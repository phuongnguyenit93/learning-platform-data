# Shard, replica, routing và nguy cơ shard nhận tải không đều

Elasticsearch phân chia một index thành nhiều primary shard. Mỗi document được lưu trên một shard, còn replica là các bản sao của primary shard được đặt trên những node khác để tăng khả năng chịu lỗi và hỗ trợ đọc. Routing quyết định document được đưa vào shard nào và search request cần truy vấn những shard nào.

Ba cơ chế này ảnh hưởng trực tiếp đến hiệu năng, nhưng chúng giải quyết những vấn đề khác nhau. Tăng replica có thể tăng khả năng phục vụ search và cải thiện khả năng sẵn sàng; nó không tự chia tải ghi của một primary shard. Custom routing có thể giảm số shard phải tìm kiếm, nhưng nếu routing key phân bố lệch thì một shard có thể trở thành điểm nóng. Tăng số shard cũng không tự sửa được mọi dạng mất cân bằng.

Bài học này giải thích quan hệ giữa shard, replica và routing; phân biệt mất cân bằng dữ liệu với mất cân bằng tải; cách nhận diện hot shard; cách chọn routing strategy; và cách cấu hình, quan sát, điều chỉnh index trong ứng dụng Spring Data Elasticsearch.

## 1. Primary shard và replica shard

Một index được chia thành một hoặc nhiều primary shard. Mỗi primary shard là một phân vùng dữ liệu độc lập. Elasticsearch phân phối các primary shard và bản sao của chúng trên các node trong cluster theo chính sách allocation.

Ví dụ index orders có ba primary shard và một replica cho mỗi primary:

~~~text
Index: orders

Node A                 Node B                 Node C
+----------------+     +----------------+     +----------------+
| Primary shard 0|     | Primary shard 1|     | Primary shard 2|
| Replica shard 1|     | Replica shard 2|     | Replica shard 0|
+----------------+     +----------------+     +----------------+
~~~

Sơ đồ chỉ minh họa một cách phân bố. Elasticsearch có thể chọn node khác dựa trên số node, allocation awareness, disk watermark, shard limits và trạng thái cluster. Một shard copy không được đặt cùng node với primary hoặc replica copy khác của chính shard đó.

### Primary shard

Primary shard giữ bản chính của một phần dữ liệu index. Khi một document được index, Elasticsearch xác định shard đích rồi gửi thao tác tới primary shard tương ứng. Primary xử lý thao tác và phối hợp replication tới các replica đang hoạt động.

Primary shard cũng là đơn vị phân phối dữ liệu và phần lớn công việc ghi. Một primary shard quá nóng có thể giới hạn thông lượng ghi của các document được định tuyến vào nó, ngay cả khi những shard khác còn rảnh.

### Replica shard

Replica là bản sao của primary shard. Replica có hai vai trò chính:

- Cung cấp bản sao dự phòng khi node chứa primary gặp sự cố.
- Cho phép search request được phục vụ từ các shard copy khác nhau, nhờ đó tăng khả năng xử lý đọc trong nhiều workload.

Replica không phải một phân vùng dữ liệu mới. Nó chứa cùng tập document của primary tương ứng. Tăng replica làm tăng dung lượng lưu trữ cần thiết và công việc replication khi ghi.

Một replica copy của shard 0 không thể đặt trên cùng node đang giữ primary shard 0. Nếu cluster không có đủ node phù hợp, replica có thể ở trạng thái unassigned.

### Số lượng primary và replica khác nhau

Số primary shard xác định cách index được chia thành các phân vùng dữ liệu. Số replica xác định số bản sao bổ sung của mỗi primary.

- Primary shard count ảnh hưởng đến khả năng phân phối dữ liệu và mức độ song song.
- Replica count ảnh hưởng đến dự phòng, khả năng phục vụ đọc và chi phí lưu trữ/replication.
- Replica count có thể thay đổi động qua index settings.
- Primary shard count không thể tùy ý đổi trực tiếp sau khi index đã được tạo. Muốn thay đổi cấu trúc primary, thường cần split, shrink hoặc reindex sang index mới theo điều kiện phù hợp.

Không tăng primary shard chỉ để xử lý một truy vấn chậm trước khi xác định nguyên nhân.

## 2. Elasticsearch phân phối document tới shard

Khi index document mà không chỉ định custom routing, Elasticsearch dùng document ID làm routing value mặc định. Routing value được hash và ánh xạ vào một primary shard của index.

Có thể hình dung:

~~~text
document ID hoặc custom routing
              |
              v
          hash value
              |
              v
      số lượng primary shard
              |
              v
        primary shard đích
              |
              v
       các replica tương ứng
~~~

Ví dụ:

~~~http
POST /orders/_doc/O-100
{
  "orderId": "O-100",
  "tenantId": "tenant-A",
  "amount": 120.5
}
~~~

Không truyền routing nên document ID O-100 được dùng làm routing value mặc định.

Nếu ứng dụng truyền routing:

~~~http
POST /orders/_doc/O-100?routing=tenant-A
{
  "orderId": "O-100",
  "tenantId": "tenant-A",
  "amount": 120.5
}
~~~

Elasticsearch dùng tenant-A để chọn shard. Các document cùng routing value trong cùng index sẽ được định tuyến nhất quán tới cùng primary shard, trừ khi dùng partitioned routing.

### Phân bố hash không bảo đảm tải thực tế cân bằng

