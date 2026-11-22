# Sharding, khóa phân mảnh và định tuyến giao dịch

Khi một database đơn lẻ tiến gần giới hạn về CPU, I/O, dung lượng hoặc khả năng mở rộng theo chiều dọc, có thể chia dữ liệu theo chiều ngang thành nhiều database độc lập. Mỗi database lưu một phần dữ liệu và cùng phục vụ một ứng dụng. Kỹ thuật này gọi là **sharding**. Trong Oracle, Oracle Sharding cung cấp cơ chế phân phối dữ liệu, quản lý topology và định tuyến kết nối dựa trên shard key.

Khái niệm quan trọng nhất khi thiết kế sharding là **shard key**: một hoặc nhiều cột xác định dữ liệu thuộc shard nào. Ứng dụng cung cấp shard key khi mở kết nối hoặc thực hiện request theo cơ chế được hỗ trợ, để Shard Director hoặc connection pool định tuyến tới đúng shard. Khi mọi thao tác của một giao dịch nằm trong cùng shard, giao dịch có thể được xử lý như transaction cục bộ. Nếu giao dịch chạm nhiều shard, hệ thống cần phối hợp giữa các database và thường phải dùng distributed transaction với two-phase commit, làm tăng độ trễ và độ phức tạp.

Sharding vì vậy không chỉ là chia bảng thành nhiều phần. Nó là quyết định kiến trúc ảnh hưởng đến khóa dữ liệu, thiết kế API, transaction boundary, truy vấn, bảo mật, vận hành và khả năng mở rộng. Một shard key tốt giúp phần lớn request đi đến đúng một shard; một shard key kém có thể tạo hot shard, khiến nhiều truy vấn phải fan-out hoặc buộc transaction thường xuyên đi qua nhiều database.

## 1. Sharding là gì?

Sharding là cách phân chia dữ liệu thành các tập con theo một quy tắc xác định, sau đó lưu mỗi tập con trên một database riêng gọi là **shard**. Các shard cùng tạo thành một sharded database về mặt logic, nhưng mỗi shard là một Oracle Database độc lập về mặt lưu trữ và xử lý.

Ví dụ một hệ thống thương mại điện tử có 100 triệu khách hàng. Thay vì lưu toàn bộ khách hàng và đơn hàng trên một database, có thể phân phối theo `CUSTOMER_ID`:

```text
                     Ứng dụng
                        |
                        v
                Shard Director (GSM)
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
      Shard 1        Shard 2        Shard 3
    Customer A-H   Customer I-P   Customer Q-Z
    Orders ...     Orders ...     Orders ...
```

Sơ đồ chỉ minh họa cách chia theo nhóm khách hàng. Trong Oracle Sharding, cách phân phối thực tế phụ thuộc sharding method, shard key, chunk map và cấu hình topology.

### 1.1. Shard là database độc lập

Mỗi shard có thể có:

- Database instance và các process Oracle riêng.
- Datafile, control file, redo log và undo riêng.
- Schema, bảng, index và dữ liệu của phần shard đó.
- User, privilege, service và cấu hình vận hành riêng.
- Backup, recovery và HA strategy riêng.

Các shard không dùng chung một tập datafile để cùng truy cập như các instance trong Oracle RAC. Đây là mô hình *shared-nothing* ở cấp shard: mỗi shard sở hữu dữ liệu của mình và phối hợp với shard khác qua mạng, Shard Catalog, Shard Director và các cơ chế replication/transaction được hỗ trợ.

### 1.2. Mục tiêu của sharding

Sharding thường được cân nhắc khi cần:

- Mở rộng dung lượng vượt khả năng hợp lý của một database.
- Phân phối CPU, I/O và workload qua nhiều database server.
- Cô lập tải theo tenant, khách hàng, khu vực hoặc nhóm nghiệp vụ.
- Đưa dữ liệu đến gần khu vực người dùng theo yêu cầu độ trễ hoặc quy định.
- Mở rộng bằng cách thêm shard thay vì chỉ nâng cấu hình một máy chủ.
- Giới hạn phạm vi sự cố hoặc bảo trì ở một phần topology, nếu ứng dụng và HA được thiết kế phù hợp.

Sharding không tự động làm mọi truy vấn nhanh hơn. Nó giúp phân phối tải khi request có thể định tuyến đến một shard hoặc một nhóm shard nhỏ. Truy vấn cần quét toàn bộ dữ liệu có thể phải chạy trên nhiều shard rồi tổng hợp kết quả, làm tăng network traffic và thời gian xử lý.

## 2. Phân biệt sharding với partitioning, RAC và Data Guard

Các công nghệ này đều liên quan đến mở rộng hoặc bảo vệ database, nhưng giải quyết những vấn đề khác nhau.

| Công nghệ | Chia ở đâu? | Mục tiêu chính | Đặc điểm |
|---|---|---|---|
| Table partitioning | Bên trong một database | Quản lý bảng lớn, partition pruning, lifecycle dữ liệu | Các partition vẫn thuộc cùng database |
| Oracle RAC | Nhiều instance cùng truy cập một database | High availability và scale-out một database | Các instance chia sẻ database storage và phối hợp cache/lock |
| Oracle Sharding | Nhiều database độc lập | Scale-out dữ liệu và workload theo chiều ngang | Mỗi shard lưu một phần dữ liệu theo shard key |
| Oracle Data Guard | Primary và standby database | Disaster recovery và data protection | Standby duy trì bản sao redo của primary |
| Oracle GoldenGate | Giữa các database/hệ thống | Logical replication và CDC | Capture, truyền và apply các thay đổi logic |

Sharding có thể kết hợp với table partitioning bên trong từng shard. Một shard cũng có thể có chiến lược HA riêng; cấu hình cụ thể có thể dùng Data Guard hoặc phương án được Oracle hỗ trợ cho phiên bản triển khai. RAC và sharding không phải hai tên gọi cho cùng một kiến trúc: RAC mở rộng một database qua nhiều instance, còn sharding chia dữ liệu giữa nhiều database.

## 3. Các thành phần của Oracle Sharding

Oracle Sharding bổ sung một lớp quản lý topology và định tuyến để ứng dụng không phải tự duy trì danh sách shard cùng thuật toán phân phối dữ liệu.

### 3.1. Sharded database

Sharded database là toàn bộ hệ thống logic gồm các shard, metadata, dịch vụ định tuyến và các thành phần quản trị. Mỗi shard chứa một tập con của bảng sharded. Một số bảng nhỏ dùng chung có thể được cấu hình theo mô hình duplicated table để có bản sao trên các shard.

### 3.2. Shard Catalog

Shard Catalog là database lưu metadata quản trị cho sharded database, chẳng hạn:

- Topology và thông tin các shard.
- Sharding method và shard key definition.
- Mapping giữa shard key/chunk và shard.
- Thông tin cấu hình để quản lý và điều phối shard.

