# Vì sao tìm kiếm có thể chưa thấy tài liệu vừa ghi

Một tình huống thường gặp khi làm việc với Elasticsearch là ứng dụng vừa ghi một document thành công, nhận được ID hoặc response thành công, nhưng ngay sau đó chạy search lại chưa thấy document đó. Điều này không nhất thiết có nghĩa thao tác ghi bị mất hoặc Elasticsearch gặp lỗi. Elasticsearch là một hệ thống tìm kiếm near-real-time (NRT): document được ghi có thể chưa xuất hiện trong kết quả search cho đến khi shard được refresh.

Điểm quan trọng là phải phân biệt ba việc:

- **Write acknowledgement:** Elasticsearch đã xử lý thao tác ghi theo các điều kiện của request và trả response.
- **Durability:** dữ liệu được bảo vệ qua translog và cơ chế lưu trữ/replication theo cấu hình.
- **Search visibility:** document đã xuất hiện trong Lucene searcher mà search request sử dụng hay chưa.

Một thao tác ghi có thể đã được xác nhận và có thể được đọc bằng GET theo ID, nhưng chưa tìm thấy bằng match, term hoặc các query search khác. Nguyên nhân thường là refresh chưa diễn ra.

Trong Spring Data Elasticsearch, cần chọn refresh policy phù hợp với yêu cầu của ứng dụng. Có thể chấp nhận chờ refresh định kỳ, yêu cầu request đợi đến refresh tiếp theo, hoặc ép refresh ngay khi thực sự cần. Việc ép refresh sau mọi lần ghi có thể làm giảm throughput và tăng chi phí segment/merge.

## 1. Hiện tượng vừa ghi xong nhưng search chưa thấy

Giả sử service lưu một sản phẩm:

    Product product = new Product();
    product.setId("p-100");
    product.setName("Mechanical Keyboard");

    productRepository.save(product);

Ngay sau đó, service tìm theo tên:

    List<Product> results =
        productRepository.findByName("Mechanical Keyboard");

Ứng dụng có thể chưa thấy p-100 trong kết quả search, dù save đã trả về bình thường.

Điều này xảy ra vì indexing và search visibility là hai bước khác nhau. Elasticsearch có thể đã nhận thao tác ghi, cập nhật trạng thái nội bộ và ghi thông tin vào translog, nhưng searcher hiện tại chưa được làm mới để nhìn thấy segment mới.

Với cấu hình thông thường, refresh chạy định kỳ. Vì vậy, document thường trở nên searchable sau một khoảng ngắn, nhưng không có cam kết rằng một search request gửi ngay sau write sẽ luôn thấy nó nếu ứng dụng không yêu cầu read-after-write visibility.

## 2. Elasticsearch là near-real-time search engine

Elasticsearch xây dựng trên Apache Lucene. Document được index vào các cấu trúc nội bộ và sau đó được tổ chức thành segment. Search request đọc dữ liệu qua một searcher gắn với các segment đã được mở cho tìm kiếm.

Refresh là quá trình làm cho các thay đổi indexing gần đây có thể được nhìn thấy qua search bằng cách mở searcher mới trên các segment đã được tạo.

Luồng khái quát:

    Ứng dụng gửi index request
             |
             v
    Elasticsearch nhận thao tác ghi
             |
             v
    Cập nhật indexing buffer và translog
             |
             v
    Thao tác ghi được xác nhận
             |
             |  Search có thể vẫn dùng searcher cũ
             v
    Refresh tạo/mở searcher mới
             |
             v
    Document có thể được tìm thấy qua search

Vì refresh không xảy ra đồng bộ sau mọi thao tác ghi, Elasticsearch được gọi là near-real-time thay vì real-time search.

Near-real-time có nghĩa dữ liệu thường trở nên searchable sau một khoảng ngắn, không có nghĩa mọi lần search đều nhìn thấy mọi write ngay lập tức.

## 3. Refresh là gì?

Refresh làm cho các thay đổi indexing gần đây trở nên khả dụng cho search. Ở mức khái quát, Elasticsearch tạo hoặc mở các segment cần thiết rồi cập nhật searcher để query có thể đọc chúng.

Refresh không giống với việc ghi lại toàn bộ index xuống đĩa hoặc tạo một Lucene commit bền vững. Nó chủ yếu thay đổi khả năng nhìn thấy dữ liệu đối với search.

Một số điểm cần nhớ:

- Refresh tác động đến search visibility.
- Refresh không phải thao tác ghi từng document.
- Refresh không đồng nghĩa với flush.
- Refresh có chi phí CPU, I/O và quản lý segment.
- Search request chỉ nhìn thấy dữ liệu đã được refresh trên shard copy mà nó đọc.

