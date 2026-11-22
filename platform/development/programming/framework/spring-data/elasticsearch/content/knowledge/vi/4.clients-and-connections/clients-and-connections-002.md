# Cấu hình bằng `ElasticsearchConfiguration` và `ClientConfiguration`

Spring Data Elasticsearch cần một client để giao tiếp với cụm Elasticsearch. Trong cấu hình Java của Spring Data Elasticsearch 5.x, hai thành phần thường đi cùng nhau là:

- **`ClientConfiguration`** mô tả cách kết nối: địa chỉ node, TLS, thông tin xác thực, timeout, HTTP headers, proxy và path prefix.
- **`ElasticsearchConfiguration`** là lớp cấu hình nền của Spring Data Elasticsearch. Ta kế thừa lớp này và cung cấp `ClientConfiguration`; Spring Data dùng cấu hình đó để đăng ký client cùng các thành phần tích hợp như `ElasticsearchOperations`.

`ClientConfiguration` không phải client đang gửi request. Nó là đối tượng mô tả cấu hình kết nối. `ElasticsearchConfiguration` sử dụng đối tượng đó để thiết lập hạ tầng Spring Data.

Bài viết tập trung vào cấu hình Java dựa trên Elasticsearch Java API Client trong Spring Data Elasticsearch 5.x. Các phiên bản Spring Data Elasticsearch 4.x sử dụng cơ chế client cũ và có API cấu hình khác; không nên trộn hai cách cấu hình trong cùng một ứng dụng.

## 1. Luồng cấu hình và các thành phần

Luồng khởi tạo có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["ElasticsearchConfiguration"]
    B --> C["clientConfiguration()"]
    C --> D["ClientConfiguration"]
    D --> E["REST transport và Elasticsearch Java API Client"]
    E --> F["ElasticsearchOperations"]
    E --> G["ElasticsearchRepository"]
    F --> H["Ứng dụng gọi search, save, delete..."]
    G --> H
    H --> I["Elasticsearch cluster"]
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `ClientConfiguration` | Khai báo endpoint và các tùy chọn HTTP/TLS/authentication |
| `ElasticsearchConfiguration` | Tạo và đăng ký hạ tầng tích hợp Elasticsearch cho Spring |
| `ElasticsearchClient` | Java API Client dùng để gọi API Elasticsearch |
| `ElasticsearchOperations` | API thao tác cấp cao của Spring Data, có mapping và chuyển đổi entity |
| `ElasticsearchRepository` | Repository abstraction cho các thao tác CRUD và truy vấn |

Trong ứng dụng Spring Data, code nghiệp vụ thường làm việc với repository hoặc `ElasticsearchOperations`. Khi cần dùng trực tiếp API mới của Elasticsearch, ứng dụng có thể inject `ElasticsearchClient`.

## 2. Cấu hình tối thiểu cho môi trường local

Giả sử Elasticsearch đang chạy tại `localhost:9200` và không yêu cầu TLS hay xác thực. Có thể tạo một lớp cấu hình như sau:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

Điểm quan trọng:

- `@Configuration` để Spring phát hiện lớp cấu hình.
- `extends ElasticsearchConfiguration` để sử dụng cơ chế cấu hình client do Spring Data cung cấp.
- `clientConfiguration()` trả về mô tả kết nối.
- `connectedTo("localhost:9200")` chỉ định địa chỉ Elasticsearch.
- `build()` hoàn tất đối tượng cấu hình.

Sau khi cấu hình được nạp vào application context, các bean hạ tầng tương ứng được đăng ký để repository và `ElasticsearchOperations` có thể sử dụng.

Địa chỉ trong `connectedTo` thường được viết dưới dạng `host:port`. Cấu hình TLS được khai báo riêng bằng `usingSsl()`; không cần thêm `http://` hoặc `https://` vào chuỗi host.

## 3. Cấu hình repository scanning

