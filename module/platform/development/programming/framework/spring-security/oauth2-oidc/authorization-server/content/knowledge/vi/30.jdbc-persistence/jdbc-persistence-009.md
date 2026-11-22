# Index, truy vấn theo token và tác động của kích thước dữ liệu

## 1. Bối cảnh và mục tiêu

Trong **OAuth 2.0/OpenID Connect Authorization Server** dùng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, nhiều luồng cấp, xác minh, introspection và thu hồi token đều cần tìm một bản ghi authorization đã lưu. Khi số client, người dùng và token tăng lên, chi phí truy vấn trong bảng authorization có thể trở thành một phần đáng kể của độ trễ Token Endpoint, Introspection Endpoint hoặc Revocation Endpoint.

Một Authorization Server có thể lưu nhiều loại giá trị trong cùng một bản ghi: authorization code, access token, refresh token, ID Token, user code, device code và state. Mỗi loại có thời hạn, metadata và tần suất tra cứu khác nhau. Bản ghi còn chứa principal, RegisteredClient ID, scopes, attributes, claims và metadata được serialize. Vì vậy, hiệu năng phụ thuộc vào cả **cách tìm đúng hàng** lẫn **lượng dữ liệu phải đọc/ghi sau khi tìm được hàng**.

Ví dụ xuyên suốt: hệ thống tại `identity.example.com` cấp access token cho hàng trăm ứng dụng nội bộ. Resource Server gọi introspection thường xuyên; một số client dùng opaque token, một số dùng JWT. Khi revoke refresh token, Authorization Server phải tìm authorization chứa token đó, đánh dấu token invalidated và lưu lại. Ban đầu bảng chỉ có vài nghìn hàng; sau một năm đã có hàng chục triệu hàng. Nếu mỗi lần tìm token phải quét bảng hoặc đọc các LOB lớn, độ trễ và I/O sẽ tăng nhanh.

Sau bài học, bạn có thể:

1. Hiểu cấu trúc bảng `oauth2_authorization` và các cột được dùng để tra cứu token.
2. Giải thích `JdbcOAuth2AuthorizationService.findByToken(token, tokenType)` tạo điều kiện SQL như thế nào.
3. Phân biệt truy vấn theo token type cụ thể với truy vấn không biết token type.
4. Thiết kế index phù hợp với kiểu dữ liệu và workload của database.
5. Hiểu vì sao cột BLOB/CLOB hoặc token quá dài làm việc index trực tiếp khó khăn.
6. Thiết kế token lookup table dùng HMAC digest khi index token value trực tiếp không phù hợp.
7. Đánh giá ảnh hưởng của attributes, claims, metadata và số lượng token lên kích thước hàng.
8. Tối ưu truy vấn consent, truy vấn theo client/principal và công việc dọn authorization hết hạn.
9. Đọc execution plan, đo latency và benchmark trước/sau khi thêm index.
10. Nhận biết khi nào cần thay `JdbcOAuth2AuthorizationService` bằng implementation chuyên biệt.

**Phạm vi phiên bản:** Nội dung tham chiếu Spring Authorization Server **1.5.8** và Spring Security 6.x. Tên bảng/cột và schema phải được đối chiếu với đúng SQL resource đi kèm dependency đang chạy. Ví dụ SQL trong bài dùng PostgreSQL khi ghi rõ `bytea`/`timestamptz`; hệ quản trị khác cần điều chỉnh kiểu dữ liệu và cú pháp.

## 2. Mô hình dữ liệu authorization

### 2.1. OAuth2Authorization chứa nhiều token và metadata

`OAuth2Authorization` không chỉ là một hàng chứa access token. Domain object gồm các thành phần chính:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `id` | ID duy nhất của authorization. | `auth-7f32...` |
| `registeredClientId` | ID nội bộ của RegisteredClient. | `client-record-001` |
| `principalName` | Principal của resource owner hoặc client. | `alice` hoặc `batch-worker` |
| `authorizationGrantType` | Grant type đã tạo authorization. | `authorization_code`, `client_credentials` |
| `authorizedScopes` | Scope được chấp thuận. | `openid`, `profile`, `orders.read` |
| `attributes` | Dữ liệu bổ sung theo flow. | Principal, authorization request, nonce, state và dữ liệu khác |
| `tokens` | Các token và metadata tương ứng. | Authorization Code, Access Token, Refresh Token, ID Token, Device Code |

Một authorization có thể chứa nhiều token trong vòng đời của nó. Ví dụ Authorization Code Flow ban đầu lưu authorization code, sau đó được cập nhật để lưu access token, refresh token và ID Token. Khi refresh, cùng bản ghi có thể được cập nhật thêm token mới hoặc metadata invalidation.

### 2.2. Bảng oauth2_authorization

`JdbcOAuth2AuthorizationService` phụ thuộc vào schema resource `oauth2-authorization-schema.sql`. DDL mặc định dùng cấu trúc **flattened**: các token và metadata được trải thành nhiều cột trong một bảng thay vì tách thành một bảng token riêng.

Các cột quan trọng:

| Nhóm | Cột tiêu biểu | Mục đích |
| --- | --- | --- |
| Khóa và chủ thể | `id`, `registered_client_id`, `principal_name` | Định danh authorization, client và principal. |
| Flow | `authorization_grant_type`, `authorized_scopes` | Grant type và scope. |
| Attributes | `attributes` | JSON/serialized data bổ sung. |
| State | `state` | OAuth state dùng trong authorization flow. |
| Authorization Code | `authorization_code_value`, `authorization_code_issued_at`, `authorization_code_expires_at`, `authorization_code_metadata` | Tra cứu code và trạng thái code. |
| Access Token | `access_token_value`, `access_token_issued_at`, `access_token_expires_at`, `access_token_metadata`, `access_token_type`, `access_token_scopes` | Tra cứu access token, loại token, scopes và metadata. |
| Refresh Token | `refresh_token_value`, `refresh_token_issued_at`, `refresh_token_expires_at`, `refresh_token_metadata` | Tra cứu và quản lý refresh token. |
| OIDC ID Token | `oidc_id_token_value`, `oidc_id_token_issued_at`, `oidc_id_token_expires_at`, `oidc_id_token_metadata` | Lưu ID Token và metadata/claims. |
| Device Authorization | `user_code_value`, `device_code_value` cùng issued/expires/metadata | Tra cứu user code và device code. |

