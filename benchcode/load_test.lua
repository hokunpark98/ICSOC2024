local counter = 0

request = function()
    path = "/a?value=" .. counter
    counter = 1
    return wrk.format(nil, path)
end
