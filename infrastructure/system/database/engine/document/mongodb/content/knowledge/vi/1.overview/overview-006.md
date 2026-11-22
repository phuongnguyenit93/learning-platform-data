# Tổng quan MongoDB: Standalone, Replica Set, Sharded Cluster và MongoDB Atlas

## 1. Từ cơ sở dữ liệu document đến kiến trúc triển khai

MongoDB là hệ quản trị cơ sở dữ liệu hướng tài liệu (document database). Thay vì buộc mọi bản ghi phải có cùng tập cột như một bảng quan hệ, MongoDB lưu dữ liệu thành **document BSON** trong **collection**. BSON biểu diễn các cấu trúc gần với JSON, đồng thời hỗ trợ thêm những kiểu dữ liệu như ngày giờ, số nguyên 64-bit, Decimal128, dữ liệu nhị phân và ObjectId.

Ví dụ một document trong collection **orders**:

~~~javascript
{
  _id: ObjectId("671000000000000000000001"),
  customerId: "CUS-1042",
  createdAt: ISODate("2026-11-01T08:30:00Z"),
  status: "PAID",
  shippingAddress: {
    city: "Ha Noi",
    country: "VN"
  },
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 120000 },
    { sku: "PEN-02", quantity: 1, unitPrice: 15000 }
  ]
}
~~~

Mô hình document quyết định **cách tổ chức dữ liệu**; standalone, replica set và sharded cluster quyết định **MongoDB chạy trên bao nhiêu tiến trình/máy và dữ liệu được lưu, sao chép, phân phối như thế nào**. MongoDB Atlas lại là **dịch vụ vận hành MongoDB trên nền tảng đám mây**, có thể cung cấp các kiến trúc triển khai tương ứng. Do đó không nên xem Atlas là một thuật toán lưu trữ thứ tư ngang hàng với replication và sharding.

Một số thành phần cần phân biệt:

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Document** | Đơn vị dữ liệu BSON, thường tương đương một đối tượng nghiệp vụ hoặc một phần đối tượng. |
| **Collection / database** | Tập hợp document / tập hợp collection cùng metadata liên quan. |
| **mongod** | Tiến trình máy chủ MongoDB lưu trữ dữ liệu và phục vụ thao tác cơ sở dữ liệu. |
| **Node / member** | Một instance MongoDB tham gia vào một cấu hình triển khai. |
| **Replica set** | Nhóm các tiến trình **mongod** cùng duy trì bản sao của một tập dữ liệu. |
| **Shard** | Một phần dữ liệu của collection được phân vùng trong sharded cluster; trong production, mỗi shard thường là một replica set. |
| **mongos** | Bộ định tuyến truy vấn của sharded cluster; ứng dụng gửi yêu cầu tới mongos. |
| **Config server** | Thành phần lưu metadata về cấu hình và vị trí phân phối dữ liệu của sharded cluster, được triển khai thành replica set. |
| **Atlas** | Dịch vụ MongoDB được quản lý, cung cấp triển khai, bảo mật, theo dõi và các tính năng vận hành theo cấu hình/gói dịch vụ. |

### Ba câu hỏi kiến trúc quan trọng

1. **Cần chịu lỗi và tự chuyển vai trò khi một máy chết không?** Nếu có, xem xét **replica set**.
2. **Dung lượng hoặc tải đã vượt giới hạn phù hợp của một tập dữ liệu trên một nhóm máy chưa?** Nếu có, xem xét **sharding** với shard key được thiết kế theo truy vấn thực tế.
3. **Đội ngũ có muốn tự quản lý server, nâng cấp, sao lưu và giám sát không?** Nếu không, cân nhắc **Atlas** với mức dịch vụ đáp ứng yêu cầu.

Replication và sharding giải quyết **hai vấn đề khác nhau**: replication nhân bản dữ liệu để tăng khả năng sẵn sàng; sharding chia dữ liệu để phân tán lưu trữ và tải. Một hệ thống lớn thường **kết hợp cả hai**.

## 2. Standalone: một máy chủ MongoDB độc lập

### 2.1. Kiến trúc và luồng xử lý

Standalone chỉ có **một tiến trình mongod** phục vụ ứng dụng và nắm giữ toàn bộ dữ liệu của instance.

~~~text
  Java / Spring Boot / mongosh
              |
              | MongoDB Driver
              v
        +-------------+
        | mongod      |
        | standalone  |
        | collections |
        | indexes     |
        | journal     |
        +-------------+
              |
           Storage
~~~

Ứng dụng kết nối trực tiếp đến địa chỉ host và cổng của **mongod**. Mọi thao tác đọc/ghi đi qua một server. Không có primary/secondary, không có cơ chế election và không có mongos.

**Ưu điểm:** dễ cài, ít tài nguyên, dễ hiểu, hữu ích cho học tập, thử nghiệm, công cụ nội bộ nhỏ và một số công việc vận hành độc lập. Nếu tải vừa phải, standalone vẫn dùng đầy đủ nhiều đặc tính của MongoDB như CRUD, aggregation, indexing và atomicity ở cấp một document.

