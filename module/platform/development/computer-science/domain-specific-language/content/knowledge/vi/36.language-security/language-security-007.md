# Giới hạn tài nguyên

Một DSL (Domain-Specific Language) thường được thiết kế để mô tả cấu hình, truy vấn, workflow, chính sách hoặc quy trình xây dựng phần mềm. Đầu vào DSL có thể do developer viết, được sinh tự động, được tải từ repository bên ngoài hoặc do người dùng gửi qua API. Dù cú pháp hợp lệ, một chương trình DSL vẫn có thể yêu cầu quá nhiều CPU, bộ nhớ, thời gian, I/O hoặc tài nguyên bên ngoài. Nếu hệ thống không giới hạn mức sử dụng, một file có thể làm parser treo, compiler hết bộ nhớ, evaluator chạy vô hạn, plugin chiếm CPU hoặc query làm cạn database connection.

Trong chương **Bảo mật DSL**, **giới hạn tài nguyên (resource limits)** là những ràng buộc được áp dụng để giới hạn lượng tài nguyên mà một lần phân tích, biên dịch, đánh giá hoặc thực thi DSL được phép tiêu thụ. Mục tiêu là giữ hệ thống ổn định, ngăn từ chối dịch vụ (denial of service), bảo vệ các tenant dùng chung nền tảng và bảo đảm một tác vụ không thể chiếm toàn bộ năng lực của process hoặc máy chủ.

Ví dụ, một DSL xử lý biểu thức có thể áp dụng các giới hạn:

~~~text
resourcePolicy "untrusted-input" {
    maxSourceBytes = 1Mi
    maxTokens = 100000
    maxAstNodes = 80000
    maxNestingDepth = 128
    maxEvaluationSteps = 500000
    maxWallTime = 3s
    maxMemory = 128Mi
}
~~~

Đây là cú pháp minh họa. Các giá trị thực tế cần được chọn theo workload, runtime, số lượng người dùng đồng thời và mức độ tin cậy của đầu vào. Không có một bộ giới hạn phù hợp cho mọi DSL.

Giới hạn tài nguyên cần được thực thi ở nhiều lớp: trước khi parse, trong parser, khi xây AST, trong semantic analysis, khi evaluate expression, khi chạy plugin, khi sinh output và khi gọi backend. Một giới hạn chỉ được ghi trong tài liệu hoặc chỉ kiểm tra sau khi tác vụ hoàn tất sẽ không bảo vệ được hệ thống.

## 1. Tài nguyên là gì?

Tài nguyên là năng lực mà một tác vụ sử dụng trong quá trình xử lý. Với DSL, những loại quan trọng gồm:

| Tài nguyên | Ví dụ | Rủi ro khi không giới hạn |
|---|---|---|
| CPU time | Parse, type-check, evaluate | Một tác vụ chiếm CPU kéo dài |
| Wall-clock time | Tổng thời gian xử lý | Request giữ worker và connection quá lâu |
| Memory | Token, AST, symbol table, cache | Process hết bộ nhớ |
| Input size | Source file, request payload | Đầu vào rất lớn làm tăng chi phí xử lý |
| Structural complexity | Độ sâu, số node, số reference | Stack overflow hoặc xử lý tăng mạnh |
| Concurrency | Số tác vụ đồng thời | Thread pool hoặc worker queue bị cạn |
| I/O | File, network, database | Chờ vô hạn hoặc tạo tải lớn lên dependency |
| Output size | Generated code, diagnostics, result | Disk, memory hoặc response bị chiếm dụng |
| External quota | API calls, cloud resources | Hết quota hoặc phát sinh chi phí |
| Persistent storage | Cache, artifact, log | Disk đầy và dịch vụ suy giảm |

Không nên chỉ đo một loại tài nguyên. Một tác vụ có thể dùng ít CPU nhưng giữ hàng nghìn connection đang chờ network; một file source nhỏ có thể tạo ra AST rất lớn; một query ngắn có thể kích hoạt database scan trên hàng tỷ bản ghi.

### 1.1. CPU time và wall-clock time

CPU time đo thời gian CPU thực sự chạy tác vụ. Wall-clock time đo khoảng thời gian từ lúc bắt đầu đến lúc kết thúc, bao gồm cả thời gian chờ I/O, lock hoặc scheduler.

Hai giới hạn này bổ sung cho nhau:

- CPU budget ngăn computation quá tốn kém.
- Wall-clock deadline ngăn request giữ tài nguyên quá lâu.

Một compiler có thể dùng CPU liên tục khi giải quyết biểu thức phức tạp. Một plugin có thể gần như không dùng CPU nhưng chờ network vô hạn. Chỉ dùng CPU limit sẽ không xử lý được trường hợp thứ hai.

### 1.2. Bộ nhớ

Bộ nhớ được dùng cho source text, token, AST, symbol table, type information, cache, intermediate representation và output. Một cấu trúc có thể tạo nhiều object nhỏ, gây áp lực garbage collector hoặc fragmentation dù kích thước source không quá lớn.

### 1.3. Tài nguyên bên ngoài

DSL có thể yêu cầu database query, HTTP call, package download, file access hoặc tạo cloud resource. Những thao tác này tiêu thụ quota và năng lực của hệ thống khác. Resource policy cần bao gồm cả dependency bên ngoài, không chỉ process cục bộ.

## 2. Vì sao giới hạn tài nguyên thuộc về bảo mật DSL?

Một hệ thống có thể bị từ chối dịch vụ mà không cần khai thác lỗi memory corruption hoặc thực thi mã trái phép. Chỉ cần đầu vào làm hệ thống tiêu tốn quá nhiều thời gian hoặc bộ nhớ cũng đủ khiến người dùng khác không thể sử dụng dịch vụ.

Các mục tiêu bảo mật chính:

- **Availability:** giữ dịch vụ sẵn sàng khi nhận đầu vào xấu hoặc workload bất thường.
- **Isolation:** ngăn một tenant ảnh hưởng tài nguyên của tenant khác.
- **Predictability:** bảo đảm tác vụ có giới hạn chi phí và thời gian.
- **Cost control:** tránh API call, compute hoặc cloud resource phát sinh ngoài dự kiến.
- **Containment:** khi một tác vụ vượt giới hạn, dừng nó mà không làm sập process chủ.
- **Fairness:** phân phối worker, CPU và quota theo chính sách.

### 2.1. Denial of service qua đầu vào DSL

Kẻ tấn công có thể gửi:

- File cực lớn.
- Cấu trúc lồng nhau rất sâu.
- Biểu thức gây backtracking hoặc tính toán bùng nổ.
- Nhiều import/include tạo đồ thị dependency lớn.
- Macro mở rộng lặp lại.
- Query trả về lượng dữ liệu khổng lồ.
- Workflow tạo quá nhiều task hoặc vòng lặp.

Mỗi đầu vào có thể hợp lệ theo grammar nhưng không hợp lý về chi phí. Parser và evaluator cần có giới hạn độc lập với kiểm tra cú pháp.

### 2.2. Resource exhaustion không chỉ do người dùng ác ý

Lỗi generator, recursive macro, dependency cycle, cache miss hoặc cấu hình sai cũng có thể gây cạn tài nguyên. Resource limits bảo vệ cả trước bug và workload ngoài dự kiến.

### 2.3. Shared service và multi-tenancy

