# Kerberos và GSSAPI

## 1. Kerberos và GSSAPI giải quyết vấn đề gì?

Trong môi trường doanh nghiệp, Kafka thường chạy trong mạng nội bộ và chỉ cho phép ứng dụng đã được xác thực kết nối. Kerberos là giao thức xác thực dựa trên ticket, thường được triển khai cùng Active Directory hoặc MIT Kerberos. GSSAPI (Generic Security Services Application Program Interface) là API bảo mật mà Kafka dùng để thực hiện cơ chế SASL GSSAPI dựa trên Kerberos.

Với Spring Kafka, `KafkaTemplate`, `@KafkaListener`, `KafkaAdmin` và Kafka Streams vẫn sử dụng Kafka Java client bên dưới. Vì vậy, ứng dụng cấu hình Kerberos thông qua các thuộc tính của Kafka client như `security.protocol`, `sasl.mechanism`, `sasl.kerberos.service.name` và `sasl.jaas.config`.

Kerberos/GSSAPI cung cấp xác thực danh tính client và broker. Nó không thay thế Kafka ACL, cũng không tự mã hóa toàn bộ dữ liệu Kafka trên mạng. Trong môi trường production, thường kết hợp `SASL_SSL`: TLS bảo vệ đường truyền, còn SASL GSSAPI xác thực bằng Kerberos.

## 2. Các thành phần trong Kerberos

Một triển khai Kerberos thường có các thành phần:

- **Realm:** miền quản lý danh tính Kerberos, thường viết hoa, ví dụ `EXAMPLE.COM`.
- **KDC (Key Distribution Center):** máy chủ cấp ticket; thường gồm Authentication Server (AS) và Ticket Granting Server (TGS).
- **Principal:** danh tính của user hoặc service, ví dụ `orders-service@EXAMPLE.COM`.
- **Service Principal Name (SPN):** principal đại diện cho service trên một host, ví dụ `kafka/broker1.example.com@EXAMPLE.COM`.
- **Ticket Granting Ticket (TGT):** ticket client nhận sau khi đăng nhập vào Kerberos, dùng để yêu cầu service ticket.
- **Service ticket:** ticket dành riêng cho một service, ví dụ Kafka broker.
- **Keytab:** file chứa key bí mật của principal để process đăng nhập tự động mà không cần nhập mật khẩu tương tác.

Client và broker không gửi mật khẩu Kerberos qua Kafka connection. Client dùng keytab hoặc ticket cache để lấy ticket từ KDC, sau đó dùng GSSAPI thực hiện trao đổi xác thực với broker.

## 3. Luồng xác thực Kerberos khi kết nối Kafka

Giả sử ứng dụng Spring Kafka chạy với principal `orders-service@EXAMPLE.COM` và kết nối broker có SPN `kafka/broker1.example.com@EXAMPLE.COM`.

```text
Spring Kafka application
  Principal: orders-service@EXAMPLE.COM
  Keytab: orders-service.keytab
          |
          | 1. Login bằng keytab
          v
       Kerberos KDC
          |
          | 2. Cấp Ticket Granting Ticket (TGT)
          v
  Kafka Java client / GSSAPI
          |
          | 3. Xin service ticket cho kafka/broker1.example.com
          v
       Kerberos KDC
          |
          | 4. Trả service ticket
          v
  Kafka Java client
          |
          | 5. SASL GSSAPI token exchange qua SASL_SSL
          v
  Kafka broker
  SPN: kafka/broker1.example.com@EXAMPLE.COM
          |
          | 6. Xác thực principal, ánh xạ principal local
          v
      Kafka Authorizer
          |
          | 7. Kiểm tra ACL cho topic/group/operation
          v
     Producer / Consumer được phép hoạt động
```

Các bước quan trọng:

1. JVM đọc cấu hình Kerberos và JAAS.
2. `Krb5LoginModule` dùng keytab để đăng nhập principal của ứng dụng.
3. Kerberos client lấy TGT từ KDC.
4. Khi kết nối broker, GSSAPI yêu cầu service ticket cho SPN Kafka trên hostname broker.
5. Client và broker trao đổi SASL token để xác thực lẫn nhau.
6. Broker xác định principal client và chuyển principal cho authorizer.
7. Kafka ACL quyết định principal có quyền đọc/ghi topic hoặc tham gia consumer group hay không.

