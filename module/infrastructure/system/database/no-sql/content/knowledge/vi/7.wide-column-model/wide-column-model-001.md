# Cách tổ chức keyspace/table, phân vùng và các hàng liên quan

## 1. Vì sao phải hiểu cấu trúc dữ liệu của mô hình cột rộng?

Một cơ sở dữ liệu thuộc họ **wide-column** thường được chọn khi ứng dụng ghi hoặc đọc lượng dữ liệu lớn theo những **khóa truy cập có thể dự đoán**, đồng thời muốn phân phối dữ liệu trên nhiều nút. Tuy nhiên, nếu chỉ hình dung nó như “bảng SQL có rất nhiều cột”, ta sẽ thiết kế sai ngay từ khóa chính.

Ba câu hỏi quan trọng khi tổ chức dữ liệu là:

1. **Keyspace/table** xác định phạm vi tổ chức và chính sách nào?
2. **Partition** nhóm những bản ghi nào để một truy vấn có thể tìm nhanh và phân phối tải hợp lý?
3. **Các hàng liên quan trong một partition** được định danh, sắp xếp và truy xuất theo quy tắc nào?

Bài học sử dụng **Apache Cassandra với CQL** làm ví dụ chính, vì Cassandra thể hiện rõ các khái niệm *keyspace*, *partition key*, *clustering columns* và *row*. Các hệ khác trong họ wide-column như HBase/Bigtable có cách tổ chức gần gũi ở một số điểm nhưng **không dùng chính xác cùng mô hình CQL hoặc cùng quy tắc truy vấn**. Khi áp dụng vào một sản phẩm cụ thể, cần theo hợp đồng của sản phẩm đó.

Hãy tưởng tượng một ứng dụng thu thập nhiệt độ của hàng nghìn thiết bị. Truy vấn phổ biến nhất là:

> “Lấy 100 sự kiện mới nhất của thiết bị D17 thuộc khách hàng T01 trong ngày 14/11/2026.”

Nếu tổ chức đúng, hệ quản trị có thể xác định partition chứa dữ liệu, rồi duyệt các hàng của thiết bị theo thứ tự thời gian. Nếu tổ chức sai, ứng dụng có thể phải quét nhiều partition hoặc tập hợp dữ liệu từ nhiều nơi để trả một trang kết quả nhỏ.

## 2. Bức tranh tổng thể: keyspace → table → partition → row → cell

Trong cách nhìn của Cassandra, có thể hình dung:

~~~text
Cluster Cassandra
└── Keyspace: telemetry
    ├── Table: events_by_device_day
    │   ├── Partition: (T01, D17, 2026-11-14)
    │   │   ├── Row: (08:31:20, event-003) -> temperature, battery, status
    │   │   ├── Row: (08:30:45, event-002) -> temperature, battery, status
    │   │   └── Row: (08:30:10, event-001) -> temperature, battery, status
    │   ├── Partition: (T01, D18, 2026-11-14)
    │   └── Partition: (T01, D17, 2026-11-15)
    └── Table: latest_state_by_device
        ├── Partition: (T01, D17) -> trạng thái mới nhất
        └── Partition: (T01, D18) -> trạng thái mới nhất
~~~

Các thành phần có vai trò khác nhau:

| Cấp | Mục đích | Cần quyết định |
| --- | --- | --- |
| **Cluster** | Các node phối hợp lưu và phục vụ dữ liệu | Cấu hình node, datacenter, vận hành |
| **Keyspace** | Namespace logic cho các bảng, kèm chính sách replication | Tên miền dữ liệu, replication theo datacenter, durable writes |
| **Table** | Định nghĩa cột, kiểu dữ liệu và primary key | Tạo bảng cho truy vấn nào, những trường nào được lưu |
| **Partition** | Tập hàng có **cùng partition key** | Dữ liệu được nhóm theo khóa nào, partition lớn/đông đến đâu |
| **Row** | Một hàng phân biệt bằng **clustering key** trong partition | Sắp xếp và xác định duy nhất từng sự kiện |
| **Cell** | Giá trị một cột thuộc hàng, kèm metadata lưu trữ nội bộ | Kiểu dữ liệu, TTL, cập nhật/xóa |

Đây là **mô hình khái niệm** để học. Về vật lý, một partition có thể có các phần dữ liệu nằm trong memtable và nhiều SSTable; cluster còn giữ replica trên các node khác nhau. Hình cây không có nghĩa mỗi partition là một file riêng hoặc mỗi table nằm trên một máy riêng.

## 3. Keyspace: nhóm bảng và xác định replication

Trong Cassandra, **keyspace** gần với một namespace/database logic của các bảng CQL. Bảng có tên đầy đủ theo dạng:

~~~text
keyspace_name.table_name
~~~

Ví dụ:

~~~sql
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

Ở đây:

- **telemetry** là tên keyspace.
- **NetworkTopologyStrategy** đặt số replica theo từng datacenter được Cassandra nhận diện.
- **dc1: 3** có nghĩa cấu hình mục tiêu **replication factor = 3** trong datacenter tên \`dc1\`, nếu hạ tầng có đủ node và được cấu hình đúng.

Tên datacenter phải khớp với cấu hình topology thực tế. Ví dụ chỉ minh họa một datacenter tên \`dc1\`; không nên sao chép nguyên xi lên cluster sản xuất mà chưa xác minh số node, các miền lỗi và chiến lược đặt replica.

Có thể tạo bảng bằng tên đầy đủ:

~~~sql
CREATE TABLE telemetry.latest_state_by_device (
    tenant_id text,
    device_id text,
    observed_at timestamp,
    temperature double,
    status text,
    PRIMARY KEY ((tenant_id, device_id))
);
~~~

**Hai hiểu nhầm cần tránh:**

1. Keyspace là ranh giới namespace và cấu hình replication; nó **không tự phân tách toàn bộ dữ liệu của mỗi tenant ra một cluster vật lý**.
2. Replication factor là **số bản sao mục tiêu cho mỗi partition trong datacenter tương ứng**, không phải “mọi bản ghi được nhân bản vào mọi node” hoặc “một table có ba partition”.

Chính sách consistency khi đọc/ghi, vị trí datacenter, khả năng chịu lỗi, khôi phục và độ bền ghi cần được xem cùng replication factor. RF = 3 tự nó không bảo đảm mọi kiểu lỗi đều không mất dữ liệu.

### 3.1. Nên tạo một keyspace cho mỗi tenant không?

Thông thường, **không nên tự động tạo keyspace/table riêng cho mỗi tenant** chỉ vì ứng dụng là multi-tenant. Tăng số lượng schema object làm tăng công sức quản lý, migration và metadata trên cluster.

Một lựa chọn phổ biến hơn là lưu **tenant_id** như một phần của khóa phân vùng. Tuy nhiên, nếu các tenant thực sự cần replication, quyền, vòng đời dữ liệu hoặc cô lập hạ tầng khác nhau, việc tổ chức keyspace/cluster riêng có thể cần đánh giá. Ranh giới logic của keyspace không thay thế yêu cầu bảo mật và kiểm soát truy cập ở ứng dụng.

## 4. Table trong Cassandra được thiết kế theo truy vấn

RDBMS thường bắt đầu bằng mô hình thực thể và quan hệ; Cassandra thường bắt đầu bằng **câu hỏi ứng dụng cần trả lời nhanh**.

Với hệ theo dõi thiết bị, ba truy vấn có thể là:

| Mã | Truy vấn thường xuyên | Khóa truy cập tự nhiên |
| --- | --- | --- |
| Q1 | Lấy sự kiện của thiết bị trong một ngày, mới nhất trước | tenant + device + day |
| Q2 | Lấy trạng thái hiện tại của một thiết bị | tenant + device |
| Q3 | Lấy sự kiện lỗi của tenant theo ngày | tenant + day + severity hoặc status |

Một table phục vụ Q1 có thể lưu nhiều sự kiện trong cùng partition; table cho Q2 chỉ cần một trạng thái hiện tại trên mỗi thiết bị; Q3 có thể cần bảng/bản chiếu khác. Trong Cassandra, **tạo nhiều bảng phục vụ các cách truy vấn khác nhau** là một chiến lược mô hình hóa quen thuộc.

Điều này có thể làm dữ liệu bị lặp. Đổi lại, đường truy cập đọc trở nên dự đoán được. Việc tạo nhiều bản sao dữ liệu cần cơ chế cập nhật, xử lý lỗi và tiêu chí nhất quán rõ ràng; không thể giả định Cassandra tự duy trì “quan hệ khóa ngoại” giữa các bảng.

## 5. Primary key quyết định partition và thứ tự các hàng

Xét table chính:

~~~sql
CREATE TABLE telemetry.events_by_device_day (
    tenant_id text,
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    temperature double,
    battery_percent int,
    status text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id ASC
);
~~~

Đọc khóa chính theo hai phần:

~~~text
PRIMARY KEY (
    (tenant_id, device_id, event_day),   -- partition key ghép
    event_time,                          -- clustering column thứ nhất
    event_id                             -- clustering column thứ hai
)
~~~

- Bộ **(tenant_id, device_id, event_day)** xác định **một partition logic**.
- Trong partition đó, mỗi row được phân biệt bởi **(event_time, event_id)**.
- **event_time DESC** định hướng thứ tự sự kiện mới hơn trước.
- **event_id ASC** quyết định thứ tự giữa những hàng có cùng event_time.
- **temperature**, **battery_percent** và **status** là cột dữ liệu thông thường, không quyết định partition hoặc clustering order.

**Lưu ý cú pháp ngoặc:** Trong Cassandra:

~~~sql
PRIMARY KEY ((a, b), c)
~~~

nghĩa là partition key ghép **(a, b)**, clustering column **c**.

Trong khi:

~~~sql
PRIMARY KEY (a, b, c)
~~~

nghĩa là partition key **a**, clustering columns **b, c**.

Hai định nghĩa có cùng tập tên trường nhưng **định tuyến dữ liệu, kích thước partition và quy tắc query khác hẳn**.

## 6. Partition: nhóm các hàng theo cùng một khóa

### 6.1. Partition key được dùng để định vị dữ liệu như thế nào?

Trong Cassandra, một giá trị partition key được đưa qua **partitioner** để xác định token. Với cấu hình thường gặp là Murmur3Partitioner, các token được phân phối trên token ring và Cassandra dùng topology/replication strategy để chọn những node giữ replica tương ứng.

~~~mermaid
flowchart LR
    A["(tenantId, deviceId, eventDay)"] --> B["Mã hóa partition key"]
    B --> C["Partitioner tính token"]
    C --> D["Phân phối token trên ring"]
    D --> E["Các node chứa replica"]
    E --> F["Các row cùng partition key"]
~~~

Đây là sơ đồ khái niệm, không phải mô tả chính xác mọi bước truyền mạng của một truy vấn. Cassandra có thể tiếp nhận truy vấn qua một coordinator node; coordinator liên lạc những replica cần thiết tùy mức consistency và trạng thái cluster.

Điểm quan trọng: **mọi hàng có cùng partition key thuộc cùng partition logic**, dù các bản sao vật lý của partition đó được lưu trên nhiều node. Trường clustering **không làm các hàng cùng partition tự động trải ra các token khác nhau**.

### 6.2. Ví dụ các bản ghi vào partition nào?

Giả sử có bốn sự kiện:

| tenant_id | device_id | event_day | event_time | event_id |
| --- | --- | --- | --- | --- |
| T01 | D17 | 2026-11-14 | 08:31:20 | E003 |
| T01 | D17 | 2026-11-14 | 08:30:45 | E002 |
| T01 | D17 | 2026-11-14 | 08:30:10 | E001 |
| T01 | D18 | 2026-11-14 | 08:32:00 | E004 |

Ba hàng đầu chung partition key **(T01, D17, 2026-11-14)** nên thuộc cùng một partition. Hàng cuối có **device_id = D18** nên thuộc partition khác. Khi **event_day** chuyển sang ngày 15/11, thiết bị D17 cũng bắt đầu một partition mới.

Không nên hiểu “partition” là dữ liệu của cả keyspace, của một ngày trong tất cả thiết bị hoặc của một row riêng. Partition là **tất cả các hàng có cùng giá trị partition key** theo đúng định nghĩa table.

### 6.3. Partition key ghép không đồng nghĩa hỗ trợ tìm bằng từng thành phần

Với partition key ghép **(tenant_id, device_id, event_day)**, truy vấn Q1 thường cần biết **đầy đủ các thành phần này**:

~~~sql
SELECT event_time, event_id, temperature, status
FROM telemetry.events_by_device_day
WHERE tenant_id = 'T01'
  AND device_id = 'D17'
  AND event_day = '2026-11-14'
LIMIT 100;
~~~

Không thể mặc định bỏ **device_id** và **event_day** rồi yêu cầu Cassandra tìm nhanh “mọi sự kiện của T01”. Dữ liệu của tenant T01 được chia thành nhiều partition theo cả thiết bị và ngày. Nếu đây là truy vấn thường xuyên, nên thiết kế đường truy cập phù hợp thay vì quét hàng loạt partition một cách tùy ý.

**Phân biệt:** Quy tắc “tiền tố trái nhất của compound index” thường gặp trong một số cơ sở dữ liệu có chỉ mục nhiều trường không thể áp nguyên xi cho **partition key ghép được băm** của Cassandra.

## 7. Các hàng liên quan trong partition: clustering columns

Nếu partition key xác định nhóm bản ghi, thì **clustering columns** xác định thứ tự và danh tính từng hàng **bên trong nhóm đó**.

Với partition **(T01, D17, 2026-11-14)**:

~~~text
Partition key:
  tenant_id = T01
  device_id = D17
  event_day = 2026-11-14

Clustering columns: event_time DESC, event_id ASC

  (2026-11-14 08:31:20, E003) -> 26.5 °C, OK
  (2026-11-14 08:30:45, E002) -> 26.3 °C, OK
  (2026-11-14 08:30:10, E001) -> 28.7 °C, WARN
~~~

Những hàng này “liên quan” vì chúng dùng chung partition key. Điều đó giúp ứng dụng có thể đọc một nhóm hữu ích theo thứ tự, nhưng **không đồng nghĩa tồn tại ràng buộc FOREIGN KEY** như giữa các bảng trong cơ sở dữ liệu quan hệ.

### 7.1. Thứ tự clustering có ích cho truy vấn khoảng

Muốn lấy sự kiện từ 08:00 đến trước 09:00:

~~~sql
SELECT event_time, event_id, temperature, status
FROM telemetry.events_by_device_day
WHERE tenant_id = 'T01'
  AND device_id = 'D17'
  AND event_day = '2026-11-14'
  AND event_time >= '2026-11-14T08:00:00Z'
  AND event_time <  '2026-11-14T09:00:00Z'
LIMIT 100;
~~~

Vì đã xác định **đầy đủ partition key**, Cassandra có thể giới hạn việc đọc vào partition liên quan; điều kiện khoảng trên **clustering column đầu** giúp giới hạn các hàng trong partition theo thời gian.

Với thứ tự **DESC**, truy vấn theo partition có thể trả những sự kiện mới hơn trước theo clustering order khai báo. Tính hiệu quả của khoảng và thứ tự vẫn phụ thuộc số hàng, loại tombstone, trạng thái lưu trữ và kích thước thực tế.

### 7.2. Clustering key bảo đảm định danh row trong partition

Giả sử hai sự kiện đến vào cùng một millisecond. Nếu chỉ có **event_time** làm clustering key, thao tác ghi cùng partition và cùng event_time sẽ nhắm tới cùng một logical row. Tùy nội dung cập nhật và timestamp ghi, một sự kiện có thể ghi đè dữ liệu của sự kiện kia.

Thêm **event_id** vào clustering key giúp phân biệt:

~~~text
(08:30:10.000, E001)
(08:30:10.000, E002)
~~~

Vì vậy, khi thiết kế dữ liệu sự kiện, phải xác định **đơn vị nào được xem là một hàng duy nhất**. Cassandra cho phép upsert; nếu ghi lại cùng toàn bộ primary key, đó là cập nhật row logic hiện có, không mặc định tạo ra row mới.

### 7.3. Clustering columns không thể thay partition key

Nếu một partition chứa 10 triệu hàng, việc thêm **event_time** làm clustering column giúp tìm một đoạn hàng trong partition; nó không chia partition đó thành 10 triệu partition để phân phối tải. Muốn chia dữ liệu sang các partition khác, phải thay **partition key** (ví dụ đưa bucket ngày/tháng vào khóa).

## 8. “Cột rộng” nghĩa là gì?

Tên **wide-column** dễ khiến người học nghĩ đến một hàng có hàng triệu thuộc tính tên khác nhau. Trong các hệ cột rộng cổ điển, cấu trúc có thể được mô tả bằng row key, column family, column qualifier và nhiều cell có timestamp/version. Trong Cassandra CQL, mô hình biểu đạt phổ biến là **một partition chứa nhiều hàng được sắp theo clustering columns**.

Ví dụ, một đơn hàng có 100 dòng hàng có thể được mô hình hóa thành 100 row cùng một partition key **order_id**. Dữ liệu “rộng” chủ yếu nằm ở **tập hàng/cell trong một nhóm khóa**, không nhất thiết là một schema table có 100 cột khai báo.

Các lưu ý:

- Cassandra CQL table có schema cột rõ ràng; nó không mặc định cho mọi row tùy ý đặt tên hàng triệu cột mới.
- HBase/Bigtable có cách nhìn column family và qualifier khác, nên không nên chuyển nguyên cú pháp Cassandra sang đó.
- “Wide row/partition” không có nghĩa “cứ thêm càng nhiều hàng vào một partition thì càng tốt”. Partition quá lớn có thể gây vấn đề đọc, compact, repair và hotspot.

## 9. Ví dụ thứ hai: các dòng hàng thuộc cùng một đơn

Ứng dụng thương mại cần lấy toàn bộ dòng hàng của một đơn khi biết **tenant_id** và **order_id**. Đây là một nhóm dữ liệu có ranh giới truy cập tương đối rõ.

Một table Cassandra có thể là:

~~~sql
CREATE TABLE commerce.order_items_by_order (
    tenant_id text,
    order_id text,
    line_no int,
    product_id text,
    product_name_at_purchase text,
    quantity int,
    unit_price decimal,
    PRIMARY KEY ((tenant_id, order_id), line_no)
) WITH CLUSTERING ORDER BY (line_no ASC);
~~~

Giả sử đã có keyspace \`commerce\` được cấu hình phù hợp. Khi lưu:

| Partition key | Clustering key | Dữ liệu |
| --- | --- | --- |
| (T01, O9001) | line_no = 1 | P10, 2 chiếc |
| (T01, O9001) | line_no = 2 | P20, 1 chiếc |
| (T01, O9001) | line_no = 3 | P30, 5 chiếc |
| (T01, O9002) | line_no = 1 | P20, 3 chiếc |

Ba dòng đầu thuộc partition **(T01, O9001)**, dòng cuối ở partition khác. Truy vấn:

~~~sql
SELECT line_no, product_id, product_name_at_purchase,
       quantity, unit_price
FROM commerce.order_items_by_order
WHERE tenant_id = 'T01'
  AND order_id = 'O9001';
~~~

cho một luồng truy xuất phù hợp: tìm partition của đơn O9001 rồi đọc các dòng theo **line_no**.

Điều này **không tự động bảo đảm giao dịch tạo đơn, trừ tồn kho và thanh toán nhất quán**. Cassandra có đặc tính ghi và batch riêng; **BATCH trong CQL không phải một giao dịch SQL tùy ý xuyên nhiều partition**, cũng không nên coi là công cụ tăng tốc bulk insert. Với bài toán có nhiều bất biến liên quan xuyên bảng hoặc dịch vụ, cần thiết kế giao dịch và đối soát phù hợp.

### 9.1. Static column: thuộc tính chung của partition

Cassandra có **static columns** để lưu một giá trị chung cho các row trong một partition. Ví dụ:

~~~sql
CREATE TABLE commerce.order_lines_with_meta (
    tenant_id text,
    order_id text,
    line_no int,
    customer_id text static,
    product_id text,
    quantity int,
    PRIMARY KEY ((tenant_id, order_id), line_no)
);
~~~

Ở đây **customer_id** là một giá trị chung cho partition **(tenant_id, order_id)**, còn **product_id** và **quantity** gắn với từng row **line_no**.

~~~text
Partition (T01, O9001):
  static customer_id = C088
  line 1 -> product P10, quantity 2
  line 2 -> product P20, quantity 1
~~~

Static column hữu ích khi thật sự có metadata chung của partition. Không nên lạm dụng để nhét thông tin cần quản lý độc lập, có vòng đời riêng hoặc kéo theo bất biến giữa nhiều partition. Một static value cũng không biến Cassandra thành mô hình có JOIN hoặc FOREIGN KEY.

## 10. Tạo nhiều table cho nhiều cách truy vấn

Vẫn lấy dữ liệu thiết bị. Table **events_by_device_day** được tối ưu cho Q1, nhưng không trả lời tự nhiên Q3: “Mọi sự kiện mức ERROR của tenant T01 trong ngày 14/11”.

Một bảng đọc riêng có thể được thiết kế:

~~~sql
CREATE TABLE telemetry.errors_by_tenant_day (
    tenant_id text,
    event_day date,
    bucket smallint,
    event_time timestamp,
    event_id uuid,
    device_id text,
    error_code text,
    PRIMARY KEY (
        (tenant_id, event_day, bucket),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id ASC
);
~~~

Ở ví dụ này:

- Chỉ ghi những sự kiện lỗi vào bảng **errors_by_tenant_day**.
- **bucket** chia lưu lượng theo một quy tắc ổn định, chẳng hạn hash của device_id chia cho số bucket đã định.
- Khi truy vấn toàn bộ sự kiện lỗi trong ngày, ứng dụng phải đọc **các bucket cần thiết** rồi gộp/sắp thứ tự ở tầng đọc.

Nếu lượng sự kiện lỗi nhỏ, một partition theo **(tenant_id, event_day)** có thể đủ; không cần bucket trước khi quan sát nguy cơ partition lớn hoặc nóng. Bucket là cách **trao đổi chi phí fan-out đọc để phân tán ghi**, không phải tối ưu miễn phí.

Các đường đọc nên được mô tả rõ:

~~~mermaid
flowchart TD
    A["Sự kiện từ thiết bị"] --> B["Xử lý và xác thực"]
    B --> C[("events_by_device_day")]
    B -->|"Nếu là lỗi"| D[("errors_by_tenant_day")]
    E["API lịch sử thiết bị"] --> C
    F["API danh sách lỗi tenant"] --> D
~~~

Sơ đồ chỉ diễn tả đường dữ liệu logic. Nếu hai bảng được ghi bằng các thao tác riêng, phải xử lý tình huống một bảng ghi thành công nhưng bảng kia thất bại, retry trùng, dữ liệu đến muộn và tính đúng đắn của bản chiếu. Có thể dùng event log/outbox hoặc pipeline đồng bộ có idempotency, tùy yêu cầu hệ thống.

## 11. Truy vấn nào phù hợp với mô hình partition + clustering?

Giả sử table:

~~~text
PRIMARY KEY (
  (tenant_id, device_id, event_day),
  event_time,
  event_id
)
~~~

Các mẫu truy cập:

| Truy vấn | Có phù hợp với khóa này? | Lý do |
| --- | --- | --- |
| Sự kiện của T01/D17/ngày 14, mới nhất trước | **Phù hợp** | Biết đủ partition key, có clustering order |
| Sự kiện của T01/D17/ngày 14 trong một giờ | **Phù hợp** | Khoảng trên event_time đầu tiên |
| Một sự kiện có đủ partition key + time + id | **Phù hợp** | Định danh đầy đủ row |
| Sự kiện của T01/D17 trong 30 ngày | **Phải truy vấn nhiều partition** | event_day nằm trong partition key |
| Mọi sự kiện của T01 trong một ngày | **Không có đường truy cập trực tiếp đơn giản** | Thiếu device_id của partition key |
| Mọi sự kiện có status = ERROR | **Không phù hợp trực tiếp** | status không thuộc khóa truy cập |
| Sự kiện theo event_id mà không biết thiết bị/ngày | **Không phù hợp trực tiếp** | Thiếu partition key và clustering prefix |

Trong Cassandra, truy vấn CQL trên primary key phải tuân các quy tắc của partition/clustering. Không nên mặc định có JOIN tùy ý, \`GROUP BY\` linh hoạt như một hệ phân tích, hoặc tìm hiệu quả bằng mọi thuộc tính.

Một số phiên bản và bản phân phối Cassandra có secondary indexes hoặc **Storage-Attached Index (SAI)**. Chúng có thể mở rộng tập truy vấn hữu ích, nhưng việc chọn chỉ mục cần dựa trên kích thước dữ liệu, mức chọn lọc, phân bố partition, giới hạn bản triển khai và kế hoạch truy vấn. Chỉ mục phụ không làm mọi truy vấn tùy ý trở nên rẻ.

**Không nên xem \`ALLOW FILTERING\` như cách chữa một khóa sai.** Một truy vấn có thể được cho phép chạy nhưng phải đọc hoặc lọc nhiều dữ liệu, dễ có độ trễ khó dự đoán khi tăng tải.

## 12. Kích thước partition: vì sao có lúc phải chia theo ngày, giờ hoặc bucket?

Lựa chọn **partition key** là điểm cân bằng giữa:

1. **Đọc ít partition** cho mỗi truy vấn.
2. **Không tạo partition quá lớn** khi dữ liệu tích lũy.
3. **Không dồn tải vào một partition nóng**.
4. **Duy trì phân phối dữ liệu đều** theo toàn cluster.

### 12.1. Sai lầm: mọi sự kiện của một thiết bị mãi mãi trong một partition

Ví dụ:

~~~text
partition key = (tenant_id, device_id)
clustering    = (event_time DESC, event_id)
~~~

Mô hình này giúp lấy mọi dữ liệu lịch sử của thiết bị mà không phải biết ngày. Tuy nhiên, thiết bị ghi nhiều năm sẽ khiến partition tăng liên tục. Các thao tác đọc, compaction, repair hoặc quét nhiều tombstone có thể trở nên tốn kém.

Thêm **event_day** vào partition key:

~~~text
partition key = (tenant_id, device_id, event_day)
~~~

giới hạn dữ liệu của mỗi partition vào một ngày thiết bị. Đổi lại, truy vấn nhiều ngày cần đọc nhiều partition.

### 12.2. Ước lượng số row và byte theo dữ liệu thực

Nếu thiết bị gửi khoảng một sự kiện mỗi giây:

~~~text
1 event/giây × 60 × 60 × 24 = 86.400 event/ngày/thiết bị
~~~

Nếu mỗi row chiếm một lượng byte nhất định sau encoding và overhead lưu trữ, một partition theo ngày có thể vẫn rất lớn. Không có một ngưỡng kích thước partition “an toàn tuyệt đối” cho mọi hệ, phần cứng và workload. Cần đo kích thước partition thực tế, số row, độ rộng row, tần suất ghi/xóa và p95/p99 của truy vấn.

Có thể chọn partition theo **giờ** hoặc bucket:

~~~text
(tenant_id, device_id, event_day, hour_bucket)
~~~

Khi đó mỗi partition có ít row hơn, nhưng API lấy dữ liệu cả ngày phải ghép tối đa nhiều partition giờ. Việc chọn ngày/giờ/tháng phải dựa trên lượng sự kiện, cửa sổ query và chi phí fan-out chấp nhận được.

### 12.3. Partition nóng khác partition lớn

**Partition lớn**: tích lũy quá nhiều dữ liệu trong một khóa, kể cả khi hiện tại ít truy cập.

**Partition nóng**: một khóa được đọc/ghi với tốc độ cao hơn mức tài nguyên xử lý phù hợp, ngay cả khi số row chưa nhiều.

Ví dụ một thiết bị gateway ghi hàng chục nghìn sự kiện mỗi giây vào partition của một ngày có thể là partition nóng. Chia theo ngày không giải quyết tải ghi dồn trong vài phút. Cần cân nhắc bucket bổ sung, tách thiết bị con hoặc partition theo nguồn sự kiện, đồng thời tính cách truy vấn và tổng hợp các bucket.

Đừng đặt **ngày hiện tại** làm partition key duy nhất cho mọi thiết bị; nó có thể khiến mọi ghi trong ngày tập trung về một partition logic.

## 13. Phân vùng logic khác replication vật lý

Có hai khái niệm dễ bị gộp:

- **Partition key** quyết định nhóm các hàng và token tương ứng.
- **Replication strategy** quyết định những node/datacenter nào lưu replica cho token range đó.

Giả sử một partition của D17 có ba replica theo cấu hình:

~~~text
Logical partition:
  (T01, D17, 2026-11-14)

Replica placements (minh họa):
  Node A -> bản sao 1
  Node B -> bản sao 2
  Node C -> bản sao 3
~~~

Thêm replica **không chia nhỏ** logical partition D17 thành ba partition nhỏ; replica giữ những bản sao của cùng dữ liệu logic. Nếu partition đang quá nóng, thêm replica có thể ảnh hưởng cách phân phối một số truy vấn đọc nhưng không phải giải pháp mặc định cho mô hình khóa hoặc tải ghi nóng.

### 13.1. Consistency level liên quan đến đọc/ghi thế nào?

Trong Cassandra, consistency level như **ONE**, **QUORUM**, **LOCAL_QUORUM** điều chỉnh số replica cần tham gia/xác nhận cho thao tác theo chính sách cụ thể. Khi thiết kế, cần cân nhắc:

- Mức sẵn sàng khi một hoặc nhiều replica lỗi.
- Mức nhất quán mong muốn và khả năng đọc giá trị mới.
- Latency, số vùng và độ trễ mạng.
- Replication factor và phạm vi datacenter.

Một công thức quorum thường được dùng để suy luận tính giao nhau là **R + W > RF** với cùng tập replica và giả định phù hợp. Tuy nhiên, chỉ áp dụng công thức đó không thay thế hiểu biết về topology, coordinator, repair, failure, timestamp và semantics thực tế của sản phẩm.

**Hợp đồng ghi bền** còn phụ thuộc đường ghi vào commit log, memtable, replica và chế độ durable writes. RF hoặc consistency level không tự động thay cho backup và diễn tập phục hồi dữ liệu bị xóa nhầm.

## 14. Điều gì xảy ra khi ghi một hàng mới?

Giả sử ứng dụng thêm một sự kiện:

~~~sql
INSERT INTO telemetry.events_by_device_day (
    tenant_id, device_id, event_day,
    event_time, event_id, temperature,
    battery_percent, status
) VALUES (
    'T01', 'D17', '2026-11-14',
    '2026-11-14T08:31:20Z',
    11111111-1111-4111-8111-111111111111,
    26.5, 83, 'OK'
);
~~~

Ở mức khái niệm:

1. Coordinator nhận lệnh ghi và xác định token từ **partition key**.
2. Hệ định vị những replica có trách nhiệm với token đó.
3. Replica áp dụng đường ghi của engine, thông thường liên quan **commit log** và **memtable**, theo cấu hình ghi thực tế.
4. Sau đó memtable được flush thành **SSTable** trên đĩa; những lần cập nhật/xóa có thể nằm ở nhiều SSTable.
5. **Compaction** hợp nhất dữ liệu lưu trữ theo chiến lược đã cấu hình. Khi đọc, engine tổng hợp trạng thái logic còn hiệu lực từ các phần liên quan.

Vì Cassandra tổ chức lưu trữ kiểu LSM, không nên suy rằng một \`UPDATE\` ngay lập tức tìm và thay đổi một “row vật lý duy nhất” trong một file. **Upsert**, timestamp của cell, TTL và tombstone tham gia vào cách xác định trạng thái được thấy khi đọc.

Đây là mô tả khái niệm. Chi tiết thứ tự gửi yêu cầu, write ACK, fsync và các bảo đảm lỗi phải được kiểm tra trong đúng phiên bản/cấu hình triển khai.

## 15. Xóa, TTL và tombstone trong một partition nhiều hàng

Dữ liệu sự kiện thường có chính sách giữ 7, 30 hoặc 90 ngày. Cassandra có TTL ở mức ghi dữ liệu:

~~~sql
INSERT INTO telemetry.events_by_device_day (
    tenant_id, device_id, event_day,
    event_time, event_id, temperature, status
) VALUES (
    'T01', 'D17', '2026-11-14',
    '2026-11-14T08:31:20Z',
    11111111-1111-4111-8111-111111111111,
    26.5, 'OK'
) USING TTL 2592000;
~~~

\`2592000\` giây là 30 ngày. Dữ liệu hết hạn không nhất thiết biến mất khỏi mọi SSTable ngay lập tức. Cassandra có thể sử dụng **tombstone** để biểu diễn việc dữ liệu đã bị xóa/hết hạn, sau đó compaction mới có cơ hội thu dọn theo điều kiện an toàn.

Các tác động:

- Truy vấn qua nhiều row đã hết hạn có thể tốn chi phí đọc và làm tăng độ trễ.
- Xóa hàng loạt hoặc cập nhật nhiều cột không hợp lý có thể tạo nhiều tombstone.
- Chiến lược compaction, thời gian giữ dữ liệu, thao tác repair và cách xử lý replica lỗi có liên hệ với việc thu dọn tombstone an toàn.
- Nếu dữ liệu tách thành partition theo ngày, việc hết hạn toàn bộ khoảng có thể thuận lợi hơn cho chiến lược lưu trữ theo thời gian, tùy engine và compaction strategy.

Với dữ liệu thời gian, có thể cân nhắc **TimeWindowCompactionStrategy (TWCS)** khi workload và chính sách TTL phù hợp. Tuy nhiên, TWCS cũng cần cấu hình cửa sổ, TTL, kiểu ghi và xử lý dữ liệu đến muộn đúng; không phải mọi bảng có timestamp đều tự động phù hợp.

## 16. Một partition có nhiều hàng không phải một giao dịch nhiều hàng

Các hàng cùng partition gần nhau về cách định tuyến và sắp xếp, nhưng **không có nghĩa mọi thao tác nhiều hàng tự động đạt toàn bộ ngữ nghĩa ACID như transaction SQL**.

Ví dụ một đơn hàng có ba dòng:

~~~text
Partition (T01, O9001):
  line 1 -> P10
  line 2 -> P20
  line 3 -> P30
~~~

Nếu ứng dụng cần bảo đảm “cả ba dòng phải xuất hiện cùng nhau hoặc không dòng nào xuất hiện”, phải nghiên cứu chính xác hỗ trợ atomic batch, isolation và ranh giới của Cassandra trong phiên bản sử dụng. Một **logged batch** có cơ chế bảo đảm đặc thù, nhưng không cung cấp toàn bộ transaction semantics của RDBMS cho các truy vấn tùy ý hoặc thao tác liên bảng/liên dịch vụ.

Khi dữ liệu có invariant xuyên partition như chuyển tiền hay trừ tồn kho, việc xếp các dòng “có liên quan” gần nhau không đủ để bảo vệ các invariant đó. Có thể cần conditional write/LWT trong phạm vi hỗ trợ, mô hình state machine, xử lý idempotent, outbox hoặc một nguồn dữ liệu giao dịch khác.

### 16.1. Phân biệt gom theo truy vấn và gom theo tính đúng đắn

Hai dòng đơn hàng cùng partition vì **API thường đọc chúng cùng nhau** là một quyết định mô hình hóa truy vấn. Việc tính tổng thanh toán và xác nhận tồn kho lại là yêu cầu **nhất quán nghiệp vụ**, cần một cơ chế khác được chỉ định rõ.

Không nên tự suy luận “cùng partition = cùng transaction”.

## 17. Tránh coi partition là thư mục và clustering là JOIN

Một cách ví von có giới hạn:

~~~text
Partition key   ~ Chọn nhóm dữ liệu
Clustering key  ~ Tìm và sắp hàng trong nhóm
Row             ~ Một bản ghi logic trong nhóm
~~~

Tuy nhiên:

- Partition không phải thư mục mà ứng dụng có thể liệt kê dễ dàng bằng mọi tiền tố.
- Clustering key không phải khóa ngoại tham chiếu sang table khác.
- Keyspace không tự tương đương một server hay tenant vật lý độc lập.
- Table không mặc định tương đương “thực thể chuẩn hóa” của SQL.
- Một partition không nhất thiết nằm trong một file hoặc trên đúng một node.

Đặt những ví von này trong giới hạn giúp tránh lẫn **mô hình logic**, **đường truy cập** và **cơ chế lưu vật lý**.

## 18. Quy trình xây table theo truy vấn: ví dụ hoàn chỉnh

Giả sử ứng dụng trò chuyện cần:

1. Lấy 50 tin nhắn mới nhất của một phòng.
2. Cuộn xem tin nhắn cũ theo thời gian.
3. Tìm một tin nhắn theo ID khi đã biết phòng chứa nó.
4. Giữ tin nhắn trong 12 tháng.

### Bước 1: Chọn nhóm đọc thường xuyên

Vì người dùng chủ yếu xem một phòng, **room_id** nên góp mặt trong partition key. Nhưng một phòng có thể tồn tại nhiều năm, nên không để mọi tin nhắn của phòng trong một partition vô hạn.

### Bước 2: Chọn bucket thời gian

Chọn **room_id + month_bucket** làm partition key khởi đầu. Nếu một số phòng có lưu lượng cực lớn, có thể xem xét bucket nhỏ hơn hoặc phương án chia tải khác.

### Bước 3: Chọn thứ tự hàng

Trong một tháng của phòng, sắp theo **sent_at DESC** rồi **message_id** để phân biệt tin nhắn cùng thời điểm:

~~~sql
CREATE TABLE chat.messages_by_room_month (
    room_id text,
    month_bucket text,
    sent_at timestamp,
    message_id uuid,
    sender_id text,
    body text,
    PRIMARY KEY (
        (room_id, month_bucket),
        sent_at,
        message_id
    )
) WITH CLUSTERING ORDER BY (
    sent_at DESC,
    message_id ASC
);
~~~

Bảng ví dụ giả định keyspace \`chat\` đã được cấu hình. Giá trị tháng phải theo dạng nhất quán, ví dụ \`2026-11\`.

### Bước 4: Viết truy vấn chính

~~~sql
SELECT sent_at, message_id, sender_id, body
FROM chat.messages_by_room_month
WHERE room_id = 'R100'
  AND month_bucket = '2026-11'
LIMIT 50;
~~~

Nếu tháng này có ít hơn 50 tin, ứng dụng phải truy vấn tháng trước rồi gộp trang kết quả. Cassandra không tự thực hiện một truy vấn phạm vi tháng xuyên nhiều partition chỉ vì các giá trị **month_bucket** có thứ tự từ điển.

### Bước 5: Thiết kế phân trang

Với dữ liệu trong một partition, có thể dùng paging của driver với cơ chế trạng thái phân trang do driver/hệ quản trị cung cấp. Khi chuyển từ tháng này sang tháng trước, tầng ứng dụng cần quản lý bucket và cursor phù hợp.

Không nên mặc định phân trang bằng \`OFFSET\` lớn như một số cách dùng SQL. Cần quy tắc chống trùng hoặc thiếu tin khi dữ liệu mới được thêm trong lúc người dùng cuộn.

### Bước 6: Giải quyết truy vấn theo ID

Nếu biết đủ room và month, truy vấn theo full primary key có thể rất trực tiếp. Nếu chỉ biết **message_id** mà không biết month, table chính không tự hỗ trợ. Có thể lưu một bảng lookup riêng:

~~~text
message_id -> room_id, month_bucket, sent_at
~~~

Đường lookup phải được cập nhật đáng tin cậy, có chiến lược xử lý ghi trùng/thiếu và xóa theo retention.

### Bước 7: Đánh giá tải và vòng đời

Đo số tin trong tháng của phòng lớn nhất, kích thước tin, tỷ lệ xóa/sửa, TTL/tombstone, số partition truy cập khi cuộn và thời gian phục hồi. Nếu độ lệch giữa các phòng cao, có thể phải thay bucket trước khi đưa vào sản xuất.

Quy trình này cho thấy cấu trúc table là hệ quả của **truy vấn chính, tính duy nhất của row và giới hạn partition**, chứ không chỉ của danh sách thuộc tính một tin nhắn.

## 19. So sánh cùng dữ liệu trong SQL và wide-column

Để thấy rõ khác biệt, hãy xét lịch sử sự kiện thiết bị:

| Khía cạnh | RDBMS điển hình | Cassandra theo truy vấn |
| --- | --- | --- |
| Thiết kế ban đầu | Thực thể, quan hệ, ràng buộc, truy vấn | Truy vấn chủ đạo, partition key, clustering key |
| Định danh | Primary key/unique constraints | Primary key gồm partition + clustering |
| Lọc theo nhiều thuộc tính | Chỉ mục, JOIN, tối ưu SQL | Ưu tiên access pattern đã thiết kế; index phụ có giới hạn |
| Nhóm dữ liệu | Bảng và index; partitioning nếu cần | Các hàng có cùng partition key |
| Thứ tự lưu/đọc | Chỉ mục/phép sort theo truy vấn | Clustering order trong partition |
| Phân phối dữ liệu | Tùy cấu hình và sản phẩm | Token/partitioner/replication là phần cốt lõi |
| Thay đổi truy vấn lớn | Có thể thêm index/query | Có thể phải thêm table/bản chiếu |
| Quan hệ giữa bảng | JOIN, FOREIGN KEY, transaction | Thường phi chuẩn hóa và phối hợp cập nhật |

Đây là so sánh định hướng. Một RDBMS hiện đại cũng có partitioning, sharding và JSON; một NoSQL hiện đại có thể hỗ trợ chỉ mục/giao dịch ở mức khác nhau. Không nên chọn theo nhãn công nghệ mà bỏ qua lượng dữ liệu, pattern truy cập và khả năng vận hành.

## 20. Các lỗi mô hình hóa thường gặp

### 20.1. Dùng \`tenant_id\` làm partition key duy nhất

Nếu tenant có hàng triệu thiết bị và tần suất ghi lớn, mọi dữ liệu dồn vào một partition logic. Cần chia theo thiết bị/thời gian hoặc tiêu chí truy cập phù hợp, đồng thời cân nhắc nhu cầu query toàn tenant.

### 20.2. Tưởng clustering column giúp phân phối dữ liệu giữa node

Clustering column chỉ sắp các hàng **trong partition**. Một partition đang nóng vẫn nóng dù có hàng triệu giá trị clustering key.

### 20.3. Nhét mọi quan hệ vào một table quá rộng

Một table trộn hồ sơ thiết bị, lịch sử sự kiện, cấu hình và cảnh báo có vòng đời khác nhau có thể phức tạp trong cập nhật/retention. Chọn table theo truy vấn và nhóm dữ liệu có vòng đời phù hợp; không nhất thiết mọi thứ liên quan đến một thiết bị phải ở chung một partition.

### 20.4. Thiết kế theo dữ liệu trung bình

Thiết bị bình thường có 100 sự kiện/ngày, nhưng thiết bị gateway có hàng triệu sự kiện/ngày. Phân phối lệch làm partition nóng/lớn. Cần đo với nhóm lớn nhất, tần suất cao nhất và thời gian giữ dữ liệu thực tế.

### 20.5. Dùng \`ALLOW FILTERING\` làm mặc định

Truy vấn theo thuộc tính không nằm trong khóa có thể thành scan/filtration rộng. Khi là đường đọc chính, cần thiết kế thêm table/index phù hợp thay vì phụ thuộc vào lọc sau đọc.

### 20.6. Cho rằng nhiều row liên quan có transaction tự động

Cùng partition giúp dữ liệu cùng lối truy cập, nhưng không thay thế việc kiểm soát đồng thời, tính nguyên tử và bất biến nghiệp vụ. Cần xác định đầy đủ các yêu cầu consistency.

### 20.7. Không có kế hoạch cho TTL/tombstone và dữ liệu đến muộn

Dữ liệu tồn đọng hoặc xóa theo TTL không biến mất vật lý tức thời. Nếu một sự kiện đến muộn sau nhiều ngày, nó có thể nằm ngoài cửa sổ compaction/retention đã tối ưu. Cần chính sách thời gian, compaction, repair và kiểm thử dữ liệu thực.

### 20.8. Nhầm replication factor với số partition

RF = 3 nghĩa là mục tiêu có ba replica cho một partition trong phạm vi được cấu hình. Nó không chia partition thành ba đoạn nhỏ hoặc làm truy vấn xuyên partition trở thành truy vấn một partition.

## 21. Bài tập thực hành

### Bài 1: Xác định các hàng thuộc cùng partition

Cho:

~~~sql
PRIMARY KEY ((tenant_id, account_id, year_month), created_at, entry_id)
~~~

Các bản ghi:

~~~text
(T01, A1, 2026-11, 09:00, E1)
(T01, A1, 2026-11, 09:05, E2)
(T01, A1, 2026-12, 08:00, E3)
(T01, A2, 2026-11, 09:10, E4)
~~~

**Câu hỏi:** Có bao nhiêu partition? Bản ghi nào ở cùng partition?

**Gợi ý:** Có ba partition: hai bản ghi đầu cùng **(T01, A1, 2026-11)**; bản ghi thứ ba và thứ tư thuộc hai partition khác nhau. **created_at** và **entry_id** định danh/sắp hàng trong partition, không tạo partition mới.

### Bài 2: Chọn partition key cho lịch sử cảm biến

Truy vấn thường xuyên: lấy dữ liệu theo một thiết bị trong một ngày. Hệ có 10.000 thiết bị, trong đó một số gateway phát nhiều sự kiện mỗi giây.

Ba phương án:

~~~text
A. partition key = (day)
B. partition key = (device_id)
C. partition key = (device_id, day)
~~~

**Gợi ý:** **C** thường là điểm khởi đầu hợp lý với truy vấn đã nêu vì vừa nhóm theo thiết bị vừa giới hạn lịch sử theo ngày. Tuy nhiên, khi gateway có lưu lượng quá cao, ngay cả partition ngày có thể quá nóng/lớn; cần đo và cân nhắc bucket nhỏ hơn.

### Bài 3: Thay đổi truy vấn mới

Table đã tối ưu cho:

~~~text
(tenant_id, device_id, day) -> event_time DESC
~~~

Yêu cầu mới là “lấy mọi sự kiện mức ERROR của tenant trong ngày, mới nhất trước”.

**Gợi ý:** Không thể chỉ truy vấn \`status = 'ERROR'\` và mong tận dụng hiệu quả table hiện tại, vì thiếu device_id trong partition key và status không phải khóa. Cần cân nhắc bản chiếu/table **errors_by_tenant_day**, với bucket nếu lưu lượng đủ lớn; quy định rõ cách đồng bộ.

### Bài 4: Đánh giá một bảng đơn hàng

Table:

~~~sql
PRIMARY KEY ((tenant_id, order_id), line_no)
~~~

**Câu hỏi:** Table phù hợp để lấy gì? Có thể dùng trực tiếp để lấy mọi đơn của tenant theo ngày hay không?

**Gợi ý:** Table phù hợp để lấy **các dòng của một đơn xác định**, theo line_no. Muốn liệt kê đơn của tenant theo ngày cần mô hình đọc/index khác, chẳng hạn **orders_by_tenant_day** với partition và clustering phù hợp.

### Bài 5: Bucket thời gian và phân trang

Ứng dụng lưu tin nhắn theo partition **(room_id, month_bucket)**, clustering **sent_at DESC**. Người dùng cuộn qua ngày cuối tháng 11 sang tháng 10.

**Gợi ý:** Hết dữ liệu của partition tháng 11 thì API phải tiếp tục truy vấn partition tháng 10, giữ cursor phù hợp và ghép kết quả. Không có một phép range scan tự động xuyên partition chỉ vì month có thể so sánh được.

## 22. Kết luận

Trong mô hình cột rộng kiểu Cassandra, **keyspace** tổ chức namespace và replication, **table** xác định schema cùng đường truy cập, **partition key** nhóm các hàng để hệ phân phối và tìm dữ liệu, còn **clustering columns** phân biệt và sắp xếp các hàng liên quan bên trong một partition. Tập hàng cùng partition có thể được đọc rất hiệu quả khi truy vấn khớp khóa, nhưng partition quá lớn hoặc quá nóng vẫn là rủi ro vận hành.

Thiết kế đúng bắt đầu bằng **truy vấn phổ biến**, tiếp đến chọn ranh giới partition, thứ tự clustering, tính duy nhất của row, chính sách TTL/compaction và các đường đọc bổ sung. Đọc nhiều dạng dữ liệu có thể cần nhiều table phục vụ truy vấn; khả năng phân phối và nhân bản cũng phải được đánh giá riêng với tính nguyên tử và toàn vẹn nghiệp vụ.
