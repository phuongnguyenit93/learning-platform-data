# Tương thích hợp đồng khi thay đổi codec, route hoặc kiểu dữ liệu

Trong Spring Messaging với RSocket, hợp đồng giao tiếp không chỉ là một DTO Java. Mỗi request phụ thuộc đồng thời vào route dùng để định tuyến, cách mã hóa payload, kiểu dữ liệu mà hai đầu mong đợi và mô hình tương tác RSocket. Một thay đổi nhỏ ở một lớp có thể khiến client cũ không gọi được handler, không giải mã được payload hoặc hiểu sai ý nghĩa dữ liệu.

Mục tiêu của quản lý tương thích là cho phép client và server được nâng cấp ở các thời điểm khác nhau mà vẫn trao đổi đúng dữ liệu. Muốn làm được điều đó, cần xác định rõ phần nào của hợp đồng đang thay đổi, phân loại mức độ tương thích và triển khai theo từng giai đoạn.

## 1. Hợp đồng RSocket gồm những phần nào?

Một message RSocket có phần **data** và phần **metadata**. Metadata có thể chứa route, thông tin xác thực hoặc dữ liệu phụ trợ. Data thường chứa payload nghiệp vụ. Hai phần này có thể dùng định dạng khác nhau.

Có bốn phần cần quản lý:

1. **Route:** tên đích mà requester gửi trong metadata và responder dùng để tìm handler. Ví dụ: **orders.submit.v1**.
2. **Codec và MIME type:** cách chuyển object thành byte và giải mã byte trở lại object. Ví dụ JSON, CBOR hoặc Protobuf.
3. **Schema của payload:** tên trường, kiểu dữ liệu, trường bắt buộc, giá trị mặc định, ý nghĩa và quy tắc null.
4. **Mô hình tương tác:** Request-Response, Request-Stream, Channel hoặc Fire-and-Forget. Thay đổi từ một kết quả đơn sang một luồng kết quả cũng là thay đổi hợp đồng.

Route không phải là một trường trong JSON payload. Route thường nằm trong routing metadata. Vì vậy, sửa DTO không tự động đổi route và đổi route cũng không tự động thay đổi schema payload.

RSocket khai báo MIME type cho data và metadata trong frame SETUP của kết nối. Các MIME type này áp dụng cho những request trên kết nối đó. Đây là điểm quan trọng khi triển khai thay đổi codec: hai phía phải thống nhất cách mã hóa và giải mã trên từng kết nối.

## 2. Phân loại thay đổi theo mức độ tương thích

| Thay đổi | Rủi ro | Cách xử lý |
|---|---|---|
| Thêm trường tùy chọn | Thường tương thích nếu consumer cũ chấp nhận trường lạ và consumer mới xử lý được khi trường vắng mặt | Giữ trường mới là optional, quy định default rõ ràng |
| Thêm trường bắt buộc | Có thể làm consumer mới từ chối payload cũ | Chỉ bật yêu cầu sau khi mọi producer đã gửi trường |
| Đổi tên hoặc xóa trường | Breaking change | Duy trì alias hoặc DTO phiên bản cũ trong giai đoạn chuyển đổi |
| Đổi kiểu dữ liệu | Breaking change nếu cách biểu diễn hoặc miền giá trị không tương thích | Tạo phiên bản schema mới và chuyển đổi rõ ràng |
| Đổi ý nghĩa của trường | Nguy hiểm vì payload vẫn giải mã được nhưng nghiệp vụ sai | Tạo trường mới hoặc phiên bản hợp đồng mới |
| Thêm giá trị enum | Có thể làm consumer cũ lỗi nếu xử lý enum đóng | Có nhánh fallback cho giá trị chưa biết |
| Đổi route | Client gọi route cũ có thể không tìm thấy handler | Giữ route cũ như alias trong thời gian migration |
| Đổi JSON sang CBOR hoặc Protobuf | Hai đầu có thể không giải mã được cùng byte payload | Thống nhất MIME type, codec và kế hoạch chuyển kết nối |
| Đổi Request-Response sang Stream | Thay đổi kiểu trả về, vòng đời và cách tiêu thụ dữ liệu | Xem đây là hợp đồng mới và kiểm thử riêng |