Khi một index có hoạt động search, Elasticsearch thường tự refresh theo chu kỳ. Giá trị mặc định thường gặp ở Elasticsearch tự quản lý là khoảng một giây, nhưng cấu hình có thể thay đổi theo index, phiên bản và môi trường triển khai. Một số môi trường managed hoặc serverless có thể dùng mặc định khác.

Không nên viết logic ứng dụng dựa trên giả định cứng rằng refresh luôn diễn ra chính xác sau một giây. Nếu yêu cầu nghiệp vụ cần visibility ngay, hãy dùng refresh policy hoặc API refresh có chủ đích.

## 4. Write acknowledgement không đồng nghĩa với search visibility

Khi Elasticsearch trả response thành công cho index request, điều đó cho biết thao tác ghi đã được xử lý theo semantics của request và các điều kiện cluster liên quan.

Response thành công không tự động có nghĩa:

- Một refresh đã diễn ra.
- Searcher mới đã được mở trên mọi shard.
- Mọi replica đều đã refresh để search nhìn thấy document ngay.
- Một query theo field bất kỳ chắc chắn trả về document.

Ví dụ:

    PUT products/_doc/p-100
    {
      "name": "Mechanical Keyboard",
      "price": 120
    }

Response có thể báo kết quả index thành công. Tuy nhiên, ngay sau đó:

    GET products/_search
    {
      "query": {
        "term": {
          "name.keyword": "Mechanical Keyboard"
        }
      }
    }

có thể chưa trả về p-100 nếu shard chưa refresh.

Ngoài refresh, query cũng cần đúng field, analyzer, filter, index/alias và routing. Nếu document vẫn không xuất hiện sau refresh, cần kiểm tra các nguyên nhân này thay vì tiếp tục ép refresh.

## 5. Translog, refresh và flush khác nhau thế nào?

Ba khái niệm này thường bị nhầm lẫn:

| Khái niệm | Vai trò chính | Tác động trực tiếp |
|---|---|---|
| Translog | Ghi nhận thao tác để hỗ trợ durability và recovery | Bảo vệ thay đổi theo chính sách translog |
| Refresh | Làm thay đổi gần đây searchable | Search có thể nhìn thấy document |
| Flush | Tạo Lucene commit và bắt đầu translog generation mới | Hỗ trợ quản lý translog và recovery |

### Translog

Translog ghi lại các thao tác ghi để Elasticsearch có thể khôi phục những thay đổi chưa được đưa vào Lucene commit sau sự cố. Chính sách translog durability quyết định thời điểm đồng bộ translog xuống storage.

Mặc định thường dùng request durability, nghĩa là translog được đồng bộ theo semantics của request trước khi thao tác được xác nhận. Cấu hình có thể thay đổi, vì vậy cần kiểm tra index settings khi yêu cầu durability đặc biệt quan trọng.

### Refresh

Refresh làm cho các document đã index xuất hiện trong searcher mới. Nó không phải là một lệnh flush và không có nghĩa mọi dữ liệu đã được commit thành một Lucene commit bền vững.

### Flush

Flush tạo một Lucene commit và chuyển sang translog generation mới. Elasticsearch tự quản lý flush theo điều kiện nội bộ; ứng dụng tìm kiếm thông thường không cần gọi flush sau mỗi lần ghi.

Nếu mục tiêu là để search nhìn thấy document, hãy nghĩ đến refresh. Nếu mục tiêu là durability/recovery, cần hiểu translog và flush. Không dùng flush như một cách thay thế refresh.

## 6. GET theo ID có thể thấy document trước khi search thấy

Elasticsearch hỗ trợ realtime GET theo document ID. Realtime GET có thể đọc trạng thái mới nhất từ các cấu trúc nội bộ, bao gồm translog, mà không phải chờ search refresh.

Ví dụ:

    PUT products/_doc/p-100
    {
      "name": "Mechanical Keyboard"
    }

    GET products/_doc/p-100

GET theo ID có thể trả document ngay sau write, trong khi:

    GET products/_search
    {
      "query": {
        "term": {
          "name.keyword": "Mechanical Keyboard"
        }
      }
    }

vẫn chưa thấy document cho đến khi refresh.

Sự khác nhau:

| API | Cách đọc | Có phụ thuộc refresh để thấy write mới? |
|---|---|---|
| GET document theo ID | Realtime document lookup | Thông thường không |
| Search API | Đọc qua Lucene searcher | Có |
| Aggregation | Tính trên tập document được search chọn | Có |

GET theo ID không thay thế search. Nếu ứng dụng cần tìm theo tên, trạng thái, category hoặc các điều kiện query khác, cần bảo đảm search visibility.

## 7. Refresh interval mặc định và cấu hình

Index setting refresh_interval quy định chu kỳ refresh tự động:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "1s"
      }
    }

Giá trị 1s là cấu hình phổ biến ở Elasticsearch tự quản lý, nhưng có thể thay đổi. Nếu tăng lên 5s hoặc 30s, document có thể mất nhiều thời gian hơn trước khi xuất hiện qua search.

