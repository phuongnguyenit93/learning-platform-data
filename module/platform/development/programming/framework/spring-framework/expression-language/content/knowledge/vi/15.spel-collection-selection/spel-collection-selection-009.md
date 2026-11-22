# Chi phí duyệt collection và kiểm soát dữ liệu lớn

## 1. Selection và projection đều phải duyệt dữ liệu

Spring Expression Language (SpEL) hỗ trợ hai thao tác quan trọng trên collection:

- **Selection** lọc phần tử theo một điều kiện.
- **Projection** biến đổi mỗi phần tử thành một giá trị hoặc một cấu trúc khác.

Ví dụ:

    members.?[active == true]

Biểu thức selection giữ lại các thành viên có active bằng true.

Ví dụ projection:

    members.![name]

Biểu thức projection lấy property name của từng thành viên để tạo collection kết quả.

Hai thao tác này giúp viết biểu thức ngắn gọn, nhưng chúng vẫn phải xử lý dữ liệu đầu vào. Với collection có n phần tử, một lần selection hoặc projection thông thường cần duyệt qua các phần tử liên quan. Vì vậy, kích thước collection và chi phí của biểu thức bên trong quyết định phần lớn thời gian thực thi.

SpEL không biến selection thành một truy vấn database tự động. Nếu collection đã được tải vào bộ nhớ, SpEL duyệt dữ liệu đang có trong ứng dụng.

## 2. Độ phức tạp cơ bản

Giả sử collection có n phần tử.

| Thao tác | Công việc chính | Độ phức tạp thường gặp |
| --- | --- | --- |
| Selection tất cả phần tử phù hợp | Kiểm tra điều kiện trên từng phần tử | O(n) |
| Projection | Đánh giá biểu thức cho từng phần tử | O(n) |
| Select first | Tìm phần tử phù hợp đầu tiên | O(n) trong trường hợp xấu nhất |
| Select last | Tìm phần tử phù hợp cuối cùng | O(n) |
| Truy cập một phần tử bằng index của List | Truy cập phần tử theo vị trí | Thường O(1) với ArrayList; phụ thuộc loại collection |

Ví dụ:

    members.?[active == true]

Nếu collection có 100 phần tử, điều kiện có thể được kiểm tra tối đa khoảng 100 lần.

Nếu collection có 100.000 phần tử, số lần kiểm tra tăng tương ứng. Việc dùng cú pháp SpEL ngắn hơn không làm giảm số lượng phần tử cần kiểm tra.

Đây là mô hình chi phí để phân tích thiết kế. Thời gian thực tế còn phụ thuộc vào loại collection, property accessor, kiểu dữ liệu, nội dung điều kiện và chi phí của method được gọi trong biểu thức.

## 3. Chi phí của điều kiện selection

Mỗi phần tử được selection kiểm tra bằng expression nằm trong dấu ngoặc vuông.

Ví dụ:

    orders.?[total >= 1000]

Điều kiện đơn giản chỉ đọc property total và so sánh với một literal. Nếu collection có n đơn hàng, SpEL cần đánh giá điều kiện trên các phần tử đó.

Một điều kiện phức tạp hơn:

    orders.?[
        customer.account.manager.department.name == 'Sales'
    ]

có thể phải đi qua nhiều property trung gian cho mỗi order.

Nếu đường dẫn property có nhiều tầng, chi phí truy cập và kiểm tra null có thể lớn hơn điều kiện chỉ đọc một field đơn giản.

Điều kiện có lời gọi method:

    orders.?[customer.isEligible()]

có thể tốn nhiều thời gian hơn nếu isEligible thực hiện tính toán hoặc truy cập dịch vụ. Nếu method đó gọi database hoặc API bên ngoài, chi phí có thể tăng rất mạnh vì nó được thực hiện lặp lại theo từng phần tử cần kiểm tra.

Nguyên tắc: giữ predicate đơn giản, có thể dự đoán và tránh thao tác I/O trong selection.

## 4. Chi phí của projection

Projection tạo ra một giá trị kết quả cho mỗi phần tử nguồn.

Ví dụ:

    members.![name]

Với n thành viên, SpEL cần đánh giá expression name trên từng thành viên và tạo collection kết quả tương ứng.

Nếu projection thực hiện phép tính:

    orders.![total * taxRate]

