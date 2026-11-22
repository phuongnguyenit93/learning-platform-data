# Thiết kế lược đồ, khóa truy cập và chỉ mục theo mẫu truy vấn

> **Chương:** Kiến trúc cơ sở dữ liệu  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ tới lựa chọn mạng, compute, dữ liệu và mô hình triển khai; cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chuyển luồng nghiệp vụ và mẫu truy vấn thành yêu cầu lưu trữ có thể đo, thay vì bắt đầu từ tên bảng hoặc loại database đang phổ biến.
2. Thiết kế lược đồ quan hệ, khóa chính, khóa ngoại, ràng buộc và kiểu dữ liệu để bảo vệ tính đúng đắn.
3. Phân tích access pattern để chọn partition key, sort key hoặc khóa truy cập phù hợp trong mô hình NoSQL.
4. Thiết kế chỉ mục theo điều kiện lọc, thứ tự sắp xếp, phân trang và tần suất đọc/ghi; nhận biết đánh đổi của index.
5. Dùng execution plan, thống kê và kiểm thử tải để xác nhận thiết kế; tránh tối ưu dựa trên phỏng đoán.
6. Đánh giá ảnh hưởng của thay đổi schema/index lên migration, lock, tính sẵn sàng, bảo mật, chi phí và vận hành cloud.

## 1. Bắt đầu từ cách ứng dụng truy cập dữ liệu

Thiết kế database không chỉ là đặt tên bảng hay chọn kiểu dữ liệu. Một lược đồ phải phục vụ các hành động thực tế: tạo booking, kiểm tra slot còn trống, xem lịch theo ngày, lấy lịch sử của khách, hủy giao dịch, tạo báo cáo. Những hành động đó quyết định dữ liệu được lưu ra sao, khóa nào bảo vệ tính đúng đắn và chỉ mục nào giúp truy vấn không phải quét toàn bộ tập dữ liệu.

Giả sử xây dựng một nền tảng đặt lịch. Các yêu cầu ban đầu:

- Một tài nguyên (bác sĩ/phòng/thiết bị) có các slot theo thời gian.
- Một slot độc quyền chỉ được xác nhận cho tối đa một booking.
- Người dùng xem lịch theo tài nguyên và khoảng ngày.
- Người dùng xem lịch sử booking của mình theo thời gian gần nhất.
- Nhân viên tìm booking theo trạng thái và thời điểm tạo để xử lý.
- Báo cáo tổng hợp theo ngày/trạng thái không được làm chậm giao dịch đặt lịch.

Đây là **query pattern/access pattern**. Mỗi mẫu cần nêu: ai gọi, điều kiện lọc, thứ tự kết quả, lượng bản ghi thường trả, tần suất, độ trễ mong muốn và mức nhất quán. Từ đó mới chọn schema và index.

### 1.1. Lập danh sách access pattern

| ID | Luồng truy cập | Điều kiện chính | Thứ tự/kết quả | Mức độ quan trọng |
|---|---|---|---|---|
| Q1 | Tìm slot của một tài nguyên trong khoảng thời gian | resource_id, start_time range | start_time tăng dần | Cao, interactive |
| Q2 | Xem booking của một khách | customer_id | created_at giảm dần, phân trang | Cao |
| Q3 | Lấy chi tiết booking | booking_id | Một bản ghi | Cao |
| Q4 | Kiểm tra slot đã bị chiếm chưa | resource_id + slot_start | Một kết quả/không có | Rất cao, kiểm soát tranh chấp |
| Q5 | Nhân viên xem booking theo trạng thái | status + created_at range | created_at giảm dần | Trung bình |
| Q6 | Hủy booking | booking_id + actor/permission | Kiểm tra trạng thái rồi đổi trạng thái | Cao |
| Q7 | Báo cáo số booking theo ngày | ngày, trạng thái, có thể theo khu vực | Tổng hợp | Có thể chạy nền |

Danh sách này cần được bổ sung bằng số liệu: Q1 có bao nhiêu lần/giây; khoảng thời gian truy vấn thường là một ngày hay ba tháng; một tài nguyên có bao nhiêu slot; Q2 đọc bao nhiêu trang; dữ liệu có cần phản ánh ngay sau khi ghi không. **Access pattern là đầu vào thiết kế**, không phải tài liệu viết sau khi schema đã hoàn tất.

### 1.2. Định lượng tải và độ trễ

Với mỗi truy vấn, ghi:

- **Read/write ratio:** tỷ lệ đọc so với ghi, có tính retry và tác vụ nền.
- **Cardinality:** số giá trị khác nhau của cột/partition key; độ phân bố đều hay lệch.
- **Selectivity:** tỷ lệ bản ghi phù hợp điều kiện lọc.
- **Result size:** số dòng, kích thước payload, có cần join hay tổng hợp không.
- **Concurrency:** bao nhiêu request chạy đồng thời; có tranh chấp cùng một khóa không?
- **Freshness/consistency:** dữ liệu có thể trễ bao lâu; đọc sau ghi có cần thấy ngay thay đổi không?
- **Growth/retention:** dung lượng tăng theo ngày/tháng, chính sách lưu và xóa.
- **Latency objective:** p95/p99 và điểm đo; timeout và ngân sách thời gian từng tầng.

Ví dụ mục tiêu p95 dưới 200 ms cho Q2 chỉ có ý nghĩa khi xác định vùng người dùng, loại cache, số dòng trả về, mức tải và thời điểm dữ liệu. Không so thời gian một truy vấn trên máy phát triển với SLO production.

## 2. Chọn mô hình dữ liệu và ranh giới thực thể

### 2.1. Mô hình quan hệ cho dữ liệu có liên hệ và giao dịch

Với booking, các thực thể có quan hệ rõ: Customer, Resource, Slot và Booking. Một mô hình quan hệ ban đầu:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ BOOKING : creates
    RESOURCE ||--o{ SLOT : offers
    RESOURCE ||--o{ BOOKING : receives
    SLOT ||--o| BOOKING : reserved_by
    CUSTOMER {
        uuid customer_id PK
        string email
        datetime created_at
    }
    RESOURCE {
        uuid resource_id PK
        string name
        string status
    }
    SLOT {
        uuid slot_id PK
        uuid resource_id FK
        datetime starts_at
        datetime ends_at
    }
    BOOKING {
        uuid booking_id PK
        uuid customer_id FK
        uuid resource_id FK
        uuid slot_id FK
        string status
        datetime created_at
    }
~~~

Đây là mô hình khái niệm đơn giản. Ràng buộc một booking cho mỗi slot cần được hiện thực bằng unique constraint hoặc cơ chế transaction/locking phù hợp; ký hiệu quan hệ trên sơ đồ không tự thực thi ràng buộc.

Các nguyên tắc quan trọng:

- Mỗi thực thể có định danh ổn định, khóa chính không phụ thuộc vào thuộc tính có thể đổi như email hoặc tên.
- Dùng foreign key để biểu diễn quan hệ và bảo vệ tham chiếu khi chính sách nghiệp vụ yêu cầu.
- Dùng NOT NULL, CHECK, UNIQUE và kiểu dữ liệu phù hợp để chuyển bất biến nghiệp vụ thành ràng buộc tại database.
- Phân biệt dữ liệu chuẩn với dữ liệu dẫn xuất/cache/search projection.
- Xác định vòng đời dữ liệu và chủ sở hữu; tránh tạo bảng có nhiều nhóm cùng ghi mà không có quy tắc.

### 2.2. Chuẩn hóa và phi chuẩn hóa

**Chuẩn hóa** giảm trùng lặp và bất thường khi cập nhật. Ví dụ, thông tin khách hàng không nên được sao chép thành nhiều bản ghi nguồn sự thật nếu các màn hình cần cùng một địa chỉ hiện tại. Tuy nhiên, một số truy vấn đọc nhiều có thể cần snapshot hoặc projection để phục vụ lịch sử giao dịch, tìm kiếm hoặc phân tích.

| Lựa chọn | Lợi ích | Đánh đổi |
|---|---|---|
| Chuẩn hóa Customer, Resource, Booking riêng | Cập nhật dữ liệu gốc nhất quán, ít lặp | Truy vấn có thể cần join |
| Lưu snapshot tên tại thời điểm booking | Giữ ý nghĩa lịch sử dù tên thay đổi | Lặp dữ liệu, phải định nghĩa field nào là snapshot |
| Read model tổng hợp riêng | Đọc nhanh, tối ưu theo màn hình | Cần cập nhật đồng bộ/bất đồng bộ, eventual consistency |
| Denormalize nhiều bản sao | Giảm join ở một số truy vấn | Tăng rủi ro cập nhật lệch và chi phí ghi |

Không phi chuẩn hóa chỉ vì join chậm. Hãy đo query, index, volume và latency trước. Nếu dùng snapshot, đặt tên rõ như resource_name_at_booking thay vì nhầm với tên hiện tại của Resource.

## 3. Thiết kế khóa: định danh, toàn vẹn và cạnh tranh

### 3.1. Khóa chính (primary key)

Primary key định danh duy nhất mỗi hàng và không null. Các lựa chọn:

- **Surrogate key:** UUID hoặc số tăng dần do hệ thống tạo; ổn định dù thuộc tính nghiệp vụ đổi.
- **Natural key:** thuộc tính nghiệp vụ tự nhiên và ổn định; cần đánh giá thay đổi, bảo mật và phạm vi duy nhất.
- **Composite key:** nhiều cột cùng tạo thành định danh, phù hợp khi tính duy nhất thuộc về tổ hợp, ví dụ (resource_id, starts_at).

| Loại khóa | Ưu điểm | Cần cân nhắc |
|---|---|---|
| Số tăng dần | Nhỏ, locality của index tốt ở một số hệ thống | Có thể lộ quy mô, hotspot khi phân phối ghi; cần sequence |
| UUID ngẫu nhiên | Sinh phân tán, giảm lộ thứ tự tạo | Rộng, index có thể phân mảnh hơn; storage/cache footprint lớn |
| UUID/time-ordered ID | Có thể cải thiện locality theo thời gian | Thứ tự không nhất thiết phản ánh transaction commit |
| Composite key | Thể hiện ràng buộc nghiệp vụ | Khóa dài lan sang foreign key/index, khó đổi nếu thành phần đổi |

Không có khóa tốt cho mọi workload. Chọn theo quy mô, phân bố ghi, khả năng sinh ID phân tán, kích thước index, mức độ cần che giấu và ràng buộc tích hợp.

### 3.2. Khóa ngoại và ràng buộc duy nhất

Ví dụ DDL theo phong cách PostgreSQL:

~~~sql
CREATE TABLE resource (
    resource_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE customer (
    customer_id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_customer_email UNIQUE (email)
);

CREATE TABLE slot (
    slot_id UUID PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resource(resource_id),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_slot_time CHECK (ends_at > starts_at),
    CONSTRAINT uq_resource_slot UNIQUE (resource_id, starts_at)
);

CREATE TABLE booking (
    booking_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES customer(customer_id),
    resource_id UUID NOT NULL REFERENCES resource(resource_id),
    slot_id UUID NOT NULL REFERENCES slot(slot_id),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong ví dụ, unique (resource_id, starts_at) bảo đảm một mốc bắt đầu duy nhất cho một resource trong bảng Slot; foreign key booking.slot_id chưa bảo đảm chỉ có một booking trên một slot. Nếu chỉ một booking đang hoạt động được chiếm slot, PostgreSQL có thể dùng partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_booking_active_slot
ON booking (slot_id)
WHERE status IN ('PENDING', 'CONFIRMED');
~~~

Đây là ví dụ phụ thuộc hệ quản trị. Nếu cần lưu nhiều lần đặt/hủy lịch sử, mô hình phải xác định trạng thái nào giữ slot, thời điểm giải phóng và cách xử lý hai transaction đồng thời.

### 3.3. Không dựa vào kiểm tra ứng dụng đơn lẻ để chống tranh chấp

Một lỗi phổ biến:

~~~text
Request A: SELECT slot -> thấy còn trống
Request B: SELECT slot -> thấy còn trống
Request A: INSERT booking
Request B: INSERT booking
~~~

Hai request có thể cùng quan sát trạng thái trống trước khi bất kỳ request nào ghi. Để bảo vệ invariant, database cần constraint, transaction với isolation/locking thích hợp hoặc conditional write/optimistic concurrency ở nơi ghi chuẩn.

Unique index sẽ từ chối insert thứ hai trên cùng slot đang bị chiếm. Ứng dụng cần chuyển lỗi constraint thành lỗi nghiệp vụ như SLOT_UNAVAILABLE, không để lộ chi tiết SQL. Nếu có quy trình giữ chỗ, có thể dùng trạng thái PENDING cùng expiration/lease và job giải phóng, nhưng việc hết hạn phải được kiểm soát nhất quán trong transaction.

**Idempotency key** bảo vệ một ý định request được gửi lại; unique constraint bảo vệ invariant nghiệp vụ giữa nhiều ý định khác nhau. Hai cơ chế bổ trợ nhau, không thay thế nhau.

### 3.4. Khóa lạc quan và khóa bi quan

| Cơ chế | Hoạt động | Phù hợp khi |
|---|---|---|
| **Optimistic concurrency** | Đọc version, ghi với điều kiện version chưa đổi; nếu không thì conflict | Xung đột hiếm, muốn giảm lock giữ lâu |
| **Pessimistic locking** | Khóa hàng/tài nguyên trong transaction để ngăn cập nhật cạnh tranh | Xung đột thường xuyên, cần tuần tự hóa |
| **Unique/conditional constraint** | Database chỉ chấp nhận trạng thái không vi phạm invariant | Có thể biểu diễn quy tắc duy nhất/điều kiện tại nơi ghi |

Ví dụ optimistic update:

~~~sql
UPDATE booking
SET status = 'CANCELLED',
    version = version + 1
WHERE booking_id = :booking_id
  AND version = :expected_version
  AND status = 'CONFIRMED';
~~~

Nếu số dòng cập nhật bằng 0, trạng thái đã thay đổi hoặc booking không còn ở điều kiện mong đợi; ứng dụng cần đọc lại và quyết định.

Với PostgreSQL, SELECT FOR UPDATE có thể khóa hàng trong transaction. Khóa bi quan làm giảm concurrency nếu giữ quá lâu; tránh gọi API bên ngoài hoặc chờ người dùng trong khi transaction giữ lock. Cần quy định thứ tự lock để giảm deadlock, transaction ngắn và retry deadlock/serialization failure có giới hạn khi thao tác an toàn.

## 4. Thiết kế khóa truy cập trong NoSQL

### 4.1. Query-first và partition key

Trong database key-value/document phân tán, cách truy vấn có thể bị giới hạn bởi partition key, sort key và API query được hỗ trợ. Vì vậy cần liệt kê access pattern trước khi chọn partition.

Partition key tốt thường:

- Phân bố đều lưu lượng và dữ liệu; tránh một giá trị quá nóng.
- Cho phép query đúng phạm vi mà không scan toàn bộ collection/table.
- Giữ nhóm dữ liệu cần đọc cùng nhau trong một truy vấn phù hợp.
- Ổn định và có cardinality/phân bố phù hợp tăng trưởng dự báo.

Sort key thường hỗ trợ lọc theo thứ tự hoặc khoảng giá trị trong cùng partition, ví dụ thời gian tạo, loại bản ghi hoặc version. Composite key có thể kết hợp loại thực thể và thuộc tính sắp xếp, nhưng cần cân nhắc encoding, range query và tính duy nhất.

### 4.2. Ví dụ access pattern với partition/sort key

Với một bảng NoSQL giả định hỗ trợ partition key và sort key:

| Access pattern | PK | SK | Kết quả |
|---|---|---|---|
| Lấy booking của khách, mới nhất trước | CUSTOMER#id | BOOKING#createdAt#bookingId | Query theo PK, sort giảm dần |
| Lấy chi tiết booking | BOOKING#id | META | Query/get theo khóa cụ thể |
| Lấy slot của resource theo thời gian | RESOURCE#id | SLOT#startAt#slotId | Query PK + sort key range |
| Lấy booking theo trạng thái | Có thể cần index phụ | STATUS#status#createdAt#id | Query theo index nếu có |

Đây là mô hình logic minh họa, không phải schema chung cho mọi NoSQL. Cần xem API query, kích thước item, partition capacity và index semantics của dịch vụ được chọn.

### 4.3. Hot partition và phân bố khóa

Nếu tất cả booking được ghi vào partition key STATUS#PENDING, lưu lượng có thể tập trung vào một partition. Tăng tổng provisioned capacity không nhất thiết giải quyết được một key nóng.

Giải pháp có thể gồm:

- Dùng khóa có cardinality cao hơn và phân bố đều hơn, ví dụ tenant/resource/customer tùy access pattern.
- Dùng write sharding với số shard hoặc bucket được thiết kế rõ, rồi tổng hợp khi đọc.
- Tránh timestamp hiện tại làm partition key duy nhất nếu mọi writer đổ vào cùng một giá trị.
- Theo dõi throttling, consumed capacity, partition skew hoặc metric tương đương của nhà cung cấp.

Write sharding làm truy vấn tổng hợp phức tạp hơn vì phải đọc nhiều shard; chỉ áp dụng khi số liệu cho thấy hot partition và có kế hoạch fan-out/read aggregation.

### 4.4. Secondary index và query bổ sung

Một global secondary index (GSI) hoặc index phụ tương tự cho phép truy vấn theo khóa khác. Ví dụ bảng chính partition theo customer, nhưng operations team cần tìm booking theo trạng thái. Có thể tạo index với partition key status và sort key createdAt#bookingId.

Đánh đổi:

- Index phụ tăng storage và chi phí ghi/cập nhật.
- Một số hệ thống cập nhật index bất đồng bộ; query có thể eventual consistency.
- Key cardinality thấp như status có thể tạo phân phối lệch/hot partition.
- Một index không nhất thiết phục vụ mọi bộ lọc kết hợp; có thể cần thêm index hoặc query service riêng.
- Cần xác định cách backfill index khi tạo mới và tác động tới throughput.

Không tạo index cho mọi thuộc tính chỉ để “sau này có thể cần”. Hãy ghi access pattern, volume, tần suất và SLA mà index phục vụ.

## 5. Thiết kế chỉ mục trong cơ sở dữ liệu quan hệ

### 5.1. Index giúp truy vấn tránh đọc quá nhiều dữ liệu

Index là cấu trúc phụ cho phép database tìm các hàng phù hợp mà không cần quét toàn bộ bảng trong nhiều trường hợp. Với B-tree phổ biến, các giá trị được duy trì theo thứ tự để hỗ trợ equality, range và ordering. Hệ quản trị có thể chọn index scan, index-only scan, bitmap scan hoặc sequential scan tùy kế hoạch thực thi.

Ví dụ Q2: lấy booking của một customer mới nhất:

~~~sql
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 20;
~~~

Index gợi ý:

~~~sql
CREATE INDEX ix_booking_customer_created
ON booking (customer_id, created_at DESC);
~~~

Thứ tự cột quan trọng: customer_id được lọc equality trước, created_at hỗ trợ ordering trong phạm vi customer. Chỉ mục có thể giảm sort và đọc ít hàng hơn, nhưng phải kiểm tra plan thực tế.

### 5.2. Leftmost prefix và thứ tự cột composite index

Với B-tree composite index (customer_id, status, created_at), các truy vấn thường có lợi khi lọc theo customer_id hoặc customer_id kết hợp status, rồi xét created_at trong phạm vi đó. Truy vấn chỉ lọc status có thể không tận dụng index này hiệu quả tùy hệ quản trị và thống kê, do thứ tự khóa bắt đầu bằng customer_id.

| Truy vấn | Index có khả năng phù hợp |
|---|---|
| WHERE customer_id = ? | (customer_id) hoặc composite bắt đầu bằng customer_id |
| WHERE customer_id = ? AND status = ? | (customer_id, status) |
| WHERE customer_id = ? ORDER BY created_at DESC | (customer_id, created_at DESC) |
| WHERE status = ? ORDER BY created_at DESC | (status, created_at DESC) nếu workload cần |
| WHERE created_at >= ? trên toàn bảng | Index bắt đầu bằng created_at hoặc partition/strategy phù hợp |

Không có quy tắc “cột có selectivity cao luôn đứng đầu” áp dụng tuyệt đối. Phải xét equality predicates, range predicates, thứ tự sort, prefix thực sự được truy vấn, khả năng covering, kích thước index và workload tổng thể. Composite index tốt cho một query có thể làm query khác tệ hơn.

### 5.3. Range, sort và phân trang

Với Q1 tìm slot:

~~~sql
SELECT slot_id, starts_at, ends_at
FROM slot
WHERE resource_id = :resource_id
  AND starts_at >= :from_time
  AND starts_at < :to_time
ORDER BY starts_at ASC
LIMIT 100;
~~~

Index:

~~~sql
CREATE INDEX ix_slot_resource_start
ON slot (resource_id, starts_at);
~~~

Equality theo resource_id đứng trước range theo starts_at. Khoảng thời gian dạng nửa mở [from, to) tránh trùng ở biên khi phân trang hoặc chia ngày; timezone và quy ước thời điểm phải thống nhất.

**OFFSET pagination**

~~~sql
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = :customer_id
ORDER BY created_at DESC, booking_id DESC
LIMIT 20 OFFSET 10000;
~~~

OFFSET lớn có thể tốn chi phí đọc/bỏ qua nhiều hàng; dữ liệu mới chèn giữa các trang cũng có thể làm kết quả nhảy hoặc trùng. **Keyset/seek pagination** dùng giá trị của hàng cuối trang trước:

~~~sql
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = :customer_id
  AND (created_at, booking_id) < (:last_created_at, :last_booking_id)
ORDER BY created_at DESC, booking_id DESC
LIMIT 20;
~~~

Index phù hợp:

~~~sql
CREATE INDEX ix_booking_customer_created_id
ON booking (customer_id, created_at DESC, booking_id DESC);
~~~

Keyset pagination cần khóa sắp xếp ổn định và đủ tie-breaker; created_at một mình có thể trùng. Nếu dữ liệu thay đổi trong lúc phân trang, cần quyết định snapshot/consistency mong muốn.

### 5.4. Partial, covering và expression index

Một số hệ quản trị hỗ trợ index chuyên biệt:

~~~sql
CREATE UNIQUE INDEX uq_booking_active_slot
ON booking (slot_id)
WHERE status IN ('PENDING', 'CONFIRMED');

CREATE INDEX ix_customer_email_lower
ON customer (LOWER(email));
~~~

Partial index giảm số entry nếu chỉ một tập hàng quan trọng; expression index có thể hỗ trợ predicate tương ứng. **Covering index** (ví dụ PostgreSQL INCLUDE) giữ thêm cột để trả kết quả mà không cần đọc heap trong một số điều kiện, nhưng tăng dung lượng và write cost:

~~~sql
CREATE INDEX ix_booking_customer_created_cover
ON booking (customer_id, created_at DESC)
INCLUDE (booking_id, status);
~~~

Không lặp index nếu đã có index tương đương hoặc index unique đáp ứng truy vấn. DDL và lợi ích phụ thuộc database/version, cấu hình, statistics và mức cập nhật dữ liệu.

### 5.5. Selectivity và vì sao index không phải lúc nào cũng được dùng

Index có lợi khi giảm đáng kể lượng dữ liệu cần đọc. Nếu truy vấn lấy 80% bảng, sequential scan có thể rẻ hơn việc đọc index rồi truy cập từng hàng. Index trên cột boolean hoặc trạng thái ít giá trị có thể kém chọn lọc; vẫn có ích khi kết hợp với thời gian, partition hoặc partial predicate.

Planner xem xét:

- Số hàng và số trang của bảng/index.
- Phân bố dữ liệu và thống kê đã được cập nhật hay chưa.
- Selectivity thực của predicate và tương quan giữa các cột.
- Số hàng sẽ trả, sort/hash/join cần thực hiện.
- Cache hit, I/O, parallelism và chi phí random/sequential access.
- Parameter values; kế hoạch tốt cho tenant lớn có thể tệ cho tenant nhỏ.

Không ép planner dùng index bằng hint trước khi hiểu plan. Hãy kiểm tra query, kiểu dữ liệu/cast và thống kê. Hint có thể cần trong một số nền tảng nhưng tạo thêm coupling vào phiên bản và cấu hình.

## 6. Đọc execution plan và đo hiệu năng

### 6.1. EXPLAIN là bằng chứng, không phải phỏng đoán

Trong PostgreSQL, có thể dùng:

~~~sql
EXPLAIN
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = '00000000-0000-0000-0000-000000000042'
ORDER BY created_at DESC
LIMIT 20;
~~~

Khi có môi trường an toàn và query không gây side effect, EXPLAIN (ANALYZE, BUFFERS) cho thời gian và số hàng thực tế:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT booking_id, status, created_at
FROM booking
WHERE customer_id = '00000000-0000-0000-0000-000000000042'
ORDER BY created_at DESC
LIMIT 20;
~~~

ANALYZE **thực sự chạy câu truy vấn**; với UPDATE/DELETE hoặc function có side effect, chỉ chạy trong transaction có kiểm soát và rollback khi thích hợp, hoặc kiểm tra plan không thực thi. Một plan thực tế cần xem:

| Thành phần plan | Cần xem gì? |
|---|---|
| Seq Scan / Index Scan / Index Only Scan | Bảng bị quét lớn? Index có được dùng? Heap fetch nhiều? |
| Estimated vs actual rows | Ước lượng sai lệch lớn không? |
| Rows Removed by Filter | Có đọc nhiều hàng rồi loại bỏ không? |
| Sort / Hash / Aggregate | Có sort/hash lớn, spill ra disk hoặc thiếu memory không? |
| Nested Loop / Hash Join / Merge Join | Join strategy có phù hợp kích thước/cardinality? |
| Buffers hit/read/temp | Đọc từ cache, storage hay ghi file tạm? |
| Planning/Execution time | Thời gian planner và thực thi; đo lặp theo tải |

Không đánh giá qua một lần chạy. Warm cache, concurrent workload, vacuum/analyze, parameter values và latency storage làm kết quả khác đáng kể.

### 6.2. Trước và sau khi có index

Giả sử Q2 trả 20 booking nhưng bảng có hàng chục triệu dòng:

~~~text
Trước index:
  Seq Scan toàn bảng
  Filter customer_id
  Sort created_at DESC
  Limit 20

Sau index khi planner thấy có lợi:
  Index Scan theo customer_id, created_at DESC
  Limit 20
~~~

Đây là sơ đồ logic minh họa, không phải output plan thực. Sau khi tạo index, kiểm tra actual rows, buffers, latency p95/p99 dưới concurrency, tốc độ ghi và chi phí index. Nếu không cải thiện, xem lại selectivity, thống kê, số dòng trả và cache trước khi thêm index khác.

### 6.3. Đo từ góc nhìn ứng dụng

Database query latency không bằng API latency. Request còn đi qua network, connection pool, serialization, application logic và có thể nhiều query. Thu thập:

- p50/p95/p99 của query quan trọng và endpoint chứa query đó.
- Tỷ lệ lỗi timeout, deadlock, serialization failure và retry.
- Số connection active/idle/waiting, thời gian acquire connection.
- Query throughput, rows read/returned, lock wait và replication lag.
- CPU, memory, IOPS, storage throughput, cache hit và temp spill.
- Chi phí theo query/workload nếu nền tảng cung cấp hoặc có thể phân bổ.

Ẩn hoặc hash giá trị có PII trong query log; giới hạn sampling và retention để telemetry không tự tạo rủi ro dữ liệu/chi phí.

## 7. Index, write cost và vận hành cloud

### 7.1. Mỗi index là một cấu trúc cần duy trì

Khi insert/update/delete, database phải cập nhật các index liên quan. Index nhiều hoặc rộng có thể:

- Tăng dung lượng storage và backup.
- Tăng write amplification, CPU, I/O và transaction time.
- Làm migration và replica catch-up chậm hơn.
- Tăng lock/resource contention khi tạo hoặc rebuild tùy cơ chế.
- Tăng chi phí managed database và thời gian phục hồi.

| Index | Query phục vụ | Độ quan trọng | Bằng chứng giữ lại |
|---|---|---|---|
| uq_booking_active_slot | Chống đặt trùng slot | Rất cao, correctness | Invariant và concurrency test |
| ix_booking_customer_created_id | Lịch sử của khách | Cao | p95 và plan Q2 |
| ix_slot_resource_start | Lịch slot theo resource | Cao | Plan Q1, latency |
| ix_booking_status_created | Quản trị theo trạng thái | Theo nhu cầu | Query usage và write cost |

Index không có truy vấn được chứng minh, không bảo vệ invariant và ít được dùng cần được xem xét loại bỏ. Việc xóa index cũng cần kiểm tra workload; index hiếm dùng có thể thiết yếu cho quy trình vận hành.

### 7.2. Tạo index online/concurrently

Trên production, tạo index có thể giữ lock hoặc tăng I/O tùy hệ quản trị. PostgreSQL có CREATE INDEX CONCURRENTLY để giảm mức chặn ghi so với cách tạo thông thường trong nhiều trường hợp, nhưng có giới hạn và chi phí; thao tác không chạy trong transaction block thông thường và có thể để lại invalid index nếu thất bại. Hệ quản trị khác có online index build/options khác.

Trước migration:

1. Kiểm tra dung lượng trống, IOPS, CPU, replica lag và load baseline.
2. Xác định lệnh có lock gì, có chạy đồng thời với ghi không, có được chạy trong transaction không.
3. Thử trên staging có volume và phân bố dữ liệu gần production.
4. Có timeout, lịch, owner, theo dõi progress và kế hoạch xử lý thất bại.
5. Kiểm tra index validity, query plan và write latency sau khi hoàn tất.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX CONCURRENTLY ix_booking_customer_created
ON booking (customer_id, created_at DESC);
~~~

Lệnh này chỉ là ví dụ cho PostgreSQL; đọc tài liệu đúng version trước khi dùng. “Online” không có nghĩa không tốn tài nguyên hoặc không ảnh hưởng latency.

### 7.3. Schema evolution: expand, migrate, contract

Thay đổi schema khi ứng dụng nhiều phiên bản cùng chạy phải giữ tương thích:

1. **Expand:** thêm cột/bảng/index mới, thường cho phép null/default phù hợp; code cũ vẫn hoạt động.
2. **Deploy compatible code:** code mới có thể đọc/ghi định dạng mới, xử lý dữ liệu cũ.
3. **Backfill/migrate:** chuyển dữ liệu theo batch, idempotent, có checkpoint và theo dõi tiến độ.
4. **Switch:** chuyển đọc sang cấu trúc mới sau khi xác nhận completeness.
5. **Contract:** bỏ cấu trúc cũ khi không còn consumer/code cũ và hết cửa sổ rollback.

Tránh thêm cột NOT NULL hoặc thay đổi khóa lớn theo cách gây scan/lock dài không kiểm soát. Với cột cần backfill, chia lô, giới hạn tốc độ và quan sát replication lag. Rollback application không tự hoàn tác dữ liệu đã chuyển đổi.

## 8. Bảo mật lược đồ, khóa và truy vấn

### 8.1. Phân quyền theo chức năng

- Tài khoản runtime chỉ có quyền cần cho thao tác của nó; không dùng superuser/admin trong connection string production.
- Read-only/reporting workload nên dùng vai trò chỉ đọc hoặc replica phù hợp.
- Migration account riêng có quyền DDL, chỉ sử dụng trong pipeline được bảo vệ.
- Quyền truy cập theo tenant/record phải được thực thi ở tầng dữ liệu hoặc service bằng cơ chế đáng tin cậy; không dựa vào client truyền customer_id.
- Dùng secret manager/workload identity khi có thể, xoay credential, mã hóa kết nối và lưu trữ.

Index không phải ranh giới bảo mật. Một index chứa email, số điện thoại hoặc field nhạy cảm vẫn thuộc phạm vi dữ liệu đó và phải được bảo vệ qua IAM, backup, log, export và retention.

### 8.2. Tránh SQL injection và truy vấn động nguy hiểm

Luôn bind parameter:

~~~sql
SELECT booking_id, status
FROM booking
WHERE customer_id = :authenticated_customer_id
  AND created_at >= :from_time;
~~~

Không nối chuỗi input thành SQL. Tên bảng/cột hoặc direction sort thường không thể bind như giá trị; nếu cần dynamic query, map từ danh sách allowlist cố định. Phân quyền dựa trên identity đã xác thực, không tin customer_id do client gửi như bằng chứng sở hữu.

### 8.3. Data type, timezone và null semantics

Chọn kiểu dữ liệu đúng giảm bug khó phát hiện:

- Thời điểm tuyệt đối nên lưu theo kiểu timestamp có timezone/UTC phù hợp database; hiển thị theo timezone người dùng. Không lưu thời gian địa phương mơ hồ khi cần so sánh liên vùng.
- Tiền dùng decimal/numeric hoặc đơn vị nguyên nhỏ nhất theo quy ước tiền tệ; tránh floating point cho phép tính tài chính chính xác.
- Trạng thái có danh sách giá trị rõ và quy trình chuyển đổi; cân nhắc enum/code table và khả năng thêm trạng thái.
- NULL biểu thị chưa biết/không có giá trị theo semantics SQL, không đồng nghĩa chuỗi rỗng hoặc số 0.
- Độ dài, collation, normalization và uniqueness email/tên phải phù hợp quy tắc nghiệp vụ và ngôn ngữ.

## 9. Partitioning, sharding và chiến lược lưu trữ lớn

Khi bảng tăng rất lớn, index không phải giải pháp duy nhất. Partitioning chia bảng thành các phần theo range/list/hash trong cùng database logic hoặc cluster tùy nền tảng; có thể hỗ trợ pruning, retention và quản trị.

### 9.1. Partition theo thời gian

Ví dụ bảng audit/event tăng theo ngày có thể partition theo tháng:

~~~sql
CREATE TABLE booking_audit (
    audit_id UUID NOT NULL,
    booking_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    action TEXT NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE booking_audit_2026_11
PARTITION OF booking_audit
FOR VALUES FROM ('2026-11-01 00:00:00+00')
TO ('2026-12-01 00:00:00+00');
~~~

Partition pruning hữu ích nếu query có predicate theo occurred_at; truy vấn không chỉ rõ partition key có thể vẫn phải xét nhiều partition. Khóa unique/primary key trên bảng partitioned có thể cần bao gồm partition key tùy database. Phải hiểu giới hạn DDL và foreign key của đúng hệ quản trị.

Partitioning hỗ trợ detach/drop partition cũ nhanh hơn xóa từng hàng và áp retention. Nhưng quá nhiều partition làm tăng catalog/planning overhead; quá ít làm tăng chi phí vacuum/maintenance và thao tác dữ liệu. Chu kỳ và số lượng cần dựa trên volume/retention.

### 9.2. Partitioning không đồng nghĩa sharding

| Cơ chế | Phạm vi | Mục tiêu | Độ phức tạp |
|---|---|---|---|
| Table partitioning | Trong database/cluster theo cơ chế engine | Pruning, retention, quản trị bảng lớn | Query phải tương thích partition key |
| Sharding | Phân dữ liệu trên nhiều node/database | Scale storage/throughput vượt một node | Routing, transaction phân tán, rebalance, backup/restore |
| Read replica | Bản sao phục vụ đọc | Tăng read capacity, tách workload | Replication lag, consistency và failover |
| Archive/object storage | Dữ liệu ít truy cập chuyển lớp lưu trữ | Giảm chi phí lưu trữ nóng | Khôi phục chậm hơn, query khác và lifecycle |

Chỉ sharding khi đã chứng minh bottleneck ở một node sau khi tối ưu schema/query/index và tận dụng khả năng scale dịch vụ. Chọn shard key có cardinality/phân bố tốt, hỗ trợ access pattern quan trọng và hạn chế cross-shard query/transaction.

## 10. Quy trình thiết kế từ access pattern tới schema/index

1. **Thu thập workload:** liệt kê query/command, caller, điều kiện, sort, result size, read/write ratio, concurrency và SLO.
2. **Xác định invariant:** duy nhất, tham chiếu, trạng thái hợp lệ, transaction boundary, retention và bảo mật.
3. **Chọn model dữ liệu:** relational/document/key-value/wide-column theo quan hệ, transaction, truy vấn và giới hạn hệ quản trị.
4. **Chọn primary/partition key:** phù hợp định danh, locality, phân phối tải và khả năng mở rộng.
5. **Lập index tối thiểu:** map từng index với một hoặc nhiều query; ưu tiên equality/range/order và quyền unique.
6. **Seed dữ liệu đại diện:** kích thước, phân bố, skew, null, dữ liệu cũ và tenant lớn; không chỉ vài chục hàng mẫu.
7. **Đo execution plan và tải:** actual rows, buffers, latency p95/p99, throughput, lock, CPU/I/O, replication lag và chi phí.
8. **Thử migration:** kiểm tra lock, backfill, online index build, rollback và tương thích phiên bản.
9. **Đưa vào vận hành:** dashboard, alert, owner query/index, rationale và lịch review khi workload thay đổi.

### 10.1. Ma trận truy vấn ↔ chỉ mục

| Query ID | Predicate | Sort/range | Index/key đề xuất | Kiểm chứng |
|---|---|---|---|---|
| Q1 slot theo resource/time | resource_id = ? | starts_at range, ASC | (resource_id, starts_at) | EXPLAIN, p95 theo khoảng ngày |
| Q2 booking của customer | customer_id = ? | created_at DESC, booking_id DESC | (customer_id, created_at DESC, booking_id DESC) | Keyset pagination, actual rows |
| Q3 chi tiết booking | booking_id = ? | Không | PK booking_id | Lookup latency |
| Q4 chiếm slot | slot_id = ?, trạng thái active | Unique | Unique/partial index theo invariant | Concurrency test |
| Q5 quản trị theo trạng thái | status = ? | created_at DESC | (status, created_at DESC) nếu workload đủ lớn | Query usage và write cost |
| Q7 tổng hợp theo ngày | Range theo ngày, group status | Aggregate | Partition/summary/read model tùy volume | Batch latency và ảnh hưởng OLTP |

Một query có thể được hỗ trợ bởi nhiều index, nhưng tổng số index phải được đánh giá theo write cost. Nếu Q5 hiếm dùng, có thể chọn scan có giới hạn hoặc chạy trên read replica/warehouse thay vì thêm index trên bảng giao dịch.

### 10.2. Ghi rationale khi thêm index

~~~text
Index: ix_booking_customer_created_id
Query phục vụ: Q2 - lịch sử booking của khách
Predicate: customer_id = ?
Order: created_at DESC, booking_id DESC
Mục tiêu: p95 dưới 200 ms tại tải đã xác định
Lợi ích quan sát: giảm sort và số row đọc theo customer
Chi phí: tăng storage và index maintenance trên INSERT
Đánh giá: actual plan + load test trước/sau + write latency
Owner: Booking data owner
Xem xét lại: khi Q2 traffic, schema hoặc retention thay đổi
~~~

Rationale giúp người vận hành biết index tồn tại để giải quyết vấn đề nào và tránh xóa/nhân đôi index tùy tiện.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Thiết kế schema trước khi liệt kê query | Index phải vá nhiều lần, truy vấn không phù hợp | Ghi access pattern và SLO trước |
| Chỉ dựa vào kiểm tra còn chỗ ở application | Race condition và đặt trùng | Constraint/transaction tại database chuẩn |
| Dùng email hoặc field có thể đổi làm primary key | Đổi thông tin kéo theo sửa tham chiếu diện rộng | Surrogate key hoặc khóa ổn định |
| Composite index sai thứ tự | Truy vấn không dùng được prefix hữu ích hoặc vẫn sort | Map equality/range/order thực tế |
| Index mọi cột “để cho nhanh” | Write chậm, storage/backup tăng | Chỉ tạo theo query và invariant có bằng chứng |
| Index boolean đơn lẻ | Selectivity thấp, planner có thể không dùng | Kết hợp predicate/partial index |
| OFFSET rất lớn | Đọc/bỏ qua nhiều hàng, trang không ổn định | Keyset pagination với tie-breaker |
| Partition key có hot value | Throttling/độ trễ dù tổng capacity còn | Chọn key phân bố đều, sharding khi đo thấy cần |
| Denormalize không có cập nhật đồng bộ | Dữ liệu lệch giữa bản sao | Source of truth, outbox/reconciliation |
| Dùng replica để kiểm tra invariant cần mới nhất | Đọc dữ liệu trễ dẫn đến quyết định sai | Consistency phù hợp từ primary |
| Tạo index lớn trong peak | CPU/I/O/lock và replica lag tăng | Lập kế hoạch online/concurrent, giám sát và thử trước |
| Không cập nhật statistics/đọc plan | Planner chọn sai kế hoạch | Analyze/statistics và kiểm tra actual rows |

## 12. Bài thực hành: thiết kế dữ liệu và chỉ mục cho dịch vụ đặt lịch

**Tình huống:** Dịch vụ có Customer, Resource, Slot và Booking. Lưu lượng đọc lịch slot cao hơn ghi booking khoảng 15 lần; giờ cao điểm có nhiều khách cùng tranh chấp một slot. Nhân viên tra cứu booking theo trạng thái/ngày tạo; khách xem lịch sử theo trang. Dữ liệu tăng đều hàng tháng. Mục tiêu p95 API tra cứu dưới 200 ms ở tải thiết kế là giả định để lập kế hoạch, chưa phải cam kết đã kiểm chứng.

Hãy hoàn thành các đầu ra:

1. **Access pattern:** liệt kê ít nhất 6 truy vấn, caller, predicate, sort, số dòng, tần suất và consistency.
2. **ERD và DDL:** định nghĩa primary key, foreign key, NOT NULL, CHECK, unique/invariant cho một slot chỉ được đặt một lần.
3. **Concurrency:** mô tả hai request đồng thời cùng slot; chứng minh constraint/transaction chặn booking trùng; phân biệt idempotency key với unique key.
4. **Index matrix:** thiết kế index cho lịch resource/time, lịch sử customer, chi tiết booking, trạng thái quản trị; giải thích thứ tự cột và write cost.
5. **Pagination:** viết truy vấn keyset cho lịch sử booking theo created_at và booking_id.
6. **NoSQL alternative:** nếu dùng key-value/document DB, đề xuất partition/sort key và index bổ sung; nêu nguy cơ hot partition.
7. **Performance:** tạo dữ liệu thử có phân bố/skew gần thực tế; chạy EXPLAIN/ANALYZE hoặc công cụ tương đương; ghi actual rows, latency, buffers, query throughput và write cost.
8. **Schema evolution:** thêm field hoặc index trong khi nhiều phiên bản API cùng chạy; mô tả expand/backfill/switch/contract và rollback.
9. **Well-Architected:** nêu rủi ro reliability, security, performance efficiency, cost, operations và sustainability cùng phép kiểm chứng.

Mẫu bảng thiết kế:

| Query | Access pattern | Ràng buộc đúng đắn | Index/key | Metric xác nhận |
|---|---|---|---|---|
| Lịch slot theo resource | resource equality + time range | Không tạo slot trùng | (resource_id, starts_at) | p95 và rows examined |
| Lịch sử khách | customer equality + order | Chỉ đọc đúng customer | (customer_id, created_at, booking_id) | p95 trang đầu/trang sâu |
| Đặt slot | Lookup/claim slot | Unique active booking | Unique/conditional write | Concurrency test |
| Quản trị trạng thái | status + time | Chỉ vai trò được phép | Index theo workload nếu cần | Latency, write overhead |

**Tiêu chí hoàn thành:** Người review hiểu mỗi khóa bảo vệ invariant nào, từng index hỗ trợ truy vấn gì, vì sao chọn thứ tự cột/partition key, kết quả đo chứng minh lợi ích ra sao và chi phí/giới hạn còn lại là gì.

## 13. Đánh giá theo tư duy Well-Architected

| Trụ cột | Câu hỏi khi thiết kế schema, key và index | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Có catalog query/index, owner, migration plan và runbook không? | ADR, query dashboard, index rationale, migration rehearsal |
| **Security** | Có least privilege, tenant isolation, parameterized query và bảo vệ PII không? | IAM/role test, access test, audit, secret handling |
| **Reliability** | Constraint và transaction bảo vệ dữ liệu khi concurrency/failure? Có restore được? | Race test, failover/restore test, consistency check |
| **Performance Efficiency** | Query quan trọng có plan, cardinality và latency đạt mục tiêu không? | EXPLAIN ANALYZE, load test, p95/p99, rows examined |
| **Cost Optimization** | Index/replica/partition có lợi ích tương xứng storage, I/O và vận hành? | Storage, write latency, IOPS, cost allocation |
| **Sustainability** | Có tránh đọc/quét dữ liệu thừa, index/partition không dùng và log giữ quá lâu? | Query efficiency, lifecycle/retention, utilization |

Không có index tốt độc lập khỏi workload. Index giúp một truy vấn có thể làm chậm insert/update; partition giúp retention có thể làm truy vấn toàn cục phức tạp. Hãy tối ưu **toàn workload và mục tiêu hệ thống**, không tối ưu một query bằng mọi giá.

## 14. Khung ghi nhớ

- **Access pattern đi trước schema:** biết ai đọc/ghi dữ liệu nào, theo điều kiện và thứ tự nào, với volume và SLO gì.
- **Khóa bảo vệ tính đúng đắn:** primary key định danh; foreign key bảo vệ tham chiếu; unique/check/transaction bảo vệ invariant.
- **Index phục vụ query có thật:** equality, range, order và pagination quyết định cấu trúc; mỗi index có write/storage/backup cost.
- **NoSQL cần chọn partition/sort key theo truy vấn:** phân bố đều, tránh hot partition và đánh giá index phụ/eventual consistency.
- **Execution plan và load test là bằng chứng:** so estimated/actual rows, buffers, latency, lock, throughput và chi phí.
- **Schema là tài sản vận hành:** migration tương thích, backup/restore, quyền tối thiểu, retention và owner phải được thiết kế cùng.

Thiết kế lược đồ, khóa truy cập và chỉ mục là quá trình chuyển **hành vi nghiệp vụ** thành **cách lưu và truy xuất dữ liệu có thể kiểm chứng**. Một database tốt không phải database có nhiều index hoặc schema phức tạp nhất; đó là database giữ dữ liệu đúng, phục vụ truy vấn quan trọng trong giới hạn độ trễ/tải/chi phí đã thống nhất và có thể thay đổi an toàn khi ứng dụng phát triển.
