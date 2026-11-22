# Chọn clustering column để hỗ trợ sắp xếp hoặc lọc theo khoảng

## Mục tiêu bài học

Trong Apache Cassandra, sau khi xác định được **partition key** từ đường truy cập chủ đạo, ta cần quyết định cách bố trí các hàng **bên trong mỗi partition**. Đó là vai trò của **clustering column**: cùng với thứ tự clustering, nó quyết định các truy vấn có thể đọc dữ liệu theo thứ tự và theo khoảng giá trị mà không phải quét, lọc hay sắp xếp tùy ý ở ứng dụng.

Bài học thuộc chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trọng tâm là chọn và sắp xếp clustering column dựa trên yêu cầu đọc thực tế, viết CQL đúng với mô hình wide-column phân tán, phân trang an toàn và vận dụng kết quả từ ứng dụng Java. Các khái niệm replication, consistency, compaction và repair được nhắc đến khi chúng ảnh hưởng đến đánh giá hiệu năng hoặc vận hành.

Sau khi hoàn thành, bạn có thể:

- Phân biệt **partition key**, **clustering column** và **regular column** trong `PRIMARY KEY`.
- Chọn thứ tự clustering phù hợp với các truy vấn lấy **bản ghi mới nhất/cũ nhất**, lọc theo **khoảng thời gian** hoặc một **tiền tố bằng nhau**.
- Giải thích hạn chế của `ORDER BY`, giới hạn của `WHERE` trên clustering column và vì sao một số query shape cần bảng riêng.
- Viết `CREATE TABLE`, `SELECT`, `ORDER BY` và khoảng `[from, to)` cho một đường đọc thực tế.
- Nhận diện các vấn đề về ranh giới bucket, dữ liệu trùng timestamp, `LIMIT`, paging, tombstone và cập nhật khóa.

## 1. Clustering column nằm ở đâu trong mô hình Cassandra?

Xét một hệ thống nhận sự kiện từ thiết bị IoT. API phổ biến là “xem các sự kiện của **một thiết bị trong một ngày**, mới nhất trước”. Một schema ứng viên:

```sql
CREATE TABLE device_events_by_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    severity text,
    event_type text,
    reading_value double,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

| Cấu phần | Cột | Vai trò |
| --- | --- | --- |
| **Partition key ghép** | `(tenant_id, device_id, day_bucket)` | Xác định partition logic, token và tập replica tương ứng |
| **Clustering column thứ nhất** | `event_time` | Định thứ tự thời gian và hỗ trợ truy vấn theo khoảng |
| **Clustering column thứ hai** | `event_id` | Phân biệt các sự kiện có cùng `event_time` |
| **Regular column** | `severity`, `event_type`, `reading_value` | Giá trị hiển thị; không tự tạo đường lọc/sắp xếp tối ưu |

Cặp ngoặc đơn lồng nhau trong `PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)` rất quan trọng: ba giá trị đầu **cùng tạo một partition key**, trong khi hai giá trị sau là **clustering key**. Đây không phải năm index độc lập.

Một partition có thể hình dung như sau:

```text
Partition key = (tenant-A, device-42, 2026-11-21 UTC)
    (10:04:10.000, event-08) -> severity=INFO, reading=21.7
    (10:04:10.000, event-03) -> severity=WARN, reading=31.5
    (10:02:40.000, event-07) -> severity=INFO, reading=20.8
    (09:59:12.000, event-06) -> severity=ERROR, reading=0.0

Partition key = (tenant-A, device-42, 2026-11-22 UTC)
    (00:01:05.000, event-09) -> severity=INFO, reading=21.1
