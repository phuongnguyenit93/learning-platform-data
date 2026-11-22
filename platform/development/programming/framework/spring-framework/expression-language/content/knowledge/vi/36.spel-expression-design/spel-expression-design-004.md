# Chọn method Java thay cho chuỗi expression khó đọc

Spring Expression Language (SpEL) phù hợp với các biểu thức khai báo ngắn như đọc property, so sánh, tính toán đơn giản và lọc collection. Khi một expression chứa nhiều tầng điều kiện, logic lặp lại, nhiều method call hoặc quy tắc nghiệp vụ phức tạp, nên cân nhắc chuyển phần logic đó thành **method Java có tên rõ ràng**.

SpEL có thể giữ vai trò kết nối dữ liệu hoặc diễn đạt một điều kiện nhỏ; Java đảm nhiệm phần cần kiểu dữ liệu rõ ràng, cấu trúc, kiểm thử và xử lý lỗi. Chuyển logic sang method không có nghĩa phải bỏ SpEL khỏi toàn bộ luồng: một expression ngắn vẫn có thể gọi method Java nếu điểm tích hợp cần cấu hình động.

## Khi nào SpEL vẫn phù hợp?

SpEL thường phù hợp khi biểu thức ngắn, dễ đọc và mô tả trực tiếp một quy tắc:

~~~java
Expression expression =
        parser.parseExpression("active and total >= #minimum");
~~~

Người đọc có thể hiểu ngay điều kiện: đối tượng phải active và total phải đạt ngưỡng. Những trường hợp phù hợp khác gồm:

- Đọc một property hoặc một chuỗi property ngắn.
- So sánh số, chuỗi, ngày tháng hoặc trạng thái.
- Kết hợp một vài điều kiện bằng toán tử logic.
- Lọc collection nhỏ bằng selection.
- Tính một giá trị đơn giản trong cấu hình hoặc annotation.
- Cho phép quản trị viên cấu hình một quy tắc nhỏ đã được giới hạn rõ ràng.

Khi expression vẫn thể hiện một quy tắc có thể đọc như câu điều kiện, SpEL giúp cấu hình linh hoạt mà không cần viết thêm class Java.

## Dấu hiệu nên chuyển logic sang Java

Không có giới hạn số ký tự hoặc số toán tử áp dụng cho mọi dự án. Hãy cân nhắc refactor khi có một hoặc nhiều dấu hiệu:

- **Điều kiện lồng nhiều tầng:** nhiều ternary hoặc nhiều nhánh khiến người đọc phải lần theo từng trường hợp.
- **Logic lặp lại:** cùng một phép kiểm tra hoặc chuỗi truy cập property xuất hiện ở nhiều expression.
- **Object graph phức tạp:** nhiều tầng property có thể null, kéo theo nhiều bước null-safe và giá trị mặc định.
- **Collection operation nhiều tầng:** selection lồng nhau, projection nối tiếp và điều kiện phức tạp trên từng phần tử.
- **Nhiều method call:** biểu thức vừa đọc dữ liệu, chuẩn hóa, tính toán, chuyển đổi và định dạng kết quả.
- **Quy tắc nghiệp vụ nhiều khái niệm:** chính sách giá, quyền lợi, hạn mức, điều kiện duyệt hoặc trạng thái quy trình.
- **Cần xử lý lỗi theo từng bước:** phải phân biệt dữ liệu thiếu, sai định dạng, không đủ quyền hoặc trạng thái không hợp lệ.
- **Có side effect:** ghi dữ liệu, gửi thông báo, gọi mạng hoặc thay đổi trạng thái.
- **Khó kiểm thử:** muốn kiểm tra một nhánh phải dựng context phức tạp hoặc đọc cả chuỗi expression mới hiểu được hành vi.

