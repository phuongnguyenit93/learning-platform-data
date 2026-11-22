# Sắp xếp theo keyword, số, ngày và nhiều trường

Elasticsearch sắp xếp document dựa trên kiểu mapping của field và giá trị được lưu trong index. Một yêu cầu sort có thể dùng chuỗi `keyword`, số, ngày giờ hoặc kết hợp nhiều field theo thứ tự ưu tiên. Trong Spring Data Elasticsearch, có thể khai báo sort cố định trong repository method, truyền `Sort` hoặc đặt sort vào `Pageable`; với các tùy chọn nâng cao như missing values, multi-value mode hay nested sort, cần kiểm soát Query DSL chi tiết hơn.

Điều quan trọng là field phải có mapping phù hợp và cấu trúc hỗ trợ sort. Field `text` dùng để tìm kiếm toàn văn thường không thể sort trực tiếp; field `keyword`, số và ngày giờ thường có doc values để Elasticsearch đọc giá trị hiệu quả.

## 1. Cách Elasticsearch sắp xếp kết quả

Sort được khai báo trong phần `sort` của Search API. Elasticsearch xét tiêu chí theo thứ tự từ trái sang phải: tiêu chí đầu tiên quyết định thứ tự chính; tiêu chí tiếp theo chỉ được dùng khi các document bằng nhau ở tiêu chí trước.

Ví dụ sort theo giá tăng dần:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": { "match_all": {} },
  "sort": [
    { "price": { "order": "asc" } }
  ]
}
~~~

`asc` là tăng dần, `desc` là giảm dần. Với field số, tăng dần nghĩa là số nhỏ đứng trước. Với field ngày, tăng dần nghĩa là thời điểm cũ đứng trước. Với `keyword`, thứ tự dựa trên giá trị term, thường là thứ tự từ điển/byte của term đã được chuẩn hóa.

Sort khác với relevance ranking. Nếu không khai báo sort tường minh, truy vấn full-text thường sắp xếp theo `_score` giảm dần. Khi khai báo sort theo field, kết quả được sắp theo field đó; `_score` chỉ được dùng nếu được thêm làm một tiêu chí sort.

## 2. Điều kiện mapping để sort

Elasticsearch thường sử dụng **doc values** để sort theo field. Doc values là cấu trúc dữ liệu dạng cột, tối ưu cho việc đọc giá trị field trên nhiều document.

Các kiểu thường dùng để sort:

| Kiểu field | Sort thông thường | Ví dụ sử dụng |
| --- | --- | --- |
| `keyword` | Có; doc values được bật mặc định nếu không tắt. | SKU, trạng thái, category, tên chuẩn hóa. |
| `long`, `integer`, `short`, `byte` | Có; sắp xếp theo giá trị số. | Số lượng, giá tính bằng cent, thứ tự ưu tiên. |
| `float`, `double`, `scaled_float` | Có; sắp xếp theo giá trị số. | Điểm, tỷ lệ, giá trị đo. |
| `date`, `date_nanos` | Có; sắp xếp theo thời điểm. | Ngày tạo, ngày xuất bản, thời hạn. |
| `boolean` | Có theo thứ tự giá trị boolean của Elasticsearch. | Cờ active hoặc published. |
| `text` | Không có doc values mặc định nên không sort trực tiếp theo cách thông thường. | Dùng subfield `keyword` để sort theo chuỗi. |

Nếu field có `doc_values: false`, sort dựa trên doc values sẽ không khả dụng. Với `text`, Elasticsearch có `fielddata` nhưng việc bật fielddata có thể dùng nhiều heap; thiết kế thông dụng là thêm multi-field `keyword` thay vì bật fielddata chỉ để sort.

## 3. Sort theo `keyword`

