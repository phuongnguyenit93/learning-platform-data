# Thay đổi dữ liệu trong lúc quét và yêu cầu nhất quán

Khi xuất hàng trăm nghìn hoặc hàng triệu document từ Elasticsearch, quá trình quét có thể kéo dài trong lúc ứng dụng khác vẫn tiếp tục thêm, cập nhật hoặc xóa dữ liệu. Nếu mỗi trang được đọc như một search request độc lập, tập kết quả có thể thay đổi giữa các lần gọi: document bị lặp, bị bỏ qua hoặc xuất hiện với phiên bản khác nhau.

Để chọn đúng cách quét, cần xác định trước yêu cầu nhất quán:

- **Snapshot export:** xuất dữ liệu theo trạng thái mà Elasticsearch nhìn thấy tại thời điểm bắt đầu quét. Các thay đổi sau thời điểm đó được xử lý ở đợt đồng bộ khác.
- **Live scan:** chấp nhận dữ liệu thay đổi trong khi đọc; kết quả phản ánh nhiều thời điểm khác nhau và có thể cần xử lý trùng/lệch.
- **Snapshot plus changes:** xuất một snapshot ổn định, đồng thời thu thập các thay đổi phát sinh sau mốc snapshot để đồng bộ tiếp.

Elasticsearch cung cấp Scroll API và Point in Time (PIT) để giữ một góc nhìn ổn định khi đọc nhiều trang. `search_after` giúp phân trang theo cursor nhưng nếu dùng riêng, không tạo snapshot và không bảo đảm kết quả ổn định khi dữ liệu thay đổi.

## 1. Vì sao dữ liệu thay đổi làm phân trang bị lệch?

Giả sử ứng dụng xuất các đơn hàng, sắp xếp theo `created_at` tăng dần và đọc 100 document mỗi lần. Ở lần đầu, danh sách có thứ tự:

```text
Trang 1: A, B, C, D, E, ...
Trang 2: F, G, H, I, J, ...
```

Sau khi đọc trang đầu, một document mới được thêm vào trước vị trí của F. Nếu request trang hai dùng `from = 100`, mọi vị trí sau document mới bị dịch một chỗ. Kết quả có thể chứa document cuối trang một lần nữa hoặc bỏ qua document vốn nằm ở đầu trang hai.

Một số tình huống khác:

- **Insert:** document mới được thêm trước cursor/offset làm dịch vị trí các document cũ.
- **Delete:** document bị xóa làm các vị trí phía sau dịch lên.
- **Update field sort:** document có thể chuyển từ phía sau cursor lên phía trước hoặc ngược lại.
- **Update field query:** document có thể bắt đầu khớp hoặc không còn khớp query giữa hai trang.
- **Refresh:** thay đổi đã ghi chỉ trở nên searchable sau refresh; hai request có thể nhìn thấy các searcher khác nhau.

Vấn đề không chỉ nằm ở `from/size`. Bất kỳ cách phân trang nào thực hiện nhiều search request độc lập đều cần một chiến lược xử lý thay đổi dữ liệu.

## 2. Refresh và thời điểm dữ liệu có thể được tìm kiếm

Elasticsearch là hệ thống near real-time. Một thao tác index/update/delete thành công chưa có nghĩa document lập tức xuất hiện hoặc biến mất trong kết quả search. Thay đổi cần được refresh để trở nên searchable.

Ví dụ:

1. Ứng dụng ghi document `order-101`.
2. Elasticsearch xác nhận thao tác ghi.
3. Trước khi refresh, một search mới có thể chưa thấy document đó.
4. Sau refresh, search có thể tìm thấy document.

Khi mở Scroll hoặc PIT, góc nhìn tìm kiếm được tạo dựa trên trạng thái đã searchable tại thời điểm mở context. Vì vậy, cần xác định rõ mốc export là sau lần ghi nào và sau refresh nào.

Nếu quy trình cần chắc chắn các ghi trước đó đã searchable trước khi bắt đầu quét, có thể:

- Dùng `refresh=wait_for` trên thao tác ghi phù hợp trước khi mở snapshot.
- Chủ động refresh index trong bước chuẩn bị export nếu quy trình vận hành cho phép.
- Chốt watermark/sequence của nguồn ghi rồi xác nhận dữ liệu đã được refresh trước khi mở PIT hoặc Scroll.

Refresh chỉ giúp các thay đổi trước đó hiển thị cho search. Nó không khóa index và không ngăn các ghi mới sau thời điểm refresh.

## 3. Scroll giữ góc nhìn tìm kiếm tại thời điểm bắt đầu

