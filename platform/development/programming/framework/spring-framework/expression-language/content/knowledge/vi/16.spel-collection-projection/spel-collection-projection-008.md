# Phân biệt projection với mapping trong mã Java

Projection trong SpEL và mapping trong Java đều có thể biến một tập đối tượng thành một tập giá trị mới. Ví dụ, từ danh sách đơn hàng, ta có thể lấy danh sách mã đơn, tên khách hàng hoặc tổng tiền. Kết quả nhìn bên ngoài có thể giống nhau, nhưng hai cơ chế khác nhau về cú pháp, thời điểm thực thi, kiểu dữ liệu, khả năng kiểm tra lúc biên dịch và phạm vi xử lý.

Trong SpEL, projection dùng cú pháp .![...]. Trong Java, mapping thường được thực hiện bằng map() của Stream API. Hiểu đúng hai cách này giúp chọn công cụ phù hợp: SpEL thuận tiện cho biểu thức ngắn được cấu hình hoặc đánh giá động; Java phù hợp với phép biến đổi phức tạp cần kiểu tĩnh, nhiều bước xử lý hoặc pipeline lớn.

## 1. Projection trong SpEL là gì?

Projection là thao tác áp dụng một biểu thức lên từng phần tử của collection để tạo ra kết quả tương ứng. Cú pháp cơ bản:

    collection.![projectionExpression]

Dấu chấm truy cập thao tác trên collection, dấu chấm than biểu thị projection, còn biểu thức trong ngoặc vuông được đánh giá cho từng phần tử.

Ví dụ, giả sử một đơn hàng có danh sách dòng hàng, mỗi dòng chứa sản phẩm và số lượng. Muốn lấy tên tất cả sản phẩm:

    lines.![product.name]

SpEL lần lượt lấy từng phần tử của lines, đọc product.name trên phần tử hiện tại và đưa kết quả vào collection đầu ra. Nếu danh sách đầu vào có năm dòng hàng, kết quả có năm giá trị tương ứng.

Projection không sửa các phần tử của collection nguồn. Nó tạo kết quả mới từ giá trị được tính cho mỗi phần tử. Nếu biểu thức trả về một thuộc tính, kết quả là tập các thuộc tính đó; nếu biểu thức tính toán, kết quả là tập các giá trị đã tính.

Ví dụ lấy tổng tiền của từng dòng hàng:

    lines.![unitPrice * quantity]

Ví dụ tạo nhãn từ nhiều thuộc tính:

    lines.![product.name + ' x ' + quantity]

