# Chọn partition key từ đường truy cập chủ đạo

## Mục tiêu bài học

Trong Apache Cassandra, **partition key** quyết định một hàng thuộc phân vùng logic nào, từ đó quyết định cách Cassandra định tuyến dữ liệu tới các replica trong cụm. Một partition key phù hợp giúp ứng dụng đọc đúng một hoặc một số ít phân vùng đã biết, trong khi một lựa chọn sai có thể khiến truy vấn thiếu khóa, phải phân tán đến quá nhiều phân vùng hoặc tập trung tải lên một phân vùng quá lớn.

Bài học thuộc chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trọng tâm là đi từ **đường truy cập chủ đạo (primary access path)** của ứng dụng đến việc chọn partition key, xét đồng thời tính đúng của CQL, phân bố dữ liệu, độ nóng, replication, giới hạn nhất quán và cách dịch vụ Java truyền khóa khi truy vấn.

Sau bài này, bạn có thể:

- Rút ra các trường đầu vào **luôn có** của đường đọc quan trọng nhất và chuyển chúng thành ứng viên partition key.
- Phân biệt **partition key đơn**, **partition key ghép**, **clustering key** và vai trò của chúng trong `PRIMARY KEY`.
- Ước tính số hàng, dung lượng, lưu lượng và số phân vùng bị truy cập khi chọn một partition key hoặc bucket thời gian.
- Nhận diện phân vùng lớn, phân vùng nóng, khóa có độ phân biệt thấp và tình huống cần bucket/shard hoặc bảng dành cho truy vấn khác.
- Viết bảng và câu lệnh CQL có đường truy cập rõ ràng; chỉ ra giới hạn của truy vấn khác khóa và cách kiểm chứng giả định với dữ liệu thực tế.

## 1. Vì sao partition key phải bắt đầu từ truy vấn?

Một hệ quản trị quan hệ thường cho phép nhiều kiểu `WHERE`, `JOIN`, `ORDER BY` trên tập bảng chuẩn hóa và tận dụng index hoặc bộ tối ưu truy vấn. Cassandra dùng mô hình **wide-column phân tán**: mỗi partition được xác định bởi giá trị partition key và các hàng bên trong partition được sắp theo clustering column. Cassandra ưu tiên những thao tác mà ứng dụng **biết trước partition cần đọc**.

Ví dụ:

> “Khách hàng xem 50 giao dịch mới nhất trong ngày của chính tài khoản mình, hiển thị thời gian giảm dần.”

Từ phát biểu này có thể tách:

- **Người được truy vấn:** một tenant và một tài khoản đã biết.
- **Phạm vi:** một ngày đã xác định.
- **Thứ tự bên trong phạm vi:** thời gian xảy ra giảm dần.
- **Giới hạn:** tối đa 50 giao dịch cho lượt xem này.

Ứng viên partition key là `(tenant_id, account_id, day_bucket)`. `occurred_at` và `event_id` có thể là clustering columns. Cách chọn này xuất phát từ **giá trị ứng dụng luôn truyền khi đọc**, thay vì chỉ từ tên thực thể hoặc thuộc tính có trong payload.

Nếu cùng bảng đó còn bị yêu cầu “tìm giao dịch chỉ bằng `event_id`” hoặc “liệt kê mọi giao dịch thất bại của tenant”, hai truy vấn mới không tự nhiên biết partition của tài khoản/ngày. Chúng cần một đường đọc riêng hoặc phải được thiết kế lại dựa trên yêu cầu thực tế.

## 2. Partition key thực sự quyết định điều gì?

### 2.1. Một partition là một đơn vị định tuyến logic

Cassandra áp dụng partitioner lên partition key để tính **token**. Cùng một giá trị partition key dẫn đến cùng một token và cùng tập replica tương ứng theo cấu hình placement/replication hiện tại. Các hàng khác clustering key nhưng cùng partition key vẫn thuộc **một phân vùng logic**.

`PRIMARY KEY` của Cassandra gồm hai phần có nhiệm vụ khác nhau:

| Thành phần | Quyết định | Truy vấn điển hình |
| --- | --- | --- |
| **Partition key** | Phân vùng và token phục vụ định tuyến tới replica | Điều kiện bằng trên các thành phần khóa phân vùng |
| **Clustering column** | Thứ tự và tính duy nhất của hàng bên trong partition | Điều kiện khoảng/thứ tự trên khóa clustering phù hợp |
| **Regular column** | Giá trị dữ liệu lưu cùng hàng | Hiển thị; không mặc nhiên dùng để định vị hiệu quả |

