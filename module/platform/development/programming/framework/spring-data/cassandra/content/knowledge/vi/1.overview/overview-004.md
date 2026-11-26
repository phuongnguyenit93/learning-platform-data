# Các thuật ngữ nền tảng: keyspace, partition, clustering và replica

Khi truy cập Apache Cassandra bằng **Spring Data Cassandra**, một lớp entity và một repository chỉ là cách ứng dụng Java giao tiếp với dữ liệu. Muốn thiết kế đúng bảng, viết truy vấn CQL hiệu quả, sử dụng `CassandraTemplate` và kiểm soát paging hoặc tính nhất quán, trước tiên cần phân biệt bốn khái niệm: **keyspace**, **partition**, **clustering** và **replica**.

Khác với cách thường bắt đầu từ các bảng chuẩn hóa rồi ghép chúng bằng JOIN trong cơ sở dữ liệu quan hệ, thiết kế Cassandra thường bắt đầu từ **truy vấn ứng dụng cần chạy**. Khóa phân vùng quyết định dữ liệu được phân phối ở đâu; khóa clustering quyết định cách sắp xếp các hàng trong một phân vùng; replica quyết định nơi lưu các bản sao và ảnh hưởng đến độ sẵn sàng, tính nhất quán.

## 1. Bức tranh tổng thể

| Thuật ngữ | Phạm vi | Vai trò chính | Cần nhớ |
| --- | --- | --- | --- |
| **Keyspace** | Nhóm các bảng trong Cassandra | Đặt tên không gian dữ liệu và cấu hình replication, bao gồm số bản sao theo datacenter | Gần với database/schema về mặt tổ chức, nhưng còn mang cấu hình replication |
| **Partition** | Một nhóm hàng **trong một bảng** có cùng partition key | Đơn vị cơ bản để phân phối dữ liệu qua các node | Nhiều hàng có thể thuộc cùng một partition |
| **Clustering column** | Các cột thuộc phần còn lại của primary key, sau partition key | Xác định thứ tự và vị trí logic của hàng bên trong partition | Không quyết định partition được đặt ở node nào |
| **Replica** | Bản sao dữ liệu của một partition tại một node | Phục vụ đọc, ghi và duy trì tính sẵn sàng khi node gặp sự cố | RF = 3 nghĩa là mục tiêu có 3 bản sao của mỗi partition trong datacenter được cấu hình |

Một sơ đồ khái niệm:

~~~text
Keyspace: commerce_ks
└── Table: orders_by_customer_day
    ├── Partition: (customer=A, day=2026-11-25)
    │   ├── Row: 10:30, order_3
    │   ├── Row: 09:15, order_2
    │   └── Row: 08:00, order_1
    └── Partition: (customer=B, day=2026-11-25)
        └── Row: 11:00, order_4

Ví dụ RF=3 trong một datacenter:
Partition (A, 2026-11-25)
    ├── bản sao tại Node 1
    ├── bản sao tại Node 2
    └── bản sao tại Node 3
~~~

Trong ví dụ trên, **partition** là nhóm các hàng của khách hàng A trong một ngày; **replica** là một bản sao của cả nhóm dữ liệu đó trên một node. Một node thực tế lưu rất nhiều partition khác nhau. Hình chỉ minh họa, vì Cassandra tự xác định vị trí replica theo token và cấu hình topology.

## 2. Keyspace: không gian tên và chính sách replication

Keyspace chứa các bảng, kiểu dữ liệu do người dùng định nghĩa và các đối tượng liên quan. Quan trọng hơn, keyspace quy định **replication strategy** và **replication factor (RF)**. Đây là những cấu hình ảnh hưởng đến cách dữ liệu được trải rộng trên cụm Cassandra.

