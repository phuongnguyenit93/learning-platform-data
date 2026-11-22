# Cấu hình tài khoản, API key và header xác thực

Spring Data Elasticsearch giao tiếp với Elasticsearch thông qua HTTP client. Khi Elasticsearch bật security, mỗi request cần mang thông tin xác thực hợp lệ. Tài khoản, mật khẩu, API key hoặc token giúp server xác định danh tính gọi API; quyền được gán cho danh tính đó quyết định request được phép đọc, ghi, tạo index hay quản lý cluster.

Bài học này trình bày cách cấu hình xác thực cho ứng dụng Spring Boot dùng Spring Data Elasticsearch, cách gửi header tùy chỉnh và cách quản lý thông tin bí mật. Các ví dụ dùng HTTPS cho cluster từ xa. Với Elasticsearch local đã tắt security trong môi trường học tập, ứng dụng có thể kết nối HTTP mà không cần credentials; không áp dụng cách đó cho cluster dùng chung hoặc production.

## 1. Xác thực và phân quyền

Hai khái niệm thường đi cùng nhau nhưng giải quyết hai câu hỏi khác nhau:

- **Authentication (xác thực):** request đến từ ai? Server kiểm tra thông tin đăng nhập, API key hoặc token để xác định danh tính.
- **Authorization (phân quyền):** danh tính đó được làm gì? Elasticsearch kiểm tra quyền trên cluster, index và thao tác cụ thể.

Ví dụ, ứng dụng có thể xác thực thành công bằng API key nhưng chỉ được đọc index `products`. Khi ứng dụng gọi API tìm kiếm, request được cho phép; khi cố ghi document hoặc xóa index, Elasticsearch có thể trả về `403 Forbidden` vì thiếu quyền.

Không nên cấp quyền quản trị cluster cho ứng dụng chỉ vì ứng dụng cần đọc và ghi document. Hãy xác định trước index và thao tác thực sự cần thiết, sau đó cấp quyền tối thiểu tương ứng.

## 2. Các phương thức xác thực thường gặp

Elasticsearch và các hệ thống đứng trước nó có thể sử dụng một số cách gửi credentials:

| Phương thức | HTTP header | Trường hợp sử dụng |
| --- | --- | --- |
| HTTP Basic Authentication | `Authorization: Basic <base64(username:password)>` | Tài khoản Elasticsearch với username và password. |
| Elasticsearch API key | `Authorization: ApiKey <encoded-api-key>` | Ứng dụng hoặc service cần credentials riêng, có thể giới hạn quyền và thời hạn. |
| Bearer token | `Authorization: Bearer <token>` | Service token, token OAuth/OIDC hoặc hệ thống xác thực được cấu hình hỗ trợ Bearer. |
| Header tùy chỉnh | Ví dụ `X-API-Key: <value>` | API gateway, reverse proxy hoặc lớp xác thực nội bộ yêu cầu header riêng. |

Không được nhầm lẫn các scheme trên. Elasticsearch API key dùng scheme `ApiKey`; nó không tự động trở thành Bearer token hoặc header `X-API-Key`. Chỉ dùng đúng loại header mà Elasticsearch hoặc gateway ở trước Elasticsearch được cấu hình chấp nhận.

### 2.1. Basic Authentication

Basic Authentication gửi username và password trong header `Authorization`. Giá trị credentials được mã hóa Base64 theo định dạng `username:password` trước khi gửi.

Ví dụ về cấu trúc header:

~~~http
Authorization: Basic <base64-encoded-credentials>
~~~

Base64 chỉ là cách biểu diễn dữ liệu, không phải mã hóa bảo mật. Người có thể đọc request cũng có thể khôi phục username và password. Vì vậy, Basic Authentication phải được truyền qua HTTPS khi kết nối qua mạng.

Với ứng dụng Spring Boot, cấu hình tài khoản bằng biến môi trường thay vì ghi trực tiếp mật khẩu vào file cấu hình được commit:

~~~yaml
spring:
  elasticsearch:
    uris: https://elasticsearch.example.com:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
~~~

Spring Boot dùng các thuộc tính này khi cấu hình Elasticsearch client tự động. Ứng dụng cần có quyền đọc index tương ứng trên tài khoản được cung cấp. Chứng thư TLS của server cũng phải được JVM tin cậy.

