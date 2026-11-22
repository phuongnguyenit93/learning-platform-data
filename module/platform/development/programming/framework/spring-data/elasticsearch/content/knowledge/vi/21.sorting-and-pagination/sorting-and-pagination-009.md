# `track_total_hits` và đánh đổi khi tính tổng số kết quả

Khi tìm kiếm bằng Elasticsearch, ứng dụng thường cần hai thông tin khác nhau: danh sách document cần hiển thị và tổng số document thỏa điều kiện tìm kiếm. Danh sách kết quả phục vụ trang hiện tại; tổng số hit phục vụ thông báo như “Có 12.450 kết quả”, tính tổng số trang hoặc quyết định có trang tiếp theo.

Tính chính xác tổng số document có thể tốn tài nguyên, đặc biệt khi query khớp với hàng trăm nghìn hoặc hàng triệu document. Elasticsearch cung cấp tham số `track_total_hits` để điều chỉnh mức độ đếm. Ứng dụng có thể yêu cầu đếm chính xác, chỉ đếm đến một ngưỡng hoặc tắt việc đếm hoàn toàn.

Trong Elasticsearch, mặc định tổng số hit được theo dõi chính xác đến 10.000. Khi số document khớp vượt ngưỡng, response có thể chỉ báo một lower bound, ví dụ “ít nhất 10.000 kết quả”. Đây là một đánh đổi có chủ đích để search có thể tập trung lấy top kết quả mà không phải luôn đếm hết mọi document phù hợp.

## 1. Phân biệt số hit trả về và tổng số hit

Trong Search API, `from` và `size` quyết định cửa sổ kết quả được trả về. `track_total_hits` quyết định Elasticsearch theo dõi tổng số document khớp query chính xác đến mức nào.

Ví dụ:

```http
GET /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Request yêu cầu tối đa 20 document đầu tiên. Nếu có 250.000 sản phẩm đang hoạt động, `hits.hits` vẫn chỉ chứa tối đa 20 phần tử, còn `hits.total` mô tả số document thỏa query theo chế độ tracking.

| Thành phần | Ý nghĩa |
|---|---|
| `from` | Vị trí bắt đầu trong danh sách đã sắp xếp. |
| `size` | Số document tối đa trả về trong response. |
| `track_total_hits` | Mức độ chính xác cần theo dõi cho tổng số document khớp query. |
| `hits.hits` | Các document thực tế được trả về cho trang hiện tại. |
| `hits.total` | Thông tin về tổng số document khớp, nếu được yêu cầu theo dõi. |

`size: 20` không có nghĩa tổng số kết quả là 20. Ngược lại, `track_total_hits: true` cũng không khiến Elasticsearch trả về tất cả document; nó chỉ yêu cầu đếm tổng số hit chính xác hơn.

## 2. Cấu trúc `hits.total`

Trong response Search API, tổng số hit thường có dạng object:

```json
{
  "hits": {
    "total": {
      "value": 250000,
      "relation": "eq"
    },
    "hits": [
      {
        "_id": "P-100",
        "_source": {
          "name": "Mechanical Keyboard"
        }
      }
    ]
  }
}
```

Hai thuộc tính quan trọng:

- `value`: số hit được báo cáo.
- `relation`: cho biết `value` là số chính xác hay chỉ là cận dưới.

`relation` có hai giá trị chính:

| Giá trị | Ý nghĩa | Cách diễn giải |
|---|---|---|
| `eq` | Exact count | `value` là tổng số document khớp chính xác. |
| `gte` | Greater than or equal | Có ít nhất `value` document khớp; số thực tế có thể lớn hơn. |

Ví dụ response:

```json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    },
    "hits": []
  }
}
```

Response này có nghĩa là có ít nhất 10.000 document khớp, không khẳng định tổng số chính xác bằng 10.000. Có thể thực tế có 12.000, 250.000 hoặc nhiều hơn.

Nếu `track_total_hits` bị tắt, Elasticsearch không trả object `hits.total`. Khi đó không được hiểu sự vắng mặt của `hits.total` là không có document phù hợp. Danh sách `hits.hits` vẫn có thể chứa kết quả.

## 3. Các chế độ của `track_total_hits`

Elasticsearch chấp nhận ba kiểu giá trị cho `track_total_hits`: boolean `true`, boolean `false` hoặc một số nguyên dương biểu thị ngưỡng đếm.

### 3.1. Không khai báo: mặc định 10.000

Nếu request không chỉ định `track_total_hits`, Elasticsearch mặc định theo dõi tổng số hit chính xác đến 10.000:

```json
GET /products/_search
{
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Nếu có 4.200 document khớp, response có thể trả:

```json
"total": {
  "value": 4200,
  "relation": "eq"
}
```

Nếu có 250.000 document khớp, response có thể trả:

```json
"total": {
  "value": 10000,
  "relation": "gte"
}
```

Ứng dụng cần đọc cả `value` và `relation`, không chỉ lấy con số `value`.

### 3.2. `track_total_hits: true`: đếm chính xác

Khi đặt `true`, Elasticsearch phải theo dõi chính xác toàn bộ số document khớp query:

```json
GET /products/_search
{
  "size": 20,
  "track_total_hits": true,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Response sẽ có `relation: "eq"` nếu request hoàn tất bình thường:

```json
"total": {
  "value": 250000,
  "relation": "eq"
}
```

Chế độ này phù hợp khi giao diện hoặc nghiệp vụ thật sự cần tổng số chính xác, ví dụ:

- Hiển thị “Tổng cộng 250.000 kết quả”.
- Tính chính xác tổng số trang.
- Xuất báo cáo cần số lượng bản ghi chính xác.
- Đối soát số document khớp điều kiện.

Đổi lại, Elasticsearch có thể phải làm thêm công việc để đếm mọi document khớp. Với query có số lượng match lớn, điều này có thể làm tăng thời gian thực thi và tài nguyên sử dụng.

### 3.3. `track_total_hits: false`: không đếm tổng số

Nếu ứng dụng chỉ cần danh sách kết quả, không cần tổng số, có thể tắt việc tracking:

```json
GET /products/_search
{
  "size": 20,
  "track_total_hits": false,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Elasticsearch vẫn tìm và trả tối đa 20 document phù hợp, nhưng response không chứa `hits.total`.

Chế độ này phù hợp với:

- Infinite scroll chỉ cần tải thêm kết quả.
- Trang gợi ý hoặc danh sách “có thể bạn quan tâm”.
- API chỉ trả các item đầu tiên mà không hiển thị tổng số.
- Luồng xử lý chỉ cần biết một số kết quả đầu để tiếp tục bước nghiệp vụ.

Không dùng `track_total_hits: false` nếu phía client đang phụ thuộc vào tổng số chính xác để hiển thị số trang hoặc thông báo tổng kết quả.

### 3.4. `track_total_hits: N`: đếm đến một ngưỡng

Có thể truyền một số nguyên để yêu cầu Elasticsearch đếm chính xác đến ngưỡng đó:

```json
GET /products/_search
{
  "size": 20,
  "track_total_hits": 2000,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Nếu số document khớp không vượt 2.000, response trả số chính xác với `relation: "eq"`. Nếu số document lớn hơn ngưỡng, response báo lower bound với `relation: "gte"`.

Ví dụ:

| Số document thực tế | Ngưỡng | `hits.total.value` | `relation` |
|---:|---:|---:|---|
| 320 | 2.000 | 320 | `eq` |
| 2.000 | 2.000 | 2.000 | `eq` |
| 8.500 | 2.000 | 2.000 | `gte` |
| 250.000 | 2.000 | 2.000 | `gte` |

Đây là lựa chọn cân bằng cho giao diện cần biết tổng số ở mức vừa phải nhưng không cần đếm chính xác khi kết quả quá lớn. Ví dụ giao diện chỉ cần hiển thị “2.000+ kết quả” là đủ.

## 4. Đánh đổi hiệu năng khi đếm tổng số

Elasticsearch thường tối ưu để tìm top document phù hợp nhất. Khi query match rất nhiều document, việc đếm chính xác tất cả match có thể buộc hệ thống thực hiện thêm công việc mà giao diện không thực sự cần.

Với truy vấn xếp hạng theo relevance, Elasticsearch có thể sử dụng các tối ưu như Max WAND để bỏ qua những document không thể lọt vào top kết quả. Khi yêu cầu đếm tổng số chính xác, một số tối ưu này không thể được sử dụng theo cách tương tự, khiến query có thể chậm hơn.

Mức chênh lệch phụ thuộc vào:

- Số lượng document khớp query.
- Độ phức tạp của query và số shard.
- Sort theo `_score` hay sort theo field.
- Số lượng clause và cấu trúc bool/nested query.
- Có aggregation hoặc các tính năng khác yêu cầu duyệt nhiều document hay không.
- Tài nguyên cluster, cache và tải đồng thời.

Không có một tỷ lệ cố định để nói `track_total_hits: true` chậm hơn bao nhiêu lần. Cần đo bằng query và dữ liệu gần production.

### So sánh ba lựa chọn

| Cấu hình | Độ chính xác tổng số | Chi phí đếm | Phù hợp |
|---|---|---|---|
| `false` | Không có tổng số | Thấp nhất cho việc tracking | Không hiển thị tổng số. |
| Số nguyên `N` | Chính xác đến N; vượt N chỉ biết `>= N` | Có giới hạn | Chỉ cần ngưỡng hoặc nhãn “N+”. |
| `true` | Chính xác toàn bộ | Có thể cao khi match nhiều | Bắt buộc hiển thị/đối soát số chính xác. |

Thông thường, nếu sản phẩm không cần số chính xác, không nên bật `true` cho mọi request chỉ vì muốn có một con số ở góc giao diện.

## 5. `track_total_hits` không ảnh hưởng số document trong trang

Một hiểu lầm thường gặp là cho rằng đặt `track_total_hits: 100` sẽ chỉ trả tối đa 100 document. Điều đó không đúng.

Ví dụ:

```json
GET /products/_search
{
  "from": 20,
  "size": 50,
  "track_total_hits": 100,
  "query": {
    "match_all": {}
  }
}
```

Request vẫn có thể trả 50 document bắt đầu từ offset 20. Giá trị 100 chỉ là ngưỡng theo dõi tổng số hit. Nó không thay đổi `size`, không giới hạn tổng dữ liệu trong index và không giới hạn số document có thể khớp.

Ngược lại, `size: 0` chỉ yêu cầu không trả document trong `hits.hits`; nó không tự động tắt việc đếm tổng số. Nếu muốn chỉ đếm mà không lấy document, có thể dùng `size: 0` cùng chế độ tracking thích hợp.

## 6. Cấu hình `track_total_hits` trong Spring Data Elasticsearch

Spring Data Elasticsearch biểu diễn tùy chọn này trên abstraction `Query`. Vì vậy có thể cấu hình trên `CriteriaQuery`, `NativeQuery` hoặc query object khác có triển khai `Query`.

Hai method cần biết:

- `setTrackTotalHits(Boolean)`: bật hoặc tắt tracking.
- `setTrackTotalHitsUpTo(Integer)`: đặt ngưỡng tracking.

Theo API Spring Data Elasticsearch, `setTrackTotalHits` có từ phiên bản 4.0 và `setTrackTotalHitsUpTo` có từ 4.1. Tham số ngưỡng chỉ có hiệu lực khi `getTrackTotalHits()` là `null`; nếu đã đặt boolean `true` hoặc `false`, boolean sẽ quyết định chế độ.

### 6.1. Yêu cầu đếm chính xác

Ví dụ với `NativeQuery`:

```java
NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();

query.setTrackTotalHits(true);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Query vẫn chỉ trả tối đa 20 document trong trang, nhưng yêu cầu theo dõi tổng số khớp chính xác.

### 6.2. Tắt tracking

```java
NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();

query.setTrackTotalHits(false);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Khi tracking tắt, không dùng `hits.getTotalHits()` để kết luận số document khớp. Hãy kiểm tra relation hoặc thiết kế response không cần tổng số.

### 6.3. Đếm chính xác đến ngưỡng

```java
NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();

query.setTrackTotalHitsUpTo(2000);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Không đặt `setTrackTotalHits(true)` hoặc `false` trên cùng query nếu muốn ngưỡng `2000` có hiệu lực, vì boolean có ưu tiên. Nếu query đã được cấu hình ở nơi khác, hãy kiểm tra giá trị `getTrackTotalHits()` trước khi gửi request.

### 6.4. Dùng CriteriaQuery

Tùy chọn này không chỉ dành riêng cho NativeQuery. Ví dụ:

```java
Criteria criteria = new Criteria("status").is("ACTIVE");
CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 20));
query.setTrackTotalHitsUpTo(1000);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

CriteriaQuery và NativeQuery đều có thể dùng các tùy chọn chung của `Query`. Nếu query được tạo bởi custom builder hoặc helper, hãy truyền cấu hình tracking ở một nơi thống nhất để tránh mỗi endpoint có hành vi khác nhau.

## 7. Đọc tính chính xác từ `SearchHits`

Spring Data Elasticsearch không chỉ trả một con số total hits. `SearchHits<T>` cung cấp cả tổng số và quan hệ của tổng số:

- `getTotalHits()` trả giá trị tổng số được báo cáo.
- `getTotalHitsRelation()` cho biết giá trị đó chính xác, là lower bound hay tracking đã tắt.

Ví dụ:

```java
SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

long total = hits.getTotalHits();
TotalHitsRelation relation = hits.getTotalHitsRelation();

switch (relation) {
    case EQUAL_TO -> log.info("Exact total hits: {}", total);
    case GREATER_THAN_OR_EQUAL_TO ->
            log.info("At least {} documents matched", total);
    case OFF -> log.info("Total hit tracking is disabled");
}
```

`TotalHitsRelation` có các giá trị:

| Giá trị Spring Data | Ý nghĩa |
|---|---|
| `EQUAL_TO` | Tổng số chính xác, tương ứng Elasticsearch `eq`. |
| `GREATER_THAN_OR_EQUAL_TO` | Tổng số là cận dưới, tương ứng Elasticsearch `gte`. |
| `OFF` | Không theo dõi tổng số hit. |

Không nên chỉ gọi `getTotalHits()` rồi hiển thị như số chính xác. Ví dụ `total = 10000` cùng relation `GREATER_THAN_OR_EQUAL_TO` phải được hiển thị là “10.000+”, không phải “10.000 kết quả”.

Nếu tracking bị tắt, giá trị số mà abstraction trả về không thể được dùng như tổng số thực tế. Hãy dựa vào relation `OFF` để biết rằng số lượng không được theo dõi.

## 8. Ảnh hưởng đến `Page`, `SearchPage` và API response

Một `Page<T>` thông thường giả định có tổng số phần tử để tính `getTotalElements()` và `getTotalPages()`. Khi total hits chỉ là lower bound hoặc tracking đã tắt, thông tin trang tổng thể không còn chính xác.

Ví dụ:

```java
SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

SearchPage<ProductDocument> page =
        SearchHitSupport.searchPageFor(hits, pageable);
```

`SearchPage` giữ `SearchHits` và thông tin phân trang, nhưng nếu total hit relation là `GREATER_THAN_OR_EQUAL_TO`, không nên trình bày `getTotalElements()` như tổng số chính xác. Nếu relation là `OFF`, tổng số không có ý nghĩa.

### Khi giao diện cần tổng số trang chính xác

Nếu UI hiển thị:

```text
Trang 3 / 125
Tổng cộng 2.498 kết quả
```

thì cần một tổng số chính xác hoặc một chiến lược tính trang khác. Có thể bật `track_total_hits: true`, hoặc thực hiện Count API riêng nếu phù hợp.

### Khi giao diện chỉ cần nút “Xem thêm”

Nếu UI chỉ cần biết còn kết quả tiếp theo hay không, không cần total count. Có thể trả một cấu trúc như:

```json
{
  "items": [
    { "id": "P-100", "name": "Mechanical Keyboard" }
  ],
  "hasMore": true
}
```

Lúc này có thể tắt tracking và dùng chiến lược lấy dư một document để xác định `hasMore`.

## 9. Dùng `size + 1` để xác định có trang tiếp theo

Một cách đơn giản để tránh đếm tổng số là yêu cầu thêm một document so với số lượng muốn hiển thị.

Ví dụ giao diện hiển thị 20 sản phẩm:

1. Gửi request với `size = 21` và `track_total_hits = false`.
2. Nếu nhận 21 document, trả 20 document đầu và đặt `hasMore = true`.
3. Nếu nhận tối đa 20 document, trả toàn bộ và đặt `hasMore = false`.

Ví dụ code:

```java
int pageSize = 20;
// This example fetches the first page. For later offset pages,
// keep from = page * pageSize while requesting size = pageSize + 1.
Pageable pageable = PageRequest.of(0, pageSize + 1, sort);

NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(pageable)
        .build();
query.setTrackTotalHits(false);

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

List<ProductDocument> fetched = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();

boolean hasMore = fetched.size() > pageSize;
List<ProductDocument> items = fetched.stream()
        .limit(pageSize)
        .toList();
```

Đây là ví dụ cho trang đầu của offset pagination. Với trang tiếp theo, cần giữ offset theo kích thước trang hiển thị (`from = page * pageSize`) trong khi lấy thêm một hit; không dùng `PageRequest.of(page, pageSize + 1)` một cách máy móc vì nó làm offset tăng theo `pageSize + 1` và có thể bỏ qua document ở ranh giới trang. Có thể dùng request có `from`/`size` tường minh hoặc một `Pageable` tùy chỉnh. Khi dữ liệu thay đổi giữa các lần gọi hoặc người dùng đi đến trang rất sâu, offset pagination vẫn có các vấn đề riêng. Với luồng duyệt lớn, nên cân nhắc `search_after` kết hợp sort ổn định và Point in Time.

`size + 1` trả lời câu hỏi “có thêm kết quả không?” mà không cần biết tổng số document trong index.

## 10. Khi cần tổng số chính xác: Count API

Nếu search request cần tối ưu lấy top kết quả nhưng một thành phần khác cần tổng số chính xác, có thể tách thành hai request:

1. Search API lấy danh sách kết quả với `track_total_hits: false` hoặc ngưỡng thấp.
2. Count API tính tổng số document thỏa query.

REST API:

```http
POST /products/_count
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Response:

```json
{
  "count": 250000,
  "_shards": {
    "total": 5,
    "successful": 5,
    "skipped": 0,
    "failed": 0
  }
}
```

Spring Data Elasticsearch cung cấp `ElasticsearchOperations.count(...)`:

```java
Criteria countCriteria = new Criteria("status").is("ACTIVE");
CriteriaQuery countQuery = new CriteriaQuery(countCriteria);
long exactCount = operations.count(countQuery, ProductDocument.class);
```

Count API không trả danh sách document và không cần sort kết quả, nhưng vẫn phải thực thi query để đếm document phù hợp. Trong ví dụ, `countQuery` cần chứa cùng điều kiện nghiệp vụ với search query, nhưng không cần pageable hoặc sort. Nó không miễn phí và có thể tốn thời gian với query match rất nhiều document. Việc tách request hữu ích khi search top hits và count có yêu cầu/tần suất khác nhau, nhưng tổng chi phí hệ thống có thể tăng nếu luôn gọi cả hai.

Nếu query dùng filter theo tenant, status hoặc quyền truy cập, phải bảo đảm count query chứa đúng các điều kiện tương tự search query. Nếu thiếu filter, con số count có thể lớn hơn tập kết quả người dùng được phép nhìn thấy.

## 11. Phân biệt `track_total_hits` với `terminate_after`

Hai tùy chọn này đều có thể khiến ứng dụng không nhận được một tổng số đầy đủ, nhưng mục đích và semantics khác nhau.

| Tùy chọn | Mục đích | Tác động |
|---|---|---|
| `track_total_hits` | Kiểm soát mức độ đếm tổng số hit. | Có thể trả exact count, lower bound hoặc không trả total. |
| `terminate_after` | Dừng thu thập document sớm sau một giới hạn trên mỗi shard. | Search có thể kết thúc sớm và không đại diện đầy đủ cho toàn bộ tập document khớp. |

Ví dụ `terminate_after`:

```json
GET /products/_search
{
  "size": 0,
  "terminate_after": 1,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Đây là một kỹ thuật có thể dùng khi chỉ cần kiểm tra nhanh xem có document phù hợp hay không. `terminate_after` áp dụng theo từng shard và có thể khiến query bị kết thúc sớm; response có thể cho biết `terminated_early`.

Không dùng `terminate_after` thay cho `track_total_hits` để tạo một con số lower bound có ý nghĩa cho giao diện. Nếu mục tiêu là đếm đến một ngưỡng, dùng integer `track_total_hits`. Nếu mục tiêu là không đếm, dùng `false`.

## 12. `track_total_hits` không giải quyết deep pagination

`track_total_hits` chỉ điều khiển việc đếm tổng số hit. Nó không tăng giới hạn `from`/`size` và không làm phân trang sâu trở nên rẻ hơn.

Ví dụ page 500 với size 20 cần bỏ qua 10.000 kết quả đầu. Elasticsearch có giới hạn cửa sổ kết quả mặc định thường là 10.000. Ngay cả khi tắt total-hit tracking, một request offset rất sâu vẫn có thể tốn tài nguyên hoặc vượt `index.max_result_window`.

Với danh sách cần duyệt sâu, hãy cân nhắc:

- `search_after` để lấy kết quả tiếp theo dựa trên sort values của hit cuối trang trước.
- Point in Time (PIT) nếu cần giữ một góc nhìn dữ liệu ổn định giữa các request.
- Scroll cho các luồng xử lý batch phù hợp, không phải cho mọi UI pagination.

Các cơ chế này giải quyết bài toán duyệt kết quả lớn; `track_total_hits` chỉ là một lựa chọn riêng về tổng số.

## 13. Ảnh hưởng khi có aggregation

Một search request có thể vừa trả top document vừa tính aggregation/facet. Aggregation thường phải xét tập document phù hợp để tính bucket hoặc metric. Trong trường hợp đó, tắt exact total hits không đồng nghĩa Elasticsearch có thể bỏ qua mọi document không nằm trong top kết quả, vì aggregation vẫn cần dữ liệu trên phạm vi rộng.

Ví dụ:

```json
GET /products/_search
{
  "size": 20,
  "track_total_hits": false,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand"
      }
    }
  }
}
```

Request không theo dõi tổng số hit, nhưng vẫn yêu cầu aggregation `by_brand`. Vì vậy, lợi ích hiệu năng thực tế của việc tắt tracking có thể khác so với query chỉ lấy top hits. Hãy benchmark đúng request production, bao gồm aggregation và sort.

## 14. Thiết kế response API theo nhu cầu giao diện

Không phải endpoint nào cũng cần trả `totalElements`.

### Endpoint dùng số trang chính xác

```json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalElements": 250000,
  "totalPages": 12500,
  "totalExact": true
}
```

Để trả kiểu response này, endpoint phải có exact count. Có thể dùng `track_total_hits: true` hoặc count query tùy workload.

### Endpoint chỉ cần lower bound

```json
{
  "items": [],
  "minimumTotal": 10000,
  "totalRelation": "gte",
  "displayLabel": "10.000+ kết quả"
}
```

Response này giữ đúng semantics của Elasticsearch. Không biến lower bound thành một con số tổng chính xác.

### Endpoint infinite scroll

```json
{
  "items": [],
  "nextCursor": "opaque-sort-cursor",
  "hasMore": true
}
```

Endpoint không cần total count; nó chỉ cung cấp cursor hoặc thông tin để lấy trang tiếp theo.

### Chọn chế độ theo UX

| UX | Tracking gợi ý | Response |
|---|---|---|
| Hiển thị tổng số trang chính xác | `true` hoặc count riêng | `totalElements`, `totalPages`. |
| Chỉ cần “10.000+ kết quả” | Ngưỡng số nguyên | `minimumTotal`, relation. |
| Nút “Xem thêm” | `false` và lấy dư một hit | `hasMore`. |
| Infinite scroll dùng cursor | `false` | `nextCursor`, `hasMore`. |
| Chỉ lấy một số gợi ý | `false` | Danh sách item. |

## 15. Đo lường trước khi chọn ngưỡng

Không có một ngưỡng tối ưu cho tất cả hệ thống. Có thể bắt đầu với mặc định 10.000, sau đó đo các nhóm query đại diện:

1. Query ít match, ví dụ dưới 100 document.
2. Query trung bình, ví dụ vài nghìn document.
3. Query phổ biến match hàng trăm nghìn document.
4. Query có filter nhiều điều kiện.
5. Query có sort theo `_score`.
6. Query có aggregation/facets.
7. Query dưới tải đồng thời gần production.

So sánh ít nhất các cấu hình:

- Không khai báo (mặc định).
- `track_total_hits: false`.
- Một ngưỡng phù hợp với UX, ví dụ 1.000 hoặc 5.000.
- `track_total_hits: true`.

Ghi nhận:

- p50, p95 và p99 latency.
- CPU và heap của node.
- Throughput và error rate.
- Tổng số hit và relation trả về.
- Ảnh hưởng đến các query khác trên cluster.

Không benchmark chỉ một lần. Cache nóng/lạnh, refresh, merge và tải đồng thời có thể làm số đo thay đổi. Cần chạy nhiều lần trong điều kiện tương đương và xem cả latency lẫn tài nguyên.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Giao diện hiển thị 10.000 kết quả dù thực tế nhiều hơn | Đọc `hits.total.value` mà bỏ qua `relation: gte`. | Hiển thị “10.000+” hoặc yêu cầu exact count. |
| Không thấy `hits.total` trong response | `track_total_hits` đã bị tắt. | Không hiểu là zero hits; kiểm tra danh sách `hits.hits` và relation ở Spring Data. |
| Trang chỉ có 20 item nhưng total là 100.000 | `size` là số item trả về; total là số item khớp. | Xử lý hai thông tin độc lập. |
| Query chậm khi bật `true` | Elasticsearch phải đếm chính xác toàn bộ match và có thể mất một số tối ưu top-k. | Chỉ bật exact count khi UX cần; thử ngưỡng hoặc count riêng. |
| `setTrackTotalHitsUpTo` không có hiệu lực | `setTrackTotalHits(true/false)` đã được đặt. | Để boolean là `null` khi muốn dùng ngưỡng. |
| `Page.getTotalPages()` không chính xác | Tổng hit chỉ là lower bound hoặc tracking bị tắt. | Không dùng total không chính xác để tính số trang; đổi response/chiến lược. |
| Dùng `terminate_after` để thay ngưỡng đếm | Query có thể bị kết thúc sớm theo shard, không phải đếm đến một lower bound chuẩn. | Dùng `track_total_hits` integer. |
| Tăng `index.max_result_window` để xử lý page sâu | Nhầm giới hạn offset pagination với total hit tracking. | Dùng `search_after`/PIT cho duyệt sâu. |
| Tắt total tracking nhưng aggregation vẫn chậm | Aggregation vẫn cần xử lý tập document phù hợp. | Đo riêng request có aggregation và tối ưu aggregation/query. |

## 17. Checklist lựa chọn chế độ tracking

Trước khi bật exact count, hãy xác định:

1. Giao diện có thực sự cần số kết quả chính xác không?
2. Người dùng có cần số trang cuối cùng hay chỉ cần biết còn kết quả tiếp theo?
3. Nếu số lượng lớn, nhãn “N+” có đáp ứng trải nghiệm không?
4. Có thể dùng `size + 1` để xác định `hasMore` không?
5. Có cần tách Count API khỏi Search API không?
6. API response có giữ thông tin `eq`, `gte` hoặc `OFF` không?
7. Query có aggregation khiến việc bỏ exact count ít tác dụng hơn không?
8. Đã đo p95/p99 và tài nguyên với dữ liệu gần production chưa?
9. Có đang nhầm `track_total_hits` với `size`, `from`, `terminate_after` hoặc `index.max_result_window` không?

## 18. Những điểm cần nhớ

- `size` quyết định số document trả về; `track_total_hits` quyết định mức độ đếm tổng số document khớp.
- Mặc định Elasticsearch theo dõi chính xác đến 10.000 hit; vượt ngưỡng có thể trả `relation: "gte"`.
- `track_total_hits: true` yêu cầu tổng số chính xác và có thể làm query tốn kém hơn.
- `track_total_hits: false` tắt tracking; response không có `hits.total` nhưng vẫn có thể có document trong `hits.hits`.
- Giá trị số nguyên yêu cầu đếm chính xác đến ngưỡng; vượt ngưỡng chỉ biết có ít nhất N hit.
- `eq` nghĩa là chính xác; `gte` nghĩa là cận dưới.
- Spring Data Elasticsearch cung cấp `setTrackTotalHits` và `setTrackTotalHitsUpTo` trên Query; ngưỡng chỉ có hiệu lực khi boolean chưa được đặt.
- `SearchHits` cung cấp cả `getTotalHits()` và `getTotalHitsRelation()`; hãy đọc cả hai.
- Không dùng lower bound hoặc total bị tắt để tính `totalPages` chính xác.
- Dùng Count API hoặc `ElasticsearchOperations.count(...)` khi cần exact count riêng, nhưng vẫn phải đo chi phí.
- Dùng `size + 1` cho `hasMore` hoặc `search_after`/PIT cho cursor pagination khi không cần tổng số.
- `terminate_after` và `track_total_hits` giải quyết hai vấn đề khác nhau.
- Tắt exact total không đảm bảo query có aggregation sẽ nhanh hơn đáng kể; hãy benchmark request thực tế.

`track_total_hits` là một công cụ điều chỉnh chi phí tìm kiếm theo nhu cầu của giao diện. Hãy quyết định trước xem người dùng cần số chính xác, một cận dưới hay không cần tổng số; sau đó truyền lựa chọn đó qua Spring Data Elasticsearch và giữ nguyên thông tin về độ chính xác trong response để tránh hiển thị một con số sai nghĩa.

## Tài liệu tham khảo

- [Elasticsearch Search API — Track total hits](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Spring Data Elasticsearch — Query API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — SearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/SearchOperations.html)
