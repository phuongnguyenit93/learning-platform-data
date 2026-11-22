# Tránh biểu thức collection quá dài và khó kiểm thử trong SpEL

## 1. Vì sao cần giữ collection expression ngắn?

Spring Expression Language (SpEL) hỗ trợ nhiều thao tác collection như index access, selection và projection. Những thao tác này giúp lọc phần tử, lấy một phần tử phù hợp hoặc biến đổi collection ngay trong một biểu thức.

Ví dụ ngắn, dễ đọc:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("items.?[active]");

List<?> activeItems = expression.getValue(order, List.class);
~~~

Khi thêm nhiều điều kiện lồng nhau, truy cập property nhiều cấp, toán tử null-safe, phép tính và các nhánh điều kiện, một expression có thể trở nên rất dài:

~~~text
orders.?[customer != null and customer.active and items != null and items.?[product != null and product.enabled and quantity > 0].size() > 0].![customer.address?.city]
~~~

Expression dài thường khó đọc, khó xác định lỗi ở đoạn nào, khó kiểm tra từng điều kiện và khó thay đổi khi mô hình dữ liệu thay đổi. Một quy tắc thực tế là giữ SpEL cho thao tác ngắn, có mục đích rõ ràng; đưa quy trình nhiều bước sang Java hoặc chia thành các expression nhỏ có tên.

## 2. Nhận biết dấu hiệu expression đã quá phức tạp

Một collection expression thường cần được tách nhỏ khi có một hoặc nhiều dấu hiệu sau:

- Selection chứa nhiều điều kiện kết hợp bằng and và or, đặc biệt khi có nhiều cấp dấu ngoặc.
- Selection lồng trong selection hoặc projection lồng nhiều tầng.
- Một biểu thức vừa lọc, vừa biến đổi, vừa tính tổng hoặc áp dụng quy tắc nghiệp vụ.
- Cùng một property path dài được lặp lại nhiều lần.
- Có nhiều điểm có thể null và expression phải xử lý nhiều nhánh null-safe.
- Một người đọc cần lần theo nhiều biến #this ở các cấp collection để hiểu phần tử hiện tại là object nào.
- Expression chỉ có thể kiểm thử bằng cách dựng một object graph lớn.
- Một thay đổi nhỏ trong domain model buộc phải sửa nhiều chuỗi expression.

Độ dài ký tự không phải tiêu chí duy nhất. Một expression ngắn nhưng có ngữ nghĩa khó hiểu vẫn cần được đơn giản hóa. Ngược lại, một đường dẫn property ngắn và rõ ràng có thể giữ nguyên.

## 3. Đặt tên cho ý định nghiệp vụ trong Java

SpEL chỉ nhìn thấy cú pháp và dữ liệu được cung cấp. Khi quy tắc có tên nghiệp vụ, hãy đưa tên đó vào method Java để người đọc hiểu mục đích mà không phải giải mã toàn bộ expression.

Ví dụ, thay vì để một chuỗi dài quyết định đơn hàng có đủ điều kiện xử lý hay không:

~~~text
orders.?[status == 'PAID' and customer != null and customer.active and total >= 100]
~~~

Có thể tạo method Java:

~~~java
public boolean isEligibleForProcessing(Order order) {
    return order.getStatus() == OrderStatus.PAID
            && order.getCustomer() != null
            && order.getCustomer().isActive()
            && order.getTotal().compareTo(new BigDecimal("100")) >= 0;
}
~~~

Nếu ứng dụng cần lọc một collection, có thể dùng Java Stream với method có tên rõ ràng:

~~~java
List<Order> eligibleOrders = orders.stream()
        .filter(this::isEligibleForProcessing)
        .toList();
~~~

Tên isEligibleForProcessing mô tả trực tiếp quy tắc. Method có thể được kiểm thử độc lập, đặt breakpoint và tái sử dụng ở nhiều luồng xử lý. SpEL vẫn hữu ích cho các điều kiện cấu hình hoặc biểu thức ngắn, còn quy tắc nghiệp vụ có nhiều thành phần nên có một vị trí rõ ràng trong Java.

