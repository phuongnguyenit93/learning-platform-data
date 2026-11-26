# Cơ sở dữ liệu cột rộng và cách nhìn dữ liệu qua bảng CQL

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao Apache Cassandra được xếp vào nhóm **cơ sở dữ liệu cột rộng (wide-column database)**, và vì sao bảng CQL không hoạt động giống hệt bảng trong cơ sở dữ liệu quan hệ.
- Phân biệt **keyspace**, **table**, **partition**, **partition key**, **clustering column** và các cột dữ liệu thông thường.
- Đọc một câu lệnh `CREATE TABLE` để xác định dữ liệu nào được đặt cùng partition, hàng nào là duy nhất và thứ tự sắp xếp trong partition.
- Nhận biết truy vấn phù hợp với khóa chính, truy vấn dễ gây quét dữ liệu, và lý do cần thiết kế bảng theo cách ứng dụng đọc dữ liệu.
- Kết nối mô hình lưu trữ của Cassandra với những lựa chọn khi sử dụng Spring Data Cassandra: entity mapping, repository, `CassandraTemplate` và câu lệnh CQL.

## 1. Cassandra là cơ sở dữ liệu cột rộng theo nghĩa nào?

Apache Cassandra là cơ sở dữ liệu phân tán, thiết kế để lưu và truy cập dữ liệu trên nhiều node, có khả năng nhân bản dữ liệu và mở rộng theo chiều ngang. Cassandra thường được gọi là **wide-column store** hoặc **column-family database**.

Chữ *cột rộng* dễ gây hiểu nhầm. Nó **không có nghĩa** mỗi bảng Cassandra bắt buộc phải định nghĩa hàng nghìn cột như một bảng SQL rất rộng. Cách hiểu hữu ích hơn khi học Cassandra là:

1. Dữ liệu của một bảng được chia thành nhiều **partition** dựa trên partition key.
2. Bên trong một partition có thể tồn tại **nhiều hàng CQL**, được xác định và sắp thứ tự bằng clustering column.
3. Mỗi hàng lưu các giá trị ở những cột được định nghĩa trong schema; các cột dữ liệu không nhất thiết phải có giá trị ở mọi hàng.

Vì vậy, một partition có thể chứa nhiều hàng theo thời gian hoặc theo một chiều sắp xếp khác. Đây là nguồn gốc thực tế của khái niệm *wide row/partition*: một khóa phân vùng có thể gắn với rất nhiều bản ghi liên quan. Tuy nhiên, **partition không nên tăng vô hạn**; partition quá lớn gây áp lực cho đọc, ghi, bộ nhớ và compaction.

Cassandra có cú pháp **Cassandra Query Language (CQL)** giống SQL ở các câu lệnh như `CREATE TABLE`, `INSERT` và `SELECT`. Sự giống nhau chủ yếu nằm ở **cách viết**, còn cách đặt dữ liệu và khả năng truy vấn dựa vào partition key, clustering columns và cấu trúc phân tán.

### Nhìn từ bảng CQL xuống dữ liệu vật lý

```text
Keyspace: learning_demo
└── Table: page_views_by_user_day
    ├── Partition (user_id = U1, view_day = 2026-11-25)
    │   ├── Row (viewed_at = 10:05, view_id = V3) -> page_url, device
    │   ├── Row (viewed_at = 09:40, view_id = V2) -> page_url, device
    │   └── Row (viewed_at = 08:30, view_id = V1) -> page_url, device
    ├── Partition (user_id = U1, view_day = 2026-11-26)
    │   └── Row (...)
    └── Partition (user_id = U2, view_day = 2026-11-25)
        └── Row (...)
```

Đây là **sơ đồ logic**, không phải sơ đồ ánh xạ một partition vào đúng một máy. Cassandra tính token từ partition key để xác định vị trí dữ liệu trong cụm; các bản sao (*replica*) của partition có thể được đặt trên nhiều node tùy chiến lược replication. Trong mỗi partition, Cassandra tổ chức các hàng theo clustering columns.

