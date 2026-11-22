# ALTER TABLE: thêm, bỏ, đổi thuộc tính và điều kiện thay đổi kiểu

## 1. ALTER TABLE giải quyết bài toán gì?

Trong Apache Cassandra, `ALTER TABLE` thay đổi **schema của một bảng đã tồn tại**. Tùy phiên bản CQL và loại bảng, bạn có thể bổ sung hoặc loại bỏ một số cột, đổi tên một số cột trong phạm vi cho phép, hay chỉnh các **table options** như TTL mặc định, compaction, compression và comment. Tuy nhiên, Cassandra không xem việc sửa bảng là thao tác tự động chuyển mọi hàng hiện hữu sang một mô hình dữ liệu mới.

Đây là bài học thuộc chương **Keyspace và schema** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Đối với cơ sở dữ liệu wide-column phân tán, thiết kế bảng gắn chặt với cách đọc/ghi theo **partition key**, **clustering columns**, replication và consistency level. Vì vậy, trước khi thay đổi schema, cần phân biệt:

- **Thay đổi metadata:** Cassandra cập nhật cách định nghĩa cột và tùy chọn bảng.
- **Thay đổi dữ liệu đang lưu:** ứng dụng có thể phải backfill, chuyển đổi dữ liệu, ghi song song hoặc tạo bảng mới.
- **Thay đổi topology/replication:** thuộc keyspace và công việc vận hành cluster, **không** thực hiện bằng `ALTER TABLE`.

Sau bài học, bạn cần giải thích được khi nào dùng `ADD`, `DROP`, `RENAME`, `WITH`; khi nào một thay đổi kiểu dữ liệu hoặc khóa chính buộc phải thiết kế migration; và cách xác minh schema trước khi ứng dụng Java phụ thuộc vào nó.

## 2. Các dạng ALTER TABLE thường dùng

Các dạng lệnh cơ bản có thể hình dung như sau:

```sql
-- Thêm cột mới.
ALTER TABLE keyspace_name.table_name
ADD new_column text;

-- Bỏ cột hiện có, nếu cột thuộc loại được phép bỏ.
ALTER TABLE keyspace_name.table_name
DROP old_column;

-- Đổi tên cột thuộc loại được phiên bản Cassandra cho phép.
ALTER TABLE keyspace_name.table_name
RENAME old_column TO new_column;

-- Đổi một hoặc nhiều table options.
ALTER TABLE keyspace_name.table_name
WITH comment = 'Mô tả bảng'
 AND default_time_to_live = 0;
```

Đây là các **mẫu cú pháp**; không được chạy nguyên văn với `keyspace_name.table_name` chưa tồn tại. Các biến thể như `IF EXISTS`/`IF NOT EXISTS`, số cột thay đổi cùng lúc, khả năng `RENAME` và tập option được hỗ trợ **phụ thuộc phiên bản Cassandra**. Khi viết migration thực tế, đối chiếu đúng cú pháp của cluster mục tiêu và thử trên môi trường test cùng phiên bản.

| Dạng thay đổi | Tác động chính | Có tự viết lại dữ liệu lịch sử không? |
| --- | --- | --- |
| `ADD column` | Bổ sung định nghĩa cột mới | **Không**; hàng cũ không tự có giá trị mới |
| `DROP column` | Bỏ định nghĩa cột có thể xóa | **Không xóa tức thời** mọi byte cũ trên SSTable |
| `RENAME column` | Đổi tên cột trong phạm vi hỗ trợ | Không chuyển kiểu hoặc thay cấu trúc partition |
| `WITH table_option` | Đổi cấu hình hoạt động của bảng | Tùy option; thường không chuyển đổi ngay mọi SSTable/hàng |
| Đổi partition key hoặc loại dữ liệu | Thường không hỗ trợ như một `ALTER TABLE` thông thường | Cần đánh giá migration/bảng mới và chuyển dữ liệu |

**Nguyên tắc đầu tiên:** đọc schema hiện tại trước khi sửa. Trạng thái mong muốn trong file migration không chứng minh trạng thái thực tế đã giống như vậy.

## 3. Chuẩn bị ví dụ: bảng đơn hàng được thiết kế theo truy vấn

