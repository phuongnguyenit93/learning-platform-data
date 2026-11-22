# Reactive callback, ReactiveAuditorAware và bật auditing reactive

Spring Data Elasticsearch có API reactive dựa trên Reactor. Khi ghi một entity bằng reactive repository hoặc ReactiveElasticsearchOperations, dữ liệu đi qua một luồng Publisher thay vì được xử lý đồng bộ ngay tại lời gọi method.

Trong luồng này, reactive entity callback cho phép chuẩn hóa entity trước khi Spring Data chuyển nó thành Document. Reactive auditing bổ sung thông tin như thời điểm tạo, thời điểm sửa và người thực hiện. Thành phần ReactiveAuditorAware cung cấp danh tính hiện tại dưới dạng Mono, phù hợp với cách Spring Security reactive lưu security context trong Reactor Context.

Ba khái niệm liên quan nhưng có nhiệm vụ riêng:

- Reactive callback can thiệp vào lifecycle của entity, ví dụ chuẩn hóa mã SKU trước khi convert.
- ReactiveAuditorAware cung cấp actor hiện tại để auditing có thể điền các field CreatedBy/LastModifiedBy.
- Bật reactive auditing đăng ký cơ chế auditing để các annotation CreatedDate, LastModifiedDate, CreatedBy và LastModifiedBy được xử lý trong reactive write path.

Bài này trình bày luồng thực thi, cách triển khai callback và auditor, cấu hình auditing, cách dùng với reactive repository/template, các giới hạn của Reactor Context, kiểm thử và những lỗi thường gặp.

## 1. Reactive write lifecycle

Với API imperative, lời gọi save thường thực hiện công việc đồng bộ và trả entity hoặc kết quả trực tiếp. Với reactive API, lời gọi thường trả về Mono hoặc Flux. Công việc chỉ chạy khi publisher được subscribe.

Luồng ghi entity khái quát:

~~~text
Reactive repository / ReactiveElasticsearchOperations
                    |
                    v
              Publisher<Entity>
                    |
                    v
          Reactive entity callbacks
                    |
                    v
          ReactiveBeforeConvertCallback
                    |
                    v
             Mapping converter
                    |
                    v
             Document / JSON
                    |
                    v
              Elasticsearch
                    |
                    v
             Mono<Entity>
~~~

ReactiveBeforeConvertCallback chạy trước khi entity được chuyển thành Document. Callback nhận entity và IndexCoordinates, sau đó trả về Publisher chứa entity tiếp theo.

Reactive auditing cũng được tích hợp qua cơ chế callback. Khi auditing được bật, callback auditing đọc thời gian và auditor hiện tại rồi cập nhật các field auditing trên entity theo metadata.

Điểm cần nhớ: reactive không có nghĩa là mọi phép xử lý đều tự động chạy song song. Reactor điều phối việc thực thi qua Publisher, subscription, scheduler và backpressure. Callback phải trả về publisher đúng hợp đồng và không tự ý phá vỡ luồng bằng thao tác blocking.

## 2. Phân biệt callback imperative và reactive

Hai callback có hình dạng gần giống nhau nhưng kiểu trả về khác nhau:

~~~java
// Imperative callback: trả về entity trực tiếp.
public interface BeforeConvertCallback<T> extends EntityCallback<T> {
    T onBeforeConvert(T entity, IndexCoordinates index);
}

// Reactive callback: trả về Publisher.
public interface ReactiveBeforeConvertCallback<T> extends EntityCallback<T> {
    Publisher<T> onBeforeConvert(T entity, IndexCoordinates index);
}
~~~

Trong Spring Data Elasticsearch, reactive callback thường nằm trong package mapping event của module Elasticsearch. Hãy xác nhận import và chữ ký trên Javadoc đúng với phiên bản dependency đang dùng.

Khác biệt:

| Callback imperative | Callback reactive |
|---|---|
| Trả trực tiếp T | Trả Publisher<T> |
| Thực thi đồng bộ | Thực thi theo subscription |
| Thường dùng với ElasticsearchOperations | Dùng với ReactiveElasticsearchOperations |
| Không dùng Reactor Context | Có thể đọc Reactor Context |
| Không biểu diễn async bằng Mono/Flux | Có thể compose Mono/Flux |

Không triển khai callback imperative rồi kỳ vọng reactive template tự gọi callback đó. Cũng không đăng ký cùng một logic ở hai nơi nếu không có lý do, vì có thể chuẩn hóa hai lần.

## 3. ReactiveBeforeConvertCallback làm gì?

Callback này thích hợp cho transformation nhẹ trước khi convert entity thành Document, ví dụ:

- Trim mã kỹ thuật.
- Chuẩn hóa SKU thành uppercase bằng Locale.ROOT.
- Chuẩn hóa khoảng trắng ở tên.
- Chuẩn hóa chuỗi rỗng theo schema.
- Tạo field dẫn xuất đơn giản từ dữ liệu đã có trên entity.

Callback không nên chịu trách nhiệm:

- Xác thực quyền truy cập.
- Kiểm tra business invariant cần nhiều ngữ cảnh.
- Gọi API bên ngoài theo từng entity.
- Gửi email hoặc message có side effect.
- Điều phối transaction nhiều bước.
- Thay thế auditing hoặc custom converter.

Nếu transformation là một phép tính thuần túy và nhẹ, callback là vị trí phù hợp. Nếu cần I/O hoặc quyết định nghiệp vụ, hãy thực hiện trong service trước khi gọi persistence.

## 4. Triển khai reactive callback

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

    public Product() {
    }

    // getters and setters
}
~~~

Callback chuẩn hóa SKU và tên:

~~~java
import java.util.Locale;

import org.reactivestreams.Publisher;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ProductNormalizationCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        return Mono.fromSupplier(() -> {
            if (product.getSku() != null) {
                product.setSku(
                    product.getSku().trim().toUpperCase(Locale.ROOT)
                );
            }

            if (product.getName() != null) {
                product.setName(product.getName().trim());
            }

            return product;
        });
    }
}
~~~

Mono.fromSupplier trì hoãn phép chuẩn hóa đến lúc subscription và chuyển exception phát sinh trong supplier thành tín hiệu error của Mono.

Callback là Spring bean nên có thể được Spring Data entity callback infrastructure phát hiện. Không gọi callback thủ công trong service nếu framework đã gọi nó; làm vậy có thể khiến transformation chạy hai lần.

Tên package hoặc interface có thể khác ở phiên bản cũ. Hãy dùng dependency Spring Data Elasticsearch thực tế để xác nhận import ReactiveBeforeConvertCallback.

### 4.1. Vì sao dùng Mono.fromSupplier?

Có thể thấy một cách viết như sau:

~~~java
return Mono.just(normalize(product));
~~~

Cách này gọi normalize ngay khi method callback được gọi, trước khi Mono được subscribe. Nếu normalize ném exception, lỗi có thể phát sinh đồng bộ tại thời điểm dựng publisher.

Với:

~~~java
return Mono.fromSupplier(() -> normalize(product));
~~~

phép tính chạy khi subscriber yêu cầu dữ liệu. Đây là cách tự nhiên hơn cho transformation đồng bộ trong reactive callback.

Nếu transformation vốn đã trả về Mono từ một nguồn reactive, hãy compose publisher đó trực tiếp thay vì bọc nó trong Mono.just.

### 4.2. Immutable entity

Với entity immutable hoặc record, callback cần tạo instance mới:

~~~java
public record Product(
    String id,
    String sku,
    String name
) {
}
~~~

~~~java
@Component
public class ImmutableProductCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        return Mono.fromSupplier(() -> new Product(
            product.id(),
            product.sku() == null
                ? null
                : product.sku().trim().toUpperCase(Locale.ROOT),
            product.name() == null
                ? null
                : product.name().trim()
        ));
    }
}
~~~

Giá trị trả về là entity được dùng cho bước convert tiếp theo. Không tạo instance mới rồi trả về object ban đầu.

Spring Data cần có khả năng materialize immutable entity theo constructor/record binding của phiên bản đang dùng. Callback không thay thế cấu hình mapping cho constructor.

## 5. Đăng ký và thứ tự callback

Thông thường, callback được đăng ký như Spring bean bằng @Component hoặc @Bean:

~~~java
@Component
public class ProductNormalizationCallback
        implements ReactiveBeforeConvertCallback<Product> {
    // implementation
}
~~~

Không cần tự tạo một callback registry trong service nếu Spring Data đã cấu hình entity callback infrastructure.

Nếu có nhiều callback cùng xử lý một entity, hãy xác định thứ tự khi các bước phụ thuộc nhau. Spring entity callback hỗ trợ ordering qua các cơ chế order của Spring như @Order hoặc Ordered trong các phiên bản tương ứng.

~~~java
@Component
@Order(10)
public class ProductTrimCallback
        implements ReactiveBeforeConvertCallback<Product> {
    // trim product name
}
~~~

~~~java
@Component
@Order(20)
public class ProductDerivedNameCallback
        implements ReactiveBeforeConvertCallback<Product> {
    // build a normalized search name from the trimmed name
}
~~~

Thứ tự thấp hơn thường có precedence cao hơn trong cơ chế ordering của Spring. Hãy xác nhận ordering trên phiên bản framework đang dùng và viết test cho kết quả cuối. Không dựa vào thứ tự phát hiện bean tình cờ.

