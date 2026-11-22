# Phân biệt refresh với flush và độ bền dữ liệu

Trong Elasticsearch, một document có thể đã được ghi thành công nhưng chưa xuất hiện trong kết quả tìm kiếm ngay lập tức. Điều này không nhất thiết có nghĩa dữ liệu bị mất. Elasticsearch tách việc làm dữ liệu **có thể tìm kiếm** khỏi việc ghi nhận dữ liệu **bền vững để khôi phục sau sự cố**.

Ba khái niệm cần phân biệt:

- **Refresh:** mở một searcher mới để các thay đổi gần đây có thể được nhìn thấy qua Search API. Đây là cơ chế tạo tính nhất quán gần thời gian thực (near real-time).
- **Flush:** thực hiện Lucene commit và bắt đầu một translog generation mới. Nó giúp hoàn tất commit của index và quản lý translog; Elasticsearch thường tự thực hiện khi cần.
- **Durability:** khả năng giữ lại thao tác đã được xác nhận sau khi node hoặc tiến trình gặp sự cố. Elasticsearch dựa vào transaction log (translog), cơ chế đồng bộ xuống đĩa và replication để hỗ trợ mục tiêu này.

Refresh không phải flush. Flush cũng không phải cơ chế backup. Một lần refresh làm dữ liệu dễ tìm kiếm hơn nhưng không tự tạo ra bảo đảm durability; một lần flush tạo Lucene commit nhưng không thay thế chính sách snapshot và khôi phục.

## 1. Vì sao ghi thành công nhưng Search chưa thấy document?

Elasticsearch được tối ưu cho tìm kiếm và ghi dữ liệu với thông lượng cao. Thay vì tạo một Lucene commit cho từng thao tác ghi, Elasticsearch gom thay đổi và định kỳ refresh để mở searcher mới.

Ví dụ:

1. Ứng dụng gửi request index một sản phẩm.
2. Elasticsearch xử lý thao tác ghi và ghi thông tin cần thiết vào translog.
3. Request trả về thành công.
4. Searcher hiện tại vẫn có thể đang đọc snapshot cũ.
5. Sau refresh tiếp theo, document mới xuất hiện trong kết quả Search API.

Vì vậy, có thể xảy ra tình huống:

- `GET /products/_doc/42` đọc document theo ID và nhìn thấy dữ liệu mới.
- `GET /products/_search` chưa tìm thấy document đó vì shard chưa refresh.

Get API theo ID là real-time theo mặc định, còn Search API là near real-time. Hai API có semantics khác nhau; không nên dùng kết quả Search ngay sau write làm cách duy nhất để xác định request ghi có thành công hay không.

## 2. Refresh là gì?

Refresh làm các thay đổi đã được xử lý trong index trở nên nhìn thấy đối với những search request tiếp theo. Về mặt Lucene, refresh mở một searcher mới trên các segment đã được tạo từ dữ liệu mới.

Refresh không yêu cầu tạo một Lucene commit đầy đủ cho mỗi lần. Nó là thao tác làm mới góc nhìn tìm kiếm, được thiết kế để diễn ra thường xuyên hơn commit.

Luồng khái quát:

~~~text
Index / update / delete request
             |
             v
       Ghi thay đổi
             |
             v
    Translog + indexing buffer
             |
             v
          Refresh
             |
             v
      Mở searcher mới
             |
             v
  Search thấy document mới
~~~

Refresh chủ yếu giải quyết visibility (khả năng nhìn thấy qua Search API), không phải là ranh giới durability.

### 2.1. Refresh interval

Index có thiết lập `index.refresh_interval` để xác định chu kỳ refresh tự động. Giá trị mặc định thường là `1s` trong cấu hình thông thường, nhưng hành vi cụ thể còn phụ thuộc phiên bản và trạng thái hoạt động của index.

