# Làm mới chứng chỉ và thông tin xác thực khi ứng dụng đang chạy

Trong một hệ thống microservices dùng **Spring Cloud LoadBalancer**, Order Service gọi Inventory Service bằng URI logic như **https://inventory-service/api/stock/BOOK-01**. LoadBalancer chọn một **ServiceInstance** (ví dụ inventory-a.internal:8443), còn HTTP transport thực hiện TLS handshake và lớp bảo mật gắn token hoặc credential phù hợp cho lời gọi. Sau khi ứng dụng đã chạy nhiều ngày, **chứng chỉ TLS, trust anchor, khóa riêng, OAuth2 access token, client secret hoặc API key** có thể hết hạn hay phải thu hồi. Nếu client chỉ đọc chúng lúc khởi động, ứng dụng có thể tiếp tục dùng giá trị cũ dù kho bí mật đã được cập nhật.

**Làm mới khi ứng dụng đang chạy** (runtime rotation/hot reload) là quá trình cấp phát, kiểm chứng và chuyển sang vật liệu bảo mật mới mà không buộc toàn bộ hệ thống dừng phục vụ. Điều đó không có nghĩa chỉ cần ghi đè một file: thành phần đang giữ **SSLContext, connection pool, HTTP client, OAuth2AuthorizedClient, interceptor hoặc secret snapshot** cũng phải thực sự sử dụng phiên bản mới.

Bài học phân tích riêng **TLS/mTLS rotation** và **credential/token rotation**, chỉ ra ranh giới của Spring Cloud LoadBalancer, cách quản lý RestClient, RestTemplate, WebClient, OpenFeign, tích hợp Secret volumes, Spring Boot SSL bundles/Spring Cloud refresh, chuyển đổi an toàn theo hai pha, kiểm thử sau rotation, giám sát và rollback.

**Phạm vi:** ví dụ dùng Spring Boot 3.x/4.x, Spring Framework/Spring Security và Spring Cloud release train tương thích. Tên package và khả năng reload có thể khác giữa phiên bản. Không suy diễn rằng một cấu hình được hỗ trợ trên web server inbound sẽ tự động áp dụng cho **mọi outbound HTTP connector**. Những URL, domain, certificate path và client registration trong bài chỉ là minh họa.

## 1. Có những loại thông tin cần luân chuyển nào?

| Vật liệu bảo mật | Được dùng để làm gì? | Khi thay đổi, cần cập nhật ở đâu? |
| --- | --- | --- |
| **Server TLS certificate + private key** | Inventory chứng minh danh tính server | TLS server connector trên Inventory |
| **CA/truststore** | Order tin cậy certificate chain của Inventory | TrustManager/SSLContext của HTTP client Order |
| **Client certificate + private key (mTLS)** | Order chứng minh danh tính với Inventory | KeyManager/SSLContext của HTTP client Order |
| **OAuth2 access token** | Gửi Bearer authorization mỗi request | Authorized client/token cache và HTTP interceptor/filter |
| **OAuth2 refresh token** | Đổi access token khi grant cho phép | Authorized client manager/store |
| **OAuth2 client secret** | Xác thực ứng dụng tại Authorization Server | ClientRegistration/credentials của token client |
| **API key** | Xác thực với downstream cụ thể | Secret provider và interceptor được dùng mỗi request |
| **Service-to-service signing key** | Ký/kiểm chứng request hoặc JWT | Key provider, JWKS/verifier và hợp đồng key ID |
| **Trust policy/revocation state** | Đánh giá certificate/key đã bị thu hồi | Trust validation, CRL/OCSP/policy theo transport |

Không gom mọi thứ thành biến **token**: access token thường ngắn hạn và có cơ chế cấp lại; client secret hoặc private key lại là credential dài hạn hơn, đòi hỏi luân chuyển an toàn qua kho bí mật. Cập nhật access token **không** thay thế việc cập nhật certificate mTLS, và ngược lại.

### 1.1. Ba chiều của rotation

Một thay đổi có thể cần đồng bộ ba nơi:

1. **Nguồn bí mật:** Secret Manager, Kubernetes Secret, Vault, PKI/CA hoặc Authorization Server.
2. **Ứng dụng/HTTP client:** file watcher, authorized client store, credential provider, TLS context, HTTP connection manager.
3. **Bên xác minh:** downstream server/trust policy, token issuer, JWKS hoặc hệ thống chấp nhận key mới.

Nếu chỉ thay nguồn bí mật mà không làm mới client, request vẫn dùng cũ. Nếu client chuyển sang credential mới trước khi downstream chấp nhận, lỗi có thể bùng phát. Nếu thu hồi cũ quá sớm, các connection hoặc token còn sống có thể mất quyền sử dụng ngay lập tức.

## 2. Spring Cloud LoadBalancer nằm ở đâu trong chuỗi bảo mật?

~~~mermaid
flowchart TD
    A["Order gọi https://inventory-service/api/..."] --> B["@LoadBalanced RestClient/WebClient/Feign"]
    B --> C["LoadBalancer chọn ServiceInstance"]
    C --> D["Tái dựng URI host:port/scheme thực tế"]
    D --> E["HTTP connector + connection pool"]
    E --> F["TLS handshake: cert/trust/mTLS"]
    F --> G["HTTP headers: Bearer token/API key"]
    G --> H["Inventory xác thực và phân quyền"]
    H --> I["Response / retry / metrics"]
    J["Secret Store / PKI / OAuth2"] --> K["Credential provider + TLS context manager"]
    K --> E
    K --> G
~~~

Spring Cloud LoadBalancer có nhiệm vụ **tìm và chọn đích**, không phải phát hành certificate, cấp access token, thay truststore hay bảo đảm token được refresh. URI logic có thể dùng service ID, nhưng TLS được thực hiện đối với **hostname của URI kết nối cuối cùng**, dưới sự kiểm soát của HTTP engine.

Phân chia trách nhiệm:

| Thành phần | Trách nhiệm | Không nên kỳ vọng |
| --- | --- | --- |
| ServiceInstanceListSupplier | Danh sách instance từ discovery/cache/health/zone/hint | Cấp token, reload certificate |
| RoundRobin/Random LoadBalancer | Chọn instance | Xác minh CA hoặc phân quyền |
| LoadBalancer interceptor/filter | Tái dựng request URI | Xóa toàn bộ credential cũ khỏi pool |
| HTTP client/SSLContext | TLS/mTLS, trust validation, kết nối | Biết khi nào một OAuth2 token hết hạn |
| OAuth2AuthorizedClientManager | Lấy/cấp lại token theo provider đã cấu hình | Thay client secret/mTLS tự động khi file đổi |
| Secret provider | Phân phối credential hiện hành | Bảo đảm client đã dùng phiên bản mới |
| Backend resource server | Kiểm tra token, scope, audience, mTLS policy | Biết vì sao LoadBalancer chọn instance A |

**Dấu hiệu cần debug:** sau rotation, request đến A thành công nhưng đến B bị 401 hoặc TLS handshake error. Có thể A và B đang ở **khác thế hệ certificate/trust policy hoặc token validator**, không phải thuật toán Round Robin bị lỗi.

## 3. TLS one-way và mTLS khác nhau ở việc phải refresh

### TLS một chiều

~~~text
Order (client) ─── TLS ───> Inventory (server)
        xác minh Inventory certificate bằng trust anchors
~~~

Khi Inventory thay server certificate, Order cần có **trust chain** tương thích và hostname validation vẫn đúng. Nếu cùng CA và certificate hợp lệ theo cùng hostname, client có thể tiếp tục tin cậy mà không phải đổi truststore. Nếu CA/root/intermediate thay đổi, cần quản lý **trust rollover**.

### mTLS (mutual TLS)

~~~text
Order (client cert + private key)
      ─── TLS xác minh hai chiều ───>
Inventory (server cert + private key)
~~~

Ngoài việc Order tin Inventory, **Inventory cũng xác minh client certificate của Order**. Khi client certificate của Order hết hạn hoặc bị thu hồi, chỉ cập nhật truststore phía Order là không đủ: phải thay **key material được KeyManager dùng cho handshake mới** và bảo đảm Inventory đã tin CA/client identity mới.

### 3.1. Vòng đời một kết nối đang mở

TLS certificate/private key thường được chọn và xác minh **khi bắt đầu TLS handshake**. Một connection keep-alive đang mở **không tự handshake lại trên mỗi HTTP request**; HTTP/2 còn có thể gửi nhiều streams trên cùng connection.

Do đó, ngay sau khi nạp vật liệu mới:

- **Connection cũ** có thể tiếp tục hoạt động bằng phiên TLS đã thiết lập, tùy chính sách server/transport.
- **Connection mới** phải dùng trust/key material mới nếu TLS context của HTTP client đã được cập nhật.
- **Pool cũ** có thể vẫn giữ socket hoặc SSLContext đã chụp từ cấu hình cũ.
- Việc đổi file certificate **không chứng minh** tất cả outbound requests đã dùng chứng chỉ mới.

Nếu cần buộc chuyển thế hệ certificate, hãy **đổi HTTP client/pool có kiểm soát**, ngừng cho mượn connection cũ, đợi drain request đang chạy và đóng tài nguyên theo deadline. Đóng toàn bộ pool ngay lập tức có thể làm hỏng những request còn in-flight.

## 4. Hostname validation/SNI khi LoadBalancer tái dựng URI

Giả sử code:

~~~text
https://inventory-service/api/stock
~~~

LoadBalancer chọn:

~~~text
instance-a.internal:8443
~~~

HTTP engine có thể kết nối tới:

~~~text
https://instance-a.internal:8443/api/stock
~~~

