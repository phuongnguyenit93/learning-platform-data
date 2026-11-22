# Kiểm thử dữ liệu gửi ra ngoài thay vì chỉ đếm lời gọi

> **Module:** Spring Boot – testing  
> **Nhóm:** Unit test nghiệp vụ  
> **Trọng tâm:** Một dependency được gọi đúng một lần vẫn có thể nhận **dữ liệu sai**. Test tốt cần kiểm tra **payload, giá trị nghiệp vụ và side effect** được gửi tới ranh giới bên ngoài của đơn vị đang kiểm thử.

## 1. Vấn đề: đúng số lần gọi chưa đủ để kết luận đúng nghiệp vụ

Giả sử hệ thống có use case tạo đơn hàng. Sau khi lưu đơn, service phải gửi một sự kiện `OrderCreated` tới cổng phát sự kiện. Test kiểu sau rất phổ biến:

```java
service.place(command);
verify(publisher, times(1)).publish(any(OrderCreatedEvent.class));
```

Nó chỉ chứng minh: **mock publisher đã nhận một lời gọi `publish` với đối số kiểu `OrderCreatedEvent`**. Nó **không chứng minh** khách hàng, mã hàng, số lượng, số tiền, currency hoặc ID đơn được gửi đúng.

Giả sử service bị lỗi và thực tế gửi:

```text
orderId        = 501
recipientEmail = wrong@example.test  <-- Sai người nhận
sku            = SKU-9
quantity       = 3
total          = 0.00                <-- Sai tiền
currency       = USD
```

Test đếm lời gọi vẫn có thể xanh. Đây là **false confidence**: kiểm tra một điều có thật nhưng quá yếu so với hợp đồng nghiệp vụ.

Một test có giá trị cần trả lời rõ:

1. **Có gửi hay không?** Ví dụ đã publish một event khi tạo đơn thành công.
2. **Gửi tới đâu và gửi loại gì?** Ví dụ tới `OrderEventPublisher`, đúng `OrderCreatedEvent`.
3. **Nội dung gửi là gì?** ID sau khi lưu, email đã chuẩn hóa, SKU, quantity, tổng tiền và currency.
4. **Gửi trong điều kiện nào?** Không publish khi đầu vào không hợp lệ hoặc lưu thất bại.
5. **Có giới hạn số lần và thứ tự không?** Chỉ assert “đúng một lần” hay “lưu trước rồi gửi” khi đó thực sự là hợp đồng.

Đây là bài học về **unit test nghiệp vụ có outbound collaborator**. Mockito giúp kiểm chứng dữ liệu **mà unit chuyển giao cho cổng bên ngoài**; nó không tự chứng minh Kafka, SMTP, HTTP endpoint hoặc database thật đã nhận dữ liệu.

## 2. Bốn mức độ kiểm tra outbound interaction

| Cách test | Nó thực sự xác minh | Lỗi vẫn có thể lọt |
| --- | --- | --- |
| `verify(publisher).publish(any())` | Có ít nhất một lời gọi phù hợp với matcher và số lần mặc định; không xem nội dung | Event chứa ID, người nhận hoặc tiền sai |
| `verify(publisher, times(1)).publish(any(OrderCreatedEvent.class))` | Có đúng một lời gọi phù hợp với đối số kiểu mong đợi | Mọi trường trong event vẫn có thể sai |
| `verify(publisher).publish(expectedEvent)` | Event khớp `equals` với giá trị kỳ vọng và có một lời gọi phù hợp | Nếu publisher nhận **thêm event khác** không khớp, test này đơn lẻ không nhất thiết fail |
| `verify(publisher).publish(captor.capture())` + assertion nội dung | Lấy event thực tế rồi kiểm tra field/DTO, đồng thời có thể kiểm tra số lần | Chỉ bảo vệ các field đã assert; vẫn là mock, chưa chứng minh giao hàng thật |

Một lựa chọn tốt nếu đối số là **immutable Java record** và toàn bộ field là contract: dùng `verify(publisher).publish(new OrderCreatedEvent(...))`. Record có `equals` theo từng component nên assertion ngắn và đủ cụ thể.

Nếu event có field động (timestamp, correlation ID, UUID), payload lớn hoặc muốn failure message cho từng trường, dùng **`ArgumentCaptor`**, sau đó so sánh chính xác các field hợp đồng. Khi test gọi một lần và captor được dùng trong `verify(publisher).publish(captor.capture())`, Mockito xác nhận đúng một lời gọi phù hợp với captor; khi muốn bắt **mọi** event ngoài ý muốn, cân nhắc `verifyNoMoreInteractions(publisher)` hoặc verify toàn bộ số lời gọi có ý nghĩa.

**Quan trọng:** không nên tối ưu test thành “càng nhiều `verify` càng tốt”. Hãy kiểm tra dữ liệu và hành vi mà user, hệ thống khác hoặc database thực sự trông chờ.

## 3. Thiết kế hợp đồng trước khi viết Mockito

Xét yêu cầu cụ thể:

- Đầu vào gồm `customerEmail`, `sku`, `unitPrice` và `quantity`.
- Email và SKU được `trim()` trước khi lưu/gửi.
- `quantity` phải lớn hơn 0, `unitPrice` không được âm.
- Tổng tiền = `unitPrice × quantity`, làm tròn hai chữ số thập phân với `HALF_UP`.
- Sau khi repository trả về ID hợp lệ, service gửi đúng **một** `OrderCreatedEvent` gồm ID đó, email đã chuẩn hóa, SKU đã chuẩn hóa, quantity, total và `currency="USD"`.
- Nếu đầu vào sai hoặc repository ném exception, **không gửi event**.
- Service trả receipt chứa ID và total để caller sử dụng.

Bảng expected độc lập:

| Giá trị | Input hoặc kết quả phụ thuộc | Expected khi gửi ra |
| --- | --- | --- |
| `customerEmail` | `" buyer@example.test "` | `"buyer@example.test"` |
| `sku` | `" SKU-9 "` | `"SKU-9"` |
| `quantity` | `3` | `3` |
| `unitPrice` | `12.50` | Dùng để tính tiền, không phải trường event |
| `total` | `12.50 × 3` | `37.50` |
| `orderId` | Repository giả lập trả `501` | `501` |
| `currency` | Quy định của ví dụ | `"USD"` |

