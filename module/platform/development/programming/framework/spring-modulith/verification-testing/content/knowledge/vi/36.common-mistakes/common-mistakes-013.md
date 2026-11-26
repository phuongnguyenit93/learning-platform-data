# Chạy test green nhưng không có assertion thực sự

Trong module học **SPRING_MODULITH_VERIFICATION_TESTING**, mục tiêu không chỉ là khởi động được ứng dụng mà còn phải kiểm chứng hành vi, sự kiện và ranh giới giữa các module Spring Modulith. Một test hiện màu xanh (*green*) chỉ có nghĩa là JUnit không ghi nhận thất bại trong lượt chạy ấy; nếu test không thực thi phép kiểm chứng nào, kết quả xanh không chứng minh yêu cầu đã đúng.

Bài này thuộc nhóm **Lỗi thường gặp** và tập trung vào việc nhận diện, sửa và thực nghiệm với những test “xanh giả”. Ví dụ dùng Java 17+, JUnit 5, AssertJ, Mockito và Spring Modulith. Giả định ứng dụng `ShopApplication` có module `ordering`: `OrderService.confirm(UUID)`, `OrderRepository.findById(UUID)`, `OrderStatus.CONFIRMED` và event công khai `OrderConfirmed(UUID orderId, String sku, int quantity)`. Module `inventory` nhận event để ghi `Reservation`; `ReservationRepository.findByOrderId(UUID)` trả `Optional<Reservation>`, entity có `getQuantity()`. Hàm fixture `givenDraftOrder()` tạo đơn nháp và trả ID. **Các API nghiệp vụ là giả định của ví dụ**, các đoạn code cần đặt vào lớp test tương ứng và bổ sung import; không mặc định chúng có sẵn trong Spring Modulith.

## 1. Test chỉ gọi method, không kiểm tra hậu điều kiện

Test sau chạy qua toàn bộ `confirm`, nhưng vẫn có thể xanh nếu phương thức không thay đổi trạng thái:

```java
@Test
void confirmsOrder_butDoesNotAssertAnything() {
    UUID id = givenDraftOrder();
    orders.confirm(id);
}
```

Chuyển yêu cầu nghiệp vụ thành phép kiểm chứng quan sát được:

```java
@Test
void confirmsOrder() {
    UUID id = givenDraftOrder();

    orders.confirm(id);

    Order saved = repository.findById(id).orElseThrow();
    assertThat(saved.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
}
```

**Tự kiểm chứng:** thay tạm phần triển khai `confirm` thành no-op. Bản test đầu vẫn có thể xanh; bản thứ hai phải đỏ. Phải hoàn nguyên mã sản phẩm sau thí nghiệm.

## 2. Viết `assertThat(...)` nhưng quên gọi phép so sánh kết thúc

Đoạn sau tạo một đối tượng assertion nhưng không yêu cầu nó kiểm tra điều kiện nào:

```java
// Sai: hai câu lệnh dưới không xác định điều kiện pass/fail.
assertThat(saved.getStatus());
assertThat(saved.getTotal());
```

Phải nối với thao tác xác nhận như `isEqualTo`, `isPositive`, `contains` hoặc `satisfies`:

```java
assertThat(saved.getStatus())
        .as("Đơn hàng phải được xác nhận")
        .isEqualTo(OrderStatus.CONFIRMED);
assertThat(saved.getTotal()).isPositive();
```

Đừng đếm số lần xuất hiện của từ `assertThat` để đo hiệu lực. Quan sát xem assertion thật sự so sánh gì, và làm phép đổi giá trị mong đợi để chắc chắn test thất bại đúng chỗ.

## 3. Assertion nằm trong nhánh không được chạy

Khi `findById` trả `Optional.empty()`, đoạn code sau bỏ qua luôn assertion:

```java
@Test
void checksStatusOnlyIfOrderExists() {
    repository.findById(id).ifPresent(order ->
            assertThat(order.getStatus()).isEqualTo(OrderStatus.CONFIRMED));
}
```

Đây là **vacuous pass**: test xanh khi dữ liệu cần kiểm tra không tồn tại. Nếu sự tồn tại là một phần của hợp đồng, buộc test thất bại khi vắng dữ liệu:

```java
Order order = repository.findById(id)
        .orElseThrow(() -> new AssertionError("Không tìm thấy đơn hàng " + id));
assertThat(order.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
```

Tương tự, tránh viết `if (events.stream().findFirst().isPresent()) { assert... }` khi event phải tồn tại. Với tập dữ liệu, dùng `singleElement()`, `hasSize(1)` hay assertion trên nội dung thay vì lặng lẽ bỏ qua khi rỗng.

## 4. `try/catch` nuốt lỗi hoặc không xác minh exception mong đợi

Một test cố bắt exception nhưng không thất bại nếu phương thức **không hề ném**:

```java
@Test
void shouldRejectMissingOrder_butCanPassWithoutException() {
    try {
        orders.confirm(UUID.randomUUID());
    } catch (OrderNotFoundException ignored) {
        // Không có assertion; nhánh không ném lỗi cũng xanh.
    }
}
```

Kiểm tra đúng kiểu lỗi bằng JUnit:

```java
@Test
void rejectsMissingOrder() {
    UUID missingId = UUID.randomUUID();

    assertThrows(OrderNotFoundException.class,
            () -> orders.confirm(missingId));
}
```

Nếu hợp đồng còn quy định trạng thái database phải giữ nguyên, bổ sung assertion về số bản ghi hoặc trạng thái trước/sau khi gọi. `assertDoesNotThrow` cũng là phép kiểm chứng hợp lệ, nhưng chỉ phù hợp khi hợp đồng thật sự là “không ném exception”.

## 5. Mockito đã được stub, nhưng chưa có tương tác nào được kiểm chứng

`when(...).thenReturn(...)` chỉ dựng dữ liệu trả về; việc stub không tự biến một test thành phép kiểm tra. Test dưới đây có thể xanh dù `orders.confirm` quên phát event:

```java
when(repository.findById(id)).thenReturn(Optional.of(draftOrder));
orders.confirm(id); // Thiếu xác minh tương tác và kết quả.
```

Nếu hợp đồng yêu cầu phát **đúng một** `OrderConfirmed`, xác minh cả lời gọi lẫn payload:

```java
ArgumentCaptor<Object> eventCaptor = ArgumentCaptor.forClass(Object.class);

orders.confirm(id);

verify(publisher, times(1)).publishEvent(eventCaptor.capture());
assertThat(eventCaptor.getValue())
        .isInstanceOfSatisfying(OrderConfirmed.class, event -> {
            assertThat(event.orderId()).isEqualTo(id);
            assertThat(event.sku()).isEqualTo("BOOK-01");
            assertThat(event.quantity()).isEqualTo(2);
        });
```

Ví dụ này giả định `draftOrder` chứa `sku="BOOK-01"`, `quantity=2` và publisher được inject vào service. `Mockito.verify(...)` **là một phép kiểm chứng thực sự**: nó làm test thất bại nếu tương tác mong đợi không xảy ra. Tuy nhiên, verify trên mock chưa chứng minh listener thật đã xử lý hoặc dữ liệu được lưu.

## 6. Context `@ApplicationModuleTest` khởi động thành công nên tưởng nghiệp vụ đúng

```java
@ApplicationModuleTest
class OrderingModuleTests {
    @Test
    void contextLoads() { }
}
```

Test này có ích như một *smoke test* khi mục tiêu là nạp context, nhưng không xác minh `confirm`, repository hay event. Hãy đặt bài kiểm tra hành vi cạnh smoke test:

```java
@ApplicationModuleTest
class OrderingBehaviorTests {
    @Autowired OrderService orders;
    @Autowired OrderRepository repository;

    @Test
    void confirmationPersistsCorrectStatus() {
        UUID id = givenDraftOrder();
        orders.confirm(id);

        assertThat(repository.findById(id).orElseThrow().getStatus())
                .isEqualTo(OrderStatus.CONFIRMED);
    }
}
```

Để xác minh **ranh giới kiến trúc**, JUnit cần có test chạy `ApplicationModules.verify()`:

```java
@Test
void verifiesModuleBoundaries() {
    ApplicationModules.of(ShopApplication.class).verify();
}
```

`verify()` có thể ném exception khi phụ thuộc module vi phạm quy tắc; vì vậy test này **có oracle pass/fail dù không dùng `assertThat`**. Đừng tự động kết luận một test thiếu assertion chỉ vì không có lời gọi `Assertions.assert*`.

## 7. Có `PublishedEvents`, nhưng chỉ lấy ra rồi bỏ đó

Spring Modulith cho phép dùng `PublishedEvents` để quan sát event phát trong test:

```java
@Test
void collectsEventsWithoutCheckingThem(PublishedEvents events) {
    orders.confirm(id);
    events.ofType(OrderConfirmed.class); // Chỉ truy vấn; không assert.
}
```

Phiên bản có assertion kiểm tra đúng số lượng và dữ liệu event:

```java
@Test
void publishesExpectedConfirmation(PublishedEvents events) {
    UUID id = givenDraftOrder();

    orders.confirm(id);

    assertThat(events.ofType(OrderConfirmed.class))
            .singleElement()
            .satisfies(event -> {
                assertThat(event.orderId()).isEqualTo(id);
                assertThat(event.sku()).isEqualTo("BOOK-01");
                assertThat(event.quantity()).isEqualTo(2);
            });
}
```

Fixture ở đây phải chuẩn bị đơn có SKU và số lượng khớp giá trị mong đợi. Test trên chứng minh publisher đã phát event; nó **không chứng minh** module `inventory` đã nhận và lưu reservation. Cần thêm test tích hợp consumer ở mục tiếp theo.

## 8. Listener bất đồng bộ có assertion, nhưng test kết thúc trước khi kiểm tra

Một assertion chạy trong công việc bất đồng bộ mà JUnit không chờ có thể thất bại sau khi test đã được báo xanh:

```java
@Test
void assertionsRunAfterTestHasReturned() {
    CompletableFuture.runAsync(() ->
            assertThat(reservations.countByOrderId(id)).isEqualTo(1L));
    // Không join/get; JUnit chỉ thấy test method kết thúc bình thường.
}
```

Với tác vụ do chính test tạo, phải đợi `future.get(timeout, unit)` hoặc `join()` để lỗi trong future được truyền về test. Với `@ApplicationModuleListener` xử lý event theo phase `AFTER_COMMIT`, nên quan sát **tác dụng phụ thật** bằng `Scenario`. Ví dụ đặt test trong package module `inventory` để bean listener và repository thuộc module này được nạp:

```java
@ApplicationModuleTest
class InventoryEventTests {
    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager txManager;
    @Autowired ReservationRepository reservations;

    @Test // Không gắn @Transactional gây rollback tự động.
    void confirmedOrderEventuallyCreatesReservation(Scenario scenario) {
        UUID id = UUID.randomUUID();
        OrderConfirmed event = new OrderConfirmed(id, "BOOK-01", 2);

        scenario.stimulate(() ->
                    new TransactionTemplate(txManager).executeWithoutResult(
                            status -> publisher.publishEvent(event)))
                .andWaitForStateChange(() -> reservations.findByOrderId(id))
                .andVerify(result -> {
                    Reservation saved = result.orElseThrow();
                    assertThat(saved.getQuantity()).isEqualTo(2);
                });
    }
}
```

Test cần listener thật đã đăng ký và database test độc lập. Transaction được commit khi `TransactionTemplate` hoàn tất để listener `AFTER_COMMIT` có cơ hội chạy. Nếu listener không tạo reservation, `Scenario` không thấy trạng thái mong đợi và test phải thất bại. `Scenario` có bước đợi **và bước xác minh**; chỉ tạo một publisher/lambda chưa đủ.

## 9. Test bị `@Disabled`, bị bỏ qua hoặc không được CI tìm thấy

Một job build có thể màu xanh ngay cả khi test mục tiêu không chạy. Những dấu hiệu cần rà soát:

- `@Disabled` hoặc `Assumptions.assumeTrue(false)` khiến test bị bỏ qua; kết quả có thể là **skipped/aborted**, không phải passed.
- Tên lớp test và cấu hình JUnit 5/Surefire/Failsafe không khớp nên không discover test.
- CI chạy `package -DskipTests`, `-Dmaven.test.skip=true` hoặc filter không chọn test tích hợp.
- Test kiến trúc `ApplicationModules.of(ShopApplication.class).verify()` chỉ nằm trong file chưa được runner thực thi.

Với Maven, có thể cấu hình Surefire để build thất bại khi không tìm thấy test của phase unit:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
```

Chạy `./mvnw -B verify` trong CI, cấu hình Failsafe nếu test tích hợp theo pattern `*IT`, và đọc số **run / failures / errors / skipped** từ báo cáo test. `failIfNoTests` của Surefire không thay thế việc xác nhận tập test tích hợp và test kiến trúc đã được discover đúng. Một job xanh với 0 test không đáp ứng quality gate kiểm chứng.

## 10. Checklist chống “green giả” trước khi chấp nhận PR

Dùng checklist này khi review một test `@ApplicationModuleTest`, test repository, event hoặc CI:

- [ ] Có một hành vi/hợp đồng được nêu rõ: đầu vào nào phải dẫn đến kết quả nào?
- [ ] Test thực thi hành vi thật; mọi fixture và giả định đầu vào đều được chuẩn bị.
- [ ] Có **oracle pass/fail**: `assertThat(...).isEqualTo(...)`, `assertThrows`, `verify(mock)`, `ApplicationModules.verify()` hoặc cơ chế tương đương ném lỗi khi sai.
- [ ] Oracle không nằm sau `ifPresent`, `if`, `return` hay nhánh có thể bỏ qua im lặng.
- [ ] Các assertion tạo trong lambda/future/event listener được test **đợi hoàn tất** và phản ánh thất bại về JUnit.
- [ ] Test sự kiện đối chiếu loại, số lượng và payload; test subscriber khẳng định kết quả thực tại module nhận.
- [ ] Với `@TransactionalEventListener`, event được phát trong transaction phù hợp và commit nếu hợp đồng yêu cầu `AFTER_COMMIT`.
- [ ] Test DB đọc lại dữ liệu cần kiểm chứng và không dựa vào mock để khẳng định persistence.
- [ ] CI thực sự discover và chạy các lớp test tương ứng; báo cáo không có tình trạng 0 test ngoài ý muốn.
- [ ] Cố ý làm sai một đầu ra quan trọng thì ít nhất một test liên quan phải **đỏ**.

**Bài tập 15–20 phút:** lấy ba test đang xanh trong dự án, lần lượt (1) bỏ cập nhật trạng thái trong `confirm`; (2) xóa lời gọi `publishEvent`; (3) vô hiệu hóa listener tạo reservation. Với mỗi thay đổi, ghi lại **test nào đỏ, assertion nào phát hiện lỗi**. Nếu không có test đỏ, bổ sung oracle: kiểm tra trạng thái đơn hàng, `PublishedEvents` với payload, hoặc `Scenario` và bản ghi reservation. Hoàn nguyên từng thay đổi trước khi chuyển sang bước tiếp theo.

| Lỗi cố ý | Test cần đỏ | Bằng chứng cần quan sát |
| --- | --- | --- |
| `confirm` không cập nhật trạng thái | `confirmsOrder` | Trạng thái khác `CONFIRMED` |
| Không phát `OrderConfirmed` | `publishesExpectedConfirmation` | Không có đúng một event với payload chuẩn |
| Listener không ghi reservation | `confirmedOrderEventuallyCreatesReservation` | Không thấy reservation hợp lệ trong thời gian chờ |
| Thêm phụ thuộc module sai quy tắc | `verifiesModuleBoundaries` | `verify()` báo vi phạm |

**Đầu ra đạt yêu cầu:** mỗi test xanh được giải thích bằng một kết quả đã kiểm chứng, lỗi được cài có chủ đích làm test thất bại, và báo cáo CI xác nhận các test thật sự chạy. Khi đó chữ “green” mới là bằng chứng có thể tin cậy để chặn hồi quy trong Spring Modulith.
