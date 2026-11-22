# Cấu hình địa chỉ cluster và thông tin xác thực

Ứng dụng Spring Boot dùng Spring Data Elasticsearch cần biết endpoint HTTP của Elasticsearch và cách xác thực khi gửi request. Sai địa chỉ thường gây lỗi DNS, connection refused hoặc timeout; sai thông tin xác thực thường gây HTTP 401 hoặc 403. Bài này hướng dẫn cấu hình endpoint, một hoặc nhiều node, Basic Authentication, HTTPS/TLS, secret theo môi trường, timeout và cách kiểm tra kết nối.

## 1. Xác định đúng địa chỉ cluster

### 1.1. HTTP endpoint của Elasticsearch

Elasticsearch cluster có thể gồm một hoặc nhiều node. Mỗi node có thể cung cấp HTTP endpoint để client gửi request tìm kiếm, đọc, ghi hoặc quản lý dữ liệu. URI thường có dạng:

~~~text
http://localhost:9200
https://elasticsearch.example.com:9200
~~~

Một URI gồm scheme (http/https), host (hostname hoặc IP), port và có thể có path prefix nếu đi qua reverse proxy.

Với cấu hình mặc định phổ biến, cổng `9200` là cổng HTTP. Cổng `9300` thường dành cho giao tiếp transport giữa các node Elasticsearch. Ứng dụng Spring Data Elasticsearch sử dụng HTTP client nên cần endpoint HTTP, thường là cổng 9200 hoặc cổng do hạ tầng chỉ định.

Không dùng địa chỉ Kibana làm địa chỉ Elasticsearch. Kibana là dịch vụ riêng; ứng dụng Spring Data cần endpoint của Elasticsearch.

### 1.2. Cluster, node và endpoint

- **Cluster** là nhóm node cùng vận hành và quản lý dữ liệu.
- **Node** là một tiến trình Elasticsearch tham gia cluster.
- **Endpoint** là địa chỉ mạng mà client kết nối đến một node hoặc dịch vụ đứng trước cluster.

Ứng dụng thường không cần tự quản lý topology nội bộ. Nó nhận một hoặc nhiều địa chỉ HTTP có thể truy cập được, sau đó HTTP client gửi request theo cấu hình.

| Môi trường | Địa chỉ thường gặp |
|---|---|
| Elasticsearch chạy trực tiếp trên máy phát triển | `http://localhost:9200` |
| Hai container cùng Docker network | `http://elasticsearch:9200` nếu service tên `elasticsearch` |
| Kubernetes | DNS của Service, ví dụ `http://elasticsearch.default.svc:9200` |
| Máy chủ hoặc VM | Hostname/IP và HTTP port do hạ tầng cung cấp |
| Elastic Cloud/dịch vụ quản lý | HTTPS endpoint được cấp trong trang quản lý |

`localhost` luôn chỉ máy hoặc network namespace nơi tiến trình ứng dụng đang chạy. Nếu Spring Boot chạy trong container, `localhost` trỏ về chính container ứng dụng, không phải container Elasticsearch khác. Hai container cùng Docker network nên dùng tên service hoặc DNS nội bộ. Nếu ứng dụng chạy trên host còn Elasticsearch chạy trong container, hãy dùng cổng đã publish ra host.

### 1.3. Một node hay nhiều node?

Với môi trường phát triển đơn giản, một URI có thể đủ:

~~~yaml
spring:
  elasticsearch:
    uris:
      - http://localhost:9200
~~~

Khi có nhiều endpoint của cùng cluster, có thể khai báo danh sách:

~~~yaml
spring:
  elasticsearch:
    uris:
      - https://es-node-1.example.com:9200
      - https://es-node-2.example.com:9200
      - https://es-node-3.example.com:9200
~~~

Danh sách này cung cấp nhiều địa chỉ cho client kết nối. Cách chọn node, retry và chuyển endpoint phụ thuộc HTTP client và cấu hình của nó. Danh sách URI không tự tạo cluster, không thay thế DNS/load balancer và không bảo đảm mọi node đều truy cập được từ nơi ứng dụng chạy.

Chỉ khai báo endpoint thực sự được phép nhận request từ ứng dụng. Trong production, nhiều hệ thống cung cấp một endpoint load balancer hoặc proxy ổn định thay vì để từng ứng dụng biết địa chỉ tất cả node.

### 1.4. Path prefix

