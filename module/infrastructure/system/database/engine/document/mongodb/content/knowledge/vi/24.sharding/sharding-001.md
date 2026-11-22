# Phân biệt sharding, replication và phân vùng nghiệp vụ trong MongoDB

## 1. Vì sao cần phân biệt ba khái niệm?

Một ứng dụng lưu đơn hàng cho hàng nghìn cửa hàng có thể bắt đầu với một MongoDB server. Khi dữ liệu và lưu lượng tăng, đội kỹ thuật thường nghe ba đề xuất:

1. **“Thêm replica set để hệ thống không ngừng khi một máy hỏng.”**
2. **“Sharding collection đơn hàng để phân phối dữ liệu và tải ghi sang nhiều máy.”**
3. **“Chia dữ liệu theo tenant hoặc theo năm để dễ quản lý nghiệp vụ.”**

Cả ba đều liên quan đến cách tổ chức dữ liệu, nhưng **giải quyết những bài toán khác nhau**. Nếu nhầm chúng với nhau, hệ thống có thể chịu thêm chi phí hạ tầng mà vẫn không mở rộng được write throughput, hoặc có thêm nhiều bản sao nhưng không thực sự phân phối dữ liệu.

Bài này thuộc chương **Sharding** của MongoDB, giúp bạn phân biệt:

- **Replication:** tạo và đồng bộ nhiều bản sao của **cùng một tập dữ liệu** để tăng availability và khả năng phục hồi.
- **Sharding:** chia **một tập dữ liệu logic** thành nhiều phần vật lý được lưu trên các **shard khác nhau** để mở rộng dung lượng và phân phối tải.
- **Phân vùng nghiệp vụ (business partitioning):** chia dữ liệu theo một quy tắc **do miền nghiệp vụ và ứng dụng định nghĩa**, như `tenantId`, khu vực, năm tài chính hay nhóm khách hàng; việc chia này **có thể hoặc không** tạo ra phân chia vật lý trên nhiều máy.

Sau bài học, bạn có thể giải thích cách MongoDB kết hợp sharding với replica set, phân biệt khóa shard với khóa phân vùng nghiệp vụ, chọn chiến lược khi hệ thống có nhiều tenant và tránh các sai lầm về khả năng chịu lỗi, consistency, query routing và chi phí vận hành.

> **Nguyên tắc đầu tiên:** **Replication nhân bản**, **sharding phân phối**, còn **phân vùng nghiệp vụ định nghĩa ranh giới dữ liệu theo domain**. Một hệ thống hoàn toàn có thể sử dụng **cả ba cùng lúc**.

## 2. Bảng so sánh nhanh

| Tiêu chí | Replication | Sharding | Phân vùng nghiệp vụ |
| --- | --- | --- | --- |
| Câu hỏi chính | “Nếu node hỏng, có bản sao để tiếp tục không?” | “Làm sao một collection lớn dùng tài nguyên nhiều shard?” | “Dữ liệu thuộc tenant, năm, khu vực hoặc đơn vị kinh doanh nào?” |
| Cơ chế | Replica set và oplog replication | Shard key, chunks/ranges, `mongos`, balancer | Quy tắc domain; filter, collection/database/cluster riêng, routing tại ứng dụng |
| Phân phối dữ liệu | Các data-bearing member giữ **cùng dataset của replica set** | Mỗi shard giữ **một phần** của sharded collection | Tùy thiết kế: có thể cùng collection hoặc lưu tách |
| Duplicates vật lý | Có các bản sao của cùng dữ liệu | Không phải mặc định mỗi shard giữ toàn bộ collection | Có thể không có bản sao; tùy backup/replica |
| Khả năng chịu lỗi | Mục tiêu cốt lõi | Cần replica set trên từng shard để chịu lỗi member | Không tự cung cấp HA |
| Mở rộng tổng dung lượng dữ liệu logic | Không phải mục tiêu chính | Có, thêm shard để phân phối dữ liệu | Chỉ khi phân vùng thực sự đặt trên hạ tầng có thêm capacity |
| Mở rộng write throughput | Không làm nhiều primary cùng ghi vào một dataset | Có thể, nếu shard key phân phối write | Có thể khi các phân vùng ghi lên hạ tầng độc lập |
| Mở rộng read | Có thể đọc secondary với đánh đổi consistency | Có thể phân phối query theo shard | Tùy cách route và hạ tầng |
| Routing | Driver khám phá primary/secondary | `mongos` quyết định shard dựa trên metadata | Ứng dụng/middleware quyết định tenant hoặc partition nào |
| Bẫy thường gặp | Tưởng nhiều bản sao nghĩa là dung lượng logic tăng tương ứng | Chọn shard key gây hotspot/scatter-gather | Có tenantId nhưng tưởng dữ liệu đã tách vật lý |

Những cột này không nói cơ chế nào “tốt hơn”. Chúng là các trục thiết kế **bổ trợ nhưng không thay thế nhau**.

## 3. Nhìn bằng sơ đồ: ba cách tổ chức một triệu đơn hàng

Giả sử collection `orders` có **1.000.000 document**.

### 3.1. Replication: ba node giữ cùng dataset

~~~text
                   Replica set rsOrders
                     (1 triệu orders)
                            |
            +---------------+---------------+
            |               |               |
       +----------+    +----------+    +----------+
       | PRIMARY  |    | SECONDARY|    | SECONDARY|
       |  1 triệu |    |  1 triệu |    |  1 triệu |
       +----------+    +----------+    +----------+
            |               ^               ^
            +---------------+---------------+
                 Oplog replication
~~~

Theo cấu hình điển hình, **mỗi data-bearing member** có bản sao toàn bộ dataset của replica set. Có ba bản sao vật lý để phục hồi khi một thành viên hỏng; **không phải ba triệu đơn hàng khác nhau**.

Nếu mọi write vẫn đi tới **một primary**, thêm secondary **không tự biến write capacity thành ba lần**. Secondary có thể được dùng để xử lý read nếu read preference cho phép, nhưng có thể trả dữ liệu chậm do replication.

### 3.2. Sharding: chia dataset thành nhiều phần

~~~text
                     Sharded collection
                    1.000.000 orders
                            |
                          mongos
                 +----------+----------+
                 |          |          |
                 v          v          v
             +--------+ +--------+ +--------+
             |Shard A | |Shard B | |Shard C |
             |~330k   | |~340k   | |~330k   |
             +--------+ +--------+ +--------+
                       Phân phối dữ liệu
~~~

Các số ở sơ đồ chỉ là **minh họa** về một phân phối tương đối đều, không phải tỷ lệ MongoDB cam kết tự động đạt được.

Mỗi shard lưu **một phần** document của sharded collection. `mongos` nhận query từ ứng dụng và quyết định gửi query đến shard nào theo shard key và metadata routing.

### 3.3. Phân vùng nghiệp vụ: chia theo tenant

~~~text
                 1.000.000 orders
                         |
                  tenantId trong mỗi
                  document/đường ghi
                         |
              +----------+----------+
              |          |          |
          Tenant A    Tenant B    Tenant C
          600.000     300.000     100.000
              |          |          |
              +----------+----------+
                Cùng orders collection
                cũng hoàn toàn có thể!
~~~

Nếu mọi document vẫn nằm trong **một collection trên một replica set**, việc có `tenantId` **chưa phải sharding vật lý**. Nó là **phân vùng logic theo miền nghiệp vụ**.

Ngược lại, bạn có thể đặt mỗi tenant trong một database riêng, hoặc ánh xạ tenant sang một cluster riêng. Khi đó phân vùng nghiệp vụ có thể dẫn đến **cách ly vật lý**, nhưng cơ chế routing và migration sẽ do kiến trúc ứng dụng quyết định.

## 4. Replication trong MongoDB

### 4.1. Một replica set có gì?

Một replica set thường có:

- **Primary:** nhận các thao tác ghi bình thường.
- **Secondary:** sao chép oplog từ primary và áp dụng các thay đổi vào bản sao của mình.
- **Election:** khi primary không khả dụng, các member đủ điều kiện bầu chọn primary mới.
- **Oplog:** nhật ký thao tác phục vụ đồng bộ.
- **Read preference:** cho phép chọn primary hoặc secondary để đọc theo chính sách.