Không nên hiểu refresh interval là cam kết mọi document sẽ xuất hiện chính xác sau một giây. Thời gian thực tế còn phụ thuộc tải cluster, hoạt động shard và việc refresh có được kích hoạt hay không. Elasticsearch cũng có cơ chế tối ưu cho index không được tìm kiếm gần đây, vì vậy index ít hoạt động có thể không refresh nền liên tục như index đang được search.

Có thể đọc setting:

~~~http
GET /products/_settings?filter_path=*.settings.index.refresh_interval
~~~

Đặt interval dài hơn:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "5s"
  }
}
~~~

Interval dài hơn có thể tăng hiệu quả indexing vì giảm số lần refresh, nhưng kết quả Search sẽ trễ hơn. Chọn giá trị dựa trên yêu cầu freshness của ứng dụng và tải thực tế.

### 2.2. Refresh thủ công

Có thể yêu cầu refresh một index:

~~~http
POST /products/_refresh
~~~

Sau khi API hoàn tất, những thay đổi đã được xử lý trên các shard liên quan sẽ có thể nhìn thấy qua Search API.

Refresh thủ công hữu ích trong:

- Integration test cần kiểm tra Search ngay sau khi ghi.
- Quy trình import có điểm kết thúc rõ ràng.
- Tác vụ quản trị cần chủ động làm mới visibility.

Không nên gọi refresh sau từng document trong luồng ghi thông thường. Refresh quá thường xuyên tạo nhiều segment nhỏ, tăng chi phí merge và làm giảm indexing throughput.

## 3. Các giá trị refresh trong write API

Nhiều write API của Elasticsearch hỗ trợ tham số `refresh` với ba giá trị chính:

| Giá trị | Hành vi | Khi cân nhắc |
|---|---|---|
| `false` | Không yêu cầu refresh riêng cho request; dùng hành vi refresh tự động | Mặc định cho hầu hết luồng ghi |
| `true` | Refresh ngay các shard liên quan để thay đổi có thể được Search nhìn thấy khi request hoàn tất | Chỉ dùng khi thực sự cần visibility tức thời |
| `wait_for` | Chờ refresh kế tiếp làm thay đổi của request có thể nhìn thấy, không chủ động ép refresh ngay | Read-after-write cần visibility nhưng muốn tránh refresh riêng cho từng request |

Ví dụ refresh ngay:

~~~http
PUT /products/_doc/42?refresh=true
Content-Type: application/json

{
  "name": "Keyboard",
  "status": "ACTIVE"
}
~~~

Ví dụ chờ refresh kế tiếp:

~~~http
PUT /products/_doc/43?refresh=wait_for
Content-Type: application/json

{
  "name": "Mouse",
  "status": "ACTIVE"
}
~~~

`refresh=wait_for` thường là lựa chọn phù hợp hơn khi caller phải tìm thấy dữ liệu ngay sau write nhưng không muốn ép một refresh mới cho từng request. Request chỉ hoàn tất sau khi refresh phù hợp xảy ra.

Nếu refresh tự động bị tắt bằng `index.refresh_interval: -1`, một request `wait_for` có thể phải chờ cho đến khi có refresh thủ công hoặc cơ chế khác làm dữ liệu visible. Đừng tắt refresh rồi kỳ vọng `wait_for` tự làm index refresh.

### 3.1. Tác động của refresh=true

`refresh=true` có thể tạo refresh ngay trên các shard liên quan. Nếu ứng dụng gửi nhiều write request riêng lẻ với tùy chọn này, cluster phải refresh liên tục, có thể:

- Tăng số segment nhỏ.
- Tăng công việc merge.
- Tăng CPU và I/O.
- Giảm throughput của indexing.
- Tạo latency cao hơn cho các request khác.

Nếu cần ghi nhiều document, ưu tiên gom thành Bulk API rồi chọn một chính sách refresh phù hợp cho cả batch. Tránh refresh mỗi item.

### 3.2. Refresh listener và wait_for

