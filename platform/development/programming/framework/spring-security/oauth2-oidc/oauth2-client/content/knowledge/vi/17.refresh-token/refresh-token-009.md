# 17.9. Nhiều request đồng thời refresh cùng một authorized client

## 1. Bối cảnh: Một token hết hạn, nhiều request đến cùng lúc

Trong **Spring Security OAuth 2.0/OIDC Client**, một `OAuth2AuthorizedClient` được tạo sau khi client nhận access token từ Authorization Server (AS). Nếu AS cấp thêm **refresh token**, OAuth2 Client có thể dùng refresh token để xin access token mới khi access token cũ hết hạn hoặc sắp hết hạn.

Ở hệ thống ít tải, quy trình trông rất đơn giản:

```text
Request A
    -> Tìm OAuth2AuthorizedClient đã lưu
    -> Access token sắp hết hạn
    -> POST /token với grant_type=refresh_token
    -> Nhận access token mới và refresh token mới nếu có
    -> Lưu OAuth2AuthorizedClient mới
    -> Gọi API
```

Nhưng trong một ứng dụng thực tế, **nhiều HTTP requests có thể cùng cần một authorized client tại một thời điểm**:

- Trình duyệt mở một trang dashboard và đồng thời gọi 6 APIs.
- Nhiều requests AJAX của cùng một tài khoản đến nhiều threads trong Spring MVC.
- Một job chạy nền và một request web cùng truy cập tài khoản liên kết.
- Một ứng dụng triển khai 4 pods, cùng đọc authorized client từ JDBC.
- WebFlux phát nhiều tác vụ bất đồng bộ cần cùng access token.
- Một mobile/web frontend gửi request lại do timeout ngay lúc access token gần hết hạn.

Nếu tất cả requests đều nhìn thấy token cũ trước khi bất kỳ request nào kịp lưu token mới, chúng có thể **đồng thời gửi nhiều refresh requests dùng cùng một refresh token**.

### Tình huống ví dụ

Giả sử:

```text
Client registration ID: partner-api
Principal name:         alice-stable-id
Access token:           AT1, expiresAt = 10:00
Refresh token:          RT1
```

Lúc **09:59:10**, nhiều requests của Alice cùng cần gọi Partner API. Giả sử refresh provider dùng `clockSkew = 60 giây`, thì AT1 đã bị xem là cần refresh dù về mặt thời gian vẫn còn gần một phút.

```text
Request A -> thấy AT1 gần hết hạn -> refresh bằng RT1
Request B -> thấy AT1 gần hết hạn -> refresh bằng RT1
Request C -> thấy AT1 gần hết hạn -> refresh bằng RT1
```

Vấn đề trở nên nghiêm trọng khi AS dùng **refresh token rotation**: mỗi lần refresh thành công, AS có thể cấp một refresh token mới và vô hiệu hóa refresh token cũ.

**Mục tiêu bài học:** hiểu race condition này, biết Spring Security quản lý refresh ở đâu, rồi thiết kế cách **chỉ một tác vụ refresh cho cùng authorized client tại một thời điểm** trong những môi trường cần điều đó.

### Sau bài này, bạn sẽ nắm được

1. Cơ chế refresh của `OAuth2AuthorizedClientManager`, `RefreshTokenOAuth2AuthorizedClientProvider` và nơi lưu `OAuth2AuthorizedClient`.
2. Vì sao `clockSkew` khiến nhiều requests bắt đầu refresh gần như cùng lúc.
3. Refresh token rotation và nguy cơ `invalid_grant`, reuse detection, revocation.
4. Race condition khi lưu token mới hoặc xóa authorized client sau lỗi.
5. Giải pháp **single-flight/per-key lock** trong một JVM.
6. Giải pháp shared storage, distributed coordination, optimistic concurrency và fencing cho nhiều instances.
7. Tại sao **đọc lại authorized client sau khi lấy lock** là bước quan trọng.
8. Cách dùng manager đúng cho Servlet, service/background và WebFlux.
9. Giới hạn của retry, cách xử lý lỗi và tránh lộ refresh token.
10. Cách kiểm chứng concurrency bằng bài test và quan sát production.

Mọi tên domain, client, user, token và timestamp trong bài đều là minh họa, không đại diện một provider thực tế.

---

## 2. Phân biệt access token và refresh token

Hai token có nhiệm vụ khác nhau:

| Thuộc tính | Access token | Refresh token |
|---|---|---|
| Mục đích | Truy cập API/Resource Server. | Xin access token mới tại Token Endpoint. |
| Bên nhận | Resource Server phù hợp với audience/scope. | Authorization Server/Token Endpoint. |
| Thời hạn | Thường ngắn hơn. | Có thể dài hơn hoặc theo chính sách riêng. |
| Có được gửi cho browser? | Phụ thuộc loại client và kiến trúc; hạn chế tối đa trong backend. | Rất nhạy cảm; backend phải bảo vệ nghiêm ngặt. |
| Khi bị lộ | Có thể bị dùng để truy cập API theo quyền đã cấp. | Có thể cho phép cấp token mới cho tới khi bị thu hồi/hết hạn. |
| Rotation | Không phải tính chất bắt buộc. | Có thể được AS thay bằng refresh token mới sau mỗi lần dùng. |

Ví dụ request để làm mới token:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=refresh_token&refresh_token=RT1
```

Response minh họa khi AS sử dụng rotation:

```json
{
  "access_token": "AT2",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "RT2",
  "scope": "api.read"
}
```

Sau phản hồi này, backend cần lưu **AT2 cùng RT2** theo chính sách của AS. Không chỉ cập nhật access token rồi tiếp tục giữ RT1.

**Không phải mọi refresh response đều chứa refresh token mới.** Có AS giữ nguyên token cũ hoặc không rotate, còn có provider yêu cầu rotation nghiêm ngặt. Spring Security token response client và provider giúp xây kết quả theo phản hồi hợp lệ, nhưng chính sách rotation cuối cùng thuộc Authorization Server.

## 3. Refresh token rotation biến race thành rủi ro bảo mật

Một AS hỗ trợ rotation thường xử lý như sau:

```text
Trước refresh:
    Refresh token hợp lệ: RT1

Lần refresh thành công:
    Client gửi RT1
    AS vô hiệu hóa RT1
    AS cấp RT2
    Client lưu RT2

Lần dùng lại RT1:
    AS thấy refresh token đã từng được sử dụng
    AS trả lỗi hoặc kích hoạt reuse detection tùy chính sách
```

Mục đích của rotation không phải làm khó client. Nó giúp **phát hiện việc dùng lại refresh token**, có thể là dấu hiệu token đã bị đánh cắp.

RFC 9700 (*OAuth 2.0 Security Best Current Practice*) khuyến nghị/quy định cơ chế chống replay phù hợp, đặc biệt với public clients, trong đó có refresh token rotation hoặc sender-constrained refresh tokens.

### 3.1. Race giữa hai requests

```mermaid
sequenceDiagram
    autonumber
    participant A as Request A
    participant B as Request B
    participant Store as Authorized Client Store
    participant AS as Authorization Server

    A->>Store: load(partner-api, alice)
    Store-->>A: AT1, RT1
    B->>Store: load(partner-api, alice)
    Store-->>B: AT1, RT1

    A->>AS: POST /token refresh_token=RT1
    AS-->>A: AT2, RT2
    Note over AS: RT1 đã bị vô hiệu hóa

    B->>AS: POST /token refresh_token=RT1
    AS-->>B: invalid_grant hoặc reuse detection

    A->>Store: save(AT2, RT2)
    B->>Store: xử lý thất bại, có thể remove()
    Note over Store: Có nguy cơ xóa hoặc làm mất AT2/RT2
```

Hai requests đều có thể **đúng** khi chúng bắt đầu: chúng cùng thấy AT1 cần refresh và cùng đọc RT1. Nhưng một trong hai có thể bị từ chối sau khi request còn lại đã tiêu thụ RT1.

### 3.2. Những hậu quả có thể xảy ra

- Request B nhận `invalid_grant` dù request A đã nhận token mới.
- Một request sau đó không tìm được authorized client vì failure handler đã xóa entry.
- Các requests tiếp theo bị yêu cầu **authorization mới**, ảnh hưởng trải nghiệm đăng nhập.
- Nếu AS có reuse detection nghiêm ngặt, **cả refresh token mới RT2 cũng có thể bị revoke** do AS nghi ngờ token family bị lộ.
- Token mới bị ghi đè bởi bản cũ do cập nhật store không kiểm soát version.
- Nhiều retries tiếp tục dùng RT1 khiến tình hình tệ hơn.
- Người dùng bị logout hoặc mất kết nối tài khoản bên ngoài dù nguyên nhân chỉ là concurrency của chính ứng dụng.

Không nên mặc định rằng **request A thành công thì RT2 chắc chắn vẫn còn hợp lệ** nếu AS đã phát hiện RT1 bị dùng lại sau đó. Hành vi revoke phụ thuộc chính sách replay detection của AS.

## 4. Spring Security tham gia refresh ở những lớp nào?

Các thành phần chủ chốt trong ứng dụng Servlet:

| Thành phần | Nhiệm vụ |
|---|---|
| `ClientRegistrationRepository` | Tìm cấu hình OAuth2 client. |
| `OAuth2AuthorizedClient` | Chứa registration, principal, access token và refresh token nếu có. |
| `OAuth2AuthorizedClientRepository` | Đọc/lưu authorized client trong ngữ cảnh Servlet HTTP request. |
| `OAuth2AuthorizedClientService` | Đọc/lưu theo registration ID và principal name, không cần Servlet request. |
| `OAuth2AuthorizedClientManager` | Điều phối việc authorize/re-authorize và xử lý lưu/xóa kết quả. |
| `RefreshTokenOAuth2AuthorizedClientProvider` | Xác định có thể/cần refresh hay không và thực hiện grant. |
| `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` | Gửi refresh request tới Token Endpoint. |
| `OAuth2AuthorizationSuccessHandler` | Xử lý authorization thành công, thường lưu token mới. |
| `OAuth2AuthorizationFailureHandler` | Xử lý thất bại, có thể xóa authorized client theo mã lỗi. |

Sơ đồ:

```mermaid
flowchart TD
    A["N request cùng cần token"] --> M["OAuth2AuthorizedClientManager"]
    M --> S["AuthorizedClientRepository hoặc Service"]
    S --> E["Existing OAuth2AuthorizedClient: AT1 + RT1"]
    M --> P["RefreshTokenOAuth2AuthorizedClientProvider"]
    P --> Q{"Access token cần refresh?"}
    Q -->|Không| R["Giữ authorized client hiện tại"]
    Q -->|Có và có RT| T["Token Endpoint: grant_type=refresh_token"]
    T --> U["AT2 + RT2 (tùy AS)"]
    U --> V["SuccessHandler lưu authorized client mới"]
    T --> X["OAuth2 error"]
    X --> Y["FailureHandler / policy"]
