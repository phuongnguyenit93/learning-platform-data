# Scope versioning

## 1. Khi quyền thay đổi, vì sao scope cần được quản lý phiên bản?

Trong chương **Scope** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, chúng ta nghiên cứu cách Authorization Server (AS) cấp phạm vi truy cập cho client, cách resource server (RS) kiểm tra scope trong access token, và cách những phạm vi đó tương tác với issuer, audience, subject, thời hạn và quyền đối với tài nguyên. **Scope versioning** là quá trình quản lý sự thay đổi của **tên scope, ý nghĩa quyền và hợp đồng cấp/chấp nhận scope** khi một hệ thống phát triển qua nhiều phiên bản.

Giả sử Orders API ban đầu chỉ công bố một scope:

~~~text
orders:read
~~~

Scope này cho phép các ứng dụng đã được cấp quyền đọc thông tin đơn hàng mà chủ thể có thể xem. Sau một thời gian, API cần tách **đọc trạng thái đơn hàng** khỏi **đọc địa chỉ giao hàng** vì địa chỉ là dữ liệu cá nhân nhạy cảm hơn.

Nếu cứ giữ scope cũ và lặng lẽ mở rộng nó để đọc thêm dữ liệu, các client từng được phê duyệt có thể được tăng quyền mà không có bước cấp quyền mới. Nếu lặng lẽ thu hẹp scope cũ, một số client đang hoạt động có thể hỏng. Nếu đổi tên scope ở client nhưng AS không cấp, hoặc RS chưa chấp nhận, request sẽ lỗi. Đó là lý do thay đổi phạm vi phải được **thiết kế, phát hành và chuyển đổi** như một hợp đồng bảo mật.

Scope versioning nhằm đạt hai mục tiêu:

1. **Tương thích:** client, Authorization Server và resource server hiểu đúng quyền đã được cấp ở từng giai đoạn.
2. **Không leo thang quyền:** các grant, consent và token cũ không tự nhận các khả năng mới mà chúng chưa được phê duyệt.

**Điều then chốt:** OAuth 2.0 có cơ chế yêu cầu và biểu diễn scope, nhưng **không tự quy định hậu tố phiên bản như v1, v2 hoặc quy tắc kế thừa giữa các tên scope**. Ý nghĩa, phiên bản và chuyển đổi được định nghĩa bởi API/Authorization Server.

### Bạn sẽ học được gì?

- Phân biệt version của API với version của scope và policy.
- Chọn lúc nào giữ scope, lúc nào thêm tên mới, lúc nào tách quyền.
- Thiết kế rollout/rollback, migration của client, consent và grant cũ.
- Hiểu ảnh hưởng tới JWT, opaque token, access token, refresh token và token exchange.
- Kiểm thử chống cấp nhầm quyền, bỏ qua audience, và so khớp scope không chính xác.

## 2. Ôn lại ngữ nghĩa scope trong OAuth 2.0

Client có thể yêu cầu một hoặc nhiều scope, ví dụ:

~~~text
scope=orders:summary:read orders:shipping:read
~~~

Trong một URL hoặc form, dấu cách phải được mã hóa đúng quy tắc. AS kiểm tra chính sách của client, resource owner, consent hoặc quyền quản trị và quyết định **scope thực tế được cấp**. Scope được cấp có thể hẹp hơn scope được yêu cầu; client phải xử lý kết quả thay vì mặc định request đồng nghĩa với grant.

Payload JWT access token **minh họa**:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-271",
  "aud": "https://orders.example.com",
  "client_id": "shop-web",
  "scope": "orders:summary:read",
  "iat": 1893492000,
  "exp": 1893492900
}
~~~

Đây là payload đã trình bày để học, **không phải JWT hoàn chỉnh có chữ ký**. Trong profile JWT access token của RFC 9068, claim **scope** khi có mặt thể hiện các scope bằng một chuỗi cách nhau bằng dấu cách. Với **opaque access token**, resource server có thể nhận tập scope từ introspection đáng tin cậy mà không cần giải mã JWT.

### 2.1. Tên scope có nghĩa chính xác theo hợp đồng

| Quy tắc | Hệ quả thực tế |
|---|---|
| Scope name là giá trị **phân biệt chữ hoa/chữ thường** | ORDERS:READ không tự đồng nghĩa với orders:read |
| Các scope tách bằng **dấu cách** trong biểu diễn OAuth | Không coi toàn chuỗi nhiều scope là một quyền duy nhất |
| OAuth không tự hiểu v1, v2, dấu hai chấm hoặc dấu chấm | Tên orders:read:v2 là một scope riêng theo hợp đồng sản phẩm |
| Không có wildcard scope tiêu chuẩn | orders:* không mặc nhiên bao hàm orders:read hay orders:delete |
| Scope có thể được cấp theo chính sách của AS | Client xin quyền không có nghĩa AS bắt buộc cấp quyền |
| Scope của token không chứng minh quyền trên từng đối tượng | RS vẫn phải kiểm tra owner, tenant, quan hệ và action cụ thể |