Sơ đồ sự cố:

~~~text
Bình thường                 Sau khi A mất
-----------                 -------------
A = primary                 A = unavailable
B = secondary               B = primary mới (nếu được bầu)
C = secondary               C = secondary
~~~

Trong giai đoạn bầu chọn, một số read/write có thể tạm lỗi; ứng dụng phải xử lý reconnect/retry theo semantics của driver và các thao tác.

### 4.2. Replication giải quyết bài toán nào?

**Availability:** Khi một member hỏng nhưng vẫn còn đa số voting members và một secondary đủ điều kiện, replica set có thể bầu primary mới.

**Data redundancy:** Có nhiều bản sao của dataset trên các data-bearing member. Một ổ đĩa hỏng không nhất thiết làm mất dữ liệu của toàn bộ replica set.

**Một số nhu cầu đọc:** Có thể cấu hình read preference để gửi truy vấn không quá nhạy cảm với freshness sang secondary.

**Maintenance:** Replica set hỗ trợ nhiều thao tác bảo trì/upgrade có kế hoạch hơn so với một instance đơn lẻ, dù vẫn phải xét downtime, election và write concern.

### 4.3. Replication không giải quyết những gì?

Replication **không tự**:

- Chia một collection 5 TB thành mỗi máy 1–2 TB.
- Tạo ba primary cùng chấp nhận write độc lập đối với cùng dataset.
- Chống lại thao tác xóa nhầm hoặc lỗi ứng dụng: xóa hợp lệ trên primary có thể được replicate.
- Thay thế backup, khôi phục theo thời điểm hoặc kế hoạch disaster recovery.
- Đảm bảo secondary luôn có write mới nhất.
- Đảm bảo write đã được acknowledged ở một mức thấp không bao giờ rollback khi failover.

**Arbiter** chỉ tham gia voting/election, không giữ bản sao dữ liệu; ba member gồm hai data-bearing member và một arbiter **không đồng nghĩa ba bản sao dữ liệu**.

### 4.4. Ví dụ read preference

~~~javascript
// Ví dụ trên mongosh kết nối replica set.
db.getMongo().setReadPref("primary");
db.orders.find({ status: "PAID" }).limit(10).toArray();

db.getMongo().setReadPref("secondaryPreferred");
db.orders.find({ status: "PAID" }).limit(10).toArray();

// Khôi phục mặc định.
db.getMongo().setReadPref("primary");
~~~

`secondaryPreferred` ưu tiên đọc secondary nhưng có thể fallback primary. Vì replication bất đồng bộ, kết quả secondary có thể không chứa các write mới xảy ra.

**Đừng dùng secondary read làm bước quyết định một write nhạy cảm** như “nếu stock còn > 0 thì trừ stock” mà không có điều kiện nguyên tử ở thao tác cập nhật.

## 5. Sharding trong MongoDB

### 5.1. Sharding phân phối dữ liệu ở cấp collection

Sharding cho phép một sharded collection phân bố các document lên nhiều **shard**. Một shard chỉ giữ **một phần** dữ liệu của collection đó; tổng các shard tạo thành dữ liệu logic của collection.

MongoDB sharding hoạt động dựa trên **shard key**. Những vùng giá trị shard key được chia thành **chunks** (hoặc ranges) và gán cho các shard. Balancer có thể di chuyển ranges giữa các shard theo chính sách phân phối và zone.

Ví dụ collection đơn hàng:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "tenant-a",
  orderId: "ORD-1001",
  createdAt: ISODate("2026-11-01T08:00:00Z"),
  total: NumberDecimal("250.00")
}
~~~

Có thể lựa chọn shard key `{ tenantId: 1, orderId: 1 }` hoặc shard key khác, tùy phân bố khóa và mẫu query. Không có một shard key tốt nhất cho mọi hệ thống.

### 5.2. Ba thành phần của sharded cluster

Một MongoDB sharded cluster có các thành phần:

1. **Shard:** nơi giữ một phần dữ liệu sharded. Trong các phiên bản hiện hành, shard phải được triển khai dưới dạng **replica set**.
2. **`mongos`:** query router nhận lệnh từ ứng dụng và định tuyến tới shard phù hợp, gom/trả kết quả khi cần.
3. **Config servers:** giữ metadata về collections, shards, chunk ranges và routing. Config servers được triển khai dưới dạng replica set (**CSRS**). Từ MongoDB 8.0, có thể dùng **config shard** để kết hợp vai trò config server với khả năng lưu application data trong cấu hình hỗ trợ.

Sơ đồ kết hợp thực tế:

~~~text
                       Application
                            |
                            v
                       mongos router
                       /           \
         +------------+             +------------+
         |                                       |
         v                                       v
     Shard A                                 Shard B
   replica set                             replica set
 +----------------+                      +----------------+
 | primary A1     |                      | primary B1     |
 | secondary A2   |                      | secondary B2   |
 | secondary A3   |                      | secondary B3   |
 +----------------+                      +----------------+
   | subset A |                             | subset B |
         ^                                       ^
         |                                       |
         +--------------+------------------------+
                        |
                Config metadata
                 config servers
                   (CSRS)
~~~

**Đây là ví dụ quan trọng nhất:** Sharding và replication **cùng xuất hiện**. Replication đảm bảo có nhiều bản sao **của mỗi shard**, còn sharding phân phối **các phần dữ liệu khác nhau giữa các shard**.

### 5.3. Primary shard không phải primary member

Trong MongoDB, cụm từ **primary** có thể chỉ hai khái niệm khác nhau:

- **Primary của replica set:** node nhận write cho replica set đó.
- **Primary shard của database:** shard được chỉ định làm nơi lưu các **unsharded collections** của database theo quy tắc mặc định (và metadata của database).

Ví dụ **Shard A** có thể là primary shard của database `shop`, trong khi trong replica set của Shard A, **member A2** đang là primary. Hai chữ “primary” này không chỉ cùng một đối tượng.

Unsharded collection **không tự được trải đều** trên tất cả shard chỉ vì database đã nằm trong sharded cluster. Các phiên bản mới có các lệnh hỗ trợ di chuyển collection không sharded (ví dụ `moveCollection` từ MongoDB 8.0), nhưng đó là một quyết định quản trị khác với việc sharding collection.

### 5.4. Client không nên kết nối trực tiếp shard để làm nghiệp vụ cluster-wide

Để chạy query trên dữ liệu được phân phối, ứng dụng thường kết nối **`mongos`** hoặc endpoint router của dịch vụ managed.

Nếu bạn kết nối trực tiếp đến một shard và query một sharded collection, bạn có nguy cơ chỉ quan sát **phần dữ liệu do shard đó giữ**, không phải toàn bộ collection trong cluster. Truy vấn/ghi cluster-wide cần đi qua router đúng cơ chế.

## 6. Shard key là ranh giới phân phối vật lý

MongoDB dựa vào **shard key** để chia và định tuyến dữ liệu. Chọn shard key ảnh hưởng lâu dài tới:

- Dữ liệu có được phân bố đồng đều không.
- Một query chạm **một shard**, **một vài shard** hay **tất cả shard**.
- Write có bị dồn vào một shard không.
- Khả năng phân phối một tenant lớn trên nhiều shard.
- Khả năng tạo unique index trên sharded collection.
- Dễ hay khó áp dụng zone sharding.
- Chi phí di chuyển chunks/ranges khi dữ liệu tăng.

### 6.1. Ranged sharding

Với ranged sharding, những giá trị shard key gần nhau thường thuộc các khoảng liền nhau:

~~~text
Shard key: orderNo

[0000, 3000) ----> Shard A
[3000, 7000) ----> Shard B
[7000, +inf) ----> Shard C
~~~

Các khoảng trên chỉ là mô hình minh họa, không phải layout MongoDB cam kết.

Lợi ích:

- Query theo **một khoảng shard key** có thể định tuyến đến tập shard phù hợp thay vì tất cả.
- Có thể hỗ trợ locality của dữ liệu gần nhau theo key.
- Dễ mô tả zone ranges trên shard key có thứ tự.

Rủi ro:

- Shard key tăng đơn điệu, như timestamp ghi liên tục, có thể tập trung write mới vào vùng đầu/cuối đang nằm trên một shard.
- Khóa có cardinality thấp hoặc giá trị rất lệch có thể gây phân bố không đều.
- Query không dùng shard key vẫn có thể scatter-gather.

### 6.2. Hashed sharding

Hashed sharding dùng giá trị hash của shard key để phân phối giá trị khóa:

~~~javascript
// Key pattern minh họa.
{ customerId: "hashed" }
~~~

Lợi ích:

- Giá trị hash có xu hướng phân bố đều hơn các giá trị gốc tăng đơn điệu.
- Giảm nguy cơ write hotspot do một khóa tăng tuần tự nếu cardinality đủ tốt.

Đánh đổi:

- Hash phá vỡ thứ tự giá trị gốc, nên query theo **range** của khóa ban đầu khó định tuyến tới một vùng liên tiếp.
- Nếu chỉ có một **giá trị shard key lặp lại rất nhiều** (một tenant cực lớn), hash nó vẫn chỉ cho một giá trị hash, không tự chia tập document thuộc giá trị đó đều cho nhiều shard.
- Hashed index không hỗ trợ `unique: true`.

Ví dụ shard key `{ tenantId: "hashed" }` có thể giúp phân phối **nhiều tenant** có ID khác nhau, nhưng không giải quyết triệt để tình huống **một tenant chiếm 90% tải**.

### 6.3. Compound shard key

Có thể dùng nhiều trường trong shard key, chẳng hạn:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Tính chất:

- Tiền tố `tenantId` có thể hỗ trợ định tuyến theo tenant, nhưng nếu một tenant trải qua nhiều ranges/shards, query chỉ có tenantId vẫn có thể chạm nhiều shard.
- Thêm `orderId` làm tăng số tổ hợp khóa, giúp chia dữ liệu của một tenant lớn khi mô hình phân bố và balancing cho phép.
- Các query có **đầy đủ điều kiện shard key** thường có cơ hội được định tuyến chính xác hơn query chỉ có một phần khóa.
- Cần thiết kế index/query patterns, không chọn compound key chỉ vì “nhiều trường thì tốt”.

### 6.4. Chọn shard key theo workload, không chỉ theo schema

Cần trả lời:

1. Đa số query có filter nào?
2. Query theo tenant, theo orderId hay theo time range?
3. Cardinality của key bao nhiêu?
4. Có một giá trị cực kỳ phổ biến không?
5. Dữ liệu ghi liên tục có tạo hotspot ở range cuối không?
6. Một tenant lớn có cần chia qua nhiều shard không?
7. Có yêu cầu unique index nào không?
8. Có nhu cầu đặt tenant ở region cụ thể qua zone ranges không?

Kết luận: **Shard key là lựa chọn vật lý có ảnh hưởng đến query routing**, trong khi `tenantId` có thể đơn thuần là **khóa phân vùng logic** phục vụ nghiệp vụ.

## 7. Targeted query và scatter-gather

Giả sử collection `orders` sharded theo `{ tenantId: 1, orderId: 1 }`.

Query có đủ khóa:

~~~javascript
db.orders.findOne({
  tenantId: "tenant-a",
  orderId: "ORD-1001"
});
~~~

`mongos` có cơ sở để định tuyến vào vùng shard key phù hợp; trong phân bố thông thường, point query đầy đủ khóa có thể được target một shard.

Query chỉ theo tenant:

~~~javascript
db.orders.find({
  tenantId: "tenant-a"
});
~~~

Có thể phải chạm **nhiều shard** nếu ranges của tenant-a trải trên nhiều shard.

Query không có shard key:

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Có thể phải **broadcast/scatter-gather** qua nhiều shard và merge kết quả.

| Query pattern | Khả năng routing |
| --- | --- |
| Equality đầy đủ shard key | Thường target rõ nhất |
| Filter theo tiền tố compound shard key | Có thể target một hoặc nhiều shard |
| Range phù hợp shard key | Có thể target tập ranges/shards liên quan |
| Chỉ filter trên field không thuộc shard key | Thường phải hỏi nhiều/tất cả shards |
| Sort/aggregate không target shard key | Có thể phải merge kết quả liên shard |

**Không nhầm:** Sharding tăng capacity tổng nhưng một query cần quét toàn cluster có thể **đắt hơn** query tương tự trên dataset nhỏ chưa shard. Sharding không thay thế index, projection, filter và query design.

## 8. Chunks, balancer và vì sao phân bố không luôn đều

MongoDB phân chia không gian shard key thành các **chunks/ranges**. Mỗi chunk có ranh giới **bao gồm cận dưới, loại cận trên**.

~~~text
[MinKey, 100)  -> Shard A
[100, 500)     -> Shard B
[500, MaxKey)  -> Shard C
~~~

Balancer có thể chuyển chunks/ranges giữa shard để cân bằng theo cơ chế của phiên bản. Việc di chuyển có chi phí mạng, I/O và metadata.

### 8.1. Balancer không phải bộ chia tải tức thì

- Không hứa mỗi shard luôn có cùng số document.
- Không hứa mỗi shard luôn có cùng số byte, CPU hoặc write QPS.
- Một tenant có nhiều document nhưng chỉ một shard key value có thể làm một vùng khóa nóng.
- Một range có dữ liệu rất lớn có thể khó chia nhỏ nếu thiếu giá trị shard key khác nhau.
- Zone rules có thể cố ý giữ một phần dữ liệu ở shard được chỉ định, khiến phân bố byte không đều.
- Migration/chunk movement không thay đổi yêu cầu app phải route query đúng khóa.

**“Đã bật sharding thì MongoDB tự làm đều mọi thứ”** là một hiểu lầm. Chọn shard key và đo tải thực tế vẫn là trách nhiệm thiết kế.

## 9. Replication và sharding có thể kết hợp

Một cluster có **3 shards**, mỗi shard là **replica set 3 data-bearing members**:

~~~text
                  SHARDED CLUSTER
               ~3 TB dữ liệu logic
                       |
                mongos / CSRS
              /        |        \
             v         v         v
           Shard A   Shard B   Shard C
           ~1 TB     ~1 TB     ~1 TB
          A1 A2 A3  B1 B2 B3  C1 C2 C3
          3 copies  3 copies  3 copies
~~~

Trong ví dụ đơn giản:

- Tổng dữ liệu ứng dụng logic ≈ **3 TB**.
- Mỗi shard giữ ≈ **1 TB** dữ liệu logic.
- Nếu mỗi shard có ba bản sao đầy đủ, tổng dung lượng lưu trữ vật lý cho dữ liệu shard (chưa tính index, oplog, overhead, compression) có thể xấp xỉ **9 TB**.
- Việc thêm replica vào shard A tăng **bản sao** dữ liệu shard A, không tự tăng số tập dữ liệu được phân phối.
- Việc thêm **shard D** có thể tăng capacity dữ liệu logic và giúp phân phối tải sau khi dữ liệu/chunks được chuyển thích hợp.

Đây chỉ là tính toán định hướng: kích thước thực tế phụ thuộc index, oplog, compression, journal, temporary files, imbalance và config servers.

### 9.1. Lợi ích phối hợp

**Sharding** tạo khả năng phân phối storage/write workload trên nhiều shard.

**Replication trong từng shard** giúp shard tiếp tục khi một data-bearing member hỏng và còn điều kiện bầu primary mới.

**Config server replica set** bảo vệ metadata của sharded cluster.

Một cluster production không nên coi một shard một máy độc lập là kiến trúc HA tương đương replica set; MongoDB hiện hành yêu cầu shard là replica set.

### 9.2. Một shard mất toàn bộ khác một member mất

Nếu **một member** của shard replica set mất, các member còn lại có thể tiếp tục sau election nếu đủ điều kiện.

Nếu **toàn bộ shard** không khả dụng, dữ liệu nằm trên shard đó không thể được truy xuất đầy đủ qua cluster. Query chạm shard bị mất có thể thất bại hoặc trả lỗi, dù những shard khác vẫn khỏe.

Thêm replication giúp chịu lỗi member, **không** đảm bảo cluster phục vụ đầy đủ mọi dữ liệu khi cả shard/zone hỏng.

## 10. Phân vùng nghiệp vụ nghĩa là gì?