Với TLS, **certificate hostname verification** phải phù hợp với danh tính endpoint mà client kiểm tra theo cấu hình thực tế. Nếu certificate chỉ chứa DNS SAN **inventory-service** nhưng URI cuối lại có host **instance-a.internal**, handshake hoặc bước hostname verification có thể thất bại. Nếu endpoint được lựa chọn theo IP, certificate cũng phải phù hợp với **IP SAN** hoặc dùng một cơ chế hostname/SNI đáng tin cậy đã được thiết kế riêng.

Không “sửa nhanh” bằng:

- tắt certificate verification;
- dùng **trust-all TrustManager**;
- tắt hostname verification;
- chấp nhận mọi SNI hoặc tự gửi header Host giả để qua TLS;
- tự động redirect bearer token sang một host chưa được phê duyệt.

**Thiết kế đúng:** thống nhất service discovery, URI rewrite, DNS, certificate SAN, ingress/mesh topology và chính sách mTLS. Với service mesh, TLS có thể kết thúc tại sidecar/proxy thay vì trong Java client; khi đó cần biết lớp nào thực sự sở hữu certificate rotation.

## 5. Hai pha để xoay CA/trust mà không gây gián đoạn

Khi đổi Certificate Authority (CA), chuyển đồng thời mọi phía bằng một lần thay thế có thể làm các instance “chia phe”: caller chỉ tin CA mới, còn một số server vẫn dùng chain cũ.

Chiến lược **expand → migrate → contract**:

~~~mermaid
flowchart LR
    A["Pha 0: Chỉ CA cũ"] --> B["Pha 1: Trust CA cũ + CA mới"]
    B --> C["Pha 2: Chuyển server/client cert sang CA mới"]
    C --> D["Xác minh mọi instance, pool và handshake mới"]
    D --> E["Pha 3: Loại CA cũ sau khi an toàn"]
~~~

| Pha | Caller truststore | Backend certificate | Mục tiêu |
| --- | --- | --- | --- |
| 0 | CA-old | CA-old | Trạng thái ban đầu |
| 1 | CA-old + CA-new | CA-old | Chuẩn bị không làm mất tin cậy hiện tại |
| 2 | CA-old + CA-new | Dần chuyển sang CA-new | Rollout có overlap |
| 3 | CA-new | CA-new ở mọi instance | Thu hẹp trust sau khi kiểm chứng |

Với **mTLS**, phải thực hiện tương tự ở chiều còn lại: server trust store của Inventory chấp nhận client CA cũ và mới trong giai đoạn quá độ, rồi mới chuyển client cert của Order. Nếu certificate mới chứa danh tính mới hoặc scope khác, cần cập nhật authorization policy đồng bộ trước.

**Thời gian overlap** cần đủ cho: propagation của Secret, reload của tiến trình, connection draining, retry, rollout đa zone và clock skew. Không cố định “5 phút luôn đủ”; phải dựa trên độ trễ phân phối/connection lifetime trong môi trường thực.

### 5.1. Phân biệt certificate renewal và compromise response

Khi chứng chỉ sắp hết hạn, overlap là phương án giảm lỗi hợp lý. Nhưng khi **private key bị lộ**, tiếp tục chấp nhận CA/key cũ lâu để tránh gián đoạn có thể nguy hiểm. Cần theo quy trình incident: cô lập credential, thu hồi nhanh, chặn việc sử dụng ngoài ý muốn và chấp nhận một số gián đoạn có kiểm soát nếu cần. **Availability không được đánh đổi bằng cách giữ khóa đã bị compromise**.

## 6. Spring Boot SSL bundles: cấu hình và giới hạn reload

Spring Boot cho phép khai báo **SSL bundle** có tên để quản lý trust/key material. Có thể dùng PEM hoặc JKS/PKCS12 và áp dụng bundle tới những thành phần hỗ trợ.

### 6.1. PEM bundle cho server TLS

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-server:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/tls/server/tls.crt"
            private-key: "file:/etc/tls/server/tls.key"
server:
  port: 8443
  ssl:
    bundle: inventory-server
~~~

Spring Boot có file watcher cho bundle hỗ trợ **reload-on-update**, với quiet period có thể cấu hình:

~~~yaml
spring:
  ssl:
    bundle:
      watch:
        file:
          quiet-period: 2s
~~~

**Điều kiện:** khả năng reload phụ thuộc **component tiêu thụ SSL bundle**. Trong tài liệu Spring Boot hiện hành, các consumer được liệt kê hỗ trợ reload là **Tomcat web server và Netty web server**. Không suy rộng thuộc tính trên thành khẳng định RestClient, WebClient, Apache HC5, Reactor Netty **outbound client**, Feign hoặc mọi database connection sẽ tự thay TLS context sau khi file thay đổi.

Chứng chỉ server vừa reload chỉ có tác dụng với các **TLS handshakes mới** theo thực thi của connector; connection hiện hữu và các phần mềm reverse proxy/mesh ngoài JVM có thể có lifecycle riêng.

### 6.2. Trust bundle cho outbound caller

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-trust:
          truststore:
            certificate: "file:/etc/tls/client/inventory-ca.pem"
~~~

Spring Boot cung cấp **SslBundles** và các helper SSL cho RestClient/WebClient trong những phiên bản phù hợp. Ví dụ cấu hình SSL trên RestClient.Builder:

~~~java
@Bean
RestClient directInventoryRestClient(
        RestClient.Builder builder, RestClientSsl ssl) {
    return builder
            .baseUrl("https://inventory.example.internal")
            .apply(ssl.fromBundle("inventory-trust"))
            .build();
}
~~~

**Đây là ví dụ sử dụng SSL bundle khi xây dựng client, chưa phải hot-reload outbound client.** Package của RestClientSsl thay đổi giữa Spring Boot 3.x và 4.x; phải dùng import tương thích BOM. Nếu muốn gọi qua service ID với Spring Cloud LoadBalancer, cần builder **@LoadBalanced** và certificate/SAN phù hợp sau URI rewrite.

Nếu cần runtime trust rotation ở outbound client, phải xác minh:

1. Consumer HTTP client thực tế có theo dõi bundle update hay không.
2. SSLContext/TrustManager có được tái tạo sau update hay vẫn bị giữ từ startup.
3. Connection pool có đang phát connection mới bằng TLS context mới không.
4. Đường code RestClient/RestTemplate/Feign/WebClient đang dùng có bị thay bởi client khác sau refresh không.

**SslBundles tạo vật liệu cấu hình; TLS engine và pool mới là nơi quyết định có dùng phiên bản mới ở handshake kế tiếp.**

## 7. Kubernetes Secrets: file có thể đổi nhưng ứng dụng vẫn dùng giá trị cũ

Kubernetes hỗ trợ mount Secret thành file trong container. Khi Secret được cập nhật, dữ liệu trong volume thường được **cập nhật theo cơ chế eventual consistency** (độ trễ phụ thuộc kubelet sync và cache/watch). Điều này phù hợp với một quy trình rotation dựa trên file:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order
          image: example/order-service:1.0
          volumeMounts:
            - name: inventory-credentials
              mountPath: /etc/inventory-credentials
              readOnly: true
      volumes:
        - name: inventory-credentials
          secret:
            secretName: inventory-client-tls
~~~

Trong ví dụ, secret chứa các file liên quan như client.crt, client.key hoặc ca.crt. Đường dẫn trong ứng dụng trỏ đến **file trong volume**, không phải một bản copy vào classpath/JAR.

### 7.1. Hai cạm bẫy quan trọng

- **Mount qua subPath không tự nhận update Secret**: Kubernetes tài liệu hóa rõ giới hạn này. Đừng mount từng certificate file qua subPath rồi kỳ vọng watcher phát hiện thay đổi.
- **Giá trị Secret đưa qua environment variable** được nạp khi container/process bắt đầu; thay Secret không tự thay giá trị biến môi trường của JVM đang chạy. Nếu chọn mô hình env var, thường phải **rolling restart** để lấy phiên bản mới.

Với volume được cập nhật, thư viện Java vẫn phải **reopen file, reload trust/key material và đưa vào client thực**. Một SSLContext được tạo từ file vào startup không liên tục đọc lại file đó.

### 7.2. Tránh đọc cặp certificate/key không đồng bộ

Secret volume có thể dùng symlink và thay đổi nguyên tử ở cấp snapshot, nhưng ứng dụng tự đọc **client.crt trước rồi client.key sau** đúng lúc filesystem chuyển snapshot có thể tạo cặp không khớp nhau. Chiến lược an toàn:

1. Dùng secret material có **generation/version** rõ.
2. Đọc certificate và private key từ **cùng một snapshot** khi có thể.
3. Kiểm tra private key có khớp public key của certificate.
4. Kiểm tra chain, EKU, SAN, thời hạn và chính sách trust.
5. Chỉ publish generation mới khi toàn bộ bộ vật liệu hợp lệ.

Kubernetes có các loại projected volumes khác, bao gồm nguồn credential/certificate tùy phiên bản cluster; không mặc định mọi cluster đều có các tính năng mới nhất. Với Kubernetes projected pod certificate, tài liệu cũng khuyến nghị đọc credential bundle cùng một snapshot để tránh certificate/key bị lệch.

### 7.3. Giới hạn quyền truy cập file

Không đặt private key vào ConfigMap công khai, git repository, Docker image hoặc log. Dùng RBAC tối thiểu cho Secret, filesystem permission hạn chế, mã hóa secret at rest theo policy và secret provider chuyên dụng khi cần. Đối với mTLS private key, nên hạn chế quyền đọc vào đúng process cần ký handshake.

## 8. Spring Cloud refresh khác với xoay TLS context

