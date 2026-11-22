# AopTestUtils để truy cập target khi cần kiểm tra mock sau proxy

Spring AOP thường bọc một bean bằng proxy để áp dụng các hành vi như transaction, security, caching hoặc logging. Vì vậy, object được inject vào test có thể là proxy thay vì chính instance thực thi logic. Nếu instance bên trong proxy là Mockito mock hoặc spy, việc xác minh tương tác trực tiếp trên biến proxy đôi khi không đúng đối tượng mà Mockito đang quản lý.

Spring Test cung cấp `AopTestUtils` để truy cập target object phía sau Spring AOP proxy. Trong kiểm thử, tiện ích này hữu ích khi cần lấy mock hoặc spy nằm bên trong proxy để kiểm tra lời gọi bằng Mockito. Cần dùng nó có chủ đích: hành động đang được kiểm tra vẫn nên đi qua proxy để các advice của Spring được thực thi; việc lấy target chủ yếu phục vụ quan sát và xác minh.

## 1. Vì sao bean Spring có thể là proxy?

Spring AOP áp dụng hành vi bổ sung bằng cách đặt một proxy quanh bean. Khi thành phần khác gọi bean qua proxy, proxy có thể thực hiện advice trước hoặc sau khi chuyển lời gọi đến target object.

Ví dụ, một service có transaction:

```java
@Service
@Transactional
public class OrderService {

    public void confirm(String orderId) {
        // Cập nhật trạng thái đơn hàng
    }
}
```

Khi transaction management được bật, bean được lấy từ Spring `ApplicationContext` có thể là một proxy. Lời gọi `confirm()` đi qua proxy để Spring mở transaction, gọi logic của target và hoàn tất hoặc rollback transaction theo kết quả.

Mối quan hệ có thể hình dung như sau:

```text
Test hoặc bean gọi OrderService
             |
             v
      Spring AOP proxy
             |
             | áp dụng advice
             | (transaction, security, ...)
             v
        Target object
             |
             v
       Logic nghiệp vụ
```

Do đó, biến được inject vào test có thể tham chiếu đến proxy. Điều này là bình thường và là một phần trong cách Spring cung cấp các tính năng AOP.

Spring AOP có thể sử dụng JDK dynamic proxy hoặc CGLIB proxy tùy cấu hình và kiểu bean. Cả hai đều có mục đích chuyển lời gọi qua lớp proxy trước khi tới target. Test không nên giả định bean luôn là một instance trực tiếp của lớp implementation.

## 2. Vấn đề khi mock hoặc spy nằm phía sau proxy

Mockito cung cấp `verify()`, `when()`, `doReturn()` và các API khác để làm việc với mock hoặc spy. Những API này cần nhận đúng object mà Mockito đã tạo hoặc quản lý.

Giả sử một bean được cấu hình làm spy, sau đó Spring AOP tạo proxy để áp dụng advice. Test nhận bean từ context và gọi:

```java
verify(orderService).calculateTotal("ORDER-42");
```

Nếu `orderService` là Spring AOP proxy còn Mockito spy nằm ở target bên trong, Mockito có thể báo `NotAMockException` vì proxy mà test đang truyền vào không phải mock/spy mà Mockito quản lý.

Vấn đề nằm ở ranh giới object:

- **Proxy:** object mà Spring đưa ra cho các thành phần sử dụng; nó điều phối lời gọi qua advice.
- **Target:** object thực thi logic ở phía sau proxy.
- **Mock/spy:** object do Mockito tạo hoặc bọc để kiểm soát, quan sát lời gọi.

Trong một số cấu hình, target có thể chính là Mockito spy. Khi đó test cần lấy target để xác minh tương tác trên đúng instance.

Không phải mọi proxy đều chứa Mockito mock hoặc spy. AOP proxy có thể chỉ bọc một bean bình thường. Trước khi gọi `verify()`, cần biết mục tiêu kiểm thử đã thực sự được cấu hình là mock/spy hay chưa.

## 3. AopTestUtils là gì?

`AopTestUtils` là tiện ích thuộc Spring Test, nằm trong package:

```java
org.springframework.test.util.AopTestUtils
```

Nó cung cấp các phương thức static để lấy target object từ một Spring AOP proxy:

| Phương thức | Hành vi |
|---|---|
| `getTargetObject(candidate)` | Lấy target ở một lớp proxy bên ngoài |
| `getUltimateTargetObject(candidate)` | Tiếp tục gỡ các lớp Spring AOP proxy lồng nhau để lấy target cuối cùng có thể truy cập |

Nếu đối tượng truyền vào không phải Spring AOP proxy, tiện ích trả lại chính đối tượng đó. Vì vậy, code test có thể gọi tiện ích tại điểm cần lấy target mà không phải tự kiểm tra từng loại proxy.

### getTargetObject()

Dùng `getTargetObject()` khi cần lấy target ngay phía sau lớp proxy hiện tại:

```java
OrderService target =
        AopTestUtils.getTargetObject(orderService);
```

Phương thức này gỡ một lớp proxy ở cấp ngoài. Nếu target nhận được vẫn là một Spring AOP proxy khác, nó chưa chắc là object cuối cùng.

### getUltimateTargetObject()

Dùng `getUltimateTargetObject()` khi có thể tồn tại nhiều lớp proxy lồng nhau và test cần target cuối cùng:

```java
OrderService target =
        AopTestUtils.getUltimateTargetObject(orderService);
```

Phương thức này tiếp tục truy cập target của các Spring AOP proxy lồng nhau. Đây thường là lựa chọn phù hợp khi cần tìm Mockito spy nằm sâu bên trong chuỗi proxy.

Cả hai phương thức đều là API kiểm thử. Chúng không thay đổi cách bean được đăng ký trong Spring context, không biến target thành mock và không tự tạo spy.

## 4. Ví dụ: lấy spy bên trong proxy để verify

Giả sử ứng dụng có một `PaymentGateway` được thay bằng Mockito spy trong test. Bean đó cũng được Spring AOP bọc bởi một proxy để áp dụng advice.

Test inject bean qua Spring context và gọi service sử dụng gateway:

```java
@SpringBootTest
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @SpyBean
    private PaymentGateway paymentGateway;

    @Test
    void sendsPaymentThroughGateway() {
        Order order = new Order(
                "ORDER-42",
                new BigDecimal("120000")
        );

        checkoutService.checkout(order);

        PaymentGateway target =
                AopTestUtils.getUltimateTargetObject(paymentGateway);

        verify(target).charge(
                eq("ORDER-42"),
                eq(new BigDecimal("120000"))
        );
    }
}
```

Ví dụ giả định:

- `CheckoutService` sử dụng `PaymentGateway` để gửi yêu cầu thanh toán.
- `@SpyBean` của Spring Boot thay bean gateway bằng spy để test có thể quan sát lời gọi trong khi vẫn giữ hành vi thật theo cấu hình spy.
- Bean được inject có thể được bọc thêm bởi Spring AOP.
- `AopTestUtils.getUltimateTargetObject()` lấy target để Mockito verify đúng spy.

Lời gọi `checkoutService.checkout(order)` vẫn đi qua bean do Spring quản lý. Test chỉ lấy target sau khi hành động hoàn tất để xác minh đối số đã gửi. Cách này giữ được hành vi advice trên đường gọi thực tế, đồng thời cho phép kiểm tra tương tác ở target.

Trong một dự án không dùng Spring Boot, có thể cấu hình spy bằng Mockito trong test configuration hoặc một cơ chế thay thế bean tương đương. Điểm cốt lõi vẫn là target cần lấy phải là object Mockito đã quản lý.

## 5. Kiểm tra target có thực sự là mock hoặc spy

Không nên mặc định rằng mọi target đều là Mockito object. Có thể dùng `Mockito.mockingDetails()` để kiểm tra trạng thái trước khi verify:

```java
Object target =
        AopTestUtils.getUltimateTargetObject(paymentGateway);

assertTrue(
        Mockito.mockingDetails(target).isSpy(),
        "payment gateway target should be a Mockito spy"
);
```

