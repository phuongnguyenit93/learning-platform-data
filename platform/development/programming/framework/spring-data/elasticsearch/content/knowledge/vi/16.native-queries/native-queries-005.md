# Khai báo aggregation và đọc kết quả tương ứng

Elasticsearch aggregation dùng để tổng hợp dữ liệu ngay trên index, chẳng hạn tính giá trung bình, tổng doanh thu, đếm số document theo danh mục hoặc nhóm sự kiện theo ngày. Trong Spring Data Elasticsearch, có thể khai báo aggregation bằng `NativeQuery` và đọc kết quả thông qua `SearchHits` cùng `ElasticsearchAggregations`.

Aggregation không giống việc lấy toàn bộ document về Java rồi tự nhóm và tính toán. Elasticsearch thực hiện phép tổng hợp trên dữ liệu đã lập chỉ mục và trả về các bucket hoặc metric. Cách này thường giảm lượng dữ liệu truyền về ứng dụng, đồng thời tận dụng khả năng xử lý phân tán của cluster.

## 1. Aggregation là gì?

Aggregation là một phần của Elasticsearch Query DSL dùng để phân tích dữ liệu. Một request tìm kiếm có thể trả về cả document hits lẫn kết quả aggregation.

Ví dụ, với index `products`, ứng dụng có thể cần:

- Tính giá nhỏ nhất, lớn nhất, trung bình và tổng.
- Đếm số sản phẩm theo danh mục.
- Đếm số sản phẩm theo trạng thái.
- Nhóm sản phẩm theo khoảng giá.
- Thống kê số sự kiện theo ngày hoặc tháng.
- Đếm số giá trị khác nhau của một field.

Luồng xử lý thường là:

```text
NativeQuery
   |-- Query: lọc tập document đầu vào
   |-- Aggregations: khai báo phép tổng hợp
            |
            v
ElasticsearchOperations.search(...)
            |
            v
SearchHits<T>
   |-- danh sách document hits
   |-- total hits / score / metadata
   |-- AggregationsContainer
            |
            v
ElasticsearchAggregations
   |-- ElasticsearchAggregation
            |
            v
Elasticsearch Java API Aggregate
            |
            v
Metric values / Bucket values
```

## 2. Các nhóm aggregation chính

Elasticsearch có nhiều aggregation, nhưng có thể chia thành các nhóm cơ bản:

| Nhóm | Mục đích | Ví dụ |
|---|---|---|
| Metric | Tính một hoặc nhiều giá trị thống kê trên tập document | `avg`, `sum`, `min`, `max`, `stats`, `cardinality` |
| Bucket | Chia document thành các nhóm theo điều kiện hoặc giá trị | `terms`, `range`, `date_histogram`, `filters` |
| Pipeline | Tính toán dựa trên kết quả của aggregation khác | `derivative`, `moving_fn`, `bucket_script` |
| Parent/child và nested | Tổng hợp trên cấu trúc document lồng hoặc quan hệ đặc biệt | `nested`, `reverse_nested`, `children` |

Metric aggregation trả về giá trị thống kê. Bucket aggregation tạo ra các nhóm, mỗi bucket có thể chứa số document và có thể có aggregation con. Pipeline aggregation đọc kết quả từ các bucket hoặc metric khác để thực hiện phép tính tiếp theo.

## 3. Document mẫu và mapping