Một số hệ thống đặt Elasticsearch sau reverse proxy và yêu cầu request có tiền tố đường dẫn:

~~~text
https://gateway.example.com/search/
~~~

Có thể cấu hình URI gốc và path prefix riêng:

~~~yaml
spring:
  elasticsearch:
    uris: https://gateway.example.com
    path-prefix: /search
~~~

Chỉ dùng `path-prefix` khi hạ tầng thực sự định tuyến Elasticsearch dưới đường dẫn con. Không thêm `/products`, `/_search` hoặc tên index vào URI kết nối gốc. Những đường dẫn đó thuộc từng API request, không phải địa chỉ cluster.

## 2. Cấu hình kết nối bằng Spring Boot

### 2.1. Các thuộc tính cơ bản

Trong Spring Boot 3.3.x, nhóm thuộc tính `spring.elasticsearch` có thể cấu hình endpoint và các thông tin kết nối phổ biến:

| Thuộc tính | Mục đích |
|---|---|
| `spring.elasticsearch.uris` | Một hoặc nhiều HTTP/HTTPS endpoint |
| `spring.elasticsearch.username` | Username cho HTTP Basic Authentication |
| `spring.elasticsearch.password` | Password cho HTTP Basic Authentication |
| `spring.elasticsearch.connection-timeout` | Thời gian chờ thiết lập kết nối |
| `spring.elasticsearch.socket-timeout` | Thời gian chờ dữ liệu trên socket |
| `spring.elasticsearch.socket-keep-alive` | Bật/tắt TCP keep-alive nếu client hỗ trợ |
| `spring.elasticsearch.path-prefix` | Tiền tố đường dẫn khi đi qua proxy |

Ví dụ cấu hình tối thiểu cho Elasticsearch cục bộ không yêu cầu xác thực:

~~~yaml
spring:
  elasticsearch:
    uris:
      - http://localhost:9200
    connection-timeout: 5s
    socket-timeout: 30s
~~~

Giá trị thời gian có thể dùng đơn vị như `ms`, `s` hoặc `m`. Chọn timeout dựa trên độ trễ mạng và đặc tính truy vấn. Timeout quá ngắn có thể ngắt request hợp lệ; timeout quá dài khiến ứng dụng giữ tài nguyên lâu khi cluster gặp sự cố.

### 2.2. Cấu hình Basic Authentication

Nếu Elasticsearch yêu cầu HTTP Basic Authentication, khai báo username và password:

~~~yaml
spring:
  elasticsearch:
    uris:
      - https://elasticsearch.example.com:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 5s
    socket-timeout: 30s
~~~

Spring Boot sử dụng các thuộc tính này để cấu hình client kết nối. Các placeholder lấy giá trị từ environment variable hoặc nguồn cấu hình Spring hỗ trợ.

Không đặt username/password trực tiếp trong URI như `https://user:password@host:9200`. Cách đó dễ làm lộ thông tin xác thực qua log, file cấu hình, lịch sử lệnh hoặc công cụ quan sát request.

Không commit password thật vào `application.yml`, file cấu hình chia sẻ, Docker image hoặc Git repository. File cấu hình chỉ nên chứa tên biến tham chiếu; secret thật được cấp khi triển khai.

### 2.3. Tách cấu hình theo môi trường

Địa chỉ cluster và credential thường khác nhau giữa máy cá nhân, kiểm thử và production. Có thể giữ cấu hình chung trong `application.yml` và nạp giá trị riêng qua profile hoặc environment variable.

Ví dụ `application.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS:http://localhost:9200}
    connection-timeout: 5s
    socket-timeout: 30s
~~~

Ví dụ `application-prod.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 5s
    socket-timeout: 30s
~~~

Khi chạy production, kích hoạt profile `prod` và cung cấp các biến môi trường tương ứng. Ví dụ tên biến:

~~~text
ELASTICSEARCH_URIS=https://es-prod.example.com:9200
ELASTICSEARCH_USERNAME=product-search-service
ELASTICSEARCH_PASSWORD=<secret được cấp từ hệ thống quản lý bí mật>
~~~

Dòng `<secret ...>` chỉ là nội dung minh họa, không phải password hợp lệ. Không lưu secret thật vào file cấu hình đã commit.

Có thể cấp biến môi trường bằng Docker/Kubernetes secret, secret manager của nền tảng cloud hoặc cơ chế quản lý secret của CI/CD. Hạn chế truyền password bằng tham số dòng lệnh vì command history và danh sách tiến trình có thể làm lộ giá trị.

