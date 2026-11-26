# Mock external gateway theo contract

## 1. Mock gateway theo contract khác gì stub cho test xanh?

Giả sử `orders` phải yêu cầu một nhà cung cấp thanh toán bên ngoài **ủy quyền khoản tiền**, rồi mới ghi kết quả vào database và phát sự kiện nghiệp vụ. Một test kiểu:

~~~java
when(paymentGateway.authorize(any()))
        .thenReturn(new Authorized("auth-123"));

checkoutService.authorize(orderId, customerId, amount, currency);

verify(paymentGateway).authorize(any());
~~~

chỉ chứng minh có lời gọi phù hợp với một mock đã trả kết quả do test tự quyết định. Nó **không kiểm tra** gateway nhận đúng số tiền, tiền tệ, idempotency key; không phân biệt khách bị từ chối với lỗi mạng; và càng không chứng minh HTTP request thật đúng hợp đồng của provider.

**Mock gateway theo contract** có nghĩa là định nghĩa *trước* những điều bất biến ở ranh giới kết nối, rồi test từng điều đó có mục đích:

1. **Input contract:** Gateway nhận đúng `orderId`, amount, currency và idempotency key ổn định; dữ liệu không cần thiết/nhạy cảm không bị chuyển ra ngoài.
2. **Outcome contract:** Thành công và bị từ chối là **hai kết quả nghiệp vụ khác nhau**; timeout, HTTP 429/5xx hoặc response không hợp lệ là **lỗi tích hợp**, không phải “từ chối thanh toán”.
3. **Side-effect contract:** Input lỗi bị chặn trước khi gọi provider; khi được ủy quyền thì lưu trạng thái và phát đúng event; khi bị từ chối thì không phát event “authorized”.
4. **Retry contract:** Một logical attempt dùng cùng idempotency key qua những lần thử lại; Mockito invocation count không chứng minh provider chỉ thực hiện một side effect.
5. **Transport contract:** HTTP method, path, header, JSON body, status/error mapping và schema cần được test trên **adapter thật** với fake HTTP server, không chỉ trên mock Java interface.

Bài thuộc chương **Mock và spy** trong `SPRING_MODULITH_VERIFICATION_TESTING`: kiểm chứng ranh giới kiến trúc ứng dụng Spring Modulith bằng `ApplicationModules`, `@ApplicationModuleTest`, dữ liệu, sự kiện, kiểm thử tích hợp và CI quality gate. Phạm vi bài này **tập trung vào hợp đồng của external gateway**; những kỹ thuật Mockito cơ bản chỉ được nhắc khi trực tiếp làm rõ một điều khoản hợp đồng.

### Sau bài học, bạn cần làm được

- Viết một contract cụ thể cho outbound payment authorization gateway.
- Dùng `ArgumentCaptor`, typed matchers, negative verification và failure stubs để kiểm tra **đúng dữ liệu, đúng kết quả, đúng nhánh**.
- Giữ `OrderCheckoutService`, persistence và event publication thật trong `@ApplicationModuleTest`, nhưng mock **outbound port**.
- Chạy HTTP adapter thật với `MockRestServiceServer` để kiểm tra URL, header, payload và mapping 4xx/429/5xx.
- Phân biệt bằng chứng của port mock, adapter test, provider contract test và bài test retry/idempotency end-to-end.

## 2. Hợp đồng cụ thể trước khi viết bất kỳ when(...) nào

Ta giả định provider công bố một HTTP contract phiên bản `v1` với quy tắc **được thỏa thuận trong ví dụ**, không phải chuẩn chung của mọi payment API.

| Chi tiết | Hợp đồng được chọn |
| --- | --- |
| Method/route | `POST /v1/authorizations`. |
| Idempotency | Header `Idempotency-Key` ổn định cho cùng `orderId` và cùng logical authorization attempt. |
| JSON request | `orderReference` (UUID dưới dạng chuỗi), `amountMinor` (số nguyên đơn vị nhỏ nhất), `currency` (ISO 4217). |
| 200, `status=AUTHORIZED` | Có `authorizationId` không rỗng; giao dịch đã được provider chấp thuận. |
| 200, `status=DECLINED` | Có `declineCode`; đây là **business outcome**, không phải lỗi transport. |
| HTTP 429 hoặc 5xx | Lỗi tạm thời, có thể thử lại theo **chính sách có giới hạn** với cùng idempotency key. |
| HTTP 400/401/403/409 | Không tự retry vô hạn; cần phân loại lỗi cấu hình, xác thực, input hoặc xung đột idempotency theo contract provider. |
| Timeout/network reset | Kết quả có thể **không xác định**: provider có thể đã ủy quyền nhưng response bị mất. |
| JSON thiếu field, `status` lạ | **Contract violation**, không tự coi là `AUTHORIZED` hoặc `DECLINED`. |

Hai điểm quan trọng:

**Thứ nhất, không đồng nhất `DECLINED` với HTTP lỗi.** Một provider có thể trả `200` chứa `DECLINED`; provider khác có thể dùng HTTP 402/422. Adapter phải ánh xạ theo **hợp đồng thực**, không dựa vào cách đặt tên chung.

**Thứ hai, timeout là *unknown outcome*, không chắc chắn “chưa ủy quyền”.** Nếu client timeout sau khi provider đã xử lý, gửi lại request với key mới có thể tạo tác động trùng. Đây là lý do `Idempotency-Key` và reconciliation là phần của contract, không phải chi tiết trang trí trong mock.

### 2.1. Một giao dịch minh họa

Request:

~~~http
POST /v1/authorizations HTTP/1.1
Host: payments.example.test
Content-Type: application/json
Idempotency-Key: auth:v1:4fde88de-9eb1-4677-a682-7e23ae949a21

{"orderReference":"4fde88de-9eb1-4677-a682-7e23ae949a21","amountMinor":125000,"currency":"VND"}
~~~

Response được ủy quyền:

~~~json
{"status":"AUTHORIZED","authorizationId":"pay_auth_77"}
~~~

Response từ chối:

~~~json
{"status":"DECLINED","declineCode":"INSUFFICIENT_FUNDS"}
~~~

VND trong ví dụ có `0` chữ số phần thập phân ở đơn vị nhỏ nhất theo ISO 4217: `125000 VND` được gửi là `125000` minor units. Với USD, `12.50 USD` thành `1250` minor units. **Không nhân tất cả currencies với 100 một cách máy móc.** Nếu provider định nghĩa đơn vị khác ISO 4217, adapter phải tuân theo contract riêng của provider và kiểm thử chuyển đổi.

### 2.2. Phân định loại bằng chứng

| Test | Chứng minh được | Chưa chứng minh |
| --- | --- | --- |
| Unit test mock `PaymentGateway` | SUT gọi port với request đúng, phản ứng theo outcome/exception đã stub. | HTTP URL/header/serialization, provider behavior thật. |
| `@ApplicationModuleTest` mock gateway | Logic nội bộ, DB state và event publication của module ứng với contract giả lập. | Provider đã nhận yêu cầu. |
| Adapter test + fake HTTP server | Request/response thực của adapter trong phạm vi fixtures; mapping status, header, money. | Provider production tuân thủ fixtures. |
| Provider sandbox/consumer-driven contract | Độ tương thích với provider hoặc specification được xác minh tại thời điểm test. | Mọi outage/timeout hoặc exactly-once business effect. |
| Retry/recovery integration | Idempotency/reconciliation trên nhiều attempts và failure windows được mô phỏng. | Không có failure mode nào ngoài phạm vi test. |

## 3. Đặt outbound port ở đâu trong Spring Modulith?

Với hệ thống một module `orders` gọi provider thanh toán **bên ngoài ứng dụng**:

~~~text
com.example.shop
├── ShopApplication.java
└── orders                         ← Spring Modulith application module
    ├── OrderCheckoutService.java
    ├── events
    │   ├── PaymentAuthorized.java
    │   └── package-info.java
    └── internal
        ├── AuthorizationRecorder.java
        ├── PaymentAttemptEntity.java
        ├── PaymentAttemptRepository.java
        ├── PaymentStatus.java
        └── payment
            ├── PaymentGateway.java
            ├── AuthorizationRequest.java
            ├── AuthorizationDecision.java
            ├── GatewayUnavailableException.java
            ├── GatewayContractException.java
            └── http
                └── HttpPaymentGateway.java
~~~

Trong thiết kế này, **port `PaymentGateway` thuộc chính module `orders`**. Adapter HTTP là implementation detail dưới `orders.internal.payment.http`. Không cần tạo một application module mới chỉ để mock provider:

~~~mermaid
flowchart LR
    S["OrderCheckoutService"] --> P["PaymentGateway port"]
    P --> A["HttpPaymentGateway adapter"]
    A --> V["External provider HTTPS"]
    S --> R["AuthorizationRecorder"]
    R --> DB[("PaymentAttemptRepository / DB")]
    R --> E["ApplicationEventPublisher"]
    T["@ApplicationModuleTest orders"] -. "MockitoBean" .-> P
    T --> R
    T --> DB
    T --> E
~~~

Trong **module test**, mock port để cô lập network, giữ application service/recorder/JPA/publisher thật. Trong **adapter test**, giữ `HttpPaymentGateway` thật nhưng thay **server HTTP bên ngoài** bằng `MockRestServiceServer`. Hai test này kiểm tra hai hợp đồng khác nhau.

**Nếu payment adapter nằm trong một Spring Modulith module tích hợp riêng**, `orders` phải phụ thuộc đúng **public/named interface** của module ấy; khi đó `@ApplicationModuleTest(STANDALONE)` có thể tạo `@MockitoBean` tại public interface ngoài module. Quy tắc không đổi: *mock tại boundary cần cô lập, không import repository/implementation nội bộ của module khác*.

