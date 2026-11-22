# Chọn kích thước lô, timeout và mức tiêu thụ bộ nhớ

Khi xuất hoặc xử lý một lượng lớn tài liệu từ Elasticsearch, ứng dụng không nên tải toàn bộ kết quả vào một danh sách rồi mới bắt đầu xử lý. Cách làm đó có thể làm heap tăng nhanh, gây garbage collection kéo dài hoặc dẫn đến OutOfMemoryError. Thay vào đó, hãy đọc dữ liệu theo từng lô, xử lý xong lô hiện tại rồi mới lấy lô tiếp theo.

Ba tham số cần được thiết kế cùng nhau là **kích thước lô**, **thời gian giữ scroll context** và **ngân sách bộ nhớ**. Chúng có liên quan nhưng không có cùng ý nghĩa:

- **Batch size** quyết định số hit được lấy trong mỗi lần đọc.
- **Scroll keep-alive** quyết định Elasticsearch giữ search context trong bao lâu để ứng dụng có thể yêu cầu lô tiếp theo.
- **Search timeout** giới hạn thời gian Elasticsearch chờ xử lý truy vấn.
- **Client timeout** giới hạn thời gian ứng dụng chờ phản hồi qua mạng.
- **Memory budget** quyết định ứng dụng có thể giữ bao nhiêu tài liệu và dữ liệu trung gian cùng lúc.

Không có một giá trị batch size hoặc timeout phù hợp cho mọi index. Kích thước tài liệu, mapping, số shard, tốc độ xử lý của ứng dụng, độ trễ mạng và tài nguyên cluster đều ảnh hưởng đến lựa chọn. Bài này sử dụng ví dụ xuất tài liệu Product từ index **products**, tập trung vào cách chọn các giá trị có căn cứ và giữ mức sử dụng bộ nhớ ổn định.

## 1. Vì sao cần đọc dữ liệu theo lô?

Giả sử index có 2 triệu sản phẩm. Nếu ứng dụng gọi một truy vấn lấy tất cả tài liệu rồi chuyển thành List<Product>, nó phải giữ một lượng lớn object Java trong heap. Ngoài source JSON, mỗi entity còn có object header, reference, String, collection và metadata do converter tạo ra.

Mô hình tải toàn bộ:

~~~text
Elasticsearch
     |
     v
Lấy toàn bộ 2 triệu tài liệu
     |
     v
Chuyển đổi thành 2 triệu Product
     |
     v
Giữ toàn bộ List<Product> trong heap
     |
     v
Xử lý hoặc ghi file
~~~

Nếu bộ nhớ không đủ, ứng dụng có thể gặp:

- Heap tăng liên tục.
- Garbage collection chạy thường xuyên và kéo dài.
- Thời gian phản hồi tăng.
- JVM bị OutOfMemoryError.
- Tiến trình xuất dữ liệu thất bại giữa chừng.

Đọc theo lô giới hạn số tài liệu được giữ tại một thời điểm:

~~~text
Lấy lô 1 --> xử lý lô 1 --> giải phóng tham chiếu
     |
     v
Lấy lô 2 --> xử lý lô 2 --> giải phóng tham chiếu
     |
     v
Lấy lô 3 --> xử lý lô 3 --> giải phóng tham chiếu
     |
     v
                  ...
~~~

Ứng dụng có thể xử lý hàng triệu tài liệu mà không cần giữ toàn bộ chúng trong bộ nhớ. Điều kiện là phần xử lý phía sau cũng phải có giới hạn: không đưa tất cả tài liệu vào một List, queue hoặc cache không giới hạn.

## 2. Batch size là gì?

**Batch size** là số hit mà ứng dụng yêu cầu trong một lần lấy dữ liệu. Với Search API, nó thường được biểu diễn bằng thuộc tính **size** trong request body. Với Spring Data Elasticsearch, có thể đặt kích thước trang qua **Pageable** khi xây dựng Query.

Ví dụ request lấy 500 tài liệu:

~~~http
POST /products/_search
{
  "size": 500,
  "query": {
    "match_all": {}
  }
}
~~~

Trong một quy trình scroll, mỗi response trả về một lô hit. Khi ứng dụng yêu cầu lô tiếp theo, Elasticsearch sử dụng search context đã được giữ từ truy vấn ban đầu.

Batch size không phải tổng số tài liệu cần xuất. Nếu index có 2 triệu tài liệu và size là 500, ứng dụng sẽ phải đọc nhiều lô liên tiếp để hoàn thành công việc.

Cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| **Batch size / size** | Số hit yêu cầu trong một response |
| **Total hits** | Tổng số tài liệu khớp truy vấn, nếu được theo dõi |
| **Scroll keep-alive** | Thời gian giữ search context giữa các lần lấy lô |
| **Search timeout** | Thời gian chờ xử lý truy vấn trên Elasticsearch |
| **Client timeout** | Thời gian client chờ request/response |
| **Export duration** | Tổng thời gian ứng dụng xử lý tất cả các lô |

Không nên đặt size bằng tổng số hit chỉ vì muốn xuất toàn bộ dữ liệu. Hãy chọn size dựa trên kích thước tài liệu, bộ nhớ và tốc độ xử lý.

## 3. Kích thước lô ảnh hưởng đến hiệu năng như thế nào?

Batch size nhỏ và lớn đều có lợi thế và chi phí.

