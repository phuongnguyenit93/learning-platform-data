# Nhận diện anti-pattern

## 1. Anti-pattern trong thiết kế DSL là gì?

Trong thiết kế ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **anti-pattern** là một cách tổ chức cú pháp, semantics, compiler, runtime hoặc API thường dẫn đến khó hiểu, khó bảo trì, dễ sai hoặc khó mở rộng khi được áp dụng lặp lại.

Một anti-pattern không nhất thiết là một đoạn code sai cú pháp. Nó có thể hoạt động trong ví dụ nhỏ nhưng tạo ra chi phí lớn khi DSL có thêm người dùng, tính năng, plugin hoặc tích hợp.

Ví dụ, một DSL workflow có thể cho phép người dùng gọi bất kỳ method Java nào bằng tên class và tên method dưới dạng string. Cách này có vẻ linh hoạt, nhưng làm mất kiểm tra kiểu, khó giới hạn quyền, phụ thuộc implementation của host và khó phát hiện lỗi trước khi chạy.

Nhận diện anti-pattern là khả năng quan sát triệu chứng, hiểu nguyên nhân và đánh giá hậu quả trong ngữ cảnh cụ thể. Mục tiêu không phải gắn nhãn mọi thiết kế khác biệt là sai, mà là tìm những lựa chọn đang làm giảm chất lượng hoặc cản trở mục tiêu của DSL.

## 2. Vì sao cần nhận diện sớm?

DSL thường nằm giữa domain expert và hệ thống phần mềm. Một quyết định thiết kế có thể ảnh hưởng đồng thời đến:

- Người viết và đọc chương trình DSL.
- Người phát triển compiler và runtime.
- Người tích hợp host API.
- Người viết plugin hoặc extension.
- Người kiểm thử và vận hành.
- Người quản lý version, migration và tài liệu.

Anti-pattern thường tích lũy dần. Một default không rõ ràng ban đầu chỉ gây nhầm lẫn nhỏ; sau này nhiều project phụ thuộc vào nó, khiến thay đổi semantics trở nên khó khăn.

Nhận diện sớm giúp:

1. Giảm lỗi khó chẩn đoán.
2. Giữ cú pháp và semantics nhất quán.
3. Giảm coupling giữa DSL với host application.
4. Bảo vệ ranh giới bảo mật.
5. Giữ compiler và runtime dễ kiểm thử.
6. Hạn chế breaking changes và chi phí migration.
7. Giúp DSL phát triển theo nhu cầu domain thay vì theo cấu trúc implementation tình cờ.

## 3. Cách nhận diện một anti-pattern

Không nên chỉ dựa vào cảm giác rằng code "trông xấu". Hãy xem xét một vấn đề theo các bước:

~~~text
Quan sát triệu chứng
        |
        v
Thu thập ví dụ tái hiện
        |
        v
Xác định nguyên nhân thiết kế
        |
        v
Đánh giá tác động và phạm vi
        |
        v
So sánh với mục tiêu DSL
        |
        v
Chọn thay đổi nhỏ có thể kiểm chứng
        |
        v
Đo lại sau refactor
~~~

### 3.1 Tìm triệu chứng lặp lại

Một lỗi đơn lẻ có thể chỉ là bug. Anti-pattern thường biểu hiện qua nhiều tình huống: người dùng liên tục phải đoán cú pháp, compiler có nhiều nhánh xử lý đặc biệt, plugin phụ thuộc class nội bộ hoặc cùng một quy tắc được triển khai ở nhiều nơi.

### 3.2 Xem xét bối cảnh

Một lựa chọn có thể hợp lý trong DSL nhỏ, chỉ dùng nội bộ, nhưng không phù hợp với ngôn ngữ công khai có nhiều plugin. Cần cân nhắc:

- Quy mô và vòng đời của DSL.
- Trình độ người dùng.
- Mức độ ổn định của domain.
- Tính chất dữ liệu và tác động của execution.
- Yêu cầu hiệu năng và bảo mật.
- Chi phí migration và compatibility.

### 3.3 Tách triệu chứng khỏi nguyên nhân

Ví dụ, nhiều lỗi parser có thể là triệu chứng của grammar mơ hồ, nhưng cũng có thể do diagnostic thiếu ngữ cảnh hoặc test fixture không đủ. Sửa message không giải quyết được ambiguity của grammar.

### 3.4 Dùng bằng chứng

Thu thập ví dụ source, test failure, thời gian compile, số lượng adapter, lỗi runtime, phản hồi người dùng và lịch sử thay đổi. Tránh đề xuất refactor lớn chỉ dựa trên một đoạn code khó đọc.

## 4. Anti-pattern: DSL chỉ là cú pháp khác của ngôn ngữ tổng quát

Một DSL nên diễn đạt khái niệm của domain bằng mô hình phù hợp. Nếu DSL chỉ đổi dấu ngoặc hoặc tên keyword nhưng vẫn buộc người dùng hiểu toàn bộ host language, giá trị chuyên biệt có thể rất thấp.

