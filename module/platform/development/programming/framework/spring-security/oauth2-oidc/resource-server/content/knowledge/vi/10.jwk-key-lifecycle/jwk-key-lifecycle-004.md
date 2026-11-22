# Bộ nhớ đệm JWKS, thời gian sống và làm mới dữ liệu khóa

Khi một API dùng **Spring Security OAuth 2.0 Resource Server** xác thực access token dạng JWT có chữ ký bất đối xứng, API cần biết **khóa công khai** tương ứng với khóa riêng đã được **Authorization Server** sử dụng để ký token. Các khóa công khai này thường được công bố qua một endpoint **JWKS (JSON Web Key Set)**. Thay vì tải toàn bộ JWKS từ mạng ở mỗi HTTP request, Resource Server thường **lưu bộ khóa trong bộ nhớ đệm (cache)** và tải lại khi cần.

Cache JWKS là điểm giao nhau giữa **hiệu năng**, **khả năng chịu lỗi** và **an toàn trong vòng đời khóa**. Cache quá ngắn làm tăng lưu lượng đến Authorization Server; cache quá lâu có thể khiến API không nhận khóa mới hoặc tiếp tục sử dụng khóa cũ lâu hơn mong muốn. Trong các đợt **key rotation**, cách issuer xuất bản khóa và cách Resource Server refresh cache phải phối hợp với nhau.

Bài này trình bày cách JWKS được lấy và sử dụng, các loại thời gian sống, cơ chế làm mới khi gặp `kid` mới, cách tổ chức rotation an toàn và những lưu ý khi cấu hình **Spring Security/NimbusJwtDecoder**. Hành vi mặc định và API cấu hình có thể phụ thuộc **phiên bản Spring Boot, Spring Security và Nimbus JOSE + JWT**.

## 1. JWKS giải quyết vấn đề gì?

Trong ký JWT bất đối xứng, Authorization Server giữ **private key** để ký token, còn Resource Server dùng **public key** để xác minh chữ ký. Public key có thể được phân phối qua JWKS.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Spring Security Resource Server
    participant JWKS as JWKS endpoint
    C->>AS: Xin access token theo grant được phép
    AS->>AS: Ký JWT bằng private key của K1
    AS-->>C: JWT có JOSE header kid=K1
    C->>RS: GET /api/orders + Bearer JWT
    RS->>JWKS: Tải public JWKs nếu cache chưa có dữ liệu phù hợp
    JWKS-->>RS: JWKS gồm public key của K1
    RS->>RS: Xác minh signature, issuer, exp, aud, scope...
    RS-->>C: Kết quả API hoặc lỗi
~~~

Đường dẫn thông dụng:

~~~text
https://auth.example.com/realms/shop/.well-known/openid-configuration
    |
    +-- jwks_uri: https://auth.example.com/realms/shop/protocol/openid-connect/certs
~~~

Đây là URL **minh họa**. Không phải mọi Authorization Server sử dụng cùng một đường dẫn. Với OIDC Discovery hoặc OAuth 2.0 Authorization Server Metadata, Resource Server có thể lấy `jwks_uri` từ metadata của **issuer đáng tin cậy**; cũng có thể được cấu hình một JWKS URL cụ thể.

Một JWKS là JSON object có thuộc tính `keys` chứa các JWK:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS_FOR_NEW_KEY",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị `n` trong ví dụ chỉ là **placeholder**, không phải khóa RSA thật. JWKS dành cho Resource Server phải công bố **vật liệu khóa công khai** phù hợp; với RSA, đó có thể là `n` và `e`. Không công bố private key hoặc những tham số bí mật như `d`, `p`, `q` trong JWKS công khai.

| Trường JWK | Vai trò |
| --- | --- |
| `kty` | Loại khóa, ví dụ `RSA` hoặc `EC` |
| `kid` | Định danh khóa giúp tìm khóa phù hợp |
| `use` | Mục đích, ví dụ `sig` cho chữ ký khi có |
| `key_ops` | Các thao tác khóa được cho phép nếu có |
| `alg` | Thuật toán dự kiến khi được công bố |
| `n`, `e` | Tham số khóa công khai RSA |
| `crv`, `x`, `y` | Một số tham số công khai của khóa đường cong elliptic |

Không phải tất cả thuộc tính đều bắt buộc trong mọi JWK. Resource Server phải dùng bộ xử lý JOSE/JWT đáng tin cậy để chọn khóa tương thích với header và **thuật toán được cấu hình cho phép**, thay vì lấy bất kỳ JWK nào trùng `kid` rồi coi là hợp lệ.

## 2. `kid` liên hệ JWKS cache như thế nào?

Một access token JWT dạng JWS thường gồm:

~~~text
BASE64URL(JOSE protected header).BASE64URL(JWT claims).BASE64URL(signature)
~~~

Ví dụ header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-02"
}
~~~

`kid` là gợi ý **chọn khóa** từ JWKS. Nếu cache của Resource Server đang giữ `key-2026-01`, nhưng JWT mới mang `key-2026-02`, decoder có thể cần tải lại JWKS để tìm khóa công khai mới.

Điều này **không đồng nghĩa** với việc token được tin cậy chỉ vì `kid` có trong JWKS:

1. Resource Server phải xác định JWKS endpoint từ **cấu hình issuer đáng tin**, không từ một URL tùy ý do token cung cấp.
2. Decoder tìm khóa có loại/thuật toán và thuộc tính phù hợp.
3. Decoder xác minh **chữ ký JWT** bằng khóa công khai được tin cậy.
4. Các validator tiếp tục kiểm tra `iss`, `exp`, `nbf`, `aud` và hợp đồng token/profile.
5. Phần authorization kiểm tra scope và quyền trên endpoint, tenant, đối tượng dữ liệu.

`kid` không phải mật khẩu, access token hoặc quyền. Nó cũng không phải cơ chế thu hồi JWT. Một JWT sai chữ ký vẫn phải bị từ chối, kể cả khi `kid` trùng một khóa trong JWKS.