So với bảng quan hệ, câu hỏi đầu tiên thường là “các thực thể liên quan thế nào?”. Với Cassandra, câu hỏi thiết kế thường bắt đầu từ “ứng dụng cần đọc những bản ghi nào cùng nhau, theo khóa nào và theo thứ tự nào?”.

## 2. Những thành phần cần nhận ra trong bảng CQL

| Thành phần | Ý nghĩa | Điều cần nhớ khi thiết kế |
| --- | --- | --- |
| **Keyspace** | Không gian tên chứa các bảng và cấu hình replication. | Tương tự một cấp tổ chức schema, nhưng còn liên quan trực tiếp đến nhân bản dữ liệu. |
| **Table** | Định nghĩa cột, kiểu dữ liệu, khóa chính và tùy chọn lưu trữ/truy vấn. | Một bảng thường phục vụ một mẫu truy vấn hoặc nhóm truy vấn gần nhau. |
| **Partition** | Nhóm các hàng có cùng giá trị partition key. | Đơn vị quan trọng để định tuyến và truy cập dữ liệu. |
| **Partition key** | Một hoặc nhiều cột dùng để phân bố dữ liệu giữa các node. | Chọn để truy vấn định vị partition và tránh phân bố lệch. |
| **Clustering column** | Cột thuộc khóa chính, xác định hàng và thứ tự bên trong partition. | Phù hợp với truy vấn theo thời gian, khoảng giá trị hoặc thứ tự. |
| **Regular column** | Cột chứa dữ liệu nghiệp vụ, không thuộc khóa chính. | Không tự động trở thành cột lọc hiệu quả. |
| **Static column** | Cột có một giá trị dùng chung cho các hàng trong một partition. | Hữu ích cho thuộc tính cấp partition; cần bảng có clustering column. |

### Đọc đúng cú pháp `PRIMARY KEY`

Cặp ngoặc trong khóa chính làm thay đổi cách Cassandra phân vùng dữ liệu:

```sql
-- id là partition key; không có clustering column
PRIMARY KEY (id)

-- customer_id là partition key; order_id là clustering column
PRIMARY KEY (customer_id, order_id)

-- (customer_id, order_day) cùng tạo thành partition key;
-- order_id là clustering column
PRIMARY KEY ((customer_id, order_day), order_id)
```

Ở ví dụ thứ ba, Cassandra tính khóa phân vùng từ **cả** `customer_id` và `order_day`. Không thể coi `customer_id` riêng lẻ là một partition key hoàn chỉnh. Toàn bộ thành phần của khóa chính xác định duy nhất một hàng CQL; hai lần ghi cùng khóa chính sẽ tác động lên cùng hàng.

Một điểm quan trọng: clustering column **không quyết định node chứa partition**. Nó quyết định định danh và trật tự các hàng **sau khi** partition đã được xác định.

## 3. Ví dụ từ nhu cầu truy vấn: lịch sử truy cập theo người dùng và ngày

Giả sử hệ thống cần hiển thị **20 lượt xem trang mới nhất của một người dùng trong một ngày**. Ứng dụng đã biết `user_id` và ngày muốn xem, đồng thời muốn dữ liệu mới nhất xuất hiện trước.

Mẫu truy vấn này dẫn đến thiết kế:

- **Partition key**: `(user_id, view_day)` để gom lượt xem theo người dùng và ngày.
- **Clustering columns**: `viewed_at` và `view_id` để sắp xếp theo thời gian, đồng thời phân biệt hai lượt xem có cùng thời điểm.
- **Regular columns**: `page_url` và `device` là thông tin trả về.

### 3.1. Tạo keyspace và bảng

```sql
-- Ví dụ cho môi trường thử nghiệm một node; không áp dụng cấu hình
-- replication này như một mặc định cho production.
CREATE KEYSPACE IF NOT EXISTS learning_demo
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE learning_demo;

CREATE TABLE IF NOT EXISTS page_views_by_user_day (
    user_id uuid,
    view_day date,
    viewed_at timestamp,
    view_id uuid,
    page_url text,
    device text,
    PRIMARY KEY ((user_id, view_day), viewed_at, view_id)
) WITH CLUSTERING ORDER BY (viewed_at DESC, view_id DESC);
```