Nếu hai callback cùng ghi một field, nên chọn một owner rõ ràng hoặc gom các bước phụ thuộc chặt vào một callback duy nhất.

## 6. Không block hoặc subscribe thủ công trong callback

Reactive callback phải trả về Publisher để framework ghép vào write pipeline. Không gọi block, subscribe hoặc chờ Future bên trong callback.

Ví dụ không nên làm:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product product,
        IndexCoordinates index) {

    String category = categoryService.findCategory(product.getSku()).block();

    product.setCategory(category);
    return Mono.just(product);
}
~~~

Đoạn code trên block reactive thread để chờ I/O. Nó làm mất lợi ích của reactive execution, có thể gây starvation và làm luồng ghi khó kiểm soát.

Cũng không nên:

~~~java
someMono.subscribe();
return Mono.just(product);
~~~

subscribe thủ công tạo một luồng thực thi tách rời. Spring Data không còn kiểm soát được thời điểm hoàn tất hoặc lỗi của tác vụ đó.

Nếu thực sự cần I/O bất đồng bộ, compose nó vào publisher được trả về:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product product,
        IndexCoordinates index) {

    return categoryService.findCategory(product.getSku())
        .map(category -> {
            product.setCategory(category);
            return product;
        });
}
~~~

Tuy nhiên, cần cân nhắc kỹ việc gọi dịch vụ ngoài trong callback. Nếu callback chạy cho mỗi entity trong bulk, nó có thể tạo một lượng lớn request phụ, làm tăng latency và khiến việc retry phức tạp. Thông thường, enrichment thuộc application service hoặc một bước ingest chuyên biệt sẽ dễ kiểm soát hơn.

## 7. Lỗi trong reactive callback

Nếu callback trả về Publisher phát ra error, error đó đi tiếp trong reactive write chain và có thể làm thao tác save thất bại.

Ví dụ:

~~~java
return Mono.fromSupplier(() -> {
    if (product.getSku() == null) {
        throw new IllegalArgumentException("SKU is required");
    }

    product.setSku(product.getSku().trim().toUpperCase(Locale.ROOT));
    return product;
});
~~~

Application service có thể ánh xạ lỗi ở ranh giới API:

~~~java
return repository.save(product)
    .onErrorMap(
        IllegalArgumentException.class,
        ex -> new InvalidProductException(ex.getMessage(), ex)
    );
~~~

Không nuốt error trong callback rồi trả entity chưa hợp lệ. Nếu lỗi là điều kiện nghiệp vụ, tốt hơn nên validate trước khi persistence để có thông báo và mã lỗi rõ ràng.

Không ghi log toàn bộ entity khi callback thất bại; entity có thể chứa dữ liệu cá nhân hoặc thông tin nhạy cảm. Log mã correlation và thông tin kỹ thuật tối thiểu cần thiết.

## 8. Reactor Context và dữ liệu theo request

Trong reactive application, thông tin theo request thường được truyền qua Reactor Context. Nó không phụ thuộc vào việc một request luôn chạy trên cùng một thread.

Điều này đặc biệt quan trọng với Spring Security reactive. Security context được lưu trong Reactor Context và được truy cập bằng ReactiveSecurityContextHolder.

Không dùng SecurityContextHolder kiểu ThreadLocal để lấy principal trong reactive callback. Khi publisher chuyển scheduler hoặc tiếp tục trên thread khác, ThreadLocal có thể không chứa đúng authentication.

Một số nguyên tắc:

- Đọc thông tin request qua API reactive context.
- Không lưu principal hiện tại vào field của singleton callback bean.
- Không dùng biến static để giữ user hiện tại.
- Không giả định thread name xác định được người dùng.
- Giữ dữ liệu actor gắn với subscription hiện tại.

## 9. ReactiveAuditorAware là gì?

Spring Data Commons định nghĩa ReactiveAuditorAware<T> để cung cấp auditor hiện tại theo kiểu reactive.

Hợp đồng thường có dạng:

~~~java
public interface ReactiveAuditorAware<T> {
    Mono<T> getCurrentAuditor();
}
~~~

T là kiểu dữ liệu của actor, ví dụ String, UUID hoặc một kiểu UserId của ứng dụng.

Khác với AuditorAware imperative trả Optional<T>, ReactiveAuditorAware trả Mono<T>. Mono có thể:

- Phát ra một auditor.
- Hoàn tất rỗng nếu không có auditor.
- Phát ra error nếu không thể xác định auditor.

Auditing infrastructure dùng kết quả này để điền các field @CreatedBy và @LastModifiedBy.

