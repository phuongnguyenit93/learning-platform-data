# Bỏ sót hoặc lặp phần tử do phân trang không ổn định

Một khách hàng mở danh sách đơn hàng, tải trang đầu gồm **A, B, C**, rồi cuộn xuống thấy **C xuất hiện lần nữa**. Người khác lại phản ánh đơn **D không bao giờ xuất hiện**, dù tìm trực tiếp bằng ID vẫn có. Lỗi thường bị quy cho frontend append sai dữ liệu, nhưng nguyên nhân cũng có thể ở **ORDER BY thiếu khóa phụ, OFFSET bị dịch bởi giao dịch mới, cursor tạo sai, sort key thay đổi, cache lẫn trang hoặc replica đọc khác thời điểm**. Không thể chữa bằng cách tăng page size hay xóa cache tùy tiện.

Bài thuộc chương **Chẩn đoán sự cố** của module **INTEGRATION_API_REST**: tập trung điều tra theo HTTP resource/URI, hợp đồng JSON/Link, SQL, Java/Spring, quyền theo tenant và kiểm thử đồng thời. Mục tiêu không phải khẳng định mọi kiểu phân trang đều bảo đảm một ảnh chụp dữ liệu; ta sẽ tìm **hợp đồng mà client được hứa**, so với **hành vi thực tế**, rồi chọn cách sửa phù hợp.

## 1. Nhận diện triệu chứng trước khi sửa

### 1.1. Các hiện tượng dễ nhầm nhau

| Triệu chứng client thấy | Nguyên nhân có thể | Bằng chứng nên thu thập |
|---|---|---|
| Item cuối trang 1 lặp ở đầu trang 2 | OFFSET drift, cursor dùng điều kiện bao gồm, sort key đổi | Hai response theo thứ tự thời gian, SQL/page token |
| Item còn tồn tại nhưng bị bỏ sót khi duyệt | OFFSET drift, thiếu tie-breaker, cursor làm tròn timestamp, filter đổi | Snapshot danh sách ID theo khóa, cursor boundary |
| Trang 2 trả rỗng rồi trang 3 lại có dữ liệu | Replica lag, cursor/filter sai, cache key lỗi, dữ liệu thêm mới | Route tới replica, cache HIT/MISS, request query |
| Trang 2 có item của tenant khác | Thiếu điều kiện tenant, cursor không ràng buộc actor, cache chia sẻ | Query plan, principal/tenant scope, cache policy |
| Cùng cursor, hai lần gọi cho kết quả khác | Phân trang trên **live dataset**, status/sort thay đổi, replica khác | Commit timeline, semantics tài liệu |
| Trang 1 chưa đủ page size dù còn item | Filter/authorization sau LIMIT, N+1 query, scan sai | SQL thực thi và chỗ áp filter |
| “hasMore=true” nhưng next luôn rỗng | Chọn sai row làm lookahead, count không đồng bộ, dữ liệu đã biến động | Logic limit+1, nextCursor/Link và test trang cuối |

**Trùng ID trên hai trang không luôn là lỗi cùng loại.** Nếu một request dùng filter A và request sau dùng filter B, hai danh sách khác nhau có thể chứa cùng item hợp lệ. Nếu client tự refresh trang 1 và đồng thời append trang 2 cũ, UI có thể tạo duplicate dù server mỗi chuỗi đều đúng. Luôn xác định **hai request có cùng hành trình phân trang hay không**.

### 1.2. Thu thập dữ liệu sự cố tối thiểu

Yêu cầu người báo lỗi cung cấp **thời điểm UTC, environment, route template, sort/filter/page size, status HTTP, request/trace ID**, hai response liên tiếp và cách client lấy next link. Với dữ liệu cá nhân, chỉ lưu **ID đã pseudonymize hoặc fixture test** trong ticket; không đòi JWT, cookie, access token hay full body nhạy cảm.

~~~http
GET /v1/orders?status=OPEN&limit=3 HTTP/1.1
Host: api.example.test
Authorization: Bearer <redacted>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
Link: </v1/orders?status=OPEN&limit=3&cursor=sample-opaque-token>; rel="next"

{
  "items": [
    {"id":"A","createdAt":"2026-11-18T09:06:00Z"},
    {"id":"B","createdAt":"2026-11-18T09:05:00Z"},
    {"id":"C","createdAt":"2026-11-18T09:04:00Z"}
  ],
  "nextCursor":"sample-opaque-token",
  "hasMore":true
}
~~~

Đây là **ví dụ mô tả**, chuỗi sample-opaque-token không phải cursor đã được ký. Trong API công khai, **cursor là opaque và phải URL-encode khi cần**; đừng gắn placeholder vào request thật. Nếu chỉ nhận được screenshot màn hình mà không có request/response, chưa thể kết luận frontend, proxy hay DB làm sai.

### 1.3. Tách hai loại “ổn định” ngay ở bước triage

- **Live feed:** mỗi trang đọc dữ liệu hiện còn đủ điều kiện tại thời điểm query và tiếp nối theo một ranh giới khóa. Item bị xóa/chuyển trạng thái có thể không còn xuất hiện. Keyset ổn định tốt trước insert ở *đầu* nhưng không tự cố định snapshot.
- **Snapshot/export:** danh sách tại một mốc logic phải được duyệt **đủ và không trùng**, dù dữ liệu live thay đổi. Cần materialized snapshot/temporal versions hoặc cơ chế tương đương; một cursor chỉ lưu lastId chưa đủ.

Hỏi product owner: “Người dùng cần cuộn feed mới nhất hay cần danh sách chính xác để kiểm toán/xuất dữ liệu?” Đây là **câu hỏi về hợp đồng nghiệp vụ**, không chỉ chọn SQL tối ưu.

## 2. Chẩn đoán nhanh bằng ba câu hỏi

