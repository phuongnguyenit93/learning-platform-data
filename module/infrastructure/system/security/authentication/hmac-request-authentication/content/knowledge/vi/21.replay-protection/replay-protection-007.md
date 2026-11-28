# Atomic check and insert trong replay protection cho HTTP request HMAC

**Atomic check and insert** là thao tác kiểm tra nonce chưa được sử dụng **và** ghi nhận nonce ấy thành một hành động **nguyên tử**. Khi hai HTTP request có cùng nonce đến đồng thời, hệ thống chống replay phải bảo đảm **tối đa một request được claim thành công**. Không được cho cả hai cùng vượt qua chỉ vì tại thời điểm từng request đọc, nonce vẫn chưa hiện diện trong store.

Bài này thuộc chương **Replay protection**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Trong module, người học thiết kế xác thực HTTP request bằng **shared secret** và **canonical request** ràng buộc phương thức, URI, signed header hoặc body; thực hành xác minh HMAC, chống replay qua timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**. Trọng tâm bài là **tính nguyên tử của thao tác check-and-insert**, không phải thuật toán sinh HMAC hay định dạng nonce một cách biệt lập.

**Quy tắc thiết kế:** Chỉ thực hiện claim sau khi HMAC và freshness hợp lệ; claim phải có **điểm quyết định nguyên tử** tại một store có thẩm quyền, **thời gian lưu nonce đủ dài**, và trạng thái lỗi store phải được xử lý theo hướng **không cho phép vượt qua xác thực**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả **race condition** khi triển khai `exists/get` rồi `insert/set` bằng hai lệnh tách rời.
2. Phân biệt **atomicity trên một process**, **atomicity ở một primary**, và bảo đảm nhất quán/bền vững khi có nhiều replica, failover hoặc nhiều region.
3. Chọn **storage key** phù hợp: audience + authenticated client ID + nonce; không tách trạng thái replay tùy tiện theo key ID khi rotation.
4. Áp dụng Redis `SET key value NX PX ttl` hoặc SQL `INSERT ... ON CONFLICT DO NOTHING` với unique constraint; hiểu tính nguyên tử và giới hạn của từng cách.
5. Tính TTL giữ nonce từ signed timestamp và cửa sổ freshness, tránh replay sau khi nonce bị xóa sớm.
6. Viết mã Java 17 mô phỏng kiểm tra HMAC/timestamp trước atomic claim và kiểm thử nhiều luồng cùng nonce.
7. Thiết kế xử lý **ambiguous commit**, fail-closed, idempotency, ủy quyền gateway và authorization sau khi claim.

## 2. Tại sao HMAC đúng vẫn cần atomic check and insert?

Client hợp lệ gửi:

~~~http
POST /v1/jobs/42/execute HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: 1795831200
X-Nonce: 00112233445566778899aabbccddeeff
X-Content-SHA256: <hex-sha256-of-body>
X-Signature: <base64-padded-hmac-tag>

{"force":false}
~~~

Các chuỗi `<...>` là placeholder. Giả sử timestamp còn trong cửa sổ và chữ ký đúng với shared secret của client. Attacker có thể ghi lại **nguyên request** rồi phát lại trong khi thời gian còn hạn: HMAC **vẫn đúng** vì không byte nào bị sửa.

| Cơ chế | Điều đã chứng minh | Điều chưa chứng minh |
| --- | --- | --- |
| HMAC-SHA256 trên canonical request | Bên gửi có khả năng dùng shared secret; method, URI, header/body được ký không bị sửa. | Chưa chứng minh nonce chưa được dùng trước đây. |
| Timestamp đã ký + freshness | Request nằm trong khoảng thời gian server chấp nhận. | Cùng request có thể được phát lại nhiều lần trong khoảng ấy. |
| **Atomic nonce claim** | Chưa có request nào **đã claim** cùng nonce namespace trong retention window. | Không đảm bảo cùng ý định nghiệp vụ với **nonce khác** chỉ chạy một lần. |
| Idempotency key + transaction nghiệp vụ | Hạn chế side effect lặp cho cùng ý định. | Không thay thế xác thực HMAC và replay guard ở HTTP ingress. |
| Authorization | Client được phép thực hiện action trên tài nguyên cụ thể. | Không chứng minh tag HMAC đúng hay nonce còn mới. |

Điều kiện nhận một request có thể hình dung:

~~~text
ACCEPT =
    HTTP input được parse nhất quán
    AND key/algorithm/policy hợp lệ
    AND HMAC(full canonical request) khớp
    AND signed timestamp còn fresh
    AND atomicClaim(audience, clientId, nonce) = CREATED
    AND authorization theo action/resource cho phép
    AND điều kiện idempotency/nghiệp vụ thỏa
~~~

Đây là các **bước liên tiếp có điều kiện**, không phải một biểu thức boolean nên tính tất cả toán hạng độc lập. **Không tạo side effect** khi chưa vượt qua các bước kiểm tra cần thiết.

## 3. Race condition khi check và insert tách rời

Giả sử có hai verifier A và B cùng xử lý một request replay. Cả hai gọi:

~~~text
if (!nonceStore.exists(key)) {
    nonceStore.insert(key, expiry);
    return ACCEPT;
}
return REPLAY;
~~~

Mã trông hợp lý nhưng hai lời gọi `exists` và `insert` **không hợp thành một thao tác nguyên tử**.

~~~mermaid
sequenceDiagram
    participant A as Verifier A
    participant B as Verifier B
    participant S as Nonce store
    par Hai request có cùng nonce
        A->>S: EXISTS(key)
        S-->>A: false
    and
        B->>S: EXISTS(key)
        S-->>B: false
    end
    A->>S: INSERT(key)
    S-->>A: OK
    B->>S: INSERT(key)
    S-->>B: OK hoặc ghi đè
    Note over A,B: Nếu logic ứng dụng dựa trên EXISTS, cả hai ACCEPT
~~~

Lỗi xảy ra ngay cả khi mỗi `EXISTS` hoặc `SET` riêng lẻ được thực hiện rất nhanh. Tốc độ không bảo đảm thứ tự logic. Chạy nhiều thread trong một process, nhiều JVM, nhiều pod hoặc nhiều region chỉ khiến cửa sổ race dễ lộ hơn.

### 3.1. Các giải pháp giả tưởng không đủ