### Dấu hiệu

- Người dùng phải biết nhiều chi tiết của ngôn ngữ host.
- Cú pháp chỉ là lớp wrapper quanh API tổng quát.
- Tài liệu DSL phải giải thích nhiều quy tắc không liên quan domain.
- Người dùng không thể đọc một chương trình DSL mà không mở implementation.

### Ví dụ

~~~text
execute(
  new WorkflowBuilder()
    .withStep(new ValidateOrder())
    .withStep(new ChargePayment())
    .withRetry(3)
)
~~~

Nếu mục tiêu là mô tả workflow cho domain expert, một dạng khai báo có thể dễ đọc hơn:

~~~text
workflow OrderProcessing {
  step ValidateOrder
  step ChargePayment retry 3
}
~~~

### Hậu quả

DSL không giảm được độ phức tạp nhận thức, khó phân tích tĩnh và khó cung cấp diagnostic theo domain.

### Cách khắc phục

Xác định những khái niệm domain quan trọng, thiết kế cú pháp biểu đạt trực tiếp các khái niệm đó và chỉ mở host-language escape hatch khi có nhu cầu được kiểm soát.

## 5. Anti-pattern: Grammar quá phức tạp

Grammar có thể trở nên khó hiểu khi tích lũy quá nhiều cú pháp tương đương, ngoại lệ và quy tắc ngữ cảnh.

### Dấu hiệu

- Nhiều cách viết cho cùng một ý nghĩa nhưng không có lý do rõ.
- Một production có quá nhiều nhánh đặc biệt.
- Parser phải kiểm tra trạng thái toàn cục để quyết định cách parse.
- Error recovery tạo diagnostic khó đoán.
- Thay đổi nhỏ làm phát sinh ambiguity ở nơi khác.

### Ví dụ

~~~text
when order.total > 100
if order.total > 100
where order.total > 100
condition(order.total > 100)
~~~

Nếu tất cả đều có cùng semantics, người dùng phải học nhiều hình thức và compiler phải duy trì nhiều đường parse.

### Hậu quả

Grammar khó tiến hóa, tài liệu phình to, formatter khó chuẩn hóa và người dùng không biết nên chọn dạng nào.

### Cách khắc phục

- Chọn một dạng canonical.
- Chỉ giữ alias khi có lợi ích rõ, chẳng hạn tương thích với syntax cũ.
- Tách grammar theo module hoặc construct.
- Viết test cho precedence, ambiguity và error recovery.
- Định nghĩa quy tắc deprecation cho cú pháp cũ.

Không nên đơn giản hóa grammar bằng cách loại bỏ một construct đang có semantics khác biệt chỉ vì nó trông giống construct khác.

## 6. Anti-pattern: Syntax mơ hồ và semantics không nhất quán

Syntax mơ hồ khiến người viết không thể dự đoán cách parser hoặc runtime diễn giải chương trình.

### Dấu hiệu

- Một biểu thức có thể được hiểu theo nhiều cách.
- Cùng một keyword có semantics khác nhau ở các context không được giải thích.
- Operator precedence không được công bố.
- Cú pháp chấp nhận một cấu trúc nhưng runtime xử lý khác với cách người dùng kỳ vọng.

### Ví dụ

~~~text
if a + b * c > limit
  ...
~~~

Nếu precedence của phép nhân và phép cộng không rõ, người dùng không biết expression được nhóm như thế nào.

### Hậu quả

Người dùng phải đoán, thêm ngoặc tùy tiện hoặc phát hiện lỗi muộn khi chạy.

### Cách khắc phục

- Công bố precedence và associativity.
- Dùng AST shape rõ ràng.
- Tránh để cùng token mang ý nghĩa phụ thuộc trạng thái ẩn.
- Cung cấp diagnostic khi cấu trúc không hợp lệ.
- Dùng ví dụ biên để kiểm tra semantics.

## 7. Anti-pattern: Implicit conversion quá nhiều

Implicit conversion giúp cú pháp ngắn, nhưng quá nhiều chuyển đổi ngầm khiến semantics khó dự đoán.

### Dấu hiệu

- String tự động biến thành number, date hoặc enum.
- Null tự động biến thành giá trị mặc định.
- Type không tương thích vẫn được chấp nhận qua nhiều bước conversion.
- Hai biểu thức giống nhau có kết quả khác do context conversion.

### Ví dụ

~~~text
let total = "100" + 20
~~~

Người dùng có thể không biết kết quả là chuỗi "10020" hay số 120.

### Hậu quả

Bug logic khó tìm, type checker phức tạp và thay đổi conversion rule có thể phá nhiều chương trình.

### Cách khắc phục

- Định nghĩa conversion matrix.
- Chỉ cho phép implicit conversion an toàn và dễ đoán.
- Dùng explicit conversion cho thay đổi có thể mất dữ liệu.
- Phân biệt null, missing và default.
- Diagnostic nên nói rõ kiểu thực tế và kiểu mong đợi.