Hash routing giúp các routing value phân bố tương đối đều khi số lượng key đủ lớn và workload của mỗi key tương đối đồng đều. Nhưng hash không biết một tenant có một trăm document hay một trăm triệu document.

Ví dụ có 10.000 tenant nhưng một tenant lớn chiếm 60% tổng số document. Nếu toàn bộ document của tenant đó dùng cùng một custom routing value, phần lớn dữ liệu và thao tác của tenant lớn sẽ tập trung vào một shard.

Cũng có thể xảy ra tình huống số document tương đối đều nhưng một tenant có lưu lượng search hoặc update cao hơn hẳn. Khi đó, mất cân bằng tải xuất hiện dù dung lượng shard chưa chênh lệch nhiều.

## 3. Routing dùng để làm gì?

Custom routing cho phép ứng dụng chọn một routing key có ý nghĩa nghiệp vụ, ví dụ tenant ID, account ID hoặc customer ID.

Khi index:

~~~http
PUT /orders/_doc/O-100?routing=tenant-A
{
  "orderId": "O-100",
  "tenantId": "tenant-A",
  "status": "OPEN"
}
~~~

Khi search theo cùng routing:

~~~http
GET /orders/_search?routing=tenant-A
{
  "query": {
    "term": {
      "tenantId": "tenant-A"
    }
  }
}
~~~

Nếu tất cả document của tenant-A được lưu cùng một shard, search theo routing có thể chỉ cần truy vấn shard đó thay vì fan-out tới mọi primary shard của index.

Routing có thể giảm:

- Số shard tham gia search.
- Công việc phối hợp kết quả giữa nhiều shard.
- Lượng dữ liệu trung gian trong query có phạm vi tenant rõ ràng.
- Chi phí tìm document theo ID khi routing value đã biết.

Routing cũng tạo một ràng buộc vận hành: các thao tác get, update và delete theo ID phải dùng đúng routing value đã dùng khi index. Nếu thiếu hoặc sai route, Elasticsearch có thể không tìm thấy document dù document vẫn tồn tại trên shard khác.

### Search routing và document filter là hai việc khác nhau

Routing chọn shard copy tham gia request. Query DSL chọn document nào được trả về từ các shard đó.

Nếu nhiều tenant có thể nằm trên cùng shard, chỉ truyền routing tenant-A mà query không có tenant filter có thể trả document tenant khác nằm trên shard đã chọn. Routing không phải bộ lọc bảo mật và không thay thế điều kiện tenant trong query.

## 4. Replica ảnh hưởng tới tải như thế nào?

Khi một search request cần đọc shard, Elasticsearch có thể chọn một trong các shard copy đang hoạt động của shard đó. Các bản sao cho phép nhiều search request được phân phối giữa primary và replica.

Ví dụ một index có một primary và hai replica cho mỗi shard:

~~~text
Shard 0 copies:
  Primary 0  -> Node A
  Replica 0  -> Node B
  Replica 0  -> Node C

Search requests:
  Request 1 -> Node A
  Request 2 -> Node B
  Request 3 -> Node C
~~~

Sơ đồ minh họa khả năng phân phối request. Cơ chế chọn shard copy thực tế còn phụ thuộc trạng thái cluster, preference, adaptive replica selection và các yếu tố tải/độ trễ.

### Replica có thể giúp đọc, không chia primary write

Mọi thao tác ghi vẫn đi qua primary shard tương ứng. Primary phối hợp replication tới các replica. Do đó, tăng replica có thể giúp search capacity và khả năng sẵn sàng, nhưng không biến một primary shard nóng thành nhiều primary độc lập.

Replica cũng tiêu thụ tài nguyên:

- Dung lượng disk cho bản sao.
- Network bandwidth cho replication.
- CPU và I/O cho indexing, merge và recovery.
- Thời gian khôi phục khi node hoặc shard copy cần phục hồi.

Nếu workload chủ yếu là ghi và một primary shard bị quá tải do routing skew, thêm replica có thể tăng chi phí mà không giải quyết điểm nghẽn chính.

### Thay đổi số replica

Có thể thay đổi replica count bằng index settings:

~~~http
PUT /orders/_settings
{
  "number_of_replicas": 2
}
~~~

Thao tác này yêu cầu Elasticsearch phân bổ thêm hoặc loại bỏ replica copies. Việc phân bổ vẫn phụ thuộc số node, allocation rules và tài nguyên cluster.

Với một node duy nhất, replica thường không thể được gán lên cùng node với primary nên sẽ unassigned. Điều đó có thể là trạng thái mong đợi trong môi trường development, nhưng production cần số node và cấu hình phù hợp với mức dự phòng mong muốn.

### wait_for_active_shards không phải authorization hay transaction

Write request có thể cấu hình số shard copies cần active trước khi thao tác được thực hiện, ví dụ wait_for_active_shards. Đây là điều kiện về khả năng sẵn sàng của shard copies trước thao tác. Nó không thay đổi cách chọn shard, không làm request được rollback như transaction và không giải quyết routing skew.

## 5. Các dạng mất cân bằng shard

Không phải mọi mất cân bằng đều giống nhau. Trước khi thay đổi cấu hình, cần xác định loại mất cân bằng đang gặp.

### Mất cân bằng dung lượng

Một số shard chứa nhiều dữ liệu hơn đáng kể so với shard khác. Điều này có thể xảy ra do:

- Custom routing key có phân bố document không đều.
- Tenant lớn chiếm phần lớn dữ liệu.
- Một nhóm document có source rất lớn.
- Dữ liệu lịch sử tập trung vào một phần key.
- Index được tạo với shard count không phù hợp.

