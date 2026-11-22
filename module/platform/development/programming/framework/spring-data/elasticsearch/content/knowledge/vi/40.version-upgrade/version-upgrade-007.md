# Nâng cấp reactive client, auditing và callback

Khi nâng cấp Spring Data Elasticsearch, thay đổi không chỉ nằm ở dependency hoặc cách khởi tạo client. Một ứng dụng dùng reactive stack còn phải kiểm tra loại client, reactive operations, repository configuration, callback lifecycle và cách lấy auditor hiện tại. Nếu chỉ chuyển code truy vấn sang reactive mà vẫn giữ auditing hoặc callback đồng bộ, metadata có thể không được ghi, callback có thể không chạy hoặc request bị block ngoài ý muốn.

Nên thực hiện nâng cấp theo ba lớp:

1. **Client và API:** chọn đúng phiên bản Spring Data Elasticsearch, Elasticsearch server/client library và cấu hình imperative/reactive.
2. **Auditing:** bật đúng auditing infrastructure, xác định entity mới/cũ và lấy principal từ reactive context.
3. **Entity callbacks:** chuyển callback sang reactive interface, bảo đảm callback trả Publisher, giữ đúng thứ tự và không thực hiện blocking work.

## 1. Hiểu các thành phần trong reactive stack

Spring Data Elasticsearch cung cấp abstraction để ứng dụng không phải gọi trực tiếp HTTP client cho mọi thao tác.

~~~text
Reactive application
       |
       v
Reactive repository / service
       |
       v
ReactiveElasticsearchOperations
       |
       v
ReactiveElasticsearchClient
       |
       v
Elasticsearch client transport
       |
       v
Elasticsearch cluster
~~~

Các thành phần có vai trò khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| ReactiveElasticsearchClient | Client reactive cấp thấp dùng để gửi request đến Elasticsearch |
| ReactiveElasticsearchOperations | API template cấp cao cho save, search, delete, index operations |
| ReactiveElasticsearchRepository | Repository abstraction trả về Mono/Flux |
| ReactiveElasticsearchAuditing | Ghi metadata tạo/sửa theo reactive lifecycle |
| ReactiveAuditorAware | Cung cấp principal hiện tại dưới dạng Mono |
| Reactive EntityCallback | Hook reactive trước/sau các bước xử lý entity |

Ứng dụng thường nên dùng ReactiveElasticsearchOperations hoặc ReactiveElasticsearchRepository. Chỉ dùng client cấp thấp khi cần một API Elasticsearch mà abstraction của Spring Data không expose.

### 1.1. Reactive không chỉ là đổi kiểu trả về

Một method trả về Mono hoặc Flux không tự động làm toàn bộ pipeline non-blocking. Các thao tác bên trong cũng phải tuân theo reactive execution:

- Không gọi block() trong service hoặc callback.
- Không dùng ThreadLocal để đọc security context của reactive request.
- Không thực hiện I/O blocking trực tiếp trong callback.
- Không tạo Publisher rồi bỏ qua, vì Publisher thường chỉ chạy khi được subscribe.
- Không chạy side effect ở thời điểm assembly nếu nó cần xảy ra theo từng subscription.
- Cân nhắc backpressure, concurrency và timeout khi xử lý nhiều document.

Ví dụ:

~~~java
public Mono<Product> save(Product product) {
    return operations.save(product);
}
~~~

Đây là một reactive pipeline. Elasticsearch operation chỉ được thực thi khi Publisher được subscribe bởi WebFlux, một consumer hoặc một thành phần reactive khác.

## 2. Lập bản đồ tương thích trước khi nâng cấp

Trước khi sửa code, xác định chính xác:

- Spring Boot version.
- Spring Data Elasticsearch version được dependency management chọn.
- Spring Data Commons version.
- Elasticsearch server version.
- Elasticsearch Java API Client hoặc RestClient version.
- Java runtime.
- Imperative hay reactive client configuration.
- Các package cũ đang được import.

Không nâng riêng một dependency Elasticsearch client lên phiên bản mới nhất nếu Spring Data release train chưa hỗ trợ. Spring Boot dependency management thường chọn một bộ phiên bản đã được kiểm tra tương thích.

### 2.1. Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch
mvn dependency:tree -Dincludes=co.elastic.clients
mvn dependency:tree -Dincludes=org.elasticsearch.client
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch
./gradlew dependencyInsight --dependency elasticsearch-java
./gradlew dependencyInsight --dependency elasticsearch-rest-client
~~~

Mục tiêu là biết dependency thực tế được resolve, không chỉ biết version khai báo trong build file.

### 2.2. Không trộn client generation

Trong quá trình chuyển đổi có thể tồn tại:

- RestHighLevelClient cũ.
- RestClient của Elasticsearch 7/8 client stack.
- Elasticsearch Java API Client.
- Rest5Client trong Elasticsearch 9 client stack.
- ReactiveElasticsearchClient do Spring Data cung cấp.

Các loại này không thể thay thế lẫn nhau chỉ bằng cách đổi tên bean. Cấu hình Spring Data, transport, request/response classes và converter phải thuộc đúng client generation.

### 2.3. Các mốc nâng cấp thường gặp

| Nâng cấp | Thay đổi cần chú ý |
| --- | --- |
| Spring Data Elasticsearch 4.4 lên 5.0 | Client mới dựa trên Elasticsearch Java API Client; package dùng RestHighLevelClient bị deprecated; NativeSearchQuery chuyển sang NativeQuery |
| 5.x | Reactive stack có ReactiveElasticsearchConfiguration và ReactiveElasticsearchClient; tiếp tục kiểm tra API/client theo minor version |
| 5.5 lên 6.0 | Dùng Elasticsearch 9 libraries và Rest5Client làm mặc định; RestClient cũ được chuyển vào package legacy và deprecated |
| 6.x | Dùng cấu hình Rest5Client mặc định; nếu duy trì RestClient cũ cần cấu hình legacy được hỗ trợ cho phiên bản đó |

