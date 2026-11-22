# Vai trò của mongod, mongos và config server trong kiến trúc MongoDB

Khi sử dụng MongoDB trên một máy đơn, ứng dụng thường kết nối đến một tiến trình **mongod** để đọc và ghi dữ liệu. Khi hệ thống cần tính sẵn sàng cao, nhiều tiến trình **mongod** có thể được tổ chức thành một **replica set**. Khi cần phân phối tập dữ liệu trên nhiều nhóm máy, MongoDB sử dụng **sharding**: tiến trình **mongos** định tuyến yêu cầu, các **mongod** của những shard lưu dữ liệu, còn **config server** duy trì metadata để cả cụm biết dữ liệu đang ở đâu.

Ba tên gọi có vai trò khác nhau, nhưng không phải ba loại database độc lập. Đặc biệt, **config server vẫn chạy bằng tiến trình mongod**, với vai trò cấu hình chuyên biệt; **mongos** là một tiến trình định tuyến khác với **mongod**.

## 1. Bắt đầu từ ba kiểu triển khai

Kiến trúc MongoDB thường được tiếp cận theo ba mức:

| Kiểu triển khai | Thành phần cốt lõi | Mục tiêu chính |
| --- | --- | --- |
| **Standalone** | Một mongod | Học tập, thử nghiệm hoặc nhu cầu đơn giản |
| **Replica set** | Nhiều mongod cùng giữ bản sao của một tập dữ liệu | Dự phòng, bầu primary, phục hồi khi thành viên lỗi |
| **Sharded cluster** | Các shard gồm mongod, một hoặc nhiều mongos, cùng config server replica set | Phân tán dữ liệu và tải xử lý giữa nhiều shard |

Sơ đồ rút gọn:

~~~text
Standalone
Ứng dụng ──> mongod ──> dữ liệu

Replica set
                    ┌──> mongod PRIMARY
Ứng dụng / driver ──┤
                    ├──> mongod SECONDARY
                    └──> mongod SECONDARY

Sharded cluster
                       ┌──> Shard A: replica set mongod
Ứng dụng ──> mongos ───┤
                       └──> Shard B: replica set mongod
                           ▲
mongos <── metadata ── Config Server Replica Set (mongod)
~~~

Mục đích của sơ đồ là phân biệt **đường đi của yêu cầu** và **nơi lưu dữ liệu**. Trong replica set, các mongod chứa các bản sao của cùng tập dữ liệu. Trong sharded cluster, những shard khác nhau có thể giữ những phần dữ liệu khác nhau; bên trong từng shard, replica set lại giúp sao chép phần dữ liệu đó để dự phòng.

**Replication** và **sharding** giải quyết hai bài toán riêng: replication tăng khả năng chịu lỗi của một tập dữ liệu; sharding phân phối dữ liệu để tăng khả năng mở rộng theo chiều ngang. Một sharded cluster sản xuất thường dùng cả hai.

## 2. mongod: tiến trình database thực sự xử lý và lưu dữ liệu

**mongod** là tiến trình máy chủ MongoDB. Đây là thành phần tiếp nhận các thao tác database, thực thi truy vấn, quản lý collection/index và phối hợp với storage engine để lưu trữ dữ liệu trên đĩa.

Một mongod thường đảm nhiệm:

- Quản lý database, collection, document và index do tiến trình đó phụ trách.
- Thực thi thao tác đọc, ghi, cập nhật, xóa và một phần xử lý aggregation.
- Sử dụng storage engine, phổ biến là **WiredTiger**, để quản lý dữ liệu, cache và cơ chế lưu trữ.
- Phối hợp với cơ chế journal, checkpoint và các tính năng bảo đảm độ bền dữ liệu theo cấu hình.
- Tham gia replication và election nếu là thành viên của replica set.
- Phục vụ một phần dữ liệu phân tán nếu được cấu hình là thành viên của shard.

Trong triển khai standalone, mongod là cả điểm kết nối và nơi thực thi truy vấn. Trong replica set, driver biết những thành viên mongod của cụm; yêu cầu ghi thông thường được gửi đến **primary**, còn nơi thực hiện đọc tùy theo **read preference** và tính sẵn sàng.

### 2.1. mongod trong replica set

Ví dụ replica set **rsBooks** gồm ba tiến trình:

~~~text
Replica set rsBooks
├── mongod books-db-1  PRIMARY
├── mongod books-db-2  SECONDARY
└── mongod books-db-3  SECONDARY
~~~

Primary nhận các thao tác ghi thông thường; các secondary tái hiện thay đổi thông qua cơ chế replication. Khi primary lỗi, những thành viên đủ điều kiện có thể bầu primary mới nếu replica set còn đáp ứng điều kiện bầu cử.

Cần phân biệt **primary/secondary** với **mongod/mongos**:

- **mongod** là loại tiến trình.
- **primary** và **secondary** là vai trò của một thành viên trong replica set tại thời điểm nhất định.
- Một mongod có thể chuyển từ secondary sang primary sau cuộc bầu cử; bản thân tiến trình vẫn là mongod.
- mongos không trở thành primary hoặc secondary của replica set.

