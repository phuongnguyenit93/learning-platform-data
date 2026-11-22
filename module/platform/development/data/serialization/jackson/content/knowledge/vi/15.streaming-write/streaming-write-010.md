# Đánh giá rủi ro khi ghi nội dung thô không qua kiểm tra cấu trúc

Jackson Core cung cấp các phương thức ghi nội dung thô như `JsonGenerator.writeRaw(...)` và `writeRawValue(...)`. Chúng cho phép đưa một đoạn ký tự vào output mà không đi qua toàn bộ quy trình tạo token có kiểu như `writeString`, `writeNumber`, `writeStartObject` hoặc `writeFieldName`.

Các API raw có thể hữu ích khi ứng dụng phải ghi một đoạn JSON đã được tạo và kiểm soát ở nơi khác. Tuy nhiên, generator không phân tích đoạn raw để xác nhận nó là một giá trị JSON hợp lệ, không tự escape dữ liệu như `writeString(...)`, và không thể bảo đảm cấu trúc cuối cùng khớp với hợp đồng. Nếu đoạn raw chứa dữ liệu không đáng tin cậy, lỗi có thể dẫn đến JSON hỏng hoặc chèn thêm field/giá trị ngoài dự kiến.

Nguyên tắc quan trọng là: **dữ liệu phải được ghi bằng API có kiểu; cú pháp JSON chỉ nên được ghi bằng API raw khi ứng dụng kiểm soát và xác thực đầy đủ đoạn nội dung đó.**

## 1. Generator thông thường bảo vệ cấu trúc JSON như thế nào?

`JsonGenerator` ghi JSON theo thứ tự token. Khi dùng API có kiểu, generator biết ứng dụng đang ở ngữ cảnh nào và loại token nào được phép tiếp theo.

```java
try (JsonGenerator gen = mapper.createGenerator(output)) {
    gen.writeStartObject();
    gen.writeStringField("name", userName);
    gen.writeNumberField("age", age);
    gen.writeBooleanField("active", true);
    gen.writeEndObject();
}
```

Jackson chịu trách nhiệm:

- Ghi dấu `{`, `}`, `[`, `]` theo đúng thao tác mở/đóng container.
- Chèn dấu phẩy và dấu hai chấm ở đúng vị trí.
- Kiểm soát thứ tự field name và value trong object.
- Escape dấu ngoặc kép, dấu gạch chéo ngược và ký tự điều khiển bên trong string.
- Ghi đúng kiểu token cho string, number, boolean và null.

Ví dụ, nếu `userName` chứa dấu ngoặc kép hoặc xuống dòng, `writeStringField(...)` vẫn tạo một JSON string hợp lệ. Ứng dụng không phải tự ghép dấu ngoặc kép hay viết chuỗi escape.

## 2. Phân biệt writeRaw và writeRawValue

Hai API có tên gần giống nhau nhưng có ngữ nghĩa khác nhau.

### 2.1. writeRaw: ghi ký tự trực tiếp

`writeRaw(...)` ghi nội dung đúng như được truyền vào. Nó không tự thêm dấu ngoặc kép, không escape string, không tự thêm dấu phân cách JSON và không xử lý nội dung như một value thông thường trong trạng thái của generator.

```java
gen.writeRaw("{\"name\":\"An\"}");
```

Lời gọi này đưa đúng đoạn ký tự vào output. Generator không phân tích object vừa ghi để cập nhật trạng thái field/array bên trong đoạn đó. Nếu trộn `writeRaw(...)` với các lệnh ghi có cấu trúc, trạng thái nội bộ của generator có thể không còn khớp với những ký tự thực tế đã được ghi.

Ví dụ rủi ro:

```java
gen.writeStartObject();
gen.writeRaw("\"name\":\"An\"");
gen.writeNumberField("age", 20);
gen.writeEndObject();
```

Sau `writeStartObject()`, generator vẫn nghĩ object chưa nhận field nào vì `writeRaw(...)` không thông báo rằng một field/value đã được ghi. Khi `writeNumberField(...)` tự thêm dấu phân cách theo trạng thái đó, output có thể thành JSON không hợp lệ, chẳng hạn thiếu dấu phẩy giữa hai field.