Field `keyword` lưu giá trị như một term nguyên vẹn, phù hợp cho exact match, aggregation và sort. Đây là lựa chọn phổ biến cho mã định danh, trạng thái, category, tên chuẩn hóa hoặc giá trị cần sắp xếp theo chuỗi.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "sku": { "type": "keyword" },
      "status": { "type": "keyword" },
      "category": { "type": "keyword" }
    }
  }
}
~~~

Sort theo SKU tăng dần:

~~~json
{
  "sort": [{ "sku": { "order": "asc" } }]
}
~~~

Sort theo trạng thái giảm dần:

~~~json
{
  "sort": [{ "status": { "order": "desc" } }]
}
~~~

### 3.1. Thứ tự chuỗi không phải thứ tự số

`keyword` sắp xếp theo chuỗi, không phân tích nội dung thành số. Nếu lưu các giá trị `"2"`, `"10"` và `"100"` trong field keyword, thứ tự chuỗi có thể khác thứ tự số mà người dùng mong đợi.

| Giá trị | Thứ tự chuỗi minh họa | Thứ tự số nếu chuyển thành số |
| --- | ---: | ---: |
| `"10"` | Trước `"2"` | Sau `2` |
| `"100"` | Trước `"2"` | Sau `10` |
| `"2"` | Sau `"100"` trong thứ tự từ điển thông thường | Trước `10` và `100` |

Nếu dữ liệu có ý nghĩa số, hãy map thành kiểu số thay vì `keyword`. Không nên sửa lỗi sort số bằng cách tự thêm số 0 vào chuỗi nếu field thực chất cần range query hoặc tính toán.

### 3.2. Chữ hoa, chữ thường và normalizer

Keyword sort mặc định không tự hiểu quy tắc alphabet của ngôn ngữ. Các giá trị `Acme`, `ACME` và `acme` có thể được xem là các term khác nhau và thứ tự có thể không giống kỳ vọng của giao diện.

Có thể dùng normalizer để chuẩn hóa giá trị trước khi lập chỉ mục. Ví dụ normalizer lowercase:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folded_keyword": {
          "type": "custom",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "brand": {
        "type": "keyword",
        "normalizer": "folded_keyword"
      }
    }
  }
}
~~~

Normalizing làm thay đổi cách term được lưu để tìm kiếm và sort. Cần kiểm tra tác động tới exact match và aggregation. Nếu cần quy tắc sắp xếp theo ngôn ngữ (collation), ví dụ quy tắc tiếng Việt có dấu, lowercase/asciifolding chưa đủ để mô phỏng thứ tự từ điển của locale. Có thể cần ICU analysis plugin và một field sort chuyên dụng được tạo theo collation phù hợp.

## 4. Sort theo chuỗi hiển thị bằng multi-field

Thuộc tính Java kiểu `String` thường cần vừa tìm kiếm toàn văn vừa sort theo chuỗi nguyên vẹn. Mapping nên dùng một field `text` chính và một subfield `keyword`:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "sort": {
            "type": "keyword",
            "normalizer": "folded_keyword",
            "ignore_above": 256
          }
        }
      }
    }
  }
}
~~~

Field chính `name` dùng cho `match` query. Subfield `name.sort` dùng cho sort, exact match hoặc aggregation. Một giá trị trong `_source` được lập chỉ mục theo cả hai cách mà không cần thêm một thuộc tính Java thứ hai.

Ví dụ sort theo tên:

~~~json
{
  "sort": [{ "name.sort": { "order": "asc" } }]
}
~~~

`ignore_above` giới hạn độ dài chuỗi được lập chỉ mục ở subfield keyword. Nếu giá trị vượt giới hạn, field chính vẫn có thể được lưu trong `_source` và tìm kiếm theo `text`, nhưng subfield `name.sort` có thể không có giá trị để sort. Chọn giới hạn dựa trên dữ liệu thật và xác định cách xử lý giá trị thiếu.

### 4.1. Khai báo multi-field trong Spring Data

Có thể mô tả multi-field bằng `@MultiField` và `@InnerField`:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "sort", type = FieldType.Keyword)
    }
)
private String name;
~~~