Ví dụ cú pháp CQL:

```sql
-- Partition key đơn là account_id; occurred_at là clustering column.
PRIMARY KEY (account_id, occurred_at)

-- Partition key ghép gồm tenant_id, account_id, day_bucket.
-- occurred_at và event_id là clustering columns.
PRIMARY KEY ((tenant_id, account_id, day_bucket), occurred_at, event_id)
```

Trong ví dụ thứ hai, **ba thành phần trong cặp ngoặc đơn lồng nhau** hợp thành một partition key. Cassandra dùng toàn bộ tổ hợp giá trị để tính token. Chúng **không** phải ba index độc lập; vì vậy truy vấn chỉ có `tenant_id = ?` không tự nhiên định vị được một partition.

### 2.2. Partition key quyết định phạm vi công việc, clustering quyết định đường đọc bên trong

```text
Ứng dụng Java
  Q: tenant=T1, account=A1, day=2026-11-21
            |
            v
Partition key = (T1, A1, 2026-11-21)
            |
            v
Token và replica của partition đó
            |
            v
Các hàng theo clustering:
  (10:12:31, e8) -> ...
  (10:10:02, e7) -> ...
  (09:58:14, e6) -> ...
            |
            v
Trả tối đa 50 hàng theo thứ tự yêu cầu
```

Hàm phân vùng phân bố **các partition** trên vòng token; nó không tự chia một partition rất lớn thành nhiều partition nhỏ độc lập. Nếu một `account_id` tạo khối lượng ghi vượt trội, các giá trị khóa khác nhau có thể được phân bố tốt trong cụm nhưng **partition của tài khoản đó vẫn nóng**.

Replication giúp các replica giữ bản sao dữ liệu và hỗ trợ chịu lỗi theo chính sách triển khai. Nó **không** thay đổi đường truy cập bắt buộc của câu CQL và không biến một partition nóng thành vô số partition độc lập.

## 3. Xác định đường truy cập chủ đạo

**Đường truy cập chủ đạo** là kiểu đọc có ảnh hưởng lớn đến mục tiêu hệ thống: có thể vì được gọi nhiều, yêu cầu độ trễ thấp, nhạy cảm về nghiệp vụ hoặc khó thay thế. Không nhất thiết là câu truy vấn được viết đầu tiên hay chỉ là truy vấn có phần trăm lượt gọi lớn nhất.

Trước khi thiết kế bảng, lập một danh mục các **query shape** với thông tin tối thiểu:

| Cần thu thập | Câu hỏi | Vì sao liên quan đến partition key? |
| --- | --- | --- |
| Đầu vào bắt buộc | Caller luôn có tenant, account, ngày hay chỉ có ID? | Thành phần partition key cần được cung cấp khi định vị phân vùng |
| Đầu vào tùy chọn | Người dùng có bỏ lọc ngày hoặc tài khoản không? | Bỏ một thành phần khóa có thể tạo query shape khác |
| Phạm vi kết quả | Một account/ngày, nhiều ngày hay toàn tenant? | Quyết định số partition mỗi yêu cầu |
| Thứ tự và giới hạn | Đọc mới nhất trước, `LIMIT` bao nhiêu? | Định hướng clustering và cách xử lý nhiều partition |
| Tải | QPS trung bình/đỉnh, số caller, phân bố tenant? | Phát hiện hotspot và fan-out ở tải thật |
| Kích thước | Hàng/byte mỗi account/ngày, TTL, cập nhật/xóa? | Dự đoán sự phát triển của partition |
| Mục tiêu | p95/p99, mức độ mới của dữ liệu, read-after-write? | Phân loại truy vấn ưu tiên và kiểm tra SLA |

### 3.1. Ví dụ danh mục của dịch vụ giao dịch

Giả sử hệ thống nhiều tenant ghi sự kiện giao dịch cho các tài khoản. Các tần suất dưới đây **chỉ là giả định học tập** để minh họa quy trình lựa chọn:

| ID | Yêu cầu | Đầu vào sẵn có | Tỷ lệ đọc giả định | Đặc điểm |
| --- | --- | --- | --- | --- |
| Q01 | Xem 50 giao dịch mới nhất của một account trong ngày | `tenantId`, `accountId`, `utcDay` | 75% | Một phạm vi xác định, mới nhất trước |
| Q02 | Xem giao dịch của account trong khoảng giờ thuộc ngày | `tenantId`, `accountId`, `utcDay`, hai mốc | 15% | Cùng phạm vi Q01, có lọc theo thời gian |
| Q03 | Xem giao dịch của account trong 7 ngày | `tenantId`, `accountId`, từ ngày đến ngày | 8% | Nhiều ngày, cần hợp nhất kết quả |
| Q04 | Tìm một giao dịch bằng event ID | `tenantId`, `eventId` | 2% | Không biết account hoặc ngày |

