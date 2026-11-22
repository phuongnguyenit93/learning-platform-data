# Kiểm thử phân trang ổn định với dữ liệu thay đổi

Một ứng dụng gọi **GET /v1/orders?limit=3**, nhận ba đơn mới nhất rồi dùng liên kết trang kế tiếp. Trong lúc người dùng cuộn danh sách, một đơn mới được tạo, một đơn cũ bị xóa và trạng thái đơn khác thay đổi. Kết quả: cùng một đơn xuất hiện ở hai trang, một đơn bị bỏ sót hoặc client thấy tổng số bản ghi không khớp. Unit test với dữ liệu đứng yên vẫn xanh; lỗi chỉ lộ ra khi **tập dữ liệu thay đổi giữa hai HTTP request**.

Bài thuộc chương **Kiểm thử** của module **INTEGRATION_API_REST**: thiết kế REST API theo resource, URI, HTTP status và hợp đồng dữ liệu, thực hành phân trang, cache, idempotency, phân quyền và kiểm thử bằng Java/Spring hoặc công nghệ tương đương. Ta sẽ xác định **loại ổn định mà API hứa**, chọn cơ chế phân trang phù hợp, rồi kiểm chứng nó bằng HTTP integration test, database thật và thao tác ghi xen kẽ.

## 1. Kết quả học tập và định nghĩa “ổn định”

Sau bài này, bạn có thể:

1. Tái hiện **duplicate** và **missing item** của OFFSET/LIMIT khi có insert/delete ở vùng đã đọc.
2. Thiết kế **total ordering** có tie-breaker và **keyset/cursor pagination** cho thứ tự nhiều cột.
3. Phân biệt **phân trang deterministic**, **duyệt dữ liệu đang sống (live)** và **snapshot nhất quán xuyên nhiều request**.
4. Kiểm chứng hành vi khi **sort key/filter membership thay đổi**, bản ghi bị xóa và read replica/cache chậm.
5. Kiểm tra hợp đồng **nextCursor, Link, page size, status lỗi, expiry, binding với tenant/filters**.
6. Viết test **MockMvc + PostgreSQL/Testcontainers**, test cạnh tranh có barrier và kiểm thử thuộc tính (property-based).
7. Xác định invariant đủ mạnh để không tuyên bố sai rằng “cursor luôn bảo đảm không thiếu/không trùng” trong mọi trường hợp.

Trong bài này, có ba mức yêu cầu khác nhau:

| Mức bảo đảm | Ý nghĩa | Cơ chế thường dùng |
|---|---|---|
| **Sắp xếp xác định** | Cùng tập dữ liệu tại một thời điểm cho thứ tự nhất quán, không phụ thuộc tie ngẫu nhiên | **ORDER BY** đầy đủ, có khóa duy nhất |
| **Duyệt live ổn định tương đối** | Các trang tiếp nối theo một ranh giới khóa; insert ở đầu danh sách không làm dịch offset | **Keyset/cursor** với sort key bất biến |
| **Snapshot consistency** | Duyệt chính xác tập bản ghi đủ điều kiện tại một mốc logic, kể cả khi dữ liệu về sau thay đổi | **Materialized snapshot**, versioned/temporal read hoặc cơ chế snapshot xuyên request |

**Keyset tự nó không hứa snapshot**. Khi bản ghi bị xóa, không thể yêu cầu trang tiếp theo vẫn trả nguyên dữ liệu đã mất nếu không có bản sao lịch sử. Khi bản ghi đổi sort key hoặc đổi status, nó có thể chuyển qua ranh giới cursor. Vì vậy test phải xuất phát từ **hợp đồng sản phẩm**, không chỉ assert số phần tử mỗi trang.

### 1.1. Mẫu hợp đồng cần thống nhất trước khi viết test

Ví dụ API quản lý đơn hàng của một tenant, sắp xếp **createdAt DESC, id DESC**:

~~~http
GET /v1/orders?status=OPEN&limit=3 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
Link: </v1/orders?status=OPEN&limit=3&cursor=opaque-signed-token>; rel="next"

{
  "items": [
    {"id":"00000000-0000-0000-0000-000000000105","createdAt":"2026-11-18T09:05:00Z","status":"OPEN"},
    {"id":"00000000-0000-0000-0000-000000000104","createdAt":"2026-11-18T09:04:00Z","status":"OPEN"},
    {"id":"00000000-0000-0000-0000-000000000103","createdAt":"2026-11-18T09:03:00Z","status":"OPEN"}
  ],
  "nextCursor":"opaque-signed-token",
  "hasMore":true
}
~~~

Từ góc nhìn client, **nextCursor là opaque**: client gửi lại nguyên trạng, không tự parse hoặc tạo cursor mới. Header **Link** và JSON **nextCursor** phải chỉ cùng một bước kế tiếp, nếu API công bố cả hai. Response có thể không cung cấp **totalElements** vì tổng live có thể thay đổi giữa các request.

## 2. Chứng minh OFFSET/LIMIT có thể bỏ sót hoặc lặp

Ban đầu có sáu đơn theo thứ tự giảm dần:

| Thứ tự | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| ID | A | B | C | D | E | F |

Client lấy trang 1 với **LIMIT 3 OFFSET 0**, nhận **A, B, C**. Trước trang 2, một đơn **X** mới được chèn lên đầu:

| Thứ tự mới | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| ID | X | A | B | C | D | E | F |

Trang 2 dùng **LIMIT 3 OFFSET 3** sẽ nhận **C, D, E**. **C lặp lại**, F lùi sang trang sau. Nếu thay vào đó **B bị xóa** trước trang 2, thứ tự trở thành **A, C, D, E, F**; OFFSET 3 trả **E, F**, và **D bị bỏ sót** mặc dù vẫn còn trong dữ liệu.

~~~sql
SELECT id, created_at
  FROM orders
 WHERE tenant_id = :tenant
 ORDER BY created_at DESC, id DESC
 LIMIT 3 OFFSET 3;
~~~

**ORDER BY đầy đủ vẫn không sửa được dịch chuyển vị trí do insert/delete**. Chỉ sửa lỗi không có tie-breaker; nó không cố định offset giữa các phiên bản của danh sách. Offset có ưu điểm hỗ trợ nhảy đến trang N và dễ diễn đạt, nên vẫn phù hợp với danh sách nhỏ, dữ liệu ít đổi hoặc UX chấp nhận sự thay đổi. Nhưng test phải phản ánh đúng giới hạn đó, không giả định snapshot.

### 2.1. Thiếu ORDER BY hoặc tie-breaker cũng gây lỗi khi dữ liệu đứng yên

