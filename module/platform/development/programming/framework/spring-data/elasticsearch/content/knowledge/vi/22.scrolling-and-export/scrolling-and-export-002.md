# Point in time để duy trì góc nhìn dữ liệu giữa các trang

## 1. Vì sao phân trang cần một góc nhìn dữ liệu ổn định?

Một trang tìm kiếm thường được tải bằng một request. Khi người dùng bấm sang trang tiếp theo, ứng dụng gửi request mới với cùng điều kiện tìm kiếm nhưng vị trí bắt đầu hoặc cursor khác.

Nếu dữ liệu trong index thay đổi giữa hai request, kết quả của trang sau có thể không còn tiếp nối chính xác trang trước. Ví dụ:

1. Trang đầu trả về 20 sản phẩm, được sắp xếp theo `createdAt` giảm dần.
2. Một sản phẩm mới được thêm vào index và Elasticsearch refresh.
3. Người dùng tải trang tiếp theo.
4. Vị trí của các document trong thứ tự kết quả có thể thay đổi; document đã thấy có thể xuất hiện lại hoặc document chưa thấy bị bỏ qua.

Vấn đề này đặc biệt rõ khi dùng `from` và `size`, nhưng cũng có thể xảy ra với `search_after` nếu mỗi request nhìn vào một trạng thái index mới.

**Point in time (PIT)** giải quyết vấn đề bằng cách tạo một góc nhìn nhất quán về index tại thời điểm mở PIT. Những request tìm kiếm tiếp theo có thể dùng cùng PIT để tiếp tục đọc dữ liệu từ góc nhìn đó, ngay cả khi index bên ngoài vẫn nhận document mới hoặc được refresh.

PIT thường được kết hợp với `search_after` để phân trang sâu và ổn định. PIT không tự chia trang; nó giữ trạng thái dữ liệu mà các trang đang đọc.

## 2. Point in time là gì?

Point in time là một search context nhẹ, đại diện cho trạng thái dữ liệu Elasticsearch tại thời điểm PIT được mở. Elasticsearch giữ lại các tài nguyên cần thiết để những lần tìm kiếm tiếp theo tiếp tục nhìn thấy cùng trạng thái đó.

Có thể hình dung:

~~~text
Thời điểm T0: mở PIT trên index products
                 |
                 v
        PIT giữ góc nhìn dữ liệu T0
                 |
       +---------+----------+
       |                    |
       v                    v
  T1: tải trang 1       Index có document mới
       |                    |
       v                    v
  T2: tải trang 2       Index tiếp tục refresh
       |                    |
       v                    v
  T3: tải trang 3       Dữ liệu hiện hành thay đổi

Các request dùng PIT vẫn đọc góc nhìn T0.
~~~

PIT có những đặc điểm sau:

- Giữ góc nhìn của dữ liệu tại thời điểm tạo PIT.
- Cho phép nhiều request tìm kiếm tiếp tục sử dụng cùng search context.
- Không khóa index và không ngăn ứng dụng ghi document mới.
- Các thay đổi được refresh sau thời điểm mở PIT không xuất hiện trong góc nhìn của PIT đó.
- Có thời hạn tồn tại, được điều khiển bằng `keep_alive`.
- Giữ tài nguyên trên cluster, vì vậy cần đóng PIT khi không còn sử dụng.

PIT không phải bản sao đầy đủ của index, không phải snapshot backup và cũng không phải transaction bao trùm các hệ thống bên ngoài Elasticsearch. Nó là cơ chế duy trì search context để các truy vấn đọc có thể dùng cùng một góc nhìn dữ liệu.

## 3. PIT khác gì với search_after và from/size?

Ba khái niệm này thường được dùng cùng nhau nhưng có vai trò khác nhau:

| Cơ chế | Vai trò | Giới hạn hoặc lưu ý |
|---|---|---|
| `from` và `size` | Lấy một trang theo vị trí bắt đầu và số lượng document | Phù hợp với trang đầu; phân trang sâu tốn tài nguyên và chịu giới hạn `max_result_window` |
| `search_after` | Lấy trang tiếp theo dựa trên sort values của hit cuối trang trước | Cần giữ nguyên query và sort; tự nó không giữ snapshot giữa các request |
| PIT | Giữ góc nhìn index nhất quán giữa nhiều request | Cần quản lý ID, `keep_alive` và đóng search context |