## 8. Anti-pattern: Stringly typed DSL

Stringly typed là cách biểu diễn nhiều khái niệm có cấu trúc bằng string tùy ý.

### Dấu hiệu

- Tên trạng thái, loại tài nguyên và operation đều là string.
- Compiler không thể xác nhận tên function hoặc field.
- Sai chính tả chỉ được phát hiện khi chạy.
- Nhiều nơi dùng magic string giống nhau nhưng không có định nghĩa chung.

### Ví dụ

~~~text
call("approveOrder", "ORD-100", "HIGH")
~~~

Một interface có kiểu rõ ràng:

~~~text
orders.approve(
  orderId: OrderId("ORD-100"),
  priority: Priority.HIGH
)
~~~

### Hậu quả

Autocomplete, static validation và refactoring yếu; lỗi chỉ xuất hiện ở runtime.

### Cách khắc phục

Dùng domain type, enum hoặc symbol resolution cho những giá trị có tập nghĩa xác định. String vẫn phù hợp cho text tự do, label hoặc dữ liệu không cần kiểm tra theo danh mục.

## 9. Anti-pattern: Magic value và default ẩn

Một giá trị mặc định không được công bố có thể thay đổi behavior mà người dùng không nhận ra.

### Dấu hiệu

- Thiếu field nhưng runtime tự chọn giá trị.
- Timeout, retry hoặc timezone được lấy từ cấu hình ngầm.
- Cùng source chạy khác nhau theo host hoặc môi trường.
- Người dùng phải hỏi vì sao một rule được đánh giá khác.

### Ví dụ

~~~text
schedule every 1 day
~~~

Nếu "một ngày" có thể là 24 giờ hoặc ngày lịch theo timezone của tenant, semantics phải được định nghĩa.

### Hậu quả

Khó tái lập, khó debug và dễ gây sai lệch giữa môi trường phát triển với production.

### Cách khắc phục

- Công bố default.
- Cho phép cấu hình rõ ở đúng scope.
- Dùng giá trị mặc định an toàn.
- Ghi default đã áp dụng vào execution metadata khi cần.
- Có diagnostic hoặc warning cho cấu hình dễ gây nhầm.

## 10. Anti-pattern: Context toàn cục và trạng thái ẩn

Global mutable state khiến hành vi phụ thuộc vào những lần chạy trước hoặc execution khác.

### Dấu hiệu

- Function DSL đọc biến môi trường hoặc singleton không được truyền tường minh.
- Một tenant thấy dữ liệu của tenant khác.
- Test chỉ pass khi chạy theo một thứ tự nhất định.
- Runtime dùng static map để lưu context của process.
- Một plugin thay đổi configuration ảnh hưởng plugin khác.

### Ví dụ

~~~java
static String currentTenant;

static void execute(String tenant, Program program) {
    currentTenant = tenant;
    program.run();
}
~~~

Hai execution đồng thời có thể ghi đè currentTenant của nhau.

### Cách khắc phục

- Truyền execution context tường minh.
- Ưu tiên immutable context.
- Tách state theo request, tenant hoặc process.
- Xác định thread-safety và lifecycle.
- Viết concurrency test cho context isolation.

## 11. Anti-pattern: Side effect không rõ ràng

Một function trông như phép tính nhưng thực tế lại ghi database, gửi email hoặc phát event là nguồn gây bất ngờ.

### Dấu hiệu

- Function có tên như calculate hoặc lookup nhưng tạo side effect.
- Một biểu thức được đánh giá lại làm command chạy nhiều lần.
- Retry tự động tạo giao dịch lặp.
- Người dùng không biết thao tác nào có thể thay đổi trạng thái ngoài chương trình.

### Ví dụ

~~~text
let result = customer.balance()
~~~

Nếu balance() âm thầm ghi audit hoặc gọi API tính phí, tên function không phản ánh behavior.

### Hậu quả

Khó reasoning, khó cache, khó retry và nguy cơ lặp side effect.

### Cách khắc phục

- Phân biệt query với command.
- Dùng tên thể hiện hành động.
- Định nghĩa side-effect metadata.
- Có idempotency key cho command có thể retry.
- Tách transaction boundary.
- Làm rõ semantics của replay và cancellation.

## 12. Anti-pattern: Compile-time và runtime bị trộn lẫn

Compiler và runtime có trách nhiệm khác nhau. Khi ranh giới không rõ, hệ thống có thể vừa lặp logic vừa bỏ lỡ lỗi sớm.

### Dấu hiệu

- Type checking chỉ diễn ra sau khi bắt đầu execution.
- Runtime phải parse lại source nhiều lần dù không cần.
- Compiler gọi service production để xác định semantics.
- Diagnostic phụ thuộc dữ liệu môi trường không được snapshot.

### Hậu quả

Lỗi xuất hiện muộn, build không tái lập và compile phụ thuộc hệ thống bên ngoài.