Các mốc trên là hướng dẫn định vị breaking changes. Hãy dùng migration guide khớp đúng phiên bản nguồn và đích; không giả định một thay đổi trong 6.0 áp dụng giống hệt cho mọi minor release sau đó.

## 3. Nâng cấp reactive client từ RestHighLevelClient

Spring Data Elasticsearch 5.0 đã tách rõ code dùng client cũ và code dùng Elasticsearch Java API Client. Các lớp phụ thuộc RestHighLevelClient được chuyển vào package erhlc và deprecated. Reactive implementation cũ cũng được chuyển vào khu vực này vì nó chứa phần code dựa trên thư viện Elasticsearch cũ.

Nếu ứng dụng còn dùng các import từ:

~~~java
org.springframework.data.elasticsearch.client.erhlc
~~~

hãy xác định từng class đang dùng và thay bằng API mới tương ứng. Không đổi package hàng loạt mà không xem constructor, request model và response model.

### 3.1. Reactive configuration với client generation mới

Reactive stack dùng configuration class riêng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;

@Configuration
public class ReactiveSearchConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .build();
    }
}
~~~

Trong cấu hình này, Spring Data tạo các bean reactive cần thiết, bao gồm ReactiveElasticsearchClient và ReactiveElasticsearchOperations. Tên bean mặc định và các chi tiết cấu hình phụ thuộc version.

Không dùng ElasticsearchConfiguration cho reactive repositories nếu ứng dụng cần ReactiveElasticsearchOperations. Cấu hình imperative và reactive là hai nhánh riêng.

### 3.2. Cấu hình TLS, timeout và authentication

ClientConfiguration hỗ trợ các thiết lập kết nối như:

- Một hoặc nhiều endpoint.
- SSL/TLS.
- Connect timeout.
- Socket timeout.
- Proxy.
- Path prefix.
- HTTP headers.
- Basic authentication.
- Client configuration callbacks.

Ví dụ cấu hình:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;

@Configuration
class ReactiveSearchConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("es.internal.example:9200")
            .usingSsl()
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(10))
            .withBasicAuth(
                System.getenv("ES_USERNAME"),
                System.getenv("ES_PASSWORD")
            )
            .build();
    }
}
~~~

Đây là ví dụ cấu hình. Cách cung cấp certificate, trust material, credential và endpoint phải theo môi trường triển khai. Không hard-code secret vào source code hoặc test fixture.

### 3.3. Reactive header supplier không được blocking

ClientConfiguration có thể nhận một supplier tạo HTTP headers cho từng request, hữu ích khi token thay đổi theo thời gian.

Trong reactive setup, supplier này phải trả kết quả mà không thực hiện blocking I/O. Không gọi synchronous token service hoặc chờ network response trong supplier.

Nếu cần lấy token từ reactive security context, hãy thiết kế authentication/header propagation theo khả năng của client configuration hiện tại. Không đọc ThreadLocal trong callback rồi giả định nó đại diện cho request reactive đang xử lý.

## 4. Lưu ý khi nâng từ Spring Data Elasticsearch 5.x lên 6.x

Spring Data Elasticsearch 6.0 chuyển sang Elasticsearch 9 libraries và Rest5Client làm client mặc định. Code dùng RestClient cũ vẫn có thể được hỗ trợ qua cấu hình legacy trong phạm vi version tương ứng, nhưng các API đó đã được deprecated.

Các điểm cần rà soát:

| Khu vực | Thay đổi |
| --- | --- |
| Client mặc định | Rest5Client |
| Cấu hình client cũ | Chuyển sang package legacy và deprecated |
| Client config callbacks cũ | Chuyển từ ElasticsearchClients sang package rest_client tương ứng |
| UpdateQuery | ifSeqNo và ifPrimaryTerm đổi từ Integer sang Long |
| ScriptType | Đã bị loại bỏ; dùng ScriptData để mô tả script |
| Reactive client | Dùng ReactiveElasticsearchConfiguration theo client generation mới |

### 4.1. Kiểm tra UpdateQuery

Code cũ có thể dùng Integer cho sequence number và primary term:

~~~java
UpdateQuery.builder(id)
    .withIfSeqNo(seqNo)
    .withIfPrimaryTerm(primaryTerm)
    .build();
~~~

Ở API mới, các giá trị tương ứng dùng Long để phù hợp kiểu của Elasticsearch client:

~~~java
Long seqNo = response.seqNo();
Long primaryTerm = response.primaryTerm();

UpdateQuery update = UpdateQuery.builder(id)
    .withIfSeqNo(seqNo)
    .withIfPrimaryTerm(primaryTerm)
    .build();
~~~

Đoạn code cần đối chiếu method và kiểu trả về của client version đang dùng. Không ép kiểu về Integer vì có thể làm mất dữ liệu hoặc không compile.

### 4.2. Thay ScriptType bằng ScriptData

Nếu code cũ phân biệt inline và stored script bằng ScriptType, chuyển sang cách tạo ScriptData theo API mới.

Ví dụ khái niệm:

~~~java
ScriptData scriptData = ScriptData.builder()
    .withScript("ctx._source.status = params.status")
    .withParams(Map.of("status", "ACTIVE"))
    .build();
~~~

Đây là minh họa ý tưởng; constructor/builder methods phụ thuộc version. Đọc Javadoc của ScriptData và migration guide trước khi sửa các script đang chạy production.

### 4.3. Client configuration callback

Trong 6.0, cấu hình callback cho RestClient cũ được chuyển sang package rest_client. Nếu ứng dụng đang custom low-level RestClient, không giữ import từ package cũ khi chuyển sang Rest5Client.

Phân biệt:

- Cấu hình client mặc định Rest5Client.
- Cấu hình legacy RestClient.
- ReactiveElasticsearchConfiguration.
- ReactiveElasticsearchLegacyRestClientConfiguration nếu phải duy trì client legacy.

