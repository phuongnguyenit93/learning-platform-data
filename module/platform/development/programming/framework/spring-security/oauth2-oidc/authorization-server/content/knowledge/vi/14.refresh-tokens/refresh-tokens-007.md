# Thiết kế phát hiện tái sử dụng và thu hồi token family khi cần mở rộng

## 1. Bài toán: một refresh token cũ bất ngờ xuất hiện lần nữa

Trong ứng dụng Spring Boot xây dựng OAuth 2.0/OpenID Connect (OIDC) Authorization Server bằng **Spring Security** và **Spring Authorization Server (SAS)**, refresh token cho phép client xin access token mới mà không bắt người dùng đăng nhập tương tác sau mỗi lần access token hết hạn.

Giả sử `orders-portal` đang giữ refresh token `R1`. Khi cần làm mới phiên, client gửi `R1` đến `/oauth2/token`. Authorization Server cấp access token mới và, với chính sách **refresh token rotation**, phát hành refresh token `R2` thay cho `R1`.

Một lúc sau, token endpoint nhận lại `R1`. Có thể xảy ra hai tình huống:

- Client hợp lệ bị timeout, không nhận được phản hồi lần đầu và **retry** bằng `R1`.
- Kẻ tấn công đã sao chép `R1` rồi cố dùng lại sau khi nó đã được tiêu thụ.

Từ phía server, hai yêu cầu có thể giống nhau. Nếu server chỉ trả `invalid_grant` vì `R1` không còn hiệu lực, ta đã **từ chối lần sử dụng sai** nhưng chưa chắc đã **phát hiện và xử lý được khả năng cả chuỗi refresh token bị lộ**. Đó là lý do một số hệ thống cần mô hình **refresh token family** và **reuse detection**.

Bài thuộc chương **Refresh Token** giải thích:

1. Phân biệt refresh token rotation, reuse detection và family-wide revocation.
2. Những gì `TokenSettings.reuseRefreshTokens(false)` giải quyết và những gì ứng dụng có thể phải bổ sung.
3. Cách mô hình hóa quan hệ cha–con giữa các refresh token, lưu lịch sử an toàn và ngăn race condition.
4. Khi nào nên thu hồi cả family, khi nào chỉ báo lỗi `invalid_grant`, và tác động tới access token đã cấp.
5. Cách mở rộng Spring Authorization Server, kiểm thử và vận hành mà không phá vỡ kiểm tra grant mặc định.

> **Lưu ý phiên bản:** Các tên lớp và ví dụ cấu hình minh họa dòng **Spring Authorization Server 1.x / Spring Security 6.x**. API và khả năng tích hợp có thể thay đổi khi Authorization Server được tích hợp vào các thế hệ Spring Security mới hơn. Cần đối chiếu Javadoc và mã thực thi đúng phiên bản; không coi một thiết kế token family minh họa là tính năng có sẵn trong mọi phiên bản SAS.

## 2. Từ refresh token thông thường đến token family

### 2.1. Các thuật ngữ phải tách biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Refresh token** | Credential dùng với `grant_type=refresh_token` để xin token mới | `R1` |
| **Refresh token rotation** | Mỗi lần refresh thành công, cấp một refresh token thay thế và không cho token cũ tiếp tục dùng | `R1 → R2 → R3` |
| **Token reuse / replay** | Một refresh token đã được tiêu thụ/không còn được phép sử dụng lại xuất hiện trong request mới | Client gửi lại `R1` sau khi đã nhận `R2` |
| **Refresh token family** | Nhóm các refresh token có quan hệ nguồn gốc từ cùng một lần cấp/quyền hoặc phiên, gồm cả token cũ đã dùng | `F42 = {R1, R2, R3}` |
| **Reuse detection** | Nhận diện một token **đã dùng** lại được trình bày bằng cách giữ trạng thái lịch sử đủ lâu | Tìm fingerprint của `R1`, thấy `status=CONSUMED` |
| **Family revocation** | Vô hiệu hóa toàn bộ refresh token hiện tại và những token sẽ sinh từ family đó | Phát hiện replay `R1` → chặn cả `R3` đang active |
| **Sender-constrained token** | Token bị ràng buộc với bằng chứng sở hữu khóa/chứng chỉ của một client/thiết bị theo profile hỗ trợ | DPoP hoặc mTLS theo chuẩn, phiên bản và policy phù hợp |

**Không phải cứ bật rotation là đã có family reuse detection.** Sau rotation, một token cũ có thể đơn giản không còn được tìm thấy trong kho authorization hiện tại. Để nhận biết “đây từng là token hợp lệ thuộc family F42”, server phải còn giữ dấu vết của token cũ, dù không cho phép dùng lại.

### 2.2. Minh họa vòng đời của một family

```mermaid
flowchart LR
    R1["R1\nACTIVE"] -->|"refresh hợp lệ"| R2["R2\nACTIVE"]
    R2 -->|"refresh hợp lệ"| R3["R3\nACTIVE"]
    R1 -.->|"chuyển thành"| U1["R1\nCONSUMED"]
    R2 -.->|"chuyển thành"| U2["R2\nCONSUMED"]
    U1 -->|"R1 bị gửi lại"| D["REUSE_DETECTED"]
    D --> F["Family REVOKED"]
    F --> X["R3 không được refresh nữa"]
```

Các mũi tên mô tả quan hệ logic. Khi `R1` được đổi thành `R2`, trạng thái `R1` phải chuyển từ `ACTIVE` sang `CONSUMED` một cách nguyên tử với thao tác phát hành `R2`. `R1` không được trở lại `ACTIVE`, kể cả khi hệ thống mất kết nối giữa các instance.

Trong mô hình đơn giản, **mỗi family chỉ có một refresh token đang active tại một thời điểm**. Đây là lựa chọn thiết kế giúp phát hiện replay rõ ràng, không phải đặc tả bắt buộc duy nhất cho mọi giao thức hoặc mọi sản phẩm.

### 2.3. Token family không đồng nghĩa toàn bộ tài khoản

Một người dùng có thể đăng nhập vào `orders-portal` ở máy tính và điện thoại. Nếu mỗi phiên/authorization ban đầu tạo một family riêng:

```text
Alice + orders-portal + phiên laptop  -> family F-LAPTOP
Alice + orders-portal + phiên mobile  -> family F-MOBILE
Bob   + orders-portal + phiên laptop  -> family F-BOB
```

Replay trong `F-LAPTOP` nên **ít nhất** chặn các refresh token thuộc family đó theo chính sách; nó không mặc nhiên đòi xóa tất cả token của Alice trên mọi thiết bị hoặc token của Bob. Tùy mức rủi ro, tổ chức có thể bổ sung hành động account-wide revocation, nhưng phải tách đó khỏi thao tác family-wide để tránh vô hiệu hóa quá rộng.

## 3. Mối đe dọa: vì sao rotation chưa đủ nếu không nhớ token cũ?

### 3.1. Kẻ tấn công có refresh token đã bị lộ