Giả sử ứng dụng quản lý đơn hàng bán hàng:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "sales")
public class SaleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private Double amount;

    @Field(type = FieldType.Integer)
    private Integer quantity;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructors, getters and setters
}
```

Mapping phù hợp rất quan trọng:

- `category` và `status` là `keyword`, phù hợp với terms aggregation.
- `amount` và `quantity` là kiểu số, phù hợp với sum, average, min, max và range aggregation.
- `createdAt` là `date`, phù hợp với date histogram.

Không nên chạy terms aggregation trên field `text` nếu mục đích là nhóm theo toàn bộ giá trị. Field `text` được analyzer chia thành token; mặc định thường không bật fielddata vì chi phí bộ nhớ. Nếu cần vừa full-text search vừa aggregation theo giá trị nguyên bản, hãy dùng multi-field có subfield `keyword` và aggregate trên subfield đó.

## 4. Khai báo aggregation bằng `NativeQuery`

`NativeQuery` của Spring Data Elasticsearch tích hợp với Elasticsearch Java API Client (ELC). Có thể dùng builder của client để khai báo query và aggregation.

Ví dụ tạo hai aggregation: thống kê giá trị `amount` và đếm số đơn hàng theo `category`.

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

Query query = NativeQuery.builder()
    .withAggregation(
        "amount_stats",
        Aggregation.of(a -> a.stats(s -> s.field("amount")))
    )
    .withAggregation(
        "sales_by_category",
        Aggregation.of(a -> a.terms(t -> t
            .field("category")
            .size(20)
        ))
    )
    .build();
```

Tên aggregation (`amount_stats`, `sales_by_category`) là tên do ứng dụng đặt. Tên này sẽ được dùng để lấy kết quả sau khi thực thi. Field trong aggregation phải là tên field Elasticsearch thực tế, và kiểu mapping phải phù hợp với loại aggregation.

### Kết hợp điều kiện query và aggregation

Aggregation được tính trên tập document phù hợp với query ở cấp cao nhất. Ví dụ chỉ thống kê các đơn hàng đã hoàn tất:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.term(t -> t
        .field("status")
        .value(v -> v.stringValue("COMPLETED"))
    ))
    .withAggregation(
        "amount_stats",
        Aggregation.of(a -> a.stats(s -> s.field("amount")))
    )
    .withAggregation(
        "sales_by_category",
        Aggregation.of(a -> a.terms(t -> t.field("category").size(20)))
    )
    .build();
```

Trong ví dụ, cả `amount_stats` và `sales_by_category` chỉ tính trên các document có `status = COMPLETED`. Cú pháp lambda và kiểu builder cụ thể phụ thuộc phiên bản Elasticsearch Java Client do Spring Data quản lý; ví dụ dùng API ELC hiện đại, không phải API `RestHighLevelClient` cũ.

## 5. Thực thi query và lấy aggregation container

Dùng `ElasticsearchOperations.search(...)` để thực thi query:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<SaleDocument> searchHits =
    operations.search(query, SaleDocument.class);
```

`SearchHits<T>` chứa các document tìm được và metadata của search response. Kết quả aggregation được lấy qua `getAggregations()`:

```java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;

ElasticsearchAggregations aggregations =
    (ElasticsearchAggregations) searchHits.getAggregations();
```

`getAggregations()` có thể không có giá trị nếu request không khai báo aggregation hoặc response không chứa aggregation. Khi dùng query có aggregation, hãy kiểm tra null trước khi ép kiểu hoặc truy cập kết quả. Các kiểu container và accessor cụ thể phụ thuộc phiên bản Spring Data Elasticsearch.

Spring Data bọc kết quả ELC trong `ElasticsearchAggregations`. Mỗi aggregation có thể được lấy theo tên đã khai báo, sau đó truy cập kiểu aggregate tương ứng của Elasticsearch Java Client.

## 6. Đọc kết quả metric aggregation

Với aggregation `stats`, Elasticsearch trả về số lượng giá trị, min, max, avg và sum.

```java
import co.elastic.clients.elasticsearch._types.aggregations.StatsAggregate;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;

ElasticsearchAggregation amountAggregation =
    aggregations.get("amount_stats");

StatsAggregate amountStats =
    amountAggregation.aggregation().stats();

long count = amountStats.count();
double min = amountStats.min();
double max = amountStats.max();
double average = amountStats.avg();
double sum = amountStats.sum();
```

Kết quả có thể được đưa vào DTO cho API báo cáo:

```java
public record AmountSummary(
        long count,
        double min,
        double max,
        double average,
        double sum) {
}

AmountSummary summary = new AmountSummary(
    amountStats.count(),
    amountStats.min(),
    amountStats.max(),
    amountStats.avg(),
    amountStats.sum()
);
```

