# AfterLoadCallback và AfterConvertCallback khi đọc

Khi Spring Data Elasticsearch đọc một document, dữ liệu đi qua nhiều bước trước khi trở thành object Java mà service sử dụng. Có lúc ứng dụng cần chuẩn hóa dữ liệu thô trước khi mapping; có lúc cần điều chỉnh entity sau khi converter đã tạo object. Hai callback **AfterLoadCallback** và **AfterConvertCallback** phục vụ hai thời điểm khác nhau trong luồng đọc đó.

**AfterLoadCallback** gắn với giai đoạn document đã được lấy từ Elasticsearch. **AfterConvertCallback** gắn với giai đoạn entity đã được chuyển đổi từ document. Chọn đúng callback giúp xử lý dữ liệu ở đúng tầng, giữ mapping dễ hiểu và tránh đưa logic đọc dữ liệu vào repository hoặc service.

Bài học này giải thích vị trí của từng callback trong lifecycle đọc, cách đăng ký callback trong Spring, cách thay đổi document hoặc entity, thứ tự chạy, phạm vi áp dụng, cách kết hợp với auditing, các lưu ý hiệu năng và cách kiểm thử.

## 1. Luồng đọc document trong Spring Data Elasticsearch

Khi gọi repository hoặc ElasticsearchOperations để đọc một entity, Spring Data phải chuyển response của Elasticsearch thành document trung gian rồi chuyển document đó thành kiểu Java đích.

Luồng khái quát:

~~~text
Repository / ElasticsearchOperations
              |
              v
       Elasticsearch search/get
              |
              v
       Elasticsearch response
              |
              v
       Spring Data Document
              |
              v
       AfterLoadCallback
              |
              v
       MappingElasticsearchConverter
              |
              v
        Domain entity
              |
              v
      AfterConvertCallback
              |
              v
      SearchHit / entity result
              |
              v
          Application
~~~

Tên và chi tiết nội bộ của các bước có thể khác giữa các API đọc và phiên bản Spring Data Elasticsearch. Điều cần nhớ là callback được gắn vào lifecycle do Spring Data quản lý; chúng không phải interceptor tùy ý cho mọi thao tác HTTP đến Elasticsearch.

Hai callback nằm ở hai giai đoạn khác nhau:

- **AfterLoadCallback** phù hợp với xử lý document vừa được tải, trước khi ứng dụng sử dụng entity đã mapping.
- **AfterConvertCallback** phù hợp với xử lý object Java sau khi converter đã tạo entity.

Một thao tác đọc có thể chạy qua cả hai callback nếu API và phiên bản đang dùng hỗ trợ chúng trong luồng đó.

## 2. Khi nào cần callback sau khi đọc?

Giả sử index có dữ liệu sản phẩm từ nhiều phiên bản ứng dụng. Một số document cũ dùng field productName, trong khi model Java hiện tại dùng name. Hoặc hệ thống cần chuẩn hóa một giá trị legacy trước khi converter map vào entity.

Các tình huống thường gặp:

- Chuẩn hóa dữ liệu legacy trong document trước khi mapping.
- Ánh xạ field tương thích giữa schema cũ và model mới.
- Bổ sung giá trị mặc định khi đọc document thiếu field.
- Chuẩn hóa entity sau khi converter đã chuyển kiểu.
- Tính field dẫn xuất chỉ phục vụ ứng dụng.
- Thêm metadata hiển thị hoặc trạng thái runtime vào entity.

Không phải mọi nhu cầu đều nên dùng callback. Nếu dữ liệu cần được sửa vĩnh viễn trong index, hãy thực hiện migration hoặc update dữ liệu. Callback đọc chỉ thay đổi đối tượng đang đi qua luồng đọc hiện tại; nó không tự ghi ngược document đã lưu.

## 3. AfterLoadCallback làm việc ở giai đoạn document được tải

AfterLoadCallback được gọi ở giai đoạn Spring Data đã nhận document từ Elasticsearch. Đây là thời điểm phù hợp khi cần xử lý dữ liệu trước hoặc trong quá trình chuyển document thành entity, theo contract của phiên bản đang sử dụng.

Ví dụ về mục tiêu: document cũ có thể thiếu field status. Ứng dụng muốn cung cấp giá trị mặc định khi đọc:

