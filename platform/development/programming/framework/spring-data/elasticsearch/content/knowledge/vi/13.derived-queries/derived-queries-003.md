# Between, LessThan, GreaterThan, Before và After

Khi tìm kiếm dữ liệu trong Spring Data Elasticsearch, nhiều use case cần giới hạn kết quả theo một khoảng giá trị: sản phẩm trong một khoảng giá, đơn hàng được tạo trước một thời điểm, hoặc sự kiện xảy ra sau một mốc thời gian. Các từ khóa **`Between`**, **`LessThan`**, **`GreaterThan`**, **`Before`** và **`After`** cho phép khai báo những điều kiện này ngay trong tên phương thức Repository.

Spring Data phân tích tên phương thức và tạo truy vấn range tương ứng cho Elasticsearch. Cách này giúp những điều kiện phổ biến dễ đọc và không phải tự viết Query DSL. Để truy vấn đúng, cần khai báo mapping phù hợp cho field số hoặc ngày giờ, hiểu rõ cận nào được tính vào kết quả, và chọn kiểu khoảng thời gian phù hợp với nghiệp vụ.

## 1. Range query dùng để làm gì?

Range query chọn các document có giá trị của một field nằm trong hoặc ngoài một giới hạn. Field thường là kiểu số hoặc ngày giờ.

Ví dụ document sản phẩm:

```json
{
  "sku": "SKU-1001",
  "name": "Wireless Headphones",
  "priceInCents": 12990,
  "createdAt": "2026-10-15T09:30:00Z"
}
```

Ứng dụng có thể cần các điều kiện:

- Giá từ 10.000 đến 50.000 cents.
- Giá thấp hơn 20.000 cents.
- Giá cao hơn 100.000 cents.
- Sản phẩm được tạo trước ngày bắt đầu một chiến dịch.
- Sự kiện được ghi nhận sau một thời điểm cụ thể.

Trong Elasticsearch Query DSL, các giới hạn được biểu diễn bằng những toán tử `gt`, `gte`, `lt` và `lte`:

| Toán tử | Ý nghĩa | Có tính giá trị ở biên? |
|---|---|---|
| `gt` | Greater than: lớn hơn | Không |
| `gte` | Greater than or equal: lớn hơn hoặc bằng | Có |
| `lt` | Less than: nhỏ hơn | Không |
| `lte` | Less than or equal: nhỏ hơn hoặc bằng | Có |

Đây là nền tảng để hiểu các từ khóa derived query trong Spring Data.

## 2. Khai báo mapping cho field số và ngày giờ

Trước khi viết Repository, cần khai báo field với kiểu mapping phù hợp. Ví dụ entity `ProductDocument`:

```java
package com.example.catalog.product.document;

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
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    protected ProductDocument() {
    }

    public ProductDocument(
            String id,
            String sku,
            String name,
            Long priceInCents,
            Instant createdAt) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.priceInCents = priceInCents;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public Long getPriceInCents() {
        return priceInCents;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Hai field quan trọng trong ví dụ:

- `priceInCents` dùng mapping `long`, phù hợp với các phép so sánh số nguyên.
- `createdAt` dùng mapping `date`, phù hợp với range query theo thời gian.

Ví dụ lưu giá bằng đơn vị cents (hoặc đơn vị tiền nhỏ nhất của hệ thống) giúp tránh sai số dấu phẩy động khi so sánh tiền. Nếu nghiệp vụ cần lưu số thập phân, hãy chọn mapping và cách biểu diễn phù hợp như `scaled_float` với scaling factor được thiết kế rõ ràng; không nên mặc định `double` là kiểu tiền tệ chính xác.

Với field ngày giờ, `Instant` biểu diễn một thời điểm tuyệt đối theo UTC. Điều này giúp so sánh giữa các request và dữ liệu ở nhiều múi giờ nhất quán hơn. Spring Data chuyển đổi giá trị Java sang định dạng ngày giờ Elasticsearch hỗ trợ theo cấu hình mapping/converter.

**Lưu ý:** annotation chỉ mô tả mapping mong muốn khi tạo index. Nếu index `products` đã tồn tại với kiểu field khác, sửa annotation không tự thay đổi mapping của index đang chạy. Hãy kiểm tra mapping thực tế trước khi chạy range query.

## 3. `Between`: tìm giá trị nằm trong một khoảng

`Between` dùng khi cần giới hạn cả cận dưới và cận trên. Ví dụ tìm sản phẩm có giá từ 10.000 đến 50.000 cents:

```java
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

