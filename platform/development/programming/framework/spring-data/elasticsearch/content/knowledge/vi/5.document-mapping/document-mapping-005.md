# Cấu hình số shard, replica và refresh interval theo môi trường

Khi tạo một index trong Elasticsearch, ngoài mapping mô tả cấu trúc document, ta còn phải chọn các thiết lập ảnh hưởng đến cách dữ liệu được phân phối, sao chép và hiển thị cho truy vấn. Ba thiết lập thường cần quan tâm là số primary shard, số replica shard và refresh interval.

Các giá trị này tác động trực tiếp đến dung lượng lưu trữ, khả năng chịu lỗi, tốc độ ghi, độ trễ tìm kiếm và chi phí vận hành cluster. Một cấu hình phù hợp cho máy phát triển một node có thể không phù hợp với staging hoặc production có nhiều data node. Vì vậy, ứng dụng Spring Data Elasticsearch cần tách cấu hình index khỏi mã nghiệp vụ và chọn giá trị theo môi trường triển khai.

Sau bài học này, bạn có thể:

- Phân biệt primary shard và replica shard, đồng thời giải thích cách Elasticsearch phân phối shard.
- Ước lượng số primary shard dựa trên dung lượng dữ liệu và workload.
- Chọn số replica phù hợp với topology và yêu cầu sẵn sàng của cluster.
- Giải thích refresh interval và tác động của nó đến độ trễ tìm kiếm cũng như hiệu năng indexing.
- Nhận biết setting nào chỉ cấu hình được khi tạo index và setting nào có thể cập nhật trên index đang chạy.
- Khai báo settings bằng Elasticsearch API, annotation Spring Data Elasticsearch, tệp JSON hoặc cấu hình theo profile.
- Kiểm tra settings thực tế sau khi ứng dụng tạo hoặc cập nhật index.

## 1. Ba thiết lập cần phân biệt

Một index Elasticsearch được chia thành các shard. Mỗi primary shard lưu một phần dữ liệu của index; replica shard là bản sao của primary shard tương ứng. Refresh là quá trình làm cho những thay đổi đã được index trở nên nhìn thấy được trong các thao tác search.

| Thiết lập | Ý nghĩa | Có thể đổi khi index đang mở? |
| --- | --- | --- |
| `index.number_of_shards` | Số primary shard của index | Không; cần xác định khi tạo index |
| `index.number_of_replicas` | Số replica cho mỗi primary shard | Có |
| `index.refresh_interval` | Khoảng thời gian giữa các lần refresh tự động | Có |

Ba thiết lập phục vụ ba mục tiêu khác nhau:

- Số primary shard định hình cách chia dữ liệu và mức song song của index.
- Số replica quyết định số bản sao shard, ảnh hưởng đến khả năng chịu lỗi, dung lượng và khả năng phục vụ search.
- Refresh interval quyết định mức độ trễ giữa lúc ghi document và lúc document có thể được tìm thấy bằng search.

Không nên chọn ba giá trị chỉ dựa trên một môi trường. Hãy xem xét số data node, dung lượng dữ liệu dự kiến, lưu lượng đọc/ghi, mục tiêu phục hồi và yêu cầu về độ mới của kết quả.

## 2. Primary shard và replica shard

### 2.1. Primary shard

Elasticsearch chia dữ liệu của một index thành một hoặc nhiều primary shard. Mỗi shard là một Lucene index độc lập. Khi một document được ghi, Elasticsearch dựa trên routing (mặc định được tính từ document ID) để xác định primary shard chịu trách nhiệm lưu document đó.

Ví dụ, index catalog-products có ba primary shard:

~~~text
catalog-products
├── primary shard 0
├── primary shard 1
└── primary shard 2
~~~

Các primary shard có thể được phân phối trên nhiều data node. Điều này cho phép index lưu lượng dữ liệu lớn hơn khả năng của một shard và phân phối công việc tìm kiếm hoặc indexing qua nhiều node.

Số primary shard là thiết lập quan trọng vì nó xác định cách chia dữ liệu của index. Elasticsearch không cho thay đổi trực tiếp `index.number_of_shards` trên một index đã được tạo, kể cả chỉ đóng index rồi mở lại. Nếu cần một số primary shard khác, thông thường phải tạo index mới với cấu hình mới rồi reindex dữ liệu; trong một số trường hợp có thể dùng API split hoặc shrink khi đáp ứng điều kiện của các thao tác đó.

### 2.2. Replica shard

Replica shard là bản sao của một primary shard. Nếu mỗi primary shard có một replica, một index có ba primary shard sẽ có ba replica shard:

~~~text
catalog-products
├── primary shard 0  ── replica shard 0
├── primary shard 1  ── replica shard 1
└── primary shard 2  ── replica shard 2
~~~