Spring Cloud có **@RefreshScope**, rebind ConfigurationProperties và actuator **/actuator/refresh**. Những cơ chế này có thể giúp ứng dụng nạp giá trị cấu hình mới mà không restart toàn bộ process.

Ví dụ một bean đọc thông tin secret từ configuration:

~~~java
@ConfigurationProperties(prefix = "inventory.auth")
public record InventoryAuthProperties(String apiKey) {}
~~~

**Không giả định record immutable sẽ được refresh bằng rebind**: Spring Cloud tài liệu hóa constructor-bound ConfigurationProperties (bao gồm Java record) không thể được refresh theo kiểu rebind thông thường. Nếu muốn sử dụng cấu hình động, hãy chọn chiến lược cụ thể như một bean **@RefreshScope** được tạo lại hoặc credential provider quản lý snapshot riêng.

### 8.1. @RefreshScope không làm mọi đối tượng phụ thuộc tự thay đổi

~~~java
@RefreshScope
@Component
class ApiKeySettings {
    private final String apiKey;

    ApiKeySettings(Environment environment) {
        this.apiKey = environment.getRequiredProperty(
                "inventory.auth.api-key");
    }

    String current() {
        return apiKey;
    }
}
~~~

Spring Cloud có thể làm mới target của proxy khi refresh scope cache bị invalidated. Nhưng nếu một HTTP interceptor đã **copy chuỗi API key vào field riêng** lúc khởi tạo, nó vẫn giữ giá trị cũ. Thiết kế đúng là interceptor **lấy snapshot mới mỗi request** hoặc HTTP client/interceptor được tạo lại và được thay thế an toàn.

### 8.2. Refresh endpoint là quyền quản trị nhạy cảm

Không public **/actuator/refresh**, **/actuator/env** hoặc khả năng POST cập nhật Environment ra internet/mesh rộng. Spring Cloud yêu cầu cấu hình exposure nếu muốn dùng endpoint; cần bảo vệ bằng authentication, authorization, network policy, audit và secret hygiene.

Một refresh sai có thể làm mất auth, thay truststore sang giá trị không hợp lệ hoặc kích hoạt tạo lại nhiều HTTP clients đang có traffic. Không dùng refresh endpoint như một endpoint nghiệp vụ cho tất cả caller tự gọi.

**Lưu ý:** Spring Cloud Context Refresh không được hỗ trợ trong một số mô hình AOT/native image; tài liệu yêu cầu tắt refresh tương ứng. Nếu chạy native image, cần lựa chọn credential provider hoặc rolling restart theo hỗ trợ thực tế.

### 8.3. Khi nào rolling restart tốt hơn hot reload?

Rolling restart thường dễ kiểm chứng hơn nếu:

- HTTP client/transport không hỗ trợ thay SSLContext trong runtime.
- Secret được nạp từ environment variables.
- Đội ngũ chưa có cơ chế atomic swap và drain connection an toàn.
- Chính sách bảo mật yêu cầu trạng thái client sau rotation hoàn toàn xác định.

Đây không phải thất bại của “zero downtime”: **rolling deployment có readiness/liveness, đủ replicas và graceful shutdown** có thể giữ service phục vụ bình thường trong khi từng pod được thay phiên. Hot reload nên được chọn khi có yêu cầu và test rõ ràng, không phải vì muốn tránh mọi restart bằng mọi giá.

## 9. Quy trình TLS rotation an toàn cho outbound HTTP client

Một luồng rotation nên diễn ra như sau:

~~~mermaid
flowchart TD
    A["Secret/PKI phát hành generation N+1"] --> B["Phân phối files/trust material"]
    B --> C["Reader phát hiện bản mới"]
    C --> D["Đọc đầy đủ + validate cert/key/chain"]
    D --> E{"Hợp lệ?"}
    E -->|Không| F["Giữ N, báo lỗi và alert"]
    E -->|Có| G["Tạo SSLContext + HTTP client/pool thế hệ N+1"]
    G --> H["Canary handshake bằng credential mới"]
    H --> I{"Đúng identity/trust?"}
    I -->|Không| F
    I -->|Có| J["Atomic swap new client for new requests"]
    J --> K["Drain in-flight requests thế hệ N"]
    K --> L["Đóng pool N theo deadline"]
    L --> M["Metrics: activeGeneration=N+1"]
~~~

### 9.1. Tại sao cần tạo cả TLS context và pool mới?

Các HTTP engines thường xây **SSLContext/TrustManager/KeyManager** lúc cấu hình connector hoặc tạo connection. Một số engine hỗ trợ dynamic material update, nhưng không có hợp đồng chung rằng mọi context/pool đều cập nhật khi file thay đổi.

Phương án có tính xác định cao là:

1. Dựng **client generation mới** với vật liệu TLS mới.
2. Chạy thử **một TLS handshake mới** đến endpoint test phù hợp.
3. **Atomic swap** con trỏ tới client mới cho requests mới.
4. Cho requests in-flight trên client cũ hoàn thành hoặc hết deadline.
5. Ngừng lease connection cũ và đóng pool generation cũ.

Cách này áp dụng về mặt kiến trúc cho **RestClient + Apache HC5**, **RestTemplate**, **WebClient + Reactor Netty** hoặc transport của **OpenFeign**, nhưng **cách đóng/drain tài nguyên khác nhau**. Không lấy một phương thức close() của Apache HC5 rồi áp cho Reactor Netty/Feign.

### 9.2. Pseudocode của atomic swap

~~~java
// PSEUDOCODE: ClientGeneration và factory là abstractions do ứng dụng tạo.
final class OutboundClientRouter {

    private final AtomicReference<ClientGeneration> active;

    OutboundClientRouter(ClientGeneration initial) {
        this.active = new AtomicReference<>(initial);
    }

    Mono<StockResponse> getStock(String sku) {
        // Capture generation khi có subscription nếu dùng Reactive streams.
        return Mono.defer(() -> {
            ClientGeneration generation = active.get();
            return generation.acquireAndCall(sku)
                    .doFinally(signal -> generation.release());
        });
    }

    void publishRotation(ClientGeneration verifiedNewGeneration) {
        ClientGeneration previous =
                active.getAndSet(verifiedNewGeneration);
        previous.stopAcceptingNewRequests();
        previous.closeAfterInFlightDrain();
    }
}
~~~

**Đây không phải đoạn code hoàn chỉnh có thể biên dịch**: các lớp/method ClientGeneration, acquireAndCall(), release(), drain và reference counting do ứng dụng tự thiết kế. Nó minh họa **không thay đổi trực tiếp SSLContext của một client đang chạy request**. Thêm nữa, stopAcceptingNewRequests()/closeAfterInFlightDrain() phải bảo đảm atomicity giữa đọc generation và tăng in-flight reference count; nếu không, có race khiến một request mới nhận generation cũ vừa bị đóng.

Đặc biệt với reactive:

- Một Mono cold có thể subscribe **sau khi** phương thức getStock() trả về. Phải capture client generation ở subscription hoặc giữ lease hợp lệ.
- Mỗi generation có thể có in-flight streams SSE/NDJSON dài. Phải có **max drain duration** và chính sách đóng stream phù hợp.
- Concurrency và memory visibility phải được kiểm thử với requests đồng thời, không chỉ chạy tuần tự.

### 9.3. Định nghĩa thế nào là rotation thành công

Không chỉ báo success khi watcher nhìn thấy file mới. Một rotation được coi là thành công khi:

- Vật liệu mới hợp lệ và không hết hạn.
- HTTP client generation mới đã được publish.
- **Connection mới** xác minh đúng server cert hoặc client cert identity.
- Lời gọi qua **service ID** vẫn giữ đúng zone/hint/routing.
- Các requests mới sử dụng generation mới.
- Requests cũ drain/đóng trong giới hạn.
- Lỗi TLS/401/403 không tăng bất thường.

Nếu một bước thất bại, giữ generation cũ khi còn an toàn, báo alert và kích hoạt rollback/quy trình incident. **Không tự fallback sang trust-all** để “cho request chạy tạm”.

## 10. Cấu hình cho RestClient, RestTemplate và Apache HC5

Spring Boot có thể cung cấp **RestClientSsl** và builder phù hợp để đọc bundle khi khởi tạo. Với Apache HttpClient 5, TLS handling thường đi qua connection manager/SSL strategy/trust configuration của Apache.

Điều cần xác minh:

| Đối tượng | Nếu được tạo một lần lúc startup | Khi certificate đổi |
| --- | --- | --- |
| RestClient | Có thể giữ request factory từ startup | Không mặc định tự tạo lại |
| RestTemplate | Giữ request factory/interceptors | Không mặc định tự tạo lại |
| Apache HC5 CloseableHttpClient | Có pool/manager | Cần quyết định cách thay manager/TLS material |
| Pool active connections | Có TLS session đã thiết lập | Tiếp tục/đóng theo drain policy |
| TLS trust material | Có thể đã được chụp vào SSLContext/manager | Cần xác minh cơ chế refresh hoặc thay generation |

### 10.1. Không chỉ đặt @RefreshScope lên RestClient.Builder

Ví dụ sai về giả định:

~~~java
@Service
class InventoryClient {
    private final RestClient client;

    InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://inventory-service")
                .build();
    }
}
~~~

Nếu refresh builder bean sau đó, **client đã build và lưu vào final field** của InventoryClient không mặc định được thay. Muốn hot-reload client vật lý phải:

- đặt đúng **client/adapter** trong refresh boundary và chứng minh lifecycle resource được quản lý; hoặc
- dùng một **routing/delegating client** lấy generation hiện hành; hoặc
- rolling restart.

