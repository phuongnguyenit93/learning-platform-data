# Khai báo aggregation bằng NativeQuery và đọc wrapper của client

Aggregation trong Elasticsearch dùng để tổng hợp dữ liệu trên tập document phù hợp với query. Thay vì chỉ lấy từng document, ứng dụng có thể đếm số sản phẩm theo danh mục, tính giá trung bình, tìm giá nhỏ nhất/lớn nhất hoặc gom doanh thu theo tháng.

Trong Spring Data Elasticsearch, có thể khai báo aggregation bằng **kiểu `Aggregation` của Elasticsearch Java API Client**, gắn nó vào `NativeQuery`, rồi thực thi bằng `ElasticsearchOperations.search(...)`.

Điểm quan trọng của bài học là phân biệt hai kiểu dữ liệu:

- **Request aggregation**: `co.elastic.clients.elasticsearch._types.aggregations.Aggregation` mô tả phép tổng hợp cần chạy.
- **Response aggregate**: `co.elastic.clients.elasticsearch._types.aggregations.Aggregate` là kiểu union chứa kết quả của một loại aggregation cụ thể.

Spring Data bọc các kết quả này trong `ElasticsearchAggregations` và `ElasticsearchAggregation`. Muốn đọc bucket hoặc metric, ứng dụng lấy wrapper từ `SearchHits`, mở wrapper và truy cập đúng biến thể của kiểu `Aggregate`.

## 1. Aggregation dùng để làm gì?

Giả sử index `products` lưu sản phẩm với các field:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "category": "ACCESSORIES",
  "price": 1299000,
  "status": "PUBLISHED",
  "createdAt": "2026-10-20T08:30:00Z"
}
~~~

Một màn hình báo cáo có thể cần:

- Đếm số sản phẩm theo danh mục.
- Tính giá trung bình của từng danh mục.
- Tìm giá thấp nhất và cao nhất.
- Đếm số sản phẩm được tạo theo tháng.
- Chỉ tổng hợp các sản phẩm đang xuất bản hoặc thuộc một tenant nhất định.

Search query xác định **tập document đầu vào**. Aggregation xác định **cách tổng hợp tập document đó**.

~~~mermaid
flowchart TD
    A["NativeQuery"] --> B["Query DSL: chọn document"]
    A --> C["Aggregation DSL: mô tả phép tổng hợp"]
    B --> D["Elasticsearch search request"]
    C --> D
    D --> E["Elasticsearch xử lý document phù hợp"]
    E --> F["Search hits"]
    E --> G["Aggregation results"]
    F --> H["SearchHits<T>"]
    G --> I["ElasticsearchAggregations wrapper"]
~~~

Một request có thể trả cả search hits và aggregation results. Nếu ứng dụng chỉ cần báo cáo tổng hợp, có thể đặt số document hits trả về bằng 0 để tránh tải dữ liệu không cần thiết.

## 2. Phân biệt Aggregation của request và Aggregate của response

Tên hai kiểu gần giống nhau nhưng vai trò khác nhau:

| Kiểu | Package | Vai trò |
|---|---|---|
| `Aggregation` | `co.elastic.clients.elasticsearch._types.aggregations.Aggregation` | Mô tả aggregation gửi lên Elasticsearch |
| `Aggregate` | `co.elastic.clients.elasticsearch._types.aggregations.Aggregate` | Chứa kết quả aggregation nhận về |
| `ElasticsearchAggregation` | `org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation` | Wrapper Spring Data cho một aggregation response |
| `ElasticsearchAggregations` | `org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations` | Wrapper Spring Data cho tập aggregation response |
| `AggregationsContainer<?>` | `org.springframework.data.elasticsearch.core.AggregationsContainer` | Abstraction của Spring Data cho aggregation container |
| `SearchHits<T>` | `org.springframework.data.elasticsearch.core.SearchHits` | Kết quả search, gồm hits và aggregation container |

Đây là hai kiểu quan trọng nhất cần phân biệt:

~~~java
// Request: khai báo phép tổng hợp cần chạy
co.elastic.clients.elasticsearch._types.aggregations.Aggregation requestAggregation;

// Response: kết quả của phép tổng hợp
co.elastic.clients.elasticsearch._types.aggregations.Aggregate responseAggregate;
~~~

