# Bảo vệ dữ liệu nhạy cảm trong payload, headers và bản ghi lỗi

Kafka lưu và phân phối record theo topic-partition. Một record không chỉ có value; nó còn có key, headers, timestamp và metadata được bổ sung trong quá trình retry, deserialize hoặc chuyển sang Dead Letter Topic (DLT). Dữ liệu nhạy cảm có thể xuất hiện ở bất kỳ vị trí nào: email trong JSON payload, access token trong header, số điện thoại trong Kafka key, hoặc thông tin cá nhân bị lộ trong exception message và stack trace.

Muốn bảo vệ dữ liệu trong Kafka, cần kiểm soát toàn bộ vòng đời của record: dữ liệu nào được phép phát đi, trường nào cần tokenization hoặc mã hóa, ai được đọc topic, header nào được giữ khi retry, DLT được lưu bao lâu và log nào được phép ghi payload. TLS, SASL và ACL bảo vệ kết nối và quyền truy cập; chúng không tự che một trường nhạy cảm khỏi mọi consumer đã có quyền đọc topic.

Bài này xây dựng một luồng đơn hàng có email khách hàng nhạy cảm, hướng dẫn giảm dữ liệu, mã hóa trường bằng AES-GCM, bảo vệ Kafka headers, cấu hình TLS/SASL và ACL, xử lý ErrorHandlingDeserializer, làm sạch DLT headers, giới hạn log và vận hành retention. Ví dụ dùng Java/Spring Kafka; các nguyên tắc áp dụng tương tự cho Kafka Producer, Consumer, Connect và Streams.

## 1. Xác định dữ liệu cần bảo vệ

Trước khi chọn thuật toán hoặc cấu hình broker, hãy lập danh mục dữ liệu. Không phải mọi trường đều có cùng mức độ nhạy cảm hoặc cùng yêu cầu truy cập.

| Nhóm dữ liệu | Ví dụ | Cách xử lý gợi ý |
|---|---|---|
| Định danh công khai | eventType, schemaVersion | Có thể để dạng rõ nếu không tiết lộ nội bộ |
| Định danh nghiệp vụ | orderId, customerId | Dùng ID nội bộ hoặc token ổn định; tránh dùng email/số điện thoại làm key |
| Dữ liệu cá nhân | Họ tên, email, số điện thoại, địa chỉ | Chỉ gửi nếu consumer thực sự cần; tokenization hoặc mã hóa trường |
| Dữ liệu tài chính | Tài khoản, thông tin thanh toán, số thẻ | Không đưa dữ liệu thẻ nhạy cảm vào event nếu không cần; token từ payment provider hoặc mã hóa đầu cuối |
| Bí mật xác thực | Password, API key, bearer token, cookie, private key | Không đưa vào payload, key, header, exception hoặc log |
| Metadata vận hành | Trace ID, tenant ID, source topic, partition, offset | Dùng giá trị không chứa PII; giới hạn quyền đọc metadata |
| Dữ liệu lỗi | Raw bytes, exception message, stack trace | Xem như dữ liệu có độ nhạy cao; giới hạn truy cập và retention |

Một trường có thể không phải bí mật nhưng vẫn cho phép liên kết danh tính. Ví dụ orderId kết hợp timestamp và tenantId có thể nhận diện một khách hàng trong hệ thống nhỏ. Hãy đánh giá cả dữ liệu đơn lẻ và khả năng kết hợp nhiều trường.

## 2. Threat model: dữ liệu đi qua những đâu?

Record có thể được sao chép ở nhiều lớp:

~~~mermaid
flowchart TD
    A[Application source] --> B[Producer payload / key / headers]
    B --> C[TLS network]
    C --> D[Kafka broker and replicas]
    D --> E[Consumer application]
    E --> F[Retry topic]
    E --> G[DLT / quarantine]
    E --> H[Application logs / tracing]
    D --> I[Disk / snapshots / backups]
    G --> H
~~~

Hãy kiểm tra ít nhất các điểm sau:

- Producer log payload trước khi gửi.
- Kafka key có chứa email, phone hoặc mã định danh trực tiếp.
- Header có Authorization, cookie, token hoặc dữ liệu cá nhân.
- Broker log, request log, JMX và audit log.
- Consumer log toàn bộ ConsumerRecord hoặc exception.
- Retry topic và DLT sao chép payload/header gốc.
- Connector, mirror, stream processor, backup và data lake tạo thêm bản sao.