**Giới hạn:** nếu server hoặc ổ đĩa không sẵn sàng, ứng dụng mất quyền truy cập dữ liệu; không có tự động failover sang một bản sao. Việc có journal giúp phục hồi sau một số kiểu dừng bất thường **không đồng nghĩa** với chịu lỗi hạ tầng hay có một bản sao thay thế. Sao lưu và kiểm thử phục hồi vẫn cần thiết.

### 2.2. Thử nghiệm standalone trên máy cá nhân

Giả sử đã cài MongoDB Server và mongosh. Tạo một thư mục dữ liệu, sau đó mở terminal:

~~~bash
mkdir -p ./mongo-data
mongod --dbpath ./mongo-data --port 27017 --bind_ip 127.0.0.1
~~~

Lệnh **mkdir -p** ở trên phù hợp Linux/macOS; trên Windows có thể tạo thư mục tương đương bằng File Explorer hoặc PowerShell. Tiến trình **mongod** cần được giữ chạy trong terminal này. Mở terminal khác:

~~~bash
mongosh "mongodb://127.0.0.1:27017"
~~~

Thực hành trên shell:

~~~javascript
use shop

db.products.insertOne({
  sku: "MOUSE-01",
  name: "Wireless Mouse",
  price: 250000,
  stock: 12
})

db.products.find({ stock: { $gt: 0 } })
db.products.createIndex({ sku: 1 }, { unique: true })
db.products.findOne({ sku: "MOUSE-01" })
~~~

Chuỗi kết nối cơ bản là **mongodb://127.0.0.1:27017/shop**. Ví dụ chỉ ràng buộc loopback để dùng local; một máy chủ thật phải cấu hình xác thực, TLS, firewall và quyền truy cập phù hợp trước khi cho ứng dụng từ xa kết nối.

### 2.3. Khi nào phù hợp?

Standalone là lựa chọn tốt để **nắm cú pháp và mô hình document** mà chưa cần mô phỏng điều phối nhiều node. Trong production, nếu dịch vụ có yêu cầu liên tục hoạt động hoặc mất một node là sự cố nghiêm trọng, replica set thường phù hợp hơn. Ngoài ra, **multi-document transactions** được hỗ trợ trong replica set/sharded cluster theo điều kiện tương ứng; không nên thiết kế bài thực hành transaction nhiều document dựa vào standalone.

## 3. Replica set: nhiều bản sao, một tập dữ liệu logic

### 3.1. Primary và secondary

Replica set là một nhóm instance **mongod** cùng chứa các bản sao của dữ liệu. Cấu hình phổ biến có **ba thành viên mang dữ liệu** để tăng khả năng sẵn sàng.

~~~text
                      Application
                           |
                      MongoDB Driver
                           |
             +-------------+-------------+
             |             |             |
          +-------+     +-------+     +-------+
          | Node A|     | Node B|     | Node C|
          |PRIMARY| --> |SECOND.|     |SECOND.|
          +-------+     +-------+     +-------+
              |              ^            ^
              +--------------+------------+
                  oplog replication

           Cả ba cùng thuộc replica set "rs0"
~~~

Trong chế độ vận hành thông thường:

- **Primary** nhận thao tác ghi của ứng dụng, ghi các thay đổi vào oplog và phục vụ đọc nếu ứng dụng sử dụng read preference mặc định.
- **Secondary** sao chép và áp dụng các thao tác từ oplog theo cơ chế **bất đồng bộ**, giữ bản sao dữ liệu. Secondary có thể phục vụ đọc nếu client yêu cầu read preference thích hợp.
- Các thành viên có quyền bỏ phiếu tham gia **election** để chọn primary khi cần. Một primary phải có đủ điều kiện và sự hỗ trợ của **đa số phiếu**; không phải cứ còn một server sống thì đều tự thành primary.

Replica set giúp chịu lỗi một số node tùy số thành viên và cấu hình voting. Với **ba thành viên có quyền bầu chọn**, khi một thành viên không hoạt động, hai thành viên còn lại vẫn có thể tạo đa số. Khi chỉ còn một trong ba thành viên, replica set không thể bầu/duy trì primary có quyền ghi theo cơ chế bình thường.

### 3.2. Điều gì xảy ra khi primary gặp sự cố?

Giả sử Node A là primary và ngừng hoạt động:

1. Các thành viên còn lại phát hiện mất liên lạc thông qua cơ chế heartbeat.
2. Replica set bầu một secondary đủ điều kiện thành primary mới khi có đa số voting.
3. Driver nhận biết topology mới và hướng thao tác tới primary hiện tại.
4. Ứng dụng có thể thấy lỗi tạm thời hoặc độ trễ trong thời gian election; cần cấu hình timeout, retry và xử lý lỗi phù hợp.

**Failover tự động không đồng nghĩa không gián đoạn**. Với ghi chỉ được xác nhận ở một node, một số thao tác chưa replicate đủ có thể bị rollback khi đổi primary. Vì vậy mức đảm bảo ghi là một phần của thiết kế nghiệp vụ, không chỉ là cấu hình mạng.

### 3.3. Oplog, write concern và read preference

**Oplog** là một capped collection nội bộ ghi các thao tác cần replication. Secondary theo dõi và áp dụng dòng thao tác từ nguồn đồng bộ. Vì replication bất đồng bộ, có thể tồn tại **replication lag**: secondary chưa thấy ngay dữ liệu vừa được ghi vào primary.

