# Mono, Flux và thời điểm thực hiện yêu cầu

## 1. Đặt vấn đề: viết lệnh gọi Vault chưa chắc đã gọi Vault

Ứng dụng Java dùng **Spring Vault** có thể giao tiếp với HashiCorp Vault theo kiểu imperative qua `VaultTemplate`, hoặc theo kiểu reactive qua `ReactiveVaultTemplate` và `ReactiveVaultOperations`. Trong hệ thống dùng Spring WebFlux/Reactor, API reactive giúp mô tả những thao tác I/O bất đồng bộ dưới dạng một chuỗi có thể kết hợp, kiểm soát lỗi và tín hiệu hủy.

Điểm nền tảng của chương **API reactive** là **thời điểm thực hiện yêu cầu**:

~~~java
Mono<VaultResponse> result = vault.read("sys/health");

// Đoạn trên tạo Publisher biểu diễn thao tác.
// Không có nghĩa đã chờ Vault trả response.
~~~

Thông thường, `Publisher` của một lời gọi reactive Vault là **cold**: xây dựng pipeline không tự động gửi HTTP request; **subscription** mới kích hoạt luồng xử lý. Nếu không có subscriber, bạn có thể viết rất nhiều toán tử `map`, `flatMap`, `timeout` nhưng sẽ không nhận được dữ liệu. Nếu subscribe nhiều lần vào publisher cold, thao tác nguồn có thể được thực hiện lại nhiều lần.

Bài học thuộc module **SPRING_VAULT**: ứng dụng Java sử dụng Vault theo danh tính workload, policy phân quyền, đọc KV secrets, quản lý vòng đời token/lease, Transit encryption và PKI. Reactive API **không bỏ qua** xác thực, ACL, token expiry, lease lifecycle hay những lỗi mà Vault có thể trả về.

Sau bài này, bạn có thể:

1. Phân biệt `Mono<T>`, `Flux<T>` và tín hiệu `onNext`/`onComplete`/`onError`.
2. Chỉ ra lúc **assembly**, **subscription** và **execution** xảy ra khi gọi Vault.
3. Viết WebFlux endpoint trả `Mono` mà không gọi `block()` hay `subscribe()` thủ công.
4. Giải thích vì sao nhiều subscriber, `retry`, `cache` có thể làm thay đổi số lần truy cập Vault hoặc độ mới dữ liệu.
5. Kiểm thử behavior với Reactor `StepVerifier` và với Vault sandbox.

## 2. Mono và Flux khác nhau ở đâu?

| Đặc điểm | `Mono<T>` | `Flux<T>` |
| --- | --- | --- |
| Số giá trị `onNext` | **0 hoặc 1** | **0 đến nhiều** |
| Kết thúc thành công | `onComplete` | `onComplete` |
| Thất bại | Một `onError` kết thúc luồng | Một `onError` kết thúc luồng |
| Thường dùng trong Spring Vault | `read`, `write`, `delete`, `get` KV | `list` key |
| Khi không có dữ liệu | `Mono.empty()` | `Flux.empty()` |
| Khi kết thúc chỉ báo hoàn tất | `Mono<Void>` | Có thể dùng `Flux` nhưng không cần thiết nếu chỉ báo một thao tác |

Ví dụ API Spring Vault:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.support.VaultResponse;

// vault được inject như một bean đã cấu hình.
Mono<VaultResponse> response = vault.read("database/creds/readonly");
Flux<String> keys = vault.list("secret/metadata/apps");
Mono<Void> deleted = vault.delete("some/path");
~~~

Các ví dụ trên chỉ minh họa **kiểu trả về**. Đường dẫn `database/creds/readonly` nếu được subscribe có thể phát hành credential động có lease mới; `secret/metadata/apps` phù hợp với thao tác list của KV v2 qua API Vault cấp thấp; `some/path` chỉ là placeholder, tuyệt đối không chạy lệnh xóa trên path thật nếu chưa xác định phạm vi.

**Cần nhớ:** `Flux` không có nghĩa Vault cung cấp một HTTP response streaming liên tục. Một thao tác `list` thông thường thực hiện **một request tới Vault**, nhận danh sách rồi phát các key trong response thành nhiều `onNext`. Backpressure điều tiết subscriber phía JVM; nó không nhất thiết khiến Vault phát sinh request riêng cho mỗi key.

## 3. Ba giai đoạn: assembly, subscription, signal

~~~mermaid
sequenceDiagram
    participant Code as Service method
    participant Pub as Mono / Flux
    participant Sub as WebFlux subscriber
    participant Vault as Vault HTTP API

    Code->>Pub: Assembly: vault.read(...).map(...)
    Note over Pub,Vault: Chưa có HTTP request của thao tác đọc
    Code-->>Sub: Trả Publisher
    Sub->>Pub: subscribe() + request(n)
    Pub->>Vault: Gửi yêu cầu reactive HTTP
    Vault-->>Pub: Response / lỗi / empty
    Pub-->>Sub: onNext(data) nếu có
    Pub-->>Sub: onComplete hoặc onError
~~~

**Assembly** là lúc Java xây dựng đồ thị toán tử. **Subscription** là lúc một subscriber đăng ký nhận dữ liệu và phát nhu cầu (`request(n)`); các operator phía nguồn bắt đầu hoạt động. **Signal** là những sự kiện `onNext`, `onError`, `onComplete`; kết thúc một luồng là thành công hoặc lỗi, không phải cả hai.