Spring Boot có thứ tự ưu tiên property source. Environment variable hoặc tham số triển khai có thể ghi đè giá trị trong YAML. Nếu ứng dụng kết nối nhầm cluster, hãy kiểm tra giá trị hiệu lực tại môi trường chạy, không chỉ kiểm tra file trong repository.

### 2.4. Cấu hình client khác cấu hình server

`spring.elasticsearch.*` là cấu hình phía ứng dụng Spring Boot. Nó cho client biết kết nối đến đâu và xác thực thế nào.

Các thiết lập như `cluster.name`, `node.name`, `network.host`, `http.port` và `path.data` thuộc cấu hình tiến trình Elasticsearch server. Không đặt chúng dưới `spring.elasticsearch` để mong Spring Boot thay đổi cluster.

Ví dụ cấu hình server Elasticsearch:

~~~yaml
cluster.name: product-search
node.name: es-node-1
network.host: 0.0.0.0
http.port: 9200
~~~

Ứng dụng Spring Boot chỉ cần endpoint mà server công bố và cho phép truy cập. Việc cấu hình, khởi động, mở firewall hoặc cấp quyền cho Elasticsearch server thuộc trách nhiệm triển khai/hạ tầng.

## 3. Authentication và quyền truy cập

### 3.1. Authentication khác authorization

- **Authentication** xác định ứng dụng đang kết nối với danh tính nào.
- **Authorization** xác định danh tính đó được phép thực hiện thao tác nào.

Username/password đúng chưa chắc cho phép ứng dụng đọc hoặc ghi mọi index. Elasticsearch có thể xác thực thành công nhưng từ chối thao tác do thiếu quyền.

Ví dụ, tài khoản chỉ được tìm kiếm trên index `products` có thể không được phép xóa index, tạo user hoặc đọc index khác. Hãy cấp quyền theo nguyên tắc tối thiểu: service chỉ có các quyền cần cho nghiệp vụ của nó.

### 3.2. HTTP Basic Authentication

Basic Authentication gửi username/password trong HTTP Authorization header theo cơ chế Base64 encoding. Base64 không phải mã hóa bảo mật; bất kỳ ai đọc được header đều có thể khôi phục thông tin xác thực.

Vì vậy:

- Chỉ dùng Basic Authentication qua HTTPS trong môi trường production hoặc khi credential đi qua mạng không tin cậy.
- Không ghi Authorization header vào log.
- Không chia sẻ credential giữa nhiều ứng dụng nếu có thể cấp danh tính riêng.
- Luân chuyển password khi nghi ngờ credential bị lộ hoặc theo chính sách bảo mật.
- Cấp role chỉ đủ quyền cho service.

Một số môi trường phát triển có thể tắt security để đơn giản hóa việc học. Không suy luận rằng production cũng được phép kết nối không xác thực.

### 3.3. API key và cơ chế xác thực khác

Elasticsearch cũng hỗ trợ API key và các cơ chế xác thực khác tùy cách triển khai. API key thường được gửi trong Authorization header theo định dạng Elasticsearch quy định.

Các thuộc tính `spring.elasticsearch.username` và `spring.elasticsearch.password` ở ví dụ trên dành cho Basic Authentication. Không đặt API key vào trường password rồi mặc định client sẽ hiểu đó là API key.

Nếu hệ thống cấp API key, hãy cấu hình header xác thực bằng cơ chế tùy biến client được hỗ trợ bởi phiên bản Spring Boot/Spring Data Elasticsearch đang dùng. Với Spring Data Elasticsearch, có thể cần tùy chỉnh `ClientConfiguration` hoặc HTTP client tương ứng. Chọn extension point phù hợp với phiên bản thư viện; tránh tạo client riêng trong khi repository/operations vẫn dùng client auto-configured khác.

API key cũng là secret: chỉ cấp quyền cần thiết, lưu trong secret manager và không đưa vào source code hoặc log.

### 3.4. Quản lý secret

Những nơi thường vô tình làm lộ credential gồm:

- File `application-prod.yml` được commit.
- Dockerfile hoặc image layer chứa password.
- Log in toàn bộ environment variable.
- CI job in lệnh có chứa secret.
- Screenshot hoặc tài liệu có credential thật.
- URL kết nối chứa username/password.

