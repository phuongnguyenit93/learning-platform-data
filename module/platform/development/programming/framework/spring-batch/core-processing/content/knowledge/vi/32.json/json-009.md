# Encoding JSON

Trong Spring Batch, JSON thường được dùng làm định dạng trao đổi giữa hệ thống nguồn, batch job và hệ thống đích. Một job có thể đọc danh sách object từ file JSON, chuyển đổi từng item rồi ghi kết quả thành JSON để một dịch vụ khác tiêu thụ. Để dữ liệu không bị sai ký tự hoặc không thể parse trên môi trường khác, cần thống nhất **character encoding** của file và cách thư viện JSON chuyển đổi giữa byte, ký tự và object.

JSON là định dạng văn bản. File JSON cuối cùng là một chuỗi byte được giải mã theo một charset, thường là UTF-8. Bản thân cú pháp JSON còn có quy tắc escape cho dấu nháy kép, backslash và ký tự điều khiển trong string. Hai khái niệm này liên quan nhưng khác nhau:

- **Encoding** chuyển ký tự Unicode thành byte hoặc ngược lại, ví dụ UTF-8.
- **JSON escaping** biểu diễn một số ký tự bên trong JSON string, ví dụ `\"`, `\\`, `\n` hoặc `\uXXXX`.
- **Serialization** chuyển object thành JSON text.
- **Deserialization** parse JSON text thành object.

Một file có thể chứa JSON hợp lệ nhưng được ghi bằng charset mà consumer không mong đợi; ngược lại, file UTF-8 có thể chứa cú pháp JSON sai. Vì vậy, cần kiểm tra cả encoding lẫn JSON structure.

## UTF-8 là lựa chọn chuẩn cho JSON trao đổi

RFC 8259 quy định JSON text được trao đổi giữa các hệ thống mở phải được mã hóa UTF-8. Generator không nên thêm byte order mark (BOM) vào JSON được truyền qua mạng; parser có thể bỏ qua BOM nếu gặp. Trong hệ thống batch, chọn UTF-8 cho input/output giúp giảm khác biệt giữa Windows, Linux, container và các dịch vụ downstream.

Ví dụ JSON chứa tiếng Việt:

```json
{
  "orderId": "DH-1001",
  "customerName": "Nguyễn Thị Ánh",
  "note": "Giao hàng lúc 8 giờ sáng",
  "city": "Hồ Chí Minh"
}
```

Các ký tự `ễ`, `ị`, `Á`, `ồ` là ký tự Unicode. Trong UTF-8, mỗi ký tự được biểu diễn bằng một hoặc nhiều byte. Khi ghi file, serializer tạo JSON text rồi writer mã hóa text thành UTF-8 bytes. Khi đọc, parser hoặc reader giải mã bytes theo encoding phù hợp trước khi parse JSON.

Không nên dựa vào charset mặc định của máy. Default charset có thể khác giữa môi trường developer, máy chủ Windows, Linux container hoặc JVM được cấu hình khác. Hãy khai báo UTF-8 tường minh ở ranh giới file và message.

## Encoding khác escaping

Ví dụ một string có newline và dấu quote:

```java
String note = "Khách nói: \"gọi trước\"\nGiao ở quầy";
```

Serializer JSON sẽ escape ký tự đặc biệt trong JSON string. JSON text có thể là:

```json
{
  "note": "Khách nói: \"gọi trước\"\nGiao ở quầy"
}
```

Khi file được mã hóa UTF-8, các ký tự Unicode được chuyển thành byte UTF-8; dấu quote và newline được biểu diễn theo cú pháp JSON. Consumer parse JSON sẽ khôi phục string ban đầu.

Không tự thay tiếng Việt thành `\uXXXX` chỉ vì nghĩ rằng JSON bắt buộc phải escape Unicode. JSON cho phép ký tự Unicode xuất hiện trực tiếp trong string nếu encoding hợp lệ. Jackson có thể ghi ký tự Unicode trực tiếp hoặc escape một số ký tự tùy cấu hình; cả hai cách đều có thể biểu diễn cùng giá trị.

Ví dụ hai JSON text sau mang cùng giá trị string:

```json
{"name":"Hồ Chí Minh"}
```

```json
{"name":"H\u1ed3 Ch\u00ed Minh"}
```

Encoding xác định byte của toàn bộ JSON text. Escape sequence là một phần của cú pháp JSON string. Không được double-encode, ví dụ chuyển JSON string thành UTF-8 bytes rồi lại đưa chuỗi biểu diễn byte đó vào serializer như dữ liệu văn bản.

## Unicode và escape sequence

JSON string dùng dấu quote kép để bao chuỗi. Các ký tự cần escape gồm:

| Ký tự | Cách biểu diễn JSON |
| --- | --- |
| Dấu quote `"` | `\"` |
| Backslash `\` | `\\` |
| Backspace | `\b` |
| Form feed | `\f` |
| Newline | `\n` |
| Carriage return | `\r` |
| Tab | `\t` |
| Ký tự điều khiển U+0000 đến U+001F | `\u00XX` tương ứng |

Một số ký tự ngoài Basic Multilingual Plane được biểu diễn bằng cặp UTF-16 surrogate trong dạng escape `\uXXXX`. Khi dùng Jackson, để thư viện xử lý Unicode và escaping; không tự cắt chuỗi theo từng `char` rồi ghép escape sequence vì có thể làm hỏng surrogate pair.

Không dùng `String.replace` thủ công để escape JSON. Cách làm đó thường bỏ sót backslash, control character, quote hoặc cặp surrogate. Dùng Jackson hoặc thư viện JSON tương thích để serialize và parse.

## JSON array và JSON Lines là hai định dạng khác nhau

Spring Batch có các thành phần JSON hỗ trợ đọc/ghi item. Trước khi chọn reader/writer, cần xác định cấu trúc file.

### JSON array

Một tài liệu JSON có thể chứa một array gồm nhiều object:

```json
[
  {"orderId":"O-1","amount":120.50},
  {"orderId":"O-2","amount":90.00},
  {"orderId":"O-3","amount":75.00}
]
```

Đây là một JSON document có root là array. `JsonItemReader` của Spring Batch được thiết kế để đọc các object trong cấu trúc JSON array thông qua `JsonObjectReader`.

### JSON Lines / NDJSON

JSON Lines lưu một JSON value trên mỗi dòng vật lý:

```text
{"orderId":"O-1","amount":120.50}
{"orderId":"O-2","amount":90.00}
{"orderId":"O-3","amount":75.00}
```

Đây không phải một JSON document array duy nhất. Mỗi dòng là một JSON document độc lập. Format này thuận tiện cho streaming và xử lý line-by-line, nhưng phải dùng reader phù hợp, chẳng hạn `FlatFileItemReader` với `LineMapper` dùng Jackson, hoặc custom `ItemReader`. Không đưa NDJSON trực tiếp vào `JsonItemReader` rồi giả định reader hiểu mỗi dòng là một phần tử array.

| Đặc điểm | JSON array | JSON Lines / NDJSON |
| --- | --- | --- |
| Cấu trúc | Một JSON document, root là array | Mỗi dòng là một JSON value độc lập |
| Dấu phân cách | `[` `]` và dấu phẩy giữa item | Newline giữa item |
| Reader phù hợp | `JsonItemReader` | `FlatFileItemReader` + Jackson hoặc custom reader |
| Dễ stream từng item | Có thể stream qua parser | Tự nhiên theo từng dòng |
| Một object nhiều dòng | Hợp lệ trong array | Không phù hợp với quy ước một JSON value mỗi dòng |

Encoding UTF-8 áp dụng cho cả hai format; cấu trúc record quyết định cách reader tách item.

## Đọc JSON array bằng JsonItemReader

Spring Batch cung cấp `JsonItemReader<T>` và abstraction `JsonObjectReader<T>`. Với Jackson, có thể dùng `JacksonJsonObjectReader<T>` để parse từng object trong JSON array.

Ví dụ model:

```java
public record OrderInput(
        String orderId,
        String customerName,
        BigDecimal amount) {
}
```

Reader:

```java
@Bean
@StepScope
JsonItemReader<OrderInput> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new JsonItemReaderBuilder<OrderInput>()
            .name("orderJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(OrderInput.class))
            .strict(true)
            .saveState(true)
            .build();
}
```

Reader này đọc từng object trong JSON array và ánh xạ thành `OrderInput`. `strict(true)` yêu cầu resource tồn tại theo strict resource behavior của reader. `saveState(true)` cho phép reader lưu vị trí để hỗ trợ restart.

`JacksonJsonObjectReader` dùng Jackson để parse JSON. Khi parser nhận byte stream, Jackson có khả năng nhận diện các encoding Unicode được hỗ trợ bởi JSON parser; tuy nhiên, hợp đồng của hệ thống vẫn nên quy định input là UTF-8. Không dựa vào khả năng auto-detect để chấp nhận file bất kỳ encoding nào mà producer gửi tới.

Nếu ứng dụng dùng phiên bản Spring Batch/Jackson khác, kiểm tra constructor và builder API tương ứng trong dependency thực tế. Các API JSON đã thay đổi giữa một số thế hệ framework, nên ví dụ cần khớp version đang triển khai.

## Cấu hình ObjectMapper cho JSON

`ObjectMapper` kiểm soát cách Jackson ánh xạ object và JSON. Encoding file là một lớp riêng; `ObjectMapper` chủ yếu quyết định cấu trúc JSON, naming, date/time, null, enum và kiểu dữ liệu.

Ví dụ cấu hình mapper cho Java time:

```java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
}
```

`JavaTimeModule` hỗ trợ các kiểu như `LocalDate`, `LocalDateTime` và `Instant`. Tắt `WRITE_DATES_AS_TIMESTAMPS` giúp ngày giờ được biểu diễn theo dạng text thay vì số timestamp đối với các kiểu được module hỗ trợ.

Khi cần cấu hình `JacksonJsonObjectReader`, có thể truyền mapper đã được cấu hình theo constructor mà phiên bản Spring Batch đang sử dụng hỗ trợ:

```java
@Bean
JacksonJsonObjectReader<OrderInput> orderJsonObjectReader(
        ObjectMapper batchObjectMapper) {
    return new JacksonJsonObjectReader<>(
            OrderInput.class,
            batchObjectMapper);
}
```

Sau đó inject reader này vào `JsonItemReaderBuilder`. Không tạo một `ObjectMapper` cấu hình khác cho writer nếu hai chiều cần cùng một contract JSON.

### Các thiết lập cần thống nhất

| Thiết lập | Tác động |
| --- | --- |
| Property naming strategy | Tên field JSON như `orderId` hay `order_id` |
| `JavaTimeModule` | Parse/serialize Java date-time types |
| Date/time format | Dạng text, timezone và precision |
| Null inclusion | Field null có được ghi ra JSON không |
| Enum handling | Dùng tên enum hay mã nghiệp vụ |
| Number handling | Decimal, integer và cách xử lý số ngoài range |
| Unknown properties | Reader xử lý field mới từ producer như thế nào |
| Polymorphic typing | Cách biểu diễn subtype nếu contract cần |

Các thiết lập này là một phần của data contract. Thay đổi naming strategy hoặc date format có thể làm consumer cũ không parse được file mới dù encoding vẫn là UTF-8.

## Đọc JSON với encoding được quy định tường minh

Ở ranh giới file, hãy quy định producer ghi UTF-8 và consumer đọc theo cùng hợp đồng. Nếu tự tạo `Reader`, dùng charset tường minh:

```java
try (BufferedReader reader = Files.newBufferedReader(
        inputPath,
        StandardCharsets.UTF_8)) {
    // Chuyển reader cho parser phù hợp.
}
```

`Files.newBufferedReader(path, StandardCharsets.UTF_8)` không dựa vào default charset của JVM. Khi thư viện JSON nhận `Reader`, byte decoding đã xảy ra trước khi parser xử lý JSON; do đó charset được chọn ở bước tạo Reader là quyết định quan trọng.

Nếu parser nhận trực tiếp `InputStream`, Jackson có thể nhận diện UTF-8/UTF-16/UTF-32 theo các byte đầu vào và BOM. Dù vậy, giao thức file nên chỉ định UTF-8 để producer và consumer không phải đoán encoding. Nếu cần từ chối byte sequence UTF-8 malformed thay vì thay bằng ký tự replacement, có thể dùng `CharsetDecoder` với `CodingErrorAction.REPORT` trước khi parse.

Ví dụ decoder strict:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(
        Files.newInputStream(inputPath), decoder)) {
    // Đưa reader vào JSON parser.
}
```

