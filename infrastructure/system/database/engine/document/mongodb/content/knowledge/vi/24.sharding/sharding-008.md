# Zone sharding và ràng buộc vị trí dữ liệu trong MongoDB

Khi ứng dụng MongoDB phát triển thành nhiều khu vực địa lý, nhiều khách hàng doanh nghiệp hoặc nhiều nhóm dữ liệu có yêu cầu vận hành riêng, câu hỏi không chỉ còn là **“chia dữ liệu sang bao nhiêu shard?”**, mà còn là **“dữ liệu thuộc nhóm nào được phép đặt trên những shard nào?”**. Một hệ thống có thể cần đưa đơn hàng của khách hàng châu Âu đến nhóm shard ở châu Âu, dữ liệu khu vực châu Á đến nhóm shard tương ứng, hoặc dành một nhóm shard riêng cho một tenant lớn.

**Zone sharding** (còn được gọi là *tag-aware sharding* trong một số tài liệu) là tính năng của MongoDB Sharding giúp gắn **một hay nhiều khoảng giá trị shard key** với **các shard thuộc zone tương ứng**. Balancer sử dụng những ràng buộc đó để phân bố các **chunk/range** phù hợp lên những shard được phép phục vụ zone.

Đây là một công cụ rất hữu ích để tổ chức vị trí dữ liệu, nhưng cũng là một công cụ dễ bị hiểu sai. Zone sharding **không tự tạo shard**, **không tự di chuyển server đến một quốc gia**, **không thay thế quy tắc replication**, và **không thể được dùng một mình làm bằng chứng đáp ứng yêu cầu pháp lý về data residency**.

Bài học này giải thích:

- Zone, shard, shard key, zone range và chunk/range liên hệ với nhau như thế nào.
- Cách thiết kế shard key để đưa dữ liệu theo vùng/tenant đến nhóm shard phù hợp.
- Cách cấu hình zone bằng các lệnh **sh.addShardToZone()** và **sh.updateZoneKeyRange()**.
- Cách nhận biết ranh giới khoảng, kiểm tra balancer và quan sát vị trí dữ liệu thực tế.
- Rủi ro của dữ liệu đã tồn tại, migration, failover, backup, replication và thao tác thay đổi zone.
- Khi nào zone sharding phù hợp, khi nào cần một kiến trúc phân tách cluster khác.
- Cách viết ứng dụng Java/Spring Data để sử dụng shard key nhất quán, truy vấn đúng vùng và hạn chế thao tác cross-shard.

Các lệnh bên dưới chỉ minh họa trên **sharded cluster thử nghiệm** có nhiều shard. Không chạy những lệnh thay đổi zone, shard key, balancer hoặc placement trên production khi chưa có quy trình change management, quyền truy cập và phương án kiểm chứng.

## 1. Ôn lại kiến trúc sharded cluster

Một sharded cluster MongoDB thường có:

| Thành phần | Vai trò |
|---|---|
| **mongos** | Router nhận truy vấn từ ứng dụng, xác định shard liên quan và chuyển lệnh |
| **Config server replica set (CSRS)** | Quản lý metadata về sharding, vùng và cách phân bố dữ liệu |
| **Shard** | Nhóm máy lưu một phần dữ liệu của các collection được shard; thường là replica set |
| **Shard key** | Trường hoặc tổ hợp trường dùng để định vị dữ liệu trong không gian shard key |
| **Chunk/range** | Một khoảng giá trị shard key được gán cho shard tại một thời điểm |
| **Balancer** | Thành phần quản lý việc cân bằng và tuân thủ các ràng buộc phân bố như zone |

Sơ đồ khái quát:

~~~text
                     Ứng dụng
                        |
                        v
                   +---------+
                   |  mongos |
                   +---------+
                        |
              metadata từ config servers
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
       Shard A       Shard B       Shard C
     (replica set) (replica set) (replica set)
          |             |             |
       Documents      Documents     Documents
         thuộc         thuộc         thuộc
        range A       range B       range C
~~~

MongoDB không chia collection bằng cách “document đầu tiên vào máy 1, document tiếp theo vào máy 2” theo một vòng tròn đơn giản. Nó xác định nơi lưu document theo **giá trị shard key** và metadata phân bố range/chunk.

### 1.1. Sharding theo khóa khác replication

Hai cơ chế bổ sung nhau nhưng giải quyết vấn đề khác nhau:

- **Sharding** chia **các phần dữ liệu** của một collection sang các shard để mở rộng dung lượng và tải.
- **Replication** tạo và duy trì **các bản sao trong cùng shard/replica set** để tăng khả năng chịu lỗi và phục vụ đọc theo chính sách.

Ví dụ một shard nằm trong zone EU vẫn có thể có thành viên replica set được triển khai ở các khu vực khác nếu hạ tầng được cấu hình như vậy. Zone ràng buộc **shard sở hữu range**, không tự kiểm soát mọi vị trí của các thành viên replica set.

### 1.2. Balancer và quyền sở hữu range

Khi một range được chuyển từ shard A sang shard B, MongoDB phải tổ chức di chuyển và cập nhật metadata. Trong các phiên bản khác nhau, tài liệu và lệnh chẩn đoán có thể dùng tên **chunk**, **range** hoặc các khái niệm tối ưu tương đương.

Về mặt tư duy, zone sharding đưa ra quy tắc:

> Những range có shard key thuộc zone X phải được gán cho những shard thuộc zone X.

Balancer cố gắng đưa placement thực tế về trạng thái tuân thủ. **Cấu hình zone không có nghĩa mọi document được di chuyển xong ngay khi câu lệnh vừa trả về**.

## 2. Zone sharding là gì?

Một **zone** là nhãn logic do quản trị viên đặt, ví dụ:

~~~text
ZONE_EU
ZONE_APAC
ZONE_US
ZONE_TENANT_PREMIUM
~~~

Zone không phải một máy, một database hay một collection riêng. Nó mô tả **nhóm shard có thể chứa những khoảng shard key được gán vào zone ấy**.

Có ba quan hệ quan trọng:

1. **Shard → Zone:** gắn shard vào một hoặc nhiều zone.
2. **Shard-key range → Zone:** gắn một khoảng giá trị của shard key trong collection vào một zone.
3. **Balancer → Placement:** điều phối range tới những shard thuộc zone phù hợp.

### 2.1. Ví dụ phân vùng theo nơi cư trú dữ liệu

Giả sử collection **geo_orders.orders** có shard key:

~~~javascript
{
  dataRegion: 1,
  orderId: 1
}
~~~

Trong đó:

- **dataRegion** là mã vùng nghiệp vụ đã được xác định theo chính sách, chẳng hạn "EU", "APAC" hoặc "US".
- **orderId** là mã đơn giúp phân biệt các đơn trong cùng vùng.

Quản trị viên muốn:

~~~text
dataRegion = EU   --> chỉ các shard thuộc ZONE_EU
dataRegion = APAC --> chỉ các shard thuộc ZONE_APAC
dataRegion = US   --> chỉ các shard thuộc ZONE_US
~~~

Sơ đồ:

~~~text
                  Shard key của document
                    { dataRegion, orderId }
                              |
               +--------------+--------------+
               |              |              |
          dataRegion=EU  dataRegion=APAC  dataRegion=US
               |              |              |
               v              v              v
           ZONE_EU        ZONE_APAC        ZONE_US
               |              |              |
         +-----+-----+     +--+---+      +---+---+
         |           |     |      |      |       |
       shardEU1   shardEU2 shardAP1 shardAP2 shardUS1
~~~

Đây chỉ là sơ đồ tên logic. Việc shardEU1 có thực sự chứa dữ liệu trên thiết bị vật lý ở EU hay không phụ thuộc **cấu hình hạ tầng/replica set và quy trình triển khai**, không phụ thuộc riêng tên zone.

### 2.2. Một zone có thể chứa nhiều shard

~~~text
ZONE_EU:
  shardEU1
  shardEU2
  shardEU3
~~~

Khi một zone có nhiều shard, MongoDB có thể phân bố các range thuộc zone giữa những shard đó theo điều kiện balancer, kích thước dữ liệu và khả năng placement.

Vì vậy, **zone không có nghĩa ép mọi dữ liệu lên một shard duy nhất**. Điều này giúp vừa giữ ràng buộc địa điểm vừa có khả năng mở rộng trong phạm vi zone.

### 2.3. Một shard có thể thuộc nhiều zone

Ví dụ:

~~~text
shardShared:
  ZONE_EU
  ZONE_APAC
~~~

Khi đó shardShared có thể được phép chứa range của cả EU và APAC. Nếu chính sách yêu cầu **ngăn hoàn toàn việc đặt hai nhóm dữ liệu cạnh nhau**, cấu hình shard cùng tham gia hai zone sẽ làm suy yếu ý định phân tách.

**Muốn isolation theo vị trí, phải kiểm tra membership thực tế của từng shard**, không chỉ đặt tên zone đẹp.

### 2.4. Một zone có thể có nhiều khoảng range

Zone có thể gắn với các khoảng shard key khác nhau. Điều này hữu ích khi nhiều mã vùng được phép đặt tại cùng một nhóm shard:

~~~text
ZONE_EU:
  dataRegion=EU
  dataRegion=EEA

ZONE_APAC:
  dataRegion=APAC
  dataRegion=SEA
~~~

Các range gán zone phải được xác định sao cho **không chồng lấn trái quy tắc cấu hình**, và cần bảo đảm có đủ shard thuộc zone để placement được thực hiện.

### 2.5. Dữ liệu không thuộc zone nào đi đâu?

**Unzoned ranges** là những range không được gán cho zone cụ thể. Chúng có thể được MongoDB phân bố trên các shard phù hợp theo quy tắc balancer thông thường, không được tự động coi là bị ràng buộc vào một quốc gia hoặc một nhóm shard đã đặt tên.

Điểm này đặc biệt nguy hiểm với field vùng:

~~~javascript
{
  dataRegion: "UNKNOWN",
  orderId: "O-999"
}
~~~

Nếu "UNKNOWN" không được phủ bởi một zone range và hệ thống vẫn cho ghi, document có thể nằm ngoài thiết kế residency mong đợi. **Zone sharding không phải schema validator**; ứng dụng cần kiểm soát mã vùng hợp lệ và xác định chính sách với dữ liệu không phân loại được.

## 3. Zone khác gì với shard key và balancer?

| Khái niệm | Chức năng | Điều nó không tự bảo đảm |
|---|---|---|
| Shard key | Phân định không gian giá trị dùng để định tuyến/phân bố | Không tự biết vị trí pháp lý mong muốn của dữ liệu |
| Zone | Nhóm shard và các range được phép nằm trên chúng | Không tự biến server thành máy đặt ở vùng địa lý tương ứng |
| Balancer | Điều phối placement theo quy tắc và trạng thái cluster | Không bảo đảm migration hoàn tất tức thì |
| Replica set | Duy trì bản sao của dữ liệu một shard | Không tự bị giới hạn địa lý bởi nhãn zone |
| Read preference | Chọn nơi phục vụ các thao tác đọc được hỗ trợ | Không tự thay đổi shard sở hữu document |
| Schema validation | Bảo đảm kiểu, sự hiện diện hoặc miền giá trị field | Không tự chọn shard/zone để đặt dữ liệu |
| Authorization | Kiểm soát ai được đọc/ghi | Không tự cấu hình residency vật lý |

Khi xây dựng “chỉ dữ liệu EU ở EU”, cần phối hợp **shard placement, vị trí tất cả replica set members, chính sách backup/restore, các hệ thống đồng bộ và quyền truy cập**. Chỉ một unique name như ZONE_EU không đủ.

## 4. Shard key là nền tảng của ràng buộc zone

Zone sharding hoạt động trên **khoảng giá trị shard key**. Vì vậy, việc chọn shard key quyết định zone có thể bao phủ những nhóm dữ liệu mong muốn hay không.

### 4.1. Thiết kế có field vùng ở đầu

Ví dụ phù hợp cho phân vùng theo vùng:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

Giá trị shard key của order:

~~~javascript
{
  dataRegion: "EU",
  orderId: "O-EU-1001"
}
~~~

Các document cùng dataRegion nằm trong một phần liên tục của thứ tự shard key ghép, nên dễ xác định khoảng cho zone.

### 4.2. Thiết kế không có field vùng

Ví dụ:

~~~javascript
{ orderId: "hashed" }
~~~

Nếu orderId là khóa hashed duy nhất, giá trị hash không tự gom đơn hàng theo **dataRegion** thành một dải liên tục. Khi đó không thể chỉ dựa trên điều kiện dataRegion = "EU" để xác định một zone range theo cùng cách như shard key có dataRegion ở prefix.

Nếu yêu cầu residency là bắt buộc, cần xem lại shard key trước khi triển khai thay vì hy vọng MongoDB suy ra vùng từ field không nằm trong khóa.

### 4.3. Chọn compound shard key có thể vừa zone vừa phân bố tải

Một shard key chỉ gồm:

~~~javascript
{ dataRegion: 1 }
~~~

có thể tạo **cardinality rất thấp**: nếu chỉ có ba region, cả dữ liệu của mỗi region có thể dồn vào một giá trị shard key. Điều này có thể làm giảm khả năng phân phối tải và gặp những giới hạn về việc chia range có cùng khóa.

Thêm trường phân biệt như orderId:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

cho nhiều giá trị shard key hơn để MongoDB có thể chia range trong một region. Tuy nhiên, cần cân nhắc truy vấn thực tế, tính đơn điệu của orderId, write hotspots, kích thước mỗi tenant và index.

### 4.4. Thứ tự field quyết định khả năng query targeting

Giả sử shard key là:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

Truy vấn có cả hai field:

~~~javascript
db.orders.findOne({
  dataRegion: "EU",
  orderId: "O-EU-1001"
});
~~~

thường thuận lợi cho mongos định tuyến đến đúng range/shard.

Ngược lại:

~~~javascript
db.orders.findOne({
  orderId: "O-EU-1001"
});
~~~

thiếu prefix dataRegion và có thể phải truy vấn nhiều shard (*scatter-gather*). Việc có index riêng trên orderId ở các shard không tự biến một query thiếu shard-key prefix thành target đúng một shard trong mọi trường hợp.

### 4.5. Vùng là dữ liệu nghiệp vụ, không nên lấy bừa từ header

Nếu server để client tự gửi:

~~~json
{
  "dataRegion": "EU",
  "orderId": "O-1234"
}
~~~

thì người dùng có thể gắn region sai và khiến dữ liệu được đưa đến một zone không đúng chính sách.

