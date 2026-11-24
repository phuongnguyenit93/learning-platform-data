# Đăng ký schema, định danh schema và tra cứu khi nhận

Trong hệ thống xử lý sự kiện, producer và consumer cần hiểu cùng cấu trúc dữ liệu. Khi số lượng dịch vụ tăng, việc sao chép schema vào từng repository và tự phối hợp phiên bản dễ dẫn đến sai lệch: producer đã phát trường mới nhưng consumer vẫn dùng cấu trúc cũ, hoặc hai nhóm hiểu khác nhau về cùng một trường. Schema Registry giải quyết phần quản lý tập trung bằng cách lưu schema, cấp định danh và cho phép ứng dụng tra cứu schema khi giải mã message.

Với Spring Cloud Stream, hàm nghiệp vụ vẫn làm việc với object hoặc Message<T>. Serializer và deserializer tích hợp với binder chịu trách nhiệm đăng ký hoặc tra cứu schema ở phía broker/client. Để thiết kế luồng đúng, cần hiểu vòng đời schema: đăng ký trước hoặc tự đăng ký khi ghi, gắn schema ID vào dữ liệu được tuần tự hóa, đọc ID khi nhận và lấy schema tương ứng từ registry.

## 1. Schema Registry làm nhiệm vụ gì?

Schema Registry là dịch vụ quản lý hợp đồng dữ liệu. Nó lưu các schema và phiên bản của chúng, tổ chức schema theo subject, cấp schema ID hoặc định danh tương đương, đồng thời có thể kiểm tra chính sách tương thích trước khi chấp nhận phiên bản mới.

Registry không thay thế broker:

- **Broker** lưu giữ và phân phối message theo topic, queue hoặc subscription.
- **Schema Registry** lưu cấu trúc dữ liệu và metadata của schema.
- **Serializer** biến object thành byte, đồng thời đăng ký hoặc tìm schema và ghi thông tin nhận diện schema theo định dạng wire của hệ sinh thái.
- **Deserializer** đọc byte, nhận diện schema được dùng để ghi, tra cứu schema và khôi phục object.

Một message có thể được lưu trên Kafka trong nhiều ngày, còn schema của nó được quản lý ở registry. Consumer đọc lại message sau khi triển khai phiên bản mới vẫn cần truy cập được schema gốc hoặc một schema reader tương thích.

Registry thường cung cấp API để đăng ký schema, tra cứu theo ID, xem các phiên bản của subject và kiểm tra compatibility. Cách tổ chức subject, phạm vi duy nhất của ID và định dạng wire phụ thuộc sản phẩm registry. Không nên giả định mọi registry đều dùng cùng REST API hoặc cùng cách nhúng ID vào payload.

## 2. Subject, schema version và schema ID

Ba khái niệm này thường bị nhầm lẫn:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Subject | Tên logic dùng để quản lý một dòng schema | orders.created-value |
| Schema version | Thứ tự phiên bản schema trong một subject | Version 3 |
| Schema ID | Định danh schema do registry cấp | ID 42 |

Một subject có thể chứa nhiều phiên bản schema. Một schema giống hệt nhau có thể được tái sử dụng hoặc nhận cùng ID ở nhiều subject tùy quy tắc của registry. Vì vậy, không coi schema ID là số phiên bản của subject. Version 3 không có nghĩa schema ID là 3.

Với Confluent Schema Registry, ID được cấp trong phạm vi registry và có thể được dùng để tra cứu schema; số version được quản lý theo subject. Các sản phẩm registry khác có thể có phạm vi ID hoặc cách định danh khác. Khi chuyển môi trường hoặc registry, không mang một ID từ registry này sang registry khác rồi kỳ vọng nó vẫn chỉ đến cùng schema.

### Subject được đặt tên như thế nào?

Với Kafka và Confluent serializer, chiến lược mặc định thường đặt subject theo tên topic cùng loại dữ liệu:

- Value của topic orders.created dùng subject orders.created-value.
- Key của topic đó dùng subject orders.created-key.

Có thể chọn chiến lược đặt tên theo record hoặc theo topic record nếu muốn quản lý schema theo loại record thay vì theo topic. Lựa chọn này ảnh hưởng đến việc các topic có thể chia sẻ schema và cách áp dụng compatibility. Cần thống nhất chiến lược giữa producer và consumer; đổi chiến lược có thể làm serializer tìm một subject khác và không tìm thấy schema đã đăng ký.