Khi chạy local HTTP không bật security, URI có thể là `http://localhost:9200` và không cần username/password. Không đưa password giả vào cấu hình chỉ để làm cho ứng dụng khởi động.

### 2.2. Elasticsearch API key

API key là credential được tạo riêng cho một ứng dụng hoặc một mục đích sử dụng. So với việc dùng chung mật khẩu của một tài khoản cá nhân, API key giúp tách quyền của ứng dụng, đặt thời hạn và thu hồi độc lập.

Khi tạo API key, Elasticsearch trả về các trường như `id`, `name`, `api_key` và `encoded`. Trường `encoded` là giá trị đã được mã hóa Base64 theo định dạng `id:api_key`; đây là giá trị dùng trong header xác thực:

~~~http
Authorization: ApiKey <encoded-value-returned-by-Elasticsearch>
~~~

Không mã hóa Base64 lần thứ hai nếu đang sử dụng trường `encoded`. Giá trị `api_key` và `encoded` đều là thông tin bí mật; chỉ hiển thị hoặc lưu chúng ở nơi được bảo vệ. Elasticsearch chỉ trả secret lúc tạo key, vì vậy cần lưu an toàn ngay khi nhận kết quả.

### 2.3. Bearer token

Bearer token thường được dùng khi hệ thống cấp token truy cập, chẳng hạn service token hoặc OAuth/OIDC. Request gửi token trong header:

~~~http
Authorization: Bearer <access-token>
~~~

Token thường có thời hạn. Ứng dụng phải có cơ chế lấy mới token trước khi token hết hạn và gửi token hiện hành cho request. Không dùng `Bearer` cho Elasticsearch API key encoded trừ khi lớp gateway được thiết kế riêng để chấp nhận cách đó.

### 2.4. Header tùy chỉnh

Một reverse proxy hoặc API gateway có thể yêu cầu header riêng, ví dụ:

~~~http
X-API-Key: <gateway-key>
X-Tenant-ID: learning-team
~~~

Header như `X-API-Key` không phải quy ước xác thực API key mặc định của Elasticsearch. Hãy xác nhận hợp đồng của gateway hoặc dịch vụ trung gian trước khi cấu hình. Nếu gateway xác thực request rồi chuyển tiếp đến Elasticsearch, cần xác định rõ gateway truyền danh tính người gọi và quyền xuống backend như thế nào.

## 3. Tạo API key có quyền tối thiểu

API key nên đại diện cho một ứng dụng và chỉ có quyền trên các index mà ứng dụng cần thao tác. Có thể tạo key qua Kibana Dev Tools hoặc Security API của Elasticsearch.

Ví dụ tạo key cho ứng dụng quản lý index `products` với quyền đọc, ghi và xem metadata index:

~~~http
POST /_security/api_key
Content-Type: application/json

{
  "name": "spring-data-products-lab",
  "expiration": "30d",
  "role_descriptors": {
    "products_app": {
      "cluster": [],
      "indices": [
        {
          "names": ["products"],
          "privileges": [
            "read",
            "write",
            "view_index_metadata"
          ]
        }
      ]
    }
  }
}
~~~

Ví dụ này giả định index `products` đã được tạo. Nếu ứng dụng cần tự tạo index, cần cấp thêm quyền `create_index` cho đúng index pattern sau khi xác định rõ quy trình khởi tạo. Không cấp quyền `all` hoặc quyền quản trị cluster chỉ để repository có thể ghi document.

Người tạo API key cần có quyền quản lý API key phù hợp. Các quyền của API key bị giới hạn bởi cả quyền của người tạo và role descriptors được khai báo khi tạo key; role descriptor không thể làm API key có quyền vượt quá người tạo.

Kết quả tạo key có cấu trúc minh họa:

~~~json
{
  "id": "<key-id>",
  "name": "spring-data-products-lab",
  "api_key": "<secret-value-returned-once>",
  "encoded": "<encoded-id-and-secret-for-authorization-header>"
}
~~~

Lưu trường `encoded` vào secret store hoặc biến môi trường của ứng dụng. Không lưu response thực tế có secret vào Git, ticket, log build hoặc tài liệu chia sẻ.

Có thể kiểm tra key bằng cách gọi API Elasticsearch với header `Authorization: ApiKey ...` và thực hiện một request được cấp quyền, chẳng hạn tìm kiếm trong index `products`. Khi key hết hạn, bị thu hồi hoặc thiếu quyền, request sẽ không còn hoạt động như trước.

