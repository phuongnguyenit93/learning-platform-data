# Key identifier của client

Trong mô hình xác thực HTTP request bằng HMAC, **client và server cùng nắm một shared secret** để tạo và xác minh chữ ký. Khi server phục vụ nhiều client, mỗi client có thể sở hữu nhiều khóa, hoặc một khóa đang được thay thế bởi khóa mới. Server cần biết **dùng khóa nào để kiểm tra chữ ký của request hiện tại**. Trường **key identifier** (thường gọi là `keyId` hoặc `kid`) giải quyết bài toán chọn khóa này.

Với mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, việc cấp phát và sử dụng `keyId` là một phần của thiết kế xác thực request dựa trên **canonical request** (phương thức HTTP, URI, các header hoặc body theo hợp đồng ký), đồng thời gắn với kiểm tra timestamp/nonce chống replay, key rotation, hành vi proxy/gateway và phân quyền. Bài học thuộc chương **Mô hình client server**, tập trung vào việc client trình bày định danh khóa và server sử dụng định danh đó một cách an toàn.

> **Luận điểm chính:** `keyId` chỉ là **định danh giúp tìm khóa**; nó **không phải shared secret**, **không phải chữ ký**, và tự nó **không chứng minh client đã được xác thực**.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt `clientId`, `keyId`, shared secret, HMAC signature và principal được xác thực.
2. Mô tả cách client gửi `keyId`, cách server tra cứu key record và cách kiểm tra chữ ký bằng **đúng khóa tương ứng**.
3. Thiết kế format `keyId`, metadata khóa, vòng đời cấp phát, kích hoạt, rotation và thu hồi.
4. Giải thích vì sao `keyId` là dữ liệu đầu vào chưa tin cậy, cần ràng buộc vào hợp đồng ký và kiểm soát giới hạn tra cứu.
5. Tránh nhầm lẫn giữa xác thực khóa và phân quyền thao tác hoặc tài nguyên.
6. Kiểm thử các tình huống key ID không tồn tại, bị đổi, bị trùng header, hết hạn, sai audience, cache cũ và request qua gateway.

## 2. Vai trò của key identifier trong mô hình client–server

Hãy tưởng tượng một API xử lý đơn hàng nhận request từ ba đối tác A, B và C. Mỗi đối tác dùng khóa HMAC khác nhau:

| Client được cấp quyền | Key identifier | Secret server lưu | Dùng để làm gì? |
| --- | --- | --- | --- |
| Partner A | `kid_A_2026_01` | `secret-A-1` | Xác minh request do credential A-1 tạo |
| Partner B | `kid_B_2026_01` | `secret-B-1` | Xác minh request do credential B-1 tạo |
| Partner C | `kid_C_2026_01` | `secret-C-1` | Xác minh request do credential C-1 tạo |

Các giá trị `secret-A-1`, `secret-B-1` và `secret-C-1` chỉ là **tên minh họa**, không phải secret đủ mạnh để dùng thực tế. Trong triển khai thật, secret phải được sinh ngẫu nhiên đủ mạnh và bảo vệ ở cả client lẫn server.

Nếu request mang `X-Key-Id: kid_B_2026_01`, server có thể dùng giá trị này để **chọn bản ghi khóa B-1**, sau đó tính HMAC với secret B-1 và kiểm tra chữ ký.

Việc tìm thấy một key record **chưa tạo ra danh tính đã xác thực**. Người lạ có thể tự gửi cùng `X-Key-Id` nhưng không biết secret; chữ ký của họ không hợp lệ. Chỉ sau khi kiểm tra chữ ký, tính mới của request và điều kiện hiệu lực khác thành công, server mới có cơ sở tạo authenticated principal tương ứng.

### 2.1. Những khái niệm dễ bị nhầm

| Khái niệm | Định nghĩa | Có bí mật không? | Vai trò |
| --- | --- | --- | --- |
| `clientId` / consumer ID | Định danh logic của hệ thống hoặc ứng dụng được cấp quyền | Thường không | Gom nhiều credential về cùng một consumer |
| `keyId` / `kid` | Định danh của **một phiên bản credential/khóa cụ thể** | Thường không | Chọn khóa tương ứng ở verifier |
| Shared secret | Dữ liệu bí mật được client và server cùng biết | **Có** | Là khóa đầu vào của HMAC |
| HMAC signature | MAC tính từ secret và canonical request | Không phải secret dài hạn | Chứng minh request khớp với secret nếu được xác minh |
| Authenticated principal | Danh tính tin cậy do server tạo sau khi xác thực đầy đủ | Không phải dữ liệu client tự quyết | Đầu vào cho kiểm tra quyền |
| Scope / permission | Quyền được cấu hình cho principal hoặc credential | Chính sách server | Quyết định thao tác/tài nguyên nào được phép |

**Quan hệ nhiều–một:** một `clientId` có thể sở hữu **nhiều `keyId`** cùng lúc, chẳng hạn khi key rotation. Mỗi `keyId` thường trỏ tới **một secret bất biến trong một vòng đời khóa**. Không nên tái sử dụng cùng `keyId` cho một secret mới.

### 2.2. Sơ đồ thành phần

~~~mermaid
flowchart LR
    C[Client A] -->|X-Key-Id và chữ ký| API[HMAC verifier]
    API -->|Tra cứu keyId| KR[(Kho metadata khóa)]
    KR -->|secret reference + owner + status| API
    API -->|Lấy secret tương ứng| SM[(Secret manager)]
    API -->|Kiểm tra canonical HMAC| P[Authenticated principal]
    P --> AUTH[Authorization]
    AUTH --> HANDLER[Business handler]
