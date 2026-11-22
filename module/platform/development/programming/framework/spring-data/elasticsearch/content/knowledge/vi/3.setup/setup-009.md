# Nhận diện lỗi kết nối, chứng chỉ và không tương thích phiên bản

Một ứng dụng Spring Data Elasticsearch có thể biên dịch thành công nhưng vẫn không truy cập được Elasticsearch khi chạy. Nguyên nhân thường nằm ở một trong bốn nhóm: ứng dụng không tới được địa chỉ cluster, TLS không thiết lập được kết nối tin cậy, thông tin xác thực hoặc quyền truy cập không hợp lệ, hay các thành phần client và server không tương thích.

Cách xử lý hiệu quả là xác định lỗi xảy ra ở lớp nào trước khi thay đổi cấu hình. Lỗi DNS không thể sửa bằng cách đổi chứng chỉ; lỗi xác thực HTTP không thể sửa bằng cách nâng phiên bản thư viện; và lỗi NoSuchMethodError thường không liên quan đến mạng.

Bài học này trình bày cách nhận diện từng nhóm lỗi trong ứng dụng Spring Data Elasticsearch, cách thu thập bằng chứng và cách sửa cấu hình theo hướng có thể vận hành an toàn.

## 1. Xác định đường kết nối cần kiểm tra

Trong ứng dụng Spring, code nghiệp vụ thường gọi repository hoặc ElasticsearchOperations. Các lớp Spring Data chuyển thao tác thành request cho Elasticsearch Java API Client hoặc client được cấu hình trong phiên bản dự án. Transport ở dưới chịu trách nhiệm trao đổi HTTP/HTTPS với node Elasticsearch.

Một đường kết nối khái quát:

~~~text
Controller / Service
        |
        v
Spring Data Repository / ElasticsearchOperations
        |
        v
Query và mapping conversion
        |
        v
Elasticsearch Java API Client
        |
        v
HTTP transport + connection pool + TLS
        |
        v
DNS / network / load balancer / proxy
        |
        v
Elasticsearch node hoặc cluster
~~~

Lỗi có thể xuất hiện ở bất kỳ ranh giới nào:

- **Ứng dụng:** cấu hình URI, profile, biến môi trường hoặc dependency chưa được nạp như mong đợi.
- **Mạng:** hostname không phân giải được, port không mở, route hoặc firewall chặn kết nối.
- **TLS:** server certificate không được tin cậy, hostname không khớp, chứng chỉ hết hạn hoặc handshake thất bại.
- **HTTP authentication/authorization:** server trả 401 hoặc 403.
- **Tương thích phần mềm:** Spring Boot, Spring Data Elasticsearch, Java API Client và Elasticsearch server không nằm trong tổ hợp được hỗ trợ.

Trước khi sửa, hãy ghi lại thời điểm lỗi, môi trường đang chạy, endpoint mà ứng dụng thực sự sử dụng, phiên bản các dependency và exception đầy đủ. Một dòng log cuối cùng thường chỉ là lớp bọc của nguyên nhân sâu hơn.

### Phân biệt lỗi lúc khởi động và lỗi lúc gọi API

Có dự án kiểm tra kết nối ngay khi khởi động, có dự án chỉ mở kết nối khi truy vấn đầu tiên được thực hiện. Vì vậy:

- Nếu ứng dụng dừng khi khởi động, xem bean configuration, dependency, SSL context và bước health check.
- Nếu ứng dụng khởi động bình thường nhưng request đầu tiên thất bại, kiểm tra DNS, network, TLS, authentication và endpoint.
- Nếu chỉ một truy vấn cụ thể thất bại, kiểm tra request DSL, mapping, quyền trên index và khả năng tương thích của API được gọi.
- Nếu lỗi xuất hiện sau khi nâng cấp, so sánh dependency tree và phiên bản server trước/sau thay đổi.

Đừng kết luận rằng ứng dụng đã kết nối thành công chỉ vì Spring context khởi động được. Một số client tạo đối tượng mà chưa mở kết nối đến server.

## 2. Kiểm tra địa chỉ, DNS và đường mạng

Ứng dụng cần kết nối đến đúng giao thức, hostname và port của Elasticsearch. Với cluster bật TLS, endpoint thường dùng HTTPS; nếu ứng dụng gọi HTTP đến cổng chỉ nhận HTTPS, server có thể đóng kết nối hoặc trả lỗi giao thức.

Ví dụ cấu hình URI:

~~~properties
spring.elasticsearch.uris=https://es.example.internal:9200
~~~