```

Các ID ở sơ đồ là nhãn minh họa; thứ tự thực tế khi `event_time` trùng dựa trên **giá trị khóa `uuid`** của Cassandra, không phải tên chuỗi `event-08`, `event-03`. Cùng một thiết bị nhưng khác ngày tạo **partition khác**; cùng partition key nhưng khác cặp `(event_time, event_id)` tạo **hàng khác**.

**Nguyên tắc:** partition key quyết định **đọc ở đâu**, clustering column quyết định **đọc những hàng nào và theo thứ tự nào trong partition đó**. Khi một API cần đọc dữ liệu trên nhiều partition, clustering column không tự tạo ra thứ tự toàn cục giữa chúng.

## 2. Bắt đầu từ hợp đồng truy vấn

Đừng chọn clustering column chỉ vì một cột “trông có vẻ quan trọng”. Hãy ghi lại chính xác kiểu đọc (query shape):

| ID | Yêu cầu | Điều kiện bắt buộc | Điều kiện/sắp xếp thêm | Giới hạn |
| --- | --- | --- | --- | --- |
| Q01 | Xem các sự kiện mới nhất trong ngày | Tenant, device, ngày UTC | `event_time DESC`, nếu trùng dùng `event_id DESC` | 30 hàng |
| Q02 | Xem sự kiện từ 09:00 đến trước 10:00 | Tenant, device, ngày UTC | `event_time >= from` và `event_time < to`, mới nhất trước | 100 hàng |
| Q03 | Xem các sự kiện cũ nhất trong ngày | Tenant, device, ngày UTC | `event_time ASC`, `event_id ASC` | 30 hàng |
| Q04 | Xem sự kiện mức `ERROR` trong ngày | Tenant, device, ngày UTC, severity | Chỉ mức `ERROR`, mới nhất trước | 30 hàng |
| Q05 | Xem sự kiện có giá trị đo cao nhất | Tenant, device, ngày UTC | `reading_value DESC` | 30 hàng |
| Q06 | Xem lịch sử 7 ngày | Tenant, device, 7 ngày UTC | Mới nhất trước trên toàn khoảng | 50 hàng |

Với bảng ví dụ ở phần 1:

- **Q01–Q03** cùng chia sẻ một partition và các kiểu đọc theo `event_time`, có thể phục vụ bằng **một bảng**.
- **Q04** có điều kiện bắt buộc theo `severity`; trong bảng hiện tại đây là regular column, nên không có đường đọc chính được thiết kế.
- **Q05** muốn sắp theo `reading_value`, không thuộc clustering key nên không thể yêu cầu `ORDER BY reading_value DESC` như SQL tùy ý.
- **Q06** trải qua nhiều ngày, cần nhiều partition và quy tắc hợp nhất ở ứng dụng hoặc một bảng khác nếu đó là đường đọc chủ đạo.

Khi chọn clustering, cần làm rõ “mới nhất” dựa trên **thời điểm sự kiện** (`event_time`), **thời điểm nhận** (`ingested_at`) hay **thời điểm cập nhật** (`updated_at`). Ba khái niệm này khác nhau khi sự kiện đến muộn hoặc bị sửa.

## 3. Chọn clustering column theo thứ tự đọc

### 3.1. Thứ tự mặc định được khai báo khi tạo bảng

`WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)` đặt thứ tự clustering mặc định trong **mỗi partition**. Với truy vấn Q01:

```sql
SELECT event_time, event_id, severity, event_type, reading_value
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 30;
```

Các dấu `?` là bind marker phù hợp với **prepared statement** của ứng dụng. Khi chạy trực tiếp bằng `cqlsh`, cần truyền literal CQL hợp lệ thay vì `?`.

Q01 có **toàn bộ partition key** và bảng đã tổ chức hàng theo thời gian giảm dần; vì vậy không cần viết thêm `ORDER BY`. Cassandra có thể đọc theo thứ tự clustering đã định nghĩa, giới hạn số hàng trả về.

Nếu mặc định luôn cần mới nhất trước, chọn `DESC` trong schema thể hiện trực tiếp đường đọc đó. Tuy nhiên, Cassandra cũng hỗ trợ đọc đảo chiều của clustering order phù hợp; lựa chọn mặc định cần dựa trên tải và phép đo, không chỉ từ giả định rằng một chiều chắc chắn nhanh hơn trong mọi phiên bản hay cấu hình.

### 3.2. Khi nhiều hàng có cùng timestamp

Nếu chỉ dùng `PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time)`, mỗi partition **chỉ có một hàng cho mỗi giá trị `event_time`**. Hai sự kiện đến cùng millisecond và cùng partition key sẽ có **cùng khóa hàng**, nên ghi sau có thể cập nhật/ghi đè các cột tương ứng của cùng hàng logic.

Bổ sung `event_id` vào clustering key giúp hai sự kiện khác ID cùng thời điểm có thể cùng tồn tại:

```sql
PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)
```

Điều kiện này chỉ bảo đảm phân biệt nếu `event_id` thực sự **duy nhất trong phạm vi khóa tương ứng**. Dùng UUID làm tie-breaker tạo thứ tự xác định theo giá trị khóa, nhưng thứ tự UUID ngẫu nhiên **không biểu thị thứ tự nhân quả** giữa các sự kiện có timestamp bằng nhau.

Nếu hệ thống cần thứ tự nghiệp vụ tuyệt đối, hãy thu thập thêm yêu cầu về **sequence number**, độ chính xác timestamp hoặc nguồn cấp ID, rồi thiết kế cột và thứ tự phù hợp. Không mặc nhiên xem `UUID` ngẫu nhiên là sequence.

### 3.3. Đọc ngược thứ tự để lấy bản ghi cũ nhất

Q03 có thể dùng lại bảng khi đảo **toàn bộ** chiều clustering:

```sql
SELECT event_time, event_id, severity, event_type
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
ORDER BY event_time ASC, event_id ASC
LIMIT 30;
```

Với bảng có thứ tự mặc định `(event_time DESC, event_id DESC)`, câu này thể hiện chiều đảo ngược. Trong CQL, `ORDER BY` có các hạn chế chặt chẽ: nó áp dụng cho clustering columns theo thứ tự schema cho phép, với partition key được ràng buộc thích hợp; không thể đảo/sắp xếp tùy ý từng cột và không thể sắp theo regular column bất kỳ.

**Lưu ý vận hành:** nếu Q03 thường xuyên đọc trên partition lớn, cần kiểm chứng độ trễ và ảnh hưởng của chiều đọc ngược bằng dữ liệu đại diện. Tính hợp lệ về CQL chưa phải cam kết hiệu năng.

## 4. Chọn clustering column theo điều kiện khoảng

### 4.1. Thiết kế thời gian làm cột clustering đầu tiên

Q02 muốn xem sự kiện trong khoảng thời gian của **một partition thiết bị/ngày**:

```sql
SELECT event_time, event_id, severity, event_type, reading_value
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
```

Ở đây:

1. `tenant_id`, `device_id` và `day_bucket` định vị một partition.
2. `event_time` là clustering column **đầu tiên**, nên điều kiện khoảng xác định một **lát dữ liệu có thứ tự** trong partition.
3. `event_id` phân định các hàng trùng `event_time`.

Quy ước `[fromInclusive, toExclusive)` giúp không đếm trùng khi ghép các khoảng liên tiếp: sự kiện đúng 10:00:00 sẽ thuộc khoảng `[10:00, 11:00)` nhưng không thuộc `[09:00, 10:00)`.

Khoảng này phải được hiểu theo cùng múi giờ và cùng quy tắc bucket với đường ghi, ví dụ ngày UTC. Nếu `from` là 23:30 ngày 21 và `to` là 00:30 ngày 22, một câu truy vấn có `day_bucket = 2026-11-21` **không** thể trả sự kiện của ngày 22. Ứng dụng cần tách thành hai lần đọc:

```text
(day_bucket = 2026-11-21, event_time ∈ [21 23:30, 22 00:00))
(day_bucket = 2026-11-22, event_time ∈ [22 00:00, 22 00:30))
```

Thời điểm ở đây là UTC; các con số chỉ để minh họa. Không giả định Cassandra tự suy ra và quét các ngày liền kề từ điều kiện `event_time`.

### 4.2. Quy tắc tiền tố và thứ tự clustering

Xét thiết kế tổng quát:

```sql
PRIMARY KEY ((tenant_id, device_id, day_bucket), severity, event_time, event_id)
```

Trong cấu trúc này, thứ tự clustering là `severity`, sau đó `event_time`, sau đó `event_id`. Để đọc một **khoảng thời gian theo một severity đã biết**, truy vấn thường sử dụng điều kiện **bằng** trên cột clustering đứng trước:

```sql
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND severity = ?
  AND event_time >= ?
  AND event_time < ?