Có một ngoại lệ kiến trúc quan trọng: khởi tạo **Vault client/session/token supplier** có lifecycle riêng. Tùy cấu hình Spring Vault, Spring context có thể xác thực hoặc làm những bước khởi tạo I/O **trước subscription của thao tác nghiệp vụ**. Vì vậy, phát biểu đúng là: *publisher cold biểu diễn thao tác đọc/ghi thường chỉ thực hiện thao tác đó khi được subscribe*, **không phải** *toàn bộ ứng dụng Spring Vault chắc chắn không kết nối Vault trước khi có subscription nào*.

### Vì sao cold publisher dẫn tới nhiều HTTP request?

~~~java
Mono<VaultResponse> operation = vault.read("sys/health");

// Giả sử đây là một Mono cold chưa cache.
operation.subscribe(a -> onFirstResult(a));
operation.subscribe(b -> onSecondResult(b));
~~~

Hai subscription **có thể tạo hai lần yêu cầu đọc** độc lập. Nếu nguồn là `database/creds/readonly`, điều này còn có thể tạo **hai dynamic credentials/leases**. Đừng gọi `subscribe()` ở nhiều nơi với giả định đang dùng chung một kết quả.

`onFirstResult` và `onSecondResult` ở ví dụ là hàm callback minh họa, không phải API có sẵn. Trong ứng dụng WebFlux, thông thường hãy **trả Publisher cho framework** thay vì tự gọi `subscribe()` trong service hoặc controller.

### Hot publisher và cache khác cold như thế nào?

- **Cold**: nguồn được chạy riêng theo từng subscription.
- **Hot**: nguồn có thể phát dữ liệu không phụ thuộc từng subscriber; subscriber mới có thể chỉ thấy sự kiện về sau.
- **`cache()` / `share()`**: các operator có thể thay đổi cách nhiều subscriber chia sẻ hoặc phát lại dữ liệu; **không mặc định phù hợp cho secrets**.

Ví dụ `vault.read(...).cache()` có thể giữ `VaultResponse` và bí mật trong bộ nhớ, trả dữ liệu **stale** sau khi Vault đã rotate/revoke secret. Khi dùng `cache(Duration)` cần xác định TTL hợp lý, cơ chế invalidation, phạm vi người dùng/tenant và sự cố bảo mật; không cache tràn lan chỉ nhằm giảm số lần request.

## 4. Cấu hình ReactiveVaultTemplate trong Spring

Spring Vault cung cấp `ReactiveVaultOperations` là interface sử dụng chính, `ReactiveVaultTemplate` là implementation. Client reactive dùng `WebClient` và hỗ trợ I/O không chặn ở lớp HTTP; không nên lấy `VaultTemplate` kiểu imperative rồi gọi `Mono.just(vaultTemplate.read(...))` và coi đó là reactive.

Để cấu hình trong Spring, có thể kế thừa `AbstractReactiveVaultConfiguration`. Ví dụ **chỉ dùng ở dev/lab** với Vault token ngắn hạn được cấp trước:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractReactiveVaultConfiguration;

@Configuration
public class VaultReactiveConfiguration
        extends AbstractReactiveVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        String url = System.getenv().getOrDefault(
                "VAULT_ADDR", "http://127.0.0.1:8200");
        return VaultEndpoint.from(URI.create(url));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String token = System.getenv("VAULT_APP_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException("VAULT_APP_TOKEN missing");
        }
        return new TokenAuthentication(token);
    }
}
~~~

Lớp cấu hình cung cấp thành phần reactive và quản lý session tương ứng; chi tiết tự xác thực/gia hạn token phụ thuộc phiên bản và auth method. Ở production hãy dùng **workload authentication** (Kubernetes, AppRole, IAM...) và kết nối **HTTPS với CA tin cậy**. Token môi trường của ví dụ chỉ giúp làm rõ thời điểm subscription của *thao tác Vault*, không phải phương án quản lý token dài hạn.

Từ Spring Vault 4.x, API xây dựng `ReactiveVaultTemplate` có thêm các constructor dùng `ReactiveVaultClient`; các constructor dựa trên `VaultEndpoint`, connector và `VaultTokenSupplier` cũng có trong nhiều phiên bản. Khi làm việc trên codebase thật, chọn cấu hình tương thích BOM Spring Boot/Spring Vault, tránh trộn constructor từ các major version.

## 5. Thực hành với Mono: đọc KV v2 trong WebFlux

Giả sử một KV v2 mount `secret/` chứa key `apps/payment-api` với field `gateway_key`. Service Java trả **trạng thái** được phép công khai mà không trả lại khóa:

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

import reactor.core.publisher.Mono;

@Service
public class GatewayConfigService {

    private final ReactiveVaultOperations vault;