mỗi phần tử cần đọc total, đọc taxRate và tính kết quả.

Nếu projection gọi method:

    members.![getDisplayName()]

method được gọi cho từng phần tử được xử lý. Hãy xem xét chi phí của method đó trước khi dùng với collection lớn.

Projection thường tạo ra collection kết quả trong bộ nhớ. Vì vậy, ngoài thời gian duyệt, ứng dụng còn phải trả chi phí cấp phát và lưu trữ các giá trị kết quả.

Nếu chỉ cần kiểm tra một điều kiện hoặc lấy một property, hãy tránh tạo projection trung gian rồi tiếp tục duyệt kết quả nếu có thể biểu diễn trực tiếp mục tiêu trong một expression hoặc xử lý Java rõ ràng hơn.

## 5. Kết hợp selection và projection

Một luồng phổ biến là lọc dữ liệu rồi lấy một phần thông tin:

    members.?[active == true].![name]

Với cách viết này, SpEL thực hiện hai công việc:

1. Duyệt collection để tìm các thành viên active.
2. Duyệt các phần tử phù hợp để lấy name.

Nếu n là số phần tử đầu vào và k là số phần tử được chọn, số lần xử lý có thể hình dung là n + k. Vì k không lớn hơn n, độ phức tạp tổng thể vẫn là O(n), nhưng có thêm chi phí tạo collection selection và collection projection.

Khi dữ liệu lớn, các collection trung gian có thể làm tăng lượng bộ nhớ sử dụng.

Nếu chỉ cần danh sách tên của các thành viên active, biểu thức kết hợp vẫn dễ đọc. Nhưng nếu cần xử lý nhiều bước, nhiều điều kiện hoặc nhiều lần chuyển đổi, hãy đo chi phí thực tế và cân nhắc thực hiện bằng Java Stream hoặc một truy vấn dữ liệu chuyên biệt.

Không nên kết luận rằng một chuỗi expression dài luôn nhanh hơn một đoạn Java tương đương. Hãy so sánh trên dữ liệu và môi trường thực tế.

## 6. Selection lồng nhau có thể tăng chi phí nhanh

Giả sử mỗi phòng ban có một danh sách nhân viên. Có thể viết:

    departments.?[
        employees.?[active == true].size() > 0
    ]

Nếu có d phòng ban và mỗi phòng ban có trung bình m nhân viên, biểu thức có thể phải duyệt gần d × m nhân viên để kiểm tra điều kiện.

Độ phức tạp có thể xấp xỉ:

    O(d × m)

Nếu còn lồng thêm collection khác, số lần xử lý có thể tiếp tục nhân lên.

Ví dụ:

    departments.?[
        teams.?[
            members.?[active == true].size() > 0
        ].size() > 0
    ]

Biểu thức này đi qua nhiều tầng collection. Với dữ liệu lớn, số lần đánh giá predicate có thể tăng đáng kể.

Hãy xác định rõ:

- Collection ngoài có bao nhiêu phần tử?
- Mỗi phần tử chứa collection con kích thước bao nhiêu?
- Có bao nhiêu tầng selection hoặc projection?
- Predicate bên trong có gọi method hoặc truy cập property tốn kém không?

Nếu một biểu thức lồng nhau khó ước lượng số lần duyệt, nên tách logic thành các bước có thể đo và kiểm thử riêng.

## 7. Select first và select last

SpEL cung cấp các dạng selection đặc biệt:

    members.^[active == true]

Chọn phần tử phù hợp đầu tiên.

    members.$[active == true]

Chọn phần tử phù hợp cuối cùng.

Hai dạng này hữu ích khi chỉ cần một kết quả thay vì toàn bộ collection đã lọc.

Select first có thể dừng khi tìm được phần tử phù hợp đầu tiên; trong trường hợp không có phần tử phù hợp, nó vẫn phải xét hết collection. Select last cần tiếp tục kiểm tra để xác định phần tử phù hợp cuối cùng.

Do đó:

- Nếu chỉ cần phần tử phù hợp đầu tiên, dùng select first thay vì selection toàn bộ rồi lấy index 0.
- Nếu cần phần tử phù hợp cuối cùng, dùng select last thay vì tạo toàn bộ kết quả selection rồi lấy phần tử cuối.
- Nếu cần tất cả kết quả, dùng selection thông thường.