Các annotation mô tả mapping tương ứng với `name` kiểu text và `name.sort` kiểu keyword. Nếu cần normalizer, cấu hình nó trên inner field bằng thuộc tính được hỗ trợ bởi phiên bản Spring Data Elasticsearch của dự án hoặc khai báo mapping bằng file JSON. Hãy xác nhận mapping thực tế sau khi index được tạo.

Không bật `fielddata: true` trên `text` chỉ để sort trong trường hợp thông thường. Fielddata có thể nạp lượng lớn dữ liệu vào heap; multi-field keyword thường phù hợp hơn.

## 5. Sort theo số

Khi field được map thành kiểu số, Elasticsearch so sánh giá trị số thực tế thay vì chuỗi biểu diễn.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "priceInCents": { "type": "long" },
      "quantity": { "type": "integer" },
      "rating": { "type": "float" }
    }
  }
}
~~~

Sắp xếp theo giá tăng dần:

~~~json
{
  "sort": [{ "priceInCents": { "order": "asc" } }]
}
~~~

Sắp xếp theo điểm đánh giá giảm dần:

~~~json
{
  "sort": [{ "rating": { "order": "desc" } }]
}
~~~

### 5.1. Chọn đúng kiểu số

| Kiểu | Dùng khi |
| --- | --- |
| `byte`, `short`, `integer`, `long` | Giá trị nguyên, số lượng, số tiền lưu bằng đơn vị nhỏ nhất. |
| `float`, `double` | Giá trị thập phân và phép so sánh gần đúng phù hợp. |
| `scaled_float` | Giá trị thập phân được lưu theo hệ số scaling đã cấu hình. |

Với tiền tệ, thường nên lưu số nguyên theo đơn vị nhỏ nhất (ví dụ cent) để tránh sai số dấu phẩy động. Nếu cần nhiều loại tiền tệ, phải xác định currency và quy tắc so sánh trước khi sort; không thể so sánh trực tiếp số tiền của các currency khác nhau như cùng một đơn vị.

Không map một field số thành `keyword` chỉ vì dữ liệu đầu vào hiện được gửi dưới dạng chuỗi. Hãy chuyển đổi và xác thực kiểu dữ liệu ở biên ứng dụng trước khi index.

### 5.2. Sort theo giá trị đã tính

Nếu giá trị sort là một phép tính từ nhiều field, có thể cân nhắc:

- Tính và lưu một field dẫn xuất khi ghi document, nếu công thức ổn định và được dùng thường xuyên.
- Dùng `script` sort khi logic thực sự cần tính tại thời điểm truy vấn.

Script sort linh hoạt nhưng thường tốn chi phí hơn sort theo field có sẵn và có thể hạn chế tối ưu hóa. Nếu công thức ổn định, lưu một giá trị dẫn xuất thường dễ vận hành hơn.

## 6. Sort theo ngày và thời gian

Field ngày giờ nên được map thành `date` hoặc `date_nanos`, không phải `keyword`, để Elasticsearch hiểu giá trị theo thời gian và hỗ trợ range query, sort và aggregation theo ngày.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "createdAt": { "type": "date" },
      "publishedAt": { "type": "date" }
    }
  }
}
~~~

Sản phẩm mới nhất trước:

~~~json
{
  "sort": [{ "createdAt": { "order": "desc" } }]
}
~~~

Sản phẩm cũ nhất trước:

~~~json
{
  "sort": [{ "createdAt": { "order": "asc" } }]
}
~~~

Elasticsearch lưu và so sánh date theo giá trị thời gian chuẩn hóa. Dữ liệu ISO-8601 có offset/timezone rõ ràng giúp tránh hiểu nhầm thời điểm. Nếu ứng dụng gửi local date-time không có timezone, cần thống nhất timezone khi chuyển sang Instant hoặc giá trị epoch.