~~~json
{
  "_id": "P-100",
  "_source": {
    "name": "Wireless Keyboard",
    "price": 79.5
  }
}
~~~

Trong khi model hiện tại mong đợi status. Có thể xử lý document ở giai đoạn load để converter nhận được dữ liệu có cấu trúc tương thích.

Pseudocode thể hiện ý tưởng:

~~~java
// Hình dạng minh họa: dùng đúng tham số và kiểu trả về
// của AfterLoadCallback trong phiên bản Spring Data đang cài.
Document onAfterLoad(Document document, IndexCoordinates index) {
    if (!document.containsKey("status")) {
        document.put("status", "UNKNOWN");
    }
    return document;
}
~~~

Đây là xử lý trên document trung gian. Callback cần trả lại đối tượng theo contract để pipeline tiếp tục. Không nên giả định mọi API hoặc mọi release đều có cùng chữ ký; hãy kiểm tra interface của dependency thực tế trước khi triển khai.

### Những việc phù hợp với AfterLoadCallback

- Điều chỉnh tên hoặc cấu trúc field legacy trước mapping.
- Bổ sung giá trị mặc định theo quy ước đọc.
- Chuẩn hóa biểu diễn dữ liệu ở tầng document.
- Loại bỏ hoặc chuyển đổi một field kỹ thuật trước khi converter đọc, nếu mapping yêu cầu.

### Những việc không nên làm ở đây

- Gọi service bên ngoài cho từng document.
- Chạy query Elasticsearch khác trong callback.
- Ghi ngược document trong lúc đang đọc.
- Thực hiện nghiệp vụ có side effect.
- Thay đổi schema index một cách ngầm định.
- Đưa logic phân quyền quan trọng vào callback mà không có kiểm soát rõ ràng ở service/API.

Callback có thể chạy trên nhiều document trong một search request. Một thao tác chậm hoặc gọi mạng trong callback có thể làm tăng độ trễ của toàn bộ trang kết quả.

## 4. AfterConvertCallback làm việc sau khi tạo entity

AfterConvertCallback được gọi sau khi Spring Data đã chuyển document thành object Java. Callback nhận entity và có thể nhận cả document gốc cùng thông tin index tùy contract của API.

Ví dụ model:

~~~java
public class Product {

    @Id
    private String id;

    private String name;

    private Double price;

    private String displayLabel;

    // getters and setters
}
~~~

Ứng dụng muốn tạo displayLabel dựa trên các field đã mapping. Đây là công việc phù hợp với entity callback:

~~~java
@Component
public class ProductAfterConvertCallback
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product product,
            Document document,
            IndexCoordinates index) {

        product.setDisplayLabel(
            product.getName() + " - " + product.getPrice()
        );

        return product;
    }
}
~~~

Chữ ký trên minh họa dạng callback phổ biến của Spring Data Elasticsearch; đối chiếu package, tham số và kiểu trả về trong release train đang dùng.

Callback nhận entity đã được converter tạo. Có thể đọc field Java theo kiểu dữ liệu domain thay vì tự parse map từ document.

### AfterConvertCallback có thể thay đổi entity

Callback có thể:

- Chuẩn hóa chuỗi sau mapping.
- Tạo field dẫn xuất chỉ dùng trong runtime.
- Điền default vào property Java chưa có giá trị.
- Chuyển đổi một trạng thái legacy thành enum/domain value.
- Gắn metadata tính toán phục vụ response.

Nếu callback sửa entity rồi trả về entity đó, object được trả về từ luồng đọc sẽ mang thay đổi này. Không có nghĩa Elasticsearch đã lưu thay đổi.

Nếu muốn thay đổi được lưu lâu dài, hãy dùng Update API, migration hoặc một luồng ghi riêng. Đừng trông chờ AfterConvertCallback tự persist.

## 5. Phân biệt hai callback

| Tiêu chí | AfterLoadCallback | AfterConvertCallback |
|---|---|---|
| Thời điểm | Sau khi document được tải từ Elasticsearch | Sau khi document được converter chuyển thành entity |
| Đối tượng xử lý | Document hoặc representation ở giai đoạn load theo API contract | Entity Java đã mapping |
| Kiểu dữ liệu | Field/document representation | Kiểu domain cụ thể |
| Use case | Tương thích schema, chuẩn hóa dữ liệu thô | Chuẩn hóa entity, field dẫn xuất |
| Có tự ghi ngược index? | Không | Không |
| Phụ thuộc mapping entity? | Có thể xử lý trước mapping | Có, vì entity đã được tạo |
| Ví dụ | Bổ sung field mặc định cho document cũ | Tạo displayLabel từ name và price |