| Giải pháp thường bị dùng sai | Vì sao vẫn có vấn đề? |
| --- | --- |
| `Thread.sleep(5)` trước insert | Tăng delay, **không** tạo atomicity. |
| `synchronized` trong mỗi verifier | Chỉ khóa các thread cùng JVM; replica khác không chia sẻ lock. |
| Redis `GET` rồi `SET` | Hai client có thể cùng đọc “missing” và cùng ghi. |
| Redis `SETNX` rồi `EXPIRE` là hai lệnh | Có thể rơi vào trạng thái key không TTL nếu tiến trình chết giữa hai lệnh. |
| `SELECT` trong SQL rồi `INSERT` không có unique constraint | Transaction có thể tranh chấp, cả hai cố ghi và logic sai nếu không có ràng buộc tại DB. |
| Thêm `@Transactional` quanh `exists`/`save` | Một annotation không tự tạo uniqueness hoặc isolation phù hợp cho mọi cạnh tranh. |
| Cache LRU mỗi pod | Mỗi pod có dữ liệu khác nhau; eviction sớm còn tạo replay. |
| Giới hạn request rate | Có thể giảm số request nhưng không bảo đảm một nonce được dùng đúng một lần. |

### 3.2. Bất biến cần kiểm tra

Đối với một nonce namespace `K` đang nằm trong retention window:

\[
\operatorname{successfulClaims}(K)\leq 1
\]

Khi nhiều request cạnh tranh, **tối đa một** được phép qua replay gate, bất kể thứ tự scheduler, pod hoặc kết nối mạng. Với request hợp lệ đầu tiên và store bình thường, mong muốn **một** claim thành công; khi store lỗi có thể **không** request nào thành công vì fail-closed.

## 4. Atomic check and insert đúng nghĩa

Thay hai lệnh đọc/ghi bằng **một thao tác có điều kiện**:

~~~text
claimIfAbsent(key, expiresAt):
    if key CHƯA TỒN TẠI tại điểm quyết định:
        ghi key + hạn lưu
        return CREATED
    else:
        return ALREADY_EXISTS
~~~

Store phải quyết định “key có tồn tại không” và “ghi key/hạn lưu” **như một đơn vị không thể bị hai lời gọi cùng thắng** trong phạm vi nhất quán đã cam kết.

### 4.1. Linearization point

**Linearization point** là thời điểm logic mà mỗi atomic operation được xem như đã xảy ra. Hai thao tác concurrent có thể chồng lấn về thời gian, nhưng kết quả phải tương đương với một thứ tự tuần tự trong đó **chỉ claim đầu tiên** tạo ra key.

~~~mermaid
sequenceDiagram
    participant A as Verifier A
    participant B as Verifier B
    participant S as Authoritative store
    par
        A->>S: CLAIM_IF_ABSENT(K, expiry)
    and
        B->>S: CLAIM_IF_ABSENT(K, expiry)
    end
    S-->>A: Ví dụ CREATED
    S-->>B: ALREADY_EXISTS
    Note over S: Điểm quyết định nguyên tử tạo một thứ tự logic
    Note over A,B: Kết quả A/B có thể đảo chiều; tối đa một thắng
~~~

Không nhất thiết phải khóa toàn bộ store. Nhiều cơ sở dữ liệu và key-value store có thể xử lý đồng thời các **key khác nhau**; yêu cầu là cùng `K` được xử lý theo **một nguồn có thẩm quyền**, với cơ chế concurrency control bảo đảm uniqueness.

### 4.2. Phân biệt atomicity và durability

**Atomicity:** Hai request đồng thời tới cùng store nhất quán không thể cùng claim một nonce còn hạn.

**Durability:** Sau khi store trả CREATED, nonce đã ghi phải **không biến mất** do sự cố theo yêu cầu chống replay. Một thao tác có thể atomic tại Redis primary, nhưng failover mất write vừa ack thì nonce **không còn tồn tại** ở primary mới.

**Global consistency:** Nếu có hai region tự claim trên hai store không đồng bộ, cả hai có thể thấy key missing. Để bảo vệ một endpoint nhận traffic ở cả hai region, phải có điều phối nhất quán hoặc routing/sharding sao cho **một nonce namespace chỉ được một nơi có thẩm quyền quyết định**, kèm phân tích partition/failover.

### 4.3. Kết quả claim phải có ba trạng thái

~~~text
CREATED        -> Nonce mới, cho đi tiếp policy tiếp theo
ALREADY_EXISTS -> Replay hoặc nonce đã dùng, REJECT
ERROR/UNKNOWN  -> Không thể chứng minh nonce mới, FAIL CLOSED
~~~

**Timeout không phải là MISS.** Một request có thể đã được store ghi nonce rồi nhưng phản hồi bị mất. Nếu verifier coi timeout là “chưa từng dùng” và cho qua, replay guard sẽ bị bypass; nếu tự gửi lại cùng nonce, có thể nhận ALREADY_EXISTS. Đây là **ambiguous commit**, cần cơ chế retry/idempotency ở tầng thích hợp, không mở đường cho request không được claim.

## 5. Namespace lưu nonce: phải giữ nguyên qua key rotation

Lựa chọn mặc định trong bài:

~~~text
nonceKey = encodeTuple(audience, authenticatedClientId, nonce)
~~~

Ví dụ:

~~~text
audience = jobs-api
clientId = partner-42
nonce    = 00112233445566778899aabbccddeeff
~~~

**Audience** là phạm vi/trust domain của API, **client ID** là định danh được chứng thực sau HMAC và **nonce** là số ngẫu nhiên cho request. Nếu cùng client có nhiều key còn hiệu lực trong giai đoạn rotation, replay guard vẫn nên áp dụng cho **cùng identity/audience**, bất kể sử dụng key nào.

| Thiết kế namespace | Đánh giá |
| --- | --- |
| `(audience, clientId, nonce)` | Lựa chọn rõ ràng cho mỗi client/audience, không reset khi đổi key. |
| `(audience, clientId, keyId, nonce)` | Có thể cho cùng nonce được claim lại qua key cũ/mới, nếu không có policy chặn riêng. |
| `(nonce)` duy nhất toàn hệ thống | Dễ gây xung đột giữa client; có thể dùng nếu chủ động yêu cầu uniqueness global, nhưng tăng chia sẻ trạng thái. |
| `(clientId, nonce)` | Có thể phù hợp nếu audience không cần tách; cần xác định trust domain. |
| `(IP, nonce)` | Không đáng tin làm identity: nhiều client NAT chung IP, proxy/IPv6 thay đổi. |
| `(signature, nonce)` | Thay signature/canonical trong khi giữ nonce có thể tạo storage key khác; sai ý nghĩa uniqueness. |

Không tin `clientId` trước HMAC: attacker có thể tự khai bất kỳ identifier nào. Chỉ dùng nó cho **lookup key có giới hạn**, rồi sau khi HMAC và key policy hợp lệ mới cho nó đóng vai trò identity khi claim.