```

**Quan trọng:** manager và service/repository giúp tổ chức lưu trữ, nhưng **không nên mặc định toàn bộ chuỗi đọc–kiểm tra–gửi HTTP–ghi token được khóa atomic giữa mọi threads hoặc mọi instances**.

### 4.1. RefreshTokenOAuth2AuthorizedClientProvider quyết định khi nào refresh

Class:

```java
org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider
```

Một provider này thường trả `null` khi:

- Chưa có authorized client.
- Authorized client không có refresh token.
- Access token chưa tới ngưỡng cần refresh.

Nó thực hiện refresh grant khi đã có authorized client với refresh token và access token được xem là hết hạn hoặc gần hết hạn theo `clockSkew`.

Do đó, **cùng một authorized client cũ có thể khiến nhiều provider instances cùng quyết định refresh** nếu cùng được gọi ở thời điểm đó.

### 4.2. Clock skew làm cửa sổ refresh mở sớm

Theo API của Spring Security, refresh provider có `setClockSkew(Duration)`; giá trị mặc định ở nhiều phiên bản hiện đại là **60 giây**. Token có thể bị coi là cần refresh khi đến gần `expiresAt`.

Ví dụ:

```text
Access token expiresAt: 14:00:00
Clock skew:             60 giây

Từ khoảng 13:59:00:
    Các requests mới có thể kích hoạt refresh.
```

Điều này giúp tránh gửi access token sát hạn tới API, nhưng cũng có thể làm **nhiều requests cùng phát hiện điều kiện refresh**. `clockSkew` không phải lock và cũng không phải cơ chế single-flight.

Skew quá lớn với token lifetime ngắn có thể làm tăng tần suất refresh, gây nhiều requests đến Token Endpoint. Cần chọn skew hợp lý, nhưng **giảm skew không giải quyết tận gốc race condition**.

### 4.3. Provider trả null không phải lỗi

Khi token còn hạn, provider thường trả `null`; manager có thể giữ và trả authorized client hiện tại. Khi refresh thành công, provider trả authorized client mới; manager thường lưu kết quả. Khi token request lỗi, exception/authorization failure được xử lý theo manager.

Ứng dụng nên gọi **`OAuth2AuthorizedClientManager.authorize(...)`**, không tự gọi `RefreshTokenOAuth2AuthorizedClientProvider.authorize(...)` rồi tự lưu token trong nhiều nơi khác nhau, trừ khi triển khai một flow rất có chủ đích.

## 5. Default failure handler và nguy cơ xóa nhầm kết quả mới

Một chi tiết dễ bỏ sót trong Spring Security:

- `DefaultOAuth2AuthorizedClientManager` (Servlet request context) mặc định có cơ chế xóa authorized client khi authorization thất bại với **`invalid_grant`**.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` (service/background context) cũng mặc định có thể **remove stored authorized client** khi nhận lỗi `invalid_grant`.

Hành vi này hợp lý trong trường hợp chỉ có một request: refresh token không hợp lệ thì entry cũ không còn dùng được.

Nhưng với concurrency:

```text
A đọc RT1
B đọc RT1

A refresh thành công -> save(AT2, RT2)
B refresh bằng RT1 -> invalid_grant
B failure handler -> remove(registrationId, principalName)
```

Nếu thao tác `remove` không biết version/token mà A vừa lưu, nó có thể **xóa entry mới của A**.

### 5.1. Vì sao unconditional remove nguy hiểm?

Contract lưu thông thường của service:

```java
removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
```

API này chủ yếu chỉ nhận **key**, không phải version của entry mà request thất bại đã đọc. Nếu một request dùng stale token mà gọi remove theo key, nó có thể xóa một entry mới vừa được request khác lưu.

Tình huống có thể đảo thứ tự:

```text
A refresh thành công nhưng chưa save.
B refresh thất bại -> remove(AT1/RT1).
A save(AT2/RT2).
```

Kết quả cuối khác hoàn toàn với thứ tự A-save rồi B-remove. Đây là **race giữa success handling và failure handling**.

### 5.2. Có nên tắt failure handler mặc định?

Không nên tắt vô điều kiện. Khi refresh token **thực sự không hợp lệ**, giữ một entry hỏng có thể khiến mọi request sau tiếp tục refresh thất bại.

Giải pháp có thể gồm:

1. **Ngăn nhiều refresh đồng thời ngay từ đầu**, theo khóa authorized client.
2. Sau khi một request lỗi, **đọc lại entry hiện tại** để xem token/version đã thay đổi chưa.
3. Dùng **conditional remove** nếu lỗi chỉ tương ứng với version cũ.
4. Nếu nhận `invalid_grant` và entry vẫn là version lỗi, xóa/đánh dấu invalid theo chính sách để user re-authorize.
5. Ghi nhận sự kiện bất thường để điều tra replay detection, không mặc định lỗi luôn là race vô hại.

Tùy kiến trúc, cần custom `OAuth2AuthorizationFailureHandler` hoặc storage service hỗ trợ compare-and-delete. Chỉ thay handler khi đã hiểu rõ contract và thứ tự lưu/xóa của manager.

## 6. Ba môi trường concurrency khác nhau

Đừng gộp mọi hiện tượng “nhiều requests đồng thời” thành một bài toán giống nhau.

| Môi trường | Ví dụ | Cơ chế đồng bộ cần xem |
|---|---|---|
| Một process, nhiều threads | Spring MVC Tomcat xử lý 10 requests của Alice. | Per-key local lock hoặc single-flight trong JVM. |
| Nhiều processes/pods | 3 pods cùng dùng JDBC authorized client service. | Distributed coordination + shared store + versioning. |
| Reactive async trong một process | WebFlux nhiều subscribers cùng yêu cầu token. | Reactive single-flight/cached in-flight publisher, không block event loop. |
| Browser sessions khác nhau nhưng cùng principal | Alice login trên laptop và điện thoại. | Xem service/repository có dùng chung key `registrationId + principalName` không. |
| Web request và background scheduler | Request web và job đều dùng token của Alice. | Cần phối hợp giữa các managers cùng đọc/ghi một store. |

Một `synchronized` hoặc `ReentrantLock` trong JVM **không đồng bộ hóa các pods khác nhau**. Một Redis lock hay DB row lock được thiết kế đúng có thể giúp nhiều nodes phối hợp, nhưng cũng có failure modes riêng.

## 7. Xác định khóa đồng bộ đúng

`OAuth2AuthorizedClientService` thường truy xuất theo:

```text
(clientRegistrationId, principalName)
```

Với multi-tenant hoặc nhiều issuer, cần thêm namespace tin cậy:

```text
(tenantId, issuer/provider, clientRegistrationId, principalName)
```

Tùy thiết kế, tenant có thể đã nằm trong registration ID hoặc stable principal name. Quan trọng là **hai security principals không được dùng chung một token chỉ vì trùng tên hiển thị**.

Ví dụ:

| Registration | Principal | Khóa lock/storage |
|---|---|---|
| `partner-api` | `alice-uid` | `partner-api + alice-uid` |
| `partner-api` | `bob-uid` | `partner-api + bob-uid` |
| `other-api` | `alice-uid` | `other-api + alice-uid` |
| `tenantA-partner` | `alice-uid` | `tenantA-partner + alice-uid` |

Không dùng một **global lock duy nhất** cho mọi user nếu có nhiều authorized clients. Nó có thể làm 1.000 users cùng phải đợi một token refresh không liên quan.

Ngược lại, nếu cùng một authorized client bị biểu diễn thành hai keys khác nhau, việc khóa theo key có thể không giúp gì. Cần đảm bảo mọi đường sử dụng token dùng **cùng registration ID và principal identity**.

### 7.1. OIDC principal name có đủ ổn định không?

Với OIDC, `(issuer, subject)` thường là cơ sở định danh ngoài đáng tin cậy. Email và tên hiển thị có thể thay đổi hoặc trùng.

Nếu application ánh xạ OIDC user về local account ID, cần bảo đảm mapping đó ổn định và tách biệt tenants. Không dùng `request.getSession().getId()` như khóa refresh nếu cùng một authorization được chia sẻ giữa nhiều sessions; cũng không gộp mọi sessions tùy tiện nếu token thuộc authorization độc lập.

### 7.2. Lock granularity và phạm vi token

