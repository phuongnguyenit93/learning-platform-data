# Tổ chức truy vấn JSON trong tài nguyên cấu hình có thể kiểm thử

Khi ứng dụng dùng nhiều truy vấn Elasticsearch, đặt toàn bộ Query DSL trong annotation hoặc nối chuỗi JSON ngay trong service sẽ khiến code khó đọc và khó kiểm tra. Một cách tổ chức tốt hơn là lưu phần Query DSL ổn định trong các file JSON thuộc classpath, nạp chúng qua một thành phần chuyên trách, rồi đưa vào Spring Data Elasticsearch để thực thi.

Cách làm này tách ba trách nhiệm: **tài nguyên JSON mô tả cấu trúc truy vấn**, **Java cung cấp tham số và điều phối**, **test xác nhận cấu trúc cũng như hành vi của truy vấn**. Nhờ vậy, nhóm phát triển có thể review thay đổi query như thay đổi mã nguồn, kiểm tra JSON độc lập và chạy integration test với Elasticsearch.

Bài này tập trung vào truy vấn JSON được quản lý trong tài nguyên cấu hình. Ví dụ sử dụng `StringQuery` và `ElasticsearchOperations` để thực thi query DSL. Với các truy vấn cần builder type-safe, sort nâng cao hoặc tính năng mới của Elasticsearch Java API Client, có thể chọn `NativeQuery` hoặc client API phù hợp với phiên bản dự án.

## 1. Vì sao nên tách Query DSL khỏi service?

### 1.1. Truy vấn inline nhanh nhưng khó bảo trì

Một query đơn giản có thể viết trực tiếp:

~~~java
Query query = new StringQuery("""
{
  "bool": {
    "must": [
      { "match": { "name": "wireless keyboard" } }
    ],
    "filter": [
      { "term": { "category": "ACCESSORY" } }
    ]
  }
}
""");
~~~

Với một truy vấn nhỏ, cách này dễ hiểu. Khi query phát triển thêm nhiều nhánh `must`, `should`, `filter`, `range`, `nested`, `highlight` hoặc điều kiện tùy chọn, service có thể chứa một khối JSON dài.

Các vấn đề thường xuất hiện:

- Logic nghiệp vụ và cấu trúc Query DSL nằm lẫn trong cùng method.
- Khó review sự thay đổi của query khi code Java cũng thay đổi nhiều.
- Khó tái sử dụng một cấu trúc query ở nhiều service.
- Dễ tạo JSON lỗi khi nối chuỗi hoặc thêm dấu ngoặc.
- Unit test phải kiểm tra cả logic service và chi tiết chuỗi JSON.
- Các query gần giống nhau dễ bị copy rồi lệch cấu hình theo thời gian.

### 1.2. Tài nguyên JSON giúp quản lý cấu trúc truy vấn

Có thể đặt query trong `src/main/resources`:

~~~text
src/
  main/
    java/
      com/example/search/
        ProductSearchService.java
        SearchQueryCatalog.java
    resources/
      elasticsearch/
        queries/
          products-by-name.json
          products-by-category.json
          products-in-price-range.json
~~~

Mỗi file có một mục đích rõ ràng. Tên file có thể thể hiện entity, hành động và phiên bản nếu query cần được quản lý theo vòng đời riêng.

Cấu trúc JSON có thể được review độc lập. Java chịu trách nhiệm nạp tài nguyên, đưa tham số vào đúng vị trí và gọi API tìm kiếm.

### 1.3. Tách cấu trúc query khỏi tham số runtime

Một truy vấn thường có hai phần:

- **Cấu trúc ổn định**: loại query, các nhánh bool, field được tìm kiếm, cách kết hợp filter.
- **Giá trị runtime**: từ khóa người dùng nhập, danh mục được chọn, khoảng giá hoặc khoảng ngày.

Tài nguyên JSON nên mô tả cấu trúc ổn định. Java đưa các giá trị runtime vào JSON tree bằng API có kiểu dữ liệu, sau đó serialize thành JSON hợp lệ.

Không nên nối chuỗi thủ công để thay giá trị vào JSON. Việc nối chuỗi dễ làm sai escaping khi giá trị chứa dấu ngoặc kép, dấu gạch chéo hoặc ký tự Unicode.

## 2. Chọn định dạng và vị trí tài nguyên

### 2.1. Đặt file trong classpath

Ví dụ file:

`src/main/resources/elasticsearch/queries/products-by-name.json`

Nội dung:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "wireless keyboard"
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "available": true
        }
      }
    ]
  }
}
~~~

