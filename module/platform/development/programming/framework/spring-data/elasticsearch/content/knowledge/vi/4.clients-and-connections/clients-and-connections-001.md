# Cơ chế tự cấu hình client của Spring Boot

Spring Boot có thể tự tạo các thành phần kết nối Elasticsearch dựa trên dependency và cấu hình trong `application.yml` hoặc `application.properties`. Nhờ cơ chế auto-configuration, ứng dụng thường chỉ cần khai báo địa chỉ cluster, thông tin xác thực và các timeout cần thiết, sau đó inject `ElasticsearchClient`, `ElasticsearchOperations` hoặc repository để làm việc với dữ liệu.

Để hiểu cơ chế này, cần phân biệt ba lớp:

- **Elasticsearch client** thực hiện giao tiếp HTTP với Elasticsearch.
- **Spring Data Elasticsearch** cung cấp mapping Java object thành document, operations API và repository abstraction.
- **Spring Boot auto-configuration** kết nối các thành phần trên dựa vào classpath, properties và các bean hiện có trong ApplicationContext.

Luồng tổng quát:

```text
application.yml / environment variables
                 |
                 v
       ElasticsearchProperties
                 |
                 v
       Low-level REST client
                 |
                 v
        Elasticsearch transport
                 |
                 v
          ElasticsearchClient
                 |
                 v
      Spring Data Elasticsearch
       ├── Mapping context / converter
       ├── ElasticsearchOperations
       └── Repository proxies
                 |
                 v
        Elasticsearch cluster
```

Tên và điều kiện tạo bean cụ thể phụ thuộc phiên bản Spring Boot, nhưng trách nhiệm của các lớp vẫn tương tự. Trong các dòng Spring Boot 3 và Spring Data Elasticsearch 5, client chính là Elasticsearch Java API Client (`co.elastic.clients.elasticsearch.ElasticsearchClient`), được xây dựng trên REST client và transport. Đây là API client hiện đại dùng để gọi các API Elasticsearch theo kiểu Java.

## 1. Auto-configuration hoạt động như thế nào?

Spring Boot auto-configuration là cơ chế cấu hình bean có điều kiện. Khi ứng dụng khởi động, Boot đọc classpath, properties và các bean đã được khai báo để quyết định cấu hình nào phù hợp.

Với Spring Data Elasticsearch, quá trình thường có các bước:

1. Ứng dụng có dependency Elasticsearch phù hợp trên classpath.
2. Boot đọc các thuộc tính trong nhóm `spring.elasticsearch`.
3. Boot cấu hình REST client để kết nối đến một hoặc nhiều HTTP endpoint.
4. REST client được kết hợp với transport và JSON mapper để tạo `ElasticsearchClient`.
5. Spring Data sử dụng client để cấu hình converter, mapping context và `ElasticsearchOperations`.
6. Repository auto-configuration quét package và tạo implementation proxy cho các interface repository phù hợp.

Nhờ vậy, service có thể inject client hoặc operations trực tiếp mà không phải tự tạo connection ở từng nơi.

### Điều kiện để auto-configuration được áp dụng

Auto-configuration chỉ hoạt động khi các dependency cần thiết có mặt và ứng dụng không thay thế cấu hình tương ứng bằng cấu hình riêng. Các điều kiện thường gặp gồm:

- Elasticsearch client và Spring Data Elasticsearch có trên classpath.
- Các properties kết nối được cung cấp hoặc giá trị mặc định phù hợp với môi trường đang chạy được sử dụng.
- ApplicationContext chưa có bean tùy chỉnh khiến cấu hình mặc định tương ứng phải lùi lại.
- Package chứa repository nằm trong phạm vi quét của ứng dụng hoặc được chỉ định rõ.

Boot thường sử dụng điều kiện kiểu `@ConditionalOnClass`, `@ConditionalOnMissingBean` và các điều kiện property để tránh tạo cấu hình không cần thiết hoặc ghi đè bean do ứng dụng chủ động cung cấp. Do đó, khi khai báo một bean client tùy chỉnh, một phần auto-configuration có thể back off. Cần kiểm tra các bean phụ thuộc như transport, operations và repository để bảo đảm toàn bộ chuỗi vẫn được cấu hình đầy đủ.

