# BeforeConvertCallback để chuẩn hóa trước khi chuyển đổi

Trong Spring Data Elasticsearch, một entity Java thường được chuyển thành Document trước khi gửi tới Elasticsearch. Có những quy tắc chuẩn hóa cần chạy ở đúng thời điểm này: loại khoảng trắng thừa, chuẩn hóa mã SKU, chuyển chuỗi rỗng thành null theo quy ước, bổ sung field dẫn xuất hoặc bảo đảm một giá trị có định dạng thống nhất trước khi mapping converter ghi document.

BeforeConvertCallback là extension point dành cho bước đó. Callback nhận entity và IndexCoordinates, trả về entity sau khi xử lý. Spring Data gọi callback trước khi chuyển entity thành Document, vì vậy thay đổi được phản ánh trong dữ liệu được ghi.

Callback nên chứa các phép biến đổi nhỏ, xác định và có thể lặp lại. Nó không phải nơi xử lý toàn bộ nghiệp vụ, xác thực quyền truy cập, gọi dịch vụ ngoài hoặc điều phối transaction. Bài này giải thích lifecycle, cách triển khai callback, cách đăng ký, thứ tự thực thi, ảnh hưởng tới entity mutable/immutable, giới hạn với các đường ghi khác và cách kiểm thử trong Spring Data Elasticsearch.

## 1. Vị trí của BeforeConvertCallback trong luồng ghi

Một thao tác lưu entity thông qua Spring Data thường đi qua các bước khái quát:

~~~text
Entity Java
    |
    v
BeforeConvertCallback
    |
    v
Mapping converter
    |
    v
Document / JSON source
    |
    v
Index request
    |
    v
Elasticsearch
~~~

Ví dụ entity Product có tên "  Wireless Mouse  " và mã SKU " sku-1001 ". Callback có thể trim tên và chuyển SKU thành chữ hoa trước khi converter tạo document.

Sau callback, converter mới xử lý mapping metadata như @Id, @Field, kiểu dữ liệu, nested object và custom conversions. Vì vậy callback có thể chuẩn hóa giá trị trên entity trước khi các giá trị đó được serialize.

BeforeConvertCallback không phải callback sau khi Elasticsearch đã lưu dữ liệu. Nó cũng không xử lý kết quả tìm kiếm. Nếu cần quan sát hoặc biến đổi ở các thời điểm khác, Spring Data Elasticsearch có những callback khác trong lifecycle.

## 2. Hợp đồng của callback

Trong Spring Data Elasticsearch, callback đồng bộ thường có dạng:

~~~java
public interface BeforeConvertCallback<T> extends EntityCallback<T> {

    T onBeforeConvert(T entity, IndexCoordinates index);
}
~~~

Các kiểu chính:

- T: kiểu entity mà callback xử lý.
- entity: object sắp được chuyển đổi.
- IndexCoordinates: index hoặc index coordinates mà thao tác ghi hướng tới.
- Giá trị trả về: entity được dùng cho bước chuyển đổi tiếp theo.

Package và chữ ký chính xác cần xác nhận theo phiên bản Spring Data Elasticsearch trong dự án. Ở các phiên bản hiện đại, callback thuộc nhóm mapping event/entity callback của Spring Data Elasticsearch.

Callback cần trả về entity. Nếu callback tạo một object mới, hãy trả về object đó; thay đổi một object nhưng trả về object cũ hoặc null có thể dẫn tới dữ liệu sai hay lỗi ở bước sau.

### 2.1. Callback là một phần của entity conversion

Điểm quan trọng là callback gắn với luồng chuyển entity thành document của Spring Data. Nó cho phép can thiệp trước khi converter chạy.

Nó không tự động can thiệp vào mọi request tới Elasticsearch. Ví dụ một ứng dụng có thể ghi qua:

- Repository của Spring Data.
- ElasticsearchOperations.
- ElasticsearchClient cấp thấp.
- REST API hoặc một service khác.
- Bulk request chứa raw JSON.

Chỉ những đường ghi đi qua cơ chế entity callback của Spring Data mới có thể kích hoạt callback tương ứng. Với API bulk, query object hoặc low-level client, cần kiểm tra cụ thể đường gọi của phiên bản đang dùng thay vì giả định callback luôn chạy.

## 3. Ví dụ entity và quy tắc chuẩn hóa