Trong dịch vụ chạy DSL cho nhiều khách hàng, một tenant không nên có thể tiêu thụ hết CPU hoặc memory của worker pool. Cần giới hạn theo request, user, tenant và toàn hệ thống.

## 3. Threat model và ranh giới tin cậy

Trước khi chọn giới hạn, cần xác định ai có thể gửi DSL và tác vụ chạy ở đâu.

Nguồn đầu vào có thể là:

- Source code trong repository nội bộ.
- File cấu hình do người dùng tải lên.
- Request gửi tới API công khai.
- Plugin hoặc extension của bên thứ ba.
- Module được tải từ registry.
- DSL được sinh từ form hoặc công cụ AI.
- Event hoặc message được xử lý tự động.

Mức độ tin cậy khác nhau. Source trong repository được review vẫn có thể có lỗi; file do người dùng gửi phải được coi là không đáng tin cậy; plugin bên thứ ba cần sandbox riêng.

### 3.1. Xác định asset cần bảo vệ

Asset có thể gồm:

- CPU và memory của compiler service.
- Worker và queue dùng chung.
- Database connection pool.
- Package registry và artifact store.
- Cloud account quota.
- File system và disk.
- Network bandwidth.
- Secret và dữ liệu tenant khác.

### 3.2. Xác định attacker capability

Kẻ tấn công có thể:

- Chọn nội dung DSL tùy ý.
- Gửi nhiều request song song.
- Tạo file có cấu trúc bất thường.
- Chọn reference hoặc function mà DSL cho phép.
- Tải module hoặc plugin từ nguồn bên ngoài nếu policy mở.
- Lặp lại request để khai thác retry hoặc cache.

Không nên giả định attacker chỉ gửi một file nhỏ và chạy một lần.

### 3.3. Ranh giới thực thi

Resource limits cần được áp dụng tại các ranh giới:

1. API gateway nhận request.
2. Queue nhận job.
3. Parser và compiler process.
4. Evaluator hoặc runtime.
5. Plugin process.
6. Backend query hoặc build tool.
7. External service và cloud provider.

Nếu parser được giới hạn nhưng plugin chạy trong cùng process với quyền không giới hạn, toàn bộ hệ thống vẫn dễ bị ảnh hưởng.

## 4. Resource budget và quota

**Resource budget** là ngân sách tài nguyên dành cho một tác vụ hoặc một phạm vi. **Quota** là giới hạn tổng lượng sử dụng trong một khoảng thời gian hoặc một phạm vi quản lý.

Ví dụ:

~~~text
resourcePolicy "api-request" {
    cpuBudget = 2s
    wallClockDeadline = 5s
    memoryBudget = 128Mi
    maxSourceBytes = 512Ki
    maxOutputBytes = 2Mi
}

quota "tenant-standard" {
    concurrentJobs = 4
    jobsPerMinute = 30
    artifactStorage = 2Gi
    externalCallsPerJob = 50
}
~~~

### 4.1. Per-operation budget

Một request parse, compile hoặc evaluate có thể nhận budget riêng. Budget nên được tạo ở đầu request và truyền xuyên suốt các bước để tổng chi phí không vượt giới hạn.

### 4.2. Per-tenant quota

Tenant quota giới hạn tổng sử dụng của một khách hàng trong khoảng thời gian. Nó giúp tránh một tenant chiếm tài nguyên dùng chung.

### 4.3. Global quota

Global quota bảo vệ toàn dịch vụ, ví dụ tổng số job đang chạy hoặc số kết nối tới database. Ngay cả khi mỗi tenant nằm trong quota riêng, tổng request vẫn có thể vượt năng lực hệ thống.

### 4.4. Burst và sustained rate

Rate limit có thể cho phép một burst ngắn nhưng giới hạn tốc độ trung bình dài hạn. Token bucket hoặc leaky bucket là những mô hình phổ biến để điều tiết request.

### 4.5. Budget phải được trừ nhất quán

Nếu parser và evaluator tự tạo budget riêng, tổng chi phí có thể vượt chính sách. Một execution context nên giữ deadline và budget dùng chung; mỗi stage chỉ tiêu thụ phần còn lại.

## 5. Giới hạn kích thước đầu vào

Giới hạn đầu tiên nên được áp dụng trước khi parser đọc toàn bộ source. Input size lớn làm tăng memory, CPU, token count và output.

Các loại kích thước cần xem xét:

- Số byte của request body.
- Số byte của từng file.
- Tổng kích thước tất cả file trong một project.
- Số file import.
- Kích thước archive sau giải nén.
- Độ dài một token hoặc literal.
- Kích thước string và collection trong runtime.

### 5.1. Giới hạn byte thay vì chỉ ký tự

UTF-8 có thể dùng nhiều byte cho một ký tự. Nếu giới hạn network payload hoặc file, byte count là đại lượng phù hợp hơn.

### 5.2. Giới hạn tổng project

Một project có thể chứa nhiều file nhỏ. Giới hạn từng file không ngăn được tổng project rất lớn. Cần cả per-file limit và total workspace limit.

### 5.3. Archive expansion

File nén nhỏ có thể giải nén thành lượng dữ liệu rất lớn. Khi nhận ZIP hoặc archive, cần giới hạn:

- Kích thước archive.
- Tổng kích thước sau giải nén.
- Số entry.
- Độ sâu thư mục.
- Tỷ lệ nén bất thường.
- Symbolic link hoặc path entry không hợp lệ.

### 5.4. Giới hạn độ dài token và literal

Một identifier, string literal, numeric literal hoặc regex pattern cực dài có thể làm lexer hoặc parser tiêu tốn tài nguyên. Nên có giới hạn riêng phù hợp grammar.

### 5.5. Reject sớm

Nếu request vượt maxSourceBytes, API nên từ chối trước khi đọc hoặc parse toàn bộ payload. Error response cần có mã ổn định và không echo lại toàn bộ nội dung lớn.

## 6. Giới hạn trong lexer và parser

Parser thường là điểm đầu tiên biến source text thành cấu trúc nội bộ. Những giới hạn cần xem xét:

- Tổng số token.
- Độ dài token tối đa.
- Độ sâu nested block.
- Số lượng delimiter chưa đóng.
- Số lượng comment.
- Số lượng error recovery.
- Số node parse tree.
- Số lượng diagnostic.

### 6.1. Giới hạn nesting depth

Source lồng nhau sâu có thể làm recursive descent parser vượt call stack:

~~~text
(((((((((((( expression ))))))))))))
~~~

Parser nên đếm nesting depth và từ chối khi vượt giới hạn. Nếu parser dùng recursion, giới hạn cần thấp hơn mức có thể gây stack overflow trong runtime.

### 6.2. Iterative parsing

Với grammar cho phép nesting sâu, parser có thể dùng explicit stack thay vì recursive call. Tuy nhiên, iterative parsing không loại bỏ nhu cầu giới hạn depth; nó chỉ giúp kiểm soát stack memory tốt hơn.

### 6.3. Token count

Một file có thể gồm hàng triệu token nhỏ. Giới hạn source bytes không đủ để dự đoán số object token, nhất là khi token object có overhead đáng kể.

### 6.4. Error recovery

Parser có thể tiếp tục sau lỗi để tạo nhiều diagnostics. Nhưng input lỗi hàng loạt có thể khiến parser phát ra hàng trăm nghìn lỗi. Cần giới hạn số diagnostic và số lần recovery.

### 6.5. Parse timeout

