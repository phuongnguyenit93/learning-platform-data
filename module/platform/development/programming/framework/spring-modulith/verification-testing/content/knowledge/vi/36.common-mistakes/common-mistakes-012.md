# Gọi event publisher nhưng không xác minh listener

Trong **SPRING_MODULITH_VERIFICATION_TESTING**, một mục tiêu quan trọng là chứng minh module thực sự cộng tác đúng qua sự kiện, bên cạnh việc dùng `ApplicationModules` kiểm chứng ranh giới phụ thuộc. Lỗi phổ biến là gọi `ApplicationEventPublisher.publishEvent(...)`, thấy test xanh hoặc bắt được `PublishedEvents`, rồi kết luận module nhận đã xử lý thành công. Test ấy chỉ mới chứng minh **phía phát**; listener có thể không được đăng ký, chưa chạy, gặp lỗi hoặc ghi sai dữ liệu.

Ví dụ xuyên suốt dùng hai module Spring Modulith: `ordering` phát `OrderPlaced`, `billing` tạo hóa đơn. Giả định `OrderPlaced` là API công khai của module `ordering`, có dạng `record OrderPlaced(UUID orderId, BigDecimal total) {}`; `OrderService.place(UUID, BigDecimal)` phát sự kiện sau khi tạo đơn; `InvoiceService.createIfAbsent(UUID, BigDecimal)` tạo hóa đơn nếu chưa tồn tại; `InvoiceRepository` có `findByOrderId(UUID)` trả `Optional<Invoice>` và `countByOrderId(UUID)`. `Invoice` cung cấp `getOrderId()` và `getAmount()`. Các lớp nghiệp vụ là fixture minh họa cần hiện thực trong ứng dụng; các API Spring/JUnit được chỉ ra bằng đúng tên.

## 1. Nhầm ba mức kiểm chứng thành một

Ba câu hỏi khác nhau cần các bằng chứng khác nhau:

| Mức | Điều cần chứng minh | Assertion phù hợp |
| --- | --- | --- |
| **Publisher** | `ordering` đã phát đúng `OrderPlaced` | `PublishedEvents` kiểm tra loại, ID và giá trị event |
| **Listener** | `billing` được kích hoạt bởi event đã commit | Test có bean listener thật, kích thích event trong transaction và chờ phản ứng |
| **Kết quả nghiệp vụ** | Hóa đơn đúng đã được ghi và có thể đọc lại | Query `InvoiceRepository`, đối chiếu `orderId`, `amount`, số bản ghi |

Một test ở mức publisher không thay thế được hai mức còn lại. `ApplicationModules.of(ShopApplication.class).verify()` cũng chỉ kiểm tra quy tắc kiến trúc; nó không tự chứng minh listener đã xử lý từng event đúng.

## 2. Dùng `PublishedEvents` rồi ngộ nhận đã kiểm tra người nhận

Ví dụ JUnit dưới đây **có giá trị**, nhưng phạm vi chỉ là hợp đồng phát sự kiện:

```java
@ApplicationModuleTest // Test trong package của module ordering
class OrderPublicationTests {

    @Autowired OrderService orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        UUID id = UUID.randomUUID();
        BigDecimal total = new BigDecimal("125.00");

        orders.place(id, total);

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event -> {
                    assertThat(event.orderId()).isEqualTo(id);
                    assertThat(event.total()).isEqualByComparingTo(total);
                });
    }
}
```

Nếu xóa listener ở `billing`, test trên vẫn có thể xanh vì `PublishedEvents` ghi nhận sự kiện **được xuất bản**, không xác nhận hóa đơn đã được tạo. Cách kiểm chứng lỗi này: tạm vô hiệu hóa listener; test publisher có thể vẫn xanh, còn test side effect ở mục 5 phải đỏ.

## 3. Khởi động sai phạm vi module khiến listener không tồn tại trong test

`@ApplicationModuleTest` mặc định tập trung vào module chứa test. Đặt test trong `ordering` thường sẽ **không** bootstrap bean thuộc `billing`; việc gọi publisher ở đó không kiểm tra listener của `billing`. Để kiểm tra người nhận, đặt integration test trong package của module `billing`, nơi listener và repository có mặt:

```java
package com.example.shop.billing;

@ApplicationModuleTest
class BillingEventIntegrationTests {
    @Autowired ApplicationEventPublisher publisher;
    @Autowired InvoiceRepository invoices;
    @Autowired PlatformTransactionManager transactionManager;
}
```

Đường dẫn package `com.example.shop.billing` là ví dụ; dùng package module thực tế. Nếu cần đi trọn luồng từ HTTP/service của `ordering` sang `billing`, viết thêm `@SpringBootTest` nạp cả ứng dụng. Cần kiểm tra **bean nào được bootstrap**, không suy luận từ tên annotation. `BootstrapMode.ALL_DEPENDENCIES` chỉ nạp các dependency theo quan hệ module và không mặc nhiên nạp mọi subscriber ngang hàng.

## 4. Nhầm listener được gọi trực tiếp với listener được đăng ký qua Spring

Listener dùng API Spring Modulith có thể được khai báo như sau:

```java
@Component
class InvoiceOnOrderPlaced {

    private final InvoiceService invoiceService;

    InvoiceOnOrderPlaced(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        invoiceService.createIfAbsent(event.orderId(), event.total());
    }
}
```

`@ApplicationModuleListener` phối hợp xử lý event theo transaction và mặc định bất đồng bộ. Một unit test gọi thẳng `on(...)` có thể xác nhận logic ủy quyền, nhưng **không** chứng minh Spring đã đăng ký listener hoặc kích hoạt đúng phase:

```java
@Test
void delegatesPayloadToInvoiceService() {
    InvoiceService service = mock(InvoiceService.class);
    InvoiceOnOrderPlaced listener = new InvoiceOnOrderPlaced(service);
    UUID id = UUID.randomUUID();
    BigDecimal total = new BigDecimal("125.00");

    listener.on(new OrderPlaced(id, total));

    verify(service).createIfAbsent(id, total);
}
```

Hãy giữ unit test này cho phần xử lý đơn lẻ, rồi bổ sung integration test phát event qua `ApplicationEventPublisher` để kiểm tra wiring thật.

## 5. Bỏ qua commit nên `@TransactionalEventListener` không chạy

`@ApplicationModuleListener` dùng semantics của transactional event listener: tác vụ phải được kích hoạt sau khi transaction phát event **commit thành công**. Nếu test chỉ `publishEvent` ngoài transaction, listener có thể không được gọi. Nếu bọc toàn bộ `@Test` bằng `@Transactional` rồi để Spring Test rollback khi kết thúc, callback `AFTER_COMMIT` cũng không chạy như mong đợi.

Test sau tạo một transaction thực, commit khi `TransactionTemplate` kết thúc, rồi dùng `Scenario` chờ bản ghi mà listener tạo. Giữ test method **không có `@Transactional`**:

```java
@ApplicationModuleTest // Đặt trong package module billing
class BillingConsumptionTests {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired InvoiceRepository invoices;

    @Test
    void committedOrderEventCreatesInvoice(Scenario scenario) {
        UUID id = UUID.randomUUID();
        BigDecimal total = new BigDecimal("125.00");

        scenario.stimulate(() -> publishCommitted(new OrderPlaced(id, total)))
                .andWaitForStateChange(() -> invoices.findByOrderId(id))
                .andVerify(found -> {
                    assertThat(found).isPresent();
                    Invoice invoice = found.orElseThrow();
                    assertThat(invoice.getOrderId()).isEqualTo(id);
                    assertThat(invoice.getAmount()).isEqualByComparingTo(total);
                });
    }

    private void publishCommitted(OrderPlaced event) {
        new TransactionTemplate(transactionManager)
                .executeWithoutResult(status -> publisher.publishEvent(event));
    }
}
```

Đây là assertion **trên tác dụng phụ của listener**, không chỉ trên số event đã phát. `Scenario` hỗ trợ đợi thay đổi trạng thái khi consumer bất đồng bộ; nếu listener bị gỡ hoặc không ghi hóa đơn, kiểm thử phải hết thời gian chờ và thất bại. Để tránh nhiễu giữa các test, dùng `orderId` mới, dữ liệu DB cách ly và cơ chế dọn dữ liệu rõ ràng.