~~~sql
-- Không đủ: nhiều đơn có cùng thời điểm tạo.
SELECT id FROM orders
 WHERE tenant_id = :tenant
 ORDER BY created_at DESC
 LIMIT :limit OFFSET :offset;

-- Tốt hơn: tie-breaker unique và ổn định.
SELECT id FROM orders
 WHERE tenant_id = :tenant
 ORDER BY created_at DESC, id DESC
 LIMIT :limit OFFSET :offset;
~~~

Nếu hai row có **created_at** bằng nhau, DB có quyền trả chúng theo thứ tự khác giữa hai lần chạy khi không có tie-breaker. Chọn **id** nếu unique và có phép so sánh nhất quán trong database, không giả định UUID phản ánh thời gian tạo. Nếu dùng **score**, **priority** hoặc trường nullable, phải định nghĩa tiếp tie-breaker, **NULLS FIRST/LAST**, collation/case folding theo DB và kết quả expected trong test.

### 2.2. Test tối thiểu tái hiện offset drift

~~~text
Given: seed A,B,C,D,E,F, page size=3, thứ tự mới nhất trước.
When:  GET page 1 -> [A,B,C].
And:   transaction khác commit X ở đầu.
And:   GET page 2 với OFFSET 3 -> [C,D,E].
Then:  assert C bị trùng, chứng minh hợp đồng snapshot không được đáp ứng.

Given: reset seed A,B,C,D,E,F.
When:  GET page 1 -> [A,B,C].
And:   transaction khác DELETE B đã commit.
And:   GET page 2 OFFSET 3 -> [E,F].
Then:  assert D bị bỏ sót.
~~~

Đây là **negative/regression demonstration**, không phải một test kỳ vọng offset “luôn đúng”. Nếu quyết định tiếp tục dùng offset, test có thể ghi nhận hành vi hợp đồng được chấp nhận hoặc yêu cầu client dedupe/refresh; không che hiện tượng bằng cách kiểm tra mỗi trang có kích thước tối đa ba.

## 3. Keyset/cursor: ranh giới theo giá trị, không theo số dòng

Với thứ tự **created_at DESC, id DESC**, cursor sau trang 1 ghi **khóa của phần tử cuối đã trả**, chẳng hạn **(2026-11-18T09:03:00Z, o-103)**. Trang sau lấy các row có cặp khóa **nhỏ hơn** cặp này:

~~~sql
SELECT id, created_at, status
  FROM orders
 WHERE tenant_id = :tenant_id
   AND status = :status
   AND (created_at, id) < (:last_created_at, :last_id)
 ORDER BY created_at DESC, id DESC
 LIMIT :page_size_plus_one;
~~~

Cú pháp row-value comparison ở đây phù hợp với **PostgreSQL** và các cột **NOT NULL** có thứ tự so sánh được. Với database khác, chuyển thành điều kiện tương đương:

~~~sql
AND (created_at < :last_created_at
     OR (created_at = :last_created_at AND id < :last_id))
~~~

**Lấy limit + 1**, chỉ trả tối đa limit item và dùng dòng dư để xác định có trang kế tiếp. **nextCursor phải tạo từ phần tử cuối thật sự trả về**, không phải từ dòng “lookahead” thứ limit+1; nếu dùng lookahead làm ranh giới, client sẽ bỏ qua dòng đó. Trang cuối trả **nextCursor=null, hasMore=false**, không tiếp tục phát một token vô nghĩa.

### 3.1. Vì sao keyset không lặp khi có insert ở đầu?

Giả sử trang 1 nhận A, B, C; cursor ở C. Một row mới X có khóa lớn hơn A được chèn lên đầu. Trang sau vẫn dùng **khóa < C**, nên lấy D, E, F; **C không bị lặp** do thay đổi offset. Đây là bảo đảm hữu ích của keyset khi:

- **Sort key** không thay đổi sau khi row được tạo;
- Mọi trang dùng **cùng filter và chiều sắp xếp**;
- Mọi khóa tie-breaker là unique, có thứ tự toàn phần;
- Phạm vi đọc nhất quán với policy và row không bị xóa/ẩn giữa các trang.

Nếu mới chèn X vào đầu **sau trang 1**, X **không xuất hiện** trong chuỗi đang tiếp tục. Điều đó hợp lý với giao diện infinite scroll live: người dùng có thể **refresh từ đầu** để nhận dữ liệu mới. Không nên vừa đòi “không bao giờ thêm row mới” vừa dùng một live keyset không có snapshot contract.

### 3.2. Cùng timestamp phải kiểm tra cả khóa phụ

Cho các row:

| created_at | id | Thứ tự DESC |
|---|---|---|
| 09:03:00Z | c3 | 1 |
| 09:03:00Z | c2 | 2 |
| 09:03:00Z | c1 | 3 |
| 09:02:00Z | b9 | 4 |

Với page size 2, trang 1 trả **c3, c2**, cursor **(09:03, c2)**. Trang 2 phải trả **c1, b9**. Nếu cursor chỉ lưu timestamp và query **created_at < 09:03**, **c1 bị bỏ sót**. Nếu dùng điều kiện **<= timestamp**, c3/c2 có thể lặp. Test tie timestamp là **ca bắt buộc**, không phải dữ liệu cạnh ít gặp: batch import và hệ DB có độ phân giải thời gian hữu hạn tạo tie thường xuyên.

### 3.3. Keyset có giới hạn quan trọng khi dữ liệu thay đổi

Tạo dữ liệu theo sort key DESC: A=100, B=90, C=80, D=70, E=60. Client nhận trang đầu **A,B**; cursor là **90**.

| Biến động giữa các trang | Hệ quả với keyset live |
|---|---|
| Chèn X=110 (trước cursor) | X không được phát trong chuỗi cũ; không làm lặp B |
| Chèn X=65 (sau cursor) | X **có thể được phát** dù không có lúc trang 1 |
| Xóa D trước khi được đọc | D không xuất hiện, không thể bảo đảm đủ tập ban đầu |
| Đổi A từ 100 xuống 50 | A có thể xuất hiện **lần nữa** ở trang sau |
| Đổi D từ 70 lên 95 | D có thể **bị bỏ sót** vì nhảy qua ranh giới |
| Đổi status của C sang CLOSED | C biến mất khỏi filter OPEN ở trang sau |

**Keyset không sửa được thay đổi thứ tự do update**. Với **created_at bất biến**, vẫn phải xét thay đổi filter như **status=OPEN**, xóa mềm, phân quyền hoặc visibility. Một test “không trùng/không thiếu trong mọi mutation” sẽ sai nếu API chỉ hứa duyệt live, không snapshot.

