# Quản lý keep_alive, PIT id và đóng tài nguyên

Khi xuất dữ liệu lớn hoặc duyệt qua nhiều trang kết quả trong Elasticsearch, ứng dụng cần giữ được một ngữ cảnh tìm kiếm đủ lâu để tiếp tục lấy dữ liệu. Hai cơ chế thường gặp là Scroll và Point in Time (PIT). Cả hai đều có tham số keep_alive, nhưng mục đích và cách quản lý tài nguyên khác nhau.

Với Scroll, Elasticsearch giữ một scroll context để tiếp tục trả các batch document tiếp theo. Với PIT, Elasticsearch giữ một góc nhìn dữ liệu ổn định trong một khoảng thời gian; ứng dụng thường kết hợp PIT với search_after để phân trang sâu. Trong cả hai trường hợp, keep_alive xác định thời gian ngữ cảnh được giữ kể từ lần sử dụng gần nhất. Ứng dụng phải lưu đúng ID mới nhất do server trả về và chủ động đóng tài nguyên khi công việc hoàn tất.

Nếu quên đóng scroll hoặc PIT, Elasticsearch cuối cùng vẫn có thể giải phóng tài nguyên khi context hết hạn, nhưng trong thời gian chờ các context này tiêu thụ tài nguyên trên cluster. Với job export dài hoặc nhiều request đồng thời, việc quản lý vòng đời rõ ràng là một phần quan trọng của thiết kế.

## 1. Vì sao cần keep_alive?

Một request search thông thường trả về một trang kết quả rồi kết thúc. Khi cần lấy hàng trăm nghìn document, ứng dụng phải gửi nhiều request. Nếu dữ liệu thay đổi giữa các request, cách phân trang thông thường có thể bỏ sót hoặc lặp document.

Scroll và PIT giúp giữ một ngữ cảnh tìm kiếm qua nhiều request:

- **Scroll:** giữ trạng thái cuộn để lấy batch tiếp theo từ một lần tìm kiếm.
- **PIT:** giữ một góc nhìn dữ liệu tại thời điểm mở PIT, sau đó dùng search_after để tiếp tục từ sort values của hit cuối cùng.

keep_alive là khoảng thời gian Elasticsearch giữ context mà không cần request tiếp theo. Nếu ứng dụng tiếp tục gửi request trước khi khoảng thời gian này hết, request có thể gia hạn thời gian sống của context.

Ví dụ, một export mở context với keep_alive một phút. Nếu mỗi batch được lấy trong vòng 10 giây, request tiếp theo có thể tiếp tục gia hạn context. Nếu ứng dụng bị pause lâu hơn một phút, context có thể hết hạn và ID cũ không còn sử dụng được.

keep_alive không phải thời lượng tối đa của toàn bộ export. Một export có thể chạy lâu hơn nhiều phút nếu nó tiếp tục sử dụng context và gia hạn đúng hạn. Tuy nhiên, context vẫn tiêu thụ tài nguyên trong suốt thời gian được giữ.

## 2. Scroll context và PIT khác nhau thế nào?

Hai cơ chế cùng hỗ trợ đọc dữ liệu qua nhiều request nhưng có semantics khác nhau:

| Tiêu chí | Scroll | Point in Time (PIT) |
|---|---|---|
| Mục đích thường gặp | Quét/export tập dữ liệu lớn theo batch | Giữ snapshot cho phân trang sâu hoặc truy vấn liên tiếp |
| Cách lấy trang tiếp | Dùng scroll ID để yêu cầu batch tiếp theo | Dùng PIT ID và search_after |
| Trạng thái phía server | Scroll context duy trì vị trí cuộn | PIT duy trì góc nhìn dữ liệu |
| Thứ tự kết quả | Nên dùng sort phù hợp; thường không dùng cho tương tác người dùng | Cần sort ổn định để dùng search_after |
| Gia hạn | Gửi scroll request với keep_alive mới | Gửi search request với PIT keep_alive mới |
| Kết thúc | Clear scroll | Close PIT |
| Trường hợp phù hợp | Batch export, reindex hoặc xử lý tuần tự | Deep pagination cần snapshot nhất quán |

Scroll thường được dùng cho tác vụ đọc tuần tự, không phải lựa chọn tối ưu cho giao diện phân trang tương tác. Với phân trang sâu, Elasticsearch khuyến nghị dùng PIT kết hợp search_after trong những trường hợp cần kết quả nhất quán khi index thay đổi.

PIT không tự lưu vị trí trang. Nó chỉ giữ góc nhìn dữ liệu. Ứng dụng vẫn phải giữ sort values của hit cuối cùng và gửi chúng trong search_after ở request tiếp theo.

## 3. keep_alive là thời gian nhàn rỗi của context

