# Lưu thông tin xác thực và chứng chỉ trong cấu hình bí mật

**Chương: Bảo mật — Spring Data Cassandra**

Ứng dụng **Spring Data Cassandra** cần thông tin để kết nối đến Apache Cassandra: địa chỉ node, local datacenter, keyspace, đôi khi là **tên người dùng và mật khẩu**, cùng tài liệu TLS như **chứng chỉ CA, truststore** hoặc **chứng chỉ và khóa riêng của client** khi dùng mutual TLS (mTLS). Nếu đưa bí mật vào `application.yml` rồi commit lên Git, mọi người có quyền đọc mã nguồn có thể vô tình truy cập dữ liệu của cluster. Nếu đặt mật khẩu ngay trong lệnh khởi chạy hoặc chuỗi kết nối, bí mật còn có thể xuất hiện trong log, history, diagnostic dump hoặc công cụ quan sát tiến trình.

Với Cassandra, cần giải quyết đồng thời **ba vấn đề độc lập**:

1. **Authentication:** Ứng dụng chứng minh danh tính với Cassandra bằng cơ chế được server bật, ví dụ `PasswordAuthenticator`.
2. **Authorization:** Role Cassandra chỉ được phép thao tác với những keyspace, table và tài nguyên cần thiết.
3. **Transport security:** Java Driver giao tiếp với Cassandra qua TLS, xác thực đúng máy chủ và, khi yêu cầu, cung cấp chứng chỉ client.

Quản lý bí mật tốt là **đưa giá trị nhạy cảm ra khỏi source code, cấp vào tiến trình ở thời điểm triển khai, giới hạn người có thể đọc, và hỗ trợ xoay vòng**. Bài này đi từ một cấu hình Spring Boot thực tế đến Kubernetes Secret, Java Driver, kiểm thử và vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt giá trị cấu hình thông thường với **secret**; xác định tệp nào cần bảo vệ và tệp nào chỉ chứa đường dẫn.
- Cấu hình Spring Data Cassandra bằng biến môi trường hoặc **Spring Boot config tree**, tránh ghi mật khẩu vào mã và Git.
- Gắn **Kubernetes Secret** làm file read-only để Spring đọc username/password, truststore và mật khẩu của truststore.
- Giải thích sự khác nhau giữa **truststore của client** và **keystore chứa chứng chỉ client**, cũng như xác thực server và mTLS.
- Tùy biến SSL context cho Java Driver 4.x khi cần CA riêng, đồng thời bảo toàn cấu hình repository, `CassandraTemplate` và CQL hiện có.
- Đánh giá nguy cơ lộ bí mật qua log, Actuator, CI, image và quyền truy cập môi trường.
- Lập quy trình rotate credentials/chứng chỉ, phát hiện lỗi TLS/authentication và kiểm thử kịch bản không an toàn.

## 2. Xác định ranh giới của secret

Không phải mọi cấu hình Cassandra đều bí mật. **Contact points**, **port**, **datacenter** và **keyspace** thường là thông tin triển khai; một số tổ chức vẫn hạn chế công khai cấu trúc hạ tầng. **Mật khẩu, token, khóa riêng, password của keystore/truststore** là bí mật cần kiểm soát chặt.

| Giá trị | Ví dụ | Cần quản lý như secret? | Ghi chú |
|---|---|---|---|
| Host, port CQL | `cassandra.internal:9042` | Thường không | Có thể quản lý ở ConfigMap / config thông thường |
| Local DC / keyspace | `dc1` / `orders` | Thường không | Không trao quyền truy cập chỉ nhờ biết tên |
| Cassandra username | `orders_api` | Có thể nhạy cảm theo chính sách | Thường lưu cùng cặp credentials |
| Cassandra password | Giá trị dài, ngẫu nhiên | **Có** | Không hard-code, không log, không commit |
| CA certificate công khai | `ca.crt` | Không phải khóa bí mật | Phải bảo đảm **tính toàn vẹn** để không tin CA giả |
| Truststore PKCS#12 | `truststore.p12` | Bảo vệ tính toàn vẹn và quyền truy cập | Truststore thường chứa public cert; không mặc định có private key |
| Mật khẩu truststore | `truststore-password` | **Có** | Dùng mở/kiểm tra kho chứng chỉ; không thay cho Cassandra password |
| Client certificate | `client.crt` | Chứng chỉ thường công khai | Đi kèm khóa riêng khi làm mTLS |
| Client private key / keystore chứa key | `client.key` / `client.p12` | **Rất nhạy cảm** | Phải giới hạn quyền đọc và xoay vòng phù hợp |

**Điểm dễ nhầm:** TLS bật không có nghĩa Cassandra đang xác thực người dùng hoặc đã giới hạn quyền CQL. Ngược lại, username/password đúng không tự bảo vệ được thông tin đăng nhập trên đường truyền nếu không có cơ chế mã hóa thích hợp. Cả cấu hình **server Cassandra** và **Java Driver** đều phải khớp.

### 2.1. Sơ đồ luồng cấp cấu hình

~~~mermaid
flowchart TD
    A["Secret manager / Kubernetes Secret"] --> B["Volume hoặc secret injection"]
    C["Config thường: endpoint, DC, keyspace"] --> D["Spring Environment"]
    B --> D
    D --> E["Spring Boot Cassandra auto-configuration"]
    E --> F["Java Driver CqlSession"]
    F --> G["CassandraRepository / CassandraTemplate"]
    H["CA/truststore và khóa client (nếu có)"] --> I["SSLContext / Driver TLS"]
    B --> H
    I --> F
    F -->|"TLS + credentials + CQL"| J["Cassandra server: auth + RBAC + TLS"]
~~~

**Nguyên tắc:** repository và `CassandraTemplate` dùng cùng `CqlSession` đã được cấu hình an toàn. Không cần lưu bản sao mật khẩu trong từng repository hay tự dựng một session khác thiếu TLS.

## 3. Cấu hình Spring Boot bằng biến môi trường

