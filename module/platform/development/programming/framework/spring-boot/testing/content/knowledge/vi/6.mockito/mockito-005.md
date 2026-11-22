# ArgumentCaptor để kiểm tra dữ liệu gửi đến phụ thuộc trong kiểm thử Spring Boot

## 1. Vấn đề cần giải quyết: kết quả trả về đúng chưa đủ

Trong một ứng dụng Spring Boot, service thường gọi các thành phần khác: repository lưu dữ liệu, client gửi HTTP, publisher phát sự kiện, hoặc adapter gửi email. Một phương thức có thể **không trả về dữ liệu cần kiểm chứng** nhưng vẫn truyền một object quan trọng sang phụ thuộc.

Ví dụ, `OrderService.placeOrder(...)` tạo mã đơn hàng rồi gọi `EventPublisher.publish(event)`. Test chỉ kiểm tra phương thức `placeOrder` trả về UUID là chưa đủ: service vẫn có thể gửi email sai, bỏ mất SKU, gửi sự kiện hai lần hoặc không gửi gì. Ta cần quan sát **argument thực tế được truyền tại ranh giới gọi phụ thuộc**.

Mockito cung cấp `ArgumentCaptor<T>` để lấy argument đó từ một lời gọi đã được mock ghi nhận, từ đó dùng JUnit hoặc AssertJ kiểm tra nội dung chi tiết. Mô hình thường gặp là:

```java
verify(publisher).publish(eventCaptor.capture());
OrderPlacedEvent event = eventCaptor.getValue();
assertEquals(expectedEmail, event.buyerEmail());
```

Ý nghĩa:
- `verify(publisher)` kiểm tra phương thức mong đợi thực sự được gọi; mặc định là **đúng một lần**.
- `eventCaptor.capture()` đăng ký matcher để lấy đối số trong lời gọi đang được xác minh.
- `getValue()` trả về đối số được bắt; các assertion sau đó kiểm tra các thuộc tính mà nghiệp vụ yêu cầu.

**Điểm quan trọng:** `ArgumentCaptor` không tự kiểm tra tính đúng đắn của dữ liệu và không tự khẳng định lời gọi xảy ra. Độ tin cậy đến từ **verification cộng với assertion cụ thể**. Captor cũng chỉ thấy lời gọi lên mock được cấu hình, không chứng minh phụ thuộc thật đã lưu database hay gửi message thành công.

## 2. Khi nào nên dùng ArgumentCaptor?

Sử dụng captor khi dữ liệu đi qua mock không thể được so sánh dễ dàng bằng một giá trị literal, hoặc ta cần kiểm tra nhiều trường của object:

- Service tạo UUID, thời gian, correlation ID, số tiền hoặc các field được tính toán rồi gửi DTO cho repository/message publisher.
- Một adapter biến request đầu vào thành command/event khác; test cần kiểm tra mapping chính xác.
- Phụ thuộc trả `void`, vì vậy kết quả có thể quan sát chủ yếu là lời gọi và dữ liệu gửi đi.
- Có nhiều lời gọi cùng một phương thức, cần kiểm tra từng argument và thứ tự phát sinh.
- Cần chứng minh các giá trị quan trọng của một object phức tạp mà không muốn ràng buộc test vào những trường không thuộc hợp đồng.

Không nhất thiết dùng captor cho mọi lời gọi. Nếu toàn bộ argument đã biết và có `equals` đúng nghĩa, cách này rõ ràng hơn:

```java
verify(publisher).publish(expectedEvent);
```

Nếu chỉ kiểm tra một điều kiện đơn giản ngay tại lời gọi, `argThat` cũng gọn:

```java
verify(publisher).publish(argThat(event ->
        event != null && event.buyerEmail().equals("buyer@example.test")));
```