Scroll API tạo search context và giữ trạng thái tìm kiếm để ứng dụng đọc các batch tiếp theo. Các request scroll sau đó tiếp tục đọc từ cùng góc nhìn ban đầu, thay vì chạy lại một search mới trên trạng thái index mới nhất.

Với một scroll context còn hiệu lực:

- Document được thêm sau khi mở scroll không xuất hiện trong lượt quét đó.
- Document được cập nhật sau khi mở scroll vẫn được nhìn theo phiên bản thuộc góc nhìn ban đầu.
- Document bị xóa sau khi mở scroll vẫn có thể được trả về từ góc nhìn ban đầu.
- Những thay đổi này không làm danh sách các batch đang quét tự dịch chuyển như offset pagination thông thường.

Đây là đặc tính hữu ích cho export nhất quán: tất cả batch thuộc cùng một lượt quét dựa trên cùng một search context. Tuy nhiên, đây là snapshot phục vụ search, không phải transaction ACID trên toàn bộ cluster hoặc bảo đảm rằng nhiều index được cập nhật nguyên tử cùng một thời điểm.

### 3.1. Mở scroll

Ví dụ đọc 500 document mỗi batch:

```http
POST /orders/_search?scroll=1m
Content-Type: application/json

{
  "size": 500,
  "sort": ["_doc"],
  "track_total_hits": false,
  "query": {
    "match_all": {}
  }
}
```

Các điểm cần chú ý:

- `scroll=1m` yêu cầu Elasticsearch giữ search context ít nhất đủ lâu để client lấy batch tiếp theo. Mỗi request scroll tiếp theo có thể gia hạn thời gian này.
- `size` là số document tối đa trong mỗi batch.
- Sort theo `_doc` thường phù hợp cho việc duyệt toàn bộ dữ liệu nhanh khi không cần thứ tự nghiệp vụ.
- `track_total_hits: false` tránh tính tổng số chính xác nếu export không cần tổng count.

Response ban đầu chứa `_scroll_id` và batch đầu tiên trong `hits.hits`.

### 3.2. Đọc batch tiếp theo

Gửi scroll ID nhận được ở response trước:

```http
POST /_search/scroll
Content-Type: application/json

{
  "scroll": "1m",
  "scroll_id": "DXF1ZXJ5QW5kRmV0Y2gBAAAAA..."
}
```

Response trả batch tiếp theo và có thể trả `_scroll_id` mới. Client phải luôn dùng scroll ID mới nhất được trả về, không giả định ID đầu tiên luôn hợp lệ cho toàn bộ quá trình.

Tiếp tục cho đến khi batch trả về rỗng. Sau đó xóa search context.

### 3.3. Đóng scroll context

```http
DELETE /_search/scroll
Content-Type: application/json

{
  "scroll_id": [
    "DXF1ZXJ5QW5kRmV0Y2gBAAAAA..."
  ]
}
```

Đóng context ngay khi hoàn tất hoặc khi export bị hủy. Không nên để scroll context tồn tại chỉ vì ứng dụng quên giải phóng. Search context giữ các tài nguyên và segment cũ cần thiết cho góc nhìn ban đầu; nhiều context kéo dài có thể làm tăng áp lực bộ nhớ, file handle và dung lượng đĩa cần giữ lại.

### 3.4. `keep_alive` không phải thời gian tối đa của toàn bộ export

Giá trị `scroll`/`keep_alive` biểu thị khoảng thời gian context được giữ kể từ lần truy cập gần nhất. Mỗi lần lấy batch tiếp theo có thể gia hạn context. Vì vậy, một export kéo dài 30 phút vẫn có thể dùng `keep_alive` ngắn hơn 30 phút nếu client liên tục lấy batch trước khi context hết hạn.

Không đặt keep-alive quá dài nếu không cần thiết. Chọn khoảng thời gian đủ cho thời gian xử lý và mạng giữa hai batch, có tính đến độ trễ tạm thời. Nếu client dừng quá lâu, context có thể hết hạn và lượt quét không thể tiếp tục bằng scroll ID cũ.

## 4. Point in Time (PIT) giữ snapshot cho nhiều search request

Point in Time tạo một góc nhìn ổn định của index tại thời điểm mở PIT. PIT thường được kết hợp với `search_after` để duyệt nhiều trang mà không phải giữ một chuỗi scroll batch.

PIT phù hợp khi:

- Cần duyệt sâu với sort có ý nghĩa nghiệp vụ.
- Muốn giữ kết quả ổn định trong lúc index tiếp tục nhận thay đổi.
- Cần cursor pagination thay cho `from/size`.
- Muốn lấy các batch theo sort values của hit cuối trang trước.