    public GatewayConfigService(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Mono<Boolean> isGatewayConfigured() {
        Mono<VaultResponse> read = vault.opsForKeyValue(
                "secret", KeyValueBackend.KV_2)
                .get("apps/payment-api");

        return read
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Secret is missing")))
                .map(response -> {
                    Map<String, Object> data = response.getData();
                    Object value = data == null
                            ? null : data.get("gateway_key");
                    return value instanceof String key
                            && !key.isBlank();
                });
    }
}
~~~

Các điểm quan trọng:

1. `opsForKeyValue("secret", KV_2)` làm việc với **mount**; `get("apps/payment-api")` dùng **key logic**, không tự nối `secret/data/` trong Java.
2. `get(...)` trả `Mono<VaultResponse>`. Khi key không tồn tại, kết quả có thể là `Mono.empty()`; `switchIfEmpty(...)` chuyển trạng thái thiếu secret thành lỗi mà dịch vụ có thể xử lý riêng.
3. `map(...)` chỉ đọc dữ liệu và tạo `Boolean`; kết quả không bao giờ chứa `gateway_key` trong response của API.
4. `isGatewayConfigured()` trả `Mono` cho caller; phương thức **không tự subscribe**.
5. Nếu Vault trả **403** do token hoặc ACL, publisher phát `onError`; `switchIfEmpty` **không** xử lý 403 vì lỗi và empty là hai tín hiệu khác nhau.

Một controller WebFlux trả publisher cho framework:

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/gateway")
public class GatewayStatusController {

    private final GatewayConfigService service;

    public GatewayStatusController(GatewayConfigService service) {
        this.service = service;
    }

    @GetMapping("/configured")
    public Mono<Map<String, Boolean>> configured() {
        return service.isGatewayConfigured()
                .map(value -> Map.of("configured", value));
    }
}
~~~

Đối với `Mono` trả từ controller, **Spring WebFlux đăng ký subscriber và điều phối HTTP response**. Không cần và không nên gọi `subscribe()` trong `configured()`; nếu tự subscribe rồi cũng trả publisher, có thể dẫn đến hai lần đọc Vault và khó kiểm soát lỗi. Endpoint cần Spring Security nếu dành cho người dùng: JWT/role của người dùng quyết định quyền truy cập API, còn Vault token của workload quyết định quyền đọc secret.

### Mono không mang nghĩa "luôn có một giá trị"

Một `Mono<VaultResponse>` có thể:

~~~text
onNext(VaultResponse) -> onComplete   # Có secret
onComplete                          # Không có giá trị
onError(error)                       # Vault/transport/auth lỗi
~~~

Đừng dùng `map` để giả định `Mono.empty()` sẽ kích hoạt lambda với `null`. Reactor **không phát `null`** qua `onNext`; phải dùng `switchIfEmpty`, `defaultIfEmpty` (với giá trị phù hợp) hoặc xử lý empty ở controller.

## 6. Flux: danh sách key, không phải streaming bí mật liên tục

Để liệt kê các key ở thư mục `apps/` trong KV v2:

~~~java
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import reactor.core.publisher.Flux;

public final class VaultKeyListing {

    private final ReactiveVaultOperations vault;

