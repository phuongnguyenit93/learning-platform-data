# Đối chiếu kết quả SpEL với logic Java tham chiếu

## Mục tiêu

Một SpEL expression thường biểu diễn một quy tắc mà ứng dụng cũng có thể viết bằng Java. Để kiểm tra expression có đúng hay không, hãy xây dựng một **logic Java tham chiếu độc lập** rồi chạy cả hai cách trên cùng bộ dữ liệu. Kết quả SpEL được so sánh với kết quả Java để phát hiện sai khác về điều kiện, kiểu dữ liệu, null, conversion, thứ tự collection hoặc xử lý giá trị biên.

Cách kiểm tra này đặc biệt hữu ích khi expression dài, có nhiều điều kiện, dùng selection/projection hoặc được lưu dưới dạng cấu hình. Nó giúp xác nhận hành vi thực tế của SpEL thay vì chỉ kiểm tra expression có parse thành công.

Sau bài này, bạn có thể:

- Viết logic Java tham chiếu cho một SpEL expression.
- Đánh giá cả hai cách trên cùng root object và tham số.
- So sánh kết quả Boolean, scalar, object và collection.
- Căn chỉnh semantics của null, số, enum, ngày giờ và conversion.
- Kiểm thử dữ liệu biên, dữ liệu sai và trường hợp không có kết quả.
- Phân biệt lỗi parse, lỗi evaluation và lỗi trong logic Java.
- Dùng parameterized test hoặc differential test để mở rộng độ bao phủ.
- Tránh tạo một Java reference chỉ sao chép nguyên xi lỗi của expression.

## 1. Vì sao cần logic Java tham chiếu?

Một expression parse thành công chưa chứng minh quy tắc nghiệp vụ được diễn đạt đúng. Ví dụ:

~~~text
#root.active and #root.total >= #minimumTotal
~~~

Expression có thể hợp lệ về cú pháp nhưng vẫn dùng nhầm property, bỏ sót điều kiện hoặc xử lý sai giá trị null. Một test chỉ kiểm tra kết quả của expression trên một dữ liệu mẫu có thể không phát hiện các trường hợp đó.

Logic Java tham chiếu cung cấp một cách biểu diễn thứ hai cho cùng quy tắc. Khi hai kết quả khác nhau, test chỉ ra rằng ít nhất một cách thực hiện đang không khớp với quy tắc mong đợi.

Cách tiếp cận này phù hợp với:

- Quy tắc tính giá, chiết khấu, thuế hoặc điều kiện đủ tiêu chuẩn.
- Lọc collection bằng selection.
- Chuyển đổi collection bằng projection.
- Kiểm tra trạng thái và quyền truy cập.
- Expression có biến truyền từ EvaluationContext.
- Expression được thay đổi bởi người cấu hình hoặc lưu ngoài mã nguồn.
- Nâng cấp Spring Framework hoặc thay đổi EvaluationContext/ConversionService.

Java reference nên thể hiện ý nghĩa nghiệp vụ bằng code dễ đọc. Không nên tạo một method Java chỉ gọi lại cùng SpEL expression, vì như vậy hai kết quả không độc lập và test không thể phát hiện sai logic.

## 2. Quy trình đối chiếu tổng quát

Với mỗi quy tắc cần kiểm tra:

1. Viết rõ quy tắc bằng ngôn ngữ nghiệp vụ.
2. Viết SpEL expression thực hiện quy tắc đó.
3. Viết một hàm Java độc lập biểu diễn cùng quy tắc.
4. Chuẩn bị một bộ input dùng chung cho cả hai cách.
5. Tạo EvaluationContext với đúng root object và biến.
6. Đánh giá expression và gọi Java reference.
7. So sánh kết quả theo đúng semantics của kiểu dữ liệu.
8. Lặp lại với trường hợp biên, null và dữ liệu không hợp lệ.

Ví dụ, quy tắc là: một đơn hàng được chấp nhận khi đang active, tổng tiền không nhỏ hơn ngưỡng tối thiểu và trạng thái là APPROVED.

SpEL:

~~~text
#root.active
and #root.total.compareTo(#minimumTotal) >= 0
and #root.status == #requiredStatus
~~~

Java reference:

~~~java
static boolean isAccepted(
        Order order,
        BigDecimal minimumTotal,
        OrderStatus requiredStatus) {

    return order.isActive()
        && order.getTotal().compareTo(minimumTotal) >= 0
        && order.getStatus() == requiredStatus;
}
~~~

