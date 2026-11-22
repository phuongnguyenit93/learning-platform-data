# Vai trò mongos, config server replica set và các shard trong MongoDB Sharding

## 1. Vì sao một MongoDB database cần sharding?

Một ứng dụng thuê nhà có thể lưu hàng triệu tin đăng, hợp đồng, lượt tìm kiếm và lịch sử thanh toán. Ban đầu, một **replica set** có thể đáp ứng nhu cầu: primary tiếp nhận ghi, các secondary sao chép dữ liệu để tăng khả năng chịu lỗi và hỗ trợ một số kiểu đọc. Nhưng khi dữ liệu và tải truy vấn vượt quá năng lực của một replica set, chỉ tăng RAM/CPU/ổ đĩa cho từng máy có thể không còn đủ kinh tế hoặc đủ khả năng mở rộng.

**Sharding** chia dữ liệu của một collection thành những phần nằm trên **nhiều shard**, để phân phối dung lượng lưu trữ và một phần tải đọc/ghi. Tuy nhiên, ứng dụng không nên phải tự nhớ “hợp đồng 1001 ở máy nào, hợp đồng 1002 ở máy nào”. MongoDB dùng một kiến trúc gồm các thành phần có trách nhiệm khác nhau:

1. **mongos (query router):** điểm vào của ứng dụng, định tuyến request đến shard phù hợp và kết hợp kết quả.
2. **Config server replica set (CSRS):** duy trì metadata điều phối cluster, chẳng hạn thông tin shard, sharded collection và vị trí các khoảng shard key.
3. **Shard:** nơi lưu và xử lý dữ liệu ứng dụng; trong production mỗi shard thường là một **replica set** riêng.

Sơ đồ tổng quát:

~~~text
                     API / Worker / BI Client
                               |
                         MongoDB Driver
                               |
                   +-----------+-----------+
                   |                       |
                mongos A                mongos B
                   |                       |
                   +-----------+-----------+
                               |
           Tra cứu / refresh metadata định tuyến
                               |
                  +------------v------------+
                  | Config Server Replica  |
                  | Set: cfg1, cfg2, cfg3  |
                  | Metadata toàn cluster  |
                  +-------------------------+
                               ^
                               | metadata về vị trí dữ liệu
                               |
                   +-----------+-----------+
                   |                       |
          +--------v--------+     +--------v--------+
          | Shard 01 (RS)   |     | Shard 02 (RS)   |
          | P, S1, S2       |     | P, S1, S2       |
          | Dữ liệu tenant  |     | Dữ liệu tenant  |
          | theo các range  |     | theo các range  |
          +-----------------+     +-----------------+
~~~

Đường nối trong sơ đồ là **sơ đồ logic**, không phải một request luôn đi qua config server trước khi tới shard. **mongos có bộ nhớ đệm metadata định tuyến**, nên trong nhiều tình huống nó biết shard cần hỏi mà không phải truy vấn config servers trên từng request.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả rõ **mongos làm gì, không làm gì**.
- Giải thích **CSRS lưu metadata chứ không phải nơi tập trung toàn bộ dữ liệu ứng dụng**.
- Nêu vai trò của **shard replica set**, primary/secondary trong từng shard.
- Vẽ được luồng **targeted query** so với **scatter-gather query**.
- Hiểu **shard key**, range/chunk, placement metadata và **balancer/chunk migration**.
- Phân tích hệ quả khi một **mongos**, **CSRS** hoặc **shard** không khả dụng.
- Sử dụng những lệnh **mongosh chỉ đọc** để khảo sát một sharded cluster.
- Chọn chiến lược kết nối, index và quan sát phù hợp, tránh những giả định sai về tính nhất quán hoặc hiệu năng.

> Bài học tập trung vào kiến trúc sharded cluster có **config server replica set chuyên trách**. Một số phiên bản MongoDB mới còn có những hình thức triển khai config server và shard tích hợp; chức năng metadata/routing vẫn cần được phân biệt, nhưng quy trình triển khai cụ thể phải theo đúng phiên bản máy chủ đang dùng.

## 2. Phân biệt horizontal sharding với replica set

Hai cơ chế thường cùng xuất hiện trong một sharded cluster nhưng **giải quyết hai mục tiêu khác nhau**.

| Tiêu chí | Replica set | Sharding |
| --- | --- | --- |
| Mục tiêu chính | Sao chép cùng một tập dữ liệu, chịu lỗi và failover | Chia dữ liệu/tải giữa nhiều shard |
| Dữ liệu giữa thành viên | Primary và secondary duy trì bản sao của cùng logical dataset | Mỗi shard giữ một phần dữ liệu của sharded collection |
| Quyết định địa chỉ dữ liệu | Không dùng shard key để chia dữ liệu giữa các member | Routing dựa trên shard key và placement metadata |
| Khi thêm thành viên | Thêm bản sao, không tự tăng khả năng chứa dữ liệu logic theo chiều ngang | Thêm shard có thể tăng sức chứa và khả năng phân tải |
| Vai trò primary | Nhận writes trong mỗi replica set | Mỗi shard replica set có primary riêng |
| Xử lý failover | Election trong replica set | Failover diễn ra độc lập bên trong shard/CSRS tương ứng |

Ví dụ hai shard:

~~~text
Shard A: Replica Set A
  A-primary:    dữ liệu range A
  A-secondary1: bản sao range A
  A-secondary2: bản sao range A

Shard B: Replica Set B
  B-primary:    dữ liệu range B
  B-secondary1: bản sao range B
  B-secondary2: bản sao range B
~~~

**Sai lầm phổ biến:** nghĩ ba secondary của một shard là “ba shard”. Không phải. Chúng là **ba thành viên của cùng một replica set**, cùng duy trì dữ liệu logic của shard đó.

Với shard A và B, một document thuộc shard A không mặc nhiên tồn tại trong shard B chỉ vì cluster bật replication. **Replication bên trong shard** và **phân mảnh giữa shards** là hai chiều riêng.

## 3. mongos: query router, không phải data server

### 3.1. Mongos đứng ở đâu?

Ứng dụng dùng MongoDB driver kết nối qua một hay nhiều **mongos**. Mongos nhận những lệnh như **find**, **insert**, **update**, **delete**, **aggregate**, rồi quyết định shard nào phải xử lý.

~~~text
App
 |
 | find({tenantId:"t001", orderNo:"SO-001"})
 v
mongos
 |
 | Dựa vào shard key và routing metadata
 v
Shard có range chứa khóa tương ứng
 |
 | thực thi trên MongoDB data-bearing nodes
 v
mongos tập hợp/trả kết quả
 |
 v
App
~~~

Mongos **không** lưu các order của ứng dụng như một shard. Nó có thể giữ **metadata định tuyến trong bộ nhớ**, thông tin phiên/trạng thái kết nối và dữ liệu trung gian cần cho việc xử lý query, nhưng nó không phải bản sao dữ liệu ứng dụng.

### 3.2. Những nhiệm vụ chính của mongos

**1. Chọn shard cần truy vấn.** Với filter chứa shard key đủ hữu ích, mongos có thể gửi request tới một shard hoặc một nhóm nhỏ shard.

**2. Fan-out khi không thể định tuyến hẹp.** Nếu filter không chứa thông tin shard key phù hợp, mongos có thể phải hỏi nhiều hoặc toàn bộ shards.

**3. Kết hợp kết quả.** Với query liên quan nhiều shards, mongos có thể hợp nhất các cursor, thực hiện phần xử lý kết quả như merge sort/aggregation theo kế hoạch cụ thể.

**4. Điều phối một số thao tác cluster-level.** Ví dụ một số lệnh quản trị sharding hoặc DDL được gọi từ mongos và cần metadata nhất quán; thực tế thực thi có thể liên quan đến các thành phần điều phối khác tùy phiên bản.

**5. Quản lý định tuyến khi metadata thay đổi.** Khi data range di chuyển giữa shards hoặc metadata bị stale, mongos cần refresh thông tin và định tuyến lại theo cơ chế của server.

**6. Chuyển các yêu cầu concern/preference phù hợp.** Khi driver gửi write concern, read concern và read preference, mongos chọn các node đích và chuyển thao tác theo semantics tương ứng; nó không tự thay thế cơ chế replication của mỗi shard.

### 3.3. Mongos không làm những việc nào?

- Không tự lưu document người dùng như một shard.
- Không tự quyết định majority commit cho các write bên trong shard replica set.
- Không phải node primary/secondary trong replica set của shard.
- Không chứa toàn bộ metadata cluster như nguồn chân lý cuối cùng; metadata chính thuộc về cấu trúc config server.
- Không phải cơ chế bảo đảm mọi truy vấn chỉ chạm **một** shard.
- Không tự biến một write trên nhiều document ở nhiều shard thành transaction all-or-nothing.
- Không phải hệ thống cache kết quả truy vấn ứng dụng theo kiểu Redis.

**Mongos giúp trừu tượng hóa vị trí dữ liệu, không xóa bỏ giới hạn vật lý của dữ liệu phân tán.**

### 3.4. Mongos có state hay stateless?

Mongos thường được gọi là **stateless query router** về phương diện **dữ liệu lưu bền vững của ứng dụng**: nếu một mongos chết, không có bộ document ứng dụng độc quyền trên mongos đó bị mất.

Tuy vậy, trong thời gian chạy, mongos vẫn có:

- Connection pools và thông tin xác thực/phiên làm việc.
- Cache routing metadata.
- Cursor/aggregation state cần thiết cho request đang hoạt động.
- Thông tin điều phối request trong thời gian ngắn.

Vì thế, “stateless” không có nghĩa một query đang chạy sẽ không bị gián đoạn khi mongos đó bị lỗi. Driver cần có khả năng chọn router khác và xử lý retry cho thao tác đủ điều kiện.

### 3.5. Nhiều mongos để tăng khả dụng

