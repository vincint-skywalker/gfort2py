
cpdef split_brackets(value, bint remove_b=True):
    '''
    Split a string based on pairs of brackets, nested brackets are not split

    Input:
        'abc (def) (fgh () ())'

    Outputs:
        ['abc (def')', '(fgh () ())']
    '''
    cdef int idx,j,j2,count,lvalue
    cdef bint start
    
    if remove_b:
        if value.startswith('(') and value.endswith(')'):
            value = value[1:-1]
    
    res = []
    start = False
    count = 0
    j = 0
    for idx,i in enumerate(value):
        if i == '(':
            count = count + 1
            start = True
        if i == ')':
            count = count - 1
        if start:
            if count == 0:
                j2=idx+1
                res.append(value[j:j2])
                j=j2
                start = False
                
    if not j == len(value):
        res.append(value[j:])

    return res