Ví dụ, request aggregation có thể yêu cầu tính average trên field `price`. Khi response về, `Aggregate` chứa biến thể average và giá trị trung bình đã tính.

Không truyền một response `Aggregate` vào `NativeQuery`. Ngược lại, cũng không thể đọc kết quả từ request `Aggregation`: request chỉ mô tả công việc Elasticsearch cần thực hiện.

## 3. Chuẩn bị mapping cho aggregation

Aggregation cần field có kiểu dữ liệu phù hợp.

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String productId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructors, getters and setters
}
~~~

Một số nguyên tắc:

- Dùng `keyword` cho danh mục, trạng thái, mã và các giá trị cần gom nhóm chính xác.
- Dùng kiểu numeric như `integer`, `long`, `double` hoặc `scaled_float` cho phép tính số học.
- Dùng `date` cho ngày giờ và date histogram.
- Không dùng trực tiếp field `text` cho terms aggregation thông thường nếu fielddata không được bật. Với multi-field, hãy dùng subfield keyword như `name.keyword`.

Ví dụ mapping tương ứng:

~~~json
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "status": {
        "type": "keyword"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Nếu mapping không hỗ trợ aggregation trên field, request có thể lỗi hoặc không có kết quả như mong đợi. Hãy kiểm tra mapping thực tế trong cluster thay vì chỉ dựa vào kiểu Java.

## 4. Khai báo terms aggregation bằng Java API Client

Terms aggregation chia document thành các bucket theo giá trị của một field.

Ví dụ đếm số sản phẩm theo danh mục:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(20)
        )
);
~~~

Trong ví dụ:

- `Aggregation.of(...)` tạo request aggregation.
- `terms(...)` chọn loại terms aggregation.
- `field("category")` xác định field dùng để nhóm.
- `size(20)` yêu cầu tối đa 20 bucket được trả về.

Nếu có các document:

| productId | category | price |
|---|---|---:|
| P-1001 | ACCESSORIES | 1299000 |
| P-1002 | ACCESSORIES | 990000 |
| P-1003 | KEYBOARD | 1599000 |
| P-1004 | MONITOR | 4500000 |

Aggregation có thể trả các bucket:

- ACCESSORIES: 2 document.
- KEYBOARD: 1 document.
- MONITOR: 1 document.

Mỗi bucket có key và số document khớp, thường đọc qua `key()` và `docCount()`.

## 5. Khai báo metric aggregation

Metric aggregation tính toán một hoặc một số giá trị số trên tập document.

### Average

Tính giá trung bình:

~~~java
Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg
                .field("price")
        )
);
~~~

### Sum

Tính tổng giá trị field:

~~~java
Aggregation totalPrice = Aggregation.of(a -> a
        .sum(sum -> sum
                .field("price")
        )
);
~~~

### Min và max

~~~java
Aggregation minPrice = Aggregation.of(a -> a
        .min(min -> min
                .field("price")
        )
);

Aggregation maxPrice = Aggregation.of(a -> a
        .max(max -> max
                .field("price")
        )
);
~~~

### Stats

Nếu cần count, min, max, average và sum trong một aggregation:

~~~java
Aggregation priceStats = Aggregation.of(a -> a
        .stats(stats -> stats
                .field("price")
        )
);
~~~

Các metric này là aggregation riêng. Có thể gắn nhiều aggregation vào cùng một NativeQuery bằng cách đặt tên khác nhau.

## 6. Gắn aggregation vào NativeQuery

Spring Data Elasticsearch cung cấp `NativeQuery` để sử dụng query DSL và aggregation của Elasticsearch Java API Client.

Ví dụ chỉ đếm số sản phẩm theo danh mục:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(20)
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .build();
~~~

Tên `by_category` là tên aggregation trong request. Ứng dụng sẽ dùng đúng tên này để tìm kết quả trong response.

Có thể gắn nhiều aggregation:

~~~java
Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg.field("price"))
);

