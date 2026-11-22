# Chọn test double ở đúng ranh giới thay vì mock toàn bộ chuỗi nghiệp vụ

Trong ứng dụng Spring Boot, một yêu cầu có thể đi qua controller, application service, domain policy, repository, HTTP client và message broker. Mockito cho phép giả lập rất nhiều đối tượng, nhưng **mock được không có nghĩa nên mock**. Nếu test thay mọi thành phần bằng `when(...).thenReturn(...)`, nó có thể xanh dù thuật toán tính tiền, kiểm tra điều kiện, quyết định trạng thái hay phối hợp nghiệp vụ thật đều sai.

Nguyên tắc trung tâm của bài:

> **Giữ nguyên phần logic đang cần chứng minh; thay bằng test double ở ranh giới mà bài test không cần hoặc không thể chạy thành phần thật một cách an toàn, nhanh và xác định.**

Ranh giới đó thường là một **outbound port** (cổng thanh toán, gửi email, clock, repository, HTTP client, message producer), chứ không phải mọi method xuất hiện trong chuỗi gọi. Ngược lại, khi mục tiêu chỉ là hợp đồng HTTP của một controller, việc mock application service ở **ranh giới của MVC slice** lại là lựa chọn hợp lý. Cùng một object có thể là **SUT** (*system under test*) trong bài test này và là dependency ngoài phạm vi trong bài test khác.

Bài viết đi từ khái niệm, ma trận quyết định đến ví dụ Java 17+, JUnit Jupiter 5, Mockito và Spring Boot 3.4+/Spring Framework 6.2+; hướng dẫn kiểm thử logic checkout thật với payment gateway giả, kiểm thử Spring bean override, MVC slice, lỗi thiết kế và cách review.

## 1. Học được gì sau bài?

Bạn sẽ có thể:

- Giải thích khác nhau giữa **SUT, collaborator, inbound boundary và outbound boundary**.
- Phân biệt **dummy, stub, fake, mock, spy** và chọn theo nhu cầu thực tế.
- Chỉ ra vì sao mock cả policy, service, repository rồi assert dữ liệu giả dễ tạo test giá trị thấp.
- Viết **unit test chạy logic domain và orchestration thật**, chỉ giả lập giao tiếp ngoài phạm vi.
- Dùng **state assertion** (giá trị, bản ghi, trạng thái) kết hợp **interaction assertion** có chủ đích.
- Sử dụng `@MockitoBean` để thay bean đúng phạm vi trong Spring TestContext, không nhầm với `@Mock` của Mockito.
- Phân biệt việc mock service trong `@WebMvcTest` với việc mock chính service trong một test được quảng cáo là kiểm tra nghiệp vụ.
- Xác định khi nào fake in-memory là đủ, khi nào cần database/HTTP/broker thật qua integration hoặc contract test.
- Nhận diện rủi ro khi bean override bỏ qua AOP, khi test cache context hoặc khi test double không tuân thủ contract.

## 2. SUT là gì và “đúng ranh giới” nghĩa là gì?

**SUT** là phần hệ thống mà một bài test **cần chứng minh tính đúng**. Nó có thể là một class, nhóm class, endpoint hoặc một workflow rộng. **Collaborator** là thứ SUT gọi tới để hoàn thành nhiệm vụ.

Ví dụ checkout:

```text
                         HTTP request
                              |
                              v
                     CheckoutController
                         (inbound)
                              |
                              v
                      CheckoutService
                      /       |      \
                     v        v       v
                 Catalog   DiscountPolicy    ... business rules
                    \         /
                     v       v
                    amount + discount
                              |
                  +-----------+-----------+
                  |                       |
                  v                       v
             PaymentGateway             OrderStore
             (outbound port)            (outbound port)
                  |                       |
                  v                       v
           external payment API     SQL / persistence adapter
```

Nếu mục tiêu là “hội viên được giảm 10%, số tiền gửi tới cổng thanh toán đúng và hóa đơn được lưu sau khi thanh toán thành công”, thì **Catalog, DiscountPolicy và CheckoutService là logic thật cần chạy**. `PaymentGateway` có thể là mock; `OrderStore` có thể là fake in-memory nếu test này không nhằm chứng minh SQL.

Nếu mục tiêu là “HTTP POST parse JSON vào `CheckoutCommand` rồi trả HTTP 200 với JSON thích hợp”, controller/MVC là SUT. Trong `@WebMvcTest`, `CheckoutService` có thể được mock vì domain calculation nằm ngoài phạm vi của test HTTP mapping. Các test service riêng vẫn phải bảo vệ tính toán thật.

**Không có ranh giới đúng cho mọi bài test.** Ranh giới phụ thuộc vào **hợp đồng mà bài test cam kết bảo vệ**. Đó là lý do nên viết câu “Test này sẽ thất bại nếu ...” trước khi quyết định mock gì.

## 3. Năm kiểu test double và mục đích thực sự

Test double là đối tượng thay một cộng tác viên trong phép kiểm thử. Thuật ngữ thường dùng:

| Loại | Ý nghĩa | Trường hợp thích hợp | Rủi ro nếu lạm dụng |
|---|---|---|---|
| **Dummy** | Đối tượng chỉ cần tồn tại để truyền tham số, test không dùng hành vi của nó | Constructor bắt buộc một phụ thuộc không liên quan tới ca kiểm thử | Che việc class có quá nhiều dependency |
| **Stub** | Cung cấp kết quả xác định cho một lời gọi | HTTP client trả một phản hồi cố định, chính sách tỷ giá bên ngoài trả một giá trị | Dữ liệu quá “đẹp” khiến test không bao phủ biến thể quan trọng |
| **Fake** | Implementation đơn giản nhưng hoạt động được, thường lưu trong bộ nhớ | In-memory order store, fake clock, fake message sink | Không tái tạo transaction, constraint, concurrency của hạ tầng thật |
| **Mock** | Đối tượng lập trình được; có thể stub kết quả và verify lời gọi | PaymentGateway: kiểm tra số tiền và số lần gọi khi gửi yêu cầu | Test khóa chi tiết tương tác thay vì kết quả đáng bảo vệ |
| **Spy** | Bao quanh đối tượng có logic thật, chỉ thay/quan sát một phần | Legacy code chưa tách dependency, cần giữ một số real method | Method chưa stub có thể chạy thật, tạo side effect và làm test dễ vỡ |

Trong Mockito, từ `mock` thường chỉ object tạo bởi `Mockito.mock` dù ta chỉ dùng nó làm **stub** để trả dữ liệu. Phân biệt thuật ngữ về hành vi kiểm thử không đồng nghĩa bắt buộc thư viện có một class riêng cho từng kiểu.

Ví dụ một test có thể dùng:

```java
PaymentGateway payment = mock(PaymentGateway.class); // Mockito mock
when(payment.charge(216_000L)).thenReturn("tx-001"); // Stubbing
verify(payment).charge(216_000L);                    // Interaction assertion
```

Đây là **đoạn minh họa**; `PaymentGateway` sẽ được định nghĩa đầy đủ ở phần ví dụ. `mock` và `verify` chỉ nên bảo vệ tương tác thực sự là một phần yêu cầu.

## 4. Vì sao mock cả chuỗi nghiệp vụ là một anti-pattern?

Xem một “test” sau:

```java
// PHẢN VÍ DỤ: chỉ kiểm tra kết quả do chính mock trả về.
CheckoutService service = mock(CheckoutService.class);

CheckoutCommand command = new CheckoutCommand("BOOK", 2, true);
CheckoutReceipt expected = new CheckoutReceipt(
        "BOOK", 2, 240_000L, 24_000L, 216_000L, "tx-001");

when(service.checkout(command)).thenReturn(expected);

assertEquals(expected, service.checkout(command));
```

Code test này **không hề chạy `CheckoutService.checkout` thật**. Dù implementation thực không cộng tiền, không giảm giá, quên lưu hóa đơn hoặc luôn ném lỗi, test vẫn có thể xanh vì đã tự bảo Mockito trả đúng `expected`.