## 2. Khai báo dependency

Với ứng dụng Spring Boot dùng Spring Data Elasticsearch, thông thường chỉ cần starter tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'
}
```

Starter đưa các thư viện Spring Data và Elasticsearch client tương thích vào dependency graph. Spring Boot dependency management quản lý các phiên bản liên quan để chúng làm việc cùng nhau.

Không nên tùy tiện khai báo một phiên bản `elasticsearch-java` hoặc REST client khác với phiên bản do Spring Boot quản lý. Client và server cũng cần nằm trong ma trận tương thích được Elasticsearch hỗ trợ. Nếu tự nâng riêng một thư viện client, có thể phát sinh lỗi binary/API hoặc lỗi giao tiếp khi chạy.

Với các dự án dùng Spring Boot dependency management, hãy ưu tiên starter và BOM của Boot. Chỉ override phiên bản khi đã xác định rõ lý do, phạm vi tương thích và đã kiểm thử kết nối với cluster đích.

## 3. Cấu hình kết nối qua application.yml

Nhóm cấu hình chính của Spring Boot là `spring.elasticsearch`. Ví dụ:

```yaml
spring:
  elasticsearch:
    uris:
      - http://localhost:9200
    connection-timeout: 2s
    socket-timeout: 30s
```

`uris` là danh sách HTTP endpoint của Elasticsearch. Có thể cấu hình nhiều địa chỉ để REST client có nhiều node endpoint phục vụ kết nối và phân phối request. Ứng dụng không cần tự xác định document đang nằm trên node nào; Elasticsearch định tuyến request đến shard phù hợp.

Các thuộc tính thường dùng:

| Property | Ý nghĩa |
|---|---|
| `spring.elasticsearch.uris` | Một hoặc nhiều URI HTTP/HTTPS của Elasticsearch. |
| `spring.elasticsearch.username` | Username khi cluster sử dụng HTTP Basic Authentication. |
| `spring.elasticsearch.password` | Password tương ứng với username. |
| `spring.elasticsearch.connection-timeout` | Thời gian chờ thiết lập kết nối. |
| `spring.elasticsearch.socket-timeout` | Thời gian chờ dữ liệu trên socket khi request đang được thực hiện. |
| `spring.elasticsearch.path-prefix` | Prefix đường dẫn nếu endpoint được đặt sau reverse proxy có path prefix. |
| `spring.elasticsearch.socket-keep-alive` | Cấu hình TCP keep-alive cho socket theo hỗ trợ của client. |

Tên property và khả năng tùy chỉnh cần đối chiếu với phiên bản Spring Boot của dự án. Không sao chép cấu hình từ tài liệu Boot cũ mà chưa kiểm tra namespace đang được phiên bản hiện tại hỗ trợ.

### Kết nối cluster có xác thực

Ví dụ sử dụng HTTPS và Basic Authentication:

```yaml
spring:
  elasticsearch:
    uris:
      - https://es-01.example.com:9200
      - https://es-02.example.com:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 3s
    socket-timeout: 45s