~~~mermaid
flowchart TD
    A["Có ID lặp/thiếu khi phân trang"] --> B{"Hai request cùng tenant/filter/sort/limit?"}
    B -->|Không| C["Sửa client state/cache key, tách chuỗi phân trang"]
    B -->|Có| D{"ORDER BY có unique tiebreaker?"}
    D -->|Không| E["Bổ sung total order, test timestamp tie"]
    D -->|Có| F{"Phân trang bằng OFFSET?"}
    F -->|Có| G["Reproduce insert/delete giữa page 1 & 2"]
    F -->|Không| H{"Keyset predicate & cursor có đúng?"}
    H -->|Không| I["Fix boundary, precision, validation"]
    H -->|Có| J["Kiểm tra mutation sort/filter, replica, cache"]
    J --> K{"Contract yêu cầu snapshot?"}
    K -->|Có| L["Materialized/temporal snapshot"]
    K -->|Không| M["Mô tả live semantics và kiểm thử"]
~~~

Một runbook ngắn cho điều tra ban đầu:

1. **Xác nhận cùng chuỗi:** ghi full query được chuẩn hóa (**không log bearer token**), phiên bản API, tenant scope được xác minh và cursor/page index; kiểm tra app không vừa reset filter vừa append.
2. **Đối chiếu response:** lập danh sách các ID của page 1/page 2, xác định duplicate ID nào và item nào bị skip so với truy vấn gốc.
3. **Đọc SQL/ORM thực thi:** kiểm tra ORDER BY, WHERE, LIMIT/OFFSET hoặc tuple comparator; không chỉ tin tên method Repository.
4. **Dựng timeline commit:** ghi transaction thêm/xóa/đổi status/sort giữa hai GET; đừng đồng nhất thời gian tạo object ở Java với thời gian COMMIT.
5. **Kiểm tra routing:** primary/read replica, cache/CDN, gateway path/query rewrite và token scope.
6. **Chọn bản sửa theo contract:** live keyset hoặc snapshot, kèm test hồi quy. Không “chữa” bằng cách lọc trùng trong UI rồi coi dữ liệu đã đầy đủ.

## 3. Lỗi số một: OFFSET/LIMIT bị dịch bởi dữ liệu mới

Giả sử dữ liệu ban đầu sắp theo created_at giảm dần:

| Vị trí | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| ID | A | B | C | D | E | F |

**Trang 1:** LIMIT 3 OFFSET 0 trả **A, B, C**.

### 3.1. Insert ở đầu làm item bị lặp

Khi client chưa gọi trang 2, transaction khác COMMIT đơn mới **X** lên đầu. Danh sách giờ là **X, A, B, C, D, E, F**. **LIMIT 3 OFFSET 3** trả **C, D, E** → **C lặp**. Không có lỗi SQL syntax và cả hai GET đều trả 200.

### 3.2. Delete ở trước offset làm item bị bỏ sót

Từ dataset ban đầu, xóa **B** sau trang 1. Danh sách còn **A, C, D, E, F**. **LIMIT 3 OFFSET 3** trả **E, F**; **D bị bỏ qua** dù D vẫn tồn tại. Nếu service chỉ trả id cuối hoặc tổng count, frontend không thể phát hiện skip chỉ bằng cách kiểm tra số item của trang sau.

~~~sql
-- OFFSET không gắn với phiên bản danh sách ở lần gọi trước.
SELECT id, created_at
  FROM orders
 WHERE tenant_id = :tenant_id
 ORDER BY created_at DESC, id DESC
 LIMIT 3 OFFSET 3;
~~~

**ORDER BY đầy đủ không ngăn OFFSET drift**; nó chỉ loại sự tùy ý khi các khóa sắp xếp trùng nhau. Truy vấn theo offset vẫn phù hợp với dữ liệu nhỏ/ít biến động hoặc trải nghiệm chấp nhận refresh và nhảy trang tùy ý. Vấn đề là **không được quảng bá nó như duyệt snapshot ổn định** qua nhiều request nếu không có snapshot backing.

### 3.3. Kiểm thử để chứng minh trước khi sửa

~~~text
Fixture: A(600), B(500), C(400), D(300), E(200), F(100).
T1: GET ?limit=3&offset=0       -> A,B,C.
T2: INSERT X(700), COMMIT.
T3: GET ?limit=3&offset=3       -> C,D,E.   [lặp C]

Reset fixture.
T1: GET ?limit=3&offset=0       -> A,B,C.
T2: DELETE B, COMMIT.
T3: GET ?limit=3&offset=3       -> E,F.     [mất D]
~~~

Đây là **negative test** dùng để tái hiện bug, không phải assertion mà bản sửa keyset phải giữ nguyên kết quả. Khi chuyển sang cursor, cần thêm test tương ứng cho insert ở đầu để chứng minh không lặp C và không skip D; cùng lúc định nghĩa rõ dữ liệu **mới xuất hiện phía sau cursor** có được đưa vào feed hay không.

## 4. Lỗi số hai: ORDER BY không tạo thứ tự toàn phần

Với **ORDER BY created_at DESC** và page size 2, nếu ba đơn cùng timestamp, DB có quyền thay đổi thứ tự giữa hai truy vấn. Điều này có thể xảy ra **ngay cả khi không có insert/delete**, vì relational tables không có thứ tự mặc định cho các row đồng hạng.

~~~sql
-- Sai nếu created_at không unique:
SELECT id FROM orders
 WHERE tenant_id = :tenant_id
 ORDER BY created_at DESC
 LIMIT :limit OFFSET :offset;

-- Chọn một tie-breaker unique và ổn định:
SELECT id FROM orders
 WHERE tenant_id = :tenant_id
 ORDER BY created_at DESC, id DESC
 LIMIT :limit OFFSET :offset;
~~~