Giả sử entity Product:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    public Product() {
    }

    // getters and setters
}
~~~

Một số quy tắc chuẩn hóa có thể áp dụng trước khi convert:

- Trim SKU và tên.
- Chuyển SKU về uppercase bằng Locale.ROOT.
- Chuẩn hóa category theo danh mục được quy ước.
- Chuyển chuỗi rỗng thành null nếu schema cho phép.
- Chuẩn hóa mã vùng hoặc mã quốc gia theo một format đã thống nhất.

Không nên đưa quy tắc giá như "giảm giá tối đa 30%" vào callback chỉ vì callback có thể sửa field. Đó là business invariant cần được kiểm tra ở domain/application service, nơi có đủ ngữ cảnh và có thể trả lỗi rõ ràng.

## 4. Triển khai BeforeConvertCallback

Một callback chuẩn hóa SKU và tên có thể được viết như sau:

~~~java
import java.util.Locale;

import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductNormalizationCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        if (product.getSku() != null) {
            product.setSku(
                product.getSku().trim().toUpperCase(Locale.ROOT)
            );
        }

        if (product.getName() != null) {
            product.setName(product.getName().trim());
        }

        if (product.getCategory() != null) {
            product.setCategory(product.getCategory().trim());
        }

        return product;
    }
}
~~~

Khi Spring quản lý callback bean, callback có thể được phát hiện và gọi trong entity callback infrastructure.

Ví dụ lưu:

~~~java
Product product = new Product();
product.setId("P-1001");
product.setSku(" sku-1001 ");
product.setName("  Wireless Mouse  ");
product.setCategory(" accessories ");

productRepository.save(product);
~~~

Entity được chuẩn hóa trước khi convert. Document ghi vào Elasticsearch sẽ chứa SKU và tên theo quy tắc callback.

Callback trên sửa object đầu vào trực tiếp. Cách này phù hợp với entity mutable đơn giản, nhưng cần cân nhắc khi entity được chia sẻ giữa nhiều luồng hoặc được dùng tiếp sau khi save.

## 5. Mutable entity và immutable entity

Không phải mọi entity đều có setter. Với object immutable, callback nên tạo và trả về một instance mới.

Ví dụ record:

~~~java
public record Product(
    String id,
    String sku,
    String name,
    String category,
    Long priceInCents
) {
}
~~~

Callback:

~~~java
import java.util.Locale;

import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ImmutableProductNormalizationCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        String normalizedSku = product.sku() == null
            ? null
            : product.sku().trim().toUpperCase(Locale.ROOT);

        String normalizedName = product.name() == null
            ? null
            : product.name().trim();

        String normalizedCategory = product.category() == null
            ? null
            : product.category().trim();

        return new Product(
            product.id(),
            normalizedSku,
            normalizedName,
            normalizedCategory,
            product.priceInCents()
        );
    }
}
~~~

Ở đây callback không sửa record gốc mà trả về một record mới.

Khi dùng immutable entity, cần kiểm tra mapping converter có thể tạo object từ constructor/record theo phiên bản Spring Data đang dùng. Callback không giải quyết thay thế vấn đề constructor binding hoặc tên property không khớp.

### 5.1. Có nên luôn tạo bản sao?

Không có quy tắc bắt buộc phải tạo object mới. Lựa chọn phụ thuộc model:

- Entity mutable, chỉ dùng trong một thao tác: sửa trực tiếp có thể đơn giản.
- Entity immutable: tạo object mới.
- Object có thể được chia sẻ hoặc cache: tránh mutation có thể làm thay đổi trạng thái nơi khác đang giữ reference.
- Object được tái sử dụng cho nhiều index hoặc nhiều request: ưu tiên transformation không gây side effect.

Điều quan trọng là callback phải trả về entity hợp lệ và không tạo ra hành vi khó đoán cho caller.

## 6. Chuẩn hóa chuỗi an toàn

### 6.1. Dùng Locale.ROOT cho mã kỹ thuật

Khi chuẩn hóa identifier như SKU, mã quốc gia hoặc code, dùng Locale.ROOT:

~~~java
String normalized = value.trim().toUpperCase(Locale.ROOT);
~~~

Không dùng locale mặc định của máy cho mã kỹ thuật. Một số ngôn ngữ có quy tắc chuyển chữ hoa/thường khác nhau; kết quả có thể khác giữa môi trường developer, container và production.