Ví dụ tạo keyspace cho môi trường có datacenter tên `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS commerce_ks
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
~~~

- `commerce_ks`: tên keyspace dùng khi tham chiếu tới bảng, ví dụ `commerce_ks.orders_by_customer_day`.
- `NetworkTopologyStrategy`: chiến lược phân bố replica theo topology/datacenter, phù hợp với cách tổ chức cụm Cassandra thực tế.
- `'dc1': 3`: mỗi partition có mục tiêu **3 replica trong datacenter dc1**; số node và topology cần đủ để đáp ứng cấu hình.
- `durable_writes = true`: bật việc ghi commit log để tăng độ bền của ghi, không phải tùy chọn điều khiển consistency level.

Tên `dc1` là ví dụ; triển khai thực tế phải dùng đúng tên datacenter của cụm. Nếu có nhiều datacenter, cấu hình replication được khai báo riêng cho từng nơi.

**Phân biệt:** keyspace không phải một máy chủ, một partition hay một replica; keyspace là phạm vi logic quản lý các bảng và cách nhân bản dữ liệu của chúng.

## 3. Partition: nhóm dữ liệu có cùng partition key

Trong một bảng Cassandra, **partition key** là một hoặc nhiều cột nằm trong khai báo `PRIMARY KEY`. Cassandra dùng giá trị partition key để tính **token**, từ đó xác định các node chịu trách nhiệm lưu replica của partition theo cấu hình cụm. Tất cả các hàng có cùng giá trị partition key thuộc cùng một partition.

Giả sử chức năng cần hỗ trợ là: **“Lấy những đơn hàng gần nhất của một khách hàng trong một ngày, theo thời gian giảm dần.”** Ta thiết kế một bảng phục vụ chính truy vấn này:

~~~sql
CREATE TABLE commerce_ks.orders_by_customer_day (
  customer_id uuid,
  order_day date,
  created_at timestamp,
  order_id uuid,
  status text,
  amount decimal,
  PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
~~~

Đọc chính xác khai báo khóa:

~~~text
PRIMARY KEY (
  (customer_id, order_day),  <-- composite partition key
  created_at,                <-- clustering column thứ nhất
  order_id                   <-- clustering column thứ hai
)
~~~

Hai dấu ngoặc quanh `customer_id, order_day` có ý nghĩa: **cả hai cột cùng tạo thành một partition key tổng hợp**. Vì vậy:

- Cùng khách hàng, cùng ngày → cùng partition, dù có nhiều đơn hàng.
- Cùng khách hàng, khác ngày → partition khác.
- Khác khách hàng, cùng ngày → partition khác.
- Giá trị đầy đủ `(customer_id, order_day, created_at, order_id)` nhận diện một hàng; nếu ghi lại cùng khóa đầy đủ, Cassandra cập nhật dữ liệu cho hàng đó theo ngữ nghĩa ghi của Cassandra, không tạo thêm hàng thứ hai có cùng primary key.

Ví dụ, với khách hàng A và ngày 25/11/2026, có thể có ba đơn:

| customer_id | order_day | created_at (UTC) | order_id | status |
| --- | --- | --- | --- | --- |
| A | 2026-11-25 | 10:30 | order_3 | PAID |
| A | 2026-11-25 | 09:15 | order_2 | NEW |
| A | 2026-11-25 | 08:00 | order_1 | PAID |

Các ký hiệu A, `order_1`… chỉ dùng để dễ đọc; khi ghi CQL thật, cột `customer_id` và `order_id` phải nhận giá trị UUID hợp lệ.

### Chọn partition key theo truy vấn và phân bố tải

Một truy vấn hiệu quả thường cung cấp đủ giá trị partition key để Cassandra biết cần đọc partition nào. Ví dụ truy vấn đúng với thiết kế bảng:

~~~sql
SELECT order_id, created_at, status, amount
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ? AND order_day = ?
LIMIT 20;
~~~

Dấu `?` biểu diễn tham số trong prepared statement của driver. Cassandra xác định đúng partition của cặp `(customer_id, order_day)`, đọc các hàng theo thứ tự clustering đã định nghĩa và trả về tối đa 20 hàng.

Ngược lại, truy vấn chỉ theo ngày, không biết khách hàng:

~~~sql
-- Không phù hợp với partition key đã thiết kế.
SELECT *
FROM commerce_ks.orders_by_customer_day
WHERE order_day = '2026-11-25';
~~~

Truy vấn này thiếu thành phần `customer_id` của partition key, nên Cassandra không thể định tuyến theo một partition cụ thể và thường không cho thực hiện bằng CQL thông thường. Thêm `ALLOW FILTERING` không giải quyết vấn đề thiết kế: nó có thể buộc hệ thống đọc/lọc quá nhiều dữ liệu và làm độ trễ khó dự đoán.

**Lựa chọn khóa luôn có đánh đổi.** Chỉ dùng `customer_id` làm partition key có thể khiến dữ liệu của một khách hàng tăng mãi và hình thành partition rất lớn. Thêm `order_day` chia dữ liệu theo ngày, nhưng truy vấn nhiều ngày phải xử lý nhiều partition. Nếu một khách hàng tạo lượng đơn bất thường trong một ngày, cần đánh giá thêm việc chia theo khung thời gian hoặc bucket/shard và chi phí truy vấn nhiều bucket.

Không có một partition key tối ưu cho mọi truy vấn. Khi cần tra cứu theo `status`, theo cửa hàng hay theo toàn bộ hệ thống, hãy xem xét **bảng được thiết kế cho truy vấn đó**, đôi khi phải chấp nhận nhân bản dữ liệu ở cấp ứng dụng. Các chỉ mục phù hợp với phiên bản Cassandra cũng có thể là lựa chọn trong những trường hợp cụ thể, nhưng cần đánh giá đặc điểm truy vấn và chi phí thực tế.

## 4. Clustering: tổ chức các hàng bên trong partition

Sau partition key, các cột còn lại trong `PRIMARY KEY` là **clustering columns**. Với bảng ví dụ, đó là `created_at` và `order_id`.

Clustering columns có hai tác dụng:

1. Cùng partition key, tổ hợp các giá trị clustering phân biệt từng hàng.
2. Quyết định thứ tự lưu trữ logic của các hàng trong partition để đọc theo khóa hoặc theo khoảng khóa hiệu quả.

`WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC)` nghĩa là khi đọc partition, đơn gần nhất theo `created_at` đứng trước; nếu thời gian bằng nhau, `order_id` xác định thứ tự phụ. Không có **thứ tự toàn cục** giữa tất cả các partition.

Chẳng hạn, có thể đọc các đơn trong một khoảng thời gian của đúng một khách hàng/ngày:

~~~sql
SELECT order_id, created_at, status
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT 20;
~~~

Truy vấn theo clustering key được hỗ trợ trong phạm vi các quy tắc thứ tự, đẳng thức và range của CQL. Việc chọn các cột clustering theo thứ tự rất quan trọng: không thể coi chúng như các cột để lọc tùy ý, hay mong `ORDER BY status` hoạt động nếu `status` không phải clustering column.

### Partition key khác clustering key thế nào?

| Câu hỏi | Partition key | Clustering key |
| --- | --- | --- |
| Quyết định dữ liệu thuộc partition nào? | Có | Không |
| Tham gia định tuyến tới replica? | Có, thông qua token và topology | Không trực tiếp |
| Quyết định thứ tự các hàng trong partition? | Không | Có |
| Có thể có nhiều cột? | Có, gọi là composite partition key | Có, gọi là nhiều clustering columns |
| Là thành phần của primary key? | Có | Có |

**Lưu ý về cú pháp:** `PRIMARY KEY (customer_id, created_at)` có partition key đơn là `customer_id`; `PRIMARY KEY ((customer_id, order_day), created_at)` có partition key tổng hợp là cả hai cột trong cặp ngoặc trong. Dấu ngoặc ảnh hưởng trực tiếp đến phân bố dữ liệu.

## 5. Replica: các bản sao của cùng một partition

Cassandra là cơ sở dữ liệu phân tán. Sau khi xác định token của partition key, hệ thống dùng replication strategy để chọn các node giữ **replica** của partition đó. Một replica chứa dữ liệu thuộc partition, bao gồm các hàng và cột của nó; nó không phải một “hàng sao chép” trong kết quả truy vấn.

Giả sử datacenter `dc1` có đủ node và RF = 3:

~~~text
                  Datacenter dc1
                      RF = 3

       Partition P = (customer A, 2026-11-25)
                          |
              +-----------+-----------+
              |           |           |
           Node 1      Node 2      Node 3
           replica P   replica P   replica P
~~~

Nhờ có các replica, một node bị lỗi không nhất thiết làm mất khả năng phục vụ partition đó. Tuy nhiên, việc đọc/ghi có thành công khi node lỗi hay không còn phụ thuộc vào **consistency level**, số replica khả dụng và cấu hình topology.

### RF khác consistency level

- **Replication factor (RF)** là số bản sao mục tiêu được lưu theo cấu hình keyspace tại mỗi datacenter.
- **Consistency level (CL)** là yêu cầu về số phản hồi thành công từ replica khi thực hiện một thao tác đọc hoặc ghi.
- **Coordinator** là node nhận yêu cầu từ client, điều phối việc truy cập các replica phù hợp; coordinator không nhất thiết là nơi duy nhất lưu dữ liệu.

Ví dụ với RF = 3 trong `dc1`:

| Consistency level | Minh họa yêu cầu | Đánh đổi thường gặp |
| --- | --- | --- |
| `ONE` | Một replica phản hồi | Ít phản hồi cần chờ hơn; có thể gặp dữ liệu cũ khi đọc tùy tình trạng đồng bộ |
| `LOCAL_QUORUM` | Đa số replica trong datacenter cục bộ; với RF = 3 là **2** | Chờ nhiều replica hơn, đổi lại khả năng quan sát dữ liệu nhất quán tốt hơn trong các điều kiện phù hợp |
| `ALL` | Tất cả replica tương ứng phải phản hồi | Đòi hỏi mức sẵn sàng của replica cao hơn, dễ thất bại khi có node gặp sự cố |

Khi dùng read/write quorum phù hợp trong cùng datacenter, hai tập replica thường có ít nhất một bản sao giao nhau. Tuy nhiên Cassandra vẫn có ngữ nghĩa xử lý ghi đồng thời, timestamp, sửa chữa và các tình huống lỗi riêng; **không nên suy ra rằng mọi truy vấn là giao dịch tuyến tính hóa hoặc hỗ trợ ACID như một RDBMS**.

RF cao hơn thường tăng khả năng chịu lỗi nhưng cũng tăng chi phí lưu trữ, truyền dữ liệu, bảo trì và đồng bộ. Partition key lệch tải vẫn có thể tạo **hot partition** dù RF = 3: replication không tự làm biến mất điểm nóng của một khóa được truy cập quá nhiều.

## 6. Liên hệ với entity, repository và CassandraTemplate trong Spring Data Cassandra

Trong Spring Data Cassandra, khai báo entity phải phản ánh **cấu trúc primary key thật của bảng CQL**. Có thể biểu diễn khóa tổng hợp bằng `@PrimaryKeyClass`, `@PrimaryKeyColumn` và dùng nó trong entity thông qua `@PrimaryKey`.

Ví dụ Java rút gọn, lược bỏ import, constructor, accessor và `equals/hashCode` để tập trung vào ý nghĩa các annotation:

~~~java
@PrimaryKeyClass
public class OrderKey implements Serializable {

    @PrimaryKeyColumn(
        name = "customer_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "order_day", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private LocalDate orderDay;

    @PrimaryKeyColumn(
        name = "created_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private UUID orderId;
}

@Table("orders_by_customer_day")
public class OrderRow {
    @PrimaryKey
    private OrderKey key;

    private String status;
    private BigDecimal amount;
}
~~~

Ở đây:

- `PrimaryKeyType.PARTITIONED` đánh dấu các thành phần của partition key; `PrimaryKeyType.CLUSTERED` đánh dấu các clustering columns.
- `ordinal` phản ánh thứ tự cột trong primary key; `ordering` phản ánh khai báo thứ tự clustering của CQL.
- `OrderKey` là **toàn bộ khóa của một hàng**, bao gồm cả partition và clustering. Cần hiện thực các thành phần Java thường dùng cho value object (như constructor, getter/setter hoặc cơ chế ánh xạ tương đương, `equals` và `hashCode`) phù hợp với phiên bản Spring Data đang chạy.

Một repository như `CassandraRepository<OrderRow, OrderKey>` có thể truy xuất một hàng bằng **đầy đủ primary key**. Nhưng truy vấn liệt kê 20 đơn gần nhất cần được viết theo **partition key** và điều kiện giới hạn phù hợp, qua repository query method/`@Query` hoặc `CassandraTemplate`. Việc có entity/repository không khiến truy vấn thiếu partition key trở nên rẻ hoặc hợp lệ.

Khi duyệt nhiều đơn, ưu tiên **paging dựa trên trạng thái trang (paging state)** của Cassandra và các API phân trang tương ứng trong Spring Data/driver. `LIMIT 20` chỉ giới hạn kết quả của yêu cầu hiện tại; không phải cơ chế nhảy tùy ý đến offset rất lớn như một số truy vấn SQL. Trong hệ thống phân tán đang tiếp tục ghi, cũng không nên mặc định các trang là ảnh chụp cố định của toàn bộ tập kết quả.

Consistency level thường được cấu hình tại tầng driver hoặc theo từng thao tác bằng các API phù hợp phiên bản đang dùng. Nó **không** được quyết định chỉ bằng annotation `@Table` hay `@PrimaryKey`.

## 7. Quy trình suy nghĩ khi thiết kế bảng theo truy vấn

Giả sử sản phẩm cần hiển thị lịch sử mua hàng của một khách theo từng ngày:

1. **Xác định truy vấn bắt buộc:** biết `customer_id`, `order_day`, lấy các đơn mới trước, mỗi lượt 20 đơn.
2. **Đặt partition key:** `(customer_id, order_day)` để gom đúng một khách hàng/ngày; đánh giá kích thước và độ lệch tải của partition dự kiến.
3. **Đặt clustering columns:** `created_at DESC` cho trình tự hiển thị, thêm `order_id` để phân biệt các đơn cùng thời điểm.
4. **Chọn replication:** ví dụ `NetworkTopologyStrategy`, RF = 3 cho datacenter có topology phù hợp, dựa trên yêu cầu chịu lỗi và chi phí.
5. **Chọn CL, paging và quan sát hiệu năng:** kiểm tra độ trễ và tính nhất quán mong muốn; tránh đọc quá nhiều hàng, theo dõi partition lớn/hot partition, lượng tombstone và số trang được quét.
6. **Thiết kế thêm đường truy cập nếu cần:** tra đơn theo trạng thái, theo cửa hàng hay báo cáo nhiều ngày có thể cần các bảng đọc riêng hoặc giải pháp phân tích/chỉ mục khác.

Ví dụ, nếu một yêu cầu mới là “tất cả đơn PAID của cả hệ thống hôm nay”, bảng `orders_by_customer_day` không còn phù hợp để phục vụ trực tiếp vì thiếu `customer_id` trong điều kiện truy vấn. Đây là tín hiệu để **xem lại data model**, thay vì vội dùng `ALLOW FILTERING` hoặc quét hàng loạt partition trên đường xử lý trực tuyến.

## 8. Các nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “Một keyspace bằng một node.” | Keyspace là phạm vi logic/cấu hình; bảng và partition của nó được phân phối trên nhiều node. |
| “Primary key và partition key luôn giống nhau.” | Primary key đầy đủ có thể gồm **partition key + clustering columns**. |
| “Mỗi hàng là một partition.” | Nhiều hàng có cùng partition key nằm trong **một partition**. |
| “Clustering phân phối dữ liệu giữa các node.” | Clustering tổ chức hàng **bên trong** partition; partition key mới dùng để tính token định tuyến. |
| “RF = 3 nghĩa là một truy vấn sẽ trả về ba hàng.” | Ba replica là các bản sao lưu trữ; truy vấn logic vẫn trả về các hàng phù hợp một lần. |
| “RF = 3 thì mọi lần đọc luôn nhận giá trị mới nhất.” | Kết quả còn phụ thuộc consistency level, thời điểm ghi, lỗi và ngữ nghĩa nhất quán của Cassandra. |
| “Repository tự tối ưu mọi `WHERE`.” | Spring Data ánh xạ và thực thi truy vấn; thiết kế khóa và khả năng truy vấn vẫn do Cassandra quy định. |
| “Có `LIMIT` thì truy vấn thiếu partition key sẽ nhanh.” | `LIMIT` không thay thế điều kiện định tuyến, không bảo đảm tránh quét dữ liệu. |

## 9. Tự kiểm tra kiến thức

**Câu 1.** Với `PRIMARY KEY ((tenant_id, bucket_day), event_time, event_id)`, cột nào xác định partition?

**Đáp án:** Cặp `(tenant_id, bucket_day)`. `event_time` và `event_id` là clustering columns.

**Câu 2.** Hai hàng có cùng `tenant_id`, `bucket_day` nhưng khác `event_time` có ở cùng partition không?

**Đáp án:** Có. Nếu toàn bộ primary key không trùng nhau, chúng là hai hàng trong cùng partition.

**Câu 3.** Thay `WITH CLUSTERING ORDER BY (event_time DESC)` có làm các hàng được phân bố sang node khác không?

**Đáp án:** Không. Thứ tự clustering ảnh hưởng cách đọc hàng trong partition; phân bố theo token của partition key.

**Câu 4.** Keyspace có RF = 3 trong datacenter cục bộ. `LOCAL_QUORUM` cần bao nhiêu replica phản hồi trong datacenter đó?

**Đáp án:** Hai replica, tức đa số của ba.

**Câu 5.** Muốn lấy mọi đơn của toàn hệ thống theo `status`, có nên áp dụng trực tiếp truy vấn theo `status` trên bảng `orders_by_customer_day`?

**Đáp án:** Không mặc định. Điều kiện đó không xác định partition key của bảng. Cần đánh giá một data model/đường truy cập riêng, hoặc chỉ mục phù hợp với khả năng và chi phí vận hành.

---

**Ghi nhớ:** keyspace quy định phạm vi dữ liệu và replication; partition key quyết định nhóm hàng và định tuyến; clustering columns quyết định thứ tự/hàng trong partition; replica là các bản sao phân tán. Nắm rõ bốn khái niệm này giúp thiết kế CQL, mapping Spring Data Cassandra, paging và chính sách nhất quán phù hợp với truy vấn thực tế.
