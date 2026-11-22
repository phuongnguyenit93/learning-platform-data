# Lộ trình học SpEL từ cú pháp cơ bản đến tích hợp an toàn

Spring Expression Language (SpEL) là ngôn ngữ biểu thức của hệ sinh thái Spring. SpEL cho phép đọc thuộc tính, gọi phương thức, tính toán, truy vấn collection và tham chiếu bean bằng một chuỗi biểu thức được phân tích rồi đánh giá trong một ngữ cảnh cụ thể. SpEL xuất hiện trong nhiều điểm tích hợp của Spring, chẳng hạn `@Value`, cấu hình bean và một số cơ chế điều kiện.

Bài này đưa ra một lộ trình học theo từng lớp: hiểu cách biểu thức được thực thi, nắm cú pháp, làm việc với object và collection, truyền dữ liệu qua evaluation context, tích hợp vào Spring, rồi giới hạn quyền đánh giá để tránh biến biểu thức thành một điểm thực thi mã tùy ý.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Giải thích vai trò của parser, expression và evaluation context.
- Viết biểu thức dùng literal, toán tử, thuộc tính, index, method và điều kiện.
- Truyền root object, biến và function vào biểu thức.
- Dùng selection và projection để lọc hoặc biến đổi collection.
- Nhận biết cách SpEL được dùng trong `@Value` và các điểm tích hợp Spring.
- Chọn evaluation context phù hợp và giới hạn khả năng của biểu thức khi dữ liệu đầu vào không đáng tin cậy.

Nên biết Java cơ bản, object và collection, Spring IoC/Dependency Injection, cách Spring tạo bean và cách đọc annotation. Bạn không cần học toàn bộ Spring trước khi bắt đầu SpEL; chỉ cần hiểu bean là gì và một biểu thức được đánh giá trong runtime như thế nào.

## 2. Bức tranh tổng thể: một biểu thức được thực thi ra sao?

Quá trình cơ bản có ba phần:

1. **Parser** nhận chuỗi biểu thức và phân tích cú pháp.
2. **Expression** đại diện cho biểu thức đã được phân tích. Có thể yêu cầu expression trả về một giá trị hoặc đặt giá trị nếu ngữ cảnh cho phép.
3. **EvaluationContext** cung cấp dữ liệu và quyền mà biểu thức được phép sử dụng: root object, biến, function, property accessor, method resolver, type locator, bean resolver và cơ chế chuyển đổi kiểu.

Luồng thực thi có thể hình dung như sau:

    Chuỗi biểu thức
          |
          v
    SpelExpressionParser
          |
          v
    Expression (cây biểu thức đã phân tích)
          |
          v
    getValue(EvaluationContext)
          |
          v
    Kết quả hoặc lỗi đánh giá

Ví dụ tối giản:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("'Hello ' + 'Spring'");
    String result = expression.getValue(String.class);

Kết quả là `Hello Spring`. Ví dụ này không cần root object vì biểu thức chỉ thao tác trên literal.

Cần phân biệt lỗi phân tích và lỗi đánh giá. Lỗi phân tích xảy ra khi chuỗi không đúng cú pháp. Lỗi đánh giá xảy ra khi biểu thức hợp lệ nhưng dữ liệu hoặc quyền trong context không đáp ứng yêu cầu, ví dụ truy cập thuộc tính không tồn tại hoặc gọi method không phù hợp.

## 3. Giai đoạn một: làm chủ cú pháp nền tảng

### 3.1. Literal và kiểu dữ liệu

SpEL hỗ trợ các literal thường gặp như chuỗi, số, boolean và null. Chuỗi trong biểu thức dùng dấu nháy đơn:

- `'Spring'` là chuỗi.
- `42`, `3.14` là số.
- `true`, `false` là boolean.
- `null` là giá trị rỗng.

Các biểu thức có thể kết hợp literal bằng toán tử:

    10 + 5
    100 / 4
    'Spring' + ' Framework'
    7 > 3
    true and false

