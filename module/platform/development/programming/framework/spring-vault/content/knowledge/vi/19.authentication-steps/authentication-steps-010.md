# Kiểm thử các bước AuthenticationSteps bằng đầu vào và phản hồi giả

## 1. Bối cảnh và mục tiêu

Trong chương **Authentication Steps** của module **SPRING_VAULT**, ứng dụng Java cần Vault client token để truy cập HashiCorp Vault qua `VaultTemplate`, đọc KV secrets, gọi Transit encryption hoặc PKI. Với những phương thức xác thực theo workload như AppRole, Kubernetes hay AWS, quá trình lấy token có nhiều bước: đọc credential, chuyển đổi đầu vào, gửi yêu cầu tới Vault, nhận phản hồi và tạo đối tượng token.

Spring Vault cung cấp `AuthenticationSteps` để **mô tả chuỗi thao tác xác thực**, cùng `AuthenticationStepsExecutor` hoặc `AuthenticationStepsOperator` để **thực thi** chuỗi đó. Khi phát triển, ta có thể dùng **đầu vào giả và phản hồi giả** để kiểm chứng flow mà không cần Vault server cho mọi bài test.

Sau bài học, bạn có thể:

- Phân biệt test phép chuyển đổi credential, test HTTP contract của login flow và integration test với Vault thật.
- Dùng `fromSupplier`, `map`, `zipWith`, `login(Function)`, `login(String, ...)` và HTTP mock để kiểm tra pipeline.
- Assert HTTP method, đường dẫn, request body, cấu trúc phản hồi `auth.client_token` và metadata token.
- Kiểm tra input không hợp lệ, `403`, `5xx`, phản hồi JSON sai, timeout, credential xoay vòng và trình tự thực thi.
- Dùng Reactor `StepVerifier` cho `AuthenticationStepsOperator` trên ứng dụng reactive.
- Giữ token, JWT, SecretID và private key thật ngoài source code, fixtures và log.

> Toàn bộ tên host, RoleID, SecretID và Vault token trong ví dụ là giá trị **giả**. Những ví dụ sử dụng `RestClient`/`MockRestServiceServer` áp dụng với Spring Framework 6.1+ và dòng Spring Vault 4.x phù hợp. Nếu dự án dùng Spring Vault 3.x, cần điều chỉnh theo API đồng bộ dựa trên `RestOperations`.

## 2. AuthenticationSteps hoạt động như thế nào?

### 2.1. Các khâu của pipeline

| Khâu | API | Vai trò | Ranh giới kiểm thử |
|---|---|---|---|
| Đầu vào | `AuthenticationSteps.fromValue(...)` | Dùng một giá trị trực tiếp; có từ Spring Vault 2.3 | Giá trị được chuyển đúng |
| Đầu vào | `AuthenticationSteps.fromSupplier(...)` | Nhận giá trị khi flow chạy | Số lần gọi supplier, dữ liệu hiện hành |
| HTTP đầu vào | `fromHttpRequest(...)` | Lấy credential/identity từ HTTP ngoài Vault | Method, URL, body/response từ HTTP mock |
| HTTP Vault | `fromVaultRequest(...)` | Lấy dữ liệu từ Vault trong một bước trung gian | Vault path/header và dữ liệu trả về |
| Chuyển đổi | `map(Function)` | Chuyển dữ liệu giữa các trạng thái | Format, validation, giá trị biến đổi |
| Kết hợp | `zipWith(other)` | Ghép hai nguồn như RoleID và SecretID | Không đảo sai hai đầu vào |
| Quan sát | `onNext(Consumer)` | Xử lý callback ở trạng thái trung gian | Callback chạy, không làm lộ secret |
| Hoàn thành | `login(Function)` | Ánh xạ giá trị hiện tại thành `VaultToken` | Token giả, ngoại lệ khi mapping lỗi |
| Hoàn thành | `login("auth/{mount}/login", mount)` | POST vào endpoint Vault và đọc login response | Request/response HTTP và token thật sự được parse |

Từ **Spring Vault 4.1**, `loginAt("approle")` là biến thể ngắn của thao tác POST vào đường dẫn `auth/approle/login`. Với các phiên bản cũ hơn, dùng `login("auth/{mount}/login", "approle")`.

`AuthenticationSteps` **chỉ định nghĩa flow**, chưa thực hiện request hay đọc giá trị supplier. Việc chạy diễn ra khi:

- `AuthenticationStepsExecutor.login()` thực thi đồng bộ và trả `VaultToken`. Executor thực hiện `ClientAuthentication` nên có thể được kết hợp với session manager.
- `AuthenticationStepsOperator.getVaultToken()` trả `Mono<VaultToken>` và các bước được thực thi theo reactive subscription.

~~~mermaid
flowchart LR
    A[Supplier / HTTP source] --> B[AuthenticationSteps]
    B --> C[map / zipWith / onNext]
    C --> D[login Function hoặc HTTP Vault]
    D --> E{Executor}
    E --> F[Đồng bộ: login]
    E --> G[Reactive: getVaultToken]
    F --> H[VaultToken hoặc exception]
    G --> H
    H --> I[Assertions: đầu vào, request, response]
~~~

Không có API public dành cho việc chạy tùy ý một node ở giữa pipeline bằng `executeStep(2)`. Nếu cần test riêng một phép biến đổi, hãy tách nó thành hàm Java thuần; nếu muốn test cách ghép node, hãy chạy **toàn bộ flow** với nguồn dữ liệu giả.

### 2.2. Các mức test phục vụ mục đích khác nhau

| Mức test | Cần Vault thật? | Phát hiện tốt nhất |
|---|---|---|
| Unit test `Supplier`/`map`/`login(Function)` | Không | Chuẩn hóa, mapping, validation, đọc credential mới |
| Test flow với HTTP mock | Không | Sai HTTP method, URL, JSON payload, JSON response, mã lỗi |
| Integration test với Vault dev/Testcontainers | Có | Role, Vault policy, chữ ký/token, TTL thực tế, phân quyền KV/Transit |
| Test toàn hệ thống | Có, trong môi trường kiểm thử độc lập | Vault outage, network timeout, token rotation, Pod restart, session renew |

Giả lập `VaultTemplate.read()` ở tầng ứng dụng **không kiểm thử** `AuthenticationSteps`, bởi request đọc KV chỉ xảy ra sau khi đã có Vault token. Để test login flow, hãy thực thi executor/operator thật và mock **nguồn credential/HTTP** ở ranh giới bên ngoài.

## 3. Chuẩn bị công cụ kiểm thử

Các thư viện thường dùng gồm **JUnit Jupiter 5**, **Spring Vault Core**, **Spring Test**, **Spring Web** (cho `RestClient`), và tùy chọn **Reactor Test**/`StepVerifier` cho reactive. Mockito hữu ích khi cần mock một client hoặc nguồn thông tin, nhưng không bắt buộc đối với các ví dụ dùng `MockRestServiceServer`.

Ví dụ dependency trong một dự án Spring Boot tương thích và có BOM quản lý phiên bản:

~~~groovy
dependencies {
    implementation("org.springframework.vault:spring-vault-core")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test") // Nếu có test reactive
}
~~~

Nếu không dùng Spring Boot, khai báo các dependency test tương ứng bằng đúng version phù hợp. `AuthenticationStepsExecutor(steps, RestOperations)` được dùng ở Spring Vault 3.x nhưng **deprecated trong 4.1**; bản 4.x hỗ trợ `RestClient` và bản 4.1 có constructor nhận tách biệt `VaultClient` với `RestClient` ngoài Vault.

Đặt hostname giả như `vault.test.invalid`, sử dụng token giả. Test HTTP phải cấu hình mock chặn mọi request định thử; một request chưa khai báo phải làm test thất bại chứ không rơi sang Vault production.

## 4. Test với đầu vào giả, không gọi Vault

Đầu tiên dùng `fromSupplier` lấy chuỗi giả, `map` chuẩn hóa và `login(Function)` biến dữ liệu thành token giả. Test này chạy executor thật nhưng flow **không có HTTP step**, nên không gọi mạng.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationStepsExecutor;
import org.springframework.vault.support.VaultToken;
import org.springframework.web.client.RestClient;

class AuthenticationStepsInputTest {

    @Test
    void readsUpdatedInputOnlyWhenFlowIsExecuted() {
        AtomicReference<String> credential =
                new AtomicReference<>(" identity-A ");
        AtomicInteger reads = new AtomicInteger();

        AuthenticationSteps steps = AuthenticationSteps
                .fromSupplier(() -> {
                    reads.incrementAndGet();
                    return credential.get();
                })
                .map(String::trim)
                // Giả lập terminal, không đăng nhập vào Vault thật.
                .login(id -> VaultToken.of("fake-token-" + id));

        AuthenticationStepsExecutor executor =
                new AuthenticationStepsExecutor(steps, RestClient.create());

        assertEquals(0, reads.get());

        VaultToken first = executor.login();
        assertEquals("fake-token-identity-A", first.getToken());
        assertEquals(1, reads.get());

        // Mô phỏng nguồn credential được xoay vòng sau lần login đầu.
        credential.set(" identity-B ");
        VaultToken second = executor.login();
        assertEquals("fake-token-identity-B", second.getToken());
        assertEquals(2, reads.get());
    }
}
~~~