Xác thực thành công chỉ chứng minh client là principal nào. Nó không đồng nghĩa principal đó có quyền `Read`, `Write`, `Create` hoặc `Describe` trên tài nguyên Kafka.

## 4. Principal client và principal broker

Client và broker có principal khác nhau:

| Thành phần | Principal ví dụ | Vai trò |
|---|---|---|
| Ứng dụng Spring Kafka | `orders-service@EXAMPLE.COM` | Danh tính client khi gọi producer, consumer hoặc admin API |
| Kafka broker 1 | `kafka/broker1.example.com@EXAMPLE.COM` | Danh tính service Kafka trên broker 1 |
| Kafka broker 2 | `kafka/broker2.example.com@EXAMPLE.COM` | Danh tính service Kafka trên broker 2 |
| Kafka broker 3 | `kafka/broker3.example.com@EXAMPLE.COM` | Danh tính service Kafka trên broker 3 |

Phần `kafka` trước dấu `/` là service name. Hostname phải khớp với hostname mà client dùng để kết nối broker và SPN đã đăng ký trong Kerberos.

Ví dụ broker 1 có principal:

```text
kafka/broker1.example.com@EXAMPLE.COM
```

Client cấu hình:

```properties
sasl.kerberos.service.name=kafka
```

Client không cần ghi hostname vào `sasl.kerberos.service.name`; Kafka client kết hợp service name với hostname broker để tạo service principal cần xác thực.

## 5. Chuẩn bị Kerberos realm và krb5.conf

JVM cần biết realm mặc định và cách tìm KDC. Có thể chỉ định file cấu hình bằng system property `java.security.krb5.conf`.

Ví dụ file `/etc/krb5.conf`:

```ini
[libdefaults]
    default_realm = EXAMPLE.COM
    dns_lookup_kdc = true
    ticket_lifetime = 10h
    renew_lifetime = 7d
    forwardable = true

[realms]
    EXAMPLE.COM = {
        kdc = kdc1.example.com
        admin_server = kdc1.example.com
    }

[domain_realm]
    .example.com = EXAMPLE.COM
    example.com = EXAMPLE.COM
```

Nếu DNS không cung cấp bản ghi SRV cho KDC, khai báo trực tiếp hostname KDC và port theo cấu hình realm. Giá trị `default_realm`, tên miền và KDC trong ví dụ phải được thay bằng thông tin của tổ chức.

Khởi chạy ứng dụng với:

```bash
java \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -jar spring-kafka-messaging.jar
```

Trong container, có thể đặt system property qua `JAVA_TOOL_OPTIONS`:

```bash
JAVA_TOOL_OPTIONS="-Djava.security.krb5.conf=/etc/krb5.conf"
```

Trên Windows, property này cũng trỏ đến file cấu hình Kerberos mà JVM đọc được, ví dụ:

```powershell
java -Djava.security.krb5.conf="C:\kerberos\krb5.ini" -jar spring-kafka-messaging.jar
```

Không giả định mọi JVM hoặc Kerberos distribution dùng cùng một đường dẫn mặc định. Hãy kiểm tra file thực tế được mount/cài đặt trong môi trường chạy.

## 6. Tạo principal và keytab

Quản trị viên Kerberos tạo principal riêng cho ứng dụng, ví dụ:

```text
orders-service@EXAMPLE.COM
```

Sau đó tạo keytab tương ứng và cấp cho process chạy Spring Kafka. Cú pháp tạo principal/keytab phụ thuộc KDC, ví dụ MIT Kerberos hoặc Active Directory; thao tác này thường do đội hạ tầng hoặc IAM thực hiện.

Keytab là credential nhạy cảm. Quy tắc triển khai:

- Tạo principal riêng cho từng ứng dụng hoặc workload, không dùng tài khoản cá nhân.
- Chỉ cấp keytab cho service cần dùng và giới hạn quyền đọc file ở OS/container.
- Mount keytab từ secret manager hoặc secret volume; không commit vào Git, image hoặc artifact.
- Không copy keytab vào log, exception message hoặc support bundle.
- Có quy trình rotate keytab và cập nhật service principal/kvno đồng bộ.
- Không chia sẻ một keytab quản trị có quyền rộng cho mọi producer/consumer.