### 3.2. Toán tử

Các nhóm toán tử nên học theo thứ tự:

- Số học: `+`, `-`, `*`, `/`, `%`, `^`.
- So sánh: `==`, `!=`, `<`, `>`, `<=`, `>=`, `between`, `instanceof`, `matches`.
- Logic: `and`, `or`, `not` hoặc `!`.
- Điều kiện: `condition ? valueA : valueB`.
- Elvis: `value ?: fallback`, dùng giá trị dự phòng khi vế trái là null.

Ví dụ:

    #quantity > 0 and #price >= 0
    #score >= 80 ? 'pass' : 'retry'
    #displayName ?: 'Guest'

Các biểu thức so sánh và logic đặc biệt hữu ích khi biểu diễn điều kiện cấu hình. Với quy tắc nghiệp vụ dài, có nhiều nhánh hoặc cần debug phức tạp, nên chuyển logic về Java để dễ kiểm thử và bảo trì.

### 3.3. Truy cập thuộc tính, method và index

Khi root object là một đối tượng Java, biểu thức có thể đọc thuộc tính và gọi method:

    name
    customer.name
    customer.getName()
    customer.address.city
    customer.tags[0]
    settings['timeout']

Với map, key có thể được truy cập bằng cú pháp index. Với list hoặc array, index bắt đầu từ 0. Truy cập thuộc tính lồng nhau yêu cầu từng đối tượng trung gian tồn tại; nếu một mắt xích là null, phép truy cập thông thường có thể phát sinh lỗi.

Safe navigation `?.` giúp tránh lỗi khi đối tượng ngay trước toán tử là null:

    customer?.address?.city

Khi dùng safe navigation, kết quả tại nhánh null là null. Đừng xem toán tử này như một cơ chế kiểm tra dữ liệu hoàn chỉnh: vẫn cần xác định rõ trường hợp null có hợp lệ không và xử lý giá trị kết quả ở tầng gọi.

### 3.4. Tham chiếu kiểu và tạo object

Toán tử `T(...)` tham chiếu một kiểu Java theo tên đầy đủ. Ví dụ:

    T(java.lang.Math).max(12, 30)
    T(java.lang.Math).PI

SpEL cũng có cú pháp `new` để gọi constructor khi evaluation context cho phép:

    new java.math.BigDecimal('19.95')

Tham chiếu kiểu và constructor làm tăng đáng kể khả năng của biểu thức. Chỉ dùng chúng trong biểu thức do ứng dụng kiểm soát và trong context có quyền phù hợp. Không mở các khả năng này cho chuỗi do người dùng bên ngoài cung cấp.

## 4. Giai đoạn hai: root object, biến và function

### 4.1. Root object

Root object là đối tượng mặc định mà biểu thức truy cập khi tên thuộc tính không có tiền tố. Ví dụ, nếu root là `Order`, biểu thức `total` có thể đọc thuộc tính total của đơn hàng.

    Order order = ...;
    Expression expression = parser.parseExpression("total");
    Object total = expression.getValue(context, order);

Trong biểu thức, `#root` đại diện cho root object. `#this` đại diện cho đối tượng hiện tại tại vị trí đang đánh giá; trong một số thao tác collection, đối tượng hiện tại có thể khác root.

### 4.2. Biến

Biến có tiền tố `#`. Ứng dụng đặt biến vào context trước khi đánh giá:

    StandardEvaluationContext context = new StandardEvaluationContext();
    context.setVariable("quantity", 3);
    context.setVariable("price", 12.5);
    Expression expression = parser.parseExpression("#quantity * #price");
    Double total = expression.getValue(context, Double.class);

Dùng biến giúp biểu thức nhận dữ liệu rõ ràng mà không phải nhúng dữ liệu vào chuỗi. Cách này cũng làm cho việc kiểm thử dễ hơn vì mỗi lần đánh giá có thể cung cấp một context với dữ liệu riêng.