`stats` thuận tiện khi cần nhiều metric trên cùng một field. Nếu chỉ cần một giá trị, có thể dùng `avg`, `sum`, `min`, `max` hoặc `value_count` để response chỉ chứa phần cần thiết.

### Những metric thường dùng

| Aggregation | Kết quả |
|---|---|
| `count` | Số document trong bucket hoặc số giá trị được đếm theo loại aggregation |
| `value_count` | Số giá trị được lập chỉ mục cho field, có thể khác số document nếu field là mảng |
| `sum` | Tổng giá trị số |
| `avg` | Giá trị trung bình |
| `min` / `max` | Giá trị nhỏ nhất/lớn nhất |
| `stats` | Count, min, max, avg và sum |
| `extended_stats` | Thêm các thống kê như độ lệch chuẩn và phương sai |
| `cardinality` | Số giá trị khác nhau ước lượng |
| `percentiles` | Các phân vị của phân bố số |

`cardinality` thường là phép ước lượng dựa trên thuật toán xác suất, không nên xem kết quả là số distinct tuyệt đối trong mọi trường hợp. Nếu nghiệp vụ cần con số chính xác, cần đánh giá phương pháp khác và chi phí tính toán.

## 7. Đọc kết quả terms aggregation

Terms aggregation tạo bucket theo từng giá trị khác nhau của một field. Ví dụ đếm số đơn hàng theo category:

```java
Aggregation.of(a -> a.terms(t -> t
    .field("category")
    .size(20)
))
```

Đọc bucket:

```java
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;

StringTermsAggregate categoryTerms =
    aggregations.get("sales_by_category").aggregation().sterms();

for (StringTermsBucket bucket : categoryTerms.buckets().array()) {
    String category = bucket.key().stringValue();
    long documentCount = bucket.docCount();

    System.out.println(category + ": " + documentCount);
}
```

`sterms()` dùng cho terms aggregation trên giá trị chuỗi. Với field số nguyên hoặc số thực, kết quả có thể thuộc kiểu `lterms()` hoặc `dterms()` tương ứng. Kiểu aggregate cần đọc phải khớp với kiểu field và response thực tế.

### `size` có ý nghĩa gì?

`size(20)` yêu cầu trả về tối đa 20 bucket đứng đầu theo thứ tự mặc định hoặc thứ tự được cấu hình. Nó không có nghĩa chỉ tính aggregation trên 20 document. Elasticsearch vẫn xét tập document phù hợp để xây dựng các bucket, sau đó chọn số bucket được trả về.

Terms aggregation phân tán có thể cần điều chỉnh `shard_size` nếu muốn tăng độ chính xác của top bucket trong cluster nhiều shard. Tăng `size` hoặc `shard_size` làm tăng bộ nhớ và dữ liệu trao đổi giữa shard; hãy đo lường trước khi đặt giá trị lớn.

## 8. Sub-aggregation: tính metric bên trong từng bucket

Có thể đặt aggregation con bên trong bucket aggregation. Ví dụ, với mỗi category, tính tổng doanh thu và giá trị trung bình:

```java
Query query = NativeQuery.builder()
    .withAggregation(
        "sales_by_category",
        Aggregation.of(a -> a.terms(t -> t
            .field("category")
            .size(20)
        ).aggregations(
            "revenue_sum",
            Aggregation.of(sub -> sub.sum(s -> s.field("amount")))
        ).aggregations(
            "average_amount",
            Aggregation.of(sub -> sub.avg(avg -> avg.field("amount")))
        ))
    )
    .build();
```

Kết quả mỗi bucket chứa `doc_count`, `revenue_sum` và `average_amount`. Cấu trúc đọc kết quả cần đi từ aggregation cha tới aggregation con trong từng bucket. API ELC dùng kiểu union `Aggregate`, vì vậy cần kiểm tra đúng biến thể bucket và metric trước khi đọc.

