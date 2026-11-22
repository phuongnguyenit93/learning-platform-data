# Chuyển dữ liệu giữa shard và theo dõi cân bằng tải trong MongoDB

## 1. Bối cảnh: khi dữ liệu được phân tán trên nhiều shard

Một ứng dụng lưu hàng trăm triệu sự kiện trong MongoDB. Thay vì đặt tất cả document trên một replica set, hệ thống tổ chức dữ liệu thành **sharded cluster** với nhiều **shard**. Mỗi shard thông thường là một replica set, nắm giữ một phần dữ liệu. Các **mongos** router định tuyến truy vấn dựa trên metadata sharding; **config server replica set** lưu thông tin cấu hình và quyền sở hữu các khoảng khóa.

Khi dữ liệu tăng lên, một shard có thể chứa nhiều dữ liệu hơn shard khác, hoặc một tập tenant/khóa ghi tăng rất nhanh. MongoDB cần có cách **chuyển quyền sở hữu những khoảng giá trị shard key** từ shard này sang shard khác để phân bố dữ liệu theo chính sách của cluster.

Trong bài này, ta sẽ tìm hiểu:

1. Dữ liệu được chia theo **range/chunk** như thế nào.
2. **Balancer** quyết định và thực hiện việc di chuyển phạm vi dữ liệu ra sao.
3. Cách phân biệt **chuyển dữ liệu vật lý**, **chuyển metadata sở hữu** và **xóa bản sao còn dư**.
4. Những lệnh dùng để quan sát balancer, phân bố dữ liệu và tiến trình di chuyển.
5. Khi nào nên để **tự động cân bằng**, khi nào có thể **di chuyển thủ công**.
6. Ảnh hưởng của **shard key, zone, jumbo range, dữ liệu lệch và hot shard**.
7. Quy trình theo dõi, xử lý sự cố và vận hành an toàn trên môi trường thật.

**Phân biệt ngay từ đầu:** cân bằng **dung lượng dữ liệu** không tự động đồng nghĩa cân bằng **CPU, số lượng query, số thao tác ghi hoặc độ trễ**. Một cluster có kích thước dữ liệu phân bố đều vẫn có thể có một shard chịu phần lớn lưu lượng.

## 2. Những thành phần tham gia vào quá trình chuyển dữ liệu

### 2.1. Shard, mongos và config servers

Sơ đồ khái niệm:

```text
             ỨNG DỤNG / MONGODB DRIVER
                       |
                       v
                 +-----------+
                 |  mongos   |
                 |  router   |
                 +-----------+
                    |     |
        Tra metadata|     | Định tuyến query
                    v     v
      +----------------+  +------------------------------+
      | Config Server  |  | Sharded Data                 |
      | Replica Set    |  |                              |
      |                |  | Shard A   Shard B   Shard C   |
      | Collection     |  |  RS A      RS B      RS C    |
      | ranges/zones/  |  |                              |
      | ownership      |  +------------------------------+
      +----------------+
```

Đơn giản hóa vai trò:

- **`mongos`** nhận request, biết topology và định tuyến theo metadata. Ứng dụng thường kết nối tới mongos chứ không chọn shard đích tùy ý.
- **Shard** lưu tập document thuộc những khoảng shard key mà nó sở hữu.
- **Config servers** lưu metadata về collection đã shard, các khoảng dữ liệu, shard hiện sở hữu và thông tin cấu hình khác.
- **Balancer** là cơ chế quản lý việc chuyển khoảng dữ liệu giữa shard để tiến đến phân bố theo chính sách hiện hành.

Các thành phần có thể phân công tác vụ khác nhau giữa các phiên bản MongoDB. Quan trọng là hiểu **metadata sở hữu** và **dữ liệu đang nằm trên đĩa** không phải lúc nào cũng đổi đồng thời.

### 2.2. Shard key quyết định việc phân hoạch

Giả sử collection `shop.events` shard theo:

```javascript
{ tenantId: 1, eventAt: 1 }
```

Một document:

```javascript
{
  _id: "event-001",
  tenantId: "T01",
  eventAt: ISODate("2026-11-01T10:00:00Z"),
  type: "LOGIN"
}
```

Sẽ được định tuyến theo **giá trị shard key** của nó. Dữ liệu được chia thành các **khoảng giá trị** trong không gian shard key và các khoảng được phân bổ cho shard.

Không nên hiểu “mỗi tenant là một shard” hoặc “mỗi document là một chunk”. Một shard có thể giữ nhiều khoảng, mỗi khoảng chứa rất nhiều document.

## 3. Range và chunk: đơn vị mà balancer quan tâm

### 3.1. Dải khóa, không phải danh sách record tùy ý

Với khóa đơn giản `{ customerId: 1 }`, tưởng tượng:

```text
   Không gian shard key tăng dần

MinKey |--------|-----------|-----------|---------| MaxKey
       A        K           T           Z
         R1         R2          R3         R4

Shard A: R1, R2
Shard B: R3
Shard C: R4
```

Mỗi đoạn là một **range** của shard key. Trong tài liệu và nhiều công cụ của MongoDB, người dùng vẫn thường gặp tên **chunk** để chỉ đơn vị phạm vi được quản lý/di chuyển.

Ví dụ metadata mô phỏng:

```javascript
{
  min: { customerId: "A" },
  max: { customerId: "K" },
  shard: "shardA"
}
```

Hãy đọc nó là: những khóa thuộc phạm vi **từ min đến trước max** được shard A sở hữu. Đó là **mô hình minh họa**, không phải lời khuyên tự tạo hoặc sửa document trong `config.chunks`.

### 3.2. Phạm vi có thể rỗng, nhỏ hoặc rất lớn

Số lượng document của một range không cố định. Hai range có độ dài shard key giống nhau có thể chứa lượng dữ liệu hoàn toàn khác nhau:

```text
Range A: customerId từ A tới K
  10 triệu document

Range B: customerId từ K tới T
  15 nghìn document
```

Vì vậy, **đếm số range/chunk không luôn phản ánh kích thước hoặc tải**.

MongoDB các phiên bản hiện đại (đặc biệt từ 6.0) chủ yếu sử dụng **chênh lệch kích thước dữ liệu** trong quyết định cân bằng thông thường, thay vì chỉ nhìn số lượng chunk. Tên trường và thuật toán chi tiết có thể thay đổi theo phiên bản.

### 3.3. Shard key dạng compound

Với:

```javascript
{ tenantId: 1, eventAt: 1 }
```

min/max là các **document cùng cấu trúc khóa** và so sánh theo thứ tự từ trái sang phải. Không thể tự tính min/max của compound key như một số nguyên đơn giản.

Một phạm vi có thể là:

```javascript
{
  min: { tenantId: "T01", eventAt: MinKey() },
  max: { tenantId: "T02", eventAt: MinKey() }
}
```

Đây là **ví dụ logic về biên khóa**, không khẳng định cluster thực tế đang có range chính xác như vậy.

### 3.4. Đơn vị logic khác dung lượng đĩa vật lý

Khi một range được chuyển:

- Quyền sở hữu logic chuyển sang shard đích.
- Bản sao dữ liệu ở shard nguồn có thể cần thời gian để được dọn dẹp.
- Dung lượng đĩa quan sát được có thể không giảm tức thời do **range deletion, storage reuse và cơ chế file của storage engine**.

Do đó, sau khi range chuyển thành công, đừng vội kết luận thất bại chỉ vì kích thước file trên shard nguồn chưa giảm.

## 4. Balancer là gì và không phải là gì?

**Balancer** là bộ phận của MongoDB sharded cluster hỗ trợ duy trì phân bố các khoảng dữ liệu theo chính sách cân bằng và zone. Nó đánh giá metadata/kích thước, xác định những lần chuyển phù hợp và tiến hành các hoạt động migration cần thiết.

### 4.1. Mục tiêu chính

- Tránh để một shard nắm giữ lượng dữ liệu chênh lệch quá lớn so với các shard khác **khi có thể cân bằng**.
- Phân bố dữ liệu mới khi cluster được bổ sung shard hoặc tập dữ liệu tăng trưởng.
- Tôn trọng các **zone constraints** được định nghĩa cho khoảng shard key.
- Giúp quá trình mở rộng dung lượng của cluster có thể diễn ra **từng bước**.

### 4.2. Những điều balancer không tự bảo đảm

Balancer **không** có nghĩa:

- Mỗi shard luôn có chính xác 1/N số document.
- Mọi shard luôn có dung lượng bằng nhau từng byte.
- Mỗi shard xử lý lượng CPU và query bằng nhau.
- Có thể tách mọi range quá lớn trong mọi trường hợp.
- Có thể chuyển một range bất kỳ qua shard nằm ngoài zone cho phép.
- Dung lượng đĩa nguồn giảm tức thì sau migration.
- Không có tác động tới network, disk I/O, latency.

### 4.3. Khi nào dữ liệu vẫn lệch dù balancer đang bật?

Một số ví dụ:

1. Dữ liệu mới tập trung vào **một miền shard key** chưa thể chia thành các range có ích.
2. Shard key có **giá trị quá phổ biến**, không thể tách hiệu quả giữa các shard.
3. **Zone** giới hạn nơi dữ liệu được phép cư trú.
4. Một range quá lớn hoặc không thể tách tốt; có thể xuất hiện trạng thái **jumbo**.
5. Cluster đang có tác vụ migration khác hoặc balancer đang chờ điều kiện hoạt động.
6. Kích thước lệch nhưng chưa vượt ngưỡng/điều kiện khởi động migration.
7. Có lỗi kết nối, replica set, metadata, thiếu tài nguyên hoặc migration bị từ chối.

Để chẩn đoán, phải kết hợp **balancer state, data distribution, metadata và log**, chứ không chỉ nhìn một trường Boolean.

## 5. Migration diễn ra qua những bước nào?

Khi MongoDB quyết định chuyển một range từ **donor shard** (nguồn) sang **recipient shard** (đích), mô hình khái quát:

```text
                        sharded cluster

    Donor shard (A)                         Recipient shard (B)
   +----------------+                      +----------------+
   | Dữ liệu range R| ------ copy ------>  | Bản sao R      |
   | Đang sở hữu R  |                      | Đang nhận R    |
   +----------------+                      +----------------+
            |                                      |
            |  Các thay đổi đồng thời được xử lý   |
            |  theo protocol migration            |
            |                                      |
            +------------+-------------------------+
                         |
               Đồng bộ/catch-up
                         |
              Chuyển quyền sở hữu metadata
                         |
              R thuộc shard B về logic
                         |
            Donor dọn dữ liệu orphan
            theo cơ chế range deletion
```

### 5.1. Giai đoạn chuẩn bị

Balancer hoặc lệnh quản trị xác định:

- Namespace của collection cần chuyển.
- Range/chunk cụ thể theo shard key.
- Donor và recipient.
- Điều kiện topology, zone và khả năng tiếp nhận.

Đây không phải thao tác “copy thư mục database từ máy A sang B”; quá trình phải phối hợp với metadata và giao thức sharding.

### 5.2. Giai đoạn sao chép

Recipient tiếp nhận dữ liệu của range. Trong lúc ứng dụng vẫn hoạt động, dữ liệu nguồn có thể thay đổi; MongoDB phải xử lý các thay đổi liên quan để đích đủ điều kiện nhận quyền sở hữu.

**Không suy rằng thời gian migration chỉ bằng thời gian copy file**. Nó còn chịu tác động của workload ghi, index, dung lượng, network và đồng bộ.

### 5.3. Catch-up và critical section

Gần lúc chuyển quyền sở hữu, cần giai đoạn phối hợp giữa các shard và metadata để tránh việc hai bên cùng tin rằng mình sở hữu range theo cách gây sai tính nhất quán.

Trong những giai đoạn ngắn, một số thao tác trên range có thể bị chờ/gián đoạn để hệ thống bảo đảm chuyển quyền sở hữu đúng. Chi tiết thực thi và thời gian phụ thuộc MongoDB version và trạng thái cluster.

### 5.4. Metadata commit

Config server/cluster metadata được cập nhật để **recipient trở thành shard sở hữu range**. Các mongos router cần biết metadata mới để định tuyến đúng; cơ chế refresh metadata giúp xử lý trạng thái router cũ.

Không chỉnh metadata bằng cách sửa thủ công document trong `config.chunks` hoặc `config.collections`. Làm vậy có thể khiến topology không nhất quán và dữ liệu không thể truy cập đúng.

### 5.5. Dọn orphan sau chuyển

Sau khi quyền sở hữu đã chuyển, donor có thể còn bản sao dữ liệu của range trước khi hệ thống hoàn thành dọn dẹp. Những bản sao không còn thuộc quyền sở hữu logic của shard thường được gọi là **orphaned documents**.

Điểm cần nhớ:

- Orphan không đồng nghĩa document nghiệp vụ đã bị nhân đôi trên kết quả truy vấn qua mongos.
- Kích thước physical storage của donor có thể chưa giảm.
- Dọn orphan và thu hồi dung lượng hệ điều hành không phải một bước tức thời.
- Cần xem trạng thái range deletion/metrics thay vì tự xóa document “nghi là orphan”.

### 5.6. Migration có làm ứng dụng phải đổi endpoint?

Thông thường ứng dụng vẫn kết nối vào **mongos** qua URI của sharded cluster. MongoDB cập nhật metadata và định tuyến tới shard mới. Ứng dụng **không cần** lưu “document O01 đang ở shard A” trong business record rồi sửa nó sau migration.

Đó là lợi ích quan trọng của sharding theo metadata, nhưng các thao tác có thể thấy latency thay đổi tạm thời khi migration hoặc refresh.

## 6. Tạo môi trường thực hành đúng phạm vi

Bài học có lệnh **đọc trạng thái** và lệnh **thay đổi dữ liệu/phân bố**. Chỉ dùng nhóm lệnh thay đổi trên **sharded cluster lab** đã được chuẩn bị, không dùng trên production khi chưa có kế hoạch.

### 6.1. Điều kiện lab

Một môi trường phù hợp có:

- **Config server replica set**.
- Ít nhất **hai shard** (thông thường là replica set riêng).
- Một hoặc nhiều `mongos`.
- Quyền tạo database/collection, shard collection và quản trị balancer khi cần.
- Hostname/port đáng tin cậy và cấu hình xác thực an toàn.

**Không thể tạo bài lab di chuyển range chỉ bằng một standalone `mongod`.** Nếu chỉ có MongoDB standalone trên máy học, phần còn lại có thể được học dưới dạng mô phỏng và câu lệnh minh họa, nhưng không chạy thật `sh.moveChunk()`.

### 6.2. Kết nối vào `mongos`

Ví dụ URI giả định:

```bash
mongosh "mongodb://localhost:27017"
```

Port 27017 ở đây chỉ đúng nếu mongos của lab đang lắng nghe trên port đó. Trong cluster có xác thực, URI cần credential và TLS thích hợp; không đưa mật khẩu vào ví dụ hoặc log.

Kiểm tra node hiện tại là mongos:

```javascript
db.adminCommand({ hello: 1 });
```

Khi kết nối tới mongos, phản hồi thường có trường:

```javascript
{ msg: "isdbgrid" }
```

Đây là **dấu hiệu vai trò router**, không phải toàn bộ response. Các helper `sh.*` chủ yếu dùng trong ngữ cảnh mongos hoặc command router được hỗ trợ.

### 6.3. Quan sát danh sách shard thật trước khi viết lệnh

```javascript
db.adminCommand({ listShards: 1 });
```

Kết quả có thể chứa các shard IDs như `shardA`, `shardB`. **Chỉ sử dụng tên shard thực tế** từ cluster của bạn. Trong bài, tên shardA/shardB/shardC là ký hiệu minh họa.

Nếu chỉ có một shard, đừng thử chuyển range tới `shardB` không tồn tại.

## 7. Bộ dữ liệu mẫu và shard key

Ta dùng database `sharding_lab265` và collection `events265`:

```javascript
const labDb = db.getSiblingDB("sharding_lab265");
const events = labDb.events265;
```

### 7.1. Chỉ chạy trên collection mới/rỗng

Ví dụ sau chủ động dùng tên collection tách biệt và kiểm tra dữ liệu:

```javascript
if (events.countDocuments({}) !== 0) {
  throw new Error(
    "events265 da co du lieu; hay dung lab/collection moi"
  );
}
```

**Không chạy `drop()` trên collection có dữ liệu thật** chỉ để lặp lại ví dụ. Nếu đã dùng collection cho bài trước, chọn database/collection lab mới.

### 7.2. Tạo index shard key

Chọn khóa:

```javascript
{ tenantId: 1, eventAt: 1 }
```

Tạo index phù hợp:

```javascript
events.createIndex({ tenantId: 1, eventAt: 1 });
```