Hai đoạn trên là **minh họa bên trong test có sẵn `publisher` và imports Mockito tương ứng**, không phải chương trình Java độc lập. Hãy chọn captor khi muốn **đọc rõ toàn bộ object đã truyền**, có nhiều assertion hoặc cần đối chiếu với giá trị được tạo trong lúc thực thi.

## 3. Cơ chế: mock ghi nhận lời gọi, verify chọn lời gọi, captor lấy đối số

Một quy trình kiểm thử gồm bốn bước:

1. **Tạo mock** của phụ thuộc và cung cấp mock đó cho đối tượng thật đang kiểm thử (SUT – system under test). Với unit test, khởi tạo service qua constructor thường đủ.
2. **Gọi hành vi** trên service thật: `service.placeOrder(...)`. Mockito ghi nhận lời gọi `publisher.publish(...)` đi vào mock.
3. **Xác minh lời gọi với captor**: `verify(publisher, times(1)).publish(captor.capture())`. Nếu không có lời gọi mong đợi, bước này thất bại; không được tiếp tục kết luận đã có đối số.
4. **Lấy dữ liệu và assert**: `captor.getValue()`, `assertEquals`, `assertAll`, `containsExactly`... để kiểm tra dữ liệu đã gửi.

Có hai cách khai báo phổ biến:

```java
// Cách 1: khai báo trực tiếp trong một test method.
ArgumentCaptor<OrderPlacedEvent> captor =
        ArgumentCaptor.forClass(OrderPlacedEvent.class);

// Cách 2: dùng MockitoExtension hoặc mở mock annotation trước test.
@Captor
ArgumentCaptor<OrderPlacedEvent> eventCaptor;
```

Với `@Captor`, cần cơ chế khởi tạo annotation của Mockito, chẳng hạn `@ExtendWith(MockitoExtension.class)` trong JUnit Jupiter. Nếu thiếu khởi tạo, trường có thể `null` và test sẽ thất bại trước khi kiểm tra dữ liệu. Với generic như `ArgumentCaptor<List<String>>`, `@Captor` còn giúp tránh các cast raw type không cần thiết.

Thông thường dùng `capture()` trong **`verify(...)` sau khi thực hiện hành vi**, không đặt captor trong phần `when(...)` để dò dữ liệu. Mockito khuyến nghị captor cho verification; khi dùng nó để thiết lập stubbing, test có thể khó chẩn đoán hoặc lỗi do chưa có invocation.

## 4. Ví dụ Java 17+ hoàn chỉnh: bắt dữ liệu sự kiện đặt hàng

### 4.1. Hợp đồng cần bảo vệ

Một service nhận email và danh sách SKU, tạo UUID đơn hàng, sau đó gửi `OrderPlacedEvent` cho `EventPublisher`. Ta cần chứng minh:

1. Sự kiện được phát **đúng một lần** khi đặt đơn hợp lệ.
2. UUID trong sự kiện bằng UUID trả về cho người gọi.
3. Email gửi đi đã được trim, danh sách SKU giữ đúng thứ tự và phần tử.
4. Sự kiện lưu một **bản sao bất biến** của danh sách, nên sửa danh sách đầu vào sau đó không làm dữ liệu sự kiện thay đổi.
5. Hai đơn hợp lệ tạo **hai lời gọi**; có thể kiểm tra từng sự kiện theo thứ tự gọi.
6. Đầu vào không hợp lệ **không phát bất kỳ sự kiện nào**.

Các lớp dưới đây chạy trong dự án Java 17+ đã cấu hình JUnit Jupiter và Mockito (trong dự án Spring Boot, các thư viện này thường được cung cấp qua `spring-boot-starter-test`). Đây là unit test; không cần khởi động Spring context.

### 4.2. Record biểu diễn dữ liệu gửi đi

Tệp `src/main/java/com/example/testing/OrderPlacedEvent.java`:

```java
package com.example.testing;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record OrderPlacedEvent(
        UUID orderId,
        String buyerEmail,
        List<String> skuCodes) {

    public OrderPlacedEvent {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(buyerEmail, "buyerEmail");
        skuCodes = List.copyOf(skuCodes);
    }
}
```

Record Java 17 cung cấp `equals`/`hashCode` theo component. `List.copyOf` tạo dữ liệu không thể thay đổi qua collection API; nó cũng giữ thứ tự và số lần lặp. Đoạn code giả định `skuCodes` không chứa `null` và các SKU là `String` bất biến; `List.copyOf` ném `NullPointerException` nếu collection hoặc phần tử là `null`.

### 4.3. Phụ thuộc và service thật

Tệp `src/main/java/com/example/testing/EventPublisher.java`:

```java
package com.example.testing;

public interface EventPublisher {
    void publish(OrderPlacedEvent event);
}
```

Tệp `src/main/java/com/example/testing/OrderService.java`:

```java
package com.example.testing;

import java.util.List;
import java.util.UUID;

public final class OrderService {
    private final EventPublisher publisher;

    public OrderService(EventPublisher publisher) {
        this.publisher = publisher;
    }

    public UUID placeOrder(String buyerEmail, List<String> skuCodes) {
        if (buyerEmail == null || buyerEmail.isBlank()
                || skuCodes == null || skuCodes.isEmpty()) {
            throw new IllegalArgumentException("Invalid order input");
        }

        UUID orderId = UUID.randomUUID();
        OrderPlacedEvent event =
                new OrderPlacedEvent(orderId, buyerEmail.trim(), skuCodes);
        publisher.publish(event);
        return orderId;
    }
}
```

Service là mã Java thuần để bài test tập trung vào hành vi gọi phụ thuộc. Trong Spring Boot thực tế, có thể gắn `@Service` và inject `EventPublisher` qua constructor; cách Mockito xác minh lời gọi vẫn giữ nguyên. Ví dụ không triển khai broker hoặc repository thật, vì điều cần kiểm tra là **dữ liệu service chuyển cho phụ thuộc**.

### 4.4. Test dùng @Mock, @Captor và MockitoExtension

Tệp `src/test/java/com/example/testing/OrderServiceTest.java`:

```java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    EventPublisher publisher;

    @Captor
    ArgumentCaptor<OrderPlacedEvent> eventCaptor;

    @Test
    void publishesCorrectDataExactlyOnce() {
        OrderService service = new OrderService(publisher);
        List<String> inputSkus =
                new ArrayList<>(List.of("SKU-2", "SKU-1"));

        UUID returnedId = service.placeOrder(
                "  buyer@example.test  ", inputSkus);

        verify(publisher).publish(eventCaptor.capture());
        OrderPlacedEvent published = eventCaptor.getValue();

        assertAll("event data",
                () -> assertEquals(returnedId, published.orderId()),
                () -> assertEquals(
                        "buyer@example.test", published.buyerEmail()),
                () -> assertEquals(
                        List.of("SKU-2", "SKU-1"), published.skuCodes()));

        inputSkus.add("SKU-LATE");
        assertEquals(
                List.of("SKU-2", "SKU-1"), published.skuCodes());
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void capturesEveryPublishedEventInInvocationOrder() {
        OrderService service = new OrderService(publisher);

        UUID firstId = service.placeOrder(
                "first@example.test", List.of("A", "A"));
        UUID secondId = service.placeOrder(
                "second@example.test", List.of("B"));

        verify(publisher, times(2)).publish(eventCaptor.capture());

        List<OrderPlacedEvent> events = eventCaptor.getAllValues();
        assertEquals(2, events.size());
        assertEquals(firstId, events.get(0).orderId());
        assertEquals("first@example.test", events.get(0).buyerEmail());
        assertEquals(List.of("A", "A"), events.get(0).skuCodes());
        assertEquals(secondId, events.get(1).orderId());
        assertEquals("second@example.test", events.get(1).buyerEmail());
        assertEquals(List.of("B"), events.get(1).skuCodes());
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void rejectsInvalidOrderWithoutPublishing() {
        OrderService service = new OrderService(publisher);

        assertThrows(IllegalArgumentException.class,
                () -> service.placeOrder(" ", List.of("A")));
        assertThrows(IllegalArgumentException.class,
                () -> service.placeOrder(
                        "buyer@example.test", List.of()));

        verifyNoInteractions(publisher);
    }
}
```