Một hiểu nhầm phổ biến là đặt keep_alive: 5m đồng nghĩa export chỉ được chạy tối đa năm phút. Thực tế, keep_alive là thời gian context được giữ sau lần request gần nhất.

Ví dụ:

    Mở PIT với keep_alive = 1m
        |
        v
    Search batch 1
        |
        | request tiếp theo sau 20 giây
        v
    Search batch 2, gia hạn 1m
        |
        | request tiếp theo sau 25 giây
        v
    Search batch 3, gia hạn 1m
        |
        | request tiếp theo sau 30 giây
        v
    Search batch 4, gia hạn 1m
        |
        v
    Đóng PIT khi hoàn tất

Miễn là request tiếp theo đến trước khi context hết hạn và server chấp nhận request, ứng dụng có thể tiếp tục công việc lâu hơn giá trị keep_alive ban đầu.

Giá trị keep_alive cần đủ dài cho khoảng thời gian dự kiến giữa hai request liên tiếp, bao gồm:

- Thời gian xử lý batch ở ứng dụng.
- Thời gian mạng và thời gian phản hồi Elasticsearch.
- Thời gian ghi dữ liệu ra file hoặc hệ thống đích.
- Các khoảng pause do scheduling, backpressure hoặc retry.

Không nên đặt keep_alive quá ngắn đến mức context hết hạn trong một lần ghi file chậm. Cũng không nên đặt quá dài nếu job có thể dừng bất ngờ, vì context sẽ tiếp tục chiếm tài nguyên cho đến khi được đóng hoặc hết hạn.

## 4. Mở PIT và nhận PIT ID

PIT được mở trên một index, alias hoặc data stream. Elasticsearch trả về một ID đại diện cho point in time vừa tạo.

REST API:

    POST /products/_pit?keep_alive=1m

Response có dạng:

    {
      "id": "46ToAw..."
    }

Ứng dụng cần lưu ID này để dùng trong các request search tiếp theo và để đóng PIT khi hoàn tất.

Một số điểm cần nhớ:

- PIT ID là giá trị opaque do Elasticsearch cấp; không phân tích hoặc tự sửa chuỗi ID.
- PIT ID không phải ID của một document.
- PIT ID gắn với ngữ cảnh tìm kiếm và thời gian sống của nó.
- ID có thể thay đổi qua các request search; luôn cập nhật ID mới nhất từ response nếu response có trả ID mới.
- Không đưa PIT ID vào log công khai hoặc response API cho người dùng nếu không cần thiết.

PIT mở trên alias có thể giữ góc nhìn của các index mà alias trỏ đến tại thời điểm mở. Nếu alias được chuyển sang index khác sau đó, PIT đang mở vẫn đại diện cho ngữ cảnh đã tạo, không tự chuyển sang một snapshot mới của alias.

## 5. Tìm kiếm bằng PIT và search_after

Sau khi mở PIT, ứng dụng gửi search request có phần pit thay vì chỉ định index trong đường dẫn:

    POST /_search
    {
      "size": 500,
      "pit": {
        "id": "46ToAw...",
        "keep_alive": "1m"
      },
      "sort": [
        { "created_at": "asc" }
      ],
      "query": {
        "match_all": {}
      }
    }

Search response chứa các hit và có thể chứa PIT ID mới. Mỗi hit có mảng sort nếu request đã khai báo sort.

Ví dụ hit cuối:

    {
      "_id": "p-0500",
      "sort": [
        "2026-11-13T10:30:00Z",
        4294967298
      ]
    }

Request tiếp theo sử dụng sort values của hit cuối trong search_after:

    POST /_search
    {
      "size": 500,
      "pit": {
        "id": "46ToAw...",
        "keep_alive": "1m"
      },
      "sort": [
        { "created_at": "asc" }
      ],
      "search_after": [
        "2026-11-13T10:30:00Z",
        4294967298
      ],
      "query": {
        "match_all": {}
      }
    }

Giá trị search_after phải lấy từ hit cuối cùng của batch trước, giữ nguyên thứ tự và kiểu dữ liệu. Không tự tạo timestamp hoặc document ID thay cho sort values mà Elasticsearch trả về.

Khi dùng PIT, Elasticsearch bổ sung một tie-breaker nội bộ _shard_doc cho sort nếu cần để phân trang ổn định trong snapshot. Response hit có thể có thêm giá trị sort tương ứng. Hãy truyền toàn bộ mảng sort values của hit cuối, kể cả giá trị tie-breaker đó, vào request tiếp theo.

Nếu ứng dụng chỉ lưu created_at mà bỏ mất giá trị tie-breaker trong mảng sort, các document có cùng timestamp có thể bị lặp hoặc bỏ qua khi phân trang.

## 6. Luôn dùng PIT ID mới nhất

