# Encoder, Decoder và cấu hình codec trong Spring RSocket

## Mục tiêu

RSocket truyền payload dưới dạng byte và metadata. Ứng dụng Spring thường làm việc với đối tượng Java như record, DTO hoặc message class, vì vậy cần một lớp chuyển đổi giữa đối tượng và byte. Spring sử dụng Encoder để tuần tự hóa dữ liệu gửi đi, Decoder để giải mã dữ liệu nhận về, và RSocketStrategies để tập hợp các codec cùng những chiến lược hỗ trợ cho requester và responder.

Nắm được cách cấu hình codec giúp hai đầu kết nối hiểu cùng một định dạng, xử lý được DTO tùy chỉnh, dùng JSON/CBOR/Protocol Buffers đúng cách và tránh các lỗi thường gặp như không tìm thấy Encoder, MIME type không khớp hoặc giải mã sai kiểu.

## 1. Encoder, Decoder và codec là gì?

### Encoder

org.springframework.core.codec.Encoder<T> chuyển một đối tượng kiểu T thành một hoặc nhiều DataBuffer để gửi qua RSocket. Ví dụ, JacksonJsonEncoder biến một DTO Java thành byte JSON; ProtobufEncoder chuyển một message được sinh từ Protocol Buffers thành byte Protobuf.

Một Encoder cần xác định nó có hỗ trợ kiểu dữ liệu và MIME type đang yêu cầu hay không. Spring gọi canEncode(ResolvableType, MimeType) để kiểm tra khả năng tương thích trước khi sử dụng encoder.

### Decoder

org.springframework.core.codec.Decoder<T> thực hiện chiều ngược lại: đọc DataBuffer và tạo ra đối tượng Java. JacksonJsonDecoder có thể giải mã JSON thành DTO; ProtobufDecoder giải mã byte Protobuf thành một Message.

Decoder cũng phải xác định kiểu đích và MIME type mà nó hỗ trợ thông qua canDecode(ResolvableType, MimeType). Nếu không có decoder phù hợp, Spring không thể chuyển payload nhận được thành tham số của handler hoặc kiểu phản hồi mà requester mong đợi.

### Codec

Trong ngữ cảnh này, codec là cách gọi chung cho bộ mã hóa và giải mã. Một định dạng dữ liệu thường cần cả Encoder lẫn Decoder:

- Chiều requester gửi: Encoder ở requester chuyển đối tượng thành byte.
- Chiều responder nhận: Decoder ở responder chuyển byte thành đối tượng.
- Chiều responder trả lời: Encoder ở responder chuyển kết quả thành byte.
- Chiều requester nhận: Decoder ở requester chuyển byte thành kiểu phản hồi.

Do đó, cấu hình chỉ có Encoder hoặc chỉ có Decoder thường chỉ hỗ trợ được một chiều của trao đổi dữ liệu. Với giao tiếp hai chiều, hai phía cần có các codec tương thích ở cả chiều gửi và chiều nhận.

## 2. Vai trò của RSocketStrategies

RSocketStrategies là nơi Spring tập hợp các thành phần dùng để mã hóa và giải mã dữ liệu, metadata cũng như hỗ trợ xử lý message. Thành phần này có thể chứa:

- Danh sách Encoder và Decoder.
- DataBufferFactory để cấp phát bộ đệm dữ liệu.
- ReactiveAdapterRegistry để thích nghi các kiểu reactive.
- RouteMatcher để so khớp route của các handler.
- MetadataExtractor để chuyển metadata thành giá trị ứng dụng.

RSocketRequester.Builder nhận RSocketStrategies để cấu hình requester. RSocketMessageHandler cũng có thể dùng cùng cấu hình để xử lý responder. Nếu client và server nằm trong cùng ứng dụng, nên cân nhắc khai báo một bean RSocketStrategies dùng chung để tránh hai bộ cấu hình lệch nhau.

### Codec mặc định của Spring Framework

Nếu chỉ dùng các codec cơ bản từ spring-core, Spring hỗ trợ các kiểu đơn giản như:

- String
- byte[]
- ByteBuffer

Những codec cơ bản này không tự động biến mọi DTO Java thành JSON. Để xử lý các kiểu đối tượng phổ biến, ứng dụng thường cần spring-web, nơi cung cấp các implementation như Jackson JSON, Jackson CBOR và Protobuf.

### Codec mặc định của Spring Boot