Trong mỗi lần đánh giá, #this đại diện cho phần tử hiện tại. Vì vậy, biểu thức sau tương đương với ví dụ lấy tên sản phẩm:

    lines.![#this.product.name]

Viết tường minh #this hữu ích khi biểu thức lồng nhau hoặc khi cần phân biệt phần tử hiện tại với root object.

## 2. Mapping trong Java với Stream.map()

Trong Java, Stream API cung cấp phương thức map() để biến mỗi phần tử đầu vào thành một giá trị đầu ra. Ví dụ tương đương với việc lấy tên sản phẩm:

    List<String> productNames = order.getLines().stream()
            .map(LineItem::getProduct)
            .map(Product::getName)
            .collect(Collectors.toList());

Mỗi lời gọi map() nhận một Function và trả về một Stream mới chứa kết quả biến đổi. Có thể ghép nhiều bước map() để đi qua các thuộc tính hoặc chuyển đổi dữ liệu. collect() là thao tác kết thúc pipeline và thu kết quả thành một List.

Nếu chỉ cần một bước, có thể viết:

    List<String> productNames = order.getLines().stream()
            .map(line -> line.getProduct().getName())
            .collect(Collectors.toList());

Cách viết này biểu đạt rõ rằng mỗi LineItem được chuyển thành tên Product. Java compiler kiểm tra các kiểu của method reference, lambda và kết quả dựa trên khai báo generic.

## 3. Cùng một bài toán bằng SpEL và Java

Giả sử root object là Order, có property lines kiểu List<LineItem>. Mỗi LineItem có product, còn Product có name.

### Cách viết bằng SpEL

    ExpressionParser parser = new SpelExpressionParser();

    EvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Expression expression =
            parser.parseExpression("lines.![product.name]");

    List<?> productNames =
            expression.getValue(context, order, List.class);

Ở đây, lines được đọc từ root object order. Projection chạy biểu thức product.name trên từng LineItem và trả về collection kết quả.

Nếu dùng biến thay cho root property:

    context.setVariable("order", order);

    Expression expression =
            parser.parseExpression("#order.lines.![product.name]");

Biến được tham chiếu bằng tiền tố #. Property path bên trong projection vẫn được đánh giá trên từng dòng hàng.

### Cách viết bằng Java

    List<String> productNames = order.getLines().stream()
            .map(line -> line.getProduct().getName())
            .collect(Collectors.toList());

Hai cách đều tạo danh sách tên sản phẩm theo thứ tự duyệt của nguồn. Tuy nhiên, SpEL biểu diễn phép biến đổi trong một chuỗi biểu thức; Java biểu diễn nó bằng các hàm có kiểu và được compiler kiểm tra.

## 4. #this và root object trong projection

Trong biểu thức SpEL thông thường, #root tham chiếu đối tượng gốc của lần đánh giá. Khi đi vào projection, #this thay đổi theo từng phần tử đang được xử lý.

Ví dụ:

    lines.![#this.product.name]

Trong mỗi lượt:

- #this là một LineItem hiện tại.
- #this.product là Product của dòng hàng đó.
- #this.product.name là tên sản phẩm được đưa vào kết quả.

Nếu cần kết hợp dữ liệu của phần tử hiện tại với một thuộc tính trên Order gốc:

    lines.![#this.quantity * #root.exchangeRate]

Ở đây, quantity thuộc LineItem hiện tại; exchangeRate thuộc root object Order. Việc dùng đúng #this và #root giúp tránh đọc nhầm property trên đối tượng sai cấp.

Trong Java Stream, lambda nhận phần tử hiện tại thông qua tham số:

    order.getLines().stream()
            .map(line -> line.getQuantity() * order.getExchangeRate())
            .collect(Collectors.toList());

Tham số line giữ vai trò tương tự #this; biến order được tham chiếu từ phạm vi bên ngoài giữ vai trò dữ liệu gốc mà lambda cần dùng.

## 5. Projection không giống Selection

Projection và Selection thường được dùng nối tiếp, nhưng có mục đích khác nhau:

- Projection (.![...]) biến đổi từng phần tử và tạo kết quả cho mỗi phần tử.
- Selection (.?[...]) lọc phần tử theo điều kiện và giữ lại những phần tử thỏa điều kiện.

Ví dụ chỉ lấy tên sản phẩm từ các dòng hàng có số lượng lớn hơn 1:

    lines.?[quantity > 1].![product.name]

SpEL thực hiện selection trước, sau đó projection trên tập kết quả đã lọc.

Java có thể biểu đạt cùng quy trình bằng filter() rồi map():

    List<String> productNames = order.getLines().stream()
            .filter(line -> line.getQuantity() > 1)
            .map(line -> line.getProduct().getName())
            .collect(Collectors.toList());

Nếu dùng map() mà không filter(), Java vẫn biến đổi tất cả phần tử. Nếu dùng projection mà không selection, SpEL cũng tạo kết quả cho tất cả phần tử đầu vào. Không nên nhầm việc chọn thuộc tính với việc lọc phần tử.

## 6. Khác biệt về kiểu dữ liệu và kiểm tra lúc biên dịch

Java Stream API sử dụng generic và kiểu hàm. Ví dụ:

    Stream<LineItem> lines = order.getLines().stream();

    Stream<String> names = lines.map(LineItem::getProduct)
            .map(Product::getName);

Compiler biết đầu vào là LineItem, kết quả cuối là String. Nếu gọi một method không tồn tại trên Product hoặc trả về kiểu không tương thích, lỗi thường được phát hiện ngay khi biên dịch.

SpEL là ngôn ngữ biểu thức được phân tích và đánh giá lúc chạy. Chuỗi:

    lines.![product.name]

không được Java compiler kiểm tra property product hoặc name. Nếu kiểu runtime không có property đó, lỗi chỉ xuất hiện khi SpEL đánh giá biểu thức.

Khi nhận kết quả từ SpEL qua getValue, ứng dụng có thể yêu cầu một kiểu đích, nhưng điều đó không biến toàn bộ biểu thức thành kiểu tĩnh như Java generic. Cần kiểm thử biểu thức với dữ liệu thực tế và xử lý lỗi đánh giá phù hợp.

## 7. Khác biệt về thời điểm thực thi

Một pipeline Stream trong Java thường là lazy. Các bước map() và filter() chỉ mô tả pipeline; phần lớn công việc được thực hiện khi gọi terminal operation như collect(), count() hoặc forEach().

Ví dụ:

    Stream<String> names = order.getLines().stream()
            .map(line -> line.getProduct().getName());

    List<String> result = names.collect(Collectors.toList());

Phép biến đổi được thực hiện khi collect() tiêu thụ stream.

SpEL projection được đánh giá khi gọi getValue(). Khi lần đánh giá hoàn tất, kết quả projection đã được tạo ra. Nó không trả về một Java Stream lazy để tiếp tục ghép các bước xử lý theo Stream API.

Điều này có ý nghĩa khi dữ liệu lớn hoặc phép biến đổi tốn kém. Java Stream hỗ trợ pipeline lazy và có thể kết hợp với parallel stream khi phù hợp. Projection của SpEL hướng đến việc đánh giá biểu thức trên dữ liệu được cung cấp, không phải thay thế cơ chế xử lý stream cho khối lượng dữ liệu lớn.

## 8. Projection trên Map và collection

Projection không chỉ dùng với List. SpEL hỗ trợ projection trên collection và array. Với Map, biểu thức projection được đánh giá trên từng Map.Entry; kết quả là collection các giá trị được chiếu ra.

Ví dụ, nếu map prices chứa mã sản phẩm làm key và giá làm value:

    #prices.![#this.key + ':' + #this.value]

Biểu thức tạo các chuỗi kết hợp key và value của từng entry. #this trong trường hợp này là Map.Entry hiện tại.

Cần nhớ rằng projection trên Map không phải thao tác giữ nguyên cấu trúc key-value như một phép map-to-map. Kết quả projection là collection các giá trị được tính. Nếu cần xây dựng một Map mới với key được giữ lại hoặc biến đổi theo quy tắc phức tạp, Java Stream cùng Collectors.toMap() thường rõ ràng hơn.

Ví dụ Java tạo Map mới:

    Map<String, BigDecimal> normalizedPrices =
            prices.entrySet().stream()
                    .collect(Collectors.toMap(
                            Map.Entry::getKey,
                            entry -> entry.getValue().setScale(2)
                    ));

Khi cần giữ cấu trúc dữ liệu hoặc kiểm soát trường hợp key trùng, hãy xử lý rõ trong Java thay vì giả định projection sẽ bảo toàn Map.

## 9. Xử lý null trong projection và mapping

Một property trung gian có thể null. Ví dụ, product có thể null hoặc name có thể null. Projection thông thường:

    lines.![product.name]

có thể lỗi nếu product của một dòng hàng là null.

Có thể dùng null-safe navigation để bảo vệ property có thể thiếu:

    lines.![#this?.product?.name]

Nếu một phần tử của collection là null, #this?.product giúp phép truy cập trả về null cho phần tử đó. Nếu chỉ product có thể null, có thể viết:

    lines.![product?.name]

Trong Java, cần thể hiện rõ cách xử lý null bằng filter, Optional hoặc điều kiện trong lambda:

    List<String> productNames = order.getLines().stream()
            .filter(Objects::nonNull)
            .map(LineItem::getProduct)
            .filter(Objects::nonNull)
            .map(Product::getName)
            .collect(Collectors.toList());

Hai cách có thể cho kết quả khác nhau nếu chọn bỏ phần tử null hoặc giữ lại null trong collection kết quả. Hãy quyết định rõ hợp đồng đầu ra: giữ vị trí với giá trị null, loại bỏ phần tử thiếu dữ liệu, hay dùng một giá trị mặc định.

Nếu collection đầu vào itself là null, cần kiểm tra trước khi gọi projection hoặc tạo stream. Null-safe navigation trên property của từng phần tử không tự xử lý một collection gốc null.

## 10. Projection và mapping có làm thay đổi dữ liệu nguồn không?

Thông thường, cả projection của SpEL và map() của Java đều tạo ra kết quả biến đổi mà không tự sửa collection nguồn. Ví dụ:

    lines.![product.name]

chỉ đọc tên sản phẩm và tạo collection kết quả. Nó không đổi product.name trong các LineItem.

Tương tự:

    order.getLines().stream()
            .map(LineItem::getQuantity)
            .collect(Collectors.toList());

tạo danh sách số lượng; nó không cập nhật các dòng hàng ban đầu.

Tuy nhiên, nếu biểu thức gọi method có side effect hoặc lambda Java thay đổi object được tham chiếu, hành vi có thể khác. Vì vậy, nên dùng property/getter thuần đọc trong projection và dùng map() cho phép biến đổi giá trị rõ ràng. Nếu mục tiêu là cập nhật object hiện có, hãy thực hiện bằng logic Java có chủ đích, dễ kiểm thử và kiểm soát giao dịch.

## 11. Projection không phải database projection

Projection trong SpEL hoạt động trên collection hoặc array đang có trong bộ nhớ của lần đánh giá. Nó không tự chuyển biểu thức thành SQL, không yêu cầu JPA chỉ lấy một số cột, và không tự tối ưu truy vấn cơ sở dữ liệu.

Ví dụ:

    order.lines.![product.name]

chỉ đọc product.name trên các dòng hàng mà object graph đã cung cấp. Nếu order.lines là quan hệ lazy của JPA, việc truy cập có thể kích hoạt tải dữ liệu tùy cấu hình ORM. SpEL không tự tránh N+1 query hoặc bảo đảm chỉ một truy vấn được thực hiện.

Nếu cần database projection thực sự, hãy dùng DTO projection, JPQL constructor expression, interface projection của Spring Data hoặc truy vấn SQL phù hợp. Hãy lấy đúng dữ liệu ở tầng persistence, sau đó dùng SpEL hoặc Java để xử lý phần biểu thức cần thiết.

## 12. Khi nào nên dùng SpEL projection?

SpEL projection phù hợp khi:

- Quy tắc biến đổi ngắn và dễ đọc.
- Biểu thức được dùng trong cấu hình Spring hoặc một tính năng đã tích hợp SpEL.
- Cần lấy một property hoặc tính một giá trị đơn giản trên từng phần tử.
- Dữ liệu đầu vào đã được chuẩn bị trong memory.
- Muốn quản lý phép chiếu như một biểu thức có thể cấu hình và kiểm thử riêng.

Ví dụ:

    members.![name]
    orders.![total * taxRate]
    lines.?[quantity > 0].![product.name]

Không nên dồn vào SpEL khi:

- Phép biến đổi có nhiều bước, nhiều nhánh hoặc cần xử lý lỗi chi tiết.
- Cần tạo Map mới với quy tắc key phức tạp hoặc xử lý key trùng.
- Cần grouping, partitioning, flatMap, parallel processing hoặc pipeline lớn.
- Cần kiểu dữ liệu được compiler kiểm tra chặt chẽ.
- Phép biến đổi có side effect hoặc cần cập nhật trạng thái domain.

Trong các trường hợp này, Java Stream, collector hoặc một phương thức domain có tên rõ ràng thường dễ bảo trì hơn.

## 13. Bảng so sánh nhanh

| Tiêu chí | SpEL projection | Java Stream mapping |
|---|---|---|
| Cú pháp | .![expression] | map(function) |
| Đầu vào | Collection, array hoặc Map | Stream của các phần tử |
| Biến đổi | Biểu thức được đánh giá cho từng phần tử | Function hoặc method reference |
| Kiểu dữ liệu | Phân giải chủ yếu lúc chạy | Generic và compiler kiểm tra lúc biên dịch |
| Thực thi | Khi gọi getValue() | Lazy cho đến terminal operation |
| Kết quả | Collection kết quả của projection | Stream mới, sau đó có thể collect |
| Xử lý Map | Chiếu từng Map.Entry thành giá trị | Có thể dùng entrySet() và Collectors |
| Pipeline nâng cao | Tập trung vào biểu thức | filter, flatMap, grouping, partitioning, parallel |
| Phù hợp | Rule ngắn, cấu hình động | Logic biến đổi phức tạp, cần kiểu tĩnh |

## 14. Kiểm thử và vận hành

Dù dùng SpEL hay Java, phép biến đổi collection cần được kiểm tra với dữ liệu đại diện:

- Collection có nhiều phần tử để xác nhận thứ tự và số lượng kết quả.
- Collection rỗng để xác nhận kết quả rỗng.
- Phần tử null hoặc property trung gian null để xác nhận chính sách xử lý.
- Property có giá trị biên hoặc kiểu dữ liệu không như mong đợi.
- Map có key/value thiếu hoặc key trùng nếu đang tạo Map mới.
- Collection lớn để đánh giá chi phí và lựa chọn cách xử lý phù hợp.

Với SpEL, cần kiểm tra cả parse và evaluate. Chuỗi có thể parse thành công nhưng vẫn lỗi khi property không tồn tại trên kiểu runtime hoặc khi dữ liệu null. Nên parse biểu thức ổn định một lần, đánh giá với context phù hợp và chỉ cung cấp những property cần thiết.

Với Java Stream, compiler giúp phát hiện nhiều lỗi kiểu sớm hơn, nhưng vẫn cần kiểm thử logic lambda, null handling và collector. Đặc biệt, nếu dùng parallel stream, cần xem xét tính thread-safe và thứ tự kết quả.

## Kết luận

Projection trong SpEL dùng .![...] để áp dụng một biểu thức lên từng phần tử và tạo collection kết quả. Mapping trong Java thường dùng Stream.map() với lambda hoặc method reference. Hai cách có thể tạo ra dữ liệu giống nhau, nhưng khác nhau ở kiểu tĩnh, thời điểm thực thi, khả năng ghép pipeline và cách kiểm soát lỗi.

Hãy dùng SpEL projection cho phép chiếu ngắn, dễ cấu hình trên dữ liệu đã có trong bộ nhớ. Dùng Java mapping khi cần compiler kiểm tra kiểu, pipeline nhiều bước, collector, grouping hoặc logic domain phức tạp. Cả hai đều không tự biến thành database projection và không tự sửa dữ liệu nguồn; hãy đặt việc truy vấn, biến đổi và cập nhật ở đúng tầng chịu trách nhiệm.