`search_after` giải quyết việc tiếp tục từ vị trí của hit cuối cùng. PIT giải quyết việc những request tiếp theo vẫn nhìn thấy cùng trạng thái dữ liệu. Vì vậy, khi cần phân trang sâu và nhất quán, thường kết hợp cả hai:

~~~text
PIT: giữ góc nhìn dữ liệu ổn định
  +
search_after: xác định vị trí tiếp tục
  =
Phân trang sâu trên cùng một góc nhìn
~~~

PIT cũng có thể được dùng với `from` và `size` cho những trang đầu. Tuy nhiên, nếu cần lấy hơn 10.000 hit, nên dùng PIT cùng `search_after` thay vì tăng `from` liên tục.

## 4. Mở PIT bằng Elasticsearch REST API

Trước tiên, mở PIT trên index cần tìm kiếm:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Elasticsearch trả về một ID:

~~~json
{
  "id": "46ToAwMDaWR5BXV1aWQy..."
}
~~~

ID này là định danh của point in time. Ứng dụng cần giữ nó để gửi trong các request tìm kiếm tiếp theo.

`keep_alive=1m` yêu cầu Elasticsearch duy trì PIT ít nhất trong khoảng thời gian cần thiết để thực hiện request tiếp theo. Khi request tìm kiếm tiếp tục sử dụng PIT và gửi `keep_alive` mới, thời hạn tồn tại được gia hạn.

Có thể mở PIT trên một index, alias hoặc nhiều index được chỉ định trong request mở PIT. Nếu mở trên alias, các index mà alias trỏ đến tại thời điểm mở sẽ là phạm vi dữ liệu của PIT.

### Tìm kiếm trang đầu bằng PIT

Sau khi mở PIT, gửi request tìm kiếm đến `/_search` và truyền PIT trong body:

~~~http
GET /_search
{
  "size": 100,
  "pit": {
    "id": "46ToAwMDaWR5BXV1aWQy...",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "createdAt": "asc"
    }
  ],
  "track_total_hits": false
}
~~~

Một số điểm quan trọng:

- Khi tìm kiếm bằng PIT, không đặt tên index trong đường dẫn `/_search`.
- Không truyền lại `index`, `routing` hoặc `preference` trong request search dùng PIT; các thông tin này đã được gắn với PIT lúc mở.
- `size` xác định số document của trang hiện tại.
- `sort` phải được giữ nguyên giữa các trang.
- `track_total_hits: false` có thể giảm chi phí nếu ứng dụng không cần tổng số document chính xác.

### Đọc sort values của hit cuối trang

Mỗi hit trong response có thể chứa `sort` values. Ví dụ:

~~~json
{
  "pit_id": "46ToAwMDaWR5BXV1aWQy...",
  "hits": {
    "hits": [
      {
        "_id": "p-100",
        "_source": {
          "createdAt": "2026-10-10T09:00:00Z",
          "name": "Wireless Headphones"
        },
        "sort": [
          "2026-10-10T09:00:00Z",
          4294967298
        ]
      }
    ]
  }
}
~~~

Khi dùng PIT, Elasticsearch tự thêm một sort tiebreaker có tên `_shard_doc`. Giá trị này được thêm vào cuối sort values để phân biệt các document có cùng giá trị của field sort chính.

Ứng dụng lấy toàn bộ mảng `sort` của hit cuối cùng làm cursor cho request tiếp theo. Không tự tạo hoặc chỉ lấy một phần sort values.

## 5. Lấy trang tiếp theo bằng search_after

Để lấy trang tiếp theo, gửi lại cùng query và sort, thêm `search_after` từ hit cuối cùng của trang trước:

~~~http
GET /_search
{
  "size": 100,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "createdAt": "asc"
    }
  ],
  "search_after": [
    "2026-10-10T09:00:00Z",
    4294967298
  ],
  "track_total_hits": false
}
~~~

Trong ví dụ:

- `LATEST_PIT_ID` là PIT ID mới nhất nhận được từ response trước đó.
- `search_after` chứa sort values của hit cuối cùng ở trang trước.
- `query` và `sort` được giữ nguyên.
- `size` có thể giữ nguyên để các trang có cùng kích thước.