Nếu ứng dụng sử dụng interface kế thừa `ElasticsearchRepository`, Spring cần biết package chứa repository.

Có thể khai báo `@EnableElasticsearchRepositories` trong lớp cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
)
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

Ví dụ repository:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Spring Data tạo implementation cho repository interface khi quá trình repository scanning được cấu hình đúng.

`@EnableElasticsearchRepositories` điều khiển việc phát hiện repository; `ElasticsearchConfiguration` cung cấp hạ tầng client và operations. Đây là hai trách nhiệm liên quan nhưng không giống nhau.

Trong ứng dụng Spring Boot, auto-configuration có thể đã thiết lập repository scanning theo package mặc định. Khi đó cần kiểm tra cấu hình đang dùng trước khi khai báo thêm `@EnableElasticsearchRepositories`, tránh cấu hình repository trùng lặp hoặc quét sai package.

## 4. Cấu hình nhiều node

Một cụm Elasticsearch có thể có nhiều node có thể nhận request. `connectedTo` nhận nhiều địa chỉ:

~~~java
@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo(
                    "es-node-1.internal:9200",
                    "es-node-2.internal:9200",
                    "es-node-3.internal:9200"
            )
            .build();
}
~~~

Danh sách này cung cấp các endpoint cho client HTTP sử dụng. Khi một node không truy cập được, client có thể tiếp tục làm việc với endpoint khác theo cơ chế lựa chọn node và retry của transport.

Một vài lưu ý khi cấu hình nhiều node:

- Các endpoint phải thuộc cụm mà ứng dụng được phép truy cập.
- Các node cần có cấu hình giao thức và bảo mật tương thích.
- Nếu triển khai sau load balancer hoặc reverse proxy, hãy dùng endpoint mà ứng dụng thực sự truy cập được.
- Việc khai báo nhiều node không thay thế health check, giám sát cụm hoặc thiết kế retry ở tầng nghiệp vụ.

Trong môi trường Docker Compose, nếu ứng dụng và Elasticsearch nằm ở hai container khác nhau trên cùng network, hostname thường là tên service, chẳng hạn `elasticsearch:9200`. `localhost` bên trong container ứng dụng trỏ về chính container ứng dụng, không tự động trỏ sang container Elasticsearch.

## 5. Cấu hình timeout

Hai timeout thường cần quan tâm là:

- **Connect timeout**: thời gian tối đa để thiết lập kết nối tới endpoint.
- **Socket timeout**: thời gian chờ dữ liệu phản hồi sau khi kết nối đã được thiết lập.

Có thể cấu hình bằng `Duration`:

~~~java
import java.time.Duration;

@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .withConnectTimeout(Duration.ofSeconds(5))
            .withSocketTimeout(Duration.ofSeconds(30))
            .build();
}
~~~

Hai giá trị có ý nghĩa khác nhau. Nếu connect timeout quá ngắn, ứng dụng có thể thất bại khi mạng chậm hoặc node đang bận thiết lập kết nối. Nếu socket timeout quá ngắn, một truy vấn hợp lệ nhưng tốn thời gian có thể bị ngắt trước khi nhận được phản hồi.

Không nên đặt timeout quá lớn chỉ để che giấu truy vấn chậm hoặc Elasticsearch quá tải. Hãy chọn giá trị theo đặc tính mạng, thời gian xử lý dự kiến và yêu cầu của từng luồng nghiệp vụ.

Timeout ở client cũng không thay thế timeout ở load balancer, reverse proxy, gateway hoặc server. Các tầng này có thể có giới hạn riêng.

## 6. Kết nối qua HTTPS và xác thực

Trong môi trường triển khai, Elasticsearch thường được bảo vệ bằng TLS và cơ chế xác thực.

### HTTPS với Basic Authentication

Có thể kết hợp `usingSsl()` và `withBasicAuth`:

~~~java
import java.time.Duration;