Một điểm quan trọng khi quản lý PIT là response search có thể trả về PIT ID mới. Tài liệu API khuyến nghị sử dụng ID mới nhất được trả về trong response cho request tiếp theo.

Luồng xử lý:

    pitId = openPointInTime()

    while (còn dữ liệu):
        response = search(pitId, searchAfter)

        if response có pit_id:
            pitId = response.pit_id

        xử lý các hits

        nếu hits rỗng:
            kết thúc

        searchAfter = sort values của hit cuối

    closePointInTime(pitId)

Không nên giữ mãi ID ban đầu nếu response đã cung cấp ID mới. Cũng không nên dùng ID từ response cũ sau khi đã nhận một ID mới hơn.

Nếu ứng dụng có nhiều worker xử lý cùng một PIT, cần điều phối quyền cập nhật PIT ID và cursor. Hai worker không nên độc lập ghi đè trạng thái bằng response đến không đúng thứ tự. Cách đơn giản nhất là một luồng tuần tự sở hữu cursor và PIT ID cho mỗi phiên export.

## 7. Gia hạn PIT bằng keep_alive

PIT được mở với một khoảng keep_alive. Các search request tiếp theo có thể gửi keep_alive mới để gia hạn thời gian context.

Ví dụ:

    POST /_search
    {
      "pit": {
        "id": "46ToAw...",
        "keep_alive": "2m"
      },
      "size": 500,
      "sort": [
        { "created_at": "asc" }
      ],
      "query": {
        "match_all": {}
      }
    }

Ở đây, request yêu cầu giữ PIT thêm hai phút kể từ lần sử dụng này. Nếu batch tiếp theo cần thời gian xử lý dài hơn, ứng dụng có thể gửi keep_alive phù hợp ở request tiếp theo.

Không cần đặt keep_alive bằng tổng thời lượng dự kiến của cả job. Hãy đặt đủ dài cho khoảng nghỉ có thể xảy ra giữa hai lần sử dụng. Nếu export có thể bị pause bởi hệ thống queue trong 10 phút, keep_alive 1 phút sẽ không đủ trừ khi ứng dụng có cơ chế tiếp tục gia hạn context trong thời gian chờ.

### Không gia hạn khi không còn cần dữ liệu

Khi export hoàn tất, hãy đóng PIT ngay. Không tiếp tục gửi request chỉ để giữ context sống nếu ứng dụng không còn cần snapshot.

Nếu một job bị hủy, người dùng bấm cancel hoặc ứng dụng phát hiện dữ liệu đích đã lỗi không thể phục hồi, cần chuyển sang cleanup và đóng PIT. Không chờ keep_alive tự hết hạn như cách kết thúc bình thường.

## 8. PIT hết hạn và xử lý lỗi

Nếu không có request tiếp theo trong thời gian keep_alive, PIT có thể hết hạn. Request dùng ID đã hết hạn sẽ thất bại vì context không còn tồn tại hoặc không còn hợp lệ.

Các nguyên nhân thường gặp:

- Batch trước xử lý quá lâu.
- Job bị pause hoặc worker không được schedule.
- Ghi file hoặc upload dữ liệu đích bị chậm.
- Retry/backoff kéo dài quá keep_alive.
- Ứng dụng bị restart trong khi PIT chưa được lưu trạng thái hoặc không thể tiếp tục.
- PIT đã bị đóng bởi cleanup hoặc tác vụ khác.

Khi PIT hết hạn, không thể giả định rằng mở PIT mới rồi tiếp tục với search_after cũ sẽ giữ nguyên snapshot ban đầu. PIT mới đại diện cho một góc nhìn dữ liệu mới; dữ liệu có thể đã được thêm, sửa hoặc xóa trong khoảng thời gian giữa hai snapshot.

Chiến lược phục hồi nên được quyết định theo yêu cầu:

1. Nếu export có thể chạy lại từ đầu, đóng hoặc bỏ trạng thái cursor cũ và bắt đầu phiên mới.
2. Nếu cần export chính xác một snapshot nhất quán, phải bảo đảm PIT được giữ sống đủ lâu và có cơ chế quản lý job/cursor bền vững.
3. Nếu hệ thống cho phép dữ liệu thay đổi và chấp nhận eventual consistency, có thể mở PIT mới và chạy lại theo checkpoint nghiệp vụ, nhưng cần thiết kế chống trùng và xử lý bản ghi bị bỏ sót.
4. Không lặp vô hạn cùng một request với PIT ID đã hết hạn.

### Retry không đồng nghĩa với gia hạn

Nếu request search thất bại tạm thời do lỗi mạng, retry có thể thành công khi PIT vẫn còn hiệu lực. Nhưng nếu PIT đã hết hạn, retry cùng ID không làm context sống lại.