## 4. Cấu hình Basic Authentication trong Spring Boot

Với Spring Boot auto-configuration, cách đơn giản nhất là khai báo URI, username và password trong cấu hình. Ví dụ:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS:https://elasticsearch.example.com:9200}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
~~~

Các biến môi trường có thể được cung cấp bởi môi trường chạy ứng dụng, secret manager hoặc cấu hình triển khai. Không ghi giá trị thực vào file YAML được quản lý bằng Git.

Khi cần truyền nhiều endpoint, thuộc tính `uris` có thể chứa danh sách URI theo định dạng được Spring Boot hỗ trợ. Tất cả endpoint phải thuộc cùng một cluster hoặc cùng một cụm endpoint có hợp đồng client tương thích.

Ví dụ cấu hình qua shell trước khi chạy ứng dụng:

~~~bash
export ELASTICSEARCH_URIS=https://elasticsearch.example.com:9200
export ELASTICSEARCH_USERNAME=products-app
export ELASTICSEARCH_PASSWORD="<secret-from-secret-store>"
~~~

Trên Windows PowerShell, biến môi trường của phiên terminal có thể được đặt bằng `$env:ELASTICSEARCH_USERNAME = "products-app"` và `$env:ELASTICSEARCH_PASSWORD = "..."`. Không ghi secret thật vào script dùng chung hoặc lịch sử lệnh có thể bị lưu lại.

Khi Spring Boot đã cấu hình client, các bean Spring Data như repository và `ElasticsearchOperations` sử dụng kết nối đó. Không cần tự thêm header Basic vào từng repository call.

## 5. Cấu hình API key bằng Spring Data Elasticsearch

API key có thể được gửi qua header tùy chỉnh của client. Với Spring Data Elasticsearch 5.x, có thể định nghĩa `ClientConfiguration` và cung cấp header `Authorization` khi cấu hình client.

Ví dụ dưới đây dùng `encoded` value đã nhận từ Elasticsearch. `host-and-port` chỉ chứa hostname và port, không có tiền tố `https://`; `.usingSsl()` chọn HTTPS cho kết nối.

~~~yaml
app:
  elasticsearch:
    host-and-port: ${ELASTICSEARCH_HOST_AND_PORT:elasticsearch.example.com:9200}
    api-key: ${ELASTICSEARCH_API_KEY}
~~~

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.http.HttpHeaders;

@Configuration
public class ProductSearchClientConfiguration extends ElasticsearchConfiguration {

    private final String hostAndPort;
    private final String encodedApiKey;

    public ProductSearchClientConfiguration(
            @Value("${app.elasticsearch.host-and-port}") String hostAndPort,
            @Value("${app.elasticsearch.api-key}") String encodedApiKey) {
        this.hostAndPort = hostAndPort;
        this.encodedApiKey = encodedApiKey;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo(hostAndPort)
                .usingSsl()
                .withHeaders(() -> {
                    HttpHeaders headers = new HttpHeaders();
                    headers.set(HttpHeaders.AUTHORIZATION, "ApiKey " + encodedApiKey);
                    return headers;
                })
                .build();
    }
}
~~~

Trong cấu hình này:

- `ElasticsearchConfiguration` cung cấp cấu hình Spring Data Elasticsearch dựa trên `ClientConfiguration`.
- `connectedTo` nhận địa chỉ host và port của Elasticsearch.
- `usingSsl()` bật TLS cho kết nối HTTPS.
- `withHeaders` cung cấp header cho các HTTP request do client gửi.
- `Authorization` dùng scheme `ApiKey` và giá trị `encoded` đã được Elasticsearch trả về.

Nếu cluster chỉ phục vụ trên HTTP trong một lab local, bỏ `.usingSsl()`. Không bỏ TLS cho cluster từ xa chỉ để tránh lỗi chứng thư; cần cấu hình trust chain đúng ở phía JVM.

Đây là một cách cấu hình client thủ công. Khi dùng cấu hình này, hãy bảo đảm ứng dụng chỉ có một cấu hình client Elasticsearch chủ động và không vô tình tạo thêm client khác với credentials hoặc endpoint khác. Chọn một đường cấu hình nhất quán giữa Spring Boot auto-configuration và cấu hình `ElasticsearchConfiguration`.