Đây là phần query DSL, không phải toàn bộ request body của Search API. Khi dùng `StringQuery`, chuỗi truyền vào mô tả query clause. Spring Data kết hợp query này với các tùy chọn khác như pageable và sort để tạo search request.

Nếu gọi Elasticsearch Validate Query API trực tiếp, phần query clause này sẽ được đặt trong trường `query` của request body. Cần phân biệt hai hình thức để tránh bọc `query` hai lần.

### 2.2. Một file cho một mục đích truy vấn

Không nên gom mọi query của ứng dụng vào một file JSON khổng lồ. Chia file theo nghiệp vụ hoặc use case:

| Tên tài nguyên | Mục đích |
|---|---|
| `products-by-name.json` | Tìm sản phẩm theo nội dung tên |
| `products-by-category.json` | Lọc sản phẩm theo danh mục |
| `products-in-price-range.json` | Lọc sản phẩm theo khoảng giá |
| `articles-by-text.json` | Tìm bài viết theo nội dung |
| `orders-by-status.json` | Tra cứu đơn hàng theo trạng thái |

Nếu một query có nhiều biến thể nhỏ nhưng cùng cấu trúc, có thể dùng một template với tham số runtime. Nếu cấu trúc hai query khác nhau đáng kể, hai tài nguyên riêng thường dễ hiểu và dễ kiểm thử hơn.

### 2.3. Không đưa secret vào query resource

File query chỉ nên chứa cấu trúc tìm kiếm. Không lưu các thông tin như:

- Username hoặc password của Elasticsearch.
- API key hoặc bearer token.
- URL có credential.
- Secret của môi trường production.

Thông tin kết nối thuộc cấu hình bảo mật của ứng dụng hoặc secret manager. Query resource thường được đóng gói cùng artifact và có thể xuất hiện trong repository hoặc file build.

## 3. Nạp tài nguyên JSON trong Spring

### 3.1. Dùng ResourceLoader

Spring `ResourceLoader` cho phép đọc resource theo location như `classpath:`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;

@Component
public class SearchQueryResourceLoader {

    private final ResourceLoader resourceLoader;

    public SearchQueryResourceLoader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String load(String location) {
        Resource resource = resourceLoader.getResource(location);

        try (InputStream input = resource.getInputStream()) {
            return StreamUtils.copyToString(
                input,
                StandardCharsets.UTF_8
            );
        } catch (IOException exception) {
            throw new IllegalStateException(
                "Cannot load Elasticsearch query resource: " + location,
                exception
            );
        }
    }
}
~~~

Cách này phù hợp khi query được đóng gói trong JAR và cần đọc qua classpath. `ResourceLoader` cũng hỗ trợ nhiều loại resource location khác, nhưng với query được quản lý cùng ứng dụng, `classpath:` thường dễ triển khai và kiểm thử.

### 3.2. Dùng ObjectMapper để parse JSON

Đọc JSON thành cây dữ liệu giúp Java thay đổi giá trị theo kiểu dữ liệu mà không phải nối chuỗi:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

@Component
public class SearchQueryJsonReader {

    private final SearchQueryResourceLoader resourceLoader;
    private final ObjectMapper objectMapper;

    public SearchQueryJsonReader(
            SearchQueryResourceLoader resourceLoader,
            ObjectMapper objectMapper) {
        this.resourceLoader = resourceLoader;
        this.objectMapper = objectMapper;
    }

    public JsonNode read(String location) {
        String json = resourceLoader.load(location);

        try {
            return objectMapper.readTree(json);
        } catch (IOException exception) {
            throw new IllegalStateException(
                "Invalid Elasticsearch query JSON: " + location,
                exception
            );
        }
    }
}
~~~

`JsonNode` là cấu trúc cây dữ liệu JSON. Khi cần thay đổi giá trị, hãy tạo bản sao có thể sửa bằng `deepCopy()` và thao tác qua `ObjectNode` hoặc `ArrayNode`.

Việc parse JSON ngay khi nạp giúp phát hiện lỗi cú pháp sớm hơn so với đợi đến lúc người dùng thực hiện truy vấn.

### 3.3. Dùng một catalog thay vì để service tự đọc file

Service không nên tự biết đường dẫn, encoding, cách mở stream và cách parse JSON. Có thể tạo một catalog chuyên trách:

~~~java
@Component
public class SearchQueryCatalog {

    private final SearchQueryJsonReader reader;

    public SearchQueryCatalog(SearchQueryJsonReader reader) {
        this.reader = reader;
    }