import com.example.catalog.product.document.ProductDocument;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByPriceInCentsBetween(
        Long minPrice,
        Long maxPrice
    );
}
```

Gọi Repository:

```java
List<ProductDocument> products = productRepository
    .findByPriceInCentsBetween(10_000L, 50_000L);
```

Điều kiện `Between` trong derived query được hiểu là bao gồm hai biên: giá trị phải lớn hơn hoặc bằng cận dưới và nhỏ hơn hoặc bằng cận trên. Về mặt range query, điều kiện tương ứng là:

```json
GET products/_search
{
  "query": {
    "range": {
      "priceInCents": {
        "gte": 10000,
        "lte": 50000
      }
    }
  }
}
```

Vì vậy, sản phẩm có giá đúng 10.000 hoặc đúng 50.000 cents vẫn được đưa vào kết quả.

Tên phương thức phải dùng tên thuộc tính Java `priceInCents`, không phải tên index hoặc tên field khác nếu mapping có cấu hình đổi tên. Spring Data dựa trên metadata entity để xác định field Elasticsearch tương ứng.

### 3.1. `Between` với ngày giờ

`Between` cũng dùng được với field ngày giờ:

```java
List<ProductDocument> findByCreatedAtBetween(
    Instant from,
    Instant to
);
```

Ví dụ:

```java
Instant from = Instant.parse("2026-10-01T00:00:00Z");
Instant to = Instant.parse("2026-11-01T00:00:00Z");

List<ProductDocument> products = productRepository
    .findByCreatedAtBetween(from, to);
```

Truy vấn bao gồm cả document có `createdAt` bằng `from` và document có `createdAt` bằng `to`. Nếu `to` được dùng làm thời điểm bắt đầu của kỳ tiếp theo, việc bao gồm cả hai đầu có thể khiến một document nằm đúng ranh giới xuất hiện trong hai khoảng liên tiếp. Phần sau sẽ trình bày cách xử lý khoảng nửa mở để tránh vấn đề này.

## 4. `LessThan`: nhỏ hơn một giá trị

`LessThan` dùng khi chỉ có cận trên và không bao gồm giá trị ở cận đó.

```java
List<ProductDocument> findByPriceInCentsLessThan(Long maxPrice);
```

Gọi:

```java
List<ProductDocument> affordable = productRepository
    .findByPriceInCentsLessThan(20_000L);
```

Điều kiện tương đương:

```json
GET products/_search
{
  "query": {
    "range": {
      "priceInCents": {
        "lt": 20000
      }
    }
  }
}
```

Sản phẩm có giá 19.999 cents được khớp; sản phẩm có giá đúng 20.000 cents không được khớp.

Nếu muốn bao gồm cả giá trị ở biên, dùng `LessThanEqual`:

```java
List<ProductDocument> findByPriceInCentsLessThanEqual(Long maxPrice);
```

`LessThanEqual` tương ứng với `lte`.

## 5. `GreaterThan`: lớn hơn một giá trị

`GreaterThan` dùng khi chỉ có cận dưới và không bao gồm giá trị ở cận đó:

```java
List<ProductDocument> findByPriceInCentsGreaterThan(Long minPrice);
```

Gọi:

```java
List<ProductDocument> premiumProducts = productRepository
    .findByPriceInCentsGreaterThan(100_000L);