## 4. Live pagination, snapshot và watermark: chọn lời hứa đúng

Hợp đồng **live keyset** có thể nói: “Mỗi trang là những row hiện đủ điều kiện ở thời điểm truy vấn, đứng sau khóa cuối đã trả; item mới nằm trước cursor sẽ cần refresh để thấy”. Hợp đồng này hữu ích cho feed/timeline và thường không cần khóa transaction qua nhiều request.

Hợp đồng **snapshot** mạnh hơn: “Client duyệt đúng tập item đủ điều kiện tại một mốc logic; không thiếu và không lặp kể cả khi dữ liệu live sau đó đổi”. Nếu tài nguyên có thể bị xóa hoặc filter thay đổi, để trả đúng **representation lúc snapshot**, backend cần lưu phiên bản lịch sử hoặc bản sao dữ liệu, không chỉ lưu các ID.

~~~mermaid
flowchart TD
    A["GET collection page 1"] --> B{"Contract?"}
    B -->|Live| C["Sort key bất biến + keyset"]
    C --> D["Tiếp tục trên dữ liệu hiện tại"]
    B -->|Snapshot| E["Tạo snapshot ID / version / as-of"]
    E --> F["Lưu membership hoặc query historical version"]
    F --> G["Cursor gắn snapshot + tenant + filter"]
    D --> H["Test thay đổi dữ liệu theo live semantics"]
    G --> I["Test đủ tập snapshot kể cả khi live đổi"]
~~~

### 4.1. Các phương án snapshot hợp lệ

| Phương án | Thực hiện | Đánh đổi/test bắt buộc |
|---|---|---|
| **Materialized ID list** | Trang 1 ghi danh sách ID đã sắp xếp vào store có TTL; các trang đọc theo vị trí trong danh sách | Bộ nhớ/storage, TTL, xử lý xóa/đổi quyền, dedupe |
| **Snapshot chứa representation** | Lưu bản JSON/version của item tại mốc chụp | Tốn storage, phù hợp báo cáo/xuất dữ liệu cần tái lập |
| **Temporal/as-of queries** | Mỗi trang truy vấn version dữ liệu tại một commit timestamp/version đáng tin | Schema lịch sử, index, retention, tính đúng commit order |
| **Export job bất đồng bộ** | POST tạo job, 202 + Location; job tạo kết quả cố định rồi phân trang tải xuống | Chi phí tạo snapshot, lifecycle, quota và timeout |
| **Transaction snapshot giữ xuyên request** | Giữ DB snapshot/transaction lâu | Thường không phù hợp REST internet: giữ connection, ảnh hưởng vacuum, timeout và scale |

**REPEATABLE READ trong một transaction** chỉ cố định snapshot trong **phạm vi transaction đó**. Mỗi HTTP GET riêng thường là một transaction mới, nên không thể gắn nhãn “snapshot stable” chỉ vì bật isolation REPEATABLE READ cho từng GET. Giữ transaction DB mở qua nhiều phút người dùng cuộn trang thường là thiết kế tốn tài nguyên và dễ lỗi.

**Materialized ID list** cố định membership/order, nhưng nếu khi trả trang 2 bạn đọc JSON hiện tại từ bảng orders, nội dung đã đổi hoặc ID đã bị xóa. Nếu contract hứa cả **giá trị ở thời điểm chụp**, phải lưu version/representation hoặc dùng temporal query. Nếu chỉ hứa “danh sách ID ban đầu” thì cần chỉ rõ cách trả item đã xóa (tombstone, skip hay 410) trong hợp đồng.

### 4.2. High-watermark có ích nhưng không tự thành snapshot

Với bảng **append-only**, sort key bất biến và cơ chế sequence phản ánh **commit/visibility order đáng tin**, có thể ghi nhận high-watermark ở trang 1, rồi giới hạn mọi trang sau bằng **sequence <= highWatermark** và keyset. Cơ chế này chặn record mới có sequence lớn hơn watermark đi vào chuỗi, kể cả khi backfill với created_at cũ.

Nhưng cần rất thận trọng: **PostgreSQL sequence/IDENTITY cấp số trước COMMIT, không phải thứ tự COMMIT**. Một transaction giữ sequence 90 nhưng commit muộn sau khi trang 1 đã lấy highWatermark=100 có thể trở nên nhìn thấy về sau dù sequence <=100. Do đó **MAX(id), MAX(created_at) hoặc MAX(sequence)** không tự cho snapshot bảo đảm chặt chẽ. Để đúng snapshot phải có **commit-order watermark được chứng minh**, materialization hoặc lịch sử dữ liệu phù hợp.

Ngay cả một upper bound hợp lệ cũng **không giải quyết delete/update** của row cũ. Tránh viết trong tài liệu rằng chỉ cần **created_at <= thời gian trang 1** là mọi trang sau chính xác: backdated insert, precision của timestamp, đồng hồ nhiều node và commit muộn có thể phá giả định.

### 4.3. Read replica, cache và pagination

Một chuỗi trang đọc qua các **read replica khác nhau** có thể nhìn thấy các thời điểm replication khác nhau. Ví dụ trang 2 ở replica lag không thấy dữ liệu mà trang 1 đã thấy ở primary; cache của trang đầu có thể cũ trong khi trang sau mới. Nếu contract yêu cầu **monotonic read/read-your-writes**, cần định tuyến phù hợp, version/LSN token hoặc chờ replica đạt mốc, không dùng **Thread.sleep(500)** để hy vọng replica đã bắt kịp.

Cache key phải gồm tenant/identity scope, filter, sort và cursor theo chính sách; không cache công khai collection riêng của user. Với danh sách thay đổi nhanh và chứa dữ liệu nhạy cảm, bắt đầu bằng **Cache-Control: private, no-store** để dễ xác định hành vi, rồi thêm cache có kiểm soát nếu thật sự cần.

## 5. Cursor là hợp đồng HTTP và dữ liệu không đáng tin

Một cursor có thể chứa:

~~~json
{
  "v": 1,
  "tenant": "00000000-0000-0000-0000-000000000017",
  "status": "OPEN",
  "limit": 20,
  "sort": "createdAt_desc_id_desc",
  "lastCreatedAt": "2026-11-18T09:03:00Z",
  "lastId": "00000000-0000-0000-0000-000000000103",
  "expiresAt": "2026-11-18T09:13:00Z"
}
~~~