Một registration có thể có nhiều tokens khác scope/audience/resource nếu ứng dụng dùng extensions. Khi đó `(registrationId, principalName)` có thể **không đủ** nếu storage tự thiết kế thêm biến thể authorization.

Hãy chọn lock key khớp **chính xác storage key và phạm vi token**. Nếu authorization cấp bởi các issuers/tenants khác nhau, phải namespace rõ ràng.

---

## 8. Giải pháp 1: single-flight/per-key lock trong một JVM

Với ứng dụng chạy một instance, cách dễ hiểu là **khóa theo authorized client key** sao cho tại một thời điểm chỉ có một thread được gọi manager để quyết định refresh cho key đó.

Nguyên tắc:

```text
Thread A, key K:
    acquire lock(K)
    manager.authorize(K) -> có thể refresh bằng RT1
    manager save(AT2, RT2)
    release lock(K)

Thread B, key K:
    đợi lock(K)
    acquire lock(K)
    manager.authorize(K) -> manager load lại AT2/RT2
    AT2 còn hạn -> không refresh
    release lock(K)
```

**Điểm mấu chốt:** Thread B phải để manager **tra lại authorized client bên trong lock**. Nếu B giữ một `OAuth2AuthorizedClient` đã load từ trước lock và truyền thẳng cho manager, nó có thể tiếp tục refresh bằng RT1 đã stale.

### 8.1. Java ví dụ: bọc manager bằng striped locks

Đoạn mã dưới đây là một **wrapper cho các lệnh authorize chạy qua cùng một service manager**. Nó chỉ có hiệu lực giữa các callers sử dụng **cùng instance wrapper** trong **cùng JVM**.

```java
package example.oauth2;

import java.util.Objects;
import java.util.concurrent.locks.ReentrantLock;

import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public final class StripedLockingAuthorizedClientManager
        implements OAuth2AuthorizedClientManager {

    private final OAuth2AuthorizedClientManager delegate;
    private final ReentrantLock[] locks;

    public StripedLockingAuthorizedClientManager(
            OAuth2AuthorizedClientManager delegate,
            int stripeCount) {

        this.delegate = Objects.requireNonNull(delegate);

        if (stripeCount <= 0) {
            throw new IllegalArgumentException(
                "stripeCount must be positive"
            );
        }

        this.locks = new ReentrantLock[stripeCount];
        for (int i = 0; i < locks.length; i++) {
            locks[i] = new ReentrantLock();
        }
    }

    @Override
    public OAuth2AuthorizedClient authorize(
            OAuth2AuthorizeRequest request) {

        Objects.requireNonNull(request, "request");

        String registrationId = request.getClientRegistrationId();

        if (registrationId == null
                && request.getAuthorizedClient() != null) {
            registrationId = request
                .getAuthorizedClient()
                .getClientRegistration()
                .getRegistrationId();
        }

        if (registrationId == null) {
            throw new IllegalArgumentException(
                "Cannot determine client registration ID"
            );
        }

        String principalName = request.getPrincipal().getName();
        String key = registrationId + "\u0000" + principalName;

        int index = Math.floorMod(key.hashCode(), locks.length);
        ReentrantLock lock = locks[index];

        lock.lock();
        try {
            // Dùng manager/service để load lại state trong lock.
            return delegate.authorize(request);
        } finally {
            lock.unlock();
        }
    }
}
```

Vì một số keys khác nhau có thể cùng hash vào một stripe, chúng đôi khi phải đợi nhau dù không cùng authorized client. Điều đó **không làm lộ token**, nhưng có thể làm giảm mức song song. Chọn số stripes phù hợp tải; ví dụ 64 hoặc 128.

Ưu điểm so với `ConcurrentHashMap<Key, ReentrantLock>` không bao giờ xóa keys là số lock objects được giới hạn. Với hệ thống rất nhiều users/tenants, map locks không có cơ chế eviction có thể tích lũy bộ nhớ vô hạn.

### 8.2. Cấu hình manager dành cho service/background

```java
package example.oauth2;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class OAuth2AuthorizedClientConfiguration {

    @Bean("serializedAuthorizedClientManager")
    OAuth2AuthorizedClientManager serializedAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        AuthorizedClientServiceOAuth2AuthorizedClientManager base =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service
            );

        base.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .build()
        );

        return new StripedLockingAuthorizedClientManager(base, 128);
    }
}
```

Đoạn trên giả định authorized client **đã được cấp quyền qua một flow trước đó và có thể được tra từ service**. Nếu chưa có authorized client, provider chỉ gồm `.refreshToken()` sẽ không thể tự bắt đầu browser login.

Trong ứng dụng thực tế có cả Authorization Code và Refresh Token flows, phần web authentication vẫn phải được cấu hình bằng Spring Security OAuth2 Login/Client infrastructure phù hợp.

### 8.3. Cách gọi từ một service cần token

```java
package example.oauth2;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class PartnerAccessTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public PartnerAccessTokenService(
            @Qualifier("serializedAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String accessTokenFor(String stablePrincipalName) {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("partner-api")
                .principal(stablePrincipalName)
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "No authorized client; interactive authorization may be required"
            );
        }

        return authorizedClient.getAccessToken().getTokenValue();
    }
}
```

Đoạn mã giả định `stablePrincipalName` đến từ **ngữ cảnh đã xác thực và đã được phân quyền**, không phải query parameter do người dùng tùy ý truyền. Service này **không được cung cấp access token cho bất kỳ tài khoản nào chỉ cần biết username**.

### 8.4. Giới hạn của wrapper

Wrapper chỉ giải quyết một phạm vi nhất định:

- Hoạt động khi **mọi refresh calls cho cùng key đi qua cùng wrapper**.
- Chỉ đồng bộ trong **một JVM**.
- Nếu có manager khác/HTTP filter khác bypass wrapper, nó vẫn có thể refresh đồng thời.
- Nếu truyền một `OAuth2AuthorizeRequest` **chứa sẵn authorized client stale** bằng `withAuthorizedClient(...)`, khóa không bắt buộc manager re-load entry mới. Với chiến lược dựa vào service, nên dùng `withClientRegistrationId(...)` để manager load state trong lock.
- Lock ở đây cũng bao phủ cache hits. Với tải rất lớn, cần cân nhắc tối ưu single-flight chỉ trên nhánh refresh, nhưng phải giữ thao tác đọc lại và cập nhật token đúng semantics.
- Nếu process crash, lock và cache local biến mất. Không có tác dụng đối với những nodes khác.

**Đây không phải patch “universal concurrency safety” cho mọi Spring Security flow.** Nó là mẫu tổ chức đồng bộ trong một instance khi callers được kiểm soát và manager dùng cùng authorized client service.

## 9. Đồng bộ Servlet web flow: nơi nào cần bọc?

Trong một ứng dụng Servlet, web request có thể sử dụng:

```java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
```

Manager này nhận:

- `ClientRegistrationRepository`.
- `OAuth2AuthorizedClientRepository`.

Trong khi service/background dùng:

```java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
```

cùng `OAuth2AuthorizedClientService`.

### 9.1. Hai managers có thể thao tác cùng một token

Nếu web authorized client repository của authenticated principal ủy quyền sang `OAuth2AuthorizedClientService`, và một background manager cũng dùng **chính service đó**, có thể xảy ra:

```text
Web request:
    DefaultOAuth2AuthorizedClientManager
        -> AuthorizedClientRepository
            -> AuthorizedClientService

Background job:
    AuthorizedClientServiceOAuth2AuthorizedClientManager
        -> AuthorizedClientService
```

Cả hai có thể đọc cùng `(registrationId, principalName)` và refresh đồng thời.

Vì vậy phải nhìn tổng thể **mọi đường có khả năng refresh**: web filters, API clients, scheduled jobs, listeners và custom code. Một wrapper chỉ được một gateway sử dụng không ngăn được request từ gateway khác.

### 9.2. HTTP session và service storage

`AuthenticatedPrincipalOAuth2AuthorizedClientRepository` thường dùng authorized client service cho authenticated principal và HTTP session repository cho anonymous. Nếu ứng dụng cấu hình `HttpSessionOAuth2AuthorizedClientRepository` cho mọi principal, mỗi session có thể có token riêng.

Điểm khác nhau:

| Store | Khóa logic | Tác động concurrency |
|---|---|---|
| InMemory service | Registration + principal trong một process | Nhiều threads cùng đọc key có thể race. |
| JDBC service | Registration + principal trong DB | Nhiều nodes cùng đọc key có thể race. |
| HttpSession repository | Theo session và registration | Requests song song trong cùng session có thể race. |
| Shared session store | Session phân tán | Nhiều nodes có thể cùng đụng session state. |
| Custom store có tenant namespace | Theo custom key | Cần lock/CAS khớp key thật. |

Không tự cho rằng **HTTP session là thread-safe cho một chuỗi refresh HTTP dài**. Có thể tồn tại nhiều requests song song dùng cùng session.

## 10. Giải pháp 2: distributed lock cho nhiều instances

Khi ứng dụng chạy trên nhiều pods/VMs, local lock không đủ:

```text
Pod A: local lock A
Pod B: local lock B

Cả hai có thể cùng lấy lock local
và cùng refresh RT1.
```

Cần một cơ chế **đồng bộ phân tán** nếu cùng authorized client được nhiều nodes sử dụng.

Khái niệm:

```text
Distributed Key:
    oauth2:refresh:{tenant}:{registrationId}:{principalName}

Lock:
    chỉ một node giữ quyền refresh cùng key

Shared Store:
    lưu OAuth2AuthorizedClient đã được cấp mới
```