Nếu đặt:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "-1"
      }
    }

thì automatic refresh bị tắt. Khi đó, document sẽ không tự trở nên searchable theo chu kỳ; ứng dụng hoặc tác vụ vận hành cần chủ động refresh khi phù hợp.

Tắt refresh có thể hữu ích trong bulk import lớn để giảm overhead, nhưng cần có bước refresh sau khi import nếu muốn search thấy dữ liệu.

### Khi nào điều chỉnh refresh_interval?

- Index ghi liên tục và chấp nhận search visibility trễ hơn: có thể tăng interval.
- Import dữ liệu lớn: có thể tạm tắt automatic refresh trong quy trình có kiểm soát, rồi refresh sau import.
- Dữ liệu cần xuất hiện nhanh trong UI: giữ interval phù hợp hoặc dùng WAIT_UNTIL cho các write cần read-after-write.
- Index phục vụ cả ingest lớn và search tương tác: cần cân bằng latency visibility với throughput.

Không nên giảm refresh_interval xuống rất nhỏ chỉ để chữa một race condition trong ứng dụng. Refresh quá thường xuyên có thể làm tăng segment count và chi phí merge.

## 8. Refresh policy trong Bulk API và Spring Data

Elasticsearch có các cách xử lý refresh thường được biểu diễn bằng ba chính sách:

| Chính sách | REST API | Ý nghĩa |
|---|---|---|
| NONE | false hoặc không truyền refresh | Không yêu cầu refresh riêng cho request |
| IMMEDIATE | true | Refresh ngay các shard liên quan sau thao tác |
| WAIT_UNTIL | wait_for | Đợi refresh tiếp theo làm thay đổi có thể nhìn thấy |

Trong Spring Data Elasticsearch, enum thường được gọi là RefreshPolicy với các giá trị NONE, IMMEDIATE và WAIT_UNTIL. Package và API truyền policy phụ thuộc phiên bản Spring Data.

### NONE

NONE không yêu cầu Elasticsearch refresh ngay sau request. Document sẽ searchable khi automatic refresh tiếp theo diễn ra hoặc khi có refresh khác tác động đến index.

Phù hợp với:

- Bulk import lớn.
- Ingest liên tục với throughput là ưu tiên.
- Write không cần search ngay lập tức.
- Các hệ thống chấp nhận eventual search visibility.

### IMMEDIATE

IMMEDIATE yêu cầu refresh ngay sau thao tác. Khi request hoàn tất, thay đổi có thể được tìm thấy qua search trên các shard liên quan.

Phù hợp với:

- Một thao tác quản trị hiếm gặp cần xuất hiện ngay.
- Quy trình nhỏ, có yêu cầu visibility tức thì.
- Test hoặc use case cần kết quả search ngay và chấp nhận chi phí.

Không nên dùng IMMEDIATE cho mọi thao tác trong hệ thống có throughput cao.

### WAIT_UNTIL

WAIT_UNTIL yêu cầu request chờ đến khi một refresh làm thay đổi có thể nhìn thấy qua search. Nó không chủ động ép refresh ngay; thay vào đó, request được giữ cho đến refresh tiếp theo phù hợp.

Phù hợp với:

- Người dùng tạo một sản phẩm rồi chuyển ngay sang trang tìm kiếm sản phẩm đó.
- API cần bảo đảm read-after-write qua search.
- Một số thao tác nghiệp vụ cần kết quả searchable trước khi trả response.

WAIT_UNTIL thường cân bằng tốt hơn giữa visibility và chi phí so với ép IMMEDIATE cho từng write, nhưng request có thể phải chờ đến chu kỳ refresh tiếp theo.

## 9. Chọn refresh policy theo yêu cầu nghiệp vụ

Không phải mọi write đều cần cùng một mức độ visibility.

| Tình huống | Policy thường phù hợp | Lý do |
|---|---|---|
| Import hàng triệu document | NONE | Tối ưu throughput, refresh sau import |
| Cập nhật dữ liệu nền theo lịch | NONE | Chấp nhận trễ đến refresh tự động |
| Người dùng tạo sản phẩm rồi tìm ngay qua search | WAIT_UNTIL | Đợi dữ liệu searchable trước khi trả kết quả |
| Một thao tác admin hiếm cần xuất hiện ngay | IMMEDIATE hoặc WAIT_UNTIL | Chọn theo yêu cầu và chi phí |
| Ghi nhiều batch trong cùng một job | NONE, sau đó refresh một lần | Tránh refresh sau từng batch |
| Test integration cần search ngay sau save | Refresh tường minh hoặc WAIT_UNTIL | Làm test xác định, không phụ thuộc timer |