Hai cách dùng cùng dữ liệu nhưng được triển khai độc lập. Khi test, nếu kết quả khác nhau, hãy kiểm tra từng điều kiện và kiểu dữ liệu thay vì chỉ sửa assertion để làm test xanh.

## 3. Ví dụ đầy đủ: so sánh kết quả Boolean

Giả sử model:

~~~java
public enum OrderStatus {
    NEW, APPROVED, PAID, CANCELLED
}

public class Order {
    private final boolean active;
    private final BigDecimal total;
    private final OrderStatus status;

    public Order(
            boolean active,
            BigDecimal total,
            OrderStatus status) {
        this.active = active;
        this.total = total;
        this.status = status;
    }

    public boolean isActive() {
        return active;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
~~~

Tạo expression một lần:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#root.active and " +
    "#root.total.compareTo(#minimumTotal) >= 0 and " +
    "#root.status == #requiredStatus"
);
~~~

Java reference:

~~~java
static boolean isAccepted(
        Order order,
        BigDecimal minimumTotal,
        OrderStatus requiredStatus) {

    return order.isActive()
        && order.getTotal().compareTo(minimumTotal) >= 0
        && order.getStatus() == requiredStatus;
}
~~~

Test đối chiếu:

~~~java
@Test
void spelMatchesJavaReferenceForOrderEligibility() {
    Order order = new Order(
        true,
        new BigDecimal("150.00"),
        OrderStatus.APPROVED
    );

    BigDecimal minimumTotal = new BigDecimal("100.00");
    OrderStatus requiredStatus = OrderStatus.APPROVED;

    StandardEvaluationContext context =
        new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", minimumTotal);
    context.setVariable("requiredStatus", requiredStatus);

    Boolean spelResult =
        expression.getValue(context, Boolean.class);

    boolean javaResult =
        isAccepted(order, minimumTotal, requiredStatus);

    assertEquals(javaResult, spelResult);
}
~~~

Điểm quan trọng là Java reference nhận cùng order, minimumTotal và requiredStatus như EvaluationContext. Không tạo một bộ dữ liệu khác cho Java và SpEL, nếu không kết quả khác nhau có thể do input chứ không phải do logic.

## 4. So sánh scalar và kiểu số

Với kết quả số, không nên mặc định mọi phép so sánh Java và SpEL đều có cùng hành vi ở mọi kiểu số. Cần xác định rõ kiểu nguồn, kiểu đích, precision và quy tắc làm tròn.

Ví dụ expression tính tổng:

~~~text
#root.unitPrice.multiply(new java.math.BigDecimal(#root.quantity))
~~~

Java reference:

~~~java
static BigDecimal calculateTotal(OrderLine line) {
    return line.getUnitPrice()
        .multiply(BigDecimal.valueOf(line.getQuantity()));
}
~~~

Đối chiếu:

~~~java
BigDecimal spelResult =
    expression.getValue(context, BigDecimal.class);

BigDecimal javaResult = calculateTotal(line);

assertEquals(0, javaResult.compareTo(spelResult));
~~~

Với BigDecimal, compareTo so sánh giá trị số mà không yêu cầu scale giống nhau. equals lại xét cả scale, nên 10.0 và 10.00 không bằng nhau theo equals dù có cùng giá trị số. Hãy chọn phép so sánh theo đúng hợp đồng dữ liệu.

Khi kiểm tra floating point, cần xác định tolerance nếu nghiệp vụ cho phép sai số. Không tự thêm tolerance cho số tiền hoặc giá trị cần chính xác thập phân; hãy dùng kiểu và quy tắc làm tròn phù hợp.

Các trường hợp số nên kiểm tra:

- Số dương, số âm và zero.
- Giá trị đúng bằng ngưỡng.
- Giá trị ngay dưới và ngay trên ngưỡng.
- Giá trị lớn hoặc nhỏ gần giới hạn kiểu.
- BigDecimal có scale khác nhau.
- Giá trị null nếu model cho phép.
- Chuyển đổi giữa Integer, Long, Double và BigDecimal nếu expression có dùng conversion.

## 5. Đối chiếu selection trên collection

Với collection selection, Java reference thường là stream filter hoặc vòng lặp. Hãy so sánh cả phần tử được chọn và thứ tự nếu thứ tự là một phần của contract.

SpEL:

~~~text
#root.orders.?[
    #this.active and #this.total.compareTo(#minimumTotal) >= 0
]
~~~