Ví dụ với cùng thời điểm **09:00** có **c3, c2, c1**, và **b9** ở 08:59. Một chuỗi đúng theo (created_at DESC, id DESC) là **c3, c2, c1, b9**. Nếu dùng cursor **chỉ có created_at** và predicate created_at **< 09:00**, c1 bị skip sau trang 1 [c3,c2]. Nếu dùng **<= 09:00**, c3/c2 có thể lặp. Giữ **cả created_at và id** trong cursor.

**Cần kiểm tra:** tất cả ORDER BY columns có **collation, null ordering, timezone/precision** xác định; khóa tie-breaker là unique trong phạm vi filter; backend dùng cùng chiều sắp xếp khi tạo cursor và khi query trang sau. Nếu API cho sort động như price/name/priority, mỗi sort cần logic cursor riêng và test theo **NULLS FIRST/LAST** tương ứng. Đừng dùng UUID như “timestamp thay thế”: UUID có thể so sánh ổn định nhưng không mặc nhiên chứa thứ tự thời gian tạo.

## 5. Lỗi số ba: keyset dùng sai boundary hoặc tạo cursor từ row sai

Keyset/cursor tránh dịch offset nhưng chỉ đúng khi query dùng cùng quy tắc thứ tự mà cursor lưu. Với created_at DESC, id DESC, sau item có khóa (t, id) phải lấy **tuple nhỏ hơn**, không bao gồm chính item đó:

~~~sql
-- PostgreSQL, created_at và id NOT NULL.
SELECT id, created_at, status
  FROM orders
 WHERE tenant_id = :tenant_id
   AND status = :status
   AND (created_at, id) < (:last_created_at, :last_id)
 ORDER BY created_at DESC, id DESC
 LIMIT :requested_size_plus_one;
~~~

Với DB không hỗ trợ row-value comparator tương ứng, điều kiện logic là:

~~~sql
AND (
     created_at < :last_created_at
     OR (created_at = :last_created_at AND id < :last_id)
)
~~~

**Điều kiện này dành cho cả hai khóa DESC**. Khi sort hỗn hợp như created_at DESC, id ASC, không copy tuple comparator nguyên xi; cần điều kiện **created_at < t OR (created_at = t AND id > lastId)**. Nếu sort key nullable, điều kiện phải khớp NULLS FIRST/LAST; so sánh SQL với NULL thường cho UNKNOWN nên row có thể bị bỏ sót.

### 5.1. Nhầm dấu so sánh

| ORDER BY | Cursor tại B | Điều kiện đúng cho trang sau |
|---|---|---|
| created_at DESC, id DESC | (t, B) | (created_at, id) **nhỏ hơn** (t, B) |
| created_at ASC, id ASC | (t, B) | (created_at, id) **lớn hơn** (t, B) |
| created_at DESC, id ASC | (t, B) | created_at < t **OR** (created_at = t AND id > B) |

Dùng **<=** hoặc **>=** có thể trả lại item cuối trang trước; chỉ so sánh created_at mà không có id sẽ gây bỏ sót hàng đồng timestamp. Test cả ca **cùng timestamp, cùng ngày, precision microsecond**, không chỉ dữ liệu giả mỗi item cách nhau một giờ.

### 5.2. Lookahead row làm mất item

Để biết còn trang sau, query **limit + 1**, trả **limit** item. Nếu lấy **row thứ limit+1** làm cursor, chính row đó sẽ bị lọt khỏi chuỗi:

~~~text
Dataset DESC: A, B, C, D, E.
Client yêu cầu limit=2; SQL đọc [A, B, C].
ĐÚNG: body=[A,B], nextCursor=key(B), hasMore=true.
SAI:  body=[A,B], nextCursor=key(C) -> trang 2 [D,E], mất C.
~~~

Với dữ liệu không thay đổi, nếu query chỉ trả đúng **limit** item, không được suy hasMore=true từ việc “đầy trang”; có thể đã đến cuối. Dùng row thứ limit+1 để quyết định hasMore. Đối với trang cuối, **nextCursor=null và không có Link rel=next**. Tránh tạo cursor mới từ item cuối nếu **hasMore=false**, khiến client gọi một trang rỗng không cần thiết.

### 5.3. Timestamp bị làm tròn hoặc mất timezone

PostgreSQL **timestamptz** có thể lưu độ phân giải microsecond. Backend serialize createdAt cho client dưới dạng chỉ **millisecond**, rồi lấy timestamp đó làm cursor ở request sau: ranh giới bị làm tròn có thể làm một row rơi sang sai phía comparator. Không lấy lastCreatedAt từ **giá trị JSON đã làm tròn**; tạo cursor từ khóa chính xác đọc từ DB và codec bảo toàn precision/timezone. Khi dùng Instant/OffsetDateTime, kiểm tra driver/database serialization và format. Test các cặp thời điểm **chỉ khác nhau vài microsecond**.

Đừng đồng nhất **created_at** với **commit timestamp**. Một transaction tạo row sớm nhưng commit muộn có thể khiến row mới xuất hiện *phía sau cursor* dù người dùng đã nhận trang đầu. Một watermark tính bằng **MAX(id)** hoặc **MAX(created_at)** không đủ chứng minh snapshot nếu có backfill/commit out of order.

## 6. Lỗi số bốn: sort key và tập lọc thay đổi khi đang duyệt

Keyset không phải snapshot. Giả sử sort theo **score DESC, id DESC** với các điểm A=100, B=90, C=80, D=70; client nhận **A,B** và cursor B=90.

| Mutation trước trang 2 | Kết quả có thể xảy ra |
|---|---|
| Chèn X=110 vào đầu | X không xuất hiện trong chuỗi hiện tại, nhưng A/B không bị lặp |
| Chèn X=75 phía sau B | X có thể đi vào trang sau dù không tồn tại lúc trang 1 |
| **Đổi A: 100 → 60** | A có thể **lặp** ở trang sau vì nhảy qua cursor |
| **Đổi D: 70 → 95** | D có thể **bị bỏ sót** vì chuyển lên trước cursor chưa đọc |
| Xóa C trước trang 2 | C không xuất hiện; live feed không hứa giữ item bị xóa |