Mã hóa TLS chỉ bảo vệ đường truyền giữa client và broker. Broker vẫn nhận được plaintext sau khi giải mã TLS. Kafka không tự mã hóa log segment, index và snapshot trên đĩa; dữ liệu ở disk cần filesystem/block encryption hoặc message-level encryption. Nếu broker operator cũng nằm ngoài trust boundary, cần mã hóa payload ở producer trước khi gửi và giải mã trong consumer được cấp quyền. [Apache Kafka Security Model](https://kafka.apache.org/44/security/security-model/)

## 3. Data minimization: không phát dữ liệu không cần thiết

Cách bảo vệ hiệu quả nhất thường là không đưa dữ liệu nhạy cảm vào event. Event nên chứa dữ liệu đủ để consumer thực hiện nhiệm vụ, không nên là bản sao đầy đủ của database row.

Ví dụ không nên phát:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ord-1001",
  "customer": {
    "fullName": "Nguyen Van A",
    "email": "customer@example.test",
    "phone": "+84901234567",
    "address": "12 Example Street",
    "password": "plaintext-password",
    "accessToken": "eyJhbGciOi..."
  },
  "payment": {
    "cardNumber": "4111111111111111",
    "cvv": "123"
  }
}
~~~

Event tối giản hơn:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "orderId": "ord-1001",
  "customerRef": "cus-token-8f21",
  "paymentRef": "pay-token-3b10",
  "amount": 125000,
  "currency": "VND"
}
~~~

Consumer cần hiển thị email có thể gọi customer service bằng customerRef sau khi được xác thực và phân quyền. Consumer chỉ cần tổng hợp doanh thu không cần nhận email, phone hay địa chỉ.

Nguyên tắc thiết kế:

1. Mỗi event chỉ chứa trường mà downstream cần để hoàn thành nhiệm vụ.
2. Không đưa password, API key, bearer token, cookie hoặc private key vào event.
3. Dùng ID ngẫu nhiên hoặc token thay cho email/số điện thoại làm Kafka key.
4. Tách event nghiệp vụ khỏi dữ liệu hồ sơ khách hàng.
5. Đặt schema owner và data owner cho từng trường nhạy cảm.
6. Có quy trình thay đổi schema khi một trường được phân loại nhạy cảm hơn.

## 4. Tokenization, hashing và encryption

Ba kỹ thuật này giải quyết các bài toán khác nhau:

| Kỹ thuật | Kết quả | Có thể khôi phục? | Lưu ý |
|---|---|---|---|
| Tokenization | Thay giá trị bằng token ngẫu nhiên có mapping ở hệ thống riêng | Có, qua token vault/service được bảo vệ | Phù hợp khi cần liên kết nhưng không muốn phát PII |
| Hash | Tạo digest một chiều | Không trực tiếp | Email/phone có không gian giá trị nhỏ; hash không khóa có thể bị dò từ điển |
| HMAC | Tạo digest có khóa bí mật | Không trực tiếp | Dùng để so khớp ổn định mà không công khai dữ liệu gốc; phải bảo vệ và xoay HMAC key |
| Encryption | Biến plaintext thành ciphertext bằng khóa | Có, khi có khóa phù hợp | Cần quản lý key, nonce, quyền giải mã và rotation |

Không dùng SHA-256 thuần để “ẩn” email hoặc số điện thoại. Kẻ tấn công có thể tạo danh sách email/phone phổ biến, hash rồi đối chiếu. Nếu cần giá trị so khớp ổn định, dùng HMAC với key nằm ngoài Kafka và giới hạn service được phép tính HMAC.

Tokenization không phải encryption. Token vault cần ACL, audit, rate limit và chính sách mapping riêng. Nếu nhiều consumer chỉ cần cùng một customer reference, hãy cấp token ổn định theo phạm vi tenant hoặc use case để giảm khả năng liên kết chéo.

## 5. Mã hóa trường nhạy cảm trong payload

Kafka không cung cấp mã hóa từng field ở tầng broker. Ứng dụng có thể mã hóa trường nhạy cảm trước khi gọi producer send. Các trường cần filter, routing hoặc aggregate có thể giữ dạng rõ nếu đã được phân loại an toàn; trường PII được lưu dưới dạng ciphertext.

Một envelope mã hóa thường chứa:

| Trường | Mục đích |
|---|---|
| algorithm | Phiên bản thuật toán, ví dụ AES-256-GCM |
| keyId | ID tham chiếu tới key trong KMS |
| nonce | Nonce ngẫu nhiên duy nhất cho lần mã hóa |
| ciphertext | Dữ liệu đã mã hóa, gồm authentication tag |
| encryptionVersion | Phiên bản format để hỗ trợ rotation/migration |

Không đặt raw encryption key hoặc data-encryption key (DEK) vào Kafka record. Chỉ lưu keyId và wrapped DEK nếu dùng envelope encryption; KMS/key vault giữ key-encryption key và kiểm soát quyền unwrap.

### 5.1. AES-GCM trong Java

Ví dụ sau dùng SecretKey được cấp từ KMS hoặc secret manager. Không tự sinh key cố định trong source code và không ghi key ra log.

~~~java
package com.example.orders.crypto;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;

public final class FieldEncryptor {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final SecureRandom secureRandom = new SecureRandom();

    public EncryptedField encrypt(
            String plaintext,
            SecretKey dataKey,
            String keyId,
            String eventId,
            String fieldName) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        secureRandom.nextBytes(nonce);