    public JsonNode productByNameTemplate() {
        return reader.read(
            "classpath:elasticsearch/queries/products-by-name.json"
        );
    }
}
~~~

Catalog giúp tập trung tên tài nguyên và tạo một điểm để kiểm soát việc nạp, cache hoặc versioning query. Khi số lượng query tăng, có thể tổ chức catalog theo domain như Product, Article hoặc Order.

## 4. Đưa tham số vào JSON an toàn

### 4.1. Không thay thế chuỗi bằng replace

Một cách dễ mắc lỗi là:

~~~java
String json = template.replace(
    "__KEYWORD__",
    userInput
);
~~~

Nếu `userInput` chứa dấu ngoặc kép hoặc ký tự escape, JSON có thể hỏng. Nếu dữ liệu được chèn vào vị trí cú pháp thay vì vị trí giá trị, cấu trúc query có thể bị thay đổi.

Thay thế chuỗi cũng dễ gây lỗi khi placeholder xuất hiện ở nhiều vị trí hoặc khi tên placeholder trùng với nội dung thật.

Hãy parse JSON thành tree và dùng Jackson để ghi giá trị. Jackson tự xử lý việc escape chuỗi, kiểu số, boolean và null theo định dạng JSON.

### 4.2. Tạo template có vị trí tham số rõ ràng

Tài nguyên `products-by-name.json` có thể chứa giá trị mặc định làm vị trí thay thế:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": ""
          }
        }
      }
    ],
    "filter": []
  }
}
~~~

Java cập nhật đúng node:

~~~java
ObjectNode root = (ObjectNode) template.deepCopy();

ObjectNode matchName = (ObjectNode) root.at(
    "/bool/must/0/match/name"
);

matchName.put("query", keyword);
~~~

`at()` sử dụng JSON Pointer để tìm node. Nếu cấu trúc tài nguyên bị đổi và đường dẫn không còn tồn tại, cần phát hiện lỗi thay vì tiếp tục tạo query thiếu điều kiện.

Có thể tạo helper để kiểm tra node bắt buộc:

~~~java
private ObjectNode requireObject(
        JsonNode root,
        String pointer) {

    JsonNode node = root.at(pointer);

    if (!(node instanceof ObjectNode objectNode)) {
        throw new IllegalStateException(
            "Expected JSON object at " + pointer
        );
    }

    return objectNode;
}
~~~

Sau đó:

~~~java
ObjectNode matchName = requireObject(
    root,
    "/bool/must/0/match/name"
);
matchName.put("query", keyword);
~~~

### 4.3. Đưa giá trị số và boolean theo đúng kiểu

Với filter khoảng giá, hãy ghi số dưới dạng JSON number:

~~~java
ObjectNode range = requireObject(
    root,
    "/bool/filter/1/range/price"
);

range.put("gte", minimumPrice);
range.put("lte", maximumPrice);
~~~

Nếu `minimumPrice` và `maximumPrice` là `BigDecimal`, Jackson ghi chúng thành JSON number. Không chuyển thành chuỗi bằng `toString()` rồi đặt trong dấu ngoặc kép, trừ khi mapping thực sự yêu cầu field keyword.

Với boolean:

~~~java
ObjectNode availability = requireObject(
    root,
    "/bool/filter/0/term"
);

availability.put("available", true);
~~~

Giá trị `true` là JSON boolean, không phải chuỗi `"true"`.

### 4.4. Thêm filter tùy chọn bằng ArrayNode

Không phải bộ lọc nào cũng được cung cấp trong mọi request. Nếu danh mục là tùy chọn, có thể thêm clause khi có giá trị:

~~~java
ArrayNode filters = (ArrayNode) root.at("/bool/filter");

if (category != null && !category.isBlank()) {
    ObjectNode termBody = objectMapper.createObjectNode();
    termBody.put("category", category);

    ObjectNode termQuery = objectMapper.createObjectNode();
    termQuery.set("term", termBody);

    filters.add(termQuery);
}
~~~

Cách này giữ JSON hợp lệ và thể hiện rõ filter nào được đưa vào. Với nhiều filter tùy chọn, có thể tạo helper cho term, range và exists query để service không phải thao tác JSON tree quá dài.

### 4.5. Kiểm tra tham số trước khi xây query

Jackson bảo đảm JSON được serialize đúng, nhưng không bảo đảm query có ý nghĩa nghiệp vụ. Service vẫn cần xác thực:

- Từ khóa không rỗng nếu truy vấn bắt buộc phải có từ khóa.
- Khoảng giá có `minimumPrice <= maximumPrice`.
- Danh mục thuộc tập giá trị được phép nếu nghiệp vụ yêu cầu.
- Ngày bắt đầu không sau ngày kết thúc.
- Số lượng điều kiện và kích thước input nằm trong giới hạn.

Không nhận tên field, index hoặc đoạn DSL tùy ý từ request công khai. Chỉ cho phép lựa chọn trong danh sách cấu hình đã kiểm soát.

## 5. Tạo StringQuery từ tài nguyên JSON

### 5.1. Serialize JSON tree thành query string

Sau khi cập nhật JSON tree, dùng `ObjectMapper` serialize thành chuỗi:

~~~java
String queryJson = objectMapper.writeValueAsString(root);
Query query = new StringQuery(queryJson);
~~~

`StringQuery` nhận query DSL dưới dạng JSON string. Phần JSON này là query clause, ví dụ `bool`, `match`, `term` hoặc `range`, không phải toàn bộ search request body có trường `query` ở cấp ngoài.

### 5.2. Ví dụ builder cho truy vấn sản phẩm

Giả sử file resource chứa:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": ""
          }
        }
      }
    ],
    "filter": []
  }
}
~~~

Có thể tạo một thành phần chuyên xây query:

~~~java
@Component
public class ProductQueryFactory {

    private final SearchQueryCatalog catalog;
    private final ObjectMapper objectMapper;

    public ProductQueryFactory(
            SearchQueryCatalog catalog,
            ObjectMapper objectMapper) {
        this.catalog = catalog;
        this.objectMapper = objectMapper;
    }

    public Query byName(String keyword, String category) {
        ObjectNode root = (ObjectNode)
            catalog.productByNameTemplate().deepCopy();

        ObjectNode matchName = requireObject(
            root,
            "/bool/must/0/match/name"
        );
        matchName.put("query", keyword);

        ArrayNode filters = (ArrayNode) root.at("/bool/filter");

        if (category != null && !category.isBlank()) {
            ObjectNode termBody = objectMapper.createObjectNode();
            termBody.put("category", category);

            ObjectNode termQuery = objectMapper.createObjectNode();
            termQuery.set("term", termBody);

            filters.add(termQuery);
        }

        try {
            return new StringQuery(
                objectMapper.writeValueAsString(root)
            );
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                "Cannot serialize product query",
                exception
            );
        }
    }

    private ObjectNode requireObject(
            JsonNode root,
            String pointer) {

        JsonNode node = root.at(pointer);

        if (!(node instanceof ObjectNode objectNode)) {
            throw new IllegalStateException(
                "Expected JSON object at " + pointer
            );
        }

        return objectNode;
    }
}
~~~

Đây là ví dụ về tổ chức trách nhiệm. Trong dự án thật, có thể tách helper JSON tree thành một thành phần dùng chung và giữ factory theo từng nghiệp vụ.

### 5.3. Thực thi bằng ElasticsearchOperations

Service gọi factory rồi thực thi:

~~~java
@Service
public class ProductSearchService {

    private final ProductQueryFactory queryFactory;
    private final ElasticsearchOperations operations;

    public ProductSearchService(
            ProductQueryFactory queryFactory,
            ElasticsearchOperations operations) {
        this.queryFactory = queryFactory;
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(
            String keyword,
            String category) {

        Query query = queryFactory.byName(keyword, category);

        return operations.search(
            query,
            ProductDocument.class
        );
    }
}
~~~

Service tập trung vào điều phối nghiệp vụ. Chi tiết đọc file và sửa JSON nằm trong catalog/factory; chi tiết gửi request nằm trong ElasticsearchOperations.

### 5.4. Thêm phân trang và sort

`StringQuery` là một implementation của Spring Data `Query`, vì vậy các tùy chọn phân trang và sort có thể được gắn vào query object:

~~~java
Query query = queryFactory.byName(keyword, category);

query.setPageable(
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
    )
);

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Field sort cần có mapping hỗ trợ sort. Nếu `createdAt` được ánh xạ sang tên khác hoặc field là text, hãy dùng field name và kiểu mapping đúng với index.

Nếu query cần các tùy chọn đặc thù của Elasticsearch như nested sort, script sort hoặc cấu hình request phức tạp, `NativeQuery` có thể phù hợp hơn. Đừng cố nhồi toàn bộ search request vào một JSON string rồi truyền cho `StringQuery`, vì `StringQuery` được dùng để mô tả query DSL clause trong abstraction của Spring Data.