@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo("es.example.internal:9200")
            .usingSsl()
            .withBasicAuth(
                    System.getenv("ELASTICSEARCH_USERNAME"),
                    System.getenv("ELASTICSEARCH_PASSWORD")
            )
            .withConnectTimeout(Duration.ofSeconds(5))
            .withSocketTimeout(Duration.ofSeconds(30))
            .build();
}
~~~

Trong ví dụ, thông tin xác thực được lấy từ biến môi trường để không ghi username/password trực tiếp vào mã nguồn. Tên biến chỉ là ví dụ; môi trường triển khai cần cấp giá trị phù hợp.

`usingSsl()` yêu cầu client sử dụng kết nối TLS. Chứng thư của Elasticsearch phải được JVM tin cậy và hostname phải khớp với chứng thư. Nếu hệ thống dùng CA nội bộ, cần cấu hình trust store hoặc SSL context phù hợp theo chính sách bảo mật của môi trường.

Không nên tắt xác minh chứng thư để xử lý nhanh lỗi TLS trong môi trường thật. Cần sửa chuỗi chứng thư, trust store hoặc hostname cho đúng.

### Gửi HTTP headers tùy chỉnh

Một số môi trường sử dụng API key hoặc yêu cầu header riêng. Có thể tạo `HttpHeaders` và cung cấp qua `withHeaders`:

~~~java
import org.springframework.http.HttpHeaders;

@Override
public ClientConfiguration clientConfiguration() {
    HttpHeaders headers = new HttpHeaders();
    headers.add(
            HttpHeaders.AUTHORIZATION,
            "ApiKey " + System.getenv("ELASTICSEARCH_API_KEY")
    );

    return ClientConfiguration.builder()
            .connectedTo("es.example.internal:9200")
            .usingSsl()
            .withHeaders(() -> headers)
            .build();
}
~~~

Header trong ví dụ minh họa cách truyền API key theo dạng Elasticsearch hỗ trợ. Giá trị API key phải được tạo và quản lý ở hệ thống Elasticsearch; ứng dụng không nên tự tạo chuỗi giả định rồi coi đó là credential hợp lệ.

Chọn cơ chế xác thực mà cluster yêu cầu. Không cần gửi Basic Authentication và API key cùng lúc nếu server không yêu cầu điều đó.

## 7. Các tùy chọn kết nối khác

Ngoài endpoint, TLS, authentication và timeout, `ClientConfiguration` còn hỗ trợ một số tùy chọn phục vụ hạ tầng mạng.

| Tùy chọn | Mục đích |
|---|---|
| `withPathPrefix("elasticsearch")` | Thêm tiền tố đường dẫn khi Elasticsearch nằm sau reverse proxy có path prefix |
| `withProxy("proxy-host:8080")` | Kết nối thông qua HTTP proxy |
| `withHeaders(...)` | Cung cấp HTTP headers cho request |
| `withConnectTimeout(...)` | Giới hạn thời gian thiết lập kết nối |
| `withSocketTimeout(...)` | Giới hạn thời gian chờ dữ liệu phản hồi |
| `usingSsl()` | Bật HTTPS/TLS |
| `withBasicAuth(...)` | Cấu hình HTTP Basic Authentication |

Ví dụ về path prefix:

~~~java
@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo("gateway.example.internal:443")
            .usingSsl()
            .withPathPrefix("search")
            .build();
}
~~~

Tùy chọn path prefix chỉ nên dùng khi gateway thực sự định tuyến Elasticsearch dưới đường dẫn đó. Nếu endpoint đã trỏ trực tiếp đến Elasticsearch, thêm prefix sai có thể dẫn đến lỗi HTTP 404.

Tên phương thức và overload có thể thay đổi giữa các phiên bản thư viện. Khi sử dụng một tùy chọn nâng cao, hãy đối chiếu API của đúng phiên bản Spring Data Elasticsearch mà dự án đang quản lý.