Hãy xác định chính xác API cần bảo đảm điều gì. Nếu người dùng chỉ cần xem chi tiết document vừa tạo và đã có ID, realtime GET có thể đủ; không cần ép refresh toàn index.

## 10. Dùng RefreshPolicy trong annotation @Document

Spring Data Elasticsearch có thể cho phép khai báo refresh policy ở metadata của entity trong các phiên bản hỗ trợ:

    @Document(
        indexName = "products",
        refreshPolicy = RefreshPolicy.WAIT_UNTIL
    )
    public class Product {

        @Id
        private String id;

        private String name;
    }

Khi entity được ghi qua các thao tác Spring Data áp dụng metadata này, refresh policy tương ứng có thể được dùng cho write request.

Cần kiểm tra package và thuộc tính annotation trong phiên bản dự án. Không phải mọi phiên bản Spring Data Elasticsearch đều có cùng metadata hoặc cùng cách áp dụng policy cho mọi API ghi.

Không nên đặt IMMEDIATE ở cấp entity chỉ để chữa một endpoint cần visibility ngay nếu entity đó được ghi rất thường xuyên bởi nhiều luồng khác. Policy ở cấp rộng có thể ảnh hưởng toàn bộ write path.

Nếu chỉ một số use case cần read-after-write, cân nhắc cấu hình ở request hoặc service tương ứng để phạm vi ảnh hưởng rõ ràng hơn.

## 11. Dùng BulkOptions để cấu hình refresh policy

Với bulk operation, có thể truyền refresh policy qua BulkOptions ở các phiên bản hỗ trợ:

    BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

    operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products")
    );

Nếu import lớn:

    BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

    for (List<IndexQuery> batch : batches) {
        operations.bulkIndex(
            batch,
            options,
            IndexCoordinates.of("products")
        );
    }

    operations.indexOps(IndexCoordinates.of("products"))
        .refresh();

Đoạn code minh họa API thường gặp. Package, builder method và kiểu IndexCoordinates phụ thuộc phiên bản Spring Data Elasticsearch. Kiểm tra dependency thực tế trước khi áp dụng.

Nếu mỗi batch dùng WAIT_UNTIL, mỗi request có thể phải chờ refresh. Với hàng trăm batch, thời gian import tổng thể có thể tăng đáng kể. Nếu không cần đọc giữa các batch, NONE rồi refresh một lần thường phù hợp hơn.

## 12. Refresh tường minh bằng IndexOperations

Khi ứng dụng cần chủ động làm dữ liệu searchable, có thể gọi refresh:

    IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

    indexOperations.refresh();

Hoặc dùng index metadata tương ứng:

    operations.indexOps(Product.class).refresh();

API cụ thể phụ thuộc Spring Data version. Refresh tường minh tác động đến index được chỉ định và có thể làm các write trước đó searchable.

Không nên gọi refresh sau mỗi document:

    for (Product product : products) {
        operations.save(product);
        operations.indexOps(Product.class).refresh();
    }

Cách này có thể tạo rất nhiều refresh và segment nhỏ. Nếu cần xử lý nhiều document, hãy gom batch, ghi xong rồi refresh một lần khi thật sự cần.

## 13. Refresh API trực tiếp của Elasticsearch

REST API:

    POST products/_refresh

Có thể refresh nhiều index:

    POST products,orders/_refresh

Refresh API thường được dùng trong:

- Quy trình import sau khi hoàn tất.
- Integration test.
- Tác vụ vận hành có kiểm soát.

Refresh không cần truyền document ID. Nó làm search visibility cho các thay đổi đã ghi trên index/shard liên quan.

Nếu ứng dụng dùng alias, hãy xác định alias trỏ đến index nào và refresh đúng đích. Refresh alias có thể áp dụng cho các index đằng sau alias theo semantics API, nhưng cần kiểm tra alias và write index trong quy trình triển khai.

## 14. WAIT_UNTIL hoạt động như thế nào?

WAIT_UNTIL sử dụng cơ chế chờ refresh listener. Thay vì yêu cầu refresh ngay, Elasticsearch giữ request chờ đến khi refresh tiếp theo làm thay đổi của request có thể nhìn thấy.

Luồng:

    Ứng dụng gửi write với refresh=wait_for
                 |
                 v
    Elasticsearch xử lý thao tác ghi
                 |
                 v
    Đăng ký chờ refresh
                 |
                 v
    Automatic hoặc explicit refresh xảy ra
                 |
                 v
    Request được hoàn tất
                 |
                 v
    Ứng dụng nhận response

WAIT_UNTIL có thể giảm số refresh cưỡng bức so với IMMEDIATE khi nhiều request cùng chờ một chu kỳ refresh.

Tuy nhiên, nó không miễn phí:

- Request giữ connection hoặc tài nguyên chờ.
- Nếu refresh interval dài, response write cũng có thể chậm.
- Nếu automatic refresh bị tắt, request có thể chờ cho đến explicit refresh hoặc timeout.
- Có giới hạn số refresh listener; quá nhiều request chờ có thể gây lỗi.

Không nên tạo hàng nghìn request WAIT_UNTIL đồng thời mà không giới hạn concurrency.

## 15. Tắt automatic refresh và rủi ro với WAIT_UNTIL

Nếu index có:

    index.refresh_interval = -1

thì automatic refresh bị tắt. Khi đó, WAIT_UNTIL không thể dựa vào chu kỳ refresh tự động để hoàn tất. Request có thể tiếp tục chờ cho đến khi một refresh tường minh xảy ra hoặc hết thời gian chờ theo cơ chế liên quan.

Trong bulk import có refresh disabled:

1. Gửi bulk với NONE.
2. Hoàn tất tất cả batch.
3. Gọi explicit refresh một lần.
4. Chỉ sau đó mới chạy các search cần thấy dữ liệu mới.

Không kết hợp tắt refresh dài hạn với WAIT_UNTIL mà không có kế hoạch refresh rõ ràng.

## 16. Tại sao IMMEDIATE làm giảm hiệu năng?

Refresh làm searcher mới có thể đọc các segment mới. Khi refresh xảy ra liên tục:

- Nhiều segment nhỏ được tạo và mở.
- Search phải quản lý nhiều segment hơn.
- Segment merge có thể tăng.
- CPU và I/O dành cho refresh/merge tăng.
- Throughput indexing có thể giảm.
- Latency search có thể dao động do áp lực tài nguyên.

Nếu mỗi document đều ép refresh, hệ thống mất lợi ích của việc gom nhiều thao tác trước khi refresh.

Ví dụ:

    save A -> refresh
    save B -> refresh
    save C -> refresh
    save D -> refresh

So với:

    save A
    save B
    save C
    save D
    -> một refresh theo chu kỳ hoặc một refresh có chủ đích

Cách thứ hai thường hiệu quả hơn khi workload có nhiều write.

## 17. Read-after-write qua GET và qua search

Hãy chọn API đọc dựa trên điều người dùng cần.

### Đọc theo ID

Nếu write trả về ID và UI chỉ cần mở chi tiết document vừa tạo, có thể dùng GET theo ID. Realtime GET thường thấy write mới mà không cần chờ refresh.

### Tìm theo thuộc tính

Nếu UI cần tìm document bằng tên, category, trạng thái hoặc full-text query, phải dựa vào search visibility. Dùng WAIT_UNTIL hoặc refresh tường minh nếu endpoint cần bảo đảm read-after-write.

### Đọc từ một hệ thống khác

Nếu một service khác thực hiện search ngay sau khi service ghi trả response, service ghi cần có hợp đồng visibility rõ ràng. Có thể:

- Trả response sau WAIT_UNTIL.
- Phát event chỉ sau khi dữ liệu searchable theo yêu cầu.
- Cho service đọc bằng ID nếu use case phù hợp.
- Chấp nhận eventual consistency và thiết kế retry/polling ở consumer.

Không nên để service khác đoán bằng cách sleep một giây rồi search lại.

## 18. Search có thể chưa thấy vì lý do khác ngoài refresh

Nếu đã chờ refresh mà document vẫn không xuất hiện, hãy kiểm tra các nguyên nhân khác:

| Nguyên nhân | Dấu hiệu | Cách kiểm tra |
|---|---|---|
| Search sai index hoặc alias | GET theo ID ở index khác thành công | Kiểm tra index/alias và write index |
| Query không khớp | GET thấy document nhưng term/match không trả | Kiểm tra mapping, analyzer và query DSL |
| Filter loại document | Search cơ bản thấy nhưng query nghiệp vụ không thấy | Kiểm tra status, tenant, permission và range filter |
| Routing không đúng | GET/search theo routing khác nhau có kết quả khác | Kiểm tra routing lúc index và lúc search |
| Write chưa hoàn tất | Search chạy trước khi async write hoàn thành | Chờ completion của Future/Mono/job |
| Item bulk thất bại | Bulk response có item errors | Kiểm tra errors và từng item |
| Document bị ghi đè hoặc xóa | ID có version/source khác mong đợi | Kiểm tra sequence, version và write path khác |
| Mapping parse lỗi | Item trả mapper_parsing_exception | Kiểm tra kiểu dữ liệu và source |

Refresh chỉ giải quyết search visibility của write đã thành công. Nó không sửa query sai, mapping sai hoặc thao tác ghi thất bại.

## 19. Bulk response thành công nhưng item có thể lỗi

Bulk API có thể trả HTTP response thành công trong khi một số item bên trong thất bại. Trước khi điều tra refresh, cần kiểm tra item-level result.