## 4. Tách một quy trình thành các bước có tên

Khi cần giữ xử lý trong SpEL, hãy chia quy trình thành các expression nhỏ. Mỗi expression nên làm một việc và có tên mô tả kết quả.

Ví dụ cần lấy tổng tiền của các đơn hàng đã thanh toán:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression paidOrdersExpression =
        parser.parseExpression("orders.?[status == 'PAID']");

Expression paidTotalsExpression =
        parser.parseExpression("#paidOrders.![total]");

StandardEvaluationContext context =
        new StandardEvaluationContext(orderBook);

List<?> paidOrders =
        paidOrdersExpression.getValue(context, List.class);

context.setVariable("paidOrders", paidOrders);

List<?> totals =
        paidTotalsExpression.getValue(context, List.class);
~~~

Luồng này có hai bước rõ ràng:

1. paidOrdersExpression chọn các đơn hàng đã thanh toán.
2. paidTotalsExpression lấy property total từ từng đơn hàng đã chọn.

Tên biến paidOrders mô tả dữ liệu trung gian. Nếu cần kiểm tra, có thể xem kết quả sau bước selection trước khi chạy projection. Cách chia này cũng giúp xác định expression nào gây lỗi khi dữ liệu không như mong đợi.

Không cần tách một expression rất đơn giản thành nhiều bước. Hãy tách khi tên bước trung gian làm cho ý định hoặc việc kiểm thử rõ hơn.

## 5. Hiểu đúng #this trong selection và projection

Trong collection operation, #this đại diện cho phần tử hiện tại đang được xử lý. Khi collection operation lồng nhau, #this thay đổi theo cấp hiện tại. Đây là một nguồn gây nhầm lẫn phổ biến.

Ví dụ selection đơn:

~~~java
Expression expression =
        parser.parseExpression("items.?[#this.active]");
~~~

Trong predicate, #this là một item. Có thể bỏ #this khi truy cập trực tiếp property của phần tử hiện tại:

~~~java
Expression expression =
        parser.parseExpression("items.?[active]");
~~~

Với projection:

~~~java
Expression expression =
        parser.parseExpression("items.![name]");
~~~

Mỗi lần projection chạy, name được đọc trên phần tử hiện tại.

Khi lồng collection operation, hãy xác định rõ mỗi cấp đang xử lý object nào. Nếu phải viết nhiều biểu thức #this lồng nhau để truy cập phần tử ngoài, hãy đưa logic vào method Java hoặc tách collection trung gian thành biến được đặt tên.

## 6. Tránh selection và projection lồng quá nhiều tầng

Một expression như sau có nhiều trách nhiệm cùng lúc:

~~~text
departments.?[employees != null and employees.?[active and salary > 5000].size() > 2].![employees.?[active].![name]]
~~~

Nó vừa lọc phòng ban theo số nhân viên phù hợp, vừa lọc nhân viên, vừa lấy tên nhân viên. Người đọc phải hiểu cấu trúc department, employee và ý nghĩa của từng #this ở mỗi cấp.

Có thể chia bằng Java:

~~~java
List<Department> departmentsWithActiveStaff = departments.stream()
        .filter(department -> department.getEmployees().stream()
                .filter(Employee::isActive)
                .filter(employee -> employee.getSalary() > 5000)
                .count() > 2)
        .toList();

List<List<String>> activeEmployeeNames = departmentsWithActiveStaff.stream()
        .map(department -> department.getEmployees().stream()
                .filter(Employee::isActive)
                .map(Employee::getName)
                .toList())
        .toList();
~~~

Nếu ứng dụng vẫn cần expression cho từng bước nhỏ, hãy chuẩn bị dữ liệu trung gian trong Java rồi đánh giá expression trên collection đã được đặt tên. Cấu trúc dữ liệu và tên biến làm rõ ngữ cảnh hơn nhiều so với một expression lồng sâu.