Một cách chọn nhanh:

- Cần thay đổi cách document được đọc hoặc chuẩn bị cho converter: xem xét AfterLoadCallback.
- Cần thay đổi object Java sau khi mapping: xem xét AfterConvertCallback.
- Cần sửa dữ liệu đã lưu trong index: dùng update hoặc migration.
- Cần thay đổi response theo một API cụ thể: cân nhắc mapper/DTO ở service thay vì callback toàn cục.

## 6. Đăng ký callback như Spring bean

Entity callback được Spring phát hiện thông qua cơ chế callback của application context. Cách thông thường là khai báo callback thành bean bằng @Component hoặc @Bean.

Ví dụ dùng component:

~~~java
@Component
public class ProductAfterConvertCallback
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product entity,
            Document document,
            IndexCoordinates index) {

        if (entity.getName() != null) {
            entity.setDisplayLabel(entity.getName().trim());
        }

        return entity;
    }
}
~~~

Hoặc khai báo bằng configuration:

~~~java
@Configuration
public class ElasticsearchCallbackConfiguration {

    @Bean
    ProductAfterConvertCallback productAfterConvertCallback() {
        return new ProductAfterConvertCallback();
    }
}
~~~

Không cần tự gọi callback từ repository. Khi callback được đăng ký đúng trong Spring context và luồng đọc của Spring Data sử dụng entity callback infrastructure, framework sẽ gọi nó ở lifecycle tương ứng.

### Callback không phải repository fragment

Repository fragment là nơi phù hợp để thêm một phương thức truy vấn hoặc hành vi repository chuyên biệt. Entity callback là hook trong lifecycle mapping/persistence. Không nên dùng callback để thay thế repository method hoặc để thực hiện một truy vấn nghiệp vụ.

## 7. Thứ tự khi có nhiều callback

Một ứng dụng có thể có nhiều callback cho cùng một entity type, chẳng hạn một callback chuẩn hóa chuỗi và một callback tạo display field.

Khi thứ tự ảnh hưởng kết quả, hãy khai báo thứ tự rõ ràng bằng cơ chế ordering của Spring, ví dụ @Order hoặc Ordered, nếu callback infrastructure của phiên bản đang dùng hỗ trợ ordering đó.

~~~java
@Component
@Order(10)
public class NormalizeProductName
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product product,
            Document document,
            IndexCoordinates index) {

        if (product.getName() != null) {
            product.setName(product.getName().trim());
        }

        return product;
    }
}
~~~

~~~java
@Component
@Order(20)
public class BuildProductLabel
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product product,
            Document document,
            IndexCoordinates index) {

        product.setDisplayLabel(product.getName());
        return product;
    }
}
~~~

Trong ví dụ, callback tạo label chạy sau callback chuẩn hóa tên. Nếu không có ordering rõ ràng, đừng dựa vào thứ tự bean được phát hiện tình cờ.

Một callback nên có trách nhiệm nhỏ và xác định. Nếu nhiều callback sửa cùng property, việc theo dõi kết quả cuối sẽ khó khăn.

## 8. Phạm vi callback và những API đọc cần lưu ý

Callback được gọi bởi các luồng Spring Data có tích hợp entity callback infrastructure. Các API như repository find/search hoặc ElasticsearchOperations thường đi qua mapping converter khi trả entity, nhưng phạm vi chính xác phụ thuộc loại operation và phiên bản.

Cần phân biệt:

- Đọc entity qua repository hoặc Operations.
- Đọc raw response/document.
- Dùng converter trực tiếp.
- Dùng Elasticsearch Java API Client trực tiếp.
- Dùng projection hoặc DTO riêng.
- Đọc aggregation mà không materialize entity.

Nếu gọi Elasticsearch Java API Client trực tiếp và tự lấy _source, không nên mặc định callback Spring Data sẽ chạy. Direct client không tự đi qua repository/template mapping lifecycle.

