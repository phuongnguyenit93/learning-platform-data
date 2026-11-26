# TLS, truststore và xác minh chứng chỉ

Khi ứng dụng dùng **Spring Data Cassandra** truy cập Apache Cassandra qua `CassandraRepository`, `CassandraTemplate` hoặc CQL, các API này sử dụng **Java driver** và `CqlSession` để giao tiếp với cluster. Nếu đường truyền không được bảo vệ, truy vấn, thông tin xác thực và dữ liệu kết quả có thể bị quan sát hoặc thay đổi khi đi qua mạng.

**TLS (Transport Layer Security)** mã hóa kết nối giữa ứng dụng và Cassandra node, kiểm tra tính toàn vẹn của dữ liệu và cho phép client xác minh danh tính server. Tuy nhiên, bật TLS chưa đủ: một kết nối được mã hóa nhưng **không xác minh chứng chỉ và tên máy chủ** vẫn có thể kết nối đến điểm cuối giả mạo.

Bài học thuộc chương **Cấu hình kết nối**, tập trung vào **client-to-node TLS** cho CQL native transport (thường dùng cổng 9042), truststore, certificate chain, hostname verification và cấu hình Spring Boot/Java driver. TLS giữa các node Cassandra là phần cấu hình khác. Ví dụ về Spring Boot dựa trên nhánh **Spring Boot 3.5**; khi triển khai thực tế, cần đối chiếu tài liệu phiên bản đang sử dụng.

## 1. TLS bảo vệ điều gì?

Đường truyền từ ứng dụng đến Cassandra có thể chứa:

- Username/password của Cassandra authentication.
- CQL `SELECT`, `INSERT`, `UPDATE`, `DELETE` và bind parameters.
- Các bản ghi nghiệp vụ trong kết quả truy vấn.
- Metadata phục vụ kết nối và khám phá topology.

| Thuộc tính của TLS | Ý nghĩa |
|---|---|
| Confidentiality | Nội dung trao đổi được mã hóa trên đường truyền |
| Integrity | Phát hiện các thay đổi dữ liệu trái phép trong quá trình truyền |
| Server authentication | Client kiểm tra certificate chain và danh tính của Cassandra endpoint |
| Client authentication (tùy chọn) | Với mTLS, server cũng kiểm tra chứng chỉ của client |

TLS **không** thay thế quyền CQL, username/password (nếu cluster yêu cầu) hay quy tắc nhất quán (`LOCAL_QUORUM`, `ONE`, v.v.). TLS cũng không sửa các truy vấn thiếu partition key hoặc làm paging nhanh hơn.

```mermaid
flowchart LR
    A["Spring Data Cassandra<br/>Repository / Template"] --> B["Java Driver / CqlSession"]
    B --> C["TLS handshake"]
    C --> D["Cassandra node<br/>CQL native transport"]
    E["Client truststore<br/>Trusted CA"] -. "xác minh chuỗi" .-> C
    F["DNS/IP endpoint"] -. "so khớp SAN" .-> C
    G["Server keystore<br/>private key + certificate"] -.-> D
    H["Client keystore<br/>chỉ khi mTLS"] -.-> C
```

Một Java driver có thể kết nối **nhiều node** sau khi khám phá topology. Vì vậy, truststore và SAN phải phù hợp với **tất cả endpoint mà driver thực tế sử dụng**, không chỉ contact point đầu tiên.

## 2. Khóa, chứng chỉ và certificate chain

### 2.1. Chứng chỉ X.509 chứa gì?

Server certificate X.509 thường chứa:

- **Public key** gắn với server; private key tương ứng phải được bảo vệ trên node.
- **Issuer** (CA cấp chứng chỉ), chữ ký của issuer và khoảng thời gian hiệu lực.
- **Subject Alternative Name (SAN)**: tên DNS hoặc IP mà chứng chỉ được phép đại diện.
- Các extension như Key Usage/Extended Key Usage, trong đó có `serverAuth` khi phù hợp.

Server phải sở hữu private key để chứng minh danh tính trong TLS handshake; ứng dụng client **không cần và không nên có private key của Cassandra node**. Client chỉ cần các chứng chỉ công khai để kiểm tra.

Một PEM certificate thường có dạng:

```text
-----BEGIN CERTIFICATE-----
... nội dung base64 ...
-----END CERTIFICATE-----
```