Với decoder strict, byte sequence không hợp lệ sẽ gây lỗi thay vì âm thầm thay bằng `�`. Điều này hữu ích với pipeline cần phát hiện file bị hỏng hoặc producer dùng sai charset.

## BOM trong file JSON

UTF-8 BOM là ba byte `EF BB BF` ở đầu file. BOM có thể xuất hiện khi file được tạo bởi một số công cụ Windows hoặc editor.

RFC 8259 không yêu cầu generator thêm BOM vào JSON text được trao đổi; parser có thể bỏ qua BOM nếu gặp. Để interoperability tốt, nên xuất JSON UTF-8 không BOM. Với input legacy, xác định rõ consumer có chấp nhận BOM hay không và kiểm thử parser/version thực tế.

Một lỗi thường gặp là BOM được giải mã thành ký tự `U+FEFF` trước dấu `[` hoặc `{`, rồi thư viện parser không chấp nhận ký tự đó ở vị trí đầu document. Nếu cần loại BOM, chỉ loại đúng một BOM ở đầu stream; không dùng `replace("\uFEFF", "")` trên toàn bộ nội dung vì có thể xóa ký tự dữ liệu hợp lệ ở vị trí khác.

Ví dụ kiểm tra byte đầu file:

```java
byte[] prefix = new byte[3];
try (InputStream input = Files.newInputStream(path)) {
    int count = input.read(prefix);
    boolean hasUtf8Bom = count == 3
            && (prefix[0] & 0xFF) == 0xEF
            && (prefix[1] & 0xFF) == 0xBB
            && (prefix[2] & 0xFF) == 0xBF;
}
```