Parser nên nhận deadline hoặc cancellation token. Nếu parser library không hỗ trợ cancellation trực tiếp, có thể chạy nó trong worker process có thể terminate khi hết deadline.

## 7. Giới hạn kích thước và độ phức tạp AST

AST có thể lớn hơn source nhiều lần vì mỗi node chứa object header, reference, type metadata và source location.

Các giới hạn:

- Tổng số AST node.
- Số child trên mỗi node.
- Độ sâu AST.
- Số declaration.
- Số attribute hoặc block.
- Số reference.
- Số symbol trong scope.
- Kích thước metadata và annotation.

### 7.1. Fan-out

Một node có hàng trăm nghìn child có thể gây memory spike hoặc khiến visitor xử lý lâu. Giới hạn số phần tử trong list, block hoặc argument list.

### 7.2. AST expansion

Macro, template hoặc desugaring có thể làm AST tăng mạnh sau parse. Cần budget riêng cho AST sau expansion, không chỉ đếm node source ban đầu.

### 7.3. Source mapping

Source range và origin metadata có ích cho diagnostics nhưng có thể tiêu tốn bộ nhớ nếu mỗi node giữ nhiều bản sao. Có thể dùng shared source table hoặc compact representation.

### 7.4. Streaming và lazy representation

Với định dạng lớn, streaming parser hoặc lazy node có thể giảm peak memory. Tuy nhiên, nếu semantic analysis cần toàn bộ symbol graph, vẫn cần giới hạn tổng dữ liệu và số reference.

## 8. Giới hạn trong semantic analysis và name resolution

Sau parsing, compiler thường xây symbol table, resolve reference, kiểm tra kiểu và phân tích dependency. Những bước này có thể có chi phí lớn.

### 8.1. Số declaration và symbol

Giới hạn số module, declaration, function, type, variable và symbol trong một scope. Một file có thể khai báo rất nhiều tên ngắn và làm symbol table tăng mạnh.

### 8.2. Lookup complexity

Nếu name resolution dùng tìm kiếm tuyến tính trong danh sách lớn, nhiều reference có thể tạo chi phí gần O(n²). Dùng map hoặc index phù hợp và đặt giới hạn reference.

### 8.3. Dependency graph

Một graph có nhiều node và edge tiêu tốn memory. Cần giới hạn số node, edge, component và độ sâu traversal.

### 8.4. Cycle detection

Cycle detection thường có thể chạy O(V + E), nhưng graph quá lớn vẫn tốn tài nguyên. Dùng thuật toán có độ phức tạp rõ và budget cho traversal.

### 8.5. Type inference

Một số hệ kiểu có thể tạo constraint graph lớn. Type inference cần giới hạn số constraint, số lần rewrite và thời gian giải. Khi không hội tụ trong budget, trả diagnostic thay vì tiếp tục vô hạn.

### 8.6. Overload resolution

Nếu một function có hàng nghìn overload hoặc expression có nhiều candidate, việc thử từng tổ hợp có thể rất tốn kém. Cần giới hạn candidate count và quy tắc disambiguation rõ.

## 9. Giới hạn đệ quy, macro và template expansion

DSL có thể hỗ trợ macro, template, include, module composition hoặc function đệ quy. Các tính năng này làm source ngắn hơn nhưng có thể mở rộng thành cấu trúc rất lớn.

Ví dụ macro tự gọi:

~~~text
macro repeatBlock() {
    repeatBlock()
}
~~~

Nếu compiler mở rộng macro không có giới hạn, nó có thể chạy mãi hoặc cạn bộ nhớ.

### 9.1. Expansion depth

Đặt giới hạn số lần macro hoặc template được mở rộng lồng nhau.

### 9.2. Expansion count

Giới hạn tổng số macro invocation hoặc số node được sinh ra. Depth thấp vẫn có thể tạo fan-out rất lớn nếu mỗi macro gọi nhiều macro con.

### 9.3. Include/import count

Giới hạn số file và module được load trong một compilation unit. Kiểm tra duplicate import và cycle để tránh đọc lại cùng tài nguyên không cần thiết.

### 9.4. Recursive function

Nếu DSL cho phép recursion, cần xác định runtime có hỗ trợ hay không, có giới hạn call depth, step count hoặc gas hay không. Nếu recursion không cần thiết cho domain, có thể loại bỏ khỏi ngôn ngữ.

### 9.5. Template amplification

Một template nhỏ có thể được áp dụng cho hàng nghìn phần tử. Cần tính chi phí theo số lần instantiate và kích thước kết quả.

### 9.6. Expansion provenance

Khi vượt giới hạn, diagnostics nên chỉ ra macro hoặc template nào tạo ra phần mở rộng lớn, kèm source location gốc và call chain. Điều này giúp sửa nguyên nhân mà không phải in toàn bộ AST.

## 10. Giới hạn trong evaluator và runtime

Nếu DSL cho phép expression hoặc workflow được đánh giá, cần giới hạn chi phí thực thi.

Các budget thường dùng:

- Maximum evaluation steps.
- Maximum call depth.
- Maximum loop iterations.
- Maximum collection size.
- Maximum string size.
- Maximum recursion depth.
- CPU budget.
- Wall-clock deadline.
- Memory budget.
- External call count.

### 10.1. Step counter

Evaluator có thể trừ một đơn vị budget cho mỗi operation hoặc nhóm operation:

~~~text
evaluate(node, context):
    context.budget.consume(1)
    if context.budget.exhausted:
        raise ResourceLimitExceeded

    return evaluateNode(node, context)
~~~

Step counter có thể kiểm soát computation thuần. Chi phí từng operation có thể khác nhau, vì vậy một số runtime dùng weighted cost thay vì mỗi node chỉ tính một bước.

### 10.2. Gas model

Gas là mô hình tính phí cho computation theo trọng số. Operation đơn giản có thể tốn ít gas; operation như regex, sorting hoặc external call có thể tốn nhiều hơn.

~~~text
resourcePolicy "workflow" {
    maxGas = 100000
    cost {
        arithmetic = 1
        collectionIteration = 2
        regexMatch = 50
        externalCall = 500
    }
}
~~~

Gas hữu ích khi muốn giới hạn chi phí logic độc lập với tốc độ CPU của máy. Nó cần được thiết kế ổn định và không được xem là phép đo thời gian chính xác.

### 10.3. Loop iteration

Loop cần giới hạn số vòng lặp hoặc kích thước input:

~~~text
for item in input.items limit 1000 {
    process(item)
}
~~~

Nếu số phần tử lớn hơn giới hạn, runtime cần từ chối hoặc áp dụng semantics được định nghĩa rõ. Không nên âm thầm bỏ phần tử nếu điều đó làm sai kết quả nghiệp vụ.

### 10.4. Call depth

Call depth giới hạn chuỗi function call và recursion. Runtime nên phát hiện trước khi stack overflow.

### 10.5. Collection growth

Một expression có thể tạo list hoặc map rất lớn. Cần giới hạn số phần tử, tổng byte và số lần copy.

### 10.6. String concatenation

Nối chuỗi lặp có thể tạo nhiều bản sao trung gian. Runtime có thể dùng builder hoặc rope, nhưng vẫn cần giới hạn tổng độ dài output.

## 11. Giới hạn cho biểu thức tốn kém

Không phải mọi biểu thức có cùng chi phí.

Các operation cần chú ý:

- Regex với pattern phức tạp.
- Sorting collection lớn.
- Join hoặc cross product.
- Recursive traversal.
- JSONPath hoặc XPath.
- Full-text search.
- Compression/decompression.
- Cryptographic operation lặp nhiều lần.
- Function do plugin cung cấp.

### 11.1. Regular expression và ReDoS

Một regex có thể gây catastrophic backtracking trên chuỗi đầu vào được chọn có chủ đích. Đây là dạng Regular Expression Denial of Service (ReDoS).

Biện pháp:

- Giới hạn độ dài pattern và input.
- Dùng regex engine có complexity bảo đảm nếu phù hợp.
- Đặt timeout hoặc cancellation nếu engine hỗ trợ.
- Tránh pattern có cấu trúc backtracking nguy hiểm.
- Không cho người dùng không tin cậy cung cấp regex tùy ý nếu domain không cần.

### 11.2. Sorting

Sort thường có chi phí O(n log n), nhưng có thể tiêu tốn memory cho collection và comparator. Giới hạn số phần tử và tránh comparator có side effect hoặc thực thi code tùy ý.

### 11.3. Nested loops và cross product

Hai collection có kích thước n và m khi tạo cross product có thể sinh n × m phần tử. Cần ước lượng output cardinality trước khi materialize.

### 11.4. Query expression

DSL truy vấn có thể cho phép filter, join, aggregation và sort. Giới hạn AST depth, join count, page size, scan budget và query timeout; đồng thời dựa vào query planner của database để đánh giá execution plan khi cần.

## 12. Giới hạn cho I/O và external calls

Một DSL có thể gọi file system, HTTP endpoint, database, package registry hoặc cloud API. Các thao tác này cần budget riêng.

### 12.1. Timeout

Mỗi external call cần timeout hữu hạn. Không để request chờ vô thời hạn khi dependency không phản hồi.

### 12.2. Tổng thời gian I/O

Nhiều call riêng lẻ có timeout ngắn vẫn có thể làm tổng request kéo dài. Cần một deadline chung và truyền phần thời gian còn lại tới từng dependency.

### 12.3. Call count

Giới hạn số request HTTP, database query, file open hoặc registry lookup trong một execution.

### 12.4. Response size

Giới hạn số byte nhận về. External service có thể trả response rất lớn hoặc không đúng content length dự kiến.

### 12.5. Retry budget

Retry có thể nhân số request lên nhiều lần. Đặt giới hạn số lần retry, backoff và tổng thời gian. Không retry lỗi validation hoặc lỗi không thể phục hồi.

### 12.6. Connection pool

Giới hạn connection đồng thời và thời gian chờ lấy connection. Khi pool đầy, request cần fail hoặc queue có giới hạn thay vì tạo thêm connection vô hạn.

### 12.7. SSRF và network scope

Nếu DSL cho phép URL hoặc HTTP call, resource policy cần đi cùng network policy: allowlist host, cấm địa chỉ nội bộ nhạy cảm nếu không cần, giới hạn redirect và kiểm tra DNS resolution theo threat model. Chỉ giới hạn số call không ngăn được request tới endpoint nguy hiểm.

## 13. Giới hạn cho file system và module loading

DSL compiler có thể đọc file import, template, schema hoặc package. File access cần được giới hạn theo workspace và policy.

### 13.1. Workspace boundary

Chỉ cho phép đọc những path thuộc workspace hoặc vùng được cấp. Resolve path sau khi canonicalize để tránh path traversal và symlink escape.

### 13.2. File count và total bytes

Giới hạn số file được mở và tổng bytes đọc trong một lần compile.

### 13.3. Include depth và cycle

Đặt giới hạn include depth và phát hiện cycle. Cùng một file được import nhiều lần nên có cache hoặc deduplication theo semantics của ngôn ngữ.

### 13.4. Symlink

Symlink có thể trỏ ra ngoài workspace. Chính sách cần xác định có cho phép symlink không, và nếu có thì phải kiểm tra target sau khi resolve.

### 13.5. File descriptor

Đóng file handle sau khi đọc và giới hạn số file mở đồng thời. Leak file descriptor có thể làm process không mở được file mới.

### 13.6. Package download

Package loader cần giới hạn kích thước download, số dependency, dependency depth, archive expansion và thời gian tải. Nên pin version và checksum để tránh nội dung thay đổi ngoài dự kiến.

## 14. Giới hạn cho plugin và extension

Plugin có thể mở rộng DSL bằng function, rule, backend hoặc generator. Vì plugin có thể chạy code riêng, nó cần được xem là một ranh giới tin cậy.

### 14.1. Plugin có thể tiêu thụ tài nguyên nào?

- CPU và memory.
- Thread và process.
- File system.
- Network.
- Database connection.
- Log và output.
- Compiler context hoặc shared cache.

### 14.2. In-process plugin

Plugin chạy cùng process có thể chia sẻ memory và thread với host. Timeout ở một callback không bảo đảm dừng được code đang chạy. Nếu plugin bị treo hoặc cấp phát quá nhiều memory, process chủ có thể bị ảnh hưởng.

In-process plugin chỉ phù hợp khi trust level cao và API có kiểm soát. Với plugin không tin cậy, nên dùng process isolation hoặc sandbox phù hợp.

### 14.3. Out-of-process plugin

Plugin chạy trong process riêng giúp host có thể:

- Giới hạn memory và CPU.
- Đặt timeout.
- Terminate process.
- Giới hạn file/network access.
- Giám sát output và exit code.

Chi phí IPC và serialization tăng lên, nhưng ranh giới lỗi và tài nguyên rõ hơn.

### 14.4. Capability-based access

Chỉ cấp cho plugin capability cần thiết, ví dụ đọc AST hoặc ghi một output directory. Không truyền toàn bộ host context nếu plugin không cần.

### 14.5. Plugin budget

Mỗi plugin có thể nhận budget riêng và budget tổng của compilation. Một plugin không được tiêu thụ toàn bộ budget khiến plugin khác không chạy.

### 14.6. Plugin output

Giới hạn số diagnostic, generated file, kích thước file, log line và metadata mà plugin có thể tạo.

## 15. Giới hạn cho concurrency và scheduling

Một tác vụ đơn lẻ có thể nằm trong budget nhưng nhiều tác vụ đồng thời vẫn làm hệ thống quá tải.

Các giới hạn cần có:

- Maximum concurrent requests.
- Maximum active compiler jobs.
- Queue length.
- Worker count.
- Per-tenant concurrency.
- Per-plugin concurrency.
- Database connection pool size.
- CPU share hoặc container quota.

### 15.1. Bounded queue

Queue không giới hạn có thể tích lũy hàng triệu job khi tốc độ nhận cao hơn tốc độ xử lý. Bounded queue cần quy định khi đầy: reject, backpressure hoặc trả trạng thái retryable.

### 15.2. Backpressure

Backpressure làm chậm producer khi consumer không theo kịp. API có thể trả 429 hoặc 503 cùng Retry-After khi capacity tạm thời hết.

### 15.3. Fair scheduling

Scheduler có thể phân phối worker theo tenant hoặc priority. Cần tránh một tenant có nhiều job nhỏ chiếm hết slot.

### 15.4. Priority abuse

Nếu caller tự đặt priority, họ có thể luôn chọn mức cao nhất. Priority nên được xác định từ policy hoặc role đáng tin cậy.

### 15.5. Head-of-line blocking

Một job lớn chạy trên worker đồng bộ có thể làm các job nhỏ phải chờ. Có thể tách queue theo workload class hoặc dùng scheduler có khả năng chia sẻ công bằng.