Aggregation priceStats = Aggregation.of(a -> a
        .stats(stats -> stats.field("price"))
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .withAggregation("average_price", averagePrice)
        .withAggregation("price_stats", priceStats)
        .build();
~~~

Tên aggregation cần duy nhất trong cùng một cấp. Nên đặt tên thể hiện ý nghĩa nghiệp vụ, ví dụ `products_by_category`, `average_price`, `orders_by_month`.

### Kết hợp query và aggregation

Aggregation được thực hiện trên tập document sau khi query chính lọc dữ liệu.

Ví dụ chỉ tổng hợp sản phẩm đang xuất bản:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query publishedOnly = Query.of(q -> q
        .term(t -> t
                .field("status")
                .value(FieldValue.of("PUBLISHED"))
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(publishedOnly)
        .withAggregation("by_category", byCategory)
        .withAggregation("average_price", averagePrice)
        .build();
~~~

Khi đó, bucket danh mục và average price chỉ được tính trên document có `status = PUBLISHED`.

Nếu cần lọc document cho aggregation nhưng vẫn muốn giữ các hit khác trong cùng response, có thể dùng filter aggregation hoặc cấu trúc aggregation riêng. Cần phân biệt query cấp cao nhất với filter đặt bên trong một aggregation.

## 7. Thực thi và lấy aggregation container từ SearchHits

Thực thi NativeQuery bằng `ElasticsearchOperations.search(...)`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> searchHits =
        operations.search(nativeQuery, ProductDocument.class);
~~~

Aggregation được trả trong `SearchHits.getAggregations()`. Kiểu trả về là abstraction `AggregationsContainer<?>`, không phải trực tiếp một map của các bucket.

Với client ELC được Spring Data Elasticsearch sử dụng, implementation cụ thể là `ElasticsearchAggregations`. Có thể chuyển wrapper về kiểu cụ thể để đọc kết quả:

~~~java
import org.springframework.data.elasticsearch.core.AggregationsContainer;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;

AggregationsContainer<?> container = searchHits.getAggregations();

if (container instanceof ElasticsearchAggregations aggregations) {
    // Đọc các ElasticsearchAggregation theo tên.
}
~~~

Đoạn kiểm tra kiểu giúp tránh cast khi response không có aggregation container hoặc đang sử dụng implementation khác.

Với một truy vấn biết chắc đã dùng ELC và có aggregation, có thể cast trực tiếp:

~~~java
ElasticsearchAggregations aggregations =
        (ElasticsearchAggregations) searchHits.getAggregations();
~~~

Không nên cast mù quáng nếu query có thể được thực thi bằng một implementation khác. Abstraction `AggregationsContainer<?>` cho phép Spring Data giữ API chung, còn wrapper ELC cung cấp quyền truy cập vào kiểu response của Java Client.

## 8. Mở wrapper để đọc Aggregate

Từ `ElasticsearchAggregations`, lấy aggregation theo tên đã khai báo:

~~~java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;
import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;

ElasticsearchAggregation categoryResult =
        aggregations.get("by_category");

Aggregate categoryAggregate = categoryResult.aggregation();
~~~

Có ba lớp cần nhớ:

1. `ElasticsearchAggregations`: tập kết quả aggregation.
2. `ElasticsearchAggregation`: wrapper cho một aggregation cụ thể.
3. `Aggregate`: kiểu union response của Elasticsearch Java API Client.

`Aggregate` có nhiều biến thể như string terms, long terms, average, sum, stats, date histogram và nhiều loại khác. Cần kiểm tra đúng biến thể trước khi đọc dữ liệu.

Ví dụ, nếu request là terms aggregation trên field keyword, response thường là string terms. Nếu request là average, response là average aggregate.

Không thể gọi `sterms()` trên kết quả average hoặc gọi `avg()` trên kết quả terms. Hãy dùng các phương thức kiểm tra biến thể như `isSterms()`, `isAvg()`, `isStats()` trước khi lấy nội dung.

## 9. Đọc bucket của terms aggregation

Giả sử request đã khai báo:

~~~java
Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(20)
        )
);
~~~

Vì `category` có mapping `keyword`, kết quả thường là biến thể string terms.

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;

Aggregate categoryAggregate =
        aggregations.get("by_category").aggregation();

if (categoryAggregate.isSterms()) {
    for (StringTermsBucket bucket :
            categoryAggregate.sterms().buckets().array()) {

        String category = bucket.key().stringValue();
        long documentCount = bucket.docCount();

        System.out.println(category + ": " + documentCount);
    }
}
~~~

Các thành phần:

- `isSterms()`: kiểm tra response có phải string terms aggregate hay không.
- `sterms()`: lấy nội dung string terms aggregate.
- `buckets().array()`: lấy danh sách bucket khi response dùng dạng array.
- `bucket.key().stringValue()`: lấy key dạng chuỗi.
- `bucket.docCount()`: số document thuộc bucket.

Java Client dùng kiểu `FieldValue` cho key của string terms bucket. Với field keyword, đọc giá trị bằng `stringValue()`.

### Field numeric cho terms aggregation

Nếu nhóm theo field numeric, response có thể là long terms hoặc double terms thay vì string terms. Ví dụ field `rating` kiểu long có thể trả biến thể long terms:

~~~java
Aggregate ratingAggregate =
        aggregations.get("by_rating").aggregation();

if (ratingAggregate.isLterms()) {
    ratingAggregate.lterms().buckets().array().forEach(bucket -> {
        long rating = bucket.key();
        long count = bucket.docCount();

        System.out.println(rating + ": " + count);
    });
}
~~~

Kiểu biến thể response phụ thuộc mapping của field và loại aggregation. Đừng giả định mọi terms aggregation đều là `StringTermsAggregate`.

## 10. Đọc metric aggregation

Metric aggregation không có danh sách bucket như terms aggregation. Nó trả về giá trị số đã tính.

### Đọc average

~~~java
Aggregate averageAggregate =
        aggregations.get("average_price").aggregation();

if (averageAggregate.isAvg()) {
    double average = averageAggregate.avg().value();
    System.out.println("Average price: " + average);
}
~~~

### Đọc sum

~~~java
Aggregate sumAggregate =
        aggregations.get("total_price").aggregation();

if (sumAggregate.isSum()) {
    double total = sumAggregate.sum().value();
    System.out.println("Total price: " + total);
}
~~~

### Đọc stats

~~~java
Aggregate statsAggregate =
        aggregations.get("price_stats").aggregation();

if (statsAggregate.isStats()) {
    var stats = statsAggregate.stats();

    System.out.println("Count: " + stats.count());
    System.out.println("Min: " + stats.min());
    System.out.println("Max: " + stats.max());
    System.out.println("Average: " + stats.avg());
    System.out.println("Sum: " + stats.sum());
}
~~~

Với metric, cần hiểu dữ liệu đầu vào và đơn vị đo. Ví dụ nếu `price` được lưu dưới dạng minor units (đồng hoặc xu), kết quả average và sum cũng dùng đơn vị đó. Không tự chuyển sang đơn vị tiền lớn hơn nếu chưa xác định quy tắc làm tròn.

## 11. Đọc sub-aggregation bên trong bucket

Aggregation có thể lồng nhau. Ví dụ:

- Nhóm sản phẩm theo category.
- Trong từng category, tính giá trung bình.

Khai báo:

~~~java
Aggregation byCategoryWithAverage = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(20)
        )
        .aggregations(
                "average_price",
                Aggregation.of(sub -> sub
                        .avg(avg -> avg.field("price"))
                )
        )
);
~~~

