# Range query cho số và thời gian

Trong tìm kiếm toàn văn, ứng dụng thường cần kết hợp điều kiện văn bản với điều kiện về giá, số lượng, điểm đánh giá hoặc thời gian. Ví dụ, người dùng tìm sản phẩm có tên chứa “keyboard”, giá từ 50 đến 200, được cập nhật trong 30 ngày gần nhất. Phần tìm kiếm văn bản có thể dùng match query, còn các giới hạn số và thời gian được biểu diễn bằng range query.

Elasticsearch cung cấp range query để tìm document có giá trị field nằm trong một khoảng. Spring Data Elasticsearch hỗ trợ xây dựng loại truy vấn này qua Criteria API, NativeQuery và query JSON khai báo trong repository. Chọn cách phù hợp giúp truy vấn rõ ràng, kiểm soát được ranh giới và tận dụng mapping đúng kiểu dữ liệu.

## 1. Range query là gì?

Range query chọn document dựa trên một hoặc nhiều giới hạn của field. Các toán tử cơ bản:

| Toán tử | Ý nghĩa | Bao gồm giá trị biên? |
| --- | --- | --- |
| gt | Greater than: lớn hơn | Không bao gồm cận dưới |
| gte | Greater than or equal: lớn hơn hoặc bằng | Có bao gồm cận dưới |
| lt | Less than: nhỏ hơn | Không bao gồm cận trên |
| lte | Less than or equal: nhỏ hơn hoặc bằng | Có bao gồm cận trên |

Ví dụ tìm sản phẩm có giá từ 100 đến 500, bao gồm cả hai đầu:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 100,
        "lte": 500
      }
    }
  }
}
~~~

Nếu cần giá lớn hơn 100 và nhỏ hơn 500, không bao gồm hai biên:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gt": 100,
        "lt": 500
      }
    }
  }
}
~~~

Range query không phân tích văn bản như match query. Nó so sánh giá trị theo kiểu dữ liệu của field trong mapping. Vì vậy, kiểu mapping phải đúng với ý nghĩa của dữ liệu.

## 2. Mapping cho field số

Elasticsearch hỗ trợ nhiều kiểu số, tùy phạm vi và độ chính xác cần lưu:

| Elasticsearch type | Trường hợp thường dùng |
| --- | --- |
| byte | Số nguyên rất nhỏ |
| short | Số nguyên trong phạm vi nhỏ |
| integer | Số nguyên 32-bit |
| long | Số nguyên 64-bit |
| unsigned_long | Số nguyên không âm có phạm vi lớn |
| half_float | Số thực độ chính xác thấp |
| float | Số thực 32-bit |
| double | Số thực 64-bit |
| scaled_float | Số thực được lưu theo hệ số scale |

Không nên chọn kiểu chỉ vì Java property có kiểu tương tự. Hãy dựa trên phạm vi giá trị, độ chính xác, dung lượng và cách nghiệp vụ so sánh.

### 2.1. Khai báo numeric mapping bằng Spring Data

Ví dụ entity sản phẩm có giá, số lượng tồn kho và điểm đánh giá:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private double price;

    @Field(type = FieldType.Integer)
    private int stockQuantity;

    @Field(type = FieldType.Float)
    private float rating;

    // Constructors, getters và setters
}
~~~

Mapping JSON tương ứng có thể viết:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "name": {
      "type": "text"
    },
    "price": {
      "type": "double"
    },
    "stockQuantity": {
      "type": "integer"
    },
    "rating": {
      "type": "float"
    }
  }
}
~~~

Annotation Spring Data giúp sinh mapping khi tạo index theo metadata entity. Nếu index đã tồn tại, thay đổi annotation không tự sửa mapping cũ. Luôn kiểm tra mapping thực tế bằng:

~~~http
GET /catalog-products/_mapping
~~~

### 2.2. Lưu tiền tệ và độ chính xác

Không nên dùng số thực nhị phân để biểu diễn tiền nếu nghiệp vụ cần so sánh chính xác đến từng đơn vị nhỏ nhất. Ví dụ, thay vì lưu 19.99 dưới dạng double, có thể lưu 1999 cents dưới dạng long:

~~~java
@Field(type = FieldType.Long)
private long priceInCents;
~~~

Range query trên priceInCents sẽ so sánh số nguyên chính xác. Ứng dụng chịu trách nhiệm chuyển đổi từ đơn vị tiền tệ sang đơn vị nhỏ nhất và định dạng khi hiển thị.

Một lựa chọn khác là Elasticsearch type scaled_float. Ví dụ mapping JSON:

~~~json
{
  "properties": {
    "price": {
      "type": "scaled_float",
      "scaling_factor": 100
    }
  }
}
~~~