Shard lớn có thể cần nhiều disk, heap cho metadata/segments và thời gian recovery lâu hơn.

### Mất cân bằng tải ghi

Một shard nhận nhiều indexing/update request hơn các shard khác. Nguyên nhân thường gặp:

- Một routing key có lưu lượng ghi cao.
- Một tenant có workload lớn.
- Producer phân phối message không đều.
- Một loại dữ liệu luôn được ghi cùng một route.
- Retry dồn dập vào shard đang bị quá tải.

Một shard có thể nóng dù kích thước dữ liệu của nó chưa phải lớn nhất.

### Mất cân bằng tải đọc

Một shard nhận nhiều search request hoặc query tốn CPU hơn. Có thể do:

- Nhiều request cùng routing tới một tenant lớn.
- Một tenant có traffic cao.
- Query trên một shard có nhiều document hoặc field lớn.
- Search routing khiến request luôn nhắm tới cùng shard.
- Cache, segment và workload của các shard khác nhau.

Replica có thể giúp phân phối tải đọc nếu search có thể chọn các shard copies khác nhau. Nhưng nếu một request chỉ nhắm tới một routing key, nó vẫn chỉ nhắm tới shard tương ứng và các replica copies của shard đó.

### Mất cân bằng phân bổ node

Số shard copy hoặc tổng dung lượng trên các node có thể không đều. Nguyên nhân gồm:

- Node mới tham gia hoặc node bị loại bỏ.
- Disk watermark.
- Allocation awareness.
- Allocation filtering.
- Shard recovery đang chạy.
- Node roles và tài nguyên khác nhau.

Elasticsearch có thể di chuyển shard copies giữa các node để cân bằng allocation. Việc này không chia một shard lớn thành nhiều shard nhỏ và không tự phân phối lại document bên trong shard.

## 6. Hot shard là gì?

Hot shard là shard nhận tải hoặc công việc cao hơn đáng kể so với các shard khác. Nó có thể trở thành nút thắt cổ chai cho index.

Ví dụ:

~~~text
Index orders - write operations per minute

Shard 0:  1,200
Shard 1:    180
Shard 2:    160
Shard 3:    190
Shard 4:    170
Shard 5:    200
~~~

Shard 0 nhận lượng ghi cao gấp nhiều lần các shard còn lại. Dù tổng cluster còn CPU và disk trống, các request nhắm vào shard 0 vẫn có thể bị chậm hoặc bị từ chối.

### Dấu hiệu hot shard

- Bulk request có latency cao bất thường.
- Tỷ lệ 429 hoặc indexing rejection tăng.
- Một shard có indexing rate cao hơn nhiều shard khác.
- Một node chứa shard nóng có CPU, disk I/O hoặc indexing pressure cao.
- Search latency thay đổi theo routing key.
- Một số tenant bị chậm trong khi tenant khác vẫn nhanh.
- Recovery hoặc merge của shard nóng kéo dài.

Không kết luận hot shard chỉ từ CPU của node. Một node có thể chứa nhiều shard khác nhau; cần liên hệ metric node với shard copy và workload của từng index.

### Hot node và hot shard không giống nhau

Hot node là node có tải cao. Hot shard là shard có workload cao. Một hot node có thể do chứa nhiều shard hoạt động, merge hoặc recovery đồng thời. Một hot shard có thể nằm trên node vẫn còn tài nguyên tổng thể nhưng chính shard đó bị giới hạn bởi workload hoặc cấu trúc dữ liệu.

Cần phân biệt hai cấp để chọn biện pháp đúng.

## 7. Routing skew và vì sao custom routing có thể gây hại

Routing key có cardinality thấp hoặc phân bố workload không đều dễ tạo shard nóng.

Ví dụ dùng status làm routing:

~~~text
routing = status

OPEN     -> shard 0
PAID     -> shard 2
CANCELLED-> shard 1
~~~

Nếu phần lớn đơn hàng ở trạng thái OPEN, shard được chọn cho OPEN sẽ nhận phần lớn document và thao tác. Routing theo status cũng làm các trạng thái có cardinality thấp tập trung mạnh.

Dùng tenant ID có thể tốt hơn nếu số tenant đủ lớn và quy mô mỗi tenant tương đối đồng đều. Nhưng nếu có tenant rất lớn hoặc tenant có traffic vượt trội, một tenant vẫn có thể làm nóng shard.

### Các nguyên nhân phổ biến

1. **Cardinality thấp:** quá ít routing key so với số shard.
2. **Skew về dung lượng:** một vài key chứa nhiều document hơn hẳn.
3. **Skew về traffic:** một key nhận nhiều request hơn.
4. **Key không ổn định:** cùng một entity được index bằng nhiều routing value khác nhau.
5. **Hot tenant:** một tenant lớn chiếm shard hoặc một nhóm shard với phần lớn workload.
6. **Batch không cân bằng:** một worker xử lý tập routing key tập trung vào một shard.
7. **Search routing quá hẹp:** nhiều request liên tục nhắm cùng một shard dù các shard khác còn rảnh.

Custom routing không tự động tốt hơn default routing. Chỉ dùng khi lợi ích giảm shard fan-out hoặc yêu cầu phân vùng dữ liệu được đo đạc rõ ràng.

## 8. Chọn routing key

Routing key nên đáp ứng một số tiêu chí:

- Có cardinality đủ cao để phân bố dữ liệu.
- Ổn định trong vòng đời document.
- Có sẵn khi index và khi cần get/update/delete.
- Phù hợp với mẫu query phổ biến.
- Không tạo một vài key quá nóng.
- Không làm lộ thông tin nhạy cảm nếu routing xuất hiện trong log hoặc request trace.

Các lựa chọn thường gặp:

| Routing key | Ưu điểm | Rủi ro |
|---|---|---|
| Không custom routing, dùng document ID | Phân bố thường tốt khi ID đủ ngẫu nhiên | Search có thể fan-out toàn index |
| Tenant ID | Query theo tenant có thể giảm shard fan-out | Tenant lớn có thể tạo hot shard |
| Customer ID | Query theo customer có thể chỉ tới một shard | Một số customer có workload/dữ liệu lớn |
| Account ID | Phù hợp workload truy cập theo account | Account lớn có thể nóng |
| Status/category | Dễ nhóm dữ liệu theo loại | Cardinality thấp và phân bố thường lệch |
| Tenant + bucket | Có thể chia tenant lớn thành nhiều route | Query tenant cần truy vấn nhiều bucket |
| Random per-document | Phân bố đều hơn trong một số trường hợp | Không tối ưu truy vấn theo tenant |

Không chọn routing key chỉ vì field đó thường xuất hiện trong query. Cần so sánh lợi ích giảm fan-out với nguy cơ phân bố dữ liệu và traffic không đều.

## 9. Routing partitioning cho tenant lớn

Elasticsearch hỗ trợ partitioned routing thông qua index setting index.routing_partition_size. Thay vì một routing value luôn chọn đúng một shard, một routing value có thể được phân phối trong một tập con gồm nhiều shard. Document ID tham gia chọn shard bên trong partition đó.

Điều này giúp một routing key lớn không dồn toàn bộ document vào một shard. Search có cùng routing value sẽ truy vấn partition shard tương ứng thay vì phải tìm toàn index.

Ví dụ tạo index:

~~~http
PUT /orders
{
  "settings": {
    "number_of_shards": 12,
    "number_of_replicas": 1,
    "index.routing_partition_size": 3
  },
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Ví dụ minh họa 12 primary shard và partition size 3. Một routing value sẽ được phân bố trên một nhóm ba shard theo thuật toán partition routing của Elasticsearch.

### Trade-off của partitioned routing

- Một tenant có thể được ghi trên nhiều shard trong partition.
- Search theo tenant phải truy vấn các shard thuộc partition đó.
- Số shard được truy vấn nhiều hơn custom routing đơn shard.
- Phân bố ghi của tenant lớn có thể tốt hơn.
- Partition size phải được quyết định khi thiết kế index; không thể coi nó như một setting thay đổi tùy ý sau khi index đã chứa dữ liệu.

Partitioned routing là lựa chọn đáng cân nhắc khi một số routing key lớn cần chia tải nhưng vẫn muốn search theo key không fan-out toàn index. Cần xác nhận giới hạn và điều kiện cấu hình theo Elasticsearch version đang dùng.

## 10. Composite routing và bucket theo tenant

Một cách khác là tạo routing value từ tenant ID và bucket:

~~~text
routing = tenantId + "#" + bucketNumber
~~~

Bucket có thể được xác định từ order ID hoặc một hash ổn định:

~~~java
int bucket = Math.floorMod(
    orderId.hashCode(),
    bucketCount
);

String routing = tenantId + "#" + bucket;
~~~

Ví dụ tenant-A có 8 bucket:

~~~text
tenant-A#0 -> shard 0
tenant-A#1 -> shard 3
tenant-A#2 -> shard 5
tenant-A#3 -> shard 1
tenant-A#4 -> shard 4
tenant-A#5 -> shard 2
tenant-A#6 -> shard 0
tenant-A#7 -> shard 5
~~~

Các ánh xạ shard trong sơ đồ chỉ minh họa. Hash routing có thể khiến nhiều bucket cùng shard.

### Lợi ích

- Ghi của tenant lớn được chia ra nhiều routing key.
- Một worker hoặc partition queue có thể xử lý một số bucket riêng.
- Có thể kiểm soát số bucket dựa trên workload.

### Chi phí

- Khi tìm toàn bộ đơn hàng của tenant, ứng dụng phải truy vấn tất cả bucket của tenant hoặc bỏ routing và search với tenant filter.
- Get/update/delete theo ID phải tính đúng bucket/routing value ban đầu.
- Bucket count và thuật toán hash phải ổn định.
- Nếu thay bucket count, cần migration hoặc version hóa routing strategy.
- Nhiều bucket không bảo đảm mỗi bucket nằm trên một shard riêng.

Composite routing là một đánh đổi giữa write distribution và query fan-out. Không tăng bucket count tùy tiện nếu query theo tenant là workload chủ đạo.

## 11. Tăng số primary shard có giải quyết hot shard không?

Tăng primary shard có thể giúp phân phối document và workload tốt hơn khi index có cấu trúc phù hợp. Tuy nhiên, thay đổi này không tự động sửa mọi hot shard.

Ví dụ một index ban đầu có ba primary shard. Nếu tất cả document của tenant-A đều dùng routing tenant-A, sau khi tạo index mới có mười hai primary shard, toàn bộ document tenant-A vẫn có thể đi vào một shard duy nhất nếu vẫn dùng custom routing không partition.

Tăng shard count mà giữ nguyên routing key nóng có thể chỉ thay đổi shard ID được chọn, không loại bỏ điểm nóng.

### Khi nào tăng shard count có ích?

- Index hiện tại có shard quá lớn và cần chia dữ liệu.
- Default ID routing phân bố tương đối đều nhưng số shard chưa đủ để tận dụng cluster.
- Workload cần nhiều shard song song hơn.
- Dung lượng dự kiến tăng và index mới được thiết kế với shard count phù hợp.

### Khi nào không có ích?

- Một tenant dùng một routing key chiếm phần lớn traffic.
- Một query rất nặng tập trung vào một route.
- Node có disk/CPU bottleneck độc lập với shard count.
- Mapping hoặc query gây scan/aggregation tốn tài nguyên.
- Replica placement hoặc allocation constraint đang là nguyên nhân.

Số primary shard cần được quyết định theo dữ liệu dự kiến, số node, workload và khả năng recovery. Tránh over-sharding vì mỗi shard có overhead về heap, segment metadata, file handle, cluster state và coordination.

## 12. Shard sizing và số lượng shard

Không có một shard size duy nhất phù hợp mọi index. Shard size phụ thuộc:

- Dung lượng source và index.
- Số lượng document.
- Số field và kiểu mapping.
- Số segment và mức độ merge.
- Tần suất update/delete.
- Tốc độ ingest.
- Query latency và concurrency.
- Heap, disk và network của node.
- Thời gian recovery mà hệ thống chấp nhận.

Shard quá lớn có thể làm recovery lâu, merge nặng và giới hạn song song. Quá nhiều shard nhỏ lại tạo overhead đáng kể cho cluster và làm search fan-out tốn kém.

Các hướng dẫn vận hành thường dùng shard cỡ vài chục GB làm điểm khởi đầu để thử nghiệm, nhưng đây không phải ngưỡng cứng. Cần benchmark với dữ liệu và workload gần production.

### Đánh giá bằng dữ liệu thực tế

Đo ít nhất:

- Primary shard size.
- Replica shard size.
- Document count theo shard.
- Indexing throughput.
- Search latency p50/p95/p99.
- Recovery duration.
- Merge time và segment count.
- Disk utilization và heap pressure.

Một index có sáu shard bằng dung lượng nhau vẫn có thể mất cân bằng về traffic. Ngược lại, shard có dung lượng khác nhau không nhất thiết gây vấn đề nếu workload và latency vẫn trong mục tiêu.

## 13. Allocation và shard balancing giữa các node

Elasticsearch cluster allocation quyết định shard copy được đặt trên node nào. Cluster allocation có thể cân bằng số shard và dung lượng theo các điều kiện hiện có.

Một số yếu tố ảnh hưởng:

- Disk watermarks.
- Shard allocation awareness.
- Allocation filtering.
- Node attributes.
- Node roles.
- Shard limits.
- Recovery và relocation đang chạy.
- Cluster allocation explain decisions.

### Awareness theo zone hoặc rack

Để tăng khả năng chịu lỗi, có thể gán node attribute như zone và cấu hình allocation awareness. Elasticsearch cố gắng phân bố shard copies qua các failure domain khác nhau khi có đủ node phù hợp.

Ví dụ node attributes:

~~~yaml
node.attr.zone: zone-a
~~~

Cluster setting:

~~~http
PUT /_cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.awareness.attributes": "zone"
  }
}
~~~