Nếu chỉ kiểm tra gọi publisher một lần, các lỗi như **gửi email chưa trim**, **lấy quantity mặc định 1**, **total luôn bằng 0** hoặc **dùng ID tạm trước khi lưu** vẫn có thể pass. Với bảng này, ta biết rõ expected phải được kiểm tra.

## 4. Dự án Spring Boot/Java 17 có thể chạy test

Mẫu dưới đây dùng **Spring Boot 3.5.0, Java 17, JUnit Jupiter và Mockito**. Tất cả unit test chạy **không nạp Spring context**, vì điều đang kiểm chứng là logic nghiệp vụ của `CheckoutService`. Có thể dùng chính kiến trúc này cho service được đăng ký làm bean trong ứng dụng thật, nhưng unit test không cần khởi động Spring để kiểm tra cổng outbound.

### 4.1. Cấu trúc tệp

```text
outbound-payload-test/
├── pom.xml
└── src/
    ├── main/java/com/example/outbound/
    │   ├── OutboundDemoApplication.java
    │   ├── PlaceOrderCommand.java
    │   ├── OrderDraft.java
    │   ├── SavedOrder.java
    │   ├── OrderCreatedEvent.java
    │   ├── OrderReceipt.java
    │   ├── OrderRepository.java
    │   ├── OrderEventPublisher.java
    │   └── CheckoutService.java
    └── test/java/com/example/outbound/
        └── CheckoutServiceTest.java
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>outbound-payload-test</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito, AssertJ, Spring Test và các thư viện test thường dùng. Không cần `@SpringBootTest` cho mẫu unit test này. Nếu sau này kiểm tra cả Bean wiring hoặc connector thật, đó là phạm vi test khác.

### 4.3. Mã Java ứng dụng

Đặt từng `public record`/`public interface`/`public class` trong **đúng tệp** có tên giống type, dưới package `com.example.outbound`.

```java
// OutboundDemoApplication.java
package com.example.outbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OutboundDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboundDemoApplication.class, args);
    }
}
```

```java
// PlaceOrderCommand.java
package com.example.outbound;

import java.math.BigDecimal;

public record PlaceOrderCommand(
        String customerEmail, String sku,
        BigDecimal unitPrice, int quantity) {}
```

```java
// OrderDraft.java
package com.example.outbound;

import java.math.BigDecimal;

public record OrderDraft(
        String customerEmail, String sku,
        int quantity, BigDecimal total) {}
```

```java
// SavedOrder.java
package com.example.outbound;

public record SavedOrder(long id) {}
```

```java
// OrderCreatedEvent.java
package com.example.outbound;

import java.math.BigDecimal;

public record OrderCreatedEvent(
        long orderId,
        String recipientEmail,
        String sku,
        int quantity,
        BigDecimal total,
        String currency) {}
```

```java
// OrderReceipt.java
package com.example.outbound;

import java.math.BigDecimal;

public record OrderReceipt(long orderId, BigDecimal total) {}
```

```java
// OrderRepository.java
package com.example.outbound;

public interface OrderRepository {
    SavedOrder save(OrderDraft draft);
}
```

```java
// OrderEventPublisher.java
package com.example.outbound;