Một kiểu khác tinh vi hơn:

```java
// PHẢN VÍ DỤ cho mục tiêu kiểm tra discount:
// Catalog, DiscountPolicy, PaymentGateway và OrderStore
// đều được mock; mọi kết quả nghiệp vụ đã do test quyết định.
when(catalog.unitPriceVnd("BOOK")).thenReturn(120_000L);
when(discountPolicy.discountVnd(240_000L, true))
        .thenReturn(24_000L);
when(paymentGateway.charge(216_000L)).thenReturn("tx-001");
```

Đây là **mẩu minh họa**, các biến chưa được khai báo trong một test độc lập. Nếu SUT là CheckoutService, cấu hình này vẫn chạy orchestration của service nhưng **không chạy quy tắc giảm giá thật**. Khi policy bị sửa thành giảm 5%, test vẫn có thể xanh vì discount 24.000 được test hard-code. Chỉ nếu **orchestration** (số lần và thứ tự gọi collaborator) là yêu cầu duy nhất, loại test như vậy mới có giá trị phù hợp với phạm vi đó.

**Ba tín hiệu test giá trị thấp:**

1. Test nói “kiểm tra tính tiền” nhưng lập sẵn số tiền trong `when(discountPolicy...).thenReturn(...)`.
2. Assert duy nhất là so sánh với dữ liệu mà test vừa cấu hình trên mock.
3. Refactor hợp lệ như gộp hai helper, đổi tên mapper hoặc thay cách phân lớp làm test vỡ dù kết quả nghiệp vụ không đổi.

Test tốt **không bắt buộc cấm mock**; nó dùng mock nơi cần **kiểm soát thế giới bên ngoài**, để phần quyết định quan trọng của nghiệp vụ vẫn được thực thi.

## 5. Chọn double theo tầng: ví dụ ứng dụng checkout

| Tầng | Trong test logic checkout | Trong MVC slice test | Trong integration test persistence |
|---|---|---|---|
| `CheckoutController` | Không cần load | **Thật** | Thường không cần nếu chỉ test repository |
| `CheckoutService` | **Thật** | Có thể mock | Có thể thật nếu test bao cả flow |
| `Catalog` | **Thật**, nếu logic giá là điều cần kiểm tra | Không cần | Thật hoặc fixture rõ |
| `DiscountPolicy` | **Thật** | Không cần | Thật nếu query/transaction liên quan |
| `PaymentGateway` | Mock/fake tại outbound boundary | Không cần vì service mock | Fake/mock hoặc sandbox/contract test riêng |
| `OrderStore` | Fake in-memory nếu không kiểm SQL | Không cần | **Adapter DB thật** và DB test phù hợp |
| Spring bean wiring | Thường không cần | Chỉ MVC context | Thật khi đây là mục tiêu |
| Giao tiếp hạ tầng thực | Không | Không | Chỉ đúng hạ tầng mà test cần bảo vệ |

Một quyết định dựa trên **rủi ro** cũng quan trọng:

- Tính tiền và áp dụng giảm giá sai gây thiệt hại: chạy policy thật, kiểm tra biên và kết quả.
- Cổng thanh toán thật có thể thu tiền: không gọi trong unit test; mock ở outbound interface.
- Truy vấn SQL có thể sai dù fake store pass: cần test riêng với database phù hợp, không lấy fake thay mọi DB test.
- Mapping JSON hoặc validation HTTP có thể sai dù service pass: cần MVC slice test hoặc HTTP integration test.
- Transaction, retry, cache và security Spring AOP có thể không được kích hoạt khi dùng mock: kiểm tra ở integration boundary phù hợp.

## 6. Thiết kế port/adapters để dễ thay đúng chỗ

Về tổ chức mã, một hướng đơn giản là tách:

- **Domain rule / policy**: công thức giá, giảm giá, điều kiện đặt hàng, chuyển trạng thái.
- **Application service**: điều phối một use case và gọi port cần thiết.
- **Outbound port**: interface thể hiện nhu cầu từ phía nghiệp vụ, ví dụ `PaymentGateway.charge(amount)` hoặc `OrderStore.save(receipt)`.
- **Outbound adapter**: implementation gọi HTTP, database, broker, email.
- **Inbound adapter**: controller, REST endpoint, message handler hoặc job.

Đồ thị phụ thuộc:

```text
CheckoutService --> Catalog (real domain logic)
                --> DiscountPolicy (real domain logic)
                --> PaymentGateway [interface] --> HTTP adapter (outside unit test)
                --> OrderStore [interface] ----> SQL adapter (outside unit test)

Unit test:
  new CheckoutService(real Catalog, real DiscountPolicy,
                      mock PaymentGateway, fake OrderStore)

Spring integration test:
  Spring creates real CheckoutService/Catalog/DiscountPolicy
  and replaces PaymentGateway bean only
```

**Tại sao interface hữu ích?** Service không cần biết URL, JDBC, Spring HTTP client hay cách gửi message. Test có thể thay adapter mà không sửa logic nghiệp vụ. Tuy nhiên, **không cần tạo interface cho mọi class**: nếu một class thuần không có hạ tầng bên ngoài, test trực tiếp implementation thường rõ hơn.

## 7. Ví dụ Java 17+ hoàn chỉnh: nghiệp vụ checkout thật, double đúng boundary

Ví dụ chạy được ở project **Spring Boot 3.4+/Spring Framework 6.2+**, Java 17+, JUnit Jupiter 5 và Mockito; phần lớn **unit test không cần Spring context**. Nó mô phỏng:

- Catalog có `BOOK` giá 120.000 VND và `PEN` giá 20.000 VND.
- Thành viên được giảm 10% trên tạm tính; để ví dụ đơn giản, mọi số tiền tính bằng **số nguyên VND kiểu `long`**, và khi không chia hết cho 10 thì phần giảm làm tròn xuống bằng phép chia nguyên. Đây là **quy tắc demo**, không phải quy tắc chung cho mọi hệ thống tiền tệ.
- Service từ chối số lượng không dương hoặc SKU không tồn tại **trước khi gọi payment**.
- PaymentGateway trả mã giao dịch; chỉ **sau khi charge thành công** service lưu hóa đơn qua OrderStore.
- Nếu payment ném lỗi, service không ghi hóa đơn. Trong hệ thống thật còn cần thiết kế idempotency, retry và xử lý kết quả không chắc chắn từ mạng; test đơn giản này không tự chứng minh tính nguyên tử giữa gateway và database.

### 7.1. Cấu trúc file

```text
src/main/java/com/example/checkout/
    CheckoutDemoApplication.java
    CheckoutCommand.java
    CheckoutReceipt.java
    Catalog.java
    DiscountPolicy.java
    PaymentGateway.java
    DemoPaymentGateway.java
    OrderStore.java
    InMemoryOrderStore.java
    CheckoutService.java
    CheckoutController.java

src/test/java/com/example/checkout/
    CheckoutServiceUnitTest.java
    CheckoutSpringBoundaryTest.java
    CheckoutControllerSliceTest.java
```

Các file chính dùng package `com.example.checkout`. `DemoPaymentGateway` là **adapter an toàn chỉ để minh họa bean trong demo**: nó ném lỗi có chủ đích thay vì thực hiện network call, không nên xem như một adapter production đầy đủ.

### 7.2. Boot application

**`src/main/java/com/example/checkout/CheckoutDemoApplication.java`**

```java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CheckoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutDemoApplication.class, args);
    }
}
```

### 7.3. Đầu vào và kết quả của use case

**`src/main/java/com/example/checkout/CheckoutCommand.java`**

```java
package com.example.checkout;

public record CheckoutCommand(
        String sku,
        int quantity,
        boolean member) {
}
```

**`src/main/java/com/example/checkout/CheckoutReceipt.java`**

```java
package com.example.checkout;

public record CheckoutReceipt(
        String sku,
        int quantity,
        long subtotalVnd,
        long discountVnd,
        long totalVnd,
        String paymentReference) {
}
```

