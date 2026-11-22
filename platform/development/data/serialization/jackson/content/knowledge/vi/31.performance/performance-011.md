# Theo dõi ảnh hưởng của giới hạn bảo mật và xử lý lỗi tới hiệu năng

Giới hạn bảo mật và xử lý lỗi là một phần của pipeline đọc dữ liệu, vì vậy chúng có thể ảnh hưởng đến CPU, bộ nhớ, độ trễ và thông lượng của ứng dụng. Với Jackson, các cơ chế như giới hạn độ sâu lồng, độ dài string/number, giới hạn body, kiểm tra field lạ, duplicate detection, validation và xử lý exception giúp bảo vệ hệ thống trước payload bất thường. Nhưng mỗi lớp kiểm soát có chi phí riêng, và cách đặt giới hạn không phù hợp có thể làm request hợp lệ bị từ chối hoặc khiến hệ thống tốn tài nguyên hơn khi lỗi xảy ra liên tục.

Mục tiêu không phải tắt kiểm tra để đạt benchmark cao nhất. Mục tiêu là hiểu chi phí của từng lớp, đo trên payload và tải gần với production, rồi chọn giới hạn vừa đáp ứng hợp đồng dữ liệu vừa giữ SLO về latency, throughput và memory. Cần đo cả đường thành công lẫn đường thất bại: một parser từ chối payload độc hại có thể bảo vệ bộ nhớ, nhưng nếu hàng nghìn request lỗi khiến ứng dụng tạo stack trace và ghi log quá lớn, chính đường xử lý lỗi lại trở thành điểm nghẽn.

## 1. Các lớp bảo vệ và nơi phát sinh chi phí

Một request JSON thường đi qua nhiều lớp:

~~~text
Client / Producer
       |
       v
Gateway / HTTP server
  - body byte limit
  - timeout / rate limit
       |
       v
Input stream / decompression
  - bounded bytes
  - decompressed-size limit
       |
       v
Jackson Core / JsonFactory
  - nesting depth
  - string / number length
  - parser features
       |
       v
Databind
  - DTO / creator / custom deserializer
  - unknown-property / coercion policy
       |
       v
Application validation
  - collection count
  - field constraints
  - domain rules
       |
       v
Business processing
~~~

Chi phí có thể xuất hiện ở các điểm khác nhau:

| Lớp | Chi phí chính | Rủi ro nếu thiếu giới hạn |
|---|---|---|
| Body limit | Đếm byte, buffer hoặc kiểm tra request metadata | Body quá lớn chiếm network, heap hoặc disk |
| Decompression limit | Giải nén và đếm output bytes | Payload nén nhỏ bung ra rất lớn |
| Parser constraints | Kiểm tra token, chiều sâu và độ dài | String/number quá dài hoặc nesting quá sâu |
| Strict parser features | Theo dõi trạng thái token, key đã thấy | Duplicate detection có thêm CPU và bộ nhớ |
| Databinding | Tạo object, collection, string, number | Nhiều object hoặc collection lớn |
| Validation | Duyệt object graph và tạo violation | Validation sau binding không ngăn allocation trước đó |
| Error handling | Tạo exception, path, stack trace, log và response | Request lỗi lặp lại có thể làm CPU/I/O tăng mạnh |

Không có một con số duy nhất mô tả toàn bộ chi phí. Body limit bảo vệ lượng byte nhận; parser constraints bảo vệ đặc điểm token; validation bảo vệ ý nghĩa dữ liệu. Cần phối hợp chúng thay vì trông chờ một feature giải quyết mọi dạng tải.

## 2. Hiểu StreamReadConstraints trong pipeline hiệu năng

StreamReadConstraints thuộc Jackson Core và được gắn vào JsonFactory. Nó có thể giới hạn các đặc điểm như độ sâu lồng, độ dài string và number; một số phiên bản còn có giới hạn tên property hoặc document length.

Ví dụ:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(80)
    .maxStringLength(500_000)
    .maxNumberLength(500)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = JsonMapper.builder(factory).build();
~~~

Các kiểm tra này diễn ra trong lúc parser đọc. Với payload hợp lệ nằm xa giới hạn, chi phí thường là các phép kiểm tra nhỏ theo token hoặc theo buffer. Chi phí không giống nhau cho mọi constraint: nesting được kiểm tra khi đi vào cấu trúc; độ dài string/number được kiểm tra khi parser xử lý token tương ứng.

Khi vượt giới hạn, parser ném StreamConstraintsException. Lúc đó ứng dụng tránh được việc tiếp tục đọc và ánh xạ một token/cấu trúc quá lớn. Tuy nhiên, không nên hiểu rằng parser không cấp phát bất kỳ bộ nhớ nào trước khi phát hiện vượt ngưỡng; parser có thể đã đọc và lưu một phần nội dung để nhận diện token. Giới hạn làm cho mức tiêu thụ có điểm dừng rõ hơn, chứ không biến việc đọc input thành thao tác miễn phí.