    public VaultKeyListing(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Flux<String> listAppKeys() {
        return vault.opsForKeyValue("secret", KeyValueBackend.KV_2)
                .list("apps")
                .filter(key -> key.startsWith("payment-"))
                .take(20);
    }
}
~~~

**ACL KV v2** cần khả năng `list` trên path metadata tương ứng, ví dụ:

~~~hcl
path "secret/metadata/apps" {
  capabilities = ["list"]
}
~~~

Đừng dùng `read` trên `secret/data/apps/*` thay cho `list` metadata. Đặc biệt, kết quả liệt kê key có thể tiết lộ cấu trúc hệ thống; chỉ cấp quyền cho những workload thực sự cần.

`Flux<String>` phát **nhiều tên key** từ phản hồi của thao tác list. `filter` và `take(20)` xử lý các phần tử **sau khi** server đã trả kết quả danh sách; chúng không tạo truy vấn `LIMIT 20` phía Vault. Không biến API list thành endpoint trả toàn bộ danh sách secret path cho người dùng nếu họ không được cấp quyền xem metadata đó.

### So sánh một số chữ ký API

~~~java
Mono<VaultResponse> one = vault.read("database/creds/readonly");
Flux<String> many = vault.list("secret/metadata/apps");
Mono<Void> done = vault.delete("path/for/authorized-test-only");
~~~

`Mono<Void>` dùng khi quan tâm việc thao tác **hoàn tất hay lỗi**, không có giá trị trả về. Một `Flux` có thể phát 0, 1 hoặc nhiều key nhưng HTTP list phía Vault vẫn là một thao tác mạng, không phải nguồn event liên tục kiểu message broker.

## 7. Ai là người subscribe? WebFlux, test hay application code

Trong chương trình Reactor, phải có **subscriber** thì chuỗi mới được kích hoạt. Những nơi thường thực hiện subscription:

| Ngữ cảnh | Ai subscribe? | Cách viết phù hợp |
| --- | --- | --- |
| Spring WebFlux controller trả `Mono`/`Flux` | WebFlux runtime | Trả publisher, để framework điều phối |
| Spring WebClient gọi API khác | Mã nhận `Mono` và subscriber cuối | Ghép qua `flatMap`, `zip`, `then` |
| JUnit với `StepVerifier` | `StepVerifier.verify()` | Kiểm tra signal và side effect |
| Batch CLI reactive | Điểm điều phối cuối của chương trình | Có thể chủ động subscribe và quản lý completion |
| Service WebFlux thông thường | Không tự subscribe | Trả publisher tới layer gọi |

### Sai: subscribe bên trong service

~~~java
public Mono<Boolean> check() {
    vault.read("secret/data/apps/payment-api")
            .subscribe(response -> {
                // Side effect chạy tách khỏi kết quả phía controller.
            });

    return Mono.just(true);
}
~~~

Sai ở đây không chỉ là gọi thêm request: `Mono.just(true)` có thể hoàn thành **trước** thao tác Vault; exception từ Vault không tự đi vào luồng HTTP response; cancellation khi client ngắt kết nối không quản lý subscription phụ.

### Đúng: ghép thành một pipeline

~~~java
public Mono<Boolean> check() {
    return vault.read("secret/data/apps/payment-api")
            .switchIfEmpty(Mono.error(
                    new IllegalStateException("Missing secret")))
            .map(response -> response.getData() != null);
}
~~~

Không `subscribe()`, không `block()` trong service; controller nhận `Mono<Boolean>` và trả nó cho framework. Khi HTTP request được xử lý, WebFlux mới subscribe. Lỗi sẽ đi theo `onError`, nơi API có thể ánh xạ thành phản hồi an toàn.

## 8. `map`, `flatMap`, `then` và thứ tự request

- `map(f)`: biến đổi **đồng bộ** một giá trị đang phát; không phù hợp khi hàm `f` trả về một `Mono` cần thực thi.
- `flatMap(f)`: nhận giá trị, trả một `Publisher` khác và **subscribe** vào publisher con trong chuỗi.
- `then(other)`: đợi publisher trước **hoàn tất thành công**, bỏ giá trị của nó, rồi tiếp tục publisher sau.
- `zip`: phối hợp kết quả của nhiều publisher; khi subscribe, có thể kích hoạt **nhiều nguồn I/O**.

Ví dụ ghi rồi đọc lại một key KV v2 trong **sandbox**, giả định token có quyền `create/update/read`:

~~~java
import java.util.Map;
import org.springframework.vault.core.ReactiveVaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;
import reactor.core.publisher.Mono;

ReactiveVaultKeyValueOperations kv =
        vault.opsForKeyValue("secret", KeyValueBackend.KV_2);

Mono<Void> write = kv.put(
        "apps/reactive-lab",
        Map.of("demo", "ONLY_SANDBOX"));

Mono<VaultResponse> writeThenRead =
        write.then(kv.get("apps/reactive-lab"));

// Chưa có subscriber: chưa chủ động thực hiện hai thao tác
// do luồng writeThenRead mô tả.
~~~

Khi có subscriber, thứ tự được duy trì: **write hoàn tất thành công trước rồi mới read**. Nếu write lỗi, read sẽ không tự chạy. Ngược lại, `vault.write(...)` trả `Mono<VaultResponse>` trong API cấp thấp; `ReactiveVaultKeyValueOperations.put` trả `Mono<Void>`.

**Không dùng `map(v -> vault.read(...))` khi mục tiêu là chờ request tiếp theo.** Đó sẽ tạo `Mono<Mono<VaultResponse>>`; phải dùng `flatMap` (hoặc `then` nếu không cần kết quả trước).

## 9. `defer` và tác dụng phụ khi assembly

Mặc dù các thao tác reactive Vault thông thường là lazy, không phải **mọi câu lệnh Java xung quanh chúng** đều lazy.

~~~java
AtomicInteger attempts = new AtomicInteger();

// Increment chạy ngay khi gọi phương thức tạo pipeline:
int assembledAt = attempts.incrementAndGet();
Mono<VaultResponse> existing = vault.read("secret/data/apps/payment-api");
~~~

Nếu cần trì hoãn **cả việc tạo nguồn và tác dụng phụ đồng bộ**, dùng `Mono.defer`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import org.springframework.vault.support.VaultResponse;

AtomicInteger subscriptions = new AtomicInteger();

Mono<VaultResponse> readLazily = Mono.defer(() -> {
    subscriptions.incrementAndGet();
    return vault.read("secret/data/apps/payment-api");
});
~~~

Trước subscription, `subscriptions.get()` vẫn bằng 0. Mỗi subscriber cold gọi supplier một lần, tăng bộ đếm và tạo thao tác đọc mới. `Mono.defer` **không tự cache** và không bảo đảm idempotency; trái lại, nó thường giúp thấy rõ tác dụng phụ nằm ở lần đăng ký.

## 10. `retry`, `timeout`, `cache`: đổi semantics và số lần request

### Retry là subscribe lại

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.util.retry.Retry;

Mono<VaultResponse> readWithLimitedRetry =
        vault.read("secret/data/apps/payment-api")
                .retryWhen(
                        Retry.backoff(2, Duration.ofMillis(250))
                                .filter(error ->
                                        error instanceof WebClientRequestException)
                );
~~~

Đây là ví dụ policy thử lại **lỗi kết nối**; loại exception cụ thể có thể khác tùy phiên bản và lớp xử lý lỗi của Spring Vault, nên phải kiểm tra khi áp dụng vào codebase. `Retry.backoff(2,...)` cho phép tối đa **2 lần thử lại sau lần đầu**, nếu lỗi phù hợp filter. Một chuỗi có thể tạo **3 yêu cầu đọc**.

Không retry mù `403` do thiếu policy hay token hết hạn; retry cùng token không sửa ACL. Nguy hiểm hơn, khi `read("database/creds/readonly")` tạo credential động hoặc `put` KV tăng version, retry có thể tạo thêm credential/version nếu server đã xử lý request đầu nhưng client không nhận được response. Với thao tác có side effect, phải thiết kế idempotency, retry policy và cleanup theo semantics của endpoint.

### Timeout không đảo ngược yêu cầu ở Vault

~~~java
Mono<VaultResponse> bounded =
        vault.read("secret/data/apps/payment-api")
                .timeout(Duration.ofSeconds(2));
~~~

`timeout` phát lỗi nếu không nhận tín hiệu đúng hạn theo semantics của Reactor và hủy subscription phía client. Tuy nhiên **hủy subscription hoặc hết thời gian phía client không bảo đảm Vault đã hủy thao tác ở server**. Với lệnh ghi, phát hành dynamic secrets, Transit hoặc PKI, server có thể đã hoàn tất dù client báo timeout. Đừng tự gửi lại request theo phản xạ nếu hậu quả không thể đảo ngược.

### Cache có thể tiết kiệm request nhưng giữ dữ liệu cũ

~~~java
Mono<VaultResponse> cached =
        vault.read("secret/data/apps/payment-api")
                .cache(Duration.ofMinutes(1));
~~~

Sau khi nguồn được kích hoạt, `cache(Duration)` có thể phát lại kết quả cho các subscriber trong thời gian TTL cache, thay vì gửi request mới. Điều này có thể phù hợp cho **dữ liệu không nhạy cảm và có hợp đồng độ tươi rõ ràng**; nhưng secret trong bộ nhớ, TTL của credential, thay đổi policy hoặc revoke không được tự động đồng bộ theo TTL cache.

Không cache Vault token hoặc credential động cho nhiều tenant/người dùng mà chưa xây dựng ranh giới phân quyền riêng. Nếu cần rotation, dùng cơ chế quản lý lifecycle thực sự thay cho việc coi một `Mono.cache()` là secret manager.

## 11. Backpressure, cancellation và thread

`Flux` cung cấp cơ chế yêu cầu `request(n)` để subscriber kiểm soát số phần tử downstream muốn nhận. Nhưng với `vault.list(...)` có thể chỉ có một HTTP response chứa nhiều key, backpressure **không giúp Vault giới hạn số key đọc từ backend**. `take(10)` có thể hủy luồng sau 10 phần tử trong JVM, không tương đương phân trang phía Vault.

Reactive API dùng I/O không chặn trong phần WebClient/connector thích hợp. Tuy nhiên nếu viết:

~~~java
Mono<VaultResponse> wrong =
        Mono.just(vaultTemplate.read("secret/data/apps/payment-api"));
~~~

với `vaultTemplate` là client **imperative**, thao tác blocking `read()` đã chạy ngay khi biểu thức bên trong `Mono.just` được đánh giá. Không thể biến client blocking thành non-blocking bằng cách bọc kết quả vào `Mono.just`.

Nếu buộc phải tích hợp API blocking vào pipeline, phương pháp cầu nối được Reactor hỗ trợ là:

~~~java
import reactor.core.scheduler.Schedulers;

Mono<VaultResponse> bridged =
        Mono.fromCallable(() ->
                vaultTemplate.read("secret/data/apps/payment-api"))
            .subscribeOn(Schedulers.boundedElastic());
~~~

Cách này **dời thao tác blocking sang worker thread**, không làm I/O bên dưới trở thành non-blocking. Nếu có lựa chọn, ưu tiên `ReactiveVaultOperations` trực tiếp, đặc biệt trên Netty event loop của WebFlux. Không gọi `block()` trong luồng event-loop, tránh gây tắc nghẽn và lỗi runtime.

Khi một HTTP client của người dùng rời đi, Spring WebFlux có thể hủy subscription. Điều đó không bảo đảm thao tác Vault đã phát hành token, credential động, khóa Transit hay chứng thư PKI được thu hồi. Với lệnh có side effect cần có idempotency, correlation và cleanup phù hợp.

## 12. Kiểm thử thời điểm thực thi bằng StepVerifier

`reactor-test` cung cấp `StepVerifier`, giúp đăng ký subscriber, kiểm tra thứ tự tín hiệu và xác nhận luồng hoàn tất/lỗi. Không cần Vault server để chứng minh quy tắc **assembly khác subscription**.

### 12.1. Không subscribe thì không chạy

Ví dụ JUnit 5 sau kiểm tra nguồn cold được thực thi một lần cho mỗi subscription:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSubscriptionTest {

    @Test
    void eachSubscriptionRunsColdSource() {
        AtomicInteger executed = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            executed.incrementAndGet();
            return Mono.just("received");
        });

