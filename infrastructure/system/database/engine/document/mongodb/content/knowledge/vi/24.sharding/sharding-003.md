# Phân bố dữ liệu, metadata định tuyến, chunk và balancer trong MongoDB Sharding

Khi một collection tăng đến mức không còn phù hợp để đặt toàn bộ dữ liệu và tải truy cập trên một nhóm máy, **sharding** cho phép MongoDB phân bố document của collection trên nhiều **shard**. Mục tiêu có thể là mở rộng dung lượng lưu trữ, phân tán tải ghi, tăng khả năng xử lý truy vấn hoặc đặt một phần dữ liệu vào những vùng hạ tầng nhất định.

Tuy nhiên, MongoDB không đơn giản “chia đều từng document theo số lượng máy”. Việc một document thuộc shard nào dựa vào **shard key**, các **khoảng giá trị (ranges/chunks)**, **metadata định tuyến** và các **quy tắc phân bố**. Router **mongos** dựa trên metadata để gửi truy vấn tới những shard thích hợp; **balancer** làm công việc dịch chuyển những khoảng dữ liệu cần thiết để đạt mục tiêu cân bằng theo cơ chế và phiên bản đang dùng.

Bốn khái niệm cốt lõi của bài:

1. **Phân bố dữ liệu:** shard key và cách ánh xạ giá trị shard key sang các shard.
2. **Metadata định tuyến:** thông tin MongoDB lưu về database, collection, chunk/range và shard sở hữu, dùng để chọn đích truy vấn.
3. **Chunk:** khoảng liên tiếp trong không gian giá trị shard key, là đơn vị logic quan trọng của quản lý vị trí dữ liệu.
4. **Balancer:** cơ chế nền điều phối việc phân bố/migration các chunk hoặc ranges giữa shard khi cần.

Điểm cần nhớ ngay từ đầu:

> **Sharding không tự biến một truy vấn thành truy vấn nhanh.** Muốn lợi ích của phân bố tải, phải chọn shard key phù hợp, định tuyến đúng, có index phục vụ truy vấn trên từng shard, và vận hành metadata/balancer với khả năng quan sát rõ ràng.

Bài học sử dụng minh họa theo **mongosh** và **Java Sync Driver**, kèm phương pháp đọc kết quả, những kịch bản lệch tải, sự cố migration và bài thực hành. Cú pháp quản trị thay đổi theo phiên bản MongoDB: những thao tác thay đổi cấu hình cluster phải được đối chiếu với phiên bản và chỉ thực hiện trên lab hoặc theo quy trình được phê duyệt.

## 1. Kiến trúc tổng quát của sharded cluster

Một MongoDB sharded cluster có ba thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| **Shard** | Lưu tập con dữ liệu; trong production thường là một replica set |
| **mongos** | Router nhận lệnh từ client, dùng metadata để định tuyến tới shard |
| **Config server replica set (CSRS)** | Lưu metadata cấu hình của sharded cluster, gồm thông tin cần cho định tuyến |

Sơ đồ:

~~~text
                      APPLICATION / DRIVER
                              |
                              v
                       +-------------+
                       |    mongos   |
                       | Query router|
                       +-------------+
                          |       ^
          Routing request |       | Metadata cache / refresh
                          v       |
                 +----------------------+
                 | Config Server RS     |
                 | Sharding metadata    |
                 +----------------------+
                          |
            +-------------+-------------+
            |             |             |
            v             v             v
       +---------+   +---------+   +---------+
       | Shard A |   | Shard B |   | Shard C |
       |Replica  |   |Replica  |   |Replica  |
       |   set   |   |   set   |   |   set   |
       +---------+   +---------+   +---------+
~~~

Sơ đồ giản lược: trong thực tế, mongos lấy/cập nhật metadata cần thiết từ config servers, gửi yêu cầu trực tiếp tới các shard, và nhận kết quả; không phải mỗi request đều đi qua config server trên đường dữ liệu.

### 1.1. Shard không đồng nghĩa một tiến trình mongod

Trong production, mỗi shard thường là **replica set** có primary và các secondary.

~~~text
Shard A:
  A1 PRIMARY
  A2 SECONDARY
  A3 SECONDARY

Shard B:
  B1 PRIMARY
  B2 SECONDARY
  B3 SECONDARY
~~~

Nhờ đó:

- **Sharding** phân chia dữ liệu giữa shard A và B.
- **Replication** tạo bản sao dữ liệu bên trong từng shard.

Hai cơ chế giải quyết hai vấn đề khác nhau: **horizontal partitioning** và **high availability**. Thêm một secondary không tự làm tăng số shard để phân tán dung lượng; thêm shard không tự thay thế replication trong mỗi shard.

### 1.2. Mongos có lưu dữ liệu nghiệp vụ không?

Mongos là router, không lưu một bản collection đầy đủ như shard. Nó sử dụng metadata và chuyển tiếp các thao tác, đôi khi hợp nhất kết quả từ nhiều shard.

Nếu một truy vấn không đủ thông tin để xác định shard đích, mongos có thể phải gửi truy vấn tới nhiều shard. Đây là kiểu **scatter-gather**.

### 1.3. Config server giữ gì?

Config servers giữ những thông tin điều khiển sharding, như:

- Danh sách shard và thuộc tính liên quan.
- Thông tin database/collection đã được shard.
- Cấu hình shard key của collection.
- Vị trí và ranh giới các chunk/ranges.
- Tags/zones dùng để ràng buộc phân bố.
- Metadata versioning và những thông tin phục vụ điều phối migration.

**Không trực tiếp sửa các collection nội bộ trong database config** bằng thao tác CRUD thông thường. MongoDB có các lệnh quản trị cho sharding và cơ chế nhất quán metadata riêng.

## 2. Dữ liệu được phân bố bằng shard key

**Shard key** là một field hoặc tổ hợp field MongoDB dùng để phân hoạch document trong một sharded collection.

Ví dụ document đơn hàng:

~~~javascript
{
  _id: "ORD-1001",
  tenantId: "TENANT-A",
  orderId: "ORD-1001",
  customerId: "C-01",
  orderDate: ISODate("2026-11-01T09:00:00Z"),
  totalCents: NumberLong(250000),
  status: "PAID"
}
~~~

Một cách chọn shard key:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Đây là **compound ranged shard key**. Giá trị shard key của một document là cặp **(tenantId, orderId)**, được so sánh theo thứ tự khóa.

Ví dụ thứ tự:

~~~text
("TENANT-A", "ORD-1001")
("TENANT-A", "ORD-1002")
("TENANT-A", "ORD-1003")
("TENANT-B", "ORD-0001")
("TENANT-C", "ORD-9001")
~~~

MongoDB phân bố những khoảng của không gian khóa này giữa các shard.

### 2.1. Shard key không phải index thông thường

Index giúp truy vấn lọc/sắp xếp nhanh trên một shard; shard key còn xác định **cách chia dữ liệu và định tuyến trong toàn cluster**.

Một query vẫn cần index phù hợp ở shard nhận lệnh. Có shard key đúng không tự bảo đảm mọi filter hay sort đều được tối ưu.

### 2.2. Shard key cần phục vụ cả đọc và ghi

Các tiêu chí quan trọng:

- **Cardinality:** có đủ giá trị khác nhau để chia dữ liệu hay không.
- **Frequency distribution:** có giá trị nào xuất hiện áp đảo không.
- **Monotonicity:** giá trị có tăng liên tục dẫn đến write hotspot không.
- **Query patterns:** các truy vấn có mang shard key để định tuyến không.
- **Write throughput:** các write có phân tán qua shard hay dồn về một vùng.
- **Chunk/range mobility:** dữ liệu có thể chia ra các khoảng hợp lý để di chuyển không.
- **Business requirements:** tenant isolation, region affinity, data placement và quyền truy cập.

### 2.3. Ví dụ shard key không cân bằng

Chọn:

~~~javascript
{ status: 1 }
~~~

trong collection orders mà hầu hết document có status = "PAID" là rủi ro:

- Cardinality thấp.
- Nhiều document cùng một giá trị.
- Khó phân chia dữ liệu nóng theo status.
- Các truy vấn ghi thường xuyên vào cùng phần khóa có thể gây hotspot.

Không nên suy rằng một shard key tốt chỉ vì field xuất hiện trong nhiều filter.

### 2.4. Ví dụ shard key tăng đều theo thời gian

Chọn key ranged:

~~~javascript
{ createdAt: 1 }
~~~

Khi phần lớn insert có createdAt ngày càng tăng, write thường dồn vào **khoảng giá trị mới nhất**, có thể nằm trên một shard ở thời điểm đó.

Đây là hiện tượng **monotonically increasing shard key hotspot**. Hashing hoặc lựa chọn key có khả năng phân tán tốt hơn có thể hữu ích, nhưng phải xét tác động lên truy vấn range và yêu cầu locality.

## 3. Range sharding và hashed sharding

MongoDB hỗ trợ những cách phân phối theo shard key, thường thảo luận qua hai kiểu chính:

| Kiểu | Ý tưởng | Thế mạnh | Đánh đổi |
| --- | --- | --- | --- |
| **Ranged shard key** | Chia các khoảng giá trị khóa theo thứ tự BSON | Định tuyến range có thể hiệu quả; locality rõ hơn | Dễ hotspot với khóa tăng đều hoặc phân bố lệch |
| **Hashed shard key** | Hash giá trị shard key để trải dữ liệu trên hash space | Giảm tương quan giữa thứ tự giá trị và vị trí lưu; phân tán nhiều kiểu khóa | Truy vấn range trên giá trị gốc khó nhắm vào ít shard |

### 3.1. Ranged key

Ví dụ:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Các chunk có thể mang những khoảng như:

~~~text
Chunk 1: [MinKey, ("TENANT-A", "ORD-5000"))
Chunk 2: [("TENANT-A", "ORD-5000"), ("TENANT-B", "ORD-0000"))
Chunk 3: [("TENANT-B", "ORD-0000"), MaxKey)
~~~

