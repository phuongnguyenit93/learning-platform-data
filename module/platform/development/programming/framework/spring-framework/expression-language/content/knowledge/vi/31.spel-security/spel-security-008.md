# Không dùng parse thành công làm bằng chứng an toàn trong SpEL

Spring Expression Language (SpEL) tách việc phân tích cú pháp khỏi việc đánh giá biểu thức. `SpelExpressionParser.parseExpression(...)` kiểm tra và tạo đối tượng Expression từ chuỗi đầu vào. Lời gọi này không chứng minh rằng biểu thức được phép truy cập dữ liệu, gọi method hay thay đổi trạng thái khi chạy.

Một expression có cú pháp hợp lệ vẫn có thể gọi bean nhạy cảm, đọc property ngoài phạm vi, thực hiện assignment hoặc gây tác dụng phụ nếu EvaluationContext cấp các capability tương ứng. Vì vậy, **parse thành công chỉ chứng minh biểu thức phù hợp với cú pháp parser chấp nhận; nó không phải kiểm tra phân quyền, kiểm tra nghiệp vụ hay sandbox bảo mật**.

## 1. Phân biệt parse và evaluate

Hai bước cơ bản:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("#order.total > 100");

    Boolean allowed = expression.getValue(context, Boolean.class);

`parseExpression` phân tích chuỗi và tạo Expression. `getValue` mới đánh giá expression trong EvaluationContext cụ thể, sử dụng root object, variables, property accessors, method resolvers, bean resolver và các dịch vụ khác mà context cung cấp.

Nếu chuỗi sai cú pháp, lỗi xuất hiện trong lúc parse. Nếu cú pháp đúng nhưng biến, property, bean hoặc method không tồn tại, lỗi có thể chỉ xuất hiện khi evaluate. Nếu mọi thành phần đều tồn tại, expression vẫn có thể thực hiện một hành động mà chính sách ứng dụng không cho phép.

Có thể parse một expression mà chưa thực thi nó:

    Expression expression =
            parser.parseExpression("@orderService.load(#orderId)");

Đoạn code này chưa gọi `load`. Method chỉ có thể được gọi khi expression được đánh giá với context có khả năng resolve bean và gọi method phù hợp.

## 2. Parse thành công không có nghĩa expression được phép chạy

Parser kiểm tra cú pháp của ngôn ngữ. Nó không biết người dùng hiện tại có quyền đọc order hay không, bean nào được phép truy cập trong use case, hoặc một method có thể ghi database hay gửi message.