Schema đi kèm Spring Authorization Server dùng `BLOB` cho nhiều cột token value và metadata; ví dụ PostgreSQL cần thay kiểu `BLOB` bằng kiểu văn bản phù hợp theo hướng dẫn của schema. Kiểu dữ liệu thực tế phụ thuộc database và bản migration của ứng dụng.

DDL mặc định tạo primary key trên `id`. Các index phụ cho tra cứu token không được khai báo sẵn trong schema authorization mặc định. Vì vậy, ứng dụng có thể cần thiết kế index theo database và workload thực tế.

### 2.3. Bảng consent

`oauth2_authorization_consent` lưu quyền mà người dùng đã chấp thuận cho client:

~~~sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    authorities varchar(1000) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);
~~~

Primary key ghép `(registered_client_id, principal_name)` hỗ trợ tìm consent theo đúng cặp client và user. Vì thứ tự cột của composite index quan trọng, index này cũng phù hợp với truy vấn chỉ lọc theo `registered_client_id` ở vị trí đầu; nó không tối ưu tương đương cho truy vấn chỉ lọc theo `principal_name`.

## 3. JdbcOAuth2AuthorizationService truy vấn theo token

### 3.1. findById

`findById(id)` sử dụng điều kiện:

~~~sql
SELECT ...
FROM oauth2_authorization
WHERE id = ?;
~~~

Đây là truy vấn dùng primary key nên thường có access path tốt. `save(authorization)` của implementation mặc định kiểm tra authorization đã tồn tại bằng `findById` rồi mới insert hoặc update. Vì vậy, đường ghi có thể gồm một lần đọc theo PK cộng với một câu INSERT/UPDATE.

### 3.2. findByToken với token type đã biết

API:

~~~java
OAuth2Authorization findByToken(
    String token,
    OAuth2TokenType tokenType
);
~~~

Khi caller biết token type, implementation chọn một filter cụ thể:

| Token type | Cột được so sánh |
| --- | --- |
| `state` | `state` |
| `code` | `authorization_code_value` |
| Access Token | `access_token_value` |
| ID Token | `oidc_id_token_value` |
| Refresh Token | `refresh_token_value` |
| User Code | `user_code_value` |
| Device Code | `device_code_value` |

Ví dụ truy vấn access token về mặt logic:

~~~sql
SELECT <authorization-columns>
FROM oauth2_authorization
WHERE access_token_value = ?;
~~~

Truy vấn này có một điều kiện equality trên một cột. Nếu database có index phù hợp và kiểu dữ liệu cho phép index equality toàn bộ giá trị, optimizer có thể tìm hàng mà không cần quét toàn bảng.

### 3.3. findByToken với tokenType null

Khi `tokenType` là `null`, service phải tìm giá trị token trong mọi loại mà implementation hỗ trợ. Điều kiện tương đương:

~~~sql
SELECT <authorization-columns>
FROM oauth2_authorization
WHERE state = ?
   OR authorization_code_value = ?
   OR access_token_value = ?
   OR oidc_id_token_value = ?
   OR refresh_token_value = ?
   OR user_code_value = ?
   OR device_code_value = ?;
~~~

Đây là điểm khác biệt hiệu năng quan trọng. Database có thể:

- Kết hợp nhiều index bằng bitmap/index-merge nếu các cột có index phù hợp.
- Chọn một access path không tối ưu nếu thống kê không chính xác.
- Thực hiện full table scan nếu không có index hữu dụng hoặc kiểu cột không hỗ trợ index.

Không nên giả định `OR` luôn gây full scan; query planner phụ thuộc database, cardinality, statistics và kiểu cột. Tuy nhiên, truy vấn không chỉ định token type có nhiều nhánh hơn và thường khó tối ưu hơn truy vấn equality trên một cột.

### 3.4. Khi nào token type có thể không biết?

Một số protocol endpoint nhận token từ request nhưng chưa biết đó là token loại nào. `findByToken(token, null)` cung cấp semantics tìm trên các loại được hỗ trợ. Nếu custom implementation thay đổi cách tra cứu, phải giữ đúng semantics đó; không được chỉ tra access token rồi bỏ sót refresh token, authorization code, user code hoặc device code.

Khi caller biết token type từ protocol context, truyền đúng type giúp service dùng filter cụ thể. Không tự đoán type dựa trên hình dạng chuỗi token hoặc prefix không được protocol quy định.

### 3.5. SELECT lấy toàn bộ authorization row

`JdbcOAuth2AuthorizationService` không chỉ select ID khi tìm token. Nó load các cột của authorization rồi dùng RowMapper để dựng lại `OAuth2Authorization`, bao gồm token values, metadata, attributes và các thông tin liên quan.

Do đó, index giúp tìm đúng hàng nhanh hơn nhưng không loại bỏ chi phí:

- Đọc các cột LOB/BLOB/CLOB.
- Chuyển đổi byte/text.
- Deserialize JSON metadata và attributes.
- Dựng các đối tượng token và claims.
- Tra cứu RegisteredClient liên quan.

Khi một authorization row chứa nhiều token và metadata lớn, thời gian đọc/mapping có thể đáng kể ngay cả khi index lookup đã nhanh.

## 4. Vì sao schema mặc định chưa đủ cho high throughput?

### 4.1. Schema tối giản ưu tiên tính tương thích

Schema mặc định phải hoạt động trên nhiều hệ quản trị quan hệ và hỗ trợ nhiều loại grant. Vì vậy, nó cung cấp một cấu trúc flattened có PK trên authorization ID và nhiều cột token/metadata, nhưng không thể tối ưu sẵn cho mọi workload.

Javadoc của `JdbcOAuth2AuthorizationService` mô tả đây là simplified JDBC implementation. Nó có thể dùng trong production, nhưng có thể không đạt hiệu năng trong môi trường throughput cao; ứng dụng được kỳ vọng cung cấp implementation `OAuth2AuthorizationService` riêng nếu yêu cầu hiệu năng của deployment cần điều đó.