### Cách khắc phục

- Đưa cú pháp, symbol và type validation vào compile-time khi có thể.
- Giữ runtime cho evaluation và dữ liệu chỉ có lúc chạy.
- Định nghĩa rõ phần nào cần dynamic lookup.
- Snapshot configuration hoặc capability version ảnh hưởng compilation.
- Không thực hiện side effect khi compile.

Một số DSL cố ý dynamic. Điều quan trọng là phải công bố ranh giới và hệ quả của dynamic behavior.

## 13. Anti-pattern: Runtime reflection không giới hạn

Cho DSL gọi tùy ý class, method hoặc property của host bằng reflection tạo một escape hatch rất rộng.

### Dấu hiệu

- Source chứa tên class hoặc method dưới dạng string.
- Compiler không biết function nào được phép.
- Plugin có thể truy cập object nội bộ.
- Authorization phụ thuộc vào việc method có public hay không.

### Hậu quả

Mất static checking, tăng attack surface, coupling mạnh với host implementation và khó version hóa.

### Cách khắc phục

- Dùng function registry hoặc capability descriptor.
- Công bố signature và return type.
- Áp dụng allowlist.
- Kiểm tra authorization ở runtime.
- Giới hạn reflection ở adapter nội bộ nếu thực sự cần.

## 14. Anti-pattern: Host API bị rò rỉ vào DSL

DSL trở nên phụ thuộc vào framework hoặc model nội bộ của host khi trực tiếp expose object của ứng dụng.

### Dấu hiệu

- DSL phải biết ORM entity, servlet request hoặc UI widget.
- Một thay đổi framework buộc sửa source DSL.
- Cùng một DSL không thể chạy trong môi trường khác.
- Plugin phụ thuộc package nội bộ không được hỗ trợ.

### Hậu quả

Khó kiểm thử, khó thay host, khó nâng cấp framework và khó xác định public contract.

### Cách khắc phục

- Thiết kế domain-oriented host API.
- Dùng DTO hoặc immutable value object.
- Dùng adapter/anti-corruption layer.
- Công bố capability và API version.
- Chỉ expose dữ liệu cần thiết cho domain.

## 15. Anti-pattern: Một abstraction tổng quát cho mọi thứ

Một interface hoặc object lớn có thể trở thành nơi chứa mọi function, state và dependency.

### Dấu hiệu

- Một HostContext có hàng trăm method.
- Mọi module đều phụ thuộc vào ApplicationService.
- Một thay đổi nhỏ yêu cầu sửa nhiều thành phần.
- Quyền truy cập không thể cấp theo capability nhỏ.

### Hậu quả

Coupling cao, test khó, permission rộng và ownership không rõ.

### Cách khắc phục

Chia interface theo domain/capability như OrderReader, PaymentCommands, AuditSink hoặc ResourceResolver. Giữ API nhỏ và tập trung, nhưng không chia nhỏ đến mức mỗi method có một interface vô nghĩa.

## 16. Anti-pattern: Nhiều nguồn sự thật

Khi cùng một rule hoặc schema được khai báo ở nhiều nơi, chúng có thể lệch nhau.

### Dấu hiệu

- Grammar và documentation mô tả khác nhau.
- Built-in function được đăng ký riêng trong compiler, runtime và editor.
- Type schema được lặp lại trong nhiều plugin.
- Version compatibility được ghi ở nhiều file nhưng không đồng bộ.

### Hậu quả

Một nơi chấp nhận cú pháp nhưng nơi khác từ chối; autocomplete gợi ý function không tồn tại ở runtime; tài liệu trở nên không đáng tin.

### Cách khắc phục

- Xác định source of truth cho grammar, schema và function descriptors.
- Sinh tài liệu hoặc registry từ metadata dùng chung khi phù hợp.
- Kiểm tra consistency bằng contract test.
- Tránh sinh code từ một nguồn nếu nguồn đó không phản ánh đầy đủ semantics.

## 17. Anti-pattern: Error message chung chung

Một diagnostic như "Invalid DSL" không giúp người dùng biết lỗi ở đâu và cách sửa.

### Dấu hiệu

- Mọi lỗi đều thành một exception chung.
- Không có source range.
- Không phân biệt syntax, type, permission và runtime failure.
- Message tiết lộ stack trace nội bộ hoặc không có error code ổn định.

### Hậu quả

Người dùng không tự sửa được lỗi, support tốn thời gian và test khó xác nhận behavior.

### Cách khắc phục

- Dùng diagnostic code ổn định.
- Có severity, source range và related information.
- Phân biệt lỗi người dùng với lỗi hệ thống.
- Cung cấp suggestion khi có cơ sở.
- Giữ message an toàn, không lộ secret hoặc nội bộ.

## 18. Anti-pattern: Parser error recovery khó đoán

Parser có thể cố tiếp tục sau syntax error để báo nhiều lỗi, nhưng recovery tùy tiện có thể tạo AST sai lệch.

### Dấu hiệu

