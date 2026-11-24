# Thứ tự lựa chọn contentType từ header, binding và mặc định

Spring Cloud Stream cần biết định dạng của payload để chọn cách chuyển đổi dữ liệu giữa đối tượng Java và dữ liệu truyền qua Kafka, RabbitMQ hoặc Pulsar. Thông tin định dạng này được biểu diễn bằng `contentType` (media type). Khi một thông điệp được gửi hoặc nhận, framework lựa chọn `contentType` theo thứ tự ưu tiên: **header của message**, sau đó **cấu hình của binding**, cuối cùng là **giá trị mặc định của ứng dụng**.

Thứ tự này rất quan trọng khi một luồng có nhiều producer, khi một function thay đổi kiểu payload, hoặc khi ứng dụng dùng chung binding cho các định dạng khác nhau. Nếu header cũ không còn phù hợp với payload mới, framework có thể chọn nhầm converter và gây lỗi chuyển đổi dù cấu hình binding có vẻ đúng.

## 1. contentType là gì?

`contentType` mô tả định dạng và kiểu nội dung của payload. Giá trị thường tuân theo cú pháp media type, gồm type và subtype, đôi khi có thêm tham số:

| Giá trị | Ý nghĩa thường gặp |
|---|---|
| `application/json` | Payload được biểu diễn bằng JSON. |
| `text/plain` | Payload là văn bản thuần. |
| `application/octet-stream` | Dữ liệu nhị phân không gắn một định dạng ứng dụng cụ thể. |
| `application/avro` | Payload dùng định dạng Avro khi ứng dụng đã cấu hình converter/serializer tương ứng. |
| `application/xml` | Payload được biểu diễn bằng XML khi có converter phù hợp. |
| `application/json; charset=UTF-8` | JSON với tham số charset được chỉ định. |

Trong Spring Messaging, một `Message<T>` gồm payload và headers. Header `contentType` là metadata mô tả cách diễn giải payload. Ở cấu hình binding, thuộc tính `content-type` khai báo định dạng mặc định cho binding đó. Nếu cả hai nơi không cung cấp giá trị, Spring Cloud Stream dùng content type mặc định của ứng dụng, thông thường là `application/json`.

`contentType` là thông tin để lựa chọn cơ chế chuyển đổi. Nó không tự định nghĩa schema nghiệp vụ, không bảo đảm payload hợp lệ và cũng không tự cài đặt converter cho Avro, Protobuf hay XML. Converter hoặc serializer tương ứng vẫn phải có mặt và được cấu hình phù hợp.

## 2. Thứ tự ưu tiên lựa chọn contentType

Spring Cloud Stream xét ba nguồn theo thứ tự từ ưu tiên cao xuống thấp:

| Thứ tự | Nguồn | Khi nào được dùng? | Ví dụ |
|---|---|---|---|
| 1 – cao nhất | Header `contentType` của message | Message có header content type hợp lệ. | `text/plain` |
| 2 | Binding property `content-type` | Message không có header content type. | `application/json` |
| 3 – thấp nhất | Default content type | Message không có header và binding không khai báo content type. | `application/json` mặc định |

Có thể ghi nhớ quy tắc:

```text
message header contentType
          |
          v
binding content-type
          |
          v
spring.cloud.stream.default.contentType
          |
          v
default: application/json
```

Nguồn có thứ tự cao hơn sẽ quyết định content type được dùng cho lần chuyển đổi đó. Giá trị ở mức thấp hơn đóng vai trò dự phòng khi không có giá trị ở mức cao hơn.

### Ví dụ chọn theo từng trường hợp

Giả sử binding đầu ra được cấu hình `application/json`:

| Header message | Binding `content-type` | Default | Kết quả lựa chọn |
|---|---|---|---|
| `text/plain` | `application/json` | `application/json` | `text/plain` từ header |
| Không có | `application/json` | `text/plain` | `application/json` từ binding |
| Không có | Không khai báo | `text/plain` | `text/plain` từ default |
| Không có | Không khai báo | Không tùy chỉnh | `application/json` mặc định |