```

Username và password được lấy từ environment variables để tránh đưa secret trực tiếp vào source code hoặc file cấu hình được commit. Trong môi trường triển khai, các biến này nên được cấp qua secret manager hoặc cơ chế quản lý secret của nền tảng.

HTTPS chỉ mã hóa đường truyền khi client xác minh đúng chứng chỉ máy chủ. Nếu cluster dùng CA nội bộ hoặc chứng chỉ riêng, cần cấu hình truststore hoặc cơ chế trust phù hợp. Không tắt xác minh chứng chỉ để xử lý tạm lỗi TLS trong production.

Các property username/password nói trên phục vụ Basic Authentication. Nếu dịch vụ yêu cầu API key, token động, client certificate hoặc cơ chế xác thực riêng, cần dùng điểm mở rộng/custom client phù hợp với phiên bản Boot và nhà cung cấp Elasticsearch; không giả định rằng chỉ cần điền API key vào trường password là đủ.

### Cấu hình qua environment variables

Spring Boot hỗ trợ externalized configuration, nên có thể đưa cấu hình ra ngoài ứng dụng. Ví dụ:

```text
SPRING_ELASTICSEARCH_URIS=https://es.example.com:9200
SPRING_ELASTICSEARCH_USERNAME=app-user
SPRING_ELASTICSEARCH_PASSWORD=<secret>
```

Các biến trên ánh xạ vào property tương ứng theo quy tắc relaxed binding. Có thể dùng profile riêng như `application-dev.yml`, `application-test.yml` và `application-prod.yml` để mỗi môi trường có endpoint khác nhau.

Không nên đặt `localhost` trong cấu hình production nếu ứng dụng chạy ở một máy/container khác cluster. `localhost` luôn trỏ về network namespace của tiến trình ứng dụng. Ví dụ, khi Spring Boot chạy trong Docker Compose, `localhost:9200` là cổng 9200 bên trong chính container ứng dụng; thường cần dùng tên service Elasticsearch trên network Compose.

## 4. Những bean thường được Boot cấu hình

Tùy phiên bản, các bean có thể được tạo qua nhiều lớp auto-configuration. Về mặt chức năng, cần hiểu các thành phần sau:

### 4.1. REST client

REST client quản lý kết nối HTTP đến Elasticsearch. Nó xử lý endpoint, request, response, timeout, connection pool và các cấu hình transport liên quan. Đây là lớp giao tiếp thấp hơn mà Java API Client sử dụng.

Ứng dụng thông thường không cần tự tạo một REST client cho mỗi request. Một client được quản lý trong ApplicationContext có thể được chia sẻ giữa các service.

### 4.2. Elasticsearch transport và Java API Client

Transport kết nối REST client với cơ chế serialize/deserialize JSON. Java API Client cung cấp API Java có kiểu dữ liệu cho các thao tác như index, get, search, update, delete và cluster APIs.

Có thể inject client trực tiếp:

```java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchClient elasticsearchClient;

    public ProductSearchService(ElasticsearchClient elasticsearchClient) {
        this.elasticsearchClient = elasticsearchClient;
    }
}
```

`ElasticsearchClient` phù hợp khi cần sử dụng trực tiếp Java API Client hoặc một API Elasticsearch chưa được abstraction ở tầng Spring Data đáp ứng theo cách mong muốn.

### 4.3. ElasticsearchOperations

Spring Data cung cấp `ElasticsearchOperations` để thao tác ở mức domain object và metadata mapping. Operations API thường phù hợp khi ứng dụng cần kiểm soát truy vấn hoặc index operation mà vẫn muốn tận dụng converter và mapping của Spring Data.

Ví dụ inject:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

Spring Data cũng cung cấp `ElasticsearchTemplate` như implementation của operations abstraction. Trong ứng dụng, nên phụ thuộc vào interface `ElasticsearchOperations` nếu không cần ràng buộc với implementation cụ thể.

### 4.4. Repository proxy

Khi bật repository support, Spring Data tạo implementation proxy cho interface repository. Ví dụ:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Service có thể inject repository và gọi các phương thức CRUD hoặc query method được Spring Data hỗ trợ. Ứng dụng không cần tự viết implementation cho interface này trong trường hợp thông thường.

## 5. Repository scanning và cấu hình bật/tắt

Trong ứng dụng Spring Boot, repository thường được quét từ package của lớp `@SpringBootApplication` trở xuống. Ví dụ:

```text
com.example.store
  ├── StoreApplication.java
  ├── product
  │    ├── Product.java
  │    └── ProductRepository.java
  └── search
       └── ProductSearchService.java
```

Nếu repository nằm ngoài phạm vi package scan mặc định, có thể chỉ định rõ bằng `@EnableElasticsearchRepositories`:

```java
@SpringBootApplication
@EnableElasticsearchRepositories(
    basePackages = "com.example.store.search.repository"
)
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

Không cần thêm annotation này nếu Boot đã quét đúng package và repository auto-configuration đang hoạt động. Khai báo scan trùng hoặc nhiều cấu hình repository không cần thiết có thể làm cấu hình khó hiểu hơn.

Có thể tắt repository auto-configuration bằng:

```yaml
spring:
  data:
    elasticsearch:
      repositories:
        enabled: false
```