public interface OrderEventPublisher {
    void publish(OrderCreatedEvent event);
}
```

```java
// CheckoutService.java
package com.example.outbound;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class CheckoutService {
    private final OrderRepository repository;
    private final OrderEventPublisher publisher;

    public CheckoutService(
            OrderRepository repository,
            OrderEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    public OrderReceipt place(PlaceOrderCommand command) {
        if (command == null
                || command.customerEmail() == null
                || command.customerEmail().isBlank()
                || command.sku() == null
                || command.sku().isBlank()
                || command.unitPrice() == null
                || command.unitPrice().signum() < 0
                || command.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }

        String email = command.customerEmail().trim();
        String sku = command.sku().trim();
        BigDecimal total = command.unitPrice()
                .multiply(BigDecimal.valueOf(command.quantity()))
                .setScale(2, RoundingMode.HALF_UP);

        OrderDraft draft = new OrderDraft(
                email, sku, command.quantity(), total);

        SavedOrder saved = repository.save(draft);
        if (saved == null || saved.id() <= 0) {
            throw new IllegalStateException("No valid saved order ID");
        }

        OrderCreatedEvent event = new OrderCreatedEvent(
                saved.id(), email, sku,
                command.quantity(), total, "USD");
        publisher.publish(event);

        return new OrderReceipt(saved.id(), total);
    }
}
```

**Ranh giới của unit:** `CheckoutService` thật; `OrderRepository` và `OrderEventPublisher` là dependency interface. Trong ứng dụng thực tế, các interface này cần implementation/adapter và có thể đăng ký `CheckoutService` làm Spring bean. Để ví dụ unit test chạy và ứng dụng mẫu có thể khởi động độc lập, class service không được đánh dấu `@Service`; bài này không cấu hình adapter thật và không khẳng định đã gửi event ra broker.

**Điểm nghiệp vụ:** ID `501` sẽ do mock repository trả lại trong test; event bắt buộc dùng ID **đã lưu**. Số tiền 37.50 đến từ phép nhân 12.50 × 3; expected không tính lại bằng cách gọi service.

### 4.4. Unit test kiểm tra đầy đủ dữ liệu outbound

```java
// CheckoutServiceTest.java
package com.example.outbound;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    OrderRepository repository;

    @Mock
    OrderEventPublisher publisher;

    @InjectMocks
    CheckoutService service;

    @Captor
    ArgumentCaptor<OrderDraft> savedDraftCaptor;

    @Captor
    ArgumentCaptor<OrderCreatedEvent> eventCaptor;

    private PlaceOrderCommand validCommand() {
        return new PlaceOrderCommand(
                " buyer@example.test ", " SKU-9 ",
                new BigDecimal("12.50"), 3);
    }

    @Test
    void sendsCorrectBusinessPayloadAfterSaving() {
        when(repository.save(any(OrderDraft.class)))
                .thenReturn(new SavedOrder(501L));

        OrderReceipt receipt = service.place(validCommand());

        verify(repository).save(savedDraftCaptor.capture());
        assertEquals(
                new OrderDraft("buyer@example.test", "SKU-9",
                        3, new BigDecimal("37.50")),
                savedDraftCaptor.getValue());

        verify(publisher).publish(eventCaptor.capture());
        assertEquals(
                new OrderCreatedEvent(
                        501L,
                        "buyer@example.test",
                        "SKU-9",
                        3,
                        new BigDecimal("37.50"),
                        "USD"),
                eventCaptor.getValue());

        assertEquals(new OrderReceipt(
                501L, new BigDecimal("37.50")), receipt);
    }

    @Test
    void invalidQuantityCausesNoOutboundCall() {
        PlaceOrderCommand invalid = new PlaceOrderCommand(
                "buyer@example.test", "SKU-9",
                new BigDecimal("12.50"), 0);

        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.place(invalid));

        verifyNoInteractions(repository, publisher);
    }

    @Test
    void repositoryFailureDoesNotPublishAnEvent() {
        when(repository.save(any(OrderDraft.class)))
                .thenThrow(new IllegalStateException("Storage unavailable"));

        IllegalStateException failure = assertThrowsExactly(
                IllegalStateException.class,
                () -> service.place(validCommand()));

        assertEquals("Storage unavailable", failure.getMessage());
        verifyNoInteractions(publisher);
    }

    @Test
    void invalidSavedIdDoesNotPublishAnEvent() {
        when(repository.save(any(OrderDraft.class)))
                .thenReturn(new SavedOrder(0L));

        assertThrowsExactly(IllegalStateException.class,
                () -> service.place(validCommand()));

        verifyNoInteractions(publisher);
    }
}
```

**Bốn phương thức test** có bốn mục tiêu rõ ràng:

1. Có lưu draft đúng, phát event đúng **từng trường**, và receipt trả về khớp ID/tổng tiền.
2. Input quantity sai thì không gọi cả repository lẫn publisher.
3. Lưu bị lỗi thì không publish, và lỗi được truyền ra theo contract.
4. Repository trả ID không hợp lệ thì không publish.

Các assertion quan trọng không dựa vào số lần gọi đơn thuần. Test đầu cũng chứng minh payload lưu vào repository đúng, trước khi xét payload gửi publisher. Các test âm tính dùng `verifyNoInteractions` vì yêu cầu thật là **không tạo side effect** khi điều kiện không được đáp ứng.

### 4.5. Vì sao các thành phần test này hoạt động?

- `@ExtendWith(MockitoExtension.class)` khởi tạo và quản lý Mockito mocks cho JUnit Jupiter.
- `@Mock` tạo dependency giả; không có database/broker thật.
- `@InjectMocks` dựng `CheckoutService` và tiêm mocks qua constructor.
- `when(repository.save(any(OrderDraft.class))).thenReturn(new SavedOrder(501L))` điều khiển ID repository trả về, không tự quyết định event do service gửi.
- `@Captor` tạo `ArgumentCaptor` typed; `verify(...).save(captor.capture())` và `verify(...).publish(captor.capture())` lấy **đối số service thực sự truyền ra**.
- `assertEquals(expectedRecord, capturedRecord)` sử dụng value equality của record để kiểm tra tất cả component. Với `BigDecimal`, equality còn xét cả scale; vì code đặt `setScale(2)`, expected `37.50` đúng thang đo.
- `verifyNoInteractions(publisher)` mạnh hơn việc chỉ không thấy kết quả trả về: nó buộc service không phát event trong hai nhánh lỗi được mô tả.

Nếu người viết vô tình sửa:

```java
// Đoạn minh họa lỗi, không áp dụng vào mã đúng:
publisher.publish(new OrderCreatedEvent(
        saved.id(),
        command.customerEmail(),  // Chưa trim
        sku,
        1,                         // Sai quantity
        BigDecimal.ZERO,           // Sai total
        "USD"));
```

`verify(publisher, times(1)).publish(any(OrderCreatedEvent.class))` có thể vẫn pass; test capture event ở trên sẽ fail. Đó là khác biệt giữa **kiểm chứng có gọi** và **kiểm chứng dữ liệu được gửi đúng**.

## 5. Hai cách khác ngoài `ArgumentCaptor`

### 5.1. So sánh trực tiếp đối số bằng `equals`

Với DTO là immutable `record`, có thể viết gọn trong test:

```java
verify(publisher).publish(new OrderCreatedEvent(
        501L, "buyer@example.test", "SKU-9",
        3, new BigDecimal("37.50"), "USD"));
```

Đây là **đoạn thay thế cho dòng verify và captor trong test thành công**, không phải test độc lập có thể dán ra ngoài class mà chạy. Nó rõ ràng, ít mã và dựa trên record equality. Nếu DTO là class bình thường và không implement `equals` theo giá trị, Mockito mặc định có thể so sánh theo identity; hãy bổ sung equality phù hợp với domain hoặc dùng captor.

Lưu ý: `verify(publisher).publish(expectedEvent)` chỉ xác nhận **một invocation phù hợp**. Nếu code phát thêm một event có nội dung khác, invocation thêm có thể không bị xác nhận bởi assertion này. Nếu hợp đồng đòi **chỉ một event tổng cộng**, dùng thêm:

```java
verifyNoMoreInteractions(publisher);
```

sau khi đã verify event mong đợi. Khi sử dụng `ArgumentCaptor` với `verify(publisher).publish(captor.capture())`, captor khớp các invocation có đối số tương thích rồi Mockito kiểm tra số lần khớp mặc định; trong ví dụ publisher chỉ có đúng một phương thức typed `publish(OrderCreatedEvent)`.

### 5.2. `argThat` khi chỉ một phần payload thuộc hợp đồng

Khi sự kiện có thêm field động không bắt buộc bằng nhau tuyệt đối, test có thể xác nhận những field thật sự quan trọng:

```java
verify(publisher).publish(argThat(event ->
        event != null
        && event.orderId() == 501L
        && "buyer@example.test".equals(event.recipientEmail())
        && "SKU-9".equals(event.sku())
        && event.quantity() == 3
        && new BigDecimal("37.50").compareTo(event.total()) == 0
        && "USD".equals(event.currency())));