## 16. Giới hạn output và diagnostics

Output cũng là tài nguyên. Compiler có thể sinh code, manifest, artifact, report hoặc diagnostics. Một đầu vào lỗi có thể tạo số lượng lỗi rất lớn; một generator có thể sinh file cực lớn.

Các giới hạn:

- Maximum output bytes.
- Maximum generated files.
- Maximum diagnostic count.
- Maximum diagnostic message length.
- Maximum log bytes.
- Maximum response rows.
- Maximum serialization depth.

### 16.1. Diagnostic cap

Khi vượt giới hạn, compiler có thể dừng thêm diagnostics và phát một diagnostic tổng hợp:

~~~text
error DSL000: Too many diagnostics; further messages were suppressed.
~~~

Không nên giữ vô hạn diagnostic trong memory chỉ để báo mọi lỗi.

### 16.2. Output cap

Nếu generator vượt output budget, không nên ghi một nửa artifact rồi để consumer tưởng file hoàn chỉnh. Có thể sinh vào temporary location, kiểm tra size, sau đó atomically publish khi thành công.

### 16.3. Streaming output

Streaming giảm peak memory khi output lớn. Nhưng cần giới hạn tổng bytes, tốc độ ghi và thời gian; streaming không làm output vô hạn trở nên an toàn.

### 16.4. Log volume

Plugin hoặc parser có thể ghi log liên tục. Giới hạn số byte hoặc số dòng và rate-limit log theo component.

## 17. Giới hạn cho query DSL và database

Một DSL truy vấn có thể tạo câu lệnh hợp lệ nhưng rất tốn kém. Resource controls cần áp dụng cả ở DSL runtime lẫn database.

### 17.1. Result limit

Giới hạn số hàng trả về và kích thước response. Pagination cần có max page size.

### 17.2. Query timeout

Đặt statement timeout hoặc driver timeout. Timeout ở ứng dụng cần được propagate để database có thể hủy query nếu driver hỗ trợ.

### 17.3. Query complexity

Giới hạn:

- Join count.
- Subquery depth.
- Predicate count.
- Aggregation stages.
- Sort expressions.
- Recursive query depth.
- Collection parameter size.

### 17.4. Scan và index policy

Một số hệ thống có thể kiểm tra execution plan hoặc yêu cầu index cho query quan trọng. Tuy nhiên, execution plan phụ thuộc statistics và trạng thái database, nên không nên coi một heuristic đơn giản là bằng chứng đầy đủ.

### 17.5. Connection budget

Giới hạn query concurrency và connection pool. Một request không nên mở nhiều connection song song không cần thiết.

### 17.6. Read/write budget

Có thể tách quyền và quota đọc/ghi. Một API tìm kiếm không nên vô tình cho phép query DSL phát sinh update hoặc delete.

## 18. Giới hạn cho build DSL và code generation

Build DSL có thể định nghĩa task, dependency, source set, compiler option và generator. Một build file có thể tạo hàng nghìn task hoặc kích hoạt download và process execution.

### 18.1. Task count

Giới hạn số task và dependency edge được tạo.

### 18.2. Dependency graph

Phát hiện cycle, giới hạn graph size và tránh tính toán lại dependency không cần thiết.

### 18.3. External process

Giới hạn số process đồng thời, thời gian chạy, memory và output. Không để child process thừa kế credential hoặc quyền không cần thiết.

### 18.4. Cache

Cache có thể tăng tốc nhưng cần giới hạn dung lượng và tránh cache key collision. Cache entry phải được xác định bởi input, toolchain và dependency version phù hợp.

### 18.5. Artifact size

Giới hạn kích thước package, số file và tổng artifact storage. Xử lý đúng khi build vượt quota.

### 18.6. Reproducibility

Resource limit không thay thế reproducible build. Pin toolchain, dependency và environment giúp workload có chi phí dễ dự đoán hơn.

## 19. Giới hạn cho deployment DSL và cloud resource

DSL triển khai có thể tạo service, database, queue, storage, network rule và nhiều cloud resource. Một file cấu hình sai có thể tạo tài nguyên hàng loạt và gây chi phí lớn.

### 19.1. Resource count

Giới hạn số resource mỗi deployment, mỗi project và mỗi tenant.

### 19.2. Cost budget

Có thể đặt budget chi phí ước lượng, nhưng cần ghi rõ dữ liệu giá và giả định. Cost estimate không phải số tiền thực tế được bảo đảm.

### 19.3. Quota preflight

Trước khi apply, kiểm tra quota provider như CPU, IP, volume hoặc service count. State có thể đổi giữa preflight và apply nên vẫn phải xử lý lỗi quota khi triển khai.

### 19.4. Destructive operation

Giới hạn hoặc yêu cầu approval cho thao tác xóa, replace hoặc mở rộng phạm vi tác động. Resource count nhỏ vẫn có thể gây hậu quả lớn nếu xóa database production.

### 19.5. Rollback và partial apply

Một deployment có thể thành công một phần. Tool cần ghi lại resource đã tạo/cập nhật, hỗ trợ resume hoặc cleanup có kiểm soát và không retry action không idempotent một cách mù quáng.

## 20. Cancellation và deadline propagation

Khi tác vụ vượt budget hoặc người dùng hủy request, hệ thống cần dừng công việc đang chạy và giải phóng tài nguyên.

### 20.1. Cancellation token

Một execution context có thể chứa cancellation token được truyền qua parser, compiler, evaluator và backend.

~~~text
compile(source, context):
    checkCancellation(context)
    tokens = lexer.scan(source, context)
    checkCancellation(context)
    ast = parser.parse(tokens, context)
    checkCancellation(context)
    model = analyzer.analyze(ast, context)
    return generator.emit(model, context)
~~~

Mỗi stage và vòng lặp dài cần kiểm tra cancellation tại các điểm an toàn.

### 20.2. Deadline propagation

Nếu request có deadline 5 giây, mỗi external call phải dùng phần thời gian còn lại thay vì đặt timeout 5 giây mới cho từng call. Nếu không, chuỗi 10 dependency có thể kéo dài rất lâu.

### 20.3. Cleanup

Khi cancel, cần:

- Đóng file handle.
- Hủy database statement nếu có thể.
- Dừng child process.
- Giải phóng lock.
- Thu hồi temporary file.
- Hủy timer và subscription.
- Đánh dấu job state phù hợp.

### 20.4. Cancellation không luôn tức thời

Một native library hoặc plugin không hỗ trợ interruption có thể tiếp tục chạy. Với code không tin cậy, process isolation giúp host terminate toàn bộ worker khi deadline hết.

## 21. Process isolation, sandbox và operating system controls

Resource limits trong ứng dụng có thể bị bỏ qua nếu plugin hoặc native code có thể cấp phát memory hoặc tạo thread trực tiếp. Hệ điều hành hoặc runtime isolation cung cấp lớp giới hạn mạnh hơn.

Các cơ chế có thể dùng tùy nền tảng:

- Container CPU và memory limits.
- cgroups hoặc job objects.
- Process memory limit.
- CPU time limit.
- File descriptor limit.
- Process/thread count limit.
- Filesystem namespace hoặc read-only mount.
- Network namespace và egress policy.
- Syscall filter.
- User namespace và non-root execution.
- WebAssembly runtime fuel và memory limits.

### 21.1. Container không tự động là sandbox hoàn chỉnh