Lặp lại quy trình này cho đến khi không còn hit:

~~~text
Mở PIT
  |
  v
Tìm trang đầu
  |
  v
Lấy sort values của hit cuối
  |
  v
Gửi search_after + PIT ID mới nhất
  |
  v
Lấy trang tiếp theo
  |
  +------ còn hit ------> Lặp lại
  |
  +------ hết hit ------> Đóng PIT
~~~

Với request sử dụng PIT, `from` phải là `0` (mặc định) hoặc `-1`. Không tăng `from` theo số trang khi đã dùng `search_after`.

## 6. Luôn sử dụng PIT ID mới nhất

Một chi tiết rất quan trọng là Elasticsearch có thể trả về `pit_id` mới sau mỗi request tìm kiếm.

Vì vậy, không nên mở PIT một lần rồi giữ ID ban đầu cho toàn bộ quá trình. Sau mỗi response:

1. Đọc `pit_id` trong response.
2. Nếu có ID mới, cập nhật ID đang giữ.
3. Dùng ID mới nhất trong request tiếp theo.
4. Khi kết thúc, đóng PIT bằng ID mới nhất.

Ví dụ:

~~~text
Open PIT
  |
  v
pit_id = A
  |
  v
Search page 1
  |
  v
Response pit_id = B
  |
  v
Search page 2 uses B
  |
  v
Response pit_id = C
  |
  v
Search page 3 uses C
  |
  v
Close PIT using C
~~~

Việc cập nhật ID là một phần của vòng đời PIT. Nếu ứng dụng tiếp tục sử dụng ID cũ trong khi Elasticsearch đã trả về ID mới, request tiếp theo có thể không sử dụng đúng search context mới nhất.

Với một cursor phân trang, nên thực hiện tuần tự từng request. Nếu gửi nhiều request đồng thời bằng cùng một PIT ID, mỗi response có thể trả về các ID mới khác nhau và ứng dụng phải quản lý việc chọn ID tiếp theo cẩn thận hơn.

## 7. keep_alive và vòng đời PIT

`keep_alive` là thời gian Elasticsearch giữ search context của PIT trước khi tự động hết hạn.

Ví dụ mở PIT trong một phút:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Request tìm kiếm tiếp theo có thể gia hạn thêm một phút:

~~~json
{
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  }
}
~~~

Không cần đặt `keep_alive` dài bằng tổng thời gian xử lý tất cả trang. Nó chỉ cần đủ để ứng dụng hoàn tất xử lý trang hiện tại và gửi request tiếp theo. Mỗi request tiếp tục có thể gia hạn thời gian tồn tại.

Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| `10s` | 10 giây |
| `30s` | 30 giây |
| `1m` | 1 phút |
| `5m` | 5 phút |

Nếu người dùng để trang tìm kiếm mở quá lâu mà không có request mới, PIT có thể hết hạn. Khi đó, cursor cũ không thể tiếp tục sử dụng. Ứng dụng cần mở PIT mới và bắt đầu lại quy trình phân trang nếu vẫn cần một góc nhìn nhất quán.

Không nên đặt thời gian tồn tại quá dài chỉ để phòng trường hợp người dùng quay lại sau nhiều giờ. PIT giữ tài nguyên trên Elasticsearch; thời gian càng dài thì tài nguyên cần giữ có thể càng lớn.

## 8. Đóng PIT khi hoàn tất

PIT tự hết hạn khi thời gian `keep_alive` kết thúc. Tuy nhiên, ứng dụng nên chủ động đóng PIT ngay khi người dùng hoàn tất việc phân trang hoặc quá trình export kết thúc.

REST API:

~~~http
DELETE /_pit
{
  "id": "LATEST_PIT_ID"
}
~~~

Response:

~~~json
{
  "succeeded": true,
  "num_freed": 3
}
~~~

Đóng PIT giúp Elasticsearch giải phóng các search context liên quan. Nên thực hiện trong khối `finally` hoặc cơ chế cleanup tương đương để việc đóng vẫn diễn ra khi quá trình xử lý gặp exception.