## 4. Java port: request và outcome là kiểu dữ liệu có ý nghĩa

File `orders/internal/payment/AuthorizationRequest.java`:

~~~java
package com.example.shop.orders.internal.payment;

import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;

public record AuthorizationRequest(
        UUID orderId,
        BigDecimal amount,
        String currency,
        String idempotencyKey
) {
    public AuthorizationRequest {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(idempotencyKey, "idempotencyKey");
        if (amount.signum() <= 0 || idempotencyKey.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid authorization request");
        }
    }
}
~~~

File `orders/internal/payment/AuthorizationDecision.java`:

~~~java
package com.example.shop.orders.internal.payment;

import java.util.Objects;

public sealed interface AuthorizationDecision
        permits AuthorizationDecision.Authorized,
                AuthorizationDecision.Declined {

    record Authorized(String authorizationId)
            implements AuthorizationDecision {
        public Authorized {
            Objects.requireNonNull(authorizationId);
            if (authorizationId.isBlank()) {
                throw new IllegalArgumentException(
                        "authorizationId is blank");
            }
        }
    }

    record Declined(String reasonCode)
            implements AuthorizationDecision {
        public Declined {
            Objects.requireNonNull(reasonCode);
            if (reasonCode.isBlank()) {
                throw new IllegalArgumentException(
                        "reasonCode is blank");
            }
        }
    }
}
~~~

File `orders/internal/payment/PaymentGateway.java`:

~~~java
package com.example.shop.orders.internal.payment;

public interface PaymentGateway {
    AuthorizationDecision authorize(AuthorizationRequest request);
}
~~~

Hai exceptions thuộc contract port:

~~~java
package com.example.shop.orders.internal.payment;