Kể cả sort key bất biến **created_at**, một filter như **status=OPEN** vẫn có thể đổi:

- Item C chuyển từ OPEN → CLOSED sau trang 1: trang sau không còn C.
- Item D chuyển CLOSED → OPEN trong vùng phía sau cursor: D có thể xuất hiện “mới”.
- Quyền đọc của actor bị thu hồi: item phải biến mất hoặc request bị từ chối, **không được giữ quyền cũ chỉ vì cursor đã ký**.

**Không sửa lỗi dữ liệu biến động bằng cách vô hiệu hóa authorization.** Nếu product yêu cầu duyệt **chính xác tập OPEN tại mốc ban đầu**, thay contract/implementation bằng **snapshot backed by persisted IDs + versions/representations** hoặc temporal query. Nếu chỉ cần feed live, mô tả rõ item mới/đã đổi trạng thái có thể cần refresh và thay đổi sort key có thể gây lệch.

### 6.1. Ba cách xử lý tùy nghiệp vụ

1. **Live feed có khóa bất biến:** sắp theo **created_at/id** không đổi, dùng keyset. Trường status/score có thể hiển thị nhưng không tham gia ORDER BY nếu UX cho phép.
2. **Snapshot ID list:** khi GET trang đầu, tạo snapshotId và lưu danh sách ID tại mốc logic; các trang sau đọc danh sách đó. Nếu cần cả giá trị cũ, phải lưu **representation/version** hoặc có temporal history: ID list đơn thuần không hồi sinh row đã xóa.
3. **Báo cáo/export bất đồng bộ:** POST tạo job bền vững trả **202 Accepted** kèm Location; worker materialize kết quả có TTL, client tải theo snapshot pages. Dùng idempotency và quota, không giữ transaction DB qua nhiều phút người dùng cuộn.

**REPEATABLE READ trong một HTTP GET** không tạo snapshot xuyên nhiều GET: mỗi request thường là một transaction khác nhau. Giữ transaction/snapshot DB mở suốt phiên cuộn thường gây connection exhaustion và vấn đề cleanup/vacuum; nếu cần tính nhất quán mạnh, thiết kế snapshot resource có lifecycle.

## 7. Lỗi số năm: cursor, cache hoặc replica thay đổi phạm vi

### 7.1. Cursor không phải quyền truy cập

Một cursor có thể chứa **lastCreatedAt, lastId, sort, status, pageSize, tenant scope, expiry và version**. Trong API public, client phải coi nó là **opaque**; backend xác minh toàn vẹn bằng HMAC/AEAD hoặc lưu state server-side, kiểm tra scope hiện tại và TTL. **HMAC không mã hóa payload**: đừng nhét JWT, raw email, phone, user profile hoặc secret vào token.

Nếu client dùng cursor của **status=OPEN** cho request **status=CLOSED**, các cặp khóa có thể hợp lệ về hình thức nhưng tạo kết quả sai. Phải **từ chối với 400 Problem Details** hoặc yêu cầu bắt đầu lại theo contract; không âm thầm áp filter mới lên boundary cũ. Cursor tenant A dùng với JWT tenant B phải bị từ chối **trước khi truy vấn**, tránh rò ID/sự tồn tại của tenant A; mọi SQL vẫn phải có tenant/owner predicate độc lập với kiểm tra cursor.

| Sai sót cursor | Dấu hiệu | Cách xác minh |
|---|---|---|
| Không bind tenant/filter/sort/page size | Lặp/thiếu khi client đổi query | Decode an toàn ở backend, so policy/scope |
| Không ký hoặc tin JSON base64 | Client tự đặt lastId để truy cập dữ liệu trái phép | Fuzz MAC, tenant, lastId |
| Codec làm tròn timestamp | Skip ở row sát nhau | DB precision test |
| Token hết hạn nhưng fallback trang đầu | A/B/C lặp “ngẫu nhiên” | Test expired token → 400/410, không reset im lặng |
| Cursor dùng row lookahead | Bỏ một row mỗi trang | Test N+1 và cursor last emitted |
| Không version codec | Sau deploy token cũ giải mã sai | Compatibility tests/expiry/migration |

### 7.2. Cache key, đường Link và query parameter

Nếu gateway/CDN cache trang 2 theo **path mà bỏ query cursor hoặc status**, response của user khác có thể bị tái sử dụng. Điều này vừa gây duplicate/missing vừa là **rò dữ liệu xuyên tenant**. Với collection nhạy cảm, bắt đầu bằng **Cache-Control: private, no-store**; nếu dùng cache, phân tích **Authorization, Cookie, Vary, tenant scope, query và TTL**, không mặc định cache chung được.

Một số UI vô tình lấy cursor mới nhưng giữ **sort/limit cũ ở request**, hoặc nối query string sai khiến cursor bị **double URL encoding**. Header **Link rel="next"** và field **nextCursor** nếu cùng được công bố phải thống nhất route, filter, limit và token. Frontend cần thay thế/khóa chuỗi pagination khi người dùng đổi filter, không append trang cũ vào danh sách mới.

### 7.3. Read replica lag và consistency window

Trang 1 có thể đọc primary sau commit, trang 2 đọc một replica chưa bắt kịp (hoặc ngược lại). Cùng cursor nhưng dữ liệu nhìn thấy ở hai replica khác nhau, làm chẩn đoán nhầm thành lỗi SQL:

~~~text
T1: Primary committed order X.
T2: GET page1 trên primary -> thấy X.
T3: GET page2 trên replica lag -> snapshot cũ hơn.
T4: Replica bắt kịp; GET lại page2 -> dữ liệu khác.
~~~

Nếu contract đòi **monotonic read/read-your-writes**, cần route primary trong phiên nhạy cảm hoặc dùng consistency watermark/LSN token và chờ replica đạt mốc; **không dùng sleep(500ms)** để “đợi chắc đồng bộ”. Điều này vẫn **không tự tạo snapshot** khi các writer tiếp tục thay dữ liệu. Đo replica lag, cache HIT/MISS và deployment version trong tracing để đối chiếu.