Nếu Q01 và Q02 có SLA gắt và là đa số yêu cầu, đường truy cập chủ đạo là:

```text
tenant_id = ?
AND account_id = ?
AND day_bucket = ?
=> đọc các sự kiện trong partition này theo thời gian
```

Ta có thể bắt đầu với ứng viên `(tenant_id, account_id, day_bucket)`. Q03 cần chiến lược đọc nhiều bucket có giới hạn. Q04 cần một bảng theo event ID hoặc một cơ chế tra vị trí khác. Không cần cố ép cả bốn truy vấn vào một partition key duy nhất.

### 3.2. Ưu tiên không chỉ theo tỷ lệ truy vấn

Ví dụ Q04 chỉ chiếm 2% nhưng là API xử lý khiếu nại có SLO nghiêm ngặt. Khi đó nó vẫn cần một đường truy cập trực tiếp theo ID. Quyết định mô hình cần cân nhắc **tầm quan trọng** và **giới hạn của từng query shape**, không loại bỏ truy vấn vì tỷ lệ thấp.

Đồng thời, trước khi chốt Q01 cần kiểm tra caller có **thực sự luôn truyền ngày UTC** không. Nếu UI chỉ có nút “50 giao dịch mới nhất bất kể ngày”, chọn `day_bucket` làm khóa buộc ứng dụng phải xác định quy tắc thử các ngày gần nhất và dừng khi đủ hàng. Nếu đây là yêu cầu chính, thiết kế bucket và đường đọc phải được cân nhắc lại.

## 4. Quy trình chọn partition key

### Bước 1. Viết hợp đồng truy vấn chủ đạo dưới dạng giá trị cụ thể

Không chỉ ghi “lọc theo tài khoản”; hãy viết:

```text
Query ID: Q01
Input bắt buộc:
  tenantId: định danh tenant được phép truy cập
  accountId: định danh tài khoản
  utcDay: ngày theo UTC
Input tùy chọn: không có ở đường preview
Output: eventId, occurredAt, amount, eventType
Thứ tự: occurredAt DESC, eventId DESC
Giới hạn: 50 hàng cho một lần xem
Phạm vi: chính xác một account trong một ngày UTC
```

Nếu một giá trị không sẵn có ở thời điểm gọi, nó là ứng viên rủi ro cho partition key. Không nên “giải quyết” bằng cách buộc API cung cấp một giá trị không thể biết được từ ngữ cảnh nghiệp vụ.

### Bước 2. Chọn tập thành phần phân biệt đúng phạm vi đọc

So sánh các ứng viên:

| Partition key ứng viên | Điểm thuận lợi | Vấn đề cần nhận diện |
| --- | --- | --- |
| `(tenant_id)` | Truy vấn toàn tenant biết khóa | Tenant lớn có thể tạo partition khổng lồ và nóng |
| `(tenant_id, account_id)` | Đọc theo account đơn giản | Dữ liệu lịch sử tăng không giới hạn nếu không phân đoạn hợp lý |
| `(tenant_id, account_id, day_bucket)` | Đọc chính xác account/ngày, kiểm soát số hàng theo ngày | Đọc nhiều ngày phải chạm nhiều partition; hot account có thể vẫn quá lớn/ngày |
| `(tenant_id, account_id, event_id)` | Định vị sự kiện khi biết ID | Liệt kê sự kiện theo account/ngày trở thành nhiều partition |
| `(tenant_id, day_bucket)` | Truy vấn toàn tenant/ngày có khóa | Mọi account cùng tenant/ngày dồn vào một partition rất lớn |

Trong ví dụ, `(tenant_id, account_id, day_bucket)` phù hợp Q01–Q02 **theo đường đọc**. Nhưng lựa chọn chỉ được chốt sau khi đánh giá kích thước và tải.

### Bước 3. Chọn mức bucket và kiểm tra hotspot

Giả sử một tài khoản hoạt động mạnh phát sinh **10 sự kiện/giây** liên tục, mỗi hàng ước tính **500 byte dữ liệu thô**:

```text
Một ngày: 10 × 60 × 60 × 24 = 864.000 sự kiện
Dung lượng thô/ngày: 864.000 × 500 B ≈ 432 MB

Một giờ: 10 × 60 × 60 = 36.000 sự kiện
Dung lượng thô/giờ: 36.000 × 500 B ≈ 18 MB
```