Sub-aggregation hữu ích cho báo cáo như doanh thu theo danh mục, số lượng đơn theo trạng thái hoặc giá trung bình theo thương hiệu. Không cần gửi một truy vấn riêng cho từng danh mục; Elasticsearch có thể thực hiện các phép tổng hợp trong cùng request.

## 9. Date histogram: nhóm dữ liệu theo thời gian

Date histogram chia document thành bucket theo khoảng thời gian như giờ, ngày, tuần hoặc tháng. Ví dụ thống kê số đơn hàng theo ngày:

```java
import co.elastic.clients.elasticsearch._types.aggregations.CalendarInterval;

Query query = NativeQuery.builder()
    .withAggregation(
        "sales_per_day",
        Aggregation.of(a -> a.dateHistogram(h -> h
            .field("createdAt")
            .calendarInterval(CalendarInterval.Day)
            .timeZone("Asia/Ho_Chi_Minh")
        ))
    )
    .build();
```

`calendarInterval` dùng đơn vị lịch như ngày hoặc tháng; `fixedInterval` dùng khoảng thời gian cố định. Ví dụ, ngày theo lịch có thể chịu ảnh hưởng của timezone và thay đổi giờ mùa hè, trong khi một khoảng cố định luôn có độ dài thời gian xác định.

Đọc bucket ngày:

```java
import co.elastic.clients.elasticsearch._types.aggregations.DateHistogramAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.DateHistogramBucket;

DateHistogramAggregate daily =
    aggregations.get("sales_per_day").aggregation().dateHistogram();

for (DateHistogramBucket bucket : daily.buckets().array()) {
    String dateLabel = bucket.keyAsString();
    long documentCount = bucket.docCount();
}
```

Nếu cần các bucket có số lượng bằng 0 trong khoảng thời gian, xem xét `min_doc_count: 0` cùng `extended_bounds` để yêu cầu Elasticsearch tạo cả bucket rỗng trong phạm vi xác định. Nếu không cấu hình, các khoảng không có document có thể không xuất hiện trong response.

Khi báo cáo theo ngày địa phương, khai báo timezone rõ ràng trong aggregation. Không chỉ chuyển timestamp sang giờ địa phương ở tầng Java sau khi aggregation đã nhóm theo UTC, vì ranh giới ngày có thể khác nhau.

## 10. Range aggregation và histogram số

Range aggregation chia giá trị số thành các bucket theo khoảng được định nghĩa trước. Ví dụ phân nhóm đơn hàng theo giá trị:

```json
{
  "aggs": {
    "amount_ranges": {
      "range": {
        "field": "amount",
        "ranges": [
          { "to": 100 },
          { "from": 100, "to": 500 },
          { "from": 500 }
        ]
      }
    }
  }
}
```

Các khoảng có dạng `[from, to)`: bao gồm cận dưới và không bao gồm cận trên. Ví dụ trên chia thành dưới 100, từ 100 đến dưới 500 và từ 500 trở lên.

Histogram aggregation chia giá trị thành các khoảng đều nhau theo `interval`, phù hợp với biểu đồ phân bố giá hoặc số lượng. Khác với range aggregation, các bucket được tạo dựa trên kích thước khoảng cố định.

Khi đọc kết quả range/histogram, mỗi bucket thường có key hoặc key_as_string, from/to và doc_count. Kiểu bucket cụ thể phụ thuộc loại aggregation được khai báo; hãy đọc đúng biến thể trong `Aggregate` thay vì ép tất cả thành string terms.

## 11. Filter aggregation và phạm vi document được tổng hợp

Có hai nơi thường dùng để lọc document trước khi tổng hợp:

1. Query ở cấp cao nhất: giới hạn cả document hits và tập dữ liệu đầu vào của tất cả aggregation thông thường.
2. Filter aggregation: tạo một bucket con chỉ chứa document thỏa điều kiện riêng; các aggregation con bên trong bucket chỉ tổng hợp tập con đó.

Ví dụ, query lấy tất cả đơn hàng trong index, nhưng muốn tính riêng doanh thu của đơn đã hoàn tất:

```json
{
  "size": 0,
  "aggs": {
    "completed_sales": {
      "filter": {
        "term": {
          "status": "COMPLETED"
        }
      },
      "aggs": {
        "total_amount": {
          "sum": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

Nếu query cấp cao nhất đã lọc `status = COMPLETED`, không cần lặp lại cùng filter trong aggregation trừ khi có mục đích riêng. Một điểm khác là `post_filter`: nó lọc hits trả về sau khi aggregation được tính, vì vậy aggregation vẫn có thể phản ánh tập document rộng hơn hits. Hãy chọn đúng vị trí lọc theo ý nghĩa báo cáo.

## 12. Nested aggregation cho field nested

Nếu document có mảng object được mapping kiểu `nested`, aggregation trên các thuộc tính con phải đi qua nested aggregation để vào đúng ngữ cảnh nested document.

Ví dụ mapping:

```java
@Field(type = FieldType.Nested)
private List<OrderLineDocument> lines;
```

Muốn tổng hợp theo SKU của từng dòng đơn hàng, cần dùng nested aggregation trên path `lines`, sau đó mới terms aggregation trên `lines.sku`. Có thể cần `reverse_nested` nếu muốn quay lại ngữ cảnh document cha.

Nếu field chỉ là `object` thông thường, không dùng nested aggregation. Chọn sai ngữ cảnh sẽ dẫn đến lỗi query hoặc kết quả không phản ánh quan hệ giữa các phần tử mảng như mong muốn.

## 13. Đọc aggregation an toàn và chuyển thành DTO

Kết quả aggregation là dữ liệu có cấu trúc, không nên truyền thẳng object client ra API công khai. Hãy chuyển thành DTO của ứng dụng:

```java
public record CategoryCount(String category, long count) {
}

public record SalesReport(
        AmountSummary amount,
        List<CategoryCount> categories) {
}
```

Ví dụ service đọc stats và terms:

```java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.aggregations.StatsAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

public SalesReport toReport(SearchHits<SaleDocument> hits) {
    if (!(hits.getAggregations() instanceof ElasticsearchAggregations aggs)) {
        throw new IllegalStateException("Expected aggregations in search response");
    }

    StatsAggregate stats = aggs.get("amount_stats").aggregation().stats();
    AmountSummary amount = new AmountSummary(
        stats.count(),
        stats.min(),
        stats.max(),
        stats.avg(),
        stats.sum()
    );

    StringTermsAggregate terms =
        aggs.get("sales_by_category").aggregation().sterms();

    List<CategoryCount> categories = new ArrayList<>();
    for (StringTermsBucket bucket : terms.buckets().array()) {
        categories.add(new CategoryCount(
            bucket.key().stringValue(),
            bucket.docCount()
        ));
    }

    return new SalesReport(amount, categories);
}
```

Đây là ví dụ đọc hai aggregation đã khai báo ở trên. Trong code production, nên kiểm tra aggregation có tồn tại và đúng kiểu trước khi truy cập; tên sai hoặc đọc nhầm biến thể aggregate có thể gây lỗi runtime. Có thể tách các hàm `readStats`, `readStringTerms` và `readDateHistogram` để tránh lặp logic chuyển đổi.

### Tránh ép kiểu tùy tiện

Elasticsearch Java API Client biểu diễn nhiều loại aggregation trong một kiểu union `Aggregate`. Một response có thể chứa `sterms`, `lterms`, `dateHistogram`, `stats` hoặc kiểu khác. Hãy gọi accessor đúng biến thể hoặc kiểm tra `is...()` trước khi đọc. Không ép một bucket số thành `StringTermsAggregate` chỉ vì key có thể chuyển thành chuỗi.

## 14. Chỉ lấy aggregation, không cần document hits

Một báo cáo tổng hợp đôi khi không cần danh sách document. Khi đó, có thể đặt kích thước hits bằng 0 để giảm payload response. Trong các phiên bản Spring Data có hỗ trợ `setMaxResults`, có thể đặt query không trả document hits:

```java
NativeQuery query = NativeQuery.builder()
    .withAggregation(
        "amount_stats",
        Aggregation.of(a -> a.stats(s -> s.field("amount")))
    )
    .build();