Các tham số cần phân biệt:

| Khái niệm | Quyết định điều gì? | Hệ quả |
|---|---|---|
| **write concern: w: 1** | Primary xác nhận ghi theo mức yêu cầu tại một thành viên. | Phản hồi thường sớm hơn, nhưng không xác nhận đã được đa số bản sao chấp nhận. |
| **write concern: w: "majority"** | Đợi đa số thành viên mang dữ liệu theo quy tắc majority của replica set xác nhận ghi. | Tăng mức bảo vệ trước rollback, đổi lại có thể tăng độ trễ hoặc không ghi được khi không đủ điều kiện. |
| **read preference: primary** | Ưu tiên đọc từ primary; mặc định của driver. | Hữu ích khi cần tránh đọc secondary đang trễ. |
| **read preference: secondary / secondaryPreferred** | Cho phép đọc secondary theo chính sách chọn node. | Giảm một phần tải đọc primary, nhưng có thể đọc dữ liệu cũ. |
| **read concern: majority** | Đọc dữ liệu đã đạt mức majority committed theo semantics MongoDB. | Liên quan đến tính ổn định dữ liệu đọc; không tự biến mọi truy vấn thành linearizable read. |

Ví dụ ghi với write concern rõ ràng:

~~~javascript
db.orders.insertOne(
  { orderId: "ORD-1001", status: "CREATED" },
  { writeConcern: { w: "majority", wtimeout: 5000 } }
)
~~~

Nếu ứng dụng cần **read-your-writes**, nên thiết kế đường đọc/ghi cùng chính sách nhất quán phù hợp; đọc ngẫu nhiên từ secondary có thể chưa thấy thay đổi mới. **Read concern**, **write concern**, **read preference**, session và transaction giải quyết những khía cạnh khác nhau, không thể thay thế lẫn nhau.

### 3.4. Mô phỏng replica set ba node trên một máy

Ví dụ dành cho môi trường học tập, không tạo khả năng chịu lỗi vật lý vì cả ba tiến trình vẫn cùng nằm trên một máy. Tạo ba thư mục riêng:

~~~bash
mkdir -p ./data/rs1 ./data/rs2 ./data/rs3
~~~

Chạy ba lệnh dưới đây trong **ba terminal riêng**:

~~~bash
mongod --replSet rs0 --port 27101 --dbpath ./data/rs1 --bind_ip 127.0.0.1
mongod --replSet rs0 --port 27102 --dbpath ./data/rs2 --bind_ip 127.0.0.1
mongod --replSet rs0 --port 27103 --dbpath ./data/rs3 --bind_ip 127.0.0.1
~~~

Kết nối tới một instance rồi khởi tạo cấu hình:

~~~bash
mongosh "mongodb://127.0.0.1:27101/?directConnection=true"
~~~

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "127.0.0.1:27101" },
    { _id: 1, host: "127.0.0.1:27102" },
    { _id: 2, host: "127.0.0.1:27103" }
  ]
})

rs.status()
db.hello()
~~~

Sau khi replica set ổn định, chuỗi kết nối cho driver có thể dùng danh sách nhiều node:

~~~text
mongodb://127.0.0.1:27101,127.0.0.1:27102,127.0.0.1:27103/shop?replicaSet=rs0&retryWrites=true&w=majority
~~~

Khai báo nhiều địa chỉ giúp driver khám phá topology và tìm primary mới khi có failover. Trong triển khai trên nhiều máy hoặc container, **tên host được replica set công bố phải có thể phân giải và kết nối từ ứng dụng**; đặt tất cả host là **localhost** không đúng cho client ở máy khác.

### 3.5. Các lưu ý thiết kế

- **Ba data-bearing members** thường phù hợp hơn cách dùng hai data-bearing members cộng arbiter khi ứng dụng cần ghi **majority** ổn định. Arbiter có quyền bỏ phiếu nhưng không lưu dữ liệu.
- Replica set mang lại **high availability** và có thể phân tải đọc trong một số trường hợp, nhưng **không tự chia tập dữ liệu thành nhiều phần**. Mỗi data-bearing member phải có khả năng lưu toàn bộ tập dữ liệu được replicate.
- Transaction nhiều document là công cụ cho các thao tác cần atomicity vượt phạm vi một document; transaction có chi phí và không thay thế việc thiết kế document hợp lý.
- Replication **không phải backup**: lệnh xóa nhầm hoặc cập nhật sai có thể được replicate sang các bản sao.
- Theo dõi replication lag, tình trạng election, dung lượng oplog, storage và latency để hiểu độ an toàn thực tế của hệ thống.

## 4. Sharded cluster: phân phối dữ liệu và tải ngang nhiều shard

### 4.1. Vì sao cần sharding?

Khi một tập dữ liệu và workload vượt khả năng hợp lý của một nhóm máy, chỉ bổ sung secondary không giải quyết được giới hạn lưu trữ ở mỗi thành viên. **Sharding** phân vùng collection thành nhiều phần dữ liệu và phân phối chúng qua các **shard**.