### 7.4. HTTP status khi cursor lỗi hoặc snapshot hết hạn

~~~http
GET /v1/orders?status=OPEN&limit=20&cursor=corrupted HTTP/1.1
Host: api.example.test
Authorization: Bearer <redacted>
~~~

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-cursor",
  "title": "Invalid pagination cursor",
  "status": 400,
  "code": "INVALID_CURSOR"
}
~~~

Đối với **snapshot có TTL và đã bị xóa**, API có thể trả **410 Gone** với mã **SNAPSHOT_EXPIRED** theo contract, hướng dẫn client bắt đầu truy vấn mới. Một cursor hỏng không được coi là trang đầu và trả 200, vì hành vi đó vừa lặp item vừa che lỗi tampering. **401/403/404** dành cho xác thực/quyền, không được chuyển thành 400 chỉ vì cursor cùng lúc sai; thứ tự kiểm tra phải bảo đảm không làm lộ dữ liệu tenant khác. Lỗi DB/proxy phải là 5xx phù hợp, không trả **200 + items=[]**.

## 8. Bản sửa mẫu: PostgreSQL keyset + Java/Spring MVC

Giả sử product chốt hợp đồng **live feed của các order OPEN trong một tenant**. Order được tạo với created_at **bất biến** và UUID id unique. Client chỉ duyệt theo **created_at DESC, id DESC**, không có yêu cầu nhảy thẳng đến page N. Lựa chọn này xử lý **OFFSET drift** và tie timestamp, nhưng không biến status OPEN thành snapshot cố định.

### 8.1. Schema/index cho đúng truy vấn

~~~sql
CREATE TABLE orders (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    status varchar(24) NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX ix_orders_tenant_owner_status_created_id
  ON orders (tenant_id, owner_id, status, created_at DESC, id DESC);
~~~

Đây là DDL **minh họa cho schema migration**, không chạy mỗi HTTP request. Nếu quyền của API cho phép một admin xem toàn tenant, query và index cho admin phải khác với query theo owner của user thường; **không tùy tiện bỏ owner_id** để làm pagination nhanh hơn. Database cần dữ liệu test có trùng timestamp, nhiều tenant và status khác nhau để kiểm chứng index/filter.

### 8.2. Cursor contract và query service

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

record Actor(UUID tenantId, UUID userId) {}
record OrderItem(UUID id, Instant createdAt, String status) {}
record OrderPage(List<OrderItem> items, String nextCursor,
                 boolean hasMore) {}
record PageCursor(UUID tenantId, UUID userId, String status,
                  int limit, Instant lastTime, UUID lastId,
                  Instant expiresAt) {}

interface SignedCursorCodec {
    // Verify HMAC/AEAD, expiry, tenant/user, filter, limit and version.
    PageCursor decode(String token, Actor actor, String status, int limit);
    String encode(PageCursor cursor);
}

@Service
class OrderPaginationService {
    private final NamedParameterJdbcTemplate jdbc;
    private final SignedCursorCodec cursors;
    private final Clock clock;

    OrderPaginationService(NamedParameterJdbcTemplate jdbc,
                           SignedCursorCodec cursors, Clock clock) {
        this.jdbc = jdbc;
        this.cursors = cursors;
        this.clock = clock;
    }

    OrderPage list(Actor actor, String status, int limit, String token) {
        if (limit < 1 || limit > 100
                || !("OPEN".equals(status) || "CLOSED".equals(status))) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid pagination params");
        }
        if (token != null && token.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Empty cursor");
        }

        PageCursor after = token == null ? null
                : cursors.decode(token, actor, status, limit);
        var args = new MapSqlParameterSource()
                .addValue("tenant", actor.tenantId())
                .addValue("owner", actor.userId())
                .addValue("status", status)
                .addValue("limitPlusOne", limit + 1);
        String query = """
                SELECT id, created_at, status
                  FROM orders
                 WHERE tenant_id = :tenant
                   AND owner_id = :owner
                   AND status = :status
                """;
        if (after != null) {
            query += """
                   AND (created_at, id) < (:lastTime, :lastId)
                """;
            args.addValue("lastTime",
                         OffsetDateTime.ofInstant(
                             after.lastTime(), ZoneOffset.UTC))
                .addValue("lastId", after.lastId());
        }
        query += """
                 ORDER BY created_at DESC, id DESC
                 LIMIT :limitPlusOne
                """;

        List<OrderItem> rows = jdbc.query(query, args,
            (rs, rowNum) -> new OrderItem(
                rs.getObject("id", UUID.class),
                rs.getObject("created_at",
                             OffsetDateTime.class).toInstant(),
                rs.getString("status")));

        boolean hasMore = rows.size() > limit;
        List<OrderItem> items = List.copyOf(
            rows.subList(0, Math.min(limit, rows.size())));
        String next = null;
        if (hasMore) {
            OrderItem last = items.get(items.size() - 1);
            next = cursors.encode(new PageCursor(
                actor.tenantId(), actor.userId(), status, limit,
                last.createdAt(), last.id(),
                clock.instant().plus(Duration.ofMinutes(10))));
        }
        return new OrderPage(items, next, hasMore);
    }
}
~~~

Điểm sửa then chốt:

- **WHERE tenant_id và owner_id** được áp ngay trong SQL, không lọc quyền sau LIMIT. Nếu phải dùng policy phức tạp, đưa điều kiện vào query/RLS hoặc truy vấn có tính đến nó trước khi xác định ranh giới trang.
- **ORDER BY và cursor comparator** nhất quán; **id** phá ties của created_at. Cursor lấy từ **row cuối được trả**, không lấy lookahead.
- **Timestamp lấy trực tiếp từ DB**, chuyển đổi qua Instant/OffsetDateTime mà không làm tròn từ JSON response.
- **SignedCursorCodec** là interface cần implementation có **HMAC/AEAD, version, TTL, strict parsing, scope binding**; không phải placeholder được phép trả dữ liệu khi token invalid.
- Các điều kiện SQL được chọn từ đoạn constant; **không nối trực tiếp token hoặc sort expression do client khai**. Chọn sort từ allowlist.