Một header hiện diện có độ ưu tiên cao hơn cấu hình binding. Vì vậy, đặt `content-type: application/json` trong YAML không đảm bảo JSON converter sẽ được chọn nếu message mang header `contentType: text/plain`.

## 3. Nguồn thứ nhất: header contentType của Message

Header là nguồn có độ ưu tiên cao nhất. Ứng dụng có thể gắn content type vào message khi tạo dữ liệu hoặc khi function xây dựng message đầu ra.

Ví dụ tạo một message văn bản:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> message = MessageBuilder
    .withPayload("Order order-9001 has been created")
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
    .build();
```

Header `MessageHeaders.CONTENT_TYPE` mô tả payload là `text/plain`. Nếu message này được gửi qua binding có cấu hình `content-type: application/json`, content type từ header vẫn có ưu tiên cao hơn. Framework sẽ chọn cách chuyển đổi tương ứng với `text/plain`, miễn là có converter phù hợp.

Một function cũng có thể thay đổi payload và cập nhật content type:

```java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Function<OrderPlaced, Message<String>> renderOrder = order ->
    MessageBuilder.withPayload(
            "Order " + order.orderId() + ", total=" + order.totalAmount())
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
        .build();
```

Ở đây, function chuyển từ `OrderPlaced` sang `String`, vì vậy header đầu ra được đặt thành `text/plain`. Consumer phía sau cần nhận nội dung theo hợp đồng văn bản tương ứng.

### Cẩn thận khi sao chép header

Khi function nhận `Message<T>`, sao chép toàn bộ header sang message mới có thể giữ lại `contentType` của payload cũ. Nếu payload đã đổi định dạng nhưng header không đổi, converter phía sau sẽ diễn giải payload theo định dạng sai.

Ví dụ, đầu vào là JSON nhưng đầu ra là văn bản. Khi tạo message mới, hãy ghi đè content type:

```java
Message<String> output = MessageBuilder
    .withPayload("Order " + input.getPayload().orderId())
    .copyHeaders(input.getHeaders())
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
    .build();
```

Không nên sao chép header một cách máy móc khi payload thay đổi. Hãy xem xét những metadata nào còn đúng ở message mới, đặc biệt là content type, schema version và các header định tuyến.

## 4. Nguồn thứ hai: content-type của binding

Nếu message không có header `contentType`, Spring Cloud Stream sử dụng thuộc tính `content-type` của binding. Cấu hình này phù hợp khi mọi message đi qua một binding tuân theo cùng một định dạng.

Ví dụ cấu hình đầu vào và đầu ra dùng JSON:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.placed
          group: order-enrichment
          content-type: application/json
        enrichOrder-out-0:
          destination: orders.enriched
          content-type: application/json
```

Khi message đi vào `enrichOrder-in-0` mà không mang header content type, binding cung cấp `application/json` cho quá trình chuyển đổi. Ở đầu ra, nếu function trả một payload không kèm header content type, binding `enrichOrder-out-0` cung cấp định dạng được cấu hình.

Có thể cấu hình content type khác nhau cho đầu vào và đầu ra. Ví dụ, một function nhận JSON rồi phát văn bản:

```yaml
spring:
  cloud:
    function:
      definition: describeOrder
    stream:
      bindings:
        describeOrder-in-0:
          destination: orders.events
          content-type: application/json
        describeOrder-out-0:
          destination: orders.audit-text
          content-type: text/plain
```

Điều này thể hiện hợp đồng của từng chặng: đầu vào là JSON, đầu ra là văn bản. Nếu function trả một `Message` có header content type riêng, header đó vẫn được ưu tiên hơn binding property.

## 5. Nguồn thứ ba: default content type