Nên xác định dataRegion từ **tenant configuration, customer residency policy hoặc thuộc tính đã được xác minh**, validate tại biên hệ thống, kiểm tra quyền và lưu lại nguồn quyết định. Trường vùng không phải một chuỗi trang trí có thể thay đổi tùy tiện.

## 5. Chuẩn bị một sharded cluster để thực hành

Các ví dụ tiếp theo giả định đã có một **sharded cluster thử nghiệm**, với:

~~~text
mongos router
config server replica set

shardEU1
shardEU2
shardAP1
shardAP2
shardUS1
~~~

Những tên shard trên chỉ là **tên minh họa**, phải thay bằng tên thực tế do cluster trả về. Người quản trị đã triển khai các node, gắn chúng vào cluster và bảo đảm mongos kết nối tới config server. Bài học **không hướng dẫn giả lập residency** bằng cách tạo năm tên shard trong một standalone MongoDB; zone sharding chỉ có ý nghĩa trong sharded cluster.

### 5.1. Xác định bạn đang kết nối mongos

Trong mongosh:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Khi thực hiện qua mongos, output thường thể hiện thông tin nhận dạng router tương ứng, chẳng hạn trường **msg: "isdbgrid"** trong những phiên bản hỗ trợ.

Một cách quan sát khác:

~~~javascript
sh.status();
~~~

Lệnh giúp xem thông tin sharding và zone ở mức quản trị. Cần quyền phù hợp. Nếu sh.status không hoạt động, kiểm tra bạn có đang kết nối nhầm trực tiếp vào **mongod shard member** hay không.

### 5.2. Liệt kê shard đang có

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Quan sát field **_id** của từng shard để dùng chính xác trong các lệnh tiếp theo. Không tự suy luận shard name từ hostname hoặc đặt tên “shardEU1” rồi giả định lệnh sẽ tạo ra shard ấy.

### 5.3. Đảm bảo các shard thực sự được triển khai ở vị trí mong muốn

Trước khi gắn zone, cần kiểm tra:

1. **Replica set members** của shard có đặt đúng quốc gia/khu vực theo chính sách không?
2. **Storage volumes, snapshots, backups** có ở khu vực được phép không?
3. Cluster có dùng **cloud provider region, availability zone** và nơi đặt node đúng yêu cầu không?
4. Có cơ chế **log, audit, export, analytics** chuyển dữ liệu sang vị trí khác không?
5. Shard đang chứa những collection khác và có cho phép trộn dữ liệu residency khác nhau không?

Zone là lớp metadata phân bố **trên những shard đã tồn tại**. Việc chuẩn bị cơ sở hạ tầng và chính sách lưu trữ phải được làm độc lập.

## 6. Thiết lập shard membership bằng sh.addShardToZone()

Sau khi xác nhận tên shard, quản trị viên gắn shard vào zone:

~~~javascript
sh.addShardToZone("shardEU1", "ZONE_EU");
sh.addShardToZone("shardEU2", "ZONE_EU");

sh.addShardToZone("shardAP1", "ZONE_APAC");
sh.addShardToZone("shardAP2", "ZONE_APAC");

sh.addShardToZone("shardUS1", "ZONE_US");
~~~

Ý nghĩa:

- **shardEU1**, **shardEU2** có thể nhận các range được gắn ZONE_EU.
- **shardAP1**, **shardAP2** có thể nhận range của ZONE_APAC.
- **shardUS1** có thể nhận range của ZONE_US.

Lệnh này cập nhật membership giữa shard và zone. Nó **không tự gắn khoảng shard key của collection** vào zone, cũng không tự tạo ra các document/collection mới.

### 6.1. Một shard vào nhiều zone

Về mặt tính năng có thể gắn:

~~~javascript
sh.addShardToZone("shardShared", "ZONE_EU");
sh.addShardToZone("shardShared", "ZONE_APAC");
~~~

Nhưng với quy tắc residency nghiêm ngặt muốn tách EU và APAC, điều này có thể không phù hợp. Một shard ở nhiều zone được phép sở hữu range thuộc **cả hai zone**.

### 6.2. Membership không đồng nghĩa region vật lý

Câu lệnh:

~~~javascript
sh.addShardToZone("shardEU1", "ZONE_EU");
~~~

không xác minh trung tâm dữ liệu thực của shardEU1 ở châu Âu. Nhãn **ZONE_EU** chỉ mang ý nghĩa do quản trị viên gán. Nếu shardEU1 đặt ở địa điểm không phù hợp, zone vẫn không tự ngăn sai sót hạ tầng.

### 6.3. Gỡ shard khỏi zone

Khi có quy trình thay đổi placement:

~~~javascript
sh.removeShardFromZone("shardEU2", "ZONE_EU");
~~~

Thao tác này ảnh hưởng các shard được phép chứa range của ZONE_EU. Một số thay đổi sẽ bị từ chối hoặc không thể hoàn tất nếu không còn shard nào đáp ứng zone range đang được dùng, tùy trạng thái cluster.

**Không gỡ shard cuối cùng của một zone đang có dữ liệu mà chưa chuẩn bị nơi thay thế và kiểm chứng migration**. Việc thay đổi membership trên production cần được xem là thay đổi kiến trúc lưu trữ.

## 7. Gắn khoảng shard key vào zone bằng sh.updateZoneKeyRange()

Để zone thực sự ảnh hưởng tới placement của một **collection cụ thể**, cần gán các **khoảng shard key** cho zone.

Cú pháp tổng quát:

~~~javascript
sh.updateZoneKeyRange(
  "<database>.<collection>",
  <minShardKeyDocument>,
  <maxShardKeyDocument>,
  "<zoneName>"
);
~~~

Các thành phần:

| Tham số | Vai trò |
|---|---|
| Namespace | Tên database và collection, chẳng hạn geo_orders.orders |
| min | Giới hạn dưới của khoảng shard key |
| max | Giới hạn trên của khoảng shard key |
| zone | Tên zone được gán cho khoảng |

**Ranh giới của zone range dùng kiểu khoảng [min, max): min được bao gồm, max bị loại trừ.** MongoDB so sánh các giá trị dựa theo thứ tự BSON/shard key của collection, không phải theo phép so sánh chuỗi trực quan của một field đơn lẻ.

### 7.1. Vì sao dùng MinKey và MaxKey?

Khi shard key gồm hai field:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

và muốn tạo zone cho **mọi orderId thuộc một dataRegion**, cần bao phủ toàn bộ miền giá trị orderId được phép.

Có thể dùng sentinel BSON **MinKey** và **MaxKey**:

~~~javascript
{
  dataRegion: "EU",
  orderId: MinKey()
}

{
  dataRegion: "EU",
  orderId: MaxKey()
}
~~~

Đây là **giá trị biên để định nghĩa range**, không phải mã orderId thực tế. Giả định schema quy định orderId là String không rỗng, mọi orderId hợp lệ đều nằm giữa hai sentinel.

Do **max bị loại trừ**, cách viết này loại chính giá trị sentinel MaxKey ở vị trí orderId nếu một document thật sự dùng kiểu ấy; với schema chỉ cho phép String thì không phát sinh trường hợp đó.

### 7.2. Tạo vùng cho EU

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);
~~~

Lệnh gắn dải shard key của **dataRegion = "EU"** vào **ZONE_EU**.

### 7.3. Tạo vùng cho APAC và US

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "APAC", orderId: MinKey() },
  { dataRegion: "APAC", orderId: MaxKey() },
  "ZONE_APAC"
);

sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "US", orderId: MinKey() },
  { dataRegion: "US", orderId: MaxKey() },
  "ZONE_US"
);
~~~

Các khoảng trên **không trùng nhau** vì dữ liệu có giá trị dataRegion khác nhau.

### 7.4. Một ví dụ để thấy rõ biên [min, max)

Giả sử shard key đơn giản chỉ gồm:

~~~javascript
{ score: 1 }
~~~

Và zone range:

~~~javascript
sh.updateZoneKeyRange(
  "demo.scores",
  { score: 0 },
  { score: 100 },
  "ZONE_LOW"
);
~~~

Khi đó:

- score = 0: nằm trong range.
- score = 50: nằm trong range.
- score = 99: nằm trong range.
- **score = 100: không nằm trong range**.
- score = -1: không nằm trong range.

Những giá trị ngoài range này **không được bảo vệ bởi ZONE_LOW** chỉ vì có tên zone. Cần cấu hình thêm range khác hoặc có chính sách rõ ràng cho dữ liệu ngoài miền.

### 7.5. Không dùng các khoảng chồng lấn

Ví dụ vùng A quản lý:

~~~text
[0, 100)
~~~

và vùng B được gán:

~~~text
[50, 150)
~~~

Hai khoảng chồng lấn trên miền [50, 100), gây mâu thuẫn về zone placement. Đối với một collection, cần thiết kế những zone range **không mâu thuẫn nhau**; MongoDB có quy tắc kiểm tra range khi cấu hình.

Không nên giải quyết trường hợp một document “thuộc hai vùng” bằng cách cho hai zone range chồng nhau. Hãy xác định một **home region** hoặc mô hình chia dữ liệu phù hợp hơn.

### 7.6. Chú ý đầy đủ cấu trúc shard key

Với shard key ghép, nên biểu diễn ranh giới tường minh theo **đúng thứ tự field của shard key**, dùng MinKey/MaxKey cho field cần bao phủ toàn miền. Những quy tắc cho phép prefix/bound cụ thể phụ thuộc lệnh và phiên bản; sử dụng một bound có đủ các thành phần của shard key như ví dụ giúp tránh hiểu nhầm.

Nếu collection sử dụng **hashed shard key**, cần kiểm tra quy tắc bound và loại key thực tế; không mặc định một dải hash có thể diễn đạt “mọi document có country=EU” khi country không tạo thành prefix thích hợp.

### 7.7. Zone range là cấu hình của từng namespace

Lệnh cấu hình:

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);
~~~

không tự áp dụng cho:

~~~text
geo_orders.payments
geo_orders.orderEvents
geo_orders.customers
~~~

Nếu các collection này cũng cần residency theo dataRegion, phải thiết kế shard key và zone ranges tương ứng **cho từng collection** hoặc chọn mô hình dữ liệu khác. Zone membership ở shard có thể được tái sử dụng, nhưng range mapping là theo namespace.

## 8. Chuyển một collection thành sharded collection

Để minh họa, giả sử **geo_orders.orders** chưa được shard và chưa có dữ liệu. Làm qua mongos có quyền quản trị.

### 8.1. Tạo database và index shard key

~~~javascript
use geo_orders

db.orders.createIndex(
  { dataRegion: 1, orderId: 1 },
  { name: "idx_data_region_order" }
);
~~~

Đảm bảo môi trường đáp ứng các điều kiện về shard key và index. Với collection đã có nhiều unique indexes, cần kiểm tra các ràng buộc liên quan đến shard key trước khi shardCollection.

### 8.2. Bật sharding và khai báo shard key

Trong những môi trường/phiên bản cần thao tác bật sharding cho database:

~~~javascript
sh.enableSharding("geo_orders");
~~~

Sau đó:

~~~javascript
sh.shardCollection(
  "geo_orders.orders",
  { dataRegion: 1, orderId: 1 }
);
~~~

Một số phiên bản mới không yêu cầu gọi sh.enableSharding riêng trước sh.shardCollection; hãy kiểm tra hành vi phiên bản của môi trường. Điểm chính là collection phải được shard bằng khóa phù hợp với zone ranges đã thiết kế.

### 8.3. Thứ tự tạo zone ảnh hưởng chi phí ban đầu

Có hai cách vận hành:

**Cách A — Cấu hình trước khi có dữ liệu:** khai báo shard membership, chuẩn bị zone ranges và shardCollection trên collection rỗng theo trình tự hỗ trợ của phiên bản MongoDB. MongoDB có thể sử dụng zone ranges để tổ chức phân bố ban đầu, giúp giảm nhu cầu di chuyển dữ liệu đã ghi sai vị trí.

**Cách B — Cấu hình sau khi collection đã chứa dữ liệu:** tạo/gắn zone ranges cho collection hiện tại. Balancer cần điều phối lại những chunk/range đang nằm trên shard không phù hợp.

Với workload nhạy cảm về residency, **tránh đưa dữ liệu thật vào cluster khi chưa có chính sách placement và hạ tầng phù hợp**. Việc có zone sau đó không xóa được lịch sử dữ liệu từng tồn tại ở nơi cũ hoặc trong snapshot/backup.

### 8.4. Insert dữ liệu ví dụ

~~~javascript
db.orders.insertMany([
  {
    _id: "ORDER-EU-001",
    dataRegion: "EU",
    orderId: "EU-001",
    tenantId: "TENANT-EU-A",
    amountCents: NumberLong("12500"),
    status: "CREATED"
  },
  {
    _id: "ORDER-EU-002",
    dataRegion: "EU",
    orderId: "EU-002",
    tenantId: "TENANT-EU-B",
    amountCents: NumberLong("9800"),
    status: "PAID"
  },
  {
    _id: "ORDER-AP-001",
    dataRegion: "APAC",
    orderId: "AP-001",
    tenantId: "TENANT-AP-A",
    amountCents: NumberLong("15000"),
    status: "CREATED"
  },
  {
    _id: "ORDER-AP-002",
    dataRegion: "APAC",
    orderId: "AP-002",
    tenantId: "TENANT-AP-B",
    amountCents: NumberLong("5900"),
    status: "PAID"
  },
  {
    _id: "ORDER-US-001",
    dataRegion: "US",
    orderId: "US-001",
    tenantId: "TENANT-US-A",
    amountCents: NumberLong("23000"),
    status: "CREATED"
  }
]);
~~~

Chỉ chạy insertMany một lần trên collection thử nghiệm trống. Các ID cố định sẽ báo duplicate nếu chạy lại. Với năm document, rất khó đánh giá cân bằng/hiệu năng; dữ liệu này chủ yếu để xác nhận **điều kiện filter và mô hình shard key**.

## 9. Kiểm tra zone membership và zone ranges

Một trong những sai lầm lớn nhất là gọi xong sh.updateZoneKeyRange rồi kết luận dữ liệu **đã ở đúng nơi**. Cần kiểm tra **cấu hình** và **placement thực tế** bằng những nguồn quan sát phù hợp.

### 9.1. Xem tổng quan bằng sh.status()

~~~javascript
sh.status();
~~~

Tùy phiên bản và số lượng collection, output có thể hiển thị:

- Danh sách shard và thuộc tính liên quan.
- Namespace đã shard.
- Shard key và kiểu phân vùng.
- Thống kê hoặc thông tin phân bố range/chunk.
- Zone/tag ranges đã khai báo.