Không trộn callback cấu hình của RestClient legacy với Rest5Client.

## 5. Chuyển query API và các package liên quan

Nâng client thường kéo theo thay đổi query classes và import.

### 5.1. NativeSearchQuery sang NativeQuery

Trong nhánh chuyển từ 4.4 lên 5.0, NativeSearchQuery cũ được thay bằng NativeQuery sử dụng Query model của Elasticsearch Java API Client.

Ví dụ:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("name")
            .query("wireless keyboard")
        )
    )
    .build();
~~~

Nếu ứng dụng có query factory lớn, chuyển từng query family và kiểm tra JSON DSL được gửi đi. Không chỉ sửa import rồi giả định semantics giống nhau.

### 5.2. Operations interface

Ưu tiên phụ thuộc vào interface:

~~~java
ReactiveElasticsearchOperations
~~~

thay vì phụ thuộc trực tiếp vào implementation template nếu không có nhu cầu đặc biệt.

Điều này giúp giảm coupling với client generation và cho phép Spring Data quản lý implementation phù hợp.

### 5.3. HttpHeaders package

Spring Data Elasticsearch 5.0 giới thiệu HttpHeaders riêng trong package:

~~~java
org.springframework.data.elasticsearch.support.HttpHeaders
~~~

Nếu client configuration cũ dùng org.springframework.http.HttpHeaders, hãy chuyển import theo migration guide. Có thể cần copy headers qua addAll thay vì truyền trực tiếp object cũ.

### 5.4. Java records và accessor

Một số kiểu dữ liệu trong Spring Data Elasticsearch được chuyển thành Java record. Code gọi getter kiểu getProp() có thể phải đổi sang accessor prop().

Không sửa mọi getter trong codebase một cách máy móc. Chỉ thay đổi các kiểu cụ thể đã được chuyển thành record trong migration guide của phiên bản đang dùng.

## 6. Dùng ReactiveElasticsearchOperations và repository

ReactiveElasticsearchOperations cung cấp API trả về Publisher như Mono và Flux. Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ProductService {

    private final ReactiveElasticsearchOperations operations;

    ProductService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    Mono<Product> save(Product product) {
        return operations.save(product);
    }
}
~~~

Reactive repository:

~~~java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByBrandId(String brandId);
}
~~~

Tên method query derivation phải tuân theo field và mapping của entity. Không gọi repository reactive bằng cách block trong controller WebFlux.

### 6.1. Reactive search

~~~java
Mono<List<SearchHit<Product>>> searchProducts(Query query) {
    return operations.search(query, Product.class)
        .collectList();
}
~~~

Kiểu trả về cụ thể của search method phụ thuộc overload và Spring Data version. Có thể nhận Flux<SearchHit<T>>, Flux<SearchHits<T>> hoặc kiểu tương ứng của API. Kiểm tra method signature của dependency trước khi áp dụng.

### 6.2. Compose thao tác

~~~java
Mono<Product> createAndRead(Product product) {
    return operations.save(product)
        .flatMap(saved -> operations.get(saved.getId(), Product.class));
}
~~~

flatMap phù hợp khi thao tác tiếp theo cũng trả về Publisher. map dùng cho phép biến đổi đồng bộ, không tạo một Publisher mới.

### 6.3. Không subscribe thủ công trong service

Tránh:

~~~java
public void save(Product product) {
    operations.save(product).subscribe();
}
~~~

Code này tách side effect khỏi request lifecycle, làm caller không biết khi nào ghi xong và khó xử lý lỗi.

Hãy trả Publisher cho caller:

~~~java
public Mono<Product> save(Product product) {
    return operations.save(product);
}
~~~

Caller ở tầng web hoặc message consumer quyết định subscription và acknowledgement.

## 7. Auditing trong Spring Data Elasticsearch

Auditing tự động ghi thông tin ai tạo/cập nhật document và thời điểm tạo/cập nhật.

Các annotation phổ biến:

| Annotation | Ý nghĩa |
| --- | --- |
| @CreatedDate | Thời điểm tạo |
| @LastModifiedDate | Thời điểm cập nhật gần nhất |
| @CreatedBy | Principal tạo |
| @LastModifiedBy | Principal cập nhật gần nhất |

Auditing hữu ích cho:

- Theo dõi lịch sử thay đổi ở mức metadata.
- Hiển thị thông tin người tạo/người sửa.
- Phân tích dữ liệu cũ.
- Hỗ trợ audit trail cơ bản.
- Tạo bộ lọc dữ liệu theo thời điểm hoặc người thao tác.

Auditing metadata trong entity không tự tạo một audit log bất biến. Nếu nghiệp vụ cần lưu mọi thay đổi, cần event log hoặc audit index riêng.

## 8. Chuẩn bị entity có audit fields

Ví dụ:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    @CreatedDate
    @Field(type = FieldType.Date, format = DateFormat.basic_date_time)
    private Instant createdDate;

    @LastModifiedDate
    @Field(type = FieldType.Date, format = DateFormat.basic_date_time)
    private Instant lastModifiedDate;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    // Constructors, getters and setters
}
~~~

Có thể chỉ dùng date fields nếu ứng dụng không cần lưu principal. Khi dùng CreatedBy hoặc LastModifiedBy, cần cung cấp AuditorAware hoặc ReactiveAuditorAware phù hợp.

### 8.1. Kiểu dữ liệu thời gian

Auditing hỗ trợ các kiểu date/time của JDK, long/Long và các kiểu Date/Calendar cũ theo Spring Data auditing infrastructure.

Instant thường phù hợp cho thời điểm tuyệt đối:

- Không gắn với timezone địa phương.
- Dễ trao đổi giữa service.
- Có thể serialize theo ISO-8601.
- Phù hợp lưu event time và audit time.

Mapping Elasticsearch phải được khai báo tương ứng. Nếu dùng format custom, đảm bảo converter, mapping và dữ liệu cũ thống nhất.