### 4.3. Function

Có thể đăng ký một method Java làm function trong context rồi gọi bằng cú pháp `#functionName(...)`. Function phải được ứng dụng đăng ký chủ động. Chỉ đăng ký các hàm nhỏ, có đầu vào và kết quả rõ ràng; tránh đưa một service tổng quát có nhiều tác dụng phụ vào expression context.

## 5. Giai đoạn ba: làm việc với collection

SpEL hỗ trợ thao tác trên list, array và collection. Hai khả năng quan trọng là selection và projection.

### 5.1. Selection — lọc phần tử

Selection dùng `.?[...]` để giữ lại các phần tử thỏa điều kiện. Ví dụ, với collection `orders` có thuộc tính `total`:

    orders.?[total > 100]

Hai biến thể hữu ích:

- `.^[...]` lấy phần tử đầu tiên thỏa điều kiện.
- `.$[...]` lấy phần tử cuối cùng thỏa điều kiện.

Trong predicate, `#this` đại diện cho phần tử đang được xét. Hãy viết điều kiện ngắn, có kiểu dữ liệu nhất quán và tránh gọi method có tác dụng phụ.

### 5.2. Projection — biến đổi phần tử

Projection dùng `.![]` để tạo collection kết quả từ một biểu thức áp dụng cho từng phần tử:

    orders.![customerName]
    products.![price]

Selection trả về những phần tử gốc thỏa điều kiện; projection trả về các giá trị được tính từ từng phần tử. Có thể kết hợp hai thao tác, nhưng nên tách biểu thức dài thành các bước Java để dễ đọc và kiểm thử.

### 5.3. Inline list và map

SpEL hỗ trợ khai báo collection ngay trong biểu thức:

    {1, 2, 3}
    {'red', 'green', 'blue'}
    {name: 'Spring', version: 6}

Inline collection phù hợp với cấu hình ngắn. Với dữ liệu lớn, thay đổi thường xuyên hoặc cần xác thực, hãy tạo collection ở Java rồi truyền vào context.

## 6. Giai đoạn bốn: tích hợp SpEL trong Spring

### 6.1. Dùng SpEL với `@Value`

`@Value` là một điểm tích hợp phổ biến. Biểu thức SpEL được đặt trong `#{...}`:

    @Value("#{2 * T(java.lang.Math).PI}")
    private double circumferenceFactor;

Ví dụ khác là đọc thuộc tính của một bean được Spring quản lý:

    @Value("#{@pricingPolicy.defaultRate}")
    private BigDecimal defaultRate;

Cú pháp `@beanName` tham chiếu bean thông qua bean resolver do Spring cung cấp. Điều đó có nghĩa biểu thức có thể phụ thuộc vào container và bean tương ứng phải tồn tại, có tên phù hợp.

### 6.2. Phân biệt placeholder và SpEL

Hai cú pháp thường xuất hiện gần nhau nhưng có mục đích khác nhau:

- `${app.name}` là placeholder để lấy giá trị cấu hình từ property source.
- `#{...}` là SpEL expression được đánh giá.

Placeholder thay thế giá trị cấu hình; SpEL thực hiện biểu thức trên giá trị và đối tượng trong context. Khi đọc `@Value`, hãy xác định rõ bạn cần lấy cấu hình đơn thuần hay cần tính toán/đọc object.

### 6.3. Template expression

Khi một chuỗi có cả văn bản thông thường và biểu thức, dùng template parsing. `TemplateParserContext` mặc định dùng `#{` và `}` làm dấu phân cách:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression(
        "Hello #{#name}", new TemplateParserContext());
    context.setVariable("name", "Spring");
    String message = expression.getValue(context, String.class);

Kết quả là `Hello Spring`. Template hữu ích cho chuỗi trình bày, nhưng nội dung template cũng phải là nội dung do ứng dụng kiểm soát nếu được đánh giá với context có nhiều quyền.