Một thay đổi chỉ được coi là tương thích khi cả producer lẫn consumer thực tế đều xử lý được nó. Không nên kết luận rằng “thêm trường luôn an toàn” nếu chưa kiểm tra cấu hình giải mã trường không xác định, quy tắc null và hành vi của các client đang chạy.

## 3. Giữ tương thích khi đổi route

Trong Spring, responder RSocket thường khai báo handler bằng **@MessageMapping**. Requester chỉ định route qua **RSocketRequester.route(...)**.

~~~java
@Controller
class OrderRSocketController {

    @MessageMapping("orders.submit.v1")
    Mono<Receipt> submitV1(OrderSubmitV1 request) {
        return orderService.submit(request);
    }
}
~~~

Requester gọi đúng route đã thỏa thuận:

~~~java
Mono<Receipt> response = requester
    .route("orders.submit.v1")
    .data(request)
    .retrieveMono(Receipt.class);
~~~

Nếu đổi route từ **orders.submit** sang **orders.create**, client cũ vẫn gửi **orders.submit**. Handler mới chỉ nhận route mới sẽ không tự động tương thích với client cũ.

Có thể duy trì hai route trong giai đoạn chuyển đổi và dùng chung logic nghiệp vụ:

~~~java
@Controller
class OrderRSocketController {

    @MessageMapping("orders.submit")
    Mono<Receipt> submitLegacy(OrderSubmitV1 request) {
        return orderService.submit(request);
    }

    @MessageMapping("orders.create.v2")
    Mono<Receipt> createV2(OrderSubmitV2 request) {
        return orderService.submit(toCommand(request));
    }
}
~~~

Cách này giúp route cũ và route mới cùng tồn tại trong lúc các client được nâng cấp. Sau khi đo lường xác nhận không còn traffic trên route cũ, mới loại bỏ handler cũ.

Spring dùng route matcher để tìm handler. **SimpleRouteMatcher** mặc định dựa trên **AntPathMatcher**; nếu có **spring-web**, có thể cấu hình **PathPatternRouteMatcher**. Route RSocket có thể phân cấp và mặc định dùng dấu chấm làm ký tự phân cách. Chúng không phải URL path: không nên áp dụng suy luận về URL decoding hoặc dấu gạch chéo của HTTP cho route RSocket.

Khi thiết kế route, nên:

- Dùng tên ổn định, mô tả hành động hoặc capability.
- Chỉ thêm phiên bản vào route khi cần một hợp đồng major mới, ví dụ **orders.create.v2**.
- Giữ route cũ trong thời gian chuyển đổi.
- Kiểm thử cả route chính xác, route pattern và biến route nếu ứng dụng có sử dụng.
- Không dùng route như nơi chứa dữ liệu nghiệp vụ dài hoặc bí mật.

## 4. Giữ tương thích khi thay đổi codec và MIME type

Codec quyết định cách object được tuần tự hóa thành byte. Decoder ở phía nhận phải hiểu đúng định dạng byte đó. Ví dụ, một client mã hóa object thành JSON nhưng server đang giải mã theo CBOR sẽ không thể xử lý payload như mong đợi.

Trong Spring, **RSocketStrategies** tập hợp encoder, decoder và route matcher. Các codec cơ bản từ **spring-core** hỗ trợ **String**, **byte[]** và **ByteBuffer**. Khi có **spring-web**, ứng dụng có thể đăng ký thêm codec JSON, CBOR hoặc Protobuf.

Ví dụ cấu hình CBOR theo API Spring hiện hành:

~~~java
@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
        .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
        .routeMatcher(new PathPatternRouteMatcher())
        .build();
}
~~~

Có thể dùng cùng cấu hình chiến lược cho requester và responder để giảm nguy cơ hai phía đăng ký codec khác nhau. Trong ứng dụng thực tế, cần kiểm tra tên lớp codec tương ứng với phiên bản Spring đang sử dụng.