Spring Boot tự cấu hình bean RSocketStrategies khi có spring-boot-starter-rsocket. Theo tài liệu Spring Boot 4.1, thứ tự mặc định là:

1. Codec CBOR dùng Jackson.
2. Codec JSON dùng Jackson.

Starter cung cấp các dependency cần thiết cho cấu hình này. Có thể bổ sung hoặc tùy chỉnh codec bằng bean triển khai RSocketStrategiesCustomizer. Thứ tự các customizer có thể ảnh hưởng thứ tự codec được đăng ký.

Nếu dùng Spring Boot, hãy kiểm tra cấu hình mặc định của đúng phiên bản Boot trong dự án trước khi tạo một RSocketStrategies bean riêng. Việc tự khai báo bean có thể làm thay đổi hoặc thay thế cấu hình tự động mà ứng dụng đang dùng.

## 3. MIME type: định dạng của payload và metadata

RSocket phân biệt data và metadata. Hai loại này có MIME type riêng được khai báo trong frame SETUP của kết nối:

- dataMimeType mô tả định dạng của phần data trong payload, ví dụ application/json, application/cbor hoặc application/x-protobuf.
- metadataMimeType mô tả cách đóng gói metadata. Giá trị mặc định thường là composite metadata, cho phép một request mang nhiều mục metadata với MIME type riêng.

Các MIME type trong SETUP áp dụng cho kết nối. Vì vậy, dataMimeType không đơn thuần là HTTP Content-Type của từng request. Khi requester gửi một DTO JSON, responder phải có Decoder tương thích với MIME type và kiểu Java tương ứng.

Với composite metadata, từng mục metadata có thể có MIME type riêng. Ví dụ route và thông tin xác thực có thể là các mục metadata khác nhau. Không nên nhầm MIME type của một mục metadata với dataMimeType của payload.

RSocketRequester.Builder cung cấp các phương thức:

- dataMimeType(MimeType): đặt MIME type cho data của kết nối.
- metadataMimeType(MimeType): đặt MIME type cho metadata của kết nối.
- setupData(Object): thêm data vào SETUP frame.
- setupMetadata(Object, MimeType): thêm một mục metadata vào SETUP frame.
- setupRoute(String, Object...): thêm route vào SETUP frame.

Trong hầu hết ứng dụng dùng routing và composite metadata mặc định, không cần đổi metadataMimeType. Nếu có nhiều Decoder trong registry, nên đặt dataMimeType tường minh khi muốn cố định định dạng trao đổi. Nếu không đặt, MIME type data mặc định được suy ra từ Decoder đầu tiên được cấu hình.

## 4. Cấu hình codec JSON với Spring Framework

Ví dụ sau dùng API Spring Framework 7.0 và Jackson 3. Cần có spring-web cùng các dependency Jackson tương ứng.

### Khai báo RSocketStrategies

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.JacksonJsonDecoder;
import org.springframework.http.codec.json.JacksonJsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
class RSocketCodecConfiguration {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders -> encoders.add(new JacksonJsonEncoder()))
            .decoders(decoders -> decoders.add(new JacksonJsonDecoder()))
            .routeMatcher(new PathPatternRouteMatcher())
            .build();
    }
}
~~~

JacksonJsonEncoder xử lý chiều chuyển DTO thành JSON; JacksonJsonDecoder xử lý chiều chuyển JSON thành DTO. PathPatternRouteMatcher là route matcher từ spring-web, hữu ích khi ứng dụng cần so khớp route theo pattern. Nếu không cần nó, có thể dùng route matcher mặc định.

### Dùng cùng strategy cho responder

Với ứng dụng Spring Framework tự cấu hình responder, có thể gắn RSocketStrategies vào RSocketMessageHandler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;

@Bean
RSocketMessageHandler rsocketMessageHandler(RSocketStrategies strategies) {
    RSocketMessageHandler handler = new RSocketMessageHandler();
    handler.setRSocketStrategies(strategies);
    return handler;
}
~~~

RSocketMessageHandler sử dụng các Encoder và Decoder trong strategy để xử lý payload của các phương thức @MessageMapping và @ConnectMapping. Khi tự khởi chạy RSocketServer bằng API cấp thấp, cần gắn responder từ handler vào server transport. Với Spring Boot, hạ tầng handler và server có thể được tự cấu hình theo dependency và application properties.

### Cấu hình requester

~~~java
import org.springframework.http.MediaType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);
~~~