JSON trên **chỉ minh họa payload trước khi ký**, không được đưa nguyên văn cho client rồi tin lại. Token bên ngoài có thể là **base64url(payload).base64url(HMAC)**, có version/kid để xoay khóa. Cursor là **input từ client**, có thể bị sửa, replay, chuyển cho người khác hoặc gửi vô hạn lần.

Các yêu cầu:

- **Toàn vẹn:** xác minh MAC/chữ ký và giới hạn kích thước trước khi parse; không tin cặp khóa do client tự chọn.
- **Binding:** ràng buộc cursor với **tenant/principal hoặc phạm vi dữ liệu**, status/filter/sort/page size, snapshot ID nếu có. Đổi filter khi đang theo cursor phải bị từ chối hoặc yêu cầu bắt đầu lại.
- **Hạn sử dụng:** token hết hạn trả lỗi ổn định; nếu snapshot đã được dọn, **410 Gone** có thể phù hợp theo contract. Cursor không có snapshot cũng nên có TTL hợp lý để giới hạn việc giữ hợp đồng/version cũ.
- **Bảo mật:** HMAC chỉ ngăn sửa, **không mã hóa payload**. Không đặt JWT, session ID, email, PII hoặc URL nội bộ vào cursor; nếu cần giữ bí mật payload, dùng opaque ID trỏ server-side state hoặc mã hóa có xác thực.
- **Phân quyền:** dù MAC đúng, mỗi request vẫn phải xác thực và kiểm tra **tenant/owner/row visibility**. HMAC không phải authorization.
- **Chống DOS:** giới hạn **limit**, độ dài cursor, số khóa query, token parsing, số request và thời gian query; sai token không được gây truy vấn full scan.

| Trường hợp | Kỳ vọng theo một hợp đồng minh họa |
|---|---|
| limit = 0, âm, quá max hoặc filter không hợp lệ | **400 Bad Request** |
| Cursor malformed, MAC sai, khác filter/sort/tenant | **400** hoặc **403** theo policy thống nhất; không tiết lộ tenant khác |
| Snapshot ID hết hạn/không còn | **410 Gone** cùng mã **SNAPSHOT_EXPIRED** |
| Chưa xác thực | **401 Unauthorized** |
| Không có quyền đọc collection/resource | **403** hoặc **404** nếu cần che |
| Không còn row sau cursor | **200**, items rỗng, hasMore=false, không có nextCursor |
| Query upstream/DB tạm không khả dụng | **503** hoặc 5xx phù hợp, **không giả là trang rỗng** |

**Cursor trống hoặc null** thường có nghĩa bắt đầu từ trang đầu; **cursor rỗng dạng chuỗi**, token thiếu thành phần hay base64 hỏng cần có policy rõ, không mặc định giải mã lỗi thành trang đầu. Header **Link rel="next"** và body nextCursor phải biến mất đồng thời ở trang cuối.

## 6. Ví dụ Java/Spring: keyset với PostgreSQL

Tình huống: **GET /v1/orders?status=OPEN&limit=20&cursor=...** đọc đơn thuộc tenant của người dùng. Hợp đồng là **live pagination**, sort theo **created_at DESC, id DESC**; **created_at và id bất biến**. Vì status có thể đổi, API chỉ hứa mỗi trang phản ánh các đơn hiện đang OPEN và nằm sau cursor, **không** hứa duyệt đủ một snapshot status OPEN ban đầu.

Ví dụ giả định **Spring Boot 3, Java 17, Spring MVC, Spring Security OAuth2 Resource Server, Spring JDBC và PostgreSQL**. Các đoạn code dùng DTO/interface có tên được chỉ rõ, có thể tích hợp vào project có migrations, JSON provider và JWT validator thực tế; đây không phải một dự án có thể chạy độc lập chỉ bằng copy/paste.

### 6.1. Schema và index phải tương ứng ORDER BY

~~~sql
CREATE TABLE orders (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    status varchar(24) NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX ix_orders_tenant_status_created_id
    ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

**Index** giúp DB truy xuất nhanh theo tenant/status và thứ tự; việc có index không tự biến hợp đồng live thành snapshot. Trường **created_at** phải được sinh theo policy nhất quán và không được update nếu dựa vào nó để bảo đảm ổn định keyset. Nếu cần sort theo **updated_at** thì phải chấp nhận rủi ro nhảy vị trí hoặc chọn snapshot/versioned data.

### 6.2. Contract DTO và cursor state

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

record VerifiedActor(UUID tenantId, UUID userId) {}
record OrderItem(UUID id, Instant createdAt, String status) {}
record OrderSlice(List<OrderItem> items, String nextCursor,
                  boolean hasMore) {}

record CursorState(
        UUID tenantId,
        String status,
        int pageSize,
        Instant lastCreatedAt,
        UUID lastId,
        Instant expiresAt) {}

interface CursorCodec {
    // Verify signature, expiry, version, tenant, filter, sort and size.
    CursorState decodeAndValidate(
            String encoded, UUID tenantId, String status, int pageSize);
    String encode(CursorState state);
}
~~~

**CursorState** gồm cặp khóa **cuối cùng đã trả**, không phải số trang. Nếu API thêm sort khác, payload/validator cần version, sort identifier và kiểm tra tương ứng. Không đưa raw access token vào cursor hoặc dùng user input làm tenantId.

### 6.3. Service truy vấn bằng keyset, lấy dư một row

~~~java
import java.sql.ResultSet;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Service
class OrderPageService {
    private final NamedParameterJdbcTemplate jdbc;
    private final CursorCodec cursors;
    private final Clock clock;

    OrderPageService(NamedParameterJdbcTemplate jdbc,
                     CursorCodec cursors, Clock clock) {
        this.jdbc = jdbc;
        this.cursors = cursors;
        this.clock = clock;
    }

    OrderSlice list(VerifiedActor actor, String status,
                    int limit, String cursorToken) {
        if (limit < 1 || limit > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid limit");
        }
        if (!("OPEN".equals(status) || "CLOSED".equals(status))) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unsupported status");
        }

        CursorState after = cursorToken == null ? null
                : cursors.decodeAndValidate(cursorToken,
                        actor.tenantId(), status, limit);

        String sql = """
                SELECT id, created_at, status
                  FROM orders
                 WHERE tenant_id = :tenant
                   AND status = :status
                """;
        var params = new MapSqlParameterSource()
                .addValue("tenant", actor.tenantId())
                .addValue("status", status)
                .addValue("fetchSize", limit + 1);
        if (after != null) {
            sql += """
                 AND (created_at, id) < (:lastTime, :lastId)
                """;
            params.addValue("lastTime",
                    OffsetDateTime.ofInstant(
                            after.lastCreatedAt(),
                            java.time.ZoneOffset.UTC))
                  .addValue("lastId", after.lastId());
        }
        sql += """
                 ORDER BY created_at DESC, id DESC
                 LIMIT :fetchSize
                """;

        List<OrderItem> fetched = jdbc.query(sql, params,
                (ResultSet rs, int index) -> new OrderItem(
                        rs.getObject("id", UUID.class),
                        rs.getObject("created_at",
                                OffsetDateTime.class).toInstant(),
                        rs.getString("status")));

        boolean hasMore = fetched.size() > limit;
        List<OrderItem> items = List.copyOf(
                fetched.subList(0, Math.min(limit, fetched.size())));
        String next = null;
        if (hasMore) {
            OrderItem last = items.get(items.size() - 1);
            next = cursors.encode(new CursorState(
                    actor.tenantId(), status, limit,
                    last.createdAt(), last.id(),
                    clock.instant().plus(Duration.ofMinutes(10))));
        }
        return new OrderSlice(items, next, hasMore);
    }
}
~~~