```

Phạm vi trên `event_time` lúc này nằm trong một tập hàng có cùng giá trị `severity`.

Ngược lại, yêu cầu “tất cả severity từ 09:00 đến 10:00 theo thời gian” **không** có cùng đường đọc liền mạch trong bảng có `severity` đứng trước. Bỏ qua clustering column đầu tiên rồi lọc theo cột phía sau thường không tạo truy vấn range trực tiếp hợp lệ/hiệu quả. Tương tự, sau khi đặt điều kiện khoảng trên một clustering column, không nên giả định các cột clustering đứng sau vẫn có thể được lọc tùy ý với hiệu quả tương đương.

Quy tắc làm việc an toàn khi thiết kế query-driven:

- Các clustering column ở **tiền tố** thường được ràng buộc bằng (`=`) theo đúng thứ tự.
- Cột tiếp theo có thể dùng **điều kiện khoảng** (`>`, `>=`, `<`, `<=`) khi CQL chấp nhận.
- Mọi trường hợp muốn bỏ qua một phần tiền tố, kết hợp nhiều khoảng hoặc sắp theo thứ tự khác phải được đánh giá bằng **truy vấn cụ thể với schema và phiên bản Cassandra mục tiêu**.

Đây là quy tắc thực dụng cho mô hình đọc có thể dự đoán chi phí; CQL có thêm các dạng điều kiện và toán tử đặc biệt theo từng phiên bản, không nên suy diễn một quy tắc tổng quát cho mọi cú pháp.

### 4.3. Lọc khoảng trên clustering khác thời gian

Clustering column có thể là **số thứ tự**, **phiên bản**, **ngày**, **giá trị đo** hoặc các loại có thứ tự khác nếu đường đọc chủ đạo thật sự dựa vào khoảng đó.

Ví dụ một hệ thống giá cần lấy các phiên bản của một tài liệu trong một nhánh:

```sql
CREATE TABLE document_versions_by_branch (
    tenant_id text,
    document_id uuid,
    branch text,
    version_no bigint,
    change_id uuid,
    author_id uuid,
    summary text,
    PRIMARY KEY ((tenant_id, document_id, branch), version_no, change_id)
) WITH CLUSTERING ORDER BY (version_no DESC, change_id DESC);