Giả sử `R1` bị đánh cắp và cả client hợp lệ lẫn kẻ tấn công đều có thể sử dụng nó. Một trong hai bên sẽ đổi `R1` thành `R2` trước; bên còn lại gửi lại `R1` sẽ bị từ chối.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client hợp lệ
    participant AS as Authorization Server
    participant DB as Family Store
    participant X as Kẻ tấn công
    C->>AS: refresh_token=R1
    AS->>DB: Kiểm tra R1 ACTIVE
    DB-->>AS: ACTIVE trong family F42
    AS->>DB: Tiêu thụ R1 và tạo R2
    AS-->>C: Access token mới + R2
    X->>AS: refresh_token=R1 lần nữa
    AS->>DB: Tra fingerprint R1
    DB-->>AS: R1 CONSUMED, family F42
    AS->>DB: Đánh dấu F42 REVOKED
    AS-->>X: invalid_grant
    C->>AS: refresh_token=R2
    AS->>DB: Kiểm tra F42
    DB-->>AS: REVOKED
    AS-->>C: invalid_grant; yêu cầu đăng nhập lại
```

Đây là **hành vi ứng dụng cần thiết kế thêm** khi chọn family-wide revocation, không phải cam kết rằng SAS mặc định thực hiện đủ các bước trên. Việc phát hiện reuse cho biết cùng một refresh token đã xuất hiện nhiều lần; **không thể phân biệt chắc chắn bên nào là client hợp lệ**. Vì thế các hệ thống có yêu cầu an ninh cao thường thu hồi family và buộc người dùng bắt đầu authorization mới.

### 3.2. Giới hạn của cơ chế phát hiện

Reuse detection có những giới hạn cần công bố:

- Nếu token bị đánh cắp nhưng **chưa được dùng lại**, không có sự kiện reuse để phát hiện.
- Nếu kẻ tấn công đổi token trước và client hợp lệ không bao giờ refresh nữa, có thể không xuất hiện replay trong khoảng quan sát.
- Nếu kẻ tấn công lấy cả token mới nhất và liên tục kiểm soát client, family rotation không thay thế bảo vệ thiết bị, XSS/CSRF hay sender-constraining.
- Nếu không giữ fingerprint/trạng thái token đã tiêu thụ, một request bằng token cũ có thể chỉ là “token không tồn tại”; không suy ra được family cần thu hồi.
- Nếu trình duyệt/app retry sau timeout, family revocation có thể xảy ra dù không có kẻ tấn công. Đây là **đánh đổi an ninh–khả dụng**, không phải lỗi cần chữa bằng cách chấp nhận lại `R1` một cách tùy ý.

### 3.3. Các đường làm lộ refresh token

Refresh token không nên xuất hiện trong URL, query string, analytics, reverse-proxy log, exception stack trace, bản sao debug hay phần frontend không kiểm soát được. Với backend confidential client, hãy giữ token ở kho credential phía server với mã hóa, phân quyền truy cập và quản lý khóa phù hợp. Với public client, cần cân nhắc profile hiện đại, rotation, sender-constraining và lưu trữ theo khuyến nghị của nền tảng.

**Không dùng một `client_secret` được nhúng trong SPA/mobile để “bảo vệ” refresh token**. Public client không thể đảm bảo bí mật đó; cần ràng buộc giao thức và mô hình lưu trữ thích hợp.

## 4. Spring Authorization Server hỗ trợ gì sẵn?

### 4.1. Refresh Grant cơ bản

Ở token endpoint, client gửi:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=R1&scope=orders.read
```

Đây là request minh họa; `BASE64_CLIENT_CREDENTIALS` và `R1` là placeholder, **không phải credential thật**. Confidential client phải xác thực bằng phương thức được đăng ký. Việc có thể gửi `scope` trong refresh request, phạm vi nào được phép và cách cấp refresh token phụ thuộc grant, client và cấu hình.

Một luồng refresh thông thường trong SAS liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `OAuth2TokenEndpointFilter` | Tiếp nhận token request |
| `OAuth2RefreshTokenAuthenticationConverter` | Đọc `grant_type=refresh_token` và tạo yêu cầu xác thực của grant |
| `OAuth2RefreshTokenAuthenticationToken` | Đối tượng `Authentication` biểu diễn refresh grant request |
| `OAuth2ClientAuthenticationFilter` | Xác thực client theo cơ chế được đăng ký, nếu áp dụng |
| `OAuth2RefreshTokenAuthenticationProvider` | Kiểm tra refresh token, client, phạm vi và điều kiện grant; phát hành token mới |
| `OAuth2AuthorizationService` | Tra và lưu trạng thái authorization/token |
| `OAuth2TokenGenerator` | Tạo token theo cấu hình |
| `TokenSettings` | Chính sách thời hạn, reuse/rotation và các cài đặt token khác |

### 4.2. Cấu hình rotation với `reuseRefreshTokens(false)`

Ví dụ cho một confidential web client (SAS 1.x):

```java
RegisteredClient ordersWeb = RegisteredClient.withId(stableInternalId)
        .clientId("orders-web")
        .clientSecret(passwordEncoder.encode(secretFromSecretManager))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://orders.example.com/login/oauth2/code/orders")
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .refreshTokenTimeToLive(Duration.ofDays(14))
                .reuseRefreshTokens(false)
                .build())
        .build();
```

Trong ví dụ, `stableInternalId` là khóa client đã được lưu bền vững; `secretFromSecretManager` là bí mật lấy qua hệ thống quản lý secret, không phải literal ghi vào source code. Mã chỉ xây dựng `RegisteredClient`, chưa phải cấu hình đầy đủ của Authorization Server.

`reuseRefreshTokens(false)` yêu cầu **phát hành refresh token mới khi refresh thành công theo khả năng thực thi của SAS**. Trên các phiên bản SAS 1.x, trạng thái authorization có thể được cập nhật để dùng refresh token mới thay token cũ. Điều này giúp token cũ không tiếp tục được dùng như token hiện hành.

**Giới hạn quan trọng:** cài đặt trên **không phải API khai báo token family**, không bảo đảm lưu lịch sử mọi refresh token đã tiêu thụ, không tự cung cấp `family_id`, cũng không nên suy ra rằng framework tự **thu hồi cả chuỗi** khi phát hiện reuse. Phải kiểm tra hành vi chính xác của `OAuth2RefreshTokenAuthenticationProvider` và `OAuth2AuthorizationService` đang dùng.

### 4.3. `reuseRefreshTokens(true)` và rủi ro khi cần phát hiện replay

Với chính sách tái sử dụng cùng refresh token, client có thể dùng một token nhiều lần trong giới hạn hợp lệ; khi ấy “token này đã xuất hiện lần thứ hai” không phải bằng chứng bất thường. Muốn phát hiện **reuse sau khi đã tiêu thụ**, cần **rotation và trạng thái tiêu thụ có thể kiểm chứng**.

Một dự án mới không nên giữ reuse vô thời hạn chỉ để tránh xử lý retry. Đặc biệt với public clients, OAuth 2.0 Security BCP đặt yêu cầu phát hiện refresh token replay thông qua **sender-constraining hoặc rotation** phù hợp; cần lựa chọn dựa trên mô hình đe dọa và khả năng hỗ trợ của phiên bản/framework.