Khi message không có header content type và binding cũng không khai báo `content-type`, Spring Cloud Stream sử dụng default content type. Giá trị mặc định thông thường là `application/json`.

Có thể thay đổi default content type ở cấp ứng dụng bằng thuộc tính `spring.cloud.stream.default.contentType`:

```yaml
spring:
  cloud:
    stream:
      default:
        contentType: application/json
```

Trong trường hợp không đặt thuộc tính này, framework dùng `application/json`. Default có phạm vi rộng, vì vậy chỉ nên thay đổi khi phần lớn binding trong ứng dụng thực sự dùng cùng định dạng. Với binding có hợp đồng khác biệt, khai báo `content-type` tường minh thường dễ đọc và dễ bảo trì hơn.

Default content type không ghi đè header hoặc cấu hình binding. Nó chỉ được dùng khi hai nguồn có ưu tiên cao hơn không cung cấp content type.

## 6. Thứ tự lựa chọn áp dụng ở chiều gửi và chiều nhận

Content type tham gia vào quá trình chuyển đổi dữ liệu ở cả hai chiều:

### Chiều gửi (producer)

1. Function hoặc thành phần ứng dụng tạo payload hay `Message<?>`.
2. Framework xác định content type theo header, binding property rồi default.
3. Message converter phù hợp chuyển payload thành dạng truyền tải.
4. Binder gửi dữ liệu đã chuyển đổi tới destination của broker.

Nếu header ghi `text/plain` nhưng payload thực tế là một đối tượng JSON, lựa chọn converter có thể không phù hợp với dữ liệu. Cần bảo đảm header mô tả đúng payload trước khi gửi.

### Chiều nhận (consumer)

1. Binder nhận dữ liệu từ destination và tạo message cho binding đầu vào.
2. Framework xác định content type từ header được truyền tới message, cấu hình binding hoặc default.
3. Converter được chọn để chuyển dữ liệu truyền tải thành kiểu payload mà function/consumer yêu cầu.
4. Nếu dữ liệu không phù hợp với converter hoặc kiểu đích, quá trình chuyển đổi có thể thất bại trước khi hàm nghiệp vụ được gọi.

Header chỉ có thể tham gia lựa chọn ở phía nhận nếu nó được broker và binder bảo toàn hoặc ánh xạ vào message. Không phải broker/binder nào cũng truyền mọi header theo cùng cách. Nếu header content type không được chuyển tiếp, binding property hoặc default ở phía nhận sẽ được dùng.

## 7. Content type và MessageConverter

Sau khi xác định content type, Spring Cloud Stream sử dụng cơ chế message conversion phù hợp. Converter nhận biết media type và kiểu đích để chuyển dữ liệu giữa biểu diễn truyền tải và đối tượng ứng dụng.

Một số ví dụ:

| Content type | Payload ứng dụng thường gặp | Lưu ý |
|---|---|---|
| `application/json` | Java record/POJO, `Map`, collection | Cần converter JSON phù hợp; schema vẫn phải tương thích. |
| `text/plain` | `String` | Dữ liệu cần đúng quy ước charset và nội dung văn bản. |
| `application/octet-stream` | `byte[]` | Ứng dụng tự chịu trách nhiệm diễn giải byte. |
| `application/avro` | Đối tượng Avro hoặc dạng được converter hỗ trợ | Cần cấu hình Avro converter/serializer và schema. |
| `application/xml` | POJO hoặc XML representation | Cần converter XML phù hợp. |

Nếu không có converter hỗ trợ content type đã chọn hoặc không thể chuyển đổi sang kiểu đích, framework có thể ném lỗi conversion. Chỉ đổi header từ `application/json` sang `application/avro` không biến byte JSON thành Avro; nội dung phải được serialize đúng định dạng.

