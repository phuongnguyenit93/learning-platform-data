# Kiểm thử cấu trúc JSON và truy vấn sau khi gắn tham số

Khi dùng `@Query` trong Spring Data Elasticsearch, truy vấn được viết dưới dạng chuỗi JSON và có thể chứa placeholder như `?0`, `?1` để nhận tham số từ phương thức repository. Vì query là một chuỗi, lỗi có thể xuất hiện ở nhiều lớp: JSON sai cú pháp, Query DSL sai cấu trúc, tên field không khớp mapping, tham số được đặt sai kiểu hoặc giá trị sau khi binding làm thay đổi kết quả ngoài dự kiến.

Vì vậy, kiểm thử nên phân biệt hai việc. Thứ nhất là kiểm tra cấu trúc JSON và Query DSL do lập trình viên khai báo. Thứ hai là chạy truy vấn qua Spring Data với các tham số thực tế trên Elasticsearch để xác nhận binding, kiểu dữ liệu và kết quả. Chỉ kiểm tra chuỗi JSON ban đầu chưa đủ chứng minh query sau khi gắn tham số hoạt động đúng.

## 1. Các lớp cần kiểm thử

Một truy vấn JSON có tham số thường đi qua các bước:

```text
@Query JSON template
       |
       v
Spring Data repository method
       |
       |  bind ?0, ?1, ?2 ...
       v
JSON query đã gắn tham số
       |
       |  gửi qua Elasticsearch client
       v
Elasticsearch Query DSL parser
       |
       v
Thực thi trên index và mapping
       |
       v
Kết quả document / aggregation
```

Có thể kiểm thử theo các lớp sau:

| Lớp | Cần xác nhận | Ví dụ lỗi |
|---|---|---|
| Cú pháp JSON | Chuỗi sau khi thay placeholder mẫu là JSON hợp lệ | Thiếu dấu ngoặc, dấu phẩy thừa, dùng nháy đơn |
| Cấu trúc Query DSL | Các node `bool`, `term`, `range`, `match`, `sort` nằm đúng vị trí | Đặt `filter` sai cấp hoặc dùng sai tên query |
| Binding tham số | Tham số đúng vị trí, đúng kiểu và được encode an toàn | Giá trị có dấu nháy làm hỏng JSON hoặc tham số bị đặt nhầm thứ tự |
| Mapping | Field tồn tại và có kiểu tương thích với query | Dùng `term` trên field `text` trong khi cần khớp chính xác |
| Ngữ nghĩa | Kết quả đúng với dữ liệu biên và các trường hợp âm | Nhầm `gte` thành `gt`, bỏ sót điều kiện lọc |
| Vận hành | Query chạy được với phiên bản Elasticsearch/client triển khai | API hoặc kiểu query không được server hỗ trợ |

## 2. Khai báo `@Query` với placeholder

Spring Data Elasticsearch hỗ trợ placeholder vị trí trong query JSON. `?0` là tham số thứ nhất, `?1` là tham số thứ hai, tiếp tục theo thứ tự từ 0.