`wait_for` cần đăng ký chờ refresh. Nếu có rất nhiều request cùng chờ trong khi refresh bị trì hoãn hoặc bị tắt, số listener có thể tăng và chạm giới hạn cấu hình của shard.

Vì vậy:

- Không dùng `wait_for` vô hạn cho workload có lưu lượng rất cao mà không đo đạc.
- Đảm bảo refresh interval phù hợp.
- Không giữ refresh bị tắt trong khi có request đang chờ visibility.
- Theo dõi timeout và lỗi liên quan đến refresh listener.
- Dùng batch nếu nhiều document thuộc cùng một quy trình ghi.

## 4. Flush là gì?

Flush trong Elasticsearch thực hiện một Lucene commit và bắt đầu một translog generation mới. Khi commit hoàn tất, các thao tác đã được ghi vào Lucene index có thể được quản lý độc lập với translog generation cũ, cho phép Elasticsearch loại bỏ translog không còn cần cho recovery.

Luồng khái quát:

~~~text
Index / update / delete
          |
          v
       Translog
          |
          v
    Refresh (nếu cần)
          |
          v
      Lucene segments
          |
          v
         Flush
          |
          +----> Lucene commit
          |
          +----> Translog generation mới
          |
          v
 Có thể trim translog cũ khi an toàn
~~~

Flush là một bước quản lý commit và translog, không phải cách để ép Search API nhìn thấy dữ liệu. Refresh và flush có mục đích riêng.

### 4.1. Flush API

Có thể yêu cầu flush một index:

~~~http
POST /products/_flush
~~~

Elasticsearch thường tự flush theo ngưỡng và điều kiện nội bộ. Trong ứng dụng thông thường, hiếm khi cần gọi flush thủ công sau mỗi lần ghi.

Flush thủ công có thể hữu ích trong một số quy trình vận hành đặc biệt, nhưng không nên được dùng như một thao tác dọn dẹp định kỳ của business service. Hãy để Elasticsearch quản lý flush tự động trừ khi có yêu cầu vận hành đã được đo đạc và kiểm chứng.

### 4.2. Flush không giống refresh

| Tiêu chí | Refresh | Flush |
|---|---|---|
| Mục tiêu | Làm thay đổi visible qua Search API | Lucene commit và chuyển translog generation |
| Tần suất | Thường xuyên hơn, theo refresh interval hoặc request | Ít thường xuyên hơn, do Elasticsearch tự quản lý |
| Ảnh hưởng chính | Search visibility | Commit và vòng đời translog/recovery |
| Có phải backup? | Không | Không |
| Gọi sau từng document? | Thường không nên | Không nên |

Một thao tác flush không phải cách thay thế cho `refresh=wait_for`. Nếu mục tiêu là ghi xong rồi Search thấy ngay, dùng chính sách refresh phù hợp.

### 4.3. Flush không phải force merge

Flush cũng khác force merge:

- Flush tạo Lucene commit và translog generation mới.
- Force merge hợp nhất các Lucene segment để giảm số segment, thường dùng cho index ít thay đổi hoặc đã hoàn tất ghi.

Không dùng force merge sau mỗi lần flush. Force merge có thể tạo tải I/O và CPU lớn, đồng thời không phải điều kiện để dữ liệu có thể tìm kiếm hoặc bền vững.

## 5. Translog và độ bền dữ liệu

Translog (transaction log) ghi lại các thao tác ghi của Elasticsearch. Nó giúp khôi phục những thay đổi chưa nằm trong một Lucene commit hoàn chỉnh khi node khởi động lại sau sự cố.

Một cách hình dung:

- Lucene index segments phục vụ tìm kiếm.
- Translog giữ thông tin thao tác ghi cần thiết cho recovery.
- Refresh làm searcher thấy dữ liệu mới.
- Flush tạo commit và chuyển translog generation.

