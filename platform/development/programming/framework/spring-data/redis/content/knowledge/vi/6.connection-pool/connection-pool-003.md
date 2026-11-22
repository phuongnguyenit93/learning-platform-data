# Bảo vệ kết nối bằng TLS và xác minh chứng chỉ

Ứng dụng Spring Data Redis thường gửi khóa, giá trị, mật khẩu xác thực và lệnh Redis qua kết nối mạng. Nếu dùng TCP không mã hóa, những byte này có thể bị quan sát hoặc thay đổi bởi tác nhân kiểm soát đường truyền. **TLS (Transport Layer Security)** bảo vệ dữ liệu trên đường đi và giúp client xác nhận rằng nó đang giao tiếp với Redis Server đúng danh tính.

Bật TLS chỉ là bước đầu. Một kết nối an toàn cần đồng thời **mã hóa đường truyền, kiểm tra chuỗi tin cậy của chứng chỉ, kiểm tra tên máy chủ và duy trì cấu hình xác thực phù hợp**. Bỏ qua bước xác minh chứng chỉ có thể khiến kết nối vẫn được mã hóa nhưng client không biết chính xác mình đang nói chuyện với máy chủ nào.

Bài học này trình bày cơ chế TLS trong chu kỳ kết nối Redis, cách cấu hình với Spring Boot và Spring Data Redis, vai trò của CA/truststore, mutual TLS, thao tác kiểm tra và hướng điều tra lỗi trong môi trường standalone, Sentinel hoặc Cluster.

## 1. Vì sao Redis cần TLS?

Redis dùng giao thức RESP trên kết nối mạng. Trong triển khai thông thường, kết nối có thể là TCP thuần hoặc TCP được bảo vệ bằng TLS. Nếu dùng TCP thuần, toàn bộ lệnh và dữ liệu RESP được truyền mà không có cơ chế mã hóa từ chính Redis.

Ví dụ một lệnh:

```redis
SET session:1001 abcdef
```

Nếu client dùng kết nối TCP không TLS, nội dung khóa và giá trị có thể hiện diện dưới dạng byte dễ đọc trên mạng. Bên cạnh đó, lệnh `AUTH` hoặc thông tin xác thực bằng ACL không tự tạo ra kênh truyền được mã hóa.

TLS bổ sung ba thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa đối với kết nối Redis |
|---|---|
| **Confidentiality — tính bí mật** | Bên thứ ba trên mạng không đọc được nội dung lệnh và phản hồi nếu TLS được triển khai đúng. |
| **Integrity — tính toàn vẹn** | Dữ liệu đang truyền được bảo vệ khỏi việc thay đổi trái phép mà không bị phát hiện. |
| **Server authentication — xác thực máy chủ** | Client có thể kiểm tra chứng chỉ và tên máy chủ để giảm nguy cơ kết nối tới máy chủ giả mạo. |

TLS **không thay thế Redis ACL**, kiểm soát quyền, firewall, private network, chính sách lưu bí mật, phân quyền dữ liệu hay quản lý vòng đời khóa. Một kết nối TLS hợp lệ vẫn có thể bị từ chối nếu user Redis không có quyền chạy `GET` hoặc `SET`.

### 1.1. TCP, TLS và Redis nằm ở các tầng nào?

```text
Ứng dụng Java: RedisTemplate / StringRedisTemplate
             ↓
Spring Data Redis + Lettuce/Jedis
             ↓
Redis Serialization Protocol (RESP)
             ↓
TLS: handshake, certificate validation, encrypted records
             ↓
TCP / mạng
             ↓
Redis Server (TLS listener)
```

TLS tạo kênh bảo vệ trước khi ứng dụng gửi các lệnh Redis theo cách thông thường. Khi kết nối thiết lập thành công, RESP vẫn là định dạng request–response được truyền trong kênh TLS; **TLS không biến Redis thành HTTP hay HTTPS**.

Redis Open Source hỗ trợ TLS từ **Redis 6.0**, với điều kiện bản Redis đang chạy được biên dịch/phân phối có hỗ trợ TLS và cấu hình TLS được bật. Một dịch vụ Redis managed có thể cung cấp endpoint TLS mặc định hoặc bắt buộc dùng TLS, tùy nhà cung cấp.

## 2. Phân biệt mã hóa, xác minh chứng chỉ và mTLS

Ba khái niệm thường bị trộn lẫn khi cấu hình.

### 2.1. Mã hóa nhưng không xác minh danh tính là chưa đủ

Khi bắt tay TLS, server đưa ra một chứng chỉ X.509 cùng thông tin cần thiết cho quá trình bắt tay. Client phải quyết định có tin máy chủ đó hay không.

Một cấu hình bỏ qua xác minh có thể tạo ra đường truyền được mã hóa, nhưng **không bảo đảm endpoint là máy chủ dự kiến**. Tác nhân trung gian có thể dùng chứng chỉ khác để đóng vai máy chủ nếu client chấp nhận mọi chứng chỉ.

Kết nối bảo vệ đúng phải kiểm tra ít nhất:

1. **Chuỗi tin cậy:** chứng chỉ server dẫn tới một CA hoặc trust anchor mà client tin cậy.
2. **Thời hạn:** chứng chỉ đang còn hiệu lực, theo đồng hồ hệ thống.
3. **Danh tính endpoint:** hostname/IP mà client kết nối phù hợp tên được chứng nhận, thông thường ở trường **Subject Alternative Name (SAN)**.
4. **Quy định sử dụng khóa và chính sách TLS:** chuỗi chứng chỉ, thuật toán và tham số giao thức đáp ứng chính sách của runtime.