### 6.1. Định dạng ngày giờ

Có thể khai báo nhiều định dạng date được chấp nhận trong mapping:

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

Mapping format xác định cách Elasticsearch parse giá trị khi index và query. Nó không thay đổi ý nghĩa sắp xếp: document được so sánh theo thời điểm, không theo thứ tự ký tự của chuỗi ngày.

### 6.2. Sort theo ngày nhưng trả về format khác

Có thể yêu cầu format trong sort response nếu cần hiển thị giá trị sort:

~~~json
{
  "sort": [{
    "createdAt": {
      "order": "desc",
      "format": "strict_date_time"
    }
  }]
}
~~~

Format chỉ điều khiển biểu diễn giá trị sort trả về. Nó không thay đổi thứ tự so sánh hoặc dữ liệu đã lưu.

## 7. Sort theo nhiều field

Khi sort có nhiều field, Elasticsearch xử lý theo thứ tự khai báo. Field đầu là tiêu chí chính; field sau là tie-breaker khi các field trước bằng nhau.

Ví dụ danh sách sản phẩm:

1. Giá tăng dần.
2. Nếu cùng giá, sản phẩm mới hơn đứng trước.
3. Nếu cùng giá và cùng thời điểm, SKU tăng dần.

Query DSL:

~~~json
{
  "sort": [
    { "priceInCents": { "order": "asc" } },
    { "createdAt": { "order": "desc" } },
    { "sku": { "order": "asc" } }
  ]
}
~~~

Đây là sort đa tiêu chí theo thứ tự ưu tiên. Không nên đảo thứ tự các object trong mảng sort vì nó làm thay đổi kết quả.

### 7.1. Spring Data `Sort`

Repository method có thể nhận `Sort` để caller chọn nhiều tiêu chí:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;

List<ProductDocument> findByCategory(String category, Sort sort);
~~~

Gọi repository:

~~~java
Sort sort = Sort.by(
        Sort.Order.asc("priceInCents"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku"));

List<ProductDocument> products =
        productRepository.findByCategory("ACCESSORIES", sort);
~~~

Thứ tự các `Sort.Order` được giữ làm thứ tự ưu tiên. Trong ví dụ, giá được xét trước, ngày tạo là tiêu chí thứ hai và SKU là tiêu chí cuối.

### 7.2. Sort cố định trong tên repository method

Khi nghiệp vụ luôn dùng cùng thứ tự, có thể khai báo `OrderBy` trong derived query:

~~~java
List<ProductDocument> findByCategoryOrderByPriceInCentsAscCreatedAtDescSkuAsc(
        String category);
~~~

Method này tương đương với sort theo `priceInCents ASC`, `createdAt DESC`, `sku ASC`. `OrderBy` phù hợp với quy tắc cố định; `Sort` phù hợp khi caller cần lựa chọn thứ tự lúc chạy.

### 7.3. Kết hợp sort với Pageable

`Pageable` có thể mang cả page number, page size và sort:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("priceInCents"),
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")));

Page<ProductDocument> page =
        productRepository.findByCategory("ACCESSORIES", pageable);
~~~

Kết quả trả về là trang đầu tiên gồm tối đa 20 document theo thứ tự đã khai báo. `Page` còn cung cấp metadata như `getTotalElements()`, `getTotalPages()` và `hasNext()`.

## 8. Dùng Sort trong NativeQuery

Khi truy vấn được xây dựng bằng `NativeQuery`, có thể đặt sort cùng query và pageable:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("category")
                .value("ACCESSORIES")))
        .withSort(Sort.by(
                Sort.Order.asc("priceInCents"),
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")))
        .withPageable(PageRequest.of(0, 20))
        .build();
~~~

Ví dụ này minh họa sort cơ bản qua Spring Data `Sort`. API builder có thể khác giữa các phiên bản Spring Data Elasticsearch; dùng đúng dependency của dự án và kiểm tra request được sinh ra. Với các tùy chọn Elasticsearch chuyên sâu như `mode`, `missing`, `nested` hoặc `unmapped_type`, có thể cần native sort options của Elasticsearch Java API Client hoặc request DSL tương ứng.

## 9. Missing values: document không có giá trị sort

Một số document có thể không chứa field được dùng để sort hoặc field có giá trị null. Elasticsearch cho phép điều khiển vị trí của các giá trị thiếu bằng tùy chọn `missing`.

Ví dụ đưa document thiếu giá xuống cuối:

~~~json
{
  "sort": [{
    "priceInCents": {
      "order": "asc",
      "missing": "_last"
    }
  }]
}
~~~

Có thể dùng `"_first"` để đưa giá trị thiếu lên đầu hoặc `"_last"` để đưa xuống cuối. Một số kiểu sort còn hỗ trợ giá trị thay thế tùy chỉnh phù hợp với kiểu field.

Đối với sort nhiều field, mỗi tiêu chí có thể có chính sách missing riêng. Hãy xác định rõ hành vi cho dữ liệu cũ, document chưa hoàn thiện hoặc field tùy chọn.

Không nên dùng một giá trị thay thế có thể trùng với dữ liệu hợp lệ nếu điều đó làm thay đổi thứ tự nghiệp vụ. Nếu field bắt buộc phải có, tốt hơn nên xác thực dữ liệu khi ghi và có quy trình backfill document cũ.

## 10. Field có nhiều giá trị và sort mode

Elasticsearch cho phép một field scalar chứa nhiều giá trị cùng kiểu. Ví dụ:

~~~json
{
  "productId": "P-100",
  "prices": [120, 150, 180]
}
~~~

Khi sort theo field nhiều giá trị, Elasticsearch cần chọn một giá trị đại diện. Tham số `mode` điều khiển cách chọn:

| Mode | Cách chọn giá trị |
| --- | --- |
| `min` | Giá trị nhỏ nhất. |
| `max` | Giá trị lớn nhất. |
| `sum` | Tổng các giá trị. |
| `avg` | Trung bình các giá trị. |
| `median` | Trung vị các giá trị. |

Ví dụ sort theo giá thấp nhất trong mảng:

~~~json
{
  "sort": [{
    "prices": {
      "order": "asc",
      "mode": "min"
    }
  }]
}
~~~

Ví dụ sort theo giá cao nhất:

~~~json
{
  "sort": [{
    "prices": {
      "order": "desc",
      "mode": "max"
    }
  }]
}
~~~

Với sort tăng dần, mặc định thường là `min`; với sort giảm dần, mặc định thường là `max`. Nếu ý nghĩa nghiệp vụ cần rõ ràng, hãy khai báo `mode` tường minh.

`mode` không thay đổi dữ liệu trong `_source`; nó chỉ xác định giá trị được dùng để so sánh khi sort. Với field nhiều giá trị, đừng giả định thứ tự phần tử trong mảng quyết định sort.

## 11. Sort theo field trong nested object

Khi field nằm trong một object array được mapping là `nested`, sort cần biết nested path và cách chọn phần tử liên quan. Một dot path đơn giản có thể không đủ.

Ví dụ document:

~~~json
{
  "name": "Keyboard",
  "offers": [
    { "seller": "A", "price": 150 },
    { "seller": "B", "price": 120 }
  ]
}
~~~

Mapping:

~~~json
{
  "properties": {
    "offers": {
      "type": "nested",
      "properties": {
        "seller": { "type": "keyword" },
        "price": { "type": "long" }
      }
    }
  }
}
~~~

Sort theo giá offer thấp nhất:

~~~json
{
  "sort": [{
    "offers.price": {
      "order": "asc",
      "mode": "min",
      "nested": { "path": "offers" }
    }
  }]
}
~~~

Có thể thêm `nested.filter` để chỉ xét các offer thỏa điều kiện, ví dụ seller thuộc danh sách được phép hoặc offer đang còn hiệu lực. Nếu không khai báo đúng nested path, Elasticsearch có thể từ chối query hoặc sort không theo phần tử mong muốn.

Với `object` array thông thường, Elasticsearch làm phẳng giá trị field con và không giữ ngữ nghĩa độc lập của từng object như `nested`. Chỉ dùng nested sort khi mapping field thực sự là `nested` và nghiệp vụ cần chọn giá trị từ các phần tử nested.

Spring Data `Sort` phù hợp với sort field đơn giản. Với nested sort có path, filter và mode, hãy dùng query API/native sort option có hỗ trợ cấu hình đầy đủ; không giả định `Sort.by("offers.price")` tự suy ra nested semantics.

## 12. Sort trên alias trỏ tới nhiều index

Alias có thể trỏ tới nhiều index trong thời gian migration hoặc để đọc dữ liệu nhiều phiên bản. Nếu một field có mapping khác nhau hoặc không tồn tại ở một index, sort có thể thất bại.

Elasticsearch cho phép khai báo `unmapped_type` trong sort để xử lý index không có mapping field đó:

~~~json
{
  "sort": [{
    "createdAt": {
      "order": "desc",
      "unmapped_type": "date",
      "missing": "_last"
    }
  }]
}
~~~

`unmapped_type` cho Elasticsearch biết kiểu cần dùng khi field không có mapping trong một index. Nó không sửa mapping và cũng không chuyển đổi field đã tồn tại nhưng có kiểu không tương thích. Nếu một index map `price` là keyword còn index khác map là long, cần giải quyết schema inconsistency hoặc tạo field sort tương thích trước khi truy vấn qua alias.

Trong quy trình versioned index, nên giữ mapping nhất quán cho các field được sort qua alias. `unmapped_type` chỉ là cơ chế hỗ trợ trường hợp field thật sự không tồn tại, không thay thế quản lý schema.

## 13. Sort theo `_score` và kết hợp với field

Khi tìm kiếm toàn văn, Elasticsearch mặc định xếp hạng theo `_score` giảm dần. Nếu cần ưu tiên relevance trước rồi mới sort theo thời gian hoặc giá, có thể khai báo nhiều tiêu chí:

~~~json
{
  "query": {
    "match": { "name": "wireless keyboard" }
  },
  "sort": [
    { "_score": { "order": "desc" } },
    { "createdAt": { "order": "desc" } },
    { "sku": { "order": "asc" } }
  ]
}
~~~

Trong ví dụ, score là tiêu chí đầu tiên. Ngày tạo chỉ quyết định thứ tự giữa những document có score bằng nhau; SKU là tie-breaker cuối.

Nếu sort theo giá trước `_score`, relevance không còn là tiêu chí ưu tiên chính. Hãy sắp xếp theo đúng thứ tự ưu tiên của trải nghiệm người dùng.

## 14. Thứ tự ổn định khi phân trang

Sort nhiều field không chỉ giúp trình bày dữ liệu mà còn giúp kết quả phân trang ổn định. Nếu chỉ sort theo `createdAt`, nhiều document có thể có cùng timestamp. Khi đó thứ tự giữa chúng không được xác định theo quy tắc nghiệp vụ.

Nên thêm một field duy nhất, có mapping hỗ trợ sort, làm tie-breaker:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku"));
~~~

Ví dụ chỉ dùng SKU làm tie-breaker nếu SKU thực sự duy nhất trong phạm vi index/tenant đang truy vấn. Nếu SKU chỉ duy nhất trong từng tenant, cần kết hợp tenant hoặc dùng một ID sort key duy nhất toàn cục.

Không nên mặc định dùng `_id` làm sort field. `_id` có các giới hạn riêng và không có doc values như field keyword thông thường. Hãy lưu một field duy nhất dành cho sort nếu use case cần tie-breaker ổn định.

Khi dữ liệu thay đổi giữa các lần lấy trang, offset pagination vẫn có thể bị lặp hoặc bỏ sót document dù sort có tie-breaker. Với tập kết quả lớn hoặc dữ liệu thay đổi liên tục, cân nhắc `search_after` kết hợp Point in Time (PIT), giữ nguyên thứ tự sort trong suốt phiên duyệt.

## 15. Kiểm soát sort field từ API

Nếu giao diện cho người dùng chọn sort, không truyền nguyên tên field do client gửi vào `Sort.by`. Hãy ánh xạ lựa chọn công khai sang field được cho phép:

~~~java
import org.springframework.data.domain.Sort;

public Sort toProductSort(String sortKey, String direction) {
    Sort.Direction order = "desc".equalsIgnoreCase(direction)
            ? Sort.Direction.DESC
            : Sort.Direction.ASC;

    String property = switch (sortKey) {
        case "price" -> "priceInCents";
        case "newest" -> "createdAt";
        case "name" -> "name.sort";
        case "sku" -> "sku";
        default -> "createdAt";
    };

    return Sort.by(new Sort.Order(order, property));
}
~~~

Đây là whitelist sort field. Trong ứng dụng thực tế, cần xác nhận tên `name.sort` được mapping metadata và phiên bản Spring Data xử lý đúng. Nếu subfield hoặc native field path không được resolve như mong muốn, dùng NativeQuery/Elasticsearch Java API Client để khai báo field sort chính xác và kiểm tra request thực tế.

Giới hạn cả page size và số tiêu chí sort được phép. Một endpoint không cần hỗ trợ mọi field trong index; chỉ mở những lựa chọn có ý nghĩa và có mapping đáp ứng.

## 16. Ví dụ entity và repository hoàn chỉnh

Entity:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "sort", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Keyword)
    private String category;

    // Constructor, getters và setters
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategoryOrderByPriceInCentsAscCreatedAtDesc(
            String category);

    List<ProductDocument> findByCategory(String category, Sort sort);

    Page<ProductDocument> findByCategory(String category, Pageable pageable);
}
~~~