Package của interface là Spring Data Commons, thường là org.springframework.data.domain.ReactiveAuditorAware. Hãy xác nhận dependency Spring Data Commons đi cùng Spring Data Elasticsearch của dự án.

## 10. Triển khai auditor từ Spring Security reactive

Ví dụ ứng dụng dùng Spring Security WebFlux và muốn lưu tên người dùng hiện tại:

~~~java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class SpringSecurityAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .filter(name -> name != null && !name.isBlank())
            .filter(name -> !"anonymousUser".equals(name));
    }
}
~~~

Nếu không có SecurityContext hoặc người dùng chưa xác thực, publisher có thể hoàn tất rỗng. Khi đó auditing không có actor để ghi vào CreatedBy/LastModifiedBy.

Tên principal là một lựa chọn đơn giản. Trong hệ thống thực tế, có thể dùng user ID bất biến thay cho username vì username có thể đổi. Nếu auditor field lưu UUID, khai báo ReactiveAuditorAware<UUID> và chuyển principal sang ID tương ứng.

Không lấy actor từ một field do client gửi trong request body. Actor phải đến từ security context hoặc một execution context đáng tin cậy do hệ thống tạo.

### 10.1. Không có Spring Security

Nếu ứng dụng không dùng Spring Security, vẫn có thể triển khai ReactiveAuditorAware bằng Reactor Context hoặc một context propagation mechanism riêng.

Ví dụ dùng key actor do tầng service đưa vào Context:

~~~java
@Component
public class ContextAuditorAware
        implements ReactiveAuditorAware<String> {

    public static final String ACTOR_CONTEXT_KEY = "auditActor";

    @Override
    public Mono<String> getCurrentAuditor() {
        return Mono.deferContextual(context ->
            Mono.justOrEmpty(context.getOrEmpty(ACTOR_CONTEXT_KEY))
                .cast(String.class)
        );
    }
}
~~~

Service gắn actor vào subscription:

~~~java
return repository.save(product)
    .contextWrite(context ->
        context.put(ContextAuditorAware.ACTOR_CONTEXT_KEY, actorId)
    );
~~~

Đây là ví dụ minh họa. Chỉ tầng đã xác thực và xác định actor mới được phép đặt key này. Không nhận actor trực tiếp từ payload không tin cậy.

### 10.2. Luồng batch và system user

Luồng import chạy nền có thể không có người dùng đăng nhập. Ứng dụng có thể truyền một actor hệ thống rõ ràng, ví dụ system:catalog-import.

Không nên tự động gán mọi request không có authentication thành system user. Điều đó có thể khiến request anonymous bị ghi nhận như thao tác nội bộ hợp lệ.

Tách các trường hợp:

- Request người dùng: actor lấy từ authentication.
- Job hệ thống: actor service account được cấu hình rõ.
- Không có actor: trả Mono.empty nếu chính sách cho phép field auditor không có giá trị.
- Trường hợp bắt buộc phải có actor: từ chối hoặc phát error theo contract ứng dụng.

## 11. Bật reactive auditing

Để Spring Data tự điền auditing metadata, bật cấu hình reactive auditing bằng annotation tương ứng với module và phiên bản.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableReactiveElasticsearchAuditing;

@Configuration
@EnableReactiveElasticsearchAuditing
public class ReactiveElasticsearchAuditingConfiguration {
}
~~~

Đăng ký một bean ReactiveAuditorAware duy nhất:

~~~java
@Bean
ReactiveAuditorAware<String> auditorAware() {
    return new SpringSecurityAuditorAware();
}
~~~

Nếu class SpringSecurityAuditorAware đã có @Component thì không cần tạo bean thứ hai cùng kiểu. Hãy tránh đăng ký nhiều auditor bean không phân biệt được vì auditing infrastructure có thể không xác định được bean phù hợp.

Một số phiên bản Spring Data Elasticsearch có tên annotation hoặc cấu hình khác. Kiểm tra API EnableReactiveElasticsearchAuditing trong dependency đang dùng. Không dùng EnableElasticsearchAuditing imperative thay cho reactive annotation nếu phiên bản cung cấp cấu hình reactive riêng.

### 11.1. Những gì annotation kích hoạt

Khi reactive auditing được bật, Spring Data đăng ký auditing infrastructure/callback để:

- Đặt created date khi entity được tạo.
- Đặt last modified date khi entity được ghi hoặc cập nhật.
- Đặt created by nếu auditor có sẵn.
- Đặt last modified by nếu auditor có sẵn.

Auditing hoạt động trong entity lifecycle của Spring Data reactive. Nếu ứng dụng gửi raw JSON qua Elasticsearch Java API Client, REST client hoặc Bulk API trực tiếp, các annotation auditing trên entity không tự chạy.

### 11.2. Không cần gọi auditor thủ công