- Một lỗi nhỏ gây hàng chục diagnostic không liên quan.
- Parser bỏ qua quá nhiều token.
- AST partial không có trạng thái invalid rõ.
- Diagnostic trỏ sai source location.

### Hậu quả

Editor hiển thị lỗi nhiễu, người dùng sửa sai chỗ và downstream phase nhận cấu trúc không đáng tin.

### Cách khắc phục

- Xác định synchronization token.
- Đánh dấu node bị lỗi hoặc incomplete.
- Giới hạn cascade diagnostics.
- Không chạy semantic rule không an toàn trên node invalid.
- Viết fixture cho malformed input và recovery behavior.

## 19. Anti-pattern: Grammar và domain model lệch nhau

DSL có thể bắt đầu từ một domain model nhưng dần tích lũy syntax không còn phản ánh khái niệm nghiệp vụ.

### Dấu hiệu

- Cùng một domain concept có nhiều tên.
- Syntax buộc người dùng biết internal identifier.
- Domain change không được phản ánh vào DSL.
- Compiler chứa mapping đặc biệt cho từng khách hàng.

### Hậu quả

DSL mất tính chuyên biệt, tài liệu khó dạy và mỗi thay đổi domain tạo thêm compatibility exception.

### Cách khắc phục

- Duy trì glossary.
- Làm việc với domain expert.
- Dùng ubiquitous language nhất quán.
- Tách domain model khỏi persistence model.
- Đánh giá syntax qua use case thật.

## 20. Anti-pattern: Cố nhồi mọi use case vào một DSL

Một DSL duy nhất có thể trở nên quá rộng khi cố phục vụ nhiều domain hoặc nhóm người dùng có nhu cầu khác nhau.

### Dấu hiệu

- Grammar có nhiều construct chỉ một nhóm dùng.
- Người dùng phải học nhiều khái niệm không liên quan.
- Feature flags và mode làm syntax thay đổi mạnh.
- Mỗi domain cần nhiều exception.

### Hậu quả

Ngôn ngữ khó học, khó test và khó duy trì backward compatibility.

### Cách khắc phục

- Xác định bounded context.
- Tách DSL hoặc module theo domain khi semantics thực sự khác.
- Chia sẻ type/API nền tảng có chủ đích.
- Dùng extension points cho phần mở rộng rõ ràng.
- Không tạo một ngôn ngữ tổng quát chỉ vì muốn tránh có nhiều DSL nhỏ.

## 21. Anti-pattern: Overengineering và abstraction quá sớm

Thiết kế framework tổng quát trước khi hiểu các use case thật có thể làm DSL phức tạp không cần thiết.

### Dấu hiệu

- Nhiều abstraction chỉ có một implementation.
- Plugin system xuất hiện trước khi có nhu cầu extension.
- Grammar hỗ trợ nhiều mode chưa có người dùng.
- Configuration có hàng chục option không được sử dụng.

### Hậu quả

Tăng chi phí học, test, documentation và maintenance.

### Cách khắc phục

- Bắt đầu từ use case thật.
- Giữ extension point ở nơi có khả năng thay đổi hợp lý.
- Trì hoãn abstraction tổng quát cho đến khi có bằng chứng lặp lại.
- Theo dõi usage và loại bỏ API không cần thiết theo policy.

## 22. Anti-pattern: Không có giới hạn tài nguyên

Một DSL có thể cho phép expression, loop, recursion hoặc query tiêu thụ tài nguyên không giới hạn.

### Dấu hiệu

- Parser có thể xử lý input lồng sâu vô hạn.
- Runtime không có execution deadline.
- Loop không có quota hoặc cancellation.
- Một function có thể tải toàn bộ dataset.
- Một tenant chiếm hết worker pool.

### Hậu quả

Denial of service, chi phí vận hành tăng và ảnh hưởng chéo giữa tenant.

### Cách khắc phục

- Giới hạn source size, AST depth và node count.
- Đặt execution timeout và instruction budget.
- Có cancellation và concurrency quota.
- Phân trang dữ liệu.
- Cô lập worker và tenant.
- Theo dõi resource consumption.

## 23. Anti-pattern: Escape hatch không được kiểm soát

Escape hatch cho phép người dùng vượt qua DSL abstraction để gọi host language hoặc code tùy ý.

### Dấu hiệu

- Một block script có thể truy cập filesystem/network.
- Không có policy khác nhau giữa môi trường dev và production.
- Compiler không thể phân tích nội dung escape block.
- Plugin có thể mở rộng quyền vượt qua capability model.

### Hậu quả

Mất portability, static analysis, reproducibility và security isolation.

### Cách khắc phục

- Chỉ cung cấp escape hatch khi có use case rõ.
- Tách quyền riêng và mặc định tắt trong môi trường không tin cậy.
- Định nghĩa type boundary và serialization.
- Audit mọi lần sử dụng.
- Có kế hoạch thay thế bằng API domain khi nhu cầu ổn định.