Đây chỉ là đoạn nhận diện; nếu cần tiếp tục đọc cùng stream, phải giữ lại các byte đã đọc hoặc mở lại stream sau khi kiểm tra. Trong đa số trường hợp, quy định producer không ghi BOM sẽ đơn giản hơn.

## Ghi JSON bằng JsonFileItemWriter

Spring Batch cung cấp `JsonFileItemWriter<T>` để ghi item thành JSON file thông qua `JsonObjectMarshaller<T>`. Với Jackson, có thể dùng `JacksonJsonObjectMarshaller<T>`.

```java
@Bean
JsonFileItemWriter<Order> orderJsonWriter(
        @Value("${batch.output.orders}") Resource outputResource) {

    return new JsonFileItemWriterBuilder<Order>()
            .name("orderJsonWriter")
            .resource(outputResource)
            .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
            .encoding(StandardCharsets.UTF_8.name())
            .saveState(true)
            .build();
}
```

Builder API có thể khác theo Spring Batch version; nếu phiên bản đang dùng không cung cấp `encoding(...)` trên builder cụ thể, cấu hình encoding qua API writer/resource được version đó hỗ trợ hoặc dùng writer tùy chỉnh với `OutputStreamWriter(StandardCharsets.UTF_8)`. Không dựa vào default charset.

`JsonFileItemWriter` ghi các item theo định dạng JSON mà implementation cung cấp, thường là một JSON array. `JsonObjectMarshaller` chịu trách nhiệm chuyển từng object thành JSON text; writer quản lý cấu trúc file và lifecycle ghi. Không tự thêm dấu `[` hoặc `]` trong marshaller nếu writer đã quản lý array wrapper.

### Dùng ObjectMapper tùy chỉnh cho marshaller

Nếu cần cùng cấu hình date/time, naming và null behavior với reader, khởi tạo `JacksonJsonObjectMarshaller` bằng `ObjectMapper` đã cấu hình theo constructor được phiên bản sử dụng hỗ trợ:

```java
@Bean
JacksonJsonObjectMarshaller<Order> orderJsonMarshaller(
        ObjectMapper batchObjectMapper) {
    return new JacksonJsonObjectMarshaller<>(batchObjectMapper);
}
```

Sau đó truyền marshaller vào builder. Việc chia sẻ cùng mapper configuration giúp reader/writer giữ một data contract nhất quán. Không thay đổi cấu hình mapper sau khi job đã bắt đầu hoặc trong lúc nhiều execution đang dùng chung mapper.

## Ghi JSON Lines bằng FlatFileItemWriter

Nếu downstream yêu cầu NDJSON, mỗi item phải được serialize thành một dòng JSON độc lập. Có thể dùng `FlatFileItemWriter` với `LineAggregator` gọi Jackson:

```java
@Bean
FlatFileItemWriter<Order> orderJsonLinesWriter(
        ObjectMapper batchObjectMapper,
        @Value("${batch.output.orders-jsonl}") Resource outputResource) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderJsonLinesWriter")
            .resource(outputResource)
            .encoding(StandardCharsets.UTF_8.name())
            .lineAggregator(order -> {
                try {
                    return batchObjectMapper.writeValueAsString(order);
                } catch (JsonProcessingException ex) {
                    throw new IllegalArgumentException(
                            "Cannot serialize order " + order.orderId(), ex);
                }
            })
            .saveState(true)
            .build();
}
```

Mỗi item được chuyển thành một JSON object trên một dòng. JSON string có newline bên trong sẽ được Jackson escape thành `\n`, vì vậy physical newline vẫn phân tách các record NDJSON. Không ghi pretty-printed JSON nhiều dòng vào writer này vì sẽ phá quy tắc một JSON value trên mỗi dòng.

