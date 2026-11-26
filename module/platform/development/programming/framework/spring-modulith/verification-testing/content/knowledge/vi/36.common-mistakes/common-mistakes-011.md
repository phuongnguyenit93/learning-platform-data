# Đo coverage mà không xem chất lượng assertion

**Lỗi cốt lõi:** line coverage và branch coverage chỉ cho biết mã đã được chạy qua, không cho biết kiểm thử có phát hiện kết quả sai hay không. Trong ứng dụng Spring Modulith, một bộ test có coverage cao vẫn có thể bỏ lọt lỗi nghiệp vụ, sự kiện sai payload, dữ liệu chưa được lưu hoặc phụ thuộc xuyên ranh giới module.

Các ví dụ dưới đây dùng JUnit 5, AssertJ và Spring Modulith. Giả định ứng dụng mẫu có `ShopApplication`, module `orders` với `OrderService.complete(UUID)`, `OrderRepository`, `OrderStatus` (`NEW`, `COMPLETED`), ngoại lệ `OrderNotFoundException` và sự kiện record `OrderCompleted(UUID orderId)`. Hàm fixture `givenPendingOrder()` tạo và trả về ID đơn hàng ở trạng thái `NEW`. Đây là tên miền minh họa; thay bằng API thật của dự án khi áp dụng.

## 1. Gọi phương thức rồi coi test xanh là đúng

Test chỉ gọi `orders.complete(id)` sẽ tăng coverage dù phương thức không cập nhật trạng thái. Cần khẳng định **kết quả nghiệp vụ quan sát được**, không chỉ khẳng định không có exception.

```java
@Test
void completingOrderChangesItsStatus() {
    UUID id = givenPendingOrder();

    orders.complete(id);

    assertThat(repository.findById(id).orElseThrow().getStatus())
            .isEqualTo(OrderStatus.COMPLETED);
}
```

Nếu sửa `complete` thành hàm không làm gì, assertion phải thất bại; đó là tín hiệu test có giá trị hơn số dòng được chạy.

## 2. Assertion quá yếu: `notNull`, `isPresent` hoặc `isNotEmpty`

`assertThat(order).isNotNull()` vẫn qua khi trạng thái đơn hàng sai. `isPresent()` chỉ xác nhận bản ghi tồn tại. Assertion nên kiểm tra giá trị chính xác theo hợp đồng nghiệp vụ.

```java
Order actual = repository.findById(id).orElseThrow();

assertThat(actual.getStatus())
        .as("Đơn hàng phải hoàn tất sau complete")
        .isEqualTo(OrderStatus.COMPLETED);
```

Nếu có nhiều đầu ra quan trọng, kiểm tra từng đầu ra: trạng thái, tổng tiền và ID chủ thể. Tránh assertion phụ thuộc vào chi tiết nội bộ không phải hợp đồng.

## 3. Kiểm tra entity còn trong bộ nhớ rồi tưởng đã kiểm tra database

Trong bài kiểm thử JPA, đọc lại cùng entity từ persistence context có thể che lỗi chưa lưu. Với `@ApplicationModuleTest` có JPA, dùng `flush()` và `clear()` trước khi truy vấn lại; test phải chạy trong transaction.

```java
@ApplicationModuleTest
class OrderPersistenceTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;
    @PersistenceContext EntityManager entityManager;

    @Test
    @Transactional
    void completionIsPersisted() {
        UUID id = givenPendingOrder();

        orders.complete(id);
        entityManager.flush();
        entityManager.clear();

        assertThat(repository.findById(id).orElseThrow().getStatus())
                .isEqualTo(OrderStatus.COMPLETED);
    }
}
```

`flush()` kiểm tra lệnh ghi đã được gửi đến database trong transaction; `clear()` buộc lần đọc sau không lấy lại đối tượng đang được quản lý. Test này **chưa** chứng minh commit đã thành công: nếu cần kiểm tra hành vi sau commit, thiết kế riêng một integration test có ranh giới transaction phù hợp.

## 4. Chỉ assert đường đi thành công, bỏ qua trường hợp thất bại

Coverage cao của nhánh thành công không đảm bảo lời gọi với ID không tồn tại xử lý đúng. Hãy kiểm tra cả exception và việc **không phát ra sự kiện thành công**.

```java
@Test
void missingOrderDoesNotPublishCompletion(PublishedEvents events) {
    UUID missingId = UUID.randomUUID();

    assertThatThrownBy(() -> orders.complete(missingId))
            .isInstanceOf(OrderNotFoundException.class);
    assertThat(events.ofType(OrderCompleted.class)).isEmpty();
}
```

Với test module, `PublishedEvents` ghi nhận các sự kiện Spring được phát trong phạm vi test. Điều kiện này bảo vệ cả nhánh lỗi lẫn tác dụng phụ.

## 5. Có branch coverage nhưng thiếu dữ liệu ở ranh giới

Hai nhánh `true/false` có thể đã được chạy nhưng vẫn lọt lỗi đổi `>=` thành `>`. Với chính sách đơn hàng tối thiểu hai sản phẩm, cần kiểm tra ngay trước, đúng tại và ngay sau ngưỡng.