Kết quả mong đợi cho thấy: **định nghĩa flow chưa đọc credential**, mỗi lần `executor.login()` lại lấy input và ánh xạ qua `map`, và giá trị mới không bị kẹt ở một chuỗi cache tạo khi khởi tạo bean.

Đây không phải kiểm thử JWT hợp lệ, AppRole có quyền thực hay Vault cấp token. Giá trị `fake-token-identity-A` là dữ liệu test chủ động tạo, không được dùng làm token vận hành.

### 4.1. Test nhánh đầu vào sai

Flow có thể chủ động kiểm tra đầu vào trong `map`. Ví dụ từ chối credential chỉ chứa khoảng trắng:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationStepsExecutor;
import org.springframework.vault.support.VaultToken;
import org.springframework.web.client.RestClient;

class AuthenticationStepsValidationTest {

    @Test
    void refusesBlankCredential() {
        AuthenticationSteps steps = AuthenticationSteps
                .fromSupplier(() -> "   ")
                .map(raw -> {
                    String value = raw.trim();
                    if (value.isEmpty()) {
                        throw new IllegalArgumentException(
                                "Test credential is missing");
                    }
                    return value;
                })
                .login(value -> VaultToken.of("fake-" + value));

        AuthenticationStepsExecutor executor =
                new AuthenticationStepsExecutor(steps, RestClient.create());

        assertThrows(IllegalArgumentException.class, executor::login);
    }
}
~~~

Test thứ hai kiểm tra **validation do ứng dụng tự thêm**, không có nghĩa Spring Vault mặc định luôn ném cùng loại exception và thông điệp đối với mọi nguồn trống. Nhờ validation sớm, test còn chứng minh flow sẽ không cố sinh token từ credential sai.

## 5. Test phản hồi HTTP giả cho AppRole login

Phần quan trọng hơn là kiểm thử HTTP request thật sự được tạo ra bởi `AuthenticationStepsExecutor`. Giả sử AppRole auth mount là `approle`. Flow sẽ gửi:

~~~http
POST /v1/auth/approle/login
Content-Type: application/json

{"role_id":"role-demo","secret_id":"secret-demo"}
~~~

Đáp lại, Vault thành công thường trả JSON với object `auth`:

~~~json
{
  "request_id": "request-demo",
  "auth": {
    "client_token": "token-demo",
    "accessor": "accessor-demo",
    "policies": ["payments-kv-read"],
    "token_policies": ["payments-kv-read"],
    "lease_duration": 600,
    "renewable": true,
    "token_type": "service"
  }
}
~~~

Trong response login, trường cần quan sát nhất là `auth.client_token`. `lease_duration` và `renewable` xác định thông tin vòng đời của `LoginToken`. Đừng nhầm object `data` của một KV response với object `auth` của response đăng nhập.

### 5.1. JUnit test với MockRestServiceServer

Đoạn test dùng `RestClient` của Spring Framework 6.1+, `MockRestServiceServer.bindTo(RestClient.Builder)` trong Spring Test và `AuthenticationStepsExecutor(steps, RestClient)` của Spring Vault 4.x.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationStepsExecutor;
import org.springframework.vault.authentication.LoginToken;
import org.springframework.vault.support.VaultToken;
import org.springframework.web.client.RestClient;

class AuthenticationStepsHttpTest {