### 8.2. CreatedDate không tự chứng minh entity là mới

Trong Elasticsearch, một entity có ID không nhất thiết là entity đã tồn tại. Ứng dụng có thể cấp ID trước khi insert. Vì vậy, chỉ kiểm tra ID null không luôn xác định đúng entity mới/cũ.

Auditing cần biết entity có phải new để quyết định giữ CreatedDate hay cập nhật LastModifiedDate.

Spring Data Elasticsearch documentation hướng dẫn dùng Persistable<ID> để cung cấp isNew() khi cần kiểm soát trạng thái mới/cũ.

Ví dụ:

~~~java
@Document(indexName = "products")
public class Product implements Persistable<String> {

    @Id
    private String id;

    @CreatedDate
    private Instant createdDate;

    @CreatedBy
    private String createdBy;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return id == null || (createdDate == null && createdBy == null);
    }
}
~~~

Đây là một chiến lược minh họa. isNew() phải phản ánh chính xác vòng đời entity của ứng dụng. Nếu entity được tạo từ import hoặc có thể thiếu audit metadata, hãy dùng trạng thái/version rõ ràng hơn thay vì suy luận từ một field tùy ý.

## 9. Bật auditing cho imperative và reactive stack

Hai stack dùng annotation kích hoạt riêng.

### 9.1. Imperative auditing

~~~java
@Configuration
@EnableElasticsearchAuditing
class ElasticsearchAuditingConfiguration {
}
~~~

### 9.2. Reactive auditing

~~~java
@Configuration
@EnableReactiveElasticsearchAuditing
class ReactiveElasticsearchAuditingConfiguration {
}
~~~

Nếu ứng dụng dùng reactive repositories, cấu hình repositories tương ứng cũng phải là:

~~~java
@EnableReactiveElasticsearchRepositories(
    basePackages = "com.example.search.repository"
)
~~~

Không bật imperative auditing rồi giả định nó sẽ xử lý reactive entity callbacks. Reactive stack có ReactiveAuditingEntityCallback và ReactiveIsNewAwareAuditingHandler riêng.

### 9.3. Chỉ cần audit date thì không cần AuditorAware

Nếu entity chỉ có CreatedDate và LastModifiedDate, auditing không cần biết principal. Khi đó có thể bật reactive auditing mà không cung cấp ReactiveAuditorAware.

Nếu dùng CreatedBy hoặc LastModifiedBy, phải cung cấp auditor provider với generic type tương thích field.

### 9.4. Chọn đúng bean bằng auditorAwareRef

Nếu application có nhiều AuditorAware/ReactiveAuditorAware bean, hãy chỉ rõ bean name qua auditorAwareRef của annotation kích hoạt auditing.

Ví dụ:

~~~java
@Configuration
@EnableReactiveElasticsearchAuditing(
    auditorAwareRef = "reactiveAuditorAware"
)
class ReactiveAuditingConfiguration {
}
~~~

Không để Spring chọn nhầm auditor provider có kiểu trả về hoặc nguồn principal không phù hợp.

## 10. ReactiveAuditorAware và Spring Security

Trong reactive application, SecurityContext thường được truyền qua Reactor Context. Không nên dùng SecurityContextHolder theo kiểu ThreadLocal trong ReactiveAuditorAware vì request có thể đổi thread trong quá trình xử lý.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

@Configuration
class AuditorConfiguration {