Đây là khóa **ranged** theo tenant rồi thời gian. Nó giúp giải thích các range liên tiếp, nhưng **không bảo đảm phân bố ghi đều**, đặc biệt nếu phần lớn sự kiện thuộc một tenant nóng và luôn có `eventAt` tăng.

### 7.3. Shard collection

Kết nối tới mongos và dùng helper:

```javascript
sh.shardCollection(
  "sharding_lab265.events265",
  { tenantId: 1, eventAt: 1 }
);
```

Tùy phiên bản/thiết lập MongoDB, việc bật sharding ở database và yêu cầu chuẩn bị collection có khác biệt. Cần dùng API thích hợp của deployment. Không chạy lại `shardCollection` nếu namespace đã shard.

### 7.4. Ghi dữ liệu nhỏ để quan sát

```javascript
const rows = [];
const tenants = ["T01", "T02", "T03", "T04"];

for (let i = 0; i < 800; i++) {
  const tenantId = tenants[i % tenants.length];
  rows.push({
    _id: "evt-" + String(i).padStart(5, "0"),
    tenantId,
    eventAt: new Date(Date.UTC(2026, 10, 1 + (i % 10), i % 24)),
    type: i % 3 === 0 ? "VIEW" : "CLICK",
    payload: { source: "lab", sequence: i }
  });
}

events.insertMany(rows);
```

Bộ dữ liệu **chỉ có 800 document nhỏ**. Nó phù hợp để học cú pháp, **không đủ để bảo đảm MongoDB tự tạo nhiều range hoặc phát sinh migration**. Nếu `sh.status()` cho thấy tất cả nằm trên một shard, không kết luận balancer bị hỏng. Việc thử chuyển thủ công còn tùy range hiện có.

## 8. Xem bức tranh tổng quan bằng `sh.status()`

### 8.1. Lệnh

Trong mongosh kết nối mongos:

```javascript
sh.status();
```

Tùy version, có thể dùng:

```javascript
sh.status(true);
```

để nhận thêm thông tin chi tiết nếu helper hỗ trợ. Đầu ra có thể gồm shard list, balancer state, databases, các sharded collections, shard key, phân bố range và zone.

### 8.2. Cách đọc

Hãy tìm những thành phần như:

```text
shards
  shardA
  shardB

balancer
  enabled / running / ...

databases
  sharding_lab265
    events265
      shard key: { tenantId: 1, eventAt: 1 }
      ranges by shard: ...
```

Các nhãn trên chỉ là **sơ đồ**, không phải bản sao chính xác output của mọi MongoDB version.

### 8.3. Chú ý đơn vị trong output

Nếu công cụ báo:

```text
Shard A: 7 chunks
Shard B: 3 chunks
```

thì ta mới biết **số đơn vị range/chunk**, chưa biết kích thước dữ liệu hoặc lưu lượng. Có thể:

```text
Shard A: 7 ranges, tổng 250 MB
Shard B: 3 ranges, tổng 300 MB
```

Trong MongoDB hiện đại, điều đó có thể **không phải phân bố tệ** theo tiêu chí dữ liệu.

### 8.4. So sánh hai lần đo

Nếu kiểm tra balancer:

```javascript
sh.status();
// Sau một khoảng thời gian quan sát và có thay đổi dữ liệu:
sh.status();
```

Hãy ghi lại **thời điểm**, **số range/dung lượng từng shard** và **trạng thái balancer**. Việc thấy một kết quả không đổi trong thời gian ngắn chưa đủ kết luận nó đứng yên bất thường.

## 9. Kiểm tra balancer có bật và đang hoạt động không

### 9.1. `sh.getBalancerState()`

```javascript
sh.getBalancerState();
```

Helper này dùng để hỏi **trạng thái bật/tắt** của balancer theo ngữ cảnh được hỗ trợ. Nó **không tự trả lời** có migration đang diễn ra, có cân bằng đạt yêu cầu hay không.

Một balancer có thể được bật nhưng:

- Không có chênh lệch dữ liệu cần di chuyển.
- Đang ngoài cửa sổ cho phép cân bằng.
- Đang chờ điều kiện hoặc tác vụ liên quan.
- Bị giới hạn bởi zone hoặc một range không thể chuyển.

Do đó, **`true` không có nghĩa đang di chuyển dữ liệu từng giây**.

### 9.2. `sh.isBalancerRunning()`

Trong môi trường/phiên bản hỗ trợ:

```javascript
sh.isBalancerRunning();
```

Helper này cung cấp thêm thông tin về hoạt động balancer. Ý nghĩa chi tiết và định dạng có thể khác theo version, và cũng **không thay thế** các số đo phân bố dữ liệu hoặc migration history.

### 9.3. Kết hợp nhiều quan sát

Một bảng tư duy:

| Balancer bật? | Có dấu hiệu đang chạy? | Phân bố dữ liệu | Diễn giải ban đầu |
|---|---|---|---|
| Có | Không | Đã phù hợp chính sách | Có thể không có việc cần làm |
| Có | Có | Đang lệch | Có thể đang từng bước cân bằng |
| Có | Không | Đang lệch | Kiểm tra ngưỡng, zone, cửa sổ, lỗi |
| Không | Không | Đang lệch | Không có auto balancing nếu bị tắt |
| Có | Có | Vẫn có hot shard | Balancer có thể cân bằng byte, không cân bằng tải truy vấn |

Không xem các cột trên như bộ quy tắc quyết định tuyệt đối; phải xác nhận bằng dữ liệu thật.

### 9.4. Tránh thay đổi cấu hình khi chưa biết lý do

Trong nhiều cluster, balancer đang bật mặc định vì được xem là cơ chế vận hành bình thường. **Không tắt balancer chỉ vì một lần migration làm query chậm**. Hãy xác định xem thay đổi tải có thực sự do migration, do shard key hay do yếu tố khác.

## 10. Quan sát phân bố document và dung lượng theo shard

### 10.1. `getShardDistribution()`

Với collection đã shard, trong mongosh:

```javascript
db.getSiblingDB("sharding_lab265")
  .events265
  .getShardDistribution();
```

Helper có thể in các chỉ số phân bố collection theo shard, tùy MongoDB version và metadata hỗ trợ, như kích thước và số document ước lượng/quan sát được.

**Đây là công cụ quan sát**, không dùng để quyết định xóa dữ liệu “thừa” theo cảm tính. Kết quả có thể có số ước lượng và bị ảnh hưởng bởi orphan hoặc thời điểm thu thập; đọc phần giải thích của output tương ứng version.

### 10.2. `sh.getShardedDataDistribution()`

Trên các phiên bản MongoDB hỗ trợ, có thể dùng:

```javascript
sh.getShardedDataDistribution();
```

Helper này cho biết phân bố dữ liệu sharded theo namespace và shard, có thể gồm **owned data** và **orphaned data** cùng những thống kê liên quan.

Một output mẫu có thể trông như sau (**số liệu minh họa**):

```text
Namespace: sharding_lab265.events265

shardA:
  owned data: 400 MB
  orphaned data: 20 MB

shardB:
  owned data: 410 MB
  orphaned data: 0 MB
```

Điểm rút ra:

- Số liệu **owned** phản ánh dữ liệu shard sở hữu theo thông tin công cụ.
- **Orphaned** không nên tính như dữ liệu nghiệp vụ đang được shard đó sở hữu hợp lệ.
- Hai shard có owned data gần bằng nhau dù physical size có thể khác do bản sao còn chờ cleanup.

**Không khẳng định mọi version đều có helper này hoặc cùng tên trường output.** Nếu unavailable, dùng `sh.status()`, các metric khác và công cụ quản trị được deployment hỗ trợ.

### 10.3. Biểu diễn có cấu trúc khi cần lưu snapshot

Thay vì chụp ảnh màn hình:

```javascript
const observation = {
  observedAt: new Date(),
  balancerEnabled: sh.getBalancerState(),
  // Ghi riêng những metric mà version hiện tại thực sự hỗ trợ.
};

printjson(observation);
```

Có thể tạo một script giám sát dùng các command/metrics được hỗ trợ để xuất JSON thời gian thực. Trong production, nên dùng monitoring system với lịch sử, cảnh báo và phân quyền thay vì chạy lệnh thủ công không lưu dấu.

## 11. `balancerCollectionStatus`: collection đã cân bằng chưa?

Ở MongoDB version hỗ trợ, helper:

```javascript
sh.balancerCollectionStatus(
  "sharding_lab265.events265"
);
```