Một keytab có thể chứa nhiều entry hoặc nhiều key version (kvno). Khi KDC đổi key của principal, keytab cũ có thể không còn xác thực được. Cần phối hợp thời điểm rotate và rolling restart của ứng dụng.

## 7. Kiểm tra keytab trước khi chạy ứng dụng

Với MIT Kerberos tools, có thể kiểm tra keytab và đăng nhập thử:

```bash
# Liệt kê principal và key version trong keytab
klist -kte /etc/security/keytabs/orders-service.keytab

# Lấy TGT bằng keytab
kinit -kt /etc/security/keytabs/orders-service.keytab \
  orders-service@EXAMPLE.COM

# Xem ticket cache
klist -e

# Yêu cầu service ticket cho Kafka broker
kvno kafka/broker1.example.com@EXAMPLE.COM

# Xóa ticket cache sau khi kiểm tra
kdestroy
```

Nếu `kinit` thất bại, cần giải quyết principal, realm, keytab, quyền đọc file hoặc đồng hồ hệ thống trước khi kiểm tra Spring Kafka. Nếu `kinit` thành công nhưng `kvno` thất bại, tập trung kiểm tra SPN Kafka, hostname, DNS và KDC.

## 8. Cấu hình JAAS với Krb5LoginModule

Kafka Java client dùng JAAS để đăng nhập Kerberos. Login module chuẩn của JDK là:

```text
com.sun.security.auth.module.Krb5LoginModule
```

Ví dụ JAAS cho ứng dụng chạy lâu dài bằng keytab:

```text
com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    storeKey=true
    keyTab="/etc/security/keytabs/orders-service.keytab"
    principal="orders-service@EXAMPLE.COM"
    doNotPrompt=true;
```

Ý nghĩa các option:

| Option | Ý nghĩa |
|---|---|
| `useKeyTab=true` | Đăng nhập bằng keytab |
| `storeKey=true` | Lưu key của principal trong Subject để GSSAPI sử dụng |
| `keyTab=...` | Đường dẫn keytab |
| `principal=...` | Principal mà ứng dụng đăng nhập |
| `doNotPrompt=true` | Không yêu cầu nhập mật khẩu tương tác |

Với service chạy nền, keytab thường phù hợp hơn ticket cache do người dùng đăng nhập thủ công. Ticket cache hữu ích cho phát triển cục bộ hoặc công cụ dòng lệnh:

```text
com.sun.security.auth.module.Krb5LoginModule required
    useTicketCache=true;
```

Không cấu hình đồng thời nhiều cơ chế credential nếu chưa hiểu thứ tự lựa chọn của `Krb5LoginModule`. Nếu chạy bằng ticket cache, process phải có cache hợp lệ và quy trình refresh ticket rõ ràng.

### Dùng file JAAS tĩnh

Kafka client cũng hỗ trợ cấu hình JAAS trong file riêng với section tên `KafkaClient`:

```text
KafkaClient {
    com.sun.security.auth.module.Krb5LoginModule required
        useKeyTab=true
        storeKey=true
        keyTab="/etc/security/keytabs/orders-service.keytab"
        principal="orders-service@EXAMPLE.COM"
        doNotPrompt=true;
};
```

Khởi chạy JVM với:

```bash
java \
  -Djava.security.auth.login.config=/etc/security/kafka-client-jaas.conf \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -jar spring-kafka-messaging.jar
```

File JAAS tĩnh thường dùng chung một danh tính cho các Kafka client trong JVM. Nếu cần producer, consumer và admin dùng principal khác nhau, `sasl.jaas.config` ở từng client property linh hoạt hơn. Khi cả system property `java.security.auth.login.config` và client property `sasl.jaas.config` cùng được đặt, client property được ưu tiên.

## 9. Cấu hình Kerberos trong Spring Boot

Spring Kafka không cần annotation riêng cho Kerberos. Cấu hình được truyền xuống Kafka producer, consumer và admin client qua `spring.kafka`.

Ví dụ `application.yml` dùng cùng một principal cho các Kafka client:

```yaml
spring:
  kafka:
    bootstrap-servers:
      - broker1.example.com:9093
      - broker2.example.com:9093
      - broker3.example.com:9093
    security:
      protocol: SASL_SSL
    properties:
      sasl.mechanism: GSSAPI
      sasl.kerberos.service.name: kafka
      sasl.jaas.config: >-
        com.sun.security.auth.module.Krb5LoginModule required
        useKeyTab=true
        storeKey=true
        keyTab="${KAFKA_KEYTAB_PATH:/etc/security/keytabs/orders-service.keytab}"
        principal="${KAFKA_KERBEROS_PRINCIPAL:orders-service@EXAMPLE.COM}"
        doNotPrompt=true;
    ssl:
      trust-store-location: file:/etc/security/kafka/client.truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${KAFKA_TRUSTSTORE_PASSWORD}
```

Trong ví dụ:

- `security.protocol: SASL_SSL` bật SASL cùng TLS.
- `sasl.mechanism: GSSAPI` chọn Kerberos qua GSSAPI.
- `sasl.kerberos.service.name: kafka` chỉ định service name trong SPN broker.
- `sasl.jaas.config` đăng nhập principal ứng dụng bằng keytab.
- `ssl.trust-store-*` giúp JVM xác minh certificate của broker; cần thay bằng CA/trust configuration thực tế.

Các thuộc tính `spring.kafka.properties.*` là Kafka client properties dùng chung cho producer và consumer. `KafkaAdmin` có nhóm `spring.kafka.admin.properties.*` riêng; nếu ứng dụng dùng KafkaAdmin, hãy cấu hình JAAS ở nhóm admin tương ứng. Ví dụ khi cả ba client dùng cùng principal:

```yaml
spring:
  kafka:
    admin:
      security:
        protocol: SASL_SSL
      properties:
        sasl.jaas.config: >-
          com.sun.security.auth.module.Krb5LoginModule required
          useKeyTab=true storeKey=true
          keyTab="${KAFKA_KEYTAB_PATH:/etc/security/keytabs/orders-service.keytab}"
          principal="${KAFKA_KERBEROS_PRINCIPAL:orders-service@EXAMPLE.COM}"
          doNotPrompt=true;
```

Spring Boot chuyển các property này đến đúng Kafka client được auto-configure. Nếu producer, consumer và admin dùng cùng một principal, giữ nguyên cùng JAAS string ở các nhóm tương ứng; nếu dùng principal riêng, cấu hình override theo từng client như mục tiếp theo.

`KAFKA_TRUSTSTORE_PASSWORD`, `KAFKA_KEYTAB_PATH` và principal phải được cấp qua môi trường triển khai. Không ghi mật khẩu truststore hoặc credential thật vào repository.

## 10. Dùng principal khác nhau cho producer, consumer và admin

Một JVM có thể tạo nhiều Kafka client với danh tính khác nhau. Kafka client property `sasl.jaas.config` cho phép mỗi producer hoặc consumer dùng principal riêng. Trong Spring Boot, có thể ghi đè cấu hình chung bằng property riêng của từng client.

Ví dụ:

```yaml
spring:
  kafka:
    bootstrap-servers: broker1.example.com:9093
    security:
      protocol: SASL_SSL
    properties:
      sasl.mechanism: GSSAPI
      sasl.kerberos.service.name: kafka
    consumer:
      properties:
        sasl.jaas.config: >-
          com.sun.security.auth.module.Krb5LoginModule required
          useKeyTab=true storeKey=true
          keyTab="/etc/security/keytabs/order-reader.keytab"
          principal="order-reader@EXAMPLE.COM"
          doNotPrompt=true;
    producer:
      properties:
        sasl.jaas.config: >-
          com.sun.security.auth.module.Krb5LoginModule required
          useKeyTab=true storeKey=true
          keyTab="/etc/security/keytabs/order-writer.keytab"
          principal="order-writer@EXAMPLE.COM"
          doNotPrompt=true;
    admin:
      properties:
        sasl.jaas.config: >-
          com.sun.security.auth.module.Krb5LoginModule required
          useKeyTab=true storeKey=true
          keyTab="/etc/security/keytabs/order-admin.keytab"
          principal="order-admin@EXAMPLE.COM"
          doNotPrompt=true;
```

Producer factory dùng principal `order-writer`, consumer factory dùng `order-reader`, còn KafkaAdmin dùng `order-admin`. Cách này hỗ trợ least privilege: service đọc dữ liệu không cần credential có quyền tạo topic hoặc ghi vào topic khác.