Với tên hiển thị tự nhiên, không tự ý uppercase hoặc lowercase toàn bộ nếu quy tắc nghiệp vụ không yêu cầu. Chuẩn hóa mã kỹ thuật và chuẩn hóa văn bản hiển thị là hai việc khác nhau.

### 6.2. Chuỗi rỗng và null

Một helper có thể chuẩn hóa chuỗi rỗng:

~~~java
private String trimToNull(String value) {
    if (value == null) {
        return null;
    }

    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
}
~~~

Callback có thể dùng helper:

~~~java
product.setName(trimToNull(product.getName()));
~~~

Nhưng chỉ làm vậy nếu schema và nghiệp vụ xem chuỗi rỗng tương đương null. Một số field cần phân biệt "không có dữ liệu" với "người dùng chủ động gửi chuỗi rỗng".

Đối với keyword, null thường không tạo indexed term thông thường. Nếu mapping dùng null_value, giá trị thay thế có thể được index cho truy vấn, nhưng _source vẫn giữ semantics null. Hãy thiết kế mapping và callback cùng nhau.

### 6.3. Không dùng callback để che giấu input sai

Trim một chuỗi là phép chuẩn hóa cơ học. Một SKU sai format, email sai cú pháp hoặc giá âm là dữ liệu cần validation.

Callback không nên âm thầm sửa "abc ???" thành một mã hợp lệ giả định. Nếu dữ liệu không hợp lệ, application service nên trả lỗi phù hợp trước khi ghi.

## 7. Sử dụng IndexCoordinates

Callback nhận IndexCoordinates, vì vậy có thể biết thao tác đang hướng tới index nào.

Ví dụ:

~~~java
@Override
public Product onBeforeConvert(
        Product product,
        IndexCoordinates index) {

    if (Arrays.asList(index.getIndexNames()).contains("products")) {
        // Apply normalization intended for this index.
    }

    return product;
}
~~~

Ví dụ dùng getIndexNames() để kiểm tra các index trong IndexCoordinates; xác nhận method và import java.util.Arrays theo API version của dự án.

Có thể dùng thông tin index khi một domain type được ghi vào các index khác nhau và cần xử lý khác biệt có chủ đích. Tuy nhiên, không nên để callback trở thành nơi chứa một ma trận logic khó quản lý theo index name.

Nếu mỗi index đại diện cho một schema khác nhau, hãy cân nhắc tách document model, mapper hoặc service rõ ràng hơn.

## 8. Đăng ký callback trong Spring

Cách đơn giản nhất là đăng ký callback như Spring bean:

~~~java
@Component
public class ProductNormalizationCallback
        implements BeforeConvertCallback<Product> {
    // implementation
}
~~~

Hoặc dùng cấu hình:

~~~java
@Configuration
public class ElasticsearchCallbackConfiguration {

    @Bean
    ProductNormalizationCallback productNormalizationCallback() {
        return new ProductNormalizationCallback();
    }
}
~~~

Không cần tự gọi callback trong service nếu Spring Data đã quản lý entity callback infrastructure. Việc gọi thủ công có thể làm chuẩn hóa hai lần hoặc tạo ra hành vi khác nhau giữa luồng repository và Operations.

Nếu callback không được gọi:

- Kiểm tra class có nằm trong component scan không.
- Kiểm tra bean có được tạo trong ApplicationContext không.
- Kiểm tra generic type của callback có đúng domain type không.
- Kiểm tra thao tác ghi có đi qua Spring Data entity conversion không.
- Kiểm tra callback infrastructure của phiên bản Spring Data Elasticsearch.
- Kiểm tra ứng dụng có tự cấu hình hoặc thay thế EntityCallbacks bean hay không.

## 9. Nhiều callback và thứ tự thực thi

Một ứng dụng có thể có nhiều callback cho cùng một entity. Ví dụ:

- Callback A trim tên.
- Callback B chuẩn hóa SKU.
- Callback C tạo normalizedSearchName.

Nếu các callback phụ thuộc kết quả của nhau, thứ tự thực thi phải rõ ràng. Spring Data entity callback infrastructure hỗ trợ cơ chế ordering thông qua các quy tắc order của Spring, chẳng hạn @Order hoặc Ordered, tùy API và phiên bản.