Service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

public Page<ProductDocument> findProducts(String category, int pageNumber) {
    Sort sort = Sort.by(
            Sort.Order.asc("priceInCents"),
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("sku"));

    return productRepository.findByCategory(
            category, PageRequest.of(pageNumber, 20, sort));
}
~~~

Ví dụ thể hiện ba kiểu field khác nhau: `name.sort` là keyword subfield, `priceInCents` là số nguyên và `createdAt` là date. Repository nhận `Sort` hoặc `Pageable`, còn `OrderBy` dùng khi thứ tự là cố định.

## 17. Thay đổi mapping sort sau khi index đã tồn tại

Mapping field type và doc values ảnh hưởng cấu trúc index. Nếu field `name` hiện chỉ là `text` và muốn thêm subfield `name.sort`, việc sửa annotation trong code không tự lập chỉ mục lại giá trị cho document cũ.

Quy trình phổ biến:

1. Tạo index mới với mapping có multi-field keyword và normalizer cần thiết.
2. Reindex dữ liệu từ index cũ sang index mới để subfield mới được tạo cho document hiện hữu.
3. Kiểm tra sort trên các giá trị đại diện, gồm chữ hoa/thường, dấu, chuỗi dài và giá trị thiếu.
4. Chuyển alias sang index mới sau khi xác minh.

