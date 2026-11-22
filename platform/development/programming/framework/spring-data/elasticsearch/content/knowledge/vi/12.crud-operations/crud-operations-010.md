# Chọn refresh policy theo yêu cầu đọc sau ghi

Khi ứng dụng ghi document vào Elasticsearch rồi lập tức tìm kiếm document đó, đôi khi kết quả search chưa nhìn thấy dữ liệu vừa ghi. Đây là hành vi bình thường vì Elasticsearch là hệ thống tìm kiếm gần thời gian thực (*near real-time*): thao tác ghi có thể đã được xác nhận nhưng document chỉ xuất hiện trong kết quả search sau lần refresh tiếp theo.

Refresh policy quyết định request ghi có chờ việc dữ liệu trở nên khả dụng cho search hay không, hoặc có chủ động yêu cầu refresh ngay hay không. Chọn policy phù hợp là một sự đánh đổi giữa độ trễ đọc sau ghi và throughput indexing.

Ba lựa chọn thường gặp là:

- **NONE / false:** không yêu cầu refresh và không chờ refresh. Dữ liệu sẽ xuất hiện trong search sau lần refresh tự động hoặc refresh được gọi riêng.
- **IMMEDIATE / true:** yêu cầu refresh ngay trên các shard liên quan trước khi request hoàn tất. Search có thể nhìn thấy thay đổi sớm, nhưng thao tác này có chi phí.
- **WAIT_UNTIL / wait_for:** request chờ đến khi một lần refresh tự nhiên làm dữ liệu trở nên khả dụng cho search. Nó không chủ động ép refresh ngay và thường là lựa chọn phù hợp khi cần đọc sau ghi mà vẫn muốn giữ hiệu năng indexing.

Không có một policy tốt nhất cho mọi thao tác. Cần xác định ứng dụng cần đọc lại bằng search ngay lập tức, có thể chấp nhận độ trễ ngắn, hay chỉ cần kiểm tra document theo id.

## 1. Vì sao ghi xong nhưng search chưa thấy document?

Elasticsearch sử dụng Lucene để lưu và tìm kiếm dữ liệu. Khi document được index, thay đổi được ghi nhận trong các cấu trúc nội bộ và translog. Tuy nhiên, để searcher mới nhìn thấy document, Elasticsearch cần thực hiện refresh.

Refresh mở các segment mới cho hoạt động tìm kiếm và làm cho những thay đổi gần đây trở nên khả dụng với search. Đây là một phần của mô hình near real-time search.

Ví dụ:

    1. Ứng dụng gửi request index document p-101.
    2. Elasticsearch xử lý thao tác ghi và xác nhận request.
    3. Ứng dụng gửi search query ngay sau đó.
    4. Searcher hiện tại chưa được refresh nên chưa thấy p-101.
    5. Một lần refresh diễn ra.
    6. Search query tiếp theo nhìn thấy p-101.

Do đó, phản hồi thành công của thao tác ghi không nhất thiết có nghĩa document đã xuất hiện trong kết quả search ngay tại thời điểm nhận response.

### Refresh không phải là flush

Refresh và flush là hai khái niệm khác nhau:

- **Refresh:** làm cho dữ liệu mới được khả dụng cho search bằng cách mở các segment mới cho searcher.
- **Flush:** thực hiện quá trình commit Lucene và xoay vòng translog theo cơ chế nội bộ của Elasticsearch.

Gọi refresh không có nghĩa ứng dụng vừa yêu cầu một thao tác fsync hoặc bảo đảm durability mới. Ngược lại, việc một document chưa xuất hiện trong search không có nghĩa thao tác ghi chưa được lưu hoặc đã mất.

Độ bền của dữ liệu còn liên quan đến translog durability, replication, cấu hình cluster và cơ chế xác nhận ghi. Refresh policy chủ yếu điều khiển thời điểm dữ liệu trở nên nhìn thấy trong search.

## 2. Refresh diễn ra ở cấp shard