## 24. Anti-pattern: Plugin coupling và extension contract không ổn định

Plugin giúp mở rộng DSL nhưng có thể làm host phụ thuộc vào implementation của extension.

### Dấu hiệu

- Plugin truy cập class nội bộ.
- Host thay đổi lifecycle mà không version hóa.
- Plugin tự đăng ký global listener nhưng không dispose.
- Dependency conflict làm plugin khác không load.
- Không có compatibility matrix.

### Hậu quả

Nâng cấp host có thể phá nhiều plugin; lỗi của một plugin có thể làm hỏng toàn ứng dụng.

### Cách khắc phục

- Công bố public extension API.
- Version hóa contract và capability.
- Định nghĩa lifecycle, thread safety và error isolation.
- Dùng plugin descriptor và dependency validation.
- Kiểm thử host/plugin version matrix.

## 25. Anti-pattern: Versioning và migration bị bỏ quên

DSL source, AST/IR, persisted process state và plugin có thể tồn tại lâu hơn một release.

### Dấu hiệu

- Compiler mới không thể đọc source cũ.
- Persisted workflow state không có schema version.
- API bị xóa mà không có deprecation window.
- Người dùng phải tự đoán cách sửa syntax.

### Hậu quả

Upgrade gây gián đoạn, dữ liệu không đọc được và support burden tăng.

### Cách khắc phục

- Phân biệt product version, language version và API version.
- Duy trì compatibility matrix.
- Có deprecation policy và migration guide.
- Version hóa persisted schema.
- Dùng expand-and-contract khi đổi field hoặc contract.
- Kiểm tra rollback với dữ liệu mới.

## 26. Anti-pattern: Test chỉ kiểm tra happy path

DSL có thể chạy đúng với ví dụ đơn giản nhưng thất bại ở input biên, lỗi hoặc concurrency.

### Dấu hiệu

- Chỉ có một vài example test.
- Không kiểm tra malformed source.
- Không có test cho type mismatch và error recovery.
- Golden baseline được cập nhật mà không review.
- Không test tenant isolation hoặc permission.

### Hậu quả

Regression và security issue dễ lọt vào release.

### Cách khắc phục

- Bổ sung boundary và negative cases.
- Dùng golden test cho output có cấu trúc.
- Dùng property/fuzz test cho parser và serializer.
- Test error handling, cancellation và concurrency.
- Test permission và resource limit.
- Kết hợp unit, integration và compatibility test.

## 27. Anti-pattern: Tài liệu không đồng bộ với implementation

Tài liệu là một phần của interface người dùng. Tài liệu sai có thể khiến một DSL đúng về mặt kỹ thuật vẫn khó sử dụng.

### Dấu hiệu

- Example không chạy với version hiện tại.
- Syntax reference thiếu construct mới.
- Deprecation không được ghi rõ.
- Diagnostic code không có giải thích.
- API reference khác với function registry.

### Hậu quả

Người dùng học sai, tạo source không hợp lệ và mất niềm tin vào tài liệu.

### Cách khắc phục

- Version hóa tài liệu.
- Chạy ví dụ trong test khi phù hợp.
- Tạo reference từ metadata có nguồn tin cậy.
- Cập nhật migration guide cùng breaking change.
- Có owner cho từng phần tài liệu.

## 28. Bảng tổng hợp dấu hiệu và hướng xử lý

| Anti-pattern | Dấu hiệu nổi bật | Hướng xử lý chính |
|---|---|---|
| DSL chỉ bọc host language | Người dùng phải hiểu implementation host | Thiết kế syntax theo domain |
| Grammar phức tạp | Nhiều alias và ngoại lệ | Chuẩn hóa construct |
| Semantics mơ hồ | Cùng source có cách hiểu khác nhau | Công bố precedence và behavior |
| Implicit conversion quá nhiều | Kiểu tự đổi khó đoán | Conversion rule tường minh |
| Stringly typed | Tên và trạng thái là string tùy ý | Domain type và symbol resolution |
| Magic defaults | Behavior phụ thuộc cấu hình ẩn | Default được công bố |
| Global mutable state | Cross-request leakage | Context theo execution |
| Side effect ẩn | Function trông như query nhưng ghi dữ liệu | Query/command separation |
| Compile/runtime trộn lẫn | Lỗi chỉ xuất hiện khi chạy | Static validation có giới hạn rõ |
| Reflection tùy ý | Gọi class/method bất kỳ | Function registry và allowlist |
| Host API leakage | DSL phụ thuộc framework | Adapter và domain API |
| God object | Một context/service làm mọi việc | Interface theo capability |
| Nhiều source of truth | Grammar, docs, registry lệch nhau | Contract metadata thống nhất |
| Error chung chung | Không có code/range | Diagnostic model rõ |
| Recovery khó đoán | Diagnostic cascade | Synchronization và invalid node |
| Overengineering | Abstraction chưa có use case | Bắt đầu từ nhu cầu thực |
| Không giới hạn tài nguyên | Execution không có budget | Quota, timeout và isolation |
| Escape hatch rộng | Chạy code tùy ý | Capability và audit |
| Plugin coupling | Phụ thuộc internal API | Stable extension contract |
| Bỏ quên versioning | Upgrade phá source/state | Version và migration policy |
| Happy-path-only tests | Thiếu negative/boundary cases | Test theo rủi ro |
| Docs drift | Example/reference lỗi thời | Docs-as-code và executable examples |