Ví dụ bên dưới dùng keyspace `schema_lab` trên **môi trường thử nghiệm**. Giả sử `nodetool status` cho biết node lab thuộc DC `datacenter1` và lab chỉ có một node. Nếu DC thực tế khác tên, hãy thay đúng tên đó trong replication map.

```sql
CREATE KEYSPACE IF NOT EXISTS schema_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': '1'
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS schema_lab.orders_by_customer (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    amount decimal,
    status text,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC)
  AND default_time_to_live = 0;
```

Hãy kiểm tra schema ngay sau khi tạo:

```sql
DESCRIBE TABLE schema_lab.orders_by_customer;
```

`DESCRIBE` là lệnh của `cqlsh`. Nếu bảng đã tồn tại, `IF NOT EXISTS` **không đảm bảo** định nghĩa hiện tại trùng định nghĩa vừa ghi. Cần đối chiếu schema và không ghi tiếp vào một bảng sai cấu trúc.

Để có dữ liệu kiểm tra:

```sql
INSERT INTO schema_lab.orders_by_customer (
    customer_id, created_at, order_id, amount, status
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20T08:00:00Z',
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    250000.00,
    'PAID'
);

SELECT created_at, order_id, amount, status
FROM schema_lab.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
```

Bảng có partition key là `customer_id`, clustering key là `created_at` và `order_id`. Mỗi partition chứa các đơn hàng của một khách; vì các đơn hàng có thể tăng theo thời gian, đây chỉ là mô hình minh họa. Trong production cần đánh giá kích thước partition, có thể bổ sung bucket thời gian nếu lưu lượng lớn.

## 4. ADD: thêm cột nhưng không tự tạo giá trị cho hàng cũ

Giả sử yêu cầu mới cần ghi chú giao hàng:

```sql
ALTER TABLE schema_lab.orders_by_customer
ADD shipping_note text;
```

Sau khi schema change hoàn tất và các node đã biết định nghĩa mới, bạn có thể ghi giá trị của cột mới cho một hàng:

```sql
UPDATE schema_lab.orders_by_customer
SET shipping_note = 'Giao trước 18 giờ'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND created_at = '2026-11-20T08:00:00Z'
  AND order_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

SELECT created_at, order_id, shipping_note
FROM schema_lab.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
```

**Hàng hiện hữu không được tự động điền giá trị mặc định.** Cassandra không tự chạy backfill qua toàn bộ partition khi `ADD`. Một hàng chưa từng được ghi `shipping_note` sẽ thường trả về `null` cho cột này khi đọc.

### Các giới hạn cần lưu ý khi thêm cột

1. `ADD` bổ sung **regular column** mới theo quy tắc của bảng; tùy cấu trúc bảng, có thể thêm `static column` nếu được hỗ trợ và phù hợp mô hình. Không dùng `ADD` để đổi thành phần của `PRIMARY KEY`.
2. Tên cột không được xung đột với cột đang tồn tại; tránh thêm lại tên từng bị `DROP` để “đổi kiểu” vì có rủi ro metadata và dữ liệu cũ trên SSTable.
3. Trước khi ứng dụng đọc/ghi cột mới, cần chờ schema agreement và đảm bảo driver nhận metadata mới.
4. Với hệ thống lớn, nếu cần giá trị mặc định theo nghiệp vụ, triển khai **backfill** có giới hạn tốc độ, theo partition key hoặc luồng dữ liệu được kiểm soát. Đừng coi `ALTER TABLE ADD` là lệnh cập nhật tất cả bản ghi.
5. Nếu ứng dụng Java hiện hữu map kết quả vào object cố định, nên triển khai code xử lý cột mới có thể `null` trong giai đoạn chuyển tiếp.

### Thêm cột có làm thay đổi phân bố replica?

Không. Cassandra chọn partition dựa trên partition key và đặt replica dựa vào replication strategy của **keyspace**. Thêm `shipping_note` không đổi `customer_id`, không thêm replica và không thay đổi `LOCAL_QUORUM` hay CL của từng statement.

## 5. DROP: bỏ cột và ảnh hưởng tới dữ liệu hiện có

Khi không còn dùng `shipping_note`, có thể bỏ cột thường này:

```sql
ALTER TABLE schema_lab.orders_by_customer
DROP shipping_note;
```