**Vì sao các assertion này có ý nghĩa?**

- `verify(publisher).publish(...)` mặc định tương ứng `times(1)`. Nếu service không phát event hoặc phát hai lần, phép xác minh này không đạt.
- `getValue()` cho phép đọc một `OrderPlacedEvent` và kiểm tra **UUID động**, email sau chuẩn hóa và cả danh sách SKU. Chỉ `verify(publisher).publish(any())` sẽ không chứng minh các trường này đúng.
- Với hai lời gọi, `times(2)` xác minh số lần; `getAllValues()` trả các argument đã bắt theo thứ tự lời gọi khớp, nên có thể kiểm tra sự kiện thứ nhất và thứ hai riêng biệt.
- `verifyNoMoreInteractions` bổ sung rằng không có lời gọi chưa xác minh nào khác trên mock đó. Dùng có chọn lọc; kiểm tra quá chặt những tương tác phụ không thuộc hợp đồng có thể làm test giòn khi refactor.
- `verifyNoInteractions` xác nhận đầu vào sai không chạm tới publisher, không chỉ riêng việc chưa gọi một overload nào.
- `inputSkus.add(...)` kiểm tra hậu điều kiện liên quan đến **bản sao dữ liệu**, bởi record dùng `List.copyOf`. Đây không phải bằng chứng về broker thật.

Ba test trên được thiết kế để **đạt** với ba lớp production ở trên. Chúng không in `stdout` riêng; output của Gradle/Maven phụ thuộc runner. Chỉ kết luận chúng thật sự đạt trong dự án cụ thể sau khi chạy build và đọc report.

### 4.5. Chạy test trong dự án Spring Boot

Với Gradle wrapper trên Linux/macOS:

```bash
./gradlew test --tests "com.example.testing.OrderServiceTest"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.OrderServiceTest"
```

Với Maven wrapper trên Linux/macOS:

```bash
./mvnw -Dtest=OrderServiceTest test
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=OrderServiceTest test
```

Điều kiện: dự án đã có JUnit Jupiter, Mockito Core, Mockito JUnit Jupiter extension và runner khám phá Jupiter (Gradle thường cấu hình `useJUnitPlatform()`; Maven cần Surefire tương thích). Nếu không dùng Spring Boot starter, cần tự khai báo các dependency test đó. Không chạy riêng các file trên bằng `javac` thiếu classpath JUnit/Mockito; lệnh wrapper là cách thông thường khi bài nằm trong dự án.

## 5. getValue(), getAllValues() và số lần gọi

Với phương thức `publish(event)`, mỗi lần gọi có một argument. Các phép xác minh có ý nghĩa khác nhau:

| Nhu cầu | Cách dùng | Điều cần nhớ |
|---|---|---|
| Một lần gọi | `verify(publisher).publish(captor.capture())` | Mặc định đúng một lần |
| Hai lần gọi | `verify(publisher, times(2)).publish(captor.capture())` | Mọi lời gọi khớp được đưa vào captor |
| Lấy giá trị sau một lần bắt | `captor.getValue()` | Với nhiều giá trị đã bắt, thường là giá trị **cuối cùng** |
| Đọc toàn bộ các lần bắt | `captor.getAllValues()` | Danh sách giá trị theo thứ tự bắt, thuận tiện kiểm tra từng lần gọi |
| Không có tương tác nào | `verifyNoInteractions(publisher)` | Không gọi `getValue` khi không có gì được capture |