Elasticsearch cố gắng đặt bản sao của cùng một shard trên các node khác nhau. Vì vậy, replica có thể phục vụ truy vấn tìm kiếm và thay thế primary khi node đang giữ primary gặp sự cố, nếu bản sao còn lại được phân bổ và hoạt động bình thường.

Nếu một index có P primary shard và R replica cho mỗi primary shard, tổng số shard copy được phân bổ là:

\[
\text{Tổng shard copy} = P \times (1 + R)
\]

Ví dụ:

| Primary shard | Replica mỗi primary | Tổng shard copy |
| ---: | ---: | ---: |
| 1 | 0 | 1 |
| 1 | 1 | 2 |
| 3 | 1 | 6 |
| 3 | 2 | 9 |
| 5 | 1 | 10 |

Số replica có thể thay đổi khi index đang hoạt động. Tăng replica làm tăng dung lượng lưu trữ và công việc đồng bộ khi ghi, nhưng có thể cải thiện khả năng chịu lỗi và năng lực phục vụ truy vấn đọc. Replica không phải bản backup độc lập; vẫn cần snapshot và quy trình phục hồi dữ liệu.

### 2.3. Phân phối shard trên các node

Giả sử cluster có ba data node và index có ba primary shard cùng một replica:

~~~text
Data node A          Data node B          Data node C
-----------          -----------          -----------
primary 0            replica 0            primary 1
replica 2            primary 2            replica 1
~~~

Đây chỉ là sơ đồ minh họa. Elasticsearch tự quyết định vị trí shard dựa trên trạng thái cluster và các quy tắc allocation. Các bản sao của cùng một shard không được đặt trên cùng một node để replica còn có ích khi node đó mất kết nối.

Nếu cluster chỉ có một data node nhưng index yêu cầu một replica, replica không thể được đặt trên node đang giữ primary tương ứng. Index có thể ở trạng thái yellow vì primary đã được cấp phát nhưng replica chưa được cấp phát. Đây là lý do môi trường local một node thường đặt `number_of_replicas` bằng 0.

Trong production, số replica cần dựa trên số node có thể nhận shard, phân vùng sẵn sàng, yêu cầu chịu lỗi và chính sách vận hành. Có nhiều replica hơn số vị trí có thể cấp phát không tự động làm cluster an toàn hơn; các bản sao không thể được phân phối sẽ ở trạng thái unassigned.

## 3. Chọn số primary shard

### 3.1. Không có một con số đúng cho mọi index

Số primary shard nên được xác định dựa trên:

- Dung lượng dữ liệu dự kiến sau khi indexing và sau các đợt tăng trưởng.
- Số lượng document và kích thước trung bình của document.
- Tốc độ ghi và lưu lượng truy vấn đồng thời.
- Số data node, dung lượng đĩa và tài nguyên CPU/RAM.
- Thời gian chấp nhận được khi phục hồi shard sau sự cố.
- Cách truy vấn thường truy cập một phần dữ liệu hay gần như toàn bộ index.

Quá ít shard có thể khiến một shard trở nên quá lớn, giới hạn khả năng phân phối tải và kéo dài thời gian recovery. Quá nhiều shard nhỏ làm tăng metadata và chi phí quản lý cluster, đồng thời nhiều truy vấn phải fan out tới nhiều shard hơn.

Tài liệu hướng dẫn sizing của Elastic đưa ra khoảng tham khảo thường dùng là khoảng 10 GB đến 50 GB cho mỗi shard và khuyến nghị giữ số document mỗi shard dưới khoảng 200 triệu. Đây là hướng dẫn để bắt đầu đánh giá, không phải giới hạn cứng hay công thức thay thế benchmark. Workload, loại dữ liệu và hạ tầng cụ thể có thể phù hợp với shard nhỏ hơn hoặc lớn hơn.

### 3.2. Ước lượng ban đầu

Có thể ước lượng sơ bộ theo dung lượng dữ liệu primary dự kiến:

\[
\text{Số primary shard ban đầu}
\approx
\left\lceil
\frac{\text{Dung lượng dữ liệu primary dự kiến}}
{\text{Dung lượng mục tiêu mỗi shard}}
\right\rceil
\]

Ví dụ, nếu dữ liệu primary sau indexing dự kiến khoảng 120 GB và nhóm chọn mục tiêu lập kế hoạch khoảng 30 GB mỗi shard, có thể bắt đầu thử nghiệm với bốn primary shard.

Con số này chỉ là điểm khởi đầu. Kích thước dữ liệu JSON đầu vào không nhất thiết bằng kích thước index trên đĩa. Mapping, analyzer, doc values, nén, segment và tỷ lệ cập nhật/xóa đều ảnh hưởng đến dung lượng thực tế. Cần tạo dữ liệu đại diện, đo kích thước shard và benchmark với truy vấn thực tế.

### 3.3. Số shard và khả năng mở rộng