Đây là phép tính minh họa, **chưa gồm overhead lưu trữ, index, tombstone, compaction hoặc replication**; không nên xem bất cứ con số nào là ngưỡng an toàn chung. Dữ liệu thực tế có thể lớn hơn đáng kể. Nếu tài khoản lớn nhất ở mức này, bucket **giờ** có thể đáng cân nhắc hơn ngày. Tuy nhiên, đọc một ngày sẽ phải ghép tối đa 24 partition theo giờ thay vì một partition theo ngày.

Vì vậy cần cân bằng **chi phí đọc nhiều bucket** và **độ lớn/độ nóng của mỗi bucket**. Khi chỉ vài tài khoản rất lớn, nghiên cứu cách phân tầng thiết kế hoặc thay đổi key dựa trên các nhóm tải, nhưng phải định nghĩa rõ cách ứng dụng tìm đúng partition cho từng trường hợp.

### Bước 4. Chọn clustering column từ thứ tự trong partition

Sau khi biết partition, mới quyết định cách sắp xếp bên trong:

```sql
PRIMARY KEY ((tenant_id, account_id, day_bucket), occurred_at, event_id)
```

Trong đó `occurred_at` cho phép đọc theo khoảng thời gian và theo thứ tự; `event_id` phân biệt các sự kiện cùng thời điểm. Nếu `event_id` là UUID ngẫu nhiên, thứ tự UUID chỉ là cách phân định ổn định khi timestamp bằng nhau, **không** chứng minh thứ tự xảy ra giữa hai sự kiện cùng timestamp.

### Bước 5. Kiểm tra truy vấn không khớp

Liệt kê từng truy vấn ngoài Q01/Q02: có đủ partition key không? Có đòi thứ tự toàn cục giữa nhiều partition không? Có lọc theo regular column không? Quyết định truy vấn nào sẽ:

- Đọc một số partition có giới hạn rồi hợp nhất ở ứng dụng.
- Dùng bảng nhân bản phục vụ riêng.
- Dùng công cụ tìm kiếm/phân tích khác nếu yêu cầu lọc và sắp xếp tùy ý là chủ đạo.
- Trả về giới hạn rõ ràng cho người dùng thay vì mở API không giới hạn.

### Bước 6. Xác nhận bằng dữ liệu và phép đo

Lấy phân bố **lớn nhất, p95/p99 và giờ cao điểm**, không chỉ trung bình. Kiểm tra số partition/giây và số hàng/byte ở partition lớn nhất, thông lượng theo partition nóng, tombstone, hiệu ứng TTL, số lần thử lại, độ trễ đọc/ghi và nguồn lực từng node.

## 5. Ví dụ CQL hoàn chỉnh: partition theo account/ngày

Giả sử `tenant_id` là chuỗi, `account_id` và `event_id` là UUID, ngày được chuẩn hóa UTC. Ta chọn bảng:

```sql
CREATE TABLE account_events_by_day (
    tenant_id text,
    account_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    amount decimal,
    description text,
    PRIMARY KEY ((tenant_id, account_id, day_bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Ba điểm quan trọng:

1. Cassandra xác định partition bằng **toàn bộ** `(tenant_id, account_id, day_bucket)`.
2. Hai trường `(occurred_at, event_id)` quyết định vị trí và tính duy nhất của hàng **bên trong** partition.
3. `event_type`, `amount` và `description` chỉ là dữ liệu được trả về trong bảng này, không có ý nghĩa truy cập nhanh theo những thuộc tính đó.

### 5.1. Q01: lấy 50 giao dịch mới nhất trong ngày

```sql
SELECT occurred_at, event_id, event_type, amount, description
FROM account_events_by_day
WHERE tenant_id = ?
  AND account_id = ?
  AND day_bucket = ?
LIMIT 50;
```

Vì bảng đã định nghĩa clustering giảm dần, kết quả trong partition được đọc theo thứ tự tương ứng mà không cần thêm `ORDER BY`. Truy vấn có **đủ partition key** và không đòi phép lọc hậu kỳ trên regular column.

### 5.2. Q02: khoảng thời gian bên trong cùng một ngày

```sql
SELECT occurred_at, event_id, event_type, amount
FROM account_events_by_day
WHERE tenant_id = ?
  AND account_id = ?
  AND day_bucket = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 100;