Nếu credential đã được commit hoặc gửi đến nơi không an toàn, xóa khỏi file hiện tại là chưa đủ vì lịch sử Git, log hoặc artifact có thể vẫn lưu giá trị cũ. Hãy thu hồi/rotate credential tại Elasticsearch và xử lý lịch sử lưu trữ theo quy trình bảo mật của tổ chức.

## 4. HTTPS và chứng chỉ TLS

### 4.1. Khi nào dùng HTTPS?

Với endpoint HTTP:

~~~text
http://elasticsearch.example.com:9200
~~~

request không được mã hóa ở tầng TLS. Với endpoint HTTPS:

~~~text
https://elasticsearch.example.com:9200
~~~

kết nối được mã hóa và client có thể xác minh danh tính server qua chứng chỉ TLS.

Trong production, đặc biệt khi credential đi qua mạng, hãy sử dụng HTTPS. Nhiều bản cài Elasticsearch hiện đại bật security và TLS theo cấu hình mặc định hoặc hướng dẫn cài đặt. Hãy lấy đúng endpoint, CA certificate và credential từ người quản trị hoặc nền tảng triển khai.

### 4.2. Client phải tin cậy CA certificate

Khi kết nối HTTPS, JVM cần xác minh được certificate chain của server và hostname trong chứng chỉ phải phù hợp với hostname client truy cập.

Nếu server dùng certificate do CA công khai đáng tin cậy cấp, JVM có thể đã tin cậy CA đó. Nếu server dùng CA nội bộ hoặc certificate tự ký, cần đưa CA phù hợp vào truststore mà JVM/client sử dụng hoặc cấu hình SSL context theo cơ chế được hỗ trợ.

Một số cách xử lý ở cấp JVM:

- Cài CA certificate nội bộ vào truststore được JVM sử dụng.
- Chỉ định truststore phù hợp bằng JVM system properties khi khởi chạy.
- Dùng SSL bundle hoặc custom SSL configuration nếu phiên bản Spring Boot và client đang dùng hỗ trợ.

Tên file, đường dẫn và password truststore phải được quản lý theo môi trường triển khai. Không đưa private key hoặc password truststore vào Git.

### 4.3. Không tắt xác minh chứng chỉ

Khi gặp `SSLHandshakeException`, nguyên nhân thường nằm ở certificate chain, truststore, hostname hoặc giao thức TLS. Hãy kiểm tra chứng chỉ và cấu hình trust.

Không dùng cấu hình trust-all, bỏ xác minh hostname hoặc chế độ không xác minh certificate để làm cho kết nối chạy được trong production. Những cách đó làm mất khả năng xác thực server và có thể khiến credential bị gửi đến máy chủ giả mạo.

Nếu dùng mutual TLS (mTLS), server còn yêu cầu client certificate. Ngoài truststore để xác minh server, client cần keystore/certificate phù hợp. Cấu hình mTLS phụ thuộc hạ tầng và cách tạo HTTP client; thuộc tính username/password cơ bản không tự cấu hình đầy đủ mTLS.

## 5. Timeout và khả năng kết nối

### 5.1. Connection timeout

Connection timeout giới hạn thời gian client chờ thiết lập kết nối tới endpoint. Nếu DNS không phân giải được, host không thể truy cập hoặc server không nhận kết nối, thao tác có thể thất bại khi hết thời gian này.

Giá trị quá thấp gây lỗi giả khi mạng có độ trễ; giá trị quá cao làm ứng dụng mất nhiều thời gian phát hiện endpoint không sẵn sàng.

### 5.2. Socket timeout

Socket timeout giới hạn thời gian chờ dữ liệu trao đổi trên kết nối theo cấu hình client. Truy vấn tìm kiếm có thể tốn thời gian hơn thao tác đọc đơn giản, vì vậy hãy chọn giá trị dựa trên thời gian xử lý dự kiến và SLA.

Không tăng timeout vô hạn để che giấu truy vấn chậm. Nếu truy vấn thường xuyên vượt timeout, cần xem xét query, mapping, lượng dữ liệu, tải cluster và network latency.

### 5.3. Timeout, retry và kiểm soát tải

Timeout chỉ giới hạn thời gian chờ. Nó không tự bảo đảm request được thực hiện lại an toàn. Khi bổ sung retry, cần phân biệt thao tác đọc với thao tác ghi và hiểu rằng request trước đó có thể đã được server xử lý nhưng response bị mất.

Không retry vô hạn khi cluster quá tải. Chính sách retry thiếu giới hạn có thể làm tăng số request và khiến hệ thống quá tải nặng hơn.