Ví dụ:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class ProductNameTrimCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Callback khác:

~~~java
@Component
@Order(20)
public class ProductSearchNameCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Trong ví dụ, callback tạo search name được thiết kế để chạy sau callback trim tên.

Không dựa vào thứ tự phát hiện bean tình cờ. Nếu nhiều callback sửa cùng field, hãy xác định rõ thứ tự và kiểm thử kết quả cuối. Khi có thể, gom các bước phụ thuộc chặt vào một callback có tên và trách nhiệm rõ ràng.

Thứ tự mặc định, cách sắp xếp callback và tương tác với callback auditing có thể phụ thuộc phiên bản Spring Data. Hãy xác nhận bằng API đang dùng và integration test.

## 10. Callback và các điểm trong entity lifecycle khác

BeforeConvertCallback chỉ là một điểm trong vòng đời entity. Spring Data Elasticsearch có các callback khác cho các thời điểm khác nhau. Tên và chữ ký chi tiết cần đối chiếu theo version, nhưng có thể phân biệt về mục đích như sau:

| Điểm lifecycle | Mục đích |
|---|---|
| BeforeConvert | Thay đổi entity trước khi converter tạo Document |
| Callback trước save (nếu version cung cấp) | Can thiệp gần thời điểm lưu, sau bước convert |
| AfterSave | Xử lý sau khi thao tác lưu hoàn tất |
| AfterLoad | Can thiệp Document sau khi đọc từ Elasticsearch |
| AfterConvert | Xử lý entity sau khi Document được convert thành object |

Ví dụ:

- Chuẩn hóa SKU trước khi ghi: BeforeConvert.
- Kiểm tra representation Document đã tạo: điểm callback trước save nếu API phù hợp.
- Ghi log sau khi lưu: AfterSave.
- Điều chỉnh document sau khi đọc: AfterLoad.
- Bổ sung trạng thái transient vào object sau convert: AfterConvert nếu phù hợp.

Không chọn callback chỉ theo tên gần giống. Xác định dữ liệu đang ở dạng entity hay Document, thao tác đã xảy ra hay chưa, và giá trị trả về có được sử dụng tiếp hay không.

## 11. Callback và auditing

Auditing theo dõi thông tin như thời điểm tạo, thời điểm sửa và người tạo/người sửa. Đây là nhu cầu riêng so với chuẩn hóa dữ liệu.

Spring Data Elasticsearch có hỗ trợ auditing thông qua các annotation như:

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;

@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
~~~

Có thể bật auditing qua cấu hình Spring phù hợp, thường dùng @EnableElasticsearchAuditing, và cung cấp AuditorAware nếu cần xác định người thực hiện.

Ví dụ cấu hình khái niệm:

~~~java
@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {
}
~~~

Auditing callback có thể tự động gán các field auditing theo lifecycle. Không nên tự viết BeforeConvertCallback chỉ để thay thế auditing nếu framework đã cung cấp cơ chế phù hợp.

Nếu cả auditing và custom callback cùng sửa entity, hãy kiểm tra thứ tự. Ví dụ callback custom có thể chuẩn hóa một field, còn auditing cập nhật timestamp. Tránh để custom callback ghi đè createdAt hoặc lastModifiedAt ngoài ý muốn.

Auditing không thay thế audit event nghiệp vụ. Nếu cần biết ai đã phê duyệt đơn hàng, thay đổi giá từ bao nhiêu thành bao nhiêu hoặc lý do thay đổi, hãy ghi audit event theo domain/application architecture.

## 12. Callback và validation

Callback có thể kiểm tra một điều kiện kỹ thuật tối thiểu trước khi convert, nhưng không nên dùng nó làm lớp validation chính của API.

| Công việc | Nơi phù hợp |
|---|---|
| Trim mã SKU | BeforeConvertCallback hoặc mapper |
| Chuẩn hóa chữ hoa cho identifier | BeforeConvertCallback |
| Kiểm tra giá không âm theo nghiệp vụ | Application/domain validation |
| Kiểm tra user có quyền sửa sản phẩm | Security/application service |
| Kiểm tra SKU có duy nhất trong hệ thống | Domain/application service cùng cơ chế concurrency phù hợp |
| Gọi dịch vụ kiểm tra thuế | Integration/application service |
| Bổ sung createdAt/lastModifiedAt | Auditing |
| Chuyển đổi kiểu dữ liệu của source | Converter hoặc mapping configuration |