Requester có thể khai báo MIME type của data khi thiết lập kết nối:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeType.valueOf("application/cbor"))
    .rsocketStrategies(rsocketStrategies)
    .tcp("localhost", 7000);
~~~

Cần phân biệt:

- **Data MIME type** mô tả định dạng payload nghiệp vụ.
- **Metadata MIME type** mô tả định dạng metadata. Composite metadata cho phép nhiều mục metadata có định dạng riêng, ví dụ routing và authentication.
- **Encoder** được dùng khi gửi object; **Decoder** được dùng khi nhận object. Client và server cần có các cặp encoder/decoder tương thích cho cả request lẫn response.

Vì data MIME type được công bố ở SETUP và áp dụng cho kết nối, không nên đổi cấu hình codec của một phía rồi giả định các kết nối đang mở sẽ tự chuyển sang định dạng mới. Khi đổi MIME type, hãy tạo kết nối theo cấu hình mới và bảo đảm peer hỗ trợ định dạng tương ứng. Nếu cần chạy song song nhiều định dạng, hãy tổ chức các kết nối hoặc endpoint theo cách có thể phân biệt và theo dõi được.

Một số nguyên tắc khi đổi codec:

1. Xác định MIME type hiện tại và MIME type đích ở cả requester lẫn responder.
2. Đăng ký decoder trước khi bắt đầu gửi payload theo định dạng mới.
3. Nếu MIME type thay đổi ở cấp kết nối, thiết lập kết nối mới với cấu hình tương ứng.
4. Kiểm thử cả chiều request và response; hai chiều có thể dùng object và codec khác nhau.
5. Không phụ thuộc ngầm vào thứ tự codec đăng ký để chọn MIME type mặc định. Nếu cần tính ổn định, khai báo MIME type rõ ràng.
6. Giữ khả năng đọc định dạng cũ trong giai đoạn migration nếu vẫn còn client cũ.

## 5. Thay đổi schema và kiểu dữ liệu an toàn

Schema là phần mô tả cấu trúc và ý nghĩa của payload. Với JSON, tên trường và cách biểu diễn giá trị thường quyết định khả năng tương thích. Với định dạng nhị phân như Protobuf, số hiệu field và quy tắc tiến hóa schema cũng là một phần của hợp đồng.

### Thêm trường tùy chọn

Giả sử payload cũ có ba trường:

~~~json
{
  "orderId": "O-100",
  "amount": 125000,
  "currency": "VND"
}
~~~

Phiên bản mới muốn thêm trường **channel**:

~~~json
{
  "orderId": "O-100",
  "amount": 125000,
  "currency": "VND",
  "channel": "MOBILE"
}
~~~

Đây có thể là thay đổi tương thích nếu consumer cũ chấp nhận trường không biết và consumer mới vẫn xử lý payload cũ không có **channel**. Tuy nhiên, hành vi với trường lạ phụ thuộc cấu hình Jackson và codec cụ thể; phải kiểm thử bằng cấu hình thật của ứng dụng.

Nếu trường mới vắng mặt, ứng dụng cần quy định giá trị mặc định ở ranh giới chuyển đổi DTO sang model nghiệp vụ:

~~~java
String channel = request.channel() == null
    ? "WEB"
    : request.channel();
~~~

Không nên để default vô tình phụ thuộc vào giá trị mặc định của kiểu Java. Ví dụ, trường số nguyên primitive bị thiếu có thể mang giá trị **0**, trong khi **0** có thể là một giá trị nghiệp vụ hợp lệ. Dùng kiểu nullable hoặc kiểm tra bắt buộc để phân biệt “không được gửi” với “được gửi bằng 0”.

### Đổi tên trường

Đổi **customerId** thành **buyerId** có thể làm client cũ và server mới không còn hiểu cùng một payload. Nếu dùng Jackson, có thể dùng alias để chấp nhận tên cũ trong thời gian chuyển đổi:

~~~java
record OrderRequest(
    @JsonAlias("customerId") String buyerId
) {}
~~~