Nếu chỉ viết `verify(publisher).publish(captor.capture())` trong trường hợp có hai lời gọi, Mockito sẽ báo có quá nhiều invocation; phép xác minh không thay cho `times(2)`. Ngược lại, `getValue()` sau nhiều lần capture chỉ giúp kiểm tra giá trị cuối, **không chứng minh giá trị của các lần trước**.

Với phương thức có nhiều tham số:

```java
// Ví dụ minh họa trong test có mock:
// void send(String recipient, Notification payload)
ArgumentCaptor<String> toCaptor = ArgumentCaptor.forClass(String.class);
ArgumentCaptor<Notification> payloadCaptor =
        ArgumentCaptor.forClass(Notification.class);

verify(client).send(toCaptor.capture(), payloadCaptor.capture());
assertEquals("buyer@example.test", toCaptor.getValue());
// Tiếp tục assert các trường của payloadCaptor.getValue().
```

Đoạn này minh họa cú pháp cho interface `client` và kiểu `Notification` giả định, **không phải tệp Java độc lập**. Khi có nhiều lời gọi, cần xác minh đúng `times(n)` và kiểm tra tương quan giữa hai danh sách `getAllValues()` theo vị trí.

## 6. Một khác biệt dễ bị bỏ qua: captor giữ tham chiếu object

Mockito ghi lại **đối tượng được truyền vào**, không tự động chụp bản sao sâu của mọi field vào thời điểm lời gọi. Nếu SUT dùng một object mutable rồi thay đổi nó **sau khi gọi mock**, đến lúc test chạy `getValue()`, object đó có thể đã mang trạng thái mới.

Ví dụ mang tính cảnh báo:

```java
// Pseudocode trong một SUT, MutableMessage là kiểu cho phép sửa state:
MutableMessage message = new MutableMessage("QUEUED");
publisher.publish(message);
message.setStatus("SENT");
```

Nếu test dùng captor sau khi service hoàn tất, `captor.getValue().getStatus()` có thể là `"SENT"`, dù status **tại lúc gọi `publish`** là `"QUEUED"`. Vì captor giữ tham chiếu, test không được dùng trạng thái sau cùng để khẳng định chắc chắn trạng thái tại thời điểm tương tác.

Cách giảm rủi ro:
- Ưu tiên DTO/command/event **bất biến** (`record`, `List.copyOf`, defensive copy với dữ liệu mutable bên trong).
- Nếu bắt buộc gửi object mutable và cần kiểm tra **snapshot tại lời gọi**, dùng `doAnswer` để sao chép những field liên quan ngay trong lúc mock nhận lời gọi.
- Không sửa object captor trả về trong test, vì có thể làm thay đổi chính object mock đã nhận; tránh phụ thuộc side effect này.

`List.copyOf` chỉ sao chép cấu trúc danh sách, **không deep copy các phần tử mutable**. Với `List<MutableItem>`, nội dung của từng `MutableItem` vẫn có thể đổi; khi đó cần record phần tử bất biến hoặc copy sâu theo hợp đồng.

## 7. Captor và các matcher: chọn đúng mức kiểm tra

| Công cụ | Mục đích chính | Ví dụ phù hợp |
|---|---|---|
| Giá trị cụ thể trong `verify` | So sánh cả argument qua `equals` | `verify(repo).save(expected)` |
| `eq(expected)` | Matcher so sánh bằng nhau khi phối hợp matcher khác | `verify(client).send(eq("x"), any())` |
| `any(Type.class)` | Chỉ cần biết có argument thuộc kiểu hợp lệ, không kiểm tra field | `verify(repo).save(any(Order.class))` |
| `argThat(predicate)` | Kiểm tra một điều kiện tại verification | `argThat(e -> e.status().equals("READY"))` |
| `ArgumentCaptor` | Đọc argument thật, kiểm tra nhiều trường, dynamic values, nhiều invocation | Bắt event chứa UUID được tạo trong service |