~~~

Trong sơ đồ, `KR` lưu hoặc trỏ tới metadata khóa; `SM` bảo vệ secret. Hai thành phần có thể được tích hợp, nhưng vẫn cần phân biệt logic: **key ID là khóa tra cứu công khai, còn secret là thông tin mật để tính HMAC**.

## 3. Ai tạo và quản lý key identifier?

Thông thường, **hệ thống cấp credential** (API provider, IAM/credential service hoặc quy trình onboarding được kiểm soát) sinh `keyId` và secret, sau đó cung cấp cho consumer qua kênh an toàn. Consumer cấu hình chúng trong ứng dụng của mình.

Một quy trình cấp phát có thể là:

1. Đăng ký một **consumer/principal** được phép gọi API, ví dụ `partner-orders-A`.
2. Chọn audience/service, môi trường và phạm vi quyền cần cấp, ví dụ chỉ được tạo đơn hàng trong tenant A.
3. Sinh một **secret ngẫu nhiên bằng CSPRNG** (ví dụ 256 bit) và một `keyId` duy nhất trong namespace tra cứu.
4. Ghi key record cùng `principalId`, trạng thái, thời hạn, thuật toán được hỗ trợ và tham chiếu secret.
5. Chuyển `keyId` và secret cho consumer qua kênh cấp phát bảo mật; chỉ hiển thị secret theo chính sách phù hợp.
6. Client lưu secret ở nơi an toàn, cấu hình `keyId`, ký request và gửi `keyId` trên mỗi request.
7. Server theo dõi trạng thái credential, audit việc sử dụng, rotation và thu hồi khi cần.

### 3.1. Key ID nên có hình thức như thế nào?

Một lựa chọn thực tế là định danh **opaque** (không mang thông tin nghiệp vụ trong chuỗi), ví dụ:

~~~text
kid_y7QgB0Xvsd4pK2mn
~~~

Nên thống nhất:

- Bộ ký tự cho phép, chẳng hạn ASCII `[A-Za-z0-9_-]`; giới hạn độ dài; không chấp nhận CR/LF, ký tự điều khiển, Unicode tương đương hoặc khoảng trắng không có quy tắc rõ.
- Phân biệt chữ hoa/chữ thường: thông thường **giữ nguyên case** của giá trị vì key ID là định danh chính xác.
- Phạm vi duy nhất: duy nhất toàn cục hoặc duy nhất theo một namespace đã được chọn bằng ranh giới tin cậy như service/environment. Nếu nhiều service dùng chung kho, cân nhắc duy nhất toàn cục để giảm nhầm lẫn.
- Quy trình sinh: ưu tiên bộ sinh có tính duy nhất cao; một UUID ngẫu nhiên hoặc chuỗi random phù hợp là các lựa chọn triển khai phổ biến.
- Không chứa secret, mật khẩu, thông tin định danh nhạy cảm hoặc quyền mà server sẽ tự suy ra từ chuỗi.
- Không đặt logic cấp quyền dựa trên việc client gửi prefix như `admin_` hay `tenant-A_`. Quyền phải đến từ **bản ghi phía server**.

**`keyId` không bắt buộc phải bí mật**. Dù vậy, vẫn nên tránh để nó lộ không cần thiết trong URL, analytics công khai hoặc log có thể chia sẻ rộng; key ID có thể giúp liên hệ request với một đối tác và làm mục tiêu thăm dò credential. Sức mạnh bảo mật phải dựa vào **secret**, không dựa vào sự khó đoán của `keyId`.

### 3.2. Vì sao không lấy client ID làm key ID?

Nếu dùng `clientId` làm định danh khóa duy nhất, khi đổi secret vẫn giữ cùng ID, verifier có thể phải thử nhiều secret cho một client, hoặc cache cũ không biết đang dùng phiên bản nào. Điều này gây phức tạp cho rotation và giảm khả năng audit.

Tách riêng:

~~~text
clientId = partner-orders-A

keyId = kid_A_v1  ---> secret version 1
keyId = kid_A_v2  ---> secret version 2

Both key records map to clientId = partner-orders-A.
~~~

Nhờ đó, server xác minh request theo **một key record cụ thể**, biết credential nào đang được dùng và thu hồi từng credential mà không phải đổi định danh logic của consumer.

## 4. Key ID đi vào HTTP request như thế nào?

Một hợp đồng HMAC có thể quy định gửi ID trong header `X-Key-Id`. Có thể dùng header `Authorization` theo một scheme riêng nếu API định nghĩa đầy đủ; không có một cách đặt header phổ quát cho mọi giao thức HMAC.

Ví dụ request tạo đơn hàng (giá trị thời gian, nonce và chữ ký chỉ minh họa):

~~~http
POST /v1/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: kid_y7QgB0Xvsd4pK2mn
X-Timestamp: 1790000000
X-Nonce: 4a0b876ee2ba539dbec96ab30f6380a7
X-Signature: <base64url-hmac-sha256>

{"orderId":"order-1042","amount":100000}
~~~

Trong ví dụ:

- `X-Key-Id` cho server biết **nên tìm credential nào**.
- `X-Timestamp` và `X-Nonce` cung cấp dữ liệu cho lớp chống replay nếu server kiểm tra chúng đúng cách.
- `X-Signature` là kết quả HMAC từ secret và canonical request được hai phía quy định.
- `POST`, request-target, `Content-Type` và body có thể được bảo vệ nếu hợp đồng ký đưa chúng vào canonical request.