Java reference:

~~~java
List<Order> javaResult = orders.stream()
    .filter(Order::isActive)
    .filter(order ->
        order.getTotal().compareTo(minimumTotal) >= 0)
    .toList();
~~~

Đánh giá SpEL:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(customer);
context.setVariable("minimumTotal", minimumTotal);

List<?> spelResult =
    expression.getValue(context, List.class);
~~~

So sánh:

~~~java
assertEquals(javaResult.size(), spelResult.size());

for (int i = 0; i < javaResult.size(); i++) {
    Order expected = javaResult.get(i);
    Order actual = (Order) spelResult.get(i);

    assertEquals(expected.getId(), actual.getId());
}
~~~

So sánh theo ID hoặc các field nghiệp vụ thường rõ hơn so sánh identity. Nếu model định nghĩa equals/hashCode đúng với ý nghĩa cần kiểm tra, có thể dùng assertEquals trực tiếp trên collection.

Với List, thứ tự thường có ý nghĩa và cần được kiểm tra. Với Set, cần xác định chỉ so sánh membership hay cả thứ tự iteration. Với Map, so sánh key/value và không giả định thứ tự nếu implementation không bảo đảm ordering.

## 6. Đối chiếu projection và cấu trúc kết quả

Projection chuyển mỗi phần tử thành một giá trị mới. Java reference có thể dùng map:

SpEL:

~~~text
#root.orders.?[#this.active].![#this.id]
~~~

Java:

~~~java
List<String> javaResult = orders.stream()
    .filter(Order::isActive)
    .map(Order::getId)
    .toList();
~~~

Khi so sánh, kiểm tra:

- Kiểu kết quả có đúng không.
- Số lượng phần tử.
- Giá trị từng phần tử.
- Thứ tự nếu collection có thứ tự.
- Cách xử lý phần tử null.
- Cấu trúc nested collection nếu có nhiều tầng projection.

Projection lồng nhau không tự động flatten. Ví dụ, nếu mỗi Department có một danh sách Employee, expression chiếu danh sách employee names theo từng department sẽ tạo cấu trúc danh sách lồng nhau. Java reference cần dùng map ở cùng cấp để tạo cấu trúc tương ứng; không dùng flatMap nếu SpEL không làm phẳng kết quả.

## 7. Đảm bảo semantics giống nhau

Java và SpEL có thể có khác biệt về conversion, null handling, operator behavior hoặc cách truy cập property. Khi đối chiếu, cần quyết định rõ quy tắc mong muốn rồi làm cho cả hai cách tuân theo cùng quy tắc đó.

### Null

Xác định null có được phép hay không và có nghĩa gì:

- Null là input không hợp lệ và phải bị từ chối.
- Null được xem như false.
- Null được thay bằng default value.
- Null là một trạng thái riêng cần giữ nguyên.

Ví dụ SpEL dùng safe navigation:

~~~text
#root.customer?.active == true
~~~

Java reference tương ứng:

~~~java
boolean javaResult =
    order.getCustomer() != null
        && order.getCustomer().isActive();
~~~

Nếu Java reference mặc định null thành false nhưng SpEL lại ném exception do thiếu safe navigation, test sẽ phát hiện sự khác nhau.

### BigDecimal và số học

Nếu Java dùng compareTo thì expression nên thể hiện cùng ý nghĩa, ví dụ:

~~~text
#root.total.compareTo(#minimumTotal) >= 0
~~~

Không so sánh bằng Java equals trong reference rồi so sánh numeric theo cách khác trong SpEL mà không có chủ đích.

### String và enum

Xác định rõ so sánh có phân biệt chữ hoa/thường hay không. Nếu Java dùng equalsIgnoreCase, expression cần gọi method tương ứng hoặc chuẩn hóa hai phía. Nếu trạng thái là enum, so sánh enum constant thường tránh được lỗi chính tả trong chuỗi.

### Date và time

Cả hai cách phải dùng cùng timezone, Clock, locale và quy tắc biên thời gian. Không gọi LocalDateTime.now() riêng biệt trong hai implementation rồi so sánh trực tiếp nếu thời điểm có thể khác nhau. Hãy truyền một Clock hoặc timestamp cố định vào cả hai cách.

### Conversion