SELECT version_no, change_id, author_id, summary
FROM document_versions_by_branch
WHERE tenant_id = ?
  AND document_id = ?
  AND branch = ?
  AND version_no >= ?
  AND version_no < ?;
```

Ở đây lựa chọn `version_no` làm clustering column đầu tiên xuất phát từ yêu cầu lấy phiên bản mới nhất và lọc một khoảng số phiên bản. Một bảng khác dành cho tìm kiếm theo tác giả sẽ có đường truy cập khác; không thêm `WHERE author_id = ?` vào bảng này rồi mong đợi hiệu năng tương tự.

## 5. Khi chọn sai thứ tự clustering

### 5.1. Đặt severity trước thời gian

Một sản phẩm có màn hình “xem sự kiện `ERROR` mới nhất của thiết bị trong ngày”. Với trường hợp **severity là bộ lọc bắt buộc** và thường xuyên dùng, có thể thiết kế bảng khác:

```sql
CREATE TABLE device_events_by_severity_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    severity text,
    event_time timestamp,
    event_id uuid,
    event_type text,
    reading_value double,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), severity, event_time, event_id)
) WITH CLUSTERING ORDER BY (severity ASC, event_time DESC, event_id DESC);

SELECT event_time, event_id, event_type, reading_value
FROM device_events_by_severity_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND severity = 'ERROR'
LIMIT 30;
```

Với một severity cụ thể, các hàng có giá trị đó được đọc theo thời gian giảm dần. Nhưng bảng này **không** tạo sẵn một danh sách **30 sự kiện mới nhất của tất cả severity** theo một trục `event_time` duy nhất: các hàng trước hết được nhóm/sắp theo `severity`. Vì vậy, nếu cả hai kiểu truy vấn đều quan trọng, cân nhắc duy trì **hai bảng theo hai đường đọc** và xác minh chi phí ghi nhân bản.

Có hai cách thiết kế khác nhau cho Q04:

| Mô hình | Partition key | Clustering | Mạnh ở truy vấn |
| --- | --- | --- | --- |
| Nhóm thời gian | `(tenant_id, device_id, day_bucket)` | `event_time, event_id` | Mới nhất/cũ nhất và khoảng thời gian của mọi severity |
| Nhóm severity trong cùng partition | `(tenant_id, device_id, day_bucket)` | `severity, event_time, event_id` | Một severity đã biết, sau đó lọc/sắp theo thời gian |

Một biến thể có thể đưa `severity` vào **partition key**, chẳng hạn `(tenant_id, device_id, day_bucket, severity)`, để mỗi severity ở partition riêng. Việc chọn severity là **partition key** hay **clustering column** là một quyết định về phân bố dữ liệu và tải: cách thứ hai cùng các severity nằm trong một partition, cách thứ nhất fan-out theo severity và có thể giảm kích thước từng partition nhưng tăng số partition cần đọc nếu muốn mọi severity.

### 5.2. Đặt ID trước thời gian

```sql
-- Ví dụ có đường đọc khác:
PRIMARY KEY ((tenant_id, device_id, day_bucket), event_id, event_time)
```

Với khóa này, các sự kiện trước hết được tổ chức theo `event_id`. Nó có thể phù hợp các lượt tìm một `event_id` cụ thể đã biết, nhưng **không** tự phục vụ việc liệt kê 30 sự kiện gần nhất hoặc tìm theo khoảng `event_time` trên mọi ID trong cùng partition. Khi thời gian là bộ lọc/kênh sắp xếp chủ đạo, hãy đặt thời gian **trước** ID.

### 5.3. Đặt cột ít ý nghĩa vào trước trục đọc chính

Một trường hợp phổ biến là đặt `event_type` lên trước `event_time` vì cột đó xuất hiện trong nhiều màn hình. Nếu màn hình chính không cung cấp `event_type` trong mọi lần gọi, nó sẽ làm hỏng đường đọc theo thời gian. Đừng cho một cột vào clustering key chỉ vì nó “hay được hiển thị”; chỉ làm vậy khi yêu cầu lọc/sắp xếp và tần suất truy vấn biện minh cho thứ tự đó.

## 6. Phân biệt `CLUSTERING ORDER BY` và `ORDER BY`

| Câu lệnh/khái niệm | Khi sử dụng | Ảnh hưởng |
| --- | --- | --- |
| `WITH CLUSTERING ORDER BY (...)` | Trong `CREATE TABLE` | Khai báo **thứ tự clustering mặc định** trong mỗi partition |
| `ORDER BY ...` | Trong `SELECT` hợp lệ | Yêu cầu thứ tự đọc phù hợp với clustering key, thường là mặc định hoặc đảo chiều được hỗ trợ |
| `WHERE` trên clustering column | Trong `SELECT` với partition key thích hợp | Giới hạn một lát hàng theo thứ tự khóa |
| `ORDER BY` theo regular column | Không được hỗ trợ tùy ý | Không dùng `ORDER BY reading_value DESC` trên bảng nhóm thời gian |
| Sắp xếp kết quả từ nhiều partition | Tại tầng ứng dụng/đường dữ liệu phù hợp | Cassandra không tự đảm bảo một thứ tự toàn cục theo CQL cho mọi partition |

Một câu truy vấn thực tế **không nên** dựa vào việc “đọc toàn bảng rồi ORDER BY” như một thói quen từ SQL quan hệ. Trong Cassandra, cấu trúc partition/clustering phải được chọn sao cho kết quả cần đọc đã nằm trên một đường truy cập xác định.

### Bảng đối chiếu các kiểu CQL

Giả sử đang dùng `device_events_by_day` với `PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)`:

| Kiểu truy vấn | Đánh giá | Lý do |
| --- | --- | --- |
| Đủ partition key, `LIMIT 30` | Phù hợp | Đọc phần đầu của một partition theo clustering |
| Đủ partition key, `event_time >= ? AND event_time < ?` | Phù hợp | Đọc khoảng trên clustering column đầu tiên |
| Đủ partition key, đảo `event_time ASC, event_id ASC` | Phù hợp | Đọc ngược thứ tự clustering trong partition |
| Chỉ `tenant_id = ?`, thiếu device/ngày | Không có đường đọc một partition | Thiếu thành phần của composite partition key |
| Đủ partition key, `event_id = ?` nhưng không có `event_time` | Không phù hợp với đường đọc chính | Bỏ qua clustering column đứng trước |
| Đủ partition key, `severity = 'ERROR'` | Không được tối ưu mặc định theo schema | `severity` là regular column |
| `ORDER BY reading_value DESC` | Không hợp lệ như yêu cầu sắp xếp clustering thông thường | `reading_value` không phải clustering column |

Một số câu không phù hợp có thể được viết lại bằng index, cơ chế lọc khác hoặc `ALLOW FILTERING` tùy phiên bản, nhưng **cú pháp chạy được không đồng nghĩa đọc ít dữ liệu**. Khi đây là yêu cầu chính, ưu tiên xét bảng/projection hoặc kiến trúc tìm kiếm phù hợp và đo hiệu năng thực tế.

## 7. Khoảng thời gian, ranh giới và độ chính xác dữ liệu

### 7.1. Thống nhất thời gian lưu và thời gian hỏi

Trước khi chọn `event_time` làm clustering key, thống nhất:

1. **Nguồn thời gian:** thiết bị phát sự kiện hay server tiếp nhận?
2. **Độ chính xác:** Cassandra `timestamp` lưu mốc thời gian với độ chính xác millisecond; không giả định có thứ tự microsecond/nanosecond chỉ từ kiểu này.
3. **Múi giờ:** lưu và tính `day_bucket` theo một quy ước nhất quán, ví dụ UTC.
4. **Sự kiện đến muộn:** vẫn thuộc bucket của thời điểm xảy ra nếu khóa được xác định từ `event_time`.
5. **Sự kiện bị sửa thời gian:** thay đổi giá trị trong primary key không phải một `UPDATE` thông thường lên khóa; thường cần xóa hàng theo khóa cũ và ghi hàng mới theo khóa mới, cùng cơ chế khôi phục lỗi.

Ví dụ một sự kiện xảy ra `2026-11-21T23:59:59Z` nhưng được nhận sau nửa đêm. Nếu hệ thống định nghĩa `day_bucket` theo `event_time`, nó vẫn thuộc partition ngày 21. Nếu một dịch vụ ghi theo `ingested_at` còn dịch vụ đọc theo `event_time`, bản ghi sẽ khó tìm hoặc rơi vào partition không mong đợi.

### 7.2. Giới hạn kết quả không bảo đảm chi phí đọc nhỏ

`LIMIT 30` chỉ giới hạn **số hàng trả về** của câu truy vấn. Nếu partition chứa rất nhiều tombstone từ TTL/xóa, Cassandra có thể phải đọc nhiều dữ liệu không còn hiển thị trước khi trả đủ hàng. Do đó, việc chọn clustering order phải đi cùng dự báo về:

- Kích thước và số hàng lớn nhất của **một partition**.
- Tốc độ ghi vào partition nóng nhất.
- TTL, xóa, sửa dữ liệu và số tombstone.
- Độ rộng khoảng cần đọc, số partition mỗi API được phép truy cập.
- Mục tiêu độ trễ p95/p99 và số hàng/byte thực tế trả về.

Compaction có thể ảnh hưởng tới số SSTable và chi phí đọc; repair giúp đảm bảo dữ liệu giữa replica được sửa chữa theo cơ chế Cassandra. Chúng không thể biến một câu truy vấn thiếu đường clustering phù hợp thành truy vấn một lát dữ liệu nhỏ.

### 7.3. Phân trang nhiều lần

Cần phân biệt ba mức:

| Giới hạn | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `LIMIT 30` của CQL | Tổng số hàng tối đa trong kết quả của câu truy vấn | Màn preview chỉ cần 30 sự kiện |
| `page size = 30` của Java driver | Số hàng mục tiêu mỗi trang do driver lấy | Người dùng bấm “tải thêm” |
| Giới hạn API | Số ngày/bucket, tổng số trang, dữ liệu tối đa cho một yêu cầu | Không cho đọc 5 năm trong một request |

Nếu muốn nhiều trang 30 hàng liên tiếp, dùng cơ chế paging của driver với câu truy vấn phù hợp. Một `SELECT ... LIMIT 30` không tự cung cấp vô hạn trang kế tiếp, mỗi trang lại có 30 hàng mới.

**Paging state** là dữ liệu opaque gắn với câu truy vấn và các giá trị bind; không chỉnh sửa, không dùng state cho partition/bộ lọc khác và không coi các trang là snapshot cố định khi có ghi/xóa đồng thời. Khi API chuyển paging state qua client, cần bảo vệ tính toàn vẹn token và kiểm soát quyền truy cập cho tenant, device và khoảng thời gian trong mọi lần gọi.

## 8. Ví dụ gọi truy vấn khoảng từ Java

Ví dụ dưới đây dùng **DataStax Java Driver 4.x** và một prepared statement phục vụ Q02. Các giá trị ngày và khoảng thời gian do ứng dụng tính theo cùng quy tắc UTC với dữ liệu đã ghi.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class DeviceEventReader {
    private final CqlSession session;
    private final PreparedStatement rangeQuery;

    public DeviceEventReader(CqlSession session) {
        this.session = session;
        this.rangeQuery = session.prepare(
            "SELECT event_time, event_id, severity, event_type, reading_value " +
            "FROM device_events_by_day " +
            "WHERE tenant_id = ? AND device_id = ? AND day_bucket = ? " +
            "AND event_time >= ? AND event_time < ?"
        );
    }

    public ResultSet readRange(
        String tenantId,
        UUID deviceId,
        LocalDate utcDay,
        Instant fromInclusive,
        Instant toExclusive
    ) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Khoang thoi gian khong hop le");
        }

        // Giả định caller đã kiểm tra hai mốc thuộc cùng bucket utcDay.
        BoundStatement statement = rangeQuery
            .bind(tenantId, deviceId, utcDay, fromInclusive, toExclusive)
            .setPageSize(50);
        return session.execute(statement);
    }
}
```