Với scaling_factor bằng 100, dữ liệu được lưu nội bộ theo giá trị đã nhân hệ số, phù hợp với hai chữ số thập phân. Chọn hệ số dựa trên độ chính xác nghiệp vụ. Hãy kiểm tra cách Spring Data phiên bản đang dùng ánh xạ BigDecimal và khai báo scaled_float; không nên giả định mọi kiểu Java số thập phân đều tự tạo mapping mong muốn.

### 2.3. Range query trên field số dạng mảng

Một field số có thể chứa nhiều giá trị. Range query sẽ khớp document nếu có ít nhất một giá trị trong field thỏa mãn khoảng được chỉ định.

Ví dụ:

~~~json
{
  "priceHistory": [80, 120, 250]
}
~~~

Query tìm giá trị từ 100 đến 150 sẽ khớp document này vì có giá trị 120. Range query không yêu cầu mọi phần tử trong mảng đều nằm trong khoảng.

Nếu nghiệp vụ cần xác định mối quan hệ giữa nhiều thuộc tính trong cùng một phần tử của mảng object, cần cân nhắc nested mapping và nested query; range query thông thường trên các field object có thể không giữ quan hệ theo từng phần tử.

## 3. Mapping cho field thời gian

Elasticsearch thường lưu date dưới dạng số epoch milliseconds nội bộ, nhưng cho phép gửi giá trị ngày giờ dưới dạng chuỗi theo format đã khai báo hoặc dạng số phù hợp.

Mapping date mặc định thường chấp nhận ISO date-time và epoch milliseconds. Khi ứng dụng có format riêng, cần khai báo rõ để dữ liệu ghi và range query sử dụng cùng quy ước.

### 3.1. Các kiểu thời gian trong Java

| Java type | Ý nghĩa |
| --- | --- |
| Instant | Một thời điểm tuyệt đối trên timeline, thường biểu diễn theo UTC |
| OffsetDateTime | Ngày giờ kèm UTC offset |
| ZonedDateTime | Ngày giờ gắn với múi giờ có quy tắc DST |
| LocalDate | Ngày lịch, không có giờ hoặc múi giờ |
| LocalDateTime | Ngày giờ địa phương, không chứa offset/múi giờ |
| Date | Thời điểm kiểu cũ, độ chính xác milliseconds |

Với dữ liệu sự kiện như createdAt, paidAt hoặc lastUpdatedAt, Instant thường là lựa chọn rõ nghĩa vì biểu diễn một thời điểm tuyệt đối. Với ngày sinh hoặc ngày hiệu lực chỉ có ý nghĩa lịch, LocalDate có thể phù hợp hơn. Tránh dùng LocalDateTime cho một sự kiện toàn cầu nếu không có quy tắc múi giờ rõ ràng.

### 3.2. Khai báo date mapping

Ví dụ:

~~~java
import java.time.Instant;

import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(type = FieldType.Date, format = DateFormat.date_time)
private Instant createdAt;
~~~

Mapping JSON tương ứng:

~~~json
{
  "properties": {
    "createdAt": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

Format gồm nhiều lựa chọn được ngăn bằng ||. Elasticsearch thử các format theo danh sách để parse giá trị đầu vào. Hãy chỉ thêm format thực sự cần thiết; format quá rộng có thể khiến dữ liệu không đồng nhất và khó kiểm soát.

### 3.3. Date format tùy chỉnh

Nếu hệ thống phải nhận một format riêng, có thể khai báo pattern:

~~~java
@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "uuuu-MM-dd HH:mm:ss"
)
private Instant importedAt;
~~~

Mapping JSON tương ứng có thể là:

~~~json
{
  "properties": {
    "importedAt": {
      "type": "date",
      "format": "uuuu-MM-dd HH:mm:ss"
    }
  }
}
~~~

Pattern trên không chứa múi giờ. Nếu chuỗi đầu vào không có offset, hệ thống phải có quy tắc rõ ràng để diễn giải thời gian đó. Với dữ liệu sự kiện, ưu tiên ISO-8601 có offset hoặc chuẩn hóa về UTC trước khi ghi.

### 3.4. date và date_nanos

Elasticsearch có hai kiểu thời gian thường gặp:

- date: độ chính xác nội bộ theo milliseconds.
- date_nanos: độ chính xác tới nanoseconds, hữu ích khi cần phân biệt các sự kiện xảy ra rất sát nhau.

date_nanos có phạm vi biểu diễn hẹp hơn date và tốn chi phí hơn trong một số trường hợp. Chỉ dùng khi độ chính xác nanoseconds có ý nghĩa nghiệp vụ. Độ chính xác của Java Instant không có nghĩa index mặc định sẽ lưu đủ nanoseconds nếu mapping là date.

## 4. Range query cho số bằng Query DSL

Ví dụ tìm sản phẩm có giá từ 50 đến dưới 200:

~~~http
GET /catalog-products/_search
{
  "query": {
    "range": {
      "price": {
        "gte": 50,
        "lt": 200
      }
    }
  }
}
~~~

Ví dụ lọc số lượng tồn kho từ 1 trở lên và rating ít nhất 4:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "range": {
            "stockQuantity": {
              "gte": 1
            }
          }
        },
        {
          "range": {
            "rating": {
              "gte": 4.0,
              "lte": 5.0
            }
          }
        }
      ]
    }
  }
}
~~~