Thêm dấu ngoặc và xuống dòng có thể giúp định dạng, nhưng không giải quyết việc một chuỗi đang gánh quá nhiều trách nhiệm. Method Java có tên theo ý nghĩa nghiệp vụ thường thể hiện mục đích rõ hơn.

## Ví dụ: chuyển điều kiện dài thành method Java

Giả sử đơn hàng chỉ đủ điều kiện áp dụng ưu đãi nếu khách hàng đang hoạt động, đơn hàng chưa bị hủy, tổng tiền đạt ngưỡng và khách hàng thuộc nhóm GOLD hoặc PLATINUM.

Expression có thể bắt đầu như sau:

~~~java
Expression expression = parser.parseExpression(
        "customer.active and not cancelled "
        + "and total >= #minimum "
        + "and (customer.tier == 'GOLD' "
        + "or customer.tier == 'PLATINUM')");
~~~

Khi quy tắc bổ sung giới hạn theo khu vực, thời gian, loại sản phẩm hoặc số lần sử dụng, expression sẽ khó đọc và khó kiểm thử riêng từng điều kiện.

Chuyển quy tắc sang một class Java:

~~~java
public final class PromotionPolicy {

    public boolean isEligible(
            Customer customer,
            Order order,
            BigDecimal minimum) {

        if (customer == null || order == null) {
            return false;
        }

        if (!customer.isActive() || order.isCancelled()) {
            return false;
        }

        if (order.getTotal().compareTo(minimum) < 0) {
            return false;
        }

        return "GOLD".equals(customer.getTier())
                || "PLATINUM".equals(customer.getTier());
    }
}
~~~

Các điều kiện có kiểu rõ ràng, có thể đặt breakpoint và kiểm tra từng giá trị. Unit test cũng có thể gọi trực tiếp PromotionPolicy mà không cần tạo parser hoặc EvaluationContext.

Nếu cần giữ SpEL làm điểm gọi, expression có thể ngắn lại:

~~~java
Expression expression =
        parser.parseExpression(
                "@promotionPolicy.isEligible("
                + "#customer, #order, #minimum)");
~~~

Context cần có BeanResolver để tìm bean promotionPolicy và phải cho phép method invocation. Nếu integration không cung cấp bean reference, có thể gọi method Java trực tiếp từ service hoặc cung cấp một root object/helper được giới hạn.

## Đặt tên method theo ý nghĩa nghiệp vụ

Tên method nên mô tả quyết định hoặc kết quả mà caller cần:

- **isEligibleForPromotion(...)**
- **canShipOrder(...)**
- **calculateNetPrice(...)**
- **requiresManualReview(...)**
- **isWithinCreditLimit(...)**

Các tên chung chung như check, process hoặc evaluate thường không đủ thông tin nếu method chứa nhiều quy tắc.

Một method nên có một trách nhiệm chính, tham số thể hiện dữ liệu đầu vào và kiểu trả về thể hiện kết quả. Nếu quy tắc cần nhiều dữ liệu, cân nhắc gom chúng vào một object đầu vào có tên thay vì truyền một danh sách tham số dài:

~~~java
public record PromotionRequest(
        Customer customer,
        Order order,
        BigDecimal minimumAmount) {
}
~~~

~~~java
public boolean isEligible(PromotionRequest request) {
    // Kiểm tra quy tắc ưu đãi ở đây.
}
~~~

Object đầu vào giúp chữ ký ổn định hơn khi quy tắc bổ sung dữ liệu và làm test dễ dựng từng trường hợp.

## Tách phép tính, quyết định và side effect

Khi chuyển logic sang Java, hãy phân biệt ba loại hành vi:

1. **Tính toán:** nhận dữ liệu và trả về kết quả, ví dụ tính giá sau thuế.
2. **Quyết định:** trả Boolean hoặc một kết quả nghiệp vụ, ví dụ có đủ điều kiện duyệt hay không.
3. **Side effect:** ghi database, gửi email, cập nhật trạng thái hoặc gọi hệ thống bên ngoài.