Nếu request cuối cùng trả về PIT ID mới, phải dùng ID mới đó để đóng. Không đóng bằng ID cũ nếu đã nhận được ID cập nhật.

## 9. Tích hợp PIT với Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ PIT thông qua `ElasticsearchOperations` và `SearchOperations`.

Các API chính:

| API | Vai trò |
|---|---|
| `openPointInTime(IndexCoordinates, Duration)` | Mở PIT và trả về PIT ID |
| `closePointInTime(String)` | Đóng PIT |
| `Query.PointInTime(String, Duration)` | Mang PIT ID và keep-alive trong query |
| `Query.setPointInTime(...)` | Gắn PIT vào query |
| `SearchHits.getPointInTimeId()` | Lấy PIT ID mới từ response |
| `Query.setSearchAfter(...)` | Đặt cursor từ sort values |
| `SearchHit.getSortValues()` | Lấy sort values của một hit |

PIT API của Spring Data Elasticsearch có từ phiên bản 5.0. Các tên package hoặc cách tạo query có thể khác ở phiên bản cũ; hãy đối chiếu dependency thực tế của dự án.

### Mở PIT và tìm kiếm bằng CriteriaQuery

Ví dụ entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructors, getters và setters
}
~~~

Mở PIT và tìm kiếm trang đầu:

~~~java
import java.time.Duration;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Duration keepAlive = Duration.ofMinutes(1);

String pitId = operations.openPointInTime(
    IndexCoordinates.of("products"),
    keepAlive
);

CriteriaQuery query = new CriteriaQuery(
    new Criteria("active").is(true)
);

query.setPageable(PageRequest.of(
    0,
    100,
    Sort.by(Sort.Order.asc("createdAt"))
));

query.setPointInTime(new Query.PointInTime(pitId, keepAlive));

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

Điểm cần chú ý:

- Mở PIT bằng `IndexCoordinates` của index hoặc alias cần tìm.
- `Query.PointInTime` nhận PIT ID và thời gian keep-alive.
- `setPointInTime` gắn PIT vào query.
- Khi query đã dùng PIT, gọi overload `operations.search(query, Product.class)` không truyền lại `IndexCoordinates`.
- `PageRequest` dùng trang `0` và giới hạn số hit của trang đầu.

### Tiếp tục trang bằng SearchAfter

Có thể lấy sort values của hit cuối cùng rồi tạo query tiếp theo:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

List<SearchHit<Product>> pageHits = hits.getSearchHits();

if (!pageHits.isEmpty()) {
    SearchHit<Product> lastHit =
        pageHits.get(pageHits.size() - 1);

    List<Object> searchAfter = lastHit.getSortValues();

    String latestPitId = hits.getPointInTimeId() != null
        ? hits.getPointInTimeId()
        : pitId;

    CriteriaQuery nextQuery = new CriteriaQuery(
        new Criteria("active").is(true)
    );

    nextQuery.setPageable(PageRequest.of(
        0,
        100,
        Sort.by(Sort.Order.asc("createdAt"))
    ));

    nextQuery.setSearchAfter(searchAfter);

    nextQuery.setPointInTime(
        new Query.PointInTime(latestPitId, keepAlive)
    );

    SearchHits<Product> nextHits = operations.search(
        nextQuery,
        Product.class
    );
}
~~~

Trong ví dụ này, `searchAfter` lấy trực tiếp từ hit cuối trang trước. `latestPitId` lấy từ response trước đó, không nhất thiết giống ID được trả về khi mở PIT.

Khi tiếp tục nhiều trang, phải cập nhật cả hai thông tin sau mỗi lần tìm kiếm:

- Cursor: sort values của hit cuối cùng trong trang vừa nhận.
- PIT ID: ID mới nhất từ `SearchHits.getPointInTimeId()`.

Nếu `getPointInTimeId()` trả về `null`, ứng dụng cần giữ ID PIT đang có thay vì ghi đè bằng `null`.

## 10. Ví dụ vòng lặp phân trang hoàn chỉnh trong Spring Data