Server **không nên nhận secret từ request**. Nếu client gửi cả secret trong header rồi server lấy secret đó để kiểm tra HMAC, cơ chế không còn xác thực theo credential do server tin cậy quản lý.

### 4.1. Ràng buộc key ID vào canonical request

Một hợp đồng minh họa có thể yêu cầu chuỗi byte ký như sau:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders?currency=VND
audience:orders-api
x-key-id:kid_y7QgB0Xvsd4pK2mn
x-timestamp:1790000000
x-nonce:4a0b876ee2ba539dbec96ab30f6380a7
content-type:application/json
body-sha256:<sha256-hex-of-exact-body-bytes>
~~~

Đây là **định dạng mô tả**, chưa phải chữ ký tính được: phần `<sha256-hex-of-exact-body-bytes>` phải được thay bằng digest thật. Hợp đồng phải chốt UTF-8, ký tự xuống dòng LF, có hay không dấu xuống dòng cuối, thứ tự các dòng, quy tắc path/query, chuẩn hóa header và raw body bytes.

**Tại sao ký cả `keyId`?** Vì key ID là một phần danh tính credential và bối cảnh xác minh. Đưa nó vào canonical bytes làm cho thông điệp được ký ràng buộc tường minh với ID đã công bố, giúp tránh nhập nhằng khi có các cách diễn giải header hoặc key namespace khác nhau. Ngay cả khi hệ thống đã chọn secret theo ID thì việc tráo ID thường khiến chữ ký không khớp; ký ID vẫn là một quy tắc protocol nên giữ rõ ràng.

Nên ràng buộc cả **audience** hoặc service ID ổn định trong canonical request và key record; nếu không, cùng khóa dùng ở nhiều đích có thể làm tăng rủi ro phát lại request giữa các service.

### 4.2. Header key ID bị lặp hoặc bị biến đổi

Request có thể chứa:

~~~http
X-Key-Id: kid_y7QgB0Xvsd4pK2mn
X-Key-Id: kid_other
~~~

Một gateway có thể gộp hai header, backend lấy header đầu còn verifier lấy header cuối. Nếu hai bên bất đồng, có thể phát sinh sai khác giữa dữ liệu **được xác thực** và dữ liệu **được xử lý**.

Cách an toàn: hợp đồng chỉ cho **một giá trị key ID**, từ chối header lặp và input mơ hồ; áp dụng cùng chính sách ở gateway và backend. Tên header HTTP có thể khác chữ hoa/chữ thường nhưng **giá trị key ID không được tự lowercase**. Không nên âm thầm trim hoặc biến đổi giá trị ngoài quy tắc hợp đồng.

## 5. Trình tự server xử lý key identifier

Cần phân biệt bốn thời điểm: **nhận ID**, **tìm credential**, **xác minh chữ ký và tính mới**, rồi **tạo principal/kiểm tra quyền**.

~~~mermaid
sequenceDiagram
    participant C as HMAC Client
    participant V as Server / Verifier
    participant K as Key Registry
    participant N as Shared Nonce Store
    participant A as Authorization

    C->>V: HTTP request + keyId + timestamp + nonce + signature
    V->>V: Kiểm tra định dạng, header trùng, giới hạn tài nguyên
    V->>K: findByKeyId(keyId)
    K-->>V: key record (secret ref, principal, trạng thái, audience)
    V->>V: Kiểm tra key hiệu lực và timestamp
    V->>V: Canonicalize + tính HMAC bằng secret của keyId
    V->>V: So sánh chữ ký an toàn
    V->>N: Đặt nonce nếu chưa tồn tại (atomic)
    N-->>V: Thành công hoặc đã từng xuất hiện
    V->>A: Principal đã xác thực + action/resource
    A-->>V: Cho phép / từ chối
    V-->>C: Kết quả HTTP
~~~

Luồng chi tiết:

1. **Đọc một `keyId` duy nhất.** Kiểm tra hiện diện, độ dài, cú pháp và header trùng trước khi tra cứu. Key ID từ Internet vẫn là dữ liệu chưa tin cậy.
2. **Tra cứu exact match** trong registry theo namespace được server quy định; không tìm khóa bằng cách dò từng secret hoặc suy secret từ ID.
3. **Kiểm tra metadata:** khóa còn hiệu lực, không bị thu hồi, thuộc đúng audience và môi trường, thuật toán hợp lệ, thuộc consumer/tenant được cấu hình; secret được lấy từ nguồn tin cậy.
4. **Kiểm tra timestamp và canonical request:** xác định giới hạn thời gian, tạo đúng chuỗi byte ký từ method, URI, header/body và key ID theo protocol version.
5. **Tính và so sánh HMAC:** ví dụ HMAC-SHA256; decode signature đúng dạng, so sánh byte bằng API thích hợp. Sai chữ ký thì từ chối.
6. **Chống replay bằng nonce:** sau khi chứng thực MAC, thực hiện thao tác lưu nonce duy nhất **nguyên tử** trong kho dùng chung; từ chối request đã sử dụng nonce. Namespace nonce nên gắn với credential/principal và đích xác thực.
7. **Tạo authenticated principal:** lấy danh tính và thuộc tính tin cậy từ key record/server policy, không sao chép nguyên `X-Client-Id` do người gọi tự khai.
8. **Kiểm tra authorization:** xét action, resource, tenant, scope và chính sách nghiệp vụ. Không thực thi request chỉ vì signature hợp lệ.

**Bất biến an toàn:** Tìm thấy `keyId` không đồng nghĩa xác thực thành công. Trong mọi nhánh xử lý thất bại, server không được tạo principal đáng tin hoặc cho handler thực thi một phần nghiệp vụ được bảo vệ.