Nếu expression dựa vào TypeConverter/ConversionService, Java reference cần áp dụng cùng quy tắc chuyển đổi hoặc nhận dữ liệu đã được chuẩn hóa trước. Không để SpEL tự chuyển String thành Integer trong khi Java reference parse theo một quy tắc khác.

## 8. Đối chiếu biến trong EvaluationContext

Nếu expression dùng biến, Java reference phải nhận cùng các giá trị đó như tham số tường minh.

SpEL:

~~~text
#root.score >= #minimumScore
and #root.status == #requiredStatus
~~~

Java:

~~~java
static boolean qualifies(
        Student student,
        int minimumScore,
        StudentStatus requiredStatus) {

    return student.getScore() >= minimumScore
        && student.getStatus() == requiredStatus;
}
~~~

Trong test, đặt biến trên context:

~~~java
context.setVariable("minimumScore", minimumScore);
context.setVariable("requiredStatus", requiredStatus);
~~~

Không đọc biến từ một global field trong Java reference trong khi SpEL lấy từ context. Điều đó tạo ra hai nguồn dữ liệu khác nhau và có thể che giấu lỗi truyền biến.

Nếu context được tạo riêng cho mỗi request, Java reference cũng nên được gọi với các tham số thuộc đúng request đó. Không tái sử dụng mutable context giữa các test song song nếu nó có thể làm lẫn giá trị biến.

## 9. Dùng parameterized test để bao phủ nhiều trường hợp

Thay vì chỉ kiểm tra một bộ dữ liệu, dùng JUnit 5 parameterized test để chạy cùng quy tắc với nhiều input.

Ví dụ:

~~~java
@ParameterizedTest
@MethodSource("orderCases")
void spelMatchesJavaReference(
        Order order,
        BigDecimal minimumTotal,
        OrderStatus requiredStatus) {

    StandardEvaluationContext context =
        new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", minimumTotal);
    context.setVariable("requiredStatus", requiredStatus);

    Boolean spelResult =
        expression.getValue(context, Boolean.class);

    boolean javaResult =
        isAccepted(order, minimumTotal, requiredStatus);

    assertEquals(javaResult, spelResult);
}

static Stream<Arguments> orderCases() {
    return Stream.of(
        Arguments.of(
            new Order(true, new BigDecimal("150"), OrderStatus.APPROVED),
            new BigDecimal("100"),
            OrderStatus.APPROVED
        ),
        Arguments.of(
            new Order(false, new BigDecimal("150"), OrderStatus.APPROVED),
            new BigDecimal("100"),
            OrderStatus.APPROVED
        ),
        Arguments.of(
            new Order(true, new BigDecimal("50"), OrderStatus.APPROVED),
            new BigDecimal("100"),
            OrderStatus.APPROVED
        ),
        Arguments.of(
            new Order(true, new BigDecimal("150"), OrderStatus.NEW),
            new BigDecimal("100"),
            OrderStatus.APPROVED
        )
    );
}
~~~

Các case trên lần lượt kiểm tra trường hợp hợp lệ, inactive, tổng tiền dưới ngưỡng và trạng thái không khớp. Nên thêm trường hợp đúng bằng ngưỡng, dữ liệu null nếu được phép và giá trị biên.

Với test nhiều tham số, đặt tên case hoặc dùng Arguments có mô tả giúp xác định nhanh trường hợp thất bại.

## 10. Differential testing với dữ liệu sinh tự động

Khi quy tắc có nhiều nhánh, có thể sinh nhiều bộ input để so sánh SpEL với Java reference. Đây là differential testing: hai implementation nhận cùng input và kết quả được đối chiếu tự động.

Quy trình:

1. Xác định miền dữ liệu hợp lệ.
2. Sinh input ngẫu nhiên hoặc theo chiến lược bao phủ biên.
3. Tạo root object và biến context từ cùng input.
4. Đánh giá SpEL.
5. Đánh giá Java reference.
6. So sánh kết quả.
7. Khi có sai khác, lưu seed và input tối thiểu để tái hiện.
8. Chuyển case thất bại thành regression test cố định.

Ví dụ các chiều dữ liệu để sinh:

- Boolean active.
- Tổng tiền từ âm, zero tới giá trị lớn.
- Các trạng thái enum.
- Ngưỡng minimum khác nhau.
- Collection rỗng, một phần tử và nhiều phần tử.
- Property optional có hoặc không có giá trị.
- Các kiểu runtime khác nhau nếu model cho phép.