Các lựa chọn hạ tầng có thể là database locking, Redis-based coordination, distributed lock service hoặc cơ chế khác được tổ chức phê duyệt. Không có một loại lock phù hợp nhất với mọi môi trường.

### 10.1. Thuật toán đề xuất

```text
authorize(registrationId, principalName):
    1. Xác định key ổn định đúng security namespace.
    2. Load authorized client hiện tại.
    3. Nếu token còn đủ hạn -> dùng lại.
    4. Nếu cần refresh -> acquire distributed lock(key).
    5. Sau khi có lock, LOAD LẠI authorized client từ shared store.
    6. Nếu entry mới đã được node khác refresh:
           -> dùng entry mới, không gọi Token Endpoint.
    7. Nếu vẫn cần refresh:
           -> gọi manager/provider để refresh qua RT hiện hành.
           -> lưu AT/RT mới bằng cơ chế nhất quán.
    8. Release lock trong finally.
    9. Trả authorized client phù hợp.
```

Trong bước 7, phải bảo đảm manager **đọc authorized client mới nhất sau khi lấy lock**. Nếu code đưa vào manager một object cũ đã được lấy từ bước 2, cả hệ thống vẫn có thể dùng RT1 stale dù có lock.

### 10.2. Sequence diagram với double-check

```mermaid
sequenceDiagram
    autonumber
    participant A as Pod A
    participant B as Pod B
    participant L as Distributed Lock
    participant Store as Shared AuthorizedClient Store
    participant AS as Authorization Server

    A->>Store: load(K)
    Store-->>A: AT1/RT1 sắp hết hạn
    B->>Store: load(K)
    Store-->>B: AT1/RT1 sắp hết hạn

    A->>L: acquire(K)
    L-->>A: granted
    B->>L: acquire(K)
    Note over B,L: B chờ có giới hạn

    A->>Store: reload(K) sau lock
    Store-->>A: AT1/RT1
    A->>AS: refresh(RT1)
    AS-->>A: AT2/RT2
    A->>Store: save(AT2/RT2)
    A->>L: release(K)

    L-->>B: granted
    B->>Store: reload(K) sau lock
    Store-->>B: AT2/RT2 còn hạn
    Note over B: Không refresh RT1
    B->>L: release(K)
```

**Đọc lại sau lock** là bước tránh gửi refresh request trùng. Không chỉ dựa vào snapshot đã load trước khi chờ lock.

### 10.3. Không giữ database transaction dài quanh HTTP call một cách máy móc

Một số người chọn:

```text
BEGIN TRANSACTION
SELECT ... FOR UPDATE
POST /token
UPDATE tokens
COMMIT
```

Cách này có thể đảm bảo serialization nếu mọi callers dùng đúng transaction/row lock, nhưng cũng có nhược điểm:

- Giữ DB connection và lock trong suốt một HTTP request có thể mất nhiều giây.
- Dễ gây lock contention khi AS chậm.
- Có thể ảnh hưởng pool database và các transaction khác.
- Timeout của AS/DB phức tạp khi xảy ra lỗi.
- Rollback database không thể “hoàn tác” việc AS đã tiêu thụ refresh token.

Với hệ thống tải cao, cân nhắc **lease-based lock ngoài transaction dài**, optimistic versioning và chính sách phục hồi phù hợp. Chọn giải pháp dựa trên yêu cầu nhất quán và khả năng vận hành, không phải chỉ vì câu lệnh `FOR UPDATE` dễ viết.

## 11. Distributed lock có thể hết hạn giữa chừng

Một distributed lock thường có **lease/TTL** để tránh khóa treo vĩnh viễn khi process chết. Nhưng refresh request có thể kéo dài quá TTL:

```text
Pod A lấy lock K trong 5 giây.
Pod A gọi AS, mạng chậm 8 giây.

Sau 5 giây: lock K hết hạn.
Pod B lấy lock K và đọc token cũ.
Pod B cũng gọi AS với RT1.

Pod A nhận RT2 rồi ghi store.
Pod B nhận invalid_grant hoặc token mới khác.
```

Như vậy **có distributed lock chưa chắc đã tuyệt đối loại trừ refresh đồng thời**.

### 11.1. Lease và timeout cần có quan hệ hợp lý

Cần xem:

- Connect timeout tới Token Endpoint.
- TLS handshake timeout.
- Response/read timeout.
- Worst-case latency của AS.
- Retry policy (nếu có) và tổng duration.
- Lease TTL/renewal heartbeat.
- Thời gian chờ lock.
- Thời gian đọc/ghi store.
- Shutdown/crash giữa các bước.

Không chỉ đặt TTL tùy ý như 1 giây. Nếu token request có thể mất 10 giây, lease ngắn hơn nhiều sẽ tăng nguy cơ chồng lấn. Đồng thời cũng không đặt lease vô hạn mà không có cơ chế xử lý process chết.

### 11.2. Fencing token giúp bảo vệ việc ghi stale

Một số distributed coordination systems hỗ trợ **fencing token** tăng dần:

```text
Pod A acquire lock -> fencing = 41
Pod A chậm, lease hết hạn

Pod B acquire lock -> fencing = 42
Pod B ghi kết quả hợp lệ với fencing = 42

Pod A tỉnh lại, cố ghi với fencing = 41
Store từ chối bản ghi stale.
```

Fencing giúp tránh **ghi đè token mới bằng kết quả cũ** khi lease hết hạn. Tuy nhiên, fencing **không hoàn tác được việc RT1 đã bị gửi tới Authorization Server hai lần**. Vì vậy nó là lớp bảo vệ dữ liệu lưu trữ, không thay thế hoàn toàn việc hạn chế duplicate refresh requests.

## 12. Optimistic concurrency và compare-and-set (CAS)

Để tránh một request cũ xóa/ghi đè entry mới, có thể thiết kế custom authorized client store có **version**.

Ví dụ bản ghi:

```text
registration_id = partner-api
principal_name  = alice-uid
version         = 7
access_token    = AT1 (encrypted)
refresh_token   = RT1 (encrypted)
```

Sau khi refresh thành công, chỉ update nếu version còn là 7:

```sql
UPDATE oauth2_authorized_client_custom
SET
    access_token_ciphertext = :new_access_token,
    refresh_token_ciphertext = :new_refresh_token,
    version = version + 1,
    updated_at = :updated_at
WHERE
    client_registration_id = :registration_id
    AND principal_name = :principal_name
    AND version = :expected_version;
```

Nếu `rowCount = 1`, update thành công. Nếu `rowCount = 0`, có một thao tác khác đã thay đổi entry; caller không nên ghi đè vô điều kiện mà phải đọc lại state và giải quyết theo policy.

**SQL trên là schema custom minh họa.** Không phải schema/SQL mặc định được `JdbcOAuth2AuthorizedClientService` cung cấp. Nếu muốn CAS, cần implementation/mappers/storage riêng phù hợp.

### 12.1. Conditional delete khi gặp invalid_grant

Ý tưởng:

```sql
DELETE FROM oauth2_authorized_client_custom
WHERE
    client_registration_id = :registration_id
    AND principal_name = :principal_name
    AND version = :version_of_failed_refresh;
```

Nếu request B thất bại với version 7 nhưng request A đã lưu version 8, B **không được xóa** entry version 8.

Tuy nhiên, hãy nhớ: nếu AS đã thực hiện reuse detection và revoke cả token family, version 8 có thể đã không còn hợp lệ. Vì thế conditional delete chỉ bảo vệ khỏi một class race trong store, **không khẳng định token mới an toàn**.

### 12.2. Tại sao CAS một mình chưa đủ?

Giả sử A và B cùng đọc RT1/version 7, rồi **đều gửi** `POST /token` trước khi ghi DB:

```text
A: AS tiêu thụ RT1, trả RT2.
B: AS nhận lại RT1, báo reuse/invalid_grant.
```

CAS có thể ngăn B xóa hoặc ghi đè version mới nhưng không ngăn hai HTTP requests đã tới AS. Với rotation strict, token family có thể bị invalidate.

Do đó, mô hình vững chắc thường kết hợp:

```text
Serialize refresh attempt theo key
    +
Re-read state sau khi acquire
    +
Conditional update/delete hoặc fencing
    +
Recovery policy khi refresh outcome không chắc chắn
```

Không có một primitive độc lập nào bảo đảm mọi thuộc tính đó dưới mọi failure scenario.

## 13. Trường hợp response bị mất: kết quả refresh không rõ ràng

Một tình huống khó hơn `invalid_grant` rõ ràng là **mất phản hồi sau khi AS đã xử lý**:

```text
T0  Client gửi refresh(RT1)
T1  AS chấp nhận RT1
T2  AS vô hiệu hóa RT1 và tạo AT2/RT2
T3  Response bị mất giữa AS và client
T4  Client thấy read timeout
```

Ở T4, client **không biết** AS đã tiêu thụ RT1 hay chưa.

Nếu retry bằng RT1:

- AS có thể từ chối `invalid_grant`.
- AS có thể coi đó là reuse attempt.
- Với một số chính sách, token family có thể bị thu hồi.

### 13.1. Không retry refresh token mù quáng

Một retry interceptor tổng quát trên mọi HTTP POST có thể gây hậu quả nghiêm trọng. Nên:

- Phân biệt rõ connect failure trước khi gửi request với response timeout sau khi request có thể đã được xử lý.
- Không giả định exception ở client nghĩa request chưa được AS nhận.
- Không retry bằng refresh token cũ vô hạn.
- Dùng chính sách retry chỉ khi có cơ sở từ hợp đồng AS và khả năng idempotency tương ứng.
- Khi không thể khôi phục an toàn, yêu cầu user re-authorization hoặc phục hồi theo quy trình provider cung cấp.

