# Total hits, total hits relation và ngưỡng đếm chính xác

## 1. Total hits là gì?

Khi Elasticsearch thực hiện tìm kiếm, response có thể chứa hai loại thông tin khác nhau:

- **Các hit được trả về:** những document nằm trong trang hiện tại, thường nằm trong `hits.hits`.
- **Total hits:** tổng số document khớp với điều kiện tìm kiếm, được biểu diễn trong `hits.total` khi request có theo dõi số lượng này.

Ví dụ, người dùng tìm kiếm sản phẩm thuộc danh mục `audio`. Có 2.450 document khớp, nhưng giao diện chỉ yêu cầu hiển thị 20 document đầu tiên.

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "from": 0,
  "size": 20
}
~~~

Response có thể có cấu trúc:

~~~json
{
  "hits": {
    "total": {
      "value": 2450,
      "relation": "eq"
    },
    "hits": [
      {
        "_id": "p-001",
        "_source": {
          "name": "Wireless Headphones",
          "category": "audio"
        }
      }
    ]
  }
}
~~~

Trong đó:

- `hits.hits` chứa các document được trả về cho trang hiện tại.
- `hits.total.value` cho biết tổng số document khớp hoặc một cận dưới của số đó.
- `hits.total.relation` cho biết `value` là con số chính xác hay chỉ là cận dưới.

`size: 20` chỉ giới hạn số document trả về trong trang. Nó không có nghĩa tổng số document khớp chỉ là 20.

Total hits thường được dùng để hiển thị số kết quả, tính số trang, xác định người dùng có thể tiếp tục xem dữ liệu hay không và cung cấp thông tin tổng quan cho màn hình tìm kiếm.

## 2. Total hits relation: eq và gte

Elasticsearch không phải lúc nào cũng đếm chính xác toàn bộ document khớp. Để cân bằng độ chính xác và tốc độ, response đi kèm một trường `relation`.

Hai giá trị thường gặp:

| Relation | Ý nghĩa | Cách hiểu `value` |
|---|---|---|
| `eq` | Equal, số lượng chính xác | Có đúng `value` document khớp |
| `gte` | Greater than or equal, cận dưới | Có ít nhất `value` document khớp |

### relation = eq

Ví dụ:

~~~json
{
  "hits": {
    "total": {
      "value": 2450,
      "relation": "eq"
    }
  }
}
~~~

Có chính xác 2.450 document khớp truy vấn.

Giao diện có thể hiển thị:

~~~text
2.450 kết quả
~~~

### relation = gte

Ví dụ:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    }
  }
}
~~~

Response cho biết có ít nhất 10.000 document khớp. Tổng thực tế có thể là 10.001, 50.000 hoặc lớn hơn nữa.

Không được hiển thị `10.000 kết quả` như một con số chính xác trong trường hợp này. Có thể hiển thị:

~~~text
Ít nhất 10.000 kết quả
~~~

Hoặc nếu giao diện không cần con số cụ thể:

~~~text
10.000+ kết quả
~~~

### Vì sao phải đọc cả value và relation?

Chỉ đọc `value` là chưa đủ. Ví dụ hai response sau có cùng `value` nhưng ý nghĩa khác nhau:

~~~json
{
  "value": 5000,
  "relation": "eq"
}
~~~

~~~json
{
  "value": 5000,
  "relation": "gte"
}
~~~

Response đầu xác nhận chính xác 5.000 kết quả. Response thứ hai chỉ xác nhận có ít nhất 5.000 kết quả. Nếu ứng dụng bỏ qua `relation`, giao diện có thể thông báo sai số lượng.

## 3. Ngưỡng mặc định 10.000

Mặc định, Elasticsearch theo dõi total hits chính xác đến ngưỡng 10.000. Đây là một lựa chọn cân bằng giữa chi phí đếm và tốc độ tìm kiếm.

Quy tắc tổng quát:

- Nếu số document khớp không vượt quá 10.000, Elasticsearch có thể trả về số chính xác với `relation: "eq"`.
- Nếu số document khớp vượt quá ngưỡng, Elasticsearch có thể dừng việc đếm chính xác tại ngưỡng và trả về `value: 10000` cùng `relation: "gte"`.

Ví dụ:

| Số document thực tế khớp | Ngưỡng theo dõi mặc định | Response total |
|---:|---:|---|
| 125 | 10.000 | `value: 125, relation: eq` |
| 8.500 | 10.000 | `value: 8500, relation: eq` |
| 10.000 | 10.000 | `value: 10000, relation: eq` |
| 12.000 | 10.000 | `value: 10000, relation: gte` |
| 2.000.000 | 10.000 | `value: 10000, relation: gte` |