Sau khi thay đổi có hiệu lực, truy vấn hoặc ghi vào `shipping_note` không còn hợp lệ. Tuy nhiên, **bỏ định nghĩa cột không có nghĩa mọi SSTable chứa cell của cột đó lập tức được viết lại**. Cassandra dùng schema và thông tin thời điểm xóa để ngăn dữ liệu không còn hợp lệ xuất hiện, trong khi việc thu hồi dung lượng vật lý chịu ảnh hưởng của cơ chế lưu trữ, compaction và quy trình vận hành.

### Không thể bỏ cột khóa chính theo cách này

Trong bảng ví dụ, `customer_id` là partition key; `created_at` và `order_id` là clustering columns. Không thể dùng `DROP` để xóa bất kỳ thành phần nào của khóa chính rồi giả định Cassandra tự phân hoạch lại dữ liệu.

Nếu muốn thay đổi khóa chính, cách thiết kế thông thường là tạo **bảng mới** có khóa khác, chuyển dữ liệu có kiểm soát, cập nhật các truy vấn, rồi ngừng sử dụng bảng cũ sau khi đã xác minh.

### Kiểm tra phụ thuộc trước khi DROP

Cột có thể được tham chiếu bởi:

- Truy vấn CQL, prepared statements và mapper của ứng dụng Java.
- Index hoặc materialized view, nếu hệ thống sử dụng những đối tượng đó.
- Quy trình ETL/CDC, truy vấn báo cáo, job đồng bộ và các dịch vụ đọc dữ liệu.

Một số loại cột và đối tượng phụ thuộc có thể khiến `DROP` bị từ chối theo phiên bản Cassandra. Đừng chọn cách bỏ kiểm tra lỗi hay ép schema thay đổi; hãy tháo gỡ phụ thuộc bằng migration có thứ tự.

**Đừng dùng `DROP old_col` rồi `ADD old_col new_type` như một công cụ ép chuyển kiểu.** Cell cũ có thể vẫn còn trong các SSTable và cấu hình về dropped columns có ý nghĩa đối với cách Cassandra đọc dữ liệu. Cần migration dữ liệu có chủ đích.

## 6. RENAME: đổi tên không đồng nghĩa đổi khóa, kiểu hoặc dữ liệu

Cassandra có cú pháp:

```sql
ALTER TABLE schema_lab.orders_by_customer
RENAME customer_id TO buyer_id;
```

**Đây là ví dụ về cú pháp và điều kiện cần xem xét, không phải bước bắt buộc trong lab ở phần 3.** Khả năng `RENAME` phụ thuộc loại cột và phiên bản Cassandra. Trong nhiều phiên bản, phạm vi hỗ trợ tập trung vào **cột thuộc khóa chính**, kèm hạn chế với index/materialized view và các phụ thuộc schema. Cột regular như `status` thường không thể được đổi tên tự do bằng `RENAME`.

Nếu phiên bản và bảng thật cho phép đổi `customer_id` thành `buyer_id`:

- Kiểu `uuid` và vai trò **partition key** vẫn là bản chất của cột; thao tác chỉ đổi tên định danh.
- Không có chuyện dữ liệu được chuyển thành partition mới vì tên khác.
- Toàn bộ câu CQL, mapper, truy vấn theo partition key và code Java phải đổi sang `buyer_id` khi schema mới có hiệu lực.

Do đó, **đổi tên cột khóa chính không giải quyết yêu cầu đổi partition key về mặt ngữ nghĩa**. Muốn phân vùng theo `tenant_id` và `customer_id` thay vì `customer_id` đơn lẻ, phải thiết kế bảng khác và nhập lại dữ liệu theo khóa mới.

| Yêu cầu | `RENAME` phù hợp? | Cách tiếp cận |
| --- | --- | --- |
| Đổi nhãn cột khóa chính, giữ đúng kiểu và vai trò | Có thể, nếu phiên bản và phụ thuộc cho phép | Kiểm tra DDL, phụ thuộc rồi đổi mã ứng dụng |
| Đổi `customer_id uuid` sang `customer_id text` | Không | Migration dữ liệu/thiết kế bảng mới |
| Chuyển partition key từ `customer_id` sang `order_id` | Không | Tạo bảng theo truy vấn mới, backfill |
| Đổi tên cột regular `status` sang `state` | Không nên giả định hỗ trợ | Thêm cột mới, dual-write/backfill, cắt chuyển |
| Đổi tên bảng hoặc keyspace | Không có lệnh `RENAME` bảng/keyspace chung tương đương | Tạo đối tượng mới và di chuyển |

