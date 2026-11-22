# Giới hạn của SpEL so với ngôn ngữ lập trình đầy đủ

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao Spring Expression Language (SpEL) rất hữu ích để biểu diễn điều kiện và truy cập dữ liệu trong Spring nhưng không thay thế Java hay một ngôn ngữ lập trình đa dụng. Bạn cũng sẽ biết phần việc nào phù hợp với SpEL, phần việc nào nên chuyển sang mã Java, và cách giới hạn quyền của bộ đánh giá biểu thức.

## 1. SpEL được thiết kế để làm gì?

Spring Expression Language là ngôn ngữ biểu thức do Spring cung cấp. Nó cho phép một ứng dụng mô tả một phép tính, điều kiện hoặc thao tác truy cập dữ liệu dưới dạng chuỗi, sau đó phân tích và đánh giá chuỗi đó trong một ngữ cảnh cụ thể.

Ví dụ, một biểu thức có thể lấy tên khách hàng từ đối tượng gốc:

    customer.name

Hoặc quyết định nhãn dựa trên tổng đơn hàng:

    total >= 1000 ? 'PRIORITY' : 'STANDARD'

SpEL thường xuất hiện ở những nơi Spring cần một giá trị hoặc một điều kiện được cấu hình bằng biểu thức, chẳng hạn:

- `@Value` để lấy giá trị từ môi trường, thuộc tính hoặc bean.
- Spring Cache, ví dụ `@Cacheable(key = "#orderId")`, để tạo khóa cache từ tham số phương thức.
- Spring Security, ví dụ `@PreAuthorize("hasAuthority('invoice:read')")`, để kiểm tra quyền truy cập.
- Các cấu hình hoặc thành phần ứng dụng tự tạo có sử dụng `ExpressionParser` và `EvaluationContext`.

Một chuỗi chỉ trở thành biểu thức SpEL khi có thành phần Spring hoặc mã ứng dụng chủ động phân tích và đánh giá nó. SpEL không tự động chạy mọi chuỗi trong ứng dụng.

## 2. Mô hình đánh giá biểu thức

Thông thường, quá trình sử dụng SpEL có ba phần:

1. **Parser** phân tích chuỗi biểu thức thành đối tượng `Expression`.
2. **EvaluationContext** cung cấp các khả năng mà biểu thức được phép sử dụng, ví dụ cách đọc thuộc tính, gọi phương thức, chuyển đổi kiểu, tra cứu bean và lưu biến.
3. **Root object** là đối tượng gốc mà biểu thức truy cập khi tên thuộc tính hoặc phương thức không được viết kèm biến `#`.

Ví dụ Java:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("customer.name");

    String name = expression.getValue(order, String.class);

Trong ví dụ này, `order` là root object. SpEL đọc thuộc tính `customer`, sau đó đọc `name`. Việc truy cập thực tế phụ thuộc vào các property accessor và cấu hình của ngữ cảnh đánh giá.

Khi cần truyền biến hoặc cấu hình quyền truy cập, có thể tạo một `EvaluationContext`:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression(
        "#order != null and #order.total > #limit ? 'REVIEW' : 'APPROVE'"
    );

    EvaluationContext context = new StandardEvaluationContext();
    context.setVariable("order", order);
    context.setVariable("limit", new BigDecimal("1000"));

    String decision = expression.getValue(context, String.class);

Biểu thức trên trả về một giá trị chuỗi. Nó không định nghĩa một chương trình gồm nhiều câu lệnh.

## 3. SpEL làm được những gì?

SpEL có nhiều khả năng hơn một bộ thay thế chuỗi đơn giản. Các khả năng phổ biến gồm:

### 3.1. Giá trị và toán tử

SpEL hỗ trợ các literal như số, chuỗi, boolean, `null`, cũng như các phép toán số học, so sánh và logic.

    10 + 5 * 2
    #quantity >= 10 and #enabled
    name matches 'A.*'
    age between {18, 60}

Các toán tử điều kiện giúp tạo ra một giá trị theo nhánh:

    #total >= 1000 ? 'PRIORITY' : 'STANDARD'

Toán tử Elvis cung cấp giá trị mặc định khi vế trái là `null`:

    #displayName ?: 'Khách hàng'

Toán tử safe navigation giúp tránh truy cập thuộc tính hoặc gọi phương thức trên một tham chiếu `null`:

    customer?.address?.city

Đây là các biểu thức điều kiện nằm trong một biểu thức đơn. Chúng không tạo ra cấu trúc `if/else` dạng câu lệnh như trong Java.

### 3.2. Đọc thuộc tính, gọi phương thức và truy cập phần tử

Nếu ngữ cảnh cho phép, biểu thức có thể đọc thuộc tính, gọi phương thức và truy cập phần tử trong mảng, danh sách hoặc map.

    customer.address.city
    customer.getDisplayName()
    items[0]
    settings['locale']