Ví dụ response:

    {
      "errors": true,
      "items": [
        {
          "index": {
            "_id": "p-1",
            "status": 201
          }
        },
        {
          "index": {
            "_id": "p-2",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception"
            }
          }
        }
      ]
    }

p-1 đã được ghi, p-2 chưa được ghi thành công. Refresh không thể làm p-2 xuất hiện vì thao tác đó đã thất bại.

Trong Spring Data, cách biểu diễn item error phụ thuộc API và phiên bản. Hãy đọc response/exception tương ứng, ghi lại ID và reason, rồi phân loại retry.

## 20. Search trên replica và visibility

Elasticsearch phân phối shard thành primary và replica. Search có thể được thực hiện trên các shard copy theo routing và adaptive replica selection.

Refresh là hoạt động của shard copy. Trong môi trường có replica, cần hiểu rằng visibility của write liên quan đến việc refresh các shard copy mà search có thể đọc. Elasticsearch điều phối refresh và replication theo semantics của request; không nên giả định rằng chỉ refresh một node thủ công luôn giải quyết được mọi vấn đề trên toàn cluster.

Khi cần visibility theo request, dùng refresh policy của write request là cách rõ ràng hơn việc tự chọn một node rồi gọi API refresh trực tiếp không đúng phạm vi.

Nếu search vẫn trả kết quả không nhất quán sau WAIT_UNTIL hoặc explicit refresh, hãy kiểm tra cluster health, shard allocation, routing và index alias. Không quy mọi trường hợp replica khác nhau thành lỗi refresh interval.

## 21. Write bất đồng bộ và thứ tự thực thi trong ứng dụng

Một nguyên nhân phổ biến khác là service khởi chạy write bất đồng bộ nhưng không chờ hoàn tất trước khi search:

    executor.submit(() -> productRepository.save(product));

    return productRepository.findByName(product.getName());

Search có thể chạy trước khi thao tác save bắt đầu hoặc hoàn tất. Đây là race condition ở ứng dụng, khác với refresh.

Với CompletableFuture, cần chờ hoặc compose các bước:

    CompletableFuture<Product> saved =
        CompletableFuture.supplyAsync(
            () -> productRepository.save(product),
            executor
        );

    return saved.thenApply(result ->
        productRepository.findByName(result.getName())
    );

Ví dụ này vẫn cần refresh policy phù hợp nếu bước đọc là search. Chờ write hoàn tất chỉ bảo đảm request ghi đã trả response; nó không tự bảo đảm refresh đã diễn ra.

Với reactive Spring Data:

    Mono<Product> saved = reactiveOperations.save(product);

    Mono<List<Product>> results = saved.flatMap(entity ->
        reactiveOperations.search(
            queryFor(entity.getName()),
            Product.class
        ).collectList()
    );

Composition bảo đảm search bắt đầu sau khi Mono save hoàn tất. Nhưng để search thấy document ngay, vẫn cần WAIT_UNTIL hoặc refresh phù hợp với API/version đang dùng.

Không gọi subscribe rồi lập tức search ở một dòng khác nếu không có cơ chế phối hợp completion. subscribe khởi chạy luồng reactive, không có nghĩa thao tác đã hoàn tất đồng bộ.

## 22. Kiểm thử integration: không dùng Thread.sleep

Một test dễ lỗi là:

    repository.save(product);
    Thread.sleep(1000);
    assertThat(repository.findByName(product.getName()))
        .isNotEmpty();

Test này phụ thuộc thời gian refresh, tải máy và cấu hình index. Nó có thể chậm hoặc flaky.

Thay vào đó, có thể refresh rõ ràng:

    repository.save(product);

    operations.indexOps(Product.class).refresh();

    List<Product> results =
        repository.findByName(product.getName());

Hoặc cấu hình write dùng WAIT_UNTIL cho test:

    @Document(
        indexName = "products_test",
        refreshPolicy = RefreshPolicy.WAIT_UNTIL
    )
    public class Product {
        @Id
        private String id;
        private String name;
    }

Annotation và policy áp dụng theo phiên bản Spring Data. Cách refresh tường minh trong test thường dễ thấy và kiểm soát hơn.

Sau test, cần dọn dữ liệu/index theo quy trình test. Nếu nhiều test chạy song song trên cùng index, refresh không giải quyết xung đột dữ liệu giữa các test; nên dùng ID hoặc index test riêng.

## 23. Kiểm tra bằng REST API

Có thể tái hiện hiện tượng:

    PUT products/_doc/p-100?refresh=false
    {
      "name": "Mechanical Keyboard"
    }

    GET products/_doc/p-100

GET theo ID có thể trả document ngay.

Search:

    GET products/_search
    {
      "query": {
        "term": {
          "name.keyword": "Mechanical Keyboard"
        }
      }
    }

Có thể chưa thấy document trước refresh.

Gọi refresh:

    POST products/_refresh