Đặt mapper/factory một lần lúc khởi tạo ứng dụng. Không tạo JsonFactory hoặc ObjectMapper mới cho từng request, vì chi phí khởi tạo, cache serializer/deserializer và cấu hình sẽ làm tăng latency và allocation.

## 3. Chọn giới hạn theo hợp đồng và phân bố dữ liệu

Giới hạn quá cao làm giảm tác dụng bảo vệ. Giới hạn quá thấp khiến request hợp lệ bị từ chối. Cách chọn tốt là dựa trên dữ liệu thực tế và giới hạn nghiệp vụ.

Ví dụ một endpoint nhận đơn hàng có thể có:
- Body tối đa theo byte.
- Số item tối đa trong một order.
- Độ dài tối đa cho ghi chú.
- Độ sâu lồng tối đa cho metadata.
- Độ dài token number phù hợp với kiểu tiền tệ.
- Timeout cho toàn bộ request.

Parser constraint không nhất thiết bằng giới hạn nghiệp vụ. Nếu comment tối đa 20.000 ký tự nhưng các field khác có thể dài hơn, maxStringLength có thể được đặt ở mức parser bảo vệ cao hơn, còn @Size(max = 20_000) áp dụng chính xác cho comment.

Hãy xác định:
1. Kích thước payload hợp lệ lớn nhất theo contract.
2. Phân vị p50, p95, p99 của kích thước và thời gian parse.
3. Số request đồng thời trong giờ cao điểm.
4. Heap và CPU còn lại khi tải bình thường.
5. Khả năng chia nhỏ batch hoặc chuyển sang streaming.
6. Biên an toàn cho tăng trưởng schema.

Đừng chọn ngưỡng chỉ dựa vào một fixture nhỏ hoặc một lần chạy local. Một request 5 MB có thể chạy tốt riêng lẻ nhưng gây áp lực đáng kể khi hàng trăm request cùng parse.

## 4. Giới hạn body theo byte và chi phí buffer

Body limit nên được áp dụng ở gateway hoặc HTTP server càng sớm càng tốt. Nếu chỉ kiểm tra sau khi đã đọc toàn bộ body vào byte array, ứng dụng đã phải trả chi phí buffer cho dữ liệu đó.

Với payload nhỏ và có chủ đích buffer, có thể đọc tối đa MAX_BYTES + 1 byte để phát hiện vượt giới hạn:

~~~java
private static final int MAX_BYTES = 2 * 1024 * 1024;

byte[] body = inputStream.readNBytes(MAX_BYTES + 1);

if (body.length > MAX_BYTES) {
    throw new PayloadTooLargeException("Request body exceeds limit");
}

RequestDto request = mapper.readValue(body, RequestDto.class);
~~~

Cách này giữ tối đa khoảng giới hạn cộng một byte trong mảng, nhưng vẫn buffer toàn bộ body hợp lệ. Với file lớn, không nên dùng cách này.

Với streaming, dùng giới hạn ở server/container hoặc một bounded stream đếm số byte thực đọc. Đừng chỉ tin Content-Length: request có thể dùng chunked transfer hoặc metadata không phản ánh số byte thực tế. Kiểm tra ở tầng transport giúp từ chối sớm trước khi Jackson tạo token và object.

Body byte limit cũng có thể làm giảm thời gian parser phải xử lý payload lớn. Nhưng nếu giới hạn đặt quá thấp, client phải chia request thành nhiều phần, làm tăng số lần handshake, header và overhead ứng dụng. Hãy cân nhắc tổng chi phí của một request lớn so với nhiều request nhỏ.

## 5. Nén dữ liệu làm thay đổi phép đo kích thước

Một request gzip 200 KB có thể bung ra thành hàng chục megabyte. Nếu chỉ giới hạn số byte compressed, hệ thống vẫn có thể phải cấp phát và parse lượng dữ liệu rất lớn sau giải nén.

Nên có hai giới hạn:
- Số byte nhận từ network trước giải nén.
- Số byte output sau giải nén, ngay trước parser.

Cũng cần timeout, giới hạn tốc độ giải nén và giới hạn concurrency cho các request nén. Parser constraints tiếp tục giới hạn nesting và token length sau giải nén.

Trong benchmark, ghi rõ dữ liệu đầu vào là compressed hay decompressed. Nếu benchmark chỉ đo readValue() trên byte array đã giải nén, nó không phản ánh chi phí network hoặc decompression của request thật.

## 6. Chi phí của maxNestingDepth, maxStringLength và maxNumberLength

Các constraint có dạng công việc khác nhau:

| Constraint | Khi nào kiểm tra | Chi phí cần quan sát |
|---|---|---|
| maxNestingDepth | Khi parser đi vào object/array lồng | Kiểm tra depth theo cấu trúc |
| maxStringLength | Khi đọc string token | Buffer/scan và kiểm tra độ dài |
| maxNumberLength | Khi đọc number token | Scan token và kiểm tra độ dài |
| maxNameLength | Khi đọc tên property, nếu phiên bản hỗ trợ | Xử lý field name |
| maxDocumentLength | Trong quá trình đọc document, nếu phiên bản hỗ trợ | Theo dõi tổng độ dài nguồn |