Một kiến trúc thường có **hơn một mongos**, đặt gần API servers hoặc sau cơ chế cân bằng kết nối thích hợp:

~~~text
API instance A ------ mongos A -----+
                                    +---- Sharded cluster
API instance B ------ mongos B -----+
~~~

Khi một router không sẵn sàng, ứng dụng có thể tiếp tục qua router khác nếu driver và kết nối được cấu hình đúng. **Nhiều mongos không có nghĩa tăng dung lượng lưu data trực tiếp**; dung lượng phụ thuộc shards.

### 3.6. Mongos và read preference

Với **readPreference: primary**, những read tương ứng sẽ chọn primary của replica set tại mỗi shard đích. Với **secondaryPreferred**, read có thể được phục vụ bởi secondary phù hợp ở các shard được nhắm đến, tùy topology và những giới hạn của từng operation.

Mongos không được hiểu là “tất cả read đều chạy ở chính mongos”. Mongos **định tuyến và hợp nhất**, còn dữ liệu ứng dụng được đọc từ các shard.

## 4. Config server replica set: bản đồ và bộ não metadata của cluster

### 4.1. CSRS là gì?

**Config server replica set (CSRS)** là một replica set dành cho **metadata của sharded cluster**. Thay vì lưu toàn bộ tin đăng/hợp đồng, nó lưu dữ liệu giúp MongoDB xác định **các shards, sharded collections và cách phân bố những khoảng shard key**.

Ví dụ khái niệm:

~~~text
Config metadata:
  collection: shop.orders
  shard key: {tenantId:1, orderNo:1}

  range R1: [MinKey ... "t020") -> shard01
  range R2: ["t020" ... "t050")   -> shard02
  range R3: ["t050" ... MaxKey)   -> shard03

  phiên bản placement metadata: V...
~~~

Đây là mô hình minh họa đơn giản, không phải schema thực của các document nội bộ config database. Việc chia range trong thực tế là theo **khóa shard đầy đủ**, có thể là khóa ghép và có các chi tiết version/collection UUID.

### 4.2. CSRS lưu những loại metadata nào?

Một số nhóm thông tin điển hình:

- Danh sách các **shards** tham gia cluster và thông tin định danh/kết nối.
- Danh sách database và collection liên quan đến sharding.
- **Shard key** đã chọn cho mỗi sharded collection.
- **Chunk/range placement**: khoảng shard key nào đang thuộc shard nào.
- Metadata phiên bản/epoch/UUID giúp phát hiện thông tin routing cũ.
- Các thiết lập/ranh giới **zones** và placement khi được sử dụng.
- Thông tin quản trị phục vụ cân bằng và những thao tác cluster-level khác.

Không nên viết trực tiếp vào **config database** hoặc sửa các metadata collections này bằng CRUD thông thường. Thay đổi sharding metadata phải đi qua **lệnh và quy trình được MongoDB hỗ trợ**.

### 4.3. Tại sao config server phải là replica set?

Metadata quyết định vị trí dữ liệu. Nếu chỉ một process giữ bản đồ đó và bị lỗi, cả cluster có thể không còn khả năng điều phối một số hoạt động định tuyến/metadata. Bởi vậy, CSRS dùng **replication** để duy trì tính khả dụng và độ bền của cluster metadata.

Với mô hình dedicated CSRS thông dụng:

~~~text
                   Config Server Replica Set

                   cfg-primary (metadata)
                       /          \
                      v            v
               cfg-secondary1  cfg-secondary2

                      Metadata nhất quán,
                election/failover khi thích hợp
~~~

Trong triển khai production thường sử dụng **ít nhất ba config server members** theo hướng dẫn MongoDB và cấu hình phù hợp. Các yêu cầu đặc biệt về voting members, arbiter, delayed members, write concern và cấu hình CSRS phải được đối chiếu với phiên bản server; không tự chọn cấu hình chỉ vì “replica set khác dùng được”.

### 4.4. CSRS không phải data warehouse hoặc nơi query trực tiếp nghiệp vụ

Một request lấy Order có thể được mongos định tuyến dựa trên bản đồ trong CSRS, nhưng **document Order thực nằm trên shard**.

~~~text
mongos --> tra cứu/refresh metadata --> CSRS
mongos --> đọc document Order -------> Shard
~~~

Ứng dụng không gửi **db.orders.find()** tới config server để đọc order. Những CRUD nghiệp vụ cần qua mongos, rồi đến shard tương ứng. Quyền truy cập và hoạt động trên config database là việc quản trị có rủi ro cao.

### 4.5. Config server primary và thay đổi metadata

Trong dedicated CSRS, primary đóng vai trò quan trọng đối với các thao tác thay đổi metadata. Khi có election hoặc không đủ khả năng thực hiện những ghi metadata cần thiết, các thao tác như thêm shard, thay đổi placement, sharding DDL và một số bước migration có thể bị ảnh hưởng.

**Không đồng nhất outage CSRS với việc toàn bộ query dữ liệu lập tức dừng.** Các mongos/shards còn có metadata đã cache và có thể tiếp tục một số đọc/ghi trên trạng thái ổn định. Nhưng các thao tác cần refresh metadata hay commit thay đổi placement có thể thất bại, và về lâu dài ảnh hưởng khả năng phục vụ cluster.

### 4.6. Khi có config shard trong các phiên bản mới

Một số bản MongoDB hiện đại có thể hỗ trợ hình thức **config shard**, trong đó chức năng config server và nơi lưu một phần dữ liệu ứng dụng có thể cùng nằm trên một nhóm thành viên theo quy định sản phẩm. Điều này **không làm mất khái niệm vai trò metadata**: router vẫn cần một nguồn metadata nhất quán, các shard vẫn chịu trách nhiệm phục vụ dữ liệu.

Vì bài tập tập trung vào ba thành phần theo kiến trúc dễ học, mọi sơ đồ bên dưới dùng **dedicated CSRS** trừ khi ghi chú khác. Khi vận hành một cluster thật, kiểm tra topology/phiên bản và các hướng dẫn tương ứng.

## 5. Shard: nơi lưu document và thực thi thao tác dữ liệu

### 5.1. Một shard thường là replica set

Shard là đơn vị lưu một phần tập dữ liệu của sharded collection. Trong môi trường production, mỗi shard thường được triển khai như một **replica set** riêng nhằm tránh một máy lỗi làm mất khả năng phục vụ phần dữ liệu đó.

~~~text
Shard 01 / RS shard01:
  shard01-primary
  shard01-secondaryA
  shard01-secondaryB

Shard 02 / RS shard02:
  shard02-primary
  shard02-secondaryA
  shard02-secondaryB
~~~

Các replica set của **từng shard độc lập nhau** về election và local replication. Việc shard01 thay primary không buộc shard02 thay primary. Mongos có nhiệm vụ gửi request đến node phù hợp theo topology và read preference.

### 5.2. Shard thực sự làm gì?

- Lưu những document/range được phân công cho shard.
- Duy trì **indexes** cho những document mà shard đang chứa.
- Thực thi filter, sort, aggregation và các thao tác CRUD khi mongos gửi tới.
- Dùng **oplog/replication** trong replica set của shard.
- Tham gia **chunk/range migration** khi dữ liệu chuyển giữa shards.
- Trả dữ liệu hoặc phần kết quả để mongos merge/điều phối tiếp.

Shard **không** tự biết mọi request người dùng cần dữ liệu ở tất cả shard khác thế nào. Nó chủ yếu xử lý phần công việc dành cho mình, theo metadata/routing mà cluster điều phối.

### 5.3. Document thuộc shard nào?

Với sharded collection, MongoDB dùng **shard key** để xác định nơi đặt document trong những **range/chunk** thuộc các shard.

Ví dụ một collection **orders** có shard key:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

Các document:

~~~javascript
{ _id: "o001", tenantId: "t001", orderNo: "SO-001", amount: 100 }
{ _id: "o002", tenantId: "t001", orderNo: "SO-002", amount: 250 }
{ _id: "o003", tenantId: "t002", orderNo: "SO-001", amount: 130 }
~~~

được phân theo thứ tự giá trị của **khóa ghép**. Không phải lúc nào mọi order của t001 cũng nằm trên đúng một shard vĩnh viễn; một tenant lớn có thể có nhiều range trên các shard khác nhau nếu shard key và placement cho phép.

### 5.4. Bản sao bên trong shard khác với bản sao giữa shards

Nếu o001 nằm trên shard01, nó có thể hiện diện trên primary và các secondary của replica set shard01. Nó **không** tự tồn tại trên shard02 chỉ vì shard02 là một shard khác.

Mongos phải định tuyến đúng shard, thay vì gửi read tới shard02 và hy vọng “secondary của cluster” sẽ có cùng document.

### 5.5. Không kết nối trực tiếp tới shard để truy vấn tập sharded data

Một ứng dụng kết nối trực tiếp tới mongod của shard01 có thể chỉ thấy phần dữ liệu trên shard01, bỏ mất document nằm ở shard02. Quan trọng hơn, truy cập trực tiếp có thể bỏ qua các quy tắc routing/metadata và không phải giao diện ứng dụng hợp lệ cho sharded collections.

**Nguyên tắc vận hành:** ứng dụng truy cập sharded cluster **qua mongos/driver được cấu hình để dùng mongos**, không tự thay thế mongos bằng cách liệt kê danh sách shard mongod rồi chọn thủ công.

Kết nối trực tiếp tới shard có thể được dùng cho một số tác vụ chẩn đoán/quản trị đặc biệt theo hướng dẫn MongoDB, nhưng không phải kiểu kết nối CRUD thông thường.

## 6. Ba vai trò tương tác khi đọc một document

Xét collection **shop.orders**, shard key là:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

Ứng dụng gửi query:

~~~javascript
db.orders.findOne({
  tenantId: "t001",
  orderNo: "SO-001"
});
~~~

Luồng khái niệm:

~~~text
   [1] App -> mongos: findOne(t001, SO-001)
                       |
                       v
   [2] mongos xác định shard key và route metadata
                       |
                       v
   [3] Range của (t001, SO-001) thuộc shard01
                       |
                       v
   [4] mongos -> shard01 replica set
                       |
                       v
   [5] Shard01 dùng index/plan để tìm document
                       |
                       v
   [6] Shard01 -> mongos -> App
~~~

**Không có yêu cầu bắt buộc** rằng mongos phải hỏi CSRS ở bước [2] với mỗi request. Nó có thể dùng metadata cache đã cập nhật. Nếu routing metadata không còn hợp lệ, mongos dùng cơ chế phát hiện và refresh.

### 6.1. Điều gì giúp query chỉ vào một shard?

Với shard key ghép **{tenantId:1, orderNo:1}**, equality filter trên **toàn bộ shard key** có thể xác định chính xác range chứa document, nên thường là **targeted query**.

~~~javascript
// Có đủ hai thành phần shard key:
db.orders.find({
  tenantId: "t001",
  orderNo: "SO-001"
});
~~~

Nếu query chỉ lọc:

~~~javascript
db.orders.find({ tenantId: "t001" });
~~~

thì mongos có thể xác định một tập **range liên quan đến prefix tenantId**, nhưng các range đó có thể nằm trên **nhiều shard**. Không được khẳng định query prefix shard key luôn chỉ chạm đúng một shard.

Nếu query chỉ lọc:

~~~javascript
db.orders.find({ status: "paid" });
~~~

và status không giúp định tuyến theo shard key, mongos thường phải hỏi **nhiều hoặc toàn bộ shards** của collection.

## 7. Targeted query và scatter-gather

### 7.1. Targeted query

**Targeted query** nghĩa mongos xác định được shard hoặc tập shard nhỏ hơn dựa vào điều kiện truy vấn và placement metadata.

~~~text
find({tenantId:"t001", orderNo:"SO-001"})
                |
              mongos
                |
              shard01
~~~

Lợi ích có thể gồm:

- Ít shard phải thực thi request.
- Giảm network fan-out và việc merge kết quả.
- Dễ dự đoán latency hơn đối với query theo khóa rõ ràng.
- Cho phép scale khi workload được phân phối trên nhiều shard phù hợp.

**Nhưng targeted không đồng nghĩa query tự động nhanh.** Nếu shard đích thiếu index thích hợp hoặc có tài liệu rất lớn, query vẫn có thể quét nhiều key/document bên trong shard.

### 7.2. Scatter-gather

**Scatter-gather** xuất hiện khi mongos không thu hẹp được tập shard đích đủ tốt:

~~~text
find({status:"paid"})
          |
        mongos
      /    |     \
     v     v      v
  shard01 shard02 shard03
     \     |      /
      \    |     /
        mongos
           |
       kết quả cuối
~~~

Mongos hoặc các thành phần pipeline liên quan phải thu thập/merge kết quả từ những shard đích. Điều này không nhất thiết sai: báo cáo toàn cluster có thể cần đọc tất cả shards. Nhưng với API truy xuất từng Order theo ID, scatter-gather liên tục thường là dấu hiệu shard key/query pattern chưa phù hợp.

### 7.3. Chi phí của scatter-gather

- Một request người dùng biến thành nhiều request nội bộ.
- Latency có thể chịu ảnh hưởng bởi shard chậm nhất.
- CPU/index scans được nhân lên ở nhiều shard.
- Kết quả cần merge sort/group có thể tiêu tốn RAM/network.
- Một shard không sẵn sàng có thể ảnh hưởng truy vấn toàn cluster.

Không thể sửa tất cả bằng cách tăng số mongos, vì chi phí nằm ở **số shard đích và công việc tại mỗi shard**.

### 7.4. Khi readConcern/readPreference tham gia

Nếu request đến ba shards, mongos phải điều phối việc đọc theo **read preference** (primary hay secondary phù hợp) và **read concern** (local/majority/snapshot tùy lệnh) ở mỗi thành phần. Tính nhất quán của một truy vấn xuyên shard có thêm giới hạn và cơ chế điều phối, nhất là transaction/snapshot.

Không thể nhìn một secondary chậm rồi nghĩ mongos tự chờ toàn bộ shard khác bắt kịp ở mọi readConcern; hành vi cụ thể phụ thuộc thao tác và mức concern được yêu cầu.

## 8. Luồng ghi qua mongos

### 8.1. Insert với shard key đầy đủ

Ví dụ:

~~~javascript
db.orders.insertOne({
  _id: "o1001",
  tenantId: "t001",
  orderNo: "SO-1001",
  amount: NumberDecimal("100.00"),
  status: "created"
});
~~~

Trong sharded collection, mongos dựa trên shard key của document để định tuyến insert tới shard sở hữu range tương ứng.

~~~text
App --> mongos --> xác định shard key
                     |
                     v
                 shard02 primary
                     |
             write + local replication
                     |
                     v
             ACK theo write concern
                     |
             mongos --> App
~~~

Mongos **không lưu bản chính của Order**. Điều kiện acknowledgment dựa trên write concern và cơ chế bên trong shard replica set liên quan.

### 8.2. Update có điều kiện shard key

Nếu một API update theo toàn bộ shard key:

~~~javascript
db.orders.updateOne(
  {
    tenantId: "t001",
    orderNo: "SO-1001",
    status: "created"
  },
  {
    $set: { status: "paid" },
    $currentDate: { paidAt: true }
  }
);
~~~

mongos có thông tin định tuyến tốt hơn so với một update chỉ có:

~~~javascript
db.orders.updateOne(
  { status: "created" },
  { $set: { status: "paid" } }
);
~~~

Không nên viết updateOne mơ hồ rồi trông mong mongos “tự tìm đúng đơn” khi filter có thể khớp nhiều document. Các yêu cầu về **targeting, shard key, upsert và thao tác nhiều shard** có sự thay đổi theo phiên bản MongoDB; cần kiểm tra tài liệu đúng phiên bản nếu dùng những cú pháp không chứa đủ shard key.

### 8.3. Write concern vẫn thuộc về dữ liệu ghi