~~~text
              Java / Spring Boot / Application
                            |
                        +--------+
                        | mongos |  <-- Query router
                        +--------+
                          /  |  \
                         /   |   \
                +---------+ +---------+ +---------+
                | Shard 1 | | Shard 2 | | Shard 3 |
                | RS A    | | RS B    | | RS C    |
                +---------+ +---------+ +---------+
                     |           |           |
                  Data A      Data B      Data C

                +---------------------------+
                | Config Server Replica Set |
                | Routing / sharding config |
                +---------------------------+
~~~

Ba nhóm thành phần:

1. **Shards:** lưu dữ liệu thực tế. Trong hệ thống chịu lỗi, mỗi shard là một replica set, tức mỗi phần dữ liệu lại được replicate giữa các node của shard đó.
2. **Config Server Replica Set (CSRS):** lưu metadata và cấu hình phân vùng để cluster định tuyến, quản lý phân phối dữ liệu. Đây là thành phần trọng yếu, không phải kho dữ liệu nghiệp vụ thay cho shard.
3. **mongos routers:** nhận yêu cầu từ ứng dụng và định tuyến tới shard phù hợp, đồng thời tổng hợp kết quả khi truy vấn nhiều shard. Router không giữ toàn bộ tập dữ liệu như mongod.

Từ góc nhìn ứng dụng, cluster vẫn là một hệ MongoDB logic; phần lớn thao tác CRUD dùng cú pháp quen thuộc. Tuy nhiên hiệu năng phụ thuộc lớn vào cách query liên quan đến **shard key**.

### 4.2. Shard key và định tuyến truy vấn

**Shard key** là một hoặc nhiều field dùng để xác định cách phân phối document của collection. Một shard key tốt cần xét đồng thời:

- **Cardinality:** có đủ nhiều giá trị phân biệt để chia dữ liệu hữu ích.
- **Distribution:** tránh phần lớn ghi/đọc dồn vào một shard.
- **Query patterns:** các truy vấn quan trọng thường có điều kiện trên shard key để router định tuyến hẹp.
- **Growth và tính ổn định:** xét dữ liệu sẽ tăng và thay đổi như thế nào, không chỉ snapshot hiện tại.

Minh họa collection **orders** có shard key theo **customerId**:

~~~text
db.orders.find({ customerId: "CUS-1042" })
         |
         +-- Có shard key --> mongos xác định shard mục tiêu

db.orders.find({ status: "PAID" })
         |
         +-- Thiếu shard key --> có thể phải truy vấn nhiều shard
~~~

Truy vấn **targeted** hướng đến shard liên quan thường tiết kiệm tài nguyên hơn. Truy vấn **scatter-gather** gửi đến nhiều shard rồi tập hợp kết quả có thể tăng độ trễ và chi phí khi cluster phát triển; kết quả thực tế còn tùy index và query plan.

Hai cách phân phối phổ biến:

| Kiểu shard key | Mô tả | Phù hợp / lưu ý |
|---|---|---|
| **Ranged** | Phân vùng theo khoảng giá trị của shard key. | Thuận lợi cho một số truy vấn khoảng; field tăng đơn điệu có thể gây hotspot ghi nếu thiết kế không tốt. |
| **Hashed** | Sử dụng giá trị băm của shard key để phân phối. | Có thể trải đều hơn với một số kiểu giá trị/ghi; không giữ tính liên tục của các khoảng giá trị gốc. |

**Hashed không tự bảo đảm tải cân bằng trong mọi tình huống**; ví dụ một khách hàng có lượng yêu cầu vượt trội vẫn có thể làm nóng shard chứa dữ liệu của khách hàng đó.

### 4.3. Chunk/range và balancer

MongoDB quản lý dữ liệu được sharding theo các **khoảng shard key**. Metadata cho phép xác định shard sở hữu từng khoảng; hệ thống có cơ chế di chuyển dữ liệu giữa shard để hỗ trợ cân bằng. Tài liệu hoặc phiên bản MongoDB có thể dùng các thuật ngữ như **chunks** và **ranges**.

Balancer giúp cải thiện phân bố dữ liệu khi đủ điều kiện nhưng không thay thế thiết kế shard key. Một shard key có phân bố truy cập lệch nghiêm trọng có thể tạo nút thắt ngay cả khi dung lượng trên các shard tương đối cân bằng. Việc thêm shard cũng không lập tức khiến mọi loại truy vấn tăng tốc tuyến tính.

### 4.4. Ví dụ thao tác trên cluster đã cấu hình

Các lệnh dưới đây phải thực hiện qua **mongos** sau khi cluster và các shard đã được quản trị viên thiết lập. Ví dụ dùng hashed shard key cho collection **sales.orders**:

~~~javascript
use sales

db.orders.createIndex({ customerId: "hashed" })

sh.shardCollection("sales.orders", { customerId: "hashed" })

sh.status()
~~~

Trong thực tế, cần xem điều kiện của collection hiện có, index, uniqueness, cấu hình cluster và yêu cầu của phiên bản MongoDB trước khi bật sharding. Việc tạo index và chọn shard key là **quyết định thiết kế**; không nên áp dụng ví dụ vào dữ liệu production khi chưa đo workload.

Chuỗi kết nối khi tự vận hành thường trỏ đến **một hoặc nhiều mongos**:

~~~text
mongodb://router1.example.net:27017,router2.example.net:27017/sales
~~~