## 7. Tách điều kiện thành method hoặc property có tên

Một predicate dài thường là dấu hiệu cho thấy nó đang biểu đạt một khái niệm có tên. Có thể thêm method vào domain object hoặc một service:

~~~java
public boolean isReadyForDispatch() {
    return paid && stockReserved && !cancelled;
}
~~~

Khi đó selection trở nên ngắn:

~~~java
Expression expression =
        parser.parseExpression("orders.?[readyForDispatch]");
~~~

Nếu quy tắc cần gọi service hoặc phụ thuộc nhiều nguồn dữ liệu, nên xử lý trong Java service trước khi đưa kết quả vào expression. Điều này tránh biến SpEL thành nơi điều phối nghiệp vụ và giúp quản lý dependency rõ ràng.

Không nên thêm getter chỉ để che một biểu thức dài nếu getter thực hiện truy vấn, side effect hoặc công việc nặng. Property được truy cập qua SpEL có thể gọi getter; vì vậy getter nên có hành vi đọc dữ liệu ổn định và dễ dự đoán.

## 8. Xử lý null ở ranh giới dữ liệu

Null-safe operator giúp expression xử lý target null, nhưng không làm cho toàn bộ expression tự động an toàn. Mỗi bước có thể trả về null cần được xử lý rõ ràng.

Ví dụ:

~~~text
orders?.?[customer?.active == true]
~~~

Ở đây ?.?, bảo vệ collection orders; customer?.active bảo vệ property customer của phần tử hiện tại. Nếu expression còn truy cập các property khác có thể null, cần xử lý riêng những chặng đó.

Khi logic null bắt đầu có nhiều nhánh, chuẩn hóa dữ liệu trước khi đánh giá expression thường rõ ràng hơn:

~~~java
List<Order> safeOrders =
        orders == null ? Collections.emptyList() : orders;

context.setVariable("orders", safeOrders);
~~~

Chỉ chuẩn hóa null thành collection rỗng khi hai trạng thái có cùng ý nghĩa nghiệp vụ. Nếu null có nghĩa “chưa tải dữ liệu” còn collection rỗng có nghĩa “đã tải nhưng không có kết quả”, hãy giữ sự khác biệt và xử lý ở Java.

## 9. Đưa dữ liệu động vào EvaluationContext

Không nên tạo expression source bằng cách nối trực tiếp giá trị runtime vào chuỗi. Dữ liệu có thể chứa dấu nháy, ký tự đặc biệt hoặc nội dung làm thay đổi cú pháp.

Ví dụ, dùng variable:

~~~java
Expression expression =
        parser.parseExpression("items.?[category == #requiredCategory]");

StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable("requiredCategory", requestedCategory);

List<?> matches = expression.getValue(context, List.class);
~~~

requiredCategory được truyền riêng trong evaluation context. Cùng expression có thể được tái sử dụng với các giá trị khác nhau. Cách này cũng giúp test các trường hợp đầu vào mà không cần dựng lại chuỗi expression.

Nếu expression cần một tập dữ liệu đầu vào rõ ràng, hãy tạo root object chuyên biệt hoặc dùng variables có tên mô tả mục đích thay vì đặt nhiều giá trị không liên quan vào một context.

## 10. Parse một lần, đánh giá nhiều lần

Khi cùng một expression được dùng lặp lại, hãy phân tích cú pháp một lần rồi giữ lại đối tượng Expression để đánh giá với các context hoặc dữ liệu khác nhau:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("items.?[active]");

List<?> firstResult = expression.getValue(firstCatalog, List.class);
List<?> secondResult = expression.getValue(secondCatalog, List.class);
~~~

Việc tách parse khỏi evaluate giúp phân biệt lỗi cú pháp với lỗi dữ liệu lúc chạy. Nếu expression source đến từ cấu hình, có thể parse và kiểm tra cú pháp trong quá trình khởi động để phát hiện cấu hình sai sớm.