Ví dụ:

    members.^[active == true]

thể hiện trực tiếp mục tiêu lấy một phần tử phù hợp đầu tiên.

Không nên tạo collection trung gian chỉ để lấy một phần tử nếu có toán tử SpEL thể hiện đúng ý định.

## 8. Chi phí bộ nhớ và collection kết quả

Selection và projection có thể tạo collection mới. Kích thước kết quả phụ thuộc vào thao tác:

- Selection tạo kết quả gồm các phần tử thỏa điều kiện.
- Projection tạo kết quả chứa giá trị được tính cho từng phần tử nguồn.
- Select first và select last chỉ cần trả về một kết quả hoặc null.

Nếu selection giữ lại k phần tử, bộ nhớ bổ sung thường tỷ lệ với k. Nếu projection tạo một giá trị cho mỗi phần tử, bộ nhớ kết quả thường tỷ lệ với n.

Khi một expression vừa selection vừa projection, có thể tồn tại collection trung gian và collection cuối cùng. Với dữ liệu lớn, cần xem xét cả peak memory chứ không chỉ thời gian chạy.

Ví dụ:

    members.?[active == true].![name]

có thể tạo một collection chứa các member phù hợp, sau đó tạo collection tên. Nếu số lượng member lớn, hai collection có thể làm tăng áp lực bộ nhớ trong quá trình đánh giá.

Nếu chỉ cần đếm hoặc kiểm tra sự tồn tại, hãy tránh materialize toàn bộ kết quả khi có thể dùng một cách xử lý phù hợp hơn với mục tiêu.

## 9. SpEL không thay thế truy vấn database

Một lỗi thiết kế phổ biến là tải toàn bộ dữ liệu về rồi mới dùng SpEL để lọc:

    allOrders.?[status == 'PAID']

Nếu allOrders chứa hàng trăm nghìn đơn hàng, ứng dụng vẫn phải:

1. Đọc dữ liệu từ database.
2. Tạo hoặc giữ collection trong bộ nhớ.
3. Duyệt các phần tử bằng SpEL.
4. Tạo collection kết quả.

Selection của SpEL không tự động chuyển thành SQL WHERE, không tự thêm index database và không tự phân trang dữ liệu.

Với dữ liệu lớn, nên đẩy điều kiện lọc xuống tầng lưu trữ nếu nghiệp vụ cho phép:

    SELECT *
    FROM orders
    WHERE status = 'PAID'
    LIMIT 100;

Database có thể tận dụng index, query planner và giới hạn kết quả. Sau đó SpEL chỉ xử lý tập dữ liệu đã được thu hẹp nếu vẫn cần biểu thức động.

Hãy phân chia trách nhiệm:

- Database: lọc, sắp xếp, phân trang và chỉ lấy các trường cần thiết.
- Service: kiểm tra quyền, điều phối và áp dụng quy tắc nghiệp vụ.
- SpEL: đánh giá rule hoặc biểu thức trên tập dữ liệu đã được chọn phù hợp.

## 10. Giới hạn dữ liệu bằng pagination và projection ở tầng truy vấn

Khi không cần toàn bộ dữ liệu, hãy truy vấn theo trang:

    Page<Order> page =
        orderRepository.findByStatus(
            OrderStatus.PAID,
            PageRequest.of(0, 100)
        );

Sau đó mới áp dụng SpEL trên nội dung của trang nếu cần.

Ví dụ:

    List<Order> eligible = parser
        .parseExpression("?[total >= #minimum]")
        .getValue(context, page.getContent(), List.class);

Ví dụ trên chỉ nhằm minh họa việc giới hạn collection đầu vào. Trong ứng dụng thực tế, có thể chọn lọc bằng repository hoặc Java trước khi gọi SpEL, tùy API và loại dữ liệu.

Nếu chỉ cần một vài thuộc tính, dùng DTO hoặc query projection để database trả về đúng các cột cần thiết thay vì tải toàn bộ entity graph.

Cần cẩn thận với lazy loading: nếu predicate truy cập một quan hệ chưa được tải, mỗi phần tử có thể kích hoạt thêm truy vấn. Đây là tình huống N+1 query có thể làm chi phí tăng mạnh dù expression nhìn rất ngắn.