Ngưỡng này không phải giới hạn số document được trả về. Nó cũng không phải giới hạn số trang. Nó chỉ quyết định mức độ Elasticsearch theo dõi tổng số hit chính xác.

Nếu ứng dụng chỉ cần biết có nhiều hơn 10.000 kết quả hay không, ngưỡng mặc định thường đã đủ. Nếu giao diện bắt buộc hiển thị con số chính xác, cần cấu hình theo dõi total hits chính xác.

## 4. track_total_hits điều khiển việc đếm như thế nào?

Tham số `track_total_hits` trong Search API cho phép ứng dụng quyết định cách Elasticsearch theo dõi số lượng document khớp.

Có ba cách cấu hình chính:

| Giá trị | Hành vi | Response total |
|---|---|---|
| `true` | Theo dõi số lượng chính xác trên toàn bộ tập kết quả | `relation: "eq"` nếu request hoàn tất đầy đủ |
| `false` | Không theo dõi tổng số hit | Không có `hits.total` |
| Số nguyên `N` | Theo dõi chính xác đến ngưỡng N | `eq` nếu tổng không vượt N; `gte` nếu vượt N |

### track_total_hits = true

~~~http
GET /products/_search
{
  "track_total_hits": true,
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Elasticsearch đếm chính xác tổng số document khớp, kể cả khi số lượng vượt 10.000.

Ví dụ response:

~~~json
{
  "hits": {
    "total": {
      "value": 125430,
      "relation": "eq"
    },
    "hits": []
  }
}
~~~

Có chính xác 125.430 document khớp. Danh sách `hits` trong ví dụ được rút gọn để tập trung vào total hits.

### track_total_hits = false

~~~http
GET /products/_search
{
  "track_total_hits": false,
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Elasticsearch không trả về tổng số document khớp trong `hits.total`. Response vẫn có thể chứa các document trong trang hiện tại.

Cách này phù hợp khi giao diện chỉ cần hiển thị danh sách kết quả và không cần số lượng tổng.

Trong Spring Data Elasticsearch, quan hệ total hits tương ứng có thể được biểu diễn bằng `TotalHitsRelation.OFF`. Ứng dụng cần nhận biết trạng thái này và không sử dụng một giá trị số như thể đó là tổng số chính xác.

### track_total_hits = N

Có thể truyền một số nguyên để đặt ngưỡng đếm:

~~~http
GET /products/_search
{
  "track_total_hits": 5000,
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Elasticsearch theo dõi chính xác đến 5.000 hit:

- Nếu có 3.200 document khớp, response trả `value: 3200` và `relation: "eq"`.
- Nếu có 8.000 document khớp, response có thể trả `value: 5000` và `relation: "gte"`.

Đây là lựa chọn hữu ích khi ứng dụng cần con số chính xác trong phạm vi nhỏ, nhưng không cần đếm đến hàng trăm nghìn hoặc hàng triệu document.

## 5. Vì sao đếm chính xác có thể tốn chi phí?

Một truy vấn tìm kiếm và một thao tác đếm chính xác có thể có yêu cầu xử lý khác nhau.

Elasticsearch có thể tối ưu việc tìm và xếp hạng các document phù hợp mà không cần xác định chính xác toàn bộ số document khớp. Khi bắt buộc đếm chính xác, hệ thống phải tiếp tục theo dõi số lượng match trên các shard liên quan.

Việc bật `track_total_hits: true` có thể làm giảm hiệu quả một số tối ưu hóa tìm kiếm, bao gồm Max WAND. Vì vậy, exact count có thể làm tăng CPU, thời gian xử lý và độ trễ, đặc biệt với truy vấn khớp nhiều document.

So sánh cách sử dụng:

| Nhu cầu giao diện | Cấu hình phù hợp |
|---|---|
| Chỉ hiển thị các document của trang hiện tại | `track_total_hits: false` |
| Hiển thị số kết quả đến một ngưỡng, ví dụ 5.000+ | `track_total_hits: 5000` |
| Hiển thị chính xác tổng số kết quả | `track_total_hits: true` |
| Chỉ cần biết còn kết quả để tải thêm | Có thể dùng phân trang và kiểm tra trang tiếp theo, không nhất thiết cần exact count |

Không nên bật exact count mặc định cho mọi truy vấn chỉ vì giao diện có chỗ hiển thị tổng số. Hãy xác định con số đó có thực sự cần chính xác hay không.

## 6. Phân biệt ngưỡng total hits và max_result_window

Hai cấu hình này thường bị nhầm lẫn vì mặc định thường cùng có giá trị 10.000, nhưng chúng kiểm soát hai vấn đề khác nhau.

| Cấu hình | Kiểm soát điều gì? | Ảnh hưởng |
|---|---|---|
| `track_total_hits` | Mức độ đếm chính xác tổng document khớp | `eq` hay `gte` trong total hits |
| `index.max_result_window` | Độ sâu phân trang bằng `from` và `size` | Giới hạn vị trí document có thể yêu cầu trong một trang |

Ví dụ:

~~~http
GET /products/_search
{
  "track_total_hits": true,
  "from": 0,
  "size": 20,
  "query": {
    "match_all": {}
  }
}
~~~

Truy vấn có thể đếm chính xác hàng trăm nghìn document nhưng chỉ trả về 20 document đầu tiên.

Ngược lại, nếu tăng `index.max_result_window`, điều đó không tự động làm total hits được đếm chính xác. Muốn thay đổi cách đếm, phải cấu hình `track_total_hits`.

Nếu cần duyệt sâu qua nhiều trang, hãy xem xét `search_after` và Point in Time thay vì tăng result window một cách tùy tiện. Đây là vấn đề phân trang, độc lập với độ chính xác của total hits.

## 7. Cấu hình track_total_hits trong Spring Data Elasticsearch

Spring Data Elasticsearch biểu diễn các tùy chọn tìm kiếm thông qua interface `Query`. Các implementation như `CriteriaQuery`, `StringQuery` và `NativeQuery` đều có thể được truyền cho `ElasticsearchOperations`.

Trong API Spring Data Elasticsearch hiện hành:

- `setTrackTotalHits(Boolean)` đặt chế độ bật hoặc tắt theo dõi tổng số hit.
- `setTrackTotalHitsUpTo(Integer)` đặt ngưỡng theo dõi tối đa.
- `setTrackTotalHitsUpTo` chỉ có hiệu lực khi `getTrackTotalHits()` đang là `null`.

Vì vậy, khi muốn dùng ngưỡng số nguyên, hãy đặt `setTrackTotalHitsUpTo(N)` và không ghi đè chế độ bằng `setTrackTotalHits(true/false)`.

### Đếm chính xác

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

CriteriaQuery query = new CriteriaQuery(
    new Criteria("category").is("audio")
);

query.setTrackTotalHits(true);

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

`setTrackTotalHits(true)` yêu cầu Elasticsearch theo dõi tổng số chính xác.

### Không cần tổng số

~~~java
CriteriaQuery query = new CriteriaQuery(
    new Criteria("category").is("audio")
);

query.setTrackTotalHits(false);

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

Khi tắt tracking, ứng dụng vẫn nhận các hit trong trang nhưng không nên dựa vào total hits để hiển thị tổng số.

### Chỉ đếm chính xác đến ngưỡng

~~~java
CriteriaQuery query = new CriteriaQuery(
    new Criteria("category").is("audio")
);

query.setTrackTotalHitsUpTo(5_000);

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

Trong ví dụ này, query giữ chế độ `trackTotalHits` ở trạng thái chưa chỉ định và đặt ngưỡng 5.000. Đây là cách dùng tương ứng với giá trị số nguyên của Search API.

Các phương thức trên thuộc API Spring Data Elasticsearch 4.0/4.1 trở lên. Nếu dự án dùng phiên bản cũ hơn, hãy đối chiếu API của dependency thực tế trước khi áp dụng.

## 8. Đọc total hits relation trong SearchHits

Spring Data Elasticsearch không chỉ cung cấp số lượng qua `SearchHits.getTotalHits()` mà còn cung cấp quan hệ qua `SearchHits.getTotalHitsRelation()`.

Enum `TotalHitsRelation` có các giá trị:

| Enum | Ý nghĩa |
|---|---|
| `EQUAL_TO` | Total hits chính xác, tương ứng `eq` |
| `GREATER_THAN_OR_EQUAL_TO` | Total hits là cận dưới, tương ứng `gte` |
| `OFF` | Không theo dõi total hits |

Ví dụ đọc kết quả:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.TotalHitsRelation;

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);

long total = hits.getTotalHits();
TotalHitsRelation relation = hits.getTotalHitsRelation();

switch (relation) {
    case EQUAL_TO ->
        System.out.println("Chính xác " + total + " kết quả");

    case GREATER_THAN_OR_EQUAL_TO ->
        System.out.println("Ít nhất " + total + " kết quả");

    case OFF ->
        System.out.println("Không theo dõi tổng số kết quả");
}
~~~

Không nên chỉ gọi `getTotalHits()` rồi hiển thị kết quả như một con số chính xác. Hãy kiểm tra `getTotalHitsRelation()` trước.

Nếu hệ thống có nhiều phiên bản Spring Data Elasticsearch, cần xác nhận enum và API tương ứng. `TotalHitsRelation` được cung cấp trong Spring Data Elasticsearch từ phiên bản 4.0; giá trị `OFF` có từ 4.1.

## 9. Xây dựng phản hồi API cho giao diện

Một API tìm kiếm có thể trả thông tin tổng số cùng quan hệ để frontend hiển thị chính xác:

~~~java
public record SearchResult<T>(
    List<T> items,
    long totalHits,
    String totalHitsRelation
) {
}
~~~

Ví dụ chuyển đổi từ `SearchHits`:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;

public SearchResult<Product> toSearchResult(SearchHits<Product> hits) {

    List<Product> items = hits.getSearchHits()
        .stream()
        .map(SearchHit::getContent)
        .toList();

    return new SearchResult<>(
        items,
        hits.getTotalHits(),
        hits.getTotalHitsRelation().name()
    );
}
~~~

Response JSON có thể là:

~~~json
{
  "items": [
    {
      "id": "p-001",
      "name": "Wireless Headphones"
    }
  ],
  "totalHits": 10000,
  "totalHitsRelation": "GREATER_THAN_OR_EQUAL_TO"
}
~~~

Frontend có thể dựa vào relation để hiển thị:

~~~text
EQUAL_TO                  → 10.000 kết quả
GREATER_THAN_OR_EQUAL_TO  → Ít nhất 10.000 kết quả
OFF                       → Không hiển thị tổng số
~~~

Một cách khác là chuyển relation thành chuỗi hiển thị ngay ở backend, chẳng hạn `exact`, `at_least` hoặc `not_tracked`. Nếu làm vậy, hãy giữ semantics rõ ràng trong hợp đồng API để frontend không hiểu nhầm.

Đối với API công khai, nên tránh trả một trường `totalHits` đơn lẻ mà không có thông tin relation nếu hệ thống có thể trả về số đếm giới hạn.

## 10. Khi nào nên dùng Count API?

Nếu nghiệp vụ chỉ cần biết số document khớp mà không cần lấy document hoặc metadata tìm kiếm, có thể cân nhắc Elasticsearch Count API.

Ví dụ:

~~~http
GET /products/_count
{
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

Response:

~~~json
{
  "count": 2450,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  }
}
~~~

Count API trả về số document khớp với query. Đây là một request riêng, hữu ích khi chỉ cần đếm mà không cần lấy danh sách hit.

Cần phân biệt:

- Search API trả về document cùng metadata tìm kiếm; total hits có thể chính xác, giới hạn hoặc tắt theo `track_total_hits`.
- Count API chỉ tập trung vào việc đếm document khớp.
- Aggregation `value_count` đếm số giá trị của một field, không đồng nghĩa số document khớp.
- Aggregation `cardinality` ước lượng số giá trị duy nhất và có thể không chính xác tuyệt đối.

Không nên dùng aggregation hoặc số phần tử trong trang hiện tại để thay thế total hits nếu mục tiêu là đếm số document phù hợp với query.

## 11. Total hits trong các tình huống phân trang

Giả sử có 18.000 document khớp và trang có kích thước 20.

Nếu dùng ngưỡng mặc định 10.000, response có thể cho biết:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    },
    "hits": [
      "... 20 documents on current page ..."
    ]
  }
}
~~~