Nếu một luồng đọc trả raw Document hoặc raw response thay vì entity, callback AfterConvertCallback cho entity có thể không được áp dụng. Tương tự, aggregation-only request thường không tạo domain entity cho từng bucket nên không nên mong callback entity chạy trên aggregation result.

Hãy kiểm tra bằng integration test cho đúng API mà ứng dụng đang sử dụng thay vì suy rộng từ một method đọc sang mọi API.

## 9. Callback với SearchHit và SearchHits

Trong tìm kiếm, Spring Data có thể trả SearchHits<T> hoặc SearchHit<T> để giữ metadata như ID, score, sort values, highlight và inner hits.

Callback tác động vào entity content theo lifecycle mapping. Metadata của search hit là một phần riêng của kết quả tìm kiếm.

Ví dụ:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();

    // product có thể đã đi qua callback tương ứng.
    // hit vẫn giữ metadata của kết quả Elasticsearch.
    float score = hit.getScore();
}
~~~

Không nên dùng callback để xóa hoặc ghi đè metadata của SearchHit. Nếu cần bổ sung khoảng cách, highlight snippet hoặc một nhãn phụ vào response, hãy chuyển SearchHit sang DTO ở service.

Một callback trên entity có thể ảnh hưởng mọi nơi đọc cùng entity type qua luồng được hỗ trợ. DTO mapping ở service giúp giữ logic trình bày trong phạm vi API cụ thể.

## 10. Kết hợp callback với auditing

Auditing thường ghi nhận thông tin về thời điểm và người tạo/cập nhật dữ liệu, ví dụ:

- createdDate.
- lastModifiedDate.
- createdBy.
- lastModifiedBy.

Đây là metadata thuộc lifecycle ghi. Spring Data auditing thường dùng annotation và auditor provider để điền giá trị khi tạo hoặc cập nhật entity.

Ví dụ:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
~~~

Cấu hình auditing cho Elasticsearch cần bật infrastructure tương ứng của phiên bản đang dùng và cung cấp auditor nếu cần createdBy/lastModifiedBy.

AfterLoadCallback và AfterConvertCallback chạy trong luồng đọc. Không dùng chúng để giả lập @LastModifiedDate hoặc thay đổi audit timestamp khi người dùng chỉ đọc dữ liệu. Việc đó làm metadata thay đổi theo lượt đọc và gây hiểu sai lịch sử dữ liệu.

### Khi nào callback đọc có thể hỗ trợ auditing?

Callback đọc có thể chuẩn hóa hoặc diễn giải các trường audit cũ để tương thích với model mới, nhưng không nên ghi thời điểm đọc vào field modified. Nếu cần ghi nhận thời điểm document được truy cập, đó là một sự kiện nghiệp vụ riêng và cần được lưu theo luồng có chủ đích.

## 11. Callback và sự kiện application event

Spring Data Elasticsearch có các application event cho những điểm trong lifecycle như load, convert, save hoặc delete tùy phiên bản. Entity callback và application event phục vụ mục đích liên quan nhưng không hoàn toàn giống nhau.

Entity callback thường phù hợp khi cần thay đổi entity/document và trả lại object đã điều chỉnh cho pipeline. Application event phù hợp khi cần thông báo một lifecycle event cho listener.

Không nên dùng event listener để sửa entity sau khi framework đã trả kết quả cho caller rồi kỳ vọng thay đổi đó xuất hiện trong object đã trả. Nếu cần biến đổi giá trị đang đi qua pipeline, dùng callback đúng thời điểm hoặc mapper/DTO ở service.

Cũng không nên giả định event và callback có thứ tự tương đương nếu chưa kiểm tra contract của phiên bản Spring Data Elasticsearch.

## 12. Callback trong ứng dụng reactive

Spring Data Elasticsearch có API reactive cho các luồng đọc không blocking. Nếu ứng dụng dùng reactive template/repository, cần kiểm tra callback infrastructure reactive được phiên bản đó hỗ trợ và contract trả về tương ứng.

Các nguyên tắc:

- Không gọi blocking repository hoặc HTTP client đồng bộ bên trong callback của luồng reactive.
- Không dùng block() để lấy dữ liệu từ một service khác trong callback.
- Giữ callback nhẹ, xác định và không phụ thuộc network.
- Nếu cần enrichment bất đồng bộ, thực hiện trong reactive service pipeline sau khi nhận entity.
- Kiểm thử cả subscription và cancellation nếu callback có tác động tới luồng reactive.