Một index được chia thành primary shard và có thể có replica shard. Search được thực hiện trên các shard copy phù hợp. Refresh làm cho thay đổi đã ghi trở nên khả dụng trên searcher của shard.

Vì vậy, refresh không đơn giản là một thao tác cập nhật cache ở cấp ứng dụng. Nó liên quan đến việc Elasticsearch mở searcher mới trên các shard bị ảnh hưởng.

Nếu một request ghi tác động đến nhiều shard, việc refresh hoặc chờ refresh cũng liên quan đến các shard đó. Một request ghi vào index khác không nhất thiết cần refresh cùng lúc nếu ứng dụng chỉ đọc dữ liệu ở một index riêng.

## 3. Ba refresh policy

### NONE: không chờ refresh

NONE tương ứng với refresh=false ở REST API và Elasticsearch Java API Client. Đây là lựa chọn mặc định phù hợp với phần lớn luồng ghi thông thường.

Đặc điểm:

- Request ghi không chủ động refresh.
- Request không chờ search visibility.
- Elasticsearch tiếp tục refresh theo interval tự động hoặc theo yêu cầu khác.
- Throughput indexing thường tốt hơn so với việc ép refresh sau từng request.

Ví dụ REST API:

    PUT products/_doc/p-101?refresh=false
    {
      "name": "Keyboard",
      "price": 45.0
    }

Sau khi request trả về thành công, một GET document theo id có thể đọc được dữ liệu mới ngay nhờ realtime GET. Nhưng một search query có thể chưa thấy document cho đến lần refresh tiếp theo.

NONE phù hợp khi:

- Ứng dụng ghi nhiều document liên tục.
- Người dùng không cần kết quả search cập nhật tức thì.
- Có thể chấp nhận độ trễ ngắn của near real-time search.
- Dữ liệu được xử lý theo batch hoặc qua pipeline ingest.

### IMMEDIATE: refresh ngay

IMMEDIATE tương ứng với refresh=true. Elasticsearch yêu cầu refresh các shard liên quan trước khi request hoàn tất, để các thay đổi đã ghi trở nên khả dụng cho search.

Ví dụ:

    PUT products/_doc/p-101?refresh=true
    {
      "name": "Keyboard",
      "price": 45.0
    }

Sau khi request hoàn tất, search trên index liên quan có thể nhìn thấy thay đổi mà request vừa ghi.

IMMEDIATE hữu ích khi:

- Một thao tác nghiệp vụ phải ghi dữ liệu rồi ngay lập tức thực hiện search để xây dựng kết quả tiếp theo.
- Một quy trình quản trị nhỏ cần xác nhận dữ liệu đã xuất hiện trong search trước khi chuyển bước.
- Một integration test cần trạng thái search xác định ngay sau thao tác ghi.

Không nên dùng IMMEDIATE cho mọi lần ghi trong hệ thống có throughput cao. Refresh thường xuyên có thể tạo nhiều segment nhỏ, tăng công việc merge và làm giảm hiệu quả indexing/search. Nếu mỗi document được ghi bằng một request riêng rồi refresh ngay, chi phí có thể lớn hơn nhiều so với gom dữ liệu thành batch và refresh một lần.

### WAIT_UNTIL: chờ refresh tự nhiên

WAIT_UNTIL tương ứng với refresh=wait_for. Request ghi được xử lý, sau đó client chờ cho đến khi một lần refresh làm các thay đổi trở nên khả dụng cho search.

Ví dụ:

    PUT products/_doc/p-101?refresh=wait_for
    {
      "name": "Keyboard",
      "price": 45.0
    }

Khác với IMMEDIATE, WAIT_UNTIL không yêu cầu Elasticsearch refresh ngay lập tức. Nó chờ lần refresh tiếp theo. Khi refresh interval đang hoạt động bình thường, thời gian chờ thường gần với phần còn lại của chu kỳ refresh hiện tại.

WAIT_UNTIL phù hợp khi:

- Request cần ghi document và sau đó có thể trả về với bảo đảm document đã nhìn thấy qua search.
- Không muốn ép một lần refresh mới cho từng request.
- Tần suất ghi vừa phải và độ trễ chờ refresh chấp nhận được.
- Một luồng nghiệp vụ cần read-after-write qua search thay vì chỉ GET theo id.

Nếu index tắt refresh tự động bằng refresh_interval = -1, WAIT_UNTIL có thể phải chờ đến khi có một lần refresh được gọi thủ công hoặc một thao tác khác tạo refresh. Vì vậy, không nên dùng WAIT_UNTIL trong một giai đoạn bulk load đã tắt refresh mà không có kế hoạch refresh rõ ràng.

## 4. So sánh ba lựa chọn

| Tiêu chí | NONE / false | IMMEDIATE / true | WAIT_UNTIL / wait_for |
|---|---|---|---|
| Chủ động refresh ngay | Không | Có | Không |
| Chờ search visibility | Không | Có, qua refresh được yêu cầu | Có, đến lần refresh kế tiếp |
| Độ trễ response | Thường thấp | Có thể cao hơn do refresh | Phụ thuộc thời điểm refresh tiếp theo |
| Chi phí refresh | Theo lịch tự động | Có thể tăng nếu dùng thường xuyên | Tận dụng refresh tự nhiên |
| Phù hợp với ghi số lượng lớn | Thường phù hợp | Thường không phù hợp cho từng request | Có thể phù hợp tùy concurrency và yêu cầu |
| Read-after-write qua search | Không bảo đảm ngay | Có sau khi request hoàn tất | Có sau khi request hoàn tất |

Có thể nhớ theo mục tiêu:

- Ưu tiên throughput và chấp nhận eventual visibility: NONE.
- Cần search thấy dữ liệu ngay sau request: IMMEDIATE hoặc WAIT_UNTIL.
- Cần read-after-write nhưng không muốn ép refresh: WAIT_UNTIL thường là lựa chọn cân bằng.

## 5. Refresh interval và độ trễ tìm kiếm

Elasticsearch tự động refresh index theo refresh interval. Trong cấu hình phổ biến, interval mặc định thường là 1 giây, nhưng giá trị thực tế có thể được thay đổi theo index settings và môi trường triển khai.

Ví dụ cấu hình:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "5s"
      }
    }

Với interval 5 giây, một document được ghi ngay sau lần refresh có thể phải chờ gần 5 giây mới xuất hiện trong search nếu request dùng NONE và không có refresh khác xảy ra.

Tăng refresh interval có thể cải thiện hiệu quả indexing trong workload ghi nhiều, nhưng làm tăng độ trễ search visibility. Giảm interval có thể giúp dữ liệu mới xuất hiện nhanh hơn, nhưng làm refresh xảy ra thường xuyên hơn và tăng chi phí xử lý.

Không nên thay refresh interval chỉ để xử lý một endpoint có yêu cầu read-after-write đặc biệt. Có thể chọn WAIT_UNTIL cho request đó và giữ interval phù hợp với workload chung.

### Index ít được tìm kiếm

Elasticsearch có cơ chế tối ưu refresh cho index ít hoạt động tìm kiếm. Tùy phiên bản và trạng thái index, refresh có thể không diễn ra đúng theo cách một ứng dụng giả định từ một con số interval cố định. Vì vậy, hãy dựa vào hành vi và cấu hình thực tế thay vì coi interval là một SLA chính xác cho mọi index.

## 6. Read-after-write bằng GET khác với read-after-write bằng search

Đây là khác biệt quan trọng khi chọn refresh policy.

Elasticsearch GET API theo document id mặc định có tính realtime. Nó có thể đọc document vừa ghi từ dữ liệu nội bộ/translog mà không cần chờ refresh.

Ví dụ:

    PUT products/_doc/p-101?refresh=false
    {
      "name": "Keyboard",
      "price": 45.0
    }

    GET products/_doc/p-101

GET theo id có thể trả về document vừa ghi ngay cả khi document chưa xuất hiện trong search.

Nhưng truy vấn:

    GET products/_search
    {
      "query": {
        "term": {
          "_id": "p-101"
        }
      }
    }