Không dùng `writeRaw(...)` để thay thế `writeFieldName`, `writeString`, `writeNumber` hoặc các phương thức typed khác trong một object/array đang được generator quản lý.

### 2.2. writeRawValue: ghi một value thô

`writeRawValue(...)` được thiết kế để ghi một đoạn văn bản như một giá trị JSON tại vị trí value hiện tại. Generator vẫn xử lý ngữ cảnh bên ngoài: chèn dấu phẩy hoặc dấu phân cách cần thiết và cập nhật trạng thái rằng một value đã được ghi.

```java
gen.writeStartObject();
gen.writeFieldName("payload");
gen.writeRawValue("{\"code\":200,\"ok\":true}");
gen.writeEndObject();
```

Kết quả có dạng:

```json
{"payload":{"code":200,"ok":true}}
```

Điểm quan trọng: generator coi toàn bộ chuỗi raw là một value theo hợp đồng của phương thức, nhưng không parse chuỗi đó để xác nhận rằng nó thực sự chứa đúng một value JSON. Trách nhiệm bảo đảm nội dung hợp lệ thuộc về caller.

### 2.3. So sánh nhanh

| API | Xử lý ngữ cảnh/separator của generator | Tự escape string | Kiểm tra cú pháp đoạn raw |
|---|---|---|---|
| `writeString(value)` | Có | Có | Không cần; value được ghi như string token |
| `writeFieldName(name)` | Có | Có cho tên field | Không cần; generator ghi field name |
| `writeRaw(text)` | Không xử lý như một JSON value | Không | Không |
| `writeRawValue(text)` | Có, như một value | Không | Không |

Với dữ liệu thông thường, hãy dùng API typed. `writeRawValue` phù hợp hơn `writeRaw` khi cần đặt một JSON value đã được kiểm soát vào vị trí value. Dù vậy, `writeRawValue` vẫn không xác thực cấu trúc của đoạn nội dung.

## 3. Rủi ro ghi JSON không hợp lệ

Vì nội dung raw không được parse, một lỗi nhỏ trong chuỗi có thể khiến cả tài liệu không thể đọc.

Ví dụ:

```java
String raw = "{\"code\":200,\"message\":\"OK\""; // Thiếu dấu }

gen.writeStartObject();
gen.writeFieldName("result");
gen.writeRawValue(raw);
gen.writeEndObject();
```

Generator không tự bổ sung dấu `}` còn thiếu. Output cuối cùng có thể trông gần giống JSON nhưng parser sẽ báo lỗi khi đọc.

Các lỗi raw thường gặp gồm:

- Thiếu hoặc thừa dấu `{`, `}`, `[`, `]`.
- Thiếu dấu ngoặc kép quanh tên field hoặc string value.
- Dấu phẩy thừa ở cuối object/array.
- Dấu ngoặc kép hoặc dấu gạch chéo ngược trong string không được escape.
- Ghi một fragment object vào vị trí cần scalar, hoặc ngược lại.
- Đưa nhiều root value vào nơi hợp đồng yêu cầu đúng một value.
- Ghép fragment theo thứ tự khiến field/value bị đặt sai vị trí.

Một tài liệu có thể chỉ hỏng ở một nhánh dữ liệu hiếm gặp, khiến lỗi khó tái hiện. Vì vậy, không nên xem việc generator hoàn tất mà không ném exception là bằng chứng JSON raw hợp lệ.

## 4. Rủi ro chèn cấu trúc và JSON injection

Nguy hiểm hơn lỗi cú pháp là đoạn raw có thể tạo ra một JSON hợp lệ nhưng thay đổi cấu trúc mà ứng dụng dự định ghi.

Giả sử ứng dụng muốn ghi một field `metadata` lấy từ nguồn ngoài:

```java
String externalFragment = "null,\"isAdmin\":true";

gen.writeStartObject();
gen.writeStringField("message", "profile updated");
gen.writeFieldName("metadata");
gen.writeRawValue(externalFragment);
gen.writeEndObject();
```