**Không kiểm tra scope bằng phép so khớp tiền tố.** Ví dụ so khớp chuỗi bắt đầu bằng orders:read có thể chấp nhận nhầm orders:read:privileged nếu sản phẩm đặt tên như vậy. Nên kiểm tra **phần tử scope nguyên vẹn** đã được tách và xác minh.

### 2.2. Scope, audience và resource không đồng nhất

Resource server chỉ nên nhận token có **issuer đáng tin**, **audience phù hợp API hiện tại**, đúng loại access token, còn thời hạn và được kiểm tra chữ ký hoặc active state theo định dạng token.

Ví dụ:

~~~text
iss = https://login.example.com
aud = https://orders.example.com
scope = orders:summary:read
~~~

Các điều kiện đó cho phép đánh giá quyền đọc tóm tắt đơn hàng. Chúng **không tự cho phép** đọc đơn hàng của người khác. API phải xác nhận principal được phép đọc **đúng order ID**. Versioning scope không thay thế kiểm tra resource/action.

## 3. Phân biệt bốn loại thay đổi

| Loại thay đổi | Ví dụ | Có phải đổi tên scope? |
|---|---|---|
| **API versioning** | GET /v1/orders/{id} thành GET /v2/orders/{id} | Không bắt buộc nếu quyền giữ nguyên |
| **Scope naming versioning** | reports:export:v1 thành reports:export:v2 | Có: mỗi tên là một scope riêng |
| **Scope semantics versioning** | Đọc tóm tắt được tách khỏi đọc địa chỉ giao hàng | Thường nên có quyền riêng để tránh nhập nhằng |
| **Policy versioning** | Quy tắc owner, trạng thái đơn hàng hoặc tenant thay đổi | Có thể giữ scope và cập nhật policy theo kiểm soát |

**Không có quy tắc một phiên bản URL phải tương ứng một phiên bản scope.** API có thể tăng từ v1 lên v2 chỉ để đổi JSON response nhưng vẫn giữ phạm vi quyền cũ. Ngược lại, endpoint giữ nguyên đường dẫn có thể cần scope mới khi thao tác đòi quyền nhạy cảm hơn.

### 3.1. Khi nào nên giữ tên scope?

Có thể giữ tên nếu **ý nghĩa quyền đã công bố vẫn như cũ**, chẳng hạn:

- Cải thiện hiệu năng, đổi tầng lưu trữ hoặc tối ưu code.
- Đổi tên trường JSON không tăng mức truy cập dữ liệu.
- Thay một endpoint bằng endpoint mới nhưng cùng năng lực nghiệp vụ.
- Sửa việc thực thi để đúng chính sách vốn đã công bố, đồng thời quản lý tác động tương thích.

Nếu sửa một lỗi phân quyền khiến client từng khai thác hành vi quá quyền ngừng hoạt động, không nên duy trì lỗ hổng vì lý do tương thích. Cần sửa theo mức độ rủi ro và thông báo hợp lý.

### 3.2. Khi nào nên tạo scope mới?

Nên tạo scope mới khi:

- Thêm quyền đọc dữ liệu nhạy cảm hơn, ví dụ số định danh, thông tin thanh toán hoặc địa chỉ giao hàng.
- Một scope rộng được tách thành các quyền nhỏ để thực thi **least privilege**.
- Thêm hành động độc lập như export, publish, approve, delete hoặc share.
- Cần consent hoặc phê duyệt quản trị mới.
- Hai loại client phải được cấp các quyền khác nhau trên cùng API.

Tên mô tả năng lực thường rõ hơn số phiên bản:

~~~text
orders:summary:read
orders:shipping:read
orders:items:read
orders:export
~~~

Hậu tố v2 có thể phù hợp khi cần giữ hai hợp đồng song song, nhưng **reports:export:v2 không tự cho người đọc biết v2 rộng/hẹp hơn v1**. Phải có tài liệu so sánh rõ ràng.

## 4. Ví dụ xuyên suốt: chuyển Orders API sang quyền chi tiết hơn

Hệ thống cũ có:

~~~http
GET /v1/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <LEGACY_ACCESS_TOKEN>
~~~

Scope cũ **orders:read** cho phép trả về thông tin đơn hàng theo hợp đồng v1, gồm trạng thái, các mặt hàng và địa chỉ giao hàng cho chủ thể có quyền trên đơn hàng đó.

Phiên bản API mới tách dữ liệu:

| Scope | Ý nghĩa được công bố | Endpoint dùng scope |
|---|---|---|
| orders:read (legacy) | Đọc dữ liệu đơn hàng theo hợp đồng v1 | GET /v1/orders/{id} trong thời gian hỗ trợ |
| orders:summary:read | Đọc trạng thái, tổng tiền và thông tin tóm tắt | GET /v2/orders/{id}/summary |
| orders:shipping:read | Đọc thông tin giao hàng nhạy cảm | GET /v2/orders/{id}/shipping |