Translog là một phần quan trọng của durability. Một document có thể chưa visible qua Search nhưng thao tác ghi đã được ghi bền vững trong translog theo chính sách durability của index.

### 5.1. index.translog.durability

Elasticsearch có setting `index.translog.durability` với hai chế độ thường gặp:

| Chế độ | Hành vi |
|---|---|
| `request` | Đồng bộ translog xuống storage trước khi xác nhận write request thành công |
| `async` | Đồng bộ theo chu kỳ `index.translog.sync_interval`, nên có một khoảng thời gian các thao tác đã được xác nhận có thể chưa được fsync |

`request` là giá trị mặc định trong cấu hình thông thường và phù hợp khi ưu tiên durability. `async` có thể tăng hiệu năng ghi trong một số workload, nhưng chấp nhận rủi ro mất các thao tác kể từ lần sync gần nhất nếu node hoặc máy bị sự cố nghiêm trọng.

Kiểm tra setting:

~~~http
GET /products/_settings?filter_path=*.settings.index.translog
~~~

Ví dụ cấu hình request durability:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "translog": {
      "durability": "request"
    }
  }
}
~~~

Nếu chọn async, cần hiểu rõ `sync_interval`, mức mất dữ liệu có thể chấp nhận và loại sự cố mà hệ thống cần chịu được. Không thay đổi setting chỉ để cải thiện benchmark mà chưa đánh giá tác động tới dữ liệu.

### 5.2. fsync và xác nhận write

Với `request`, Elasticsearch đồng bộ translog xuống storage theo chính sách trước khi trả xác nhận cho write request. Điều này giúp bảo vệ thao tác trước các tình huống tiến trình hoặc node dừng đột ngột, với điều kiện storage và hạ tầng thực hiện đúng cam kết flush/fsync.

Độ bền cuối cùng còn phụ thuộc:

- Chất lượng và cấu hình storage.
- Tình trạng filesystem và thiết bị lưu trữ.
- Replication và khả năng phục hồi shard.
- Cấu hình active shard copies khi ghi.
- Quy trình backup và snapshot.

Không nên diễn giải một HTTP 200 là bảo đảm tuyệt đối trước mọi loại lỗi phần cứng, mất toàn bộ cluster hoặc lỗi vận hành. Cần thiết kế cả replication, snapshot và quy trình restore.

## 6. Refresh, flush và translog trong cùng một vòng đời

Một chuỗi sự kiện khái quát:

~~~text
1. Client gửi index/update/delete
          |
          v
2. Elasticsearch xử lý thao tác và ghi translog
          |
          v
3. Theo durability=request, đồng bộ translog
          |
          v
4. Write response được trả về
          |
          +---------------------------+
          |                           |
          v                           v
5a. Refresh                     5b. Flush
    mở searcher mới                 Lucene commit
    Search thấy dữ liệu             translog generation mới
          |                           |
          v                           v
   Visibility thay đổi          Recovery log được quản lý
~~~

Refresh và flush có thể xảy ra ở những thời điểm khác nhau. Không nên giả định mọi refresh đều đi kèm flush hoặc mỗi flush đều được gọi để đáp ứng một request search.

## 7. Read-after-write trong ứng dụng

Một số luồng nghiệp vụ cần ghi xong rồi đọc lại ngay, ví dụ:

- Tạo sản phẩm và chuyển sang trang chi tiết có dùng Search API.
- Cập nhật trạng thái đơn hàng rồi chạy một truy vấn tìm kiếm ngay.
- Import dữ liệu rồi kiểm tra bằng aggregation.

Trước hết hãy xác định cách đọc:

- Nếu đọc theo ID bằng Get API, mặc định thao tác get là real-time và thường có thể thấy write mới mà không cần refresh.
- Nếu đọc bằng Search API, cần chờ refresh làm thay đổi visible.
- Nếu chỉ cần phản hồi kết quả của thao tác ghi, có thể dùng response write thay vì query lại Elasticsearch.