Trong **Spring Boot 3.x**, cấu hình cơ bản cho Cassandra có tiền tố `spring.cassandra.*`. Giá trị bí mật được lấy từ môi trường triển khai:

~~~yaml
# application.yml: lưu trong Git được, vì chỉ có tên biến và thông số thường.
spring:
  cassandra:
    contact-points: "${CASSANDRA_CONTACT_POINTS}"
    port: "${CASSANDRA_PORT:9042}"
    local-datacenter: "${CASSANDRA_LOCAL_DC}"
    keyspace-name: "${CASSANDRA_KEYSPACE}"
    username: "${CASSANDRA_USERNAME}"
    password: "${CASSANDRA_PASSWORD}"
    ssl:
      enabled: true
~~~

Khi ứng dụng khởi động, Spring giải quyết các placeholder từ môi trường. Nếu thiếu biến bắt buộc, nên để ứng dụng **fail lúc startup** thay vì cấp giá trị mặc định là username/password chia sẻ hoặc tài khoản có quyền cao.

Với Spring Boot 2.x, nhiều thuộc tính Cassandra nằm trong nhánh `spring.data.cassandra.*`; với Boot 3.x là `spring.cassandra.*`. Kiểm tra phiên bản dự án khi sao chép ví dụ. Tên biến chuẩn dạng `SPRING_CASSANDRA_USERNAME` và `SPRING_CASSANDRA_PASSWORD` cũng có thể được ánh xạ theo cơ chế relaxed binding của Spring Boot.

### 3.1. Ưu điểm và giới hạn của biến môi trường

Biến môi trường đơn giản và tương thích với nhiều hệ thống triển khai. Nhưng giá trị của chúng vẫn có thể lộ qua công cụ xem môi trường tiến trình, cấu hình container, crash report, script chẩn đoán hoặc log vô tình in toàn bộ môi trường.

Không nên:

~~~yaml
# KHÔNG làm: mật khẩu thật được commit trong source.
spring:
  cassandra:
    username: superuser
    password: "my-production-password"
~~~

Không nên đưa secret vào argument Java như `-Dspring.cassandra.password=...` trong script/lệnh chạy nếu hệ thống có thể ghi lại command line. Không echo nội dung secret để “debug kết nối”. Nếu nền tảng hỗ trợ **file-mounted secret** hoặc secret manager tích hợp, cách đó giảm một số bề mặt lộ thông tin so với việc phân phối toàn bộ giá trị qua biến môi trường.

### 3.2. Mã ứng dụng không cần tự lấy mật khẩu

Trong đa số trường hợp, Spring Boot tự cấu hình `CqlSession` từ các thuộc tính Cassandra. Một repository bình thường chỉ cần khai báo:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CustomerRepository
        extends CassandraRepository<Customer, UUID> {
}
~~~

`Customer` là entity đã được ánh xạ tới bảng Cassandra. Repository không nên mở file password, giữ secret trong trường static hoặc ghi username/password vào log. Nếu có logic bổ sung như chuẩn bị statement, paging hay consistency, logic đó hoạt động trên session đã được bảo vệ.

## 4. Spring Boot config tree: đọc secret trực tiếp từ file

Một cách tách secret khỏi biến môi trường là **gắn secret thành các file**, rồi dùng `spring.config.import=configtree:...`. Spring Boot đọc tên file thành **property key**, nội dung file thành **property value**.

Giả sử container ứng dụng có các file:

~~~text
/run/secrets/cassandra-config/
  spring.cassandra.username
  spring.cassandra.password
~~~

Hai tên file phía trên là **khóa cấu hình Spring**, không phải dữ liệu đăng nhập thật. Dữ liệu thật được cấp từ secret manager của môi trường triển khai.