Đây là địa chỉ minh họa. Trong hệ thống thật, dùng hostname và port do môi trường triển khai cung cấp. Nếu có nhiều node, cấu hình có thể chứa nhiều URI theo cú pháp mà phiên bản Spring Boot đang dùng hỗ trợ.

### Những điểm cần xác nhận

1. Hostname có đúng với môi trường không: local, Docker Compose, Kubernetes, staging hay production?
2. DNS có phân giải hostname từ chính máy/container chạy ứng dụng không?
3. Port có được mở từ network namespace của ứng dụng không?
4. Ứng dụng đang dùng HTTP hay HTTPS đúng với cấu hình node không?
5. Có proxy, load balancer, ingress hoặc service mesh ở giữa không?
6. Endpoint có yêu cầu path prefix hay không?
7. Cluster có đang khởi động, phục hồi hoặc quá tải không?

Một địa chỉ như localhost:9200 có ý nghĩa khác nhau tùy nơi chạy. Bên trong container ứng dụng, localhost trỏ về chính container ứng dụng, không phải container Elasticsearch. Với Docker Compose, thường phải dùng service name trên cùng network; trong Kubernetes, thường dùng DNS của Service.

### Phân biệt các lỗi mạng thường gặp

| Dấu hiệu | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| UnknownHostException | DNS không phân giải được hostname | Kiểm tra DNS, service name và namespace |
| Connection refused | Host tới được nhưng port không nhận kết nối | Kiểm tra port, service, listener và trạng thái node |
| ConnectTimeoutException | Không thiết lập được kết nối trong thời gian cho phép | Kiểm tra firewall, route, endpoint và tải mạng |
| SocketTimeoutException | Kết nối có thể đã được tạo nhưng thao tác chờ quá lâu | Kiểm tra server, query, mạng và socket timeout |
| No route to host | Không có đường mạng tới đích | Kiểm tra route, network policy và firewall |
| Connection reset/closed | Kết nối bị đóng giữa chừng | Kiểm tra protocol, proxy, TLS và log server |

Connect timeout và socket/read timeout biểu thị hai giai đoạn khác nhau. Tăng cả hai lên một giá trị lớn không tự sửa được DNS sai hoặc port bị chặn. Chỉ điều chỉnh timeout sau khi đã xác định thao tác hợp lệ nhưng thời gian chờ hiện tại không phù hợp.

### Kiểm tra endpoint từ đúng môi trường chạy ứng dụng

Chạy lệnh kiểm tra trong cùng máy hoặc container nơi ứng dụng thực sự chạy. Kiểm tra từ laptop của developer không chứng minh pod production có cùng đường mạng.

Với endpoint HTTPS và CA nội bộ, có thể kiểm tra bằng curl:

~~~bash
curl --cacert ./ca.crt https://es.example.internal:9200/
~~~

Nếu endpoint dùng Basic Authentication, có thể cung cấp credential theo cơ chế an toàn của môi trường shell hoặc secret manager. Không ghi mật khẩu trực tiếp vào lịch sử lệnh hoặc tài liệu chia sẻ.

Trên Linux, có thể kiểm tra TLS và chuỗi certificate bằng:

~~~bash
openssl s_client -connect es.example.internal:9200 -servername es.example.internal -showcerts
~~~

Các lệnh trên chỉ kiểm tra đường đi từ môi trường chạy lệnh. Chúng không thay thế việc xác nhận ứng dụng đang nạp đúng cấu hình và trust store.

## 3. Nhận diện lỗi TLS và chứng chỉ

TLS bảo vệ kết nối HTTPS bằng cách xác thực danh tính server và mã hóa dữ liệu trao đổi. Khi client kết nối đến Elasticsearch qua HTTPS, Java phải xây dựng được chuỗi tin cậy từ certificate server tới một CA mà client tin cậy, đồng thời xác minh hostname mà ứng dụng đang gọi.

Một handshake có thể thất bại dù port đã mở và server vẫn hoạt động bình thường.

### Certificate chain và CA trust

Server thường gửi certificate của chính nó cùng các certificate trung gian cần thiết. Client kiểm tra chuỗi đó để xác định certificate có được ký bởi CA đáng tin cậy hay không.

Các khái niệm cần phân biệt:

- **Server certificate:** certificate Elasticsearch trình ra khi nhận kết nối TLS.
- **CA certificate:** certificate của tổ chức phát hành được client tin cậy.
- **Intermediate certificate:** certificate trung gian nối server certificate với CA gốc.
- **Trust store:** nơi Java hoặc SSL context lưu các CA/certificate được tin cậy.
- **Private key:** khóa bí mật đi kèm certificate của server hoặc client; không phải file cần đưa vào trust store của client chỉ để xác minh server.