Một payload phẳng có hàng nghìn field có thể có depth thấp nhưng vẫn tốn thời gian và bộ nhớ. Một payload rất sâu có thể nhỏ theo byte nhưng tốn chi phí cho cấu trúc lồng và code recursive phía ứng dụng.

Vì vậy, không dùng maxNestingDepth để thay cho giới hạn số phần tử. Cũng không dùng maxStringLength để thay cho giới hạn body. Các constraint bổ sung cho nhau.

Các API và đơn vị đo có thể khác theo phiên bản Jackson. Khi nâng cấp, kiểm tra release notes/Javadoc và benchmark lại thay vì giả định mọi version có cùng implementation và mặc định.

## 7. Strict duplicate detection và unknown-property policy

Strict duplicate detection có thể giúp từ chối object chứa cùng một tên property nhiều lần. Parser phải theo dõi những tên đã xuất hiện trong object hiện tại, vì vậy có thêm chi phí CPU và bộ nhớ, đặc biệt với object có nhiều field.

Ví dụ cấu hình:

~~~java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();
~~~

Cần phân biệt duplicate key nguyên văn với hai tên alias khác nhau cùng ánh xạ vào một property. Strict duplicate detection phát hiện trường hợp lặp chính xác tên JSON; nó không tự biết display_name và displayName là cùng logical property nếu cả hai được khai báo alias.

FAIL_ON_UNKNOWN_PROPERTIES kiểm tra property không được DTO nhận diện trong quá trình binding. Chi phí của nó thường gắn với xử lý field không biết; nó không đòi hỏi parser phải giữ toàn bộ object tree. Nhưng nếu ứng dụng bật strict mode và nhiều client gửi field lạ liên tục, đường exception sẽ phát sinh thường xuyên.

Chọn policy theo contract:
- Strict mode giúp phát hiện typo và schema mismatch.
- Ignore mode giúp tương thích với producer có thể thêm field.
- @JsonAnySetter hoặc JsonNode giúp giữ dữ liệu mở rộng khi có nhu cầu.

Không tắt strict mode chỉ để benchmark đẹp hơn. Hãy đo cả hiệu năng lẫn tỷ lệ dữ liệu sai bị bỏ qua.

## 8. Coercion và validation có ảnh hưởng đến CPU

Coercion cho phép Jackson chuyển một số token sang kiểu đích khác, ví dụ chuỗi số thành integer hoặc float thành integer. Coercion có thể làm API dễ tương thích hơn nhưng cũng làm hợp đồng khó đoán hơn và tạo thêm các bước chuyển đổi.

Validation sau binding thường duyệt object và có thể tạo ConstraintViolation cho từng lỗi. Với một object lớn có nhiều lỗi, tập violation có thể tiêu tốn bộ nhớ. Nếu chỉ cần từ chối ngay khi một điều kiện cơ bản không đạt, có thể kiểm tra trong custom deserializer hoặc adapter trước khi tạo cấu trúc lớn.

Tuy nhiên, không nên đưa mọi quy tắc nghiệp vụ vào deserializer. Hãy tách:
- Cú pháp và kiểu token: parser/Databind.
- Giới hạn cấu trúc để bảo vệ tài nguyên: parser hoặc streaming deserializer.
- Ràng buộc field/domain: Bean Validation hoặc domain model.
- Quy tắc phụ thuộc database/service: business layer.

Việc đặt validation đúng tầng giúp chi phí dễ dự đoán và thông báo lỗi rõ ràng.

## 9. Tree Model và Databinding có profile bộ nhớ khác nhau

readTree() tạo một cây JsonNode. Mỗi object, array, scalar, field name và collection entry có overhead Java. Kích thước heap của tree có thể lớn hơn nhiều so với số byte JSON đầu vào.

readValue() trực tiếp thành DTO thường tránh được việc giữ cả cây trung gian, nhưng vẫn phải tạo object graph đích. Nếu DTO có collection lớn, số object vẫn tăng theo số phần tử.

| Cách đọc | Đặc điểm | Khi phù hợp |
|---|---|---|
| readTree() | Giữ toàn bộ node tree | Cần chọn nhánh, inspect hoặc normalize dữ liệu |
| readValue() | Bind trực tiếp vào DTO | Schema ổn định, cần object đích |
| Streaming parser | Xử lý token hoặc từng record | Payload lớn, xử lý tuần tự |
| MappingIterator | Đọc nhiều root value/record tuần tự | CSV hoặc batch theo record |
| readValues() / iterator | Duyệt các value từ parser | Stream có nhiều item cùng kiểu |

Nếu chỉ cần xử lý một danh sách lớn, parse thành ArrayNode rồi convert từng node vẫn giữ toàn bộ array trong heap. Streaming từng item có thể giảm peak memory, nhưng cần nghĩ đến transaction: nếu item thứ 501 sai, 500 item trước có thể đã được xử lý.