public class GatewayUnavailableException
        extends RuntimeException {
    public GatewayUnavailableException(String message) {
        super(message);
    }
    public GatewayUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
package com.example.shop.orders.internal.payment;

public class GatewayContractException
        extends RuntimeException {
    public GatewayContractException(String message) {
        super(message);
    }
    public GatewayContractException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Các đoạn trên là **hai tệp exception riêng biệt**, không đặt hai public classes trong một tệp Java.

**Contract decision:** `Authorized` hoặc `Declined` là một **kết quả trả về**, còn `GatewayUnavailableException` mô tả lỗi tạm thời/unknown outcome và `GatewayContractException` mô tả adapter không thể diễn giải response theo hợp đồng. Không viết:

~~~java
// Sai: lỗi mạng bị giả mạo thành business decline.
catch (Exception ignored) {
    return new AuthorizationDecision.Declined("NETWORK_ERROR");
}
~~~

Làm như vậy khiến hệ thống ghi “khách bị từ chối” trong khi provider có thể đã chấp thuận. Một contract đúng giúp phân biệt chính sách **reconciliation** với nhánh từ chối thật.

### 4.1. Không gửi dữ liệu không có trong hợp đồng

`AuthorizationRequest` **không chứa** email, số điện thoại, địa chỉ hoặc `CustomerEntity` đầy đủ. `customerId` chỉ dùng để lưu quan hệ trong database nội bộ của `orders`. Trước khi thêm trường vào external request, hãy xác nhận provider cần dữ liệu đó và chính sách privacy/compliance.

### 4.2. BigDecimal là domain amount; adapter sở hữu money serialization

Port nhận `BigDecimal` để tránh floating-point, còn HTTP adapter chuyển amount sang `amountMinor` theo currency. Tách lớp giúp unit test nghiệp vụ không phụ thuộc cách provider biểu diễn tiền; adapter test phải bảo vệ **quy tắc chuyển đổi thực**, bao gồm scale và overflow.

## 5. Use case và transaction: tách network call khỏi transaction ghi DB

File `orders/internal/PaymentStatus.java`:

~~~java
package com.example.shop.orders.internal;

public enum PaymentStatus {
    AUTHORIZED,
    DECLINED
}
~~~

File `orders/internal/PaymentAttemptEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.util.UUID;

@Entity
@Table(name = "payment_attempts")
public class PaymentAttemptEntity {

    @Id
    private UUID orderId;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(nullable = false, length = 3)
    private String currency;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private PaymentStatus status;

    @Column(name = "idempotency_key",
            nullable = false, unique = true, length = 128)
    private String idempotencyKey;

    @Column(name = "authorization_id")
    private String authorizationId;

    @Column(name = "decline_code")
    private String declineCode;

    protected PaymentAttemptEntity() {}

    private PaymentAttemptEntity(
            AuthorizationFields f,
            PaymentStatus status,
            String authorizationId,
            String declineCode) {
        this.orderId = f.orderId();
        this.customerId = f.customerId();
        this.amount = f.amount();
        this.currency = f.currency();
        this.idempotencyKey = f.idempotencyKey();
        this.status = status;
        this.authorizationId = authorizationId;
        this.declineCode = declineCode;
    }

    public static PaymentAttemptEntity authorized(
            AuthorizationFields fields, String authorizationId) {
        return new PaymentAttemptEntity(
                fields, PaymentStatus.AUTHORIZED,
                authorizationId, null);
    }

    public static PaymentAttemptEntity declined(
            AuthorizationFields fields, String reasonCode) {
        return new PaymentAttemptEntity(
                fields, PaymentStatus.DECLINED,
                null, reasonCode);
    }

    public UUID getOrderId() { return orderId; }
    public BigDecimal getAmount() { return amount; }
    public String getCurrency() { return currency; }
    public PaymentStatus getStatus() { return status; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public String getAuthorizationId() { return authorizationId; }
    public String getDeclineCode() { return declineCode; }

    public record AuthorizationFields(
            UUID orderId, UUID customerId,
            BigDecimal amount, String currency,
            String idempotencyKey) {}
}
~~~

File `orders/internal/PaymentAttemptRepository.java`:

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentAttemptRepository
        extends JpaRepository<PaymentAttemptEntity, UUID> {}
~~~

File `orders/events/PaymentAuthorized.java`:

~~~java
package com.example.shop.orders.events;

import java.util.UUID;

public record PaymentAuthorized(
        UUID eventId,
        UUID orderId,
        String authorizationId,
        String idempotencyKey
) {}
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Để **không giữ transaction database mở trong lúc chờ HTTP**, use case gọi gateway **trước**, sau đó gọi một bean khác để ghi kết quả trong transaction.

File `orders/OrderCheckoutService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.internal.AuthorizationRecorder;
import com.example.shop.orders.internal.PaymentStatus;
import com.example.shop.orders.internal.payment.AuthorizationRequest;
import com.example.shop.orders.internal.payment.PaymentGateway;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;
import java.util.UUID;

@Service
public class OrderCheckoutService {

    private final PaymentGateway gateway;
    private final AuthorizationRecorder recorder;

    public OrderCheckoutService(
            PaymentGateway gateway,
            AuthorizationRecorder recorder) {
        this.gateway = gateway;
        this.recorder = recorder;
    }

    public PaymentStatus authorize(
            UUID orderId, UUID customerId,
            BigDecimal amount, String currency) {
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Amount must be positive");
        }
        // Provider contract của ví dụ yêu cầu ISO 4217 uppercase.
        Currency.getInstance(currency);

        String key = "auth:v1:" + orderId;
        var request = new AuthorizationRequest(
                orderId, amount, currency, key);

        var decision = gateway.authorize(request);
        return recorder.record(request, customerId, decision);
    }
}
~~~

File `orders/internal/AuthorizationRecorder.java`:

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.PaymentAuthorized;
import com.example.shop.orders.internal.PaymentAttemptEntity.AuthorizationFields;
import com.example.shop.orders.internal.payment.AuthorizationDecision;
import com.example.shop.orders.internal.payment.AuthorizationRequest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class AuthorizationRecorder {

    private final PaymentAttemptRepository attempts;
    private final ApplicationEventPublisher events;

    public AuthorizationRecorder(
            PaymentAttemptRepository attempts,
            ApplicationEventPublisher events) {
        this.attempts = attempts;
        this.events = events;
    }

    @Transactional
    public PaymentStatus record(
            AuthorizationRequest request, UUID customerId,
            AuthorizationDecision decision) {
        var fields = new AuthorizationFields(
                request.orderId(), customerId,
                request.amount(), request.currency(),
                request.idempotencyKey());

        if (decision instanceof
                AuthorizationDecision.Authorized approved) {
            attempts.save(PaymentAttemptEntity.authorized(
                    fields, approved.authorizationId()));

            events.publishEvent(new PaymentAuthorized(
                    UUID.randomUUID(),
                    request.orderId(),
                    approved.authorizationId(),
                    request.idempotencyKey()));
            return PaymentStatus.AUTHORIZED;
        }

        if (decision instanceof
                AuthorizationDecision.Declined declined) {
            attempts.save(PaymentAttemptEntity.declined(
                    fields, declined.reasonCode()));
            return PaymentStatus.DECLINED;
        }

        throw new IllegalArgumentException(
                "Unsupported authorization decision");
    }
}
~~~

**Vì sao một bean `AuthorizationRecorder` riêng?** Gọi phương thức `@Transactional` trên một bean khác thông qua Spring proxy bảo đảm phần ghi database có transaction rõ; gọi `this.record(...)` từ cùng bean có thể bypass proxy. `OrderCheckoutService.authorize` không có `@Transactional`, nên network call không nằm trong transaction ghi của recorder.

**Giới hạn thiết kế cố ý giữ rõ:** Một provider có thể đã ủy quyền, nhưng database `attempts.save` sau đó lỗi hoặc process chết trước commit. HTTP và database **không atomic** chỉ vì recorder có `@Transactional`. Dữ liệu `orderId`/idempotency key ổn định giúp reconciliation, nhưng ví dụ chưa triển khai **retries an toàn end-to-end**, check tồn tại trước khi gọi provider, hay idempotent event publication. Những việc đó cần thiết kế và test riêng ở phần sau.

## 6. Test contract: lập bảng trước khi stub

Mỗi hàng dưới đây nên có **một mục tiêu quan sát riêng**, không dùng một mock happy-path làm bằng chứng cho tất cả.

| Trường hợp | Gateway phải nhận gì / trả gì? | Outcome bên trong module |
| --- | --- | --- |
| Hợp lệ + provider `AUTHORIZED` | Đúng amount/currency/orderId/key; trả `Authorized("auth-...")`. | Row `AUTHORIZED`, đúng `authorizationId`, một `PaymentAuthorized` cho order. |
| Hợp lệ + `DECLINED` | Cùng request contract; trả `Declined("...")`. | Row `DECLINED`, lưu reason, **không** phát `PaymentAuthorized`. |
| Amount không dương | **Không được gọi** gateway. | Exception validation; không tạo row/event. |
| HTTP timeout / 429 / 5xx được adapter phân loại | Port ném `GatewayUnavailableException`. | Không ghi `AUTHORIZED`/`DECLINED` giả; chưa có event authorized; retry/reconciliation là workflow khác. |
| Response provider thiếu field hoặc status lạ | Port ném `GatewayContractException`. | Fail closed, không lưu một authorized/declined sai. |
| Hai lần thử lại cùng logical order | **Cùng idempotency key**. | Cần kiểm tra policy retry, dedup DB và event; không tự suy từ `times(1)`. |
| Thay amount/currency cho cùng key | Phải từ chối hoặc mở logical attempt mới theo policy. | Không được âm thầm tái sử dụng key cho một giao dịch khác. |

Chính **cột thứ hai và thứ ba** quyết định matcher/assertion sẽ viết thế nào, thay vì viết một chuỗi `when(any()).thenReturn(...)` rồi mới tìm business story phù hợp với test.

## 7. Unit test tập trung vào outbound request contract

Unit test có thể mock `AuthorizationRecorder` để tách trách nhiệm gọi gateway; `PaymentGateway` cũng là mock. Đây là test **request contract và orchestration**, không phải database/HTTP test.

~~~java
package com.example.shop.orders;

import com.example.shop.orders.internal.AuthorizationRecorder;
import com.example.shop.orders.internal.PaymentStatus;
import com.example.shop.orders.internal.payment.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderCheckoutGatewayContractTests {

    @Mock PaymentGateway gateway;
    @Mock AuthorizationRecorder recorder;

    @Test
    void sendsExactAuthorizationContractToGateway() {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        BigDecimal amount = new BigDecimal("125000");
        var approved =
                new AuthorizationDecision.Authorized("pay_auth_77");

        when(gateway.authorize(any(AuthorizationRequest.class)))
                .thenReturn(approved);
        when(recorder.record(
                any(AuthorizationRequest.class),
                eq(customerId), eq(approved)))
                .thenReturn(PaymentStatus.AUTHORIZED);

        var checkout = new OrderCheckoutService(
                gateway, recorder);
        var result = checkout.authorize(
                orderId, customerId, amount, "VND");

        assertThat(result).isEqualTo(PaymentStatus.AUTHORIZED);

        var captured = ArgumentCaptor.forClass(
                AuthorizationRequest.class);
        verify(gateway).authorize(captured.capture());

        AuthorizationRequest request = captured.getValue();
        assertThat(request.orderId()).isEqualTo(orderId);
        assertThat(request.amount())
                .isEqualByComparingTo(amount);
        assertThat(request.currency()).isEqualTo("VND");
        assertThat(request.idempotencyKey())
                .isEqualTo("auth:v1:" + orderId);

        verify(recorder).record(
                same(request), eq(customerId), eq(approved));
    }

    @Test
    void invalidAmountIsRejectedBeforeAnyGatewayCall() {
        var checkout = new OrderCheckoutService(
                gateway, recorder);

        assertThatThrownBy(() ->
                checkout.authorize(
                        UUID.randomUUID(),
                        UUID.randomUUID(),
                        BigDecimal.ZERO, "VND"))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(gateway, recorder);
    }
}
~~~

### 7.1. Vì sao `any()` trong stubbing vẫn có thể chấp nhận?

Trong happy-path test, `when(gateway.authorize(any(AuthorizationRequest.class)))` chỉ cho phép SUT tiếp tục chạy. **Sức mạnh của test nằm ở `ArgumentCaptor` và assertions theo từng field**, không nằm ở matcher rộng ấy. Nếu thiếu captor, test có thể pass khi code gửi sai `currency`, sai `amount` hoặc key sinh mới trên mỗi attempt.

Khi chỉ cần kiểm tra một expected record immutable với `BigDecimal` được chuẩn hóa, có thể stub/verify `eq(expectedRequest)`; lưu ý `BigDecimal.equals()` phân biệt scale: `new BigDecimal("10.0")` không `equals` với `10.00`. Nếu hợp đồng chỉ quan tâm số trị, captor + `isEqualByComparingTo` giúp thể hiện chính xác hơn; còn nếu wire format yêu cầu scale cố định, assert string/amountMinor ở **adapter test**.

### 7.2. Không over-verify thứ tự implementation không có trong contract

Không thêm `InOrder(gateway, recorder)` chỉ vì hiện tại code gọi gateway rồi ghi DB. **Trong ví dụ này** quan hệ “chỉ ghi kết quả sau khi nhận decision” là cần thiết; nó được kiểm tra bởi việc `recorder.record(..., decision)` nhận chính decision do gateway trả, đồng thời các failure tests đảm bảo không ghi trạng thái giả. Nếu protocol có yêu cầu sequencing nghiêm ngặt hơn, thêm một test có tên/contract rõ, thay vì verify mọi helper call.

### 7.3. Lỗi contract không nên bị nuốt thành giá trị mặc định

Test riêng cho port ném exception:

~~~java
@Test
void unknownGatewayOutcomeDoesNotReachRecorder() {
    var checkout = new OrderCheckoutService(
            gateway, recorder);
    UUID orderId = UUID.randomUUID();

    when(gateway.authorize(any(AuthorizationRequest.class)))
            .thenThrow(new GatewayUnavailableException(
                    "Timed out"));

    assertThatThrownBy(() ->
            checkout.authorize(orderId, UUID.randomUUID(),
                    new BigDecimal("125000"), "VND"))
            .isInstanceOf(GatewayUnavailableException.class);

    verifyNoInteractions(recorder);
}
~~~

Lời gọi gateway **có xảy ra**; assertion ở đây chỉ cấm recorder tạo business outcome giả. Đây là khác biệt thiết yếu so với `verifyNoInteractions(gateway)` ở nhánh validation lỗi.

## 8. @ApplicationModuleTest: mock outbound port, giữ dữ liệu và event thật

Một test module cần chứng minh **phản ứng nội bộ của `orders` khi gateway trả kết quả theo contract**. Trong `@ApplicationModuleTest(STANDALONE)`, mock `PaymentGateway`, nhưng để `OrderCheckoutService`, `AuthorizationRecorder`, JPA repository, transaction manager và `ApplicationEventPublisher` chạy thật.

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.PaymentAuthorized;
import com.example.shop.orders.internal.PaymentAttemptRepository;
import com.example.shop.orders.internal.PaymentStatus;
import com.example.shop.orders.internal.payment.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ApplicationModuleTest
class CheckoutPaymentGatewayModuleTests {

    @Autowired OrderCheckoutService checkout;
    @Autowired PaymentAttemptRepository attempts;

    // Thay đúng external gateway boundary; không mock JPA/publisher.
    @MockitoBean PaymentGateway gateway;

    @Test
    void approvedGatewayResponseIsRecordedAndEventPublished(
            PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        var amount = new BigDecimal("125000");

        when(gateway.authorize(any(AuthorizationRequest.class)))
                .thenReturn(
                        new AuthorizationDecision.Authorized(
                                "pay_auth_77"));

        PaymentStatus status = checkout.authorize(
                orderId, customerId, amount, "VND");

        assertThat(status).isEqualTo(PaymentStatus.AUTHORIZED);

        var captor = org.mockito.ArgumentCaptor.forClass(
                AuthorizationRequest.class);
        verify(gateway).authorize(captor.capture());

        assertThat(captor.getValue().orderId())
                .isEqualTo(orderId);
        assertThat(captor.getValue().amount())
                .isEqualByComparingTo(amount);
        assertThat(captor.getValue().currency())
                .isEqualTo("VND");
        assertThat(captor.getValue().idempotencyKey())
                .isEqualTo("auth:v1:" + orderId);

        // JPA thật: provider outcome được ghi trong transaction.
        assertThat(attempts.findById(orderId))
                .get()
                .satisfies(record -> {
                    assertThat(record.getStatus())
                            .isEqualTo(PaymentStatus.AUTHORIZED);
                    assertThat(record.getAuthorizationId())
                            .isEqualTo("pay_auth_77");
                    assertThat(record.getIdempotencyKey())
                            .isEqualTo("auth:v1:" + orderId);
                    assertThat(record.getAmount())
                            .isEqualByComparingTo(amount);
                });

        // Event do Spring publisher thật phát.
        assertThat(events.ofType(PaymentAuthorized.class)
                .matching(PaymentAuthorized::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.authorizationId())
                            .isEqualTo("pay_auth_77");
                    assertThat(event.idempotencyKey())
                            .isEqualTo("auth:v1:" + orderId);
                    assertThat(event.eventId()).isNotNull();
                });
    }
}
~~~

Điều kiện: đã có datasource JPA, transaction manager, schema `payment_attempts`, Spring Modulith test starter và Spring Framework 6.2+ cho `@MockitoBean`. Dự án Boot cũ có thể cần annotation thay thế. Không gắn `@Transactional` trên test class nếu muốn `AuthorizationRecorder` commit transaction riêng và đọc lại sau khi method trả về.