Replica set không tự tạo thêm nhiều shard. Cả nhóm này vẫn cùng quản lý **một tập dữ liệu logic**.

### 2.2. mongod trong shard

Một **shard** là đơn vị chứa một phần dữ liệu của sharded cluster. Với mô hình triển khai hiện đại, shard được tổ chức thành replica set. Ví dụ:

~~~text
Shard A = rsShardA
  ├── mongod A1 PRIMARY
  ├── mongod A2 SECONDARY
  └── mongod A3 SECONDARY

Shard B = rsShardB
  ├── mongod B1 PRIMARY
  ├── mongod B2 SECONDARY
  └── mongod B3 SECONDARY
~~~

Nếu collection được sharding, các document của collection đó có thể phân bố giữa Shard A và Shard B theo **shard key** và metadata phân vùng.

Hai shard không phải hai bản sao giống nhau. Ngược lại, **A1/A2/A3** sao chép phần dữ liệu do Shard A sở hữu; **B1/B2/B3** sao chép phần dữ liệu do Shard B sở hữu.

Khi một shard nhận yêu cầu từ mongos, mongod thuộc shard thực sự đọc index, truy cập dữ liệu và thực thi phần truy vấn được giao. mongos không thay thế storage engine hoặc bộ thực thi truy vấn của mongod.

### 2.3. Một số thuật ngữ dễ lẫn

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| mongod | Tiến trình máy chủ database |
| Replica set | Nhóm mongod sao chép một tập dữ liệu |
| Primary | Thành viên replica set nhận các thao tác ghi thông thường |
| Secondary | Thành viên đồng bộ bản sao dữ liệu từ replication |
| Shard | Đơn vị lưu một phần dữ liệu của sharded cluster, thường là cả một replica set |
| mongos | Tiến trình định tuyến đến shard |
| Config server | Vai trò mongod chuyên giữ metadata cho sharded cluster; có thể kiêm vai trò shard trong cấu hình hỗ trợ |

## 3. mongos: cổng truy cập và bộ định tuyến của sharded cluster

**mongos** (MongoDB Query Router) là tiến trình cung cấp giao diện truy cập logic của **toàn bộ sharded cluster** cho ứng dụng.

Thay vì ứng dụng tự biết collection đang nằm trên máy nào, ứng dụng kết nối đến một hoặc nhiều mongos. Router xác định shard liên quan, chuyển yêu cầu, thu thập kết quả khi cần và trả lại kết quả cho client.

~~~text
           Yêu cầu: tìm đơn hàng ORD-1001
Ứng dụng -----------------------------------> mongos
                                               |
                                               | Xem metadata shard
                                               v
                                      Chọn shard đích
                                               |
                                               v
                                          Shard B
                                               |
                                               v
Ứng dụng <---------------------------------- kết quả
~~~

Các nhiệm vụ chính của mongos gồm:

1. Tiếp nhận yêu cầu từ ứng dụng thông qua giao thức MongoDB.
2. Sử dụng metadata về phân bố dữ liệu để quyết định shard nào cần xử lý.
3. Gửi yêu cầu đến các shard liên quan và áp dụng lựa chọn thành viên replica set phù hợp.
4. Kết hợp kết quả khi yêu cầu liên quan đến nhiều shard.
5. Trả kết quả về ứng dụng, khiến sharded cluster trông giống một hệ thống database logic.

**mongos không lưu bền vững document nghiệp vụ.** Nó giữ một số thông tin định tuyến dưới dạng cache và có thể được khởi chạy nhiều instance để tăng tính sẵn sàng. Cache metadata không biến mongos thành nơi lưu dữ liệu chính.

### 3.1. Định tuyến theo shard key

Giả sử collection **shop.orders** được phân vùng dựa trên shard key **customerId**. Để hình dung, giả sử metadata mô tả ba khoảng giá trị:

~~~text
customerId < 1000          -> Shard A
1000 <= customerId < 2000  -> Shard B
customerId >= 2000         -> Shard C
~~~

Đây là **ví dụ minh họa về range sharding**, không phải quy tắc phân vùng mặc định của MongoDB.

Khi ứng dụng gửi:

~~~javascript
db.orders.find({ customerId: 1450 });
~~~

mongos có thể dựa trên shard key và metadata để hướng truy vấn đến Shard B. Đây là **targeted query**: chỉ những shard cần thiết mới được hỏi.

Ngược lại:

~~~javascript
db.orders.find({ status: "PAID" });
~~~

Nếu điều kiện không giúp xác định shard chứa các document phù hợp, mongos có thể phải gửi yêu cầu tới nhiều hoặc toàn bộ shard. Đây là mô hình **scatter/gather** hoặc **broadcast query**.