    @Test
    void postsPayloadAndParsesFakeVaultLoginResponse() {
        String base = "https://vault.test.invalid/v1";
        RestClient.Builder builder = RestClient.builder().baseUrl(base);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();
        RestClient restClient = builder.build();

        AuthenticationSteps steps = AuthenticationSteps
                .fromSupplier(() -> Map.of(
                        "role_id", "role-demo",
                        "secret_id", "secret-demo"))
                .login("auth/{mount}/login", "approle");

        server.expect(requestTo(base + "/auth/approle/login"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.role_id").value("role-demo"))
                .andExpect(jsonPath("$.secret_id").value("secret-demo"))
                .andRespond(withSuccess("""
                    {
                      "request_id": "request-demo",
                      "auth": {
                        "client_token": "token-demo",
                        "accessor": "accessor-demo",
                        "policies": ["payments-kv-read"],
                        "token_policies": ["payments-kv-read"],
                        "lease_duration": 600,
                        "renewable": true,
                        "token_type": "service"
                      }
                    }
                    """, MediaType.APPLICATION_JSON));

        AuthenticationStepsExecutor executor =
                new AuthenticationStepsExecutor(steps, restClient);

        VaultToken token = executor.login();
        assertEquals("token-demo", token.getToken());
        assertTrue(token instanceof LoginToken);
        LoginToken loginToken = (LoginToken) token;
        assertTrue(loginToken.isRenewable());
        assertEquals(600, loginToken.getLeaseDuration().getSeconds());

        server.verify();
    }
}
~~~

Bài test xác nhận ba phần nối nhau: **Supplier tạo payload**, HTTP terminal gửi đúng URL/method/JSON và executor **phân tích phản hồi** để tạo Vault token với metadata TTL. Không cần Vault server, không có request thực nào tới hostname `vault.test.invalid`.

**Đường dẫn của client phải khớp cách tạo Vault API client.** Ví dụ dùng base URL `https://vault.test.invalid/v1` và route tương đối `auth/approle/login`. Nếu dự án cung cấp `VaultClient`/`VaultEndpoint` riêng (Spring Vault 4.1+) hoặc tự chèn `/v1`, hãy điều chỉnh mock cho đúng request thực tế và tránh prefix hai lần. Có thể thay phần terminal bằng `loginAt("approle")` khi dùng Spring Vault 4.1+.

### 5.2. Test khi Vault từ chối credentials

Một flow login có thể trả lỗi `403 Forbidden` do credential không khớp hoặc auth role từ chối. Mock response nên mô phỏng lỗi này, và test cần assert rằng executor **không sinh token thành công**:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.vault.VaultException;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationStepsExecutor;
import org.springframework.web.client.RestClient;

class AuthenticationStepsForbiddenTest {

    @Test
    void refusesForbiddenLogin() {
        String base = "https://vault.test.invalid/v1";
        RestClient.Builder builder = RestClient.builder().baseUrl(base);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        AuthenticationSteps steps = AuthenticationSteps
                .fromSupplier(() -> Map.of(
                        "role_id", "role-demo",
                        "secret_id", "invalid-secret-demo"))
                .login("auth/approle/login");

        server.expect(requestTo(base + "/auth/approle/login"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withStatus(HttpStatus.FORBIDDEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"errors\":[\"permission denied\"]}"));

        AuthenticationStepsExecutor executor =
                new AuthenticationStepsExecutor(steps, builder.build());

        assertThrows(VaultException.class, executor::login);
        server.verify();
    }
}
~~~

Loại exception cụ thể có thể thay đổi theo phiên bản của Spring Vault và HTTP adapter (ví dụ subclass `VaultLoginException`). Khi chuyển sang một release khác, hãy kiểm tra contract exception và tránh assert thông điệp lỗi tiếng Anh. `403` khi login là lỗi **xác thực Vault**, trong khi `403` ở `kv-app/data/...` sau login thường là lỗi **phân quyền trên secret path**.

### 5.3. Những response khác cần giả lập

Nên bổ sung test với HTTP `500/503`, timeout và JSON không hợp lệ. Với HTTP 200 nhưng thiếu `auth.client_token`, test phải chứng minh flow **không chấp nhận một token rỗng/không hợp lệ**. Lỗi có thể xuất hiện trong quá trình deserialize, xác minh phản hồi hoặc tạo token tùy phiên bản; không buộc test vào một exception message không được API bảo đảm.

Đối với timeout, dùng client/server mock có timeout **ngắn và được kiểm soát**, không dùng sleep hoặc kết nối host thật để chờ đến timeout của hệ điều hành. Kiểm thử phải có deadline và kết thúc có thể dự đoán.

## 6. Giả lập hai bước HTTP: lấy identity ngoài Vault, rồi đăng nhập

Một số auth method cần lấy chứng cứ nhận dạng từ một endpoint bên ngoài Vault, ví dụ AWS EC2 identity metadata. Trong Spring Vault, `AuthenticationSteps.fromHttpRequest(...)` cho phép diễn đạt bước này, sau đó dùng `map` để dựng payload login:

~~~java
import java.util.Map;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationSteps.HttpRequestBuilder;

AuthenticationSteps steps = AuthenticationSteps
        .fromHttpRequest(HttpRequestBuilder
                .get("https://identity.test.invalid/identity-document")
                .as(String.class))
        .map(document -> document.replace("\r", "").trim())
        .map(document -> Map.of(
                "pkcs7", document,
                "nonce", "nonce-demo"))
        .login("auth/aws-ec2/login");
~~~

Đây là flow **minh họa** cách kiểm thử, không thay cho quy trình xác thực AWS EC2 thật với PKCS#7/nonce/role. Một test dành cho flow này cần hai HTTP mock:

1. **Identity endpoint giả** trả dữ liệu văn bản khi nhận GET `/identity-document`. Assert document đã được chuẩn hóa và đưa vào field `pkcs7`.
2. **Vault endpoint giả** nhận POST `/v1/auth/aws-ec2/login` với `pkcs7` và `nonce`, rồi trả JSON `auth.client_token`.

Nếu identity endpoint trả `404` hoặc timeout, flow phải thất bại ở bước lấy identity và **không nên gửi request login**. Khi dùng Spring Vault 4.1, constructor executor nhận tách biệt `VaultClient` và `RestClient` ngoài Vault giúp tách mock cho hai tuyến; với phiên bản khác, cấu hình HTTP mocks theo adapter đang dùng.

Việc test luồng HTTP thành công chưa chứng minh danh tính EC2/JWT có chữ ký hợp lệ hoặc không bị replay. Xác minh cryptographic proof và role binding phải kiểm thử với Vault test server thật.

## 7. Ghép hai đầu vào bằng zipWith

AppRole có thể nhận `RoleID` và `SecretID` từ hai nguồn khác nhau. `zipWith` kết hợp hai node; `map` tạo JSON payload cho login:

~~~java
import java.util.Map;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationSteps.Node;

Node<String> roleId =
        AuthenticationSteps.fromSupplier(() -> "role-demo");
Node<String> secretId =
        AuthenticationSteps.fromSupplier(() -> "secret-demo");

AuthenticationSteps steps = roleId
        .zipWith(secretId)
        .map(pair -> Map.of(
                "role_id", pair.getLeft(),
                "secret_id", pair.getRight()))
        .login("auth/approle/login");
~~~

Để test các trường hợp credential thay đổi, dùng hai `AtomicReference<String>` độc lập:

| Tình huống | RoleID giả | SecretID giả | Điều cần kiểm tra |
|---|---|---|---|
| Cả hai có dữ liệu | `role-A` | `secret-A` | JSON body chứa đúng hai key và giá trị tương ứng |
| Chỉ xoay SecretID | `role-A` | `secret-B` | Lần login sau dùng SecretID mới |
| Chỉ xoay RoleID | `role-B` | `secret-A` | Giá trị RoleID mới không bị cache |
| Supplier báo lỗi | `role-A` | Ném lỗi có chủ đích | Không nhận token thành công |
| Vault từ chối cặp credential | `role-B` | `secret-B` | HTTP 403 đưa về caller, không retry vô hạn trong flow |

Đừng dựa vào thứ tự side effect của hai nhánh độc lập như một hợp đồng API cố định giữa executor đồng bộ và reactive. Hãy kiểm tra **giá trị sau khi ghép**; nếu một bước thực sự phụ thuộc bước trước, diễn đạt phụ thuộc tuần tự trong flow thay vì dựa vào thứ tự ngẫu nhiên của hai supplier.

## 8. Reactive: kiểm thử bằng AuthenticationStepsOperator

Nếu ứng dụng dùng Spring WebFlux hoặc `ReactiveVaultTemplate`, `AuthenticationStepsOperator` diễn dịch flow dưới dạng `Mono<VaultToken>`. Khác biệt quan trọng của reactive test là **subscriber kích hoạt thực thi**. Reactor `StepVerifier` có thể kiểm tra:

- `onNext` mang token đúng khi flow hoàn thành.
- `onComplete` khi kết thúc thành công.
- `onError` khi supplier, transform hoặc HTTP login báo lỗi.

Ví dụ kiểm thử bằng đầu vào/token giả, không gửi HTTP:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationStepsOperator;
import org.springframework.vault.support.VaultToken;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.test.StepVerifier;

class ReactiveAuthenticationStepsTest {

    @Test
    void createsTokenWhenSubscribed() {
        AtomicInteger calls = new AtomicInteger();

        AuthenticationSteps steps = AuthenticationSteps
                .fromSupplier(() -> {
                    calls.incrementAndGet();
                    return "jwt-demo";
                })
                .map(String::trim)
                .login(jwt -> VaultToken.of("fake-token-" + jwt));

        AuthenticationStepsOperator operator =
                new AuthenticationStepsOperator(
                        steps, WebClient.builder().build());

        var result = operator.getVaultToken();
        assertEquals(0, calls.get(),
                "Chưa subscribe nên chưa lấy input");

        StepVerifier.create(result)
                .assertNext(token ->
                        assertEquals("fake-token-jwt-demo", token.getToken()))
                .verifyComplete();

        assertEquals(1, calls.get());
    }
}
~~~

Test này cho thấy không nên gọi `block()` trong code reactive production chỉ để đợi Vault login. Với flow có HTTP, bạn có thể dùng `WebClient` cùng `ExchangeFunction` giả hoặc MockWebServer/WireMock để cấp JSON response. Một test lỗi cần đăng ký HTTP mock trả lỗi trước khi kiểm tra:

~~~java
// Chỉ đúng khi operator đã được cấu hình HTTP mock báo lỗi.
StepVerifier.create(operator.getVaultToken())
        .expectError()
        .verify();
~~~

Không dùng assertion `expectError()` cho flow thuần `login(Function)` vốn trả token thành công như ví dụ trước đó. Khi kiểm tra lỗi, ưu tiên assert **loại lỗi hoặc điều kiện công khai ổn định** thay vì raw exception message.

Trong runtime reactive, Spring Vault có thể chuyển supplier đồng bộ sang scheduler để tránh chặn event-loop. Do đó, test không nên hard-code tên thread, cũng không được dựa vào thứ tự callback không được contract của API bảo đảm.

## 9. Ma trận kiểm thử dữ liệu đầu vào và phản hồi

Một bộ test đầy đủ cần bao phủ cả thành công và lỗi:

| Case | Đầu vào/phản hồi giả | Assertion |
|---|---|---|
| Đăng nhập thành công | RoleID, SecretID giả; HTTP 200 có `auth.client_token` | Đúng method/path/body, tạo token |
| Nhận TTL và renewable | HTTP 200 có `lease_duration=600`, `renewable=true` | `LoginToken` có TTL và trạng thái renew đúng |
| RoleID/SecretID thay đổi | Supplier đọc input B ở lần chạy kế tiếp | Body lần sau chứa input mới |
| Thiếu credential | Supplier trả rỗng hoặc null theo test | Validation từ chối trước khi tạo token |
| JSON body sai key | Mapping nhầm `roleId` thay vì `role_id` | HTTP mock phát hiện request không đúng contract |
| Vault từ chối login | HTTP 403 và JSON `errors` | Không trả token; caller nhận lỗi |
| Vault tạm lỗi | HTTP 500/503 | Flow báo lỗi; ứng dụng quyết định retry có giới hạn |
| Network timeout | HTTP client fake mô phỏng timeout | Flow có lỗi, không chờ vô hạn |
| HTTP 200 thiếu `auth.client_token` | JSON có `auth` rỗng/thiếu field | Không chấp nhận token rỗng |
| JSON sai cú pháp | Body không parse được | Chuyển đổi phản hồi lỗi; không trả token |
| External identity HTTP lỗi | HTTP 404/500 ở bước `fromHttpRequest` | Không gửi request login sau đó |
| Hai nguồn credential | `zipWith` ghép hai supplier | Kết quả giữ đúng cặp RoleID/SecretID |
| Login thành công nhưng đọc KV 403 | Token có thật, ACL thiếu `read` | Phân loại là lỗi authorization của KV |
| Reactive thành công | Mock `Mono` tạo token | `onNext` rồi `onComplete` |
| Reactive thất bại | HTTP response hoặc mapping báo lỗi | `onError` và không `onNext` token |

**Không nên buộc mọi case thất bại vào cùng một exception class:** lỗi JSON parsing, lỗi credential validation và HTTP `403` được xử lý ở các tầng khác nhau. Mục tiêu chung là không cấp/không chấp nhận token sai và báo lỗi tới caller để quyết định phục hồi.

## 10. Đặt test đúng vị trí so với VaultTemplate và SessionManager

`AuthenticationStepsExecutor` thực hiện `ClientAuthentication`. Khi Spring Vault cần Vault token, một `SessionManager` như `LifecycleAwareSessionManager` có thể gọi login, cache token, renew trước hạn và đăng nhập lại khi cần. `VaultTemplate` nhận token qua session manager để truy cập KV, Transit, PKI.

~~~mermaid
sequenceDiagram
    participant T as Unit/HTTP mock test
    participant S as AuthenticationStepsExecutor
    participant H as HTTP mock
    participant M as SessionManager
    participant V as VaultTemplate

    T->>S: login()
    S->>H: POST auth/approle/login
    H-->>S: JSON auth.client_token giả
    S-->>T: VaultToken
    Note over T,S: Kiểm thử này dừng tại ranh giới xác thực
    M->>S: login() khi session cần token
    S-->>M: VaultToken mới
    V->>M: getSessionToken()
    M-->>V: Token dùng cho request
~~~

Bài test `executor.login()` chỉ chứng minh **login flow**. Nó **không tự chứng minh**:

- `LifecycleAwareSessionManager` gia hạn hoặc revoke token đúng lịch và đúng TTL.
- Kubernetes projected JWT xoay vòng theo vòng đời Pod, AppRole SecretID được cấp lại an toàn, hoặc mTLS certificate đã được reload vào JVM.
- Vault policy cho phép đọc secret tại KV v2 path `data/` hoặc thao tác Transit/PKI.
- Dynamic secret lease được gia hạn hay dữ liệu KV cached trong ứng dụng được refresh.

Các hành vi này cần bài test session lifecycle, integration test với Vault thật hoặc kiểm thử hệ thống tương ứng. Tại bước đầu tiên, HTTP mock giúp tìm lỗi format/URL một cách nhanh và ổn định trước khi kết nối Vault.

## 11. Các sai lầm thường gặp

### 11.1. Mock chính executor rồi kết luận AuthenticationSteps chạy đúng

Ví dụ `when(executor.login()).thenReturn(VaultToken.of("fake-token"))` chỉ kiểm tra code của **caller**. Không có bước `fromSupplier`/`map`/HTTP terminal nào chạy thật. Với mục tiêu bài học này, hãy dùng executor thật và mock **nguồn đầu vào hoặc HTTP response**.

### 11.2. Mock VaultTemplate để test login

Mock `VaultTemplate.read(...)` trả một KV response giả sẽ không kích hoạt `AuthenticationSteps`. Đây là test business logic hoặc client của secrets engine, không phải test authentication flow.

### 11.3. Dùng credential thật trong fixture

JWT, SecretID, client certificate private key hay Vault token thật không được commit vào repo hoặc in ra log test. Với HTTP mock, chỉ cần literal giả; với integration test, dùng workload/role/Vault lab cô lập và cấp credential ngắn hạn theo chính sách CI.

### 11.4. Hiểu sai cơ chế thực thi trễ

Định nghĩa `AuthenticationSteps.fromSupplier(...)` không đồng nghĩa supplier chạy ngay. Mặt khác, nếu tự đọc file JWT một lần rồi nhúng thành `fromValue(...)`, lần đăng nhập sau **không đọc JWT hiện hành**. Khi cần credential thay đổi, dùng supplier đọc lại đúng nguồn ở thời điểm thực thi.

### 11.5. Chỉ kiểm tra HTTP 200

HTTP 200 vẫn có thể mang body thiếu `auth.client_token`, thiếu thông tin cần thiết hoặc JSON không hợp lệ. Test phải kiểm tra kết quả token và metadata có ý nghĩa, không chỉ status code. JSON key `client_token` trong response nằm ở object **`auth`**, không phải field `data.token`.

### 11.6. Bắt lỗi rồi retry vô hạn trong map hoặc callback

Credential sai hoặc Vault policy/role không đúng thường không được chữa bằng retry. Để flow phát lỗi; đặt backoff, jitter, giới hạn lần thử và deadline ở nơi quản lý phiên/request phù hợp. Không tự gọi login song song trong callback và làm lệch trạng thái session.

### 11.7. Dùng những assertion phụ thuộc implementation

Không buộc test vào thứ tự gọi hai supplier độc lập trong `zipWith` hay tên thread của reactive pipeline. Với HTTP mock, kiểm tra contract được công bố: HTTP method, path, body, response và kết quả. Thông điệp exception chi tiết hoặc số request thêm do client internal có thể thay đổi giữa các phiên bản; nếu có khác biệt, xác định rõ yêu cầu thực sự trước khi sửa test.

## 12. Bài tập thực hành

**Bài tập A — Input rotation:** tạo `AtomicReference` giữ credential giả, dựng flow với `fromSupplier`/`map`/`login(Function)`. Gọi `executor.login()` hai lần, thay dữ liệu giữa hai lần và xác nhận token giả phản ánh input mới.

**Bài tập B — AppRole HTTP contract:** dựng flow gửi `role_id`/`secret_id`; dùng `MockRestServiceServer` xác nhận POST `/v1/auth/approle/login`, trả JSON token, kiểm tra `LoginToken` TTL và khả năng renew.

**Bài tập C — Hai kết quả liên tiếp:** mock response thành công cho lần login đầu và `403` cho lần thứ hai. Kiểm tra lần đầu có token, lần sau có exception, mỗi lần có request đúng. Không tái sử dụng token giả của lần một để che lần login hai thất bại.

**Bài tập D — External identity:** thêm `fromHttpRequest`, trả dữ liệu identity giả; xác nhận phần chuyển đổi chuỗi và body login. Thử trả HTTP `500` tại bước identity và khẳng định Vault login không được gọi.

**Bài tập E — Reactive:** dùng `AuthenticationStepsOperator` với dữ liệu giả, `StepVerifier` xác nhận `onNext/onComplete`; thay nguồn giả bằng response báo lỗi rồi xác nhận `onError`.

**Bài tập F — Tích hợp trên Vault lab:** tạo AppRole chỉ có quyền `read` tại `kv-app/data/payments/config`; login qua flow thật, dùng `VaultTemplate` đọc đúng key. Thử path không được cấp quyền để kiểm tra riêng `403` của KV.

### Checklist nghiệm thu

- [ ] Tất cả token, RoleID, SecretID và JWT trong unit/HTTP mock đều là dữ liệu giả.
- [ ] Unit test bao phủ mapping, validation, thực thi trễ và thay đổi đầu vào.
- [ ] HTTP contract test kiểm tra đúng HTTP method, path, body, số request và cấu trúc phản hồi.
- [ ] Có test login thành công, lỗi `403`, lỗi `5xx`, timeout và JSON thiếu/sai.
- [ ] Test TTL/renewable khi phản hồi tạo `LoginToken` có metadata tương ứng.
- [ ] Reactive test dùng `StepVerifier`, không dùng `block()` trong logic production.
- [ ] Kiểm thử login flow tách biệt với kiểm thử Vault ACL và token/secret lease lifecycle.
- [ ] Không ghi raw credential/token hoặc body login thật vào log, screenshot hay artifact CI.
- [ ] Integration test chỉ sử dụng Vault test cô lập và dọn credential theo quy trình.

## 13. Tổng kết

Trong **SPRING_VAULT**, kiểm thử `AuthenticationSteps` bằng **đầu vào và phản hồi giả** giúp xác minh đường đi **credential → transform → HTTP login → VaultToken** trước khi hệ thống phụ thuộc vào Vault thật. Dùng `fromSupplier`/`map`/`login(Function)` để kiểm tra pipeline thuần, `MockRestServiceServer` để kiểm tra HTTP contract của executor, và `StepVerifier` để kiểm tra tín hiệu của operator reactive.

Sau khi test flow đạt yêu cầu, kiểm thử tích hợp sẽ xác nhận Vault role và policy thực tế, token TTL, cách `VaultTemplate` truy cập KV/Transit/PKI và các tình huống vận hành. Việc giữ đúng ranh giới test làm lỗi dễ xác định, giảm chi phí chạy test và giúp phát hiện sớm các nguy cơ như cache credential cũ hoặc parse sai phản hồi.

## Tài liệu tham khảo

- Spring Vault Reference — [Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html), mục Authentication Steps.
- Spring Vault API — [`AuthenticationSteps`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationSteps.html).
- Spring Vault API — [`AuthenticationSteps.Node`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationSteps.Node.html).
- Spring Vault API — [`AuthenticationSteps.HttpRequestBuilder`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationSteps.HttpRequestBuilder.html).
- Spring Vault API — [`AuthenticationStepsExecutor`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationStepsExecutor.html).
- Spring Vault API — [`AuthenticationStepsOperator`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationStepsOperator.html).
- Spring Framework Reference — [MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html).
- Reactor Reference — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- HashiCorp Vault API — [AppRole login](https://developer.hashicorp.com/vault/api-docs/auth/approle#login-with-approle).
