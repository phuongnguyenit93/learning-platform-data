# Kết hợp PIT với search_after qua API phiên bản đang dùng

Khi phải đọc một lượng lớn document theo nhiều trang, phân trang bằng `from/size` sẽ ngày càng tốn tài nguyên. Elasticsearch phải xử lý các kết quả ở những vị trí trước trang hiện tại rồi mới trả về phần dữ liệu cần đọc. Ngoài ra, nếu index được refresh trong lúc ứng dụng đang đọc từng trang, kết quả của các request search độc lập có thể thay đổi giữa chừng.

**Point in Time (PIT)** và **`search_after`** giải quyết hai vấn đề khác nhau và bổ trợ cho nhau:

- PIT giữ một góc nhìn nhất quán của dữ liệu tại thời điểm mở.
- `search_after` tiếp tục từ vị trí của hit cuối cùng ở trang trước mà không phải bỏ qua toàn bộ các trang trước đó.

Kết hợp hai cơ chế giúp ứng dụng quét dữ liệu theo từng batch với thứ tự ổn định, phù hợp cho export, đồng bộ, xử lý nền và các API cần phân trang sâu.

Bài này sử dụng API của Spring Data Elasticsearch 5.x, với các ví dụ tương thích API 5.4.x: `ElasticsearchOperations.openPointInTime(...)`, `Query.PointInTime`, `NativeQueryBuilder.withSearchAfter(...)`, `SearchHit.getSortValues()` và `SearchHits.getPointInTimeId()`. Nếu dự án dùng phiên bản khác, cần đối chiếu Javadoc của đúng phiên bản đang được dependency management chọn.

## 1. Vì sao cần kết hợp PIT và search_after?

### Hạn chế của from/size khi đọc sâu

Một request phân trang thông thường:

~~~http
POST /products/_search
Content-Type: application/json

{
  "from": 20000,
  "size": 500,
  "query": {
    "match_all": {}
  }
}
~~~

Yêu cầu này trả 500 hit bắt đầu từ vị trí 20.000. Elasticsearch vẫn phải xử lý đủ số kết quả trước vị trí đó để xác định trang cần trả về. Khi `from` tăng cao, chi phí xử lý và bộ nhớ tăng theo.

Elasticsearch cũng giới hạn tổng số hit có thể truy cập bằng `from + size` theo `index.max_result_window`, thường mặc định là 10.000. Tăng giới hạn này không giải quyết được chi phí của phân trang sâu.

### search_after dùng con trỏ thay cho offset

`search_after` nhận các giá trị sort của hit cuối trang trước. Elasticsearch tiếp tục tìm các hit đứng sau vị trí đó theo cùng thứ tự sort.

Ví dụ, trang đầu kết thúc ở:

~~~json
{
  "sort": [1299000, "P-1002"]
}
~~~

Trang kế tiếp truyền:

~~~json
{
  "search_after": [1299000, "P-1002"]
}
~~~

Request không cần `from: 20000`. Nó dùng giá trị sort làm con trỏ để tiếp tục từ vị trí đã đọc.

Tuy nhiên, nếu mỗi request search nhìn vào trạng thái index mới nhất, các thay đổi giữa hai request có thể làm kết quả không nhất quán: document mới xuất hiện, document bị xóa hoặc giá trị sort thay đổi. PIT giữ cùng một góc nhìn dữ liệu cho toàn bộ chuỗi request.

### Vai trò của từng thành phần

| Thành phần | Giải quyết vấn đề |
|---|---|
| PIT | Giữ snapshot tìm kiếm nhất quán qua nhiều request |
| Sort | Xác định thứ tự kết quả |
| search_after | Xác định vị trí tiếp tục từ trang trước |
| Sort values | Mang các giá trị cần truyền làm con trỏ |
| keep_alive | Gia hạn thời gian PIT còn hiệu lực |
| close PIT | Giải phóng search context khi hoàn tất |

~~~mermaid
flowchart TD
    A["Mở PIT trên index hoặc alias"] --> B["Tạo query + sort + PIT"]
    B --> C["Search trang đầu"]
    C --> D["Đọc hit và sort values cuối trang"]
    D --> E["Lấy PIT ID mới từ response"]
    E --> F["Search trang kế với search_after"]
    F --> G{"Còn hit?"}
    G -->|Có| D
    G -->|Không| H["Đóng PIT bằng ID mới nhất"]
~~~

## 2. PIT giữ lại điều gì?

PIT là một tham chiếu nhẹ tới trạng thái dữ liệu mà Elasticsearch nhìn thấy tại thời điểm mở PIT. Nó cho phép nhiều request search tiếp tục làm việc trên cùng một góc nhìn ngay cả khi index được refresh sau đó.