### 5.1. Lỗi trả về khi không tìm được khóa

Các trường hợp `keyId` không tồn tại, khóa bị khóa/thu hồi hoặc chữ ký sai thường nên trả **lỗi xác thực tổng quát**, chẳng hạn HTTP 401 theo hợp đồng API, tránh nói “key ID này có tồn tại nhưng secret sai”. Điều này giảm khả năng dò xem ID nào đang hoạt động.

Lỗi 403 thường dành cho trường hợp **đã xác thực** nhưng principal không có quyền thực hiện hành động cụ thể. Cần giới hạn tốc độ và quan sát lưu lượng bất thường; thông báo lỗi đồng nhất không tự ngăn được key enumeration qua timing hoặc hành vi hệ thống.

### 5.2. Tìm khóa bằng ID khác với cấp quyền cho ID

Giả sử request gửi `X-Key-Id: kid_partner_A_v2` và HMAC hợp lệ, nhưng body chứa:

~~~json
{
  "tenantId": "tenant-B",
  "orderId": "order-B-999",
  "amount": 50000
}
~~~

Nếu key record ánh xạ đến `tenant-A`, server **phải đối chiếu** việc cập nhật order B với quyền thuộc tenant A. Chữ ký chỉ chứng minh request được tạo bằng secret của credential A; không chứng minh principal A được phép thao tác trên tài nguyên của B.

## 6. Key registry: metadata cần lưu

Một key record thực tế có thể có cấu trúc logic:

~~~yaml
keyId: kid_y7QgB0Xvsd4pK2mn
clientId: partner-orders-A
principalId: service-account-partner-A
tenantId: tenant-A
audience: orders-api
environment: production
algorithm: HMAC-SHA256
secretRef: secrets/orders-api/partner-A/key-2026-01
status: ACTIVE
notBefore: "2026-11-01T00:00:00Z"
acceptUntil: "2027-02-01T00:00:00Z"
allowedActions:
  - orders:create
  - orders:read
~~~

Đây là **mẫu thiết kế**, không phải cấu hình production đầy đủ hoặc secret thật. `secretRef` là đường dẫn/tham chiếu tới kho bảo mật, không phải secret và không được client gửi. Server nên kiểm tra tính hợp lệ của metadata và bảo vệ quyền đọc/ghi registry.

| Field | Tác dụng |
| --- | --- |
| `keyId` | Khóa tra cứu chính xác |
| `clientId` / `principalId` | Gắn credential với consumer/workload được quản lý |
| `tenantId` | Ràng buộc tenant/phạm vi dữ liệu tại phía server |
| `audience`, `environment` | Không dùng khóa nhầm API/đích hoặc môi trường |
| `algorithm` | Thuật toán do server kiểm soát; không để client tự chọn `alg=none` |
| `secretRef` | Nguồn lấy secret có kiểm soát; không lộ secret qua log hay response |
| `status`, `notBefore`, `acceptUntil` | Quản lý hiệu lực, thời gian chuyển tiếp và thu hồi |
| `allowedActions` | Dữ liệu đầu vào cho phân quyền; có thể được quản lý trong hệ thống ACL/RBAC riêng |
| Audit metadata | Thời điểm cấp, người/ứng dụng cấp, lần dùng gần nhất; hỗ trợ điều tra và rotation |

Trạng thái thường dùng: `ACTIVE`, `RETIRING` (vẫn chấp nhận xác minh trong giai đoạn chuyển tiếp có thời hạn), `REVOKED` và `EXPIRED`. Tên trạng thái có thể khác theo hệ thống, nhưng ngữ nghĩa phải nhất quán và không được coi khóa revoked là hợp lệ chỉ vì HMAC khớp.

### 6.1. Chỉ một nơi quyết định principal

Client có thể gửi cả `X-Client-Id: partner-orders-A` để quan sát hoặc routing, nhưng giá trị đó không nên được coi là principal chỉ vì nó xuất hiện trong header.

Một trình tự đúng là:

~~~text
request.keyId
  -> keyRegistry.lookup(keyId)
  -> keyRecord.secretRef / keyRecord.status / keyRecord.audience
  -> verify HMAC and freshness
  -> principal = keyRecord.principalId
  -> authorize(principal, request.action, request.resource)
~~~

Giá trị `keyRecord.principalId` đến từ hệ thống quản lý khóa đã được bảo vệ. Đây là điểm nối **authentication** và **authorization**.

### 6.2. Caching key record có lợi và có rủi ro

Tra cứu registry/secret manager trên mọi request có thể tốn độ trễ. Cache giúp giảm tải nhưng cần:

- Key cache theo **đúng `keyId` và namespace**; tránh trộn production với staging hoặc audience khác.
- TTL ngắn hoặc cơ chế push invalidation đối với trạng thái/khóa bị thu hồi.
- Không cache quyết định “khóa hợp lệ vĩnh viễn”; cần đánh giá hiệu lực tại thời điểm xử lý.
- Không ghi secret vào debug dump; quản lý vòng đời và quyền truy cập cache.
- Không phục hồi sai khóa khi cache miss: chính sách lỗi phải rõ ràng, nhất là khi registry tạm mất kết nối.

**Ví dụ:** Khóa bị thu hồi ở registry lúc 10:00 nhưng verifier còn giữ record `ACTIVE` trong cache đến 10:30; request đã ký bằng khóa bị thu hồi có thể vẫn được chấp nhận trong khoảng đó. Sự cố này thuộc **tính nhất quán của trạng thái khóa**, không thuộc độ mạnh HMAC.