Một callback đồng bộ được đăng ký cho imperative flow không tự động có nghĩa nó phù hợp với reactive flow. Hãy dùng đúng loại callback mà API reactive trong release train cung cấp.

## 13. Xử lý null, field thiếu và dữ liệu legacy

Document trong index có thể được tạo từ nhiều phiên bản ứng dụng. Vì vậy, callback đọc cần chịu được field thiếu, null hoặc dữ liệu cũ.

Ví dụ AfterConvertCallback:

~~~java
@Override
public Product onAfterConvert(
        Product product,
        Document document,
        IndexCoordinates index) {

    if (product.getName() == null) {
        product.setName("Unnamed product");
    }

    if (product.getDisplayLabel() == null) {
        product.setDisplayLabel(product.getName());
    }

    return product;
}
~~~

Không nên thay thế dữ liệu lỗi bằng một giá trị mặc định một cách âm thầm nếu điều đó che giấu vấn đề dữ liệu. Với field bắt buộc theo nghiệp vụ, có thể ghi nhận metric hoặc phát hiện lỗi ở service.

Nếu callback thay đổi field trước converter, cần đảm bảo kiểu dữ liệu đúng với mapping/converter. Ví dụ field numeric không nên được gán một chuỗi tùy ý.

### Tương thích ngược không thay thế migration

Callback có thể là cầu nối tạm thời khi đọc document cũ. Nếu toàn bộ index cần chuyển sang schema mới, migration hoặc reindex giúp dữ liệu nhất quán hơn và giảm logic tương thích chạy mãi trong mọi lần đọc.

Đặt thời hạn hoặc điều kiện loại bỏ callback legacy sau khi migration hoàn tất.

## 14. Hiệu năng và side effect

Callback có thể chạy nhiều lần trong một request search vì mỗi hit có thể đi qua quá trình mapping. Một search trả 100 hit có thể gọi callback tương ứng cho nhiều entity.

Vì vậy:

- Không gọi HTTP hoặc database cho từng hit.
- Không chạy truy vấn Elasticsearch lồng nhau.
- Không ghi log toàn bộ entity ở mỗi lần đọc.
- Tránh tính toán CPU nặng trên field lớn.
- Tránh tạo object hoặc collection lớn không cần thiết.
- Không giữ entity trong static cache hoặc mutable singleton.
- Không sửa state dùng chung giữa các request.

Nếu cần enrichment từ service khác, cân nhắc batch lookup ở tầng service: thu thập các ID từ page, lấy dữ liệu bổ sung một lần, rồi ghép vào DTO.

Callback nên có tính xác định: cùng document đầu vào và cùng cấu hình sẽ tạo cùng kết quả. Điều này giúp đọc lại document không tạo side effect khác nhau.

## 15. Lỗi trong callback được xử lý như thế nào?

Nếu callback ném exception, luồng đọc có thể thất bại tùy nơi callback được gọi và cách framework bọc exception. Một callback lỗi có thể khiến toàn bộ operation đọc không trả được kết quả, dù Elasticsearch đã trả document thành công.

Không nên nuốt mọi exception:

~~~java
try {
    // callback logic
} catch (Exception ex) {
    // Không nên âm thầm bỏ qua mọi lỗi.
}
~~~

Thay vào đó:

- Xác định lỗi nào có thể phục hồi bằng default.
- Xác định lỗi nào phải làm request thất bại.
- Ghi log có context như index và document ID khi được phép.
- Không log toàn bộ payload nếu chứa dữ liệu nhạy cảm.
- Dùng metric để phát hiện tỷ lệ document legacy hoặc lỗi mapping.
- Giữ exception rõ ràng để service có thể phân loại.

Nếu callback xử lý dữ liệu không tin cậy, validate trước khi đưa giá trị vào entity hoặc response.

## 16. Ví dụ đầy đủ: chuẩn hóa Product sau khi đọc

Giả sử ứng dụng cần trim tên và tạo display label sau khi converter đã mapping:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    private Double price;

    @Transient
    private String displayLabel;

    // getters and setters
}
~~~

Callback:

~~~java
@Component
public class ProductAfterConvertCallback
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product product,
            Document document,
            IndexCoordinates index) {

        if (product.getName() != null) {
            product.setName(product.getName().trim());
        }

        if (product.getName() != null && product.getPrice() != null) {
            product.setDisplayLabel(
                product.getName() + " - " + product.getPrice()
            );
        }

        return product;
    }
}
~~~

Property displayLabel được đánh dấu transient nếu không muốn Spring Data lưu nó như field của document. Annotation cụ thể có thể là @Transient từ Spring Data mapping package; kiểm tra import đúng trong dự án.

Khi đọc qua Operations:

~~~java
Product product = operations.get(
    "P-100",
    Product.class,
    IndexCoordinates.of("products")
);
~~~

Nếu luồng get của phiên bản đang dùng đi qua entity callback infrastructure, entity trả về sẽ có displayLabel đã được tạo. Đọc bằng direct client và tự map JSON sẽ không tự chạy callback này.

### Không biến callback thành nơi định dạng mọi API

Nếu displayLabel chỉ dùng ở một endpoint, DTO mapper trong service có thể phù hợp hơn. Callback ở entity type có phạm vi rộng hơn và có thể làm các caller khác nhận entity đã biến đổi mà họ không mong đợi.

## 17. Ví dụ: chuẩn hóa document legacy trước khi convert

Giả sử index cũ lưu product_name, còn entity mới dùng name. Một callback ở giai đoạn load có thể chuẩn bị document để converter đọc theo field mới, nếu contract callback và mapping converter cho phép thao tác này.

Pseudocode:

~~~java
Document onAfterLoad(Document document, IndexCoordinates index) {
    if (!document.containsKey("name")
            && document.containsKey("product_name")) {
        document.put("name", document.get("product_name"));
    }

    return document;
}
~~~

Cần kiểm tra tên field thực tế mà converter mong đợi, bao gồm @Field(name = "...") và naming strategy. Nếu index mapping vẫn dùng field cũ, cách sửa phù hợp có thể là cập nhật mapping/entity metadata hoặc migration thay vì thêm alias field trong callback.

Không xóa field cũ trong document trung gian nếu converter hoặc logic khác vẫn cần nó. Callback chỉ thay đổi representation đang được đọc; nó không sửa _source trong index.

## 18. Kiểm thử AfterLoadCallback và AfterConvertCallback

Nên kiểm thử callback ở hai cấp:

**Unit test callback:** truyền document/entity mẫu, xác nhận callback trả kết quả đúng. Test này nhanh và hữu ích cho các nhánh null, field thiếu và giá trị legacy.

**Integration test:** đọc document từ Elasticsearch tương thích bằng đúng repository hoặc Operations API của ứng dụng, xác nhận callback được framework gọi đúng thời điểm và kết quả cuối cùng đúng.

Ví dụ kiểm thử AfterConvertCallback:

~~~java
@Test
void createsDisplayLabelAfterConversion() {
    Product product = new Product();
    product.setName(" Wireless Keyboard ");
    product.setPrice(79.5);

    Product result = callback.onAfterConvert(
        product,
        Document.create(),
        IndexCoordinates.of("products")
    );

    assertThat(result.getName()).isEqualTo("Wireless Keyboard");
    assertThat(result.getDisplayLabel())
        .isEqualTo("Wireless Keyboard - 79.5");
}
~~~

Chữ ký constructor và callback trong test cần khớp API phiên bản đang dùng.

### Các tình huống integration test

- Đọc document có đủ field.
- Đọc document thiếu field legacy.
- Đọc document có giá trị null.
- Đọc qua repository findById.
- Đọc qua ElasticsearchOperations.get hoặc search.
- Search trả nhiều hit và callback chạy trên entity content.
- Callback được gọi theo thứ tự đã cấu hình khi có nhiều callback.
- Raw client đọc document không kích hoạt callback Spring Data.
- Callback ném exception và service xử lý theo chính sách.
- Field @Transient không bị ghi trở lại khi lưu entity.

Không chỉ gọi trực tiếp method callback rồi kết luận framework đã đăng ký đúng. Cần ít nhất một integration test đi qua luồng đọc thực tế.