Nếu Elasticsearch dùng CA nội bộ hoặc certificate tự ký, trust store mặc định của JVM có thể không tin cậy certificate đó. Khi đó, client có thể báo:

~~~text
javax.net.ssl.SSLHandshakeException
sun.security.validator.ValidatorException:
PKIX path building failed
unable to find valid certification path to requested target
~~~

Thông điệp này thường cho biết Java không xây dựng được chuỗi certificate tin cậy. Hãy lấy CA certificate đúng từ quản trị viên hoặc hệ thống cấp phát certificate rồi cấu hình client tin cậy CA đó.

Không nên tải một certificate bất kỳ từ endpoint đang lỗi rồi tự động tin cậy nó mà không xác minh nguồn gốc. Nếu certificate bị thay thế bởi một endpoint giả mạo, thao tác tin cậy mù quáng sẽ làm mất ý nghĩa xác thực TLS.

### Hostname verification và Subject Alternative Name

Tin cậy CA chưa đủ. Certificate còn phải hợp lệ với hostname mà client sử dụng.

Ví dụ ứng dụng kết nối tới:

~~~text
https://es.example.internal:9200
~~~

Certificate server cần có Subject Alternative Name (SAN) phù hợp với es.example.internal. Nếu certificate chỉ có SAN cho localhost hoặc một hostname khác, client có thể từ chối kết nối dù CA đã được tin cậy.

Các trường hợp thường gặp:

- Ứng dụng gọi bằng IP nhưng certificate chỉ chứa DNS name.
- Ứng dụng dùng alias của load balancer nhưng certificate chỉ chứa tên node.
- Certificate được cấp cho domain staging nhưng ứng dụng dùng domain production.
- DNS trỏ tới node khác có certificate không phù hợp.

Cách sửa đúng là sử dụng hostname phù hợp với certificate hoặc cấp certificate có SAN bao phủ hostname mà ứng dụng cần dùng. Không tắt hostname verification để che lỗi này.

### Certificate hết hạn hoặc chưa có hiệu lực

Certificate có khoảng thời gian hiệu lực. Nếu certificate hết hạn hoặc thời gian hệ thống lệch đáng kể, Java có thể từ chối handshake.

Kiểm tra:

- Not Before và Not After của certificate.
- Đồng hồ hệ thống và đồng bộ thời gian NTP trên host/container.
- Certificate đã được thay thế trên tất cả node hoặc load balancer chưa.
- Ứng dụng có đang giữ connection pool cũ sau khi certificate được xoay vòng không.

Khi xoay vòng certificate, cần có kế hoạch cập nhật trust store, reload/restart client phù hợp và xác nhận tất cả endpoint đều trình certificate mới.

### Lỗi TLS khác

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| PKIX path building failed | CA không được tin cậy hoặc thiếu intermediate | Cài đúng CA chain vào trust store |
| No subject alternative DNS name matching | Hostname không nằm trong SAN | Dùng hostname đúng hoặc cấp lại certificate |
| CertificateExpiredException | Certificate hết hạn | Cấp và triển khai certificate mới |
| protocol_version hoặc handshake_failure | TLS version/cipher không giao nhau hoặc cấu hình handshake sai | Đối chiếu chính sách TLS của JVM, proxy và server |
| bad_certificate | Certificate client không hợp lệ trong mTLS hoặc server từ chối certificate | Kiểm tra client certificate, chain và cấu hình mTLS |
| certificate_unknown | Một phía không tin cậy certificate phía kia | Kiểm tra trust store và log handshake ở cả hai phía |

Nếu hệ thống bật mutual TLS (mTLS), client cũng phải trình certificate và chứng minh sở hữu private key tương ứng. Đây là yêu cầu khác với việc client tin cậy server certificate. Hãy xác định cluster chỉ yêu cầu HTTPS thông thường hay yêu cầu cả client certificate.

### Cấu hình trust store cho Java

Một cách triển khai phổ biến là đưa CA certificate vào Java trust store riêng cho ứng dụng. Ví dụ tạo trust store PKCS12 từ CA certificate:

~~~bash
keytool -importcert \
  -alias elasticsearch-ca \
  -file ca.crt \
  -keystore es-truststore.p12 \
  -storetype PKCS12
~~~

Lệnh sẽ yêu cầu mật khẩu trust store và hỏi xác nhận certificate. Chỉ xác nhận sau khi đã kiểm tra fingerprint và nguồn cấp certificate.