Nếu callback phát hiện dữ liệu không thể convert, có thể ném exception khiến thao tác ghi thất bại. Nhưng exception đó thường không tự trở thành response validation thân thiện cho HTTP client. Application service cần bắt và ánh xạ lỗi theo API contract.

## 13. Những việc không nên làm trong BeforeConvertCallback

Callback thường được gọi trong luồng ghi và có thể chạy rất nhiều lần. Tránh:

- Gọi HTTP service hoặc database bên ngoài theo từng entity.
- Gửi email, webhook hoặc message có side effect.
- Thực hiện transaction nghiệp vụ nhiều bước.
- Kiểm tra quyền người dùng mà không có security context rõ ràng.
- Sinh giá trị ngẫu nhiên mỗi lần callback chạy nếu cần idempotency.
- Dựa vào thời gian hiện tại cho field nghiệp vụ mà không xác định quy tắc.
- Thay đổi một object dùng chung ở nhiều request.
- Ghi log toàn bộ entity có dữ liệu nhạy cảm.
- Thực hiện truy vấn Elasticsearch lồng bên trong callback cho từng entity.

Các thao tác I/O trong callback làm luồng ghi khó dự đoán, dễ tạo N+1 request và làm bulk indexing chậm. Callback nên là một transformation nhẹ, đồng bộ và xác định.

Nếu cần enrichment từ dịch vụ ngoài, thực hiện trong application/integration layer trước khi gọi Elasticsearch hoặc dùng cơ chế enrich index của Elasticsearch nếu dữ liệu tham chiếu và freshness phù hợp.

## 14. Callback có chạy khi dùng Repository và ElasticsearchOperations không?

Các thao tác entity-oriented của Spring Data như repository save thường đi qua mapping infrastructure, vì vậy là đường sử dụng phù hợp để kiểm tra BeforeConvertCallback.

Ví dụ:

~~~java
productRepository.save(product);
~~~

Hoặc:

~~~java
operations.save(product);
~~~

Tuy nhiên, không suy rộng kết quả này sang mọi API chỉ vì tên method có chữ index hoặc bulk.

| Đường ghi | Callback cần xem xét |
|---|---|
| Repository save(entity) | Thường đi qua Spring Data entity conversion |
| ElasticsearchOperations.save(entity) | Đường entity-oriented cần callback |
| saveAll(entities) | Kiểm tra implementation/version và test đường bulk thực tế |
| IndexQuery có object | Xác nhận callback có được gọi trong operation path đó không |
| UpdateQuery với Document | Không nên giả định entity callback chạy; đây là partial update document |
| Elasticsearch Java API Client trực tiếp | Không đi qua Spring Data callback infrastructure |
| REST/Bulk API raw JSON | Không đi qua Spring Data callback infrastructure |
| Ingest pipeline | Chạy phía Elasticsearch, độc lập với Java callback |

Một quy tắc thực tế: callback không phải interceptor toàn cục cho cluster. Nó chỉ có tác dụng trên những thao tác được Spring Data điều phối qua callback infrastructure.

Nếu một ứng dụng vừa dùng repository save vừa dùng low-level client cho bulk import, chuẩn hóa chỉ đặt trong callback có thể tạo ra hai kết quả dữ liệu khác nhau. Khi đó cần đưa transformation chung vào một mapper dùng chung, dùng ingest pipeline hoặc bảo đảm mọi producer áp dụng cùng contract.

## 15. Bulk và callback

Bulk indexing giúp gửi nhiều document trong một request. Nhưng có nhiều cách xây dựng bulk:

- Gọi saveAll(entities) của repository.
- Dùng ElasticsearchOperations với các entity-oriented operation.
- Tạo IndexQuery/UpdateQuery.
- Dùng Elasticsearch Java API Client với raw operations.

Callback coverage phụ thuộc đường triển khai cụ thể. Không thể suy ra chỉ từ việc request cuối cùng là Bulk API rằng BeforeConvertCallback chắc chắn được gọi cho từng entity.

Khi callback là một phần bắt buộc của dữ liệu, hãy viết integration test trên đúng phương thức bulk production sử dụng. Có thể dùng một field marker trong test hoặc một spy callback để xác nhận số lần gọi, sau đó đọc document đã index để xác nhận dữ liệu thực sự được chuẩn hóa.