Khi xử lý lỗi, cần phân biệt:

- Lỗi tạm thời của mạng hoặc cluster: retry có giới hạn và backoff.
- PIT ID không còn hợp lệ hoặc đã hết hạn: cần khởi động lại phiên theo chính sách.
- Lỗi query hoặc mapping: sửa query/dữ liệu, không retry vô hạn.
- Lỗi khi ghi dữ liệu đích: xử lý theo cơ chế export/checkpoint, rồi cleanup PIT khi job bị hủy.

## 9. Đóng PIT tường minh

Khi không cần snapshot nữa, ứng dụng phải gọi Close Point in Time API:

    DELETE /_pit
    {
      "id": "46ToAw..."
    }

Response cho biết PIT có được đóng hay không:

    {
      "succeeded": true,
      "num_freed": 3
    }

num_freed cho biết số shard context được giải phóng trong response. Giá trị này có thể khác số document hoặc số index.

Nên đóng PIT trong các trường hợp:

- Export đã đọc hết dữ liệu.
- Người dùng hủy export.
- Job thất bại và không thể tiếp tục.
- Một request search không thể phục hồi và job kết thúc.
- Ứng dụng không còn sử dụng snapshot.

Đóng PIT giúp giải phóng tài nguyên sớm thay vì chờ keep_alive hết hạn.

Nếu response search cuối cùng đã trả một PIT ID mới, dùng ID mới nhất khi đóng. Nếu API hoặc tình huống lỗi khiến ứng dụng không nhận được ID mới, hãy dùng ID gần nhất mà ứng dụng đang giữ và xử lý trường hợp context đã hết hạn hoặc đã được giải phóng.

## 10. Dùng try/finally để bảo đảm đóng PIT

Đóng tài nguyên nên được đặt trong finally để vẫn chạy khi xử lý batch ném exception:

    String pitId = openPit();

    try {
        String searchAfter = null;

        while (true) {
            SearchResponse<Product> response =
                searchWithPit(pitId, searchAfter);

            if (response.pitId() != null) {
                pitId = response.pitId();
            }

            List<Hit<Product>> hits = response.hits().hits();
            if (hits.isEmpty()) {
                break;
            }

            export(hits);
            searchAfter = extractSortValues(hits.getLast());
        }
    } finally {
        closePit(pitId);
    }

Đây là mã giả mô tả vòng đời; tên kiểu response và accessor cụ thể phụ thuộc phiên bản Elasticsearch Java API Client. Điểm cần giữ là cập nhật biến pitId khi response trả ID mới và đóng ID đang được quản lý trong finally.

Trong code thực tế, nên bảo vệ cả bước mở PIT và đóng PIT:

- Chỉ gọi close khi đã nhận được PIT ID hợp lệ.
- Nếu close thất bại do PIT đã hết hạn, ghi nhận cleanup outcome và kết thúc job theo chính sách.
- Không để exception trong cleanup che mất exception gốc của quá trình export.
- Ghi log đủ thông tin correlation/job ID để điều tra, nhưng tránh ghi PIT ID đầy đủ vào log có phạm vi truy cập rộng.

## 11. Java API Client: mở, tìm kiếm và đóng PIT

Elasticsearch Java API Client cung cấp các API tương ứng với open PIT, search và close PIT. Cú pháp builder cụ thể có thể thay đổi theo phiên bản client được Spring Boot/Spring Data quản lý.

Mở PIT:

    OpenPointInTimeResponse opened =
        client.openPointInTime(request -> request
            .index("products")
            .keepAlive(time -> time.time("1m"))
        );

    String pitId = opened.id();

Tìm kiếm với PIT:

    SearchResponse<Product> response =
        client.search(request -> request
            .pit(pit -> pit
                .id(pitId)
                .keepAlive(time -> time.time("1m"))
            )
            .size(500)
            .sort(sort -> sort
                .field(field -> field
                    .field("created_at")
                    .order(SortOrder.Asc)
                )
            )
            .query(query -> query
                .matchAll(matchAll -> matchAll)
            ),
        Product.class);

Cập nhật PIT ID nếu response có ID mới:

    if (response.pitId() != null) {
        pitId = response.pitId();
    }

Đóng PIT:

    ClosePointInTimeResponse closed =
        client.closePointInTime(request -> request.id(pitId));

Tên response class, kiểu Time, enum sort và accessor có thể khác theo phiên bản. Dùng API tương ứng dependency đang cài đặt; không trộn builder của High Level REST Client cũ với Elasticsearch Java API Client hiện đại.

Nếu dùng Java client trực tiếp trong một service Spring, inject client bean đã được cấu hình thay vì tạo client mới cho mỗi lần export. Client là tài nguyên dùng chung và cần được quản lý bởi Spring/container.