```java
@ParameterizedTest
@CsvSource({
    "1, false",
    "2, true",
    "3, true"
})
void minimumItemCountIsInclusive(int count, boolean expected) {
    assertThat(orderPolicy.canPlaceOrder(count)).isEqualTo(expected);
}
```

Nếu đổi điều kiện từ `count >= 2` thành `count > 2`, trường hợp `count = 2` phải đỏ. Một assertion sát biên có thể bắt lỗi mà cùng tỷ lệ branch coverage không phát hiện.

## 6. Lấy `verify(mock)` thay cho kiểm tra kết quả thực tế

Trong unit test, `verify(repository).save(any())` chỉ nói rằng `save` được gọi, dù entity được truyền vào có trạng thái sai. Ít nhất cần xác minh đối số mang ý nghĩa nghiệp vụ:

```java
verify(repository).save(argThat(order ->
        order.getStatus() == OrderStatus.COMPLETED));
```

Mockito verification vẫn có ích để kiểm tra tương tác, nhưng không chứng minh bản ghi đã lưu hoặc các module đã tích hợp đúng. Bổ sung test `@ApplicationModuleTest` với repository thật và assertion đọc lại database như mục 3 cho đường đi quan trọng.

## 7. Chỉ đếm sự kiện mà không kiểm tra nội dung

`assertThat(events.ofType(OrderCompleted.class)).isNotEmpty()` có thể qua khi sự kiện mang ID của đơn hàng khác, hoặc phát lặp. Kiểm tra **đúng một** sự kiện và **đúng ID**:

```java
@Test
void publishesExactlyOneMatchingCompletion(PublishedEvents events) {
    UUID id = givenPendingOrder();

    orders.complete(id);

    assertThat(events.ofType(OrderCompleted.class))
            .singleElement()
            .extracting(OrderCompleted::orderId)
            .isEqualTo(id);
}
```

Đây là assertion trên hợp đồng sự kiện giữa các module, không chỉ trên việc một nhánh có `publishEvent(...)` đã chạy.

## 8. Assert sự kiện bất đồng bộ ngay lập tức

Với xử lý bất đồng bộ, assert ngay sau lệnh gọi hoặc `Thread.sleep(100)` dễ gây test lúc xanh lúc đỏ. Spring Modulith cung cấp `Scenario` để kích hoạt hành vi và chờ sự kiện thỏa điều kiện:

```java
@Test
void eventuallyPublishesCompletion(Scenario scenario) {
    UUID id = givenPendingOrder();

    scenario.stimulate(() -> orders.complete(id))
            .andWaitForEventOfType(OrderCompleted.class)
            .matching(event -> id.equals(event.orderId()))
            .toArrive();
}
```

Nếu listener dùng `@TransactionalEventListener` tại `AFTER_COMMIT`, phải cấu hình stimulus chạy qua transaction được commit; test transaction bị rollback sẽ không kích hoạt phase này. Chờ đúng sự kiện và điều kiện mới kiểm chứng được hành vi.

## 9. Chạy `@ApplicationModuleTest` rồi mặc định kiến trúc hợp lệ

`@ApplicationModuleTest` kiểm tra hành vi trong phạm vi module được bootstrap; việc context khởi động thành công **không thay thế** xác minh quy tắc phụ thuộc module. Thêm test kiến trúc vào bộ JUnit:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithArchitectureTests {

    @Test
    void modulesRespectDeclaredBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` ném lỗi khi vi phạm ranh giới hoặc các quy tắc phụ thuộc áp dụng; vì vậy JUnit sẽ đánh dấu test thất bại dù không có `assertThat`. Coverage của service không đo được loại lỗi kiến trúc này.

## 10. Quality gate chỉ nhìn phần trăm coverage

Quy định “coverage >= 80%” có thể đạt được bằng những test yếu ở các mục trên. Trong CI, cần chạy cả bộ JUnit chứa assertion nghiệp vụ, test sự kiện, test database và `ApplicationModules.verify()`; ngưỡng coverage chỉ là một tín hiệu bổ sung. Ví dụ job Maven chạy `./mvnw -B verify` khi project đã cấu hình test và plugin đo coverage trong lifecycle.

Đánh giá chất lượng assertion bằng phép thử có chủ đích: đổi tạm `>=` thành `>` ở mục 5, đổi trạng thái `COMPLETED` thành `NEW` hoặc phát sự kiện sai ID; test liên quan **phải đỏ**. Mutation testing có thể tự động hóa phép kiểm này. Nếu thay đổi sai vẫn khiến CI xanh, hãy cải thiện assertion và dữ liệu kiểm thử trước khi nâng ngưỡng coverage.

**Dấu hiệu đạt:** mỗi test quan trọng nêu rõ điều kiện đầu vào, kết quả mong đợi và assertion cụ thể; nhánh lỗi không gây tác dụng phụ; sự kiện được đối chiếu bằng payload; dữ liệu được xác nhận ở lớp lưu trữ; ranh giới module được kiểm tra độc lập. Khi đó coverage cho biết mức độ bao phủ của một bộ kiểm thử thực sự có khả năng phát hiện hồi quy.