Các scope mới yêu cầu được AS cấp theo chính sách client/grant/consent phù hợp. **Không tự chuyển scope legacy thành cả hai scope mới** vì việc đó có thể bỏ qua mục tiêu tách quyền.

### 4.1. Các request phải có kết quả khác nhau

~~~text
Token A: scope = orders:read
GET /v1/orders/order-721
  => Có thể ALLOW nếu người gọi có quyền và endpoint legacy còn hỗ trợ.

GET /v2/orders/order-721/shipping
  => DENY vì không có orders:shipping:read.
~~~

~~~text
Token B: scope = orders:summary:read
GET /v2/orders/order-721/summary
  => Có thể ALLOW nếu người gọi có quyền trên order-721.

GET /v2/orders/order-721/shipping
  => DENY vì thiếu orders:shipping:read.
~~~

~~~text
Token C: scope = orders:summary:read orders:shipping:read
GET /v2/orders/order-721/shipping
  => Chỉ ALLOW nếu đúng audience và người gọi được phép xem shipping.
~~~

Điều kiện **có thể ALLOW** còn phụ thuộc chữ ký/active token, issuer, thời gian, tenant và ownership. Alice có scope shipping vẫn không được đọc địa chỉ của đơn hàng thuộc Bob nếu không được ủy quyền.

### 4.2. Luồng cấp scope mới

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant C as Client shop-web
    participant AS as Authorization Server
    participant RS as Orders API
    U->>C: Muốn xem đơn hàng
    C->>AS: Yêu cầu orders:summary:read
    AS->>AS: Kiểm tra client, grant, consent hoặc policy
    AS-->>C: Access token với scopes thực tế được cấp
    C->>RS: GET /v2/orders/order-721/summary + Bearer token
    RS->>RS: Xác minh iss, aud, signature/active, exp và token type
    RS->>RS: Kiểm tra scope và quyền của Alice trên order-721
    RS-->>C: Dữ liệu được phép hoặc lỗi
~~~

Trong Authorization Code + PKCE, client cần thực hiện toàn bộ quy tắc bảo vệ authorization code, redirect URI và xác thực người dùng theo hệ thống. Với client credentials, AS kiểm tra chính sách của ứng dụng/workload; không bắt buộc có người dùng cuối hay consent tại thời điểm gọi.

## 5. Ba chiến lược thiết kế scope versioning

### 5.1. Chiến lược A: scope mô tả một khả năng ổn định

Ví dụ:

~~~text
orders:summary:read
orders:shipping:read
orders:delete
orders:export
~~~

**Ưu điểm:** tên quyền gắn với hành động, dễ đánh giá consent, review và kiểm toán. Các phiên bản API có thể dùng lại nếu phạm vi thực chất không đổi.

**Nhược điểm:** khi phạm vi quyền vẫn bị thay đổi, nhóm phát triển phải xem xét thêm tên mới hoặc sửa hợp đồng; không được mặc định tên cũ có ý nghĩa mới.

**Khuyến nghị:** đây thường là cách dễ bảo trì khi có thể chia quyền thành các hành động nhỏ rõ ràng.

### 5.2. Chiến lược B: phiên bản nằm ngay trong tên scope

Ví dụ:

~~~text
reports:export:v1
reports:export:v2
~~~

**Ưu điểm:** hai hợp đồng được nhận diện độc lập và có thể chạy song song trong giai đoạn chuyển đổi.

**Nhược điểm:** số phiên bản có thể tăng không kiểm soát; người đọc tên scope khó biết phạm vi chính xác. V2 **không mặc định là siêu tập của v1**.

Điều bắt buộc khi dùng cách này:

1. Đặc tả từng scope cho phép action và loại dữ liệu nào.
2. Định nghĩa AS được cấp scope cho client/grant nào.
3. Định nghĩa RS nào chấp nhận scope, cho endpoint/action nào.
4. Không tự chuyển grant v1 thành v2.
5. Đặt mốc deprecation/sunset và kiểm thử hành vi legacy.

### 5.3. Chiến lược C: giữ tên scope, version chính sách

Ví dụ scope **orders:read** vẫn mang nghĩa đọc những đơn hàng người gọi được phép, còn quyền theo tenant, project, owner hoặc trạng thái do PDP/policy engine quyết định.

Một policy **minh họa**, không phải định dạng chuẩn OAuth:

~~~yaml
policy: orders-read
revision: 2026-11
action: order:read
conditions:
  - same-tenant-or-explicit-share
  - owner-or-authorized-delegate
~~~