Ví dụ:

1. Ứng dụng mở PIT trên index `products`.
2. PIT ghi nhận trạng thái dữ liệu đang hiển thị tại thời điểm đó.
3. Ứng dụng đọc trang đầu.
4. Một tiến trình khác thêm, sửa hoặc xóa sản phẩm.
5. Ứng dụng đọc trang tiếp theo bằng cùng PIT.
6. Các trang tiếp theo vẫn được đọc theo góc nhìn đã mở PIT.

PIT không khóa index và không ngăn các ứng dụng khác ghi dữ liệu. Những thay đổi sau thời điểm mở PIT không được đưa vào snapshot đang dùng. Một document bị xóa hoặc cập nhật sau đó vẫn được nhìn theo trạng thái tại thời điểm PIT mở trong phạm vi snapshot đó.

PIT không phải transaction của cơ sở dữ liệu quan hệ. Nó không cung cấp transaction nhiều document, không ngăn index bị xóa và không thay thế cơ chế đồng bộ dữ liệu của ứng dụng.

## 3. API PIT trong Spring Data Elasticsearch 5.x

Spring Data Elasticsearch cung cấp API PIT trên `ElasticsearchOperations`.

Các phương thức chính:

| API | Vai trò |
|---|---|
| `openPointInTime(IndexCoordinates, Duration)` | Mở PIT và nhận PIT ID |
| `closePointInTime(String)` | Đóng PIT |
| `Query.PointInTime(id, keepAlive)` | Mô tả PIT ID và thời gian gia hạn cho một query |
| `withPointInTime(...)` | Gắn PIT vào query builder |
| `withSearchAfter(List<Object>)` | Gắn sort values của hit trước vào query |
| `SearchHits.getPointInTimeId()` | Đọc PIT ID mới được trả về sau lần search |
| `SearchHit.getSortValues()` | Đọc sort values của một hit |

PIT được hỗ trợ trong Spring Data Elasticsearch từ dòng 5.0. `search_after` có mặt trong Query abstraction từ dòng 4.2 và được kế thừa bởi `NativeQueryBuilder`.

Ví dụ import:

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query.PointInTime;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.client.elc.NativeQueryBuilder;

import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
~~~

Có hai kiểu cùng tên `Query` trong các package khác nhau:

- `co.elastic.clients.elasticsearch._types.query_dsl.Query`: query DSL của Elasticsearch Java API Client.
- `org.springframework.data.elasticsearch.core.query.Query`: abstraction query của Spring Data; `PointInTime` là record lồng bên trong kiểu này.

Trong code bên dưới, `Query` được import từ Java Client để xây dựng DSL. Để tránh import nhầm, có thể dùng tên đầy đủ `org.springframework.data.elasticsearch.core.query.Query.PointInTime` khi tạo PIT metadata.

## 4. Mở PIT trước khi đọc trang đầu

Giả sử ứng dụng cần đọc dữ liệu từ index `products`:

~~~java
import java.time.Duration;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;

public class ProductExporter {

    private final ElasticsearchOperations operations;

    public ProductExporter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void startExport() {
        Duration keepAlive = Duration.ofMinutes(1);

        String pitId = operations.openPointInTime(
                IndexCoordinates.of("products"),
                keepAlive
        );

        // Dùng pitId để tạo các request search tiếp theo.
    }
}
~~~

`IndexCoordinates.of("products")` xác định index hoặc alias được mở. `keepAlive` là thời gian PIT được giữ nếu không có request tiếp theo gia hạn.

Phương thức trả về một chuỗi PIT ID. Đây là định danh opaque do Elasticsearch cấp; ứng dụng chỉ lưu và truyền lại, không phân tích cấu trúc bên trong.

Có overload nhận thêm `ignoreUnavailable` khi cần quy định cách xử lý index không tồn tại hoặc đã đóng. Với luồng export cần dữ liệu đầy đủ, thường nên để lỗi index không khả dụng được phát hiện thay vì âm thầm bỏ qua index.

PIT cần quyền đọc trên index đích. Tài khoản ứng dụng không cần quyền quản trị index chỉ để mở PIT và tìm kiếm.

## 5. Tạo sort ổn định trước khi dùng search_after

`search_after` chỉ hoạt động đúng khi query có sort. Các request tiếp theo phải giữ nguyên thứ tự sort và kiểu dữ liệu của sort values.

Giả sử document có:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "createdAt": "2026-10-20T08:30:00Z"
}
~~~

Mapping nên khai báo:

~~~json
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Ta có thể sắp xếp theo `createdAt` tăng dần, rồi `productId` tăng dần:

~~~java
SortOptions byCreatedAt = SortOptions.of(s -> s
        .field(f -> f
                .field("createdAt")
                .order(SortOrder.Asc)
        )
);

SortOptions byProductId = SortOptions.of(s -> s
        .field(f -> f
                .field("productId")
                .order(SortOrder.Asc)
        )
);
~~~

`productId` đóng vai trò tie-breaker nếu nhiều document có cùng thời điểm tạo. Field tie-breaker phải có giá trị ổn định, hỗ trợ sort và đủ duy nhất trong tập index mà PIT đang đọc.

Không nên sort trực tiếp theo metadata `_id` như thể đó là một keyword field thông thường. Nếu cần sắp xếp theo document ID, hãy lưu một bản sao ID trong field keyword có doc values, hoặc dùng cơ chế tie-breaker PIT phù hợp.

Elasticsearch có thể thêm `_shard_doc` làm tie-breaker nội bộ khi search qua PIT. Nếu cần thứ tự nghiệp vụ dễ hiểu, hãy dùng field nghiệp vụ duy nhất làm tie-breaker. Nếu chỉ cần quét toàn bộ tập dữ liệu theo thứ tự nội bộ ổn định của PIT, có thể cân nhắc sort theo `_shard_doc`.

## 6. Tạo query đầu tiên với PIT

Trong Spring Data Elasticsearch 5.x, `NativeQuery.builder()` có thể nhận query DSL, sort, page size và PIT metadata.

Ví dụ trang đầu:

~~~java
import org.springframework.data.domain.PageRequest;

Query matchAll = Query.of(q -> q
        .matchAll(m -> m)
);

Duration keepAlive = Duration.ofMinutes(1);

NativeQuery firstPageQuery = NativeQuery.builder()
        .withQuery(matchAll)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .withPointInTime(
                new org.springframework.data.elasticsearch.core.query.Query.PointInTime(
                        pitId,
                        keepAlive
                )
        )
        .build();

SearchHits<ProductDocument> firstPage =
        operations.search(firstPageQuery, ProductDocument.class);
~~~

Các điểm cần chú ý:

- `PageRequest.of(0, 500)` giữ offset ở trang đầu và giới hạn 500 kết quả.
- PIT được gắn vào query bằng `withPointInTime(...)`.
- Chưa truyền `search_after` ở trang đầu.
- Khi query có PIT, gọi `operations.search(query, ProductDocument.class)`; không truyền index coordinates lần nữa. Index đã được xác định khi mở PIT.
- `matchAll` chỉ là ví dụ quét toàn bộ document. Trong thực tế có thể dùng query/filter nghiệp vụ, miễn là giữ nguyên chúng giữa các trang.

PIT mang theo index, routing và preference đã được xác định lúc mở. Khi gửi search request có PIT, không tự chỉ định lại index, routing hoặc preference trong request.

## 7. Lấy sort values từ hit cuối cùng

Sau khi nhận trang đầu, ứng dụng xử lý các document rồi lấy sort values của hit cuối:

~~~java
List<SearchHit<ProductDocument>> pageHits =
        firstPage.getSearchHits();

if (firstPage.hasSearchHits()) {
    for (SearchHit<ProductDocument> hit : pageHits) {
        ProductDocument product = hit.getContent();

        // Xử lý hoặc ghi product ra file đích.
    }

    SearchHit<ProductDocument> lastHit =
            pageHits.get(pageHits.size() - 1);

    List<Object> searchAfter = lastHit.getSortValues();
}
~~~

`getSortValues()` trả về danh sách giá trị theo đúng thứ tự các sort clause. Với sort `createdAt` rồi `productId`, sort values có thể là:

~~~json
[
  "2026-10-20T08:30:00.000Z",
  "P-1002"
]
~~~

Giữ nguyên danh sách này để truyền vào request kế tiếp. Không tự dựng lại từ entity, không đổi kiểu số thành chuỗi và không đảo thứ tự các phần tử.

Nếu query không có sort, `getSortValues()` không cung cấp con trỏ phù hợp cho `search_after`. Vì vậy, sort là điều kiện bắt buộc của luồng phân trang này.

## 8. Cập nhật PIT ID sau mỗi lần search

Một chi tiết quan trọng: response của mỗi request search qua PIT có thể trả về một PIT ID mới.

Trong Spring Data Elasticsearch, đọc ID mới bằng:

~~~java
String newPitId = searchHits.getPointInTimeId();
~~~