Ứng dụng không cần tự đoán document đang ở shard nào. Truy cập trực tiếp một shard để thực hiện thao tác nghiệp vụ thông thường sẽ bỏ qua định tuyến toàn cluster và có thể dẫn đến hành vi sai mong đợi.

### 4.5. Rủi ro và chi phí bổ sung

Sharded cluster làm tăng số thành phần phải quản lý: router, config servers, nhiều replica sets, kết nối mạng, giám sát, balancing và quá trình nâng cấp. Các giao dịch liên quan nhiều shard có thể phát sinh **distributed transactions** với chi phí cao hơn giao dịch chỉ trong một shard. Thiết kế index, aggregation, phân trang, phân tích query plan và tính cục bộ dữ liệu trở nên đặc biệt quan trọng.

Sharding phù hợp khi đã có bằng chứng về **giới hạn lưu trữ hoặc throughput** và một mô hình shard key tốt. Nếu mục tiêu chính là chịu lỗi cho một workload chưa quá lớn, bắt đầu bằng replica set thường đơn giản hơn.

## 5. MongoDB Atlas: dịch vụ MongoDB được quản lý trên đám mây

### 5.1. Atlas nằm ở tầng nào?

**MongoDB Atlas** là dịch vụ cơ sở dữ liệu trên cloud do MongoDB vận hành. Khi tạo deployment, người dùng chọn cấu hình tài nguyên, vùng đặt dữ liệu và các đặc điểm liên quan; Atlas hỗ trợ nhiều mô hình triển khai và các tính năng vận hành tùy loại deployment và gói dịch vụ.

~~~text
                       Application
                            |
               TLS + Driver connection
                            |
                    MongoDB Atlas
           +--------------------------------+
           | MongoDB deployment            |
           |  - Replica set, hoặc           |
           |  - Sharded cluster             |
           |                                |
           | Atlas management layer         |
           |  - Provisioning                |
           |  - Monitoring / alerts         |
           |  - Security / networking       |
           |  - Backups (theo gói/cấu hình) |
           |  - Scaling / maintenance       |
           +--------------------------------+
                    Cloud provider
~~~

Atlas **không bỏ qua các nguyên lý replica set và sharding**. Một cluster Atlas vẫn có primary/secondary hoặc shards tùy cấu hình. Khác biệt lớn là Atlas đảm nhận nhiều công việc triển khai và vận hành mà đội ngũ phải tự làm khi chạy MongoDB trên máy chủ riêng.

### 5.2. Quy trình kết nối cơ bản

1. Tạo **organization/project** phù hợp và tạo deployment MongoDB Atlas ở cloud provider/region mong muốn.
2. Tạo **database user** với quyền tối thiểu cần thiết. Tài khoản quản trị Atlas và database user là hai phạm vi xác thực khác nhau.
3. Cấu hình **network access** cho ứng dụng, ví dụ IP access list hoặc kết nối private network nếu deployment hỗ trợ. Không mở rộng quyền truy cập tùy tiện.
4. Lấy connection string từ Atlas, thay username/password đúng cách và lưu thông tin bí mật trong secret manager hoặc biến môi trường.
5. Kết nối bằng MongoDB Driver/mongosh, sau đó xác nhận CRUD, độ trễ, cảnh báo và chính sách sao lưu.

Ví dụ **mẫu** URI dạng DNS seed list, phải thay bằng địa chỉ thực tế từ Atlas:

~~~text
mongodb+srv://app_user:<encoded-password>@<cluster-host>/shop?retryWrites=true&w=majority
~~~

Đối với **mongodb+srv**, driver tra cứu DNS SRV/TXT để lấy thông tin thành viên và các tùy chọn kết nối tương ứng; không nên tự gán các cổng máy chủ giống URI thông thường. Mật khẩu chứa ký tự đặc biệt trong URI cần được **percent-encode**. Tránh đưa credential vào source code, log hoặc Git.

### 5.3. Atlas hỗ trợ gì và vẫn cần tự quyết định gì?

| Atlas hỗ trợ quản lý | Đội phát triển vẫn phải chịu trách nhiệm |
|---|---|
| Cấp phát và duy trì hạ tầng MongoDB tùy loại deployment. | Chọn region, cấu hình tài nguyên, ngân sách và yêu cầu độ trễ. |
| Công cụ monitoring, metrics và alerting. | Xác định SLO, ngưỡng cảnh báo và xử lý sự cố phía ứng dụng. |
| Tùy chọn backup/restore, bảo vệ dữ liệu theo tier và cấu hình. | Kiểm tra khả năng restore thực tế, retention, RPO/RTO và quyền truy cập backup. |
| Cơ chế network, xác thực, mã hóa và tích hợp cloud. | Thiết kế least privilege, network boundary, quản trị secrets và truy cập ứng dụng. |
| Tùy chọn mở rộng deployment. | Thiết kế schema, index, query, shard key và capacity theo workload. |

Atlas có các loại deployment với hạn mức và khả năng khác nhau; **không mặc định** mọi tier đều hỗ trợ cùng một mức backup, scaling, private networking, sharding hoặc high availability. Khi đưa vào production phải kiểm tra tài liệu, giới hạn và chi phí của **gói đang dùng tại thời điểm triển khai**.

### 5.4. Khi nào chọn Atlas?