## 6. Spring Boot auto-configuration và Spring Data

### 6.1. Auto-configuration

Khi dự án có dependency Spring Data Elasticsearch tương thích với phiên bản Spring Boot, Boot có thể auto-configure các thành phần client dựa trên `spring.elasticsearch.*`.

Repository và `ElasticsearchOperations` sử dụng cấu hình kết nối do ứng dụng cung cấp. Vì vậy, khi chỉ cần URI, Basic Authentication và timeout thông thường, bắt đầu bằng application configuration thường là đủ.

Ví dụ một service inject repository:

~~~java
@Service
public class ProductSearchService {

    private final ProductRepository productRepository;

    public ProductSearchService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    // Các phương thức nghiệp vụ gọi repository tại đây.
}
~~~

Service không cần tự mở socket hoặc tự gắn Authorization header cho từng request. Client được cấu hình ở tầng tích hợp và được Spring quản lý.

### 6.2. Khi nào cần custom client configuration?

Có thể cần tùy chỉnh khi hệ thống dùng API key, proxy đặc biệt, mTLS, SSL context riêng, custom headers hoặc yêu cầu HTTP client mà các thuộc tính cơ bản không biểu diễn được.

Trước khi tạo cấu hình tùy chỉnh, hãy xác định phiên bản Spring Boot/Spring Data Elasticsearch và extension point tương ứng. Nếu tự tạo `RestClient`, `ElasticsearchClient` hoặc cấu hình Spring Data riêng, cần bảo đảm repository và `ElasticsearchOperations` cùng sử dụng đúng client đó.

Không vô tình tạo hai đường kết nối: một client auto-configured từ `spring.elasticsearch.*` và một client tự tạo với credential khác. Khi đó request từ repository có thể vẫn đi qua client cũ dù một bean client khác đã được cấu hình.

Khi thay đổi auto-configuration, hãy kiểm tra bean thực tế được Spring tạo và log cấu hình đã che secret. Không in password, API key hoặc Authorization header để xác minh.

## 7. Kiểm tra endpoint và thông tin xác thực

### 7.1. Kiểm tra từ môi trường chạy ứng dụng

Trước khi kiểm tra code Java, xác nhận máy/container chạy Spring Boot có thể truy cập endpoint Elasticsearch.

Một phép kiểm tra cơ bản là gọi root endpoint. Ví dụ trong terminal kiểu POSIX:

~~~bash
curl --fail --silent --show-error \
  --user "$ELASTICSEARCH_USERNAME:$ELASTICSEARCH_PASSWORD" \
  "$ELASTICSEARCH_URI/"
~~~

Nếu endpoint sử dụng CA nội bộ, bổ sung CA certificate được cấp:

~~~bash
curl --fail --silent --show-error \
  --cacert "$ELASTICSEARCH_CA_CERT" \
  --user "$ELASTICSEARCH_USERNAME:$ELASTICSEARCH_PASSWORD" \
  "$ELASTICSEARCH_URI/"
~~~

Các biến trong ví dụ phải được cấp trong môi trường terminal trước khi chạy. Không thay chúng bằng password thật rồi lưu lệnh vào tài liệu hoặc script chia sẻ. Với endpoint local không bật authentication, có thể gọi root endpoint mà không truyền `--user`.

Root endpoint thường trả thông tin cơ bản về cluster/node và phiên bản khi request được chấp nhận. Đây là bước kiểm tra endpoint và xác thực ban đầu; nó không chứng minh tài khoản có quyền truy vấn index mà ứng dụng cần.

### 7.2. Kiểm tra cluster health khi có quyền

Có thể kiểm tra thêm:

~~~bash
curl --fail --silent --show-error \
  --user "$ELASTICSEARCH_USERNAME:$ELASTICSEARCH_PASSWORD" \
  "$ELASTICSEARCH_URI/_cluster/health"
~~~

API cluster health có thể yêu cầu quyền giám sát cluster. Nếu service account chỉ được cấp quyền đọc index `products`, request này có thể bị từ chối dù ứng dụng vẫn tìm kiếm sản phẩm bình thường.

Không cấp quyền quản trị cluster chỉ để phép kiểm tra health hoạt động. Hãy dùng tài khoản giám sát riêng hoặc kiểm tra API mà service thực sự có quyền truy cập.

### 7.3. Kiểm tra trong ứng dụng