Đây là ví dụ logic; trong một compound key, ranh giới thực tế là tuple và tuân theo BSON ordering.

### 3.2. Hashed key

Ví dụ:

~~~javascript
{ customerId: "hashed" }
~~~

MongoDB ánh xạ giá trị customerId sang hash space để phân bố. Những customerId kế tiếp nhau về thứ tự chữ không nhất thiết gần nhau trong không gian hash.

Filter equality với customerId vẫn có thể được chuyển thành giá trị hash để định tuyến. Nhưng truy vấn:

~~~javascript
{
  customerId: {
    $gte: "C-1000",
    $lt: "C-2000"
  }
}
~~~

không tự trở thành một đoạn liên tiếp nhỏ trên hash space, nên có thể phải xét nhiều shard.

### 3.3. Hashed không chữa mọi hotspot

Nếu một tenant hay một giá trị shard key duy nhất có rất nhiều write, **cùng giá trị hash sẽ ánh xạ về cùng vị trí logic**. Hashing không tự chia một giá trị shard key duy nhất thành nhiều key.

Có thể cần key compound phù hợp, bucketing hoặc mô hình phân bố khác nếu một logical key quá nóng.

### 3.4. Không chọn shard key trước khi phân tích workload

Một key giúp insert cân bằng nhưng làm mọi truy vấn phân tích trở thành scatter-gather có thể gây chi phí lớn.

Trước khi chọn, thu thập:

- Các query filter phổ biến.
- Các update/delete và trường được dùng để tìm document.
- Các sort và range query chính.
- Tỷ lệ write/read, kích thước document.
- Phân bố giá trị, tenant lớn và tenant nhỏ.
- Truy vấn xuyên tenant, báo cáo tổng hợp và join.
- Yêu cầu vùng dữ liệu và thay đổi trong tương lai.

## 4. Chunk là gì?

Trong sharding, **chunk** là một **khoảng liên tiếp trong không gian giá trị shard key** của một collection. MongoDB quản lý và phân bố các khoảng này giữa những shard.

Ví dụ key ranged là **{ tenantId: 1, orderId: 1 }**:

~~~text
Key space (sắp xếp theo shard key)
MinKey ------------------------------------------------ MaxKey

  [Range A)       [Range B)        [Range C)       [Range D)
      |               |                |               |
    Shard 1         Shard 2          Shard 1          Shard 3
~~~

Một chunk chứa những document có giá trị shard key nằm trong khoảng của nó.

### 4.1. Ranh giới kiểu nửa mở

Thường mô tả chunk bằng:

\[
[\text{min}, \text{max})
\]

Nghĩa là:

- **min** được bao gồm.
- **max** không được bao gồm.
- Hai chunk kề nhau có thể dùng ranh giới chung mà không chồng lặp.
- Mỗi giá trị shard key thuộc một khoảng logic phù hợp.

Ví dụ:

~~~text
Chunk A: [100, 200)
Chunk B: [200, 300)

key = 199 thuộc Chunk A
key = 200 thuộc Chunk B
~~~

### 4.2. Chunk không phải một file trên disk

Chunk là **đơn vị logic của phân bố**, không phải một file vật lý riêng hoặc một partition file độc lập mà người dùng có thể mở trong filesystem.

Một shard vẫn lưu document qua storage engine và index. Metadata ánh xạ **khoảng shard key** tới shard sở hữu.

### 4.3. Chunk và document không phải quan hệ một–một

Một chunk thường chứa nhiều document. MongoDB không tạo một chunk mới cho mỗi document.

Số lượng document trong hai chunk có thể khác xa nhau dù kích thước dữ liệu tương tự, vì document có size khác nhau.

### 4.4. Chunk target size không phải giới hạn tuyệt đối

MongoDB có cấu hình mục tiêu về kích thước chunk/range để hỗ trợ cân bằng. Con số mặc định và hành vi splitting/merging đã thay đổi giữa các phiên bản; ví dụ nhiều bản phát hành hiện đại có default chunk size mục tiêu **128 MiB**.

**Đây không phải cam kết mỗi chunk luôn nhỏ hơn 128 MiB.** Những chunk có thể lớn hơn mục tiêu do dữ liệu, việc phân chia, khóa có giá trị lặp hoặc tình trạng migration.

Không nên dùng chunk count làm đại diện chính xác cho số byte dữ liệu.

## 5. Từ shard key tới chunk rồi tới shard

Một document có khóa:

~~~text
tenantId = TENANT-B
orderId  = ORD-1010
~~~

Mongos phải biết:

1. Collection đã shard chưa?
2. Shard key pattern của collection là gì?
3. Giá trị khóa có thuộc chunk/range nào?
4. Chunk đó hiện do shard nào sở hữu?
5. Shard nào phải nhận operation?

Ví dụ bảng metadata mô phỏng:

| Khoảng key | Shard sở hữu |
| --- | --- |
| [MinKey, ("TENANT-A","ORD-5000")) | shard-a |
| [("TENANT-A","ORD-5000"), ("TENANT-B","ORD-5000")) | shard-b |
| [("TENANT-B","ORD-5000"), MaxKey) | shard-c |

Document có **("TENANT-B", "ORD-1010")** nằm trong khoảng thứ hai theo thứ tự tuple, nên mongos có thể định tuyến tới **shard-b**.

Bảng chỉ minh họa: ranh giới thực tế phụ thuộc key, BSON ordering và metadata của cluster.

### 5.1. Một shard có thể sở hữu nhiều chunk

~~~text
Shard A:
  Chunk 1
  Chunk 4
  Chunk 7

Shard B:
  Chunk 2
  Chunk 6

Shard C:
  Chunk 3
  Chunk 5
~~~

Một shard không nhất thiết sở hữu một khoảng lớn duy nhất. Khi balancer migration hoặc quá trình phân chia thay đổi phân bố, shard có thể sở hữu nhiều khoảng không kề nhau trong key space.

### 5.2. Dữ liệu cùng giá trị shard key

Document có thể cùng chia sẻ một giá trị shard key. Điều quan trọng là MongoDB không thể chia **một giá trị shard key không thể phân biệt** thành các chunk riêng chỉ nhờ cắt ranh giới nằm giữa chính những giá trị giống nhau.

Nếu quá nhiều document có cùng giá trị khóa, có thể dẫn đến range/chunk khó chia hoặc di chuyển hiệu quả. Chọn shard key có cardinality và phân bố phù hợp là quyết định từ đầu rất quan trọng.

## 6. Phân biệt chunk split, merge và migration

Ba hành động này có ngữ nghĩa khác nhau:

| Hành động | Ý nghĩa | Có tự đổi shard sở hữu không? |
| --- | --- | --- |
| **Split** | Chia một khoảng shard key thành các khoảng nhỏ hơn | Thường không; các khoảng mới ban đầu ở cùng shard |
| **Merge** | Hợp nhất những khoảng kề nhau thỏa điều kiện | Không nhất thiết đổi shard sở hữu |
| **Migration / Move** | Chuyển quyền sở hữu một khoảng/chunk từ shard nguồn sang shard đích | **Có** |

### 6.1. Split không đồng nghĩa dữ liệu được chuyển đi

Ví dụ:

~~~text
Trước:
Shard A sở hữu [0, 1000)

Sau split:
Shard A sở hữu [0, 500)
Shard A sở hữu [500, 1000)
~~~

Số chunk tăng từ một lên hai, nhưng dữ liệu vẫn ở Shard A.

### 6.2. Migration có thể thay phân bố

~~~text
Trước:
Shard A: [0, 500), [500, 1000)
Shard B: [1000, 1500)

Sau move chunk:
Shard A: [0, 500)
Shard B: [500, 1000), [1000, 1500)
~~~

Dữ liệu có shard key thuộc **[500, 1000)** được chuyển quyền sở hữu logic từ A sang B theo quy trình migration.

### 6.3. Cơ chế split/merge khác theo phiên bản

Không nên ghi nhớ cứng rằng “mỗi khi chunk vượt ngưỡng, MongoDB tự split ngay”. Các cơ chế **automatic splitting, auto-merging và range management** đã thay đổi đáng kể theo phiên bản MongoDB.

Khi vận hành, hãy đọc tài liệu đúng release. Bài học này tập trung vào **bản chất logical ranges và balancing**, không xem một tên lệnh split cũ là hành vi phổ quát của mọi phiên bản.

## 7. Metadata định tuyến được lưu ở đâu?

**Config server replica set** giữ metadata cấu hình sharded cluster.

Một số loại metadata logic:

| Thông tin | Công dụng |
| --- | --- |
| Database metadata | Database thuộc cluster và thông tin placement liên quan |
| Collection metadata | Namespace, UUID, shard key, cấu hình sharding |
| Chunk/range metadata | Từ min tới max, shard sở hữu, thông tin version |
| Shard registry | Các shard của cluster, địa chỉ kết nối |
| Zone/tag metadata | Phạm vi shard key được yêu cầu nằm trong nhóm shard nhất định |
| Migration state / coordination | Thông tin hỗ trợ điều phối việc di chuyển dữ liệu |

Trong một số phiên bản, những loại metadata này có thể nhìn thấy qua các collection nội bộ ở database **config**, nhưng **schema nội bộ không phải API ổn định để ứng dụng sửa trực tiếp**.

### 7.1. Vì sao metadata rất quan trọng?

Nếu mongos không biết chunk có key **K** đang nằm ở shard nào, nó không thể định tuyến chính xác theo mô hình sharding.

Đặc biệt khi migration hoàn tất, **quyền sở hữu range thay đổi**. Metadata phải phản ánh trạng thái mới để những router tiếp tục gửi đúng shard.

### 7.2. Config servers không nằm trên đường dữ liệu của mỗi request