**Không tự động truy cập header `jku` hoặc `x5u` do token khai báo để tải khóa từ Internet.** Nếu xử lý các trường này, chỉ dùng nguồn khóa đã được kiểm soát và cho phép rõ ràng; nếu không, kẻ tấn công có thể điều khiển hệ thống đi lấy khóa từ nguồn không tin cậy hoặc gây SSRF.

## 3. Vì sao cần cache JWKS?

Giả sử Orders API nhận 1.000 request/giây. Nếu mọi request đều tải JWKS qua mạng, Authorization Server/JWKS endpoint sẽ phải xử lý 1.000 truy vấn/giây chỉ để phục vụ kiểm tra chữ ký. Trong khi đó, phần lớn token được ký bởi **một nhóm nhỏ khóa công khai** đang hoạt động.

JWKS cache giúp:

- **Giảm độ trễ xác thực:** sau khi có public key phù hợp, việc kiểm tra chữ ký JWT thường diễn ra cục bộ.
- **Giảm tải cho issuer:** tránh tạo hàng loạt HTTP request JWKS lặp lại.
- **Tăng khả năng chịu lỗi ngắn hạn:** nếu đã có khóa hợp lệ trong cache, một số request có thể tiếp tục xác minh dù JWKS endpoint tạm chậm hoặc mất kết nối, tùy chính sách cache/decoder.
- **Hỗ trợ thay khóa có kiểm soát:** trong một giai đoạn rotation, cache có thể giữ cả khóa ký cũ và khóa ký mới để xác minh token còn hạn.

Tuy nhiên, cache cũng tạo ra **độ trễ đồng bộ**: Authorization Server vừa công bố khóa mới nhưng một Resource Server có thể vẫn đang giữ ảnh chụp JWKS cũ.

### Ba khái niệm thường bị nhầm

| Khái niệm | Đơn vị/thước đo | Ý nghĩa |
| --- | --- | --- |
| **JWT expiration (`exp`)** | Thời điểm NumericDate trong JWT | Khi nào **một access token** hết hiệu lực |
| **JWKS cache TTL** | Khoảng thời gian, ví dụ 5 phút | Khi nào **bản sao tập khóa** trong cache hết thời gian lưu được cấu hình |
| **Key rotation overlap** | Khoảng thời gian cùng công bố nhiều public key | Bảo đảm token đã ký bởi khóa cũ còn có thể xác minh khi khóa mới bắt đầu được dùng |

**JWT còn hạn không có nghĩa cache JWKS phải còn hạn**, và **cache JWKS còn hạn không làm một JWT đã hết hạn được dùng tiếp**. Hai vòng đời độc lập.

## 4. Các tầng cache có thể cùng tồn tại

Trong một hệ thống triển khai thật, có thể có nhiều tầng:

~~~text
Resource Server instance A          Resource Server instance B
        |                                     |
  Nimbus/JWKS cache A                   Nimbus/JWKS cache B
        |                                     |
        +------------------+------------------+
                           |
                 HTTP client / proxy / CDN
                           |
                      JWKS endpoint
                           |
                    Authorization Server
~~~

Một số tầng thường thấy:

| Tầng | Cache gì? | Lưu ý |
| --- | --- | --- |
| **Decoder cache trong JVM** | JWKS JSON hoặc tập JWK đã parse | Thường gắn với từng decoder/instance; TTL/refresh phụ thuộc implementation |
| **Spring Cache do ứng dụng cung cấp** | Dữ liệu JWKS qua adapter cache nếu phiên bản hỗ trợ | Chính sách eviction, TTL, dung lượng do ứng dụng quản lý |
| **HTTP client cache / proxy / CDN** | HTTP response của `jwks_uri` khi hạ tầng có cache | Có thể dùng `Cache-Control`, `ETag`, `Last-Modified` theo cache thực tế |
| **Issuer/CDN phía Authorization Server** | Bản sao JWKS do issuer xuất bản | Cần kiểm soát thời gian lan truyền khi rotation |

**Không mặc định rằng HTTP `Cache-Control: max-age=300` quyết định TTL bên trong `NimbusJwtDecoder`.** Nimbus hoặc cache adapter có thể dùng chính sách nội bộ và HTTP client không nhất thiết tôn trọng header cache theo cách một browser/CDN làm. Cần xác định **tầng nào đang cache, ai thiết lập thời gian sống và khi nào nó thực sự được làm mới**.

Tương tự, nếu hệ thống có 20 replica và mỗi replica có cache riêng, cache nóng ở replica A **không tự động làm cache của B mới hơn**. Rotation nên tính đến replica cũ, node mới khởi động và quá trình triển khai rolling update.

## 5. TTL, thời gian làm mới và thời gian hết hạn

### 5.1. TTL (time-to-live)

**TTL** là khoảng thời gian một bản dữ liệu cache được giữ trước khi bị coi là hết hạn theo chính sách. Ví dụ:

~~~text
10:00  Resource Server tải JWKS, cache bắt đầu chứa K1
10:03  Request dùng K1 có thể xác minh bằng khóa đã cache
10:05  TTL giả định 5 phút kết thúc
10:06  Lần truy cập tiếp theo có thể khiến cache nạp lại JWKS
~~~

Trong cách cài đặt **lazy refresh**, hết TTL **không đồng nghĩa** xuất hiện một HTTP request đúng tại mốc 10:05. Dữ liệu có thể chỉ được tải lại khi có nhu cầu xác thực kế tiếp. Một số cache hay JWKS source hỗ trợ refresh sớm hoặc làm mới dựa trên điều kiện; hành vi cụ thể phụ thuộc phiên bản và cấu hình.

Chính sách thường được phân biệt:

- **Expire after write:** hết hạn sau một thời gian từ lúc ghi/cập nhật entry.
- **Expire after access:** thời gian sống được kéo dài khi entry được truy cập; nếu dùng tùy tiện cho JWKS, khóa cũ có thể tồn tại rất lâu khi API luôn có lưu lượng.
- **Refresh after write:** sau một khoảng, dữ liệu có thể được làm mới khi truy cập; nhiều thư viện tiếp tục dùng giá trị cũ trong lúc refresh.
- **Maximum cache age:** đặt giới hạn cứng đối với độ tuổi bản sao, dù có cache hit.
- **Stale on failure:** tạm dùng dữ liệu cũ khi fetch lỗi, nếu chính sách thư viện và an ninh cho phép.