Không cần parse lại cùng một chuỗi trong mỗi vòng lặp. Nếu cần lọc từng phần tử bằng một quy tắc đơn giản, cân nhắc Java Stream hoặc một method predicate thay vì tạo và parse expression mới cho từng phần tử.

## 11. Kiểm thử expression theo từng hành vi

Một expression collection nên có test cho cả dữ liệu bình thường và các trường hợp biên. Tạo fixture nhỏ, dễ đọc, với dữ liệu chỉ đủ để thể hiện quy tắc.

Ví dụ test selection:

~~~java
@Test
void selectsOnlyActiveItems() {
    List<Item> items = List.of(
            new Item("A", true),
            new Item("B", false),
            new Item("C", true));

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("items.?[active]");

    Catalog catalog = new Catalog(items);

    List<?> result = expression.getValue(catalog, List.class);

    assertEquals(2, result.size());
}
~~~

Nên có các trường hợp sau tùy hành vi expression:

- Collection có nhiều phần tử, một số khớp và một số không khớp.
- Collection rỗng.
- Collection null nếu expression được thiết kế để hỗ trợ null.
- Phần tử có property null.
- Không có phần tử nào khớp selection.
- Index hợp lệ và index ngoài giới hạn nếu dùng index access.
- Kiểu kết quả đúng với kiểu mà ứng dụng mong đợi.

Test nên xác nhận kết quả và trường hợp lỗi có ý nghĩa. Không cần tạo fixture lớn nếu một collection nhỏ đã thể hiện được hành vi.

## 12. Kiểm thử parse và evaluate riêng biệt

Parse error và evaluation error là hai loại lỗi khác nhau:

- Parse error xảy ra khi chuỗi không đúng cú pháp SpEL.
- Evaluation error xảy ra khi expression hợp lệ nhưng dữ liệu hoặc context không cho phép thực hiện thao tác.

Có thể kiểm tra cú pháp riêng:

~~~java
Expression expression = parser.parseExpression("items.?[active]");
~~~

Sau đó đánh giá với dữ liệu:

~~~java
List<?> result = expression.getValue(catalog, List.class);
~~~

Khi test thất bại, việc tách hai bước giúp xác định lỗi nằm ở expression source hay ở dữ liệu runtime. Nếu expression được đọc từ cấu hình, nên có test hoặc kiểm tra khởi động để phát hiện lỗi parse trước khi luồng nghiệp vụ chạy.

## 13. Giới hạn quyền của evaluation context

Collection expression có thể truy cập property và gọi method tùy evaluation context được cấu hình. StandardEvaluationContext hỗ trợ các khả năng rộng như reflection, method resolution, type access và bean resolution khi được bật.

Không đánh giá chuỗi SpEL do người dùng không tin cậy gửi lên bằng context có quyền rộng. Nếu chỉ cần data binding hoặc đọc property giới hạn, cân nhắc SimpleEvaluationContext và chỉ bật các khả năng thật sự cần thiết.

Một expression ngắn vẫn có thể thực hiện thao tác không phù hợp nếu context cấp quyền quá rộng. Vì vậy, độ dài và độ phức tạp của expression là một vấn đề bảo trì; quyền truy cập của context là một vấn đề bảo mật riêng cần được thiết kế.

## 14. Khi nào nên dùng SpEL, khi nào nên dùng Java?

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Lọc collection bằng một predicate ngắn tại điểm cấu hình | SpEL selection |
| Chọn một phần tử đầu tiên hoặc cuối cùng theo điều kiện đơn giản | SpEL first/last selection |
| Lấy một property từ mỗi phần tử | SpEL projection |
| Nhiều cấp selection/projection lồng nhau | Tách thành Java hoặc các bước trung gian |
| Quy tắc nghiệp vụ có nhiều điều kiện và nhiều trạng thái | Java method/service |
| Cần gọi repository, API hoặc phối hợp nhiều service | Java service |
| Cần logging, exception handling và side effect rõ ràng | Java |
| Cần biểu thức ngắn do cấu hình quyết định | SpEL, với context được giới hạn phù hợp |