Một cách hiểu sai:

~~~text
Client -> mongos -> config servers -> shard -> config servers -> client
~~~

Đây không phải chuỗi xử lý thông thường của mỗi CRUD request.

Mongos **cache** routing metadata cần thiết. Khi nhận operation, router thường sử dụng thông tin cache để chọn shard. Khi metadata thay đổi hoặc bị coi là cũ, nó cập nhật từ nguồn metadata phù hợp.

### 7.3. Metadata khác dữ liệu collection

Config servers không phải shard chứa mọi order. Chúng lưu **thông tin vị trí, cấu trúc và điều phối**.

Vì vậy không nên dùng config server để chạy các truy vấn nghiệp vụ trên collection orders, hoặc cố xây index nghiệp vụ ở đó.

## 8. Mongos định tuyến bằng cached metadata

Quy trình ở mức logic:

~~~text
Application -> mongos
                |
                v
         Parse operation
                |
                v
       Xác định namespace
                |
                v
     Lấy shard key / ranges
        từ routing cache
                |
                v
   Target một/nhiều shard phù hợp
                |
                v
       Shard thực thi query
                |
                v
      Mongos merge kết quả
                |
                v
            Application
~~~

### 8.1. Routing cache giúp giảm overhead

Nếu mỗi query đều phải đọc config server trước khi chạy, config server dễ thành bottleneck. Vì vậy mongos có thể giữ routing metadata trong cache và sử dụng cơ chế refresh/invalidation thích hợp.

### 8.2. Cached metadata có thể bị cũ

Ví dụ chunk trước đây ở Shard A, sau migration chuyển sang Shard B. Mongos M1 chưa cập nhật vị trí mới và gửi request theo cache cũ.

MongoDB có cơ chế **metadata versioning** và phản hồi về routing stale để router refresh và thực hiện lại quá trình định tuyến theo điều kiện hỗ trợ. Các tên lỗi hoặc chi tiết nội bộ thay đổi theo phiên bản.

Ứng dụng thông thường không nên tự duy trì bảng chunk-location của riêng mình rồi định tuyến trực tiếp vào shard; hãy để mongos/driver thực hiện cơ chế định tuyến được hỗ trợ.

### 8.3. Mongos có cần restart sau migration không?

Không. Hệ thống được thiết kế để cập nhật routing metadata mà không yêu cầu mỗi lần di chuyển chunk đều phải restart toàn bộ mongos.

Nếu ứng dụng chỉ hoạt động sau khi restart router, đó là dấu hiệu cần điều tra metadata, kết nối hoặc lỗi tương thích, không phải quy trình vận hành bình thường.

## 9. Targeted query và scatter-gather

Đây là hệ quả rõ nhất của routing metadata đối với ứng dụng.

### 9.1. Targeted query

Giả sử collection orders được shard theo:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
});
~~~

cung cấp đầy đủ key của document, nên mongos có đủ thông tin để định tuyến tới range chứa khóa tương ứng.

### 9.2. Targeted vào nhiều chunk chưa chắc chỉ một shard

Query:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A"
});
~~~

với compound shard key có tenantId làm prefix có thể giới hạn các **khoảng key liên quan tới TENANT-A**. Tuy nhiên, nếu một tenant trải qua nhiều chunk trên nhiều shard, query vẫn phải gửi tới nhiều shard.

Vì vậy, “query có shard key” **không mặc nhiên đồng nghĩa chỉ một shard**. Phải xem predicate có xác định được một khoảng/điểm cụ thể và metadata phân bố ra sao.

### 9.3. Scatter-gather

Query:

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

không chứa shard key tenantId/orderId. Nếu mongos không thể suy ra shard đích từ các điều kiện khác, nó có thể gửi query tới **nhiều hoặc tất cả shard liên quan**, sau đó hợp nhất kết quả.

~~~text
                    mongos
                  /   |    \
                 v    v     v
              Shard A B     C
                 \    |    /
                  \   |   /
                 Merge results
~~~

### 9.4. Scatter-gather không luôn sai

Các truy vấn báo cáo xuyên tenant hoặc thống kê toàn cluster có thể cần quét nhiều shard là hợp lý.

Nhưng nếu truy vấn phổ biến của API latency-sensitive luôn scatter-gather, shard key có thể không phù hợp access patterns.

### 9.5. Index vẫn cần trên shard

Một query được định tuyến chính xác tới một shard nhưng thiếu index vẫn có thể dùng **COLLSCAN** trên shard đó.

Ngược lại, scatter-gather query có index tốt trên từng shard vẫn phải chịu overhead gửi request và hợp nhất kết quả.

Hai tầng cần tối ưu song song:

1. **Routing:** bao nhiêu shard được target.
2. **Local execution:** mỗi shard dùng plan/index nào.

## 10. Explain trong sharded cluster

Trên kết nối **mongos**, dùng:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
}).explain("executionStats");
~~~

So sánh với:

~~~javascript
db.orders.find({
  status: "PAID"
}).explain("executionStats");
~~~

Mục tiêu quan sát:

- Những shard nào tham gia.
- Có phải một shard hay nhiều shard.
- Stage và plan trong từng shard.
- Tổng documents/keys examined, nếu executionStats cung cấp.
- Thời gian thực thi và công đoạn merge.

Cấu trúc explain và tên stage có thể thay đổi giữa query engines/phiên bản MongoDB. Một số plan hiển thị các cấu trúc sharded query hoặc merge riêng; không phụ thuộc cứng vào một tên stage duy nhất.

### 10.1. Không so thời gian giữa hai query khác dữ liệu

Muốn so sánh targeted và scatter-gather có ý nghĩa, cần xét:

- Predicate tương đương về độ chọn lọc.
- Index tương ứng.
- Cache warm/cold.
- Số lượng document.
- Số shard.
- Hình dạng kết quả và sort/limit.
- Độ trễ mạng.

Kết luận “targeted luôn nhanh gấp N lần” từ một lần explain đơn lẻ không đáng tin.

## 11. Sort, limit và aggregation trên nhiều shard

Mongos có thể cần **merge** kết quả từ nhiều shard.

Ví dụ:

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({ orderDate: -1 })
.limit(20);
~~~

Nếu query chạm nhiều shard, quá trình thực thi có thể gồm:

- Các shard lọc và tạo kết quả trung gian.
- Các shard hoặc mongos tham gia sắp xếp theo plan.
- Mongos hợp nhất những phần đã nhận.
- Áp dụng limit theo ngữ nghĩa toàn truy vấn.

Khả năng đẩy một số stage xuống shard phụ thuộc pipeline và optimizer.

### 11.1. $group xuyên shard

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 },
      totalCents: { $sum: "$totalCents" }
    }
  }
]);
~~~

Pipeline này có thể cần aggregate cục bộ trên nhiều shard rồi hợp nhất kết quả theo semantics của $group.

### 11.2. Định tuyến tốt vẫn không đủ cho join lớn

$lookup, $graphLookup, sort lớn và group lớn có thể tạo workload nặng khi collection phân tán. Cần xem các điều kiện hỗ trợ của phiên bản, index của collection được join, và explain thay vì giả định mọi aggregation tự chạy hoàn toàn song song và tuyến tính khi thêm shard.

## 12. Balancer làm nhiệm vụ gì?

**Balancer** là cơ chế quản lý phân bố dữ liệu nền của sharded cluster. Nó xem xét vị trí các ranges/chunks và các chính sách, rồi có thể điều phối migration giữa những shard khi cần.

Ví dụ ban đầu:

~~~text
Shard A: 8 chunks
Shard B: 2 chunks
Shard C: 2 chunks
~~~

Nếu phù hợp với logic cân bằng của phiên bản và không bị các ràng buộc khác chặn, MongoDB có thể di chuyển một số chunk/range từ A sang B/C theo thời gian.

**Không nên suy rằng balancer luôn cố làm số chunk trên mọi shard bằng nhau chính xác.** Các thuật toán hiện đại có thể sử dụng những tiêu chí khác như mức dữ liệu và các ngưỡng liên quan; zones, oversized ranges và giới hạn vận hành cũng ảnh hưởng.

### 12.1. Balancer không có nghĩa tất cả shard sẽ có cùng số document

Document có kích thước khác nhau. Một chunk có 10.000 document nhỏ có thể ít byte hơn chunk chỉ có 100 document lớn.

Balancer không thể bảo đảm mỗi shard có **bằng nhau số row, byte, CPU, IOPS và query latency**. Đây là những đại lượng khác nhau.

### 12.2. Balancer không sửa shard key kém

Nếu nhiều write dồn vào **một giá trị shard key duy nhất**, migration của các khoảng xung quanh chưa chắc giúp phân tán write của giá trị đó.

Cân bằng storage và cân bằng **workload** không đồng nghĩa. Một shard có dung lượng thấp nhưng đang nhận hầu hết write vẫn có thể là bottleneck.

### 12.3. Khi nào balancing diễn ra?

Quyết định có migration phụ thuộc:

- Trạng thái balancer.
- Phân bố hiện tại theo thuật toán của phiên bản.
- Chunk/range có thể di chuyển được không.
- Kích thước và giới hạn migration.
- Zones và tags.
- Trạng thái shard nguồn/đích.
- Các hoạt động bảo trì hoặc migration khác.
- Tính tương thích của cluster.

Không nên nói mỗi insert sẽ gây một lần balancing hoặc sau khi thêm shard dữ liệu sẽ lập tức phân bố đều.

## 13. Các giai đoạn logic của chunk migration

Một migration cần chuyển dữ liệu và cập nhật quyền sở hữu range theo quy trình nhất quán.

Ở mức khái niệm:

~~~text
1. Chọn range/chunk cần chuyển
2. Chọn donor shard và recipient shard
3. Recipient nhận/copy dữ liệu cần thiết
4. Đồng bộ những thay đổi xảy ra trong quá trình copy
5. Điều phối commit quyền sở hữu range
6. Routing metadata được cập nhật
7. Dọn dữ liệu cũ/orphans khi đủ điều kiện
~~~

