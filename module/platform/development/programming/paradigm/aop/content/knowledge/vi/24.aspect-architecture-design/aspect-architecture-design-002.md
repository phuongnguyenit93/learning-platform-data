# Xác định nơi áp dụng và nơi tuyệt đối không được can thiệp trong kiến trúc AOP

## 1. Vì sao đây là quyết định kiến trúc quan trọng?

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), một **aspect** gom một mối quan tâm cắt ngang nhiều thành phần, chẳng hạn đo thời gian, ghi log, tracing, kiểm tra quyền hoặc quản lý một chính sách thực thi. **Pointcut** chọn các **join point** mà **advice** được áp dụng. Vì vậy, thiết kế AOP không chỉ là viết logic trong advice; phần quan trọng hơn là xác định **chính xác tập điểm được phép can thiệp** và **tập điểm phải loại trừ**.

Can thiệp quá hẹp khiến một số đường gọi bỏ qua chính sách. Can thiệp quá rộng có thể làm chậm chương trình, lộ dữ liệu, tạo vòng lặp đệ quy trong logging, làm thay đổi ngoại lệ hoặc vô tình thực thi lại tác dụng phụ. Nghiêm trọng hơn, một lời khuyên chung kiểu “áp dụng cho mọi phương thức” có thể bao quanh chính công cụ mà advice cần gọi để hoạt động.

Câu hỏi kiến trúc cần trả lời trước khi viết pointcut:

1. **Chính sách nhằm bảo vệ hoặc quan sát điều gì?** Một nghiệp vụ, một yêu cầu, một giao dịch, một lần retry, một tài nguyên hay một callback?
2. **Join point nào đại diện đúng ranh giới đó?** Method call, method execution, constructor hay điểm khác tùy mô hình AOP?
3. **Có thể thay đổi kết quả không?** Advice chỉ quan sát, có thể từ chối, có thể gọi lại hành vi đích hay có thể thay đổi đầu ra?
4. **Những đối tượng nào tuyệt đối phải loại trừ khỏi pointcut đang xét?** Logger/exporter, công cụ đo chính advice, một số phương thức hạ tầng, code nhạy cảm hoặc phương thức có hợp đồng không chấp nhận việc can thiệp ấy.
5. **Làm cách nào chứng minh điểm đúng được bao phủ và điểm cấm không bị can thiệp?** Phải có test và quan sát cơ chế thực thi thực tế.

**Nguyên tắc:** không có danh sách “mọi AOP đều tuyệt đối cấm” độc lập với loại advice. Một điểm rất phù hợp cho tracing có thể không phù hợp cho retry; một thao tác nghiệp vụ thích hợp cho kiểm tra quyền vẫn có thể không được phép để advice tự sửa kết quả. Do đó, phải định nghĩa các *vùng cấm theo từng chính sách*. Một số bất biến về bảo mật và tính đúng đắn phải được bảo vệ tại ranh giới đáng tin cậy, bất kể AOP có hoạt động hay không.

## 2. Phân biệt nơi áp dụng, nơi không áp dụng và nơi chưa xác minh

Khi đánh giá một join point, nên phân thành ba trạng thái thiết kế:

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| **ALLOW / áp dụng** | Có lý do rõ ràng để advice chạy; hành vi được phép thay đổi trong phạm vi hợp đồng | Đưa vào pointcut có chủ đích, có test |
| **DENY / loại trừ** | Advice được xét có thể gây đệ quy, sai ngữ nghĩa, rủi ro bảo mật hoặc effect không an toàn | Loại trừ tường minh và kiểm thử không bị intercept |
| **REVIEW / chưa kết luận** | Thiếu thông tin về kiểu join point, tác dụng phụ, transaction, async hoặc khả năng weave | Không mở rộng pointcut đến khi có bằng chứng |

Ví dụ:

- **Timing advice**: phù hợp với các entry point nghiệp vụ có thời lượng đáng quan tâm; có thể cần loại trừ chính bộ ghi metric để tránh recursion và đo lường nhiễu.
- **Retry advice**: chỉ áp dụng khi đã xác định lỗi retryable và effect được thiết kế an toàn khi lặp; phải loại trừ các thao tác không idempotent chưa có chống trùng.
- **Authorization advice**: phù hợp ở các ranh giới yêu cầu quyền; nhưng không được coi đó là rào chắn duy nhất nếu đường gọi có thể bypass interception.
- **Transaction advice**: phù hợp quanh một đơn vị công việc giao dịch; không tự bao phủ mọi tài nguyên ngoài giao dịch, và không nên mở transaction kéo dài qua khoảng chờ backoff một cách vô ý.
- **Result-recording advice**: phải đứng ở đúng ranh giới outcome; không ghi “committed” khi transaction chưa commit hoặc “async success” khi phương thức mới trả về future.

Quyết định ALLOW/DENY/REVIEW cần ghi **lý do và loại advice**, tránh một nhãn “không AOP” mơ hồ áp lên toàn bộ hệ thống.

## 3. Bắt đầu từ concern và đơn vị đo, không bắt đầu từ tên package

Một cách tiếp cận thiếu an toàn là chọn toàn bộ một package rồi áp cùng một advice cho mọi phương thức. Cách này dễ tạo phạm vi can thiệp ngoài dự kiến khi thêm lớp hoặc refactor.

Hãy định nghĩa mối quan tâm trước:

- **Quan sát yêu cầu:** ranh giới từ tiếp nhận đến trả kết quả; cần biết một request có thể qua nhiều hàm con và callback.
- **Quan sát nghiệp vụ:** ranh giới thao tác logic như đặt hàng hoặc duyệt tài liệu; một phương thức có thể chỉ khởi tạo tác vụ nên chưa đại diện completion.
- **Đếm truy cập dữ liệu:** chọn những operation đã được định nghĩa rõ; tránh mỗi getter nhỏ đều tạo một event.
- **Kiểm soát quyền:** chọn các entry point nhạy cảm và ranh giới thực thi effect; đảm bảo quyền dựa trên principal, action, resource đáng tin cậy.
- **Chính sách retry:** chọn toàn operation có thể lặp an toàn hoặc một bước có semantics lặp rõ ràng, không chỉ vì phương thức có thể ném exception.
- **Giao dịch:** chọn đơn vị cập nhật dữ liệu cần commit/rollback đồng bộ, với quy tắc propagation rõ ràng.