**Nguyên tắc matcher:** Khi một lời gọi Mockito dùng argument matcher cho một tham số, những tham số còn lại cũng phải dùng matcher phù hợp (`eq(...)`, `any(...)`, `capture()`, v.v.). Trộn matcher với literal thô có thể gây `InvalidUseOfMatchersException`.

Ví dụ đúng cho method có hai tham số:

```java
verify(client).send(
        eq("buyer@example.test"), payloadCaptor.capture());
```

Đây là đoạn minh họa trong test có `client`, `eq` và `payloadCaptor` đã khai báo. Nếu chỉ cần kiểm tra giá trị mà không cần đọc nhiều trường, `argThat` có thể ngắn hơn; nếu cần thông báo assertion riêng cho từng field thì captor với `assertAll` thường dễ bảo trì.

## 8. Áp dụng trong test Spring Boot thật

**Unit test với MockitoExtension:** Giống ví dụ mục 4, khởi tạo service thật qua constructor với dependency mock. Cách này không tạo ApplicationContext, chạy nhanh và rất phù hợp để kiểm tra service **gọi một port/interface với đúng dữ liệu**.

**Integration/slice test có Spring context:** Khi cần xác minh mapping/controller hoặc cấu hình Spring đi qua đường đi thật, phải đưa mock vào đúng bean được service sử dụng. Trong dự án hiện đại, các công cụ như `@MockitoBean` (ở những phiên bản Spring Framework hỗ trợ) hoặc cơ chế thay thế mock bean tương ứng với phiên bản Spring Boot có thể hữu ích. Nếu tạo một `@Mock` độc lập mà Spring service đang gọi một bean thật khác, captor trên mock đó sẽ thấy **không có invocation** dù ứng dụng thực tế đã gọi bean khác.

**Repository:** `verify(repository).save(captor.capture())` có thể xác minh entity/service **đề nghị** lưu dữ liệu nào. Nó không chứng minh JPA mapping, database constraint, transaction hoặc dữ liệu đã commit. Khi rủi ro nằm ở persistence, cần test tích hợp với repository/database phù hợp.

**Message broker/HTTP client:** Captor cho biết command/request/payload được chuyển tới adapter mock. Nó không xác nhận broker nhận được message hay server ngoài xử lý thành công. Với contract trên mạng, cần integration/contract test cho serialization, headers, retry, lỗi phản hồi và cơ chế giao tiếp thật ở cấp phù hợp.

**Mockito và AOP/proxy:** Xác minh trên đúng mock mà code kiểm thử đang gọi; tránh trộn spy/mock của nhiều instance hoặc vô tình bypass proxy Spring khi chính behavior proxy là thứ cần test. Captor không thay thế việc hiểu ranh giới SUT và dependency.

## 9. Những lỗi thường gặp và cách phân tích

### 9.1. "Wanted but not invoked"

Thông báo kiểu `Wanted but not invoked` cho biết invocation bạn xác minh không xuất hiện trên **mock đó** theo điều kiện matcher. Kiểm tra:
- SUT có thực sự chạy qua nhánh gọi dependency không?
- Có tạo nhầm một instance khác của publisher/repository?
- Service Spring dùng bean khác với mock trong test?
- Tham số/bộ lọc matcher có khớp lời gọi thực không?

Đừng chữa bằng việc bỏ `verify` hoặc đổi thành `any()` nếu chính dữ liệu truyền đi đang là rủi ro cần kiểm chứng.

### 9.2. "Too many actual invocations"

Nếu `verify(mock)` mặc định mong một lần nhưng thực tế hai lần, đó có thể là bug phát event trùng hoặc test chưa thiết kế đúng số lần. Hãy xác định hợp đồng rồi dùng `times(n)` chính xác. Đừng luôn tăng `n` để test xanh.