        // Assembly: chưa thực thi supplier.
        assertEquals(0, executed.get());

        StepVerifier.create(source)
                .expectNext("received")
                .verifyComplete();

        assertEquals(1, executed.get());

        // Subscribe vào cùng Mono cold thêm một lần.
        StepVerifier.create(source)
                .expectNext("received")
                .verifyComplete();

        assertEquals(2, executed.get());
    }

    @Test
    void emptyIsDifferentFromError() {
        StepVerifier.create(Mono.<String>empty())
                .verifyComplete();

        StepVerifier.create(Mono.<String>error(
                        new IllegalStateException("denied")))
                .expectError(IllegalStateException.class)
                .verify();
    }
}
~~~

Bộ đếm ở đây tăng trong `Mono.defer`, không phải bộ đếm HTTP của Vault. Khi kiểm thử tích hợp, có thể thay nguồn bằng một Vault client giả có khả năng đếm invocation hoặc dùng audit/metric an toàn để kiểm tra số lần request thật. Đừng tuyên bố `StepVerifier` kiểm thử Vault authentication/ACL nếu nó chỉ chạy publisher giả.

### 12.2. Flux và demand

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveFluxTest {

    @Test
    void requestsTwoItemsThenCancels() {
        Flux<String> keys = Flux.just(
                "payment-a", "payment-b", "other");

        StepVerifier.create(keys, 0)
                .thenRequest(2)
                .expectNext("payment-a", "payment-b")
                .thenCancel()
                .verify();
    }
}
~~~