## 6. Tổ chức nhiều query resource

### 6.1. Chia theo domain và mục đích

Một cấu trúc có thể mở rộng:

~~~text
src/main/resources/
  elasticsearch/
    queries/
      product/
        search-by-name.json
        filter-by-category.json
        price-range.json
      article/
        search-content.json
        search-title.json
      order/
        filter-by-status.json
~~~

Tên file nên phản ánh mục đích truy vấn thay vì tên kỹ thuật chung như `query1.json` hoặc `search.json`.

### 6.2. Đặt tên và version query

Khi thay đổi query có thể ảnh hưởng đáng kể đến kết quả, có thể version hóa tài nguyên:

~~~text
product/
  search-by-name-v1.json
  search-by-name-v2.json
~~~

Versioning hữu ích khi cần rollout có kiểm soát hoặc so sánh hành vi giữa hai cấu hình. Không cần tạo version mới cho mọi thay đổi nhỏ; hãy dùng khi có thay đổi hợp đồng hoặc kết quả cần được theo dõi riêng.

### 6.3. Dùng cấu hình để chọn tài nguyên, không để client tự chọn path

Nếu cần chọn query theo môi trường hoặc tính năng, có thể cấu hình tên resource trong application properties:

~~~yaml
search:
  queries:
    product-by-name: classpath:elasticsearch/queries/product/search-by-name-v1.json
~~~

Java bind cấu hình vào `@ConfigurationProperties` hoặc inject `Environment`. Tên resource phải được giới hạn trong cấu hình tin cậy.

Không nhận path như `classpath:...` trực tiếp từ người dùng API. Việc cho client chọn tùy ý resource path có thể dẫn đến truy cập tài nguyên ngoài dự định hoặc chạy query không được kiểm soát.

### 6.4. Khi nào nên cache query template?

Nếu file resource được đóng gói cùng ứng dụng và không thay đổi trong thời gian chạy, có thể nạp và parse một lần rồi giữ template trong memory. Mỗi request phải tạo bản sao riêng trước khi sửa:

~~~java
ObjectNode requestQuery = cachedTemplate.deepCopy();
~~~

Không sửa trực tiếp một `ObjectNode` dùng chung giữa nhiều request. Nếu hai request cùng cập nhật node query, tham số của request này có thể ghi đè request kia.

Nếu resource được đọc từ file ngoài classpath và có thể thay đổi khi ứng dụng đang chạy, cần thiết kế cache invalidation/reload rõ ràng. Không nên giả định Spring Resource tự theo dõi mọi thay đổi file.

## 7. Kiểm thử cấu trúc JSON độc lập

### 7.1. Kiểm tra resource tồn tại và parse được

Một unit test nên phát hiện file thiếu hoặc JSON sai cú pháp:

~~~java
@SpringBootTest
class SearchQueryResourceTest {

    @Autowired
    private SearchQueryCatalog catalog;

    @Test
    void productQueryTemplateCanBeLoaded() {
        JsonNode template = catalog.productByNameTemplate();

        assertTrue(template.has("bool"));
        assertTrue(template.at("/bool/must").isArray());
        assertTrue(template.at("/bool/filter").isArray());
    }
}
~~~

Test này không cần Elasticsearch. Nó xác nhận tài nguyên được đóng gói và có cấu trúc tối thiểu mà factory mong đợi.

Có thể dùng test không khởi tạo toàn bộ Spring context bằng cách tạo `ResourceLoader` và `ObjectMapper` trực tiếp nếu muốn test catalog ở phạm vi nhỏ hơn.

### 7.2. Kiểm tra giá trị được đưa vào đúng node

Test factory nên xác nhận query đã tạo chứa đúng dữ liệu:

~~~java
@Test
void insertsKeywordAndCategoryAsJsonValues() throws Exception {
    Query query = queryFactory.byName(
        "wireless \"keyboard\"",
        "ACCESSORY"
    );

    StringQuery stringQuery = (StringQuery) query;
    JsonNode json = objectMapper.readTree(stringQuery.getSource());

    assertEquals(
        "wireless \"keyboard\"",
        json.at("/bool/must/0/match/name/query").asText()
    );

    assertEquals(
        "ACCESSORY",
        json.at("/bool/filter/0/term/category").asText()
    );
}
~~~