### 4.4. Public client không đương nhiên nhận refresh token

Không giả định mọi Authorization Code + PKCE public client đều được SAS cấp refresh token trong mọi cấu hình. Một số cách triển khai SAS 1.x hạn chế việc phát hành refresh token cho public client. Nếu sản phẩm cần phiên dài hạn trên SPA/mobile, phải xác minh khả năng của phiên bản, nguyên tắc OAuth Security BCP và phương án BFF/backend token storage hoặc sender-constraining khi thích hợp.

Không tự sửa client authentication hoặc token generator để cấp refresh token thiếu chính sách chỉ vì “mobile cần đăng nhập lâu”.

## 5. Khi nào thật sự cần mở rộng thành token family?

Không phải hệ thống nào cũng cần xây family registry riêng. Trước khi thiết kế, hãy xác định **yêu cầu có thể kiểm thử**:

| Yêu cầu | Rotation thông thường có thể đủ? | Cần bổ sung khi nào? |
| --- | --- | --- |
| Token cũ không được dùng để xin token mới | Thường có, khi rotation và persistence đúng | Kiểm thử với phiên bản SAS và repository thực tế |
| Phân biệt token cũ từng hợp lệ với token hoàn toàn ngẫu nhiên | Không nhất thiết | Cần lưu fingerprint/historical record |
| Phát hiện `R1` đã tiêu thụ lại xuất hiện | Không suy ra từ cài đặt rotation | Cần reuse registry và trạng thái token |
| Biết active descendant `R3` của `R1` | Không phải mô hình mặc định được bảo đảm | Cần family ID và quan hệ token |
| Tự động chặn mọi refresh tiếp theo trong family | Không chỉ bằng `reuseRefreshTokens(false)` | Cần family revocation policy thực thi ở refresh endpoint |
| Ngăn hai request đồng thời đều đổi được cùng token | Phải kiểm chứng phụ thuộc persistence | Có thể cần lock/CAS/transaction mạnh hơn |
| Vô hiệu hóa access token JWT còn hạn ngay lập tức | Không | Resource Server cần state check/denylist/introspection hoặc token TTL phù hợp |
| Hiển thị cảnh báo bảo mật cho người dùng | Không | Cần sự kiện reuse có audit/correlation |

Nếu hệ thống chỉ cần token cũ bị từ chối và access token sống rất ngắn, rotation chuẩn có thể đáp ứng mục tiêu đã đặt. Nếu hệ thống tuyên bố “phát hiện token bị đánh cắp và thu hồi toàn bộ family”, phải xây được **đường dẫn kiểm tra và bằng chứng kiểm thử** cho tuyên bố đó.

## 6. Mô hình dữ liệu gợi ý cho family và lịch sử token

Một phương án là duy trì hai nhóm dữ liệu:

1. **`refresh_token_family`**: danh tính family, client, principal, authorization/phiên, trạng thái và thời điểm thu hồi.
2. **`refresh_token_lineage`**: fingerprint của từng refresh token, quan hệ parent/child, trạng thái đã dùng và thời gian.

```mermaid
erDiagram
    REFRESH_TOKEN_FAMILY ||--o{ REFRESH_TOKEN_LINEAGE : contains
    REFRESH_TOKEN_FAMILY {
        string family_id PK
        string registered_client_id
        string principal_name
        string authorization_id
        string status
        datetime created_at
        datetime expires_at
        datetime revoked_at
        bigint version
    }
    REFRESH_TOKEN_LINEAGE {
        string token_id PK
        string family_id FK
        string parent_token_id
        string token_fingerprint UK
        string status
        datetime issued_at
        datetime expires_at
        datetime consumed_at
    }
```

Đây là **lược đồ nghiệp vụ minh họa**, không phải schema do SAS tạo sẵn. Với hệ thống đa tenant, phải bổ sung định danh tenant/issuer và ràng buộc phân vùng dữ liệu. `principal_name` có thể không đại diện end user trong một số grant; việc định danh family cần phù hợp nguồn gốc cấp refresh token.

### 6.1. Gợi ý trường và ràng buộc

| Trường | Vai trò | Quy tắc bảo mật/vận hành |
| --- | --- | --- |
| `family_id` | ID chuỗi rotation | Sinh một lần, không thay trong các lần refresh |
| `registered_client_id` | Khóa `RegisteredClient.id` nội bộ | Không thay bằng chuỗi `client_id` HTTP |
| `authorization_id` | Liên hệ đến `OAuth2Authorization` | Lấy từ authorization hợp lệ, dùng để tìm trạng thái cấp token |
| `principal_name` | Chủ thể được cấp quyền, khi có | Không tin principal do caller tự khai |
| `status` family | `ACTIVE`, `REVOKED`, `EXPIRED` | Family `REVOKED` không được phát hành refresh tiếp |
| `token_fingerprint` | Khóa tra token không cần lưu plaintext | Dùng HMAC hoặc hash an toàn trên token ngẫu nhiên entropy cao, có thiết kế quản lý khóa |
| `parent_token_id` | Quan hệ giữa các đời token | Giúp truy dòng; không dựa vào thứ tự tên token |
| `status` token | `ACTIVE`, `CONSUMED`, `REVOKED` | Không biến `CONSUMED` về `ACTIVE` |
| `consumed_at` | Thời điểm token đã được dùng | Phục vụ nhận diện replay, audit và TTL |
| `version` | Kiểm soát cập nhật đồng thời | Dùng CAS/optimistic locking hoặc row lock theo thiết kế |
| `expires_at` | Hạn token/family | Không cho refresh vượt giới hạn tuyệt đối của family |

Nên có **ràng buộc duy nhất** cho fingerprint và, trong mô hình một token active/family, cơ chế bảo đảm không thể có hai token active hợp lệ cùng lúc. Có thể dùng row lock trên family và transaction để tuần tự hóa mọi rotation; unique partial index cho trạng thái active là biện pháp bổ sung **phụ thuộc database**, không phải SQL portable cho mọi dialect.

### 6.2. Vì sao phải giữ dấu vết token đã dùng?

Với rotation, `OAuth2Authorization` có thể chỉ giữ **refresh token hiện hành**. Sau khi `R1` bị thay bằng `R2`, `authorizationService.findByToken("R1", REFRESH_TOKEN)` có thể không tìm thấy authorization. Lúc này server không biết một chuỗi ngẫu nhiên được gửi tới là:

- Token cũ từng hợp lệ thuộc family F42;
- Token chưa từng tồn tại;
- Token của một issuer/môi trường khác;
- Giá trị ngẫu nhiên do kẻ tấn công gửi.

Muốn nhận diện replay **đúng nghĩa**, cần giữ **tombstone / fingerprint** của token cũ ít nhất trong cửa sổ phát hiện được định nghĩa. Nếu dọn ngay bản ghi `R1` sau khi phát hành `R2`, sẽ mất khả năng liên kết `R1` với family.