Khi đọc kết quả, mỗi bucket có map sub-aggregation riêng:

~~~java
Aggregate categoryAggregate =
        aggregations.get("category_with_average").aggregation();

if (categoryAggregate.isSterms()) {
    for (var bucket :
            categoryAggregate.sterms().buckets().array()) {

        String category = bucket.key().stringValue();
        long count = bucket.docCount();

        Aggregate averagePriceAggregate =
                bucket.aggregations().get("average_price");

        double averagePrice = averagePriceAggregate.avg().value();

        System.out.println(
                category + ": count=" + count
                        + ", averagePrice=" + averagePrice
        );
    }
}
~~~

Trong ví dụ:

- Bucket cha đại diện cho một category.
- `bucket.docCount()` là số document trong category đó.
- `bucket.aggregations().get("average_price")` lấy sub-aggregation theo tên.
- `avg().value()` trả giá trung bình trong chính bucket cha.

Sub-aggregation được tính trên tập document của bucket cha, không phải trên toàn bộ tập document của index.

Nếu cần đọc sub-aggregation có kiểu khác, vẫn phải kiểm tra biến thể `Aggregate` tương ứng.

## 12. Kết hợp nhiều kiểu aggregation trong một request

Một dashboard có thể cần cả bucket và metric:

~~~java
Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t.field("category").size(20))
);

Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg.field("price"))
);