Tại sao có **limit+1**? Nếu client xin 20 item, ta đọc tối đa 21. Chỉ khi row 21 tồn tại thì **hasMore=true**. Cặp khóa của **row thứ 20** mới được lưu vào nextCursor; row 21 phải được trả ở trang sau. Nếu chỉ query đúng limit, trang có đúng 20 item có thể là trang cuối nhưng server không biết và phát link next thừa.

**Thời gian:** PostgreSQL lưu timestamptz với độ chính xác thực tế theo DB, nên cursor phải giữ chính xác **Instant đọc từ DB**; tránh tự làm tròn đến mili-giây rồi query lại gây duplicate/skip. OffsetDateTime được đổi về Instant UTC trong mã. Phần nối SQL chỉ thêm **đoạn SQL constant** theo trạng thái đã giải mã, không nối raw cursor/status vào câu lệnh; tất cả giá trị dữ liệu được bind parameter.

**Database dialect:** ví dụ dùng PostgreSQL row comparison trên UUID. Với DB khác, collation/null ordering khác hoặc driver không hỗ trợ tuple comparison, viết câu điều kiện OR tương đương và test trực tiếp trên engine production. Nếu lọc theo **owner_id** ngoài tenant, bắt buộc thêm vào mọi query và index phù hợp; **security filter chỉ là lớp đầu, SQL phải bảo vệ row-level visibility**.

### 6.4. Controller trả HTTP contract và Link

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.util.UriComponentsBuilder;

interface VerifiedActorResolver {
    VerifiedActor fromValidatedJwt(Jwt jwt);
}

@RestController
@RequestMapping("/v1/orders")
class OrderPageController {
    private final OrderPageService pages;
    private final VerifiedActorResolver actors;