| Batch size nhỏ | Batch size lớn |
|---|---|
| Mỗi response chứa ít tài liệu | Mỗi response chứa nhiều tài liệu |
| Ít dữ liệu cần giữ trong heap tại một thời điểm | Heap cần đủ chỗ cho nhiều entity hơn |
| Nhiều lần round-trip đến Elasticsearch | Ít lần round-trip hơn |
| Có thể tăng overhead mạng và xử lý request | Có thể tăng throughput đến một mức nhất định |
| Dễ xử lý khi tài liệu lớn | Có nguy cơ GC hoặc bộ nhớ tăng mạnh |
| Phù hợp khi mỗi tài liệu nặng hoặc xử lý chậm | Phù hợp hơn khi tài liệu nhỏ và sink xử lý nhanh |

Ví dụ, batch size 50 có thể an toàn với tài liệu chứa nhiều nested object hoặc trường văn bản dài, nhưng sẽ tạo nhiều request hơn so với size 500. Ngược lại, size 5.000 có thể giảm số lần gọi mạng nhưng khiến mỗi response lớn, tốn bộ nhớ và làm tăng thời gian chuyển đổi.

Tăng batch size không bảo đảm tốc độ tăng tuyến tính. Khi network, CPU, disk hoặc tốc độ ghi đích đã bão hòa, tăng thêm tài liệu mỗi lô chỉ làm bộ nhớ và độ trễ tăng mà không cải thiện throughput đáng kể.

## 4. Cách chọn batch size ban đầu

Không có một con số chuẩn cho mọi ứng dụng. Có thể bắt đầu bằng một giá trị vừa phải, đo lường rồi điều chỉnh.

Một cách thử nghiệm thực tế:

1. Bắt đầu với 200 hoặc 500 tài liệu mỗi lô.
2. Chạy trên dữ liệu có kích thước và phân bố gần production.
3. Theo dõi heap, GC, thời gian mỗi batch và throughput.
4. Tăng lên 1.000 nếu heap còn dư và thời gian xử lý mỗi request là overhead đáng kể.
5. Giảm xuống 100 hoặc 50 nếu response lớn, entity nặng, GC tăng hoặc xử lý một batch quá lâu.
6. Dừng tăng khi throughput không cải thiện rõ rệt hoặc tài nguyên bắt đầu chịu áp lực.

Các giá trị 50, 100, 200, 500 và 1.000 chỉ là các điểm thử nghiệm thường tiện so sánh, không phải giới hạn hay khuyến nghị cố định của Elasticsearch.

### Cân nhắc kích thước tài liệu

Số lượng tài liệu không phản ánh đầy đủ dung lượng response. 500 tài liệu chỉ có vài trường keyword có thể nhỏ hơn nhiều so với 500 tài liệu chứa mô tả dài, nested object và mảng lớn.

Khi chọn size, cần đo:

- Kích thước response trung bình theo byte.
- Số lượng trường được trả về.
- Độ phức tạp object Java sau khi converter ánh xạ.
- Số lượng collection hoặc nested object được tạo.
- Chi phí xử lý hoặc ghi mỗi tài liệu.

Nếu tài liệu có source lớn, hãy giảm batch size hoặc dùng source filtering để chỉ lấy các trường cần xuất. Source filtering giúp giảm dữ liệu truyền và chuyển đổi, nhưng chỉ nên áp dụng nếu các trường bị bỏ không cần cho nghiệp vụ.

### Cân nhắc tốc độ của nơi nhận dữ liệu

Nếu ứng dụng đọc nhanh hơn nhiều so với khả năng ghi vào file, database hoặc dịch vụ đích, batch lớn có thể làm dữ liệu chờ tích tụ trong bộ nhớ.

Ví dụ:

~~~text
Elasticsearch: 10.000 tài liệu/giây
          |
          v
Ứng dụng đọc và chuyển đổi nhanh
          |
          v
Queue không giới hạn
          |
          v
Hệ thống đích: 1.000 tài liệu/giây
~~~

Queue sẽ tăng liên tục vì tốc độ tiêu thụ thấp hơn tốc độ sản xuất. Giảm batch size chỉ làm chậm thời điểm đầy bộ nhớ; nó không giải quyết sự chênh lệch tốc độ. Cần dùng queue có giới hạn, backpressure hoặc điều chỉnh tốc độ đọc theo khả năng ghi đích.

## 5. Ước lượng bộ nhớ cho mỗi batch

Bộ nhớ cần thiết không chỉ bằng kích thước JSON trong response. Khi Spring Data chuyển source thành Java object, heap còn chứa:

- Entity Product và object lồng nhau.
- String và mảng ký tự/byte.
- List, Map và các collection.
- SearchHit cùng metadata như ID, score và highlight.
- Buffer của HTTP client và JSON parser.
- Batch đang được ứng dụng xử lý.
- Dữ liệu được serialize để ghi sang hệ thống đích.
- Queue hoặc task đang chờ xử lý.

Có thể dùng công thức ước lượng đơn giản:

\[
M_{\text{batch}} \approx B \times H
\]

Trong đó:

- \(B\) là batch size.
- \(H\) là heap footprint trung bình của một tài liệu sau khi chuyển đổi.

Đây chỉ là ước lượng cho phần entity của một batch. Bộ nhớ đỉnh thực tế còn bao gồm response buffer, batch đang ghi, queue, object tạm và các luồng xử lý song song.

Ví dụ nếu một Product sau chuyển đổi chiếm trung bình 8 KB trên heap và batch size là 500:

\[
500 \times 8\text{ KB} \approx 4\text{ MB}
\]

Con số này chưa bao gồm các cấu trúc phụ và dữ liệu tạm. Không nên lấy kích thước source JSON làm heap footprint chính xác; object Java thường có overhead và cách biểu diễn khác với JSON.

### Khi xử lý nhiều batch cùng lúc

Nếu ứng dụng cho phép 4 batch được xử lý đồng thời, bộ nhớ cho các batch có thể tăng gần theo số lượng batch đang hoạt động:

\[
M_{\text{in-flight}} \approx C \times B \times H
\]