Giữ dấu vết không có nghĩa giữ raw refresh token. Token plaintext phải được xem là credential. Với token đủ entropy, có thể dùng fingerprint bằng HMAC-SHA-256 (khóa HMAC bảo vệ riêng) hoặc giải pháp tương đương có kiểm soát, nhằm tra cứu mà không lộ token gốc khi DB bị đọc trái phép. Nếu xoay khóa HMAC, cần thiết kế version/khả năng tra cứu các fingerprint cũ đến hết vòng đời phát hiện.

### 6.3. Một family nên hết hạn lúc nào?

Đừng để rotation tạo chuỗi refresh vô hạn nếu chính sách bắt buộc đăng nhập lại sau một khoảng cố định. Có hai giới hạn khác nhau:

- **Hạn từng refresh token:** mỗi token có `expires_at`, ví dụ 7 ngày từ lúc phát hành.
- **Hạn tuyệt đối của family:** mọi descendant không được vượt thời điểm chấm dứt family, ví dụ 30 ngày từ lần cấp ban đầu.

Giá trị thời gian cụ thể là **ví dụ thiết kế**, phải cân bằng UX, bảo mật và quản lý phiên. Một family có thể hết hạn sớm do user logout, thu hồi consent, client bị khóa, thay đổi credential hoặc sự kiện reuse.

## 7. Thuật toán rotation nguyên tử và phát hiện reuse

### 7.1. Máy trạng thái tối thiểu

```mermaid
stateDiagram-v2
    [*] --> ACTIVE : Issue R1
    ACTIVE --> CONSUMED : Refresh thành công và tạo R2
    ACTIVE --> EXPIRED : Quá hạn
    ACTIVE --> REVOKED : User/admin/client revoke
    CONSUMED --> REUSE_DETECTED : R1 xuất hiện lần nữa
    REUSE_DETECTED --> REVOKED : Revoke family
    EXPIRED --> [*]
    REVOKED --> [*]
```

Lưu ý trạng thái `REUSE_DETECTED` có thể là **sự kiện audit**, không nhất thiết là cột status riêng của token. Khi token `CONSUMED` xuất hiện lại, system đánh dấu family `REVOKED` trong transaction. Một token đã hết hạn mà chưa từng dùng cần bị từ chối; việc coi đó là replay và thu hồi cả family hay không là quyết định chính sách rủi ro.

### 7.2. Trình tự an toàn với một database dùng chung

Ví dụ nguyên lý cho một lần refresh:

1. **Xác thực OAuth client trước.** Kiểm tra phương thức client authentication đã đăng ký và credential nếu áp dụng. Không dựa vào `client_id` được tự khai để tin request.
2. **Tra fingerprint token.** Nếu chưa từng tồn tại, trả lỗi `invalid_grant` và không chọn ngẫu nhiên family để thu hồi.
3. **Xác minh token thuộc client/issuer đúng.** Nếu request không đúng ràng buộc, từ chối theo giao thức; không để caller trái phép chủ động thu hồi family của người khác.
4. **Khóa family hoặc kiểm soát version.** Mọi request thay đổi một family tuân theo cùng thứ tự khóa nhằm tránh hai lần refresh đồng thời.
5. **Đọc lại trạng thái token dưới khóa.** Nếu token đã `CONSUMED`, đánh dấu family `REVOKED`, ghi sự kiện reuse và kết thúc với quyết định từ chối. Nếu family đã `REVOKED`, chỉ từ chối.
6. **Kiểm tra điều kiện grant chuẩn.** Token chưa hết hạn, authorization hợp lệ, client được dùng refresh grant, scope không vượt đã cấp, policy phiên/user/tenant hợp lệ.
7. **Tạo refresh token mới `Rnext` cùng access token mới.** Lưu family ID, parent token và fingerprint mới; đổi token cũ sang `CONSUMED`.
8. **Cập nhật `OAuth2Authorization` và family/lineage nhất quán** trong transaction phù hợp. Commit trước khi trả token response.
9. **Trả token response** chỉ sau khi trạng thái đã lưu thành công; nếu transaction rollback, không được công bố token đã cấp là hợp lệ.

Các bước 5 và 8 là nơi hệ thống cần **tính nguyên tử**; chỉ kiểm tra `usedAt == null` trong memory rồi ghi ở một bước khác có thể cho hai request đồng thời cùng thắng.

### 7.3. Pseudocode cho một service tích hợp

Mẫu sau **cố ý là pseudocode Java**, biểu diễn hợp đồng nghiệp vụ; `FamilyRepository`, `LineageRepository`, `RefreshIssuer` và các DTO **không phải API có sẵn của SAS**:

```java
@Transactional
RefreshDecision rotateAndPersist(
        AuthenticatedClient client,
        String presentedRefreshToken,
        Set<String> requestedScopes) {

    String fingerprint = tokenFingerprinter.hmac(presentedRefreshToken);
    TokenRecord initial = lineage.findByFingerprint(fingerprint);
    if (initial == null || !initial.belongsTo(client)) {
        return RefreshDecision.invalidGrant();
    }

    // Tất cả đường rotate/revoke đều khóa family theo cùng thứ tự.
    Family family = families.lockById(initial.familyId());
    TokenRecord current = lineage.findById(initial.id()); // Đọc lại dưới khóa.

    if (family.isRevokedOrExpired()) {
        return RefreshDecision.invalidGrant();
    }

    if (current.isConsumed()) {
        families.markRevoked(family.id(), "REFRESH_REUSE");
        lineage.revokeActiveTokensInFamily(family.id());
        audit.recordReuse(family.id(), client.id());  // Không ghi token thô.
        return RefreshDecision.reuseDetected();
    }

    if (!current.isActive() || current.isExpired()) {
        return RefreshDecision.invalidGrant();
    }

    // Hàm giả định này PHẢI bảo toàn toàn bộ kiểm tra grant mặc định.
    grantChecks.verify(client, family, current, requestedScopes);

    IssuedTokens issued = refreshIssuer.issueReplacement(family, current);

    lineage.markConsumed(current.id());
    lineage.insertActiveChild(
            family.id(),
            current.id(),
            tokenFingerprinter.hmac(issued.refreshToken()),
            issued.refreshExpiresAt());
    authorizations.saveConsistentWithFamily(issued.authorization());

    return RefreshDecision.granted(issued);
}

RefreshDecision decision = rotationService.rotateAndPersist(
        authenticatedClient, rawRefreshToken, requestedScopes);

// Bên NGOÀI transaction mới chuyển quyết định thành lỗi OAuth.
if (decision.isRejected()) {
    throw new OAuth2AuthenticationException(
            new OAuth2Error(OAuth2ErrorCodes.INVALID_GRANT));
}
return decision.tokensForResponse();
```

**Điểm tinh tế rất quan trọng:** trong nhiều cấu hình `@Transactional`, nếu vừa `markRevoked(...)` rồi **ném ngay một unchecked exception**, transaction có thể rollback và **hủy luôn thao tác thu hồi family**. Pseudocode vì vậy trả `ReuseDetected` ra khỏi transaction để **commit revocation trước**, rồi adapter HTTP mới ném `OAuth2AuthenticationException` và trả `invalid_grant`. Cũng có thể dùng transaction chuyên trách với semantics commit rõ ràng; cần viết integration test cho nhánh reuse để chứng minh trạng thái `REVOKED` được lưu thật.