## 10. Ví dụ streaming để giới hạn số item

Giả sử root JSON là array và endpoint chỉ nhận tối đa 500 item:

~~~java
private static final int MAX_ITEMS = 500;

void processItems(InputStream input, ObjectMapper mapper) throws IOException {
    try (JsonParser parser = mapper.getFactory().createParser(input)) {
        if (parser.nextToken() != JsonToken.START_ARRAY) {
            throw JsonMappingException.from(parser, "Expected an array");
        }

        int count = 0;

        while (parser.nextToken() != JsonToken.END_ARRAY) {
            if (count >= MAX_ITEMS) {
                throw JsonMappingException.from(
                    parser,
                    "Array contains too many items"
                );
            }

            ItemRequest item = mapper.readValue(parser, ItemRequest.class);
            process(item);
            count++;
        }
    }
}
~~~

Vòng lặp đọc một phần tử rồi xử lý trước khi sang phần tử kế tiếp. Peak memory có thể thấp hơn nhiều so với việc tạo List<ItemRequest> cho toàn bộ array.

Đổi lại, process(item) có thể tạo side effect trước khi biết toàn bộ document có hợp lệ hay không. Nếu API yêu cầu all-or-nothing, hãy dùng transaction, staging hoặc bước validate/ghi tạm trước khi commit. Streaming là chiến lược quản lý bộ nhớ; nó không tự giải quyết tính nguyên tử của nghiệp vụ.

## 11. Chi phí của đường xử lý lỗi

Đường thành công thường thực hiện parse, binding và business logic. Đường thất bại có thể thêm:
- Tạo exception object.
- Thu thập stack trace.
- Xây dựng mapping path.
- Tạo thông báo lỗi.
- Chuyển đổi exception thành response.
- Ghi log hoặc gửi trace/event.
- Serialize error response.

Một request sai lặp đi lặp lại có thể tốn CPU đáng kể dù payload nhỏ. Nếu mỗi lỗi đều ghi stack trace đầy đủ ở mức ERROR, log volume và I/O có thể trở thành bottleneck.

Không nên dùng exception làm cơ chế điều khiển luồng cho dữ liệu bình thường, ví dụ thử parse nhiều định dạng lần lượt bằng cách bắt exception cho đến khi một parser thành công. Nếu có thể nhận diện content type hoặc schema trước, hãy chọn parser rõ ràng.

Với lỗi input dự kiến như JSON sai cú pháp hoặc vượt quota, ứng dụng có thể trả response chuẩn hóa và log thông tin gọn. Với lỗi code/configuration bất ngờ, cần giữ cause và stack trace để điều tra.

## 12. Không log toàn bộ payload trong mỗi exception

Raw JSON có thể chứa token, password, email, số điện thoại hoặc dữ liệu tài chính. Ghi toàn bộ body vào log vừa tăng I/O và storage, vừa tạo rủi ro lộ dữ liệu.

Thay vào đó, ghi các trường có cardinality thấp:
- Correlation/request ID.
- Endpoint hoặc operation name.
- Exception class.
- Mapping path đã được giới hạn độ dài.
- JsonLocation nếu có.
- Kích thước body.
- Loại constraint bị vượt.
- Phiên bản ứng dụng và profile mapper.

Tránh dùng raw property value, exception message chứa giá trị input, request ID hoặc path tùy ý làm metric label. Những giá trị thay đổi theo từng request tạo high cardinality và làm hệ thống metrics tốn bộ nhớ.

Nếu cần tái hiện lỗi, lưu fixture synthetic hoặc payload đã được redacted theo chính sách dữ liệu. Không ghi raw body theo mặc định chỉ để hỗ trợ debug.

## 13. Phân loại lỗi giúp giảm chi phí và tăng khả năng vận hành

Không phải mọi exception Jackson đều là lỗi client. Việc phân loại đúng giúp response và logging phù hợp:

| Loại lỗi | Diễn giải thường gặp | Hành động |
|---|---|---|
| JsonParseException | Cú pháp JSON sai | Trả lỗi input, log gọn |
| StreamConstraintsException | Vượt giới hạn parser | Từ chối request, tăng metric theo constraint |
| MismatchedInputException | Shape/token không phù hợp kiểu đích | Trả lỗi field/contract |
| InvalidFormatException | Giá trị không chuyển được | Trả lỗi format/range |
| UnrecognizedPropertyException | Field lạ trong strict mode | Kiểm tra contract/version |
| InvalidDefinitionException | DTO/module/serializer config không dùng được | Xem là lỗi server, giữ stack trace |
| IOException | Nguồn đọc bị lỗi hoặc client ngắt | Phân biệt transport với parse |
| ConstraintViolationException | Bean Validation thất bại | Trả lỗi validation đã chuẩn hóa |

Các nhóm trên chỉ là hướng phân loại. Hãy xem cause, path và tầng phát sinh. Ví dụ, ValueInstantiationException có thể do input vi phạm invariant hoặc do constructor có bug.