Các cơ chế trên **không đồng nghĩa**. Đặc biệt, “có entry trong cache” chưa chắc “entry hiện tại còn được chấp nhận để kiểm tra token”. Cần biết cache trả giá trị cũ, xoá entry hay buộc fetch trước khi xác minh.

### 5.2. Các mốc khác nhau trong vòng đời JWK

Một tổ chức thường cần xét:

| Mốc | Ý nghĩa |
| --- | --- |
| **Publish key** | Công bố **public key mới** trong JWKS |
| **Start signing** | Authorization Server bắt đầu ký JWT mới bằng private key mới |
| **Stop signing old key** | Không phát hành JWT mới với private key cũ |
| **Last old token expires** | JWT hợp lệ cuối cùng đã ký bằng khóa cũ hết hạn |
| **Remove old public key** | Có thể gỡ public key cũ khỏi JWKS nếu không còn consumer hợp lệ cần dùng |
| **Cache convergence** | Các Resource Server cuối cùng đã lấy phiên bản JWKS phù hợp sau propagation/cache refresh |

Chỉ tính TTL cache mà bỏ qua **token lifetime** là không đủ để chọn thời điểm gỡ khóa cũ.

### 5.3. Có một TTL “chuẩn bắt buộc” cho JWKS không?

**Không có một TTL duy nhất phù hợp mọi hệ thống OAuth 2.0/OIDC.** Một số triển khai Nimbus/Spring Security có chính sách cache mặc định ở khoảng **vài phút**; ví dụ tài liệu của một số dòng Spring Security nêu cache JWKS trong bộ nhớ khoảng **5 phút**. Tuy nhiên, **không dùng số 5 phút như một bảo đảm xuyên mọi phiên bản, decoder, HTTP client hoặc custom cache**.

TTL hợp lý phụ thuộc:

- Tần suất ký lại/rotation khóa.
- Thời gian access token còn hiệu lực.
- Khả năng refresh khi thấy `kid` chưa biết.
- Mức độ sẵn sàng của JWKS endpoint.
- Số replica, độ trễ mạng và giới hạn tải issuer.
- Yêu cầu phản ứng khi thu hồi hoặc thay khóa khẩn cấp.
- Chính sách cache bổ sung của Spring Cache, Nimbus, proxy hoặc CDN.

Nên **đo và kiểm chứng hành vi trong chính phiên bản đang dùng**, đồng thời tạo quy trình rotation không chỉ dựa vào đúng một con số TTL.

## 6. Key rotation an toàn khi có JWKS cache

Giả sử Authorization Server đang ký bằng khóa **K1** và muốn chuyển sang **K2**.

Một cách triển khai có kiểm soát:

1. **Tạo K2 an toàn**, giữ private key của K2 ở Authorization Server/KMS/HSM, không đưa private key vào JWKS.
2. **Công bố public key K2 trong JWKS trước** khi bắt đầu phát JWT ký bằng K2. JWKS lúc này chứa **K1 và K2**.
3. **Chờ khoảng lan truyền** đủ để proxy/CDN/cache và các Resource Server có thể biết K2. Nếu hệ thống hỗ trợ refresh an toàn khi gặp `kid` mới thì có thể giảm độ trễ, nhưng không được lệ thuộc hoàn toàn vào cơ chế đó.
4. **Chuyển hoạt động ký sang K2**. JWT mới mang `kid: K2`; JWT cũ mang `kid: K1` vẫn có thể còn hạn.
5. **Giữ public key K1 trong JWKS** đến khi JWT cũ cuối cùng có thể chấp nhận đã hết hạn, cộng thêm dung sai đồng hồ và biên an toàn của hệ thống.
6. **Gỡ public key K1** khi không còn consumer hợp lệ cần xác minh token đã ký bằng K1. Quản lý cache và tình huống thay khóa khẩn cấp theo chính sách riêng.

~~~mermaid
gantt
    title Minh họa vòng đời khóa khi chuyển K1 sang K2
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section K1
    Ký token bằng K1            :a1, 2026-11-01, 7d
    Giữ public K1 để xác minh   :a2, 2026-11-08, 4d
    section K2
    Công bố public K2 trước     :b1, 2026-11-05, 3d
    Bắt đầu ký bằng K2          :b2, 2026-11-08, 8d
~~~

Các ngày trong sơ đồ là **giả định để minh họa trình tự**, không phải thời hạn khuyến nghị cố định. Khi áp dụng thực tế phải dựa trên thời gian phát token, JWT lifetime tối đa, clock skew và chính sách đồng bộ JWKS.

### Ví dụ tính mốc gỡ khóa K1

Giả sử:

- Authorization Server ngừng ký bằng **K1** lúc **12:00 UTC**.
- Access token được cấp tối đa **15 phút**.
- Resource Server cho phép **60 giây clock skew**.
- Hệ thống chừa thêm **2 phút biên an toàn** để xử lý độ trễ và sự không đồng nhất vận hành.

Thì token cuối cùng ký bằng K1 có thể còn được chấp nhận ít nhất tới gần **12:16 UTC**, và một mốc gỡ K1 được vận hành thận trọng có thể là **12:18 UTC hoặc muộn hơn**, sau khi đã xác nhận các giả định. Cần thêm yếu tố token lifetime thực tế, cách tính `exp`, propagation và mọi profile token khác đang dùng cùng khóa.

**Không xóa K1 khỏi JWKS ngay khi bắt đầu ký bằng K2.** Làm vậy có thể khiến token K1 vẫn còn hạn đột nhiên bị từ chối trên các Resource Server vừa refresh JWKS.

### Đừng tái sử dụng `kid` cho vật liệu khóa khác