có thể cung cấp tình trạng collection có **phù hợp chính sách cân bằng** hay không, cùng thông tin chỉ dẫn về nguyên nhân không phù hợp.

### 11.1. Đừng diễn giải “compliant” thành “không còn vấn đề hiệu năng”

Một collection được đánh giá phù hợp theo chính sách balancer vẫn có thể:

- Có một tenant cực nóng.
- Có query scatter-gather tốn CPU trên nhiều shard.
- Có index thiếu.
- Có shard hardware yếu hơn.
- Có orphan đang chờ dọn.
- Có lag replication.

Balancer compliance liên quan **phân bố dữ liệu theo chính sách**, không phải chứng chỉ hiệu năng tổng thể.

### 11.2. Nếu helper không có

Không tự giả định:

```javascript
sh.balancerCollectionStatus(...);
```

luôn hoạt động trên bản MongoDB bất kỳ. Nếu helper không được cung cấp, quan sát bằng `sh.status()`, phân bố dữ liệu và các lệnh/metrics mà phiên bản đang dùng hỗ trợ.

## 12. Theo dõi lịch sử migration

### 12.1. Vì sao cần lịch sử?

Một ảnh chụp `sh.status()` chỉ nói **hiện tại**. Để biết:

- Range nào đã chuyển?
- Chuyển từ shard nào sang shard nào?
- Migration bắt đầu/kết thúc khi nào?
- Có lỗi, retry hoặc thời gian kéo dài bất thường?

ta cần lịch sử và log.

### 12.2. `config.changelog`

Trong một số phiên bản/cấu hình MongoDB, collection `config.changelog` lưu sự kiện quản trị sharding, gồm những event liên quan balancer/migration.

Lệnh **chỉ đọc** để quan sát:

```javascript
const cfg = db.getSiblingDB("config");

cfg.changelog.find({
  what: /moveChunk|moveRange|balancer/i
}).sort({ time: -1 }).limit(20);
```

Chú ý:

- **Tên event và schema log có thể thay đổi** giữa các phiên bản.
- Không phải mọi migration sẽ hiện đúng bộ tên `what` của ví dụ.
- Không xem `config.changelog` như API ổn định để xây phần mềm business lâu dài.
- **Không sửa, xóa hoặc chèn thủ công** vào collection metadata/config.

### 12.3. `config.actionlog` và server logs

Một số deployment còn có thông tin về balancer round ở `config.actionlog` hoặc log của các thành phần liên quan:

```javascript
cfg.actionlog.find().sort({ time: -1 }).limit(20);
```

Không phải lúc nào collection này cũng tồn tại hoặc được duy trì theo cùng schema. Khi điều tra sâu, **server logs** của mongos, config servers và các shard thường quan trọng hơn việc cố đoán một field metadata không ổn định.

### 12.4. Tương quan lịch sử với metric hạ tầng

Nếu thấy latency tăng:

```text
10:00  Balancer bắt đầu migration
10:03  Network throughput tăng
10:05  Shard A disk I/O tăng
10:06  Application p99 latency tăng
10:12  Migration hoàn tất
10:14  Latency giảm
```

Đó là **mối tương quan cần kiểm chứng**, chưa phải bằng chứng tuyệt đối migration là nguyên nhân. Cũng có thể workload tăng cùng thời điểm. Nên kết hợp metrics đọc/ghi, slow query, index, replication lag và trạng thái migration.

## 13. Di chuyển một range thủ công bằng `sh.moveChunk()`

### 13.1. Khi nào mới xem xét?

**Thông thường hãy để balancer quản lý việc cân bằng.** Di chuyển thủ công có thể hữu ích trong:

- Lab để hiểu phạm vi quyền sở hữu.
- Một kế hoạch vận hành đã kiểm tra rõ shard đích, zone và dung lượng.
- Tình huống khắc phục bất cân bằng cụ thể theo hướng dẫn của MongoDB version.

Không nên xem `moveChunk` là API business để định tuyến từng đơn hàng hoặc chọn shard cho mỗi insert.

### 13.2. Cú pháp helper

Trong mongosh của các phiên bản hỗ trợ:

```javascript
sh.moveChunk(
  "database.collection",
  { shardKeyField: someValue },
  "destinationShardName"
);
```

Ví dụ **chỉ dành cho lab**, sau khi đã xác nhận collection có range trên shard nguồn và shard đích phù hợp:

```javascript
sh.moveChunk(
  "sharding_lab265.events265",
  {
    tenantId: "T02",
    eventAt: ISODate("2026-11-02T00:00:00Z")
  },
  "shardB"
);
```

Ý nghĩa:

- Namespace chỉ định collection đã shard.
- Object thứ hai là một **điểm trong không gian shard key** để xác định range chứa điểm đó, không phải document hoàn chỉnh.
- `"shardB"` là **ID shard đích**, phải khớp danh sách thật của cluster.
- Lệnh yêu cầu MongoDB **di chuyển range/chunk chứa shard key được cung cấp**, không di chuyển riêng document mang key đó.

### 13.3. Những điều kiện phải kiểm tra trước khi chạy

1. Đang kết nối đến **mongos**, không phải direct một replica set shard theo nhầm ngữ cảnh.
2. Namespace thực sự đã shard theo khóa mong đợi.
3. Shard đích tồn tại và hoạt động bình thường.
4. Range được chọn hiện thuộc shard khác với đích.
5. Zone policy **cho phép** range nằm trên đích.
6. Có đủ disk/network/replication health để nhận dữ liệu.
7. Đã dự kiến tác động tới latency và xử lý lỗi.

Nếu collection chỉ có một range và ít dữ liệu, di chuyển range này có thể khiến **toàn bộ collection nhỏ** chuyển shard; nó **không tạo cân bằng 50/50**. Không dùng một lệnh `moveChunk` để thay cho thiết kế shard key/range.

### 13.4. Trạng thái sau lệnh

Sau khi một migration hoàn tất theo kết quả command:

```javascript
sh.status();

db.getSiblingDB("sharding_lab265")
  .events265
  .getShardDistribution();
```

Kết quả có thể cho thấy quyền sở hữu range chuyển shard. Tuy nhiên, lượng orphan/physical storage trên donor **chưa chắc đã được dọn xong**. Tiếp tục quan sát nếu cần.

### 13.5. Không thực hiện hàng loạt `moveChunk` tùy ý

Một vòng lặp tự gọi `moveChunk` cho hàng trăm range có thể:

- Gây bão network/disk.
- Tranh chấp với balancer.
- Tăng latency.
- Vô tình di chuyển dữ liệu trái mục tiêu/zone.
- Khó phục hồi nếu automation chọn sai phạm vi.

Nếu có nhu cầu rebalance quy mô lớn, dùng **chính sách balancer và quy trình của deployment**, chỉ triển khai manual movement trong runbook có review.

## 14. Di chuyển range cụ thể và vấn đề phiên bản

Trong MongoDB, tên **chunk** và **range** cùng xuất hiện trong tài liệu/vận hành. Một số phiên bản có command/helper điều khiển **range migration** với min/max rõ ràng; một số giao diện được thay đổi, bổ sung hoặc hạn chế theo version.

Không tự áp một câu lệnh `moveRange` suy đoán từ tài liệu của phiên bản khác rồi chạy trên production. Nếu cần điều khiển ranh giới min/max:

1. Xác định chính xác **MongoDB server và mongosh version**.
2. Kiểm tra command/helper được phiên bản đó hỗ trợ.
3. Xác định min/max đầy đủ theo **shard key index và BSON type**.
4. Kiểm tra zone constraints.
5. Thử trên một cluster lab có cấu trúc giống production.

Trong phạm vi học thao tác cơ bản, `sh.moveChunk()` với một điểm shard key là ví dụ dễ hiểu; **không xem nó là cách thay thế mọi chức năng balancer hiện đại**.

## 15. Bật/tắt balancer: cần hiểu tác động trước khi làm

### 15.1. Điều khiển toàn cluster

Trong mongosh của cluster hỗ trợ:

```javascript
sh.stopBalancer();
```

và:

```javascript
sh.startBalancer();
```

Đây là thao tác **thay đổi vận hành**, không phải lệnh chỉ đọc. Không chạy trên production khi chưa được phê duyệt.

### 15.2. Không đồng nhất “dừng balancer” với “dừng mọi ghi”

Khi balancer bị dừng:

- Ứng dụng thường vẫn có thể đọc/ghi trên các shard đang sở hữu dữ liệu.
- Những thay đổi mới có thể khiến phân bố dữ liệu ngày càng lệch.
- Quy trình di chuyển range tự động bị ảnh hưởng theo trạng thái điều khiển.
- Một migration đang chạy có thể cần thời gian xử lý trước khi trạng thái dừng ổn định.