`create(keys, 0)` bắt đầu không yêu cầu item nào; `thenRequest(2)` phát tín hiệu nhu cầu hai item, và `thenCancel()` hủy. Đây là test backpressure **bên trong Reactor**, không chứng minh Vault chỉ trả hai key ở tầng HTTP.

### 12.3. Kiểm thử timeout với virtual time

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveTimeoutTest {

    @Test
    void timeoutIsTriggeredAfterTwoSeconds() {
        StepVerifier.withVirtualTime(
                        () -> Mono.delay(Duration.ofMinutes(5))
                                  .timeout(Duration.ofSeconds(2)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectError(TimeoutException.class)
                .verify();
    }
}
~~~

`withVirtualTime` yêu cầu xây Publisher **bên trong supplier** để các toán tử thời gian gắn đúng scheduler ảo. Test này chứng minh timeout của Reactor; **không** cần hoặc thực hiện HTTP request Vault.

## 13. Bài thực hành Vault dev: Mono đọc, Flux liệt kê

Chỉ sử dụng môi trường dev cô lập, dữ liệu giả và token ứng dụng có TTL ngắn. Cần Vault CLI, JDK, Spring Boot WebFlux, Spring Vault và Reactor Core/test tương thích BOM; để chạy controller, project phải có Spring WebFlux và một `ReactiveVaultOperations` đã được cấu hình.

### Bước 1 — Khởi động Vault dev

Terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=root
~~~

Terminal thứ hai:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="root"

vault status
vault secrets list -detailed
~~~

Vault dev thường đã gắn KV v2 dưới mount `secret/`. Nếu chưa có mount đó, operator có thể bật `vault secrets enable -path=secret -version=2 kv`; không tạo chồng mount khi nó đã tồn tại.

### Bước 2 — Tạo key và chính sách

~~~bash
vault kv put -mount=secret apps/payment-api \
  gateway_key="DEMO_VALUE_NOT_A_REAL_SECRET"

vault policy write reactive-demo-read - <<'HCL'
path "secret/data/apps/payment-api" {
  capabilities = ["read"]
}

path "secret/metadata/apps" {
  capabilities = ["list"]
}
HCL

APP_TOKEN="$(vault token create \
  -policy=reactive-demo-read \
  -ttl=15m \
  -field=token)"
~~~

Hai phần policy có nhiệm vụ khác nhau: `read` cho nội dung KV v2 tại key cụ thể, và `list` trên metadata của thư mục `apps`. **Không** cấp `create` hay `update` nếu workload chỉ có nhu cầu đọc. Ngay cả lệnh list cũng có thể tiết lộ tên key; chỉ thực hiện trong sandbox.

Kiểm tra quyền bằng **chính token ứng dụng**:

~~~bash
VAULT_TOKEN="$APP_TOKEN" vault kv get \
  -mount=secret apps/payment-api

VAULT_TOKEN="$APP_TOKEN" vault kv list \
  -mount=secret apps/
~~~

Nếu lệnh đầu bị `403`, xem ACL trên `secret/data/apps/payment-api`; nếu lệnh list bị `403`, xem ACL `secret/metadata/apps`. Không dùng root token để chứng minh policy workload hoạt động.

### Bước 3 — Chạy ứng dụng reactive

Chuyển token tới tiến trình Java của **sandbox**, không đưa vào source code:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_APP_TOKEN="$APP_TOKEN"

# Khởi động Spring Boot đã cấu hình ReactiveVaultConfiguration.
# Ví dụ: chạy từ IDE với các environment variables trên.
~~~

Sau khi ứng dụng có controller ở mục 5, gửi HTTP request:

~~~bash
curl -i http://localhost:8080/api/gateway/configured
~~~

Trong ví dụ **chưa có cấu hình bảo mật API**, phản hồi thành công dự kiến là HTTP 200 với JSON:

~~~json
{"configured":true}
~~~

Controller chỉ trả `true/false`, không trả `gateway_key`. Trong ứng dụng thật phải thêm xác thực/phân quyền người dùng cuối hoặc khóa endpoint chẩn đoán theo chính sách. Vault token nằm ở **server-side workload**, không gửi cho trình duyệt.

### Bước 4 — Quan sát Mono không có subscriber

Với Java test hoặc debugger được kiểm soát:

~~~java
Mono<Boolean> result = service.isGatewayConfigured();

// Chưa subscribe, chưa hoàn tất đọc KV từ luồng này.
// Test StepVerifier.create(result).expectNext(true).verifyComplete()
// sẽ thực hiện subscription.
~~~

`StepVerifier` có thể được dùng trong integration test; nếu cấu hình authentication thực hiện I/O lúc bean khởi tạo, đừng nhầm những request bootstrap đó với request đọc KV của `result`.

### Bước 5 — Thử lỗi thiếu quyền và lỗi dữ liệu

Tạo một token `default` không được cấp quyền đọc path:

~~~bash
DENIED_TOKEN="$(vault token create \
  -policy=default \
  -ttl=5m \
  -field=token)"

curl -sS -o /dev/null -w "status=%{http_code}\n" \
  -H "X-Vault-Token: $DENIED_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/apps/payment-api"
~~~

Kỳ vọng thường là `403` ở Vault. Nếu ứng dụng được khởi động bằng `VAULT_APP_TOKEN` chứa token không có quyền, publisher khi được xử lý sẽ báo lỗi Vault; lỗi cũng có thể xuất hiện trước đó trong vòng đời khởi tạo phiên tùy cấu hình. Cần trả lỗi backend an toàn cho người dùng, không chuyển nguyên credential/stack trace vào response.

Thử trường hợp **key không tồn tại** bằng một path *không được cấp quyền đọc* sẽ không chứng minh `Mono.empty()`: Vault có thể trả 403 trước khi xác định dữ liệu. Để kiểm tra empty/404, dùng token test có `read` trên **một key thử nghiệm khác** nhưng key chưa được tạo. Luôn phân biệt `404/empty` với `403`.

### Bước 6 — Dọn môi trường dev

~~~bash
vault token revoke "$APP_TOKEN"
vault token revoke "$DENIED_TOKEN"

vault kv metadata delete -mount=secret apps/payment-api
vault policy delete reactive-demo-read
~~~

`vault kv metadata delete` xóa các phiên bản KV v2 của key thử nghiệm. Chỉ chạy trên Vault dev riêng, kiểm tra đúng mount/key trước khi xóa.

## 14. Ma trận quan sát các trường hợp

| Tình huống | Subscription | Kết quả mong đợi |
| --- | --- | --- |
| Tạo `Mono` bằng `vault.read` | Chưa | Chưa chạy **thao tác đọc** qua publisher cold |
| Subscribe một lần | Có | Một luồng HTTP đọc Vault, thành công/empty/error |
| Subscribe hai lần cùng publisher cold | Có, hai lần | Thường hai lượt đọc độc lập |
| Dùng `Mono.defer` + bộ đếm | Chưa/Có | 0 khi assembly; 1 cho mỗi subscription |
| `Mono.empty()` | Có | Hoàn tất không giá trị, `map` không chạy |
| `Mono.error(...)` | Có | `onError`, không tự thành empty |
| `Flux.list(...)` | Có | Một thao tác list trả nhiều `onNext` key |
| Token thiếu quyền đọc KV | Có | Vault từ chối, thường HTTP 403 |
| Token thiếu quyền list metadata | Có | `list` bị từ chối, dù `get` có thể được phép |
| `retryWhen` trên request có side effect | Có | Có thể chạy lại toàn bộ thao tác và phát hành thêm dữ liệu |
| `timeout` với request đã tới server | Có | Client nhận lỗi timeout; server không nhất thiết rollback |
| `Mono.cache` sau lần gọi thành công | Nhiều subscriber | Có thể phát lại dữ liệu cũ, không tự làm mới Vault secret |
| `block()` trên event loop | Có | Tắc nghẽn/rủi ro lỗi; không phù hợp WebFlux |
| `StepVerifier` trên publisher mock | Có | Chứng minh semantics Reactor, **không** chứng minh Vault ACL |

Một bài test tốt không chỉ khẳng định “đã nhận `Mono`”, mà phải xác minh **request thực sự xảy ra khi nào**, số lần khi subscribe lại, tín hiệu empty/error và hậu quả của retry đối với API Vault.

## 15. Xử lý lỗi và quan sát pipeline trong production

**Reactive không tự sửa lỗi của Vault**. Token workload hết hạn, thiếu policy, mount KV sai, lease bị thu hồi, Transit/PKI từ chối hoặc kết nối TLS không hợp lệ đều có thể xuất hiện dưới dạng tín hiệu `onError`. Cần phân loại lỗi **nghiệp vụ**, **xác thực/phân quyền**, **không tồn tại dữ liệu** và **network/timeout**.

Một mẫu logging an toàn chỉ quan sát vòng đời subscription và loại lỗi, không in `VaultResponse`:

~~~java
Mono<Boolean> status = service.isGatewayConfigured()
        .doOnSubscribe(subscription ->
                log.debug("vault-config subscription started"))
        .doOnSuccess(value ->
                log.debug("vault-config completed"))
        .doOnError(error ->
                log.warn("vault-config request failed: {}",
                        error.getClass().getSimpleName()))
        .doFinally(signal ->
                metrics.recordReactiveVaultTerminalSignal(signal));
~~~

`log` và `metrics` ở đây là **thành phần minh họa do ứng dụng định nghĩa**; không có sẵn trong snippet. Không log `error.getMessage()` vô điều kiện nếu thông điệp của client có thể chứa path hoặc dữ liệu nhạy cảm. Cần định nghĩa chính sách loại bỏ token, mật khẩu, secret, JWT, lease ID và request payload ở cả logging, tracing và metric.

Trong reactive pipeline, mỗi subscription có thể tạo một **operation span/metric**. Nếu đo thời gian, phân biệt lúc assembly với lúc subscription; bộ đếm trong `doOnSubscribe` đo số lần đăng ký, **không chắc bằng số request Vault** khi auth được tái sử dụng, operator cache được áp dụng, subscription bị hủy trước request hoặc một subscription có retry.

**Bảo vệ mọi tầng**:

- **WebFlux request:** xác thực JWT người dùng/role, kiểm tra tenant và dữ liệu được phép trả ra.
- **Workload → Vault:** Vault token do workload authentication tạo, ACL chỉ cấp API path/capability cần dùng.
- **Pipeline:** không log secret, không cache vô thời hạn, không retry mù thao tác có side effect, tránh `block()`.
- **Vòng đời:** quản lý Vault token TTL và secret lease riêng; `Mono`/`Flux` không tự gia hạn token hoặc lease.
- **Mạng:** cấu hình TLS/CA, timeout HTTP hợp lý, giới hạn số request đồng thời và quan sát lỗi authentication/authorization.

Nếu cần đọc nhiều secret trong một `Flux`, `flatMap` có thể tạo nhiều request đồng thời. Dùng tham số concurrency giới hạn khi cần, ví dụ `flatMap(this::readOne, 4)` trong service do ứng dụng tự định nghĩa, để tránh tạo bão request tới Vault. Không phải cứ có backpressure là hệ thống tự giới hạn toàn bộ số request mạng.

## 16. Câu hỏi tự kiểm tra

1. `Mono<VaultResponse> m = vault.read("secret/data/apps/demo")` vừa được khai báo. Có thể chắc chắn Vault đã nhận yêu cầu GET chưa? Vì sao?
2. Một `Mono` cold được subscribe hai lần. Có thể có bao nhiêu lượt gọi HTTP phía Vault và điều đó nguy hiểm thế nào với `database/creds/readonly`?
3. `Mono.empty()` và `Mono.error(...)` khác nhau ở những tín hiệu nào? Vì sao `map` không chạy khi Mono empty?
4. Vì sao `Flux<String> list(...)` không có nghĩa Vault streaming từng key qua HTTP trong thời gian dài?
5. Viết controller WebFlux có nên gọi `subscribe()` bên trong rồi trả `Mono.just(true)` không?
6. Khi `retryWhen` thử lại một yêu cầu ghi KV v2, hậu quả có thể là gì nếu lần ghi đầu thực sự đã được Vault xử lý?
7. Vì sao `Mono.just(vaultTemplate.read(path))` vẫn là blocking khi `vaultTemplate` thuộc imperative API?
8. Có thể coi `timeout` là bằng chứng Vault đã hủy một thao tác cấp credential hay không?
9. Khi nào `cache(Duration)` có thể khiến dữ liệu của ứng dụng khác phiên bản secret trên Vault?
10. Nếu bạn dùng `Flux.list("apps")` trên mount KV v2, cần capability ACL nào và ở nhóm path nào?

**Gợi ý:** (1) Chưa; publisher cold chưa có subscription. (2) Thường hai lần, có thể tạo hai lease/credential. (3) Empty chỉ complete, error gửi `onError`. (4) Một request có thể trả danh sách rồi được chuyển thành nhiều signal. (5) Không; để WebFlux subscribe. (6) Tạo thêm version hoặc lặp side effect. (7) Biểu thức blocking được gọi trước khi tạo Mono. (8) Không. (9) Khi cache sống lâu hơn dữ liệu/credential đã thay đổi. (10) Capability `list` trên `secret/metadata/apps`.

## 17. Tiêu chí hoàn thành và tài liệu tham khảo

**Bạn đạt mục tiêu của bài** khi tự chứng minh được ba kết quả sau:

1. Ở mức Reactor, pipeline được tạo nhưng chưa subscription thì thao tác cold chưa chạy; hai subscription có thể dẫn tới hai lần thực thi.
2. Ở mức Spring Vault, `Mono` đọc một secret, `Flux` liệt kê nhiều key; thiếu dữ liệu, thiếu quyền và timeout được xử lý bằng các tín hiệu khác nhau.
3. Ở mức ứng dụng, WebFlux là subscriber cuối, response không lộ secret, và các operator như `retry`, `cache`, `timeout` được chọn theo tác dụng thực tế lên Vault.

**Nguồn tài liệu chính thức để tra cứu theo phiên bản đang dùng:**

- [Spring Vault — Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html)
- [Spring Vault — ReactiveVaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultOperations.html)
- [Spring Vault — ReactiveVaultTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultTemplate.html)
- [Spring Vault — ReactiveVaultKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultKeyValueOperations.html)
- [Spring Vault — ReactiveVaultVersionedKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultVersionedKeyValueOperations.html)
- [Project Reactor — Introduction to Reactive Programming](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [HashiCorp Vault — KV Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/kv)

**Kết luận:** `Mono` và `Flux` là mô tả luồng tín hiệu **bất đồng bộ**. Khi làm việc với `ReactiveVaultTemplate`, câu hỏi cốt lõi không chỉ là *lấy dữ liệu nào*, mà còn là *ai subscribe, subscribe bao nhiêu lần, khi nào phát request và lỗi/timeout/retry ảnh hưởng gì tới Vault*. Hiểu đúng thời điểm thực thi giúp ứng dụng Java bảo vệ secrets, tránh thao tác lặp và kiểm soát vòng đời request.