Ví dụ các expression sau đều có hình thức cú pháp hợp lệ:

    #order.total > 100

    #order.status = 'APPROVED'

    @orderPolicy.canApprove(#order)

Chúng có ý nghĩa và khả năng thực thi khác nhau:

- Expression đầu chỉ so sánh giá trị nếu context cho phép đọc property.
- Expression thứ hai là assignment; nếu context có accessor ghi phù hợp, nó có thể thay đổi object.
- Expression thứ ba yêu cầu BeanResolver tìm bean và method resolver gọi method trên bean đó.

Parser không tự quyết định expression nào phù hợp với use case. Việc đánh giá có được phép hay không phải do ứng dụng kiểm soát bằng context, policy và kiểm tra quyền nghiệp vụ.

## 3. Expression hợp lệ vẫn có thể thất bại lúc evaluate

Parse thành công không đảm bảo mọi tham chiếu sẽ được resolve khi chạy. Các lỗi runtime thường gặp:

- Variable chưa được đăng ký trong EvaluationContext.
- Root object không có property được tham chiếu.
- Object trung gian là null khi expression truy cập property tiếp theo.
- Bean name không được BeanResolver tìm thấy.
- Method không tồn tại hoặc không có chữ ký phù hợp.
- TypeConverter không thể chuyển đổi đối số hoặc kết quả.
- Property không hỗ trợ ghi khi expression thực hiện assignment.
- Method được gọi ném exception hoặc dịch vụ bên ngoài thất bại.

Ví dụ:

    Expression expression =
            parser.parseExpression("#customer.address.city");

Expression có thể parse thành công dù context chưa đăng ký variable `customer`. Lỗi chỉ xuất hiện khi gọi `getValue(context)`. Tương tự, tên bean trong `@orderPolicy` có thể hợp lệ về cú pháp nhưng không resolve được nếu context không có BeanResolver hoặc bean tương ứng.

Hãy phân biệt lỗi parse với lỗi evaluation để xử lý đúng nguyên nhân. Không bắt mọi exception rồi trả về giá trị mặc định như thể expression đã được xác thực.

## 4. Evaluate thành công vẫn không chứng minh an toàn

Ngay cả khi expression chạy thành công và trả về kết quả đúng kiểu, nó vẫn có thể vượt quá quyền mà use case cần.

Một method có thể:

- Đọc dữ liệu thuộc tenant hoặc người dùng khác.
- Ghi hoặc xóa bản ghi.
- Gửi email, phát message hoặc gọi API bên ngoài.
- Thay đổi trạng thái object hoặc tài nguyên dùng chung.
- Kích hoạt khởi tạo bean hoặc truy cập dịch vụ có quyền rộng.
- Thực hiện tính toán tốn tài nguyên trên collection lớn.

Ví dụ, `@paymentService.refund(#paymentId)` có thể parse được và có thể evaluate thành công nếu bean cùng method được cung cấp. Điều đó không chứng minh người gọi được phép hoàn tiền cho payment đó. Quyền này phải được xác minh trong tầng nghiệp vụ, dựa trên principal, tài nguyên, tenant, trạng thái và quy tắc giao dịch.

**Kết quả đúng không đồng nghĩa hành động được ủy quyền.** Cần kiểm tra cả capability của context và quyền nghiệp vụ tại thời điểm thực hiện.

## 5. EvaluationContext quyết định nhiều capability lúc chạy

EvaluationContext cung cấp các thành phần quyết định expression có thể làm gì:

| Thành phần | Ảnh hưởng |
|---|---|
| Root object và variables | Những dữ liệu expression có thể tham chiếu |
| PropertyAccessor | Property nào có thể đọc hoặc ghi |
| MethodResolver | Method nào có thể được tìm và gọi |
| BeanResolver | Bean name nào có thể được resolve qua `@beanName` |
| TypeLocator | Class nào có thể được tham chiếu bằng `T(...)` |
| ConstructorResolver | Constructor nào có thể được gọi bằng `new` |
| TypeConverter | Những chuyển đổi kiểu được hỗ trợ |

Cùng một chuỗi expression có thể có hành vi khác nhau trong hai EvaluationContext. Một context chỉ có root object giới hạn có thể không resolve được bean; một StandardEvaluationContext có BeanFactoryResolver và reflective method access có thể mở nhiều khả năng hơn.

Do đó, không thể đánh giá độ an toàn chỉ từ chuỗi expression. Cần xem cả context thực tế được dùng khi evaluate.

## 6. StandardEvaluationContext không phải sandbox

StandardEvaluationContext cung cấp nhiều khả năng linh hoạt, thường bao gồm reflective property access, method invocation và type/constructor resolution. Khi được cấu hình BeanResolver, expression còn có thể truy cập bean theo tên.

Sự linh hoạt này phù hợp với expression nội bộ đáng tin cậy, nhưng có thể quá rộng nếu chuỗi expression đến từ người dùng hoặc cấu hình có thể bị thay đổi.

Ví dụ:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setBeanResolver(
            new BeanFactoryResolver(beanFactory)
    );

Context trên có thể resolve bean từ BeanFactory. Nếu expression được cung cấp từ nguồn không tin cậy, việc cho phép resolver toàn cục có thể mở ra nhiều service ngoài mục đích hiện tại.

Không nên coi việc parser chấp nhận expression hoặc việc dùng StandardEvaluationContext là một ranh giới bảo mật. Hãy giới hạn object, resolver, accessor và method mà use case cần.

## 7. SimpleEvaluationContext giảm phạm vi nhưng không thay thế policy

SimpleEvaluationContext được thiết kế cho các use case giới hạn như data binding. Tùy builder được chọn, nó có thể giới hạn property access và quyền ghi; nó không hỗ trợ bean reference, type reference hoặc constructor invocation. Instance method invocation không được bật mặc định.

Ví dụ context chỉ đọc:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(orderView)
                    .build();

Đây là lựa chọn phù hợp khi expression chỉ cần đọc property từ một view model. Nếu cần gọi instance method, builder có thể bật rõ bằng `withInstanceMethods()`; khi làm vậy, cần xem xét method nào được công khai trên object.

SimpleEvaluationContext thu hẹp tập tính năng được cung cấp, nhưng không tự xác nhận quyền truy cập dữ liệu hay quy tắc nghiệp vụ. Nếu root object chứa dữ liệu ngoài phạm vi người dùng, expression vẫn có thể đọc dữ liệu đó qua property được phép. Hãy chỉ cung cấp object đã được kiểm tra quyền và phù hợp với use case.

## 8. Không ghép dữ liệu không tin cậy vào chuỗi expression

Một lỗi thiết kế thường gặp là nối trực tiếp dữ liệu đầu vào vào expression:

    String source =
            "name == '" + userInput + "'";

    Expression expression = parser.parseExpression(source);

Nếu `userInput` chứa ký tự cú pháp của SpEL, nội dung cuối cùng có thể không còn là điều kiện mà ứng dụng dự định tạo. Người dùng có thể làm thay đổi cấu trúc expression thay vì chỉ cung cấp một giá trị dữ liệu.

Hãy giữ expression cố định và truyền dữ liệu qua variables:

    Expression expression =
            parser.parseExpression("name == #requestedName");

    context.setVariable("requestedName", userInput);

    Boolean matches =
            expression.getValue(context, Boolean.class);

Giá trị biến vẫn cần được kiểm tra kiểu, độ dài và quy tắc nghiệp vụ. Tuy nhiên, nó được truyền như dữ liệu runtime thay vì được ghép thành mã SpEL mới.

Nếu người dùng cần chọn điều kiện hoặc trường lọc, ưu tiên nhận cấu trúc dữ liệu có schema rõ ràng, ví dụ tên trường từ allowlist, toán tử từ enum và giá trị riêng biệt.

## 9. Xác định một tập expression được phép

Nếu ứng dụng phải nhận expression do người dùng hoặc quản trị viên cấu hình, hãy xác định trước một tập cú pháp và capability được chấp nhận. Ví dụ, một bộ lọc sản phẩm có thể chỉ cho phép:

- Đọc một số property đã allowlist như `price`, `category` và `active`.
- So sánh, kết hợp điều kiện và dùng literal hoặc variables.
- Không assignment.
- Không bean reference.
- Không constructor invocation hoặc type reference.
- Không gọi method ngoài danh sách đã định.

Có thể parse expression rồi kiểm tra cấu trúc AST theo allowlist như một lớp kiểm soát bổ sung. Bộ kiểm tra phải xử lý đệ quy toàn bộ node và từ chối cấu trúc không nhận diện; không được mặc định cho phép node mới khi nâng cấp Spring.

Không nên dùng regex hoặc tìm chuỗi đơn giản như `contains("@")` để chứng minh expression an toàn. Cú pháp lồng nhau, literal và các dạng biểu thức khác có thể làm kiểm tra chuỗi thiếu chính xác. AST allowlist cũng không thay thế context hạn chế và authorization tại runtime.

Nếu không cần hỗ trợ ngôn ngữ biểu thức tổng quát, một DSL nhỏ hoặc cấu trúc filter có schema thường dễ giới hạn và kiểm thử hơn.

## 10. Giới hạn bean, method và property được expose

Nếu expression cần gọi logic ứng dụng, hãy expose facade có API hẹp. Không đưa toàn bộ ApplicationContext, BeanFactory, repository hoặc service quản trị vào context.

Ví dụ:

    public final class OrderExpressionFacade {

        public boolean canPreview(OrderView order) {
            return order.isVisible();
        }

        public BigDecimal estimatedTotal(OrderView order) {
            return order.getTotal();
        }
    }

Facade chỉ cung cấp các thao tác cần thiết cho expression. Nếu dùng bean reference, hãy dùng BeanResolver allowlist chỉ resolve facade được phép. Nếu dùng variables, chỉ đăng ký đúng object cần thiết cho lần đánh giá.

Giới hạn đồng thời:

- Bean name được resolve.
- Method được gọi trên object đã expose.
- Property được đọc hoặc ghi.
- Root object và variables được đưa vào context.
- Type reference và constructor invocation nếu use case không cần.

Một allowlist bean không đủ nếu bean đó vẫn công khai method có quyền rộng. Tương tự, một facade hẹp không đủ nếu root object chứa dữ liệu nhạy cảm mà expression có thể đọc.

## 11. Kiểm tra quyền tại thời điểm evaluate

Quyền truy cập có thể thay đổi theo người gọi, tenant, trạng thái bản ghi hoặc thời điểm thực hiện. Vì vậy, không nên chỉ kiểm tra một lần lúc lưu expression rồi giả định expression luôn được phép chạy về sau.

Trước khi evaluate hoặc thực hiện hành động quan trọng, ứng dụng cần:

1. Xác thực principal và tenant hiện tại.
2. Tải hoặc chọn root object trong phạm vi người gọi được phép.
3. Kiểm tra quyền trên tài nguyên cụ thể.
4. Tạo EvaluationContext với đúng variables và capability.
5. Đánh giá expression trong ranh giới transaction hoặc service phù hợp.
6. Xử lý lỗi, ghi audit và kiểm soát side effect theo chính sách.

Nếu expression chỉ dùng để lọc hoặc hiển thị, hãy ưu tiên context chỉ đọc và object đã giới hạn. Nếu expression có thể thay đổi trạng thái, authorization phải được kiểm tra trong service thực hiện hành động; không dựa vào kết quả parse hoặc một điều kiện client gửi lên.

## 12. Giới hạn tài nguyên và tác dụng phụ

Một expression có thể hợp lệ nhưng vẫn tiêu tốn nhiều tài nguyên hoặc gọi method lặp lại. Selection/projection trên collection lớn, method thực hiện truy vấn, hoặc lời gọi dịch vụ bên ngoài có thể làm tăng thời gian xử lý.

Các biện pháp nên áp dụng:

- Giới hạn độ dài expression và kích thước dữ liệu đầu vào.
- Giới hạn kích thước collection được đưa vào context.
- Không expose method thực hiện I/O hoặc công việc không giới hạn cho expression tùy ý.
- Tránh đánh giá lặp expression có method side effect.
- Dùng timeout, transaction và idempotency ở tầng service khi hành động cần chúng.
- Không chia sẻ EvaluationContext chứa trạng thái request giữa các request đồng thời.

Parser không phải bộ thực thi có sandbox tài nguyên tổng quát. Giới hạn độ dài chuỗi chỉ kiểm soát một phần đầu vào; nó không bảo đảm expression evaluate nhanh hoặc không tạo side effect.

## 13. Phân biệt parse validation, evaluation và authorization

Ba việc này trả lời ba câu hỏi khác nhau:

| Bước | Câu hỏi | Bằng chứng thu được |
|---|---|---|
| Parse | Chuỗi có đúng cú pháp SpEL được parser chấp nhận không? | Có thể tạo Expression |
| Evaluate | Expression có chạy được trong context cụ thể không? | Có kết quả hoặc lỗi runtime |
| Authorization | Người gọi có được phép thực hiện thao tác trên dữ liệu/tài nguyên này không? | Quyết định quyền của ứng dụng |

Không dùng kết quả của một bước thay cho bước khác. Parse thành công không chứng minh evaluate sẽ thành công. Evaluate thành công cũng không chứng minh hành động được phép.

Một hệ thống an toàn cần cả ba: cú pháp được giới hạn, context có capability tối thiểu và authorization được thực hiện ở đúng ranh giới nghiệp vụ.

## 14. Ghi nhớ

`parseExpression(...)` phân tích cú pháp và tạo Expression; `getValue(...)` mới đánh giá expression trong EvaluationContext. Parse thành công không xác nhận bean, method, property hay variable có thể resolve, và càng không chứng minh hành vi runtime an toàn. Một expression evaluate thành công vẫn có thể đọc dữ liệu ngoài phạm vi hoặc thực hiện side effect nếu context cấp quyền đó. Không ghép input không tin cậy vào chuỗi SpEL; truyền dữ liệu qua variables, giới hạn root object và resolver, ưu tiên SimpleEvaluationContext cho data binding, và dùng facade/allowlist khi cần capability bổ sung. Luôn kiểm tra quyền tại thời điểm thực hiện và xem parse validation, evaluation và authorization là ba trách nhiệm riêng biệt.