Một token endpoint đôi khi có cơ chế idempotency/vendor-specific, nhưng **không được tự giả định có hỗ trợ** nếu tài liệu provider không nói vậy.

### 13.2. Local lock có giữ được sau timeout không?

Lock có thể đảm bảo **các threads trong cùng process không cùng gửi refresh request tại một thời điểm**, nhưng sau timeout, thread kế tiếp vẫn cần quyết định:

- Store còn RT1 cũ.
- Không có bằng chứng AS đã/ chưa tiêu thụ RT1.
- Nếu cứ retry bằng RT1, có thể gây reuse detection.

Vì vậy concurrency control phải phối hợp với **failure policy** chứ không chỉ khóa.

## 14. Cách sử dụng manager để đảm bảo đọc state mới

`OAuth2AuthorizedClientManager` có thể nhận `OAuth2AuthorizeRequest` theo nhiều cách. Với service manager, cách phổ biến:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("partner-api")
        .principal("alice-stable-id")
        .build();

OAuth2AuthorizedClient client = manager.authorize(request);
```

Khi manager dùng `OAuth2AuthorizedClientService`, nó có thể tìm authorized client theo registration/principal và quyết định refresh.

### 14.1. Tránh truyền `OAuth2AuthorizedClient` stale

Nếu caller đã đọc một object cũ trước lock:

```java
OAuth2AuthorizedClient old = service.loadAuthorizedClient(
    "partner-api",
    "alice-stable-id"
);
```

rồi chờ lock, sau đó gọi:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withAuthorizedClient(old)
        .principal("alice-stable-id")
        .build();
```

thì manager có thể sử dụng **object stale mà caller cung cấp** thay vì bắt buộc đọc bản mới của store. Bước lock đã không bảo vệ dữ liệu đầu vào.

Khi xây cơ chế single-flight, ưu tiên **chọn registration + principal và để manager load latest state trong critical section**, hoặc tự thực hiện explicit reload và bảo đảm manager dùng đúng latest object.

### 14.2. Manager instance và storage phải nhất quán

Nếu ứng dụng có nhiều managers:

```text
WebManager  -> AuthorizedClientRepository -> JDBC service
JobManager  -> InMemory service
```

thì hai managers có thể không thấy cùng state, dù đều dùng `registrationId=partner-api` và `principalName=alice-uid`.

Để dùng chung một authorization, cần thống nhất storage và security boundary. Không copy refresh token thủ công giữa nhiều stores như một workaround không kiểm soát.

## 15. DefaultOAuth2AuthorizedClientManager và service manager

### 15.1. Servlet web request

Trong HTTP Servlet context:

```java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
```

Manager này nhận:

```java
DefaultOAuth2AuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientRepository repository
)
```

Nó phù hợp khi app đang xử lý request/session và có `Authentication`.

### 15.2. Background/service context

Trong job hoặc service ngoài HTTP request:

```java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
```

Manager này nhận:

```java
AuthorizedClientServiceOAuth2AuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientService service
)
```

Nó phù hợp với các authorized clients được lưu theo principal mà không cần `HttpServletRequest`/`HttpServletResponse`.

### 15.3. Cùng một refresh token có thể bị sử dụng qua hai manager types

Ví dụ portal cho người dùng liên kết tài khoản API, rồi background job đồng bộ thay mặt họ:

```text
Portal web login:
    Manager Servlet + Repository
        -> lưu authorized client Alice

Background job:
    Service manager + AuthorizedClientService
        -> đọc authorized client Alice
        -> refresh nếu cần
```

Nếu cả hai cùng dùng underlying service, chúng có thể đụng **cùng RT1**. Đây là lý do cần coordination ở tầng storage/token lifecycle chứ không đơn thuần bọc một HTTP controller.

---

## 16. Spring Security cấu hình refresh provider như thế nào?

Ví dụ cấu hình trong một ứng dụng Servlet, với provider tổng hợp:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration
public class OAuth2ProviderConfiguration {

    @Bean
    OAuth2AuthorizedClientProvider authorizedClientProvider() {
        return OAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken(refresh -> refresh
                .clockSkew(Duration.ofSeconds(60))
            )
            .build();
    }
}
```

Trong flow authorization code, `authorizationCode()` tham gia khi cần authorization tương tác; `refreshToken()` xử lý khi authorized client đã có refresh token phù hợp và access token cần cấp lại.

**Provider builder không tự thêm distributed locking.** Nó định nghĩa **grant strategies**, không phải storage transaction isolation.

### 16.1. Token response client riêng cho refresh grant

Trong những phiên bản Spring Security hiện đại, refresh token response client Servlet có thể là:

```java
org.springframework.security.oauth2.client.endpoint.RestClientRefreshTokenTokenResponseClient
```

Và reactive counterpart:

```java
org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient
```

Tùy phiên bản, có thể có các lớp dựa trên `RestTemplate` cũ hơn.

Nên cấu hình timeout/TLS/proxy thích hợp cho refresh token HTTP request, nhưng **timeout không tự giải quyết việc nhiều requests cùng sử dụng RT1**.

### 16.2. Clock skew và refreshing quá sớm

Nếu token sống 2 phút mà skew là 60 giây, một nửa thời hạn token có thể nằm trong vùng cần refresh. Khi tải cao, nhiều requests có thể nhanh chóng tranh nhau refresh.

Điều chỉnh skew theo token lifetime và network latency có thể giảm refresh frequency, nhưng concurrency control vẫn là một vấn đề độc lập.

## 17. WebFlux/reactive: không dùng ReentrantLock trên event loop

Trên **Spring Security WebFlux**, các API tương ứng:

```text
ReactiveOAuth2AuthorizedClientManager
ReactiveOAuth2AuthorizedClientProvider
RefreshTokenReactiveOAuth2AuthorizedClientProvider
ReactiveOAuth2AuthorizedClientService
ServerOAuth2AuthorizedClientRepository
```

Khi dùng WebFlux, token refresh thường trả kết quả dạng:

```java
Mono<OAuth2AuthorizedClient>
```

Dùng `ReentrantLock.lock()` hoặc gọi `.block()` trực tiếp trong Reactor event loop có thể chặn các tác vụ I/O khác và giảm throughput.

### 17.1. Reactive single-flight là gì?

Thay vì chặn thread, có thể tổ chức:

```text
key K -> Mono đang thực hiện refresh cho K
```

Khi request A bắt đầu refresh:

```text
K -> inFlight Mono<OAuth2AuthorizedClient>
```

Request B tới cùng key trong khi A chưa xong:

```text
B đăng ký subscribe cùng inFlight Mono
    -> không gửi refresh HTTP request thứ hai
    -> cùng nhận kết quả hoặc lỗi của lần refresh đang chạy
```

Khi publisher hoàn tất hoặc lỗi, cần **loại entry in-flight** để lần sau có thể load state mới và refresh lại nếu cần.

### 17.2. Không cache vô hạn một Mono có token

Nếu giữ `Mono.cache()` mãi trong map cho key K, tất cả lần gọi sau có thể tiếp tục trả **authorized client cũ đã hết hạn**, dù refresh hoàn tất từ lâu.

Cần phân biệt:

- Cache **in-flight operation** trong thời gian nó đang chạy.
- Store **authorized client** có token và expiry để các lần gọi tương lai kiểm tra.

Khi sử dụng Reactor operators như `cache`, `doFinally`, `defer` và map concurrent, phải quản lý **subscription, cancellation, removal sau terminal signal và race khi thay map entry**. Viết một sample `Mono` quá ngắn mà thiếu lifecycle dễ tạo bug khó chẩn đoán.

### 17.3. Multi-instance reactive vẫn cần distributed coordination

Reactive single-flight trong một process chỉ gom các subscribers trong process đó. Hai pods WebFlux vẫn có thể refresh cùng RT1. Cần shared store, locking/coordination và CAS giống nguyên tắc ở phần nhiều instances.

## 18. Khi nào có thể reuse access token trong lúc refresh đang chạy?

Một access token có thể **vẫn còn hiệu lực theo `expiresAt`** trong cửa sổ `clockSkew` dù provider muốn xin token mới sớm.

Một số hệ thống có thể thiết kế chính sách:

```text
AT1 còn hạn đủ cho request:
    -> cho phép tạm dùng AT1
    -> một tác vụ refresh đang chạy