Nếu cấu hình JVM sử dụng trust store này, ví dụ:

~~~text
-Djavax.net.ssl.trustStore=/run/secrets/es-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Cách áp dụng chính xác phụ thuộc cách client được tạo. Client có SSL context riêng có thể không sử dụng trust store mặc định của JVM. Trong trường hợp đó, cấu hình SSL context/trust material trực tiếp trên client hoặc dùng cơ chế SSL bundle mà phiên bản Spring Boot hỗ trợ.

Với Spring Boot, nên ưu tiên cơ chế cấu hình SSL bundle và tích hợp client do phiên bản đang dùng cung cấp, nếu có. Tên property và cách liên kết bundle với Elasticsearch REST client thay đổi theo phiên bản Boot; hãy đối chiếu reference documentation của đúng phiên bản thay vì sao chép property từ một dự án khác.

### Ví dụ cấu hình theo ý tưởng với Java

Một cấu hình client có thể biểu diễn các thành phần kết nối, SSL context và Basic Authentication như sau:

~~~java
// Ví dụ khái niệm: cách tạo ClientConfiguration/SSL context
// cụ thể phụ thuộc phiên bản Spring Data Elasticsearch.
ClientConfiguration configuration = ClientConfiguration.builder()
    .connectedTo("es.example.internal:9200")
    .usingSsl(sslContext)
    .withBasicAuth(username, password)
    .build();
~~~

Điểm quan trọng là sslContext phải được tạo từ trust material đã xác minh và có hostname verification phù hợp. Không dùng trust manager chấp nhận mọi certificate trong môi trường thật. API builder thực tế có thể khác giữa các thế hệ client; hãy kiểm tra tài liệu và dependency của dự án.

### Vì sao không nên tắt xác minh SSL?

Một số hướng dẫn thử nghiệm dùng trust all, NoopHostnameVerifier hoặc tùy chọn bỏ qua certificate validation. Chúng có thể làm kết nối chạy được trong một thử nghiệm ngắn, nhưng loại bỏ khả năng xác thực server. Khi đó, client có thể mã hóa dữ liệu tới nhầm endpoint hoặc bên trung gian giả mạo.

Nếu cần xác định nhanh lỗi nằm ở TLS, hãy dùng một công cụ kiểm tra riêng trong môi trường cô lập và chỉ trong thời gian ngắn. Không commit cấu hình bỏ xác minh SSL, không đưa nó vào image triển khai và không coi việc bỏ qua kiểm tra là bản sửa lỗi.

## 4. Phân biệt TLS với Authentication và Authorization

TLS thiết lập kênh giao tiếp an toàn. Sau đó Elasticsearch vẫn có thể yêu cầu ứng dụng xác thực và kiểm tra quyền.

Các trạng thái HTTP thường giúp khoanh vùng:

- 401 Unauthorized: thiếu credential, credential sai, token hết hạn hoặc cơ chế authentication không đúng.
- 403 Forbidden: danh tính đã được xác định nhưng không có quyền thực hiện thao tác.
- Lỗi TLS trước khi nhận HTTP response: chưa đi tới giai đoạn Elasticsearch kiểm tra Basic Auth hoặc quyền index.

Ví dụ cấu hình URI và thông tin đăng nhập được cung cấp từ cấu hình ngoài:

~~~properties
spring.elasticsearch.uris=https://es.example.internal:9200
# Username/password được nạp từ secret manager hoặc biến môi trường.
~~~

Tên property cần được kiểm tra với phiên bản Spring Boot đang dùng. Đưa username/password qua secret manager hoặc biến môi trường do nền tảng quản lý; không ghi mật khẩu vào Git, file cấu hình được chia sẻ hoặc log.

Một tài khoản có thể đăng nhập thành công nhưng vẫn không có quyền tìm kiếm trên index. Hãy kiểm tra role, index privileges và API privilege tương ứng. Đừng cấp quyền cluster-wide rộng hơn mức ứng dụng cần chỉ để làm hết lỗi 403.

### Bảng phân biệt nhanh

| Quan sát | Lớp lỗi có khả năng |
|---|---|
| Không nhận được HTTP status, có SSLHandshakeException | TLS/certificate |
| Không nhận được HTTP status, có UnknownHostException | DNS |
| HTTP 401 | Authentication |
| HTTP 403 | Authorization |
| HTTP 404 cho index hoặc endpoint | Tên index, API path, quyền ẩn danh hoặc API không tồn tại |
| HTTP 400 với query parse error | Request DSL, mapping hoặc API payload |
| HTTP 5xx | Server, cluster, shard hoặc proxy |