Nếu lỗi cấu hình phía server bị trả thành 400, team có thể bỏ lỡ regression. Nếu lỗi client bị log stack trace ở ERROR hàng nghìn lần, log noise che mất sự cố thật.

## 14. Thiết kế error response không tạo thêm tải không cần thiết

Error response nên có cấu trúc ổn định, không cần chứa toàn bộ exception:

~~~json
{
  "code": "INVALID_JSON",
  "message": "Request body is not valid for this endpoint",
  "path": "items[2].quantity",
  "requestId": "req-123"
}
~~~

Không đưa stack trace, tên class nội bộ hoặc toàn bộ input vào response. Nếu có nhiều validation violations, giới hạn số lỗi trả về hoặc tổng độ dài response để một payload sai khổng lồ không tạo thêm response khổng lồ.

Có thể giữ nguyên exception làm cause khi ném exception ứng dụng:

~~~java
try {
    return mapper.readValue(input, RequestDto.class);
} catch (StreamConstraintsException exception) {
    throw new PayloadLimitException("JSON exceeds parser limits", exception);
} catch (JsonProcessingException exception) {
    throw new InvalidRequestException("Invalid JSON request", exception);
}
~~~

Trong code thực tế, thứ tự catch phải theo quan hệ kế thừa của phiên bản Jackson. StreamConstraintsException thuộc nhánh exception của Jackson Core; kiểm tra import và hierarchy của dependency đang dùng để tránh catch unreachable hoặc phân loại sai.

Nếu lỗi xảy ra khi serialize response phía server, không được chuyển thành INVALID_JSON của request. Đó là lỗi tạo output và thường cần được xử lý như server error.

## 15. Metrics nên theo dõi điều gì?

Một bộ metrics hữu ích nên mô tả kích thước, thời gian, kết quả và tài nguyên:

| Metric | Ý nghĩa |
|---|---|
| Request body bytes | Kích thước input thực nhận |
| Decompressed bytes | Kích thước sau giải nén |
| Parse/bind duration | Thời gian từ lúc bắt đầu đọc đến khi có DTO |
| End-to-end request duration | Thời gian toàn request |
| Parse success/failure count | Tỷ lệ request parse thành công |
| Constraint rejection count | Số request bị từ chối theo từng loại giới hạn |
| Mapping error count | Sai shape, format hoặc unknown property |
| Validation failure count | Số request binding được nhưng vi phạm validation |
| Heap/GC allocation | Áp lực bộ nhớ khi tải tăng |
| Concurrent parsing requests | Số request đang parse cùng lúc |
| Error log volume | Tải I/O do lỗi |

Có thể dùng Micrometer Timer/Counter nếu ứng dụng đã dùng metrics framework. Chỉ dùng label có tập giá trị hữu hạn như exception_type, endpoint_group hoặc limit_kind. Không dùng raw URL có ID, request ID, property value hoặc exception message làm label.

Nên phân biệt số request bị từ chối vì body quá lớn, parser constraint, validation thất bại và lỗi server do InvalidDefinitionException/custom handler. Các con số này giúp biết nên điều chỉnh giới hạn, sửa client contract hay khắc phục cấu hình.

## 16. Đo thời gian đúng cách

Không nên kết luận hiệu năng từ một lần gọi System.nanoTime() quanh một request. Kết quả có thể bị ảnh hưởng bởi JIT compilation, class loading, GC, cache nóng/lạnh, scheduler và các request khác.

Khi đo:
- Tách thời gian đọc byte, parse/bind, validation và business processing nếu cần.
- Dùng cùng payload và cùng target type khi so sánh.
- Khởi tạo ObjectMapper trước vùng đo.
- Chạy nhiều lần warmup.
- Đo nhiều iteration và nhiều fork.
- Theo dõi allocation/GC cùng latency.
- Đo p50, p95 và p99 khi chạy load test.
- Ghi rõ CPU, heap, JDK, Jackson version và cấu hình.

Một benchmark chỉ đo readTree() không thể đại diện cho endpoint thực tế nếu production còn giải nén, validation, logging và database work. Ngược lại, benchmark end-to-end khó cho biết parser constraint nào tạo ra chi phí. Cần cả microbenchmark và load test có kiểm soát.

## 17. Dùng JMH để so sánh parser và policy

JMH phù hợp để đo các đoạn xử lý Java có thể lặp lại. Một benchmark tối giản có thể so sánh mapper mặc định với mapper có constraints:

~~~java
@State(Scope.Thread)
public class JacksonReadBenchmark {

    private ObjectMapper baseline;
    private ObjectMapper constrained;
    private byte[] payload;

    @Setup
    public void setup() throws Exception {
        payload = Files.readAllBytes(Path.of("fixture.json"));

        baseline = new ObjectMapper();

        StreamReadConstraints limits = StreamReadConstraints.builder()
            .maxNestingDepth(80)
            .maxStringLength(500_000)
            .maxNumberLength(500)
            .build();

        JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(limits)
            .build();

        constrained = JsonMapper.builder(factory).build();
    }