## 12. Quản lý cursor khi dùng search_after

PIT ID và search_after là hai trạng thái khác nhau:

- PIT ID xác định snapshot/context.
- search_after xác định vị trí tiếp tục trong thứ tự sort của snapshot đó.

Một export có thể cần lưu:

    ExportState
      jobId
      pitId
      searchAfterValues
      keepAlive
      processedCount
      status

searchAfterValues nên giữ đúng kiểu dữ liệu và thứ tự của mảng sort. Nếu sort có timestamp, numeric ID và _shard_doc, cursor cần lưu tất cả các giá trị đó.

Không tự tính cursor từ document entity nếu response đã cung cấp sort values. Dữ liệu sort có thể chứa giá trị nội bộ hoặc định dạng được Elasticsearch chuẩn hóa.

### Checkpoint và PIT expiry

Nếu lưu cursor xuống database để tiếp tục sau restart, vẫn phải lưu ý PIT có thể hết hạn trong lúc ứng dụng dừng. Checkpoint cursor không tự giữ snapshot sống.

Khi khởi động lại:

- Nếu PIT còn hiệu lực và ID vẫn dùng được, tiếp tục với PIT ID mới nhất đã lưu cùng search_after.
- Nếu PIT hết hạn, không dùng cursor cũ với PIT mới rồi tuyên bố đây là cùng snapshot.
- Nếu cần export lại toàn bộ, tạo PIT mới và bắt đầu từ đầu.
- Nếu chấp nhận resume theo checkpoint nghiệp vụ, cần cơ chế chống duplicate và xử lý thay đổi dữ liệu.

Một phương án phổ biến cho export có thể chạy lại là ghi dữ liệu đích theo khóa idempotent, lưu checkpoint theo batch và cho phép chạy lại một phần. Đây là chiến lược của ứng dụng, không phải khả năng tự động của PIT.

## 13. Scroll keep_alive và scroll ID

Scroll có vòng đời riêng. Request đầu tiên mở scroll context:

    POST /products/_search?scroll=1m
    {
      "size": 500,
      "sort": [ "_doc" ],
      "query": {
        "match_all": {}
      }
    }

Response trả về _scroll_id và batch đầu tiên.

Request tiếp theo dùng scroll ID:

    POST /_search/scroll
    {
      "scroll": "1m",
      "scroll_id": "DnF1ZXJ5VGhlbkZldGNo..."
    }

Mỗi scroll request có thể trả scroll ID mới. Ứng dụng phải dùng ID mới nhất cho lần tiếp theo, tương tự nguyên tắc cập nhật PIT ID.

scroll trong request tiếp theo chỉ định thời gian giữ context kể từ request đó. Nếu job đang xử lý batch chậm, hãy đặt khoảng đủ dài cho thời gian xử lý và request tiếp theo.

### Đóng scroll context

Khi đọc xong hoặc job bị hủy, gọi Clear Scroll:

    DELETE /_search/scroll
    {
      "scroll_id": [
        "DnF1ZXJ5VGhlbkZldGNo..."
      ]
    }

Clear Scroll giải phóng context sớm. Không nên chỉ dừng vòng lặp sau batch cuối mà bỏ quên cleanup.

Scroll ID cũng là opaque value. Không phân tích hoặc chỉnh sửa chuỗi. Nếu response trả ID mới, cập nhật trạng thái và dùng ID mới nhất.

## 14. Đọc hết Scroll result đúng cách

Một vòng lặp scroll thường tiếp tục cho đến khi batch trả về không còn hit:

    response = initialSearchWithScroll()
    scrollId = response.scrollId

    try:
        while response có hits:
            process(response.hits)
            response = continueScroll(scrollId)
            if response có scroll_id mới:
                scrollId = response.scroll_id
    finally:
        clearScroll(scrollId)

Đây là mã giả. Trong implementation thực tế:

- Xử lý batch hiện tại trước khi yêu cầu batch tiếp theo nếu cần backpressure.
- Cập nhật scroll ID sau mỗi response.
- Dừng khi hits rỗng.
- Đảm bảo clear scroll chạy khi có exception.
- Không giữ toàn bộ dữ liệu trong bộ nhớ nếu mục tiêu là export streaming.

Nếu một batch được ghi vào file hoặc database đích, chỉ đánh dấu batch hoàn tất sau khi ghi thành công. Nếu ghi đích lỗi, quyết định retry batch, restart job hay hủy scroll theo chính sách. Scroll context không thay thế checkpoint bền vững.

## 15. Scroll trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp API stream search có thể dùng để duyệt kết quả theo từng hit và quản lý scroll bên dưới trong các phiên bản hỗ trợ.

