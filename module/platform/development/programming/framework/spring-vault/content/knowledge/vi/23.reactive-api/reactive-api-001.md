# ReactiveVaultTemplate và ReactiveVaultOperations trong Spring Vault

Khi xây dựng API bất đồng bộ bằng **Spring WebFlux** và Reactor, ứng dụng Java thường muốn truy cập **HashiCorp Vault** mà không chặn các luồng xử lý I/O. **Spring Vault** cung cấp lớp `ReactiveVaultTemplate` và giao diện `ReactiveVaultOperations` để đọc/ghi secrets bằng các chuỗi `Mono`, `Flux`; sử dụng xác thực Vault theo workload, policy tối thiểu và HTTP client reactive.

Bài học thuộc chương **API reactive** và tập trung vào hai API này: mô hình thực thi, cách cấu hình, đọc KV v1/v2, dùng Transit, quản lý phiên/token, xử lý lỗi, bảo mật, quan sát hiệu năng và kiểm thử tích hợp. Đây là một phần của module **SPRING_VAULT**, nơi `VaultTemplate`, KV secrets, token/lease, Transit encryption và PKI đều phải hoạt động đúng theo phân quyền của Vault.

## 1. Vì sao Spring Vault có API reactive?

Trong cách lập trình imperative, một lời gọi `VaultTemplate.read(...)` thường đợi HTTP request hoàn tất rồi trả về `VaultResponse`. Nếu đặt trực tiếp lời gọi này lên luồng event loop của WebFlux/Netty, ứng dụng có nguy cơ giữ luồng xử lý trong lúc chờ mạng.

API reactive biểu diễn công việc cần làm dưới dạng **Publisher**. `ReactiveVaultOperations.read(...)` trả `Mono<VaultResponse>`, còn `list(...)` trả `Flux<String>`. HTTP client reactive có thể tận dụng I/O không blocking, phối hợp với các nguồn khác bằng Reactor mà không phải giữ một thread chờ mỗi request.

| Khía cạnh | API đồng bộ | API reactive |
| --- | --- | --- |
| Điểm vào | `VaultTemplate`, `VaultOperations` | `ReactiveVaultTemplate`, `ReactiveVaultOperations` |
| Đọc secret | `VaultResponse read(path)` | `Mono<VaultResponse> read(path)` |
| Liệt kê key | Thường trả tập key đồng bộ | `Flux<String> list(path)` |
| HTTP client | Cơ chế đồng bộ của Spring Vault | `ReactiveVaultClient`/`WebClient` và connector reactive |
| Session | `SessionManager` | `VaultTokenSupplier`, `ReactiveSessionManager` |
| Luồng xử lý | Caller có thể bị chặn trong I/O | I/O được mô hình hóa thành publisher bất đồng bộ |
| Quản lý kết quả | `try/catch`, đối tượng/null | `onErrorResume`, `switchIfEmpty`, `map`, `flatMap` |
| Trường hợp dùng | Batch đồng bộ, MVC, ứng dụng imperative | WebFlux, pipeline Reactor, ứng dụng I/O bất đồng bộ |

**Reactive không có nghĩa Vault nhanh hơn, không có nghĩa API miễn phí về độ trễ, cũng không có nghĩa mọi công đoạn tự động non-blocking.** Việc ký, mã hóa, parse payload và các lệnh thư viện khác có thể vẫn tiêu tốn CPU hoặc chặn nếu tự gọi API đồng bộ trong chuỗi reactive.

### Mono và Flux trong trường hợp Vault

- `Mono<T>` phát tối đa một giá trị hoặc hoàn tất rỗng; thích hợp để đọc một secret, ghi một secret hoặc truy vấn trạng thái Vault.
- `Flux<T>` phát nhiều giá trị theo luồng, chẳng hạn các tên key trong một kết quả `list`.
- Chúng truyền tín hiệu `onNext`, `onComplete` và `onError`, không phải phương thức luôn trả dữ liệu ngay khi được gọi.
- Reactor cho phép ghép nhiều request với `flatMap`, `zip`, `retryWhen`, `timeout` và các toán tử khác; chỉ sử dụng chúng với giới hạn concurrency, bảo mật và tính idempotent phù hợp.

## 2. Kiến trúc: từ WebFlux đến Vault

~~~mermaid
flowchart TD
    A["HTTP request / WebFlux handler"] --> B["Business service: Mono hoặc Flux"]
    B --> C["ReactiveVaultOperations interface"]
    C --> D["ReactiveVaultTemplate"]
    D --> E["VaultTokenSupplier / ReactiveSessionManager"]
    D --> F["ReactiveVaultClient / WebClient"]
    E --> F
    F --> G["TLS + HTTP đến HashiCorp Vault"]
    G --> H["Vault auth / policy"]
    H --> I["KV v1/v2"]
    H --> J["Transit encrypt/decrypt"]
    H --> K["sys API và engine khác"]
    K --> L["PKI qua API tương ứng nếu được hỗ trợ"]
    I --> M["Reactor Publisher trả kết quả"]
    J --> M
    L --> M
    M --> B
~~~

Luồng kết nối có hai vấn đề độc lập:

1. **Xác thực và quyền:** `VaultTokenSupplier` cung cấp Vault token hoặc mô tả luồng login theo workload. Vault kiểm tra token/policy cho từng API. Giao diện reactive không thay đổi quyền được cấp.
2. **Thực thi HTTP:** `ReactiveVaultTemplate` dùng client reactive để gửi request. Tính bất đồng bộ chỉ có ý nghĩa khi các thành phần liên quan không chuyển sang gọi blocking ngay giữa pipeline.