Không phải mọi registry đều dùng khái niệm subject theo cách của Confluent. Hãy kiểm tra quy ước của registry và serializer cụ thể.

## 3. Vòng đời schema từ producer đến consumer

Luồng phổ biến khi producer ghi message bằng serializer có tích hợp Schema Registry:

~~~text
Producer tạo object
       |
       v
Serializer xác định schema
       |
       v
Tìm schema trong registry theo subject
       |
       +---- Chưa có / cần phiên bản mới
       |              |
       |              v
       |       Đăng ký schema và nhận ID
       |
       v
Tuần tự hóa payload và gắn schema ID
       |
       v
Broker lưu message
       |
       v
Consumer nhận byte và đọc schema ID
       |
       v
Deserializer tra cứu schema trong registry
       |
       v
Giải mã payload thành object
~~~

Nếu schema đã đăng ký, serializer có thể lấy ID hiện có thay vì tạo phiên bản mới. Nếu schema chưa có và chế độ tự đăng ký được bật, serializer có thể gửi schema đến registry, nhận ID rồi tiếp tục mã hóa. Nếu tự đăng ký bị tắt, schema phải được đăng ký trước; nếu không, thao tác gửi có thể thất bại.

Ở phía consumer, deserializer đọc ID từ dữ liệu wire, kiểm tra cache cục bộ và chỉ gọi registry khi chưa có schema tương ứng. Nhờ cache, mỗi message không nhất thiết tạo một request tra cứu mới. Tuy vậy, consumer vẫn cần quyền truy cập registry khi gặp schema chưa được cache.

## 4. Đăng ký schema trước khi phát hành

Có hai cách phổ biến để đăng ký schema:

1. **Đăng ký trước (pre-registration):** pipeline CI/CD hoặc nhóm quản trị đăng ký schema và kiểm tra compatibility trước khi producer được triển khai.
2. **Tự đăng ký (auto registration):** serializer đăng ký schema khi producer lần đầu ghi message dùng schema đó.

Đăng ký trước giúp kiểm soát thay đổi và quyền tạo schema. Đây thường là lựa chọn phù hợp cho môi trường production có nhiều nhóm producer. Tự đăng ký thuận tiện khi phát triển cục bộ hoặc thử nghiệm, nhưng nếu nhiều phiên bản ứng dụng tự đăng ký ngoài quy trình kiểm soát, registry có thể nhận schema ngoài dự kiến hoặc từ chối schema do compatibility policy.

### Ví dụ đăng ký bằng API

Với Confluent Schema Registry, một request đăng ký Avro schema vào subject có thể có dạng:

~~~http
POST /subjects/orders.created-value/versions
Content-Type: application/vnd.schemaregistry.v1+json

{
  "schema": "{\"type\":\"record\",\"name\":\"OrderCreated\",\"namespace\":\"com.example.orders\",\"fields\":[{\"name\":\"eventId\",\"type\":\"string\"},{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"totalMinorUnits\",\"type\":\"long\"}]}"
}
~~~

Registry trả về schema ID, ví dụ:

~~~json
{
  "id": 42
}
~~~

Đây là ví dụ theo API của Confluent Schema Registry. Endpoint, media type, xác thực và body có thể khác ở sản phẩm khác. Trong môi trường thật, dùng HTTPS, thông tin xác thực được quản lý an toàn và pipeline có bước kiểm tra compatibility trước khi đăng ký.

### Kiểm tra compatibility trước khi đăng ký

Trước khi thêm schema mới, registry có thể kiểm tra schema đó với các phiên bản trong subject. Các chế độ thường gặp:

- **Backward:** consumer dùng schema mới có thể đọc dữ liệu được ghi bằng schema cũ.
- **Forward:** consumer dùng schema cũ có thể đọc dữ liệu được ghi bằng schema mới.
- **Full:** hỗ trợ cả hai chiều backward và forward.
- **Transitive:** kiểm tra với nhiều phiên bản trước đó, thay vì chỉ phiên bản gần nhất.

Tên và cách cấu hình chính sách phụ thuộc registry. Compatibility ở cấp schema không bảo đảm ý nghĩa nghiệp vụ luôn tương thích. Ví dụ, đổi đơn vị totalMinorUnits từ đồng sang xu mà vẫn giữ kiểu long có thể vượt qua kiểm tra kiểu nhưng làm sai kết quả nghiệp vụ.