        byte[] aad = associatedData(eventId, fieldName);
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, dataKey,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);

        byte[] ciphertext = cipher.doFinal(
                plaintext.getBytes(StandardCharsets.UTF_8));

        return new EncryptedField(
                "AES-256-GCM",
                keyId,
                Base64.getEncoder().encodeToString(nonce),
                Base64.getEncoder().encodeToString(ciphertext));
    }

    public String decrypt(
            EncryptedField encrypted,
            SecretKey dataKey,
            String eventId,
            String fieldName) throws Exception {

        byte[] nonce = Base64.getDecoder().decode(encrypted.nonce());
        byte[] ciphertext = Base64.getDecoder().decode(encrypted.ciphertext());

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, dataKey,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(associatedData(eventId, fieldName));

        byte[] plaintext = cipher.doFinal(ciphertext);
        return new String(plaintext, StandardCharsets.UTF_8);
    }

    private byte[] associatedData(String eventId, String fieldName) {
        return ("orders-v1|" + eventId + "|" + fieldName)
                .getBytes(StandardCharsets.UTF_8);
    }

    public record EncryptedField(
            String algorithm,
            String keyId,
            String nonce,
            String ciphertext) {
    }
}
~~~

AES-GCM cung cấp confidentiality và integrity. Nếu nonce, ciphertext hoặc AAD bị sửa, decrypt sẽ thất bại khi xác thực tag. Với mỗi key, nonce phải không bị tái sử dụng; dùng SecureRandom và thiết kế key rotation phù hợp với volume. AAD ràng buộc ciphertext với eventId/fieldName nhưng không được xem là bí mật.

Trong ví dụ, tên thuật toán AES-256-GCM giả định dataKey có độ dài 256 bit. Kiểm tra key size khi nhận key từ KMS; không tự cắt hoặc pad key để ép đủ độ dài. Với AES-GCM, nonce 96 bit là lựa chọn khuyến nghị phổ biến và không được tái sử dụng với cùng key. Ở hệ thống có volume rất lớn, cần thiết kế nonce/key rotation theo giới hạn số lần mã hóa của GCM.

Ví dụ record:

~~~java
public record OrderPlacedEvent(
        String eventId,
        String orderId,
        String customerRef,
        FieldEncryptor.EncryptedField customerEmail,
        long amount,
        String currency
) {
}
~~~

Consumer xử lý tổng hợp có thể đọc orderId, amount và currency mà không cần giải mã customerEmail. Chỉ service được phép gửi thông báo mới nhận quyền lấy DEK từ KMS và giải mã trường email.

### 5.2. Envelope encryption và quản lý khóa

Trong production, thường không dùng một master key trực tiếp cho mọi record. Một mô hình phổ biến:

1. KMS tạo hoặc cấp DEK cho tenant/dataset/rotation window.
2. Producer dùng DEK mã hóa field bằng AES-GCM.
3. KMS wrap DEK bằng key-encryption key (KEK).
4. Record lưu keyId, wrapped DEK, nonce và ciphertext.
5. Consumer được cấp quyền gọi KMS unwrap DEK theo policy.
6. DEK được cache trong memory trong thời gian ngắn nếu policy cho phép; không ghi ra log hoặc disk tùy tiện.
7. Khi rotation, phát hành keyId mới và duy trì khả năng giải mã record cũ trong retention window.

Phải xác định rõ ai có quyền encrypt, decrypt, rotate, disable và destroy key. Nếu hủy key quá sớm, dữ liệu còn trong Kafka, retry topic, DLT hoặc backup có thể không giải mã được nữa. Nếu giữ key vô thời hạn, dữ liệu đã hết retention vẫn có thể phục hồi từ bản sao cũ.

## 6. Encryption at rest và encryption in transit

Hai lớp này có mục tiêu khác nhau:

| Lớp | Bảo vệ điều gì? | Không bảo vệ điều gì? |
|---|---|---|
| TLS | Dữ liệu trên kết nối client-broker và broker-broker | Broker đã giải mã, disk, backup, consumer được cấp quyền |
| Filesystem/block encryption | Disk, volume hoặc thiết bị lưu trữ bị lấy cắp | Người có quyền đăng nhập broker và đọc file |
| Message-level encryption | Payload/field được mã hóa trước khi gửi Kafka | Metadata/header không được mã hóa, trừ khi ứng dụng mã hóa chúng |
| ACL | Ai được đọc/ghi topic, group và resource | Không giới hạn theo từng field bên trong một record |