    @Bean
    ReactiveAuditorAware<String> reactiveAuditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
~~~

ReactiveAuditorAware trả về Mono chứa auditor hiện tại hoặc Mono.empty() nếu không có auditor.

Nếu Authentication principal là custom UserDetails, có thể map sang user ID ổn định thay vì lưu display name.

### 10.1. Dùng ID thay vì tên hiển thị

createdBy và lastModifiedBy thường nên lưu một định danh ổn định:

- User ID.
- Service account ID.
- Tenant-scoped principal ID.
- System actor như batch-importer.

Tên hiển thị có thể thay đổi theo thời gian, gây khó khăn khi truy vấn lịch sử.

### 10.2. Background job và system actor

Một batch job không có security context người dùng. ReactiveAuditorAware có thể trả về system actor:

~~~java
return () -> ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .filter(Authentication::isAuthenticated)
    .map(Authentication::getName)
    .switchIfEmpty(Mono.just("system:catalog-import"));
~~~

Chỉ dùng fallback này khi nghiệp vụ cho phép. Nếu auditor là bắt buộc, có thể trả Mono.empty() hoặc phát lỗi theo policy để không ghi dữ liệu thiếu actor.

### 10.3. Không lấy principal ở thời điểm assembly

Không đọc SecurityContext trong constructor hoặc lúc tạo callback bean rồi lưu vào field. Principal thay đổi theo subscription/request.

Hãy truy xuất context bên trong publisher được trả về từ ReactiveAuditorAware.

## 11. DateTimeProvider và clock

Auditing mặc định dùng CurrentDateTimeProvider để lấy thời điểm hiện tại. Có thể thay bằng DateTimeProvider nếu cần:

- Dùng clock thống nhất.
- Kiểm thử thời gian xác định.
- Dùng một nguồn thời gian của hệ thống.
- Áp dụng policy UTC.

Ví dụ:

~~~java
@Bean
DateTimeProvider dateTimeProvider(Clock clock) {
    return () -> Optional.of(Instant.now(clock));
}

@Bean
Clock auditClock() {
    return Clock.systemUTC();
}
~~~

Sau đó tham chiếu bean:

~~~java
@EnableReactiveElasticsearchAuditing(
    dateTimeProviderRef = "dateTimeProvider"
)
~~~

Nếu hệ thống cần thời điểm do nguồn nghiệp vụ cấp, không ghi đè tùy tiện bằng clock local. Phân biệt occurredAt từ event và auditedAt do projector/service cập nhật.

## 12. Entity callbacks trong Spring Data Elasticsearch

Entity callbacks là các hook được gọi tại những điểm xác định trong lifecycle xử lý entity. Callback có thể trả entity ban đầu hoặc một instance đã được sửa đổi.

Callback phù hợp với:

- Chuẩn hóa field trước khi convert.
- Tạo slug hoặc normalized value.
- Bổ sung metadata kỹ thuật.
- Ghi dấu trạng thái hoặc tenant context.
- Chuẩn hóa dữ liệu sau khi load/convert.
- Thực hiện hành vi sau khi save.

Spring Data khuyến nghị EntityCallback API cho các thay đổi entity ở lifecycle. Application events vẫn có thể được phát trước callback, nhưng callback cho phép thực thi theo thứ tự xác định hơn.

### 12.1. Imperative và reactive callback là hai interface khác nhau

Reactive implementation chỉ gọi reactive callback tương ứng; imperative implementation chỉ gọi callback đồng bộ.

| Imperative | Reactive |
| --- | --- |
| BeforeConvertCallback | ReactiveBeforeConvertCallback |
| AfterLoadCallback | ReactiveAfterLoadCallback |
| AfterConvertCallback | ReactiveAfterConvertCallback |
| AfterSaveCallback | ReactiveAfterSaveCallback |

Không cài BeforeConvertCallback đồng bộ rồi mong ReactiveElasticsearchOperations tự gọi nó. Khi chuyển service sang reactive stack, phải chuyển callback bean sang interface reactive tương ứng.

### 12.2. Callback của Spring Data Elasticsearch

Các callback được Spring Data Elasticsearch sử dụng trong entity lifecycle gồm:

| Callback | Thời điểm | Mục đích |
| --- | --- | --- |
| BeforeConvertCallback / ReactiveBeforeConvertCallback | Trước khi entity được convert thành Document | Sửa entity trước khi ghi |
| AfterLoadCallback / ReactiveAfterLoadCallback | Sau khi Document được đọc từ Elasticsearch, trước khi convert thành entity | Xử lý raw Document |
| AfterConvertCallback / ReactiveAfterConvertCallback | Sau khi Document được convert thành entity | Bổ sung hoặc chuẩn hóa entity đã đọc |
| AuditingEntityCallback / ReactiveAuditingEntityCallback | Trước convert | Điền created/modified metadata |
| AfterSaveCallback / ReactiveAfterSaveCallback | Sau khi lưu | Xử lý entity đã được lưu |

Danh sách callback và method signature phải kiểm tra theo phiên bản Spring Data Elasticsearch cụ thể. Không suy luận rằng mọi callback interface của Spring Data Commons đều được mọi store module triển khai.

## 13. Viết ReactiveBeforeConvertCallback

Ví dụ tạo slug trước khi lưu:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
class ProductSlugCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Mono<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        if (product.getSlug() != null && !product.getSlug().isBlank()) {
            return Mono.just(product);
        }

        product.setSlug(toSlug(product.getName()));
        return Mono.just(product);
    }

    private String toSlug(String value) {
        return value.toLowerCase()
            .trim()
            .replaceAll("[^a-z0-9]+", "-");
    }
}
~~~

Đây là ví dụ dùng entity mutable. Với immutable entity/record, tạo và trả instance mới thay vì mutate object.

Callback được gọi trong reactive pipeline. Nó không thực thi ngay khi bean được tạo; logic chạy khi operation được subscribe.

### 13.1. Trả entity đã thay đổi

Callback phải trả về entity được dùng cho bước convert tiếp theo. Nếu tạo instance mới nhưng vẫn trả entity cũ, thay đổi sẽ bị mất.

### 13.2. Không thực hiện blocking I/O

Không gọi JDBC blocking, synchronous HTTP client hoặc block() trong callback. Nếu cần dữ liệu từ một service khác, compose Publisher và trả về Mono/Flux tương ứng.

Tuy nhiên, callback thường nên làm biến đổi cục bộ, xác định và nhanh. Đưa nghiệp vụ cần nhiều nguồn dữ liệu vào service layer trước thao tác save sẽ dễ quan sát và kiểm thử hơn.

## 14. Viết ReactiveAfterSaveCallback

Callback sau save có thể phát event nội bộ hoặc bổ sung thông tin cho luồng tiếp theo:

~~~java
import org.springframework.data.elasticsearch.core.event.ReactiveAfterSaveCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
class ProductAfterSaveCallback
        implements ReactiveAfterSaveCallback<Product> {

    @Override
    public Mono<Product> onAfterSave(
            Product product,
            IndexCoordinates index) {

        return Mono.just(product);
    }
}
~~~

Không nên gửi email hoặc gọi hệ thống bên ngoài trực tiếp trong callback nếu side effect đó cần bảo đảm giao nhận. Elasticsearch save có thể thành công nhưng downstream side effect thất bại, hoặc callback có thể được thực thi lại theo retry của pipeline.

Nếu cần phát event bền vững, dùng transactional outbox ở nguồn dữ liệu phù hợp hoặc một workflow có retry/deduplication rõ ràng. Elasticsearch callback không tạo transaction phân tán.

## 15. Thứ tự callback và auditing

Spring Data đăng ký auditing bằng một entity callback nội bộ. Trong Spring Data Elasticsearch hiện hành, AuditingEntityCallback và ReactiveAuditingEntityCallback có order 100. Các callback store-specific như BeforeConvertCallback mặc định có LOWEST_PRECEDENCE.

Điều này có ý nghĩa khi ứng dụng tự đăng ký callback khác:

- Callback có order nhỏ hơn được chạy trước callback có order lớn hơn.
- Auditing callback có thể chạy trước callback custom mặc định.
- Callback custom chạy sau auditing có thể vô tình ghi đè CreatedDate hoặc LastModifiedDate.
- Nếu nhiều callback sửa cùng field, kết quả phụ thuộc order.

### 15.1. Đặt order có chủ đích

Có thể dùng @Order hoặc implement Ordered:

~~~java
@Component
@Order(200)
class ProductMetadataCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Mono<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {
        return Mono.just(product);
    }
}
~~~