Shard Catalog không phải nơi chứa toàn bộ dữ liệu nghiệp vụ của ứng dụng. Dữ liệu khách hàng và đơn hàng được lưu ở các shard theo quy tắc phân phối. Catalog là nguồn metadata để các công cụ và thành phần quản lý hiểu topology.

### 3.3. Shard Director / Global Service Manager

Shard Director, thường được triển khai bằng Global Service Manager (GSM), là thành phần định tuyến kết nối và cung cấp global service. Client kết nối qua Shard Director và cung cấp shard key theo cơ chế hỗ trợ. Thành phần này sử dụng shard map để đưa kết nối tới shard thích hợp.

Shard Director cũng tham gia quản lý service, topology và trạng thái shard. Trong hệ thống production, cần thiết kế nhiều Shard Director hoặc phương án dự phòng phù hợp để lớp định tuyến không trở thành điểm lỗi đơn.

### 3.4. Global service

Global service cung cấp điểm kết nối logic cho ứng dụng. Service có thể được cấu hình theo workload, role, vùng hoặc mục đích truy cập. Shard Director dùng thông tin service và shard key để chọn nơi phục vụ request theo cấu hình.

Tên service và cấu hình kết nối cần được thống nhất giữa DBA và đội ứng dụng. Ứng dụng nên dùng service name được công bố thay vì hard-code SID hoặc kết nối trực tiếp một instance cụ thể.

### 3.5. Chunk và shard map

Trong system-managed sharding, dữ liệu được chia thành các chunk logic theo shard key. Chunk là đơn vị quản lý/phân phối dữ liệu và được ánh xạ tới shard. Shard map biểu diễn cách các giá trị shard key hoặc chunk được phân bổ.

Khi thêm shard hoặc cân bằng lại dung lượng, Oracle có thể di chuyển chunk theo cơ chế được hỗ trợ. Nhờ đó, DBA có thể điều chỉnh phân phối dữ liệu mà không cần ứng dụng tự tính toán vị trí vật lý của từng khách hàng.

### 3.6. Shard group và shardspace

Trong topology nâng cao, shard có thể được tổ chức thành shard group và shardspace để biểu diễn nhóm lưu trữ, phạm vi dữ liệu hoặc cấu hình replication/HA. Ý nghĩa cụ thể của từng thành phần phụ thuộc sharding method và kiến trúc triển khai. Khi thiết kế, cần dùng mô hình topology của đúng Oracle Database release thay vì suy luận shard group giống cluster hoặc RAC group.

## 4. Shard key là gì?

Shard key là một hoặc nhiều cột dùng để xác định shard chứa một dòng dữ liệu. Khi ứng dụng biết shard key của request, hệ thống có thể định tuyến tới shard sở hữu dữ liệu đó.

Ví dụ bảng khách hàng:

```sql
CREATE TABLE customers (
    customer_id   NUMBER(12) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    email         VARCHAR2(320),
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

Nếu `CUSTOMER_ID` là shard key, mọi dòng có cùng `CUSTOMER_ID` được định tuyến đến shard tương ứng. Các bảng nghiệp vụ phụ thuộc khách hàng như `ORDERS`, `ADDRESSES` và `PAYMENTS` có thể được thiết kế để cùng phân phối theo khóa khách hàng, giúp thao tác cho một khách hàng chủ yếu diễn ra trong một shard.

### 4.1. Simple shard key và composite shard key

Simple shard key gồm một cột, ví dụ `CUSTOMER_ID`.

Composite shard key gồm nhiều cột, ví dụ:

```text
(TENANT_ID, CUSTOMER_ID)
```

Composite key hữu ích khi một ID chỉ duy nhất trong phạm vi tenant. Ví dụ hai tenant đều có `CUSTOMER_ID = 1001`, nhưng cặp `(TENANT_ID, CUSTOMER_ID)` là định danh phân phối đầy đủ.

Khi dùng composite shard key, mọi client và bảng liên quan phải nhất quán về thứ tự/thành phần khóa. Thiếu một phần shard key có thể khiến định tuyến không thể xác định một shard duy nhất và phải dùng đường xử lý rộng hơn.

### 4.2. Shard key khác primary key

Primary key định danh duy nhất một dòng trong phạm vi mà constraint bảo đảm. Shard key xác định nơi lưu dòng đó. Hai khái niệm có thể trùng nhau nhưng không bắt buộc giống hệt.

Ví dụ:

```text
Shard key:   CUSTOMER_ID
Primary key: (CUSTOMER_ID, ORDER_ID)
```

Một đơn hàng được xác định duy nhất trong phạm vi customer, và `CUSTOMER_ID` cũng dùng để định tuyến. Với sharded table, cần tuân theo các giới hạn của Oracle về primary key/unique constraint; thông thường khóa duy nhất cục bộ phải bao gồm các cột shard key để database có thể enforce uniqueness mà không cần kiểm tra toàn bộ shard.

Nếu ứng dụng cần `ORDER_ID` duy nhất toàn hệ thống nhưng `ORDER_ID` không chứa shard key, cần thiết kế ID globally unique hoặc một cơ chế định danh phù hợp. Không giả định unique constraint cục bộ trên mỗi shard sẽ bảo đảm uniqueness trên toàn sharded database.

### 4.3. Tiêu chí chọn shard key

Một shard key tốt nên đáp ứng các tiêu chí:

1. **Phân phối cân bằng:** dữ liệu và workload không dồn vào một vài shard.
2. **Có trong request:** ứng dụng thường biết key trước khi truy vấn hoặc cập nhật.
3. **Ổn định:** ít thay đổi trong vòng đời bản ghi.
4. **Giữ locality:** các bảng thường được truy vấn cùng nhau có thể colocate.
5. **Cardinality phù hợp:** đủ nhiều giá trị để phân phối dữ liệu.
6. **Tránh hotspot:** không tạo một key quá phổ biến hoặc tăng đơn điệu gây tập trung tải.
7. **Đáp ứng quy định:** nếu dữ liệu phải ở một vùng/tenant cụ thể, key và mapping phải thể hiện được điều đó.

Không có shard key tốt chỉ dựa trên cardinality. Một cột có hàng triệu giá trị nhưng mọi request đọc cùng một tenant lớn vẫn có thể tạo hot shard. Phải đánh giá cả phân bố dữ liệu lẫn phân bố request.

## 5. Các phương pháp sharding trong Oracle

Oracle Sharding hỗ trợ các cách phân phối khác nhau. Lựa chọn ảnh hưởng đến locality, cân bằng tải và khả năng quản trị.

### 5.1. System-managed sharding

System-managed sharding thường dùng consistent hash trên shard key. Oracle quản lý việc phân chia thành chunk và phân phối chunk giữa các shard. DBA không cần tự ánh xạ từng giá trị key vào từng shard.

Ví dụ DDL minh họa cho sharded table:

```sql
CREATE SHARDED TABLE customers (
    customer_id   NUMBER(12) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    email         VARCHAR2(320),
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
)
PARTITION BY CONSISTENT HASH (customer_id)
PARTITIONS AUTO
TABLESPACE SET ts_customers;
```

Đây là ví dụ khái niệm; cú pháp đầy đủ và tablespace set phải phù hợp phiên bản, shard catalog và topology đã triển khai. Consistent hash giúp phân phối key tương đối đều và hỗ trợ di chuyển chunk khi topology thay đổi.

Ưu điểm:

- Giảm công việc tự định nghĩa range/list mapping.
- Hỗ trợ phân phối dữ liệu cân bằng theo hash.
- Dễ thêm shard và tái cân bằng bằng chunk movement.
- Phù hợp workload có truy cập theo key và không cần locality theo range.

Hạn chế:

- Truy vấn theo khoảng key có thể phải truy cập nhiều shard.
- DBA ít kiểm soát trực tiếp shard nào giữ một range cụ thể.
- Hot key vẫn có thể tạo hotspot dù hash phân phối đều các key khác.

### 5.2. User-defined sharding

User-defined sharding cho phép DBA kiểm soát mapping dữ liệu vào shard theo range hoặc list value. Ví dụ dữ liệu được chia theo khu vực địa lý, mã tổ chức hoặc nhóm tenant.

Ví dụ thiết kế logic:

```text
REGION = NORTH  -> Shard group North
REGION = CENTRAL -> Shard group Central
REGION = SOUTH  -> Shard group South
```

Ưu điểm:

- Kiểm soát rõ dữ liệu thuộc shard nào.
- Có thể đặt dữ liệu gần người dùng hoặc khu vực pháp lý tương ứng.
- Có thể tối ưu workload theo vùng/tenant.

Hạn chế:

- DBA phải quản lý mapping và dung lượng từng vùng.
- Phân phối lệch nếu một vùng lớn hơn nhiều vùng khác.
- Thêm vùng hoặc thay mapping có thể cần quy trình di chuyển dữ liệu rõ ràng.

User-defined sharding phù hợp khi ranh giới dữ liệu có ý nghĩa nghiệp vụ rõ và tương đối ổn định. Không nên chọn range chỉ vì dễ hiểu nếu một range có thể tăng trưởng nhanh hơn các range khác.

### 5.3. Composite sharding

Composite sharding kết hợp hai cấp phân phối, chẳng hạn range/list ở cấp đầu và hash ở cấp tiếp theo. Cách này có thể vừa giữ locality theo một chiều nghiệp vụ, vừa phân tán dữ liệu trong từng nhóm để giảm hotspot.

Ví dụ ý tưởng:

```text
REGION
  +-- NORTH   -> hash CUSTOMER_ID -> nhiều shard/chunk
  +-- CENTRAL -> hash CUSTOMER_ID -> nhiều shard/chunk
  +-- SOUTH   -> hash CUSTOMER_ID -> nhiều shard/chunk