## 7. Giai đoạn năm: chọn EvaluationContext đúng

Evaluation context quyết định biểu thức có thể nhìn thấy và thực hiện những gì. Đây là điểm quan trọng nhất khi chuyển từ ví dụ học tập sang ứng dụng thực tế.

### 7.1. StandardEvaluationContext

`StandardEvaluationContext` cung cấp nhiều khả năng: root object, biến, function, property accessor, method resolver, type locator, constructor resolver và bean resolver. Nó phù hợp với trường hợp ứng dụng tin cậy hoàn toàn biểu thức và cần khả năng tùy biến rộng.

Vì có thể mở rộng tới truy cập kiểu, constructor, method và bean, context này có quyền rất mạnh. Không dùng nó để đánh giá trực tiếp biểu thức do người dùng, tenant hoặc nguồn bên ngoài gửi lên.

### 7.2. SimpleEvaluationContext

`SimpleEvaluationContext` được thiết kế cho các tình huống cần giới hạn tính năng, đặc biệt là data binding. Ví dụ context chỉ đọc thuộc tính:

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Có thể chọn chế độ read-write khi nghiệp vụ thực sự cần cập nhật thuộc tính và đã kiểm soát object đích. Simple context không cung cấp toàn bộ khả năng mạnh của Standard context; các tính năng cần quyền cao hơn phải được cấu hình có chủ đích và cần xem xét rủi ro trước khi bật.

### 7.3. Nguyên tắc cấp quyền tối thiểu

Khi thiết kế context, hãy tự trả lời:

1. Root object là gì? Có chứa dữ liệu nhạy cảm hoặc tham chiếu tới service không?
2. Biểu thức có cần gọi method hay chỉ đọc thuộc tính?
3. Có thật sự cần tham chiếu kiểu, constructor hoặc bean không?
4. Biến và function nào được phép xuất hiện?
5. Có thể dùng `SimpleEvaluationContext` thay cho `StandardEvaluationContext` không?
6. Kết quả có được kiểm tra kiểu và kiểm tra null trước khi sử dụng không?

Chỉ đưa vào context đúng dữ liệu và khả năng cần thiết cho một mục đích cụ thể. Không dùng một context toàn quyền dùng chung cho mọi loại biểu thức trong hệ thống.

## 8. Giai đoạn sáu: tích hợp an toàn

SpEL là ngôn ngữ biểu thức có khả năng truy cập object và gọi hành vi tùy theo context. Nếu ứng dụng lấy chuỗi từ người dùng rồi đánh giá bằng context nhiều quyền, biểu thức có thể trở thành một đường thực thi ngoài dự kiến.

### 8.1. Không đánh giá biểu thức không tin cậy bằng context toàn quyền

Không ghép input người dùng vào chuỗi biểu thức rồi gọi `parseExpression(...).getValue(...)`. Ví dụ thiết kế cần tránh là nhận một biểu thức tùy ý từ request, sau đó đánh giá nó bằng `StandardEvaluationContext` có bean resolver hoặc quyền gọi method.

Nếu sản phẩm thực sự cần người dùng định nghĩa điều kiện, hãy thiết kế một ngôn ngữ điều kiện giới hạn hoặc một tập biểu thức được cho phép. Xác thực cú pháp và dữ liệu không thay thế cho việc giới hạn quyền thực thi.

### 8.2. Dùng allowlist và context giới hạn

- Chỉ cho phép các thuộc tính đã định nghĩa; dùng DTO nhỏ thay vì truyền entity hoặc service lớn.
- Ưu tiên `SimpleEvaluationContext` với chế độ read-only khi chỉ cần đọc dữ liệu.
- Chỉ đăng ký function đã được rà soát và không có tác dụng phụ ngoài dự kiến.
- Không đăng ký bean resolver, type locator hoặc constructor resolver nếu use case không cần.
- Không cho phép biểu thức tự chọn class, bean hoặc method tùy ý.
- Giới hạn độ dài và số lượng biểu thức ở tầng ứng dụng để tránh đầu vào quá lớn.