```

Đoạn này được dùng **bên trong test class** sau khi service đã được gọi và mock repository trả `501L`; cần static import `org.mockito.ArgumentMatchers.argThat`. Ưu điểm: rõ subset/semantics, có thể dùng `compareTo` để không khóa vào scale của `BigDecimal` khi scale không phải contract. Nhược điểm: khi mismatch, failure message thường kém cụ thể hơn `ArgumentCaptor` kết hợp các assertion có mô tả.

Không dùng matcher luôn đúng như `argThat(event -> true)`: nó chỉ đổi tên cho `any()` và không xác minh dữ liệu.

### 5.3. Khi nên dùng cách nào?

| Tình huống | Cách ưu tiên | Lý do |
| --- | --- | --- |
| Immutable record chứa toàn bộ contract | `verify(mock).send(expectedRecord)` | Ngắn, trực tiếp, đầy đủ |
| DTO có nhiều field cần mô tả failure chi tiết | `ArgumentCaptor` + `assertAll`/AssertJ | Cho biết trường nào sai |
| Chỉ một phần event ổn định, field còn lại sinh động | `argThat` hoặc captor + assertions theo field | Không khóa giá trị không thuộc contract |
| Nhiều invocation cần kiểm tra tập payload | `ArgumentCaptor#getAllValues()` | Lấy tất cả event gửi ra |
| Muốn diễn giải dữ liệu outbound như một output thuần | Recording fake thay mock | Dễ assert cả danh sách payload |
| Chỉ cần biết không tạo side effect khi lỗi | `verifyNoInteractions` | Phản ánh negative contract chính xác |

## 6. Phân biệt assertion số lần gọi, nội dung và thứ tự

### 6.1. Số lần gọi là thuộc tính độc lập

Có những hợp đồng thật sự cần **đúng một lần** (ví dụ một thông báo xác nhận cho mỗi đơn hàng). Khi đó phải kiểm tra count, nhưng **count phải đi cùng nội dung**:

```java
ArgumentCaptor<OrderCreatedEvent> captor =
        ArgumentCaptor.forClass(OrderCreatedEvent.class);

verify(publisher, times(1)).publish(captor.capture());
assertEquals(expectedEvent, captor.getValue());
```

Đoạn này là **mẫu nhúng vào test**, giả định có `publisher`, `expectedEvent` và static imports `verify`/`times`. Ở đây, `times(1)` xác nhận count, còn `assertEquals` xác nhận giá trị. Không dùng `times(1)` như thay thế cho assert payload.

Tương tự, nếu một code phát hai thông báo cho cùng đơn trong khi yêu cầu chỉ một, kiểm tra payload đơn lẻ mà không kiểm soát số lượng event cũng có thể bỏ sót duplicate. Có thể dùng verify trên toàn bộ method, `verifyNoMoreInteractions` sau khi verify những lời gọi mong đợi, hoặc fake ghi lại các event rồi so sánh danh sách.

### 6.2. Nhiều lần gửi: `getAllValues()`

Giả sử một batch xử lý hai đơn hàng và yêu cầu phát **mỗi đơn đúng một event**. Khi đó cần kiểm tra từng payload, tránh chỉ đếm hai lời gọi:

```java
ArgumentCaptor<OrderCreatedEvent> captor =
        ArgumentCaptor.forClass(OrderCreatedEvent.class);

verify(publisher, times(2)).publish(captor.capture());

assertThat(captor.getAllValues()).containsExactlyInAnyOrder(
        expectedEventForFirstOrder,
        expectedEventForSecondOrder);
```

Đây là **mẫu minh họa cho một batch service khác**, không phải phương thức `CheckoutService.place` hiện tại (nó xử lý một đơn). Cần static import AssertJ `assertThat`, Mockito `verify`/`times`; `expectedEventForFirstOrder` và `expectedEventForSecondOrder` là các record kỳ vọng do test chuẩn bị độc lập.

- `getValue()` lấy **giá trị được capture cuối cùng**, nên không phù hợp nếu cần kiểm tra tất cả event.
- `getAllValues()` trả toàn bộ giá trị capture từ các invocation đã verify.
- `containsExactlyInAnyOrder` kiểm tra **đúng số phần tử, nội dung và số lần xuất hiện**, không phụ thuộc thứ tự.
- Nếu hợp đồng yêu cầu order của các event, đổi thành `containsExactly`; không áp đặt thứ tự khi chỉ yêu cầu tập dữ liệu.

### 6.3. Thứ tự lời gọi chỉ khi thuộc hợp đồng

Nếu yêu cầu “**chỉ được publish sau khi save thành công**”, thứ tự giữa hai cổng có thể mang ý nghĩa nghiệp vụ:

```java
InOrder sequence = inOrder(repository, publisher);
sequence.verify(repository).save(any(OrderDraft.class));
sequence.verify(publisher).publish(any(OrderCreatedEvent.class));
```

Đoạn này là **mẫu bổ trợ** trong test; cần `org.mockito.InOrder` và static import `org.mockito.Mockito.inOrder`. Nó kiểm tra thứ tự tương đối, **vẫn phải có assertion dữ liệu** riêng. Không verify thứ tự các private helper hay method nội bộ chỉ vì hiện tại chúng chạy theo một thứ tự cụ thể.

Ngay cả khi save được gọi trước publish trong unit test, sự phối hợp qua DB/broker thật có thể khác do transaction/ack/network. Muốn bảo đảm sự kiện được phát bền vững sau commit có thể cần transactional outbox và integration test. Unit Mockito không chứng minh điều đó.

## 7. Kiểm tra dữ liệu gửi ra ở các loại outbound port khác nhau

Cùng tư duy được áp dụng cho nhiều adapter trong Spring Boot:

| Outbound port | Dữ liệu đáng assert | Sai lầm phổ biến |
| --- | --- | --- |
| `EmailSender` | To/CC, template ID, subject, body chứa order ID/số tiền, locale | Chỉ `verify(sender).send(any())` |
| `OrderEventPublisher` | Event type, aggregate ID, correlation ID, SKU, amount, currency | Đếm publish nhưng không xem event payload |
| `PaymentGateway` | Amount/currency, order reference, idempotency key, callback URL | Chỉ assert gateway đã được gọi |
| `InventoryClient` | SKU, requested quantity, warehouse, reservation ID | Dùng `anyString()`/`anyInt()` cho tất cả fields |
| `Repository` | Entity/draft lưu đúng owner, state, total | Chỉ `verify(repository).save(any())` |
| `WebhookClient` | Target URL, HTTP method, headers, JSON body, signature/identifier | Chỉ assert request đã “sent” |
| `AuditLogger` có contract nghiệp vụ | Actor/action/resource ID, outcome, policy metadata | Chỉ assert ghi một log bất kỳ |

Đối với các giá trị nhạy cảm như token, mật khẩu hay dữ liệu thanh toán, test **không nên dùng thông tin thật**. Dùng fixture giả và assert quy tắc ẩn/mã hóa/chỉ mang trường cần thiết. Không đưa secret thật vào failure logs hoặc snapshot.

