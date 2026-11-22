# Tương thích ngược khi thêm, bỏ hoặc đổi kiểu trường

## Mục tiêu

Sau bài này, bạn có thể đánh giá một thay đổi trong message contract có làm hỏng producer hoặc consumer cũ hay không; phân biệt backward, forward và full compatibility; áp dụng quy tắc phù hợp với JSON/Jackson trong Spring; và triển khai thay đổi theo từng bước để nhiều phiên bản ứng dụng cùng hoạt động trong thời gian nâng cấp.

## 1. Message contract là gì?

Message contract là thỏa thuận về cấu trúc và ý nghĩa của thông điệp giữa bên gửi (producer) và bên nhận (consumer). Contract thường mô tả:

- Tên event hoặc message type.
- Các trường, kiểu dữ liệu, ý nghĩa và đơn vị của từng trường.
- Trường bắt buộc, tùy chọn, giá trị mặc định và quy tắc null.
- Quy tắc mã hóa, ví dụ JSON, Protocol Buffers hoặc Avro.
- Phiên bản schema và cách xử lý dữ liệu được tạo bởi phiên bản cũ.

Trong Spring Messaging, ứng dụng làm việc với `Message<?>`, gồm payload và headers. Một `MessageConverter` chuyển payload giữa dạng đã serialize và kiểu Java; header `MessageHeaders.CONTENT_TYPE` có thể cho converter biết định dạng nội dung. Ví dụ, cùng một JSON payload có thể được chuyển thành DTO Java thông qua converter Jackson. Xem [Spring MessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0-M6/javadoc-api/org/springframework/messaging/converter/MessageConverter.html).

Đừng đồng nhất message contract với class Java. Producer và consumer có thể được triển khai bằng ngôn ngữ, framework và phiên bản khác nhau. Class Java chỉ là một biểu diễn của contract ở một phía. Khi class thay đổi, điều cần đánh giá là payload trên đường truyền và cách mọi consumer diễn giải payload đó.

Một thay đổi có thể tương thích về cú pháp nhưng vẫn phá vỡ nghiệp vụ. Ví dụ, đổi `amount` từ đơn vị đồng sang đơn vị xu nhưng vẫn giữ kiểu `long` có thể deserialize thành công, song consumer cũ sẽ tính sai giá trị. Vì vậy, cần kiểm tra cả khả năng deserialize lẫn ý nghĩa dữ liệu.

## 2. Ba hướng tương thích

Giả sử phiên bản contract cũ là V1 và phiên bản mới là V2.

| Loại tương thích | Câu hỏi cần trả lời | Hướng kiểm tra |
|---|---|---|
| Backward compatibility | Consumer mới có đọc được message do producer cũ tạo ra không? | V2 reader đọc V1 data |
| Forward compatibility | Consumer cũ có đọc được message do producer mới tạo ra không? | V1 reader đọc V2 data |
| Full compatibility | Cả consumer cũ và mới có đọc được dữ liệu của producer cũ và mới không? | Kiểm tra cả hai hướng |

Một số schema registry còn có chế độ **transitive**. Thay vì chỉ so sánh schema mới với phiên bản liền trước, registry kiểm tra với tất cả các phiên bản trước đó. Điều này quan trọng khi message cũ còn được lưu trong hàng đợi, topic, data lake hoặc event store và có thể được phát lại sau nhiều lần nâng cấp.

Không có một quy tắc “thêm trường luôn an toàn” áp dụng cho mọi serializer. Kết quả phụ thuộc định dạng dữ liệu, schema, converter, cấu hình consumer và thứ tự triển khai producer/consumer.

## 3. Thêm trường mới

Thêm trường thường là thay đổi dễ kiểm soát nhất, nhưng cần xét cả hai phía.

Giả sử V1 gửi:

~~~json
{
  "paymentId": "pay-1042",
  "amount": 125000
}
~~~

V2 bổ sung trường `currency`:

~~~json
{
  "paymentId": "pay-1042",
  "amount": 125000,
  "currency": "VND"
}
~~~

### Consumer mới đọc message cũ

Consumer V2 nhận payload V1 sẽ không tìm thấy `currency`. Nếu trường mới không bắt buộc, consumer có thể dùng giá trị mặc định đã được xác định theo nghiệp vụ.

Ví dụ DTO Java 17:

~~~java
import java.math.BigDecimal;

public record PaymentAuthorized(
    String paymentId,
    BigDecimal amount,
    String currency
) {
    public String effectiveCurrency() {
        // Chỉ hợp lệ nếu contract cũ bảo đảm mọi amount đều là VND.
        return currency == null ? "VND" : currency;
    }
}
~~~

Ở đây, `currency` là kiểu tham chiếu nên có thể nhận `null` khi payload cũ không có thuộc tính. Giá trị mặc định phải xuất phát từ quy tắc nghiệp vụ đã được xác nhận. Nếu message cũ có thể chứa nhiều loại tiền tệ, không được tự gán VND; hãy giữ trạng thái thiếu dữ liệu, tra cứu nguồn phù hợp hoặc từ chối message theo chính sách rõ ràng.

Nếu trường mới thật sự bắt buộc, không nên thêm nó như một yêu cầu bắt buộc ngay lập tức. Hãy triển khai theo giai đoạn: consumer có khả năng xử lý cả message cũ và mới trước, sau đó mới để producer gửi trường mới, rồi chỉ siết validation khi mọi producer đã được nâng cấp.

### Consumer cũ đọc message mới

Consumer V1 không biết `currency`. Với JSON, khả năng đọc được phụ thuộc cách xử lý thuộc tính lạ.

Trong Spring Framework 6.2, `MappingJackson2MessageConverter` dùng Jackson 2 và mặc định tắt `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES`. Vì vậy converter này có thể bỏ qua trường JSON mới mà DTO cũ không khai báo. Nếu ứng dụng thay converter hoặc truyền một `ObjectMapper` được cấu hình riêng, hãy kiểm tra hành vi thực tế thay vì dựa vào mặc định. Xem [MappingJackson2MessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html).

Ví dụ cấu hình rõ ràng với Spring Messaging 6.2 và Jackson 2:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;

ObjectMapper objectMapper = new ObjectMapper()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

MappingJackson2MessageConverter converter =
    new MappingJackson2MessageConverter(objectMapper);
~~~

Đây là mảnh cấu hình converter, không phải ứng dụng độc lập. Trong hệ thống thực tế, hãy dùng converter đã được đăng ký trong messaging endpoint hoặc broker adapter. Spring Framework 7 có các API converter dựa trên Jackson 3; tên class và package có thể khác. Kiểm tra Javadoc đúng phiên bản mà dự án đang dùng.

**Kết luận khi thêm trường:** trường mới nên được consumer mới xem là tùy chọn trong giai đoạn chuyển tiếp; consumer cũ cần bỏ qua thuộc tính chưa biết nếu muốn tương thích theo hướng forward. Nếu một consumer cũ có validation riêng hoặc dùng schema đóng, việc thêm trường vẫn có thể làm message bị từ chối.

## 4. Phân biệt trường bị thiếu, null và giá trị mặc định

Ba trạng thái sau không giống nhau:

~~~json
{}
~~~

~~~json
{ "discount": null }
~~~

~~~json
{ "discount": 0 }
~~~

- **Thiếu thuộc tính:** producer không gửi trường đó.
- **Null:** producer gửi trường nhưng khẳng định hiện không có giá trị.
- **Giá trị mặc định:** producer gửi một giá trị cụ thể, ví dụ `0`, `false` hoặc chuỗi rỗng.