Một đơn vị nghiệp vụ thường có ranh giới quan sát tốt hơn các phương thức nhỏ như getX(), setY(), hashCode() hoặc toString(). Tuy nhiên, nếu cần instrument một nhóm hàm nhỏ phục vụ profiling chuyên sâu, đó vẫn có thể là quyết định có chủ đích và được kiểm soát hiệu năng.

## 4. Phân tích điểm can thiệp thật sự có sẵn

Mô hình AOP không đồng nhất. Không được xây quy tắc kiến trúc dựa trên giả định rằng mọi lời gọi Java đều có thể bị bắt.

### 4.1. Proxy-based interception

Một proxy nhận lời gọi rồi có thể chạy advice trước khi chuyển tiếp đến target:

~~~text
caller ---> proxy [advice] ---> target.method()
caller -----------------------> target.method()  (đường trực tiếp)
~~~

Nếu một đối tượng khác giữ tham chiếu tới **target gốc**, nó có thể gọi trực tiếp và không qua proxy. Một số hình thức **self-invocation** trên chính target cũng không quay lại proxy. Cơ chế proxy qua interface, subclass hoặc adapter có giới hạn khác nhau về method có thể can thiệp.

### 4.2. Weaving tại điểm thực thi hoặc điểm gọi

Một cơ chế weaving có thể ghép advice vào bytecode tại những join point đã chọn. Ví dụ, weaving tại **method execution** có thể bao phủ thực thi phương thức được chọn dù đường vào không qua proxy. Nhưng điều đó phụ thuộc mã nào được weave, classloader nào tải lớp, thời điểm weaving và loại join point mà công cụ hỗ trợ.

Phương thức final/private/static, constructor, method handle, native code và code nạp động cần được đánh giá theo **cơ chế cụ thể**. Không thể khẳng định tất cả loại điểm ấy luôn bị bỏ qua hoặc luôn được hỗ trợ trong mọi AOP.

### 4.3. Cấu hình và thứ tự cũng thuộc phạm vi

Một pointcut hợp lệ về cú pháp chưa bảo đảm runtime đã intercept:

- Có thể không match chữ ký, visibility, kiểu hoặc call site được mong đợi.
- Có thể chưa đăng ký aspect ở build/deployment đang chạy.
- Có thể có lớp không được weave, đối tượng được khởi tạo theo đường khác.
- Có thể advice ngoài cùng trả kết quả mà không gọi proceed(), nên advice bên trong không chạy.
- Có thể chương trình có đường vào khác tới cùng side effect.

**Phải kiểm tra đường gọi ở runtime**, không chỉ nhìn vào việc khai báo aspect.

## 5. Nơi thường phù hợp để áp dụng AOP

### 5.1. Entry point có ý nghĩa nghiệp vụ

Các phương thức ở biên một use case, chẳng hạn placeOrder(), approveDocument() hoặc calculateQuote(), thường thích hợp cho tracing, correlation ID, kiểm tra quyền, đo thời lượng và ghi kết quả.

Ưu điểm là có đơn vị quan sát rõ: một lượt operation, outcome và effect liên quan. Nếu một use case bao gồm nhiều bước bất đồng bộ, cần phân biệt lúc phương thức trả handle với lúc tác vụ thật sự hoàn tất.

### 5.2. Ranh giới truy cập tài nguyên

Có thể dùng aspect để thu thập số liệu truy cập hoặc áp chính sách nhất quán tại các lời gọi tới kho dữ liệu, dịch vụ từ xa, file hoặc hàng đợi. Nhưng phải biết sự kiện được đo là **attempt**, **giao dịch**, **request gửi đi** hay **kết quả đã xác nhận**.

Ví dụ, ghi log “database updated” tại thời điểm phương thức gọi SQL trả về có thể sai nếu transaction chưa commit. Nếu cần khẳng định dữ liệu đã cam kết, phải quan sát mốc commit thực.

### 5.3. Điểm kiểm soát tập trung có đường đi xác định

AOP hữu ích khi một nhóm hành vi phải dùng chung các chính sách như xác thực ngữ cảnh, logging cấu trúc, chuẩn hóa lỗi hoặc kiểm tra điều kiện kỹ thuật. Điều kiện là tập join point được quản lý chặt và không có đường bypass quan trọng.

Với chính sách bảo mật, điểm can thiệp có thể giúp giảm lặp, nhưng **nguồn tin cậy và cưỡng chế quyền** phải tồn tại tại ranh giới phù hợp với tài nguyên, không dựa duy nhất vào sự may mắn rằng lời gọi luôn qua proxy.

### 5.4. Các thao tác có hợp đồng retry/idempotency rõ

Retry advice phù hợp với một số thao tác đọc không tạo effect, hoặc thao tác ghi được thiết kế idempotent với khóa ổn định và đối soát kết quả. Nếu retry bao cả giao dịch, mỗi attempt thường cần ranh giới transaction mới theo chính sách của resource manager.

Phải xác định lỗi nào retryable, số attempts, backoff, deadline, cancellation, trạng thái commit chưa chắc chắn và mọi effect ngoài transaction.

## 6. Những vùng phải loại trừ khỏi một số loại advice

Bảng dưới đây là **ma trận theo loại chính sách**; “loại trừ” không có nghĩa cấm mọi hình thức quan sát trong mọi hoàn cảnh.