Nếu giá trị mới được trả về, phải dùng nó cho request tiếp theo và khi đóng PIT:

~~~java
if (searchHits.getPointInTimeId() != null) {
    pitId = searchHits.getPointInTimeId();
}
~~~

Không tiếp tục dùng mã PIT ban đầu trong toàn bộ quá trình. Elasticsearch yêu cầu request tiếp theo sử dụng PIT ID mới nhất mà response trước đó trả về.

`getPointInTimeId()` có thể trả về `null` nếu response không chứa ID mới. Trong trường hợp đó, giữ ID gần nhất đang có. Với một luồng PIT bình thường, response thường trả về ID để tiếp tục.

## 9. Tạo request trang tiếp theo bằng withSearchAfter

Trang kế tiếp dùng:

- Cùng query.
- Cùng sort.
- Cùng page size.
- PIT ID mới nhất.
- Sort values của hit cuối trang trước.

Ví dụ:

~~~java
NativeQuery nextPageQuery = NativeQuery.builder()
        .withQuery(matchAll)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .withPointInTime(
                new org.springframework.data.elasticsearch.core.query.Query.PointInTime(
                        pitId,
                        keepAlive
                )
        )
        .withSearchAfter(searchAfter)
        .build();

SearchHits<ProductDocument> nextPage =
        operations.search(nextPageQuery, ProductDocument.class);
~~~

`withSearchAfter(searchAfter)` nhận `List<Object>` lấy từ `SearchHit.getSortValues()`.

Lưu ý `PageRequest.of(0, 500)` vẫn ở trang 0. `search_after` đã xác định vị trí tiếp tục; không tăng page index như phân trang offset. Nếu dùng page index lớn cùng search_after, có thể tạo offset không cần thiết hoặc làm query sai mục đích.

## 10. Ví dụ service đọc toàn bộ document theo batch

Đây là một service hoàn chỉnh. Mỗi batch được xử lý ngay khi nhận, không gom toàn bộ document vào một list trong bộ nhớ.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.function.Consumer;

import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.client.elc.NativeQueryBuilder;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductExportService {

    private static final int BATCH_SIZE = 500;
    private static final Duration KEEP_ALIVE =
            Duration.ofMinutes(1);

    private final ElasticsearchOperations operations;

    public ProductExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportAll(Consumer<ProductDocument> sink) {
        String pitId = operations.openPointInTime(
                IndexCoordinates.of("products"),
                KEEP_ALIVE
        );

        List<Object> searchAfter = null;

        try {
            Query matchAll = Query.of(q -> q
                    .matchAll(m -> m)
            );

            SortOptions byCreatedAt = SortOptions.of(s -> s
                    .field(f -> f
                            .field("createdAt")
                            .order(SortOrder.Asc)
                    )
            );

            SortOptions byProductId = SortOptions.of(s -> s
                    .field(f -> f
                            .field("productId")
                            .order(SortOrder.Asc)
                    )
            );

            while (true) {
                NativeQueryBuilder builder = NativeQuery.builder()
                        .withQuery(matchAll)
                        .withSort(byCreatedAt, byProductId)
                        .withPageable(PageRequest.of(0, BATCH_SIZE))
                        .withPointInTime(
                                new org.springframework.data.elasticsearch.core.query.Query.PointInTime(
                                        pitId,
                                        KEEP_ALIVE
                                )
                        );

                if (searchAfter != null) {
                    builder.withSearchAfter(searchAfter);
                }

                SearchHits<ProductDocument> page =
                        operations.search(
                                builder.build(),
                                ProductDocument.class
                        );

                String returnedPitId = page.getPointInTimeId();
                if (returnedPitId != null && !returnedPitId.isBlank()) {
                    pitId = returnedPitId;
                }

                if (!page.hasSearchHits()) {
                    break;
                }

                List<SearchHit<ProductDocument>> pageHits =
                        page.getSearchHits();

                for (SearchHit<ProductDocument> hit : pageHits) {
                    sink.accept(hit.getContent());
                }

                SearchHit<ProductDocument> lastHit =
                        pageHits.get(pageHits.size() - 1);

                searchAfter = lastHit.getSortValues();

                if (searchAfter == null || searchAfter.isEmpty()) {
                    throw new IllegalStateException(
                            "Search response did not contain sort values"
                    );
                }

                if (pageHits.size() < BATCH_SIZE) {
                    break;
                }
            }
        } finally {
            if (pitId != null && !pitId.isBlank()) {
                operations.closePointInTime(pitId);
            }
        }
    }
}
~~~

Trong ví dụ:

1. PIT được mở một lần trước vòng lặp.
2. Mỗi request đọc tối đa `BATCH_SIZE` document.
3. Query và sort được giữ nguyên.
4. Trang đầu không có `searchAfter`.
5. Các trang tiếp theo truyền sort values của hit cuối trang trước.
6. PIT ID được cập nhật sau mỗi response.
7. Khi không còn hit hoặc batch cuối có ít hơn `BATCH_SIZE`, vòng lặp dừng.
8. `finally` đóng PIT bằng ID mới nhất, kể cả khi quá trình xử lý ném exception.

`Consumer<ProductDocument>` đại diện cho bước ghi file, gửi message hoặc chuyển đổi dữ liệu. Nếu xử lý một batch có thể kéo dài lâu, hãy cân nhắc thời gian `KEEP_ALIVE` đủ để request kế tiếp được gửi trước khi PIT hết hạn.

Trong hệ thống thực tế, nên ghi log số lượng document đã xử lý, thời gian từng batch và lỗi đóng PIT. Không log PIT ID ra nơi công khai vì đây là định danh của search context.

## 11. Có thể dùng CriteriaQuery thay cho NativeQuery không?

Có. PIT và search_after thuộc Query abstraction của Spring Data, không chỉ dành riêng cho `NativeQuery`.

Ví dụ dùng `CriteriaQuery`:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("status").is("PUBLISHED");

CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 500));
query.setSearchAfter(searchAfter);
query.setPointInTime(
        new org.springframework.data.elasticsearch.core.query.Query.PointInTime(
                pitId,
                keepAlive
        )
);
~~~

`CriteriaQuery` phù hợp khi query chỉ có các điều kiện đơn giản mà Criteria API biểu diễn tốt. `NativeQuery` thuận tiện hơn khi cần typed Elasticsearch Java Client DSL, nhiều sort options hoặc query nâng cao.

Dù chọn query type nào, nguyên tắc vẫn giống nhau:

- Gắn PIT vào từng query.
- Giữ sort ổn định.
- Lấy search-after values từ hit cuối.
- Dùng PIT ID mới nhất.
- Đóng PIT sau khi hoàn tất.

## 12. Dùng REST API để hiểu request thực tế

Spring Data Elasticsearch chuyển các thông tin PIT và search_after thành request Elasticsearch tương ứng.

### Mở PIT

~~~http
POST /products/_pit?keep_alive=1m
~~~

Response trả về một ID:

~~~json
{
  "id": "46ToAw..."
}
~~~

### Search trang đầu

Khi search bằng PIT, endpoint không còn chứa tên index:

~~~http
POST /_search
Content-Type: application/json