Với request factory Apache HC5, cần đóng connection manager cũ **sau** drain, không dùng một factory đã đóng cho request mới.

### 10.2. Token rotation không nhất thiết cần thay RestClient object

Nếu RestClient gắn một interceptor đọc token mới **mỗi request**, Access Token có thể thay đổi mà không phải tạo lại SSLContext/pool:

~~~java
@Bean
RestClient inventoryClient(
        RestClient.Builder builder,
        CurrentTokenProvider tokenProvider) {
    return builder
            .baseUrl("https://inventory.example.internal")
            .requestInterceptor((request, body, execution) -> {
                String token = tokenProvider.getValidToken();
                request.getHeaders().setBearerAuth(token);
                return execution.execute(request, body);
            })
            .build();
}
~~~

**CurrentTokenProvider** là abstraction của ứng dụng; phải quản lý expiry, đồng bộ refresh, retry an toàn và tránh rò rỉ token. Đoạn này minh họa **gắn token tại thời điểm request**, không phải cơ chế triển khai OAuth2 hoàn chỉnh.

Nếu cùng một RestClient được sử dụng để gọi **nhiều host ngoài** phạm vi Inventory, interceptor trên có thể gửi nhầm token. Nên dùng dedicated client cho đúng downstream/audience, kiểm tra redirect policy và không sao chép Authorization qua domain khác.

## 11. WebClient và Reactor Netty: TLS context khác token filter

Với **WebClient**, SSL/TLS của kết nối thường do **ClientHttpConnector**, ví dụ **ReactorClientHttpConnector** gắn với **Reactor Netty HttpClient**, chịu trách nhiệm. Một **ExchangeFilterFunction** có thể bổ sung token HTTP trên mỗi request.

Hai cơ chế vận hành ở các lớp khác nhau:

~~~text
WebClient request
  |
  +-- ExchangeFilterFunction cấp Bearer token cho HTTP header
  |
  +-- ReactorLoadBalancerExchangeFilterFunction chọn instance
  |
  +-- ReactorClientHttpConnector
       |
       +-- HttpClient/ConnectionProvider: TLS context + connections
       +-- SSL handshake khi mở socket mới
~~~

Đổi Bearer token **thường không cần đóng TCP pool**. Ngược lại, đổi **client mTLS private key** thường cần bảo đảm connector tạo những handshake mới bằng identity mới. Với pooled connections, chỉ thay file chưa đủ.

### 11.1. SSL bundle được áp dụng khi xây WebClient

Spring Boot có helper **WebClientSsl**, cho phép:

~~~java
@Bean
WebClient directInventoryWebClient(
        WebClient.Builder builder,
        WebClientSsl ssl) {
    return builder
            .baseUrl("https://inventory.example.internal")
            .apply(ssl.fromBundle("inventory-trust"))
            .build();
}
~~~

Đoạn này sử dụng SSL bundle khi **tạo WebClient**; muốn xoay trust/key material lúc runtime cần xác minh connector/consumer thực sự cập nhật. Không mặc định helper từ Boot tự thay SSL context trong pool đang tồn tại. Package của **WebClientSsl** thay đổi theo dòng Spring Boot; cần import đúng phiên bản.

Nếu cần gọi theo **https://inventory-service**, sử dụng **@LoadBalanced WebClient.Builder** và một integration test xác minh URI vật lý/SAN/hostname verification còn phù hợp.

### 11.2. Reactor Netty client generation

Mẫu thiết kế cho outbound mTLS:

~~~text
generation 17:
  SslContext(old certificate/key/trust)
  HttpClient(old SSL configuration)
  ConnectionProvider(old pool)
  WebClient(old connector)

generation 18:
  SslContext(new certificate/key/trust)
  HttpClient(new SSL configuration)
  ConnectionProvider(new pool)
  WebClient(new connector)
~~~

Sau khi test generation 18 thành công, routing adapter chuyển request mới sang WebClient 18. Pool 17 được drain/close theo lifecycle và grace period.

**Lưu ý về Reactor Netty resources:** HttpClient, ConnectionProvider và LoopResources có thể dùng tài nguyên toàn cục/chia sẻ. Không gọi dispose() bừa lên tài nguyên toàn cục vì có thể ảnh hưởng WebClient khác. Nên sở hữu rõ **mỗi pool do ứng dụng tạo** và giới hạn close đúng phạm vi.

### 11.3. Reactive không có nghĩa rotation tự atomic

Với WebClient:

- Tạo Mono không có nghĩa request đã bắt đầu.
- Subscription sau khi swap mới là thời điểm nên chọn client generation.
- Hủy request khi drain có thể kết thúc HTTP stream hoặc ngắt hoạt động backend, nhưng **không rollback side effect đã xảy ra**.
- Một operation retry có thể vô tình đi qua **hai certificate generations** nếu lấy client mới ở mỗi attempt. Điều đó cần được định nghĩa và kiểm thử, đặc biệt khi downstream policy đang đổi.

Không đổi SSL context giữa chừng trong cùng một TLS session. TLS handshake xác định identity của connection; nếu cần chắc chắn request mới sử dụng credential mới, phải kiểm tra connection acquisition và lifecycle pool.

## 12. OpenFeign: thay credential theo RequestInterceptor, TLS theo HTTP engine

OpenFeign trong Spring Cloud thường sử dụng **FeignBlockingLoadBalancerClient** để chọn ServiceInstance. TLS được thực thi bởi HTTP client bên dưới như **Apache HttpClient 5**, **OkHttp** hoặc client khác.

Ví dụ một API key provider được gọi **ở mỗi request**:

~~~java
interface RotatingApiKeyProvider {
    String currentKey();
}

@Configuration(proxyBeanMethods = false)
class InventoryFeignAuthConfiguration {

    @Bean
    RequestInterceptor inventoryApiKeyInterceptor(
            RotatingApiKeyProvider provider) {
        return template ->
                template.header("X-Inventory-Api-Key", provider.currentKey());
    }
}

@FeignClient(
        name = "inventory-service",
        configuration = InventoryFeignAuthConfiguration.class)
interface InventoryFeignClient {
    @GetMapping("/api/stock/{sku}")
    StockResponse stock(@PathVariable("sku") String sku);
}
~~~

**Chỉ minh họa API key**, không phải mẫu OAuth2 chuẩn. Trong production, class InventoryFeignAuthConfiguration phải được giới hạn **đúng named client**; nếu bị component scan như một global Feign configuration, interceptor có thể gắn API key Inventory vào request của **Feign client khác**. Đặt cấu hình ngoài vùng scan toàn cục hoặc áp dụng cách cô lập config phù hợp.

### 12.1. Thay API key khác với thay mTLS certificate

- **API key**: nếu provider trả giá trị mới, Feign RequestInterceptor có thể thêm header mới ở request tiếp theo, không cần tái tạo pool.
- **OAuth2 bearer**: cần authorized client manager xử lý expiry, scopes, audience và token store.
- **mTLS certificate/trust**: nằm ở Feign underlying HTTP engine, thường cần cấu hình lại client/connection manager và drain, hoặc rolling restart.

Đừng chỉ refresh một Feign RequestInterceptor bean rồi kỳ vọng **SSL socket** đổi certificate; đây là hai tầng khác nhau.

### 12.2. Timeout/retry khi thông tin xác thực đổi

Feign, Spring Cloud LoadBalancer và reverse proxy có thể có retry policy riêng. Khi server trả **401/403**, đừng mặc định retry liên tục với cùng credential cũ:

- 401 có thể do token hết hạn, key bị thu hồi, issuer/audience sai hoặc clock skew.
- 403 có thể do scope/policy không phù hợp, thường không sửa bằng refresh token.
- Nếu cần refresh access token sau 401, chỉ làm **một quy trình có giới hạn** và bảo đảm request body có thể gửi lại an toàn.
- POST tạo reservation/thanh toán có thể đã có side effect; việc retry cần idempotency.

Một token mới không đồng nghĩa endpoint sẽ cho phép cùng scope hoặc quyền. Rotation thành công phải kiểm tra **authorization outcome**, không chỉ việc token khác giá trị.

## 13. OAuth2 access token, refresh token và client secret có vòng đời khác nhau

Đối với **OAuth2 client_credentials**, ứng dụng dùng client ID/secret (hoặc phương thức client authentication khác) để **yêu cầu access token mới** khi cần. Grant này thường không phát refresh token theo cách authorization_code; access token hết hạn thì gọi Token Endpoint để lấy token mới theo chính sách provider.

Đối với **authorization_code + refresh_token**, authorized client manager có thể đổi một access token đã hết hạn bằng refresh token nếu provider được cấu hình và token hợp lệ. **Không tự triển khai vòng lặp “401 → refresh vô hạn → replay”**.

### 13.1. Spring Security RestClient OAuth2

Spring Security hỗ trợ **OAuth2ClientHttpRequestInterceptor** kết hợp **OAuth2AuthorizedClientManager**:

~~~java
@Bean
RestClient securedInventoryRestClient(
        RestClient.Builder builder,
        OAuth2AuthorizedClientManager manager) {

    OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(manager);

    oauth2.setClientRegistrationIdResolver(
            request -> "inventory-client");

    return builder
            .baseUrl("https://inventory.example.internal")
            .requestInterceptor(oauth2)
            .build();
}
~~~

Đoạn code minh họa cách **ủy quyền cấp/cấp lại token cho Spring Security**, không tự hardcode Bearer token. Trong backend service-to-service với client_credentials, cần cấu hình **ClientRegistrationRepository, OAuth2AuthorizedClientManager/provider và principal scope** phù hợp; một manager mặc định dựa trên user đang đăng nhập có thể không thích hợp cho scheduled job.