Atlas hữu ích khi đội phát triển muốn tập trung vào nghiệp vụ và giao bớt vận hành hạ tầng MongoDB cho dịch vụ quản lý. Tuy vậy, vẫn phải tính đến **chi phí theo tài nguyên/lưu lượng**, vị trí dữ liệu, yêu cầu tuân thủ, độ trễ giữa ứng dụng và database, phương án khôi phục cũng như nguy cơ phụ thuộc dịch vụ cloud.

**Self-managed MongoDB** có thể phù hợp khi tổ chức có yêu cầu triển khai on-premises, hạn chế vị trí lưu trữ hoặc đã sở hữu năng lực vận hành database đáng tin cậy. Cả hai hướng đều dùng cùng nền tảng khái niệm MongoDB; lựa chọn phụ thuộc yêu cầu hệ thống và khả năng vận hành, không chỉ vào số lượng document.

## 6. So sánh nhanh bốn cách tiếp cận

| Tiêu chí | Standalone | Replica set | Sharded cluster | Atlas |
|---|---|---|---|---|
| Bản chất | Một server MongoDB độc lập. | Nhiều bản sao của cùng dữ liệu. | Chia dữ liệu giữa nhiều shard, thường replicate từng shard. | Dịch vụ quản lý deployment MongoDB trên cloud. |
| Mục tiêu chính | Đơn giản, học tập, phát triển. | High availability và khả năng phục hồi lỗi node. | Mở rộng ngang dung lượng và workload. | Giảm gánh nặng vận hành, cung cấp tiện ích cloud. |
| Primary/secondary | Không có election. | Có primary/secondary. | Mỗi shard thường là một replica set riêng. | Phụ thuộc topology của deployment Atlas. |
| Phân vùng dữ liệu qua shard | Không. | Không. | Có. | Có nếu chọn cấu hình sharded cluster phù hợp. |
| Mất một node | Có thể mất toàn bộ dịch vụ. | Có thể failover nếu còn quorum và thành viên đủ điều kiện. | Phụ thuộc tính sẵn sàng của từng shard, router và config server. | Phụ thuộc loại deployment, vùng và cấu hình khả dụng. |
| Vận hành | Nhẹ nhất. | Cần quản trị replication/election. | Phức tạp nhất khi self-managed. | Atlas quản lý nhiều tác vụ, ứng dụng vẫn phải quản lý dữ liệu và truy cập. |
| Thích hợp | Lab, local development, workload độc lập chấp nhận downtime. | Phần lớn ứng dụng cần độ sẵn sàng cao. | Workload lớn có chiến lược phân vùng rõ ràng. | Đội ngũ muốn MongoDB được quản lý trên cloud. |

Một cách diễn đạt đúng hơn là có **hai trục lựa chọn**:

- **Trục topology:** standalone → replica set → sharded cluster, theo nhu cầu chịu lỗi và mở rộng.
- **Trục vận hành:** tự quản lý (**self-managed**) hoặc sử dụng dịch vụ được quản lý (**Atlas**), theo yêu cầu hạ tầng và nhân sự.

Ví dụ: **Replica set trên Atlas** và **replica set tự quản lý** cùng dùng cơ chế replication; nhưng quy trình tạo máy, monitoring, backup và nâng cấp khác nhau. **Sharded cluster trên Atlas** vẫn phải có shard key tốt.

## 7. Chọn kiến trúc từ yêu cầu thực tế

### 7.1. Một cây quyết định đơn giản

~~~mermaid
flowchart TD
    A["Bắt đầu: cần triển khai MongoDB"] --> B{"Chỉ học tập hoặc môi trường local?"}
    B -->|Có| C["Standalone local"]
    B -->|Không| D{"Ứng dụng cần tự phục hồi lỗi node?"}
    D -->|Có| E["Replica set làm nền tảng"]
    D -->|Không| F["Đánh giá rủi ro downtime; standalone chỉ khi chấp nhận được"]
    E --> G{"Dữ liệu / tải cần chia trên nhiều shard?"}
    G -->|Có, có shard key phù hợp| H["Sharded cluster với replica set mỗi shard"]
    G -->|Chưa| I["Duy trì replica set và tối ưu schema/index/query"]
    C --> J{"Muốn dịch vụ cloud được quản lý?"}
    F --> J
    H --> J
    I --> J
    J -->|Có| K["Chọn deployment phù hợp trên Atlas"]
    J -->|Không| L["Vận hành MongoDB self-managed"]
~~~

Không tồn tại một con số lượng dữ liệu hay số request cố định áp dụng cho mọi hệ thống để quyết định khi nào phải sharding. Hiệu quả phụ thuộc nhiều yếu tố: kích thước document, index, phân bố truy vấn, read/write ratio, tốc độ tăng dữ liệu, phần cứng, latency và mức chịu lỗi mong muốn.

### 7.2. Ba tình huống minh họa

**Tình huống A — Ứng dụng học MongoDB:** sinh viên viết CRUD và aggregation, dữ liệu nhỏ, không yêu cầu chạy liên tục. Chạy standalone local để giảm thành phần vận hành; khi học election và replication thì tạo replica set ba tiến trình để quan sát hành vi.