Các `record` có `equals`, `hashCode` và accessor theo tên component, nên dễ assert giá trị trong unit test. Việc chọn `long` chỉ để các phép tính demo minh bạch; trong production hãy có money type, currency, giới hạn số và rounding policy theo domain.

### 7.4. Logic catalog và giảm giá thật

**`src/main/java/com/example/checkout/Catalog.java`**

```java
package com.example.checkout;

import org.springframework.stereotype.Component;

@Component
public class Catalog {

    public long unitPriceVnd(String sku) {
        if (sku == null) {
            throw new IllegalArgumentException("sku is required");
        }
        return switch (sku) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 20_000L;
            default -> throw new IllegalArgumentException(
                    "unknown sku: " + sku);
        };
    }
}
```

**`src/main/java/com/example/checkout/DiscountPolicy.java`**

```java
package com.example.checkout;

import org.springframework.stereotype.Component;

@Component
public class DiscountPolicy {

    public long discountVnd(long subtotalVnd, boolean member) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }
        return member ? subtotalVnd / 10 : 0L;
    }
}
```

Cả hai class chứa **quy tắc nghiệp vụ thật**: price lookup, điều kiện SKU, tỉ lệ giảm giá. Trong bài kiểm tra tính tiền, không mock hai class này. Nếu policy sai từ 10% thành 5%, các assertion về số tiền phải **đỏ**.

### 7.5. Hai outbound port và adapter minh họa

**`src/main/java/com/example/checkout/PaymentGateway.java`**

```java
package com.example.checkout;

public interface PaymentGateway {
    String charge(long amountVnd);
}
```

**`src/main/java/com/example/checkout/OrderStore.java`**

```java
package com.example.checkout;

public interface OrderStore {
    void save(CheckoutReceipt receipt);
}
```

**`src/main/java/com/example/checkout/DemoPaymentGateway.java`**

```java
package com.example.checkout;

import org.springframework.stereotype.Component;

@Component
public class DemoPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amountVnd) {
        throw new IllegalStateException(
                "Demo adapter: no real payment gateway configured");
    }
}
```

Adapter này **cố ý không liên lạc mạng**. Nó tồn tại để Boot có bean thực sự cho `PaymentGateway`, và test có thể minh họa **thay đúng bean** bằng `@MockitoBean`. Một hệ thống triển khai thật phải thay nó bằng adapter giao tiếp payment sandbox/production có cấu hình, timeout, bảo mật, idempotency và observability phù hợp.

**`src/main/java/com/example/checkout/InMemoryOrderStore.java`**

```java
package com.example.checkout;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class InMemoryOrderStore implements OrderStore {
    private final List<CheckoutReceipt> saved = new ArrayList<>();

    @Override
    public void save(CheckoutReceipt receipt) {
        saved.add(receipt);
    }

    public List<CheckoutReceipt> receipts() {
        return List.copyOf(saved);
    }
}
```

Đây là **fake persistence** đơn giản. Nó có hành vi thật `save` và `receipts` nên test có thể xác nhận kết quả lưu. Nhưng fake **không thể chứng minh** JPA mapping, unique constraint, index, transaction, lock hay tính đúng của SQL. Test liên quan database phải dùng adapter thật và DB test phù hợp ở một cấp khác.

Trong ví dụ, `InMemoryOrderStore` cũng là một Spring component cho demo để dễ chạy. Với ứng dụng production, nên có adapter repository thật và chỉ đăng ký fake ở test scope hoặc profile phù hợp.

### 7.6. Application service: logic thật cần bảo vệ

**`src/main/java/com/example/checkout/CheckoutService.java`**

```java
package com.example.checkout;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final Catalog catalog;
    private final DiscountPolicy discountPolicy;
    private final PaymentGateway paymentGateway;
    private final OrderStore store;

    public CheckoutService(
            Catalog catalog,
            DiscountPolicy discountPolicy,
            PaymentGateway paymentGateway,
            OrderStore store) {
        this.catalog = catalog;
        this.discountPolicy = discountPolicy;
        this.paymentGateway = paymentGateway;
        this.store = store;
    }

    public CheckoutReceipt checkout(CheckoutCommand command) {
        if (command == null) {
            throw new IllegalArgumentException("command is required");
        }
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        long unitPrice = catalog.unitPriceVnd(command.sku());
        long subtotal = Math.multiplyExact(
                unitPrice, command.quantity());
        long discount = discountPolicy.discountVnd(
                subtotal, command.member());
        long total = Math.subtractExact(subtotal, discount);

        String paymentReference = paymentGateway.charge(total);
        CheckoutReceipt receipt = new CheckoutReceipt(
                command.sku(),
                command.quantity(),
                subtotal,
                discount,
                total,
                paymentReference);

        store.save(receipt);
        return receipt;
    }
}
```

Cần nhìn thấy **điểm tách ranh giới**: mọi bước xác định số tiền đều chạy Java thật. `PaymentGateway` và `OrderStore` là hai giao tiếp ra ngoài có thể thay. Khi `charge` ném lỗi, `store.save` không được gọi, vì lời gọi lưu nằm sau `charge` trong flow thực tế.

`Math.multiplyExact` và `Math.subtractExact` giúp test phát hiện overflow số nguyên qua `ArithmeticException` thay vì âm thầm cuốn vòng. Trong sản phẩm thật vẫn phải quy định rõ trần số tiền, xử lý tình trạng payment đã charge nhưng lưu thất bại và idempotency.

### 7.7. Controller cho ví dụ MVC slice

**`src/main/java/com/example/checkout/CheckoutController.java`**

```java
package com.example.checkout;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/checkouts")
public class CheckoutController {
    private final CheckoutService service;

    public CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping
    public CheckoutReceipt checkout(
            @RequestBody CheckoutCommand command) {
        return service.checkout(command);
    }
}
```

Controller này chỉ nhận JSON, gọi application service và trả result; không có security, validation annotations, exception mapping hay HTTP 201 trong ví dụ. Với một API production, test cần bổ sung các hợp đồng thực sự quy định.

## 8. Unit test quan trọng nhất: mock payment, fake store, chạy business thật

**`src/test/java/com/example/checkout/CheckoutServiceUnitTest.java`**

```java
package com.example.checkout;

import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CheckoutServiceUnitTest {

    @Test
    void calculatesRealRulesBeforeChargingAndSaving() {
        PaymentGateway paymentGateway = mock(PaymentGateway.class);
        InMemoryOrderStore store = new InMemoryOrderStore();

        CheckoutService service = new CheckoutService(
                new Catalog(),
                new DiscountPolicy(),
                paymentGateway,
                store);

        when(paymentGateway.charge(216_000L))
                .thenReturn("tx-001");

        CheckoutReceipt receipt = service.checkout(
                new CheckoutCommand("BOOK", 2, true));

        assertAll("real checkout result",
                () -> assertEquals("BOOK", receipt.sku()),
                () -> assertEquals(2, receipt.quantity()),
                () -> assertEquals(240_000L, receipt.subtotalVnd()),
                () -> assertEquals(24_000L, receipt.discountVnd()),
                () -> assertEquals(216_000L, receipt.totalVnd()),
                () -> assertEquals("tx-001",
                        receipt.paymentReference()));

        assertEquals(List.of(receipt), store.receipts());
        verify(paymentGateway).charge(216_000L);
    }

    @Test
    void rejectsUnknownSkuBeforeExternalCharge() {
        PaymentGateway paymentGateway = mock(PaymentGateway.class);
        InMemoryOrderStore store = new InMemoryOrderStore();

        CheckoutService service = new CheckoutService(
                new Catalog(),
                new DiscountPolicy(),
                paymentGateway,
                store);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout(
                        new CheckoutCommand("MISSING", 2, false)));

        verifyNoInteractions(paymentGateway);
        assertTrue(store.receipts().isEmpty());
    }

    @Test
    void paymentFailureDoesNotSaveReceipt() {
        PaymentGateway paymentGateway = mock(PaymentGateway.class);
        InMemoryOrderStore store = new InMemoryOrderStore();

        CheckoutService service = new CheckoutService(
                new Catalog(),
                new DiscountPolicy(),
                paymentGateway,
                store);

        doThrow(new IllegalStateException("declined"))
                .when(paymentGateway).charge(216_000L);

        assertThrows(IllegalStateException.class,
                () -> service.checkout(
                        new CheckoutCommand("BOOK", 2, true)));

        verify(paymentGateway).charge(216_000L);
        assertTrue(store.receipts().isEmpty());
    }
}
```