    OrderPageController(OrderPageService pages,
                        VerifiedActorResolver actors) {
        this.pages = pages;
        this.actors = actors;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderSlice> list(
            @RequestParam(defaultValue = "OPEN") String status,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(required = false) String cursor,
            @AuthenticationPrincipal Jwt jwt) {
        VerifiedActor actor = actors.fromValidatedJwt(jwt);
        OrderSlice result = pages.list(actor, status, limit, cursor);
        var response = ResponseEntity.ok()
                .cacheControl(CacheControl.noStore());

        if (result.nextCursor() != null) {
            String nextUri = UriComponentsBuilder
                    .fromPath("/v1/orders")
                    .queryParam("status", status)
                    .queryParam("limit", limit)
                    .queryParam("cursor", result.nextCursor())
                    .build().encode().toUriString();
            response.header("Link", "<" + nextUri + ">; rel=\"next\"");
        }
        return response.body(result);
    }
}
~~~

Ví dụ dùng **relative Link URI** để không phải tin Host/X-Forwarded-Host do client khai. Nếu frontend cần absolute URI, dựng public origin từ cấu hình hoặc trusted proxy. API dùng JWT phải kiểm tra **issuer, audience, signature, lifetime, scope SCOPE_orders:read** trong Spring Security; người dùng vẫn phải được lọc tenant/owner ở truy vấn. Không dùng cursor do client đưa để thay actor đã xác thực.

**Đọc dữ liệu OPEN live:** một item chuyển CLOSED giữa hai page sẽ biến mất; đó là hành vi được phép theo contract này. Nếu sản phẩm đòi **tập OPEN chính xác tại lúc trang 1**, service trên phải được thay bằng **snapshot-backed query**, không chỉnh mỗi test để che sự khác biệt.

## 7. Thiết kế bộ kiểm thử theo mức bảo đảm

**Đơn vị kiểm thử quan trọng nhất là một chuỗi GET có hành động ghi xen giữa**, không phải hai assertion độc lập cho page 1 và page 2. Test phải kiểm tra cả **danh sách ID, thứ tự, điểm ranh giới, next link, dữ liệu thừa/thiếu** và **scope tenant**.

| Dữ liệu/tình huống | Cách tạo test | Kỳ vọng đúng với live keyset |
|---|---|---|
| 0, 1, N-1, N, N+1 item | N là page size | Không mất item; next chỉ khi thực sự còn |
| Trùng timestamp | 3+ row có cùng created_at | Tie-breaker id quyết định đúng thứ tự |
| Insert ở đầu sau trang 1 | Commit row khóa lớn hơn cursor | Không lặp row đã nhận; row mới cần refresh |
| Insert ở phía sau cursor | Backfill row khóa nhỏ hơn cursor | Có thể xuất hiện ở các trang sau theo live semantics |
| Delete row **trước** cursor | Xóa row đã nhận | Không làm dịch hàng đợi như OFFSET |
| Delete row **sau** cursor | Xóa row chưa nhận | Row bị xóa không xuất hiện; không hứa snapshot |
| Update trường **không nằm trong sort/filter** | Đổi note của order | Không dịch vị trí; nội dung có thể mới |
| Update trường sort hoặc status filter | Đổi created_at/status giữa các trang | Có thể skip/duplicate/ẩn row; phải có test chứng minh contract |
| Client thay đổi filter, sort hoặc limit | Tái dùng cursor cũ | Từ chối hoặc bắt đầu chuỗi mới theo contract |
| Gửi cursor của tenant khác | JWT tenant B với cursor tenant A | Không trả row tenant A, không rò internal IDs |
| Cursor sửa byte, sai MAC, quá dài, hết hạn | Fuzz input | 400/410 thích hợp, không full scan/5xx |
| Client gửi cùng cursor nhiều lần | Repeated GET | Ổn định khi DB không đổi; không tạo side effect |
| GET qua read replica lag | Điều khiển visibility/version | Chính sách read-after-write/snapshot không bị vi phạm |
| Đổi quyền sau khi lấy page 1 | Thu hồi scope/quyền resource | Trang tiếp bị chặn dù token cursor còn hợp lệ |

**Kỳ vọng có điều kiện:** nếu không có mutation và danh sách input có khóa unique, duyệt toàn bộ bằng cursor phải trả **đúng tập ID, đúng thứ tự, mỗi ID một lần**. Nếu chỉ có insert **trước cursor**, tập row ban đầu còn tồn tại phía sau phải vẫn đọc được, không bị duplicate do dịch offset. Khi cho phép **delete, đổi sort key hoặc đổi filter membership**, không được assert tính đầy đủ của snapshot nếu contract là live.

### 7.1. Phân cấp test để giảm false confidence

- **Unit test** comparator, encode/decode cursor, validation, response mapping; có thể dùng fixed clock và fake codec.
- **Service integration với PostgreSQL thật** kiểm tra tuple comparison, timestamp precision, index/collation, transaction visibility, insert/delete/update và SQL tenant filter.
- **HTTP integration (MockMvc/WebTestClient)** kiểm tra JSON, headers, 401/403/400/410, paging links và parsing URL.
- **Concurrency/fault tests** tạo commit xen giữa các page bằng connection khác, nhiều writers và replica/cache/gateway nếu dùng.
- **Property-based/model test** sinh tập row/chuỗi thao tác, so thuật toán với mô hình expected tùy invariant.

H2 hoặc một in-memory fake repository không chứng minh query PostgreSQL row comparison, độ chính xác timestamptz và isolation giống production. Dùng **Testcontainers PostgreSQL** hoặc một database test giống engine/phiên bản chính. **Không bọc toàn bộ integration test trong @Transactional** nếu muốn dữ liệu được nhìn thấy từ transaction/connection HTTP độc lập; cần seed bằng transaction đã commit.

### 7.2. MockMvc test với mutation xen giữa hai trang

Đoạn dưới là cấu trúc test minh họa, giả định helper **seedFourOpenOrders, insertOpenOrder** ghi/commit vào PostgreSQL test, cùng JWT test principal đã được cấu hình khớp VerifiedActorResolver:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
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
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPageHttpIT {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void insertAheadDoesNotRepeatTheLastItem() throws Exception {
        UUID tenant = UUID.randomUUID();
        UUID[] original = seedFourOpenOrders(tenant);
        // Fixture commit thứ tự A > B > C > D.

        var auth = jwt()
                .jwt(t -> t.subject("00000000-0000-0000-0000-000000000001")
                        .claim("tenant_id", tenant.toString()))
                .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders:read"));
        var first = mvc.perform(get("/v1/orders")
                .param("status", "OPEN").param("limit", "2")
                .with(auth))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(2))
                .andExpect(header().exists("Link"))
                .andReturn();
        JsonNode firstJson = mapper.readTree(
                first.getResponse().getContentAsString());
        assertEquals(original[0].toString(),
                firstJson.path("items").get(0).path("id").asText());
        String cursor = firstJson.path("nextCursor").asText();

        insertOpenOrder(tenant, Instant.parse("2026-11-18T10:00:00Z"));
        var second = mvc.perform(get("/v1/orders")
                .param("status", "OPEN").param("limit", "2")
                .param("cursor", cursor).with(jwt()
                    .jwt(t -> t.subject("00000000-0000-0000-0000-000000000001")
                            .claim("tenant_id", tenant.toString()))
                    .authorities(
                            new SimpleGrantedAuthority("SCOPE_orders:read"))))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode secondJson = mapper.readTree(
                second.getResponse().getContentAsString());
        assertEquals(original[2].toString(),
                secondJson.path("items").get(0).path("id").asText());
        assertEquals(original[3].toString(),
                secondJson.path("items").get(1).path("id").asText());
        assertTrue(secondJson.path("nextCursor").isNull());
    }
}
~~~

Đoạn test trên **không chạy độc lập** cho tới khi các fixture helper và project Spring/test database được cung cấp. Seed phải bảo đảm **thời gian của A/B/C/D đều nhỏ hơn 10:00Z** và sắp theo thứ tự được assert; mỗi row phải thuộc tenant riêng. Test không dùng **sleep()** để giả lập mutation: helper ghi transaction đã commit trước request tiếp theo, vì vậy thao tác xen giữa có thứ tự xác định.

**Spring Security test jwt()** dựng Authentication giả, **không kiểm tra chữ ký/issuer/audience của token thật**. Test resource server với JWT ký sai hoặc audience khác cần integration test riêng, không dùng fixture JWT làm bằng chứng crypto đã an toàn.

### 7.3. Test boundary size và đồng timestamp

Với **limit=2**, mỗi ca cần test cả body và Link:

~~~text
0 row       -> items=[], nextCursor=null, hasMore=false
1 row       -> 1 item, nextCursor=null
2 rows      -> 2 items, nextCursor=null
3 rows      -> 2 items, nextCursor có giá trị, trang 2 đúng 1 item

Rows: (t,c3), (t,c2), (t,c1), (t-1s,b9)
Page 1     -> c3,c2; cursor=(t,c2)
Page 2     -> c1,b9; không lặp c2, không mất c1
~~~

Thực hiện test trên PostgreSQL để kiểm tra **độ chính xác timestamp, UUID ordering và SQL tuple comparison**. Với trang có đúng limit row và không còn nữa, **không phát next**. Với row sau cursor bị xóa, trang cuối có thể trả ít hơn limit mà vẫn đúng live semantics.

## 8. Test bảo mật và độ bền của cursor

Không nên lấy một cursor JSON base64 chưa ký rồi tin vào **tenantId, lastId, timestamp** do client cung cấp. Ví dụ sau minh họa lớp kiểm chứng **HMAC-SHA256** cho một payload được serialize bằng JSON; mã **chỉ chịu trách nhiệm bảo vệ byte**, còn **CursorCodec** phải parse schema, version, expiry, tenant, status, limit và sort theo allowlist.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

class InvalidCursor extends RuntimeException {}

final class HmacCursorSigner {
    private final SecretKey key;

    // SecretKey được cấp từ secret manager/config an toàn, không hardcode.
    HmacCursorSigner(SecretKey key) {
        this.key = key;
    }