Nếu client gọi `redis.internal.example`, chứng chỉ có `DNS:redis.internal.example` là trường hợp điển hình. Chỉ có chứng chỉ cho `redis-public.example` không đủ cho endpoint đó, ngay cả khi hai hostname hiện cùng trỏ đến một IP.

### 2.2. Một chiều TLS và mutual TLS (mTLS)

| Cơ chế | Server trình chứng chỉ? | Client trình chứng chỉ? | Phía nào xác minh? |
|---|---|---|---|
| **TLS xác thực server** | Có | Không bắt buộc | Client kiểm tra chứng chỉ và danh tính Redis Server. |
| **Mutual TLS (mTLS)** | Có | Có | Client kiểm tra server; server đồng thời kiểm tra chứng chỉ client. |
| **Redis ACL qua TLS** | Có | Không nhất thiết | Redis xử lý username/password/quyền sau khi có kết nối; không đồng nghĩa mTLS. |

Mối quan hệ ở mức kết nối:

```mermaid
sequenceDiagram
    participant App as Spring Data Redis / Driver
    participant Redis as Redis TLS Listener
    App->>Redis: TCP connect
    App->>Redis: TLS ClientHello (có thể mang SNI)
    Redis-->>App: TLS ServerHello + chứng chỉ server
    Note over App: Kiểm tra CA, hạn, SAN, chính sách TLS
    opt Server yêu cầu mTLS
        Redis-->>App: Yêu cầu chứng chỉ client
        App->>Redis: Chứng chỉ client + chứng minh có private key
        Note over Redis: Kiểm tra chuỗi chứng chỉ client và quyền tin cậy
    end
    Note over App,Redis: Hoàn tất handshake, lập kênh TLS
    App->>Redis: Lệnh Redis (RESP bên trong TLS)
    Redis-->>App: Phản hồi Redis (RESP bên trong TLS)
```

Redis Open Source khi được cấu hình hỗ trợ TLS có mặc định **yêu cầu client certificate**, trừ khi đặt `tls-auth-clients no`. Vì vậy, một ứng dụng chỉ cấu hình truststore đôi khi vẫn bị lỗi handshake: server đang đòi **mTLS**, không chỉ server authentication.

## 3. Những loại chứng chỉ và kho khóa cần biết

### 3.1. CA, certificate chain và SAN

- **CA certificate:** chứng chỉ của cơ quan ký phát mà client chọn tin cậy. Có thể là CA công khai, CA nội bộ hoặc CA thử nghiệm.
- **Server certificate:** chứng chỉ xác nhận danh tính Redis Server hoặc TLS proxy trước Redis. Chứng chỉ được CA ký hoặc thuộc một chuỗi có thể xác minh.
- **Intermediate CA:** chứng chỉ trung gian nối server certificate tới root CA.
- **SAN (Subject Alternative Name):** trường liệt kê DNS name hoặc địa chỉ IP được phép dùng để nhận diện endpoint.
- **Private key:** khóa bí mật tương ứng với chứng chỉ. Khóa của server phải được server/proxy giữ kín; khóa client phải được client giữ kín khi dùng mTLS.

Chứng chỉ **CA** có thể được phân phối tới ứng dụng để đưa vào kho tin cậy. Không cần và không nên sao chép **private key của CA** tới ứng dụng chỉ để xác minh server.

### 3.2. Truststore và keystore có khác nhau không?

Trong Java:

| Thành phần | Chứa gì? | Công dụng |
|---|---|---|
| **Truststore** | Chứng chỉ CA hoặc trust anchor được chấp nhận | Client kiểm tra server certificate; server có thể dùng truststore riêng để kiểm tra client trong mTLS. |
| **Keystore** | Chứng chỉ danh tính và private key tương ứng, có thể kèm certificate chain | Client đưa chứng chỉ của chính mình khi server yêu cầu mTLS; hoặc server trình chứng chỉ server. |

Một client chỉ cần **TLS một chiều** thường phải cấu hình truststore khi CA nội bộ chưa nằm trong kho tin cậy mặc định của JDK. Client **không cần keystore chứa private key** nếu Redis Server không yêu cầu chứng chỉ phía client.

Java hỗ trợ các dạng kho khóa như **PKCS#12 (`.p12`, `.pfx`)** và **JKS**. Spring Boot còn có **SSL bundles** hỗ trợ PEM (`.crt`/`.pem` và `.key`), giúp không phải chuyển mọi chứng chỉ sang keystore Java.

### 3.3. Sự khác biệt giữa “chứng chỉ hợp lệ” và “đúng hostname”

Giả sử CA nội bộ đã được ứng dụng tin cậy, nhưng server đưa chứng chỉ chỉ có SAN `DNS:cache-a.internal`. Nếu Spring kết nối tới `cache-b.internal`, kiểm tra chuỗi CA có thể thành công trong khi **kiểm tra hostname phải thất bại**.

Đừng giải quyết lỗi này bằng cách vô hiệu hóa hostname verification. Thay vào đó, dùng hostname đúng với chứng chỉ, hoặc cấp lại chứng chỉ có SAN phù hợp với endpoint thực tế.

**Lưu ý về IP:** nếu kết nối bằng địa chỉ `10.0.0.15`, thông thường chứng chỉ cần có SAN kiểu **IP:10.0.0.15**. Một SAN `DNS:10.0.0.15` không tương đương với SAN kiểu IP trong mọi client TLS.

## 4. Cấu hình Redis Server chấp nhận TLS

Ở Redis Server hoặc Redis TLS proxy, người quản trị phải cung cấp endpoint có TLS. Những directive Redis Open Source điển hình:

```conf
# Tắt Redis TCP không mã hóa
port 0

# Mở cổng TLS
tls-port 6380

# Danh tính server và CA tin cậy
tls-cert-file /etc/redis/tls/server.crt
tls-key-file /etc/redis/tls/server.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# Chỉ xác thực server, không yêu cầu chứng chỉ client
tls-auth-clients no
```

Các đường dẫn chỉ là ví dụ. File chứng chỉ và private key phải có trên máy/container Redis, được process Redis đọc được và được bảo vệ bằng quyền file thích hợp.

Cấu hình trên là **TLS một chiều**. Nếu muốn Redis bắt buộc client trình certificate, dùng:

```conf
tls-auth-clients yes
```

Khi đó, CA cấu hình phía server dùng để xác minh chứng chỉ client, còn client vẫn phải tin cậy CA đã ký chứng chỉ server. Hai việc xác minh này độc lập.

Một số triển khai có nhiều listener, ví dụ TCP thường trên một port và TLS trên một port khác. Tránh đặt client Spring vào cổng plaintext khi yêu cầu bảo vệ đường truyền; nếu chính sách chỉ cho phép TLS, nên tắt listener plaintext và giới hạn truy cập mạng.

### 4.1. TLS của replication, Cluster và Sentinel

TLS giữa ứng dụng với Redis Server **không tự động đồng nghĩa** toàn bộ lưu lượng Redis nội bộ đã mã hóa:

- **Replication:** Redis có `tls-replication yes` để dùng TLS ở kết nối replication phía replica.
- **Cluster:** `tls-cluster yes` áp dụng TLS cho cluster bus và liên lạc giữa các node khi cấu hình phù hợp.
- **Sentinel:** việc Sentinel kết nối, tự giao tiếp hoặc cung cấp endpoint phụ thuộc cấu hình TLS của Sentinel và phiên bản/nền tảng; cần kiểm tra từng loại kết nối.

Ứng dụng dùng Redis Cluster có thể được chuyển hướng sang nhiều node. Mỗi node hoặc proxy TLS được kết nối đến phải có chứng chỉ và hostname phù hợp, không chỉ seed node đầu tiên.

## 5. Bật TLS trong Spring Boot khi dùng Spring Data Redis

### 5.1. Phụ thuộc cần thiết

Với ứng dụng Spring Boot thông thường, khai báo starter và để Boot quản lý phiên bản Spring Data Redis và driver Lettuce:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Spring Boot thường dùng **Lettuce** theo mặc định. Phần lớn thao tác TLS có thể cấu hình bằng `application.yml`, không cần tự tạo `LettuceConnectionFactory`.

### 5.2. Dùng CA công khai đã được JDK tin cậy

Nếu server có chứng chỉ hợp lệ do CA nằm trong Java default truststore ký, có thể cấu hình:

```yaml
spring:
  data:
    redis:
      host: redis.example.com
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      timeout: 3s
```

Ở đây:

- `host` phải là DNS name mà chứng chỉ TLS xác nhận.
- `port` phải là **cổng TLS** thực sự của Redis hoặc dịch vụ proxy Redis.
- `ssl.enabled: true` bật giao tiếp TLS.
- Username/password là Redis ACL, không phải private key hay truststore.
- `timeout` là giới hạn thời gian thao tác ở phía client theo ý nghĩa thuộc tính Boot; **không phải cách sửa lỗi chứng chỉ**.

**Bật TLS không có nghĩa bỏ qua xác minh.** Lettuce thông thường bật peer verification khi SSL được sử dụng, và có thể dựa vào trust anchors mặc định của JDK nếu không cấu hình CA riêng. Không gọi các API như `disablePeerVerification()` để “sửa nhanh” lỗi kết nối.

### 5.3. Cú pháp `rediss://`

Redis URI thường dùng:

- `redis://` cho kết nối Redis thông thường.
- `rediss://` cho kết nối Redis qua TLS.

Ví dụ:

```yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
```

Giá trị môi trường có thể mang dạng:

```text
rediss://user:password@redis.example.com:6380/0
```

Khi dùng URL, cần xem quy tắc ưu tiên của phiên bản Spring Boot đang chạy; URI thường ghi đè một số trường host/port/credentials/database. Để tránh xung đột, hãy chọn một cách khai báo endpoint rõ ràng.

URI chứa mật khẩu là **bí mật**: tránh ghi trực tiếp vào Git, log, issue hoặc command line chia sẻ. Ưu tiên secret manager và injection qua môi trường/volume được bảo vệ.

### 5.4. Cài CA nội bộ qua Spring Boot SSL bundle dạng PEM

Một endpoint nội bộ có thể được cấp bởi CA của tổ chức, chưa nằm trong Java default truststore. Khi đó nên cấu hình một **SSL bundle** để định nghĩa vật liệu tin cậy riêng cho Redis.

Ví dụ `application.yml` dùng file CA được mount tại đường dẫn từ môi trường:

```yaml
spring:
  ssl:
    bundle:
      pem:
        redis-client:
          truststore:
            certificate: "file:${REDIS_CA_CERT_PATH}"

  data:
    redis:
      host: redis.internal.example
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
        bundle: redis-client
```

Giả sử biến môi trường:

```text
REDIS_CA_CERT_PATH=/etc/app/redis-tls/ca.crt
```

Thì Spring Boot nạp chứng chỉ CA qua `file:/etc/app/redis-tls/ca.crt`, và Redis connection factory dùng bundle `redis-client`.

Những điểm quan trọng:

1. `spring.ssl.bundle.pem.redis-client.truststore.certificate` là **chứng chỉ đáng tin để xác minh server**, không phải client private key.
2. `spring.data.redis.ssl.bundle: redis-client` gắn bundle với kết nối Redis.
3. Tên bundle phải trùng ở hai vị trí.
4. Redis endpoint vẫn cần hostname hợp lệ trong SAN và certificate chain đúng.
5. File CA phải tồn tại, có quyền đọc và ở định dạng PEM mà Boot hỗ trợ.

Spring Boot hỗ trợ quản lý SSL bundle trong các dòng hiện đại, bao gồm Boot 3.3. Với ứng dụng dùng phiên bản Boot cũ hơn, phải xác nhận property được hỗ trợ trong **chính version tài liệu đó** trước khi sao chép.

Nếu CA gồm chuỗi root và intermediate, cần đóng gói trust material đúng hướng dẫn SSL bundle; tùy trường hợp server cũng phải gửi đầy đủ intermediate chain trong TLS handshake.

### 5.5. SSL bundle dạng PKCS#12/JKS

Nếu tổ chức đã cung cấp truststore Java, có thể sử dụng:

```yaml
spring:
  ssl:
    bundle:
      jks:
        redis-client:
          truststore:
            location: "file:${REDIS_TRUSTSTORE_PATH}"
            password: ${REDIS_TRUSTSTORE_PASSWORD}
            type: PKCS12

  data:
    redis:
      host: redis.internal.example
      port: 6380
      ssl:
        enabled: true
        bundle: redis-client
```

Ví dụ tạo một PKCS#12 truststore từ CA (chạy trên máy có `keytool`):

```bash
keytool -importcert \
  -alias redis-internal-ca \
  -file ca.crt \
  -keystore redis-truststore.p12 \
  -storetype PKCS12
```

`keytool` sẽ yêu cầu mật khẩu keystore và xác nhận thông tin chứng chỉ. Hãy kiểm tra **CA được nhập có thực sự là CA đã cấp server certificate dự kiến**; không nhập tùy tiện một chứng chỉ lạ chỉ để cho lỗi handshake biến mất.

SSL bundle theo từng ứng dụng giúp tránh sửa truststore mặc định toàn máy Java, vốn có thể ảnh hưởng đến các kết nối TLS khác.

### 5.6. Cấu hình Java truststore truyền thống

Một phương án khác là cung cấp system properties JVM:

```text
-Djavax.net.ssl.trustStore=/etc/app/redis-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=***secret***
```

Đây là minh họa tham số, **không chạy nguyên văn với dấu sao**. Phải truyền giá trị mật khẩu từ cơ chế quản lý bí mật; lưu ý tham số JVM có thể xuất hiện trong thông tin process hoặc môi trường quan sát tùy hệ điều hành.

Truststore JVM mặc định áp dụng phạm vi rộng hơn bundle riêng. Với Spring Boot hỗ trợ SSL bundle, ưu tiên cách ràng buộc riêng cho Redis khi có thể.

## 6. Khi Redis Server yêu cầu mutual TLS (mTLS)

### 6.1. Client cần thêm gì?

Nếu Redis yêu cầu client certificate, Spring phải có:

- **Trust material:** CA để xác minh **server certificate**.
- **Client certificate:** chứng chỉ client được CA mà Redis Server tin cậy ký.
- **Client private key:** khóa tương ứng của client certificate.
- **Mật khẩu hoặc cơ chế đọc private key**, nếu key được mã hóa và runtime hỗ trợ theo định dạng tương ứng.

Ví dụ PEM bundle:

```yaml
spring:
  ssl:
    bundle:
      pem:
        redis-mtls:
          truststore:
            certificate: "file:${REDIS_CA_CERT_PATH}"
          keystore:
            certificate: "file:${REDIS_CLIENT_CERT_PATH}"
            private-key: "file:${REDIS_CLIENT_KEY_PATH}"

  data:
    redis:
      host: redis.internal.example
      port: 6380
      ssl:
        enabled: true
        bundle: redis-mtls
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
```

Giải thích:

- `truststore.certificate` phục vụ **xác minh chứng chỉ Redis Server**.
- `keystore.certificate` và `keystore.private-key` để **ứng dụng trình chứng chỉ của nó** khi Redis yêu cầu.
- Username/password chỉ cần nếu Redis ACL yêu cầu; mTLS và ACL là hai cơ chế có mục đích khác nhau và có thể được dùng đồng thời.

Chứng chỉ client cần đúng **Extended Key Usage (client authentication)** nếu chính sách của server yêu cầu. Không tái sử dụng private key của Redis Server cho ứng dụng.

### 6.2. Redis Server kiểm tra client ra sao?

Khi `tls-auth-clients yes`, Redis có thể yêu cầu client certificate trong TLS handshake và xác minh theo CA đã cấu hình. Nếu client không có chứng chỉ, key không tương ứng hoặc chứng chỉ không được tin cậy, TLS handshake có thể thất bại **trước khi có bất kỳ lệnh Redis nào được gửi**.

Khi xử lý lỗi, kiểm tra từng phía:

| Phía kiểm tra | Điều cần xác nhận |
|---|---|
| Spring client | Tin đúng CA của Redis Server; đúng SAN/hostname; có client keypair nếu cần. |
| Redis Server | Đang tin CA ký client certificate; có yêu cầu mTLS đúng chủ đích; certificate/key hợp lệ. |
| Ứng dụng/ACL | Username/password và quyền lệnh Redis vẫn đáp ứng nghiệp vụ. |

### 6.3. Vòng đời chứng chỉ