Thêm multi-field vào mapping có thể được Elasticsearch chấp nhận trong một số trường hợp, nhưng các document cũ cần được cập nhật/reindex để subfield mới có giá trị. Không giả định chỉ thêm mapping là dữ liệu lịch sử lập tức sortable.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Sort tên báo lỗi fielddata hoặc không hỗ trợ | Đang sort trực tiếp trên `text`. | Tạo subfield `keyword` và sort trên subfield. |
| Giá `"100"` đứng trước `"20"` theo cách không mong muốn | Giá được map thành `keyword`. | Dùng kiểu số như `long` hoặc `scaled_float` phù hợp. |
| Chữ hoa/chữ thường có thứ tự khó hiểu | Keyword không có normalizer hoặc yêu cầu collation theo locale. | Chuẩn hóa bằng normalizer hoặc dùng ICU collation field. |
| Document thiếu giá trị xuất hiện ở đầu/cuối không đúng | Chưa cấu hình `missing`. | Đặt `missing: "_first"` hoặc `"_last"` theo yêu cầu. |
| Sort mảng giá không đúng ý nghĩa | Chưa chọn `mode` phù hợp. | Dùng `min`, `max`, `avg`, `sum` hoặc `median` theo nghiệp vụ. |
| Nested sort không đúng | Thiếu nested path hoặc nested filter. | Khai báo nested sort đầy đủ và xác nhận mapping là `nested`. |
| Sort qua alias nhiều index thất bại | Field không có mapping ở một index hoặc mapping khác kiểu. | Chuẩn hóa schema; dùng `unmapped_type` chỉ khi field thực sự không tồn tại. |
| Kết quả phân trang bị lặp hoặc thiếu | Sort không có tie-breaker duy nhất hoặc dữ liệu thay đổi giữa các request. | Thêm sort key duy nhất; cân nhắc PIT + `search_after`. |
| Sort subfield qua Spring `Sort` không được resolve | Property path không khớp cách mapping metadata xử lý multi-field. | Kiểm tra request sinh ra hoặc dùng native sort options. |