| Kiểu truy vấn | Đường đi điển hình | Hệ quả |
| --- | --- | --- |
| Có điều kiện shard key đủ để khoanh vùng | Một hoặc một nhóm nhỏ shard | Giảm số nơi phải truy vấn |
| Không xác định được shard đích | Nhiều hoặc tất cả shard | Tăng công việc phân tán, có thể tăng độ trễ |
| Truy vấn sort/aggregation nhiều shard | Shard thực thi phần việc, kết quả được kết hợp ở nơi phù hợp | Có thêm chi phí điều phối và kết hợp |

Không phải cứ có shard key là chắc chắn chỉ chạm một shard: hiệu quả còn phụ thuộc loại shard key, biểu thức truy vấn và cách dữ liệu đang phân bố. Với **hashed sharding**, một số truy vấn dạng khoảng trên giá trị gốc cũng có đặc tính định tuyến khác với range sharding.

### 3.2. mongos lấy vị trí dữ liệu ở đâu?

mongos lấy metadata phân vùng từ **config servers** rồi lưu cache những phần cần dùng. Ví dụ metadata cho biết:

- Collection nào được sharding và sử dụng shard key nào.
- Những khoảng hoặc đơn vị dữ liệu nào thuộc shard nào.
- Những shard nào đang tham gia cụm.
- Metadata nào đã thay đổi sau thao tác phân phối lại dữ liệu.

Khi topology hoặc vị trí dữ liệu thay đổi, mongos cần làm mới thông tin định tuyến. Vì vậy cách diễn đạt “mongos biết mọi document nằm ở đâu” chỉ là lối nói đơn giản: thông thường nó định tuyến bằng **metadata về collection, shard key và phạm vi dữ liệu**, chứ không giữ danh sách riêng cho từng document.

### 3.3. Một hay nhiều mongos?

Có thể chạy nhiều mongos để tránh phụ thuộc vào một router duy nhất:

~~~text
                    ┌──> mongos-1 ──┐
Ứng dụng / driver ───┤              ├──> Các shard
                    └──> mongos-2 ──┘
~~~

Các mongos không cần tạo thành replica set và không bầu primary chung. Chúng có thể cùng truy cập metadata của một sharded cluster; driver hoặc tầng kết nối có thể sử dụng nhiều router được cấu hình.

Mongos là điểm truy cập dịch vụ rất quan trọng. Nếu tất cả router mà ứng dụng có thể dùng đều không truy cập được, ứng dụng sẽ không thể tiếp tục giao tiếp với cụm qua đường kết nối đó, dù dữ liệu trên các shard còn nguyên.

### 3.4. Không truy cập thẳng shard để thay mongos

Kết nối trực tiếp đến một mongod của shard có thể phục vụ một số thao tác quản trị chuyên biệt, nhưng **không phải cách truy cập nghiệp vụ bình thường** trong sharded cluster.

Kết nối trực tiếp có thể chỉ nhìn thấy **một phần** dữ liệu của collection đã sharding, đồng thời bỏ qua cơ chế định tuyến và điều phối của toàn cluster. Với ứng dụng, hãy kết nối qua mongos khi làm việc với sharded cluster.

## 4. Config server: nơi lưu bản đồ và trạng thái của sharded cluster

**Config server** là thành phần quản lý **cluster metadata**: thông tin mô tả topology, dữ liệu được phân bố thế nào và các cấu hình cần thiết để các thành phần phối hợp với nhau.

Config server **không phải một binary hoàn toàn riêng** như mongos. Nó chạy bằng **mongod** được cấu hình vai trò **config server**. Nhiều config server được ghép thành **Config Server Replica Set (CSRS)**.

Ví dụ:

~~~text
Config Server Replica Set: cfgRS
├── cfg-1: mongod (PRIMARY, config server role)
├── cfg-2: mongod (SECONDARY, config server role)
└── cfg-3: mongod (SECONDARY, config server role)
~~~

Trong mô hình **dedicated config server**, nhóm này dành cho metadata và công việc điều phối của cụm; dữ liệu nghiệp vụ nằm trên các shard riêng.

### 4.1. Metadata bao gồm những gì?

Config servers lưu thông tin như:

- Danh sách các shard của cluster.
- Thông tin database và collection tham gia cluster.
- Cấu hình sharding, shard key và các metadata liên quan.
- Metadata về range/chunk và shard đang sở hữu dữ liệu.
- Lịch sử hoặc trạng thái cần thiết cho một số hoạt động quản trị, điều phối phân vùng.
- Những cấu hình cluster khác, bao gồm thông tin phục vụ xác thực và phân quyền trong mô hình tự quản lý.

Ví dụ khái niệm:

~~~text
Collection: shop.orders
Shard key:  { customerId: 1 }

Metadata:
  Range 1 -> shardA
  Range 2 -> shardB
  Range 3 -> shardC
~~~

Khi một range dữ liệu được di chuyển từ shard này sang shard khác, metadata cần được cập nhật để mongos biết nơi định tuyến các yêu cầu tiếp theo.

