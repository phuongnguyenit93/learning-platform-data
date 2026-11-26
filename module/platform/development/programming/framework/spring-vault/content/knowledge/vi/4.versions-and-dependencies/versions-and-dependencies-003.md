# Khác biệt API giữa dòng 3.x, 4.0 và 4.1 trở lên

Spring Vault là thư viện tích hợp HashiCorp Vault cho ứng dụng Java. Nó cung cấp `VaultTemplate`/`VaultOperations` để làm việc với KV secrets, xác thực theo workload, vòng đời token và lease, Transit encryption, PKI, xử lý lỗi và kiểm thử với Vault thật. Khi nâng cấp, không thể chỉ đổi số phiên bản Maven rồi giả định các lớp giao tiếp HTTP, JSON và quản lý vòng đời vẫn hành xử giống hệt nhau.

**Chương:** Phiên bản và phụ thuộc. Bài này tập trung vào **khác biệt API và tác động đến mã nguồn** giữa Spring Vault 3.x, 4.0 và 4.1+, đặc biệt với các ứng dụng đang dùng `VaultTemplate`, tuỳ biến HTTP client hoặc xử lý secret động.

> **Mốc tham chiếu: 25/11/2026.** Các dòng ổn định được tài liệu Spring công bố tại thời điểm này là 3.1.x, 3.2.x, 4.0.x và 4.1.x; bản vá mới được công bố gồm **4.0.5 và 4.1.2**. Các ví dụ API 4.1 được đối chiếu với Javadoc/reference 4.1.2. “4.1 trở lên” diễn đạt **hướng tiến hóa API bắt đầu từ 4.1**, không cam kết API của một bản 4.2+ chưa phát hành sẽ giữ nguyên.

## 1. Bản đồ thay đổi

| Khía cạnh | Spring Vault 3.x | Spring Vault 4.0 | Spring Vault 4.1+ |
| --- | --- | --- | --- |
| Nền tảng | Spring Framework **6.x**, Java **17+** | Spring Framework **7.0**, Java **17+** | Spring Framework **7.0+** theo bản vá đang dùng, Java **17+** |
| API nghiệp vụ chính | `VaultOperations`, `VaultTemplate`, `ReactiveVaultTemplate` | Các Template vẫn là API chính | Các Template **vẫn dùng được**; thêm lớp fluent client mới |
| HTTP đồng bộ bên dưới | Chủ yếu **`RestTemplate`** | Bổ sung `RestClient` / `RestClientBuilder` | **`VaultClient`** (bên dưới là `RestClient`) làm nền mới cho Template |
| HTTP reactive | `WebClient` bên dưới `ReactiveVaultTemplate` | Tiếp tục hỗ trợ reactive | Thêm **`ReactiveVaultClient`** dùng fluent API trên `WebClient` |
| Định tuyến & header Vault | Các API Template và callback `RestOperations` | Thêm chọn lựa HTTP mới | `VaultClient.path(...)`, `token(...)`, `namespace(...)` tách ý định Vault khỏi HTTP thuần |
| JSON mapping | Chủ yếu Jackson 2 | Thêm Jackson 3, vẫn tương thích Jackson 2 | Tiếp tục Jackson 3/2; cần kiểm tra mapper được chọn trên classpath |
| HTTP transport | JDK `HttpURLConnection`, Apache HttpComponents, OkHttp 3 và các client reactive | Bỏ OkHttp; mở rộng JDK `HttpClient`, Reactor, Jetty cho imperative | Hệ thống client mới dùng JDK `HttpClient` mặc định nếu không có client phù hợp khác |
| Tuỳ biến HTTP | `RestTemplateCustomizer`, `RestTemplateBuilder` | Thêm `RestClientCustomizer` và `RestClientBuilder` | Ưu tiên `VaultClientCustomizer`; một số tuỳ biến `RestTemplate` bị **deprecated** |
| KV v1/v2 | Thường dùng `opsForKeyValue(mount, KeyValueBackend)` | Tiếp tục | Thêm `opsForKeyValue(mount)` **tự xác định phiên bản mount** |
| Quản lý secret động | `SecretLeaseContainer`, `RequestedSecret`, lease events | Tiếp tục | Thêm `ManagedSecret`, cải tiến rotation kể cả secret không có lease |
| PKI/chứng chỉ | `opsForPki(...)`, tự xây dựng cơ chế cập nhật certificate | Tiếp tục | Thêm `CertificateContainer` và `ManagedCertificate` quản lý phát hành/rotation |
| Tương thích mã nguồn | Cơ sở trước khi nâng | **Breaking changes** do nâng Framework và gỡ API deprecated cũ | Bổ sung API mới; **nhiều đường cũ vẫn còn nhưng bị deprecated từ 4.1** |