**Encoding tuple phải không nhập nhằng.** Nếu các thành phần chứa dấu `:`, cách nối `audience + ":" + client + ":" + nonce` có thể tạo collision giữa tuple khác nhau. Có thể validate alphabet của mọi thành phần, dùng **length-prefix** hoặc một serializer nhị phân chính tắc rồi hash để tạo storage key cố định.

### 5.1. Chọn nonce đủ entropy và ký vào canonical

Ví dụ client sinh nonce 16 byte:

~~~java
byte[] bytes = new byte[16];
new java.security.SecureRandom().nextBytes(bytes);
String nonce = java.util.HexFormat.of().formatHex(bytes);
// 32 ký tự [0-9a-f], entropy từ 16 byte ngẫu nhiên, không phải từ hex.
~~~

Timestamp **không thay nonce**: timestamp trong một giây có thể lặp giữa hàng nghìn request. Cũng không dùng `Math.random()` hoặc counter cục bộ không đồng bộ giữa client replicas. Nonce phải được **HMAC ký**; nếu có thể sửa nonce mà MAC vẫn đúng, attacker sẽ thay nonce cho replay request.

## 6. TTL và freshness: claim phải sống lâu hơn khả năng replay

Hợp đồng ví dụ có:

~~~text
pastWindowSeconds P = 300
futureToleranceSeconds F = 60
safetyMarginSeconds M = 10

fresh(ts, now) = now - P <= ts <= now + F
~~~

`ts` là **signed epoch seconds**, `now` là server epoch seconds ở trust boundary; hai bất đẳng thức có biên **inclusive**. Một request còn có thể được nhận:

~~~text
Sớm nhất: now = ts - F
Muộn nhất: now = ts + P

Khoảng có thể fresh: [ts - F, ts + P]
Chiều dài: P + F = 360 giây
~~~

Giả sử client ký timestamp **60 giây ở tương lai** so với server nhận request đầu tiên. Nếu nonce store đặt TTL chỉ 300 giây từ lần claim đầu, nonce hết hạn khi request **vẫn còn fresh khoảng 60 giây**. Replay lúc ấy có thể được claim lại.

### 6.1. Hai cách expiration hợp lệ

**Cách A — absolute expiration theo signed timestamp đã được HMAC xác minh:**

~~~text
expiresAt >= signedTimestamp + P + M
~~~

Tại request có `ts = now + 60`, nonce được lưu ít nhất đến `now + 370`; freshness chỉ kéo dài đến `now + 360`. Safety margin bao phủ rounding, clock skew trong giả định hệ thống và chênh lệch giữa verifier/store.

**Cách B — TTL cố định bảo thủ tính lúc claim:**

~~~text
TTL = P + F + M = 370 giây
~~~

TTL cố định **370 giây từ lần claim** có thể giữ lâu hơn cần thiết nếu request đầu tiên đến gần cuối freshness window, nhưng không rơi vào cửa sổ replay do nonce xóa quá sớm trong điều kiện đồng hồ được kiểm soát.

| Thời điểm với `ts = 1795831260` | Fresh theo `P=300,F=60`? | Nonce cần còn không? |
| --- | --- | --- |
| `now = 1795831199` (ts-61) | Không | Không claim. |
| `now = 1795831200` (ts-60) | **Có**, đầu cửa sổ | Claim đầu tiên và bắt đầu giữ. |
| `now = 1795831500` (ts+240) | **Có** | **Phải còn**. |
| `now = 1795831560` (ts+300) | **Có**, biên cuối | **Phải còn**. |
| `now = 1795831561` (ts+301) | Không | Có thể cleanup sau biên an toàn. |

### 6.2. Không để TTL phá atomicity

Một claim có thể atomic khi INSERT, nhưng nếu key tự bị **evict trước expiresAt** vì cache đầy bộ nhớ, cùng nonce có thể được claim lại. Các dạng phá vỡ khác là SQL cleanup quá sớm, Redis failover làm mất write, server clock nhảy lùi, hoặc TTL milliseconds bị nhầm với seconds.

Đừng đặt `EXPIRE` tách rời sau `SETNX`. Hạn lưu phải được thiết lập **trong cùng thao tác claim** hoặc cùng transaction có ràng buộc rõ ràng. Nếu storage không thể đáp ứng retention, verifier **không được âm thầm bỏ qua nonce protection**.

### 6.3. Khi nonce đã hết hạn mà client dùng lại?

Chính sách nonce store chủ yếu bảo đảm **không có replay trong khoảng các request ký trước còn có thể fresh**. Sau thời gian lưu, nếu client cố tình ký một request **mới** với timestamp mới và **tái sử dụng nonce cũ**, store có thể đã xóa key và chấp nhận theo cơ chế này; client vẫn **vi phạm khuyến nghị sinh nonce ngẫu nhiên mới cho mỗi request**. Nếu nghiệp vụ đòi uniqueness lâu hơn, cần retention/sequence policy khác hoặc idempotency bền vững; không hứa rằng TTL hữu hạn chứng minh nonce chưa từng xuất hiện trong lịch sử vô hạn.

## 7. Redis: `SET NX PX` thay cho `GET` rồi `SET`

Khi dùng Redis làm authoritative nonce store trong một phạm vi nhất quán phù hợp:

~~~redis
SET hmac:nonce:<scope-hash> 1 NX PX 370000
~~~

`<scope-hash>` là placeholder cho khóa từ tuple `(audience, authenticatedClientId, nonce)` được mã hóa không nhập nhằng và hash/serialize ổn định.

| Thành phần | Tác dụng |
| --- | --- |
| `SET ...` | Đặt dấu “nonce đã claim”. |
| `NX` | Chỉ ghi nếu key **chưa tồn tại**. |
| `PX 370000` | Đặt TTL **370.000 milliseconds** (370 giây) cùng lệnh. |
| Kết quả `OK` | Nonce được claim thành công: CREATED. |
| Kết quả nil/null | Key đã tồn tại: ALREADY_EXISTS, reject. |
| Timeout/network error | Trạng thái chưa biết: ERROR/UNKNOWN, **không cho qua**. |

Thời hạn này chỉ minh họa cho `P=300,F=60,M=10`. Với API khác, tính lại từ contract; không copy một con số cố định không đánh giá nhu cầu.

### 7.1. Tính nguyên tử giới hạn ở đâu?

`SET NX PX` giải quyết **race giữa các request cùng primary Redis** khi primary hoạt động bình thường. Nó **không tự bảo đảm**:

- Write đã ACK luôn sống sót sau failover; replication bất đồng bộ có thể mất write chưa được sao chép.
- Hai Redis cluster độc lập ở hai region không thể cùng nhận một nonce trước khi đồng bộ.
- Nonce sẽ không bị eviction sớm bởi memory policy.
- Kết quả timeout có thể được diễn giải chính xác là “đã tạo” hay “chưa tạo”.