Có nghĩa:

- Trang hiện tại chứa tối đa 20 document.
- Tổng số document khớp ít nhất là 10.000.
- Không thể suy ra tổng số trang chính xác từ con số 10.000.
- Không thể kết luận chỉ có 500 trang, vì tổng thực tế có thể lớn hơn nhiều.

Nếu giao diện dùng `Page<T>` để hiển thị số trang, cần cân nhắc semantics của total hits. Khi count bị giới hạn, tổng trang suy ra từ giá trị cận dưới chỉ là ước lượng hoặc giới hạn dưới, không phải tổng trang chính xác.

Nếu giao diện chỉ cần nút `Xem thêm`, có thể lấy trang tiếp theo theo `Pageable` hoặc dùng `search_after`. Không nhất thiết phải đếm chính xác toàn bộ index.

Với phân trang sâu, `from` và `size` có giới hạn riêng. `search_after` giúp tiếp tục từ sort values của hit cuối cùng trang trước, nhưng nó không tự làm cho total hits chính xác. Phân trang và đếm tổng số là hai quyết định riêng.

## 12. Những lưu ý về tính chính xác của số đếm

Total hits relation mô tả mức độ chính xác của bộ đếm trong response. Khi xử lý kết quả, cần lưu ý thêm một số điều:

**Không nhầm total hits với số hit trong trang.** Một trang có 20 phần tử không có nghĩa query chỉ khớp 20 document.

**Không coi gte là eq.** `gte` có nghĩa ít nhất bằng giá trị, không phải bằng đúng giá trị.

**Không coi OFF là 0 kết quả.** Khi tracking bị tắt, total count không được cung cấp. Điều đó không có nghĩa không có document khớp.

**Không dùng total hits bị giới hạn để tính số trang chính xác.** Nếu relation là `gte`, số trang suy ra từ value chỉ là cận dưới.

**Kiểm tra trạng thái request.** Khi response báo timeout hoặc shard failure, kết quả tìm kiếm có thể chưa đầy đủ. Nếu giao diện cần con số đáng tin cậy, hãy xem cả trạng thái thực thi và thông tin shard cùng với total hits.

**Không tăng ngưỡng một cách tùy tiện.** Ngưỡng lớn hơn có thể làm số đếm chính xác hơn nhưng cũng tăng chi phí xử lý.

**Không dùng count cho mọi thao tác.** Nếu giao diện chỉ cần biết còn trang sau, hãy cân nhắc cơ chế phân trang thay vì yêu cầu exact count.

## 13. Quy trình lựa chọn ngưỡng đếm

Có thể xác định cấu hình dựa trên yêu cầu sản phẩm:

1. Xác định giao diện có thật sự cần hiển thị tổng số kết quả hay không.
2. Nếu không cần, đặt `track_total_hits: false`.
3. Nếu chỉ cần hiển thị đến một ngưỡng, chọn `track_total_hits: N`.
4. Nếu cần tổng số chính xác cho nghiệp vụ, đặt `track_total_hits: true`.
5. Trong Spring Data, dùng `setTrackTotalHits` hoặc `setTrackTotalHitsUpTo` theo đúng chế độ.
6. Đọc cả `getTotalHits()` và `getTotalHitsRelation()` từ `SearchHits`.
7. Hiển thị `eq` như con số chính xác, `gte` như cận dưới và `OFF` như không có số đếm.
8. Đánh giá latency và tài nguyên cluster trên truy vấn có nhiều kết quả.
9. Kiểm tra timeout và shard failures trước khi dùng total hits cho báo cáo quan trọng.

## Kết luận

Total hits cho biết tổng số document khớp với query, còn `hits.hits` chỉ chứa các document được trả về trong trang hiện tại. Elasticsearch dùng `relation` để thông báo mức độ chính xác của `value`: `eq` là số đếm chính xác, `gte` là cận dưới và khi tracking bị tắt thì không có total count.

Mặc định, Elasticsearch theo dõi chính xác đến 10.000 hit. Có thể đặt `track_total_hits: true` để đếm chính xác toàn bộ, `false` để bỏ qua total count hoặc một số nguyên để đặt ngưỡng tùy chỉnh. Đếm chính xác có thể làm tăng chi phí tìm kiếm, vì vậy nên chọn theo nhu cầu giao diện và nghiệp vụ.

Trong Spring Data Elasticsearch, cấu hình bằng `Query.setTrackTotalHits` hoặc `Query.setTrackTotalHitsUpTo`, sau đó đọc `SearchHits.getTotalHits()` cùng `SearchHits.getTotalHitsRelation()`. Luôn giữ thông tin relation khi chuyển kết quả sang API để frontend phân biệt số lượng chính xác, cận dưới và trạng thái không theo dõi.

## Tài liệu tham khảo

- [Elasticsearch — The Search API: Track total hits](https://www.elastic.co/docs/solutions/search/the-search-api#track-total-hits)
- [Elasticsearch — Search API reference](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch — Count API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-count)
- [Spring Data Elasticsearch — Query API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — TotalHitsRelation API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/TotalHitsRelation.html)