```

Composite sharding hữu ích khi một key nghiệp vụ lớn cần được chia nhỏ hơn, hoặc khi cần tổ chức dữ liệu theo vùng và vẫn cân bằng tải trong vùng. Cần hiểu rõ Oracle release hỗ trợ tổ hợp partitioning/sharding nào và cách shard map biểu diễn hai cấp đó.

### 5.4. So sánh các phương pháp

| Tiêu chí | System-managed hash | User-defined range/list | Composite |
|---|---|---|---|
| Mapping | Oracle quản lý theo hash/chunk | DBA xác định mapping | Kết hợp nhiều cấp |
| Cân bằng dữ liệu | Thường thuận lợi hơn với key phân bố tốt | Phụ thuộc mapping và kích thước nhóm | Có thể cân bằng trong từng nhóm |
| Locality theo range/vùng | Hạn chế hơn | Tốt nếu mapping phù hợp | Có thể giữ locality và phân tán tiếp |
| Vận hành | Tự động hóa nhiều hơn | Cần quản lý mapping | Phức tạp hơn |
| Rủi ro | Hot key/hot shard | Range/list lệch tải | Thiết kế key và mapping phức tạp |

## 6. Co-location và table family

Một trong những lợi ích lớn nhất của sharding là giữ các dữ liệu thường được truy cập cùng nhau trên cùng shard. Khái niệm này gọi là **co-location**.

Ví dụ một request hiển thị đơn hàng của khách hàng thường cần:

- Thông tin customer.
- Orders của customer.
- Order items.
- Địa chỉ giao hàng.

Nếu các bảng này cùng dùng `CUSTOMER_ID` làm shard key và được định nghĩa trong cùng table family, dữ liệu liên quan có thể nằm cùng shard. Khi đó join và transaction thường chỉ cần một database.

### 6.1. Parent-child tables cùng shard key

Mô hình:

```text
CUSTOMERS
  shard key: CUSTOMER_ID
       |
       +------ ORDERS
       |        shard key: CUSTOMER_ID
       |            |
       |            +---- ORDER_ITEMS
       |                   shard key: CUSTOMER_ID
       |
       +------ ADDRESSES
                shard key: CUSTOMER_ID