dataMimeType được đặt tường minh thành application/json để hai phía thống nhất định dạng data. requester dùng cùng strategy để encode request và decode response. Kết nối TCP ở ví dụ chỉ là transport; codec mới quyết định cách biểu diễn đối tượng thành byte.

## 5. Ví dụ truyền DTO JSON qua RSocket

Định nghĩa DTO đơn giản:

~~~java
public record DeviceEvent(
    String deviceId,
    long sequence,
    double temperatureC
) {}

public record DeviceAck(
    String deviceId,
    String status
) {}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class DeviceController {

    @MessageMapping("telemetry.accept")
    Mono<DeviceAck> accept(DeviceEvent event) {
        return Mono.just(new DeviceAck(event.deviceId(), "accepted"));
    }
}
~~~

Requester:

~~~java
Mono<DeviceAck> response = requester.route("telemetry.accept")
    .data(new DeviceEvent("sensor-17", 42, 28.6))
    .retrieveMono(DeviceAck.class);
~~~

Khi request được thực thi, JacksonJsonEncoder tuần tự hóa DeviceEvent thành JSON. Ở phía server, JacksonJsonDecoder tạo lại DeviceEvent để phương thức accept nhận được đối tượng đúng kiểu. Giá trị DeviceAck do handler trả về được mã hóa ở phía server, sau đó requester giải mã thành DeviceAck.

Với dữ liệu mẫu trên, đối tượng phản hồi có dạng:

~~~text
DeviceAck[deviceId=sensor-17, status=accepted]
~~~

Các đoạn mã trên là thành phần của ứng dụng Spring đã cấu hình transport, strategy và route; chúng không phải chương trình Java độc lập chỉ có thể chạy bằng javac. Trong test hoặc ứng dụng dòng lệnh có thể block để lấy kết quả, nhưng trong pipeline reactive nên trả Mono/Flux cho tầng gọi tiếp theo.

## 6. Cấu hình codec với Spring Boot

Khi dùng spring-boot-starter-rsocket, Boot tự cấu hình RSocketStrategies, RSocketMessageHandler và RSocketRequester.Builder phù hợp với các dependency hiện có.

Một server TCP độc lập có thể được cấu hình bằng application.properties:

~~~properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

Đối với WebFlux chạy trên Reactor Netty, có thể gắn RSocket qua WebSocket:

~~~properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
~~~

Trong trường hợp Boot đã tự cấu hình codec JSON/CBOR, không cần thêm Jackson codec lần nữa nếu cấu hình mặc định đáp ứng yêu cầu. Khi cần codec bổ sung, sử dụng RSocketStrategiesCustomizer:

~~~java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.codec.protobuf.ProtobufDecoder;
import org.springframework.http.codec.protobuf.ProtobufEncoder;

@Bean
RSocketStrategiesCustomizer protobufCodecs() {
    return strategies -> {
        strategies.encoder(new ProtobufEncoder());
        strategies.decoder(new ProtobufDecoder());
    };
}
~~~

Customizer bổ sung encoder và decoder Protobuf vào strategy mà Boot đang xây dựng. Có thể đặt thứ tự customizer bằng @Order nếu ứng dụng có nhiều customizer và thứ tự đăng ký cần được kiểm soát.

Boot cũng cung cấp RSocketRequester.Builder dưới dạng prototype bean. Mỗi điểm injection nhận một builder riêng vì builder có trạng thái cấu hình. Nên tạo requester từ builder được inject tại service cần kết nối, tránh tái sử dụng một builder đã cấu hình cho nhiều kết nối có thiết lập khác nhau.

## 7. Dùng Protocol Buffers làm định dạng payload

Protocol Buffers phù hợp khi cần schema rõ ràng, payload nhỏ và tương thích giữa nhiều ngôn ngữ. Spring Web cung cấp ProtobufEncoder và ProtobufDecoder để làm việc với các lớp Java được sinh từ file .proto.

Các lớp message được tạo bằng protoc và triển khai com.google.protobuf.Message. Dependency protobuf-java phải có mặt trong ứng dụng.

Đăng ký ProtobufEncoder và ProtobufDecoder trong RSocketStrategies hoặc bằng RSocketStrategiesCustomizer như ví dụ ở phần trước. Khi tạo requester, đặt data MIME type phù hợp:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.parseMimeType("application/x-protobuf"))
    .tcp("localhost", 7000);