## 8. Sử dụng client và Spring Data operations sau khi cấu hình

Sau khi cấu hình được nạp, service có thể inject `ElasticsearchOperations` để làm việc với entity:

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public void save(Product product) {
        operations.save(product);
    }

    public Product findById(String id) {
        return operations.get(id, Product.class);
    }

    public void deleteById(String id) {
        operations.delete(id, Product.class);
    }
}
~~~

`ElasticsearchOperations` là abstraction cấp cao của Spring Data. Nó phối hợp mapping metadata, converter và client để chuyển đổi giữa entity Java và document Elasticsearch.

Nếu cần gọi API trực tiếp, có thể inject Java API Client:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class NativeElasticsearchService {

    private final ElasticsearchClient elasticsearchClient;

    // Gọi các API của Elasticsearch Java API Client tại đây.
}
~~~

Hai cách sử dụng có mức trừu tượng khác nhau:

- Dùng `ElasticsearchOperations` hoặc repository khi muốn làm việc theo mô hình Spring Data và entity.
- Dùng `ElasticsearchClient` khi cần sử dụng trực tiếp API của Elasticsearch Java Client hoặc một tính năng mà abstraction cấp cao chưa bao phủ thuận tiện.

Không cần tự tạo một client thứ hai trong service. Hãy sử dụng bean được quản lý bởi Spring để các thành phần dùng chung cấu hình, transport và vòng đời.

## 9. Phân biệt cấu hình Java với Spring Boot auto-configuration

Trong ứng dụng Spring Boot, có hai cách tổ chức phổ biến:

**Cách 1 — Dùng auto-configuration của Spring Boot**

Spring Boot đọc cấu hình từ application properties/YAML và tạo các bean Elasticsearch phù hợp với dependency đang có. Đây thường là cách ngắn gọn khi endpoint và tùy chọn kết nối không có yêu cầu tùy biến đặc biệt.

Ví dụ cấu hình endpoint theo thuộc tính Spring Boot của phiên bản tương ứng:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

Tên property, cấu trúc SSL và các tùy chọn được hỗ trợ cần đối chiếu với phiên bản Spring Boot đang sử dụng.

**Cách 2 — Tự cấu hình bằng `ElasticsearchConfiguration`**

Ứng dụng tạo lớp cấu hình kế thừa `ElasticsearchConfiguration` và tự trả về `ClientConfiguration`. Cách này phù hợp khi cần điều khiển endpoint, TLS, authentication, headers, timeout hoặc cách kết nối cụ thể bằng Java.

Khi đã chọn cấu hình Java, cần xác định rõ bean nào do cấu hình tùy chỉnh sở hữu và bean nào do Boot tự động tạo. Tránh khai báo nhiều client hoặc nhiều cấu hình repository cạnh tranh nhau.

Không nên vừa tùy chỉnh client bằng một lớp `ElasticsearchConfiguration`, vừa tự tạo một `RestClient`/`ElasticsearchClient` khác trong cùng application context mà không có chủ đích rõ ràng. Điều đó dễ dẫn đến bean trùng tên, phụ thuộc không nhất quán hoặc các service sử dụng những kết nối có cấu hình khác nhau.

## 10. Cấu hình nào phù hợp với môi trường nào?

| Môi trường | Cấu hình thường dùng |
|---|---|
| Local development | Một endpoint, thường không TLS nếu cluster local được cấu hình như vậy |
| Docker Compose | Hostname là tên service và port nội bộ của Elasticsearch |
| Test integration | Endpoint của Elasticsearch test instance, timeout phù hợp với môi trường CI |
| Staging/production | Nhiều endpoint hoặc load balancer, TLS, credential lấy từ secret, timeout được xác định rõ |
| Sau reverse proxy | Endpoint của gateway, TLS và path prefix nếu gateway yêu cầu |

Không nên sao chép nguyên cấu hình local sang production. Địa chỉ mạng, xác thực, TLS, quyền truy cập và timeout phụ thuộc môi trường triển khai.