Khi dùng Spring Container, nên đăng ký `ReactiveVaultTemplate` như một singleton dùng chung vì nó được thiết kế để an toàn khi dùng giữa nhiều thread sau khi cấu hình. Trong Java code, **inject qua `ReactiveVaultOperations`** giúp giảm phụ thuộc trực tiếp vào implementation và đơn giản hóa việc mock trong test.

## 3. Các class và interface cần biết

| Thành phần | Package | Vai trò |
| --- | --- | --- |
| `ReactiveVaultOperations` | `org.springframework.vault.core` | Giao diện thao tác read/write/delete/list, KV, Transit, sys, callback. |
| `ReactiveVaultTemplate` | `org.springframework.vault.core` | Implementation chính của `ReactiveVaultOperations`. |
| `ReactiveVaultClient` | `org.springframework.vault.client` | HTTP client reactive cấp thấp dành cho Vault. |
| `VaultEndpoint` | `org.springframework.vault.client` | Địa chỉ, cổng, scheme và API base path của Vault. |
| `VaultTokenSupplier` | `org.springframework.vault.authentication` | Hàm `getVaultToken()` trả `Mono<VaultToken>`. |
| `ReactiveSessionManager` | `org.springframework.vault.authentication` | Chiến lược quản lý session/token reactive. |
| `ReactiveLifecycleAwareSessionManager` | `org.springframework.vault.authentication` | Quản lý đăng nhập, giữ token và renewal theo lifecycle của session. |
| `ReactiveVaultKeyValueOperations` | `org.springframework.vault.core` | Thao tác KV v1 hoặc KV v2 theo API được chọn. |
| `ReactiveVaultVersionedKeyValueOperations` | `org.springframework.vault.core` | KV v2 có version/metadata và khả năng cập nhật dùng CAS. |
| `ReactiveVaultTransitOperations` | `org.springframework.vault.core` | Encrypt/decrypt/sign/verify/rewrap bằng Transit engine. |
| `AbstractReactiveVaultConfiguration` | `org.springframework.vault.config` | Cấu hình Java cho bean template, client và reactive session. |

Các hàm quan trọng của `ReactiveVaultOperations`:

~~~java
Mono<VaultResponse> read(String path);
<T> Mono<VaultResponseSupport<T>> read(String path, Class<T> responseType);
Mono<VaultResponse> write(String path, Object body);
Mono<Void> delete(String path);
Flux<String> list(String path);

ReactiveVaultKeyValueOperations opsForKeyValue(
        String mount, KeyValueBackend version);
ReactiveVaultVersionedKeyValueOperations opsForVersionedKeyValue(String mount);
ReactiveVaultTransitOperations opsForTransit();
ReactiveVaultTransitOperations opsForTransit(String mount);
ReactiveVaultSysOperations opsForSys();
~~~

Khối trên chỉ là **chữ ký rút gọn minh họa**, không phải một interface đầy đủ để copy vào project. Các phương thức `doWithSession(...)` và `doWithVault(...)` cho phép gọi API khác trực tiếp bằng `WebClient` khi template chưa có convenience operation.

## 4. Dependency, phiên bản và cấu hình reactive

Để dùng API reactive, ứng dụng cần Spring Vault hỗ trợ reactive API, Reactor cùng HTTP client reactive thích hợp, thường qua Spring WebFlux. Đừng giả định chỉ có `spring-boot-starter-web` là đủ cho các bean reactive hoặc rằng có WebFlux thì `ReactiveVaultTemplate` luôn được tự tạo.

Một cấu hình Maven theo hướng **dependency management của Spring Boot/Spring Cloud phù hợp** có thể bao gồm:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
  </dependency>
  <dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Thí dụ không ghim version vì phải chọn **một bộ phiên bản tương thích theo BOM**. Nếu dự án không sử dụng Spring Boot dependency management, bạn phải khai báo và kiểm tra version tương thích của Spring Vault, Spring Framework, Reactor và HTTP client. Có thể dùng Spring Cloud Vault để tự cấu hình Vault, nhưng phải xác nhận nó thực sự cung cấp bean `ReactiveVaultOperations`/`ReactiveVaultTemplate` trong phiên bản và mô hình autoconfiguration đang sử dụng.

### 4.1. Cấu hình sản xuất: sử dụng workload identity

Trong production, hãy chọn auth method phù hợp runtime (Kubernetes service account, GCP workload/GCE, AppRole được bảo vệ, cloud IAM, v.v.), và để thành phần xác thực có khả năng cấp lại/renew token khi hợp lệ. `AbstractReactiveVaultConfiguration` có các bean `reactiveVaultTemplate()`, `reactiveSessionManager()` và cấu hình HTTP connector/TLS.

Một điểm đặc biệt của `AbstractReactiveVaultConfiguration` là việc xây dựng luồng xác thực reactive dựa trên `AuthenticationStepsFactory`/`AuthenticationSteps`: một custom `ClientAuthentication` chỉ có method `login()` đồng bộ không tự động trở thành một flow non-blocking. Cần kiểm tra method xác thực và phiên bản thư viện hỗ trợ reactive trước khi sử dụng.

Khi Vault dùng CA nội bộ, cài đặt đúng **trust của HTTP connector Java**; không dùng cờ bỏ xác minh certificate/hostname. Đặt timeout và giới hạn kết nối cho HTTP client bằng cơ chế được hỗ trợ của connector thực tế.