query.setMaxResults(0);

SearchHits<SaleDocument> hits =
    operations.search(query, SaleDocument.class);
```

Kiểm tra API query của phiên bản đang dùng để xác nhận cách đặt `size: 0`. Dù hits không được trả về, response vẫn có thể chứa aggregation. Đây là lựa chọn phù hợp cho dashboard chỉ hiển thị số tổng hợp.

## 15. Phân trang bucket và giới hạn của terms aggregation

Terms aggregation trả về một số lượng bucket giới hạn bởi `size`. Nó phù hợp với top N danh mục, trạng thái hoặc thương hiệu. Nếu cần duyệt toàn bộ số lượng bucket lớn, không nên tăng `size` lên một giá trị khổng lồ.

Composite aggregation được thiết kế để phân trang qua các bucket. Response trả về `after_key`; request tiếp theo gửi lại `after` để tiếp tục từ vị trí đó. Cách này phù hợp khi cần duyệt tất cả tổ hợp giá trị, ví dụ mọi cặp `category` và `status`.

Phân biệt:

- `terms`: lấy top bucket theo thứ tự/độ ưu tiên, thuận tiện cho dashboard.
- `composite`: duyệt bucket theo trang một cách có kiểm soát.

Không nên coi `terms.size` là cơ chế phân trang chính xác cho tất cả bucket. Với phân tích cardinality lớn, chọn composite và xử lý `after_key`.

## 16. Hiệu năng và độ chính xác của aggregation

Aggregation có thể tiêu tốn CPU, heap và mạng, đặc biệt với cardinality cao hoặc nhiều tầng bucket. Một số nguyên tắc:

- Aggregate trên `keyword`, numeric hoặc date field có mapping phù hợp.
- Không bật fielddata trên `text` chỉ để dùng terms aggregation nếu có thể tạo subfield `keyword`.
- Chỉ khai báo aggregation cần thiết cho màn hình hoặc báo cáo.
- Giới hạn `size` của terms và số bucket lồng nhau.
- Dùng filter ở query cấp cao nhất để giảm tập document đầu vào khi toàn bộ aggregation cùng cần bộ lọc đó.
- Dùng `cardinality` như giá trị ước lượng, không mặc định là count chính xác.
- Kiểm tra độ chính xác top terms trong cluster nhiều shard và điều chỉnh `shard_size` có chủ đích.
- Tránh aggregation nhiều tầng với cardinality rất lớn nếu chưa đo tài nguyên.
- Cân nhắc cache hoặc lưu kết quả tổng hợp cho dashboard có truy vấn lặp lại và dữ liệu không cần realtime tuyệt đối.

`doc_values` được dùng rộng rãi cho aggregation, sort và truy cập giá trị field theo cột. Hầu hết field keyword và numeric bật doc values mặc định. Không tắt doc values nếu ứng dụng cần aggregate hoặc sort trên field đó.

## 17. Kiểm tra aggregation bằng REST API

Trước khi chuyển query sang `NativeQuery`, có thể thử trực tiếp trên Elasticsearch Dev Tools để hiểu response:

```http
GET /sales/_search
Content-Type: application/json