### 7.1. Dùng refresh=wait_for

Ví dụ một write cần Search thấy ngay sau khi request hoàn tất:

~~~http
POST /products/_update/42?refresh=wait_for
Content-Type: application/json

{
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

Sau khi request hoàn tất, refresh phù hợp đã xảy ra để cập nhật có thể được nhìn thấy trong Search. Đây là lựa chọn hữu ích cho read-after-write qua Search khi muốn tránh ép refresh ngay lập tức.

Không nên thêm `refresh=wait_for` vào mọi thao tác ghi nếu caller không cần Search visibility ngay. Mỗi request chờ refresh có thể làm tăng latency của ứng dụng.

### 7.2. Dùng GET khi biết document ID

Nếu chỉ cần xác nhận document vừa ghi, dùng Get API:

~~~http
GET /products/_doc/42
~~~

Get API theo ID là real-time theo mặc định. Đây thường là cách phù hợp hơn so với việc ép refresh toàn index chỉ để kiểm tra một document cụ thể.

### 7.3. Đừng dùng flush để xử lý read-after-write

Flush không phải chính sách visibility. Nếu một test hoặc service gọi flush với hy vọng Search nhìn thấy document ngay, thiết kế đang nhầm lẫn giữa commit/translog và refresh. Dùng refresh hoặc `refresh=wait_for` theo nhu cầu đọc.

## 8. Tích hợp refresh policy trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp các abstraction để làm việc với refresh. Tên package và cách cấu hình cụ thể phụ thuộc release train đang dùng, nhưng ý nghĩa vẫn tương ứng với các chính sách của Elasticsearch.

### 8.1. Refresh thủ công qua IndexOperations

Trong integration test hoặc một quy trình quản trị cần Search thấy dữ liệu đã ghi, có thể gọi refresh trên index:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

indexOperations.refresh();
~~~

Với entity đã khai báo index mapping, có thể lấy index operations từ entity class:

~~~java
IndexOperations indexOperations =
        operations.indexOps(Product.class);

indexOperations.refresh();
~~~

Chỉ gọi khi có nhu cầu rõ ràng. Không đặt lệnh refresh trong mỗi lần save ở service thông thường.

### 8.2. RefreshPolicy cho bulk operation

Khi gửi nhiều `IndexQuery` bằng bulk API, có thể chọn refresh policy ở cấp bulk options. Ví dụ minh họa:

~~~java
BulkOptions bulkOptions = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        indexQueries,
        bulkOptions,
        IndexCoordinates.of("products")
);
~~~

Các kiểu `BulkOptions`, enum `RefreshPolicy` và tên builder method có thể khác giữa các release train. Hãy kiểm tra API của dependency dự án. Ý nghĩa cần giữ:

- `NONE`: không yêu cầu refresh riêng; theo lịch refresh thông thường.
- `IMMEDIATE`: yêu cầu refresh ngay sau thao tác.
- `WAIT_UNTIL`: chờ refresh tiếp theo làm thay đổi visible.

Với bulk import lớn, thường nên tránh IMMEDIATE cho từng batch nhỏ nếu không cần visibility tức thời. Có thể ghi theo lô với chính sách mặc định, rồi refresh một lần sau khi import hoàn tất nếu nghiệp vụ cần Search thấy toàn bộ dữ liệu.

### 8.3. Flush từ Spring Data hoặc client

Flush là thao tác quản trị index/translog và thường không nằm trong luồng save thông thường của repository. Nếu một quy trình vận hành thật sự cần gọi Flush API, hãy dùng Elasticsearch Java Client hoặc API index operations được phiên bản Spring Data hỗ trợ, và ghi rõ lý do vận hành.

Không nên thêm flush sau mỗi `save()` hoặc `bulkIndex()`. Elasticsearch tự quản lý flush theo ngưỡng và điều kiện nội bộ; gọi thủ công liên tục có thể làm giảm hiệu năng mà không cải thiện read-after-write.