## 6. Dùng `Thread.sleep` hoặc assert quá sớm với listener bất đồng bộ

Với `@ApplicationModuleListener`, `assertThat(invoices.findByOrderId(id)).isPresent()` ngay sau `publishCommitted(...)` có thể chạy trước listener; `Thread.sleep(200)` lại phụ thuộc tốc độ máy CI. Thay vì chờ một khoảng thời gian đoán trước, chờ **điều kiện quan sát được** bằng `Scenario.andWaitForStateChange(...)` như mục 5.

Nếu `billing` còn phát một sự kiện công khai `InvoiceCreated(UUID orderId)` sau khi lưu thành công, có thể chờ **đúng event đầu ra**:

```java
scenario.stimulate(() -> publishCommitted(new OrderPlaced(id, total)))
        .andWaitForEventOfType(InvoiceCreated.class)
        .matching(InvoiceCreated::orderId, id)
        .toArrive();
```

Ví dụ này chỉ áp dụng khi ứng dụng thật có phát `InvoiceCreated`; event đầu ra không tự xuất hiện nhờ `Scenario`. Chờ `InvoiceCreated` chứng minh tín hiệu phát ra, còn xác nhận hóa đơn đã được lưu vẫn cần truy vấn repository. Đối với trường hợp **không** được phát event, assertion tức thời `isEmpty()` sau publisher cũng không chứng minh được listener sẽ không phát trễ.

## 7. Chỉ kiểm tra hóa đơn tồn tại mà bỏ qua payload sai

`assertThat(invoices.findByOrderId(id)).isPresent()` vẫn xanh nếu listener gán sai `amount`, tạo hóa đơn cho ID khác ở một kho lưu không ràng buộc, hoặc điền thiếu trường bắt buộc. Với dữ liệu ví dụ `125.00`, kiểm tra đầy đủ hợp đồng:

```java
Invoice invoice = invoices.findByOrderId(id).orElseThrow();

assertThat(invoice.getOrderId()).isEqualTo(id);
assertThat(invoice.getAmount())
        .as("Số tiền trên hóa đơn phải lấy từ OrderPlaced")
        .isEqualByComparingTo(new BigDecimal("125.00"));
assertThat(invoices.countByOrderId(id)).isEqualTo(1L);
```

Trong integration test bất đồng bộ, thực hiện các assertion này **sau khi** `Scenario` xác nhận state đã thay đổi, tránh đọc DB trước khi consumer xong. Muốn đánh giá chất lượng, cố ý sửa listener truyền `BigDecimal.ZERO` thay vì `event.total()`; test phải đỏ ở assertion số tiền.

## 8. Không kiểm tra event phát lại và tính idempotent của listener

Sự kiện có thể được gửi lại trong cơ chế retry/republication; listener tạo hóa đơn lần hai sẽ gây dữ liệu trùng. Với hợp đồng `createIfAbsent`, kiểm thử business operation đồng bộ để xác nhận idempotency, sau đó kiểm chứng một event thật qua `Scenario`:

```java
@Test
void duplicateHandlingDoesNotCreateDuplicateInvoices() {
    UUID id = UUID.randomUUID();
    BigDecimal total = new BigDecimal("125.00");

    invoiceService.createIfAbsent(id, total);
    invoiceService.createIfAbsent(id, total);

    assertThat(invoices.countByOrderId(id)).isEqualTo(1L);
}
```

Test trên chỉ xác nhận nghiệp vụ `createIfAbsent`, chưa chứng minh hai lần phát event bất đồng bộ đã xử lý xong. Để kiểm tra nhiều event thật, cần cơ chế quan sát **cả hai lượt xử lý** trước khi đếm (ví dụ tín hiệu hoàn thành do ứng dụng cung cấp). Nếu có xử lý song song, thêm unique constraint cho `order_id` và bài kiểm thử cạnh tranh: mẫu `exists → insert` đơn thuần không ngăn hai thread cùng chèn.

## 9. Listener lỗi nhưng publisher vẫn xanh; quality gate bỏ sót hồi quy

Với listener bất đồng bộ, lỗi xử lý thường không được ném ngược về chỗ gọi `publishEvent`. Vì vậy, test chỉ assert publisher hoàn tất mà không exception sẽ bỏ sót cả lỗi DB. Ở mức unit, có thể kiểm tra listener **không nuốt** lỗi từ nghiệp vụ:

```java
@Test
void propagatesInvoiceCreationFailure() {
    InvoiceService service = mock(InvoiceService.class);
    UUID id = UUID.randomUUID();
    BigDecimal total = new BigDecimal("125.00");
    doThrow(new IllegalStateException("DB unavailable"))
            .when(service).createIfAbsent(id, total);

    assertThatThrownBy(() ->
            new InvoiceOnOrderPlaced(service).on(new OrderPlaced(id, total)))
            .isInstanceOf(IllegalStateException.class);
}
```

Vì đây là lời gọi trực tiếp, test không nói gì về retry của hệ thống event. Nếu dự án bật **Spring Modulith Event Publication Registry**, cần integration test riêng để kiểm tra publication chưa hoàn tất sau lỗi và được đánh dấu hoàn tất sau khi retry thành công, dựa trên loại registry/persistence đã cấu hình. Không mặc định mọi cấu hình đều tự retry.

Quality gate CI phải chạy test publisher **và** test consumer có assertion database, cộng test kiến trúc:

```java
@Test
void moduleDependenciesAreValid() {
    ApplicationModules.of(ShopApplication.class).verify();
}
```

`verify()` bắt lỗi phụ thuộc module, còn test ở mục 5 bắt listener bị mất hoặc ghi sai. Coverage cao ở publisher không bù được một trong hai.

## 10. Bài tập kiểm chứng: làm test đỏ đúng chỗ

Trên ứng dụng `ordering`–`billing` với JUnit 5, `@ApplicationModuleTest` và một database test độc lập, thực hiện theo thứ tự:

1. **Đường chuẩn:** chạy test `PublishedEvents` ở mục 2 và test `Scenario` ở mục 5 với một `orderId` mới. Xác nhận có đúng một hóa đơn, `orderId` và `amount` đều khớp event.
2. **Mất listener:** tạm bỏ `@ApplicationModuleListener` hoặc loại bean `InvoiceOnOrderPlaced` khỏi context `billing`. Test publisher vẫn có thể xanh; test consumer phải đỏ vì không quan sát được hóa đơn. Hoàn nguyên thay đổi.
3. **Sai payload:** sửa listener truyền `BigDecimal.ZERO` thay cho `event.total()`. Test consumer phải đỏ ở so sánh số tiền; chỉ test `isPresent()` sẽ bỏ lọt lỗi. Hoàn nguyên.
4. **Thiếu commit:** phát event trong transaction rollback thay vì commit. Giải thích vì sao callback `AFTER_COMMIT` không chạy. Không dùng `Thread.sleep` để kết luận event chắc chắn không được xử lý; kiểm tra transaction phase bằng một test được đồng bộ hóa phù hợp.
5. **Phát lại và lỗi xử lý:** gọi nghiệp vụ tạo hóa đơn hai lần và thử lỗi DB có kiểm soát. Xác nhận hóa đơn không trùng; nếu có registry sự kiện, ghi lại trạng thái publication thất bại và kết quả sau retry.

| Lỗi được cố ý tạo | Test cần phát hiện | Dấu hiệu đạt |
| --- | --- | --- |
| Xóa bean listener | `@ApplicationModuleTest` của `billing` + `Scenario` | Không có hóa đơn → test đỏ |
| Truyền sai `total` | Assertion payload trên `Invoice` | Giá trị không khớp → test đỏ |
| Tạo hai hóa đơn cùng `orderId` | Test idempotency/unique constraint | Count khác `1` → test đỏ |
| Thêm phụ thuộc module trái quy tắc | `ApplicationModules.verify()` | Test kiến trúc đỏ |

**Tiêu chí hoàn thành:** mỗi lần gọi publisher có test xác nhận event **và** ít nhất một test listener xác nhận hiệu ứng nghiệp vụ; test listener chạy trong context có subscriber, dùng transaction đã commit khi cần `AFTER_COMMIT`, chờ hành vi bất đồng bộ bằng điều kiện rõ ràng và kiểm tra dữ liệu thật. Đó mới là bằng chứng chống hồi quy ở ranh giới các module.
