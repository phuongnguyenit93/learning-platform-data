# Cấu hình serializer với native encoding

## Mục tiêu

Spring Cloud Stream cho phép ứng dụng gửi payload Java qua output binding mà không phải tự thao tác với Kafka Producer API. Ở chế độ chuyển đổi thông thường, framework dùng message converter và content type để biến payload thành dạng truyền tin. Khi cần kiểm soát wire format bằng Kafka client, producer binding có thể bật **native encoding** để giao việc mã hóa cho Kafka Serializer được cấu hình.

Native encoding hữu ích khi producer cần dùng JSON serializer, Avro/Protobuf serializer, schema registry hoặc một định dạng tương thích với các hệ thống không viết bằng Java. Điều quan trọng là phải cấu hình đúng serializer cho key và value, hiểu ranh giới giữa message conversion và serialization, và kiểm thử bytes thực tế được ghi vào topic.

Sau bài học, bạn có thể:

- Giải thích native encoding của Kafka binder.
- Bật use-native-encoding trên output binding.
- Cấu hình Kafka key serializer và value serializer riêng biệt.
- Chọn serializer phù hợp cho String, JSON, byte array hoặc schema-based format.
- Hiểu tác động của type headers và content type.
- Kiểm thử wire format và khả năng đọc từ consumer khác ngôn ngữ.
- Tránh cấu hình serializer không tương thích với dữ liệu producer gửi.

## 1. Message conversion và native serialization

Trong chế độ thông thường, Spring Cloud Stream nhận payload Java, sau đó sử dụng message converter dựa trên content type để chuyển đổi payload trước khi binder gửi dữ liệu. Ví dụ, POJO có thể được chuyển thành JSON bytes khi binding dùng application/json.

Khi bật native encoding, Kafka binder sử dụng serializer của Kafka client để mã hóa key/value. Đường chuyển đổi payload mặc định của Spring Cloud Stream được bỏ qua cho phần encoding tương ứng; kiểu payload gửi vào phải tương thích với serializer đã cấu hình.

Luồng xử lý khái quát:

    Java object / Spring Message
        -> Native encoding được bật?
            -> Không: Spring Cloud Stream MessageConverter
            -> Có: Kafka key/value Serializer
        -> Kafka binder / Producer
        -> Kafka record bytes
        -> Kafka topic

Hai cách có thể tóm tắt:

| Chế độ | Thành phần mã hóa payload | Cách chọn định dạng |
|---|---|---|
| Framework conversion | Spring MessageConverter | Content type và kiểu payload |
| Native encoding | Kafka client Serializer | key.serializer và value.serializer |

Native encoding không làm biến mất mọi chức năng của Spring Messaging. Ứng dụng vẫn có thể tạo Message, gắn application headers và gửi qua binding. Thay đổi chính là serializer của Kafka client chịu trách nhiệm mã hóa key/value theo cấu hình native.

## 2. Bật native encoding trên output binding

Thuộc tính use-native-encoding được đặt ở producer của binding đầu ra:

    spring:
      cloud:
        function:
          definition: paymentEvents
        stream:
          bindings:
            paymentEvents-out-0:
              destination: payments.captured
              producer:
                use-native-encoding: true

Trong ví dụ:

- paymentEvents-out-0 là output binding của function paymentEvents.
- payments.captured là Kafka topic đích.
- use-native-encoding: true yêu cầu Kafka binder dùng native serializer cho dữ liệu producer.
- Serializer thực tế được cấu hình trong namespace Kafka binder.

Bật native encoding mà không cấu hình serializer phù hợp có thể khiến ứng dụng không khởi động hoặc gửi message thất bại. Hãy cấu hình serializer cùng lúc và xác minh kiểu payload mà function thực sự trả về.

### Cấu hình serializer theo binding

Kafka binder cho phép đặt client properties riêng cho producer binding:

    spring:
      cloud:
        function:
          definition: paymentEvents
        stream:
          bindings:
            paymentEvents-out-0:
              destination: payments.captured
              producer:
                use-native-encoding: true
          kafka:
            bindings:
              paymentEvents-out-0:
                producer:
                  configuration:
                    key.serializer: org.apache.kafka.common.serialization.StringSerializer
                    value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
                    spring.json.add.type.headers: false

Cấu hình này dùng:

- StringSerializer cho record key.
- Spring Kafka JsonSerializer cho record value.
- spring.json.add.type.headers: false để không thêm type information header riêng của Spring Kafka vào record; hữu ích khi wire format JSON cần được tiêu thụ bởi client không dùng Spring Kafka.

Tên property và class phải tương thích với phiên bản Kafka client/Spring Kafka trong ứng dụng. Nếu dùng serializer của Confluent, Apicurio hoặc thư viện schema khác, thay class serializer và cung cấp các cấu hình schema registry tương ứng.

## 3. Serializer cho key và value là hai cấu hình riêng

Một Kafka record có thể chứa key và value. Kafka client mã hóa hai phần này độc lập, vì vậy có thể dùng hai serializer khác nhau.

| Phần record | Kiểu ứng dụng | Serializer thường gặp |
|---|---|---|
| Key | String, ví dụ order-42 | StringSerializer |
| Value | POJO sự kiện | Spring Kafka JsonSerializer |
| Key | UUID hoặc kiểu tùy chỉnh | Serializer phù hợp với wire format đã thống nhất |
| Value | byte[] | ByteArraySerializer |
| Value | Avro/Protobuf | Serializer tích hợp schema/registry tương ứng |

Ví dụ một sự kiện:

    public record PaymentCaptured(
            String eventId,
            String orderId,
            long amountMinor,
            String currency
    ) {}

Function tạo payload:

    @Bean
    Supplier<PaymentCaptured> paymentEvents(PaymentEventSource source) {
        return source::next;
    }

Với JsonSerializer, value là đối tượng Java và serializer chuyển nó thành JSON bytes. Nếu cấu hình ByteArraySerializer, payload gửi vào phải là byte[]; serializer này không tự chuyển POJO thành JSON.

### Đặt Kafka record key

Key có thể được đặt qua Kafka message header được Kafka binder/Spring Kafka hỗ trợ. Ví dụ với Spring Kafka:

    import org.springframework.kafka.support.KafkaHeaders;
    import org.springframework.messaging.Message;
    import org.springframework.messaging.support.MessageBuilder;

    Message<PaymentCaptured> message = MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.KEY, event.orderId())
            .build();

    streamBridge.send("paymentEvents-out-0", message);

KafkaHeaders.KEY là metadata để xác định record key; nó không phải một phần của JSON value. Serializer của key phải chấp nhận kiểu giá trị được đặt trong header. Trong ví dụ, key là String nên dùng StringSerializer.

Nếu ứng dụng không cần key, cần cấu hình và kiểm tra hành vi key null theo yêu cầu partitioning. Không cấu hình một serializer đòi kiểu UUID rồi gửi String key, hoặc ngược lại.

## 4. Các lựa chọn serializer phổ biến

### StringSerializer

Dùng khi key hoặc value là chuỗi:

    value.serializer: org.apache.kafka.common.serialization.StringSerializer

Payload cần là String. Nếu ứng dụng gửi POJO, StringSerializer không tự gọi Jackson để biến POJO thành JSON. Hãy chuyển thành chuỗi một cách tường minh hoặc chọn serializer phù hợp.

### ByteArraySerializer

Dùng khi ứng dụng đã tạo bytes theo wire format:

    value.serializer: org.apache.kafka.common.serialization.ByteArraySerializer

Cách này phù hợp khi một thư viện khác đã encode JSON, Avro hoặc Protobuf thành byte array. Cần bảo đảm encoding, schema và version được thống nhất giữa producer và consumer.

### Spring Kafka JsonSerializer

Dùng khi payload là POJO và muốn Spring Kafka/Jackson tạo JSON bytes:

    value.serializer: org.springframework.kafka.support.serializer.JsonSerializer

JsonSerializer xử lý đối tượng Java thành JSON. Cấu hình type headers là một quyết định tương thích:

- Type headers của Spring Kafka có thể giúp Spring Kafka JsonDeserializer xác định lớp đích.
- Consumer Python, Go hoặc Java không dùng Spring Kafka có thể bỏ qua Kafka headers và parse JSON value theo schema riêng.
- Nếu consumer không dựa vào type headers, có thể tắt chúng và khai báo kiểu đích/schema ở phía nhận.
- Không dùng type header do producer gửi như bằng chứng tin cậy để quyết định lớp được phép deserialize.