## 9. Bulk indexing và refresh interval

Khi import lượng lớn document, refresh thường xuyên có thể làm giảm throughput. Một chiến lược thường dùng là tạm tăng refresh interval hoặc tắt refresh tự động trong một khoảng ghi có kiểm soát, sau đó bật lại và refresh một lần.

Ví dụ quy trình:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

Thực hiện bulk indexing theo batch:

~~~http
POST /products/_bulk
Content-Type: application/x-ndjson

{"index":{"_id":"p-1"}}
{"name":"Keyboard","status":"ACTIVE"}
{"index":{"_id":"p-2"}}
{"name":"Mouse","status":"ACTIVE"}
~~~

Sau khi hoàn tất ghi, khôi phục refresh interval:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "1s"
  }
}
~~~

Sau đó yêu cầu refresh nếu cần Search thấy dữ liệu ngay:

~~~http
POST /products/_refresh
~~~

### 9.1. Rủi ro khi tắt refresh

Khi `refresh_interval` là `-1`:

- Search không nhìn thấy document mới cho đến khi có refresh.
- Các request `refresh=wait_for` có thể phải chờ.
- Một quy trình import bị lỗi giữa chừng có thể để index ở trạng thái không refresh.
- Người vận hành có thể quên khôi phục setting.

Vì vậy, nếu dùng chiến lược này, hãy quản lý nó như một quy trình có trạng thái:

1. Lưu setting hiện tại.
2. Tạm tắt hoặc tăng interval.
3. Thực hiện import theo batch.
4. Kiểm tra bulk response và số document lỗi.
5. Khôi phục setting trong cả nhánh thành công và nhánh lỗi.
6. Refresh một lần khi cần.
7. Xác nhận Search visibility.

Không tắt refresh nếu hệ thống đang phục vụ truy vấn cần dữ liệu mới liên tục và không có cửa sổ import riêng.

### 9.2. Tắt refresh không đồng nghĩa tắt durability

Refresh interval và translog durability là hai setting khác nhau. Tắt refresh không tự động tắt fsync translog. Nếu `index.translog.durability` vẫn là `request`, write request vẫn tuân theo chính sách đồng bộ translog tương ứng.

Không đánh đổi durability chỉ để tăng tốc import nếu yêu cầu nghiệp vụ không cho phép mất dữ liệu đã xác nhận. Hãy tối ưu batch size, concurrency, refresh interval và workload trước khi xem xét async durability.

## 10. Replication, durability và backup

Ba khái niệm cũng cần được phân biệt:

- **Translog durability:** bảo vệ thao tác ghi để có thể phục hồi sau sự cố node theo chính sách đồng bộ.
- **Replication:** giữ các shard copy để tăng khả năng sẵn sàng và phục hồi khi một node/shard gặp lỗi.
- **Snapshot:** tạo bản sao lưu có thể khôi phục sau lỗi lớn, xóa nhầm hoặc mất cluster.

Replica không phải backup. Nếu một document bị xóa nhầm hoặc dữ liệu sai được replicate, bản sao cũng có thể phản ánh thay đổi đó. Snapshot là cơ chế backup cần có lịch, chính sách lưu giữ và quy trình restore được kiểm thử.

### 10.1. wait_for_active_shards

Write API có thể nhận `wait_for_active_shards` để yêu cầu số shard copies hoạt động tối thiểu trước khi bắt đầu thao tác ghi. Thiết lập này liên quan đến availability và replication readiness, không phải refresh.

Ví dụ:

~~~http
PUT /products/_doc/42?wait_for_active_shards=all
Content-Type: application/json

{
  "name": "Keyboard"
}
~~~

Yêu cầu `all` có thể làm request chờ nếu một replica không hoạt động. Nó không có nghĩa document đã visible qua Search ngay lập tức; refresh vẫn là cơ chế visibility riêng.