Việc tắt repository không đồng nghĩa tắt toàn bộ Elasticsearch client. Ứng dụng vẫn có thể dùng `ElasticsearchClient` hoặc `ElasticsearchOperations` nếu các bean tương ứng vẫn được cấu hình.

## 6. Khi nào cần thay thế auto-configuration?

Auto-configuration đáp ứng phần lớn kết nối thông thường. Cấu hình riêng chỉ nên được thêm khi có yêu cầu cụ thể, ví dụ:

- Dùng API key, token hoặc cơ chế xác thực riêng.
- Cần truststore/certificate hoặc SSL context đặc biệt.
- Cần custom HTTP headers, proxy, connection pool hoặc callback xử lý request.
- Có nhiều cluster Elasticsearch với mục đích khác nhau trong cùng một ứng dụng.
- Cần kiểm soát transport, serializer hoặc client lifecycle ở mức thấp.

Spring Boot cung cấp các điểm mở rộng cho REST client builder ở những phiên bản tương ứng. Có thể khai báo customizer bean để bổ sung thiết lập mà vẫn giữ phần lớn auto-configuration mặc định. Ví dụ về mặt ý tưởng:

```java
@Bean
RestClientBuilderCustomizer elasticsearchClientCustomizer() {
    return builder -> {
        // Bổ sung cấu hình HTTP phù hợp với môi trường triển khai.
    };
}
```

Interface và package của customizer cần được import theo đúng phiên bản Spring Boot. Nếu yêu cầu vượt quá khả năng customizer, có thể tự khai báo client/transport bean. Khi đó cần kiểm tra điều kiện back-off của auto-configuration và tự chịu trách nhiệm về việc đóng tài nguyên, chia sẻ client, mapping và operations bean liên quan.

### Nhiều cluster trong một ứng dụng

Các property `spring.elasticsearch.*` chủ yếu phục vụ cấu hình client mặc định. Nếu ứng dụng kết nối hai cluster độc lập, ví dụ một cluster tìm kiếm sản phẩm và một cluster audit, cần cấu hình hai client riêng với endpoint, credential và bean name rõ ràng.

Có thể tạo các bean `ElasticsearchClient` riêng, sau đó dùng `@Qualifier` để inject đúng client vào service. Nếu cần Spring Data operations/repository cho từng cluster, phải cấu hình cả operations template, mapping context và repository binding tương ứng; chỉ tạo hai client bean chưa đủ để hai nhóm repository tự động biết phải dùng cluster nào.

Tránh dùng cùng một bean name hoặc inject theo type khi có nhiều client mà không chỉ rõ `@Qualifier`, vì Spring có thể không xác định được bean phù hợp.

## 7. Kiểm tra kết nối và xử lý lỗi khởi động

Khi ứng dụng khởi động thành công, điều đó không phải lúc nào cũng chứng minh cluster có thể xử lý mọi truy vấn nghiệp vụ. Cần kiểm tra kết nối thực tế bằng một thao tác phù hợp hoặc health check được thiết kế cho hệ thống.

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| `Connection refused` | Elasticsearch chưa chạy, sai port, sai địa chỉ hoặc service chưa sẵn sàng nhận kết nối. |
| DNS/unknown host | Hostname không phân giải được trong network của ứng dụng, thường gặp khi dùng sai tên service/container. |
| Timeout | Network chậm, firewall, endpoint không phản hồi, timeout quá ngắn hoặc cluster quá tải. |
| HTTP 401 | Thiếu hoặc sai thông tin xác thực. |
| HTTP 403 | Đã xác thực nhưng user/API key không có quyền thao tác. |
| SSL handshake/certificate error | Sai trust chain, hostname certificate không khớp hoặc cấu hình TLS không phù hợp. |
| Version/API compatibility error | Phiên bản client, Spring Data và server không tương thích hoặc request dùng API không được server hỗ trợ. |
| Repository bean không tồn tại | Repository nằm ngoài phạm vi scan, thiếu dependency hoặc repository auto-configuration bị tắt. |

Có thể bật điều kiện report của Spring Boot khi cần tìm hiểu vì sao một auto-configuration được áp dụng hoặc bị bỏ qua. Chạy ứng dụng với chế độ debug để xem condition evaluation report, sau đó kiểm tra các bean thực tế trong ApplicationContext. Không nên suy luận chỉ từ việc dependency đã có trong Gradle rằng tất cả bean Elasticsearch chắc chắn đã được tạo.