Trong MongoDB, metadata của cluster được lưu ở các collection thuộc **database config** trên config servers. Đây là dữ liệu hệ thống nhạy cảm; **không nên tự ý sửa, xóa hoặc chèn document trực tiếp** vào các collection metadata đó.

### 4.2. Tại sao config server phải là replica set?

Nếu metadata mất hoặc không sẵn sàng, các thành phần khó có thể điều phối dữ liệu trên toàn cluster. Vì vậy MongoDB triển khai config servers dưới dạng **replica set**, thường với **ba thành viên** trong môi trường production để có khả năng duy trì majority khi một thành viên hỏng.

Các thay đổi metadata quan trọng cần được ghi và xác nhận với cơ chế đồng thuận phù hợp. Khi CSRS mất primary và không bầu được primary mới, metadata trở thành trạng thái **không thể ghi**; các hoạt động yêu cầu thay đổi metadata như di chuyển hoặc chia range/chunk có thể tạm dừng. Một số thao tác dữ liệu trên shard vẫn có thể hoạt động, tùy trạng thái cluster; nếu toàn bộ config servers không sẵn sàng, cluster có nguy cơ không thể hoạt động bình thường.

Điểm quan trọng là **config servers đảm bảo metadata luôn nhất quán và sẵn sàng**, chứ không trực tiếp thay mongos định tuyến mọi truy vấn.

### 4.3. Dedicated config server và config shard từ MongoDB 8.0

Từ **MongoDB 8.0**, kiến trúc hỗ trợ **config shard**: một replica set có thể đảm nhiệm **đồng thời** vai trò config server **và** shard lưu dữ liệu ứng dụng.

| Kiểu bố trí | Vai trò | Đặc điểm |
| --- | --- | --- |
| **Dedicated config server** | Replica set chuyên giữ metadata cluster | Tách biệt metadata với dữ liệu nghiệp vụ |
| **Config shard** | Replica set giữ metadata và đồng thời là một shard | Có thể giảm số lượng replica set/nút cần vận hành |

Điều này giúp tránh một khẳng định quá đơn giản rằng “config servers tuyệt đối không lưu dữ liệu ứng dụng”. Trong **mô hình dedicated**, chúng không được dùng để lưu dữ liệu nghiệp vụ. Trong **mô hình config shard** được hỗ trợ, cùng các mongod có thể lưu cả metadata và dữ liệu ứng dụng.

Dù lựa chọn nào, cluster vẫn cần có vai trò config server và thông tin định tuyến vẫn phải được quản lý nhất quán. Không nên tự ý biến dedicated config server thành shard bằng thao tác dữ liệu thủ công; việc chuyển chế độ dùng các cơ chế quản trị được MongoDB hỗ trợ.

## 5. Sơ đồ tổng thể: ba thành phần phối hợp thế nào?

Ví dụ kiến trúc sharded cluster có hai router, hai shard replica set và một dedicated CSRS:

~~~text
                  +-----------------------+
                  |      ỨNG DỤNG         |
                  |  Java / Node / Python |
                  +-----------+-----------+
                              |
                     MongoDB driver
                              |
                 +------------+------------+
                 |                         |
           +-----v-----+             +-----v-----+
           | mongos A  |             | mongos B  |
           | Router    |             | Router    |
           +-----+-----+             +-----+-----+
                 |                         |
                 +-------------+-----------+
                               |
                     routing CRUD/query
                               |
              +----------------+----------------+
              |                                 |
        +-----v----------------+        +-------v--------------+
        | Shard A / rsShardA   |        | Shard B / rsShardB   |
        | mongod A1 PRIMARY    |        | mongod B1 PRIMARY    |
        | mongod A2 SECONDARY  |        | mongod B2 SECONDARY  |
        | mongod A3 SECONDARY  |        | mongod B3 SECONDARY  |
        +----------------------+        +----------------------+

                 metadata / topology
              mongos <--------------------> CSRS
                                        +-------------------------+
                                        | cfgRS                   |
                                        | mongod cfg1 PRIMARY     |
                                        | mongod cfg2 SECONDARY   |
                                        | mongod cfg3 SECONDARY   |
                                        +-------------------------+
~~~

Các đường kết nối trong sơ đồ là quan hệ logic. Trong vận hành thực tế, mongos, các shard và CSRS còn có những luồng giao tiếp nội bộ để phát hiện thay đổi topology, quản trị metadata và phối hợp các tác vụ cluster.

Từ sơ đồ, có thể rút ra ba câu phân biệt:

- **mongod của shard lưu và xử lý phần dữ liệu do shard chịu trách nhiệm.**
- **mongos nhận yêu cầu ở cấp cluster và định tuyến tới shard cần thiết.**
- **config server quản lý metadata để những quyết định định tuyến và điều phối cluster có cơ sở nhất quán.**

## 6. Theo dấu một yêu cầu đọc và một thao tác thay đổi dữ liệu

Xét collection **shop.orders** đã được sharding theo **customerId**.

### 6.1. Yêu cầu đọc có shard key