Để đọc NDJSON, có thể dùng `FlatFileItemReader` và `LineMapper` parse từng dòng:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderJsonLinesReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ObjectMapper batchObjectMapper) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderJsonLinesReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .lineMapper((line, lineNumber) ->
                    batchObjectMapper.readValue(line, OrderInput.class))
            .saveState(true)
            .build();
}
```

Ví dụ trên giả định mỗi JSON value nằm trọn trên một dòng. Nếu NDJSON producer phát một object nhiều dòng vật lý, file không còn tuân theo convention line-delimited; cần thay đổi format hoặc dùng reader/parser phù hợp.

## Encoding cho FlatFileItemReader và FlatFileItemWriter

Với JSON Lines, `FlatFileItemReaderBuilder` và `FlatFileItemWriterBuilder` có cấu hình encoding. Hãy đặt UTF-8 rõ ràng:

```java
.encoding(StandardCharsets.UTF_8.name())
```

Reader giải mã byte thành text trước khi `LineMapper` parse JSON. Writer mã hóa text do `LineAggregator` tạo thành byte theo charset đã cấu hình.

Đối với `JsonItemReader`, encoding có thể được xử lý bên trong `JsonObjectReader`/JSON parser vì reader nhận một `Resource` và parser làm việc trên stream. Kiểm tra API của Spring Batch/Jackson version đang dùng để biết điểm cấu hình chính xác. Nếu cần ép UTF-8 nghiêm ngặt, dùng `JsonObjectReader` tùy chỉnh hoặc một resource/stream adapter giải mã bằng charset được chỉ định.

Không giả định `.encoding(...)` có mặt trên mọi JSON reader builder hoặc mọi version. Hãy phân biệt API của `FlatFileItemReader` với API của `JsonItemReader`.

## Date, time và timezone trong JSON

Encoding đúng không đảm bảo date/time có nghĩa giống nhau giữa producer và consumer. JSON không định nghĩa kiểu ngày giờ riêng; ngày giờ thường được biểu diễn bằng string hoặc number theo contract ứng dụng.

Ví dụ ISO-8601:

```json
{
  "businessDate": "2026-11-15",
  "createdAt": "2026-11-15T08:30:00",
  "createdInstant": "2026-11-15T01:30:00Z"
}
```

Các giá trị có ý nghĩa khác nhau:

- `LocalDate` chỉ là ngày, không có giờ hoặc timezone.
- `LocalDateTime` có ngày và giờ, không có offset/timezone.
- `Instant` là một thời điểm UTC.
- `OffsetDateTime` có offset rõ ràng.

Với dữ liệu trao đổi giữa hệ thống, thường nên dùng ISO-8601 có offset hoặc UTC `Z` khi cần xác định một thời điểm. Không ghi `LocalDateTime` rồi để consumer tự đoán timezone. Nếu dùng numeric timestamp, phải quy định epoch, đơn vị milliseconds/seconds và timezone semantics.

Ví dụ model:

```java
public record OrderEvent(
        String orderId,
        LocalDate businessDate,
        Instant createdAt) {
}
```

ObjectMapper cần `JavaTimeModule` và định dạng được thống nhất. Test round-trip phải xác nhận giá trị thời gian không bị dịch múi giờ hoặc mất precision.

## Decimal và số trong JSON

JSON number không mang metadata về precision/scale. Nếu `BigDecimal` được serialize thành number, consumer cần parse với semantics decimal phù hợp để tránh chuyển qua `double` rồi mất precision.

Ví dụ:

```json
{
  "amount": 1234567890.123456789
}
```

Đối với tiền tệ, nên dùng `BigDecimal` trong Java và cấu hình/test consumer để giữ decimal precision. Không dùng `double` cho phép tính tài chính chỉ vì JSON number có thể parse thành floating point.

Một số hệ thống chọn biểu diễn tiền dưới dạng string để bảo toàn scale/format theo contract:

```json
{
  "amount": "1234567890.123456789",
  "currency": "VND"
}
```

Đây là quyết định schema API, không phải yêu cầu encoding. Producer và consumer phải thống nhất kiểu field là number hay string.

## Null, missing field và backward compatibility

Trong JSON, field có thể bị thiếu, có giá trị `null` hoặc có giá trị cụ thể. Ba trạng thái này có thể mang ý nghĩa nghiệp vụ khác nhau.

```json
{"orderId":"O-1"}
```

```json
{"orderId":"O-1","note":null}
```

```json
{"orderId":"O-1","note":"Gọi trước"}
```

ObjectMapper có thể được cấu hình để bỏ field null hoặc ghi `null`. Reader cần có default/validation rõ ràng khi field thiếu. Thay đổi `Include.NON_NULL` hoặc naming strategy có thể thay đổi JSON contract dù encoding vẫn UTF-8.

Khi producer thêm field mới, reader nên có chính sách về unknown property phù hợp. Nếu bật fail khi gặp property không biết, một field mới có thể làm batch cũ thất bại. Nếu bỏ qua unknown fields, cần bảo đảm những field bắt buộc vẫn được validate.

## Encoding lỗi và dữ liệu mojibake

Mojibake là tình trạng ký tự bị hiển thị sai do bytes được giải mã bằng charset khác với charset dùng để encode. Ví dụ UTF-8 bytes bị đọc như Windows-1252 hoặc một code page legacy có thể làm tiếng Việt biến thành chuỗi ký tự lạ.

Các dấu hiệu:

- Tiếng Việt xuất hiện thành `Nguyá»…` hoặc ký tự không mong đợi.
- File mở trong editor này đúng nhưng batch runtime đọc sai.
- Job chạy trên Windows thành công nhưng Linux container đọc khác.
- Downstream nhận được dấu `�` (replacement character).
- JSON parser báo malformed input hoặc lỗi byte sequence.

Nguyên nhân thường gặp:

- Producer ghi theo charset mặc định của máy.
- Reader dùng charset mặc định thay vì UTF-8.
- Một hệ thống encode UTF-8 hai lần.
- File bị convert qua tool trung gian và thay đổi encoding.
- BOM hoặc byte sequence không hợp lệ ở đầu file.
- JSON string bị escape thủ công sai.

Không sửa mojibake bằng cách replace chuỗi ký tự hiển thị nếu chưa xác định bytes gốc. Hãy kiểm tra byte sequence, charset producer và decoder consumer, sau đó sửa ở ranh giới encode/decode.

## Không double-encode JSON

Một lỗi thường gặp là serialize object thành JSON string rồi serialize string đó lần nữa:

```java
String json = objectMapper.writeValueAsString(order);
String wrapped = objectMapper.writeValueAsString(json);
```

`wrapped` là JSON string chứa nội dung JSON, không phải JSON object. Ví dụ:

```json
"{\"orderId\":\"O-1\",\"amount\":100}"
```

Trong khi consumer mong đợi:

```json
{"orderId":"O-1","amount":100}
```

Với `JsonFileItemWriter`, truyền object và marshaller để writer serialize một lần. Với NDJSON, `LineAggregator` serialize object một lần cho mỗi item. Không gọi `writeValueAsString` trước rồi lại để Jackson serialize chuỗi đó như object JSON lần nữa.

## Kiểm tra byte output thay vì chỉ nhìn text

Editor có thể tự đoán encoding hoặc hiển thị nội dung đã giải mã. Để xác nhận file UTF-8, có thể đọc bytes và decode bằng UTF-8 trong test:

```java
byte[] bytes = Files.readAllBytes(outputPath);
String decoded = new String(bytes, StandardCharsets.UTF_8);