Apache Kafka không mã hóa log segment, index hoặc snapshot trên đĩa. Nếu yêu cầu bảo vệ disk, bật encryption ở filesystem/block device và cả backup/volume snapshot. Nếu cần ngăn broker operator đọc plaintext, producer phải mã hóa message trước khi send; điều này cũng làm Kafka Streams/Connect không thể xử lý trực tiếp field ciphertext nếu không có quyền giải mã. [Kafka Security Model – Encryption at Rest](https://kafka.apache.org/44/security/security-model/)

## 7. TLS, SASL và xác thực client

Kafka listener có bốn protocol phổ biến:

| Protocol | Authentication | Encryption |
|---|---|---|
| PLAINTEXT | Không | Không |
| SSL | Có thể dùng mutual TLS | TLS |
| SASL_PLAINTEXT | SASL | Không |
| SASL_SSL | SASL, có thể kết hợp mTLS | TLS |

Production nên dùng TLS cho mọi kết nối không nằm trong một trust boundary cô lập. Có thể dùng SASL/SCRAM hoặc OAuth/OIDC theo hệ thống identity; mTLS hữu ích cho broker-to-broker và controller-to-broker. Không dùng SASL/PLAIN trên SASL_PLAINTEXT vì username/password không được mã hóa trên đường truyền.

Ví dụ client properties với SASL_SSL và SCRAM:

~~~properties
bootstrap.servers=kafka-1.example.internal:9093,kafka-2.example.internal:9093
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-producer" password="INJECT_FROM_SECRET_PROVIDER";
ssl.truststore.location=/run/secrets/kafka-client.truststore.jks
ssl.truststore.password=INJECT_FROM_SECRET_PROVIDER
ssl.endpoint.identification.algorithm=https
~~~

Đây là mẫu cấu hình, không phải thông tin đăng nhập dùng thật. Inject secret bằng secret manager, ConfigProvider hoặc cơ chế secret injection của nền tảng. Không commit password vào Git, Docker image, Helm values công khai, log hoặc exception.

TLS cần được cấu hình riêng cho từng listener. Kết nối controller và inter-broker nên nằm trên listener nội bộ; không expose controller listener cho client. advertised.listeners cũng là một phần của network boundary vì client sẽ kết nối tới địa chỉ broker được quảng bá sau metadata fetch.

## 8. Authorization bằng ACL và nguyên tắc least privilege

Authentication xác định principal; authorization quyết định principal đó được làm gì. KRaft có StandardAuthorizer. ACL có thể áp dụng cho Topic, Group, Cluster, TransactionalId và resource khác.

Ví dụ phân quyền:

| Principal | Resource | Quyền tối thiểu theo use case |
|---|---|---|
| orders-producer | orders.events | WRITE, DESCRIBE |
| orders-consumer | orders.events | READ, DESCRIBE |
| orders-consumer | group orders-service | READ |
| orders-recovery | orders.events-dlt | READ |
| orders-recoverer | orders.events-dlt | WRITE, DESCRIBE |
| kafka-admin | Cluster và resource quản trị | Chỉ cấp cho operator được ủy quyền |

Ví dụ tạo ACL cho producer:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1.example.internal:9093 \
  --command-config admin-client.properties \
  --add --allow-principal User:orders-producer \
  --operation Write --operation Describe \
  --topic orders.events
~~~

Ví dụ tạo ACL cho consumer:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1.example.internal:9093 \
  --command-config admin-client.properties \
  --add --allow-principal User:orders-consumer \
  --operation Read --operation Describe \
  --topic orders.events

kafka-acls.sh --bootstrap-server kafka-1.example.internal:9093 \
  --command-config admin-client.properties \
  --add --allow-principal User:orders-consumer \
  --operation Read --group orders-service
~~~

ACL kiểm soát quyền ở cấp topic/group. Một consumer có READ trên orders.events thường có thể đọc toàn bộ payload và headers của record trong topic đó. Nếu một nhóm consumer chỉ được phép xem amount nhưng không được xem email, hãy mã hóa email ở producer hoặc tách dữ liệu sang topic/service riêng; ACL không phải field-level security.

Không dùng super.users cho service account thông thường. Tránh cấp wildcard READ trên toàn cluster và tránh bật allow.everyone.if.no.acl.found=true như trạng thái vận hành lâu dài. Authentication mà không có authorizer không tạo ra ranh giới quyền đọc dữ liệu giữa các principal. [Apache Kafka Security Model – Authorization](https://kafka.apache.org/44/security/security-model/)

## 9. Bảo vệ Kafka headers

Headers thường bị xem là metadata vô hại, nhưng chúng có thể chứa:

- Authorization bearer token, API key hoặc session cookie.
- Email, số điện thoại, tên khách hàng.
- Tenant ID có thể liên kết với một khách hàng cụ thể.
- SQL query, URL có query parameter, exception detail.
- Class name hoặc package nội bộ được serializer tự động thêm.

Không dùng header để vận chuyển secret. Header vẫn là một phần của Kafka record và có thể được đọc bởi consumer có quyền READ. TLS không che header khỏi broker hoặc consumer được cấp quyền.

Ví dụ header không nên phát:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Headers;

void addUnsafeHeaders(
        Headers headers,
        String bearerToken,
        String email,
        String sessionCookie) {
    headers.add("Authorization",
            bearerToken.getBytes(StandardCharsets.UTF_8));
    headers.add("customer-email",
            email.getBytes(StandardCharsets.UTF_8));
    headers.add("session-cookie",
            sessionCookie.getBytes(StandardCharsets.UTF_8));
}
~~~

Thay bằng metadata tối thiểu:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Headers;

void addSafeHeaders(
        Headers headers,
        String eventId,
        String traceParent) {
    headers.add("event-id", eventId.getBytes(StandardCharsets.UTF_8));
    headers.add("traceparent", traceParent.getBytes(StandardCharsets.UTF_8));
    headers.add("content-type",
            "application/json".getBytes(StandardCharsets.UTF_8));
    headers.add("schema-version", "1".getBytes(StandardCharsets.UTF_8));
}
~~~

Correlation ID và trace ID nên là giá trị ngẫu nhiên, không nhúng email/phone hoặc thông tin nhận diện. Nếu tenant ID nhạy cảm, dùng tenant token hoặc mã hóa header theo quy ước có thể quản lý.

Spring Kafka JsonSerializer có thể thêm type information vào headers theo mặc định. Nếu class/package name tiết lộ cấu trúc nội bộ, tắt type headers và dùng schema/version mapping ổn định:

~~~properties
spring.kafka.producer.properties.spring.json.add.type.headers=false
~~~

Không dựa vào việc deserializer xóa type header ở consumer để coi dữ liệu đó đã được bảo vệ; header vẫn được lưu trong Kafka và có thể được consumer khác đọc.

## 10. Không để payload xuất hiện trong application logs

Các pattern dễ làm lộ dữ liệu:

~~~java
log.info("Received record: {}", record);
log.error("Failed to process payload={}", event, exception);
log.debug("Headers: {}", record.headers());
~~~

Không log toàn bộ record, payload hoặc headers ở production. Thay bằng metadata đã được duyệt:

~~~java
log.info(
        "Order event received eventId={} topic={} partition={} offset={}",
        safeEventId,
        record.topic(),
        record.partition(),
        record.offset());
~~~

Khi log lỗi, ghi failure code và exception class; chỉ ghi message sau khi đã kiểm tra không chứa dữ liệu đầu vào hoặc secret:

~~~java
log.warn(
        "Order processing failed eventId={} failureCode={} exceptionType={}",
        safeEventId,
        "CUSTOMER_LOOKUP_TIMEOUT",
        exception.getClass().getSimpleName());
~~~

Không ghi stack trace đầy đủ vào một hệ thống log có quyền truy cập rộng nếu exception có thể chứa payload, SQL, URL, token hoặc thông tin cá nhân. Nếu cần forensic detail, ghi vào kho log hạn chế quyền, có retention ngắn và audit truy cập.

## 11. ErrorHandlingDeserializer và dữ liệu lỗi

Deserialization xảy ra trước khi listener nhận record. Nếu deserializer ném exception, listener không có object để xử lý. Spring Kafka cung cấp ErrorHandlingDeserializer để bắt lỗi deserialize và đưa thông tin lỗi cùng raw bytes vào header của record lỗi.

Điều này giúp error handler xử lý record malformed, nhưng raw bytes có thể chứa toàn bộ payload nhạy cảm ban đầu. Không log các header này và không gửi chúng sang DLT có quyền truy cập rộng.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false
~~~

Trusted packages nên giới hạn đúng package cần thiết; không dùng wildcard chỉ để né lỗi deserialize. ErrorHandlingDeserializer có thể lưu raw bytes trong DeserializationException header. Khi DeadLetterPublishingRecoverer làm việc với ErrorHandlingDeserializer, framework có thể khôi phục raw key/value ban đầu để publish DLT. Vì vậy, DLT vẫn có thể chứa payload lỗi nguyên bản dù listener chưa từng deserialize thành object. [Spring Kafka – Serialization and Deserialization](https://docs.spring.io/spring-kafka/docs/3.3.x/reference/kafka/serdes.html)

DLT producer phải serialize được cả object đã deserialize và raw byte[] của record lỗi deserialize. Có thể dùng DelegatingByTypeSerializer hoặc nhiều KafkaTemplate cho từng kiểu dữ liệu. Nếu template chỉ có JsonSerializer cho OrderEvent, đừng giả định nó tự xử lý đúng raw byte[] từ ErrorHandlingDeserializer.

## 12. DLT có thể nhạy cảm hơn topic gốc

DeadLetterPublishingRecoverer mặc định gửi record tới topic có hậu tố -dlt và cùng partition với record gốc. DLT vì thế cần ít nhất số partition bằng topic gốc khi dùng resolver mặc định.

Spring Kafka giữ các headers gốc và bổ sung thông tin như:

| DLT header | Rủi ro dữ liệu |
|---|---|
| DLT_EXCEPTION_FQCN | Tiết lộ class/package nội bộ |
| DLT_EXCEPTION_CAUSE_FQCN | Tiết lộ cấu trúc lỗi nội bộ |
| DLT_EXCEPTION_MESSAGE | Có thể chứa dữ liệu đầu vào, SQL, URL hoặc secret |
| DLT_EXCEPTION_STACKTRACE | Có thể chứa payload, query, token và đường dẫn nội bộ |
| DLT_ORIGINAL_TOPIC | Tiết lộ tên luồng nghiệp vụ |
| DLT_ORIGINAL_PARTITION/OFFSET | Metadata để truy vết record |
| DLT_ORIGINAL_TIMESTAMP | Thời điểm phát sinh |
| DLT_ORIGINAL_CONSUMER_GROUP | Tiết lộ tên ứng dụng/consumer group |

Nếu record đã có Authorization hoặc customer-email header, DLT mặc định có thể giữ lại các header đó. Retry và replay nhiều lần còn có thể làm header history tăng kích thước; stack trace lặp có thể khiến record vượt giới hạn kích thước. DLT không phải vùng lưu trữ ít nhạy cảm hơn; nó thường là nơi chứa payload lỗi và chi tiết kỹ thuật nhất. [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)

## 13. Làm sạch DLT headers bằng allowlist

Nếu chỉ thêm một header function, Spring Kafka chỉ thêm header; nó không loại bỏ header gốc. Khi cần xóa hoặc thay đổi header đã được copy, subclass DeadLetterPublishingRecoverer và override createProducerRecord().

Ví dụ dưới đây chỉ giữ event ID, trace context, content type và metadata nguồn cần cho điều tra. Header exception message/stack trace và header gốc không nằm trong allowlist sẽ bị loại:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.support.KafkaHeaders;

import java.util.Set;

public final class SanitizingDeadLetterRecoverer
        extends DeadLetterPublishingRecoverer {

    private static final Set<String> ALLOWED_HEADERS = Set.of(
            "event-id",
            "traceparent",
            "tracestate",
            "content-type",
            KafkaHeaders.DLT_ORIGINAL_TOPIC,
            KafkaHeaders.DLT_ORIGINAL_PARTITION,
            KafkaHeaders.DLT_ORIGINAL_OFFSET,
            KafkaHeaders.DLT_ORIGINAL_TIMESTAMP,
            KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP);

    public SanitizingDeadLetterRecoverer(KafkaTemplate<Object, Object> template) {
        super(template);
    }

    @Override
    protected ProducerRecord<Object, Object> createProducerRecord(
            ConsumerRecord<?, ?> record,
            TopicPartition topicPartition,
            Headers headers,
            byte[] key,
            byte[] value) {

        for (Header header : headers.toArray()) {
            if (!ALLOWED_HEADERS.contains(header.key())) {
                headers.remove(header.key());
            }
        }

        return super.createProducerRecord(
                record, topicPartition, headers, key, value);
    }
}
~~~

Đăng ký recoverer với container error handler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorHandlingConfiguration {
    @Bean
    DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
            KafkaTemplate<Object, Object> dltTemplate) {
        return new SanitizingDeadLetterRecoverer(dltTemplate);
    }

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            DeadLetterPublishingRecoverer recoverer) {
        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1000L, 2L));
    }
}
~~~