Nếu **hasMore=false**, JSON serializer có thể phát nextCursor=null và HTTP không có Link next. Trường hợp bằng đúng limit item nhưng không còn row thứ limit+1 vẫn là trang cuối. Dùng phép chia truy vấn trên database production-compatible để test PostgreSQL uuid ordering và timestamp precision; một mock list sắp trong JVM chưa đủ.

### 8.3. Controller giữ hợp đồng HTTP nhất quán

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.util.UriComponentsBuilder;

interface VerifiedActorResolver {
    // tenant/owner từ JWT đã xác minh và membership được phép.
    Actor resolve(Jwt jwt);
}

@RestController
class OrderPaginationController {
    private final OrderPaginationService pages;
    private final VerifiedActorResolver actors;

    OrderPaginationController(OrderPaginationService pages,
                              VerifiedActorResolver actors) {
        this.pages = pages;
        this.actors = actors;
    }

    @GetMapping(value = "/v1/orders",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderPage> list(
        @AuthenticationPrincipal Jwt jwt,
        @RequestParam(defaultValue = "OPEN") String status,
        @RequestParam(defaultValue = "20") int limit,
        @RequestParam(required = false) String cursor) {
        Actor actor = actors.resolve(jwt);
        OrderPage result = pages.list(actor, status, limit, cursor);
        var response = ResponseEntity.ok()
            .cacheControl(CacheControl.noStore());
        if (result.nextCursor() != null) {
            String next = UriComponentsBuilder.fromPath("/v1/orders")
                .queryParam("status", status)
                .queryParam("limit", limit)
                .queryParam("cursor", result.nextCursor())
                .build().encode().toUriString();
            response.header(HttpHeaders.LINK,
                            "<" + next + ">; rel=\"next\"");
        }
        return response.body(result);
    }
}
~~~

Backend cần được cấu hình **OAuth2 Resource Server** với signature/issuer/audience/lifetime và scope thích hợp; controller này giả định JWT đã qua security filter. **Route-level scope không thay truy vấn theo tenant/owner**. Relative Link tránh dùng absolute Host do header X-Forwarded-Host có thể bị giả nếu ingress không kiểm soát. Kiểm thử thêm proxy prefix và URL encoding nếu public route không phải /v1/orders.

### 8.4. Không sửa sai bằng client-side deduping đơn độc

Frontend có thể dùng Map/Set keyed by ID để **không hiển thị duplicate**, nhưng không khôi phục item bị skip. Nếu dữ liệu bị đổi sort hoặc mất snapshot, “lọc C khỏi trang 2” sẽ làm trang chỉ còn hai item và có thể bỏ qua D mãi mãi. Dedupe UI là **biện pháp phòng vệ trải nghiệm**, không phải bằng chứng SQL contract đúng. Khi sort/filter đổi, client phải **reset list + cursor + pending requests**, bỏ response cũ đến muộn và giữ một logical page chain nhất quán.

## 9. Kiểm thử hồi quy: từ SQL tới HTTP qua hai trang

Một test gọi GET trang 1 và GET trang 2 **không có writer** chỉ chứng minh thuật toán trên dữ liệu tĩnh. Với bug thực tế, phải **commit mutation xen giữa hai HTTP requests**, và dùng DB/driver gần production để tái hiện timestamp, isolation và tuple comparison.

| Test case | Thiết lập | Kỳ vọng đúng |
|---|---|---|
| 0, 1, N−1, N, N+1 items | Page size N | Không next khi hết, next khi thực sự còn |
| Timestamp bằng nhau | 3 item cùng created_at | Không lặp/thiếu, id phá ties |
| Insert ở đầu sau page 1 | Commit X có key lớn hơn cursor | Page 2 không lặp item đã phát |
| Delete item đã phát | Commit DELETE B sau page 1 | Không dịch ranh giới cursor; tiếp tục row phía sau |
| Insert phía sau cursor | Backfill X có key nhỏ hơn | X có thể xuất hiện trong live feed; không gọi là snapshot |
| Update sort key qua cursor | Đổi score A giảm và D tăng | Test minh họa giới hạn của live keyset, không assert snapshot |
| Update status | OPEN → CLOSED phía sau cursor | Không còn item bị loại khỏi filter |
| Cursor làm tròn microsecond | Hai row lệch vài microsecond | Query dùng đúng khóa DB, không skip |
| Cursor của tenant B | Token/actor thuộc tenant A | 400/403 theo contract, tuyệt đối không leak B |
| Limit/sort/filter bị thay | Reuse cursor cũ | 400, không silently reset trang đầu |
| Cursor bị sửa/hết hạn | MAC invalid, TTL cũ | 400 hoặc 410 theo contract, không full scan |
| Replica lag/cache collision | Route qua replica cũ/cache sai key | Test consistency policy hoặc cấu hình no-store |
| Client đổi filter khi request cũ còn chạy | Out-of-order HTTP responses | UI bỏ trang cũ, không append vào chuỗi mới |

### 9.1. Integration test mẫu với MockMvc

Đoạn JUnit sau là **test skeleton**: cần triển khai fixture ghi PostgreSQL và actor/JWT test tương ứng. Dữ liệu A/B/C/D được seed với **created_at khác nhau, tất cả nhỏ hơn thời điểm insert X**, tenant/owner đúng.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPaginationIncidentIT {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;

    @Test
    void insertBeforeCursorDoesNotRepeatOrSkipOldRows()
            throws Exception {
        UUID tenant = UUID.randomUUID();
        UUID owner = UUID.randomUUID();
        List<UUID> oldIds = seedFourOpenOrdersInDescendingOrder(
                tenant, owner); // fixture COMMIT; A,B,C,D.

        var first = mvc.perform(get("/v1/orders")
                .with(jwt().jwt(t -> t.subject(owner.toString())
                    .claim("tenant_id", tenant.toString()))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")))
                .param("status", "OPEN")
                .param("limit", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andExpect(jsonPath("$.hasMore").value(true))
            .andReturn();
        JsonNode page1 = json.readTree(
            first.getResponse().getContentAsString());
        assertEquals(oldIds.get(0).toString(),
            page1.path("items").get(0).path("id").asText());
        String token = page1.path("nextCursor").asText();

        insertCommittedOpenOrder(tenant, owner,
            Instant.parse("2026-11-18T12:00:00Z"));

        var second = mvc.perform(get("/v1/orders")
                .with(jwt().jwt(t -> t.subject(owner.toString())
                    .claim("tenant_id", tenant.toString()))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")))
                .param("status", "OPEN")
                .param("limit", "2")
                .param("cursor", token))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.hasMore").value(false))
            .andReturn();
        JsonNode page2 = json.readTree(
            second.getResponse().getContentAsString());
        assertEquals(oldIds.get(2).toString(),
            page2.path("items").get(0).path("id").asText());
        assertEquals(oldIds.get(3).toString(),
            page2.path("items").get(1).path("id").asText());
        assertTrue(page2.path("nextCursor").isNull());
    }
}
~~~

**Giới hạn:** fixture methods là pseudocode, cần test database đã migration/seed, implementation SignedCursorCodec, Clock, JWT claim mapping và SecurityFilterChain tương ứng. **jwt() mock authentication**, không kiểm tra chữ ký/issuer/audience thực; thêm integration test với JWKS/token test để xác minh boundary. Không bọc cả test trong một outer **@Transactional** khiến các transaction HTTP/fixture vô tình không thấy dữ liệu đã commit.

### 9.2. Test điều kiện cạnh tranh có kiểm soát

~~~text
Client thread: GET page 1 -> lưu nextCursor -> signal page1Done.
Writer thread: wait page1Done -> INSERT/DELETE/UPDATE -> COMMIT.
Writer thread: signal mutationCommitted.
Client thread: wait mutationCommitted -> GET page 2 -> assert IDs.
~~~

Dùng **CountDownLatch/CyclicBarrier** hoặc orchestration bằng futures, đảm bảo writer dùng **transaction/connection riêng**. Không dùng Thread.sleep(500) để giả định commit xong. Với snapshot, assert **set equality và representation version** như mốc chụp. Với live keyset, assert **monotonic key boundary và không lặp do insert ở đầu**, không đòi đủ mọi item từng tồn tại khi đã bị xóa/đổi sort.

### 9.3. Property-based và fault injection

Sinh danh sách random có nhiều timestamp trùng, status/tenant xen kẽ, các thao tác insert/delete/update và page size từ 1 tới max. Ghi random seed, commit order và cursor boundary khi test fail để tái hiện. Những thuộc tính đúng khi **không có mutation**: duyệt hết sẽ ra đúng ID theo total order, không trùng, không skip, next luôn tiến về phía khóa nhỏ hơn và kết thúc. **Khi có mutation**, oracle phải mô phỏng dữ liệu nhìn thấy tại từng SELECT, không lấy snapshot ban đầu làm chuẩn cho live feed.

Đối với replica/cache, inject **lag có kiểm soát, cache stale hoặc CDN bỏ query param**, kiểm tra response vẫn đúng isolation hoặc ứng dụng cấu hình **no-store/routing primary** theo contract. Test outage trả 5xx phù hợp chứ không trả danh sách rỗng giả. Với gateway, đo **query parameters có được preserve và URL encoded đúng** khi client theo Link rel=next.

## 10. Runbook giảm tác động khi bug đang xảy ra

| Bước | Hành động an toàn | Điều cần tránh |
|---|---|---|
| **1. Phân loại impact** | Tách UI duplicate với API skip, tính route/tenant/bản deploy ảnh hưởng | Suy đoán mọi 404/duplicate cùng nguyên nhân |
| **2. Ghi chứng cứ** | Request ID, hai page, cursor hash, SQL shape, thời điểm commit, replica/cache | Log raw JWT/cursor chứa PII hoặc cả payload |
| **3. Kiểm tra deployment** | Diff sort/query/cursor version, feature flag, migration, query plan | Rollback khi schema/token format không tương thích |
| **4. Chặn rủi ro dữ liệu** | Với export chính xác, tạm dùng snapshot job/primary hoặc giới hạn chức năng | Tiếp tục xuất thiếu dòng rồi tuyên bố thành công |
| **5. Giảm trải nghiệm xấu** | Cho refresh/restart cursor chain, cảnh báo dữ liệu đang live | Lọc trùng ở UI rồi coi đã hết skip |
| **6. Sửa và kiểm thử** | Regression tests cho offset drift, tie, limit+1, tenant, cache/replica | Chỉ test dữ liệu tĩnh hoặc chỉ unit mock |
| **7. Xác nhận phục hồi** | So ID với nguồn đúng theo contract, đo duplicate/skip, kiểm tra 4xx/5xx | Chỉ xem RPS/CPU rồi đóng incident |

Nếu báo cáo tải xuống đã được tạo **không đầy đủ** và có ảnh hưởng nghiệp vụ, đánh dấu output bị tác động, **đối soát lại từ nguồn dữ liệu** và cân nhắc phát hành lại theo cơ chế idempotent. Không “bổ sung thiếu” bằng cách gửi lại toàn bộ POST export với key mới khi có thể tạo nhiều job/charge. Với feed live, có thể khuyến nghị người dùng **refresh từ đầu** sau khi bản sửa triển khai; với snapshot export, cần **phiên bản ảnh chụp có khả năng tái lập**.

Quan sát vận hành nên đo **page request rate, p95/p99 latency, deep-page query time, rows scanned, cursor invalid/expired, cache HIT/MISS, replica lag, số user refresh**, và nếu có hỗ trợ đối soát, **duplicate/skipped IDs** theo tập test. Metric không được chứa raw cursor, orderId, JWT, URL có token hoặc userId làm label. Dùng trace/sample logs có truy cập giới hạn; đừng xây hệ thống logging theo dõi mỗi row của mọi khách hàng chỉ để phát hiện lỗi.

## 11. Bài tập chẩn đoán: feed đơn hàng và báo cáo doanh thu

Một Orders API có bốn Spring Boot replicas, PostgreSQL primary với hai read replicas, Redis cache và gateway. Endpoint **GET /v1/orders?status=OPEN&limit=3** đang dùng OFFSET, sắp theo **updated_at DESC** mà nhiều row có cùng timestamp. Một khách hàng báo **B lặp** trong feed; một đối tác tải toàn bộ đơn để đối soát thấy **D bị mất**. Trong lúc duyệt, nhân viên thường chuyển order từ OPEN sang CLOSED và worker có thể backfill dữ liệu.

Hãy thực hiện theo thứ tự:

1. Viết **hai request/response HTTP** có đủ filter, limit, cursor/offset và ID; tái hiện duplicate bằng INSERT và skip bằng DELETE/đổi status.
2. Chỉ ra vì sao **ORDER BY updated_at DESC** không đủ ổn định; bổ sung tie-breaker và giải thích tại sao sửa này **chưa xử lý OFFSET drift**.
3. Viết SQL **created_at DESC, id DESC** dùng keyset cho feed live, thêm tenant/owner filter và logic **limit+1**; test row trùng timestamp.
4. Dự đoán kết quả khi A đổi updated_at từ mới thành cũ sau page 1 hoặc D chuyển CLOSED; tại sao keyset cũng có thể lặp/skip nếu sort key/filter biến động?
5. Thiết kế **snapshot-backed export** trả đúng tập order tại thời điểm yêu cầu, gồm snapshot ID, TTL, URI job, representation/version và trường hợp row bị xóa.
6. Thử cursor tenant A với JWT tenant B, đổi status khi reuse cursor, làm hỏng MAC; xác định mã HTTP và bảo vệ không rò dữ liệu.
7. Kiểm tra **Redis cache key** và đường truy cập primary/replica; đề xuất một chiến lược read consistency và bộ metric để phân biệt lag với SQL lỗi.
8. Xây tối thiểu **tám test tự động**, trong đó có writer commit giữa hai GET, timestamp microsecond, N+1 lookahead, hết cursor và gateway Link encoding.
9. Viết **runbook một trang** cho đội trực: impact, bằng chứng, rollback guard, giảm rủi ro báo cáo không đầy đủ và tiêu chí đóng sự cố.

**Gợi ý:** feed dùng keyset với sort key bất biến và chính sách refresh; export cần snapshot **có khả năng tái lập**. Đừng lấy MAX(id) làm commit watermark nếu database cấp sequence trước COMMIT. Nếu snapshot chỉ lưu ID mà row bị xóa/đổi nội dung, API phải có policy hoặc versioned representation để giữ đúng lời hứa. Không bỏ tenant filter hay sửa 404 thành 200 để “làm sạch” thống kê. Client-side dedupe chỉ che duplicate, **không bù được dữ liệu bị skip**.

## 12. Checklist sau khi khắc phục và tài liệu tham khảo

- [ ] Đã tách **live feed** và **snapshot/export** thành hai hợp đồng rõ ràng.
- [ ] Có bằng chứng hai HTTP requests, cùng tenant/filter/sort/limit và timeline COMMIT.
- [ ] **ORDER BY** tạo total order, với tie-breaker unique, nullable/collation được định nghĩa.
- [ ] Không tuyên bố OFFSET ổn định xuyên request khi có insert/delete.
- [ ] Keyset predicate khớp chiều sort; dùng **cặp khóa đầy đủ**, đúng precision timestamp.
- [ ] **nextCursor lấy từ row cuối đã trả**, không phải lookahead; no next ở trang cuối.
- [ ] Dùng tenant/owner filter **trước LIMIT**, authz ở mọi request; cursor có MAC, expiry, version và binding.
- [ ] Có policy cho update sort/filter, replica lag, cache key, query encoding và đổi filter ở frontend.
- [ ] Test với PostgreSQL thật/production-compatible, writer transaction riêng, boundary N/N+1 và mutation có barrier.
- [ ] Có runbook, rollback có điều kiện, phương án đối soát lại export bị thiếu và telemetry an toàn.

Tham khảo: **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 8288 Web Linking**, https://www.rfc-editor.org/rfc/rfc8288.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **PostgreSQL SELECT/ORDER BY/LIMIT/OFFSET**, https://www.postgresql.org/docs/current/sql-select.html; **PostgreSQL Transaction Isolation**, https://www.postgresql.org/docs/current/transaction-iso.html; **Spring Data JDBC**, https://docs.spring.io/spring-framework/reference/data-access/jdbc.html; **Spring MVC Testing (MockMvc)**, https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html; **Testcontainers PostgreSQL**, https://java.testcontainers.org/modules/databases/postgres/.

**Kết luận:** Bỏ sót/lặp phần tử không có một nguyên nhân duy nhất. Hãy bắt đầu từ **hợp đồng dữ liệu tại từng thời điểm**, tái hiện bằng **request và transaction đã commit**, rồi phân biệt **OFFSET drift, thứ tự không toàn phần, cursor boundary, thay đổi sort/filter và replica/cache**. Chọn **keyset cho feed phù hợp**, **snapshot cho dữ liệu phải tái lập**, giữ phân quyền theo tenant và xác nhận bằng kiểm thử hồi quy thay vì chỉ che triệu chứng trên giao diện.