**Tình huống B — API đặt hàng cần hoạt động liên tục:** dữ liệu còn vừa với một nhóm máy, nhưng mất một server không được làm ứng dụng ngừng lâu. Replica set với nhiều thành viên mang dữ liệu, write concern/read concern phù hợp và backup độc lập là nền tảng hợp lý. Chưa cần sharding nếu chưa có bằng chứng nút thắt.

**Tình huống C — Dịch vụ nhiều tenant tăng trưởng mạnh:** tập dữ liệu, index hoặc lưu lượng ghi lớn vượt khả năng mở rộng dọc phù hợp. Kiểm tra workload theo tenant, độ lệch tenant lớn/nhỏ và các truy vấn liên tenant; sau đó đánh giá shard key, phân phối tải và chi phí cross-shard trước khi quyết định sharded cluster. Nếu vận hành trên cloud và muốn giảm trách nhiệm hạ tầng, có thể dùng Atlas.

## 8. Các khác biệt liên quan đến ứng dụng và driver

Ứng dụng Java/Spring Data MongoDB vẫn làm việc với **database, collection, document, query, index và aggregation** ở cả ba topology. Điểm thay đổi rõ nhất là **connection string**, chính sách nhất quán và hành vi khi cluster thay đổi trạng thái.

| Triển khai | Dạng địa chỉ kết nối điển hình |
|---|---|
| Standalone | mongodb://db-host:27017/appdb |
| Replica set | mongodb://db1:27017,db2:27017,db3:27017/appdb?replicaSet=rs0 |
| Sharded cluster tự quản lý | mongodb://mongos1:27017,mongos2:27017/appdb |
| Atlas | mongodb+srv://user:password@cluster-host/appdb |

Các URI trên là **mẫu mô tả**, không phải endpoint thật. Trong ứng dụng, cấu hình từ biến môi trường hoặc secret manager; tránh đưa username/password vào repository.

Khi xây dựng API có ghi dữ liệu, cần quan tâm:

1. **Retry:** driver hỗ trợ những cơ chế retry nhất định, nhưng nghiệp vụ nên sử dụng idempotency key hoặc ràng buộc unique khi có nguy cơ gửi trùng request.
2. **Timeout:** đặt server selection timeout và timeout thao tác theo SLO; failover có thể khiến một số request thất bại tạm thời.
3. **Index:** query không có index thích hợp có thể chậm trên standalone, replica set lẫn sharded cluster. Thêm server không chữa được mọi full collection scan.
4. **Atomicity:** cập nhật một document có tính nguyên tử theo mức bảo đảm của MongoDB; nghiệp vụ trải nhiều document cần cân nhắc mô hình dữ liệu và transaction khi cần.
5. **Observability:** xem latency, connection pool, slow queries, replication lag, cache/storage và phân bố tải shard; các chỉ số cần đọc trong ngữ cảnh workload.

Ví dụ: API tạo đơn hàng không nên cho phép cùng một **orderId** được chèn hai lần khi client retry:

~~~javascript
db.orders.createIndex({ orderId: 1 }, { unique: true })
~~~

Một unique index là cơ chế bảo vệ dữ liệu hữu ích trong nhiều trường hợp. Trong sharded collection, tính hợp lệ và phạm vi áp dụng của unique index còn phụ thuộc quy tắc shard key; phải kiểm tra ràng buộc trước khi thiết kế uniqueness toàn hệ thống.

## 9. Khả năng chịu lỗi, backup và bảo mật

### Replication không thay thế backup

Nếu ứng dụng vô tình xóa collection hoặc thực hiện bản cập nhật sai, các thay đổi có thể được replicate tới các secondary. Vì vậy cần có **backup độc lập**, retention, khả năng point-in-time recovery khi cần và quy trình thử restore định kỳ. Đặt mục tiêu **RPO** (mức mất dữ liệu chấp nhận) và **RTO** (thời gian phục hồi chấp nhận) trước khi chọn công cụ.

### Election không tự bảo đảm zero downtime

Khi primary mất kết nối, ứng dụng có thể mất vài giây hoặc lâu hơn tùy điều kiện mạng, timeout và election; không nên tự đặt cam kết thời gian failover chỉ vì replica set có ba node. Cần thử nghiệm outage ở môi trường tương ứng với sản xuất và kiểm tra ứng dụng có xử lý lỗi tạm thời hợp lý không.

### Sharding không tự bảo đảm truy vấn nhanh

Một truy vấn thiếu shard key có thể phải tới nhiều shard; một pipeline aggregation có thể tốn chi phí giao tiếp và xử lý phân tán. Tốc độ còn tùy query plan, index, phân bố dữ liệu và giới hạn tài nguyên. Shard key nên được chọn từ workload đo được thay vì chỉ từ tên field có vẻ hợp lý.

### Biện pháp bảo vệ cơ bản

- Bật authentication và cấp quyền tối thiểu cho application user; tách quyền quản trị với quyền đọc/ghi ứng dụng.
- Sử dụng TLS cho kết nối qua mạng; giới hạn IP/network và ưu tiên kết nối riêng nếu phù hợp.
- Không ghi database URI chứa mật khẩu vào log, file mẫu có thể commit hoặc thông báo lỗi gửi ra client.
- Bảo vệ backup và khóa truy cập tương đương dữ liệu chính.
- Theo dõi dung lượng đĩa, tốc độ tăng dữ liệu, tình trạng replication, cấu hình cảnh báo và khả năng khôi phục.
- Với hệ thống nhiều khu vực, cân nhắc data residency, độ trễ mạng, topology và chính sách đọc/ghi trước khi phân bổ node.