Ví dụ tìm sản phẩm theo trạng thái và khoảng giá:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
    {
      "bool": {
        "filter": [
          { "term": { "status": "?0" } },
          {
            "range": {
              "priceMinorUnits": {
                "gte": ?1,
                "lt": ?2
              }
            }
          }
        ]
      }
    }
    """)
    List<ProductDocument> findByStatusAndPriceRange(
            String status,
            Long minPrice,
            Long maxPrice);
}
```

Trong ví dụ:

- `?0` nhận giá trị `status` và nằm trong chuỗi JSON, vì trạng thái là chuỗi.
- `?1` nhận giá trị `minPrice` và được đặt ở vị trí JSON number, không đặt trong dấu nháy.
- `?2` nhận giá trị `maxPrice` và cũng là JSON number.

Với tham số `("PUBLISHED", 100000L, 500000L)`, ý nghĩa query sau binding là:

```json
{
  "bool": {
    "filter": [
      { "term": { "status": "PUBLISHED" } },
      {
        "range": {
          "priceMinorUnits": {
            "gte": 100000,
            "lt": 500000
          }
        }
      }
    ]
  }
}
```

Đây là JSON minh họa cho bộ tham số trên. Khi chạy thật, Spring Data thực hiện bước binding theo cơ chế của phiên bản đang dùng. Không tự nối chuỗi JSON bằng `+` để thay tham số; hãy để repository binder xử lý placeholder.

## 3. Đặt placeholder đúng kiểu JSON

Placeholder phải nằm ở vị trí phù hợp với kiểu JSON mà query cần.

| Kiểu tham số | Vị trí placeholder thường dùng | Ví dụ |
|---|---|---|
| Chuỗi | Trong dấu nháy kép | `"status": "?0"` |
| Số nguyên/số thực | Không có dấu nháy | `"gte": ?1` |
| Boolean | Không có dấu nháy | `"available": ?2` |
| Chuỗi ngày giờ | Trong dấu nháy kép | `"gte": "?3"` |
| Mảng/tập hợp | Ở vị trí value của JSON array/terms theo cách binding được hỗ trợ | `"terms": {"category": ?4}` |

Các ví dụ vị trí trên mô tả kiểu JSON mong muốn. Cần kiểm tra hỗ trợ binding cho kiểu dữ liệu cụ thể ở phiên bản Spring Data Elasticsearch của dự án, nhất là collection, object và kiểu ngày giờ.

### Chuỗi phải được bind như một giá trị JSON

Giả sử tham số là:

```text
PUBLISHED "VIP"
```

Nếu nối chuỗi thủ công vào JSON, dấu nháy kép bên trong có thể làm hỏng cú pháp. Với placeholder, truyền giá trị dưới dạng tham số repository để Spring Data xử lý theo cơ chế binding của nó.

Không nên viết:

```java
String json = "{\"term\":{\"status\":\"" + status + "\"}}";
```

Cách nối chuỗi trên dễ tạo lỗi escape và khiến dữ liệu đầu vào bị hiểu thành một phần cấu trúc query. Dùng `@Query` placeholder hoặc API query builder để tách dữ liệu khỏi cấu trúc truy vấn.

### Không đặt dấu nháy sai quanh số và Boolean

Đây là JSON number:

```json
{ "gte": 100 }
```

Đây là JSON string:

```json
{ "gte": "100" }
```

Hai dạng không giống nhau. Nếu mapping là `long`, hãy bind số ở dạng JSON number. Tương tự, Boolean phải là `true`/`false` không có dấu nháy, còn ngày giờ thường là chuỗi ISO-8601 được mapping `date` phân tích.

## 4. Kiểm tra JSON template trước khi gọi Elasticsearch

JSON template có placeholder chuỗi như `"?0"` vẫn có thể parse như JSON trước khi binding vì `?0` đang là nội dung của một JSON string. Nhưng placeholder số viết `?1` không có dấu nháy sẽ khiến template chưa phải JSON hoàn chỉnh.

Do đó, khi kiểm tra cấu trúc JSON, hãy tạo một bản mẫu với giá trị đại diện đã encode thành JSON rồi parse bằng thư viện JSON. Việc này kiểm tra cú pháp và vị trí node, nhưng chưa thay thế integration test với binder thật của Spring Data.

Ví dụ dùng Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

String template = """
{
  "bool": {
    "filter": [
      { "term": { "status": "?0" } },
      { "range": { "priceMinorUnits": { "gte": ?1, "lt": ?2 } } }
    ]
  }
}
""";

String sampleJson = template
    .replace("\"?0\"", mapper.writeValueAsString("PUBLISHED"))
    .replace("?1", mapper.writeValueAsString(100000L))
    .replace("?2", mapper.writeValueAsString(500000L));

JsonNode root = mapper.readTree(sampleJson);
```

Đoạn kiểm thử này dùng giá trị mẫu để tạo JSON hợp lệ. Trong dự án thật, nên tránh viết một bộ thay placeholder tổng quát bằng các phép `String.replace` đơn giản nếu template có thể chứa chuỗi trùng với `?1` hoặc placeholder nằm ở nhiều ngữ cảnh. Có thể giữ template nhỏ, dùng helper chỉ phục vụ fixture, hoặc kiểm tra cấu trúc bằng integration test. Không dùng helper này trong code production để thay thế cơ chế binding của Spring Data.

### Kiểm tra cấu trúc bằng JSON Pointer

Sau khi parse, có thể xác nhận các node quan trọng tồn tại và đúng kiểu:

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(root.at("/bool/filter").isArray()).isTrue();
assertThat(root.at("/bool/filter/0/term/status").asText())
    .isEqualTo("PUBLISHED");
assertThat(root.at("/bool/filter/1/range/priceMinorUnits/gte").isNumber())
    .isTrue();
assertThat(root.at("/bool/filter/1/range/priceMinorUnits/lt").asLong())
    .isEqualTo(500000L);
```

Kiểm tra theo đường dẫn giúp phát hiện trường bị đặt sai cấp hoặc vô tình biến number thành string. Với query lớn, có thể xác nhận thêm `must`, `must_not`, `should`, `sort`, `aggs` và `minimum_should_match`.

## 5. Kiểm tra mapping tương ứng

Một JSON query hợp lệ vẫn có thể sai khi field không tồn tại hoặc kiểu field không phù hợp. Ví dụ `term` thường dùng cho field `keyword`, Boolean hoặc giá trị số chính xác; `range` dùng với số và ngày.

Document mẫu:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    // Constructors, getters and setters
}
```

Mapping tương ứng cần có:

```json
{
  "properties": {
    "status": { "type": "keyword" },
    "priceMinorUnits": { "type": "long" },
    "available": { "type": "boolean" }
  }
}
```

Có thể kiểm tra mapping đang chạy bằng:

```http
GET /products/_mapping
```

Không chỉ kiểm tra annotation Java. Index có thể đã được tạo từ một phiên bản ứng dụng cũ hoặc được quản lý độc lập; mapping thực tế của Elasticsearch mới là cấu trúc được query thực thi trên đó.

## 6. Kiểm thử repository bằng Elasticsearch thật

Kiểm thử tích hợp là cách trực tiếp nhất để xác nhận Spring Data đã bind tham số, gửi query hợp lệ và nhận đúng kết quả từ Elasticsearch. Dùng một instance Elasticsearch dành riêng cho test, chẳng hạn container có version cố định tương thích với Spring Data/client của dự án.

Ví dụ repository:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
    {
      "bool": {
        "filter": [
          { "term": { "status": "?0" } },
          {
            "range": {
              "priceMinorUnits": {
                "gte": ?1,
                "lt": ?2
              }
            }
          }
        ]
      }
    }
    """)
    List<ProductDocument> findByStatusAndPriceRange(
            String status,
            Long minPrice,
            Long maxPrice);
}
```

Test nên chuẩn bị document ở cả trong và ngoài biên:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

@SpringBootTest
class ProductRepositoryQueryTest {

    @Autowired
    ProductRepository repository;

    @Autowired
    ElasticsearchOperations operations;

    @BeforeEach
    void setUp() {
        IndexOperations index = operations.indexOps(ProductDocument.class);
        if (index.exists()) {
            index.delete();
        }
        index.createWithMapping();

        repository.saveAll(List.of(
            product("p-1", "PUBLISHED", 100L),
            product("p-2", "PUBLISHED", 499L),
            product("p-3", "PUBLISHED", 500L),
            product("p-4", "DRAFT", 250L)
        ));

        index.refresh();
    }

    @Test
    void bindsStringAndNumericParameters() {
        List<ProductDocument> result =
            repository.findByStatusAndPriceRange("PUBLISHED", 100L, 500L);

        assertThat(result)
            .extracting(ProductDocument::getId)
            .containsExactlyInAnyOrder("p-1", "p-2");
    }

    private ProductDocument product(String id, String status, long price) {
        ProductDocument document = new ProductDocument();
        document.setId(id);
        document.setStatus(status);
        document.setPriceMinorUnits(price);
        return document;
    }
}
```