có thể chưa tìm thấy document trước lần refresh tiếp theo.

Do đó, nếu service chỉ cần xác nhận document đã được lưu bằng id, có thể không cần refresh. Nếu service cần chạy một query search, aggregation hoặc query theo field ngay sau khi ghi, refresh policy mới trở nên quan trọng.

Không nên thêm refresh chỉ vì một thao tác GET theo id chưa được hiểu đúng. Hãy xác định loại đọc mà nghiệp vụ thực sự thực hiện.

## 7. Chọn policy theo từng luồng nghiệp vụ

### Ghi log hoặc event liên tục

Luồng ingest log thường ưu tiên throughput. Hệ thống có thể chấp nhận việc dashboard chậm hơn một khoảng ngắn so với thời điểm event được gửi.

Khuyến nghị thường dùng: NONE, để refresh theo interval hoặc lifecycle mặc định. Nếu dashboard cần cập nhật gần thời gian thực, điều chỉnh interval dựa trên tải và yêu cầu quan sát thay vì refresh ngay cho mỗi event.

### Tạo sản phẩm rồi hiển thị qua search

Giả sử người dùng tạo sản phẩm và màn hình tiếp theo lập tức tìm kiếm sản phẩm đó theo tên hoặc danh mục. Nếu search phải thấy dữ liệu ngay trước khi trả response, WAIT_UNTIL là lựa chọn hợp lý.

Nếu màn hình có thể hiển thị object từ response của lệnh tạo mà không cần query lại Elasticsearch, có thể dùng NONE. Khi đó ứng dụng trả object vừa tạo trực tiếp và search index sẽ cập nhật theo refresh bình thường.

### Cập nhật dữ liệu rồi chạy aggregation

Nếu một workflow ghi nhiều document rồi ngay sau đó chạy aggregation cần bao gồm toàn bộ thay đổi, có thể:

1. Ghi các document với NONE.
2. Sau khi toàn bộ batch đã hoàn tất, gọi refresh một lần trên index.
3. Chạy aggregation sau khi refresh hoàn tất.

Hoặc dùng WAIT_UNTIL cho bulk request nếu API và phiên bản client hỗ trợ. Cách gom thao tác thường tránh việc refresh sau từng document.

### Bulk import dữ liệu lớn

Khi nhập hàng trăm nghìn hoặc hàng triệu document:

- Tránh IMMEDIATE cho từng request.
- Có thể tạm tăng refresh interval hoặc tắt refresh tự động trong giai đoạn nạp dữ liệu nếu kế hoạch vận hành cho phép.
- Gửi bulk theo batch có giới hạn kích thước.
- Sau khi hoàn tất, gọi refresh một lần để dữ liệu khả dụng cho search.
- Khôi phục refresh interval ban đầu nếu đã thay đổi.

Nếu refresh_interval được đặt thành -1, cần chắc chắn bước refresh cuối cùng được thực hiện. Nếu bỏ qua, dữ liệu có thể chưa xuất hiện trong search cho đến khi có refresh khác được kích hoạt.

### Integration test

Test thường cần kết quả search xác định ngay sau khi ghi. Có thể dùng WAIT_UNTIL cho thao tác ghi trong test hoặc gọi refresh tường minh sau khi lưu dữ liệu:

    productRepository.save(product);
    operations.indexOps(Product.class).refresh();
    List<Product> found = productRepository.findByName(product.getName());

Refresh tường minh giúp test không phụ thuộc vào thời điểm refresh tự động. Tuy nhiên, không nên đưa cách làm này vào mọi request production nếu không có yêu cầu tương ứng.

## 8. Sử dụng refresh trong Elasticsearch Java API Client

Elasticsearch Java API Client cho phép thiết lập refresh option trên request ghi. Enum Refresh thường có các giá trị tương ứng False, True và WaitFor.

Ví dụ ghi một document và chờ refresh:

    client.index(request -> request
        .index("products")
        .id("p-101")
        .document(product)
        .refresh(Refresh.WaitFor)
    );

