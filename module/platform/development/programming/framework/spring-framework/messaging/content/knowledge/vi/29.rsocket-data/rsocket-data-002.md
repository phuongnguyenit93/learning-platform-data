# Codec cho chuỗi, dữ liệu nhị phân và đối tượng JSON

## 1. Codec trong RSocket làm nhiệm vụ gì?

RSocket truyền payload dưới dạng dữ liệu nhị phân. Ở tầng ứng dụng, client và server thường làm việc với các kiểu Java như String, byte[], ByteBuffer hoặc DTO. **Codec** là thành phần chuyển đổi giữa đối tượng Java và phần data dạng byte của RSocket payload:

- Encoder chuyển giá trị Java thành byte để gửi đi.
- Decoder đọc byte nhận được và tạo lại giá trị Java.
- MIME type mô tả định dạng của data để hai phía chọn cách mã hóa và giải mã phù hợp.

Ví dụ, cùng một nội dung có thể được biểu diễn theo nhiều cách. Chuỗi "hello" có thể là các byte UTF-8 thuần trong text/plain hoặc là JSON string có dấu ngoặc kép trong application/json. Một đối tượng User có thể được tuần tự hóa thành JSON. Một file ảnh có thể được truyền dưới dạng byte thô mà không cần chuyển thành JSON.

RSocket không tự hiểu cấu trúc của DTO Java. Hai phía phải thống nhất MIME type và có encoder/decoder tương thích. Nếu client gửi JSON nhưng server lại giải mã như dữ liệu nhị phân hoặc text thuần, kết quả sẽ không đúng với hợp đồng ứng dụng.

## 2. MIME type và RSocketStrategies

Một kết nối RSocket khai báo data MIME type và metadata MIME type trong quá trình SETUP. Data MIME type cho biết cách diễn giải phần data của payload trên kết nối. Ví dụ thường gặp:

| MIME type | Ý nghĩa | Dữ liệu thường dùng |
|---|---|---|
| text/plain | Văn bản thuần | String |
| application/octet-stream | Byte nhị phân | byte[], ByteBuffer |
| application/json | JSON | DTO, record, Map, List |

Trong Spring, **RSocketStrategies** tập hợp các thành phần phục vụ việc xử lý payload, gồm encoder, decoder, metadata extractor và route matcher. Khi gửi một object qua RSocketRequester, Spring chọn encoder phù hợp với kiểu Java và MIME type. Khi nhận phản hồi hoặc xử lý payload ở server, Spring tìm decoder tương ứng.

Spring có các codec nền tảng cho những kiểu đơn giản và nhị phân phổ biến như String, byte[], ByteBuffer và DataBuffer. Để chuyển DTO thành JSON, cần đăng ký codec JSON, thường là Jackson.

Một cấu hình chiến lược có hỗ trợ JSON:

~~~java
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;

RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
    .build();
~~~

Jackson2JsonEncoder và Jackson2JsonDecoder thuộc Spring Web và sử dụng Jackson 2. Ứng dụng cần có dependency Jackson tương ứng trên classpath. Với Spring Boot, hãy bảo đảm các dependency cần thiết được đưa vào ứng dụng; nếu đã có cấu hình RSocketStrategies tự động hoặc tùy chỉnh, kiểm tra danh sách codec thực tế trước khi thêm codec trùng lặp.

Ở client, có thể gắn chiến lược vào RSocketRequester.Builder và khai báo data MIME type:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.parseMimeType("application/json"))
    .tcp("localhost", 7000);
~~~

Ở server, đăng ký RSocketStrategies để RSocketMessageHandler sử dụng. Trong cấu hình Spring, có thể khai báo bean:

~~~java
@Bean
RSocketStrategies rSocketStrategies() {
    return RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .build();
}
~~~

Nếu tự tạo RSocketMessageHandler thay vì dùng cấu hình tự động, cần gắn RSocketStrategies vào handler theo cấu hình của ứng dụng. Client và server phải có codec phù hợp với định dạng mà kết nối sử dụng.

## 3. Truyền chuỗi với text/plain

Với dữ liệu văn bản thuần, kiểu Java thường dùng là String. Codec chuỗi chuyển nội dung thành byte theo charset, thường là UTF-8, và decoder chuyển byte nhận được thành String.

Client:

~~~java
RSocketRequester textRequester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.parseMimeType("text/plain"))
    .tcp("localhost", 7000);

Mono<String> reply = textRequester
    .route("text.echo")
    .data("Xin chào RSocket")
    .retrieveMono(String.class);
~~~

Server:

~~~java
@Controller
class TextController {

    @MessageMapping("text.echo")
    Mono<String> echo(@Payload String message) {
        return Mono.just(message);
    }
}
~~~