Order 200 là ví dụ. Chọn giá trị dựa trên callback nào cần chạy trước và không ghi đè audit metadata. Đừng dựa vào thứ tự ngẫu nhiên giữa các bean không khai báo order.

### 15.2. Giữ CreatedDate không bị ghi đè

Một callback chuẩn hóa entity không nên reset CreatedDate mỗi lần save. CreatedDate chỉ được gán khi entity được nhận diện là new; LastModifiedDate được cập nhật khi sửa.

Nếu custom callback thay đổi audit field, hãy xác định rõ policy và test cả create/update.

### 15.3. Callback order phải được kiểm thử

Khi có nhiều callback, kiểm tra:

- Thứ tự thực tế theo order.
- Callback có nhận entity đã được auditing hay chưa.
- Callback có trả instance mới không.
- Field nào bị thay đổi.
- Reactive pipeline có chạy callback khi subscribe.

Không suy luận thứ tự từ thứ tự khai báo @Bean trong configuration.

## 16. Application events và EntityCallback

Spring Data Elasticsearch có các store-specific ApplicationEvents như BeforeConvertEvent hoặc AfterSaveEvent trong các phiên bản hỗ trợ.

EntityCallback là lựa chọn phù hợp hơn khi cần sửa entity tại lifecycle checkpoint vì:

- Callback trả entity đã được sửa đổi.
- Reactive callback trả Publisher.
- Thứ tự được điều khiển qua Ordered.
- Callback được gọi theo lifecycle của template.
- Tránh một số bất định khi ApplicationEventMulticaster chạy bất đồng bộ.

Application event vẫn hữu ích cho quan sát hoặc tích hợp event listener, nhưng không nên thay callback bằng listener async nếu logic cần hoàn tất trước khi document được convert hoặc lưu.

### 16.1. Đừng trộn listener đồng bộ và callback reactive

Một listener đồng bộ không trở thành reactive chỉ vì nó được gọi trong reactive application. Nếu cần sửa entity trước khi ghi, dùng ReactiveBeforeConvertCallback.

### 16.2. Event listener không thay thế outbox

Event listener trong process có thể không chạy nếu JVM dừng hoặc process lỗi sau khi ghi. Nếu side effect cần bền vững, phải dùng durable messaging/outbox.

## 17. Nâng cấp callback cũ

Khi chuyển từ phiên bản cũ, kiểm tra:

- Các class kế thừa AbstractElasticsearchEventListener.
- Các listener nhận BeforeConvertEvent/AfterSaveEvent.
- Callback đồng bộ implement BeforeConvertCallback.
- Callback dùng implementation template cụ thể.
- Logic audit được viết thủ công trong listener.
- Listener phụ thuộc ApplicationEventMulticaster.

Chọn cách chuyển:

| Logic cũ | Hướng chuyển |
| --- | --- |
| Sửa entity trước khi convert | ReactiveBeforeConvertCallback |
| Xử lý Document sau khi load | ReactiveAfterLoadCallback |
| Sửa entity sau khi convert | ReactiveAfterConvertCallback |
| Xử lý sau save | ReactiveAfterSaveCallback |
| Ghi created/modified fields | Reactive Elasticsearch auditing |
| Side effect cần bền vững | Outbox/message workflow |

Không chuyển tất cả listener sang callback một cách máy móc. Một số listener chỉ quan sát sự kiện, không cần thay đổi entity.

## 18. Những thao tác có thể không đi qua entity callbacks

Entity callbacks gắn với lifecycle mà Spring Data template/repository thực hiện. Nếu ứng dụng bỏ qua template và gọi Elasticsearch Java API Client trực tiếp, không nên giả định Spring Data auditing hoặc callback sẽ được chạy.

Các trường hợp cần kiểm tra riêng:

- Gọi trực tiếp ElasticsearchClient.
- Bulk request ở cấp client.
- Update script trực tiếp.
- Delete-by-query.
- Reindex API.
- Ingest pipeline.
- Job đồng bộ dữ liệu ngoài Spring Data.

Nếu thao tác không đi qua entity lifecycle, ứng dụng phải tự điền audit fields hoặc dùng cơ chế ở tầng ingest/nguồn dữ liệu phù hợp.

Đặc biệt, partial update bằng script có thể chỉ thay đổi một số field và không tạo entity hoàn chỉnh. Không thể giả định @LastModifiedDate sẽ tự cập nhật nếu operation không kích hoạt auditing callback.

## 19. Auditing và immutable entity

Với entity mutable, auditing có thể gán field qua setter hoặc field access.

Với immutable object hoặc Java record, auditing infrastructure cần tạo instance mới thông qua persistent entity metadata và constructor/property access phù hợp.

Khi dùng immutable entity:

- Đảm bảo audit fields nằm trong constructor/property model.
- Đảm bảo mapping metadata nhận diện được field.
- Không tạo callback trả lại instance cũ sau khi auditing đã tạo instance mới.
- Kiểm tra constructor parameter names và nullability.
- Test cả insert và update.

Nếu callback custom cần sửa immutable entity, dùng factory/wither hoặc constructor để tạo instance mới.

## 20. Vấn đề entity mới/cũ khi có ID được cấp trước

Elasticsearch cho phép document ID được ứng dụng tạo trước khi index. Vì vậy, entity có ID không đồng nghĩa đã tồn tại.

Ví dụ:

~~~java
Product product = new Product();
product.setId(UUID.randomUUID().toString());
product.setName("Keyboard");
~~~

Nếu isNew() chỉ kiểm tra id == null, entity này có thể bị xem là đã tồn tại dù chưa được lưu.

Dùng Persistable<ID> khi cần kiểm soát:

~~~java
public class Product implements Persistable<String> {

    @Id
    private String id;

    @CreatedDate
    private Instant createdDate;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return createdDate == null;
    }
}
~~~