~~~javascript
db.orders.updateOne(
  {
    tenantId: "t001",
    orderNo: "SO-1001"
  },
  {
    $set: { status: "paid" }
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

Trong shard đích có replica set, **w:"majority"** yêu cầu điều kiện xác nhận theo đa số thành viên dữ liệu phù hợp của replica set đó. Mongos chuyển/điều phối kết quả tới client, không đóng vai trò một phiếu majority của shard.

### 8.4. Ghi nhiều document trên nhiều shards

Một lệnh updateMany hoặc chuỗi hai updateOne có thể chạm nhiều document trên các shard khác nhau. **Không được coi chúng tự động là một transaction all-or-nothing**.

Nếu nghiệp vụ cần cập nhật đồng thời Order, Payment và Audit nằm ở nhiều shard, MongoDB có **distributed transactions** trên topology/phiên bản hỗ trợ. Nhưng transaction xuyên shards cần thêm điều phối, resource và có thể phát sinh write conflict/timeout. Không dùng transaction đa shard để thay thế việc chọn mô hình dữ liệu và shard key hợp lý.

## 9. Shard key: nền tảng của routing

### 9.1. Vai trò của shard key

Shard key là field hoặc tổ hợp field được MongoDB dùng để chia sharded collection thành các khoảng định tuyến. Việc chọn shard key ảnh hưởng:

- Document đặt ở shard nào.
- Một truy vấn có targeted hay phải scatter-gather.
- Dữ liệu và throughput có được phân phối đều hay không.
- Có hình thành shard hoặc key range **nóng** không.
- Có hỗ trợ các điều kiện equality/range phổ biến hay không.
- Mức độ khó khăn khi muốn thay đổi chiến lược phân mảnh về sau.

Một shard key không tốt có thể khiến cluster có nhiều shard nhưng tải dồn vào một shard.

### 9.2. Cardinality và phân phối

Giả sử dùng:

~~~javascript
{ status: 1 }
~~~

trong collection orders với chỉ ba trạng thái created/paid/cancelled. **Cardinality thấp** khiến tập document cùng một giá trị quá lớn, dễ tạo phân phối lệch và không có nhiều khả năng targeted cho những query không lọc status.

Nếu dùng:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

và tenant/orderNo phân phối đủ tốt, các request biết tenantId + orderNo có thể target chính xác hơn. Nhưng tenant lớn có thể tạo tải nóng; cần đo kích thước từng tenant, tần suất ghi và kiểu truy vấn.

### 9.3. Range sharding

Với **range-based sharding**, các giá trị shard key theo thứ tự BSON được chia thành **range/chunk** có chủ sở hữu là shard.

~~~text
Khóa tăng dần ------------------------------------->
   [R1]          [R2]          [R3]           [R4]
   shard01       shard02       shard01        shard03
~~~

Ưu điểm: các truy vấn theo một khoảng liên tục của shard key có thể target tập chunk liên quan.

Rủi ro: khóa **tăng đơn điệu** như thời gian ghi có thể đưa nhiều writes mới vào cùng vùng range cuối, tạo **hot shard/hot chunk** nếu phân phối không thích hợp.

### 9.4. Hashed sharding

Với hashed shard key, MongoDB dùng giá trị băm của field làm cơ sở phân bố. Ví dụ:

~~~javascript
{ tenantId: "hashed" }
~~~

Equality query biết tenantId có thể được định tuyến theo giá trị hash tương ứng. Hashed sharding có thể giúp phân phối tốt hơn khi field có cardinality phù hợp.

**Đổi lại:** locality của range theo giá trị gốc (chẳng hạn một khoảng thời gian) không còn giống range sharding trên field đó. Nếu một tenant quá lớn và toàn bộ document cùng một giá trị tenantId hashed, hashed tenantId một mình cũng **không tự chia tải của tenant ấy ra nhiều hash values**.

### 9.5. Prefix của compound shard key

Với:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

query chỉ có tenantId có thể target **một tập range** của tenant. Nhưng nếu tenant trải trên nhiều chunks ở nhiều shard, vẫn phải liên hệ nhiều shards. Query có cả tenantId/orderNo thường định tuyến hẹp hơn.

Không nhầm **index prefix** và **targeting guarantee**: một compound index hỗ trợ một filter không đảm bảo chỉ target một shard nếu filter thiếu phần shard key cần thiết.

### 9.6. Shard key và index

Mỗi shard vẫn có query planner và index cục bộ để thực thi truy vấn. Trong nhiều trường hợp, sharded collection yêu cầu index thích hợp để hỗ trợ shard key, cùng các quy tắc liên quan đến unique indexes. Một query được định tuyến đúng shard nhưng không có index tốt vẫn có thể chậm.

Chọn shard key và thiết kế **bộ index cho workload** phải được xem cùng nhau, không phải hai công việc độc lập.

### 9.7. Thay đổi shard key không phải sửa một dòng config

MongoDB có các tính năng như **refine shard key** hoặc **reshard collection** trên các phiên bản được hỗ trợ, nhưng quy trình thay đổi có chi phí và giới hạn thực tế. Không mặc định có thể đổi shard key tùy ý, không gián đoạn, như đổi tên field của document.

Vì vậy, trước khi sharding production nên lập ma trận **query shapes, phân bố dữ liệu, write load, tenant size và kế hoạch tăng trưởng**.

## 10. Chunk/range: đơn vị placement metadata

### 10.1. Chunk là gì?

Trong sharded collection, MongoDB biểu diễn việc đặt dữ liệu bằng các **khoảng shard key** (thường gọi là **chunks**). Mỗi chunk có:

- Ranh giới khóa dưới và trên theo định nghĩa metadata.
- Shard sở hữu chunk.
- Thông tin version/placement liên quan.

~~~text
Collection: orders
Shard key: {tenantId:1, orderNo:1}

  Chunk C1: [MinKey, key-A)   -> shard01
  Chunk C2: [key-A, key-B)    -> shard02
  Chunk C3: [key-B, MaxKey)   -> shard01
~~~

Một shard có thể sở hữu **nhiều chunks** không liền nhau. Không phải cluster luôn chia một shard thành một khoảng duy nhất.

### 10.2. Một chunk không phải một collection

Chunk là đơn vị **định tuyến/placement** của một phần dữ liệu sharded collection, không phải database riêng của người dùng và không phải một replica set.

Nếu một document có shard key nằm trong C2, nó thuộc shard sở hữu C2 theo metadata hiện tại. Bên trong shard đó, document vẫn được lưu như MongoDB document bình thường cùng các index liên quan.

### 10.3. Metadata có thể thay đổi qua migration

Khi cân bằng dữ liệu hoặc thay đổi placement, chunk/range có thể được chuyển từ shard01 sang shard02. Vì thế, không nên lưu trong ứng dụng một bản đồ tĩnh “tenant t001 nằm trên shard01”.

**mongos sử dụng metadata cluster**, không phải một bảng hardcode trong API. Nếu key range chuyển đi, router phải cập nhật định tuyến qua cơ chế refresh để tiếp tục gửi request đúng shard.

## 11. Balancer và chunk migration: ai quyết định, ai di chuyển?

### 11.1. Mục tiêu của balancer

Một sharded cluster có thể bị phân bố không đều vì:

- Thêm một shard mới.
- Dữ liệu của một nhóm tenant tăng nhanh.
- Một số range chứa nhiều dữ liệu hơn những range khác.
- Áp dụng zones hoặc thay đổi placement rules.
- Khác biệt phân phối workload theo shard key.

**Balancer** hỗ trợ điều chỉnh placement để phân phối dữ liệu theo các quy tắc của cluster. Trong kiến trúc dedicated CSRS truyền thống của các phiên bản MongoDB hiện đại, thành phần điều phối cân bằng gắn với **config server primary**; việc thực thi chi tiết và cơ chế coordinator có thể thay đổi theo version.

Không mô tả balancer là “một mongos ngẫu nhiên chuyển document” hoặc “ứng dụng tự chuyển dữ liệu mỗi khi query chậm”.

### 11.2. Vai trò của các thành phần khi migration

~~~text
      CSRS / Balancer / Cluster coordinators
               |
               | xác định range cần chuyển,
               | quản lý điều phối/metadata
               v
       Donor shard -----------> Recipient shard
           |                       |
       dữ liệu hiện tại         nhận/copy dữ liệu
       + thay đổi khi move      và đồng bộ thay đổi
           |                       |
           +-----------+-----------+
                       |
             hoàn tất theo protocol
             cập nhật placement metadata
                       |
                    mongos
             refresh routing khi cần
~~~

Tên gọi:

- **Donor shard:** shard hiện đang sở hữu chunk/range được chuyển.
- **Recipient shard:** shard nhận range sau migration.
- **CSRS/coordinator:** duy trì metadata và phối hợp chuyển quyền sở hữu theo cơ chế được MongoDB hỗ trợ.
- **mongos:** định tuyến request theo phiên bản metadata đang hiệu lực.

Việc chuyển dữ liệu là công việc do **shard nodes** phối hợp, không phải mongos đọc toàn bộ document vào RAM rồi insert thủ công sang shard khác.

### 11.3. Migration không có nghĩa ứng dụng được phép thấy dữ liệu nhân đôi

Trong quá trình di chuyển, có thể tồn tại các bản sao tạm hoặc document ở các vị trí khác nhau theo protocol. MongoDB dùng metadata phiên bản, cơ chế sở hữu range và **orphan cleanup** để bảo đảm request thông thường được xử lý theo quyền sở hữu đúng.

Không nên query trực tiếp donor/recipient bằng cách bỏ qua mongos để kiểm tra rồi kết luận có dữ liệu trùng logic chỉ vì thấy cùng document trong giai đoạn migration.

### 11.4. Stale routing metadata

Giả sử mongos A đang cache:

~~~text
range R -> shard01
~~~

Sau migration, CSRS đã commit placement:

~~~text
range R -> shard02
~~~

Khi mongos A gửi request tới shard01 theo metadata cũ, các node có thể phát hiện phiên bản định tuyến không còn hợp lệ và yêu cầu refresh. Mongos cập nhật route rồi thử thao tác theo cơ chế tương ứng.

**Không phải mọi lần stale metadata đều là một lỗi người dùng thấy.** MongoDB có cơ chế xử lý và retry một số trường hợp. Nhưng migration, DDL và cache refresh có thể ảnh hưởng latency, và một số request vẫn có thể thất bại nếu vượt giới hạn/lỗi vận hành.

### 11.5. Balancing không đồng nghĩa cân bằng CPU tuyệt đối

Balancer chủ yếu giải quyết **placement/data distribution** theo chính sách của server. Một shard có thể có lượng dữ liệu gần bằng shard khác nhưng bị nóng hơn nhiều vì workload tập trung vào một tenant hoặc một range.

Phân bố dung lượng tốt không đảm bảo:

- QPS đều giữa các shards.
- Latency p99 đều.
- Disk I/O hoặc cache hit ratio giống nhau.
- Không có hot chunk/hot shard.

**Shard key và query patterns** vẫn là nền tảng của phân tải, còn balancer giúp quản lý dữ liệu trong những giới hạn đó.

## 12. Zones: định hướng dữ liệu đến nhóm shards

### 12.1. Khi cần ràng buộc vị trí

Một số hệ thống có yêu cầu đặt dữ liệu theo vùng địa lý, nhóm tenant hoặc tier storage. **Zones** (tag-aware sharding) cho phép gắn các range shard key với nhóm shard được chỉ định theo chính sách.

Ví dụ khái niệm:

~~~text
Zone APAC:
  các range tenant thuộc APAC -> shard01, shard02

Zone EU:
  các range tenant thuộc EU   -> shard03, shard04
~~~

CSRS quản lý metadata zone/placement; balancer/placement machinery thực thi việc điều chỉnh theo khả năng và giới hạn tương ứng. **mongos vẫn dùng routing metadata để tìm shard thực sự sở hữu range.**

### 12.2. Zones không tự thay thế chính sách bảo mật

Zone placement không tự tạo quy tắc tenant authorization trong API. Dữ liệu đặt ở shard thuộc vùng mong muốn vẫn cần:

- Xác thực/ủy quyền.
- Filter tenant chính xác.
- Encryption/TLS và quản trị key.
- Quy tắc backup/restore phù hợp vùng dữ liệu.
- Giám sát việc tuân thủ placement và migration.

Không dùng zone làm lý do bỏ điều kiện tenantId trong query.

## 13. Sharded và unsharded collections trong cùng database

### 13.1. Không phải collection nào cũng tự phân mảnh

Trong một sharded cluster, có thể tồn tại cả:

- **Sharded collection:** document được phân phối theo shard key.
- **Unsharded collection:** dữ liệu không được tự chia theo shard key dù database đang nằm trong sharded cluster.

Ví dụ logic:

~~~text
Database: shop
  orders          -> sharded theo tenantId/orderNo
  eventLogs       -> sharded theo tenantId/eventId
  appSettings     -> unsharded (dữ liệu nhỏ)
~~~

Đối với unsharded collection, placement/quy tắc điều phối phụ thuộc phiên bản; kiến trúc truyền thống có **primary shard của database** để giữ unsharded collections. Các bản hiện đại có thêm cơ chế di chuyển unsharded collection; cần đối chiếu tài liệu server.

### 13.2. Primary shard của database khác primary node của replica set

Hai khái niệm dễ gây nhầm:

- **Primary shard of a database:** khái niệm placement cấp database trong sharded cluster, quan trọng với unsharded collections theo mô hình truyền thống.
- **PRIMARY member of shard replica set:** tiến trình mongod nhận writes của một shard replica set.

“Database primary shard = shard02” **không có nghĩa shard02 là node PRIMARY duy nhất của toàn cluster**. Mỗi shard replica set có election/primary riêng.

### 13.3. Vì sao cần phân biệt?

Một request đọc unsharded collection có thể đi tới shard đang giữ collection đó, trong khi request đọc orders sharded được định tuyến theo shard key/range. Chỉ vì hai collections nằm trong cùng database **không** có nghĩa document của chúng cùng nằm trên một shard.

Đặc biệt, $lookup hoặc aggregation liên quan nhiều collections có các giới hạn về sharding, join placement và phiên bản; không giả định join luôn được thực hiện trên cùng một server.

## 14. Sự cố từng thành phần: điều gì sẽ xảy ra?

### 14.1. Một mongos lỗi

Nếu mongos A ngừng hoạt động:

- Requests đang gắn vào mongos A có thể thất bại hoặc phải được retry.
- Các shards và CSRS vẫn có thể hoạt động bình thường.
- Client có cấu hình nhiều mongos có thể chọn router khác.
- Một query/cursor đang chạy không được đảm bảo tiếp tục nguyên vẹn chỉ nhờ router khác.

Điểm mấu chốt: **mongos có thể scale theo số router**, nhưng client vẫn cần xử lý lỗi và retry đúng điều kiện.

### 14.2. Một config server member lỗi

Với dedicated CSRS 3 members, nếu một member lỗi nhưng CSRS vẫn có quorum và primary phù hợp, metadata operations có thể tiếp tục, dù có giảm khả năng chịu lỗi.

Nếu mất quorum/primary của CSRS:

- Những thao tác cập nhật metadata như migration, thêm shard, thay đổi sharding DDL có thể không thực hiện được.
- Một số query CRUD trên dữ liệu đã có với routing metadata hợp lệ **có thể tiếp tục**.
- Những request cần metadata mới/refresh hoặc các hoạt động quản trị tương ứng có thể thất bại.
- Mức tác động cụ thể phụ thuộc phiên bản, trạng thái cache, topology và thời điểm mất quorum.

Không khẳng định “CSRS lỗi thì toàn bộ data biến mất” hay “CSRS không quan trọng vì mongos có cache”.

### 14.3. Một shard secondary lỗi

Nếu shard01 là replica set và một secondary lỗi:

- Primary shard01 vẫn có thể tiếp tục nhận write nếu các điều kiện election/acknowledgment cho phép.
- Read preference muốn chọn secondary có thể bị ảnh hưởng.
- WriteConcern majority có thể chậm hoặc timeout nếu không còn đủ members cần thiết.
- Khả năng chịu lỗi của shard giảm.

Shard02 có thể không bị ảnh hưởng trực tiếp, nhưng query scatter-gather qua cả shard01 và shard02 có thể chịu tác động nếu shard01 không đáp ứng.

### 14.4. Primary của shard lỗi

Replica set của shard có thể bầu primary mới nếu còn đủ điều kiện/quorum. Trong giai đoạn election:

- Writes tới shard đó có thể tạm thất bại/chờ retry.
- Driver/mongos cần cập nhật topology.
- Các request đang chạy có thể bị gián đoạn.
- Write concern và retryable writes/idempotency vẫn quan trọng.

**Failover của một shard không mặc nhiên khiến mọi shard khác thay primary**, nhưng các query chạm shard lỗi vẫn bị ảnh hưởng.

### 14.5. Toàn bộ một shard không khả dụng

Với sharded collection, phần document nằm trên shard không khả dụng **không tự xuất hiện ở shard khác**. Những query target riêng các shard khỏe mạnh có thể tiếp tục trong một số trường hợp; query cần dữ liệu từ shard lỗi có thể thất bại.

Không được xem cluster nhiều shards là một bản sao đầy đủ của tất cả dữ liệu. **Replication của mỗi shard** mới đảm nhiệm khả năng chịu lỗi của phần dữ liệu đó.

### 14.6. Mất một mongos so với mất một shard

| Thành phần lỗi | Dữ liệu ứng dụng ở đâu? | Hệ quả phổ biến | Cách giảm rủi ro |
| --- | --- | --- | --- |
| **Một mongos** | Vẫn ở các shards | Lỗi kết nối/router; request đang chạy có thể fail | Nhiều mongos, driver selection/retry |
| **Một secondary của shard** | Còn trên primary/other secondaries | Giảm replica redundancy, ảnh hưởng read preference | Đủ member, giám sát lag/health |
| **Primary của shard** | Replica set của shard | Failover/election, writes bị gián đoạn ngắn | Replica set đúng cấu hình, retries |
| **Một shard hoàn toàn mất** | Dữ liệu thuộc shard đó không khả dụng | Queries cần range đó fail | Replication/backup/DR của shard |
| **Một CSRS secondary** | User data vẫn ở shards | Giảm metadata redundancy | Quorum CSRS, giám sát |
| **CSRS mất quorum** | User data vẫn ở shards | Metadata changes/refresh có thể fail; CRUD tùy cache/trạng thái | Khôi phục CSRS quorum đúng quy trình |
| **Network giữa mongos và shard** | Dữ liệu chưa chắc mất | Targeting không tới được shard, timeout | Network monitoring, retry có kiểm soát |

## 15. Tính nhất quán: ba replica set khác nhau không phải một transaction

### 15.1. Shard replica set và CSRS có replication riêng

Trong cấu trúc minh họa:

~~~text
CSRS:     cfg1/cfg2/cfg3           (replication metadata)
Shard01:  s01p/s01s1/s01s2        (replication dữ liệu shard01)
Shard02:  s02p/s02s1/s02s2        (replication dữ liệu shard02)
~~~

Mỗi replica set có election, oplog, write concern/quorum riêng cho phạm vi của nó. Không thể tính majority write của shard01 bằng cách cộng phiếu của cfg1 hoặc shard02.

### 15.2. WriteConcern majority khi ghi document

Ứng dụng gửi:

~~~javascript
db.orders.insertOne(
  {
    _id: "o1002",
    tenantId: "t001",
    orderNo: "SO-1002"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

Write được định tuyến tới shard sở hữu khóa; majority acknowledgment liên quan tới replication và write concern ở shard đích. Cơ chế ghi metadata trên CSRS là phần điều phối khác, không có nghĩa mongos phải nhân bản document tới tất cả CSRS members.

### 15.3. Giao dịch trên nhiều shards

Ví dụ một thao tác chuyển tiền giữa Wallet trên shard01 và shard02 cần bảo đảm tất cả hoặc không gì:

~~~text
Transaction
  Update wallet A (shard01)
  Update wallet B (shard02)
  Insert transfer audit (có thể shard khác)
Commit transaction
~~~

MongoDB có distributed transaction coordination theo phiên bản/topology phù hợp; **mongos tham gia định tuyến và điều phối thao tác liên quan**, nhưng không phải nơi lưu mọi bản ghi. Transaction phân tán có chi phí lớn hơn một single-document update và cần retry/idempotency.

Không thể thay thế transaction bằng việc gửi ba updateOne độc lập qua cùng mongos.

### 15.4. Read preference trên từng shard

Một scatter-gather query đọc từ nhiều shards có thể chọn các node phù hợp trong từng shard theo readPreference. Nếu dùng secondaryPreferred, dữ liệu trên các shard có thể có độ trễ replication khác nhau. Với bài toán cần một ảnh chụp nhất quán xuyên nhiều collections/shards, phải xem **readConcern snapshot/transaction** theo khả năng hỗ trợ, thay vì giả định những secondary tự cùng mốc.

## 16. Quan sát topology an toàn bằng mongosh

Các lệnh sau dành cho **sharded cluster thực hành đã tồn tại**, mongosh kết nối qua **mongos**. Chúng chủ yếu **đọc metadata/status**, không tạo thêm shard, không thay đổi config server và không kích hoạt migration.

### 16.1. Kiểm tra có đang kết nối mongos không

~~~javascript
const hello = db.hello();

printjson({
  msg: hello.msg,
  isWritablePrimary: hello.isWritablePrimary,
  maxWireVersion: hello.maxWireVersion
});

if (hello.msg !== "isdbgrid") {
  throw new Error(
    "Đây không phải kết nối tới mongos; hãy dùng URI sharded cluster."
  );
}
~~~

Trên mongos, **hello** thường báo **msg: "isdbgrid"** để phân biệt với mongod. Không dùng **isWritablePrimary** riêng lẻ để chứng minh đây là mongos vì mongod primary cũng có thể ghi.

### 16.2. sh.status()

~~~javascript
sh.status();
~~~

Lệnh này trình bày tổng quan sharded cluster theo công cụ mongosh và phiên bản, có thể gồm:

- Danh sách shards.
- Thông tin active mongos/cluster metadata tương ứng.
- Database/collection sharding metadata.
- Shard key và thông tin phân phối chunks/ranges.
- Một số thông tin balancer hoặc zones nếu có.

**Output không cố định** giữa các phiên bản. Không viết parser ứng dụng production dựa trên vị trí dòng xuất ra của sh.status().

### 16.3. listShards command

~~~javascript
const result = db.getSiblingDB("admin").runCommand({
  listShards: 1
});

if (result.ok !== 1) {
  throw new Error(tojson(result));
}

printjson(
  result.shards.map(s => ({
    id: s._id,
    host: s.host,
    tags: s.tags
  }))
);
~~~

Trong output thường có:

~~~javascript
{
  _id: "shard01",
  host: "shard01-rs/s01a.example:27018,s01b.example:27018,..."
}
~~~

Đây là **hình dạng minh họa**, không phải tên node thật trong môi trường người học. Thông tin **host** giúp thấy một shard thường là một **replica set** với tên và member addresses.

Lệnh có thể yêu cầu quyền quản trị/quan sát phù hợp. Nếu bị unauthorized, cần xin quyền read-only hợp lệ thay vì tự chỉnh metadata.

### 16.4. Cách nhìn vai trò của từng thành phần

Kết hợp:

~~~text
db.hello().msg = "isdbgrid"
  -> đang nói chuyện với mongos

listShards.shards[].host
  -> các replica sets tham gia với vai trò shard

sh.status()
  -> tổng quan routing, collections và placement metadata
~~~

Không có một trường đơn giản trong listShards cho biết mọi document đang nằm ở đâu. Muốn hiểu placement theo collection phải đọc sharding metadata/commands phù hợp, không suy ra từ số lượng replica set members.

### 16.5. Trạng thái balancer

Trên phiên bản mongosh hỗ trợ:

~~~javascript
printjson({
  balancerEnabled: sh.getBalancerState()
});
~~~

Nếu có quyền và phiên bản hỗ trợ, có thể dùng command trạng thái:

~~~javascript
const result = db.getSiblingDB("admin").runCommand({
  balancerStatus: 1
});

printjson(result);
~~~

Đây là **quan sát trạng thái**, không phải lệnh bật/tắt balancer. Không chủ động chạy **sh.stopBalancer()**, **sh.startBalancer()**, **moveChunk**, **removeShard** hoặc thay đổi shard key trên cluster dùng chung chỉ để thực hành.

### 16.6. Explain của query chạy qua mongos

Giả sử cluster đã có **shop.orders** sharded và shard key:

~~~javascript
{ tenantId: 1, orderNo: 1 }
~~~

Chạy query plan chỉ đọc:

~~~javascript
const orders = db.getSiblingDB("shop")
  .getCollection("orders");

const targeted = orders.find({
  tenantId: "t001",
  orderNo: "SO-001"
}).explain("queryPlanner");

const broad = orders.find({
  status: "paid"
}).explain("queryPlanner");

printjson(targeted);
printjson(broad);
~~~

**Không chạy đoạn này nếu không có collection shop.orders lab tương ứng**; nó là ví dụ để thay bằng collection đã được cấp quyền trên cluster thực hành.

Khi phân tích explain:

- Xem những shards được nhắm tới trong plan/output.
- Xem mỗi shard dùng **IXSCAN** hay **COLLSCAN**.
- Xem có bước merge/sort giữa shards không.
- Cân nhắc khác biệt giữa query shape và dữ liệu thực.

Cấu trúc explain có thể có các stage như **SHARD_MERGE**, **SHARDING_FILTER** hoặc thông tin **shards** tùy phiên bản/query engine. **Đừng viết kiểm tra cứng** rằng nhất định phải thấy một tên stage cụ thể mới là sharded query.

### 16.7. Chỉ đọc không có nghĩa mọi output đều công khai

Tên host, shard IDs, zones, config metadata có thể tiết lộ kiến trúc hạ tầng. Không chia sẻ nguyên output vào public issue, tài liệu mở hay log ứng dụng mà chưa che thông tin nhạy cảm. Dùng quyền read-only đúng nhu cầu và xử lý bí mật cấu hình theo chính sách tổ chức.

## 17. Lab độc lập: tạo một sharded collection nhỏ (tùy chọn)

Phần này **chỉ dành cho sharded cluster thực hành cô lập** mà bạn được phép tạo database, index và sharded collection. Không thực hiện trên production hoặc cluster dùng chung. Những thao tác tạo collection, sharding DDL và index có thể thay đổi metadata/placement, nên đây là bài lab **tùy chọn**, không phải bước bắt buộc để hiểu ba vai trò.

### 17.1. Điều kiện

- Đã kết nối tới **mongos**.
- Có ít nhất một shard khả dụng, tốt hơn nhiều shard để quan sát routing.
- Có quyền tạo collection/index và sharding trên database riêng.
- Sử dụng **mongo_sharding_lab**; không trùng database thật.
- Không thay đổi config server topology, không thêm/bớt shard và không chạy lệnh move dữ liệu thủ công.
- **Mongosh** và phiên bản MongoDB có các helper được dùng; nếu khác, đối chiếu cú pháp chính thức trước khi chạy.

### 17.2. Tạo dữ liệu mẫu

~~~javascript
(() => {
  const hello = db.hello();
  if (hello.msg !== "isdbgrid") {
    throw new Error("Ví dụ chỉ chạy khi kết nối qua mongos.");
  }

  const lab = db.getSiblingDB("mongo_sharding_lab");
  const coll = lab.getCollection("lab_orders");
  const tag = "sharding-v1";

  coll.deleteMany({ dataset: tag });

  const documents = [];
  const tenants = ["t001", "t002", "t003", "t004"];
  for (let t = 0; t < tenants.length; t++) {
    for (let n = 1; n <= 5; n++) {
      const orderNo = "SO-" + String(n).padStart(3, "0");
      documents.push({
        _id: "lab-" + tenants[t] + "-" + orderNo,
        dataset: tag,
        tenantId: tenants[t],
        orderNo: orderNo,
        status: n % 2 === 0 ? "paid" : "created",
        amount: NumberDecimal(String(100 + t * 20 + n))
      });
    }
  }

  coll.insertMany(documents);
  coll.createIndex(
    { tenantId: 1, orderNo: 1 },
    { name: "ix_lab_shard_key" }
  );

  printjson({
    total: coll.countDocuments({ dataset: tag }),
    indexes: coll.getIndexes().map(i => i.name)
  });
})();
~~~

**Kết quả mong đợi:** 20 order, gồm 4 tenant, mỗi tenant 5 order. Script chỉ xóa dữ liệu mang nhãn bài tập; nếu chạy lại sau khi collection đã sharded thì nó vẫn chỉ thao tác trên các document lab.

### 17.3. Bật sharding cho collection của lab

Trong **một sharded cluster cô lập**, sau khi index shard key đã có:

~~~javascript
sh.shardCollection(
  "mongo_sharding_lab.lab_orders",
  { tenantId: 1, orderNo: 1 }
);
~~~

Một số version có quy tắc/command chuẩn bị database khác nhau; hãy dựa vào tài liệu của bản server. Không tự chạy **sh.enableSharding()** với các tham số không hiểu rõ chỉ để “kích hoạt” sharding; trên những bản MongoDB hiện đại, thao tác sharding collection có thể không cần bước enable riêng như tài liệu cũ.

**Lưu ý quan trọng:** tập 20 document rất nhỏ nên sau khi shardCollection có thể **toàn bộ dữ liệu vẫn nằm trên một shard**. Điều đó không có nghĩa sharding thất bại. MongoDB không cam kết ngay lập tức tạo nhiều chunks và phân phối đều 20 record chỉ vì cluster có nhiều shards.

### 17.4. So sánh query targeted và broad

~~~javascript
const coll = db.getSiblingDB("mongo_sharding_lab")
  .getCollection("lab_orders");

print("Query theo toàn bộ shard key:");
printjson(
  coll.find({
    dataset: "sharding-v1",
    tenantId: "t001",
    orderNo: "SO-001"
  }).explain("queryPlanner")
);

print("Query không có shard key:");
printjson(
  coll.find({
    dataset: "sharding-v1",
    status: "paid"
  }).explain("queryPlanner")
);
~~~

Ý định của bài:

- Query thứ nhất chứa equality của shard key **{tenantId,orderNo}**, mongos có cơ sở định tuyến tới range chứa khóa.
- Query thứ hai chỉ lọc **status**, có thể phải scatter-gather trên các shards liên quan.
- Vì dataset nhỏ và placement hiện tại có thể chỉ trên một shard, **số shard xuất hiện trong explain chưa phản ánh sự khác nhau về chi phí ở production**.

### 17.5. Không cố “ép” dữ liệu sang shard khác bằng thao tác quản trị

Chỉ để quan sát metadata, có thể:

~~~javascript
sh.status();
~~~

Không chạy **moveChunk**, **moveRange**, **reshardCollection**, **removeShard**, **balancerStart/Stop** hoặc can thiệp trực tiếp config collections để ép ví dụ nhỏ trông “cân bằng”. Những tác vụ đó thay đổi trạng thái cluster và chỉ nên được thực hiện trong quy trình vận hành/lab được chuẩn bị riêng.

### 17.6. Kết quả mong đợi

Người học giải thích được:

1. Tại sao API kết nối mongos, không gửi CRUD đến config server.
2. Tại sao listShards cho thấy replica set endpoints chứ không liệt kê documents.
3. Tại sao query có đủ shard key dễ target hơn.
4. Tại sao query broad có nguy cơ phải gửi tới nhiều shards.
5. Tại sao 20 document không tự phân bố đều sau shardCollection.
6. Tại sao một shard replica set có nhiều mongod members vẫn chỉ là **một shard logic**.

## 18. Kiến trúc ví dụ cho một ứng dụng nhiều tenant

### 18.1. Bối cảnh

Một nền tảng đa tenant lưu:

- **tenants**: cấu hình và trạng thái tenant.
- **orders**: đơn hàng tăng nhanh.
- **events**: sự kiện lớn, truy vấn theo tenant và thời gian.
- **payments**: giao dịch có yêu cầu audit cao.

Ứng dụng có hai dạng truy vấn chính:

~~~javascript
// Q1: lấy một order theo mã trong tenant.
db.orders.findOne({
  tenantId: "t001",
  orderNo: "SO-1001"
});

// Q2: dashboard đếm paid theo thời gian trên tất cả tenant.
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
~~~

Q1 phù hợp với shard key có tenantId + orderNo nếu phân bố và constraints cho phép. Q2 có thể cần đọc nhiều shards vì là báo cáo toàn cluster. Không có shard key nào tự đảm bảo cả hai query đều target một shard mà không đánh đổi.

### 18.2. Tách trách nhiệm theo service

~~~text
                 Order API
                    |
              MongoDB Driver
                    |
          mongos-A / mongos-B
                    |
      +-------------+-------------+
      |             |             |
   Shard01        Shard02        Shard03
  (RS riêng)     (RS riêng)     (RS riêng)
      |             |             |
      +-------------+-------------+
            Routing metadata
                    |
                  CSRS
        (config server replica set)
~~~

**Order API** chịu trách nhiệm authentication, authorization, idempotency và điều kiện nghiệp vụ. **mongos** chịu trách nhiệm routing, shard **thực thi và lưu dữ liệu**, CSRS **giữ bản đồ metadata**.

Không giao việc kiểm soát tenant authorization cho mongos. Mongos có thể chọn đúng shard cho **tenantId do client gửi**, nhưng nếu API tin tenantId sai mà không xác thực, dữ liệu vẫn có thể bị truy cập không đúng quyền.

### 18.3. Chiến lược đọc/ghi

Với order quan trọng:

- Write concern majority theo chính sách.
- Targeted writes khi filter/shard key hỗ trợ.
- Conditional update/transaction khi giữ invariant.
- Read preference theo nhu cầu read-your-writes hoặc báo cáo stale-tolerant.
- Theo dõi **p95/p99 latency**, scatter-gather rate, shard balance và replication lag.

Với dashboard:

- Có thể chạy aggregation trên nhiều shards khi thật sự cần.
- Cân nhắc summary/read model nếu query toàn cluster quá thường xuyên.
- Không cố chuyển toàn bộ dashboard sang cùng một shard chỉ để giảm fan-out nếu điều đó làm nóng shard.

## 19. Chọn số mongos, số shard và số replica set member

### 19.1. Mongos scale theo nhu cầu routing

Số mongos phụ thuộc lượng kết nối, request/aggregation, khả năng failover và vị trí mạng của các ứng dụng. Một mongos quá tải có thể thành nút cổ chai về routing/merge; thêm mongos có thể giúp phân tải router.

Nhưng nếu một query scatter-gather tới 50 shards và mỗi shard thiếu index, thêm mongos **không tự giảm tổng công việc 50 shard**.

### 19.2. Thêm shards khi cần chia dữ liệu/tải

Thêm shard làm tăng sức chứa logic và có thể giúp phân tải khi:

- Shard key có khả năng phân phối các document/workload.
- Balancer/placement thực sự chuyển các ranges thích hợp.
- Query shapes cho phép targeted queries.
- Các shard mới có đủ CPU/RAM/IOPS và replication.

Nếu một tenant khổng lồ làm nóng một giá trị shard key, thêm shard chưa chắc giảm nóng khi shard key không cho phép phân tách tải đó.

### 19.3. Replica set members để chịu lỗi, không thay thế shards

Thêm secondary trong shard01 làm tăng số bản sao dữ liệu shard01 và có thể mở thêm tùy chọn phục vụ read; nó không chia document logic của shard01 thành nhiều phần như thêm shard02.

Vì vậy, quyết định scaling cần phân biệt:

| Mục tiêu | Thay đổi có thể cân nhắc |
| --- | --- |
| Router CPU/network quá tải | Thêm mongos hoặc tối ưu query merge |
| Dung lượng/tải dữ liệu vượt một shard | Thêm shard, xem shard key/placement |
| Shard không có đủ redundancy | Cải thiện replica set của shard |
| CSRS mất quorum | Khôi phục quorum/cấu hình config server đúng quy trình |
| Một tenant làm nóng một range | Xem shard key, key cardinality, phân tải truy vấn |
| Query thường xuyên scatter-gather | Xem filter/shard key và mô hình báo cáo |

## 20. Những giới hạn và hiểu lầm quan trọng

### 20.1. Sharding không tăng giới hạn kích thước một document

MongoDB vẫn có giới hạn **16 MiB BSON document** cho document thông thường. Chia collection trên 10 shard không có nghĩa một document được phép lớn 160 MiB. Shard phân phối **nhiều document**, không cắt một document thành những phần đặt trên nhiều shard theo cách ứng dụng có thể coi như document lớn.

### 20.2. Sharding không tự làm mọi truy vấn nhanh hơn

Với một database nhỏ, sharding có thể **tăng chi phí điều phối**, network và vận hành. Nếu workload có một query phức tạp mà không thể target hẹp, scatter-gather có thể chậm hơn một query tốt trên một replica set đủ tài nguyên.

Sharding là công cụ để **mở rộng theo chiều ngang khi có nhu cầu và mô hình phù hợp**, không phải tùy chọn mặc định cho mọi collection.

### 20.3. Sharding không phải backup

Replica set bên trong shard giúp chịu lỗi một số member. Nhưng deleteMany nhầm, lỗi ứng dụng hoặc corruption logic vẫn có thể được nhân bản. Config metadata cũng cần chiến lược backup/restore thích hợp.

Một chiến lược disaster recovery cho sharded cluster phải xem xét **tính nhất quán giữa config metadata và dữ liệu shards**, không chỉ backup ngẫu nhiên một shard.

### 20.4. Nhiều shards không đồng nghĩa dữ liệu được sao chép sang tất cả shards

Đây là khác biệt cốt lõi với replica set. Shard01 chỉ lưu phần dữ liệu được định tuyến tới nó; nếu toàn bộ shard01 mất, không thể yêu cầu shard02 tự “trả bản sao đầy đủ của shard01” trừ khi có cơ chế phục hồi riêng.

### 20.5. Một router không thấy shard không chứng minh shard bị xóa

Có thể là lỗi kết nối, quyền, metadata cache hoặc topology thay đổi. Điều tra qua commands/metrics, không sửa trực tiếp config metadata.

### 20.6. Đọc từ secondary không nghĩa query không qua mongos

Ứng dụng có thể kết nối mongos với readPreference secondaryPreferred. Mongos chọn những secondary đủ điều kiện trong **mỗi shard replica set đích**. Nó không bắt ứng dụng kết nối trực tiếp tới secondary để “đọc nhanh hơn”.

### 20.7. Shard key không tự bảo đảm unique toàn cluster

Trong sharded collection, **unique index** có các ràng buộc về shard key/prefix và cách bảo đảm uniqueness giữa shards, phụ thuộc phiên bản và kiểu index. Không mặc định một unique index trên field bất kỳ (không có shard key) sẽ bảo vệ được tính duy nhất toàn cluster như trên unsharded collection.

Nếu business key như orderNo chỉ duy nhất trong tenant, cần thiết kế **tenantId + orderNo**, shard key và unique constraint cùng nhau. Không dựa vào việc các shard tự trao đổi kiểm tra duplicate toàn cluster cho mọi trường.

## 21. Bảng tổng hợp trách nhiệm

| Trách nhiệm | mongos | CSRS | Shard |
| --- | --- | --- | --- |
| Nhận kết nối CRUD của app | **Có** | Không phải nơi CRUD nghiệp vụ | Không trực tiếp cho sharded CRUD thông thường |
| Lưu document người dùng | Không | Không trong mô hình dedicated CSRS truyền thống | **Có** |
| Giữ metadata về chunk placement | Cache để routing | **Nguồn metadata cluster** | Giữ thông tin/phiên bản cần cho thực thi |
| Chọn shard cần xử lý request | **Có** | Cung cấp thông tin định tuyến | Nhận request đã định tuyến |
| Thực thi index scan/CRUD trên document | Phân phối/merge kết quả | Không làm thay shard | **Có** |
| Replica set election của shard | Không | Không | **Có, bên trong shard RS** |
| Replica set election của CSRS | Không | **Có** | Không |
| Cân bằng/migration | Routing và tham gia các thao tác điều phối tương ứng | Metadata và cơ chế coordinator/balancer | Donor/recipient di chuyển dữ liệu |
| Majority write của document | Truyền/điều phối acknowledgment | Không thay shard RS | **Các thành viên shard RS** |
| Scale query routing | Thêm router | Không phải mục tiêu chính | Không trực tiếp |
| Scale dung lượng dữ liệu | Không | Không phải nơi chứa data trong mô hình dedicated | Thêm shards/phân bố data |

## 22. Những sai lầm thường gặp

| Hiểu lầm | Vì sao sai | Cách tư duy đúng |
| --- | --- | --- |
| mongos là nơi chứa tất cả document | Mongos là query router | Data nằm trên shards |
| Config server lưu toàn bộ Order để mongos hỏi | CSRS giữ metadata | Mongos hỏi shard để đọc Order |
| Mỗi secondary là một shard | Secondary là bản sao trong cùng replica set | Shard là đơn vị dữ liệu logic riêng |
| Có ba shard nghĩa mọi document có ba bản sao | Sharding phân chia dữ liệu, không sao chép giữa shards | Mỗi shard RS lo replica của phần mình |
| Có shard key là query luôn target một shard | Filter có thể thiếu thành phần shard key hoặc range trải nhiều shards | Đánh giá targeting theo query shape và placement |
| Chỉ cần status index thì query status khỏi scatter-gather | Index trong từng shard khác routing theo shard key | Xem shard key và index đồng thời |
| Thêm mongos sẽ cân bằng data tự động | Mongos không là balancer lưu trữ | CSRS/placement + donor/recipient shards xử lý |
| Balancer làm CPU mọi shard bằng nhau | Balancer chủ yếu xử lý placement | Đo workloads và hot keys riêng |
| Một config server lỗi thì mọi CRUD dừng tức thì | Tác động phụ thuộc quorum, cache, metadata needs | Hiểu failover CSRS và điều kiện thao tác |
| CSRS là không quan trọng vì mongos có cache | Cache có thể stale và không thay metadata source | CSRS cần HA/quorum đúng |
| Có thể query shard01 trực tiếp để lấy toàn bộ collection | Shard01 giữ một phần dữ liệu | CRUD ứng dụng qua mongos |
| Đang migration thấy document ở hai shard nghĩa duplicate nghiệp vụ | Có dữ liệu tạm/orphan trong protocol | Dùng routing metadata và queries qua mongos |
| Đã thêm shard thì 20 document tự dàn đều | Dữ liệu nhỏ có thể chỉ thuộc một chunk/shard | Xem thresholds/placement thực tế |
| Primary shard của database là primary mongod | Khác khái niệm placement và election | Phân biệt database primary shard vs shard RS primary |
| Config metadata chỉ là cache, sửa tay cũng được | Có tính nhất quán/version/ownership | Chỉ dùng sharding commands hỗ trợ |
| Sharding tự làm transaction nhiều document | Các write độc lập vẫn có phạm vi riêng | Dùng transaction khi thực sự cần |
| Shard key làm trường bất kỳ unique toàn cluster | Unique index có ràng buộc sharding | Thiết kế key/constraint cùng nhau |

## 23. Bài tập thực hành và tư duy hệ thống

### Bài 1 — Vẽ kiến trúc

Một cluster có hai mongos, CSRS ba thành viên, ba shards; mỗi shard là replica set ba thành viên. Hãy vẽ sơ đồ và gắn đúng vai trò **router**, **metadata**, **data**. Tổng có bao nhiêu replica set độc lập? Một mongos có được tính là member của shard RS không?

### Bài 2 — Điều tra query thiếu Order

Ứng dụng tìm **orderNo = SO-1001** mà không cung cấp tenantId. Shard key là **{tenantId:1,orderNo:1}**. Query có thể cần đi qua bao nhiêu shard? Vì sao thêm index {orderNo:1} ở từng shard chưa bảo đảm targeting một shard?

### Bài 3 — Đọc với đầy đủ shard key

Giả sử shard key là **{tenantId:1,orderNo:1}**. Trình bày đường đi của request **find({tenantId:"t001",orderNo:"SO-1001"})** từ API đến mongos, metadata và shard. Mỗi thành phần chịu trách nhiệm gì?

### Bài 4 — Scatter-gather và merge

Một pipeline đếm đơn **paid** của mọi tenant không lọc shard key. Tại sao nó có thể chạm nhiều shards? Mongos/cluster phải làm những công việc hợp nhất nào, và khi nào nên cân nhắc một read model riêng?

### Bài 5 — Phân biệt shard RS và CSRS

Shard01-primary bị lỗi nhưng CSRS vẫn khỏe mạnh. Hãy giải thích replica set nào thực hiện election, thao tác nào bị ảnh hưởng và vì sao các shards khác không bắt buộc bầu primary mới.

### Bài 6 — Mongos hỏng

API đang dùng mongos A, A chết giữa một aggregate. Data trên các shards có biến mất không? Request hiện tại có được bảo đảm hoàn tất không? Ứng dụng cần cấu hình gì để tiếp tục qua mongos B?

### Bài 7 — CSRS mất quorum

Một CSRS ba member mất hai members; shard replica sets vẫn khỏe. Những hoạt động metadata nào có nguy cơ bị chặn? Có phải mọi CRUD chắc chắn dừng ngay không? Giải thích vai trò cache metadata và trường hợp cần refresh.

### Bài 8 — Arbiter và dữ liệu

Một shard replica set có primary, secondary và arbiter. Arbiter có chứa document của shard không? Nó đóng góp gì cho election, và vì sao không thể xem nó như bản sao có dữ liệu khi phân tích khả năng majority writes?

### Bài 9 — Migration

Một chunk chuyển từ shard01 sang shard02. Đánh dấu vai trò **donor**, **recipient**, **CSRS/coordinator**, **mongos**. Vì sao mongos có thể tạm giữ routing metadata cũ và cần refresh? Người dùng có nên kết nối thẳng donor để tìm document sau migration không?

### Bài 10 — Chọn shard key

So sánh ba ứng viên cho orders:

1. **{status:1}**
2. **{tenantId:1,orderNo:1}**
3. **{tenantId:"hashed"}**

Với workload gồm tìm order theo tenant+orderNo, liệt kê toàn bộ order một tenant và report paid toàn hệ thống, phân tích cardinality, targeting, locality, tenant lớn và hot shard.

### Bài 11 — Shard key prefix

Query chỉ lọc tenantId, trong khi shard key là {tenantId:1,orderNo:1}. Nó luôn target một shard không? Nếu một tenant trải trên nhiều chunks của các shards khác nhau, mongos sẽ làm gì?

### Bài 12 — Theo dõi an toàn

Kết nối đến sharded cluster lab bằng mongosh, chạy **db.hello()**, **sh.status()** và **listShards**. Chỉ ra bằng chứng bạn đang nói với mongos và số lượng shard replica sets. Vì sao không sửa config database để “thử routing”?

### Bài 13 — Explain

Trên một sharded collection lab có shard key thích hợp, so sánh explain của query có **toàn bộ shard key equality** với query chỉ lọc một field không thuộc shard key. Đọc shards được target, IXSCAN/COLLSCAN và bước merge; không giả định stage name cố định giữa các phiên bản.

### Bài 14 — Collection nhỏ sau sharding

Bạn tạo 20 Order rồi chạy sh.shardCollection, nhưng sh.status cho thấy dữ liệu vẫn chỉ nằm trên một shard. Đây có chắc là lỗi? Nêu vai trò chunk size, phân bố dữ liệu và hoạt động balancer; vì sao không nên ép moveChunk trên cluster chung?

### Bài 15 — Scale router và scale data

Cluster có 50 mongos nhưng một shard đang 95% CPU và một shard chỉ 20%. Thêm mongos có giải quyết nóng shard không? Hãy đề xuất kế hoạch kiểm tra query patterns, shard key, data placement, index và workloads.

### Bài 16 — Global uniqueness

Ứng dụng yêu cầu orderNo duy nhất **trong tenant**, nhưng hai tenant có thể dùng cùng mã SO-001. Bạn chọn shard key và unique index nào? Vì sao không nên mặc định unique index chỉ trên orderNo sẽ được bảo đảm toàn cluster ở mọi cấu hình sharded?

### Bài 17 — Read preference

Ứng dụng kết nối mongos với readPreference secondaryPreferred. Query target shard01 và shard02. Ai chọn node secondary trong từng shard? Nếu secondary của shard02 chậm và dữ liệu cũ, điều gì ảnh hưởng kết quả báo cáo? Nêu cách dùng read concern/session khi cần mốc nhất quán.

### Bài 18 — Invariant xuyên hai shards

Chuyển 500 đơn vị giữa hai Wallet có shard keys khác nhau, wallet A ở shard01, wallet B ở shard02. Hai updateOne độc lập có tự all-or-nothing chỉ vì cùng gửi qua mongos không? Đề xuất transaction/idempotency và lý do không gọi payment gateway trong callback transaction.

### Bài 19 — Zones và compliance

Một tenant yêu cầu dữ liệu ở EU. Zones có thể hỗ trợ placement thế nào? Những nghĩa vụ nào vẫn phải do ứng dụng/quy trình vận hành xử lý (tenant authorization, backup, encryption, kiểm soát migration)?

### Bài 20 — Phân tích sự cố theo vai trò

Ba sự cố xảy ra riêng: (a) mongos A chết; (b) CSRS mất majority; (c) toàn shard02 mất kết nối. Với mỗi sự cố, hãy nêu:

- Thành phần nào lưu data ứng dụng có nguy cơ không truy cập được?
- Những thao tác nào có thể tiếp tục?
- Những thao tác metadata nào bị ảnh hưởng?
- Client và driver cần retry thế nào?
- Monitoring nào cần đọc trước khi thay đổi hạ tầng?

### Bài 21 — Thiết kế vận hành

Đề xuất dashboard có các nhóm thông tin: **mongos request rate**, **routing targets per query**, **shard CPU/IOPS**, **replication lag**, **balancer/migration activity**, **config server health**, **scatter-gather percentage**. Giải thích vì sao chỉ đo tổng QPS của cluster là chưa đủ.

### Bài 22 — Kết nối đúng nơi

Một developer dùng URI trực tiếp tới **shard01-primary** để chạy countDocuments trên sharded collection orders rồi nhận số nhỏ hơn dashboard. Hãy giải thích nguyên nhân, nguy cơ của direct shard access và cách sửa bằng kết nối tới mongos.

## 24. Tài liệu tham khảo MongoDB

- MongoDB Manual — [Sharding](https://www.mongodb.com/docs/manual/sharding/).
- MongoDB Manual — [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/).
- MongoDB Manual — [mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/).
- MongoDB Manual — [Config Servers](https://www.mongodb.com/docs/manual/core/sharded-cluster-config-servers/).
- MongoDB Manual — [Shards](https://www.mongodb.com/docs/manual/core/sharded-cluster-shards/).
- MongoDB Manual — [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/).
- MongoDB Manual — [Targeted Operations versus Broadcast Operations](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/).
- MongoDB Manual — [Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/).
- MongoDB Manual — [Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/).
- MongoDB Manual — [sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/).
- MongoDB Manual — [listShards](https://www.mongodb.com/docs/manual/reference/command/listShards/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Distributed Transactions](https://www.mongodb.com/docs/manual/core/transactions-sharded-clusters/).

**Kết luận:** Trong MongoDB sharded cluster, **mongos là cửa vào và router**, **config server replica set giữ bản đồ metadata của cluster**, còn **các shard lưu và xử lý dữ liệu người dùng**. Mỗi shard thường có replica set riêng để chịu lỗi; điều đó khác với việc chia collection theo shard key. Một query có đầy đủ thông tin shard key có thể được định tuyến hẹp, trong khi query không đủ điều kiện thường phải **scatter-gather**. Balancer và chunk migration thay đổi **placement**, nên mongos phải duy trì routing metadata đúng. Thiết kế tốt bắt đầu từ **query patterns, shard key, index, topology và failure model**, không phải từ số lượng server; hiểu rõ ba vai trò là nền tảng để mở rộng MongoDB mà vẫn kiểm soát độ trễ, tính nhất quán và khả năng phục hồi.