Dữ liệu sinh tự động cần bị giới hạn trong miền hợp lệ. Nếu tạo input không hợp lệ, hãy kiểm tra riêng rằng cả hai implementation từ chối theo cùng contract, thay vì so sánh một kết quả bất kỳ.

Không chỉ kiểm tra random data. Hãy giữ test tường minh cho các giá trị biên vì chúng dễ đọc, dễ review và tái hiện ổn định.

## 11. So sánh lỗi và hành vi thất bại

Không phải mọi test đều nên so sánh giá trị trả về. Có những quy tắc cần xác nhận cả hai cách đều từ chối input không hợp lệ.

Ví dụ, nếu total bắt buộc khác null:

- Java reference có thể ném IllegalArgumentException với thông báo nghiệp vụ.
- SpEL có thể ném SpelEvaluationException hoặc bọc exception từ getter/method.

Không nhất thiết hai implementation phải ném cùng exception class. Điều cần so sánh là contract quan sát được: input có được chấp nhận không, lỗi thuộc loại nào theo tầng ứng dụng, và dữ liệu có bị thay đổi ngoài ý muốn không.

Có thể viết test riêng cho:

- Expression parse failure.
- Property hoặc method access failure.
- Conversion failure.
- Null input bị từ chối.
- Java reference validation failure.
- Function hoặc method bên trong expression ném exception.

Nếu ứng dụng cần một API lỗi thống nhất, hãy chuyển exception kỹ thuật thành lỗi nghiệp vụ tại ranh giới service. Không so sánh toàn bộ message text giữa SpEL và Java vì nội dung có thể khác nhau theo phiên bản và implementation.

## 12. Tránh tạo Java reference trùng lỗi với SpEL

Một test đối chiếu chỉ hữu ích khi hai cách thực hiện độc lập đủ để sai khác có thể xuất hiện.

Không nên:

- Viết Java reference bằng cách gọi lại cùng expression.
- Sao chép nguyên văn cùng một chuỗi điều kiện mà không kiểm tra ý nghĩa nghiệp vụ.
- Dùng cùng helper đang bị nghi ngờ là nguồn lỗi ở cả hai phía.
- Tạo expected result bằng cách gọi chính code đang được test.
- Sửa Java reference chỉ để khớp kết quả SpEL mà không đối chiếu quy tắc nghiệp vụ.

Nên:

- Viết Java reference bằng cấu trúc code dễ đọc và có tên rõ nghĩa.
- Đối chiếu từng điều kiện với yêu cầu nghiệp vụ.
- Có expected value tường minh cho một số case quan trọng.
- Review các case biên độc lập với implementation.
- Khi hai cách khác nhau, kiểm tra requirement trước khi quyết định cách nào đúng.

Java reference cũng có thể sai. Differential testing chỉ phát hiện bất đồng; nó không tự chứng minh implementation nào đúng. Một oracle thứ ba như ví dụ nghiệp vụ đã được xác nhận hoặc expected value tường minh vẫn cần thiết cho các quy tắc quan trọng.

## 13. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| SpEL và Java cho Boolean khác nhau | Điều kiện, null hoặc toán tử không tương đương | Chia quy tắc thành từng điều kiện và so sánh |
| Kết quả số khác nhau rất nhỏ | Precision, scale, rounding hoặc kiểu số khác nhau | Chuẩn hóa kiểu và quy tắc so sánh |
| Collection có cùng phần tử nhưng khác thứ tự | Một implementation không giữ ordering như implementation kia | Xác định thứ tự có thuộc contract không |
| Collection khác số lượng phần tử | Predicate, null handling hoặc conversion khác nhau | Kiểm tra từng phần tử và điều kiện |
| Projection có cấu trúc khác | Một bên flatten hoặc map sai cấp | So sánh kiểu và cấu trúc kết quả từng tầng |
| Chỉ sai ở null | Safe navigation và Java null check không tương đương | Xác định hợp đồng null rồi căn chỉnh hai phía |
| Chỉ sai với enum/String | Chuẩn hóa hoặc quy tắc so sánh khác nhau | Dùng enum hoặc chuẩn hóa String rõ ràng |
| Chỉ sai với ngày giờ | Timezone, locale hoặc thời điểm hiện tại khác nhau | Truyền Clock/ZoneId cố định |
| Test lúc pass lúc fail | Dùng dữ liệu thời gian thực, random không lưu seed hoặc shared context | Cố định input và cô lập context |
| Cả hai cùng sai requirement | Java reference sao chép cùng giả định sai | Thêm expected value độc lập từ quy tắc nghiệp vụ |