**sh.status() là công cụ quan sát metadata**, không phải bằng chứng duy nhất rằng không còn bản sao dữ liệu trong các backup, snapshot hay các node replication ngoài nơi quy định.

### 9.2. Kiểm tra membership bằng metadata config

Trong môi trường có quyền đọc metadata:

~~~javascript
db.getSiblingDB("config")
  .shards
  .find(
    {},
    { _id: 1, host: 1, tags: 1 }
  );
~~~

Trong những phiên bản có trường **tags** biểu diễn zone membership, kết quả có thể trông tương tự:

~~~javascript
{
  _id: "shardEU1",
  tags: ["ZONE_EU"]
}
~~~

Tên field/metadata có thể thay đổi theo phiên bản. **Không sửa trực tiếp collection config.shards** để thêm zone; dùng helper/command quản trị được MongoDB hỗ trợ.

### 9.3. Xem zone ranges của collection

~~~javascript
db.getSiblingDB("config")
  .tags
  .find({
    ns: "geo_orders.orders"
  });
~~~

Metadata zone range trong các phiên bản hỗ trợ thường cung cấp:

~~~javascript
{
  ns: "geo_orders.orders",
  min: {
    dataRegion: "EU",
    orderId: MinKey()
  },
  max: {
    dataRegion: "EU",
    orderId: MaxKey()
  },
  tag: "ZONE_EU"
}
~~~

Kết quả cho biết **range EU đã được khai báo thuộc ZONE_EU**. Nó **chưa chứng minh mọi chunk tương ứng đang được gán cho shardEU1 hoặc shardEU2**.

### 9.4. Phân biệt kiểm tra “quy tắc” với kiểm tra “thực thi”

| Câu hỏi | Nguồn quan sát phù hợp |
|---|---|
| Shard nào thuộc ZONE_EU? | sh.status / metadata shard membership |
| Khoảng giá trị nào gắn ZONE_EU? | sh.status / config.tags theo namespace |
| Chunk/range đang thuộc shard nào? | Phân bố metadata collection, công cụ sharding được hỗ trợ |
| Balancer có đang chạy hoặc đang gặp lỗi? | sh.getBalancerState / sh.isBalancerRunning / log/monitoring theo phiên bản |
| Migration đã hoàn tất chưa? | Quan sát balancer, phân bố theo shard và xác nhận ngoài thời điểm chuyển đổi |
| Dữ liệu có bản sao ngoài EU không? | Kiểm tra toàn bộ replica set, backup, logs, exports và hạ tầng |

Tất cả các nhóm quan sát trên mới tạo được bức tranh tương đối đầy đủ về residency.

### 9.5. Kiểm tra trạng thái balancer

Các helper thường gặp:

~~~javascript
sh.getBalancerState();
sh.isBalancerRunning();
~~~

Trong những phiên bản mongosh hỗ trợ, chúng cung cấp thông tin về cấu hình bật/tắt balancer và trạng thái hoạt động. Đừng suy ra chỉ từ một lần gọi **isBalancerRunning() = false** rằng đã hết migration hoặc mọi range đúng zone: balancer có thể đang tạm nghỉ giữa các vòng, hoặc đang bị dừng.

Trong môi trường production, nên kiểm tra thêm lịch sử migration, các cảnh báo từ monitoring và trạng thái bố trí range theo công cụ được phiên bản hỗ trợ.

### 9.6. Xem phân bố ở mức collection

Trên những phiên bản/môi trường mongosh hỗ trợ, có thể thử:

~~~javascript
db.getSiblingDB("geo_orders")
  .orders
  .getShardDistribution();
~~~

Lệnh/hỗ trợ có thể khác giữa shell và phiên bản server. Thông tin về phân bố số document/kích thước mỗi shard giúp đánh giá hiện trạng, nhưng **không tự xác nhận mọi document EU đang ở shard EU** nếu chỉ nhìn tổng số document.

Muốn kiểm chứng rule cần đối chiếu **range boundaries, current ownership và zone membership**, không chỉ bảng số lượng theo shard.

### 9.7. Đọc config metadata phải là thao tác đọc

Không sử dụng:

~~~javascript
// Không thực hiện những thao tác can thiệp metadata như sau.
db.getSiblingDB("config").tags.updateOne(...);
db.getSiblingDB("config").chunks.deleteMany(...);
~~~

Metadata sharding do MongoDB quản lý. Tự sửa trực tiếp có nguy cơ làm mất đồng bộ và gây lỗi cluster. Hãy dùng các helper quản trị zone/migration được công bố và phù hợp phiên bản.

## 10. Balancer áp dụng zone constraint như thế nào?

Khi zone range đã được gán và có shard thuộc zone, MongoDB dùng cơ chế balancer để xử lý những chunk/range không nằm đúng nơi.

Ví dụ, trước khi bật zone:

~~~text
EU range:
  shardAP1 đang sở hữu một phần
  shardEU1 đang sở hữu phần còn lại

Zone rule mới:
  EU range -> ZONE_EU
  ZONE_EU members -> shardEU1, shardEU2
~~~

Mục tiêu sau khi cân bằng:

~~~text
EU range:
  shardEU1
  shardEU2

shardAP1:
  không còn sở hữu EU range theo metadata
~~~

### 10.1. Quy trình logic

~~~text
Khai báo zone range
        |
        v
MongoDB nhận biết range placement
        |
        v
Range nào ở shard không thuộc zone?
        |
       Có
        |
        v
Balancer xem xét migration/range management
        |
        v
Chuyển quyền sở hữu tới shard thuộc zone
        |
        v
Cập nhật metadata phân bố
        |
        v
Tiếp tục kiểm tra những range chưa phù hợp
~~~

Thứ tự, thời gian và cơ chế thực thi chi tiết phụ thuộc phiên bản, loại collection, số lượng shard và tải hiện tại. Đây là sơ đồ khái niệm, không phải log tuần tự cố định của MongoDB.

### 10.2. Không bảo đảm migration ngay lập tức

Một lệnh:

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);
~~~

chủ yếu thiết lập **quy tắc**. Nếu trước đó chunk EU nằm sai zone, MongoDB có thể cần một khoảng thời gian để hoàn tất các migration phù hợp.

Khoảng thời gian này có thể phụ thuộc:

- Lượng dữ liệu phải di chuyển.
- Số range/chunk và độ phân mảnh hiện tại.
- Tải ghi/đọc đồng thời.
- Băng thông giữa các shard.
- Cấu hình và trạng thái balancer.
- Giới hạn migration, lỗi mạng hoặc trạng thái node.

Trong giai đoạn chuyển đổi, **không được tuyên bố residency đã đạt hoàn toàn** chỉ vì lệnh cấu hình trả kết quả thành công.

### 10.3. Điều gì xảy ra nếu balancer bị dừng?

Nếu đã gắn zone nhưng balancer đang bị tắt, những range nằm trên shard không phù hợp có thể **không được tự động chuyển đi** như kỳ vọng. Chính sách placement được ghi nhận không tương đương hệ thống đã thực hiện di chuyển.

Trên môi trường thử nghiệm, có thể quan sát trạng thái bằng helper như phần trên. Việc bật/tắt balancer của production cần quy trình vận hành riêng vì ảnh hưởng toàn bộ workload sharded collection.

### 10.4. Chuyển dữ liệu có thể tốn tài nguyên

Migration có thể làm tăng:

- Network I/O giữa các shard.
- Disk I/O và CPU của shard nguồn/đích.
- Mức sử dụng bộ nhớ trong quá trình xử lý.
- Độ trễ truy vấn ở một số thời điểm.
- Áp lực lên capacity của shard thuộc zone.

Đừng dồn dữ liệu của một region rất lớn vào một shard nhỏ chỉ vì đó là shard duy nhất mang tên vùng hợp lý. Nếu region cần nhiều capacity, có thể bố trí **nhiều shard trong zone** với thiết kế shard key đủ khả năng phân chia range.

### 10.5. “Có đúng zone” khác “cân bằng đều”

Nếu ZONE_EU có ba shard, mục tiêu ràng buộc là range EU thuộc **một shard được phép trong ZONE_EU**. Điều đó không có nghĩa mọi shard EU chứa chính xác một phần ba số document hoặc byte.

Dung lượng và tải thực phụ thuộc phân bố shard key, kích thước document, hoạt động ghi, trạng thái balancer và một số giới hạn chia range. Cần theo dõi **dung lượng, IOPS, CPU, số lượng hotspot** thay vì chỉ đếm shard.

## 11. Query targeting trong zone sharding

Zone sharding xác định placement; **mongos vẫn dùng shard key và metadata** để định tuyến truy vấn.

### 11.1. Query đầy đủ shard key

~~~javascript
db.orders.find({
  dataRegion: "EU",
  orderId: "EU-001"
});
~~~

Với shard key:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

mongos có thông tin để target range chứa cặp khóa này. Nếu range thuộc zone EU và placement đã hội tụ, truy vấn được chuyển tới shard có quyền sở hữu range ở thời điểm đó.

### 11.2. Chỉ có dataRegion

~~~javascript
db.orders.find({
  dataRegion: "EU",
  status: "PAID"
});
~~~

Query có **prefix shard key** nên mongos có thể giới hạn các shard/range liên quan đến dataRegion EU. Nhưng nếu ZONE_EU có nhiều shard, query có thể phải đọc **nhiều shard trong zone EU**, chứ không nhất thiết đúng một shard.

Index phụ như:

~~~javascript
db.orders.createIndex({
  dataRegion: 1,
  status: 1,
  orderId: 1
});
~~~

có thể hỗ trợ lọc trong phạm vi shard, tùy query pattern và planner. Tuy nhiên, **index phụ không thay shard key** và không tự chuyển query thiếu dataRegion thành target chính xác theo vùng.

### 11.3. Chỉ có orderId

~~~javascript
db.orders.find({
  orderId: "EU-001"
});
~~~

Không có dataRegion nên mongos có thể phải hỏi nhiều shard. Nếu ứng dụng chủ yếu truy vấn theo orderId, cần một chiến lược:

- Tích hợp dataRegion vào thông tin trả về từ API tạo order và gửi lại khi truy vấn.
- Lưu mapping **orderId → dataRegion** ở một nơi phù hợp, có consistency và residency được xác định.
- Thiết kế lại shard key/model dữ liệu nếu hầu hết truy vấn không mang prefix vùng.

Không nên tạo zone chỉ theo sở thích vận hành mà bỏ qua các query pattern quan trọng của ứng dụng.

### 11.4. Explain để xem shard nào được truy vấn