**Đây là phần cốt lõi của bài.**

- `new Catalog()` và `new DiscountPolicy()` là **implementation thật**. Thay logic giá hoặc giảm giá sẽ thay kết quả và khiến test phát hiện.
- `PaymentGateway` là **mock outbound port**. Unit test không thu tiền thật, nhưng xác minh số tiền gửi qua boundary.
- `InMemoryOrderStore` là **fake**. Ta assert bản ghi đã được lưu với đúng dữ liệu mà không cần JPA, transaction hay DB server.
- `assertAll` gom các thuộc tính có cùng ý nghĩa của receipt; `verify` xác nhận **đúng một lần** phương thức `charge(216_000L)` được gọi trong kịch bản thành công.
- Trường hợp SKU không hợp lệ xác nhận test **fail trước external boundary**.
- Trường hợp gateway ném lỗi xác nhận không lưu receipt sau thất bại.

**Vì sao không mock `CheckoutService`?** Nó là SUT, chính là thứ phải chạy để test phát hiện bug. **Vì sao không mock `DiscountPolicy`?** Vì giảm giá là một trong những quy tắc được cam kết và có thể kiểm tra nhanh, xác định. **Vì sao mock payment?** Vì charge là tác động bên ngoài, không thuộc phạm vi kiểm chứng tính toán và không an toàn để thực hiện trên hệ thống thật trong unit test.

### 8.1. Test này vẫn chưa chứng minh điều gì?

Nó chưa chứng minh:

- HTTP request/response mapping đúng.
- Bean Spring được quét và inject đúng.
- Adapter payment thật gọi đúng API, timeout, retry, chữ ký xác thực và idempotency.
- Store SQL/JPA thực sự commit hay rollback.
- Thanh toán và lưu hóa đơn có tính atomic; cổng ngoài không thuộc cùng transaction database.

Những khoảng trống này là **lý do bổ sung các test ở boundary tiếp theo**, không phải lý do mock tất cả thành phần.

## 9. Khi nào verify interaction và khi nào assert state?

Có hai loại quan sát thường gặp.

**State/result assertion** nhìn kết quả hoặc trạng thái có ý nghĩa:

```java
assertEquals(216_000L, receipt.totalVnd());
assertEquals(List.of(receipt), store.receipts());
```

**Interaction assertion** nhìn lời gọi tới collaborator:

```java
verify(paymentGateway).charge(216_000L);
```

Trong ví dụ payment gateway là outbound boundary và gọi tiền **một lần** có ý nghĩa, nên `verify` đáng dùng. Nhưng nếu verify mọi lời gọi nội bộ:

```java
// PHẢN VÍ DỤ: test bám call graph thay vì contract.
verify(catalog).unitPriceVnd("BOOK");
verify(discountPolicy).discountVnd(240_000L, true);
verify(mapper).toReceipt(any());
verify(auditHelper).buildText(any());
```

đoạn này (chỉ minh họa, các biến chưa định nghĩa) sẽ dễ vỡ khi refactor dù response và side effects không đổi. `Catalog`, `DiscountPolicy` và mapper trong test ở trên còn là **object thật**, không phải mock để verify. Thay bằng mock chỉ để verify gọi helper là đang làm test phụ thuộc implementation.

**Quy tắc quyết định:** Nếu việc gọi collaborator theo số lần/argument là một **hợp đồng quan trọng** (không charge hai lần, không gửi email khi fail, phát event sau commit), verify nó. Nếu chỉ là chi tiết nội bộ của cách tính, assert kết quả cuối cùng và các side effects quan trọng.

Đừng dựa vào `verifyNoMoreInteractions(...)` ở mọi test theo thói quen: nó có thể làm test vỡ khi thêm một lời gọi harmless. Dùng khi **không được phát thêm request/tác động** là một điều kiện cần bảo vệ.

## 10. Mock vs fake ở outbound port: chọn cái nào?

Với `OrderStore` trong unit test, ta có hai lựa chọn hợp lý:

1. **Mock OrderStore:** `verify(store).save(expectedReceipt)`. Ngắn gọn khi chỉ muốn bảo vệ lời gọi save, hoặc khi store là dependency phức tạp.
2. **Fake OrderStore:** dùng implementation in-memory, gọi `store.receipts()` để kiểm tra trạng thái. Hữu ích khi muốn mô phỏng thao tác read/write đơn giản và test một chuỗi hành động.

Chọn fake khi hành vi của double đủ nhỏ để duy trì. **Không xây một database giả bằng tay** với transaction, locks, filtering, pagination và SQL nếu mục tiêu đã đòi logic giống DB thật. Khi tính đúng phụ thuộc SQL hoặc JPA mapping, chạy test với database thật phù hợp, có fixture và cleanup.

Với `PaymentGateway`, một mock phản hồi `"tx-001"` đủ cho unit test. Nhưng nếu domain logic phải đối phó mạng chậm hoặc mã lỗi phức tạp, có thể dùng một fake/HTTP stub server có hành vi phong phú hơn; đồng thời cần contract/integration test xác minh adapter với giao thức thực tế.

**Fake vẫn có bug:** test xanh với fake sai ngữ nghĩa có thể che bug khi triển khai. Fake cần bám đúng **contract thiết yếu** và được giữ đơn giản; không tự tin nó tái hiện production.

## 11. Bean replacement đúng phạm vi với Spring TestContext

Mockito mock Java thuần:

```java
PaymentGateway gateway = mock(PaymentGateway.class);
```

chỉ tạo object trong test method. Nó **không tự thay** `PaymentGateway` mà `CheckoutService` nhận từ `ApplicationContext`. Nếu bạn chạy `@SpringBootTest` mà chỉ khai báo field `@Mock`/`mock(...)`, service trong Spring có thể vẫn dùng bean thật.

Khi cần kiểm chứng Spring wiring và giữ domain service chạy thật, có thể dùng **`@MockitoBean`** của Spring Framework **6.2+** để thay đúng một bean. Spring Boot **3.4+/3.5** dùng Spring Framework có hỗ trợ annotation này; trong Spring Boot **3.3 trở về trước**, công cụ phổ biến là `@MockBean` của Boot (đã deprecated từ 3.4, không nên tiếp tục mặc định dùng cho project mới).

**Các cơ chế khác nhau:**

| Cơ chế | Thay bean trong Spring context? | Khi nào dùng? |
|---|---|---|
| `Mockito.mock(...)` | Không | Unit test tạo SUT bằng constructor |
| `@Mock` + `MockitoExtension` | Không | Tự khởi tạo mock và inject vào SUT của unit test |
| `@MockitoBean` | Có | Spring context test cần thay một dependency bean bằng Mockito mock |
| `@MockitoSpyBean` | Wrap bean thật | Partial mocking có lý do đặc biệt; chú ý AOP/side effects |
| `@TestConfiguration` + `@Import` | Đăng ký bean test theo cấu hình | Fake/adapter test thực sự, thay vì mock tương tác |
| `@TestBean` (Spring TestContext) | Có | Dùng factory method test thay bean bằng một implementation xác định |
| `@MockBean` (Spring Boot cũ) | Có, ở các phiên bản còn hỗ trợ | Dự án Boot trước 3.4 hoặc giai đoạn migration |

Không dùng `@Primary` hoặc `spring.main.allow-bean-definition-overriding=true` như một “mẹo” bắt mọi test vượt lỗi trùng bean. Chúng có tác động khác nhau tới đăng ký bean và có thể che cấu hình sai. Nếu thực sự cần override, chọn cơ chế chính thức phù hợp và để lỗi xuất hiện khi bean không tồn tại/mơ hồ.