Với kiểu Java nguyên thủy như `int` hoặc `boolean`, việc deserialize có thể khiến trạng thái thiếu hoặc null trở thành `0` hoặc `false`, tùy cấu hình Jackson. Điều này làm mất khả năng phân biệt “không được gửi” với “đã gửi giá trị 0”. Dùng kiểu tham chiếu như `Integer`, `Boolean` hoặc `BigDecimal` khi cần nhận biết trường chưa có giá trị.

Nếu nghiệp vụ cần phân biệt cả missing và explicit null, một DTO thông thường với thuộc tính nullable có thể chưa đủ vì hai trạng thái có thể cùng trở thành `null`. Khi đó, hãy dùng JSON tree/presence wrapper, custom deserializer hoặc một schema format có hỗ trợ presence rõ ràng.

Không dùng giá trị mặc định chỉ để tránh lỗi deserialize. Default phải có ý nghĩa nghiệp vụ ổn định. Ví dụ, `quantity = 0` có thể hợp lệ khác với “chưa biết quantity”; `isActive = false` khác với “producer cũ không gửi trường isActive”.

## 5. Bỏ trường đã tồn tại

Bỏ trường có thể phá vỡ consumer vẫn đang phụ thuộc vào nó.

Giả sử V1 có `legacyCode`, còn V2 bỏ trường đó. Hai tình huống cần kiểm tra:

- **Consumer mới đọc message cũ:** message cũ vẫn chứa `legacyCode`. Consumer mới phải bỏ qua trường này hoặc tiếp tục hỗ trợ alias/field cũ trong giai đoạn chuyển tiếp.
- **Consumer cũ đọc message mới:** message mới không còn `legacyCode`. Consumer cũ có thể deserialize nhưng logic nghiệp vụ vẫn có thể lỗi nếu trường đó là bắt buộc.

Một lộ trình an toàn:

1. Đánh dấu trường cũ là deprecated trong tài liệu contract và code.
2. Chuyển consumer sang không còn phụ thuộc trường cũ; vẫn chấp nhận message có hoặc không có trường đó.
3. Nếu cần thay thế, thêm trường mới với tên và ý nghĩa rõ ràng.
4. Cho producer ngừng gửi trường cũ sau khi các consumer đã sẵn sàng.
5. Chờ hết thời gian lưu trữ/replay của message cũ hoặc bảo đảm consumer vẫn đọc được schema cũ.
6. Chỉ sau đó mới loại bỏ trường cũ khỏi schema và DTO.

Với event sourcing hoặc broker lưu message lâu dài, bước 5 rất quan trọng. Một message được tạo từ nhiều tháng trước vẫn có thể được replay vào consumer mới. Việc producer hiện tại không còn gửi trường cũ không có nghĩa dữ liệu cũ đã biến mất.

## 6. Đổi tên trường

Đổi tên về mặt code có vẻ nhỏ, nhưng trên wire format đó thường là bỏ một key và thêm một key khác.

Ví dụ đổi `customer_name` thành `displayName`. Trong giai đoạn chuyển tiếp, DTO Jackson có thể đọc cả tên cũ lẫn mới bằng `@JsonAlias`:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerSnapshot(
    @JsonProperty("displayName")
    @JsonAlias({"customer_name", "name"})
    String displayName
) {}
~~~

`@JsonAlias` cho phép deserializer nhận các tên cũ. Khi serialize, thuộc tính chính vẫn được ghi bằng tên `displayName`. Vì vậy alias giúp consumer mới đọc message cũ; nó không làm cho consumer cũ tự hiểu tên mới.

Để rollout an toàn, có thể tạm thời gửi cả key cũ và mới, cho consumer mới ưu tiên key mới và fallback về key cũ, rồi chờ consumer cũ được nâng cấp trước khi ngừng gửi key cũ. Nếu cả hai key cùng xuất hiện, phải quy định rõ key nào có quyền ưu tiên và kiểm thử trường hợp giá trị xung đột.