**Không nhầm:** interceptor có thể lấy token mới khi token cũ hết hạn, nhưng nếu **client secret của OAuth2 client registration** thay đổi ở kho bí mật, manager/repository/token HTTP client đang giữ cấu hình cũ có thể vẫn gửi client secret cũ. Rotation **client secret** phải cập nhật **ClientRegistration** hoặc tạo generation mới của auth client và làm sạch cache theo chính sách.

### 13.2. Spring Security WebClient OAuth2

Đối với reactive application, Spring Security cung cấp **ServerOAuth2AuthorizedClientExchangeFilterFunction** cùng **ReactiveOAuth2AuthorizedClientManager**:

~~~java
@Bean
WebClient securedInventoryWebClient(
        WebClient.Builder builder,
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
    oauth2.setDefaultClientRegistrationId("inventory-client");

    return builder
            .baseUrl("https://inventory.example.internal")
            .filter(oauth2)
            .build();
}
~~~

Đây là mẫu cho **backend-specific client**, không phải cách gắn token mặc định lên mọi WebClient trong ứng dụng. Tài liệu Spring Security cảnh báo việc đặt default authorized client quá rộng có thể gửi access token tới những URL không mong muốn.

Muốn kết hợp với Spring Cloud LoadBalancer, dùng builder được cấu hình **@LoadBalanced** và test filter chain. Việc OAuth2 filter tự gọi Authorization Server cần một HTTP client/đích riêng, không tạo vòng phụ thuộc vào chính service ID Inventory.

### 13.3. Cache và ngưỡng làm mới token

Giả sử:

~~~text
access_token.expires_at = 12:00:00
clock_skew             = 30 giây
request bắt đầu        = 11:59:40
~~~

Nếu một downstream call có thể mất 45 giây, token được chọn ở 11:59:40 **có thể hết hạn trước khi backend xác minh**. Một authorized client provider thường có clock skew và chính sách cấp mới trước expiry; phải cấu hình cho đúng thời gian mạng/clock skew của môi trường.

Không lưu token mãi trong một field final, không cache theo key thiếu audience/scope/tenant hoặc dùng chung authorized client giữa các principal không tương đương. Ngược lại, không gọi Token Endpoint ở **mọi request** nếu token vẫn còn hợp lệ, vì dễ gây tải và race.

### 13.4. Chống “thundering herd” lúc token hết hạn

Nhiều request cùng lúc phát hiện token hết hạn có thể đồng thời gọi Authorization Server. Một credential provider nên:

- Có cache theo client registration và principal/audience/scope phù hợp.
- Dùng **single-flight refresh** hoặc đồng bộ phù hợp để tránh hàng trăm refresh trùng nhau.
- Có timeout, retries giới hạn và circuit-breaker/bulkhead cho **Token Endpoint** riêng.
- Không dùng token đã hết hạn vô hạn khi Authorization Server lỗi.
- Không ghi access token/refresh token/client secret ra log/metrics.

Trong trường hợp rotation key tại Authorization Server, đồng bộ thời gian phát hành token mới với khả năng resource servers xác minh JWT/JWKS mới. Đổi client secret và đổi JWT signing key là **hai quy trình khác nhau**.

## 14. API key rotation: cập nhật snapshot an toàn giữa nhiều thread

Với hệ thống đang dùng API key thay vì OAuth2, nguyên tắc cốt lõi là **không chụp API key vào interceptor khi khởi tạo**.

Ví dụ **không hỗ trợ runtime rotation**:

~~~java
String apiKeyAtStartup = secretProvider.readKey();

RestClient client = RestClient.builder()
        .defaultHeader("X-Inventory-Api-Key", apiKeyAtStartup)
        .build();
~~~

Nếu secretProvider có giá trị mới sau 10 phút, RestClient trên vẫn giữ giá trị cũ. Đừng sửa bằng cách mutate default headers của singleton client từ thread khác.

### 14.1. Một provider đọc snapshot mỗi request

~~~java
final class RotatingApiKeyProvider {
    private final AtomicReference<String> current =
            new AtomicReference<>();

    RotatingApiKeyProvider(String initial) {
        publish(initial);
    }

    String currentKey() {
        String key = current.get();
        if (key == null) {
            throw new IllegalStateException("No active API key");
        }
        return key;
    }

    void publish(String validatedNewKey) {
        if (validatedNewKey == null || validatedNewKey.isBlank()) {
            throw new IllegalArgumentException("Invalid API key");
        }
        current.set(validatedNewKey);
    }
}
~~~

Đây là **mẫu dữ liệu minh họa**, không phải credential store production. Trong thực tế:

- Không dùng **isBlank()** làm bước xác minh duy nhất; cần kiểm tra key ID/version, policy và thử xác thực qua endpoint test.
- Nạp secret từ provider đã xác thực, không từ header do client bên ngoài gửi.
- Không in key vào exception/log; chỉ log **generation ID** không nhạy cảm.
- Java String không bảo đảm bộ nhớ chứa secret được xóa ngay sau khi thay; với yêu cầu bảo mật cao, cân nhắc key handle/HSM/credential library và vòng đời phù hợp.
- Có thể cần API key overlap: server chấp nhận cả cũ/mới trong thời gian chuyển đổi và chỉ thu hồi cũ khi mọi caller đã cập nhật.

### 14.2. Mẫu WebClient filter lấy key tại mỗi subscription

~~~java
ExchangeFilterFunction apiKeyFilter = (request, next) ->
        Mono.defer(() -> {
            ClientRequest updated = ClientRequest.from(request)
                    .headers(headers -> headers.set(
                            "X-Inventory-Api-Key",
                            rotatingApiKeyProvider.currentKey()))
                    .build();
            return next.exchange(updated);
        });

WebClient client = webClientBuilder
        .baseUrl("https://inventory-service")
        .filter(apiKeyFilter)
        .build();
~~~

**rotatingApiKeyProvider** là bean đã tạo từ ví dụ tương ứng; **webClientBuilder** cần được cấu hình **@LoadBalanced** nếu sử dụng host là service ID. Mono.defer giúp giá trị key được lấy **khi request được subscribe**, phù hợp với mô hình cold Publisher.

Không sử dụng một global filter gắn API key Inventory cho các downstream khác. Mỗi key phải có đúng **audience/host/service scope** và quyền tối thiểu. Không gửi header bí mật vào redirect sang host không tin cậy.

### 14.3. Không dùng refresh để “phục hồi” token đã bị thu hồi

Khi API key cũ bị thu hồi ở server, request bằng giá trị cũ có thể nhận 401/403. Điều cần làm là **nhận version mới đã được phân phối** hoặc fail closed nếu chưa có, không tự tạo fallback sang key chưa được cấp phép hay gửi lại vô hạn.

Nếu server hỗ trợ giai đoạn chấp nhận hai key, nên chuyển tất cả callers sang key mới trước khi thu hồi cũ. Nếu phát hiện lộ key, thu hồi nhanh và mở quy trình khắc phục theo chính sách security incident.

## 15. Thứ tự rotation mTLS và HTTP credential theo môi trường

Không có một thứ tự thay đổi duy nhất cho mọi hệ thống. Nhưng nên đánh giá hai trục:

1. **Transport identity:** TLS certificate/trust, SAN, mTLS client cert.
2. **Application identity:** Bearer token, API key, OAuth2 scopes và audience.

Kịch bản ví dụ:

~~~text
Inventory hiện tại:
    server cert CA-old
    chấp nhận client cert CA-client-old
    chấp nhận token issuer/key-old

Order hiện tại:
    trust CA-old
    client cert CA-client-old
    token do issuer/key-old cấp
~~~

Khi đổi cả PKI và OAuth2:

1. Phân phối trust anchors mới cho cả hai chiều **trước** khi đổi certificates.
2. Cho resource servers chấp nhận **JWT signing keys mới** (và cũ trong thời gian overlap, nếu chính sách cho phép).
3. Phát hành server/client certificates mới và triển khai theo canary.
4. Bảo đảm OAuth2 client registrations/token managers có credentials mới.
5. Chuyển outbound client generation; test new TLS handshake + Bearer authorization.
6. Theo dõi **mTLS handshake failures** tách khỏi 401/403 (application auth).
7. Thu hồi vật liệu cũ sau khi hết overlap, đã drain đủ và đạt tiêu chí bảo mật.

Trong sự kiện security incident, quy trình có thể buộc **thu hồi ngay** thay vì giữ overlap. Cần runbook riêng cho chứng chỉ hết hạn thông thường và credential bị compromise.

### 15.1. JWT/JWKS rotation có hai chiều riêng

- **Issuer/Auth Server:** tạo signing key mới, công bố public key với key ID (kid), bắt đầu ký token mới, giữ key cũ đủ để xác minh token còn sống khi chính sách cho phép.
- **Resource server:** cập nhật JWKS/verifier cache để nhận key mới trước khi issuer phát token mới, theo cache TTL/refresh behavior của framework.

Không trộn việc cập nhật **JWKS của resource server** với việc nạp **mTLS truststore của HTTP client**. Chúng có thể đều là public keys nhưng có trách nhiệm xác minh khác nhau.

### 15.2. Clock skew và thời gian hiệu lực

NTP/clock skew ảnh hưởng cả certificate validity (notBefore/notAfter) và OAuth2/JWT nbf/exp. Nếu instance A có đồng hồ lệch vài phút còn B chính xác, client có thể quan sát lỗi theo Round Robin dù cùng credential. Cần theo dõi đồng bộ thời gian và có chính sách skew phù hợp, không tắt kiểm tra expiration để che lỗi.