Ví dụ khái quát:

    Query query = new NativeQueryBuilder()
        .withQuery(q -> q.matchAll(m -> m))
        .withPageable(PageRequest.of(0, 500))
        .build();

    try (SearchHitsIterator<Product> stream =
             operations.searchForStream(
                 query,
                 Product.class,
                 IndexCoordinates.of("products")
             )) {

        while (stream.hasNext()) {
            SearchHit<Product> hit = stream.next();
            export(hit.getContent());
        }
    }

SearchHitsIterator là một iterator có thể đóng. Dùng try-with-resources để bảo đảm tài nguyên scroll được giải phóng khi đọc hết hoặc khi exception xảy ra.

API scroll time, cách cấu hình keep_alive và kiểu iterator có thể thay đổi giữa các phiên bản Spring Data Elasticsearch. Kiểm tra chữ ký searchForStream và cấu hình query tương ứng của dependency dự án. Không giả định Pageable tự quy định thời gian keep_alive nếu API cụ thể không có cấu hình đó.

Nếu cần kiểm soát chi tiết scroll ID hoặc keep_alive ở từng request, có thể dùng Elasticsearch Java API Client trực tiếp. Trong trường hợp đó, ứng dụng phải chịu trách nhiệm cập nhật ID và clear context.

## 16. Đóng tài nguyên khi ứng dụng có nhiều nhánh kết thúc

Một export có thể kết thúc theo nhiều cách:

- Đọc hết dữ liệu.
- Người dùng hủy.
- Job vượt quá deadline.
- Lỗi khi đọc Elasticsearch.
- Lỗi ghi file hoặc upload đích.
- Process nhận tín hiệu shutdown.

Tất cả các nhánh kết thúc sau khi context đã được mở đều cần cleanup.

Mẫu quản lý:

    String pitId = null;
    Throwable failure = null;

    try {
        pitId = openPit();
        runExport(pitId);
    } catch (Exception ex) {
        failure = ex;
        throw ex;
    } finally {
        if (pitId != null) {
            try {
                closePit(pitId);
            } catch (Exception cleanupError) {
                if (failure != null) {
                    failure.addSuppressed(cleanupError);
                } else {
                    throw cleanupError;
                }
            }
        }
    }

Đây là mẫu minh họa cho việc giữ exception gốc khi cleanup cũng lỗi. Trong ứng dụng thực tế, có thể dùng helper hoặc resource wrapper để tránh lặp lại logic này.

Nếu dùng try-with-resources, có thể đóng gói PIT trong một lớp AutoCloseable:

    try (PitSession session = pitSessionFactory.open(
            IndexCoordinates.of("products"),
            Duration.ofMinutes(1))) {
        exportAll(session);
    }

PitSession là lớp ứng dụng tự xây dựng, giữ PIT ID mới nhất và thực hiện close trong close(). Đây không phải tên class có sẵn của Spring Data; nó minh họa cách gói lifecycle để service không quên cleanup.

## 17. Quản lý PIT trong job bất đồng bộ

Với job export chạy qua queue hoặc scheduler, vòng đời PIT có thể dài hơn một HTTP request. Không nên mở PIT trong controller rồi để một worker khác tự đoán ID hoặc cursor.

Một thiết kế có thể gồm:

    Export API
       |
       v
    Create export job
       |
       v
    Worker opens PIT
       |
       v
    Read batch with search_after
       |
       v
    Write batch to destination
       |
       +----> Persist checkpoint
       |
       v
    More results?
       |
       +---- yes ---> next batch; renew keep_alive
       |
       +---- no ----> close PIT; mark complete

Job state nên có:

- Job ID.
- Trạng thái đang chạy, hoàn tất, thất bại hoặc bị hủy.
- PIT ID mới nhất nếu cần tiếp tục cùng snapshot.
- Sort values của hit cuối cùng.
- Số document đã xử lý.
- Thời điểm heartbeat hoặc lần gia hạn gần nhất.
- Thông tin lỗi và chính sách retry.

Nếu worker mất kết nối hoặc restart, trạng thái job giúp quyết định tiếp tục, chạy lại hay đánh dấu thất bại. Không nên dựa vào biến trong bộ nhớ của một process cho một export có thể kéo dài qua nhiều lần deploy.

## 18. Giới hạn tài nguyên và giám sát

Mỗi PIT hoặc scroll context giữ tài nguyên trên Elasticsearch. Số lượng context đồng thời, thời gian sống và kích thước dữ liệu có thể ảnh hưởng heap, file descriptor, segment và khả năng merge.

Một số nguyên tắc:

- Giới hạn số export chạy đồng thời.
- Dùng batch size vừa phải.
- Chọn keep_alive đủ cho thời gian xử lý giữa hai batch.
- Đóng context ngay khi xong hoặc hủy.
- Tránh mở PIT trước khi worker sẵn sàng sử dụng.
- Tránh giữ context trong lúc chờ user tương tác.
- Theo dõi các chỉ số search context của cluster.