Đoạn code sau minh họa một quy trình đọc toàn bộ sản phẩm đang hoạt động theo từng lô. Mỗi request tiếp tục từ hit cuối trang trước và sử dụng PIT ID mới nhất.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.function.Consumer;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductExportService {

    private static final int PAGE_SIZE = 100;

    private final ElasticsearchOperations operations;

    public ProductExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportActiveProducts(Consumer<Product> consumer) {

        Duration keepAlive = Duration.ofMinutes(1);

        String latestPitId = operations.openPointInTime(
            IndexCoordinates.of("products"),
            keepAlive
        );

        List<Object> searchAfter = null;

        try {
            while (true) {
                CriteriaQuery query = new CriteriaQuery(
                    new Criteria("active").is(true)
                );

                query.setPageable(PageRequest.of(
                    0,
                    PAGE_SIZE,
                    Sort.by(Sort.Order.asc("createdAt"))
                ));

                query.setPointInTime(
                    new Query.PointInTime(latestPitId, keepAlive)
                );

                query.setTrackTotalHits(false);

                if (searchAfter != null) {
                    query.setSearchAfter(searchAfter);
                }

                SearchHits<Product> hits = operations.search(
                    query,
                    Product.class
                );

                String returnedPitId = hits.getPointInTimeId();

                if (returnedPitId != null) {
                    latestPitId = returnedPitId;
                }

                List<SearchHit<Product>> page = hits.getSearchHits();

                if (page.isEmpty()) {
                    break;
                }

                for (SearchHit<Product> hit : page) {
                    consumer.accept(hit.getContent());
                }

                SearchHit<Product> lastHit = page.get(page.size() - 1);
                searchAfter = lastHit.getSortValues();

                if (page.size() < PAGE_SIZE) {
                    break;
                }
            }
        } finally {
            operations.closePointInTime(latestPitId);
        }
    }
}
~~~

Vòng lặp hoạt động như sau:

1. Mở PIT trên index `products`.
2. Tạo query có điều kiện `active = true`.
3. Đặt trang đầu ở vị trí `0`, kích thước 100 và sort theo `createdAt`.
4. Gắn PIT ID và `keep_alive`.
5. Gọi `operations.search`.
6. Cập nhật PIT ID nếu response trả về ID mới.
7. Xử lý các document trong trang.
8. Lấy sort values của hit cuối cùng.
9. Nếu trang đủ 100 hit, tiếp tục bằng `search_after`.
10. Khi hết dữ liệu hoặc có lỗi, đóng PIT bằng ID mới nhất.

Đây là ví dụ đồng bộ. Nếu ứng dụng dùng API reactive, cần quản lý cùng vòng đời PIT và cleanup theo cách bất đồng bộ phù hợp với reactive pipeline.

Trong code thực tế, cần xử lý trường hợp PIT hết hạn hoặc shard gặp lỗi. Khi PIT đã hết hạn, không thể tiếp tục bằng cursor cũ; hãy mở PIT mới và khởi động lại quá trình đọc nếu nghiệp vụ cho phép.

## 11. Vì sao PIT cần sort ổn định?

`search_after` cần sort values để xác định chính xác vị trí bắt đầu của trang kế tiếp. Nếu nhiều document có cùng giá trị sort, việc phân trang có thể bỏ sót hoặc lặp lại hit nếu không có tiebreaker.

Ví dụ chỉ sort theo `createdAt`:

~~~json
{
  "sort": [
    {
      "createdAt": "asc"
    }
  ]
}
~~~

Nhiều sản phẩm có thể được tạo cùng một thời điểm. Elasticsearch cần một giá trị phụ để phân biệt thứ tự của các document đó.

Khi dùng PIT, Elasticsearch tự thêm `_shard_doc` làm tiebreaker cho các request tìm kiếm. `_shard_doc` là giá trị duy nhất cho document trong phạm vi PIT và ổn định trong suốt vòng đời của PIT đó.

Nếu không dùng PIT, hãy tự thêm một field có giá trị duy nhất cho mỗi document vào sort, ví dụ `id` hoặc một trường tie-breaker có `doc_values` phù hợp.

Một số lưu ý:

- Giữ nguyên thứ tự và các field sort giữa các request.
- Dùng toàn bộ sort values của hit cuối cùng, kể cả tiebreaker do PIT thêm.
- Không tự tính giá trị `_shard_doc`.
- Nếu sort theo ngày trên nhiều index có kiểu dữ liệu khác nhau, cần chuẩn hóa format và kiểu số để `search_after` được diễn giải nhất quán.
- Khi cần thứ tự nghiệp vụ, chọn field sort phù hợp rồi để PIT cung cấp tiebreaker ổn định.

## 12. PIT và những thay đổi dữ liệu trong lúc phân trang

PIT giữ góc nhìn dữ liệu ở thời điểm mở. Điều đó có nghĩa:

- Document được thêm sau thời điểm PIT mở sẽ không xuất hiện trong các trang của PIT đó.
- Thay đổi hoặc xóa document sau thời điểm mở không làm thay đổi góc nhìn mà PIT đang giữ.
- Một refresh mới không làm PIT chuyển sang trạng thái index mới.
- Khi mở PIT mới, ứng dụng sẽ nhìn thấy trạng thái dữ liệu mới nhất đã được Elasticsearch refresh và hiển thị.

Ví dụ:

~~~text
T0: index có A, B, C
    Mở PIT-1

T1: thêm D, refresh
    PIT-1 vẫn nhìn thấy A, B, C

T2: tải trang tiếp theo bằng PIT-1
    Kết quả vẫn thuộc tập A, B, C

T3: mở PIT-2
    PIT-2 nhìn thấy A, B, C, D
~~~

Điều này rất hữu ích cho giao diện tìm kiếm cần giữ kết quả ổn định trong một phiên duyệt. Tuy nhiên, nếu người dùng muốn thấy dữ liệu mới vừa được thêm, ứng dụng cần bắt đầu một phiên tìm kiếm mới bằng PIT mới.

PIT không thay thế cơ chế đồng bộ dữ liệu hoặc transaction của ứng dụng. Nó chỉ kiểm soát góc nhìn khi đọc dữ liệu Elasticsearch.

## 13. PIT khi dùng alias, rollover và nhiều index

PIT có thể mở trên alias hoặc nhiều index. Khi mở PIT trên alias, Elasticsearch xác định các index đích tại thời điểm tạo PIT.

Ví dụ:

~~~http
POST /products-read/_pit?keep_alive=1m
~~~

Giả sử `products-read` đang trỏ tới `products-v1`. Sau đó hệ thống chuyển alias sang `products-v2`. Những request dùng PIT đã mở vẫn tiếp tục trên góc nhìn được tạo lúc mở PIT; phiên phân trang mới mở PIT mới sẽ dùng trạng thái alias hiện tại.

Điều này hữu ích trong các hệ thống dùng alias và rollover:

- Một phiên tìm kiếm đang diễn ra có thể tiếp tục đọc cùng tập index.
- Phiên tìm kiếm mới có thể nhìn thấy index thế hệ mới.
- Ứng dụng không cần tự thay đổi index path trong từng trang khi đang dùng PIT.

Khi alias trỏ đến nhiều index, mapping và kiểu dữ liệu của field sort phải tương thích giữa các index. Nếu sort theo ngày nhưng một index dùng `date` và index khác dùng `date_nanos`, cần cấu hình `numeric_type` và `format` phù hợp theo yêu cầu Elasticsearch.

## 14. PIT có tốn tài nguyên không?

Có. PIT giữ các search context và tài nguyên liên quan để duy trì góc nhìn dữ liệu cũ. Elasticsearch có thể phải giữ lại các segment cũ mà PIT còn tham chiếu, ngay cả khi index đã refresh hoặc merge segment mới.

Các ảnh hưởng có thể gặp:

- Tăng số search context đang mở.
- Giữ lại segment cũ lâu hơn.
- Tăng áp lực lên file handle, bộ nhớ và dung lượng đĩa.
- Làm chậm quá trình giải phóng tài nguyên sau merge nếu PIT tồn tại quá lâu.

Vì vậy:

- Dùng `keep_alive` ngắn nhưng đủ cho request tiếp theo.
- Gia hạn khi thực sự cần tiếp tục phân trang.
- Đóng PIT ngay sau khi hoàn tất.
- Không mở PIT mới cho mỗi request nếu một phiên tìm kiếm có thể dùng chung PIT.
- Theo dõi số lượng search context đang mở và trạng thái cluster.
- Giới hạn số phiên PIT đồng thời theo nhu cầu ứng dụng.