{
  "size": 0,
  "query": {
    "term": {
      "status": "COMPLETED"
    }
  },
  "aggs": {
    "amount_stats": {
      "stats": {
        "field": "amount"
      }
    },
    "sales_by_category": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_amount": {
          "avg": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

Response sẽ có `aggregations.amount_stats` và `aggregations.sales_by_category.buckets`. Kiểm tra tên aggregation, key, doc_count và giá trị metric trước khi viết code chuyển đổi. Khi đã hiểu response, ánh xạ cấu trúc đó sang `NativeQuery` và kiểu ELC tương ứng.

## 18. Lỗi thường gặp

### Aggregation trên field `text`

Terms aggregation cần giá trị nguyên bản nhưng field `text` được phân tích thành token. Dùng subfield `keyword` hoặc field mapping phù hợp. Không bật fielddata một cách tùy tiện vì có thể tiêu tốn nhiều heap.

### Không đọc được aggregation từ `SearchHits`

Có thể query chưa khai báo aggregation, tên aggregation khi đọc không trùng tên khi khai báo hoặc code đang ép kiểu container sai. Kiểm tra `getAggregations()` và response thực tế.

### Gọi sai accessor của `Aggregate`

ELC dùng union type cho nhiều loại aggregation. Terms chuỗi dùng `sterms()`, metric stats dùng `stats()`, date histogram dùng `dateHistogram()`. Hãy chọn đúng kiểu theo request đã khai báo.

### Bucket bị thiếu

Terms aggregation chỉ trả về số bucket theo `size` và có thể phân phối top bucket giữa các shard. Nếu cần toàn bộ bucket, dùng composite aggregation; nếu cần cải thiện top terms, xem xét `shard_size`.

### Ngày bị nhóm sai timezone

Date histogram có thể nhóm theo UTC nếu không chỉ định timezone. Với báo cáo theo ngày địa phương, đặt `time_zone` trong aggregation và xác định rõ calendar interval hay fixed interval.

### Metric không đúng với tập dữ liệu mong muốn

Aggregation được tính trên tập document do query cấp cao nhất xác định. Kiểm tra query, filter aggregation và post_filter để hiểu chính xác phạm vi dữ liệu được tổng hợp.

### Giá trị cardinality không khớp distinct count

Cardinality thường là ước lượng. Nếu yêu cầu chính xác, cần chọn cách tính phù hợp và cân nhắc chi phí.

## 19. Quy trình xây dựng báo cáo bằng NativeQuery

Khi triển khai một báo cáo, có thể làm theo trình tự:

1. Xác định tập document đầu vào bằng query cấp cao nhất.
2. Xác định metric cần tính: sum, avg, min, max, stats, cardinality hoặc percentiles.
3. Xác định bucket cần nhóm: terms, range, date histogram, filters hoặc nested.
4. Kiểm tra mapping của từng field; dùng keyword cho nhóm chuỗi và numeric/date cho phép tính tương ứng.
5. Đặt tên aggregation ổn định, dễ hiểu và duy nhất trong query.
6. Dùng `NativeQuery.builder().withAggregation(...)` để khai báo aggregation.
7. Thực thi bằng `ElasticsearchOperations.search(...)`.
8. Lấy `ElasticsearchAggregations` từ `SearchHits` và đọc đúng biến thể `Aggregate`.
9. Chuyển kết quả thành DTO của ứng dụng, không để kiểu client rò ra API nếu không cần.
10. Kiểm tra bucket limit, cardinality, timezone, filter scope và chi phí trên dữ liệu gần production.

## 20. Kết luận

Trong Spring Data Elasticsearch, `NativeQuery` cho phép khai báo metric, bucket và các aggregation lồng nhau bằng Elasticsearch Java API Client. Dùng `withAggregation(name, aggregation)` để gắn aggregation vào query, thực thi qua `ElasticsearchOperations.search(...)`, sau đó lấy `ElasticsearchAggregations` từ `SearchHits` và truy cập kết quả theo tên.

Metric aggregation như `stats`, `sum` và `avg` trả về giá trị thống kê; bucket aggregation như `terms`, `range` và `date_histogram` chia document thành nhóm; sub-aggregation cho phép tính metric bên trong từng bucket. Mapping phải hỗ trợ phép tổng hợp, query cấp cao nhất quyết định tập document đầu vào và kết quả cần được đọc theo đúng kiểu `Aggregate`. Với bucket lớn, cardinality cao hoặc báo cáo theo thời gian, cần chú ý giới hạn, độ chính xác, timezone và hiệu năng. Chuyển response thành DTO rõ ràng sẽ giúp phần báo cáo độc lập hơn với API client Elasticsearch.