Đây là mô hình logic, không phải API từng bước để ứng dụng tự gọi. Trình tự nội bộ và các phase thực tế có thể thay đổi theo MongoDB release.

### 13.1. Donor và recipient

- **Donor:** shard đang sở hữu dữ liệu trước migration.
- **Recipient:** shard nhận dữ liệu và quyền sở hữu sau migration.

Trong migration, MongoDB phải xử lý việc dữ liệu tiếp tục thay đổi khi copy đang diễn ra, đồng thời bảo đảm không có hai shard cùng được coi là owner hợp lệ của cùng range sau commit metadata.

### 13.2. Metadata commit là ranh giới quan trọng

Không đủ nếu recipient chỉ copy xong file/document. Router còn phải biết **range hiện thuộc shard nào**.

Chính vì vậy chunk migration gắn với metadata versioning và refresh của mongos.

### 13.3. Orphaned documents

Sau migration, dữ liệu vật lý cũ trên donor có thể còn tồn tại tạm thời trong quá trình cleanup. Chúng thường được gọi là **orphaned documents** theo ngữ cảnh sharding.

Sự tồn tại tạm thời của dữ liệu cũ không có nghĩa hai shard được phép cùng trả document như hai owner hợp lệ. MongoDB có cơ chế lọc/ownership theo metadata để giải quyết sự khác biệt giữa bản sao vật lý đang cleanup và quyền sở hữu logic.

### 13.4. Migration có thể ảnh hưởng latency

Copy dữ liệu, đồng bộ thay đổi và thay ownership tạo thêm I/O/network/CPU, có thể ảnh hưởng workload. Một số giai đoạn có thể tạo pause/latency spike ngắn tùy phiên bản, tình huống và contention.

**“Online migration” không có nghĩa không có bất kỳ tác động nào tới request latency.**

## 14. Oversized ranges và jumbo chunks

Một chunk có thể quá lớn hoặc khó chia khi nhiều document có giá trị shard key không đủ phân biệt.

Ví dụ shard key:

~~~javascript
{ tenantId: 1 }
~~~

và **TENANT-LARGE** có hàng triệu document:

~~~text
tenantId = "TENANT-LARGE"
tenantId = "TENANT-LARGE"
tenantId = "TENANT-LARGE"
...
~~~

Nếu toàn bộ có cùng giá trị key, không thể tạo ranh giới shard key nằm giữa những document đó chỉ bằng việc split trên tenantId.

Một số phiên bản/cơ chế dùng thuật ngữ **jumbo** hoặc **oversized chunk/range** cho tình huống gây khó khăn migration.

### 14.1. Vì sao balancer không tự sửa được?

Balancer di chuyển **các range theo shard key**. Nó không tự chia một giá trị khóa không phân biệt thành nhiều giá trị.

Nếu tất cả document nóng nằm trên một giá trị key, việc di chuyển range chỉ đổi shard nhận hotspot, chứ không chia hotspot cho nhiều shard.

### 14.2. Phòng ngừa

- Chọn shard key có cardinality đủ lớn.
- Dùng compound shard key khi đúng pattern truy vấn và write.
- Đánh giá tenant cực lớn trước khi sử dụng tenantId đơn lẻ.
- Tránh trường khóa thiếu/null hàng loạt.
- Theo dõi kích thước range/chunk và migration khó hoàn tất.
- Cân nhắc resharding/refine shard key theo khả năng phiên bản và quy trình đã phê duyệt.

Không xóa trực tiếp metadata của chunk hoặc sửa giá trị key hàng loạt trên production để “chữa jumbo” mà không có kế hoạch migration/data consistency.

## 15. Balancer và shard key hotspot: hai vấn đề khác nhau

Có hai dạng mất cân bằng cần phân biệt.

**Storage imbalance:**

~~~text
Shard A: 800 GB
Shard B: 200 GB
Shard C: 180 GB
~~~

**Write throughput imbalance:**

~~~text
Shard A: 20.000 writes/s
Shard B: 1.000 writes/s
Shard C: 900 writes/s
~~~

Một shard có dung lượng thấp vẫn có thể chứa phần key được ghi liên tục.

### 15.1. Balancer ưu tiên phân bố dữ liệu, không hứa cân bằng QPS

Khi đánh giá hiệu quả scaling, theo dõi cả:

- Data size và số document theo shard.
- Number/ranges/chunks ownership.
- Write/read operations per shard.
- CPU, IOPS, cache pressure.
- Query latency per shard.
- Migrations, replication lag.
- Tỷ lệ targeted và scatter-gather queries.

### 15.2. Trường hợp key tăng đơn điệu

Nếu tất cả insert có shard key tăng liên tục, ghi thường đi vào chunk ở đuôi phạm vi. Balancer có thể chuyển chunk cũ đi nhưng **write mới vẫn hướng tới đuôi key space**.

Giải pháp có thể liên quan chọn key khác, hashed/compound key hoặc thay mô hình dữ liệu, không đơn giản bật balancer là xong.

## 16. Zones: ràng buộc vị trí dữ liệu

MongoDB hỗ trợ **zones** để gắn các khoảng shard key với nhóm shard được chỉ định.

Tình huống:

- Dữ liệu khu vực APAC nên nằm trên nhóm shard trong hạ tầng APAC.
- Dữ liệu nhóm tenant nhạy cảm cần placement theo chính sách.
- Một số data ranges cần dự trữ shard có cấu hình phần cứng khác.

Sơ đồ:

~~~text
Zone APAC -> shard-a, shard-b
Zone EMEA -> shard-c, shard-d

Shard key ranges:
  APAC tenants -> Zone APAC
  EMEA tenants -> Zone EMEA
~~~

### 16.1. Zone không tự thay shard key

Zone ranges được diễn đạt theo **không gian shard key** của collection. Nếu shard key không thể biểu đạt điều kiện placement, zones không tự hiểu một field ứng dụng nằm ngoài shard key để định tuyến chính xác.

### 16.2. Ví dụ cấu hình zones trong lab

Giả sử collection đã shard theo:

~~~javascript
{ region: 1, accountId: 1 }
~~~

Đặt tên zone cho shard:

~~~javascript
sh.addShardToZone("shard-a", "ZONE_APAC");
sh.addShardToZone("shard-b", "ZONE_APAC");
~~~

Tạo range của zone cho giá trị region = "APAC":

~~~javascript
sh.updateZoneKeyRange(
  "sharding_lab.accounts",
  {
    region: "APAC",
    accountId: MinKey()
  },
  {
    region: "APAC",
    accountId: MaxKey()
  },
  "ZONE_APAC"
);
~~~

Ví dụ chỉ minh họa cú pháp và ý tưởng. Tên shard, shard key, ranh giới BSON và version phải khớp môi trường; hãy kiểm tra với MongoDB Manual trước khi thực thi. Nếu shard của zone không đủ capacity hoặc không sẵn sàng, việc đạt placement mong muốn có thể bị chậm/chặn.

### 16.3. Zones tác động balancing thế nào?

Balancer phải xem xét các ràng buộc phân bố theo zone khi đưa range tới shard. Một migration làm trái zone không phải trạng thái cân bằng hợp lệ mà quản trị viên nên ép thực hiện.

### 16.4. Zone chưa phải biện pháp an ninh hoặc tuân thủ đầy đủ

Zone giúp **định hướng placement** theo shard key, nhưng không thay thế:

- IAM/role-based access.
- Encryption.
- Network isolation.
- Quy định backup/replication/cross-region.
- Kiểm soát dữ liệu ở logs và analytics.
- Quy tắc tuân thủ pháp lý cụ thể.

Đừng chỉ dùng tên zone rồi kết luận mọi bản sao và dữ liệu liên quan chắc chắn không ra khỏi một lãnh thổ; cần kiểm tra toàn topology, backup và chính sách.

## 17. Tạo sharded collection trong môi trường lab

Ví dụ sau giả định có một sharded cluster lab đang hoạt động và mongosh kết nối tới **mongos**, không phải một standalone mongod.

### 17.1. Tạo database và dữ liệu

~~~javascript
use sharding_lab

db.orders.insertMany([
  {
    _id: "ORD-1001",
    tenantId: "TENANT-A",
    orderId: "ORD-1001",
    status: "PAID",
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    totalCents: NumberLong(200000)
  },
  {
    _id: "ORD-1002",
    tenantId: "TENANT-A",
    orderId: "ORD-1002",
    status: "PENDING",
    createdAt: ISODate("2026-11-02T09:00:00Z"),
    totalCents: NumberLong(150000)
  },
  {
    _id: "ORD-2001",
    tenantId: "TENANT-B",
    orderId: "ORD-2001",
    status: "PAID",
    createdAt: ISODate("2026-11-03T09:00:00Z"),
    totalCents: NumberLong(300000)
  }
]);
~~~

### 17.2. Tạo index hỗ trợ shard key

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  orderId: 1
});
~~~

### 17.3. Shard collection

~~~javascript
sh.shardCollection(
  "sharding_lab.orders",
  {
    tenantId: 1,
    orderId: 1
  }
);
~~~

Các yêu cầu về index, uniqueness, collection có sẵn, key restrictions và trình tự enabling sharding khác nhau theo phiên bản. Một số phiên bản có thể không còn yêu cầu gọi **sh.enableSharding** cho database trước như tài liệu cũ. Luôn đọc thông tin phản hồi của server trong lab.

### 17.4. Tạo vài document không đủ để nhìn thấy cân bằng

Với ba document nhỏ, nhiều hệ thống chỉ tạo một hoặc rất ít chunk và đặt chúng vào một shard. Không nên kết luận balancer hỏng chỉ vì vài document chưa được phân bố ra tất cả shard.