Các tính năng như persistence, AOF, replication, `WAIT` hoặc `WAITAOF` (nếu phiên bản/dịch vụ hỗ trợ) có thể tăng một số bảo đảm vận hành, nhưng **không được tự suy ra linearizability và durable exactly-once qua mọi kiểu failover**. Cần xác định consistency model mà store thực sự cung cấp và đánh giá theo threat model.

### 7.2. Lỗi đáng thử khi integration test Redis

1. 100 request đồng thời dùng cùng nonce và cùng authoritative primary: **một** CREATED, còn lại ALREADY_EXISTS.
2. Primary sập **ngay sau ACK** nhưng trước khi replication/durability hoàn tất: kiểm tra có mất nonce trên primary mới không.
3. Redis memory pressure: nonce chưa hết hạn có bị evict không; store có fail closed khi không còn chỗ ghi không.
4. Claim timeout sau khi lệnh có thể đã chạy: verifier **không chấp nhận**, client được hướng dẫn retry với nonce mới và idempotency khi cần.
5. Sai đơn vị TTL `PX 370` thay vì `PX 370000`: kiểm tra replay ngay sau vài giây để phát hiện.

## 8. SQL: unique constraint làm điểm quyết định nguyên tử

Với PostgreSQL hoặc RDBMS hỗ trợ ràng buộc uniqueness đáng tin, một schema đơn giản:

~~~sql
CREATE TABLE hmac_nonce_claims (
    audience    text NOT NULL,
    client_id   text NOT NULL,
    nonce_hex   char(32) NOT NULL,
    expires_at  timestamptz NOT NULL,
    PRIMARY KEY (audience, client_id, nonce_hex)
);
~~~

Sau HMAC/freshness hợp lệ, thực hiện:

~~~sql
INSERT INTO hmac_nonce_claims (
    audience, client_id, nonce_hex, expires_at
) VALUES ($1, $2, $3, $4)
ON CONFLICT (audience, client_id, nonce_hex) DO NOTHING
RETURNING nonce_hex;
~~~

Số row trả về phân biệt:

- **Một row:** nonce mới được tạo trong transaction; chỉ cho phép đi tiếp khi **commit thành công**.
- **Không row:** nonce đã tồn tại; reject replay.
- **Lỗi transaction/commit không xác định:** fail closed hoặc reconcile theo giao thức bảo vệ đã thiết kế.

**Không SELECT trước INSERT** làm điều kiện quyết định. Unique constraint là trọng tài khi hai transaction tranh chấp cùng primary key. Trạng thái transaction và thời điểm COMMIT phải được xử lý chặt chẽ, nhất là khi downstream side effect không ở cùng cơ sở dữ liệu.

### 8.1. SQL cleanup và nonce đã hết hạn

Nếu row cũ vẫn tồn tại dù `expires_at` đã qua, INSERT mới sẽ bị conflict và bị từ chối. Điều này **bảo thủ về bảo mật** nhưng có thể ảnh hưởng availability khi nonce hiếm khi bị tái sử dụng. Job cleanup chỉ xóa row **sau** thời hạn retention an toàn; không xóa theo thời gian `created_at + 300s` nếu timestamp có thể nằm ở tương lai và còn fresh tổng cộng 360 giây.

Nếu triển khai `DELETE expired + INSERT` hoặc UPSERT để “tái sử dụng key” trong một transaction, phải chứng minh không tồn tại race với request khác, timeout, timestamp, rollback và thẩm quyền clock. Với mục tiêu của bài, **unique INSERT và cleanup riêng sau expiry** là mô hình dễ suy luận hơn.

### 8.2. Atomic claim không đồng nghĩa giao dịch nghiệp vụ exactly-once

Một chuỗi sự kiện:

~~~text
1. Claim nonce COMMIT
2. Backend xử lý transfer/job
3. Backend lỗi trước khi trả response
4. Client retry cùng nonce -> REJECT replay
~~~

Kết quả nghiệp vụ có thể đã chạy hoặc chưa. **Nonce store không phải bộ ghi kết quả idempotency**. Với side effect, cần **idempotency key được ký**, trạng thái kết quả bền vững và transaction/outbox/unique constraint phù hợp. Ngược lại, nếu backend cho phép retry với nonce mới không kiểm tra idempotency, có thể chạy side effect trùng dù mỗi nonce được claim đúng một lần.

## 9. Java 17: minh họa atomic check and insert + HMAC verification

Đoạn mã Java 17 sau dùng `ConcurrentHashMap.compute` cho một **nonce store mô phỏng trong một JVM**. Nó cố ý kiểm tra đầy đủ **HMAC-SHA256**, timestamp và nonce format trước khi claim. Mô hình test còn bao gồm **nhiều thread tranh chấp cùng nonce**, replay qua key rotation, thời hạn nonce và tampering.

**Không đem store này lên production đa replica:** `ConcurrentHashMap` chỉ đồng bộ giữa các thread của **một process** và không có durability, replication hoặc cleanup định kỳ. Trong triển khai thật thay interface `NonceClaims` bằng Redis/SQL có semantics nhất quán, TTL và xử lý ambiguous failure.

### 9.1. Signing contract dùng trong mã

~~~text
HMAC-ATOMIC-CLAIM-V1
POST
/v1/jobs/42/execute
audience:jobs-api
x-client-id:partner-42
x-key-id:<old-or-new-key-id>
x-timestamp:<unix-epoch-seconds>
x-nonce:<32-lowercase-hex>
content-type:application/json
x-content-sha256:<64-lowercase-hex>
~~~

Các dòng nối bằng **LF (0x0A)**, không LF cuối, mã hóa UTF-8. `X-Signature` truyền HMAC-SHA256 full tag **32 byte**, Base64 chuẩn có một dấu `=` ở cuối (**44 ký tự**). Server kiểm tra đúng một signed header tại ingress; các thông tin này không phải RFC HMAC tiêu chuẩn chung, mà là **hợp đồng ví dụ được cả signer và verifier tuân thủ**.

### 9.2. Chương trình đầy đủ

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