Đây là minh họa định dạng, không phải chứng chỉ có thể sử dụng. Private key có dạng khác, chẳng hạn `-----BEGIN PRIVATE KEY-----`; tuyệt đối không commit private key thật vào Git hay đưa vào log.

### 2.2. Truststore khác keystore thế nào?

| Thành phần | Nội dung điển hình | Nơi sử dụng | Vai trò |
|---|---|---|---|
| **Server keystore** | Server certificate, chain và **private key** | Cassandra node | Chứng minh danh tính server |
| **Client truststore** | CA root/intermediate được tin cậy, hoặc trusted server certificate | Java driver/Spring Boot | Xác minh server |
| **Client keystore** | Client certificate và **private key** | Ứng dụng khi dùng mTLS | Chứng minh danh tính client |
| **Server truststore** | CA/chứng chỉ client được tin cậy | Cassandra node khi dùng mTLS | Xác minh client |

Với **TLS một chiều**, Cassandra cần server keystore và Java driver cần trust material đủ để xác minh server. **Client keystore không bắt buộc.** Với **mutual TLS (mTLS)**, mỗi bên phải có chứng chỉ/khóa và tin cậy chứng chỉ của bên còn lại theo chính sách.

Java có thể lưu vật liệu chứng chỉ/khóa ở nhiều định dạng:

- **PEM**: chứng chỉ hoặc private key dạng văn bản; thuận tiện khi mount Kubernetes Secret.
- **PKCS#12** (`.p12`, `.pfx`): container chứa certificate/key hoặc trusted certificate entries.
- **JKS** (`.jks`): kiểu Java KeyStore truyền thống.

Tên phần mở rộng tệp không bảo đảm đúng nội dung: `cassandra-truststore.p12` có thể chứa chỉ public CA certificate; `client.p12` có thể chứa private key và certificate. Phân biệt **vai trò** trước khi cấu hình.

### 2.3. CA và chuỗi chứng chỉ

Khi Cassandra trình một server certificate, Java driver phải xác minh chữ ký và dựng được chuỗi tin cậy tới **trust anchor** trong truststore. Ví dụ:

```text
Root CA (tin cậy trong client truststore)
  └── Intermediate CA
       └── cassandra-1.example.internal (server certificate)
```

Thông thường, ứng dụng tin vào **CA certificate**, không cần import riêng certificate của mỗi node nếu chúng được cấp bởi CA phù hợp. Server cần gửi chuỗi intermediate cần thiết; thiếu intermediate có thể làm certificate verification thất bại dù root CA đã có trong truststore.

Nếu cluster tự cấp self-signed certificate cho lab, có thể tin trực tiếp certificate tương ứng. Trong môi trường dài hạn, quản lý chứng chỉ qua CA và quy trình rotation thường dễ kiểm soát hơn.

**Không chuyển private key của CA hoặc server sang client truststore.** Chỉ dùng certificate công khai từ nguồn đã được xác thực.

## 3. Hostname verification: đúng CA chưa có nghĩa đúng server

Ngoài kiểm tra chữ ký, thời hạn và certificate chain, ứng dụng phải xác minh **endpoint hiện tại có tên đúng với chứng chỉ**.

Giả sử client đang mở kết nối tới `cassandra-1.example.internal`:

- Nếu SAN có `DNS:cassandra-1.example.internal`, danh tính hostname khớp.
- Nếu SAN chỉ có `DNS:cassandra-2.example.internal`, không được xem là cùng máy chủ.
- Nếu client kết nối bằng địa chỉ `10.20.30.11`, chứng chỉ chỉ có DNS SAN **không đủ** để xác minh IP; cần SAN loại `IP Address:10.20.30.11`.

| Host/IP mà driver dùng | SAN của certificate | Kết quả kỳ vọng |
|---|---|---|
| `cassandra-1.example.internal` | `DNS:cassandra-1.example.internal` | Khớp hostname |
| `cassandra-1.example.internal` | `DNS:cassandra-2.example.internal` | Không khớp |
| `10.20.30.11` | Chỉ có `DNS:cassandra-1.example.internal` | Không khớp IP |
| `10.20.30.11` | `IP:10.20.30.11` | Khớp IP |

Bảng chỉ nói về **hostname matching**; TLS vẫn có thể thất bại nếu CA không tin cậy, certificate hết hạn hoặc bị từ chối vì các quy tắc khác.