## 19. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Callback không chạy | Callback chưa là Spring bean hoặc API đọc không đi qua Spring Data mapping | Kiểm tra component scan và luồng đọc |
| Callback chạy khi dùng Operations nhưng không chạy với direct client | Direct client bỏ qua Spring Data callback infrastructure | Tự gọi mapper hoặc dùng Operations |
| Entity thay đổi nhưng index không đổi | Callback đọc chỉ thay đổi object trả về | Dùng Update API hoặc migration nếu cần persist |
| Field legacy không được map | Xử lý sai thời điểm hoặc tên field không khớp converter | Kiểm tra mapping và AfterLoad contract |
| displayLabel bị lưu vào index | Field chưa được đánh dấu transient hoặc mapping cho phép lưu | Đánh dấu field runtime-only |
| Search chậm sau khi thêm callback | Callback gọi mạng hoặc tính toán nặng cho từng hit | Đưa enrichment sang batch service |
| Nhiều callback cho kết quả không ổn định | Không khai báo ordering hoặc cùng sửa một field | Dùng @Order và tách trách nhiệm |
| Audit timestamp thay đổi khi đọc | Dùng callback đọc để sửa field auditing | Chỉ cập nhật audit ở lifecycle ghi |
| Callback lỗi làm hỏng cả search | Exception không được xử lý theo chính sách | Phân loại lỗi và ghi nhận context |
| Reactive request bị treo | Callback thực hiện blocking I/O | Dùng reactive contract hoặc enrichment ở reactive pipeline |

## 20. Chọn callback hay xử lý ở service?

| Nhu cầu | Nơi phù hợp |
|---|---|
| Chuẩn hóa document trước khi converter map | AfterLoadCallback |
| Điều chỉnh entity sau khi mapping | AfterConvertCallback |
| Tạo response field chỉ cho một endpoint | DTO mapper/service |
| Enrichment cần gọi nhiều service | Service layer, ưu tiên batch |
| Ghi created/modified metadata | Auditing ở lifecycle ghi |
| Sửa dữ liệu bền vững trong index | Update API hoặc migration |
| Thêm truy vấn nghiệp vụ | Repository hoặc ElasticsearchOperations |
| Xử lý raw response từ direct client | Adapter/converter do ứng dụng quản lý |

Callback nên chứa logic dùng chung, nhẹ và gắn chặt với lifecycle đọc. Logic nghiệp vụ có nhiều dependency hoặc chỉ áp dụng cho một use case nên ở service.

## 21. Checklist triển khai callback đọc

- [ ] Xác định rõ cần xử lý document trước mapping hay entity sau mapping.
- [ ] Dùng AfterLoadCallback cho giai đoạn load theo đúng contract của phiên bản.
- [ ] Dùng AfterConvertCallback cho entity đã được converter tạo.
- [ ] Đăng ký callback thành Spring bean.
- [ ] Kiểm tra callback có được gọi bởi repository/Operations API đang dùng.
- [ ] Không giả định direct ElasticsearchClient tự gọi Spring Data callbacks.
- [ ] Giữ callback nhẹ, xác định và không có side effect ngoài ý muốn.
- [ ] Kiểm tra null, field thiếu và dữ liệu legacy.
- [ ] Khai báo ordering nếu nhiều callback phụ thuộc nhau.
- [ ] Đánh dấu field runtime-only phù hợp để không lưu ngược vào index.
- [ ] Không dùng callback đọc để cập nhật auditing timestamps.
- [ ] Dùng Update API hoặc migration nếu thay đổi phải được lưu bền vững.
- [ ] Không gọi blocking I/O trong reactive flow.
- [ ] Có unit test cho logic callback.
- [ ] Có integration test đi qua luồng đọc thật.

AfterLoadCallback và AfterConvertCallback cho phép can thiệp vào hai thời điểm khác nhau của quá trình đọc Elasticsearch. AfterLoadCallback xử lý document ở giai đoạn load theo contract của phiên bản; AfterConvertCallback xử lý entity sau khi converter đã mapping. Cả hai đều tác động tới dữ liệu đang đi qua luồng đọc và không tự ghi thay đổi trở lại index. Giữ callback nhẹ, đăng ký đúng trong Spring context và đặt logic theo đúng tầng giúp việc đọc dữ liệu nhất quán mà không biến callback thành nơi chứa nghiệp vụ hoặc side effect.