**Phân vùng nghiệp vụ** là cách phân loại dữ liệu theo khái niệm thuộc business domain:

- Tenant/công ty: `tenantId`.
- Năm tài chính: `fiscalYear`.
- Khu vực pháp lý: `countryCode`.
- Nhóm sản phẩm: `businessUnit`.
- Vòng đời dữ liệu: active/archive.
- Lớp dịch vụ: free/pro/enterprise.
- Loại giao dịch hoặc nguồn sự kiện.

Mục tiêu có thể là:

1. Cách ly tenant hoặc quyền truy cập.
2. Đặt chính sách retention/backup khác nhau.
3. Dễ khoanh vùng nghiệp vụ khi di chuyển dữ liệu.
4. Giảm phạm vi truy vấn.
5. Phân công vận hành theo nhóm dữ liệu.
6. Tách tenant lớn khỏi tenant nhỏ.
7. Hỗ trợ tuân thủ chính sách lưu trữ theo vùng địa lý.

Điều đó **chưa tự nói dữ liệu nằm trên máy nào**. Phân vùng nghiệp vụ có thể chỉ là một field, một tập collection, nhiều database hoặc nhiều cluster riêng biệt.

### 10.1. Phân vùng logic trong cùng collection

Ví dụ:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "tenant-a",
  orderId: "ORD-1001",
  total: 250
}
~~~

Mọi tenant vẫn dùng chung `db.orders`. Query phải có tenantId:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID"
});
~~~

Index thường dùng:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

**Đây không nhất thiết là sharding.** Trên một replica set, tất cả document tenant-a/b/c vẫn thuộc cùng một dataset được replicate cho mọi data-bearing member.

### 10.2. Collection theo năm

Ứng dụng có thể tạo:

~~~text
orders_2024
orders_2025
orders_2026
orders_2027
~~~

Khi truy vấn đơn của năm 2026, ứng dụng chọn `orders_2026`. Đây là **phân vùng theo thời gian do application định nghĩa**.

Ưu điểm: dễ thao tác retention/archive theo collection và khoanh phạm vi một năm.

Nhược điểm:

- Phải chọn đúng collection khi ghi/đọc.
- Báo cáo nhiều năm có thể phải query nhiều collection hoặc dùng `$unionWith` ở ngữ cảnh hỗ trợ.
- Index và schema/validator phải quản lý trên nhiều collection.
- Quá nhiều namespace làm tăng chi phí metadata/operations.
- Không tự phân phối lên nhiều máy nếu tất cả collection cùng ở một replica set.

### 10.3. Database per tenant

~~~text
tenant_a.orders
tenant_b.orders
tenant_c.orders
~~~

Lợi ích: ranh giới quản lý và đặt quyền theo database có thể rõ ràng hơn với một số mô hình.

Nhược điểm: migration, indexes, schema versions, connection pooling, backup/restore và cross-tenant reporting phức tạp hơn. Dùng một database riêng cho mỗi tenant **không tự** tăng write capacity nếu mọi database vẫn ở một primary của cùng replica set.

### 10.4. Cluster per tenant hoặc nhóm tenant

Một số hệ thống ánh xạ tenant lớn hoặc nhóm khách hàng đặc biệt sang **cluster độc lập**.

Ưu điểm:

- Cô lập tải tốt hơn.
- Có thể cấp capacity, phiên bản, vùng địa lý và lịch vận hành riêng.
- Hạn chế ảnh hưởng của một tenant quá lớn tới tenant khác.

Đánh đổi:

- Chi phí nhiều cluster.
- App phải quản lý **tenant → cluster mapping**.
- Migration giữa clusters phức tạp.
- Thống kê cross-tenant và transaction cross-cluster khó hơn; không có một `mongos` chung mặc định để tự join mọi cluster độc lập.
- Cần đồng bộ policy bảo mật, backup, schema và index trên nhiều deployment.

**Không nhầm** nhiều clusters do ứng dụng route với **một sharded cluster** có `mongos` điều phối toàn bộ collection.

## 11. Bốn kiểu multi-tenancy phổ biến

| Kiểu | Mô tả | Có phải MongoDB sharding không? | Điểm mạnh | Điểm yếu |
| --- | --- | --- | --- | --- |
| Shared collection | Document có `tenantId` | Không nhất thiết | Ít namespace, dễ triển khai | Cần filter/auth chặt, tenant nóng cạnh tranh tài nguyên |
| Collection per tenant | Mỗi tenant có collection riêng | Không nhất thiết | Có thể tùy index/TTL theo tenant | Nhiều collection và metadata |
| Database per tenant | Database riêng cho tenant | Không nhất thiết | Ranh giới quản lý rõ | Provisioning/migrations phức tạp |
| Cluster per tenant/group | App route sang deployment riêng | **Không phải** một sharded cluster theo nghĩa MongoDB | Cách ly tài nguyên mạnh | Chi phí và cross-cluster query |
| Shared sharded collection | Một collection sharded có `tenantId` trong khóa hoặc filter | **Có**, nếu đã shard collection | Scale-out dưới một namespace logic | Shard key/route và phân bố khó |

**Quan trọng:** Tenant là khái niệm **nghiệp vụ**, shard là đơn vị **hạ tầng và phân phối dữ liệu MongoDB**. Không có quy tắc “một tenant bằng một shard”.

## 12. Trường hợp một tenant cực lớn

Giả sử:

~~~text
Tenant A: 90% write QPS, 70% dữ liệu
Tenant B:  5% write QPS, 15% dữ liệu
Tenant C:  3% write QPS, 10% dữ liệu
Còn lại:  2% write QPS,  5% dữ liệu
~~~

Nếu shard key là `{ tenantId: "hashed" }`, tất cả document có cùng tenantId A tạo cùng một hashed key value. Một giá trị khóa đơn lẻ không tự được trải đều trên nhiều chunks/shards chỉ vì số document rất lớn.

**Hệ quả:** Một tenant nóng có thể trở thành điểm nghẽn dù tổng số shards nhiều.

Những hướng thiết kế cần cân nhắc:

- Dùng **compound shard key** có thêm field đủ đa dạng bên trong tenant, như `{ tenantId: 1, orderId: 1 }`, nếu query patterns và uniqueness phù hợp.
- Tách tenant rất lớn sang **cluster dedicated**.
- Phân phối workload theo bucket hoặc một giá trị chia tải có quy tắc rõ, đồng thời xử lý fan-out truy vấn.
- Giới hạn query nặng, cache hoặc phân công dedicated read capacity.
- Đo hot shard theo QPS/CPU/I/O thay vì chỉ theo dung lượng.

Không tự đặt một trường random `partitionNo` rồi dùng làm shard key nếu những query chính không biết partitionNo: như vậy có thể buộc truy vấn fan-out sang mọi phân vùng.

## 13. Ví dụ thực hành: phân vùng logic trước khi sharding

Phần này chạy được trên một MongoDB database bình thường, **không cần sharded cluster**.

~~~javascript
const lab = db.getSiblingDB("partitioning_lab");

lab.orders.drop();