## 5. Schema ID được gắn vào message như thế nào?

Schema Registry không bắt buộc mọi serializer phải nhúng ID theo cùng một định dạng. Một cách phổ biến trong hệ sinh thái Confluent là wire format đặt một byte đánh dấu trước schema ID dạng số nguyên 32-bit, sau đó là phần payload đã mã hóa:

~~~text
+----------------+----------------------+----------------------+
| Magic byte     | Schema ID             | Serialized payload   |
| 1 byte         | 4 bytes               | Các byte dữ liệu     |
+----------------+----------------------+----------------------+
~~~

Với định dạng này, consumer có thể đọc schema ID mà không cần biết trước schema cụ thể. Deserializer dùng ID để lấy schema rồi giải mã phần payload còn lại. Ví dụ ID 42 chỉ là định danh tra cứu; nó không chứa schema đầy đủ.

Đây là chi tiết wire format của serializer Confluent, không phải chuẩn chung của Kafka hay Spring Cloud Stream. Không tự cắt năm byte đầu của payload hoặc tự tạo ID nếu không triển khai đúng giao thức serializer. Một registry khác có thể dùng header, envelope hoặc cơ chế metadata khác.

Schema ID thường nằm trong phần mã hóa của value hoặc key. Vì vậy, đừng mặc định rằng nó luôn xuất hiện như một Spring Message header có tên schemaId. Nếu cần quan sát ID, dùng công cụ giải mã hoặc API của serializer/registry theo đúng wire format.

## 6. Consumer tra cứu schema khi nhận

Consumer không cần tải toàn bộ danh mục schema khi khởi động. Với serializer kiểu Confluent, quy trình thường là:

1. Đọc byte message từ broker.
2. Đọc magic byte và schema ID từ phần đầu payload.
3. Tìm schema ID trong cache của deserializer.
4. Nếu chưa có, gọi registry để lấy schema theo ID.
5. Dùng writer schema lấy được và reader schema của ứng dụng (nếu có) để giải mã.
6. Trả về GenericRecord, SpecificRecord hoặc kiểu dữ liệu tương ứng với cấu hình deserializer.

Với Avro, writer schema cho biết dữ liệu được ghi theo cấu trúc nào. Consumer có thể dùng GenericRecord nếu muốn xử lý record động, hoặc SpecificRecord nếu có class được sinh từ schema. Khi reader schema khác writer schema, Avro thực hiện schema resolution theo quy tắc của nó.

Nếu registry không truy cập được và schema chưa nằm trong cache, deserializer có thể không giải mã được message. Vì vậy, registry là một dependency vận hành của consumer, ngay cả khi broker vẫn đang hoạt động bình thường.

## 7. Tích hợp Schema Registry với Spring Cloud Stream và Kafka

Spring Cloud Stream tách hàm nghiệp vụ khỏi client Kafka. Khi dùng serializer/deserializer của Confluent, có thể bật native encoding/decoding để Kafka client xử lý tuần tự hóa. Binder vẫn quản lý binding, destination và consumer group.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder;readOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
        readOrder-in-0:
          destination: orders.created
          group: order-reader
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              use-native-encoding: true
              configuration:
                value.serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
                schema.registry.url: https://schema-registry.example
                auto.register.schemas: false
          readOrder-in-0:
            consumer:
              use-native-decoding: true
              configuration:
                value.deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
                schema.registry.url: https://schema-registry.example
                specific.avro.reader: true
~~~

Ví dụ trên thể hiện ý tưởng cấu hình Kafka binder dùng native serializer/deserializer và registry. Cấu hình chính xác của các thuộc tính serializer phụ thuộc phiên bản Spring Cloud Stream Kafka binder và thư viện Confluent được sử dụng; tên property và vị trí cấu hình cần được xác nhận theo phiên bản binder đang dùng. Hãy kiểm tra tài liệu phiên bản và log client để xác nhận serializer thực sự nhận được các thuộc tính.

Khi native encoding được bật, producer cần dùng serializer tương ứng, ví dụ KafkaAvroSerializer; consumer cần dùng KafkaAvroDeserializer. Với SpecificRecord, cấu hình specific.avro.reader cho deserializer và bảo đảm class được sinh từ schema có trên classpath. Nếu dùng GenericRecord, bỏ tùy chọn specific reader và xử lý kiểu record động.