Đối với import khối lượng lớn, nếu normalization cần áp dụng nhất quán cho nhiều producer, cân nhắc một mapper chung hoặc ingest pipeline. Tránh dựa vào callback mà không kiểm tra đường import.

## 16. Reactive application và callback reactive

Spring Data Elasticsearch có cả API imperative và reactive. Callback đồng bộ BeforeConvertCallback<T> không nên được xem là thay thế tự động cho callback reactive.

Trong reactive stack, Spring Data có callback reactive tương ứng ở các phiên bản hỗ trợ, thường trả về Publisher<T> thay vì trực tiếp trả entity. Tên interface, package và cách đăng ký phụ thuộc version.

Một số nguyên tắc:

- Dùng callback đúng với loại template/repository đang sử dụng.
- Không chặn reactive thread bằng HTTP hoặc database call đồng bộ.
- Nếu transformation thuần CPU và nhẹ, giữ nó ngắn.
- Nếu cần I/O, thực hiện trong reactive service chain với timeout và error handling rõ.
- Viết test bằng reactive test tools để xác nhận callback được thực thi trong đúng flow.

Không đăng ký một callback imperative rồi giả định reactive operations sẽ tự gọi nó. Kiểm tra tài liệu và type signature của ReactiveElasticsearchOperations trong dependency thực tế.

## 17. Callback, converter và ingest pipeline khác nhau

Ba cơ chế đều có thể tác động tới dữ liệu trước khi index, nhưng nằm ở các lớp khác nhau:

| Cơ chế | Chạy ở đâu | Phù hợp với |
|---|---|---|
| BeforeConvertCallback | Spring Data application, trước entity conversion | Chuẩn hóa entity Java trước khi convert |
| Mapping converter/custom conversions | Spring Data mapping layer | Ánh xạ kiểu Java và Document |
| Ingest pipeline | Elasticsearch, khi document được ingest | Chuẩn hóa chung cho nhiều producer sau khi request tới cluster |

Ví dụ:

- Callback trim SKU trong entity Product.
- Converter ánh xạ Money thành số cent.
- Ingest pipeline chuẩn hóa field từ cả Java service, Logstash và bulk importer.

Nếu cùng một phép biến đổi được triển khai ở nhiều lớp, phải bảo đảm semantics giống nhau. Ví dụ uppercase SKU ở callback nhưng lowercase SKU ở pipeline sẽ tạo ra kết quả khó đoán giữa các producer.

Chọn một nơi làm nguồn chuẩn cho từng quy tắc. Những quy tắc chỉ liên quan đến Java domain model thường phù hợp với mapper/callback. Những quy tắc ingest chung cho nhiều producer có thể phù hợp với pipeline.

## 18. Callback và custom conversion

Custom conversion dùng khi một kiểu Java cần được chuyển sang hoặc đọc từ representation Elasticsearch khác.

Ví dụ một kiểu Money có thể được ghi thành số cent hoặc một object có cấu trúc. Đây là trách nhiệm của converter/custom conversions, không phải callback.

Callback phù hợp khi entity đã có kiểu Java và chỉ cần chuẩn hóa giá trị trước khi converter xử lý.

| Nhu cầu | Cơ chế |
|---|---|
| Trim chuỗi trước khi ghi | BeforeConvertCallback |
| Chuyển Money thành Long | Custom writing converter |
| Chuyển Long thành Money khi đọc | Custom reading converter |
| Đổi cấu trúc document dùng chung nhiều producer | Ingest pipeline hoặc schema migration |
| Tính giá sau thuế theo chính sách nghiệp vụ | Domain/application service |

Không dùng callback để tự serialize JSON hoặc tạo Document thủ công nếu mapping converter đã có thể làm đúng việc đó.

## 19. Tác động khi reindex và ghi lại dữ liệu

Callback có thể chạy lại mỗi lần entity được lưu qua Spring Data callback path. Vì vậy phép chuẩn hóa nên idempotent.

Một phép biến đổi idempotent có đặc điểm:

~~~text
normalize(normalize(value)) = normalize(value)
~~~

Ví dụ trim và uppercase là idempotent:

- " sku-1001 " → "SKU-1001"
- Chạy lại → vẫn là "SKU-1001"