Mở PIT:

```http
POST /orders/_pit?keep_alive=2m
```

Response trả một PIT ID. Dùng ID này trong Search API:

```http
POST /_search
Content-Type: application/json

{
  "size": 500,
  "pit": {
    "id": "46ToAwMDaWR4BXV...",
    "keep_alive": "2m"
  },
  "track_total_hits": false,
  "sort": [
    { "created_at": "asc" },
    { "_shard_doc": "asc" }
  ],
  "query": {
    "match_all": {}
  }
}
```

PIT ID được truyền trong mỗi request tiếp theo. Elasticsearch có thể trả PIT ID mới; client nên dùng ID mới nhất trong response. `keep_alive` được gia hạn khi tiếp tục gửi request với PIT.

### 4.1. Dùng `search_after`

Sau khi nhận batch đầu tiên, lấy mảng `sort` của hit cuối cùng. Gửi mảng đó trong request kế tiếp:

```json
{
  "size": 500,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "2m"
  },
  "track_total_hits": false,
  "sort": [
    { "created_at": "asc" },
    { "_shard_doc": "asc" }
  ],
  "search_after": [
    "2026-11-13T10:15:00Z",
    4294967298
  ],
  "query": {
    "match_all": {}
  }
}
```

Các giá trị trong `search_after` phải lấy nguyên vẹn từ mảng `sort` của hit cuối batch trước, đúng thứ tự và kiểu dữ liệu. Không tự tính lại từ field trong `_source` nếu response đã cung cấp sort values.

Lặp lại cho đến khi batch rỗng. Cuối cùng đóng PIT:

```http
DELETE /_pit
Content-Type: application/json

{
  "id": "LATEST_PIT_ID"
}
```

### 4.2. Sort phải có thứ tự xác định

Nếu sort chỉ dùng `created_at`, nhiều document có thể cùng timestamp. Khi cần tiếp tục từ `search_after`, phải có tie-breaker để thứ tự giữa các document bằng nhau được xác định.

Với PIT, `_shard_doc` là tie-breaker hiệu quả cho thứ tự duyệt trong snapshot. Có thể khai báo tường minh như ví dụ trên. Nếu không dùng PIT, hãy dùng một field sort ổn định, duy nhất trong phạm vi truy vấn, chẳng hạn `event_id` kiểu `keyword`; không mặc định `_id` là field có thể sort thông thường.

## 5. `search_after` không có PIT không tạo snapshot

`search_after` cho phép gửi sort values của hit cuối trang trước để tiếp tục tìm document sau cursor. Tuy nhiên, nếu mỗi request không dùng PIT, Elasticsearch thực hiện search trên trạng thái hiện tại mà request đó nhìn thấy.

Ví dụ:

1. Request đầu trả document có `created_at` từ 10:00 đến 10:05.
2. Ứng dụng lưu sort values của document cuối là 10:05.
3. Một document mới có `created_at = 10:03` được ghi và refresh.
4. Request tiếp theo dùng `search_after` tại 10:05 nên document mới nằm trước cursor và không được trả trong lượt duyệt.

Một document khác có sort value mới hơn cursor có thể xuất hiện ở trang sau dù nó chưa tồn tại khi trang đầu được đọc. Nếu document đã đọc bị cập nhật field sort để chuyển sang sau cursor, nó có thể xuất hiện lần nữa. Nếu document chưa đọc chuyển lên trước cursor, nó có thể bị bỏ qua.

Tie-breaker duy nhất giúp phân định thứ tự khi giá trị sort bằng nhau, nhưng không biến nhiều search request thành một snapshot. Khi cần tính nhất quán qua toàn bộ lượt quét, hãy kết hợp `search_after` với PIT.

## 6. Điều gì xảy ra với insert, update và delete trong lúc quét?

Bảng dưới đây mô tả hành vi ở mức search snapshot:

| Thay đổi sau khi mở Scroll/PIT | Lượt quét đang dùng snapshot | Lượt search mới không dùng snapshot |
|---|---|---|
| Thêm document mới | Không thấy document mới trong snapshot hiện tại. | Có thể thấy sau khi thay đổi được refresh. |
| Cập nhật document | Có thể thấy phiên bản cũ thuộc snapshot; không thấy phiên bản mới trong snapshot hiện tại. | Có thể thấy phiên bản mới sau refresh. |
| Xóa document | Document thuộc snapshot ban đầu vẫn có thể được trả về. | Không còn thấy document sau khi delete được refresh. |
| Cập nhật field dùng để sort | Vị trí trong snapshot không đổi theo bản cập nhật mới. | Document có thể chuyển vị trí giữa các request. |
| Cập nhật field dùng trong query | Tình trạng khớp của snapshot giữ theo dữ liệu ban đầu. | Document có thể bắt đầu khớp hoặc không còn khớp sau refresh. |