Dependency của serializer Confluent không nằm trong starter Kafka binder mặc định. Cần thêm artifact serializer tương thích với Kafka client và phiên bản Java của ứng dụng. Đồng thời cấu hình URL registry, TLS hoặc thông tin xác thực theo môi trường.

Ví dụ Java function có thể dùng kiểu Avro được sinh tự động:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.example.orders.OrderCreated;

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderCreated> readOrder() {
        return event -> System.out.printf(
                "Received order %s, total=%d%n",
                event.getOrderId(),
                event.getTotalMinorUnits());
    }
}
~~~

Tên getter trong class sinh từ Avro phụ thuộc schema và cấu hình code generation. Ví dụ minh họa cách consumer nhận object đã được deserializer tạo ra; serializer/deserializer và registry phải được cấu hình đúng trước khi message đến hàm.

## 8. Đăng ký tự động hay quản lý schema qua CI/CD?

Trong môi trường phát triển, auto.register.schemas giúp thử nghiệm nhanh. Khi producer gặp schema mới trong subject, serializer có thể đăng ký và nhận ID. Trong production, nhiều nhóm chọn pre-registration:

- Pipeline kiểm tra schema mới với chính sách compatibility.
- Người hoặc quy trình có quyền phù hợp đăng ký schema.
- Pipeline lưu schema ID hoặc version trong log triển khai để truy vết.
- Producer triển khai với auto registration tắt và chỉ dùng schema đã được phê duyệt.

Không nên nhúng một schema ID cố định vào mã ứng dụng như một hằng số nếu serializer có thể tra cứu theo schema. ID thuộc registry và subject context; quy trình triển khai phải bảo đảm đúng registry và schema đã đăng ký. Khi môi trường dev, staging và production có registry riêng, ID có thể khác nhau dù nội dung schema giống nhau.

## 9. Cache, hiệu năng và khả năng sẵn sàng

Tra cứu registry qua mạng cho từng message sẽ tăng độ trễ và tạo tải không cần thiết. Serializer/deserializer thường cache schema theo subject hoặc ID. Khi gặp schema đã biết, ứng dụng có thể tuần tự hóa hoặc giải mã mà không gọi registry lại.

Khi vận hành, cần chú ý:

- **Cache miss:** lần đầu gặp schema ID mới có thể phát sinh request đến registry.
- **Registry outage:** producer không thể đăng ký schema mới; consumer không thể lấy schema chưa cache.
- **Cache và rollout:** consumer mới có thể gặp schema ID mà phiên bản cũ chưa từng thấy.
- **Timeout và retry:** cấu hình timeout, retry và circuit breaker theo thư viện client, tránh để registry chậm làm nghẽn toàn bộ luồng xử lý.
- **Dung lượng cache:** số lượng schema và subject lớn có thể ảnh hưởng bộ nhớ; kiểm tra giới hạn cache của client.
- **Tính sẵn sàng:** triển khai registry có HA, giám sát lỗi API và theo dõi độ trễ tra cứu.

Cache giúp giảm phụ thuộc vào registry cho schema đã biết, nhưng không thay thế kế hoạch khôi phục. Một consumer mới đọc lại dữ liệu lịch sử có thể gặp schema rất cũ chưa từng nằm trong cache của tiến trình hiện tại. Registry phải giữ schema tương ứng trong suốt thời gian dữ liệu còn có thể được đọc.

## 10. Bảo mật và quản trị quyền truy cập

Registry chứa hợp đồng và metadata quan trọng của hệ thống. Không phải mọi ứng dụng đều cần quyền đăng ký schema:

- Producer dùng schema đã pre-register thường chỉ cần quyền đọc schema; producer bật auto registration cần quyền đăng ký schema trong subject được chỉ định.
- Consumer thường chỉ cần quyền đọc schema.
- Pipeline CI/CD hoặc nhóm quản trị có quyền đăng ký, kiểm tra compatibility và quản lý subject.
- Dùng TLS để bảo vệ kết nối và cơ chế xác thực của registry.
- Lưu credential trong secret manager hoặc cơ chế cấu hình an toàn; không commit token vào repository.
- Giới hạn quyền theo subject hoặc namespace nếu registry hỗ trợ.