Với hệ thống đa ngôn ngữ, JSON contract nên được định nghĩa độc lập với tên class Java. Không để consumer phải biết package hoặc class name của producer.

### Avro, Protobuf và schema registry

Với Avro hoặc Protobuf, serializer thường tích hợp schema registry để lưu schema/version và mã hóa record theo wire format của hệ sinh thái đó. Cấu hình thường cần:

- Serializer class đúng với nền tảng schema.
- URL và credential của schema registry.
- Subject naming strategy hoặc quy tắc đăng ký schema.
- Chính sách compatibility.
- Schema/record type mà producer gửi.

Ví dụ dưới đây chỉ minh họa vị trí khai báo; tên property cụ thể phụ thuộc serializer/registry:

    spring:
      cloud:
        stream:
          kafka:
            bindings:
              paymentEvents-out-0:
                producer:
                  configuration:
                    value.serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
                    schema.registry.url: https://schema-registry.example

Không dùng tên class hoặc property trong ví dụ nếu dependency tương ứng chưa có trong ứng dụng. Schema registry không tự động được kích hoạt chỉ bằng cách bật native encoding.

## 5. Native encoding và content type

content-type trong Spring Cloud Stream mô tả định dạng payload ở abstraction của framework và hỗ trợ lựa chọn message converter. Khi bật native encoding, Kafka serializer là thành phần quyết định bytes của key/value.

Ví dụ:

    spring:
      cloud:
        stream:
          bindings:
            paymentEvents-out-0:
              content-type: application/json
              producer:
                use-native-encoding: true

Khi native encoding được bật, không nên dựa vào content-type để thay thế value.serializer. Nếu serializer là Avro nhưng content type lại khai báo JSON, cấu hình sẽ gây hiểu nhầm cho người đọc và có thể làm consumer chọn sai cơ chế giải mã.

Hãy thống nhất ba yếu tố:

1. Kiểu Java mà function tạo ra.
2. Serializer thực sự dùng để tạo Kafka record bytes.
3. Wire format/schema mà consumer dự kiến đọc.

Content type có thể vẫn xuất hiện trong Spring Message hoặc metadata tùy cấu hình, nhưng không biến một serializer thành serializer khác. Nếu cần consumer dùng Spring MessageConverter, hãy xác định rõ binding consumer đang dùng native decoding hay framework conversion.

## 6. Native encoding khác native decoding

Native encoding là quyết định của **producer binding**. Native decoding là quyết định riêng của **consumer binding**.

| Thuộc tính | Vị trí | Chức năng |
|---|---|---|
| use-native-encoding | bindings.<name>.producer | Dùng Kafka serializer để mã hóa record khi gửi |
| use-native-decoding | bindings.<name>.consumer | Dùng Kafka deserializer để giải mã record khi nhận |

Ví dụ consumer dùng native decoding:

    spring:
      cloud:
        stream:
          bindings:
            paymentEvents-in-0:
              destination: payments.captured
              group: billing-service
              consumer:
                use-native-decoding: true
          kafka:
            bindings:
              paymentEvents-in-0:
                consumer:
                  configuration:
                    value.deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
                    spring.json.value.default.type: com.example.events.PaymentCaptured
                    spring.json.trusted.packages: com.example.events

Đây là cấu hình phía consumer để minh họa tính độc lập của hai phía. Consumer có thể dùng native decoding trong khi một producer khác dùng framework conversion, miễn là wire format cuối cùng tương thích. Ngược lại, producer dùng native encoding không bắt buộc mọi consumer đều phải dùng native decoding; consumer có thể dùng đường conversion nếu cấu hình binder và payload cho phép.

Khi dùng Spring Kafka JsonDeserializer, kiểm tra type mapping và trusted packages theo chính sách bảo mật. Chỉ tin cậy package cần thiết; không mở rộng phạm vi tùy tiện khi nhận dữ liệu từ producer không đáng tin cậy.

## 7. Ví dụ hoàn chỉnh: Spring Cloud Stream phát JSON cho consumer đa ngôn ngữ

Giả sử dịch vụ thanh toán phát sự kiện để các consumer Java và Python cùng đọc. Contract JSON được định nghĩa độc lập với class Java:

    {
      "eventId": "evt-901",
      "eventType": "payment.captured",
      "orderId": "order-42",
      "amountMinor": 12550,
      "currency": "VND"
    }