Không nên giữ PIT trong suốt thời gian người dùng mở một tab vô thời hạn. Nếu phiên tìm kiếm bị bỏ dở, hãy để TTL giải phóng tài nguyên và có thể yêu cầu người dùng bắt đầu một phiên tìm kiếm mới.

## 15. PIT hết hạn hoặc gặp lỗi thì xử lý thế nào?

PIT có thể không còn sử dụng được trong một số trường hợp:

- `keep_alive` đã hết hạn.
- Cluster hoặc node gặp sự cố khiến search context không còn khả dụng.
- Một shard trong PIT bị lỗi hoặc không sẵn sàng.
- Ứng dụng gửi sai PIT ID hoặc tiếp tục dùng ID cũ.

Khi PIT hết hạn, Elasticsearch có thể trả lỗi cho request tìm kiếm. Ứng dụng không nên tiếp tục gửi `search_after` cũ với PIT ID mới được tạo tùy tiện, vì cursor đó thuộc một góc nhìn khác.

Quy trình xử lý phù hợp:

1. Ghi nhận phiên tìm kiếm cũ không còn hiệu lực.
2. Nếu có thể, đóng PIT cũ bằng ID còn lưu.
3. Mở PIT mới trên index hoặc alias hiện hành.
4. Tạo lại query và sort.
5. Bắt đầu phân trang từ trang đầu.
6. Thông báo cho người dùng nếu giao diện cần làm mới kết quả.

Nếu response có shard failure, cần kiểm tra thông tin shard thay vì mặc định rằng dữ liệu trả về là đầy đủ. Với một PIT có shard bị thiếu, Elasticsearch có thể tiếp tục báo lỗi tương ứng ở các lần tìm kiếm tiếp theo; khi shard đã phục hồi, có thể cần mở PIT mới.

## 16. PIT, scroll và export dữ liệu lớn

PIT cùng `search_after` thường phù hợp cho phân trang sâu và duy trì góc nhìn nhất quán. Scroll vẫn có vai trò trong một số quy trình đọc dữ liệu theo lô hoặc xử lý export truyền thống.

| Tiêu chí | PIT + search_after | Scroll |
|---|---|---|
| Mục tiêu phổ biến | Phân trang sâu, duy trì góc nhìn nhất quán | Đọc kết quả theo lô trong một tiến trình |
| Cursor | Sort values của hit cuối | Scroll ID |
| Góc nhìn dữ liệu | PIT giữ trạng thái index tại thời điểm mở | Scroll giữ search context của lần tìm kiếm |
| Request tiếp theo | Gửi query, PIT và search_after | Gửi scroll ID và thời gian giữ |
| Cleanup | Đóng PIT | Clear scroll context |
| Phù hợp | Tìm kiếm nhiều trang, cursor pagination | Batch processing và một số tác vụ export |

Không nên dùng `from`/`size` để đọc hàng trăm nghìn document. Với yêu cầu phân trang sâu, PIT kết hợp `search_after` là lựa chọn phù hợp. Với batch export, hãy chọn PIT hoặc scroll theo yêu cầu về cách xử lý, khả năng tiếp tục, thời gian chạy và tài nguyên.

Spring Data Elasticsearch cũng hỗ trợ `searchForStream(...)` để đọc kết quả theo luồng; tài liệu của framework mô tả việc sử dụng scroll nội bộ cho API này. Nếu chọn stream/scroll, cần đóng tài nguyên hoặc giải phóng scroll context theo API tương ứng.

## 17. Những lỗi thường gặp khi dùng PIT

**Nghĩ rằng PIT tự phân trang.** PIT chỉ giữ góc nhìn dữ liệu. Cần dùng `search_after` hoặc cơ chế phân trang khác để lấy trang tiếp theo.

**Dùng lại PIT ID ban đầu.** Mỗi response có thể trả về ID mới. Luôn cập nhật và sử dụng ID mới nhất.

**Quên giữ sort values.** `search_after` phải nhận toàn bộ sort values của hit cuối cùng, bao gồm tiebreaker khi dùng PIT.