Cách này phù hợp khi **ý nghĩa scope không thay đổi** nhưng dữ liệu quan hệ, quy tắc tổ chức hoặc cơ chế authorization cần được cải tiến. Phiên bản policy không nên trở thành cách âm thầm mở rộng quyền đã cấp bởi một scope.

### 5.4. Lựa chọn theo loại thay đổi

| Tình huống | Hướng giải quyết |
|---|---|
| API thay đổi schema, không đổi khả năng được phép | Giữ scope, version endpoint độc lập |
| Thêm quyền đọc dữ liệu nhạy cảm | Thêm scope mới và cấp quyền đúng quy trình |
| Một scope quá rộng cần chia nhỏ | Tách thành các scope theo action/resource |
| Hợp đồng cũ và mới phải tồn tại song song | Có thể dùng v1/v2 trong tên và giới hạn thời gian |
| Thay đổi ownership, role, membership | Cập nhật/version policy thực thi |
| Alias scope cũ sang scope mới | Chỉ dùng nếu chứng minh tương đương quyền, có hạn gỡ bỏ |

## 6. Thiết kế scope registry và hợp đồng AS–RS

Để tránh AS cấp một quyền nhưng RS diễn giải quyền khác, nên quản lý một **scope registry** hoặc hợp đồng quyền được version theo quy trình phát hành.

| Thuộc tính | Ví dụ | Công dụng |
|---|---|---|
| scope_name | orders:shipping:read | Định danh quyền cần so khớp chính xác |
| description | Xem địa chỉ giao hàng | Hướng dẫn client, người dùng và quản trị |
| audience | https://orders.example.com | RS dự kiến sử dụng scope |
| action | order:shipping:read | Hành động mà policy RS kiểm tra |
| data_sensitivity | Personal data | Mức bảo vệ cần thiết |
| eligible_clients | Các client đã được phê duyệt | Giới hạn nơi AS có thể cấp |
| consent_policy | User consent hoặc admin approval | Điều kiện cấp quyền |
| introduced_at | Phiên bản phát hành nội bộ | Truy vết thay đổi |
| deprecated_at | Mốc bắt đầu chuyển đổi | Cảnh báo và truyền thông |
| retired_at | Mốc ngừng chấp nhận | Vòng đời kết thúc |
| owner | Nhóm sở hữu API | Trách nhiệm thay đổi |

Registry phải làm rõ **hai chiều khác nhau**:

- Scope còn được **xin và cấp mới** tại AS hay không.
- Access token **đã phát hành** với scope đó còn được RS chấp nhận tại endpoint nào, trong thời gian nào.

Xóa scope khỏi cấu hình đăng ký client không tự làm một JWT đã cấp mất hiệu lực. Ngược lại, RS từ chối scope cũ trước khi client nâng cấp có thể gây gián đoạn.

### 6.1. Quy tắc endpoint phải cụ thể

~~~yaml
# Hợp đồng minh họa, không phải cấu hình dự án thật.
audience: https://orders.example.com
routes:
  legacy-order:
    path: /v1/orders/{id}
    action: order:read:legacy
    required_scope: orders:read
  summary:
    path: /v2/orders/{id}/summary
    action: order:summary:read
    required_scope: orders:summary:read
  shipping:
    path: /v2/orders/{id}/shipping
    action: order:shipping:read
    required_scope: orders:shipping:read
~~~

Ở cả ba đường đi, RS còn phải kiểm tra **quyền trên đơn hàng cụ thể** theo principal, tenant, ownership và chính sách dữ liệu. Tên scope không thay cho những quyết định đó.

## 7. Kế hoạch chuyển đổi theo nhiều giai đoạn

| Giai đoạn | Authorization Server | Resource Server | Client và vận hành |
|---|---|---|---|
| **Thiết kế** | Tạo scope mới và policy cấp | Ánh xạ scope tới action/endpoint | Kiểm kê tích hợp và công bố hợp đồng |
| **Chuẩn bị** | Cấp scope mới cho client được phê duyệt | Thêm endpoint mới và kiểm tra scope mới | Kiểm thử token, consent và quyền tài nguyên |
| **Chuyển đổi** | Cấp đúng scope thực tế theo grant | Duy trì legacy có giới hạn | Client yêu cầu lại quyền mới khi cần |
| **Ngừng cấp scope cũ** | Không cấp legacy cho grant mới theo lịch | Tạm giữ quy tắc nhận legacy tại v1 | Xác nhận client cũ đã nâng cấp |
| **Retire scope cũ** | Gỡ cấu hình cấp legacy | Dừng nhận tại endpoint liên quan | Gỡ code và tài liệu legacy |

Thứ tự cụ thể có thể thay đổi theo sản phẩm, nhưng AS, RS và client phải **được điều phối**. Không thể coi deploy một service là bằng chứng mọi client đã nhận grant mới.

### 7.1. Không dùng fallback quyền rộng

Trong migration, không nên viết:

~~~text
ALLOW shipping nếu token có orders:read
            OR token có orders:shipping:read
~~~

Khi mục tiêu là yêu cầu quyền riêng cho địa chỉ giao hàng, biểu thức trên cho client legacy một đường vòng vào endpoint nhạy cảm. Một alias chỉ hợp lệ nếu **hai scope thực sự tương đương phạm vi** và có lý do/thời hạn rõ ràng.

### 7.2. Đo lường trước khi sunset

Cần quan sát:

- Client nào vẫn **request** scope legacy.
- AS còn **issue** access token chứa scope legacy cho client/grant nào.
- RS còn **accept** request nhờ scope legacy ở endpoint nào.
- Tỷ lệ lỗi **invalid_scope**, **invalid_token**, **insufficient_scope**, 401 và 403.
- Các job chạy không thường xuyên hoặc tích hợp bên thứ ba chưa xuất hiện trong thời gian quan sát ngắn.

Log chỉ cần metadata như client_id, issuer, audience, scope name, endpoint, decision và trace ID trong phạm vi bảo vệ dữ liệu; **không ghi nguyên access token/refresh token**.

### 7.3. Rollback an toàn

Nếu chuyển đổi gây lỗi:

1. Có thể duy trì endpoint legacy đã được cho phép trong một khoảng hỗ trợ xác định.
2. Có thể rollback phần mềm client hoặc tạm dừng chức năng cần quyền mới.
3. Nếu rollback policy, chỉ quay về chính sách đã được đánh giá an toàn.
4. Nếu phát hiện đã cấp nhầm quyền quá rộng, cần giảm quyền/thu hồi phù hợp; không rollback bằng cách cho mọi client dùng legacy ở API mới.

Rollback phải bảo vệ **tính đúng của quyền** song song với tính sẵn sàng.

## 8. Access token và refresh token khi scope đổi

### 8.1. JWT access token đã phát hành

Giả sử JWT cũ chứa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-271",
  "aud": "https://orders.example.com",
  "scope": "orders:read",
  "iat": 1893492000,
  "exp": 1893492900
}
~~~

Token này đã được phát hành với scope legacy. Việc triển khai scope mới ở AS hoặc RS **không tự sửa payload đã ký**. Nếu RS xác minh JWT offline và vẫn hỗ trợ endpoint v1, token có thể còn được chấp nhận tới khi hết hạn, trừ khi có cơ chế kiểm tra trạng thái hoặc chặn token bổ sung.

**Opaque token** thường được xác minh qua introspection; thay đổi trạng thái/phạm vi trong kho token có thể được phản ánh tùy cách AS quản lý và TTL cache. Không nên âm thầm mở rộng quyền của một token opaque đã cấp chỉ vì dễ sửa metadata server-side.

### 8.2. Refresh token không phải vé tự động xin scope mới

Theo OAuth 2.0 (RFC 6749), khi client gửi yêu cầu refresh có tham số scope, **tập scope được yêu cầu không được bao gồm phạm vi chưa được cấp ban đầu**. Khi không gửi tham số scope, phạm vi được hiểu bằng phạm vi grant ban đầu theo quy tắc của giao thức.

~~~text
Grant ban đầu: orders:read
Refresh xin: orders:shipping:read
=> Không được tự mở rộng grant bằng refresh token cũ.
~~~

Nếu scope mới đại diện cho quyền bổ sung, cần luồng authorization, consent hoặc phê duyệt client/admin thích hợp. Đối với client credentials, AS cũng phải kiểm tra chính sách cho workload/client. **Refresh token rotation** để chống reuse là vấn đề vòng đời credential, **khác với scope migration**.

### 8.3. Thời gian hết hạn, cutover và revoke

Khi quyết định dừng nhận scope legacy, phải xét:

- **iat/nbf/exp** và TTL còn lại của các access token.
- **Thời gian cache introspection** của opaque token.
- **Refresh token/grant cũ** có thể tạo access token legacy mới nếu AS chưa dừng cấp.
- Quyền động đã thay đổi, ví dụ user rời tenant hoặc bị thu hồi membership.
- Khả năng cần vô hiệu hóa ngay access token bị lộ hoặc được cấp quá quyền.

Thu hồi refresh token không tự làm mọi JWT access token còn hạn mất hiệu lực nếu resource server chỉ xác minh offline. Nếu cần dừng ngay quyền cũ, cần policy cưỡng chế tại RS và/hoặc cơ chế revoke/denylist/session state theo kiến trúc.

### 8.4. Scope versioning không thay thế bảo vệ token

Access token bearer có thể bị sử dụng lại nếu bị đánh cắp trong thời gian còn hiệu lực. Ngoài versioning scope, hệ thống cần **TLS, giới hạn scope/audience/TTL, lưu trữ token an toàn, không log secrets, refresh token rotation và phát hiện reuse**. Khi phù hợp, DPoP hoặc mTLS sender-constrained access token giúp giảm khả năng dùng lại token bị lộ. Token có scope mới vẫn phải được kiểm tra quyền resource/action.