Thời hạn của server certificate hoặc client certificate sẽ hết. Hệ thống cần có:

1. Nguồn cấp phát CA/certificate đáng tin.
2. Quy trình cấp và xoay vòng certificate trước hạn.
3. Cơ chế phân phối certificate và private key an toàn.
4. Cách cập nhật truststore/bundle và **tạo lại hoặc làm mới kết nối** khi vật liệu TLS đổi.
5. Giám sát lỗi handshake và thời điểm hết hạn.

Không giả định mọi client, mọi Spring Boot version hoặc mọi pool tự nạp lại file chứng chỉ ngay sau khi thay file trên đĩa. Khả năng reload SSL bundle và việc tạo lại connection phụ thuộc phiên bản/driver/cách cấu hình. Khi chưa có hỗ trợ reload được xác minh, hãy tổ chức restart/rollout có kiểm soát và kiểm tra bắt tay mới.

## 7. Thực hành: tự kiểm tra CA và hostname trong môi trường local

Bài thực hành này có thể chạy trên máy đã cài **OpenSSL, redis-server có hỗ trợ TLS và redis-cli**. Các lệnh dưới đây dành cho môi trường lab; chứng chỉ ngắn hạn và khóa thử nghiệm không dùng cho production.

### 7.1. Tạo CA thử nghiệm

```bash
mkdir -p certs

openssl genrsa -out certs/ca.key 4096
openssl req -x509 -new -sha256 -days 7 \
  -key certs/ca.key \
  -subj "/CN=Redis Lab Root CA" \
  -out certs/ca.crt
```

File `ca.key` là **private key của CA**: chỉ dùng tại lab và giữ kín. Ứng dụng client sau này chỉ cần `ca.crt` để tin chứng chỉ server.

### 7.2. Cấp chứng chỉ server có SAN

```bash
openssl genrsa -out certs/server.key 2048

openssl req -new -sha256 \
  -key certs/server.key \
  -subj "/CN=localhost" \
  -out certs/server.csr
```

Tạo file `certs/server.ext`:

```ini
subjectAltName=DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
```

Ký CSR bằng CA vừa tạo:

```bash
openssl x509 -req -sha256 -days 7 \
  -in certs/server.csr \
  -CA certs/ca.crt \
  -CAkey certs/ca.key \
  -CAcreateserial \
  -out certs/server.crt \
  -extfile certs/server.ext
```

SAN trong ví dụ hỗ trợ kết nối bằng `localhost` hoặc `127.0.0.1`. Ở production, SAN cần khớp **endpoint DNS thật** của Redis hoặc TLS proxy.

### 7.3. Chạy Redis chỉ có TLS

Trong thư mục lab có `certs/`, chạy một Redis process phục vụ cổng 6380:

```bash
redis-server \
  --port 0 \
  --tls-port 6380 \
  --tls-cert-file ./certs/server.crt \
  --tls-key-file ./certs/server.key \
  --tls-ca-cert-file ./certs/ca.crt \
  --tls-auth-clients no
```

Nếu server báo không hỗ trợ TLS, cần dùng bản phân phối Redis đã bật TLS hoặc môi trường TLS tương ứng. Không phải mọi binary Redis đều được biên dịch giống nhau.

### 7.4. Kiểm tra bằng redis-cli

Từ một terminal khác:

```bash
redis-cli -h localhost -p 6380 \
  --tls --cacert certs/ca.crt \
  PING
```

Kết quả mong đợi: `PONG`. Nếu bỏ `--tls`, client TCP thường gửi RESP vào cổng TLS và không thể thực hiện thao tác Redis bình thường. Nếu client không tin CA tự tạo, bắt tay TLS dự kiến thất bại.

**`PING` thành công chỉ chứng minh một tuyến kết nối và lệnh cơ bản hoạt động.** Để kiểm tra danh tính hostname một cách rõ ràng, dùng công cụ có tùy chọn xác minh hostname như `openssl s_client` bên dưới.

### 7.5. Xác minh chuỗi CA và hostname một cách tường minh

```bash
openssl s_client \
  -connect localhost:6380 \
  -servername localhost \
  -CAfile certs/ca.crt \
  -verify_hostname localhost \
  -verify_return_error
```

Nếu chứng chỉ đã được tạo đúng và server đang dùng chứng chỉ tương ứng, quá trình xác minh nên thành công; dấu hiệu thường gặp là `Verify return code: 0 (ok)`.

Có thể kiểm tra SAN của file chứng chỉ:

```bash
openssl x509 -in certs/server.crt -noout -text
```

Tìm `X509v3 Subject Alternative Name` và xác nhận có `DNS:localhost` cùng `IP Address:127.0.0.1`.

Thử kết nối tới server nhưng yêu cầu xác minh một hostname khác:

```bash
openssl s_client \
  -connect localhost:6380 \
  -servername not-the-server.example \
  -CAfile certs/ca.crt \
  -verify_hostname not-the-server.example \
  -verify_return_error
```

Nếu không có hostname đó trong SAN, xác minh danh tính dự kiến thất bại. Đây là một ví dụ cho thấy “CA đúng” chưa đủ nếu tên endpoint sai.

### 7.6. Kết nối Spring Boot tới lab

Tạo Spring configuration dùng CA của lab:

```yaml
spring:
  ssl:
    bundle:
      pem:
        redis-lab:
          truststore:
            certificate: "file:${REDIS_LAB_CA_PATH}"

  data:
    redis:
      host: localhost
      port: 6380
      ssl:
        enabled: true
        bundle: redis-lab
```