Trong driver 4.x, `LocalDate` ánh xạ kiểu CQL `date`, còn `Instant` ánh xạ `timestamp`. Lớp ứng dụng cần **thực hiện** kiểm tra bucket, giới hạn khoảng đọc và kiểm tra quyền truy cập; chú thích trong ví dụ là giả định về caller, không phải một phép kiểm tra đã được viết. Nếu khoảng qua nhiều ngày, hãy tách theo bucket rồi xử lý thứ tự/phân trang cho nhiều partition.

Một `CqlSession` nên được quản lý theo vòng đời dịch vụ và có thể dùng chung cho nhiều truy vấn; tránh tạo session mới ở mỗi lần gọi. Cấu hình timeout, consistency level, retry và việc lặp `ResultSet` cần phù hợp mục tiêu API. Với trang kết quả, việc lặp toàn bộ một `ResultSet` đồng bộ có thể kích hoạt tải thêm trang, vì vậy endpoint chỉ trả một trang phải kiểm soát rõ số hàng đã duyệt và trạng thái trang tiếp theo.

## 9. Ảnh hưởng tới replication, consistency và dữ liệu nhân bản

Clustering key xác định **thứ tự và định danh hàng trong partition**, nhưng không tự quyết định mức nhất quán. Replication factor và chiến lược đặt replica ở keyspace quyết định các bản sao; consistency level của từng thao tác đọc/ghi quyết định mức phản hồi từ các replica. Chọn `LOCAL_QUORUM` có thể phù hợp một số topology và SLA cụ thể, nhưng **không sửa** được truy vấn muốn `ORDER BY reading_value DESC` trên bảng không có đường clustering phù hợp.