## 7. Java: sử dụng key ID trong bước kiểm tra chữ ký

Đoạn code dưới đây minh họa cách verifier nhận `keyId`, tra cứu đúng secret, kiểm tra tình trạng credential và HMAC bằng JCA. Dùng Java 17+ để có `record`. Trong sản phẩm thật, `KeyRegistry` cần kết nối kho khóa tin cậy và áp dụng bảo vệ cache/secret phù hợp.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.Optional;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class HmacKeyIdVerifier {
    private static final Pattern KEY_ID_FORMAT =
            Pattern.compile("[A-Za-z0-9_-]{8,80}");

    private HmacKeyIdVerifier() {}

    // secretKey phải lấy từ secret manager/kho khóa do server quản lý.
    public record KeyRecord(
            String keyId,
            String principalId,
            String audience,
            SecretKey secretKey,
            Instant notBefore,
            Instant acceptUntil,
            boolean revoked) {}

    public interface KeyRegistry {
        Optional<KeyRecord> findExact(String keyId);
    }

    // Mới xác nhận chữ ký và credential, CHƯA xử lý nonce hay authorization.
    public record SignatureMatch(String principalId, String keyId) {}

    public static Optional<SignatureMatch> verifySignature(
            String presentedKeyId,
            String presentedSignature,
            byte[] canonicalRequest,
            String expectedAudience,
            Instant now,
            KeyRegistry registry) throws GeneralSecurityException {

        if (presentedKeyId == null
                || !KEY_ID_FORMAT.matcher(presentedKeyId).matches()
                || presentedSignature == null
                || canonicalRequest == null) {
            return Optional.empty();
        }

        // Exact lookup, không thử lần lượt toàn bộ secret trong hệ thống.
        Optional<KeyRecord> lookup = registry.findExact(presentedKeyId);
        if (lookup.isEmpty()) {
            return Optional.empty();
        }

        KeyRecord key = lookup.get();
        if (key.revoked()
                || !key.keyId().equals(presentedKeyId)
                || !key.audience().equals(expectedAudience)
                || now.isBefore(key.notBefore())
                || !now.isBefore(key.acceptUntil())) {
            return Optional.empty();
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(presentedSignature);
        } catch (IllegalArgumentException invalidEncoding) {
            return Optional.empty();
        }

        // HMAC-SHA256 luôn có 32 byte. Chốt dạng Base64URL không padding.
        if (supplied.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied).equals(presentedSignature)) {
            return Optional.empty();
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key.secretKey());
        byte[] expected = mac.doFinal(canonicalRequest);

        if (!MessageDigest.isEqual(expected, supplied)) {
            return Optional.empty();
        }

        return Optional.of(new SignatureMatch(
                key.principalId(), key.keyId()));
    }

    // Ví dụ phía client, khi canonicalRequest đã được tạo đúng contract:
    public static String sign(byte[] canonicalRequest, SecretKey clientSecret)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(clientSecret);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal(canonicalRequest));
    }
}
~~~

**Giới hạn cố ý của đoạn code:**

1. `canonicalRequest` phải chứa `keyId`, method, URI, những header/body cần thiết, timestamp/nonce và audience theo **hợp đồng ký đã chốt**. Đoạn code không tự xây canonical request.
2. `verifySignature` chưa kiểm tra timestamp trong cửa sổ, chưa ghi nonce vào kho chống replay và chưa kiểm tra scope/resource. Kết quả `SignatureMatch` là một **kết quả kiểm tra MAC**, chưa phải quyết định chấp nhận request nghiệp vụ.
3. Caller phải từ chối request có nhiều header cùng tên/giá trị mơ hồ; phải hoàn thành kiểm tra freshness, nonce nguyên tử, authorization trước khi gọi business handler.
4. Lỗi “không tìm thấy key ID”, “secret không khớp”, “khóa đã thu hồi” cần được ánh xạ thành lỗi xác thực bên ngoài phù hợp và không tiết lộ chi tiết.
5. Dùng secret được sinh an toàn và `SecretKey` đúng thuật toán; mã minh họa không giải quyết bài toán cấp phát, lưu trữ hay rotate secret.

> Chú ý: `String.getBytes(StandardCharsets.UTF_8)` phù hợp khi contract ký **canonical text UTF-8**; với body, cần tính digest từ **đúng raw bytes đã được hợp đồng ký định nghĩa**, không từ JSON serialize lại.

### 7.1. Luồng gọi hai bước sau khi kiểm tra MAC

Pseudocode tích hợp làm rõ nơi tạo principal:

~~~text
keyId = parseExactlyOneHeader("X-Key-Id")
timestamp, nonce, signature = parseSignedHeaders()

assertValidTimestamp(timestamp, allowedWindow)
canonicalBytes = canonicalize(request, keyId, timestamp, nonce)

match = verifySignature(keyId, signature, canonicalBytes, audience)
if match == NONE:
    return 401 generic_authentication_failed

# Chỉ request đã được MAC xác minh mới chiếm không gian nonce.
if !nonceStore.putIfAbsent(audience, match.keyId, nonce, ttl):
    return reject_replay

principal = loadTrustedPrincipal(match.principalId)
if !authorizer.can(principal, action, resource, tenant):
    return 403 forbidden

return businessHandler.executeWithIdempotency(request, principal)
~~~

Timestamp phải được kiểm tra theo đơn vị và cửa sổ đã công bố. Nonce phải được lưu **atomically trên kho chia sẻ giữa các instance**. TTL cần che phủ toàn bộ khoảng thời gian timestamp còn có thể hợp lệ; nếu dùng cửa sổ `±5 phút`, không mặc định rằng TTL 5 phút từ lần nhận đầu luôn đủ. Với request có tác động tài chính, idempotency cần được xử lý riêng.