Search lại:

    GET products/_search
    {
      "query": {
        "term": {
          "name.keyword": "Mechanical Keyboard"
        }
      }
    }

Sau refresh, document đã được ghi thành công và query đúng có thể tìm thấy nó.

Một cách khác là dùng refresh=wait_for:

    PUT products/_doc/p-101?refresh=wait_for
    {
      "name": "Wireless Mouse"
    }

Khi write response trả về, request đã đợi refresh phù hợp để dữ liệu searchable.

## 24. Refresh và optimistic concurrency

Refresh policy không thay thế cơ chế concurrency control.

Nếu hai request cùng cập nhật một document, Elasticsearch có thể dùng sequence number và primary term hoặc version để bảo vệ thao tác theo semantics phù hợp. Refresh chỉ quyết định khi nào thay đổi nhìn thấy qua search.

Ví dụ:

- Request A cập nhật price.
- Request B cập nhật stock.
- Search chưa refresh có thể chưa thấy một hoặc cả hai thay đổi.
- GET theo ID có thể thấy trạng thái mới nhất.
- Nếu có xung đột ghi, cần xử lý version/conflict riêng.

Đừng dùng IMMEDIATE để chữa lost update hoặc version conflict. Những vấn đề đó cần optimistic concurrency control, update script, retry hoặc thiết kế thao tác ghi đúng.

## 25. Refresh và bulk import lớn

Khi nhập nhiều document, refresh từng batch có thể làm giảm throughput.

Một quy trình thường dùng:

1. Tạo index với mapping/settings đã chuẩn bị.
2. Nếu phù hợp, tạm tăng refresh_interval hoặc tắt automatic refresh.
3. Gửi bulk request với refresh NONE.
4. Theo dõi item failure và retry lỗi tạm thời.
5. Hoàn tất tất cả batch.
6. Khôi phục refresh_interval nếu đã thay đổi.
7. Gọi refresh một lần khi cần search thấy dữ liệu ngay.
8. Chạy các query kiểm tra sau refresh.

Ví dụ:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "-1"
      }
    }

Sau import:

    POST products/_refresh

Rồi khôi phục:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "1s"
      }
    }

Đây là ví dụ vận hành; chỉ tắt refresh khi job có quyền kiểm soát index và có quy trình khôi phục setting ngay cả khi job thất bại. Không để index production bị tắt refresh ngoài dự kiến.

## 26. WAIT_UNTIL và giới hạn refresh listener

WAIT_UNTIL dùng listener để chờ refresh. Elasticsearch có giới hạn số refresh listener trên mỗi shard thông qua setting liên quan, thường được gọi là index.max_refresh_listeners.

Nếu có quá nhiều request WAIT_UNTIL đồng thời và refresh chưa xảy ra, request mới có thể bị từ chối khi listener đạt giới hạn.

Để tránh:

- Không dùng WAIT_UNTIL cho mọi write ở workload throughput cao.
- Giới hạn số request chờ đồng thời.
- Giữ refresh interval phù hợp.
- Không tắt automatic refresh nếu request đang phụ thuộc WAIT_UNTIL.
- Dùng bulk để gom nhiều write cần cùng visibility.
- Theo dõi lỗi và latency của write request.

Nếu ứng dụng cần ghi nhiều document rồi đọc cả nhóm, một bulk request với WAIT_UNTIL có thể phù hợp hơn hàng nghìn request riêng cùng chờ refresh, tùy workload.

## 27. Refresh và search consistency giữa nhiều request

Giả sử người dùng thực hiện:

1. Tạo product p-100.
2. Nhận response thành công.
3. Mở danh sách sản phẩm.

Nếu write dùng NONE, danh sách có thể chưa thấy p-100 ngay lập tức. Một request search sau đó có thể thấy document khi refresh diễn ra.

Đây là eventual consistency ở search visibility. Ứng dụng nên quyết định trải nghiệm:

- Có thể hiển thị chi tiết dựa trên ID ngay sau write.
- Có thể hiển thị thông báo đang cập nhật và danh sách sẽ đồng bộ sau.
- Có thể chờ WAIT_UNTIL trước khi trả response nếu yêu cầu tìm kiếm ngay là bắt buộc.
- Có thể cập nhật UI local theo response write và đồng bộ search sau.

Không nên mặc định mọi endpoint create/update phải ép refresh. Điều đó biến yêu cầu visibility của UI thành chi phí cho toàn bộ write workload.

## 28. Những lỗi thường gặp

### Nghĩ save trả về là search thấy ngay

Save response cho biết thao tác ghi đã được xử lý, nhưng search visibility cần refresh. Dùng WAIT_UNTIL hoặc refresh tường minh nếu cần.

### Nhầm realtime GET với search

GET theo ID có thể đọc write mới từ translog, trong khi search dựa trên searcher đã refresh. Hai API có semantics khác nhau.