Pseudocode không triển khai crypto, token generator, lock, index hay tích hợp SAS đầy đủ, nên không được chép thành production code nếu chưa hoàn thiện các phần đó. Đặc biệt `authorizations.saveConsistentWithFamily` là abstraction **do ứng dụng phải thiết kế** để trạng thái SAS và family registry nhất quán.

### 7.4. Hai request đồng thời dùng cùng R1

```text
Request A: xác thực client -> tìm F42 -> khóa F42
Request B: xác thực client -> tìm F42 -> chờ khóa F42
Request A: thấy R1 ACTIVE -> cấp R2 -> R1 CONSUMED -> commit
Request B: đọc lại R1 -> thấy CONSUMED -> đánh dấu F42 REVOKED -> commit
Request B: trả invalid_grant
```

Theo chính sách bảo thủ, request B tạo **reuse event** và khiến R2 của request A bị thu hồi; kể cả A và B đều xuất phát từ cùng client do retry, server có thể không phân biệt được. Nếu yêu cầu sản phẩm muốn xử lý retry mềm hơn, phải có **cơ chế idempotency gắn với sender/transaction đã xác thực chặt**, không chỉ “chấp nhận R1 thêm 30 giây” bởi cửa sổ ấy có thể cho kẻ tấn công dùng lại token cũ.

Nếu không có lock/CAS và hai request cùng đọc `R1 ACTIVE`, cả hai có thể phát hành token khác nhau. Đây là lỗi nghiêm trọng mà test tuần tự sẽ không phát hiện.

## 8. Lồng ghép vào Spring Authorization Server mà không bỏ kiểm tra mặc định

### 8.1. Vì sao không chỉ thêm một validator đơn giản?

Trong SAS 1.x, refresh grant được xử lý bởi `OAuth2RefreshTokenAuthenticationProvider` với trạng thái trong `OAuth2AuthorizationService`. Một validator gọi sau khi framework đã không tìm được refresh token cũ có thể **không đủ dữ liệu** để biết nó thuộc family nào.

Giải pháp mở rộng thường cần:

- **Kho lineage** giữ fingerprint của refresh token đã dùng và family ID.
- **Điểm xử lý refresh grant** có quyền tra lineage và trạng thái authorization, kiểm soát nguyên tử trước khi cấp token.
- **Điều phối transaction** giữa family registry và `OAuth2AuthorizationService`.
- **Cơ chế phát hành token** dùng `OAuth2TokenGenerator` và chính sách SAS một cách nhất quán.
- **Xử lý revoke** để mọi refresh token còn active thuộc family đều bị từ chối về sau.

Nếu custom provider thay provider chuẩn nhưng chỉ kiểm tra “token có trong registry” rồi tự cấp token, nó có thể bỏ qua client binding, `RegisteredClient`, scope, expiry, authorization state hoặc policy khác. Đó là rủi ro cao hơn bản thân replay.

### 8.2. Chọn điểm mở rộng và thứ tự provider

Ở phong cách cấu hình SAS 1.x, token endpoint có API:

```java
.tokenEndpoint(tokenEndpoint -> tokenEndpoint
    .authenticationProviders(providers -> {
        // Kiểm tra danh sách provider hiện hữu của đúng phiên bản.
        // Với grant refresh_token, thay/bọc provider tương ứng theo
        // thiết kế được review; KHÔNG để hai provider cùng có đường
        // xử lý thành công làm bỏ qua family policy.
    }))
```

Đoạn này là **định vị extension point**, không phải cấu hình runnable hoàn chỉnh. Tùy cách tích hợp, có thể cần wrapper có transaction hoặc thay thế có kiểm soát `OAuth2RefreshTokenAuthenticationProvider` bằng provider dùng service riêng. Đơn thuần **append** một provider vào cuối danh sách có thể không bao giờ được gọi nếu provider mặc định đã xử lý request; còn đặt provider mới đầu danh sách nhưng trả token mà không chạy kiểm tra chuẩn sẽ mở đường bypass.

Một lựa chọn kiến trúc dễ chứng minh tính đúng là đặt family registry **cùng persistence/transaction boundary** với authorization store và bảo đảm logic grant tương đương provider chuẩn. Nếu dùng hai DB hoặc dịch vụ từ xa, phải thiết kế fail-closed, retry/idempotency, outbox/compensation hoặc cơ chế nhất quán khác; không được khẳng định chỉ có `@Transactional` là bảo đảm nguyên tử xuyên hệ thống.

### 8.3. Mối quan hệ với OAuth2Authorization và OAuth2AuthorizationService

Mỗi family cần ánh xạ rõ ràng tới một authorization hoặc một chuỗi authorization theo chính sách. Phải dùng `RegisteredClient.id` nội bộ để liên kết dữ liệu; `client_id` là định danh giao thức ở request.

Khi family bị thu hồi, chỉ xóa fingerprint active khỏi registry **chưa đủ** nếu refresh token vẫn có thể được SAS tìm bằng `OAuth2AuthorizationService` và được một provider khác chấp nhận. Ngược lại, chỉ xóa authorization khỏi SAS nhưng không giữ tombstone token cũ có thể làm mất tín hiệu reuse. **Hai nguồn trạng thái phải thống nhất** và mọi đường refresh phải kiểm tra family status.

### 8.4. Không tự động coi refresh token mới là “an toàn”

Khi phát hiện `R1` reuse, không biết kẻ tấn công hay client hợp lệ hiện giữ `R2`. Bỏ qua sự kiện vì “R2 là token mới” có thể cho bên đã chiếm phiên tiếp tục refresh. Family revocation là cách bảo thủ để chặn cả hai bên, sau đó người dùng phải đăng nhập/ủy quyền lại theo chính sách.

## 9. Family revocation ảnh hưởng tới token nào?

### 9.1. Phân biệt quyền refresh và access token đang được dùng

| Đối tượng | Khi family chuyển `REVOKED` | Cần làm thêm nếu muốn hiệu lực ngay |
| --- | --- | --- |
| **Refresh token active** | Phải bị từ chối tại token endpoint khi dùng lại | Tất cả provider/instance kiểm tra trạng thái family; không có đường vòng |
| **Refresh token đã consumed** | Tiếp tục bị từ chối; có thể ghi nhận replay | Giữ fingerprint/tombstone trong cửa sổ phát hiện |
| **Authorization code** | Không mặc nhiên thuộc refresh token family | Nếu policy là disconnect toàn bộ authorization, thu hồi theo quan hệ authorization phù hợp |
| **Access token JWT self-contained** | Có thể còn được API chấp nhận đến `exp` | TTL ngắn, token denylist/version, introspection hoặc kiểm tra trạng thái qua API theo SLA |
| **Opaque/reference access token** | Có thể bị vô hiệu hóa khi authorization/token state bị cập nhật | Resource Server dùng introspection và cache nhất quán |
| **ID token OIDC** | Không phải refresh token và không phải access token API | Xử lý session, OIDC logout và xác thực ID token theo vai trò riêng |
| **Phiên đăng nhập OP/RP** | Không tự kết thúc chỉ do revoke family | Logout/session revocation riêng nếu yêu cầu |
| **Family khác cùng user/client** | Không nên bị ảnh hưởng mặc định | Chỉ xử lý thêm khi có chính sách toàn tài khoản/thiết bị |