```

Các bảng cùng shard key và cùng quy tắc phân phối cho phép một customer cùng các dữ liệu phụ thuộc được định tuyến đến một shard.

### 6.2. Table family

Table family mô tả nhóm bảng sharded có quan hệ parent-child và được colocate theo shard key. Bảng gốc là root table; các bảng phụ thuộc dùng cùng shard key và quan hệ foreign key phù hợp.

Thiết kế này giúp:

- Join cục bộ trong một shard.
- Enforce các quan hệ referential integrity cục bộ theo khả năng hỗ trợ.
- Thực hiện giao dịch nghiệp vụ trong một shard.
- Giảm số request phải fan-out hoặc dùng distributed transaction.

### 6.3. Foreign key trong sharded database

Không nên giả định một foreign key trên sharded table có thể tham chiếu tùy ý đến dòng ở shard khác như trong một database đơn. Để giữ referential integrity hiệu quả, bảng parent/child thường cần colocate và foreign key phải phù hợp với shard key/table family.

Nếu một quan hệ nghiệp vụ bắt buộc tham chiếu qua shard, cần thiết kế validation ở application/service layer hoặc một mô hình dữ liệu khác. Kiểm tra giới hạn foreign key và table family theo đúng phiên bản Oracle đang sử dụng.

### 6.4. Duplicated tables cho dữ liệu tham chiếu

Một số bảng nhỏ, ít thay đổi và được nhiều shard sử dụng có thể được triển khai dưới dạng duplicated table để mỗi shard có bản sao cục bộ. Ví dụ:

- Danh mục quốc gia.
- Mã loại tiền.
- Bảng trạng thái dùng chung.
- Bảng cấu hình tham chiếu nhỏ.

Duplicated table giúp tránh truy vấn remote shard chỉ để lấy một giá trị lookup. Khi thay đổi dữ liệu, cơ chế replication của Oracle Sharding duy trì các bản sao theo cấu hình. Cần cân nhắc chi phí đồng bộ và tần suất thay đổi; bảng lớn hoặc thay đổi liên tục thường không phù hợp.

## 7. Thiết kế shard key theo access pattern

Shard key phải được chọn dựa trên cách ứng dụng truy cập dữ liệu, không chỉ dựa trên cấu trúc bảng.

### 7.1. Request thường có customer ID

Nếu phần lớn request bắt đầu từ customer, `CUSTOMER_ID` là ứng viên tốt:

```sql
SELECT order_id, order_date, order_status
FROM orders
WHERE customer_id = :customer_id
ORDER BY order_date DESC;
```

Khi ứng dụng cung cấp `CUSTOMER_ID`, Shard Director có thể route đến shard chứa customer. Truy vấn không cần quét toàn bộ shard.

### 7.2. Request chỉ có order ID

Nếu API chỉ nhận `ORDER_ID` nhưng shard key là `CUSTOMER_ID`, hệ thống không thể tự suy ra shard từ order ID nếu không có mapping bổ sung. Các lựa chọn:

- Đưa customer ID vào request hoặc token để định tuyến.
- Thiết kế ID chứa thông tin shard theo quy ước được quản lý.
- Duy trì một lookup service/global index ánh xạ order ID sang shard key.
- Chấp nhận truy vấn cross-shard nếu tần suất thấp và chi phí phù hợp.

Đây là một quyết định quan trọng của API. Nếu ứng dụng thường xuyên tìm theo một key khác shard key, cần đánh giá lại thiết kế trước khi triển khai sharding.

### 7.3. Hot key và skew

Một shard key có cardinality cao vẫn có thể gây lệch tải. Ví dụ `TENANT_ID` phân phối đều giữa hàng nghìn tenant, nhưng một tenant lớn tạo 70% request. Nếu mọi dữ liệu của tenant đó ở một shard, shard này trở thành hot shard.

Các cách xử lý có thể gồm:

- Chia tenant lớn thành sub-tenant hoặc bucket.
- Dùng composite shard key như `(TENANT_ID, BUCKET_ID)` nếu nghiệp vụ cho phép.
- Tách workload lớn sang shardspace hoặc mô hình riêng.
- Cache dữ liệu đọc nhiều.
- Dùng read replica/replication architecture phù hợp cho read-heavy workload.

Mọi cách chia nhỏ tenant đều làm tăng độ phức tạp khi cần transaction toàn tenant hoặc truy vấn tổng hợp. Cần cân bằng giữa locality và phân phối tải.

### 7.4. Monotonic key

Nếu dùng một giá trị tăng liên tục như timestamp hoặc sequence toàn cục làm range shard key, các bản ghi mới có thể dồn vào range cuối cùng và tạo hot shard. Hash-based sharding thường giúp phân tán các giá trị key, nhưng query theo thời gian có thể phải truy cập nhiều shard.

Không có quy tắc rằng sequence luôn là shard key xấu; vấn đề là phân bố và access pattern. Hãy đo tốc độ insert, số request theo key và mức sử dụng từng shard.

### 7.5. Shard key có nên thay đổi?

Shard key nên ổn định trong vòng đời bản ghi. Khi thay đổi shard key, dữ liệu có thể cần chuyển sang shard khác và kéo theo thay đổi quan hệ parent-child, cache, transaction và routing. Khả năng cập nhật shard key trực tiếp phụ thuộc loại sharding và phiên bản; không nên giả định đây là một UPDATE thông thường.

Nếu nghiệp vụ thường xuyên đổi tenant hoặc region, cần thiết kế quy trình chuyển dữ liệu có kiểm soát, hoặc chọn key ổn định hơn để tránh di chuyển row thường xuyên.

## 8. Tạo sharded table và duplicated table

DDL chính xác phụ thuộc Oracle Database release, sharding method, shard catalog và tablespace set. Ví dụ sau minh họa system-managed consistent hash:

```sql
CREATE SHARDED TABLE customers (
    customer_id   NUMBER(12) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
)
PARTITION BY CONSISTENT HASH (customer_id)
PARTITIONS AUTO
TABLESPACE SET ts_customers;
```

Bảng `ORDERS` trong cùng table family có thể dùng cùng shard key và liên kết với parent theo quy tắc Oracle Sharding hỗ trợ. Ví dụ logic:

```sql
CREATE SHARDED TABLE orders (
    customer_id  NUMBER(12) NOT NULL,
    order_id     NUMBER(12) NOT NULL,
    order_date   TIMESTAMP NOT NULL,
    order_status VARCHAR2(20) NOT NULL,
    CONSTRAINT orders_pk PRIMARY KEY (customer_id, order_id),
    CONSTRAINT orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
)
PARTITION BY REFERENCE (orders_customer_fk);
```

Đoạn thứ hai mô tả ý tưởng reference partitioning trong table family; cú pháp và khả năng áp dụng cần đối chiếu với Oracle Sharding release, loại sharding và cách khai báo root table. Không sao chép trực tiếp hai đoạn DDL như một script bootstrap hoàn chỉnh khi chưa tạo topology, tablespace set và cấu hình table family.

### 8.1. Primary key và unique constraint

Với sharded table, các constraint duy nhất phải được thiết kế để Oracle có thể bảo đảm tính duy nhất trong phạm vi phân phối. Thông thường shard key phải nằm trong primary key hoặc unique key của sharded table. Nếu muốn một mã duy nhất toàn sharded database mà không chứa shard key, hãy tạo ID globally unique hoặc cơ chế kiểm soát uniqueness phù hợp.

### 8.2. Index trong mỗi shard

Index của sharded table được tạo và quản lý theo object definition trong các shard. Local index giúp truy vấn cục bộ theo shard key và các predicate khác. Cần xem execution plan trên shard thực tế, cardinality và workload; một index có ích trên database đơn lẻ chưa chắc giải quyết được scatter-gather query.

### 8.3. Duplicated table

Duplicated table chứa bản sao dữ liệu tham chiếu trên các shard. DDL tạo duplicated table khác với `CREATE SHARDED TABLE`; cần dùng cú pháp được Oracle Sharding hỗ trợ cho release tương ứng và quản lý thay đổi qua shard catalog. Không tự tạo một bảng cùng tên thủ công trên từng shard rồi coi đó là duplicated table, vì khi đó Oracle không có metadata replication tương ứng.

## 9. Định tuyến kết nối bằng shard key

Định tuyến là quá trình xác định shard phục vụ một request. Trong Oracle Sharding, client hoặc connection pool cần cung cấp shard key theo API/driver hỗ trợ.

### 9.1. Routing qua Shard Director

Luồng tổng quát:

1. Ứng dụng mở kết nối tới global service qua Shard Director.
2. Ứng dụng cung cấp shard key.
3. Shard Director tra shard map.
4. Kết nối được chuyển tới shard phù hợp.
5. Các SQL tiếp theo trên connection được thực thi tại shard đó.

Khi client không cung cấp đủ shard key, hệ thống có thể phải sử dụng route không xác định shard duy nhất hoặc đường xử lý cross-shard tùy API và cấu hình. Truy vấn có predicate shard key trong SQL không phải lúc nào cũng tương đương với việc cung cấp shard key khi tạo connection; khả năng routing phụ thuộc cách client/driver và service được cấu hình.

### 9.2. Proxy routing và direct routing

**Proxy routing**: client kết nối qua Shard Director; thành phần này nhận shard key và chuyển kết nối tới shard. Đây là mô hình dễ hình dung và phù hợp khi cần lớp định tuyến tập trung.

**Direct routing**: client hoặc shard-aware connection pool sử dụng shard map để kết nối trực tiếp tới shard sau khi xác định key. Cách này có thể giảm hop qua router và giảm tải ở lớp định tuyến, nhưng client/pool phải quản lý topology và routing đúng cách.

Khả năng và cách cấu hình proxy/direct routing phụ thuộc Oracle client, JDBC driver, UCP và release. Cần kiểm tra tài liệu đúng phiên bản thay vì giả định mọi driver đều hỗ trợ cùng API.

### 9.3. Sharding API trong JDBC

JDBC 4.3 định nghĩa API cho sharding key và connection builder. Driver cần hỗ trợ các API đó. Ví dụ khái niệm:

```java
ShardingKey shardingKey = dataSource.createShardingKeyBuilder()
        .subkey(customerId, JDBCType.NUMERIC)
        .build();