Không nên coi `wait_for_active_shards=all` là thay thế snapshot hoặc một bảo đảm chống mọi sự cố. Hãy chọn số shard copies cần hoạt động theo SLA và topology cluster.

## 11. Các tình huống thường gặp

| Tình huống | Cơ chế phù hợp |
|---|---|
| Save xong, Search có thể thấy sau refresh tự động | Refresh mặc định |
| Save xong, caller cần Search thấy trước khi trả response | `refresh=wait_for` |
| Test ghi xong rồi query Search ngay | `IndexOperations.refresh()` hoặc `wait_for` |
| Đọc lại document theo ID | Get API real-time |
| Import hàng triệu document | Bulk, điều chỉnh refresh interval, refresh sau khi hoàn tất |
| Muốn commit và xoay translog generation | Flush, thường để Elasticsearch tự quản lý |
| Muốn bảo vệ thao tác đã xác nhận sau node crash | Translog durability |
| Muốn phục hồi sau xóa nhầm hoặc mất cluster | Snapshot và restore |
| Muốn chờ đủ shard copies trước write | `wait_for_active_shards` |

## 12. Kiểm thử refresh và durability

Integration test nên phân biệt visibility với durability thay vì dùng một thao tác refresh cho mọi kiểm thử.

### 12.1. Kiểm thử Search visibility

Một test có thể thực hiện:

1. Index document với refresh mặc định.
2. Dùng Get API theo ID để kiểm tra document đã được ghi.
3. Search theo một field để quan sát trạng thái trước refresh.
4. Gọi `IndexOperations.refresh()` hoặc dùng write với `WAIT_UNTIL`.
5. Search lại và xác nhận document xuất hiện.

Ví dụ pseudocode:

~~~java
operations.save(product);

// Get by ID có thể thấy document trước refresh.
Product loaded = operations.get(product.getId(), Product.class);

// Search visibility cần refresh.
operations.indexOps(Product.class).refresh();

SearchHits<Product> hits = operations.search(
        query,
        Product.class
);
~~~

Kết quả cụ thể phụ thuộc refresh timing, nên không viết test yêu cầu Search luôn không thấy document ngay sau write mặc định. Refresh nền có thể xảy ra trước khi assertion chạy. Thay vào đó, kiểm thử có kiểm soát bằng refresh policy hoặc refresh thủ công để bảo đảm test xác định.

### 12.2. Kiểm thử wait_for

Gửi write với `WAIT_UNTIL`, chờ request hoàn tất rồi Search. Test xác nhận caller có thể đọc qua Search sau khi write trả về.

Nếu refresh interval bị tắt, test cần chủ động kích hoạt refresh hoặc khôi phục interval; nếu không, `wait_for` có thể chờ không kết thúc trong thời gian mong đợi.

### 12.3. Kiểm thử flush

Không dùng việc Search thấy document sau flush làm bằng chứng rằng flush là cơ chế refresh. Hãy kiểm thử flush như thao tác index/translog riêng nếu ứng dụng vận hành thực sự cần nó. Với đa số business service, không cần viết test gọi flush sau từng write.

### 12.4. Kiểm thử durability

Không thể chứng minh durability chỉ bằng một unit test hoặc bằng việc gọi refresh. Durability cần được đánh giá ở cấp integration/chaos hoặc vận hành:

- Kiểm tra setting translog durability.
- Xác nhận write response theo chính sách `request`.
- Kiểm tra khả năng phục hồi shard sau restart có kiểm soát trong môi trường thử nghiệm.
- Kiểm tra replication và active shard copies.
- Thử quy trình snapshot/restore.
- Ghi nhận giới hạn của storage và hạ tầng.

Không gây crash node production để thử durability. Dùng môi trường staging và kịch bản failure được kiểm soát.

## 13. Các lỗi thường gặp

### 13.1. Nhầm refresh với flush