## 6. Cấu hình Basic Auth bằng ClientConfiguration

Trong trường hợp muốn tự quản lý client thay vì dùng các thuộc tính auto-configuration của Spring Boot, `ClientConfiguration` cũng hỗ trợ Basic Authentication:

~~~java
import org.springframework.data.elasticsearch.client.ClientConfiguration;

ClientConfiguration clientConfiguration = ClientConfiguration.builder()
        .connectedTo("elasticsearch.example.com:9200")
        .usingSsl()
        .withBasicAuth(username, password)
        .build();
~~~

Đoạn code trên minh họa cách tạo cấu hình; trong ứng dụng thực tế, đặt nó trong cấu hình Spring Data được quản lý bởi Spring container. Lấy `username` và `password` từ secret configuration, không viết cứng trong source code.

Chỉ dùng một cơ chế xác thực cho endpoint, trừ khi gateway có yêu cầu kết hợp cụ thể. Nếu vừa khai báo Basic Auth vừa tự thêm `Authorization: ApiKey ...`, hai cách xác thực có thể xung đột vì một request chỉ nên có một giá trị Authorization phù hợp với server.

## 7. Gửi Bearer token hoặc header tùy chỉnh

`withHeaders` cũng có thể dùng để gửi Bearer token hoặc header do gateway yêu cầu. Ví dụ:

~~~java
import org.springframework.http.HttpHeaders;

ClientConfiguration clientConfiguration = ClientConfiguration.builder()
        .connectedTo("elasticsearch.example.com:9200")
        .usingSsl()
        .withHeaders(() -> {
            HttpHeaders headers = new HttpHeaders();
            headers.setBearerAuth(accessToken);
            headers.set("X-Tenant-ID", tenantId);
            return headers;
        })
        .build();
~~~

Trong ví dụ này, `accessToken` phải là token Bearer do hệ thống xác thực cấp và `tenantId` là giá trị được gateway/backend chấp nhận. Nếu dùng Elasticsearch API key, thay `setBearerAuth(accessToken)` bằng header `Authorization` với scheme `ApiKey` như phần trước.

Header supplier được gọi khi client cần lấy headers cho request. Nếu token có thời hạn ngắn, không giữ một token cố định trong cấu hình suốt vòng đời ứng dụng. Cần tích hợp một token provider có khả năng lấy mới token và xử lý lỗi khi identity provider không sẵn sàng. Không log token trong quá trình refresh hoặc gửi request.

Đối với header `X-API-Key` của gateway, có thể dùng `headers.set("X-API-Key", gatewayKey)`. Điều này chỉ có tác dụng khi gateway thực sự được cấu hình để kiểm tra header đó; Elasticsearch không tự hiểu `X-API-Key` là API key scheme chuẩn của nó.

## 8. Gọi API trực tiếp để kiểm tra credentials

Trước khi kiểm tra repository, có thể xác minh endpoint và credentials bằng curl. Ví dụ API key trên một endpoint HTTPS có CA certificate riêng:

~~~bash
curl --cacert ./http_ca.crt \
  -H "Authorization: ApiKey ${ELASTICSEARCH_API_KEY}" \
  "https://elasticsearch.example.com:9200/_cluster/health?pretty"
~~~

`ELASTICSEARCH_API_KEY` trong ví dụ là giá trị `encoded`, không phải raw `api_key`. File `http_ca.crt` là CA certificate mà client cần tin cậy; tên và vị trí file phụ thuộc cách cluster được triển khai.

Với Basic Authentication:

~~~bash
curl --cacert ./http_ca.crt \
  -u "${ELASTICSEARCH_USERNAME}:${ELASTICSEARCH_PASSWORD}" \
  "https://elasticsearch.example.com:9200/_cluster/health?pretty"
~~~

Với Bearer token:

~~~bash
curl --cacert ./http_ca.crt \
  -H "Authorization: Bearer ${ELASTICSEARCH_ACCESS_TOKEN}" \
  "https://elasticsearch.example.com:9200/_cluster/health?pretty"
~~~

Khi kiểm tra, hãy gọi một API mà credential được cấp quyền sử dụng. API `_cluster/health` có thể yêu cầu quyền cluster nhất định; API key chỉ được cấp quyền index có thể xác thực đúng nhưng vẫn không được phép xem cluster health. Trong trường hợp đó, hãy kiểm tra bằng một API trên index được phép, chẳng hạn `GET /products/_search`.