~~~javascript
db.orders.find({
  dataRegion: "EU",
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

Và:

~~~javascript
db.orders.find({
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

Trong sharded cluster, explain thường chứa thông tin về các shard tham gia, cây plan và những stage tương ứng. Vị trí và cấu trúc các trường như **shards**, **winningPlan**, **SHARD_MERGE** khác nhau giữa các phiên bản và execution engine.

Hãy so sánh **phạm vi shard được gửi truy vấn**, không chỉ tìm chữ IXSCAN hay COLLSCAN trong output.

### 11.5. Zone không bảo đảm truy vấn chỉ chạy trong một region từ mọi node ứng dụng

Nếu ứng dụng ở châu Á gửi truy vấn EU qua mongos ở châu Á, router vẫn phải chuyển lệnh tới shard EU theo placement. Điều này có thể tạo **độ trễ mạng xuyên vùng** dù dữ liệu đã được đặt đúng zone.

Muốn đạt trải nghiệm “dữ liệu EU ở EU, request EU cũng xử lý gần EU”, cần thiết kế **định tuyến ứng dụng/API gateway, vùng triển khai service và cách kết nối mongos** phù hợp. Zone chỉ điều phối phân bố dữ liệu của sharded collection.

## 12. Di chuyển khỏi zone hoặc thay đổi ranh giới

Một doanh nghiệp có thể đổi chính sách dữ liệu, mở thêm shard hoặc thay đổi phân vùng. Những thay đổi này phải được quản lý như **data migration**, không chỉ một dòng cấu hình.

### 12.1. Bỏ một zone range

Helper thường dùng:

~~~javascript
sh.removeRangeFromZone(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() }
);
~~~

Lệnh gỡ mapping vùng của một khoảng đã khai báo. **Gỡ range khỏi zone không có nghĩa MongoDB tức thì chuyển mọi document EU về nơi khác**. Sau khi không còn ràng buộc, range có thể được cân bằng theo các điều kiện khác, và placement cần quan sát.

### 12.2. Đổi EU từ zone cũ sang zone mới

Một kế hoạch thay đổi hợp lý thường gồm:

1. Tạo/kiểm tra shard ở khu vực mới, gồm mọi replica set member.
2. Gắn shard mới vào zone cần thiết hoặc thiết kế zone mới.
3. Cấu hình lại range mapping trong phạm vi phiên bản cho phép.
4. Đảm bảo balancer hoạt động theo kế hoạch.
5. Chờ/giám sát migration đến khi metadata ownership hội tụ.
6. Kiểm tra dấu vết/backup ở khu vực cũ theo chính sách.
7. Chỉ sau đó gỡ membership cũ hoặc ngừng sử dụng shard không còn hợp lệ.

Không nên gỡ shard cuối cùng khỏi zone trước khi có nơi nhận mới. Cũng không nên thay đổi key range của dữ liệu đã có mà bỏ qua tác động đến request đang chạy và các hệ thống đọc liên quan.

### 12.3. Thay đổi shard key có phải sửa zone tự động?

Zone ranges được định nghĩa trong **không gian shard key**. Nếu thay đổi cấu trúc shard key qua quy trình resharding hoặc thay đổi mô hình, các range/zone cần được **đánh giá và cấu hình phù hợp với khóa mới**.

Không được mặc định zone range của **{dataRegion:1,orderId:1}** áp dụng nguyên trạng cho **{tenantId:1,dataRegion:1}** hoặc **{orderId:"hashed"}**. Khả năng hỗ trợ và điều kiện resharding/zone của từng phiên bản cũng cần được kiểm tra riêng.

### 12.4. Di chuyển document giữa region không phải sửa một chuỗi

Nếu một khách hàng thay đổi residency từ APAC sang EU:

~~~javascript
{
  dataRegion: "APAC",
  orderId: "AP-001"
}
~~~

việc muốn đổi thành:

~~~javascript
{
  dataRegion: "EU",
  orderId: "AP-001"
}
~~~

có nghĩa thay đổi **giá trị shard key** và có thể cần di chuyển document tới shard khác. MongoDB áp dụng những điều kiện riêng cho update shard key, version và cách thực hiện thao tác; không nên viết một updateMany tùy tiện rồi mong toàn bộ tenant tự chuyển an toàn.

Ở tầng nghiệp vụ cần quyết định:

- Dữ liệu lịch sử có phải chuyển hay chỉ dữ liệu tạo mới?
- Có cần downtime/freeze writes khi chuyển vùng?
- Các reference, unique keys, transaction và index bị ảnh hưởng thế nào?
- Dữ liệu ở backup cũ được xử lý theo quy định ra sao?
- Nếu việc chuyển dở dang, khôi phục/rollback ở cấp ứng dụng như thế nào?

Thay đổi residency thường nên có **migration workflow riêng**, không phải một thao tác cập nhật field không kiểm soát.

## 13. Ràng buộc vị trí dữ liệu không đồng nghĩa chứng nhận data residency

**Data residency** thường nói đến yêu cầu dữ liệu được lưu hoặc xử lý trong một phạm vi địa lý/pháp lý cụ thể. **Data sovereignty** có thể liên quan thêm đến cơ sở pháp lý và quyền kiểm soát. Những yêu cầu cụ thể phụ thuộc hợp đồng, loại dữ liệu và quy định áp dụng; không thể kết luận chỉ từ tên vùng mà không xem bối cảnh.

Zone sharding hỗ trợ **chính sách placement cho range của một sharded collection**, nhưng chưa bao phủ toàn bộ vòng đời thông tin.

### 13.1. Những lớp cần kiểm tra

| Lớp | Câu hỏi quan trọng |
|---|---|
| Sharded data | Range chứa dữ liệu EU có được gán vào zone EU và đã hội tụ placement chưa? |
| Replica set | Primary, secondary, hidden/delayed members của shard được đặt ở đâu? |
| Config servers | Metadata nào được lưu ở config server và đặt tại đâu? |
| Backups/snapshots | Snapshot, PITR, lưu trữ lạnh, bản sao dự phòng được giữ ở vùng nào? |
| Migration | Dữ liệu từng tồn tại trên donor shard ngoài vùng có được cleanup/retention theo chính sách không? |
| Application logging | Log lỗi, audit, trace, payload request có vô tình chứa dữ liệu nhạy cảm không? |
| Query processing | Kết quả truy vấn có đi qua router/service ở vùng khác không? |
| Export/ETL | Data lake, warehouse, search index hoặc analytics pipeline được đặt ở đâu? |
| Access control | Người dùng/service ở vùng khác có quyền đọc dữ liệu theo chính sách không? |
| Disaster recovery | Khi khôi phục sau thảm họa, dữ liệu sẽ được restore vào đâu? |
| Encryption/key management | Khóa mã hóa, KMS, quy tắc truy cập và hạ tầng bảo mật ở đâu? |
| Retention/deletion | Dữ liệu và bản sao trong backup được giữ/xóa theo lịch nào? |

Một hệ thống có **mọi chunk của EU thuộc shardEU1** nhưng backup shardEU1 ở vùng không được phép vẫn có thể không đạt yêu cầu data residency.

### 13.2. Replica set có thể sao chép dữ liệu ra khỏi vùng

Giả sử zone EU gồm shard **EU_RS**, nhưng shard đó là replica set:

~~~text
EU_RS
  primary:   Frankfurt
  secondary: Frankfurt
  secondary: Singapore
~~~

Zone sharding có thể xác định EU range thuộc EU_RS. Tuy nhiên, secondary ở Singapore vẫn sao chép dữ liệu của **cùng shard** theo cơ chế replication.

Nếu chính sách yêu cầu **mọi bản sao vật lý của dữ liệu EU phải ở EU**, phải bố trí **mọi data-bearing member** của replica set theo yêu cầu, không chỉ primary hoặc tên shard.

Các thành viên đặc biệt, snapshot và cơ chế disaster recovery cũng cần được xem xét riêng theo chính sách.

### 13.3. Dữ liệu có thể xuất hiện ngoài zone trong quá trình di chuyển

Nếu cấu hình zone được áp dụng **sau khi dữ liệu đã ghi**, trước đó tài liệu có thể nằm trên các shard khác. Trong quá trình migration, MongoDB có cơ chế thay đổi ownership và dọn dữ liệu cũ theo quy tắc phiên bản.

Không nên lấy việc **metadata sở hữu range đã chuyển** làm bằng chứng ngay lập tức rằng không còn bất kỳ byte dữ liệu nào trên donor shard, snapshot hoặc backup lịch sử. Cần kiểm tra trạng thái cleanup và chính sách lưu trữ ở tầng hạ tầng.

### 13.4. Query xuyên vùng vẫn có thể truyền dữ liệu qua mạng

Một aggregation không lọc dataRegion:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      totalOrders: { $sum: 1 }
    }
  }
]);
~~~

có thể cần đọc dữ liệu từ nhiều shard thuộc nhiều zone để tính kết quả tổng. Tùy query plan, kết quả trung gian hoặc kết quả cuối có thể đi qua router hoặc một shard xử lý merge.

**Zone placement không phải cơ chế tự động cấm mọi truy vấn cross-region**. Nếu chính sách cấm đưa dữ liệu thô xuyên biên giới, kiến trúc phải kiểm soát đường truy vấn, vị trí mongos/application, phép aggregate và phạm vi dữ liệu được chuyển.

### 13.5. Không tự khẳng định đáp ứng một đạo luật

Zone sharding là một **công cụ kỹ thuật**, không phải chứng nhận tuân thủ GDPR, luật nội địa hóa dữ liệu hoặc điều khoản hợp đồng nào. Đánh giá tuân thủ cần có yêu cầu cụ thể, chính sách vận hành và bằng chứng về toàn bộ hệ thống.

Một hướng tiếp cận thực tế là tách hai tài liệu:

- **Placement design:** dataRegion nào thuộc zone nào, zone có những shard nào.
- **Compliance evidence:** vị trí mọi bản sao, backup, mạng, log, luồng truy cập, retention, audit và kiểm chứng thường xuyên.

## 14. Thiết kế zone cho multi-tenant SaaS

Một hệ thống SaaS có thể dùng cùng một cluster nhưng cần cô lập vị trí theo tenant.

### 14.1. Phương án A: zone theo home region

Mỗi tenant có thuộc tính cấu hình:

~~~javascript
{
  tenantId: "TENANT-123",
  homeRegion: "EU"
}
~~~

Mỗi document nghiệp vụ chứa:

~~~javascript
{
  dataRegion: "EU",
  tenantId: "TENANT-123",
  orderId: "ORD-100"
}
~~~

Shard key có thể cân nhắc:

~~~javascript
{
  dataRegion: 1,
  tenantId: 1,
  orderId: 1
}
~~~

Ưu điểm:

- Region nằm ở prefix cho zone range.
- Query thường biết tenantId và dataRegion có thể tận dụng prefix shard key.
- Có đủ nhiều giá trị từ tenantId/orderId để phân chia dữ liệu trong zone khi điều kiện phù hợp.

Nhược điểm:

- Mọi query theo orderId mà không biết dataRegion/tenantId có thể phải hỏi nhiều shard.
- Thay đổi homeRegion của tenant có thể trở thành dự án migration.
- Một tenant quá lớn có thể gây hotspot hoặc tạo nhu cầu capacity riêng.

### 14.2. Phương án B: dedicated zone cho tenant lớn

Ví dụ tenant **ENTERPRISE-A** có nhu cầu vận hành riêng, zone:

~~~text
ZONE_ENTERPRISE_A
  shardDedicatedA1
  shardDedicatedA2
~~~

Để dùng zone một cách chính xác, shard key phải cho phép xác định range tương ứng tenant ấy. Nếu shard key:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

thì có thể gắn:

~~~javascript
sh.updateZoneKeyRange(
  "saas.orders",
  { tenantId: "ENTERPRISE-A", orderId: MinKey() },
  { tenantId: "ENTERPRISE-A", orderId: MaxKey() },
  "ZONE_ENTERPRISE_A"
);
~~~

Và membership:

~~~javascript
sh.addShardToZone(
  "shardDedicatedA1",
  "ZONE_ENTERPRISE_A"
);

sh.addShardToZone(
  "shardDedicatedA2",
  "ZONE_ENTERPRISE_A"
);
~~~

Lưu ý zone không tự tạo **hàng rào hiệu năng tuyệt đối**. Shard có thể thuộc zone khác; mongos, config servers, network và một số tài nguyên chung vẫn tồn tại. Nếu khách hàng yêu cầu cách ly mạnh ở nhiều lớp, **cluster riêng** có thể phù hợp hơn.

### 14.3. Phương án C: region và tenant cùng trong khóa

Nếu muốn zone theo region nhưng query luôn theo tenant:

~~~javascript
{ dataRegion: 1, tenantId: 1, orderId: 1 }
~~~

Một zone range toàn bộ EU có thể dùng:

~~~javascript
sh.updateZoneKeyRange(
  "saas.orders",
  {
    dataRegion: "EU",
    tenantId: MinKey(),
    orderId: MinKey()
  },
  {
    dataRegion: "EU",
    tenantId: MaxKey(),
    orderId: MaxKey()
  },
  "ZONE_EU"
);
~~~

Với schema đảm bảo tenantId và orderId là các String hợp lệ, hai sentinel bao phủ toàn bộ miền giá trị nghiệp vụ mong đợi.

**Cần đặc biệt chú ý thứ tự và cấu trúc bound của compound key.** Không được tự đổi field thứ tự hoặc dùng kiểu BSON không khớp khi định nghĩa một range cho collection đang chạy.

### 14.4. Một tenant có dữ liệu ở nhiều region

Không phải mọi tenant đều có duy nhất một home region. Ví dụ một tập đoàn có văn phòng ở EU và US, mỗi đơn hàng phải lưu theo **nơi phát sinh giao dịch**. Khi đó có thể:

- Gán dataRegion theo từng document thay vì theo tenant cố định.
- Duy trì chính sách quyền và routing cho từng document.
- Chấp nhận query tenant toàn cục có thể phải đọc nhiều zone, hoặc dùng read model tổng hợp đã được phép.
- Tránh di chuyển dữ liệu lịch sử chỉ vì tenant thay đổi cấu hình mặc định.

Kiểu phân vùng phải bám sát **ràng buộc thật của dữ liệu**, không gắn một region cho tenant nếu từng document có chính sách residency độc lập.

## 15. Range sharding, hashed sharding và zone sharding

**Range-based sharding** và **hashed sharding** liên quan cách phân bố giá trị shard key; **zone sharding** bổ sung ràng buộc placement trên những range tương ứng.

| Tiêu chí | Range shard key có prefix region | Hashed shard key thuần |
|---|---|---|
| Định vị tất cả dataRegion=EU thành một miền liên tục | Thường dễ khi region ở prefix | Không tự nhiên nếu region không là thành phần prefix phù hợp |
| Query theo region | Có thể tận dụng prefix | Có thể phải scatter-gather tùy key |
| Phân bố insert đơn điệu | Có thể tạo hotspot nếu khóa không thiết kế tốt | Hashed có thể giúp phân tán theo giá trị hash |
| Zone theo region | Trực quan, dễ gắn khoảng | Cần cân nhắc khóa ghép và vùng hash thực tế |
| Truy vấn range theo khóa | Có thể phù hợp với range order | Hashed thường không phục vụ range theo giá trị gốc giống range key |

Một phương án kỹ thuật có thể kết hợp **region ở prefix** với trường còn lại thiết kế để tăng phân bố. Nhưng không được kết luận mọi kết hợp hashed/range đều được hỗ trợ và tối ưu như nhau: cần kiểm tra phiên bản MongoDB, tính năng compound hashed shard key, lệnh shardCollection và giới hạn zone bounds cụ thể.

### 15.1. Vì sao không chọn shard key chỉ vì muốn zone?

Shard key tốt phải cân bằng:

1. **Khả năng phân phối tải/ghi** trong mỗi zone.
2. **Khả năng target truy vấn** theo các pattern phổ biến.
3. **Cardinality** đủ lớn để chia dữ liệu.
4. **Chi phí thay đổi shard key** hoặc business field.
5. **Ràng buộc unique index** của collection.
6. **Yêu cầu residency và isolation**.
7. **Khả năng scale riêng từng region**.

Nếu dataRegion chỉ có ba giá trị và mọi order EU ghi dồn một chỗ, zone đúng vị trí vẫn có thể tạo một shard nóng. Cần xem cả **orderId/tenantId**, phân bố thực và kích thước chunk/range.

### 15.2. “Range theo quốc gia” có phải yêu cầu dùng chuỗi mã quốc gia?

Không nhất thiết. Mã vùng có thể là enum nghiệp vụ như **REG_EU**, **REG_APAC**, **REG_US**, hoặc numeric ID có thứ tự và miền giá trị rõ.

Điều quan trọng là:

- Kiểu BSON ổn định.
- Field bắt buộc và được validate.
- Mapping business policy → dataRegion có thể giải thích/audit.
- Những giá trị hợp lệ được zone ranges bao phủ.
- Khi thêm một mã vùng mới, quy trình cập nhật zone được làm **trước khi nhận dữ liệu mới** nếu yêu cầu placement nghiêm ngặt.

## 16. Unique index, khóa định danh và dữ liệu theo vùng

Trong sharded collection, ràng buộc uniqueness cần được thiết kế cùng shard key. Không thể giả định mọi unique index tùy ý đều được MongoDB cưỡng chế toàn cục theo mong muốn.

### 16.1. Unique index có shard key ở prefix

Nếu collection mới dùng:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

và quy tắc nghiệp vụ là **mỗi cặp (dataRegion, orderId) chỉ xuất hiện một lần**, có thể xem xét unique index:

~~~javascript
db.orders.createIndex(
  { dataRegion: 1, orderId: 1 },
  {
    unique: true,
    name: "uq_region_order"
  }
);
~~~

Với sharded collection, unique index thường cần **shard key là prefix**, theo những quy tắc được MongoDB hỗ trợ. Không nên tạo một index unique chỉ trên orderId rồi tự tin rằng cluster sẽ bảo đảm uniqueness toàn cục nếu orderId không phải shard-key prefix.

**Lưu ý thực hành:** đoạn trên minh họa lựa chọn **thiết kế index ngay từ đầu**. Nếu trước đó đã tạo index không unique trên cùng key pattern như phần 8, không nên chạy thêm một lệnh createIndex chỉ khác option unique rồi mong MongoDB tự chuyển đổi index. Cần chuẩn bị/migrate index đúng quy trình của phiên bản MongoDB.

### 16.2. Global orderId và regional orderId là hai bất biến khác nhau

Nếu nghiệp vụ yêu cầu:

~~~text
Trong EU:   EU-001 chỉ xuất hiện một lần.
Trong US:   EU-001 vẫn được phép trùng.
~~~