Container chia sẻ kernel với host. Cần cấu hình privilege, capabilities, mounts, network và runtime security đúng cách. Không chạy plugin không tin cậy với quyền root hoặc host filesystem rộng.

### 21.2. WebAssembly

Wasm runtime có thể cung cấp memory limit, fuel metering và import capabilities. Tuy nhiên, host functions được expose vẫn có thể tạo external side effect; cần giới hạn chúng riêng.

### 21.3. Worker process

Worker process có thể chạy một compilation hoặc plugin job riêng. Supervisor theo dõi CPU, memory và deadline rồi terminate worker khi vượt budget.

### 21.4. Isolation boundary

Không chia sẻ secret, file descriptor hoặc network credential với worker nếu nó không cần. Sandbox cần cấp đúng input, output directory và capability tối thiểu.

## 22. Fairness và multi-tenant isolation

Một dịch vụ DSL dùng chung cần đảm bảo tenant không chiếm tài nguyên của nhau.

### 22.1. Per-tenant accounting

Ghi nhận CPU, memory peak, job duration, queue time, external calls và storage theo tenant.

### 22.2. Concurrency quota

Giới hạn số job đồng thời của mỗi tenant. Một tenant có thể có quota khác theo plan hoặc role, nhưng mức cao hơn vẫn phải nằm trong global capacity.

### 22.3. Fair queue

Scheduler có thể lấy job luân phiên theo tenant hoặc dùng weighted fair queue. Tránh để tenant gửi nhiều request liên tục chiếm toàn bộ queue.

### 22.4. Noisy neighbor

Noisy neighbor là tenant có workload bất thường làm ảnh hưởng tenant khác. Metrics theo tenant, quota và isolation giúp phát hiện và giới hạn ảnh hưởng.

### 22.5. Cache isolation

Cache dùng chung cần key có namespace tenant hoặc đảm bảo dữ liệu không bị lẫn. Cache hit không nên làm lộ artifact hoặc metadata của tenant khác.

## 23. Resource limits phải là policy đáng tin cậy

Không nên để người gửi DSL tự nâng giới hạn của chính tác vụ của họ.

Ví dụ nguy hiểm:

~~~text
resourcePolicy {
    maxMemory = 100Gi
    maxExecutionTime = 24h
}
~~~

Nếu policy này được chấp nhận trực tiếp từ input không tin cậy, giới hạn không còn tác dụng.

### 23.1. Trusted policy source

Resource policy nên đến từ:

- Server configuration.
- Tenant plan được xác thực.
- Administrator policy.
- Platform quota.
- Execution profile được allowlist.

DSL source có thể yêu cầu một profile, nhưng server phải kiểm tra caller có quyền dùng profile đó.

### 23.2. Hard limit và soft limit

- Hard limit: vượt ngưỡng thì từ chối hoặc dừng tác vụ.
- Soft limit: phát cảnh báo, giảm priority hoặc yêu cầu approval.

Soft limit hữu ích cho observability và capacity planning, nhưng không thay thế hard limit cho tài nguyên có thể gây sập hệ thống.

### 23.3. Default deny cho khả năng đắt đỏ

Nếu DSL hỗ trợ network, arbitrary code, recursive evaluation hoặc large export, hãy yêu cầu capability rõ ràng thay vì bật cho mọi input.

### 23.4. Policy version

Gắn version policy vào execution record để giải thích vì sao cùng một source có thể bị từ chối ở môi trường hoặc thời điểm khác nhau.

## 24. Chọn giới hạn phù hợp

Không nên chọn con số tùy ý mà không đo workload. Quy trình thiết kế:

1. Thu thập workload hợp lệ đại diện.
2. Đo CPU, memory, source size, AST nodes và wall-clock time.
3. Xác định mức tối đa nghiệp vụ thực sự cần.
4. Thêm headroom có kiểm soát.
5. Chạy stress test và adversarial input.
6. Chọn hard limit và soft threshold.
7. Theo dõi false rejection và resource exhaustion.
8. Điều chỉnh policy theo version.

### 24.1. Giới hạn theo workload class

Parser interactive, batch compiler, plugin build và public API có đặc tính khác nhau. Có thể định nghĩa profile riêng:

| Profile | Mục tiêu | Chính sách thường thấy |
|---|---|---|
| Interactive | Phản hồi nhanh cho editor | Deadline ngắn, input nhỏ |
| CI build | Compile project lớn | CPU/memory cao hơn, timeout rõ |
| Untrusted API | Xử lý input bên ngoài | Giới hạn chặt, sandbox |
| Batch analysis | Xử lý nhiều file | Queue và total budget |
| Plugin execution | Chạy extension | Process isolation và capability |

### 24.2. Relative limit và absolute limit

Absolute limit là số cụ thể như 128 MiB. Relative limit có thể là phần trăm memory hoặc CPU được cấp cho worker. Cần kết hợp để tránh giới hạn không phù hợp khi container size thay đổi.

### 24.3. Headroom

Đặt giới hạn sát mức tiêu thụ bình thường có thể gây lỗi ngẫu nhiên do garbage collection, cache hoặc khác biệt runtime. Headroom cần dựa trên số liệu, không phải phỏng đoán.

### 24.4. Limit composition

Một request có thể chịu nhiều giới hạn đồng thời: per-operation, per-tenant, per-worker và global. Khi bất kỳ hard limit nào bị vượt, hệ thống phải có hành vi rõ.

## 25. Xử lý khi vượt giới hạn

Khi tác vụ vượt resource budget, hệ thống cần kết thúc theo cách có kiểm soát.

Các kết quả có thể gồm:

- Reject trước khi bắt đầu.
- Stop processing và trả resource-limit diagnostic.
- Cancel external operation.
- Terminate worker process.
- Đưa job vào trạng thái failed hoặc cancelled.
- Yêu cầu user giảm input hoặc chọn profile khác nếu được phép.

### 25.1. Error classification

Phân biệt:

- InputTooLarge.
- NestingLimitExceeded.
- AstNodeLimitExceeded.
- EvaluationBudgetExceeded.
- CpuLimitExceeded.
- WallClockTimeout.
- MemoryLimitExceeded.
- ExternalCallQuotaExceeded.
- OutputLimitExceeded.
- TenantQuotaExceeded.

Mã lỗi ổn định giúp client hiểu có nên sửa input, retry sau hay liên hệ administrator.

### 25.2. Không retry tự động mọi lỗi

Input vượt hard limit sẽ không tự hết khi retry. Rate limit có thể retry sau Retry-After; timeout do dependency tạm thời có thể retry có giới hạn. Client cần phân biệt retryable và non-retryable.

### 25.3. Không trả stack trace

Resource exhaustion có thể phát sinh exception từ runtime. API công khai nên trả diagnostic đã chuẩn hóa, không trả stack trace hoặc thông tin nội bộ.

### 25.4. Partial output

Nếu tác vụ bị dừng giữa chừng, output tạm không nên bị coi là artifact hoàn chỉnh. Dùng temporary directory và publish atomically khi job thành công.

## 26. Observability và resource accounting

Không thể quản lý giới hạn hiệu quả nếu không biết tác vụ tiêu thụ gì.

Metrics hữu ích:

- Source bytes.
- Token count.
- AST node count và depth.
- Symbol/reference count.
- Macro expansion count.
- Evaluation steps hoặc gas.
- CPU time.
- Wall-clock duration.
- Peak memory.
- External call count và latency.
- Query duration và rows returned.
- Generated output bytes.
- Queue wait time.
- Cancellation và limit-exceeded count.