Nếu duy trì hai bảng `device_events_by_day` và `device_events_by_severity_day` cho hai query shape, đường ghi phải duy trì cả hai. Khi `severity` thay đổi, trong bảng thứ hai nó là **một phần primary key**: cần xóa hàng ở khóa severity cũ và ghi hàng tại khóa severity mới, đồng thời cập nhật representation ở bảng thứ nhất. Điều này có thể tạo tombstone và các bảng có thể nhất thời không đồng bộ nếu một lượt ghi lỗi.

Cassandra không tự duy trì một phép `JOIN` hoặc giao dịch SQL thông thường xuyên mọi projection do ứng dụng quản lý. Cần đặt quy trình retry có thể lặp an toàn, cơ chế đối soát và xử lý sự kiện đến muộn hoặc trùng. Việc chọn consistency level cao hơn **không tự đảm bảo** mọi bảng nhân bản được cập nhật tức thời như một transaction duy nhất.

## 10. Checklist chọn clustering column

| Câu hỏi | Dấu hiệu đã làm rõ | Nếu chưa rõ |
| --- | --- | --- |
| Partition key đã xác định chưa? | Caller luôn truyền đủ tenant, device, bucket | Chốt lại đường truy cập trước khi chọn clustering |
| Trục sắp xếp là gì? | `event_time DESC`, tie-break `event_id DESC` | Phân biệt event time, ingest time, updated time |
| Có lọc khoảng không? | `event_time >= from AND event_time < to` | Xác định cột range và tiền tố clustering |
| Cột đứng trước cột range có được ràng buộc bằng? | Ví dụ `severity = 'ERROR'` khi severity đứng trước time | Cân nhắc đổi thứ tự cột hoặc bảng riêng |
| Truy vấn cần sắp trên nhiều partition không? | Có quy tắc fan-out/hợp nhất rõ | Không dựa vào `ORDER BY` toàn cục |
| Có yêu cầu sort theo regular column không? | Được đánh dấu query shape riêng | Không hứa hẹn `ORDER BY` tùy ý |
| Có sự kiện cùng timestamp không? | Có `event_id`/sequence phân định | Tránh nhiều sự kiện cùng primary key |
| Khoảng thời gian vượt bucket không? | Đường đọc tách partition rõ | Sửa quy tắc phân rã theo ngày/giờ |
| Giới hạn kết quả/phân trang thế nào? | Phân biệt `LIMIT`, page size, giới hạn API | Không giả định `LIMIT` là rẻ tuyệt đối |
| Đã đo trên tải và dữ liệu đại diện chưa? | Có p95/p99, partition lớn, tombstone, truy vấn đảo chiều | Không kết luận chỉ vì CQL chạy được |