## 19. Quy trình chọn sort cho một use case

Khi thiết kế sort, hãy xác định theo thứ tự:

1. Người dùng cần sort theo chuỗi, số, ngày hay relevance score?
2. Field có mapping đúng kiểu và doc values được bật không?
3. Với chuỗi, cần exact keyword sort hay collation theo ngôn ngữ?
4. Nếu field là text, đã có subfield keyword chuyên sort chưa?
5. Giá trị thiếu phải đứng đầu hay cuối?
6. Field có thể chứa nhiều giá trị không; nếu có, cần `mode` nào?
7. Field nằm trong nested object không; nếu có, đã khai báo nested path/filter chưa?
8. Có cần nhiều tiêu chí và tie-breaker duy nhất để phân trang ổn định không?
9. Alias có trỏ tới nhiều index với mapping tương thích không?
10. Có thể dùng `OrderBy`, `Sort` hoặc `Pageable`, hay cần NativeQuery cho tùy chọn nâng cao?
11. Kiểm tra request sort được sinh ra và thử với dữ liệu đại diện trước khi phát hành.

## 20. Tài liệu tham khảo

- [Elasticsearch — Sort search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html)
- [Elasticsearch — Keyword field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/keyword.html)
- [Elasticsearch — Numeric field types](https://www.elastic.co/guide/en/elasticsearch/reference/current/number.html)
- [Elasticsearch — Date field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/date.html)
- [Elasticsearch — Doc values](https://www.elastic.co/guide/en/elasticsearch/reference/current/doc-values.html)
- [Spring Data Elasticsearch — Query methods and sorting](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/query-methods-details.html)
- [Spring Data Elasticsearch — Mapping annotations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)

Sort theo `keyword` dùng thứ tự chuỗi; sort theo số và ngày dùng giá trị có kiểu tương ứng. Khi cần vừa tìm toàn văn vừa sort theo chuỗi, tạo multi-field `keyword` cho field `text`. Nhiều tiêu chí được xét theo thứ tự khai báo; `missing`, `mode` và nested sort điều khiển các trường hợp đặc biệt. Trong Spring Data Elasticsearch, `OrderBy`, `Sort` và `Pageable` đáp ứng nhu cầu phổ biến, còn NativeQuery giúp kiểm soát các tùy chọn sort chuyên sâu.