Tên getter source và khả năng ép kiểu có thể phụ thuộc API của phiên bản Spring Data Elasticsearch. Nếu phiên bản dự án không công khai source qua getter đó, hãy tách hàm serialize JSON thành một phương thức riêng trả về `JsonNode` hoặc chuỗi để test mà không cần truy cập nội bộ `StringQuery`.

Test với dấu ngoặc kép chứng minh Jackson giữ dữ liệu như một JSON string hợp lệ thay vì làm hỏng cấu trúc query.

### 7.3. Kiểm tra filter tùy chọn

Nếu category có thể không được truyền, test cần xác nhận:

- Không có filter category khi giá trị null hoặc blank.
- Có đúng một filter category khi giá trị hợp lệ.
- Các filter cố định trong template vẫn còn nguyên.
- Không có filter bị nhân đôi giữa các lần gọi.

Mỗi lần tạo query phải sửa một bản copy của template. Nếu dùng lại node đã bị sửa, test gọi factory nhiều lần có thể phát hiện filter cũ bị giữ lại.

### 7.4. So sánh JSON theo cấu trúc

Không nên so sánh toàn bộ JSON bằng chuỗi nếu thứ tự key không có ý nghĩa. Hãy parse thành `JsonNode` và so sánh cấu trúc:

~~~java
JsonNode actual = objectMapper.readTree(actualJson);
JsonNode expected = objectMapper.readTree(expectedJson);

assertEquals(expected, actual);
~~~

Cách này bỏ qua khác biệt không quan trọng về khoảng trắng và thứ tự field trong object, nhưng vẫn phát hiện thay đổi về giá trị, array order và cấu trúc node.

## 8. Kiểm thử query với Elasticsearch

### 8.1. Validate Query API

Elasticsearch cung cấp Validate Query API để kiểm tra query có hợp lệ theo index/mapping hay không:

~~~http
POST /products/_validate/query?explain=true
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless keyboard"
            }
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "ACCESSORY"
          }
        }
      ]
    }
  }
}
~~~

Validate Query API có thể phát hiện query không hợp lệ hoặc vấn đề liên quan đến mapping. Nó không chứng minh query trả đúng tập kết quả nghiệp vụ hoặc có hiệu năng tốt trên dữ liệu production.

Khi dùng tài nguyên query clause với `StringQuery`, hãy bọc clause trong trường `query` khi gọi Validate Query API trực tiếp.

### 8.2. Integration test với Elasticsearch thật hoặc Testcontainers

Để kiểm tra kết quả thực tế, cần chạy integration test với phiên bản Elasticsearch tương thích với dự án.

Một kịch bản cơ bản:

1. Khởi động Elasticsearch test instance.
2. Tạo index với mapping và analyzer cần thiết.
3. Nạp một tập document đại diện.
4. Gọi factory để tạo query từ JSON resource.
5. Thực thi bằng `ElasticsearchOperations.search`.
6. Xác nhận ID và nội dung kết quả.
7. Thử các giá trị có ký tự đặc biệt, tiếng Việt hoặc giá trị biên.
8. Kiểm tra query với filter tùy chọn.
9. Dọn index hoặc dữ liệu test sau khi hoàn thành.

Unit test JSON không thay thế integration test. JSON có thể parse hợp lệ nhưng vẫn dùng field không tồn tại, sai kiểu hoặc analyzer không tương thích.

### 8.3. Kiểm tra cả query không có kết quả và query quá rộng

Test nên bao gồm:

- Query có kết quả mong đợi.
- Query không có kết quả.
- Query với chuỗi rỗng hoặc chỉ có khoảng trắng.
- Query có ký tự đặc biệt.
- Query thiếu filter bắt buộc.
- Query có khoảng giá biên.
- Query trên field text và keyword.
- Query có nested field nếu tài nguyên sử dụng nested.

Nếu query có thể tạo tải lớn, hãy đo trên dữ liệu gần quy mô thực tế. Một query hợp lệ về cú pháp vẫn có thể quá chậm.

## 9. Validate cấu trúc và hợp đồng query

### 9.1. Kiểm tra field path bắt buộc

Factory đang dựa vào JSON Pointer như:

`/bool/must/0/match/name`

Nếu một người sửa resource chuyển `match` thành `multi_match` hoặc thay cấu trúc bool, factory có thể không tìm được node.

Có hai cách quản lý:

- Giữ cấu trúc JSON ổn định và test các path bắt buộc.
- Thiết kế factory linh hoạt hơn, tìm node theo tên hoặc nhận query fragment riêng từ nhiều resource.

Không nên để lỗi path chỉ xuất hiện ở request production. Hãy kiểm tra cấu trúc ngay khi khởi động hoặc trong test.