SpEL có thể gọi phương thức Java đã được phơi bày qua ngữ cảnh. Vì vậy, một biểu thức ngắn vẫn có thể gọi logic nằm trong mã Java. Khả năng này phụ thuộc vào method resolver và quyền truy cập được cấu hình.

### 3.3. Tham chiếu kiểu, khởi tạo đối tượng và bean

Trong ngữ cảnh cho phép, SpEL có thể tham chiếu một kiểu Java bằng toán tử `T(...)`, gọi phương thức tĩnh và tạo đối tượng bằng `new`.

    T(java.lang.Math).max(10, 20)
    new java.math.BigDecimal('19.95')

Biểu thức cũng có thể tham chiếu bean theo tên, ví dụ:

    @taxCalculator.calculate(#order)

Cú pháp tham chiếu bean chỉ hoạt động khi ngữ cảnh có `BeanResolver` phù hợp. Không nên mặc định rằng mọi `EvaluationContext` đều có quyền tra cứu bean.

### 3.4. Biến và hàm đã đăng ký

Biến trong ngữ cảnh thường được tham chiếu bằng tiền tố `#`:

    #currentUser
    #order.total

Ứng dụng cũng có thể đăng ký một phương thức Java làm hàm để biểu thức gọi bằng tên. SpEL không yêu cầu người viết định nghĩa thân hàm mới bên trong biểu thức; phần triển khai vẫn nằm trong mã Java.

### 3.5. Lọc và chiếu collection

SpEL có cú pháp chuyên biệt để làm việc với collection:

- Selection `.?[...]` lọc các phần tử thỏa điều kiện.
- Projection `.![...]` tạo collection mới từ một thuộc tính hoặc biểu thức của từng phần tử.
- `.^[...]` lấy phần tử đầu tiên thỏa điều kiện.
- `.$[...]` lấy phần tử cuối cùng thỏa điều kiện.

Ví dụ:

    #orders.?[status == 'PAID']
    #orders.![id]
    #orders.^[total > 1000]

Những thao tác này rất tiện cho việc truy vấn dữ liệu đã có trong bộ nhớ. Chúng không phải là vòng lặp tổng quát để điều khiển một quy trình nhiều bước.

### 3.6. Gán giá trị

SpEL có toán tử gán. Nếu quyền ghi được bật và đối tượng cho phép, biểu thức có thể thay đổi thuộc tính:

    name = 'New name'

Ngoài ra, một biểu thức có thể gọi phương thức Java có tác dụng phụ. Do đó, không nên xem mọi biểu thức SpEL là phép tính thuần túy hoặc mặc định an toàn để chạy trên dữ liệu do người dùng cung cấp.

## 4. Những gì SpEL không cung cấp như một ngôn ngữ lập trình đầy đủ

Sự khác biệt chính nằm ở mục đích và cấu trúc của ngôn ngữ. SpEL tập trung vào việc đánh giá biểu thức trong một ứng dụng Spring. Java là ngôn ngữ lập trình đa dụng dùng để xây dựng toàn bộ hành vi của ứng dụng.

| Nhu cầu | SpEL | Java |
|---|---|---|
| Tính toán và so sánh | Có, bằng biểu thức | Có |
| Chọn một giá trị theo điều kiện | Có, bằng toán tử ba ngôi hoặc Elvis | Có, bằng biểu thức hoặc `if/else` |
| Truy cập thuộc tính và gọi phương thức | Có, tùy quyền của context | Có, theo quy tắc truy cập của Java |
| Lọc hoặc chiếu collection | Có cú pháp chuyên biệt | Có vòng lặp, Stream API và thư viện |
| Khai báo biến cục bộ cho một khối chương trình | Không có mô hình khối lệnh tổng quát; có biến trong context | Có |
| Định nghĩa class, interface, enum hoặc kiểu mới | Không | Có |
| Định nghĩa phương thức với thân hàm mới | Không; có thể gọi phương thức Java đã đăng ký hoặc được phép | Có |
| Vòng lặp tổng quát như `for`, `while`, `do/while` | Không có cấu trúc câu lệnh tương ứng | Có |
| Xử lý ngoại lệ bằng `try/catch/finally` | Không có cấu trúc câu lệnh tương ứng | Có |
| Tổ chức package, module và phụ thuộc | Không | Có |
| Quản lý luồng, tác vụ bất đồng bộ và vòng đời ứng dụng | Không phải chức năng của SpEL | Có, thông qua Java và thư viện |
| I/O, mạng, cơ sở dữ liệu và tài nguyên hệ thống | Chỉ có thể gián tiếp gọi mã Java được phép | Có, thông qua API và thư viện |
| Kiểm tra kiểu tĩnh và kiểm tra lỗi trong quá trình biên dịch | Hạn chế; nhiều lỗi chỉ xuất hiện khi đánh giá | Mạnh hơn nhờ trình biên dịch và hệ kiểu Java |

Một số điểm cần hiểu đúng:

- **Có điều kiện không có nghĩa là có cấu trúc điều khiển đầy đủ.** Toán tử ba ngôi giúp chọn một kết quả, nhưng không thay thế một khối `if` chứa nhiều câu lệnh.
- **Có selection/projection không có nghĩa là có vòng lặp tổng quát.** SpEL có thể lọc hoặc biến đổi collection, nhưng không phù hợp để mô tả một thuật toán lặp nhiều bước với trạng thái thay đổi.
- **Gọi được phương thức Java không có nghĩa là SpEL có thể định nghĩa phương thức đó.** Phần logic vẫn phải được viết, biên dịch và kiểm thử trong Java.
- **Có thể gán giá trị không có nghĩa là có mô hình lập trình mệnh lệnh hoàn chỉnh.** SpEL vẫn thiếu các cấu trúc tổ chức chương trình như khai báo kiểu, khối lệnh, vòng lặp và xử lý ngoại lệ.
- **Có thể truy cập API không có nghĩa là mọi API đều tự động được phép.** Quyền truy cập phụ thuộc vào root object, `EvaluationContext`, resolver và các thành phần Spring tích hợp.

## 5. So sánh cùng một yêu cầu

Giả sử ứng dụng cần quyết định một đơn hàng có phải chuyển sang bước kiểm tra thủ công hay không.

Nếu chỉ cần tạo một nhãn từ dữ liệu đã có, SpEL là phù hợp:

    #order != null and #order.total >= #limit ? 'REVIEW' : 'APPROVE'

Biểu thức nhận dữ liệu từ context và trả về một kết quả. Nó dễ đặt trong cấu hình hoặc annotation khi quy tắc ngắn và ổn định.

Nếu quy trình cần nhiều bước, Java phù hợp hơn:

    if (order == null) {
        throw new IllegalArgumentException("Order is required");
    }

    if (order.isCancelled()) {
        return Decision.REJECT;
    }

    BigDecimal total = order.calculateTotal();
    RiskProfile profile = riskService.evaluate(order);

    if (total.compareTo(limit) >= 0 || profile.requiresReview()) {
        auditService.recordReview(order);
        notificationService.notifyReviewer(order);
        return Decision.REVIEW;
    }

    return Decision.APPROVE;

Đoạn Java có thể khai báo biến, gọi nhiều dịch vụ, thay đổi trạng thái, phát sinh ngoại lệ và trả về từ nhiều nhánh. Cố gắng ép toàn bộ quy trình này thành một biểu thức SpEL sẽ làm biểu thức khó đọc, khó kiểm thử và phụ thuộc quá nhiều vào quyền truy cập của context.

Một cách kết hợp tốt là để Java thực hiện quy trình và cung cấp các hàm nhỏ, có tên rõ ràng cho SpEL khi cần cấu hình một quy tắc đơn giản.

## 6. Giới hạn kiểu dữ liệu và thời điểm phát hiện lỗi

SpEL đánh giá biểu thức dựa trên đối tượng thực tế và ngữ cảnh lúc chạy. Vì thế, một số vấn đề chỉ xuất hiện khi biểu thức được thực thi:

- Thuộc tính hoặc phương thức không tồn tại trên đối tượng thực tế.
- Giá trị `null` xuất hiện ở vị trí biểu thức không xử lý.
- Không thể chuyển đổi giá trị sang kiểu kết quả mong muốn.
- Collection có phần tử không có cấu trúc mà biểu thức kỳ vọng.
- Bean, hàm hoặc kiểu Java được tham chiếu không có trong context.
- Phương thức được gọi ném ngoại lệ trong quá trình thực thi.

Parser có thể phát hiện lỗi cú pháp khi phân tích biểu thức. Tuy nhiên, việc phân tích thành công không đảm bảo rằng biểu thức sẽ đánh giá thành công với mọi dữ liệu đầu vào.

Ứng dụng nên xử lý lỗi phân tích và lỗi đánh giá ở lớp Java gọi SpEL. Không nên đặt kỳ vọng rằng biểu thức có thể tự bắt ngoại lệ và phục hồi như một khối chương trình Java.

SpEL có cơ chế biên dịch biểu thức để tối ưu một số trường hợp đánh giá lặp lại. Cơ chế này không biến SpEL thành Java và không loại bỏ các giới hạn về cấu trúc ngôn ngữ. Hiệu quả còn phụ thuộc vào kiểu dữ liệu và tính ổn định của biểu thức; chỉ nên bật sau khi đã đo hiệu năng trên đường chạy thực tế.

## 7. Giới hạn quyền truy cập và an toàn

Một biểu thức chỉ an toàn trong phạm vi quyền mà context cho phép. `StandardEvaluationContext` cung cấp nhiều khả năng truy cập linh hoạt, bao gồm cơ chế phản chiếu để truy cập thuộc tính và gọi phương thức. Khi cấu hình thêm type locator, constructor resolver hoặc bean resolver, biểu thức có thể có thêm quyền đối với kiểu Java, constructor và bean.

Điều này hữu ích với biểu thức do lập trình viên kiểm soát. Nó có thể trở thành rủi ro nếu ứng dụng lấy nguyên văn biểu thức từ người dùng, nội dung bên ngoài hoặc một nguồn không đáng tin cậy rồi đánh giá bằng context có quyền rộng.

Một số nguyên tắc thực tế:

1. Không đánh giá biểu thức do người dùng tùy ý nhập bằng `StandardEvaluationContext` có quyền truy cập rộng.
2. Với nhu cầu data binding đơn giản, cân nhắc `SimpleEvaluationContext`. Context này được thiết kế để chỉ bật những khả năng cần thiết; nó không cung cấp mặc định các khả năng tham chiếu kiểu, gọi constructor hoặc tra cứu bean như context tiêu chuẩn.
3. Chỉ đăng ký những property accessor, method resolver và hàm thực sự cần thiết.
4. Không đưa toàn bộ `ApplicationContext`, dịch vụ nhạy cảm hoặc đối tượng có quyền cao vào root object hay biến của biểu thức.
5. Ưu tiên biểu thức do ứng dụng kiểm soát, có phạm vi rõ ràng và được kiểm thử với dữ liệu đại diện.
6. Giữ các thao tác có tác dụng phụ, truy cập mạng, ghi dữ liệu hoặc thay đổi trạng thái trong service Java có kiểm soát quyền và xử lý lỗi.

Ví dụ về context chỉ đọc cho một trường hợp data binding:

    ExpressionParser parser = new SpelExpressionParser();
    EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Expression expression = parser.parseExpression("customer.name");
    String name = expression.getValue(context, order, String.class);

Cấu hình này phù hợp khi biểu thức chỉ cần đọc thuộc tính theo cơ chế data binding. Nếu ứng dụng cần thêm khả năng, hãy bật từng khả năng một cách có chủ đích và hiểu rõ quyền mà nó mang lại.

## 8. Khi nào nên dùng SpEL và khi nào nên dùng Java?

Dùng SpEL khi:

- Cần một điều kiện hoặc phép tính ngắn trong cấu hình Spring.
- Cần tạo cache key từ tham số hoặc thuộc tính của đối tượng.
- Cần kiểm tra một điều kiện truy cập trong tích hợp Spring Security.
- Cần chọn, đọc hoặc chiếu dữ liệu từ một đối tượng hoặc collection đã có.
- Quy tắc đủ ngắn để người bảo trì hiểu được ngay tại nơi nó được khai báo.

Dùng Java khi:

- Logic có nhiều bước hoặc nhiều nhánh.
- Cần vòng lặp, xử lý ngoại lệ, retry hoặc điều phối tác vụ.
- Cần gọi nhiều service hoặc phối hợp giao dịch.
- Cần quản lý trạng thái, tài nguyên, luồng hoặc tác vụ bất đồng bộ.
- Cần kiểu dữ liệu rõ ràng, kiểm tra lỗi khi biên dịch, refactor an toàn và kiểm thử đơn vị sâu.
- Biểu thức bắt đầu chứa nhiều lời gọi phương thức, nhiều điều kiện lồng nhau hoặc tác dụng phụ.

Một quy tắc thực tế: nếu người đọc phải lần theo nhiều lời gọi để hiểu biểu thức, hãy chuyển logic vào một phương thức Java có tên rõ ràng. Khi đó, SpEL có thể gọi phương thức đó nếu thật sự cần cấu hình hóa điểm quyết định.

## 9. Ghi nhớ

SpEL là ngôn ngữ biểu thức được nhúng trong hệ sinh thái Spring. Nó rất hữu ích để mô tả giá trị, điều kiện, truy cập thuộc tính, gọi phương thức được cho phép và thao tác collection trong một ngữ cảnh cụ thể.

Giới hạn của nó đến từ mục tiêu thiết kế: SpEL đánh giá biểu thức, còn Java xây dựng chương trình. SpEL có toán tử điều kiện, selection, projection, biến và khả năng gọi mã Java, nhưng không cung cấp đầy đủ cấu trúc khai báo kiểu, khối lệnh, vòng lặp, xử lý ngoại lệ, module và công cụ phát triển của một ngôn ngữ đa dụng.

Hãy dùng SpEL cho quy tắc ngắn, khai báo và có phạm vi quyền rõ ràng. Hãy đặt quy trình nghiệp vụ, tác dụng phụ và logic phức tạp trong Java.