Mockito cũng cung cấp `isMock()` để xác định một object có được Mockito quản lý hay không. Spy cũng là một dạng mock trong mô hình Mockito, nhưng `isSpy()` giúp phân biệt rõ loại object cần quan sát.

Nếu target không phải mock hoặc spy, `verify(target)` sẽ thất bại với lỗi `NotAMockException`. Khi đó, cần xem lại cách test thay thế bean, cấu trúc proxy và object mà test đang inject.

Có thể dùng một biến có kiểu cụ thể nếu biết chắc target là implementation hoặc interface tương ứng:

```java
PaymentGateway target =
        AopTestUtils.getUltimateTargetObject(paymentGateway);
```

Nếu kiểu target không thể xác định tại thời điểm biên dịch, có thể nhận kết quả dưới dạng `Object`, kiểm tra loại và cast sau khi xác nhận phù hợp. Không nên cast mù quáng chỉ vì biến proxy được inject có kiểu interface.

## 6. Proxy lồng nhau và lựa chọn phương thức

Một bean có thể đi qua nhiều lớp proxy trong quá trình cấu hình. Chẳng hạn, một lớp tích hợp có thể bọc bean để áp dụng một nhóm hành vi, trong khi một proxy khác được tạo bởi cơ chế AOP.

Minh họa:

```text
Test
 |
 v
Proxy A
 |
 v
Proxy B
 |
 v
Mockito spy
 |
 v
Logic thật
```

Nếu dùng `getTargetObject()`, kết quả có thể là Proxy B. Test vẫn chưa có Mockito spy để verify. Dùng `getUltimateTargetObject()` giúp tiếp tục gỡ các lớp Spring AOP proxy lồng nhau.

Quy tắc lựa chọn:

- Biết chỉ có một lớp Spring AOP proxy và cần target trực tiếp: `getTargetObject()`.
- Có thể có proxy lồng nhau hoặc không kiểm soát được cấu trúc proxy: `getUltimateTargetObject()`.
- Đối tượng không phải Spring AOP proxy: không cần gỡ; tiện ích trả lại candidate.

Cần lưu ý rằng tiện ích này làm việc với Spring AOP proxy và target source mà proxy cung cấp. Nó không phải công cụ tổng quát để bóc mọi wrapper, decorator, dynamic proxy do thư viện khác tạo ra hoặc mọi lớp bao ngoài tùy ý. Nếu target source có cách cung cấp target đặc biệt hoặc không thể truy cập target theo cách thông thường, việc unwrap có thể không cho kết quả như mong đợi và có thể phát sinh lỗi.

## 7. Vì sao vẫn phải gọi qua proxy?

Mục đích của AopTestUtils là giúp test quan sát target. Nó không có nghĩa test nên gọi trực tiếp target để thực hiện hành vi đang kiểm tra.

Ví dụ, với một service có `@Transactional`:

Giả sử trong bài test này target của bean cũng đã được cấu hình thành Mockito spy, chẳng hạn bằng `@SpyBean` hoặc test configuration tương đương.

```java
OrderService target =
        AopTestUtils.getUltimateTargetObject(orderService);

// Không dùng target để thay thế lời gọi qua bean Spring:
target.confirm("ORDER-42");
```

Lời gọi trực tiếp target bỏ qua proxy. Vì vậy, transaction advice hoặc các advice khác gắn trên proxy có thể không được thực thi. Điều đó làm thay đổi điều kiện mà ứng dụng thực sự chạy.

Nếu target là spy và cần verify tương tác, cách tổ chức phù hợp:

```java
// Act: gọi bean được Spring quản lý
orderService.confirm("ORDER-42");

// Assert: lấy target để kiểm tra tương tác nếu cần
OrderService target =
        AopTestUtils.getUltimateTargetObject(orderService);

verify(target).confirm("ORDER-42");
```