Đây là ví dụ cấu hình. Cần cấu hình attribute trên các node tương ứng và xác nhận cluster có đủ zone. Nếu không đủ node ở một zone, một số replica có thể unassigned để giữ yêu cầu awareness.

Awareness tăng khả năng chịu lỗi ở tầng placement. Nó không tự cân bằng số document hoặc traffic bên trong một shard.

### Allocation filtering

Có thể giới hạn shard được phân bổ lên node dựa trên attribute, ví dụ nhóm node hot/warm hoặc node chuyên biệt. Điều này giúp tổ chức tài nguyên, nhưng filter sai có thể khiến shard không có node phù hợp và ở trạng thái unassigned.

Không dùng allocation filtering như cách chia document của một shard. Một shard copy được di chuyển nguyên vẹn giữa node; các document bên trong vẫn thuộc cùng shard.

## 14. Search load balancing và adaptive replica selection

Với một shard có primary và nhiều replica, search request có thể được gửi đến một shard copy phù hợp. Elasticsearch có cơ chế lựa chọn replica thích ứng dựa trên thông tin hiệu năng và thời gian phản hồi.

Điều này giúp phân phối search giữa các node đang giữ copy của shard. Tuy nhiên:

- Nó không tạo thêm shard.
- Nó không chia một primary shard thành nhiều phần.
- Nó không giải quyết một routing key có traffic lớn vượt khả năng của mọi copy.
- Nó không làm giảm lượng dữ liệu mà một query trên shard phải xử lý.
- Nó không thay thế query tuning hoặc routing design.

Nếu một tenant rất nóng và mọi search đều nhắm tới cùng một shard, replica có thể phân phối các request tới nhiều node copies. Nhưng mỗi request vẫn cần xử lý toàn bộ công việc của shard tương ứng.

### Preference và tính nhất quán cache

Search preference có thể ảnh hưởng cách chọn shard copy và tính ổn định của lựa chọn qua các request. Dùng preference phù hợp có thể giúp tận dụng cache trong một số workload, nhưng cố định mọi request vào một node hoặc copy có thể tạo hot node.

Không đặt preference cố định chỉ để làm kết quả có vẻ ổn định nếu chưa đo tác động tới tải và cache.

## 15. Routing trong Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ khai báo property dùng làm routing thông qua annotation @Routing trên entity property.