Trong `application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/cassandra-config/"
  cassandra:
    contact-points: "${CASSANDRA_CONTACT_POINTS}"
    port: "${CASSANDRA_PORT:9042}"
    local-datacenter: "${CASSANDRA_LOCAL_DC}"
    keyspace-name: "${CASSANDRA_KEYSPACE}"
    ssl:
      enabled: true
~~~

Spring lấy `spring.cassandra.username` và `spring.cassandra.password` từ hai file có cùng tên. Dùng `configtree:` **không tự tạo secret**; bạn phải bảo đảm các file đã được mount đúng đường dẫn trước khi ứng dụng chạy.

Ở ví dụ production, dùng `configtree:` bắt buộc để ứng dụng báo lỗi khi thiếu vùng cấu hình cần thiết. Nếu một môi trường phát triển không có secret volume, có thể cấu hình profile riêng với `optional:configtree:...`, nhưng đừng dùng `optional:` để âm thầm bỏ qua bí mật bắt buộc ở production.

### 4.1. Vì sao cách đặt tên file có ích?

Nếu chỉ mount file `username` và `password` rồi dùng `configtree:/run/secrets/cassandra-config/`, Spring sẽ thu được property `username` và `password` ở cấp gốc; chúng **không tự động** biến thành `spring.cassandra.username` và `spring.cassandra.password`. Cách đặt trực tiếp tên file có dấu chấm giúp binding rõ ràng.

Bạn cũng có thể giữ tên file `username`/`password` và cấu hình:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/cassandra-config/"
  cassandra:
    username: "${username}"
    password: "${password}"
~~~

Tuy nhiên, tên property `username` ở cấp gốc dễ va chạm với nguồn cấu hình khác. Với môi trường có nhiều ứng dụng/dịch vụ, ưu tiên đặt tên rõ namespace và tránh tự nhân bản bí mật qua nhiều nơi.

### 4.2. File nào thuộc source, file nào thuộc secret?

| File/đường dẫn | Có thể theo dõi bằng Git? | Lý do |
|---|---|---|
| `src/main/resources/application.yml` chỉ có placeholder và đường dẫn | Có | Không chứa giá trị bí mật |
| Template deployment chỉ tham chiếu `secretName` | Thường có | Không đưa secret payload vào manifest |
| `/run/secrets/cassandra-config/spring.cassandra.password` | **Không** | Chứa mật khẩu thật |
| `/run/secrets/cassandra-tls/client-keystore.p12` | **Không** | Có thể chứa khóa riêng client |
| Chứng chỉ CA công khai đã kiểm soát nguồn | Có thể, theo chính sách | Cần quản lý tính toàn vẹn và cập nhật |
| File `.env` chứa thông tin thật để chạy local | **Không** | Có thể vô tình commit hoặc sao lưu rộng |

Thêm cơ chế ignore và secret scanning trong CI giúp giảm rủi ro, nhưng **không thay thế** việc cấp secret có kiểm soát. Nếu một mật khẩu đã từng bị commit, xóa khỏi commit mới không đủ: phải **rotate ngay** và xử lý lịch sử phân phối theo quy trình tổ chức.

## 5. Kubernetes Secret: tách auth và TLS theo mục đích

Ví dụ ứng dụng chạy trong Kubernetes, tổ chức có sẵn hai Secret được hệ thống quản lý bí mật tạo và đồng bộ:

- `cassandra-app-auth` chứa các key `username` và `password`.
- `cassandra-client-tls` chứa `truststore.p12` và `truststore-password`.

Ví dụ sau chỉ tham chiếu **Secret đã tồn tại**; không chứa mật khẩu, khóa riêng hoặc chứng chỉ thật trong manifest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: registry.example.com/orders-api:1.0.0
          env:
            - name: CASSANDRA_CONTACT_POINTS
              value: "cassandra.service.internal"
            - name: CASSANDRA_LOCAL_DC
              value: "dc1"
            - name: CASSANDRA_KEYSPACE
              value: "orders"
          volumeMounts:
            - name: cassandra-auth
              mountPath: /run/secrets/cassandra-config
              readOnly: true
            - name: cassandra-tls
              mountPath: /run/secrets/cassandra-tls
              readOnly: true
      volumes:
        - name: cassandra-auth
          secret:
            secretName: cassandra-app-auth
            items:
              - key: username
                path: spring.cassandra.username
              - key: password
                path: spring.cassandra.password
        - name: cassandra-tls
          secret:
            secretName: cassandra-client-tls
            items:
              - key: truststore.p12
                path: truststore.p12
              - key: truststore-password
                path: truststore-password
~~~

Trong `application.yml`, giá trị:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/cassandra-config/"
  cassandra:
    contact-points: "${CASSANDRA_CONTACT_POINTS}"
    local-datacenter: "${CASSANDRA_LOCAL_DC}"
    keyspace-name: "${CASSANDRA_KEYSPACE}"
    ssl:
      enabled: true
app:
  cassandra:
    tls:
      truststore-path: "/run/secrets/cassandra-tls/truststore.p12"
      truststore-password-file: "/run/secrets/cassandra-tls/truststore-password"
~~~

Khóa `app.cassandra.tls.*` là **cấu hình tùy chỉnh của ứng dụng** để dùng trong ví dụ Java ở phần sau. Chúng không phải thuộc tính tự động cấu hình TLS sẵn có của Spring Boot.

**Chú ý về đường dẫn:** Trong một số image/container, filesystem là read-only hoặc ứng dụng chạy bằng UID không phải root. Kiểm tra quyền sở hữu/đọc của secret volume, `runAsUser` và `fsGroup` theo security context thực tế. Không thay bằng `chmod 777` hoặc sao chép khóa riêng sang thư mục chia sẻ chỉ để vượt lỗi permissions.

### 5.1. Kubernetes Secret không phải một hệ thống quản lý bí mật hoàn chỉnh

Trường `data` của Kubernetes Secret thường sử dụng **Base64 để biểu diễn byte**, không phải phép mã hóa bảo vệ khỏi người có thể đọc Secret. Để hạn chế truy cập, cần:

1. Giới hạn quyền `get/list/watch` Secret bằng Kubernetes RBAC theo namespace và service account.
2. Bật **encryption at rest** cho dữ liệu Secret trong etcd theo cấu hình cluster.
3. Giới hạn quyền truy cập Kubernetes API, CI pipeline, container và node.
4. Chỉ mount những key cần thiết cho Pod; tránh mount secret vào container không liên quan.
5. Cân nhắc External Secrets/CSI driver hoặc tích hợp secret manager được tổ chức chấp thuận, nếu có yêu cầu quản lý vòng đời tập trung.

Tránh đưa payload bí mật vào `kubectl apply -f ...` từ một manifest lưu trong Git. Việc dùng Secret name trong manifest không tự động bảo vệ dữ liệu nếu người dùng vẫn có quyền đọc mọi Secret trong namespace.

### 5.2. Không nhầm cập nhật volume với cập nhật connection

Khi Kubernetes cập nhật Secret, nội dung của **projected secret volume** có thể được cập nhật sau một khoảng trễ, tùy cách mount. Nhưng Spring thường chỉ resolve cấu hình khi tạo ApplicationContext, và **Java Driver `CqlSession` không mặc nhiên nạp lại username/password, truststore hay SSLContext** chỉ vì byte của file thay đổi.

Với thiết kế ở đây, cần **rolling restart/rollout** ứng dụng hoặc cơ chế rebuild session được thiết kế và kiểm thử riêng. Đặc biệt, volume dùng `subPath` có giới hạn cập nhật khác với projected volume thông thường; không dựa vào “secret đã update” để kết luận kết nối hiện tại dùng dữ liệu mới.

## 6. TLS: truststore, keystore và xác thực danh tính server

### 6.1. Các thành phần liên quan

| Thành phần | Bên sử dụng | Chức năng |
|---|---|---|
| Server certificate | Cassandra server trình ra cho Driver | Để client xác thực danh tính server |
| CA certificate / truststore | Java Driver | Xác định chuỗi chứng chỉ server nào đáng tin |
| Client certificate | Java Driver trình ra nếu mTLS | Chứng minh danh tính client qua certificate |
| Client private key / keystore | Ứng dụng/Driver nếu mTLS | Ký bắt tay TLS; phải giữ bí mật |
| Cassandra username/password | Java Driver khi server yêu cầu | Xác thực tại tầng CQL/protocol |
| Cassandra role/grants | Cassandra server | Quyết định thao tác CQL được phép |

**Truststore** không đồng nghĩa với “client certificate”. Một PKCS#12 chỉ chứa CA công khai phục vụ kiểm tra server có vai trò khác với PKCS#12 chứa **khóa riêng của client** để mTLS. Có thể dùng cả hai, nhưng nên lưu ở những Secret/đường dẫn được quản lý phù hợp.

### 6.2. Điều kiện để TLS đúng nghĩa

Cấu hình client `spring.cassandra.ssl.enabled=true` không đủ để khẳng định hệ thống an toàn nếu:

- Cassandra server chưa bật **client/native transport encryption** tương thích.
- Java Driver không tin CA đã ký chứng chỉ server.
- Chứng chỉ server hết hạn, chuỗi tin cậy không đầy đủ, hoặc hostname/IP client kết nối không phù hợp Subject Alternative Name (SAN).
- Cơ chế xác minh danh tính hostname phía client bị tắt hoặc chưa cấu hình đúng theo phiên bản Driver.
- Có một đường kết nối khác (ví dụ một session do mã ứng dụng tự tạo) vẫn truy cập CQL không TLS.

Để **chống giả mạo server**, ngoài mã hóa truyền tải phải xác minh certificate chain và danh tính endpoint. Chi tiết bật hostname verification phụ thuộc cấu hình SSL engine của **Java Driver phiên bản đang chạy**; kiểm tra tài liệu Driver và có bài test chứng chỉ SAN không khớp. Tuyệt đối không lắp `TrustManager` chấp nhận mọi chứng chỉ, không tắt hostname verification chỉ để test pass, và không chuyển sang kết nối cleartext như phương án chữa lỗi thiếu CA.

~~~text
Spring application
    │  TLS handshake
    ├── kiểm tra: certificate chain + tên server (SAN)
    ├── (nếu mTLS) gửi client certificate / chứng minh sở hữu private key
    │  kênh được mã hóa
    └── Cassandra: xác thực account / role và kiểm tra quyền CQL
~~~

### 6.3. SSLContext cho CA riêng bằng Spring Boot customizer

Với Cassandra dùng CA nội bộ, có thể cần cung cấp **truststore riêng** cho Driver. Ví dụ sau minh họa Java 17, Spring Boot 3.x và Java Driver 4.x. Nó đọc PKCS#12 đã mount từ secret volume, tạo `SSLContext` và cấp vào session builder được Spring Boot sử dụng.

~~~java
package example.cassandra;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.cassandra.CqlSessionBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CassandraTlsConfiguration {

    @Bean
    CqlSessionBuilderCustomizer cassandraTlsCustomizer(
            @Value("${app.cassandra.tls.truststore-path}") String truststorePath,
            @Value("${app.cassandra.tls.truststore-password-file}") String passwordFile)
            throws GeneralSecurityException, IOException {

        // Secret đã được mount trước khi ApplicationContext khởi tạo.
        // stripTrailing() xử lý newline cuối file khi provision secret.
        char[] password = Files.readString(
                Path.of(passwordFile), StandardCharsets.UTF_8)
                .stripTrailing().toCharArray();

        try {
            KeyStore truststore = KeyStore.getInstance("PKCS12");
            try (InputStream input = Files.newInputStream(Path.of(truststorePath))) {
                truststore.load(input, password);
            }

            TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());
            trustManagers.init(truststore);

            SSLContext sslContext = SSLContext.getInstance("TLS");
            sslContext.init(null, trustManagers.getTrustManagers(), new SecureRandom());

            return builder -> builder.withSslContext(sslContext);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

**Giải thích:**

- `truststore.p12` và `truststore-password` nằm ở volume bí mật, không được đóng gói trong JAR hoặc image.
- `CqlSessionBuilderCustomizer` can thiệp vào session builder của Spring Boot; cấu hình contact points, local DC, auth và keyspace vẫn do auto-configuration quản lý.
- `TrustManagerFactory` dùng CA được cung cấp để kiểm tra chuỗi chứng chỉ, thay vì chấp nhận mọi certificate.
- `password` được xóa khỏi mảng `char[]` sau khi load. Bởi `Files.readString(...)` tạm tạo `String` trong heap, đây là biện pháp **giảm tồn dư trong một biến**, không thể bảo đảm xóa toàn bộ mọi bản sao khỏi bộ nhớ JVM. Trong hệ thống có yêu cầu bảo mật đặc biệt, nên dùng API/SDK secret manager phù hợp.
- `stripTrailing()` phù hợp khi file provisioning có newline kết thúc ngoài ý muốn; nó cũng xóa khoảng trắng cuối chuỗi. Nếu chính sách cho phép mật khẩu kết thúc bằng khoảng trắng, cần sử dụng định dạng file và parser không biến đổi byte mật khẩu.

Ví dụ chỉ **nạp CA để xác thực server**. Nếu Cassandra yêu cầu **mTLS**, cần nạp thêm keystore chứa client private key và certificate chain qua `KeyManagerFactory`, rồi truyền `keyManagers.getKeyManagers()` vào tham số thứ nhất của `sslContext.init(...)`. Chỉ tin CA phía server là chưa đủ cho mTLS. Hạn chế quyền đọc private key hơn so với tệp chứa public CA.

Đoạn code giả định Driver dùng đúng `SSLContext` đã nhận; việc **xác thực hostname** vẫn phải kiểm tra ở SSL engine/Driver config của phiên bản triển khai. Không đưa mật khẩu truststore trực tiếp vào source hoặc `@Value("actual-secret")`.

### 6.4. Đường cấu hình thay thế cho truststore

Tùy Java Driver/Java runtime, hệ thống có thể dùng **JSSE truststore properties**, ví dụ:

~~~text
javax.net.ssl.trustStore=/run/secrets/cassandra-tls/truststore.p12
javax.net.ssl.trustStoreType=PKCS12
~~~

Cách này phụ thuộc việc Driver xây dựng SSL context từ **JSSE mặc định** và cần mật khẩu truststore theo phương thức an toàn của môi trường. Đừng mặc định rằng truyền system properties luôn có tác dụng khi ứng dụng đã cấp một `SSLContext` riêng. Không đưa password trực tiếp lên command line hoặc vào `JAVA_TOOL_OPTIONS` nếu nền tảng có thể ghi lại giá trị đó; ưu tiên file mount/secret manager và cơ chế cấu hình phiên bản Driver đang hỗ trợ.

## 7. Authentication và phân quyền Cassandra

**Phía server** phải bật cơ chế xác thực và ủy quyền thích hợp. Nếu Cassandra cấu hình `AllowAllAuthenticator` và `AllowAllAuthorizer`, việc client cung cấp username/password không bảo đảm rằng server đang kiểm soát truy cập như mong muốn.

Khi Cassandra dùng native authentication/authorization, hãy tạo **role chuyên biệt cho mỗi ứng dụng/môi trường**. Ví dụ minh họa nguyên tắc quyền tối thiểu:

~~~sql
-- Thao tác quản trị: chạy bởi tài khoản được cấp quyền tạo role.
CREATE ROLE orders_api WITH LOGIN = true AND PASSWORD = 'PROVISION_AT_RUNTIME';

-- Chỉ cấp quyền cần thiết cho bảng mà chức năng sử dụng.
GRANT SELECT ON TABLE orders.orders_by_customer_month TO orders_api;
GRANT MODIFY ON TABLE orders.orders_by_customer_month TO orders_api;
~~~

Chuỗi `PROVISION_AT_RUNTIME` ở đây **chỉ là placeholder để đọc ví dụ**, không phải mật khẩu có thể dùng. Trong quy trình thật, secret phải do hệ thống provisioning an toàn tạo/cấp cho Cassandra; không đưa lệnh `CREATE ROLE ... PASSWORD 'mật khẩu thật'` vào file migration được commit, log SQL hoặc lịch sử shell.

Role cho ứng dụng đọc dữ liệu có thể chỉ cần `SELECT`; ứng dụng cần ghi dùng `MODIFY` trên bảng phù hợp. Quyền `CREATE`, `ALTER`, `DROP` hoặc quyền quản trị schema thường thuộc luồng migration có tài khoản riêng, không nên cấp cho mọi instance API.

### 7.1. Tách account và keyspace theo môi trường

| Môi trường | Role | Quyền gợi ý |
|---|---|---|
| Local development | `orders_dev` | Chỉ keyspace dev, dữ liệu giả lập |
| Integration test | `orders_test` | Keyspace test được tạo theo bài test |
| Staging | `orders_staging` | Chỉ keyspace staging |
| Production API | `orders_api` | Quyền SELECT/MODIFY tối thiểu theo bảng cần |
| Production schema migration | `orders_schema_migrator` | Quyền DDL theo phạm vi được kiểm soát |

Tránh tái sử dụng cùng một mật khẩu giữa staging và production. Không dùng role superuser để “tiết kiệm bước GRANT”. Việc tách role còn cho phép xoay vòng riêng và theo dõi thay đổi bằng audit log của tầng vận hành.

### 7.2. Bảo mật không thay thế thiết kế query

Ngay cả khi đã cấu hình TLS/auth/RBAC đúng, repository vẫn cần truy vấn theo **partition key** và schema phù hợp. Một role có quyền SELECT không làm `ALLOW FILTERING` trở nên hiệu quả, không chữa được hot partition hay thay đổi yêu cầu consistency.

Ngược lại, quyền thiếu hoặc tài khoản sai có thể khiến lệnh CQL bị từ chối dù kết nối TCP/TLS đã thành công. Khi xử lý lỗi, phân biệt authentication, authorization, trust chain TLS, hostname và timeout/consistency để tránh sửa nhầm cấu hình.

## 8. Không để secret lọt vào log, monitoring và artifact

Một mật khẩu được cấp bằng secret manager vẫn có thể bị lộ sau khi tiến trình nhận được nó. Hãy rà soát các đường sau:

| Bề mặt | Rủi ro | Biện pháp |
|---|---|---|
| Git/source/JAR/image | Bí mật tồn tại lâu, phân phối rộng | Chỉ commit placeholder; secret scanning; không copy secret vào image |
| Log startup/config | In cấu hình Spring, URI hoặc environment | Không dump toàn bộ properties; dùng masking và log theo allowlist |
| Actuator `/env`, `/configprops` | Giá trị cấu hình có thể bị truy cập | Giới hạn endpoint, cấu hình sanitization, kiểm tra với bản Boot đang dùng |
| Stack trace/debug | Một thư viện có thể đưa URI/param vào exception | Không log raw credentials/driver options; kiểm tra formatter |
| Shell/CI | Command history, job output, debug echo | Truyền bằng secret binding; tắt debug in secrets, giới hạn retention |
| Metrics/tracing | Secret nằm trong tag/baggage/high-cardinality | Tag bằng tên operation/outcome; không tag username/password/token |
| Backup/snapshot | Secret bị lưu ngoài vòng đời dự kiến | Áp dụng chính sách bảo vệ, retention, encryption và xóa bản cũ |
| Quyền đọc volume | Container khác hoặc tài khoản không cần vẫn đọc được | Giới hạn mount, filesystem permission và service account |

Spring Boot có cơ chế **che dấu giá trị nhạy cảm** trong một số endpoint Actuator, nhưng mức độ và mặc định có thể thay đổi theo phiên bản/cấu hình. Không coi Actuator là nơi được phép công khai chỉ vì tin rằng password luôn bị che.

Nếu ứng dụng tự tạo record log cho kết nối, nên giữ thông tin hữu ích như:

~~~text
cassandra.connection: endpoint_group=primary, local_dc=dc1,
keyspace=orders, tls_enabled=true, result=success
~~~

Không cần in:

~~~text
# Không log dạng này:
cassandra.connection: username=<real-user>, password=<real-password>,
truststore_password=<real-secret>, private_key=<PEM-content>
~~~

Ngay cả khi che bằng chuỗi `***`, tránh làm lộ toàn bộ secret trước đó qua debug dump hoặc exception được ghi ở tầng khác.

## 9. Xoay vòng credentials và chứng chỉ không làm gián đoạn dịch vụ

### 9.1. Rotate Cassandra username/password

Một cách triển khai an toàn khi được hệ thống hỗ trợ là **overlap hai role** hoặc hai bộ credential:

1. Tạo role/credential mới bằng quy trình provisioning riêng, cấp **cùng quyền tối thiểu cần thiết**.
2. Cập nhật secret source, đồng bộ vào môi trường triển khai và xác nhận Secret mới tồn tại (không in giá trị).
3. Rolling restart các Pod/instance để **`CqlSession` mới** sử dụng credential mới.
4. Kiểm tra auth failure, connection pool, request timeout, read/write và retry tại từng instance sau rollout.
5. Chỉ thu hồi role/credential cũ khi toàn bộ instance sử dụng credential mới và không còn workload phụ thuộc.
6. Lưu dấu vết thay đổi, thời điểm revoke, account owner và thời hạn xoay vòng tiếp theo.

Nếu chỉ **đổi mật khẩu trên cùng role** trước khi mọi client được chuyển sang secret mới, các kết nối mới hoặc reconnect có thể thất bại trong cửa sổ chuyển đổi. Chiến lược overlap cho phép kiểm soát tiến trình tốt hơn, miễn là cơ chế quyền và audit của tổ chức hỗ trợ.

**Không dựa vào một kết nối đang sống:** session hiện tại có thể tạm vẫn xử lý được, nhưng lỗi xuất hiện khi pool mở kết nối mới sau mạng chập chờn hoặc node chuyển đổi. Kiểm tra cả startup mới lẫn reconnect.

### 9.2. Rotate CA/server certificate

Khi thay CA hoặc chứng chỉ server:

- Phân phối truststore tạm thời **tin cả CA cũ và CA mới** trong giai đoạn chuyển tiếp, nếu chính sách tin cậy cho phép.
- Thay chứng chỉ trên Cassandra server theo thứ tự được vận hành kiểm soát.
- Rollout client với truststore mới, xác nhận xác thực server/hostname và reconnect.
- Bỏ CA cũ khỏi truststore khi không server hợp lệ nào còn dùng chứng chỉ cũ.

Một client chỉ tin CA mới trong khi một số server vẫn phục vụ certificate ký bởi CA cũ có thể mất kết nối từng node. Ngược lại, tin CA cũ vĩnh viễn không phải kế hoạch xoay vòng hoàn chỉnh.

Với **mTLS**, cần thêm lifecycle của **client certificate/private key** và server truststore tin CA ký cho client. Khi client certificate gần hết hạn, gia hạn trước, triển khai cùng khóa mới và kiểm tra handshake. Không copy private key qua email/chat hoặc hệ thống log.

### 9.3. Không kỳ vọng hot reload tự động

Trong ví dụ `CassandraTlsConfiguration`, `SSLContext` được tạo **khi Spring context khởi tạo**, rồi cấp cho Driver. Khi file trên volume thay đổi, SSLContext đã tạo **không tự đọc lại**. Phương án mặc định phù hợp là rolling restart. Nếu cần không restart, phải xây dựng cơ chế **tái tạo session/SSLContext an toàn**, chuyển traffic và test reconnect kỹ càng; đây là một tính năng riêng, không có chỉ nhờ mount Secret.

## 10. Kiểm thử security configuration

Unit test repository bằng mock không thể xác minh kết nối TLS hoặc role Cassandra. Khi cần kiểm thử an toàn, xây dựng môi trường tích hợp có **authentication và TLS được bật thực sự**, chứa chứng chỉ và credential test tách biệt production.

### 10.1. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi | Điều chứng minh |
|---|---|---|
| Credential test hợp lệ, TLS/CA đúng | Kết nối, truy vấn trong quyền cho phép thành công | Authentication + TLS + authorization làm việc |
| Sai mật khẩu | Session/query không được xác thực | Không fail-open thành tài khoản mặc định |
| Role thiếu quyền SELECT | CQL bị từ chối | Quyền tối thiểu có hiệu lực |
| CA không tin cậy | Bắt tay TLS hoặc validation thất bại | Client không tin server tùy tiện |
| Certificate server sai SAN/hostname | Kết nối thất bại **khi hostname verification được bật** | Client kiểm tra đúng endpoint |
| Client certificate không hợp lệ khi mTLS bắt buộc | TLS handshake bị từ chối | Server kiểm tra danh tính client |
| Secret volume thiếu file | Startup fail rõ lỗi cấu hình | Không âm thầm dùng mật khẩu rỗng/fallback |
| Rotate rồi rolling restart | Instance mới kết nối bằng credential/cert mới | Quy trình deploy/rotation hoạt động |
| Tắt TLS khi server bắt buộc TLS | Không kết nối được | Không có đường cleartext fallback |

### 10.2. Ví dụ test cấu hình thiếu secret

Một cách đơn giản là kiểm tra rằng cấu hình production **bắt buộc** đường dẫn config tree tồn tại và tệp cần thiết được cấp. Với Spring Boot 3.x, thiếu thư mục của một `configtree:` không có `optional:` sẽ làm giai đoạn nạp config thất bại. Test còn phải kiểm tra trường hợp thư mục tồn tại nhưng thiếu một key, ví dụ `spring.cassandra.password`.

Không nên viết test rằng mọi profile đều dùng chung secret production, vì CI/dev có thể không được cấp quyền. Tạo **test-only credentials** và chứng chỉ riêng cho Cassandra tích hợp; không chụp nguyên nội dung secret vào test snapshot hay log assertions.

### 10.3. Xác minh cùng cấu hình ở Repository và Template

Với `@SpringBootTest` dùng một Cassandra integration environment có TLS/auth, có thể xác nhận:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.cassandra.core.CassandraTemplate;

@SpringBootTest
class CassandraSecurityIntegrationTest {
    @Autowired
    CustomerRepository repository;

    @Autowired
    CassandraTemplate template;

    @Test
    void repositoryAndTemplateUseConfiguredSession() {
        UUID id = UUID.randomUUID();
        // Test environment đã có bản ghi với id hoặc sử dụng fixture độc lập.
        // Phép gọi sau phải được thực hiện qua kết nối TLS/auth đã cấu hình.
        assertThat(repository).isNotNull();
        assertThat(template).isNotNull();

        // Thêm assertion truy vấn CQL thật và xác minh quyền trong test đầy đủ.
        // Không dùng "bean != null" làm bằng chứng TLS hoạt động.
    }
}
~~~

Đoạn mã này chỉ thể hiện **khung khởi tạo Spring context**, chưa chứng minh TLS hoạt động. Bài kiểm thử tích hợp hoàn chỉnh phải thực hiện truy vấn thực và tạo các tình huống âm tính trong ma trận trên. Việc inject được `CassandraTemplate` không đủ để khẳng định certificate/hostname đã được xác thực.

### 10.4. Lỗi cần quan sát khi test

Các tình huống có thể biểu hiện khác nhau theo Driver phiên bản và giai đoạn thất bại:

- Sai username/password hoặc role không có quyền: lỗi authentication/authorization từ Cassandra.
- CA không tin hoặc sai hostname: lỗi TLS/certificate trong handshake hoặc kết nối.
- Local datacenter/endpoint sai: Driver không tìm được node phù hợp.
- Keyspace chưa được tạo: lỗi schema/config, **không phải lỗi secret**.
- Cluster quá tải: timeout/`UnavailableException`, **không nên** sửa bằng cách tắt TLS.

Khi Java Driver trả `AllNodesFailedException`, xem nguyên nhân theo từng node (`getAllErrors()` trong các phiên bản hỗ trợ) để biết có lỗi TLS, network hay node không sẵn sàng. Không log toàn bộ property chứa password để tiện chẩn đoán.

## 11. Mẫu vận hành theo môi trường

| Môi trường | Nguồn secret | Cách đọc | Lưu ý |
|---|---|---|---|
| Local dev | Secret file riêng, không commit | Config tree / env từ công cụ dev | Chỉ dùng credential dev |
| CI/integration test | Secret do CI inject hoặc tạo test credential tạm | Env/volume | Không dùng secret production trong pipeline |
| Kubernetes staging | Kubernetes Secret đồng bộ từ secret manager | Read-only volume + configtree | Tách role và namespace staging |
| Kubernetes production | Secret manager + cơ chế cấp vào cluster được kiểm soát | Read-only volume + rollout | RBAC, audit, rotation, TLS validation |
| VM/bare metal | Protected file/agent của secret manager | File/SDK + quyền OS | Không dùng world-readable config |

Sự lựa chọn giữa biến môi trường, file mount, Secret Store CSI, External Secrets hoặc SDK secret manager phụ thuộc hạ tầng. Mẫu quan trọng không đổi: **repository không biết secret đến từ đâu**, Driver nhận cấu hình lúc khởi tạo session, và các bản sao bí mật được giới hạn cả thời gian sống lẫn phạm vi truy cập.

### 11.1. Khi dùng nhiều keyspace, cluster hoặc tenant

Một ứng dụng có thể truy cập nhiều cluster Cassandra bằng nhiều `CqlSession` được cấu hình riêng. Khi ấy:

- Mỗi session cần đúng endpoint, local DC, credentials, truststore và SSL policy.
- Không dùng nhầm secret production của cluster A cho cluster B.
- Đặt tên property và đường mount theo cluster để tránh va chạm, ví dụ `app.cassandra.primary.*` và `app.cassandra.analytics.*`.
- Tái sử dụng `CqlSession` theo vòng đời ứng dụng, tránh mở session mới cho từng request chỉ để “đọc lại mật khẩu”.

Từng repository/`CassandraTemplate` phải được gắn với session thích hợp; dự án nhiều datasource/session không thể giả định auto-configuration mặc định bao phủ tất cả. Kiểm tra cấu hình custom bean khi thêm cluster thứ hai.

### 11.2. Bảo mật và hiệu năng là hai mục tiêu cùng phải kiểm soát

TLS có chi phí handshake/CPU và cần cấu hình đúng pool/connection reuse. Không tắt TLS để đạt benchmark tốt hơn. Khi đánh giá hiệu năng Spring Data Cassandra, giữ nguyên auth/TLS, consistency, paging và topology giống production. Một phép đo qua connection local không TLS không đại diện cho API dùng `LOCAL_QUORUM` qua mạng thật.

Secret rotation/restart cần giám sát connection pool, thời gian tạo session, p95/p99 và tỷ lệ timeout để tránh quá nhiều Pod reconnect Cassandra cùng thời điểm.

## 12. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Commit username/password trong `application-prod.yml` | Secret lan rộng qua Git, fork và artifact | Chỉ dùng placeholder/configtree, rotate khi bị lộ |
| Cho mật khẩu vào command line hoặc CI echo | Bí mật xuất hiện trong log/process history | Secret binding, file mount, tắt debug in secret |
| Dùng Base64 và cho rằng đã mã hóa | Ai đọc được Secret vẫn giải mã được | RBAC, encryption at rest, kiểm soát API |
| Gộp credential app với superuser Cassandra | Lộ một ứng dụng thành toàn quyền cluster | Role theo ứng dụng và grant tối thiểu |
| Chỉ bật `spring.cassandra.ssl.enabled` | Có thể thiếu CA, hostname verification hoặc server TLS | Kiểm thử chain/SAN, TLS phía server và Driver |
| Trust-all certificate để sửa lỗi kết nối | Có thể kết nối tới server giả | Cấp CA đúng, sửa SAN/endpoint, giữ validation |
| Mount client private key cho mọi Pod | Tăng phạm vi lộ khóa | Chỉ cấp cho workload cần mTLS |
| Secret volume được update rồi cho rằng session đã đổi | Client còn dùng credentials/SSLContext cũ | Rollout hoặc cơ chế refresh được thiết kế riêng |
| Thu hồi credential cũ ngay khi tạo secret mới | Instance chưa rollout có thể mất kết nối | Overlap, rolling restart, kiểm tra trước khi revoke |
| Lấy “Spring context start” làm bằng chứng security | Chưa chắc query thành công, hostname đã validate | Test truy vấn thực, auth/role, CA/SAN âm tính |
| Dùng secret production để chạy unit/integration test | Rủi ro truy cập dữ liệu thật và lộ secret | Test-only roles/certificates, isolation |

## 13. Tình huống thực hành

**Tình huống A — Secret lộ qua Git.** Một lập trình viên phát hiện mật khẩu của Cassandra production trong commit cũ, nhưng file hiện tại đã đổi sang `${CASSANDRA_PASSWORD}`. Có cần làm thêm gì không?

**Gợi ý:** Có. Xem mật khẩu cũ là đã bị lộ; rotate/revoke theo quy trình sự cố, rà soát phạm vi phân phối và audit. Chỉ sửa file ở commit mới không thu hồi được bí mật đã xuất hiện trong lịch sử.

**Tình huống B — TLS kết nối được nhưng không tin server.** Người phát triển sửa lỗi `PKIX path building failed` bằng cách tạo `TrustManager` chấp nhận mọi chứng chỉ. Có chấp nhận được không?

**Gợi ý:** Không. Sửa truststore chứa CA đúng, certificate chain, SAN/hostname và cấu hình Driver để xác minh danh tính server. Kiểm thử một endpoint giả/mismatch phải bị từ chối.

**Tình huống C — Rotate Secret nhưng Pod vẫn dùng account cũ.** Kubernetes Secret đã cập nhật, nhưng log Cassandra vẫn cho thấy session đến từ role cũ. Vì sao?

**Gợi ý:** Cấu hình Spring và `CqlSession` có thể đã được tạo trước đó. Volume cập nhật không bảo đảm session tự nạp lại; rollout Pod hoặc refresh session đúng quy trình.

**Tình huống D — Quyền cấp quá rộng.** Một service chỉ đọc lịch sử đơn hàng nhưng dùng Cassandra superuser để tránh cấu hình GRANT. Có rủi ro gì?

**Gợi ý:** Khi service bị chiếm quyền, kẻ tấn công có thể truy cập/thay đổi nhiều tài nguyên hơn nhu cầu nghiệp vụ. Tạo role riêng chỉ có `SELECT` trên bảng/đối tượng cần thiết.

**Tình huống E — Bảo mật và paging.** Một API đọc bảng theo partition key với nhiều page; ứng dụng đã dùng TLS/auth đúng nhưng phát hiện query chậm do partition rất lớn. Có nên tắt TLS để giảm p99?

**Gợi ý:** Không. Xem thiết kế bucket/partition, page size, truy vấn và metrics Driver/Cassandra; bảo đảm transport security không phải biến cần đánh đổi để che lỗi mô hình dữ liệu.

**Tình huống F — mTLS.** Client đã có truststore tin CA của server nhưng Cassandra yêu cầu client certificate. Vì sao handshake vẫn fail?

**Gợi ý:** Truststore chỉ phục vụ tin server. Client còn cần certificate/private key hợp lệ và SSL context/Driver có `KeyManager`; server phải tin CA đã cấp certificate client.

## 14. Checklist triển khai

- [ ] Source và image không chứa mật khẩu, private key hoặc secret thật.
- [ ] Secret được cấp bởi cơ chế của môi trường; không xuất ra log/CI artifact.
- [ ] `spring.cassandra.username/password` được resolve từ env/configtree đúng Spring Boot version.
- [ ] Mount read-only, permission phù hợp UID/GID, không cấp cho container không liên quan.
- [ ] Cassandra server thực sự bật authentication/authorization cần thiết; role chỉ có quyền tối thiểu.
- [ ] TLS được bật ở server/client, truststore hợp lệ và xác minh server hostname/SAN.
- [ ] Nếu mTLS, keystore/private key client được bảo vệ và đã kiểm thử handshake.
- [ ] Actuator, logging, metrics, tracing và debug dump không công khai secret.
- [ ] Có quy trình rotate credential/certificate với overlap và rollout.
- [ ] Test âm tính cho sai password, thiếu quyền, CA không tin và SAN không khớp.
- [ ] Kết nối của repository, `CassandraTemplate` và custom `CqlSession` đều dùng cấu hình đã bảo vệ.
- [ ] Hiệu năng/timeout được đánh giá với TLS và consistency giống production.

## 15. Tổng kết

Khi dùng **Spring Data Cassandra**, việc lưu thông tin xác thực và chứng chỉ trong **cấu hình bí mật** giúp bảo vệ cả đường truy cập CQL lẫn vòng đời vận hành của ứng dụng. Spring Boot có thể nhận secret qua biến môi trường hoặc **config tree**; Kubernetes có thể mount Secret thành file; Java Driver dùng username/password cùng SSL context để kết nối đến Cassandra an toàn.

Điều quan trọng là **xác thực, phân quyền và TLS đều phải được cấu hình đúng**, secret không nằm trong Git/log/image, quyền role phù hợp với từng bảng truy vấn, và các đợt rotation có bước chuyển tiếp/rollout. Những biện pháp đó đi cùng thiết kế bảng theo partition key, tính nhất quán và paging; một cấu hình kết nối an toàn là nền tảng để repository và `CassandraTemplate` truy cập hệ thống phân tán một cách đúng đắn.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Data Cassandra Reference](https://docs.spring.io/spring-data/cassandra/reference/)
- [Apache Cassandra Documentation — Security](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/security.html)
- [Kubernetes Documentation — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [DataStax Java Driver 4.x — SSL](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/ssl/index.html)