Elasticsearch cung cấp các API stats để quan sát search contexts và hoạt động của node/index. Có thể kiểm tra node stats hoặc index stats tùy mục tiêu vận hành, ví dụ số search context đang mở và các chỉ số liên quan đến search.

Nếu số context mở tăng liên tục và không giảm, hãy kiểm tra:

- Job có clear scroll hoặc close PIT không?
- Exception path có chạy cleanup không?
- Client có lưu ID mới nhất hay đang đóng ID cũ?
- Có job bị treo giữa hai batch không?
- keep_alive có quá dài so với nhu cầu?
- Có nhiều worker mở context nhưng không thực sự xử lý dữ liệu?

Không nên xử lý bằng cách giảm keep_alive xuống quá ngắn nếu nguyên nhân thực sự là ứng dụng quên cleanup. Hãy sửa vòng đời tài nguyên trước.

## 19. Chọn keep_alive và batch size

Keep_alive và batch size có liên quan đến nhau:

- Batch quá nhỏ làm tăng số request và overhead.
- Batch quá lớn làm tăng thời gian xử lý, memory và thời gian giữa các lần request.
- Keep_alive quá ngắn có thể hết hạn trong khi ứng dụng xử lý batch.
- Keep_alive quá dài làm context tồn tại lâu khi job dừng bất thường.

Có thể bắt đầu bằng cách đo:

1. Thời gian lấy batch từ Elasticsearch.
2. Thời gian xử lý mỗi document.
3. Thời gian ghi batch ra đích.
4. Độ trễ mạng và retry dự kiến.
5. Số worker chạy đồng thời.

Ví dụ nếu một batch thường hoàn tất trong 5 đến 10 giây, nhưng đôi khi ghi file mất 30 giây, keep_alive một phút có thể đủ với một khoảng dự phòng. Nếu batch có thể chờ queue vài phút, cần thiết kế heartbeat hoặc gia hạn theo cách phù hợp; chỉ tăng keep_alive lên hàng giờ có thể giữ context không cần thiết quá lâu.

Không có batch size hay keep_alive tối ưu chung cho mọi cluster. Hãy benchmark với kích thước document, số shard và tải search/index thực tế.

## 20. PIT và Scroll khi export có ghi dữ liệu sang hệ thống khác

Export thường có hai phía: đọc từ Elasticsearch và ghi sang file, object storage, database hoặc API bên ngoài. Thời gian ghi đích có thể lâu hơn thời gian lấy batch.

Một vòng lặp an toàn cần cân nhắc:

1. Đọc batch từ Elasticsearch.
2. Ghi batch sang đích.
3. Xác nhận ghi đích thành công.
4. Lưu checkpoint của batch.
5. Lấy batch tiếp theo và gia hạn context.

Nếu lấy batch tiếp theo trước khi ghi xong batch hiện tại, ứng dụng có thể phải giữ nhiều batch trong bộ nhớ và làm tăng khoảng thời gian giữa các lần gia hạn context.

Nếu ghi đích thành công nhưng process dừng trước khi lưu checkpoint, batch có thể được ghi lại khi job chạy lại. Hãy dùng khóa idempotent hoặc cơ chế upsert ở đích nếu cần tránh duplicate.

Nếu checkpoint được lưu trước khi ghi đích thành công, job có thể bỏ qua dữ liệu chưa được ghi. Vì vậy, thứ tự commit batch và checkpoint phải phản ánh yêu cầu nhất quán của export.

PIT bảo đảm snapshot nguồn trong thời gian context còn sống; nó không tạo transaction phân tán giữa Elasticsearch và hệ thống đích.

## 21. Bảo mật và xử lý PIT ID

PIT ID và scroll ID là token opaque dùng để tiếp tục một context. Chúng không nên được xem là dữ liệu nghiệp vụ hoặc đưa ra client không cần thiết.

Các nguyên tắc:

- Chỉ lưu ID trong trạng thái job hoặc bộ nhớ cần thiết.
- Không ghi toàn bộ ID vào log công khai.
- Không cho người dùng tự gửi một PIT ID bất kỳ để truy cập dữ liệu.
- Gắn cursor với job/user/tenant đã được xác thực.
- Kiểm tra quyền truy cập ở mỗi request export theo thiết kế bảo mật của ứng dụng.
- Hạn chế thời gian sống và đóng context khi hoàn tất.

PIT không thay thế authorization. Việc có PIT ID không nên được xem là cơ chế duy nhất để xác định người dùng có quyền xem dữ liệu.

## 22. Các lỗi thường gặp

### Nghĩ keep_alive là thời lượng tối đa của job