Nếu không đặt refresh, request thường dùng hành vi mặc định tương ứng không chờ refresh.

Với bulk request, có thể đặt refresh policy cho toàn bộ request:

    client.bulk(request -> request
        .refresh(Refresh.WaitFor)
        .operations(operation -> operation
            .index(index -> index
                .index("products")
                .id("p-101")
                .document(product)
            )
        )
    );

Bulk request có thể chứa nhiều item. Refresh option được áp dụng ở cấp request; nó không biến các item thành transaction và không làm item lỗi trở thành thành công.

Tên enum và cách cấu hình builder cần theo phiên bản Elasticsearch Java API Client trong dự án. Nếu sử dụng phiên bản cũ, package hoặc tên kiểu có thể khác.

## 9. Sử dụng refresh với Spring Data Elasticsearch

Trong Spring Data Elasticsearch, phần lớn ứng dụng thao tác thông qua repository hoặc ElasticsearchOperations. Cần phân biệt API ghi entity với thao tác refresh index.

### Lưu entity bằng repository

Ví dụ:

    productRepository.save(product);

hoặc:

    productRepository.saveAll(products);

Các lời gọi này không nên được hiểu là mặc định đã refresh index để search thấy dữ liệu ngay. Nếu ứng dụng cần read-after-write qua search, phải chọn cách điều khiển refresh phù hợp với API và phiên bản Spring Data đang dùng.

### Refresh tường minh qua IndexOperations

Spring Data cung cấp IndexOperations để thực hiện thao tác trên index:

    IndexOperations indexOperations =
        operations.indexOps(Product.class);

    indexOperations.refresh();

Sau khi refresh hoàn tất, search trên index có thể nhìn thấy các thay đổi đã được ghi trước đó và thuộc phạm vi index được refresh.

Nếu entity dùng alias hoặc tên index tùy chỉnh, có thể tạo IndexOperations bằng IndexCoordinates tương ứng để refresh đúng đích:

    IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

    indexOperations.refresh();

Không nên gọi refresh qua một IndexCoordinates không trỏ đến index/alias mà thao tác ghi thực sự sử dụng.

### Request-level refresh policy

Một số API ghi của Spring Data Elasticsearch có thể cho phép cấu hình refresh policy ở mức thao tác hoặc query; điểm đặt cấu hình phụ thuộc phiên bản và loại API đang dùng. Khi yêu cầu WAIT_UNTIL hoặc IMMEDIATE cho từng request, hãy kiểm tra đúng API của phiên bản dự án, thay vì giả định repository.save hoặc saveAll luôn nhận một tham số RefreshPolicy.

Nếu abstraction repository không cung cấp quyền điều khiển cần thiết, có thể:

- Dùng IndexOperations.refresh() sau nhóm thao tác ghi.
- Dùng ElasticsearchOperations hoặc API ghi có hỗ trợ refresh policy trong phiên bản hiện tại.
- Dùng Elasticsearch Java API Client trực tiếp cho request cần option cụ thể.

Khi chọn cách gọi trực tiếp, cần đảm bảo mapping, converter, exception handling và cấu hình client vẫn nhất quán với phần còn lại của ứng dụng.

## 10. Refresh và bulk indexing

Bulk API hỗ trợ refresh option ở cấp request. Với một batch có nhiều document, dùng WAIT_UNTIL có thể giúp caller chỉ tiếp tục sau khi các thay đổi thành công đã được refresh.

Ví dụ luồng:

    1. Tạo batch document.
    2. Gửi một bulk request với refresh=wait_for.
    3. Đọc BulkResponse và kiểm tra từng item.
    4. Sau khi response trả về, chạy search nếu cần.

Cần nhớ rằng:

- WAIT_UNTIL không đảm bảo mọi item đều thành công.
- Bulk response có thể chứa partial failure.
- Phải kiểm tra errors và item response.
- Chỉ những document được ghi thành công mới có thể xuất hiện trong search.
- Nếu request timeout, trạng thái item có thể chưa rõ và cần đối chiếu trước khi retry.