Ứng dụng gửi:

~~~javascript
db.orders.find({ customerId: 1450 });
~~~

Trình tự điển hình:

1. Driver gửi lệnh đến một mongos khả dụng.
2. Mongos xem metadata đang cache để suy ra shard nào quản lý khoảng dữ liệu chứa **customerId = 1450**.
3. Mongos chuyển yêu cầu đến shard đích.
4. Mongod trên shard thực thi truy vấn và sử dụng index khi phù hợp.
5. Kết quả được trả về qua mongos cho ứng dụng.

Nếu metadata thay đổi do phân phối lại dữ liệu, router cần cập nhật thông tin định tuyến. Config server cung cấp metadata làm nguồn tham chiếu cho hoạt động này.

### 6.2. Yêu cầu đọc không định vị được shard

Ứng dụng gửi:

~~~javascript
db.orders.find({ status: "PAID" }).sort({ createdAt: -1 });
~~~

Nếu shard key không cho phép thu hẹp phạm vi, mongos có thể chuyển yêu cầu đến các shard liên quan. Mỗi shard tự xử lý phần dữ liệu của mình; các kết quả được phối hợp để tạo đầu ra đúng với truy vấn.

Phần kết hợp có thể nằm ở mongos hoặc tại một shard tùy loại truy vấn và kế hoạch thực thi, đặc biệt với aggregation. Vì vậy không nên diễn đạt mọi trường hợp là “mongos tự thực hiện toàn bộ phép join/sort/aggregate”.

### 6.3. Thao tác ghi

Ứng dụng gửi một document mới:

~~~javascript
db.orders.insertOne({
  orderNo: "ORD-1001",
  customerId: 1450,
  amount: 850000,
  status: "NEW",
  createdAt: new Date()
});
~~~

Với sharded collection, mongos định tuyến thao tác insert đến shard chịu trách nhiệm cho giá trị shard key của document. Mongod trên shard đích thực thi thao tác ghi; replication của shard sẽ sao chép thay đổi theo cơ chế của replica set.

**Config server không nhận và lưu bản ghi đơn hàng này trong mô hình dedicated config server.** Nó quản lý thông tin về vị trí dữ liệu và cấu hình cluster. Nếu cluster dùng **config shard**, chính shard mang vai trò config server cũng có thể là nơi lưu bản ghi ứng dụng khi metadata phân vùng chỉ định nó.

### 6.4. Khi dữ liệu được di chuyển giữa các shard

Giả sử cluster cần phân phối lại một phạm vi dữ liệu:

~~~text
Trước:  Range X nằm trên Shard A
Sau:    Range X nằm trên Shard B
~~~

Quy trình di chuyển dữ liệu do các thành phần cluster phối hợp thực hiện, với metadata được cập nhật để phản ánh quyền sở hữu mới. Mongos sử dụng metadata mới để hướng yêu cầu tiếp theo đến vị trí đúng.

Đừng hình dung mongos tự đọc từng document từ Shard A rồi lưu toàn bộ vào Shard B như một công cụ copy dữ liệu ứng dụng. Nó là router; việc dịch chuyển dữ liệu là cơ chế quản trị giữa các shard và thành phần điều phối của MongoDB.

## 7. Vai trò của mỗi thành phần khi có sự cố

Một cluster có nhiều thành phần nên cách hệ thống phản ứng tùy thuộc vào thành phần nào bị lỗi.

| Tình huống | Tác động điển hình | Ý nghĩa kiến trúc |
| --- | --- | --- |
| Standalone mongod dừng | Database đó không phục vụ cho tới khi khôi phục | Không có thành viên dự phòng |
| Một secondary mongod trong shard lỗi | Shard có thể vẫn phục vụ nếu primary và điều kiện cần thiết còn sẵn sàng | Replica set cung cấp dự phòng |
| Primary mongod của shard lỗi | Có thể gián đoạn ngắn trong khi bầu primary mới; nếu không đủ điều kiện bầu, ghi bị ảnh hưởng | Replication cần quorum và election |
| Một mongos lỗi | Ứng dụng có thể tiếp tục qua mongos khác nếu được cấu hình và reachable | Router không phải nơi chứa dữ liệu |
| CSRS mất primary nhưng còn khả năng bầu mới | Các thao tác metadata có thể gián đoạn trong thời gian chuyển primary | Metadata phụ thuộc tính sẵn sàng của CSRS |
| CSRS không thể bầu primary | Thao tác cập nhật metadata bị hạn chế; một số truy vấn/ghi dữ liệu có thể vẫn hoạt động tùy trạng thái | Metadata không còn khả năng ghi |
| Tất cả config server không truy cập được | Cluster có nguy cơ gián đoạn rộng hoặc không hoạt động | Đây là thành phần cốt lõi, cần bảo vệ và sao lưu |
| Một shard mất khả năng phục vụ | Dữ liệu/hoạt động liên quan tới shard đó có thể gián đoạn | Dữ liệu đã sharding không được nhân bản sang mọi shard |