Ví dụ dùng `index.refresh()` sau khi nạp fixture để search nhìn thấy document ngay trong test. Trong production, không nên refresh thủ công sau mọi lần ghi vì có thể làm giảm throughput. Test cần chạy với Elasticsearch server thực tế hoặc container tương thích, không chỉ mock repository, vì mock không kiểm tra Query DSL và mapping ở server.

## 7. Kiểm thử tham số có ký tự đặc biệt

Một test quan trọng là truyền chuỗi có dấu nháy kép, dấu gạch chéo ngược, Unicode hoặc ký tự điều khiển hợp lệ. Mục tiêu là xác nhận giá trị được binding như một chuỗi JSON, không làm thay đổi cấu trúc query.

Ví dụ thêm một document có status chứa dấu nháy:

```java
@Test
void bindsStringContainingQuotesAsAValue() {
    String unusualStatus = "PUBLISHED \"VIP\"";

    ProductDocument document = product("p-quote", unusualStatus, 200L);
    repository.save(document);
    operations.indexOps(ProductDocument.class).refresh();

    List<ProductDocument> result =
        repository.findByStatusAndPriceRange(unusualStatus, 100L, 300L);

    assertThat(result)
        .extracting(ProductDocument::getId)
        .contains("p-quote");
}
```

Test này xác nhận tham số chuỗi được xử lý đúng với dữ liệu có ký tự đặc biệt. Có thể bổ sung chuỗi Unicode như `Đà Nẵng`, dấu tiếng Việt tổ hợp hoặc ký tự `\\` nếu những giá trị đó xuất hiện trong dữ liệu thật.