Producer Java:

    public record PaymentCaptured(
            String eventId,
            String eventType,
            String orderId,
            long amountMinor,
            String currency
    ) {}

    @Bean
    Supplier<PaymentCaptured> paymentEvents(PaymentEventSource source) {
        return source::next;
    }

Cấu hình:

    spring:
      cloud:
        function:
          definition: paymentEvents
        stream:
          bindings:
            paymentEvents-out-0:
              destination: payments.captured
              producer:
                use-native-encoding: true
          kafka:
            bindings:
              paymentEvents-out-0:
                producer:
                  configuration:
                    key.serializer: org.apache.kafka.common.serialization.StringSerializer
                    value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
                    spring.json.add.type.headers: false

Với cấu hình này, Kafka JsonSerializer tạo JSON bytes từ đối tượng PaymentCaptured. Python consumer có thể đọc value bytes rồi parse JSON mà không cần biết class Java:

    import json

    def decode_payment(value: bytes) -> dict:
        event = json.loads(value.decode("utf-8"))
        required = {
            "eventId",
            "eventType",
            "orderId",
            "amountMinor",
            "currency",
        }
        missing = required - event.keys()
        if missing:
            raise ValueError(f"Missing fields: {sorted(missing)}")
        return event

Ví dụ Python chỉ minh họa bước decode và kiểm tra trường bắt buộc; consumer production còn cần quản lý poll, offset commit, retry và idempotency theo client đang sử dụng.

Điểm quan trọng là cả hai phía thống nhất JSON schema, tên trường, kiểu dữ liệu và semantics. Tắt Spring type headers giúp tránh đưa tên class Java vào yêu cầu tương thích của consumer đa ngôn ngữ; nó không thay thế việc validate schema.

## 8. Cấu hình theo binding hay toàn binder?

Khi nhiều output binding dùng serializer khác nhau, cấu hình riêng theo binding giúp giới hạn tác động:

    spring:
      cloud:
        stream:
          bindings:
            paymentEvents-out-0:
              destination: payments.captured
              producer:
                use-native-encoding: true
            auditEvents-out-0:
              destination: audit.events
              producer:
                use-native-encoding: true
          kafka:
            bindings:
              paymentEvents-out-0:
                producer:
                  configuration:
                    value.serializer: org.springframework.kafka.support.serializer.JsonSerializer
              auditEvents-out-0:
                producer:
                  configuration:
                    value.serializer: org.apache.kafka.common.serialization.StringSerializer

Trong ví dụ, binding thanh toán gửi POJO JSON còn binding audit gửi String. Code producer phải gửi đúng kiểu tương ứng. Nếu tất cả binding đều dùng chung serializer, có thể cân nhắc cấu hình ở cấp binder/client theo khả năng của phiên bản; tuy nhiên, cấu hình per-binding thường dễ kiểm soát hơn khi các wire contract khác nhau.

Không đặt serializer class trong domain code. Hãy giữ lựa chọn serializer ở cấu hình adapter/binder để thay đổi wire format không buộc domain service phụ thuộc Kafka client.

## 9. Lỗi thường gặp khi bật native encoding

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Producer lỗi khi gửi POJO | Đang dùng StringSerializer hoặc ByteArraySerializer không nhận POJO | Chọn JsonSerializer hoặc encode thành đúng kiểu trước khi gửi |
| Consumer không đọc được record | Serializer và deserializer không cùng wire format | Đồng bộ hai phía và kiểm tra bytes thực tế |
| Python đọc JSON nhưng Java consumer lỗi type | Consumer phụ thuộc type headers hoặc DTO mapping khác | Dùng contract/schema rõ ràng và cấu hình kiểu đích ở consumer |
| Record key lỗi trong khi value đúng | Key serializer không tương thích với key header | Kiểm tra riêng key type và key.serializer |
| Content type là JSON nhưng bytes không phải JSON | Native serializer tạo định dạng khác | Xác minh serializer và wire format, không chỉ đọc content type |
| Avro consumer không tìm được schema | Registry URL, subject hoặc credentials sai | Kiểm tra serializer, registry và schema compatibility |
| Ứng dụng không khởi động | Serializer class không có trong classpath hoặc cấu hình sai | Kiểm tra dependency và property theo binder version |
| Type header gây phụ thuộc class producer | Spring Kafka JsonSerializer thêm type information | Tắt type headers nếu contract không dùng chúng và kiểm tra consumer |