Ví dụ:

~~~java
@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Routing
    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String status;

    // getters and setters
}
~~~

Khi dùng các thao tác entity-aware của Spring Data, routing metadata có thể được lấy từ property được đánh dấu. Điều này giúp thao tác lưu hoặc đọc theo entity sử dụng route tương ứng theo contract của phiên bản.

Phải kiểm tra API thực tế của Spring Data Elasticsearch đang dùng, đặc biệt với các thao tác chỉ nhận ID hoặc Query object. Không giả định mọi overload đều tự suy ra routing nếu không có entity chứa routing property.

### Gán routing property từ server

Ví dụ service tạo order:

~~~java
public Order createOrder(CreateOrderRequest request) {
    String tenantId = currentTenant.requireTenantId();

    Order order = new Order();
    order.setId(request.orderId());
    order.setTenantId(tenantId);
    order.setStatus("OPEN");

    return operations.save(order);
}
~~~

Tenant ID được lấy từ trusted context. Không dùng tenant ID tùy ý từ request body làm routing property.

### Routing khi dùng Java API Client trực tiếp

Nếu ứng dụng gọi Elasticsearch Java API Client, routing được truyền trên request:

~~~java
IndexResponse response = client.index(i -> i
    .index("orders")
    .id(order.getId())
    .routing(order.getTenantId())
    .document(order)
);
~~~

Search cũng cần route phù hợp:

~~~java
SearchResponse<Order> response = client.search(s -> s
    .index("orders")
    .routing(tenantId)
    .query(q -> q.term(t -> t
        .field("tenantId")
        .value(tenantId)
    )),
    Order.class
);
~~~

Đây là request ở tầng Java API Client. Khi dùng Spring Data Operations, routing được truyền qua metadata của query hoặc operation theo API của release train. Không nhầm cách truyền route của direct client với method signature của mọi Spring Data version.

## 16. Cấu hình shard và replica khi tạo index

Có thể khai báo số primary shard và replica trong index settings:

~~~http
PUT /orders
{
  "settings": {
    "number_of_shards": 6,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Index có sáu primary shard và một replica cho mỗi primary, tức tối đa mười hai shard copies khi toàn bộ replica được phân bổ.

Nếu thay replica count sau khi index được tạo:

~~~http
PUT /orders/_settings
{
  "number_of_replicas": 2
}
~~~

Số primary shard không thay đổi bằng cách gửi cùng một setting update. Muốn thay đổi số primary, xem xét split/shrink hoặc tạo index mới và reindex dữ liệu.

### Spring Data tạo index từ entity

Spring Data có thể tạo index dựa trên metadata entity và cấu hình index settings. Với cấu hình shard/replica cụ thể, có thể dùng index settings resource hoặc tạo index bằng provisioning script/IndexOperations tùy cách quản lý schema của dự án.

Không dựa vào default shard count của một phiên bản Elasticsearch cho mọi môi trường. Hãy quản lý index template, settings và mapping có chủ đích, rồi kiểm tra index thực tế sau khi tạo.

Nếu production dùng alias trỏ tới versioned index, tạo index mới với settings phù hợp rồi chuyển alias sau khi reindex và xác nhận dữ liệu.

## 17. Cách chẩn đoán shard mất cân bằng

Bắt đầu bằng trạng thái shard:

~~~http
GET /_cat/shards/orders?v
~~~

Lệnh này hiển thị shard ID, primary/replica, state, node và dung lượng. Nó giúp xác định shard copies đang nằm trên node nào và dung lượng có chênh lệch không.

Xem thống kê index:

~~~http
GET /orders/_stats/indexing,search,store,segments
~~~

Xem thống kê node:

~~~http
GET /_nodes/stats/indices,thread_pool,fs
~~~

Xem trạng thái node ngắn gọn:

~~~http
GET /_cat/nodes?v&h=name,roles,cpu,heap.percent,ram.percent,disk.used_percent
~~~

Xem thread pool:

~~~http
GET /_cat/thread_pool/write,search?v
~~~

Tên metric và mức chi tiết có thể thay đổi theo Elasticsearch version. Các API trên cần quyền monitoring phù hợp.

### Đọc số liệu theo từng cấp

1. So sánh shard size để tìm data skew.
2. So sánh indexing/search stats để tìm traffic skew.
3. Liên hệ shard với node để phát hiện node placement skew.
4. Kiểm tra thread pool queue/rejected để xác định áp lực thực tế.
5. Kiểm tra disk, heap, CPU và I/O để tìm tài nguyên giới hạn.
6. So sánh latency theo tenant hoặc routing key ở tầng ứng dụng.
7. Xem query và bulk request có tập trung vào một route không.

Không chỉ nhìn tổng CPU cluster. Một cluster có CPU trung bình thấp vẫn có thể có một shard hoặc một node bị quá tải cục bộ.

### Dùng allocation explain khi shard unassigned

Nếu replica không được phân bổ, có thể yêu cầu Elasticsearch giải thích:

~~~http
GET /_cluster/allocation/explain
{
  "index": "orders",
  "shard": 0,
  "primary": false
}
~~~

Kết quả giúp hiểu allocation decider nào ngăn shard copy được gán, ví dụ disk watermark, awareness hoặc không có node phù hợp.

Không ép allocate shard bằng thao tác thủ công nếu chưa hiểu nguyên nhân. Có thể làm giảm khả năng chịu lỗi hoặc gây mất dữ liệu nếu xử lý sai.

## 18. Biện pháp xử lý theo nguyên nhân

### Trường hợp A: một tenant tạo hot shard

Các hướng xử lý:

- Chuyển tenant lớn sang index riêng nếu có lợi ích vận hành rõ ràng.
- Dùng partitioned routing để phân tán một routing key trên nhiều shard.
- Dùng composite routing với bucket ổn định.
- Tách loại workload ghi nặng sang index phù hợp.
- Giới hạn concurrency hoặc tốc độ ingest cho tenant nóng.

Cần cân nhắc query fan-out tăng lên nếu tenant được chia thành nhiều bucket.

### Trường hợp B: nhiều shard nhỏ và search fan-out cao

Các hướng xử lý:

- Tạo index mới với số primary shard phù hợp hơn.
- Reindex hoặc rollover theo chiến lược dữ liệu.
- Giảm shard count trong index mới bằng shrink khi điều kiện cho phép.
- Tối ưu query để tránh fan-out không cần thiết.
- Tránh tạo quá nhiều index nhỏ cho từng tenant nếu cluster phải quản lý hàng nghìn shard.

### Trường hợp C: tải đọc cao nhưng ghi ổn định

Các hướng xử lý:

- Tăng replica nếu node và disk còn đủ tài nguyên.
- Kiểm tra search load balancing và replica allocation.
- Tối ưu query, filter, sort và aggregation.
- Dùng routing khi query pattern cho phép giảm shard fan-out.
- Cache ở tầng ứng dụng cho dữ liệu đọc lặp lại nếu semantics phù hợp.

Tăng replica không bảo đảm mọi query nhanh hơn. Query quá nặng trên một shard vẫn cần xử lý nhiều dữ liệu.

### Trường hợp D: node nóng do allocation lệch

Các hướng xử lý:

- Kiểm tra allocation explain và awareness.
- Kiểm tra disk watermarks và node roles.
- Bổ sung node phù hợp nếu cluster thiếu capacity.
- Điều chỉnh allocation filters có kiểm soát.
- Chờ relocation/recovery hoàn tất và theo dõi tải.
- Kiểm tra shard lớn hoặc shard hoạt động nhiều đang tập trung trên node.

Không di chuyển shard liên tục trong lúc cluster quá tải; relocation cũng tiêu thụ network và disk I/O.

### Trường hợp E: tải ghi toàn index cao

Các hướng xử lý:

- Tăng ingest capacity bằng node và tài nguyên phù hợp.
- Điều chỉnh bulk size/concurrency dựa trên metric.
- Giảm refresh frequency trong giai đoạn bulk ingest nếu use case cho phép.
- Tối ưu mapping và tránh field không cần thiết.
- Giảm update-in-place quá thường xuyên bằng thiết kế dữ liệu phù hợp.
- Xem xét rollover để tách dữ liệu theo thời gian.

Đừng chỉ tăng replica để giải quyết write bottleneck.

## 19. Rollover, ILM và phân vùng dữ liệu theo thời gian

Với dữ liệu append theo thời gian như log, event hoặc telemetry, một index duy nhất tăng mãi sẽ làm shard lớn dần. Rollover tạo index mới khi đạt điều kiện như tuổi, số document hoặc dung lượng.

Ví dụ alias:

~~~text
events-write -> events-000001
events-read  -> events-000001, events-000002, ...
~~~

Sau rollover:

~~~text
events-write -> events-000002
events-read  -> events-000001, events-000002
~~~

Mỗi backing index có shard/replica settings riêng. ILM có thể chuyển index qua các phase và thực hiện rollover, shrink hoặc delete theo policy.

Rollover giúp quản lý vòng đời và giới hạn kích thước index. Nó không tự giải quyết một routing key nóng nếu mọi event của tenant lớn vẫn tập trung vào cùng một shard trong từng backing index.

Khi thiết kế time-based index, cần xác định tenant routing có còn cần thiết hay default routing theo ID đã đủ. Nếu query luôn theo time range và tenant, có thể cân nhắc alias, data stream và filter strategy phù hợp.

## 20. Tác động của routing và shard tới bulk indexing

Bulk request có thể chứa document thuộc nhiều shard. Elasticsearch phân phối các operation tới primary shard tương ứng. Nếu batch phân bố không đều, một shard nóng có thể làm toàn batch hoàn tất chậm hơn.

Ví dụ:

~~~text
Bulk batch: 1,000 operations

Shard 0: 800 operations
Shard 1:  50 operations
Shard 2:  40 operations
Shard 3:  35 operations
Shard 4:  25 operations
Shard 5:  50 operations
~~~

Tổng batch không quá lớn nhưng phần lớn operation dồn vào shard 0. Tăng số worker gửi bulk có thể làm shard đó quá tải nhanh hơn.

### Điều chỉnh producer

- Theo dõi phân bố routing key trong batch.
- Giới hạn concurrency theo workload.
- Dùng backoff khi gặp 429.
- Tránh nhiều worker đồng thời đẩy dữ liệu của cùng một hot tenant.
- Cân nhắc partition producer theo routing key hoặc bucket.
- Đo latency và rejected count theo từng shard/tenant khi có thể.

Không chia batch chỉ theo số lượng document nếu kích thước và routing distribution rất khác nhau.

## 21. Ví dụ chọn chiến lược cho hệ thống đơn hàng

Giả sử hệ thống có 500 tenant:

- 450 tenant nhỏ, mỗi tenant dưới 100.000 order.
- 45 tenant trung bình, mỗi tenant vài triệu order.
- 5 tenant rất lớn, mỗi tenant hàng chục triệu order.
- Phần lớn search là tìm order theo tenant và khoảng thời gian.
- Một số tenant lớn có traffic cao hơn nhiều lần.

Một thiết kế có thể là:

1. Dùng tenant ID làm routing cho phần lớn tenant nếu đo benchmark cho thấy giảm fan-out đáng kể.
2. Tách nhóm tenant rất lớn sang index riêng hoặc dùng partitioned routing.
3. Giữ tenantId là keyword field để filter trong mọi query.
4. Dùng replica count dựa trên read throughput và availability.
5. Dùng time partition/rollover nếu vòng đời dữ liệu phù hợp.
6. Theo dõi hot shard và traffic theo tenant để điều chỉnh.
7. Quản lý index template và alias để thay đổi schema/settings có kiểm soát.

Không có một thiết kế đúng cho mọi hệ thống. Nếu tenant nhỏ và workload không có skew đáng kể, default routing theo document ID có thể đơn giản và cân bằng hơn custom routing.

### Cách benchmark

So sánh ít nhất ba phương án:

- Default routing theo document ID.
- Custom routing theo tenant ID.
- Partitioned/composite routing cho tenant lớn.

Đo:

- Index throughput.
- Bulk latency p50/p95/p99.
- Search latency theo tenant.
- Shard size distribution.
- Search shard fan-out.
- 429/rejected operations.
- CPU, heap, disk I/O và network.
- Thời gian recovery sau node failure.

Dùng workload có phân bố tenant giống production. Benchmark với tenant đồng đều có thể che giấu vấn đề hot tenant.

## 22. Các sai lầm thường gặp

| Triệu chứng hoặc giả định | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Tăng replica nhưng write vẫn chậm | Primary shard nóng vẫn nhận toàn bộ write | Sửa routing skew hoặc tăng khả năng ghi của shard |
| Tăng primary shard nhưng tenant lớn vẫn nóng | Một routing key vẫn chọn một shard | Partitioned/composite routing hoặc tách tenant |
| Một node có nhiều shard hơn | Allocation và tài nguyên node khác nhau | Kiểm tra allocation, awareness và disk |
| Shard size đều nhưng latency lệch | Traffic/query cost khác nhau | Đo indexing/search load theo shard |
| Search theo tenant vẫn chậm | Query không có routing hoặc tenant filter phù hợp | Kiểm tra route, query và fan-out |
| Routing thiếu khi get theo ID | Không lưu/khôi phục đúng route | Dùng routing property hoặc truyền route rõ ràng |
| Replica unassigned | Không đủ node hoặc allocation rule không cho phép | Kiểm tra allocation explain |
| Cluster có quá nhiều shard nhỏ | Over-sharding và nhiều index | Rollover, shrink/reindex và quản lý shard count |
| Một tenant chiếm phần lớn dung lượng | Data skew | Tách tenant hoặc phân vùng route |
| Bulk tăng concurrency làm 429 nhiều hơn | Hot shard hoặc cluster indexing pressure | Giảm concurrency, backoff, điều chỉnh batch |
| Thay đổi tenant routing nhưng document không di chuyển | Source field không thay đổi shard metadata | Reindex/migrate với routing mới |
| Search routing bị coi là filter bảo mật | Nhầm shard selection với document filtering | Thêm tenant filter và authorization |

## 23. Checklist thiết kế shard, replica và routing

- [ ] Xác định số primary shard theo dung lượng và workload dự kiến.
- [ ] Không over-shard chỉ để tăng số song song.
- [ ] Chọn replica count theo availability và read throughput.
- [ ] Đảm bảo replica copies có thể phân bổ trên các node khác nhau.
- [ ] Hiểu replica không chia primary write workload.
- [ ] Chỉ dùng custom routing khi có query pattern và lợi ích đo được.
- [ ] Chọn routing key có cardinality và phân bố phù hợp.
- [ ] Đo data skew và traffic skew riêng biệt.
- [ ] Kiểm tra hot tenant và hot shard.
- [ ] Cân nhắc partitioned routing cho routing key quá lớn.
- [ ] Đánh giá chi phí query fan-out khi dùng bucket routing.
- [ ] Giữ routing value ổn định trong vòng đời document.
- [ ] Dùng tenant filter riêng nếu routing theo tenant.
- [ ] Cấu hình awareness theo zone/rack nếu yêu cầu availability cần thiết.
- [ ] Theo dõi shard allocation, disk watermark và recovery.
- [ ] Dùng replica để hỗ trợ đọc và dự phòng khi phù hợp.
- [ ] Benchmark với phân bố dữ liệu và traffic gần production.
- [ ] Quản lý thay đổi primary shard qua index mới, split, shrink hoặc reindex.
- [ ] Theo dõi indexing/search latency và rejected count theo shard/node.
- [ ] Có kế hoạch migration khi đổi routing strategy.

Shard chia index thành các phân vùng dữ liệu; replica tạo bản sao để tăng khả năng sẵn sàng và hỗ trợ đọc; routing chọn shard cho document và giới hạn shard tham gia search. Một thiết kế hiệu năng tốt cần cân bằng cả dung lượng, traffic và phạm vi truy vấn. Replica không chữa được primary write hot spot, tăng shard count không tự sửa routing key lệch, và custom routing có thể tạo hot shard nếu một key lớn chiếm phần lớn workload. Hãy đo shard size, indexing/search rate, latency và allocation trước khi thay đổi; chọn routing, partitioning, replica và index lifecycle theo workload thực tế.