HTTP 404 cần đọc response body và log server trước khi kết luận. Elasticsearch có thể trả thông tin khác nhau tùy API, quyền và cấu hình bảo mật.

## 5. Nhận diện không tương thích phiên bản

Spring Data Elasticsearch là một phần của hệ sinh thái Spring Data. Ứng dụng còn phụ thuộc Spring Boot, Spring Framework, Elasticsearch Java API Client và Elasticsearch server. Các thành phần này phát triển theo những nhịp phát hành khác nhau, nên không thể chỉ nhìn một con số phiên bản rồi đoán toàn bộ tổ hợp có tương thích hay không.

Một cấu hình điển hình có các lớp:

| Thành phần | Vai trò |
|---|---|
| Spring Boot | Quản lý cấu hình và dependency mặc định của ứng dụng |
| Spring Data Elasticsearch | Repository abstraction, mapping và operations |
| Elasticsearch Java API Client (elasticsearch-java) | API Java và kiểu request/response |
| HTTP transport/REST client | Gửi request qua HTTP/HTTPS |
| Elasticsearch server | Nhận và thực thi API trên cluster |

Ngoài ra, ứng dụng có thể còn dependency từ thư viện khác kéo vào một phiên bản Elasticsearch client khác. Đây là lý do cần xem dependency tree của runtime thay vì chỉ đọc build.gradle hoặc pom.xml.

### Kiểm tra ma trận tương thích

Khi chọn phiên bản, hãy đối chiếu tài liệu tương thích chính thức của Spring Data Elasticsearch và Elasticsearch cho đúng release train đang dùng. Cần kiểm tra ít nhất:

1. Phiên bản Spring Boot đang chạy.
2. Phiên bản Spring Data Elasticsearch do Boot quản lý hoặc được khai báo riêng.
3. Phiên bản elasticsearch-java thực sự nằm trong runtime classpath.
4. Phiên bản Elasticsearch server của cluster.
5. Phiên bản Java runtime mà các thư viện yêu cầu.

Không nên giả định mọi phiên bản client mới đều tương thích với mọi server cũ, hoặc nâng riêng elasticsearch-java là đủ. Spring Data có thể phụ thuộc vào kiểu dữ liệu và API của một phiên bản Java client cụ thể.

### Ưu tiên dependency management của Spring Boot

Trong ứng dụng Spring Boot, dependency management của Boot thường chọn các phiên bản Spring Data và thư viện liên quan đã được kiểm tra cùng nhau. Nếu không có yêu cầu đặc biệt, nên giữ bộ phiên bản được quản lý này.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'
}
~~~

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>
~~~

Không cần tự thêm một phiên bản elasticsearch-java tùy ý nếu starter đã quản lý dependency tương ứng. Nếu cần override, hãy xác nhận phiên bản đó nằm trong tổ hợp được hỗ trợ và kiểm tra cả các dependency bắc cầu.

### Tránh trộn client thuộc các thế hệ khác nhau

Các dự án cũ có thể dùng RestHighLevelClient; các dự án hiện đại dùng Elasticsearch Java API Client. Đây là những API và mô hình cấu hình khác nhau.

Các dấu hiệu trộn client hoặc dependency:

- Code import class từ org.elasticsearch.client.RestHighLevelClient trong khi cấu hình chỉ tạo Java API Client.
- Runtime có đồng thời nhiều thế hệ elasticsearch-rest-client hoặc các module Elasticsearch với phiên bản lệch nhau.
- Một thư viện kéo phiên bản client cũ vào runtime.
- Spring Data được nâng cấp nhưng cấu hình client custom vẫn dùng API đã bị loại bỏ hoặc thay đổi.
- Code biên dịch với một dependency graph nhưng ứng dụng chạy bằng classpath khác.

Không nên giữ cả hai thế hệ client chỉ vì một phần code cũ chưa được chuyển đổi. Nếu cần migration, xác định phạm vi sử dụng từng client, lập kế hoạch chuyển đổi và loại bỏ dependency cũ khi không còn caller.

### Các lỗi thường thấy khi lệch dependency

| Exception hoặc dấu hiệu | Ý nghĩa thường gặp |
|---|---|
| ClassNotFoundException | Class không có trong runtime classpath |
| NoClassDefFoundError | Class từng được biên dịch tham chiếu nhưng runtime không nạp được |
| NoSuchMethodError | Class tồn tại nhưng phiên bản runtime không có method mà code/thư viện mong đợi |
| NoSuchFieldError | Field không tồn tại trong phiên bản class đang được nạp |
| AbstractMethodError | Implementation không còn khớp với interface/abstract class runtime |
| Lỗi compile với package co.elastic.clients... | Java API Client thiếu hoặc phiên bản không có API được gọi |
| HTTP 400 báo API parameter không hỗ trợ | Request dùng tính năng hoặc tham số không phù hợp với server |
| Response parse/deserialization error | Client và server có khác biệt về schema/API response hoặc dữ liệu không như mong đợi |