```

Khoảng `[fromInclusive, toExclusive)` tránh đếm trùng tại ranh giới của các khoảng liền nhau. Cả hai mốc phải nằm trong ngày tương ứng với `day_bucket`; một khoảng vượt nửa đêm UTC cần được tách thành hai lượt đọc ở hai partition.

### 5.3. Q03: xem dữ liệu trong bảy ngày

Giả sử yêu cầu là “các sự kiện gần nhất của account trong **bảy ngày lịch UTC được chọn**”. Với key hiện tại, ứng dụng có thể:

1. Xác định tối đa bảy giá trị `day_bucket` nằm trong khoảng. Nếu yêu cầu là cửa sổ **trượt 7 × 24 giờ** thay vì bảy ngày lịch, khoảng này có thể chạm đến **tám** ngày UTC và cần đọc tối đa tám bucket.
2. Đọc từng partition bằng câu Q01/Q02 thích hợp, kiểm soát số lượng hàng đã tải.
3. Hợp nhất các luồng theo `(occurred_at DESC, event_id DESC)`.
4. Trả số hàng nghiệp vụ yêu cầu, giữ thông tin tiếp tục phù hợp với từng partition.

Không được giả định một câu `ORDER BY` duy nhất trên nhiều partition sẽ tự tạo thứ tự toàn cục đúng và có chi phí thấp. Nếu bảy ngày luôn là đường đọc chủ đạo, partition theo ngày có thể không còn là lựa chọn tốt nhất; phải so sánh lại bucket, bảng chuyên biệt và mức fan-out.

### 5.4. Q04: tra cứu bằng event ID

Q04 **không** có `account_id` hay `day_bucket`. Để định vị một sự kiện mà không quét các tài khoản/ngày, dùng bảng khác:

```sql
CREATE TABLE account_events_by_id (
    tenant_id text,
    event_id uuid,
    account_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_type text,
    amount decimal,
    PRIMARY KEY ((tenant_id, event_id))
);