**Bằng chứng chính xác:**

- Request truyền qua port có đúng các trường nghiệp vụ.
- Recorder thật lưu `AUTHORIZED`/authorization ID bằng JPA.
- `PaymentAuthorized` được phát trong Spring context.

**Chưa được chứng minh:** provider đã nhận HTTP request, response thật có đúng schema, listener sau commit hoàn tất hoặc external side effect exactly-once.

### 8.1. Nhánh DECLINED: business outcome, không phải exception

~~~java
@Test
void declinedDecisionPersistsDeclinedWithoutAuthorizedEvent(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();

    when(gateway.authorize(any(AuthorizationRequest.class)))
            .thenReturn(
                    new AuthorizationDecision.Declined(
                            "INSUFFICIENT_FUNDS"));

    PaymentStatus status = checkout.authorize(
            orderId, UUID.randomUUID(),
            new BigDecimal("50000"), "VND");

    assertThat(status).isEqualTo(PaymentStatus.DECLINED);
    assertThat(attempts.findById(orderId))
            .get()
            .satisfies(row -> {
                assertThat(row.getStatus())
                        .isEqualTo(PaymentStatus.DECLINED);
                assertThat(row.getDeclineCode())
                        .isEqualTo("INSUFFICIENT_FUNDS");
                assertThat(row.getAuthorizationId()).isNull();
            });
    assertThat(events.ofType(PaymentAuthorized.class)
            .matching(PaymentAuthorized::orderId, orderId))
            .isEmpty();
}
~~~

Đoạn này đặt cùng `CheckoutPaymentGatewayModuleTests`. Nó phát hiện lỗi nguy hiểm: một provider **từ chối** nhưng hệ thống vẫn tạo event báo đã được ủy quyền. Không cần `verifyNoMoreInteractions` trên toàn bộ ứng dụng; DB state và **event vắng mặt đúng loại** mới là hợp đồng.

### 8.2. Timeout/unknown outcome: không ghi “declined” giả

~~~java
@Test
void temporaryGatewayErrorDoesNotStoreFinalDecision(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();

    when(gateway.authorize(any(AuthorizationRequest.class)))
            .thenThrow(new GatewayUnavailableException(
                    "Network timeout"));

    assertThatThrownBy(() ->
            checkout.authorize(
                    orderId, UUID.randomUUID(),
                    new BigDecimal("50000"), "VND"))
            .isInstanceOf(GatewayUnavailableException.class);

    assertThat(attempts.existsById(orderId)).isFalse();
    assertThat(events.ofType(PaymentAuthorized.class)
            .matching(PaymentAuthorized::orderId, orderId))
            .isEmpty();
}
~~~

**Đây là quyết định thiết kế của use case ví dụ:** lỗi gateway được truyền ra ngoài, chưa ghi final decision. Một production workflow có thể lưu `PENDING`/unknown outcome trước khi gọi provider để retry/reconcile bền vững; khi chọn mô hình đó, assertions phải phản ánh contract mới, không dùng bài test này như luật phổ quát.

### 8.3. Input invalid: cấm hoàn toàn outbound call

~~~java
@Test
void invalidAmountNeverCallsGateway(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();

    assertThatThrownBy(() ->
            checkout.authorize(
                    orderId, UUID.randomUUID(),
                    BigDecimal.ZERO, "VND"))
            .isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(gateway);
    assertThat(attempts.existsById(orderId)).isFalse();
    assertThat(events.ofType(PaymentAuthorized.class)
            .matching(PaymentAuthorized::orderId, orderId))
            .isEmpty();
}
~~~

Ở đây `verifyNoInteractions(gateway)` là điều khoản **cấm gọi provider khi chưa qua validation**, không phải oververification một chi tiết triển khai. `@MockitoBean` mock được reset giữa các test methods theo cơ chế Spring Test mặc định; vẫn dùng UUID riêng và tách state database/async phù hợp.

## 9. HTTP adapter: ánh xạ contract thật, không đẩy JSON vào service

Ở production, `HttpPaymentGateway` triển khai port bằng Spring `RestClient` (Spring Framework 6.1+). Trong adapter, **money conversion và HTTP error mapping là trách nhiệm của adapter**, không phải `OrderCheckoutService`.

File `orders/internal/payment/http/HttpPaymentGateway.java`:

~~~java
package com.example.shop.orders.internal.payment.http;

import com.example.shop.orders.internal.payment.*;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.math.BigDecimal;
import java.util.Currency;

public final class HttpPaymentGateway
        implements PaymentGateway {

    private final RestClient http;

    public HttpPaymentGateway(RestClient http) {
        this.http = http;
    }

    @Override
    public AuthorizationDecision authorize(
            AuthorizationRequest request) {
        long minorUnits = toMinorUnits(
                request.amount(), request.currency());

        try {
            ProviderReply reply = http.post()
                    .uri("/v1/authorizations")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("Idempotency-Key",
                            request.idempotencyKey())
                    .body(new ProviderRequest(
                            request.orderId().toString(),
                            minorUnits, request.currency()))
                    .retrieve()
                    .onStatus(
                            status -> status.value() == 429
                                    || status.is5xxServerError(),
                            (req, response) -> {
                                throw new GatewayUnavailableException(
                                        "Temporary HTTP status "
                                        + response.getStatusCode());
                            })
                    .onStatus(
                            HttpStatusCode::is4xxClientError,
                            (req, response) -> {
                                throw new GatewayContractException(
                                        "Provider rejected HTTP request: "
                                        + response.getStatusCode());
                            })
                    .body(ProviderReply.class);

            if (reply == null || reply.status() == null) {
                throw new GatewayContractException(
                        "Empty/malformed provider response");
            }

            return switch (reply.status()) {
                case "AUTHORIZED" ->
                        new AuthorizationDecision.Authorized(
                                required(reply.authorizationId(),
                                        "authorizationId"));
                case "DECLINED" ->
                        new AuthorizationDecision.Declined(
                                required(reply.declineCode(),
                                        "declineCode"));
                default -> throw new GatewayContractException(
                        "Unexpected status: " + reply.status());
            };
        } catch (ResourceAccessException ex) {
            // Timeout/network reset: provider outcome chưa chắc chắn.
            throw new GatewayUnavailableException(
                    "Provider I/O failed; outcome unknown", ex);
        } catch (RestClientException ex) {
            // Bao gồm các lỗi Spring client/deserialization
            // không được custom onStatus xử lý trước đó.
            throw new GatewayContractException(
                    "Provider response could not be processed", ex);
        }
    }

    static long toMinorUnits(
            BigDecimal amount, String currencyCode) {
        Currency currency = Currency.getInstance(currencyCode);
        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Currency has no defined minor unit");
        }
        try {
            return amount.movePointRight(fractionDigits)
                    .longValueExact();
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Amount precision/size not supported", ex);
        }
    }

    private static String required(
            String value, String name) {
        if (value == null || value.isBlank()) {
            throw new GatewayContractException(
                    "Missing provider field: " + name);
        }
        return value;
    }

    public record ProviderRequest(
            String orderReference,
            long amountMinor,
            String currency) {}

    public record ProviderReply(
            String status,
            String authorizationId,
            String declineCode) {}
}
~~~

Trong ví dụ, `HttpPaymentGateway` nhận một `RestClient` đã cấu hình base URL, connect/read timeout, auth headers và connection settings. Bean production có thể được tạo qua `@Configuration` riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentAdapterConfiguration {

    @Bean
    PaymentGateway paymentGateway(
            RestClient.Builder builder,
            @Value("${payments.provider.base-url}") String baseUrl) {
        return new HttpPaymentGateway(
                builder.baseUrl(baseUrl).build());
    }
}
~~~

Cấu hình này đặt trong package nội bộ của `orders`; thêm imports Spring `@Bean`, `@Configuration`, `@Value`, `RestClient`, `PaymentGateway` và `HttpPaymentGateway`. **Không hard-code credential hoặc URL production trong tests.** Trong implementation thực cần cấu hình connect/read timeout, authentication, TLS và resilience; snippet tập trung vào contract request/response nên không coi các defaults là cấu hình production tối ưu.

### 9.1. Phân loại status phải căn cứ provider contract thực

`onStatus` ở trên:

- 429 và 5xx → `GatewayUnavailableException` để cấp trên quyết định retry/reconcile.
- Những 4xx còn lại → `GatewayContractException`: không giả làm `DECLINED`.
- 200 `AUTHORIZED`/`DECLINED` → domain decision theo response body.
- Body thiếu/unknown status → fail closed.

Nếu provider thật dùng `422` cho business decline hoặc `409` cho trạng thái idempotency đã tồn tại, adapter phải có mapping cụ thể được kiểm thử; **không bê nguyên bảng status của ví dụ cho mọi provider**.

Một status `202 Accepted` có thể là `PENDING`, không phải authorized; adapter hiện tại sẽ xem response không khớp contract nếu body không có `AUTHORIZED/DECLINED`. Điều đó đúng với **hợp đồng đã chọn**. Nếu provider có workflow pending, phải mở rộng `AuthorizationDecision` và xử lý hậu quả nghiệp vụ một cách tường minh.

### 9.2. Chuyển tiền không dùng float

Hàm `toMinorUnits` kiểm tra đổi `BigDecimal` thành integer **chính xác**, không tự làm tròn. Ví dụ:

~~~java
assertThat(HttpPaymentGateway.toMinorUnits(
        new BigDecimal("125000"), "VND"))
        .isEqualTo(125000L);

assertThat(HttpPaymentGateway.toMinorUnits(
        new BigDecimal("12.50"), "USD"))
        .isEqualTo(1250L);