```

Nhưng đây là **một cơ chế stale-while-refresh tùy ứng dụng**, không phải hành vi mặc định cần giả định ở Spring Security.

Các rủi ro cần cân nhắc:

- Token có thể hết hạn trước khi Resource Server xử lý request.
- Resource Server có thể đã revoke token.
- Backend có thể có request kéo dài hơn remaining lifetime.
- Khi refresh token rotation/reuse detection xảy ra, AS có thể thu hồi nhiều tokens liên quan.
- Một lớp cache tự chế có thể bỏ qua các kiểm tra mới của manager.

Do đó, nếu dùng chiến lược này, phải quy định **ngưỡng remaining lifetime an toàn** và có policy rõ. Với API quan trọng, chờ một refresh single-flight hoàn tất có thể dễ đảm bảo hơn việc dùng token sát hạn.

## 19. Phục hồi sau `invalid_grant` trong môi trường concurrency

`invalid_grant` có thể có nhiều nguyên nhân:

- Refresh token đã hết hạn.
- Refresh token bị revoke.
- Client dùng lại refresh token đã rotate.
- Refresh token không phù hợp client authentication.
- Provider áp một chính sách khác theo contract.

**Không thể chỉ nhìn `invalid_grant` rồi kết luận chắc chắn là một race**.

### 19.1. Quy trình phân loại

Khi request B nhận `invalid_grant`:

1. Xác định registration/principal của authorization (không log token value).
2. Kiểm tra có một request refresh khác cho cùng key đang/đã thành công gần đó hay không.
3. Đọc lại authorized client từ store với quyền truy cập đúng.
4. So sánh version/refresh-token fingerprint được bảo vệ, nếu store hỗ trợ.
5. Nếu entry hiện tại mới hơn entry B dùng, không xóa entry mới chỉ vì B lỗi.
6. Nếu AS có reuse detection, xác định liệu token family có bị revoke hay không trước khi tiếp tục sử dụng.
7. Nếu không có state hợp lệ, yêu cầu re-authorization theo flow ứng dụng.
8. Ghi metrics và điều tra nguồn đồng thời, không retry RT cũ vô hạn.

### 19.2. Không vô hiệu hóa bảo mật của AS để tránh race

Một cách giải quyết sai là yêu cầu AS **không vô hiệu hóa refresh token cũ** chỉ vì client có nhiều requests. Rotation bảo vệ chống token replay và thường là một lựa chọn quan trọng về bảo mật.

Giải pháp phù hợp là **sửa concurrency ở client**, không làm yếu an ninh chỉ để che lỗi đồng thời.

### 19.3. Khi cần bắt đầu authorization flow mới

Nếu refresh token không còn hợp lệ và hệ thống không có phương án khôi phục được provider hỗ trợ, có thể phải:

```text
Người dùng Alice
    -> bắt đầu lại Authorization Code + PKCE
    -> nhận access token/refresh token mới
    -> lưu authorized client mới
```

Với background job không có browser, không được giả lập người dùng hay tự đổi sang `client_credentials` để lách giới hạn. Job cần biết authorization của user không còn khả dụng và có thể báo yêu cầu người dùng kết nối lại tài khoản.

## 20. Logout, disconnect và delete cũng có thể race với refresh

Không chỉ hai refresh requests mới có concurrency. Ví dụ:

```text
Request A: đang refresh RT1.
Request B: người dùng bấm "Disconnect provider".
B: remove authorized client và revoke token.
A: refresh xong, save AT2/RT2.
```

Nếu A save sau thao tác disconnect của B, token có thể **xuất hiện lại trong store** dù người dùng đã ngắt liên kết.

Một thiết kế lifecycle cần xem:

- Token refresh.
- Logout/disconnect.
- User deletion/account deactivation.
- Revoke token ở AS.
- Cập nhật client credentials.
- Tenant offboarding.

Có thể dùng **version, tombstone, revocation marker hoặc trạng thái account-link** để ngăn một refresh đang chạy ghi lại authorization đã bị người dùng xóa. Một simple lock theo key có thể giúp serialization nếu **mọi đường refresh/delete dùng chung lock**, nhưng với nhiều instances cần một cơ chế coordination phù hợp.

### 20.1. Tombstone là gì?

Một entry có thể mang trạng thái:

```text
state = ACTIVE / DISCONNECTED
version = 12
```

Refresh chỉ được lưu nếu entry vẫn `ACTIVE` và version còn phù hợp. Khi người dùng disconnect, state chuyển sang `DISCONNECTED`; refresh response đến muộn không được ghi đè trạng thái đó.

Đây là một **mô hình custom storage**, không phải built-in field mặc định của `JdbcOAuth2AuthorizedClientService`.

## 21. Bảo mật storage và logging khi xử lý race

Refresh token có giá trị nhạy cảm cao. Những thông tin **không nên ghi**:

```text
refresh_token
access_token
Authorization: Basic clientId:clientSecret
client_assertion
code_verifier
id_token
```

Có thể ghi:

```text
registrationId=partner-api
principalReference=<internal opaque id>
operation=refresh
result=success | invalid_grant | timeout
lockWaitMs=...
refreshDurationMs=...
storageVersion=...
retryCount=...
```

Nếu principal name là thông tin cá nhân, cân nhắc **pseudonymization** trong logs. Không đưa raw principal/email vào high-cardinality metrics labels.

### 21.1. Fingerprint để xác định token version

Nếu cần đối chiếu token cũ/mới, không nên ghi toàn bộ refresh token hoặc hash dễ bị lộ không được quản trị. Một cách là dùng **HMAC/fingerprint được quản lý bằng secret** làm internal identifier cho debug/compare, hoặc tốt hơn sử dụng một **version counter** độc lập trong store.

Tránh log fingerprint ở quy mô cho phép theo dõi người dùng nếu không cần thiết. Việc kiểm tra race thường chỉ cần version + key đã được namespace hóa và timestamp.

### 21.2. Database và Redis không tự an toàn chỉ vì ở private subnet

Cần:

- TLS tới storage khi phù hợp.
- Access controls nguyên tắc đặc quyền tối thiểu.
- Encryption at rest và bảo vệ backups.
- Không log query parameters chứa token.
- Cơ chế xóa dữ liệu khi account disconnect.
- Secret/key rotation và audit theo chính sách.
- Isolation giữa tenants/principals.
- Bảo vệ lock keys khỏi dữ liệu nhạy cảm không cần thiết.

## 22. Quan sát production: metrics cần có

Một hệ thống không có dữ liệu quan sát sẽ khó phân biệt outage AS với refresh race.

| Metric | Mục đích |
|---|---|
| Số lần refresh attempt | Phát hiện spike khi token hết hạn. |
| Số refresh success | Theo dõi cấp lại token thành công. |
| Số `invalid_grant` | Phát hiện token invalid/reuse. |
| Số requests bị gom bởi single-flight | Biết concurrency control có hoạt động. |
| Lock wait duration | Phát hiện chờ lock quá lâu. |
| Token Endpoint latency | Chọn connect/read timeout và lease TTL. |
| Storage CAS conflict | Đếm xung đột cập nhật version. |
| Conditional delete no-op | Biết có failure path stale tránh xóa bản mới. |
| Re-authorization required | Theo dõi ảnh hưởng tới người dùng. |
| Token family/replay events do AS cung cấp | Nhận biết replay detection theo contract provider. |
| Number of API calls per authorized client | Đối chiếu tải với refresh frequency. |
| DB/store errors | Phân biệt persistence failure với AS error. |

Không gắn access token, refresh token hoặc raw user email làm nhãn metrics.

### 22.1. Một dấu hiệu thường thấy

```text
10:00:00  refresh_attempt=10
10:00:01  refresh_success=1
10:00:01  refresh_invalid_grant=9
```

Với cùng authorized client và token rotation, đây là dấu hiệu mạnh cần điều tra **duplicate refresh**, dù cũng cần xác minh nguyên nhân từ AS/telemetry phù hợp.

Một hệ thống dùng single-flight có thể ghi:

```text
10:00:00  refresh_attempt=1
10:00:00  in_flight_joiners=9
10:00:01  refresh_success=1
```

Các request cùng chờ một refresh, không gửi 10 refresh tokens trùng nhau.

## 23. Kiểm thử concurrency ở mức đơn vị

Bài test nên kiểm tra **hành vi đồng thời**, không chỉ `authorize()` trả token trong trường hợp đơn luồng.

Các tình huống cần bao phủ:

1. 10 threads cùng dùng authorized client đã gần hết hạn.
2. Chỉ một refresh call tới mock Token Endpoint khi single-flight hoạt động.
3. Cả 10 callers cuối cùng nhận authorized client chứa token mới.
4. Không có caller nào dùng RT1 sau khi RT2 đã được lưu.
5. Khi refresh thất bại, lock được nhả và caller sau có thể xử lý recovery theo policy.
6. Khi hai keys khác nhau cần refresh, không bị khóa toàn cục quá mức.
7. Sau logout/disconnect, refresh cũ không hồi sinh authorized client.
8. Token response có refresh token mới thì store lưu RT2, không giữ RT1.
9. CAS stale update/delete không đè version mới.
10. Distributed lock lease timeout không dẫn tới silent overwrite.

### 23.1. Dùng CountDownLatch để ép requests cùng bắt đầu

Trong Java/JUnit, có thể dùng `CountDownLatch` để tổ chức các threads bắt đầu gần nhau. Ví dụ pseudocode:

```java
int threadCount = 10;
CountDownLatch ready = new CountDownLatch(threadCount);
CountDownLatch start = new CountDownLatch(1);

for (int i = 0; i < threadCount; i++) {
    executor.submit(() -> {
        ready.countDown();
        start.await();

        // Tất cả gọi cùng một wrapper/manager và cùng key.
        manager.authorize(
            OAuth2AuthorizeRequest
                .withClientRegistrationId("partner-api")
                .principal("alice-uid")
                .build()
        );

        return null;
    });
}