Nếu phải thay đổi tên mà không thể `RENAME`, có thể thêm cột mới, backfill và chuyển ứng dụng dần; với khóa chính, cần tạo bảng mới.

## 7. WITH: đổi table options và hiểu phạm vi hiệu lực

`ALTER TABLE ... WITH ...` thay đổi thuộc tính **của bảng**. Nó không đổi RF của keyspace, không thay partition key, và không bảo đảm mọi dữ liệu cũ tự được tính toán lại theo cấu hình mới.

### 7.1. Comment và TTL mặc định

Ví dụ đổi mô tả và TTL mặc định:

```sql
ALTER TABLE schema_lab.orders_by_customer
WITH comment = 'Orders indexed by customer for recent lookups'
 AND default_time_to_live = 604800;
```

`604800` là số giây trong bảy ngày. `default_time_to_live` tác động tới **các lần ghi mới không chỉ định TTL riêng** theo quy tắc của Cassandra; thay đổi này **không tự thêm TTL hồi tố** cho những cell đã được ghi trước đó. Nếu cần xóa dữ liệu lịch sử theo chính sách mới, phải có kế hoạch lưu trữ/dọn dữ liệu riêng.

Ví dụ tắt TTL mặc định cho các lần ghi sau:

```sql
ALTER TABLE schema_lab.orders_by_customer
WITH default_time_to_live = 0;
```

Tắt TTL mặc định không khôi phục dữ liệu đã hết hạn. Đối với bảng đơn hàng nghiệp vụ, TTL phải được đánh giá theo yêu cầu lưu trữ và tuân thủ, không tùy tiện đặt bảy ngày chỉ vì ví dụ.

### 7.2. Compaction và compression

Ví dụ chỉnh compaction strategy:

```sql
ALTER TABLE schema_lab.orders_by_customer
WITH compaction = {
    'class': 'LeveledCompactionStrategy'
};
```

Đây là **mẫu cú pháp**, không phải lựa chọn chiến lược compaction tối ưu cho mọi workload. Cassandra có các chiến lược và tham số phù hợp với những mẫu dữ liệu khác nhau, chẳng hạn STCS/LCS/TWCS. Khi đổi compaction, Cassandra áp dụng quy tắc mới cho công việc compaction, có thể phát sinh tải I/O và dung lượng tạm thời; không thể suy ra tất cả SSTable đã lập tức chuyển sang cấu trúc mới.

Compression cũng thường được cấu hình qua table option:

```sql
ALTER TABLE schema_lab.orders_by_customer
WITH compression = {
    'class': 'LZ4Compressor'
};
```

Compression có thể ảnh hưởng SSTable được ghi/compaction về sau; cần tính chi phí CPU, I/O, dung lượng và phiên bản Cassandra. Không xem đây là lệnh nén tức thời toàn bộ dữ liệu trên đĩa.

### 7.3. gc_grace_seconds và an toàn tombstone

`gc_grace_seconds` liên quan tới khoảng thời gian giữ tombstone để các replica có cơ hội nhận biết dữ liệu đã bị xóa. Giảm tùy tiện giá trị này trong hệ thống có replica mất kết nối lâu hoặc repair không đều có thể khiến dữ liệu đã xóa xuất hiện lại khi replica cũ trở lại.

```sql
-- Chỉ minh họa thuộc tính, không phải khuyến nghị vận hành:
ALTER TABLE schema_lab.orders_by_customer
WITH gc_grace_seconds = 864000;
```

Giá trị thực tế cần dựa trên phiên bản Cassandra, chiến lược repair và thời gian có thể gián đoạn của replica. Không hạ thấp thời gian này chỉ để “xóa tombstone nhanh hơn”.