Trong production, nên giám sát cả khả năng kết nối và trạng thái cluster. Health check cần cân nhắc timeout, tần suất và tác động của request; không nên gửi truy vấn nặng hoặc thao tác tạo/xóa index ở mỗi lần kiểm tra health.

## 8. Vòng đời client và nguyên tắc sử dụng

Client được Boot tạo và quản lý như bean của Spring ApplicationContext. Khi ứng dụng dừng, Spring quản lý vòng đời và đóng các tài nguyên bean theo cấu hình của chúng. Vì vậy:

- Inject và tái sử dụng client được quản lý bởi Spring.
- Không tạo một client mới cho từng request hoặc từng lần gọi repository.
- Không tự đóng client được inject từ ApplicationContext sau mỗi thao tác.
- Nếu tự tạo client, phải xác định rõ ai sở hữu và đóng REST client/transport khi ứng dụng dừng.
- Không log password, API key, Authorization header hoặc dữ liệu nhạy cảm trong request/response.

Một client dùng chung giúp tái sử dụng connection pool và tránh tạo quá nhiều socket. Service nên tập trung vào truy vấn và nghiệp vụ; thông tin kết nối, timeout và xác thực thuộc cấu hình môi trường.

## 9. Kiểm thử cấu hình client

Không nên để mọi unit test đều phụ thuộc một Elasticsearch thật. Có thể chia kiểm thử theo mục tiêu:

- **Unit test:** mock repository hoặc operations khi kiểm tra logic service; test không cần kết nối cluster.
- **Context test:** xác minh các bean cần thiết được tạo và inject đúng khi dùng cấu hình ứng dụng.
- **Integration test:** chạy Elasticsearch tương thích trong Testcontainers hoặc môi trường test riêng để xác minh mapping, query, serialization và hành vi thực tế.

Spring Boot cung cấp test slice cho Spring Data Elasticsearch ở các phiên bản phù hợp, giúp tập trung kiểm thử lớp repository. Khi dùng test slice, vẫn cần cung cấp endpoint hoặc test infrastructure phù hợp; annotation test không tự tạo một cluster production.

Đối với integration test, nên kiểm tra cả việc tạo index/mapping, ghi document, đọc theo id và tìm kiếm. Nếu test phụ thuộc vào search ngay sau khi ghi, hãy xử lý rõ thời điểm refresh thay vì dựa vào timing ngẫu nhiên.

## 10. Những điểm cần nhớ

- `spring.elasticsearch.*` là nhóm property cấu hình kết nối Elasticsearch trong Spring Boot hiện đại.
- Boot đọc properties và classpath để tự cấu hình REST client, transport và Elasticsearch Java API Client.
- Spring Data dùng client để tạo `ElasticsearchOperations`, mapping/converter và repository proxy.
- `ElasticsearchClient` phù hợp khi cần Java API Client trực tiếp; `ElasticsearchOperations` và repository phù hợp với abstraction của Spring Data.
- Repository scan thường dựa vào package của `@SpringBootApplication`; chỉ dùng `@EnableElasticsearchRepositories` khi cần chỉ định phạm vi riêng.
- Khai báo bean tùy chỉnh có thể làm một phần auto-configuration back off; phải kiểm tra toàn bộ chuỗi bean phụ thuộc.
- Dùng externalized configuration cho endpoint và credential; không commit secret vào repository.
- Tái sử dụng client do Spring quản lý, không tạo client mới theo từng request.
- Chỉ custom client khi có yêu cầu rõ ràng như API key, TLS đặc biệt, proxy hoặc nhiều cluster.

Nắm được cơ chế auto-configuration giúp ứng dụng Spring Data Elasticsearch có cấu hình kết nối gọn, nhất quán giữa các môi trường và dễ kiểm soát khi cần mở rộng. Khi có lỗi, hãy lần theo chuỗi từ properties, REST client, transport, Java API Client đến Spring Data operations và repository để xác định chính xác lớp cấu hình đang gặp vấn đề.