lab.orders.insertMany([
  { _id: 1, tenantId: "A", orderId: "A-001",
    status: "PAID", total: 100,
    createdAt: ISODate("2026-01-01T09:00:00Z") },
  { _id: 2, tenantId: "A", orderId: "A-002",
    status: "PAID", total: 150,
    createdAt: ISODate("2026-01-02T09:00:00Z") },
  { _id: 3, tenantId: "A", orderId: "A-003",
    status: "CANCELLED", total: 50,
    createdAt: ISODate("2026-01-03T09:00:00Z") },
  { _id: 4, tenantId: "A", orderId: "A-004",
    status: "PAID", total: 250,
    createdAt: ISODate("2026-01-04T09:00:00Z") },
  { _id: 5, tenantId: "A", orderId: "A-005",
    status: "PENDING", total: 300,
    createdAt: ISODate("2026-01-05T09:00:00Z") },
  { _id: 6, tenantId: "A", orderId: "A-006",
    status: "PAID", total: 200,
    createdAt: ISODate("2026-01-06T09:00:00Z") },

  { _id: 7, tenantId: "B", orderId: "B-001",
    status: "PAID", total: 75,
    createdAt: ISODate("2026-01-01T10:00:00Z") },
  { _id: 8, tenantId: "B", orderId: "B-002",
    status: "PAID", total: 125,
    createdAt: ISODate("2026-01-02T10:00:00Z") },
  { _id: 9, tenantId: "B", orderId: "B-003",
    status: "PENDING", total: 200,
    createdAt: ISODate("2026-01-03T10:00:00Z") },
  { _id: 10, tenantId: "B", orderId: "B-004",
    status: "PAID", total: 50,
    createdAt: ISODate("2026-01-04T10:00:00Z") },

  { _id: 11, tenantId: "C", orderId: "C-001",
    status: "PAID", total: 40,
    createdAt: ISODate("2026-01-01T11:00:00Z") },
  { _id: 12, tenantId: "C", orderId: "C-002",
    status: "PAID", total: 60,
    createdAt: ISODate("2026-01-02T11:00:00Z") },
  { _id: 13, tenantId: "C", orderId: "C-003",
    status: "CANCELLED", total: 90,
    createdAt: ISODate("2026-01-03T11:00:00Z") },

  { _id: 14, tenantId: "D", orderId: "D-001",
    status: "PAID", total: 300,
    createdAt: ISODate("2026-01-01T12:00:00Z") },
  { _id: 15, tenantId: "D", orderId: "D-002",
    status: "PAID", total: 500,
    createdAt: ISODate("2026-01-02T12:00:00Z") }
]);

lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_date" }
);

lab.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "uq_tenant_order", unique: true }
);
~~~

Ở đây `tenantId` là **khóa phân vùng nghiệp vụ**, và index giúp query/constraint. Nhưng vì chưa chạy `shardCollection`, **không có sharding vật lý**.

### 13.1. Đếm theo tenant

~~~javascript
lab.orders.aggregate([
  { $group: { _id: "$tenantId", orders: { $sum: 1 } } },
  { $sort: { _id: 1 } }
]);
~~~

Giá trị dự kiến:

| Tenant | Số đơn |
| --- | ---: |
| A | 6 |
| B | 4 |
| C | 3 |
| D | 2 |
| **Tổng** | **15** |

### 13.2. Tổng doanh thu PAID theo tenant

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Đối chiếu:

| Tenant | Số đơn PAID | Doanh thu PAID |
| --- | ---: | ---: |
| A | 4 | 700 |
| B | 3 | 250 |
| C | 2 | 100 |
| D | 2 | 800 |
| **Tổng** | **11** | **1.850** |

Số liệu này giúp bạn nhìn **phân bố nghiệp vụ**. Nó **chưa cho biết** những document đã nằm ở mấy shard.

### 13.3. Query theo tenant

~~~javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ createdAt: -1 });
~~~

Query này có thể tận dụng index `ix_tenant_status_date` ở collection bình thường. Nếu sau này sharding theo một khóa có `tenantId` trong tiền tố, query có thể còn có lợi về **shard targeting**. Hai lợi ích khác nhau:

- **Index:** giảm số document/key cần xét bên trong một shard/server.
- **Shard key:** giảm số shard cần được liên hệ.

Một query được target đúng shard vẫn có thể chậm nếu shard đó thiếu index. Một query có index tốt vẫn có thể tốn chi phí scatter-gather nếu thiếu shard key.

## 14. Quan sát sharding trên cluster đã được dựng sẵn

Phần này **chỉ áp dụng khi có sharded cluster thử nghiệm** và bạn kết nối qua `mongos`. Không tự bật sharding hoặc thay đổi cluster production chỉ để hoàn thành bài tập.

### 14.1. Xem cluster status

~~~javascript
// Chạy trong mongosh đang kết nối mongos.
sh.status();
~~~

Kết quả cung cấp thông tin về shards, databases và metadata của collections đã sharded, tùy phiên bản/quyền và cấu hình.

Bạn cũng có thể dùng:

~~~javascript
db.hello();
~~~

Khi đang kết nối `mongos`, response thường có `msg: "isdbgrid"`, giúp phân biệt router với một `mongod` riêng.

### 14.2. Minh họa shardCollection

Giả sử lab cluster có collection `partitioning_lab.orders`, shard key được chọn sau khi phân tích workload và đã có index phù hợp:

~~~javascript
// CHỈ MINH HỌA: thay đổi metadata sharding trong cluster.
// Không tự chạy trên production hoặc collection đang có
// traffic khi chưa có kế hoạch rollout.
sh.shardCollection(
  "partitioning_lab.orders",
  { tenantId: 1, orderId: 1 }
);
~~~

Trong cluster thật, preconditions và quy trình sharding collection phụ thuộc phiên bản, tình trạng collection, index, unique indexes, zone ranges và quyền quản trị. Ví dụ ở đây chỉ thể hiện **lệnh gắn collection với shard key**.

**Đặc biệt:** Collection `lab.orders` ở mục 13 đã có unique index `{tenantId:1,orderId:1}` và `_id_`; khi chuyển sang sharded collection, phải kiểm tra điều kiện về **uniqueness**, shard-key prefix, dữ liệu `_id` và quy tắc cluster. Không tự coi mọi index trên collection thường đều hợp lệ y nguyên sau sharding.

### 14.3. Đọc cluster routing

Sau khi sharding hoàn tất, query qua `mongos`:

~~~javascript
lab.orders.find({
  tenantId: "A",
  orderId: "A-001"
}).explain("queryPlanner");
~~~

Các trường trong explain có thể khác giữa version và engine; trong sharded cluster, plan thường cho thấy thông tin về shard được truy vấn, routing và các subplans. Cần phân biệt:

- **Shard targeting:** query được gửi đến bao nhiêu shard.
- **Index selection:** mỗi shard có dùng `IXSCAN`, `COLLSCAN` hoặc plan khác.
- **Merge stage:** kết quả nhiều shard có cần hợp nhất/sort không.

Không dùng một ảnh chụp explain để suy luận tải thực tế; cần đo trên workload và phân bố dữ liệu thực tế.

## 15. Phân vùng theo thời gian không tự tương đương time-series hay shard key

Ứng dụng có thể chia:

~~~text
events_2025
events_2026
events_2027
~~~

hoặc dùng một collection `events` với field `occurredAt` và index.

Ba lựa chọn khác nhau:

| Lựa chọn | Cách tổ chức | Tự scale-out qua shards? |
| --- | --- | --- |
| Collection theo năm | Ứng dụng route dữ liệu vào tên collection | Không |
| Một collection thường có index theo Date | B-tree index hỗ trợ filter/sort thời gian | Không |
| Một collection sharded theo key có Date | MongoDB phân phối ranges/chunks | Có, nếu cluster được sharded |
| Time series collection | Cơ chế bucket dành cho measurement | Không tự đồng nghĩa đã sharded |

Có thể **shard time series collection** trong những phiên bản/thiết lập được hỗ trợ, nhưng time series và sharding là **hai quyết định riêng** với các giới hạn đặc thù.

Nếu shard key chỉ là `occurredAt` tăng liên tục, write có thể tập trung ở vùng range cuối. Nếu dùng hashed key để phân đều, query theo khoảng thời gian có thể phải liên hệ nhiều shards. Phải chọn theo mục tiêu thực tế, không máy móc “dữ liệu có timestamp thì shard theo timestamp”.

## 16. Zone sharding: kết nối quy tắc nghiệp vụ với vị trí shard

MongoDB cho phép cấu hình **zones** gắn với một số shards và các **khoảng shard key**. Balancer có thể di chuyển ranges vào shards thuộc zone phù hợp.

Ví dụ nghiệp vụ:

~~~text
Tenant thuộc khu vực EU -> dữ liệu nằm trong zone eu
Tenant thuộc khu vực APAC -> dữ liệu nằm trong zone apac
~~~

Đây là ví dụ về kết hợp:

- **Phân vùng nghiệp vụ:** xác định tenant/khu vực của dữ liệu.
- **Sharding:** dùng shard key để route và chia ranges.
- **Zone policy:** chỉ định các shard có thể chứa ranges thuộc một zone.
- **Replication:** sao chép dữ liệu bên trong mỗi shard replica set.

### 16.1. Zone không chỉ là một field region