Không có nguyên tắc “cứ ba thành viên là không bao giờ dừng”. Khả năng hoạt động phụ thuộc quorum, tình trạng mạng, số lượng thành viên khả dụng, dữ liệu đã đồng bộ, read/write concern và topology cụ thể.

### Ví dụ: lỗi mongos và lỗi mongod không giống nhau

- Nếu **mongos-1** chết, dữ liệu vẫn nằm trên shard. Khi có **mongos-2** và ứng dụng cấu hình kết nối phù hợp, client có thể tiếp tục sau khi phát hiện kết nối lỗi.
- Nếu **mongod primary của Shard A** chết, router còn hoạt động nhưng các truy vấn/ghi liên quan đến Shard A phải chờ hoặc chịu ảnh hưởng theo trạng thái replica set.
- Nếu **CSRS gặp sự cố**, các shard có thể vẫn giữ dữ liệu đầy đủ nhưng cluster mất một phần năng lực phối hợp dựa trên metadata.

Các tình huống này giải thích tại sao giám sát production cần theo dõi cả router, shard replica set và config server replica set.

## 8. Kiểm tra vai trò trong mongosh

Các lệnh sau dùng để **quan sát** deployment hiện có. Kết quả phụ thuộc quyền truy cập, phiên bản và việc bạn đang kết nối tới mongos hay mongod.

### 8.1. Xác định đang kết nối tới mongos hay mongod

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Đặc điểm thường thấy:

- Nếu kết nối tới **mongos**, phản hồi có field **msg** với giá trị **isdbgrid**.
- Nếu kết nối tới **mongod trong replica set**, phản hồi thường có các field như **setName** và trạng thái thành viên.
- Nếu là một mongod cấu hình **config server**, vẫn là mongod; cần đối chiếu thông tin cấu hình/cluster để xác định vai trò chuyên biệt, không chỉ dựa vào việc không có **isdbgrid**.

Có thể kiểm tra nhanh:

~~~javascript
const hello = db.adminCommand({ hello: 1 });

print("msg:", hello.msg);
print("setName:", hello.setName);
print("isWritablePrimary:", hello.isWritablePrimary);
~~~

Lưu ý: **isWritablePrimary** trong phản hồi mongos không có nghĩa mongos là primary của replica set. Trong kết nối đến mongos, ý nghĩa của thuộc tính phản hồi phải được hiểu theo loại server và cách client xác định topology.

### 8.2. Xem trạng thái sharded cluster

Kết nối mongosh qua **mongos** với quyền quản trị/quan sát phù hợp:

~~~javascript
sh.status();
~~~

Lệnh cung cấp thông tin về shard, database, collection đã sharding và trạng thái liên quan tùy phiên bản. Đây là cách hữu ích để biết bạn đang kiểm tra **toàn cluster**, thay vì một mongod shard riêng lẻ.

Xem danh sách shard thông qua lệnh quản trị:

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Kết quả điển hình có thể biểu diễn mỗi shard với tên, host/replica set và trạng thái. Ví dụ minh họa:

~~~javascript
{
  shards: [
    { _id: "shardA", host: "rsShardA/a1.example.net:27018,a2.example.net:27018" },
    { _id: "shardB", host: "rsShardB/b1.example.net:27018,b2.example.net:27018" }
  ],
  ok: 1
}
~~~

Phản hồi thực tế có thể có thêm field hoặc cấu trúc chi tiết tùy phiên bản. Đừng suy ra số thành viên replica set chỉ từ danh sách host rút gọn trong ví dụ.

### 8.3. Nhận biết config shard ở MongoDB 8.0+

Trên cluster hỗ trợ config shard, khi kết nối mongos, có thể kiểm tra danh sách shard:

~~~javascript
const result = db.adminCommand({ listShards: 1 });
const configShard = result.shards.find(shard => shard._id === "config");

print(configShard ? "Có config shard" : "Không có config shard");
~~~

Nếu tồn tại shard với **_id = "config"**, cluster sử dụng config shard. Nếu không, với topology tương ứng cluster dùng dedicated config server.

Không tự ý cập nhật các collection thuộc database **config** để thử thay đổi cách sharding. Chỉ sử dụng lệnh quản trị được hỗ trợ nếu cần thay đổi cấu hình cluster.

### 8.4. Xem trạng thái replica set của mongod

Khi kết nối đến một mongod là thành viên replica set với quyền thích hợp:

~~~javascript
rs.status();
~~~

Lệnh giúp quan sát tên replica set, các thành viên và trạng thái primary/secondary. Đây là kiểm tra **ở cấp replica set**, không phải một báo cáo đầy đủ của mọi shard trên toàn cluster.

Nếu kết nối đến mongos, muốn quan sát topology toàn sharded cluster hãy ưu tiên lệnh dành cho cluster như **sh.status()** hoặc công cụ quản lý/giám sát thích hợp.

## 9. Hình dung cách khởi động và kết nối