Trong ví dụ này, lời gọi nghiệp vụ đi qua proxy. Việc lấy target chỉ diễn ra ở bước xác minh. Nếu test cần xác nhận transaction, security hoặc cache advice hoạt động, cần quan sát kết quả ở ranh giới phù hợp hoặc kiểm tra trạng thái mà advice tạo ra; chỉ verify phương thức target được gọi chưa chứng minh toàn bộ advice đã hoạt động đúng.

## 8. AopTestUtils không thay thế ArgumentCaptor hoặc matcher

AopTestUtils giải quyết câu hỏi **đối tượng nào cần đưa cho Mockito** khi target nằm sau proxy. Nó không quyết định cách so khớp đối số.

Sau khi lấy target, test vẫn dùng các công cụ Mockito bình thường:

- Giá trị cụ thể hoặc `eq(expected)` khi cần xác nhận dữ liệu chính xác.
- `argThat(...)` khi cần kiểm tra một quy tắc trên đối số.
- `ArgumentCaptor` khi cần giữ đối số thực tế để kiểm tra nhiều thuộc tính.
- `same(expected)` khi identity của object là điều cần bảo vệ.

Ví dụ dùng captor trên target:

```java
PaymentGateway target =
        AopTestUtils.getUltimateTargetObject(paymentGateway);

checkoutService.checkout(order);

ArgumentCaptor<PaymentRequest> captor =
        ArgumentCaptor.forClass(PaymentRequest.class);

verify(target).charge(captor.capture());

PaymentRequest actual = captor.getValue();
assertEquals("ORDER-42", actual.orderId());
assertEquals(new BigDecimal("120000"), actual.amount());
```

Ở đây AopTestUtils giúp lấy đúng spy; ArgumentCaptor giữ request được gửi; assertion kiểm tra nội dung request. Mỗi công cụ giải quyết một phần riêng của bài kiểm thử.

## 9. Khi nào nên dùng AopTestUtils?

AopTestUtils hữu ích trong những tình huống cụ thể:

- Bean trong Spring context là AOP proxy, còn mock hoặc spy cần verify nằm ở target.
- Một bean có nhiều lớp Spring AOP proxy lồng nhau.
- Test cần xác nhận target có thực sự là Mockito mock/spy.
- Cần truy cập target để kiểm tra trạng thái hoặc lời gọi mà proxy không trực tiếp thể hiện qua API Mockito.

Không nên dùng nó mặc định cho mọi bean trong test. Nếu bean không phải proxy, hoặc Mockito có thể verify trực tiếp object đã inject, gọi AopTestUtils không tạo thêm giá trị đáng kể.

Cũng không nên dùng target access để kiểm tra chi tiết nội bộ khi hành vi công khai của bean đã đủ để chứng minh yêu cầu. Test càng phụ thuộc vào cấu trúc proxy và target, nó càng dễ bị ảnh hưởng khi cách cấu hình AOP thay đổi dù hành vi ứng dụng vẫn giữ nguyên.

## 10. Những giới hạn và lưu ý quan trọng

### Chỉ gỡ Spring AOP proxy

AopTestUtils được thiết kế cho proxy của Spring AOP. Nếu object là wrapper của thư viện khác, Java dynamic proxy không do Spring AOP tạo, decorator tự viết hoặc một container proxy khác, tiện ích không đảm bảo tìm được object nằm sâu bên trong.

### Target source có thể ảnh hưởng khả năng truy cập

Spring AOP sử dụng `TargetSource` để cung cấp target. Với target source thông thường, test có thể lấy target để kiểm tra. Với cấu hình target source đặc biệt, target có thể được tạo hoặc chọn theo từng lần truy cập. Khi đó, không nên giả định việc lấy target luôn trả về một instance ổn định hoặc giống instance của lần gọi trước.

Nếu target source không thể cung cấp target theo cách mà tiện ích yêu cầu, thao tác unwrap có thể thất bại. Hãy đọc exception và xem cấu hình proxy thay vì tiếp tục cast hoặc verify một object chưa xác định.

### Không thay đổi thứ tự advice

AopTestUtils không làm thay đổi thứ tự advice, không tắt transaction và không sửa proxy. Nó chỉ cung cấp cách truy cập target cho mục đích kiểm thử. Việc gọi phương thức trên target trực tiếp vẫn có thể bỏ qua advice như đã giải thích.