## 11. Các lỗi kết nối thường gặp

### Connection refused

Ví dụ lỗi:

~~~text
Connection refused: localhost/127.0.0.1:9200
~~~

Nguyên nhân thường gặp:

- Elasticsearch chưa khởi động hoặc chưa sẵn sàng.
- Sai port hoặc endpoint.
- Ứng dụng chạy trong container nhưng lại dùng `localhost` thay cho tên service.
- Port chưa được expose hoặc network không cho phép truy cập.

Hãy kiểm tra trạng thái Elasticsearch và khả năng truy cập từ chính môi trường chạy ứng dụng.

### Unknown host hoặc DNS resolution failed

Hostname không phân giải được. Kiểm tra tên service/container, DNS nội bộ, network và cấu hình endpoint.

### HTTP 401 Unauthorized

Server không chấp nhận thông tin xác thực. Kiểm tra username, password, API key, cách truyền header và credential có còn hiệu lực hay không.

### HTTP 403 Forbidden

Thông tin xác thực có thể hợp lệ nhưng principal thiếu quyền thực hiện thao tác. Kiểm tra role và quyền trên cluster/index.

### SSLHandshakeException

Lỗi TLS thường liên quan đến:

- JVM chưa tin cậy CA ký chứng thư server.
- Chứng thư hết hạn hoặc thiếu intermediate certificate.
- Hostname kết nối không khớp với Subject Alternative Name của chứng thư.
- Client đang dùng HTTP trong khi endpoint yêu cầu HTTPS, hoặc ngược lại.

Cần sửa trust chain và endpoint theo cấu hình thật của server.

### Timeout

Phân biệt connect timeout với socket timeout. Nếu không thể thiết lập kết nối, kiểm tra DNS, firewall, route và trạng thái node. Nếu đã kết nối nhưng phản hồi chậm, kiểm tra truy vấn, tải cluster, network và timeout của các tầng trung gian.

### Không tìm thấy repository bean

Kiểm tra package của repository, phạm vi component/repository scanning và việc cấu hình `@EnableElasticsearchRepositories` có phù hợp với cách ứng dụng đang dùng hay không.

### Lỗi tương thích thư viện

Spring Data Elasticsearch và Elasticsearch Java API Client cần các phiên bản tương thích. Trong ứng dụng Spring Boot, nên ưu tiên dependency management do Spring Boot cung cấp; tránh tự nâng riêng một thư viện client lên phiên bản không tương thích với Spring Data đang dùng.

## 12. Checklist khi đưa cấu hình vào ứng dụng

Khi tạo hoặc thay đổi cấu hình, hãy xác nhận:

1. Đang sử dụng đúng thế hệ Spring Data Elasticsearch và đúng loại client.
2. Endpoint có thể truy cập được từ nơi ứng dụng chạy.
3. Protocol HTTP/HTTPS khớp với cấu hình server.
4. TLS certificate được JVM tin cậy.
5. Credential hoặc API key được lấy từ nguồn cấu hình an toàn.
6. Connect timeout và socket timeout phù hợp với workload.
7. Repository scanning bao phủ đúng package.
8. Các service sử dụng bean client/operations do Spring quản lý.
9. Không tạo client hoặc cấu hình repository trùng lặp.
10. Cấu hình local, test và production phản ánh đúng hạ tầng của từng môi trường.

## Kết luận

`ClientConfiguration` mô tả cách ứng dụng kết nối đến Elasticsearch; `ElasticsearchConfiguration` sử dụng mô tả đó để đăng ký client và hạ tầng Spring Data. Sau khi cấu hình đúng, repository và `ElasticsearchOperations` có thể dùng chung kết nối do Spring quản lý. Hãy lựa chọn cấu hình dựa trên môi trường triển khai, bảo mật, timeout và phiên bản Spring Data Elasticsearch đang sử dụng.