Không nên dùng refresh=true cho từng bulk nhỏ liên tiếp nếu có thể gom các batch hoặc dùng WAIT_UNTIL. Mỗi lần refresh có thể làm tăng số segment nhỏ và tạo thêm công việc cho cluster.

## 11. Ảnh hưởng của refresh đến hiệu năng

Refresh làm cho dữ liệu mới có thể được tìm kiếm, nhưng không miễn phí. Refresh thường xuyên có thể:

- Tạo nhiều segment nhỏ hơn.
- Tăng số segment mà search phải quản lý.
- Tăng chi phí merge về sau.
- Tăng CPU và I/O trong workload indexing.
- Làm giảm throughput khi ứng dụng ép refresh quá thường xuyên.

IMMEDIATE đặc biệt dễ gây chi phí nếu được dùng cho từng document. Ví dụ một API nhận 100 request mỗi giây, mỗi request ghi một document và refresh ngay có thể tạo tần suất refresh cao hơn nhiều so với việc gom dữ liệu.

WAIT_UNTIL thường giảm việc ép refresh vì nhiều request có thể cùng chờ một lần refresh tự nhiên. Tuy nhiên, nếu có quá nhiều request đồng thời chờ refresh, ứng dụng vẫn cần giới hạn concurrency và theo dõi latency.

NONE giữ luồng ghi nhẹ hơn, nhưng search visibility phụ thuộc refresh interval. Đây thường là lựa chọn tốt cho ingest lớn và các nghiệp vụ chấp nhận eventual consistency.

## 12. Những nhầm lẫn thường gặp

### Nghĩ rằng response ghi thành công có nghĩa search thấy ngay

Request ghi được xác nhận và search visibility là hai thời điểm khác nhau. Nếu cần tìm thấy document ngay qua search, hãy dùng WAIT_UNTIL, IMMEDIATE hoặc refresh tường minh.

### Nghĩ rằng WAIT_UNTIL ép refresh ngay

WAIT_UNTIL chờ một lần refresh làm dữ liệu khả dụng. Nó không chủ động yêu cầu refresh ngay như IMMEDIATE.

### Dùng IMMEDIATE cho mọi document

Ép refresh sau mỗi lần ghi có thể làm tăng số segment và chi phí merge. Chỉ dùng khi yêu cầu độ trễ read-after-write thực sự cần thiết.

### Nghĩ rằng NONE có nghĩa dữ liệu không được lưu

NONE chỉ không chờ refresh. Dữ liệu vẫn được ghi theo cơ chế Elasticsearch; search sẽ thấy sau refresh tự động hoặc refresh tường minh.

### Nhầm GET theo id với search

GET document theo id có thể realtime ngay cả khi search chưa thấy document. Trước khi thêm refresh, hãy xác định thao tác đọc là GET hay search.

### Nhầm refresh với durability

Refresh làm dữ liệu khả dụng cho search. Nó không thay thế translog durability, replication hoặc flush. Không dùng refresh policy như một bảo đảm rằng dữ liệu đã được fsync theo một cách cụ thể.

### Tắt refresh interval rồi quên refresh lại

Trong bulk load, tắt refresh có thể cải thiện throughput. Nhưng nếu không có bước refresh cuối cùng, search có thể chưa thấy dữ liệu. Hãy ghi rõ bước refresh và khôi phục setting trong quy trình.

### Nghĩ saveAll là một thao tác atomic có một refresh

saveAll có thể được triển khai bằng bulk hoặc cơ chế khác tùy phiên bản. Dù request có một refresh option, nó vẫn không tạo transaction all-or-nothing cho các document.

## 13. Cách quyết định policy

Có thể chọn theo câu hỏi nghiệp vụ:

| Câu hỏi | Lựa chọn thường phù hợp |
|---|---|
| Có cần search thấy document ngay sau khi ghi không? | Nếu không: NONE |
| Cần search thấy ngay nhưng không muốn ép refresh? | WAIT_UNTIL |
| Có yêu cầu đặc biệt phải refresh trước khi request trả về? | IMMEDIATE |
| Chỉ cần GET document theo id sau khi ghi? | Thường không cần refresh |
| Đang bulk import dữ liệu lớn? | NONE trong lúc ghi, refresh một lần sau khi hoàn tất |
| Integration test cần search kết quả vừa ghi? | WAIT_UNTIL hoặc refresh tường minh |

Trước khi chọn, hãy xác định:

1. Read-after-write có phải yêu cầu nghiệp vụ hay chỉ là tiện ích trong code?
2. Tầng đọc sử dụng GET theo id hay search/query/aggregation?
3. Có thể trả object vừa ghi trực tiếp cho client không?
4. Độ trễ refresh hiện tại có đáp ứng được yêu cầu không?
5. Lưu lượng ghi và số request đồng thời là bao nhiêu?
6. Có thể refresh một lần sau batch thay vì từng document không?

## 14. Ví dụ thiết kế service theo yêu cầu đọc sau ghi

Giả sử service tạo sản phẩm rồi trả lại danh sách tìm kiếm theo tên. Nếu contract API yêu cầu danh sách phải bao gồm sản phẩm vừa tạo, có hai hướng thiết kế.

### Hướng A: dùng WAIT_UNTIL cho thao tác ghi

Service ghi document với refresh policy WAIT_UNTIL bằng API ghi tương ứng, sau đó thực hiện search. Khi write request trả về, thay đổi đã khả dụng cho search.

Ưu điểm:

- Dễ hiểu với luồng ghi rồi search.
- Không cần gọi refresh tường minh ở tầng service.
- Không ép refresh ngay nếu refresh tự động sắp diễn ra.

Đánh đổi:

- Request tạo sản phẩm phải chờ refresh.
- Latency phụ thuộc refresh interval và tải cluster.
- Cần bảo đảm API Spring Data/client thực sự áp dụng WAIT_UNTIL cho thao tác ghi.

### Hướng B: ghi với NONE, sau đó refresh một lần

Nếu một workflow ghi nhiều sản phẩm rồi thực hiện một truy vấn tổng hợp, có thể:

    productRepository.saveAll(products);
    operations.indexOps(Product.class).refresh();
    return productRepository.searchByCategory("keyboard");

Ưu điểm:

- Có thể gom nhiều thao tác ghi trước một lần refresh.
- Phù hợp với batch hoặc workflow có ranh giới rõ ràng.

Đánh đổi:

- Refresh tường minh tác động đến index và có chi phí.
- Nếu có nhiều writer đồng thời, refresh cũng có thể làm những thay đổi khác trên cùng index trở nên khả dụng.
- Cần xử lý trường hợp saveAll có lỗi từng phần trước khi chạy search.

Nếu API chỉ cần trả về object vừa tạo, một hướng thứ ba đơn giản hơn là trả object từ service mà không search lại Elasticsearch. Khi đó không cần thêm refresh chỉ để dựng response.

## Kết luận

Refresh policy điều khiển thời điểm document mới trở nên khả dụng cho search sau khi ghi. NONE không chờ refresh và thường phù hợp với ingest throughput cao; IMMEDIATE ép refresh trước khi request hoàn tất; WAIT_UNTIL chờ lần refresh tự nhiên và thường là lựa chọn cân bằng khi cần read-after-write qua search.

Trước khi chọn policy, cần phân biệt GET theo id với search: GET có thể realtime mà không cần refresh, trong khi search cần dữ liệu đã được refresh. Refresh cũng khác flush và durability; nó không tạo transaction hoặc rollback cho saveAll/bulk. Với Spring Data Elasticsearch, có thể dùng API refresh tường minh qua IndexOperations hoặc API ghi có hỗ trợ refresh policy theo phiên bản. Hãy chỉ trả chi phí refresh khi nghiệp vụ thực sự cần kết quả search nhìn thấy dữ liệu ngay, và ưu tiên gom thao tác trước một lần refresh khi xử lý batch.