**Dừng balancer không làm cluster thành standalone database**, và cũng không phải nút “đóng băng toàn bộ dữ liệu”.

### 15.3. Bật lại sau cửa sổ bảo trì

Nếu đã tắt theo runbook được duyệt, cần bật lại và xác minh:

```javascript
sh.startBalancer();
sh.getBalancerState();
sh.isBalancerRunning();
sh.status();
```

Chỉ một phản hồi lệnh thành công không thay thế việc theo dõi cluster đã tiến tới phân bố mong muốn.

### 15.4. Cửa sổ cân bằng và hệ thống có tải theo giờ

Một số deployment có thể cấu hình **balancer window** để hạn chế thời gian cân bằng. Việc dùng cửa sổ phải dựa vào hành vi thực tế:

- Nếu dữ liệu mới tăng nhanh suốt ngày, cửa sổ quá ngắn khiến backlog migration lớn.
- Nếu chỉ cân bằng trong giờ thấp điểm, có thể giảm tác động trực tiếp đến workload ban ngày.
- Cần kiểm tra timezone của hệ thống/quy tắc window ở phiên bản hỗ trợ.

Không tùy ý thay đổi `config.settings` hoặc metadata bằng CRUD thủ công để “lập lịch” nếu deployment đã có API/quy trình được hỗ trợ.

## 16. Tắt/bật balancing cho một collection

MongoDB cung cấp helper ở những phiên bản hỗ trợ:

```javascript
sh.disableBalancing(
  "sharding_lab265.events265"
);
```

và:

```javascript
sh.enableBalancing(
  "sharding_lab265.events265"
);
```

### 16.1. Phạm vi khác nhau

| Thao tác | Phạm vi |
|---|---|
| `sh.stopBalancer()` | Hoạt động balancing tự động ở cấp cluster theo cơ chế điều khiển |
| `sh.startBalancer()` | Cho phép balancing tự động ở cấp cluster |
| `sh.disableBalancing(ns)` | Ngừng balancing tự động cho namespace được chỉ định |
| `sh.enableBalancing(ns)` | Bật lại balancing tự động cho namespace được chỉ định |

**Không nên coi tắt balancing của collection là khóa mọi thao tác quản trị khác**. Nó không biến dữ liệu thành bất biến và không nhất thiết chặn mọi thao tác di chuyển thủ công trong mọi phiên bản.

### 16.2. Lý do có thể dùng tạm thời

- Đang thực hiện migration/backup có runbook rõ.
- Muốn kiểm soát biến động của collection cụ thể trong một thời gian ngắn.
- Cần phân tích nguyên nhân hiệu năng và cô lập một yếu tố.

Sau đó cần **khôi phục trạng thái mong muốn** và theo dõi. Không để một collection tăng trưởng nhanh bị tắt balancing vô thời hạn chỉ vì một thử nghiệm chưa được kết thúc.

## 17. Zone sharding: không phải range nào cũng có thể tới mọi shard

### 17.1. Zone định nghĩa chính sách vị trí

**Zone** là cách liên kết một hoặc nhiều shard với một nhóm placement và gán các khoảng shard key cho zone đó.

Ví dụ nghiệp vụ:

- Dữ liệu vùng APAC phải ở nhóm shard APAC.
- Dữ liệu vùng EU phải ở nhóm shard EU.
- Một số tenant cần nằm trên nhóm hạ tầng riêng do chính sách.

Sơ đồ:

```text
Range thuộc zone APAC
           |
           +-- Shard A (zone APAC)  Có thể nhận
           |
           +-- Shard B (zone APAC)  Có thể nhận
           |
           +-- Shard C (zone EU)    Không phù hợp policy
```

Một cluster có zone policy có thể không cân bằng đều giữa **tất cả shard** vì dữ liệu phải tuân thủ phạm vi placement.

### 17.2. Ví dụ minh họa cấu hình zone

Giả sử một collection **khác** có shard key:

```javascript
{ region: 1, createdAt: 1 }
```

Các lệnh quản trị zone (chỉ mang tính minh họa, **không chạy trực tiếp nếu collection và shard chưa tồn tại**):

```javascript
sh.addShardToZone("shardA", "APAC");

sh.updateZoneKeyRange(
  "geo_lab.events",
  { region: "APAC", createdAt: MinKey() },
  { region: "APAC", createdAt: MaxKey() },
  "APAC"
);
```

Lưu ý: với shard key có trường region rồi createdAt, một cặp min/max như trên dùng để minh họa khoảng trong **cùng region**; việc bao phủ tất cả khóa của region và bảo đảm không chồng chéo zone cần được thiết kế cẩn thận theo thứ tự BSON của shard key. Khi triển khai thật, phải tính đúng ranh giới và kiểm tra cấu hình zone.

### 17.3. Zone có thể giải thích sự chênh lệch

Giả sử:

```text
Shard A + B: zone APAC, tổng 5 TB
Shard C:     zone EU,   tổng 1 TB
```

Nếu policy không cho dữ liệu APAC chuyển sang C, việc C còn nhiều dung lượng **không đồng nghĩa balancer bị lỗi**. Nó đang tuân thủ placement constraints.

### 17.4. Zone không tự giải quyết hot tenant

Nếu một tenant ghi 90% tổng traffic trong zone APAC và shard key khiến dữ liệu của tenant không phân tán tốt, balancer có thể gặp giới hạn dù APAC có nhiều shard. Giải pháp có thể cần **đổi thiết kế shard key, pattern truy cập hoặc kiến trúc dữ liệu**, không chỉ thêm zone tag.

## 18. Jumbo range: vì sao có phạm vi khó di chuyển?

### 18.1. Khái niệm

Một range có thể trở nên **quá lớn hoặc khó tách**, thường được mô tả bằng thuật ngữ **jumbo** trong bối cảnh sharding. Nguyên nhân có thể liên quan đến phân bố shard key, dữ liệu có nhiều document cùng giá trị shard key hoặc khả năng chọn điểm chia.

Ví dụ:

```text
Collection shard theo { country: 1 }

95% document có country = "VN"
5% thuộc các country khác
```

Nếu một số lượng cực lớn document chia sẻ đúng một giá trị shard key `"VN"`, cluster không thể chia chúng thành nhiều range phân biệt **chỉ bằng khóa `country`**. Tập dữ liệu đó có thể tạo một phần quá lớn không dễ cân bằng.

### 18.2. Hậu quả

- Dữ liệu vẫn lệch dù balancer bật.
- Migration có thể bị trì hoãn hoặc báo lỗi.
- Có thể thấy cảnh báo liên quan range/chunk size hoặc jumbo trong log/metadata.
- Shard chịu lượng lớn dữ liệu hoặc request không được giải phóng tải như kỳ vọng.

### 18.3. Không “chữa” bằng ép move liên tục

Một số phiên bản MongoDB có các tùy chọn/command đặc biệt liên quan di chuyển jumbo hoặc xử lý range lớn. Dùng sai có thể gây tải nặng, thời gian di chuyển dài và rủi ro vận hành.

Không chạy force movement chỉ vì `sh.status()` cho thấy một shard lớn hơn. Trước tiên xác định:

1. Shard key có phân biệt đủ giá trị không?
2. Phạm vi quá lớn hay chỉ hot về traffic?
3. Có thể thay đổi mô hình shard key phù hợp?
4. Có zone constraint ngăn di chuyển?
5. Có đủ dung lượng/IO và maintenance window?

### 18.4. Shard key “đẹp trên giấy” có thể không đủ tốt

Khóa `{ country: 1 }` có ít giá trị phân biệt; khóa `{ tenantId: 1 }` cũng có thể bị lệch nếu một tenant chiếm đa số dữ liệu. Khóa `{ createdAt: 1 }` đơn điệu có thể tập trung ghi mới vào một phần giá trị.

Một khóa compound hoặc hashed phù hợp có thể cải thiện phân bố, nhưng **đánh đổi** khả năng targeted query, range query, co-location và chính sách zone. Phải thiết kế shard key dựa trên **cả tăng trưởng dữ liệu lẫn mẫu truy cập**, không chọn chỉ vì nó chia được nhiều chunk.

## 19. Balancer cân bằng dữ liệu, còn truy vấn có thể vẫn nóng

### 19.1. Dung lượng bằng nhau nhưng QPS khác nhau