Không gọi auditorAware.getCurrentAuditor() trong mỗi service rồi tự set createdBy nếu auditing infrastructure đã được bật và entity được lưu qua đúng reactive path.

Để framework quản lý lifecycle giúp tránh việc mỗi service áp dụng quy tắc khác nhau. Nếu cần ghi một actor cụ thể cho job, hãy đưa actor vào Reactor Context hoặc cấu hình execution context trước khi save.

## 12. Khai báo auditing field trên entity

Ví dụ Product:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdAt;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedAt;

    @CreatedBy
    @Field(type = FieldType.Keyword)
    private String createdBy;

    @LastModifiedBy
    @Field(type = FieldType.Keyword)
    private String lastModifiedBy;

    // constructors, getters and setters
}
~~~

Các annotation auditing đến từ Spring Data Commons:

- @CreatedDate: thời điểm tạo.
- @LastModifiedDate: thời điểm sửa gần nhất.
- @CreatedBy: actor tạo.
- @LastModifiedBy: actor sửa gần nhất.

Các field ngày nên dùng kiểu thời gian phù hợp như Instant. Mapping Elasticsearch phải tương thích với field date; actor thường là keyword nếu cần lọc chính xác.

### 12.1. Created và LastModified khác nhau

Ví dụ entity mới được lưu:

~~~text
createdAt       = thời điểm T1
lastModifiedAt  = thời điểm T1 hoặc theo cấu hình modifyOnCreate
createdBy       = alice
lastModifiedBy  = alice
~~~

Khi entity được lưu lại ở thời điểm T2:

~~~text
createdAt       = giữ thời điểm T1
lastModifiedAt  = cập nhật thành T2
createdBy       = giữ alice
lastModifiedBy  = actor hiện tại ở T2
~~~

Auditing metadata mô tả lần tạo và lần sửa gần nhất. Nó không phải lịch sử đầy đủ của mọi lần thay đổi. Nếu cần audit trail, cần event log hoặc một mô hình lưu lịch sử riêng.

### 12.2. modifyOnCreate và setDates

Auditing configuration ở các phiên bản hỗ trợ có thể cho phép điều chỉnh việc set date và cập nhật modified metadata khi tạo mới, thông qua các thuộc tính như setDates hoặc modifyOnCreate.

Không dựa vào default mà chưa kiểm tra version. Nếu API yêu cầu hành vi cụ thể, cấu hình rõ và viết test cho cả insert lẫn update.

### 12.3. Auditor rỗng

Nếu ReactiveAuditorAware trả Mono.empty(), auditing không có actor để gán. Điều đó không nhất thiết làm thao tác save thất bại. Date fields vẫn có thể được xử lý độc lập nếu date auditing được bật.

Nếu business policy yêu cầu mọi document phải có createdBy, hãy kiểm tra actor ở application service hoặc cấu hình auditor bắt buộc. Đừng giả định annotation tự động từ chối save khi không có principal.

## 13. Reactive repository và ReactiveElasticsearchOperations

Reactive repository có thể được khai báo như sau:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Mono<Product> findBySku(String sku);
}
~~~

Ghi entity:

~~~java
Mono<Product> saveResult = productRepository.save(product);
~~~

ReactiveElasticsearchOperations cũng cung cấp API reactive:

~~~java
Mono<Product> saveResult =
    reactiveOperations.save(product);
~~~

Tên method/overload và generic signature phụ thuộc phiên bản. Điểm quan trọng là sử dụng reactive template/repository thay vì gọi imperative Operations rồi bọc kết quả vào Mono.

Để lưu nhiều entity:

~~~java
Flux<Product> saved =
    productRepository.saveAll(products);
~~~

Callback/auditing cần được kiểm tra trên đúng write path mà ứng dụng sử dụng, đặc biệt với bulk operation. Không suy luận rằng mọi API có chữ save hoặc bulk đều chạy callback giống nhau.

## 14. Reactor Context và Spring Security

Trong reactive application, security context được truyền theo subscription. Ví dụ service:

~~~java
public Mono<Product> createProduct(Product product) {
    return productRepository.save(product);
}
~~~

Nếu request đi qua Spring Security WebFlux, authentication context được giữ trong Reactor Context và ReactiveAuditorAware có thể đọc nó.

Không cần truyền username qua từng method argument nếu ứng dụng đã dùng security context đúng cách. Nhưng nếu thao tác được chạy ở scheduler hoặc job độc lập, cần bảo đảm context được truyền theo reactive chain hoặc actor được đặt rõ ràng.

### 14.1. Context không phải ThreadLocal

Một luồng reactive có thể chạy trên nhiều thread. Ví dụ một publisher bắt đầu trên event-loop thread, chuyển scheduler để thực hiện công việc khác, rồi tiếp tục trên thread khác.