Thêm `region: "EU"` vào document **không** tự kích hoạt zone sharding. Zone phải được cấu hình trên cluster và phạm vi khóa phù hợp. Ví dụ API quản trị có `sh.addShardToZone()` và `sh.updateZoneKeyRange()`, nhưng chúng thay đổi cluster metadata nên không sử dụng tùy tiện trong bài lab.

### 16.2. Những giới hạn khi dùng zone

- Zone range dựa trên **shard key**, không thể tùy ý chọn một field ngoài key để route.
- Ranges có cận dưới bao gồm, cận trên loại trừ.
- Shard có thể thuộc nhiều zones, tùy cấu hình.
- Balancer cần thời gian đạt trạng thái phân phối mong muốn; không đảm bảo migration tức thì.
- Một shard replica set có thể có members ở các vị trí địa lý khác nhau; chỉ xem zone không đủ để chứng minh mọi **bản sao vật lý** nằm đúng khu vực pháp lý.
- Với hashed shard key, zone ranges dựa trên **giá trị đã hash**, không mặc nhiên ánh xạ đơn giản theo chuỗi tenant ID gốc.

**Không coi zone sharding một mình là cam kết pháp lý về data residency.** Cần kiểm tra vị trí của tất cả data-bearing members, backup, config metadata, logs, export và quy tắc vận hành.

## 17. Index và uniqueness ở ba mô hình

### 17.1. Replica set không thay đổi phạm vi unique của collection

Trên collection thường nằm trong một replica set, unique index bảo vệ khóa của collection trên dataset đó. Replication sao chép thay đổi và index theo cơ chế MongoDB, không tạo “một uniqueness riêng” cho từng secondary để ứng dụng ghi độc lập.

### 17.2. Sharded collection có quy tắc riêng

Với ranged sharding, unique index trên sharded collection phải phù hợp với **shard-key prefix** theo quy tắc MongoDB hỗ trợ.

Ví dụ shard key:

~~~javascript
{ tenantId: 1 }
~~~

Index bảo vệ email duy nhất trong tenant:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

Ngược lại, unique index chỉ trên `{emailKey:1}` không có shard-key prefix theo tình huống trên, nên không thể giả định MongoDB chấp nhận/đảm bảo toàn cluster.

### 17.3. _id và global uniqueness

Nếu `_id` không phải shard key, MongoDB có các tình huống chỉ thực thi uniqueness của `_id` trong phạm vi từng shard. Ứng dụng cần tạo định danh toàn cục đủ duy nhất khi nghiệp vụ dựa vào một `_id` global.

### 17.4. Phân vùng nghiệp vụ thành nhiều clusters có ràng buộc riêng

Nếu tenant A và tenant B được ghi ở **hai MongoDB clusters độc lập**, unique index trên collection ở cluster A **không** tự chặn một giá trị trùng ở cluster B. Nếu cần global uniqueness xuyên nhiều clusters, cần mô hình registry/coordination hoặc kiến trúc dữ liệu có ràng buộc chung được thiết kế rõ.

**Tóm lại:** Phải hỏi “ràng buộc duy nhất ở **phạm vi nào**?” trước khi quyết định index.

## 18. Giao dịch và tính nhất quán khi dữ liệu bị phân phối

### 18.1. Replication: write concern và read preference

Trong replica set:

- Write thông thường vào primary.
- `writeConcern: {w:"majority"}` xác định mức xác nhận qua đa số member theo quy tắc deployment.
- Read preference có thể gửi read tới secondary.
- Secondary có thể stale do replication lag, ngay cả khi primary đã xác nhận write.

**Replication không tự đồng nghĩa linearizable reads trong mọi cấu hình.**

### 18.2. Sharding: một business transaction có thể chạm nhiều shards

Giả sử chuyển tiền:

~~~text
Account A ở Shard 1
Account B ở Shard 2

Debit A   -> Shard 1
Credit B  -> Shard 2
~~~

Hai thao tác cập nhật trên **hai documents** và **hai shards** không tự là một write nguyên tử đơn chỉ vì chạy qua `mongos`. MongoDB hỗ trợ **distributed transactions** trong các phiên bản/topology phù hợp, nhưng có chi phí phối hợp và giới hạn vận hành.

Một thiết kế tốt cố gắng gom dữ liệu thường xuyên được cập nhật cùng nhau vào phạm vi hợp lý khi có thể, nhưng không đánh đổi quá nhiều bằng cách tạo shard key khiến hotspot hoặc query khác rất đắt.

### 18.3. Phân vùng nghiệp vụ không tạo transaction qua nhiều clusters

Nếu app tự chia tenant vào các clusters độc lập, transaction MongoDB trên cluster A **không tự tham gia** một transaction toàn cục với cluster B. Cần thiết kế saga, outbox/inbox, idempotency hoặc quy trình điều phối theo business requirements.

### 18.4. Một write trên một document vẫn có atomicity

Sharding không loại bỏ tính nguyên tử của thao tác cập nhật **một document** trong phạm vi MongoDB đảm bảo. Ví dụ:

~~~javascript
db.inventory.updateOne(
  {
    tenantId: "A",
    sku: "SKU-1",
    stock: { $gte: 1 }
  },
  {
    $inc: { stock: -1 }
  }
);
~~~

Điều kiện tồn kho phải được kiểm tra cùng thao tác ghi, không dùng một read stale từ secondary rồi update vô điều kiện. Nếu collection đã sharded, filter nên được thiết kế theo quy tắc định tuyến và tính hợp lệ của thao tác trên sharded collection.

## 19. Scale-out và availability không phải một con số duy nhất

Một yêu cầu “hệ thống cần tăng gấp ba” chưa đủ để chọn cơ chế. Cần biết tăng gì:

| Mục tiêu | Replication | Sharding | Phân vùng nghiệp vụ |
| --- | --- | --- | --- |
| Chịu lỗi một member | **Phù hợp** | Chỉ khi mỗi shard có replication/HA | Không tự đủ |
| Lưu thêm nhiều dữ liệu logic | Mỗi bản sao vẫn giữ toàn dataset | **Phù hợp** nếu phân phối đều | Có thể, nếu partition đặt trên capacity khác |
| Phân phối write QPS | Một primary vẫn nhận write cho dataset | **Phù hợp** nếu shard key đủ đa dạng | Có thể với các clusters độc lập |
| Chuyển báo cáo khỏi primary | Có thể read secondary | Có thể phân phối read giữa shards | Có thể dùng reporting cluster/partition |
| Cách ly một tenant lớn | Không riêng bằng replication | Có thể qua shard key/zone nhưng cần thiết kế | Database/cluster riêng có thể rõ ràng |
| Archive một năm cũ | Không trực tiếp | Không thay retention | Collection theo năm/retention phù hợp |
| Hạn chế dữ liệu theo vùng | Placement của replicas phải thiết kế | Zone sharding có thể hỗ trợ | Routing tenant/cluster theo vùng có thể hỗ trợ |
| Truy vấn cross-tenant nhanh | Không trực tiếp | Phụ thuộc shard targeting/query | Có thể bị khó hơn nếu tách clusters |

Không có câu trả lời mặc định “thêm shard luôn nhanh hơn” hay “thêm replica luôn rẻ hơn”. Cần đo kích thước dataset, working set, QPS, query patterns và yêu cầu HA.

## 20. Ba tình huống quyết định kiến trúc

### Tình huống A — Dữ liệu vừa đủ một server, nhưng downtime không thể chấp nhận

Yêu cầu:

- Dataset 100 GB.
- Ứng dụng không cần write scale-out lớn.
- Muốn có automatic failover khi một node lỗi.

**Ưu tiên:** replica set có các data-bearing members đủ điều kiện election và backup. Sharding chưa chắc cần thiết, vì thêm router/shards/config metadata làm tăng độ phức tạp mà không giải quyết tốt hơn yêu cầu cốt lõi.

### Tình huống B — Dataset và write workload vượt khả năng một primary

Yêu cầu:

- Collection đơn hàng rất lớn.
- Nhiều tenant ghi song song.
- Tăng CPU/storage đơn máy không còn đủ.
- Query hầu hết có tenantId/orderId.