    @Benchmark
    public RequestDto baselineRead() throws Exception {
        return baseline.readValue(payload, RequestDto.class);
    }

    @Benchmark
    public RequestDto constrainedRead() throws Exception {
        return constrained.readValue(payload, RequestDto.class);
    }
}
~~~

Ví dụ cần được đặt trong project JMH với dependency và plugin tương ứng. Fixture phải nằm dưới các giới hạn để hai benchmark đo cùng một công việc thành công. Không tạo ObjectMapper trong từng benchmark invocation.

Dùng JMH warmup, measurement, forks và profiler phù hợp. Allocation profiler giúp so sánh bytes/op; GC profiler giúp nhận ra chi phí cấp phát. Không chỉ nhìn throughput trung bình: nếu latency tail tăng hoặc allocation tăng mạnh, endpoint có thể vẫn gặp vấn đề khi concurrency cao.

Đây là benchmark minh họa. Hãy thêm đúng module, custom deserializer, naming strategy và feature mà mapper production sử dụng nếu chúng ảnh hưởng đường binding.

## 18. Benchmark đường thất bại riêng với đường thành công

Không trộn request hợp lệ và request sai vào một benchmark duy nhất mà không ghi rõ tỷ lệ. Đường thất bại tạo exception và có thể đi qua error serialization/logging.

Nên tách các kịch bản:

| Kịch bản | Mục tiêu |
|---|---|
| Payload hợp lệ, gần p50 | Chi phí bình thường |
| Payload hợp lệ, gần p99 | Chi phí ở kích thước lớn |
| String vượt giới hạn sớm | Chi phí phát hiện token quá dài |
| Nesting vượt giới hạn sớm | Chi phí từ chối cấu trúc sâu |
| Nesting vượt giới hạn gần cuối | Chi phí khi parser đã đọc phần lớn input |
| Sai kiểu ở field đầu | Chi phí mapping error sớm |
| Sai kiểu ở field cuối | Chi phí sau khi đã xử lý phần lớn payload |
| Unknown property | Chi phí strict policy |
| Duplicate key | Chi phí detection và rejection |
| Validation có nhiều violations | Chi phí tạo và serialize lỗi |

Đối với failure benchmark, không ghi stack trace ra console trong vòng đo nếu mục tiêu là cô lập parser. Sau đó thực hiện một benchmark hoặc load test khác bao gồm error handler và logging thực tế. Nếu bỏ logging trong toàn bộ phép đo, bạn sẽ bỏ qua một phần đáng kể của đường lỗi production.

## 19. Đo memory và allocation, không chỉ heap sau GC

Heap usage tại một thời điểm không đủ để so sánh parser. Một request có thể cấp phát nhiều object tạm rồi GC trước khi bạn chụp số liệu. Hãy quan sát:
- Allocation rate.
- Bytes allocated per operation.
- Số lần và thời gian GC.
- Peak live set.
- Old-generation pressure.
- Số request đồng thời đang giữ body/tree/DTO.

Tree Model thường tạo nhiều node object. Databinding trực tiếp tạo DTO và collection. Streaming có thể giảm số object sống đồng thời, nhưng vẫn tạo object cho từng item nếu ứng dụng cần chúng.

Body buffer, decompressed buffer và JsonNode tree có thể cùng tồn tại trong một request. Nếu code giữ cả ba, peak memory cao hơn nhiều so với chỉ nhìn kích thước file.

Cũng cần kiểm tra ownership và lifecycle: không giữ reference đến JsonNode, byte array hoặc exception quá lâu trong cache, async task hoặc log event.

## 20. Validation sau binding có thể làm tăng peak memory

Bean Validation có thể tạo nhiều ConstraintViolation nếu object có hàng nghìn field sai. Nếu ứng dụng gom tất cả violations thành một list và serialize đầy đủ, response cũng có thể lớn.

Một số lựa chọn:
- Giới hạn số violations được trả về.
- Dùng giới hạn collection trước khi bind nếu số phần tử ảnh hưởng lớn.
- Validate theo batch/record khi streaming.
- Dừng sớm nếu hợp đồng chỉ cần biết request invalid.
- Giữ thông báo lỗi ngắn và không đưa raw input vào từng violation.

Không nên giảm số lỗi trả về bằng cách bỏ qua các constraint quan trọng. Có thể validate đầy đủ ở backend nhưng chỉ trả một số lỗi đại diện; hoặc dừng sớm khi đã đủ thông tin để từ chối.

Nếu cần all-or-nothing, tách bước validation khỏi side effect. Đừng vừa đọc vừa ghi dữ liệu không thể rollback rồi mới phát hiện item cuối vi phạm giới hạn.

## 21. Concurrency và backpressure ảnh hưởng tổng tài nguyên

Một payload hợp lệ có thể parse nhanh khi chạy đơn lẻ nhưng trở thành vấn đề khi nhiều request cùng lúc. Peak memory phụ thuộc vào:
- Kích thước body được giữ trong mỗi request.
- Buffer giải nén.
- Object graph hoặc tree.
- Số request đang parse đồng thời.
- Queue và async tasks giữ reference đến dữ liệu.