## 11. Bài tập thực hành

Một ứng dụng Java lưu lịch sử thay đổi giá theo cửa hàng. Mỗi lần thay đổi có:

```text
tenant_id, store_id, product_id, day_bucket,
changed_at, change_id, price, currency, actor_id
```

Các truy vấn:

1. **R1:** Lấy 20 lần đổi giá mới nhất của một sản phẩm trong một cửa hàng/ngày.
2. **R2:** Lấy các lần đổi giá trong khoảng `[09:00, 12:00)` của cùng sản phẩm/ngày.
3. **R3:** Lấy 20 lần đổi giá cũ nhất của cùng sản phẩm/ngày.
4. **R4:** Lấy 20 lần đổi giá có `price` cao nhất của cùng sản phẩm/ngày.
5. **R5:** Lấy 50 lần đổi giá mới nhất của một sản phẩm trên **mọi cửa hàng** trong tenant.

Yêu cầu:

1. Đề xuất partition key cho R1–R3 dựa trên các trường mà caller luôn biết; giải thích vai trò `product_id`.
2. Chọn clustering key hỗ trợ R1/R2, xử lý khi nhiều thay đổi có cùng `changed_at`.
3. Viết câu `CREATE TABLE` và ba câu `SELECT` phù hợp cho R1/R2/R3.
4. Giải thích vì sao R4 và R5 không tự có cùng đường đọc, và cách tiếp cận nếu hai truy vấn là nghiệp vụ quan trọng.
5. Với khoảng bắt đầu 23:00 ngày 21 và kết thúc 01:00 ngày 22 UTC, mô tả số bucket và cách tách khoảng.