Giả sử:

```text
Shard A: owned data 500 GB, 15.000 query/s
Shard B: owned data 490 GB,    800 query/s
Shard C: owned data 510 GB,    750 query/s
```

Balancer có thể xem data distribution khá cân đối, nhưng Shard A vẫn là điểm nghẽn.

Nguyên nhân có thể:

- Một tenant nóng nằm chủ yếu trên shard A.
- Query luôn nhắm tới một dải shard key.
- Index trên shard A bị thiếu/khác biệt.
- Tài nguyên phần cứng của A yếu hơn.
- Query scatter-gather hoặc aggregation gửi tải không đồng đều.
- Chunk placement phù hợp về byte nhưng không phù hợp về hoạt động.

### 19.2. Xem cả workload

Không chỉ xem `sh.status()`. Nên theo dõi:

- CPU mỗi shard/replica set.
- Disk IOPS, độ trễ read/write, dung lượng trống.
- Network throughput giữa shards.
- Số lượng operation, query latency (p95/p99).
- Replication lag và write concern wait.
- Slow queries và `explain()` của các mẫu truy vấn quan trọng.
- Dung lượng owned/orphaned per collection.
- Migration rate, failure rate và thời gian chạy.

### 19.3. Scatter-gather là vấn đề định tuyến, không đơn thuần phân bố byte

Ví dụ collection shard theo:

```javascript
{ tenantId: 1, eventAt: 1 }
```

Query có điều kiện `tenantId` và khoảng `eventAt` có cơ hội định tuyến tập trung hơn một query chỉ lọc `type: "CLICK"` không chứa shard key.

Nếu query thường xuyên không có shard key, mongos có thể phải gửi tới nhiều shard. Balancer chuyển range không tự khiến query scatter-gather trở thành targeted.

## 20. Khi thêm shard mới, dữ liệu có chuyển ngay không?

### 20.1. Thêm capacity không đồng nghĩa đã dùng capacity

Khi thêm `shardC` vào cluster đang có A/B:

```text
Trước:
  shardA: 600 GB
  shardB: 580 GB

Vừa thêm shardC:
  shardA: 600 GB
  shardB: 580 GB
  shardC:   0 GB
```

Điều này **bình thường ngay sau khi thêm shard**. Balancer cần đánh giá và di chuyển những phạm vi phù hợp theo điều kiện thực tế. Nó không lập tức sao chép 1/3 dữ liệu sang shard mới tại thời điểm command thêm shard trả thành công.

### 20.2. Theo dõi tiến độ

Ở các mốc quan sát:

```text
Thời điểm  | Owned A | Owned B | Owned C
----------+---------+---------+--------
T0        | 600 GB  | 580 GB  | 0 GB
T1        | 540 GB  | 530 GB  | 110 GB
T2        | 425 GB  | 420 GB  | 335 GB
T3        | 395 GB  | 390 GB  | 395 GB
```

Con số trên là **minh họa**, không dự đoán tốc độ thực tế. Tốc độ còn phụ thuộc dữ liệu, số range có thể di chuyển, zone, network, I/O và balancer.

### 20.3. Đừng vội phát hiện “lỗi” từ một snapshot

Nếu sau 30 giây shard mới vẫn rỗng, chưa đủ kết luận cân bằng không hoạt động. Hãy xác nhận:

- Balancer bật hay tắt.
- Collection đã shard hay còn unsharded.
- Có zone giới hạn shard mới không.
- Dữ liệu có nhiều range phù hợp không.
- Có lỗi migration trong log không.
- Có đủ dữ liệu để balancer thấy cần chuyển không.

## 21. Draining shard và di chuyển dữ liệu khỏi một shard

Một mục tiêu khác là **loại bỏ một shard**. Khi một shard được đưa vào quy trình remove/drain theo cơ chế MongoDB, cluster cần di chuyển dữ liệu nó đang sở hữu tới các shard còn lại trước khi có thể hoàn tất việc loại shard.

### 21.1. Draining khác balancing thông thường

Balancing thông thường nhằm điều chỉnh phân bố. **Draining** nhằm đưa lượng dữ liệu hợp lệ của shard sắp bị loại về nơi khác.

```text
Shard A: tiếp tục phục vụ
Shard B: tiếp tục phục vụ
Shard C: trạng thái draining
           |
           v
       Dữ liệu chuyển dần sang A/B
           |
           v
       Hoàn tất điều kiện remove shard
```

### 21.2. Không thể chỉ tắt máy shard rồi gọi là đã di chuyển xong

Nếu tắt shard trước khi dữ liệu được chuyển hợp lệ và metadata cập nhật, cluster có thể mất khả năng truy cập phần dữ liệu đang nằm ở shard đó.

Khi remove shard cần:

- Xác nhận cluster còn đủ capacity.
- Có đủ các shard đích phù hợp với zone.
- Theo dõi tiến độ draining và dữ liệu/chunk còn lại.
- Xử lý collection unsharded hoặc những cấu hình đặc biệt theo quy trình version.
- Chỉ loại hạ tầng sau khi lệnh quản trị báo hoàn tất và xác minh thực tế.

### 21.3. Không đồng nhất shrink cluster với backup/restore

Draining là thao tác di chuyển quyền sở hữu dữ liệu giữa shards; nó không thay thế backup. Trong suốt quá trình, một sai sót vận hành vẫn có thể gây gián đoạn. Duy trì kế hoạch khôi phục và change window phù hợp.

## 22. Ràng buộc đặc biệt của sharded collection

### 22.1. Collection chưa shard

Một collection không được sharded theo đúng nghĩa thường không có phân bố nhiều range như collection đã shard. Việc nó nằm trên một shard không chứng minh balancer hỏng.

MongoDB các phiên bản mới có cơ chế quản lý placement và **moveCollection** riêng cho unsharded collection; đó là vấn đề khác với việc di chuyển chunk/range của một **sharded collection**.

### 22.2. Hashed shard key

Nếu collection shard theo:

```javascript
{ tenantId: "hashed" }
```

range được phân bổ trong **không gian giá trị hash** của shard key. Mục tiêu thường là phân tán các giá trị khóa, không giữ các tenantId gần nhau theo thứ tự chữ cái.

Khi dùng manual move, không nên suy biên min/max bằng cách nhìn thứ tự String tenantId. Dùng các helper/metadata được hỗ trợ và hiểu cách định tuyến hashed key.

### 22.3. Compound hashed key

Ví dụ:

```javascript
{ region: 1, tenantId: "hashed" }
```

cho phép kết hợp một trường prefix có thể liên quan zone/range với một thành phần băm. Nhưng cấu hình hashed key, unique index, range splitting và targeted query có nhiều điều kiện theo version. Không sửa shard key trực tiếp trong production mà chưa đánh giá toàn bộ tác động.

### 22.4. Resharding khác chunk migration

**Chunk/range migration** chuyển dữ liệu giữa shards **trong khi giữ nguyên shard key** của collection.

**Resharding** thay đổi cách phân vùng theo **một shard key khác**. Đây là thao tác lớn hơn, có cơ chế và yêu cầu riêng.

```text
Migration:
  shard key giữ nguyên
  range R: shard A -> shard B

Resharding:
  shard key cũ { tenantId: 1 }
              ->
  shard key mới { tenantId: 1, eventAt: 1 }
  tổ chức lại phân bố theo khóa mới
```

Không dùng `sh.moveChunk()` để “chuyển shard key” hoặc sửa cấu trúc khóa của collection.

## 23. Theo dõi tác động lên người dùng và application

### 23.1. Những chỉ số cần đối chiếu

| Nhóm metric | Ví dụ | Mục đích |
|---|---|---|
| Dữ liệu | Owned bytes theo shard/namespace | Biết mức phân bố dung lượng |
| Ownership | Số range/chunk hoặc placement state | Biết quyền sở hữu đã đổi |
| Orphan | Orphaned bytes, range deletion backlog | Phân biệt di chuyển logic với dọn vật lý |
| Migration | Số lần/giây, duration, failure | Theo dõi tốc độ và lỗi |
| Storage | Disk used/free, write latency, IOPS | Phát hiện donor/recipient quá tải |
| Network | Throughput, latency giữa shard | Phát hiện copy/catch-up chậm |
| Query | p95/p99, scatter-gather, slow queries | Xem tác động thật tới ứng dụng |
| Replica set | Secondary lag, elections | Đánh giá sức khỏe data-bearing members |
| Balancer | Enabled/round/compliance | Biết cơ chế tự động đang làm gì |