## 10. Những nhầm lẫn phổ biến

**“Có ba node tức là dữ liệu được chia đều làm ba phần.”** Sai đối với replica set: mỗi thành viên mang dữ liệu giữ một bản sao của cùng tập dữ liệu logic. Chỉ sharding mới chia các phần dữ liệu giữa shard.

**“Replica set tự động tăng gấp ba khả năng ghi.”** Sai: ghi thông thường đi vào primary và được replicate. Replica set chủ yếu phục vụ khả năng sẵn sàng; khả năng đọc phụ thuộc chính sách read preference và yêu cầu nhất quán.

**“Thêm shard là mọi request nhanh hơn.”** Không nhất thiết. Query thiếu shard key, phân bố dữ liệu lệch, hot tenant hoặc aggregate cross-shard có thể không cải thiện, thậm chí làm tăng chi phí.

**“Atlas là cơ sở dữ liệu khác MongoDB.”** Không: Atlas cung cấp MongoDB dưới mô hình được quản lý và bổ sung công cụ/tính năng dịch vụ. Data model và các khái niệm replication/sharding vẫn là MongoDB.

**“Đã có replica set thì không cần backup.”** Sai: replication sao chép cả thay đổi hợp lệ lẫn thao tác nhầm. Backup phục vụ khôi phục về thời điểm/bản dữ liệu độc lập.

**“Đọc secondary luôn nhận dữ liệu mới nhất.”** Sai: replication bất đồng bộ có thể tạo lag; ứng dụng phải chọn read preference và read concern theo yêu cầu nghiệp vụ.

## 11. Ghi nhớ kiến trúc qua một ví dụ

Giả sử collection **orders** chứa đơn hàng của nhiều khách:

- Với **standalone**, toàn bộ collection nằm trên một mongod. Nếu mongod dừng, API không đọc/ghi được.
- Với **replica set ba thành viên**, mỗi thành viên mang bản sao của collection **orders**. Primary nhận ghi; secondaries áp dụng oplog và có thể tham gia election. Khi primary mất, hệ thống có thể chọn primary mới nếu đủ đa số.
- Với **sharded cluster ba shard**, các khoảng shard key của **orders** được phân phối qua ba shard. Ví dụ một document thuộc shard 2, nhưng trong replica set của shard 2 lại có nhiều bản sao của chính document đó.
- Với **Atlas**, đội phát triển có thể chạy replica set hoặc sharded cluster tương ứng trên cloud và sử dụng công cụ vận hành của Atlas theo gói đã chọn.

~~~text
                REPLICATION                     SHARDING
        +---------------------------+    +---------------------------+
        | Node A: orders = A+B+C    |    | Shard 1: orders = A       |
        | Node B: orders = A+B+C    |    | Shard 2: orders = B       |
        | Node C: orders = A+B+C    |    | Shard 3: orders = C       |
        +---------------------------+    +---------------------------+
         Dữ liệu được nhân bản             Dữ liệu được phân vùng

              SHARDING + REPLICATION
        +-----------------------------------------------+
        | Shard 1: RS (A, A, A)                        |
        | Shard 2: RS (B, B, B)                        |
        | Shard 3: RS (C, C, C)                        |
        +-----------------------------------------------+
        Mỗi phần dữ liệu được sao chép trong shard riêng
~~~

## 12. Câu hỏi tự kiểm tra

1. Một ứng dụng có yêu cầu chịu lỗi máy chủ nhưng dữ liệu vẫn vừa trên một nhóm máy: vì sao replica set thường là bước đầu phù hợp hơn sharded cluster?
2. Vì sao một replica set ba node có thể cần election, trong khi standalone không có bước này?
3. Nếu client ghi với **w: 1** rồi primary mất ngay lập tức, nguy cơ nào có thể xảy ra?
4. Truy vấn chỉ theo **status** sẽ có rủi ro gì khi **customerId** là shard key?
5. Atlas giải quyết những công việc vận hành nào, và vì sao Atlas vẫn cần schema, index, backup policy và capacity planning?
6. Tại sao ba mongod chạy trên cùng laptop là bài lab replica set hữu ích nhưng không đại diện cho high availability trước lỗi mất máy?

**Tài liệu tra cứu chính thức:**

- MongoDB Manual: https://www.mongodb.com/docs/manual/
- MongoDB Replication: https://www.mongodb.com/docs/manual/replication/
- MongoDB Sharding: https://www.mongodb.com/docs/manual/sharding/
- MongoDB Atlas Documentation: https://www.mongodb.com/docs/atlas/

Trong các bài tiếp theo, có thể đi sâu vào BSON/schema design, indexing, aggregation, replication, sharding và transaction. Ở cấp tổng quan, điểm cần hiểu là **standalone đơn giản hóa triển khai; replica set giải quyết độ sẵn sàng; sharding giải quyết phân phối dữ liệu/tải; Atlas cung cấp lựa chọn vận hành MongoDB trên cloud**.