### 4.2. Ví dụ tối thiểu chỉ để thử local

Đoạn dưới đây minh họa constructor và API, **không phải mẫu production**. Đòi Vault dev/test đã chạy trên loopback và một token test được đưa vào tiến trình qua `DEV_VAULT_TOKEN`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.ReactiveVaultTemplate;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
class LocalReactiveVaultConfiguration {

    @Bean
    ReactiveVaultOperations reactiveVaultOperations() {
        String rawToken = System.getenv("DEV_VAULT_TOKEN");
        if (rawToken == null || rawToken.isBlank()) {
            throw new IllegalStateException("Missing dev-only Vault token");
        }

        VaultTokenSupplier supplier =
                () -> Mono.just(VaultToken.of(rawToken));

        return new ReactiveVaultTemplate(
                VaultEndpoint.from("http://127.0.0.1:8200"),
                new ReactorClientHttpConnector(),
                supplier
        );
    }
}
~~~

**Giới hạn của ví dụ:** supplier trả **token tĩnh**, không tự renew hoặc đăng nhập lại khi token hết hạn; HTTP chỉ phù hợp khi kết nối tới Vault dev server trên loopback. Không đặt root token vào repository/CI logs, không dùng ví dụ này làm cấu hình production, và tránh tạo bean này trùng với một bean đã có từ auto-configuration.

## 5. Thực hành đọc KV v2: dùng đúng logical path

Giả sử Vault đã bật KV v2 tại mount `secret/` và đã có secret logic `orders/config`:

~~~bash
# Dùng Vault test riêng và token có quyền đúng path.
vault kv put -mount=secret orders/config \
  app.mode=staging \
  feature.checkout=true

# Lệnh này in dữ liệu, chỉ thực hiện với secret giả trong môi trường test.
vault kv get -mount=secret orders/config
~~~

Một policy cho ứng dụng **chỉ đọc** dữ liệu KV v2:

~~~hcl
path "secret/data/orders/config" {
  capabilities = ["read"]
}
~~~

Khi gọi `opsForKeyValue("secret", KeyValueBackend.KV_2)`, Spring Vault tự sử dụng API KV v2 tương ứng. **Không thêm `data/` vào path logic** truyền vào `get("orders/config")`; nhưng khi viết policy, phải dùng đường API `secret/data/orders/config`.

### 5.1. Service reactive: chỉ lấy một giá trị không nhạy cảm

Ví dụ Java dưới đây trả về `app.mode`, không trả raw secret cho client ngoài. `VaultResponse` có thể chứa nhiều key nhạy cảm; service chỉ trích đúng key được phép công bố.

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

import reactor.core.publisher.Mono;

@Service
public class OrdersRuntimeMode {

    private final ReactiveVaultOperations vault;

    public OrdersRuntimeMode(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Mono<String> currentMode() {
        return vault.opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/config")
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Missing orders/config")))
                .flatMap(response -> {
                    Map<String, Object> data = response.getData();

                    if (data == null || !(data.get("app.mode") instanceof String)) {
                        return Mono.error(new IllegalStateException(
                                "orders/config is missing app.mode"));
                    }

                    return Mono.just((String) data.get("app.mode"));
                });
    }
}
~~~

Điểm quan trọng:

1. `currentMode()` **trả về `Mono<String>`**, không gọi `.block()` và không tự `subscribe()`.
2. `Mono.empty()` do secret không tồn tại được chuyển thành lỗi domain rõ ràng bằng `switchIfEmpty`.
3. Nếu response có dữ liệu nhưng thiếu key, lỗi được phát trong pipeline.
4. Không log `response.getData()`, không truyền cả response ra controller vì nó có thể chứa mật khẩu/secret khác.
5. Không tự động retry mọi lỗi: sai policy hoặc thiếu secret không thể chữa bằng retry dồn dập.

### 5.2. Một endpoint WebFlux dùng Mono được trả về

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/internal/runtime")
class RuntimeController {

    private final OrdersRuntimeMode modes;

    RuntimeController(OrdersRuntimeMode modes) {
        this.modes = modes;
    }