Chỉ khai báo `sasl.jaas.config` chung khi mọi client thực sự dùng cùng một danh tính. Nếu đã khai báo JAAS riêng ở producer/consumer/admin, hãy kiểm tra cấu hình cuối cùng của từng client để tránh vô tình kế thừa hoặc ghi đè sai principal.

## 11. Cấu hình Kafka Java client trực tiếp

Nếu tự tạo `ProducerFactory` hoặc `ConsumerFactory`, thêm các Kafka client properties vào map cấu hình:

```java
Map<String, Object> securityProperties(String jaasConfig) {
    Map<String, Object> properties = new HashMap<>();

    properties.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SASL_SSL");
    properties.put(SaslConfigs.SASL_MECHANISM, "GSSAPI");
    properties.put(SaslConfigs.SASL_KERBEROS_SERVICE_NAME, "kafka");
    properties.put(SaslConfigs.SASL_JAAS_CONFIG, jaasConfig);

    return properties;
}
```

Ví dụ tạo consumer factory:

```java
@Bean
ConsumerFactory<String, OrderEvent> orderConsumerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers,
        @Value("${app.kafka.jaas-config}") String jaasConfig) {

    Map<String, Object> properties = new HashMap<>();
    properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    properties.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
    properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    properties.putAll(securityProperties(jaasConfig));

    return new DefaultKafkaConsumerFactory<>(
            properties,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderEvent.class));
}
```

Producer factory cũng dùng cùng security properties nhưng serializer của producer:

```java
@Bean
ProducerFactory<String, OrderEvent> orderProducerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers,
        @Value("${app.kafka.jaas-config}") String jaasConfig) {

    Map<String, Object> properties = new HashMap<>();
    properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    properties.putAll(securityProperties(jaasConfig));

    return new DefaultKafkaProducerFactory<>(
            properties,
            new StringSerializer(),
            new JsonSerializer<>());
}
```

Trong ví dụ Java, `app.kafka.jaas-config` là property riêng do ứng dụng nạp từ secret/config provider. Có thể khai báo nó trong cấu hình triển khai:

```yaml
app:
  kafka:
    jaas-config: >-
      com.sun.security.auth.module.Krb5LoginModule required
      useKeyTab=true storeKey=true
      keyTab="${KAFKA_KEYTAB_PATH}"
      principal="${KAFKA_KERBEROS_PRINCIPAL}"
      doNotPrompt=true;
```

Ví dụ tập trung vào thuộc tính SASL; nếu dùng `SASL_SSL`, vẫn phải cấu hình truststore/certificate phù hợp. Khi tự tạo factory, đừng quên áp dụng bảo mật cho `KafkaAdmin`, `KafkaStreams` hoặc client khác nếu ứng dụng sử dụng chúng.

## 12. Cấu hình broker để chấp nhận GSSAPI

Broker phải bật listener SASL và cơ chế GSSAPI. Ví dụ một broker dùng SASL_SSL:

```properties
listeners=SASL_SSL://0.0.0.0:9093
advertised.listeners=SASL_SSL://broker1.example.com:9093

sasl.enabled.mechanisms=GSSAPI
sasl.kerberos.service.name=kafka

listener.name.sasl_ssl.gssapi.sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required useKeyTab=true storeKey=true doNotPrompt=true keyTab="/etc/kafka/keytabs/kafka-broker.keytab" principal="kafka/broker1.example.com@EXAMPLE.COM";

security.inter.broker.protocol=SASL_SSL
sasl.mechanism.inter.broker.protocol=GSSAPI
```

Đây là cấu hình minh họa cho broker. Trong cluster nhiều broker, mỗi broker phải dùng keytab chứa service principal phù hợp hostname của nó. Nếu cluster dùng `inter.broker.listener.name`, hãy cấu hình listener nội bộ theo mô hình đó và không đồng thời cấu hình một lựa chọn inter-broker protocol xung đột.

Broker cũng phải có TLS keystore/certificate hợp lệ cho listener SASL_SSL. Certificate cần khớp hostname trong `advertised.listeners` để client xác minh TLS thành công.

## 13. Hostname, DNS và SPN phải khớp

Kerberos nhạy với tên service và hostname. Kafka client có thể thực hiện reverse DNS lookup trong quá trình SASL handshake. Cấu hình sai hostname thường gây lỗi `Server not found in Kerberos database` hoặc `GSS initiate failed`.