| Vùng/hoạt động | Advice rủi ro | Vì sao phải loại trừ hoặc xem xét cực kỳ cẩn thận? | Thay thế hoặc điều kiện cho phép |
| --- | --- | --- | --- |
| Chính logger, exporter, metric registry hoặc hàm publish telemetry của aspect | Log/tracing/metrics quá rộng | Advice gọi logger; logger lại match pointcut; gây vòng đệ quy, tràn stack hoặc khuếch đại event | Loại trừ hạ tầng observability, dùng guard chống reentrancy và kiểm thử |
| Hàm mà advice dùng để lấy quyền hoặc truy vấn policy | Authorization advice cùng đường | Guard cần policy evaluator; evaluator lại bị cùng guard chặn, có thể đệ quy hoặc bế tắc | Tách trusted policy engine khỏi pointcut hoặc định nghĩa chain rõ |
| Bộ tạo proxy, weaving, classloader, bootstrap lõi | Advice tổng quát | Hạ tầng cần hoạt động để advice tồn tại; instrumentation không kiểm soát có thể gây lỗi khởi tạo | Giới hạn rõ tập lớp hỗ trợ, kiểm tra vòng phụ thuộc và initialization |
| equals/hashCode/toString hoặc getter rất nhỏ | Retry, transaction, logging tần suất cao | Có thể được gọi vô số lần từ collection/logging; tăng overhead, recursion và làm đổi contract | Chỉ instrument có chủ đích khi có nhu cầu profiling/diagnostics cụ thể |
| Hàm gửi tiền, thanh toán, email hoặc phát event chưa chống trùng | Retry | Mỗi proceed() có thể lặp effect không rollback được | Chỉ retry sau khi có idempotency/deduplication và hiểu failure semantics |
| Method trả future/publisher nhưng advice chỉ bắt return đồng bộ | Transaction, timeout, recorder cuối | Return handle không đồng nghĩa hoàn thành logic; commit/ghi success có thể quá sớm | Dùng cơ chế theo dõi completion và lifecycle tài nguyên tương ứng |
| Hàm dọn dẹp, rollback, close tài nguyên | Retry hoặc observer gây throw | Lặp cleanup có thể không an toàn; lỗi mới có thể che lỗi gốc | Cơ chế cleanup chuyên trách, exception policy rõ |
| Phần cập nhật trạng thái bất biến nghiệp vụ | Advice biến đổi kết quả hoặc skip | Có thể bỏ qua validation/authorization và invariant cốt lõi | Đưa bất biến bắt buộc vào domain/resource boundary đáng tin |
| API có dữ liệu nhạy cảm | Logging đầu vào/đầu ra tự động | Có thể lộ token, thông tin cá nhân hoặc payload mật | Chỉ ghi trường allowlisted; redaction theo hợp đồng |
| Code nền chạy trước lúc cấu hình context sẵn sàng | Context/authorization phụ thuộc ThreadLocal | Thiếu principal hoặc mang context cũ | Khởi tạo scope đúng, xác định service principal rõ ràng |
| Thread pool, scheduler, callback/worker chung | Advice giữ state mutable/thread-bound | Có thể rò context giữa các request hoặc giải phóng tài nguyên sai thời điểm | Snapshot bất biến, bind/restore per-task, instrument đúng nơi execute |
| Native/external code không thuộc tập join point | Policy dựa hoàn toàn vào interception | Chính sách có thể không chạy | Dùng guard ở API/tài nguyên đáng tin hoặc adapter kiểm soát đường vào |

Một quy tắc có tính **bắt buộc** đối với kiến trúc là: *không được để những hành vi nhạy cảm dựa hoàn toàn vào một interceptor mà đường thực thi có thể bỏ qua*. Điều này khác với việc cấm tuyệt đối mọi advice tại chính hành vi đó.

## 7. Chống đệ quy và vòng phụ thuộc của instrumentation

Một lỗi điển hình:

~~~text
around anyMethod():
    log("enter")
    proceed()
    log("exit")
~~~

Nếu chính log() match pointcut “anyMethod”, chuỗi có thể trở thành:

~~~text
advice for business()
  -> log()
      -> advice for log()
          -> log()
              -> advice for log()
                  ...
~~~

Hậu quả có thể là StackOverflowError, treo ứng dụng, log storm hoặc tiêu thụ tài nguyên lớn. Tương tự nếu metric collector, exporter, tracer, cache hay authorization evaluator nằm trong cùng tập điểm bị instrument.

### 7.1. Ưu tiên loại trừ tường minh

Thiết kế pointcut có danh sách ALLOW theo hành vi đích cùng danh sách DENY đối với hạ tầng:

~~~text
selectedJoinPoints =
    businessOperationExecution
    AND NOT telemetryImplementation
    AND NOT policyEvaluatorInternals
    AND NOT instrumentationBootstrap
~~~

Đây là **biểu thức khái niệm**, không phải cú pháp cụ thể. Tên các khối cần được ánh xạ thành pointcut của mô hình AOP được chọn.

### 7.2. Reentrancy guard chỉ là lớp dự phòng

Có thể dùng cờ theo scope để tránh advice xử lý lặp trên chính thread hoặc chuỗi gọi mà nó tạo ra. Nhưng guard phải có finally để khôi phục trạng thái. Guard dựa trên ThreadLocal không tự bảo vệ callback trên thread khác; một số hệ thống cần context propagation riêng.

Một guard chống reentrancy có thể vô tình che event hợp lệ ở lời gọi lồng nhau. Vì vậy cần phân biệt **đệ quy không chủ đích của instrumentation** với **lời gọi nghiệp vụ lồng nhau hợp lệ**. Ưu tiên thiết kế pointcut đúng rồi dùng guard như một biện pháp phòng vệ bổ sung.

### 7.3. Tách luồng dữ liệu quan sát

Nếu mọi lần ghi metric đi ngược qua cùng pipeline được instrument, hệ thống có thể tự khuếch đại. Cần thiết kế telemetry path có phạm vi riêng, cơ chế giới hạn tải và chính sách xử lý lỗi observer. Dữ liệu quan sát không nên phụ thuộc vào chính dữ liệu quan sát đến mức tạo vòng không có điểm dừng.

## 8. Giữ nguyên hợp đồng của những phương thức không cho phép thay đổi

Một số method có hợp đồng rất nhạy cảm về tính thuần, tính quyết định hoặc không có side effect. Ví dụ:

- equals() phải thể hiện quan hệ tương đương thích hợp, nhất quán với hashCode().
- hashCode() nên ổn định khi trạng thái dùng để tính hash không đổi.
- toString() có thể được gọi từ công cụ log; lời gọi này không nên tạo effect nghiệp vụ nguy hiểm.
- Các getter hoặc phép toán số học thuần có thể được dùng trong thuật toán có giả định chặt về độ trễ và lỗi.

Một advice chỉ đo thời lượng một cách an toàn có thể chấp nhận được trong profiling, nhưng advice **retry**, **cache có biến đổi dữ liệu**, **ghi effect bắt buộc**, **thay thế giá trị** hoặc **ném lỗi mới** có thể phá hợp đồng phương thức.

Không có nghĩa tất cả những method này tuyệt đối không bao giờ được instrument: một profiler có thể cần chúng. Nhưng chính sách can thiệp phải được chứng minh không làm mất các bất biến về ý nghĩa, hiệu năng và tài nguyên của chúng.

### 8.1. Không dùng AOP để “vá” bất biến lõi một cách vô hình