### 11.1. Phân biệt REPLACE và REPLACE_OR_CREATE

Spring Framework `@MockitoBean` mặc định dùng chiến lược **REPLACE_OR_CREATE**: nếu tìm thấy bean tương ứng, nó thay; nếu không, có thể tạo mới mock. Với một test có mục tiêu xác nhận **bean đã tồn tại và cần được thay**, có thể dùng:

```java
@MockitoBean(enforceOverride = true)
PaymentGateway gateway;
```

`enforceOverride = true` yêu cầu **REPLACE** và sẽ thất bại nếu không có bean đích phù hợp. Nó giúp tránh trường hợp test pass nhờ tự thêm mock cho dependency mà production configuration thực ra thiếu.

Nếu một MVC slice cố ý **không nạp CheckoutService thật**, dùng `@MockitoBean` với giá trị mặc định là hợp lý để cung cấp mocked collaborator cho controller. Ở đó tạo bean mock mới là điều đã được thiết kế.

**Lưu ý:** bean override cần xác định bean đích theo type/name/qualifier. Nếu có nhiều bean cùng type, dùng `@Qualifier` hoặc tên rõ ràng; không giả định framework sẽ đoán đúng adapter nào để thay.

## 12. Ví dụ Spring Boot: thay đúng PaymentGateway bean, giữ service thật

Ví dụ này kiểm tra `ApplicationContext` đã tạo `Catalog`, `DiscountPolicy` và `CheckoutService`, sau đó **chỉ thay PaymentGateway**. Không gọi demo gateway thật, không mở network.

**`src/test/java/com/example/checkout/CheckoutSpringBoundaryTest.java`**

```java
package com.example.checkout;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
        classes = CheckoutDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CheckoutSpringBoundaryTest {

    @Autowired
    CheckoutService service;

    @Autowired
    InMemoryOrderStore store;

    @MockitoBean(enforceOverride = true)
    PaymentGateway paymentGateway;

    @Test
    void retainsRealBusinessBeansAndReplacesOnlyGateway() {
        when(paymentGateway.charge(216_000L))
                .thenReturn("tx-spring");

        CheckoutReceipt receipt = service.checkout(
                new CheckoutCommand("BOOK", 2, true));

        assertAll("Spring-managed checkout",
                () -> assertEquals(240_000L,
                        receipt.subtotalVnd()),
                () -> assertEquals(24_000L,
                        receipt.discountVnd()),
                () -> assertEquals(216_000L,
                        receipt.totalVnd()),
                () -> assertEquals("tx-spring",
                        receipt.paymentReference()));

        assertEquals(List.of(receipt), store.receipts());
        verify(paymentGateway).charge(216_000L);
    }
}
```

**Tại sao `enforceOverride=true` hợp lệ ở đây?** `DemoPaymentGateway` là một bean đã được khai báo bằng `@Component` và implement `PaymentGateway`. `@MockitoBean` thay bean đó, không cần tạo một bean mới để vá cấu hình thiếu. `CheckoutService` vẫn là Spring bean thật, nên wiring từ context được kiểm tra.

Test có một method để ví dụ không phải quản lý cleanup trạng thái singleton của `InMemoryOrderStore` giữa nhiều test methods. Nếu suite lớn dùng store fake stateful và cache context, phải có chiến lược isolation/reset phù hợp; **`@MockitoBean` không tự reset tất cả bean khác**.

### 12.1. Phạm vi `@MockitoBean` và Spring AOP

Spring TestContext bean override kiểu **REPLACE**/`REPLACE_OR_CREATE` thay bean bằng mock instance trực tiếp. Bean mock thường **không còn Spring AOP advice** vốn áp dụng trên bean cũ (ví dụ `@Transactional`, `@Cacheable`, `@Retryable`, method security).

Điều này phù hợp khi bean được thay là **outbound gateway không thuộc điều cần kiểm tra**. Nhưng nếu bạn mock **chính service nghiệp vụ** rồi kết luận transaction/retry/security của service chạy đúng, test sẽ sai mục tiêu: behavior của proxy/logic thật đã bị thay.

`@MockitoSpyBean` có cơ chế wrap bean thật và có thể vẫn nằm sau Spring AOP proxy. Điều đó không có nghĩa spy luôn an toàn: `when(spy.method())` có thể chạy method thật trong lúc stubbing; dùng `doReturn`/`doThrow` khi phù hợp, và kiểm tra ảnh hưởng của proxy/cache/retry.

### 12.2. Vì sao không dùng full Boot context cho mọi unit test?

`@SpringBootTest` khởi động context và có chi phí: bean initialization, configuration, component scanning và cache management. Để kiểm tra phép giảm 10% từ subtotal, `new DiscountPolicy()` + JUnit là đủ. Chỉ giữ vài Spring context test có mục tiêu bảo vệ wiring/configuration quan trọng và bean replacement.

## 13. MVC slice: khi mock application service lại là đúng boundary

Có thể nghe mâu thuẫn: “Đừng mock CheckoutService”, rồi lại “Hãy mock CheckoutService trong `@WebMvcTest`”. Điểm khác nằm ở **SUT**.

Trong MVC slice test, ta không kiểm tra tính tiền. Ta kiểm tra **routing, JSON binding/serialization và HTTP response** của controller. Do đó, collaborator `CheckoutService` nằm ngoài phạm vi và có thể được mock. Những quy tắc nghiệp vụ vẫn được bảo vệ bởi unit/context test khác.

**`src/test/java/com/example/checkout/CheckoutControllerSliceTest.java`**

```java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CheckoutController.class)
class CheckoutControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CheckoutService service;

    @Test
    void mapsJsonCommandAndReturnsReceipt() throws Exception {
        CheckoutCommand command =
                new CheckoutCommand("BOOK", 2, true);
        CheckoutReceipt receipt = new CheckoutReceipt(
                "BOOK", 2, 240_000L, 24_000L, 216_000L,
                "tx-http");

        when(service.checkout(command)).thenReturn(receipt);

        mvc.perform(post("/api/checkouts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku": "BOOK",
                                  "quantity": 2,
                                  "member": true
                                }
                                """))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.sku").value("BOOK"),
                        jsonPath("$.subtotalVnd").value(240_000),
                        jsonPath("$.discountVnd").value(24_000),
                        jsonPath("$.totalVnd").value(216_000),
                        jsonPath("$.paymentReference").value("tx-http"));

        verify(service).checkout(command);
    }
}
```

**Giải thích:**

- `@WebMvcTest(CheckoutController.class)` dựng Spring MVC slice, không nạp toàn bộ service/repository như full application context.
- `@MockitoBean` cung cấp mocked `CheckoutService` cho constructor của controller. Vì service thật không nhất thiết tồn tại trong MVC slice, không đặt `enforceOverride=true` ở đây.
- `MockMvc` xác minh endpoint nhận JSON record và trả JSON. Test không gọi payment, không đọc catalog và không giả vờ đã kiểm tra công thức giảm giá.
- `verify(service).checkout(command)` giúp phát hiện controller truyền sai input, nếu mapping của record là một phần điều cần kiểm tra.

**Giới hạn:** nếu dự án có Spring Security hoặc cấu hình HTTP đặc biệt, cần fixture/security setup phù hợp để test phản ánh API thực tế. Không tắt authentication/CSRF tùy tiện chỉ để test xanh. Với đoạn demo này không có Spring Security dependency.

Trong MVC slice, **mock đúng service là boundary đúng**. Trong unit test `CheckoutService`, **mock chính service là phá mục tiêu**. Cùng một kỹ thuật, giá trị khác nhau theo phạm vi.

## 14. Bean override theo phiên bản Spring Boot

Không sao chép một annotation thiếu bối cảnh version:

| Dự án | Annotation thường dùng cho mock Spring bean | Import |
|---|---|---|
| Spring Boot 3.3 trở về trước | `@MockBean` của Spring Boot | `org.springframework.boot.test.mock.mockito.MockBean` |
| Spring Boot 3.4/3.5, Spring Framework 6.2+ | **Ưu tiên `@MockitoBean`** | `org.springframework.test.context.bean.override.mockito.MockitoBean` |
| Spring Boot 4.x / Spring Framework 7.x | **`@MockitoBean`** và cơ chế mới tương thích | Spring TestContext `MockitoBean`; kiểm tra module test dependency đúng version |

Trong Spring Boot 3.4, `@MockBean` và `@SpyBean` đã bị **deprecated** để chuyển sang `@MockitoBean` và `@MockitoSpyBean` của Spring Framework. Đây không phải thay import cơ học 100%: có khác biệt về vị trí hỗ trợ annotation, lựa chọn bean và behavior override. Cần kiểm tra test sau migration, nhất là nếu đặt `@MockBean` trên `@Configuration` hoặc dùng nhiều bean cùng type.

Với dự án Boot 3.3, đoạn `CheckoutSpringBoundaryTest` ở mục 12 có thể cần thay `@MockitoBean` bằng `@MockBean` và bỏ thuộc tính `enforceOverride` vì API cũ không có thuộc tính đó. Đây là **lựa chọn version**, không được dùng hai annotation xen kẽ trong một project khi chưa hiểu cơ chế.

Khi cần fake thay vì Mockito mock, có thể dùng `@TestConfiguration` và `@Import` để cung cấp implementation test; với Spring Framework 6.2+ có `@TestBean` để override từ factory method. Cần chú ý bean name, qualifier và scope. Không dùng cấu hình override rộng khiến mất bean production quan trọng mà test định bảo vệ.

## 15. Chọn mock hoặc fake ở ranh giới nào của ứng dụng thật?

Một số tình huống điển hình:

### 15.1. Dịch vụ gọi REST ngoài

**Mục tiêu:** tính toán dữ liệu và gửi request với amount, currency, idempotency key hợp lệ. Ở unit test, mock/fake một `PaymentGateway` interface. Ở adapter contract test, dùng mock HTTP server để xác minh JSON, headers, status mapping và timeout; ở một số integration test được phép, dùng sandbox API.

**Không nên:** mock cả `CheckoutService` rồi assert hóa đơn đã trả về từ mock. Điều đó bỏ qua luồng gửi request thật lẫn nghiệp vụ.

### 15.2. Email và notification

**Mục tiêu:** không gửi email khi giao dịch thất bại; gửi đúng một notification khi hoàn tất. Dùng fake/spy của `NotificationPort` ở outbound boundary, assert message hoặc verify call một lần. Không gọi SMTP production.

**Không nên:** mock handler chính rồi `verify(handler).handle(...)` nếu test có mục tiêu bảo vệ logic quyết định thông báo.

### 15.3. Repository và DB

**Mục tiêu:** kiểm tra status transition và quyết định có lưu hay không. Fake repository đơn giản hoặc mock save/load đủ cho unit test.

**Mục tiêu khác:** kiểm tra query, mapping, unique constraint, transaction hoặc optimistic locking. Dùng repository adapter thật với database test phù hợp; fake in-memory không bảo vệ SQL.

### 15.4. Thời gian, UUID và randomness

Business logic hết hạn voucher cần thời gian xác định. Thay đồng hồ thật bằng **`Clock.fixed(...)`** và inject `Clock` vào domain service, thay vì dùng `Thread.sleep`. UUID hoặc random nếu ảnh hưởng kết quả nên được inject qua generator có thể điều khiển được. Đây là **control boundary**, không phải lý do mock cả policy.

### 15.5. Message broker / async worker

Test event business có thể dùng fake `EventPublisher` để ghi event được phát; adapter test riêng xác minh serialization, partition key, delivery/retry semantics với broker kiểm soát. Nếu yêu cầu nghiệp vụ liên quan sau-commit hoặc eventual consistency, test đúng boundary transaction/async thay vì kết luận từ một `verify(publisher)` đơn lẻ.

### 15.6. Spring Security và AOP

Nếu yêu cầu là quyền truy cập HTTP, transaction rollback hoặc retry advice, đừng mock chính bean/proxy đang thực thi những chính sách ấy. Dùng Spring context test hoặc HTTP/integration test thích hợp và assert kết quả quan sát được. Mock ở port ngoài vẫn có thể cần để cô lập external API.

## 16. Mô hình quyết định cho từng dependency

Đặt năm câu hỏi cho **mỗi dependency** trong test:

1. **Đây có phải logic mà test phải chứng minh không?** Nếu có, chạy implementation thật. Nếu đó là payment adapter external không thuộc phạm vi, mới cân nhắc double.
2. **Phần thật có rẻ và xác định không?** Value object, mapper thuần, discount policy thường rẻ; không cần mock chỉ vì được inject.
3. **Nó có side effect hoặc phụ thuộc môi trường không?** Network, DB, clock, filesystem và broker cần cách ly hoặc setup phù hợp.
4. **Test cần kiểm tra kết quả hay giao thức/tương tác?** Với domain, assert state/value; với outbound API, verify amount, idempotency key, số lần gọi; với SQL, test adapter thật.
5. **Một double có làm mất hành vi quan trọng không?** Nếu mock một bean có `@Transactional` hoặc method tính giá, có thể test không còn đường đi cần bảo vệ.

Bảng quyết định nhanh:

| Nếu ... | Thì ... |
|---|---|
| Class thuần tính số tiền/điều kiện | **Giữ thật**, không cần Spring |
| Service điều phối nghiệp vụ đang được test | **Giữ thật**, inject mock/fake outbound port |
| Controller mapping HTTP trong `@WebMvcTest` | **Giữ controller thật**, mock service ở ranh giới slice |
| Adapter HTTP ngoài cần kiểm serialization | **Giữ adapter thật**, dùng mock HTTP server |
| SQL/mapping DB là hợp đồng | **Giữ repository thật**, dùng DB test |
| Muốn test Spring bean wiring | Boot context thật, override ít bean ngoài phạm vi |
| Legacy class chưa có seam | Spy có chủ đích tạm thời, cân nhắc tách port |
| Double phải mô phỏng quá nhiều protocol/transaction | Xem xét integration test hạ tầng thật thay vì fake tự viết |

## 17. Test double không được “dạy” hệ thống đáp án

Đây là một bẫy điển hình:

```java
// PHẢN VÍ DỤ: expected amount được đưa thẳng vào stub
// của chính business policy mà test muốn chứng minh.
when(discountPolicy.discountVnd(240_000L, true))
        .thenReturn(24_000L);
```

Nếu implementation của `DiscountPolicy` sai, Mockito vẫn trả 24.000. Test có thể đo orchestration nhưng **không đo tính đúng giảm giá**.

Một cấu hình tốt hơn:

```java
DiscountPolicy discountPolicy = new DiscountPolicy();
assertEquals(24_000L,
        discountPolicy.discountVnd(240_000L, true));
```

Rồi trong test checkout, inject **chính object thật đó** để xem toàn use case tính ra 216.000. Đó là hai mức bảo vệ bổ sung nhau: unit test policy cho bảng tình huống, unit test service cho luồng phối hợp, Spring test cho bean wiring.

Đừng chuyển cùng một con số từ `when(...)` sang `assertEquals(...)` mà không để logic thật chạy. “Có assert” chưa đủ; test cần có **đường thực thi không được tạo hoàn toàn bởi test setup**.

## 18. Khi mock nhiều vẫn có thể hợp lý

Không nên áp đặt quy tắc “một test chỉ có một mock”. Có tình huống một use case thật phải gọi ba outbound port: tax API, payment API và event bus. Một unit test orchestration có thể mock cả ba, **miễn logic quyết định và trạng thái cần kiểm chứng vẫn chạy thật**, các hợp đồng ở adapter được bảo vệ bằng test khác.

Ví dụ use case đăng ký tài khoản có:

- `UserPolicy` kiểm tra mật khẩu, email và trạng thái đăng ký.
- `UserRepository` là boundary persistence.
- `EmailGateway` là boundary email.
- `AuditPublisher` là boundary event.