### 7.1. Ví dụ email có nhiều đối số

Giả sử interface có phương thức:

```java
void send(String recipient, String subject, String body);
```

Để kiểm tra đúng người nhận và nội dung:

```java
verify(emailSender).send(
        eq("buyer@example.test"),
        eq("Order 501 confirmed"),
        argThat(body -> body != null
                && body.contains("SKU-9")
                && body.contains("37.50")));
```

Đây là **minh họa sử dụng trong một test khác**: `emailSender` là Mockito mock, `send` thuộc interface giả định, và static imports là `eq`, `argThat` của `org.mockito.ArgumentMatchers`. Dùng matcher cho **tất cả ba đối số** trong lời gọi verify để tránh `InvalidUseOfMatchersException` khi trộn matcher và giá trị thô.

Tùy contract mà chọn exact string vs structural assertions:

- Subject cần chính xác → `eq(...)` hợp lý.
- Body có thể đổi whitespace/locale/template formatting → assert phần ổn định như order ID, tổng tiền, recipient phù hợp.
- Body là JSON → parse thành object/JSON tree rồi assert giá trị; đừng phụ thuộc thứ tự field, khoảng trắng hay indentation trừ khi format nguyên văn là contract.

### 7.2. Việc lưu repository cũng là outbound data

Nếu service gọi repository để lưu, chỉ verify `save(any(OrderDraft.class))` không phát hiện entity bị thiếu owner/total hoặc trạng thái sai. Captor trên `OrderRepository#save` trong dự án mẫu cho thấy:

```text
Expected draft:
OrderDraft(
  customerEmail = "buyer@example.test",
  sku           = "SKU-9",
  quantity      = 3,
  total         = 37.50)
```

Test unit kiểm tra service **đã đề nghị lưu đúng dữ liệu**. Nó **chưa chứng minh** repository/ORM đã persist, transaction commit hoặc query đọc lại đúng. Muốn kiểm tra persistence thực, thêm `@DataJpaTest` hoặc integration test với database đúng loại; dữ liệu mong đợi vẫn nên được assert theo business contract.

## 8. Tránh assertion outbound giòn hoặc “xanh giả”

### 8.1. Expected không được lặp lỗi của actual

Sai:

```java
service.place(command);

OrderCreatedEvent actual = captor.getValue();
OrderCreatedEvent expected = actual;

assertEquals(expected, actual);
```

Thậm chí đoạn trên còn thiếu `verify(publisher).publish(captor.capture())` trước khi gọi `getValue()`, nên có thể lỗi `No argument value was captured`. Nhưng dù thêm verify, `expected = actual` vẫn là tautology: nó không định nghĩa giá trị phải đúng.

Tốt hơn: expected từ **đầu vào và quy tắc đã biết**, với ID có kiểm soát của stub repository:

```java
new OrderCreatedEvent(
        501L, "buyer@example.test", "SKU-9",
        3, new BigDecimal("37.50"), "USD");
```

Đây là expected độc lập; khi code biến đổi sai thì mismatch sẽ bị phát hiện.

### 8.2. `any()` ở verify là công cụ đếm, không phải oracle payload

`any()` và `any(OrderCreatedEvent.class)` hữu ích khi stub repository, hoặc khi bạn chỉ quan tâm có tương tác. Nhưng nếu dùng chúng ở tất cả verification về side effect, test không kiểm tra điều quan trọng nhất: **thông điệp gửi đi có đúng nội dung không?**

Một anti-pattern có thêm verify nhưng vẫn yếu:

```java
verify(publisher).publish(any(OrderCreatedEvent.class));
assertNotNull(service.place(command));
```

Nó vừa không kiểm tra payload, vừa gọi `service.place` **lần thứ hai** ngay trong assertion, tạo side effect bổ sung; test có thể fail vì count hoặc gây nhầm lẫn. Hãy gọi use case **một lần**, giữ kết quả, rồi assert response và interactions.

### 8.3. Assert chi tiết không thuộc hợp đồng

Payload test có thể quá giòn khi khóa vào:

- HashMap iteration order trong JSON mà consumer không yêu cầu.
- Timestamp chính xác tới nanosecond khi tạo bằng đồng hồ thật.
- UUID ngẫu nhiên cố định dù contract chỉ yêu cầu hợp lệ/duy nhất.
- Tên helper nội bộ, số lần gọi mapper/private method.
- Chuỗi email đầy đủ từng dấu cách khi yêu cầu chỉ có template ID và trường nghiệp vụ.

Nếu hợp đồng chỉ định dữ liệu có ý nghĩa mà không yêu cầu formatting byte-for-byte, assert semantics thay vì snapshot nguyên văn. Nhưng nếu hệ thống ngoài thật sự cần **signature bytes**, canonical JSON, header chính xác hoặc template bắt buộc, những chi tiết đó **trở thành contract** và cần test đúng.

### 8.4. Record, object mutable và vấn đề capture tham chiếu

`ArgumentCaptor` giữ **đối tượng được truyền vào**, không tự chụp deep snapshot tại thời điểm gửi. Nếu payload là mutable object và service sửa lại nó **sau** khi gọi publisher, captor có thể nhìn thấy trạng thái đã thay đổi, khiến test không phản ánh chính xác bytes/value đã đi qua boundary tại thời điểm gọi.

Giải pháp thường tốt nhất:

1. Dùng immutable DTO/record cho event.
2. Tạo defensive copy khi chuyển qua asynchronous boundary.
3. Nếu cần kiểm thử chính xác thời điểm, dùng recording fake hoặc mock `doAnswer` để snapshot field ngay tại invocation.

Ví dụ minh họa với DTO mutable giả định:

```java
List<String> snapshots = new ArrayList<>();

doAnswer(invocation -> {
    MutableMessage message = invocation.getArgument(0);
    snapshots.add(message.getBody());
    return null;
}).when(sender).send(any(MutableMessage.class));
```

Đoạn này **không thuộc dự án chạy được ở phần 4**: `MutableMessage`/`sender` là các type/biến minh họa, cần import `ArrayList`/`List` và Mockito `doAnswer`/`any`. Nó cho thấy cách lưu snapshot **giá trị** ngay khi gọi. Không dùng `doAnswer` phức tạp nếu record/immutable object đã giải quyết được vấn đề.