## 9. Nhiều issuer, audience, OIDC và delegation

### 9.1. Cùng tên scope không có nghĩa cùng quyền ở mọi issuer/API

~~~text
Token A:
  iss = https://login.example.com
  aud = https://orders.example.com
  scope = orders:summary:read

Token B:
  iss = https://login.example.com
  aud = https://billing.example.com
  scope = invoices:read
~~~

Billing API không thể nhận token A chỉ vì issuer đã được tin cậy. Mỗi RS phải kiểm tra **audience và scope theo hợp đồng của chính mình**. Khi có nhiều issuer, cùng chuỗi scope có thể được định nghĩa khác nhau; phải ràng buộc issuer/profile rõ ràng.

### 9.2. User delegated scope và application scope

Một client sử dụng Authorization Code + PKCE có thể mang quyền được cấp trong ngữ cảnh người dùng. Một worker dùng Client Credentials nhận token theo quyền của **ứng dụng**. Hãy phân biệt loại principal và grant; không gán quyền người dùng cho client credentials.

Với token exchange/on-behalf-of giữa hai dịch vụ, downstream token phải đúng resource/audience, scope và chính sách delegation. **Một service không được dùng service token nhiều quyền hơn để đáp ứng yêu cầu vượt quyền của caller**. Đó có thể là lỗi confused deputy, ngay cả khi token được ký hợp lệ.

### 9.3. OIDC scopes không phải nơi tùy ý đặt phiên bản

Các scope OIDC như **openid**, **profile**, **email** có ý nghĩa theo đặc tả. Không tự đổi openid thành openid:v2 rồi mong các OIDC client chuẩn hiểu nó. Quản lý scope nghiệp vụ của API bằng hợp đồng riêng, đồng thời nhớ:

- **ID token** dành cho client xác minh kết quả đăng nhập, không thay access token để gọi API.
- **Access token** dành cho resource server đúng audience.
- **Refresh token** dùng tại token endpoint, không gửi cho resource server.

## 10. Triển khai và kiểm tra bằng Java/Spring Security

### 10.1. Kiểm tra scope chính xác

Ví dụ sai:

~~~java
// SAI: một chuỗi bắt đầu bằng orders:read chưa chắc là scope orders:read.
boolean allowed = scopeString.startsWith("orders:read");
~~~

Điều này có thể nhận nhầm scope khác như orders:read:privileged. Sử dụng tập scope đã được phân tích theo giao thức **sau khi xác minh token**:

~~~java
// Pseudocode: VerifiedAccessToken là kiểu của ứng dụng.
boolean hasScope(VerifiedAccessToken token, String requiredScope) {
    return token.scopes().contains(requiredScope);
}
~~~

Không tự tin claims từ JWT chỉ được decode Base64 mà chưa xác minh issuer, chữ ký/active, audience và thời hạn.

### 10.2. Tách quyền legacy và quyền mới ở từng endpoint

~~~java
// Mã minh họa: cần cấu hình method security và scope converter phù hợp.
@PreAuthorize("hasAuthority('SCOPE_orders:summary:read')")
@GetMapping("/v2/orders/{id}/summary")
public OrderSummary readSummary(
        @PathVariable String id,
        Authentication authentication) {

    VerifiedPrincipal principal =
        principalFactory.fromVerifiedAuthentication(authentication);
    return orders.readSummaryAuthorized(principal, id);
}
~~~

Với Spring Security OAuth2 Resource Server, **SCOPE_** là tiền tố authority thường dùng khi map scope, phụ thuộc cấu hình thực tế. Cần bổ sung kiểm tra **audience phù hợp** trong JwtDecoder/validators hoặc cơ chế opaque token; chỉ cấu hình issuer không đảm bảo mọi policy audience nghiệp vụ.

Hàm **readSummaryAuthorized** vẫn phải kiểm tra người gọi có quyền trên **đúng order ID**:

~~~java
// Pseudocode: các lớp domain/policy do ứng dụng định nghĩa.
OrderSummary readSummaryAuthorized(VerifiedPrincipal caller, String id) {
    Order order = repository.findById(id)
        .orElseThrow(NotFoundException::new);

    if (!policy.canReadSummary(caller, order)) {
        throw new ForbiddenException();
    }
    return mapper.toSummary(order);
}
~~~

Trong giai đoạn chuyển đổi, endpoint v1 có thể được bảo vệ bởi authority **SCOPE_orders:read** theo hợp đồng legacy. Endpoint v2 shipping phải yêu cầu **SCOPE_orders:shipping:read** và không dùng OR fallback vô thời hạn. Nếu có đường vào qua background job, GraphQL hoặc bulk API, các đường đó cũng phải thực thi cùng policy.