Ví dụ một thao tác chuyển tiền phải bảo đảm số dư đủ, tài khoản hợp lệ và hạn mức không bị vượt. Nếu chỉ đặt kiểm tra trong advice, một đường gọi không qua proxy/weaving có thể bỏ qua tất cả.

Bất biến nghiệp vụ cần được bảo vệ ở ranh giới thực hiện effect hoặc trong giao dịch/resource layer thích hợp. AOP có thể bổ sung đo lường, trace và tái sử dụng một số kiểm tra, nhưng không được biến nó thành điểm thất bại đơn duy nhất cho tính đúng đắn cốt lõi.

## 9. Loại advice quyết định mức can thiệp được phép

### 9.1. Before advice

Before advice thường làm việc **trước** hành vi đích: kiểm tra tham số kỹ thuật, ghi sự kiện bắt đầu hoặc quyết định từ chối nếu chính sách cho phép. Rủi ro là side effect của before advice có thể xảy ra ngay cả khi hành vi đích thất bại hoặc bị từ chối ở lớp trong.

### 9.2. After returning advice

Thấy một lượt thực thi trả về bình thường; không tự có nghĩa nghiệp vụ đã commit hoặc future đã hoàn tất. Nếu cần đo “operation success”, phải xác định mốc completion thực tế.

### 9.3. After throwing advice

Có thể thấy ngoại lệ được ném đồng bộ từ join point theo ngữ nghĩa mô hình. Không tự thấy lỗi được gửi qua CompletionStage, callback hoặc terminal signal về sau.

### 9.4. After/finally advice

Phù hợp dọn scope ngắn hạn nếu nó bao quanh đúng lifecycle. Nhưng “finally của lời gọi tạo future” có thể chạy khi công việc nền vẫn tiếp tục. Không đóng tài nguyên mà worker còn sử dụng chỉ vì phương thức tạo future đã return.

### 9.5. Around advice

Có quyền lực lớn nhất: có thể không gọi proceed(), gọi một lần, gọi nhiều lần, thay exception, thay giá trị trả về hoặc thay đổi thời điểm thực thi. Đây là nơi cần kiểm soát nghiêm nhất.

Đối với các operation không được phép retry hoặc skip, hợp đồng của around advice phải được quy định rõ như:

~~~text
- proceed() đúng một lần
- không thay đổi danh tính/cấu trúc giá trị trả về
- không nuốt ngoại lệ của target
- observer failure không thay outcome của nghiệp vụ
- không kéo dài hoặc đóng sai lifecycle tài nguyên
~~~

Nếu có chính sách chủ đích cho phép khác đi, như cache/fallback/retry, phải chứng minh điều kiện tương ứng và ghi rõ trong thiết kế.

## 10. Tương tác giữa nhiều aspect: nơi được can thiệp thay đổi theo thứ tự

Các advice có thể lồng nhau:

~~~text
Outer(Middle(Inner(operation)))
~~~

Lớp ngoài đi vào trước và ra sau. Nếu một advice ngoài **không gọi proceed()**, toàn bộ advice phía trong có thể bị bỏ qua. Vì vậy, bảng pointcut đúng vẫn có thể không đủ nếu thứ tự áp dụng không phù hợp.

### 10.1. Kiểm tra quyền và cache

~~~text
Cache(Authorization(readPrivateData))
~~~

Khi cache hit, Cache có thể trả dữ liệu mà không chạy Authorization bên trong. Với dữ liệu riêng tư, đây là vùng phải review nghiêm ngặt. Cần đảm bảo guard bao phủ cả cache hit/miss, cache key gắn đúng context, và mọi tài nguyên được bảo vệ ở ranh giới tin cậy.

### 10.2. Retry và giao dịch

~~~text
Retry(Transaction(operation))
~~~

Nếu Transaction thực sự tạo giao dịch mới mỗi lần proceed(), mỗi attempt có scope commit/rollback riêng.

~~~text
Transaction(Retry(operation))
~~~

Mọi attempt có thể nằm trong cùng transaction; sau lỗi đầu, transaction có thể trở thành rollback-only hoặc aborted. Đặc biệt không nên để backoff dài làm giữ lock trong transaction mà không có chủ ý.

Một pointcut retry đúng **không được mặc nhiên áp vào mọi method ghi dữ liệu**. Nó phải đi cùng idempotency và trạng thái commit.

### 10.3. Recorder và lỗi telemetry

~~~text
Retry(RecordAttempt(Transaction(operation)))
~~~

Nếu RecordAttempt ném lỗi sau khi transaction đã commit, Retry có thể vô tình chạy lại nghiệp vụ chỉ vì recorder gặp sự cố. Với log/metric best effort, cần cô lập lỗi observer. Nếu recorder bắt buộc, phải định nghĩa một chính sách lỗi và transactional consistency riêng.

### 10.4. Fallback và kiểm tra quyền

~~~text
Fallback(Authorization(operation))
~~~

Nếu Fallback bắt luôn lỗi từ chối quyền và tạo một đường chạy thay thế có tác dụng phụ, nó có thể làm vô hiệu hóa chính sách. Fallback cần phân loại exception, không tự áp cho authorization errors.

## 11. Một ví dụ Java 17+: can thiệp có chọn lọc và loại trừ telemetry

Ví dụ dùng Java Dynamic Proxy để **mô phỏng một interceptor áp dụng có chủ đích**. Chỉ phương thức được gắn annotation @Observed trên interface mới được advice quan sát. Hai phương thức health() và emitMetric() không thuộc pointcut; đặc biệt emitMetric() phải được loại khỏi advice ghi metric để tránh instrumentation tự gọi lại chính nó.

Đây là ví dụ về **phạm vi interception**, không phải lời khuyên biến annotation thành quy tắc bảo mật tự động hay một ví dụ bytecode weaving tổng quát.