Trong môi trường nhiều datacenter, cần cấu hình replication phù hợp (thường là `NetworkTopologyStrategy`), chọn số bản sao theo yêu cầu khả dụng và tính nhất quán.

### 3.2. Ghi các hàng vào cùng một partition

```sql
INSERT INTO page_views_by_user_day
  (user_id, view_day, viewed_at, view_id, page_url, device)
VALUES
  (11111111-1111-4111-8111-111111111111,
   '2026-11-25', '2026-11-25T08:30:00Z',
   22222222-2222-4222-8222-222222222222,
   '/courses/cassandra', 'desktop');

INSERT INTO page_views_by_user_day
  (user_id, view_day, viewed_at, view_id, page_url, device)
VALUES
  (11111111-1111-4111-8111-111111111111,
   '2026-11-25', '2026-11-25T10:05:00Z',
   33333333-3333-4333-8333-333333333333,
   '/courses/spring-data-cassandra', 'mobile');
```

Hai hàng có **cùng partition key** là `(user_id, view_day)` nhưng có clustering key khác nhau. Chúng nằm trong cùng partition logic. Vì bảng khai báo `viewed_at DESC`, hàng lúc 10:05 đứng trước hàng lúc 08:30 khi đọc theo thứ tự mặc định trong partition.

`view_day` là một *time bucket* (nhóm theo ngày). Nếu một người dùng tạo quá nhiều lượt xem trong một ngày, có thể cân nhắc bucket theo giờ hoặc bổ sung phân đoạn phù hợp. Đổi bucket sẽ ảnh hưởng cách truy vấn và cách ghép kết quả; không có kích cỡ bucket tối ưu cho mọi hệ thống.

### 3.3. Đọc đúng partition

```sql
SELECT viewed_at, view_id, page_url, device
FROM page_views_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND view_day = '2026-11-25'
LIMIT 20;
```

Truy vấn xác định **đủ hai thành phần partition key**, rồi đọc tối đa 20 hàng trong partition theo thứ tự clustering mặc định. Nó khớp với nhu cầu “20 lượt xem mới nhất của U1 trong ngày 25/11”.

Nếu muốn lọc theo khoảng thời gian trong ngày, có thể thêm điều kiện trên clustering column đầu tiên:

```sql
SELECT viewed_at, view_id, page_url
FROM page_views_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND view_day = '2026-11-25'
  AND viewed_at >= '2026-11-25T09:00:00Z'
LIMIT 20;
```

Các giá trị ngày và thời gian ở ví dụ dùng mốc UTC. Khi tạo `view_day` trong ứng dụng, hãy quy định rõ bucket tính theo UTC hay múi giờ nghiệp vụ; nếu quy ước không nhất quán, dữ liệu có thể rơi vào ngày khác với kỳ vọng khi đọc.

### 3.4. Hàng CQL khác partition như thế nào?

Xét hai khóa:

```text
Partition key: (U1, 2026-11-25)
  Clustering key: (2026-11-25T10:05:00Z, V2) -> một hàng CQL
  Clustering key: (2026-11-25T08:30:00Z, V1) -> một hàng CQL
```

Nếu ghi thêm một lượt xem có `view_id` mới, Cassandra thêm một hàng logic vào cùng partition. Nếu ghi lại với **toàn bộ khóa chính giống hệt**, đây là thao tác kiểu *upsert*: các giá trị cột được ghi trong lệnh được cập nhật theo cơ chế ghi của Cassandra. Khóa chính không hoạt động như số thứ tự tự tăng của cơ sở dữ liệu quan hệ.

## 4. Vì sao không thể truy vấn bảng CQL như bảng SQL bất kỳ?

Ở nhiều cơ sở dữ liệu quan hệ, bạn có thể viết `WHERE` theo nhiều cột rồi dựa vào bộ tối ưu truy vấn và các index để lựa chọn kế hoạch thực thi. Trong Cassandra, cách đọc hiệu quả thường cần **xác định partition trước**, sau đó tận dụng clustering columns để tìm hàng bên trong partition.

Với bảng ví dụ, các trường hợp có ý nghĩa khác nhau:

| Nhu cầu truy vấn | Đánh giá | Lý do |
| --- | --- | --- |
| Lấy lượt xem của một `user_id` trong một `view_day` | **Phù hợp** | Có đủ partition key. |
| Lọc tiếp theo `viewed_at` trong partition đó | **Phù hợp** | `viewed_at` là clustering column đầu tiên. |
| Chỉ tìm theo `user_id`, không biết `view_day` | **Không phù hợp với khóa hiện tại** | Partition key gồm cả `user_id` và `view_day`. |
| Tìm tất cả lượt xem có `device = 'mobile'` | **Không được hỗ trợ hiệu quả bằng khóa hiện tại** | `device` là regular column, không định vị được partition. |
| Lấy 20 lượt xem mới nhất của **mọi** người dùng | **Cần mô hình truy vấn khác** | Clustering order chỉ sắp xếp **trong từng partition**, không tạo thứ tự thời gian toàn cục. |

Tùy loại bảng và phiên bản Cassandra, một số truy vấn ngoài khóa có thể dùng index hay `ALLOW FILTERING`. Tuy nhiên, `ALLOW FILTERING` không biến một thiết kế lệch nhu cầu truy vấn thành truy vấn rẻ; nó có thể khiến hệ thống phải đọc và lọc lượng dữ liệu lớn. Không nên thêm `ALLOW FILTERING` chỉ để một truy vấn chạy được.

**`LIMIT 20` cũng không bảo đảm truy vấn rẻ** nếu hệ thống vẫn phải quét qua nhiều partition hoặc bỏ qua nhiều hàng để tìm đủ kết quả. Truy vấn hiệu quả bắt đầu từ mô hình khóa, không bắt đầu từ `LIMIT`.

### Nếu có thêm màn hình “lượt xem theo URL”?

Ứng dụng có thể cần một bảng khác, chẳng hạn `page_views_by_url_day`, với partition key bắt đầu từ URL (hoặc mã trang) và ngày, rồi clustering theo thời điểm xem. Cùng một lượt xem sẽ được ghi vào nhiều bảng để phục vụ các cách đọc khác nhau. Cách **phi chuẩn hóa theo truy vấn** này là một lựa chọn thiết kế phổ biến của Cassandra.

Đổi lại, ứng dụng phải quản lý ghi vào nhiều bảng và xử lý khả năng dữ liệu chưa đồng nhất tức thời giữa các cách nhìn. Cassandra không cung cấp `JOIN` và ràng buộc khóa ngoại kiểu cơ sở dữ liệu quan hệ để tự động thực hiện việc đó.

## 5. Những đặc điểm của dữ liệu cột rộng cần lưu ý

### Partition key: phân bố và định tuyến dữ liệu

Giá trị partition key được băm thành token; Cassandra dựa trên token cùng topology/replication để tìm các replica chịu trách nhiệm. Vì vậy, partition key vừa ảnh hưởng **khả năng truy vấn**, vừa ảnh hưởng **phân bố tải**.

- Khóa có quá ít giá trị khác nhau, chẳng hạn `status = 'ACTIVE'`, dễ tạo các partition lớn hoặc tập trung tải.
- Khóa quá chi tiết có thể tạo rất nhiều partition nhỏ, tăng overhead quản lý và làm truy vấn cần đọc nhiều partition.
- Khóa chứa cả `user_id` và `view_day` thường phân tán tốt hơn khóa chỉ có một hằng số chung, nhưng mức độ phù hợp còn tùy lượng dữ liệu và truy vấn thực tế.

Một partition nóng (*hot partition*) có thể xuất hiện khi nhiều request cùng truy cập một khóa, ngay cả khi toàn cụm còn tài nguyên rảnh.

### Clustering columns: thứ tự cục bộ trong partition

`WITH CLUSTERING ORDER BY (viewed_at DESC, view_id DESC)` đặt thứ tự mặc định của các hàng trong từng partition. Đây không phải `ORDER BY` toàn bảng. CQL có các quy tắc giới hạn lọc và sắp xếp theo clustering columns; không nên giả định có thể đảo thứ tự và lọc tùy ý như trong SQL.