Điều này rất hữu ích cho một bản export nhất quán theo snapshot, nhưng cần hiểu hệ quả nghiệp vụ: document bị xóa trong lúc export vẫn có thể xuất hiện trong file export, và document được tạo trong lúc export sẽ không có trong file đó.

Nếu mục tiêu là “xuất tất cả dữ liệu tồn tại tại thời điểm bắt đầu”, hành vi này thường đúng. Nếu mục tiêu là “xuất mọi thay đổi phát sinh cho đến khi job kết thúc”, snapshot đơn lẻ chưa đủ.

## 7. Snapshot search không phải transaction trên toàn cluster

Scroll context và PIT giữ search view để nhiều request đọc nhất quán trên các shard tham gia. Chúng không tạo transaction database với khóa ghi và rollback cho toàn bộ cluster.

Một số giới hạn cần nhớ:

- Elasticsearch vẫn nhận write trong lúc quét; write mới không bị khóa bởi PIT hoặc Scroll.
- Search view dựa trên dữ liệu đã searchable tại thời điểm context được mở.
- Một lần cập nhật liên quan nhiều index không trở thành một giao dịch nguyên tử chỉ vì client mở PIT trên alias hoặc nhiều index.
- Nếu có nhiều nguồn ghi độc lập, cần xác định mốc dữ liệu và cơ chế đồng bộ ở tầng nghiệp vụ.
- Snapshot search không thay thế backup. Để backup/restore index, dùng Elasticsearch Snapshot and Restore API với snapshot repository phù hợp.

Vì vậy, hãy mô tả chính xác yêu cầu nhất quán: snapshot search cung cấp góc nhìn đọc ổn định cho lượt quét, không phải cam kết transaction xuyên suốt mọi hoạt động ghi của hệ thống.

## 8. Chọn Scroll hay PIT kết hợp `search_after`?

| Tiêu chí | Scroll | PIT + `search_after` |
|---|---|---|
| Mục tiêu điển hình | Export/batch scan lớn. | Phân trang sâu, cursor hoặc export cần sort xác định. |
| Cách lấy batch tiếp | Scroll ID và request tiếp theo. | Sort values của hit cuối và `search_after`. |
| Snapshot | Giữ search context từ request đầu. | PIT giữ góc nhìn ổn định giữa các search request. |
| Sort | `_doc` thường phù hợp khi chỉ cần duyệt nhanh. | Có thể sort theo field nghiệp vụ; PIT hỗ trợ tie-breaker `_shard_doc`. |
| Trạng thái phía server | Giữ scroll context. | Giữ PIT context; client quản lý PIT ID và cursor. |
| Dùng cho UI pagination | Không phải lựa chọn mặc định. | Phù hợp hơn cho cursor pagination. |
| Kết thúc | Clear scroll context. | Close PIT. |

Chọn Scroll cho export đơn giản theo batch, đặc biệt khi không cần thứ tự nghiệp vụ. Chọn PIT kết hợp `search_after` khi cần cursor ổn định, sort theo field và kiểm soát rõ vị trí tiếp tục.

Không dùng `from/size` cho export rất lớn chỉ vì API đơn giản. Offset pagination phải bỏ qua các kết quả trước offset, có giới hạn `index.max_result_window` và có thể bị lệch khi dữ liệu thay đổi giữa request.

## 9. Quét dữ liệu bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `ElasticsearchOperations.searchForStream(...)` để duyệt kết quả theo kiểu iterator. API này dùng cơ chế scroll phía dưới và trả `SearchHitsIterator`, giúp ứng dụng xử lý từng hit mà không cần tải toàn bộ kết quả vào bộ nhớ.

Ví dụ:

```java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import java.util.function.Consumer;

@Service
public class OrderExportService {

    private final ElasticsearchOperations operations;

    public OrderExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportActiveOrders(Consumer<OrderDocument> writer) {
        Query query = buildActiveOrdersQuery();

        try (SearchHitsIterator<OrderDocument> hits =
                     operations.searchForStream(query, OrderDocument.class)) {
            while (hits.hasNext()) {
                SearchHit<OrderDocument> hit = hits.next();
                writer.accept(hit.getContent());
            }
        }
    }

    private Query buildActiveOrdersQuery() {
        Criteria criteria = new Criteria("status").is("ACTIVE");
        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(PageRequest.of(0, 500));
        return query;
    }
}
```