**Thu hồi cả family không đồng nghĩa vô hiệu hóa ngay mọi access token đã ký.** Nếu API chỉ xác minh chữ ký JWT, issuer, audience và expiry thì nó không tự biết `family.status=REVOKED`. Phải phối hợp với Resource Server khi sản phẩm cam kết truy cập bị ngắt tức thời.

### 9.2. Thu hồi bằng token revocation endpoint

RFC 7009 định nghĩa Token Revocation Endpoint, thường là `/oauth2/revoke`, để thu hồi token theo quy tắc client authentication. Nó không tự đặt ra một schema **token family** chung cho mọi triển khai.

Nếu ứng dụng muốn thao tác `revokeFamily(familyId)`, nên triển khai backend quản trị được phân quyền riêng:

1. Xác nhận tác nhân có quyền rút family theo client/user/tenant.
2. Đánh dấu family `REVOKED` với lý do và thời gian.
3. Ngăn refresh theo mọi descendant active.
4. Áp dụng chính sách vô hiệu hóa `OAuth2Authorization`/token hiện hành và phân phối sự kiện tới API khi cần.
5. Ghi audit và phản hồi đúng mức hiệu lực đã đạt.

Không để bất kỳ client nào có thể truyền `familyId` của người khác rồi vô hiệu hóa tùy ý. Việc thu hồi family của chính client cũng phải xác minh client binding.

### 9.3. Khi nào nên rút cả family?

Một policy thường dùng:

- **Có bằng chứng một token `CONSUMED` được trình bày lại** sau khi đã xác minh đúng client/issuer/binding → thu hồi family, log sự kiện rủi ro, yêu cầu authorization mới.
- **Client hoặc user chủ động disconnect** → có thể thu hồi family liên quan theo phạm vi yêu cầu.
- **Phát hiện tài khoản hoặc thiết bị bị chiếm** → cân nhắc thu hồi nhiều family của cùng user/client và yêu cầu xác thực lại.
- **Token hoàn toàn không nhận diện được** → trả `invalid_grant`, rate-limit/observe, nhưng không thể xác định family để thu hồi.
- **Token đã hết hạn nhưng chưa tiêu thụ** → từ chối; quyết định có revoke family hay chỉ dọn trạng thái cần dựa trên threat model.

Tránh dùng duy nhất `client_id` để xóa mọi family: một client có thể được nhiều người dùng sử dụng. Phải ràng buộc `registeredClientId`, principal, issuer/tenant và chính family được xác định tin cậy.

## 10. Timeout, retry và grace period: bài toán khó nhất

### 10.1. Vì sao client hợp lệ có thể gây reuse event?

```text
T0   Client gửi R1.
T1   Server commit R1 -> R2 và trả kết quả.
T2   Mạng mất response, client không biết R2.
T3   Client retry với R1.
T4   Server thấy R1 CONSUMED và thu hồi family.
```

Hệ thống không thể khẳng định đây là tấn công chỉ từ R1. Phương án bảo thủ ưu tiên an ninh có thể buộc người dùng đăng nhập lại. Đây là hành vi cần được **giải thích và kiểm thử**, không phải lỗi có thể giải quyết bằng cách cho phép R1 được đổi vô hạn trong vài giây.

### 10.2. Những lựa chọn thiết kế và đánh đổi

| Lựa chọn | Ưu điểm | Rủi ro / điều kiện |
| --- | --- | --- |
| **Revoke ngay khi reuse** | Dễ chứng minh, giảm nguy cơ attacker giữ descendant | Retry hợp lệ có thể khiến user phải login lại |
| **Cho phép retry qua khóa idempotency ràng buộc an toàn** | Giảm lỗi do mất response | Phải chứng minh cùng sender/transaction; không trả R2 cho caller không đủ bằng chứng |
| **Grace period chấp nhận lại token cũ** | Có thể giảm lỗi retry | Tạo cửa sổ attacker reuse; không phù hợp nếu không có sender binding và mô hình đe dọa rõ |
| **Sender-constraining (DPoP/mTLS)** | Giảm giá trị token bị đánh cắp khi không có khóa | Cần hỗ trợ đầy đủ theo phiên bản, kiểm soát proof/replay và bảo vệ khóa phía client |
| **BFF/server-side token handling** | Giảm lộ token cho JavaScript và kiểm soát refresh tập trung | Tăng trách nhiệm vận hành session/cookie/backend và CSRF |

Nếu chọn grace period, phải tài liệu hóa điều kiện, thời hạn, bằng chứng phân biệt request và cơ chế revoke khi proof khác nhau. **Không được** đơn giản “token cũ còn dùng được trong 30 giây” rồi vẫn tuyên bố đã có reuse detection đáng tin cậy.

### 10.3. Cần kiểm soát duplicate request ở client

Ngoài phía server, client nên có cơ chế **single-flight refresh**: khi nhiều request API cùng thấy access token sắp hết hạn, chỉ một lần refresh đang chạy; các request khác chờ kết quả. Nếu có nhiều tab/process, cần đồng bộ cẩn thận theo mô hình ứng dụng. Tuy nhiên single-flight chỉ giảm lỗi hợp lệ; **không thay thế** single-use enforcement tại Authorization Server.

## 11. Những nguy cơ bảo mật và lỗi triển khai thường gặp

### 11.1. Chỉ bật rotation và gọi đó là reuse detection

Nếu SAS không còn giữ token cũ, `R1` có thể trả `invalid_grant` nhưng hệ thống không biết family F42. Bắt buộc phải có cách lưu fingerprint và mapping lịch sử đủ lâu nếu mục tiêu là phát hiện/revoke theo family.

### 11.2. Khi phát hiện replay thì ném exception làm rollback luôn revoke

Trong transaction, `throw new OAuth2AuthenticationException(...)` sau `family.status=REVOKED` có thể rollback thay đổi. Cần tách commit quyết định revoke khỏi phản hồi lỗi và kiểm thử DB thực tế.

### 11.3. Dùng `findByToken` trên repository mặc định như một lịch sử đầy đủ

`OAuth2AuthorizationService.findByToken` phục vụ tra token theo trạng thái repository; không có cam kết cung cấp lịch sử mọi refresh token từng phát hành. Nếu muốn tìm token cũ, cần index/tombstone riêng phù hợp.

### 11.4. Tự custom provider nhưng bỏ kiểm tra client và scope

Một provider chỉ so fingerprint rồi cấp token có thể bị dùng để refresh bằng client khác, scope cao hơn hoặc authorization bị thu hồi. Bảo toàn toàn bộ kiểm tra refresh grant của SAS hoặc triển khai tương đương có kiểm chứng; ưu tiên extension được hỗ trợ trước khi thay lõi.