### 23.2. Một biểu đồ duy nhất chưa đủ

Nếu biểu đồ dung lượng của shard A giảm, đó có thể là:

- Dữ liệu được chuyển đúng sang shard khác.
- TTL hoặc delete đang xóa document.
- Compression/storage metrics thay đổi.
- Collection đã được reshard hoặc ghi lại.

Nên đối chiếu lịch sử migration, owned bytes của shard đích, hoạt động application và các sự kiện vận hành.

### 23.3. Alert dựa vào xu hướng

Ví dụ những cảnh báo hữu ích:

- Owned data lệch quá mức trong nhiều chu kỳ **và** balancer không tiến triển.
- Disk free trên recipient dưới ngưỡng an toàn.
- Migration failure rate tăng.
- Orphan cleanup backlog tăng liên tục.
- Balancer bị tắt ngoài maintenance window.
- p99 write latency tăng trong lúc migration.
- Replication lag tăng vượt ngưỡng của hệ thống.

Không cấu hình “cứ thấy 1 range lệch là báo critical”. Cluster nhỏ có thể không cần cân bằng ngay, và số range không phản ánh size.

## 24. Quy trình phân tích khi balancer dường như không cân bằng

### Bước 1 — Xác minh kết nối và topology

```javascript
db.adminCommand({ hello: 1 });
db.adminCommand({ listShards: 1 });
```

Đảm bảo đang ở **mongos** và có ít nhất hai shard đích khả dụng. Kiểm tra shard replica sets có primary/secondary phù hợp và không có sự cố nghiêm trọng.

### Bước 2 — Kiểm tra collection đã shard

```javascript
sh.status();
```

Xác nhận namespace, shard key và số range/dữ liệu hiện có. **Một unsharded collection không tự phân tán nhiều shard theo chunk balancer.**

### Bước 3 — Kiểm tra balancer state

```javascript
sh.getBalancerState();
sh.isBalancerRunning();
```

Nếu balancer bị tắt, tìm nguyên nhân và runbook; không tự bật ngay trong một maintenance window do nhóm khác chủ trì.

### Bước 4 — Xem dữ liệu thực

```javascript
db.getSiblingDB("sharding_lab265")
  .events265
  .getShardDistribution();
```

Nếu có helper hỗ trợ:

```javascript
sh.getShardedDataDistribution();
```

Phân biệt owned data với orphan và số chunk.

### Bước 5 — Kiểm tra policy/zone

Xem range có được phép tới các shard khác không. Một shard còn trống nhưng thuộc zone không tương thích thì không phải đích hợp lệ.

### Bước 6 — Tìm dấu hiệu jumbo hoặc unsplittable range

Kiểm tra metadata/log phù hợp version. Đánh giá cardinality của shard key và sự tập trung dữ liệu. Nếu mọi document có cùng shard key, balancer không thể tự biến một giá trị đơn thành nhiều giá trị khác.

### Bước 7 — Xem lịch sử migration và lỗi

```javascript
db.getSiblingDB("config").changelog
  .find({ what: /moveChunk|moveRange|balancer/i })
  .sort({ time: -1 })
  .limit(20);
```

Đối chiếu với log mongos/config servers/shards và monitoring. Đừng chỉ tin một chuỗi event khi version đã thay đổi schema.

### Bước 8 — Đánh giá tải donor/recipient

Kiểm tra network/disk, replication lag, write concern, bầu cử và query latency. Nếu recipient không đủ tài nguyên, di chuyển thêm có thể làm tình hình xấu hơn.

### Bước 9 — Chọn biện pháp có ranh giới

Các lựa chọn có thể gồm:

- Để balancer tiếp tục khi tiến độ bình thường.
- Bổ sung capacity theo kế hoạch.
- Chỉnh zone placement khi policy cho phép.
- Xử lý shard key/khả năng tách range qua kiến trúc phù hợp.
- Lập maintenance window cho migration đặc biệt.
- Theo hướng dẫn của version, di chuyển thủ công một range lab hoặc range production đã được phê duyệt.

**Không chữa bằng sửa metadata trực tiếp.**

### Bước 10 — Xác minh sau thay đổi

Ghi lại:

- Owned bytes, orphaned bytes.
- Range/ownership.
- Trạng thái balancer.
- Migration success/failure.
- Disk free và replication lag.
- Application p95/p99 latency.

Đảm bảo ứng dụng phục vụ bình thường và trạng thái balancing đã được khôi phục đúng kế hoạch.

## 25. Những nhầm lẫn cần tránh

| Ngộ nhận | Thực tế |
|---|---|
| Balancer phân phối từng document tới shard ít tải nhất | Balancer làm việc theo **phạm vi shard key**, không chọn shard cho mỗi document tùy ý |
| Balancer bật thì luôn đang di chuyển dữ liệu | Có thể không có migration cần thực hiện |
| Có 10 chunk ở A và 5 ở B nghĩa A gấp đôi dung lượng | Chunk có kích thước khác nhau; cần xem dữ liệu |
| Di chuyển chunk giống copy folder dữ liệu | Cần sao chép, catch-up, metadata commit và cleanup |
| Sau migration donor phải giảm disk used ngay | Orphan cleanup và storage reuse có thể làm số vật lý giảm chậm |
| Orphan đồng nghĩa query thấy document trùng | Quyền sở hữu logic và routing giúp phân biệt |
| Một range chỉ chứa một document | Một range có thể chứa rất nhiều document |
| MoveChunk với key X chỉ chuyển document X | Chuyển **range chứa key X** |
| MoveChunk luôn làm dữ liệu cân bằng | Có thể chuyển cả range lớn và khiến lệch hướng khác |
| Cân bằng dung lượng nghĩa cân bằng CPU/QPS | Hot key, query pattern và hardware có thể vẫn lệch |
| Range có thể chuyển tới mọi shard | Zone/sharding constraints có thể giới hạn |
| Cứ thêm một shard là dữ liệu tự đều ngay | Balancing cần thời gian và đủ điều kiện |
| Tắt balancer nghĩa application ngừng ghi | Không; thao tác đọc/ghi bình thường vẫn theo quyền sở hữu |
| sh.status() có balancer enabled nghĩa đã cân bằng xong | Cần xem distribution/compliance và xu hướng |
| config.chunks là bảng quản trị có thể sửa bằng updateOne | Đây là metadata nội bộ; chỉnh trực tiếp nguy hiểm |
| MoveChunk là cách đổi shard key | Đổi shard key thuộc resharding, không phải migration thông thường |
| Số document bằng nhau là luôn tối ưu | Document size và traffic có thể khác rất nhiều |
| Shard mới rỗng là balancer hỏng | Có thể chưa cần chuyển hoặc bị zone/khóa hạn chế |
| Một số liệu snapshot đủ chẩn đoán sự cố | Cần so sánh theo thời gian, log và nhiều metrics |
| Có nhiều orphan nghĩa dữ liệu đã mất | Orphan là dữ liệu bản sao chờ dọn; cần quan sát đúng ngữ nghĩa |
| Để sửa lệch thì force move mọi jumbo range | Có rủi ro cao; cần phân tích nguyên nhân và runbook |

## 26. Bài tập thực hành

### Bài 1 — Vẽ một cluster và ownership

Giả sử collection `orders` shard theo `{ customerId: 1 }`, có ba shard:

```text
Shard A: [MinKey, "K")
Shard B: ["K", "T")
Shard C: ["T", MaxKey)
```

Trả lời:

1. Đơn hàng có `customerId: "M15"` thuộc shard nào theo sơ đồ?
2. Nếu range `["K","T")` chuyển từ B sang C, điều gì phải thay đổi trong metadata?
3. Shard B có thể còn bản sao vật lý trong một thời gian không?
4. Ứng dụng dùng mongos có cần đổi đường kết nối không?

### Bài 2 — Đếm chunk và so sánh dung lượng

Hai shard có:

```text
Shard A: 8 chunks, owned 420 MB
Shard B: 4 chunks, owned 430 MB
```

Vì sao không thể kết luận A chịu tải gấp đôi? Những metric nào cần thêm để đánh giá cân bằng dữ liệu và cân bằng query?

### Bài 3 — Kiểm tra balancer trên lab

Trên một sharded cluster lab:

```javascript
sh.status();
sh.getBalancerState();
sh.isBalancerRunning();
```

Hãy phân biệt:

- Balancer có bật không.
- Hiện có dấu hiệu hoạt động không.
- Collection có cân bằng theo chính sách không.
- Có migration đang diễn ra không.