### Cẩn thận với target mutable

Nếu lấy target rồi thay đổi trực tiếp trạng thái của nó trong test, test có thể bỏ qua các quy tắc mà ứng dụng thường thực thi qua proxy. Hãy dùng target chủ yếu để quan sát hoặc verify. Nếu cần thiết lập dữ liệu, ưu tiên API công khai, fixture hoặc cơ chế test phù hợp với phạm vi kiểm thử.

### Không đưa vào mã production

AopTestUtils thuộc Spring Test và được thiết kế cho mã kiểm thử. Không dùng nó trong service hoặc logic nghiệp vụ production để truy cập implementation bên trong proxy. Nếu ứng dụng cần một đối tượng hoặc hành vi cụ thể, hãy thiết kế dependency và API phù hợp thay vì phụ thuộc vào cấu trúc proxy.

## 11. Chẩn đoán lỗi khi verify sau proxy

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `NotAMockException` khi gọi `verify(bean)` | Biến bean là Spring AOP proxy, Mockito spy nằm ở target | Lấy target bằng `getUltimateTargetObject()`, rồi kiểm tra `mockingDetails()` |
| Target sau `getTargetObject()` vẫn không phải mock | Có nhiều lớp proxy | Thử `getUltimateTargetObject()` |
| Cast target thất bại | Target không có kiểu mà test giả định | Kiểm tra kiểu thực tế và cấu hình bean |
| Không có tương tác được verify | Test gọi nhầm bean, lời gọi không đi qua spy hoặc hành vi không xảy ra | Theo dõi đường dependency và xác nhận spy được đăng ký trong context |
| Lỗi khi unwrap | Target source hoặc proxy không cung cấp target theo cách tiện ích hỗ trợ | Xem loại proxy, target source và nguyên nhân gốc của exception |
| Advice không chạy trong test | Test gọi trực tiếp target thay vì proxy | Thực hiện hành động qua bean inject từ Spring context |

Khi gặp `NotAMockException`, không nên ngay lập tức kết luận Mockito không hỗ trợ Spring AOP. Trước hết, hãy xác định object nào là proxy và object nào là mock/spy. Sau đó, kiểm tra target mà AopTestUtils trả về có thực sự do Mockito quản lý hay không.

## 12. Quy trình sử dụng trong một bài test

Có thể tổ chức test theo trình tự sau:

1. **Chuẩn bị Spring context:** khai báo cấu hình AOP và bean cần kiểm tra.
2. **Chuẩn bị mock hoặc spy:** dùng cơ chế test phù hợp để thay hoặc bọc dependency cần quan sát.
3. **Inject bean qua Spring:** giữ reference mà ứng dụng thực sự sử dụng.
4. **Thực hiện hành động qua bean proxy:** gọi service hoặc controller theo đường đi bình thường.
5. **Lấy target khi cần:** dùng `getTargetObject()` hoặc `getUltimateTargetObject()` tùy số lớp proxy.
6. **Xác nhận target là mock/spy:** dùng `Mockito.mockingDetails()` nếu cấu trúc chưa chắc chắn.
7. **Verify hoặc capture:** kiểm tra tương tác và dữ liệu đầu vào theo hợp đồng cần bảo vệ.

Trình tự này giữ rõ hai mục tiêu: ứng dụng được gọi qua Spring-managed bean để proxy hoạt động; Mockito kiểm tra đúng mock/spy nằm ở target khi cấu trúc proxy khiến reference bên ngoài không phải mock.

AopTestUtils là công cụ nhỏ nhưng hữu ích khi kiểm thử các bean Spring có AOP proxy. Hiểu rõ proxy, target và Mockito object giúp tránh lỗi verify nhầm instance, đồng thời giữ được đường thực thi thực tế qua Spring. Chỉ truy cập target khi cần kiểm tra hoặc quan sát; hành động nghiệp vụ cần kiểm thử vẫn nên đi qua bean mà Spring cung cấp.