### 8.5. Thời gian và ID động

Nếu event có `createdAt`, `eventId` hoặc `correlationId`, xác định contract:

- **Giá trị phải chính xác theo yêu cầu?** Tiêm `Clock` cố định và generator ID có thể kiểm soát, rồi assert equality.
- **Chỉ cần hợp lệ/không rỗng?** Assert thuộc tính phù hợp như không null, parse được UUID, liên kết đúng correlation ID.
- **Phải giống ID từ upstream?** Chuẩn bị upstream ID cố định và assert event truyền nguyên đúng giá trị đó.
- **Phải duy nhất giữa các lần gửi?** Dùng test nhiều invocation và assert tính duy nhất, thay vì đòi một UUID được viết sẵn.

Đừng assert trực tiếp `Instant.now()` bằng chính một lần gọi `Instant.now()` khác: độ lệch thời gian gây flaky test và không cho biết payload đúng hay không.

### 8.6. Bất đồng bộ và reactive

Nếu service publish event trong `CompletableFuture`, Reactor hoặc listener, một `verify` ngay lập tức có thể chạy **trước** khi async task phát thông điệp. Cần:

- Điều khiển executor/scheduler trong unit test để hoàn thành tác vụ xác định được.
- Chờ completion stage hoặc dùng test utility phù hợp, không dùng `Thread.sleep` cố định.
- Trong Reactor, kiểm tra cả signal/kết quả bằng `StepVerifier` khi thích hợp và bảo đảm publisher thực sự được subscribe.
- Với message broker, sử dụng integration test có cơ chế chờ/consume và assert payload thật.

Một test pass chỉ vì mock được gọi trên luồng test nhưng event bên ngoài chưa giao thành công không đủ chứng minh hành vi ở network boundary.

## 9. Failure path: cần assert “không gửi gì” và trạng thái đúng

Đếm event thành công thôi chưa đủ. Những nhánh nghiệp vụ không được gửi cũng là một phần outbound contract.

| Tình huống | Kỳ vọng service | Cách kiểm tra |
| --- | --- | --- |
| Command null | Từ chối, không lưu/gửi | `assertThrowsExactly` + `verifyNoInteractions` |
| Quantity bằng 0 | Từ chối, không lưu/gửi | Unit test của phần 4 |
| Giá âm | Từ chối, không lưu/gửi | Input validation + no interactions |
| Repository ném exception | Bề ngoài báo lỗi, không publish | Stub exception + `verifyNoInteractions(publisher)` |
| Repository trả ID không hợp lệ | Không publish event sai | Stub ID 0 + no publish |
| Lưu thành công | Tạo event đầy đủ đúng một lần | Capture payload, assert record |
| Publisher ném lỗi | Tùy hợp đồng: propagate/retry/queue | Assert loại lỗi và chính sách rõ ràng |

Trong service ví dụ, nếu publisher ném exception sau khi repository đã lưu, service cũng ném exception. **Điều đó không mặc nhiên rollback việc lưu**. Unit test với mock không thể đảm bảo tính atomic giữa database và broker. Một kiến trúc cần bảo đảm “không mất event sau commit” thường xem xét **transactional outbox**, retry idempotent, hoặc giao thức giao nhận riêng. Lúc đó cần integration test đối với transaction, outbox record và consumer để xác nhận luồng bền vững.

Một lỗi dễ bị bỏ qua: test no-interaction chỉ đúng khi nó bảo vệ yêu cầu thực. Nếu service được phép gửi audit event khi validation thất bại, `verifyNoInteractions(allMocks)` có thể quá nghiêm ngặt. Hãy phân biệt **outbound nghiệp vụ bị cấm** với **audit/logging được cho phép**.

## 10. Test double nào phù hợp: mock, stub, spy hay recording fake?

| Loại | Mục đích | Trong bài này |
| --- | --- | --- |
| **Stub** | Trả dữ liệu đã biết để điều khiển luồng | `when(repository.save(...)).thenReturn(new SavedOrder(501))` |
| **Mock** | Ghi nhận và verify tương tác | `publisher` để capture event |
| **Spy** | Bao quanh đối tượng thật, vẫn có thể quan sát/stub một phần | Chỉ dùng khi thực sự cần hành vi thật cùng observation |
| **Recording fake** | Implementation đơn giản lưu các sự kiện nhận được vào danh sách | Có thể assert toàn bộ `sentEvents` như output |

Một cách hữu ích là thay mock publisher bằng **recording fake**. Nó cho phép so sánh cả danh sách event và thường làm rõ “payload gửi ra” là một output có thể quan sát.

Ví dụ class recording fake chạy được nếu thêm vào source `src/test/java/com/example/outbound/RecordingPublisher.java`:

```java
// RecordingPublisher.java
package com.example.outbound;

import java.util.ArrayList;
import java.util.List;

final class RecordingPublisher implements OrderEventPublisher {
    private final List<OrderCreatedEvent> events = new ArrayList<>();

    @Override
    public void publish(OrderCreatedEvent event) {
        events.add(event);
    }

    List<OrderCreatedEvent> events() {
        return List.copyOf(events);
    }
}
```

Có thể thêm test method sau vào `CheckoutServiceTest` (nằm trong đúng class, cần static JUnit `assertEquals` và Mockito `when` đã được import):

```java
@Test
void recordingFakeExposesWholeOutboundEvent() {
    RecordingPublisher recording = new RecordingPublisher();
    OrderRepository stubRepository = draft -> new SavedOrder(501L);
    CheckoutService concreteService =
            new CheckoutService(stubRepository, recording);

    concreteService.place(validCommand());

    assertEquals(
            java.util.List.of(new OrderCreatedEvent(
                    501L, "buyer@example.test", "SKU-9",
                    3, new BigDecimal("37.50"), "USD")),
            recording.events());
}
```

Test này không dùng `@Mock publisher` mà kiểm tra recording fake, tức **output list** sau khi gọi service. Việc chọn mock/captor hay fake là quyết định thiết kế; cả hai đều có thể assert payload đúng. Recording fake không thay thế một Kafka producer hoặc SMTP server thật và không xác nhận serialization/giao nhận ngoài tiến trình.

## 11. Tổ chức assertion theo ranh giới khi test Spring Boot