**Ưu tiên SAN trong thiết kế chứng chỉ mới**, không phụ thuộc vào Subject Common Name (CN) như cơ chế thay thế. Giữ `verify-hostname: true`; sửa DNS, certificate SAN hoặc địa chỉ quảng bá thay vì tắt xác minh tên để “cho kết nối chạy”.

### 3.1. Lưu ý về cluster và discovery

`spring.cassandra.contact-points` là danh sách điểm vào ban đầu. Sau khi tìm hiểu topology, Java driver có thể mở kết nối đến địa chỉ của từng node/replica được quảng bá. Do đó:

1. Chứng chỉ của mỗi node phải bao phủ tên DNS/IP mà driver thực sự kết nối.
2. Các địa chỉ như `broadcast_rpc_address` và cấu hình dịch địa chỉ (nếu có) phải phù hợp mạng ứng dụng.
3. Nếu dùng load balancer, proxy hay dịch vụ managed, cần xác định TLS kết thúc tại đâu và tên endpoint được xác minh là tên nào.

Có thể **khởi tạo session thành công nhưng truy vấn sau đó lỗi TLS** khi driver chuyển sang node có SAN sai, CA khác hoặc chứng chỉ hết hạn. Khi chẩn đoán, hãy ghi nhận endpoint node trong log driver.

## 4. Bật TLS tại Cassandra server

Trong Cassandra tự quản lý, client-to-node TLS được cấu hình tại `client_encryption_options` của `cassandra.yaml`. Ví dụ minh họa cho môi trường tự quản lý với Cassandra 5.0, **sau khi** người vận hành đã tạo server keystore PKCS#12 và cấp quyền đọc file:

```yaml
client_encryption_options:
  enabled: true
  optional: false
  keystore: /etc/cassandra/tls/server.p12
  keystore_password_file: /etc/cassandra/secrets/server-keystore-password
  store_type: PKCS12
  require_client_auth: false
```

Ý nghĩa:

- `enabled: true`: bật mã hóa client-to-node.
- `optional: false`: từ chối kết nối plaintext sau khi các client đã chuyển sang TLS.
- `keystore`: chứa server certificate, chain và private key.
- `keystore_password_file`: file chứa mật khẩu được bảo vệ; cần đối chiếu hỗ trợ theo phiên bản Cassandra, nhất là nếu chạy bản cũ.
- `require_client_auth: false`: chưa bắt buộc client certificate, tức TLS một chiều.

| `enabled` | `optional` | Chế độ |
|---|---|---|
| `false` | — | Không bật TLS client-to-node |
| `true` | `true` | Cho phép TLS và plaintext trong giai đoạn chuyển đổi |
| `true` | `false` | Chỉ chấp nhận kết nối TLS |

**Triển khai trên cluster đang hoạt động:** cấp chứng chỉ và chuẩn bị client trước; có thể cho phép cả hai giao thức trong giai đoạn chuyển đổi có kiểm soát, xác minh client dùng TLS rồi mới tắt plaintext. Việc cập nhật `cassandra.yaml`, phân phối certificate, restart/reload và rollback cần quy trình vận hành theo phiên bản cluster.

**TLS giữa các node** dùng `server_encryption_options`, độc lập với `client_encryption_options`. Cổng 9042 thường dùng cho CQL native transport, nhưng **số cổng không tự chứng minh kết nối có TLS**.

### 4.1. Mở rộng sang mTLS

Khi Cassandra yêu cầu client certificate, chẳng hạn `require_client_auth: true` ở phiên bản phù hợp:

- Server cần trust CA/chứng chỉ cấp cho client.
- Ứng dụng Java cần client certificate và private key trong client keystore hoặc PEM bundle.
- Java driver vẫn phải tin CA/chứng chỉ server và kiểm tra hostname.
- Cassandra username/password, roles và authorization vẫn là cơ chế riêng; cách kết hợp tùy cấu hình authenticator.

Không đưa server private key vào ứng dụng để đáp ứng mTLS. Phải dùng cặp khóa và certificate được cấp **cho client**.

## 5. Spring Boot 3.5: cấu hình TLS bằng SSL bundle

Ứng dụng có `spring-boot-starter-data-cassandra` thường nhận `CqlSession` auto-configured. Trong Spring Boot 3.5, các property liên quan gồm:

- `spring.cassandra.ssl.enabled`: yêu cầu sử dụng SSL/TLS.
- `spring.cassandra.ssl.verify-hostname`: xác minh tên endpoint, nên giữ `true`.
- `spring.cassandra.ssl.bundle`: chọn SSL bundle với trust material.
- `spring.ssl.bundle.pem.*` / `spring.ssl.bundle.jks.*`: định nghĩa chứng chỉ hoặc truststore.

Giả định cluster có node `cassandra-1.example.internal` và `cassandra-2.example.internal`, datacenter thực là `dc1`, keyspace `sales`. Chứng chỉ CA đáng tin cậy được mount ở `/run/secrets/cassandra-ca.pem` trong **container ứng dụng**.

### 5.1. Phương án A — PEM truststore

```yaml
spring:
  cassandra:
    contact-points: cassandra-1.example.internal,cassandra-2.example.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: sales
    ssl:
      enabled: true
      verify-hostname: true
      bundle: cassandra-ca

  ssl:
    bundle:
      pem:
        cassandra-ca:
          truststore:
            certificate: "file:/run/secrets/cassandra-ca.pem"
```

PEM truststore này chứa **CA certificate công khai**, không cần private key phía client nếu chỉ dùng TLS một chiều. `file:/...` được giải quyết trên máy/container đang chạy JVM Spring Boot; nếu ứng dụng dùng Docker hoặc Kubernetes, file phải được mount đến đúng vị trí và cấp quyền đọc phù hợp.

### 5.2. Phương án B — Java PKCS#12 truststore

Nếu tổ chức quản lý truststore bằng `keytool`, có thể dùng SSL bundle loại JKS với container PKCS#12:

```yaml
spring:
  cassandra:
    contact-points: cassandra-1.example.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: sales
    ssl:
      enabled: true
      verify-hostname: true
      bundle: cassandra-store

  ssl:
    bundle:
      jks:
        cassandra-store:
          truststore:
            location: "file:/run/secrets/cassandra-truststore.p12"
            type: PKCS12
            password: "${CASSANDRA_TRUSTSTORE_PASSWORD}"
```

Trong file `application.yml` thực tế, placeholder mật khẩu là `${CASSANDRA_TRUSTSTORE_PASSWORD}`: Spring Boot đọc giá trị từ biến môi trường do runtime/secret manager cấp. **Không đặt mật khẩu thật trong Git hoặc trong mẫu tài liệu.**