ThreadLocal không phải cơ chế đáng tin cậy để truyền actor giữa các bước này. Reactor Context gắn với subscriber và được giữ qua các toán tử reactive theo quy tắc propagation.

Nếu dùng thư viện blocking hoặc custom scheduler, cần hiểu cách context được truyền. Đừng đọc principal trong một callback bằng SecurityContextHolder imperative rồi giả định luôn đúng.

### 14.2. Gắn context đúng phạm vi

Ví dụ:

~~~java
return productRepository.save(product)
    .contextWrite(context ->
        context.put("auditActor", "batch-importer")
    );
~~~

Context chỉ thuộc subscription đó. Không lưu actor vào field của singleton bean, vì nhiều request có thể chạy đồng thời và ghi đè dữ liệu của nhau.

## 15. Reactive auditing và callback tùy chỉnh cùng tồn tại

Một ứng dụng có thể vừa có ReactiveBeforeConvertCallback để chuẩn hóa SKU, vừa bật auditing để ghi created/modified metadata.

Hai cơ chế giải quyết các nhu cầu khác nhau:

- Callback tùy chỉnh thay đổi dữ liệu domain theo quy tắc chuẩn hóa.
- Auditing callback bổ sung metadata về thời gian và actor.

Nếu cả hai cùng sửa entity, thứ tự thực thi có thể quan trọng. Ví dụ callback tùy chỉnh không nên ghi đè createdAt sau khi auditing đã đặt giá trị. Dùng ordering khi cần và kiểm tra trên Spring Data version thực tế.

Không triển khai ReactiveAuditorAware bằng cách tự sửa entity. Auditor provider chỉ trả về actor; auditing infrastructure chịu trách nhiệm đưa actor vào các field auditing.

## 16. Entity immutable và auditing

Với entity immutable, auditing infrastructure cần tạo instance mới hoặc dùng persistent property accessor phù hợp để cập nhật auditing fields.

Ví dụ record có các field auditing:

~~~java
public record Product(
    @Id String id,
    String sku,
    @CreatedDate Instant createdAt,
    @LastModifiedDate Instant lastModifiedAt,
    @CreatedBy String createdBy,
    @LastModifiedBy String lastModifiedBy
) {
}
~~~

Việc hỗ trợ constructor/record và cập nhật auditing field phụ thuộc Spring Data version và mapping metadata. Nếu entity immutable, hãy xác nhận constructor parameter names, persistence creator và auditing property accessor hoạt động đúng.

Integration test nên đọc lại document sau insert/update để kiểm tra auditing metadata thực sự được lưu. Không chỉ kiểm tra record ban đầu trong memory.

## 17. Phân biệt reactive auditing với audit history

Auditing annotations giữ trạng thái hiện tại:

- Ai tạo document?
- Document được tạo lúc nào?
- Ai sửa gần nhất?
- Lần sửa gần nhất diễn ra lúc nào?

Chúng không tự lưu:

- Giá trị cũ và giá trị mới của từng field.
- Lý do thay đổi.
- Toàn bộ danh sách actor đã chỉnh sửa.
- Các sự kiện phê duyệt hoặc chuyển trạng thái.
- Một lịch sử bất biến phục vụ kiểm toán.

Nếu cần lịch sử, có thể lưu domain event/audit event riêng, append vào một index lịch sử hoặc sử dụng hệ thống event store phù hợp. Không ghi đè LastModifiedBy rồi kỳ vọng có thể truy lại mọi người từng sửa.

## 18. Các đường ghi không đi qua reactive callback

Reactive callback chỉ áp dụng cho các thao tác được điều phối qua Spring Data reactive entity callback infrastructure.

| Đường ghi | Reactive callback/auditing |
|---|---|
| ReactiveElasticsearchRepository.save(entity) | Đường reactive entity-oriented phù hợp |
| ReactiveElasticsearchOperations.save(entity) | Đường reactive entity-oriented phù hợp |
| Reactive repository saveAll | Kiểm tra callback coverage trên version/path thực tế |
| Raw Elasticsearch Java API Client | Không đi qua Spring Data callback |
| REST/Bulk API với raw JSON | Không đi qua Spring Data callback |
| Update request bằng raw partial Document | Không nên giả định entity callback được gọi |
| Reindex API trong Elasticsearch | Không chạy Java reactive callback |

Nếu cùng một index được ghi từ cả reactive service và một importer raw JSON, chỉ đặt normalization trong ReactiveBeforeConvertCallback sẽ tạo dữ liệu không đồng nhất. Hãy dùng mapper chung, pipeline ingest hoặc quy ước rõ cho mọi producer.

