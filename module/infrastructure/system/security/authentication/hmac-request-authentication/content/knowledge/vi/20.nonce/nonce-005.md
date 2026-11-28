# Nonce store: lưu và xác nhận nonce nguyên tử để chống replay cho HTTP request HMAC

**Nonce store** là thành phần ghi nhận nonce đã được dùng trong các HTTP request **xác thực HMAC thành công**. Khi cùng một client gửi lại nonce đã ghi nhận trong thời gian request còn có hiệu lực, hệ thống phải từ chối lần sau — kể cả khi **chữ ký HMAC hoàn toàn đúng**, timestamp vẫn còn mới và request không bị sửa byte nào. Đây là lớp bảo vệ chống **replay attack** mà riêng HMAC hoặc timestamp không cung cấp.

Bài **Nonce store** thuộc chương **Nonce**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module hướng dẫn xác thực HTTP request bằng **shared secret** và **canonical request** ràng buộc method, URI, header/body; xác minh HMAC, chống replay bằng timestamp/nonce, key rotation, kiểm thử proxy/gateway, và phân biệt **authentication** với **authorization**. Trọng tâm bài là **mô hình lưu nonce, atomic claim, TTL/expiration, phân tán nhiều replica và xử lý lỗi store**.

**Nguyên tắc đầu tiên:** nonce store không phải nơi “đọc rồi mới ghi” bằng hai lệnh tách rời. Thao tác chống replay phải là **claim-if-absent nguyên tử** và giá trị được claim phải có **thời hạn lưu đủ dài**. Nếu hai request đồng thời cùng nonce đều được xác nhận là mới, cơ chế chống replay đã thất bại.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích khác nhau giữa **HMAC hợp lệ**, **timestamp fresh**, **nonce chưa được dùng** và **idempotency nghiệp vụ**.
2. Thiết kế key lưu nonce theo **audience + authenticated client ID + nonce**, tránh lỗi khi key rotation hoặc phân tách tenant.
3. Triển khai **atomic claim** bằng Redis `SET ... NX PX ...`, unique constraint của SQL hoặc store có thao tác tương đương; nhận biết lỗi `GET` rồi `SET`.
4. Suy ra thời điểm nonce có thể hết hạn từ `signedTimestamp` và các cửa sổ `pastWindow`/`futureTolerance`, xử lý đúng ranh giới thời gian.
5. Hiểu vì sao multi-replica, vùng địa lý, cache eviction, failover, clock skew và outage ảnh hưởng trực tiếp đến replay protection.
6. Viết Java 17 mô phỏng nonce store có atomic compare-and-claim, HMAC verifier, concurrency test, replay across key rotation và freshness.
7. Kết hợp nonce với idempotency, key manager, gateway và authorization trong thiết kế production.

## 2. Vì sao phải có nonce store?

Một request hợp lệ được client ký:

~~~http
POST /v1/transfers?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: 1795831200
X-Nonce: 00112233445566778899aabbccddeeff
X-Content-SHA256: <64-hex-lowercase>
X-Signature: <base64-full-hmac-sha256>

{"transferId":"t-123","amount":50000}
~~~

Hai giá trị `<...>` là placeholder. HMAC của request được tính từ canonical request chứa **method, raw URI/query, client ID, key ID, timestamp, nonce, Content-Type và body digest**. Giả sử server nhận request này lúc `2026-11-28T02:00:00Z`, chữ ký đúng.

Một proxy không đáng tin có thể **sao chép nguyên request** và phát lại ngay sau đó:

~~~text
Lần 1: HMAC = PASS; timestamp = FRESH; nonce chưa thấy -> ACCEPT
Lần 2: HMAC = PASS; timestamp = FRESH; nonce đã claim -> REJECT
Lần 3: HMAC = PASS; timestamp = FRESH; nonce đã claim -> REJECT
~~~

Điểm quan trọng: request ở lần 2 **không bị thay đổi**, nên nó **vẫn phải vượt qua phép kiểm tra HMAC**. Store tồn tại để ghi nhận **lịch sử sử dụng nonce** trong giới hạn thời gian và phân quyền đã xác thực.

| Cơ chế | Điều chứng minh/giới hạn | Không tự giải quyết được |
| --- | --- | --- |
| HMAC trên canonical request | Client có quyền sử dụng shared secret; các trường **được ký** không bị sửa. | Cùng request được phát lại nguyên vẹn. |
| Signed timestamp + freshness | Request nằm trong cửa sổ thời gian hợp lệ. | Nhiều replay trong cửa sổ. |
| **Nonce store atomic** | Một nonce trong một namespace chỉ claim thành công một lần khi còn hiệu lực. | Client cố ý phát hành **request mới** với nonce mới nhưng cùng nghiệp vụ. |
| Business idempotency | Một ý định nghiệp vụ chỉ tạo side effect một lần theo idempotency key và trạng thái. | Xác thực secret và tính toàn vẹn HTTP request nếu thiếu HMAC. |
| Authorization | Client có quyền thao tác với action/resource/tenant. | Tính toàn vẹn request hoặc replay nếu không có cơ chế khác. |

**Không thể chỉ dựa vào timestamp:** cửa sổ timestamp 5 phút vẫn cho phép kẻ tấn công replay request nhiều lần trong 5 phút ấy. **Không thể chỉ dựa vào nonce:** nếu store xóa nonce cũ quá sớm mà không giới hạn timestamp, một request cũ có thể được chấp nhận trở lại.

## 3. Nonce: sinh thế nào và ràng buộc với request nào?

### 3.1. Sinh nonce từ CSPRNG

Ví dụ contract yêu cầu nonce dài **16 byte** (128 bit), biểu diễn thành **32 ký tự hex chữ thường**:

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

byte[] nonceBytes = new byte[16];
new SecureRandom().nextBytes(nonceBytes);
String nonce = HexFormat.of().formatHex(nonceBytes);
// Ví dụ: "00112233445566778899aabbccddeeff"
~~~

Hex ở ví dụ là **định dạng**, không thêm entropy. Một nonce 128 bit ngẫu nhiên và không lặp có nguy cơ collision rất nhỏ ở lưu lượng hợp lý; xác suất collision vẫn tăng theo **birthday bound**, xấp xỉ \(n(n-1)/2^{129}\) sau \(n\) nonce độc lập. Client phải sinh nonce mới cho **mỗi request mới**, kể cả retry đã được ký lại.

Không dùng `System.currentTimeMillis()` làm nonce duy nhất, không dùng bộ đếm cục bộ không phối hợp giữa replica, `Math.random()` hoặc giá trị như `"123"` cho hệ thống cần chống replay. Timestamp và nonce phục vụ **hai vai trò khác nhau**: thời gian và định danh lần sử dụng.

### 3.2. Nonce phải được HMAC ký

Canonical request mẫu sẽ có:

~~~text
x-timestamp:1795831200
x-nonce:00112233445566778899aabbccddeeff
~~~

Nếu `X-Nonce` **không nằm trong HMAC**, attacker có thể thay nonce của một request cũ bằng nonce mới để qua kiểm tra store, còn chữ ký của phần request khác vẫn đúng. Do đó server phải kiểm tra **đúng chuỗi nonce đã dùng khi dựng canonical** với chuỗi nonce đưa vào store.

Nonce cũng cần **kiểm tra format** trước khi dùng làm storage key: chỉ chấp nhận `[0-9a-f]{32}` trong contract; không trim, lower-case giá trị do client gửi một cách ngầm định, không nhận slash, colon, Unicode hoặc control character.

### 3.3. Key lưu nonce: tránh namespace sai

Một namespace minh họa:

~~~text
nonceKey = (audience, authenticatedClientId, nonce)
~~~

Ví dụ:

~~~text
audience = transfers-api
client   = partner-42
nonce    = 00112233445566778899aabbccddeeff
~~~

**Audience** phân tách các dịch vụ/trust domain; **client ID đã xác thực** phân tách các client; **nonce** phân biệt từng request. Client ID là dữ liệu tự khai **trước HMAC**, chỉ trở thành danh tính đáng tin **sau khi tag HMAC khớp với secret/key đúng policy**.

**Không thêm `keyId` vào nonce namespace theo thói quen.** Trong quá trình rotation, cùng một client có thể có hai key active. Nếu nonce store khóa theo `(clientId,keyId,nonce)`, client có thể dùng **cùng nonce** dưới key ID khác và vượt qua guard của key trước. Một chính sách đơn giản, nhất quán là **nonce unique trên client + audience bất kể key ID**.

Nếu hệ thống có yêu cầu scope khác (ví dụ nonce global giữa các audience dùng chung quyền, tenant ID bắt buộc nằm trong identity), hãy định nghĩa rõ ràng trong contract và đánh giá **khả năng replay qua trust boundaries**. Tránh nối các giá trị tùy ý bằng dấu phân cách khi giá trị chưa được validate; có thể **length-prefix** hoặc hash encoding cấu trúc để tạo storage key an toàn.

**Nonce không phải secret**, nhưng không nên đưa đầy đủ raw nonce/canonical/headers nhạy cảm vào log. Với store, có thể dùng một khóa dạng `SHA256(encode(audience,clientId,nonce))` nếu cần key ngắn, cố định và tránh ký tự phân cách; phải bảo đảm encoding tuple không nhập nhằng và không làm mất namespace.

## 4. Atomic claim: chỉ một trong các request cạnh tranh được chấp nhận

Đây là thao tác nonce store quan trọng nhất:

~~~text
claim(namespaceKey, expiresAt):
    nếu key chưa tồn tại -> tạo key + đặt hạn lưu NGUYÊN TỬ -> ACCEPT
    nếu key đã tồn tại  -> không ghi đè, trả ALREADY_USED -> REJECT
    nếu store lỗi        -> ERROR / fail closed theo chính sách
~~~

### 4.1. Vì sao `GET` rồi `SET` không an toàn?

Một lỗi race condition:

~~~mermaid
sequenceDiagram
    participant A as Verifier A
    participant B as Verifier B
    participant S as Shared store
    A->>S: GET nonce
    S-->>A: MISS
    B->>S: GET nonce
    S-->>B: MISS
    A->>S: SET nonce
    S-->>A: OK
    B->>S: SET nonce
    S-->>B: OK
    Note over A,B: Cả hai cho thực thi request replay
~~~

**Không** ghép `GET` + `SET` thành hai thao tác rồi coi đã chống replay. Trong một hệ thống có nhiều replica, hai request đồng thời có thể đều thấy `MISS` trước khi một replica ghi thành công. Tương tự, không đủ khi dùng một `synchronized` block chỉ bảo vệ **một process** nhưng các node khác vẫn hoạt động độc lập.

### 4.2. Claim nguyên tử đúng

~~~mermaid
sequenceDiagram
    participant A as Verifier A
    participant B as Verifier B
    participant S as Atomic nonce store
    par Hai request cùng nonce
        A->>S: CLAIM NX + TTL
    and
        B->>S: CLAIM NX + TTL
    end
    S-->>A: Ví dụ: CREATED
    S-->>B: Ví dụ: ALREADY_EXISTS
    Note over A,B: Chỉ một request được xử lý tiếp
~~~

Kết quả cụ thể verifier A/B có thể đảo ngược tùy lịch thực thi; bất biến là **tối đa một claim thành công** đối với cùng nonce namespace trong khi token còn phải được giữ.

### 4.3. Trạng thái và thứ tự kiểm tra

~~~mermaid
flowchart TD
    A["HTTP request tại trusted ingress"] --> B["Strict parse, giới hạn body/header, reject duplicate"]
    B --> C["Timestamp và nonce đúng format; freshness theo server clock"]
    C --> D["Chọn key theo client ID + key ID và policy"]
    D --> E["Dựng canonical; tính lại HMAC trên body/method/URI/header"]
    E --> F{"Full HMAC tag khớp?"}
    F -->|Không| X["Reject authentication"]
    F -->|Có| G{"Atomic claim(audience, client ID, nonce, TTL)?"}
    G -->|Already used| R["Reject replay"]
    G -->|Store error| Q["Fail closed hoặc cơ chế nhất quán được duyệt"]
    G -->|Created| H["Authorization + idempotency + business action"]
~~~

**Claim nonce chỉ sau khi HMAC hợp lệ.** Nếu claim trước, attacker có thể sao chép nonce từ request hợp lệ và gửi chữ ký giả để **chiếm trước nonce**, làm request thật bị từ chối (nonce burning / DoS). Kiểm tra timestamp theo format và freshness trước HMAC có thể là bước tối ưu giảm chi phí; nó **không được làm thay đổi danh tính hay quyền** trước khi chữ ký xác minh.

Việc claim có thể xảy ra **trước authorization**, vì đây là mốc đánh dấu một **request đã được xác thực về mặt mật mã**. Khi authorization từ chối, nonce có thể đã bị tiêu thụ — cần mô tả rõ cho client và xử lý retry/idempotency. Quan trọng là không thực hiện nghiệp vụ trước khi cả authentication, replay và authorization được thông qua.

## 5. TTL nonce: không được hết hạn khi timestamp còn fresh

Một nonce store không thể giữ mọi nonce mãi mãi, vì sẽ tốn bộ nhớ/storage. Nhưng **xóa quá sớm làm replay protection mất tác dụng**.

Giả sử hợp đồng yêu cầu:

~~~text
pastWindowSeconds      P = 300
futureToleranceSeconds F = 60
safetyMarginSeconds    M = 10  // ví dụ, cần cấu hình theo vận hành

fresh(ts, now) = (now - P <= ts) AND (ts <= now + F)
~~~

Với signed timestamp `ts`:

~~~text
Request fresh sớm nhất khi: now = ts - F
Request fresh muộn nhất khi: now = ts + P

Khoảng có thể fresh: [ts-F, ts+P]   (biên inclusive)
Chiều dài tối đa:    P+F = 360 giây
~~~

Giả sử một client ký request có `ts=1795831260`, **60 giây trong tương lai** so với server `now=1795831200`. Server có thể nhận sớm ngay tại `now=1795831200` và **vẫn** được chấp nhận tới `now=1795831560` (tức thêm **360 giây** từ lần nhận đầu tiên).

| Thời điểm server | So với signed timestamp | Fresh? | Nhu cầu giữ nonce |
| --- | --- | --- | --- |
| `1795831199` | ts-61s | Không | Request chưa được chấp nhận. |
| `1795831200` | ts-60s | **Có**, sớm nhất | Claim nonce và bắt đầu giữ. |
| `1795831500` | ts+240s | **Có** | Nonce vẫn phải tồn tại. |
| `1795831560` | ts+300s | **Có**, biên cuối | Nonce vẫn phải tồn tại. |
| `1795831561` | ts+301s | Không | Có thể xóa nonce nếu có margin an toàn. |

Nếu store dùng TTL **300 giây từ lần đầu claim**, nonce có thể biến mất từ `now=1795831500` trong khi request **vẫn còn fresh 60 giây nữa**. Kẻ tấn công replay request đúng HMAC ở `1795831530` sẽ nhận `SET NX` thành công nếu key đã hết hạn. Đó là **replay bypass do TTL quá ngắn**.

### 5.1. Công thức expiration theo signed timestamp

Một chính sách có biên an toàn:

~~~text
expiresAt > ts + P
expiresAt = ts + P + M
~~~

Trong ví dụ `P=300,F=60,M=10`, nonce được giữ tới `ts+310` hoặc muộn hơn (khoảng 370 giây từ claim sớm nhất). Dùng phép tính số nguyên có kiểm tra overflow, không đặt expiration bằng giá trị timestamp **chưa xác minh HMAC**.

Nếu dùng TTL tương đối tính từ khi claim, chọn giá trị bảo thủ:

~~~text
TTL_SECONDS = P + F + M = 370 seconds
TTL_MS      = 370000 milliseconds
~~~

TTL này có thể giữ nonce **lâu hơn mức tối thiểu** nếu request được nhận gần cuối freshness window, nhưng đổi lại đơn giản hơn, không cần đồng bộ chính xác đồng hồ của cache với clock verifier để tính absolute expiry. Vẫn cần giới hạn clock skew, độ trễ store và clock rollback theo threat model.

**Biên inclusive:** nếu request còn fresh tại `now=ts+P`, không được xóa nonce **ngay trước hoặc đúng thời điểm đó** rồi cho một replay mới đi qua. Safety margin `M` phải bao phủ độ phân giải giây, làm tròn TTL, lệch clock giữa replica/store và trễ mạng hợp lý.

### 5.2. TTL không chỉ là bài toán chi phí

| Lỗi TTL/eviction | Hậu quả |
| --- | --- |
| TTL chỉ bằng `F` | Nonce bị xóa rất sớm dù request có thể còn được nhận hàng phút. |
| TTL bằng `P` tính từ lúc claim sớm | Thiếu `F`, tạo cửa sổ replay ở cuối. |
| Cache tự evict do `maxmemory-policy` kiểu LRU | Nonce biến mất **trước** thời điểm được phép hết hạn. |
| Replica có server clock chậm bất thường | Một request cũ có thể quay lại vùng fresh sau khi nonce bị xóa. |
| Failover mất write gần đây | Nonce đã claim biến mất, replay được chấp nhận lại. |
| Cleanup SQL xóa bản ghi sớm hơn `ts+P+M` | Nonce có thể được insert lại qua unique constraint. |
| Store tạm lỗi, code coi lỗi như `MISS` | Mất chống replay đúng lúc store lỗi. |

Nonce expiration và freshness **phải là một hợp đồng thống nhất**. Một lưu trữ TTL đúng trong điều kiện clock được kiểm soát **không** bảo đảm an toàn nếu thành phần verifier có thể làm đồng hồ lùi hàng phút rồi tiếp tục nhận request cũ. Cần **NTP/clock drift monitoring** và chính sách fail-closed khi giả định về thời gian không còn đúng.

## 6. Redis: atomic claim bằng một lệnh

Với hệ thống dùng Redis được cấu hình và vận hành đúng yêu cầu an toàn, một lệnh có thể thực hiện **create-if-absent + set TTL** nguyên tử:

~~~redis
SET hmac:nonce:<sha256-of-encoded-scope> 1 NX PX 370000
~~~

Giải nghĩa:

| Thành phần | Ý nghĩa |
| --- | --- |
| `hmac:nonce:<sha256-of-encoded-scope>` | Storage key từ audience, client ID đã xác thực, nonce; placeholder là hash thực tính trên tuple có encoding không nhập nhằng. |
| `1` | Dấu đã claim; không cần lưu body hay secret. |
| `NX` | Chỉ set nếu key chưa tồn tại. |
| `PX 370000` | TTL 370.000 mili giây = 370 giây, ví dụ `P+F+M`. |
| Redis trả `OK` | Claim thành công, request có thể tiếp tục sang bước authorization. |
| Redis trả nil/null | Key đã có, từ chối replay. |
| Timeout/error | **Không** coi là chưa dùng. Từ chối hoặc áp dụng chính sách sự cố bảo mật được phê duyệt. |

**Không** dùng hai lệnh `SETNX key 1` và `EXPIRE key ...` tách rời: process có thể chết sau SETNX nhưng trước EXPIRE, tạo key tồn tại mãi; hoặc một lỗi xử lý khiến trạng thái không nhất quán. Lệnh `SET key value NX PX ttl` đặt cả điều kiện độc nhất và TTL trong **cùng một operation**.

### 6.1. Relative TTL hay absolute expiration?

Cả hai có thể được thiết kế đúng:

- **TTL cố định đủ lớn:** `PX (P+F+M)*1000` khi claim; dễ triển khai, giữ nhiều hơn một chút.
- **Expiration theo signed timestamp:** `expiresAt = ts + P + M`, dùng một thao tác atomically tạo key với absolute expiration (nếu store hỗ trợ, ví dụ Redis `PXAT`); phải xử lý đồng hồ verifier/store và rounding chặt chẽ.

Trong hai cách, **signed timestamp chỉ được tin sau khi HMAC khớp**. Nếu chọn absolute time, store phải không xóa nonce trước khi bất kỳ verifier còn có thể chấp nhận timestamp đó. Đặc biệt, đừng cộng `futureTolerance` vào timestamp thay cho `pastWindow` khi tính ngày hết hạn: thời điểm hết hạn cuối cùng của freshness là **`ts+P`**.

### 6.2. Redis failover và eviction: atomic chưa chắc đồng nghĩa bền vững

Một lệnh `SET NX PX` là nguyên tử **tại một primary đang phục vụ operation**, nhưng thiết kế hệ thống phân tán phải xem xét **durability/replication/failover**:

- Nếu primary đã xác nhận claim nhưng write chưa được sao chép bền vững, failover có thể làm bản ghi nonce **biến mất**. Request bị replay trên primary mới có thể được nhận.
- Replication, Redis `WAIT` hoặc AOF có thể giảm một số cửa sổ mất dữ liệu tùy cấu hình, nhưng **không tự tạo bảo đảm linearizable/durable exactly-once xuyên mọi kiểu failover**.
- `maxmemory-policy` phải tránh **eviction chưa hết hạn** của nonce bảo mật. Nếu Redis hết tài nguyên và không thể ghi claim, verifier **fail closed**, không “cho qua tạm”.
- Nếu nhiều region có Redis độc lập, cùng nonce có thể được claim thành công ở hai nơi. Muốn chống replay toàn cục cần một ranh giới phối hợp/strong consistency hoặc giao thức ownership/sharding có bảo đảm phù hợp.

Với nghiệp vụ tài chính/side effect nhạy cảm, cân nhắc **nonce store bền vững hoặc kết hợp unique constraint/idempotency transaction** thay vì cho rằng một cache bất kỳ đã đủ.

## 7. SQL: unique constraint làm trọng tài giữa các replica

Một lựa chọn bền vững hơn cho khối lượng vừa phải là bảng nonce có **primary key** trên namespace. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE hmac_nonce_claims (
    audience     text NOT NULL,
    client_id    text NOT NULL,
    nonce_hash   bytea NOT NULL,
    expires_at   timestamptz NOT NULL,
    PRIMARY KEY (audience, client_id, nonce_hash)
);
~~~

Ở đây `nonce_hash` có thể là `SHA256(nonceBytes)` hoặc hash của encoding nonce; cần thống nhất encoding và kiểm tra nonce trước đó. Primary key không chứa `key_id` để trạng thái chống replay nhất quán qua key rotation.

Claim bằng **một thao tác INSERT có unique constraint**, không SELECT trước:

~~~sql
INSERT INTO hmac_nonce_claims
    (audience, client_id, nonce_hash, expires_at)
VALUES
    ($1, $2, $3, $4)
ON CONFLICT (audience, client_id, nonce_hash)
DO NOTHING
RETURNING nonce_hash;
~~~

- Trả **một row**: claim thành công.
- Không trả row: nonce đã được claim, reject replay.
- Lỗi transaction, mất kết nối hoặc commit không rõ kết quả: **không tự giả định claim thành công hoặc chưa có**; fail closed hoặc reconcile idempotent theo policy.

**Phải commit claim trước khi cho phép side effect**, hoặc thiết kế một transaction nhất quán phù hợp. Nếu backend là hệ thống khác (message queue/payment processor), không thể giả định commit nonce và gọi API bên ngoài là **một transaction phân tán tự động**. Đối với nghiệp vụ có side effect, cần idempotency/outbox hoặc giao thức giao dịch thích hợp.

### 7.1. Cleanup database

Row nonce hết hạn có thể được xóa theo lịch để giới hạn storage, **nhưng chỉ xóa khi thời điểm hết hạn đã qua** và khi giả định đồng hồ được đáp ứng. Index trên `expires_at` giúp cleanup theo batch. Đừng xóa theo “row tạo hơn 300 giây” khi timestamp tương lai có thể còn fresh; TTL/cleanup cần cùng logic `ts+P+margin` hoặc retention bảo thủ.

### 7.2. Dung lượng và trade-off lưu trữ

Nếu mỗi client gửi \(R\) request/giây và nonce giữ ít nhất \(T\) giây, ước lượng số bản ghi đang hoạt động:

\[
N \approx R \times T
\]

Ví dụ \(R=1000\) request/giây, \(T=370\) giây thì xấp xỉ **370.000 nonce records** đang sống ở steady state, chưa tính overhead của key, index, replication, persistence và traffic burst. Cần capacity planning, rate limits theo client/audience và metric về nonce count, occupancy, conflict rate, write latency, outage/retry và evictions.

**Không nên giảm TTL dưới mức an toàn để tiết kiệm RAM.** Nếu store quá tải, ưu tiên giới hạn traffic, sharding hợp lệ, tối ưu representation hoặc tăng tài nguyên mà vẫn giữ thuộc tính chống replay.

## 8. Java 17: mô phỏng nonce store nguyên tử và xác thực HMAC

Đoạn chương trình dưới đây tự chứa, minh họa **client ký request**, **verifier xác minh HMAC/timestamp** rồi claim nonce vào một store trong JVM. Chương trình dùng `ConcurrentHashMap.compute` để làm một thao tác **đọc-kiểm tra-ghi nguyên tử theo cùng key** và kiểm thử nhiều luồng cùng claim một nonce.

**Giới hạn rõ ràng:** `DemoNonceStore` **không có background eviction, không bền vững, không dùng chung qua JVM hoặc region**. Nó thích hợp cho unit test/giải thích atomicity, **không** được dùng thay Redis/SQL phù hợp trong cluster. Bài thực hành không chạy request thật ra mạng.

### 8.1. Chương trình đầy đủ

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class NonceStoreExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String METHOD = "POST";
    private static final String RAW_TARGET =
        "/v1/transfers?currency=VND";
    private static final String AUDIENCE = "transfers-api";
    private static final String CLIENT_ID = "partner-42";
    private static final String CONTENT_TYPE = "application/json";
    private static final String OLD_KEY_ID = "key-2026-11";
    private static final String NEW_KEY_ID = "key-2026-12";
    private static final long PAST = 300;
    private static final long FUTURE = 60;
    private static final long MARGIN = 10;

    record SignedRequest(
        String method, String rawTarget,
        String clientId, String keyId, String timestamp,
        String nonce, String contentType, String bodyHash,
        String signature, byte[] body
    ) {}

    record KeyRecord(
        String clientId, String keyId, byte[] secret,
        Instant activeFrom, Instant expiresAt, boolean revoked
    ) {}

    // Mô phỏng claim có expiry; chỉ có atomicity trong MỘT JVM.
    static final class DemoNonceStore {
        private final ConcurrentHashMap<String, Long> expires =
            new ConcurrentHashMap<>();

        boolean claim(String audience, String clientId, String nonce,
                long nowEpochSeconds, long expiresAtEpochSeconds) {
            if (expiresAtEpochSeconds <= nowEpochSeconds) {
                return false;
            }
            // Input đã được validate và HMAC xác thực trước claim.
            // Length-prefix ngăn nhập nhằng giữa các phần tử tuple.
            String storageKey =
                audience.length() + ":" + audience +
                clientId.length() + ":" + clientId +
                nonce.length() + ":" + nonce;
            AtomicBoolean claimed = new AtomicBoolean(false);
            expires.compute(storageKey, (key, previousExpiry) -> {
                if (previousExpiry != null &&
                    previousExpiry > nowEpochSeconds) {
                    return previousExpiry; // Key còn hạn: replay.
                }
                claimed.set(true);
                return expiresAtEpochSeconds;
            });
            return claimed.get();
        }

        // Không cleanup nên map này tăng mãi. Đừng dùng làm store thật.
        int storedEntries() {
            return expires.size();
        }
    }

    static String newNonce() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    static byte[] randomSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return bytes;
    }

    static String sha256Hex(byte[] content)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(content)
        );
    }

    static byte[] mac(byte[] secret, String canonical)
            throws GeneralSecurityException {
        // Mac có trạng thái: tạo mới cho mỗi phép tính/thread.
        Mac hmac = Mac.getInstance("HmacSHA256");
        hmac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return hmac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8)
        );
    }

    static String canonical(String method, String rawTarget,
            String clientId, String keyId, String timestamp,
            String nonce, String contentType, String bodyHash) {
        if (!METHOD.equals(method) ||
            !RAW_TARGET.equals(rawTarget) ||
            !CLIENT_ID.equals(clientId) ||
            !(OLD_KEY_ID.equals(keyId) || NEW_KEY_ID.equals(keyId)) ||
            !CONTENT_TYPE.equals(contentType) ||
            timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}") ||
            nonce == null || !nonce.matches("[0-9a-f]{32}") ||
            bodyHash == null ||
            !bodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                "Canonical request sai hợp đồng"
            );
        }
        return String.join("\n",
            "HMAC-NONCE-STORE-V1",
            method,
            rawTarget,
            "audience:" + AUDIENCE,
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + contentType,
            "x-content-sha256:" + bodyHash
        ); // LF, UTF-8, không có LF cuối.
    }

    static byte[] decodeSignature(String value) {
        if (value == null ||
            !value.matches("[A-Za-z0-9+/]{43}=")) {
            return null; // HMAC-SHA256 full 32 byte.
        }
        try {
            byte[] tag = Base64.getDecoder().decode(value);
            if (tag.length != 32 ||
                !Base64.getEncoder().encodeToString(tag)
                    .equals(value)) {
                return null;
            }
            return tag;
        } catch (IllegalArgumentException malformed) {
            return null;
        }
    }

    static Long parseTimestamp(String text) {
        if (text == null || !text.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean fresh(long ts, long now) {
        try {
            return ts >= Math.subtractExact(now, PAST) &&
                   ts <= Math.addExact(now, FUTURE);
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static SignedRequest sign(byte[] secret, String keyId,
            String nonce, Clock clientClock)
            throws GeneralSecurityException {
        byte[] body =
            "{\"transferId\":\"t-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);
        String timestamp = Long.toString(
            clientClock.instant().getEpochSecond()
        );
        String hash = sha256Hex(body);
        String signedText = canonical(
            METHOD, RAW_TARGET, CLIENT_ID, keyId,
            timestamp, nonce, CONTENT_TYPE, hash
        );
        String signature = Base64.getEncoder().encodeToString(
            mac(secret, signedText)
        );
        return new SignedRequest(
            METHOD, RAW_TARGET, CLIENT_ID, keyId,
            timestamp, nonce, CONTENT_TYPE, hash,
            signature, body
        );
    }

    static boolean verifyAndClaim(SignedRequest req,
            Map<String, KeyRecord> keyring,
            Clock serverClock, DemoNonceStore store)
            throws GeneralSecurityException {
        if (req == null || req.body() == null ||
            req.body().length > 65536) {
            return false;
        }
        byte[] receivedTag = decodeSignature(req.signature());
        Long ts = parseTimestamp(req.timestamp());
        if (receivedTag == null || ts == null) {
            return false;
        }

        Instant verifiedAt = serverClock.instant();
        long now = verifiedAt.getEpochSecond();
        if (!fresh(ts, now)) {
            return false;
        }

        final String text;
        try {
            String actualHash = sha256Hex(req.body());
            if (!actualHash.equals(req.bodyHash())) {
                return false;
            }
            text = canonical(
                req.method(), req.rawTarget(), req.clientId(),
                req.keyId(), req.timestamp(), req.nonce(),
                req.contentType(), actualHash
            );
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        // Client ID/key ID chưa đáng tin trước phép so HMAC.
        KeyRecord key = keyring.get(
            req.clientId() + ":" + req.keyId()
        );
        if (key == null || key.revoked() ||
            !req.clientId().equals(key.clientId()) ||
            !req.keyId().equals(key.keyId()) ||
            key.secret() == null || key.secret().length < 32 ||
            key.activeFrom() == null || key.expiresAt() == null ||
            verifiedAt.isBefore(key.activeFrom()) ||
            !verifiedAt.isBefore(key.expiresAt())) {
            return false;
        }

        byte[] expectedTag = mac(key.secret(), text);
        if (expectedTag.length != 32 ||
            !MessageDigest.isEqual(expectedTag, receivedTag)) {
            return false;
        }

        // Đã xác thực HMAC và freshness: bây giờ mới claim nonce.
        final long expiresAt;
        try {
            expiresAt = Math.addExact(
                ts, Math.addExact(PAST, MARGIN)
            );
        } catch (ArithmeticException overflow) {
            return false;
        }
        return store.claim(
            AUDIENCE, req.clientId(), req.nonce(), now, expiresAt
        );
    }

    static SignedRequest replaceBody(
            SignedRequest src, byte[] changed) {
        return new SignedRequest(
            src.method(), src.rawTarget(), src.clientId(),
            src.keyId(), src.timestamp(), src.nonce(),
            src.contentType(), src.bodyHash(), src.signature(), changed
        );
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] vectorKey = new byte[20];
        Arrays.fill(vectorKey, (byte) 0x0b);
        String tag = HexFormat.of().formatHex(
            mac(vectorKey, "Hi There")
        );
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        check(expected.equals(tag), "RFC 4231 vector sai");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        byte[] oldSecret = randomSecret();
        byte[] newSecret = randomSecret();
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC
        );
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        Instant end = Instant.parse("2027-01-01T00:00:00Z");
        KeyRecord oldKey = new KeyRecord(
            CLIENT_ID, OLD_KEY_ID, oldSecret, start, end, false
        );
        KeyRecord newKey = new KeyRecord(
            CLIENT_ID, NEW_KEY_ID, newSecret, start, end, false
        );
        Map<String, KeyRecord> keys = Map.of(
            CLIENT_ID + ":" + OLD_KEY_ID, oldKey,
            CLIENT_ID + ":" + NEW_KEY_ID, newKey
        );
        SignedRequest request = sign(
            oldSecret, OLD_KEY_ID, newNonce(), fixed
        );

        // Java HttpRequest chỉ dựng HTTP; ví dụ không gửi ra mạng.
        HttpRequest http = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + RAW_TARGET))
            .header("Content-Type", request.contentType())
            .header("X-Client-Id", request.clientId())
            .header("X-Key-Id", request.keyId())
            .header("X-Timestamp", request.timestamp())
            .header("X-Nonce", request.nonce())
            .header("X-Content-SHA256", request.bodyHash())
            .header("X-Signature", request.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(request.body()))
            .build();
        check(METHOD.equals(http.method()), "HTTP method sai");

        // Happy path: lần đầu thành công, phát lại cùng request bị reject.
        DemoNonceStore shared = new DemoNonceStore();
        check(verifyAndClaim(request, keys, fixed, shared),
            "Claim đầu tiên phải thành công");
        check(!verifyAndClaim(request, keys, fixed, shared),
            "Replay với cùng nonce phải bị từ chối");

        // Timestamp mới nhưng VẪN cùng nonce và HMAC được ký lại:
        // nonce vẫn bị từ chối theo client + audience, không theo timestamp.
        Clock oneSecondLater = Clock.offset(
            fixed, Duration.ofSeconds(1)
        );
        SignedRequest sameNonceNewTimestamp = sign(
            oldSecret, OLD_KEY_ID, request.nonce(), oneSecondLater
        );
        check(!verifyAndClaim(
                sameNonceNewTimestamp, keys, oneSecondLater, shared),
            "Timestamp mới không làm nonce cũ hợp lệ");

        // Rotation: cùng client/audience/nonce qua key ID mới vẫn bị reject.
        SignedRequest sameNonceNewKey = sign(
            newSecret, NEW_KEY_ID, request.nonce(), fixed
        );
        check(!verifyAndClaim(
                sameNonceNewKey, keys, fixed, shared),
            "Key rotation không được reset nonce namespace");
        check(verifyAndClaim(
                sameNonceNewKey, keys, fixed, new DemoNonceStore()),
            "Key mới hợp lệ nếu nonce chưa claim ở một store mới");

        // Nonce MỚI cho cùng client là request mới theo replay protection.
        SignedRequest independent = sign(
            oldSecret, OLD_KEY_ID, newNonce(), fixed
        );
        check(verifyAndClaim(independent, keys, fixed, shared),
            "Nonce mới phải được claim");

        // Hai request có cùng nonce cùng lúc: chỉ MỘT thread thắng.
        DemoNonceStore contested = new DemoNonceStore();
        ExecutorService executor = Executors.newFixedThreadPool(8);
        CountDownLatch ready = new CountDownLatch(8);
        CountDownLatch startRace = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();
        try {
            for (int i = 0; i < 8; i++) {
                results.add(executor.submit((Callable<Boolean>) () -> {
                    ready.countDown();
                    startRace.await();
                    return verifyAndClaim(
                        request, keys, fixed, contested
                    );
                }));
            }
            ready.await();
            startRace.countDown();
            int accepted = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    accepted++;
                }
            }
            check(accepted == 1,
                "Atomic claim phải có đúng 1 trong 8 thread thành công");
        } finally {
            startRace.countDown();
            executor.shutdownNow();
        }

        // Body bị sửa: MAC/body digest sai; KHÔNG được claim nonce mới.
        DemoNonceStore bodyStore = new DemoNonceStore();
        byte[] tampered = request.body().clone();
        tampered[0] ^= 1;
        check(!verifyAndClaim(
                replaceBody(request, tampered), keys, fixed, bodyStore),
            "Body bị sửa phải reject");
        check(verifyAndClaim(request, keys, fixed, bodyStore),
            "Body giả không được chiếm trước nonce của request thật");

        // Freshness: -300 và +60 ở biên ACCEPT, -301 và +61 REJECT.
        for (long offset : new long[] {-300L, +60L}) {
            SignedRequest boundary = sign(
                oldSecret, OLD_KEY_ID, newNonce(),
                Clock.offset(fixed, Duration.ofSeconds(offset))
            );
            check(verifyAndClaim(
                    boundary, keys, fixed, new DemoNonceStore()),
                "Timestamp ở biên phải được nhận: " + offset);
        }
        for (long offset : new long[] {-301L, +61L}) {
            SignedRequest stale = sign(
                oldSecret, OLD_KEY_ID, newNonce(),
                Clock.offset(fixed, Duration.ofSeconds(offset))
            );
            check(!verifyAndClaim(
                    stale, keys, fixed, new DemoNonceStore()),
                "Timestamp ngoài cửa sổ phải reject: " + offset);
        }

        // Request ở future+60 vẫn fresh tại now+360.
        SignedRequest future = sign(
            oldSecret, OLD_KEY_ID, newNonce(),
            Clock.offset(fixed, Duration.ofSeconds(60))
        );
        Clock latestFresh = Clock.offset(
            fixed, Duration.ofSeconds(360)
        );
        check(verifyAndClaim(
                future, keys, latestFresh, new DemoNonceStore()),
            "Future+60 phải còn fresh sau 360 giây");
        check(!verifyAndClaim(
                future, keys,
                Clock.offset(fixed, Duration.ofSeconds(361)),
                new DemoNonceStore()),
            "Sau 361 giây phải reject vì quá hạn");

        // Key bị revoke dù HMAC có thể được tính đúng.
        KeyRecord revoked = new KeyRecord(
            CLIENT_ID, OLD_KEY_ID, oldSecret, start, end, true
        );
        check(!verifyAndClaim(
                request, Map.of(
                    CLIENT_ID + ":" + OLD_KEY_ID, revoked),
                fixed, new DemoNonceStore()),
            "Key revoked phải bị từ chối");
        System.out.println(
            "PASS: HMAC, atomic nonce claim, race, replay, TTL policy"
        );
    }
}
~~~

### 8.2. Phân tích atomicity của `ConcurrentHashMap.compute`

Trong `DemoNonceStore.claim`, một lời gọi `compute(storageKey, ...)` quyết định việc **giữ expiry cũ hoặc ghi expiry mới** dưới thao tác atomic theo key trong một map. Với 8 request song song cùng namespace, chỉ một request thấy key chưa được claim và đặt hạn lưu.

~~~java
expires.compute(storageKey, (key, previousExpiry) -> {
    if (previousExpiry != null && previousExpiry > nowEpochSeconds) {
        return previousExpiry; // Nonce đã claim, reject.
    }
    claimed.set(true);
    return expiresAtEpochSeconds;
});
~~~

`AtomicBoolean` chỉ chuyển kết quả ra khỏi callback của **chính lời gọi**; tính atomic đến từ `ConcurrentHashMap.compute`. Callback phải ngắn, không làm HTTP request, không có side effect từ bên ngoài. Nếu một service chạy trên 10 JVM, mỗi JVM có map riêng, **cả 10 JVM vẫn có thể nhận cùng nonce**. Production phải chuyển tính atomic đến **lưu trữ dùng chung/nhất quán** và có chính sách durability/failover.

**Điểm demo có chủ ý chưa giải quyết:** Map không tự xóa nonce hết hạn, vì vậy sẽ tăng bộ nhớ và có thể giữ key vô hạn cho tới khi cùng nonce xuất hiện lại. Không dùng kiểu triển khai này cho production; hãy chọn store hỗ trợ TTL cleanup an toàn và giới hạn tài nguyên.

### 8.3. Độ dài HMAC và thời điểm claim

Ví dụ yêu cầu:

~~~text
X-Signature: 44 ASCII characters, standard padded Base64
decoded tag: 32 bytes full HMAC-SHA256
expected tag: 32 bytes from server-side HMAC
comparison: MessageDigest.isEqual(expectedTag, receivedTag)
~~~

Trước khi claim, verifier đã kiểm tra method, raw URI/query, body digest, client/key ID, timestamp và nonce trong **canonical**. Nếu attacker thay body hoặc nonce mà không ký lại, HMAC fail và **không tiêu thụ nonce**. Ngay cả khi signer tự ký lại bằng secret hợp lệ với **timestamp khác nhưng nonce cũ**, store vẫn reject trong cùng namespace.

### 8.4. Kiểm thử hai lần claim trên key khác nhau

Trong key rotation, request được ký bằng key mới và nonce mới có thể được nhận theo policy. Nhưng nếu nó **tái sử dụng nonce** đã claim từ key cũ, store reject khi namespace không chứa key ID. Đó là lựa chọn nhất quán cho cùng authenticated client/audience; không phải vì tag HMAC của hai request giống nhau (thực tế tag thường **khác nhau** khi key ID và secret khác).

## 9. Thiết kế nonce store phân tán trong production

### 9.1. Thứ tự trách nhiệm giữa ingress, verifier và store

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy ngoài
    participant G as Trusted gateway
    participant V as HMAC verifier
    participant S as Consistent nonce store
    participant B as Backend
    C->>P: HTTP + signed timestamp/nonce + HMAC
    P->>G: Forward/possible rewrite
    G->>V: Strict parsed request + actual body bytes
    V->>V: Recompute canonical, HMAC, timestamp fresh
    alt Invalid HMAC or stale
        V-->>C: Reject authentication
    else Valid HMAC and fresh
        V->>S: Atomic claim(namespace, expiry)
        alt Nonce already used
            S-->>V: ALREADY_USED
            V-->>C: Reject replay
        else Store unavailable
            S-->>V: ERROR
            V-->>C: Fail closed
        else New nonce
            S-->>V: CREATED
            V->>B: Verified identity/request
            B->>B: Authorize + idempotency + side effect
        end
    end
~~~

**Nguồn dữ liệu đáng tin:** server phải lấy method, raw URI/query, signed headers và body bytes thực nhận ở đúng trust boundary. Nếu proxy thay URI, tự giải nén body hoặc thêm header điều khiển nghiệp vụ sau khi HMAC đã verify, nonce store không thể tự khắc phục lỗi canonicalization/authorization.

### 9.2. Một vài lựa chọn lưu trữ

| Lựa chọn | Điểm mạnh | Giới hạn và điều kiện |
| --- | --- | --- |
| Redis `SET NX PX` | Claim + TTL trong một lệnh, latency thấp | Xem xét replication durability, eviction, failover, multi-region. |
| SQL unique index + INSERT | Có transaction và durability theo DB config | DB write/cleanup có chi phí; cần thiết kế throughput/partition. |
| Transactional key-value store với conditional write | Có thể cung cấp uniqueness/durability ở phạm vi rõ ràng | Phải xác minh nhất quán, TTL, lỗi ambiguous commit và cross-region semantics. |
| `ConcurrentHashMap` cục bộ | Phù hợp unit test/một JVM đơn | Không chia sẻ giữa replica, không durability/TTL, không đủ cho cluster. |
| Cache LRU không có pin retention | Triển khai nhanh | **Không phù hợp** nếu có thể evict nonce trước hạn. |

**Không tự dùng một “Bloom filter” thông thường làm nguồn quyết định cuối cùng** cho yêu cầu exactly-once: false positive có thể reject request hợp lệ, còn reset/rotate filter không chặt có thể tạo lỗ hổng thời gian. Bloom filter có thể hỗ trợ lớp tiền lọc/quan sát nếu vẫn có store authoritative và chấp nhận trade-off.

### 9.3. Store không sẵn sàng: nên làm gì?

Nếu verifier đã HMAC PASS nhưng **nonce claim timeout hoặc mất kết nối**, không thể kết luận nonce chưa tồn tại. Đối với endpoint yêu cầu chống replay, phải **fail closed** hoặc dùng fallback **có bảo đảm tương đương, được thiết kế từ trước**. Không bật cờ `allowWhenRedisDown=true` chỉ để duy trì availability mà không đánh giá lỗ hổng.

Lỗi **timeout sau khi gửi claim** có thể là **ambiguous commit**: nonce đã được tạo ở store nhưng response bị mất. Retry cùng nonce sẽ nhận duplicate; đây có thể là một **false reject về trải nghiệm**, nhưng không phải lý do mở bypass. API cần hướng dẫn client ký request mới với nonce mới và dùng **idempotency key** để xác định side effect có xảy ra hay chưa.

### 9.4. Metric và capacity

Theo dõi **claim success/conflict, invalid HMAC, timestamp reject, store latency p95/p99, error rate, TTL/eviction, replication lag, key count, clock drift, namespace throughput và concurrency races**. Không log secret, toàn bộ signature hay body nhạy cảm; nonce có thể được hash/truncate trong telemetry tùy threat model.

Giới hạn tốc độ và quota theo **identity đã xác thực** để một client hợp lệ bị lộ secret không thể vô hạn tạo nonce mới làm đầy store. Rate limit IP/người dùng trước HMAC có thể giảm tải, nhưng không được thay nonce store bằng rate limiting.

## 10. Key rotation, gateway và authorization

### 10.1. Key rotation không phải “reset replay history”

Trong quá trình rotation, một client có thể dùng cả `key-2026-11` và `key-2026-12` trong khoảng overlap. Verifier chọn secret từ `client ID + key ID` rồi xác minh HMAC của các trường đã ký. Sau đó nonce store kiểm tra `(audience, clientId, nonce)` **không phụ thuộc key ID**.

Nếu key cũ bị revoke, request dùng key đó phải bị từ chối **trước claim**, dù timestamp còn fresh. Không nên thử nhiều secret/algorithm thay cho key ID được ký chỉ để “đạt một chữ ký đúng”.

### 10.2. Gateway cần một biên giới rõ ràng

Gateway có thể chịu trách nhiệm HMAC verification và nonce claim một lần, sau đó chuyển identity đã xác minh cho backend qua kênh tin cậy. Nhưng phải **chặn backend bypass**, mTLS/identity nội bộ, xóa header giả từ client như `X-Verified`, và truyền **cùng method, resource, tenant, body** đã được verify. Nếu cả gateway lẫn backend tự claim cùng nonce trên một store, backend sẽ tự từ chối mọi request đã được gateway chấp nhận — cần xác định **điểm claim duy nhất hoặc giao thức ủy quyền xác thực nội bộ**.

### 10.3. Authentication khác authorization

Nonce store chỉ biết nonce đã được dùng; nó **không biết** client có quyền xóa đơn hàng, chuyển tiền, thao tác tenant nào. Sau HMAC, freshness và claim thành công, backend vẫn cần **authorization** theo identity, scopes, action, resource và policy; xử lý idempotency cho nghiệp vụ có side effect. Một client có shared secret hợp lệ nhưng vượt quyền phải bị từ chối dù nonce hoàn toàn mới.

## 11. Ma trận kiểm thử nonce store

Tạo test có một signer và verifier dùng cùng shared secret, timestamp giả định cố định; mỗi trường hợp độc lập dùng một namespace/store sạch nếu không phải bài kiểm tra replay. Những ca liên quan Redis/SQL/failover cần **integration test** thật; `DemoNonceStore` chỉ minh họa logic trong một JVM.

| Ca kiểm thử | Đầu vào/hành động | Kết quả mong đợi |
| --- | --- | --- |
| Request đầu tiên | HMAC đúng, ts fresh, nonce chưa claim | Atomic claim **ACCEPT**. |
| Replay lần hai | Cùng HMAC, timestamp, nonce, body | HMAC vẫn PASS; nonce **REJECT**. |
| Replay 100 lần | Cùng nonce qua nhiều request | Chỉ lần đầu có thể claim. |
| Hai request đồng thời | Cùng namespace trên hai thread/JVM | **Tối đa một** claim thành công trong store authoritative. |
| `GET` rồi `SET` | Hai verifier cùng thấy key missing | Test cho thấy race; triển khai này bị loại. |
| Redis `SET NX PX` | Hai request cùng key tới cùng consistent primary | Một `OK`, một nil/null; TTL đặt atomically. |
| SQL unique constraint | Hai transaction INSERT cùng namespace | Một insert thành công, một conflict/no row. |
| Nonce khác cùng client | Hai request khác nonce, HMAC đúng | Cả hai có thể claim. |
| Cùng nonce khác client | Hai client xác thực, namespace theo client | Hai claim có thể độc lập theo contract. |
| Cùng nonce khác audience | Hai service tách trust domain | Độc lập nếu contract phân tách audience. |
| Cùng nonce, key mới | Cùng client/audience qua key rotation | **REJECT** nếu nonce đã được claim dưới key cũ. |
| Cùng nonce, timestamp mới | Client ký lại HMAC và timestamp mới, nonce không đổi | **REJECT** trong thời gian giữ nonce. |
| Nonce sai format | Chuỗi ngắn/Unicode/colon/leading/trailing SP | Reject trước storage key construction. |
| Nonce có entropy yếu | Timestamp làm nonce hoặc `Math.random()` | Test/review phải phát hiện thiết kế sai; yêu cầu CSPRNG. |
| Body bị sửa, nonce mới | HMAC/body hash sai | **Không claim** nonce; request hợp lệ cùng nonce sau đó còn cơ hội được nhận. |
| HMAC sai, nonce từ request hợp lệ | Attacker cố burn nonce | Không được ghi nonce khi MAC chưa khớp. |
| Timestamp quá cũ | `ts=now-301`, HMAC hợp lệ | Reject freshness, không claim. |
| Timestamp future +60 | `ts=now+60`, HMAC hợp lệ | Fresh; nonce phải giữ ít nhất đến `ts+300+margin`. |
| TTL sai 300s từ claim sớm | Lúc `now+350` replay vẫn fresh | **Test phát hiện lỗ hổng** nonce đã bị xóa quá sớm. |
| TTL đúng P+F+M | 370s từ claim với `P=300,F=60,M=10` | Nonce không biến mất trong freshness window giả định. |
| Cache memory eviction | Nonce bị evict trước expiry | Fail test replay/durability; đổi policy/store. |
| Redis timeout sau claim | Claim có thể đã được commit | Fail closed/không tự nhận là MISS; retry theo idempotency. |
| Redis failover mất write | Primary mới không có nonce | Chỉ an toàn nếu durability/consistency được đảm bảo theo yêu cầu. |
| Hai region độc lập | Cùng nonce tới mỗi region | Test phải phát hiện **double-claim** nếu không có coordination. |
| Gateway và backend cùng claim | Một request hợp lệ được claim hai lần | Thiết kế phải chọn điểm claim duy nhất/hợp đồng nội bộ. |
| Key revoked | HMAC đúng với key cũ đã thu hồi | Reject theo key policy, không claim. |
| Client retry nonce mới | Cùng business ID, timestamp/nonce mới | Nonce có thể ACCEPT; **idempotency** ngăn side effect trùng. |
| Authorization denied | HMAC đúng, nonce mới, client thiếu quyền | Không thực hiện business action; quyết định nonce-consumption theo contract. |

### Câu hỏi tự kiểm tra

1. Vì sao HMAC và timestamp đều đúng nhưng request vẫn có thể là replay?
2. Hai verifier cùng gọi `GET` rồi `SET` trên nonce có thể sai trong tình huống nào?
3. Nếu dùng `P=300,F=60`, tại sao TTL chỉ 300 giây kể từ lúc claim chưa đủ an toàn?
4. Vì sao namespace nonce nên chứa `client ID + audience` nhưng không mặc định chứa `key ID`?
5. Nếu Redis `SET NX PX` trả timeout sau khi đã tạo key, verifier nên coi nonce là “mới” hay “đã dùng”? Vì sao?
6. Vì sao `ConcurrentHashMap.compute` đủ làm unit test atomicity một JVM nhưng không bảo vệ hệ thống 4 replica?
7. Tại sao nonce store không thay thế business idempotency hoặc authorization?
8. Một Redis primary acknowledge write rồi failover mất write có thể tạo lỗ hổng gì dù bản thân `SET NX` nguyên tử?

## 12. Checklist production

- [ ] Nonce được sinh bằng **CSPRNG**, đủ entropy (ví dụ 128 bit) và có format duy nhất; không dùng timestamp/counter cục bộ làm nonce.
- [ ] Nonce, timestamp, client ID, key ID, method, raw URI/query, signed headers và body digest được đưa vào **canonical HMAC request** đúng contract.
- [ ] Ingress từ chối duplicate `X-Nonce`/`X-Timestamp`/`X-Signature`, parser ambiguity, CR/LF và framing/smuggling sai.
- [ ] Tự tính HMAC-SHA256 full tag trên request thực nhận; chỉ claim nonce **sau** HMAC và freshness hợp lệ.
- [ ] Storage key namespace rõ ràng: **(audience, authenticatedClientId, nonce)**, encode không nhập nhằng; không vô tình reset qua key rotation.
- [ ] Claim-if-absent **nguyên tử** trên một store authoritative (Redis `SET NX PX`, SQL unique index hoặc conditional write tương đương).
- [ ] Không dùng `GET`/`SET` tách rời, lock chỉ trong một node hoặc cache có thể evict sớm.
- [ ] TTL không hết trước `signedTimestamp + pastWindow + margin`; nếu TTL tương đối, dùng đủ `P+F+margin` và kiểm soát clock skew.
- [ ] Đánh giá durability, replication, failover và multi-region consistency; không coi cache atomic là bền vững trong mọi sự cố.
- [ ] Khi store lỗi hoặc claim ambiguous, **fail closed** hoặc dùng fallback được phê duyệt có bảo đảm tương đương.
- [ ] Thiết kế capacity, throughput, rate limit, quota, eviction monitoring và TTL cleanup an toàn, không giảm TTL để tiết kiệm RAM.
- [ ] Chỉ có **một điểm claim có thẩm quyền** giữa gateway và backend; hop nội bộ xác thực, chặn bypass và header identity giả.
- [ ] Key rotation tra client ID/key ID an toàn, kiểm tra revoke/algorithm/audience; nonce namespace nhất quán qua key cũ/mới.
- [ ] Sau nonce claim, kiểm tra authorization theo tenant/action/resource; dùng **idempotency key được ký** để chống side effect lặp do retry với nonce mới.
- [ ] Có test unit và integration cho race đồng thời, duplicate, TTL tại future boundary, outage/failover, multi-region, proxy rewrite và key rotation.

**Kết luận:** **Nonce store** là cơ chế **ghi nhận việc sử dụng một nonce, trong đúng namespace và đủ lâu, bằng một thao tác claim nguyên tử**. HMAC chứng minh tính toàn vẹn và quyền dùng secret; timestamp giới hạn thời gian sống; nonce store ngăn request y hệt được chấp nhận lại. Nhưng tính an toàn chỉ thực sự có khi atomicity, TTL, tính nhất quán nhiều replica, xử lý lỗi store, trust boundary và quản lý key được thiết kế đúng. Với các nghiệp vụ có side effect, nonce store vẫn phải đi cùng **idempotency và authorization**.