Ví dụ dùng `Consumer` làm sink minh họa, lọc các đơn hàng `ACTIVE` và đặt batch size 500 qua `Pageable`. Trong code thực tế, thay consumer bằng writer ghi file/object storage hoặc batch sink phù hợp. `SearchHitsIterator` phải được đóng để giải phóng scroll context; try-with-resources bảo đảm close được gọi cả khi writer ném exception. Cấu hình scroll keep-alive và overload của `searchForStream` cần đối chiếu với phiên bản Spring Data Elasticsearch của dự án.

### 9.1. Không giữ toàn bộ kết quả trong một List

Không nên chuyển iterator thành một danh sách lớn nếu mục tiêu là export dữ liệu lớn:

```java
List<OrderDocument> all = StreamSupport
        .stream(hits.spliterator(), false)
        .map(SearchHit::getContent)
        .toList();
```

Đoạn code này có thể giữ toàn bộ document trong heap và làm mất lợi ích xử lý theo batch. Thay vào đó, ghi từng document vào file, object storage, message queue hoặc sink theo từng batch nhỏ.

### 9.2. Ghi theo batch và xử lý lỗi

Khi ghi dữ liệu ra sink, nên gom một số document thành batch để giảm overhead I/O, nhưng giới hạn kích thước theo bộ nhớ. Nếu sink thất bại, cần quyết định dừng toàn bộ export hay retry batch.

Nếu retry ghi ra sink, dùng document ID ổn định làm idempotency key để ghi lại cùng record không tạo bản sao. Scroll/PIT bảo đảm góc nhìn đọc ổn định; chúng không tự bảo đảm sink nhận dữ liệu đúng một lần.

### 9.3. Phiên bản Spring Data và API scroll mức thấp

Các phiên bản Spring Data Elasticsearch có thể cung cấp các API scroll mức thấp như bắt đầu scroll, tiếp tục theo scroll ID và xóa context. Tên method và overload có thể khác theo phiên bản. Khi dùng trực tiếp, cần:

1. Lưu scroll ID mới nhất từ response.
2. Truyền keep-alive phù hợp cho mỗi lần tiếp tục.
3. Dừng khi batch rỗng.
4. Gọi clear scroll trong `finally` hoặc cơ chế cleanup tương đương.

Với code ứng dụng thông thường, `searchForStream` cùng try-with-resources thường đơn giản hơn việc tự quản lý scroll ID.

## 10. Xử lý thay đổi phát sinh trong lúc export

Scroll/PIT cho snapshot ổn định, nhưng không tự đưa các thay đổi phát sinh sau snapshot vào file export. Nếu nghiệp vụ cần dữ liệu mới nhất đến thời điểm job kết thúc, phải bổ sung một luồng thay đổi.

### 10.1. Snapshot rồi đồng bộ delta

Một mô hình thường dùng:

```text
Chốt watermark W
       |
       v
Mở PIT / Scroll snapshot
       |
       v
Export toàn bộ document thuộc snapshot
       |
       v
Đọc change log từ W đến thời điểm đồng bộ
       |
       v
Apply insert/update/delete theo thứ tự
       |
       v
Đối soát và chốt export
```

Watermark có thể là offset của change log, CDC position hoặc một mốc nghiệp vụ có thể tái lập. Điều quan trọng là phải có quan hệ rõ ràng giữa thời điểm chụp snapshot và vị trí bắt đầu đọc delta; nếu không, có thể bỏ sót thay đổi xảy ra ở ranh giới.

Một thiết kế thực tế thường ghi nhận vị trí change stream trước khi bắt đầu snapshot, export snapshot, rồi replay các sự kiện từ vị trí đó. Vì snapshot có thể chứa một phần các thay đổi đã xảy ra sau watermark, sink cần xử lý upsert/delete theo version hoặc thứ tự sự kiện để không ghi đè dữ liệu mới bằng trạng thái cũ. Cách làm cụ thể phụ thuộc khả năng CDC của hệ thống nguồn.

### 10.2. Dùng `updated_at` làm watermark

Nếu hệ thống không có CDC, có thể quét delta bằng field `updated_at`:

```json
GET /orders/_search
{
  "query": {
    "range": {
      "updated_at": {
        "gte": "2026-11-13T10:00:00Z",
        "lt": "2026-11-13T11:00:00Z"
      }
    }
  }
}
```