Khi dùng Spring Boot, khai báo CommonErrorHandler/DefaultErrorHandler bean để Boot gắn vào listener container factory được auto-configure; nếu tự tạo factory, gọi setCommonErrorHandler() trên factory đó. DLT template cần serializer tương thích với cả payload thông thường và raw byte[] nếu ứng dụng xử lý deserialization failure.

Allowlist phải được điều chỉnh theo nhu cầu điều tra thực tế. Đừng thêm header chỉ vì nó tiện; mỗi header cần có owner, mục đích và mức độ nhạy cảm. Ví dụ này chỉ lọc headers, không mã hóa hay che payload/key. Nếu raw value trong DLT chứa PII, cần bảo vệ payload ở producer hoặc đưa DLT vào vùng cách ly có ACL, mã hóa disk, retention ngắn và quy trình truy cập riêng.

Nếu cần giữ thông tin lỗi, tạo failureCode có danh sách giá trị cố định như INVALID_SCHEMA, CUSTOMER_LOOKUP_TIMEOUT hoặc PAYMENT_DECLINED. Tránh lưu exception.getMessage() trực tiếp; exception message có thể bao gồm input người dùng.

## 14. Retry topics cũng cần chính sách dữ liệu

Retry topic giữ record để thử lại sau. Nó thường giữ nguyên key/value và một phần header của record gốc. Vì vậy retry topic cần cùng mức phân loại dữ liệu và bảo vệ như topic nguồn:

- Cùng yêu cầu TLS, ACL và encryption at rest.
- Retention đủ dài cho retry window nhưng không dài hơn yêu cầu nghiệp vụ.
- Không dùng consumer group rộng để đọc retry topic.
- Không log raw payload khi kiểm tra retry backlog.
- Giới hạn ai được replay hoặc copy record từ retry topic.
- Kiểm soát headers được giữ qua mỗi lần retry.

Khi dùng Spring Kafka non-blocking retry, hãy kiểm tra header history và stack trace header. DeadLetterPublishingRecoverer có các cơ chế appendOriginalHeaders và stripPreviousExceptionHeaders; cấu hình phù hợp giúp tránh header phình to khi record được chuyển qua nhiều retry topic.

## 15. Retention, compaction và xóa dữ liệu

Kafka retention không phải secure erase tức thời. Một record hết hạn có thể còn tồn tại trong segment chưa được xóa vật lý, replica, snapshot, backup, tiered storage, retry topic hoặc DLT.

Khi thiết kế retention:

1. Xác định thời gian cần xử lý, retry, replay và điều tra.
2. Đặt retention riêng cho topic chính, retry, DLT và quarantine.
3. Kiểm kê bản sao ở Connect sink, data lake, mirror cluster và backup.
4. Có quy trình xử lý yêu cầu xóa/ẩn danh dữ liệu ở các hệ thống downstream.
5. Xác định thời gian giữ key mã hóa; việc hủy key có thể làm ciphertext không thể giải mã nhưng không tự xóa record.
6. Kiểm tra compacted topic: tombstone và compaction không bảo đảm xóa ngay mọi bản sao trên disk/backup.