Aggregation priceStats = Aggregation.of(a -> a
        .stats(stats -> stats.field("price"))
);

NativeQuery dashboardQuery = NativeQuery.builder()
        .withQuery(publishedOnly)
        .withAggregation("by_category", byCategory)
        .withAggregation("average_price", averagePrice)
        .withAggregation("price_stats", priceStats)
        .build();

SearchHits<ProductDocument> dashboardHits =
        operations.search(dashboardQuery, ProductDocument.class);
~~~

Sau khi thực thi, đọc từng aggregation bằng đúng tên:

~~~java
ElasticsearchAggregations dashboardAggregations =
        (ElasticsearchAggregations) dashboardHits.getAggregations();

Aggregate categories =
        dashboardAggregations.get("by_category").aggregation();

Aggregate average =
        dashboardAggregations.get("average_price").aggregation();

Aggregate stats =
        dashboardAggregations.get("price_stats").aggregation();
~~~

Nên tách phần đọc kết quả thành các hàm hoặc mapper riêng khi dashboard có nhiều aggregation. Điều này giúp service không bị trộn lẫn logic tạo query với logic chuyển response thành DTO.

## 13. Chỉ lấy aggregation, không lấy document hits

Nếu màn hình chỉ cần số liệu tổng hợp, việc trả về nhiều document hits là không cần thiết. Có thể đặt số hit tối đa bằng 0 trong query:

~~~java
NativeQuery aggregationOnlyQuery = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .withAggregation("average_price", averagePrice)
        .withMaxResults(0)
        .build();
~~~

Khi đó, response vẫn chứa aggregation results, nhưng không yêu cầu trả danh sách document trong hits.

Đây là cách hữu ích cho dashboard hoặc API thống kê. `SearchHits.getTotalHits()` và aggregation bucket count là hai thông tin khác nhau:

- `getTotalHits()` nói về số document khớp query.
- `bucket.docCount()` nói về số document nằm trong bucket.
- Metric aggregation trả giá trị tổng hợp, không phải số document hits được trả về.

Nếu cần cả danh sách document lẫn thống kê, giữ page size phù hợp và đọc cả hai phần từ cùng response.

## 14. Date histogram aggregation

Date histogram gom document theo khoảng thời gian như ngày, tuần hoặc tháng. Đây là cách phổ biến để vẽ biểu đồ số lượng đơn hàng hoặc doanh thu theo thời gian.

Khai báo theo tháng:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.CalendarInterval;

Aggregation byMonth = Aggregation.of(a -> a
        .dateHistogram(d -> d
                .field("createdAt")
                .calendarInterval(CalendarInterval.Month)
        )
);
~~~

Gắn vào NativeQuery:

~~~java
NativeQuery monthlyQuery = NativeQuery.builder()
        .withQuery(publishedOnly)
        .withAggregation("products_by_month", byMonth)
        .withMaxResults(0)
        .build();
~~~

Kết quả date histogram chứa các bucket theo mốc thời gian. Mỗi bucket thường có:

- Key timestamp (milliseconds).
- Key dạng chuỗi nếu response có `key_as_string`.
- Document count.
- Sub-aggregation nếu được khai báo.

Ví dụ response rút gọn:

~~~json
{
  "aggregations": {
    "products_by_month": {
      "buckets": [
        {
          "key_as_string": "2026-09-01T00:00:00.000Z",
          "key": 1788220800000,
          "doc_count": 120
        },
        {
          "key_as_string": "2026-10-01T00:00:00.000Z",
          "key": 1788220800000,
          "doc_count": 145
        }
      ]
    }
  }
}
~~~

Khi dùng date histogram, cần xác định timezone, calendar interval hay fixed interval theo nghiệp vụ. Tháng theo lịch khác với một khoảng cố định 30 ngày. Nếu báo cáo theo múi giờ địa phương, cấu hình timezone phù hợp để ranh giới ngày/tháng không bị lệch.

## 15. Terms aggregation có giới hạn bucket

Terms aggregation không mặc định trả mọi giá trị khác nhau. Tham số `size` giới hạn số bucket trả về, thường sắp xếp theo document count giảm dần.

Ví dụ:

~~~java
Aggregation topCategories = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(10)
        )
);
~~~