Tuy nhiên, `updated_at` chỉ đáng tin nếu được cập nhật nhất quán và có độ chính xác phù hợp. Cần tính đến:

- Đồng hồ giữa các service có thể lệch.
- Hai cập nhật có thể cùng timestamp.
- Một thay đổi có thể được refresh trễ nên chỉ xuất hiện sau lần quét delta.
- Một document bị xóa không còn xuất hiện trong search thông thường để delta biết rằng phải xóa ở đích.
- Một document có thể được cập nhật nhiều lần trong khoảng quét.

Để giảm rủi ro, có thể dùng overlap window: lần quét tiếp theo bắt đầu sớm hơn watermark đã lưu một khoảng thời gian, sau đó upsert theo ID ổn định để việc đọc lặp không tạo bản sao. Với delete, cần tombstone hoặc change log riêng. Nếu yêu cầu không được mất thay đổi, CDC/outbox thường đáng tin cậy hơn việc chỉ dựa vào timestamp.

### 10.3. Dùng index bất biến hoặc partition theo thời gian

Nếu dữ liệu có tính append-only, có thể thiết kế index theo ngày/tuần hoặc theo batch. Export các partition đã đóng/không còn nhận ghi sẽ đơn giản hơn vì tập dữ liệu ít thay đổi.

Ví dụ:

```text
events-2026-11-10  (đã đóng, chỉ đọc)
events-2026-11-11  (đã đóng, chỉ đọc)
events-2026-11-12  (đang nhận ghi)
```

Có thể export các index đã đóng bằng snapshot search, trong khi index hiện tại được xử lý bằng một delta riêng. Cần bảo đảm ứng dụng ghi không quay lại index cũ sau khi partition đã được coi là hoàn tất.

## 11. Tính nhất quán của file export và sink

Một lượt đọc nhất quán không tự làm cho file export nhất quán. Ví dụ job đã đọc 50 batch nhưng ghi file bị lỗi ở batch 51. Khi chạy lại, nếu job tạo file mới nhưng giữ một phần output cũ, file có thể chứa document trùng.

Nên thiết kế sink với một trong các cách:

- Ghi vào file tạm và chỉ đổi tên/publish khi export hoàn tất.
- Ghi mỗi batch vào object riêng có số thứ tự/checksum rồi tạo manifest khi hoàn tất.
- Upsert vào đích theo ID ổn định để retry không tạo bản ghi trùng.
- Lưu checkpoint theo batch và đảm bảo checkpoint chỉ được commit sau khi sink đã ghi bền vững.
- Ghi tombstone cho document bị xóa nếu cần đồng bộ trạng thái delete.

Nếu export phải tiếp tục sau khi process chết, cần hiểu scroll/PIT context có thể hết hạn hoặc mất khi cluster thay đổi. Không coi scroll ID hoặc PIT ID là checkpoint bền vững lâu dài. Với job có thể chạy lại nhiều giờ hoặc cần resume qua sự cố, hãy thiết kế snapshot version, change log và sink idempotent để có thể khởi động lại một lượt quét mới.

### 11.1. At-least-once và exactly-once

Scroll/PIT điều khiển dữ liệu mà reader nhìn thấy; chúng không cung cấp exactly-once delivery giữa Elasticsearch và hệ thống đích.

- **At-most-once:** có thể mất record nếu checkpoint được ghi trước khi sink xác nhận thành công.
- **At-least-once:** retry batch có thể ghi cùng record nhiều lần; sink phải idempotent.
- **Exactly-once effect:** thường cần ID ổn định, upsert/version check, transaction hoặc cơ chế dedup ở sink. Không thể chỉ dựa vào scroll ID để có bảo đảm này.

Thứ tự an toàn thường là ghi batch thành công trước, sau đó mới cập nhật checkpoint. Nếu process chết giữa hai bước, batch có thể được gửi lại; sink idempotent sẽ xử lý lần gửi lặp.

## 12. Mốc dữ liệu và yêu cầu nhất quán theo từng tình huống