## 29. Cách đánh giá mức độ nghiêm trọng

Không phải anti-pattern nào cũng cần refactor ngay. Có thể đánh giá theo một số chiều:

### 29.1 User impact

Người dùng có thường xuyên nhầm lẫn, viết workaround hoặc không thể dự đoán behavior không?

### 29.2 Change cost

Một thay đổi nhỏ có cần sửa nhiều module hoặc nhiều plugin không?

### 29.3 Defect risk

Thiết kế có làm tăng khả năng lỗi dữ liệu, sai quyết định nghiệp vụ hoặc regression không?

### 29.4 Security impact

Có thể vượt quyền, truy cập tenant khác, thực thi code không tin cậy hoặc làm cạn tài nguyên không?

### 29.5 Operational impact

Có khó debug, quan sát, rollback hoặc phục hồi không?

### 29.6 Frequency

Vấn đề xuất hiện một lần hay lặp lại trong nhiều feature và team?

Một cách xếp ưu tiên đơn giản:

| Ưu tiên | Tiêu chí | Hành động |
|---|---|---|
| Critical | Có nguy cơ bảo mật hoặc mất dữ liệu đang diễn ra | Giới hạn tác động ngay |
| High | Gây lỗi rộng hoặc cản trở thay đổi quan trọng | Lập kế hoạch sửa gần |
| Medium | Tăng chi phí hoặc gây lỗi lặp lại | Refactor theo phạm vi |
| Low | Chủ yếu là readability hoặc cleanup | Xử lý khi có thay đổi liên quan |

## 30. Refactor để loại bỏ anti-pattern

Refactor nên có mục tiêu rõ và giữ behavior được cam kết.

### 30.1 Viết test trước

Tạo fixture cho behavior hiện tại và behavior mong muốn. Nếu behavior hiện tại đã sai, ghi rõ expected đúng theo đặc tả.

### 30.2 Xác định boundary

Chọn phần cần thay đổi: grammar, type system, host API, runtime, plugin contract hoặc documentation. Tránh refactor toàn hệ thống khi vấn đề nằm ở một boundary nhỏ.

### 30.3 Thay đổi theo bước

Ví dụ thay stringly typed function call:

~~~text
Before:
call("approveOrder", "ORD-100", "HIGH")

After:
orders.approve(
  orderId: OrderId("ORD-100"),
  priority: Priority.HIGH
)
~~~

Có thể triển khai theo giai đoạn:

1. Đăng ký function descriptor có kiểu.
2. Thêm cú pháp mới.
3. Duy trì alias cũ trong thời gian chuyển đổi.
4. Phát diagnostic deprecation.
5. Cung cấp migration tool hoặc hướng dẫn.
6. Loại bỏ dạng cũ theo version policy.

### 30.4 Đo lại

Sau refactor, so sánh:

- Số lượng nhánh đặc biệt.
- Độ phức tạp grammar.
- Tỷ lệ lỗi compile/runtime.
- Chất lượng diagnostic.
- Số dependency giữa module.
- Thời gian build/test.
- Mức độ sử dụng workaround.

### 30.5 Tránh refactor hình thức

Đổi tên class hoặc chia file không tự động loại bỏ anti-pattern. Phải thay đổi nguyên nhân khiến behavior khó hiểu hoặc khó bảo trì.

## 31. Phân biệt anti-pattern với trade-off có chủ ý

Một số lựa chọn trông giống anti-pattern nhưng có thể là trade-off hợp lý.

Ví dụ:

- DSL nhỏ có thể dùng cú pháp đơn giản thay vì xây type system đầy đủ.
- Một host nội bộ có thể expose API cụ thể thay vì framework plugin tổng quát.
- Runtime có thể dynamic để hỗ trợ rule thay đổi thường xuyên.
- Một số implicit conversion được giữ vì domain có quy tắc chuyển đổi rõ.

Để phân biệt, hãy hỏi:

1. Quyết định có giải quyết nhu cầu thật không?
2. Chi phí và rủi ro có được hiểu và chấp nhận không?
3. Hành vi có được tài liệu hóa không?
4. Có cách giới hạn tác động không?
5. Khi nhu cầu thay đổi, có thể migrate không?

Một trade-off có chủ ý thường có lý do, phạm vi và giới hạn rõ. Anti-pattern thường tồn tại do lịch sử hoặc tiện lợi ngắn hạn mà không ai chịu trách nhiệm về hệ quả.

## 32. Quy trình review thiết kế DSL