SELECT account_id, day_bucket, occurred_at, event_type, amount
FROM account_events_by_id
WHERE tenant_id = ? AND event_id = ?;
```

Điều kiện thiết kế là `event_id` phải duy nhất trong tenant. Nếu chỉ duy nhất trong account, phải đổi hợp đồng đầu vào hoặc khóa; nếu event ID có thể lặp, bảng này sẽ ghi đè cùng một hàng logic.

Ứng dụng có thể lưu đầy đủ dữ liệu hiển thị ở bảng theo ID hoặc chỉ lưu thông tin **định vị** `(account_id, day_bucket, occurred_at)` rồi đọc tiếp bảng theo ngày. Cách thứ hai giảm lặp một số trường nhưng thêm lượt đọc và cần xử lý trường hợp projection cập nhật lệch tạm thời.

## 6. Các lựa chọn dễ sai và hậu quả

### 6.1. Chỉ dùng tenant ID vì mọi API đều có tenant

```sql
-- Ví dụ KHÔNG phù hợp cho tenant có lịch sử sự kiện lớn:
PRIMARY KEY (tenant_id, occurred_at, event_id)
```

Phần này đặt tất cả sự kiện của tenant vào một partition nếu `tenant_id` là partition key đơn. Mặc dù app luôn biết khóa, tenant lớn sẽ tạo partition tăng rất nhanh và có thể bị nóng. **Khóa luôn có** chỉ là điều kiện cần; **phân bố kích thước và tải** cũng phải đạt yêu cầu.

### 6.2. Đưa timestamp hoặc event ID vào partition key khi cần đọc một danh sách

```sql
-- Mỗi sự kiện nằm trong partition riêng theo event_id:
PRIMARY KEY ((tenant_id, event_id))
```

Đường này tốt cho lookup theo ID, nhưng không thích hợp để tự liệt kê 50 sự kiện gần nhất theo account nếu caller không biết danh sách `event_id` trước. Các khóa có độ phân biệt rất cao không tự động tạo đường đọc tốt cho một trang danh sách.

### 6.3. Cho rằng partition key nhiều cột là nhiều chỉ mục có thể bỏ qua

Với `PRIMARY KEY ((tenant_id, account_id, day_bucket), occurred_at, event_id)`, một truy vấn chỉ có `tenant_id = ?` không tự định vị được partition. Một truy vấn chỉ có `account_id = ?` cũng thiếu thông tin. Không coi `ALLOW FILTERING` là cách sửa thiết kế; nó có thể dẫn đến lượng dữ liệu cần đọc lớn và khó kiểm soát, hoặc câu lệnh vẫn không được chấp nhận tùy dạng.

### 6.4. Tin rằng token hash tự giải quyết mọi hotspot

Token giúp phân bố **nhiều partition key khác nhau**. Nếu chỉ một tổ hợp `(tenant, account, day)` nhận phần lớn traffic, mọi hàng trong tổ hợp đó vẫn thuộc cùng partition và tập replica. Điều này cần xử lý bằng thiết kế bucket, truy cập, thậm chí chia shard khi thật sự cần.

### 6.5. Lấy trung bình làm đại diện

Giả sử đa số tài khoản có 100 sự kiện/ngày, nhưng một tài khoản có 500.000 sự kiện/ngày. Trung bình toàn hệ thống có thể trông nhỏ mà partition lớn nhất lại tạo vấn đề. Khi chọn bucket, hãy dự báo **đỉnh theo khóa logic**, không chỉ tổng hàng chia đều cho số tài khoản.

## 7. Khi nào cần bucket thời gian hoặc shard?

### 7.1. Bucket thời gian

Đưa `day_bucket`, `hour_bucket` hoặc `month_bucket` vào partition key làm giới hạn độ dài lịch sử của một partition theo thời gian. Cần thống nhất:

- Ngày/giờ tính theo **UTC hay múi giờ nghiệp vụ**; nên cố định quy tắc từ lúc ghi.
- Bucket lấy từ `occurred_at` (event time) hay `ingested_at` (thời điểm hệ thống nhận).
- Xử lý sự kiện **đến muộn**, sự kiện bị sửa thời gian hoặc sự kiện ở ranh giới ngày.
- Số bucket tối đa một API được đọc khi người dùng chọn khoảng thời gian rộng.

Ví dụ sự kiện xảy ra `2026-11-20 23:59:59 UTC` nhưng đến server sau nửa đêm: nếu key dùng ngày theo **thời điểm xảy ra**, sự kiện vẫn được ghi vào bucket ngày 20. Quy tắc này phải giống nhau ở đường ghi và đường đọc. Đổi cách tính bucket giữa chừng có thể làm sự kiện không tìm thấy qua các API cũ.

Bucket thời gian giúp tránh dữ liệu lịch sử dồn vô hạn vào một partition, nhưng nó không giảm nhiều nếu ngay trong **một giờ** đã có số lượng sự kiện cực lớn.

### 7.2. Sharding một khóa logic quá nóng

Nếu một account có tốc độ ghi cao đến mức bucket giờ vẫn gây nghẽn, có thể thêm `shard_id` vào partition key:

```sql
CREATE TABLE account_events_by_day_sharded (
    tenant_id text,
    account_id uuid,
    day_bucket date,
    shard_id int,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    amount decimal,
    PRIMARY KEY ((tenant_id, account_id, day_bucket, shard_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Một cách chọn shard ở đường ghi là `hash(event_id) mod N`, với `N` được cố định/quản lý theo phiên bản schema. Khi cần tìm một event theo ID, ứng dụng có thể tính shard tương ứng; khi muốn liệt kê **toàn bộ sự kiện của account/ngày**, ứng dụng phải đọc các shard liên quan rồi hợp nhất thứ tự.

| Cách làm | Lợi ích | Chi phí phải chấp nhận |
| --- | --- | --- |
| Không shard, bucket ngày | Đọc một partition/ngày đơn giản | Partition có thể lớn hoặc nóng |
| Bucket giờ | Giảm dữ liệu mỗi partition theo thời gian | Đọc nhiều giờ phải hợp nhất nhiều partition |
| Bucket ngày + `N` shard | Dàn ghi của một account/ngày ra nhiều partition | Mỗi trang danh sách có thể cần fan-out đến `N` partition |
| Bucket giờ + shard | Giới hạn kích thước và phân tán tải hơn | Quản lý khóa, fan-out, paging và thay đổi `N` phức tạp |

Không nên tự ý tăng `N` mà bỏ qua khả năng tìm dữ liệu cũ: nếu thay quy tắc shard, phải có kế hoạch phiên bản/di trú hoặc biết `N` áp dụng cho từng thời kỳ. Shard tăng độ phức tạp và không mặc nhiên là quyết định tốt hơn.

## 8. Đường đọc từ ứng dụng Java

Chọn partition key chỉ có ý nghĩa khi API thực sự truyền đầy đủ những giá trị dùng để định tuyến. Ví dụ DataStax Java Driver 4.x với bảng `account_events_by_day`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

import java.time.LocalDate;
import java.util.UUID;

public final class AccountEventReader {
    private final CqlSession session;
    private final PreparedStatement latestInDay;

    public AccountEventReader(CqlSession session) {
        this.session = session;
        this.latestInDay = session.prepare(
            "SELECT occurred_at, event_id, event_type, amount " +
            "FROM account_events_by_day " +
            "WHERE tenant_id = ? AND account_id = ? AND day_bucket = ? " +
            "LIMIT 50"
        );
    }

    public ResultSet latest(String tenantId, UUID accountId, LocalDate utcDay) {
        BoundStatement bound = latestInDay.bind(tenantId, accountId, utcDay);
        return session.execute(bound);
    }
}
```

`LocalDate` tương ứng kiểu CQL `date`, còn `UUID` tương ứng `uuid`. Ứng dụng phải tính `utcDay` theo đúng quy tắc ghi dữ liệu và kiểm tra tenant/account có được phép truy cập. Partition key có thành phần `tenant_id` **không tự thay thế** cơ chế phân quyền ở lớp ứng dụng.

Prepared statement giúp tránh ghép chuỗi các giá trị đầu vào và tạo đường gọi nhất quán. Driver có thể tận dụng thông tin routing key/token khi xác định replica phù hợp, tùy cấu hình topology và chính sách load balancing. Dùng một `CqlSession` chia sẻ và quản lý vòng đời theo dịch vụ thay vì tạo session mới cho mỗi request.

Nếu màn hình phải tải nhiều trang, cần phân biệt `LIMIT 50` (tổng số hàng tối đa của câu truy vấn) với **page size** của driver (số hàng mục tiêu mỗi trang). Với phân trang dài, thường dùng một prepared statement không cố định `LIMIT 50`, cấu hình page size, tiếp tục bằng **paging state** opaque và ràng buộc token với cùng query shape cùng tham số. Không giả định các trang là ảnh chụp dữ liệu bất biến khi có cập nhật đồng thời.

## 9. Mối quan hệ với replication, consistency và bảo trì

Một thiết kế partition key đúng giúp truy vấn có mục tiêu rõ ràng; **replication factor**, placement và **consistency level** quyết định cách các replica đáp ứng yêu cầu. Chẳng hạn `LOCAL_QUORUM` có thể phù hợp một số yêu cầu đọc/ghi trong datacenter với cấu hình replication thích hợp; lựa chọn cụ thể phụ thuộc SLA và topology. Thay consistency level **không** làm một câu truy vấn thiếu partition key trở thành đọc đúng một partition.

Khi cùng sự kiện có thêm bảng `account_events_by_id`, ứng dụng phải cập nhật các representation cần thiết. Cassandra không tự tạo một phép `JOIN` để đồng bộ hai bảng. Việc ghi nhiều bảng có thể tạo sai lệch tạm thời nếu một lượt ghi thất bại; cần retry an toàn, đối soát và thiết kế để xử lý bản ghi lặp hoặc đến muộn.

Các hoạt động như compaction, repair và TTL liên quan trực tiếp tới vận hành partition lớn:

- **Compaction** ảnh hưởng đến tổ chức SSTable và chi phí đọc/ghi, nhưng không sửa được partition key sai.
- **TTL/xóa** có thể sinh tombstone; truy vấn `LIMIT 50` vẫn có thể đọc nhiều tombstone trước khi trả đủ hàng.
- **Repair** duy trì sự nhất quán replica theo cơ chế Cassandra, nhưng không tự đồng bộ logic giữa các bảng nhân bản do ứng dụng duy trì.

Vì vậy cần kiểm soát phân vùng lớn, tombstone, tốc độ ghi và yêu cầu đọc trong bước chọn key, trước khi quyết định tuning compaction hay mức nhất quán.

## 10. Checklist kiểm chứng trước khi chốt partition key

| Câu hỏi kiểm chứng | Dấu hiệu đạt | Cần thiết kế lại khi |
| --- | --- | --- |
| Caller có đủ mọi thành phần partition key không? | Q01/Q02 luôn nhận tenant, account, ngày | Đa số request không biết account/ngày |
| Có truy vấn nào cần tìm bằng khóa khác không? | Có bảng/đường đọc Q04 theo event ID | API âm thầm quét nhiều account để tìm ID |
| Partition có giới hạn tăng trưởng không? | Bucket phù hợp với dữ liệu và thời hạn lưu | Một account có thể tăng vô hạn trong cùng partition |
| Tải phân bố ra sao? | Partition nóng nhất đáp ứng mục tiêu đo được | Chỉ dựa vào số liệu trung bình hoặc ước đoán |
| Số partition mỗi request có giới hạn không? | Đọc một ngày = một partition; bảy ngày được chặn | API có thể fan-out hàng nghìn bucket |
| Clustering có đúng thứ tự đọc? | `occurred_at DESC, event_id DESC` phù hợp | UI đòi `ORDER BY amount` toàn tenant |
| Quy tắc bucket có ổn định không? | Thống nhất UTC và thời gian sự kiện | Ghi theo ingest time nhưng đọc theo event time |
| Đường ghi nhiều bảng có được quản lý? | Có retry/idempotency và đối soát | Ghi một projection thành công, projection khác mất dữ liệu |
| Đã đo với dữ liệu đại diện chưa? | Có phân bố cực trị, p95/p99, tombstone và peak | Chỉ chạy vài `SELECT` trên dữ liệu mẫu nhỏ |

Trên môi trường thử nghiệm phù hợp, dùng `cqlsh` để xác nhận cú pháp CQL; tạo các partition đại diện gồm cả account thường và account rất lớn; dùng metric/tracing để quan sát độ trễ, lượng dữ liệu đọc và tác động của tombstone. Thử ranh giới UTC, khoảng không có dữ liệu, sự kiện đến muộn và truy vấn qua nhiều bucket. Một câu lệnh chạy thành công **chưa đủ** để chứng minh partition key tốt dưới tải.

## 11. Bài tập thực hành

Một ứng dụng Java theo dõi nhật ký chuyển trạng thái của đơn giao hàng. Mỗi bản ghi gồm:

```text
tenant_id, parcel_id, changed_at, change_id, status, actor_id, note
```

Các API:

1. **R1:** Xem 20 thay đổi trạng thái gần nhất của một kiện hàng trong ngày UTC.
2. **R2:** Xem lịch sử thay đổi của kiện hàng từ 08:00 đến trước 10:00 cùng ngày.
3. **R3:** Xem 100 thay đổi gần nhất của kiện hàng trong 30 ngày lịch UTC được chọn.
4. **R4:** Tìm một thay đổi bằng `change_id`, chỉ biết tenant.
5. **R5:** Nhân viên xem mọi thay đổi có `status = FAILED` của một tenant trong ngày.

Yêu cầu:

1. Xác định đường truy cập chủ đạo nếu R1/R2 chiếm 90% lượng đọc và có SLA gắt nhất.
2. Đề xuất partition key, clustering key và viết `CREATE TABLE` cho R1/R2.
3. Giải thích R3 cần đọc bao nhiêu bucket nếu chọn bucket ngày; đề xuất giới hạn cho API và cách hợp nhất kết quả.
4. Giải thích vì sao R4/R5 thiếu đường truy cập trên bảng R1/R2 và phác thảo các bảng/projection cần khảo sát.
5. Nếu một kiện hàng có tới 1 triệu cập nhật/ngày, bạn cần thu thập thêm chỉ số gì trước khi chốt bucket ngày, bucket giờ hoặc shard?

**Gợi ý đối chiếu:** Với R1/R2, ứng viên là partition key `(tenant_id, parcel_id, day_bucket)` và clustering `(changed_at DESC, change_id DESC)`. R3 đi qua 30 partition theo ngày cho một kiện hàng nếu khoảng bao gồm 30 ngày lịch UTC; một cửa sổ trượt đúng 30 × 24 giờ có thể chạm **31** partition ngày. Cả hai cần kiểm soát fan-out và hợp nhất. R4 cần một đường lookup theo `(tenant_id, change_id)` nếu ID duy nhất trong tenant. R5 là query shape toàn tenant theo trạng thái, cần thiết kế bảng/projection riêng với bucket và phân bố tải được đo. Một triệu cập nhật/ngày là tín hiệu phải xem kích thước hàng, tốc độ ghi đỉnh, số tombstone và tải partition trước khi quyết định.

## Kết luận

Partition key phù hợp được suy ra từ **giá trị ứng dụng luôn biết trên đường đọc chủ đạo**, sau đó được kiểm chứng bằng **quy mô phân vùng và tải thực tế**. Một khóa có thể định tuyến đúng nhưng vẫn gây partition lớn hoặc hotspot; một khóa phân bố đều nhưng thiếu giá trị cần thiết khi đọc cũng không phục vụ được API. Thiết kế Cassandra hiệu quả vì vậy cần chốt đồng thời hợp đồng truy vấn, partition key, bucket, clustering, đường đọc thay thế và giới hạn fan-out, rồi chứng minh bằng dữ liệu và phép đo trên cụm mục tiêu.