Phân bố chunk/range phụ thuộc khối lượng dữ liệu, cấu hình sharding và thuật toán/chế độ của phiên bản.

### 17.5. Không làm trên production theo ví dụ

Sharding một collection có dữ liệu thật có yêu cầu riêng về index, điều kiện vận hành, thời gian và tác động workload. Phải có kế hoạch migration/rollback và kiểm tra tính tương thích của ứng dụng.

## 18. Quan sát phân bố và balancer từ mongosh

Trên kết nối mongos:

~~~javascript
sh.status();
~~~

Lệnh này cung cấp tổng quan topology và sharding state theo phiên bản, có thể gồm:

- Danh sách shard.
- Databases/collections được shard.
- Key pattern.
- Số lượng chunk/ranges/zone thông tin phù hợp.
- Dữ liệu liên quan balancer/migration ở mức có sẵn.

### 18.1. Trạng thái balancer

Một số mongosh helper và command theo phiên bản có thể dùng:

~~~javascript
sh.getBalancerState();
~~~

Và:

~~~javascript
db.adminCommand({
  balancerStatus: 1
});
~~~

Các field và helper cụ thể có thể khác theo phiên bản. **Balancer enabled** không đồng nghĩa đang có migration ngay lúc kiểm tra; một cluster cân bằng có thể không cần chuyển chunk.

### 18.2. Phân bố của một collection

Trong những phiên bản hỗ trợ, helper có thể cung cấp thống kê phân bố:

~~~javascript
db.orders.getShardDistribution();
~~~

Kết quả thường giúp nhìn tương quan dữ liệu/chunks trên shard. Không cần giả định API tồn tại ở mọi client/version; nếu helper không hỗ trợ, dùng tài liệu vận hành tương ứng và các metric có sẵn từ cluster.

### 18.3. Explain của query

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
}).explain("executionStats");
~~~

So sánh:

~~~javascript
db.orders.find({
  status: "PAID"
}).explain("executionStats");
~~~

Điểm cần ghi lại là **số shard được target**, plan trên từng shard và tổng chi phí thực thi.

### 18.4. Không sửa trực tiếp config metadata

Có thể có những lệnh cho phép người vận hành đọc trạng thái cluster. Nhưng **không chạy update/insert/delete trực tiếp vào cấu trúc config metadata để chuyển chunk**. Dùng API được MongoDB hỗ trợ và quy trình đã được kiểm soát.

## 19. Bật/tắt balancer trong môi trường thử nghiệm

Trong phiên bản hỗ trợ, mongosh có các helper quản trị:

~~~javascript
sh.stopBalancer();
~~~

và:

~~~javascript
sh.startBalancer();
~~~

**Đây là thao tác thay đổi trạng thái cluster**; không dùng tùy tiện trên production. Nếu tắt balancer trong thời gian dài, phân bố dữ liệu có thể lệch dần khi workload/collection tăng.

### 19.1. Khi nào cân nhắc tạm dừng?

Một số công việc bảo trì hoặc troubleshooting có thể cần tạm dừng migration sau khi được đánh giá và phê duyệt.

Không nên tắt balancer chỉ vì có truy vấn chậm mà chưa chứng minh migration là nguyên nhân. Cần đo CPU, I/O, network, lock/latency, thời điểm migration và trạng thái query plan.

### 19.2. Không ép migration để “chia đều cho đẹp”

Một chunk chuyển đi có thể:

- Làm locality truy vấn kém đi.
- Đi ngược ràng buộc zone.
- Tăng network traffic.
- Gặp vấn đề oversized range.
- Tạo churn khi workload chưa ổn định.

Đừng cố cân bằng số chunk bằng tay nếu chưa xác định mục tiêu vận hành và thuật toán của phiên bản.

### 19.3. Điều cần quan sát sau khi bật lại

- Balancer có thể tiến hành migration theo nhu cầu không.
- Có range bị block do zone/capacity không.
- Có migration errors/retries không.
- Dung lượng và workload có tiến tới mục tiêu không.
- p95/p99 latency có biến động bất thường không.

## 20. Thêm shard mới và quá trình phân bố lại

Giả sử cluster có hai shard:

~~~text
Shard A: 1.2 TB
Shard B: 1.1 TB
~~~

Thêm Shard C có capacity trống không có nghĩa ngay sau lệnh addShard mọi collection lập tức phân bố **0.77 TB / shard**.

Tùy collection, chunk/range, balancer, zone và khối lượng dữ liệu:

1. Shard mới tham gia cluster.
2. Metadata ghi nhận shard mới.
3. Những range có thể chuyển được chọn dần.
4. Migration chuyển dữ liệu và quyền sở hữu.
5. Trạng thái cân bằng tiến triển theo thời gian.

### 20.1. Các điều kiện gây chậm

- Balancer không chạy hoặc đang bị tạm dừng.
- Zone không cho range đặt ở shard mới.
- Chunk quá lớn/khó di chuyển.
- Disk/network throughput thấp.
- Một shard đang quá tải.
- Migration conflict hoặc retry.
- Collection quá nhỏ để cần phân bố nhiều range.

### 20.2. Mở rộng lưu trữ không tự phân tán mọi truy vấn

Thêm shard không giúp query chỉ đọc một tenant nóng nếu toàn bộ truy vấn vẫn target cùng một shard.

Cần kết hợp topology, shard key và query patterns.

## 21. Shard key tốt và xấu qua ví dụ workload

Giả sử hệ thống SaaS có:

~~~text
100.000 tenants
95% tenants nhỏ
5% tenants lớn
Top 10 tenants chiếm 60% writes
Queries:
  - 65% lấy order theo tenantId + orderId
  - 20% lấy order theo tenantId + date range
  - 10% tìm theo customerId
  - 5% báo cáo toàn hệ thống
~~~

Các phương án:

### 21.1. Chọn { tenantId: 1 }

Điểm mạnh: nhiều query dùng tenantId có thể dễ nhắm theo key.

Rủi ro: tenant quá lớn hoặc quá nóng có thể trở thành tập giá trị shard key không thể chia nhỏ theo tenantId đơn lẻ.

### 21.2. Chọn { tenantId: 1, orderId: 1 }

Điểm mạnh: mở rộng độ phân biệt trong từng tenant, targeted query khi có cả tenantId và orderId.

Đánh đổi: query chỉ có tenantId có thể target nhiều chunk/shard nếu tenant trải rộng. Nếu orderId tăng đơn điệu trong tenant, có thể có write hotspot theo phần đuôi của tenant đó.

### 21.3. Chọn { orderId: "hashed" }

Điểm mạnh: khả năng phân tán theo hash của orderId.

Đánh đổi: truy vấn chỉ có tenantId có thể scatter-gather. Phải xét yêu cầu read xuyên orders của cùng tenant và chi phí truy vấn.

### 21.4. Không chọn bằng cảm tính

Để quyết định cần phân tích:

- Cardinality và frequency của các field.
- Query templates thực tế.
- Distribution theo tenant.
- Index và explain.
- Tải theo giờ cao điểm.
- Giới hạn storage/latency.
- Khả năng thay shard key trong tương lai.

Một field xuất hiện trong 80% query chưa chắc là key tốt nếu giá trị phân bố cực lệch.

## 22. Compound shard key và thứ tự field

Shard key:

~~~javascript
{ tenantId: 1, orderDate: 1 }
~~~

khác:

~~~javascript
{ orderDate: 1, tenantId: 1 }
~~~

Với query:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderDate: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
~~~

Cách bố trí tenantId trước có thể giúp nhóm phạm vi theo tenant, nhưng mức targeting cuối cùng phụ thuộc chunk boundaries và phân bố.

Với truy vấn chỉ theo orderDate, việc tenantId đứng trước có thể khiến không thể xác định một khoảng hẹp từ prefix, dẫn tới nhiều shard hơn.

### 22.1. Equality prefix thường có giá trị

Query có equality trên phần đầu shard key thường tạo ra điều kiện định tuyến rõ ràng hơn so với chỉ filter ở field phía sau compound key.

Tuy nhiên, mongos có thể target **nhiều shard** nếu range khớp trải ra nhiều chunks.

### 22.2. Unique index trong sharded collection

Unique constraints trên sharded collections có các giới hạn liên quan shard key. Không nên giả định có thể tạo bất kỳ unique index toàn cluster mà không xét prefix shard key, cơ chế và phiên bản.

Nếu orderId cần unique toàn hệ thống, thiết kế shard key/index/ID generation phải phù hợp với các ràng buộc uniqueness.

### 22.3. Missing/null shard key

Document có field shard key thiếu/null có quy tắc xử lý riêng của MongoDB theo key và operation. Một lượng lớn document cùng missing/null có thể tập trung ở một vùng key space và làm xấu khả năng phân bố.

Do đó cần schema validation và kế hoạch dữ liệu ngay từ đầu, thay vì dựa vào việc sharding tự xử lý mọi lỗi schema.

## 23. Dòng đời metadata trong một migration

Giả sử chunk **[K1, K2)** ban đầu ở Shard A, sau đó chuyển sang Shard B.

~~~text
T0: config metadata => [K1, K2) thuộc Shard A
T1: mongos M1 cache vị trí A
T2: migration bắt đầu (A -> B)
T3: recipient đồng bộ dữ liệu cần thiết
T4: metadata commit ownership sang B
T5: mongos M1 có thể còn cache cũ trong chốc lát
T6: router gặp điều kiện stale, refresh metadata
T7: query cho [K1, K2) target Shard B
T8: cleanup dữ liệu orphaned ở donor theo cơ chế
~~~

Đây là sơ đồ khái niệm; mọi mốc là logical phases chứ không phải những event public có tên chính xác giống nhau ở mọi bản MongoDB.

### 23.1. Tại sao client không được tự route theo bản đồ cũ?