Với Avro, field alias hỗ trợ schema resolution khi reader schema đổi tên field. Với Protocol Buffers binary wire format, field name không phải định danh trên wire; field number mới là định danh. Tuy nhiên, đổi tên vẫn ảnh hưởng JSON/TextFormat mapping và code sinh ra. Do đó, cần đánh giá riêng binary format và JSON representation.

## 7. Đổi kiểu dữ liệu của trường

Đổi kiểu trực tiếp trên cùng một tên trường là thay đổi rủi ro cao nhất trong ba loại thay đổi.

Ví dụ:

~~~json
{ "customerId": "00042" }
~~~

được đổi thành:

~~~json
{ "customerId": 42 }
~~~

Các consumer có thể:
- Không deserialize được vì kiểu Java không khớp.
- Mất số 0 ở đầu nếu identifier bị chuyển từ chuỗi sang số.
- Tràn số khi giá trị vượt miền biểu diễn của kiểu mới.
- Thay đổi độ chính xác khi đổi giữa integer, floating point và decimal.
- Chạy được nhưng diễn giải sai đơn vị hoặc ý nghĩa.

Identifier thường nên giữ dạng chuỗi vì có thể chứa số 0 đầu, chữ cái hoặc ký tự định dạng. Tiền tệ nên dùng `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất có quy tắc scale rõ ràng; tránh đổi tiền từ decimal sang `double` vì floating point có thể làm tròn.

### Chiến lược đổi kiểu bằng trường mới

Thay vì đổi kiểu tại chỗ, hãy thêm trường mới với tên thể hiện rõ kiểu/ý nghĩa:

~~~json
{
  "customerId": "00042",
  "customerIdNumeric": 42
}
~~~

Consumer mới đọc `customerIdNumeric` khi có, nếu không thì chuyển đổi từ `customerId` theo quy tắc đã kiểm tra. Producer có thể dual-write cả hai trường trong thời gian chuyển tiếp. Sau khi mọi consumer đã dùng trường mới và dữ liệu cũ không còn cần thiết, mới dừng trường cũ.

Nếu ý nghĩa nghiệp vụ thay đổi, không chỉ kiểu dữ liệu thay đổi, hãy cân nhắc tạo event type hoặc schema version mới. Ví dụ `amount` trước đây là tổng trước thuế nhưng nay là tổng sau thuế thì cùng một kiểu `BigDecimal` vẫn là breaking change về semantics.

### Một số lưu ý về numeric types

- `int32` sang `int64` có thể giữ nguyên giá trị cũ trong phạm vi hợp lệ, nhưng consumer Java, database column, JSON Schema và serializer đều cần được kiểm tra.
- `long` sang `double` có thể mất độ chính xác với số nguyên lớn.
- `BigDecimal` sang `double` có thể làm thay đổi giá trị tiền.
- Chuỗi timestamp sang epoch milliseconds là thay đổi định dạng và đơn vị; cần quy định timezone, độ chính xác và quy tắc chuyển đổi.
- Đổi enum thành string hoặc ngược lại ảnh hưởng cả cách serialize lẫn cách xử lý giá trị chưa biết.

Không kết luận một phép đổi kiểu an toàn chỉ vì một ví dụ nhỏ deserialize thành công. Phải thử với giá trị biên, dữ liệu thực tế và mọi serializer/consumer đang được triển khai.

## 8. Quy tắc cụ thể theo định dạng dữ liệu

### JSON và Jackson trong Spring

JSON thường được xem là linh hoạt vì object có thể chứa các thuộc tính mới. Nhưng tính linh hoạt chỉ hữu ích khi consumer được cấu hình để xử lý chúng.

Trong Spring Messaging, `MessageConverter` chuyển payload đã serialize thành kiểu Java. Với Jackson converter, hãy xác định:

- Converter nào đang được dùng ở từng endpoint.
- `Content-Type` có chính xác là `application/json` hay không.
- Unknown property có được bỏ qua hay gây lỗi.
- Missing/null có được phân biệt không.
- Enum không nhận diện được được xử lý thế nào.
- Custom serializer/deserializer có làm thay đổi quy tắc mặc định không.

Spring Framework 6.2 `MappingJackson2MessageConverter` mặc định bỏ qua thuộc tính JSON chưa biết. Nhưng cấu hình riêng, converter khác hoặc consumer viết bằng ngôn ngữ khác có thể có hành vi khác. Không được suy rộng hành vi của một consumer Spring sang toàn bộ hệ thống.

Giá trị enum mới cũng có thể làm consumer cũ lỗi. Unknown property và unknown enum value là hai trường hợp khác nhau. Có thể thiết kế enum với giá trị fallback như `UNKNOWN`, hoặc dùng string và map sang domain enum bằng logic có kiểm soát. Không dựa vào `FAIL_ON_UNKNOWN_PROPERTIES` để xử lý enum.

### Protocol Buffers

Với Protobuf binary wire format:

- Mỗi field có một field number duy nhất; number này là định danh trên wire và không được đổi sau khi message type đã được sử dụng.
- Thêm field mới thường an toàn nếu dùng number chưa từng sử dụng và consumer cũ xử lý unknown field theo đúng runtime.
- Khi bỏ field, phải reserve field number; nên reserve cả field name để tránh tái sử dụng nhầm và giữ an toàn cho JSON/TextFormat.
- Không tái sử dụng field number đã bỏ.
- Tránh đổi kiểu field tại chỗ. Một số cặp kiểu có wire representation tương thích có điều kiện, nhưng vẫn có thể gây mất dữ liệu hoặc phá vỡ code ứng dụng.
- Thêm enum value có thể an toàn ở wire format nhưng vẫn làm code consumer có switch exhaustive hoặc logic không có nhánh fallback bị lỗi.

Ví dụ:

~~~protobuf
syntax = "proto3";

message PaymentAuthorized {
  string payment_id = 1;
  int64 amount_minor_units = 2;
  string currency = 3;

  // Field cũ đã bị loại bỏ; không tái sử dụng số 4 hoặc tên này.
  reserved 4;
  reserved "legacy_amount";
}
~~~

Các quy tắc trên áp dụng cho binary wire format. ProtoJSON và TextFormat có quy tắc tương thích riêng; field name và enum name được biểu diễn trong JSON nên việc đổi tên có thể gây ảnh hưởng dù binary field number vẫn giữ nguyên.

Tham khảo [Protocol Buffers: Updating A Message Type](https://protobuf.dev/programming-guides/proto3/#updating) và [Proto Best Practices](https://protobuf.dev/programming-guides/dos-donts/).

### Apache Avro

Avro hỗ trợ schema resolution giữa writer schema và reader schema. Khi consumer đọc record được ghi bằng schema cũ, reader schema mới có thể bổ sung field nếu field đó có default. Giá trị default được dùng khi writer schema không có field tương ứng.

Ví dụ thêm field `currency`:

~~~json
{
  "type": "record",
  "name": "PaymentAuthorized",
  "fields": [
    { "name": "paymentId", "type": "string" },
    { "name": "amountMinorUnits", "type": "long" },
    {
      "name": "currency",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

Với union nullable, đặt nhánh `null` đầu tiên nếu default là `null`. Default trong Avro là quy tắc đọc khi reader có field nhưng writer schema không có field đó; nó không có nghĩa producer được phép bỏ field khi ghi nếu schema writer yêu cầu field ấy.

Khi bỏ field, reader schema mới có thể bỏ qua field có trong writer schema cũ. Khi đổi tên, aliases hỗ trợ ánh xạ tên cũ sang tên mới. Avro cũng cho phép một số type promotion cụ thể như `int` sang `long`, `float` hoặc `double`, và `float` sang `double`; không phải mọi phép đổi kiểu đều hợp lệ.

Tham khảo [Apache Avro Specification](https://avro.apache.org/docs/current/specification/), đặc biệt phần schema resolution, field defaults, aliases và type promotion.

## 9. Schema Registry và kiểm tra compatibility

Nếu hệ thống dùng schema registry, hãy chọn compatibility mode phù hợp với cách producer/consumer được triển khai:

- **BACKWARD:** consumer theo schema mới đọc được data từ schema liền trước.
- **BACKWARD_TRANSITIVE:** consumer mới đọc được data từ mọi schema đã đăng ký trước đó.
- **FORWARD:** consumer cũ đọc được data theo schema mới.
- **FORWARD_TRANSITIVE:** mọi consumer schema cũ được kiểm tra với schema mới.
- **FULL:** backward và forward với phiên bản trước.
- **FULL_TRANSITIVE:** backward và forward với mọi phiên bản trước.
- **NONE:** không kiểm tra compatibility.

Ví dụ, Confluent Schema Registry mặc định dùng `BACKWARD` và không phải `BACKWARD_TRANSITIVE`. Quy tắc cho Avro, Protobuf và JSON Schema khác nhau. Riêng JSON Schema còn phụ thuộc content model mở/đóng và compatibility policy. Xem [Confluent Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html).

Registry chỉ kiểm tra những quy tắc schema mà nó hiểu. Nó không biết mọi logic nghiệp vụ của consumer, không đảm bảo đơn vị đo không thay đổi, và không thay thế contract test. Hãy kết hợp kiểm tra registry với kiểm thử producer/consumer thật.

## 10. Triển khai theo mô hình expand-contract

Đối với hệ thống có nhiều instance hoặc deploy độc lập, hãy thay đổi contract theo nhiều bước.

### Khi thêm trường

1. Thiết kế field mới là tùy chọn trong giai đoạn chuyển tiếp; xác định rõ default hoặc cách xử lý khi thiếu.
2. Deploy consumer mới trước để đọc được message cũ và message mới.
3. Xác nhận consumer cũ có bỏ qua field mới hay không. Nếu consumer cũ strict, nâng cấp chúng trước khi producer gửi field mới.
4. Bắt đầu để producer ghi field mới.
5. Theo dõi tỷ lệ message có field mới và lỗi deserialize.
6. Chỉ sau khi mọi producer/consumer đã chuyển đổi mới xem xét siết validation.

### Khi bỏ trường

1. Ngừng dùng field cũ trong logic consumer.
2. Deploy consumer có thể xử lý message có hoặc không có field.
3. Ngừng phát field cũ từ producer.
4. Chờ thời gian lưu trữ và replay của message cũ, hoặc bảo đảm schema cũ vẫn được hỗ trợ.
5. Loại field khỏi schema/DTO sau khi không còn consumer hay dữ liệu lịch sử phụ thuộc.

### Khi đổi kiểu hoặc ý nghĩa

1. Giữ nguyên field cũ.
2. Thêm field mới với tên khác và kiểu/ý nghĩa mới.
3. Nâng cấp consumer để đọc field mới, fallback sang field cũ.
4. Nâng cấp producer để dual-write hoặc chuyển đổi theo từng nhóm.
5. Đối chiếu dữ liệu giữa hai field, xử lý sai lệch.
6. Ngừng field cũ sau khi mọi consumer và luồng replay đã chuyển đổi.

Mô hình này thường được gọi là expand-contract: mở rộng contract để cả hai phiên bản cùng tồn tại, chuyển dần producer/consumer, rồi mới thu hẹp và dọn field cũ.

## 11. Kiểm thử tương thích

Mỗi thay đổi contract nên có test matrix. Không chỉ kiểm tra DTO mới với payload mới.

| Producer | Consumer | Kịch bản cần xác minh |
|---|---|---|
| V1 | V1 | Hành vi hiện tại không bị thay đổi |
| V1 | V2 | Consumer mới đọc được message cũ |
| V2 | V1 | Consumer cũ xử lý được message mới nếu yêu cầu forward compatibility |
| V2 | V2 | Hành vi mới đúng theo contract |

Bộ test nên bao gồm:

- Payload thiếu field mới.
- Payload có field mới với giá trị hợp lệ.
- Payload có field mới bằng null.
- Payload có field lạ mà consumer không khai báo.
- Enum value mới.
- Giá trị số nhỏ nhất/lớn nhất, overflow và độ chính xác.
- Field rename có cả tên cũ và tên mới.
- Message được lưu từ schema cũ và phát lại.
- Message sai kiểu hoặc sai format cần bị từ chối có kiểm soát.
- Custom `ObjectMapper` hoặc converter thực tế của ứng dụng.

Lưu payload đại diện của các phiên bản cũ thành fixture trong test. Khi thay đổi DTO hoặc schema, chạy lại toàn bộ fixture đó với consumer mới. Nếu có schema registry, đưa compatibility check vào CI trước khi đăng ký schema mới.

## 12. Lỗi thường gặp

- **Thêm field bắt buộc ngay lập tức:** consumer mới không đọc được message do producer cũ tạo ra.
- **Giả định mọi consumer bỏ qua field lạ:** Jackson, Protobuf, JSON Schema và consumer tự viết có quy tắc khác nhau.
- **Nhầm missing với null hoặc zero:** dữ liệu mặc định có thể làm sai logic nghiệp vụ.
- **Bỏ field trước khi nâng cấp consumer:** consumer cũ có thể vẫn yêu cầu trường đó.
- **Đổi kiểu tại chỗ:** producer và consumer đang chạy khác phiên bản sẽ diễn giải cùng key theo kiểu khác nhau.
- **Đổi tên mà không hỗ trợ alias/dual-write:** consumer cũ không nhận ra tên mới.
- **Chỉ test schema mới:** không phát hiện message lịch sử hoặc producer cũ.
- **Tin rằng schema registry bảo đảm mọi thứ:** registry không kiểm tra ý nghĩa nghiệp vụ và mọi hành vi runtime.
- **Xóa field rồi tái sử dụng định danh:** với Protobuf, tái sử dụng field number có thể khiến dữ liệu được giải mã sai.

## 13. Checklist trước khi phát hành

- [ ] Đã xác định consumer nào đang đọc message và producer nào đang ghi message.
- [ ] Đã xác định yêu cầu backward, forward hay full compatibility.
- [ ] Đã kiểm tra định dạng serialization và phiên bản converter.
- [ ] Field mới có quy tắc missing/null/default rõ ràng.
- [ ] Consumer cũ có xử lý được field mới hay không đã được kiểm thử.
- [ ] Field bị bỏ đã hết người dùng và có kế hoạch xử lý message lịch sử.
- [ ] Thay đổi kiểu/ý nghĩa dùng field mới hoặc event version mới khi cần.
- [ ] Protobuf field number cũ đã được reserve khi xóa.
- [ ] Avro default/alias phù hợp với reader schema.
- [ ] Schema Registry compatibility check và contract tests đã chạy.
- [ ] Có kế hoạch dual-read/dual-write và thời điểm loại field cũ.
- [ ] Có metric/log theo dõi lỗi deserialize và tỷ lệ message theo schema version.

## Tài liệu tham khảo

- [Spring Framework — MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.0-M6/javadoc-api/org/springframework/messaging/converter/MessageConverter.html): chuyển đổi payload và vai trò của content type.
- [Spring Framework — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html): cấu hình Jackson 2 và xử lý unknown properties.
- [Protocol Buffers — Proto3 Language Guide](https://protobuf.dev/programming-guides/proto3/): field number, unknown fields, thêm/bỏ field và wire compatibility.
- [Protocol Buffers — Best Practices](https://protobuf.dev/programming-guides/dos-donts/): tránh đổi kiểu field và các quy tắc khi xóa.
- [Apache Avro — Specification](https://avro.apache.org/docs/current/specification/): schema resolution, defaults, aliases và type promotion.
- [Confluent — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): backward, forward, full và transitive compatibility.