SpEL thường phù hợp nhất với phép tính và quyết định ngắn. Side effect nên nằm trong service hoặc application layer có transaction, logging, retry và xử lý lỗi phù hợp.

Không nên gọi method có side effect từ expression chỉ vì context cho phép method invocation. Framework có thể đánh giá biểu thức nhiều lần hoặc ở những thời điểm khó dự đoán. Nếu mỗi lần evaluate đều gửi thông báo hoặc cập nhật trạng thái, hành vi có thể bị lặp.

Một thiết kế rõ ràng là để SpEL kiểm tra điều kiện rồi Java quyết định có thực hiện hành động hay không:

~~~java
boolean eligible =
        Boolean.TRUE.equals(
                expression.getValue(context, order, Boolean.class));

if (eligible) {
    promotionService.applyPromotion(order);
}
~~~

Expression trả kết quả kiểm tra; service Java thực hiện thay đổi trạng thái sau khi caller quyết định.

## Gọi method Java từ SpEL

Chuyển logic sang Java không có nghĩa SpEL không thể gọi method. SpEL hỗ trợ method invocation trên root object, variable hoặc bean nếu EvaluationContext có khả năng tương ứng.

### Gọi method trên root object

Có thể đặt một helper làm root object:

~~~java
public final class OrderRules {

    public boolean isHighValue(Order order) {
        return order != null
                && order.getTotal().compareTo(
                        new BigDecimal("1000.00")) >= 0;
    }
}
~~~

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(new OrderRules());

context.setVariable("order", order);

Expression expression =
        parser.parseExpression("isHighValue(#order)");

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

Method được gọi trên root object OrderRules. Logic nằm trong Java; SpEL chỉ truyền dữ liệu vào method và nhận kết quả.

### Gọi method trên Spring bean

Nếu context có BeanResolver, expression có thể tham chiếu Spring bean:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(
        new BeanFactoryResolver(applicationContext));

context.setVariable("order", order);

Expression expression =
        parser.parseExpression(
                "@orderRules.isHighValue(#order)");
~~~

Bean orderRules phải tồn tại trong BeanFactory hoặc ApplicationContext. Method invocation cũng phải được resolver của context hỗ trợ.

Một số integration Spring tự tạo EvaluationContext với khả năng riêng. Khi tự tạo StandardEvaluationContext, cần cấu hình BeanResolver rõ ràng nếu muốn dùng cú pháp @beanName. Chỉ expose bean nhỏ có API phù hợp; không đưa repository, application context hoặc service có quyền rộng vào context của expression không đáng tin cậy.

## Khi nào nên gọi method trực tiếp từ Java?

Nếu caller đã là Java code và logic chỉ được dùng tại một điểm, gọi method trực tiếp thường rõ ràng hơn việc tạo chuỗi SpEL chỉ để gọi lại method:

~~~java
boolean eligible =
        promotionPolicy.isEligible(customer, order, minimum);
~~~

Cách này có kiểm tra kiểu ở compile time, hỗ trợ rename và tìm references bằng IDE, đồng thời giúp người đọc lần theo call hierarchy. Không cần parser, EvaluationContext hoặc xử lý lỗi parse.

SpEL có ích khi cần quy tắc được cấu hình dưới dạng chuỗi hoặc tại một điểm tích hợp Spring vốn đã đánh giá expression. Nếu không có nhu cầu cấu hình động, thêm SpEL vào giữa một lời gọi Java đơn giản chỉ làm tăng số thành phần phải quản lý.

## So sánh SpEL và method Java