Ngược lại, phép nối chuỗi "prefix-" + value không idempotent nếu callback chạy nhiều lần:

- Lần 1: prefix-SKU-1001
- Lần 2: prefix-prefix-SKU-1001

Nếu cần tạo field dẫn xuất, hãy tính từ field gốc hoặc kiểm tra trạng thái trước khi gán.

Reindex qua Elasticsearch Reindex API không chạy Java BeforeConvertCallback vì dữ liệu được chuyển trực tiếp giữa index trong Elasticsearch. Nếu muốn chuẩn hóa dữ liệu cũ trong lúc reindex, dùng destination ingest pipeline hoặc một job application đọc entity và ghi lại qua Spring Data callback path.

## 20. Kiểm thử callback

Nên có unit test cho transformation và integration test cho việc callback thực sự được Spring Data gọi.

### 20.1. Unit test trực tiếp

~~~java
@Test
void shouldNormalizeSkuAndName() {
    Product product = new Product();
    product.setSku(" sku-1001 ");
    product.setName("  Wireless Mouse  ");

    ProductNormalizationCallback callback =
        new ProductNormalizationCallback();

    Product result = callback.onBeforeConvert(
        product,
        IndexCoordinates.of("products")
    );

    assertThat(result.getSku()).isEqualTo("SKU-1001");
    assertThat(result.getName()).isEqualTo("Wireless Mouse");
}
~~~

Unit test xác nhận logic callback. Nó chưa chứng minh Spring đã đăng ký callback hoặc repository save đã đi qua callback infrastructure.

### 20.2. Integration test với Spring context

Có thể dùng @SpringBootTest cùng Elasticsearch test instance hoặc Testcontainers. Lưu entity qua đúng repository/Operations path mà ứng dụng sử dụng, sau đó đọc lại document.

Kiểm tra:

- Callback bean được tạo.
- Callback được gọi khi save entity.
- Giá trị trong _source đã được chuẩn hóa.
- Field không liên quan vẫn giữ nguyên.
- Entity immutable trả về instance đã chuẩn hóa.
- IndexCoordinates nhận đúng index trong trường hợp index động.
- Callback order đúng nếu có nhiều callback.

Ví dụ assertion sau khi save và đọc lại:

~~~java
productRepository.save(product);

Product saved = productRepository.findById("P-1001")
    .orElseThrow();

assertThat(saved.getSku()).isEqualTo("SKU-1001");
assertThat(saved.getName()).isEqualTo("Wireless Mouse");
~~~

Nếu cần xác nhận callback chạy trước converter, có thể kiểm tra raw _source hoặc dùng converter/test spy theo khả năng test infrastructure. Chỉ kiểm tra object gốc sau save chưa chắc đủ, nhất là khi callback tạo immutable instance mới mà caller không nhận lại object đó.

### 20.3. Kiểm tra đường bulk

Nếu production dùng saveAll, bulk operations hoặc IndexQuery, viết test riêng cho chính API đó. Không dùng kết quả test repository.save đơn lẻ để suy luận callback coverage cho mọi bulk path.

Test nên xác nhận cả số lần callback được gọi và source thực tế đã ghi. Nếu callback chỉ chạy trong một đường ghi, cần có một transformation chung khác cho các đường còn lại.

### 20.4. Kiểm tra idempotency và null

Bổ sung test cho:

- Gọi callback hai lần không làm thay đổi kết quả lần đầu.
- Field null vẫn null.
- Chuỗi rỗng được giữ hay chuyển null theo quy tắc đã chọn.
- Unicode và mã kỹ thuật được chuẩn hóa đúng.
- Locale của JVM không làm thay đổi kết quả identifier.
- Field không thuộc phạm vi callback không bị sửa.