### 11.5. Dữ liệu family và OAuth2Authorization ở hai kho không nhất quán

Nếu ghi lineage thành công nhưng `OAuth2AuthorizationService.save` thất bại, client có thể mất refresh token; nếu ngược lại, có thể có token đang active nhưng family registry không nhận diện. Cần transaction chung khi khả thi hoặc cơ chế outbox/compensation và fail-closed được chứng minh bằng test lỗi từng bước.

### 11.6. Xóa tombstone quá sớm

Khi xóa dấu vết `R1` trước khi các descendant hết hạn, replay `R1` sẽ không thể liên kết với family. Thiết kế retention tối thiểu theo cửa sổ phát hiện và thời gian sống family, có giới hạn dữ liệu và chính sách bảo vệ privacy.

### 11.7. Revoke mọi session của user chỉ vì một family bị replay

Có thể tạo tác động diện rộng hoặc denial of service. Phạm vi mặc định nên là family bị ảnh hưởng; mở rộng sang client/user toàn tài khoản dựa trên policy rủi ro riêng.

### 11.8. Ghi raw refresh token vào log hoặc database lịch sử

Token bị lộ qua log/backup sẽ có thể bị lạm dụng nếu còn hạn. Dùng fingerprint cho lookup, mã hóa/bảo vệ token cần lưu theo mô hình SAS, và kiểm soát log/telemetry/backup. Audit chỉ nên ghi family ID, client ID, reason code, timestamp và correlation ID thích hợp.

## 12. Kiểm thử theo máy trạng thái và điều kiện tranh chấp

### 12.1. Ma trận test cơ bản

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| `R1` active, đúng client và còn hạn | Cấp access token mới và `R2`; `R1` chuyển `CONSUMED` |
| Gửi lại `R1` sau refresh thành công | `invalid_grant`; ghi reuse event và revoke F42 theo policy |
| Dùng `R2` sau khi F42 bị revoke | `invalid_grant`, không cấp token mới |
| Gửi token chưa từng tồn tại | `invalid_grant`, không vô cớ revoke family khác |
| Gửi refresh token của client A bằng client B | Từ chối theo client binding, không để client B cố ý revoke family của A |
| Client credential sai | `invalid_client` tại client authentication; không vào đường phát hành token |
| Refresh token đã hết hạn | Từ chối, không tạo token mới |
| Family vượt absolute lifetime | Từ chối dù descendant mới có thời hạn riêng dài hơn |
| Refresh xin scope chưa được cấp/không được phép | `invalid_scope` hoặc lỗi phù hợp, không nâng quyền |
| `reuseRefreshTokens(false)` có hiệu lực | Token trả lần sau khác token lần trước theo chính sách |
| Một user có hai family | Replay family A không mặc định revoke family B |
| Hai user cùng client | Revoke family Alice không tác động family Bob |
| Logout/disconnect có chính sách revoke | Family tương ứng bị chặn và audit đúng |
| JWT access token còn hạn sau family revoke | API xử lý đúng cơ chế revoke đã cam kết; không giả định tự mất hiệu lực |
| Opaque access token sau revoke | Introspection/cache phản ánh trạng thái theo SLA |
| Replay đã được ghi nhưng HTTP trả lỗi | DB vẫn lưu family `REVOKED` sau commit |

### 12.2. Concurrency và retry

| Thử nghiệm | Điều cần chứng minh |
| --- | --- |
| Hai request đồng thời gửi cùng `R1` | Không có hai rotation thành công; trạng thái cuối nhất quán |
| Request B chờ lock của request A | Sau commit A, B nhìn thấy trạng thái mới thay vì snapshot cũ |
| Mất response sau commit rotation | Client retry được xử lý theo chính sách đã công bố, không cấp token thứ hai ngoài kiểm soát |
| Server crash trước commit | Không có token được trả thành công mà DB chưa lưu |
| Server crash sau commit, trước response | Retry không phá vỡ nguyên tắc single-use; recovery theo policy |
| Hai node dùng chung DB | Không có branch độc lập với hai active descendant |
| Lỗi ghi `OAuth2Authorization` sau ghi lineage | Cả transaction rollback hoặc cơ chế bù trừ đưa hệ thống về trạng thái an toàn |
| Reuse event dẫn tới revoke trong transaction | `REVOKED` vẫn được persist dù token endpoint trả `invalid_grant` |
| Race giữa refresh và user disconnect | Sau mốc policy thu hồi có hiệu lực không phát hành refresh token mới |
| Mất kết nối cache hoặc family store | Fail-closed, không cấp refresh token khi không xác minh được trạng thái |

Khi dùng JDBC, thử trên database/dialect sát production với transaction isolation và lock thật. Test in-memory đơn giản hoặc unit test mock repository có thể bỏ sót race condition. Cần kiểm tra cả `OAuth2AuthorizationService` khi phát hành access token và lưu refresh token mới.

### 12.3. Kiểm thử an toàn dữ liệu

- Tìm trong log/APM/audit sau test để đảm bảo không có raw refresh token, secret hoặc full token response.
- Xác nhận fingerprint không cho phép khôi phục token gốc theo thiết kế và khóa HMAC được quản lý riêng.
- Test người dùng A không thể yêu cầu revoke family của người dùng B bằng cách thay family ID.
- Test client bị khóa, grant đã bị tắt hoặc scope bị thu hồi không thể refresh dù fingerprint hợp lệ.
- Test cleanup tombstone không làm mất khả năng phát hiện trong cửa sổ cam kết.
- Test rotation/replay ở môi trường nhiều issuer hoặc tenant không gây nhầm family.

## 13. Observability và quy trình phản ứng sự cố

### 13.1. Mẫu sự kiện audit

```json
{
  "event": "refresh_token_reuse_detected",
  "family_ref": "family-f42",
  "registered_client_id": "internal-client-ref",
  "client_id": "orders-web",
  "reason": "CONSUMED_TOKEN_PRESENTED",
  "action": "FAMILY_REVOKED",
  "correlation_id": "req-8ac4",
  "event_time": "2026-11-16T10:00:00Z"
}
```

Đây là schema audit do ứng dụng định nghĩa, không phải event chuẩn được SAS tự phát trong mọi cấu hình. Không đưa raw refresh token hoặc fingerprint có thể bị lạm dụng ra hệ thống log công khai; trường tham chiếu phải được phân quyền và có retention phù hợp.

### 13.2. Chỉ số giám sát hữu ích

- Tỷ lệ `invalid_grant` của refresh grant theo client và phiên bản ứng dụng.
- Số lần `CONSUMED` token được gửi lại và số family bị revoke.
- Tỷ lệ reuse xuất hiện ngay sau lần refresh đầu, gợi ý network retry/single-flight bug.
- Thời gian chờ lock/transaction, số conflict CAS và lỗi DB.
- Số request refresh bị từ chối do family status, token expiry hoặc client binding.
- Lượng refresh token cũ được giữ làm tombstone và tốc độ dọn theo retention.
- Tỷ lệ người dùng phải đăng nhập lại sau reuse và số sự kiện được xác nhận là compromise.