## 8. Key rotation: một client có nhiều key ID

Key rotation là trường hợp điển hình nhất thể hiện vì sao `clientId` và `keyId` cần tách nhau. Trong một khoảng chuyển tiếp, **hai credential khác nhau** có thể đều ánh xạ tới một principal.

~~~mermaid
flowchart TB
    P[Principal: partner-orders-A]
    P --> OLD[Key ID cũ: kid_A_v1]
    P --> NEW[Key ID mới: kid_A_v2]
    OLD --> OS[Secret v1, RETIRING]
    NEW --> NS[Secret v2, ACTIVE]
~~~

### 8.1. Quy trình chuyển khóa không gián đoạn

1. **Cấp credential mới:** tạo secret mới và `keyId = kid_A_v2`; giữ `kid_A_v1` ở trạng thái còn chấp nhận xác minh trong khoảng overlap có giới hạn.
2. **Cấu hình registry:** cả hai ID trỏ tới cùng principal/audience phù hợp nhưng khác secret; server xác minh theo ID nhận được.
3. **Phân phối secret mới an toàn:** cập nhật client để dùng `kid_A_v2` cùng secret v2. Request cũ đang trên đường truyền vẫn có thể dùng v1.
4. **Quan sát chuyển đổi:** đo lưu lượng theo ID (trong hệ thống nội bộ), đảm bảo các instance/region nhất quán và không còn client cần v1.
5. **Thu hồi ID cũ:** đặt `kid_A_v1` thành `REVOKED` hoặc hết `acceptUntil`; vô hiệu hóa cache và ngăn mọi instance chấp nhận nó.
6. **Dọn trạng thái đúng quy trình:** ngừng phân phối/cho phép dùng secret v1, lưu audit theo retention policy, theo dõi lỗi sau chuyển đổi.

Không nên thực hiện rotation bằng cách **ghi secret mới đè lên cùng một `keyId`**. Làm vậy khiến client không biết đang dùng phiên bản nào, cache verifier có thể lệch, việc truy vết và rollback khó kiểm soát.

**Ngoại lệ sự cố:** Nếu nghi secret đã bị lộ, không duy trì overlap thông thường để giữ tương thích. Cần ưu tiên thu hồi khóa bị nghi xâm phạm, chấp nhận gián đoạn có kiểm soát khi cần và điều tra những request đã được ký bằng credential đó.

### 8.2. Những trường hợp rotation cần chú ý

- **Nhiều instance verifier:** mỗi instance phải cập nhật status và secret ref đồng bộ; nếu vùng A nhận v2 còn vùng B chưa nhận, request sẽ lỗi thất thường.
- **Nhiều client instance:** một số client vẫn ký bằng v1 sau khi phiên bản khác đã chuyển v2; nên theo dõi ID sử dụng để quyết định khi nào đóng overlap.
- **Nonce namespace:** nếu namespace theo `keyId` thì v1 và v2 có hai tập nonce độc lập. Điều này phù hợp vì chữ ký dùng khóa khác, nhưng **idempotency nghiệp vụ** phải được ràng buộc theo operation/principal để không xử lý trùng khi retry qua các key version.
- **Phân quyền theo principal:** quyền của partner không tự mở rộng khi cấp v2; việc tăng/giảm quyền là quyết định chính sách riêng.
- **Thu hồi tức thì:** cần dự liệu độ trễ invalidation cache và phương án fail closed ở những API nhạy cảm.

## 9. Key ID qua reverse proxy và API gateway

Trong hệ thống nhiều tầng, client có thể gửi `X-Key-Id` đến load balancer, WAF, API gateway rồi mới tới service xác minh HMAC.

~~~mermaid
flowchart LR
    CL[Client] --> GW[API Gateway]
    GW --> SV[HMAC Verifier]
    SV --> APP[Application]
~~~

Rủi ro đặc thù với `keyId`:

| Tình huống | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gateway xóa header `X-Key-Id` | Backend không tìm được khóa | Đảm bảo forward chính xác header đã được định nghĩa |
| Gateway gộp header trùng | Gateway/backend có thể diễn giải key ID khác nhau | Từ chối header trùng hoặc mơ hồ ngay tại biên |
| Gateway sửa tên hoặc giá trị ID | Canonical request sai, chữ ký không khớp | Xác minh cùng biểu diễn, không tự đổi case giá trị ID |
| Gateway kiểm tra HMAC rồi truyền `X-Principal` | Backend có thể bị giả mạo principal nếu client tự gửi header đó | Gateway xóa header principal do client cung cấp; truyền danh tính qua kênh tin cậy |
| Mỗi service dùng kho khóa riêng nhưng trùng ID | Lookup có thể nhầm audience/namespace | Ràng buộc service ID/audience và namespace của key record |
| Retry sau gateway | Nonce trùng hoặc nghiệp vụ xử lý trùng | Thiết kế retry tạo request mới và idempotency riêng |
| Gateway cache metadata khóa cũ | Khóa đã thu hồi vẫn được chấp nhận | Invalidation/TTL và policy thu hồi thống nhất |

Nếu **gateway** trực tiếp xác minh HMAC, backend cần được bảo vệ khỏi kết nối ngoài trực tiếp và không được tin header danh tính do người gọi tự khai. Nếu **backend** là verifier, contract canonicalization phải tính đến mọi phép rewrite method, path, query, header/body của gateway.