NoSuchMethodError thường là bằng chứng mạnh về binary incompatibility trong classpath. Tăng timeout hoặc đổi URI sẽ không giải quyết được lỗi đó.

### Kiểm tra dependency tree

Với Gradle, xem dependency Elasticsearch trong runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để xem lý do một phiên bản được chọn:

~~~bash
./gradlew dependencyInsight \
  --dependency elasticsearch-java \
  --configuration runtimeClasspath
~~~

Có thể kiểm tra riêng spring-data-elasticsearch, elasticsearch-rest-client và các module liên quan. Với Maven:

~~~bash
mvn dependency:tree
~~~

Tập trung vào phiên bản cuối cùng được resolve, nguồn dependency kéo nó vào và các dòng bị conflict/omitted. Dependency khai báo trực tiếp không nhất thiết là phiên bản runtime được chọn.

### Xác nhận phiên bản server

Có thể truy vấn root endpoint của cluster:

~~~http
GET /
~~~

Response thường chứa trường version.number, cùng tên cluster và tên node. Ghi lại phiên bản thực tế từ đúng endpoint mà ứng dụng kết nối. Trong cluster qua load balancer hoặc nhiều node, cũng cần xác nhận các node cùng phiên bản trong quá trình rolling upgrade theo chính sách hỗ trợ.

Nếu ứng dụng dùng một Elasticsearch service được quản lý, hãy lấy phiên bản và giới hạn API từ thông tin của nhà cung cấp.

## 6. Kiểm tra cấu hình Spring Boot và profile

Một lỗi phổ biến là file cấu hình đúng nhưng ứng dụng đang chạy với profile khác hoặc biến môi trường ghi đè giá trị.

Ví dụ cấu hình:

~~~yaml
spring:
  elasticsearch:
    uris: https://es.example.internal:9200
    connection-timeout: 2s
    socket-timeout: 10s
~~~

Các tên property ở ví dụ cần đối chiếu với phiên bản Boot thực tế. Tùy release, cách cấu hình SSL bundle, transport và custom client có thể khác. Username và password nên được nạp từ nguồn cấu hình bí mật bên ngoài.

Hãy xác minh:

- Profile nào đang active.
- URI cuối cùng sau khi resolve placeholder.
- Biến môi trường có tồn tại trong process/container không.
- Có cấu hình Java custom nào ghi đè auto-configuration không.
- Có nhiều bean client/operations cùng tồn tại không.
- Secret mount có đúng path và quyền đọc không.
- Ứng dụng đang chạy image/build mới nhất hay vẫn dùng artifact cũ.

Không in mật khẩu, private key hoặc nội dung secret ra log để kiểm tra. Có thể log hostname, port, scheme, profile, phiên bản client và trạng thái đã cấu hình credential mà không tiết lộ giá trị bí mật.

### Khi dùng custom configuration

Nếu dự án tự tạo client, hãy xác định bean nào được inject vào ElasticsearchOperations và repository. Cấu hình URI ở application.yml có thể không tác động tới client tự tạo.

Đọc wiring của các bean:

- Client được tạo ở đâu?
- SSL context lấy trust material từ đâu?
- Basic Auth/API key được gắn ở tầng nào?
- Bean operations sử dụng client nào?
- Có @Primary hoặc qualifier khiến service nhận nhầm bean không?

Chỉ thay đổi một nguồn cấu hình sau khi đã biết bean nào đang được sử dụng. Nếu có hai cấu hình cạnh tranh, sửa file properties có thể không thay đổi hành vi runtime.

## 7. Quy trình chẩn đoán theo thứ tự

Dùng quy trình sau để tránh thay đổi nhiều biến cùng lúc.

### Bước 1: Thu thập bằng chứng

Ghi nhận exception đầy đủ, nested cause, HTTP status và response body nếu có. Ghi nhận endpoint, scheme, profile, phiên bản Java, Spring Boot, Spring Data Elasticsearch, Java client và Elasticsearch server.

Không đưa credential, access token, private key hoặc dữ liệu document nhạy cảm vào log chia sẻ.

### Bước 2: Xác nhận DNS và TCP