| Table option | Mục đích chính | Cần đánh giá |
| --- | --- | --- |
| `comment` | Gắn mô tả cho bảng | Thường ít tác động đến dữ liệu |
| `default_time_to_live` | TTL mặc định cho các ghi phù hợp về sau | Không retroactive; nguy cơ hết hạn dữ liệu |
| `compaction` | Chiến lược tổ chức và gộp SSTable | I/O, write amplification, đọc và không gian đĩa |
| `compression` | Cách nén SSTable | CPU, dung lượng, hiệu quả truy vấn |
| `gc_grace_seconds` | Liên quan thời hạn an toàn loại bỏ tombstone | Repair, replica offline, nguy cơ dữ liệu “sống lại” |
| `caching` | Chính sách cache của bảng | Bộ nhớ, access pattern |

Không phải mọi option đều hợp lệ trên mọi loại bảng hoặc phiên bản Cassandra; ví dụ bảng counter có hạn chế riêng về TTL.

## 8. Điều kiện thay đổi kiểu dữ liệu: phân biệt cú pháp và chuyển đổi an toàn

Một lỗi suy luận phổ biến là tưởng `ALTER TABLE` hoạt động giống lệnh `ALTER COLUMN TYPE` của nhiều hệ quản trị quan hệ: thay kiểu khai báo rồi Cassandra tự đọc dữ liệu cũ và chuyển từng giá trị sang kiểu mới.

**Trên các phiên bản Cassandra hiện đại, không có cơ chế ALTER TABLE chuyển đổi kiểu cột tùy ý và tự viết lại dữ liệu hiện hữu.** Cú pháp thay kiểu từng xuất hiện hoặc có giới hạn ở một số đời CQL/Cassandra cũ; không thể mặc định rằng `ALTER TABLE ... ALTER column TYPE ...` được phiên bản đang vận hành chấp nhận. Phải kiểm tra tài liệu của **đúng phiên bản**, loại cột và các giới hạn chuyển đổi trước khi dự tính migration.

Ngay cả trong môi trường có hỗ trợ một chuyển đổi rất hạn chế, điều kiện tối thiểu phải đánh giá là liệu **biểu diễn bytes hiện hữu** có tương thích với kiểu đích hay không. Đổi metadata không tự biến biểu diễn cũ thành một cách mã hóa mới; ngoài ra cần xét ảnh hưởng đến khóa, collection, UDT, index và mã client.

### 8.1. Một số ví dụ không thể coi là đổi kiểu tại chỗ

| Thay đổi mong muốn | Vấn đề | Hướng xử lý thực tế |
| --- | --- | --- |
| `price text` → `price decimal` | Chuỗi và số thập phân có biểu diễn khác; còn có dữ liệu không parse được | Thêm `price_decimal`, chuyển đổi từng giá trị hợp lệ và cắt chuyển |
| `customer_id uuid` → `customer_id text` (partition key) | Đổi kiểu khóa có thể thay biểu diễn/token và cách truy vấn | Tạo bảng mới với khóa và quy trình chuyển dữ liệu |
| `created_at timestamp` → `created_at text` (clustering key) | Thay kiểu khóa ảnh hưởng mã hóa, thứ tự sắp xếp và điều kiện truy vấn | Tạo bảng mới rồi ghi dữ liệu theo thiết kế mới |
| `tags text` → `tags set<text>` | Đổi scalar sang collection, cách lưu/đọc khác | Cột mới hoặc bảng mới, chuyển đổi dữ liệu |
| `address frozen<address_type>` → UDT có cấu trúc khác | Cần kiểm tra quy tắc tương thích, frozen/non-frozen và nâng cấp UDT | Thiết kế migration UDT/bảng theo phiên bản, kiểm thử bằng dữ liệu thật |
| `text` ↔ `varchar` | Là tên kiểu tương đương trong CQL phổ biến | Thường không đòi hỏi đổi kiểu vật lý; kiểm tra biểu diễn schema thay vì chạy DDL không cần thiết |

Đặc biệt, **partition key và clustering columns** gắn trực tiếp với mô hình đọc/ghi: không được giả định `ALTER TABLE` có thể thêm/bỏ/thay kiểu các thành phần khóa một cách an toàn. Khi cần thay phân bố partition hoặc thứ tự clustering, hãy tạo bảng phù hợp với truy vấn mới.

### 8.2. Migration “expand → backfill → cutover → contract” cho cột regular

Giả sử cột `status` đang lưu `text` nhưng ứng dụng mới cần mã trạng thái `int`. Có thể chuyển đổi theo các pha:

1. **Expand:** thêm cột mới `status_code int`, giữ nguyên `status text`.
2. **Dual-write:** phiên bản ứng dụng chuyển tiếp ghi cả hai cột, hoặc xây dựng cơ chế đồng bộ phù hợp để tránh lệch dữ liệu.
3. **Backfill:** chuyển các giá trị cũ theo ánh xạ nghiệp vụ, ví dụ `PAID → 2`; chạy có giới hạn tải và có khả năng tiếp tục sau lỗi.
4. **Verify:** kiểm tra dữ liệu theo partition, số lượng, tính đúng đắn mapping và kết quả truy vấn ở CL cần thiết.
5. **Cutover:** chuyển toàn bộ đường đọc sang cột mới sau khi dữ liệu và client đã sẵn sàng.
6. **Contract:** chỉ bỏ cột cũ khi đã hết phụ thuộc và có phương án phục hồi.

Ví dụ CQL cho một hàng:

```sql
ALTER TABLE schema_lab.orders_by_customer
ADD status_code int;

UPDATE schema_lab.orders_by_customer
SET status_code = 2
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND created_at = '2026-11-20T08:00:00Z'
  AND order_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

SELECT status, status_code
FROM schema_lab.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
```

Cassandra không cung cấp một câu lệnh `UPDATE` quét toàn bảng và chuyển tất cả hàng theo kiểu SQL quan hệ. Với dữ liệu lớn, thường phải xây dựng công cụ backfill theo partition key, xử lý pagination, retry có giới hạn và đối chiếu kết quả. Không lạm dụng `ALLOW FILTERING` để biến một backfill khổng lồ thành truy vấn trực tiếp trên cluster.

### 8.3. Đổi primary key cần bảng mới

Nếu từ bảng `orders_by_customer` bạn muốn tìm đơn hàng trực tiếp theo `order_id` với độ trễ ổn định, nên xây dựng bảng phục vụ truy vấn đó:

```sql
CREATE TABLE IF NOT EXISTS schema_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    amount decimal,
    status_code int
);
```

Bảng mới có partition key `order_id`. Quy trình nghiệp vụ phải ghi/đồng bộ các bảng theo nhu cầu truy vấn, backfill dữ liệu lịch sử và xử lý tính nhất quán giữa các bản dữ liệu phi chuẩn hóa. `ALTER TABLE` trên bảng cũ không thể tự đổi partition key thành `order_id` hay tự tạo bảng được phân phối theo khóa mới.

## 9. Quan sát schema sau ALTER TABLE

Sau mỗi thay đổi, cần kiểm tra Cassandra **đã ghi nhận điều gì** và ứng dụng có thể dựa vào schema mới hay chưa.

Trong `cqlsh`:

```sql
DESCRIBE TABLE schema_lab.orders_by_customer;
```

Với bảng metadata:

```sql
-- Xem các cột, kiểu và vai trò trong khóa.
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'schema_lab'
  AND table_name = 'orders_by_customer';

-- Xem các table options quan trọng.
SELECT table_name, default_time_to_live, gc_grace_seconds,
       compaction, compression, comment
FROM system_schema.tables
WHERE keyspace_name = 'schema_lab'
  AND table_name = 'orders_by_customer';
```

| Nơi kiểm tra | Điều cần xác nhận |
| --- | --- |
| `system_schema.columns` | Cột được thêm/bỏ đúng chưa? `kind`, `type`, `position` có khớp kỳ vọng không? |
| `system_schema.tables` | TTL mặc định, compaction, compression và comment đã đổi như dự kiến chưa? |
| `DESCRIBE TABLE` | DDL toàn bộ bảng vẫn tương thích với thiết kế và các phụ thuộc không? |
| Schema agreement | Các node đã nhận cùng schema version trước khi tiếp tục bước phụ thuộc chưa? |
| Truy vấn thử theo partition key | Driver/CQL có đọc-ghi được cột mới với kiểu đúng không? |

`DESCRIBE` là câu lệnh tiện ích của `cqlsh`, không phải câu CQL mà driver Java nhất thiết thực thi trực tiếp. Metadata từ `system_schema` có thể truy vấn bằng driver, nhưng việc metadata khớp **không chứng minh dữ liệu lịch sử đã được backfill đầy đủ**.

### Schema agreement và phối hợp phiên bản ứng dụng