Tăng số primary shard có thể giúp phân phối dữ liệu và công việc trên nhiều node, nhưng không phải cứ tăng shard là search nhanh hơn. Một truy vấn trên index nhiều shard thường phải được thực hiện ở từng shard liên quan rồi tổng hợp kết quả. Khi có quá nhiều shard nhỏ, overhead điều phối có thể lớn hơn lợi ích song song.

Nếu index dự kiến tăng liên tục, hãy xem xét vòng đời index. Với dữ liệu dạng thời gian, data stream kết hợp index template và rollover policy cho phép mỗi backing index có shard count phù hợp. Khi rollover tạo index mới, có thể thay đổi số primary shard trong template cho các index tương lai.

### 3.4. Thay đổi shard count sau khi index đã có dữ liệu

Không thể sửa `index.number_of_shards` bằng Update Index Settings API trên index đang chạy. Khi thiết kế ban đầu chưa phù hợp, các hướng xử lý thường gặp là:

1. Tạo index đích với số primary shard mới.
2. Reindex document từ index cũ sang index mới.
3. Kiểm tra mapping, số lượng document, truy vấn và kết quả tìm kiếm.
4. Chuyển alias đọc/ghi sang index mới.
5. Chỉ xóa index cũ sau khi đã xác nhận quy trình chuyển đổi và chính sách lưu trữ cho phép.

API split có thể tăng số shard trong các điều kiện nhất định; API shrink có thể giảm số shard của index đã được chuẩn bị phù hợp. Cả hai đều có điều kiện vận hành riêng và không phải cách đổi số shard tùy ý. Với nhiều ứng dụng, tạo index mới rồi reindex là cách dễ kiểm soát hơn.

## 4. Chọn số replica

### 4.1. Replica ảnh hưởng đến điều gì?

Replica có ba tác động chính:

**Khả năng chịu lỗi.** Nếu node chứa primary ngừng hoạt động, một replica đã được cấp phát trên node khác có thể được nâng lên thành primary. Thời gian và khả năng phục hồi phụ thuộc trạng thái bản sao, cluster và cơ chế recovery.

**Năng lực đọc.** Search có thể được phân phối tới primary hoặc replica. Replica bổ sung có thể giúp cluster xử lý nhiều truy vấn đọc hơn, tùy workload và tài nguyên node.

**Chi phí ghi và lưu trữ.** Mỗi lần ghi cần được sao chép tới replica. Nhiều replica làm tăng dung lượng lưu trữ và lưu lượng mạng, đồng thời tiêu thụ CPU, disk I/O và tài nguyên recovery.

### 4.2. Chọn replica theo topology

Một bảng định hướng ban đầu:

| Môi trường/topology | Giá trị thường dùng để bắt đầu | Lý do |
| --- | ---: | --- |
| Local một node | 0 | Tránh replica unassigned và trạng thái yellow |
| Test một node tạm thời | 0 | Tiết kiệm tài nguyên, kiểm thử logic |
| Dev cluster nhỏ | 0 hoặc 1 | Phụ thuộc số node và nhu cầu thử nghiệm |
| Staging nhiều node | Giống production | Kiểm thử hành vi phân phối và recovery gần thực tế |
| Production nhiều node | Thường ít nhất 1 | Có bản sao trên node khác để hỗ trợ availability |

Đây là gợi ý ban đầu, không phải cấu hình bắt buộc. Ví dụ, một production cluster một node không thể phân phối replica sang node khác. Ngược lại, một môi trường staging cần mô phỏng production nên có thể cần cùng số replica và topology tương đương production.

Đặt replica bằng 0 làm giảm khả năng chịu lỗi của index. Nếu node duy nhất giữ primary gặp sự cố hoặc dữ liệu shard bị hỏng, không có replica trong cluster để thay thế. Snapshot, backup, giám sát và kế hoạch khôi phục vẫn cần thiết.

### 4.3. Health của cluster và replica

Cluster health thường có ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| green | Tất cả primary và replica shard đều được cấp phát |
| yellow | Tất cả primary shard đã được cấp phát nhưng còn replica chưa được cấp phát |
| red | Có ít nhất một primary shard chưa được cấp phát |

Một index yellow trong local một node có thể chỉ do replica không có node khác để đặt. Tuy nhiên, trong production, yellow kéo dài cần được điều tra vì có thể phản ánh thiếu node, disk watermark, allocation rule hoặc sự cố shard.

Có thể xem trạng thái bằng:

~~~http
GET /_cluster/health/catalog-products
~~~

## 5. Refresh interval là gì?

### 5.1. Refresh làm document có thể tìm kiếm

Khi một document được index hoặc cập nhật, Elasticsearch không nhất thiết làm cho thay đổi đó xuất hiện ngay trong kết quả search. Refresh mở các thay đổi đã được chuẩn bị trong shard để chúng có thể được tìm thấy bằng search.