### 26.1. Metrics theo stage

Ghi nhận thời gian và tài nguyên ở từng stage:

~~~mermaid
flowchart LR
    A[Input] --> B[Lex]
    B --> C[Parse]
    C --> D[Analyze]
    D --> E[Evaluate]
    E --> F[Generate]
    F --> G[Output]
~~~

Nếu parse chiếm 80% CPU, cần xem lexer/parser; nếu evaluate tốn thời gian, cần xem expression hoặc external call. Tổng thời gian đơn lẻ không đủ để tìm bottleneck.

### 26.2. Cardinality và privacy

Không gắn raw source, secret hoặc dữ liệu cá nhân vào metric label. Label có cardinality cao như request ID có thể làm metrics backend quá tải.

### 26.3. Audit

Với tác vụ vượt quota hoặc plugin bị terminate, audit record có thể lưu tenant, policy version, resource category, thời điểm và job ID. Tránh lưu toàn bộ input nhạy cảm.

### 26.4. Alert

Alert có thể dựa trên:

- Tỷ lệ resource limit exceeded tăng đột biến.
- Worker memory gần ngưỡng.
- Queue backlog tăng.
- CPU saturation kéo dài.
- External dependency timeout.
- Tenant sử dụng quota bất thường.

### 26.5. Capacity planning

Metrics lịch sử giúp dự đoán số worker, memory, CPU và storage cần thiết. Capacity planning cần xét peak concurrency và phân bố workload, không chỉ average.

## 27. Kiểm thử resource limits

Resource policy cần được kiểm tra bằng test có chủ đích. Mục tiêu là xác nhận giới hạn được enforce, không làm hỏng process chủ và tạo kết quả có thể dự đoán.

### 27.1. Boundary tests

Với giới hạn N:

- Input có kích thước N được xử lý theo contract.
- Input N+1 bị từ chối hoặc dừng theo policy.
- Giá trị rỗng và giá trị sát biên được xử lý đúng.
- Unicode nhiều byte được tính đúng theo đơn vị.

### 27.2. Depth tests

Sinh nested expression tăng dần để xác nhận parser dừng tại depth limit và không stack overflow.

### 27.3. Expansion tests

Tạo macro hoặc template có fan-out lớn. Xác nhận expansion count được kiểm tra trước khi memory tăng không kiểm soát.

### 27.4. Timeout tests

Dùng operation chậm có thể kiểm soát để xác nhận deadline được truyền qua parser/evaluator/external call và worker được giải phóng sau timeout.

### 27.5. Memory tests

Chạy worker trong memory limit riêng và xác nhận host process vẫn sống khi worker bị terminate. Theo dõi temporary file và child process sau khi dừng.

### 27.6. Concurrency tests

Gửi nhiều request đồng thời từ một tenant và nhiều tenant. Xác nhận per-tenant fairness, queue cap và global capacity.

### 27.7. Fuzzing

Fuzz parser, deserializer, macro expansion và expression evaluator để tìm input gây crash hoặc resource spike. Fuzz test nên chạy trong sandbox với giới hạn chặt.

## 28. Ví dụ thiết kế resource policy cho một DSL service

Giả sử một API nhận DSL do khách hàng gửi để kiểm tra và sinh manifest. Service có thể định nghĩa policy phía server:

~~~yaml
profile: untrusted-dsl
input:
  maxRequestBytes: 1048576
  maxFiles: 100
  maxFileBytes: 262144
parser:
  maxTokens: 100000
  maxNestingDepth: 128
  maxAstNodes: 80000
  maxDiagnostics: 200
analysis:
  maxSymbols: 30000
  maxReferences: 50000
  maxDependencyEdges: 60000
evaluation:
  maxSteps: 500000
  maxCallDepth: 64
  maxLoopIterations: 10000
execution:
  cpuSeconds: 2
  wallClockSeconds: 5
  memoryBytes: 134217728
  maxExternalCalls: 20
output:
  maxGeneratedFiles: 200
  maxOutputBytes: 2097152
~~~

Các con số chỉ để minh họa. Một triển khai thực tế cần đo workload và xác định mức phù hợp.

### 28.1. Request admission

API gateway kiểm tra request body size, authentication, tenant quota và rate limit trước khi đưa job vào queue.

### 28.2. Worker isolation

Job chạy trong worker process/container với CPU, memory, filesystem và network policy giới hạn. Worker nhận một execution budget đã xác thực.

### 28.3. Compiler enforcement

Lexer, parser, analyzer và evaluator tiêu thụ chung budget. Mỗi stage kiểm tra deadline và cancellation.

### 28.4. External access

Nếu DSL cần resolve module, worker chỉ được truy cập registry allowlist và bị giới hạn download bytes, dependency count và timeout.

### 28.5. Output publication

Generated files được ghi vào temporary directory. Khi compile hoàn tất và tổng output nằm trong giới hạn, service mới publish artifact.

### 28.6. Accounting

Service ghi lại duration, CPU, peak memory, token count, AST nodes và limit status theo job/tenant. Raw DSL và secret không được đưa vào metric label.

## 29. Ví dụ: giới hạn evaluator cho expression DSL

Giả sử DSL hỗ trợ arithmetic, list, function call và loop. Runtime có thể dùng budget:

~~~text
executionPolicy {
    maxSteps = 200000
    maxCallDepth = 48
    maxCollectionItems = 5000
    maxStringBytes = 65536
    maxLoopIterations = 10000
    deadline = 2s
}
~~~

Evaluator minh họa:

~~~java
Value evaluate(Node node, Context context) {
    context.checkCancelled();
    context.budget().consume(costOf(node));

    if (context.budget().isExceeded()) {
        throw new ResourceLimitExceededException(
            "Evaluation step budget exceeded"
        );
    }

    return switch (node.kind()) {
        case LITERAL -> evaluateLiteral(node);
        case ADD -> evaluateAdd(node, context);
        case CALL -> evaluateCall(node, context);
        case LIST -> evaluateList(node, context);
    };
}
~~~

Đây là pseudocode. Runtime thật cần bảo đảm mọi đường thực thi, kể cả function built-in và plugin callback, đều tiêu thụ budget phù hợp.

### 29.1. Built-in function

Một built-in sort có thể tính cost dựa trên số phần tử. Regex function có thể cần cost lớn hơn và timeout riêng. Nếu một function không thể được đo hoặc dừng, không nên expose nó cho input không tin cậy.

### 29.2. Function call và recursion

Trước khi gọi function, tăng call depth; khi function kết thúc, giảm depth trong finally hoặc cơ chế tương đương để không làm sai trạng thái khi có exception.

### 29.3. Collection allocation

Trước khi tạo collection, kiểm tra expected size nếu có thể. Với generator lazy, vẫn cần giới hạn số phần tử được consume để tránh một consumer lặp vô hạn.

## 30. Ví dụ: resource limits cho query DSL

Một Query DSL nhận filter động có thể đặt:

~~~text
queryPolicy "interactive-search" {
    maxAstDepth = 32
    maxPredicates = 100
    maxJoins = 8
    maxInValues = 1000
    maxPageSize = 100
    maxRows = 10000
    statementTimeout = 2s
    maxConcurrentQueries = 5
}
~~~

Khi build query, compiler kiểm tra cấu trúc AST. Khi execute, runtime áp dụng parameter limit, statement timeout, result limit và connection quota.