Trong cluster nhiều node, schema được lan truyền; một thao tác `ALTER TABLE` thành công qua coordinator không nhất thiết có nghĩa **mọi node tức thời** đã sẵn sàng cho truy vấn phụ thuộc cột mới. Theo dõi schema agreement qua công cụ/driver phù hợp; tránh chạy nhiều thay đổi schema phụ thuộc nhau đồng thời.

Nếu ứng dụng Java có nhiều instance:

- Đặt migration schema dưới một cơ chế điều phối, tránh mỗi instance tự chạy DDL xung đột.
- Triển khai theo thứ tự tương thích ngược: thêm cột, chờ schema agreement, đưa phiên bản ứng dụng mới vào, backfill/cutover rồi mới bỏ cột cũ.
- Với prepared statement, kiểm tra mã client tương thích schema mới; chuẩn bị lại statement hoặc cập nhật metadata khi phát sinh lỗi do schema.
- Kiểm tra mức consistency cho quá trình backfill và đọc xác minh, đồng thời tránh ảnh hưởng write path/compaction/repair đang chạy.

## 10. Ví dụ Java: kiểm tra cột rồi ghi bằng prepared statement

Ví dụ minh họa Cassandra Java Driver 4.x. Giả sử `CqlSession session` đã được tạo và quản lý vòng đời; cột `status_code` đã được thêm, schema agreement đã hoàn tất.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.util.UUID;

// session đã tồn tại, kết nối đúng cluster/keyspace.
Row metadata = session.execute("""
    SELECT kind, type
    FROM system_schema.columns
    WHERE keyspace_name = 'schema_lab'
      AND table_name = 'orders_by_customer'
      AND column_name = 'status_code'
    """).one();

if (metadata == null
        || !"regular".equals(metadata.getString("kind"))
        || !"int".equals(metadata.getString("type"))) {
    throw new IllegalStateException("status_code chưa có hoặc sai kiểu");
}

PreparedStatement update = session.prepare("""
    UPDATE schema_lab.orders_by_customer
    SET status_code = ?
    WHERE customer_id = ?
      AND created_at = ?
      AND order_id = ?
    """);