Kiểm tra các điểm sau:

- `bootstrap.servers` dùng FQDN có thể phân giải được.
- `advertised.listeners` trả về FQDN thật của từng broker, không phải hostname nội bộ không thể truy cập từ client.
- SPN được đăng ký theo đúng hostname broker, ví dụ `kafka/broker1.example.com@EXAMPLE.COM`.
- `sasl.kerberos.service.name` khớp service prefix `kafka` trong SPN.
- Forward DNS và reverse DNS không dẫn đến hostname khác với SPN.
- TLS certificate SAN bao gồm hostname broker mà client sử dụng.
- Không dùng IP address thay cho hostname nếu SPN được đăng ký theo FQDN.

Trong môi trường có load balancer hoặc DNS alias, cần xác định hostname nào thực sự được Kafka client dùng để tạo service ticket. Không đăng ký SPN theo alias tùy tiện nếu broker không thể xác thực principal đó.

## 14. Xác thực và phân quyền Kafka ACL

Sau khi GSSAPI xác thực client, broker có principal để authorizer kiểm tra quyền. Kafka ACL là lớp phân quyền độc lập.

Ví dụ ma trận quyền:

| Principal | Resource | Quyền cần thiết |
|---|---|---|
| `User:order-writer` | Topic `orders` | `Write`; thêm `Describe` nếu thao tác yêu cầu |
| `User:order-reader` | Topic `orders` | `Read` và quyền mô tả phù hợp |
| `User:order-reader` | Group `order-service` | `Read` để join/commit offset của consumer group |
| `User:order-admin` | Topic/cluster | Chỉ các quyền quản trị cần thiết như `Create`, `Alter` hoặc `Describe` |

Principal hiển thị trong ACL phụ thuộc quy tắc ánh xạ principal của broker. Với Kerberos, `sasl.kerberos.principal.to.local.rules` có thể chuyển principal đầy đủ thành short name để tạo principal dạng `User:order-reader`. Nếu tổ chức dùng custom `KafkaPrincipalBuilder`, cách ánh xạ có thể khác.

Không cấp `super.users` hoặc quyền cluster-wide cho ứng dụng chỉ để xử lý lỗi authorization. Hãy cấp ACL tối thiểu theo topic, group và operation thực tế.

## 15. Ticket lifetime và tự làm mới credential

Ứng dụng chạy lâu dài không thể phụ thuộc vào ticket cache hết hạn mà không có quy trình renew. Khi dùng keytab với Kafka Java client, login module và Kafka login manager có thể lấy lại credential theo vòng đời ticket/Kerberos configuration.

Các điểm cần kiểm soát:

- TGT và service ticket có thời hạn do chính sách realm quy định.
- KDC phải truy cập được từ pod/VM trong lúc login hoặc renew.
- Keytab phải còn hiệu lực và có key version được KDC chấp nhận.
- JVM process cần quyền đọc keytab trong suốt vòng đời.
- Khi rotate keytab, rollout ứng dụng và kiểm tra ticket mới trước khi thu hồi key cũ.
- Theo dõi lỗi login/reauthentication thay vì chỉ kiểm tra kết nối lúc startup.

Kafka client có các cấu hình Kerberos liên quan đến login refresh, nhưng không nên thay đổi interval mặc định nếu chưa hiểu vòng đời ticket của realm. Trước khi tinh chỉnh, kiểm tra `ticket_lifetime`, `renew_lifetime`, keytab và log login module.

## 16. Bảo vệ kết nối bằng SASL_SSL

Hai protocol thường gặp:

| Protocol | Xác thực | Mã hóa đường truyền |
|---|---|---|
| `SASL_PLAINTEXT` | SASL GSSAPI/Kerberos | Không có TLS; không phù hợp cho mạng không tin cậy |
| `SASL_SSL` | SASL GSSAPI/Kerberos | Có TLS để bảo vệ dữ liệu trên đường truyền |

Kerberos xác thực client và broker, nhưng khi yêu cầu bảo mật dữ liệu in transit, hãy dùng `SASL_SSL`. Cấu hình truststore hoặc SSL bundle để JVM xác minh chứng thư broker. Nếu cần mutual TLS, cấu hình thêm client certificate theo chính sách tổ chức; mTLS và Kerberos là hai cơ chế có thể kết hợp nhưng có mục đích khác nhau.