Tạo file **SelectiveAspectDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class SelectiveAspectDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed {}

    interface Operations {
        @Observed
        String execute(String input);

        String health();

        void emitMetric(String event);
    }

    static final class RealOperations implements Operations {
        @Override
        public String execute(String input) {
            System.out.println("business execute " + input);
            return "done-" + input;
        }

        @Override
        public String health() {
            System.out.println("business health");
            return "UP";
        }

        @Override
        public void emitMetric(String event) {
            System.out.println("metric " + event);
        }
    }

    static Object invokeTarget(
            Object target, Method method, Object[] arguments) throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException error) {
            throw error.getCause();
        }
    }

    public static void main(String[] args) {
        RealOperations target = new RealOperations();

        Operations proxy = (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[]{Operations.class},
                (instance, method, arguments) -> {
                    if (!method.isAnnotationPresent(Observed.class)) {
                        return invokeTarget(target, method, arguments);
                    }

                    System.out.println("advice before execute");
                    try {
                        Object result = invokeTarget(
                                target, method, arguments);
                        System.out.println("advice after execute");

                        // emitMetric KHÔNG thuộc tập method được quan sát.
                        // Gọi trực tiếp target giúp demo tránh vòng proxy.
                        try {
                            target.emitMetric("execute.success");
                        } catch (RuntimeException ignored) {
                            // Telemetry best effort trong demo.
                        }
                        return result;
                    } catch (Throwable error) {
                        System.out.println("advice observed failure");
                        throw error;
                    }
                });

        System.out.println("caller=" + proxy.execute("A"));
        System.out.println("health=" + proxy.health());
        proxy.emitMetric("manual");
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac SelectiveAspectDemo.java
java SelectiveAspectDemo
~~~

Stdout chính xác:

~~~text
advice before execute
business execute A
advice after execute
metric execute.success
caller=done-A
business health
health=UP
metric manual
~~~

Phân tích:

1. execute() có @Observed trong interface; InvocationHandler chạy advice, sau đó chuyển lời gọi tới target.
2. health() không match, vì vậy không có dòng “advice before/after” cho lời gọi health.
3. emitMetric() cũng không match. Dòng “metric manual” được in mà không kích hoạt advice.
4. Advice có thể phát metric mà không tự lặp vô hạn qua chính pointcut của nó.
5. Demo giữ nguyên giá trị trả về “done-A” và chỉ quan sát, không retry, không cache, không thay đổi kết quả.

**Giới hạn:** Java Dynamic Proxy của ví dụ là một dạng interception qua interface; lời gọi trực tiếp target không đi qua proxy. Trong production, không nên tùy tiện truy cập target thô ở các đường nghiệp vụ nhạy cảm. Ví dụ gọi target.emitMetric() trực tiếp để minh họa vùng telemetry được cô lập, không phải mẫu cho phép bỏ kiểm soát quyền.

Ví dụ cũng cố ý chỉ in log/metric đơn giản. Một hệ thống đo lường thật cần thêm giới hạn dữ liệu, quản lý lỗi ghi log, xử lý cạnh tranh, context và thiết kế quan sát bất đồng bộ.

## 12. Xác định vùng cấm bằng chính sách pointcut

Một pointcut nên có **điều kiện dương** xác định công việc cần bao phủ và **điều kiện âm** dành cho các phần đã biết phải loại.

Mẫu giả mã độc lập công cụ:

~~~text
observedBusinessOperation(joinPoint) =
    matchesApprovedBusinessBoundary(joinPoint)
    AND NOT matchesTelemetryInternals(joinPoint)
    AND NOT matchesAdviceInfrastructure(joinPoint)
    AND NOT matchesBootstrapOrLifecycleInternals(joinPoint)
    AND NOT isExplicitlyExcluded(joinPoint)
~~~

Tùy loại advice, còn có điều kiện:

~~~text
retryableOperation(joinPoint) =
    explicitlyRetryApproved(joinPoint)
    AND hasDefinedRetryableFailurePolicy(joinPoint)
    AND hasSafeRepeatedEffectContract(joinPoint)
    AND NOT isCleanupOrCompensation(joinPoint)
~~~

~~~text
authorizationBoundary(joinPoint) =
    handlesProtectedActionAndResource(joinPoint)
    AND canResolveTrustedPrincipal(joinPoint)
    AND canDenyBeforeSensitiveEffect(joinPoint)
~~~

Các biểu thức trên chỉ trình bày **ý tưởng policy**, không thay thế việc xác minh ngữ nghĩa pointcut trong công cụ đang dùng. Đặc biệt, điều kiện “has safe effect contract” không phải điều mà một engine AOP bất kỳ tự nhận biết được; nó phải được chứng minh từ thiết kế và kiểm thử.

### 12.1. Allowlist và denylist

**Allowlist** là danh sách ranh giới được phê duyệt: tên operation, annotation có nghĩa rõ ràng, package/module ổn định hoặc tập signature đã kiểm toán.

**Denylist** loại trừ các vùng nguy hiểm: instrumenter, exporter, phương thức lifecycle và những loại thao tác mà advice tương ứng không được đụng tới.

Hai lớp nên bổ trợ nhau: allowlist thu hẹp phạm vi theo mục đích; denylist phòng ngừa các vùng chắc chắn không an toàn. Chỉ dựa vào denylist trên pointcut “mọi method” dễ bỏ sót những thành phần mới chưa biết; chỉ dựa vào allowlist nhưng không xác minh proxy/weaving có thể bỏ qua những đường cần được bảo vệ.

### 12.2. Quyền thay đổi danh sách áp dụng

Với aspect có thể làm thay đổi hành vi (authorization, retry, transaction, fallback), việc thêm một method vào allowlist không phải thay đổi trang trí. Cần review:

- Effect và mức độ nhạy cảm.
- Phạm vi transaction và async.
- Loại lỗi, giá trị trả về.
- Rủi ro lặp, skip hoặc can thiệp sai lifecycle.
- Test chứng minh pointcut match đúng method và không match vùng cấm.

Tài liệu kiến trúc nên chỉ rõ **owner của policy** và cách đánh giá thay đổi đó.

## 13. Bảo mật: nơi không được chỉ dựa vào advice

Với ranh giới truy cập nhạy cảm, câu “tuyệt đối không được can thiệp” có hai nghĩa khác nhau:

1. **Không được đưa vào một advice nguy hiểm**, như retry không idempotent hoặc log payload bí mật.
2. **Không được để một thao tác nhạy cảm chỉ phụ thuộc vào advice để cưỡng chế quyền**, khi có khả năng đường gọi bỏ qua interceptor.

Một phép kiểm tra quyền đáng tin cậy cần thông tin về **principal**, **action**, **resource** và **ngữ cảnh** đã được xác minh. Nếu một worker, job, callback hoặc caller khác có thể gọi thẳng target, việc kiểm tra ở proxy bên ngoài không đủ.

Những điểm cần xét:

- Self-invocation không qua proxy trong một số mô hình.
- Caller giữ target gốc hoặc tự tạo object không có interceptor.
- Pointcut chỉ match interface nhưng đường gọi thực tế dùng method ngoài interface.
- Method không có khả năng override dưới cơ chế subclass proxy.
- Code không được weave hoặc không được instrument tại thời điểm chạy.
- Cache hoặc fallback trả kết quả trước khi guard bên trong có cơ hội chạy.
- Background worker chạy với context thiếu danh tính hoặc dùng principal đã lỗi thời.

Không thể tuyên bố một hệ thống an toàn chỉ vì “annotation đã có”. Hãy kiểm tra điều kiện quyền tại ranh giới có khả năng ngăn **effect thực sự**, bổ sung kiểm soát ở tài nguyên khi thích hợp, và kiểm thử các đường vào khác nhau.

### Dữ liệu nhạy cảm và log

Một advice ghi đối số/tất cả giá trị trả về có thể thu thập mật khẩu, secret, token, dữ liệu sức khỏe, thông tin thanh toán hoặc dữ liệu cá nhân. Do vậy cần policy dữ liệu tách khỏi pointcut:

- Chỉ ghi trường được phép bằng allowlist.
- Loại bỏ hoặc che thông tin nhạy cảm theo hợp đồng.
- Hạn chế kích thước, retention và phạm vi chia sẻ.
- Kiểm tra lỗi format/toString có thể tiết lộ dữ liệu hoặc sinh effect.
- Không ghi mặc định toàn bộ payload chỉ vì aspect có thể lấy nó.

## 14. Ngữ cảnh, thread và bất đồng bộ quyết định nơi kết thúc advice

Khi method trả về một Future hoặc CompletionStage, around advice thường hoàn tất lượt **gọi phương thức** khi nhận handle. Tác vụ logic có thể kết thúc trên thread khác muộn hơn.

~~~text
t0 advice before
t1 method tạo future
t2 method trả future
t3 advice after return
...
t4 future complete/fail/cancel
~~~

Nếu mục tiêu là đo thời gian **invocation**, t0–t3 có thể đúng. Nếu mục tiêu là đo **operation end-to-end**, việc ghi success tại t3 là quá sớm.

Một số rủi ro:

- Transaction bị đóng trong finally ở t3 nhưng worker còn đang dùng tài nguyên đó.
- ThreadLocal chứa correlation/principal bị xóa trước khi task capture context.
- Không khôi phục ThreadLocal ở worker sau callback khiến tác vụ sau dùng context cũ.
- Timeout chỉ dừng chờ, nhưng task vẫn đang chạy và có thể tạo effect.
- Publisher có nhiều subscription; mỗi subscription có ranh giới khác nhau, không có một completion duy nhất cho mọi người dùng.

**Quyết định áp dụng:** instrument ở đúng ranh giới thực thi phù hợp (ví dụ nơi worker thực sự chạy) hoặc theo dõi completion qua hợp đồng async của API. Không kéo dài thread-bound resource tùy ý qua callback chỉ để làm cho một advice “bao đủ” thao tác.

## 15. Tác dụng phụ, retry và transaction: vùng không được phép lặp mù

Nếu advice retry có quyền gọi proceed() nhiều lần, mọi effect trong phạm vi ấy phải được kiểm tra:

| Tác dụng phụ | Nếu proceed() chạy nhiều lần | Ranh giới an toàn cần có |
| --- | --- | --- |
| Đọc dữ liệu thuần | Chủ yếu tăng tải, có thể đọc phiên bản khác | Deadline, retry budget, consistency phù hợp |
| Ghi bản ghi database | Có thể tạo bản ghi trùng, tăng counter nhiều lần | Transaction và idempotency/unique key |
| Chuyển tiền | Có thể thu/chuyển nhiều lần | Idempotency key bền, reconciliation |
| Gửi email | Có thể gửi nhiều bản | Outbox, event ID, deduplication |
| Công bố message | Có thể phát trùng hoặc sai thứ tự | Outbox/consumer idempotency, sequencing |
| Tạo audit event | Có thể đếm trùng hoặc mất bản ghi | Cấp độ audit rõ, độ bền và khóa chống trùng |
| Cleanup/compensation | Có thể hoàn tác hai lần hoặc phá trạng thái | Hợp đồng idempotent riêng, chính sách lỗi cụ thể |

Một transaction database không tự rollback email, thanh toán ngoài hay message đã rời tiến trình. Nếu commit trả lỗi không chắc chắn, retry không có idempotency có thể gây effect trùng ngay cả khi attempt trước đã commit.

Không đưa method có effect nguy hiểm vào pointcut retry vì thấy nó dùng cùng annotation hoặc cùng package. Chỉ mở rộng khi operation đã có hợp đồng chống lặp rõ ràng và được kiểm thử bằng tình huống crash, timeout, commit unknown.

## 16. Hiệu năng và độ tin cậy: tránh can thiệp mọi lời gọi nhỏ

Một method có thể được gọi hàng triệu lần, ví dụ equals(), hashCode(), các getter nhỏ, serializer hoặc vòng lặp tính toán. Advice trước/sau mỗi lượt có thể gây:

- Thời gian overhead vượt quá phần việc thật.
- Tăng cấp phát object/context, áp lực garbage collection.
- Tranh chấp lock/bộ đếm tập trung.
- Log/trace cardinality quá cao và lưu trữ đắt.
- Sai kết quả đo do chính đo lường chiếm phần lớn thời gian.
- Reentrancy khi formatter hoặc logger gọi lại phương thức bị instrument.

Nếu cần profiling sâu, hãy đặt **mục tiêu, sampling và giới hạn hiệu năng**, có chiến lược tắt/giảm instrumentation và đo overhead. Điều này khác với dùng cùng một pointcut rộng trong đường production bình thường.

Một số advice cần tuyệt đối không block trong luồng latency-sensitive theo hợp đồng. Nếu ghi log qua exporter chậm, phải quyết định rõ overflow policy: drop, backpressure hay fail operation. Với telemetry best effort, việc exporter lỗi không nên trở thành lỗi nghiệp vụ.

## 17. Vòng đời tài nguyên: nơi phải tránh can thiệp không đúng thời điểm

Trong hệ thống có connection, lock, file handle, transaction hoặc scope context, advice có thể nắm một ranh giới ngắn hơn hoặc dài hơn vòng đời tài nguyên thực.

Ví dụ:

~~~text
around method:
    open resource
    future = proceed()
    close resource
    return future
~~~

Nếu future tiếp tục dùng resource, close xảy ra quá sớm. Ngược lại, nếu advice giữ resource mãi cho tới khi một event hoàn tất không bảo đảm được gửi, có thể rò tài nguyên.

Cần xác định:

1. Ai sở hữu resource?
2. Resource được dùng bởi thread/callback nào?
3. Tín hiệu nào chứng minh mọi thao tác sử dụng đã xong?
4. Có đường throw đồng bộ, exception async, timeout, cancel hoặc shutdown không?
5. Cleanup lỗi có che nguyên nhân lỗi nghiệp vụ không?
6. Có transaction nào đã ở trạng thái rollback-only hoặc kết thúc trước khi advice giả định không?

Các điểm như close(), rollback(), unlock(), cleanup() không nhất thiết cấm mọi instrumentation, nhưng phải **loại khỏi retry hoặc advice thay đổi thực thi** nếu không có hợp đồng cho phép gọi lặp và không phá tính an toàn.

## 18. Kiểm thử đúng nơi áp dụng và đúng vùng cấm

Một test chỉ thấy phương thức nghiệp vụ trả kết quả đúng là chưa đủ. Phải kiểm tra **advice có chạy ở nơi được chọn và không chạy ở nơi bị loại**.

### 18.1. Kiểm thử độ bao phủ dương tính

- Với operation thuộc allowlist, xác minh advice chạy đúng số lần.
- Nếu có authorization, xác minh quyền được kiểm tra trước side effect.
- Nếu có transaction, xác minh begin/commit/rollback đúng thứ tự thực tế.
- Nếu có recorder cuối, xác minh outcome phản ánh cả commit hoặc async completion theo hợp đồng.
- Nếu có retry, xác minh số attempts và các lần tạo transaction phù hợp.

### 18.2. Kiểm thử vùng loại trừ

- Gọi trực tiếp logger, exporter hoặc emitMetric(), xác minh không kích hoạt advice đang dùng nó.
- Gọi health(), infrastructure utility và method bị đánh dấu loại trừ; xác minh không có thêm advice.
- Kiểm tra equals()/hashCode()/toString() nếu chúng nằm trong vùng cấm của pointcut liên quan.
- Nếu có cơ chế proxy, kiểm tra self-invocation, target thô và các đường khởi tạo khác.
- Nếu có weaving, kiểm tra class/method thực sự được weave trong build đang triển khai.
- Khi cache hit hoặc fallback, kiểm tra có bỏ qua guard/recorder bắt buộc hay không.

### 18.3. Kiểm thử lỗi và ảnh hưởng phụ

Dùng fault injection ở các điểm:

- Lỗi target trước khi có effect.
- Lỗi sau khi effect bên ngoài đã xảy ra.
- Commit thất bại hoặc không rõ kết quả.
- Logger/metric exporter ném exception.
- Retry sau timeout, cancellation trong lúc worker vẫn chạy.
- Nhiều request đồng thời, nhiều callback hoặc task dùng lại thread.

Một chính sách chỉ được chấp nhận khi test xác minh **kết quả, lỗi, số lượt effect, thứ tự sự kiện và bảo toàn tài nguyên**, không chỉ assert một exception được ném.

### 18.4. Test ma trận

| Nhóm đường | Expected ALLOW | Expected DENY | Tín hiệu cần quan sát |
| --- | --- | --- | --- |
| Business entry point | Tracing/metric operation | Advice không liên quan | Event bắt đầu/kết thúc đúng scope |
| Telemetry exporter | Hoạt động bình thường | Chính advice đang gọi exporter | Không recursion, một lần ghi |
| Authorization boundary | Guard chạy | Bypass guard | Principal/action/resource và không có effect trái quyền |
| Sensitive mutation | Transaction thích hợp | Retry thiếu idempotency | Commit/rollback và số side effect |
| Async worker | Context/guard đúng lúc thực thi | Giả định chỉ method submit đã đủ | Completion outcome và context khôi phục |
| Cleanup/lifecycle | Dọn dẹp chuẩn | Retry/biến đổi không được duyệt | Resource release đúng một lần theo hợp đồng |

## 19. Quy trình ra quyết định theo kiến trúc

Có thể thực hiện qua chín bước:

**Bước 1 — Liệt kê concern.** Phân biệt observability, security, transaction, retry, caching, fallback và lifecycle. Không gom tất cả thành một “general aspect”.

**Bước 2 — Xác định hợp đồng hành vi.** Method có side effect không? Có thể gọi lặp hoặc skip không? Giá trị trả về có đại diện cho kết quả cuối không?

**Bước 3 — Chọn ranh giới logic.** Chọn operation/service boundary có ý nghĩa, thay vì chọn mọi method trong một package. Với async, xác định cả ranh giới completion.

**Bước 4 — Xác định cơ chế AOP và join point thực sự.** Proxy hay weaving, method call hay execution, ràng buộc method modifier/classloader và đường gọi nội bộ.

**Bước 5 — Tạo bảng ALLOW/DENY/REVIEW theo từng policy.** Ghi rõ phương thức và lý do. Đặc biệt loại trừ hạ tầng của chính advice và các operation không phù hợp retry/transaction.

**Bước 6 — Vẽ thứ tự advice.** Ví dụ RecordFinal(Retry(Transaction(operation))). Xác định lớp nào có thể bỏ qua proceed(), gọi nhiều lần hoặc chuyển đổi lỗi.

**Bước 7 — Xác định ownership và trust boundary.** Tài nguyên sống đến khi nào? Principal có đáng tin cậy? Kiểm tra quyền có điểm cưỡng chế không thể bypass không?

**Bước 8 — Kiểm thử cả điểm được áp dụng và điểm bị loại.** Bao gồm self-call, target trực tiếp, worker, callback, retry, timeout, commit lỗi và telemetry failure.

**Bước 9 — Giám sát và review khi đổi hệ thống.** Mỗi method mới, thay đổi interface, build/weaving scope hoặc đường vào mới đều có thể làm thay đổi tập join point. Phải cập nhật chính sách và test cùng thay đổi.

## 20. Những sai lầm thường gặp

**Sai lầm 1: pointcut chọn toàn bộ package và mọi method.** Khi thêm lớp telemetry hoặc utility, chúng cũng bị can thiệp. Khắc phục bằng allowlist theo hành vi và loại trừ hạ tầng, cùng test độ bao phủ.

**Sai lầm 2: kiểm tra quyền chỉ ở proxy.** Một đường đi tới target gốc hoặc lời gọi nội bộ có thể bypass. Đưa quyết định quyền tới ranh giới thực thi effect đáng tin cậy, rồi dùng AOP hỗ trợ nhất quán.

**Sai lầm 3: retry mọi lời gọi ghi dữ liệu.** Lặp effect ngoài transaction có thể tạo thanh toán/email trùng. Chỉ retry nơi idempotency/đối soát đã được bảo đảm.

**Sai lầm 4: instrument logger của chính aspect.** Tạo vòng đệ quy và tăng tải không kiểm soát. Loại trừ telemetry internals và dùng reentrancy guard khi cần.

**Sai lầm 5: coi method return là task success.** Future có thể hoàn tất lỗi sau khi method trả về. Phải theo dõi đúng completion nếu policy yêu cầu outcome logic.

**Sai lầm 6: xem mọi lỗi là retryable.** Authorization denial, validation failure, business rejection hay lỗi exporter không nên bị retry mù.

**Sai lầm 7: đóng tài nguyên trong finally khi worker vẫn dùng.** Sai ownership/lifecycle. Đặt cleanup tại ranh giới sử dụng cuối thật sự.

**Sai lầm 8: dùng tên annotation thay cho chứng cứ interception.** Một aspect khai báo tồn tại không chứng minh pointcut match và runtime can thiệp mọi đường cần bảo vệ. Cần test trên cơ chế/artefact thực.

**Sai lầm 9: log toàn bộ đối số và kết quả.** Có thể lộ dữ liệu mật, gây chi phí lớn hoặc kích hoạt toString() nguy hiểm. Chỉ ghi metadata allowlisted.

**Sai lầm 10: chỉ kiểm tra nơi phải có advice.** Không kiểm tra nơi **không được** có advice sẽ bỏ sót recursion, chi phí và effect ngoài ý muốn.

## 21. Tình huống tự kiểm tra

**Tình huống A.** Một timing aspect match tất cả method, bao gồm chính MetricsExporter.publish(). Advice gọi publish() để ghi metric. Rủi ro gì?

**Đáp án:** publish() có thể lại kích hoạt timing aspect và gọi publish() tiếp, sinh đệ quy. Cần loại trừ exporter khỏi pointcut và kiểm thử không có reentrancy không mong muốn.

**Tình huống B.** Một retry aspect được gắn cho chargeCard(). Lần đầu phía thanh toán đã ghi nhận giao dịch nhưng caller timeout. Có thể gọi lại an toàn chỉ nhờ transaction database nội bộ không?

**Đáp án:** Không. Transaction database nội bộ không tự rollback effect ở bên thanh toán. Cần idempotency key/kiểm tra kết quả và reconciliation theo hợp đồng.

**Tình huống C.** Authorization advice chạy khi gọi target qua proxy, nhưng bên trong target một method gọi this.delete(). Guard có chắc chạy?

**Đáp án:** Không thể chắc với proxy-based interception. Lời gọi this.delete() có thể không đi qua proxy. Với weaving tại method execution, hành vi có thể khác; phải kiểm chứng join point thực tế và cưỡng chế quyền tại ranh giới đáng tin cậy.

**Tình huống D.** Recorder after-returning thấy một CompletableFuture đã được trả về, rồi log “completed successfully”. Điều gì sai?

**Đáp án:** Lần gọi đã trả handle không có nghĩa future hoàn tất thành công. Muốn đo operation outcome phải quan sát completion của đối tượng kết quả theo hợp đồng.

**Tình huống E.** Một advice caching được đặt ngoài authorization; cache hit trả dữ liệu riêng tư ngay. Cần đánh giá gì?

**Đáp án:** Authorization bên trong có thể bị bỏ qua vì cache không gọi proceed(). Cần kiểm tra quyền cả nhánh hit/miss, key phân vùng đúng và guard dữ liệu nhạy cảm.

**Tình huống F.** Có nên cấm toàn bộ instrumentation trên hashCode()?

**Đáp án:** Không có quy tắc phổ quát. Trong monitoring production thông thường, nên tránh advice tạo effect lớn, retry hay thay đổi kết quả. Một công cụ profiling chuyên biệt vẫn có thể cần đo hashCode() nếu đã kiểm soát overhead và semantics.

**Tình huống G.** Test chỉ assert method nằm trong allowlist được intercept một lần. Đã đủ chưa?

**Đáp án:** Chưa. Cần test vùng loại trừ không bị instrument, đường gọi khác tới same effect không bypass security, và error/async/resource lifecycle đúng.

**Tình huống H.** Một cleanup method ném lỗi khi đóng resource, advice trong finally cũng ném lỗi log. Người gọi có thể mất thông tin gì?

**Đáp án:** Lỗi của observer có thể che mất lỗi cleanup hoặc lỗi nghiệp vụ trước đó. Cần chính sách bảo toàn nguyên nhân/suppressed exception hoặc xử lý observer best effort, tùy hợp đồng.

## 22. Kết luận kỹ thuật

Xác định nơi áp dụng AOP là bài toán **chọn đúng ranh giới hành vi**; xác định nơi không được can thiệp là bài toán **bảo vệ hợp đồng, hiệu năng, an toàn truy cập và vòng đời tài nguyên**. Không nên bắt đầu bằng pointcut quá rộng rồi hy vọng các ngoại lệ sẽ tự được xử lý.

Một thiết kế tốt xác định rõ:

- **ALLOW:** các operation/join point có lý do can thiệp và policy được phê duyệt.
- **DENY:** những thành phần mà loại advice đó có thể gây đệ quy, lặp effect, sai outcome hoặc thay đổi bất biến.
- **REVIEW:** những trường hợp chưa chứng minh được semantics của phương thức, proxy/weaving, transaction hoặc async.
- **VALIDATION:** test độ bao phủ dương tính, vùng loại trừ, đường bypass, thứ tự advice, lỗi và tác dụng phụ.

AOP hữu ích khi các concern cắt ngang được áp dụng có chủ đích. Chất lượng kiến trúc nằm ở việc **nơi được chọn thực sự cần advice, nơi bị loại không vô tình chạy advice và mọi bất biến quan trọng vẫn được bảo vệ ở ranh giới đáng tin cậy**.