### Gọi flush để làm dữ liệu searchable

Flush và refresh có mục đích khác nhau. Search visibility cần refresh; không dùng flush như một thay thế.

### Gọi refresh sau mọi document

Refresh quá thường xuyên làm tăng segment và chi phí merge. Gom write hoặc dùng WAIT_UNTIL/NONE phù hợp.

### Dùng WAIT_UNTIL khi automatic refresh đã tắt

Request có thể chờ lâu hoặc đến timeout nếu không có refresh xảy ra. Cần explicit refresh trong quy trình.

### Dùng Thread.sleep trong test

Sleep làm test phụ thuộc timing. Gọi refresh tường minh hoặc dùng policy phù hợp để test xác định.

### Chỉ kiểm tra HTTP status của bulk

Bulk có thể có item thất bại. Kiểm tra kết quả từng item trước khi kết luận document đã được ghi.

### Không chờ async write hoàn tất

Search có thể chạy trước khi write request được gửi hoặc hoàn tất. Compose Future/Mono hoặc chờ completion đúng cách.

### Search sai index, alias hoặc routing

Refresh không sửa được target sai. Kiểm tra index/alias, routing, mapping, analyzer và filter.

### Giảm refresh_interval quá thấp để chữa race condition

Refresh thường xuyên làm tăng overhead. Chọn policy theo yêu cầu read-after-write thay vì giảm interval toàn index không có căn cứ.

### Dùng IMMEDIATE cho toàn bộ hệ thống

Một số use case cần visibility ngay, nhưng ép refresh mọi write có thể giảm throughput. Chọn phạm vi hẹp.

## 29. Quy trình điều tra khi write xong nhưng search chưa thấy

Khi gặp vấn đề, kiểm tra theo thứ tự:

1. Xác nhận write request đã hoàn tất và response báo thành công.
2. Nếu dùng bulk, kiểm tra errors và từng item.
3. Thử GET document theo ID để xác nhận source hiện tại.
4. Xác nhận index, alias, write index và routing.
5. Kiểm tra mapping, analyzer và query DSL.
6. Gọi refresh tường minh trong môi trường điều tra.
7. Chạy lại search query.
8. Nếu vẫn không thấy, kiểm tra filter, tenant, permission và các thao tác update/delete khác.
9. Kiểm tra refresh_interval và trạng thái shard.
10. Nếu write bất đồng bộ, xác nhận Future/Mono/job đã hoàn tất.

Nếu explicit refresh làm document xuất hiện, nguyên nhân có khả năng là search visibility. Nếu vẫn không xuất hiện, cần điều tra query hoặc write path thay vì tiếp tục gọi refresh.

## 30. Quy trình chọn refresh strategy

Có thể chọn policy theo các bước:

1. Xác định người dùng cần đọc bằng ID hay cần search theo field.
2. Nếu chỉ cần đọc theo ID, dùng realtime GET khi phù hợp.
3. Nếu search có thể trễ theo refresh interval, dùng NONE và chấp nhận eventual visibility.
4. Nếu write request phải đợi searchable trước khi trả response, dùng WAIT_UNTIL.
5. Nếu có thao tác nhỏ cần refresh ngay lập tức, cân nhắc IMMEDIATE.
6. Với bulk import lớn, dùng NONE rồi refresh một lần sau khi hoàn tất.
7. Tránh WAIT_UNTIL khi automatic refresh bị tắt nếu không có explicit refresh.
8. Kiểm tra số request chờ và giới hạn refresh listener.
9. Dùng refresh tường minh trong integration test thay vì Thread.sleep.
10. Đo latency write, throughput ingest và search visibility trước khi thay đổi refresh_interval.

## Kết luận

Tài liệu vừa ghi có thể chưa xuất hiện trong kết quả search vì Elasticsearch là near-real-time search engine. Write acknowledgement, durability và search visibility là ba khái niệm khác nhau. Translog hỗ trợ durability và recovery; refresh làm thay đổi trở nên searchable; flush tạo Lucene commit và quản lý translog generation. Realtime GET theo ID có thể thấy document trước khi search thấy nó.

Trong Spring Data Elasticsearch, NONE phù hợp với write không cần visibility ngay, IMMEDIATE ép refresh và có thể làm giảm throughput, còn WAIT_UNTIL đợi refresh tiếp theo để bảo đảm read-after-write qua search. Với bulk import, thường nên ghi bằng NONE rồi refresh một lần khi hoàn tất. Với test, hãy refresh tường minh thay vì Thread.sleep. Nếu đã refresh mà vẫn không tìm thấy document, kiểm tra item-level bulk errors, index/alias, routing, mapping, analyzer, filter và thứ tự thực thi bất đồng bộ. Chọn refresh policy theo yêu cầu nghiệp vụ giúp cân bằng search visibility với hiệu năng ingest.