Request này chỉ yêu cầu tối đa 10 category. Nếu có 200 category, 190 category còn lại không xuất hiện trong kết quả đó.

Một số điểm cần nhớ:

- `size` là số bucket trả về, không phải số document trong mỗi bucket.
- `shard_size` ảnh hưởng số bucket mỗi shard gửi về coordinator và có thể ảnh hưởng độ chính xác của top buckets.
- Với cardinality lớn và cần duyệt toàn bộ bucket, cân nhắc composite aggregation thay vì tăng `size` tùy tiện.
- Nếu sort theo metric sub-aggregation hoặc theo key, cần cấu hình order rõ ràng.

Đừng dùng top 10 terms rồi coi tổng số document của 10 bucket là tổng số document toàn index. Các bucket bị bỏ qua có thể chứa document còn lại.

## 16. Đọc aggregation an toàn và chuyển thành DTO

Không nên để controller phụ thuộc trực tiếp vào kiểu response thấp của Elasticsearch Java Client. Service có thể đọc wrapper và chuyển dữ liệu thành DTO của ứng dụng.

Ví dụ DTO:

~~~java
public record CategoryCount(
        String category,
        long count
) {
}
~~~

Mapper đọc terms result:

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;

public List<CategoryCount> readCategoryCounts(
        ElasticsearchAggregations aggregations
) {
    ElasticsearchAggregation result =
            aggregations.get("by_category");

    Aggregate aggregate = result.aggregation();

    if (!aggregate.isSterms()) {
        throw new IllegalStateException(
                "Expected string terms aggregation"
        );
    }

    List<CategoryCount> counts = new ArrayList<>();

    for (StringTermsBucket bucket :
            aggregate.sterms().buckets().array()) {
        counts.add(new CategoryCount(
                bucket.key().stringValue(),
                bucket.docCount()
        ));
    }

    return counts;
}
~~~

Kiểu DTO tách giao diện ứng dụng khỏi cấu trúc response của client. Nếu sau này đổi tên aggregation hoặc chuyển từ terms sang composite, chỉ cần điều chỉnh mapper thay vì sửa mọi controller.

Trong service thật, nên xử lý trường hợp:

- `SearchHits.getAggregations()` là null.
- Không tìm thấy aggregation theo tên.
- Aggregate response có biến thể khác với mong đợi.
- Bucket list rỗng.
- Metric không có giá trị do không có document phù hợp.

Đừng giả định mọi query luôn trả đủ aggregation như code đang mong muốn, đặc biệt khi template hoặc filter được tạo động.

## 17. Phân biệt aggregation với group-by trong SQL

Có thể hình dung terms aggregation gần với `GROUP BY` trong SQL:

~~~sql
SELECT category, COUNT(*)
FROM products
WHERE status = 'PUBLISHED'
GROUP BY category;
~~~

Trong Elasticsearch:

- Query/filter tương ứng với phần chọn document.
- Terms aggregation tương ứng với nhóm theo category.
- `doc_count` tương ứng số document trong bucket.
- Metric aggregation tương ứng hàm tổng hợp như AVG, SUM, MIN, MAX.

Tuy nhiên, Elasticsearch aggregation có các đặc tính riêng:

- Kết quả phân tán qua nhiều shard rồi được hợp nhất.
- Terms aggregation có giới hạn số bucket và có thể có sai số phân phối trong một số cấu hình.
- Bucket và sub-aggregation có thể lồng nhau nhiều cấp.
- Aggregation làm việc trên field đã được lập chỉ mục/doc values, không phải thao tác SQL trên toàn bộ source JSON.

Không nên coi mọi aggregation đều có tính chất giống một câu SQL chạy trên một bảng duy nhất.

## 18. Các lỗi thường gặp

### Import nhầm Aggregation và Aggregate

Request dùng `Aggregation`; response dùng `Aggregate`. Hai kiểu nằm cùng package nhưng có vai trò trái ngược nhau. Hãy đặt tên biến như `byCategoryAggregation` và `categoryAggregate` để dễ phân biệt.

### Đọc kết quả trực tiếp từ NativeQuery

`NativeQuery` chỉ chứa request. Kết quả nằm trong `SearchHits.getAggregations()` sau khi gọi `ElasticsearchOperations.search(...)`.

### Quên tên aggregation