```

Truy vấn range tương ứng:

```json
GET products/_search
{
  "query": {
    "range": {
      "priceInCents": {
        "gt": 100000
      }
    }
  }
}
```

Document có giá 100.001 cents được khớp; document có giá đúng 100.000 cents không được khớp.

Nếu muốn bao gồm giá trị tại cận dưới, dùng `GreaterThanEqual`:

```java
List<ProductDocument> findByPriceInCentsGreaterThanEqual(Long minPrice);
```

`GreaterThanEqual` tương ứng với `gte`.

## 6. `Before` và `After`: so sánh theo thời điểm

`Before` và `After` thường được dùng khi thuộc tính là ngày giờ. Chúng thể hiện ý nghĩa thời gian rõ hơn `LessThan` và `GreaterThan`.

Ví dụ Repository:

```java
import java.time.Instant;
import java.util.List;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCreatedAtBefore(Instant cutoff);

    List<ProductDocument> findByCreatedAtAfter(Instant cutoff);
}
```

Tìm sản phẩm được tạo trước thời điểm cutoff:

```java
Instant cutoff = Instant.parse("2026-11-01T00:00:00Z");

List<ProductDocument> olderProducts = productRepository
    .findByCreatedAtBefore(cutoff);
```

Điều kiện `Before` tương ứng với `lt`:

```json
GET products/_search
{
  "query": {
    "range": {
      "createdAt": {
        "lt": "2026-11-01T00:00:00Z"
      }
    }
  }
}
```

Tìm sản phẩm được tạo sau thời điểm cutoff:

```java
List<ProductDocument> newerProducts = productRepository
    .findByCreatedAtAfter(cutoff);
```

Điều kiện `After` tương ứng với `gt`:

```json
GET products/_search
{
  "query": {
    "range": {
      "createdAt": {
        "gt": "2026-11-01T00:00:00Z"
      }
    }
  }
}
```

Document có thời điểm đúng bằng `cutoff` không thuộc kết quả của `Before` hoặc `After`, vì cả hai đều là phép so sánh nghiêm ngặt. Nếu cần bao gồm thời điểm đó, dùng `LessThanEqual` hoặc `GreaterThanEqual` với field ngày giờ:

```java
List<ProductDocument> createdAtOrBefore(Instant cutoff);
List<ProductDocument> createdAtOrAfter(Instant cutoff);
```

Trong Repository thực tế, khai báo đúng tên derived query:

```java
List<ProductDocument> findByCreatedAtLessThanEqual(Instant cutoff);
List<ProductDocument> findByCreatedAtGreaterThanEqual(Instant cutoff);
```

`Before`/`After` có thể xem là cách đặt tên theo ngữ nghĩa thời gian cho điều kiện nhỏ hơn/lớn hơn. Chúng vẫn tạo range query trên field date; không phải một loại query riêng của Elasticsearch.

## 7. Bảng so sánh các từ khóa

| Derived query keyword | Điều kiện | Range operator |
|---|---|---|
| `Between(min, max)` | `min <= value <= max` | `gte` + `lte` |
| `LessThan(max)` | `value < max` | `lt` |
| `LessThanEqual(max)` | `value <= max` | `lte` |
| `GreaterThan(min)` | `value > min` | `gt` |
| `GreaterThanEqual(min)` | `value >= min` | `gte` |
| `Before(time)` | `value < time` | `lt` |
| `After(time)` | `value > time` | `gt` |

Các từ khóa trên có thể dùng với field có kiểu phù hợp. `Before` và `After` thường giúp tên phương thức dễ hiểu hơn khi field biểu diễn thời gian; `LessThan` và `GreaterThan` thường được dùng cho số.

## 8. Kết hợp range với điều kiện khác

Một use case thực tế thường cần kết hợp range với điều kiện exact match. Ví dụ tìm sản phẩm thuộc danh mục `audio`, có giá trong khoảng 10.000–50.000 cents:

```java
List<ProductDocument> findByCategoryAndPriceInCentsBetween(
    String category,
    Long minPrice,
    Long maxPrice
);
```

Gọi Repository:

```java
List<ProductDocument> products = productRepository
    .findByCategoryAndPriceInCentsBetween(
        "audio",
        10_000L,
        50_000L
    );