Khi có sai khác, ghi lại input, biến, root type, expression version và kết quả của từng phía. Sau đó thu nhỏ input để tìm điều kiện đầu tiên làm kết quả lệch nhau.

## 14. Quy trình xây dựng bộ test đối chiếu

1. **Chốt quy tắc nghiệp vụ.** Viết điều kiện bằng ngôn ngữ rõ ràng và xác định các trường hợp biên.
2. **Viết Java reference.** Dùng code thuần, tham số rõ ràng và không gọi lại SpEL.
3. **Viết expression.** Giữ root object và biến context có tên nhất quán.
4. **Chuẩn bị fixture chung.** Dùng cùng object và tham số cho cả hai cách.
5. **Chọn phép so sánh.** Xác định equals, compareTo, field comparison hoặc collection ordering.
6. **Kiểm thử trường hợp cơ bản.** Bao phủ đúng, sai và bằng ngưỡng.
7. **Kiểm thử null và conversion.** Dùng đúng EvaluationContext/ConversionService của ứng dụng.
8. **Kiểm thử collection.** So sánh số lượng, phần tử, cấu trúc và thứ tự.
9. **Mở rộng dữ liệu.** Dùng parameterized hoặc differential testing cho miền input rộng.
10. **Giữ regression case.** Mỗi sai khác đã sửa cần trở thành test cố định.
11. **Xác nhận bằng oracle độc lập.** Với rule quan trọng, kiểm tra một số expected value được xác định từ yêu cầu nghiệp vụ.

## 15. Thực hành tốt

- Luôn viết rõ rule nghiệp vụ trước khi viết hai implementation.
- Giữ Java reference độc lập với expression đang kiểm tra.
- Dùng cùng root object và cùng biến cho cả SpEL lẫn Java.
- Yêu cầu kiểu kết quả rõ ràng từ getValue khi phù hợp.
- So sánh BigDecimal bằng compareTo nếu contract dựa trên giá trị số.
- Kiểm tra cả nội dung và thứ tự collection khi thứ tự có ý nghĩa.
- Căn chỉnh null, conversion, locale, timezone và rounding.
- Dùng parameterized test cho các nhánh và giá trị biên.
- Dùng differential testing để mở rộng input, lưu seed và case thất bại.
- Kiểm tra hành vi lỗi riêng, không phụ thuộc toàn bộ exception message.
- Không dùng shared mutable EvaluationContext giữa các test chạy song song.
- Giữ expected value tường minh cho các quy tắc quan trọng.
- Chuyển mỗi sai khác được phát hiện thành regression test.

## 16. Checklist review

Trước khi chấp nhận một SpEL expression, hãy kiểm tra:

- [ ] Quy tắc nghiệp vụ được mô tả rõ.
- [ ] Có Java reference độc lập.
- [ ] Hai cách dùng cùng root object và tham số.
- [ ] Biến EvaluationContext được đối chiếu với tham số Java tương ứng.
- [ ] Kiểu kết quả và cách so sánh đã được xác định.
- [ ] Null handling tương đương.
- [ ] Numeric precision, scale và rounding phù hợp.
- [ ] Locale, timezone và thời gian hiện tại được cố định khi cần.
- [ ] Collection size, phần tử, cấu trúc và thứ tự được kiểm tra.
- [ ] ConversionService trong test khớp cấu hình ứng dụng.
- [ ] Có test cho giá trị biên và input không hợp lệ.
- [ ] Có test cho exception/validation behavior.
- [ ] Java reference không gọi lại expression hoặc sao chép cùng lỗi.
- [ ] Có expected value độc lập cho các case nghiệp vụ quan trọng.
- [ ] Case sai khác được giữ lại thành regression test.

## Kết luận

Đối chiếu SpEL với logic Java tham chiếu là cách kiểm tra hành vi bằng hai implementation độc lập trên cùng dữ liệu. Java reference cần diễn đạt cùng quy tắc nghiệp vụ nhưng không gọi lại expression đang kiểm tra. Hãy so sánh kết quả theo đúng kiểu dữ liệu, căn chỉnh null, conversion, precision, timezone và collection ordering, rồi mở rộng bằng parameterized hoặc differential testing. Khi hai kết quả khác nhau, dùng input và từng điều kiện để tìm sai khác, đồng thời giữ expected value độc lập cho những quy tắc quan trọng.