Ví dụ trên giả định server đã cấu hình RSocketMessageHandler và các codec nền tảng cho chuỗi. Client gửi một String, Spring mã hóa nó thành data của request; server giải mã thành String, xử lý rồi mã hóa String trả về.

**text/plain** biểu diễn văn bản thuần. Nội dung "hello" được truyền dưới dạng byte văn bản, không có cấu trúc JSON. Nếu ứng dụng cần gửi chuỗi nhưng kết nối được cấu hình với application/json và Jackson JSON codec, chuỗi sẽ được biểu diễn theo quy tắc JSON, thường là một JSON string có dấu ngoặc kép. Vì vậy, cần thống nhất MIME type và cách biểu diễn ở hai phía.

Không nên tự chuyển String sang byte[] rồi lại giả định decoder sẽ tự hiểu nội dung. Nếu chọn byte[] thì kiểu nhận cũng phải là byte[] hoặc phải có bước giải mã ký tự rõ ràng, với charset được thống nhất.

## 4. Truyền dữ liệu nhị phân với byte[] và ByteBuffer

Với ảnh, file, nội dung nén hoặc dữ liệu nhị phân khác, có thể dùng byte[] hoặc ByteBuffer. Các kiểu này giữ nguyên byte và không cần chuyển dữ liệu thành chuỗi.

Ví dụ client gửi và nhận byte[]:

~~~java
RSocketRequester binaryRequester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.parseMimeType("application/octet-stream"))
    .tcp("localhost", 7000);

byte[] imageBytes = loadImageBytes();

Mono<byte[]> stored = binaryRequester
    .route("files.store")
    .data(imageBytes)
    .retrieveMono(byte[].class);
~~~

Phía server:

~~~java
@Controller
class FileController {

    @MessageMapping("files.store")
    Mono<byte[]> store(@Payload byte[] content) {
        // Kiểm tra và lưu content bằng dịch vụ lưu trữ của ứng dụng.
        return Mono.just(content);
    }
}
~~~

Đây là ví dụ echo để minh họa codec byte[]. Trong ứng dụng thực tế, không nên mặc định trả lại toàn bộ file nếu nghiệp vụ chỉ cần trả về mã lưu trữ hoặc trạng thái xử lý. Hãy kiểm tra kích thước, quyền truy cập và loại file trước khi lưu.

**application/octet-stream** thể hiện dữ liệu nhị phân tổng quát. ByteArrayEncoder/ByteArrayDecoder có thể chuyển đổi byte[] trực tiếp. Nếu dùng ByteBuffer, dữ liệu cần được đọc theo vùng còn lại từ position đến limit; hãy chú ý position có thể thay đổi khi buffer được đọc. Khi cần giữ dữ liệu gốc để dùng lại, có thể tạo duplicate hoặc slice phù hợp thay vì chia sẻ một buffer đã bị tiêu thụ.

Spring cũng hỗ trợ DataBuffer cho các tình huống xử lý dữ liệu ở tầng thấp. DataBuffer phù hợp khi cần tích hợp với API reactive của Spring, nhưng khi tự thao tác buffer, phải quản lý vòng đời và giải phóng buffer đúng cách nếu loại buffer yêu cầu release. Với trường hợp thông thường, byte[] hoặc ByteBuffer dễ hiểu và dễ kiểm soát hơn.

## 5. Truyền đối tượng Java dưới dạng JSON

DTO là lựa chọn thuận tiện khi request hoặc response có nhiều trường mang ý nghĩa nghiệp vụ. JSON codec dùng Jackson để tuần tự hóa object thành JSON và giải mã JSON thành object tương ứng.

Ví dụ DTO:

~~~java
public record Greeting(String message, String sender) {}
~~~

Client gửi DTO và nhận DTO:

~~~java
RSocketRequester jsonRequester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.parseMimeType("application/json"))
    .tcp("localhost", 7000);

Mono<Greeting> reply = jsonRequester
    .route("greeting.echo")
    .data(new Greeting("Xin chào", "client-01"))
    .retrieveMono(Greeting.class);
~~~

Server xử lý:

~~~java
@Controller
class GreetingController {

    @MessageMapping("greeting.echo")
    Mono<Greeting> echo(@Payload Greeting greeting) {
        return Mono.just(greeting);
    }
}
~~~

Khi gửi request, Jackson2JsonEncoder chuyển Greeting thành JSON. Khi server nhận payload, Jackson2JsonDecoder tạo lại đối tượng Greeting. Chiều phản hồi cũng sử dụng codec JSON để chuyển DTO về client.

Ví dụ JSON tương ứng có dạng:

~~~json
{
  "message": "Xin chào",
  "sender": "client-01"
}
~~~