Từ đúng môi trường chạy ứng dụng, xác minh hostname phân giải được và port có thể kết nối. Nếu thất bại ở bước này, xử lý DNS, route, firewall, service discovery hoặc endpoint trước khi xem certificate.

### Bước 3: Xác nhận TLS

Nếu endpoint là HTTPS, kiểm tra certificate chain, CA trust, SAN/hostname, thời hạn certificate và chính sách TLS. Dùng CA đúng nguồn và giữ hostname verification bật.

### Bước 4: Xác nhận HTTP authentication

Khi đã thiết lập được TLS, kiểm tra 401 và 403 riêng biệt. Xác minh credential, token, role và quyền index/cluster.

### Bước 5: Xác nhận phiên bản và dependency

Đọc dependency tree runtime, đối chiếu compatibility matrix và kiểm tra phiên bản server. Xử lý classpath conflict trước khi thay đổi code query.

### Bước 6: Kiểm tra request Elasticsearch

Nếu kết nối và client đều hoạt động nhưng một query thất bại, xem request DSL, endpoint, mapping và API support. Một lỗi 400 parse query khác hoàn toàn với lỗi TLS hoặc binary incompatibility.

### Bước 7: Kiểm tra lại bằng một thao tác tối thiểu

Sau khi sửa, thử một request nhẹ tới cluster hoặc một truy vấn đơn giản trên index kiểm thử. Tiếp đó mới thử query nghiệp vụ có sort, aggregation, highlight hoặc phân trang.

## 8. Bảng chẩn đoán tổng hợp

| Triệu chứng | Lớp cần kiểm tra đầu tiên | Bằng chứng nên lấy |
|---|---|---|
| UnknownHostException | DNS/service discovery | Hostname và kết quả phân giải từ container |
| Connection refused | Port/listener | Endpoint, port, trạng thái service |
| Connect timeout | Network/firewall/route | Kết quả kiểm tra TCP từ runtime |
| PKIX path building failed | CA trust chain | Server chain, CA fingerprint, trust store |
| Hostname mismatch | SAN/hostname verification | Hostname ứng dụng gọi và SAN certificate |
| Certificate expired | Certificate lifecycle/time | Validity period và đồng hồ hệ thống |
| TLS protocol/handshake failure | TLS policy | JVM version, TLS/cipher policy, server/proxy logs |
| HTTP 401 | Authentication | Cơ chế auth và trạng thái credential |
| HTTP 403 | Authorization | Role và index privileges |
| NoSuchMethodError | Runtime dependency conflict | Dependency tree và classpath thực tế |
| ClassNotFoundException | Thiếu dependency | Runtime classpath, packaging |
| HTTP 400 parse error | Query/API/mapping | Request body, server version, mapping |
| HTTP 5xx hoặc shard failure | Elasticsearch cluster | Cluster health, shard state, server logs |

Bảng này giúp chọn nơi điều tra đầu tiên. Một triệu chứng có thể có nhiều nguyên nhân; luôn xác nhận bằng exception gốc và log ở phía server.

## 9. Ví dụ tình huống thực tế

### Tình huống A: Ứng dụng trong container không kết nối được localhost:9200

Log:

~~~text
java.net.ConnectException: Connection refused
~~~

Ứng dụng chạy trong container riêng, Elasticsearch chạy ở container khác. localhost trỏ về container ứng dụng nên kết nối đi nhầm đích.

Cách xử lý:

1. Xác định Docker network mà hai container cùng tham gia.
2. Dùng service name và port nội bộ của Elasticsearch trong URI.
3. Xác nhận Elasticsearch lắng nghe trên interface phù hợp.
4. Kiểm tra lại kết nối từ container ứng dụng.

### Tình huống B: HTTPS báo PKIX path building failed

Ứng dụng kết nối được host và port nhưng Java không tin cậy CA đã ký certificate của Elasticsearch.

Cách xử lý:

1. Nhận CA certificate từ nguồn quản trị đáng tin cậy.
2. Xác minh fingerprint hoặc chuỗi phát hành.
3. Đưa CA vào trust store/SSL bundle được client sử dụng.
4. Xác nhận trust store đó thực sự được nạp trong runtime.
5. Kết nối lại và giữ hostname verification bật.

Nếu sau khi thêm CA xuất hiện lỗi hostname mismatch, đó là bước xác minh riêng: kiểm tra SAN và hostname trong URI.

### Tình huống C: Kết nối TLS thành công nhưng server trả 401

TLS đã tạo được kênh HTTPS, nhưng Elasticsearch không chấp nhận credential hoặc client không gửi credential như dự kiến.