Do đó, body limit và parser constraints cần đi cùng concurrency limit, rate limit và backpressure. Nếu server cho phép quá nhiều request lớn parse cùng lúc, mỗi request đều tuân thủ giới hạn nhưng tổng heap vẫn có thể vượt khả năng.

Đối với import batch, có thể dùng worker pool giới hạn số tác vụ, bounded queue và streaming. Tránh tạo một future cho mỗi record trong file hàng triệu dòng nếu không có backpressure.

Khi hệ thống gần bão hòa, từ chối sớm hoặc điều tiết tốc độ có thể tốt hơn nhận tất cả request rồi để GC/timeout làm sụp throughput.

## 22. Tác động của logging và tracing

Logging có thể là phần đắt nhất của đường lỗi nếu mỗi request ghi stack trace, raw body và nhiều dòng metadata. Các yếu tố cần xem:
- Formatter có serialize object hoặc exception nhiều lần không.
- Log appender ghi đồng bộ hay bất đồng bộ.
- Queue log có bounded hay không.
- Stack trace có bị ghi lặp ở nhiều layer không.
- Trace span có gắn raw payload hoặc exception message lớn không.

Một pattern tốt:
- Ở boundary, chuyển lỗi thành error code và status.
- Log một lần tại layer chịu trách nhiệm xử lý request.
- Giữ cause đầy đủ cho lỗi server bất ngờ.
- Với lỗi input dự kiến, ghi class/path/location và metric; không nhất thiết ghi stack trace cho từng request.
- Dùng sampling hoặc rate limit log cho một lỗi lặp lại có tần suất cao.

Không được nuốt lỗi hoàn toàn. Nếu giảm log, hãy bù bằng counter/metric để vẫn nhìn thấy tỷ lệ lỗi và xu hướng.

## 23. Tránh tạo thông báo lỗi từ payload quá lớn

Một số code xử lý lỗi có thể vô tình gọi exception.getMessage() rồi đưa toàn bộ message vào response hoặc log. Tùy exception và custom deserializer, message có thể chứa giá trị input, path dài hoặc nội dung nhạy cảm.

Nên:
- Chuẩn hóa error code.
- Giới hạn chiều dài path/message.
- Không echo raw value.
- Tránh serialize toàn bộ JsonNode khi log.
- Giữ exception cause trong log nội bộ khi cần.
- Không tạo một response chứa hàng chục nghìn validation errors.

Nếu cần chỉ ra vị trí, JsonLocation và mapping path thường đủ hữu ích mà không cần trả nguyên payload. Cần kiểm tra dữ liệu nào được đưa vào path/message trước khi log.

## 24. Đặt ngưỡng dựa trên SLO và tải production

Một cách chọn policy có thể theo quy trình:

1. Thu thập kích thước và thời gian xử lý của payload hợp lệ.
2. Xác định ngưỡng contract cho body, string, collection và nesting.
3. Chạy benchmark để so sánh baseline và mapper có constraints.
4. Chạy load test với concurrency gần production.
5. Đo p95/p99 latency, throughput, allocation và GC.
6. Tăng tỷ lệ request vượt giới hạn trong môi trường thử nghiệm để đo failure path.
7. Kiểm tra error response và logging không gây bottleneck.
8. Triển khai ngưỡng ban đầu có biên an toàn.
9. Theo dõi tỷ lệ rejection và điều chỉnh qua thay đổi có kiểm soát.

Ví dụ nếu p99 payload hợp lệ là 1.2 MB, không tự động đặt limit 1.3 MB. Cần biết biến động theo thời gian, encoding, nén, số request đồng thời và giới hạn tài nguyên. Có thể chọn mức lớn hơn có chủ đích, nhưng phải kiểm tra peak memory khi nhiều request cùng đạt ngưỡng.

Không dùng một ngưỡng body duy nhất cho mọi endpoint nếu profile dữ liệu khác nhau. Một webhook nhỏ, API CRUD và import batch có nhu cầu khác nhau.

## 25. Kiểm thử hiệu năng và correctness cùng nhau

Benchmark nhanh nhưng cho kết quả sai không có giá trị. Mỗi thay đổi policy cần kiểm tra:
- Payload hợp lệ trước đây vẫn được đọc.
- Payload vượt giới hạn bị từ chối đúng loại.
- Không có silent truncation hoặc default value ngoài ý muốn.
- Parser dừng đúng khi gặp lỗi.
- Stream được đóng theo lifecycle đã định.
- Error response không lộ dữ liệu.
- Metrics được tăng đúng loại.
- Hệ thống không tạo log storm khi lỗi lặp lại.

Có thể dùng fixture ở ngay ngưỡng và ngưỡng cộng một. Với giới hạn collection, test số item bằng đúng max và max + 1. Với body limit, test số byte thực nhận chứ không chỉ sửa Content-Length trong request. Với gzip, test cả compressed và decompressed size.