### 8.3. Tách parse và evaluate

Nếu biểu thức là cấu hình cố định do ứng dụng sở hữu, có thể parse một lần và tái sử dụng `Expression`. Mỗi lần đánh giá nên nhận context cùng dữ liệu phù hợp với lần gọi đó. Tránh lưu context chứa dữ liệu request hoặc dữ liệu người dùng vào singleton rồi dùng lại cho request khác.

Không dùng việc parse một lần như bằng chứng rằng biểu thức an toàn. Parse chỉ kiểm tra cú pháp; quyền thực thi phụ thuộc vào context lúc đánh giá.

### 8.4. Kiểm tra kết quả và lỗi

Xử lý rõ các tình huống:

- Biểu thức sai cú pháp.
- Thuộc tính hoặc method không tồn tại.
- Giá trị null ở giữa đường dẫn.
- Kiểu kết quả không tương thích với kiểu đích.
- Index vượt phạm vi hoặc key không tồn tại.
- Method/function ném exception khi thực thi.

Không trả stack trace hoặc chi tiết nội bộ của bean cho client. Ghi log đủ thông tin để vận hành và debug nhưng tránh ghi dữ liệu nhạy cảm hoặc toàn bộ biểu thức có thể chứa bí mật.

### 8.5. Hạn chế tác dụng phụ

Ưu tiên biểu thức chỉ đọc và có kết quả xác định. Tránh method thay đổi trạng thái, gọi mạng, ghi database hoặc thực hiện thao tác tốn tài nguyên. Khi cần nghiệp vụ có tác dụng phụ, hãy gọi service từ Java theo luồng được kiểm soát thay vì ẩn hành vi đó trong expression.

## 9. Quy trình xây dựng một use case thực tế

Giả sử ứng dụng cần đánh giá điều kiện hiển thị một ưu đãi dựa trên dữ liệu đơn hàng. Có thể triển khai theo trình tự:

1. Xác định đầu vào tối thiểu: tổng tiền, trạng thái khách hàng và số lượng sản phẩm.
2. Tạo DTO chỉ chứa các thuộc tính cần đọc; không truyền toàn bộ entity graph hoặc Spring service.
3. Viết biểu thức ngắn, ví dụ `total >= 100 and customerLevel == 'GOLD'`.
4. Parse biểu thức cấu hình khi khởi tạo hoặc khi cấu hình được cập nhật.
5. Tạo context giới hạn, đặt root object hoặc biến có kiểu rõ ràng.
6. Đánh giá với kiểu kết quả mong đợi, ví dụ Boolean.
7. Xử lý null, lỗi parse và lỗi evaluate theo chính sách của ứng dụng.
8. Viết test cho trường hợp đúng, sai, null, dữ liệu biên và biểu thức không hợp lệ.

Nếu điều kiện được người dùng cuối tự nhập, cần có thiết kế allowlist riêng: xác định grammar được hỗ trợ, các trường được đọc, toán tử được dùng và giới hạn kích thước. Không chỉ kiểm tra chuỗi bằng regex rồi chuyển nó vào một context toàn quyền.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không parse được biểu thức | Sai dấu nháy, ngoặc hoặc toán tử | Thu nhỏ biểu thức và kiểm tra cú pháp từng phần |
| Không tìm thấy thuộc tính | Root object không đúng hoặc tên property sai | Kiểm tra object truyền vào `getValue` và accessor |
| NullPointerException khi đọc đường dẫn | Một thuộc tính trung gian là null | Dùng safe navigation ở vị trí phù hợp và xác định chính sách null |
| Không tìm thấy biến | Chưa gọi `setVariable` hoặc sai tên biến | Đối chiếu tên sau dấu `#` với context |
| Không tìm thấy bean | Bean chưa được đăng ký hoặc sai tên | Kiểm tra Spring context và bean resolver |
| Không chuyển được kiểu | Kiểu kết quả không tương thích | Yêu cầu kiểu kết quả rõ ràng và kiểm tra conversion |
| Biểu thức gọi được nhiều method ngoài dự kiến | Context được cấp quyền quá rộng | Thu hẹp context, root object và resolver |