Alias giúp decoder nhận cả tên cũ và tên mới; cần kiểm tra riêng tên được encoder phát ra để bảo đảm producer mới gửi đúng định dạng đã thống nhất. Khi tất cả producer đã chuyển sang tên mới, có thể bỏ alias trong một phiên bản major sau.

### Đổi kiểu hoặc ý nghĩa trường

Các thay đổi sau cần được coi là breaking change trừ khi có một quy tắc chuyển đổi đã được kiểm chứng:

- **amount** từ số nguyên sang chuỗi.
- **createdAt** từ epoch milliseconds sang ISO-8601.
- **quantity** từ đơn vị chiếc sang đơn vị thùng.
- Trường nullable chuyển thành bắt buộc.
- Một enum được mở rộng nhưng consumer cũ từ chối giá trị chưa biết.

Tên trường giữ nguyên không có nghĩa là hợp đồng vẫn tương thích. Ý nghĩa, đơn vị đo, miền giá trị, timezone và quy tắc làm tròn cũng là một phần của schema.

Với Protobuf, không tái sử dụng số hiệu field đã bị xóa; hãy đánh dấu số hiệu và tên cũ là reserved theo quy tắc của Protobuf. Với JSON, hãy quy định rõ cách xử lý trường không xác định, giá trị null và giá trị enum mới.

### Tách DTO theo phiên bản

Khi thay đổi không thể tương thích, dùng DTO riêng giúp giữ rõ ranh giới giữa hai hợp đồng:

~~~java
record OrderSubmitV1(
    String orderId,
    BigDecimal amount,
    String currency
) {}

record OrderSubmitV2(
    String orderId,
    BigDecimal amount,
    String currency,
    String channel
) {}
~~~

Chuyển DTO về một command hoặc domain model nội bộ trước khi gọi nghiệp vụ. Nhờ đó, logic nghiệp vụ không phải phụ thuộc vào việc client đang dùng phiên bản payload nào.

## 6. Quy trình migration không làm gián đoạn client

Một quy trình triển khai an toàn có thể chia thành các bước sau:

1. **Kiểm kê hợp đồng đang chạy:** ghi lại route, MIME type, schema payload, mô hình tương tác và phiên bản client. Xác định consumer nào còn dùng route hoặc codec cũ.
2. **Mở rộng phía nhận:** triển khai handler hoặc decoder có thể tiếp nhận định dạng cũ và mới. Nếu thay MIME type ở cấp kết nối, chuẩn bị cấu hình/kết nối mới thay vì thay đổi ngầm kết nối đang hoạt động.
3. **Giữ route cũ:** thêm route mới nhưng tiếp tục phục vụ route cũ. Nếu schema mới không tương thích, dùng DTO mới và chuyển đổi về model nội bộ.
4. **Chuyển producer từng đợt:** nâng cấp client theo nhóm, có thể dùng cấu hình hoặc feature flag để kiểm soát thời điểm chuyển.
5. **Theo dõi traffic:** đếm request theo route, MIME type, phiên bản payload và phiên bản client. Theo dõi lỗi route không tồn tại, lỗi giải mã và lỗi xác thực dữ liệu.
6. **Ngừng hợp đồng cũ:** chỉ xóa route, decoder hoặc DTO cũ khi số liệu xác nhận không còn consumer cần chúng và thời gian hỗ trợ đã kết thúc.

Nếu thay đổi chỉ là bổ sung trường tùy chọn, có thể giữ route và MIME type. Nếu thay đổi codec, phải xử lý tương thích MIME type. Nếu thay đổi cấu trúc hoặc ý nghĩa payload theo cách breaking, nên tạo phiên bản hợp đồng mới. Không nên gộp cả ba loại thay đổi vào một lần phát hành nếu không có lý do rõ ràng.

## 7. Kiểm thử hợp đồng

Unit test cho DTO không đủ để chứng minh hai ứng dụng RSocket tương thích. Cần kiểm thử ở ranh giới requester-responder bằng đúng codec, MIME type, route matcher và cấu hình Jackson/Protobuf của môi trường chạy.