SpEL có lợi khi biểu thức ngắn, dữ liệu đầu vào rõ và vị trí tích hợp thực sự cần expression. Java phù hợp hơn khi logic có nhiều bước hoặc cần hành vi có tên, kiểm thử độc lập và quản lý dependency.

## 15. Quy trình đơn giản hóa một expression dài

Khi gặp expression collection khó đọc, có thể xử lý theo trình tự:

1. Xác định kết quả cuối cùng cần là gì: collection, một phần tử, một giá trị hay Boolean.
2. Ghi lại các điều kiện selection thành những câu có tên nghiệp vụ.
3. Xác định các property path có thể null và ranh giới cần null-safe access.
4. Tách các bước trung gian có ý nghĩa thành variables hoặc method Java.
5. Giữ lại SpEL cho từng thao tác ngắn nếu nó vẫn giúp cấu hình dễ hiểu.
6. Parse expression một lần và viết test cho kết quả bình thường cùng các trường hợp biên.
7. Nếu vẫn cần đọc nhiều lần mới hiểu, chuyển quy tắc chính sang Java method/service.

Mục tiêu là để mỗi expression thể hiện một thao tác rõ ràng. Tên method và biến trung gian nên giải thích ý định thay cho việc buộc người đọc tự giải mã một chuỗi dài.

## 16. Ví dụ tổng hợp: từ expression lồng nhau sang các bước dễ kiểm thử

Giả sử cần lấy tên nhân viên đang hoạt động thuộc các phòng ban có ít nhất hai nhân viên hoạt động. Có thể viết thành một expression lồng nhiều cấp, nhưng việc hiểu và test rất khó:

~~~text
departments.?[employees != null and employees.?[active].size() >= 2].![employees.?[active].![name]]
~~~

Có thể chuyển quy tắc sang Java:

~~~java
public boolean hasEnoughActiveEmployees(Department department) {
    return department.getEmployees() != null
            && department.getEmployees().stream()
                    .filter(Employee::isActive)
                    .count() >= 2;
}

List<Department> eligibleDepartments = departments.stream()
        .filter(this::hasEnoughActiveEmployees)
        .toList();

List<List<String>> activeNames = eligibleDepartments.stream()
        .map(department -> department.getEmployees().stream()
                .filter(Employee::isActive)
                .map(Employee::getName)
                .toList())
        .toList();
~~~

Method hasEnoughActiveEmployees thể hiện điều kiện lựa chọn. Phần projection tên nhân viên là một bước riêng. Có thể viết unit test cho method predicate, test cho phép chiếu tên và test cho luồng tổng hợp. Nếu cần hiển thị hoặc cấu hình một predicate đơn giản, vẫn có thể dùng SpEL ở ranh giới thích hợp.

## 17. Ghi nhớ

- Giữ selection và projection ngắn, tập trung vào một thao tác.
- Đưa quy tắc nghiệp vụ nhiều điều kiện vào method Java có tên rõ ràng.
- Tách collection operation lồng nhau thành các bước trung gian có tên.
- Hiểu rõ #this thay đổi theo collection operation hiện tại.
- Xử lý null ở từng ranh giới; null và collection rỗng có thể mang ý nghĩa khác nhau.
- Truyền dữ liệu động qua variables trong EvaluationContext, tránh nối dữ liệu vào expression source.
- Parse một lần khi tái sử dụng cùng expression; đánh giá với context/dữ liệu tương ứng.
- Kiểm thử parse và evaluate riêng, bao gồm collection rỗng, null, không có phần tử khớp và index ngoài giới hạn.
- Giới hạn quyền của evaluation context khi expression không hoàn toàn do ứng dụng kiểm soát.
- Chọn Java khi cần nhiều bước, side effect, dependency, logging hoặc xử lý lỗi rõ ràng.