Kiểm thử phải đi qua **đường HTTP thực** với cấu hình proxy/gateway đang dùng. Unit test tra cứu ID trong một `Map` đơn giản không đủ để phát hiện header duplication hoặc khác biệt path decoding.

## 10. Những lỗi bảo mật thường gặp

### 10.1. Coi key ID là bằng chứng xác thực

**Sai:**

~~~java
String keyId = request.getHeader("X-Key-Id");
String principal = keyRegistry.findExact(keyId).get().principalId();
processRequestAs(principal); // Chưa xác minh HMAC!
~~~

Bất kỳ ai biết một ID đều có thể tự gửi ID đó. Đúng ra server phải kiểm tra toàn bộ điều kiện xác thực rồi mới tạo principal.

### 10.2. Cho client chỉ định thuật toán hoặc nguồn secret

Không dùng các input như `X-Alg: none`, `secretUrl`, `secretPath` hoặc `X-Client-Scope: admin` làm chính sách trực tiếp. Key record server-side quyết định thuật toán, secret, audience và quyền. Nhập `keyId` phải không dẫn tới xây đường dẫn file tùy ý hoặc truy vấn không tham số hóa.

### 10.3. Dùng chung một secret cho toàn bộ client

Nếu A và B dùng chung secret, chữ ký đúng không chứng minh client nào thực sự gửi request; một client bị xâm phạm có thể giả mạo client còn lại nếu thiết kế principal không phân biệt. Tốt hơn là cấp **credential riêng** theo consumer, môi trường và audience.

### 10.4. Tra khóa theo thứ tự cho đến khi HMAC khớp

Với hàng nghìn khóa, cách “thử hết secret đến khi khớp” làm tăng tải, không minh bạch về principal và khó kiểm soát trạng thái bị thu hồi. `keyId` cho phép **tra cứu một credential cụ thể**. Với key không tồn tại, server trả lỗi xác thực chung và áp dụng rate limiting; tránh để quá trình dò ID thành kênh tiêu tốn tài nguyên.

### 10.5. Cho client tự chọn key ID hoặc tenant để nâng quyền

Một API tạo credential mà không kiểm tra quyền có thể cho consumer A cấp ID hoặc principal mapping dưới tên B. Hệ thống cấp phát credential phải kiểm tra quyền chủ sở hữu trước khi tạo record; verifier không được quyết định tenant từ prefix tự khai.

### 10.6. Để danh tính sau gateway bị giả mạo

Nếu gateway truyền `X-Authenticated-Client` nhưng không xóa giá trị client gửi từ Internet, backend có thể nhận header giả. Header danh tính nội bộ chỉ đáng tin khi do thành phần xác thực **được tin cậy** thiết lập và ranh giới kết nối được bảo vệ.

## 11. Bộ kiểm thử key identifier

Một hệ thống tốt cần kiểm thử đồng thời **key lookup, HMAC, state, replay, authorization và đường đi gateway**.

| Ca kiểm thử | Đầu vào / thao tác | Kết quả kỳ vọng |
| --- | --- | --- |
| Key hợp lệ | `keyId` tồn tại, secret đúng, ký canonical request đúng | Xác minh chữ ký thành công; tiếp tục freshness/nonce/quyền |
| Key ID không tồn tại | Dùng ID ngẫu nhiên không có trong registry | Lỗi xác thực tổng quát; không lộ dữ liệu key |
| ID đúng, signature sai | Client khai ID có thật nhưng không biết secret | Bị từ chối, không tạo principal |
| Đổi ID sau khi ký | Ký với v1 rồi đổi header sang v2 | Bị từ chối |
| Thiếu key ID | Không gửi header | Bị từ chối theo contract |
| Header ID trùng | Hai `X-Key-Id` khác nhau hoặc trùng nhau | Bị từ chối vì request mơ hồ |
| ID chứa CR/LF, quá dài | Input sai format hoặc quá giới hạn | Bị từ chối sớm, tránh log injection/tải lookup |
| Chênh chữ hoa/thường | Thay case của **giá trị** key ID | Không tự chuẩn hóa nhầm sang credential khác |
| Key đã thu hồi | HMAC hợp lệ bằng secret cũ | Bị từ chối theo trạng thái key |
| Key chưa tới hạn / hết hạn | Request trước `notBefore` hoặc sau `acceptUntil` | Bị từ chối |
| Sai audience | Key chỉ dùng cho orders API gọi billing API | Bị từ chối |
| Khóa v1 và v2 overlap | Hai ID khác nhau, đều đang hiệu lực | Mỗi ID xác minh bằng đúng secret của mình |
| Chuyển rotation xong | Dùng v1 sau khi revoked | Bị từ chối trên mọi node |
| Cache credential cũ | Thu hồi key trong khi verifier có cache | Không chấp nhận vượt quá chính sách thu hồi |
| Timestamp cũ/nonce lặp | Chữ ký đúng nhưng timestamp hết hạn hoặc nonce đã dùng | Bị từ chối replay/freshness |
| Đúng HMAC, sai tenant | Principal A thao tác resource tenant B | Lỗi phân quyền, không xử lý nghiệp vụ |
| Gateway lược bỏ/đổi header | Request đi qua proxy thực | Từ chối/đúng hành vi đã định nghĩa, không xác minh nhầm |
| Client tự gửi principal header | Chèn `X-Authenticated-Client: admin` | Không ảnh hưởng principal thực sự do verifier tạo |
| Key enumeration | Thử nhiều `keyId` tồn tại/không tồn tại | Response không tiết lộ trạng thái chi tiết; rate limit hoạt động |