thì uniqueness của cặp **(dataRegion, orderId)** là hợp lý.

Nếu quy tắc là:

~~~text
orderId = O-123 phải duy nhất trong toàn bộ cluster,
bất kể dataRegion.
~~~

thì unique compound key theo region **không đủ về mặt logic**: nó cho phép cặp ("EU","O-123") và ("US","O-123") cùng tồn tại.

Có thể cần:

- Dịch vụ sinh ID bảo đảm uniqueness toàn cục.
- Registry business key có cơ chế uniqueness thích hợp.
- Thiết kế ID chứa thông tin vùng và điều kiện uniqueness theo hợp đồng.
- Xem xét lại shard key nếu truy vấn/định danh chủ yếu theo orderId toàn cục.

Đừng mặc định ObjectId tự sinh có thể được dùng thay cho **một ràng buộc nghiệp vụ tuyệt đối** trong mọi thiết kế sharded collection.

### 16.3. _id không luôn là unique constraint toàn cluster theo mong đợi

Trong những sharded collection có shard key **không bao gồm _id theo quy tắc thích hợp**, unique _id index có thể được thực thi **ở từng shard**; ứng dụng vẫn phải bảo đảm _id không xung đột toàn cluster theo thiết kế của mình.

Vì vậy, nếu API cho client tự đặt _id hoặc có nhiều dịch vụ sinh _id, cần phân tích uniqueness theo topology/shard key thay vì suy ra “MongoDB luôn cưỡng chế mọi _id là unique toàn cluster” cho mọi cấu hình sharding.

### 16.4. Nhận diện request trùng trong zone sharding

Một API tạo order trong vùng EU có thể nhận:

~~~json
{
  "dataRegion": "EU",
  "requestId": "R-100",
  "orderId": "EU-001"
}
~~~

Khi client retry cùng yêu cầu, backend cần sử dụng **cùng requestId** và không tạo order mới. Có thể đưa requestId vào một unique business index phù hợp với shard key, ví dụ tổ hợp **(dataRegion, requestId)** nếu shard key/collection được thiết kế để cho phép ràng buộc đó.

Không nên đưa các field vào unique index một cách tùy ý nếu quy tắc sharded unique index không cho phép. Nếu cần nhiều bất biến cùng lúc, có thể cần **collection registry riêng hoặc đổi mô hình định danh**.

## 17. Bắt buộc mã vùng và ngăn dữ liệu “lọt ra ngoài zone”

Zone range chỉ bao phủ những giá trị shard key đã được khai báo. Nếu ứng dụng cho phép dữ liệu:

~~~javascript
{ dataRegion: null, orderId: "X-1" }
{ orderId: "X-2" }
{ dataRegion: "eu", orderId: "X-3" }
{ dataRegion: "EU ", orderId: "X-4" }
{ dataRegion: "MARS", orderId: "X-5" }
~~~

thì các document đó có thể không nằm trong range dự kiến cho String **"EU"**, **"APAC"** hoặc **"US"**.

### 17.1. Schema validation

Ví dụ tạo **collection mới** chỉ cho phép ba mã vùng hợp lệ:

~~~javascript
use geo_orders