Đây là ví dụ tối giản. Nếu dữ liệu được import với CreatedDate có sẵn, hoặc field có thể null dù document đã tồn tại, cần một trạng thái new/persisted đáng tin cậy hơn.

## 21. Cấu hình reactive repositories và auditing cùng nhau

Ví dụ configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableReactiveElasticsearchRepositories;
import org.springframework.data.elasticsearch.config.EnableReactiveElasticsearchAuditing;

@Configuration
@EnableReactiveElasticsearchRepositories(
    basePackages = "com.example.product.repository"
)
@EnableReactiveElasticsearchAuditing(
    auditorAwareRef = "reactiveAuditorAware"
)
class ReactiveElasticsearchConfiguration {
}
~~~

Reactive client configuration có thể nằm trong class cấu hình riêng kế thừa ReactiveElasticsearchConfiguration của Spring Data. Nếu cùng dùng một tên class, đặt tên rõ ràng để tránh nhầm giữa application configuration và Spring Data base class.

Ví dụ provider:

~~~java
@Bean
ReactiveAuditorAware<String> reactiveAuditorAware() {
    return () -> ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
~~~

Không bật đồng thời imperative và reactive repository scanning trên cùng package nếu không có thiết kế rõ ràng. Hai repository infrastructure có thể tạo bean trùng hoặc chọn operations không mong muốn.

## 22. Migration checklist theo giai đoạn

### Giai đoạn A: Dependency và client

1. Xác định Spring Boot, Spring Data Elasticsearch và Elasticsearch server version.
2. Kiểm tra dependency tree để tìm client cũ.
3. Loại bỏ RestHighLevelClient nếu đã chuyển sang client generation mới.
4. Chuyển cấu hình reactive sang ReactiveElasticsearchConfiguration phù hợp.
5. Với Spring Data 6.x, kiểm tra Rest5Client default và legacy RestClient usage.
6. Cập nhật import và client configuration callbacks.
7. Chuyển NativeSearchQuery sang NativeQuery nếu thuộc migration path 4.4 lên 5.0.
8. Cập nhật các thay đổi kiểu dữ liệu/API như Long sequence number hoặc ScriptData khi cần.
9. Kiểm tra TLS, timeout, authentication và connection lifecycle.

### Giai đoạn B: Reactive operations

1. Dùng ReactiveElasticsearchOperations hoặc ReactiveElasticsearchRepository.
2. Loại bỏ block() trong request path.
3. Trả Mono/Flux về tầng gọi.
4. Không subscribe thủ công trong service.
5. Xử lý timeout, retry và cancellation.
6. Kiểm tra bulk/search pagination và backpressure.
7. Kiểm tra client/transport có được đóng đúng lifecycle.

### Giai đoạn C: Auditing

1. Thêm audit fields vào entity.
2. Chọn kiểu date/time và mapping.
3. Xác định isNew() cho entity có ID được cấp trước.
4. Bật EnableReactiveElasticsearchAuditing.
5. Cung cấp ReactiveAuditorAware nếu cần CreatedBy/LastModifiedBy.
6. Đọc principal từ Reactor/Spring Security reactive context.
7. Cấu hình fallback system actor nếu nghiệp vụ cho phép.
8. Cấu hình DateTimeProvider nếu cần clock thống nhất.

### Giai đoạn D: Entity callbacks

1. Liệt kê callbacks và event listeners hiện có.
2. Chuyển callback đồng bộ sang reactive callback tương ứng.
3. Trả entity hoặc Publisher chứa entity.
4. Bỏ blocking I/O và ThreadLocal access.
5. Đặt callback order rõ ràng.
6. Không ghi đè audit fields ngoài policy.
7. Tách durable side effects sang outbox/workflow.
8. Kiểm tra direct client/bulk/update paths có bypass callbacks không.

### Giai đoạn E: Kiểm thử và triển khai

1. Khởi động Spring context với reactive configuration.
2. Kiểm tra reactive repository bean được tạo đúng.
3. Kiểm tra save tạo CreatedDate/CreatedBy.
4. Kiểm tra update giữ CreatedDate và đổi LastModifiedDate.
5. Kiểm tra ReactiveAuditorAware lấy đúng principal.
6. Kiểm tra background job dùng system actor.
7. Kiểm tra callback chạy khi subscribe.
8. Kiểm tra callback order.
9. Kiểm tra bulk/direct client paths.
10. Chạy integration test với Elasticsearch version tương thích.
11. Theo dõi lỗi mapping, timeout, connection pool và latency sau deploy.

## 23. Kiểm thử reactive auditing

Test cần subscribe pipeline để callback được thực thi. Dùng StepVerifier:

~~~java
StepVerifier.create(productRepository.save(product))
    .assertNext(saved -> {
        assertThat(saved.getCreatedDate()).isNotNull();
        assertThat(saved.getLastModifiedDate()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("test-user");
    })
    .verifyComplete();
~~~

Để test principal, thiết lập reactive security context trong subscriber:

~~~java
Mono<Product> result = productRepository.save(product)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );

StepVerifier.create(result)
    .assertNext(saved ->
        assertThat(saved.getCreatedBy()).isEqualTo("test-user")
    )
    .verifyComplete();
~~~

Chi tiết test fixture Authentication và Spring Security dependency phụ thuộc dự án.

### 23.1. Kiểm tra create và update

Kịch bản:

1. Save entity lần đầu.
2. Lưu lại CreatedDate và CreatedBy.
3. Chờ hoặc cố định clock.
4. Update entity và save lần nữa.
5. Xác nhận CreatedDate/CreatedBy không đổi.
6. Xác nhận LastModifiedDate/LastModifiedBy được cập nhật.

Không dùng thời gian thực sát nhau rồi assert millisecond khác nhau nếu clock precision không bảo đảm. Có thể inject Clock cố định hoặc tăng clock trong test.

### 23.2. Kiểm tra callback

Một callback test có thể thêm field marker:

~~~java
@Component
class ProductMarkerCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Mono<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {
        product.setIndexedByCallback(true);
        return Mono.just(product);
    }
}
~~~