Hãy kiểm tra SQL thực tế và số lượng truy vấn khi selection/projection truy cập quan hệ ORM.

## 11. Parse một lần, đánh giá nhiều lần

Không nên tạo parser và parse lại cùng một chuỗi trong mỗi vòng lặp nếu expression không thay đổi.

Cách dễ gây lãng phí:

    for (Order order : orders) {
        Expression expression =
            new SpelExpressionParser()
                .parseExpression("total >= 1000");

        boolean eligible =
            expression.getValue(order, Boolean.class);
    }

Cách phù hợp hơn:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("total >= 1000");

    for (Order order : orders) {
        boolean eligible =
            expression.getValue(order, Boolean.class);
    }

Parsing tạo cấu trúc expression. Giữ lại Expression cho phép tái sử dụng kết quả parsing và tránh lặp lại công việc đó.

Nếu expression có variables, hãy truyền EvaluationContext phù hợp cho từng lần đánh giá. Không đưa dữ liệu của request này vào context dùng chung cho request khác khi chưa kiểm soát an toàn state và concurrency.

Parse-once không loại bỏ chi phí duyệt collection hoặc evaluation. Nó chỉ tránh chi phí parse lặp lại.

## 12. Giữ predicate đơn giản và tránh side effect

Selection và projection gọi expression lặp lại trên nhiều phần tử. Vì vậy, predicate và projection nên có hành vi rõ ràng, dễ dự đoán.