### 30.1. Giới hạn trước execution

AST có quá nhiều join có thể bị từ chối trước khi gửi tới database. Điều này tiết kiệm connection và giúp thông báo lỗi rõ.

### 30.2. Giới hạn tại database

Application timeout không phải lúc nào cũng dừng query phía database. Dùng statement timeout hoặc cancellation API của driver khi được hỗ trợ.

### 30.3. Giới hạn result

Không tải toàn bộ hàng vào memory rồi mới cắt. Dùng LIMIT, cursor hoặc streaming có giới hạn để database và ứng dụng không tạo kết quả khổng lồ.

### 30.4. Query plan

Với query quan trọng, có thể kiểm tra execution plan hoặc cost estimate trong môi trường phù hợp. Không thực thi mọi query của người dùng với quyền hoặc chi phí không giới hạn chỉ vì AST hợp lệ.

## 31. Ví dụ: resource limits cho build DSL

Một build DSL có thể định nghĩa task graph:

~~~text
buildPolicy "ci" {
    maxTasks = 2000
    maxDependencyEdges = 10000
    maxParallelTasks = 8
    maxChildProcesses = 16
    maxTaskDuration = 10m
    maxArtifactBytes = 1Gi
    maxCacheBytes = 5Gi
}
~~~

### 31.1. Task graph

Giới hạn node và edge trước khi scheduler bắt đầu chạy. Phát hiện cycle và từ chối graph không hợp lệ.

### 31.2. Parallel execution

Max parallel tasks bảo vệ CPU và memory. Scheduler có thể điều chỉnh concurrency theo loại task thay vì chỉ dựa vào số lượng.

### 31.3. Child process

Mỗi process cần timeout, output cap và resource limit. Khi task bị cancel, process con cũng cần được terminate.

### 31.4. Cache và artifact

Giới hạn cache eviction, artifact retention và tổng disk usage. Không để build thất bại vì disk đầy mà không có diagnostics.

## 32. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ giới hạn file size | AST hoặc expansion vẫn có thể rất lớn | Giới hạn token, node, depth và expansion |
| Chỉ dùng timeout | Memory có thể tăng vọt trước deadline | Kết hợp time và memory limit |
| Chỉ đo CPU | I/O có thể chờ vô hạn | Có wall-clock deadline và I/O timeout |
| Parser đệ quy không giới hạn | Stack overflow | Depth limit và parser stack có kiểm soát |
| Macro không có expansion cap | AST amplification | Giới hạn depth, invocation và generated nodes |
| Retry vô hạn | Tăng tải lên dependency | Retry budget và backoff |
| Queue không giới hạn | Backlog chiếm memory và tăng latency | Bounded queue và backpressure |
| Plugin chạy chung process không kiểm soát | Plugin có thể làm sập host | Process isolation và capability |
| Cho caller tự nâng quota | Resource policy mất tác dụng | Policy từ nguồn tin cậy |
| Chỉ có quota per-tenant | Tổng tải vẫn vượt global capacity | Per-tenant và global limit |
| Chỉ giới hạn output sau khi tạo xong | Memory/disk đã bị tiêu thụ | Streaming có cap hoặc temporary output |
| Không truyền cancellation | Worker tiếp tục chạy sau khi request kết thúc | Deadline và cancellation propagation |
| Dùng mock để kiểm tra timeout | Không phản ánh driver hoặc OS thật | Integration tests trong sandbox |
| Không đo resource usage | Không biết limit có phù hợp | Metrics theo stage và workload |
| Log toàn bộ input khi lỗi | Tốn storage và có thể lộ secret | Diagnostic cap và redaction |
| Coi container là bảo vệ tuyệt đối | Quyền host hoặc network vẫn có thể rộng | Hardening sandbox và least privilege |

## 33. Quy trình thiết kế resource limits cho DSL

Một quy trình thực tế có thể gồm:

1. **Xác định nguồn input:** repository, API, plugin, registry hoặc generated source.
2. **Xác định tài nguyên cần bảo vệ:** CPU, memory, I/O, worker, database, network và storage.
3. **Lập threat model:** attacker có thể chọn input, concurrency và external dependency nào?
4. **Đo workload hợp lệ:** source size, token count, AST size, compile time và peak memory.
5. **Đặt admission limits:** request size, file count, rate và queue capacity.
6. **Đặt parser limits:** token, depth, node và diagnostics.
7. **Đặt semantic limits:** symbols, references, graph size và inference steps.
8. **Đặt runtime budget:** gas, loop, recursion, memory và deadline.
9. **Đặt external limits:** timeout, response size, call count và retry budget.
10. **Cô lập plugin:** process, container hoặc Wasm sandbox cùng capability.
11. **Đặt output limits:** file count, bytes, logs và diagnostics.
12. **Thiết kế fairness:** per-tenant quota, global quota và scheduler.
13. **Định nghĩa exceed behavior:** reject, cancel, terminate, retry hoặc approval.
14. **Instrument:** metrics theo stage, tenant và policy version.
15. **Kiểm thử boundary và adversarial input:** stress, fuzz, timeout và concurrency.
16. **Điều chỉnh có kiểm soát:** version policy và review false rejection.

Giới hạn cần được ghi rõ trong contract API hoặc tài liệu DSL. Client nên biết kích thước, thời gian hoặc quota tối đa để có thể chia nhỏ tác vụ phù hợp.

## 34. Tiêu chí của một resource policy tốt

Một resource policy tốt bảo vệ hệ thống mà vẫn cho phép workload hợp lệ hoàn thành. Nó có phạm vi rõ, được lấy từ nguồn tin cậy, có thể quan sát và có hành vi xác định khi vượt ngưỡng.

Các câu hỏi quan trọng:

- Đầu vào đến từ ai và mức độ tin cậy nào?
- Có giới hạn byte, file count, token count và archive expansion không?
- Parser có giới hạn nesting, token, AST node và error recovery không?
- Macro, import và template có expansion cap không?
- Semantic analysis có giới hạn symbol, reference, graph và inference không?
- Evaluator có step/gas budget, call depth và loop limit không?
- Regex, sorting, join và collection growth có được kiểm soát không?
- External call có timeout, response cap và retry budget không?
- Plugin có process isolation và capability tối thiểu không?
- Queue, worker, connection và concurrency có giới hạn không?
- Output và diagnostics có byte/count cap không?
- Per-tenant quota có kết hợp global capacity limit không?
- Cancellation có được truyền xuyên suốt và cleanup đầy đủ không?
- Resource policy có đến từ server hoặc administrator đáng tin cậy không?
- Khi vượt giới hạn, lỗi có phân loại và retry semantics rõ không?
- Metrics có cho biết stage nào tiêu thụ tài nguyên và tenant nào vượt quota không?

Giới hạn tài nguyên là một phần của thiết kế bảo mật DSL, bởi một ngôn ngữ an toàn cần kiểm soát cả điều gì được phép diễn đạt lẫn chi phí để xử lý và thực thi điều đó. Khi input, parser, AST, semantic analysis, evaluator, plugin, I/O, output và concurrency đều có budget phù hợp, hệ thống có thể từ chối workload bất thường sớm, cô lập lỗi và giữ năng lực phục vụ cho các tác vụ khác. Resource policy cần được đo lường, enforce ở đúng ranh giới và cập nhật theo workload thực tế để duy trì cả availability lẫn khả năng sử dụng.