    @GetMapping("/mode")
    Mono<String> mode() {
        return modes.currentMode();
    }
}
~~~

Endpoint `/internal/runtime/mode` chỉ dùng cho minh họa khi `app.mode` được xem là **không nhạy cảm** và đã có bảo vệ truy cập. Không tạo controller tương tự để trả password, Vault token, Transit plaintext hoặc private key. WebFlux runtime sẽ subscribe vào publisher theo vòng đời request; service **không cần và không nên** gọi `subscribe()` thủ công.

## 6. API KV v2 có version và CAS

Nếu ứng dụng cần điều khiển version, đọc metadata hoặc dùng compare-and-set, hãy dùng:

~~~java
ReactiveVaultVersionedKeyValueOperations kv2 =
        vault.opsForVersionedKeyValue("secret");
~~~

Đọc version hiện hành:

~~~java
Mono<Versioned<Map<String, Object>>> latest =
        kv2.get("orders/config");
~~~

Viết một version mới:

~~~java
Mono<Versioned.Metadata> writeResult =
        kv2.put("orders/config", Map.of("app.mode", "staging"));
~~~

Với code đầy đủ, import:

~~~java
import java.util.Map;
import org.springframework.vault.core.ReactiveVaultVersionedKeyValueOperations;
import org.springframework.vault.support.Versioned;
import reactor.core.publisher.Mono;
~~~

Mẫu ở trên giả định biến `vault` là `ReactiveVaultOperations` đã được inject; các thao tác trả về Publisher để ghép, không thực thi ngay bằng cách gán biến. `put` của KV v2 có thể ghi version mới và ảnh hưởng tất cả key ở path; **không biến một bản cấu hình không đủ key thành thao tác cập nhật an toàn**. Với cập nhật cạnh tranh, dùng kiểu `Versioned` có CAS và kiểm tra cách xử lý lỗi conflict; với patch, dùng khả năng được hỗ trợ bởi KV v2 và chính sách Vault phù hợp.

**Điểm hay bị nhầm:** `opsForVersionedKeyValue` hướng tới API KV version 2; còn `opsForKeyValue("secret", KeyValueBackend.KV_2)` cung cấp API đơn giản cho cả version 1 và version 2. Tên `get("orders/config")` là đường logic tương đối với mount; policy vẫn dùng `secret/data/orders/config`.

## 7. Danh sách key bằng Flux và giới hạn backpressure

Phương thức `list(String path)` của `ReactiveVaultOperations` trả `Flux<String>`. Khi cần, cũng có thể dùng `list` của `ReactiveVaultKeyValueOperations` cho semantics của KV mount.

~~~java
Flux<String> names = vault.opsForKeyValue(
        "secret", KeyValueBackend.KV_2)
        .list("orders");
~~~

Lệnh list có thể cần capability `list` trên đường metadata KV v2:

~~~hcl
path "secret/metadata/orders/*" {
  capabilities = ["list"]
}
~~~

Đây chỉ là policy **minh họa**; chính path cần cấp phụ thuộc prefix được list và cách Vault kiểm tra ACL. Nếu không cần liệt kê, **không cấp `list`**. Hãy kiểm tra đúng endpoint `metadata` mà HTTP client gọi trong Vault audit logs đã lọc, thay vì thêm wildcard toàn hệ thống.

### Backpressure không thay Vault thành một stream vô hạn

Vault LIST thường trả một **tập tên key** cho một request HTTP; `Flux<String>` giúp tiêu thụ tập đó bằng Reactor. Nó không làm server Vault tự phát từng key khi người đọc yêu cầu từng phần hoặc biến LIST thành một change-data stream. Nếu danh sách rất lớn, payload HTTP ban đầu vẫn có thể tốn memory/time, và ứng dụng phải giới hạn quy mô và số request đến Vault.

Không dùng:

~~~java
vault.list("secret/metadata/orders")
     .flatMap(name -> vault.read("secret/data/orders/" + name))
     .subscribe(response -> System.out.println(response.getData()));
~~~

Đoạn trên minh họa **cách làm sai**: tự subscribe, có nguy cơ tạo nhiều request đồng thời và ghi tất cả bí mật ra log. Nếu cần xử lý một tập secret, thiết kế giới hạn concurrency, phân quyền, xử lý key do người dùng cung cấp, deadline và cách không phát tán dữ liệu. Với tác vụ đọc dữ liệu nhạy cảm, nên ưu tiên **đọc đúng path** thay vì liệt kê toàn bộ.

## 8. Compose Mono/Flux: flatMap, timeout và retry

Trong pipeline reactive, một lời gọi Vault là một phần của đồ thị công việc. Toán tử `map` phù hợp cho phép biến đổi đồng bộ không chặn; `flatMap` phù hợp khi bước kế tiếp trả `Mono` hoặc `Flux`.

Ví dụ phối hợp hai tham số cấu hình (đều không nhạy cảm):

~~~java
Mono<String> combined =
    Mono.zip(
        vault.opsForKeyValue("secret", KeyValueBackend.KV_2)
             .get("orders/config"),
        vault.opsForKeyValue("secret", KeyValueBackend.KV_2)
             .get("orders/flags")
    ).map(tuple -> {
        Object mode = tuple.getT1().getData().get("app.mode");
        Object flag = tuple.getT2().getData().get("feature.checkout");
        return String.valueOf(mode) + ":" + String.valueOf(flag);
    });
~~~

Ví dụ này yêu cầu hai secret tồn tại và `getData()` không null; trong production, validate schema và báo lỗi khi thiếu key. `Mono.zip` có thể bắt đầu các request độc lập cùng lúc sau subscription, nhưng **không tạo transaction xuyên hai path trong Vault**. Nếu một publisher hoàn tất rỗng, `zip` có thể hoàn tất rỗng; thêm kiểm tra thiếu secret riêng trước khi ghép khi bắt buộc có đủ hai dữ liệu.

### Timeout và retry có chủ đích

~~~java
Mono<String> mode =
    ordersRuntimeMode.currentMode()
        .timeout(Duration.ofSeconds(3))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(150))
            .filter(this::isTransientVaultFailure));
~~~

Ví dụ nằm trong một service đã có `ordersRuntimeMode`, method `isTransientVaultFailure(Throwable)` do ứng dụng **tự định nghĩa**, và import `java.time.Duration`, `reactor.util.retry.Retry`. Cần phân loại lỗi thực tế:

- **Có thể tạm thời:** timeout, lỗi kết nối, một số `5xx`/standby/failover. Retry hữu hạn với backoff và jitter, trong một **request budget** cho phép.
- **Không nên retry:** Vault `403` thiếu policy, sai auth role, KV path không tồn tại, lỗi schema dữ liệu hoặc chứng chỉ TLS không tin cậy.
- **Không retry mù request ghi:** PUT/POST tạo credential, phát hành PKI hoặc cập nhật KV có thể đã thành công phía Vault trước khi client timeout. Retry có thể tạo tác dụng phụ trùng lặp. Dùng idempotency/CAS hoặc reconciliation riêng.