**Gợi ý đối chiếu:** Một schema ứng viên cho R1–R3 là `PRIMARY KEY ((tenant_id, store_id, product_id, day_bucket), changed_at, change_id)` với `CLUSTERING ORDER BY (changed_at DESC, change_id DESC)`. R2 dùng `changed_at >= ? AND changed_at < ?`; R3 đảo cả hai cột clustering sang `ASC`. R4 cần sắp theo `price`, có thể cần đường truy cập khác; R5 thiếu `store_id` và còn muốn thứ tự chung giữa các cửa hàng. Khoảng qua nửa đêm UTC phải đọc **hai partition ngày** cho cùng store/product rồi hợp nhất theo yêu cầu.

## Kết luận

Chọn clustering column là quyết định **thứ tự đọc bên trong partition**. Khi đường truy cập chủ đạo cần bản ghi mới nhất hoặc một khoảng thời gian, đặt cột thời gian ở vị trí clustering phù hợp, bổ sung cột phân định khi trùng timestamp và khai báo hướng clustering từ hợp đồng truy vấn. Khi yêu cầu thêm bộ lọc nằm trước trục thời gian, sắp xếp theo regular column hoặc gộp dữ liệu từ nhiều partition, cần đánh giá lại thứ tự clustering, partition key hoặc bổ sung bảng phục vụ riêng. Một schema tốt được xác nhận bằng **CQL cụ thể, dữ liệu đại diện và phép đo dưới tải thực tế**.