{
  "size": 500,
  "pit": {
    "id": "46ToAw...",
    "keep_alive": "1m"
  },
  "query": {
    "match_all": {}
  },
  "sort": [
    {
      "createdAt": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ]
}
~~~

### Search trang tiếp theo

Giả sử response trước trả PIT ID mới và sort values cuối trang:

~~~json
{
  "pit_id": "46ToAw...new",
  "hits": {
    "hits": [
      {
        "_id": "P-1002",
        "sort": [
          "2026-10-20T08:30:00.000Z",
          "P-1002"
        ]
      }
    ]
  }
}
~~~

Request tiếp theo phải dùng PIT ID mới và sort values cuối trang:

~~~http
POST /_search
Content-Type: application/json

{
  "size": 500,
  "pit": {
    "id": "46ToAw...new",
    "keep_alive": "1m"
  },
  "query": {
    "match_all": {}
  },
  "sort": [
    {
      "createdAt": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ],
  "search_after": [
    "2026-10-20T08:30:00.000Z",
    "P-1002"
  ]
}
~~~

Không gửi `index`, `routing` hoặc `preference` trong search request có PIT; các thông tin đó đã được xác định khi mở PIT.

### Đóng PIT

Khi đọc xong:

~~~http
DELETE /_pit
Content-Type: application/json

{
  "id": "46ToAw...new"
}
~~~

Luôn đóng bằng PIT ID mới nhất mà ứng dụng đang giữ. Nếu không đóng, PIT sẽ tự hết hạn theo `keep_alive`, nhưng chờ hết hạn làm search context tiếp tục chiếm tài nguyên trong khoảng thời gian đó.

## 13. Java API Client trực tiếp và Spring Data API

Nếu cần gọi API Elasticsearch trực tiếp, Java API Client cung cấp các thao tác tương ứng:

| Nghiệp vụ | Spring Data Elasticsearch 5.x | Elasticsearch Java API Client |
|---|---|---|
| Mở PIT | `operations.openPointInTime(index, keepAlive)` | `client.openPointInTime(...)` |
| Đính kèm PIT | `withPointInTime(new Query.PointInTime(...))` | `SearchRequest.pit(...)` |
| Truyền con trỏ | `withSearchAfter(List<Object>)` | `SearchRequest.searchAfter(...)` |
| Đọc sort values | `SearchHit.getSortValues()` | `Hit.sort()` |
| Đọc PIT ID mới | `SearchHits.getPointInTimeId()` | `SearchResponse.pitId()` |
| Đóng PIT | `operations.closePointInTime(id)` | `client.closePointInTime(...)` |

Spring Data API có lợi thế là kết quả được chuyển đổi thành entity qua mapping converter của Spring Data. Khi gọi Java Client trực tiếp, response được deserialize theo JSON mapper của client; custom conversion của Spring Data không tự động được áp dụng như khi dùng `ElasticsearchOperations`.

Không trộn các API cũ của `RestHighLevelClient` như `SearchSourceBuilder` hoặc `SearchRequest` cũ với `NativeQuery` và Java API Client. Hãy dùng đúng dependency và package theo phiên bản Spring Data Elasticsearch trong dự án.

## 14. PIT và search_after khác gì Scroll?

Cả Scroll lẫn PIT + search_after đều có thể đọc tập dữ liệu lớn theo từng batch, nhưng cách sử dụng khác nhau.

| Tiêu chí | PIT + search_after | Scroll |
|---|---|---|
| Cách chuyển trang | Dựa trên sort values của hit cuối | Dựa trên scroll ID |
| Snapshot | PIT giữ góc nhìn dữ liệu nhất quán | Scroll context giữ trạng thái tìm kiếm |
| Thứ tự | Cần sort ổn định | Có thể dùng thứ tự phù hợp với tác vụ scan |
| Phân trang sâu | Phù hợp | Phù hợp cho luồng batch truyền thống |
| Request tiếp theo | Gửi PIT ID và search_after | Gửi scroll ID |
| Kết thúc | Đóng PIT | Clear scroll |
| Dùng cho | API phân trang sâu, export cần con trỏ rõ ràng | Batch scan hoặc quy trình đã dùng Scroll API |

Nếu cần phân trang sâu cho giao diện hoặc muốn con trỏ có thể lưu và truyền giữa các request, PIT + search_after thường là lựa chọn phù hợp.

Nếu ứng dụng đã dùng `searchForStream(...)` của Spring Data, cần hiểu rằng API stream này sử dụng Scroll nội bộ theo tài liệu Spring Data. Nó không tự động trở thành PIT + search_after.

Không nên mở nhiều PIT hoặc scroll context không cần thiết cho cùng một tác vụ. Hãy chọn một cơ chế và giải phóng tài nguyên sau khi đọc xong.

## 15. Quản lý keep_alive và tài nguyên

`keep_alive` là thời gian PIT tiếp tục tồn tại nếu không có request gia hạn. Mỗi request search gửi lại PIT cùng `keep_alive` sẽ kéo dài thời gian sống của PIT.

Không cần đặt `keep_alive` đủ dài để quét toàn bộ index. Chỉ cần đủ dài cho khoảng thời gian dự kiến giữa hai request liên tiếp, bao gồm thời gian xử lý batch.

Ví dụ:

- Batch thường hoàn tất trong 2 giây: có thể chọn keep alive khoảng 1 phút.
- Batch có bước xử lý ngoài Elasticsearch kéo dài 30 giây: cần tính khoảng chờ đó vào keep alive.
- Tác vụ có thể bị tạm dừng nhiều phút: cần thiết kế timeout, checkpoint và khả năng khởi động lại rõ ràng.

PIT giữ các segment cũ cần thiết cho snapshot. Vì vậy, mở quá nhiều PIT hoặc giữ chúng quá lâu có thể làm tăng:

- Dung lượng đĩa do segment cũ chưa được giải phóng.
- Số file handle.
- Bộ nhớ heap để theo dõi trạng thái document đã bị xóa/cập nhật.
- Tài nguyên search context trên node.

Hãy đóng PIT ngay khi hoàn tất. `keep_alive` là cơ chế hết hạn dự phòng, không phải lý do để bỏ qua `closePointInTime(...)`.

## 16. Xử lý lỗi và khả năng tiếp tục

### PIT hết hạn

Nếu ứng dụng không gửi request trước khi keep alive hết hạn, PIT có thể không còn hợp lệ. Search request tiếp theo sẽ thất bại.

Không thể lấy lại đúng snapshot cũ chỉ bằng cách mở PIT mới. PIT mới sẽ nhìn thấy trạng thái dữ liệu tại thời điểm mở mới.

Nếu yêu cầu nhất quán tuyệt đối của một lần export, cần báo lỗi và khởi động lại toàn bộ lượt đọc theo PIT mới hoặc dùng chiến lược checkpoint nghiệp vụ có quy tắc đối soát rõ ràng. Không âm thầm mở PIT mới rồi tiếp tục từ sort values cũ vì có thể bỏ sót hoặc lặp document.

### Response trả PIT ID mới

Luôn cập nhật ID mới sau từng search. Nếu ứng dụng chỉ giữ ID lúc mở PIT, các request tiếp theo hoặc thao tác close có thể dùng ID đã cũ.

### Xử lý batch thất bại

Nếu ghi batch ra file, database hoặc hệ thống đích thất bại, cần xác định checkpoint đã được commit hay chưa trước khi chuyển sang trang tiếp theo.

Một cách tổ chức an toàn:

1. Đọc một trang.
2. Ghi và xác nhận xử lý thành công toàn bộ trang.
3. Chỉ sau đó lưu sort values của hit cuối làm checkpoint.
4. Chuyển sang trang kế tiếp.

Nếu lưu checkpoint trước khi ghi xong dữ liệu đích, một lỗi giữa chừng có thể làm mất document khi khởi động lại.

PIT ID có thời hạn và có thể thay đổi qua mỗi response. Nếu checkpoint cần tồn tại lâu hơn PIT, không thể chỉ lưu PIT ID rồi kỳ vọng tiếp tục sau nhiều giờ. Cần thiết kế quy trình mở snapshot mới và đối soát theo khóa nghiệp vụ, thời gian hoặc version dữ liệu.

### Shard failure và timeout

Nếu một search response có shard failure hoặc timeout, không nên coi batch đó là đã đọc đầy đủ. Kiểm tra trạng thái shard, timeout và log lỗi trước khi ghi checkpoint hoàn tất.

Với export cần đầy đủ dữ liệu, nên cấu hình xử lý lỗi theo hướng dừng và báo lỗi thay vì âm thầm chấp nhận kết quả thiếu shard.

## 17. Dùng PIT với alias hoặc nhiều index

PIT có thể được mở trên một index, alias hoặc tập index. Khi mở PIT qua alias, Elasticsearch xác định tập index đích tại thời điểm mở.

Ví dụ:

~~~java
String pitId = operations.openPointInTime(
        IndexCoordinates.of("products"),
        Duration.ofMinutes(1)
);
~~~

Nếu `products` là alias trỏ đến `products-v1` và `products-v2`, PIT sẽ giữ góc nhìn trên tập index được alias phân giải lúc mở.

Trong các request tiếp theo, dùng PIT ID mà không chỉ định lại alias hoặc index. Nếu alias được chuyển sang index khác trong khi quá trình export đang chạy, PIT hiện tại vẫn đại diện cho tập index đã được mở.

Khi tìm qua nhiều index, hãy bảo đảm mapping tương thích với query và sort. Field dùng để sort cần tồn tại và có kiểu dữ liệu phù hợp trên tất cả index được mở trong PIT.

Nếu cùng một business key xuất hiện ở nhiều index, ứng dụng cần quy tắc xử lý trùng lặp riêng. PIT không tự hợp nhất document giữa các index.

## 18. Bảo mật khi cung cấp cursor cho API bên ngoài

Một API có thể chia quá trình đọc thành nhiều request từ client:

1. Client gọi trang đầu.
2. Server mở PIT, tìm trang đầu và tạo cursor.
3. Client gửi cursor để lấy trang kế.
4. Server tiếp tục bằng PIT ID và sort values đã lưu.

Không nên để client tự sửa PIT ID, sort values, tenant filter hoặc query. Cursor nên là token opaque do server tạo, có thể được ký hoặc mã hóa, và chỉ chứa thông tin cần thiết như:

- PIT ID hiện tại.
- Sort values của hit cuối.
- Query/filter fingerprint.
- Page size.
- Thời điểm hết hạn.
- Tenant hoặc phạm vi truy cập đã xác thực.

Server phải kiểm tra cursor thuộc đúng người dùng/tenant và query ban đầu. PIT không phải cơ chế phân quyền; mọi request vẫn phải được xác thực và áp dụng filter quyền truy cập phù hợp.

Không ghi PIT ID hoặc cursor chứa dữ liệu nhạy cảm vào log công khai. Khi cursor hết hạn, API nên trả lỗi có ý nghĩa để client bắt đầu lại phiên tìm kiếm.

## 19. Các lỗi thường gặp

### Chỉ dùng search_after mà không dùng PIT

Các request có thể nhìn thấy những trạng thái index khác nhau sau refresh. Với luồng đọc cần snapshot nhất quán, hãy mở PIT trước.

### Chỉ dùng PIT mà không có sort/search_after

PIT giữ snapshot nhưng không tự tạo con trỏ phân trang sâu. Cần sort và truyền sort values để tiếp tục.

### Không có tie-breaker ổn định

Nếu nhiều document có cùng giá trị sort, thứ tự có thể không xác định. Thêm field duy nhất hoặc dùng tie-breaker phù hợp với PIT.

### Dùng from tăng dần cùng search_after

`search_after` đã là vị trí tiếp tục. Giữ offset ở 0 và dùng page size cố định.

### Quên lấy sort values từ hit cuối

Sort values của hit đầu hoặc hit bất kỳ sẽ làm bỏ qua hoặc đọc lặp một phần dữ liệu. Luôn lấy `getSortValues()` từ hit cuối của batch đã xử lý thành công.

### Quên cập nhật PIT ID

Mỗi response có thể trả PIT ID mới. Giữ ID cũ có thể khiến request tiếp theo hoặc close PIT thất bại.

### Truyền index lại khi search qua PIT

PIT đã lưu index/routing/preference. Search request có PIT không được chỉ định lại các tham số này. Trong Spring Data, dùng overload `operations.search(query, Entity.class)` cho query có PIT.

### Dùng sort field không hỗ trợ sort

Field text hoặc field thiếu doc values có thể không dùng được cho sort. Dùng keyword, numeric, date hoặc multi-field phù hợp.

### Không đóng PIT

PIT hết hạn tự động nhưng vẫn giữ tài nguyên trong thời gian sống. Đóng PIT trong `finally` khi hoàn tất hoặc gặp lỗi.

### Gia hạn quá ngắn

Nếu xử lý batch mất nhiều thời gian hơn keep alive, PIT có thể hết hạn trước request kế tiếp. Chọn keep alive theo thời gian xử lý thực tế và gia hạn ở mỗi search.

### Tự mở PIT mới rồi dùng cursor cũ

PIT mới có snapshot khác. Sort values từ snapshot cũ không bảo đảm tiếp tục chính xác trên snapshot mới. Nếu PIT hết hạn, cần khởi động lại hoặc đối soát theo thiết kế nghiệp vụ.

## 20. Quy trình triển khai

Khi xây dựng chức năng export hoặc phân trang sâu:

1. Xác nhận phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client đang dùng.
2. Chọn index/alias và xác thực quyền đọc.
3. Kiểm tra mapping của các field dùng trong query và sort.
4. Chọn sort ổn định, có tie-breaker duy nhất.
5. Mở PIT bằng `operations.openPointInTime(...)`.
6. Tạo query với `Query.PointInTime`, sort và page size.
7. Search trang đầu mà chưa truyền search_after.
8. Xử lý batch và lấy sort values từ hit cuối.
9. Cập nhật PIT ID bằng `SearchHits.getPointInTimeId()`.
10. Tạo query kế tiếp với `withSearchAfter(...)`.
11. Lặp đến khi không còn hit.
12. Đóng PIT bằng ID mới nhất trong `finally`.
13. Ghi checkpoint sau khi batch đã được xử lý thành công.
14. Theo dõi timeout, shard failures, thời gian batch và số PIT đang mở.

## Tài liệu tham khảo

- [Spring Data Elasticsearch 5.4 — SearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/SearchOperations.html)
- [Spring Data Elasticsearch 5.4 — Query API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch 5.4 — NativeQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch — PIT API guide](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html#point-in-time-pit-api)
- [Elasticsearch — Point in time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Elasticsearch — Paginate search results with search_after](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)

## Kết luận

PIT giữ góc nhìn dữ liệu nhất quán trong khi `search_after` cho phép chuyển từ batch này sang batch tiếp theo bằng sort values của hit cuối. Với Spring Data Elasticsearch 5.x, mở PIT bằng `ElasticsearchOperations.openPointInTime(...)`, gắn PIT bằng `withPointInTime(new Query.PointInTime(...))`, truyền con trỏ bằng `withSearchAfter(...)`, cập nhật ID qua `SearchHits.getPointInTimeId()` và đóng PIT bằng `closePointInTime(...)`. Giữ nguyên query/sort giữa các trang, chọn tie-breaker ổn định, xử lý batch trước khi lưu checkpoint và luôn giải phóng PIT sau khi hoàn tất.