`timeout(Duration)` của Reactor giới hạn thời gian của publisher quan sát được; cần đồng thời thiết lập **connect timeout, response timeout** ở HTTP connector, không trông đợi chỉ một toán tử timeout có thể cấu hình mọi giai đoạn mạng.

## 9. Phiên reactive: VaultTokenSupplier và ReactiveSessionManager

~~~mermaid
sequenceDiagram
    autonumber
    participant S as WebFlux service
    participant O as ReactiveVaultOperations
    participant M as ReactiveSessionManager
    participant V as Vault auth
    participant E as KV/Transit
    S->>O: read() / encrypt()
    O->>M: getVaultToken()
    M->>V: Login qua workload identity khi cần
    V-->>M: Vault token + TTL/renewability
    M-->>O: Mono<VaultToken>
    O->>E: HTTP request có Vault token
    E-->>O: Response theo policy
    O-->>S: Mono/Flux data hoặc error
    Note over M,V: Renew / re-login theo cơ chế session, không login mỗi request
~~~

`VaultTokenSupplier` là functional interface với `Mono<VaultToken> getVaultToken()`. Với môi trường production, không nên gọi một login mới cho từng request; token được giữ và gia hạn hoặc đăng nhập lại bởi `ReactiveSessionManager` thích hợp. `ReactiveLifecycleAwareSessionManager` hỗ trợ quản lý lifecycle, token renewal và các sự kiện xác thực theo khả năng của token/auth method.

Những việc **không nên nhầm lẫn**:

| Vòng đời | Do gì quản lý? | Sai lầm thường thấy |
| --- | --- | --- |
| Vault client token | `ReactiveSessionManager` / auth method | Thấy `Mono` là tưởng token tự làm mới nếu dùng supplier tĩnh. |
| Credential đăng nhập ban đầu | Workload identity/Kubernetes/AppRole/GCP... | Copy một root token vào image để “đảm bảo reactive client hoạt động”. |
| Dynamic secret lease | Vault engine và cơ chế secret lease riêng | Renew token rồi kết luận Database password chưa hết hạn. |
| KV v2 static secret version | KV versioning, chính sách refresh | Mỗi lần gọi `getProperty`/`get` là có sự kiện realtime. |
| Chứng chỉ PKI | PKI engine và TLS consumer | Login token được gia hạn thì cert `notAfter` cũng thay đổi. |

Khi Spring `ApplicationContext` đóng, các session manager/HTTP client/secret lease container cần được quản lý đúng lifecycle. Việc đóng context không bảo đảm cleanup HTTP thành công nếu mạng bị ngắt hoặc tiến trình bị `SIGKILL`; vì vậy production phải có TTL hữu hạn và cơ chế thu hồi độc lập khi cần.

## 10. Dùng Transit encryption qua API reactive

`ReactiveVaultOperations` có `opsForTransit()` và `opsForTransit(mount)`. Một operation đơn giản:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.support.VaultTransitContext;

import reactor.core.publisher.Mono;

@Service
class CustomerDataEncryption {

    private final ReactiveVaultOperations vault;