Nếu ứng dụng lưu sẵn quy tắc tenant A thuộc Shard 1, tenant B thuộc Shard 2, rồi kết nối trực tiếp, mapping có thể sai sau migration.

Hãy để **mongos và routing metadata** quyết định shard đích, trừ khi đang dùng một mô hình partitioning tự quản hoàn toàn khác không phải MongoDB native sharding.

### 23.2. Stale metadata không đồng nghĩa data corruption

Một router sử dụng cache cũ có thể cần refresh. Điều đó không tự chứng minh dữ liệu đã mất; phải xem server error, migration state, routing version và kết quả truy vấn qua mongos.

Tuy nhiên lỗi stale kéo dài, liên tục hoặc ảnh hưởng request nghiêm trọng vẫn cần điều tra, không nên coi mọi lỗi đều bình thường.

## 24. Balancer và zone placement khi Region bị mất

Giả sử:

~~~text
Zone APAC: Shard A, Shard B
Zone EMEA: Shard C, Shard D
~~~

Nếu Shard A mất, balancer có thể cần xem những range thuộc Zone APAC còn có thể đặt ở Shard B không. Nhưng chỉ còn một shard hợp lệ có thể không đủ capacity, hoặc không có migration khả thi trong điều kiện hiện tại.

### 24.1. Balancer không phải failover của replica set

Nếu một member mongod trong Shard A replica set mất, replication/election xử lý khả dụng của **Shard A**. Balancer không phải công cụ tự động thay primary trong replica set.

Nếu **cả shard** không còn khả dụng, hành vi của sharded cluster bị ảnh hưởng tùy collection và range nằm trên shard đó. Chuyển chunk giữa shard là vấn đề placement, không thay thế khả năng đọc dữ liệu từ một shard đã mất hoàn toàn.

### 24.2. Zone có thể hạn chế lựa chọn

Dữ liệu bị ràng buộc chỉ ở Zone APAC không được tự chuyển sang Zone EMEA để cân bằng thông thường nếu vi phạm policy.

Trước khi thiết kế zone, cần đảm bảo số shard/capacity phù hợp cho tình huống lỗi mà hệ thống phải chịu.

## 25. Sự cố config servers, mongos và shards

Ba loại thành phần có tác động khác nhau:

| Thành phần gặp lỗi | Hệ quả khái quát |
| --- | --- |
| Một mongos | Client có thể chuyển sang router khác nếu cấu hình và hạ tầng cho phép |
| Config server member | Metadata availability phụ thuộc CSRS quorum và điều kiện; hoạt động cấu hình/metadata có thể bị ảnh hưởng |
| Một member trong shard replica set | Replica set của shard đó xử lý failover nếu đủ quorum |
| Cả một shard mất khả dụng | Dữ liệu/ranges thuộc shard đó có thể không phục vụ bình thường |
| Network giữa mongos và một shard bị lỗi | Operation target shard đó có thể lỗi/timeout |
| Network giữa các shard | Migration/coordination và một số operation phân tán có thể bị ảnh hưởng |

### 25.1. Config server là critical metadata plane

Không có nghĩa chỉ khi đọc/ghi dữ liệu mới cần config servers. Sharding metadata và các thay đổi cấu hình phụ thuộc độ sẵn sàng của CSRS.

Cần triển khai CSRS theo hướng dẫn HA và backup phù hợp; không đặt tất cả config server members trong một failure domain nếu yêu cầu chịu mất vùng lỗi.

### 25.2. Đừng đồng nhất mongos với shard

Mongos là router. Nó không có một bản copy dữ liệu đầy đủ để “cứu” khi shard dữ liệu mất.

Đặt thêm nhiều mongos có thể tăng khả dụng/routing capacity, nhưng không làm tăng bản sao dữ liệu của mỗi shard.

## 26. Sharding và replication ảnh hưởng nhau thế nào?

Một sharded collection có thể trải trên Shard A và Shard B, mỗi shard là replica set riêng.

~~~text
Collection orders:
  Range X -> Shard A replica set
  Range Y -> Shard B replica set

Shard A:
  primary A1
  secondary A2
  secondary A3

Shard B:
  primary B1
  secondary B2
  secondary B3
~~~

Một write vào Range X sẽ được route tới Shard A và áp dụng replication theo cơ chế của Shard A.

### 26.1. Migration không thay thế replication

Chuyển Range X từ Shard A sang B khác với thêm secondary A4 vào Shard A. Migration thay **shard sở hữu** range; replication duy trì bản sao **trong cùng shard replica set**.

### 26.2. Balancing và replica elections có thể đồng thời ảnh hưởng latency

Nếu shard đang election, hoặc recipient/donor đang tải cao, migration có thể gặp lỗi, trì hoãn hoặc retry. Khi chẩn đoán latency spike, nhìn cả:

- Balancer/migrations.
- Replica set primary changes.
- Replication lag.
- Disk I/O và cache pressure.
- Network congestion.
- Query plan và index.

Không nên đổ mọi latency tăng cho balancer khi chưa có dữ liệu quan sát.

## 27. Index trên sharded collection

Shard key cần có index hỗ trợ theo điều kiện của MongoDB. Nhưng các truy vấn nghiệp vụ khác cũng có thể cần index.

Ví dụ collection shard theo:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

API thường lọc:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
}).sort({
  createdAt: -1
});
~~~

Có thể cân nhắc một index hỗ trợ predicate và sort:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Đây là **index phục vụ truy vấn**; không có nghĩa thay shard key hiện tại.

### 27.1. Routing vs index

- Shard key giúp router biết **gửi tới shard nào**.
- Secondary indexes giúp từng shard biết **tìm document thế nào**.

Một truy vấn có thể cần tối ưu cả hai.

### 27.2. Explain per shard

Khi query chạm nhiều shard, executionStats cần được đọc theo từng shard. Có thể một shard xử lý nhanh còn shard khác COLLSCAN lớn do dữ liệu phân bố khác biệt hoặc index/plan khác.

Đừng chỉ nhìn tổng thời gian mà bỏ qua shard chậm nhất.

## 28. Update, delete và upsert trên sharded collection

Các lệnh ghi cũng cần định tuyến.

Ví dụ update có đầy đủ shard key:

~~~javascript
db.orders.updateOne(
  {
    tenantId: "TENANT-A",
    orderId: "ORD-1001"
  },
  {
    $set: {
      status: "SHIPPED"
    }
  }
);
~~~

Mongos có đủ thông tin để xác định range chứa key, với điều kiện cấu hình và query phù hợp.

### 28.1. Ghi thiếu shard key

Ví dụ:

~~~javascript
db.orders.updateOne(
  {
    status: "PENDING",
    customerId: "C-01"
  },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

Khả năng định tuyến, yêu cầu đối với updateOne/upsert và các hành vi hỗ trợ đã thay đổi giữa MongoDB versions. Không nên khẳng định mọi updateOne thiếu shard key đều được phép hoặc đều bị từ chối ở mọi bản MongoDB.

Nguyên tắc thiết kế chung: **đưa shard key phù hợp vào filter khi có thể**, để server có đích rõ ràng và giảm chi phí tìm document.

### 28.2. Upsert có yêu cầu riêng

Khi operation có **upsert: true**, server có thể phải xác định nơi insert document mới. Những quy tắc về shard key, equality predicate và upsert phụ thuộc version và loại operation.

Trước khi dùng production, kiểm tra hướng dẫn của phiên bản MongoDB đang chạy.

### 28.3. Không thay đổi shard key tùy tiện

Shard key có những ràng buộc khi sửa giá trị và thay đổi key design. MongoDB hỗ trợ các cơ chế như refine shard key hoặc reshard collection trong những phiên bản có chức năng tương ứng.

Không coi việc đổi shard key chỉ là drop/create index. Nó có thể ảnh hưởng toàn bộ placement và routing của dữ liệu.

## 29. Resharding và refine shard key

Khi shard key không còn phù hợp, có thể cần một trong các hướng:

- **Refine shard key:** bổ sung trường vào key pattern theo các quy tắc cho phép, nhằm tăng khả năng phân biệt giá trị trong phạm vi.
- **Reshard collection:** tổ chức lại dữ liệu theo shard key khác khi MongoDB phiên bản/topology hỗ trợ.
- **Đổi data model:** ví dụ partition theo tenant/bucket hoặc thay truy vấn để phân bố tốt hơn.

### 29.1. Refine không đồng nghĩa reshard

Refine thường phát triển key bằng cách thêm suffix field theo quy tắc của MongoDB. Reshard có thể thay cách phân bố dữ liệu trên diện rộng.

Cả hai là quyết định kiến trúc cần đánh giá khả năng tương thích, index, workload, disk headroom, migration/resharding capacity và rollback.

### 29.2. Chọn từ đầu vẫn quan trọng

Dù có tính năng resharding, thay key trên một collection lớn vẫn có chi phí và rủi ro vận hành. Không nên chọn một key bất kỳ với kỳ vọng đổi lại không tốn công.

## 30. Quan sát tình trạng phân bố và migration

Một dashboard sharding nên theo dõi:

| Nhóm metric | Điều cần biết |
| --- | --- |
| Dữ liệu | Storage size và document count từng shard |
| Chunk/range | Số lượng và phân bố quyền sở hữu |
| Balancer | Enabled, đang làm gì, migration success/failure |
| Zones | Range có được đặt đúng nhóm shard không |
| Routing | Targeted vs scatter-gather, số shard/query |
| Query execution | CPU, p95/p99, examined keys/documents |
| Replication | Primary changes, replication lag từng shard |
| Capacity | Disk utilization, IOPS, cache, network |
| Metadata plane | Config server health, routing errors |
| App | Server selection errors, timeouts, duplicate retries |

### 30.1. Dấu hiệu lệch dữ liệu

- Một shard có dung lượng cao hơn đáng kể.
- Số chunk/range hoặc dung lượng vẫn lệch sau nhiều chu kỳ balancing.
- Có migration bị lỗi lặp lại.
- Zone không có đủ shard hợp lệ.
- Những chunk lớn không thể tách/di chuyển.
- Thêm shard mới nhưng range không chuyển sang.

### 30.2. Dấu hiệu lệch workload

- Một shard có CPU/IOPS vượt hẳn shard còn lại.
- Write latency của một tenant rất lớn.
- Hầu hết query chạm tất cả shards.
- Tăng shard nhưng p95 API không cải thiện.
- Một prefix/key value sinh phần lớn write.

Điều tra shard key, access pattern và index trước khi chỉ điều chỉnh balancer.

## 31. Kiểm thử balancer có kiểm soát

Một bài test minh họa trên lab:

**Mục tiêu:** sau khi thêm shard hoặc thay phân bố, xác nhận MongoDB có thể di chuyển ranges theo nhu cầu và routing vẫn đúng.

### 31.1. Preflight

1. Xác định replica set của từng shard khỏe.
2. CSRS và mongos hoạt động bình thường.
3. Thu thập sh.status và phân bố collection.
4. Ghi balancer state.
5. Ghi zones, chunk/range đặc biệt và disk headroom.
6. Chạy workload đọc/ghi có request ID.
7. Xác định ngưỡng dừng nếu latency tăng hoặc lỗi xuất hiện.

### 31.2. Trong test

Quan sát:

- Balancer có chọn migrations khi thật sự có imbalance không?
- Donor và recipient có đủ tài nguyên không?
- Routing của query có tiếp tục đúng không?
- Có stale metadata refresh errors bất thường không?
- Query latency có spike không?
- Dữ liệu ứng dụng có còn nhất quán không?

### 31.3. Sau test

- Xác nhận phân bố tiến tới mục tiêu.
- Không còn migration errors kéo dài.
- Truy vấn targeted và scatter-gather trả kết quả đúng.
- Chỉ số p95/p99 trở lại ngưỡng.
- Kiểm tra zone placement.
- Không có duplicate nghiệp vụ do retry.
- Đóng test với báo cáo đo thực tế, không chỉ chụp một sh.status.

### 31.4. Không tự ép migration production

Các helper thủ công để move chunk/range có chi tiết thay đổi theo release. Những lệnh này có thể gây ảnh hưởng tới storage và routing. Bài học cố ý không yêu cầu học viên tự ép move chunk trên production; hãy dùng topology lab và các lệnh được tài liệu phiên bản hỗ trợ.

## 32. Java Sync Driver: targeted query qua mongos

Ứng dụng Java nên kết nối qua connection string của sharded cluster (thường chỉ tới mongos hoặc seed phù hợp do nền tảng cung cấp).

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ShardedOrdersQuery {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu MONGODB_URI của sharded cluster"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {

            MongoDatabase database =
                    client.getDatabase("sharding_lab");

            MongoCollection<Document> orders =
                    database.getCollection("orders");

            Bson filter = Filters.and(
                    Filters.eq("tenantId", "TENANT-A"),
                    Filters.eq("orderId", "ORD-1001")
            );

            FindIterable<Document> result =
                    orders.find(filter);

            for (Document order : result) {
                System.out.println(order.toJson());
            }
        }
    }
}
~~~