Đặt biến môi trường `REDIS_LAB_CA_PATH` trỏ tới đường dẫn tuyệt đối của `certs/ca.crt`; Spring process phải đọc được file đó. Không cần cấu hình keystore client vì Redis lab đã đặt `tls-auth-clients no`.

Để xác minh từ ứng dụng, có thể dùng `StringRedisTemplate`:

```java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisTlsProbe {

    private final StringRedisTemplate redis;

    public RedisTlsProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String roundTrip() {
        String key = "lab:tls:ping";

        redis.opsForValue().set(key, "secure", Duration.ofSeconds(30));
        return redis.opsForValue().get(key);
    }
}
```

Nếu TLS handshake, kiểm tra certificate và thao tác Redis thành công, `roundTrip()` sẽ đọc lại chuỗi `"secure"`. Điều này cho thấy đường truyền TLS được thiết lập và các lệnh cơ bản chạy, **không phải phép chứng minh tự động mọi khía cạnh của bảo mật hoặc tính năng Redis**.

## 8. Xác minh chứng chỉ trong các môi trường triển khai

### 8.1. Container và Kubernetes

File CA nên được cung cấp qua volume hoặc cơ chế phân phối chứng chỉ có kiểm soát. Ứng dụng cần đường dẫn ổn định, quyền đọc và mật khẩu/khóa phù hợp.

Ví dụ mapping khái niệm:

```text
Secret / volume quản lý bởi nền tảng
  ├── ca.crt               → Redis client trust material
  ├── client.crt           → chỉ khi dùng mTLS
  └── client.key           → chỉ khi dùng mTLS
            ↓ mount (read-only)
Ứng dụng Spring Boot
            ↓ TLS handshake + xác minh server
Redis TLS endpoint / proxy
```

Không sao chép private key vào Docker image hoặc commit lên Git. Với Kubernetes, kiểm soát quyền đọc Secret và identity của pod; với secret manager bên ngoài, dùng phương pháp mount/injection được tổ chức phê duyệt.

### 8.2. Managed Redis và TLS terminator

Dịch vụ Redis cloud có thể dùng TLS terminator hoặc proxy. Khi ấy chứng chỉ được ứng dụng nhìn thấy là chứng chỉ của **endpoint TLS**, không nhất thiết là chứng chỉ riêng từng Redis process phía sau.

Cần:

- Kết nối đúng hostname mà nhà cung cấp phát hành và xác nhận trong SAN.
- Dùng cổng/protocol TLS của dịch vụ.
- Tin CA mà nhà cung cấp hướng dẫn; không tùy tiện tin mọi chứng chỉ.
- Phân biệt Redis ACL credentials với mTLS client certificate nếu dịch vụ yêu cầu cả hai.
- Kiểm tra giới hạn của dịch vụ về TLS version, cipher, client certificate và failover.

### 8.3. Redis Cluster và chuyển hướng node

Redis Cluster cho client biết các node và hash slots. Driver có thể mở kết nối TLS tới node khác sau khi nhận thông tin topology hoặc chuyển hướng `MOVED`/`ASK`.

Nếu chứng chỉ chỉ hợp lệ cho seed hostname nhưng các node được quảng bá bằng IP nội bộ không có IP SAN, kết nối ban đầu có thể thành công rồi những lệnh tới node khác thất bại. Không nên tắt hostname verification để che vấn đề này. Cần sửa cấu hình node addressing/advertised hostnames hoặc cấp chứng chỉ phù hợp cho **tất cả endpoint có thể được kết nối**.

### 8.4. Sentinel và failover

Ở mô hình Sentinel, ứng dụng có thể cần kết nối tới Sentinel để tìm primary rồi kết nối tới Redis data node. Các endpoint này có thể có chứng chỉ, hostname, password và chính sách TLS khác nhau. Cần đảm bảo driver/version/cấu hình hỗ trợ đúng cách kết nối TLS qua Sentinel và qua data nodes. Một cấu hình TLS chỉ đúng ở endpoint Redis nhưng sai ở Sentinel có thể khiến quá trình failover không hoạt động.

## 9. Kết nối TLS và pool: handshake xuất hiện lúc nào?

Trong Spring Data Redis, `RedisConnectionFactory` điều phối việc lấy kết nối Redis. Với Lettuce, một số hoạt động có thể dùng kết nối chia sẻ; các loại thao tác khác có thể dùng kết nối chuyên biệt hoặc connection pooling tùy cấu hình.

**TLS handshake diễn ra khi một kết nối TLS mới được thiết lập**, không phải ở mọi lệnh `GET` trên kết nối đang còn mở. Vì vậy:

- Tái sử dụng kết nối có thể giảm chi phí handshake.
- Khi nhiều kết nối mới được tạo đồng thời, CPU và latency bắt tay có thể tăng.
- Khi certificate hết hạn hoặc bị thay đổi, kết nối cũ và kết nối mới có thể có hành vi khác nhau tùy chính sách phiên TLS và driver.
- Cấu hình timeout quá ngắn có thể khiến thao tác tạo kết nối TLS dễ thất bại trên đường truyền chậm.
- Pool không làm thay việc xác minh danh tính; từng **kết nối mới** phải được xác minh theo chính sách TLS.

Mô hình:

```mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Pool as ConnectionFactory / Driver
    participant Redis as Redis TLS Server
    App->>Pool: Yêu cầu kết nối
    alt Có kết nối TLS còn sử dụng được
        Pool-->>App: Trả kết nối đã thiết lập
    else Cần tạo kết nối mới
        Pool->>Redis: TCP + TLS handshake
        Redis-->>Pool: Chứng chỉ / bắt tay
        Note over Pool: Kiểm tra trust chain và hostname
        Pool-->>App: Trả kết nối TLS hợp lệ
    end
    App->>Redis: GET / SET trên kênh TLS
    Redis-->>App: Phản hồi Redis qua TLS
```