### 9.3. Gọi getValue() khi chưa capture

`getValue()` chỉ có ý nghĩa **sau một verification/stubbing tương ứng đã capture thành công**. Nếu test không gọi `verify(...capture())`, hoặc verification đã thất bại, không được suy đoán captor có dữ liệu. Dùng JUnit assertion/Mockito failure để xem invocation trước.

### 9.4. Chỉ kiểm tra "có event", bỏ qua dữ liệu

```java
verify(publisher).publish(any(OrderPlacedEvent.class));
```

Dòng này xác nhận mock nhận một argument không null thuộc kiểu phù hợp nhưng **không kiểm tra** UUID, email, danh sách SKU, số tiền hay metadata. Với bài học về ArgumentCaptor, phải thêm assertion cho các field là một phần của hợp đồng.

### 9.5. Captor lấy được object nhưng test quá giòn

Test capture cả DTO rồi so từng field nội bộ không liên quan đến yêu cầu có thể fail khi refactor hợp lệ. Ưu tiên kiểm tra field định nghĩa hành vi giao tiếp: ID, recipient, số tiền, trạng thái, danh sách sản phẩm, thời điểm/sự kiện theo hợp đồng. Không khẳng định clock/random ID bằng một giá trị cố định nếu không inject nguồn tạo dữ liệu hoặc đối chiếu với giá trị returned.

### 9.6. Nhầm object mutable là snapshot

Captor chỉ giữ reference. Nếu muốn kiểm tra trạng thái **tại thời điểm gọi**, hãy chuyển sang immutable event hoặc chụp copy tại invocation. Sự kiện immutable cũng giúp ngăn lỗi khi message xử lý bất đồng bộ sau đó.

### 9.7. Quên thứ tự và số lần xuất hiện khi có nhiều lời gọi

`getAllValues()` dùng để kiểm tra nhiều invocation, nhưng test phải xác định liệu thứ tự gọi có thuộc hợp đồng hay không. Nếu thứ tự không quan trọng, so các trường cần thiết theo tập hoặc đa tập phù hợp, **giữ số lần xuất hiện khi duplicate có ý nghĩa**. Không chuyển bừa sang `Set` nếu cần phát hiện event phát hai lần.

## 10. Checklist trước khi kết luận ArgumentCaptor test đạt

- [ ] Đang kiểm thử **đối tượng thật** (service/adapter), còn dependency là mock đúng instance.
- [ ] Đã gọi hành vi trước, rồi `verify(...capture())` với đúng mock và đúng method.
- [ ] Đã xác minh số lần gọi (`times(n)`, mặc định một lần, hoặc `verifyNoInteractions` khi cần).
- [ ] Đã dùng `getValue()` cho một giá trị hoặc `getAllValues()` khi cần nhiều invocation.
- [ ] Đã kiểm tra dữ liệu quan trọng bên trong object: dynamic ID, field được biến đổi, collection, recipient, trạng thái...
- [ ] Đã phân biệt nội dung tại invocation và trạng thái bị mutate sau invocation.
- [ ] Đã dùng matcher nhất quán khi phương thức có nhiều argument.
- [ ] Đã phân biệt **gọi mock với đúng dữ liệu** và **phụ thuộc thật đã hoàn tất tác vụ**.
- [ ] Đã chạy đúng lớp test và xem report của Gradle/Maven/CI, không chỉ dự đoán từ ví dụ.

**Kết luận:** `ArgumentCaptor` giúp Mockito kiểm tra **dữ liệu thực sự được chuyển từ Spring Boot service tới phụ thuộc mock**. Quy trình đáng tin là **thực thi service → verify đúng invocation → capture argument → assert những field nghiệp vụ cần thiết**. Với nhiều lần gọi dùng `getAllValues()`; với object mutable chú ý captor không tự lưu snapshot; và khi cần chứng minh database/broker thật đã xử lý, hãy bổ sung integration test phù hợp.