Ma trận tối thiểu nên có:

| Producer | Consumer | Điều cần xác nhận |
|---|---|---|
| Client cũ | Server mới | Route cũ còn hoạt động; payload cũ vẫn giải mã được |
| Client mới | Server cũ | Chỉ kỳ vọng pass nếu thay đổi đã được thiết kế backward-compatible |
| Client mới | Server mới | Route, MIME type, schema và response mới khớp nhau |
| Payload thiếu trường mới | Consumer mới | Default hoặc validation đúng như hợp đồng |
| Payload có trường lạ | Consumer cũ | Hành vi bỏ qua hoặc từ chối đúng như cấu hình đã chọn |
| Payload có enum lạ | Consumer | Fallback hoặc lỗi có chủ đích |
| Kết nối dùng MIME type cũ/mới | Peer tương ứng | Không xảy ra giải mã nhầm định dạng |

Nên lưu các payload mẫu (golden fixtures) cho từng phiên bản. Với codec nhị phân, kiểm tra cả khả năng đọc payload được tạo bởi phiên bản trước. Với JSON, kiểm tra tên trường, null, số lớn, độ chính xác thập phân và định dạng ngày giờ.

Cũng cần kiểm tra mô hình tương tác: Request-Response phải trả đúng một response; Request-Stream phải giữ đúng kiểu và thứ tự phần tử; Channel phải xử lý luồng hai chiều và backpressure; Fire-and-Forget chỉ xác nhận việc gửi message, không chứng minh handler đã hoàn tất nghiệp vụ.

## 8. Quan sát và xử lý lỗi khi chuyển đổi

Trong giai đoạn migration, log và metric nên giúp trả lời được:

- Route nào đang được gọi và tần suất sử dụng route cũ là bao nhiêu?
- Kết nối đang dùng data MIME type và metadata MIME type nào?
- Phiên bản client hoặc contract version nào gửi request?
- Có bao nhiêu lỗi route không tìm thấy, lỗi decode/encode hoặc lỗi validation?
- Lỗi xuất hiện ở request, response hay khi xử lý stream?

Có thể đưa contract version vào metadata hoặc một trường header đã được chuẩn hóa, nhưng hai phía phải thống nhất cách truyền và giải mã. Không ghi token, dữ liệu cá nhân hoặc toàn bộ payload nhạy cảm vào log. Dùng correlation ID để nối log requester và responder.

Khi phát hiện lỗi sau khi chuyển đổi, cần xác định lỗi thuộc lớp nào trước khi rollback: route không khớp, MIME type không tương thích, schema không giải mã được hay dữ liệu giải mã thành công nhưng sai ý nghĩa. Rollback producer về phiên bản cũ chỉ an toàn khi server vẫn giữ route và decoder cũ.

## 9. Checklist trước khi phát hành

- [ ] Đã ghi lại route, MIME type, schema và interaction model của hợp đồng hiện tại.
- [ ] Đã phân loại thay đổi là tương thích hay breaking change.
- [ ] Route cũ vẫn có handler trong thời gian cần hỗ trợ.
- [ ] Requester và responder có encoder/decoder tương thích cho cả request lẫn response.
- [ ] MIME type của kết nối được cấu hình rõ ràng và thống nhất.
- [ ] Consumer mới xử lý đúng trường thiếu, null, trường lạ và enum chưa biết.
- [ ] Đã kiểm thử client cũ với server mới bằng payload thực tế.
- [ ] Đã kiểm thử kết nối mới nếu thay data MIME type.
- [ ] Có metric để biết khi nào không còn traffic trên hợp đồng cũ.
- [ ] Có điều kiện rõ ràng trước khi xóa route, codec hoặc DTO cũ.

## 10. Tài liệu tham khảo

- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — mô hình message, requester, responder, route, MIME type, RSocketStrategies và codec.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — cấu trúc protocol, SETUP, data và metadata.
- [Spring Framework API: RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html) — API tạo request và cấu hình requester.
- [Spring Framework API: RSocketStrategies](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html) — cấu hình encoder, decoder và route matcher.