Không dùng log compaction hoặc tombstone như một cam kết xóa dữ liệu cá nhân tức thời. Nếu nghiệp vụ có yêu cầu xóa, cần thiết kế data ownership và deletion workflow xuyên suốt các hệ thống.

## 16. Bảo vệ log, audit và quyền truy cập vận hành

Kafka authorizer có thể log quyết định ACL. Audit log nên được chuyển tới hệ thống lưu trữ bền vững, append-only và có quyền truy cập hạn chế. Request log chi tiết có thể hữu ích cho forensic nhưng rất verbose và có thể làm lộ metadata; chỉ bật khi cần và có retention rõ.

Phân tách quyền:

| Vai trò | Quyền phù hợp |
|---|---|
| Application producer | Ghi đúng topic được giao |
| Application consumer | Đọc đúng topic và group |
| DLT operator | Đọc DLT, không nhất thiết đọc topic gốc |
| Security operator | Quản lý ACL, certificate và key policy |
| Platform operator | Quản trị broker/cluster theo quy trình break-glass |
| Auditor | Đọc audit metadata đã kiểm soát, không mặc định đọc payload |

JMX, Admin API và broker/controller listener là các bề mặt riêng. Bảo vệ producer/consumer traffic không tự bảo vệ JMX hoặc công cụ quản trị. Không expose JMX không xác thực ra mạng người dùng.

## 17. Cấu hình producer và consumer trong Spring Boot

Ví dụ producer gửi JSON, dùng TLS/SASL qua externalized configuration và tắt type headers:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.internal:9093
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      ssl.endpoint.identification.algorithm: https
~~~

Thông tin JAAS và truststore password được inject từ secret provider/environment theo deployment platform. Không commit giá trị bí mật trong application.yml. Nếu dùng ConfigProvider, giới hạn allowed paths chỉ tới thư mục secret được phép đọc.

Consumer có thể dùng ErrorHandlingDeserializer như phần trước. Producer/consumer có quyền khác nhau; không dùng chung service principal có cả quyền đọc mọi topic và ghi mọi topic nếu không cần.

## 18. Lab: phát event an toàn và xử lý DLT

Mục tiêu: tạo event chỉ chứa customerRef, mã hóa email ở producer, chỉ dùng header allowlist và chuyển record lỗi sang DLT đã làm sạch header.

### Bước 1: thiết kế payload

~~~json
{
  "eventId": "evt-2001",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "orderId": "ord-2001",
  "customerRef": "cus-token-71a2",
  "customerEmail": {
    "algorithm": "AES-256-GCM",
    "keyId": "orders-pii-2026-01",
    "nonce": "BASE64_NONCE",
    "ciphertext": "BASE64_CIPHERTEXT"
  },
  "amount": 250000,
  "currency": "VND"
}
~~~

Email ở đây là ciphertext; producer chỉ giữ customerRef để routing và tra cứu. Không gửi password, API token hoặc dữ liệu thẻ.

### Bước 2: kiểm tra headers

Chỉ phát event-id, traceparent, content-type và schema-version. Thử thêm header Authorization trong môi trường lab rồi xác nhận sanitizing recoverer loại nó khỏi DLT.

### Bước 3: cấu hình broker/client security

Bật listener SASL_SSL, cấu hình SCRAM credential và truststore. Cấp ACL producer chỉ WRITE topic đầu vào; consumer chỉ READ topic và group cần thiết. Xác minh principal không đọc được DLT nếu không có quyền.

### Bước 4: gây lỗi listener

Cho listener ném exception có chứa một chuỗi giả lập như email hoặc token. Kiểm tra DLT chỉ giữ failure code/metadata cho phép; stack trace và exception message không xuất hiện trong headers của DLT.

### Bước 5: kiểm tra deserialization failure

Gửi JSON malformed. Xác nhận ErrorHandlingDeserializer đưa lỗi ra error handling path. Kiểm tra DLT payload/raw bytes và xác nhận chỉ role quarantine được đọc. Không in raw bytes ra console hoặc test report.

### Bước 6: kiểm tra log và retention

Tìm trong application logs, broker logs, DLT, retry topics và test output để chắc chắn không có email/token plaintext. Kiểm tra retention và quy trình xóa dữ liệu ở topic chính, retry, DLT và sink.