session.execute(update.bind(
    2,
    UUID.fromString("11111111-1111-4111-8111-111111111111"),
    Instant.parse("2026-11-20T08:00:00Z"),
    UUID.fromString("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
));
```

Java text block yêu cầu Java 15 trở lên. Bind marker `?` dùng cho **giá trị**, không thay tên keyspace/table/cột. Nếu ứng dụng cần hỗ trợ Java phiên bản cũ hơn, dùng chuỗi Java thông thường với đúng escape.

Đoạn ví dụ chỉ xác minh một cột regular. Migration production phải còn kiểm tra khóa chính, các cột quan trọng, table options và các giả thiết về dữ liệu trước khi mở chức năng phụ thuộc schema mới.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `ADD` thành công nhưng hàng cũ trả về `null` | Thêm cột không backfill dữ liệu | Xử lý `null`, triển khai backfill khi nghiệp vụ cần |
| `DROP` cột thất bại | Cột là phần khóa chính hoặc còn index/view/phụ thuộc | Kiểm tra metadata và xử lý đúng mô hình, không ép lệnh |
| `RENAME` bị từ chối | Loại cột hoặc phiên bản không cho phép | Đánh giá chiến lược cột mới/bảng mới và chuyển ứng dụng |
| Thử `ALTER COLUMN ... TYPE` bị lỗi cú pháp | Cú pháp đổi kiểu không được phiên bản hỗ trợ | Thêm cột mới hoặc tạo bảng mới, chuyển giá trị có kiểm soát |
| Sửa TTL nhưng dữ liệu cũ không tự hết hạn | `default_time_to_live` không áp hồi tố | Thiết kế xử lý dữ liệu lịch sử riêng |
| Đổi compaction mà I/O tăng | SSTable cần được xử lý theo chiến lược mới | Theo dõi compaction, dung lượng đĩa, tải node |
| Sau ADD một số instance Java lỗi `Undefined column` | Schema chưa lan truyền hoặc client chưa cập nhật metadata | Chờ schema agreement, xử lý refresh/reprepare hợp lý |
| Đổi `gc_grace_seconds` rồi dữ liệu đã xóa xuất hiện lại | Replica thiếu tombstone quá lâu, repair không phù hợp | Rà soát cấu hình và quy trình repair, đánh giá khôi phục |
| `ALTER TABLE` xong nhưng truy vấn theo khóa mới không hiệu quả | Không thể đổi partition key bằng thêm cột thường | Thiết kế bảng mới theo truy vấn và backfill |
| Bảng có tên đúng nhưng định nghĩa khác mong đợi | `CREATE IF NOT EXISTS` trước đó đã bỏ qua schema hiện hữu | Đọc `system_schema`, đánh giá drift rồi chạy migration đúng |

## 12. Bài thực hành có thể tự kiểm chứng

Trên keyspace `schema_lab` ở mục 3 (hoặc một keyspace lab của riêng bạn):

1. Kiểm tra `DESCRIBE TABLE` và `system_schema.columns` để ghi lại schema ban đầu, đặc biệt `customer_id`, `created_at`, `order_id`.
2. Thêm `shipping_note text` và kiểm tra bảng metadata xuất hiện cột mới. Đọc một hàng trước khi ghi cột này để thấy `null`.
3. Cập nhật `shipping_note` cho một hàng theo **đầy đủ PRIMARY KEY**, đọc lại và xác nhận nội dung.
4. Dùng `ALTER TABLE ... WITH comment = '...'` để đổi mô tả. Đọc `system_schema.tables.comment` xác nhận.
5. Thêm `status_code int`, chuyển thử một giá trị `'PAID'` thành `2`, rồi giải thích vì sao một lệnh `ALTER` không tự chuyển mọi chuỗi cũ.
6. Bỏ `shipping_note` sau khi chắc chắn không còn cần nó; xác nhận cột không còn trong `system_schema.columns`.
7. Tự thiết kế bảng `orders_by_id` cho truy vấn bằng `order_id`; giải thích vì sao chỉ `ADD order_id` vào một bảng khác sẽ **không** đổi partition key.

Chỉ khi dữ liệu lab không cần giữ, có thể dọn riêng môi trường thử nghiệm:

```sql
-- Cảnh báo: xóa toàn bộ các bảng và dữ liệu trong schema_lab.
DROP KEYSPACE IF EXISTS schema_lab;
```

Không thực hiện câu `DROP` này trên keyspace có dữ liệu hoặc dịch vụ đang sử dụng.

## 13. Checklist trước khi đưa ALTER TABLE lên production

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Bảng và cluster đích đúng chưa? | Tên đầy đủ `keyspace.table`, môi trường kết nối, metadata |
| Thay đổi thuộc loại `ADD`, `DROP`, `RENAME` hay `WITH`? | Cú pháp hợp lệ cho đúng phiên bản Cassandra |
| Có đụng partition/clustering key không? | So sánh khóa trong `system_schema.columns`; thiết kế bảng mới nếu cần |
| Có cần chuyển đổi giá trị cũ không? | Kế hoạch backfill, ánh xạ kiểu dữ liệu, xử lý dữ liệu lỗi và xác minh |
| Có index, materialized view hoặc mã Java phụ thuộc không? | Danh sách phụ thuộc, thứ tự triển khai tương thích |
| Có thay đổi TTL/compaction/compression không? | Đánh giá dữ liệu, tài nguyên đĩa, I/O và tác động vận hành |
| Các node đã thống nhất schema chưa? | Schema agreement và truy vấn metadata sau thay đổi |
| Khi nào có thể bỏ cột/bảng cũ? | Đã cutover, dữ liệu đã đối chiếu, phụ thuộc đã hết, phương án phục hồi rõ ràng |
| Có ảnh hưởng tính sẵn sàng/CL trong lúc migration không? | Theo dõi lỗi, tải ghi/đọc, điều kiện replica/repair |

**Ghi nhớ:** `ALTER TABLE` trong Cassandra chủ yếu thay đổi **schema và các tùy chọn bảng**. Thêm cột không tự backfill, bỏ cột không dọn mọi SSTable tức thời, đổi table option không nhất thiết áp dụng hồi tố, và đổi kiểu/khóa chính thường đòi hỏi migration có thiết kế. Đọc metadata, kiểm tra schema agreement và chuyển đổi dữ liệu theo từng pha là cách phối hợp an toàn giữa CQL, replication/compaction/repair và ứng dụng Java.