Một bộ test tích hợp nên kiểm tra cả raw HTTP headers, case tên header, HTTP/2 khi dùng, canonical bytes đã ký, metadata registry và handler thực sự được gọi. Mục đích là khẳng định **chính credential đã được xác minh** mới được dùng cho quyết định quyền.

## 12. Tình huống thực hành: đối tác thanh toán đổi khóa

Hệ thống nhận callback thanh toán từ `merchant-A`. Ban đầu merchant dùng:

~~~text
clientId: merchant-A
keyId: kid_ma_v1
secret: <secret-v1>
principal: svc-merchant-A
tenant: merchant-A
audience: payment-webhook
~~~

Khi tới kỳ rotation, server phát hành thêm `kid_ma_v2` và secret v2, cả hai trỏ tới cùng `svc-merchant-A` trong thời gian ngắn.

**Tình huống 1:** Merchant chưa cập nhật client, tiếp tục gửi `kid_ma_v1` với HMAC đúng trong thời gian overlap. Server có thể chấp nhận nếu key v1 vẫn còn hiệu lực, timestamp và nonce hợp lệ, đồng thời callback đúng tenant/scope.

**Tình huống 2:** Một attacker biết `kid_ma_v2` nhưng không có secret v2. Họ tự gửi request với ID này. Tra cứu ID thành công nhưng chữ ký không hợp lệ: server phải từ chối.

**Tình huống 3:** Merchant ký đúng bằng v2 nhưng yêu cầu cập nhật giao dịch của `merchant-B`. Authentication thành công, authorization thất bại.

**Tình huống 4:** Sau khi v1 bị thu hồi, client còn cache v1 và gửi signed request hợp lệ về mặt HMAC. Server phải từ chối vì **khóa đã mất hiệu lực**; đổi key ID là một phần của quy trình cấp quyền và thu hồi, không chỉ là phép toán mật mã.

**Tình huống 5:** Gateway retry lại callback với cùng timestamp/nonce. Nếu bản đầu đã đi qua nonce gate, bản sau phải bị từ chối replay. Nếu merchant tạo callback mới với nonce mới, nghiệp vụ vẫn phải dùng event ID/idempotency để tránh tác động lặp.

### Câu hỏi thực hành

1. Vì sao `keyId` biết được không đồng nghĩa biết secret?  
   *Gợi ý:* ID phục vụ tra cứu bản ghi; tạo HMAC hợp lệ cần secret.
2. Vì sao hai key ID v1/v2 nên ánh xạ tới cùng principal khi rotation bình thường?  
   *Gợi ý:* Danh tính consumer không tự thay đổi cùng phiên bản credential.
3. Nếu đổi `X-Key-Id` làm chữ ký không khớp, có cần ký key ID trong canonical request nữa không?  
   *Gợi ý:* Nên có để ràng buộc tường minh credential identity và loại bỏ nhập nhằng protocol.
4. Server xác minh HMAC thành công có được bỏ qua kiểm tra tenant không?  
   *Gợi ý:* Không, authentication và authorization là hai quyết định khác nhau.
5. Một gateway đang gửi hai giá trị `X-Key-Id` tới backend. Nên làm gì?  
   *Gợi ý:* Từ chối request mơ hồ và thống nhất parsing tại biên.
6. Điều gì xảy ra nếu server thu hồi key nhưng cache verifier chưa được cập nhật?  
   *Gợi ý:* Hệ thống có thể tiếp tục nhận request đã ký bằng secret cũ; cần chính sách invalidation/TTL phù hợp.

## 13. Checklist khi thiết kế key identifier

- [ ] `keyId` định danh chính xác một credential, không phải secret hay quyền.
- [ ] Consumer được cấp ID và secret qua quy trình tin cậy; secret đủ ngẫu nhiên và bảo quản an toàn.
- [ ] Có tách `clientId`, `keyId`, `principalId` và ánh xạ quản lý bởi server.
- [ ] Key record có audience, environment, trạng thái, thời hạn và tham chiếu secret phù hợp.
- [ ] Input `keyId` được giới hạn định dạng/độ dài, chỉ cho một giá trị, tra cứu exact match.
- [ ] Hợp đồng canonical request phiên bản hóa và ký cả key ID cùng dữ liệu HTTP cần bảo vệ.
- [ ] Chỉ dùng secret phía server được chọn bởi key record, không dùng secret do client tự khai.
- [ ] Chưa tạo authenticated principal trước khi HMAC, timestamp, nonce và hiệu lực key được xác minh.
- [ ] Authorization theo principal/action/resource/tenant được áp dụng trước xử lý nghiệp vụ.
- [ ] Rotation tạo key ID mới, kiểm soát thời gian overlap và thu hồi ID cũ trên mọi node.
- [ ] Key cache được giới hạn và có cách vô hiệu hóa nhanh khi credential bị thu hồi.
- [ ] Proxy/gateway không biến đổi hoặc tin nhầm header ID/principal; có kiểm thử end-to-end.
- [ ] Log, metric và lỗi xác thực không lộ secret hoặc trạng thái tồn tại của key cho caller.

**Kết luận:** Trong mô hình HMAC client–server, `keyId` là điểm nối giữa **request do client gửi** và **credential do server quản lý**. Thiết kế tốt giúp verifier chọn đúng secret, hỗ trợ nhiều client/phiên bản khóa và truy vết chính xác. Tuy nhiên, key ID chỉ trở thành thông tin có ý nghĩa xác thực sau khi chữ ký, tính mới và trạng thái khóa được xác minh; quyền thực hiện hành động vẫn phải được server quyết định độc lập.