public final class AtomicCheckInsertExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/jobs/42/execute";
    private static final String AUDIENCE = "jobs-api";
    private static final String CLIENT = "partner-42";
    private static final String OLD_KEY = "key-2026-11";
    private static final String NEW_KEY = "key-2026-12";
    private static final String CONTENT_TYPE = "application/json";
    private static final long PAST = 300L;
    private static final long FUTURE = 60L;
    private static final long MARGIN = 10L;

    record Request(
        String method, String target, String clientId, String keyId,
        String timestamp, String nonce, String contentType,
        String bodyHash, String signature, byte[] body
    ) {}

    record Key(
        String clientId, String keyId, byte[] secret,
        Instant activeFrom, Instant expiresAt, boolean revoked
    ) {}

    interface NonceClaims {
        boolean claim(String audience, String clientId, String nonce,
            long nowEpochSeconds, long expiresEpochSeconds);
    }

    // Test-only: cùng JVM, không durability, không cleanup, không network.
    static final class InMemoryNonceClaims implements NonceClaims {
        private final ConcurrentHashMap<String, Long> expires =
            new ConcurrentHashMap<>();

        @Override
        public boolean claim(String audience, String clientId, String nonce,
                long nowEpochSeconds, long expiresEpochSeconds) {
            if (expiresEpochSeconds <= nowEpochSeconds) {
                return false;
            }
            // Length-prefix tránh nhập nhằng tuple nếu delimiter có trong ID.
            String k = audience.length() + ":" + audience
                + clientId.length() + ":" + clientId
                + nonce.length() + ":" + nonce;
            AtomicBoolean created = new AtomicBoolean(false);
            expires.compute(k, (key, previousExpiry) -> {
                if (previousExpiry != null &&
                    previousExpiry > nowEpochSeconds) {
                    return previousExpiry;
                }
                created.set(true);
                return expiresEpochSeconds;
            });
            return created.get();
        }
    }

    static byte[] randomSecret() {
        byte[] key = new byte[32];
        RNG.nextBytes(key);
        return key;
    }

    static String randomNonce() {
        byte[] nonceBytes = new byte[16];
        RNG.nextBytes(nonceBytes);
        return HexFormat.of().formatHex(nonceBytes);
    }

    static String sha256(byte[] bytes) throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    static byte[] hmac(byte[] key, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    static String canonical(String method, String target,
            String clientId, String keyId, String timestamp,
            String nonce, String contentType, String bodyHash) {
        if (!METHOD.equals(method) || !TARGET.equals(target) ||
            !CLIENT.equals(clientId) ||
            !(OLD_KEY.equals(keyId) || NEW_KEY.equals(keyId)) ||
            !CONTENT_TYPE.equals(contentType) ||
            timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}") ||
            nonce == null || !nonce.matches("[0-9a-f]{32}") ||
            bodyHash == null || !bodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Invalid signed fields");
        }
        return String.join("\n",
            "HMAC-ATOMIC-CLAIM-V1",
            method, target,
            "audience:" + AUDIENCE,
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + contentType,
            "x-content-sha256:" + bodyHash);
    }

    static byte[] decodeSignature(String text) {
        // Full HMAC-SHA256 32B -> Base64 basic padded 44 ASCII chars.
        if (text == null || !text.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] result = Base64.getDecoder().decode(text);
            if (result.length != 32 ||
                !Base64.getEncoder().encodeToString(result)
                    .equals(text)) {
                return null; // Reject non-canonical Base64.
            }
            return result;
        } catch (IllegalArgumentException malformed) {
            return null;
        }
    }

    static Long timestamp(String text) {
        if (text == null || !text.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean fresh(long signed, long serverNow) {
        try {
            long oldest = Math.subtractExact(serverNow, PAST);
            long newest = Math.addExact(serverNow, FUTURE);
            return signed >= oldest && signed <= newest;
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static Request sign(byte[] secret, String keyId,
            String nonce, Clock clock)
            throws GeneralSecurityException {
        byte[] body = "{\"force\":false}"
            .getBytes(StandardCharsets.UTF_8);
        String ts = Long.toString(clock.instant().getEpochSecond());
        String digest = sha256(body);
        String text = canonical(METHOD, TARGET, CLIENT,
            keyId, ts, nonce, CONTENT_TYPE, digest);
        String signature = Base64.getEncoder().encodeToString(
            hmac(secret, text));
        return new Request(METHOD, TARGET, CLIENT, keyId,
            ts, nonce, CONTENT_TYPE, digest, signature, body);
    }

    static boolean verifyAndClaim(Request r, Map<String, Key> keyring,
            Clock serverClock, NonceClaims claims)
            throws GeneralSecurityException {
        if (r == null || r.body() == null || r.body().length > 65536) {
            return false;
        }
        byte[] supplied = decodeSignature(r.signature());
        Long ts = timestamp(r.timestamp());
        if (supplied == null || ts == null) {
            return false;
        }
        Instant serverNow = serverClock.instant();
        long now = serverNow.getEpochSecond();
        if (!fresh(ts, now)) {
            return false;
        }

        final String message;
        try {
            String actualDigest = sha256(r.body());
            if (!actualDigest.equals(r.bodyHash())) {
                return false;
            }
            message = canonical(r.method(), r.target(), r.clientId(),
                r.keyId(), r.timestamp(), r.nonce(),
                r.contentType(), actualDigest);
        } catch (IllegalArgumentException invalid) {
            return false;
        }

        // Client ID/key ID là lookup hints cho tới khi HMAC đúng.
        Key key = keyring.get(r.clientId() + ":" + r.keyId());
        if (key == null || key.revoked() ||
            !r.clientId().equals(key.clientId()) ||
            !r.keyId().equals(key.keyId()) ||
            key.secret() == null || key.secret().length < 32 ||
            key.activeFrom() == null || key.expiresAt() == null ||
            serverNow.isBefore(key.activeFrom()) ||
            !serverNow.isBefore(key.expiresAt())) {
            return false;
        }
        byte[] expected = hmac(key.secret(), message);
        if (expected.length != 32 ||
            !MessageDigest.isEqual(expected, supplied)) {
            return false;
        }

        // Chỉ khi HMAC hợp lệ mới đặt expiration và claim.
        final long expiry;
        try {
            expiry = Math.addExact(ts,
                Math.addExact(PAST, MARGIN));
        } catch (ArithmeticException overflow) {
            return false;
        }
        return claims.claim(AUDIENCE, r.clientId(), r.nonce(), now, expiry);
    }

    static Request alterBody(Request r, byte[] body) {
        return new Request(r.method(), r.target(), r.clientId(),
            r.keyId(), r.timestamp(), r.nonce(), r.contentType(),
            r.bodyHash(), r.signature(), body);
    }

    static void require(boolean result, String label) {
        if (!result) {
            throw new AssertionError(label);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] secret = new byte[20];
        Arrays.fill(secret, (byte) 0x0b);
        String actual = HexFormat.of().formatHex(
            hmac(secret, "Hi There"));
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        require(expected.equals(actual), "RFC 4231 HMAC test");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        byte[] oldSecret = randomSecret();
        byte[] newSecret = randomSecret();
        Instant activeFrom = Instant.parse("2026-01-01T00:00:00Z");
        Instant activeUntil = Instant.parse("2027-01-01T00:00:00Z");
        Map<String, Key> keyring = Map.of(
            CLIENT + ":" + OLD_KEY,
            new Key(CLIENT, OLD_KEY, oldSecret,
                activeFrom, activeUntil, false),
            CLIENT + ":" + NEW_KEY,
            new Key(CLIENT, NEW_KEY, newSecret,
                activeFrom, activeUntil, false)
        );
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC);
        Request r = sign(oldSecret, OLD_KEY, randomNonce(), fixed);

        // Không gửi request ra mạng: chỉ minh họa HTTP client.
        HttpRequest http = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("Content-Type", r.contentType())
            .header("X-Client-Id", r.clientId())
            .header("X-Key-Id", r.keyId())
            .header("X-Timestamp", r.timestamp())
            .header("X-Nonce", r.nonce())
            .header("X-Content-SHA256", r.bodyHash())
            .header("X-Signature", r.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(r.body()))
            .build();
        require(METHOD.equals(http.method()), "Client HTTP method");

        // Một store: request đầu nhận, replay cùng nonce bị từ chối.
        InMemoryNonceClaims store = new InMemoryNonceClaims();
        require(verifyAndClaim(r, keyring, fixed, store),
            "First claim must succeed");
        require(!verifyAndClaim(r, keyring, fixed, store),
            "Second claim must reject replay");

        // Timestamp và tag mới vẫn không cho reuse nonce đang được giữ.
        Clock nextSecond = Clock.offset(
            fixed, Duration.ofSeconds(1));
        Request sameNonceNewTime = sign(oldSecret, OLD_KEY,
            r.nonce(), nextSecond);
        require(!verifyAndClaim(
            sameNonceNewTime, keyring, nextSecond, store),
            "Changing timestamp must not reset claimed nonce");

        // Key rotation vẫn giữ cùng namespace audience/client/nonce.
        Request sameNonceNewKey = sign(newSecret, NEW_KEY,
            r.nonce(), fixed);
        require(!verifyAndClaim(
            sameNonceNewKey, keyring, fixed, store),
            "Changing key ID must not reset nonce history");

        // Không claim nếu body bị sửa (có thể thử lại request thật).
        InMemoryNonceClaims tamperStore = new InMemoryNonceClaims();
        byte[] tamperedBody = r.body().clone();
        tamperedBody[0] ^= 1;
        require(!verifyAndClaim(
            alterBody(r, tamperedBody), keyring, fixed, tamperStore),
            "Tampered HMAC must fail");
        require(verifyAndClaim(r, keyring, fixed, tamperStore),
            "Invalid MAC must not burn nonce");

        // Hai tag/timestamps đúng nhưng 12 request concurrent cùng nonce:
        // CHỈ MỘT được phép qua gate của cùng store.
        InMemoryNonceClaims contested = new InMemoryNonceClaims();
        ExecutorService pool = Executors.newFixedThreadPool(12);
        CountDownLatch ready = new CountDownLatch(12);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Boolean>> answers = new ArrayList<>();
        try {
            for (int i = 0; i < 12; i++) {
                answers.add(pool.submit((Callable<Boolean>) () -> {
                    ready.countDown();
                    release.await();
                    return verifyAndClaim(r, keyring, fixed, contested);
                }));
            }
            ready.await();
            release.countDown();
            int successes = 0;
            for (Future<Boolean> answer : answers) {
                if (answer.get()) {
                    successes++;
                }
            }
            require(successes == 1,
                "Exactly one of 12 concurrent claims must succeed");
        } finally {
            release.countDown();
            pool.shutdownNow();
        }

        // Freshness boundaries: -300/+60 accepted, -301/+61 rejected.
        for (long delta : new long[] {-300L, +60L}) {
            Request boundary = sign(oldSecret, OLD_KEY, randomNonce(),
                Clock.offset(fixed, Duration.ofSeconds(delta)));
            require(verifyAndClaim(boundary, keyring, fixed,
                new InMemoryNonceClaims()), "Fresh boundary " + delta);
        }
        for (long delta : new long[] {-301L, +61L}) {
            Request outside = sign(oldSecret, OLD_KEY, randomNonce(),
                Clock.offset(fixed, Duration.ofSeconds(delta)));
            require(!verifyAndClaim(outside, keyring, fixed,
                new InMemoryNonceClaims()), "Reject offset " + delta);
        }

        // Request ts=now+60 vẫn fresh tại now+360 (P+F).
        Request future = sign(oldSecret, OLD_KEY, randomNonce(),
            Clock.offset(fixed, Duration.ofSeconds(60)));
        Clock atLastFresh = Clock.offset(fixed,
            Duration.ofSeconds(360));
        require(verifyAndClaim(future, keyring, atLastFresh,
            new InMemoryNonceClaims()), "Future+60 at now+360");
        require(!verifyAndClaim(future, keyring,
            Clock.offset(fixed, Duration.ofSeconds(361)),
            new InMemoryNonceClaims()), "Reject after freshness");

        // Mất store: không được mặc định claim thành công.
        NonceClaims failing = (aud, client, nonce, now, expiry) -> {
            throw new IllegalStateException("Store unavailable");
        };
        boolean failClosed = false;
        try {
            verifyAndClaim(r, keyring, fixed, failing);
        } catch (IllegalStateException outage) {
            failClosed = true; // HTTP boundary should reject/503.
        }
        require(failClosed, "Store errors must not be treated as success");
        System.out.println(
            "PASS: atomic claims, concurrent race, HMAC, freshness");
    }
}
~~~

### 9.3. Atomicity của `ConcurrentHashMap.compute` nằm ở đâu?

Trong demo:

~~~java
expires.compute(k, (key, previousExpiry) -> {
    if (previousExpiry != null && previousExpiry > nowEpochSeconds) {
        return previousExpiry;  // Replay đang còn retention.
    }
    created.set(true);
    return expiresEpochSeconds;
});
~~~

Một lời gọi `compute` xử lý **read-and-update nguyên tử cho cùng key** theo semantics của `ConcurrentHashMap`. Mỗi invocation có `AtomicBoolean` riêng để lấy kết quả ra callback; **không phải `AtomicBoolean` tạo tính nguyên tử giữa các request**. Không đặt I/O, HTTP call hoặc side effect bên ngoài vào callback của `compute`.

Nhưng nếu thay store bằng **12 JVM**, mỗi JVM giữ một `ConcurrentHashMap` riêng, cùng nonce có thể được chấp nhận **12 lần**. Vì vậy production phải dựa vào storage **dùng chung với conditional write và failover model đúng**.

### 9.4. Điểm yếu có chủ ý của mã minh họa

- `InMemoryNonceClaims` không background cleanup, không persistence; map có thể giữ entry rất lâu và mất sạch khi JVM restart.
- Có thể coi expiry cũ là hết hạn và claim lại theo `nowEpochSeconds` của request. Clock giữa các JVM ngoài đời phải được giám sát; production store cần soạn contract về time authority và TTL.
- `Request` chỉ là record test; server thật phải parse HTTP, reject duplicate security headers, request smuggling, CRLF, body quá lớn và URI ambiguity **trước khi xác minh**.
- Mẫu chỉ chọn key ID trong một cấu hình hai key; production cần key manager, audience, route scope, trạng thái client/tenant và algorithm policy.
- Program không tạo business side effect, không cài authorization thực hay idempotency DB; những bước đó **phải được thêm** cho endpoint `execute` thật.
- Nếu store trả timeout sau một claim đã commit, verifier không thể đơn giản xác định nó thành công; chính sách fail-closed + retry mới/idempotency được áp dụng ở production.

## 10. Failover, multi-region và request retry

### 10.1. Failure matrix

| Lỗi | Atomicity có còn đủ? | Hành vi cần thiết |
| --- | --- | --- |
| 20 request đồng thời tới cùng primary lành mạnh | Có nếu store hỗ trợ conditional write | Tối đa một CREATED. |
| Redis `GET` rồi `SET` | **Không** | Đổi sang `SET NX PX`. |
| Redis primary ACK rồi failover mất write | Không bảo đảm durable replay history | Đánh giá cấu hình replication/durability; fail closed khi không chắc chắn. |
| Cache tự evict nonce sớm | Nonce trở lại trạng thái missing | Cấm eviction trước TTL, xử lý thiếu bộ nhớ an toàn. |
| SQL INSERT chưa commit đã cho backend xử lý | Kết quả claim có thể rollback | Chỉ thực thi sau commit, hoặc transaction bảo đảm tương đương. |
| Timeout sau khi store có thể đã ghi | **Ambiguous commit** | Không biến lỗi thành CREATED; retry theo chính sách. |
| Region A và B dùng store độc lập | Có thể đồng thời CREATED ở hai region | Phối hợp namespace qua một authoritative store/shard. |
| Node clock nhảy lùi | Timestamp cũ có thể fresh lại sau cleanup | Clock monitoring, fail-closed khi vượt giả định. |
| Backend và gateway cùng claim một request | Claim thứ hai luôn thấy đã tồn tại | Xác định **một điểm claim có thẩm quyền**. |
| Gateway kiểm tra MAC nhưng backend bị truy cập trực tiếp | Bypass cả claim/authorization | Chặn direct access, xác thực hop nội bộ. |

### 10.2. Retry với cùng nonce hay nonce mới?

Nếu request đã được claim, **gửi lại cùng nonce phải bị từ chối**: đó chính là replay protection. Nếu client không nhận response và muốn retry tác vụ nghiệp vụ, client cần tuân thủ contract:

1. Dùng **idempotency key** cố định cho cùng ý định nghiệp vụ, **nằm trong phạm vi ký**.
2. Sinh **nonce mới**, cập nhật timestamp, body/signature nếu cần, ký lại request.
3. Backend tra trạng thái idempotency một cách **nguyên tử**, trả lại kết quả trước đó hoặc bảo đảm side effect không bị lặp.

**Không** hướng dẫn retry cùng nonce cho đến khi store trả CREATED; làm như vậy đánh mất ý nghĩa guard. Với payment hoặc job execution, nên có trạng thái kiểm tra kết quả để tránh vấn đề “claim xong nhưng side effect chưa biết đã chạy chưa”.

### 10.3. Claim thất bại do authorization có tiêu nonce không?

Một thiết kế phổ biến claim nonce **sau HMAC, trước authorization**, nên request có HMAC đúng nhưng **không đủ quyền** vẫn tiêu nonce. Điều này chặn replay của một request đã được xác thực về mặt mật mã, nhưng ảnh hưởng retry khi policy/permission thay đổi. Phải ghi thành contract, tránh yêu cầu client dùng lại nonce; client có thể ký request mới, còn authorization luôn được kiểm tra tại thời điểm xử lý.

Nếu hệ thống chọn kiểm tra authorization trước claim, cần chứng minh không có side effect/race và không cho phép request đã xác thực bị replay vượt qua logic nghiệp vụ; lựa chọn này phải được thiết kế chủ động, không phải di chuyển code tùy ý.

## 11. Xác thực, phân quyền và canonical request tại trust boundary

Atomic claim **không tự khắc phục một canonical request thiếu thông tin bảo mật**. Ví dụ client ký `POST /v1/jobs/42/execute` nhưng gateway sau khi verify cho phép `X-HTTP-Method-Override: DELETE` làm backend đổi effective method. HMAC và nonce đều có thể hợp lệ trong khi **hành động thật khác hành động đã ký**.

Verifier cần:

- Dựng canonical từ **method, raw URI/query, signed headers và byte body thực nhận**; chốt thứ tự, UTF-8/LF, encoding, body digest.
- Reject duplicate `X-Nonce`, `X-Timestamp`, `X-Signature`, `X-Key-Id` và các header quyết định routing/representation tại trusted ingress.
- Ký timestamp và nonce; kiểm tra signed timestamp theo **server clock** và **đúng format/unit**.
- Chọn shared secret qua client ID/key ID đã được khai báo nhưng chỉ công nhận identity **sau khi HMAC tag khớp** và key active, audience/route hợp lệ.
- Claim nonce atomically trong namespace nhất quán, TTL đủ dài và store không lỗi.
- Thực hiện **authorization** theo identity đáng tin, tenant, action, scope và resource, đồng thời idempotency khi có side effect.

Đặc biệt khi proxy/gateway thực hiện HMAC verification còn backend xử lý nghiệp vụ, phải có **kênh nội bộ xác thực**, ngăn backend bị gọi trực tiếp, xóa header `X-Verified` hoặc `X-User` do client ngoài gửi và truyền **cùng ngữ nghĩa request đã ký**.

## 12. Ma trận kiểm thử atomic check and insert

Với mỗi test, dùng signer hợp lệ và nonce store mới trừ các ca replay/race; test store failover và SQL/Redis cần **integration test thực** chứ không chỉ kiểm thử `ConcurrentHashMap`.

| Case | Thiết lập/thao tác | Kỳ vọng |
| --- | --- | --- |
| Claim đầu tiên | HMAC đúng, timestamp fresh, nonce mới | **CREATED**, có thể đi tiếp authz. |
| Replay tuần tự | Gửi cùng request và nonce lần hai | **ALREADY_EXISTS**, reject. |
| Race 12 thread | Cùng nonce, một instance store | **Chính xác một** CREATED nếu store bình thường. |
| Race 12 JVM | Cùng nonce qua các process | **Tối đa một** CREATED trên authoritative shared store. |
| `GET` + `SET` | Để hai request cùng đọc MISS | Chứng minh race, không dùng cách này. |
| Redis `SET NX PX` | Các claim concurrent trên primary nhất quán | Một `OK`, còn lại nil/null. |
| SQL unique INSERT | Hai transaction insert cùng primary key | Một commit thành công, còn lại conflict/no row. |
| Duplicate security header | Hai `X-Nonce` khác case | Reject tại ingress. |
| Nonce thiếu entropy | Timestamp làm nonce | Lỗi thiết kế client; yêu cầu CSPRNG. |
| Nonce sai format | Có SP, colon hoặc Unicode | Reject trước xây storage key. |
| HMAC sai | Giữ nonce hợp lệ nhưng sửa signature/body | Reject, **không claim nonce**. |
| Sửa nonce trên wire | Giữ HMAC cũ, thay nonce | HMAC FAIL, không claim. |
| Signed timestamp quá cũ | `ts=now-301` với `P=300` | Reject freshness, không claim. |
| Signed timestamp future đúng biên | `ts=now+60` | Có thể claim, retention phải đủ. |
| Nonce TTL 300s từ claim sớm | Replay khi request vẫn fresh ở 350s | Test phát hiện lỗ hổng xóa sớm. |
| Nonce TTL 370s | `P=300,F=60,M=10` | Không mất trước freshness deadline. |
| Cache eviction | Nonce bị đẩy khỏi cache trước expiry | Cấu hình không đạt replay protection. |
| Redis failover mất write | Primary đã ACK nhưng primary mới thiếu nonce | Phát hiện durability gap; cần thiết kế phù hợp. |
| Store timeout | Không biết đã claim hay chưa | **Fail closed**, không coi timeout là MISS. |
| Multi-region active-active | Hai store độc lập nhận cùng nonce | Phát hiện double-claim; cần global consistency/routing. |
| Cùng nonce qua key rotation | Old key đã claim, new key ký lại nonce ấy | **Reject** trong cùng client/audience retention. |
| Khác client | Cùng nonce, hai identity hợp lệ | Có thể claim độc lập nếu namespace theo client. |
| Khác audience | Cùng nonce, hai service độc lập | Có thể claim độc lập nếu contract phân tách audience. |
| Gateway + backend claim đôi | Cùng request claim ở hai tầng | Thiết kế sai; xác định một chủ sở hữu claim. |
| Key revoked | HMAC đúng nhưng key không còn active | Reject trước claim. |
| Retry nonce mới, business ID cũ | HMAC và nonce có thể hợp lệ | **Idempotency** chống side effect lặp. |
| Authentication đúng, quyền thiếu | HMAC và nonce PASS | **Authorization DENY**; không thực hiện nghiệp vụ. |

### Câu hỏi tự đánh giá

1. Tại sao hai lệnh `EXISTS` và `INSERT` riêng lẻ không thể chứng minh nonce chỉ được claim một lần?
2. Linearization point của atomic claim có ý nghĩa gì khi 12 request đến đồng thời?
3. Vì sao `synchronized` trong mỗi JVM không đủ cho các pod khác nhau?
4. Sự khác nhau giữa một lệnh Redis atomic trên primary và tính **bền vững** của nonce sau failover là gì?
5. Với `P=300,F=60`, vì sao nonce cần TTL ít nhất `P+F+margin` nếu dùng relative TTL từ lần claim sớm nhất?
6. Vì sao namespace `(clientId,keyId,nonce)` có thể làm cùng nonce được nhận lại khi client rotate key?
7. Nếu store timeout sau khi đã nhận claim, có thể coi timeout là nonce mới và chấp nhận request không?
8. Atomic nonce claim có thay thế idempotency key và authorization không? Vì sao?

## 13. Checklist trước khi triển khai

- [ ] Nonce là chuỗi ngẫu nhiên đủ entropy (ví dụ 128 bit) có định dạng strict và **được HMAC ký**.
- [ ] Timestamp và nonce nằm trong canonical cùng method, raw URI/query, signed headers và body digest; input thực nhận không bị proxy/backend diễn giải khác.
- [ ] HMAC full tag được decode và so sánh an toàn; kiểm tra freshness theo trusted server clock **trước claim**.
- [ ] Chỉ claim **sau khi HMAC hợp lệ**, không để request giả burn nonce của người khác.
- [ ] Storage namespace rõ ràng **(audience, authenticatedClientId, nonce)**, encoding tuple không nhập nhằng; cân nhắc key rotation khi chọn namespace.
- [ ] Không dùng read-then-write, lock cục bộ hay `GET` + `SET` tách rời để quyết định accept.
- [ ] Dùng **conditional write nguyên tử** tại authoritative store: Redis `SET NX PX`, SQL unique `INSERT` hoặc lựa chọn có semantics tương đương.
- [ ] Có đủ ba kết quả CREATED, ALREADY_EXISTS, ERROR/UNKNOWN; **timeout và outage fail closed**.
- [ ] TTL bảo đảm giữ nonce đến sau `signedTs+P` có margin, hoặc relative TTL `P+F+margin` phù hợp clock assumptions.
- [ ] Không evict/cleanup nonce khi request đã ký còn fresh; theo dõi drift, memory pressure và TTL unit.
- [ ] Đánh giá transaction commit, replication durability, failover, sharding và multi-region consistency; atomicity trên primary **không tự tạo exactly-once bền vững**.
- [ ] Xác định **một trust boundary/điểm claim có thẩm quyền** giữa gateway và backend; chặn direct bypass và header identity giả.
- [ ] Tách nonce replay guard với **business idempotency**; dùng idempotency key đã ký cho hành động có side effect và lưu trạng thái kết quả.
- [ ] Sau authentication + replay guard, kiểm tra authorization theo client, tenant, action, resource và scope.
- [ ] Có test race thực qua nhiều replica, Redis/SQL, outage/ambiguous commit, future boundary, key rotation, proxy rewrite và authz denied.

**Kết luận:** **Atomic check and insert** là thao tác cốt lõi biến nonce từ một giá trị ngẫu nhiên thành cơ chế chống replay thực sự. Chỉ một lời gọi **claim-if-absent có điều kiện nguyên tử**, TTL đủ dài, storage có thẩm quyền và xử lý lỗi fail-closed mới ngăn được hai request concurrent cùng nonce đi tiếp. Nhưng chống replay vẫn phụ thuộc HMAC/canonical request đúng, timestamp fresh, key policy, proxy/gateway đáng tin và kiểm tra **authorization + idempotency** cho side effect.