**Unit test (không Spring context):** Dùng Mockito/recording fake để xác minh service đã xây dựng và chuyển đúng command/event/entity tới dependency. Tốc độ nhanh, lỗi dễ định vị. Ví dụ `CheckoutServiceTest` đã chứng minh transformation của service.

**Spring slice test:** Nếu kiểm tra controller với `@WebMvcTest` và service bị mock, assert HTTP request binding và response JSON/status; điều đó **không chứng minh** service thật gửi event đúng. Muốn kiểm tra service outbox dùng class thật hoặc integration test tương ứng.

**Integration test:** Dựng adapter thật hoặc test double ở network boundary (ví dụ HTTP stub server) để assert serialized JSON, headers, queue topic, database row/outbox record và mapping của adapter. Nếu unit test đã xác minh record chứa total 37.50, integration test có thể xác minh chính record đó được chuyển thành đúng JSON/Avro message.

**E2E/system test:** Gửi request từ client ngoài vào ứng dụng đang chạy, sau đó quan sát trạng thái hệ thống/consumer thật. Lưu ý retries, duplicate delivery và eventual consistency.

Sơ đồ ranh giới:

```text
                     UNIT TEST
PlaceOrderCommand ──► CheckoutService (THẬT)
                           │
             ┌─────────────┴────────────────┐
             ▼                              ▼
      OrderRepository MOCK          OrderEventPublisher MOCK
      capture OrderDraft            capture OrderCreatedEvent
             │                              │
       assert draft fields           assert event fields
             │                              │
             └─────────────┬────────────────┘
                           ▼
                 assert OrderReceipt

                INTEGRATION TEST
CheckoutService ──► repository adapter ──► DB test
               └──► publisher adapter  ──► broker/HTTP fake or real
                           │
               assert saved row and serialized message
```

Không nên kết luận “event đã tới Kafka” chỉ từ `verify(publisher).publish(...)` trên Mockito mock. Test ở mức nào phải chứng minh ranh giới tương ứng.

## 12. Mutation thinking: kiểm tra chất lượng test bằng thay đổi sai

Sau khi viết test, hãy tự hỏi: **“Nếu code gửi dữ liệu sai thì assertion nào sẽ đỏ?”** Có thể thử thay đổi sai có chủ đích trên bản làm việc tạm rồi khôi phục:

| Lỗi giả định trong service | `times(1) + any()` | Assertion nội dung |
| --- | --- | --- |
| Gửi email người nhận chưa `trim()` | Vẫn có thể pass | Fail: email kỳ vọng không khớp |
| Đổi quantity `3` thành `1` | Vẫn có thể pass | Fail: quantity sai |
| Gửi total `0.00` | Vẫn có thể pass | Fail: total sai |
| Dùng ID `0` thay vì `501` | Vẫn có thể pass | Fail: orderId sai |
| Gửi `EUR` thay vì `USD` | Vẫn có thể pass | Fail: currency sai |
| Không gửi event | Fail | Fail |
| Gửi hai event | Có thể fail nếu verify kiểm đếm **tất cả** lần gọi phù hợp | Fail nếu ràng buộc đúng một event |
| Không publish khi repository lỗi | `verifyNoInteractions` hỗ trợ | Negative contract được bảo vệ |

Không cần đợi một mutation-testing framework mới sử dụng được tư duy này. Nhưng nếu có nhiều logic, công cụ như PIT có thể giúp tìm assertion yếu. Kết quả mutation score cần được diễn giải cùng với hợp đồng thực, vì không phải biến đổi máy sinh nào cũng tương ứng lỗi nghiệp vụ có ý nghĩa.

**Một phép thử tối thiểu:** nếu thay `"USD"` trong code thành `"EUR"` mà test đếm lời gọi vẫn xanh, test chưa bảo vệ currency. Nếu expected payload được assert độc lập, nó sẽ fail.

## 13. Những lỗi Mockito phổ biến

### Lỗi A. Chỉ test lại stubbing

```java
when(repository.save(any())).thenReturn(new SavedOrder(501L));
assertEquals(new SavedOrder(501L),
        repository.save(new OrderDraft(
                "buyer@example.test", "SKU-9", 3,
                new BigDecimal("37.50"))));
```

Đoạn minh họa này chỉ xác minh mock trả giá trị đã stub, **không gọi service**; nó không test use case. Đặt stub để điều khiển upstream, **gọi service**, rồi verify outgoing payload và return value.

### Lỗi B. Captor đặt trong `when(...)`

Mockito khuyến nghị capture trong **verification** vì nếu method không được gọi, lỗi xuất hiện ngay tại verify và dễ chẩn đoán. Đừng tùy tiện dùng `captor.capture()` làm điều kiện stubbing rồi kỳ vọng nó thay thế assertion outbound.

### Lỗi C. Trộn matcher và raw argument

```java
// Sai nếu dùng matcher cho một tham số nhưng để tham số khác ở dạng raw:
verify(sender).send(eq("buyer@example.test"), "Subject", anyString());

// Đúng: dùng matcher cho toàn bộ các tham số của lời gọi này:
verify(sender).send(
        eq("buyer@example.test"),
        eq("Subject"),
        anyString());
```

Đoạn này chỉ minh họa với method `send(String,String,String)` giả định. Nếu không dùng matcher, truyền cả ba expected theo cách so sánh giá trị trực tiếp cũng được.

### Lỗi D. Assert giá trị capture nhưng không kiểm tra ngữ cảnh

Một event có amount đúng nhưng orderId hoặc recipient sai vẫn là event sai. Đừng chỉ assert một field “dễ pass”. Chọn các trường mà consumer dùng để quyết định hành vi và những bất biến business quan trọng.

### Lỗi E. Oververify mọi chi tiết

Nếu yêu cầu chỉ là phát đúng `OrderCreatedEvent`, đừng verify số lần service gọi formatter/private mapper hoặc thứ tự từng bước nội bộ không quan trọng. Test nên tồn tại qua refactor hợp lệ mà không cần sửa kỳ vọng.

### Lỗi F. Không kiểm tra invocation dư thừa

`verify(publisher).publish(expectedEvent)` có thể pass ngay cả khi có thêm event khác. Với contract đúng một event, kiểm soát **toàn bộ lời gọi outbound** bằng captor/all-values hoặc `verifyNoMoreInteractions` sau những invocation đã verify.

### Lỗi G. Test không đợi async completion

Khi thao tác publish được lên lịch bất đồng bộ, verify quá sớm sẽ fail ngẫu nhiên. Hãy kiểm soát completion hoặc dùng công cụ chờ điều kiện; không chữa bằng sleep tùy tiện.