Connection connection = dataSource.createConnectionBuilder()
        .shardingKey(shardingKey)
        .build();
```

Đoạn code minh họa chuẩn JDBC; Oracle JDBC/UCP version và cách cấu hình DataSource phải hỗ trợ sharding API tương ứng. Với composite shard key, builder có thể cần nhiều subkey theo đúng thứ tự và kiểu dữ liệu được định nghĩa trong shard catalog.

Trong ứng dụng Spring, connection pool cần giữ đúng thông tin shard khi cấp connection. Không lấy một connection đã được route tới shard A rồi tái sử dụng nó cho request của shard B mà không dùng cơ chế chuyển/định tuyến được hỗ trợ.

### 9.4. Shard-aware connection pool

Connection pool thông thường tái sử dụng connection dựa trên database/service. Trong sharded database, pool cần biết shard key để lấy connection đúng shard hoặc quản lý pool theo shard. Oracle Universal Connection Pool (UCP) có các tính năng tích hợp với Oracle Sharding trong các release được hỗ trợ.

Một pool shard-aware giúp:

- Giảm chi phí mở kết nối mới.
- Tái sử dụng connection tại đúng shard.
- Định tuyến theo shard key.
- Hỗ trợ affinity và quản lý topology theo khả năng driver/pool.

Pool cần giới hạn tổng connection trên toàn bộ shard. Nếu ứng dụng có nhiều instance và mỗi instance tạo pool lớn cho mọi shard, số connection có thể tăng theo tích số application instances × shards × pool size. Cần capacity planning và kiểm soát idle connection.

### 9.5. Shard key phải có trước khi lấy connection

Nếu API biết `CUSTOMER_ID` ngay từ đầu, hãy truyền key trước khi lấy connection. Nếu chỉ biết shard key sau khi đã query một bảng khác, request đầu tiên có thể cần lookup service hoặc một route khác.

Thiết kế API nên truyền shard key trong path, request context hoặc token đã xác thực khi phù hợp. Không tin shard key do client tùy ý gửi nếu nó ảnh hưởng tenant isolation; server phải xác thực key với danh tính/ủy quyền của request.

## 10. Định tuyến transaction

Khi một connection đã được route tới shard, các statement trên connection đó thường được thực hiện tại shard đã chọn. Một transaction cục bộ có thể cập nhật nhiều bảng colocated và commit như transaction Oracle thông thường.

### 10.1. Single-shard transaction

Ví dụ request cập nhật customer và tạo order:

```sql
UPDATE customers
SET customer_name = :name
WHERE customer_id = :customer_id;

INSERT INTO orders(customer_id, order_id, order_date, order_status)
VALUES (:customer_id, :order_id, SYSTIMESTAMP, 'NEW');

COMMIT;
```

Nếu cả hai bảng colocated theo `CUSTOMER_ID` và connection được route bằng customer key, các thao tác diễn ra trên một shard. Transaction có thể dùng local commit, giảm network coordination và giữ semantics quen thuộc của Oracle.

### 10.2. Multi-shard transaction

Nếu một transaction cần cập nhật dữ liệu ở hai shard, ví dụ chuyển hàng tồn kho giữa hai kho thuộc hai shard khác nhau, hệ thống phải phối hợp transaction trên nhiều database.

Oracle Sharding có thể hỗ trợ multi-shard transaction theo cơ chế distributed transaction. Để bảo đảm atomicity, hệ thống thường sử dụng two-phase commit (2PC):

1. **Prepare phase:** coordinator yêu cầu các participant chuẩn bị commit và ghi trạng thái cần thiết.
2. **Commit phase:** khi tất cả participant sẵn sàng, coordinator yêu cầu commit; nếu có lỗi theo protocol, transaction được xử lý theo quy tắc distributed transaction.

2PC giúp duy trì atomicity nhưng tăng round-trip, thời gian giữ resource và độ phức tạp phục hồi. Nếu network hoặc một participant lỗi trong lúc commit, có thể xuất hiện in-doubt transaction cần recovery.

### 10.3. Chi phí của multi-shard transaction

Multi-shard transaction có thể làm tăng:

- Network latency giữa coordinator và shard.
- Thời gian transaction mở.
- Lock duration ở các participant.
- Khối lượng metadata/recovery cần quản lý.
- Khả năng gặp lỗi distributed transaction hoặc in-doubt.
- Khó khăn khi retry nếu kết quả commit không xác định ngay tại client.

Vì vậy, kiến trúc sharding thường cố gắng đưa các thao tác thường xuyên của một business transaction vào cùng shard. Multi-shard transaction nên dành cho trường hợp thật sự cần atomicity xuyên shard.

### 10.4. Khi nào dùng saga hoặc eventual consistency?

Không phải mọi nghiệp vụ liên quan nhiều shard đều cần 2PC. Có thể chia quy trình thành các bước cục bộ với saga/outbox và compensation nếu nghiệp vụ cho phép.

Ví dụ chuyển hàng giữa hai vùng:

1. Tạo yêu cầu chuyển ở shard nguồn.
2. Giữ hoặc trừ tồn kho ở shard nguồn trong transaction cục bộ.
3. Phát sự kiện chuyển hàng.
4. Shard đích nhận sự kiện và cộng tồn kho trong transaction cục bộ.
5. Nếu bước sau thất bại, chạy compensation hoặc đưa yêu cầu vào trạng thái cần xử lý.

Saga không cung cấp atomic commit tức thời như 2PC. Nó cung cấp consistency theo quy trình và compensation. Chọn 2PC hay saga dựa trên yêu cầu nghiệp vụ, latency, failure model và khả năng chấp nhận trạng thái trung gian.

## 11. Truy vấn một shard và truy vấn nhiều shard

### 11.1. Shard-key lookup

Truy vấn có đủ shard key thường được route tới shard sở hữu dữ liệu:

```sql
SELECT order_id,
       order_date,
       order_status