Không nên kiểm tra bằng cách chỉ assert chuỗi JSON chứa một đoạn con. Cùng một đoạn text có thể xuất hiện ở sai vị trí hoặc sai kiểu. Hãy parse JSON và assert node theo đường dẫn, sau đó xác nhận kết quả bằng integration test.

## 8. Kiểm thử tham số range và biên

Range query thường có lỗi do nhầm `gt`/`gte` hoặc `lt`/`lte`. Hãy tạo dữ liệu ở đúng hai biên và ngay bên trong/ngoài khoảng.

Với query:

```json
{
  "range": {
    "priceMinorUnits": {
      "gte": 100,
      "lt": 500
    }
  }
}
```

Kết quả kỳ vọng:

| Giá trị | Có được trả về? | Lý do |
|---:|---|---|
| 99 | Không | Nhỏ hơn biên dưới |
| 100 | Có | `gte` bao gồm biên dưới |
| 499 | Có | Nằm trong khoảng |
| 500 | Không | `lt` không bao gồm biên trên |
| 501 | Không | Lớn hơn biên trên |

Với ngày giờ, nên kiểm thử khoảng nửa mở `[from, to)` tương tự. Tạo document đúng tại `from`, ngay trước `to` và đúng `to` để phát hiện lỗi timezone hoặc lỗi biên.

## 9. Kiểm thử danh sách và tham số rỗng

Nếu query dùng `terms` hoặc tham số tập hợp, hãy kiểm tra:

- Danh sách có một phần tử.
- Danh sách có nhiều phần tử.
- Danh sách rỗng.
- Danh sách có phần tử trùng.
- Danh sách có giá trị null nếu DTO có thể tạo ra trường hợp này.

Không nên mặc định danh sách rỗng có nghĩa “bỏ qua filter”. Nếu API quy định danh sách rỗng là không lọc, bỏ điều kiện trước khi gọi repository. Nếu danh sách rỗng nghĩa là không có kết quả được phép, trả về danh sách rỗng ngay hoặc tạo điều kiện không khớp một cách rõ ràng.

Với tham số `null`, xác định rõ đó là giá trị hợp lệ, điều kiện bỏ qua hay lỗi validation. Placeholder không tự động loại bỏ một nhánh query chỉ vì tham số null. Với nhiều filter tùy chọn, custom repository hoặc Criteria/NativeQuery động thường phù hợp hơn một `@Query` tĩnh có nhiều placeholder.

## 10. Kiểm thử thứ tự và vị trí placeholder

Placeholder bắt đầu từ `?0`, không phải `?1`. Nếu method có ba tham số, cần xác nhận:

| Placeholder | Tham số |
|---|---|
| `?0` | Tham số thứ nhất |
| `?1` | Tham số thứ hai |
| `?2` | Tham số thứ ba |

Ví dụ method:

```java
List<ProductDocument> search(String status, Long minPrice, Long maxPrice);
```

thì `?0` phải là status, `?1` là giá tối thiểu và `?2` là giá tối đa. Đổi thứ tự tham số trong method mà quên sửa template có thể tạo query hợp lệ về cú pháp nhưng sai về ngữ nghĩa.

Đặt tên tham số mô tả rõ ý nghĩa, viết test với giá trị khác nhau dễ nhận biết và assert tập ID kết quả. Tránh dùng ba giá trị số giống nhau trong test vì nhầm thứ tự placeholder có thể không bị phát hiện.

## 11. Kiểm tra query sau binding ở mức HTTP

Trong trường hợp cần biết chính xác request body mà ứng dụng gửi tới Elasticsearch, có thể quan sát HTTP request ở môi trường kiểm thử. Một số hướng tiếp cận:

- Dùng HTTP mock server hoặc proxy kiểm thử để nhận request và lưu body.
- Dùng logging của HTTP client ở môi trường phát triển nếu phiên bản client hỗ trợ log request phù hợp.
- Dùng Elasticsearch test container và xác nhận hành vi thực tế qua kết quả query.