keep_alive là thời gian context được giữ sau lần sử dụng gần nhất. Request tiếp theo có thể gia hạn. Job có thể dài hơn keep_alive ban đầu nếu tiếp tục sử dụng context đúng hạn.

### Đặt keep_alive quá ngắn

Nếu xử lý batch hoặc ghi dữ liệu đích lâu hơn thời gian keep_alive, PIT/scroll context có thể hết hạn. Đo thời gian xử lý thực tế và chọn khoảng dự phòng hợp lý.

### Đặt keep_alive quá dài và không cleanup

Context không cần thiết vẫn chiếm tài nguyên. Hãy đóng ngay khi hoàn tất hoặc hủy thay vì chỉ dựa vào expiry.

### Tiếp tục dùng PIT ID cũ

Search response có thể trả PIT ID mới. Luôn cập nhật và dùng ID mới nhất cho request tiếp theo và khi đóng.

### Lưu thiếu search_after values

Phải lưu toàn bộ sort values của hit cuối, kể cả tie-breaker. Không tự tái tạo cursor từ một field duy nhất.

### Mở PIT mới rồi dùng cursor cũ như cùng snapshot

PIT mới có góc nhìn dữ liệu khác. search_after cũ không khôi phục snapshot đã hết hạn; cần restart hoặc dùng chiến lược checkpoint nghiệp vụ có xử lý duplicate/missing.

### Không đóng PIT khi có exception

Đặt close trong finally hoặc dùng resource wrapper có AutoCloseable. Cleanup cần chạy cả khi export bị hủy hoặc ghi đích thất bại.

### Quên clear scroll

Scroll context cần được clear sau khi đọc xong. Dừng vòng lặp không tự đảm bảo context được giải phóng ngay.

### Không cập nhật Scroll ID mới

Scroll response có thể trả ID mới. Dùng ID mới nhất cho batch kế tiếp và clear scroll.

### Dùng Scroll cho phân trang tương tác sâu

Scroll được thiết kế cho việc đọc batch theo context, thường phù hợp với export. Với phân trang sâu cần snapshot nhất quán, PIT + search_after thường phù hợp hơn.

### Cho rằng PIT là checkpoint bền vững

PIT có expiry và tiêu thụ tài nguyên server. Lưu ID/cursor không bảo đảm context còn sống sau restart. Cần thiết kế restart/retry riêng.

## 23. Checklist vòng đời cho một export

Một quy trình export dùng PIT có thể theo các bước:

1. Xác thực người yêu cầu và xác định index/alias được phép export.
2. Kiểm tra giới hạn concurrency và kích thước export.
3. Mở PIT với keep_alive đủ cho khoảng xử lý một batch.
4. Lưu PIT ID mới nhất.
5. Search batch đầu với sort ổn định.
6. Xử lý và ghi batch sang đích.
7. Lưu checkpoint sau khi batch được ghi thành công.
8. Cập nhật PIT ID từ response nếu có.
9. Lưu toàn bộ sort values của hit cuối làm search_after.
10. Gửi request tiếp theo trước khi keep_alive hết và gia hạn nếu cần.
11. Dừng khi không còn hit.
12. Đóng PIT trong finally.
13. Đánh dấu job hoàn tất sau khi cleanup theo chính sách.
14. Nếu lỗi, phân loại lỗi và quyết định retry/restart; không dùng lại PIT đã hết hạn.

Với Scroll, thay bước PIT/search_after bằng việc mở scroll, dùng scroll ID mới nhất để lấy batch tiếp theo và gọi clear scroll trong finally.

## Kết luận

keep_alive xác định thời gian Scroll context hoặc PIT được giữ sau lần sử dụng gần nhất; nó không phải thời lượng tối đa của toàn bộ job. Scroll dùng scroll ID để lấy batch tiếp theo và cần clear scroll khi kết thúc. PIT giữ một góc nhìn dữ liệu và thường kết hợp với search_after; ứng dụng phải lưu sort values đầy đủ, cập nhật PIT ID mới nhất từ response và close PIT khi không còn cần snapshot.

Trong Spring Data Elasticsearch, SearchHitsIterator cần được đóng bằng try-with-resources khi dùng stream/scroll. Với PIT hoặc các thao tác cần kiểm soát ID và keep_alive chi tiết, có thể dùng Elasticsearch Java API Client và đặt cleanup trong finally hoặc một lớp AutoCloseable. Hãy chọn keep_alive đủ cho khoảng xử lý giữa hai batch, giới hạn số context đồng thời, xử lý expiry có chủ đích và không coi PIT ID/cursor là checkpoint bền vững. Quản lý đúng vòng đời giúp export ổn định và tránh giữ tài nguyên Elasticsearch lâu hơn nhu cầu.