`index.refresh_interval` quy định khoảng thời gian giữa các lần refresh tự động của shard. Trong Elastic Stack, giá trị mặc định thường là `1s`; trên Elastic Cloud Serverless, mặc định là `5s` và giới hạn tối thiểu cũng khác. Hành vi cụ thể còn phụ thuộc phiên bản và loại dịch vụ, vì vậy hãy kiểm tra tài liệu của môi trường đang sử dụng.

Ví dụ:

~~~json
{
  "index": {
    "refresh_interval": "2s"
  }
}
~~~

Với khoảng refresh dài hơn, dữ liệu mới có thể mất nhiều thời gian hơn trước khi xuất hiện trong search, nhưng Elasticsearch giảm tần suất tạo search-visible segment. Điều này thường giúp cải thiện hiệu năng indexing khi workload ưu tiên ghi.

### 5.2. Refresh không phải flush

Refresh và flush là hai hoạt động khác nhau:

- Refresh làm các thay đổi đã index trở nên nhìn thấy được đối với search.
- Flush tạo Lucene commit và xử lý transaction log theo cơ chế nội bộ của Elasticsearch.

Không nên hiểu refresh interval là khoảng thời gian dữ liệu mới mới được lưu bền vững. Độ bền của thao tác ghi còn liên quan đến translog, cấu hình durability và phản hồi xác nhận của Elasticsearch. Refresh chủ yếu điều khiển search visibility.

### 5.3. Đánh đổi giữa độ mới và hiệu năng

| Refresh interval | Độ trễ search visibility | Tác động thường gặp |
| --- | --- | --- |
| `1s` | Thấp | Search thấy dữ liệu mới nhanh, refresh thường xuyên hơn |
| `5s` | Cao hơn | Giảm tần suất refresh, có thể tăng hiệu năng indexing |
| `30s` | Cao hơn nữa | Phù hợp hơn với workload ghi nhiều, chấp nhận dữ liệu search chậm cập nhật |
| `-1` | Không có refresh tự động | Dùng có kiểm soát trong bulk indexing; cần refresh lại khi hoàn tất |

Giá trị ngắn không phải lúc nào cũng tốt. Refresh thường xuyên tạo thêm segment nhỏ, làm tăng công việc merge và chi phí I/O. Giá trị dài giúp gom nhiều thay đổi hơn giữa các lần refresh nhưng khiến kết quả search chậm cập nhật.

### 5.4. Refresh thủ công và refresh=wait_for

Nếu một luồng nghiệp vụ cần tìm thấy document ngay sau khi ghi, có thể dùng tham số refresh của API ghi:

~~~http
POST /catalog-products/_doc/sku-1001?refresh=wait_for
{
  "sku": "sku-1001",
  "name": "Keyboard"
}
~~~

`refresh=wait_for` chờ lần refresh kế tiếp làm thay đổi trở nên nhìn thấy được. Cách này thường phù hợp hơn việc ép refresh ngay sau từng request bằng `refresh=true`, vì nó có thể chờ lần refresh theo lịch thay vì tạo refresh riêng cho từng lần ghi.

Spring Data Elasticsearch cũng hỗ trợ tùy chọn refresh trong một số API lưu/index thông qua các tùy chọn tương ứng của phiên bản đang dùng. Khi cần đảm bảo read-after-write, hãy chọn chính sách refresh theo API thực tế và đo ảnh hưởng đến throughput.

Không nên gọi refresh thủ công sau mọi lần lưu document. Điều đó có thể biến một luồng ghi nhiều thành chuỗi refresh liên tục, làm giảm hiệu năng của cluster.

### 5.5. Tắt refresh trong bulk indexing

Khi nạp lượng lớn dữ liệu ban đầu, có thể tạm đặt refresh interval thành `-1` để tắt refresh tự động:

~~~http
PUT /catalog-products/_settings
{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

Sau khi hoàn tất bulk indexing, khôi phục refresh interval và yêu cầu refresh:

~~~http
PUT /catalog-products/_settings
{
  "index": {
    "refresh_interval": "1s"
  }
}
~~~

~~~http
POST /catalog-products/_refresh
~~~

Chỉ nên dùng quy trình này cho giai đoạn bulk có kiểm soát. Nếu quên khôi phục refresh interval, document mới có thể không xuất hiện trong search cho đến khi có refresh thủ công. Cũng cần cân nhắc các client khác đang đọc index trong thời gian nạp dữ liệu.

## 6. Cấu hình index settings khi tạo index

### 6.1. Tạo index bằng Elasticsearch API

Có thể khai báo settings cùng mapping trong Create Index API:

~~~http
PUT /catalog-products-v1
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "refresh_interval": "1s"
  },
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

Trong ví dụ, index có ba primary shard, mỗi primary có một replica và refresh tự động mỗi giây. Khi có đủ data node để phân phối, tổng cộng có sáu shard copy.

Settings ở thời điểm tạo index là nơi quyết định số primary shard. Hãy chuẩn bị mapping và settings cùng nhau để tránh index được tạo trước với cấu hình mặc định rồi mới phát hiện cần thay đổi shard count.