Với shard key **{ tenantId: 1, orderId: 1 }**, filter cung cấp đủ key để mongos định tuyến tới phạm vi tương ứng.

### 32.1. Ví dụ query có thể scatter-gather

~~~java
Bson filter = Filters.eq("status", "PAID");

orders.find(filter).forEach(
        order -> System.out.println(order.toJson())
);
~~~

Query trên không mang shard key theo ví dụ. Mongos có thể cần gửi tới nhiều shard. Driver không tự biết thêm tenantId nếu ứng dụng không cung cấp.

### 32.2. Không tự lưu danh sách tenant-to-shard ở client

Ứng dụng nên gửi query hợp lệ qua mongos. Nếu tự giữ mapping tenant -> shard trong Java, mapping đó có thể bị lỗi thời khi chunk migration hoặc resharding diễn ra.

### 32.3. Lỗi trong migration

Đối với các lỗi tạm thời như network hiccup, topology change và write concern timeout, ứng dụng cần retry đúng loại operation, dùng requestId/idempotency khi cần.

Không tự retry vô hạn các lệnh có side effect; một write có thể đã được áp dụng dù client chưa nhận response.

## 33. Java Sync Driver: aggregate và explain để hiểu định tuyến

Một aggregation tổng hợp có thể đụng nhiều shard:

~~~java
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Accumulators;
import org.bson.Document;

import java.util.Arrays;

orders.aggregate(Arrays.asList(
        Aggregates.group(
                "$status",
                Accumulators.sum("count", 1)
        )
)).forEach(
        row -> System.out.println(row.toJson())
);
~~~

Để phân tích routing từ mongosh, thường dễ bắt đầu bằng:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
], {
  explain: true
});
~~~

Hoặc dùng explain của find như mục 10. Những cách gọi explain bằng Java Driver và output shapes cần tham khảo tài liệu phiên bản driver/server. Điểm cần tập trung không phải có bao nhiêu dòng output, mà là **shard participation và chi phí execution**.

## 34. Case study: tenant SaaS tăng trưởng không đồng đều

Giả sử ban đầu:

~~~text
Shard A: 400 GB, 1.500 writes/s
Shard B: 380 GB, 1.400 writes/s
Shard C: 390 GB, 1.450 writes/s
~~~

Sau một năm:

~~~text
Shard A: 700 GB, 20.000 writes/s
Shard B: 450 GB, 1.800 writes/s
Shard C: 460 GB, 1.900 writes/s
~~~

Một tenant lớn tăng trưởng nhanh và chiếm phần lớn write.

### 34.1. Những giả thuyết

1. Tenant có shard key một giá trị duy nhất và tạo hotspot.
2. Write tập trung vào đuôi một key ranged tăng dần.
3. Chunk của tenant quá lớn hoặc không thể split.
4. Balancer bị tắt hoặc bị zone hạn chế.
5. Migration lỗi do capacity/replication/network.
6. Số byte không lệch nhiều nhưng workload query tập trung ở một shard.

### 34.2. Cách điều tra

- Xác nhận shard key pattern và phân bố khóa.
- Xem sh.status, migration/balancer metrics.
- Xem query filters có target đúng shard không.
- Đo QPS/latency per shard.
- Xem chunk/range sizes, hotspot key values.
- Kiểm tra zone rules.
- Xem explain của top queries.
- Đánh giá lại key, bucket hoặc resharding nếu cần.

### 34.3. Vì sao thêm shard không chắc giải quyết?

Nếu 20.000 writes/s cùng nhắm một giá trị shard key, chuyển chunk chứa giá trị đó sang shard D chỉ biến D thành shard nóng.

Vấn đề gốc là khả năng **chia workload theo key**, không chỉ số shard.

## 35. Case study: phân bố theo địa lý và zones

Một hệ thống có tenants APAC và EMEA, muốn ưu tiên lưu document của từng nhóm trên shard hạ tầng tương ứng.

### 35.1. Thiết kế shard key

Ví dụ:

~~~javascript
{ region: 1, tenantId: 1, documentId: 1 }
~~~

Khi có region làm prefix, các khoảng theo region có thể biểu đạt bằng zones. Tuy nhiên, nếu nhiều query chỉ có tenantId mà không có region, việc định tuyến có thể kém hơn.

Ứng dụng cần đảm bảo region có sẵn trong những operation latency-sensitive hoặc có cơ chế xác định region đúng.

### 35.2. Placement policy

~~~text
ZONE_APAC:
  shard-apac-1
  shard-apac-2

ZONE_EMEA:
  shard-emea-1
  shard-emea-2
~~~

### 35.3. Những điểm cần xác minh

- Query thực sự có region/tenantId.
- Dữ liệu được phân bố đúng zone.
- Khi một shard trong zone mất, còn capacity đủ.
- Replication members của từng shard cũng tuân thủ ràng buộc liên quan.
- Backup và log không vô tình vi phạm residency.
- Cơ chế chuyển region của tenant được thiết kế rõ.

Zone placement không tự hoàn thành mọi yêu cầu tuân thủ dữ liệu.

## 36. Một số hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Thêm shard thì mọi query nhanh hơn | Query routing và workload mới quyết định |
| Sharding là replication | Sharding chia dữ liệu; replication sao chép trong shard |
| Mongos lưu đầy đủ collection | Mongos là router, không phải shard chứa dữ liệu |
| Config server xử lý mọi CRUD request | Mongos cache metadata và route tới shard |
| Chunk là một file trên disk | Chunk là khoảng shard key logic |
| Một shard chỉ có một chunk | Một shard có thể sở hữu nhiều ranges |
| Mọi chunk có cùng số document | Document size/phân bố khác nhau |
| Chunk target size là giới hạn cứng | Range có thể lớn hơn mục tiêu |
| Split làm dữ liệu sang shard khác | Split chia range, thường chưa đổi owner |
| Balancer chỉ làm chunk count bằng nhau | Tiêu chí thay đổi theo phiên bản, còn size/zones |
| Balancer sửa được shard key kém | Một key value quá nóng vẫn có thể dồn một shard |
| Có shard key trong query là chắc một shard | Predicate có thể chạm nhiều chunks/shards |
| Có index nghĩa là query targeted | Index là local execution; routing cần shard key metadata |
| Hashed key giúp range query theo giá trị gốc | Hash phá locality của range trên giá trị gốc |
| Hashed key tự chia một tenant nóng | Một giá trị hash đơn lẻ vẫn thuộc một vị trí |
| Migration hoàn tất mà router phải restart | Routing metadata có cơ chế refresh |
| Dữ liệu orphaned có nghĩa ứng dụng thấy trùng | Ownership/routing có semantics riêng |
| Zones tự thay shard key | Zone ranges được định nghĩa trên shard key |
| Zones là cơ chế ACL hoàn chỉnh | Cần security và compliance độc lập |
| Config metadata có thể tự update như dữ liệu nghiệp vụ | Không trực tiếp sửa metadata nội bộ |
| Thêm shard là có phân bố ngay lập tức | Balancing/migrations phụ thuộc dữ liệu và policy |
| Balancer là cơ chế failover primary | Election thuộc replica set của mỗi shard |
| w:majority nghĩa là tất cả shard đã lưu mọi write | Write concern áp dụng theo semantics operation/cluster, không đồng nghĩa mọi shard |
| Update thiếu shard key luôn hợp lệ ở mọi version | Quy tắc phụ thuộc operation và server version |
| Reshard chỉ là đổi index | Có thể cần chuyển dữ liệu/metadata ở quy mô lớn |