```

Đây là derived query kết hợp điều kiện category với range trên giá. Field `category` nên có mapping `keyword`, còn `priceInCents` nên là field số.

Query DSL tương đương về ý nghĩa:

```json
GET products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "audio"
          }
        },
        {
          "range": {
            "priceInCents": {
              "gte": 10000,
              "lte": 50000
            }
          }
        }
      ]
    }
  }
}
```

Điều kiện lọc dạng range thường không cần tính relevance score. Khi xây query thủ công, đặt chúng trong `bool.filter` giúp thể hiện rõ đây là điều kiện lọc. Với derived query, Spring Data tạo cấu trúc query dựa trên method name.

## 9. Phân trang và sắp xếp kết quả range

Nếu khoảng giá có thể trả về nhiều sản phẩm, Repository có thể trả về `Page` và nhận `Pageable`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<ProductDocument> findByPriceInCentsBetween(
    Long minPrice,
    Long maxPrice,
    Pageable pageable
);
```

Sử dụng:

```java
PageRequest pageRequest = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "priceInCents")
);

Page<ProductDocument> page = productRepository
    .findByPriceInCentsBetween(10_000L, 50_000L, pageRequest);
```

Spring Data chuyển `Pageable` thành giới hạn và thứ tự cho truy vấn Elasticsearch. Field sort nên có kiểu hỗ trợ doc values, ví dụ field số, ngày giờ hoặc `keyword`. Không nên sort trực tiếp trên field `text` nếu mapping không có field con `keyword` phù hợp.

Với phân trang thông thường, `PageRequest` tiện lợi. Tuy nhiên, Elasticsearch giới hạn độ sâu của phân trang `from`/`size`. Nếu phải đọc hàng trăm nghìn document theo range để export hoặc xử lý batch, cần xem xét `search_after` với sort ổn định và Point in Time (PIT) theo phiên bản Elasticsearch thay vì tăng page number vô hạn.

## 10. Khoảng thời gian nửa mở: `[from, to)`

Đối với dữ liệu theo thời gian, một quy ước rất hữu ích là khoảng **bao gồm cận đầu và loại trừ cận cuối**:

\[
[from, to)
\]

Tức là:

\[
value \ge from \quad \text{và} \quad value < to
\]

Ví dụ, lấy các sự kiện trong tháng 10:

- `from = 2026-10-01T00:00:00Z`
- `to = 2026-11-01T00:00:00Z`

Điều kiện này bao gồm mọi thời điểm từ đầu tháng 10 đến ngay trước đầu tháng 11. Document đúng `2026-11-01T00:00:00Z` thuộc tháng 11, không bị đếm hai lần.

Có thể khai báo derived query kết hợp hai toán tử:

```java
List<ProductDocument> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
    Instant from,
    Instant to
);
```

Đây là cách phù hợp cho báo cáo theo ngày, tháng hoặc các cửa sổ thời gian liền kề. Nó tránh phải tính `23:59:59.999...` cho cận cuối, vốn dễ sai khi độ chính xác timestamp hoặc cách serialize thay đổi.

Nếu dùng `Between`, cả hai biên được bao gồm. Vì vậy, cần chọn giữa `Between` và khoảng nửa mở theo đúng định nghĩa nghiệp vụ.

## 11. Múi giờ, định dạng và độ chính xác ngày giờ

Elasticsearch lưu date dưới dạng giá trị số nội bộ và hiển thị theo định dạng date mapping. Range query có thể nhận giá trị ngày ISO-8601, epoch millis hoặc định dạng được mapping cho phép.

Một số lưu ý:

- Ưu tiên `Instant` cho thời điểm tuyệt đối và truyền giá trị có `Z` hoặc offset rõ ràng.
- Nếu nghiệp vụ dựa trên ngày địa phương, xác định timezone trước khi chuyển thành `Instant`.
- Không so sánh chuỗi ngày giờ tùy ý nếu mapping chưa được khai báo là `date`.
- Xác định độ chính xác timestamp. Mapping `date` thường dùng millisecond; nếu cần độ chính xác nanosecond, xem xét `date_nanos` và khả năng hỗ trợ của phiên bản Elasticsearch/Spring Data.
- Dùng cùng quy ước timezone cho dữ liệu ghi, tham số query và báo cáo.

Ví dụ chuyển ngày địa phương thành khoảng UTC:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 10, 15);