Không ghi credential hoặc nội dung dữ liệu nhạy cảm vào log khi debug lỗi đăng ký/tra cứu. Log schema ID, subject, version và mã lỗi thường đủ để điều tra mà không cần in toàn bộ payload.

## 11. Xử lý lỗi đăng ký và tra cứu

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Producer không đăng ký được schema | URL, TLS, credential hoặc quyền ghi sai | Kiểm tra kết nối registry, quyền subject và log serializer |
| Schema bị từ chối | Vi phạm compatibility policy | So sánh schema mới với phiên bản trước và kiểm tra policy |
| Consumer không tìm thấy schema ID | ID thuộc registry khác, schema bị xóa hoặc sai wire format | Kiểm tra registry context, ID và serializer |
| Consumer không giải mã được payload | Sai schema, sai serializer hoặc dữ liệu bị hỏng | Xác nhận schema ID, loại dữ liệu và cấu hình deserializer |
| Consumer mới đọc dữ liệu cũ thất bại | Reader schema không tương thích hoặc registry không còn schema cũ | Kiểm tra writer/reader schema và thời hạn lưu giữ |
| Chỉ lỗi ở một môi trường | Registry URL, subject strategy hoặc ID khác nhau | So sánh cấu hình và subject thực tế giữa môi trường |

Không khắc phục lỗi bằng cách xóa subject hoặc đăng ký lại schema tùy tiện. Schema ID đã được ghi vào message lịch sử có thể vẫn cần thiết để consumer đọc dữ liệu đó. Xóa schema đang được tham chiếu có thể làm hỏng khả năng giải mã dữ liệu cũ.

## 12. Kiểm thử quy trình register và lookup

Kiểm thử cần xác nhận cả schema lẫn luồng dữ liệu:

1. **Schema registration test:** đăng ký schema mới và xác nhận registry trả về ID hợp lệ.
2. **Compatibility test:** thử đăng ký thay đổi có chủ đích và xác nhận registry chấp nhận hoặc từ chối đúng chính sách.
3. **Serialization test:** producer mã hóa object và message có thể được giải mã bằng schema tương ứng.
4. **Lookup test:** consumer đọc message có schema ID chưa nằm trong cache, tra cứu registry và khôi phục đúng object.
5. **Cross-version test:** producer cũ và mới trao đổi với consumer cũ và mới theo ma trận tương thích đã chọn.
6. **Failure test:** mô phỏng registry không truy cập được, credential sai hoặc schema ID không tồn tại để xác nhận lỗi được quan sát và xử lý đúng.
7. **Broker integration test:** chạy với Kafka binder và registry thật hoặc môi trường container tương đương để xác nhận native serializer/deserializer.

Test binder của Spring Cloud Stream hữu ích để kiểm tra logic hàm và binding, nhưng nó không thay thế kiểm thử Schema Registry. Nếu ứng dụng dựa vào ID nhúng trong payload, serializer cụ thể và cache của deserializer, cần kiểm thử bằng đúng thư viện và wire format đó.

## 13. Checklist trước khi đưa schema vào production

- Subject naming strategy đã thống nhất giữa producer và consumer.
- Schema mới đã được kiểm tra compatibility với các phiên bản cần hỗ trợ.
- Schema được đăng ký trước hoặc auto registration được bật có chủ đích.
- Producer dùng đúng serializer và registry của môi trường.
- Consumer dùng đúng deserializer, reader schema và kiểu record.
- Schema ID được đọc từ wire format của serializer; không tự tạo hoặc tự sửa ID.
- Registry giữ schema cũ trong suốt thời gian message lịch sử còn được tiêu thụ.
- Cache, timeout, retry, TLS, authentication và quyền subject đã được cấu hình.
- Log và metric có subject, schema ID, lỗi đăng ký/tra cứu và độ trễ registry.
- Có kiểm thử producer-consumer lệch phiên bản và kiểm thử khi registry gián đoạn.

Schema Registry giúp các nhóm chia sẻ hợp đồng dữ liệu có kiểm soát. Producer đăng ký hoặc tìm schema rồi gắn định danh vào dữ liệu tuần tự hóa; consumer đọc định danh, tra cứu schema và giải mã payload. Khi hiểu rõ subject, version, ID và trách nhiệm của serializer/deserializer, ta có thể triển khai Spring Cloud Stream với schema evolution an toàn, truy vết được và hỗ trợ nhiều phiên bản producer-consumer cùng tồn tại.