### 9.2. Kiểm tra kiểu dữ liệu

Một số lỗi không phải lỗi JSON syntax:

- `term` trên field text thay vì keyword.
- `range` trên field không phải numeric/date.
- `nested` query dùng sai path.
- `match` dùng cho mã cần exact match.
- Sort trên field không có doc values phù hợp.

Những lỗi này cần kiểm tra với mapping thực tế hoặc integration test. JSON Schema có thể kiểm tra cấu trúc cơ bản của tài liệu, nhưng không thay thế việc validate với Elasticsearch mapping.

### 9.3. Quản lý thay đổi query như thay đổi hợp đồng

Nếu query resource là một phần quan trọng của sản phẩm, hãy review thay đổi như code:

- Nêu mục đích của thay đổi.
- Kiểm tra field và analyzer liên quan.
- Cập nhật test cấu trúc.
- Cập nhật integration test cho kết quả mong đợi.
- Đo hiệu năng nếu query thay đổi độ rộng hoặc loại operator.
- Ghi nhận thay đổi kết quả nếu ảnh hưởng xếp hạng hoặc bộ lọc.

Không nên chỉnh JSON trực tiếp trên production cluster mà không cập nhật lại tài nguyên trong source of truth của ứng dụng. Nếu query chỉ thay đổi trong cluster, các môi trường khác sẽ khó tái tạo cùng hành vi.

## 10. Tách query resource khỏi sort và pagination

### 10.1. Query JSON chỉ giữ điều kiện tìm kiếm

Khi dùng `StringQuery`, tài nguyên thường chứa query clause. Sort và pageable có thể được gắn riêng vào Spring Data `Query`:

~~~java
Query query = new StringQuery(queryJson);

query.setPageable(
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
    )
);
~~~

Cách tổ chức này giữ query condition trong file JSON và giữ tham số hiển thị trong Java. Nó cũng giúp cùng một query resource được tái sử dụng cho các page size hoặc sort khác nhau.

### 10.2. Khi cần toàn bộ Search DSL trong một tài nguyên

Một search request có thể chứa nhiều phần ngoài query:

- `sort`
- `from` và `size`
- `highlight`
- `_source`
- `aggs`
- `track_total_hits`
- `rescore` hoặc các tùy chọn khác

Nếu mục tiêu là quản lý toàn bộ search request trong JSON, `StringQuery` có thể không phải abstraction phù hợp vì nó đại diện cho query clause. Khi đó, hãy xem xét Elasticsearch Java API Client hoặc một lớp adapter chuyên chuyển request JSON thành request client theo API được phiên bản sử dụng hỗ trợ.

Không truyền nguyên search body có trường `query` vào `StringQuery` nếu abstraction đang mong đợi query clause. Hãy xác định rõ ranh giới dữ liệu của từng API.

## 11. Bảo mật và vận hành

### 11.1. Không cho phép người dùng gửi DSL tùy ý

Không nhận một chuỗi JSON Query DSL hoàn chỉnh từ client rồi chuyển thẳng vào Elasticsearch. Điều đó có thể cho phép client yêu cầu:

- Query quá rộng.
- Script hoặc regexp không được phép.
- Truy cập field nội bộ.
- Sort hoặc aggregation tốn kém.
- Truy vấn index ngoài phạm vi nghiệp vụ nếu target index cũng bị điều khiển.

API công khai nên nhận các tham số nghiệp vụ có kiểu rõ ràng. Server chọn query resource và chỉ đưa các tham số được xác thực vào đúng node.

### 11.2. Giới hạn chi phí truy vấn

Tùy nghiệp vụ, có thể giới hạn:

- Độ dài từ khóa.
- Số lượng filter.
- Page size tối đa.
- Khoảng ngày hoặc khoảng giá.
- Số lượng giá trị trong `terms` filter.
- Loại query được phép sử dụng.

Query resource không thay thế giới hạn ở service. Một template hợp lệ vẫn có thể tạo request nặng nếu tham số runtime không được kiểm soát.

### 11.3. Logging có kiểm soát

Log hữu ích để debug query, nhưng không nên ghi toàn bộ dữ liệu nhạy cảm hoặc query input không giới hạn.

Có thể log:

- Tên query resource hoặc query ID.
- Thời gian thực thi.
- Index/alias đã chọn theo cấu hình tin cậy.
- Page size và số hit.
- Loại lỗi và correlation ID.

Nếu cần log DSL, cân nhắc masking giá trị nhạy cảm và giới hạn kích thước log. Không log credential hoặc secret.