assertTrue(decoded.contains("Nguyễn Thị Ánh"));
assertFalse(decoded.startsWith("\uFEFF"));
```

Với file lớn, không dùng `readAllBytes` trong production; ví dụ chỉ phù hợp cho file test nhỏ. Test cũng nên parse lại JSON bằng Jackson để xác nhận cấu trúc hợp lệ:

```java
JsonNode root = objectMapper.readTree(outputPath.toFile());
assertEquals("Nguyễn Thị Ánh",
        root.get(0).get("customerName").asText());
```

Nếu output là NDJSON, parse từng dòng riêng thay vì gọi `readTree` trên toàn file như một JSON document.

## Restart và file JSON

Reader/writer JSON có thể tham gia restart nếu implementation hỗ trợ `ItemStream` và lưu state. `JsonItemReader` và `JsonFileItemWriter` có cơ chế state trong các phiên bản hỗ trợ; cần đặt tên ổn định và bật `saveState` khi muốn restart.

Các nguyên tắc:

- Giữ input file immutable trong suốt vòng đời job và thời gian restart.
- Dùng cùng identifying `JobParameters` khi restart cùng `JobInstance`.
- Giữ reader/writer name và cấu hình JSON tương thích.
- Giữ encoding và schema JSON không đổi giữa lần chạy đầu và restart.
- Không thay input file bằng nội dung khác tại cùng path.
- Output file của lần chạy dở cần được giữ hoặc xử lý theo quy trình staging/restart.

Nếu đổi ObjectMapper configuration giữa lần chạy đầu và restart, cùng một item có thể được serialize khác format. Điều này đặc biệt quan trọng với file output đã ghi một phần. Version hóa schema/format và giữ cấu hình tương thích trong thời gian execution có thể restart.

### Output file và transaction

File output không luôn tham gia cùng transaction database của `JobRepository`. Nếu process chết sau khi ghi bytes nhưng trước khi metadata commit, file có thể chứa output của chunk chưa được xác nhận trong checkpoint. Writer hỗ trợ transactional/restart có thể quản lý một số tình huống, nhưng không nên giả định filesystem có transaction ACID như database.

Với output quan trọng, cân nhắc ghi vào file tạm theo execution, lưu checkpoint writer, sau đó publish/rename file khi job hoàn tất. Nếu phải restart, giữ file tạm và dùng cùng path. Với filesystem khác hoặc object storage, rename có thể không atomic; dùng manifest/version và checksum.

## Validation JSON trước khi chạy batch

Encoding và syntax nên được xác nhận ở bước ingestion hoặc đầu job:

1. Kiểm tra file tồn tại và kích thước hợp lý.
2. Xác định input contract quy định UTF-8.
3. Kiểm tra BOM theo policy của hệ thống.
4. Parse JSON bằng parser có streaming nếu file lớn.
5. Xác nhận root structure đúng array hoặc NDJSON.
6. Validate required fields, type và version schema.
7. Ghi nhận checksum/version để restart đọc đúng resource.

Không parse toàn bộ file lớn thành một `JsonNode` hoặc `List` chỉ để validation nếu job cần streaming. Dùng parser streaming hoặc `JsonItemReader` để tránh giữ toàn bộ dữ liệu trong memory.

## Xử lý lỗi encoding và parse

Phân biệt các loại lỗi để chọn hành động phù hợp:

| Lỗi | Ví dụ | Hành động thường phù hợp |
| --- | --- | --- |
| Byte encoding không hợp lệ | UTF-8 sequence malformed | Fail file, quarantine và yêu cầu producer gửi lại |
| Charset sai nhưng bytes hợp lệ theo charset khác | Mojibake | Sửa contract/decoder; không tự đoán trong production |
| JSON syntax lỗi | Thiếu dấu `]`, quote chưa đóng | Fail hoặc quarantine; retry không sửa được file bất biến |
| JSON schema/data lỗi | Thiếu `orderId`, amount sai kiểu | Validation, reject record hoặc skip theo quy tắc nghiệp vụ |
| I/O tạm thời | Network mount mất kết nối | Retry có giới hạn và timeout phù hợp |
| Resource không tồn tại | File bị move/xóa | Kiểm tra claim/archive và metadata |

Không cấu hình skip rộng cho mọi exception từ JSON reader. Nếu byte stream hoặc cấu trúc array bị hỏng, reader có thể không xác định được ranh giới item tiếp theo. Skip chỉ an toàn khi có thể phục hồi ranh giới record và nghiệp vụ cho phép bỏ item.

## Kiểm thử encoding JSON

Nên kiểm thử cả serialization, deserialization và file I/O. Unit test ObjectMapper không chứng minh writer đã ghi UTF-8; test file thực tế mới kiểm tra byte encoding.

### Round-trip Unicode

Tạo object có tiếng Việt, ký tự đặc biệt, emoji và string nhiều dòng; serialize rồi parse lại:

```java
@Test
void roundTripsUnicodeAndEscapedCharacters() throws Exception {
    OrderInput original = new OrderInput(
            "O-1001",
            "Nguyễn Thị Ánh 😀",
            new BigDecimal("123456.78"));

    String json = objectMapper.writeValueAsString(original);
    OrderInput restored = objectMapper.readValue(json, OrderInput.class);

    assertEquals(original, restored);
}
```

Test này xác nhận mapper giữ dữ liệu Unicode trong memory. Cần thêm file test để xác nhận charset bytes.

### Ghi và đọc file UTF-8

Với writer, tạo output tạm, ghi item có tiếng Việt, đọc bytes bằng UTF-8 rồi parse lại. Xác nhận file không có BOM nếu contract yêu cầu no-BOM.

Với reader, tạo file bằng `Files.writeString(path, json, StandardCharsets.UTF_8)`, chạy reader và xác nhận object nhận đúng tên/ghi chú tiếng Việt. Không tạo fixture bằng default charset vì test có thể chỉ pass trên một máy.

### Test JSON array và NDJSON riêng biệt

Không dùng chung fixture cho hai format. JSON array phải có root `[` ... `]`; NDJSON phải có một JSON value trên mỗi dòng. Xác nhận reader được chọn đúng format và fail rõ ràng khi input sai cấu trúc.

### Test BOM và byte malformed

Tạo fixture có UTF-8 BOM và xác nhận hành vi theo policy: chấp nhận và bỏ BOM, hoặc từ chối với lỗi rõ ràng. Tạo byte sequence UTF-8 không hợp lệ và xác nhận strict decoder báo lỗi thay vì âm thầm tạo replacement character.

### Test date/time và decimal

Round-trip `BigDecimal`, `LocalDate`, `Instant` và `OffsetDateTime`. So sánh giá trị chính xác, bao gồm scale/precision và offset/timezone semantics. Đừng chỉ so sánh JSON string nếu thứ tự property không phải một phần contract.

### Test restart

Chạy job qua một số chunk, làm step thất bại, sau đó restart cùng identifying parameters. Xác nhận reader tiếp tục đúng item, writer tiếp tục output đúng vị trí và JSON cuối parse được. Nếu writer ghi JSON array, xác nhận chỉ có một cặp bracket và dấu phẩy đúng; nếu ghi NDJSON, xác nhận mỗi dòng parse độc lập.

## Những lỗi thường gặp

### Dùng charset mặc định

File có thể đọc đúng trên máy này nhưng sai trên máy khác. Chọn UTF-8 tường minh ở writer/reader hoặc parser boundary.

### Nhầm encoding với escaping

`\\uXXXX` không phải charset. Để Jackson xử lý escaping; để UTF-8 xử lý byte representation.

### Tự escape JSON bằng replace

Có thể bỏ sót backslash, control character hoặc surrogate pair. Dùng ObjectMapper.

### Đọc NDJSON bằng JsonItemReader

`JsonItemReader` đọc cấu trúc JSON array qua `JsonObjectReader`; NDJSON cần reader line-based hoặc custom reader.

### Ghi pretty JSON nhiều dòng vào NDJSON

Một object có thể chiếm nhiều dòng và phá ranh giới record. Dùng compact JSON một dòng cho mỗi item.

### Double serialize

Serialize object thành string rồi serialize string lần nữa sẽ tạo JSON string chứa JSON, không phải JSON object. Serialize đúng một lần.

### Bỏ qua BOM và file malformed

BOM hoặc byte sequence không hợp lệ có thể làm parser lỗi hoặc tạo ký tự replacement. Quy định rõ policy và kiểm thử.

### Thay ObjectMapper giữa restart

Schema, naming hoặc date format khác có thể làm file output không đồng nhất. Giữ cấu hình ổn định cho một logical execution.

### Chỉ test text trong editor

Editor có thể tự đoán charset. Kiểm tra bytes bằng UTF-8 decoder và parse JSON lại.

### Cho rằng JSON number giữ mọi precision tự động

Consumer có thể parse number thành floating point. Dùng `BigDecimal` và thống nhất schema cho tiền tệ.

## Nguyên tắc triển khai

Khi thiết kế JSON input/output cho Spring Batch, hãy xác định:

1. Contract quy định UTF-8 và có cho phép BOM không?
2. File là JSON array hay JSON Lines/NDJSON?
3. Reader phù hợp là `JsonItemReader`, `FlatFileItemReader` hay custom streaming reader?
4. Writer phù hợp là `JsonFileItemWriter` hay `FlatFileItemWriter` với một JSON object mỗi dòng?
5. Charset được đặt tường minh ở đúng byte/text boundary chưa?
6. ObjectMapper có naming, date/time, null, enum và number policy ổn định chưa?
7. Unicode, escaping, control characters và surrogate pairs được thư viện xử lý chưa?
8. Input malformed, BOM và byte sequence không hợp lệ được xử lý ra sao?
9. Reader/writer state, file path và mapper configuration có tương thích khi restart không?
10. Test đã kiểm tra byte output, round-trip Unicode, format structure, precision và restart chưa?

Với phần lớn pipeline trao đổi JSON, dùng UTF-8 không BOM, Jackson cho serialization/deserialization và một schema rõ ràng cho từng phiên bản dữ liệu. Chọn `JsonItemReader`/`JsonFileItemWriter` cho JSON array; chọn line-based reader/writer cho NDJSON. Luôn phân biệt byte encoding với JSON escaping, giữ cấu hình mapper ổn định và kiểm thử file bytes thực tế để phát hiện lỗi trước khi dữ liệu đi tới hệ thống downstream.

## Ghi nhớ

JSON là text; UTF-8 chuyển Unicode characters thành bytes, còn JSON escaping biểu diễn quote, backslash, newline và control characters bên trong string. Dùng UTF-8 tường minh và tránh BOM trong output trao đổi; không dựa vào default charset hoặc tự escape bằng `replace`. `JsonItemReader` phù hợp với JSON array thông qua `JsonObjectReader`/Jackson; NDJSON cần reader line-based hoặc custom reader. `JsonFileItemWriter` có thể ghi JSON object theo cấu trúc file, còn NDJSON dùng `FlatFileItemWriter` với một JSON object compact trên mỗi dòng. Cấu hình ObjectMapper nhất quán cho naming, Java time, null, enum và decimal. Giữ input/output resource và mapper contract ổn định qua restart, phân biệt lỗi encoding với lỗi JSON/schema và kiểm thử round-trip Unicode cùng byte output thực tế.