Khi review một feature hoặc kiến trúc DSL, có thể dùng các câu hỏi:

1. Cú pháp có diễn đạt đúng khái niệm domain không?
2. Có nhiều cách viết tương đương không cần thiết không?
3. Semantics có rõ và nhất quán không?
4. Type checking có phát hiện lỗi sớm được không?
5. Default và conversion có minh bạch không?
6. Side effect có được thể hiện rõ không?
7. Context và state có bị chia sẻ sai scope không?
8. Host API có expose quá nhiều implementation detail không?
9. Có function hoặc plugin nào vượt capability cần thiết không?
10. Error có code, source range và recovery behavior rõ không?
11. Có giới hạn resource cho input và execution không?
12. Versioning và migration có được tính đến không?
13. Test có bao gồm negative, boundary và compatibility cases không?
14. Documentation có phản ánh contract thực tế không?

Các câu hỏi này là gợi ý để thảo luận thiết kế, không phải lý do tự động từ chối mọi thay đổi.

## 33. Ví dụ tổng hợp: phát hiện anti-pattern trong DSL workflow

Giả sử một DSL workflow ban đầu có cú pháp:

~~~text
run("validateOrder", input)
run("chargePayment", input)
run("sendEmail", input)
~~~

Sau một thời gian, nhiều vấn đề xuất hiện:

- Tên function là string nên sai chính tả chỉ lỗi khi chạy.
- Không có type checking cho input.
- run() có thể gọi function bất kỳ được đăng ký trong host.
- Không biết function nào tạo side effect.
- Retry workflow có thể charge payment hai lần.
- Diagnostics chỉ trả "Execution failed".

### 33.1 Nhận diện

Đây là tổ hợp stringly typed API, reflection/service lookup quá rộng, side effect không rõ và error contract yếu.

### 33.2 Thiết kế mục tiêu

~~~text
orders.validate(input.order)
payments.charge(
  payment: input.payment,
  idempotencyKey: execution.id
)
notifications.sendReceipt(input.customer)
~~~

### 33.3 Thay đổi contract

- Function có descriptor và type signature.
- Compiler resolve symbol và kiểm tra input.
- Runtime cấp capability theo execution.
- Command nhạy cảm có idempotency key.
- Error có code ổn định và source location.
- Host API kiểm tra authorization.

### 33.4 Migration

Giữ run() như compatibility adapter trong một thời gian, phát warning cho function cũ và cung cấp migration guide. Sau khi consumer chuyển đổi, loại bỏ theo major version đã công bố.

### 33.5 Kết quả mong đợi

Người viết DSL nhận được lỗi sớm hơn, runtime giới hạn quyền rõ hơn, retry an toàn hơn và host có thể thay implementation mà không buộc source DSL phụ thuộc vào class nội bộ.

## 34. Câu hỏi tự kiểm tra

1. Anti-pattern trong thiết kế DSL là gì?
2. Vì sao một cách làm có thể chạy được nhưng vẫn là anti-pattern?
3. Làm sao phân biệt triệu chứng với nguyên nhân thiết kế?
4. Khi nào một DSL chỉ là wrapper của host language?
5. Grammar quá phức tạp gây khó khăn gì cho parser và người dùng?
6. Implicit conversion có thể làm semantics khó dự đoán ra sao?
7. Stringly typed design ảnh hưởng static checking như thế nào?
8. Magic default có thể làm môi trường chạy khác nhau ra sao?
9. Vì sao global mutable context nguy hiểm trong runtime nhiều tenant?
10. Side effect ẩn làm retry và caching khó như thế nào?
11. Compile-time và runtime nên chia trách nhiệm ra sao?
12. Reflection không giới hạn làm tăng attack surface như thế nào?
13. Host API leakage gây coupling gì?
14. God object làm giảm khả năng kiểm soát capability ra sao?
15. Nhiều source of truth có thể làm compiler, editor và docs lệch nhau như thế nào?
16. Diagnostic tốt cần có những thông tin nào?
17. Parser error recovery không tốt gây cascade như thế nào?
18. Khi nào cần tách một DSL thành nhiều DSL theo bounded context?
19. Vì sao resource limit và escape hatch policy quan trọng?
20. Plugin contract cần ổn định những thành phần nào?
21. Versioning và migration giúp tránh rủi ro nào?
22. Vì sao golden test không thay thế unit và property test?
23. Làm sao phân biệt anti-pattern với trade-off có chủ ý?
24. Một refactor tốt cần có bằng chứng trước và sau nào?

Nhận diện anti-pattern giúp nhóm phát triển hiểu những lựa chọn thiết kế đang tạo ra chi phí hoặc rủi ro cho DSL. Khi đánh giá dựa trên triệu chứng, nguyên nhân, tác động và mục tiêu domain, nhóm có thể chọn refactor đúng phạm vi, giữ compatibility cần thiết và cải thiện khả năng sử dụng, kiểm thử, bảo mật cũng như vận hành của ngôn ngữ.