## 11. Ma trận kiểm thử scope versioning

Giả định Alice sở hữu order-721, không có quyền xem order-999; mọi token trong những hàng không nêu ngoại lệ đều đã xác minh issuer, audience và thời hạn:

| Scope trong token | Request | Kỳ vọng |
|---|---|---|
| orders:read | GET /v1/orders/order-721 | Có thể ALLOW khi v1 còn hỗ trợ |
| orders:read | GET /v2/orders/order-721/summary | **DENY** vì chưa có scope mới |
| orders:read | GET /v2/orders/order-721/shipping | **DENY** |
| orders:summary:read | GET /v2/orders/order-721/summary | Có thể ALLOW |
| orders:summary:read | GET /v2/orders/order-721/shipping | **DENY** |
| orders:shipping:read | GET /v2/orders/order-721/shipping | Có thể ALLOW nếu policy đồng ý |
| orders:shipping:read | GET /v2/orders/order-999/shipping | **DENY** vì sai resource |
| orders:summary:read orders:shipping:read | GET /v2/orders/order-721/shipping | Có thể ALLOW theo policy |
| orders:shipping:read với aud là Billing API | GET /v2/orders/order-721/shipping | **DENY** vì audience sai |
| orders:shipping:read với issuer chưa được tin cậy | GET /v2/orders/order-721/shipping | **DENY** vì issuer sai |

**ALLOW trong bảng là kết quả có điều kiện**, không có nghĩa bỏ qua tenant, role, consent, ownership hoặc trạng thái đơn hàng.

### 11.1. Kiểm thử cấp quyền tại Authorization Server

- Client chưa được phê duyệt xin scope mới: **không cấp quyền vượt chính sách**.
- Client được phê duyệt và hoàn tất consent khi cần: AS có thể cấp scope mới đúng grant.
- Refresh token grant cũ chỉ có orders:read xin orders:shipping:read: **không mở rộng quyền**.
- Client Credentials của service A xin scope không dành cho nó: AS từ chối theo registration/policy.
- Scope khác chữ hoa/chữ thường hoặc sai chính tả: không tự quy đổi thành quyền khác.
- Khi AS ngừng cấp legacy, RS vẫn phải xử lý token legacy đã cấp theo thời gian chuyển đổi/chính sách bảo mật.

### 11.2. Kiểm thử tương thích và hệ thống

- JWT cũ còn hạn không tự mang scope mới.
- Token có cả hai loại scope không làm endpoint v2 tự nhận legacy.
- Opaque introspection cache không giữ quyền đã thu hồi vượt giới hạn policy.
- Hệ thống nhiều issuer/audience không dùng một scope chung để vượt ranh giới.
- Danh sách, export, bulk và tác vụ bất đồng bộ vẫn kiểm tra quyền theo từng resource.
- Client tích hợp ít dùng cũng được kiểm tra trước khi loại bỏ legacy.
- Rollback không mở lại scope cũ tại endpoint nhạy cảm.
- Logs chỉ chứa metadata, không chứa access token hoặc refresh token.

Trong OAuth, AS có thể trả **invalid_scope** cho yêu cầu scope không hợp lệ, không được biết hoặc vượt chính sách. Tại RS, thiếu scope cho action thường là **403 Forbidden** với **insufficient_scope** khi áp dụng RFC 6750; token không hợp lệ hoặc sai audience thường là **401 Unauthorized**/invalid_token theo giao thức và contract API.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Đổi ý nghĩa scope cũ mà không có hợp đồng | Client cũ bị tăng/giảm quyền ngoài dự kiến | Tạo scope mới nếu quyền thay đổi đáng kể |
| Tăng phiên bản scope mỗi lần đổi URL API | Bùng nổ danh mục scope | Tách API version khỏi permission version |
| Coi scope v2 luôn bao hàm v1 | Cấp quyền sai hoặc mở rộng ngầm | Không mặc định kế thừa; mô tả quyền rõ |
| Cấp scope mới qua refresh token grant cũ | Tăng quyền không được phê duyệt | Tuân thủ giới hạn grant và flow mới |
| Dùng legacy OR new ở endpoint nhạy cảm | Lách quyền mới | Chỉ alias khi tương đương quyền, có sunset |
| So scope bằng startsWith | Nhầm scope đặc quyền | So tên scope nguyên vẹn |
| Chỉ kiểm tra scope, bỏ qua aud/iss | Token API khác được chấp nhận | Xác minh toàn bộ access token |
| Chỉ kiểm tra scope, bỏ qua tenant/owner | BOLA/IDOR, lộ dữ liệu | Authorization theo resource và action |
| Ngừng chấp nhận legacy trước khi client chuyển đổi | Tăng 403 hàng loạt | Rollout theo pha, đo traffic và thông báo |
| Ngừng cấp legacy nhưng tưởng JWT cũ đã hết quyền | Token offline còn sống tới exp | Tính TTL và revoke/policy RS |
| Log token để phân tích migration | Rò rỉ bearer credential | Log metadata có kiểm soát |