Sau khi endpoint hoạt động từ môi trường chạy, khởi động ứng dụng Spring Boot với đúng profile và environment variable. Thử một thao tác repository đơn giản hoặc truy vấn đã được cấp quyền.

Nếu root endpoint thành công nhưng thao tác tìm kiếm thất bại, hãy kiểm tra:

- Tài khoản có quyền trên index cần dùng không.
- Index đã tồn tại chưa.
- Mapping của field có phù hợp với truy vấn không.
- Ứng dụng có đang kết nối đúng cluster/profile không.
- Request có đi qua proxy hoặc path prefix đúng không.

Việc Spring tạo được bean client không nhất thiết chứng minh cluster đã sẵn sàng. Hãy thực hiện request kiểm tra thực tế từ ứng dụng.

## 8. Chẩn đoán lỗi kết nối thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `UnknownHostException` | Hostname sai hoặc DNS không phân giải được | Kiểm tra URI, DNS và network của container |
| `Connection refused` | Sai port, server chưa chạy hoặc không lắng nghe trên địa chỉ đó | Kiểm tra HTTP port và trạng thái service |
| `Connect timed out` | Firewall, route mạng hoặc endpoint không truy cập được | Kiểm tra network policy, security group và endpoint |
| HTTP `401 Unauthorized` | Thiếu hoặc sai credential | Kiểm tra username/password, API key và cơ chế auth |
| HTTP `403 Forbidden` | Đã xác thực nhưng thiếu quyền | Kiểm tra role/index privileges |
| `SSLHandshakeException` | CA không được tin cậy, certificate không hợp lệ hoặc TLS không tương thích | Kiểm tra truststore, certificate chain và hostname |
| HTTP `404 Not Found` | Sai endpoint, path prefix hoặc tài nguyên/index không tồn tại | Kiểm tra URL và route proxy |
| HTTP `400 Bad Request` | Request/query không hợp lệ hoặc kiểu dữ liệu không phù hợp | Đọc response body và kiểm tra query/mapping |
| Socket/read timeout | Cluster xử lý chậm, mạng chậm hoặc timeout quá ngắn | Kiểm tra latency, tải cluster và query |
| Kết nối được nhưng không có kết quả | Query không khớp hoặc index/dữ liệu không như mong đợi | Kiểm tra index, document, analyzer và query |

Hãy phân loại lỗi theo tầng trước khi thay đổi cấu hình:

1. **DNS/network**: ứng dụng có tìm thấy host và mở được kết nối không?
2. **TLS**: client có xác minh được chứng chỉ server không?
3. **Authentication**: server có nhận diện được danh tính ứng dụng không?
4. **Authorization**: danh tính đó có quyền gọi API/index cần thiết không?
5. **Application/query**: request có đúng endpoint, mapping và cú pháp không?

Không đổi nhiều thuộc tính cùng lúc. Thay từng yếu tố theo bằng chứng từ lỗi giúp xác định nguyên nhân nhanh hơn.

## 9. Checklist cấu hình theo môi trường

Trước khi đưa ứng dụng vào một môi trường mới, hãy xác nhận:

- [ ] Có URI HTTP/HTTPS đúng của Elasticsearch endpoint.
- [ ] Hostname và port truy cập được từ chính môi trường chạy Spring Boot.
- [ ] Không nhầm HTTP port với transport port hoặc địa chỉ Kibana.
- [ ] Nếu dùng Docker/Kubernetes, hostname phù hợp với network/DNS nội bộ.
- [ ] Nếu có nhiều URI, tất cả đều là endpoint hợp lệ mà client được phép truy cập.
- [ ] Nếu đi qua reverse proxy, path prefix được cấu hình chính xác.
- [ ] Cơ chế xác thực đã được xác định: Basic Auth, API key hoặc cơ chế khác.
- [ ] Credential được cấp từ secret manager/environment, không nằm trong Git.
- [ ] Tài khoản có đúng quyền trên index và API cần dùng.
- [ ] HTTPS certificate được JVM tin cậy và hostname được xác minh.
- [ ] Connection timeout và socket timeout phù hợp với môi trường.
- [ ] Đã kiểm tra endpoint từ môi trường chạy và thử thao tác ứng dụng có quyền.
- [ ] Log không ghi password, API key, token hoặc Authorization header.

Khi các điểm này đã rõ, bạn có thể tiếp tục khai báo document, mapping và repository. Những phần đó sẽ sử dụng client đã được Spring Boot cấu hình để giao tiếp với cluster.