Hai binary quan trọng là **mongod** và **mongos**. Role được xác định bằng cấu hình và cách các tiến trình tham gia topology.

| Nhiệm vụ | Binary | Ý tưởng cấu hình |
| --- | --- | --- |
| Chạy MongoDB standalone | mongod | Storage path, network, security |
| Chạy thành viên replica set | mongod | Replica set name, storage, network |
| Chạy thành viên shard replica set | mongod | Replica set name và vai trò **shardsvr** |
| Chạy dedicated config server | mongod | Replica set name và vai trò **configsvr** |
| Chạy query router | mongos | Địa chỉ **config server replica set** |

### 9.1. Ví dụ cấu hình minh họa

Dưới đây là **các đoạn cấu hình độc lập để minh họa vai trò**, chưa phải quy trình triển khai cụm hoàn chỉnh. Cần thiết lập replica set, thêm shard, cấu hình xác thực nội bộ, kết nối an toàn và các bước quản trị khác trước khi vận hành.

Cấu hình của một mongod thuộc shard replica set:

~~~yaml
# shard-a.yml
storage:
  dbPath: /var/lib/mongodb/shard-a
net:
  port: 27018
replication:
  replSetName: rsShardA
sharding:
  clusterRole: shardsvr
~~~

Cấu hình của một mongod thuộc **dedicated config server replica set**:

~~~yaml
# config-a.yml
storage:
  dbPath: /var/lib/mongodb/config-a
net:
  port: 27019
replication:
  replSetName: cfgRS
sharding:
  clusterRole: configsvr
~~~

Cấu hình router mongos:

~~~yaml
# router.yml
net:
  port: 27017
sharding:
  configDB: cfgRS/cfg-a.example.net:27019,cfg-b.example.net:27019,cfg-c.example.net:27019
~~~

Đoạn cấu hình trên dùng hostname minh họa, không đại diện cho hệ thống thật. Mongos **không cần khai báo storage.dbPath** để lưu collection ứng dụng.

Chạy binary với tệp cấu hình tương ứng:

~~~bash
mongod --config /etc/mongodb/shard-a.yml
mongod --config /etc/mongodb/config-a.yml
mongos --config /etc/mongodb/router.yml
~~~

Ba lệnh chỉ minh họa sự khác nhau giữa binary và role. **Chúng không tự tạo ra sharded cluster hoàn chỉnh**: ví dụ chưa bao gồm việc chuẩn bị thư mục, hostname, cấu hình security, khởi tạo replica set và đăng ký shard.

### 9.2. Ứng dụng nên kết nối đến đâu?

Standalone:

~~~text
mongodb://standalone.example.net:27017/bookstore
~~~

Replica set:

~~~text
mongodb://db-a.example.net:27017,db-b.example.net:27017,db-c.example.net:27017/bookstore?replicaSet=rsBooks
~~~

Sharded cluster (ứng dụng kết nối đến mongos):

~~~text
mongodb://router-a.example.net:27017,router-b.example.net:27017/bookstore
~~~

Đây là các URI mẫu. Trong môi trường thực tế cần tính đến TLS, authentication, DNS, network policy và những tùy chọn kết nối theo yêu cầu của deployment.

Ví dụ Java Driver kết nối thông qua hai mongos:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ReadBooks {
    public static void main(String[] args) {
        String uri = "mongodb://router-a.example.net:27017,"
                + "router-b.example.net:27017/bookstore";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("bookstore");
            MongoCollection<Document> books = db.getCollection("books");

            Document book = books.find(new Document("isbn", "9786040000123"))
                    .first();

            System.out.println(book);
        }
    }
}
~~~

Ứng dụng chỉ cần dùng API truy vấn collection; driver cùng mongos quản lý đường đi đến các shard phù hợp. Nếu môi trường không sharding, ứng dụng kết nối đến standalone hoặc replica set mongod và không cần mongos/config servers.

## 10. So sánh trách nhiệm theo từng câu hỏi vận hành

| Câu hỏi | Thành phần trả lời chính |
| --- | --- |
| Document này được lưu ở máy nào? | Mongod thuộc shard đang sở hữu dữ liệu; mongos định tuyến theo metadata |
| Ai trực tiếp thực thi truy vấn trên index và document? | mongod của shard |
| Ai tiếp nhận truy vấn ở điểm kết nối logic của sharded cluster? | mongos |
| Ai biết range/chunk đang thuộc shard nào? | Metadata trên config server; mongos sử dụng cache metadata |
| Ai sao chép dữ liệu sau khi primary ghi? | Các mongod trong cùng replica set |
| Ai bầu primary mới của shard sau sự cố? | Các thành viên replica set của shard |
| Ai cung cấp tính sẵn sàng cho metadata? | Config Server Replica Set |
| Có thể đặt nhiều router để dự phòng không? | Có, nhiều mongos |
| Có thể dùng config server để lưu ứng dụng không? | Có trong mô hình config shard được hỗ trợ từ MongoDB 8.0; không phải mục đích của dedicated config server |
| Có sharding thì luôn phải kết nối thẳng vào từng shard không? | Không; ứng dụng bình thường kết nối qua mongos |