Output có thể trở thành:

```json
{
  "message": "profile updated",
  "metadata": null,
  "isAdmin": true
}
```

Ứng dụng dự định ghi một value cho `metadata`, nhưng chuỗi raw đã chèn thêm field `isAdmin` vào object cha. Đoạn raw là dữ liệu do nguồn ngoài kiểm soát, vì vậy đây là một dạng structural injection.

Nếu consumer dùng field được chèn thêm để quyết định quyền, trạng thái hoặc luồng nghiệp vụ, tác động có thể nghiêm trọng hơn một lỗi parse. Không nên cho người dùng, request parameter, file upload hoặc dữ liệu đối tác tùy ý điều khiển fragment đưa vào `writeRaw(...)` hay `writeRawValue(...)`.

### 4.1. Ghi string từ nguồn ngoài bằng API typed

Nếu nội dung chỉ là văn bản, hãy ghi nó như string:

```java
String externalText = request.getParameter("comment");

gen.writeStartObject();
gen.writeStringField("comment", externalText);
gen.writeEndObject();
```

Ngay cả khi `externalText` chứa ký tự như `"`, `{`, `}`, `,` hoặc xuống dòng, Jackson vẫn escape chúng bên trong string. Chúng không thể trở thành field hoặc token JSON mới.

### 4.2. Ghi object từ dữ liệu đã deserialize

Nếu nguồn ngoài gửi JSON và ứng dụng muốn đưa object đó vào output, hãy parse thành `JsonNode` hoặc DTO rồi ghi qua Databind:

```java
JsonNode metadata = mapper.readTree(externalJson);

gen.writeStartObject();
gen.writeFieldName("metadata");
gen.writeTree(metadata);
gen.writeEndObject();
```

`writeTree(...)` ghi cấu trúc node thông qua codec, nhờ vậy generator quản lý cấu trúc value như một phần của output. Nếu contract yêu cầu một kiểu cụ thể, deserialize thành DTO rồi dùng `writeObject(...)` còn giúp kiểm soát kiểu và các thuộc tính được phép xuất.

## 5. Rủi ro bỏ qua escaping

Các phương thức typed tự escape string. Phương thức raw không làm việc đó.

Ví dụ, string đầu vào:

```text
He said: "Hello"
Next line
```

Ghi bằng typed API:

```java
gen.writeStringField("message", message);
```

Jackson tạo một JSON string hợp lệ, escape dấu ngoặc kép và ký tự xuống dòng. Nếu tự tạo JSON bằng raw:

```java
gen.writeRawValue("\"" + message + "\"");
```

chuỗi có dấu ngoặc kép hoặc newline có thể làm JSON hỏng hoặc thoát khỏi string context. Tự escape bằng replace cũng dễ bỏ sót backslash, control character hoặc các trường hợp Unicode.

Nếu thật sự cần tạo một JSON string token, dùng `writeString(...)`. Không cần và không nên tự thêm dấu ngoặc kép quanh giá trị Java.

## 6. Ghi tên field bằng raw cũng có rủi ro

Tên field JSON cũng là string và cần được escape. Hãy dùng:

```java
gen.writeFieldName(fieldName);
gen.writeString(value);
```

Không ghép tên field vào raw fragment:

```java
// Không an toàn: fieldName có thể chứa dấu ngoặc kép hoặc nội dung cấu trúc.
gen.writeRaw("\"" + fieldName + "\":\"" + value + "\"");
```

Nếu `fieldName` hoặc `value` đến từ dữ liệu bên ngoài, chuỗi ghép có thể làm sai cấu trúc. `writeFieldName` và `writeString` đảm nhiệm việc escape đúng vị trí.

## 7. Phân biệt kiểm tra cú pháp, schema và quy tắc nghiệp vụ

Ngay cả khi raw fragment parse được thành JSON hợp lệ, điều đó chưa bảo đảm fragment phù hợp với hợp đồng ứng dụng.

Có ba lớp kiểm tra khác nhau:

1. **Cú pháp JSON:** fragment có đúng grammar JSON và có đúng một root value không?
2. **Schema/shape:** root có đúng kiểu object/array không, field bắt buộc có tồn tại không, kiểu field có đúng không, có field lạ hoặc duplicate field không?
3. **Quy tắc nghiệp vụ và bảo mật:** giá trị có nằm trong phạm vi được phép không, người gửi có quyền cung cấp field đó không, nội dung có được phép xuất sang consumer không?

Ví dụ `{"isAdmin":true}` là JSON hợp lệ về cú pháp. Tuy nhiên, nếu payload của người dùng không được phép tự đặt quyền quản trị, ứng dụng phải loại bỏ hoặc từ chối field đó ở tầng DTO/schema/authorization. Parser chỉ kiểm tra cấu trúc JSON, không hiểu quyền nghiệp vụ.

## 8. Xác thực raw fragment trước khi ghi

Nếu ứng dụng bắt buộc nhận một fragment JSON đã được tạo ở nơi khác, tối thiểu hãy parse nó trước khi dùng. Ví dụ dưới đây kiểm tra có đúng một root value và bật phát hiện duplicate field name:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.StreamReadFeature;

static void validateSingleJsonValue(String raw) throws IOException {
    JsonFactory validationFactory = JsonFactory.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .build();

    try (JsonParser parser = validationFactory.createParser(raw)) {
        JsonToken first = parser.nextToken();
        if (first == null) {
            throw new IOException("JSON fragment is empty");
        }

        // Đọc hết cấu trúc của root value đầu tiên.
        parser.skipChildren();

        // Nếu còn token, fragment chứa root value hoặc nội dung thừa.
        if (parser.nextToken() != null) {
            throw new IOException("Expected exactly one JSON root value");
        }
    }
}
```

Parser sẽ ném lỗi nếu JSON bị cắt, sai cú pháp hoặc có duplicate field trong object khi strict duplicate detection được bật. Sau khi đọc xong root value đầu tiên, lời gọi `nextToken()` tiếp theo phát hiện nội dung dư hoặc root value thứ hai.

Đây chỉ là kiểm tra cú pháp và duplicate field. Nó không xác nhận fragment có đúng schema hay được phép theo nghiệp vụ. Nếu cần object root, kiểm tra token đầu tiên phải là `START_OBJECT`; nếu cần array, yêu cầu `START_ARRAY`. Với contract phức tạp, dùng JSON Schema validator hoặc deserialize vào DTO có kiểu rõ ràng.

Sau khi validate, nếu vẫn ghi raw để giữ nguyên lexical representation, hãy bảo đảm chính chuỗi đã validate chính là chuỗi sẽ được ghi, không có bước ghép hoặc biến đổi khác giữa hai thao tác:

```java
validateSingleJsonValue(rawFragment);