assertThatThrownBy(() ->
        HttpPaymentGateway.toMinorUnits(
                new BigDecimal("125000.50"), "VND"))
        .isInstanceOf(IllegalArgumentException.class);
~~~

Đoạn test này đặt trong **cùng package** `com.example.shop.orders.internal.payment.http` vì helper có package-private visibility; hoặc đổi thành một `MoneySerializer` riêng nếu nhiều adapter dùng chung. Trường hợp fraction không biểu diễn được cần được quyết định bằng **validation/rounding policy được đặc tả**, không âm thầm cắt phần thập phân.

## 10. HTTP fake server kiểm chứng byte-level contract tốt hơn mock port

`MockRestServiceServer` có thể gắn vào `RestClient.Builder` để chặn request trong test và trả response giả lập. Khi đó **adapter thật** chạy, gồm URI, headers, serialization, error mapping và chuyển đổi minor units.

~~~java
package com.example.shop.orders.internal.payment.http;

import com.example.shop.orders.internal.payment.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class HttpPaymentGatewayWireContractTests {

    private MockRestServiceServer server;
    private HttpPaymentGateway gateway;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://payments.test");
        server = MockRestServiceServer.bindTo(builder).build();
        gateway = new HttpPaymentGateway(builder.build());
    }

    @Test
    void sendsContractFieldsAndMapsAuthorizedResponse() {
        UUID orderId = UUID.randomUUID();
        String key = "auth:v1:" + orderId;

        server.expect(requestTo(
                        "https://payments.test/v1/authorizations"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("Idempotency-Key", key))
                .andExpect(content().contentType(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.orderReference")
                        .value(orderId.toString()))
                .andExpect(jsonPath("$.amountMinor")
                        .value(125000))
                .andExpect(jsonPath("$.currency")
                        .value("VND"))
                .andRespond(withSuccess(
                        """
                        {"status":"AUTHORIZED",
                         "authorizationId":"pay_auth_77"}
                        """,
                        MediaType.APPLICATION_JSON));

        var result = gateway.authorize(
                new AuthorizationRequest(
                        orderId, new BigDecimal("125000"),
                        "VND", key));

        assertThat(result).isEqualTo(
                new AuthorizationDecision.Authorized(
                        "pay_auth_77"));
        server.verify();
    }

    @Test
    void mapsBusinessDeclineWithoutPretendingNetworkFailed() {
        UUID orderId = UUID.randomUUID();
        String key = "auth:v1:" + orderId;

        server.expect(requestTo(
                        "https://payments.test/v1/authorizations"))
                .andRespond(withSuccess(
                        """
                        {"status":"DECLINED",
                         "declineCode":"INSUFFICIENT_FUNDS"}
                        """,
                        MediaType.APPLICATION_JSON));

        var result = gateway.authorize(
                new AuthorizationRequest(
                        orderId, new BigDecimal("125000"),
                        "VND", key));

        assertThat(result).isEqualTo(
                new AuthorizationDecision.Declined(
                        "INSUFFICIENT_FUNDS"));
        server.verify();
    }
}
~~~

Hai tests trên **không thực hiện kết nối mạng** tới `payments.test`; request được `MockRestServiceServer` intercept. `requestTo`/header/jsonPath assertions chứng minh adapter tạo đúng request trong fixture, nhưng **chưa** chứng minh provider thật nhận những trường ấy. Trường hợp JSON body cần kiểm tra *không rò field PII*, thêm assertion body chỉ có các keys được phép hoặc schema validation.

### 10.1. Test lỗi 503 → retryable, không biến thành decline

Thêm vào cùng lớp:

~~~java
@Test
void http503MapsToGatewayUnavailable() {
    UUID orderId = UUID.randomUUID();

    server.expect(requestTo(
                    "https://payments.test/v1/authorizations"))
            .andRespond(withStatus(
                    HttpStatus.SERVICE_UNAVAILABLE));

    assertThatThrownBy(() -> gateway.authorize(
            new AuthorizationRequest(
                    orderId, new BigDecimal("125000"),
                    "VND", "auth:v1:" + orderId)))
            .isInstanceOf(GatewayUnavailableException.class);
    server.verify();
}
~~~

### 10.2. Test 401 → lỗi hợp đồng/cấu hình, không auto-decline

~~~java
@Test
void http401DoesNotBecomeBusinessDecline() {
    UUID orderId = UUID.randomUUID();

    server.expect(requestTo(
                    "https://payments.test/v1/authorizations"))
            .andRespond(withStatus(HttpStatus.UNAUTHORIZED));

    assertThatThrownBy(() -> gateway.authorize(
            new AuthorizationRequest(
                    orderId, new BigDecimal("125000"),
                    "VND", "auth:v1:" + orderId)))
            .isInstanceOf(GatewayContractException.class);
    server.verify();
}
~~~

### 10.3. Test response thiếu field → fail closed

~~~java
@Test
void missingAuthorizationIdIsContractViolation() {
    UUID orderId = UUID.randomUUID();

    server.expect(requestTo(
                    "https://payments.test/v1/authorizations"))
            .andRespond(withSuccess(
                    """
                    {"status":"AUTHORIZED"}
                    """,
                    MediaType.APPLICATION_JSON));

    assertThatThrownBy(() -> gateway.authorize(
            new AuthorizationRequest(
                    orderId, new BigDecimal("125000"),
                    "VND", "auth:v1:" + orderId)))
            .isInstanceOf(GatewayContractException.class)
            .hasMessageContaining("authorizationId");
    server.verify();
}
~~~

Tùy provider, bổ sung 429, 409/idempotency conflict, response `PENDING`, empty body, invalid JSON và network timeout theo contract thực. **Đừng tự stub 200 cho mọi tình huống:** chính việc phân loại outcome/error là ranh giới dễ bị hồi quy nhất.

## 11. Một HTTP fixture do ta viết chưa phải bằng chứng provider tuân thủ contract

Điểm dễ đánh đồng:

~~~text
Unit test:         CheckoutService ──> Mockito PaymentGateway
Adapter test:      HttpPaymentGateway ──> MockRestServiceServer
Provider contract: HttpPaymentGateway ──> API specification / sandbox
Reliability test:  Retry, crash, reconcile ──> durable outcomes
~~~

`MockRestServiceServer` chỉ thực hiện **những response do team tự cấu hình**. Nếu provider đã đổi JSON field `authorizationId` thành `authorization_id` mà fixture chưa cập nhật, adapter test vẫn xanh dù production deserialization sai.

Vì vậy, trước khi tuyên bố “đã kiểm chứng contract với provider”, cần có **một nguồn hợp đồng độc lập**:

| Nguồn | Mục tiêu | Cách duy trì |
| --- | --- | --- |
| OpenAPI/schema do provider phát hành | Tên fields, required/optional, status và errors. | Pin phiên bản, diff khi nâng version; validate request/response fixtures. |
| Provider sandbox | Adapter được provider thực nhận và trả response. | Smoke test với credentials test, tránh dữ liệu thật; cô lập quota/rate-limit. |
| Consumer-driven contract có provider verification | Nhà cung cấp xác nhận các expectations mà consumer cần. | Chạy provider verification khi triển khai version mới. |
| Sanitized interaction samples | Phát hiện payload thực khác fixture. | Loại bỏ secret/PII; cập nhật mẫu có kiểm duyệt. |
| Tài liệu error catalog và rate limit | Map 400/409/422/429/5xx đúng nghĩa. | Theo dõi thay đổi semantics, không chỉ HTTP status number. |

**Contract Java port** và **contract HTTP provider** là hai hợp đồng riêng biệt. Adapter chịu trách nhiệm chuyển đổi giữa chúng. `@MockitoBean PaymentGateway` bảo vệ consumer logic; HTTP fake server bảo vệ adapter; xác minh với nguồn provider độc lập giúp phát hiện drift.

### 11.1. Khi provider bổ sung status mới

Ví dụ response mới:

~~~json
{"status":"PENDING","reference":"async_922"}
~~~

Adapter hiện tại ném `GatewayContractException`, tức **fail closed**. Đó là hành vi an toàn cho contract chỉ có `AUTHORIZED/DECLINED`; nhưng khi team đồng ý hỗ trợ `PENDING`, cần cập nhật đồng bộ:

1. Contract Java `AuthorizationDecision` thêm `Pending` hoặc một trạng thái nghiệp vụ phù hợp.
2. Adapter nhận `PENDING` và kiểm tra `reference`.
3. Use case/recorder không đánh dấu `AUTHORIZED` sớm.
4. Có test polling/callback hoặc reconciliation riêng.
5. DB/event contract và migration được mở rộng trước khi deploy nếu cần.

Đừng “sửa nhanh” adapter bằng `default -> new Authorized(...)` chỉ để test xanh.

## 12. Retry: Mockito phải kiểm tra key ổn định, không chỉ số lần gọi

**Hợp đồng lý tưởng:** Một logical attempt có một idempotency key bất biến. Nếu client/worker gọi lại vì timeout, phải giữ key và payload tương đương, trừ khi protocol quy định cách xử lý khác.

### 12.1. Test hai lần gọi do caller chủ động thử lại

Trong unit test, stubbing kết quả liên tiếp **không tự tạo một retry**. Để minh họa, test chủ động gọi use case hai lần với cùng `orderId`:

~~~java
@Test
void explicitRetryReusesTheSameIdempotencyKey() {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    BigDecimal amount = new BigDecimal("125000");

    when(gateway.authorize(any(AuthorizationRequest.class)))
            .thenThrow(new GatewayUnavailableException(
                    "First attempt timed out"))
            .thenReturn(
                    new AuthorizationDecision.Authorized(
                            "pay_auth_77"));

    when(recorder.record(
            any(AuthorizationRequest.class), eq(customerId),
            any(AuthorizationDecision.class)))
            .thenReturn(PaymentStatus.AUTHORIZED);

    var checkout = new OrderCheckoutService(
            gateway, recorder);

    assertThatThrownBy(() ->
            checkout.authorize(orderId, customerId, amount, "VND"))
            .isInstanceOf(GatewayUnavailableException.class);

    assertThat(checkout.authorize(
            orderId, customerId, amount, "VND"))
            .isEqualTo(PaymentStatus.AUTHORIZED);

    var captor = ArgumentCaptor.forClass(
            AuthorizationRequest.class);
    verify(gateway, times(2)).authorize(captor.capture());

    var calls = captor.getAllValues();
    assertThat(calls).hasSize(2);
    assertThat(calls.get(0).idempotencyKey())
            .isEqualTo("auth:v1:" + orderId);
    assertThat(calls.get(1).idempotencyKey())
            .isEqualTo(calls.get(0).idempotencyKey());
    assertThat(calls.get(1).amount())
            .isEqualByComparingTo(calls.get(0).amount());
    assertThat(calls.get(1).currency())
            .isEqualTo(calls.get(0).currency());
}
~~~

Đặt test này trong `OrderCheckoutGatewayContractTests` của mục 7. **Câu khẳng định chính xác:** khi caller **chủ động** retry cùng logical order, service tạo cùng key/payload. Nó **không chứng minh** provider thực deduplicate, Spring Retry đã được cấu hình hay database/event không có duplicate sau recovery.

### 12.2. Lỗi cố ý cần bắt: sinh idempotency key ngẫu nhiên

~~~java
// SAI nếu mỗi retry là cùng một logical authorization attempt.
String key = UUID.randomUUID().toString();
~~~

Một test chỉ dùng `verify(gateway, times(2))` sẽ không phát hiện lỗi. Test **captor cả hai invocations** và so sánh key/payload mới có giá trị.

### 12.3. Không tái sử dụng cùng key với payload bị đổi

Giả sử khách sửa giỏ hàng sau timeout:

~~~text
Attempt 1: key=auth:v1:ORDER-1, amountMinor=125000
Attempt 2: key=auth:v1:ORDER-1, amountMinor=130000
~~~

Đây có thể là **idempotency conflict**; nếu provider lưu request gốc theo key, kết quả trả lại có thể tương ứng **125000**, không phải **130000**. Mẫu `OrderCheckoutService` ở mục 5 chưa khóa invariant “cùng order ID phải giữ amount/currency” trước khi gọi gateway, vì vậy **không đủ để triển khai retry trong production**.

Một thiết kế hoàn chỉnh cần:

- Ghi logical attempt và request hash/amount/currency trước khi gọi provider.
- Từ chối payload bị thay đổi khi dùng lại cùng key.
- Hoặc tạo **attempt ID mới được quản lý bền vững** với key mới khi nghiệp vụ cho phép thử một giao dịch khác.
- Kiểm tra chính sách provider cho HTTP 409, key expiration và replay.

Test nên xác minh **sai payload không tạo outbound request mới dưới cùng key**. Nếu không có state store, unit mock đơn lẻ không thể chứng minh invariant xuyên qua process restarts.

## 13. Partial failure: provider thành công nhưng local transaction thất bại

Trong mẫu này, network call diễn ra **trước** recorder transaction:

~~~mermaid
sequenceDiagram
    participant Checkout as OrderCheckoutService
    participant Provider as External Payment
    participant Recorder as AuthorizationRecorder
    participant DB as PaymentAttempt DB
    Checkout->>Provider: authorize(key K)
    Provider-->>Checkout: AUTHORIZED auth_77
    Checkout->>Recorder: record(AUTHORIZED)
    Recorder->>DB: save row
    alt Commit succeeds
        DB-->>Checkout: Committed
    else DB failure / crash
        DB-->>Checkout: Rolled back / unknown
        Note over Provider,DB: Provider auth_77 may still exist
    end
~~~

**Không có database transaction nào rollback được một authorization đã thành công bên provider.** Tương tự, nếu adapter trả `GatewayUnavailableException` vì timeout, provider cũng có thể đã xử lý request.

### 13.1. Một test unit ghi nhận failure window, không giả kết quả

~~~java
@Test
void recorderFailureIsNotMistakenForGatewayDecline() {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    var approved =
            new AuthorizationDecision.Authorized("pay_auth_77");

    when(gateway.authorize(any(AuthorizationRequest.class)))
            .thenReturn(approved);
    when(recorder.record(
            any(AuthorizationRequest.class),
            eq(customerId), eq(approved)))
            .thenThrow(new IllegalStateException(
                    "Simulated database failure"));

    var checkout = new OrderCheckoutService(
            gateway, recorder);

    assertThatThrownBy(() ->
            checkout.authorize(
                    orderId, customerId,
                    new BigDecimal("125000"), "VND"))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("database");

    verify(gateway).authorize(
            any(AuthorizationRequest.class));
}
~~~

Kết luận chỉ là **service không nuốt lỗi recorder để giả thành `DECLINED`**. Vì recorder mock, test chưa chứng minh rollback JPA. Ngược lại, provider đã trả `Authorized` trong test, nên không được kết luận “không có authorization”.

### 13.2. Hướng triển khai production cần thêm contract bền vững

Tùy nghiệp vụ, một workflow đáng tin hơn có thể:

1. Lưu một attempt `PENDING` với `idempotencyKey` và **request fingerprint** trong transaction ban đầu.
2. Commit attempt, rồi mới gọi gateway qua worker/command có recovery.
3. Ghi outcome với unique constraint và optimistic locking/compare-and-set.
4. Khi timeout: hỏi provider trạng thái theo key/reference hoặc retry **cùng key** nếu provider có idempotency guarantee.
5. Khi provider authorized nhưng local DB thất bại: retry ghi outcome/reconcile, không tự coi payment bị decline.
6. Khi phát event: giữ stable event identity/logical transition, hoặc dùng durable event publication/outbox và consumer idempotency theo yêu cầu.

Trong kiến trúc ấy, unit/module tests phải kiểm tra `PENDING → AUTHORIZED/DECLINED`, retry/recovery và **không xuất hiện hai final outcomes** cho cùng key. Các test ở mục 8 minh họa *đường xử lý đồng bộ đơn giản*, không nên tái sử dụng chúng nguyên trạng để tuyên bố một payment workflow an toàn khi crash.

### 13.3. Exactly-once có ít nhất ba nghĩa

| Phát biểu | Phép kiểm chứng |
| --- | --- |
| Một command gọi `PaymentGateway.authorize` một lần trong unit test. | `verify(gateway, times(1))`. |
| Provider nhận nhiều attempts có cùng key nhưng chỉ tạo một authorization. | Provider sandbox/contract và reconciliation/integration test. |
| Internal DB/event/consumer chỉ phản ánh một logical payment transition dù retry. | Unique constraint, idempotency marker, state machine và crash/replay tests. |

Không dùng câu thứ nhất để suy ra câu thứ hai hoặc thứ ba.

## 14. Timeout/retry policy: đừng cho mock tự quyết định production behavior

Một mock:

~~~java
when(gateway.authorize(any()))
        .thenThrow(new GatewayUnavailableException("timeout"))
        .thenReturn(new AuthorizationDecision.Authorized("auth-77"));
~~~

không có nghĩa Spring Retry/Resilience4j đã **thử lại**. Nó chỉ xếp các kết quả cho hai invocation *nếu có*. Khi code không gọi lại, test có thể never reach nhánh thứ hai; khi thêm `@Retryable`, lời gọi qua Spring proxy hoặc `RetryTemplate` cần được test riêng.

### 14.1. Các quyết định phải được ghi trong contract

| Điều kiện | Câu hỏi chính sách |
| --- | --- |
| HTTP 429 | Có `Retry-After` không? Tôn trọng rate limit thế nào? |
| HTTP 503 | Max attempts, exponential backoff, jitter, deadline và circuit breaker? |
| Timeout | Provider có tra cứu outcome theo idempotency key/reference không? |
| 401/403 | Không retry vô hạn; credential/configuration có lỗi? |
| 400/422 | Input validation hay business decline theo provider spec? |
| 409 | Key bị dùng cho payload khác hay authorization đã tồn tại? |
| Trả `PENDING` | Callback/polling nào xác nhận final outcome? |
| Process restart | Attempt/key/status có được lưu bền vững để resume? |

**Không tự động retry mọi `RuntimeException`**: một lỗi validation, contract violation hoặc authorization declined có thể không thể phục hồi bằng retry; ngược lại timeout có thể cần reconciliation thay vì gửi lại vô tội vạ.

### 14.2. Test backoff mà không ngủ thật

Nếu ứng dụng có retry policy với backoff, hãy tách `RetryPolicy`, clock/scheduler hoặc dùng test harness của resilience library để điều khiển attempts. Unit test kiểm tra **attempt classification và key reuse**; integration test kiểm tra timeout/budget/cancellation và state recovery. Tránh `Thread.sleep` dài trong CI chỉ để chứng minh vài dòng business logic.

## 15. Gateway đồng bộ, bất đồng bộ và nguy cơ gọi side effect sau assertion

Port trong ví dụ là đồng bộ:

~~~java
AuthorizationDecision authorize(AuthorizationRequest request);
~~~

Nếu thiết kế thật dùng `CompletableFuture<AuthorizationDecision>`, reactive `Mono` hoặc callback, **thời điểm có result không còn đồng nghĩa method return**. Mockito test cần mô phỏng future completion/error/cancellation đúng contract:

~~~java
CompletableFuture<AuthorizationDecision> future =
        new CompletableFuture<>();
when(asyncGateway.authorize(any())).thenReturn(future);

// Trigger command, assert chưa có final outcome.
future.complete(new AuthorizationDecision.Authorized("auth-77"));
// Chờ observable state ở module, không sleep tùy tiện.
~~~

Đây là **snippet thiết kế cho một AsyncPaymentGateway khác**, không phải code compile nguyên trạng với interface đồng bộ của mục 4. Khi async gateway, phải kiểm tra duplicate completion, error channel, executor transaction propagation và shutdown/cancellation.

### 15.1. Không dùng verify(timeout) làm bằng chứng không có duplicate muộn

`verify(gateway, timeout(2_000).times(1)).authorize(...)` có thể pass ngay khi invocation đầu tiên xuất hiện, rồi call thứ hai đến sau. Nếu yêu cầu không duplicate request/side effect, hãy kiểm tra theo business key/idempotency và cửa sổ thời gian/lifecycle có kiểm soát, không dựa vào một timeout matcher.

### 15.2. Event publication và transaction là một boundary khác

`AuthorizationRecorder` phát `PaymentAuthorized` **trong transaction** lưu row. `PublishedEvents` có thể quan sát event đã phát nhưng **không bảo đảm listener `AFTER_COMMIT` đã chạy**. Nếu transaction cuối cùng rollback do lỗi flush/commit, việc gọi `publishEvent` có thể vẫn đã xảy ra.

Khi mục tiêu là listener Spring Modulith:

- Test receiver với `@ApplicationModuleListener` thật, datasource và transaction commit.
- Chờ state/side effect qua `Scenario` hoặc Awaitility thay vì mock publisher.
- Dùng Event Publication Registry integration test nếu cần incomplete/completed/recovery theo target.
- Không coi mock gateway `Authorized` là bằng chứng provider đã tạo external authorization thật.

## 16. Chọn test double theo ranh giới, không theo sự tiện tay

| Thành phần | Test `orders` module | Test HTTP adapter | Test với provider |
| --- | --- | --- | --- |
| `OrderCheckoutService` | **Thật** | Không cần bootstrap | Tùy phạm vi end-to-end |
| `AuthorizationRecorder` | **Thật**, để kiểm tra transaction | Không cần | Có thể thật trong scenario tích hợp |
| `PaymentAttemptRepository` | **Thật**, JPA/database | Không cần | Thật nếu kiểm tra recovery |
| `ApplicationEventPublisher` | **Thật**, `PublishedEvents` | Không cần | Thật nếu cần event delivery |
| `PaymentGateway` port | **`@MockitoBean`** | Implementation **thật** | Implementation thật |
| HTTP server bên ngoài | Không được gọi | **`MockRestServiceServer`** | Provider sandbox/test server |

**Khi nào `@MockitoSpyBean PaymentGateway` là lựa chọn nguy hiểm?** Nếu bean thực là `HttpPaymentGateway`, spy thường chạy method thật khi chưa stub; `when(spy.authorize(request))` còn có thể thực hiện HTTP request **ngay lúc setup**. Không nên spy trực tiếp một outbound gateway có khả năng ủy quyền/charge thật. Dùng mock port cho module test, fake server cho adapter test.

### 16.1. STANDALONE hay DIRECT_DEPENDENCIES?

Trong ví dụ, gateway port và adapter đều thuộc **module `orders`**, nên `@MockitoBean PaymentGateway` thay bean tại I/O boundary dù mode `STANDALONE`. `DIRECT_DEPENDENCIES` không cần thiết để “kiểm chứng HTTP thật”; adapter test dùng RestClient với fake server là đủ.

Nếu payment integration thuộc một application module riêng, hãy công bố `payments :: api` và để `orders` phụ thuộc interface ấy. Khi test riêng `orders`, mock public API; khi cần kiểm tra wiring giữa hai module thật, chọn `DIRECT_DEPENDENCIES`/integration test thích hợp **không override interface đang được kiểm chứng**.

### 16.2. Fake gateway có state được dùng khi nào?

Một in-memory fake có thể giữ map `idempotencyKey → decision` và trả cùng response cho request trùng key; nó hữu ích để test workflow nhiều bước, nhưng **không chứng minh provider HTTP có idempotency**. Chỉ dùng fake như mô hình behavior của provider có **nguồn contract xác nhận**, không đưa cơ chế do team tự giả định thành sự thật về provider.

## 17. Ranh giới Spring Modulith và quality gate kiến trúc

Trong thiết kế port/adapter cùng `orders`, `orders.internal.payment.http.HttpPaymentGateway` được phép dùng port nội bộ của chính module. Nhưng module `shipping` không nên import `orders.internal.payment.PaymentAttemptRepository` hoặc `HttpPaymentGateway`. Nếu cần phản ứng khi payment authorized, nó chỉ nên nhận **public event** như `orders :: events`.

File `shipping/package-info.java` có thể định nghĩa:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders :: events")
package com.example.shop.shipping;
~~~

Và architecture test:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` phát hiện dependency graph/cycle, truy cập package không public/named interface và `allowedDependencies` violations theo mô hình Spring Modulith. Nó **không thể xác định** JSON gửi provider có đúng `amountMinor` hoặc header `Idempotency-Key` hay không. Đó là trách nhiệm của contract/wire tests.

### 17.1. Nếu PaymentGateway được tách thành module integrations

Một biến thể:

~~~text
payments
└── api
    ├── PaymentAuthorizationGateway.java
    └── package-info.java  → @NamedInterface("api")

orders
└── package-info.java → allowedDependencies = "payments :: api"
~~~

Khi đó **port được sở hữu bởi `payments` module** (khác với mã mẫu đang sở hữu trong `orders`); mọi code thuộc `orders` phải import đúng API công bố. Không sao chép cả hai kiến trúc vào cùng một hệ thống rồi có hai bean `PaymentGateway` khó phân giải. Chọn một ownership model phù hợp, test boundary tương ứng.

## 18. Quality gate CI theo rủi ro thay đổi hợp đồng

| Gate | Assertion trọng tâm | Khi nào chạy |
| --- | --- | --- |
| **Port contract unit** | Amount/currency/orderId/idempotency key bằng captor; invalid input không gọi gateway. | Mỗi pull request. |
| **Outcome matrix** | AUTHORIZED, DECLINED, unknown failure tạo đúng state/event hoặc exception. | Mỗi pull request. |
| **Modulith module test** | Gateway mock, nhưng DB transaction và `PublishedEvents` thật. | Mỗi pull request nếu hạ tầng test đủ nhanh. |
| **HTTP adapter test** | Method, URL, header, `amountMinor`, response schema và 401/429/503 mapping. | Mỗi thay đổi adapter; tốt nhất mỗi PR. |
| **Provider contract verification** | Versioned schema, provider sandbox/consumer contract hợp lệ. | Khi nâng API/provider version, và theo lịch để phát hiện drift. |
| **Idempotency/recovery** | Same key across attempts, request fingerprint, no duplicate final transition/event. | Integration stage cho thay đổi retry/persistence. |
| **Failure windows** | Provider authorized nhưng DB fail; timeout unknown; process recovery. | Resilience/integration stage. |
| **Database constraints** | Unique orderId/key, rollback/commit và migration đúng. | JPA/DB production-like integration. |
| **Event publication/receiver** | AFTER_COMMIT, registry incomplete/completed, consumer idempotency. | Event/integration stage. |
| **Architecture** | `ApplicationModules.verify()`. | Mỗi PR. |
| **Security/privacy** | Không gửi PII ngoài hợp đồng; không log credentials, keys hoặc payload nhạy cảm. | Static checks, adapter/observability tests. |

Không phải mọi PR đều cần gọi sandbox có quota, nhưng **wire tests với fake server nên chạy nhanh và thường xuyên**. Sandbox/provider-contract stage cần pin API version, giữ secrets ở CI secret store và không dùng dữ liệu/thanh toán thật.

### 18.1. Điều gì phải làm đỏ CI?

Một PR nên bị chặn nếu:

- Đổi `Idempotency-Key` thành UUID mới cho mỗi retry.
- Chuyển `125000 VND` thành `12500000` minor units do nhân 100 sai.
- Biến `DECLINED` hoặc 401 thành `AUTHORIZED`.
- Bỏ `authorizationId` khỏi event thành công hoặc phát `PaymentAuthorized` khi decline.
- Cho input `amount=0` vẫn gọi provider.
- Đổi tên JSON field hoặc route mà adapter test không được cập nhật với provider contract.
- Bỏ unique constraint hoặc để retry sinh hai final outcomes.
- Module khác import `orders.internal.payment` thay vì public event/API.

Một refactor hợp lệ như đổi tên helper nội bộ, đổi thứ tự validation không ảnh hưởng observable contract, hoặc thay HTTP client library mà giữ wire contract **không nên** làm unit/module tests thất bại. Đó là lý do ta assert **điều khoản hợp đồng**, không verify mọi method nội bộ.

## 19. Anti-pattern cần nhận diện

### 19.1. Stub trả thành công cho mọi request nhưng không assert argument

~~~java
when(gateway.authorize(any())).thenReturn(
        new AuthorizationDecision.Authorized("auth-1"));
checkout.authorize(orderId, customerId, amount, currency);
verify(gateway).authorize(any());
~~~

Không phát hiện sai amount, currency hoặc key. Dùng typed captor và đối chiếu từng field nghiệp vụ.

### 19.2. Giả lập business decline bằng exception chung

~~~java
when(gateway.authorize(any()))
        .thenThrow(new RuntimeException("DECLINED"));
~~~

Không khớp contract khi provider trả `200 DECLINED`. Dùng kiểu `Declined`; để lỗi network/contract trong exception được phân loại.

### 19.3. Catch mọi exception rồi xem là khách bị từ chối

~~~java
try {
    return gateway.authorize(request);
} catch (RuntimeException ex) {
    return new AuthorizationDecision.Declined("FAILED");
}
~~~

Timeout unknown outcome có thể đã authorized. Không ghi kết quả decline sai; cần retry/reconciliation policy.

### 19.4. Bỏ idempotency header trong test HTTP

Test mock Java port vẫn pass vì nó không thực thi adapter. Wire test phải assert `Idempotency-Key` header thật và sự ổn định qua attempts.

### 19.5. Chuyển đổi tiền qua double hoặc nhân 100 bất kể currency

`BigDecimal.doubleValue()` hoặc `amount * 100` có thể sai precision/minor units. Kiểm tra VND, USD và input fractional/overflow.

### 19.6. Mock repository trong module test cần chứng minh persist

`verify(repository.save(...))` không có bằng chứng transaction/DB. Giữ recorder/repository thật, mock duy nhất gateway I/O.

### 19.7. Spy một outbound gateway có real HTTP side effect

`when(spy.authorize(...))` có thể gọi provider trước SUT. Đừng dùng spy như một cách “mock nhưng vẫn thật hơn” cho thanh toán.

### 19.8. Dùng giả định tự tạo làm provider contract

Fake server trả JSON do ta viết vẫn xanh khi provider đã đổi schema. Pin specification và xác minh sandbox/CDC khi cần.

### 19.9. Retry mọi 4xx hoặc mỗi attempt dùng key mới

401 có thể là lỗi credential; 409 có thể là idempotency conflict; thay key trên timeout có thể tạo double authorization. Retry theo error catalog và key policy.

### 19.10. Coi event đã phát là provider đã thanh toán

`PaymentAuthorized` là **event nội bộ ghi nhận outcome mà adapter thông báo**, không phải chứng từ settlement hoặc capture. `PublishedEvents` càng không chứng minh external charge thực.

## 20. Bài tập kiểm chứng: nhận diện lỗi contract qua test

Một team mới tích hợp provider `v2` và có yêu cầu:

~~~text
POST /v2/authorizations
Header: Idempotency-Key = "auth:" + attemptId ổn định
Body: {orderReference, amountMinor, currency}

200 {status: AUTHORIZED, authorizationId}
200 {status: DECLINED, declineCode}
202 {status: PENDING, providerReference}
429/5xx: transient; 401/403: credential/config
409: idempotency-key conflict hoặc replay, tra cứu theo providerReference
~~~

Một test hiện tại chỉ là:

~~~java
when(gateway.authorize(any()))
        .thenReturn(new AuthorizationDecision.Authorized("x"));
checkout.authorize(orderId, customerId, amount, currency);
verify(gateway).authorize(any());
~~~

### Câu hỏi

1. Test đang thiếu các assertions nào để bảo vệ request contract?
2. `Idempotency-Key` thuộc request header hay body? Test tầng nào chứng minh nó thực sự xuất hiện trên HTTP?
3. Nếu amount `12.50 USD`, `amountMinor` phải là bao nhiêu theo contract giả định?
4. Nếu `200 DECLINED`, có nên ném `GatewayUnavailableException` không?
5. Nếu `202 PENDING` xuất hiện lần đầu, adapter có nên coi là `AUTHORIZED` để tránh crash không?
6. Nếu provider trả 503, nên verify điều gì ở module và điều gì ở adapter?
7. Nếu request timed out nhưng provider đã authorized, tại sao retry với key mới có thể nguy hiểm?
8. Nếu `PaymentGateway` được mock trong `@ApplicationModuleTest`, test có chứng minh HTTP serialization đúng không?
9. Provider đổi `authorizationId` thành `authorization_id`, loại test nào phát hiện nếu fixture chưa được cập nhật?
10. Nếu recorder DB lỗi sau provider authorized, `@Transactional` có rollback được authorization của provider không?
11. Có nên đếm `times(1)` trên mock gateway rồi khẳng định business effect exactly-once không?
12. Nếu module `shipping` trực tiếp dùng `orders.internal.payment.PaymentAttemptRepository`, gate nào phải bắt lỗi?

### Đáp án gợi ý

1. Capture `AuthorizationRequest` và assert `orderId`, amount, currency, key; invalid input có `verifyNoInteractions(gateway)`.
2. Header HTTP; dùng adapter test `MockRestServiceServer`/fake server, rồi kiểm chứng nguồn contract provider độc lập.
3. `1250` minor units, tính chính xác không qua `double`.
4. Không. `DECLINED` là business outcome; lưu trạng thái decline, không phát event authorized.
5. Không. Cần `Pending` và workflow xác nhận hoặc fail closed cho đến khi hỗ trợ được phê duyệt.
6. Adapter: 503 → `GatewayUnavailableException`. Module: không lưu final outcome giả; retry/reconciliation policy xử lý trạng thái unknown.
7. Key mới có thể khiến provider xem đó là giao dịch mới và ủy quyền trùng.
8. Không. Mock port chỉ chứng minh request Java và reaction; wire test kiểm tra serialization, URL, headers.
9. Provider sandbox/CDC hoặc contract/schema validation từ specification độc lập; fake fixture cũ không tự phát hiện drift.
10. Không. DB transaction chỉ rollback state local; provider là hệ thống bên ngoài cần idempotency/reconciliation/compensation.
11. Không. Invocation count trong một JVM không chứng minh dedup bên ngoài hoặc durable exactly-once.
12. `ApplicationModules.of(...).verify()` phát hiện truy cập package/module API không công bố hoặc vi phạm dependencies.

## 21. Checklist trước khi merge gateway contract tests

- [ ] Port `PaymentGateway` mô tả rõ request, `Authorized`, `Declined` và typed integration errors.
- [ ] Input gồm `orderId`, amount chính xác, currency và idempotency key ổn định; không gửi PII ngoài contract.
- [ ] Test success dùng typed `ArgumentCaptor` hoặc exact expected request; không dừng ở `verify(any())`.
- [ ] Test invalid input **không gọi** gateway và không tạo local final outcome.
- [ ] Test `DECLINED` lưu đúng reason và không phát `PaymentAuthorized`.
- [ ] Test gateway timeout/unknown outcome không bị chuyển thành business decline hoặc authorized giả.
- [ ] Test retry so sánh key/payload qua **nhiều invocations**, không chỉ đếm `times(2)`.
- [ ] Có cơ chế cấm cùng key nhưng amount/currency thay đổi, hoặc chỉ ra rõ đây là gap chưa triển khai.
- [ ] Module test giữ `AuthorizationRecorder`, JPA repository, transaction và Spring publisher thật.
- [ ] HTTP adapter test giữ `HttpPaymentGateway` thật, mock **server** chứ không mock port.
- [ ] Assert URL, HTTP method, `Idempotency-Key`, content type và chính xác các JSON fields.
- [ ] Test money minor-unit conversion cho currency được hỗ trợ, fractional input không hợp lệ và overflow.
- [ ] Test `AUTHORIZED`, `DECLINED`, missing field/unknown status, 401/409, 429/5xx theo provider spec.
- [ ] Không coi self-authored fake-server fixtures là bằng chứng provider production tương thích.
- [ ] Có schema/sandbox hoặc consumer-driven provider verification khi rủi ro/tần suất thay đổi yêu cầu.
- [ ] Connect/read timeout, auth, TLS, rate limit và `Retry-After` được thiết kế/kiểm tra ở adapter hoặc resilience layer.
- [ ] Có chính sách durable `PENDING`/reconciliation nếu side effect cần phục hồi sau crash.
- [ ] DB unique key, transaction rollback và event idempotency có integration tests khi retry quan trọng.
- [ ] Event `PaymentAuthorized` không bị nhầm với external charge/settlement hoặc listener completion.
- [ ] Không dùng `@MockitoSpyBean` để vô tình thực thi gateway gửi HTTP.
- [ ] `ApplicationModules.verify()` và CI contract/migration/integration gates đều được chạy theo phạm vi.

**Kết luận:** Mock external gateway “theo contract” không chỉ là làm `when(...).thenReturn(...)` để service chạy được. Bài test có giá trị khi nó ràng buộc **dữ liệu gửi ra, ý nghĩa outcome, phân loại lỗi và hành vi khi side effect bị cấm**. Trong Spring Modulith, `@MockitoBean PaymentGateway` giúp cô lập I/O nhưng vẫn cho phép kiểm chứng service, transaction, repository và `PublishedEvents` thật; HTTP adapter test kiểm tra request/response ở wire boundary; provider contract và retry/reconciliation integration tests bảo vệ những gì mock không thể chứng minh. Tách đúng tầng bằng chứng giúp test bớt giòn và tránh cảm giác an toàn giả, đặc biệt với idempotency và failure windows của payment workflows.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, bootstrap modes và `PublishedEvents`.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): module API/named interface, `allowedDependencies` và `verify()`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event publication, listener transaction và registry.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, request/response và error handling.
- [Spring Framework — MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): fake HTTP server cho synchronous REST clients.
- [Spring Framework — MockitoBean/MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean overrides trong Spring Test.
- [Mockito — API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/Mockito.html): captors, typed matchers, `verify` và interaction verification.
- [Java SE — Currency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html): ISO 4217, default fraction digits.

> Ghi chú áp dụng: Ví dụ minh họa Spring Framework 6.2+, Spring Modulith, Spring Data JPA, Mockito, JUnit 5 và Java 17+; `RestClient` có từ Spring Framework 6.1. Cấu hình schema, datasource, JSON converter, timeout, authentication và bean registration phải được bổ sung đúng theo project. HTTP status semantics và minor units **phải đối chiếu provider thực**, không xem bảng contract giả định là tiêu chuẩn chung. Workflow minh họa chưa cung cấp durable retry/idempotent finalization hoàn chỉnh. Theo STEP_4, tài liệu mới được biên soạn; chưa chạy Gradle hoặc vòng Content QA chuyên môn.