Khi xoay vòng CA hoặc certificate server, cần thực hiện quy trình đảm bảo kết nối mới tải được trust material mới. Đừng dựa vào việc “mọi pool tự refresh certificate” mà chưa kiểm chứng theo phiên bản Boot/driver và cách triển khai.

## 10. Chẩn đoán lỗi handshake và certificate

### 10.1. Bảng phân loại

| Biểu hiện hoặc thông báo điển hình | Nguyên nhân có thể | Cách xử lý đúng hướng |
|---|---|---|
| `PKIX path building failed` / `unable to find valid certification path` | Client không tin CA ký chứng chỉ server hoặc server không gửi đủ intermediate chain | Kiểm tra CA/truststore và certificate chain; không tắt verify. |
| `No subject alternative DNS name matching ...` / `No name matching ...` | Hostname kết nối không có trong SAN | Sửa endpoint DNS hoặc cấp chứng chỉ có SAN phù hợp. |
| `certificate expired` / `not yet valid` | Certificate không còn trong khoảng hiệu lực hoặc đồng hồ hệ thống sai | Xác nhận giờ hệ thống, xoay vòng/cấp lại chứng chỉ. |
| `certificate required` / `bad certificate` | Server yêu cầu mTLS nhưng client thiếu/sai keypair hoặc CA | Cấu hình client certificate và private key hợp lệ; kiểm tra CA phía server. |
| `SSLHandshakeException` | Nhóm lỗi chung của handshake | Xem nguyên nhân gốc (CA, hostname, TLS version, cipher, mTLS). |
| `wrong version number` / `NotSslRecordException` | Dùng TLS vào cổng plaintext hoặc ngược lại | Đối chiếu endpoint, port, giao thức và proxy. |
| `Connection refused` / timeout | Sai host/port, firewall, server không chạy hoặc đường mạng lỗi | Kiểm tra reachability và listener trước khi điều tra chứng chỉ. |
| `NOAUTH` / `NOPERM` | Redis ACL, xảy ra sau kết nối tương ứng | Kiểm tra username/password/quyền; không nhầm với lỗi CA. |
| Chỉ lỗi sau chuyển hướng Cluster | Chứng chỉ/topology trên node khác không phù hợp | Kiểm tra SAN, DNS, routing và TLS từng node. |

Tên exception cụ thể tùy driver, Java runtime và Redis deployment. Một thông báo cấp cao như `RedisConnectionFailureException` có thể bọc nguyên nhân gốc là `SSLHandshakeException`; cần đọc **cause chain** để biết tầng lỗi.

### 10.2. Thứ tự điều tra hợp lý

1. **Endpoint:** hostname, port và TLS mode có đúng không? Redis Server đang nghe ở listener TLS nào?
2. **Kết nối mạng:** có mở TCP được từ đúng máy/pod đang chạy Spring không?
3. **Handshake:** thử kết nối với `redis-cli --tls --cacert` hoặc công cụ TLS phù hợp.
4. **Trust chain:** chứng chỉ do CA nào ký, client có trust anchor đó không, server có gửi intermediate chain đầy đủ?
5. **Hostname/SAN:** hostname client sử dụng có xuất hiện trong chứng chỉ không?
6. **mTLS:** server có yêu cầu client certificate, client có đúng certificate/private key, CA server có tin client không?
7. **Redis ACL:** sau handshake, user có đủ quyền thực thi lệnh không?
8. **Topology/failover:** chứng chỉ của mọi node/proxy liên quan có đúng không?

Đừng dùng cơ chế “trust all”, bỏ hostname verification hoặc tắt TLS như lời giải lâu dài. Các thay đổi đó có thể khiến lỗi biến mất trong lab nhưng làm mất mục tiêu xác thực server.

### 10.3. Logging chẩn đoán TLS cho Java

Khi cần điều tra sâu trong môi trường được kiểm soát, có thể bật debug JSSE:

```text
-Djavax.net.debug=ssl,handshake
```

Log có thể chứa chi tiết về chứng chỉ, endpoint, hostname và handshake. Chỉ bật khi cần, hạn chế quyền truy cập log và tắt sau khi chẩn đoán. Không xuất private key, mật khẩu hoặc biến môi trường chứa bí mật ra log để “tiện debug”.

Với TLS phía Redis, tham khảo log Redis Server và TLS proxy nếu có; đối chiếu thời điểm handshake thất bại giữa server/client. Sai CA ở client và thiếu client certificate ở mTLS có thể cùng xuất hiện dưới lớp exception kết nối, nhưng cách khắc phục khác nhau.

## 11. Kiểm chứng an toàn theo từng tình huống

### 11.1. TLS một chiều với CA nội bộ

**Mục tiêu:** Spring chỉ tin CA được phép và xác minh hostname.

**Các bước:**

1. Nhận CA certificate từ nguồn đáng tin.
2. Xác nhận server certificate có SAN cho endpoint thật và chưa hết hạn.
3. Mount CA vào ứng dụng, cấu hình SSL bundle PEM/JKS.
4. Bật `spring.data.redis.ssl.enabled` và chọn SSL bundle.
5. Chạy thao tác đọc/ghi tối thiểu qua `StringRedisTemplate`.
6. Dùng công cụ kiểm tra riêng để xác minh certificate chain/hostname.