db.createCollection("validatedOrders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["dataRegion", "orderId", "tenantId"],
      properties: {
        dataRegion: {
          bsonType: "string",
          enum: ["EU", "APAC", "US"]
        },
        orderId: {
          bsonType: "string",
          minLength: 1
        },
        tenantId: {
          bsonType: "string",
          minLength: 1
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Validator ngăn một số document thiếu/sai kiểu vùng được insert hoặc update khi quy tắc validation áp dụng.

Tuy nhiên:

- Validator **không tự tạo zone range**.
- Validator **không xác minh shard membership**.
- Validator **không chọn region đúng với tenant**; nếu người dùng được phép gửi bất kỳ một trong ba mã, vẫn cần logic phân quyền/mapping.
- Collection mới **validatedOrders chưa tự được shard**; muốn zone sharding cho nó phải shard và cấu hình ranges riêng.

### 17.2. Mapping tenant → vùng phải được bảo vệ

Giả sử tenant có thuộc tính tin cậy:

~~~javascript
{
  tenantId: "T-EU-001",
  allowedDataRegion: "EU"
}
~~~

Backend không nên cho request tạo order với tenantId này và dataRegion = "US" chỉ vì US có trong enum. Cần xác thực caller, tra cứu chính sách, xác định dataRegion, rồi ghi document.

Với API nhiều vùng, có thể áp dụng:

~~~text
Auth principal
      |
      v
Resolve tenantId đáng tin cậy
      |
      v
Load tenant residency policy
      |
      v
Determine dataRegion
      |
      v
Validate allowed value
      |
      v
Insert document có shard key phù hợp
~~~

Nếu policy hoặc region thay đổi, cần kiểm soát phiên bản và transaction/workflow thay vì để những request đồng thời ghi dataRegion khác nhau cho cùng tenant mà không nhận biết.

### 17.3. Không dùng mỗi collation để sửa lỗi mã vùng

Chuỗi "EU", "eu" và "EU " phải được chuẩn hóa từ đầu theo hợp đồng. Đừng kỳ vọng collation case-insensitive trên một truy vấn bất kỳ sẽ khiến zone range cho "EU" tự động bao phủ mọi biến thể. Zone range phụ thuộc thứ tự giá trị shard key, không phải phép chuẩn hóa tùy ý của ứng dụng.

### 17.4. Mã vùng mới phải có quy trình rollout

Giả sử doanh nghiệp bổ sung region **LATAM**. Trước khi API ghi dữ liệu LATAM:

1. Chuẩn bị shard vật lý và replication đúng vị trí.
2. Gắn các shard đó vào **ZONE_LATAM**.
3. Thêm range cho dataRegion = "LATAM" ở từng namespace liên quan.
4. Xác minh range không overlap, balancer và capacity.
5. Cập nhật validator/tenant policy.
6. Chỉ sau đó mở quyền tạo dữ liệu mới.

Nếu phát hành code chấp nhận LATAM trước rồi mới tạo zone, có cửa sổ thời gian mà document LATAM không được ràng buộc placement.

## 18. Khi zone thiếu shard hoặc shard đầy

### 18.1. Zone không còn shard thành viên

Nếu một zone range đã được gán nhưng zone không có shard đủ điều kiện để nhận dữ liệu, balancer không thể đưa mọi range vào vị trí mong muốn. Tùy hành động, phiên bản và trạng thái cluster, lệnh cấu hình hoặc hoạt động liên quan có thể bị từ chối, chờ, hoặc báo lỗi.

Không nên viết logic ứng dụng giả định **“nếu ZONE_EU không còn shard, MongoDB sẽ tự đưa EU sang bất kỳ shard US nào để tiếp tục phục vụ”**. Một fallback như vậy trái với mục đích zone constraint và không phải hợp đồng an toàn để dựa vào.

### 18.2. Hết dung lượng trong một zone

~~~text
ZONE_EU: shardEU1 95% disk, shardEU2 94% disk
ZONE_US: shardUS1 20% disk
~~~

Nếu EU chỉ được đặt trong ZONE_EU, capacity thừa của shardUS1 không tự giải quyết giới hạn EU. Muốn tăng capacity cho EU, cần:

- Mở rộng storage/tài nguyên các shard EU.
- Thêm shard phù hợp vào zone EU.
- Điều chỉnh shard key và phân bố hotspots nếu cần.
- Đánh giá quy trình phân vùng dữ liệu hoặc retention theo chính sách.

Đừng mở rộng zone membership sang shard US chỉ để “hết lỗi disk” nếu điều đó vi phạm ràng buộc dữ liệu.

### 18.3. Jumbo range hoặc range khó chia

Một lượng dữ liệu lớn có cùng giá trị shard key hoặc phân bố rất lệch có thể tạo các range khó di chuyển/chia trong điều kiện nhất định. Với shard key chỉ gồm region và region có ít giá trị, một region cực lớn có thể trở thành điểm nghẽn.

Thiết kế shard key ghép có thêm orderId/tenantId hợp lý có thể tăng cardinality, nhưng cũng cần xem xét các giá trị đơn điệu, mối quan hệ với query pattern và hành vi balancer của phiên bản triển khai.

### 18.4. Sự cố một region và yêu cầu availability

Nếu các shard của EU đều ở EU và EU gặp sự cố hạ tầng diện rộng, dữ liệu EU có thể tạm thời không phục vụ được. Đây là một đánh đổi:

~~~text
Strict geographic placement
             |
             v
Không cho copy EU ra ngoài vùng
             |
             v
Khả năng phục hồi xuyên vùng bị giới hạn
             |
             v
Cần thiết kế DR trong phạm vi được phép
~~~

Một chính sách residency nghiêm ngặt có thể giới hạn các phương án disaster recovery. Cần thỏa thuận yêu cầu **RPO/RTO, nơi đặt secondary/backup và phương án khôi phục** trước khi xảy ra sự cố, thay vì tự động sao chép sang vùng không được phép.

## 19. Zone và hashed shard key: những giới hạn thiết kế thực tế

Giả sử hệ thống muốn vừa phân vùng theo country vừa phân tán dữ liệu đồng đều:

~~~javascript
{
  country: 1,
  customerId: "hashed"
}
~~~

Một compound hashed shard key như vậy có thể hữu ích trong những phiên bản hỗ trợ, vì country ở prefix cho phép nhóm theo miền địa lý còn phần hashed có thể hỗ trợ phân tán trong miền. Tuy nhiên:

- Không được thay đổi shard key một cách tùy tiện trên collection đang có dữ liệu.
- Hãy kiểm tra **phiên bản server** và các quy tắc index/shardCollection cho compound hashed key.
- Zone range phải phù hợp **thứ tự shard key thực tế**, không phải trường plaintext khi nó được băm.
- Khả năng query targeting và unique indexes có ràng buộc riêng.

Đặc biệt, không nên viết:

~~~javascript
{ customerId: "hashed" }
~~~

và mong MongoDB có thể suy ra một range liên tục chứa mọi customerId thuộc country = "EU" khi country chỉ là field phụ không nằm trong shard key.

### 19.1. Shard key theo thời gian thay vì vùng

Nếu shard key là:

~~~javascript
{ createdAt: 1, orderId: 1 }
~~~

thì các document EU và US được xen theo createdAt. Không có cách trực tiếp gắn **toàn bộ EU** vào một zone chỉ bằng một khoảng createdAt khi country không thuộc khóa.

Zone range có thể dùng để tách **dữ liệu nóng/lạnh theo thời gian** nếu đó là yêu cầu; nhưng đây là bài toán placement khác với geographic residency. Đừng nhầm **zone hot/cold storage** với **zone dữ liệu theo quốc gia**.

### 19.2. Không cần mọi collection phải có cùng shard key

Collection đơn hàng, customers và analytics có query patterns khác nhau. Tuy nhiên, nếu cùng yêu cầu residency theo region, chúng cần một chiến lược phối hợp:

- Mỗi collection có shard key hỗ trợ zone theo region.
- Hoặc tách dữ liệu theo các database/cluster riêng.
- Hoặc giới hạn rõ dữ liệu nào được phép được tổng hợp sang nơi khác.

Nếu một collection dùng shard key không thể diễn đạt vùng, nó có thể trở thành lỗ hổng trong bản thiết kế residency mặc dù collection chính đã zone-sharded tốt.

## 20. Java MongoDB Sync Driver: ghi đúng shard key và truy vấn đúng vùng

Ứng dụng Java thông thường **không gọi sh.updateZoneKeyRange khi xử lý từng request**. Quản trị cluster chịu trách nhiệm cấu hình zone và balancer; backend chịu trách nhiệm gửi document với **shard key đúng**, bảo đảm dữ liệu hợp lệ và sử dụng filter có thể target.

Trong ví dụ dưới đây:

- MongoDB cluster đã được shard bằng **{dataRegion:1,orderId:1}**.
- Đã có zone range EU/APAC/US như các phần trên.
- Ứng dụng có dependency **mongodb-driver-sync** và biến môi trường **MONGODB_URI** trỏ đến mongos.
- Region được lấy từ **chính sách đáng tin cậy** ở backend, không sao chép trực tiếp từ header của người dùng.

### 20.1. Ghi document có đầy đủ shard key

~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Map;
import java.util.Set;
import java.util.UUID;

public class ZonedOrderWriteDemo {
    // Demo: thay bằng policy service/tenant registry có kiểm soát
    // trong hệ thống thật.
    private static final Map<String, String> TENANT_REGION = Map.of(
            "TENANT-EU-A", "EU",
            "TENANT-AP-A", "APAC",
            "TENANT-US-A", "US"
    );

    private static final Set<String> ALLOWED =
            Set.of("EU", "APAC", "US");

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        String tenantId = "TENANT-EU-A";
        String dataRegion = TENANT_REGION.get(tenantId);

        if (dataRegion == null || !ALLOWED.contains(dataRegion)) {
            throw new IllegalArgumentException(
                    "Tenant has no validated data region");
        }

        String orderId = UUID.randomUUID().toString();

        Document order = new Document("dataRegion", dataRegion)
                .append("orderId", orderId)
                .append("tenantId", tenantId)
                .append("status", "CREATED")
                .append("amountCents", 12500L);

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("geo_orders")
                    .getCollection("orders")
                    .withWriteConcern(WriteConcern.MAJORITY);

            orders.insertOne(order);
            System.out.println("Created order " + orderId);
        }
    }
}
~~~

Code có các đặc điểm:

1. **dataRegion** được quyết định từ tenant policy do backend kiểm soát.
2. **orderId** phân biệt document trong region.
3. Insert chứa đầy đủ shard key.
4. Driver gửi lệnh đến mongos; mongos dùng metadata sharding để định tuyến.
5. **WriteConcern.MAJORITY** nói về mức xác nhận ghi, không tự xác minh shard đang ở quốc gia nào.

Đoạn code tạo một order mới mỗi lần chạy để minh họa insert. Trong API có retry, cần thêm **business requestId và idempotency** để tránh tạo trùng đơn khi mạng bị ngắt.

### 20.2. Đọc với filter chứa shard key

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ZonedOrderRead {
    public static Document findOrder(
            MongoCollection<Document> orders,
            String dataRegion,
            String orderId) {

        Bson filter = Filters.and(
                Filters.eq("dataRegion", dataRegion),
                Filters.eq("orderId", orderId)
        );

        return orders.find(filter).first();
    }
}
~~~

Filter đi từ region đến orderId theo shard-key pattern. Nó giúp mongos xác định phạm vi range có thể liên quan; không cần tạo riêng kết nối Java tới shardEU1 hoặc shardAP1 để “định tuyến thủ công”.

**Không nối trực tiếp vào shard replica set cho các thao tác ứng dụng thông thường trên sharded collection** nhằm né mongos. Router cần quản lý metadata, định tuyến, migration và các quy tắc sharding.

### 20.3. Đếm đơn theo region

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class ZonedOrderCount {
    public static long countByRegion(
            MongoCollection<Document> orders,
            String region) {

        return orders.countDocuments(
                Filters.eq("dataRegion", region)
        );
    }
}
~~~

Đếm theo dataRegion có thể chạm nhiều shard trong cùng zone nếu region được chia thành nhiều range. Đây vẫn có thể là thiết kế hợp lý: zone xác định **nhóm shard được phép**, không ép mọi query vùng chỉ cần một shard.

### 20.4. Explain qua Java

~~~java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class ZonedOrderExplain {
    public static Document explainByRegionAndId(
            MongoCollection<Document> orders,
            String region,
            String orderId) {

        return orders.find(
                Filters.and(
                        Filters.eq("dataRegion", region),
                        Filters.eq("orderId", orderId)
                )
        ).explain(ExplainVerbosity.QUERY_PLANNER);
    }
}
~~~

Kết quả explain giúp đánh giá mức độ target shard và index. Không dùng một lần explain như bằng chứng duy nhất rằng **mọi bản sao vật lý** đều ở đúng khu vực.

### 20.5. Update với shard key đủ cụ thể

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class ZonedOrderUpdate {
    public static boolean markPaid(
            MongoCollection<Document> orders,
            String dataRegion,
            String orderId) {

        UpdateResult result = orders.updateOne(
                Filters.and(
                        Filters.eq("dataRegion", dataRegion),
                        Filters.eq("orderId", orderId),
                        Filters.eq("status", "CREATED")
                ),
                Updates.set("status", "PAID")
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

Điều kiện **status = CREATED** giúp thao tác cập nhật có điều kiện trên document, tránh ghi đè trạng thái đã thay đổi. Không cho client tự thay **dataRegion** khi chỉ đang cập nhật status thanh toán.

## 21. Spring Data MongoDB: giữ region trong Query và Criteria

Trong Spring Data MongoDB, **MongoTemplate** có thể thực hiện các truy vấn với shard-key field mà không cần ứng dụng biết shard cụ thể.

### 21.1. Truy vấn bằng MongoTemplate

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderLookupService {
    private final MongoTemplate mongoTemplate;

    public OrderLookupService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document findByRegionAndOrderId(
            String dataRegion,
            String orderId) {

        Query query = Query.query(
                Criteria.where("dataRegion").is(dataRegion)
                        .and("orderId").is(orderId)
        );

        return mongoTemplate.findOne(
                query,
                Document.class,
                "orders"
        );
    }
}
~~~

Backend nên cung cấp dataRegion từ tenant policy đáng tin cậy, không để một caller chỉ cần chọn một vùng khác rồi đọc đơn hàng của tenant khác.

### 21.2. Tạo document với region đã xác minh

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class OrderCreationService {
    private final MongoTemplate mongoTemplate;

    public OrderCreationService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document create(
            String trustedRegion,
            String tenantId,
            String orderId) {

        Document order = new Document("dataRegion", trustedRegion)
                .append("tenantId", tenantId)
                .append("orderId", orderId)
                .append("status", "CREATED");

        return mongoTemplate.insert(order, "orders");
    }
}
~~~

Ví dụ chỉ minh họa thao tác ghi. Trong hệ thống thực, cần validate vùng, quyền caller, key duy nhất, idempotency và các cấu hình write concern phù hợp. Cũng cần bảo đảm MongoTemplate đang kết nối **mongos** đúng cluster đã zone-sharded.

### 21.3. Annotation entity không tự thiết lập zone

Ngay cả khi Spring Data model đánh dấu những field như dataRegion/orderId và có annotation index, điều đó **không tự sinh ra zone membership và zone ranges của cluster**.

Zone là phần của **cluster administration** và cần được khai báo/giám sát qua công cụ MongoDB phù hợp. Application migration có thể phối hợp việc tạo index/sharding theo quy trình DevOps, nhưng không nên để mọi instance API đồng thời gọi sh.addShardToZone khi startup.

### 21.4. Tránh tạo API nhận region tùy ý

Không nên tin tuyệt đối:

~~~http
GET /orders/O-123?dataRegion=EU
~~~

Chỉ vì client gửi "EU". Trong kiến trúc đa tenant, service cần:

1. Xác thực caller.
2. Xác định tenant/authorization scope.
3. Tra cứu mapping tenant → vùng hoặc chính sách theo từng document.
4. Dùng dataRegion đã xác minh làm filter.
5. Kiểm tra tài liệu kết quả thực sự thuộc tenant đã được phép.

**Zone sharding giải quyết placement, không thay authorization**.

## 22. Transaction xuyên shard và xuyên vùng

MongoDB hỗ trợ transaction trên nhiều shard trong những deployment/version phù hợp, nhưng các thao tác cross-shard có thể phức tạp và tốn tài nguyên hơn thao tác target đúng một shard.

Giả sử một transaction vừa cập nhật order EU vừa cập nhật payment US:

~~~text
Transaction
    |
    +-- EU shard: update order
    |
    +-- US shard: insert payment
    |
    +-- coordination / commit
~~~

Hệ thống có thể cần phối hợp nhiều shard và truyền dữ liệu qua mạng. Zone sharding **không tự cấm** một ứng dụng có quyền thực hiện transaction cross-region.

### 22.1. Khi nào nên tránh cross-zone transaction?

- Khi yêu cầu residency không cho phép truyền dữ liệu thô vượt vùng.
- Khi luồng nghiệp vụ có tần suất rất cao, cần latency thấp và ít contention.
- Khi một vùng gặp sự cố sẽ làm toàn bộ transaction không thể hoàn tất.
- Khi dữ liệu có thể được tổ chức để một đơn vị nghiệp vụ nằm trong một shard/zone phù hợp.

Không nên cố gắng ép mọi nghiệp vụ về một shard nếu điều đó phá vỡ khả năng scale. Cần cân bằng **atomicity, latency, isolation, data location và tính sẵn sàng**.

### 22.2. Colocation theo region giúp gì?

Nếu order, payment và inventory đều có dataRegion phù hợp và các query cung cấp shard key đúng, có thể giảm phạm vi shard tham gia một số thao tác. Tuy nhiên, **cùng zone không đồng nghĩa cùng shard**: ZONE_EU có thể có nhiều shard và mỗi collection có cách phân bố range khác nhau.

Do đó, nếu cần bảo đảm hai document nằm cùng shard để tối ưu transaction, chỉ có zone chung là **chưa đủ**. Phải xem shard key, mapping range và chiến lược thiết kế dữ liệu.

## 23. Quy trình triển khai zone sharding an toàn

Một thay đổi zone có thể ảnh hưởng tới dung lượng shard, độ trễ mạng, tính sẵn sàng và việc tuân thủ vị trí dữ liệu. Vì vậy, với hệ thống thật cần một **runbook có các điều kiện chấp nhận rõ ràng**, không chỉ một tập lệnh mongosh.

### 23.1. Giai đoạn 1 — Thu thập yêu cầu

Xác định:

- Collection nào có dữ liệu cần ràng buộc vị trí.
- Có bao nhiêu vùng: EU, APAC, US hay vùng theo chính sách riêng.
- Vùng được xác định từ tenant, document, nơi cư trú hay nghiệp vụ nào.
- Có dữ liệu phải ở **một quốc gia**, một khu vực cloud hay một nhóm máy riêng không.
- Có yêu cầu đối với **replication, backup, logs, audit, export, search indexes** không.
- Có yêu cầu **RPO/RTO** khi một region mất kết nối không.
- Query pattern nào phải chạy thường xuyên và cần latency bao nhiêu.

Ví dụ một ma trận chính sách:

| Data class | Region key | Allowed zone | Backup constraint | Query scope |
|---|---|---|---|---|
| EU customer order | dataRegion=EU | ZONE_EU | Chỉ vùng được phê duyệt | Thường theo EU + tenant |
| APAC customer order | dataRegion=APAC | ZONE_APAC | Chỉ vùng được phê duyệt | Thường theo APAC + tenant |
| Global aggregate | Có thể là dữ liệu đã tổng hợp | Theo chính sách riêng | Kiểm tra được phép tổng hợp xuyên vùng | Có thể cross-zone |

Bảng chỉ là ví dụ kỹ thuật; các điều kiện pháp lý/thương mại cần được tổ chức có thẩm quyền xác nhận.

### 23.2. Giai đoạn 2 — Thiết kế shard key

Với collection orders, xem xét:

~~~javascript
{ dataRegion: 1, tenantId: 1, orderId: 1 }
~~~

Câu hỏi cần trả lời:

1. Có thể tạo zone range bao phủ chính xác từng region không?
2. Với mỗi region có đủ giá trị khác nhau để chia range không?
3. API quan trọng có luôn biết dataRegion/tenantId không?
4. Unique business key có phù hợp với shard key và các quy tắc index không?
5. Một tenant lớn có tạo hotspot không?
6. Nếu đổi region của tenant, cần migration theo cách nào?

Nếu shard key không hỗ trợ những yêu cầu này, **sửa thiết kế trước khi ghi hàng tỷ document** thường dễ hơn đổi sau.

### 23.3. Giai đoạn 3 — Chuẩn bị hạ tầng

- Xác minh những shard đã được triển khai đúng physical/cloud region.
- Kiểm tra vị trí của **từng replica set member**.
- Kiểm tra capacity theo lượng dữ liệu dự kiến của từng zone.
- Kiểm tra backup/PITR và DR.
- Bảo đảm quyền quản trị zone phù hợp.
- Xác nhận công cụ quan sát balancer/migrations hoạt động.
- Xây dựng điều kiện rollback hoặc dừng rollout.

Không đặt shard vật lý vào zone chỉ dựa trên tên máy; cần chứng cứ về nơi đặt storage và replication.

### 23.4. Giai đoạn 4 — Chuẩn bị index và zone

Với collection rỗng, một quy trình điển hình theo phiên bản hỗ trợ:

~~~text
Create/verify shards
        |
        v
Add shard membership to zones
        |
        v
Define non-overlapping zone ranges
        |
        v
Create shard-key index / shard collection
        |
        v
Insert representative test data
        |
        v
Observe chunk/range placement
~~~

Với collection đã có dữ liệu, thứ tự sẽ cần tính đến hiện trạng sharding và việc balancer phải di chuyển range. Không sao chép quy trình dành cho collection rỗng vào hệ thống đang mang tải lớn mà không đánh giá migrations.

### 23.5. Giai đoạn 5 — Chặn dữ liệu ngoài miền hợp lệ

Trước khi mở traffic:

- Validator yêu cầu dataRegion tồn tại và nằm trong enum hợp lệ.
- Backend xác thực tenant/region mapping.
- Các code path importer, batch, admin scripts cũng phải tuân theo chính sách.
- Không có giá trị **UNKNOWN**, null hoặc dữ liệu sai kiểu bị đưa vào unzoned range khi chính sách cấm.
- Có quy tắc xử lý mã vùng mới trong tương lai.

Chỉ một API chính được sửa chưa đủ nếu còn worker/importer khác có quyền insert document không hợp lệ.

### 23.6. Giai đoạn 6 — Theo dõi hội tụ placement

Sau khi cấu hình:

1. Xem zone membership.
2. Xem zone ranges của namespace.
3. Đối chiếu range ownership trên shard.
4. Xác minh balancer đang hoạt động và không có lỗi migration.
5. Theo dõi shard capacity/network I/O.
6. Chờ quá trình dọn dữ liệu cũ khi có migration.
7. Kiểm tra snapshot/backup và các luồng phụ.

Nếu chưa hội tụ, chỉ ghi nhận **“zone policy đã khai báo”**, không ghi nhận **“mọi dữ liệu đã được chuyển xong”**.

### 23.7. Giai đoạn 7 — Kiểm thử đường ứng dụng

Chạy những query đại diện:

~~~javascript
db.orders.find({
  dataRegion: "EU",
  tenantId: "TENANT-EU-A",
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

Và một query thiếu prefix:

~~~javascript
db.orders.find({
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

So phạm vi shard được target, latency, index plans và lượng dữ liệu được trả. Một thiết kế residency đúng nhưng khiến toàn bộ API phải scatter-gather có thể không đạt yêu cầu vận hành.

### 23.8. Giai đoạn 8 — Nghiệm thu và giám sát định kỳ

Không chỉ kiểm tra một lần khi deploy. Cần giám sát:

- Có shard nào được thêm vào zone ngoài quy trình không.
- Có zone range mới chồng lấn hoặc bị thiếu không.
- Có shard thuộc zone bị loại bỏ hay không còn capacity không.
- Có collection mới được tạo mà quên cấu hình zone không.
- Có dữ liệu mang mã region chưa được phê duyệt không.
- Có thay đổi backup/replica placement sau failover hoặc DR không.

Một quy trình nghiệm thu tốt ghi rõ **ai chịu trách nhiệm cho từng kiểm tra**, bằng chứng nào được lưu và trường hợp nào phải dừng rollout.

## 24. Quan sát, monitoring và cảnh báo

Một hệ thống có zone sharding nên có metric và cảnh báo riêng cho placement, không chỉ CPU và latency.

### 24.1. Các metric hữu ích

| Metric/quan sát | Mục đích |
|---|---|
| Zone membership snapshot | Phát hiện shard được thêm/gỡ sai chính sách |
| Zone range snapshot | Phát hiện gap, overlap hoặc namespace thiếu cấu hình |
| Non-compliant range placement | Tìm range hiện ở shard không thuộc zone yêu cầu |
| Balancer status/history | Phát hiện balancing dừng, lỗi hoặc kéo dài |
| Migration duration/failures | Đo chi phí chuyển dữ liệu và sự cố |
| Per-zone disk usage | Phát hiện zone sắp hết dung lượng |
| Per-shard write/read latency | Nhận biết một shard nóng |
| Scatter-gather query ratio | Phát hiện API không truyền shard-key prefix |
| Unknown/invalid dataRegion count | Tìm dữ liệu nằm ngoài miền đã định nghĩa |
| New namespace without zone policy | Phát hiện collection mới chưa có residency design |
| Backup/replica location inventory | Phục vụ bằng chứng về nơi có bản sao dữ liệu |

Các tên trên là **chỉ số quan sát được đề xuất**, không phải danh sách metric mặc định MongoDB luôn xuất ra nguyên tên.

### 24.2. Alert khi shard thuộc zone quá tải

Ví dụ ngưỡng cảnh báo được doanh nghiệp xác định:

~~~text
ZONE_EU:
  shardEU1 disk utilization > threshold
  shardEU2 disk utilization > threshold

Action:
  - Kiểm tra tăng trưởng và workload
  - Mở rộng capacity trong vùng được phép
  - Kiểm tra shard key/hotspot
  - Không tự chuyển EU sang shard US
~~~

Ngưỡng chính xác cần dựa trên cấu hình storage, headroom cho migration, tải ghi và khả năng mở rộng của hạ tầng.

### 24.3. Alert khi dataRegion không được bao phủ

Giả sử application telemetry phát hiện dataRegion = "LATAM", nhưng cluster chỉ có zone EU/APAC/US. Đây nên là tín hiệu cần xử lý trước khi tiếp tục lưu dữ liệu nhạy cảm:

~~~text
Invalid / unapproved region value
           |
           v
Reject or quarantine by policy
           |
           v
Review tenant-region mapping
           |
           v
Provision new zone if authorized
~~~

Không nên tự động gán mọi mã vùng chưa biết vào ZONE_US chỉ vì đó là zone có nhiều capacity.

### 24.4. Lưu nhật ký thay đổi cấu hình zone

Với mỗi lần thay đổi, nên ghi:

- Người/phần mềm thực hiện và phê duyệt.
- Namespace và zone name.
- Shard membership trước/sau.
- Range bounds trước/sau.
- Thời điểm cấu hình.
- Tình trạng balancer/migration khi nghiệm thu.
- Link tới báo cáo inventory replica, backup và region.

Audit thay đổi zone hỗ trợ điều tra vì sao dữ liệu xuất hiện tại vị trí ngoài dự kiến và ai đã phê duyệt hành động.

## 25. Tình huống sự cố thường gặp

### 25.1. Đã tạo zone nhưng EU document vẫn ở shard APAC

Khả năng:

- Lệnh sh.updateZoneKeyRange chưa được chạy cho đúng namespace.
- Các range EU tồn tại trước zone; balancer chưa di chuyển xong.
- Balancer bị dừng hoặc migration lỗi.
- Shard APAC cũng được gắn nhầm vào ZONE_EU.
- Thao tác đọc metadata và danh tính shard chưa được đối chiếu đúng.

**Hướng điều tra:** xác minh membership, range mapping, balancer, current range owners và lịch sử migration. Không tự xóa document trên donor shard bằng một lệnh deleteMany.

### 25.2. Dữ liệu mới region "EU " lọt sang zone khác

Nguyên nhân: chuỗi có dấu cách khác **"EU"** và không nằm trong khoảng được kỳ vọng. Biện pháp: chuẩn hóa và validate ở API cùng schema. Không sửa bằng cách mở rộng zone range quá rộng để bao gồm vô tình mọi mã gần giống nhau.

### 25.3. Query theo orderId chậm sau khi bật sharding

Nếu shard key bắt đầu bằng dataRegion và API chỉ tìm theo orderId, mongos có thể phải hỏi nhiều shard. Cần thay đổi hợp đồng API để biết region, thêm mapping service phù hợp hoặc xem lại shard key.

**Không nên kết luận lỗi do zone sharding** nếu bản chất là query không có shard-key prefix.

### 25.4. Zone EU đầy còn US vẫn rảnh

Đây là đặc tính của partition theo zone, không nhất thiết là balancer hỏng. Balancer không nên phá ràng buộc EU để “cân bằng toàn cluster”. Cần tăng capacity zone EU hoặc điều chỉnh workload trong phạm vi được phép.

### 25.5. Collection mới chứa dữ liệu EU nhưng không có zone

Ví dụ một team tạo **geo_orders.orderAuditEvents** và shard theo createdAt mà không có region. Collection mới không tự kế thừa zone range của orders. Cần chuẩn hóa quy trình tạo collection và kiểm kê namespace, không chỉ kiểm tra collection chính.

### 25.6. Migration hoàn tất nhưng backup cũ vẫn ở vùng khác

Zone placement mới không xóa được snapshot lịch sử. Đây là vấn đề retention/backup/compliance phải xử lý theo quy trình. Không kết luận có thể xóa backup ngay nếu chính sách phục hồi hoặc pháp lý yêu cầu giữ lại.

### 25.7. Zone có nhiều shard nhưng document chưa phân bố đều

Có thể do shard key không đủ phân biệt, dữ liệu skew, range chưa chia phù hợp, balancer chưa xử lý hoặc thiếu capacity. Cần dùng thống kê per-shard và explain/metrics, không mặc định thêm zone name giải quyết skew.

### 25.8. Sau khi đổi homeRegion, tenant vẫn có dữ liệu ở vùng cũ

Việc cập nhật một field cấu hình tenant không tự di chuyển mọi collection nghiệp vụ và backup. Cần migration có inventory, phạm vi lịch sử, kiểm chứng range ownership và luồng read/write trong lúc chuyển đổi.

### 25.9. Transaction cross-zone có latency tăng

Một workflow vô tình cập nhật dữ liệu của nhiều region có thể kích hoạt giao tiếp xuyên shard/vùng. Cần xem lại yêu cầu nghiệp vụ, filter shard key, transaction boundaries và vị trí service. Không dùng zone để hứa “cùng tên zone = cùng shard”.

### 25.10. Không thêm được unique index mong muốn

Trên sharded collection, unique index có ràng buộc với shard key và trạng thái dữ liệu hiện có. Một index chỉ trên orderId có thể không hợp lệ để bảo đảm uniqueness toàn cluster theo shard key đang dùng. Cần xem lại business ID model và migration, không bỏ ràng buộc rồi dựa vào check-before-insert.

## 26. Zone sharding hay tách cluster theo region?

Zone sharding là một công cụ mạnh, nhưng không phải thiết kế duy nhất để phân vùng dữ liệu. Khi dữ liệu bị ràng buộc chặt về vị trí, cần so sánh với các mô hình khác.

| Tiêu chí | Một sharded cluster nhiều zone | Cluster riêng cho từng region |
|---|---|---|
| Số cụm MongoDB | Một cluster logic, nhiều shard/zone | Nhiều cluster độc lập |
| Metadata/router | Có các thành phần cluster chung | Mỗi cluster có control plane/metadata riêng |
| Placement theo shard key | Zone ranges và balancer | Application routing đến cluster tương ứng |
| Nguy cơ truy vấn xuyên vùng | Có nếu query chạm nhiều shard/zone | Cần tầng ứng dụng phối hợp nếu muốn cross-region |
| Cách ly vận hành | Một số tài nguyên và thay đổi có thể chung | Phân tách rõ hơn theo cluster |
| Transaction xuyên vùng | Có cơ chế sharded transaction theo điều kiện hỗ trợ, nhưng tốn chi phí | Không có transaction MongoDB đơn giản xuyên cluster độc lập |
| Residency nghiêm ngặt | Cần kiểm tra toàn bộ replica/backup/metadata/process | Cần kiểm tra mọi thành phần của từng cluster, nhưng phạm vi có thể rõ hơn |
| Scale theo region | Thêm shard vào zone có thể giúp mở rộng | Scale từng cluster độc lập |
| Quản lý ứng dụng | Một kết nối sharded cluster, shard key quan trọng | Nhiều kết nối, routing và data ownership phức tạp hơn |
| Blast radius | Một số thay đổi control plane có thể ảnh hưởng nhiều zone | Có thể giảm ảnh hưởng chung, nhưng vận hành nhiều cluster hơn |

**Không có lựa chọn tốt nhất cho mọi hệ thống.** Một cluster nhiều zone phù hợp khi các vùng có thể chia sẻ một hệ thống sharding chung và được phép có những thành phần cluster chung. Cluster tách biệt có thể phù hợp hơn khi cần boundary vận hành/bảo mật rõ ràng và khó chấp nhận một số chia sẻ metadata hoặc luồng xử lý.

### 26.1. Zone sharding cho nhóm tài nguyên nóng/lạnh

Zone không chỉ dùng cho địa lý. Có thể đặt các range theo **thời gian, hạng tenant hoặc loại workload** lên những nhóm shard có phần cứng khác nhau, nếu shard key có cấu trúc phù hợp.

Ví dụ:

~~~text
ZONE_HOT:
  Shard có storage/CPU phù hợp workload hiện tại

ZONE_ARCHIVE:
  Shard phục vụ dữ liệu cũ, truy cập ít hơn
~~~

Tuy nhiên, nếu gắn zone theo createdAt và dữ liệu của một document chuyển từ “hot” sang “archive” theo thời gian, cần hiểu cách thay đổi range placement và điều kiện update; không thể chỉ đổi nhãn zone rồi mặc định mọi dữ liệu tự ổn định ngay.

### 26.2. Không nhầm zone với read preference theo latency

Read preference giúp chọn **node replica** để phục vụ read trong phạm vi shard đã được target, không phải thay shard key hay range owner. Dù ứng dụng đặt **readPreference nearest**, mongos vẫn cần đưa query tới shard chứa range phù hợp.

Nếu EU data được zone-shard về EU nhưng primary application đặt ở APAC, vẫn có chi phí mạng. Zone không tự định tuyến người dùng đến một deployment frontend thích hợp.

### 26.3. Một ma trận quyết định

Chọn zone sharding khi:

- Các region có thể dùng chung sharded cluster theo chính sách được duyệt.
- Shard key có thể chứa thuộc tính định vị cần thiết.
- Có nhu cầu phân bố tải trong một region trên nhiều shard.
- Quản trị viên có thể kiểm soát placement, replication, backup và migration theo zone.
- Ứng dụng có thể gửi query với shard-key prefix thường xuyên.

Cân nhắc cluster riêng khi:

- Yêu cầu tách biệt control plane/metadata hoặc cách ly vận hành rất cao.
- Chính sách không cho phép một số thành phần dữ liệu/backup/logs được dùng chung.
- Các region có quy trình vận hành/phiên bản/chu kỳ thay đổi độc lập.
- Phần lớn query là nội vùng và có thể route đến cluster riêng ở tầng ứng dụng.
- Chi phí của routing đa cluster chấp nhận được.

Có thể kết hợp hai cách: một số vùng dùng cluster riêng, bên trong mỗi cluster vẫn dùng sharding và zone cho workload đặc biệt.

## 27. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Gắn tên ZONE_EU cho một shard đặt ngoài EU | Sai ràng buộc địa lý thực tế | Kiểm chứng hạ tầng/replica placement |
| Chỉ cấu hình membership mà không gắn range | Zone chưa quản lý giá trị shard key nào | Dùng sh.updateZoneKeyRange theo namespace |
| Chỉ gắn range mà không có shard đủ điều kiện | Balancer không có nơi placement hợp lệ | Chuẩn bị zone member/capacity trước |
| Cho một shard vào cả EU và US dù cần cách ly | Shard được phép nhận cả hai nhóm | Kiểm tra membership và chính sách isolation |
| Chọn shard key không chứa region khi cần zone theo region | Không diễn đạt được range phù hợp | Thiết kế shard-key prefix theo yêu cầu |
| Chỉ dùng {region:1} khi có rất ít giá trị | Cardinality thấp, khó phân bố tải | Xem compound key với orderId/tenantId |
| Gắn zone range với min/max sai thứ tự | Lỗi cấu hình hoặc khoảng sai | Dùng đầy đủ shard-key fields và sentinel hợp lệ |
| Chồng lấn hai zone range | Mâu thuẫn placement | Thiết kế khoảng không chồng lấn |
| Không tính khoảng [min,max) | Bản ghi tại max không nằm trong range | Dùng biên đúng và kiểm tra giá trị boundary |
| Cho phép region UNKNOWN/null | Dữ liệu có thể vào unzoned range | Schema validation và policy mapping |
| Chấp nhận region do client tự khai | Khách hàng có thể chọn vị trí sai | Resolve từ nguồn tin cậy và authorize |
| Kết luận lệnh zone thành công là di chuyển xong | Residency chưa hội tụ | Theo dõi balancer và placement |
| Tắt balancer nhưng chờ tự di chuyển | Range có thể ở shard cũ | Vận hành balancer theo quy trình |
| Chỉ kiểm tra primary nằm trong vùng | Secondary có thể chứa bản sao ngoài vùng | Kiểm kê toàn bộ replica members |
| Quên backups/exports | Dữ liệu vẫn tồn tại ở nơi ngoài vùng | Kiểm soát toàn bộ data lifecycle |
| Cho rằng cùng zone nghĩa là cùng shard | Transaction/query vẫn có thể cross-shard | Thiết kế shard key và range cụ thể |
| Truy vấn chỉ theo orderId | Mongos có thể scatter-gather | Truyền shard-key prefix hoặc có mapping |
| Thêm shard US để chữa EU đầy | Có thể vi phạm residency | Scale capacity trong zone được phép |
| Gỡ shard cuối khỏi zone | Mất nơi placement hợp lệ | Chuẩn bị replacement trước |
| Thay homeRegion bằng update tùy tiện | Dữ liệu cũ, backup, các collection không tự đổi | Migration có kiểm soát |
| Unique index không có shard-key prefix | Không bảo đảm uniqueness theo mong muốn | Thiết kế index cùng shard key |
| Mở API cho region mới trước khi cấu hình zone | Có cửa sổ dữ liệu unzoned | Rollout hạ tầng/zone/schema trước app |
| Dùng zone như bằng chứng pháp lý duy nhất | Bỏ sót toàn bộ hệ thống ngoài sharded collection | Audit toàn bộ replication, log, backup, xử lý |

## 28. Bài tập thực hành và câu hỏi tình huống

Các bài tập dùng cluster **thử nghiệm** có đủ shard và mongos. Những lệnh thêm/gỡ zone, thay đổi range chỉ được thực hiện với quyền quản trị và khi biết rõ namespace dữ liệu thử. Nếu bạn chỉ có standalone mongod, có thể làm bài phân tích sơ đồ và cú pháp mà không cần chạy lệnh.

### Bài 1. Xác định ba thành phần của zone sharding

Giả sử:

~~~text
shardEU1, shardEU2 -> ZONE_EU
shardAP1           -> ZONE_APAC

EU shard-key range   -> ZONE_EU
APAC shard-key range -> ZONE_APAC
~~~

**Câu hỏi:** Ai định nghĩa shard membership, ai định nghĩa range-to-zone và ai giúp placement hội tụ?

**Định hướng trả lời:** sh.addShardToZone gắn shard vào zone; sh.updateZoneKeyRange gắn range vào zone; balancer giúp điều phối ownership/range migration theo các ràng buộc, không phải cùng một thao tác nguyên tử duy nhất.

### Bài 2. Viết lệnh gắn shard vào zone

Cho cluster có shard tên **shardEU1** và **shardEU2**. Hãy gắn cả hai vào ZONE_EU.

~~~javascript
sh.addShardToZone("shardEU1", "ZONE_EU");
sh.addShardToZone("shardEU2", "ZONE_EU");
~~~

**Câu hỏi:** Lệnh trên có tự xác nhận shard ở Frankfurt không? Có tự gắn collection orders vào zone không?

**Đáp án:** Không. Cần xác minh hạ tầng; và phải khai báo zone range cho namespace liên quan.

### Bài 3. Tạo zone range cho compound shard key

Collection **geo_orders.orders** có shard key:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

Hãy khai báo range EU bao gồm mọi orderId dạng String hợp lệ.

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);
~~~

**Giải thích:** MinKey và MaxKey là sentinel để bao phủ toàn bộ miền String orderId. Bound trên bị loại trừ, nên schema cần giới hạn orderId để không có document dùng MaxKey làm giá trị thật.

### Bài 4. Biên đóng/mở của zone range

Shard key đơn:

~~~javascript
{ score: 1 }
~~~

Zone range:

~~~text
[score=10, score=20)
~~~

**Câu hỏi:** score=10, score=19, score=20, score=9 thuộc range không?

**Đáp án:** 10 và 19 thuộc range; 20 và 9 không thuộc range. Nếu doanh nghiệp muốn score=20 thuộc cùng zone, cần định nghĩa khoảng khác phù hợp, không tùy tiện hiểu max là inclusive.

### Bài 5. Tìm lỗi trong thiết kế shard key

Yêu cầu: dữ liệu thuộc country="EU" phải vào zone EU.

Thiết kế:

~~~javascript
{ orderId: "hashed" }
~~~

Và field country chỉ nằm ở document, không nằm trong shard key.

**Câu hỏi:** Vì sao khó thể hiện yêu cầu zone theo country?

**Định hướng:** Zone ranges được gắn trong không gian shard key. Với key hash orderId thuần túy, các document EU có thể phân tán khắp miền hash; country không tạo thành một khoảng shard key liên tục. Phải xem lại shard key/mô hình hoặc kiến trúc lưu trữ.

### Bài 6. Truy vấn nào có lợi cho targeting?

Cho shard key:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

Ba truy vấn:

~~~javascript
// A
db.orders.find({ dataRegion: "EU", orderId: "EU-001" });

// B
db.orders.find({ dataRegion: "EU" });

// C
db.orders.find({ orderId: "EU-001" });
~~~

**Câu hỏi:** Truy vấn nào có đầy đủ shard key, query nào dùng prefix và query nào thiếu prefix?

**Đáp án:** A đầy đủ; B có prefix region nên có thể target những range trong EU; C thiếu prefix, có nguy cơ scatter-gather. B có thể đọc nhiều shard EU nếu zone có nhiều shard.

### Bài 7. Phân biệt cấu hình và placement

Quản trị viên tạo zone EU, sh.updateZoneKeyRange trả thành công, nhưng một range EU đang ở shardAP1.

**Câu hỏi:** Có thể tuyên bố đã hoàn tất di chuyển EU không? Cần kiểm tra những gì?

**Định hướng:** Chưa. Cần xem zone membership, range metadata, balancer state, lỗi migration và current shard ownership; sau đó kiểm tra dữ liệu cũ/backup nếu có yêu cầu residency.

### Bài 8. Một shard thuộc hai zone

~~~text
shardShared:
  ZONE_EU
  ZONE_APAC
~~~

**Câu hỏi:** Điều này có phù hợp nếu dữ liệu EU không được phép tồn tại trên bất kỳ shard chứa APAC data không?

**Định hướng:** Không phù hợp với mục tiêu isolation đó, vì shardShared có thể sở hữu range của cả hai zone. Phải xem lại membership và thiết kế các nhóm shard tách biệt.

### Bài 9. Unzoned range

Collection có zone ranges cho EU, APAC, US. Một ứng dụng insert:

~~~javascript
{
  dataRegion: "LATAM",
  orderId: "LA-001"
}
~~~

**Câu hỏi:** Zone nào ràng buộc dữ liệu LATAM? Làm sao ngăn dữ liệu nằm ngoài chính sách?

**Định hướng:** Không có zone LATAM được xác định, nên không được mặc định nó thuộc một zone cố định. Cần policy/validator từ chối hoặc quy trình provision zone LATAM trước khi tiếp nhận dữ liệu.

### Bài 10. Replica set vượt ra ngoài vùng

ShardEU1 có:

~~~text
Primary: Frankfurt
Secondary A: Frankfurt
Secondary B: Singapore
~~~

**Câu hỏi:** Nếu chính sách cấm dữ liệu EU có bản sao ngoài EU, zone sharding đã đủ chưa?

**Đáp án:** Chưa. Replica set tự sao chép dữ liệu shard sang mọi data-bearing member. Cần thiết kế replica placement và toàn bộ backup/DR phù hợp.

### Bài 11. Một region hết dung lượng

ZONE_EU có hai shard đều gần hết disk, ZONE_US còn thừa nhiều tài nguyên.

**Câu hỏi:** Có nên gắn shardUS1 vào ZONE_EU chỉ để balancer có thêm capacity không?

**Định hướng:** Chỉ nếu chính sách thực sự cho phép đặt EU data ở shardUS1; nếu residency cấm thì không. Nên mở rộng capacity trong vùng được phép hoặc thêm shard EU phù hợp.

### Bài 12. Global unique orderId

Một hệ thống yêu cầu orderId duy nhất toàn cluster. Shard key và unique index hiện tại:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

**Câu hỏi:** ("EU","O-123") và ("US","O-123") có vi phạm uniqueness của cặp không? Cần gì nếu O-123 phải duy nhất toàn hệ thống?

**Đáp án:** Không vi phạm uniqueness của cặp, vì dataRegion khác nhau. Cần cơ chế ID/business registry bảo đảm global uniqueness hoặc thiết kế lại ràng buộc/shard key phù hợp.

### Bài 13. Mở một vùng mới

Đội sản phẩm muốn cho phép **dataRegion="LATAM"** từ tuần tới. Hãy viết kế hoạch rollout an toàn.

**Một đáp án phù hợp gồm:**

1. Xác định hạ tầng, replication/backup hợp lệ cho LATAM.
2. Tạo/kiểm tra shard trong vùng đó.
3. Gắn shard vào ZONE_LATAM.
4. Khai báo zone range LATAM cho từng namespace yêu cầu.
5. Kiểm chứng metadata và placement.
6. Bổ sung LATAM vào validator và tenant policy.
7. Mở traffic ứng dụng, quan sát dữ liệu mới và alarm.

Không nên phát hành API chấp nhận LATAM trước khi có zone policy nếu dữ liệu không được phép vào unzoned ranges.

### Bài 14. Tenant thay đổi home region

Tenant T-1 chuyển từ APAC sang EU, nhưng đã có hàng triệu order và bản sao backup lịch sử.

**Câu hỏi:** Vì sao chỉ update cấu hình T-1 thành EU không đủ? Hãy liệt kê những thành phần migration cần xét.

**Định hướng:** Dữ liệu cũ vẫn mang shard key/range cũ; cần kế hoạch chuyển hoặc giữ lịch sử theo chính sách, kiểm tra transaction, mapping/unique keys, luồng đọc/ghi đồng thời, balancer và backup retention. Không thay shard key trên hàng triệu document một cách tùy tiện.

### Bài 15. So sánh sharding zone và cluster riêng

Một khách hàng yêu cầu dữ liệu, metadata, backups và toàn bộ vận hành phải được cách ly trong một vùng pháp lý với hệ thống khu vực khác.

**Câu hỏi:** Vì sao một cluster chung có zone có thể chưa đủ? Khi nào nên cân nhắc cluster riêng?

**Định hướng:** Zone chủ yếu ràng buộc range placement; cluster có các thành phần metadata/router/operational control chung. Nếu chính sách yêu cầu tách biệt rộng hơn, cluster riêng có thể phù hợp hơn, nhưng vẫn phải kiểm tra mọi replica, backup, log, export và đường truy cập của cluster riêng.

### Bài 16. Đọc kết quả explain

Hai câu query:

~~~javascript
db.orders.find({
  dataRegion: "EU",
  orderId: "EU-001"
}).explain("queryPlanner");

db.orders.find({
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

**Yêu cầu:** Ghi lại số shard tham gia, index được dùng và phạm vi range của từng query. Giải thích tại sao query thứ hai có thể đắt hơn dù tìm cùng orderId.

**Định hướng:** Query thứ nhất có full shard key, có cơ sở target hẹp; query thứ hai thiếu region nên có thể scatter-gather. Kết quả cụ thể phải dựa trên explain thực tế, không tự điền số shard cố định.

## 29. Cheat sheet lệnh zone sharding

Những lệnh dưới đây là **bảng tra cứu cú pháp**. Trên production, phải thay tên namespace/shard/zone bằng giá trị thực và tuân theo quy trình thay đổi được phê duyệt.

| Mục đích | Lệnh/khái niệm |
|---|---|
| Xem sharded cluster | sh.status() |
| Liệt kê shard | db.adminCommand({listShards:1}) |
| Gắn shard vào zone | sh.addShardToZone(shardName, zoneName) |
| Gỡ shard khỏi zone | sh.removeShardFromZone(shardName, zoneName) |
| Gắn range vào zone | sh.updateZoneKeyRange(namespace, min, max, zoneName) |
| Gỡ range khỏi zone | sh.removeRangeFromZone(namespace, min, max) |
| Xem zone metadata | config.tags (đọc qua config database) |
| Xem membership metadata | config.shards (đọc qua config database) |
| Xem trạng thái balancer | sh.getBalancerState(), sh.isBalancerRunning() |
| Xem tổng quan phân bố collection | getShardDistribution() khi shell/server hỗ trợ |
| Xem shard targeting của query | explain("queryPlanner") |
| Tạo sharded collection | sh.shardCollection(namespace, shardKey) |
| Ngăn region sai kiểu hoặc ngoài enum | $jsonSchema validator + kiểm tra policy |

### 29.1. Một cấu hình mẫu gói gọn

Giả sử các shard bên dưới đã tồn tại trong cluster thử nghiệm, và collection dùng shard key gồm **dataRegion + orderId**:

~~~javascript
// 1. Shard membership
sh.addShardToZone("shardEU1", "ZONE_EU");
sh.addShardToZone("shardEU2", "ZONE_EU");
sh.addShardToZone("shardAP1", "ZONE_APAC");
sh.addShardToZone("shardUS1", "ZONE_US");

// 2. Namespace-specific zone ranges
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);

sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "APAC", orderId: MinKey() },
  { dataRegion: "APAC", orderId: MaxKey() },
  "ZONE_APAC"
);

sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "US", orderId: MinKey() },
  { dataRegion: "US", orderId: MaxKey() },
  "ZONE_US"
);

// 3. Quan sát cấu hình
sh.status();

db.getSiblingDB("config").tags.find({
  ns: "geo_orders.orders"
});
~~~

**Không dùng đoạn trên như một script bootstrap đầy đủ**: nó giả định shard membership, cluster topology, collection shard key/index và quyền quản trị đã được chuẩn bị theo các bước trước. Để đảm bảo một hệ thống production đúng chính sách, vẫn phải xác nhận balancer đã hội tụ và kiểm tra replica/backup/metadata.

### 29.2. Mô hình ba lớp để ghi nhớ

~~~text
Lớp 1 — Business policy
  Tenant/document thuộc region nào?
  Ai có quyền quyết định region?
                  |
                  v
Lớp 2 — MongoDB zone placement
  shard key chứa field region
  region range -> zone
  zone -> permitted shards
  balancer -> converged ownership
                  |
                  v
Lớp 3 — Physical and operational controls
  replica set members
  storage, backups, logs
  exports, disaster recovery
  auth/audit, migrations
~~~

Nếu một trong ba lớp sai, việc “zone đã khai báo” không đủ để kết luận hệ thống đáp ứng ràng buộc vị trí dữ liệu.

## 30. Kết luận

**Zone sharding** giúp MongoDB quản lý vị trí đặt các khoảng shard key trong một sharded cluster. Thay vì để mọi range được phân bố trên tất cả shard không phân biệt, quản trị viên có thể đặt các quy tắc như:

~~~text
{ dataRegion: "EU", orderId: ... }
    -> ZONE_EU
    -> shardEU1 / shardEU2

{ dataRegion: "APAC", orderId: ... }
    -> ZONE_APAC
    -> shardAP1 / shardAP2
~~~

Nhưng tính năng này cần được hiểu đúng qua **sáu nguyên tắc**:

1. **Zone là ràng buộc placement cho shard-key ranges.** Nó không tự tạo shard hay xác minh vị trí vật lý của máy.
2. **Shard key phải diễn đạt được nhóm dữ liệu cần đặt.** Với residency theo region, region thường cần là prefix phù hợp; field không nằm trong shard key không tự tạo range liên tục.
3. **Shard membership và zone ranges là hai cấu hình riêng**, còn balancer quản lý quá trình tiến tới placement tuân thủ. Một lệnh thành công không đồng nghĩa di chuyển hoàn tất ngay.
4. **Unzoned ranges vẫn cần chính sách.** Field region null, sai kiểu, viết khác, hoặc mã mới chưa được tạo zone có thể phá ý định residency nếu ứng dụng không validate.
5. **Zone sharding không thay replication, backup, routing, authorization hoặc compliance audit.** Muốn bảo vệ vị trí dữ liệu phải xem toàn bộ vòng đời và những bản sao.
6. **Khả năng scale và latency vẫn cần được thiết kế.** Nhiều shard có thể cùng một zone, query thiếu shard-key prefix có thể scatter-gather, và capacity trống ở một zone khác không nhất thiết dùng được cho zone đang đầy.

Khi kết hợp shard key hợp lý, zone ranges không chồng lấn, membership chính xác, balancer được giám sát, schema validation, tenant-region policy và kiểm soát hạ tầng, zone sharding trở thành một công cụ hữu ích để **giữ dữ liệu trong nhóm shard được phép theo quy tắc đã định**, đồng thời vẫn khai thác khả năng mở rộng ngang của MongoDB.

Điều cần kiểm chứng sau cùng không chỉ là **“đã khai báo zone nào?”**, mà là **“ở thời điểm hiện tại và trong toàn bộ vòng đời dữ liệu, những bản ghi này thực sự có thể nằm ở đâu, được sao chép tới đâu và ai có quyền đưa chúng qua ranh giới đó?”**.