## 13. Tình huống suy luận

### Tình huống A: URL đổi, quyền giữ nguyên

Orders API thay GET /v1/orders/{id} thành GET /v2/orders/{id}, chỉ đổi tên trường JSON nhưng giữ nguyên chủ thể, loại dữ liệu và quyền. **Có bắt buộc đổi orders:read thành orders:read:v2 không?**

**Không.** API version và scope version độc lập nếu phạm vi cấp quyền giữ nguyên.

### Tình huống B: thêm dữ liệu cá nhân

Phiên bản mới trả địa chỉ giao hàng chi tiết, trong khi scope cũ chỉ cho xem tóm tắt. **Có nên giữ scope cũ để tiện tương thích?**

**Không nên mở rộng ngầm.** Cần scope/quyền mới và chính sách cấp quyền phù hợp.

### Tình huống C: refresh token cũ

Client đã có grant orders:read, giữ refresh token hợp lệ và xin orders:shipping:read lúc refresh. **AS có thể cấp vì client đã xác thực không?**

**Không.** Refresh request không được tăng phạm vi so với grant ban đầu theo RFC 6749. Client cần được cấp quyền mới đúng quy trình.

### Tình huống D: JWT legacy còn hạn

AS dừng cấp orders:read hôm nay, nhưng JWT đã ký có scope đó còn hạn 10 phút. **JWT tự hết tác dụng ngay không?**

**Không nhất thiết.** RS offline vẫn có thể nhận token theo rule legacy tới khi exp, trừ khi có cơ chế chặn hoặc đổi policy RS.

### Tình huống E: khác audience

Một token được cấp cho Billing API có scope invoices:read. Client gửi token đó sang Orders API vì các API cùng tin một issuer. **Có nên chấp nhận không?**

**Không.** Resource server phải kiểm tra audience dành cho mình trước khi đánh giá scope.

### Tình huống F: scope đúng nhưng resource sai

Alice có orders:shipping:read nhưng yêu cầu địa chỉ giao hàng của đơn hàng Bob. **Có được phép không?**

**Không**, trừ khi Alice có quyền nghiệp vụ thích hợp trên đơn hàng của Bob.

### Tình huống G: rollback bằng alias rộng

Đội phát triển cho phép cả reports:export:v1 lẫn v2 gọi endpoint xuất dữ liệu nhạy cảm mới, dù v1 không từng cho loại dữ liệu đó. **Rủi ro gì?**

**Client giữ grant v1 được truy cập thêm dữ liệu không được cấp.** Cần bỏ alias hoặc giữ hành vi legacy trong phạm vi quyền cũ, không biến scope cũ thành quyền mới.

## 14. Checklist quyết định trước khi phát hành scope mới

1. **Đã đổi cái gì?** API schema, URL, khả năng, dữ liệu, đối tượng hay policy?
2. **Ý nghĩa quyền có tăng hoặc giảm không?** Client cũ có nhận quyền vượt grant không?
3. **Tên nào mô tả rõ nhất?** Scope theo hành động hay hậu tố v1/v2 có tài liệu đi kèm?
4. **AS cấp cho ai?** Client, user/delegated actor, workload, consent, admin approval và audience nào?
5. **RS thực thi thế nào?** Exact-match scope, issuer, audience, token type, thời gian, ownership và tenant.
6. **Token cũ còn tồn tại bao lâu?** JWT/opaque, introspection cache, refresh grant và revoke ra sao?
7. **Migration chứng minh được gì?** Client usage, 401/403/invalid_scope, lịch sunset, rollback và test âm tính.

**Scope là một hợp đồng quyền cần được giữ ổn định hoặc thay đổi có kiểm soát.** Version scope khi **ý nghĩa quyền** thay đổi; đừng tự đồng nhất nó với phiên bản endpoint, đừng cấp scope mới qua grant cũ và đừng để scope thay thế quyết định authorization trên resource cụ thể. AS, client và RS cần thống nhất từ **phát hành, kiểm tra, sử dụng đến thu hồi**.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 3.3](https://www.rfc-editor.org/rfc/rfc6749#section-3.3): ngữ nghĩa scope, yêu cầu và quyền được cấp.
- [RFC 6749 — Refreshing an Access Token, Section 6](https://www.rfc-editor.org/rfc/rfc6749#section-6): giới hạn scope khi dùng refresh token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách trình access token, invalid_token và insufficient_scope.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claim scope và kiểm tra JWT access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái, scope của opaque token.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu token cho resource server cụ thể.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): quyền và audience của downstream token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo vệ token và ranh giới cấp quyền.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scopes OIDC và phân biệt ID token với access token.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và authorization theo đối tượng.