    private byte[] mac(byte[] data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            return mac.doFinal(data);
        } catch (Exception ex) {
            throw new IllegalStateException("Cursor signer unavailable", ex);
        }
    }

    String seal(String jsonPayload) {
        byte[] payload = jsonPayload.getBytes(StandardCharsets.UTF_8);
        String encoded = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(payload);
        String signature = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(mac(payload));
        return encoded + "." + signature;
    }

    String openVerified(String cursor) {
        if (cursor == null || cursor.length() > 4096) {
            throw new InvalidCursor();
        }
        String[] parts = cursor.split("\\.", -1);
        if (parts.length != 2) {
            throw new InvalidCursor();
        }
        try {
            byte[] payload = Base64.getUrlDecoder().decode(parts[0]);
            byte[] signature = Base64.getUrlDecoder().decode(parts[1]);
            if (!MessageDigest.isEqual(mac(payload), signature)) {
                throw new InvalidCursor();
            }
            return new String(payload, StandardCharsets.UTF_8);
        } catch (IllegalArgumentException ex) {
            throw new InvalidCursor();
        }
    }
}
~~~

Mẫu signer này cần được gắn với **CursorCodec** có parser JSON chặt chẽ: hạn chế field, từ chối version không hỗ trợ, so identity bằng claim đã xác minh, so filter/sort/limit của request, kiểm tra thời gian bằng **Clock** và ánh xạ **InvalidCursor → 400 Problem Details**. Nếu token snapshot hết hạn hoặc snapshot store đã xóa, **410** có thể phù hợp, nhưng phải phân biệt với MAC sai. Secret phải có cơ chế **rotation/kid và overlap có thời hạn**; HMAC **không che nội dung JSON**, nên tránh PII. Đừng log toàn token khi parser lỗi.

### 8.1. Các tình huống tampering bắt buộc

1. Lấy cursor của tenant A gửi với JWT tenant B: kết quả **không có dữ liệu A**, dù cả hai tenant có order ID giống dạng.
2. Giữ cursor nhưng đổi **status=OPEN → CLOSED** hoặc **limit=20 → 100**: bị từ chối theo contract, không tái sử dụng cặp khóa cho truy vấn khác.
3. Đổi một byte payload, bỏ dấu phân cách, base64 sai, chuỗi quá dài, signature rỗng: trả **400**, không 500 và không trả trang đầu.
4. Tạo cursor quá hạn bằng fixed Clock: trả lỗi hết hạn đã công bố; không phải ngủ chờ 10 phút thật trong test.
5. Revoke quyền đọc order giữa hai trang: **403/404** theo policy, không tiếp tục dùng token đã ký như “vé” thay cho quyền.
6. Gửi rất nhiều cursor hỏng: request phải bị **rate limit**, giới hạn parse/size và không tạo truy vấn DB tốn kém.

Test thuần signer có thể dùng byte của payload trước/sau một ký tự và assert InvalidCursor. Test HTTP thì phải chứng minh status, Problem Details và **không có SQL query được thực thi** khi MAC sai (qua metric/spy repository); ngoài ra kiểm tra path/status/limit thực sự gắn với scope đã ký.

## 9. Kiểm thử thay đổi đồng thời và oracle

Một test có **Thread.sleep** sau INSERT để đợi database “chắc đã cập nhật” là dễ flaky. Với integration test, dùng **CountDownLatch, CyclicBarrier hoặc CompletableFuture** để điều khiển thứ tự:

~~~text
Thread client:
    GET page1 -> lưu IDs + nextCursor
    signal page1Done
    wait mutationCommitted
    GET page2 -> assert contract

Thread writer (transaction riêng):
    wait page1Done
    INSERT/DELETE/UPDATE row đã chọn
    COMMIT
    signal mutationCommitted
~~~

Mô hình này đảm bảo **mutation commit nằm giữa hai HTTP GET**. Các test khác phải tạo hai writer cạnh tranh với nhau: ví dụ writer A tạo row trước cursor, writer B xóa row sau cursor; test kết quả theo **thứ tự commit quan sát được**. Nếu muốn test một trang đang chạy đồng thời với transaction ghi, phải định nghĩa isolation của SELECT và dùng barrier ở điểm trước/sau commit, không kỳ vọng thứ tự thread scheduling ngẫu nhiên.

### 9.1. Xây oracle đúng theo loại contract

**Không có mutation:** lấy danh sách ID từ query ORDER BY đầy đủ và so với kết quả nối tất cả các trang. Assert **set equality + ordered equality + không duplicate**; danh sách phải kết thúc, không loop vô hạn với cùng cursor.

**Chỉ insert trước cursor:** bảo toàn thứ tự/độ đầy đủ của các row cũ còn eligible phía sau, không thấy lại row đã trả. Row mới ở đầu chỉ thấy khi refresh.

**Live có delete/status mutation:** oracle cần mô hình mỗi trang tại thời điểm truy vấn và cursor boundary; **không** assert set bằng snapshot ban đầu. Có thể chụp thứ tự event commit do test tạo, rồi tính expected SELECT trên trạng thái tương ứng tại từng trang.

**Snapshot materialized:** oracle là **ID list và representation/version tại mốc chụp**. Sau khi insert/delete/update bảng live, mọi trang vẫn trả cùng set/order; nếu contract chỉ cố định ID list thì representation mới hoặc tombstone phải tuân theo chính sách riêng. Test snapshot TTL expiry, permission revocation, store outage, pagination đến hết và khi snapshot không còn.

### 9.2. Property-based/model-based testing

Sinh ngẫu nhiên các row với **timestamp có thể trùng**, tenant/status xen kẽ, limit từ 1 đến max và chiều sắp xếp được công bố; sinh chuỗi event insert/delete/update và phân trang theo thứ tự được ghi. Các thuộc tính phù hợp:

- **No mutation:** đúng thứ tự total order và không thiếu/trùng.
- **Cursor monotonicity:** mỗi item sau trang đầu có tuple khóa **nhỏ hơn** khóa cuối của trang trước, nếu sort và row keys bất biến.
- **Tenant isolation:** không có item nào có tenant khác, dù cursor/ID bị thay.
- **Pagination termination:** khi dữ liệu hữu hạn và không thêm vô hạn row phía sau, chuỗi trang kết thúc.
- **Next-link coherence:** có row dư thì có next; không row dư thì không next; token giải mã đúng khóa item cuối.
- **Snapshot set equality:** chỉ áp dụng nếu implementation thực sự hỗ trợ snapshot.

Để test tái lập được, ghi **random seed, danh sách thao tác, thời điểm commit và policy version** khi thất bại. Tránh assertion dựa trên thời gian hệ thống hoặc thứ tự thread không được kiểm soát. Property-based test của comparator trên Java vẫn phải đi kèm **PostgreSQL integration** vì null/collation/precision có thể khác.