## 16. Cân bằng tải trong giai đoạn rotation: tránh nửa cụm ở chính sách cũ

Spring Cloud LoadBalancer có thể chọn **bất kỳ ServiceInstance hợp lệ** sau discovery/cache/zone/hint. Nếu từng instance Inventory được rollout certificate hoặc auth policy lệch nhau, request có thể:

~~~text
Request 1: LB chọn A -> TLS OK, HTTP 200
Request 2: LB chọn B -> TLS handshake failed
Request 3: LB chọn C -> TLS OK, HTTP 401
Request 4: LB chọn A -> HTTP 200
~~~

Không tự sửa bằng tăng retry vô hạn. Một lần thử lại có thể qua instance khác và vô tình che lỗi trong canary, làm phần trăm lỗi khó đo. Cần:

- Kiểm chứng riêng **A/B/C** bằng TLS handshake và request auth trên mỗi thế hệ.
- Ghi **service ID, instance ID, zone, certificate generation** vào telemetry an toàn.
- Đảm bảo publisher/registry/health phản ánh readiness thực của backend mới.
- Dùng **canary/rolling rollout** trước khi loại bỏ CA/key cũ.
- Giới hạn retries; **không retry 401/403 mù** như timeout/503.

Nếu cần tạm ngừng chọn một instance chưa đạt policy, hãy thay readiness/health hoặc metadata/routing có kiểm soát. **ZonePreference** không phải cơ chế chứng thực mTLS; một hint header không được coi là bằng chứng identity.

### 16.1. Service ID khác physical TLS identity

Trong logs, phân biệt:

~~~text
logicalServiceId = inventory-service
selectedInstance = inventory-b
physicalHost     = inventory-b.internal
tlsPeerIdentity  = certificate SAN/subject đã xác minh
httpAuthAudience = inventory-api
credentialGen    = token-key-2026-11
~~~

Không ghi token value, private key, certificate bytes hoặc client secret. Có thể log fingerprint **của certificate công khai** khi chính sách cho phép, nhưng nó không thay thế verification chain/hostname và có thể có thông tin hạ tầng nhạy cảm.

### 16.2. Retry và credential rotation

Một logical request có thể gồm hai attempts ở hai thế hệ:

~~~text
Attempt 1 (generation N):
    TCP/TLS OK -> HTTP 401 vì token hết hạn

Credential provider nhận token mới hoặc generation N+1 đã publish

Attempt 2 (generation N+1):
    TLS OK -> HTTP 200
~~~

Chỉ cho phép một nhánh retry này **nếu OAuth2 provider và application contract hỗ trợ**; tránh replay một POST có side effect nếu không có idempotency. Nếu retry ở Spring Cloud LoadBalancer và OAuth2 filter lại tự retry, số attempts có thể nhân lên.

## 17. Kiểm thử đơn vị: chứng minh header đã thực sự đổi

Một test dùng WebClient với ExchangeFunction giả có thể xác nhận **giá trị header** được đọc lại sau publish:

~~~java
@Test
void usesCurrentApiKeyOnEachSubscription() {
    RotatingApiKeyProvider provider =
            new RotatingApiKeyProvider("key-generation-1");

    List<String> observed = new CopyOnWriteArrayList<>();

    ExchangeFunction fake = request -> {
        observed.add(request.headers()
                .getFirst("X-Inventory-Api-Key"));
        return Mono.just(ClientResponse.create(HttpStatus.OK)
                .body("ok")
                .build());
    };

    ExchangeFilterFunction rotating = (request, next) ->
            Mono.defer(() -> {
                ClientRequest updated = ClientRequest.from(request)
                        .headers(headers -> headers.set(
                                "X-Inventory-Api-Key",
                                provider.currentKey()))
                        .build();
                return next.exchange(updated);
            });

    WebClient client = WebClient.builder()
            .exchangeFunction(fake)
            .filter(rotating)
            .build();

    Mono<String> call = client.get()
            .uri("https://inventory.example.internal/test")
            .retrieve()
            .bodyToMono(String.class);

    StepVerifier.create(call).expectNext("ok").verifyComplete();
    provider.publish("key-generation-2");
    StepVerifier.create(call).expectNext("ok").verifyComplete();

    assertEquals(List.of("key-generation-1", "key-generation-2"),
            observed);
}
~~~

Các imports của ví dụ: **CopyOnWriteArrayList**, **List**, **Mono**, **StepVerifier**, **WebClient**, **ExchangeFunction**, **ExchangeFilterFunction**, **ClientRequest**, **ClientResponse**, **HttpStatus**, JUnit assertions. Key dạng chuỗi chỉ là dữ liệu giả dùng trong unit test.

**Test này không kiểm tra TLS, mTLS hoặc LoadBalancer.** Nó chỉ xác minh WebClient filter cấp header theo snapshot mới mỗi subscription. Để biết certificate/connection pool đã đổi, phải chạy test HTTP/TLS tích hợp.

## 18. Integration test: thay certificate mà không restart caller

Để xác minh thực sự **hot TLS rotation**, cần một test server HTTPS/mTLS chứ không chỉ mock HTTP response. Có thể dùng **MockWebServer HTTPS**, WireMock HTTPS hoặc một test server Netty/Tomcat với hai thế hệ certificate tự cấp bởi test CA.

### 18.1. Chuẩn bị test PKI

Tạo hai bộ tài liệu thử nghiệm **không chứa khóa production**:

~~~text
CA-old
  └── inventory-old.crt + inventory-old.key
  └── order-client-old.crt + order-client-old.key

CA-new
  └── inventory-new.crt + inventory-new.key
  └── order-client-new.crt + order-client-new.key
~~~

Certificate test phải có **SAN hợp lệ** cho hostname được HTTP client dùng, ví dụ localhost hoặc test domain; không tắt hostname validation để test “dễ pass”. Nếu test dùng hostname localhost thì certificate cần DNS SAN localhost, nếu client dùng IP thì cần IP SAN tương ứng.

Thiết lập hai server hoặc một server có khả năng thay certificate/SSLContext cho **handshake mới**. Mở kết nối mới bằng client thế hệ N và N+1 để kiểm tra trường hợp trust transition.

### 18.2. Ma trận kiểm thử trust rollover

| Phía client trust | Server certificate | Kỳ vọng |
| --- | --- | --- |
| CA-old | CA-old | TLS thành công |
| CA-old | CA-new | TLS thất bại vì không tin CA mới |
| CA-old + CA-new | CA-old | TLS thành công trong overlap |
| CA-old + CA-new | CA-new | TLS thành công trong overlap |
| CA-new | CA-new | TLS thành công sau rotation |
| CA-new | CA-old | TLS thất bại khi đã loại bỏ CA cũ |
| CA-new, sai SAN | CA-new, hostname không khớp | TLS/hostname verification thất bại |
| CA-new, private key không khớp | Cấu hình invalid | Từ chối publish generation mới |

Mỗi ca phải ép **TCP/TLS handshake mới**, không dùng lại connection đang mở. Nếu request 1 và 2 dùng cùng HTTP/2 connection, test có thể pass nhờ TLS session cũ dù truststore mới **chưa hề được áp dụng**.

### 18.3. Ma trận kiểm thử mTLS

Ngoài trust server, Inventory phải kiểm tra client identity:

| Client certificate | Server trust for clients | Kết quả |
| --- | --- | --- |
| client-old | CA-client-old | Thành công |
| client-new | CA-client-old | Thất bại nếu CA-new chưa được tin |
| client-new | CA-client-old + CA-client-new | Thành công trong overlap |
| client-new | CA-client-new | Thành công sau rotate |
| expired client certificate | Trust chain hợp lệ | Thất bại theo certificate validity |
| no client certificate | Server yêu cầu mTLS | Handshake không thành công |

Nếu server còn có authorization theo principal từ certificate, cần kiểm tra thêm identity, roles và policy chứ không chỉ handshake success.

### 18.4. Kiểm thử connection pool drain

1. Mở một request A lâu (server trì hoãn body) trên generation N.
2. Đợi A thật sự bắt đầu xử lý trên server.
3. Publish generation N+1 sau khi đã canary handshake thành công.
4. Gửi request B mới, xác minh B dùng **connection + client certificate generation N+1**.
5. Cho A hoàn tất và xác minh body/status không bị cắt không cần thiết.
6. Đảm bảo pool N ngừng nhận request mới và được close sau drain.
7. Lặp lại với request A bị timeout/cancel để xác minh không leak in-flight reference.

Không chỉ quan sát HTTP status. Cần đo connection accept/handshake, peer certificate identity, active/idle pool và requests phân loại theo generation; log chỉ fingerprint/key ID an toàn, không ghi private key.

## 19. Integration test: xoay API key/OAuth2 dưới traffic

Test nên có ít nhất ba lớp:

### 19.1. Test API key hai pha

Backend giả có trạng thái:

~~~text
Pha 0: chỉ chấp nhận key-old
Pha 1: chấp nhận key-old và key-new
Pha 2: chỉ chấp nhận key-new
~~~

Test:

1. Client đang dùng key-old gọi API, nhận 200.
2. Server bật dual acceptance.
3. Credential provider publish key-new.
4. Request mới dùng key-new và nhận 200 **mà không restart JVM**.
5. Server ngừng chấp nhận key-old.
6. Xác minh không còn request mới dùng key-old; mọi request mới thành công.

Đặc biệt, hãy kiểm tra rằng key không bị leak sang **một downstream thứ hai** khi client redirect hoặc khi cùng HTTP client có nhiều base URLs.

### 19.2. Test OAuth2 token renewal

Với Authorization Server giả hoặc integration test provider:

- Token T1 có expiry ngắn.
- Authorized client manager được cấu hình đúng cho grant (client_credentials hoặc refresh_token).
- HTTP requests trước expiry dùng T1 theo policy cache.
- Sau khi T1 hết hạn hoặc đến ngưỡng refresh, manager lấy token T2.
- Backend chấp nhận T2, reject token expired và xác minh scopes/audience.
- Khi nhiều concurrent requests cùng yêu cầu renewal, số calls tới token endpoint không tăng mất kiểm soát.

**Không gộp test token renewal với rotation client secret**. Một client_credentials flow vẫn có thể đổi access token thường xuyên nhưng vẫn tiếp tục dùng client secret cũ. Test client secret rotation phải thay **registration/auth credentials** và xác minh token request mới dùng thế hệ secret mới.

### 19.3. Test lỗi có kiểm soát

| Sự cố được gây ra | Hành vi mong muốn |
| --- | --- |
| Secret file tạm thời có cặp cert/key không khớp | Không publish generation mới; giữ generation cũ nếu còn an toàn |
| Secret volume chưa cập nhật | Không tuyên bố rotation thành công; metrics/alert cho biết đang chờ |
| API key mới chưa được server chấp nhận | Canary fail, không chuyển toàn bộ traffic |
| Auth Server tạm thời lỗi | Không refresh storm; timeout/backoff/deadline rõ |
| Client secret đã bị thu hồi | Không retry vô hạn với secret cũ |
| Backend A đã rotate, B chưa | Canary từng instance, không che bằng retry vô hạn |
| Connection cũ đóng sau swap | Requests đang chạy drain đúng policy, không leak |
| CA cũ bị compromise | Thu hồi theo security runbook, không kéo dài overlap trái policy |

### 19.4. Kết hợp Spring Cloud LoadBalancer vào bài test

Dùng hai HTTPS/mTLS servers làm **ServiceInstance** của inventory-service qua SimpleDiscoveryClient hoặc test supplier:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: https://inventory-a.internal:8443
              - uri: https://inventory-b.internal:8443
~~~

Các host/port ở đây là ví dụ; trong test thật dùng port động cùng DNS/test hostname phù hợp SAN, hoặc custom DNS resolver trong môi trường test có kiểm soát.

Kiểm tra cả request qua **https://inventory-service** lẫn **identity TLS của instance đã chọn**, không chỉ so sánh URI logic. Nếu chỉ gửi request trực tiếp localhost, bạn mới test HTTP transport và chưa chứng minh integration với Spring Cloud LoadBalancer.

## 20. Observability: biết thế hệ nào đang được dùng

Một dashboard rotation chỉ hiển thị “Secret updated at 12:00” là chưa đủ. Nên có các tín hiệu:

| Tín hiệu | Trả lời câu hỏi |
| --- | --- |
| Active credential generation | Ứng dụng đã publish phiên bản nào? |
| Secret observed generation | File watcher/provider đã nhìn thấy version nào? |
| Certificate notAfter/days remaining | Bao lâu nữa sẽ hết hạn? |
| Last successful client TLS handshake after rotation | Client thật sự dùng material mới chưa? |
| Rotation validation failures | Lỗi parse, key mismatch, chain/SAN? |
| TLS handshake failure rate | Có lỗi trust/mTLS/SNI theo instance không? |
| HTTP 401/403 rate | Lỗi application authorization tăng không? |
| OAuth2 token refresh failures | Token endpoint/client secret đang lỗi không? |
| Old generation in-flight connections | Còn bao nhiêu request/socket cần drain? |
| Connection pool pending/active | Rotation có gây connection storm không? |
| Service ID / instance ID / zone | Lỗi chỉ xảy ra ở một backend hoặc zone? |
| Rollout completion | Bao nhiêu pods/generations đã cập nhật? |

### 20.1. Không để metrics lộ bí mật

Không ghi:

- PEM certificate private key hoặc nội dung Secret.
- Bearer/refresh token.
- Client secret, API key hoặc chữ ký HMAC.
- Authorization/Cookie headers.
- Raw request/response body có dữ liệu cá nhân.

Các nhãn có thể dùng gồm **logical service ID**, **generation ID công khai**, loại lỗi và mã status. Tránh đưa per-user ID, token hash chưa được kiểm soát hay instance ID có cardinality vô hạn lên metric. Có thể lưu certificate expiry và một fingerprint công khai đã cân nhắc bảo mật để phục vụ debug.

### 20.2. Phân loại lỗi đúng tầng

~~~text
TLS: javax.net.ssl.SSLHandshakeException
    -> trust, certificate validity, SAN/SNI, mTLS client identity

HTTP: 401 Unauthorized
    -> token missing/expired/wrong audience/issuer, key invalid

HTTP: 403 Forbidden
    -> scope/role/policy hoặc identity không được cấp quyền

HTTP: 503 Service Unavailable
    -> backend/gateway unavailable hoặc LB không có instance

Transport: connect timeout/refused
    -> connection/network, chưa chắc liên quan credential
~~~

Trong một số stack, TLS exception có thể bị **ResourceAccessException**, **WebClientRequestException** hoặc Feign exception bọc lại. Cần đọc root cause, nơi phát sinh và traces. **Không tăng retry cho 401/403/TLS handshake liên tục** khi certificate mismatch hoặc policy sai; nó chỉ tăng tải và che nguồn lỗi.

## 21. Runbook khi rotation gây lỗi production

Giả sử triển khai CA-new cho Inventory và Order bắt đầu lỗi ngẫu nhiên:

1. **Khoanh vùng:** service ID, zone, instance ID nào lỗi? Lỗi TLS hay HTTP 401/403?
2. **Kiểm tra PKI:** SAN, certificate chain, validity, EKU, CA overlap và clock skew.
3. **Kiểm tra Secret propagation:** generation trong Secret Manager, mounted volume, app observed generation.
4. **Kiểm tra runtime client:** SSLContext generation, pool generation, còn socket cũ không?
5. **Kiểm tra LB:** supplier/discovery có trả instance chưa rotate hay metadata đang stale?
6. **Kiểm tra auth:** access token audience/issuer/scope, client registration secret, JWKS cache và server verifier.
7. **Tạm dừng rollout:** không lan thêm lỗi sang mọi pods khi chưa rõ nguyên nhân.
8. **Canary một connection mới:** kiểm tra A/B/zone với material mới, không reuse socket cũ.
9. **Rollback có kiểm soát** nếu credential cũ chưa bị compromise và policy cho phép; nếu đã compromise, thay thế cấp tốc thay vì phục hồi credential nguy hiểm.
10. **Xác nhận phục hồi:** error rate, successful TLS handshakes, 401/403, tokens renewed, old pools drained.

### 21.1. Không làm ba hành động sau trong incident

- **Không tắt hostname verification/trust validation** để “mở đường” tạm thời.
- **Không bật retry vô hạn** cho SSLHandshakeException, 401 hoặc 403.
- **Không log full token, key hoặc Secret** để tìm lỗi.

Nếu cần chẩn đoán, hãy thu các giá trị không bí mật: certificate subject/SAN/notAfter, verified peer identity, mã exception, credential generation và trace/span ID. Quyền xem thông tin PKI/credential cần được giới hạn theo policy vận hành.

## 22. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ thay file PEM rồi coi client đã đổi TLS | SSLContext/pool vẫn chứa thế hệ cũ | Kiểm tra consumer reload hoặc thay client generation |
| Dùng reload-on-update của server rồi suy ra WebClient outbound tự refresh | Kết nối outbound vẫn dùng cũ | Tách inbound server SSL và outbound connector |
| Mount Secret qua Kubernetes subPath | File không nhận update tự động | Mount cả thư mục Secret/projected volume |
| Lấy secret từ env var rồi kỳ vọng hot rotation | JVM vẫn giữ biến môi trường cũ | Dùng volume/secret provider động hoặc rolling restart |
| Chỉ refresh RestClient.Builder | RestClient đã build giữ request factory cũ | Refresh đúng adapter hoặc atomic swap client |
| Thay certificate nhưng không kiểm tra SAN/SNI | TLS handshake/hostname verification fail theo instance | Thống nhất URI rewrite và certificate SAN |
| Chỉ đổi client certificate, chưa update server trust | mTLS handshake fail | Thực hiện trust overlap trước |
| Thay CA theo một bước, bỏ qua overlap | Nửa cụm còn CA cũ bị từ chối | Expand → migrate → contract có canary |
| Đóng pool cũ ngay khi publish | Request in-flight bị ngắt | Drain có deadline và quản lý lease/refcount |
| Chỉ gọi probe trên một instance | Tưởng mọi bản sao đã rotate | Canary từng instance/zone và TLS handshake mới |
| Thêm API key ở defaultHeader khi startup | Giữ API key cũ mãi | Interceptor/filter lấy snapshot mỗi request |
| Ghi API key trong Feign global configuration | Rò credential sang Feign client khác | Per-client config có scope rõ |
| Coi access token expiry bằng client secret rotation | Manager vẫn dùng registration secret cũ | Quản lý vòng đời auth client riêng |
| Nhận 401 rồi replay POST vô hạn | Duplicate side effect/retry storm | Giới hạn attempts, idempotency và xử lý auth đúng |
| Tắt verification cho qua TLS lỗi | Mất xác minh danh tính, nguy cơ MITM | Sửa CA/SAN/truststore, không dùng trust-all |
| Dùng refresh actuator public | Có thể bị thay config/credential trái phép | Authn/authz, network policy và audit |
| Log certificate private key/token | Lộ credential trong logs | Chỉ ghi generation/failure category an toàn |
| Chạy dual trust quá lâu sau compromise | Mở dài cửa sổ sử dụng key cũ | Quy trình thu hồi theo mức độ incident |
| Tin rằng 503 = certificate lỗi | Có thể là discovery/backend outage | Tách TLS, HTTP status và no-instance |