| Tiêu chí | SpEL expression | Method Java |
|---|---|---|
| Cấu trúc phù hợp | Điều kiện và phép tính ngắn | Logic nhiều bước hoặc có nhánh |
| Kiểu dữ liệu | Kiểm tra nhiều phần ở runtime | Kiểm tra kiểu ở compile time |
| Debug | Cần xem expression và EvaluationContext | Có thể đặt breakpoint theo dòng |
| Refactor | Chuỗi có thể không được IDE cập nhật | IDE hỗ trợ rename và tìm references |
| Kiểm thử | Cần parser, context và root object | Có thể unit test trực tiếp |
| Tái sử dụng | Dùng lại Expression hoặc template | Gọi method từ nhiều caller |
| Cấu hình động | Thuận tiện cho rule được cấu hình | Cần thay đổi code hoặc dữ liệu đầu vào |
| Side effect | Khó kiểm soát nếu evaluate lặp lại | Có thể đặt trong service và transaction rõ ràng |

Không có lựa chọn luôn tốt hơn. Hãy chọn theo nơi logic được quản lý, ai có quyền thay đổi quy tắc và mức độ phức tạp của hành vi.

## Chuyển expression khó đọc thành method theo từng bước

Một quy trình refactor có thể thực hiện như sau:

1. **Ghi lại hành vi hiện tại:** liệt kê property, variable, method và các nhánh mà expression đang sử dụng.
2. **Xác định kết quả:** expression trả Boolean, số, chuỗi, collection hay object?
3. **Đặt tên nghiệp vụ:** chọn tên method mô tả điều kiện hoặc phép tính.
4. **Định nghĩa tham số có kiểu:** chỉ truyền dữ liệu method cần; tránh truyền application context hoặc object có quyền rộng.
5. **Chuyển logic từng phần:** giữ nguyên thứ tự điều kiện, quy tắc null và cách so sánh.
6. **Viết unit test:** bao phủ trường hợp bình thường, biên, null và dữ liệu không hợp lệ.
7. **Thay expression:** dùng lời gọi method ngắn hoặc gọi Java trực tiếp.
8. **So sánh kết quả:** chạy trên dữ liệu đại diện để xác nhận hành vi trước và sau tương đương.
9. **Loại bỏ logic trùng lặp:** không duy trì hai phiên bản quy tắc độc lập.

Nếu expression được lưu trong database hoặc cấu hình bên ngoài, cần có kế hoạch cập nhật rule và tương thích phiên bản. Không đổi chữ ký method mà không tìm các expression đang gọi method đó.

## Kiểm thử method Java

Một method nghiệp vụ có thể được kiểm thử mà không cần SpEL:

~~~java
class PromotionPolicyTests {

    private final PromotionPolicy policy =
            new PromotionPolicy();

    @Test
    void rejectsInactiveCustomer() {
        Customer customer = Customer.inactive();
        Order order = Order.withTotal("200.00");

        boolean result = policy.isEligible(
                customer,
                order,
                new BigDecimal("100.00"));

        assertFalse(result);
    }

    @Test
    void acceptsEligibleCustomerAndOrder() {
        Customer customer = Customer.goldMember();
        Order order = Order.withTotal("200.00");

        boolean result = policy.isEligible(
                customer,
                order,
                new BigDecimal("100.00"));

        assertTrue(result);
    }
}
~~~

Ví dụ minh họa hai trường hợp. Bộ test thực tế nên bao phủ từng điều kiện độc lập và các kết hợp quan trọng: đơn hàng bị hủy, tổng tiền đúng bằng ngưỡng, khách hàng không có hạng thành viên hoặc dữ liệu đầu vào null.

Khi method chỉ nhận dữ liệu và trả kết quả, test thường không cần khởi động Spring context. Nếu method phụ thuộc repository hoặc dịch vụ khác, có thể dùng mock cho unit test hoặc integration test cho hành vi cần kiểm tra với hạ tầng thật.

## Giữ SpEL ở vai trò điều phối nhỏ

Trong một số ứng dụng, expression vẫn cần kết hợp vài giá trị hoặc gọi method đã được chuẩn bị:

~~~java
Expression expression =
        parser.parseExpression(
                "@promotionPolicy.isEligible(#customer, #order)");
~~~