Một unit test có thể dùng fake repository + mock email + fake event publisher, nhưng giữ `UserPolicy` và `RegisterUserService` thật. Số double không phải vấn đề duy nhất; câu hỏi là **chúng thay phần nào của hợp đồng**.

Một test “thin orchestrator” chỉ cần verify các cổng được gọi đúng sequence cũng có giá trị nếu thứ tự là contract. Nhưng đừng dùng nó thay test domain rules, và tránh `InOrder` cho những bước có thể thực hiện đổi thứ tự mà vẫn đúng nghiệp vụ.

## 19. Cách phát hiện “mock toàn chuỗi” trong code review

Tìm các tín hiệu sau:

- Test method tên `calculatesDiscountCorrectly` nhưng `DiscountPolicy` lại là `@Mock`.
- Test method tên `processesOrder` nhưng `CheckoutService` bị `@MockitoBean` thay, còn assertion chỉ kiểm tra JSON đã stub.
- Hầu hết assertion dùng `verify(...)` trên internal helpers, rất ít assert business result.
- Có rất nhiều `when(...).thenReturn(...)` mô tả cả một kịch bản mà production logic gần như không chạy.
- Test phải biết private method, tên lớp mapper, chi tiết DTO trung gian hoặc số lần gọi một helper không thuộc contract.
- Sửa domain rule nhưng test vẫn xanh vì mọi giá trị đã hard-code trong stub.
- Refactor nội bộ không đổi behavior lại làm hàng chục test gãy.
- Fake repository ngày càng tái triển khai phức tạp SQL, transaction, filter và sorting để test xanh.

**Một cách review nhanh:** chỉ vào dòng Act rồi hỏi “đang gọi code thật nào?”. Nếu Act gọi mock SUT, hãy yêu cầu test nêu đúng mục tiêu giới hạn, hoặc viết lại để chạy logic thật. Nếu Act gọi service thật nhưng policy bị mock, hãy xác định test đang bảo vệ orchestration hay domain policy và bổ sung phần còn thiếu.

**Mutation thought experiment:** giả sử sửa giảm giá từ 10% thành 9%. Test nào đỏ? Nếu không có test đỏ nào, khả năng cao suite chưa bảo vệ yêu cầu giảm giá. Tương tự, giả sử xóa lời gọi `OrderStore.save`: test nào phát hiện mất dữ liệu? Trong ví dụ unit test ở mục 8, assertion trên fake store sẽ đỏ.

## 20. Rủi ro của Spring bean override quá rộng

### 20.1. Thay nhầm bean đang cần kiểm tra

Nếu mục tiêu là thử transaction của `CheckoutService` nhưng bạn dùng `@MockitoBean CheckoutService`, transaction advice và method thật có thể không chạy. Test xanh chỉ chứng minh mock trả dữ liệu. Phải giữ bean/proxy cần kiểm chứng thật và thay đúng outbound dependency.

### 20.2. Tạo mock dù production thiếu bean

`@MockitoBean` mặc định có thể **thay hoặc tạo**; nếu module không nạp bean thật vì config sai, test vẫn có thể có mock và chạy. Khi cần phát hiện thiếu wiring, dùng `enforceOverride=true` hoặc một integration test bootstrapping phù hợp.

### 20.3. Nhiều bean cùng type

Nếu có `StripePaymentGateway` và `BankPaymentGateway` cùng implement `PaymentGateway`, annotation theo type có thể mơ hồ. Dùng qualifier/bean name phù hợp với bean mà SUT thật inject; đừng ghi đè đại một bean và hiểu nhầm test đã thay đúng adapter.

### 20.4. Context cache bị phân mảnh

Spring TestContext cache `ApplicationContext` theo cấu hình, bao gồm context customizer từ mock bean definitions. Hai test với các bộ `@MockitoBean` khác nhau có thể cần hai context riêng, tăng thời gian CI. Đừng tạo tổ hợp mock bean biến thiên không cần thiết ở hàng chục full-context tests khi unit/slice test đã đủ.

### 20.5. State của fake bean và test parallel

Một fake singleton như `InMemoryOrderStore` sẽ giữ trạng thái qua nhiều test method nếu chung context. Cần reset fixture an toàn hoặc thiết kế test data độc lập. Tránh cho test chạy song song chỉnh chung một fake mutable nếu không có chiến lược concurrency rõ.

### 20.6. `@MockitoSpyBean` và method thật

Spy không có stub có thể chạy method thật, thậm chí ngay lúc `when(spy.method())`. Với side effect, dùng `doReturn`/`doThrow` thích hợp; tốt hơn là tách boundary để không cần partial mock. Đừng để một spy test biến thành giả lập từng method trong service.

### 20.7. AOP không được kiểm chứng bởi mock

Bean bị `@MockitoBean` thay trực tiếp không còn nhất thiết mang advice của bean gốc. Các thuộc tính `@Transactional`, `@Cacheable`, `@Retryable` hoặc method security trên bean bị thay **không phải đang được thử**. Muốn kiểm tra advice, giữ bean thật, gọi qua proxy và assert effect.

## 21. Làm sao giữ test độc lập, nhanh và đáng tin?

Một chiến lược kiểm thử hợp lý có thể gồm:

1. **Domain unit tests:** chạy value object, policy và use case logic thật với dependency tối thiểu.
2. **Application service unit tests:** fake persistence, mock external API ở outbound port, assert kết quả và tác động cần thiết.
3. **MVC slice tests:** controller thật, service mock nếu chỉ kiểm hợp đồng HTTP, bao gồm validation/serialization/security theo yêu cầu.
4. **Persistence integration tests:** repository thật với DB test phù hợp để kiểm query, mapping và constraint.
5. **External adapter contract tests:** HTTP stub server hoặc sandbox được kiểm soát, xác minh giao thức và error mapping.
6. **End-to-end tests ít nhưng quan trọng:** nối các phần thật cho vài luồng rủi ro cao, chấp nhận chi phí cao hơn và setup cô lập.

Không có một “kim tự tháp” cố định cho mọi sản phẩm. Tỉ lệ mỗi loại test tùy rủi ro, kiến trúc và chi phí bảo trì. Nhưng **bài unit test ít phụ thuộc tài nguyên ngoài** sẽ nhanh và ổn định; các lớp integration/contract test giúp phát hiện những lỗi mà mock/fake không thể nhìn thấy.

### 21.1. Khi nào chọn fake thay vì mock?

- Fake cho trạng thái đọc/ghi ít quy tắc, giúp assert trạng thái.
- Mock cho cổng bên ngoài cần kiểm tra argument/call count hoặc giả lập exception.
- Real collaborator cho logic thuần rẻ và ổn định.
- Testcontainers/DB thật cho hành vi transaction hoặc query mà fake không tái tạo.

### 21.2. Khi nào nên refactor thay vì thêm mock?

Nếu class cần 10 mock để chạy một nhánh đơn giản, có thể nó gánh quá nhiều trách nhiệm. Cân nhắc tách domain policy, application orchestration và outbound adapters; inject qua constructor; dùng interface tại seam hạ tầng. Refactor nhằm cải thiện thiết kế, **không chỉ để làm Mockito hài lòng**.

## 22. Chạy các ví dụ với Gradle và Spring Boot

Các file ở mục 7–13 được thiết kế cho **Java 17+, Spring Boot 3.4+/3.5 với Spring Framework 6.2+, JUnit Jupiter 5, Mockito và Jackson**. Để cả `@SpringBootTest` và `@WebMvcTest` hoạt động, cần các starter trong một Gradle project có **Spring Boot plugin/BOM và repository được cấu hình**.

Ví dụ phần dependency trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn bổ sung cho build đã cấu hình Spring Boot**, không phải một `build.gradle` độc lập. `spring-boot-starter-test` trong nhánh Spring Boot 3.4+/3.5 kéo JUnit Jupiter/Mockito/Spring Test integration thông dụng.

Chạy từ thư mục có Gradle wrapper:

```bash
./gradlew test --tests com.example.checkout.CheckoutServiceUnitTest --tests com.example.checkout.CheckoutSpringBoundaryTest --tests com.example.checkout.CheckoutControllerSliceTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.checkout.CheckoutServiceUnitTest --tests com.example.checkout.CheckoutSpringBoundaryTest --tests com.example.checkout.CheckoutControllerSliceTest
```

Với multi-project Gradle, dùng đường dẫn task thích hợp như `:your-module:test` khi module đó thực sự tồn tại. Package/file path phải khớp những file đã ghi. **Không copy phản ví dụ không đầy đủ thành Java class runnable**; các đoạn ấy chỉ để đối chiếu cách thiết kế.

**Kết quả dự kiến khi cấu hình đúng:**

- `CheckoutServiceUnitTest` có 3 test: checkout hợp lệ, SKU sai không gọi payment, payment fail không lưu receipt.
- `CheckoutSpringBoundaryTest` có 1 test: bean Spring thật tính đúng tiền, Mockito thay PaymentGateway; assertion trên store và gateway đúng.
- `CheckoutControllerSliceTest` có 1 test: HTTP POST JSON được mapping thành command, trả JSON có tổng tiền và paymentReference do service mock cung cấp.
- Tổng cộng ví dụ có **5 test method**; trong môi trường chạy đúng dependency/configuration, Gradle dự kiến báo `BUILD SUCCESSFUL`.
- Không có stdout nghiệp vụ cố định từ các JUnit test; `DemoPaymentGateway` không thực hiện network và không nên bị gọi trong các test này.

Đây là **kết quả mong đợi khi đọc mã**, không phải tuyên bố đã chạy test trên repository thực tế. Có thể kiểm tra báo cáo tại `build/reports/tests/test/index.html` và dữ liệu XML tại `build/test-results/test/` của module tương ứng.

### 22.1. Nếu test không khởi động được context

Một số hướng kiểm tra:

- `@MockitoBean` phải có trong version Spring Test đang dùng; với Boot 3.3 cần API cũ hoặc nâng cấp.
- `@SpringBootTest(classes=CheckoutDemoApplication.class)` phải nạp đúng các bean package `com.example.checkout`.
- `enforceOverride=true` yêu cầu tồn tại bean `PaymentGateway` thật; ở demo `DemoPaymentGateway` là bean đích. Nếu bean không tồn tại, đó là lỗi cần xem, không nên tắt bảo đảm ngay.
- `@WebMvcTest` cần Jackson/web support từ starter-web. Nếu có security trên classpath, request POST có thể cần principal/CSRF theo chính sách đang kiểm.
- Nếu `@Autowired` thất bại, xem root cause của `Failed to load ApplicationContext`, bean ambiguity và qualifier.
- Nếu test run cùng suite bị fail do state fake singleton, kiểm tra context cache và isolation thay vì ép thứ tự chạy.

## 23. Bài tập thực hành

### Bài A — chọn SUT và ranh giới đúng

Yêu cầu: voucher có hạn sử dụng, chỉ giảm cho khách hàng mới, sau đó thanh toán và lưu order.

Hãy xác định thành phần phải chạy thật khi test **quy tắc voucher**, và thành phần nào có thể là double. Gợi ý: voucher policy thật, fixed clock, fake customer lookup nếu lookup là external, payment gateway mock, order repository fake nếu không kiểm SQL.

### Bài B — phát hiện test xanh giả

Cho test:

```java
CheckoutService mockService = mock(CheckoutService.class);
when(mockService.checkout(command)).thenReturn(receipt);
assertEquals(receipt, mockService.checkout(command));
```

Đây là đoạn minh họa; `command` và `receipt` chưa khai báo. Hãy trả lời: nếu xóa toàn bộ code trong `CheckoutService.checkout` thật, test này có đỏ không? Nếu không, sửa bằng cách tạo service thật và chỉ mock/fake outbound collaborators.

### Bài C — kiểm tra lỗi payment

Với ví dụ ở mục 8, đổi gateway thành ném `IllegalStateException("declined")`; assert số lần gọi charge, exception và store rỗng. Tiếp tục thử số lượng âm và SKU không có; không được charge khi input sai.

### Bài D — chọn MVC slice hay service unit

Một API nhận POST JSON sai tên field `quantity` dẫn tới HTTP 400 thay vì mong đợi, trong khi discount policy hoàn toàn đúng. Nên sửa/test ở đâu? Gợi ý: controller/MVC binding/validation và HTTP contract cần test riêng; unit test domain không bắt được lỗi JSON mapping.

### Bài E — giao dịch và dữ liệu

Fake `OrderStore` có thể kiểm câu “save được gọi sau charge”; có thể khẳng định JPA transaction commit, unique constraint hay rollback khi server xử lý HTTP thật không? Giải thích vì sao cần integration test database và test transaction boundary riêng.

### Bài F — thay đúng bean

Trong Spring context có hai bean cùng implement `PaymentGateway`, one for card và one for bank. Nếu test dùng `@MockitoBean PaymentGateway gateway;`, rủi ro gì? Hãy đề xuất bean name/qualifier rõ ràng, và giải thích khi nào `enforceOverride=true` phù hợp.

## 24. Checklist review trước khi chốt một bài test

- [ ] Test có một mục tiêu và hợp đồng rõ: **nó phải đỏ nếu bug nào xuất hiện**?
- [ ] SUT là implementation thật, không phải mock tự trả dữ liệu `expected`.
- [ ] Domain rule quan trọng (giá, discount, eligibility, state transition) được chạy thật.
- [ ] Test double tập trung tại outbound boundary, external API, DB, clock hoặc collaborator thực sự ngoài phạm vi.
- [ ] Double phản ánh những phần contract tối thiểu, không giả lập hệ thống phức tạp quá mức.
- [ ] Tôi phân biệt unit/service test với controller MVC slice: mock service chỉ khi service ngoài scope.
- [ ] Có assertion về **kết quả và trạng thái**, không chỉ verify call graph nội bộ.
- [ ] Verify interaction chỉ khi argument, thứ tự hoặc số lần gọi có ý nghĩa nghiệp vụ.
- [ ] Nếu dùng Spring context, tôi thay **đúng bean** bằng annotation phù hợp phiên bản.
- [ ] Tôi hiểu `@MockitoBean` mặc định có thể tạo bean mới; khi cần xác minh bean tồn tại, cân nhắc `enforceOverride=true`.
- [ ] Tôi không vô tình mock mất proxy/transaction/cache/security behavior đang định kiểm tra.
- [ ] Fake bean, context cache, test parallel và data isolation được xử lý có chủ đích.
- [ ] Các adapter DB/HTTP/message vẫn có test riêng để bảo vệ giao thức/hạ tầng thật.
- [ ] Một refactor nội bộ hợp lệ không khiến test vỡ nếu contract giữ nguyên.
- [ ] Khi test đỏ, thông báo giúp thấy sai lệch nghiệp vụ chứ không chỉ một method trung gian chưa được gọi.

**Ghi nhớ:** **Mock ít hay nhiều không phải tiêu chí chất lượng tự thân.** Tiêu chí đúng là **phần nào của hệ thống thực sự được thực thi, phần nào được thay và vì sao**. Một bài unit test checkout đáng tin sẽ chạy giá, giảm giá, điều kiện và orchestration thật; chỉ thay cổng thanh toán hoặc lưu trữ nếu chúng ở ngoài mục tiêu. Một MVC slice test đáng tin có thể mock application service để tập trung vào HTTP contract, nhưng không được tuyên bố từ đó rằng business logic đã đúng. Đặt test double đúng ranh giới giúp test vừa nhanh, vừa bắt được lỗi quan trọng và bền vững khi refactor.

### Tài liệu tham khảo

- Spring Framework — Bean Overriding in Tests: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
- Spring Framework 6.2 — `@MockitoBean` và `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Boot 3.4 Release Notes — deprecation của `@MockBean` và `@SpyBean`: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
- Mockito API — `mock`, `when`, `verify`, `spy`: https://site.mockito.org/
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