Khi debug, hãy thử lần lượt: parse biểu thức độc lập, đánh giá với dữ liệu mẫu nhỏ, kiểm tra root object, kiểm tra biến, rồi mới thêm bean hoặc function. Cách này giúp khoanh vùng lỗi mà không làm tăng quyền của context chỉ để né lỗi.

## 11. Lộ trình thực hành theo từng chặng

| Chặng | Nội dung | Bài tập hoàn thành |
|---|---|---|
| 1. Cú pháp | Literal, toán tử, điều kiện, property và index | Viết biểu thức tính tổng, kiểm tra trạng thái và giá trị mặc định |
| 2. Context | Root object, `#this`, `#root`, biến và function | Đánh giá biểu thức trên DTO đơn giản |
| 3. Collection | Selection, projection, list và map | Lọc đơn hàng theo tổng tiền và lấy danh sách mã |
| 4. Spring | `@Value`, bean reference và template expression | Đọc cấu hình và tạo chuỗi từ biến |
| 5. Quyền đánh giá | Standard và Simple evaluation context | So sánh khả năng đọc thuộc tính và gọi method |
| 6. An toàn | Allowlist, input không tin cậy, lỗi và giới hạn | Tạo bộ đánh giá điều kiện chỉ đọc trên DTO |

Một bài tập tổng hợp tốt là tạo `OrderView` chỉ có `total`, `customerLevel` và `active`. Viết một biểu thức Boolean xác định ưu đãi có áp dụng hay không. Đánh giá biểu thức với `SimpleEvaluationContext` read-only, sau đó viết test cho khách hàng GOLD, khách hàng thường, tổng tiền bằng ngưỡng, tổng tiền dưới ngưỡng và dữ liệu null. Cuối cùng thử thay đổi biểu thức để tham chiếu kiểu hoặc gọi method và quan sát context giới hạn từ chối khả năng không được cấp.

## 12. Checklist trước khi đưa SpEL vào ứng dụng

- [ ] Biểu thức có ngắn, rõ và cần thiết cho cấu hình không?
- [ ] Chuỗi biểu thức có nguồn gốc tin cậy và có quy trình thay đổi không?
- [ ] Root object chỉ chứa dữ liệu cần thiết không?
- [ ] Đã chọn context có quyền tối thiểu chưa?
- [ ] Có thể dùng read-only `SimpleEvaluationContext` không?
- [ ] Đã tránh bean, class, constructor và method không cần thiết chưa?
- [ ] Kết quả có kiểu rõ ràng và có xử lý null không?
- [ ] Đã kiểm thử dữ liệu biên, lỗi parse và lỗi evaluate chưa?
- [ ] Biểu thức có tránh tác dụng phụ và thao tác tốn tài nguyên không?
- [ ] Log có tránh lộ dữ liệu nhạy cảm không?

## 13. Kết luận

Hãy học SpEL theo thứ tự từ cú pháp đến context rồi mới tới tích hợp Spring và bảo mật. Cú pháp giúp bạn viết được biểu thức; evaluation context quyết định biểu thức nhìn thấy và thực hiện được gì. Trong ứng dụng thực tế, chất lượng thiết kế nằm ở việc giữ biểu thức nhỏ, dữ liệu đầu vào rõ ràng và quyền đánh giá ở mức tối thiểu. Khi logic trở nên dài, khó kiểm thử hoặc có tác dụng phụ, hãy chuyển nó về Java để giữ hành vi dễ hiểu và dễ bảo trì.