Content type cũng có thể chứa tham số như charset. Với dữ liệu văn bản, producer và consumer nên thống nhất charset, thường là UTF-8. Khi xử lý dữ liệu nhị phân, không nên giải mã byte thành chuỗi theo charset tùy ý.

## 8. Ví dụ xác định converter qua ba cấp

Giả sử ứng dụng có cấu hình mặc định JSON:

```yaml
spring:
  cloud:
    stream:
      default:
        contentType: application/json
      bindings:
        publishReport-out-0:
          destination: reports.output
          content-type: application/json
        publishText-out-0:
          destination: reports.text
```

Ba message có kết quả như sau:

**Message A – có header:**

```java
Message<String> textMessage = MessageBuilder
    .withPayload("Daily report is ready")
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
    .build();
```

Nếu gửi qua `publishReport-out-0`, header `text/plain` được ưu tiên hơn binding `application/json`.

**Message B – không có header, binding có content type:**

```java
streamBridge.send("publishReport-out-0", reportObject);
```

Nếu message không mang header content type, binding `publishReport-out-0` chọn `application/json`.

**Message C – không có header, binding không khai báo content type:**

```java
streamBridge.send("publishText-out-0", "Report generated");
```

Binding `publishText-out-0` không khai báo content type, do đó default `application/json` được chọn theo cấu hình ví dụ. Nếu muốn văn bản thuần, hãy đặt `content-type: text/plain` trên binding hoặc gắn header `text/plain` vào message.

Ví dụ này cho thấy payload là `String` không tự động có nghĩa content type sẽ là `text/plain`. Việc lựa chọn định dạng vẫn tuân theo thứ tự ưu tiên đã nêu; kiểu Java và content type cần được thiết kế thống nhất.

## 9. Những lỗi thường gặp khi contentType không khớp

### Header cũ ghi đè binding

Function nhận message JSON, sao chép header rồi đổi payload thành chuỗi nhưng quên thay `contentType`. Header cũ vẫn có thể thắng cấu hình `text/plain` của binding đầu ra. Converter nhận metadata JSON trong khi payload mới là văn bản.

**Cách xử lý:** khi đổi kiểu payload, hãy đặt lại `MessageHeaders.CONTENT_TYPE` hoặc loại bỏ header cũ nếu muốn binding/default quyết định.

### Nghĩ rằng binding luôn có ưu tiên cao nhất

Nhóm phát triển cấu hình `content-type: application/json` nhưng producer gửi message mang header `text/plain`. Header có ưu tiên cao hơn, vì vậy binding không phải nguồn được chọn.

**Cách xử lý:** kiểm tra header thực tế ở ranh giới gửi và xác định thành phần nào tạo hoặc sao chép nó.

### Payload và content type mô tả hai định dạng khác nhau

Ứng dụng đặt header `application/avro` nhưng vẫn gửi chuỗi JSON. Framework chọn converter theo Avro và quá trình chuyển đổi có thể thất bại.

**Cách xử lý:** bảo đảm serializer tạo đúng định dạng được khai báo; content type chỉ mô tả dữ liệu, không thực hiện phép biến đổi thay cho serializer.

### Giả định header luôn đi qua broker

Producer đặt header content type nhưng binder hoặc broker không truyền header đó theo cách mong đợi. Consumer không nhìn thấy header và chọn content type theo binding hoặc default.

**Cách xử lý:** kiểm tra header mapping của binder, cấu hình native encoding/decoding và message thực tế ở phía nhận. Với hợp đồng ổn định, khai báo binding content type tường minh ở phía consumer.

### Dùng default cho các binding có định dạng khác nhau

Ứng dụng đổi default thành `text/plain` để phục vụ một luồng văn bản, vô tình ảnh hưởng các binding khác không khai báo content type.

**Cách xử lý:** giữ default phù hợp với phần lớn luồng và khai báo rõ content type tại binding có định dạng riêng.

## 10. Lưu ý khi dùng native encoding và native decoding

