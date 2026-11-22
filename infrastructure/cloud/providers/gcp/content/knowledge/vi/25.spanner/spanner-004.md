# Thiết kế schema và lựa chọn primary keys

Một nền tảng học trực tuyến dùng Cloud Run phục vụ API đăng ký khóa học, GKE xử lý sự kiện và Spanner lưu dữ liệu giao dịch. Mỗi giây, hàng nghìn học viên có thể đăng ký, thanh toán hoặc gửi tiến độ. Nếu ứng dụng chọn khóa chính tăng dần như `EnrollmentId=1,2,3,...` vì quen với cơ sở dữ liệu một máy, phần lớn lượt ghi mới có thể dồn vào cùng một **key range**. Spanner có nhiều tài nguyên tính toán nhưng độ trễ ghi vẫn tăng vì một vùng dữ liệu bị nóng (*hotspot*).

Trong chương **Spanner** của module **CLOUD_PROVIDERS_GCP**, bài này tập trung vào cách **thiết kế bảng, quan hệ dữ liệu và primary keys** phù hợp cơ chế phân tán. Mục tiêu là lựa chọn cân bằng giữa **phân phối tải, tính duy nhất, locality khi đọc, tính nhất quán và chi phí index**. Các ví dụ dùng **GoogleSQL dialect**; Spanner cũng hỗ trợ **PostgreSQL dialect**, nhưng cú pháp DDL và một số hàm không giống hệt nhau.

**Sau bài học, bạn có thể:**

1. Giải thích Spanner lưu hàng theo thứ tự khóa và chia thành các **splits**.
2. Nhận diện khóa timestamp/sequence tăng tuần tự tạo hotspot và chọn UUIDv4, bit-reversed sequence hoặc khóa ghép phù hợp.
3. Thiết kế bảng quan hệ, secondary indexes và bảng interleaved theo query patterns.
4. Tính đến multi-tenancy, transaction locality, row/parent hotspots và write amplification.
5. Kiểm tra bằng schema DDL, query plans, metrics/Key Visualizer và bài tập tình huống.

## 1. Mô hình lưu trữ quyết định cách chọn primary key

Spanner là cơ sở dữ liệu quan hệ phân tán, hỗ trợ giao dịch nhất quán mạnh và phân phối dữ liệu trên nhiều máy. Các hàng trong một bảng được **sắp theo thứ tự primary key**. Spanner chia các khoảng khóa thành các **splits** và phân công chúng cho các máy chủ; các ranh giới split có thể thay đổi theo dung lượng và tải.

~~~mermaid
flowchart TB
    A["Bảng Enrollments<br/>được sắp theo primary key"] --> S1["Split: khoảng khóa A–F"]
    A --> S2["Split: khoảng khóa G–N"]
    A --> S3["Split: khoảng khóa O–Z"]
    S1 --> N1["Server 1"]
    S2 --> N2["Server 2"]
    S3 --> N3["Server 3"]
    W["Nhiều writer"] -->|"PK phân bố"| S1
    W --> S2
    W --> S3
~~~

Sơ đồ chỉ minh họa: splits không nhất thiết khớp chữ cái, một server có thể phụ trách nhiều splits và Spanner tự cân bằng theo tải.

### 1.1. Vì sao thứ tự key quan trọng?

| Thuộc tính | Hệ quả khi thiết kế |
| --- | --- |
| Hàng được sắp theo PK | **Point lookup** qua đầy đủ PK hiệu quả; **range scan** theo prefix/range khóa có locality tốt hơn quét tùy ý. |
| Splits là khoảng key | Những lượt ghi dồn vào **cuối/đầu một khoảng liên tục** có thể làm một split quá tải. |
| Khóa ghép theo thứ tự từ trái sang phải | `(TenantId, StudentId, EventTime)` thuận lợi khi truy vấn biết tenant/student; không tự tối ưu truy vấn chỉ biết EventTime. |
| Primary key đồng thời là cấu trúc vật lý | Đổi thứ tự key có thể thay đổi **phân phối tải, locality, transaction và chiến lược query**; không chỉ đổi constraint. |
| Secondary index có cấu trúc khóa riêng | Bảng chính phân bố tốt vẫn có thể bị **index hotspot** nếu index bắt đầu bằng timestamp tăng dần. |

**Primary key phải phân biệt duy nhất từng hàng**, nhưng *duy nhất* chưa đủ: với Spanner, một khóa hợp lý cần còn **phân tán được ghi** và phục vụ được truy vấn chủ đạo.

### 1.2. Ba câu hỏi bắt buộc trước khi viết DDL

1. **Đường ghi:** dữ liệu được tạo theo thứ tự nào, có tăng đều theo thời gian, có tenant/account cực nóng không?
2. **Đường đọc:** ứng dụng thường tìm theo một ID, một tenant, một user hay danh sách sự kiện gần đây?
3. **Quan hệ dữ liệu:** những hàng nào cần đọc/giao dịch cùng nhau và có parent có số child quá lớn không?

Để có thiết kế đáng tin, thu thập tỷ lệ đọc/ghi, QPS/TPS, phân bố theo tenant, dữ liệu tăng trưởng, p95/p99 và nhóm query quan trọng. Không chọn khóa dựa trên ví dụ chỉ có vài hàng.

## 2. Chọn khóa chính: bốn phương án thường gặp

### 2.1. Tránh timestamp hoặc ID tăng dần ở vị trí đầu với bảng ghi lớn

Ví dụ **không phù hợp** cho bảng sự kiện liên tục có tốc độ ghi cao:

~~~sql
-- GoogleSQL; ví dụ ANTI-PATTERN cho workload insert lớn.
CREATE TABLE EnrollmentEventsBad (
  CreatedAt TIMESTAMP NOT NULL,
  EventId STRING(64) NOT NULL,
  StudentId STRING(64) NOT NULL,
  Kind STRING(32),
) PRIMARY KEY (CreatedAt, EventId);
~~~

Các timestamp mới liên tục tăng, nên lượt insert hầu hết nhắm tới **cuối keyspace**. Dù thêm `EventId` duy nhất làm cột thứ hai, prefix `CreatedAt` vẫn có tính tuần tự. Đổi từ `ASC` sang `DESC` không giải quyết tận gốc: nó chỉ chuyển điểm nóng sang **đầu** khoảng khóa.

Tương tự, key `(OrderId INT64)` lấy từ sequence **tăng đều** hoặc một ID dựa trên thời gian (như UUIDv1; nhiều dạng ID sắp được theo thời gian) có thể tạo điểm nóng khi insert tập trung. Không nên dựa vào nhãn “UUID” mà bỏ qua **thứ tự byte và entropy ở phần đầu**.

### 2.2. UUIDv4 ngẫu nhiên cho bảng root ghi nhiều

Spanner khuyến nghị **UUID version 4** cho nhiều bảng mới vì các giá trị phân bố rộng và ít có xu hướng tập trung ở một key range.

~~~sql
-- GoogleSQL dialect. Không chạy trên database production không có phê duyệt.
CREATE TABLE Students (
  StudentId UUID NOT NULL DEFAULT (NEW_UUID()),
  Email STRING(320) NOT NULL,
  DisplayName STRING(200),
  CreatedAt TIMESTAMP,
) PRIMARY KEY (StudentId);
~~~

Ví dụ insert và trả khóa được Spanner sinh:

~~~sql
INSERT INTO Students (Email, DisplayName)
VALUES ('student-lab@example.invalid', 'Hoc vien lab')
THEN RETURN StudentId;
~~~

**Ưu điểm:** client không cần điều phối số thứ tự; phân phối lượt insert của những student mới trên nhiều khoảng khóa; PK là định danh không đổi. **Đổi lại:** các ID không chứa thứ tự thời gian hoặc thông tin kinh doanh, và truy vấn tìm theo Email/CreatedAt thường cần **secondary index**. UUIDv4 ngẫu nhiên cũng không giúp tối ưu range scan “100 học viên mới nhất” nếu không có thêm index/query design.

Không dùng UUIDv4 làm “bảo mật”: ID khó đoán **không thay thế** kiểm tra IAM, tenant ownership và phân quyền ở API.

### 2.3. Bit-reversed sequence khi API yêu cầu khóa số

Nếu cần số nguyên 64-bit vì migration hoặc hợp đồng API, Spanner cung cấp **bit-reversed positive sequence** để phân tán các giá trị sinh ra thay vì gom về cuối keyspace.

~~~sql
-- GoogleSQL dialect; chỉ minh họa trên DB lab.
CREATE SEQUENCE EnrollmentSeq OPTIONS (
  sequence_kind = 'bit_reversed_positive'
);

CREATE TABLE EnrollmentIds (
  EnrollmentId INT64 NOT NULL
    DEFAULT (GET_NEXT_SEQUENCE_VALUE(SEQUENCE EnrollmentSeq)),
  StudentId STRING(64) NOT NULL,
  CourseId STRING(64) NOT NULL,
) PRIMARY KEY (EnrollmentId);
~~~

Giá trị từ sequence có thể **không tăng đều theo thời gian** và không nhất thiết liền mạch: đừng dùng nó làm số hóa đơn mang yêu cầu tuần tự không có khoảng trống. Spanner còn hỗ trợ cơ chế `IDENTITY`, `AUTO_INCREMENT` và `SERIAL` (tùy dialect), nhưng phải xem **cách các giá trị được phân phối**, không đánh đồng với auto-increment đơn máy của RDBMS cũ.

Với migration từ ID số hiện có, phải tránh **va chạm khóa** giữa dữ liệu cũ và khóa mới: có thể cần skipped range/cấu hình sequence và quy trình đối soát trước cutover.

### 2.4. Khóa ghép để phục vụ truy vấn theo nhóm

Giả sử API thường đọc toàn bộ enrollment của một học viên. Khóa ghép:

~~~sql
CREATE TABLE Enrollments (
  StudentId UUID NOT NULL,
  EnrollmentId UUID NOT NULL DEFAULT (NEW_UUID()),
  CourseId STRING(64) NOT NULL,
  Status STRING(32) NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
) PRIMARY KEY (StudentId, EnrollmentId);
~~~

Các enrollment của cùng `StudentId` được xếp gần nhau theo prefix của khóa, giúp truy vấn:

~~~sql
-- Dùng tham số trong production; giá trị chỉ minh họa kiểu UUID.
SELECT EnrollmentId, CourseId, Status
FROM Enrollments
WHERE StudentId = @student_id;
~~~

**Đánh đổi:** nếu một StudentId/tenant có lượng ghi rất lớn, locality có thể trở thành hotspot. Khi truy vấn chỉ biết `EnrollmentId`, khóa ghép trên lại **không cung cấp point lookup bằng một cột**; cần biết StudentId hoặc thêm index phù hợp.

| Loại khóa | Tốt nhất khi | Rủi ro cần thử |
| --- | --- | --- |
| `UUIDv4` đầu PK | Tạo root rows trên nhiều writers, tra cứu theo ID | Không tự phục vụ thứ tự thời gian/nhóm |
| `INT64` bit-reversed | Cần tương thích khóa số, throughput insert cao | Khóa không có thứ tự tăng ý nghĩa |
| `(StudentId, EnrollmentId)` | Đọc/ghi theo từng học viên, thao tác trong nhóm | Một học viên cực nóng, tra cứu chỉ EnrollmentId |
| `(CreatedAt, EventId)` | Scan gần đây có vẻ thuận | **Hotspot ghi** nếu CreatedAt tăng liên tục |

**Quy tắc:** chọn thứ tự khóa theo **đường ghi và đường đọc thật**. Không có một kiểu primary key tối ưu cho mọi bảng.

## 3. Thiết kế quan hệ: interleaving, foreign keys và locality

Spanner hỗ trợ **foreign keys** và **interleaved tables**. Hai cơ chế có mục đích khác nhau:

- **Foreign key:** mô tả/ràng buộc quan hệ dữ liệu. Không nhất thiết đặt hai bảng gần nhau về vật lý.
- **Interleaving:** bố trí hàng của bảng con gần hàng của bảng cha trong thứ tự khóa, để các hàng thường đọc cùng nhau có locality tốt; cũng áp dụng ràng buộc cha–con.

### 3.1. Interleaved child theo prefix khóa cha

Trong ví dụ `Students` và `Enrollments`, nếu hầu hết API tìm enrollment **theo student**, có thể dùng:

~~~sql
-- GoogleSQL. Giả sử bảng Students(StudentId UUID) đã tồn tại.
CREATE TABLE EnrollmentsInterleaved (
  StudentId UUID NOT NULL,
  EnrollmentId UUID NOT NULL,
  CourseId STRING(64) NOT NULL,
  Status STRING(32) NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
) PRIMARY KEY (StudentId, EnrollmentId),
  INTERLEAVE IN PARENT Students ON DELETE CASCADE;
~~~

Những điều kiện quan trọng:

1. Khóa của bảng con phải bắt đầu bằng **các cột khóa của cha, đúng thứ tự, tên và kiểu**.
2. Parent row phải tồn tại trước, hoặc được tạo trong cùng transaction theo quy tắc Spanner.
3. `ON DELETE CASCADE` sẽ xóa cả child rows khi xóa parent; chỉ dùng nếu đúng vòng đời dữ liệu. `ON DELETE NO ACTION` yêu cầu xử lý child trước khi xóa parent.
4. Locality **không có nghĩa một row tree mãi nằm trong một split**: Spanner có thể chia khi dữ liệu hoặc tải lớn.
5. Với một parent có **hàng triệu child hoặc ghi tập trung**, interleaving có thể làm hotspot/transaction trở nên phức tạp. Không lồng mọi dữ liệu vào một root “global tenant”.

~~~mermaid
flowchart TB
    S1["Student A (parent row)"] --> A1["Enrollment A-1"]
    S1 --> A2["Enrollment A-2"]
    S2["Student B (parent row)"] --> B1["Enrollment B-1"]
    S2 --> B2["Enrollment B-2"]
    NOTE["Các hàng liên quan theo<br/>prefix StudentId, không phải JOIN miễn phí"]
    A1 -.-> NOTE
~~~

**Không nên interleave chỉ vì có foreign key logic.** Nếu nghiệp vụ thường truy vấn “mọi enrollment của CourseId trên toàn bộ học viên”, key prefix `StudentId` không tối ưu cho query đó; cần secondary index hoặc bảng/đường truy vấn khác.

### 3.2. Transaction locality và khóa ghi thường xuyên

Đặt các hàng được truy cập/giao dịch cùng nhau gần nhau có thể giảm công việc trên nhiều splits. Tuy nhiên, nếu một row hoặc key prefix nhận **tất cả lượt UPDATE** (ví dụ hàng `GlobalCounters` dùng chung), bản thân hàng ấy là điểm nghẽn dù khóa phân phối của các bảng khác tốt.

Tránh cập nhật một bộ đếm toàn cục sau mỗi enrollment nếu cần thông lượng rất cao. Xem xét:

- Đếm theo **shard** rồi tổng hợp khi đọc, nếu nghiệp vụ chấp nhận.
- Dùng tổng hợp bất đồng bộ/analytics cho chỉ số không cần nhất quán tức thì.
- Giữ transaction ghi ngắn, giới hạn số hàng và phạm vi khóa tham gia.
- Chọn consistency của việc đọc theo yêu cầu thực tế; không hy sinh dữ liệu tài chính vì một phép tối ưu chưa kiểm thử.

## 4. Multi-tenant schema và key prefix

Giả sử một SaaS phục vụ nhiều trường học. Cần bảo đảm mỗi request chỉ truy cập bản ghi thuộc `TenantId`. Một khóa ghép dễ hiểu:

~~~sql
CREATE TABLE TenantCourses (
  TenantId STRING(64) NOT NULL,
  CourseId UUID NOT NULL DEFAULT (NEW_UUID()),
  Name STRING(200) NOT NULL,
  Status STRING(32) NOT NULL,
) PRIMARY KEY (TenantId, CourseId);
~~~

Khi client gửi `tenantId` và `courseId`, query có thể lọc theo cả prefix:

~~~sql
SELECT Name, Status
FROM TenantCourses
WHERE TenantId = @tenant_id
  AND CourseId = @course_id;
~~~

**Tính cách ly dữ liệu:** khóa chứa `TenantId` hữu ích để thiết kế query và locality, **nhưng không tự thực thi authorization**. API phải xác minh tenant từ danh tính đã xác thực; không lấy `tenant_id` tùy ý trong request làm bằng chứng quyền.

### 4.1. Khi tenant là hot key

Khóa `(TenantId, CreatedAt, EventId)` có thể tốt cho truy vấn sự kiện theo tenant, nhưng nếu chỉ **một tenant** tạo hàng chục nghìn event/s, các timestamp tăng liên tục **trong tenant đó** vẫn tạo một vùng ghi nóng.

Một cách tránh là đặt shard hoặc ID phân bố trước timestamp:

~~~sql
CREATE TABLE TenantEvents (
  TenantId STRING(64) NOT NULL,
  ShardId INT64 NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
  EventId UUID NOT NULL,
  Payload JSON,
) PRIMARY KEY (TenantId, ShardId, CreatedAt DESC, EventId);
~~~

Ứng dụng tính `ShardId` **ổn định** từ `EventId`, ví dụ hash vào N logical shards. Khi ghi, các event của cùng tenant phân tán ra nhiều dãy key theo ShardId; mỗi dãy được sắp theo thời gian.

**Đánh đổi khi đọc:** truy vấn “50 event mới nhất của một tenant” phải đọc **N shards**, lấy các kết quả gần nhất rồi merge/sort/limit. Không thể chỉ dùng một range scan theo tenant và mong có đủ thứ tự thời gian toàn tenant.

Vì thế:

- Chọn N theo **lưu lượng thực, năng lực và số splits/nodes**, không tạo hàng triệu shard theo cảm tính.
- N là một phần schema/query contract; thay N có thể cần migration/backfill.
- `DESC` giúp lấy gần đây trong từng shard, **không khắc phục hotspot** nếu chỉ có một shard nóng.
- Một tenant ít tải không nhất thiết cần hash sharding; đừng đánh đổi locality để xử lý vấn đề chưa tồn tại.

### 4.2. Key ghép có điều kiện

| Query chủ đạo | Key/index có thể thử | Đánh đổi |
| --- | --- | --- |
| Tìm course theo tenant + course ID | PK `(TenantId, CourseId)` | Không có global point lookup chỉ bằng CourseId |
| Đọc enrollments theo student | PK `(StudentId, EnrollmentId)` | Cần index nếu tìm từ CourseId |
| Sự kiện gần đây của mỗi student | `(StudentId, EventTime DESC, EventId)` | Hot student có thể thành điểm nóng |
| Ghi event theo tenant cực nóng | `(TenantId, ShardId, CreatedAt DESC, EventId)` | Đọc toàn tenant phải fan-out và merge |
| Truy vấn ngẫu nhiên toàn hệ thống theo ID | PK UUIDv4 độc lập | Không tự gom dữ liệu cùng tenant |

Trong Spanner, **tăng số lượng key columns không đồng nghĩa tăng khả năng phân phối**: cần đánh giá **phân bố phần đầu khóa** và pattern của writes thực tế.

## 5. Secondary indexes: tối ưu đọc nhưng có thể tạo hotspot mới

Primary key chọn theo `StudentId` giúp đọc dữ liệu một học viên. Nhưng dịch vụ khóa học cần tìm **toàn bộ enrollment của một khóa học**; đó là lúc secondary index có giá trị.

### 5.1. Một index theo truy vấn thực tế

~~~sql
CREATE INDEX EnrollmentsByCourse
ON Enrollments(CourseId, StudentId)
STORING (Status, CreatedAt);
~~~

Truy vấn:

~~~sql
SELECT StudentId, Status, CreatedAt
FROM Enrollments
WHERE CourseId = @course_id;
~~~

Spanner có thể dùng index khi phù hợp; `STORING` lưu thêm cột trong index để tránh phải đọc lại bảng gốc cho một số truy vấn. Điều này tăng **storage** và **write amplification**: mỗi lần UPDATE cột được index/store có thể phải sửa thêm dữ liệu index.

Không tạo index cho mọi cột rồi hy vọng tất cả query nhanh. Mỗi index làm tăng chi phí ghi, lưu trữ và thời gian backfill/schema change. Dùng **query plan/EXPLAIN và workload metrics** để chứng minh lợi ích.

### 5.2. Index có thể nóng ngay khi primary key không nóng

Giả sử bảng log có PK là UUIDv4 phân bố đều, nhưng thêm:

~~~sql
-- RỦI RO: index bắt đầu bằng timestamp tăng đều.
CREATE INDEX LogsByCreatedAt
ON EventLogs(CreatedAt);
~~~

Mỗi message insert có thể phải **ghi index vào vùng cuối keyspace** của index. Bảng gốc phân bố tốt không giải quyết hotspot của cấu trúc index.

Phương án tùy bài toán:

- Nếu query luôn biết `UserId`: index `(UserId, CreatedAt DESC)`; workload phải có nhiều user active để phân bố.
- Nếu query toàn hệ thống theo thời gian: cân nhắc **sharded time index**, fan-out đọc hoặc chuyển workload phân tích sang hệ thống phù hợp.
- Nếu chỉ cần trả vài event theo PK: cân nhắc bỏ index ít giá trị để giảm write amplification.

### 5.3. Null-filtered và unique indexes

Trong **GoogleSQL dialect**, index dạng `NULL_FILTERED` bỏ các hàng có NULL ở cột khóa index:

~~~sql
CREATE NULL_FILTERED INDEX EnrollmentsByCompletedAt
ON Enrollments(CompletedAt DESC);
~~~

Đoạn này chỉ dùng khi bảng thực có cột `CompletedAt TIMESTAMP` cho phép NULL; đây là ví dụ ý tưởng **bổ sung schema**, không chạy trực tiếp trên bảng `Enrollments` chưa có cột đó. Index nhỏ hơn nếu phần lớn enrollment chưa hoàn tất, nhưng query cần trả cả NULL **không thể** dùng chỉ index này để có kết quả đầy đủ.

**Unique index** thực thi tính duy nhất theo index key; với `UNIQUE NULL_FILTERED`, các hàng bị lọc do NULL **không chịu ràng buộc unique của index ấy**. Với email/username cần unique, hãy chuẩn hóa dữ liệu, quy định NULL và scope tenant rõ ràng trước khi thêm unique index.

Lưu ý: trong **PostgreSQL dialect**, cú pháp tương ứng dùng `INCLUDE` thay `STORING`, và index lọc NULL theo điều kiện `WHERE ... IS NOT NULL`. Không trộn hai dialect trong một file DDL.

## 6. Đổi schema và primary key khi hệ thống đã chạy

Spanner hỗ trợ nhiều thay đổi schema **trực tuyến** như thêm cột, bảng hoặc index. Tuy vậy, một thay đổi ảnh hưởng đến **primary key, khóa tham chiếu, thứ tự hàng hoặc hợp đồng API** thường là bài toán migration dữ liệu; không nên coi là lệnh `ALTER` đơn giản, không rủi ro.

### 6.1. Quy trình chuyển từ khóa tuần tự sang UUID

Giả sử bảng cũ dùng `OrderId INT64` tăng dần, đã xuất hiện write hotspot. Quy trình đề xuất:

1. **Đo và xác định nguồn hotspot:** PK của bảng, secondary index hay một hàng counter chung?
2. **Thiết kế key mới:** UUIDv4 hoặc bit-reversed sequence theo yêu cầu tương thích; xác định cách tra cứu ID cũ.
3. **Tạo bảng mới** với PK khác trong môi trường đã phê duyệt; thêm unique index/mapping nếu vẫn cần tìm theo ID cũ.
4. **Backfill** theo những batch có giới hạn, kiểm tra số hàng, checksum/đối soát và tốc độ tăng CPU/I/O.
5. **Đồng bộ thay đổi trong giai đoạn chuyển tiếp** bằng CDC/outbox hoặc cơ chế phù hợp; tránh dual-write thiếu khả năng giải quyết ghi một bên thành công, một bên thất bại.
6. **Chuyển read/write có kiểm soát**, quan sát latency, conflicts, duplicate keys và backlog; có rollback plan trước khi nhận ghi mới.
7. **Dọn bảng/index cũ** khi xác minh dữ liệu không còn phụ thuộc, có backup và phê duyệt.

**Đừng thiết kế rollback chỉ bằng đổi connection string:** nếu dữ liệu đã được ghi vào bảng mới, quay về bảng cũ có thể đòi reverse replication/reconciliation. Đặc biệt với giao dịch thanh toán, cần thử xử lý duplicate, idempotency và tính nhất quán từ đầu.

### 6.2. Index backfill và chi phí thay đổi schema

Khi thêm secondary index vào bảng đang có dữ liệu, Spanner cần **backfill** index. Hệ thống có thể tiếp tục phục vụ, nhưng backfill dùng tài nguyên và có thể ảnh hưởng CPU/độ trễ. Với index lớn:

- Kiểm tra **mức tải và capacity dự phòng**, giới hạn thay đổi trong maintenance/change window được phê duyệt.
- Theo dõi progress và query plan sau khi index sẵn sàng.
- Kiểm tra các truy vấn bắt buộc có điều kiện lọc phù hợp, nhất là `NULL_FILTERED`.
- Đo tăng dung lượng index và chi phí ghi sau khi thêm; xóa index không hữu ích theo quy trình review.

### 6.3. Commit timestamp và TTL: tránh hotspot vô tình

Spanner hỗ trợ lưu **commit timestamp** vào cột được khai báo phù hợp. Nó hữu ích để audit thời điểm ghi, nhưng nếu đưa commit timestamp tăng dần làm **cột đầu PK** hoặc **cột đầu secondary index**, có thể tạo điểm nóng tương tự timestamp thường. Nên dùng như **cột dữ liệu không dẫn đầu khóa** khi yêu cầu truy vấn cho phép.

**TTL/row deletion policy** giúp dọn dữ liệu hết hạn theo nền tảng, nhưng xóa **bất đồng bộ**, không tức thì đến đúng giây quy định; phải kiểm tra chính sách retention, quan hệ cha–con và nhu cầu giữ dữ liệu theo quy định. TTL không sửa được key hotspot.

## 7. Chứng minh thiết kế bằng đo lường

### 7.1. Baseline cần thu thập

| Nhóm tín hiệu | Cần đo |
| --- | --- |
| **Lưu lượng** | Inserts/updates/reads mỗi giây, phân bố theo tenant/user, kích thước row, peak burst. |
| **Độ trễ** | p50/p95/p99 theo thao tác, deadline exceeded và transaction aborts/retries. |
| **Resource** | CPU utilization, storage, write throughput, số nodes/processing units. |
| **Key distribution** | Hot ranges, split patterns và mức skew theo key prefix. |
| **Truy vấn** | Query plan, index usage, scanned rows/bytes, lock/transaction conflicts. |
| **Index cost** | Số index phải cập nhật mỗi write, backfill, dung lượng và latency. |
| **Nghiệp vụ** | Idempotent write, đúng dữ liệu theo tenant, khả năng xử lý sau lỗi. |

**Key Visualizer** tạo heatmap cho hoạt động theo khoảng khóa, giúp tìm nơi read/write dồn cục bộ. Đặt nó bên cạnh Cloud Monitoring, query statistics và transaction insights để kết luận nóng ở **primary table, secondary index hay cùng một hàng/nhóm khóa**.

~~~mermaid
flowchart TD
    ALERT["Write p99 hoặc ABORTED tăng"] --> KV["Key Visualizer:<br/>hot key range nào?"]
    KV --> PK{"Primary table hay index?"}
    PK -->|Primary table| K["Kiểm tra prefix key, sequential ID,<br/>tenant skew và hot counter"]
    PK -->|Secondary index| I["Kiểm tra leading index key<br/>và write amplification"]
    K --> TEST["Đề xuất schema/query mới,<br/>test với tải đại diện"]
    I --> TEST
    TEST --> VERIFY{"p99, skew, costs<br/>có cải thiện?"}
    VERIFY -->|Không| KV
    VERIFY -->|Có| KEEP["Ghi ADR và kế hoạch rollout"]
~~~

**Chú ý:** Spanner tự split và cân bằng tải, nhưng không thể “chữa” một dãy timestamp tăng đều bằng việc mãi thêm server. Khi mọi write mới rơi vào một đầu của cùng một range, giới hạn ở **mô hình khóa/traffic**, không chỉ ở tổng capacity.

### 7.2. Tín hiệu để không sửa nhầm

| Biểu hiện | Chưa nên kết luận | Bước điều tra |
| --- | --- | --- |
| CPU tổng còn thấp, write p99 cao | “Cần tăng node gấp đôi” | Xem hot range và phân bố write/key. |
| PK UUIDv4 nhưng insert chậm | “UUID không hiệu quả” | Kiểm tra timestamp-leading index, mutation count, quota và transaction conflicts. |
| Một tenant p99 cao | “Toàn DB thiếu capacity” | Đo per-tenant QPS/row hotspots, key prefix và transaction scope. |
| Query theo CourseId quét nhiều dữ liệu | “Phải đổi PK của mọi bảng” | Xem index/query plan trước; cân nhắc index theo CourseId. |
| Thêm index xong write p99 tăng | “Cần giữ index vì read nhanh” | Đo write amplification và cân nhắc cân bằng read/write. |

Để so sánh hai thiết kế, benchmark cùng **dataset, tỷ lệ read/write, phân bố tenant, số node/PU, cache profile và concurrency**. Một lab vài chục hàng chỉ chứng minh DDL/logic, **không chứng minh phân phối key ở quy mô lớn**.

## 8. Thực hành an toàn với database lab GoogleSQL

**Mục tiêu:** tạo một bảng root UUID, bảng child theo prefix, secondary index phục vụ query theo khóa học; đối chiếu phương án PK tuần tự và tự đánh giá query patterns.

**Điều kiện:** project đã có **Spanner instance + database GoogleSQL lab riêng** với billing/quota được phê duyệt. Thay đổi DDL tạo bảng/index và có thể phát sinh chi phí. Không chạy trên database production; không ghi dữ liệu cá nhân thật. Người học chỉ thực hiện khi có quyền schema update và data write trên database lab.

### 8.1. Đọc metadata, không làm thay đổi tài nguyên

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export INSTANCE_ID="YOUR_LAB_SPANNER_INSTANCE"
export DATABASE_ID="YOUR_LAB_GOOGLESQL_DATABASE"

gcloud config set project "$PROJECT_ID"
gcloud spanner instances describe "$INSTANCE_ID" --project="$PROJECT_ID"
gcloud spanner databases describe "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID"
gcloud spanner databases ddl describe "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID"
~~~

**Nếu tên bảng `LabStudents` hoặc `LabEnrollments` đã tồn tại, dừng.** Chọn database lab trống hoặc namespace/tên mới được phép; không overwrite bảng của nhóm khác. Nếu database là PostgreSQL dialect, không chạy các mẫu GoogleSQL dưới đây.

### 8.2. DDL cho hai bảng và một index

Trong **Spanner Studio** của database lab đã xác minh, áp dụng:

~~~sql
CREATE TABLE LabStudents (
  StudentId UUID NOT NULL DEFAULT (NEW_UUID()),
  DisplayName STRING(100) NOT NULL,
) PRIMARY KEY (StudentId);

CREATE TABLE LabEnrollments (
  StudentId UUID NOT NULL,
  EnrollmentId UUID NOT NULL DEFAULT (NEW_UUID()),
  CourseId STRING(64) NOT NULL,
  Status STRING(24) NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
) PRIMARY KEY (StudentId, EnrollmentId),
  INTERLEAVE IN PARENT LabStudents ON DELETE CASCADE;

CREATE INDEX LabEnrollmentsByCourse
ON LabEnrollments(CourseId, StudentId)
STORING (Status, CreatedAt);
~~~

**Vì sao chọn như vậy?** `StudentId` UUIDv4 tạo các root IDs phân bố, còn `(StudentId, EnrollmentId)` gom enrollment theo học viên. Index `CourseId` cho phép truy vấn enrollment theo khóa học mà không phải đổi PK của bảng child.

### 8.3. Kiểm tra bằng hai query paths

Tạo một student thử và lưu UUID được trả về:

~~~sql
INSERT INTO LabStudents (DisplayName)
VALUES ('Hoc vien demo')
THEN RETURN StudentId;
~~~

Sau đó dùng **tham số `@student_id` kiểu UUID** từ kết quả và một course ID lab trong ứng dụng/Spanner Studio có hỗ trợ bind parameters:

~~~sql
INSERT INTO LabEnrollments
  (StudentId, CourseId, Status, CreatedAt)
VALUES
  (@student_id, 'java-basic-lab', 'ACTIVE', CURRENT_TIMESTAMP())
THEN RETURN EnrollmentId;

-- Đường đọc theo StudentId (prefix primary key).
SELECT EnrollmentId, CourseId, Status
FROM LabEnrollments
WHERE StudentId = @student_id;

-- Đường đọc theo CourseId (có thể sử dụng secondary index).
SELECT StudentId, Status, CreatedAt
FROM LabEnrollments
WHERE CourseId = 'java-basic-lab';
~~~

Không tự chèn UUID trả về dạng string vào SQL bằng nối chuỗi; dùng parameter binding của client. Đọc query plan bằng Spanner Studio hoặc lệnh gcloud read-only:

~~~bash
gcloud spanner databases execute-sql "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID" \
  --sql="SELECT StudentId, Status FROM LabEnrollments WHERE CourseId = 'java-basic-lab'" \
  --query-mode=PLAN
~~~

Quan sát Spanner có chọn index không; với dữ liệu ít, optimizer có thể chọn cách khác mà vẫn đúng. Nếu muốn chỉ rõ index trong **GoogleSQL**, có thể dùng index hint sau khi đã bảo đảm index tồn tại:

~~~sql
SELECT StudentId, Status, CreatedAt
FROM LabEnrollments@{FORCE_INDEX=LabEnrollmentsByCourse}
WHERE CourseId = 'java-basic-lab';
~~~

**Bằng chứng lab:** bảng root dùng UUID, child có prefix cha, truy vấn theo `StudentId` và `CourseId` trả kết quả đúng, query plan được đọc. **Không** khẳng định đã chứng minh chống hotspot bằng một vài INSERT nhỏ.

### 8.4. Dọn tài nguyên được tạo

Sau khi ghi lại kết quả, chỉ xóa **các bảng và index thuộc lab** nếu owner cho phép. Với các quan hệ interleaved, phải xóa **child/index trước parent** theo thứ tự phụ thuộc. Không xóa cả database/instance vì chúng có thể được dùng chung; không chạy `DROP TABLE` trên môi trường chưa được xác minh.

~~~sql
-- Chỉ dành cho đúng database lab sau khi kiểm tra tên/owner.
DROP INDEX LabEnrollmentsByCourse;
DROP TABLE LabEnrollments;
DROP TABLE LabStudents;
~~~

Nếu môi trường không cho phép sửa schema, có thể hoàn thành lab **trên giấy**: giải thích thứ tự khóa, đường đọc và kế hoạch kiểm tra bằng Key Visualizer. Không cần tạo project, instance hoặc database mới để làm phần lý thuyết.

## 9. Bài tập thiết kế và hướng giải

### Bài A — Sự kiện đăng ký tăng theo thời gian

Một bảng nhận **8.000 insert/s** từ nhiều Cloud Run instances:

~~~sql
CREATE TABLE SignupEvents (
  CreatedAt TIMESTAMP NOT NULL,
  EventId STRING(64) NOT NULL,
  UserId STRING(64) NOT NULL,
) PRIMARY KEY (CreatedAt, EventId);
~~~

**Yêu cầu:** giải thích vì sao thêm Spanner nodes có thể chưa giải quyết được p99 write, và đề xuất hai thiết kế thay thế.

**Hướng giải:** `CreatedAt` luôn tăng là cột đầu PK, khiến write dồn vào đầu/cuối keyspace. Phương án 1: dùng `EventId UUIDv4` làm PK, thêm index phục vụ truy vấn cần thiết nhưng **không** tạo index chỉ bắt đầu bằng timestamp tăng dần một cách vô ý. Phương án 2: `(ShardId, CreatedAt DESC, EventId)` với hash phân bố để write vào nhiều ranges; truy vấn gần đây cần fan-out N shards và merge. Dùng Key Visualizer để xác minh, không chỉ thử ở bảng vài trăm hàng.

### Bài B — Multi-tenant bị lệch tải

Một SaaS có **200 tenants** nhưng một tenant tạo **70% lượt ghi**. Đội đề xuất `PRIMARY KEY(TenantId, CreatedAt, EventId)`.

**Yêu cầu:** rủi ro gì còn tồn tại và khi nào nên thêm shard?

**Hướng giải:** hàng của mỗi tenant được gom theo prefix, nhưng tenant “cá voi” vẫn ghi nối tiếp vào key-range theo thời gian. Cân nhắc `(TenantId, ShardId, CreatedAt DESC, EventId)`, chọn shard theo hash ổn định và đo tải; chấp nhận fan-out khi query toàn tenant. Nếu khách hàng chỉ ghi ít hoặc query cần locality cực cao, sharding thêm có thể không đáng.

### Bài C — Truy vấn hai chiều cho enrollment

Ứng dụng cần **(1)** tìm tất cả enrollment của student và **(2)** liệt kê student đăng ký một course. Bạn chọn `PRIMARY KEY(StudentId, EnrollmentId)`.

**Yêu cầu:** cách đáp ứng truy vấn thứ hai mà không làm lại PK là gì?

**Hướng giải:** thêm secondary index có cột đầu `CourseId`, ví dụ `(CourseId, StudentId)`; dùng `STORING` với những cột được truy vấn nhiều để tránh base lookup nếu đáng chi phí. Đo index maintenance cost, không lập index dư thừa. Nếu PK của child dùng interleaving theo parent student, cần cân nhắc lifetime/ON DELETE và lượng dữ liệu theo student.

### Bài D — Natural key và uniqueness

Hệ thống cho đăng ký bằng email. Người thiết kế muốn dùng `Email` làm PK vì con người đọc được, nhưng email có thể **đổi** và cùng địa chỉ có thể xuất hiện trong các tenant độc lập.

**Yêu cầu:** thiết kế khóa và unique constraint như thế nào?

**Hướng giải:** dùng **stable surrogate key** (ví dụ `StudentId UUIDv4`) làm PK; giữ `TenantId`/Email đã được **canonicalize** làm dữ liệu nghiệp vụ, thêm **unique index phù hợp phạm vi tenant** nếu quy định yêu cầu. Canonicalization phải có chính sách rõ, và một `UNIQUE NULL_FILTERED` không bảo đảm unique cho các hàng bị lọc NULL. Thay email không bắt buộc di chuyển tất cả child keys.

### Bài E — Ước lượng write amplification

Một bảng nhận **5.000 inserts/s**. Mỗi INSERT tác động một base row và **ba** secondary indexes, không kể chi phí nội bộ khác.

**Yêu cầu:** ước lượng số lần cập nhật logic đối tượng và nêu vì sao chỉ số này chưa phải số RPC hoặc physical writes.

**Hướng giải:** có thể hình dung **5.000 × (1 + 3) = 20.000** thao tác cập nhật **đối tượng logic/giây** (base + index entries) trong mô hình đơn giản. Nó **không** là số RPC hoặc số write vật lý do batching, transaction, internals, schema/index coverage và implementation khác nhau. Mục đích là thấy mỗi index thêm tạo chi phí duy trì đáng xét.

### Bài F — Hot counter trong một bảng phân bố tốt

Primary key của bảng `Payments` là UUIDv4 và phân phối đều, nhưng mọi transaction đều chạy `UPDATE DailyTotals SET Total = Total + ... WHERE Day = @today`. p99 tăng và transaction abort nhiều.

**Yêu cầu:** tại sao UUIDv4 không cứu được và đề xuất cách cải thiện.

**Hướng giải:** hot row `DailyTotals(@today)` là điểm tranh chấp ghi. Có thể phân rã counters thành nhiều shard, tính tổng khi đọc/định kỳ, hoặc xử lý theo streaming analytics nếu nhất quán tức thì không bắt buộc. Với tiền, phải có ledger và đối soát idempotent; không thay một bộ đếm mạnh bằng số gần đúng khi nghiệp vụ cần chính xác.

## 10. Checklist review schema trước production

| Câu hỏi | Tiêu chí chấp nhận |
| --- | --- |
| PK có ổn định, duy nhất và không lộ danh tính? | Có invariant rõ; không dùng email thay đổi như khóa cha vô tình. |
| Cột đầu khóa có tăng tuần tự ở tải ghi cao không? | Không, hoặc đã có thiết kế giảm hotspot và benchmark chứng minh. |
| Các query thường gặp có prefix key/index phù hợp? | Có query plans và độ trễ đạt SLO trên dữ liệu đại diện. |
| Interleaving/foreign keys có phục vụ quan hệ thật? | Chọn vì locality/integrity, không vì mọi quan hệ đều cần interleave. |
| Tenant nóng hoặc parent quá lớn có bị cô lập không? | Có số liệu phân bố, headroom, phương án shard/fan-out phù hợp. |
| Secondary indexes có gây hot writes hoặc tăng chi phí quá mức? | Đã kiểm tra leading index keys, storage và write amplification. |
| DDL migration/rollback có thể thực hiện an toàn? | Có backfill, data reconciliation, cutover/rollback và người chịu trách nhiệm. |
| Giám sát đã đủ để phát hiện lỗi thiết kế khóa? | Cloud Monitoring, query metrics, Key Visualizer và alert/incident runbook. |
| Bảo mật multi-tenant được kiểm tra ở tầng ứng dụng? | IAM/database roles và authorization; PK prefix không phải security boundary. |

### Tự kiểm tra

1. **Vì sao tăng dần `OrderId` làm nóng một split?** — Inserts liên tục vào cùng đầu một key range, dù Spanner có nhiều máy.
2. **UUIDv4 tốt ở điểm nào?** — Phân tán inserts qua keyspace; không phải cách sắp thứ tự theo thời gian.
3. **Bit-reversed sequence khác sequence tăng thường thế nào?** — Giá trị được đảo bit để tránh ghi dồn ở một đầu; không dùng làm số thứ tự liên tục.
4. **Cột đầu tiên của composite key quan trọng vì sao?** — Nó định hình locality và các range scans/prefix filters, ảnh hưởng phân phối ghi.
5. **Interleaving có giống foreign key không?** — Không; interleaving còn ảnh hưởng physical locality và yêu cầu prefix key cha.
6. **Vì sao một index có thể nóng khi PK không nóng?** — Index có keyspace riêng, ví dụ index dẫn đầu bằng timestamp tăng.
7. **`STORING` có miễn phí không?** — Không; tốn storage và duy trì index khi dữ liệu thay đổi.
8. **Hash sharding có đánh đổi gì?** — Phân tán write nhưng query theo thời gian toàn tenant cần đọc/merge nhiều shard.
9. **Đổi PK của bảng đang có hàng triệu row là việc gì?** — Thường là migration schema + dữ liệu + query contracts, có backfill, cutover và rollback.
10. **Có thể khẳng định chống hotspot từ 20 INSERT trong lab?** — Không; cần load test và Key Visualizer trên phân bố dữ liệu đủ đại diện.

## 11. Tài liệu chính thức

- [Spanner — Schema and data model](https://cloud.google.com/spanner/docs/schema-and-data-model): row ordering, splits, interleaved tables và foreign keys.
- [Spanner — Schema design best practices](https://cloud.google.com/spanner/docs/schema-design): tránh sequential key hotspots, hash sharding và key order.
- [Spanner — Primary key default values](https://cloud.google.com/spanner/docs/primary-key-default-value): UUIDv4, `IDENTITY` và bit-reversed sequence.
- [Spanner — Primary keys overview](https://cloud.google.com/spanner/docs/primary-keys-overview): cách Spanner phân phối key và migration.
- [Spanner — Migrate primary keys](https://cloud.google.com/spanner/docs/migrating-primary-keys): chuyển keys cũ và tránh va chạm với sequence.
- [Spanner — Secondary indexes](https://cloud.google.com/spanner/docs/secondary-indexes): index, `STORING`/`INCLUDE`, null filtering và unique constraints.
- [Spanner — GoogleSQL DDL](https://cloud.google.com/spanner/docs/reference/standard-sql/data-definition-language): cú pháp tạo bảng, PK và interleaving.
- [Spanner — Schema updates](https://cloud.google.com/spanner/docs/schema-updates): thay đổi schema, online index backfill.
- [Spanner — Key Visualizer](https://cloud.google.com/spanner/docs/key-visualizer): heatmap phát hiện hot key ranges.
- [Spanner — Commit timestamps](https://cloud.google.com/spanner/docs/commit-timestamp): timestamp semantics và nguy cơ hotspot.
- [Spanner — Time to live](https://cloud.google.com/spanner/docs/ttl): chính sách xóa dữ liệu không đồng bộ.
- [gcloud spanner databases ddl describe](https://cloud.google.com/sdk/gcloud/reference/spanner/databases/ddl/describe) và [execute-sql](https://cloud.google.com/sdk/gcloud/reference/spanner/databases/execute-sql): kiểm tra DDL và query plans.

**Kết luận:** trong Spanner, primary key vừa xác định **danh tính hàng** vừa ảnh hưởng **cách phân phối dữ liệu và tải ghi**. Dùng UUIDv4/bit-reversed sequence khi cần phân bố inserts, khóa ghép khi cần locality theo nghiệp vụ, và shard khi một nhóm quá nóng; đồng thời kiểm tra secondary indexes, interleaving và transaction hotspots. Lựa chọn chỉ đáng tin khi **query patterns, độ trễ p99, Key Visualizer, chi phí và khả năng migration** đều được thử trên workload đại diện.