Tên truyền vào `withAggregation("by_category", ...)` phải trùng tên khi đọc `aggregations.get("by_category")`. Tên sai khiến ứng dụng không tìm thấy kết quả mong đợi.

### Cast response sai kiểu

Terms trên keyword thường trả string terms; terms trên numeric có thể trả long terms hoặc kiểu khác. Average trả avg aggregate. Kiểm tra `isSterms()`, `isLterms()`, `isAvg()`, `isStats()` trước khi gọi accessor.

### Aggregation trên field text

Field text thường không phù hợp cho terms aggregation vì fielddata mặc định tắt. Dùng keyword subfield hoặc khai báo mapping keyword ngay từ đầu.

### Nghĩ rằng size là số document

`terms.size(20)` là số bucket tối đa trả về, không phải 20 document. `withMaxResults(0)` điều khiển số hit, độc lập với số bucket.

### Đọc nhầm bucket count và total hits

`SearchHits.getTotalHits()` là tổng số document khớp query. `bucket.docCount()` là số document thuộc một bucket. Hai số có thể khác nhau và có mục đích khác nhau.

### Không kiểm tra aggregation container

Nếu response không có aggregation, `getAggregations()` có thể không có giá trị. Kiểm tra null và kiểu container trước khi cast.

### Coi terms là danh sách đầy đủ mọi giá trị

Terms aggregation giới hạn bucket theo `size`. Với cardinality lớn, cân nhắc composite aggregation và phân trang bucket.

### Bỏ qua mapping và đơn vị số

Average hoặc sum chỉ có ý nghĩa khi field numeric được mapping đúng và đơn vị dữ liệu nhất quán. Với tiền tệ, không cộng các amount khác currency nếu chưa lọc hoặc quy đổi theo nghiệp vụ.

## 19. Quy trình triển khai aggregation bằng NativeQuery

Khi xây dựng API báo cáo:

1. Xác định tập document cần tổng hợp và tạo query/filter tương ứng.
2. Kiểm tra mapping của field dùng cho bucket, metric và date histogram.
3. Chọn loại aggregation: terms, avg, sum, stats, date histogram hoặc loại phù hợp khác.
4. Tạo request `Aggregation` bằng Java API Client.
5. Gắn aggregation vào `NativeQuery` với tên ổn định.
6. Dùng `withMaxResults(0)` nếu không cần document hits.
7. Thực thi qua `ElasticsearchOperations.search(...)`.
8. Lấy `SearchHits.getAggregations()` và kiểm tra null.
9. Chuyển wrapper sang `ElasticsearchAggregations` khi đang dùng ELC.
10. Lấy `ElasticsearchAggregation` theo tên và gọi `aggregation()`.
11. Kiểm tra đúng biến thể của `Aggregate` trước khi đọc bucket hoặc metric.
12. Chuyển kết quả sang DTO của ứng dụng.
13. Kiểm tra giới hạn bucket, sai số phân phối và đơn vị dữ liệu.
14. Kiểm thử với index rỗng, không có document khớp và bucket vượt giới hạn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch 5.4 — Reference Documentation](https://docs.spring.io/spring-data/elasticsearch/reference/5.4/elasticsearch.html)
- [Spring Data Elasticsearch 5.4 — NativeQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch 5.4 — ElasticsearchAggregations API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregations.html)
- [Spring Data Elasticsearch 5.4 — ElasticsearchAggregation API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregation.html)
- [Elasticsearch — Aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html)
- [Elasticsearch Java API Client — Aggregations](https://www.elastic.co/guide/en/elasticsearch/client/java-api-client/current/aggregations.html)

## Kết luận

Trong Spring Data Elasticsearch, khai báo aggregation bằng kiểu `Aggregation` của Elasticsearch Java API Client rồi gắn vào `NativeQuery` qua `withAggregation(name, aggregation)`. Sau khi gọi `ElasticsearchOperations.search(...)`, lấy container từ `SearchHits.getAggregations()`, chuyển sang `ElasticsearchAggregations`, lấy từng `ElasticsearchAggregation` theo tên và đọc kiểu response `Aggregate` tương ứng. Luôn phân biệt request `Aggregation` với response `Aggregate`, kiểm tra đúng biến thể terms/metric, và chuyển dữ liệu tổng hợp sang DTO phù hợp với ứng dụng.