| Nhu cầu | Cách tiếp cận | Giới hạn cần hiểu |
|---|---|---|
| Xuất dữ liệu theo trạng thái tại lúc bắt đầu | Scroll hoặc PIT + `search_after`. | Không chứa insert/update sau mốc snapshot. |
| Duyệt hàng triệu document theo batch, không cần sort nghiệp vụ | Scroll, sort `_doc`. | Cần giữ và đóng scroll context. |
| Duyệt sâu có sort ổn định | PIT + `search_after`. | PIT có thời hạn; dùng PIT ID mới nhất. |
| Chỉ cần quét gần nhất và chấp nhận thay đổi giữa các trang | `search_after` không PIT hoặc offset pagination. | Có thể lặp/bỏ sót khi dữ liệu hoặc sort values thay đổi. |
| Export cần bao gồm cả thay đổi trong lúc job chạy | Snapshot + CDC/change log hoặc delta pass. | Phải xử lý watermark và thứ tự cập nhật. |
| Dữ liệu append-only, partition cũ không còn ghi | Export partition đã đóng. | Phải bảo đảm không có write quay lại partition cũ. |
| Backup/restore toàn index | Snapshot and Restore API. | Không thay thế bằng cách quét document qua Scroll. |
| Job phải resume sau thời gian dài hoặc node restart | Snapshot version + durable change log + idempotent sink. | Scroll/PIT context không phải checkpoint lâu dài. |

## 13. Kiểm thử thay đổi dữ liệu trong lúc quét

Nên có integration test xác minh rõ semantics snapshot và live search. Dùng Elasticsearch thật hoặc Testcontainers với phiên bản tương thích; mock repository không thể kiểm chứng search context và refresh behavior.

### 13.1. Kiểm thử Scroll snapshot

Một kịch bản kiểm thử:

1. Index các document A, B, C và refresh.
2. Mở scroll với batch size 1 hoặc 2.
3. Đọc batch đầu.
4. Thêm document D và refresh.
5. Cập nhật B và refresh.
6. Xóa C và refresh.
7. Tiếp tục đọc các batch của scroll.
8. Xác nhận lượt quét vẫn phản ánh trạng thái thuộc snapshot ban đầu theo search context.
9. Chạy search mới không dùng scroll để xác nhận trạng thái mới đã searchable.
10. Clear scroll context.

### 13.2. Kiểm thử PIT + `search_after`

Lặp lại kịch bản trên với PIT:

1. Index dữ liệu ban đầu và refresh.
2. Mở PIT.
3. Lấy trang đầu và lưu sort values của hit cuối.
4. Thực hiện insert/update/delete rồi refresh.
5. Gửi request tiếp theo với PIT ID mới nhất và `search_after`.
6. Xác nhận các trang vẫn dựa trên snapshot đã mở.
7. Đóng PIT.

### 13.3. Kiểm thử `search_after` không PIT

Chạy cùng kịch bản nhưng không mở PIT. Thêm document có sort value nằm trước cursor, thay đổi sort value của document chưa đọc và xóa một document. Xác nhận kết quả có thể thay đổi giữa các request; test nên thể hiện đây là chế độ không snapshot, không đóng đinh một thứ tự cụ thể phụ thuộc timing.

### 13.4. Kiểm thử lỗi khi export

Giả lập sink lỗi giữa hai batch:

- Kiểm tra context được đóng khi job dừng.
- Kiểm tra checkpoint chỉ được lưu sau khi batch ghi thành công.
- Chạy lại batch và xác nhận sink idempotent không tạo bản sao.
- Kiểm tra file tạm không bị công bố như file hoàn chỉnh.

Không dùng `Thread.sleep` để chờ refresh trong test. Dùng refresh API hoặc cấu hình test phù hợp để xác định rõ khi nào document searchable.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Export bị thiếu document khi đang có insert | Quét bằng nhiều search request độc lập, document mới nằm trước cursor/offset. | Dùng Scroll/PIT cho snapshot hoặc chạy delta riêng. |
| Một document xuất hiện hai lần | Offset bị dịch, sort value thay đổi hoặc sink retry không idempotent. | Dùng snapshot, sort ổn định và dedup/upsert theo ID. |
| Document đã xóa vẫn xuất hiện trong file export | Scroll/PIT giữ phiên bản thuộc snapshot ban đầu. | Xử lý delete bằng delta/tombstone sau snapshot nếu cần trạng thái mới nhất. |
| Document cập nhật không có giá trị mới trong file | Snapshot được mở trước khi update/refresh. | Chạy delta sau snapshot hoặc chốt thời điểm export phù hợp. |
| `search_after` bỏ sót document | Sort value thay đổi hoặc document mới được thêm trước cursor. | Kết hợp PIT và sort ổn định. |
| Scroll request hết hạn | Client dừng quá lâu hoặc keep-alive quá ngắn. | Gia hạn context đúng nhịp, giảm thời gian xử lý batch hoặc mở lại lượt export. |
| Cluster giữ nhiều segment cũ | Scroll/PIT context mở quá lâu hoặc bị quên đóng. | Đóng context sớm, giới hạn số export đồng thời và keep-alive hợp lý. |
| Export không thể resume sau restart | Scroll/PIT ID đã hết hạn hoặc không còn context. | Thiết kế restartable export với snapshot mới, watermark/change log và sink idempotent. |
| Count/export không khớp | Snapshot và count được thực hiện ở các thời điểm khác nhau. | Tính count trong cùng snapshot hoặc chấp nhận/ghi rõ mốc dữ liệu khác nhau. |
| Tưởng PIT khóa các ghi mới | Nhầm snapshot search với transaction/lock. | Ghi tiếp vẫn được phép; PIT chỉ giữ góc nhìn đọc. |