Một đợt triển khai client bị lỗi retry có thể làm reuse tăng đột biến. Đừng tự động quy kết mọi event là kẻ tấn công hoặc khóa cả tài khoản; cần điều tra correlation, phiên bản client, timestamp và bằng chứng rò rỉ token.

### 13.3. Runbook khi phát hiện reuse

1. **Xác minh sự kiện:** token đã `CONSUMED` thật, thuộc family/client nào, có đồng thời request hợp lệ hoặc lỗi timeout không?
2. **Kiểm tra trạng thái thu hồi:** family đã `REVOKED` và refresh descendant hiện hành bị chặn tại mọi node chưa?
3. **Đánh giá access token đang còn hạn:** Resource Server dùng JWT offline hay introspection; cần denylist/cập nhật state theo SLA không?
4. **Đánh giá mức độ ảnh hưởng:** một family, một thiết bị, một client, một tenant hay nhiều phiên của cùng người dùng?
5. **Thông báo và phục hồi:** theo chính sách, yêu cầu đăng nhập lại, đổi credential client hoặc liên hệ đội hỗ trợ; không đính kèm token trong thông báo.
6. **Điều tra nguyên nhân:** exfiltration qua client/log/proxy, mã độc, retry sau timeout hay bug concurrency.
7. **Kiểm thử lại:** tái hiện replay tuần tự/đồng thời và chứng minh code đã vá không tạo hai active token hoặc rollback revocation.

Nếu yêu cầu thu hồi tức thì nhưng API chỉ xác minh JWT offline và không có state check, hãy công bố rõ giới hạn kỹ thuật thay vì tuyên bố đã ngắt toàn bộ access token ngay.

## 14. Bài tập tình huống thiết kế

Một Authorization Server phục vụ hai client:

```text
Client: orders-web
  Grant: authorization_code + refresh_token
  reuseRefreshTokens: false
  Access token TTL: 10 phút
  Refresh token TTL: 7 ngày

Family F-A (Alice trên laptop)
  R1: CONSUMED
  R2: CONSUMED
  R3: ACTIVE

Family F-B (Alice trên điện thoại)
  R4: ACTIVE
```

Hệ thống nhận hai request:

- **Request X:** `R1` được gửi lại, client authentication hợp lệ.
- **Request Y:** `R3` đang được dùng để refresh gần cùng thời điểm.

Giả sử API đơn hàng dùng JWT offline và access token hiện tại còn hạn 8 phút.

Hãy trả lời:

1. Tại sao chỉ dùng `OAuth2AuthorizationService.findByToken(R1, REFRESH_TOKEN)` có thể không đủ để xác định `R1` thuộc family F-A?
2. Sau khi thấy R1 đã `CONSUMED`, cần khóa family ở đâu và xử lý request Y thế nào để không cấp descendant mới ngoài kiểm soát?
3. Có nên thu hồi F-B của Alice ngay không? Nếu muốn thu hồi cả hai family, cần chính sách gì?
4. JWT access token còn hạn có tự bị từ chối ở API khi F-A bị revoke không?
5. Nếu request X thật ra là retry sau timeout của client hợp lệ, làm thế nào phân biệt được với kẻ tấn công? Đánh đổi khi revoke ngay là gì?
6. Tại sao ném `OAuth2AuthenticationException` ngay trong transaction sau khi cập nhật F-A có thể khiến revocation mất hiệu lực?
7. Thiết kế ít nhất sáu test: token cũ, client khác, hai refresh song song, retry sau timeout, JWT offline sau revoke và restart giữa commit/response.

**Gợi ý đáp án:** cần một registry giữ fingerprint/token lineage để tìm F-A; dùng lock/CAS và transaction bảo đảm sau reuse F-A bị revoke và Y không thể thành công sau mốc thu hồi có hiệu lực. F-B là family riêng, chỉ revoke thêm theo chính sách bảo vệ tài khoản. JWT offline vẫn có thể hợp lệ đến `exp` nếu không có denylist/state check. Retry và đánh cắp token có thể giống nhau, nên dùng cơ chế idempotency/sender binding chặt nếu muốn giảm false positive; phải đảm bảo commit revoke rồi mới tạo lỗi OAuth.

## 15. Checklist triển khai production

1. **Đúng mục tiêu:** phân biệt rotation, single-use, reuse detection, family revocation và SLA thu hồi access token.
2. **Client:** xác thực client, grant, scope, redirect/consent và chính sách token vẫn theo SAS; không thay provider chuẩn bằng logic thiếu validation.
3. **Rotation:** bật `reuseRefreshTokens(false)` khi phù hợp và kiểm chứng hành vi trên đúng phiên bản/persistence.
4. **Lineage:** mỗi family có ID ổn định, token cũ có fingerprint/tombstone và parent relationship; không lưu raw token trong log/index lịch sử.
5. **Atomicity:** chỉ một active descendant; sử dụng transaction + lock/CAS, kiểm thử nhiều node và bảo đảm revocation được commit trước khi trả `invalid_grant`.
6. **Policy:** quyết định khi nào revoke family, khi nào block user/client, xử lý unknown/expired token và retry hợp lệ.
7. **Access token:** xác định JWT/opaque, introspection cache và thời gian hiệu lực thực tế sau revoke.
8. **Kho dữ liệu:** có retention, index, backup, HMAC key management, transaction và cleanup token lịch sử.
9. **Ứng dụng client:** single-flight refresh, bảo vệ credential, không retry mù với refresh token cũ, có đường reauthorization an toàn.
10. **Kiểm thử:** replay tuần tự/đồng thời, double-submit, failover, crash, mất response, DB lỗi và race với logout/disconnect.
11. **Vận hành:** audit tối thiểu, cảnh báo reuse, runbook cho cả compromise và false positive, không rò token.

## 16. Tài liệu tham khảo

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, `OAuth2AuthorizationService`, `TokenSettings`.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): token endpoint, refresh grant và điểm mở rộng provider.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `AuthenticationManager`, `AuthenticationProvider` và phân tách trách nhiệm.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Refresh Token Grant, xác thực client và ràng buộc scope.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, replay detection, rotation và sender-constraining.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): các hành vi thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái token và Resource Server.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token theo profile DPoP.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc certificate và xác thực client, cần kiểm tra mức hỗ trợ thực tế của stack.

**Ghi nhớ:** `reuseRefreshTokens(false)` là bước quan trọng để xoay refresh token, nhưng **phát hiện token cũ được tái sử dụng và thu hồi cả token family là một bài toán trạng thái, giao dịch và chính sách riêng**. Muốn làm đúng, cần lưu dấu vết token đã tiêu thụ, liên kết đúng family/client/principal, cập nhật nguyên tử khi rotation hoặc revoke, xử lý retry thận trọng và kiểm chứng tác động ở Resource Server. Không có một cờ cấu hình duy nhất thay thế được thiết kế, kiểm thử và vận hành này.