### Những nhầm lẫn thường gặp

**Nhầm lẫn 1: mongos là database server có dữ liệu riêng.**  
Mongos là query router; dữ liệu bền vững được quản lý bởi mongod trong các shard. Router có metadata cache nhưng không giữ document ứng dụng như một kho dữ liệu độc lập.

**Nhầm lẫn 2: config server là một binary khác mongod.**  
Config server là vai trò của mongod. Chỉ mongos là tiến trình router với binary riêng.

**Nhầm lẫn 3: sharding và replica set giống nhau.**  
Replica set giữ bản sao cùng dữ liệu; sharding chia dữ liệu giữa các shard. Trong thực tế mỗi shard lại sử dụng replica set.

**Nhầm lẫn 4: mỗi truy vấn luôn đi qua config server.**  
Mongos cache metadata và dùng thông tin đó để định tuyến. Nó không nhất thiết phải hỏi config server cho từng document trong từng lần đọc.

**Nhầm lẫn 5: có thể thay mongos bằng kết nối trực tiếp đến một shard.**  
Một shard chỉ chứa một phần dữ liệu đã phân vùng; kết nối ứng dụng trực tiếp có thể trả kết quả thiếu hoặc bỏ qua cơ chế điều phối đúng.

**Nhầm lẫn 6: chỉ cần tăng số mongos để lưu được nhiều dữ liệu hơn.**  
Mongos không tăng dung lượng lưu trữ dữ liệu. Khả năng mở rộng dung lượng và khối lượng dữ liệu phụ thuộc vào các shard, cách phân vùng và thiết kế workload.

**Nhầm lẫn 7: config server trong mọi phiên bản tuyệt đối không thể chứa dữ liệu ứng dụng.**  
Điều đó đúng với vai trò dedicated truyền thống, nhưng MongoDB 8.0+ hỗ trợ config shard giữ cả metadata và dữ liệu ứng dụng.

## 11. Bài thực hành quan sát kiến trúc

Bài thực hành này ưu tiên các lệnh **chỉ đọc**, phù hợp khi bạn có sẵn một MongoDB deployment thử nghiệm và quyền quan sát cần thiết.

### Tình huống A: kết nối đến một replica set

1. Kết nối bằng mongosh đến replica set thử nghiệm.
2. Chạy các lệnh:

~~~javascript
db.adminCommand({ hello: 1 });
rs.status();
~~~

3. Tìm tên replica set, thành viên đang là primary và các secondary.
4. Xác định thành phần nào là **mongod**; giải thích vì sao không cần mongos trong topology chỉ có replica set này.

### Tình huống B: kết nối đến sharded cluster

1. Kết nối mongosh qua mongos.
2. Chạy:

~~~javascript
const info = db.adminCommand({ hello: 1 });
print(info.msg);

sh.status();

const shards = db.adminCommand({ listShards: 1 });
printjson(shards);
~~~

3. Quan sát giá trị **isdbgrid** và danh sách shard.
4. Từ cấu hình đang thấy, phân biệt **router**, **shard** và **config server**.
5. Nếu phiên bản từ 8.0 trở lên, kiểm tra có shard mang **_id = "config"** để biết có đang dùng config shard hay không.

### Tình huống C: giải thích đường đi của một câu truy vấn

Giả sử **shop.orders** sharding theo **customerId** và có hai shard:

~~~javascript
db.orders.find({ customerId: 1450 });
db.orders.find({ status: "PAID" });
~~~

Hãy trả lời:

1. Yêu cầu đầu tiên có cơ hội được định tuyến đến một shard hay nhiều shard? Vì sao?
2. Tại sao yêu cầu thứ hai có thể cần scatter/gather?
3. Thành phần nào giữ bản đồ phân vùng lâu dài?
4. Thành phần nào trực tiếp dùng index và đọc document?
5. Nếu mongos đang kết nối lỗi nhưng có mongos dự phòng, dữ liệu trên shard có biến mất không?
6. Nếu replica set của một shard mất primary, thành phần nào tham gia bầu primary mới?

Một câu trả lời tốt sẽ xác định rõ ba trách nhiệm: **mongos định tuyến**, **mongod trên shard xử lý và lưu dữ liệu**, **config server quản lý metadata**. Việc hiểu riêng từng vai trò là nền tảng để tiếp tục học replication, sharding, shard key, balancer, khả năng sẵn sàng và giám sát MongoDB.

## Tài liệu tham khảo

- [MongoDB — Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/)
- [MongoDB — Routing with mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/)
- [MongoDB — Config Servers](https://www.mongodb.com/docs/manual/core/sharded-cluster-config-servers/)
- [MongoDB — Config Shards](https://www.mongodb.com/docs/manual/core/config-shard/)
- [MongoDB — Shards](https://www.mongodb.com/docs/manual/core/sharded-cluster-shards/)