## 10. Hiệu năng, quan sát và tiêu chí go/no-go

Keyset thường tránh phải bỏ qua hàng triệu row như OFFSET lớn, nhưng **không tự đảm bảo truy vấn nhanh**. Dùng **EXPLAIN (ANALYZE, BUFFERS)** trên dữ liệu mô phỏng production và kiểm tra index được dùng theo **tenant + filter + sort key**. Query có điều kiện kiểu “nếu cursor null thì bỏ qua” hoặc filter tùy chọn phức tạp có thể làm planner khó tối ưu; tách query branch theo trường hợp có cursor và đo cả hai.

Theo dõi p95/p99 theo **page size, sort/filter, trạng thái có/không cursor**, DB rows scanned, cache hit, replica lag, tỷ lệ 400/410 cursor, số trang trung bình/client và tình huống client dùng cursor hết hạn. Metric label theo **route template và status**, không gắn cursor nguyên văn, raw orderId, userId hoặc JWT (cardinality và rò dữ liệu).

**Go/no-go cho thay OFFSET bằng keyset** phải dựa trên contract: giảm duplicate/skip khi insert/delete ở đầu, kết quả đúng với tie timestamp, không rò tenant, latency được cải thiện ở deep pages và có kế hoạch cho client cũ cần nhảy tới trang N. Keyset thường **không hỗ trợ “nhảy trực tiếp trang 527”** nếu không có index/anchor phụ. Nếu sản phẩm đòi snapshot thật, không tuyên bố đã đạt chỉ bằng đổi offset thành cursor.

## 11. Bài tập: kiểm thử danh sách đơn hàng đang thay đổi

Một API dùng PostgreSQL cung cấp **GET /v1/orders?status=OPEN&limit=3&cursor=...**. Mỗi tenant có tối đa 100.000 đơn, nhiều đơn có timestamp bằng nhau. Khi client cuộn, nhân viên có thể đổi status sang CLOSED, worker có thể backfill đơn cũ, và một replica được dùng để phục vụ GET. Product owner đưa ra hai yêu cầu: màn hình quản lý cần **feed live không lặp do insert ở đầu**, còn tính năng xuất báo cáo cần **đúng toàn bộ danh sách tại thời điểm yêu cầu xuất**.

Hãy hoàn thành:

1. **Phân loại contract** của feed và export; giải thích vì sao không thể dùng một lời hứa “stable pagination” chung.
2. Vẽ thứ tự **created_at DESC, id DESC**, thiết kế điều kiện SQL keyset và cursor gồm những field nào.
3. Chứng minh bằng hai kịch bản OFFSET: **insert X vào đầu làm trùng C** và **delete B làm bỏ D** với page size 3.
4. Với keyset, dự đoán kết quả khi **sort key của A giảm qua cursor** hoặc **status của D đổi CLOSED**; nêu test nào nên đậu và test nào không thể hứa.
5. Thiết kế **snapshot-backed export** với job/operation ID, TTL, representation/version và cách xử lý quyền bị thu hồi khi client đang tải.
6. Viết test **PostgreSQL/Testcontainers + MockMvc**, có ít nhất một case timestamp tie, một case INSERT đã commit giữa hai GET và một case cursor tenant khác.
7. Test **limit=3** khi có 2, 3, 4 row; kiểm tra nextCursor, Link, số item và kết thúc chuỗi.
8. Đặt **SLO và cảnh báo** cho deep-page latency, 410 snapshot expired, replica lag và SQL scan.

**Đáp án định hướng:** feed dùng live keyset với sort key bất biến và yêu cầu client refresh để thấy item mới phía trước; export dùng snapshot/temporal version hoặc materialized representation có TTL. Với feed, đổi status có thể làm item biến mất mà không vi phạm hợp đồng; với export, thay đổi live **không được thay kết quả snapshot**. Tất cả trang vẫn phải kiểm tra tenant/quyền, không tin cursor dù đã ký. Trong test, đảm bảo mutation commit sau page 1 và trước page 2, không dựa vào sleep ngẫu nhiên.

## 12. Checklist và tài liệu tham khảo

- [ ] Hợp đồng phân biệt **deterministic order, live keyset và snapshot**; không dùng từ “ổn định” mơ hồ.
- [ ] ORDER BY có **tie-breaker unique**, thứ tự/null/collation nhất quán với cursor predicate.
- [ ] Trang sau dùng **khóa cuối đã trả**, lấy dư **limit+1** và không bỏ dòng lookahead.
- [ ] Test **insert, delete, update sort key, update filter, equal timestamp** giữa các trang.
- [ ] Kiểm tra **page rỗng/đúng N/N+1**, không có next ở trang cuối, Link và body đồng nhất.
- [ ] Cursor có signature/MAC, TTL, version, tenant/filter/sort/size binding; quyền luôn được kiểm tra lại.
- [ ] Snapshot thực sự cố định **membership và representation/version** nếu contract yêu cầu; high-watermark có bảo đảm commit-order được chứng minh.
- [ ] Kiểm thử bằng DB production-compatible, mutation được commit từ connection khác, barrier/fixed clock và replica/cache khi có sử dụng.
- [ ] Đo latency deep page, rows scanned, false 400/410, invalid cursor flood, tenant isolation và authorization change.

Tham khảo: **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 8288 Web Linking**, https://www.rfc-editor.org/rfc/rfc8288.html; **Spring MVC Testing (MockMvc)**, https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html; **Spring JDBC NamedParameterJdbcTemplate**, https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html; **PostgreSQL SELECT/ORDER BY**, https://www.postgresql.org/docs/current/sql-select.html; **PostgreSQL Transaction Isolation**, https://www.postgresql.org/docs/current/transaction-iso.html; **Testcontainers Java PostgreSQL**, https://java.testcontainers.org/modules/databases/postgres/.

**Kết luận:** Kiểm thử phân trang ổn định không chỉ là kiểm tra LIMIT và OFFSET; đó là kiểm tra **một lời hứa về thứ tự, phạm vi dữ liệu và thời điểm quan sát** khi có giao dịch ghi xen giữa. **Keyset giải quyết dịch chuyển offset và tie-breaker giải quyết thứ tự không xác định**, nhưng **snapshot thật mới bảo đảm tập dữ liệu tại một mốc bất biến**. Chọn contract trước, viết test theo đúng mức bảo đảm và luôn giữ phân quyền tenant cùng cursor integrity trên mọi trang.