Không tắt hostname verification hoặc trust toàn bộ certificate để xử lý nhanh lỗi TLS. Sửa certificate SAN, trust chain và hostname broker cho đúng.

## 17. Debug và quan sát Kerberos/GSSAPI

Khi xác thực lỗi, kiểm tra từ thấp đến cao:

1. DNS và kết nối mạng đến KDC.
2. JVM đang đọc đúng `krb5.conf`.
3. Keytab chứa đúng principal và process đọc được file.
4. `kinit` lấy được TGT.
5. `kvno` lấy được service ticket cho SPN Kafka.
6. Kafka client dùng đúng service name, mechanism và JAAS config.
7. Broker dùng đúng SPN/keytab và listener GSSAPI.
8. TLS handshake thành công nếu dùng SASL_SSL.
9. Kafka ACL cho phép operation của principal.

Có thể bật Kerberos debug tạm thời bằng JVM option:

```bash
java \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -Dsun.security.krb5.debug=true \
  -jar spring-kafka-messaging.jar
```

Debug output có thể chứa principal, hostname và thông tin nhạy cảm về môi trường. Chỉ bật trong thời gian ngắn, giới hạn quyền đọc log và tắt sau khi điều tra. Không bật debug Kerberos liên tục ở production.

Các metric/log nên quan sát gồm số lần xác thực thất bại, lỗi TLS handshake, thời gian kết nối, reconnect, consumer authentication exception và Kafka authorization exception. Không log keytab, ticket cache hoặc JAAS credential.

## 18. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `No valid credentials provided` | JAAS không đăng nhập được, thiếu TGT hoặc không đọc được keytab | Kiểm tra `principal`, `keyTab`, quyền file và `kinit` |
| `Failed to find any Kerberos tgt` | Ticket cache không tồn tại/hết hạn hoặc keytab login chưa thành công | Dùng keytab cho service; kiểm tra `klist` và JAAS options |
| `Server not found in Kerberos database` | SPN sai hostname/service name hoặc chưa đăng ký trong KDC | Kiểm tra `advertised.listeners`, DNS, SPN và `sasl.kerberos.service.name` |
| `Clock skew too great` | Đồng hồ client, broker hoặc KDC lệch quá giới hạn realm | Đồng bộ NTP/time service trên các máy |
| `Preauthentication failed` | Keytab sai, key version cũ hoặc principal không khớp | Kiểm tra keytab/kvno và rotate credential đúng quy trình |
| `GSS initiate failed` | Lỗi tổng hợp trong GSSAPI handshake | Bật Kerberos debug tạm thời; kiểm tra KDC, SPN, DNS, JAAS và broker log |
| `KRB_AP_ERR_MODIFIED` | Broker dùng key không khớp SPN hoặc keytab đã đổi không đồng bộ | Xác minh SPN owner, keytab và kvno trên broker |
| `SaslAuthenticationException` | Broker từ chối xác thực hoặc client dùng mechanism/protocol sai | So sánh `GSSAPI`, `SASL_SSL`, service name và broker listener |
| `SSLHandshakeException` | Truststore thiếu CA, certificate hết hạn hoặc SAN không khớp hostname | Kiểm tra trust chain, certificate và hostname verification |
| `TopicAuthorizationException` | Kerberos xác thực thành công nhưng principal thiếu ACL | Xem principal broker log ghi nhận và cấp ACL tối thiểu |
| `GroupAuthorizationException` | Principal không có quyền `Read` trên consumer group | Cấp ACL cho đúng group ID |
| Kết nối chậm khi SASL handshake | DNS/reverse DNS lookup chậm hoặc dùng hostname không chuẩn | Dùng FQDN ổn định và kiểm tra DNS resolution |

Đừng xử lý mọi `SaslAuthenticationException` bằng cách thay keytab ngay. Trước tiên phân biệt lỗi Kerberos login, SPN, TLS và ACL vì chúng nằm ở các tầng khác nhau.

## 19. Kiểm thử tích hợp Kerberos với Spring Kafka

Kiểm thử cần xác nhận cả xác thực, phân quyền và nghiệp vụ Kafka:

1. **Login độc lập:** chạy `kinit -kt` bằng keytab của service principal.
2. **Service ticket:** dùng `kvno kafka/broker1.example.com@EXAMPLE.COM` để xác minh SPN.
3. **Producer:** gửi record đến topic được cấp quyền và xác nhận send future thành công.
4. **Consumer:** đọc record bằng group ID được cấp ACL.
5. **ACL deny:** dùng principal không có quyền và xác nhận broker từ chối đúng operation.
6. **Principal mapping:** xác minh principal đầy đủ được ánh xạ đúng short name mà ACL sử dụng.
7. **TLS:** xác nhận certificate chain và hostname broker được JVM tin cậy.
8. **Keytab rotation:** thay keytab theo quy trình và xác nhận ứng dụng có thể reconnect/reauthenticate.
9. **KDC unavailable:** xác minh hành vi reconnect/renew và cảnh báo vận hành.
10. **Broker restart:** xác nhận producer/consumer kết nối lại và GSSAPI handshake thành công.

Một môi trường integration test có thể dùng Kafka broker và Kerberos KDC test realm trong container hoặc VM riêng. Không dùng principal/keytab production trong test. Unit test cho cấu hình YAML không chứng minh ticket exchange và broker ACL hoạt động; cần ít nhất một bài test end-to-end với KDC và broker đã bật GSSAPI.

## 20. Quy trình triển khai production

1. Tạo principal riêng cho ứng dụng và SPN riêng cho từng broker hostname.
2. Cấu hình realm/KDC và đồng bộ thời gian giữa client, broker và KDC.
3. Tạo keytab, kiểm tra bằng `klist`, `kinit` và `kvno`.
4. Cấu hình broker listener `SASL_SSL`, bật `GSSAPI` và dùng broker keytab tương ứng.
5. Cấu hình Spring Boot `security.protocol=SASL_SSL`, `sasl.mechanism=GSSAPI`, service name và `sasl.jaas.config`.
6. Mount keytab/truststore qua secret management và giới hạn quyền đọc.
7. Cấp Kafka ACL tối thiểu cho principal producer, consumer và admin.
8. Kiểm tra `bootstrap.servers`, `advertised.listeners`, DNS, SPN và certificate SAN.
9. Kiểm thử producer, consumer, authorization deny, restart và keytab rotation.
10. Theo dõi login failure, TLS failure, ACL denial, ticket expiry và reconnect sau triển khai.

## 21. Tổng kết

- Kerberos xác thực bằng ticket; GSSAPI là API/cơ chế SASL mà Kafka dùng để thực hiện xác thực Kerberos.
- Client dùng principal và keytab của ứng dụng; mỗi broker có service principal theo hostname.
- `sasl.kerberos.service.name` phải khớp service prefix trong SPN broker, thường là `kafka`.
- JVM cần đọc đúng `krb5.conf`; JAAS `Krb5LoginModule` thường dùng `useKeyTab=true`, `storeKey=true`, `principal`, `keyTab` và `doNotPrompt=true` cho service chạy nền.
- Spring Boot truyền Kafka client security properties qua `spring.kafka.security.protocol` và `spring.kafka.properties.*`; có thể override JAAS riêng cho producer, consumer và admin.
- `SASL_SSL` kết hợp Kerberos authentication với TLS encryption; `SASL_PLAINTEXT` không mã hóa dữ liệu Kafka trên đường truyền.
- Kerberos authentication và Kafka ACL authorization là hai bước riêng biệt.
- FQDN, DNS, `advertised.listeners`, SPN, clock synchronization và keytab kvno phải khớp.
- Keytab là secret; cần quản lý quyền file, rotation và không commit vào source control.
- Kiểm thử end-to-end phải có KDC, broker GSSAPI, TLS và ACL; chỉ kiểm tra YAML chưa đủ.

Khi cấu hình đúng Kerberos/GSSAPI, ứng dụng Spring Kafka có thể xác thực bằng danh tính service được quản lý tập trung, trong khi Kafka ACL kiểm soát chính xác topic và consumer group mà ứng dụng được phép truy cập.

## Tài liệu tham khảo

- [Apache Kafka — Authentication using SASL (GSSAPI/Kerberos)](https://kafka.apache.org/44/security/authentication-using-sasl/)
- [Apache Kafka — Broker Configurations](https://kafka.apache.org/44/configuration/broker-configs/)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Java SE — Krb5LoginModule](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html)