**Hai mốc cần nhớ:** **4.0** là lần nâng *nền thư viện và HTTP/JSON ecosystem*; **4.1** là lần mở rộng *mô hình API Vault-specific*, cho phép chuyển dần các đường code phụ thuộc `RestTemplate` sang `VaultClient`.

Nguồn: [Spring Vault 4.0 GA](https://spring.io/blog/2025/11/18/spring-vault-4-0-goes-ga/), [Spring Vault 4.1 GA](https://spring.io/blog/2026/06/10/spring-vault-4-1-available/), [4.0 release notes](https://github.com/spring-projects/spring-vault/releases/tag/4.0.0), [4.1 release notes](https://github.com/spring-projects/spring-vault/releases/tag/4.1.0).

## 2. Spring Vault 3.x: `VaultTemplate` và `RestTemplate`

Ở dòng 3.x, `VaultTemplate` triển khai giao diện `VaultOperations` và thường dựa vào **`RestTemplate`** để gửi HTTP. Ứng dụng nên phụ thuộc vào `VaultOperations` trong business code, còn thông tin Vault endpoint, TLS, authentication và session manager được cấu hình tại tầng hạ tầng.

```java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

class OrdersSecrets {
    private final VaultOperations vault;

    OrdersSecrets(VaultOperations vault) {
        this.vault = vault;
    }

    VaultResponse readConfig() {
        VaultKeyValueOperations kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
        return kv.get("orders/api"); // đường dẫn tương đối với KV mount
    }
}
```

**Đây là đoạn mã đọc secret**, giả định bean `VaultOperations` đã được tạo bằng workload authentication thích hợp. Với KV v2, `opsForKeyValue("secret", KV_2)` thực hiện việc ghép path API đặc thù của KV v2. Không cần truyền chuỗi `secret/data/orders/api` vào `kv.get()`; `data/` là chi tiết của Vault HTTP API.

Các API đã có và vẫn quan trọng sau khi nâng cấp:

- `vault.read(path)`, `vault.write(path, data)`, `vault.delete(path)`: thao tác ở cấp path, phù hợp khi đã hiểu loại mount và API server.
- `vault.opsForKeyValue(mount, KeyValueBackend.KV_1/KV_2)`: chọn KV theo loại mount, giúp tránh nhầm KV v1 và v2.
- `vault.opsForVersionedKeyValue(mount)`: đọc/ghi version cụ thể, metadata, soft-delete hoặc destroy khi dùng KV v2.
- `vault.opsForTransit(mount)`, `vault.opsForPki(mount)`, `vault.opsForToken()`: tác vụ Transit, PKI và token ở mức domain.
- `LifecycleAwareSessionManager` cùng `SecretLeaseContainer`: quản lý token/lease đã tồn tại **trước** 4.1; không coi chúng là API mới của 4.1.
- `doWithVault(...)` và `doWithSession(...)`: lối thoát về `RestOperations` để gọi endpoint chưa có trong Template API. Đây là nơi cần xem xét kỹ khi đổi lớp HTTP.

Trong 3.x, người viết thư viện hay tự dựng `RestTemplate` hoặc gắn interceptor để thêm Vault namespace, token, timeout, TLS. Cách làm này hoạt động nhưng khiến logic Vault lẫn với logic HTTP, đặc biệt nguy hiểm nếu path do nguồn không tin cậy cung cấp. Nên giới hạn path ở cấu hình đáng tin cậy, validate segment và không cho input người dùng biến thành URL tuyệt đối.

Tham khảo: [Spring Vault 3.2 – VaultTemplate](https://docs.spring.io/spring-vault/reference/3.2/vault/imperative-template.html) và [3.2 – Client Support](https://docs.spring.io/spring-vault/reference/3.2/vault/client-support.html).

## 3. Từ 3.x sang 4.0: thay đổi nền tảng, HTTP client và JSON

### 3.1. Spring Framework 7 và API deprecated bị loại bỏ

Spring Vault **4.0 yêu cầu Spring Framework 7**, không chạy trên Framework 6.x của ứng dụng Spring Boot 3.x theo cách pha trộn dependency. Bản 4.0.0 còn loại bỏ các API đã **deprecated** trước đó, sử dụng chú giải nullability kiểu **JSpecify**, và nâng hệ phụ thuộc tương ứng (ví dụ Spring Data, Spring Security, Kotlin). Với Java, mức runtime tối thiểu vẫn là **17**; không suy rằng Framework 7 bắt buộc Java 21.

Tác động điển hình:

1. Lỗi biên dịch từ những phương thức/lớp đã bị xoá ở 4.0: thay bằng API được công bố trong Javadoc 4.0 trước khi tiếp tục.
2. Lỗi nhị phân như `NoSuchMethodError`/ `NoClassDefFoundError` khi có `spring-core`, `spring-web` hoặc module Spring Data ở **hai thế hệ** trên classpath.
3. Với Kotlin hoặc tooling kiểm tra nullability nghiêm ngặt, annotation JSpecify có thể làm lộ chỗ code đang giả định giá trị không null.

Đừng tự động sửa hàng loạt mọi chỗ gọi `VaultTemplate`: nhiều phương thức domain như `read`, `write`, `opsForTransit`, `opsForPki` vẫn được giữ. Hãy dựa trên lỗi compile, API chính thức và kiểm thử.

### 3.2. `RestClient` trong 4.0 không phải `VaultClient` của 4.1

Spring Vault 4.0 bổ sung hỗ trợ **Spring Framework `RestClient`** và **`RestClientBuilder`** để tạo/kết nối `VaultTemplate`; mô hình chính vẫn là `VaultTemplate`. Chỉ từ **4.1** mới có kiểu **`org.springframework.vault.client.VaultClient`** với builder, `path()`, `token()` và `namespace()` riêng.

```java
// Spring Vault 4.0: API RestClientBuilder (minh hoạ tầng khởi tạo)
import org.springframework.vault.client.RestClientBuilder;
import org.springframework.vault.core.VaultTemplate;

RestClientBuilder restClientBuilder = RestClientBuilder.builder()
        .endpointProvider(endpointProvider);

VaultTemplate vault = new VaultTemplate(restClientBuilder, sessionManager);
```

Ở đây `endpointProvider` và `sessionManager` là các bean hạ tầng được khởi tạo phù hợp với môi trường; đoạn code mô tả **constructor 4.0**, không phải một ứng dụng hoàn chỉnh. Trong dự án dùng Spring Cloud Vault starter, thường để auto-configuration tạo bean thay vì viết lại bộ khởi tạo thủ công.

### 3.3. Jackson 3 và HTTP transport

Spring Vault 4.0 chuyển sang hỗ trợ **Jackson 3** (nhóm Maven `tools.jackson.*`) và còn khả năng tương thích với **Jackson 2** (`com.fasterxml.jackson.*`). **Spring Vault không tự kéo thư viện Jackson vào chỉ để chọn giúp ứng dụng**: phải có mapper đúng trên classpath, ưu tiên phiên bản do BOM Spring Boot quản lý.

```xml
<!-- Trên stack Spring Framework 7/Boot 4, sử dụng Jackson 3 -->
<dependency>
    <groupId>tools.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <!-- version do BOM Spring Boot 4 quản lý -->
</dependency>
```

Nếu **cả Jackson 2 và Jackson 3** xuất hiện, Spring Vault ưu tiên Jackson 3. Do đó ứng dụng có custom `ObjectMapper`, module Kotlin, serializer/deserializer hoặc các lớp chuyển JSON riêng phải test lại việc map Vault response ↔ POJO. Lỗi Jackson Kotlin từng xảy ra ở 4.0.0 và đã được sửa trong các bản vá sau; không đánh đồng “hỗ trợ cả hai phiên bản” với “mọi cấu hình JSON cũ hoạt động nguyên vẹn”.

Về HTTP, **OkHttp support bị bỏ ở 4.0**. Các lựa chọn client hiện tại bao gồm JDK `HttpClient`, Apache Http Components, Reactor Netty và Jetty tùy mode; JDK `HttpClient` là phương án mặc định khi không có client phù hợp khác. Nếu trước đây cấu hình `OkHttp3ClientHttpRequestFactory` hoặc đặt timeout/TLS qua OkHttp, phải chuyển cấu hình sang client được hỗ trợ và chạy kiểm thử kết nối TLS.

Tham khảo: [Spring Vault 4.0 release notes](https://github.com/spring-projects/spring-vault/releases/tag/4.0.0), [4.1 – HTTP Client Support](https://docs.spring.io/spring-vault/reference/vault/client-support.html) và [Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html).

## 4. Spring Vault 4.1+: `VaultClient` và `ReactiveVaultClient`

`VaultClient` là **API fluent đồng bộ** nằm giữa `VaultTemplate` và `RestClient`. Nó hiểu các khái niệm của Vault thay vì buộc người dùng tự tạo header `X-Vault-Token`, `X-Vault-Namespace` hoặc ghép URI bằng tay. `ReactiveVaultClient` tương tự cho luồng `WebClient`, và là **kiểu mới** mặc dù `ReactiveVaultTemplate` đã tồn tại từ trước.

### 4.1. Đọc bằng `VaultClient`

```java
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.support.VaultResponse;

// Ví dụ sử dụng trong dịch vụ đã được inject SessionManager
VaultClient client = VaultClient.create(
        VaultEndpoint.create("vault.internal.example", 8200));

VaultResponse response = client.get()
        .path("secret/data/orders/api")       // path API KV v2
        .token(sessionManager.getSessionToken())
        .retrieve()
        .requiredBody();
```

**Điều kiện:** `sessionManager` đã được cấu hình login và gia hạn token theo workload (Kubernetes/JWT/AppRole hoặc phương thức phù hợp), host chỉ là tên minh hoạ. `VaultClient` tự cung cấp cú pháp header token, nhưng gọi `VaultClient` thuần **không tự mang theo mọi cơ chế `SessionManager`** nếu bạn không truyền token/thiết lập xác thực. Không hard-code Vault token vào mã nguồn và không in `response` ra log.

Ở mức HTTP, `VaultClient` cần **path thật của endpoint Vault**: KV v2 có `data/` trong đường dẫn. Nếu muốn viết `kv.get("orders/api")` mà không phải biết path `data/`, dùng `VaultTemplate.opsForKeyValue(...)` như phần dưới.

### 4.2. Ghép `VaultClient` với `VaultTemplate`

```java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.support.VaultResponse;

VaultOperations vault = new VaultTemplate(client, sessionManager);
VaultKeyValueOperations kv = vault.opsForKeyValue("secret");
VaultResponse result = kv.get("orders/api");
```

Constructor `VaultTemplate(VaultClient, SessionManager)` được thêm ở **4.1**. Việc gọi `opsForKeyValue("secret")` **không truyền `KeyValueBackend`** cũng mới ở 4.1: nó hỏi Vault để nhận diện mount KV v1 hay KV v2. Phương thức này cần kết nối và có thể thất bại nếu không đọc được thông tin mount. Đảm bảo Vault policy phù hợp với yêu cầu xác định mount của API; nếu đã biết trước mount, `opsForKeyValue("secret", KeyValueBackend.KV_2)` vẫn là lựa chọn chủ động và có thể tránh truy vấn phát hiện phiên bản.

Lưu ý khác biệt quan trọng:

| Tình huống | API gợi ý |
| --- | --- |
| 3.x/4.0, biết mount là KV v2 | `opsForKeyValue("secret", KeyValueBackend.KV_2).get("orders/api")` |
| 4.1+, cần tự xác định KV version | `opsForKeyValue("secret").get("orders/api")` |
| 4.1+, cần đọc version số 3 hoặc metadata | `opsForVersionedKeyValue("secret")` |
| 4.1+, endpoint Vault chưa được Template bao phủ | `VaultClient.get()/post()/delete().path(...)` |

**Không có API mới nào tự cấp quyền Vault.** Đọc KV, phát hiện mount và thao tác PKI/Transit vẫn phụ thuộc policy của token, namespace và secrets engine đã mount thực tế.

### 4.3. Giới hạn path theo endpoint và rủi ro URL tuyệt đối

Khi `VaultClient` được tạo với `VaultEndpoint`, việc dùng `.path(...)` kiểm soát cách xây đường dẫn tương đối tới Vault được cấu hình, tránh việc chuỗi absolute URL bất ngờ trỏ sang một máy chủ khác. Tuy nhiên API còn cho phép một số cách chỉ định `URI` hoàn chỉnh, và `VaultTemplate` vẫn có các đường gọi dựa trên chuỗi path. Do đó:

- Ưu tiên `.path("transit/encrypt/orders-key")` và giá trị cố định/đã validate từ code hoặc cấu hình tin cậy.
- Tránh nối input người dùng trực tiếp vào path, nhất là đoạn có `../`, URL-encoded traversal, dấu `/` hay chuỗi URL tuyệt đối.
- Xác định rõ **mount path** và **secret path**, không dùng dữ liệu không tin cậy để chọn namespace, token hoặc Vault endpoint.
- Dùng TLS và timeout hợp lý; trên log chỉ ghi thông tin lỗi đã che token/secret.

Điểm này có giá trị bảo mật thực tế: các bản **Spring Vault 4.0.5 và 4.1.2** phát hành ngày **19/11/2026** vá **CVE-2026-41698** liên quan đến path traversal qua tham số secret path chưa được làm sạch. Khi dùng 4.0/4.1, hãy chọn patch đã vá và vẫn validate đầu vào.

### 4.4. Phân biệt exception ở các tầng

`VaultClient`/`ReactiveVaultClient` chuẩn hoá lỗi giao tiếp thông qua **`VaultClientResponseException`** (thuộc họ `VaultException`), cho phép lấy HTTP status, headers và response body ở tầng client. Các API `VaultTemplate`/domain có thể chuyển lỗi sang `VaultException` thích hợp; không nên giả định một exception cụ thể xuất hiện giống nhau ở cả hai tầng.

Về nghiệp vụ: **401/403** thường yêu cầu kiểm tra token, namespace, policy; **404** có thể là không có secret, sai KV version/path hoặc mount; lỗi kết nối/timeout cần retry có giới hạn và giám sát. Lỗi `404` không phải lý do tự động ghi secret mới. Với `vault.read(...)`, kiểm tra tình huống trả `null`; với `readRequired(...)` hoặc `requiredBody()`, kỳ vọng cách xử lý “không có dữ liệu” khác với phương thức có thể trả về `null`.

Nguồn: [Spring Vault – Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html), [VaultClient Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.html), [bài viết thiết kế VaultClient](https://spring.io/blog/2025/12/26/evolving-spring-vault/) và [advisory bản vá 4.0.5/4.1.2](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/).

## 5. Di chuyển phần tuỳ biến HTTP khi nâng lên 4.1

Lý do phổ biến khiến dự án bị kẹt ở API cũ là có **code tự tạo bean HTTP client**, interceptor namespace, request factory hoặc TLS/timeout. Từ 4.1, các constructor `VaultTemplate` dùng `RestTemplateBuilder`, `ClientHttpRequestFactory` theo một số chữ ký, cùng `RestTemplateCustomizer`/`RestTemplateBuilder` được đánh dấu **deprecated** để khuyến khích `VaultClient` và client customizer mới. **Deprecated không có nghĩa là bị xoá ngay ở 4.1.**

| Trước đây | Hướng đi từ 4.1 | Vì sao |
| --- | --- | --- |
| `RestTemplateCustomizer` để thêm namespace Vault | `VaultClientCustomizer`; dùng `builder.defaultNamespace(...)` | Diễn đạt rõ đây là thuộc tính của request tới Vault |
| Interceptor để tự đặt `X-Vault-Token` | `VaultClient.token(VaultToken)` hoặc `VaultTemplate` với session manager | Giảm xử lý token thủ công; dễ kiểm soát vòng đời token |
| Tự tạo `RestTemplate` để gọi endpoint Vault | `VaultClient` hoặc `VaultTemplate` trên `VaultClient` | Giữ path/namespace và lỗi trong lớp Vault-specific |
| Tuỳ chỉnh chung `RestClient` (timeout, HTTP factory, converter) | `RestClientCustomizer`, `VaultClient.Builder.configureRestClient(...)` hoặc factory phù hợp | Các thông số thấp tầng vẫn thuộc HTTP client |
| Override `VaultTemplate.doCreateRestTemplate(...)` | Constructor nhận `VaultClient` và customizer tương ứng | Không phụ thuộc vào hook đã deprecated |
| Reactive custom `WebClient` | `ReactiveVaultClientCustomizer` hoặc client reactive phù hợp | Không biến reactive call thành blocking operation |

Ví dụ bean sử dụng hạ tầng cấu hình Spring Vault **4.1+**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.client.VaultClientCustomizer;

@Configuration
class VaultCustomization {

    @Bean
    VaultClientCustomizer namespaceCustomizer() {
        return builder -> builder.defaultNamespace("team-orders");
    }
}
```

`VaultClientCustomizer` được các cơ chế cấu hình Spring Vault có hỗ trợ nhận diện để áp dụng lên `VaultClient.Builder`. Nếu dự án tự `new VaultClient` bằng tay, **bean customizer không tự ảnh hưởng** đến instance đó: phải chủ động áp dụng cấu hình. Với Spring Cloud Vault, cần kiểm tra phiên bản Cloud Vault đi kèm 4.1 và cơ chế auto-configuration tương ứng; không ghép ngẫu nhiên starter và Core khác thế hệ.

Đặc biệt với request factory: ở 3.x client mặc định có thể là `HttpURLConnection`, còn 4.x dùng JDK `HttpClient` mặc định. Đừng chỉ test “đọc được một secret”: cần kiểm tra proxy, mTLS, CA truststore, timeout, connection pooling, streaming/request body và khả năng retry an toàn.

Tham khảo: [VaultClientCustomizer Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClientCustomizer.html), [bài viết chuyển đổi API HTTP](https://spring.io/blog/2025/12/26/evolving-spring-vault/).

## 6. API 4.1 quản lý vòng đời secret: `ManagedSecret`

`SecretLeaseContainer` có từ các phiên bản trước, quản lý `RequestedSecret`, gia hạn lease và phát `SecretLeaseCreatedEvent`, `SecretLeaseRotatedEvent`, `SecretLeaseExpiredEvent`, `SecretLeaseErrorEvent`. Trong 4.1, **`ManagedSecret`** giúp gắn hành động cập nhật ứng dụng trực tiếp vào secret được quản lý, thay vì mỗi consumer tự viết listener và lọc event.

Mô hình:

```text
Vault dynamic credentials (database/creds/orders)
             │
             ▼
      SecretLeaseContainer
       renew / request again
             │
             ▼
         ManagedSecret
       mapping + callback
             │
             ▼
    Cập nhật người dùng mật khẩu
    cho pool / client đang sử dụng
```

Trong một ứng dụng có bean `HikariDataSource`, tài liệu Spring đưa ví dụ dùng `ManagedSecret.rotating("mysql/creds/my-role", secrets -> secrets.as(UsernamePassword::from).applyTo(...))` để đưa username/password mới vào datasource. **Ý nghĩa là thay đổi ứng dụng khi secret xoay vòng**; thực tế việc thay credentials có tác dụng với connection mới hay connection đang mở còn phụ thuộc cấu hình pool và cách đóng/mở kết nối. Không áp dụng callback như một bảo đảm toàn bộ session JDBC cũ đều được thay ngay.

`ManagedSecret` hỗ trợ mô hình xoay vòng secret **có lease** và những trường hợp secret không có lease mà vẫn cần rotation, theo khả năng và chính sách Vault. Cần chọn TTL, vòng đời token, retries và xử lý secret hết hạn phù hợp. Dù abstraction mới giảm code lặp, vẫn phải bảo vệ giá trị bí mật khỏi log, metric tags và exception messages.

**Một trường hợp cần test:** token dùng để lấy credential hết hạn; `LifecycleAwareSessionManager` hoặc cơ chế session tương đương đăng nhập lại nhưng các lease cũ bị revoke. Hãy xác minh `SecretLeaseContainer` có thể yêu cầu credential mới và ứng dụng thực sự dùng giá trị mới.

## 7. API 4.1 quản lý chứng chỉ: `CertificateContainer`, `ManagedCertificate`

Ở 3.x/4.0, API PKI `opsForPki()` cung cấp tác vụ issue/revoke certificate, nhưng lập lịch rotation và cập nhật TLS/SSL trong ứng dụng thường do người viết tích hợp tự lo. Từ 4.1:

- **`CertificateContainer`**: quản lý việc xin và phát hành lại certificate dựa trên hạn dùng, cùng lifecycle/events.
- **`ManagedCertificate`**: đăng ký certificate cần quản lý và callback khi certificate bundle thay đổi; có thể nối vào thành phần sử dụng chứng chỉ, ví dụ SSL bundle.
- **`RequestedCertificate`** và các event liên quan: mô tả yêu cầu certificate và chu kỳ cấp lại.

Ví dụ rút gọn theo API 4.1:

```java
@Bean
ManagedCertificate tlsCertificate(SslBundles sslBundles) {
    VaultCertificateRequest request = VaultCertificateRequest.builder()
            .commonName("orders.internal.example")
            .ttl(Duration.ofHours(12))
            .build();

    return ManagedCertificate.issue(
            "orders-tls", "orders-pki-role", request,
            bundle -> sslBundles.register("orders-tls",
                    bundle.createKeyStore("orders-key")));
}
```

Ví dụ minh hoạ cách gắn PKI role và callback vào SSL bundle; cần import đúng kiểu trong dự án và bảo đảm `SslBundles` hoặc registry cụ thể cho phép đăng ký/cập nhật như mong đợi. **PKI certificate có thể không có Vault lease**; thời điểm rotation dựa vào thời hạn certificate và chính sách container, không đồng nhất với gia hạn token. Cần kiểm tra bên sử dụng certificate có thực sự tải lại key/trust material khi rotate.

`CertificateContainer` là thành phần lifecycle: bean cần được đăng ký và start đúng thời điểm. Tài liệu cảnh báo callback có thể đến sau các hook khởi tạo như `@PostConstruct`, nên hãy kiểm tra thứ tự khởi tạo và việc sẵn sàng của certificate trước khi khởi động HTTP server hoặc database client cần mTLS.

Nguồn: [Credential Rotation – SecretLeaseContainer, ManagedSecret, CertificateContainer](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html).

## 8. Những API cũ vẫn nên giữ khi chúng giải quyết đúng nhu cầu

Không phải tất cả code sau nâng cấp đều cần chuyển sang `VaultClient`. Quy tắc:

| Nhu cầu | API nên ưu tiên | Lý do |
| --- | --- | --- |
| KV v1/v2 CRUD theo mount | `VaultOperations.opsForKeyValue(...)` | API domain che chi tiết HTTP path, tiện xử lý response |
| KV v2 version/metadata/soft-delete/destroy | `opsForVersionedKeyValue(...)` | Có API rõ ràng cho phiên bản và metadata |
| Transit encrypt/decrypt | `opsForTransit(...)` | Thể hiện rõ cryptographic operation; plaintext không cần lưu vào KV |
| PKI issue/revoke theo yêu cầu | `opsForPki(...)` | Domain API vẫn phù hợp |
| PKI certificate cần tự động rotate | `ManagedCertificate` + `CertificateContainer` (4.1+) | Quản lý vòng đời thay vì chỉ issue một lần |
| Database credential có lease và cần cập nhật runtime | `ManagedSecret` (4.1+) hoặc `SecretLeaseContainer` | Bám theo sự kiện renewal/rotation |
| Vault endpoint đặc biệt chưa có Template API | `VaultClient` (4.1+) | Fluent HTTP Vault-specific; không cần callback `RestOperations` cho code mới |
| Mô hình reactive hoàn toàn | `ReactiveVaultTemplate` và khi cần `ReactiveVaultClient` (4.1+) | Không chặn event loop bằng API đồng bộ |

**Về bảo mật:** một bản nâng cấp Spring Vault không tự thay đổi quyền hạn của token. Cần dùng authentication gắn với workload, Vault policy theo nguyên tắc quyền tối thiểu, namespace đúng, TLS và cơ chế renewal/rotation phù hợp ứng dụng.

## 9. Quy trình migration thực tế từ 3.x qua 4.0 sang 4.1

### Bước 1 — Kiểm kê API và phụ thuộc hiện có

Tìm những vị trí sau trong mã ứng dụng:

```text
VaultTemplate / VaultOperations / ReactiveVaultTemplate
RestTemplateBuilder / RestTemplateCustomizer
RestOperationsCallback / doWithVault / doWithSession
ClientHttpRequestFactory / OkHttp3ClientHttpRequestFactory
MappingJackson2HttpMessageConverter / ObjectMapper
SessionManager / LifecycleAwareSessionManager
SecretLeaseContainer / LeaseListener
opsForKeyValue / opsForVersionedKeyValue
opsForTransit / opsForPki
```

Kèm theo phiên bản thực được giải quyết từ classpath, thay vì chỉ nhìn vào dependency khai báo:

```bash
# Maven
mvn dependency:tree
mvn help:effective-pom

# Gradle
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-core
```

### Bước 2 — Nâng nền tương thích

- **3.1.x** thường ứng với Spring Framework **6.1.x**, **3.2.x** ứng với **6.2.x**. Không nhảy từ Boot 3/Framework 6 sang Spring Vault 4.x riêng lẻ.
- Chọn Spring Boot 4/Framework 7 cùng BOM và Spring Cloud release train tương thích nếu sử dụng `spring-cloud-starter-vault-config`.
- Nâng lên **bản vá đã sửa lỗi** của Spring Vault trong nhánh tương thích; đến 25/11/2026, các bản 4.x được công bố là **4.0.5 / 4.1.2**.
- Kiểm tra Jackson, HTTP transport, các API từng deprecated, nullability và các lớp nội bộ mà ứng dụng đang mở rộng.

### Bước 3 — Ổn định hành vi ở 4.0 trước khi đổi kiến trúc ở 4.1

Đầu tiên giữ business code trên `VaultOperations` và kiểm tra KV, Transit, PKI, token/lease chạy đúng với Framework 7. Sau đó thay các cấu hình OkHttp/Jackson/HTTP client không tương thích. Việc chia hai bước giúp xác định lỗi thuộc **nâng nền 4.0** hay **chuyển mô hình client 4.1**.

### Bước 4 — Chuyển dần phần code cần `VaultClient`

Đổi các callback HTTP thuần và custom interceptor khi hợp lý. Migrate `RestTemplateCustomizer` sang `VaultClientCustomizer`; dùng `RestClientCustomizer` cho timeout, connector và conversion. Không thay các API domain đang hoạt động tốt chỉ để dùng syntax mới.

### Bước 5 — Kiểm thử bảo mật và vận hành

| Kịch bản | Kết quả cần xác nhận |
| --- | --- |
| Workload login bằng Kubernetes/JWT/AppRole | Không cần hard-code root token; token có policy đúng; login lại sau expiration theo thiết kế |
| KV v1 và KV v2 trên hai mount | Trả đúng giá trị; path không bị ghép `data/` hai lần; thiếu secret được xử lý rõ |
| Phát hiện KV version 4.1 | Có quyền lấy thông tin mount và nhận đúng phiên bản; thiếu quyền báo lỗi dễ hiểu |
| Transit encrypt/decrypt | Payload tương ứng; không log plaintext/ciphertext nhạy cảm |
| PKI issue/rotation | Certificate đúng role/CN/TTL, client sử dụng chứng chỉ mới sau rotation |
| Token/lease hết hạn, Vault trả 401/403 | Session/lease recovery phù hợp; không retry vô hạn hoặc bỏ qua policy |
| Vault 404/429/5xx hoặc timeout | Lỗi phân loại đúng, có timeout/backoff phù hợp và metric; không in token/secret |
| Path từ nguồn bên ngoài | Reject path sai format, traversal và URI tuyệt đối; không điều hướng sang host khác |
| Nâng JSON mapper | Jackson 3/2 không gây lỗi conversion, POJO/Kotlin custom serializer hoạt động |

Lập các integration test với Vault test instance (có thể dùng Testcontainers khi đã có hạ tầng Docker), policies và secrets engines gần giống môi trường chạy thật. Mock `VaultOperations` chỉ kiểm tra business logic; không thay thế được kiểm thử auth, lease, mount/path, TLS hoặc lỗi API Vault.

## 10. Tóm tắt quyết định kỹ thuật

**3.x:** `VaultTemplate` + `RestTemplate` là kiến trúc nền, các API KV/Transit/PKI và lease containers đã có. **4.0:** nâng lên Framework 7, thêm `RestClient`/Jackson 3, đổi HTTP transport và gỡ API deprecated cũ. **4.1+:** thêm `VaultClient`/`ReactiveVaultClient`, KV version detection, `ManagedSecret` và `ManagedCertificate`/`CertificateContainer`; một số API cấu hình `RestTemplate` được đánh dấu deprecated để chuyển dần.

Với code nghiệp vụ đang dùng `VaultOperations`, thường **giữ API domain và nâng nền trước**. Với code tự dựng HTTP, namespace, token hoặc rotation, **đọc Javadoc 4.1 để chọn đường thay thế**. Kết thúc bằng dependency tree, kiểm thử workload/policy thực và bản vá bảo mật đã được công bố.

### Tài liệu tham khảo chính thức

1. [Spring Vault 3.2 – VaultTemplate](https://docs.spring.io/spring-vault/reference/3.2/vault/imperative-template.html)
2. [Spring Vault 3.2 – HTTP Client Support](https://docs.spring.io/spring-vault/reference/3.2/vault/client-support.html)
3. [Spring Vault 4.0 GA (18/11/2025)](https://spring.io/blog/2025/11/18/spring-vault-4-0-goes-ga/)
4. [Spring Vault 4.0 – Release notes](https://github.com/spring-projects/spring-vault/releases/tag/4.0.0)
5. [Spring Vault 4.1 GA (10/06/2026)](https://spring.io/blog/2026/06/10/spring-vault-4-1-available/)
6. [Spring Vault 4.1 – Release notes](https://github.com/spring-projects/spring-vault/releases/tag/4.1.0)
7. [Spring Vault 4.1 – VaultClient Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.html)
8. [Spring Vault 4.1 – VaultTemplate Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
9. [Spring Vault 4.1 – Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
10. [Spring Vault 4.1 – Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
11. [Evolving Spring Vault: Introducing VaultClient](https://spring.io/blog/2025/12/26/evolving-spring-vault/)
12. [Spring Vault 4.0.5 và 4.1.2 – bản vá CVE-2026-41698 (19/11/2026)](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/)