Nếu K2 mang cùng `kid` với K1 nhưng public key khác, những instance giữ cache có thể chọn nhầm khóa và báo chữ ký không hợp lệ. Nên dùng **`kid` mới, ổn định và duy nhất trong phạm vi cần thiết** cho mỗi lần xoay vật liệu khóa. Không dùng `kid` như nguồn ủy quyền để tải một public key ngoài danh sách tin cậy.

## 7. Điều gì xảy ra khi gặp `kid` chưa có trong cache?

Đây là tình huống quan trọng nhất trong rotation:

~~~mermaid
flowchart TD
    A["Nhận JWT có kid=K2"] --> B["Đọc JWKS cache hiện tại"]
    B --> C{"Có JWK thích hợp cho K2?"}
    C -- "Có" --> D["Xác minh chữ ký và các validators"]
    C -- "Không" --> E{"Decoder/cache có hỗ trợ fetch lại phù hợp?"}
    E -- "Có" --> F["Fetch JWKS từ issuer tin cậy theo giới hạn retry/cache"]
    F --> G{"Có public key K2 hợp lệ?"}
    G -- "Có" --> D
    G -- "Không" --> H["Từ chối xác thực"]
    E -- "Không / không thể tải" --> H
    D --> I{"Chữ ký, issuer, exp, aud... đúng?"}
    I -- "Có" --> J["Tiếp tục phân quyền"]
    I -- "Không" --> H
~~~

Một số phiên bản hoặc cách cấu hình Nimbus JWKS source hỗ trợ **làm mới cache khi không tìm được khóa theo `kid`**. Nhưng cần hiểu giới hạn:

- Không phải mọi loại cache đều có hành vi giống nhau khi chưa tìm được `kid`.
- Việc thêm **custom cache** có thể thay đổi cách Nimbus xử lý cache miss và refresh.
- Một số triển khai giới hạn thời điểm hoặc tần suất refresh để tránh việc attacker tạo vô số JWT có `kid` ngẫu nhiên, khiến API liên tục fetch JWKS.
- Nếu JWKS endpoint chưa công bố K2, fetch lại vẫn không giải quyết được.
- Nếu request bị sai chữ ký hoặc token không phù hợp issuer/algorithm, refresh JWKS **không thể** biến nó thành token hợp lệ.

**Không dựa vào giả định “Nimbus sẽ luôn tải lại JWKS ngay khi gặp kid lạ”.** Khi thiết kế rotation, hãy đối chiếu chính xác phiên bản và behavior của `RemoteJWKSet`/decoder/cache adapter đang dùng, rồi công bố khóa mới trước khi bắt đầu ký như phương án ổn định hơn.

### Bảo vệ trước unknown-kid flooding

Một attacker có thể gửi lượng lớn JWT giả với `kid` khác nhau. Nếu API cố tải JWKS sau mỗi `kid` lạ, issuer có thể bị quá tải và API tăng độ trễ.

Các nguyên tắc cần áp dụng:

1. Chỉ fetch từ **JWKS URI đã cho phép**.
2. Có **timeout** HTTP ngắn, số retry hữu hạn và cơ chế tránh nhiều request refresh trùng nhau.
3. Cache JWKS có thời gian sống phù hợp và cơ chế rate limiting/backoff khi refresh thất bại.
4. Giới hạn lưu lượng request vào API và quan sát tỷ lệ unknown `kid`.
5. **Fail closed:** không chấp nhận JWT chỉ vì JWKS endpoint hiện không truy cập được.

Đối với JWT đã có khóa trong cache, decoder có thể không cần fetch thêm. Đối với `kid` lạ, API phải xác minh từ nguồn khóa đáng tin hoặc từ chối xác thực; **không chọn đại khóa khác** để cố chấp nhận token.

## 8. Spring Security: cấu hình issuer và JWKS URI

Ứng dụng Spring Boot Servlet dùng Resource Server thường có dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

### 8.1. Cấu hình `issuer-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Với cấu hình này, Spring Security dùng issuer để tìm metadata và JWKS URI theo cơ chế hỗ trợ, đồng thời cấu hình kiểm tra `iss` của JWT. Tùy dòng phiên bản, quá trình discovery có thể diễn ra vào lúc khởi tạo hoặc thời điểm xử lý token đầu tiên; tránh mặc định mọi phiên bản đều có cùng phụ thuộc khởi động vào issuer.

Sau khi lấy được bộ khóa, decoder có thể xác minh JWT mà không cần gọi issuer ở **mỗi request**, miễn khóa phù hợp vẫn có trong cache và các điều kiện xác thực thành công.

### 8.2. Cấu hình đồng thời `issuer-uri` và `jwk-set-uri`

Khi biết rõ endpoint JWKS, có thể khai báo:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
          jwk-set-uri: https://auth.example.com/realms/shop/protocol/openid-connect/certs
~~~

Trong các dòng Spring Boot/Spring Security có hỗ trợ, `jwk-set-uri` cung cấp endpoint khóa trực tiếp, giúp giảm hoặc tránh bước discovery issuer lúc khởi tạo; `issuer-uri` vẫn cung cấp thông tin để kiểm tra claim `iss`. **Cung cấp URI JWKS không khiến API tự biết audience hoặc quyền nghiệp vụ**: các điều kiện đó cần cấu hình riêng.

Không nên bỏ `issuer-uri` chỉ vì đã có `jwk-set-uri` nếu API thực sự cần xác minh issuer. Nếu cấu hình decoder thủ công, hãy bảo đảm bạn chủ động gắn validators tương đương.

### 8.3. Tách việc lấy khóa khỏi thời hạn JWT

Ngay cả khi JWKS cache đang “fresh”, Resource Server vẫn phải kiểm tra mỗi JWT:

- **Chữ ký/thuật toán** với khóa tin cậy.
- **Issuer** chính xác được API cho phép.
- **Thời hạn** `exp` và `nbf` (cùng những điều kiện thời gian khác theo profile).
- **Audience** được phát hành cho API nhận token.
- **Loại/profile access token** khi giao thức yêu cầu.
- **Scope/authorities**, tenant và quyền trên đối tượng.