### 6.2. Cập nhật các setting động

Có thể cập nhật replica và refresh interval trên index hiện có bằng Update Index Settings API:

~~~http
PUT /catalog-products-v1/_settings
{
  "index": {
    "number_of_replicas": 2,
    "refresh_interval": "5s"
  }
}
~~~

Request trên thay số replica từ một lên hai và refresh interval thành năm giây. Không thể thêm `number_of_shards` vào request để đổi primary shard count của index hiện có.

Nếu muốn trả một setting về mặc định, Elasticsearch hỗ trợ đặt giá trị của setting đó thành null trong Update Index Settings API. Hãy cân nhắc giá trị mặc định của đúng phiên bản và dịch vụ trước khi dùng cách này.

### 6.3. Phân loại setting

| Setting | Loại | Cách thay đổi |
| --- | --- | --- |
| `index.number_of_shards` | Static | Khi tạo index; thay đổi cấu trúc cần thao tác split, shrink hoặc tạo index mới |
| `index.number_of_replicas` | Dynamic | Update Index Settings API |
| `index.refresh_interval` | Dynamic | Update Index Settings API |

Việc thay đổi replica hoặc refresh interval có hiệu lực trên index đang chạy, nhưng không có nghĩa ứng dụng tự áp dụng giá trị mới chỉ vì profile YAML đã đổi. Cần có quy trình gửi cập nhật tới Elasticsearch hoặc tạo index mới theo cấu hình đó.

## 7. Khai báo settings trong Spring Data Elasticsearch

Spring Data Elasticsearch có thể tạo settings từ annotation hoặc tệp JSON. Khi cần chọn giá trị theo profile, có thể kết hợp cấu hình Spring Boot với IndexOperations để tạo index theo giá trị đã được bind.

### 7.1. Dùng @Setting cho cấu hình cố định

Với index có cấu hình giống nhau ở mọi môi trường, có thể khai báo trực tiếp:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "catalog-products")
@Setting(
    shards = 3,
    replicas = 1,
    refreshInterval = "1s"
)
public class ProductDocument {
    // Các trường document
}
~~~

Các thuộc tính thường dùng của @Setting:

- `shards`: số primary shard khi tạo index.
- `replicas`: số replica cho mỗi primary shard khi tạo index.
- `refreshInterval`: refresh interval khi tạo index.
- `settingPath`: đường dẫn classpath tới tệp JSON chứa settings.
- `useServerConfiguration`: không gửi settings từ entity để Elasticsearch dùng cấu hình phía server.

Giá trị mặc định được Spring Data Elasticsearch công bố cho annotation hiện hành là một shard, một replica và refresh interval `1s`. Giá trị mặc định của Elasticsearch và hành vi dịch vụ có thể khác; hãy khai báo rõ các giá trị quan trọng thay vì dựa vào mặc định ngầm.

@Setting được dùng khi Spring Data tạo index. Nếu index đã tồn tại, thay đổi annotation rồi khởi động lại ứng dụng không tự thay đổi settings của index hiện tại. Cần kiểm tra và cập nhật bằng API quản lý index.

### 7.2. Dùng tệp JSON settings

Khi có nhiều thiết lập hoặc muốn quản lý settings ngoài annotation, có thể dùng `settingPath`:

~~~java
@Document(indexName = "catalog-products")
@Setting(settingPath = "/elasticsearch/settings/catalog-settings.json")
public class ProductDocument {
    // Các trường document
}
~~~

Ví dụ tệp `src/main/resources/elasticsearch/settings/catalog-settings.json`:

~~~json
{
  "index": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "refresh_interval": "1s"
  }
}
~~~

Spring Data đọc tệp settings từ classpath khi tạo index. Tài liệu Spring Data hiện hành cũng hỗ trợ SpEL expression cho `settingPath`, vì vậy có thể chọn resource theo bean hoặc cấu hình môi trường nếu dự án chủ động thiết kế cách phân giải đó. Với ứng dụng cần logic chọn profile rõ ràng, cấu hình bằng `@ConfigurationProperties` và IndexOperations thường dễ kiểm soát hơn.

### 7.3. Để server hoặc index template quản lý settings

Nếu cluster administrator quản lý settings bằng index template, entity có thể dùng:

~~~java
@Document(indexName = "catalog-products")
@Setting(useServerConfiguration = true)
public class ProductDocument {
    // Các trường document
}
~~~

`useServerConfiguration = true` yêu cầu Spring Data không gửi settings của entity khi tạo index. Khi đó, settings có thể đến từ cấu hình phía Elasticsearch, chẳng hạn index template khớp với tên index. Cách này hữu ích khi nhiều ứng dụng cần tuân theo một chuẩn index do đội vận hành quản lý.

### 7.4. Tạo index với settings lấy từ Spring Profile

Khi local, dev, staging và production cần các giá trị khác nhau, có thể bind chúng thành một class cấu hình:

~~~java
package com.example.catalog.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.elasticsearch.index")
public class ProductIndexProperties {

    private int shards = 1;
    private int replicas = 0;
    private String refreshInterval = "1s";

    public int getShards() {
        return shards;
    }

    public void setShards(int shards) {
        this.shards = shards;
    }

    public int getReplicas() {
        return replicas;
    }

    public void setReplicas(int replicas) {
        this.replicas = replicas;
    }

    public String getRefreshInterval() {
        return refreshInterval;
    }

    public void setRefreshInterval(String refreshInterval) {
        this.refreshInterval = refreshInterval;
    }
}
~~~

Đăng ký cấu hình bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(ProductIndexProperties.class)` trong một lớp configuration:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Sau đó dùng ElasticsearchOperations và IndexOperations để tạo index với settings đang có hiệu lực:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.ApplicationRunner;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.document.Document;

@Configuration
public class ProductIndexConfiguration {

    @Bean
    ApplicationRunner createProductIndex(
            ElasticsearchOperations operations,
            ProductIndexProperties properties) {

        return args -> {
            IndexOperations indexOperations =
                operations.indexOps(ProductDocument.class);

            if (!indexOperations.exists()) {
                Map<String, Object> settings = Map.of(
                    "index", Map.of(
                        "number_of_shards", properties.getShards(),
                        "number_of_replicas", properties.getReplicas(),
                        "refresh_interval", properties.getRefreshInterval()
                    )
                );

                Document mapping = indexOperations.createMapping();
                indexOperations.create(settings, mapping);
            }
        };
    }
}
~~~

Đoạn mã minh họa API `IndexOperations.create(settings, mapping)`: mapping được sinh từ annotation của ProductDocument, còn settings lấy từ cấu hình đã bind theo profile. Nếu index chưa tồn tại, ứng dụng tạo index với cả hai phần.

Trong dự án thực tế, nên đặt trách nhiệm tạo index vào migration hoặc một bước bootstrap có kiểm soát, đặc biệt khi chạy nhiều instance ứng dụng cùng lúc. Nếu nhiều instance đồng thời kiểm tra `exists()` rồi tạo index, có thể xảy ra tranh chấp tạo index. Ứng dụng runtime cũng không nhất thiết phải có quyền quản trị index.

Đặt `createIndex = false` trên @Document nếu muốn Spring Data không tự tạo index theo annotation khi bootstrap repository:

~~~java
@Document(indexName = "catalog-products", createIndex = false)
public class ProductDocument {
    // Các trường document
}
~~~

Khi dùng cách này, migration hoặc thành phần bootstrap phải bảo đảm index đã được tạo trước khi repository sử dụng nó.

## 8. Cấu hình theo môi trường bằng application.yml

### 8.1. Cấu hình mặc định

Tệp `src/main/resources/application.yml` có thể chứa cấu hình chung:

~~~yaml
spring:
  application:
    name: catalog-service

app:
  elasticsearch:
    index:
      shards: 1
      replicas: 0
      refresh-interval: 1s
~~~

### 8.2. Local một node

Tệp `application-local.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200

app:
  elasticsearch:
    index:
      shards: 1
      replicas: 0
      refresh-interval: 1s
~~~

Một primary shard thường đủ cho dữ liệu local nhỏ. Replica bằng 0 tránh trạng thái yellow do không có node thứ hai. Refresh một giây giúp quan sát kết quả tìm kiếm gần như ngay sau khi ghi trong quá trình phát triển.

### 8.3. Development

Tệp `application-dev.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

app:
  elasticsearch:
    index:
      shards: 1
      replicas: 0
      refresh-interval: 2s
~~~

Giá trị dev phụ thuộc số data node và mục tiêu của cluster dùng chung. Nếu dev có nhiều node và cần thử replica allocation, có thể đặt replica bằng một. Nếu ưu tiên tiết kiệm tài nguyên, giữ replica bằng không.

### 8.4. Staging

Tệp `application-staging.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

app:
  elasticsearch:
    index:
      shards: 3
      replicas: 1
      refresh-interval: 1s
~~~

Staging nên mô phỏng topology production khi cần kiểm thử phân phối shard, recovery và tải truy vấn. Các con số trong ví dụ chỉ để minh họa cách override cấu hình; cần thay bằng kết quả sizing của hệ thống.

### 8.5. Production