Một số binder cho phép broker client thực hiện serialization/deserialization gốc thay cho message conversion của Spring Cloud Stream. Ví dụ, Kafka binder có các tùy chọn như `useNativeEncoding` ở phía producer và `useNativeDecoding` ở phía consumer.

Khi bật native encoding/decoding, serializer/deserializer của client hoặc broker được cấu hình có thể đảm nhiệm việc chuyển đổi payload. Khi đó, không nên giả định message converter của Spring sẽ xử lý dữ liệu theo đúng đường đi thông thường chỉ dựa vào `contentType`. Cần cấu hình serializer/deserializer, kiểu dữ liệu và schema nhất quán ở cả hai phía.

Content type vẫn có thể hữu ích như metadata mô tả dữ liệu, nhưng không thay thế cấu hình native serializer/deserializer. Tên thuộc tính và hành vi cụ thể khác nhau theo binder, vì vậy hãy đối chiếu tài liệu của đúng binder và phiên bản đang sử dụng.

## 11. Kiểm thử thứ tự ưu tiên contentType

Nên kiểm thử từng nguồn ưu tiên để tránh chỉ kiểm tra trường hợp mặc định:

| Trường hợp | Thiết lập | Kết quả cần xác minh |
|---|---|---|
| Header ghi đè binding | Binding JSON, header text/plain | Converter/định dạng được chọn theo header. |
| Binding ghi đè default | Không có header, binding text/plain, default JSON | Binding được sử dụng. |
| Default được dùng | Không có header, không có binding content type | Default cấu hình được sử dụng. |
| Header không hỗ trợ | Header chỉ tới media type không có converter | Có lỗi conversion rõ ràng, không âm thầm coi payload là định dạng khác. |
| Header cũ sau khi đổi payload | Copy header cũ rồi đổi kiểu payload | Kiểm tra header được thay hoặc loại bỏ đúng. |
| Header qua broker | Gửi và nhận bằng binder thật | Xác minh header được mapping/bảo toàn như dự kiến. |

Spring Cloud Stream Test Binder hữu ích để kiểm thử logic function, binding và message header trong phạm vi ứng dụng. Tuy nhiên, nó không mô phỏng đầy đủ mapping header và native serialization của Kafka, RabbitMQ hoặc Pulsar. Những hành vi phụ thuộc broker cần được xác minh bằng kiểm thử tích hợp với binder tương ứng.

Khi điều tra lỗi conversion, hãy ghi nhận tên binding, content type được chọn, kiểu payload trước chuyển đổi, kiểu đích và nguyên nhân từ converter. Tránh log toàn bộ payload nếu chứa dữ liệu nhạy cảm.

## 12. Quy trình xác định contentType khi có lỗi

Khi một message không được chuyển đổi như mong đợi, lần lượt kiểm tra:

1. Message có header `contentType` không? Nếu có, giá trị và kiểu dữ liệu của header là gì?
2. Header có được tạo ở producer, sao chép từ message trước hay được binder ánh xạ từ broker?
3. Binding hiện tại khai báo `content-type` nào?
4. Nếu header và binding đều không có, default `spring.cloud.stream.default.contentType` đang là gì?
5. Converter tương ứng có được đăng ký và hỗ trợ media type cùng kiểu payload đích không?
6. Payload thực tế có đúng định dạng mà content type mô tả không?
7. Binder có bật native encoding/decoding khiến đường chuyển đổi khác đi không?
8. Ở phía nhận, header có còn tồn tại hay consumer đang dựa vào binding property/default?

Thứ tự header → binding → default giúp Spring Cloud Stream chọn một content type nhất quán khi chuyển đổi thông điệp. Khi hiểu rõ nguồn nào đang thắng và bảo đảm metadata luôn mô tả đúng payload, nhóm phát triển có thể tránh phần lớn lỗi chọn converter sai và giữ hợp đồng dữ liệu ổn định giữa các dịch vụ.