Khi nhiều range condition chỉ dùng để lọc, đặt chúng trong bool.filter để tránh tính relevance score không cần thiết. Range query bên trong filter context vẫn quyết định document có được chọn hay không.

## 5. Range query cho ngày giờ bằng Query DSL

### 5.1. Khoảng thời gian cố định

Giả sử cần tìm sự kiện trong tháng 3 năm 2026:

~~~http
GET /events/_search
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-03-01T00:00:00Z",
        "lt": "2026-04-01T00:00:00Z"
      }
    }
  }
}
~~~

Khoảng này bao gồm thời điểm bắt đầu tháng 3 và không bao gồm thời điểm bắt đầu tháng 4. Cách dùng cận trên exclusive rất hữu ích khi chia dữ liệu theo tháng/ngày vì hai khoảng liên tiếp không bị chồng lấn.

### 5.2. Khoảng thời gian có timezone

Nếu người dùng chọn tháng 3 theo giờ Việt Nam, ranh giới tháng là:

- Bắt đầu: 2026-03-01 00:00:00 +07:00.
- Kết thúc exclusive: 2026-04-01 00:00:00 +07:00.

Có thể gửi trực tiếp offset:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-03-01T00:00:00+07:00",
        "lt": "2026-04-01T00:00:00+07:00"
      }
    }
  }
}
~~~

Elasticsearch chuyển các giá trị có offset về cùng timeline để so sánh. Cách này làm rõ múi giờ của ranh giới và tránh hiểu nhầm ngày lịch của người dùng với UTC.

Một cách khác là truyền giá trị không có offset cùng thuộc tính time_zone:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-03-01T00:00:00",
        "lt": "2026-04-01T00:00:00",
        "time_zone": "+07:00"
      }
    }
  }
}
~~~

time_zone được dùng để diễn giải giá trị ngày giờ trong query và ảnh hưởng đến việc làm tròn date math. Giá trị now luôn dựa trên thời điểm hiện tại UTC; time_zone không thay đổi bản thân thời điểm now.

### 5.3. Dùng date math

Date math cho phép tạo khoảng thời gian tương đối với thời điểm hiện tại:

| Biểu thức | Ý nghĩa |
| --- | --- |
| now | Thời điểm hiện tại |
| now-1d | Một ngày trước thời điểm hiện tại |
| now-7d | Bảy ngày trước |
| now-1M | Một tháng trước theo đơn vị calendar month |
| now/d | Làm tròn về đầu ngày hiện tại |
| now-7d/d | Lùi bảy ngày rồi làm tròn về đầu ngày |
| now+1d/d | Đầu ngày kế tiếp |

Ví dụ tìm sự kiện trong 24 giờ gần nhất:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "now-24h",
        "lte": "now"
      }
    }
  }
}
~~~

Ví dụ lấy dữ liệu từ đầu ngày cách đây 6 ngày đến đầu ngày mai, theo múi giờ Việt Nam:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "now-6d/d",
        "lt": "now+1d/d",
        "time_zone": "+07:00"
      }
    }
  }
}
~~~

Date math rất tiện cho dashboard và báo cáo định kỳ. Tuy nhiên, cần phân biệt khoảng rolling 24 giờ với khoảng ngày lịch. Hai khái niệm này cho kết quả khác nhau quanh thời điểm nửa đêm.

## 6. Quy tắc biên khoảng và half-open interval

Range query cho phép chọn inclusive/exclusive độc lập ở hai đầu. Trong hệ thống xử lý dữ liệu theo thời gian, cách phổ biến là dùng khoảng nửa mở:

\[
[start,\ end)
\]

Tức là bao gồm start nhưng không bao gồm end. Ví dụ:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "2026-01-01T00:00:00Z",
      "lt": "2026-02-01T00:00:00Z"
    }
  }
}
~~~

Lợi ích:

- Không cần tạo thời điểm cuối như 23:59:59.999.
- Tránh bỏ sót dữ liệu có độ chính xác cao hơn milliseconds.
- Hai khoảng liên tiếp không trùng nhau.
- Dễ biểu diễn tháng, ngày, kỳ thanh toán hoặc cửa sổ đồng bộ.

Ví dụ tháng 1 là [01-01, 02-01), tháng 2 là [02-01, 03-01). Một document tại đúng 00:00 đầu tháng 2 chỉ thuộc tháng 2.

Với giá trị số, cũng có thể dùng khoảng nửa mở nếu cần chia bucket không chồng lấn. Tuy nhiên, nếu nghiệp vụ nói rõ “từ 100 đến 200 bao gồm 200”, hãy dùng gte/lte để thể hiện đúng quy tắc.

## 7. Range query bằng NativeQuery

NativeQuery dùng typed query DSL của Elasticsearch Java API Client. Đây là lựa chọn tốt khi cần kết hợp nhiều query, date math, time zone hoặc các tùy chọn range chi tiết.

### 7.1. Numeric range

Ví dụ tìm sản phẩm có giá từ 50 đến dưới 200:

~~~java
import co.elastic.clients.json.JsonData;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.domain.PageRequest;

Query priceRange = Query.of(q -> q
    .range(r -> r
        .number(n -> n
            .field("price")
            .gte(JsonData.of(50))
            .lt(JsonData.of(200))
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(priceRange)
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Trong Java API Client, numeric range values được biểu diễn qua JsonData. Kiểu builder cụ thể phụ thuộc phiên bản client do Spring Boot quản lý.

### 7.2. Date range

Ví dụ tìm document trong khoảng thời gian ISO-8601:

~~~java
Query dateRange = Query.of(q -> q
    .range(r -> r
        .date(d -> d
            .field("createdAt")
            .gte("2026-03-01T00:00:00Z")
            .lt("2026-04-01T00:00:00Z")
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(dateRange)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

### 7.3. Date math và time zone

Một range query dùng date math có thể biểu diễn:

~~~java
Query recentEvents = Query.of(q -> q
    .range(r -> r
        .date(d -> d
            .field("createdAt")
            .gte("now-30d/d")
            .lt("now+1d/d")
            .timeZone("+07:00")
        )
    )
);
~~~

Hãy kiểm tra method name của builder trong phiên bản Java API Client đang dùng. Với các phiên bản có generated typed DSL khác nhau, cấu trúc có thể thay đổi nhưng JSON cuối cùng phải tương đương với Query DSL mong muốn.

## 8. Kết hợp range với full-text query

Trong tìm kiếm toàn văn, thường không dùng range làm truy vấn duy nhất. Ví dụ tìm sản phẩm có tên khớp “keyboard”, giá từ 50 đến dưới 200 và được tạo trong 90 ngày gần nhất:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ],
      "filter": [
        {
          "range": {
            "price": {
              "gte": 50,
              "lt": 200
            }
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "now-90d",
              "lte": "now"
            }
          }
        }
      ]
    }
  }
}
~~~

Ý nghĩa:

- must chứa match query để tính relevance score dựa trên nội dung name.
- filter chứa range query để loại document ngoài khoảng giá hoặc thời gian.
- Các điều kiện filter không đóng góp vào relevance score.

Đây là mẫu thường gặp cho trang tìm kiếm có bộ lọc giá, ngày tạo, tồn kho, điểm đánh giá hoặc khoảng số lượng.

### 8.1. Kết hợp bằng NativeQuery

~~~java
Query combinedQuery = Query.of(q -> q
    .bool(b -> b
        .must(m -> m
            .match(match -> match
                .field("name")
                .query("keyboard")
            )
        )
        .filter(f -> f
            .range(r -> r
                .number(n -> n
                    .field("price")
                    .gte(JsonData.of(50))
                    .lt(JsonData.of(200))
                )
            )
        )
        .filter(f -> f
            .range(r -> r
                .date(d -> d
                    .field("createdAt")
                    .gte("now-90d")
                    .lte("now")
                )
            )
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(combinedQuery)
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Trong ứng dụng, giá trị tìm kiếm và các ranh giới thường đến từ request DTO. Hãy validate min không lớn hơn max, giới hạn kích thước trang và chuẩn hóa thời gian trước khi xây dựng query.

## 9. Range query bằng Criteria API

Criteria API của Spring Data Elasticsearch cho phép tạo điều kiện theo property mà không phải viết JSON hoặc typed DSL trực tiếp.

Ví dụ range trên số:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.domain.PageRequest;

Criteria criteria = Criteria.where("price")
    .greaterThanEqual(50)
    .lessThan(200);

CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 20));

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Các phép so sánh thường dùng:

- greaterThan(value): lớn hơn.
- greaterThanEqual(value): lớn hơn hoặc bằng.
- lessThan(value): nhỏ hơn.
- lessThanEqual(value): nhỏ hơn hoặc bằng.
- between(lower, upper): khoảng giữa hai giá trị theo semantics của API phiên bản đang dùng.

Khi cần kiểm soát rõ biên, nên dùng hai phương thức so sánh riêng thay vì dựa vào giả định về between.

### 9.1. Kết hợp nhiều điều kiện Criteria

~~~java
Criteria criteria = Criteria.where("price")
    .greaterThanEqual(50)
    .lessThan(200)
    .and("stockQuantity")
    .greaterThan(0);

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

Criteria phù hợp với bộ lọc động do người dùng chọn. Ví dụ, nếu người dùng chỉ nhập giá tối thiểu, ứng dụng chỉ thêm greaterThanEqual; nếu nhập cả hai biên, thêm điều kiện tương ứng.

### 9.2. Range trên thời gian

Có thể dùng giá trị thời gian tương thích với converter của Spring Data, chẳng hạn Instant hoặc chuỗi ISO-8601:

~~~java
import java.time.Instant;

Instant start = Instant.parse("2026-03-01T00:00:00Z");
Instant end = Instant.parse("2026-04-01T00:00:00Z");

Criteria dateCriteria = Criteria.where("createdAt")
    .greaterThanEqual(start)
    .lessThan(end);

CriteriaQuery query = new CriteriaQuery(dateCriteria);
~~~

Nếu dùng chuỗi ISO-8601, hãy thống nhất offset và format với mapping. Nếu cần date math như now-30d/d hoặc tùy chọn time_zone, NativeQuery thường biểu đạt trực tiếp và rõ hơn Criteria API.

## 10. Range query trong repository bằng @Query

Với truy vấn cố định, có thể dùng annotation @Query:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
        {
          "range": {
            "price": {
              "gte": ?0,
              "lt": ?1
            }
          }
        }
        """)
    List<ProductDocument> findByPriceRange(
        double minimum,
        double maximum
    );
}
~~~

@Query phù hợp khi cấu trúc query ổn định. Nếu số lượng điều kiện tùy chọn thay đổi theo request, NativeQuery hoặc CriteriaQuery dễ xây dựng và kiểm soát hơn.

Không nên nối chuỗi JSON thủ công từ dữ liệu người dùng. Dùng placeholder hoặc typed builder để tránh lỗi escaping, sai kiểu và rủi ro query injection.

## 11. Date math và các đơn vị thời gian

Date math của Elasticsearch hỗ trợ các đơn vị như:

| Ký hiệu | Đơn vị |
| --- | --- |
| y | năm |
| M | tháng |
| w | tuần |
| d | ngày |
| h hoặc H | giờ |
| m | phút |
| s | giây |
| ms | milliseconds |

Ví dụ:

- now-15m: 15 phút trước.
- now-6h: 6 giờ trước.
- now-2d: 2 ngày trước.
- now-1w: 1 tuần trước.
- now-3M: 3 tháng trước.

Chữ hoa/thường quan trọng: M là tháng, m là phút. Nhầm hai ký hiệu này có thể làm khoảng thời gian sai nghiêm trọng.

### 11.1. Làm tròn date math

Toán tử / làm tròn về đầu đơn vị:

- now/d: đầu ngày hiện tại.
- now/w: đầu tuần hiện tại theo quy tắc Elasticsearch.
- now/M: đầu tháng hiện tại.
- now/y: đầu năm hiện tại.

Ví dụ:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "now/M",
      "lt": "now+1M/M"
    }
  }
}
~~~

Query này chọn dữ liệu từ đầu tháng hiện tại đến trước đầu tháng kế tiếp. Khi có time_zone, việc làm tròn có thể được thực hiện theo múi giờ đó.

### 11.2. now không phải thời điểm của máy ứng dụng

Biểu thức now được Elasticsearch đánh giá ở phía server. Nếu ứng dụng chạy ở múi giờ khác cluster, không nên giả định now tự động dùng timezone của ứng dụng.

Đối với báo cáo theo ngày lịch của người dùng:

1. Lấy timezone người dùng từ cấu hình nghiệp vụ.
2. Tính start/end của ngày hoặc tháng trong timezone đó.
3. Chuyển thành Instant/UTC hoặc truyền local date-time cùng time_zone.
4. Dùng gte cho start và lt cho end.

Cách này làm rõ ranh giới thời gian và giúp kiểm thử dễ hơn.

## 12. Sắp xếp kết quả theo số và thời gian

Range query chỉ lọc document. Nếu cần kết quả được sắp xếp theo giá hoặc ngày tạo, hãy thêm sort riêng.

Query DSL:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 50,
        "lt": 200
      }
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "createdAt": {
        "order": "desc"
      }
    }
  ]
}
~~~

Có thể dùng Spring Data Sort:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.PageRequest;

NativeQuery query = NativeQuery.builder()
    .withQuery(priceRange)
    .withSort(Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.desc("createdAt")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Sort field phải có kiểu phù hợp và được Elasticsearch cho phép sort. Với text field, thường cần sort trên keyword subfield thay vì field text đã phân tích.

## 13. Range query và pagination

Có thể phân trang bằng Pageable:

~~~java
PageRequest pageRequest = PageRequest.of(0, 20);

NativeQuery query = NativeQuery.builder()
    .withQuery(priceRange)
    .withPageable(pageRequest)
    .build();
~~~

Offset pagination phù hợp với kết quả nhỏ và vừa. Với dữ liệu rất lớn hoặc cần duyệt sâu, hãy xem xét search_after kết hợp sort ổn định hoặc Point in Time. Range query không tự giải quyết giới hạn deep pagination.

Nếu sort theo nhiều field, nên có tie-breaker ổn định để tránh kết quả thay đổi thứ tự giữa các trang khi nhiều document có cùng giá trị sort.

## 14. Range query, exists và missing field

Range query chỉ khớp document có giá trị field phù hợp. Document thiếu field không khớp range.

Ví dụ tìm document có price từ 100 trở lên:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 100
      }
    }
  }
}
~~~

Nếu muốn chắc chắn field tồn tại và nằm trong khoảng, có thể kết hợp exists:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "exists": {
            "field": "price"
          }
        },
        {
          "range": {
            "price": {
              "gte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

Đặc biệt chú ý khi dùng must_not:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "range": {
            "price": {
              "gte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

Query này có thể khớp cả document thiếu price vì document đó không khớp range bị phủ định. Nếu nghiệp vụ muốn chỉ lấy document có price và nằm ngoài khoảng, hãy thêm exists trong filter.

## 15. Range query và range aggregation

Hai tính năng có tên gần nhau nhưng mục tiêu khác nhau:

| Tính năng | Mục đích |
| --- | --- |
| range query | Lọc document theo khoảng giá trị |
| range aggregation | Chia document thành các bucket theo khoảng để thống kê |

Ví dụ range aggregation chia sản phẩm theo giá:

~~~json
{
  "size": 0,
  "aggs": {
    "price_buckets": {
      "range": {
        "field": "price",
        "ranges": [
          { "to": 50 },
          { "from": 50, "to": 100 },
          { "from": 100, "to": 200 },
          { "from": 200 }
        ]
      }
    }
  }
}
~~~

Range aggregation trả số lượng document trong từng bucket và có thể dùng cho biểu đồ phân bố giá. Nếu chỉ cần chọn kết quả nằm trong một khoảng, dùng range query.

## 16. Range query trên field IP và range type

Ngoài số và thời gian, Elasticsearch còn hỗ trợ range query trên các kiểu dữ liệu có thứ tự như IP và các field range chuyên biệt.

### 16.1. IP range

Field kiểu ip có thể được lọc theo địa chỉ hoặc khoảng địa chỉ phù hợp:

~~~json
{
  "query": {
    "range": {
      "client.ip": {
        "gte": "192.168.1.0",
        "lte": "192.168.1.255"
      }
    }
  }
}
~~~

Đây là so sánh trên kiểu IP, không phải so sánh chuỗi thông thường. Hãy khai báo mapping type ip để Elasticsearch hiểu đúng.

### 16.2. Range field types

Elasticsearch còn có các field range chuyên biệt như integer_range, long_range, float_range, double_range, date_range và ip_range. Chúng lưu một khoảng như một giá trị field, khác với việc một document có field số đơn lẻ rồi dùng range query để lọc.

Với range field, query có thể sử dụng các quan hệ như INTERSECTS, CONTAINS hoặc WITHIN tùy loại truy vấn và kiểu dữ liệu. Đây là mô hình khác với ví dụ phổ biến price hoặc createdAt và cần thiết kế mapping riêng.

## 17. Những lỗi thường gặp

**Dùng range query trên field text.** Range không thực hiện so sánh số học trên chuỗi đã phân tích. Hãy khai báo numeric/date mapping đúng kiểu.

**Giá trị số được lưu dưới dạng keyword.** So sánh có thể theo thứ tự từ vựng thay vì số học. Kiểm tra mapping và tạo index mới nếu cần đổi kiểu.

**Nhầm gt với gte hoặc lt với lte.** Điều này làm mất hoặc nhận thừa document đúng tại ranh giới. Viết rõ quy tắc inclusive/exclusive.

**Dùng between mà không xác nhận semantics.** Khi cần biên chính xác, dùng các phép so sánh riêng và kiểm thử giá trị tại hai đầu.

**Dùng LocalDateTime mà không xác định timezone.** Cùng một chuỗi ngày giờ có thể đại diện thời điểm khác nhau. Chuẩn hóa UTC hoặc truyền offset/time_zone rõ ràng.

**Dùng m thay cho M trong date math.** m là phút, M là tháng. Kiểm tra ký hiệu và viết test cho biểu thức thời gian.

**Dùng now/d khi nghiệp vụ cần rolling 24 giờ.** now/d là đầu ngày, không phải 24 giờ trước. Dùng now-24h cho cửa sổ rolling.

**Dùng cận trên 23:59:59.999.** Có thể bỏ sót dữ liệu có độ chính xác cao hơn. Dùng khoảng nửa mở với lt đầu kỳ kế tiếp.

**Quên timezone khi lọc ngày lịch.** Một ngày theo UTC có thể lệch ngày của người dùng. Tính start/end theo timezone nghiệp vụ.

**Dùng double cho tiền tệ mà không đánh giá độ chính xác.** Cân nhắc lưu đơn vị nhỏ nhất bằng long hoặc dùng scaled_float có scaling factor phù hợp.

**Range query khớp nhiều giá trị trong mảng theo ý nghĩa không mong muốn.** Range query khớp nếu ít nhất một giá trị thỏa mãn. Nếu cần quan hệ giữa các field của cùng object, dùng nested.

**Phủ định range nhưng quên field missing.** must_not range có thể bao gồm document không có field. Kết hợp exists khi cần.

**Dùng sort trên text field.** Sort nên dùng keyword hoặc kiểu số/ngày thích hợp. Kiểm tra mapping và doc values.

## 18. Kiểm tra và debug

Khi range query trả kết quả không đúng, nên kiểm tra:

1. Mapping thực tế của field qua _mapping.
2. Dữ liệu trong _source của document mẫu.
3. Kiểu dữ liệu và format đầu vào.
4. Đơn vị số, ví dụ cents hay currency unit.
5. Ranh giới inclusive/exclusive.
6. Offset và timezone của giá trị ngày giờ.
7. Date math và cách làm tròn.
8. Field có tồn tại trong document hay không.
9. Query DSL cuối cùng được gửi tới Elasticsearch.
10. Sort và pagination có làm kết quả hiển thị khác kỳ vọng hay không.

Có thể kiểm tra cú pháp query bằng _validate/query:

~~~http
POST /catalog-products/_validate/query?explain=true
{
  "query": {
    "range": {
      "price": {
        "gte": 50,
        "lt": 200
      }
    }
  }
}
~~~

Sau đó chạy _search trên tập dữ liệu có các trường hợp biên: giá đúng 50, giá đúng 200, giá giữa khoảng, giá ngoài khoảng và document thiếu price.

Với thời gian, hãy tạo dữ liệu tại đúng start, ngay trước end, đúng end và hai phía của ranh giới ngày theo timezone để xác nhận semantics.

## 19. Ví dụ hoàn chỉnh: tìm kiếm sản phẩm theo văn bản, giá và thời gian

Giả sử yêu cầu:

- Tên sản phẩm khớp từ khóa người dùng.
- Giá từ minimumPrice trở lên và nhỏ hơn maximumPrice.
- Chỉ lấy sản phẩm được tạo trong khoảng thời gian do người dùng chọn.
- Sắp xếp theo giá tăng dần, sau đó theo ngày tạo mới nhất.
- Trả 20 kết quả mỗi trang.

DTO điều kiện tìm kiếm:

~~~java
import java.time.Instant;

public record ProductSearchCriteria(
    String text,
    Double minimumPrice,
    Double maximumPrice,
    Instant createdFrom,
    Instant createdBefore,
    int page,
    int size
) {}
~~~

Service xây dựng query:

~~~java
import co.elastic.clients.json.JsonData;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(
            ProductSearchCriteria criteria) {

        if (criteria.minimumPrice() != null
                && criteria.maximumPrice() != null
                && criteria.minimumPrice() >= criteria.maximumPrice()) {
            throw new IllegalArgumentException(
                "minimumPrice must be less than maximumPrice"
            );
        }

        if (criteria.page() < 0 || criteria.size() < 1
                || criteria.size() > 100) {
            throw new IllegalArgumentException("Invalid page or size");
        }

        Query query = Query.of(q -> q.bool(b -> {
            if (criteria.text() != null && !criteria.text().isBlank()) {
                b.must(m -> m.match(match -> match
                    .field("name")
                    .query(criteria.text())
                ));
            }

            if (criteria.minimumPrice() != null
                    || criteria.maximumPrice() != null) {
                b.filter(f -> f.range(r -> r.number(n -> {
                    n.field("price");
                    if (criteria.minimumPrice() != null) {
                        n.gte(JsonData.of(criteria.minimumPrice()));
                    }
                    if (criteria.maximumPrice() != null) {
                        n.lt(JsonData.of(criteria.maximumPrice()));
                    }
                    return n;
                })));
            }

            if (criteria.createdFrom() != null
                    || criteria.createdBefore() != null) {
                b.filter(f -> f.range(r -> r.date(d -> {
                    d.field("createdAt");
                    if (criteria.createdFrom() != null) {
                        d.gte(criteria.createdFrom().toString());
                    }
                    if (criteria.createdBefore() != null) {
                        d.lt(criteria.createdBefore().toString());
                    }
                    return d;
                })));
            }

            return b;
        }));

        NativeQuery nativeQuery = NativeQuery.builder()
            .withQuery(query)
            .withSort(Sort.by(
                Sort.Order.asc("price"),
                Sort.Order.desc("createdAt")
            ))
            .withPageable(PageRequest.of(
                criteria.page(),
                criteria.size()
            ))
            .build();

        return operations.search(nativeQuery, ProductDocument.class);
    }
}
~~~

Đây là ví dụ minh họa cách kết hợp các điều kiện tùy chọn trong typed DSL. Tên builder và kiểu JsonData có thể khác giữa các phiên bản Elasticsearch Java API Client; hãy dùng đúng dependency của dự án. Trong triển khai thực tế, cần bổ sung kiểm tra ngày bắt đầu không sau ngày kết thúc, giới hạn độ rộng khoảng thời gian và quy tắc timezone theo nghiệp vụ.

Nếu query có nhiều điều kiện động hơn, có thể xây dựng danh sách filter trước rồi kết hợp vào bool query. Với bộ lọc đơn giản, CriteriaQuery có thể ngắn hơn. Với date math hoặc tùy chọn DSL đặc thù, NativeQuery thường rõ ràng hơn.

## 20. Quy trình chọn và triển khai range query

Khi thêm bộ lọc số hoặc thời gian vào ứng dụng:

1. Xác định kiểu dữ liệu thực tế: số nguyên, số thập phân, tiền tệ, ngày lịch hay thời điểm.
2. Chọn mapping tương ứng trong Elasticsearch và xác nhận index đang dùng mapping đó.
3. Xác định rõ đơn vị và độ chính xác, ví dụ cents, kilogram, milliseconds hoặc nanoseconds.
4. Quy định cận dưới/cận trên là inclusive hay exclusive.
5. Với khoảng thời gian, thống nhất UTC/offset/timezone và dùng khoảng nửa mở nếu phù hợp.
6. Chọn range query trong NativeQuery, CriteriaQuery hoặc @Query theo mức độ động và phức tạp.
7. Kết hợp full-text match trong must với range filter trong filter context khi phù hợp.
8. Thêm sort và pagination độc lập với điều kiện range.
9. Kiểm tra dữ liệu tại hai biên và trường hợp thiếu field.
10. Theo dõi query latency và response size khi triển khai.

Range query là công cụ lọc quan trọng trong tìm kiếm toàn văn. Kết quả chính xác phụ thuộc vào mapping đúng kiểu, quy tắc biên rõ ràng và cách diễn giải thời gian nhất quán. Khi kết hợp với full-text query trong bool query, ứng dụng có thể cung cấp bộ lọc giá, số lượng và ngày tháng linh hoạt mà vẫn giữ relevance score cho phần tìm kiếm văn bản.

## 21. Tài liệu tham khảo

- [Elasticsearch - Range query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-range-query): toán tử gt/gte/lt/lte, date math và time zone.
- [Elasticsearch - Date field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/date): format date, epoch values và cách Elasticsearch lưu thời gian.
- [Elasticsearch - Numeric field types](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/number): các kiểu số và lựa chọn mapping.
- [Elasticsearch - Date math](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/api-conventions#date-math): biểu thức thời gian tương đối và làm tròn.
- [Spring Data Elasticsearch - Query methods and template](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): CriteriaQuery, NativeQuery và cách thực thi truy vấn.
- [Spring Data Elasticsearch - Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html): mapping entity và annotation field.

API builder có thể thay đổi theo phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Khi triển khai, hãy đối chiếu dependency thực tế và mapping của index đang chạy.