**Cân nhắc:** sharded collection với shard key được benchmark theo workload, shards triển khai dưới dạng replica sets, router qua `mongos` và kế hoạch quan sát balancing/hotspots. Có thể vẫn cần phân vùng nghiệp vụ để lọc theo tenant và retention.

### Tình huống C — Một tenant enterprise yêu cầu cách ly hoàn toàn

Yêu cầu:

- Tenant enterprise có SLA, phiên bản hoặc vùng lưu riêng.
- Không muốn cạnh tranh tải với nhóm tenant phổ thông.
- Có khả năng chấp nhận quản trị riêng và chi phí cao hơn.

**Cân nhắc:** dedicated database/cluster theo tenant hoặc nhóm tenant, ánh xạ routing trong app, backup và security riêng. Không nhầm chiến lược đó với việc để MongoDB tự chia một collection bằng shards; có thể dùng sharding **bên trong** cluster dedicated nếu tenant quá lớn.

## 21. Chi phí vận hành và failure domains

### 21.1. Replication

Phải vận hành:

- Election và failover.
- Oplog retention.
- Replication lag.
- Write concern và read preference.
- Dung lượng của các bản sao và indexes.
- Backup/restore; bản sao không phải backup theo thời điểm.

### 21.2. Sharding

Ngoài replication của mỗi shard, cần vận hành:

- `mongos` và config server replica set.
- Shard key/index design.
- Balancer, chunk/range migrations.
- Scatter-gather query performance.
- Thêm/bớt shards theo quy trình.
- Distributed transactions khi có.
- Zone placement và tính khả dụng khi một shard mất.
- Unique index constraints và `_id` global uniqueness.

### 21.3. Phân vùng nghiệp vụ

Ứng dụng và vận hành phải quản lý:

- Danh mục partition (tenant → collection/database/cluster).
- Provisioning tenant mới.
- Index/schema migration đồng bộ trên partitions.
- Di chuyển tenant, split/merge partitions.
- Cross-partition analytics.
- Quyền truy cập tránh lộ dữ liệu tenant.
- Backup/retention và data residency theo business policy.

**Phân vùng nghiệp vụ có thể tăng complexity ở tầng application**, ngay cả khi mỗi MongoDB cluster riêng rất đơn giản.

## 22. Quy trình ra quyết định có hệ thống

Dùng trình tự sau:

~~~text
1. Cần HA và chịu lỗi member?
      |
      +-- Có --> thiết kế replica set / backups / failover
      |
      v
2. Dataset hoặc write QPS đã vượt một shard/primary?
      |
      +-- Có --> phân tích sharding, shard key, workload
      |
      v
3. Cần tách tenant/năm/region theo business policies?
      |
      +-- Có --> định nghĩa logical partitions
                  rồi chọn collection/database/cluster/zone
      |
      v
4. Có cần kết hợp không?
      |
      +-- Sharded cluster gồm replica sets
      +-- TenantId + shard key
      +-- Zone sharding theo business region
      +-- Dedicated cluster cho tenant lớn
      |
      v
5. Đo lại failure, read/write QPS, routing,
   query latency, lag, cost và operational complexity
~~~

### Checklist trước khi quyết định sharding

1. Dataset có thực sự vượt capacity/working set phù hợp của một replica set?
2. Write workload có thể phân bố trên nhiều shard keys?
3. Query phổ biến có mang shard key không?
4. Có một tenant hay một timestamp hot không?
5. Cross-shard aggregation/transactions có tần suất cao không?
6. Unique constraints có phù hợp shard-key prefix không?
7. Index có hỗ trợ query bên trong từng shard không?
8. Có kế hoạch reshard/migration và quan sát hotspots không?
9. Có đủ ngân sách vận hành thêm `mongos`/CSRS/shards không?
10. Cần placement theo zone hoặc dữ liệu cư trú theo vùng không?

## 23. Sai lầm thường gặp

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Ba replicas tức lưu được ba lần dữ liệu logic” | Mỗi data-bearing member giữ cùng dataset | Replication tạo bản sao để HA |
| “Replica set có ba primary để ghi” | Một replica set thông thường có một primary nhận write | Muốn phân phối write cân nhắc nhiều shards |
| “Sharding làm mọi shard có bản sao toàn bộ dữ liệu” | Mỗi shard giữ subset | Bản sao toàn bộ **subset** nằm trong replica set của shard |
| “Có tenantId là đã shard theo tenant” | Field logic không tạo physical shard | Cần cấu hình shardCollection/cluster đúng |
| “Một tenant luôn ứng với một shard” | Shard key ranges có thể chứa nhiều tenant; tenant lớn có thể trải nhiều ranges | Shard là đơn vị vật lý, tenant là domain |
| “Collection per year tự phân bố lên nhiều servers” | Các collection có thể ở cùng primary shard/replica set | Phải có placement/routing vật lý riêng |
| “Sharding không cần replica set” | Shards hiện hành phải triển khai là replica sets | Replication bổ trợ HA |
| “Secondary luôn có dữ liệu vừa được ghi” | Replication bất đồng bộ | Dùng read preference/read concern/causal consistency phù hợp |
| “Sharding luôn tăng tốc mọi query” | Scatter-gather và merge có thể đắt | Chọn shard key và index theo workload |
| “Hashed tenantId chia một tenant nóng ra mọi shards” | Một tenantId tạo một hashed value | Cần compound/distribution strategy khác |
| “Balancer luôn làm CPU và write QPS đều” | Balancer xử lý placement/ranges, không tối ưu mọi query/workload | Theo dõi hotspots và key distribution |
| “Primary shard là primary member của replica set” | Hai khái niệm khác cấp | Phân biệt database primary shard và replSet primary |
| “Zone tag tự chứng minh tuân thủ luật cư trú dữ liệu” | Replicas, backup và placement khác vẫn tồn tại | Audit toàn bộ dữ liệu/metadata/backup paths |
| “Unique index trên mọi sharded collection như collection thường” | Có yêu cầu shard-key prefix và hạn chế | Xem sharded uniqueness trước rollout |
| “Shard được thêm là dữ liệu tự lập tức cân bằng” | Balancing/migration có thời gian và điều kiện | Lập kế hoạch, giám sát chunk/range movement |
| “Replication thay backup” | Xóa nhầm/lỗi logic được replicate | Backup và kiểm thử restore riêng |
| “Ứng dụng dùng nhiều clusters vẫn có một transaction MongoDB chung” | Clusters độc lập không tự chia sẻ transaction | Saga/coordination khi cần |

## 24. Bài tập thực hành

### Bài 1 — Ba đề xuất, ba nhu cầu

Một hệ thống gặp ba vấn đề:

1. Một máy MongoDB hỏng khiến API ngừng.
2. Một collection vượt capacity của một máy.
3. Phòng kế toán muốn đóng băng dữ liệu theo năm tài chính.

Với từng vấn đề, chọn **replication**, **sharding** hay **phân vùng nghiệp vụ** làm hướng chính. Nêu một lý do và một điều cơ chế đó không tự bảo đảm.

**Đáp án định hướng:** (1) replication cho HA, không thay backup; (2) sharding để scale-out dữ liệu, vẫn cần replica set cho HA; (3) phân vùng theo kỳ/năm hoặc retention policy, không nhất thiết shard.

### Bài 2 — Tính số bản sao, không tính nhầm dữ liệu logic

Có một replica set gồm 3 data-bearing members giữ 300 GB dữ liệu logic, bỏ qua index/oplog/overhead. Mỗi member giữ bao nhiêu dữ liệu logic? Tổng dung lượng bản sao dữ liệu xấp xỉ bao nhiêu?

**Đáp án:** Mỗi member giữ ~300 GB; tổng dữ liệu vật lý lưu theo các bản sao ~900 GB. Không được nói hệ thống có 900 GB dữ liệu nghiệp vụ khác nhau.

### Bài 3 — Sharding với replication

Một cluster có 4 shards, mỗi shard là replica set gồm 3 data-bearing members; dataset logic 4 TB được phân bố đều. Bỏ qua overhead, ước lượng dataset logic trên mỗi shard và tổng bản sao.

**Đáp án:** ~1 TB/shard, ~3 TB bản sao của subset mỗi shard, tổng vật lý ~12 TB cho các bản sao; không phải 12 TB dữ liệu logic duy nhất.

### Bài 4 — Phân vùng tenant logic