Cấu trúc JSON thực tế phụ thuộc cấu hình ObjectMapper, naming strategy, annotation và các module Jackson được đăng ký. Hai phía cần thống nhất tên trường, kiểu dữ liệu, quy tắc ngày giờ, enum và cách xử lý trường thiếu hoặc null. DTO không nhất thiết phải giống nhau hoàn toàn về class Java, nhưng cấu trúc JSON trao đổi phải tương thích.

Jackson hỗ trợ record trong các phiên bản hiện đại. Với class thông thường, cần có constructor hoặc cơ chế tạo đối tượng mà Jackson có thể sử dụng, cùng getter/setter hoặc cấu hình phù hợp. Nếu DTO có kiểu đặc biệt như LocalDateTime, UUID hoặc kiểu thư viện bên ngoài, hãy đăng ký Jackson module cần thiết và kiểm tra định dạng thực tế.

## 6. Phân biệt JSON string và văn bản thuần

Một lỗi dễ gặp là cho rằng String luôn được truyền giống nhau dù MIME type là gì.

Với text/plain, chuỗi:

~~~text
hello
~~~

được truyền như văn bản thuần. Với application/json, một String được mã hóa theo cú pháp JSON sẽ có dạng:

~~~json
"hello"
~~~

Dấu ngoặc kép là một phần của biểu diễn JSON. Nếu server nhận JSON nhưng dùng cách đọc văn bản thuần, nội dung có thể bao gồm cả dấu ngoặc kép hoặc không được xử lý như mong đợi.

Tương tự, byte[] trong application/octet-stream là byte thô. Nếu byte[] được tuần tự hóa thành JSON bằng Jackson, nó có thể được biểu diễn thành chuỗi Base64. Hai cách biểu diễn có mục đích khác nhau:

- Dùng application/octet-stream và codec byte[] khi cần truyền byte nguyên trạng.
- Dùng application/json khi muốn biểu diễn dữ liệu theo cấu trúc JSON.
- Dùng text/plain khi nội dung chỉ là văn bản thuần.

Không chọn MIME type chỉ dựa vào kiểu Java. Hãy xét định dạng trên wire mà client và server đã thống nhất.

## 7. Một kết nối và lựa chọn MIME type

Data MIME type được khai báo trong SETUP của kết nối RSocket. Do đó, không nên nghĩ rằng chỉ cần đổi route là có thể tự động đổi định dạng data từ text/plain sang application/json hoặc application/octet-stream.

Nếu ứng dụng cần các nhóm payload có định dạng khác nhau, hãy thiết kế hợp đồng kết nối rõ ràng. Các lựa chọn thường gặp:

1. Dùng một định dạng thống nhất, chẳng hạn JSON, cho DTO và các request nghiệp vụ trên một kết nối.
2. Dùng các kết nối riêng với data MIME type phù hợp cho luồng văn bản, nhị phân hoặc JSON.
3. Nếu cần một payload mang nhiều kiểu nội dung, thiết kế envelope hoặc metadata theo một hợp đồng rõ ràng và cấu hình cơ chế giải mã tương ứng; không tự suy đoán định dạng chỉ từ route.

Metadata MIME type là cấu hình riêng với data MIME type. Route metadata cũng không phải data payload. Ví dụ setupRoute hoặc requester.route xác định đích xử lý, trong khi codec và data MIME type xác định cách chuyển đổi phần data.

## 8. Dùng JSON với danh sách và kiểu generic

JSON codec có thể chuyển đổi collection và DTO lồng nhau. Ví dụ server trả về danh sách User:

~~~java
record User(Long id, String name) {}

@MessageMapping("users.all")
Mono<List<User>> allUsers() {
    return userService.findAll().collectList();
}
~~~

Client có thể nhận với kiểu tham chiếu generic:

~~~java
Mono<List<User>> users = requester
    .route("users.all")
    .retrieveMono(
        new ParameterizedTypeReference<List<User>>() {}
    );
~~~

ParameterizedTypeReference giữ lại thông tin kiểu generic ở runtime để Spring biết cấu trúc cần giải mã. Nếu chỉ truyền List.class, thông tin kiểu phần tử User không được thể hiện đầy đủ. JSON codec vẫn chịu trách nhiệm chuyển JSON thành object; ParameterizedTypeReference chỉ mô tả kiểu đích.

Với response là một object đơn giản, dùng retrieveMono(User.class). Với collection hoặc kiểu lồng nhau, dùng ParameterizedTypeReference tương ứng. Kiểu Java phía client phải khớp với cấu trúc JSON mà server thực sự trả về.

## 9. Truyền dữ liệu lớn và luồng nhị phân

Không nên luôn đọc toàn bộ file lớn vào byte[] rồi gửi trong một request. Cách đó làm tăng mức sử dụng bộ nhớ và có thể tạo áp lực lên heap khi nhiều client tải lên cùng lúc.