## 19. Testing reactive callback

Dùng StepVerifier để kiểm tra Publisher thay vì gọi block trong test callback.

~~~java
@Test
void shouldNormalizeProductBeforeConvert() {
    Product product = new Product();
    product.setSku(" sku-1001 ");
    product.setName("  Wireless Mouse  ");

    StepVerifier.create(
        callback.onBeforeConvert(
            product,
            IndexCoordinates.of("products")
        )
    )
    .assertNext(result -> {
        assertThat(result.getSku()).isEqualTo("SKU-1001");
        assertThat(result.getName()).isEqualTo("Wireless Mouse");
    })
    .verifyComplete();
}
~~~

Unit test xác nhận transformation. Nó chưa chứng minh callback được Spring đăng ký hoặc reactive repository save thực sự gọi callback.

### 19.1. Test ReactiveAuditorAware

Có thể test trường hợp không có security context:

~~~java
StepVerifier.create(auditorAware.getCurrentAuditor())
    .verifyComplete();
~~~

Test với authentication trong Reactor Context:

~~~java
Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        "alice",
        "n/a",
        List.of(new SimpleGrantedAuthority("ROLE_USER"))
    );

StepVerifier.create(
    auditorAware.getCurrentAuditor()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(authentication)
        )
)
.expectNext("alice")
.verifyComplete();
~~~

Ví dụ cần dependency Spring Security WebFlux và import tương ứng. Không test bằng SecurityContextHolder imperative vì đó không phải context source của reactive security.

### 19.2. Integration test auditing

Dùng Elasticsearch test instance hoặc Testcontainers, bật reactive auditing trong Spring context và lưu qua đúng reactive repository/template.

~~~java
StepVerifier.create(productRepository.save(product))
    .assertNext(saved -> {
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getLastModifiedAt()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("alice");
    })
    .verifyComplete();
~~~

Sau đó đọc lại document để xác nhận source trong Elasticsearch chứa metadata mong muốn.

Nên kiểm tra:

- Insert đặt created date và created by.
- Update giữ created metadata và cập nhật last modified metadata.
- Không có auditor thì hành vi đúng chính sách.
- Batch job ghi actor hệ thống đã định.
- Callback chuẩn hóa và auditing cùng hoạt động.
- Raw client path không được giả định tự chạy auditing.
- Lỗi trong ReactiveAuditorAware được truyền đúng qua save chain.

### 19.3. Kiểm thử thời gian xác định

Nếu test cần timestamp chính xác, kiểm tra cách phiên bản auditing hỗ trợ cấu hình DateTimeProvider hoặc clock/time provider. Có thể dùng provider cố định trong test thay vì so sánh với thời gian hệ thống có độ chính xác không xác định.

Không thêm sleep để chờ timestamp thay đổi. Dùng provider test hoặc kiểm tra quan hệ thời gian phù hợp.

## 20. Backpressure, concurrency và hiệu năng

Reactive callback chạy trong write pipeline, vì vậy thời gian xử lý callback ảnh hưởng tới tốc độ hoàn tất publisher.

Một số nguyên tắc:

- Giữ transformation CPU nhẹ.
- Tránh I/O không cần thiết.
- Không gọi block.
- Không subscribe thủ công.
- Không lưu request-specific state trong singleton callback.
- Giữ callback stateless khi có thể.
- Đo latency và throughput của save/saveAll.
- Với enrichment bất đồng bộ, đặt timeout và giới hạn concurrency ở tầng phù hợp.
- Không tạo một request dịch vụ ngoài cho mỗi entity trong bulk mà chưa đánh giá tải.

Reactive không làm cho thao tác nặng trở nên miễn phí. Một callback gọi dịch vụ chậm cho từng entity có thể làm cả luồng import chậm và giữ nhiều publisher đang chờ.