    CustomerDataEncryption(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    Mono<String> encryptForStorage(String plaintext) {
        byte[] bytes = plaintext.getBytes(StandardCharsets.UTF_8);

        return vault.opsForTransit()
                .encrypt("customer-data", bytes, VaultTransitContext.empty());
    }
}
~~~

`ReactiveVaultTransitOperations.encrypt(String, byte[], VaultTransitContext)` trả `Mono<String>` chứa ciphertext. Trong ví dụ, `VaultTransitContext.empty()` chỉ rõ không có tùy chọn context bổ sung (tham số này không được null); với derived keys hoặc yêu cầu mã hóa chuyên biệt, sử dụng `VaultTransitContext` phù hợp và kiểm tra contract của key. Không in `plaintext` hoặc ciphertext chứa thông tin nghiệp vụ nhạy cảm ra log.

Policy tối thiểu nếu chỉ cần encrypt:

~~~hcl
path "transit/encrypt/customer-data" {
  capabilities = ["update"]
}
~~~

Không cấp quyền `decrypt` nếu ứng dụng không cần giải mã. Transit thực hiện thao tác cryptographic phía Vault, giúp ứng dụng không phải tải material của khóa về JVM. Đối với batch requests, `ReactiveVaultTransitOperations` có các phương thức trả `Flux`; khi dùng, giới hạn số phần tử và xử lý lỗi từng phần theo semantics API thực tế.

**PKI không giống Transit:** không nên suy rằng tồn tại `opsForPki()` trên mọi phiên bản `ReactiveVaultOperations` chỉ vì API imperative có PKI convenience methods. Nếu cần phát hành chứng chỉ từ một flow reactive và chưa có operation tương ứng, kiểm tra Javadoc phiên bản; có thể dùng `doWithSession` hoặc reactive HTTP client đã xác thực để gọi đúng endpoint PKI, bảo vệ private key và response, rồi reload consumer TLS theo quy trình riêng.

## 11. doWithSession và doWithVault: khác nhau ở bảo mật

`ReactiveVaultOperations` cung cấp hai kiểu callback:

- `doWithSession(Function<WebClient, Publisher>)`: sử dụng `WebClient` trong ngữ cảnh **đã xác thực**, phù hợp khi phải gọi một Vault API chưa có phương thức convenience.
- `doWithVault(Function<WebClient, Publisher>)`: sử dụng client **không có ngữ cảnh phiên xác thực** theo contract, cho các API Vault công khai hoặc thao tác bootstrap có kiểm soát.

Ví dụ minh họa truy vấn API trong authenticated session bằng `WebClient`:

~~~java
Mono<String> identityInfo =
    vault.doWithSession(client ->
        client.get()
            .uri("auth/token/lookup-self")
            .retrieve()
            .bodyToMono(String.class));
~~~

Đây là ví dụ kỹ thuật; `lookup-self` có thể trả token metadata mà tổ chức coi là nhạy cảm, vì vậy **không trả JSON nguyên trạng cho client web hoặc ghi vào log**. Trong ứng dụng thật, parse đúng các trường được phép quan sát hoặc sử dụng API chuyên dụng khi có.

### Rủi ro path và URI người dùng cung cấp

Spring Vault cho phép API template hoặc callback dùng path tương đối với endpoint và có hỗ trợ URI tuyệt đối trong một số trường hợp. **Không nhận path/URL không được tin cậy từ HTTP request rồi truyền thẳng vào `read()` hoặc `doWithSession()`.** URI tuyệt đối có thể khiến auth header/token bị gửi đến host không mong muốn nếu code bỏ qua kiểm tra. Cần:

1. Chỉ cho phép một danh sách path/mount được định trước.
2. Không ghép URL từ dữ liệu do người dùng gửi; tránh SSRF và path traversal logic.
3. Khi cần tham số động, map sang ID nghiệp vụ hợp lệ thay vì đường Vault tùy ý.
4. Kiểm soát hostname, scheme, TLS và redirect của client đã xác thực.
5. Giữ `X-Vault-Token`, JWT và HTTP body chứa secret ngoài mọi hệ thống ghi log/tracing.

**Nguyên tắc:** reactive không làm giảm các yêu cầu bảo mật HTTP và policy. Một path sai hoặc token lộ vẫn nguy hiểm như trong client đồng bộ.

## 12. Xử lý Mono.empty, lỗi và hành vi khi Vault không sẵn sàng

Một API reactive có ba kiểu kết thúc đáng phân biệt:

| Tín hiệu | Ví dụ | Phản ứng đúng |
| --- | --- | --- |
| `onNext(data)` rồi `onComplete` | KV get trả secret hợp lệ | Validate schema, chỉ đưa secret đến consumer được phép. |
| `onComplete` không có data | Secret/key không tồn tại theo API | `switchIfEmpty` sang lỗi domain hoặc xử lý optional path. |
| `onError(Throwable)` | Token expired, 403, network/TLS/5xx | Phân loại lỗi, không coi `403` là missing secret. |

### Sai lầm thường gặp

~~~java
// SAI: lỗi Vault bị biến thành một giá trị giả trông như cấu hình thật.
Mono<String> password = getPasswordFromVault()
    .onErrorReturn("default-password");
~~~

Đây chỉ là **anti-pattern** minh họa; `getPasswordFromVault()` là method giả định. Với credential database, fallback sang password tĩnh hardcode sau `403` có thể tạo điểm yếu bảo mật và khó phát hiện.

Thay bằng phân loại lỗi:

~~~java
Mono<String> password = getPasswordFromVault()
    .doOnError(ex -> metrics.incrementVaultReadFailure(
            ex.getClass().getSimpleName()))
    .onErrorMap(ex -> new SecretUnavailableException(
            "Required Vault credential unavailable", ex));
~~~

`metrics`, `SecretUnavailableException` và `getPasswordFromVault()` là các abstraction ví dụ do ứng dụng tự định nghĩa. Trong production, **kiểm tra cause/HTTP status trước khi map** và không tự ý đưa message chứa bearer token vào log. Tránh logging `Throwable` thô nếu transport có thể chèn path, header hoặc payload nhạy cảm vào exception.

### Quan sát readiness

Nếu secret thiết yếu chưa lấy được, service cần readiness phản ánh việc không thể phục vụ request phụ thuộc bí mật đó. Một request nghiệp vụ thất bại trước khi Vault khôi phục có thể cần trả lỗi có kiểm soát, nhưng không cho phép truy cập không xác thực hoặc dùng quyền Vault rộng hơn để “chữa” lỗi.

Trong Vault cluster HA, endpoint `/v1/sys/health` có thể có mã HTTP đặc biệt khi standby, sealed hoặc chưa initialized. `vault.opsForSys().health()` là một lựa chọn reactive; cần diễn giải đúng trạng thái server chứ không giả định mọi mã khác 200 đều là lỗi mạng.

## 13. Kiểm thử unit bằng Reactor StepVerifier

`reactor-test` cho phép kiểm tra Publisher mà không gọi `.block()` trong code nghiệp vụ. Một test unit kiểm tra service ở mục 5 bằng Mockito:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.vault.core.ReactiveVaultKeyValueOperations;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OrdersRuntimeModeTest {

    @Test
    void readsModeFromKvV2() {
        ReactiveVaultOperations operations = mock(ReactiveVaultOperations.class);
        ReactiveVaultKeyValueOperations kv =
                mock(ReactiveVaultKeyValueOperations.class);

        VaultResponse response = new VaultResponse();
        response.setData(Map.of("app.mode", "staging"));

        when(operations.opsForKeyValue("secret", KeyValueBackend.KV_2))
                .thenReturn(kv);
        when(kv.get("orders/config"))
                .thenReturn(Mono.just(response));

        OrdersRuntimeMode service = new OrdersRuntimeMode(operations);

        StepVerifier.create(service.currentMode())
                .expectNext("staging")
                .verifyComplete();
    }

    @Test
    void missingSecretFailsClearly() {
        ReactiveVaultOperations operations = mock(ReactiveVaultOperations.class);
        ReactiveVaultKeyValueOperations kv =
                mock(ReactiveVaultKeyValueOperations.class);

        when(operations.opsForKeyValue("secret", KeyValueBackend.KV_2))
                .thenReturn(kv);
        when(kv.get("orders/config"))
                .thenReturn(Mono.empty());

        StepVerifier.create(new OrdersRuntimeMode(operations).currentMode())
                .expectErrorMatches(ex -> ex instanceof IllegalStateException
                        && ex.getMessage().contains("Missing orders/config"))
                .verify();
    }
}
~~~

Cần có JUnit 5, Mockito, `reactor-test`, Spring Vault và Spring Framework tương thích trong test dependencies. Test chứng minh logic map/empty và interface có thể mock, **chưa chứng minh HTTP client, auth, Vault policy hoặc KV v2 mount thực sự hoạt động**.

### StepVerifier và thời gian

Khi test toán tử `timeout` hoặc `retryWhen` có delay thuần Reactor, có thể dùng virtual time. Nhưng **virtual time không làm Vault server đẩy nhanh TTL thật**; muốn test token renewal, dynamic lease hoặc expiry thực tế phải kết nối Vault test server và quan sát TTL do server cấp.

Ngoài ra, `StepVerifier` subscribe vào Publisher giúp test kiểm tra tín hiệu cuối. Đừng gọi `block()` trước khi tạo StepVerifier vì điều đó khiến test không còn kiểm được hành vi reactive trọn vẹn.

## 14. Integration test: Vault thật và các trường hợp âm

Một bài thực hành end-to-end nên tạo Vault instance **chỉ dành cho test**, KV v2 tại `secret/` và token/policy riêng cho workload test. Không chạy test với root/shared token trong production.

| Test | Setup | Kết quả cần kiểm tra |
| --- | --- | --- |
| KV v2 đọc đúng | Token có `read secret/data/orders/config`, path tồn tại. | `Mono` phát đúng data; không lộ các key bí mật ra HTTP response. |
| KV thiếu secret | Path logic không có. | `Mono.empty()` hoặc lỗi thư viện tương ứng được map thành kết quả domain đúng. |
| KV 403 | Token thiếu quyền. | `onError` phân loại 403, không trả password fallback. |
| Sai KV version | Dùng `KV_1` với KV v2 mount hoặc ngược lại. | Bộc lộ sai path/API; test giúp phát hiện khi config thay đổi. |
| TLS không tin CA | Dùng endpoint test với CA chưa trust. | Lỗi handshake, không bypass TLS verification. |
| Login token expired | Token test TTL ngắn hoặc revoke chủ động. | Session xử lý reauth nếu được hỗ trợ, hoặc trả lỗi rõ ràng. |
| Vault timeout/503 | Fault proxy/Vault test không sẵn sàng. | Timeout, retry có giới hạn và readiness phù hợp. |
| Transit encrypt | Token chỉ có `update transit/encrypt/customer-data`. | Encrypt thành công, decrypt bị từ chối khi policy không cho phép. |
| Concurrent requests | Nhiều subscription đồng thời có giới hạn. | Không login mới vô hạn, không bão request và không lộ token. |
| ApplicationContext.close() | Đóng context có session manager đang chạy. | Scheduler và client resources được giải phóng theo lifecycle. |

### Trình tự triển khai test

1. Tạo Vault test instance và mount KV v2, ghi dữ liệu giả như `app.mode=staging`.
2. Đặt auth method/role theo workload test và cấp policy đọc một path; dùng Vault URI/TLS phù hợp test, không hardcode root token vào app.
3. Khởi tạo `ReactiveVaultTemplate` qua cấu hình Spring hoặc thủ công đúng `VaultTokenSupplier`.
4. Chạy `StepVerifier` cho `get`, `list`, `write` (nếu đã cấp quyền), `opsForTransit` trong một suite có cleanup.
5. Chạy các negative tests: thiếu path, policy denial, endpoint sai, timeout và cert không được trust.
6. Dùng instrumentation kiểm số login/renew, latency và concurrency; lọc token/secret khỏi log.
7. Đóng `ApplicationContext` và xóa tài nguyên thử nghiệm theo ownership.
8. Ghi nhận version Spring Vault/Spring Framework/Reactor, auth method, mount path và chính sách thực tế để tái lập test.

**Đừng nhầm unit test với E2E:** mock `ReactiveVaultOperations` không kiểm chứng chữ ký workload identity hay kết nối TLS với Vault. Ngược lại, một integration test chỉ thấy HTTP 200 không chứng minh đã xử lý đúng `Mono.empty`, cancellation, retry hoặc dữ liệu được phát tán ngoài ý muốn.

## 15. Hiệu năng, bảo mật và anti-pattern khi vận hành

| Anti-pattern | Tại sao gây vấn đề | Giải pháp |
| --- | --- | --- |
| `.block()` trong WebFlux event loop | Có thể chặn event loop hoặc ném lỗi trong môi trường non-blocking. | Return/compose `Mono` hoặc `Flux` đến controller. |
| `subscribe()` trong service để “cho request chạy” | Tách pipeline khỏi lifecycle HTTP, lỗi/cancellation/timeout khó quản lý. | Return Publisher cho caller; subscribe tại biên phù hợp. |
| Tạo template/client mỗi request | Tạo connection/session lặp, khó quản lý tài nguyên. | Dùng singleton `ReactiveVaultOperations`. |
| `flatMap` trên danh sách secret không giới hạn | Burst request có thể gây quá tải Vault. | Giới hạn concurrency, bulkhead và request budget. |
| Retry `403` hoặc lỗi certificate | Không giải quyết quyền và trust, tạo bão request. | Chẩn đoán auth/CA/path, fix cấu hình. |
| Cache bí mật vô thời hạn | Token/secret đã revoke vẫn còn trong app. | TTL/cơ chế rotation rõ, hạn chế số bản sao. |
| Trả `VaultResponse` thẳng ra API công khai | Lộ password, token hoặc metadata. | Map sang DTO tối thiểu và bảo vệ endpoint. |
| Đưa URI/path người dùng vào template | Nguy cơ SSRF hoặc gửi token đến host ngoài. | Whitelist path, không cho URI tùy ý. |
| Trộn `VaultTemplate` sync và `ReactiveVaultTemplate` trong event loop | Thành phần blocking phá lợi ích non-blocking. | Giữ pipeline reactive hoặc cách ly phần sync theo thiết kế. |

### Chỉ số đáng theo dõi

- `vault_http_requests_total` theo operation/result và auth method (không gắn token).
- `vault_request_latency_seconds` và connect/response timeout.
- `vault_login_failure_total`, renewal failure, reauthentication.
- `vault_active_requests`/in-flight, retry rate, connection pool saturation.
- `vault_forbidden_total` phân biệt login denial với policy denial.
- `vault_secret_refresh_failure_total` khi consumer sử dụng dynamic credential hoặc certificate.

Đây là tên metric **đề xuất**, không phải metric mặc định của Spring Vault. Không đưa `X-Vault-Token`, JWT, password, plaintext Transit hoặc `lease_id` nguyên văn vào metrics labels hoặc HTTP trace. Hạn chế log request/response body đối với các thao tác Vault chứa secret.

## 16. Checklist và câu hỏi tự đánh giá

Trước khi đưa API reactive vào sản xuất, cần xác minh:

1. **Kiến trúc:** Dịch vụ thực sự dùng WebFlux/Reactor non-blocking; không gọi `block()` trên event loop.
2. **Bean:** `ReactiveVaultOperations` được inject qua interface, template dùng chung, HTTP connector có TLS/timeout/pool phù hợp.
3. **Auth:** `VaultTokenSupplier`/`ReactiveSessionManager` có chiến lược login, renew, reauth và shutdown rõ.
4. **ACL:** Vault token chỉ có quyền theo từng mount/path và capability cần dùng.
5. **KV:** phân biệt logical path `orders/config`, mount `secret` và API policy `secret/data/orders/config`.
6. **Kết quả:** xử lý riêng `Mono.empty`, dữ liệu thiếu key và `onError`; không rò rỉ response.
7. **Transit/PKI:** thao tác cryptographic, TLS key và certificate không bị lẫn với token/secret lease.
8. **Resilience:** timeout, retry hữu hạn, idempotency của lệnh ghi, ngưỡng quá tải và cancellation.
9. **An toàn:** không gửi URI/path không tin cậy vào client xác thực; bảo vệ CA, token và metadata.
10. **Kiểm thử:** có StepVerifier cho publisher, integration Vault thật, negative tests và kiểm tra đóng context.

Câu hỏi luyện tập:

- Tại sao `Mono<VaultResponse>` từ `ReactiveVaultOperations.read` không có nghĩa HTTP request đã chạy trước khi có subscription?
- Khi KV v2 mount tại `secret/`, ứng dụng truyền path nào vào `opsForKeyValue(...).get(...)` và policy cần path nào?
- Vì sao `doWithSession` cần kiểm soát path/URI nghiêm ngặt hơn một method chỉ nhận ID nghiệp vụ?
- Điều gì khác giữa lỗi `Mono.empty` và Vault trả `403`?
- Có thể dùng `retryWhen` vô điều kiện cho endpoint Database credentials hoặc PKI issue không? Vì sao?
- `ReactiveLifecycleAwareSessionManager` và dynamic secret lease có nhiệm vụ giống nhau không?
- Vì sao StepVerifier với mock chỉ kiểm được logic service, chưa chứng minh cơ chế xác thực Vault end-to-end?
- Khi cần PKI, vì sao phải kiểm tra API reactive của phiên bản thư viện thay vì giả định mọi `VaultOperations` đồng bộ đều có đối ứng?

**Ghi nhớ:** `ReactiveVaultTemplate` là implementation, `ReactiveVaultOperations` là abstraction để code Java thao tác Vault theo Reactor. Lợi ích chính là **ghép luồng bất đồng bộ và không blocking ở tầng HTTP**, nhưng tính an toàn vẫn phụ thuộc Vault auth, policy, TLS, timeout, lifecycle token/lease, đường dẫn KV và việc consumer không làm lộ dữ liệu nhạy cảm.

## Tài liệu chính thức tham khảo

- [Spring Vault – Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html).
- [ReactiveVaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultOperations.html).
- [ReactiveVaultTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultTemplate.html).
- [ReactiveVaultKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultKeyValueOperations.html).
- [ReactiveVaultVersionedKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultVersionedKeyValueOperations.html).
- [ReactiveVaultTransitOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultTransitOperations.html).
- [AbstractReactiveVaultConfiguration API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractReactiveVaultConfiguration.html).
- [ReactiveLifecycleAwareSessionManager API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveLifecycleAwareSessionManager.html).
