# Thực nghiệm dữ liệu sự kiện hoặc lịch sử truy cập theo khóa/thời gian

Một bài thực nghiệm có giá trị với **mô hình cột rộng (wide-column)** cần xuất phát từ câu hỏi mà ứng dụng thực sự đặt ra: “Lấy những sự kiện mới nhất của người dùng này”, “Đọc lịch sử thiết bị trong một khoảng thời gian” hay “Hiển thị 20 lần truy cập gần nhất”. Khi truy vấn luôn biết một **khóa nhận diện** và cần dữ liệu theo **thời gian**, cách chọn *partition key*, *clustering columns* và thời lượng nhóm dữ liệu (*time bucket*) quyết định trực tiếp đường đọc, phân bố tải và khả năng tăng trưởng.

Bài học thực hành với **Apache Cassandra và CQL**. Ta sẽ thiết kế hai cách lưu lịch sử truy cập, nạp dữ liệu giả lập, chạy truy vấn theo khóa/thời gian, quan sát số liệu và phân tích các đánh đổi: phân vùng lớn so với nhiều phân vùng, đọc mới nhất so với đọc nhiều ngày, tính đúng đắn khi retry, và chi phí của một người dùng cực nóng. CQL minh họa theo các phiên bản Cassandra hỗ trợ cú pháp được trình bày; giao diện, câu lệnh vận hành và bảo đảm kỹ thuật cần được kiểm tra theo phiên bản triển khai thực tế.

> **Phạm vi ví dụ:** lịch sử truy cập mang tính kỹ thuật và dữ liệu tổng hợp. Mọi số liệu về tải, kích thước và độ trễ trong bài đều là **giả định hoặc mục tiêu thực nghiệm**, không phải kết quả benchmark Cassandra hay lời hứa hiệu năng. Các lệnh tạo và xóa dữ liệu chỉ nên chạy trong môi trường thử nghiệm.

## 1. Yêu cầu nghiệp vụ biến thành câu hỏi lưu trữ

Giả sử một nền tảng ghi nhận hoạt động truy cập của người dùng. Mỗi sự kiện có tenant, người dùng, thời gian xảy ra, mã sự kiện, hành động, đường dẫn truy cập, mã trạng thái HTTP và thời gian xử lý.

Một bản ghi đại diện:

~~~json
{
  "tenantId": "t01",
  "userId": "u-hot",
  "eventId": "550e8400-e29b-41d4-a716-446655440001",
  "occurredAt": "2026-11-14T08:20:00Z",
  "action": "VIEW",
  "resourcePath": "/catalog/42",
  "statusCode": 200,
  "latencyMs": 18
}
~~~

Các yêu cầu học tập cần được viết thành **access pattern** cụ thể:

| Mã | Câu hỏi ứng dụng | Điều kiện biết trước | Dữ liệu trả về | Tính chất |
|---|---|---|---|---|
| Q1 | Lấy 20 sự kiện mới nhất của một user trong ngày | `tenantId`, `userId`, ngày UTC | 20 hàng theo thời gian giảm dần | Đọc nhiều, độ trễ thấp |
| Q2 | Đọc sự kiện của một user từ 09:00 đến 10:00 | Khóa user, ngày, khoảng timestamp | Các hàng thuộc khoảng | Đọc theo range |
| Q3 | Xem lịch sử user trong bảy ngày | Khóa user, khoảng ngày | Các hàng nhiều ngày, có phân trang | Đọc qua nhiều nhóm |
| Q4 | Xem tất cả lỗi HTTP 5xx của một tenant | Tenant, thời gian, trạng thái lỗi | Sự kiện lỗi từ nhiều user | Đường truy cập khác Q1–Q3 |
| Q5 | Ghi một sự kiện từ API hoặc consumer | Định danh event ổn định | Ghi đúng một event logic khi có retry | Tải ghi liên tục |
| Q6 | Xóa hoặc hết hạn dữ liệu lịch sử quá cũ | Chính sách giữ dữ liệu | Không còn truy cập dữ liệu hết hạn theo hợp đồng | Vòng đời dữ liệu |

Từ bảng này, cần nhận ra: **Q1–Q3 cùng định vị dữ liệu theo người dùng và thời gian**, còn Q4 là câu hỏi về tất cả người dùng trong một tenant. Một bảng tối ưu cho Q1 không nhất thiết hỗ trợ Q4 hiệu quả.

Mục tiêu thực hành gồm: tạo hai mô hình cột rộng, giải thích từng thành phần của khóa chính, ghi dữ liệu có thể tái tạo, đọc đúng theo thứ tự và khoảng thời gian, đo độ trễ/throughput/dung lượng, rồi chọn mô hình bằng chứng cứ.

## 2. Ba quyết định thiết kế: partition, row, clustering

Cassandra tổ chức các hàng theo **partition key**. Những hàng có cùng partition key nằm trong cùng phân vùng logic. Trong phân vùng, **clustering columns** định danh và tổ chức các hàng theo một thứ tự được khai báo.

Sơ đồ một nhóm lịch sử:

~~~text
Partition key = (tenant_id=t01, user_id=u-hot, bucket_day=2026-11-14)
┌───────────────────────┬─────────────────────────┬────────┬──────────────┐
│ occurred_at DESC      │ event_id                │ action │ resource     │
├───────────────────────┼─────────────────────────┼────────┼──────────────┤
│ 2026-11-14T08:20:00Z  │ ...001                  │ VIEW   │ /catalog/42  │
│ 2026-11-14T08:15:00Z  │ ...002                  │ LOGIN  │ /login       │
│ 2026-11-14T08:10:00Z  │ ...003                  │ VIEW   │ /home        │
└───────────────────────┴─────────────────────────┴────────┴──────────────┘

Partition key = (tenant_id=t01, user_id=u-hot, bucket_day=2026-11-13)
┌───────────────────────┬─────────────────────────┬────────┬──────────────┐
│ 2026-11-13T23:40:00Z  │ ...010                  │ VIEW   │ /home        │
└───────────────────────┴─────────────────────────┴────────┴──────────────┘
~~~

Trong cú pháp CQL:

~~~sql
PRIMARY KEY ((tenant_id, user_id, bucket_day), occurred_at, event_id)
~~~

Ý nghĩa từng phần:

- `(tenant_id, user_id, bucket_day)` là **partition key ghép**. Cần đủ ba giá trị khi muốn định vị chính xác một phân vùng.
- `occurred_at` và `event_id` là **clustering columns**. Chúng phân biệt hàng và xác định thứ tự trong phân vùng.
- Toàn bộ tổ hợp khóa chính nhận diện một hàng. Hai thao tác ghi dùng đúng cùng khóa chính sẽ nhắm đến cùng hàng logic, theo ngữ nghĩa cập nhật của Cassandra.
- `action`, `resource_path`, `status_code`, `latency_ms` là **regular columns**: dữ liệu có ý nghĩa nghiệp vụ nhưng không tạo đường truy cập chính trong mô hình này.

**Chú ý dấu ngoặc:**

~~~sql
-- Partition key chỉ gồm tenant_id; user_id là clustering column.
PRIMARY KEY (tenant_id, user_id, occurred_at)

-- Partition key ghép gồm tenant_id và user_id.
PRIMARY KEY ((tenant_id, user_id), occurred_at)

-- Partition key ghép gồm tenant, user và ngày.
PRIMARY KEY ((tenant_id, user_id, bucket_day), occurred_at, event_id)
~~~

Ba định nghĩa trên không tương đương. Thay đổi ngoặc thay đổi cách gom dữ liệu, khả năng định tuyến và quy mô của mỗi partition.

## 3. Vì sao phải cân nhắc bucket thời gian?

Một cách thiết kế ban đầu là gom **toàn bộ lịch sử của một user** vào một partition:

~~~sql
PRIMARY KEY ((tenant_id, user_id), occurred_at, event_id)
~~~

Nó thuận lợi khi một query xem toàn bộ lịch sử user: biết tenant và user là đủ để định vị. Nhưng với user hoạt động lâu năm hoặc tạo nhiều sự kiện, partition có thể tăng liên tục. Một người dùng nhận hàng nghìn sự kiện/giây cũng có thể làm cả một partition hoặc nhóm replica trở thành điểm nóng.

Một phương án khác chia theo ngày:

~~~sql
PRIMARY KEY ((tenant_id, user_id, bucket_day), occurred_at, event_id)
~~~

Khi đó, truy vấn theo ngày chỉ cần một partition, còn truy vấn dài ngày cần nhiều partition. Đổi lại, một partition không tiếp tục tăng suốt nhiều năm.

| Quyết định | Không bucket | Theo ngày | Theo giờ |
|---|---|---|---|
| Khóa partition | Tenant + user | Tenant + user + ngày | Tenant + user + giờ |
| Số sự kiện/partition | Tăng theo tuổi user | Giới hạn theo lưu lượng/ngày | Giới hạn theo lưu lượng/giờ |
| Xem 30 phút gần nhất | Thường một partition | Thường một partition, có thể hai nếu qua nửa đêm | Một hoặc hai bucket |
| Xem 7 ngày | Có thể một partition rất lớn | Khoảng 7–8 partition tùy mốc thời gian | Tới hàng trăm partition |
| Nguy cơ | Partition quá lớn, hot partition | Fan-out khi truy vấn nhiều ngày | Nhiều partition nhỏ, tăng điều phối |

Các con số partition khi truy vấn nhiều ngày là ước lượng theo biên khoảng thời gian. Nếu ứng dụng dùng khoảng `[start, end)`, cần tính đúng bucket mà khoảng ấy cắt qua.

Ví dụ một user sinh 2 sự kiện/giây liên tục: trong 24 giờ có 172.800 sự kiện. Một tháng có trên 5 triệu sự kiện. Nếu mỗi sự kiện ở dạng logic khoảng 300 byte, riêng dữ liệu nội dung của một ngày đã khoảng 52 MB trước overhead, index và cơ chế lưu trữ. Đây **chỉ là ước lượng dung lượng logic**, chưa phản ánh chính xác byte trên đĩa hoặc ngưỡng an toàn cho Cassandra.

**Cách chọn bucket phải dựa trên phân bố thực:** bao nhiêu user hoạt động bình thường, user nóng nhất có tải bao nhiêu, API thường xem bao lâu và số partition mỗi lần đọc là bao nhiêu.

## 4. Chuẩn bị môi trường Cassandra thử nghiệm

Có thể dùng Cassandra đã có trong môi trường học. Nếu cần một node độc lập, ví dụ Docker sau cho thấy cách chạy một môi trường thử với cổng CQL mặc định 9042:

~~~bash
docker run -d --name cassandra-events-lab \
  -p 9042:9042 \
  cassandra:4.1
~~~

Cassandra có thể cần một khoảng thời gian để khởi động. Khi dịch vụ đã sẵn sàng, mở `cqlsh` trong container:

~~~bash
docker exec -it cassandra-events-lab cqlsh
~~~

Các ví dụ về `cqlsh` và `nodetool` dưới đây giả định container được đặt tên `cassandra-events-lab`. Nếu dùng Cassandra cài sẵn hoặc cluster do tổ chức quản lý, thay bằng địa chỉ, thông tin xác thực và tên môi trường tương ứng.

Một node chỉ giúp học keyspace, partition và query. **Nó không chứng minh khả năng phân tán, replication factor lớn hơn một, tính chịu lỗi node hay độ trễ liên datacenter**. Các thử nghiệm failover thật cần cụm nhiều node được thiết kế riêng.

Trong `cqlsh`, tạo keyspace cho bài thực hành:

~~~sql
CREATE KEYSPACE IF NOT EXISTS wide_column_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE wide_column_lab;
~~~

`SimpleStrategy` và replication factor 1 dùng riêng cho ví dụ một node. Cluster thực tế thường cần cấu hình replication phù hợp topology/datacenter, cùng các quy tắc quản trị và bảo mật đã được xác định.

## 5. Tạo hai mô hình để so sánh

Ta tạo một bảng **A không bucket** và một bảng **B có bucket theo ngày**. Hai bảng chứa cùng các trường, cho phép dùng cùng tập sự kiện để quan sát tác động của khóa phân vùng.

### 5.1. Bảng A: lịch sử theo user, không chia ngày

~~~sql
CREATE TABLE IF NOT EXISTS wide_column_lab.events_by_user_all (
    tenant_id text,
    user_id text,
    occurred_at timestamp,
    event_id uuid,
    action text,
    resource_path text,
    status_code int,
    latency_ms int,
    PRIMARY KEY (
        (tenant_id, user_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Tất cả sự kiện của một user trong tenant thuộc cùng partition. Nó trực tiếp phục vụ truy vấn “lấy các sự kiện mới nhất của user này” mà không cần biết ngày.

### 5.2. Bảng B: lịch sử theo user và ngày

~~~sql
CREATE TABLE IF NOT EXISTS wide_column_lab.events_by_user_day (
    tenant_id text,
    user_id text,
    bucket_day date,
    occurred_at timestamp,
    event_id uuid,
    action text,
    resource_path text,
    status_code int,
    latency_ms int,
    PRIMARY KEY (
        (tenant_id, user_id, bucket_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Ở bảng B, `bucket_day` được tính theo ngày UTC của `occurred_at`. Đây là **quy ước của ứng dụng**: Cassandra không tự tính ngày từ timestamp mỗi khi ghi. Nếu hệ thống chấp nhận múi giờ nghiệp vụ khác UTC thì phải dùng cùng quy tắc trong cả writer và reader.

### 5.3. Vì sao cần hai clustering columns?

Sự kiện có thể trùng `occurred_at` khi độ phân giải timestamp không đủ hoặc nhiều request đến cùng một thời điểm. Nếu chỉ dùng `occurred_at` làm clustering key, các sự kiện có cùng timestamp và cùng partition key sẽ có cùng primary key.

Thêm `event_id` tạo khóa phụ:

~~~text
(tenant_id, user_id, bucket_day, occurred_at, event_id)
                  xác định một hàng logic
~~~

Trong thử nghiệm, `event_id` được tạo **ổn định từ định danh sự kiện**, để retry cùng event không sinh thêm hàng khác. Một UUID mới mỗi lần retry sẽ làm dữ liệu trùng nghiệp vụ dù primary key vẫn là duy nhất.

`CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)` giúp truy vấn lấy sự kiện gần nhất theo thứ tự thời gian giảm dần. Nếu hai sự kiện có cùng timestamp, `event_id ASC` chỉ tạo thứ tự xác định; thứ tự UUID này không nhất thiết phản ánh thời điểm phát sinh thật của hai sự kiện trùng timestamp.

## 6. Ghi dữ liệu mẫu để nhìn thấy partition và thứ tự

Các lệnh sau dùng ba sự kiện ngày 14/11 và một sự kiện ngày 13/11 cho user thử nghiệm `u-demo`. Chúng chỉ ghi vào **bảng B** để minh họa và không trùng khóa với dữ liệu lớn được sinh ở phần sau.

~~~sql
INSERT INTO wide_column_lab.events_by_user_day
(tenant_id, user_id, bucket_day, occurred_at, event_id,
 action, resource_path, status_code, latency_ms)
VALUES
('t01', 'u-demo', '2026-11-14', '2026-11-14T08:10:00Z',
 550e8400-e29b-41d4-a716-446655440001,
 'VIEW', '/home', 200, 12);

INSERT INTO wide_column_lab.events_by_user_day
(tenant_id, user_id, bucket_day, occurred_at, event_id,
 action, resource_path, status_code, latency_ms)
VALUES
('t01', 'u-demo', '2026-11-14', '2026-11-14T08:15:00Z',
 550e8400-e29b-41d4-a716-446655440002,
 'LOGIN', '/login', 200, 35);

INSERT INTO wide_column_lab.events_by_user_day
(tenant_id, user_id, bucket_day, occurred_at, event_id,
 action, resource_path, status_code, latency_ms)
VALUES
('t01', 'u-demo', '2026-11-14', '2026-11-14T08:20:00Z',
 550e8400-e29b-41d4-a716-446655440003,
 'VIEW', '/catalog/42', 200, 18);

INSERT INTO wide_column_lab.events_by_user_day
(tenant_id, user_id, bucket_day, occurred_at, event_id,
 action, resource_path, status_code, latency_ms)
VALUES
('t01', 'u-demo', '2026-11-13', '2026-11-13T23:40:00Z',
 550e8400-e29b-41d4-a716-446655440010,
 'VIEW', '/home', 200, 22);
~~~

Đọc toàn bộ hàng **của một ngày** với đủ partition key:

~~~sql
SELECT occurred_at, event_id, action, resource_path
FROM wide_column_lab.events_by_user_day
WHERE tenant_id = 't01'
  AND user_id = 'u-demo'
  AND bucket_day = '2026-11-14';
~~~

Thứ tự `occurred_at` dự kiến là **08:20, 08:15, 08:10** vì clustering khai báo `DESC`, dù các câu `INSERT` được gửi theo thứ tự tăng dần. Một hàng ngày 13/11 nằm ở partition khác nên không xuất hiện ở kết quả ngày 14/11.

## 7. Thực nghiệm Q1: lấy N sự kiện mới nhất theo khóa

Nhu cầu: hiển thị 20 lần truy cập mới nhất của user trong ngày. Bảng B có đường truy cập trực tiếp:

~~~sql
SELECT occurred_at, event_id, action, resource_path, status_code
FROM wide_column_lab.events_by_user_day
WHERE tenant_id = 't01'
  AND user_id = 'u-demo'
  AND bucket_day = '2026-11-14'
LIMIT 20;
~~~

Với ví dụ `u-demo`, kết quả có ba hàng theo thứ tự mới nhất trước. `LIMIT 20` giới hạn số hàng trả về; nếu có 10.000 hàng trong partition, query vẫn chỉ yêu cầu tối đa 20 hàng của đường truy cập này.

Ở bảng A, cùng truy vấn theo user có thể viết:

~~~sql
SELECT occurred_at, event_id, action, resource_path, status_code
FROM wide_column_lab.events_by_user_all
WHERE tenant_id = 't01'
  AND user_id = 'u-demo'
LIMIT 20;
~~~

Điểm khác biệt: bảng A không cần ngày, còn bảng B cần `bucket_day`. Không thể dùng bảng B để truy vấn hiệu quả chỉ với tenant và user mà bỏ ngày, vì các ngày tạo ra nhiều partition khác nhau.

Nếu API yêu cầu “20 sự kiện mới nhất của user **không giới hạn ngày**”, bảng B cần logic dò các bucket từ gần nhất lùi về trước, có giới hạn phạm vi hợp lý. Đổi lại, bảng A không có ranh giới tăng trưởng cho partition của user.

## 8. Thực nghiệm Q2: đọc một khoảng timestamp trong partition

Nhu cầu: xem các sự kiện từ 08:12 đến trước 08:21 cùng ngày. Dùng điều kiện khoảng trên clustering column `occurred_at`:

~~~sql
SELECT occurred_at, event_id, action, latency_ms
FROM wide_column_lab.events_by_user_day
WHERE tenant_id = 't01'
  AND user_id = 'u-demo'
  AND bucket_day = '2026-11-14'
  AND occurred_at >= '2026-11-14T08:12:00Z'
  AND occurred_at <  '2026-11-14T08:21:00Z';
~~~

Kết quả dự kiến: sự kiện **08:20 và 08:15**; sự kiện 08:10 nằm ngoài khoảng.

Dùng khoảng nửa mở `[start, end)` giúp ghép các cửa sổ không chồng lấn theo biên:

~~~text
[08:00, 09:00) và [09:00, 10:00)
-> sự kiện đúng 09:00 thuộc cửa sổ thứ hai
-> không bị đếm hai lần khi ghép theo cửa sổ
~~~

Điều kiện phải trùng với phạm vi partition được chọn. Nếu yêu cầu thực sự là 23:50 ngày 13/11 đến 00:10 ngày 14/11, hai bảng có đặc điểm khác:

- Bảng A có thể dùng **một truy vấn theo user và khoảng timestamp**.
- Bảng B cần **hai truy vấn** vào hai `bucket_day` khác nhau, rồi ghép kết quả có thứ tự.

Điều này không phải lỗi của time bucketing mà là **chi phí được chủ động trao đổi để giới hạn kích thước partition**.

## 9. Thực nghiệm Q3: truy vấn nhiều ngày và phân trang

Một phân vùng chỉ chứa một ngày của một user. API lịch sử bảy ngày cần xác định những `bucket_day` cắt khoảng thời gian. Với khoảng thời gian nửa mở, thuật toán ứng dụng có thể:

1. Chuyển `start` và `end` về cùng múi giờ dùng để bucket (ví dụ UTC).
2. Tính các ngày có giao với khoảng `[start, end)`.
3. Với mỗi ngày, truy vấn bằng **đầy đủ tenant, user, bucket_day**; giới hạn timestamp theo hai biên nếu cần.
4. Ghép kết quả của các bucket theo `occurred_at DESC` và `event_id ASC`; áp dụng `limit` ở tầng API.
5. Giới hạn số ngày và số request con, theo dõi độ trễ tổng và xử lý lỗi từng bucket.

~~~mermaid
flowchart TD
    A["GET /users/u42/events?from=...&to=..."] --> B["Tính các bucket UTC cần đọc"]
    B --> C["Đọc partition ngày 14"]
    B --> D["Đọc partition ngày 13"]
    B --> E["Đọc các ngày còn lại trong phạm vi"]
    C --> F["Ghép theo timestamp và khóa phụ"]
    D --> F
    E --> F
    F --> G["Giới hạn 20 kết quả và trả next cursor"]
~~~

Giả mã cho trường hợp dữ liệu luôn thuộc bucket theo chính `occurred_at`:

~~~text
function newestEvents(tenant, user, start, end, limit):
    days = UTC days intersecting [start, end)
    candidates = []
    for day in days (newest to oldest):
        rows = query one partition with time bounds and a bounded page size
        append rows to candidates
        if enough rows exist to determine global top limit:
            stop or continue as required by merge and pagination policy
    sort/merge by occurredAt DESC, eventId ASC
    return first limit rows and a resumable cursor
~~~

Trong code production, phải xác định rõ khi nào đủ dữ liệu để dừng và cách xử lý nhiều trang trong từng bucket. Nếu đọc song song các partition, cần merge các luồng đã sắp và giữ trạng thái phân trang riêng cho từng luồng. Nếu chỉ đọc một trang của mỗi bucket mà giả định đã có toàn bộ dữ liệu, các trang sau có thể bỏ sót hàng.

### 9.1. Paging trong CQL/driver

Một kết quả nhiều hàng không nhất thiết phải được tải hết trong một response. Driver Cassandra hỗ trợ **paging theo fetch size và paging state**. Khi dùng state để tiếp tục, cần giữ nguyên truy vấn, tham số và điều kiện phù hợp; paging state là thông tin nội bộ không nên tùy tiện chỉnh sửa hoặc tin tưởng từ đầu vào người dùng khi chưa kiểm tra.

Trong `cqlsh`, có thể thử việc chia trang bằng lệnh điều khiển:

~~~text
PAGING 10;
~~~

Sau đó chạy một câu `SELECT` trả nhiều hàng để quan sát việc `cqlsh` lấy trang tiếp. `PAGING` của client giúp khám phá hành vi; nó **không** tự tạo một API cursor an toàn cho lịch sử nhiều partition.

Với một API, cursor nên có phiên bản, phạm vi tenant/user, khoảng thời gian, ngày/bucket hiện tại và vị trí tiếp theo hoặc paging state tương ứng. Hãy định nghĩa rõ điều gì xảy ra khi sự kiện mới được ghi giữa hai lần gọi trang: dữ liệu có thể thay đổi và không nên mặc định có snapshot nhất quán xuyên suốt nhiều trang.

## 10. Những câu truy vấn không phù hợp với bảng này

Từ `events_by_user_day`, không thể mong các query sau có cùng chi phí như Q1/Q2:

~~~sql
-- Không biết user: không có đầy đủ partition key.
SELECT *
FROM wide_column_lab.events_by_user_day
WHERE tenant_id = 't01'
  AND bucket_day = '2026-11-14';

-- Biết status_code nhưng không biết partition key.
SELECT *
FROM wide_column_lab.events_by_user_day
WHERE status_code = 500;
~~~

Hai biểu thức trên được đưa ra để **phân tích mô hình**, không phải các câu lệnh nên thực thi trên dataset lớn. Trong Cassandra, chúng có thể bị từ chối vì không có đường truy cập hỗ trợ; cố thêm `ALLOW FILTERING` không biến chúng thành truy vấn phân vùng tốt và có thể gây quét rất rộng.

Nguyên tắc của bảng hiện tại:

| Nhu cầu | Đường truy cập | Nhận xét |
|---|---|---|
| Một user, một ngày, mới nhất | Một partition + clustering order | Phù hợp |
| Một user, một ngày, khoảng giờ | Một partition + clustering range | Phù hợp |
| Một user, nhiều ngày | Nhiều partition có giới hạn | Cần điều phối |
| Mọi user trong tenant, mới nhất | Không có khóa định vị phù hợp | Cần mô hình đọc khác |
| Tìm theo `status_code` trên toàn hệ | Không được tổ chức theo mã trạng thái | Cần projection/index/hệ phân tích thích hợp |
| Thống kê dài hạn toàn bộ event | Quét nhiều partition | Thường phù hợp hơn với pipeline phân tích |

Vì vậy, thực nghiệm wide-column là thực nghiệm **truy vấn đã định hình**, không phải bài tập xem có viết được cú pháp `SELECT` tùy ý hay không.

## 11. Mô hình bổ sung cho Q4: lỗi HTTP theo tenant và thời gian

Nếu sản phẩm cần liên tục hiển thị lỗi 5xx mới nhất trên tất cả user của tenant, có thể cân nhắc một bảng đọc thứ hai chỉ chứa sự kiện lỗi.

~~~sql
CREATE TABLE IF NOT EXISTS wide_column_lab.errors_by_tenant_day (
    tenant_id text,
    bucket_day date,
    occurred_at timestamp,
    user_id text,
    event_id uuid,
    resource_path text,
    status_code int,
    latency_ms int,
    PRIMARY KEY (
        (tenant_id, bucket_day),
        occurred_at,
        user_id,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    user_id ASC,
    event_id ASC
);
~~~

Đường đọc:

~~~sql
SELECT occurred_at, user_id, resource_path, status_code, latency_ms
FROM wide_column_lab.errors_by_tenant_day
WHERE tenant_id = 't01'
  AND bucket_day = '2026-11-14'
LIMIT 30;
~~~

Trong ví dụ này, ứng dụng chỉ ghi vào `errors_by_tenant_day` khi có event HTTP 5xx. Không yêu cầu Cassandra lọc mọi `status_code` trên bảng lịch sử vốn được tổ chức theo user.

**Đánh đổi mới:** một tenant có lưu lượng lỗi rất lớn sẽ tạo partition nóng ở bảng tổng hợp. Khi dữ liệu tăng, có thể cần bucket theo giờ hoặc thêm shard, rồi ghép kết quả. Ghi cùng một event vào hai bảng cũng nảy sinh vấn đề:

- Bảng nào là dữ liệu gốc được dùng để đối soát?
- Nếu ghi bảng user thành công nhưng ghi projection lỗi thì retry hoặc tái tạo ra sao?
- Nếu cùng event đến hai lần, consumer dùng cùng định danh và cùng khóa hay tạo bản sao mới?
- Dashboard chấp nhận trễ bao lâu so với luồng ghi chính?

Việc ghi hai bảng riêng không tự động cung cấp đầy đủ ngữ nghĩa giao dịch nhiều document như một cơ sở dữ liệu quan hệ. Batch trong Cassandra có bảo đảm và chi phí riêng, không nên dùng tùy tiện để giả lập transaction SQL hay tăng tốc nhiều partition.

## 12. Sinh dữ liệu thực nghiệm có thể tái tạo bằng Python

Đọc ba sự kiện mẫu chưa giúp thấy vấn đề khi tải tăng. Ta cần dữ liệu gồm **nhiều người dùng bình thường và ít nhất một user nóng**. Script dưới đây nạp cùng sự kiện vào hai bảng A/B, với UUID ổn định theo ngày và thứ tự sự kiện, để có thể tái chạy và đối chiếu.

Điều kiện: Cassandra CQL đã chạy, đã tạo hai bảng như mục 5, và môi trường Python đã có driver tương thích:

~~~bash
python -m pip install cassandra-driver
~~~

Lưu nội dung sau thành `seed_events.py` trong thư mục thực hành của bạn rồi chạy từ máy kết nối được cổng 9042. Đây là mã ví dụ cho bài học; worker không thực thi script này vào repository.

~~~python
from datetime import date, datetime, time, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
import random

from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args

HOSTS = ["127.0.0.1"]
KEYSPACE = "wide_column_lab"

DAYS = 14
ROWS_PER_DAY = 1500
FIRST_DAY = date(2026, 11, 1)
TENANT = "t01"

rng = random.Random(20261114)

cluster = Cluster(HOSTS)
session = cluster.connect(KEYSPACE)

insert_all = session.prepare("""
    INSERT INTO events_by_user_all
      (tenant_id, user_id, occurred_at, event_id, action,
       resource_path, status_code, latency_ms)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""")

insert_day = session.prepare("""
    INSERT INTO events_by_user_day
      (tenant_id, user_id, bucket_day, occurred_at, event_id,
       action, resource_path, status_code, latency_ms)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""")

rows_all = []
rows_day = []

try:
    for day_offset in range(DAYS):
        day = FIRST_DAY + timedelta(days=day_offset)
        midnight = datetime.combine(day, time.min, tzinfo=timezone.utc)

        for i in range(ROWS_PER_DAY):
            # Xấp xỉ 20% event đi vào một user nóng.
            user = "u-hot" if rng.random() < 0.20 else (
                f"u-{rng.randrange(100):03d}"
            )

            # Timestamp nằm trong đúng bucket UTC của ngày.
            seconds = int(i * 86400 / ROWS_PER_DAY)
            occurred_at = midnight + timedelta(seconds=seconds)

            # Cùng event luôn có cùng ID, kể cả khi chạy lại seed.
            event_id = uuid5(
                NAMESPACE_URL, f"access:{TENANT}:{day.isoformat()}:{i}"
            )
            action = "LOGIN" if i % 7 == 0 else "VIEW"
            resource_path = f"/catalog/{i % 50}"
            status_code = 500 if i % 97 == 0 else 200
            latency_ms = 8 + (i % 120)

            rows_all.append((
                TENANT, user, occurred_at, event_id, action,
                resource_path, status_code, latency_ms
            ))

            rows_day.append((
                TENANT, user, day, occurred_at, event_id, action,
                resource_path, status_code, latency_ms
            ))

    def write_batch(statement, arguments, label):
        failures = 0
        for success, result in execute_concurrent_with_args(
            session,
            statement,
            arguments,
            concurrency=32,
            raise_on_first_error=False
        ):
            if not success:
                failures += 1
                if failures <= 3:
                    print(f"{label}: write error: {result}")

        print(f"{label}: attempted={len(arguments)}, failures={failures}")
        if failures:
            raise RuntimeError(f"{label}: {failures} writes failed")

    write_batch(insert_all, rows_all, "unbucketed")
    write_batch(insert_day, rows_day, "daily-bucketed")
finally:
    cluster.shutdown()
~~~

Script mặc định tạo `14 × 1.500 = 21.000` sự kiện logic, chèn vào **mỗi bảng** để có cùng tập dữ liệu. Tải này đủ để quan sát cách viết query và vị trí partition; chưa đủ để suy ra khả năng chịu tải lớn. Để nghiên cứu tăng trưởng, thay `ROWS_PER_DAY`, `DAYS` và phân bố user, nhưng luôn giữ lại thông tin seed và số liệu.

Lệnh chạy:

~~~bash
python seed_events.py
~~~

### Tại sao cần user nóng?

Nếu mọi user nhận số sự kiện gần bằng nhau, hai cách chia partition có thể trông tương đương khi dataset nhỏ. Tăng tỷ lệ sự kiện cho `u-hot` khiến kích thước và số thao tác dồn vào một số partition lớn hơn, từ đó có cơ sở để đo chênh lệch với các user bình thường.

Trong script mẫu, user nóng chiếm khoảng 20% sự kiện, còn 80% còn lại phân bố ngẫu nhiên trên 100 user. Tỷ lệ này chỉ là cấu hình thử; workload sản xuất có thể lệch khác nhiều. Với mỗi thí nghiệm, hãy nêu rõ **phân bố per-user** thay vì chỉ báo tổng số hàng.

### Tại sao ID phải cố định giữa các lần nạp?

Nếu chạy lại script, `uuid5` nhận cùng tên định danh sẽ tạo cùng `event_id`; `occurred_at` và partition key cũng cố định từ `day`, `i` và seed. Khi đó các lần ghi nhắm vào cùng primary key logic thay vì chèn thêm event trùng với UUID mới.

Điều này minh họa **idempotent upsert ở phạm vi một hàng**, không có nghĩa mọi pipeline event được bảo đảm exactly-once tự động. Nếu cùng ID được gửi với payload khác hoặc ghi timestamp khác, cần quy tắc nghiệp vụ để phát hiện và xử lý xung đột.

## 13. Đọc dữ liệu sau khi nạp

Thử trên bảng B:

~~~sql
-- N sự kiện mới nhất của user nóng trong ngày 14.
SELECT occurred_at, event_id, action, resource_path
FROM wide_column_lab.events_by_user_day
WHERE tenant_id = 't01'
  AND user_id = 'u-hot'
  AND bucket_day = '2026-11-14'
LIMIT 20;

-- Một cửa sổ giờ cụ thể.
SELECT occurred_at, event_id, status_code, latency_ms
FROM wide_column_lab.events_by_user_day
WHERE tenant_id = 't01'
  AND user_id = 'u-hot'
  AND bucket_day = '2026-11-14'
  AND occurred_at >= '2026-11-14T09:00:00Z'
  AND occurred_at <  '2026-11-14T10:00:00Z'
LIMIT 100;
~~~

Thử trên bảng A:

~~~sql
-- Lấy 20 sự kiện mới nhất của user (không cần ngày).
SELECT occurred_at, event_id, action, resource_path
FROM wide_column_lab.events_by_user_all
WHERE tenant_id = 't01'
  AND user_id = 'u-hot'
LIMIT 20;

-- Đọc dữ liệu của riêng ngày 14 qua một range trên clustering key.
SELECT occurred_at, event_id, action, resource_path
FROM wide_column_lab.events_by_user_all
WHERE tenant_id = 't01'
  AND user_id = 'u-hot'
  AND occurred_at >= '2026-11-14T00:00:00Z'
  AND occurred_at <  '2026-11-15T00:00:00Z'
LIMIT 20;
~~~

Quan sát có thể kiểm tra bằng mắt: mỗi bảng có cùng các event logic, nhưng cùng truy vấn phải đi qua **khóa và số phân vùng khác nhau**. Đừng dùng `SELECT COUNT(*)` trên partition khổng lồ để thống kê production: phép đếm có thể phải đọc rất nhiều hàng, không phải metadata tức thời. Với bài thực hành, đã biết chính xác số dòng seed nên dùng nhật ký nạp và các metric thu được để đối chiếu.

## 14. Đo latency: từ một lệnh CQL đến phép thử có kiểm soát

Thấy `SELECT` trả kết quả trong terminal chưa đủ chứng minh hiệu quả. Một phép đo cần lưu **thời gian client end-to-end**, tải đang gửi, số hàng thực trả, tỷ lệ lỗi và thông tin môi trường.

Ví dụ Python dưới đây đo tuần tự 200 lần truy vấn “20 event của user nóng ngày 14” trên A và B. Nó chỉ là **microbenchmark tuần tự** để bắt đầu quan sát, không thay thế workload đồng thời với nhiều kết nối và tải production.

~~~python
from datetime import date, datetime, timezone
from time import perf_counter
from math import ceil

from cassandra.cluster import Cluster

cluster = Cluster(["127.0.0.1"])
session = cluster.connect("wide_column_lab")

q_all = session.prepare("""
    SELECT occurred_at, event_id, action
    FROM events_by_user_all
    WHERE tenant_id = ?
      AND user_id = ?
      AND occurred_at >= ?
      AND occurred_at < ?
    LIMIT 20
""")

q_day = session.prepare("""
    SELECT occurred_at, event_id, action
    FROM events_by_user_day
    WHERE tenant_id = ?
      AND user_id = ?
      AND bucket_day = ?
    LIMIT 20
""")

start = datetime(2026, 11, 14, tzinfo=timezone.utc)
end = datetime(2026, 11, 15, tzinfo=timezone.utc)

def percentile(values, p):
    ordered = sorted(values)
    position = max(0, ceil(len(ordered) * p / 100) - 1)
    return ordered[position]

def measure(label, statement, parameters, iterations=200):
    # Warm-up tách khỏi thời gian đo.
    for _ in range(30):
        list(session.execute(statement, parameters))

    latencies_ms = []
    row_count = None

    for _ in range(iterations):
        t0 = perf_counter()
        rows = list(session.execute(statement, parameters))
        latencies_ms.append((perf_counter() - t0) * 1000)
        row_count = len(rows)

    print(
        f"{label}: rows={row_count}, "
        f"p50={percentile(latencies_ms, 50):.2f} ms, "
        f"p95={percentile(latencies_ms, 95):.2f} ms, "
        f"p99={percentile(latencies_ms, 99):.2f} ms"
    )

try:
    measure("all-history", q_all, ("t01", "u-hot", start, end))
    measure("day-bucket", q_day, ("t01", "u-hot", date(2026, 11, 14)))
finally:
    cluster.shutdown()
~~~

Cả hai truy vấn nhận gần cùng tập dữ liệu ngày 14 nếu tập nạp và thời gian của event nhất quán; tuy nhiên, index/partition path khác nhau. Kết quả có thể rất gần nhau vì dataset còn nhỏ và nằm trong bộ nhớ. Đó là kết quả bình thường của môi trường thử, không phải dấu hiệu phải “tăng số cho đẹp”.

### Ý nghĩa của các chỉ số

| Chỉ số | Cách diễn giải |
|---|---|
| `p50` | Khoảng một nửa request hoàn thành không quá giá trị này |
| `p95` / `p99` | Phần đuôi độ trễ; quan trọng khi có queue, partition nóng hoặc I/O |
| Throughput | Số thao tác **thực hoàn thành** mỗi giây |
| Error rate | Tỷ lệ lỗi, gồm timeout và thất bại ở client/server |
| Rows returned | Số hàng trả về, dùng để so sánh các query thực sự tương đương |
| Bytes transferred | Tổng byte request/response, ảnh hưởng mạng và serialization |
| CPU, RAM, disk I/O | Chỉ ra chi phí vận hành mà latency đơn lẻ không giải thích |
| Partition size/skew | Phân bố số hàng và kích thước giữa user thường với user nóng |

Giá trị p95 không có ý nghĩa đầy đủ khi chỉ có một số ít request. Cần nhiều mẫu, thời gian đủ dài, cùng tải và nhiều lần chạy để so sánh ổn định. Với hàng triệu event, nên dùng công cụ tạo tải có khả năng cố định tốc độ, concurrency và báo cáo histogram latency, cùng telemetry phía Cassandra.

## 15. Thiết kế workload thực nghiệm theo ba mức

Không nên đổi schema và đồng thời đổi phần cứng, số node, consistency level, driver, số lượng event rồi kết luận do bucket. Hãy dùng một ma trận thí nghiệm có biến được kiểm soát.

| Workload | Dữ liệu/tải đầu vào | Cần đo | Câu hỏi |
|---|---|---|---|
| W1 — User thường | Ít event/ngày, query Q1/Q2 | p95, hàng đọc, throughput | Có khác biệt đáng kể khi partition đều nhỏ? |
| W2 — User nóng | 20–50% event tập trung ở một user | p99, CPU/replica, timeout, partition skew | Partition không bucket có trở nên quá lớn/nóng? |
| W3 — Lịch sử dài | Truy vấn 1, 7, 30, 90 ngày | Số partition, tổng request con, latency API | Chi phí fan-out của bucket ngày là bao nhiêu? |
| W4 — Ghi đồng thời | Nhiều client ghi liên tục vào một số user | Write p95, throughput, error rate | Phân bố tải có tạo bottleneck cục bộ? |
| W5 — Retention | TTL/xóa dữ liệu cũ theo cửa sổ | Tombstone, đọc, compaction, dung lượng | Chính sách lưu giữ ảnh hưởng đường đọc dài hạn thế nào? |

Trong mỗi workload, tăng dữ liệu từ nhỏ đến lớn, giữ lại báo cáo về **số sự kiện/partition** của user bình thường và user nóng. Nếu chạy trên một node, chỉ suy luận được về cách truy cập và chi phí tại node đó; chưa thể suy ra hiệu quả chia tải ra nhiều replica hoặc datacenter.

### Thí dụ cấu hình thí nghiệm

~~~yaml
experiment: wide-column-access-history
environment:
  database: Apache Cassandra
  topology: one-node-learning
  consistency: ONE
dataset:
  tenantCount: 1
  userCountApprox: 101
  days: 14
  eventsPerDay: 1500
  hotUserEventShare: 0.20
  seed: 20261114
variants:
  A: partition-by-tenant-user
  B: partition-by-tenant-user-day
queryMix:
  latestSingleDay: 0.60
  oneHourRange: 0.25
  sevenDayHistory: 0.15
measure:
  - clientLatencyP50P95P99
  - achievedReadsAndWritesPerSecond
  - errorAndTimeoutCount
  - partitionsReadPerApiRequest
  - requestAndResponseBytes
  - partitionSizeDistribution
  - cpuMemoryDiskNetwork
~~~

Đây là một tài liệu mô tả kế hoạch thử nghiệm, **không phải cấu hình mà Cassandra hay load generator có thể chạy trực tiếp**. Cần chuyển nó thành script/cấu hình của công cụ đo thực tế.

## 16. Đọc số liệu và không nhầm quy mô partition với dung lượng table

Một bảng có 10 triệu hàng không nhất thiết có partition lớn, nếu dữ liệu trải đều trên rất nhiều partition. Ngược lại, một bảng chỉ có 100.000 hàng vẫn có thể có một partition rất lớn nếu mọi hàng cùng khóa.

Phân biệt các lớp số liệu:

1. **Tổng số hàng/tổng dung lượng table:** cho biết quy mô chung.
2. **Số partition và phân bố hàng trong từng partition:** cho biết độ lệch, partition to và nóng.
3. **Tải trên mỗi token range/node/replica:** cho biết dữ liệu và lưu lượng được phân phối như thế nào.
4. **Độ trễ theo loại query và số partition mà API truy cập:** cho biết chi phí thực tế cho người dùng.
5. **Compaction, tombstones, read/write latency và I/O:** cho biết tác dụng phụ của cập nhật và retention.

Có thể xem thông tin cluster và table qua các lệnh vận hành ở môi trường thử:

~~~bash
docker exec cassandra-events-lab nodetool status
docker exec cassandra-events-lab nodetool tablestats wide_column_lab.events_by_user_day
docker exec cassandra-events-lab nodetool tablestats wide_column_lab.events_by_user_all
~~~

Kết quả và tên metric phụ thuộc Cassandra/phiên bản. Thống kê cấp table **không tự cung cấp đầy đủ histogram kích thước mọi partition**; muốn biết partition bất thường cần bổ sung công cụ hoặc cách thu thập phù hợp. Trong thực hành có thể dùng nhật ký seed để biết phân bố logic và so sánh với dung lượng table.

Đo cả **mạng từ phía ứng dụng**. Với lịch sử 90 ngày, bảng B có thể yêu cầu nhiều lần đọc nhỏ rồi ghép; một query Cassandra nhanh không đảm bảo API nhanh nếu ứng dụng tạo quá nhiều request con hoặc trả payload quá lớn.

## 17. Chạy thí nghiệm time bucket: ngày so với giờ

Khi user nóng có hàng trăm nghìn event/ngày, bucket ngày có thể chưa đủ nhỏ. Giả sử ta thử một bảng mới `events_by_user_hour` với khóa:

~~~sql
PRIMARY KEY ((tenant_id, user_id, bucket_hour), occurred_at, event_id)
~~~

Ở đây `bucket_hour` có thể là text dạng `2026-11-14T08` hoặc một giá trị timestamp được chuẩn hóa về đầu giờ. Phải chọn kiểu dữ liệu, timezone và cách tạo bucket thống nhất trong writer/reader; không nên lấy một chuỗi giờ theo giờ địa phương ở ghi và UTC ở đọc.

Một định nghĩa cụ thể:

~~~sql
CREATE TABLE IF NOT EXISTS wide_column_lab.events_by_user_hour (
    tenant_id text,
    user_id text,
    bucket_hour text,
    occurred_at timestamp,
    event_id uuid,
    action text,
    resource_path text,
    status_code int,
    latency_ms int,
    PRIMARY KEY (
        (tenant_id, user_id, bucket_hour),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Để so sánh công bằng, nạp **cùng sự kiện** vào bảng theo giờ bằng một script có thể tái hiện, trong đó `bucket_hour` được tính từ thời điểm UTC của event.

| Kích thước bucket | User tạo 3.600 event/giờ | Đọc 24 giờ | Nhận xét |
|---|---:|---|---|
| Không bucket | Tăng mãi theo tuổi user | Một partition, có thể rất lớn | Ít fan-out, khó giới hạn tăng trưởng |
| Theo ngày | 86.400 event/partition/ngày | Một đến hai partition tùy biên | Cân bằng cho một số workload |
| Theo giờ | 3.600 event/partition/giờ | Khoảng 24–25 partition tùy biên | Partition nhỏ hơn, nhiều request hơn |

Các giá trị trên được tính từ tần suất giả định 1 event/giây? **Trong bảng này, 3.600 event/giờ tương ứng 1 event/giây**, và 86.400 event/ngày tương ứng cùng tốc độ. Với user có 10 event/giây, số hàng tăng gấp mười; với user gián đoạn, thấp hơn. Không thể chọn bucket bằng số giờ mà không biết kích thước hàng, phân bố và mẫu đọc.

Hãy đo lại W2 và W3 trên bucket giờ: p99 của user nóng có giảm không, độ trễ đọc 24 giờ và số request con tăng bao nhiêu, và toàn hệ có tạo quá nhiều partition nhỏ hay không?

## 18. Sự kiện đến muộn, trùng lặp và thứ tự nghiệp vụ

Lịch sử truy cập thường có **thời gian xảy ra sự kiện** (event time) khác với **thời gian hệ thống nhận được** (ingest time). Một thiết bị ngoại tuyến có thể gửi sự kiện của hôm qua vào hôm nay. Nếu partition được bucket theo `occurred_at`, sự kiện đến muộn phải được ghi vào bucket **của hôm qua**, không phải bucket ngày nhận.

~~~text
occurredAt  = 2026-11-13T23:59:50Z
receivedAt  = 2026-11-14T09:00:00Z
bucket_day  = 2026-11-13    (theo occurredAt UTC)
~~~

Như vậy, Q1 và Q2 theo thời gian xảy ra vẫn có nghĩa nhất quán. Nhưng nếu API cần “các sự kiện **vừa được nhận** gần đây”, mô hình theo `occurred_at` không trực tiếp đáp ứng; có thể cần một bảng đọc khác theo `ingest time`.

### 18.1. Retry và idempotency

Consumer có thể nhận cùng event hai lần do ít nhất một lần gửi thành công nhưng acknowledgment thất lạc. Nếu mỗi lần sinh `event_id` mới, cả hai bản ghi có thể cùng được lưu. Nếu cùng event luôn có cùng `tenant/user/day/occurred_at/event_id`, chúng nhắm vào cùng hàng logic. Tuy nhiên, việc một sự kiện có payload thay đổi cần quy tắc rõ: ghi đè, từ chối hay lưu version?

Bất biến của hệ thống sự kiện có thể là:

> Một event nguồn có định danh ổn định chỉ được tính một lần vào báo cáo, bất kể số lần consumer retry.

Để bảo vệ bất biến này trên nhiều bảng projection hoặc hệ tổng hợp, cần thiết kế riêng cơ chế nhận diện event, upsert/conditional write, replay, đối soát và cách xử lý khi ghi từng nơi thành công không đồng đều. Primary key của một bảng đơn lẻ chưa giải quyết toàn bộ bài toán đó.

### 18.2. Clustering order không phải total ordering toàn hệ

Trong một partition, Cassandra tổ chức hàng theo clustering key. Điều này **không** cho thứ tự toàn cục giữa tất cả partition, cũng không làm thời điểm event từ nhiều thiết bị trở nên đồng bộ tuyệt đối. Nếu hai hệ thống có clock sai lệch, thứ tự theo timestamp có thể khác thứ tự thực tế.

Khi cần thứ tự nghiệp vụ chặt, phải xác định source sequence, causal ID, phiên bản hoặc cơ chế hợp nhất phù hợp. Không suy ra tính đúng đắn của luồng nghiệp vụ chỉ vì query có `ORDER BY occurred_at DESC`.

## 19. Retention, TTL và tombstone trong dữ liệu sự kiện

Lịch sử truy cập thường cần chính sách giữ dữ liệu, ví dụ 30 hoặc 90 ngày. Cassandra hỗ trợ TTL cho dữ liệu, nhưng hết hạn không đồng nghĩa dữ liệu lập tức biến mất khỏi mọi tệp vật lý. TTL và xóa tạo ra **tombstone** theo cơ chế lưu trữ/replication, và lượng tombstone lớn có thể ảnh hưởng truy vấn, compaction và bảo trì.

Ví dụ thêm TTL 30 ngày tính từ thời điểm ghi theo thao tác minh họa:

~~~sql
INSERT INTO wide_column_lab.events_by_user_day
(tenant_id, user_id, bucket_day, occurred_at, event_id,
 action, resource_path, status_code, latency_ms)
VALUES
('t01', 'u-ttl-demo', '2026-11-14', '2026-11-14T09:00:00Z',
 550e8400-e29b-41d4-a716-446655440020,
 'VIEW', '/home', 200, 24)
USING TTL 2592000;
~~~

Lệnh này đặt TTL tương ứng 30 × 24 × 60 × 60 giây tính theo thời điểm ghi, không phải “tự xóa khi `occurred_at` cũ hơn 30 ngày”. Với event đến muộn, hai khái niệm khác nhau. Nếu chính sách là “lịch sử đúng 30 ngày theo event time”, ứng dụng phải tính hoặc quản lý expiry cho phù hợp với quy tắc đó.

Các câu hỏi cần đưa vào thực nghiệm:

- Với TTL cao và dữ liệu đến trễ, mốc hết hạn được tính thế nào?
- Khi một bucket hầu như toàn tombstone, đọc trang có còn nhanh không?
- Khi xóa nhiều hàng trong partition, compaction và dung lượng có thay đổi ra sao theo thời gian?
- Những khoảng thời gian bảo trì như repair, backup và khôi phục có phù hợp với retention?
- Có cần giữ dữ liệu gốc lâu hơn projection hiển thị hay không?

Không nên thử xóa hàng triệu row trên cluster production chỉ để “dọn dữ liệu cũ” mà chưa đo tác động. Chọn bucket và TTL phải được xem như **quyết định về vòng đời dữ liệu**, không chỉ tối ưu query.

## 20. Consistency và replication khi đọc lịch sử

Cùng partition key giúp định vị dữ liệu, nhưng không tự bảo đảm lần đọc luôn thấy giá trị mới nhất từ mọi replica. Cassandra là hệ phân tán có mức consistency cho đọc/ghi; hành vi phụ thuộc topology, replication factor, consistency level và tình trạng node.

Trong lab một node, consistency level `ONE` là cách minh họa cơ bản. Nhưng khi triển khai nhiều replica cần xác định:

- Sau khi API xác nhận ghi thành công, lần đọc nào phải thấy event mới?
- Mức độ chấp nhận dữ liệu trễ hoặc tạm thiếu ở trang lịch sử?
- Khi một replica lỗi, hệ thống cần ưu tiên sẵn sàng hay yêu cầu xác nhận nhiều replica?
- Các thao tác replay hoặc projection có thể tạo ra dữ liệu không đồng bộ trong bao lâu?
- Làm sao quan sát và phục hồi replication lag, repair hoặc dữ liệu thiếu?

Không thể suy chỉ từ `CLUSTERING ORDER BY`, `LIMIT` hay cùng một partition rằng hệ thống có bảo đảm thứ tự giao dịch và nhất quán mạnh. Cần đặc tả riêng **mức consistency** theo đường đọc/ghi cùng những trường hợp lỗi có thể xảy ra.

Thử nghiệm failover thật nên tiến hành trên một cụm nhiều node và ghi rõ RF, consistency level, lỗi node nào, thời điểm request timeout và trạng thái dữ liệu sau phục hồi. Đừng diễn giải kết quả lab một node thành kết luận cho cấu hình nhiều datacenter.

## 21. Diễn giải kết quả giả định và quyết định thiết kế

Giả sử một thí nghiệm đã chạy trên hai mô hình A/B với cùng tập dữ liệu lớn, cùng cấu hình và workload. Bảng sau **chỉ để minh họa cách ghi báo cáo**, không phải số liệu đo đã được thực hiện:

| Chỉ số giả định | A: không bucket | B: bucket ngày | Cách hiểu |
|---|---:|---:|---|
| Q1 p95 — đọc 20 event của một ngày | 12 ms | 10 ms | Cả hai đều đạt mục tiêu giả định |
| Q2 p99 — cửa sổ một giờ user nóng | 45 ms | 27 ms | B có lợi trong điều kiện thử này |
| Q3 p95 — lịch sử 30 ngày qua API | 35 ms | 110 ms | B chịu thêm fan-out/merge |
| Số partition đọc cho Q3 | 1 | Tới 30–31 | B đọc nhiều nhóm hơn |
| Số hàng/partition lớn nhất | 3.000.000 | 100.000 | B giới hạn độ lớn nhóm theo ngày |
| Write p95 | 18 ms | 17 ms | Chênh lệch nhỏ, cần lặp phép đo |
| Tỷ lệ lỗi | 0% | 0% | Chưa chứng minh mọi tải đều không lỗi |

Kết luận phù hợp khi có số đo thật sẽ là: **với workload và môi trường nêu rõ**, A tiết kiệm fan-out cho truy vấn lịch sử dài; B kiểm soát kích thước partition và có thể tốt hơn với query một ngày, nhưng phải có cơ chế ghép nhiều bucket. Mô hình nên chọn phụ thuộc yêu cầu nghiệp vụ nào quan trọng hơn.

Không được kết luận “bucket ngày luôn nhanh hơn” hoặc “một partition luôn tối ưu” từ một bảng minh họa. Trong một hệ thống thực, data skew, ổ đĩa, cache, compaction, số node và số người dùng đồng thời có thể làm kết quả khác.

### Mẫu báo cáo ngắn cho mỗi lần chạy

~~~text
Tên thí nghiệm:
Thời điểm và cấu hình:
Phiên bản Cassandra / driver:
Topology, RF, consistency level:
Seed và phân bố event/user:
Số ngày, tổng event, hot user ratio:
Schema và bucket:
Loại query:
Offered load / achieved throughput:
p50 / p95 / p99 / timeout / error rate:
Số partition mỗi request:
Dung lượng và phân bố partition:
CPU / RAM / disk / network:
Kết luận trong phạm vi dữ liệu thử:
Rủi ro và bước kiểm chứng tiếp theo:
~~~

Một kết luận dùng được phải để người khác **tái hiện** và **phản biện**. Nếu không lưu bối cảnh đo, chênh lệch 10 ms và 12 ms không đủ để quyết định kiến trúc.

## 22. Giám sát và xử lý sự cố khi đưa vào vận hành

Sau thực nghiệm, cần xác định những dấu hiệu hệ thống đang đi ra khỏi phạm vi đã kiểm chứng:

| Tình huống | Tín hiệu | Hành động điều tra |
|---|---|---|
| User nóng tạo quá nhiều event | p99 ghi tăng, tải một replica/node cao | Kiểm tra phân bố khóa, mức fan-out, bucket và hot partition |
| API lịch sử dài ngày chậm | Nhiều request con, p95 API cao nhưng mỗi query nhỏ nhanh | Giới hạn cửa sổ, giảm fan-out, điều chỉnh bucket/thiết kế cursor |
| Data tăng nhanh | Kích thước partition lớn nhất, disk và compaction tăng | Tính lại event/partition, thời lượng bucket, retention |
| Sự kiện thiếu trong một projection | Sai lệch số lượng giữa bảng gốc và bảng đọc | Kiểm tra retry, idempotency, backlog, replay/reconciliation |
| Query mới bị từ chối hoặc rất chậm | Thiếu partition key, có filtering/scan rộng | Viết lại access pattern, tạo bảng đọc phù hợp |
| Sau TTL truy vấn chậm | Tombstone và read latency tăng | Kiểm tra chính sách expiry, compaction, dạng query |
| Đọc dữ liệu vừa ghi không như kỳ vọng | Event không xuất hiện ngay ở một đường đọc | Kiểm tra consistency, replica, projection lag và mã event |

Runbook cho sự cố “lấy 20 event gần nhất tăng từ p95 30 ms lên 500 ms” có thể đi theo thứ tự:

1. Xác định phạm vi: một tenant, một user, một ngày hay toàn hệ? Kiểm tra query key thực tế.
2. Đối chiếu **p95 client**, error rate, timeout và số hàng trả với metric phía Cassandra.
3. Kiểm tra phân bố request theo user, số hàng/partition, node/replica đang nhận tải và khả năng xuất hiện hot key.
4. Xem kích thước bucket, tần suất ghi, CPU, disk I/O, compaction, tombstone, network và backlog.
5. Thử giảm tải có kiểm soát hoặc điều chỉnh giới hạn cửa sổ đọc; nếu cần thay schema, triển khai phiên bản bảng đọc mới với kế hoạch chuyển dữ liệu.
6. Đối chiếu trạng thái sau xử lý: độ trễ, tỷ lệ lỗi, tính đầy đủ của dữ liệu và số lượng request con.
7. Ghi lại điều kiện gây lỗi và cập nhật bài thực nghiệm để lần thiết kế tiếp theo tránh lặp lại.

Nếu ứng dụng có dữ liệu nhạy cảm trong lịch sử truy cập, cần kiểm soát quyền theo tenant/user ở tầng API, loại bỏ thông tin không cần thiết khỏi log, giới hạn retention và bảo vệ backup. Partition key có `tenant_id` là **đặc điểm định tuyến dữ liệu**, không tự nó là cơ chế xác thực/phân quyền.

## 23. Bài tập thực hành nâng cao

Sử dụng hai bảng A/B và script seed của bài học. Không cần tạo cụm nhiều node nếu mục tiêu chỉ là học về khóa và truy vấn; với nội dung yêu cầu replication hoặc failover, hãy mô tả giới hạn của môi trường khi chưa có đủ node.

### Bài 1 — Truy vấn đúng đường khóa

Viết CQL để:

1. Lấy 10 event gần nhất của `u-hot` ngày 14/11.
2. Lấy những event từ 09:00 đến trước 10:00 của `u-hot`.
3. Lấy event trong khoảng giao giữa ngày 13 và 14/11.
4. Giải thích tại sao `WHERE status_code = 500` không được phục vụ trực tiếp bởi `events_by_user_day`.
5. Đề xuất một bảng/projection phục vụ “30 lỗi HTTP mới nhất của tenant”.

Sau mỗi câu, chỉ ra partition key và clustering range được dùng, hoặc giải thích vì sao truy vấn phải đi qua nhiều partition.

### Bài 2 — Thiết kế bucket bằng số liệu

Giả sử có ba nhóm user:

| Nhóm | Số event/giây khi hoạt động | Khoảng thời gian đọc phổ biến |
|---|---:|---|
| Thường | 0,01 | 7 ngày |
| Tích cực | 1 | 1 ngày |
| Rất nóng | 25 | 1 giờ |

Với kích thước logic mỗi sự kiện 300 byte, hãy ước lượng số event và byte mỗi partition theo bucket ngày/giờ cho từng nhóm. So sánh fan-out của một query 7 ngày. Nêu vì sao một cấu hình bucket duy nhất có thể không phù hợp với mọi nhóm, và nguy cơ khi đưa thêm chiều shard vào partition key.

### Bài 3 — Benchmark có đối chứng

Nạp cùng dữ liệu vào A và B, tăng `ROWS_PER_DAY` và tỷ lệ user nóng theo từng lần chạy. Ghi:

- p50/p95/p99 của Q1 và Q2 khi chạy tuần tự, rồi khi chạy đồng thời.
- Throughput thực và error/timeout rate.
- Số partition mà API phải đọc cho Q3 ở 1, 7, 30 ngày.
- Dung lượng table và chỉ số vận hành liên quan.
- Nhận xét khi số hàng của `u-hot` tăng nhiều lần.

Giữ cùng môi trường khi so sánh; báo riêng thay đổi được áp dụng ở mỗi vòng.

### Bài 4 — Dữ liệu đến muộn và lặp

Giả lập một event có `occurredAt = 2026-11-13T23:55:00Z` nhưng được nhận ngày 14/11. Trả lời nó phải vào `bucket_day` nào, và API “những event vừa nhận” khác với “những event vừa xảy ra” ở đâu.

Gửi cùng event hai lần; giữ nguyên event ID và timestamp trong lần retry, rồi phân tích kết quả. Sau đó tạo một ID mới cho lần retry và giải thích tại sao có thể xuất hiện hai hàng dù sự kiện nghiệp vụ là một.

### Bài 5 — Chọn mô hình theo yêu cầu mới

Nghiệp vụ thêm ba yêu cầu:

- Tìm tất cả lần truy cập đường dẫn `/checkout` trong một giờ trên mọi user.
- Xem 50 event mới nhất của một user trong bất kỳ khoảng thời gian nào.
- Tạo thống kê tổng số lỗi 5xx mỗi phút cho mỗi tenant.

Hãy quyết định yêu cầu nào dùng được bảng B, yêu cầu nào cần truy vấn nhiều bucket, yêu cầu nào nên có projection hoặc pipeline tổng hợp. Nêu tác động tới ghi, tính nhất quán và khả năng tái tạo projection khi có sự cố.

## 24. Câu hỏi tự kiểm tra

1. Vì sao một hàng được nhận diện bằng **toàn bộ primary key** chứ không chỉ `user_id`?
2. Sự khác nhau giữa `PRIMARY KEY ((tenant_id, user_id), occurred_at)` và `PRIMARY KEY (tenant_id, user_id, occurred_at)` là gì?
3. Tại sao `CLUSTERING ORDER BY (occurred_at DESC)` giúp đọc event mới nhất trong **một partition**, nhưng không sắp xếp toàn cục mọi tenant?
4. Nếu truy vấn một ngày rất nhanh nhưng API 90 ngày lại chậm, cần đo thêm yếu tố nào ngoài latency của một câu `SELECT`?
5. Vì sao sự kiện đến trễ nên được bucket theo `occurred_at` khi nghiệp vụ yêu cầu lịch sử theo thời điểm xảy ra?
6. Cần điều kiện gì để retry cùng một event không tạo thêm một hàng logic khác?
7. Nếu một tenant tạo phần lớn lỗi của hệ thống, bảng `errors_by_tenant_day` gặp nguy cơ gì?
8. TTL tính theo thời điểm ghi khác chính sách “xóa sau 30 ngày tính từ event time” thế nào?
9. Nếu cluster có nhiều replica, tại sao khóa phân vùng tốt chưa đủ xác định yêu cầu đọc thấy ghi vừa hoàn tất?
10. Một benchmark trên một node và 21.000 event có thể chứng minh điều gì, và còn thiếu gì để quyết định kiến trúc production?

## 25. Điều cần giữ lại sau thực nghiệm

Điểm trọng tâm của mô hình cột rộng là biến **mẫu truy cập theo khóa và thời gian** thành cách bố trí dữ liệu có thể dự đoán được. `Partition key` quyết định phạm vi gom và định vị dữ liệu; `clustering columns` tạo thứ tự hàng trong nhóm; bucket thời gian đặt giới hạn tăng trưởng cho một nhóm nhưng tăng số partition cần đọc khi truy vấn dài ngày.

Khi thực hành, hãy luôn giữ cùng một chuỗi lý luận: **viết truy vấn → chọn khóa → ghi dữ liệu đại diện → kiểm tra kết quả theo thứ tự và thời gian → đo tải/độ trễ → xem phân bố partition → cân nhắc vận hành và dữ liệu đến trễ**. Kết quả tốt không chỉ là CQL chạy được, mà là giải thích được vì sao thiết kế đáp ứng Q1–Q3, vì sao Q4 cần đường dữ liệu khác, và bằng chứng nào cho thấy chi phí đọc/ghi vẫn chấp nhận được khi quy mô tăng.