### 4.2. Index cần khớp predicate thật

Một index chỉ hữu ích nếu câu SQL có predicate mà index hỗ trợ. Ví dụ:

- Index `access_token_value` hỗ trợ `WHERE access_token_value = ?`.
- Index `refresh_token_value` không tự tối ưu `WHERE access_token_value = ?`.
- Composite index `(registered_client_id, principal_name)` không thay thế index trên token value.
- Index trên `access_token_expires_at` hữu ích cho truy vấn cleanup theo expiry, nhưng không trực tiếp tăng tốc `findByToken`.

Trước khi tạo index, hãy liệt kê các truy vấn thực tế và tần suất gọi của chúng.

### 4.3. Index làm tăng chi phí ghi

Mỗi index phụ phải được cập nhật khi hàng được INSERT, UPDATE hoặc DELETE. `save(authorization)` có thể cập nhật nhiều cột trong một hàng; thêm nhiều index làm tăng:

- Số page/index cần ghi.
- WAL/redo log và replication traffic.
- Dung lượng lưu trữ.
- Chi phí vacuum/maintenance tùy database.
- Khả năng phân mảnh và áp lực cache.

Không tạo index cho mọi cột chỉ vì chúng có thể xuất hiện trong một câu query hiếm. Index phải có lợi ích đọc lớn hơn chi phí ghi và vận hành.

## 5. Thiết kế index cho truy vấn token

### 5.1. Trường hợp cột token là VARCHAR có thể index trực tiếp

Nếu schema tùy chỉnh dùng kiểu chuỗi có giới hạn và database có thể tạo index equality trên toàn bộ giá trị, có thể cân nhắc:

~~~sql
CREATE INDEX idx_oauth2_auth_access_token
    ON oauth2_authorization (access_token_value);

CREATE INDEX idx_oauth2_auth_refresh_token
    ON oauth2_authorization (refresh_token_value);

CREATE INDEX idx_oauth2_auth_code
    ON oauth2_authorization (authorization_code_value);

CREATE INDEX idx_oauth2_auth_id_token
    ON oauth2_authorization (oidc_id_token_value);

CREATE INDEX idx_oauth2_auth_user_code
    ON oauth2_authorization (user_code_value);

CREATE INDEX idx_oauth2_auth_device_code
    ON oauth2_authorization (device_code_value);
~~~

Đây là ví dụ cho schema có cột indexable, không phải migration có thể áp dụng trực tiếp lên DDL mặc định đang dùng BLOB. Phải kiểm tra giới hạn độ dài index, encoding, collation, row size và khả năng index kiểu dữ liệu của database.

### 5.2. Vì sao không nên index trực tiếp BLOB/CLOB?

BLOB/CLOB được thiết kế cho dữ liệu lớn. Nhiều database không hỗ trợ B-tree index thông thường trên toàn bộ LOB; một số database chỉ cho phép function-based index, prefix index hoặc index theo giới hạn cụ thể. Prefix index không bảo đảm equality chính xác nếu nhiều token có cùng prefix.

Ngay cả khi database cho phép index trên VARCHAR dài, index toàn bộ JWT/token có thể:

- Tạo index rất lớn.
- Chạm giới hạn kích thước index entry.
- Tăng chi phí INSERT/UPDATE.
- Tốn buffer cache.
- Lưu raw bearer token trong index pages, backup và snapshot.

Vì vậy, index token value trực tiếp chỉ phù hợp khi kiểu cột, độ dài token và database đã được kiểm chứng. Với token dài hoặc LOB, nên cân nhắc lookup key có kích thước cố định.

### 5.3. Không dùng prefix index như thể là exact index

Ví dụ một database hỗ trợ index prefix:

~~~sql
-- Minh họa ý tưởng, cú pháp phụ thuộc database.
CREATE INDEX idx_access_token_prefix
    ON oauth2_authorization (access_token_value(128));
~~~

Index prefix có thể giúp lọc sơ bộ nhưng nhiều token có thể chung prefix. Database vẫn cần kiểm tra phần còn lại; optimizer có thể không dùng index nếu selectivity thấp hoặc predicate không tương thích. Không cắt token khi so sánh, không dùng prefix làm định danh token và không bỏ bước xác minh toàn bộ giá trị.

### 5.4. Hash digest với kích thước cố định

Một cách phổ biến là tạo digest từ token rồi index digest thay vì index toàn chuỗi. Digest SHA-256 có kích thước cố định 32 byte; HMAC-SHA-256 cũng có kích thước 32 byte.

Nếu chỉ lưu một cột `token_hash` bên cạnh token value, cần nhớ rằng **JdbcOAuth2AuthorizationService mặc định vẫn truy vấn cột token value**. Thêm hash column hoặc index hash không làm câu SQL mặc định tự chuyển sang digest.

Để dùng hash index, phải:

1. Thay đổi mapper/write path để tạo digest khi lưu token.
2. Duy trì digest khi update, rotate hoặc remove authorization.
3. Thay đổi `findByToken` để tính digest của token được gửi lên.
4. Truy vấn bằng digest và lấy authorization ID.
5. Load authorization tương ứng và giữ semantics của `OAuth2AuthorizationService`.
6. Đồng bộ dữ liệu hash với token value trong cùng transaction.

### 5.5. Dùng HMAC thay cho plain hash khi token có entropy thấp

Authorization code, access token và refresh token thường có entropy cao, nhưng user code/device code hoặc một số identifier ngắn có thể có không gian giá trị nhỏ hơn. Nếu lưu plain SHA-256 của giá trị ngắn, người có quyền đọc database có thể thử brute force offline.

Với lookup index, cân nhắc HMAC-SHA-256 bằng secret key do ứng dụng quản lý ngoài database:

~~~java
byte[] tokenDigest(
        SecretKey lookupKey,
        String tokenType,
        String token) throws GeneralSecurityException {

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(lookupKey);
    mac.update(tokenType.getBytes(StandardCharsets.UTF_8));
    mac.update((byte) 0);
    return mac.doFinal(token.getBytes(StandardCharsets.UTF_8));
}
~~~