Tệp `application-prod.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

app:
  elasticsearch:
    index:
      shards: 3
      replicas: 1
      refresh-interval: 1s
~~~

Trong production, số shard phải dựa trên dung lượng và benchmark. Replica phải phù hợp với số data node, failure domain và mục tiêu availability. Refresh interval phải dựa trên yêu cầu độ mới của search và throughput indexing. Không sao chép nguyên các con số minh họa nếu chưa đánh giá workload.

Kích hoạt profile bằng biến môi trường hoặc tham số dòng lệnh:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Các biến endpoint và credentials phải được cấp từ môi trường triển khai hoặc secret manager. Không lưu mật khẩu thật trong application-{profile}.yml được commit vào repository.

### 8.6. Thay đổi profile có cập nhật index đã tồn tại không?

Đây là điểm quan trọng khi triển khai. Profile chỉ quyết định giá trị Spring bind vào ứng dụng. Việc đổi từ local sang production hoặc đổi replicas từ 0 lên 1 không tự thay đổi settings của index đã tồn tại.

Có ba tình huống:

1. **Index chưa tồn tại:** bước tạo index có thể dùng settings theo profile hiện tại.
2. **Index đã tồn tại, setting dynamic thay đổi:** cần gọi Update Index Settings API hoặc quy trình quản trị tương ứng để cập nhật replica và refresh interval.
3. **Index đã tồn tại, primary shard count thay đổi:** cần tạo index mới với shard count mới rồi chuyển dữ liệu bằng reindex hoặc thao tác split/shrink phù hợp.

Vì vậy, không nên chỉ dựa vào việc restart ứng dụng với profile mới để kết luận index đã nhận settings mới. Luôn đọc settings thực tế từ Elasticsearch.

## 9. Dùng index template để chuẩn hóa settings

Index template cho phép áp dụng settings và mappings cho các index mới có tên khớp với pattern. Đây là cách phù hợp khi đội vận hành muốn quản lý shard count, replica và refresh interval ở phía Elasticsearch thay vì để từng ứng dụng tự tạo index.

Ví dụ tạo composable index template:

~~~http
PUT /_index_template/catalog-prod-template
{
  "index_patterns": ["catalog-products-prod-*"],
  "priority": 200,
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "refresh_interval": "1s"
    }
  }
}
~~~

Khi tạo index tên `catalog-products-prod-v1`, template phù hợp có thể cung cấp các settings mặc định. Có thể tạo template riêng cho local, dev, staging và production bằng pattern tương ứng, hoặc dùng component template chung kết hợp với index template theo môi trường.

Ví dụ, nếu ứng dụng dùng `@Setting(useServerConfiguration = true)`, Spring Data không gửi settings từ entity. Khi đó, index template có thể là nguồn quản lý settings thống nhất. Hãy đảm bảo index name thực tế khớp pattern và template có priority phù hợp nếu nhiều template cùng khớp.

Index template chỉ áp dụng khi tạo index mới. Thay đổi template không tự cập nhật settings của index đã được tạo trước đó. Các index hiện hữu cần được cập nhật riêng nếu setting đó hỗ trợ thay đổi động.

## 10. Theo dõi và kiểm tra settings thực tế

Không nên chỉ kiểm tra application.yml hoặc annotation. Hãy đọc settings mà Elasticsearch đang sử dụng.

### 10.1. Xem settings của index

~~~http
GET /catalog-products/_settings?include_defaults=true
~~~

Request này trả về settings hiện tại và có thể kèm các giá trị mặc định. Khi so sánh giữa môi trường, hãy phân biệt setting được khai báo tường minh với setting do Elasticsearch mặc định.

### 10.2. Xem số shard và kích thước

~~~http
GET /_cat/shards/catalog-products?v=true&h=index,shard,prirep,state,store,node
~~~

Kết quả giúp quan sát primary (p) và replica (r), trạng thái phân bổ, kích thước shard và node đang giữ shard.

Có thể xem tổng quan index:

~~~http
GET /_cat/indices/catalog-products?v=true
~~~

### 10.3. Theo dõi cluster health

~~~http
GET /_cluster/health/catalog-products
~~~

Theo dõi các chỉ số:

- active_primary_shards: số primary shard đang hoạt động.
- active_shards: tổng số shard copy đang hoạt động.
- unassigned_shards: số shard chưa được cấp phát.
- relocating_shards: số shard đang được di chuyển.
- initializing_shards: số shard đang khởi tạo.
- status: green, yellow hoặc red.

### 10.4. Kiểm tra ảnh hưởng của refresh interval

Hãy đo cả tốc độ ghi và độ trễ search visibility. Một bài kiểm thử có thể:

1. Ghi một tập document đại diện.
2. Ghi lại thời điểm request được xác nhận.
3. Thực hiện truy vấn cho đến khi document xuất hiện.
4. Đo thời gian chờ và throughput indexing.
5. Lặp lại với một số refresh interval khác nhau.

Kết quả cần phản ánh workload thật: kích thước document, mapping, số shard, replica, lượng request đồng thời và tài nguyên node. Đừng chỉ dựa vào một phép thử đơn lẻ trên máy phát triển.

## 11. Những lỗi cấu hình thường gặp

**Đặt quá nhiều primary shard cho index nhỏ.** Nhiều shard nhỏ làm tăng overhead và fan out của search. Hãy ước lượng dữ liệu, đo kích thước shard và benchmark trước khi chọn số lượng.

**Đặt quá ít shard cho index tăng trưởng lớn.** Một shard quá lớn có thể làm recovery lâu và giới hạn khả năng phân phối dữ liệu. Theo dõi tốc độ tăng trưởng và chuẩn bị chiến lược rollover hoặc reindex.

**Giữ replica bằng một trong cluster chỉ có một data node.** Replica không thể được đặt cùng node với primary, dẫn đến trạng thái yellow. Dùng replica bằng không trong môi trường đơn node nếu chấp nhận không có bản sao trong cluster.

**Đặt replica bằng không ở production mà không có kế hoạch chịu lỗi.** Khi mất primary hoặc dữ liệu bị hỏng, không có replica để thay thế. Hãy đánh giá SLA, node topology và snapshot trước khi quyết định.

**Cho rằng tăng replica làm tăng dung lượng primary.** Replica là bản sao của shard, không làm tăng dung lượng dữ liệu primary mà index có thể lưu. Nó tăng tổng dung lượng và có thể tăng năng lực đọc.

**Cho rằng đổi number_of_shards qua PUT _settings sẽ có hiệu lực.** Đây là setting tĩnh. Cần tạo index mới và chuyển dữ liệu hoặc dùng thao tác split/shrink trong điều kiện phù hợp.

**Đặt refresh interval quá ngắn cho workload ghi lớn.** Refresh thường xuyên tạo thêm công việc segment và merge. Hãy đo throughput và độ trễ search trước khi chọn.

**Tắt refresh rồi quên bật lại.** Document có thể tiếp tục được ghi nhưng không tự xuất hiện trong search. Hãy quản lý thao tác bulk bằng quy trình có bước khôi phục setting và refresh cuối cùng.

**Gọi refresh thủ công sau từng lần ghi.** Điều này làm tăng overhead và có thể giảm throughput. Nếu cần read-after-write, cân nhắc refresh=wait_for.

**Nghĩ rằng thay application-prod.yml sẽ cập nhật index cũ.** Profile chỉ thay đổi cấu hình ứng dụng. Cần kiểm tra index tồn tại hay chưa và thực hiện update settings hoặc reindex theo loại setting.

**Dùng annotation @Setting như một cơ chế migration.** @Setting cung cấp giá trị khi Spring Data tạo index. Nó không tự thay đổi settings đã có trên index hiện hữu.

## 12. Quy trình chọn và triển khai settings

Khi tạo index mới cho ứng dụng Spring Data Elasticsearch, có thể đi theo trình tự:

1. Xác định dữ liệu dự kiến, tốc độ tăng trưởng, kích thước document và thời gian lưu trữ.
2. Xác định topology cluster: số data node, failure domain, tài nguyên và yêu cầu availability.
3. Ước lượng số primary shard ban đầu theo dung lượng primary và mục tiêu kích thước shard.
4. Chọn số replica theo khả năng phân phối shard và mục tiêu chịu lỗi.
5. Xác định độ trễ search visibility mà nghiệp vụ chấp nhận để chọn refresh interval.
6. Đưa các giá trị vào cấu hình theo profile hoặc index template.
7. Tạo index với settings và mapping được quản lý cùng nhau.
8. Kiểm tra settings, mapping, shard allocation và cluster health sau khi tạo.
9. Benchmark bằng dữ liệu và truy vấn đại diện ở staging hoặc môi trường gần production.
10. Theo dõi shard size, số shard trên node, indexing throughput, search latency và trạng thái allocation.
11. Nếu chỉ replica hoặc refresh interval cần đổi, cập nhật setting động và xác nhận kết quả.
12. Nếu primary shard count cần đổi, lập kế hoạch tạo index mới, reindex/split/shrink và chuyển alias.

Các con số cụ thể cần được xác nhận bằng dữ liệu và benchmark. Cấu hình local thường ưu tiên đơn giản và tiết kiệm tài nguyên; staging nên mô phỏng production; production cần cân bằng giữa dung lượng, độ sẵn sàng, throughput và độ mới của kết quả tìm kiếm.

## 13. Tài liệu tham khảo

- [Elasticsearch - General index settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules): phân loại static và dynamic settings, số replica và refresh interval.
- [Elastic - Size your Elasticsearch shards](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/size-shards): hướng dẫn sizing, ảnh hưởng của oversharding và cách điều chỉnh shard strategy.
- [Elasticsearch - Update index settings API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-put-settings): cập nhật các dynamic index settings.
- [Spring Data Elasticsearch - Index settings](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html): dùng @Setting, settingPath và useServerConfiguration.
- [Spring Data Elasticsearch - IndexOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/IndexOperations.html): tạo index với settings và mapping.

Khi vận hành thực tế, hãy đối chiếu tài liệu với phiên bản Elasticsearch và Spring Data Elasticsearch mà ứng dụng đang dùng. Default và giới hạn của Elastic Stack, Elastic Cloud Serverless và các phiên bản khác nhau có thể không giống nhau.