Một lỗi serialization thường không thể khắc phục bằng cách retry message vô hạn. Nếu payload có kiểu không tương thích serializer, cần sửa code hoặc cấu hình; retry chỉ lặp lại cùng lỗi.

## 10. Kiểm thử serializer và wire format

Kiểm thử cần chứng minh serializer thực sự tạo bytes đúng contract, không chỉ chứng minh Spring application context khởi động.

### Unit test cho serializer

Có thể kiểm tra serializer trực tiếp:

    @Test
    void shouldSerializePaymentAsJson() {
        JsonSerializer<PaymentCaptured> serializer =
                new JsonSerializer<PaymentCaptured>().noTypeInfo();

        PaymentCaptured event = new PaymentCaptured(
                "evt-901",
                "payment.captured",
                "order-42",
                12550L,
                "VND"
        );

        byte[] bytes = serializer.serialize("payments.captured", event);
        String json = new String(bytes, StandardCharsets.UTF_8);

        assertTrue(json.contains("\"eventId\":\"evt-901\""));
        assertTrue(json.contains("\"amountMinor\":12550"));
    }

Test này xác minh serializer JSON tạo nội dung mong đợi. Trong ứng dụng production, nên dùng cùng serializer class/configuration với Kafka binder để tránh test một cấu hình khác cấu hình runtime.

### Integration test với Kafka

Dùng Kafka Testcontainers hoặc broker test để kiểm tra:

- Output binding bật native encoding.
- Key serializer và value serializer được khởi tạo đúng.
- Record key và value bytes đúng wire format.
- Custom application headers được truyền theo cấu hình binder.
- Consumer khác ngôn ngữ hoặc consumer dùng deserializer tương ứng đọc được record.
- Serializer lỗi được báo đúng và không bị hiểu nhầm thành broker delivery failure.
- Thay đổi schema/DTO vẫn đáp ứng compatibility policy.

Test Binder hữu ích cho wiring và function behavior, nhưng không thay thế Kafka broker integration test khi cần xác minh Kafka client serializer và record bytes thực tế.

## 11. Quy trình cấu hình trong production

Khi bật native encoding cho một output binding:

1. Xác định payload Java mà function hoặc StreamBridge gửi.
2. Chốt wire format: String, JSON, byte array, Avro, Protobuf hoặc định dạng khác.
3. Chọn serializer cho value; chọn riêng serializer cho key nếu có key.
4. Bật use-native-encoding trên đúng output binding.
5. Đặt client serializer properties trong namespace Kafka binder đúng binding.
6. Nếu dùng schema registry, cấu hình endpoint, credential, subject strategy và compatibility.
7. Quyết định có dùng Spring Kafka type headers hay không; với consumer đa ngôn ngữ, ưu tiên contract độc lập với class name.
8. Đồng bộ deserializer/schema ở các consumer.
9. Kiểm tra record bytes bằng integration test trên Kafka.
10. Theo dõi serialization error, producer error rate và schema registry failures sau triển khai.

Credential của schema registry phải được quản lý bằng secret store hoặc biến môi trường an toàn; không commit mật khẩu vào YAML. Serializer và schema là một phần của hợp đồng tích hợp, nên mọi thay đổi wire format cần được version hóa và kiểm thử tương thích.

## Kết luận

Native encoding cho phép Kafka binder dùng Kafka client Serializer để mã hóa key và value thay cho message conversion mặc định của Spring Cloud Stream. Bật use-native-encoding ở producer binding, sau đó cấu hình đúng key.serializer và value.serializer theo kiểu dữ liệu và wire contract.

Với JSON, Spring Kafka JsonSerializer có thể chuyển POJO thành JSON bytes; với String, byte array, Avro hoặc Protobuf, chọn serializer tương ứng. Content type không thay thế serializer khi native encoding được bật, và native encoding độc lập với native decoding ở consumer. Hãy kiểm tra key/value riêng, kiểm soát type headers và xác minh bytes thực tế trên Kafka để bảo đảm các consumer Java hoặc đa ngôn ngữ đọc được cùng hợp đồng.