## 21. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Reactive callback không chạy | Đăng ký callback imperative hoặc write path không qua reactive mapping | Dùng ReactiveBeforeConvertCallback và đúng reactive template |
| Callback chạy nhưng dữ liệu không đổi | Không trả về instance đã chuẩn hóa | Return Publisher chứa entity mới/đã sửa |
| Mono phát error trước subscription | Dùng Mono.just(normalize()) với phép tính có thể lỗi | Dùng Mono.fromSupplier hoặc Mono.defer |
| Reactive thread bị block | Gọi block, Future.get hoặc I/O đồng bộ | Compose Publisher và dùng API non-blocking |
| Auditor luôn rỗng | Không có security context hoặc context không được truyền | Kiểm tra ReactiveSecurityContextHolder/Reactor Context |
| Auditor đọc sai người dùng | Dùng ThreadLocal/SecurityContextHolder imperative | Dùng ReactiveSecurityContextHolder |
| CreatedBy không được điền | Chưa bật reactive auditing hoặc auditor Mono.empty | Bật annotation đúng và kiểm tra provider |
| LastModifiedDate không đổi | Write path bypass auditing hoặc field mapping sai | Test reactive save path và annotation |
| Auditing chạy ở reactive nhưng không ở raw bulk | Raw client không qua Spring Data callback | Dùng pipeline/mapper hoặc gán metadata trước khi ghi |
| Hai auditor bean gây mơ hồ | Nhiều ReactiveAuditorAware không phân biệt | Đăng ký một bean rõ ràng hoặc cấu hình reference |
| Actor batch thành anonymous | Job không có security context | Đặt system actor có chủ đích trong Reactor Context |
| Callback sửa entity dùng chung | Mutation gây race hoặc side effect | Tạo instance mới hoặc dùng object theo request |
| Auditing ghi đè callback | Ordering hoặc cùng sửa một field | Xác định owner và kiểm thử callback order |
| Record không nhận auditing fields | Constructor/persistent accessor không tương thích | Kiểm tra immutable mapping và version |
| Test không thấy document mới | Chưa refresh hoặc đọc quá sớm qua Search API | Dùng test setup/refresh policy phù hợp |

## 22. Quy trình bật reactive auditing trong ứng dụng

Khi triển khai:

1. Xác nhận ứng dụng đang dùng reactive Spring Data Elasticsearch, không chỉ bọc imperative API trong Mono.
2. Kiểm tra phiên bản Spring Data Elasticsearch và Spring Data Commons.
3. Khai báo field auditing bằng CreatedDate, LastModifiedDate, CreatedBy và LastModifiedBy.
4. Tạo ReactiveAuditorAware<T> trả Mono<T>.
5. Nếu dùng Spring Security WebFlux, đọc principal qua ReactiveSecurityContextHolder.
6. Nếu là batch job, truyền system actor qua context đáng tin cậy.
7. Bật reactive auditing bằng annotation cấu hình đúng version.
8. Đăng ký callback reactive tùy chỉnh nếu cần chuẩn hóa entity trước convert.
9. Kiểm tra ordering khi callback tùy chỉnh và auditing cùng thay đổi entity.
10. Dùng reactive repository hoặc ReactiveElasticsearchOperations.
11. Kiểm tra raw client/bulk paths có bypass callback hay không.
12. Viết unit test bằng StepVerifier và integration test với Elasticsearch.
13. Theo dõi lỗi và latency của write pipeline.

Không dùng reactive auditing để thay thế audit history hoặc business authorization. Nó chỉ ghi metadata tạo/sửa trên entity trong các đường persistence được hỗ trợ.

## 23. Bảng tra cứu nhanh

| Nhu cầu | Thành phần |
|---|---|
| Chuẩn hóa entity trước khi convert trong reactive flow | ReactiveBeforeConvertCallback<T> |
| Trả entity từ callback reactive | Publisher<T>, thường là Mono<T> |
| Chuẩn hóa đồng bộ nhưng defer tới subscription | Mono.fromSupplier |
| Lấy actor hiện tại trong reactive flow | ReactiveAuditorAware<T> |
| Lấy principal Spring Security WebFlux | ReactiveSecurityContextHolder |
| Đọc actor từ Reactor Context riêng | Mono.deferContextual |
| Ghi thời điểm tạo | @CreatedDate |
| Ghi thời điểm sửa | @LastModifiedDate |
| Ghi người tạo | @CreatedBy |
| Ghi người sửa gần nhất | @LastModifiedBy |
| Bật reactive auditing | @EnableReactiveElasticsearchAuditing nếu version hỗ trợ |
| Lưu qua reactive repository | ReactiveElasticsearchRepository |
| Lưu qua reactive template | ReactiveElasticsearchOperations |
| Kiểm thử publisher | StepVerifier |
| Ghi lịch sử đầy đủ | Domain audit event/history riêng |
| Ghi qua raw client | Chuẩn hóa/auditing ở application hoặc ingest pipeline |

Reactive callback và reactive auditing giúp đưa chuẩn hóa entity cùng metadata tạo/sửa vào đúng lifecycle của Spring Data Elasticsearch. ReactiveBeforeConvertCallback trả Publisher để Spring Data ghép transformation vào write chain; ReactiveAuditorAware trả Mono chứa actor lấy từ Reactor Context hoặc Spring Security reactive context; cấu hình reactive auditing kích hoạt việc điền các field auditing. Hãy tránh block/subscribe thủ công, giữ callback nhẹ và idempotent, phân biệt metadata lần sửa gần nhất với audit history, và kiểm thử đúng reactive repository/template path mà ứng dụng sử dụng.