Không đưa credentials vào query string hoặc URL. URL thường xuất hiện trong access log, proxy log, browser history và công cụ quan sát request.

## 9. TLS và chứng thư số

Credentials chỉ được bảo vệ trên đường truyền khi kết nối sử dụng TLS đúng cách. Với cluster từ xa, dùng `https://` và bảo đảm JVM tin cậy CA đã ký chứng thư server.

Nếu tổ chức cung cấp truststore dạng PKCS12, có thể cấu hình JVM khi chạy ứng dụng:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/path/to/elasticsearch-truststore.p12 \
  -Djavax.net.ssl.trustStorePassword="${TRUSTSTORE_PASSWORD}" \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar application.jar
~~~

Truststore chứa CA hoặc certificate cần thiết để JVM xác minh chứng thư server. Mật khẩu truststore cũng là thông tin nhạy cảm và cần lấy từ secret store hoặc môi trường chạy.

Không tắt certificate validation, hostname verification hoặc dùng trust-all SSL context trong môi trường thật. Những cách đó làm mất khả năng xác minh server và có thể khiến credentials bị gửi tới một endpoint giả mạo.

Trong một số môi trường, client cần truststore hoặc SSL context riêng thay vì truststore toàn JVM. Khi đó cấu hình SSL phải được thực hiện theo phiên bản Spring Data Elasticsearch và HTTP client đang sử dụng; tránh sao chép cấu hình TLS của một phiên bản thư viện khác mà không kiểm tra API tương ứng.

## 10. Quản lý và bảo vệ credentials

Username/password, API key, Bearer token và gateway key đều là secret. Cách quản lý nên đáp ứng các nguyên tắc sau:

- **Không commit secret:** chỉ commit tên biến hoặc placeholder, không commit giá trị thật trong YAML, `.properties`, Docker Compose hay source Java.
- **Tách theo môi trường:** dùng credentials riêng cho local, test, staging và production; không dùng một API key cho nhiều ứng dụng không liên quan.
- **Quyền tối thiểu:** chỉ cấp quyền trên index và thao tác ứng dụng cần.
- **Đặt thời hạn:** API key và access token nên có expiration phù hợp với vòng đời sử dụng.
- **Luân chuyển:** tạo key mới, cập nhật secret ở ứng dụng, xác nhận request hoạt động rồi thu hồi key cũ.
- **Thu hồi khi có sự cố:** nếu secret bị lộ, revoke ngay và kiểm tra log truy cập liên quan.
- **Không ghi log header:** không in `Authorization`, password hoặc token vào log HTTP, exception hay tracing span.
- **Bảo vệ pipeline:** secret của CI/CD phải dùng kho secrets của nền tảng và chỉ cấp cho job cần thiết.

Để luân chuyển API key mà không gây gián đoạn, có thể tạo key mới trong khi key cũ còn hiệu lực, cập nhật secret của ứng dụng, khởi động lại hoặc reload credentials theo thiết kế, xác minh hoạt động rồi xóa key cũ. Nếu client chỉ đọc credentials lúc khởi tạo, cần restart hoặc cơ chế refresh rõ ràng để client dùng key mới.

Không chia sẻ API key qua chat, email, ảnh chụp màn hình hoặc file cấu hình mẫu. Khi cần đưa ví dụ vào tài liệu, thay secret thật bằng placeholder.

## 11. Xử lý lỗi xác thực và kết nối

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `401 Unauthorized` | Thiếu header, sai username/password, API key không hợp lệ, token hết hạn hoặc sai authentication scheme. | Kiểm tra header, secret đang được ứng dụng nạp và loại scheme server yêu cầu. |
| `403 Forbidden` | Xác thực thành công nhưng thiếu quyền trên index hoặc thao tác. | Kiểm tra role của user/API key, index pattern và privilege cần cho thao tác. |
| SSL handshake/certificate error | JVM không tin cậy CA, chứng thư hết hạn hoặc hostname không khớp SAN. | Kiểm tra URL, certificate chain, hostname và truststore. |
| Connection refused/timeout | Sai host/port, firewall, service chưa sẵn sàng hoặc network không định tuyến được. | Kiểm tra endpoint, Docker port mapping, DNS và trạng thái cluster. |
| Request hoạt động bằng curl nhưng lỗi trong Spring | Ứng dụng nạp secret khác, client không dùng cấu hình dự kiến hoặc cấu hình TLS/header chưa đồng nhất. | So sánh endpoint, scheme, truststore và cách tạo client; không in secret để so sánh. |
| API key hoạt động khi đọc nhưng lỗi khi ghi/tạo index | Key chỉ có quyền đọc hoặc thiếu privilege quản lý index. | Cấp đúng privilege cần thiết cho index cụ thể. |