gen.writeStartObject();
gen.writeFieldName("payload");
gen.writeRawValue(rawFragment);
gen.writeEndObject();
```

Nếu không cần giữ nguyên cách viết số, escape hoặc khoảng trắng của fragment, lựa chọn dễ kiểm soát hơn là parse thành `JsonNode` rồi dùng `writeTree(...)`. Khi đó generator tạo lại cấu trúc từ node thay vì tin cậy nguyên văn chuỗi nguồn.

## 9. Strict duplicate detection không thay thế kiểm tra raw

Jackson có cơ chế phát hiện duplicate field name khi parse, và generator cũng có cơ chế kiểm tra duplicate field được ghi thông qua API field-name của nó ở các cấu hình hỗ trợ.

Tuy nhiên, nội dung được đưa qua `writeRaw(...)` hoặc `writeRawValue(...)` không được generator phân tích thành các field token. Vì vậy, không thể dựa vào duplicate detection ở generator để phát hiện hai field trùng tên nằm bên trong một raw object.

Ví dụ fragment:

```json
{"role":"user","role":"admin"}
```

Đây là nội dung có duplicate member name. Các parser/consumer có thể xử lý khác nhau, ví dụ giữ giá trị đầu, giữ giá trị cuối hoặc báo lỗi. Nếu fragment đến từ nguồn ngoài, bật `StreamReadFeature.STRICT_DUPLICATE_DETECTION` ở parser xác thực để phát hiện trường hợp này.

Với hợp đồng API, nên từ chối duplicate field thay vì dựa vào hành vi không thống nhất giữa các consumer.

## 10. Raw output có thể làm sai pretty printing và framing

Pretty printer chỉ có thể định dạng các cấu trúc mà generator biết. Nội dung raw được chèn nguyên văn nên khoảng trắng, xuống dòng và indentation bên trong fragment không nhất thiết được chuẩn hóa.

Tương tự, generator quản lý một JSON document thông thường theo root value. Nếu raw fragment chứa nhiều root value hoặc thêm token ngoài cấu trúc mong muốn, output có thể không còn là một tài liệu JSON duy nhất.

Ví dụ, một raw fragment có thể chứa object hợp lệ nhưng cũng có thể chứa hai root value liên tiếp:

```text
{"id":1}{"id":2}
```

Mỗi object riêng có thể parse được, nhưng chuỗi nối liền không phải một JSON document đơn theo contract thông thường. Nếu hệ thống cần nhiều record, hãy đặt chúng trong một array hoặc dùng framing rõ ràng như JSON Lines/JSON Text Sequence.

## 11. Các lựa chọn an toàn hơn raw output

| Nhu cầu | API nên ưu tiên | Lý do |
|---|---|---|
| Ghi văn bản do người dùng cung cấp | `writeString` / `writeStringField` | Tự quote và escape string |
| Ghi số, boolean, null | `writeNumber`, `writeBoolean`, `writeNull` | Giữ đúng kiểu JSON và trạng thái generator |
| Ghi tên thuộc tính động | `writeFieldName` | Escape tên field và cập nhật context |
| Ghi một object Java | `writeObject` với codec phù hợp | Databind áp dụng serializer và annotation |
| Ghi một cây JSON | `writeTree` với codec phù hợp | Generator nhận cấu trúc node thay vì raw text |
| Nhận JSON ngoài rồi xuất lại | Parse, kiểm tra schema, sau đó `writeTree`/`writeObject` | Kiểm soát shape và dữ liệu được phép |
| Giữ nguyên byte/lexical JSON đã tin cậy | Validate đầy đủ rồi mới cân nhắc `writeRawValue` | Giữ nguyên nội dung nhưng vẫn có ranh giới kiểm tra |

Đối với API có DTO ổn định, deserialize thành DTO và serialize lại thường rõ ràng hơn giữ nguyên fragment. DTO giúp giới hạn field được nhận và field được xuất theo contract.

## 12. Khi nào raw API có thể phù hợp?

Raw API không phải lúc nào cũng sai. Có một số tình huống có thể cân nhắc:

- Ứng dụng ghép các literal JSON tĩnh được viết trong source code và đã có test.
- Một thành phần đã tạo ra một JSON value hoàn chỉnh, có nguồn gốc tin cậy và đã được xác thực trước.
- Cần giữ nguyên biểu diễn văn bản của một JSON value vì yêu cầu tương thích hoặc chữ ký/hash, sau khi đã xác định rõ quy tắc canonicalization và validation.
- Một integration đặc thù yêu cầu chèn đoạn raw vào output và đã kiểm soát đầy đủ framing, encoding, cấu trúc và trust boundary.

Ngay cả trong các trường hợp đó, hãy giới hạn phạm vi raw fragment, ghi rõ hợp đồng của nó và tránh trộn `writeRaw(...)` với các lệnh token có cấu trúc theo cách khiến trạng thái generator không còn đồng bộ.

Không nên dùng raw API chỉ vì muốn tiết kiệm vài dòng code hoặc cho rằng nó luôn nhanh hơn. Parse/validate có chi phí, nhưng lỗi cấu trúc, injection và khó bảo trì có thể đắt hơn nhiều. Nếu hiệu năng là lý do, hãy đo bằng benchmark đại diện trước khi chọn cách triển khai.

## 13. Ví dụ tổng hợp: ghi dữ liệu ngoài một cách an toàn

Giả sử request có trường `comment` là văn bản và trường `metadataJson` là JSON do một hệ thống đối tác gửi. `comment` phải luôn được ghi như string; metadata cần được parse và kiểm tra trước khi đưa vào output.

```java
public void writePartnerEvent(
        String comment,
        String metadataJson,
        ObjectMapper mapper,
        OutputStream output
) throws IOException {
    // Parse thành tree để xác nhận cú pháp trước khi ghi.
    JsonNode metadata = mapper.reader()
            .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .readTree(metadataJson);

    if (metadata == null || !metadata.isObject()) {
        throw new IOException("metadata must be a JSON object");
    }

    // Tại đây có thể áp dụng thêm schema/allowlist cho các field metadata.
    try (JsonGenerator gen = mapper.createGenerator(output)) {
        gen.writeStartObject();
        gen.writeStringField("comment", comment);

        gen.writeFieldName("metadata");
        gen.writeTree(metadata);

        gen.writeEndObject();
    }
}
```

Ví dụ dùng `FAIL_ON_TRAILING_TOKENS` để từ chối dữ liệu có token sau root value và kiểm tra metadata phải là object. Nếu cần phát hiện duplicate field trong metadata, hãy dùng `JsonFactory` có `StreamReadFeature.STRICT_DUPLICATE_DETECTION` cho parser được dùng để đọc fragment. Nếu cần giới hạn field, kiểu hoặc quyền cung cấp dữ liệu, bổ sung schema/allowlist ở tầng ứng dụng.

Điểm quan trọng là `comment` luôn được ghi bằng `writeStringField`, còn `metadataJson` được parse thành tree và ghi lại bằng `writeTree`. Dữ liệu ngoài không được tự quyết định vị trí field hoặc cấu trúc của object cha.

## 14. Danh sách kiểm tra trước khi dùng raw API

Trước khi gọi `writeRaw` hoặc `writeRawValue`, hãy xác định:

1. Nội dung đến từ literal do code kiểm soát hay từ request/file/hệ thống ngoài?
2. Nội dung là một JSON value hoàn chỉnh, một phần cấu trúc hay chỉ là text?
3. Phương thức có làm thay đổi trạng thái generator như mong đợi không?
4. String và field name đã được escape đúng chưa?
5. Fragment có đúng một root value và đúng loại root không?
6. Có duplicate field name hoặc field ngoài schema không?
7. Có thể parse fragment và kiểm tra schema trước khi ghi không?
8. Có thể dùng typed API, `writeObject` hoặc `writeTree` thay thế không?
9. Nếu giữ nguyên raw text, chuỗi được validate có chắc chắn là chuỗi được ghi không?
10. Output có được kiểm tra lại và chỉ công bố sau khi ghi thành công không?

Nếu không trả lời được các câu hỏi về nguồn gốc, cấu trúc và validation, không nên đưa dữ liệu đó vào raw output.

## 15. Ghi nhớ

`writeRaw(...)` ghi ký tự trực tiếp và không quản lý chúng như một token/value JSON trong trạng thái generator. `writeRawValue(...)` đặt nội dung vào vị trí value và cập nhật context bên ngoài, nhưng không parse hay xác nhận rằng nội dung là đúng một value JSON hợp lệ. Cả hai đều bỏ qua việc escape và kiểm tra cấu trúc của đoạn raw.

Rủi ro gồm JSON hỏng, sai trạng thái generator, duplicate field, bỏ qua schema và JSON structural injection khi dữ liệu không đáng tin cậy được phép thêm token hoặc field. Hãy ưu tiên `writeString`, `writeFieldName`, `writeNumber`, `writeObject` và `writeTree`. Nếu bắt buộc dùng raw, parse toàn bộ fragment, kiểm tra đúng một root value, phát hiện duplicate field, xác thực schema/allowlist và chỉ ghi đúng chuỗi đã được kiểm tra. Việc generator không ném exception không chứng minh output raw an toàn hoặc đúng hợp đồng.