Performance test phải chạy trên cùng JDK/Jackson version và cấu hình mapper dự kiến production. Một benchmark dùng mapper mặc định sẽ không đại diện cho ứng dụng đã bật custom modules, strict duplicate detection hoặc validation.

## 26. Ví dụ đo và ghi nhận parse duration

Có thể dùng Micrometer Timer nếu dự án đã có:

~~~java
Timer parseTimer = registry.timer("jackson.databind.duration");

RequestDto read(byte[] body, ObjectMapper mapper) throws IOException {
    return parseTimer.recordCallable(
        () -> mapper.readValue(body, RequestDto.class)
    );
}
~~~

Counter cho constraint rejection:

~~~java
Counter nestingRejected =
    registry.counter("jackson.read.rejected", "reason", "nesting");

try {
    return mapper.readValue(body, RequestDto.class);
} catch (StreamConstraintsException exception) {
    nestingRejected.increment();
    throw exception;
}
~~~

Ví dụ trên đơn giản hóa phân loại. Nếu cần phân biệt string, number, name và document limit, hãy xác định loại constraint bằng API/exception của đúng phiên bản hoặc phân loại tại lớp adapter đã đặt từng giới hạn. Không parse exception message bằng chuỗi fragile để tạo metric.

Timer nên bao quanh đúng phần muốn đo. Nếu đặt timer quanh toàn endpoint, nó bao gồm network, authentication, business logic và response serialization. Nếu muốn tách parse/bind, đặt timer sát lệnh mapper và tạo metric end-to-end riêng.

## 27. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách thay thế |
|---|---|---|
| Tắt constraints để tăng tốc | Payload bất thường có thể tiêu thụ tài nguyên lớn | Đo overhead và chọn ngưỡng hợp lý |
| Đặt mọi giới hạn rất cao | Bảo vệ không còn ý nghĩa thực tế | Dựa vào contract và tải |
| Tạo ObjectMapper mỗi request | Tăng allocation và mất lợi ích cache | Tái sử dụng mapper sau khi cấu hình |
| Parse toàn bộ file lớn thành tree | Peak memory cao | Streaming hoặc MappingIterator |
| Dùng exception để thử nhiều format | Tốn stack trace và khó phân loại | Chọn parser từ content type/schema |
| Log raw body và stack trace cho mọi lỗi | I/O, storage và rủi ro dữ liệu | Log metadata an toàn, metric và sampling |
| Bắt mọi exception rồi trả DTO rỗng | Che lỗi và đưa dữ liệu sai vào nghiệp vụ | Phân loại và từ chối rõ ràng |
| Chỉ benchmark payload nhỏ | Không thấy p99 và memory pressure | Test payload lớn và concurrency |
| Chỉ đo đường thành công | Bỏ qua chi phí error storm | Benchmark failure path riêng |
| Chỉ dùng @Size sau khi bind để chống array lớn | Collection đã được cấp phát | Streaming/custom deserializer quota |

## 28. Checklist theo dõi trước và sau khi triển khai

Trước khi triển khai:
- Xác định giới hạn body theo byte và sau giải nén.
- Cấu hình StreamReadConstraints trên JsonFactory dùng thật.
- Xác định quota collection và property.
- Quy định unknown field, duplicate key, coercion và null.
- Chuẩn hóa lỗi client/server.
- Xác định logging và metric không chứa dữ liệu nhạy cảm.
- Benchmark payload hợp lệ và payload bị từ chối.
- Load test concurrency, GC và p95/p99.

Sau khi triển khai:
- Theo dõi body-size distribution.
- Theo dõi parse/bind duration.
- Theo dõi rejection theo từng constraint.
- Theo dõi mapping và validation failure.
- Theo dõi allocation rate, GC pause và heap pressure.
- Theo dõi log volume và queue saturation.
- Kiểm tra client hợp lệ có bị từ chối không.
- Điều chỉnh ngưỡng qua release có kiểm soát, không sửa nóng mapper toàn cục.

## Kết luận

Giới hạn bảo mật giúp kiểm soát lượng công việc Jackson phải thực hiện, còn xử lý lỗi quyết định chi phí khi input không hợp lệ. StreamReadConstraints, body limit, giới hạn sau giải nén, quota collection và concurrency control bảo vệ các tầng khác nhau. Strict duplicate detection, unknown-property policy và validation có thể tăng chi phí nhưng cũng phát hiện dữ liệu mơ hồ hoặc sai contract. Đường lỗi còn có chi phí tạo exception, path, response, log và trace.

Hãy đo riêng đường thành công và thất bại, theo dõi allocation/GC cùng latency, tái sử dụng mapper đã cấu hình và tránh log raw payload. Dùng JMH để cô lập chi phí parser/databinding, load test để thấy tác động concurrency, rồi chọn ngưỡng theo dữ liệu hợp lệ và SLO. Bảo mật và hiệu năng không phải hai mục tiêu loại trừ nhau: policy tốt là policy có giới hạn rõ, được đo bằng tải thực tế và có cách từ chối dữ liệu bất thường với chi phí hữu hạn.