Trong ví dụ, `view_id` là clustering column cuối nhằm giữ các lượt xem có cùng timestamp thành những hàng khác nhau. Nếu chỉ dùng `(user_id, view_day, viewed_at)` làm khóa chính, hai lượt xem ở cùng thời điểm ghi có thể cùng khóa và ghi đè dữ liệu trên cùng hàng.

### Cột thường, cột static và dữ liệu thưa

Một regular column như `page_url` không tham gia khóa chính; một số hàng có thể thiếu giá trị cho cột đó. Cassandra vẫn có schema CQL, nên “dữ liệu thưa” **không có nghĩa** mỗi hàng được tự do đặt tên cột tùy ý mà không khai báo.

Nếu một partition có thuộc tính chung, ví dụ `user_display_name text STATIC`, giá trị đó được chia sẻ ở cấp partition thay vì nhân bản ở mỗi hàng CQL. Cột `STATIC` chỉ phù hợp với dữ liệu thật sự chung cho partition và một bảng có clustering column.

### Ghi, xóa và vòng đời dữ liệu

Cassandra sử dụng cơ chế ghi tối ưu cho lưu trữ phân tán. Các lệnh `INSERT` và `UPDATE` đều có tính chất *upsert* ở mức khóa chính; thiết kế nghiệp vụ không nên mặc định “`INSERT` trùng khóa sẽ báo lỗi” như ở nhiều bảng quan hệ.

Xóa dữ liệu hoặc làm hết hạn dữ liệu qua TTL tạo ra **tombstone** để các replica có thể phối hợp nhận biết dữ liệu đã bị xóa. Nhiều tombstone và partition quá lớn có thể làm đọc chậm. Khi chọn bucket hoặc TTL cho dữ liệu sự kiện, cần cân nhắc cả khối lượng dữ liệu lẫn cách hệ thống đọc chúng.

### Replication và consistency không thay đổi quy tắc khóa

Cassandra có thể lưu nhiều replica của cùng partition. Mức nhất quán đọc/ghi, ví dụ `LOCAL_QUORUM` khi cấu hình phù hợp, quyết định số replica cần phản hồi cho một thao tác. Điều đó **không** khiến CQL có thể tự động `JOIN` hoặc lọc tùy ý bằng regular column. Replication/consistency giải quyết những vấn đề khác với thiết kế truy vấn.

## 6. Liên hệ với Spring Data Cassandra

Spring Data Cassandra hỗ trợ ánh xạ một hàng CQL thành đối tượng Java và cung cấp nhiều cách thao tác dữ liệu:

| Thành phần trong Spring Data Cassandra | Quan hệ với mô hình CQL |
| --- | --- |
| Entity mapping, ví dụ `@Table`, `@PrimaryKey`, `@PrimaryKeyColumn` | Mô tả bảng và khóa chính, bao gồm partition key/clustering column. |
| Repository | Thuận tiện cho các thao tác với entity và những truy vấn có thể diễn đạt bằng repository. |
| `CassandraTemplate` | Thực hiện các thao tác CQL/ánh xạ với quyền kiểm soát rõ hơn. |
| Truy vấn CQL | Thể hiện trực tiếp cách chọn partition, lọc theo clustering columns và đọc dữ liệu. |

Ví dụ, một repository có phương thức đọc lượt xem theo `userId` và `viewDay` vẫn phải tuân thủ **khóa chính của bảng Cassandra**. Việc dùng annotation hoặc tên phương thức repository không làm biến mất quy tắc định tuyến dữ liệu. Khi thiết kế Java entity, hãy xác định khóa CQL trước rồi ánh xạ đúng thành phần partition và clustering; thiếu một cột trong khóa hoặc gán sai loại khóa có thể dẫn đến truy vấn không hợp lệ hoặc dữ liệu ghi sai chỗ mong đợi.

Cũng không nên hiểu repository tương đương ORM quan hệ đầy đủ. Cassandra không cung cấp mô hình `JOIN`, khóa ngoại và truy vấn ad hoc như một RDBMS; Spring Data Cassandra tuân theo những giới hạn và thế mạnh của Cassandra.

## 7. Thiết kế bảng theo truy vấn: quy trình thực hành

Khi nhận một yêu cầu dữ liệu, hãy làm theo thứ tự sau:

1. **Viết câu truy vấn bằng lời.** Ví dụ: “Lấy 20 sự kiện mới nhất của người dùng X trong ngày D”.
2. **Xác định những giá trị luôn có trong request.** Ở đây là `user_id` và `view_day`; chúng là ứng viên tự nhiên cho partition key.
3. **Xác định thứ tự và điều kiện phạm vi.** Ở đây là thời gian giảm dần; chọn `viewed_at` làm clustering column đầu tiên.
4. **Đảm bảo mỗi hàng có khóa riêng.** Bổ sung `view_id` để phân biệt các sự kiện trùng timestamp.
5. **Ước lượng partition lớn đến mức nào.** Đánh giá sự kiện/ngày, kích thước từng hàng và tần suất truy cập. Điều chỉnh bucket nếu cần.
6. **Viết thử các CQL `SELECT` quan trọng.** Kiểm tra chúng có đủ partition key và có dùng clustering columns theo cách Cassandra hỗ trợ hay không.
7. **Xem xét yêu cầu đọc khác.** Nếu màn hình khác cần tìm sự kiện theo trang, hãy cân nhắc bảng chuyên biệt, quy trình ghi đồng bộ và chi phí nhân bản dữ liệu.
8. **Đo đạc với dữ liệu đại diện.** Theo dõi phân bố partition, độ trễ, paging, tombstone, thông lượng đọc/ghi; không đánh giá hiệu năng chỉ bằng tập dữ liệu nhỏ.

Đối với kết quả nhiều hàng, Cassandra và driver hỗ trợ **paging** để lấy dữ liệu theo từng trang. Đây là cách đọc tuần tự bằng trạng thái phân trang, không phải cơ chế `OFFSET` kiểu SQL. Trên một màn hình sự kiện, việc đọc từng trang theo partition và trật tự clustering thường phù hợp hơn việc tải toàn bộ lịch sử vào bộ nhớ.

## 8. Tự kiểm tra cách hiểu

**Câu 1.** Với `PRIMARY KEY ((tenant_id, month), event_time, event_id)`, những cột nào quyết định partition?

**Trả lời:** Cặp `(tenant_id, month)`; `event_time` và `event_id` là clustering columns. Chỉ `tenant_id` không đủ để xác định một partition cụ thể.

**Câu 2.** Hai sự kiện có cùng `tenant_id`, `month` và `event_time`, nhưng khác `event_id`, có phải cùng hàng CQL không?

**Trả lời:** Không. Hai sự kiện ở cùng partition nhưng là hai hàng khác nhau vì toàn bộ clustering key khác nhau.

**Câu 3.** Nếu cần lọc mọi lượt xem có `device = 'mobile'` trên toàn hệ thống, chỉ thêm `WHERE device = 'mobile'` vào bảng mẫu có đủ tốt không?

**Trả lời:** Không. Cột `device` không giúp định vị partition. Cần làm rõ cách người dùng yêu cầu truy vấn, rồi cân nhắc bảng/index thích hợp và kiểm chứng chi phí đọc thực tế.

**Câu 4.** `CLUSTERING ORDER BY (viewed_at DESC)` có bảo đảm lấy được 20 sự kiện mới nhất trên **toàn cụm** không?

**Trả lời:** Không. Thứ tự clustering chỉ áp dụng **bên trong một partition**, nên muốn đọc dữ liệu toàn cụm theo thời gian phải thiết kế một mô hình truy cập khác.

## Kết luận

Khi nhìn một bảng CQL, hãy hình dung theo trật tự **table → partition key → partition → clustering rows → regular columns**. Bảng trông giống bảng SQL, nhưng phần quan trọng nhất là **dữ liệu được gom và định tuyến theo partition key, rồi sắp xếp trong partition bằng clustering columns**.

Hiểu mô hình wide-column giúp bạn chọn khóa chính, giới hạn kích thước partition và xây dựng truy vấn CQL phù hợp trước khi ánh xạ entity hoặc viết repository trong Spring Data Cassandra. Đây là nền tảng để thiết kế hệ thống phân tán có khả năng dự đoán hiệu năng và mở rộng theo nhu cầu thực tế.