## 19. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| DLT chứa Authorization hoặc email header | Recoverer giữ toàn bộ original headers | Dùng allowlist bằng subclass createProducerRecord |
| DLT có stack trace dài | Default recoverer thêm exception stacktrace header | Loại stacktrace header hoặc tạo failureCode an toàn |
| DLT có payload malformed nguyên bản | ErrorHandlingDeserializer giữ raw bytes để recovery | Xem DLT là dữ liệu nhạy cảm; giới hạn ACL/retention và không log raw bytes |
| Broker disk đọc được plaintext | Kafka không mã hóa log segment at rest | Bật filesystem/block encryption hoặc message-level encryption |
| Consumer đọc được field không thuộc nhiệm vụ | ACL chỉ giới hạn topic, không giới hạn field | Tokenize/encrypt field hoặc tách topic theo audience |
| TLS đã bật nhưng dữ liệu vẫn lộ ở broker | TLS kết thúc tại broker | Dùng message-level encryption nếu broker operator nằm ngoài trust boundary |
| JSON type header tiết lộ class name | JsonSerializer thêm type info header | Tắt add.type.headers hoặc dùng token/schema mapping |
| Log có PII trong exception | Exception message/stack trace chứa input | Ghi failure code, sanitize log và hạn chế forensic log |
| Secret xuất hiện trong Git/config | Credential hard-code trong properties | Dùng secret manager/ConfigProvider và rotate credential |
| Record vẫn tồn tại sau retention | Replica, segment deletion, backup, DLT hoặc sink còn bản sao | Kiểm kê toàn bộ data lifecycle và deletion workflow |

## 20. Checklist bảo vệ dữ liệu

- Có data classification cho payload, key, headers, DLT và logs.
- Producer chỉ phát các trường consumer thực sự cần.
- Không đưa password, API key, bearer token, cookie hoặc private key vào record.
- Không dùng PII trực tiếp làm Kafka key, trace ID hoặc correlation ID.
- Tokenization/HMAC/encryption được chọn đúng mục đích.
- AES-GCM dùng nonce duy nhất và key được quản lý ngoài Kafka.
- TLS bảo vệ mọi listener phù hợp; controller listener không public.
- Authentication và authorization được cấu hình riêng.
- ACL theo least privilege cho topic, group và DLT.
- Headers dùng allowlist; không chứa secret hoặc PII.
- Spring JsonSerializer type headers được kiểm soát.
- ErrorHandlingDeserializer raw bytes được xem là payload nhạy cảm.
- DLT không giữ exception message/stacktrace hoặc header nhạy cảm nếu không cần.
- Retry topics và DLT có ACL, encryption, retention và monitoring riêng.
- Application logs không ghi payload, key, headers hoặc exception detail nhạy cảm.
- Backup, snapshots, Connect sinks, Streams state và mirror clusters nằm trong data inventory.
- Có audit cho đọc DLT, giải mã, truy cập KMS và thay đổi ACL.
- Có quy trình retention/deletion và key rotation được kiểm thử.

## 21. Ghi nhớ

| Lớp bảo vệ | Vai trò |
|---|---|
| Data minimization | Không phát dữ liệu không cần |
| Tokenization | Thay PII bằng reference được quản lý |
| HMAC | So khớp ổn định mà không phát plaintext |
| Field-level encryption | Bảo vệ trường nhạy cảm ngay cả khi broker lưu record |
| TLS | Bảo vệ dữ liệu trên đường truyền |
| Filesystem encryption | Bảo vệ disk/volume/backup |
| ACL | Giới hạn principal đọc/ghi resource |
| Header allowlist | Ngăn metadata/secret bị sao chép sang retry và DLT |
| DLT sanitization | Giảm rò rỉ exception, stack trace và raw headers |
| Log redaction | Ngăn payload và secret xuất hiện trong log |
| Retention/deletion | Quản lý thời gian tồn tại của mọi bản sao dữ liệu |

Bảo vệ dữ liệu nhạy cảm trong Kafka là trách nhiệm của toàn bộ pipeline. Hãy giảm dữ liệu ngay từ producer, mã hóa trường cần bảo vệ, dùng TLS và ACL để kiểm soát truy cập, lọc headers, làm sạch DLT và không ghi payload vào log. Đặc biệt, luôn xem retry topic, raw deserialization bytes và bản ghi lỗi là dữ liệu có cùng mức độ nhạy cảm với record gốc.

## 22. Tài liệu tham khảo

- Apache Kafka – [Security Model](https://kafka.apache.org/44/security/security-model/)
- Apache Kafka – [Encryption and Authentication using SSL](https://kafka.apache.org/44/security/encryption-and-authentication-using-ssl/)
- Apache Kafka – [Authentication using SASL](https://kafka.apache.org/44/security/authentication-using-sasl/)
- Apache Kafka – [Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/)
- Spring Kafka – [Handling Exceptions and Dead Letter Topics](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- Spring Kafka 3.3 – [Serialization, Deserialization and ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/docs/3.3.x/reference/kafka/serdes.html)