FROM orders
WHERE customer_id = :customer_id
  AND order_id = :order_id;
```

Nếu connection đã được mở với shard key `CUSTOMER_ID`, truy vấn có thể chạy cục bộ. Đây là dạng truy vấn nên tối ưu cho OLTP.

### 11.2. Truy vấn không có shard key

Ví dụ:

```sql
SELECT COUNT(*)
FROM orders
WHERE order_status = 'NEW';
```

Predicate không chứa shard key. Hệ thống không thể xác định một shard duy nhất chỉ từ điều kiện này. Tùy service và API, truy vấn có thể phải thực hiện trên nhiều shard rồi tổng hợp, hoặc cần được gửi qua cơ chế multi-shard query.

Fan-out query có thể tốn network, CPU và thời gian tăng theo số shard. Khi số shard tăng, chi phí điều phối và tổng hợp cũng tăng.

### 11.3. Cross-shard join

Join giữa hai bảng colocated theo cùng shard key thường có thể xử lý cục bộ trên shard. Join giữa bảng không colocated có thể cần dữ liệu di chuyển qua mạng hoặc truy vấn phân tán phức tạp.

Ví dụ join orders với customers theo `CUSTOMER_ID` là phù hợp nếu hai bảng cùng table family. Join orders với một bảng giao dịch toàn cục phân phối theo `TRANSACTION_ID` có thể trở thành cross-shard join.

### 11.4. Aggregate toàn hệ thống

Báo cáo như tổng doanh thu tất cả shard thường cần chạy aggregate ở từng shard rồi tổng hợp kết quả. Cần kiểm tra tính chính xác của aggregation, filter, timezone và thời điểm dữ liệu giữa shard.

Với báo cáo nặng, có thể dùng data warehouse, materialized/reporting layer hoặc pipeline CDC thay vì chạy fan-out OLTP query trên mọi shard.

## 12. Định tuyến theo tenant và bảo mật

Một mô hình phổ biến là shard theo `TENANT_ID`. Mỗi tenant có dữ liệu trên một shard hoặc một nhóm phân phối theo key. Điều này giúp locality và có thể hỗ trợ yêu cầu residency.

### 12.1. Xác thực shard key

Shard key là thông tin định tuyến, không phải cơ chế authorization. Nếu client gửi `TENANT_ID` của tenant khác, việc route đúng shard không ngăn truy cập trái phép.

Ứng dụng cần:

- Lấy tenant identity từ token/session đã xác thực.
- Kiểm tra user có quyền truy cập tenant đó.
- Không tin `TENANT_ID` từ query parameter mà chưa xác minh.
- Đưa tenant key vào mọi query cần thiết.
- Bảo vệ connection context để không tái sử dụng sai tenant.

### 12.2. Tenant isolation

Sharding theo tenant không tự động bảo đảm mọi dữ liệu tenant được cô lập về mặt bảo mật. Cần kết hợp schema privilege, application authorization, auditing và kiểm tra query predicate. Nếu nhiều tenant cùng một shard, vẫn phải enforce tenant filter trong ứng dụng hoặc database security policy phù hợp.

### 12.3. Data residency

User-defined sharding có thể hỗ trợ mapping tenant/region đến shard group ở khu vực mong muốn. Tuy nhiên, cần xem cả bản sao, backup, archive log, monitoring và dữ liệu duplicated table. Dữ liệu chỉ được đặt đúng vùng nếu toàn bộ pipeline và HA topology cũng tuân thủ quy định residency.

## 13. Thay đổi topology và rebalance dữ liệu

Khi số lượng tenant, dung lượng hoặc tải tăng, DBA có thể cần thêm shard hoặc chuyển chunk để cân bằng.

### 13.1. Thêm shard

Quy trình tổng quát:

1. Chuẩn bị server/storage và database mới.
2. Cấu hình shard theo topology, service và replication/HA policy.
3. Đăng ký shard với Shard Catalog bằng công cụ quản trị.
4. Xác nhận shard sẵn sàng và service hoạt động.
5. Thực hiện rebalance/chunk movement theo chính sách.
6. Theo dõi dữ liệu, lag, throughput và trạng thái chuyển chunk.

Thêm một database vào topology chưa chắc tự động làm dữ liệu cũ được phân phối lại ngay. Cần hiểu cơ chế chunk movement và trạng thái rebalance của Oracle release.

### 13.2. Chunk movement

Chunk là đơn vị phân phối dữ liệu trong system-managed sharding. Khi rebalance, Oracle có thể chuyển chunk từ shard nguồn sang shard đích và cập nhật shard map. Mục tiêu là cân bằng dung lượng/workload mà không yêu cầu ứng dụng tự viết logic chuyển từng dòng.

Trong thời gian di chuyển, cần theo dõi:

- Tiến độ chunk movement.
- Dung lượng tạm và network traffic.
- Ảnh hưởng đến latency của request.
- Tính sẵn sàng của shard nguồn/đích.
- Trạng thái shard map và routing sau khi hoàn tất.

### 13.3. Hot shard không chỉ do dữ liệu nhiều

Một shard có thể ít dữ liệu nhưng vẫn hot vì workload tập trung vào một tenant hoặc key. Rebalance theo dung lượng không luôn giải quyết được hot key. Cần xem metrics CPU, I/O, session, request rate, top SQL và distribution của key.

Nếu một tenant đơn lẻ tạo tải vượt năng lực shard, có thể cần sub-sharding, cache, tách workload hoặc thay đổi mô hình dữ liệu. Di chuyển nguyên tenant sang shard khác chỉ giúp nếu shard đích còn capacity và key không tiếp tục tập trung.

## 14. High availability và backup cho từng shard

Vì shard là database độc lập, mỗi shard cần backup, recovery, monitoring và HA strategy. Không thể giả định backup của Shard Catalog thay thế backup dữ liệu shard.

### 14.1. Data Guard theo shard

Một kiến trúc có thể triển khai standby cho từng shard bằng Data Guard theo mô hình được Oracle hỗ trợ. Khi shard primary gặp sự cố, standby của shard đó có thể được chuyển vai trò theo runbook. Shard Catalog và Shard Director cũng cần HA riêng.

### 14.2. Phân biệt lỗi shard với lỗi router

Các lớp có thể gặp lỗi độc lập:

- Một shard database không sẵn sàng.
- Shard Director/GSM không sẵn sàng.
- Shard Catalog không sẵn sàng.
- Network giữa application và shard bị gián đoạn.
- Replication/standby lag hoặc failover chưa hoàn tất.

Monitoring cần phân biệt các lớp này để không xử lý nhầm. Nếu router lỗi nhưng shard vẫn khỏe, khôi phục routing là ưu tiên. Nếu một shard lỗi, cần xử lý database/standby của shard đó.

### 14.3. Backup và restore

Backup policy cần bao phủ mọi shard, catalog và metadata cần thiết để dựng lại topology. Restore một shard về thời điểm khác với các shard còn lại có thể gây inconsistency xuyên shard nếu nghiệp vụ có giao dịch multi-shard.

Runbook DR phải mô tả cách phục hồi shard, đồng bộ catalog/routing, xác nhận shard map và đối soát dữ liệu. Cần kiểm thử restore định kỳ thay vì chỉ kiểm tra backup job thành công.

## 15. Quản trị Oracle Sharding

Oracle cung cấp công cụ `GDSCTL` để quản lý Shard Director, shard, service và topology. Các lệnh cụ thể thay đổi theo release và deployment mode.

Một số thao tác kiểm tra khái quát:

```text
GDSCTL> config shard
GDSCTL> status
GDSCTL> config gsm
```

Các lệnh này minh họa việc xem cấu hình shard, trạng thái topology và Global Service Manager. Khi chạy thực tế, dùng help và tài liệu của đúng phiên bản để xác nhận cú pháp, quyền và tùy chọn.

### 15.1. Shard Catalog views

Shard Catalog cung cấp data dictionary views để xem metadata sharding. Các view có thể gồm thông tin shard, shard group, sharding key, shard method và mapping. Tên view/cột phụ thuộc release và quyền; DBA có thể tra cứu các view `DBA_SHARDS`, `DBA_SHARDING_KEYS` và các view liên quan trong data dictionary của phiên bản.

Không nên hard-code một truy vấn quản trị dựa trên tên cột của phiên bản khác. Trước khi viết automation, kiểm tra `DESC` hoặc data dictionary reference trong môi trường thật.

### 15.2. Monitoring theo từng shard

Nên theo dõi ít nhất:

- CPU, memory, I/O và storage của từng shard.
- Session count và connection pool utilization.
- Throughput, latency và error rate theo shard.
- Top SQL và execution plan.
- Transaction duration, lock wait và deadlock.
- Tablespace growth và archive log generation.
- Replication/standby lag nếu có HA.
- Chunk movement/rebalance progress.
- Shard Director/GSM availability và routing error.

Metrics tổng thể có thể che giấu skew. Một shard có thể đạt 95% CPU trong khi trung bình cluster chỉ 35%. Dashboard nên hiển thị phân bố theo từng shard, không chỉ một con số trung bình.

## 16. Thiết kế ứng dụng Spring/Java cho sharded database

Ứng dụng cần mang shard key xuyên suốt request, từ API đến repository và connection acquisition.

### 16.1. Đưa shard key vào application context

Ví dụ request:

```text
GET /tenants/42/customers/1001/orders
```

Server xác thực tenant 42, xác định customer 1001 thuộc tenant đó và tạo routing context:

```java
public record TenantContext(long tenantId) {}
```

Repository/service nhận tenant key tường minh hoặc dùng context đã được xác thực. Tránh dùng ThreadLocal không được dọn trong thread pool vì có thể làm rò tenant context giữa các request.

### 16.2. Chọn shard trước khi mở transaction

Transaction nên bắt đầu sau khi shard key đã được xác định và connection đã được route đúng. Nếu một transaction Spring mở connection trước rồi mới đổi shard key, connection có thể vẫn gắn với shard ban đầu.

Thiết kế routing DataSource/connection pool cần phối hợp với transaction manager. Cần integration test để xác nhận mọi repository trong cùng transaction dùng đúng shard và không vô tình lấy connection từ một pool khác.

### 16.3. Không route chỉ bằng ThreadLocal tùy tiện

Một `AbstractRoutingDataSource` tùy biến có thể chọn DataSource theo context, nhưng tự viết router không tự động biến nhiều Oracle database thành Oracle Sharding. Nó chỉ chọn DataSource theo logic ứng dụng. Khi dùng Oracle Sharding, nên dùng Shard Director, shard-aware driver/pool và cơ chế được Oracle hỗ trợ để đồng bộ với shard map.

Nếu tự quản lý routing ngoài Oracle Sharding, ứng dụng phải tự xử lý topology change, failover, data movement, connection pool, stale mapping và transaction boundary. Đây là một bài toán vận hành lớn.

### 16.4. Transaction propagation

Trong Spring, `@Transactional` quản lý transaction trên connection do transaction manager cấp. Nếu một service gọi repository với shard key khác trong cùng transaction, không thể giả định Spring sẽ tự chuyển transaction sang shard khác. Connection đã được lấy thường gắn với database cụ thể.

Đối với multi-shard transaction, cần dùng khả năng distributed transaction được hỗ trợ và cấu hình transaction manager tương ứng; không chỉ gọi hai DataSource trong một method rồi kỳ vọng atomic commit.

## 17. ID toàn cục và sequence trong sharding

Nếu mỗi shard có sequence riêng bắt đầu từ cùng một giá trị, hai shard có thể sinh cùng ID. Điều đó không nhất thiết vi phạm uniqueness cục bộ, nhưng có thể gây trùng khi dữ liệu được tổng hợp hoặc di chuyển.

Các chiến lược thường dùng:

- **Composite key:** `(SHARD_KEY, LOCAL_ID)` làm khóa duy nhất.
- **UUID/GUID:** tạo ID phân tán với xác suất trùng rất thấp, chấp nhận kích thước/index trade-off.
- **Shard prefix:** đưa shard identifier vào ID theo quy ước toàn hệ thống.
- **Scalable sequence:** dùng khả năng sequence phù hợp của Oracle version nếu đáp ứng yêu cầu.
- **Central ID service:** cấp ID toàn cục, nhưng có thể tạo dependency/throughput bottleneck.

Không nên giả định sequence trong Oracle là gapless hoặc toàn cục giữa các shard. Sequence có thể cache, có gap khi rollback hoặc restart. Nếu dùng shard prefix, cần quản lý việc thay đổi topology và tránh tái sử dụng prefix.

## 18. Các lỗi thiết kế thường gặp

### 18.1. Chọn shard key không xuất hiện trong API

Ứng dụng phải lookup shard key trước khi truy vấn, làm tăng round-trip hoặc buộc fan-out. Hãy kiểm tra các API quan trọng có biết shard key ngay từ đầu không.

### 18.2. Chọn key có skew lớn

Một tenant hoặc region lớn tạo hot shard. Cần phân tích percentile workload, không chỉ tổng số key.

### 18.3. Bảng liên quan không colocate

Transaction tạo order phải cập nhật inventory ở shard khác. Điều này biến giao dịch OLTP đơn giản thành multi-shard transaction. Cần xác định aggregate boundary và locality trước khi chọn key.

### 18.4. Dùng fan-out query cho API OLTP

Mọi request phải hỏi tất cả shard rồi tổng hợp. Khi số shard tăng, latency và network traffic tăng. Nếu query thường xuyên cần global lookup, cân nhắc duplicated/reference table, global index/service hoặc data warehouse.

### 18.5. Không tính chi phí connection pool

Mỗi application instance giữ pool cho nhiều shard có thể tạo hàng nghìn connection. Cần capacity planning tổng thể và theo dõi idle/active connection.

### 18.6. Coi shard key là security boundary

Định tuyến đúng shard không thay thế authorization. Luôn xác thực tenant/user và kiểm soát quyền trên dữ liệu.

### 18.7. Không kiểm thử topology change

Thêm shard, move chunk hoặc failover có thể làm routing/cache thay đổi. Cần test ứng dụng trong lúc topology thay đổi và xác nhận connection pool xử lý stale routing theo hướng được hỗ trợ.

## 19. Quy trình thiết kế sharding

Một quy trình có thể thực hiện theo các bước:

1. **Đo workload hiện tại:** dung lượng, throughput, latency, CPU, I/O, hot SQL và growth rate.
2. **Xác định aggregate nghiệp vụ:** dữ liệu nào cần đọc/ghi cùng transaction?
3. **Liệt kê access pattern:** API thường tìm theo customer, tenant, order hay thời gian?
4. **Đề xuất shard key:** đánh giá cardinality, skew, stability và locality.
5. **Chọn sharding method:** system-managed hash, user-defined range/list hoặc composite.
6. **Thiết kế table family:** colocate parent-child và xác định duplicated/reference tables.
7. **Thiết kế global ID:** bảo đảm uniqueness và khả năng di chuyển dữ liệu.
8. **Thiết kế routing:** Shard Director, global service, JDBC/UCP và connection pool.
9. **Phân loại transaction:** single-shard, multi-shard 2PC hoặc saga/eventual consistency.
10. **Thiết kế truy vấn:** targeted query, cross-shard query, reporting và global lookup.
11. **Thiết kế HA/DR:** backup, Data Guard/replication, catalog và director availability.
12. **Kiểm thử:** skew, hot key, fan-out, latency, failover, rebalance và transaction recovery.
13. **Vận hành:** metrics per shard, capacity, chunk movement, backup và runbook.

## 20. Bài thực hành thiết kế sharding cho hệ thống đa tenant

Giả sử ứng dụng SaaS có nhiều tenant. Mỗi tenant có khách hàng, đơn hàng, chi tiết đơn và địa chỉ. Phần lớn API nhận `TENANT_ID` trong access token.

### Bước 1: Xác định aggregate

Các dữ liệu sau thường được truy cập cùng nhau:

```text
TENANT
  +-- CUSTOMERS
  |     +-- ADDRESSES
  |     +-- ORDERS
  |            +-- ORDER_ITEMS
  +-- TENANT_SETTINGS