Với dữ liệu lớn, cân nhắc chia thành các chunk và dùng mô hình streaming hoặc channel của RSocket. Reactive Streams cung cấp backpressure để bên nhận kiểm soát tốc độ tiêu thụ dữ liệu. Hãy xác định rõ:

- Kích thước chunk và giới hạn tổng dung lượng.
- Thứ tự chunk, mã phiên truyền và cách phát hiện chunk thiếu/trùng.
- Cách xác nhận hoàn tất, retry và hủy truyền.
- Giới hạn frame, timeout và tài nguyên lưu tạm.
- Cách giải phóng buffer và xử lý lỗi giữa luồng.

RSocket có thể phân mảnh payload theo giới hạn transport/protocol, nhưng điều đó không thay thế thiết kế streaming cho file rất lớn. Phân mảnh frame không đồng nghĩa ứng dụng đã có cơ chế quản lý file theo chunk, tiếp tục truyền hoặc xác nhận lưu trữ.

## 10. Lỗi codec thường gặp và cách khắc phục

- **UnsupportedMediaTypeException hoặc không tìm thấy encoder:** kiểm tra MIME type, kiểu Java và danh sách encoder đã đăng ký trong RSocketStrategies.
- **Không giải mã được JSON:** kiểm tra JSON đầu vào, Jackson dependency, decoder và cấu hình ObjectMapper.
- **Client nhận Map thay vì DTO:** kiểm tra kiểu đích khi gọi retrieveMono/retrieveFlux; với generic, dùng ParameterizedTypeReference.
- **Chuỗi có dấu ngoặc kép ngoài ý muốn:** kiểm tra kết nối đang dùng text/plain hay application/json và encoder nào được chọn.
- **byte[] bị biến thành Base64:** kiểm tra dữ liệu đang được mã hóa như JSON hay byte nhị phân. Dùng application/octet-stream cho byte thô.
- **Dữ liệu tiếng Việt bị lỗi:** thống nhất charset và MIME type; text/plain thường dùng UTF-8. Với JSON, kiểm tra encoding và cấu hình Jackson.
- **DTO có trường null hoặc thiếu:** đối chiếu JSON thực tế, constructor, getter/setter, record component và cấu hình Jackson.
- **Một phía dùng JSON, phía kia dùng octet-stream:** thống nhất data MIME type của kết nối và cấu hình codec tương ứng ở cả hai phía.
- **Lỗi chỉ xảy ra với file lớn:** kiểm tra kích thước payload, giới hạn frame, timeout, backpressure và việc có giữ toàn bộ file trong bộ nhớ hay không.

Khi debug, nên kiểm tra payload thực tế ở dạng byte hoặc JSON đã che thông tin nhạy cảm, MIME type của kết nối, codec được chọn và kiểu Java tại điểm gửi/nhận. Không log nội dung bí mật, token, dữ liệu cá nhân hoặc toàn bộ file chỉ để tìm lỗi codec.

## 11. Bảng chọn codec nhanh

| Mục đích | Kiểu Java | Data MIME type | Codec phù hợp |
|---|---|---|---|
| Gửi văn bản thuần | String | text/plain | CharSequenceEncoder / StringDecoder |
| Gửi byte thô | byte[] | application/octet-stream | ByteArrayEncoder / ByteArrayDecoder |
| Dùng NIO buffer | ByteBuffer | application/octet-stream | ByteBufferEncoder / ByteBufferDecoder |
| Trao đổi DTO | DTO / record | application/json | Jackson2JsonEncoder / Jackson2JsonDecoder |
| Trao đổi collection generic | List<T>, DTO lồng nhau | application/json | Jackson JSON codec + ParameterizedTypeReference khi nhận |

Tên codec là những thành phần thường dùng trong hệ codec của Spring; việc chọn thực tế phụ thuộc MIME type, thứ tự đăng ký và kiểu dữ liệu. Nếu ứng dụng có custom codec, hãy kiểm tra khả năng canEncode/canDecode của codec đó.

## 12. Ghi nhớ

Codec là cầu nối giữa kiểu Java và byte payload của RSocket. Dùng text/plain cho văn bản thuần, application/octet-stream cho byte nhị phân và application/json cho DTO/record được Jackson tuần tự hóa. RSocketStrategies quản lý encoder, decoder và các thành phần xử lý liên quan; RSocketRequester sử dụng chiến lược đó khi gửi và nhận dữ liệu.

Client và server phải thống nhất data MIME type, cấu trúc dữ liệu và codec tương thích. Khi có lỗi, hãy kiểm tra định dạng thực tế trên wire, MIME type, encoder/decoder và kiểu đích. Với payload lớn, thiết kế streaming và backpressure thay vì mặc định gom toàn bộ dữ liệu vào bộ nhớ.