**Chỉ chọn một phương án** (PEM hoặc PKCS#12) cho session đang được cấu hình. Hai ví dụ nêu hai cách biểu diễn cùng khái niệm **client trust material**.

### 5.3. Chú ý về phiên bản

Các property `ssl.bundle` và `ssl.verify-hostname` của Cassandra đã được tài liệu Spring Boot 3.5 mô tả. Với Spring Boot/Spring Data Cassandra đời cũ, cần kiểm tra lại API và tên property trước khi áp dụng. Nếu ứng dụng tự tạo bean `CqlSession` hoặc có nhiều session, phải bảo đảm TLS được cấu hình **trên session thực sự được repository/template sử dụng**.

Một số môi trường sử dụng cloud Cassandra có yêu cầu kết nối riêng như secure connection bundle, endpoint/port khác hoặc chính sách certificate riêng. Không tự suy đoán các property trên đủ cho mọi dịch vụ managed.

## 6. Tạo truststore PKCS#12 bằng keytool

Giả sử bạn nhận một **CA certificate công khai** `cassandra-ca.crt` từ đội vận hành. Trước khi import, đối chiếu nguồn cấp và **SHA-256 fingerprint** qua kênh tin cậy.

In thông tin certificate:

```bash
keytool -printcert -file cassandra-ca.crt
```

Tạo truststore PKCS#12:

```bash
keytool -importcert \
  -trustcacerts \
  -alias cassandra-ca \
  -file cassandra-ca.crt \
  -keystore cassandra-truststore.p12 \
  -storetype PKCS12
```

Khi được hỏi, nhập mật khẩu truststore tương tác. Tránh đưa mật khẩu vào command line vì có thể lộ qua process list hoặc shell history.

Kiểm tra:

```bash
keytool -list -v \
  -keystore cassandra-truststore.p12 \
  -storetype PKCS12
```

Alias `cassandra-ca` nên là trusted certificate entry; không cần private key trong truststore này. Đưa file `.p12` và mật khẩu tới môi trường Spring Boot qua cơ chế secret/volume phù hợp.

Không dùng thao tác import chỉ để tin một server certificate mới gặp trên mạng mà chưa xác minh fingerprint và nguồn; làm như vậy phá hỏng mục đích của certificate validation.

## 7. Java driver 4.x: cấu hình SSL engine trực tiếp

Khi không dùng Spring Boot auto-configuration hoặc cần tùy biến sâu hơn, Apache Cassandra Java Driver 4.x hỗ trợ `DefaultSslEngineFactory`. Ví dụ **HOCON config** của driver:

```hocon
datastax-java-driver {
  advanced.ssl-engine-factory {
    class = DefaultSslEngineFactory
    truststore-path = "/run/secrets/cassandra-truststore.jks"
    truststore-password = ${?CASSANDRA_TRUSTSTORE_PASSWORD}
    hostname-validation = true
  }
}
```

Tại HOCON thực tế, `${?CASSANDRA_TRUSTSTORE_PASSWORD}` là cú pháp lấy biến môi trường tùy chọn theo HOCON, **không phải chuỗi mật khẩu**; đảm bảo biến đó đã tồn tại để driver nạp truststore. Ví dụ chọn file `.jks` khi file thực tế là JKS; nếu dùng PKCS#12, phải bảo đảm loader/Java runtime và cấu hình loại store phù hợp.

Java driver cũng có thể nhận `SSLContext` hoặc `SslEngineFactory` lập trình thông qua `CqlSession.builder()`, ví dụ `withSslContext(sslContext)`. Nếu tự tùy biến factory, phải tiếp tục áp dụng hostname verification đúng cách; không dùng trust manager chấp nhận mọi certificate.

Trong Spring Boot, `spring.cassandra.config` có thể hỗ trợ nạp cấu hình driver; các property `spring.cassandra.*` có thể có mức ưu tiên cao hơn cấu hình driver trùng nội dung. Nên chọn một nguồn cấu hình chính và kiểm tra session thực được tạo, tránh bundle và HOCON đưa giá trị TLS mâu thuẫn.

## 8. mTLS: khi client cũng phải trình chứng chỉ

TLS một chiều cho phép client xác minh server. Với **mTLS**, server còn yêu cầu client chứng minh sở hữu private key tương ứng client certificate.

```mermaid
sequenceDiagram
    participant App as Java driver
    participant DB as Cassandra node
    App->>DB: ClientHello
    DB-->>App: Server certificate và chain
    Note over App: Kiểm tra CA, hiệu lực, SAN, hostname
    DB-->>App: CertificateRequest (nếu mTLS)
    App->>DB: Client certificate và chứng minh private key
    Note over DB: Xác minh client certificate bằng server truststore
    App->>DB: CQL request qua TLS
    DB-->>App: CQL response qua TLS
```

Với Spring Boot PEM SSL bundle, có thể cấp đồng thời CA certificate và client keypair:

```yaml
spring:
  ssl:
    bundle:
      pem:
        cassandra-mtls:
          truststore:
            certificate: "file:/run/secrets/cassandra-ca.pem"
          keystore:
            certificate: "file:/run/secrets/client.crt"
            private-key: "file:/run/secrets/client.key"

  cassandra:
    ssl:
      enabled: true
      verify-hostname: true
      bundle: cassandra-mtls
```

Đây chỉ là phần **TLS** của cấu hình: ứng dụng còn cần contact points, datacenter, keyspace và authentication thích hợp. Server phải tin CA đã cấp `client.crt`. Private key client cần được cấp quyền file hạn chế và quản lý vòng đời an toàn.

## 9. Kiểm tra kết nối có thực sự xác minh chứng chỉ không?

### 9.1. Kiểm tra mạng và certificate chain bằng OpenSSL

Trước khi xem code Spring, cần xác nhận DNS và đường mạng đến cổng CQL. Kết nối TCP thành công **chưa chứng minh** TLS hoạt động.

Với OpenSSL hỗ trợ các tham số dưới đây:

```bash
openssl s_client \
  -connect cassandra-1.example.internal:9042 \
  -servername cassandra-1.example.internal \
  -CAfile /run/secrets/cassandra-ca.pem \
  -verify_hostname cassandra-1.example.internal \
  -verify_return_error \
  -showcerts
```

| Tham số | Tác dụng |
|---|---|
| `-connect` | Endpoint thực tế đang kiểm tra |
| `-servername` | SNI nếu proxy/endpoint xử lý SNI |
| `-CAfile` | CA certificate dùng để xác minh chuỗi |
| `-verify_hostname` | So khớp tên DNS trên certificate |
| `-verify_return_error` | Báo lỗi và dừng xác minh khi certificate không đạt |
| `-showcerts` | In chuỗi certificate mà server trình |

Kết quả `Verify return code: 0 (ok)` là dấu hiệu certificate chain và hostname verification đạt trong lần thử đó. Đừng chỉ dựa vào dòng “CONNECTED”, vì kết nối socket có thể thành công trong khi validation vẫn lỗi.

Nếu được cung cấp tệp server certificate công khai, xem SAN và thời hạn bằng:

```bash
openssl x509 -in cassandra-server.crt \
  -noout -subject -issuer -dates -ext subjectAltName
```

Lệnh này xem file được cung cấp, còn `openssl s_client` kiểm tra chứng chỉ **thực sự** được endpoint trả về. Với cluster nhiều node, kiểm tra từng địa chỉ mà Java driver có thể dùng.

### 9.2. Kiểm tra bằng cqlsh

Apache Cassandra `cqlsh` có `--ssl`; nếu dùng private CA, có thể cấu hình `~/.cassandra/cqlshrc`:

```ini
[connection]
hostname = cassandra-1.example.internal
port = 9042

[ssl]
certfile = /run/secrets/cassandra-ca.pem
validate = true
```

Sau đó:

```bash
cqlsh cassandra-1.example.internal 9042 --ssl
```

`certfile` trong mục `[ssl]` là CA/trust material để xác minh server, **không phải private key client**. Với mTLS, các tham số như `usercert` và `userkey` có vai trò riêng. Kiểm tra `cqlsh --help` và `conf/cqlshrc.sample` theo phiên bản được cài nếu cú pháp có khác biệt.

Khi vào cqlsh, thử một truy vấn đọc nhỏ:

```sql
SELECT release_version, data_center FROM system.local;
```

cqlsh dùng TLS thành công **không có nghĩa** ứng dụng Java đã nạp cùng truststore: hai client có thể khác đường dẫn certificate, CA mặc định và quy tắc cấu hình.

### 9.3. Kiểm tra từ CqlSession của Spring Data

Khi Spring Boot đã có `CqlSession`, có thể viết phép smoke test đọc một row metadata:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import org.springframework.stereotype.Component;

@Component
public class CassandraTlsProbe {
    private final CqlSession session;

    public CassandraTlsProbe(CqlSession session) {
        this.session = session;
    }

    public String readReleaseVersion() {
        Row row = session.execute(
            "SELECT release_version FROM system.local"
        ).one();

        if (row == null) {
            throw new IllegalStateException("Không đọc được system.local");
        }
        return row.getString("release_version");
    }
}
```

Đây là method minh họa, chỉ gọi tại thời điểm phù hợp, chẳng hạn smoke test hoặc readiness có kiểm soát. Nó chứng minh session thực hiện được CQL tại thời điểm gọi. Để khẳng định hostname verification đang bật, vẫn phải kiểm tra cấu hình SSL thật của session và chứng chỉ được dùng khi kết nối.

Repository, `CassandraTemplate` và `CqlSession` thường chia sẻ cơ chế kết nối khi dùng auto-configuration. **TLS handshake diễn ra trước khi câu CQL và entity mapping được xử lý**; lỗi TLS không thể sửa bằng thay đổi `@PrimaryKey` hay repository query.

## 10. Chẩn đoán lỗi TLS thường gặp

Các exception từ driver có thể bao bọc lỗi gốc. Hãy tìm `SSLHandshakeException`, `CertificateException` và những dòng `Caused by` liên quan trước khi kết luận.

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `PKIX path building failed` | CA không nằm trong truststore, thiếu intermediate | Xác nhận CA, chain và bundle thực đang được nạp |
| `No subject alternative DNS name matching` | DNS endpoint không thuộc SAN | Sửa DNS/endpoint hoặc cấp lại certificate đúng SAN |
| `No subject alternative names matching IP` | Dùng IP trong khi cert chỉ có DNS SAN | Kết nối bằng DNS hợp lệ hoặc cấp certificate có IP SAN |
| `CertificateExpiredException` / `NotYetValidException` | Certificate hết hạn, chưa hiệu lực hoặc clock sai | Xem `Not Before/After` và đồng bộ thời gian |
| `Received fatal alert: bad_certificate` | Client cert sai, bị từ chối hoặc thiếu trust ở phía server | Kiểm tra client keystore, chain, yêu cầu mTLS |
| `handshake_failure` | Protocol/cipher không tương thích hoặc mTLS thiếu cert | Xem phiên bản JVM, cipher policy, log hai phía |
| `Unrecognized SSL message, plaintext connection?` | Client dùng TLS với server/port plaintext | Xác định đúng `client_encryption_options` và port |
| `Connection reset` / `Unable to connect` | Firewall, proxy, node chưa sẵn sàng hoặc TLS mismatch | Kiểm tra TCP, OpenSSL, node và client logs |
| Contact point kết nối được, query sau lỗi | Node khám phá tiếp theo có SAN/CA/địa chỉ sai | Kiểm tra chứng chỉ và advertised address từng node |
| `AuthenticationException` / `Unauthorized` sau handshake | Credentials hoặc quyền CQL sai | Điều tra Cassandra authentication, roles; không tự xem là lỗi TLS |

Quy trình xử lý:

1. **Xác định endpoint thực tế**: DNS/IP, port, node, network và có qua proxy hay load balancer không.
2. **Kiểm tra TCP**, sau đó kiểm tra **TLS handshake độc lập** bằng OpenSSL với CA và hostname tương ứng.
3. **Xem certificate chain, SAN và thời hạn** ở mọi node mà driver có thể chọn.
4. **Kiểm tra cấu hình Java runtime**: đúng bundle, truststore, định dạng, password, đường dẫn mount và quyền đọc.
5. **Xem stack trace gốc**, tách lỗi TLS khỏi lỗi authentication hoặc query.
6. **Kiểm tra lại session và query** sau khi sửa, không chỉ dựa vào lần khởi động đầu tiên.

Không giải quyết lỗi `PKIX` hoặc SAN mismatch bằng việc dùng `TrustAll`, tắt `validate` hay `verify-hostname` rồi đưa cấu hình đó vào production. Những cách này bỏ qua bước xác minh điểm cuối và làm yếu bảo vệ TLS.

### 10.1. Khi lỗi chỉ xuất hiện ở production

Các tình huống phổ biến:

- File CA có trên laptop nhưng **chưa được mount** vào container ứng dụng.
- Cluster đã xoay CA, ứng dụng vẫn dùng truststore cũ.
- DNS nội bộ hoặc ingress thay đổi tên, nhưng certificate SAN chưa cập nhật.
- Node mới tham gia cluster dùng certificate khác hoặc quảng bá IP không nằm trong SAN.
- JVM và chính sách TLS/cipher khác giữa local và production.

Khi lỗi xảy ra ngắt quãng, hãy nhóm log theo **endpoint node** và thời điểm certificate rotation để xác định phần cluster gặp sự cố.

## 11. Vòng đời chứng chỉ và rotation

Chứng chỉ có thời hạn. Một quy trình rotation có kiểm soát gồm:

1. Theo dõi hạn của server certificate, CA và client certificate (nếu mTLS).
2. Khi thay CA, phân phối truststore chứa **CA cũ và CA mới** trong giai đoạn chuyển đổi, nếu chính sách cho phép.
3. Cấp server certificates mới với **SAN đúng** các endpoint sẽ được driver sử dụng.
4. Xác nhận các kết nối **mới** của client kiểm tra thành công chuỗi và hostname.
5. Sau khi mọi server/client đã chuyển đổi, loại CA cũ theo lịch rõ ràng.

Một số phiên bản Cassandra có **hot reload** SSL key/trust material và lệnh `nodetool reloadssl`. Khả năng reload của **ứng dụng Java** phụ thuộc driver, Spring Boot, SSL bundle và cách session được tạo. Không tự suy ra rằng sửa tệp trên đĩa khiến mọi kết nối Java đang mở được xác minh lại ngay; có thể cần khởi tạo lại session hoặc restart ứng dụng theo kế hoạch.

Giữ bí mật private key và mật khẩu truststore/keystore. Trong log, chỉ ghi các thông tin đủ để điều tra như endpoint, loại lỗi handshake và fingerprint certificate đã kiểm chứng, tránh in secret hoặc toàn bộ nội dung key material.

## 12. Bài tập và tự kiểm tra

### Bài 1 — Chọn đúng kho chứng chỉ

Bạn có ba file: `server.p12` chứa server private key và chain; `ca.pem` chứa CA công khai; `client.p12` chứa client keypair. Hỏi ứng dụng cần file nào cho TLS một chiều? Khi nào cần `client.p12`?

**Đáp án:** TLS một chiều: ứng dụng cần tin `ca.pem` (qua PEM bundle hoặc truststore). `server.p12` thuộc Cassandra node. `client.p12` chỉ cần khi server yêu cầu client certificate cho mTLS.

### Bài 2 — Xử lý SAN mismatch

Driver dùng `10.30.2.8:9042`, còn cert chỉ có `DNS:cassandra-2.example.internal`. Root CA đã import, nhưng có lỗi SAN IP mismatch.

**Đáp án:** Sửa endpoint sang DNS hợp lệ nếu mạng và discovery hỗ trợ, hoặc cấp cert có `IP:10.30.2.8` trong SAN. Không tắt hostname verification.

### Bài 3 — Cấu hình Spring Boot

Tạo `application.yml` với `spring.cassandra.ssl.enabled: true`, `verify-hostname: true` và PEM bundle trỏ `file:/run/secrets/cassandra-ca.pem`. Dùng OpenSSL xác minh hostname và chạy một query `system.local` qua `CqlSession`.

**Câu hỏi:** Tại sao query chạy thành công chưa đủ để biết hostname verification được bật? Vì một kết nối có thể được thiết lập theo cấu hình bỏ xác minh tên; phải kiểm tra property và SSL context/session thực.

### Bài 4 — Lỗi ngắt quãng ở cluster ba node

Contact point kết nối thành công nhưng những lần sau báo `SSLHandshakeException`.

**Hướng giải:** Kiểm tra endpoint driver chọn sau discovery, certificate SAN/CA của từng node, ngày hiệu lực và truststore đã được ứng dụng nạp.

### Bài 5 — Kế hoạch đổi CA

Viết thứ tự chuyển từ CA cũ sang CA mới cho cluster đang hoạt động. Giải thích tại sao cần khoảng thời gian tin đồng thời hai CA trong quá trình chuyển đổi và khi nào phải tạo lại kết nối Java.

### Tóm lược kiến thức

- **Truststore** cho biết client tin CA/chứng chỉ nào; **keystore** chứa certificate và private key để bên sở hữu tự chứng minh danh tính.
- **Hostname verification** phải kiểm tra SAN của endpoint DNS/IP thực tế, bao gồm các node Cassandra được khám phá.
- **Spring Boot 3.5** có thể cấu hình Cassandra TLS bằng `spring.cassandra.ssl.*` và **SSL bundle** PEM/JKS.
- **mTLS** cần thêm client certificate/key và cấu hình server tin cậy client certificate.
- Kiểm chứng theo thứ tự **mạng → TLS → authentication → CQL**; khi rotate chứng chỉ, kiểm tra cả server lẫn ứng dụng.

## Tài liệu tham khảo

- [Apache Cassandra — Security](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/security.html): TLS client-to-node, mTLS và certificate reload.
- [Apache Cassandra — cassandra.yaml Configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `client_encryption_options` và thiết lập SSL phía node.
- [Apache Cassandra Java Driver 4.19 — SSL](https://apache.github.io/cassandra-java-driver/4.19.0/core/ssl/): `DefaultSslEngineFactory`, truststore, keystore, hostname validation.
- [Spring Boot 3.5 — Cassandra](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html#data.nosql.cassandra): `spring.cassandra.ssl.*`, `CqlSession` và SSL bundle.
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): PEM và JKS/PKCS#12 trust material.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `--ssl` và `cqlshrc`.
- [Apache Cassandra — cqlshrc.sample](https://github.com/apache/cassandra/blob/trunk/conf/cqlshrc.sample): `[ssl]`, `certfile`, `validate`, `usercert` và `userkey`.
- [Oracle JDK — keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): tạo và kiểm tra trusted certificate entries.