## 21. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Callback không chạy | Bean chưa được scan hoặc write path không dùng entity callbacks | Kiểm tra ApplicationContext và operation path |
| Callback không nhận entity mong muốn | Generic type không đúng | Khai báo callback với domain type chính xác |
| Thay đổi không xuất hiện trong document | Callback sửa object nhưng trả về object khác hoặc không trả đúng instance | Trả về entity đã chuẩn hóa |
| Immutable entity không được cập nhật | Callback tạo instance mới nhưng trả về object cũ | Return instance mới |
| Callback chạy hai lần | Gọi thủ công ngoài Spring hoặc nhiều đường save | Bỏ gọi thủ công và kiểm tra lifecycle |
| Giá trị bị prefix lặp | Transformation không idempotent | Tính lại từ source hoặc kiểm tra trước khi gán |
| Bulk import không được chuẩn hóa | Bulk path không gọi callback | Test đúng API bulk; dùng mapper chung hoặc pipeline |
| Low-level client bỏ qua callback | Không đi qua Spring Data infrastructure | Chuẩn hóa trước request hoặc dùng ingest pipeline |
| Hai callback ghi đè nhau | Thứ tự không rõ hoặc cùng sửa field | Dùng ordering và một owner cho từng field |
| Callback gọi dịch vụ làm save chậm | Có I/O hoặc N+1 trong callback | Chuyển I/O sang application service |
| Callback sửa nhầm dữ liệu theo index | Logic dựa trên IndexCoordinates quá rộng | Tách mapper/schema và test index cụ thể |
| Auditing field bị ghi đè | Custom callback và auditing cùng sửa timestamp | Dùng auditing cho metadata và xác định order |
| Reactive callback không được gọi | Dùng callback imperative cho reactive path | Dùng reactive callback phù hợp phiên bản |

## 22. Quy trình triển khai BeforeConvertCallback

Khi thêm callback vào ứng dụng:

1. Xác định domain type và các field cần chuẩn hóa.
2. Xác định transformation là kỹ thuật, xác định và idempotent.
3. Giữ validation nghiệp vụ ở application/domain layer.
4. Viết callback implement BeforeConvertCallback<T>.
5. Chọn mutate entity hay trả instance mới theo model.
6. Đăng ký callback như Spring bean.
7. Xác định thứ tự nếu có nhiều callback cùng loại.
8. Kiểm tra callback có đúng với imperative/reactive stack không.
9. Kiểm tra các write path thực tế: repository, Operations, bulk và low-level client.
10. Viết unit test và integration test đọc lại document.
11. Kiểm tra tương tác với converter, auditing và ingest pipeline.
12. Theo dõi tác động lên throughput nếu callback chạy cho nhiều entity.

Callback nên nhỏ, dễ kiểm thử và không có side effect bên ngoài. Nếu transformation cần nhiều ngữ cảnh hoặc có thể thất bại theo quy tắc nghiệp vụ, hãy thực hiện ở application service trước khi gọi persistence.

## 23. Bảng tra cứu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Chuẩn hóa entity trước khi convert | BeforeConvertCallback<T> |
| Trim/uppercase identifier | Callback hoặc mapper dùng chung |
| Entity mutable | Sửa entity rồi return entity |
| Entity immutable/record | Tạo và return instance mới |
| Biết index đích | Dùng IndexCoordinates |
| Nhiều callback cùng entity | Dùng ordering và test thứ tự |
| Gán created/modified metadata | Spring Data auditing |
| Chuyển kiểu Java sang Document | Mapping converter/custom conversions |
| Chuẩn hóa cho nhiều producer | Ingest pipeline hoặc shared mapping service |
| Partial update bằng raw Document | Kiểm tra Update API; không giả định callback chạy |
| Bulk import | Test đúng bulk path |
| Reactive write | Reactive callback tương ứng nếu version hỗ trợ |
| Reindex trong Elasticsearch | Ingest pipeline ở destination nếu cần chuẩn hóa |
| Gọi API ngoài hoặc kiểm tra quyền | Application/integration/security layer |
| Kiểm tra callback | Unit test và integration test với Spring context |

BeforeConvertCallback là điểm mở rộng phù hợp để chuẩn hóa entity ngay trước khi Spring Data Elasticsearch chuyển nó thành Document. Hãy giữ callback nhẹ, xác định và idempotent; trả về đúng entity đã xử lý, dùng instance mới với entity immutable, và kiểm tra thứ tự nếu có nhiều callback. Callback chỉ chạy trên các đường ghi đi qua entity callback infrastructure, vì vậy phải kiểm thử riêng repository, Operations và bulk path mà ứng dụng thực sự dùng. Auditing, custom conversion, ingest pipeline và business validation có trách nhiệm riêng; chọn đúng lớp giúp dữ liệu nhất quán mà không biến callback thành nơi chứa toàn bộ logic ứng dụng.