**Thay đổi query hoặc sort giữa các trang.** Các request dùng chung cursor phải giữ cùng query và sort để vị trí tiếp tục có ý nghĩa.

**Đặt `keep_alive` quá ngắn.** Nếu ứng dụng không gửi request tiếp theo trước khi PIT hết hạn, phiên phân trang sẽ bị mất.

**Đặt `keep_alive` quá dài.** PIT giữ tài nguyên trên cluster. Chỉ gia hạn đủ lâu cho bước tiếp theo và đóng khi hoàn tất.

**Không đóng PIT.** Dù PIT tự hết hạn, ứng dụng nên chủ động đóng để giải phóng tài nguyên sớm.

**Dùng index path cùng PIT search.** Request search có PIT không truyền lại index, routing hoặc preference; các thông tin này đã được xác định khi mở PIT.

**Dùng `from` tăng dần cùng search_after.** Với PIT và search_after, giữ `from` ở mặc định hoặc `0`; tiếp tục bằng sort values.

**Cho rằng PIT khóa ghi.** PIT không chặn các thao tác ghi. Nó chỉ giữ góc nhìn đọc ổn định.

**Dùng cursor của PIT cũ cho PIT mới.** Sort values của phiên cũ không phải cursor hợp lệ cho một góc nhìn mới. Nếu PIT hết hạn, hãy bắt đầu lại quá trình phân trang.

## 18. Quy trình triển khai PIT cho màn hình tìm kiếm

Có thể triển khai theo trình tự sau:

1. Xác định tập index hoặc alias cần tìm kiếm.
2. Chọn field sort có kiểu dữ liệu phù hợp và xác định thứ tự kết quả.
3. Mở PIT với `keep_alive` vừa đủ.
4. Thực hiện request trang đầu bằng query, sort và PIT ID.
5. Lưu PIT ID mới nhất từ response.
6. Lưu sort values của hit cuối cùng làm cursor.
7. Khi người dùng yêu cầu trang tiếp theo, gửi lại cùng query/sort, PIT ID mới nhất và `search_after`.
8. Gia hạn `keep_alive` trong request tiếp theo.
9. Tiếp tục đến khi hết kết quả hoặc người dùng kết thúc phiên.
10. Đóng PIT bằng ID mới nhất trong `finally` hoặc cleanup handler.
11. Nếu PIT hết hạn, tạo phiên mới và bắt đầu lại từ trang đầu.
12. Theo dõi số PIT đang mở, thời gian tồn tại và tài nguyên cluster.

Nếu giao diện có nhiều phiên tìm kiếm đồng thời, mỗi phiên cần có PIT ID và cursor riêng. Không dùng chung một PIT/cursor giữa những truy vấn có điều kiện hoặc thứ tự sort khác nhau.

## Kết luận

Point in time giữ một góc nhìn nhất quán về dữ liệu Elasticsearch tại thời điểm mở PIT. Nhờ đó, các request tải trang tiếp theo không bị ảnh hưởng bởi document mới được thêm, cập nhật hoặc xóa sau thời điểm tạo PIT.

PIT thường được kết hợp với `search_after`: PIT giữ trạng thái dữ liệu, còn `search_after` xác định vị trí tiếp tục. Để phân trang đúng, phải giữ nguyên query và sort, lấy đầy đủ sort values của hit cuối cùng và luôn cập nhật PIT ID mới nhất từ response.

Trong Spring Data Elasticsearch, có thể mở PIT bằng `ElasticsearchOperations.openPointInTime`, gắn vào query bằng `Query.PointInTime`, đọc ID mới qua `SearchHits.getPointInTimeId()` và đóng bằng `closePointInTime`. Quản lý `keep_alive` hợp lý và cleanup sau khi hoàn tất giúp duy trì kết quả ổn định mà vẫn kiểm soát tài nguyên cluster.

## Tài liệu tham khảo

- [Elasticsearch — Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch — Open a point in time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time)
- [Elasticsearch — Close a point in time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-close-point-in-time)
- [Spring Data Elasticsearch — Point in Time API](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html)
- [Spring Data Elasticsearch — SearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchOperations.html)
- [Spring Data Elasticsearch — Query.PointInTime API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Query.PointInTime.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/SearchHits.html)