## 12. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy resource | Sai classpath location hoặc file không được đóng gói | Kiểm tra đường dẫn và nội dung artifact |
| JSON parse thất bại | Dấu phẩy, ngoặc hoặc kiểu dữ liệu sai | Parse resource trong unit test |
| Factory không tìm thấy JSON Pointer | Cấu trúc resource thay đổi nhưng code chưa cập nhật | Kiểm tra path bắt buộc và cập nhật test |
| Query lỗi vì field không tồn tại | Tên field trong JSON không khớp mapping | Kiểm tra mapping API và entity metadata |
| Query trả kết quả rỗng | Field type, analyzer hoặc giá trị filter không tương thích | Kiểm tra _analyze, mapping và query DSL |
| Chuỗi có dấu ngoặc kép làm JSON lỗi | Thay placeholder bằng nối chuỗi | Dùng Jackson tree và serialize |
| Filter cũ xuất hiện ở request sau | Sửa trực tiếp template dùng chung | Dùng deepCopy() cho từng request |
| Giá trị số bị xử lý như text | Ghi số dưới dạng chuỗi | Dùng ObjectNode.put với kiểu số phù hợp |
| Query JSON hợp lệ nhưng Elasticsearch từ chối | DSL không phù hợp mapping hoặc phiên bản | Dùng Validate Query API và integration test |
| Test pass nhưng production query chậm | Dataset, shard hoặc tải khác môi trường test | Đo query trên dữ liệu và cấu hình gần production |
| Query resource giữa môi trường khác nhau | Resource được thay ngoài source of truth | Quản lý version và deploy cùng artifact |
| StringQuery nhận sai cấu trúc | Truyền toàn search body thay cho query clause | Tách query clause khỏi request-level options |

## 13. Quy trình triển khai đề xuất

Một quy trình thực tế có thể gồm:

1. Xác định mục đích nghiệp vụ và loại query cần dùng.
2. Viết query clause JSON trong tài nguyên classpath.
3. Parse tài nguyên bằng Jackson và kiểm tra cấu trúc tối thiểu.
4. Tạo factory để đưa tham số có kiểu vào JSON tree.
5. Serialize thành JSON và tạo `StringQuery`.
6. Gắn sort/pageable hoặc tùy chọn Spring Data cần thiết.
7. Thực thi qua `ElasticsearchOperations`.
8. Unit test việc nạp, parse và tạo query.
9. Validate query với mapping Elasticsearch.
10. Integration test kết quả, trường hợp biên và hiệu năng.
11. Review/version hóa tài nguyên cùng thay đổi code.
12. Đóng gói và triển khai cùng artifact ứng dụng.

Với query đơn giản, có thể giữ query inline bằng `@Query` hoặc `StringQuery`. Khi query dài, được tái sử dụng hoặc cần review độc lập, tài nguyên JSON cùng factory có kiểm thử thường dễ bảo trì hơn.

## 14. Những điểm cần ghi nhớ

- Lưu Query DSL trong `src/main/resources` giúp tách cấu trúc truy vấn khỏi service.
- `StringQuery` nhận query DSL clause; cần phân biệt với toàn bộ search request body.
- Dùng `ResourceLoader` để nạp resource và `ObjectMapper` để parse JSON.
- Dùng `deepCopy()` trước khi thay đổi template để tránh request đồng thời ghi đè dữ liệu của nhau.
- Cập nhật tham số bằng `ObjectNode`/`ArrayNode`, không nối chuỗi JSON thủ công.
- Giữ đúng kiểu dữ liệu: string, number, boolean, array và object.
- Tách query condition khỏi sort/pageable nếu dùng Spring Data Query abstraction.
- Unit test xác nhận resource và cấu trúc; integration test xác nhận mapping và hành vi Elasticsearch.
- Validate Query API giúp phát hiện lỗi DSL nhưng không thay thế đánh giá relevance hoặc hiệu năng.
- Không nhận Query DSL, index path hoặc resource path tùy ý từ client.
- Quản lý query resource trong source control và triển khai cùng ứng dụng để các môi trường có thể tái tạo cùng hành vi.

Khi tổ chức truy vấn JSON theo cách này, Query DSL trở thành một tài nguyên có thể review, kiểm thử và version hóa. Java giữ vai trò đưa tham số nghiệp vụ vào đúng vị trí và thực thi truy vấn, còn integration test xác nhận query thực sự hoạt động với mapping và Elasticsearch của dự án.