**Kết quả mong muốn:** ứng dụng kết nối khi đúng CA và đúng hostname; kết nối thất bại nếu CA không tin cậy hoặc hostname sai.

### 11.2. Redis yêu cầu mTLS

**Mục tiêu:** hai phía xác minh danh tính.

**Các bước:**

1. Redis Server tin CA ký client certificate và yêu cầu mTLS.
2. Spring tin CA ký server certificate.
3. Spring có client certificate và private key đúng cặp, còn hiệu lực.
4. Redis vẫn dùng ACL nếu chính sách yêu cầu username/password.
5. Thử kết nối đúng vật liệu; xác nhận việc bỏ client certificate làm handshake bị từ chối.

**Kết quả mong muốn:** handshake chỉ hoàn tất khi đáp ứng chính sách chứng chỉ hai phía.

### 11.3. Xoay vòng chứng chỉ

**Mục tiêu:** bảo trì tính tin cậy khi thay CA/server certificate.

**Các bước:**

1. Chuẩn bị trust bundle chứa CA mới theo quy trình chuyển tiếp, nếu cần có giai đoạn tin cả CA cũ và CA mới.
2. Phân phối trust material trước khi thay chứng chỉ server.
3. Thay server certificate với SAN hợp lệ và cập nhật các node/proxy liên quan.
4. Đảm bảo driver tạo các kết nối mới bằng trust configuration đã cập nhật.
5. Kiểm tra handshake và lệnh Redis thực tế.
6. Sau khi mọi phía chuyển xong, loại CA cũ theo chính sách thu hồi.

**Kết quả mong muốn:** không có khoảng thời gian ứng dụng phải tắt xác minh để duy trì kết nối.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Có mật khẩu Redis là dữ liệu mạng đã an toàn.” | ACL xác thực/phân quyền; TLS bảo vệ dữ liệu khi truyền. |
| “Có TLS nghĩa là server chắc chắn đúng.” | Phải kiểm tra trust chain và hostname; TLS không xác minh đúng nếu cấu hình bỏ qua verify. |
| “Truststore và keystore là một.” | Truststore chứa chứng chỉ tin cậy; keystore chứa certificate và private key danh tính. |
| “Tất cả Redis TLS đều bắt buộc mTLS.” | Chính sách mTLS phụ thuộc cấu hình/server; Redis Open Source mặc định yêu cầu client certificate khi dùng TLS, nhưng có thể tắt bằng `tls-auth-clients no`. |
| “CA certificate phải giữ bí mật như private key.” | CA certificate dùng để xác minh có thể phân phối; **CA private key** phải được bảo vệ nghiêm ngặt. |
| “Chứng chỉ do CA tin cậy ký là đủ.” | Còn phải hợp lệ về thời gian, chính sách và **khớp SAN của endpoint**. |
| “`PING` thành công chứng minh mọi cấu hình TLS đều an toàn.” | Nó chỉ xác nhận một kết nối và một lệnh; phải đánh giá cấu hình verify/trust và topology. |
| “Mọi lệnh Redis đều bắt tay TLS lại.” | Handshake thường diễn ra khi tạo kết nối; lệnh trên kết nối đang mở tái sử dụng kênh TLS. |
| “Restart Redis sẽ tự cập nhật truststore client.” | Trust material của client và kết nối mới cần được cập nhật theo vòng đời riêng. |
| “Cluster chỉ cần certificate trên seed node.” | Client có thể kết nối tới nhiều node sau khi định tuyến; mỗi endpoint TLS cần chứng chỉ hợp lệ. |

## 13. Kết luận kỹ thuật

Để bảo vệ kết nối Spring Data Redis, hãy nhìn toàn bộ chuỗi:

```text
Endpoint đúng (DNS + TLS port)
        ↓
Truststore chứa CA tin cậy
        ↓
TLS handshake xác minh certificate chain và hostname
        ↓
Client certificate/private key (nếu mTLS)
        ↓
Redis ACL / quyền thực thi lệnh
        ↓
Spring Data Redis gửi RESP qua kênh đã bảo vệ
        ↓
Duy trì kết nối, theo dõi lỗi và xoay vòng chứng chỉ
```

Một cấu hình đáng tin cậy phải làm cho **chứng chỉ sai hoặc hostname sai bị từ chối**, thay vì chỉ làm cho ứng dụng “kết nối được” bằng mọi giá. Sử dụng SSL bundle của Spring Boot khi cần CA nội bộ hoặc mTLS, giữ nguyên xác minh peer, bảo vệ private key và kiểm tra chứng chỉ trên đúng endpoint, gồm cả các node được client khám phá qua Redis Cluster/Sentinel.

### Tài liệu chính thức

- [Redis — TLS](https://redis.io/docs/latest/management/security/encryption/) — bật TLS trên server, `tls-port`, certificate, mTLS, replication và Cluster.
- [Redis CLI — SSL/TLS](https://redis.io/docs/latest/develop/tools/cli/) — `redis-cli --tls`, `--cacert`, client certificate.
- [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html) — Redis, `spring.data.redis.ssl.enabled` và SSL bundle.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html) — SSL bundle bằng PEM, JKS/PKCS#12.
- [Spring Boot 3.3 — SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html) — ví dụ tương ứng cho dự án dùng Boot 3.3.
- [Spring Data Redis — Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html) — standalone, master/replica, Sentinel và Cluster.
- [Spring Data Redis — LettuceClientConfiguration API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/lettuce/LettuceClientConfiguration.html) — SSL và peer verification.
- [Lettuce — SSL Connections](https://github.com/redis/lettuce/wiki/SSL-Connections) — TLS handshake, truststore và hostname verification.