Sau save và đọc lại document, xác nhận field marker được ghi. Nếu test chỉ gọi method mà không subscribe, callback sẽ chưa chạy.

## 24. Các lỗi thường gặp

**Dùng imperative client configuration cho reactive repository.** Reactive repository cần ReactiveElasticsearchOperations và reactive client tương ứng. Dùng ReactiveElasticsearchConfiguration.

**Giữ RestHighLevelClient sau khi chuyển sang client mới.** Package cũ đã deprecated và có thể bị loại bỏ. Thay bằng client/API theo migration guide.

**Nâng Elasticsearch Java API Client độc lập với Spring Data.** Dependency có thể không tương thích. Để Spring Boot/Spring Data BOM quản lý version nếu có thể.

**Chỉ đổi NativeSearchQuery thành NativeQuery rồi giữ nguyên query builder cũ.** Query model mới dùng Elasticsearch Java API Client classes. Chuyển và kiểm tra DSL theo từng query.

**Dùng EnableElasticsearchAuditing cho reactive stack.** Dùng EnableReactiveElasticsearchAuditing.

**Dùng AuditorAware đồng bộ để lấy principal reactive.** Dùng ReactiveAuditorAware và đọc principal qua Reactor Context.

**Đọc SecurityContextHolder trong reactive pipeline.** ThreadLocal không bảo đảm theo request khi đổi thread. Dùng ReactiveSecurityContextHolder.

**Quên isNew() khi ID được cấp trước.** CreatedDate/LastModifiedDate có thể bị xử lý sai. Dùng Persistable hoặc chiến lược nhận diện entity mới rõ ràng.

**Dùng callback đồng bộ trong reactive template.** Reactive implementation gọi reactive callback interface. Chuyển sang ReactiveBeforeConvertCallback và interface tương ứng.

**Callback không trả entity đã sửa.** Thay đổi bị mất trước khi convert. Trả đúng instance hoặc Publisher chứa instance mới.

**Gọi block() trong callback.** Có thể chặn event loop và làm giảm throughput. Compose Publisher hoặc chuyển I/O ra khỏi callback.

**Subscribe thủ công trong service.** Caller không kiểm soát lỗi và completion. Trả Publisher về caller.

**Dùng ThreadLocal để lấy auditor.** Reactive execution có thể đổi thread. Lấy principal từ Reactor Context.

**Callback ghi đè CreatedDate.** Callback chạy sau auditing có thể reset metadata. Kiểm soát order và chỉ sửa field thuộc trách nhiệm.

**Cho rằng callback chạy với mọi low-level API.** Direct client, script hoặc bulk path có thể bypass entity lifecycle. Điền audit metadata ở đúng tầng.

**Gửi side effect không bền vững trong AfterSaveCallback.** Save thành công không đồng nghĩa message/email đã được giao. Dùng outbox/workflow cho side effect quan trọng.

**Không kiểm tra reactive callback vì test không subscribe.** Callback chỉ chạy trong pipeline khi subscription diễn ra. Dùng StepVerifier hoặc subscribe tại test boundary.

**Dùng application event async để sửa entity trước save.** Event multicaster có thể chạy khác thread và không bảo đảm thứ tự. Dùng EntityCallback.

## 25. Quy trình triển khai nâng cấp an toàn

Một lộ trình thực tế:

1. Chốt version matrix của Spring Boot, Spring Data Elasticsearch, Elasticsearch client và server.
2. Đọc migration guide giữa version nguồn và đích.
3. Chuyển reactive client configuration sang class phù hợp.
4. Chuyển query API, imports và client callbacks.
5. Xác nhận ReactiveElasticsearchOperations và repository wiring.
6. Thêm auditing annotations và kiểm tra entity isNew semantics.
7. Bật EnableReactiveElasticsearchAuditing.
8. Chuyển AuditorAware sang ReactiveAuditorAware.
9. Chuyển callback implementations sang reactive interfaces.
10. Kiểm tra callback order và tránh blocking.
11. Kiểm tra các đường ghi bypass Spring Data entity lifecycle.
12. Viết integration tests cho create/update/auditor/callback.
13. Triển khai canary và quan sát latency, errors, connection pool, audit fields.
14. Xóa code client/callback legacy sau khi toàn bộ caller đã chuyển.

## 26. Tài liệu tham khảo

- [Spring Data Elasticsearch - Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html): imperative/reactive client configuration và Rest5Client.
- [Spring Data Elasticsearch - Upgrading 4.4.x to 5.0.x](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides/migration-guide-4.4-5.0.html): package changes, NativeQuery và client migration.
- [Spring Data Elasticsearch - Upgrading 5.5.x to 6.0.x](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides/migration-guide-5.5-6.0.html): Elasticsearch 9 libraries, Rest5Client, legacy RestClient và API changes.
- [Spring Data Elasticsearch - Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html): entity audit metadata, Persistable, AuditorAware và reactive auditing.
- [Spring Data Elasticsearch - Entity Callbacks](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/entity-callbacks.html): synchronous/reactive callback interfaces, lifecycle và ordering.
- [Spring Data Commons - Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/data-commons/auditing.html): CreatedBy, CreatedDate, AuditorAware và ReactiveAuditorAware.
- [Spring Data Elasticsearch - ReactiveElasticsearchAuditing API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/config/EnableReactiveElasticsearchAuditing.html): cấu hình reactive auditing.
- [Spring Security - Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): security context trong reactive application.

Package, method signature và client generation thay đổi theo Spring Data Elasticsearch version. Hãy đối chiếu Javadoc và migration guide đúng phiên bản đang nâng cấp. Mấu chốt là reactive client, reactive auditing và reactive callbacks phải cùng thuộc reactive lifecycle; mọi thao tác ghi cần được kiểm tra để bảo đảm audit metadata được tạo đúng và không bị callback tùy chỉnh ghi đè.