```

### Bước 2: Chọn shard key

Đề xuất `TENANT_ID` hoặc composite `(TENANT_ID, CUSTOMER_ID)` tùy tính duy nhất và phân bố tải. Nếu một tenant có workload rất lớn, có thể cần bucket hoặc sub-sharding; điều này phải được đánh giá với yêu cầu transaction.

### Bước 3: Chọn sharding method

Nếu tenant phân bố tương đối đều và không có yêu cầu vùng cố định, system-managed consistent hash là ứng viên. Nếu tenant phải nằm ở khu vực cụ thể, user-defined mapping hoặc composite method có thể phù hợp hơn.

### Bước 4: Thiết kế table family

Đặt các bảng nghiệp vụ dùng chung shard key để tenant và dữ liệu con được colocate. Các bảng lookup nhỏ, ít thay đổi có thể được cân nhắc làm duplicated tables.

### Bước 5: Thiết kế API routing

Access token xác định tenant. Middleware xác thực tenant và truyền shard key đến connection acquisition. Repository không tự đoán shard từ một ID không có mapping.

### Bước 6: Thiết kế transaction

Tạo order và order items cùng tenant thực hiện trong một shard transaction. Báo cáo tổng doanh thu toàn tenant hoặc toàn hệ thống có thể cần multi-shard query hoặc reporting pipeline. Chuyển tài nguyên giữa hai tenant/shard cần chọn 2PC hoặc saga theo yêu cầu nghiệp vụ.

### Bước 7: Kiểm thử phân phối

Tạo tenant nhỏ, tenant lớn và tenant có request rate cao. Đo:

- Số tenant và số dòng trên từng shard.
- Request rate, CPU và I/O mỗi shard.
- Tỷ lệ targeted query so với fan-out query.
- Số multi-shard transaction.
- Latency p50/p95/p99 theo shard.

Nếu một shard nóng, điều chỉnh key/mapping hoặc tách workload trước khi tăng số shard một cách máy móc.

## 21. Checklist trước khi đưa Oracle Sharding vào production

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Business boundary | Aggregate nào cần transaction cục bộ và dữ liệu nào có thể eventual consistency? |
| Shard key | Request có key ngay từ đầu; key ổn định và phân phối tải phù hợp không? |
| Sharding method | Hash, range/list hay composite phù hợp access pattern và residency? |
| Table family | Parent-child có colocate; FK có đáp ứng giới hạn Oracle không? |
| Reference data | Bảng nhỏ nào nên duplicated; cách cập nhật bản sao ra sao? |
| Global ID | ID có unique toàn hệ thống và không phụ thuộc sequence cục bộ không? |
| Routing | GSM/global service, JDBC driver/UCP và pool có hỗ trợ routing đã chọn không? |
| Security | Shard key được xác thực; tenant isolation được enforce ở ứng dụng/database không? |
| Transactions | Giao dịch nào single-shard; giao dịch nào dùng 2PC hoặc saga? |
| Queries | Có quá nhiều fan-out, cross-shard join hoặc global lookup không? |
| Capacity | Connection pool, CPU, I/O, storage và growth mỗi shard đã được tính chưa? |
| HA/DR | Mỗi shard, Shard Catalog và Shard Director có backup/standby/runbook không? |
| Rebalance | Đã thử thêm shard, chunk movement và topology refresh chưa? |
| Monitoring | Dashboard có metrics riêng từng shard và latency theo route không? |
| Recovery | Đã thử lỗi network, shard outage, in-doubt transaction và restore chưa? |

Sharding phát huy hiệu quả khi shard key phản ánh đúng cách ứng dụng truy cập dữ liệu. Oracle Sharding cung cấp shard catalog, shard director, chunk map và routing để phân phối request đến database chứa dữ liệu. Khi các bảng liên quan được colocate, phần lớn giao dịch có thể chạy trong một shard với chi phí thấp hơn. Những truy vấn hoặc transaction xuyên shard vẫn có thể thực hiện theo cơ chế được hỗ trợ, nhưng thường tốn network coordination và có thể cần two-phase commit. Vì vậy, quyết định quan trọng nhất là chọn shard key ổn định, cân bằng tải, có sẵn trong request và giữ được dữ liệu của cùng một aggregate trên cùng shard; sau đó mới thiết kế routing, transaction, HA, rebalance và monitoring quanh quyết định đó.