### 11.1. Phân biệt lỗi 401 và 403

`401` thường cho biết server không xác thực được request. Kiểm tra xem client có gửi header hay không, scheme có đúng không, credentials có bị cắt khoảng trắng hoặc nạp nhầm môi trường không, key/token còn hiệu lực không.

`403` thường cho biết server đã nhận diện danh tính nhưng danh tính đó không được phép thực hiện thao tác. Kiểm tra quyền trên index, loại thao tác và các quyền cluster cần thiết. Không giải quyết lỗi `403` bằng cách đổi sang tài khoản superuser; hãy cấp privilege nhỏ nhất đáp ứng use case.

### 11.2. Kiểm tra cấu hình mà không làm lộ secret

Có thể log endpoint, trạng thái TLS, tên profile hoặc việc secret có được nạp hay không. Không log giá trị username/password đầy đủ, API key, access token hoặc nội dung header `Authorization`.

Khi cần xác nhận client đang dùng credentials mới, có thể gọi một endpoint kiểm tra quyền phù hợp và quan sát status code. Nếu cần phân tích sâu hơn, bật log của client ở mức an toàn và cấu hình redaction cho headers trước khi chia sẻ log.

## 12. Chọn phương thức xác thực cho ứng dụng

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Bài thực hành local, Elasticsearch chỉ bind loopback và tắt security | HTTP không credentials, chỉ trong môi trường lab. |
| Ứng dụng nội bộ dùng tài khoản service ổn định | Basic Authentication qua HTTPS, với tài khoản có quyền tối thiểu. |
| Mỗi ứng dụng cần secret riêng, có thể giới hạn quyền và thu hồi độc lập | Elasticsearch API key. |
| Tổ chức dùng OAuth/OIDC hoặc service token | Bearer token với cơ chế cấp và refresh token phù hợp. |
| Elasticsearch nằm sau API gateway có quy ước xác thực riêng | Header do gateway yêu cầu, chẳng hạn `X-API-Key`, qua HTTPS. |

Trong ứng dụng Spring Data Elasticsearch, việc xác thực được cấu hình ở client. Sau khi client gửi đúng endpoint, TLS và header, repository tiếp tục thao tác trên index theo mapping và quyền của danh tính đó. Vì vậy, khi gặp lỗi, hãy tách riêng ba phần để kiểm tra: kết nối mạng, xác thực danh tính và phân quyền thao tác.

## 13. Quy trình cấu hình từ đầu đến cuối

Khi tích hợp một ứng dụng Spring Boot với cluster có security, có thể thực hiện theo trình tự:

1. Xác định endpoint Elasticsearch, port, giao thức HTTP/HTTPS và CA certificate.
2. Xác định phương thức xác thực mà cluster hỗ trợ: Basic, API key, Bearer token hoặc header gateway.
3. Tạo tài khoản hoặc API key riêng cho ứng dụng với quyền tối thiểu trên index cần dùng.
4. Lưu credentials và truststore password trong secret store hoặc biến môi trường của môi trường chạy.
5. Cấu hình Spring Boot properties cho Basic Authentication hoặc tạo `ClientConfiguration` với header khi dùng API key/Bearer/custom header.
6. Kiểm tra kết nối và xác thực bằng một API mà danh tính được phép gọi.
7. Kiểm tra quyền đọc/ghi trên index thực tế bằng thao tác tương ứng.
8. Theo dõi expiration, luân chuyển và thu hồi credentials theo quy trình vận hành.

Khi credentials và header được cấu hình đúng, Spring Data Elasticsearch có thể sử dụng cùng client để thao tác document và index. Tài khoản hoặc API key chỉ nên có đúng quyền ứng dụng cần, còn TLS bảo vệ credentials trên đường truyền và secret management bảo vệ chúng trong suốt vòng đời triển khai.