Instant from = day.atStartOfDay(zone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();
```

Hai giá trị này tạo khoảng một ngày theo lịch địa phương, sau đó được chuyển sang UTC để query. Không nên cộng cố định 24 giờ cho mọi ngày địa phương nếu timezone có quy tắc chuyển giờ mùa hè; dùng `LocalDate` và `ZoneId` để xác định đầu ngày kế tiếp.

## 12. Xử lý giá trị biên và tham số đầu vào

Trước khi gọi Repository, nên kiểm tra điều kiện đầu vào:

```java
public List<ProductDocument> searchByPriceRange(Long min, Long max) {
    if (min == null || max == null) {
        throw new IllegalArgumentException("Price bounds are required");
    }

    if (min < 0 || max < 0) {
        throw new IllegalArgumentException("Price cannot be negative");
    }

    if (min > max) {
        throw new IllegalArgumentException(
            "Minimum price must not exceed maximum price"
        );
    }

    return productRepository.findByPriceInCentsBetween(min, max);
}
```

Ví dụ trên thể hiện kiểm tra cận dưới/cận trên trước khi truy vấn. Quy tắc cho phép giá bằng 0 hay không phụ thuộc nghiệp vụ. Nếu API cho phép bỏ trống một cận, Service có thể chọn method `GreaterThanEqual` hoặc `LessThanEqual` tương ứng thay vì gửi một tham số null vào `Between`.

Các field không tồn tại hoặc có giá trị null trong document thường không khớp range query. Nếu hệ thống cần phân biệt “không có giá” với “giá bằng 0”, hãy thiết kế field và query rõ ràng; không coi null là một giá trị số.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Range query trả về rỗng dù dữ liệu có vẻ nằm trong khoảng | Field mapping là `text`/`keyword` thay vì kiểu số/date | Kiểm tra mapping thực tế và dùng kiểu field phù hợp. |
| Giá trị đúng cận không xuất hiện | Dùng `LessThan`/`GreaterThan` hoặc `Before`/`After` vốn loại trừ biên | Dùng `LessThanEqual`, `GreaterThanEqual` hoặc `Between` khi cần bao gồm biên. |
| Document ở ranh giới hai tháng bị đếm hai lần | Dùng `Between` bao gồm cả hai đầu cho các kỳ liền nhau | Dùng khoảng `[from, to)` với `GreaterThanEqual` và `LessThan`. |
| Query ngày lệch một ngày | Chuyển timezone không nhất quán hoặc dùng đầu/cuối ngày theo UTC thay vì timezone nghiệp vụ | Tạo `Instant` từ `LocalDate` và `ZoneId` phù hợp. |
| So sánh tiền không như mong muốn | Dùng số thực dấu phẩy động cho giá trị cần chính xác | Lưu đơn vị tiền nhỏ nhất bằng số nguyên hoặc dùng scaled decimal mapping. |
| Derived query không được tạo | Tên property trong method không khớp entity hoặc keyword không được phiên bản hỗ trợ | Kiểm tra property, import và tài liệu phiên bản Spring Data. |
| Sort range result lỗi | Sort trên field `text` không có keyword subfield | Sort trên field số/date hoặc subfield `keyword`. |
| Query không trả document thiếu field | Range query không khớp document không có giá trị field | Xử lý missing field riêng nếu nghiệp vụ yêu cầu. |

Khi điều tra, hãy kiểm tra ba điểm theo thứ tự: tên property trong method, mapping thật trên index, và giá trị đã được lưu trong `_source`. Tên method đúng nhưng mapping sai vẫn có thể tạo truy vấn không có kết quả.

## 14. Khi nào nên dùng derived query và khi nào dùng Query DSL?

Derived query phù hợp khi điều kiện ngắn gọn và có thể diễn đạt rõ bằng tên phương thức:

```java
Page<ProductDocument> findByPriceInCentsBetween(
    Long min,
    Long max,
    Pageable pageable
);
```

Khi query cần nhiều nhóm `bool`, nested field, aggregation, script, function score hoặc điều kiện động phức tạp, tên method có thể trở nên khó đọc. Khi đó, có thể chuyển use case sang `ElasticsearchOperations` với `NativeQuery` hoặc một repository fragment chuyên trách.

Một range query viết trực tiếp trong Elasticsearch DSL có dạng:

```json
{
  "range": {
    "createdAt": {
      "gte": "2026-10-01T00:00:00Z",
      "lt": "2026-11-01T00:00:00Z"
    }
  }
}
```

Đây là khoảng nửa mở `[from, to)`. Dù dùng derived query hay Query DSL, semantics của cận phải được xác định giống nhau và kiểm thử bằng dữ liệu tại đúng biên.

## 15. Kiểm thử điều kiện range

Range query rất dễ sai ở cận. Một integration test nên tạo document ở các giá trị ngay dưới, đúng bằng và ngay trên biên.

Ví dụ với khoảng giá từ 10.000 đến 20.000 cents:

| Document | Giá | Kết quả `Between(10000, 20000)` |
|---|---:|---|
| A | 9.999 | Không khớp |
| B | 10.000 | Khớp |
| C | 15.000 | Khớp |
| D | 20.000 | Khớp |
| E | 20.001 | Không khớp |

Với `LessThan(20000)`, document có giá đúng 20.000 không khớp. Với `GreaterThan(10000)`, document có giá đúng 10.000 không khớp.

Ví dụ test Repository với Elasticsearch integration test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProductRepositoryRangeTest {

    @Autowired
    private ProductRepository productRepository;

    @BeforeEach
    void setUp() {
        productRepository.deleteAll();

        Instant now = Instant.parse("2026-10-15T00:00:00Z");
        productRepository.saveAll(List.of(
            new ProductDocument("p1", "SKU-1", "Below", 9_999L, now),
            new ProductDocument("p2", "SKU-2", "Lower edge", 10_000L, now),
            new ProductDocument("p3", "SKU-3", "Middle", 15_000L, now),
            new ProductDocument("p4", "SKU-4", "Upper edge", 20_000L, now),
            new ProductDocument("p5", "SKU-5", "Above", 20_001L, now)
        ));
    }

    @Test
    void betweenIncludesBothBounds() {
        List<ProductDocument> result = productRepository
            .findByPriceInCentsBetween(10_000L, 20_000L);

        assertThat(result)
            .extracting(ProductDocument::getId)
            .containsExactlyInAnyOrder("p2", "p3", "p4");
    }

    @Test
    void lessThanExcludesTheUpperBound() {
        List<ProductDocument> result = productRepository
            .findByPriceInCentsLessThan(20_000L);

        assertThat(result)
            .extracting(ProductDocument::getId)
            .containsExactlyInAnyOrder("p1", "p2", "p3");
    }
}
```

Đây là ví dụ minh họa cách kiểm tra semantics. Test cần một Elasticsearch instance tương thích và mapping `products` được tạo đúng. Nếu test dùng index tồn tại từ trước, cần xóa/tạo lại index test để tránh mapping cũ ảnh hưởng kết quả. Trong môi trường test, `deleteAll()` chỉ xóa document theo Repository; nó không thay thế việc quản lý index/mapping.

## 16. Tóm tắt cách chọn từ khóa

- Dùng `Between` khi cần một khoảng có cả cận dưới và cận trên, và muốn bao gồm hai biên.
- Dùng `LessThan` khi cần giá trị nhỏ hơn cận trên, không bao gồm biên.
- Dùng `GreaterThan` khi cần giá trị lớn hơn cận dưới, không bao gồm biên.
- Dùng `Before` cho thời điểm trước một mốc và `After` cho thời điểm sau một mốc; hai điều kiện này cũng loại trừ thời điểm đúng bằng mốc.
- Dùng `LessThanEqual` và `GreaterThanEqual` khi cần bao gồm một biên.
- Với các khoảng thời gian liên tiếp, ưu tiên `[from, to)` bằng `GreaterThanEqual` kết hợp `LessThan` để không trùng dữ liệu tại ranh giới.

Điều quan trọng nhất là hiểu chính xác biên của range, dùng mapping số/ngày giờ tương ứng, thống nhất timezone và kiểm thử document ở ngay các giá trị biên. Khi các yếu tố này rõ ràng, derived query của Spring Data Elasticsearch giúp biểu đạt điều kiện tìm kiếm ngắn gọn, dễ đọc và dễ bảo trì.