Cách xử lý:

1. Xác minh cơ chế authentication cluster yêu cầu.
2. Kiểm tra username/password hoặc API key qua secret manager.
3. Kiểm tra cấu hình custom client có gắn credential không.
4. Xác nhận ứng dụng đang dùng đúng profile và bean client.
5. Không đưa secret vào log để tìm lỗi.

Nếu response là 403, kiểm tra quyền của principal trên index và API thay vì đổi mật khẩu liên tục.

### Tình huống D: Sau khi nâng dependency xuất hiện NoSuchMethodError

Ứng dụng biên dịch được nhưng runtime nạp một phiên bản class khác với phiên bản mà thư viện gọi đã được biên dịch cùng.

Cách xử lý:

1. Lấy dependency tree của runtimeClasspath.
2. Tìm dependency kéo phiên bản Elasticsearch client không mong muốn.
3. Đối chiếu phiên bản Spring Boot/Spring Data/client được hỗ trợ.
4. Bỏ override hoặc khóa phiên bản ở mức tương thích.
5. Clean build và triển khai artifact mới.
6. Kiểm tra lại classpath trong môi trường chạy thật.

### Tình huống E: Kết nối được nhưng query trả HTTP 400

Client và transport đã gửi request tới server. Vấn đề có thể nằm ở cú pháp Query DSL, field không tồn tại, kiểu field không đúng hoặc tham số API không được server hỗ trợ.

Cách xử lý:

1. Thu thập request body thực tế.
2. Chạy request trong Dev Tools trên đúng cluster.
3. Kiểm tra mapping của field.
4. Đối chiếu API parameter với phiên bản server.
5. Sửa query hoặc nâng cấp theo compatibility matrix nếu cần.

## 10. Nguyên tắc vận hành và bảo mật

**Quản lý certificate như một phần của vòng đời triển khai.** Theo dõi ngày hết hạn, nơi phát hành, SAN, CA chain và lịch xoay vòng. Cập nhật trust material đồng bộ với thay đổi certificate của server.

**Không tắt TLS verification trong production.** Giữ xác minh CA và hostname. Không dùng trust-all manager hoặc hostname verifier bỏ qua kiểm tra.

**Bảo vệ secret.** Lưu password, API key, trust store password và private key trong secret manager hoặc cơ chế quản lý secret của nền tảng. Không commit vào repository và không ghi ra log.

**Giữ dependency đồng bộ.** Ưu tiên dependency management của Spring Boot và kiểm tra ma trận tương thích trước khi override hoặc nâng riêng một module.

**Đặt timeout có chủ đích.** Connect timeout kiểm soát thời gian thiết lập kết nối; socket/read timeout kiểm soát thời gian chờ phản hồi. Giá trị cần dựa trên latency thực tế và SLA của ứng dụng.

**Quan sát lỗi ở cả hai phía.** Log client giúp biết request thất bại ở đâu; log Elasticsearch và proxy giúp xác định server đã nhận request hay chưa. Dùng request ID hoặc correlation ID khi nền tảng hỗ trợ để ghép các log.

**Kiểm tra lại sau khi triển khai.** Xác minh ứng dụng đang dùng đúng URI, certificate, secret và dependency của release mới. Một cấu hình local chạy được chưa đủ để kết luận container hoặc production có cùng trust store và network.

## 11. Checklist xử lý một sự cố kết nối

Khi nhận được báo lỗi từ môi trường chạy, có thể đi theo danh sách sau:

- [ ] Ghi lại exception gốc và toàn bộ chuỗi Caused by.
- [ ] Xác nhận URI thực tế: scheme, hostname, port và path prefix.
- [ ] Xác nhận DNS và TCP từ đúng container/host.
- [ ] Nếu HTTPS, kiểm tra chain, CA, SAN, thời hạn và TLS policy.
- [ ] Xác nhận authentication trả 401 hay authorization trả 403.
- [ ] Ghi lại phiên bản Spring Boot, Spring Data, Java client và server.
- [ ] Kiểm tra dependency tree của runtimeClasspath.
- [ ] Xác nhận bean client/operations đang được sử dụng.
- [ ] Chạy thử request tối thiểu và đọc response body.
- [ ] Kiểm tra lại sau khi triển khai, không chỉ trên máy phát triển.

Mỗi bước loại trừ một lớp nguyên nhân. Khi biết request dừng ở DNS, TCP, TLS, HTTP authentication, API parsing hay runtime linkage, ta có thể sửa đúng cấu hình hoặc dependency gây ra sự cố.