Khi capture request, hãy parse body như JSON và kiểm tra các giá trị đã bind. Không chỉ so sánh chuỗi raw vì thứ tự field trong JSON object không mang ý nghĩa và có thể thay đổi giữa các phiên bản client.

Nếu dùng mock server, cần cấu hình đúng transport mà Spring Data đang sử dụng. Spring Data Elasticsearch qua Elasticsearch Java API Client và các dòng cũ dùng `RestHighLevelClient` có stack HTTP khác nhau; một mock được cấu hình cho client cũ có thể không quan sát được request của client mới.

Không bật log body hoặc header nhạy cảm trong production. Query có thể chứa dữ liệu cá nhân, mã định danh, token hoặc thông tin nội bộ; nếu cần log phục vụ chẩn đoán, hãy giới hạn môi trường, quyền truy cập và thời gian lưu.

## 12. Query JSON sai cú pháp và Query DSL sai ngữ nghĩa

Hai loại lỗi này cần được phân biệt:

### JSON sai cú pháp

Ví dụ lỗi:

```json
{
  'term': {
    'status': 'PUBLISHED',
  }
}
```

JSON yêu cầu dấu nháy kép cho tên field và chuỗi, đồng thời không cho phép dấu phẩy thừa sau phần tử cuối. Dùng Jackson `readTree` hoặc parser JSON khác để phát hiện lỗi cú pháp.

### JSON hợp lệ nhưng Query DSL sai

Ví dụ:

```json
{
  "bool": {
    "filters": [
      { "term": { "status": "PUBLISHED" } }
    ]
  }
}
```

JSON trên parse được, nhưng thuộc tính đúng của bool query là `filter`, không phải `filters`. Chỉ parser Query DSL của Elasticsearch mới xác nhận đầy đủ cấu trúc và loại query có được hỗ trợ.

### Query DSL hợp lệ nhưng mapping không phù hợp

Ví dụ `term` query trên field `text` vẫn là Query DSL hợp lệ, nhưng có thể không trả kết quả như mong muốn vì field đã được phân tích. Cần đối chiếu mapping và dữ liệu được index.

## 13. Truy vấn sau binding có thể hợp lệ nhưng vẫn sai kết quả

Một query được parse thành công chưa đảm bảo kết quả nghiệp vụ đúng. Một số trường hợp:

- `gte` và `gt` bị dùng nhầm.
- `must_not` bao gồm cả document thiếu field ngoài dự kiến.
- `should` không có `minimum_should_match` trong bool query có filter/must, khiến nhánh OR chỉ tăng điểm thay vì bắt buộc khớp.
- Query dùng field `text` trong khi muốn so khớp chính xác.
- Date range được tạo theo UTC nhưng người dùng mong ngày địa phương.
- Tham số thứ tự bị đảo, ví dụ min/max bị hoán đổi.
- Danh sách rỗng hoặc null được hiểu khác quy tắc nghiệp vụ.

Vì vậy, test nên assert kết quả theo ID hoặc thuộc tính quan trọng, không chỉ assert repository không ném exception.

## 14. Tổ chức bộ kiểm thử

Có thể tách test thành các lớp:

| Loại test | Phạm vi | Mục đích |
|---|---|---|
| JSON structure test | Template và placeholder mẫu | Phát hiện lỗi cú pháp, sai node hoặc sai kiểu JSON |
| Repository integration test | Repository + Elasticsearch test server | Kiểm tra binding thực, mapping và Query DSL |
| Boundary test | Giá trị sát biên số/ngày | Xác nhận `gt`, `gte`, `lt`, `lte` |
| Special-character test | Chuỗi có dấu nháy, backslash, Unicode | Xác nhận string binding và encoding |
| Negative test | Field thiếu, null, danh sách rỗng, trạng thái không khớp | Xác nhận điều kiện loại trừ và trường hợp biên |
| Compatibility test | Phiên bản server/client được triển khai | Phát hiện khác biệt API và Query DSL |

Không nhất thiết phải tạo một test class cho từng dòng. Có thể nhóm theo repository hoặc use case, nhưng nên giữ mỗi test tập trung vào một hành vi dễ hiểu.

## 15. Ví dụ kiểm thử một repository hoàn chỉnh

Một bộ test tối thiểu nên có:

```java
@Test
void returnsOnlyDocumentsMatchingStatusAndHalfOpenPriceRange() {
    List<ProductDocument> result =
        repository.findByStatusAndPriceRange("PUBLISHED", 100L, 500L);

    assertThat(result)
        .extracting(ProductDocument::getId)
        .containsExactlyInAnyOrder("p-1", "p-2");
}

@Test
void returnsNoDocumentsWhenStatusDoesNotMatch() {
    List<ProductDocument> result =
        repository.findByStatusAndPriceRange("ARCHIVED", 100L, 500L);

    assertThat(result).isEmpty();
}

@Test
void excludesUpperRangeBoundary() {
    List<ProductDocument> result =
        repository.findByStatusAndPriceRange("PUBLISHED", 100L, 500L);

    assertThat(result)
        .extracting(ProductDocument::getId)
        .doesNotContain("p-3");
}
```

Các test này giả định fixture đã được nạp và refresh như phần trước. Chúng xác nhận đồng thời placeholder, điều kiện status, range và biên trên không bao gồm.

## 16. Những lỗi thường gặp

### JSON template parse được nhưng query sau binding hỏng

Template có thể parse khi placeholder nằm trong string nhưng giá trị được bind chứa dấu nháy hoặc ký tự escape. Kiểm tra special-character bằng integration test với binder thật.

### Đặt số trong dấu nháy

Giá trị trở thành JSON string trong khi mapping là numeric. Đặt placeholder số ở vị trí không có dấu nháy và truyền kiểu Java số phù hợp.

### Placeholder lệch thứ tự

Thay đổi chữ ký method mà quên cập nhật `?0`, `?1` làm query hợp lệ nhưng lọc sai. Dùng dữ liệu test có giá trị khác nhau và assert ID.

### Dùng nối chuỗi thủ công

Nối trực tiếp input vào JSON dễ làm hỏng escape và trộn dữ liệu với cấu trúc query. Dùng placeholder hoặc Query builder.

### Chỉ test mock repository

Mock chỉ xác nhận code gọi method, không kiểm tra binding, mapping hoặc Query DSL. Cần integration test với Elasticsearch tương thích.

### Chỉ kiểm tra request không lỗi

Query có thể chạy thành công nhưng trả sai tập document. Hãy tạo fixture dương, âm và biên rồi assert kết quả cụ thể.

### Không refresh dữ liệu fixture

Search có thể chưa thấy document vừa ghi do refresh interval. Trong test, refresh index sau khi nạp fixture hoặc dùng refresh policy phù hợp.

## 17. Quy trình kiểm thử đề xuất

Khi thêm hoặc sửa một `@Query` có tham số, có thể thực hiện theo thứ tự:

1. Viết Query DSL mẫu với tên field và cấu trúc bool rõ ràng.
2. Xác định kiểu từng tham số và vị trí placeholder từ `?0`.
3. Đặt placeholder chuỗi, số, Boolean và ngày giờ đúng kiểu JSON.
4. Parse một JSON mẫu sau binding đại diện để phát hiện lỗi cấu trúc.
5. Đối chiếu tên field và kiểu dữ liệu với mapping thực tế.
6. Chạy repository integration test trên Elasticsearch phiên bản tương thích.
7. Thử chuỗi có ký tự đặc biệt, giá trị null/danh sách rỗng và tham số sai biên.
8. Assert tập document trả về, không chỉ kiểm tra request thành công.
9. Khi cần chẩn đoán, capture HTTP body trong môi trường test và parse thành JSON để kiểm tra giá trị đã bind.
10. Giữ test chạy trong CI với image Elasticsearch được pin version.

## 18. Kết luận

Với `@Query`, cần kiểm tra cả JSON template lẫn truy vấn sau khi Spring Data gắn tham số. Placeholder `?0`, `?1` được đánh số từ 0 và phải đặt đúng vị trí kiểu JSON: chuỗi thường nằm trong dấu nháy, số và Boolean không có dấu nháy, ngày giờ được biểu diễn theo format mapping chấp nhận. Không nối chuỗi input trực tiếp vào JSON.

JSON parser giúp phát hiện lỗi cú pháp và test cấu trúc giúp xác nhận các node nằm đúng vị trí. Tuy nhiên, chỉ integration test với Elasticsearch mới xác nhận binding thực tế, mapping, Query DSL và kết quả. Hãy kiểm thử giá trị biên, chuỗi đặc biệt, null, danh sách rỗng và thứ tự tham số; khi cần quan sát request cuối cùng, capture HTTP body ở môi trường kiểm thử và parse nó như JSON thay vì so sánh chuỗi thô. Cách kiểm thử nhiều lớp này giúp phát hiện cả lỗi cú pháp lẫn lỗi truy vấn hợp lệ nhưng sai ý nghĩa.