## 14. Cách chạy và kỳ vọng

Trong thư mục `outbound-payload-test` có `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=CheckoutServiceTest test
```

Ở dự án mẫu trước khi thêm `RecordingPublisher` test bổ sung, `CheckoutServiceTest` có **4 phương thức `@Test`**. Nếu thêm method recording fake ở phần 10, có **5 phương thức**. Kết quả lệnh Maven có thể in `BUILD SUCCESS` khi toàn bộ assertion pass; số task, thời gian và log không có stdout cố định. Bài này không có `System.out.println`.

Để đọc kết quả, kiểm tra report Surefire trong `target/surefire-reports/` và chú ý số test đã chạy, skipped và failed. **Không dùng một dòng “build success” làm bằng chứng payload đúng nếu test chỉ chứa `any()`/`times(1)`.** Assert và expected mới quyết định ý nghĩa bộ test.

Nếu muốn kiểm tra event sai thực sự bị phát hiện, thay thử (trên nhánh làm việc tạm, sau đó hoàn nguyên) chuỗi currency trong `CheckoutService`:

```java
// Dòng đang đúng trong mã ví dụ:
publisher.publish(new OrderCreatedEvent(
        saved.id(), email, sku,
        command.quantity(), total, "USD"));

// Thử sai có chủ đích:
publisher.publish(new OrderCreatedEvent(
        saved.id(), email, sku,
        command.quantity(), total, "EUR"));
```

Sau đó test `sendsCorrectBusinessPayloadAfterSaving` phải fail tại so sánh event. Hai phiên bản trên chỉ là minh họa để đánh giá assertion, **không để lại code sai trong ứng dụng**.

## 15. Checklist cho code review

- [ ] Đã chỉ rõ **outbound boundary** (repository, publisher, email, HTTP, audit, payment).
- [ ] Test gọi **unit thật**; không chỉ gọi stub/mock rồi assert chính stubbing.
- [ ] Expected xuất phát từ quy tắc nghiệp vụ và test fixture độc lập.
- [ ] Đã assert các field quan trọng: recipient, ID, amount, currency, quantity, status, correlation key theo contract.
- [ ] Các biến đổi trim/normalize/map/round đã có ví dụ cụ thể với expected độc lập.
- [ ] Nếu contract yêu cầu một event, đã kiểm soát **đúng một event**, không để invocation dư lọt.
- [ ] Nếu có nhiều event, đã dùng `getAllValues()` và so sánh đầy đủ tập/thứ tự tùy yêu cầu.
- [ ] Nếu không được gửi khi invalid/failure, đã test **no side effect**.
- [ ] Không buộc test phụ thuộc ID/timestamp ngẫu nhiên hay thứ tự không thuộc contract.
- [ ] Ưu tiên immutable event; hiểu `ArgumentCaptor` giữ tham chiếu khi dùng mutable object.
- [ ] Nếu async, đã đợi và quan sát kết quả đúng cách.
- [ ] Phân biệt “đã gọi mock” với “adapter thật đã serialize/giao message hoặc DB đã commit”.
- [ ] Có thể chỉ ra ít nhất một dữ liệu gửi sai khiến test thất bại.

## 16. Câu hỏi tự đánh giá

**1.** `verify(emailSender, times(1)).send(any())` có chứng minh email đã gửi đúng địa chỉ không?  
**Trả lời:** Không. Nó chỉ chứng minh một lời gọi phù hợp; cần assert recipient (và nội dung quan trọng).

**2.** Khi nào chỉ `verifyNoInteractions(publisher)` là đủ?  
**Trả lời:** Khi hành vi cần bảo vệ là **tuyệt đối không gửi** ở một nhánh cụ thể, ví dụ input không hợp lệ. Nếu service có nhiều collaborator và chỉ publisher bị cấm tương tác, chỉ kiểm tra publisher.

**3.** Dùng `verify(publisher).publish(new OrderCreatedEvent(...))` có hợp lý không?  
**Trả lời:** Có nếu event là record/value object với equality đúng và expected độc lập. Cần kiểm soát invocation dư nếu contract yêu cầu tổng cộng chỉ một event.

**4.** Một test kiểm tra đúng total 37.50 nhưng không kiểm tra currency có đủ không?  
**Trả lời:** Không nếu consumer yêu cầu currency đúng; 37.50 USD và 37.50 EUR có ý nghĩa khác nhau.

**5.** `ArgumentCaptor#getValue()` và `getAllValues()` khác nhau thế nào?  
**Trả lời:** `getValue()` lấy giá trị capture cuối; `getAllValues()` lấy danh sách toàn bộ đối số đã capture để kiểm tra nhiều invocation.

**6.** Vì sao không thể tuyên bố message đã được Kafka nhận chỉ từ Mockito `verify`?  
**Trả lời:** Mock chỉ ghi nhận lời gọi tại boundary unit, không thực thi producer serialization, network, broker acknowledgement hoặc consumer. Cần integration/system test cho phần đó.

**7.** Vì sao payload immutable hữu ích?  
**Trả lời:** Event không bị sửa sau invocation, giúp kết quả capture và hợp đồng giao tiếp ổn định, giảm rủi ro test quan sát sai trạng thái của đối tượng mutable.

**8.** Nếu repository ném exception, điều gì nên được assert?  
**Trả lời:** Lỗi/handling đúng contract và **không publish event**; trong ví dụ kiểm tra `assertThrowsExactly` + `verifyNoInteractions(publisher)`.

## 17. Tài liệu tham khảo

- Mockito – `ArgumentCaptor`: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/ArgumentCaptor.html
- Mockito – verification và matchers: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html
- JUnit 5 User Guide – Writing tests/Assertions: https://junit.org/junit5/docs/current/user-guide/
- Spring Boot 3.5 – Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/index.html
- AssertJ Core Documentation: https://assertj.github.io/doc/

**Điểm cần nhớ:** Đừng dừng lại ở “đã gọi một lần”. Với outbound side effect, test phải chứng minh **dữ liệu gì đã rời khỏi unit, dữ liệu có đúng nghiệp vụ không, và trong những tình huống nào không được gửi**. Khi cần chứng minh message đã đi tới hệ thống bên ngoài, bổ sung integration test đúng ranh giới, vì unit test với mock chỉ quan sát lời gọi.