Refresh làm dữ liệu visible qua Search; flush thực hiện Lucene commit và bắt đầu translog generation mới. Chọn API theo mục tiêu thực tế.

### 13.2. Gọi refresh sau mọi save

Refresh liên tục tạo segment nhỏ và tăng chi phí merge. Dùng mặc định hoặc `wait_for` khi cần read-after-write.

### 13.3. Gọi flush để ép Search thấy dữ liệu

Flush không phải cơ chế read-after-write. Dùng refresh hoặc refresh policy.

### 13.4. Nghĩ write response thành công đồng nghĩa Search thấy ngay

Write acknowledgment và Search visibility là hai thời điểm khác nhau. Search cần refresh; Get theo ID có semantics real-time.

### 13.5. Nghĩ refresh bảo đảm durability

Refresh không thay thế translog fsync hoặc Lucene commit. Hãy hiểu cấu hình translog durability.

### 13.6. Nghĩ flush là backup

Flush không tạo bản sao lưu có thể khôi phục sau khi index bị xóa hoặc cluster mất. Dùng snapshot.

### 13.7. Tắt refresh rồi quên bật lại

Index có thể không cập nhật Search visibility theo mong muốn. Ghi lại setting cũ và khôi phục bằng quy trình có cleanup.

### 13.8. Dùng wait_for khi refresh đã bị tắt

Request có thể chờ đến khi có refresh. Khôi phục refresh interval hoặc chủ động refresh theo quy trình.

### 13.9. Dùng async durability mà không chấp nhận rủi ro

Các thao tác đã được xác nhận kể từ lần sync gần nhất có thể bị mất trong một số sự cố. Chỉ chọn async khi yêu cầu nghiệp vụ cho phép và đã đánh giá.

## 14. Quy trình lựa chọn chính sách

Khi thiết kế luồng ghi và đọc:

1. Xác định caller đọc bằng Get API hay Search API.
2. Nếu không cần Search thấy ngay, giữ refresh mặc định.
3. Nếu cần Search visibility trước khi trả response, cân nhắc `refresh=wait_for`.
4. Chỉ dùng `refresh=true` khi thật sự cần ép refresh ngay và đã hiểu chi phí.
5. Với bulk import, điều chỉnh refresh interval theo cửa sổ ghi và khôi phục setting sau đó.
6. Không dùng flush như một bước bắt buộc sau mỗi write.
7. Chọn translog durability theo yêu cầu mất dữ liệu có thể chấp nhận.
8. Thiết kế replication, active shard copies và snapshot riêng cho availability/backup.
9. Kiểm thử Search visibility và durability như hai thuộc tính khác nhau.
10. Theo dõi refresh, merge, translog, indexing latency và lỗi task trên cluster.

## 15. Kết luận

Refresh làm thay đổi trở nên nhìn thấy qua Search API bằng cách mở searcher mới. Flush thực hiện Lucene commit và chuyển translog generation để quản lý dữ liệu đã commit và vòng đời translog. Hai thao tác có mục tiêu khác nhau và thường được Elasticsearch tự quản lý.

Độ bền của write phụ thuộc vào translog và chính sách đồng bộ. Với `index.translog.durability=request`, Elasticsearch đồng bộ translog theo từng write request trước khi xác nhận; chế độ `async` đồng bộ theo chu kỳ và chấp nhận một cửa sổ rủi ro mất thao tác khi có sự cố. Refresh không phải durability, flush không phải backup, và replica không thay thế snapshot.

Trong Spring Data Elasticsearch, dùng `IndexOperations.refresh()` hoặc refresh policy phù hợp khi cần Search visibility. Với luồng ghi thông thường, giữ refresh mặc định; với read-after-write qua Search, cân nhắc `WAIT_UNTIL`; với bulk import, điều chỉnh refresh interval có kiểm soát. Chọn chính sách theo cách ứng dụng đọc dữ liệu, yêu cầu độ trễ và mức durability mà nghiệp vụ cần.