## 23. Bài tập tình huống

### 23.1. Tình huống A: chứng chỉ server mới cùng CA

Inventory thay certificate cũ bằng certificate mới cùng CA, cùng DNS SAN, còn hiệu lực. Order giữ nguyên truststore và HTTP client.

**Câu hỏi:** Order có bắt buộc phải reload truststore không?

**Đáp án:** Không nhất thiết, vì trust anchor vẫn tin certificate chain mới nếu các kiểm tra hostname, validity, EKU và policy đều hợp lệ. Tuy nhiên, phải bảo đảm **handshake mới** tới từng instance thành công. Kết nối đã mở trước đó không chứng minh việc xác minh certificate mới.

### 23.2. Tình huống B: thay CA mới

Order chỉ tin CA-old, Inventory-B chuyển sang certificate ký bởi CA-new.

**Câu hỏi:** Retry sang A có giải quyết hoàn toàn sự cố không?

**Đáp án:** Không. Retry có thể tạm che lỗi nếu A còn CA-old, nhưng B vẫn lỗi TLS. Cần trust overlap CA-old+CA-new ở Order trước khi chuyển server certificates, xác minh B bằng kết nối mới rồi mới thu hẹp trust.

### 23.3. Tình huống C: token ngắn hạn

Order dùng client_credentials lấy token T1, token hết hạn sau 5 phút. Một worker giữ T1 trong field final của singleton Feign interceptor.

**Câu hỏi:** Vì sao sau 5 phút Feign trả 401?

**Đáp án:** Interceptor đã chụp token cũ. Dùng authorized client manager hoặc token provider lấy token còn hiệu lực tại thời điểm request; cache theo expiry và refresh đồng bộ. Không gửi lại T1 vô hạn, cũng không gọi Token Endpoint ở mọi request.

### 23.4. Tình huống D: Kubernetes Secret đã cập nhật nhưng app vẫn dùng cũ

Secret Manager có generation N+1, Kubernetes Secret đã được update, app đang mount file qua **subPath**.

**Câu hỏi:** File watcher có bảo đảm thấy N+1 không?

**Đáp án:** Không. Kubernetes tài liệu hóa mount qua subPath **không tự cập nhật** khi Secret đổi. Chuyển sang mount thư mục phù hợp hoặc rolling restart; sau khi file thực sự đổi vẫn cần nạp material và cập nhật HTTP client generation.

### 23.5. Tình huống E: chỉ WebClient mới lỗi sau rotation

RestClient outbound gọi cùng downstream thành công, WebClient vẫn có SSLHandshakeException.

**Câu hỏi:** Có thể kết luận Spring Cloud LoadBalancer sai không?

**Đáp án:** Chưa. Hai clients có thể dùng **HTTP engines, SSLContext, truststore và connection pools khác nhau**. Kiểm tra consumer của SSL bundle, underlying connector, selected instance, hostname verification và active client generation. Đừng chỉ so sánh URI logic.

### 23.6. Tình huống F: mTLS client key vừa bị compromise

Khóa mTLS của Order bị phát hiện lộ. Server vẫn chấp nhận cả client cert cũ và mới trong overlap.

**Câu hỏi:** Có nên kéo dài overlap để rollout nhẹ nhàng?

**Đáp án:** Không nếu điều đó trái với yêu cầu phản ứng sự cố. Phải ưu tiên thu hồi/cô lập key bị lộ và cấp vật liệu mới theo runbook bảo mật. Có thể chấp nhận gián đoạn có kiểm soát, phân phối credential mới nhanh và giới hạn client scope, thay vì tiếp tục tin key đã compromise.

## 24. Checklist production trước khi bật runtime rotation

- [ ] Xác định rõ phải rotate **server certificate, client mTLS certificate, trust CA, access token, client secret hay API key**.
- [ ] Có sơ đồ logical service ID → selected ServiceInstance → physical host → TLS peer identity.
- [ ] Certificate SAN/SNI/hostname verification được thiết kế nhất quán với URI rewrite.
- [ ] Không sử dụng trust-all, disable hostname verification hoặc private key trong source repo.
- [ ] Secrets có generation/version, time-to-expiry và audit trail.
- [ ] Kubernetes volume nhận update; không dựa vào subPath hoặc env var để hot reload.
- [ ] Đọc cert/key atomically theo snapshot, kiểm tra khớp key, chain và validity trước publish.
- [ ] Phân biệt reload Spring Boot **server SSL bundle** với outbound client SSL context/pool.
- [ ] Đã xác định HTTP engine thực tế của RestClient, RestTemplate, WebClient và Feign.
- [ ] Có cơ chế **atomic swap + drain** hoặc rolling restart đã được kiểm thử.
- [ ] HTTP client không được sử dụng sau khi generation/pool của nó đã đóng.
- [ ] Có test in-flight requests, reactive cancellation và long-lived streams trong rotation.
- [ ] CA/trust rollover có overlap phù hợp; xử lý compromise có quy trình riêng.
- [ ] OAuth2AuthorizedClientManager/provider đúng grant, expiry và principal scope.
- [ ] Không nhầm access token renewal với rotation OAuth2 client secret/JWKS.
- [ ] API key interceptor/filter lấy snapshot ở thời điểm request, đúng audience/downstream.
- [ ] Không đặt credential của một service trong Feign/WebClient global configuration cho service khác.
- [ ] Retry có giới hạn; không retry vô hạn 401/403/TLS handshake errors.
- [ ] Có canary handshake và authorization test trên nhiều instances/zones.
- [ ] Có metrics credential generation, TLS errors, 401/403, token refresh failure và pool drain.
- [ ] Actuator refresh/env endpoints được bảo vệ hoặc không expose khi không dùng.
- [ ] Cấu hình rolling restart/readiness có dự phòng khi hot reload không hỗ trợ.
- [ ] Có rollback/incident runbook, tránh tái kích hoạt key bị compromise.
- [ ] Không log bearer tokens, private keys, API keys hoặc client secrets.
- [ ] Đối chiếu khả năng của Spring Boot/Spring Cloud/Spring Security/HTTP engine theo BOM thật.

## 25. Kết luận

**Làm mới chứng chỉ và thông tin xác thực khi ứng dụng đang chạy không phải chỉ là đổi một file hoặc gọi một endpoint refresh.** Spring Cloud LoadBalancer chọn **ServiceInstance**; HTTP transport và connection pool sở hữu **TLS session, SSLContext, KeyManager/TrustManager**; OAuth2 client/token provider sở hữu **vòng đời access token và client secret**. Mỗi lớp có cơ chế cập nhật khác nhau.

Để rotation an toàn:

1. **Thiết kế overlap trust/credential** cho luân chuyển thông thường, nhưng có quy trình thu hồi khẩn cấp khi key bị lộ.
2. **Phân phối secret thành công chưa đủ**; validate và publish một generation mới vào đúng client.
3. **TLS:** bảo đảm handshake mới dùng certificate/trust mới; thay và drain HTTP pool nếu transport không hỗ trợ cập nhật động.
4. **OAuth2/API key:** lấy thông tin hợp lệ ở thời điểm request, không đóng cứng trong singleton interceptor.
5. **Kiểm thử thật:** đồng thời xác minh service ID được LoadBalancer chọn, physical TLS identity, HTTP authorization và request in-flight.
6. **Quan sát đầy đủ:** không chỉ đo “rotation event” mà còn theo dõi TLS handshakes, credential generation, 401/403, fallback/retry và pool drain.

Trong hệ thống yêu cầu độ tin cậy cao, **rolling restart có kiểm soát vẫn là lựa chọn hợp lệ** khi outbound client không bảo đảm hot reload. Tránh vì mục tiêu zero downtime mà làm yếu TLS verification hoặc kéo dài sự tồn tại của một khóa đã bị compromise.

## 26. Tài liệu tham khảo

- [Spring Boot – SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): PEM/JKS SSL bundles, SslBundles, reload-on-update, giới hạn consumer hỗ trợ reload và file watcher.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestClientSsl/WebClientSsl, request factories, client builders và khả năng áp dụng SSL bundle.
- [Spring Boot – SSL Hot Reload](https://spring.io/blog/2023/11/07/ssl-hot-reload-in-spring-boot-3-2-0/): cơ chế server-side SSL bundle reload khi chứng chỉ được cập nhật.
- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): @RefreshScope, ConfigurationProperties rebind, /actuator/refresh, security và giới hạn AOT/native.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestClient, WebClient và service ID.
- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, discovery, health, metadata và retry-aware selection.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): FeignBlockingLoadBalancerClient, named client configuration và RequestInterceptor.
- [Spring Security – Authorized Client Features, Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): OAuth2ClientHttpRequestInterceptor và OAuth2AuthorizedClientManager với RestClient.
- [Spring Security – Authorized Client Features, Reactive](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html): ServerOAuth2AuthorizedClientExchangeFilterFunction, token acquisition và refresh.
- [Spring Security – OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): refresh token grant và cấu hình token response client.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, RestTemplate và SSL/transport abstraction.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): WebClient connector và lifecycle.
- [Reactor Netty – HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): TLS, connection pooling và HTTP client resources.
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): mounted Secret update consistency, subPath limitation, env vars và cluster propagation.
- [Kubernetes – Projected Volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/): projected secrets, pod certificates, symlink atomics và đọc credential material.
- [RFC 8446 – TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshakes, identities và session resumption.
- [RFC 6749 – OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client credentials và refresh token grants.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authorization và nguyên tắc bảo vệ token.