~~~

ProtobufEncoder và ProtobufDecoder hỗ trợ application/x-protobuf và application/octet-stream. Với một giá trị đơn, Protobuf dùng định dạng message thông thường. Với Flux nhiều message, Spring dùng dạng delimited: kích thước từng message được ghi trước nội dung message để decoder tách đúng ranh giới phần tử.

ProtobufDecoder giới hạn kích thước message mặc định ở 256 KB. Có thể điều chỉnh bằng setMaxMessageSize(int) nếu yêu cầu ứng dụng cần giới hạn khác; nên chọn giới hạn có chủ đích để tránh nhận payload quá lớn. Không được giả định rằng một Flux Protobuf có thể được đọc như một message Protobuf đơn không có thông tin phân tách.

## 8. Tự xây dựng Encoder và Decoder

Khi định dạng dữ liệu không được Spring cung cấp sẵn, có thể triển khai org.springframework.core.codec.Encoder<T> và Decoder<T> riêng.

Một implementation cần đáp ứng các trách nhiệm chính:

1. Xác định kiểu Java và MIME type mà codec hỗ trợ trong canEncode hoặc canDecode.
2. Công bố danh sách MIME type hỗ trợ qua getEncodableMimeTypes hoặc getDecodableMimeTypes.
3. Chuyển đối tượng thành DataBuffer ở chiều encode; chuyển DataBuffer thành đối tượng ở chiều decode.
4. Xử lý lỗi định dạng, dữ liệu thiếu, dữ liệu không hợp lệ và kích thước payload.
5. Hỗ trợ đúng cả đường đi một giá trị và luồng nhiều giá trị nếu ứng dụng cần cả hai.

Đăng ký codec tùy chỉnh:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoder(new MoneyEncoder())
    .decoder(new MoneyDecoder())
    .build();
~~~

Tên MoneyEncoder và MoneyDecoder ở đây đại diện cho hai implementation do ứng dụng tự viết. Khi viết codec, hãy dùng DataBufferFactory được truyền vào để tạo buffer, không tự giả định một MIME type cho mọi payload. Codec phải kiểm tra MIME type thực tế và kiểu dữ liệu trước khi xử lý.

Không nên dùng Java native serialization cho payload qua mạng. Định dạng có schema hoặc định dạng chuẩn như JSON, CBOR và Protobuf dễ kiểm soát khả năng tương thích, giới hạn đầu vào và hỗ trợ nhiều ngôn ngữ hơn.

## 9. Metadata và codec của metadata

Metadata có thể mang route, token xác thực hoặc thông tin ngữ cảnh. RSocketRequester hỗ trợ thêm metadata cho một request bằng metadata(value, mimeType):

~~~java
import org.springframework.util.MimeType;

MimeType bearerMimeType =
    MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Mono<DeviceAck> response = requester.route("telemetry.accept")
    .metadata(accessToken, bearerMimeType)
    .data(event)
    .retrieveMono(DeviceAck.class);
~~~

Với composite metadata mặc định, mỗi mục metadata được đóng gói cùng MIME type riêng. Giá trị metadata cũng phải có Encoder phù hợp. Ở phía nhận, MetadataExtractor và các Decoder đã đăng ký được dùng để chuyển metadata thành giá trị ứng dụng hoặc header.

Route là một mục metadata theo định dạng routing của RSocket. Vì vậy, nếu đổi metadataMimeType sang định dạng khác, cần đảm bảo hai phía vẫn hiểu cách biểu diễn route và các mục metadata cần thiết. Trong phần lớn ứng dụng dùng route(...), hãy giữ composite metadata mặc định.

## 10. Quy trình chẩn đoán lỗi codec

Khi gặp lỗi encode/decode, kiểm tra lần lượt:

1. Kiểu Java của payload có được Encoder/Decoder hỗ trợ không?
2. Codec có được đăng ký trong RSocketStrategies đang thực sự được requester và responder sử dụng không?
3. dataMimeType trong SETUP có khớp định dạng codec của cả hai phía không?
4. Nếu payload là metadata, MIME type của từng metadata entry có đúng không và metadata extractor có giải mã mục đó không?
5. Hai đầu có dùng cùng schema, tên field, kiểu số, enum và quy tắc nullability không?
6. Có nhiều codec cùng hỗ trợ một kiểu và MIME type khiến thứ tự đăng ký chọn codec không mong muốn không?
7. Kích thước message hoặc cấu trúc payload có vượt giới hạn decoder không?

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| No encoder for ... | Chưa đăng ký Encoder phù hợp hoặc kiểu Java không được hỗ trợ | Thêm codec tương ứng và kiểm tra canEncode |
| No decoder for ... | Thiếu Decoder hoặc MIME type không được hỗ trợ | Đăng ký Decoder và kiểm tra canDecode với MIME type thực tế |
| DecodingException hoặc lỗi Jackson | Payload sai định dạng, DTO không tương thích hoặc hai đầu dùng schema khác nhau | Kiểm tra payload, kiểu DTO và cấu hình mapper |
| Kết nối thành công nhưng request lỗi khi gửi DTO | Chỉ có codec cơ bản String/byte[]/ByteBuffer | Thêm spring-web codec hoặc dùng Spring Boot starter |
| Server giải mã sai định dạng | dataMimeType của requester không khớp codec phía server | Đặt MIME type tường minh và thống nhất hai đầu |
| Metadata không được ánh xạ | Thiếu Decoder, MIME type của entry sai hoặc metadata extractor chưa đăng ký | Kiểm tra composite metadata và cấu hình extractor |
| Protobuf stream bị lỗi phân tách | Flux được gửi/đọc như message đơn thay vì delimited message | Dùng ProtobufEncoder/Decoder tương thích và kiểm tra dạng stream |
| Payload lớn bị từ chối | Giới hạn message của decoder bị vượt quá | Điều chỉnh giới hạn phù hợp và kiểm soát kích thước đầu vào |

## 11. Kiểm thử và checklist triển khai

Một bài kiểm thử tích hợp nên kiểm tra ít nhất:

- Gửi một DTO và nhận lại đúng kiểu phản hồi.
- Gửi nhiều phần tử nếu route hỗ trợ streaming.
- Kiểm tra JSON hoặc CBOR được giải mã đúng ở cả hai chiều.
- Kiểm tra codec tùy chỉnh hoặc Protobuf với đúng MIME type.
- Gửi payload có field thiếu, field không hợp lệ hoặc kiểu không tương thích để xác nhận lỗi được xử lý.
- Kiểm tra metadata route và metadata nghiệp vụ.
- Kiểm tra payload vượt giới hạn cấu hình.
- Kiểm tra client và server có cùng schema và cấu hình codec cần thiết.

Checklist trước khi triển khai:

1. Chọn định dạng dữ liệu và MIME type rõ ràng.
2. Xác nhận dependency cung cấp Encoder/Decoder tương ứng.
3. Đăng ký cả Encoder và Decoder trong RSocketStrategies.
4. Dùng cùng cấu hình strategy cho requester và responder khi có thể.
5. Đặt dataMimeType tường minh nếu kết nối có nhiều định dạng hoặc thứ tự decoder có thể thay đổi.
6. Giữ metadataMimeType phù hợp với routing/composite metadata.
7. Xác định giới hạn kích thước payload và validate dữ liệu nhận vào.
8. Chạy kiểm thử round-trip trên kết nối RSocket thực tế.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocketStrategies — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [JacksonJsonEncoder — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/json/JacksonJsonEncoder.html)
- [JacksonJsonDecoder — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/json/JacksonJsonDecoder.html)
- [ProtobufEncoder — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/protobuf/ProtobufEncoder.html)
- [ProtobufDecoder — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/protobuf/ProtobufDecoder.html)
- [RSocketStrategiesCustomizer — Spring Boot API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/rsocket/messaging/RSocketStrategiesCustomizer.html)

## Ghi chú tương thích phiên bản

Tên một số codec Jackson thay đổi giữa các dòng Spring Framework:

- Spring Framework 6.x dùng Jackson 2, ví dụ Jackson2JsonEncoder, Jackson2JsonDecoder, Jackson2CborEncoder và Jackson2CborDecoder.
- Spring Framework 7.x chuyển sang Jackson 3, dùng JacksonJsonEncoder, JacksonJsonDecoder, JacksonCborEncoder và JacksonCborDecoder. Các codec Jackson2 cũ bị deprecated từ Spring Framework 7.0.

Hãy dùng class name và dependency phù hợp với phiên bản Spring Framework/Spring Boot của dự án. Không trộn Jackson 2 và Jackson 3 codec trong cùng ví dụ cấu hình nếu chưa có chủ đích tương thích rõ ràng.