JWKS cache chỉ hỗ trợ **tìm vật liệu khóa để xác minh**. Nó không lưu trạng thái “JWT X đã được cấp quyền” và không thay thế authorization.

## 9. Tùy chỉnh cache JWKS với `NimbusJwtDecoder`

Ở một số dòng Spring Security, builder `NimbusJwtDecoder.withJwkSetUri(...)` có phương thức **`cache(org.springframework.cache.Cache)`** để tích hợp cache ứng dụng. Bạn có thể dùng một cache có TTL và giới hạn dung lượng, ví dụ cache dựa trên Caffeine.

> **Điều kiện phiên bản:** Mã dưới đây minh họa API builder ở những phiên bản **có hỗ trợ `cache(Cache)`**. Cần kiểm tra API trong dependency thực tế của dự án. Kiểu cache và cách Nimbus phát hiện cache miss/unknown `kid` có thể thay đổi theo phiên bản; chỉ thay thế cache sau khi hiểu hành vi refresh của phiên bản ấy.

### 9.1. Ví dụ cache có TTL

Dependency Caffeine và Spring Cache adapter cần được cung cấp tương thích với phiên bản Spring Boot của ứng dụng; ví dụ dưới đây giả định `com.github.ben-manes.caffeine:caffeine` và `org.springframework:spring-context-support` đã có.

~~~java
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import org.springframework.cache.Cache;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JwksCacheConfiguration {

    @Bean
    Cache jwksCache() {
        return new CaffeineCache(
            "jwks",
            Caffeine.newBuilder()
                .maximumSize(32)
                .expireAfterWrite(Duration.ofMinutes(5))
                .build()
        );
    }
}
~~~

Ý nghĩa:

- `expireAfterWrite(Duration.ofMinutes(5))` đặt **TTL cho entry cache** sau khi ghi/cập nhật.
- `maximumSize(32)` giới hạn lượng entry ở tầng cache này, hữu ích khi cache được chia theo một số JWKS URI được cho phép.
- Đây là **giá trị minh họa**, không phải một TTL khuyến nghị bắt buộc.
- Cache entry có thể là **tập JWKS trả về cho một URI**, không có nghĩa “mỗi JWK = một entry” hay “mỗi token = một entry”.

**Không dùng `expireAfterAccess(...)` một cách vô thức** nếu kỳ vọng JWKS phải được tải lại sau một khoảng thời gian cứng: khi API liên tục có lưu lượng, một entry có thể được gia hạn TTL bằng mỗi lần truy cập.

### 9.2. Gắn cache vào decoder và giữ kiểm tra token

Ví dụ cấu hình dành cho API xác minh JWT và yêu cầu audience `orders-api`:

~~~java
import org.springframework.cache.Cache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfiguration {

    private static final String ISSUER =
        "https://auth.example.com/realms/shop";
    private static final String JWKS_URI =
        "https://auth.example.com/realms/shop/protocol/openid-connect/certs";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder(Cache jwksCache) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .cache(jwksCache)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

Các điểm cần hiểu:

1. `withJwkSetUri(JWKS_URI)` cung cấp nguồn khóa tin cậy, không có nghĩa API chấp nhận mọi token được ký bằng bất kỳ khóa có trong đó.
2. `cache(jwksCache)` thay đổi cách lưu/tải lại dữ liệu JWKS theo adapter được hỗ trợ; **TTL của Caffeine không phải TTL JWT**.
3. `JwtValidators.createDefaultWithIssuer(ISSUER)` đưa các kiểm tra mặc định tương ứng và issuer vào decoder. `audienceValidator` bảo đảm token hướng đến API.
4. `setJwtValidator(...)` **thay** tập validator của decoder bằng tập mới: phải giữ lại đầy đủ các điều kiện quan trọng thay vì chỉ kiểm tra audience.
5. Nếu hệ thống dùng **RFC 9068 `at+jwt`** hoặc profile riêng, cần bổ sung validator type/profile theo khả năng phiên bản, tránh bỏ mặc điều kiện `typ`/claim bắt buộc.
6. Cấu hình cache tùy chỉnh có thể ảnh hưởng hành vi **refresh khi không tìm được `kid` mới**; cần hiểu contract của decoder/cache adapter được chọn.

Đây là cấu hình **minh họa**, không nhất thiết phải tùy chỉnh. Với hệ thống đơn giản, cache mặc định của decoder có thể đã đủ và thường giảm độ phức tạp vận hành.

### 9.3. Cẩn trọng với cache không có giới hạn thời gian

Ví dụ tạo `ConcurrentMapCache` mà không có cơ chế expiration riêng có thể giữ JWKS cũ lâu hơn mong đợi:

~~~java
// Ví dụ không có TTL tự thân:
// new ConcurrentMapCache("jwks");
~~~

Nếu gắn loại cache đó vào decoder và giả định Nimbus vẫn áp dụng TTL mặc định như trước thì có thể dẫn đến vấn đề rotation. Một cache ứng dụng nên có **chính sách expiry, refresh, dung lượng và invalidation rõ ràng** phù hợp với behavior của phiên bản.

## 10. Điều chỉnh HTTP client để tải JWKS

Ngoài TTL, Resource Server còn cần xử lý kết nối mạng tới JWKS endpoint:

- **Connect timeout:** tránh chờ lâu khi không kết nối được.
- **Read timeout:** giới hạn thời gian đợi response.
- **TLS:** kết nối đến endpoint đáng tin, xác minh chứng chỉ và hostname theo cấu hình.
- **Response size:** không cho endpoint hoặc trung gian trả dữ liệu quá lớn vượt mức an toàn.
- **Retry/backoff:** hạn chế số lần thử lại; không tạo bão request khi issuer lỗi.
- **Rate limiting/concurrency:** tránh nhiều luồng đồng thời cùng tải lại JWKS khi cache lạnh hoặc vừa hết TTL.

Trong các phiên bản có hỗ trợ, builder `NimbusJwtDecoder.withJwkSetUri(...)` có thể nhận một `RestOperations` qua phương thức `restOperations(...)` để kiểm soát cách tải JWKS. Tên API chính xác, vị trí hook HTTP client và behavior cần đối chiếu với Spring Security/Nimbus đang dùng.

Ví dụ khái niệm:

~~~java
// Chỉ là sơ đồ cách cấu hình; tạo RestOperations với timeout/TLS
// phù hợp phiên bản và chính sách của hệ thống:
//
// NimbusJwtDecoder decoder = NimbusJwtDecoder
//     .withJwkSetUri(jwksUri)
//     .restOperations(jwksRestOperations)
//     .build();
~~~

Các header HTTP như `Cache-Control`, `ETag` và `Last-Modified` chỉ hữu ích nếu **tầng HTTP/client/cache tương ứng thực sự dùng chúng**. Không mặc định có request điều kiện `If-None-Match` hoặc HTTP 304 trong mọi cách tích hợp Nimbus. Để biết chính xác việc refresh, cần kiểm tra log/metrics của **JWKS fetch thực tế**.

## 11. Khi JWKS endpoint gặp sự cố

Phân biệt **cache đã nóng** và **cache chưa có khóa**:

| Tình huống | Hành vi có thể có | Quyết định bảo mật |
| --- | --- | --- |
| Cache còn public key K1 phù hợp với token K1 | Có thể xác minh cục bộ nếu cache/decoder cho phép dùng entry đó | Vẫn kiểm tra đầy đủ chữ ký, thời hạn, issuer, audience |
| Cache lạnh, JWKS endpoint không truy cập được | Không có vật liệu khóa cần thiết để xác minh | **Không chấp nhận** JWT chưa xác thực |
| Cache đã hết TTL, refresh thất bại | Tùy implementation: từ chối, dùng stale entry có giới hạn, hoặc phát sinh lỗi hệ thống | Không tự “cho qua” mọi token |
| Nhận token K2 nhưng cache chỉ có K1 và issuer không trả JWKS mới | Không tìm được khóa để xác minh K2 | Từ chối token K2 cho đến khi có khóa được tin cậy |
| JWKS trả JSON lỗi định dạng, thiếu khóa hoặc sai thuật toán | Decoder có thể báo lỗi xác minh/cấu hình | Không dùng khóa không phù hợp để thay thế |
| Issuer bị compromise hoặc key bị thu hồi khẩn cấp | Cache cũ có thể còn chứa public key bị rút | Cần quy trình khóa khẩn cấp và cách invalidation/giới hạn TTL riêng |

**Không nên mặc định mọi lỗi fetch JWKS sẽ trả 401 hay 503**. HTTP response thực tế phụ thuộc giai đoạn lỗi, `AuthenticationException` hoặc lỗi hạ tầng, entry point, exception handler và phiên bản Spring Security. Điều bất biến về an toàn là **không cấp quyền truy cập khi không thể xác minh token bằng khóa tin cậy theo chính sách**.

### “Stale-while-error” có nên dùng không?

Một số kiến trúc cho phép tiếp tục dùng JWKS cũ trong thời gian ngắn nếu issuer tạm mất kết nối, nhằm bảo vệ tính sẵn sàng. Tuy nhiên:

- Dữ liệu cũ có thể không chứa khóa vừa được thêm, nên JWT mới không xác minh được.
- Dữ liệu cũ có thể chứa public key đã bị gỡ, nên các token ký bởi khóa cũ vẫn có thể được chấp nhận theo chính sách xác minh cục bộ.
- Nếu có yêu cầu thu hồi **khẩn cấp** do lộ private key, việc tiếp tục sử dụng cache cũ là rủi ro.

Vì vậy cần **giới hạn tuổi dữ liệu cũ** và xác định khi nào phải fail closed. Không thêm fallback “bỏ qua signature validation” khi JWKS endpoint lỗi.

### JWKS cache không phải hệ thống thu hồi access token

Trong xác thực JWT offline, API kiểm tra chữ ký/claims chứ thường không truy vấn trạng thái revoke của **từng token**. Việc bỏ public key khỏi JWKS có thể ảnh hưởng **toàn bộ JWT ký bằng khóa đó** khi các cache đã cập nhật, nhưng không phải cơ chế revocation có hiệu lực tức thì trên mọi instance. Nếu cần thu hồi token tức thời, hệ thống có thể cần introspection, revocation state, danh sách từ chối hoặc chiến lược thời hạn JWT ngắn.

## 12. Thao tác thủ công khi thay khóa khẩn cấp

Với rotation định kỳ, nên công bố public key mới trước khi đổi signer và giữ public key cũ đủ lâu. Với **nghi ngờ lộ private key**, nhu cầu an ninh có thể cao hơn yêu cầu duy trì token cũ:

1. Ngừng sử dụng private key bị ảnh hưởng để ký JWT mới.
2. Phát hành/công bố public key thay thế từ nguồn issuer đã được kiểm soát.
3. Xác định phương án vô hiệu hóa token ký bằng khóa cũ theo yêu cầu an ninh, chấp nhận rằng một số client có thể cần xin token mới.
4. **Invalidate cache JWKS** hoặc ép ứng dụng tái nạp dữ liệu theo cơ chế được hỗ trợ, tính đến tất cả instance và các proxy/CDN.
5. Theo dõi issuer/Resource Server và xác nhận token ký bằng khóa bị rút được xử lý đúng theo chính sách.

Không có một API chuẩn duy nhất “xóa cache JWKS của mọi instance Spring Security”. Cách invalidation phụ thuộc cache đang dùng: local cache của Nimbus, Spring Cache, proxy, CDN, triển khai rolling restart hoặc một cơ chế quản trị được thiết kế từ trước. Không nên khởi động lại một instance rồi cho rằng toàn bộ cụm đã cập nhật.

**Trường hợp lộ private key khác rotation bình thường:** có thể phải ngừng chấp nhận token còn hạn đã ký bằng khóa cũ để bảo vệ hệ thống. Đó là quyết định vận hành/bảo mật cần cơ chế nhất quán trên toàn cụm.

## 13. Quan sát và chẩn đoán cache JWKS

Khi xảy ra lỗi `401 Unauthorized` sau một đợt rotation, cần xác định lỗi nằm ở đâu:

~~~mermaid
flowchart TD
    A["API từ chối JWT sau key rotation"] --> B{"Token có kid nào?"}
    B --> C["Kiểm tra JWKS của issuer tin cậy"]
    C --> D{"Public key mới đã được công bố?"}
    D -- "Chưa" --> E["Sửa trình tự publish/sign ở Authorization Server"]
    D -- "Rồi" --> F{"Resource Server có cache phiên bản mới?"}
    F -- "Chưa" --> G["Xem TTL, cache miss, refresh, proxy/CDN"]
    F -- "Rồi" --> H{"Chữ ký và alg/kty phù hợp?"}
    H -- "Không" --> I["Kiểm tra signer, khóa và thuật toán"]
    H -- "Có" --> J["Kiểm tra issuer, exp, nbf, aud, profile"]
    J --> K["Kiểm tra scope và quyền nghiệp vụ"]
~~~

Các tín hiệu vận hành hữu ích:

| Tín hiệu | Điều có thể phát hiện |
| --- | --- |
| Số lần **fetch JWKS** và tỷ lệ lỗi/timeout | Issuer quá tải, mạng lỗi, refresh lặp lại |
| **Cache hit/miss**, tuổi entry nếu cache hỗ trợ metrics | TTL có phù hợp với lưu lượng và rotation |
| **Unknown `kid`** theo issuer đã xác minh/ngữ cảnh tin cậy | Key rotation chưa lan truyền hoặc request giả mạo gây tải |
| Thời gian xác minh JWT và thời gian fetch JWKS | Độ trễ do mạng/cold cache |
| Lỗi chữ ký, issuer, audience, expiry | Phân biệt lỗi khóa với lỗi policy token |
| Số replica đang dùng phiên bản cấu hình khóa/decoder nào | Sự không đồng nhất trong rolling deployment |

**Không ghi nguyên JWT hoặc access token vào log.** `kid` có thể hữu ích để chẩn đoán, nhưng nên giới hạn/tẩy sạch dữ liệu được ghi từ request không tin cậy, tránh log injection và cardinality metrics vô hạn. Đừng tạo metric label với mỗi `kid` ngẫu nhiên do attacker gửi.

### Các nguyên nhân phổ biến khi rotation tạo ra 401

- Issuer bắt đầu ký bằng K2 trước khi public K2 xuất hiện ở mọi JWKS endpoint/CDN.
- JWKS cache của API chứa K1 và chưa refresh khi thấy K2.
- Custom cache không có TTL hoặc không tương thích cơ chế refresh của decoder.
- JWT mới có `kid` khác giá trị JWKS, hoặc public key không khớp private key đang ký.
- `alg` của JWT khác thuật toán được Resource Server cho phép.
- Issuer gỡ K1 quá sớm trong lúc token K1 còn hạn.
- JWKS URI hoặc issuer được cấu hình sai ở một số replica.
- Kết nối TLS/timeout/proxy ngăn API tải JWKS.
- Chữ ký và JWK đúng nhưng JWT sai `aud`, `iss`, `exp` hoặc token profile.

Không nên “sửa” hàng loạt lỗi trên bằng cách vô hiệu hóa xác minh chữ ký hay nới lỏng audience/issuer.

## 14. Bảng tình huống cache và kết quả mong đợi

Giả sử:

- Issuer đáng tin: `https://auth.example.com/realms/shop`.
- Resource Server: **Orders API**.
- JWKS ban đầu chứa **K1**.
- Sau đó issuer công bố **K1 + K2** và bắt đầu ký bằng **K2**.
- Access token phải còn hạn, audience `orders-api` và đáp ứng điều kiện JWT/profile của API.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Token K1 hợp lệ, cache đang có public K1 | Xác minh cục bộ thành công nếu các điều kiện khác đều đúng |
| Token K2 hợp lệ, cache đã có public K2 | Xác minh thành công nếu các điều kiện khác đều đúng |
| Token K2 hợp lệ, cache chỉ có K1, refresh thành công | Xác minh sau khi lấy được public K2, nếu decoder hỗ trợ đường refresh này |
| Token K2 hợp lệ, cache chỉ có K1, refresh chưa xảy ra/không thành công | Không thể xác minh, phải từ chối request |
| Token `kid=K2` nhưng chữ ký giả | Từ chối dù public K2 có sẵn |
| Token K1 đã hết hạn nhưng public K1 vẫn trong cache | Từ chối do `exp`, không phụ thuộc khóa đang cache |
| Token K1 còn hạn nhưng public K1 bị gỡ và cache đã refresh chỉ còn K2 | Có thể không xác minh được token K1, chứng tỏ gỡ khóa quá sớm đối với rotation thông thường |
| JWKS không truy cập được, cache lạnh | Không xác minh được; không cho request đi qua |
| JWKS không truy cập được, cache chứa khóa tin cậy còn được phép sử dụng | Có thể tiếp tục xác minh JWT tương ứng tùy chính sách cache/decoder |
| Token hợp lệ và đúng khóa nhưng thiếu scope `orders.write` | Xác thực có thể thành công nhưng thao tác ghi bị 403 |

Bảng thể hiện **hành vi mong muốn theo nguyên tắc bảo mật**; thời điểm fetch, cache hit/miss và mã HTTP khi lỗi hạ tầng phụ thuộc cấu hình/phiên bản cụ thể.

## 15. Lưu ý khi kiểm tra tích hợp và triển khai thực tế

Để hiểu đúng cache JWKS, cần phân biệt hai loại kiểm tra:

**Kiểm tra xác thực token qua decoder thật:** dùng JWT ký bằng khóa thử nghiệm, JWKS server thử nghiệm và các tình huống K1 → K2; quan sát số lần tải JWKS, hành vi khi `kid` mới xuất hiện, lỗi fetch và thời gian TTL.

**Kiểm tra authorization:** dùng `Authentication` được tạo sẵn hoặc mock JWT để kiểm tra scope/endpoint/quyền nghiệp vụ. Các helper của Spring Security Test như `jwt()` thường bỏ qua việc tải JWKS và xác minh chữ ký thật, nên **không chứng minh** cache refresh hay key rotation hoạt động.

Một bộ tình huống thực tế nên bao gồm:

1. **Cold start:** cache trống, issuer hoạt động, token K1 hợp lệ.
2. **Cache hit:** nhiều request JWT K1 liên tiếp không tạo fetch JWKS tương ứng mỗi request.
3. **TTL expiration:** xác định request nào kích hoạt refresh sau TTL thực tế.
4. **Prepublish K2:** issuer công bố K1 + K2, API vẫn xác minh được token K1.
5. **Unknown `kid` K2:** quan sát decoder/cache có refresh trước khi TTL không.
6. **Remove K1 after overlap:** mọi token K1 hợp lệ đã hết hạn trước khi JWKS chỉ còn K2.
7. **Temporary outage:** phân biệt cache nóng/cold cache và lỗi fail closed.
8. **Concurrent requests:** nhiều request mới cùng `kid` không tạo fetch storm nếu giải pháp có coalescing/throttling.
9. **Bogus `kid` flood:** request giả không được quyền điều khiển bất kỳ JWKS URL ngoài allowlist.
10. **Bad JWT claims/signature:** cache có khóa vẫn không khiến token sai chữ ký, issuer, audience hoặc thời hạn được chấp nhận.

Với các trường hợp trên, cần quan sát luồng **HTTP fetch JWKS thật** và hành vi decoder đã được cấu hình, thay vì suy đoán từ log controller. Việc xây dựng/kích hoạt các kiểm tra tích hợp là công việc triển khai và QA riêng; bài học này giải thích cơ chế và các tình huống cần hiểu.

## 16. Những hiểu lầm thường gặp

**“JWKS cache TTL 5 phút nên JWT hết hạn sau 5 phút.”**  
Không. JWT lifetime được định nghĩa qua `exp` và chính sách cấp token của Authorization Server. JWKS TTL là độ tuổi dữ liệu **khóa công khai** trong cache.

**“Có `kid` mới là Nimbus chắc chắn tự tải lại ngay.”**  
Không có bảo đảm xuyên mọi phiên bản hoặc custom cache. Cần hiểu behavior thực tế, và nên **publish K2 trước khi ký** để giảm phụ thuộc vào refresh khi miss.

**“Chỉ cần xóa K1 khỏi JWKS là mọi token K1 bị vô hiệu hóa tức thì.”**  
Không. Các Resource Server có thể còn giữ K1 trong cache; việc gỡ khóa cũng có thể từ chối token hợp lệ chưa hết hạn trên những instance đã refresh.

**“Dùng HTTP `Cache-Control` là tự cấu hình TTL của Spring Security.”**  
Không nhất thiết. Header HTTP và cache bên trong Nimbus/Spring Cache có thể được quản lý độc lập.

**“`kid` chính là khóa công khai, nên không cần JWKS.”**  
Sai. `kid` chỉ là định danh/gợi ý chọn khóa, không chứa vật liệu cần thiết để xác minh chữ ký.

**“API mất kết nối JWKS thì cho request đi qua để giữ khả dụng.”**  
Không. Nếu chưa có khóa tin cậy để xác minh token, phải **fail closed**. Có được phép dùng cache stale với giới hạn nào hay không là chính sách riêng, không phải bỏ kiểm tra signature.

**“Có public key K2 trong JWKS là token K2 chắc chắn hợp lệ.”**  
Không. API vẫn phải xác minh chữ ký, thuật toán, issuer, audience, expiry, type/profile và quyền truy cập.

**“JWKS là nơi lưu refresh token.”**  
Không. JWKS công bố khóa (thường là khóa công khai) phục vụ JOSE/JWT; refresh token là thông tin xác thực riêng trong OAuth 2.0 do client sử dụng với Authorization Server khi được cấp.

## 17. Quy tắc thiết kế nên mang theo

Khi thiết kế Resource Server dựa trên JWT và JWKS, hãy xác định rõ:

1. **Nguồn khóa đáng tin cậy:** issuer nào được phép, JWKS URI lấy từ đâu, HTTPS/TLS và thuật toán nào được chấp nhận.
2. **Cache nằm ở tầng nào:** nội bộ decoder/Nimbus, Spring Cache, HTTP client hay CDN; thời gian sống và refresh thuộc quyền kiểm soát của ai.
3. **Cách xử lý khóa mới:** `kid` chưa biết có kích hoạt fetch không, tần suất/timeout/retry giới hạn thế nào.
4. **Lịch rotation:** publish public key mới trước khi đổi signer; giữ public key cũ đến khi token cũ cuối cùng không còn hợp lệ.
5. **Cách xử lý mất kết nối:** cache nóng, cache lạnh, stale policy và trường hợp key compromise đều cần quyết định fail closed rõ ràng.
6. **Điều kiện xác minh độc lập:** signature, issuer, audience, time, token profile và quyền nghiệp vụ vẫn bắt buộc dù JWKS đã được cache.
7. **Khả năng quan sát:** đo fetch, cache miss, unknown `kid`, độ trễ, lỗi fetch và tình trạng đồng bộ giữa replica mà không làm lộ token.

**Điểm cần nhớ:** JWKS cache giúp Spring Security Resource Server xác minh JWT hiệu quả và duy trì khả năng phục vụ trong giới hạn cho phép. Nhưng một cache đúng phải gắn với **vòng đời khóa của issuer**, **TTL/refresh đã được hiểu rõ theo phiên bản** và **quy trình rotation có khoảng chồng lấn**. Cách thiết kế an toàn là quản lý việc công bố và rút khóa chủ động, không phụ thuộc hoàn toàn vào giả định decoder sẽ tự làm mới đúng thời điểm.