Method Java xử lý quy tắc; SpEL chỉ nối dữ liệu của context với lời gọi method.

Nếu expression phải quyết định nhiều nhánh rồi gọi nhiều bean khác nhau, hãy chuyển orchestration sang Java. Một service có thể gọi policy, repository và collaborator theo thứ tự rõ ràng. Expression không nên trở thành một ngôn ngữ workflow thu nhỏ.

## Lưu ý về hiệu năng

Chuyển expression phức tạp sang method Java có thể giảm công việc diễn giải và làm rõ đường gọi, nhưng không nên refactor chỉ dựa trên giả định Java luôn nhanh hơn đáng kể.

Nếu expression được đánh giá thường xuyên, trước tiên hãy parse một lần và tái sử dụng Expression. Sau đó benchmark với dữ liệu và tần suất thực tế. Nếu cần, so sánh interpreter, compiler mode và lời gọi Java trực tiếp.

Chi phí còn phụ thuộc số lần truy cập property, method invocation, conversion, kích thước collection và cách quản lý context. Một method Java vẫn có thể chậm nếu nó gọi database hoặc thực hiện thuật toán tốn kém. Tối ưu nên dựa trên đo lường; lợi ích về khả năng đọc, kiểm thử và quản lý kiểu thường là lý do refactor rõ ràng hơn.

## Lưu ý về bảo mật

Method invocation trong SpEL mở ra khả năng thực thi method trên object mà EvaluationContext expose. Nếu expression do người dùng hoặc quản trị viên nhập, không nên cho phép gọi tùy ý method của service.

Hãy giới hạn:

- Root object chỉ chứa dữ liệu cần thiết.
- Bean được tham chiếu có API nhỏ và được chọn rõ ràng.
- Method được phép theo target type, tên và chữ ký.
- Không expose method có side effect hoặc truy cập tài nguyên nếu không cần.
- Không nối input người dùng vào expression source; truyền dữ liệu bằng variable.
- Dùng context giới hạn khi biểu thức chỉ cần đọc property.

Một method Java có tên rõ ràng không tự động an toàn. Quyền mà expression có thể sử dụng phụ thuộc object và resolver được cung cấp cho context.

## Khi nào nên giữ logic trong SpEL?

Có thể giữ expression khi nó vẫn ngắn, dễ đọc và chỉ thể hiện một quy tắc khai báo:

~~~text
active and total >= #minimum
~~~

Có thể chuyển sang Java khi biểu thức chứa nhiều tầng điều kiện, logic lặp lại, xử lý null ở nhiều cấp, collection operation phức tạp hoặc phụ thuộc nhiều method.

Một tiêu chí thực tế: nếu người bảo trì phải giải thích từng phần của chuỗi trước khi hiểu tên nghiệp vụ của nó, hãy cân nhắc đặt logic vào method có tên rõ ràng. Nếu biểu thức đọc lên đã thể hiện ngay quy tắc, SpEL vẫn là lựa chọn gọn.

## Kết luận

SpEL phù hợp với biểu thức ngắn, khai báo và dễ đọc. Khi chuỗi trở thành nơi chứa nhiều nhánh nghiệp vụ, logic lặp lại, nhiều tầng collection hoặc side effect, hãy chuyển phần đó thành **method Java có kiểu và tên rõ ràng**. Method giúp IDE hỗ trợ refactor, dễ đặt breakpoint, dễ unit test và kiểm soát lỗi tốt hơn.

Nếu vẫn cần cấu hình động, giữ SpEL làm lớp điều phối nhỏ và gọi method đã được giới hạn qua root object hoặc bean reference phù hợp. Nếu caller đã là Java và không cần rule dạng chuỗi, gọi method trực tiếp sẽ đơn giản hơn. Hãy refactor theo từng bước, kiểm tra hành vi trước và sau, đồng thời chỉ expose những method mà EvaluationContext thực sự cần.