ready.await();
start.countDown();
```

Đoạn này **minh họa kỹ thuật đồng bộ start**, chưa phải một bài test JUnit hoàn chỉnh; cần khai báo `executor`, `manager`, imports, timeout, thu thập futures và đóng executor. Trong bài test đầy đủ, sử dụng fake/mocked Token Endpoint và store để đếm số refresh requests, tránh gọi AS thật.

### 23.2. Tại sao cần test trường hợp lỗi?

Chỉ test “10 threads cùng thành công” chưa đủ. Cần mô phỏng:

```text
Thread A refresh thành công, lưu RT2.
Thread B nhận invalid_grant do dùng RT1 stale.
```

Sau đó xác nhận failure policy **không xóa nhầm RT2 nếu store có version-aware logic**, đồng thời không giả định RT2 chắc chắn còn hợp lệ nếu AS đã revoke token family.

Test thêm:

```text
Refresh response mất sau khi AS tiêu thụ RT1.
```

Với kết quả không chắc chắn, hệ thống phải tránh retry RT1 mù quáng và chuyển sang recovery/re-authorization khi cần.

### 23.3. Test trên một JVM không chứng minh distributed safety

Một test local với `ReentrantLock` có thể đạt kết quả hoàn hảo nhưng production vẫn lỗi khi chạy 3 pods. Phải có integration tests hoặc fault-injection ở lớp distributed coordination/storage nếu yêu cầu hệ thống là multi-instance.

Không cần dùng một Authorization Server production thật để tạo race; có thể dùng test provider/mock token endpoint với trạng thái rotate RT1→RT2 và từ chối reuse.

---

## 24. Các phương án kiến trúc để chọn

| Kiến trúc | Cơ chế phù hợp | Hạn chế |
|---|---|---|
| Một instance Spring MVC, một manager được mọi callers dùng | Per-key local lock hoặc single-flight | Không an toàn nếu có manager ngoài wrapper. |
| Nhiều instances, shared JDBC service | Distributed serialization + reload + CAS | Cần quản trị locks/leases và DB versions. |
| Spring Session chia sẻ giữa nodes | Coordination theo session/authorized client key | Session storage không tự khóa network refresh. |
| WebFlux một instance | Reactive in-flight deduplication | Không được block event loop, phải cleanup publisher. |
| WebFlux nhiều pods | Reactive single-flight + distributed coordination | Thêm failure modes của lease/lock. |
| Background job và web cùng dùng token user | Shared store + coordination chung ở tầng token lifecycle | Phải thống nhất principal/key và manager usage. |
| Token rotation strict/reuse detection | Ngăn duplicate refresh trước Token Endpoint | CAS đơn độc không đủ. |
| AS không rotate refresh token | Vẫn nên giảm duplicate requests và tránh lost updates | Race ít nghiêm trọng hơn nhưng không biến mất. |

**Khuyến nghị thiết kế theo mức rủi ro:**

- Nếu ứng dụng nhỏ, một instance và mọi callers cùng một manager, single-flight trong JVM thường là điểm bắt đầu đơn giản.
- Nếu ứng dụng đa instance và dùng refresh token rotation nghiêm ngặt, cần serialization giữa các nodes cùng version-aware storage/recovery.
- Nếu app có nhiều dòng code hoặc managers khác nhau tự refresh, ưu tiên đưa quyền refresh về **một abstraction quản lý chung** thay vì thêm locks riêng lẻ tại từng controller.
- Nếu AS hỗ trợ cơ chế sender-constrained refresh token hoặc chính sách rotation đặc biệt, phải đối chiếu tài liệu provider và threat model.
- Không khuyến khích tắt rotation hoặc nới lỏng replay detection chỉ để tránh xử lý concurrency ở client.

## 25. Những lỗi triển khai thường gặp

### Lỗi 1 — Mỗi request tự gọi Token Endpoint

Code tự đọc refresh token rồi POST `/token` trong mọi controller.

**Hậu quả:** nhiều requests có thể dùng RT1 cùng lúc và gây reuse detection.

**Cách làm tốt hơn:** gọi authorized client manager và tập trung token lifecycle vào một service/gateway với concurrency control.

### Lỗi 2 — Chỉ dùng ConcurrentHashMap để cache token

`ConcurrentHashMap` làm một số thao tác map thread-safe nhưng **không tự đảm bảo toàn bộ load–check–POST–save được thực hiện atomic**. Một map có thể vẫn chứa AT1 trong khi nhiều callers đã cùng gọi Token Endpoint.

### Lỗi 3 — Dùng `synchronized` trên mỗi request object

Nếu mỗi request tạo một object mới rồi `synchronized(this)`, các requests không dùng chung monitor. Không có serialization thực sự.

### Lỗi 4 — Dùng global lock cho mọi user

Một refresh của Alice làm Bob và hàng nghìn users khác phải đợi dù không có token liên quan.

**Cách xử lý:** khóa theo authorized client key hoặc dùng striped locks có giới hạn/đo contention.

### Lỗi 5 — Chỉ khóa khi save, không khóa token request

Hai requests có thể đã dùng RT1 cùng lúc trước khi đi tới thao tác save. Lúc đó đã quá muộn để ngăn AS phát hiện reuse.

### Lỗi 6 — Đọc authorized client trước khi lấy lock nhưng không đọc lại

Thread B chờ A refresh xong nhưng vẫn gửi RT1 được load từ trước.

**Cách xử lý:** re-read state bên trong critical section và để manager sử dụng object mới.

### Lỗi 7 — Distributed lock TTL ngắn hơn refresh request

Lock của A hết hạn khi HTTP request chưa xong; B lấy lock và dùng RT1.

**Cách xử lý:** tính tổng timeout, lease renewal, fencing và failure policy. Không giả định lock thuê bao là bảo đảm tuyệt đối.

### Lỗi 8 — CAS update nhưng vẫn gửi refresh trùng

CAS tránh ghi đè DB nhưng AS đã thấy RT1 bị dùng lại.

**Cách xử lý:** cần serialization trước POST refresh, không chỉ CAS sau response.

### Lỗi 9 — Failure handler xóa entry vừa được request khác làm mới

Request B nhận `invalid_grant` rồi remove theo key, xóa cả AT2/RT2 của A.

**Cách xử lý:** conditional removal theo version và coordination, đồng thời xác định AS có revoke token family không.

### Lỗi 10 — Tự retry invalid_grant liên tục

Nếu RT1 đã rotate, retry RT1 có thể kích hoạt thêm replay detection hoặc rate limiting.

**Cách xử lý:** phân loại lỗi, đọc lại state và re-authorization khi cần.

### Lỗi 11 — Chỉ khóa một manager nhưng request khác bypass nó

Một API gateway dùng locking wrapper, nhưng scheduled job gọi trực tiếp manager gốc.

**Cách xử lý:** xác định tất cả code paths và một nguồn token lifecycle chung.

### Lỗi 12 — Chia sẻ key giữa tenants

Hai users khác tenant cùng tên hiển thị và registration ID có thể đụng storage key.

**Cách xử lý:** namespace theo stable principal, tenant và issuer/provider đáng tin.

### Lỗi 13 — Giữ lock trong lúc gọi API nghiệp vụ

Sau khi lấy access token, code vẫn giữ lock cho toàn bộ `GET /orders` hoặc một nghiệp vụ 30 giây.

**Cách xử lý:** critical section chỉ bao trùm phần đọc/check/refresh/save cần serialization. **Thả lock trước khi gọi Resource Server API** nếu không có lý do giao thức đặc biệt.

### Lỗi 14 — Tắt TLS verify để xử lý timeout Token Endpoint

Race condition và TLS handshake failure là hai vấn đề khác nhau.

**Cách xử lý:** chỉnh HTTP transport, truststore và proxy theo chính sách; không bỏ bảo vệ kết nối chứa refresh token.

### Lỗi 15 — Dùng Client Credentials thay token của Alice sau refresh thất bại

Token được cấp cho service không mang authorization của Alice.

**Cách xử lý:** yêu cầu user reauthorize hoặc dùng delegated grant đúng chuẩn nếu được AS và policy hỗ trợ.

### Lỗi 16 — Chỉ test chức năng một thread

Test đơn luồng không phát hiện việc nhiều request cùng load RT1.

**Cách xử lý:** test có barrier/latch, mock token rotation, failpoint cho save/delete và test đa node khi cần.

## 26. Các tình huống thực hành

### Tình huống A — Dashboard gọi 8 API cùng lúc

Alice vừa đăng nhập, access token gần hết hạn và frontend mở dashboard có 8 parallel requests.

**Phân tích:** nếu 8 calls cùng dùng manager/store nhưng không có serialization, chúng có thể cùng dùng RT1.

**Giải pháp:** một single-flight theo `(registrationId, principal)`; một request refresh, các requests còn lại đợi và dùng AT2 sau khi lưu.

### Tình huống B — 3 pods dùng InMemory store

Mỗi pod có token riêng và refresh token riêng do mỗi lần authorization được lưu local.

**Phân tích:** các entries có thể không thực sự là **cùng** authorized client; tuy nhiên cũng có thể người dùng bị chuyển node và không thấy authorization.

**Giải pháp:** đánh giá storage architecture trước khi thêm distributed lock. Nếu cần cùng một authorization, dùng shared storage nhất quán.

### Tình huống C — 3 pods dùng JDBC service

Các pods dùng chung một `(registrationId, principalName)`.

**Phân tích:** shared DB làm token visible nhưng không bảo đảm chỉ một node refresh.

**Giải pháp:** distributed locking + re-read + version-aware save/delete; bổ sung test token rotation.

### Tình huống D — Request A thắng, B lỗi rồi xóa entry

A save RT2; B nhận `invalid_grant` và remove entry theo key.

**Phân tích:** failure handler mặc định có thể có tác động ngoài ý muốn trong tình huống race.

**Giải pháp:** ngăn duplicate refresh, dùng conditional removal khi cần và kiểm tra replay policy của AS.

### Tình huống E — Request A timeout nhưng AS đã rotate

Client không nhận RT2 và store còn RT1.

**Phân tích:** kết quả ở AS không rõ, nên retry RT1 có thể bị xem là reuse.

**Giải pháp:** xử lý outcome không chắc chắn; không retry mù quáng. Khi cần, yêu cầu user authorization mới.

### Tình huống F — Người dùng disconnect khi refresh đang chạy

B xoá tài khoản liên kết, A refresh thành công và lưu lại token.

**Phân tích:** token bị “hồi sinh” sau disconnect.

**Giải pháp:** dùng account-link state/tombstone và conditional writes hoặc serialization giữa refresh và disconnect.

### Tình huống G — Token chưa hết hạn nhưng API 401

API từ chối access token của Alice dù `expiresAt` còn vài phút.

**Phân tích:** có thể token bị revoke hoặc audience/scope sai, không chắc do concurrency refresh.

**Giải pháp:** phân biệt Resource Server error và Token Endpoint error, không tự xin token mới liên tục khi cấu hình sai.

### Tình huống H — Clock skew là 5 phút, token chỉ sống 3 phút

Mỗi manager call thấy access token “gần hết hạn”.

**Phân tích:** có thể tạo refresh liên tục, kích thích race.

**Giải pháp:** điều chỉnh skew theo lifetime và latency. Nếu vẫn nhiều requests đồng thời, cần single-flight.

### Tình huống I — WebFlux dùng `.block()` để lấy token

Developer bọc manager blocking trong reactive handler.

**Phân tích:** chặn event loop, giảm throughput và có thể gây deadlock/timeout.

**Giải pháp:** dùng reactive manager và reactive single-flight. Không áp ReentrantLock blocking trực tiếp lên event loop.

### Tình huống J — Custom per-key lock map không xóa entries

Mỗi lần user đăng nhập tạo một lock key mới giữ mãi trong map.

**Phân tích:** lock map tăng không giới hạn theo số users.

**Giải pháp:** striped locks hoặc keyed-lock registry có reference counting/eviction được thiết kế đúng.

### Tình huống K — Refresh kết quả về muộn sau lease expiry

Pod A giữ lock hết TTL, Pod B đã cập nhật version 8, rồi A lưu version 7.

**Phân tích:** distributed lock đơn độc không chống stale writes.

**Giải pháp:** CAS/fencing ngăn A ghi đè, nhưng vẫn phải xử lý rủi ro duplicate token requests ở AS.

### Tình huống L — Backend job và request web cùng token Alice

Job refresh RT1 trong khi request web cũng refresh RT1 qua manager khác.

**Phân tích:** có hai code paths refresh cùng authorized client nhưng dùng locks khác nhau.

**Giải pháp:** phối hợp concurrency ở mức token lifecycle/shared store thay vì chỉ khóa controller.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao nhiều requests có thể cùng refresh một authorized client?

**Trả lời:** Chúng có thể cùng đọc token cũ và cùng thấy access token đã tới ngưỡng refresh trước khi bất kỳ request nào kịp lưu token mới.

**Câu 2.** Refresh token rotation làm race nguy hiểm hơn thế nào?

**Trả lời:** AS có thể vô hiệu hóa RT1 sau lần refresh đầu; lần dùng RT1 tiếp theo bị `invalid_grant` và có thể kích hoạt reuse detection hoặc revoke token family.

**Câu 3.** `RefreshTokenOAuth2AuthorizedClientProvider` thường làm gì nếu access token vẫn còn đủ hạn?

**Trả lời:** Nó không cần reauthorize và có thể trả `null`; manager có thể dùng authorized client hiện có.

**Câu 4.** `clockSkew` có phải mutex/lock không?

**Trả lời:** Không. Nó chỉ ảnh hưởng ngưỡng thời gian quyết định token cần refresh, không serialize requests.

**Câu 5.** Vì sao phải đọc lại token sau khi lấy lock?

**Trả lời:** Một request khác có thể đã refresh và lưu RT2 trong lúc caller đang chờ lock; snapshot RT1 trước lock đã stale.

**Câu 6.** Local `ReentrantLock` có đồng bộ giữa 3 pods không?

**Trả lời:** Không. Nó chỉ có hiệu lực với threads dùng cùng lock trong một JVM.

**Câu 7.** CAS có ngăn AS nhận hai refresh requests với RT1 không?

**Trả lời:** Không. CAS chủ yếu bảo vệ thao tác ghi/xóa store, nên cần serialization trước token request.

**Câu 8.** Failure handler mặc định có thể làm gì khi gặp `invalid_grant`?

**Trả lời:** Theo manager Spring Security, nó có thể xóa authorized client đã lưu. Trong race, cần tránh xóa nhầm version mới.

**Câu 9.** Có thể retry RT1 vô hạn khi refresh timeout không?

**Trả lời:** Không. AS có thể đã tiêu thụ RT1 dù response bị mất, nên retry có thể bị coi là reuse.

**Câu 10.** Vì sao cần fencing token nếu distributed lock có TTL?

**Trả lời:** Khi lease của caller cũ hết hạn, caller mới có thể đã ghi state mới; fencing giúp từ chối stale writes từ caller cũ.

**Câu 11.** Khi nào nên yêu cầu user reauthorize?

**Trả lời:** Khi refresh token không còn hợp lệ và không có recovery được AS/policy cho phép, hoặc token family đã bị revoke.

**Câu 12.** Reactivity có tự ngăn refresh race không?

**Trả lời:** Không. Nhiều reactive subscriptions hoặc nhiều pods vẫn có thể gửi duplicate token requests; cần reactive single-flight/coordination phù hợp.

**Câu 13.** Vì sao không dùng token Client Credentials để thay token của user?

**Trả lời:** Nó đại diện cho service, không mang authorization mà user đã cấp.

**Câu 14.** Điều gì xảy ra nếu disconnect và refresh thực hiện đồng thời?

**Trả lời:** Refresh response về muộn có thể lưu lại token sau khi account đã disconnect; cần tombstone/version/serialization.

**Câu 15.** Khi test concurrency, nên đếm điều gì?

**Trả lời:** Số token refresh requests thực sự, refresh success/invalid_grant, số callers nhận token mới và số CAS conflicts hoặc entry bị xóa sai.

## 28. Ghi nhớ trọng tâm

| Khái niệm | Ghi nhớ |
|---|---|
| **Authorized client** | Lưu access token + refresh token cùng registration/principal. |
| **Refresh token rotation** | Mỗi refresh thành công có thể thay RT1 bằng RT2 và vô hiệu hóa RT1. |
| **Duplicate refresh** | Nhiều requests cùng dùng RT1 khi state còn stale. |
| **`invalid_grant`** | Có thể đến từ RT không hợp lệ/hết hạn/bị dùng lại; không kết luận nguyên nhân khi chưa điều tra. |
| **`RefreshTokenOAuth2AuthorizedClientProvider`** | Quyết định khi nào refresh dựa trên authorized client, RT và expiry/skew. |
| **`OAuth2AuthorizedClientManager`** | Điều phối load, provider, success/failure handling và persistence. |
| **Local single-flight** | Chỉ một refresh operation cho một key trong cùng JVM. |
| **Per-key lock** | Khóa theo security namespace của authorized client, tránh global contention. |
| **Re-read sau lock** | Không dùng RT stale đã đọc trước khi chờ. |
| **Distributed lock** | Đồng bộ giữa nodes, nhưng phải xét lease và failure. |
| **CAS / optimistic version** | Ngăn stale write/delete, không tự ngăn duplicate token HTTP requests. |
| **Fencing token** | Từ chối writes từ caller có lease cũ hết hạn. |
| **Conditional remove** | Tránh thất bại với version 7 xóa mất version 8. |
| **Retry** | Không lặp RT cũ mù quáng khi refresh outcome không chắc chắn. |
| **User disconnect** | Cần bảo vệ khỏi refresh response đến muộn ghi lại token. |
| **WebFlux** | Dùng reactive in-flight deduplication; tránh block event loop. |
| **Multi-instance** | Shared storage một mình không đủ; cần coordination theo key. |
| **Quan sát hệ thống** | Theo dõi refresh rate, invalid_grant, lock wait và CAS conflicts, không log secrets. |

### Kết luận

Khi **nhiều requests đồng thời refresh cùng một `OAuth2AuthorizedClient`**, vấn đề không chỉ là gửi dư Token Endpoint requests. Với **refresh token rotation**, các requests dùng lại RT1 có thể khiến AS từ chối, phát hiện token replay hoặc thậm chí thu hồi cả token family. Spring Security cung cấp manager/provider/service và cơ chế xử lý lỗi/lưu trữ, nhưng không nên mặc định toàn bộ thao tác refresh đã atomic trong mọi process và mọi node.

Giải pháp đáng tin cậy là **serialize refresh theo authorized client key, đọc lại state sau khi có quyền refresh, lưu/xóa bằng cơ chế có điều kiện và có recovery policy khi kết quả AS không rõ ràng**. Với một JVM, có thể dùng single-flight/per-key locks; với nhiều nodes, cân nhắc distributed coordination, CAS và fencing. Đừng quên `invalid_grant` failure handling, token rotation, user disconnect, sự khác biệt Servlet/WebFlux và bảo mật refresh token trong logs/storage.

## Tài liệu tham khảo chính thức

- [Spring Security — Core Interfaces and Classes for OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): vai trò `OAuth2AuthorizedClientManager`, providers, success/failure handlers và persistence.
- [Spring Security API — RefreshTokenOAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RefreshTokenOAuth2AuthorizedClientProvider.html): điều kiện refresh, clock skew và token response client.
- [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): manager cho Servlet request và behavior của failure handler.
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): manager ngoài Servlet request, lưu authorized clients và xử lý `invalid_grant`.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive authorized client manager và storage.
- [RFC 6749 — OAuth 2.0 Refresh Token Grant](https://datatracker.ietf.org/doc/html/rfc6749#section-6): cơ chế xin access token mới bằng refresh token.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token replay detection, rotation và các yêu cầu bảo mật liên quan.