Vì sao một lệnh Boolean không đủ trả lời cả bốn câu hỏi?

### Bài 4 — Quan sát phân bố một collection

Với collection `sharding_lab265.events265`:

```javascript
db.getSiblingDB("sharding_lab265")
  .events265
  .getShardDistribution();
```

Ghi nhận những shard đang chứa dữ liệu. Nếu có `sh.getShardedDataDistribution()`, so sánh owned/orphaned. Giải thích tại sao kết quả có thể khác giữa hai lần đo do migration hoặc dữ liệu mới.

### Bài 5 — Xác định phạm vi của `moveChunk`

Giả sử có range:

```text
[{ tenantId:"T02", eventAt:MinKey },
 { tenantId:"T03", eventAt:MinKey })
```

Nếu chạy helper chọn một điểm `tenantId:"T02"` bên trong range, hãy trả lời:

- Đang yêu cầu di chuyển một document hay cả range?
- Điều gì xảy ra với những document T02 khác cùng range?
- Vì sao phải biết shard đích và zone?
- Tại sao không gọi moveChunk hàng loạt khi chưa có runbook?

### Bài 6 — Thêm shard mới

Ban đầu:

```text
Shard A: 900 GB
Shard B: 880 GB
```

Sau khi thêm C, nó có 0 GB. Hãy mô tả quá trình balancer có thể sử dụng để chuyển dữ liệu, điều kiện khiến quá trình chậm và những metric cần theo dõi cho A/B/C.

### Bài 7 — Balancer bật nhưng chưa cân bằng

Cluster có:

```text
Shard A: 1 TB
Shard B: 150 GB
Balancer enabled: true
```

Đưa ra ít nhất năm giả thuyết **khác nhau** dẫn tới kết quả trên. Với mỗi giả thuyết, chỉ ra một loại thông tin cần xem: zone, chunk/range size, migration log, balancer window, hardware, shard key hoặc dữ liệu unsharded.

### Bài 8 — Zone làm thay đổi ý nghĩa “cân bằng”

Giả sử:

```text
Shard A: zone APAC
Shard B: zone APAC
Shard C: zone EU
```

Toàn bộ dữ liệu APAC là 3 TB còn EU là 500 GB. Vì sao không thể di chuyển tùy tiện APAC range sang C chỉ để đạt dung lượng đều trên ba shard? Hãy đề xuất cách đánh giá đúng cân bằng **trong từng zone**.

### Bài 9 — Nhận diện hot shard

Ba shard có owned data khoảng 500 GB mỗi shard, nhưng QPS:

```text
Shard A: 20.000/s
Shard B: 1.000/s
Shard C: 1.100/s
```

Vì sao chỉ gọi `sh.startBalancer()` không chắc giải quyết được vấn đề? Hãy đề xuất cách điều tra query routing, hot tenant, index, shard key và hardware.

### Bài 10 — Vì sao orphan có thể tăng tạm thời?

Một range vừa chuyển từ shard A sang B. Metadata đã công bố B là chủ mới, nhưng một công cụ giám sát báo:

```text
Shard A orphaned bytes: 200 MB
Shard B owned bytes tăng: 200 MB
```

Hãy giải thích tại sao đây có thể là trạng thái trung gian hợp lệ và vì sao không được tự xóa document theo filter trên A nếu chưa hiểu range deletion.

### Bài 11 — Chọn shard key phù hợp

So sánh ba khóa cho collection `events`:

```javascript
{ createdAt: 1 }
{ tenantId: 1 }
{ tenantId: "hashed" }
```

Giả sử 80% query lọc theo tenant, một tenant chiếm 70% số sự kiện và sự kiện mới luôn tăng theo thời gian. Hãy thảo luận trade-off về range query, targeted query, cardinality, hotspot và khả năng migration.

Không cần khẳng định có một shard key tối ưu tuyệt đối; nêu các dữ kiện cần đo trước khi chọn.

### Bài 12 — Quy trình thay shard

Một shard cần được loại bỏ để thay phần cứng. Hãy viết runbook mức khái niệm:

1. Xác định shard có bao nhiêu owned data.
2. Kiểm tra cluster còn đủ capacity.
3. Kiểm tra zone placement.
4. Khởi động draining theo command được version hỗ trợ.
5. Theo dõi tiến độ và lỗi.
6. Xác minh metadata/ownership trước khi tắt node.

Vì sao tắt tiến trình MongoDB và xóa thư mục dữ liệu trước khi drain hoàn tất là nguy hiểm?

### Bài 13 — Phân biệt resharding và migration

Với collection hiện shard theo `{ tenantId: 1 }`, tổ chức muốn đổi sang `{ tenantId: 1, eventAt: 1 }`.

`sh.moveChunk()` có làm được điều này không? So sánh mục tiêu của **migration** và **resharding**, mức tác động và nhu cầu kiểm soát query/index.

### Bài 14 — Thiết kế dashboard cân bằng tải

Hãy đề xuất dashboard với:

- Owned GB từng shard.
- Orphaned GB từng shard.
- Số migration thành công/thất bại theo giờ.
- Disk free và IOPS.
- p95/p99 query latency.
- CPU/QPS theo shard.
- Balancer enabled/activity.
- Thời gian observation và version deployment.

Cho biết metric nào đánh giá **dữ liệu**, metric nào đánh giá **workload**, và metric nào dùng để phát hiện lỗi trong quá trình migration.

## 27. Quy trình thao tác an toàn để ghi nhớ

Khi cần điều tra hoặc điều chỉnh việc chuyển dữ liệu giữa shard, đi qua thứ tự:

1. **Xác nhận đang kết nối mongos** và namespace đúng.
2. **Kiểm tra shard key, zone và topology** trước khi giả định dữ liệu có thể phân tán tùy ý.
3. **Đo owned data**, không chỉ đếm chunk hay nhìn dung lượng file.
4. **Xem balancer enabled/activity/compliance** với helper được version hỗ trợ.
5. **Theo dõi history/log** để biết có migration hay lỗi đang lặp.
6. **Đánh giá donor/recipient** về disk, network, replica set health và application latency.
7. **Ưu tiên balancer** khi mục tiêu là tự động cân bằng thông thường.
8. **Chỉ manual move trong runbook có phạm vi**, ghi rõ range, shard đích và điều kiện hoàn tác.
9. **Không sửa trực tiếp metadata sharding** và không tự xóa orphan.
10. **Xác minh sau chuyển** bằng distribution, ownership, metrics và truy vấn của ứng dụng.

Quy trình này giúp phân biệt một cluster đang cân bằng bình thường, một cluster bị giới hạn bởi policy/shard key và một cluster gặp sự cố migration thật sự.

## 28. Tổng kết

**MongoDB chia dữ liệu sharded theo các khoảng của shard key.** Một range/chunk là đơn vị logic mà hệ thống có thể chuyển từ donor sang recipient. Quá trình migration bao gồm sao chép, đồng bộ thay đổi, cập nhật metadata quyền sở hữu và dọn dữ liệu không còn được sở hữu trên shard nguồn.

**Balancer hướng tới phân bố dữ liệu phù hợp chính sách**, không bảo đảm số document, số chunk, CPU hay QPS luôn bằng nhau. Dung lượng owned, zone constraints, shard key và khả năng tách range quyết định những gì thực sự có thể cân bằng.

**Theo dõi phải kết hợp nhiều lớp thông tin.** `sh.status()` giúp quan sát topology; `sh.getBalancerState()` và các helper activity cho biết trạng thái balancer; `getShardDistribution()`/`getShardedDataDistribution()` cung cấp góc nhìn về dữ liệu; log và metric hạ tầng giúp phát hiện migration lỗi hoặc ảnh hưởng latency.

**Lệnh di chuyển thủ công là thao tác quản trị có tác động thật.** `sh.moveChunk()` hướng tới cả range chứa giá trị shard key, không phải một document. Chỉ dùng khi biết rõ namespace, donor, recipient, zone và tác động tài nguyên; không sửa `config.chunks` hay xóa dữ liệu trực tiếp để “ép cân bằng”.

**Mục tiêu cuối cùng là cluster có khả năng mở rộng và phục vụ ứng dụng ổn định**, chứ không phải đạt một biểu đồ chunk count đẹp. Khi hiểu được quyền sở hữu range, cơ chế migration và các chỉ số balancer, bạn sẽ biết lúc nào cần quan sát thêm, lúc nào phải điều chỉnh mô hình phân bố và lúc nào một thay đổi thủ công thực sự được biện minh.