Collection `orders` có 15 document như mục 13, tất cả trên một replica set. Field `tenantId` đã được index. Đây đã là MongoDB sharding chưa? Vì sao?

**Đáp án:** Chưa. TenantId là phân vùng nghiệp vụ logic và index giúp query; không có sharded collection/chunk routing qua mongos.

### Bài 5 — Kiểm tra số đơn theo tenant

Chạy `$group` trên `lab.orders` và đối chiếu:

~~~text
A: 6
B: 4
C: 3
D: 2
Tổng: 15
~~~

Nếu nhóm có số đơn quá nhiều, điều gì xảy ra với tải khi shard key chỉ là `tenantId`?

**Đáp án:** Một tenant nóng có thể tập trung vào một shard key value, gây hotspot; cần đánh giá phân bố và compound shard key/kiến trúc khác.

### Bài 6 — Replication lag và read

Một đơn vừa ghi trên primary nhưng không xuất hiện khi đọc `secondaryPreferred`. Đây có phải bằng chứng sharding thất bại không?

**Đáp án:** Không. Đây có thể là stale read do replication lag. Read preference và consistency cần thiết kế phù hợp.

### Bài 7 — Chọn shard key

Workload có nhiều query:

~~~javascript
db.orders.findOne({
  tenantId: "A",
  orderId: "A-001"
});
~~~

So sánh ưu/nhược của `{orderId:"hashed"}`, `{tenantId:1}` và `{tenantId:1,orderId:1}`. Chọn một hướng nếu tenant A chiếm phần lớn dữ liệu, đồng thời nêu điều phải benchmark.

### Bài 8 — Targeted và scatter-gather

Sharded collection dùng `{tenantId:1,orderId:1}`. Đánh giá query nào có khả năng target hẹp hơn:

~~~javascript
db.orders.findOne({ tenantId: "A", orderId: "A-001" });
db.orders.find({ tenantId: "A" });
db.orders.find({ status: "PAID" });
~~~

**Đáp án:** Point query đủ khóa thường định tuyến hẹp nhất; tenant-only có thể đến một hoặc nhiều shards; status-only thường cần scatter-gather.

### Bài 9 — Chia collection theo năm

Một ứng dụng có `orders_2025` và `orders_2026` trên cùng replica set. Điều gì cần thay đổi nếu muốn mỗi năm ở capacity vật lý riêng? Truy vấn cross-year sẽ gặp khó khăn nào?

### Bài 10 — Primary shard và replica set primary

Giải thích hai câu:

- “Database `shop` có primary shard là Shard B.”
- “Replica set của Shard B đang có member B2 làm primary.”

Tại sao hai câu không mâu thuẫn?

### Bài 11 — Global unique key

Collection `users` sharded theo `tenantId`. Ứng dụng muốn email duy nhất toàn nền tảng, nhưng index `{tenantId:1,email:1}` chỉ bảo vệ email trong tenant. Nêu hai hướng kiến trúc có thể cân nhắc.

**Gợi ý:** Thay đổi mô hình shard key/uniqueness nếu phù hợp, hoặc dùng registry riêng có khóa global unique và quy trình phối hợp ghi. Không tùy tiện tạo unique index thiếu shard-key prefix.

### Bài 12 — Zone và data residency

Dữ liệu EU cần nằm trong khu vực EU. Một cluster cấu hình zone EU và đặt range tenant EU lên shard thuộc zone. Những nơi nào vẫn cần kiểm tra ngoài zone ranges?

**Đáp án:** Vị trí toàn bộ data-bearing replica members, backup, exported data, logs, metadata/config, tài khoản truy cập và chính sách vận hành. Zone không tự đảm bảo tuân thủ tuyệt đối.

### Bài 13 — Điều kiện tồn kho dưới concurrency

Backend đọc tồn kho từ secondary rồi trừ stock trên primary khi thấy stock > 0. Nêu lỗi và viết một `updateOne` có điều kiện:

~~~javascript
db.inventory.updateOne(
  { sku: "SKU-1", stock: { $gte: 1 } },
  { $inc: { stock: -1 } }
);
~~~

Giải thích tại sao điều kiện ghi nguyên tử vẫn cần thiết dù dùng sharding và replication.

### Bài 14 — Chọn phương án cho một tenant enterprise

Một tenant lớn cần SLA riêng, backup riêng, có nhân sự quản trị riêng và không được bị ảnh hưởng bởi tenants nhỏ. Chọn giữa shard key tenantId, zone sharding và dedicated cluster. Nêu trade-off chi phí/operability, không chỉ đáp án một từ.

### Bài 15 — Failure domain

Trong một sharded cluster, member A1 của Shard A mất nhưng replica set A còn đủ điều kiện election; sau đó cả Shard B mất. Mô tả tác động khác nhau tới availability. Vì sao một shard khác khỏe không thay thế được dữ liệu của Shard B?

### Bài 16 — Thiết kế kiến trúc tổng hợp

Ứng dụng SaaS có các yêu cầu:

- 4 triệu doanh nghiệp, phần lớn nhỏ nhưng vài doanh nghiệp cực lớn.
- Không muốn một member hỏng làm ngừng dịch vụ.
- Một số tenant có khu vực lưu dữ liệu bắt buộc.
- Báo cáo có thể đọc chậm vài giây, nhưng xác nhận thanh toán không được dùng stale read.
- Dữ liệu tăng vượt một server.

Hãy đề xuất cách kết hợp **replica sets**, **sharding**, **business partitioning**, **zone/dedicated clusters**, **read preference** và **write/read concern**; nêu ít nhất ba rủi ro phải đo trước khi vận hành.

## 25. Tổng kết

Ba cơ chế cần được hiểu **theo mục tiêu**, không theo tên gọi:

- **Replication:** giữ các bản sao đồng bộ bất đồng bộ trong replica set, hỗ trợ availability/failover và một số read distribution; không tự phân phối write của cùng dataset lên nhiều primary.
- **Sharding:** chia sharded collection theo shard key thành chunks/ranges nằm trên nhiều shards; hỗ trợ scale-out storage và phân phối workload khi shard key phù hợp; không tự tạo HA nếu không có replication bên trong shard.
- **Phân vùng nghiệp vụ:** định nghĩa ranh giới tenant, năm, region hoặc service tier; có thể chỉ là filter trong cùng collection hoặc trở thành các collection/databases/clusters riêng; không tự biến thành MongoDB sharding.

Một **sharded cluster production** kết hợp **replica set trên mỗi shard** và **config server replica set**, phục vụ ứng dụng qua `mongos`. Một hệ thống nhiều tenant có thể đặt `tenantId` trong dữ liệu, dùng shard key phù hợp workload, gắn zones cho dữ liệu cần placement riêng và tách tenant lớn sang cluster chuyên dụng khi cần.

**Quy tắc thiết kế cuối:** Bắt đầu từ yêu cầu **availability, capacity, write/read workload, query patterns, consistency, tenant isolation và data locality**. Sau đó mới chọn số replica, số shard, shard key và chiến lược business partition. Dữ liệu chỉ thực sự được scale-out khi routing và placement vật lý hỗ trợ mục tiêu đó.

### Tài liệu MongoDB chính thức

- [Replication](https://www.mongodb.com/docs/manual/replication/) — replica set, primary/secondary, replication lag và failover.
- [Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-members/) — data-bearing members và arbiter.
- [Sharding Introduction and Architecture](https://www.mongodb.com/docs/manual/sharding/) — phân phối dữ liệu, shard key và thành phần cluster.
- [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/) — shards, mongos, config servers.
- [Shards](https://www.mongodb.com/docs/manual/core/sharded-cluster-shards/) — shard replica set, primary shard và unsharded collections.
- [Config Servers](https://www.mongodb.com/docs/manual/core/sharded-cluster-config-servers/) — CSRS, routing metadata và config shard từ 8.0.
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/) — ranges, chunks và phân phối ban đầu.
- [Ranged Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/) — lựa chọn khóa và range queries.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/) — hash distribution và trade-off với range queries.
- [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — shard key selection.
- [Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/) — zone ranges và data locality.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — giới hạn unique indexes.
- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — đọc secondary và stale data.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — giao dịch trong replica set và sharded cluster.