Nên ưu tiên:

    orders.?[status == 'PAID' and total >= #minimum]

Cần thận trọng với:

    orders.?[customer.loadLatestStatus() == 'ACTIVE']

Nếu loadLatestStatus gọi database hoặc API, nó có thể được thực hiện nhiều lần. Một collection lớn có thể dẫn đến số lượng lời gọi rất lớn.

Không nên dùng method có side effect trong predicate, ví dụ cập nhật trạng thái, gửi message hoặc ghi log nghiệp vụ như một phần bắt buộc của quá trình lọc. Selection có mục tiêu chọn phần tử; nó không phải cơ chế điều phối side effect.

Nếu dữ liệu cần được làm giàu từ nguồn ngoài, hãy thực hiện ở service với batching hoặc caching phù hợp, rồi đưa kết quả vào expression context.

## 13. Kiểm soát EvaluationContext và property access

Chi phí evaluation còn phụ thuộc vào cách SpEL tìm và đọc dữ liệu.

Các yếu tố có thể ảnh hưởng:

- PropertyAccessor phải giải quyết property trên object.
- MethodResolver có thể phải tìm method phù hợp.
- TypeConverter có thể chuyển đổi kiểu trong quá trình đánh giá.
- Variable và function được tra cứu trong EvaluationContext.
- Property lồng nhau có thể dẫn tới nhiều lần truy cập cho mỗi phần tử.

Với một expression được đánh giá nhiều lần, việc dùng context và accessor phù hợp có thể ảnh hưởng hiệu năng.

Tuy nhiên, không nên mở rộng quyền truy cập chỉ để làm expression chạy được. Với biểu thức do người dùng hoặc cấu hình bên ngoài cung cấp, hãy giới hạn object, variable, property accessor và method resolver theo đúng nghiệp vụ.

Tối ưu hiệu năng phải giữ nguyên các giới hạn truy cập cần thiết.

## 14. Compiler và tối ưu hiệu năng

SpEL có compiler với các mode như OFF, IMMEDIATE và MIXED. Compiler có thể cải thiện tốc độ cho những expression và kiểu dữ liệu phù hợp.

Tuy nhiên, không phải mọi biểu thức đều có thể compile. Các expression phụ thuộc kiểu dữ liệu thay đổi, accessor tùy chỉnh hoặc cấu trúc phức tạp có thể không phù hợp với compiler.

Không nên bật compiler chỉ vì collection lớn. Trước tiên cần xác định phần tốn thời gian là:

- Parsing lặp lại.
- Duyệt collection.
- Property hoặc method access.
- Truy vấn database phát sinh trong predicate.
- Cấp phát collection kết quả.
- Chuyển đổi kiểu hoặc logic nghiệp vụ.

Sau khi đo, mới thử compiler mode trên workload đại diện và so sánh kết quả. Compiler không thể thay thế việc giảm kích thước dữ liệu đầu vào hoặc loại bỏ I/O lặp lại.

## 15. Đo lường thay vì đoán

Khi tối ưu selection/projection, hãy đo trên dữ liệu có kích thước và phân bố gần môi trường thật.

Nên theo dõi:

- Số phần tử đầu vào.
- Số phần tử được chọn.
- Thời gian parse và thời gian evaluation riêng biệt.
- Thời gian predicate cho mỗi phần tử.
- Số lần gọi method hoặc truy vấn database.
- Bộ nhớ tăng thêm do collection kết quả.
- Số lần truy vấn SQL và hiện tượng N+1.
- Latency trung bình và percentile cao khi chạy đồng thời.

Một benchmark nhỏ có thể dùng để so sánh các biểu thức:

    ExpressionParser parser = new SpelExpressionParser();

    Expression selection =
        parser.parseExpression("?[active == true]");

    long start = System.nanoTime();

    List<?> result = selection.getValue(
        context,
        members,
        List.class
    );

    long elapsed = System.nanoTime() - start;

    System.out.println("Matched: " + result.size());
    System.out.println("Elapsed ns: " + elapsed);

Đoạn code chỉ minh họa cách lấy thời gian một lần. Để benchmark đáng tin cậy, cần warm-up JVM, chạy nhiều lần, dùng dữ liệu đại diện và tránh ảnh hưởng của logging hoặc các tác vụ khác. JMH phù hợp hơn cho benchmark vi mô cần so sánh chính xác.

## 16. Checklist khi xử lý collection lớn

Trước khi dùng selection hoặc projection trên collection lớn, hãy tự kiểm tra:

1. Collection đầu vào có thực sự cần tải toàn bộ không?
2. Có thể lọc hoặc phân trang ở database hay tầng repository không?
3. Predicate có gọi method tốn kém hoặc phát sinh I/O không?
4. Có thể parse expression một lần và tái sử dụng không?
5. Có cần toàn bộ collection kết quả hay chỉ phần tử đầu tiên?
6. Projection có tạo collection trung gian không cần thiết không?
7. Có selection/projection lồng nhau khiến số lần duyệt nhân lên không?
8. Quan hệ ORM có gây N+1 query không?
9. Có thể chỉ lấy các trường cần thiết bằng DTO không?
10. Đã đo thời gian và bộ nhớ trên dữ liệu đại diện chưa?

Không có một ngưỡng số phần tử chung cho mọi ứng dụng. Collection 10.000 phần tử với predicate đơn giản có thể nhẹ hơn 100 phần tử nhưng mỗi phần tử gọi nhiều API bên ngoài.

Hãy dựa vào chi phí mỗi phần tử và giới hạn tài nguyên của hệ thống.

## 17. Những điểm cần nhớ

- Selection và projection là thao tác duyệt collection trong bộ nhớ.
- Selection toàn bộ thường có độ phức tạp O(n); projection cũng thường O(n).
- Select first có thể dừng ở kết quả đầu tiên; trường hợp xấu nhất vẫn phải duyệt hết.
- Select last cần tìm kết quả cuối nên phải xét collection.
- Predicate hoặc projection có method tốn kém sẽ nhân chi phí theo số phần tử được xử lý.
- Selection/projection có thể tạo collection kết quả và tăng bộ nhớ sử dụng.
- Lồng nhiều collection có thể làm số lần duyệt tăng theo tích kích thước các tầng.
- SpEL không tự chuyển selection thành SQL hay tự phân trang database.
- Hãy lọc và giới hạn dữ liệu ở repository/database trước khi dùng SpEL nếu phù hợp.
- Parse expression một lần và tái sử dụng khi source không đổi.
- Tránh I/O và side effect trong predicate.
- Đo thời gian, bộ nhớ và số truy vấn trước khi tối ưu compiler hoặc cấu trúc expression.

SpEL phù hợp để biểu diễn rule và xử lý collection đã được giới hạn hợp lý. Với dữ liệu lớn, hãy kiểm soát kích thước đầu vào, số lần duyệt, chi phí mỗi phần tử và collection kết quả trước khi quyết định dùng expression hay chuyển xử lý xuống tầng truy vấn.