Việc đưa `tokenType` vào input tạo domain separation: cùng chuỗi token ở hai loại khác nhau tạo digest khác nhau. Secret key phải được giữ trong KMS/secret manager, không lưu cùng database hoặc log.

HMAC lookup không thay thế kiểm tra token protocol, expiry, invalidation hoặc client binding. Nó chỉ giúp tìm hàng bằng một giá trị indexable.

### 5.6. Token lookup side table

Khi cần tra cứu nhanh nhiều loại token, có thể tách ánh xạ token → authorization ID thành bảng riêng. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE oauth2_authorization_token_lookup (
    token_type varchar(32) NOT NULL,
    token_hash bytea NOT NULL,
    authorization_id varchar(100) NOT NULL,
    expires_at timestamptz,
    PRIMARY KEY (token_type, token_hash),
    FOREIGN KEY (authorization_id)
        REFERENCES oauth2_authorization(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_oauth2_token_lookup_authorization
    ON oauth2_authorization_token_lookup (authorization_id);

CREATE INDEX idx_oauth2_token_lookup_expiry
    ON oauth2_authorization_token_lookup (expires_at);
~~~

Bảng lookup giữ digest cố định, token type và authorization ID. Primary key `(token_type, token_hash)` hỗ trợ equality lookup. Index `authorization_id` giúp tìm/xóa các mapping khi authorization bị xóa. Index expiry chỉ cần nếu có job cleanup theo thời gian; không tạo nếu không có truy vấn sử dụng.

Các giá trị `token_type` nên dùng một tập mã ổn định, ví dụ `access_token`, `refresh_token`, `authorization_code`, `oidc_id_token`, `user_code`, `device_code`, `state`.

Luồng tra cứu:

~~~mermaid
sequenceDiagram
    autonumber
    participant E as Introspection / Revocation
    participant S as Custom OAuth2AuthorizationService
    participant L as Token Lookup Table
    participant A as oauth2_authorization
    E->>S: findByToken(token, tokenType)
    S->>S: HMAC-SHA-256(tokenType, token)
    S->>L: SELECT authorization_id WHERE type + digest
    L-->>S: authorization_id
    S->>A: SELECT authorization WHERE id = ?
    A-->>S: Authorization row
    S-->>E: OAuth2Authorization
~~~

Nếu `tokenType` là `null`, custom service phải giữ semantics tìm trên mọi loại mà implementation hỗ trợ. Có thể tính digest cho từng token type rồi truy vấn theo tập cặp `(token_type, token_hash)`. Không được chỉ tra một loại token và trả `null` khi token thuộc loại khác.

### 5.7. Giới hạn và trade-off của lookup table

Lookup table tăng thêm một lần ghi mapping cho mỗi token, thêm storage và cần transaction nhất quán. Khi save/update authorization, custom service phải cập nhật cả authorization row và các lookup rows trong cùng transaction. Khi remove authorization, phải xóa mapping tương ứng hoặc dùng foreign key cascade phù hợp.

Hash side table **không tự xóa raw token khỏi bảng authorization**. Nếu mục tiêu là giảm lộ token trong database, cần thiết kế persistence model chỉ lưu digest và tái tạo token object từ request/metadata theo yêu cầu của protocol. Đó là một thay đổi lớn đối với mapper/service và phải kiểm thử mọi flow, bao gồm introspection, revocation, refresh, device flow và OIDC.

Nếu HMAC key được rotate, phải hỗ trợ versioning hoặc quy trình tính lại digest. Ví dụ thêm `hash_key_version` vào lookup table, dual-write trong giai đoạn chuyển tiếp, backfill digest mới rồi chuyển read path và retire key cũ. Mất HMAC key đồng nghĩa không thể tính digest để tra cứu các mapping được tạo bằng key đó.

## 6. Index cho các truy vấn ngoài token lookup

### 6.1. Theo RegisteredClient và principal

Một số hệ thống có dashboard hoặc tác vụ quản trị tìm authorization theo client/principal:

~~~sql
CREATE INDEX idx_oauth2_auth_client_principal
    ON oauth2_authorization (registered_client_id, principal_name);
~~~

Index này có thể hữu ích cho truy vấn:

~~~sql
SELECT id, authorization_grant_type
FROM oauth2_authorization
WHERE registered_client_id = ?
  AND principal_name = ?;
~~~

Nó không giúp `findByToken` mặc định vì truy vấn token không lọc theo hai cột đó. Chỉ tạo khi ứng dụng thực sự có query pattern tương ứng.

Nếu workload chủ yếu truy vấn theo `principal_name` mà không có `registered_client_id`, composite index bắt đầu bằng `registered_client_id` có thể không phù hợp. Khi đó cân nhắc index riêng theo principal sau khi xem execution plan.

### 6.2. Consent composite key

Primary key `(registered_client_id, principal_name)` của bảng consent hỗ trợ:

- Tìm consent theo cả client và principal.
- Tìm các consent theo client khi predicate dùng cột đầu.
- Xóa consent theo cặp khóa.

Nếu có trang quản trị liệt kê tất cả client đã cấp quyền cho một principal, truy vấn theo `principal_name` có thể cần index riêng:

~~~sql
CREATE INDEX idx_oauth2_consent_principal
    ON oauth2_authorization_consent (principal_name);
~~~

Không cần tạo index này nếu ứng dụng không có truy vấn như vậy.

### 6.3. Cleanup theo expiry

Job cleanup có thể cần tìm authorization đã hết hạn. Bảng có các cột như:

- `authorization_code_expires_at`
- `access_token_expires_at`
- `refresh_token_expires_at`
- `oidc_id_token_expires_at`
- `user_code_expires_at`
- `device_code_expires_at`

Nếu cleanup query lọc độc lập theo từng expiry column, index riêng có thể hỗ trợ:

~~~sql
CREATE INDEX idx_oauth2_auth_access_expiry
    ON oauth2_authorization (access_token_expires_at);

CREATE INDEX idx_oauth2_auth_refresh_expiry
    ON oauth2_authorization (refresh_token_expires_at);
~~~

Đây là ví dụ cho job cleanup có predicate tương ứng. Không tạo index tất cả expiry columns một cách máy móc; hãy xem job thực tế và tần suất.

### 6.4. Không xóa authorization chỉ vì access token hết hạn

Một authorization row có thể chứa refresh token còn hạn, device/user code chưa hết hạn hoặc metadata cần giữ cho audit. Nếu access token hết hạn nhưng refresh token vẫn hợp lệ, xóa toàn bộ row sẽ phá refresh flow.

Job cleanup phải đánh giá trạng thái của **mọi token và authorization liên quan**, bao gồm invalidated metadata và retention/audit policy. Tác vụ xóa nên chạy theo batch, có giới hạn số hàng và không giữ transaction quá lâu.

## 7. Kích thước dữ liệu ảnh hưởng hiệu năng thế nào?

### 7.1. Token dài làm row và LOB lớn

JWT có thể dài hơn opaque token vì chứa header, claims và chữ ký. ID Token có thể mang nhiều claims; access token JWT có thể mang role, tenant, permission hoặc custom claims. Nếu lưu raw token trong LOB, token càng dài thì dung lượng row càng tăng.

Kích thước không chỉ đến từ token value:

- `attributes` có thể chứa authorization request, principal hoặc dữ liệu bổ sung.
- Token metadata chứa issued/expiry, invalidated flag và claims.
- OIDC ID Token claims có thể được serialize trong metadata.
- Scopes/authorities có thể tăng theo client.
- Một authorization row có thể chứa nhiều token cùng lúc.

### 7.2. Row lớn làm tăng chi phí đọc

Khi `findByToken` tìm thấy một hàng, RowMapper cần đọc các cột liên quan và dựng lại domain object. Nếu attributes/metadata/token values rất lớn:

- Database có thể phải đọc thêm LOB pages.
- Network truyền nhiều bytes hơn từ database tới application.
- JDBC driver phải cấp buffer/stream cho dữ liệu lớn.
- JSON deserialization tốn CPU và allocation.
- Garbage collection chịu áp lực khi nhiều request đồng thời.

Index giúp giảm số hàng cần tìm, nhưng không làm cho hàng được tìm thấy nhỏ hơn. Đây là lý do một truy vấn đã dùng index vẫn có thể chậm nếu payload authorization lớn.

### 7.3. Row rộng và cache locality

Một bảng có nhiều cột token/metadata thường tạo row rộng. Dữ liệu LOB có thể được lưu ngoài page chính tùy database, nhưng vẫn tạo thêm pointer, page access và I/O. Khi working set lớn hơn buffer pool, database phải đọc nhiều page từ storage.

Index cũng chiếm buffer cache. Nếu index token rất lớn, một phần cache vốn dành cho data pages sẽ bị dùng cho index pages. Vì vậy, index digest cố định thường nhỏ hơn nhiều so với index raw JWT/token.

### 7.4. Kích thước metadata có thể tăng ngoài dự kiến

Không nên lưu toàn bộ hồ sơ người dùng, danh sách quyền rất lớn hoặc object request không cần thiết trong `attributes`. Thay vào đó:

- Chỉ lưu dữ liệu cần thiết để tiếp tục protocol flow.
- Dùng stable user ID thay vì serialize toàn bộ profile.
- Giữ claim trong ID Token/access token ở mức tối thiểu theo audience và scope.
- Đặt giới hạn kích thước request/claims/attributes.
- Tách dữ liệu audit hoặc dữ liệu nghiệp vụ lớn sang store phù hợp.

Không bỏ metadata bắt buộc để giảm row size. Ví dụ invalidation metadata và claims cần cho OIDC/token processing phải được giữ theo semantics của service.

### 7.5. Serialization và LOB handling

`JdbcOAuth2AuthorizationService` dùng mapper để chuyển `OAuth2Authorization` thành SQL parameters và RowMapper để tái tạo object. Các cột LOB được xử lý thông qua `LobHandler`. Với schema dùng `BLOB`, dữ liệu text có thể được chuyển thành bytes; với `CLOB`/text, cách bind/read khác nhau.

Schema phải phù hợp database:

- PostgreSQL không có kiểu `BLOB`; cần dùng kiểu text/bytea thích hợp theo nội dung và resource SQL.
- Database có giới hạn row/index size cần chọn VARCHAR/LOB phù hợp.
- Cần kiểm tra timestamp timezone/instant semantics theo JDBC driver và DB.
- Fixed-length JSON columns có thể không đủ cho attributes hoặc metadata dài.

Không thay kiểu dữ liệu tùy ý mà không kiểm thử mapper, LobHandler và schema migration.

## 8. Tối ưu đường ghi và cập nhật authorization

### 8.1. save có thể đọc trước khi ghi

Implementation mặc định kiểm tra `findById(authorization.getId())` để quyết định insert hay update. Điều này tạo một lượt đọc bổ sung trên đường save. Khi authorization flow có nhiều lần update, chi phí đọc/ghi sẽ tăng theo số lần cập nhật.

### 8.2. UPDATE ghi nhiều cột

Update SQL mặc định cập nhật các nhóm cột authorization, token value, issued/expires time và metadata. Khi một row có nhiều LOB, update có thể serialize và bind nhiều dữ liệu ngay cả khi thay đổi nghiệp vụ chỉ liên quan một phần.

Không tối ưu bằng cách bỏ các cột mà mapper cần. Nếu write amplification trở thành bottleneck, cân nhắc custom service/schema có thể cập nhật đúng phần thay đổi hoặc tách token records theo mô hình riêng, nhưng phải bảo đảm transaction và object semantics.

### 8.3. Index làm tăng write amplification

Khi thêm index trên token values, expiry, client/principal và lookup side table, mỗi lần phát hành/refresh/revoke phải duy trì các index đó. Đo cả read throughput và write throughput; không tối ưu introspection bằng cách làm Token Endpoint hoặc refresh flow chậm hơn mức chấp nhận được.

## 9. Đọc execution plan và đo hiệu năng

### 9.1. Bắt đầu từ truy vấn thật

Trước khi tạo index:

1. Xác định endpoint/flow phát sinh query.
2. Thu thập SQL thực tế và bind type.
3. Đo tần suất, hit/miss ratio và độ dài token.
4. Xác định query có truyền token type hay `null`.
5. Xem row count và phân bố dữ liệu.
6. Lấy execution plan trên dữ liệu có quy mô gần production.

Không tối ưu dựa trên một bảng dev chỉ có vài trăm authorization.

### 9.2. PostgreSQL EXPLAIN

Với schema tùy chỉnh có cột token indexable, ví dụ:

~~~sql
PREPARE find_access_token(varchar) AS
SELECT id
FROM oauth2_authorization
WHERE access_token_value = $1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_access_token('example-token-value');

DEALLOCATE find_access_token;
~~~

Kiểm tra:

- Planner chọn Index Scan/Bitmap Index Scan hay Seq Scan.
- Số estimated rows so với actual rows.
- Actual time và loops.
- Shared hit/read buffers.
- Filter rows bị loại bỏ.
- Heap fetch sau index lookup.

Nếu `findByToken` mặc định select toàn bộ authorization columns, query chỉ chọn `id` trong ví dụ trên chỉ để khảo sát lookup path. Hãy kiểm tra thêm câu SELECT thực tế của service vì row materialization có chi phí khác.

### 9.3. Đo cả tokenType cụ thể và null

Benchmark hai trường hợp:

~~~sql
-- Biết token type:
SELECT id
FROM oauth2_authorization
WHERE access_token_value = :token;

-- Không biết token type:
SELECT id
FROM oauth2_authorization
WHERE state = :token
   OR authorization_code_value = :token
   OR access_token_value = :token
   OR oidc_id_token_value = :token
   OR refresh_token_value = :token
   OR user_code_value = :token
   OR device_code_value = :token;
~~~

So sánh execution plan và số buffer đọc. Nếu unknown-token query là hot path, lookup table theo `(token_type, token_hash)` có thể giúp custom service kiểm soát cách tìm kiếm tốt hơn.

### 9.4. Statistics và maintenance

Index mới không bảo đảm planner dùng ngay nếu statistics cũ hoặc dữ liệu skew. Sau migration/backfill, cập nhật statistics theo database. Theo dõi index bloat, dead tuples, vacuum/analyze và growth. Index không được sử dụng có thể là chi phí ghi/storage không cần thiết.

### 9.5. Chỉ số benchmark

| Chỉ số | Ý nghĩa |
| --- | --- |
| p50/p95/p99 latency | Độ trễ điển hình và tail latency. |
| Queries per second | Throughput lookup. |
| Buffer hits/reads | Tỷ lệ đọc từ cache và storage. |
| Rows scanned/returned | Mức độ hiệu quả của access path. |
| DB CPU | Chi phí planner, comparison, serialization và row mapping. |
| Network bytes | Lượng dữ liệu DB trả về application. |
| Write latency | Chi phí INSERT/UPDATE sau khi thêm index. |
| Index/table size | Dung lượng lưu trữ và cache pressure. |
| Lock wait/deadlock | Tranh chấp khi save, revoke và cleanup đồng thời. |

Chạy test với token tồn tại và không tồn tại, dữ liệu phân bố đều và skew, cache nóng/lạnh, nhiều client, nhiều token type và concurrency gần production.

## 10. Dọn dữ liệu và retention

### 10.1. Token hết hạn không tự xóa row

Một token hết hạn không đồng nghĩa authorization row có thể xóa. Row có thể còn refresh token hợp lệ hoặc chứa thông tin cần thiết cho logout/revocation/audit. `OAuth2Authorization.Token.isActive()` kết hợp expiry và invalidated state; cleanup phải xét cả hai khía cạnh.

### 10.2. Batch cleanup

Với dữ liệu lớn, không nên xóa hàng triệu row trong một transaction. Một job bảo trì nên:

- Chọn một batch ID nhỏ theo thứ tự ổn định.
- Chỉ chọn row đã qua retention và không còn token/authorization cần giữ.
- Xóa mapping/index phụ cùng transaction.
- Commit sau mỗi batch.
- Có thể dùng `SKIP LOCKED` nếu database hỗ trợ và nhiều worker cleanup chạy song song.
- Giới hạn thời gian, số batch và tốc độ xóa.
- Ghi metric số hàng được kiểm tra/xóa và thời gian xử lý.

Không dùng một câu `DELETE` chỉ dựa vào `access_token_expires_at < now()` nếu row vẫn có refresh token hoặc token khác còn hiệu lực.

### 10.3. Index expiry theo workload

Nếu cleanup thường xuyên lọc theo `refresh_token_expires_at`, index trên cột đó có thể hữu ích. Nếu job lọc theo điều kiện phức tạp gồm nhiều token expiry và invalidation metadata, một index đơn có thể không đủ. Hãy thiết kế query có thể dùng index và xem execution plan thay vì tạo hàng loạt index không có bằng chứng.

### 10.4. Retention và bảo mật

Authorization data có thể chứa bearer token, claims và thông tin định danh. Retention cần cân bằng:

- Khả năng revoke/introspect token còn hiệu lực.
- Refresh token rotation và reuse detection.
- Audit/security investigation.
- Quy định lưu trữ dữ liệu.
- Chi phí storage/backup.
- Quy trình xóa dữ liệu cá nhân.

Không giữ token vô thời hạn chỉ để thuận tiện cho debug. Cũng không xóa sớm dữ liệu cần thiết để xử lý token còn hiệu lực.

## 11. Khi nào cần custom OAuth2AuthorizationService?

### 11.1. Dấu hiệu cần thay implementation

Xem xét custom service khi:

- `findByToken` là bottleneck chính dù đã tối ưu index phù hợp.
- Database không thể index trực tiếp token LOB.
- Unknown token type query tạo plan quá đắt.
- Cần token hash/HMAC lookup hoặc token table chuẩn hóa.
- Authorization row quá rộng và SELECT all columns gây I/O lớn.
- Save/update gây write amplification không đáp ứng throughput.
- Cần partitioning, sharding hoặc multi-tenant routing.
- Cần transaction/locking semantics riêng cho refresh token rotation.

Javadoc của `JdbcOAuth2AuthorizationService` khuyến nghị ứng dụng cung cấp implementation riêng nếu yêu cầu throughput cao vượt giới hạn của simplified implementation.

### 11.2. Giữ đúng contract của OAuth2AuthorizationService

Custom implementation phải giữ semantics của các method:

- `save(OAuth2Authorization)`
- `remove(OAuth2Authorization)`
- `findById(String)`
- `findByToken(String, OAuth2TokenType)`

Đặc biệt:

1. `findByToken(token, null)` phải tìm trên tất cả token type mà implementation hỗ trợ.
2. `findByToken` phải trả authorization có token tương ứng, không trả một row ngẫu nhiên khi digest collision/duplicate.
3. `save` phải duy trì token values, metadata và invalidated state.
4. `remove` phải xóa lookup mappings và authorization nhất quán.
5. Refresh/revoke/introspection phải nhìn thấy cùng trạng thái trong transaction/consistency model đã chọn.
6. Không làm lộ token trong log, exception hoặc metrics.

### 11.3. Mapper và LobHandler

Nếu tiếp tục dùng schema LOB nhưng tùy chỉnh mapper:

- Giữ JSON serialization tương thích với module Jackson của Spring Security/Authorization Server.
- Đảm bảo `LobHandler` bind/read đúng BLOB/CLOB.
- Kiểm thử dữ liệu Unicode, claims lồng nhau và payload lớn.
- Kiểm tra giới hạn cột và hành vi null.
- Đảm bảo timestamp/Instant round-trip đúng timezone.

Nếu tách bảng token, cần transaction và migration đầy đủ; không chỉ thêm một repository phụ rồi để default service tiếp tục query bảng cũ.

## 12. Lỗi thường gặp và cách xử lý

### Lỗi 1: Thêm index nhưng query vẫn full scan

**Triệu chứng:** Index đã tồn tại nhưng execution plan vẫn dùng Seq Scan/Table Scan.

**Nguyên nhân:** Kiểu cột LOB, predicate không tương thích, selectivity thấp, statistics cũ hoặc index không bao phủ query.

**Cách xử lý:** Kiểm tra kiểu dữ liệu, SQL thực tế, bind type và execution plan; cân nhắc digest lookup nếu LOB không index được.

### Lỗi 2: Tạo index prefix cho token

**Triệu chứng:** Nhiều candidate rows cùng prefix hoặc database vẫn phải lọc nhiều hàng.

**Nguyên nhân:** Prefix không duy nhất và không đại diện cho toàn token.

**Cách xử lý:** Dùng equality trên toàn giá trị khi khả thi hoặc fixed-size HMAC digest; luôn xác minh toàn bộ token.

### Lỗi 3: Nghĩ hash column tự tăng tốc default service

**Triệu chứng:** Thêm `access_token_hash` nhưng query vẫn chậm.

**Nguyên nhân:** `JdbcOAuth2AuthorizationService` vẫn dùng `WHERE access_token_value = ?`.

**Cách xử lý:** Tùy chỉnh mapper/write path và `findByToken` để query digest; hoặc dùng side table cùng custom service.

### Lỗi 4: Tạo quá nhiều index

**Triệu chứng:** Read query nhanh hơn nhưng Token Endpoint/refresh/revoke chậm hơn, storage tăng.

**Nguyên nhân:** Index write amplification và buffer pressure.

**Cách xử lý:** Chỉ giữ index phục vụ workload đo được; benchmark cả read và write.

### Lỗi 5: Chỉ tối ưu token lookup mà bỏ qua row size

**Triệu chứng:** Query plan dùng index nhưng latency vẫn cao.

**Nguyên nhân:** RowMapper đọc LOB lớn, deserialize attributes/claims và dựng object.

**Cách xử lý:** Giảm payload không cần thiết, giới hạn claims/attributes, xem xét schema/service chuyên biệt.

### Lỗi 6: Dùng index expiry để xóa mọi row đã hết access token

**Triệu chứng:** Refresh token còn hạn nhưng authorization bị xóa.

**Nguyên nhân:** Cleanup chỉ xét một token trong row.

**Cách xử lý:** Đánh giá toàn bộ token và retention trước khi xóa.

### Lỗi 7: Dùng SHA-256 plain hash cho user code ngắn

**Triệu chứng:** Người có bản sao database có thể thử đoán user code offline.

**Nguyên nhân:** Hash không có secret key và input entropy thấp.

**Cách xử lý:** Dùng HMAC với key ngoài DB, rate limit và quản lý key version.

### Lỗi 8: Lookup table không được cập nhật cùng authorization

**Triệu chứng:** Token tồn tại trong authorization nhưng không tìm thấy mapping, hoặc mapping trỏ tới row đã xóa.

**Nguyên nhân:** Ghi hai bảng không cùng transaction hoặc bỏ sót nhánh update/remove.

**Cách xử lý:** Duy trì mapping nguyên tử, foreign key/cascade phù hợp và reconciliation job.

### Lỗi 9: Index composite sai thứ tự

**Triệu chứng:** Query theo principal không dùng index `(registered_client_id, principal_name)`.

**Nguyên nhân:** Predicate không có cột leading key.

**Cách xử lý:** Thiết kế thứ tự cột theo điều kiện equality/sort thực tế và kiểm tra plan.

### Lỗi 10: Benchmark với dữ liệu nhỏ

**Triệu chứng:** Local test rất nhanh nhưng production chậm.

**Nguyên nhân:** Không mô phỏng cardinality, skew, token length, concurrency và cache pressure.

**Cách xử lý:** Benchmark trên dữ liệu gần quy mô production và đo p95/p99, buffer reads, write latency.

## 13. Ma trận kiểm thử và benchmark

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| `findById` với ID tồn tại | Dùng PK lookup và trả đúng authorization. |
| `findByToken` với access token type | Dùng filter đúng cột access token. |
| `findByToken` với refresh token type | Dùng filter đúng cột refresh token. |
| `findByToken` với authorization code type | Dùng filter đúng cột code. |
| `findByToken` với tokenType null | Tìm đủ các loại token/state theo contract. |
| Token không tồn tại | Trả `null` với latency ổn định. |
| Token có cùng prefix nhưng khác giá trị | Không trả nhầm authorization. |
| Token dài gần giới hạn | Insert, lookup và row mapping thành công. |
| Metadata/attributes lớn | Không truncate; JSON round-trip đúng. |
| LOB BLOB/CLOB | Mapper đọc/ghi đúng theo schema DB. |
| Index trực tiếp trên token | Execution plan dùng index khi phù hợp. |
| Hash lookup | Digest được tính nhất quán và query trả đúng ID. |
| HMAC key version rotation | Cả mapping cũ/mới hoạt động trong thời gian chuyển đổi. |
| Save/update authorization | Lookup mappings và row dữ liệu đồng bộ. |
| Remove authorization | Mapping phụ được xóa đúng. |
| Refresh token rotation | Token cũ invalidated, token mới được tra cứu đúng. |
| Revocation | Tìm đúng authorization và cập nhật invalidation metadata. |
| Cleanup batch | Không xóa row còn refresh/device/user token active. |
| Consent lookup theo client + principal | Composite PK được sử dụng. |
| Consent lookup theo principal | Có index phù hợp nếu workload yêu cầu. |
| Concurrent lookup/write | Không mất mapping hoặc đọc trạng thái không nhất quán. |
| Load test nhiều triệu rows | p95/p99 đạt SLO, query plan ổn định. |

### 13.1. Quy trình benchmark trước/sau index

1. Tạo dataset có cardinality và phân bố token type gần production.
2. Chạy query typed và `tokenType=null` để lấy baseline.
3. Lưu execution plan, p50/p95/p99, buffer reads và DB CPU.
4. Tạo một nhóm index nhỏ theo query hot path.
5. Cập nhật statistics và chạy lại benchmark.
6. Đo cả Token Endpoint/refresh/revoke write path.
7. Đo dung lượng index và chi phí maintenance.
8. Chỉ giữ thay đổi có lợi ích tổng thể và rollback được.

## 14. Checklist production

| Hạng mục | Điều kiện cần xác nhận |
| --- | --- |
| Schema | Schema đúng version Spring Authorization Server và DB vendor? |
| Token lookup | Biết các endpoint nào gọi `findByToken` và tần suất? |
| Token type | Caller truyền token type khi biết; null vẫn giữ semantics đầy đủ? |
| Primary key | `id` có PK/index? |
| Secondary index | Index chỉ tạo theo query workload và kiểu cột có thể index? |
| LOB | Đã xác minh khả năng index BLOB/CLOB và giới hạn kích thước? |
| Hash lookup | Custom service thực sự query digest; không chỉ thêm cột? |
| HMAC key | Secret key được giữ ngoài DB và có kế hoạch rotation? |
| Row size | Attributes/claims/metadata có giới hạn và không chứa payload thừa? |
| Write path | Đã đo chi phí `save`/update và index maintenance? |
| Consent | Composite PK phù hợp query pattern? |
| Cleanup | Chỉ xóa row khi mọi token liên quan hết hạn/invalidated và retention cho phép? |
| Query plan | Có EXPLAIN/ANALYZE và statistics phù hợp? |
| Benchmark | Có p95/p99, read/write, hit/miss và concurrency? |
| Custom service | Đã giữ đúng contract `OAuth2AuthorizationService`? |
| Consistency | Authorization và token lookup mapping cập nhật cùng transaction? |
| Observability | Có metric query latency, rows/buffers, DB pool wait và table/index growth? |
| Security | Không log raw bearer token hoặc HMAC secret? |

## 15. Bài tập thực hành

Authorization Server đang lưu 8 triệu hàng trong `oauth2_authorization`. Khoảng 70% request tra access token, 20% tra refresh token và 10% còn lại tra code, ID Token, user code hoặc device code. Schema dùng BLOB cho token values; bảng có PK `id` nhưng chưa có secondary index. Một số authorization row có attributes/claims dài do chứa quá nhiều thông tin hồ sơ.

1. Vẽ query path cho `findByToken(token, tokenType)` với access token, refresh token và token type null.
2. Giải thích vì sao index trên `access_token_expires_at` không giúp `WHERE access_token_value = ?`.
3. Đề xuất index nếu database/schema chuyển token columns sang kiểu có thể index toàn giá trị; nêu giới hạn của phương án này.
4. Thiết kế `oauth2_authorization_token_lookup` với HMAC-SHA-256 và composite primary key.
5. Viết pseudo-code cho `findByToken` có token type cụ thể và token type null.
6. Chứng minh thêm hash column mà không đổi SQL không làm query mặc định dùng hash index.
7. Đo tác động của row size bằng cách giảm attributes/claims không cần thiết.
8. Thiết kế cleanup batch không xóa authorization còn refresh token active.
9. So sánh p95/p99, buffer reads và write latency trước/sau index.
10. Đưa ra tiêu chí quyết định giữ `JdbcOAuth2AuthorizationService` hay thay bằng implementation riêng.

**Tiêu chí đạt:** Thiết kế index khớp query thật, không phụ thuộc index không hỗ trợ LOB, token lookup digest được duy trì nhất quán, cleanup không phá token còn hiệu lực và benchmark thể hiện cả lợi ích đọc lẫn chi phí ghi.

## 16. Tài liệu đối chiếu

- [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): schema dependency, `findById`, `findByToken`, mapper và giới hạn throughput của implementation JDBC mặc định.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): cấu trúc `OAuth2Authorization`, token lifecycle và `OAuth2AuthorizationService`.
- [Spring Authorization Server 1.5.8 — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): flattened authorization schema, consent composite key, truy vấn repository và lưu ý kích thước dữ liệu.
- [Spring Authorization Server — oauth2-authorization-schema.sql](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql): các cột authorization và primary key của schema JDBC.
- [Spring Authorization Server — oauth2-authorization-consent-schema.sql](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql): composite primary key của authorization consent.
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html): cách index hỗ trợ equality/range lookup và trade-off chi phí ghi.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): đọc execution plan và estimated/actual cost.
- [PostgreSQL — Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, hash, GIN, GiST và phạm vi sử dụng.
- [MySQL — InnoDB Limits](https://dev.mysql.com/doc/refman/8.4/en/innodb-limits.html): giới hạn row size và index key length.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, refresh token và vòng đời authorization.