## 37. Bài thực hành: shard key và targeting

### Bài 1 – Xác định shard key range

Collection sharded theo:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Cho các giá trị:

~~~text
TENANT-A / ORD-1001
TENANT-A / ORD-9999
TENANT-B / ORD-1001
TENANT-C / ORD-0001
~~~

Hãy sắp xếp theo shard key và vẽ ba khoảng liên tiếp bao phủ key space. Giải thích vì sao ranh giới là tuple chứ không phải chỉ orderId.

### Bài 2 – Targeted hay scatter-gather?

Với key trên, phân tích:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
});
~~~

~~~javascript
db.orders.find({
  tenantId: "TENANT-A"
});
~~~

~~~javascript
db.orders.find({
  orderId: "ORD-1001"
});
~~~

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Cho biết query nào cung cấp đầy đủ shard key; query nào có thể chạm nhiều chunks/shards, và tại sao kết luận chính xác cần metadata thực tế.

### Bài 3 – Explain targeted vs scatter

Trong lab:

~~~javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
}).explain("executionStats");
~~~

So sánh với query lọc status. Ghi số shard tham gia và stage/index trên từng shard. Không chỉ so executionTimeMillis.

### Bài 4 – Hashed shard key

Một collection sharded theo customerId hashed. Hãy giải thích vì sao query equality theo customerId có thể targeted nhưng query range trên customerId gốc có thể phải gửi tới nhiều shard.

### Bài 5 – Key tăng đơn điệu

Collection events shard theo createdAt ranged, mỗi event có createdAt tăng liên tục. Dự đoán hotspot khi insert và đề xuất hai cách thay mô hình shard key, kèm đánh đổi về range query.

## 38. Bài thực hành: chunks và balancer

### Bài 6 – Split và migration

Ban đầu:

~~~text
Shard A owns [0, 1000)
Shard B owns [1000, 2000)
~~~

Thực hiện logical split [0, 1000) thành [0, 500) và [500, 1000). Hỏi sau split shard nào sở hữu hai ranges?

Sau đó mô phỏng migrate [500, 1000) sang Shard B. Vẽ bảng owner mới.

### Bài 7 – Metadata stale

Mongos M1 cache [500, 1000) ở Shard A. Balancer migrate range sang Shard B. Hãy mô tả vai trò của version/refresh và tại sao ứng dụng không nên tự route trực tiếp theo bản cache của mình.

### Bài 8 – Thêm shard

Cluster có Shard A 700 GB, B 680 GB, thêm C trống. Những điều kiện nào quyết định dữ liệu có thể chuyển sang C? Vì sao không kỳ vọng kích thước lập tức chia đều sau lệnh addShard?

### Bài 9 – Oversized range

Một tenant chiếm 40% dữ liệu và shard key chỉ có tenantId. Hãy giải thích vì sao balancer khó tách hotspot của tenant đó và đề xuất compound key hoặc model khác phù hợp.

### Bài 10 – Balancer state

Trên lab đã được phép:

~~~javascript
sh.status();
sh.getBalancerState();
db.adminCommand({ balancerStatus: 1 });
~~~

Ghi lại: có bao nhiêu shard, collection shard nào, balancer enabled không, có lý do migration bị chặn không. Phân biệt **enabled** và **đang migration**.

## 39. Bài thực hành: zones, vận hành và troubleshooting

### Bài 11 – Zone placement

Collection có shard key:

~~~javascript
{ region: 1, tenantId: 1 }
~~~

Thiết kế zone cho APAC và EMEA. Liệt kê những thông tin phải kiểm tra trước khi dùng sh.addShardToZone và sh.updateZoneKeyRange. Giải thích vì sao query chỉ có tenantId có thể khó target chính xác.

### Bài 12 – Storage imbalance và write imbalance

Cho số liệu:

~~~text
Shard A: 500 GB, 18.000 writes/s
Shard B: 500 GB, 2.000 writes/s
Shard C: 500 GB, 2.100 writes/s
~~~

Dữ liệu đã đều về byte. Balancer có nhất thiết làm tăng throughput không? Hãy phân tích hot key, query targeting và shard key.

### Bài 13 – Zone vs Region failure

Một zone chỉ có một shard hợp lệ. Nếu shard đó mất, balancer có thể tự đưa range sang mọi shard ở zone khác không? Giải thích xung đột giữa placement restriction và availability.

### Bài 14 – Query có index nhưng chậm

Một query lọc status có index trên từng shard, nhưng chạm 12 shards và trả rất nhiều document. Hãy phân tích chi phí fan-out, merge, network và đề xuất phương án theo query patterns.

### Bài 15 – Chẩn đoán migration

Sau khi thêm shard, balancer không chuyển ranges. Lập checklist: balancer state, zone rules, size/capacity, oversized chunks, errors, nguồn/đích, tài nguyên và version features.

### Bài 16 – Truy vấn Java

Từ ví dụ Java Sync Driver, viết hai hàm:

- findOrder(tenantId, orderId) dùng đầy đủ compound shard key.
- findPaidOrders() chỉ lọc status.

Giải thích vì sao hai hàm có khả năng routing khác nhau dù cùng sử dụng một MongoClient và cùng collection.

### Bài 17 – Đánh giá shard key trước production

Giả sử có 50.000 tenants và 10 tenants lớn sinh 70% write. So sánh các key:

~~~javascript
{ tenantId: 1 }
{ tenantId: 1, orderId: 1 }
{ orderId: "hashed" }
~~~

Với mỗi key, đánh giá cardinality, hotspots, query targeting theo tenant và chi phí cross-tenant reporting. Không có một key tối ưu tuyệt đối nếu chưa biết workload.

### Bài 18 – Resharding decision

Một cluster đang dùng createdAt ranged và write hotspot ở chunk cuối. Lập kế hoạch đánh giá xem có cần resharding không: số liệu cần thu, key ứng viên, impact truy vấn, dung lượng tạm, version, window, rollback và tiêu chí pass/fail.

## 40. Checklist thiết kế sharding

Trước khi đưa collection lên sharded cluster:

1. **Workload:** có số liệu read/write và top query patterns thực.
2. **Shard key:** cardinality đủ, frequency không lệch quá mức.
3. **Hotspot:** đã đánh giá monotonic/hashed/tenant lớn.
4. **Targeting:** query latency-sensitive có đủ key predicates không.
5. **Index:** các shard có index phù hợp cho local execution.
6. **Chunks:** hiểu ranges, target size và oversized cases.
7. **Metadata:** config server RS khỏe và có cơ chế backup/monitoring.
8. **mongos:** ứng dụng kết nối router đúng, có khả năng failover.
9. **Balancer:** biết trạng thái, migration policy và metric.
10. **Zones:** placement phản ánh shard key và có capacity dự phòng.
11. **Capacity:** shard mới có disk/network/IOPS đủ cho migration.
12. **Reliability:** mỗi shard là replica set có quorum/fault domains phù hợp.
13. **Operations:** admin commands có change process và không sửa config metadata trực tiếp.
14. **Observability:** đo scatter-gather, imbalance, migration và replication.
15. **Future evolution:** có kế hoạch refine/reshard khi workload đổi.
16. **Data correctness:** update/upsert/unique constraints đúng phiên bản.
17. **Retries:** xử lý lỗi mơ hồ và idempotency.
18. **Backup:** replica set và sharding không thay thế backup/restore.

## 41. Kết luận

MongoDB Sharding phân bố dữ liệu dựa trên **shard key** và những **chunk/ranges** trong không gian khóa. **Config servers** giữ metadata cấu hình, **mongos** dùng metadata định tuyến (thường đã cache) để gửi request tới shard phù hợp, còn **balancer** có thể điều phối việc chuyển những khoảng dữ liệu giữa các shard theo chính sách và thuật toán của phiên bản.

Một truy vấn có đầy đủ shard key có cơ hội target ít shard hơn. Query thiếu shard key có thể trở thành scatter-gather dù các shard vẫn có index. Một chunk là khoảng logic **[min, max)**, không phải file trên disk; split chỉ thay ranh giới còn migration mới thay shard owner. Balancer có thể hỗ trợ cân bằng dung lượng, nhưng **không tự chữa workload hotspot do shard key kém**.

Để sharding phát huy hiệu quả, cần thiết kế đúng từ cả ba tầng:

- **Data model:** shard key, cardinality, ranges, zones.
- **Execution:** mongos routing, query patterns, indexes, explain.
- **Operations:** balancer/migration, metadata health, replication, capacity, observability và an toàn retry.

Khả năng mở rộng không chỉ đến từ số shard, mà từ **việc dữ liệu và thao tác thực sự có thể được chia nhỏ, định tuyến và vận hành an toàn**.

## Tài liệu tham khảo

- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/)
- [MongoDB Manual — Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/)
- [MongoDB Manual — Range Based Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/)
- [MongoDB Manual — Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [MongoDB Manual — Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/)
- [MongoDB Manual — Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/)
- [MongoDB Manual — Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/)
- [MongoDB Manual — Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/)
- [MongoDB Manual — sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