## 15. Quy trình chọn và vận hành một lượt export

1. **Xác định mốc dữ liệu:** export theo trạng thái lúc bắt đầu, theo thời điểm cutoff hay cần bao gồm thay đổi đến khi hoàn tất.
2. **Chọn cơ chế:** Scroll cho batch scan đơn giản; PIT + `search_after` cho cursor/sort ổn định; CDC/delta nếu phải bao gồm thay đổi phát sinh.
3. **Chuẩn bị dữ liệu:** xác nhận các write cần thiết đã refresh trước khi mở context.
4. **Chọn batch size:** đủ lớn để giảm overhead nhưng không làm tăng heap hoặc thời gian xử lý mỗi batch quá mức.
5. **Chọn sort:** `_doc` cho scroll export không cần thứ tự; field sort có tie-breaker khi cần thứ tự xác định.
6. **Quản lý context:** dùng keep-alive phù hợp, giới hạn export đồng thời và luôn đóng Scroll/PIT.
7. **Ghi sink an toàn:** ghi theo batch, ID ổn định, retry idempotent và checkpoint sau khi ghi bền vững.
8. **Đồng bộ delta:** nếu cần trạng thái mới nhất, replay CDC/change log hoặc quét delta có watermark sau snapshot.
9. **Đối soát:** so sánh số lượng theo cùng mốc dữ liệu, kiểm tra lỗi batch và xác nhận manifest/export hoàn tất.
10. **Dọn dẹp:** đóng context, giải phóng file tạm và ghi nhận metadata của lần export.

## 16. Những điểm cần nhớ

- Dữ liệu có thể thay đổi giữa các request phân trang; `from/size` và `search_after` không có PIT không bảo đảm một snapshot ổn định.
- Scroll giữ search context từ lần search ban đầu; insert/update/delete sau đó không thay đổi góc nhìn của lượt scroll đang chạy.
- PIT giữ góc nhìn ổn định cho nhiều request search và thường được kết hợp với `search_after`.
- Scroll/PIT dựa trên dữ liệu đã searchable tại thời điểm mở context; write chưa refresh có thể chưa xuất hiện trong snapshot.
- Document mới sau snapshot không được thêm vào lượt quét; document bị update/delete sau snapshot vẫn có thể được đọc theo phiên bản ban đầu.
- Scroll ID và PIT ID là trạng thái tạm thời; dùng ID mới nhất từ response và đóng context khi xong.
- `keep_alive` là thời gian context cần được giữ giữa các request, không phải thời lượng tối đa của toàn bộ export.
- Sort cần thứ tự xác định; PIT có thể dùng `_shard_doc` làm tie-breaker, còn search không PIT cần field tie-breaker ổn định.
- `searchForStream` của Spring Data Elasticsearch giúp xử lý scroll theo iterator; luôn đóng iterator bằng try-with-resources.
- Snapshot search không phải transaction ACID, không khóa write và không thay thế Snapshot and Restore API.
- Muốn bao gồm thay đổi phát sinh trong lúc export, cần delta pass, CDC/outbox, watermark hoặc mô hình dữ liệu bất biến.
- Scroll/PIT không bảo đảm exactly-once cho sink; cần ID ổn định, idempotency và checkpoint đúng thứ tự.

Khi dữ liệu tiếp tục thay đổi trong lúc quét, điều quan trọng là xác định rõ export cần phản ánh trạng thái nào. Dùng Scroll hoặc PIT để giữ góc nhìn đọc ổn định, dùng `search_after` với PIT cho cursor có thứ tự, và bổ sung change log/delta khi phải thu nhận các cập nhật phát sinh sau snapshot. Thiết kế cả reader, sink và checkpoint cùng nhau để tránh mất hoặc nhân đôi dữ liệu.

## Tài liệu tham khảo

- [Elasticsearch — Scroll search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html#scroll-search-results)
- [Elasticsearch — Point in Time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Elasticsearch — Search after](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html#search-after)
- [Spring Data Elasticsearch — Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