Trong đó \(C\) là số batch hoặc worker đang giữ dữ liệu cùng lúc. Đây vẫn là ước lượng đơn giản, nhưng giúp nhận ra rằng tăng concurrency cũng làm tăng áp lực bộ nhớ.

Không nên tăng batch size và số worker cùng lúc mà không đo lường. Thay đổi một biến mỗi lần sẽ giúp xác định nguyên nhân khi heap hoặc GC tăng.

## 6. Scroll keep-alive là gì?

Scroll API giữ một **search context** để ứng dụng tiếp tục lấy các batch sau truy vấn ban đầu. Tham số **scroll** xác định thời gian Elasticsearch giữ context đó sau mỗi lần tương tác.

Ví dụ:

~~~http
POST /products/_search?scroll=90s
{
  "size": 500,
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Response đầu tiên chứa một **_scroll_id**. Ứng dụng dùng ID này để yêu cầu batch tiếp theo:

~~~http
POST /_search/scroll
{
  "scroll": "90s",
  "scroll_id": "ID_TRA_VE_TU_RESPONSE"
}
~~~

Mỗi lần scroll tiếp theo có thể trả về scroll ID mới. Ứng dụng phải dùng ID mới nhất nhận được trong response tiếp theo.

Khi hoàn thành, cần xóa scroll context:

~~~http
DELETE /_search/scroll
{
  "scroll_id": [
    "ID_SCROLL_MOI_NHAT"
  ]
}
~~~

### Keep-alive không phải tổng thời gian export

Nếu keep-alive là 90 giây, điều đó không có nghĩa toàn bộ export phải hoàn tất trong 90 giây. Context được gia hạn khi ứng dụng gửi request scroll tiếp theo với thời gian keep-alive mới.

Ví dụ:

- Batch 1 được trả về.
- Ứng dụng xử lý batch 1 trong 40 giây.
- Ứng dụng yêu cầu batch 2 với keep-alive 90 giây.
- Context tiếp tục được giữ trong khoảng thời gian mới.
- Quy trình lặp lại cho đến khi hết dữ liệu.

Keep-alive cần đủ dài để bao phủ khoảng thời gian ứng dụng xử lý một batch và gửi request kế tiếp, cộng thêm biên an toàn cho độ trễ mạng hoặc tải tạm thời.

Nếu mỗi batch mất 2 phút để xử lý nhưng keep-alive chỉ là 30 giây, context có thể hết hạn trước khi ứng dụng yêu cầu batch tiếp theo.

Không cần đặt keep-alive bằng tổng thời gian của một export kéo dài nhiều giờ. Hãy đặt theo thời gian tối đa dự kiến giữa hai request scroll liên tiếp.

## 7. Search timeout khác scroll keep-alive

**Search timeout** và **scroll keep-alive** là hai tham số độc lập.

- Search timeout giới hạn thời gian Elasticsearch chờ thực hiện một search request.
- Scroll keep-alive xác định thời gian giữ search context giữa các lần lấy batch.
- Client timeout là thời gian ứng dụng chờ response qua kết nối.
- Thời gian xử lý batch là thời gian code phía ứng dụng tiêu thụ dữ liệu.

Ví dụ search request có cả timeout và scroll:

~~~http
POST /products/_search?scroll=90s
{
  "size": 500,
  "timeout": "20s",
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Ở đây:

- **scroll=90s** yêu cầu giữ search context trong 90 giây giữa các lần scroll.
- **timeout=20s** giới hạn thời gian chờ thực thi tìm kiếm theo hành vi Search API.
- **size=500** yêu cầu 500 hit trong mỗi batch.
- **sort: _doc** tối ưu cách duyệt tài liệu khi không cần thứ tự relevance.

Nếu search timeout xảy ra, response có thể cho biết truy vấn đã bị timeout hoặc có shard không hoàn tất, tùy cấu hình partial results và phiên bản. Một quy trình export cần kiểm tra trạng thái response, chẳng hạn **timed_out** và thông tin shard, thay vì mặc định rằng mọi response đều chứa đầy đủ kết quả.

### Client timeout

Client HTTP hoặc Elasticsearch Java API Client có timeout riêng. Nếu client dừng chờ sau 10 giây trong khi server vẫn đang xử lý request, ứng dụng có thể nhận lỗi timeout ở phía client dù nguyên nhân khác với Search API timeout.

Cần phân biệt:

| Tham số | Nơi kiểm soát | Tác dụng |
|---|---|---|
| **scroll keep-alive** | Search/scroll request | Giữ search context giữa các batch |
| **Search API timeout** | Search request body | Giới hạn thời gian chờ xử lý truy vấn |
| **Client request/socket timeout** | Cấu hình HTTP transport/client | Giới hạn thời gian client chờ response |
| **Application deadline** | Logic ứng dụng hoặc job scheduler | Giới hạn tổng thời gian một tác vụ được phép chạy |

Đừng tăng scroll keep-alive để sửa lỗi client timeout. Cũng đừng tăng client timeout để bù cho một scroll context đã hết hạn. Trước khi điều chỉnh, hãy xác định đúng loại timeout trong log và exception.

## 8. Chọn keep-alive dựa trên thời gian xử lý một batch

Một cách chọn thực tế là đo thời gian từ lúc nhận một batch đến lúc ứng dụng gửi yêu cầu batch tiếp theo.

Ví dụ:

| Công đoạn | Thời gian |
|---|---:|
| Nhận response và chuyển đổi | 2 giây |
| Xử lý 500 Product | 18 giây |
| Ghi dữ liệu đích | 25 giây |
| Độ trễ mạng và dao động tải | 5 giây |
| Tổng khoảng giữa hai lần scroll | Khoảng 50 giây |

Nếu thời gian giữa hai request thường khoảng 50 giây, keep-alive 90 giây có thể là điểm khởi đầu để thử nghiệm. Nếu hệ thống đích đôi khi chậm 2 phút, cần điều chỉnh hoặc chia nhỏ batch để giảm thời gian giữ dữ liệu.

Không chọn keep-alive quá dài mà không có lý do. Mỗi scroll context giữ tài nguyên phía Elasticsearch, có thể giữ các segment cũ và làm chậm việc giải phóng tài nguyên sau cập nhật hoặc merge. Nhiều context mở cùng lúc sẽ tạo thêm áp lực lên cluster.

Cũng không chọn keep-alive quá ngắn khiến context thường xuyên hết hạn khi ứng dụng xử lý batch.

## 9. Mức tiêu thụ bộ nhớ phía Elasticsearch

Scroll context tiêu thụ tài nguyên ở phía cluster, không chỉ phía JVM ứng dụng. Elasticsearch phải giữ trạng thái tìm kiếm để tiếp tục trả các batch tiếp theo.

Một số ảnh hưởng:

- Search context được giữ mở trong thời gian scroll.
- Các segment cần thiết cho góc nhìn dữ liệu của scroll có thể tiếp tục được giữ.
- File descriptor và tài nguyên liên quan có thể chưa được giải phóng.
- Nhiều scroll context đồng thời làm tăng áp lực lên node.
- Keep-alive dài làm tài nguyên tồn tại lâu hơn nếu ứng dụng không tiếp tục hoặc không xóa context.

Vì vậy, hãy đóng scroll ngay sau khi hoàn thành hoặc khi job thất bại. Không để scroll context tồn tại chỉ vì ứng dụng quên gọi clear hoặc iterator không được đóng.

Elasticsearch có giới hạn số scroll context đang mở, thường được kiểm soát bởi setting **search.max_open_scroll_context**. Giá trị mặc định và cách cấu hình phụ thuộc phiên bản. Không nên tăng giới hạn chỉ để cho phép nhiều job export cùng chạy mà chưa đánh giá heap, file descriptor và tải cluster.

Có thể theo dõi số search context đang mở qua node stats, bao gồm thông tin search contexts. Tên trường và đường dẫn API có thể khác theo phiên bản, nhưng cần quan sát số context mở, heap, GC, CPU và trạng thái node trong thời gian export.

## 10. Vì sao nên dùng sort _doc khi scroll toàn bộ index?

Nếu mục tiêu chỉ là duyệt toàn bộ tài liệu, không cần sắp xếp theo relevance hoặc một trường nghiệp vụ, Elasticsearch khuyến nghị dùng **_doc** sort trong scroll để duyệt hiệu quả.

Ví dụ:

~~~http
POST /products/_search?scroll=90s
{
  "size": 500,
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

**_doc** là thứ tự nội bộ phù hợp cho việc quét dữ liệu. Nó không mang ý nghĩa thứ tự nghiệp vụ như giá tăng dần hoặc ngày tạo mới nhất.

Nếu export cần thứ tự ổn định theo khóa nghiệp vụ, hãy xác định rõ sort field và tie-breaker. Sort theo trường có thể làm truy vấn tốn kém hơn so với duyệt theo _doc, tùy mapping và cấu trúc index.

Với quy trình chỉ cần chuyển tất cả tài liệu sang hệ thống khác, thường không cần tính relevance score. Dùng match_all cùng _doc giúp biểu đạt đúng mục tiêu quét dữ liệu.

## 11. Dùng SearchHitsIterator trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp **SearchHitsIterator<T>** và phương thức **searchForStream(...)** để duyệt kết quả theo luồng. Iterator giúp ứng dụng xử lý từng hit mà không cần giữ toàn bộ kết quả trong một List.

Ví dụ với Spring Data Elasticsearch 5.x:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

int batchSize = 500;

Query query = NativeQuery.builder()
        .withQuery(q -> q.matchAll(m -> m))
        .withPageable(PageRequest.of(0, batchSize))
        .build();

try (SearchHitsIterator<Product> hits = operations.searchForStream(
        query,
        Product.class,
        IndexCoordinates.of("products")
)) {
    while (hits.hasNext()) {
        SearchHit<Product> hit = hits.next();
        Product product = hit.getContent();

        exportProduct(product);
    }
}
~~~

Trong ví dụ:

- **PageRequest.of(0, batchSize)** đặt kích thước trang dùng làm batch size.
- **searchForStream(...)** trả iterator để đọc hit tuần tự.
- **hasNext()** kiểm tra còn hit hay không.
- **next()** lấy hit tiếp theo.
- **getContent()** lấy entity Product.
- **try-with-resources** bảo đảm iterator được đóng khi hoàn tất hoặc khi có exception.

API và cách cấu hình scroll keep-alive có thể khác theo phiên bản Spring Data Elasticsearch. Một số phiên bản cung cấp overload nhận **SearchScrollSpec** hoặc API scroll riêng để chỉ định thời gian giữ context. Hãy kiểm tra chữ ký của phiên bản đang dùng; không suy luận rằng batch size và keep-alive là cùng một thiết lập.

### Không chuyển iterator thành List nếu muốn tiết kiệm bộ nhớ

Cách sau làm mất lợi ích của xử lý theo luồng:

~~~java
List<Product> allProducts = new ArrayList<>();

try (SearchHitsIterator<Product> hits = operations.searchForStream(
        query,
        Product.class,
        IndexCoordinates.of("products")
)) {
    while (hits.hasNext()) {
        allProducts.add(hits.next().getContent());
    }
}
~~~

Iterator có thể đọc từng batch, nhưng đoạn mã lại giữ tất cả entity trong **allProducts**. Với index lớn, heap vẫn tăng theo tổng số tài liệu.

Hãy xử lý mỗi entity ngay khi đọc hoặc chỉ giữ một batch nhỏ cần thiết cho hệ thống đích.

## 12. Tách batch đọc và batch ghi

Trong một quy trình export hoặc chuyển dữ liệu, batch đọc từ Elasticsearch và batch ghi sang hệ thống đích không nhất thiết phải bằng nhau.

Ví dụ:

- Đọc 500 Product từ Elasticsearch.
- Chuyển đổi từng Product.
- Gom 100 record đã chuyển đổi.
- Ghi 100 record sang hệ thống đích.
- Lặp lại cho đến khi hết 500 Product.

Hai tham số có ý nghĩa khác nhau:

| Tham số | Kiểm soát |
|---|---|
| **readBatchSize** | Số tài liệu lấy từ Elasticsearch trong một lần đọc |
| **writeBatchSize** | Số bản ghi gom lại trước khi ghi sang hệ thống đích |
| **maxInFlightBatches** | Số batch được phép xử lý đồng thời |
| **queueCapacity** | Số phần tử hoặc batch tối đa đang chờ |

Nếu hệ thống đích có bulk API tối ưu ở 100 record, không nhất thiết phải giảm read batch size xuống 100. Ứng dụng có thể đọc 500 và chia thành 5 lần ghi, miễn là bộ nhớ và luồng xử lý được giới hạn.

Ví dụ xử lý theo nhóm ghi:

~~~java
int readBatchSize = 500;
int writeBatchSize = 100;

List<ExportRecord> writeBatch = new ArrayList<>(writeBatchSize);

try (SearchHitsIterator<Product> hits = operations.searchForStream(
        query,
        Product.class,
        IndexCoordinates.of("products")
)) {
    while (hits.hasNext()) {
        Product product = hits.next().getContent();

        writeBatch.add(toExportRecord(product));

        if (writeBatch.size() == writeBatchSize) {
            destination.writeBatch(writeBatch);
            writeBatch.clear();
        }
    }

    if (!writeBatch.isEmpty()) {
        destination.writeBatch(writeBatch);
    }
}
~~~

Trong ví dụ, read batch size được đặt ở Pageable khi tạo query; write batch size điều khiển collection ở phía ứng dụng. Đoạn mã chỉ giữ tối đa một nhóm ghi do ứng dụng tạo ra, ngoài batch nội bộ mà iterator đang quản lý.

Nếu destination ghi chậm, lời gọi writeBatch sẽ làm ứng dụng tạm dừng đọc. Đây là backpressure tự nhiên và giúp không tích lũy dữ liệu vô hạn.

## 13. Dùng scroll API trực tiếp khi cần kiểm soát keep-alive

Trong các phiên bản Spring Data Elasticsearch có API scroll tường minh, có thể bắt đầu scroll, tiếp tục scroll và xóa context thông qua các phương thức tương ứng trên **ElasticsearchOperations**. Chữ ký cụ thể phụ thuộc phiên bản, vì vậy cần kiểm tra API hiện có trong dự án.

Ở mức Elasticsearch REST API, vòng đời scroll có ba bước:

~~~text
1. Search ban đầu với tham số scroll
          |
          v
2. Nhận _scroll_id và batch đầu tiên
          |
          v
3. Gọi _search/scroll bằng ID mới nhất
          |
          v
4. Lặp cho đến khi batch rỗng
          |
          v
5. Gọi clear scroll để giải phóng context
~~~

Ví dụ request đầu:

~~~http
POST /products/_search?scroll=2m
{
  "size": 500,
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Request tiếp tục:

~~~http
POST /_search/scroll
{
  "scroll": "2m",
  "scroll_id": "SCROLL_ID_MOI_NHAT"
}
~~~

Xóa context:

~~~http
DELETE /_search/scroll
{
  "scroll_id": [
    "SCROLL_ID_MOI_NHAT"
  ]
}
~~~

Cần dùng scroll ID mới nhất được trả về trong từng response. Không giả định ID ban đầu luôn là ID cần dùng cho toàn bộ vòng đời.

Khi dùng API scroll trực tiếp, hãy bảo đảm clear context trong khối finally hoặc cơ chế cleanup tương đương. Nếu dùng SearchHitsIterator, đóng iterator bằng try-with-resources để thư viện thực hiện cleanup.

## 14. Scroll context và dữ liệu thay đổi trong lúc export

Scroll duy trì một góc nhìn dữ liệu từ thời điểm search ban đầu. Vì vậy, các thay đổi phát sinh sau khi scroll bắt đầu không nhất thiết xuất hiện trong cùng phiên scroll.

Ví dụ:

1. Export bắt đầu lúc 10:00.
2. Search context được tạo.
3. Một sản phẩm mới được ghi lúc 10:05.
4. Scroll tiếp tục lấy các batch còn lại.

Tài liệu mới được thêm sau thời điểm bắt đầu có thể không xuất hiện trong phiên scroll hiện tại. Tương tự, việc tài liệu bị cập nhật hoặc xóa trong lúc export không có nghĩa kết quả scroll sẽ phản ánh ngay trạng thái mới nhất.

Điều này hữu ích nếu muốn export một góc nhìn nhất quán tại thời điểm bắt đầu, nhưng cần lưu ý nếu mục tiêu là đồng bộ liên tục.

Nếu cần xuất dữ liệu gần thời gian thực, hãy thiết kế cơ chế đồng bộ thay đổi riêng, chẳng hạn:

- Lưu mốc thời gian hoặc watermark của lần export.
- Dùng updatedAt hoặc sequence/version theo mô hình dữ liệu.
- Chạy lượt đồng bộ phần thay đổi sau mốc.
- Dùng change data capture hoặc event log nếu hệ thống nguồn hỗ trợ.
- Ghi checkpoint để có thể tiếp tục sau lỗi.

Không nên cho rằng scroll tự động thu thập các tài liệu mới được ghi trong khi export đang chạy.

## 15. Khi nào dùng scroll, search_after và Point in Time?

Scroll không phải lựa chọn duy nhất để đọc sâu dữ liệu.

| Cơ chế | Trường hợp phù hợp | Đặc điểm |
|---|---|---|
| **from/size** | Phân trang thông thường với số trang nông | Dễ dùng nhưng không phù hợp deep pagination lớn |
| **scroll** | Batch export hoặc xử lý tuần tự số lượng lớn | Giữ search context; cần clear sau khi hoàn tất |
| **search_after** | Duyệt sâu theo sort values | Không giữ một danh sách trang trước; cần sort ổn định |
| **Point in Time (PIT) + search_after** | Phân trang sâu cần góc nhìn dữ liệu nhất quán | PIT giữ góc nhìn index; search_after tiếp tục từ cursor |

Với giao diện người dùng cần chuyển qua nhiều trang, **PIT + search_after** thường là hướng phù hợp hơn scroll. Scroll phù hợp với job đọc tuần tự và xử lý hàng loạt.

Không nên dùng scroll như cơ chế phân trang cho từng lần người dùng bấm “Trang tiếp theo” trong giao diện. Một scroll context tồn tại lâu có thể giữ tài nguyên trong cluster và không phù hợp với hành vi người dùng có thể dừng giữa chừng.

## 16. Timeout trong Spring Data Elasticsearch

Khi dùng Spring Data Elasticsearch, cần xác định API đang điều khiển loại timeout nào.

**Scroll keep-alive:** Một số API stream/scroll cho phép truyền cấu hình scroll spec hoặc thời gian giữ context. Tên lớp và overload thay đổi theo phiên bản. Khi sử dụng, chọn thời gian dựa trên khoảng thời gian tối đa giữa hai lần lấy batch, không dựa trên tổng thời gian export.

**Search timeout:** Nếu query ban đầu có thể tốn thời gian, có thể cấu hình timeout ở cấp search request qua Query abstraction hoặc NativeQuery nếu phiên bản hỗ trợ. Search timeout không thay thế keep-alive.

**Client timeout:** Cấu hình trên Elasticsearch Java API Client hoặc HTTP transport quyết định thời gian client chờ request. Cần đủ dài cho một response batch có kích thước dự kiến, nhưng không nên để request treo vô hạn.

**Application timeout:** Job scheduler, worker hoặc request HTTP bên ngoài có thể có deadline riêng. Nếu export chạy trong background, hãy dùng thời gian thực thi phù hợp với loại job và cơ chế theo dõi trạng thái.

Khi gặp timeout, hãy ghi nhận:

- Loại timeout phát sinh.
- Batch đang xử lý.
- Thời gian truy vấn và thời gian xử lý phía ứng dụng.
- Scroll context còn hiệu lực hay đã hết hạn.
- Response có cờ timed_out hoặc shard failure không.
- Client có ngắt kết nối trước khi server trả kết quả không.

Đừng retry toàn bộ export một cách mù quáng nếu chưa biết batch nào đã được ghi vào đích. Hãy thiết kế checkpoint hoặc thao tác ghi idempotent để tránh nhân đôi dữ liệu.

## 17. Kiểm soát bộ nhớ bằng backpressure

Backpressure là cách điều chỉnh tốc độ đọc theo khả năng xử lý của hệ thống phía sau. Nếu destination chậm, ứng dụng không tiếp tục lấy batch nhanh hơn khả năng ghi.

Một pipeline không giới hạn:

~~~text
Elasticsearch --> Reader --> Unbounded Queue --> Slow Writer
                                  |
                                  v
                          Memory grows forever
~~~

Pipeline có giới hạn:

~~~text
Elasticsearch --> Reader --> Bounded Queue --> Writer
                      ^                         |
                      |                         |
                      +---- Wait when full -----+
~~~

Có thể triển khai bằng:

- Xử lý tuần tự trong cùng một vòng lặp.
- Dùng queue có capacity cố định.
- Giới hạn số task đang chạy đồng thời.
- Chỉ lấy batch mới khi batch trước đã được ghi xong hoặc có slot trống.
- Dùng reactive pipeline có backpressure nếu toàn bộ chuỗi xử lý hỗ trợ reactive đúng cách.

Không nên dùng một Executor có hàng đợi không giới hạn cho hàng triệu tài liệu. Khi writer chậm, task và object sẽ tích lũy trong heap.

Nếu xử lý song song, hãy xác định rõ quyền sở hữu batch và thứ tự ghi. Cũng cần tính số scroll context đang mở nếu mỗi worker có một phiên scroll riêng. Nhiều worker không phải lúc nào cũng tăng throughput; có thể làm Elasticsearch hoặc hệ thống đích quá tải.

## 18. Giảm dữ liệu trả về bằng source filtering

Nếu export chỉ cần một số trường, hãy yêu cầu Elasticsearch trả đúng các trường đó. Việc này giảm dữ liệu truyền qua mạng và lượng source cần chuyển đổi.

Ví dụ chỉ xuất SKU, tên và giá:

~~~http
POST /products/_search?scroll=90s
{
  "size": 500,
  "_source": [
    "sku",
    "name",
    "price"
  ],
  "sort": [
    "_doc"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Trong Spring Data Elasticsearch, Query abstraction hoặc NativeQuery có thể hỗ trợ source filtering tùy phiên bản. Nếu chuyển kết quả sang DTO, hãy bảo đảm kiểu nhận chỉ yêu cầu các trường thực sự được trả về.

Không nên source-filter rồi ánh xạ vào một entity đầy đủ nếu ứng dụng sẽ hiểu các trường không được trả về là giá trị null thực sự. Có thể dùng projection hoặc DTO riêng để biểu đạt rõ tập dữ liệu được xuất.

## 19. Ước lượng và theo dõi bộ nhớ JVM

Khi chạy export, nên theo dõi:

- Heap used và heap committed.
- Tần suất và thời gian garbage collection.
- Old generation occupancy.
- Số lượng object được tạo khi chuyển đổi.
- Kích thước batch đang xử lý.
- Kích thước queue.
- Số worker và batch đang chạy đồng thời.
- Thời gian ghi dữ liệu đích.
- Số lần retry và batch thất bại.

Nếu heap tăng đều theo thời gian và không giảm sau GC, có thể ứng dụng đang giữ tham chiếu đến dữ liệu cũ. Những nguyên nhân phổ biến:

- Danh sách tổng hợp giữ tất cả Product.
- Cache không có giới hạn.
- Queue không giới hạn.
- Log hoặc metrics giữ source quá lớn.
- Callback hoặc lambda giữ tham chiếu đến object lâu hơn cần thiết.
- Batch được gửi sang executor nhưng không được tiêu thụ kịp.

Sau khi xử lý một batch, hãy bỏ tham chiếu không cần thiết. Không cần gọi **System.gc()** sau mỗi batch; việc này không giải quyết thiết kế giữ tham chiếu và có thể làm hiệu năng xấu đi.

Ở phía Elasticsearch, theo dõi heap node, search context, CPU, disk I/O, search thread pool và các request bị reject. Batch size lớn có thể làm tăng response size và thời gian xử lý trên cả client lẫn server.

## 20. Ghi nhận tiến độ và checkpoint cho export dài

Một export kéo dài có thể bị gián đoạn bởi restart ứng dụng, lỗi mạng hoặc timeout. Nếu phải bắt đầu lại từ đầu, thời gian và tài nguyên có thể tăng đáng kể.

Nên ghi nhận tiến độ theo một đơn vị có thể khôi phục:

- ID tài liệu cuối cùng đã ghi thành công.
- Mốc thời gian hoặc watermark của lần đồng bộ.
- Số tài liệu đã đọc và đã ghi.
- Batch hoặc partition hiện tại.
- Trạng thái job và lỗi gần nhất.

Scroll ID là trạng thái của search context phía Elasticsearch, không nên coi nó như checkpoint bền vững để lưu lâu dài qua restart. Nếu ứng dụng cần resume sau khi process chết, có thể thiết kế lại theo **search_after** với sort key ổn định và checkpoint cursor, hoặc chạy lại từ watermark có cơ chế ghi idempotent.

Khi ghi sang hệ thống đích, dùng ID ổn định hoặc khóa idempotency để retry không tạo bản ghi trùng. Nếu một batch ghi một phần rồi lỗi, cần biết cách xác định những bản ghi đã thành công và phát lại an toàn.

## 21. Ví dụ service export có batch size giới hạn

Ví dụ sau dùng SearchHitsIterator để đọc tuần tự và ghi từng nhóm 100 bản ghi sang destination. Batch đọc được cấu hình riêng qua Pageable.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductExportService {

    private static final IndexCoordinates PRODUCTS =
            IndexCoordinates.of("products");

    private static final int READ_BATCH_SIZE = 500;
    private static final int WRITE_BATCH_SIZE = 100;

    private final ElasticsearchOperations operations;
    private final ProductDestination destination;

    public ProductExportService(
            ElasticsearchOperations operations,
            ProductDestination destination) {
        this.operations = operations;
        this.destination = destination;
    }

    public void exportAll() {
        Query query = NativeQuery.builder()
                .withQuery(q -> q.matchAll(m -> m))
                .withPageable(PageRequest.of(0, READ_BATCH_SIZE))
                .build();

        List<ExportRecord> writeBatch =
                new ArrayList<>(WRITE_BATCH_SIZE);

        try (SearchHitsIterator<Product> hits =
                     operations.searchForStream(
                             query,
                             Product.class,
                             PRODUCTS
                     )) {

            while (hits.hasNext()) {
                SearchHit<Product> hit = hits.next();
                writeBatch.add(toExportRecord(hit.getContent()));

                if (writeBatch.size() == WRITE_BATCH_SIZE) {
                    destination.writeBatch(writeBatch);
                    writeBatch.clear();
                }
            }

            if (!writeBatch.isEmpty()) {
                destination.writeBatch(writeBatch);
            }
        }
    }

    private ExportRecord toExportRecord(Product product) {
        return new ExportRecord(
                product.getId(),
                product.getSku(),
                product.getName(),
                product.getPrice()
        );
    }
}
~~~

Các lớp **ProductDestination** và **ExportRecord** là thành phần minh họa của ứng dụng, không phải API có sẵn của Spring Data.

Điểm chính của ví dụ:

- READ_BATCH_SIZE điều khiển số hit được lấy trong mỗi batch.
- WRITE_BATCH_SIZE điều khiển số record được gom trước khi ghi.
- Iterator được đóng tự động khi vòng lặp kết thúc hoặc phát sinh exception.
- Chỉ giữ một write batch nhỏ trong code ứng dụng.
- Không gom toàn bộ sản phẩm vào List.

Trong môi trường thực tế, cần cấu hình scroll keep-alive phù hợp với phiên bản Spring Data Elasticsearch và tốc độ ghi của destination. Nếu phương thức searchForStream đang dùng overload có SearchScrollSpec, hãy đặt keep-alive rõ ràng theo thời gian xử lý batch đã đo.

## 22. Các dấu hiệu cho thấy batch size hoặc timeout chưa phù hợp

| Dấu hiệu | Nguyên nhân có thể | Hướng điều chỉnh |
|---|---|---|
| Heap tăng mạnh sau mỗi response | Batch quá lớn hoặc entity nặng | Giảm batch size, source filtering |
| GC kéo dài | Quá nhiều object được tạo hoặc giữ cùng lúc | Giảm batch/concurrency, loại queue không giới hạn |
| Nhiều request nhỏ và throughput thấp | Batch quá nhỏ | Tăng size từng bước và đo lại |
| Scroll context hết hạn | Keep-alive ngắn hơn khoảng thời gian giữa hai lần scroll | Tăng keep-alive hoặc giảm thời gian xử lý batch |
| Search request thường timed out | Query ban đầu hoặc shard quá chậm | Tối ưu query, kiểm tra tải và timeout |
| Client timeout nhưng server vẫn xử lý | Client timeout thấp hơn thời gian response | Kiểm tra transport timeout và độ trễ thực tế |
| Số scroll context mở tăng liên tục | Iterator không được đóng hoặc job không clear context | Dùng try-with-resources/finally và kiểm tra cleanup |
| Destination chậm, queue tăng | Reader nhanh hơn writer | Dùng backpressure và queue có giới hạn |
| Export chạy lâu nhưng heap ổn định | Throughput hoặc I/O là nút thắt | Đo thời gian đọc, chuyển đổi và ghi riêng |
| Export thiếu tài liệu sau timeout | Response một phần hoặc job tiếp tục sai cursor | Kiểm tra timed_out/shards và checkpoint |

## 23. Quy trình tinh chỉnh batch size, timeout và bộ nhớ

Một quy trình thực tế có thể thực hiện theo các bước:

1. **Đo kích thước tài liệu.** Lấy một tập đại diện và đo source bytes cùng heap footprint sau chuyển đổi.
2. **Chọn batch ban đầu.** Thử 200 hoặc 500 tài liệu, tùy độ lớn của entity.
3. **Đo thời gian mỗi batch.** Tách thời gian search, network, conversion và ghi destination.
4. **Đặt keep-alive.** Chọn lớn hơn khoảng thời gian dự kiến giữa hai request scroll, có biên an toàn.
5. **Đặt Search API timeout.** Bảo đảm truy vấn có đủ thời gian xử lý nhưng vẫn phát hiện shard quá chậm.
6. **Đặt client timeout.** Đủ dài cho một request batch và phù hợp với transport.
7. **Giới hạn bộ nhớ.** Không giữ toàn bộ kết quả; giới hạn write batch, queue và concurrency.
8. **Đo throughput.** Theo dõi số tài liệu mỗi giây và độ trễ từng batch.
9. **Tăng hoặc giảm batch size.** Thay đổi từng bước; dừng khi throughput không cải thiện hoặc heap/GC tăng.
10. **Kiểm tra cleanup.** Đóng iterator hoặc clear scroll context sau khi hoàn tất và cả khi thất bại.
11. **Kiểm tra tính đầy đủ.** Xác nhận response không timed out, shard không thất bại và số bản ghi đã ghi phù hợp.
12. **Thiết kế resume.** Dùng checkpoint và thao tác ghi idempotent cho job dài.

Nên thử nghiệm trên môi trường có dữ liệu, số shard và tải gần với production. Kết quả đo trên một index nhỏ hoặc chỉ vài nghìn tài liệu có thể không đại diện cho hành vi khi xuất hàng triệu tài liệu.

## 24. Nguyên tắc vận hành cần nhớ

- Chọn batch size theo kích thước tài liệu, heap footprint và tốc độ của hệ thống đích.
- Bắt đầu với một giá trị vừa phải, đo rồi điều chỉnh; không dùng một con số cố định cho mọi index.
- Phân biệt batch size với tổng số hit.
- Phân biệt scroll keep-alive, Search API timeout, client timeout và application deadline.
- Keep-alive phải đủ dài cho khoảng thời gian giữa hai lần lấy batch, không cần bằng tổng thời gian export.
- Dùng SearchHitsIterator hoặc API scroll phù hợp và luôn đóng tài nguyên.
- Không chuyển iterator thành List chứa toàn bộ dữ liệu.
- Tách read batch size và write batch size khi hệ thống đích có yêu cầu khác.
- Giới hạn queue và số batch chạy đồng thời để tránh tích lũy heap.
- Dùng source filtering khi chỉ cần một phần trường.
- Dùng _doc sort cho việc quét toàn bộ dữ liệu khi không cần thứ tự nghiệp vụ.
- Kiểm tra timeout, shard failure và số bản ghi thực tế để tránh export thiếu dữ liệu.
- Dùng checkpoint và ghi idempotent nếu job cần tiếp tục sau lỗi.
- Theo dõi cả tài nguyên JVM lẫn search context và tải của Elasticsearch.

Chọn batch size, timeout và bộ nhớ là một bài toán cân bằng giữa throughput, độ trễ và tài nguyên. Batch lớn có thể giảm số lần round-trip nhưng làm tăng bộ nhớ mỗi response; keep-alive dài giúp ứng dụng có thời gian xử lý batch nhưng giữ search context lâu hơn; timeout của search và client kiểm soát những giai đoạn khác nhau. Khi đọc theo luồng, xử lý có giới hạn, đóng scroll context đúng cách và đo lường trên dữ liệu thực tế, ứng dụng Spring Data Elasticsearch có thể xuất lượng lớn tài liệu ổn định mà không phải giữ toàn bộ dữ liệu trong heap.
