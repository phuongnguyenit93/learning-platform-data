# Tránh công bố tài liệu JSON chưa kết thúc đầy đủ

Khi tạo JSON bằng Jackson, dữ liệu có thể được ghi dần ra file, HTTP response, socket hoặc message stream. Nếu ứng dụng công bố đầu ra trước khi hoàn tất root value, consumer có thể nhận một tài liệu bị cắt dở và không parse được. Nguy hiểm hơn, một số cấu hình khi đóng generator có thể tự đóng các object hoặc array còn mở, khiến phần dữ liệu đã ghi trở thành JSON hợp lệ về cú pháp nhưng vẫn thiếu nội dung nghiệp vụ.

Vì vậy, cần phân biệt ba trạng thái:

1. **Đang tạo**: generator vẫn đang ghi token và tài liệu chưa hoàn chỉnh.
2. **Đã hoàn tất**: root value đã được kết thúc tường minh, quá trình ghi và đóng tài nguyên thành công.
3. **Đã công bố**: dữ liệu hoàn chỉnh đã được đưa đến nơi consumer có thể đọc.

Không nên xem flush hoặc close là bằng chứng duy nhất rằng tài liệu đã hoàn tất. Ứng dụng cần kiểm soát thời điểm công bố, xử lý lỗi ghi và chọn cách xuất phù hợp với loại đích.

## 1. Một JSON document chỉ hoàn chỉnh khi root value đã kết thúc

Jackson Core dùng JsonGenerator để ghi JSON theo token. Với object, ứng dụng bắt đầu bằng writeStartObject() và kết thúc bằng writeEndObject(). Với array, cặp tương ứng là writeStartArray() và writeEndArray().

Ví dụ:

~~~java
JsonGenerator generator = mapper.getFactory().createGenerator(outputStream);

generator.writeStartObject();
generator.writeStringField("orderId", "ORD-100");

generator.writeArrayFieldStart("items");
generator.writeString("BOOK-01");
generator.writeString("PEN-02");
generator.writeEndArray();

generator.writeEndObject();
generator.flush();
~~~

Dữ liệu chỉ có root object hoàn chỉnh sau khi writeEndObject() thành công. Nếu chương trình dừng sau writeArrayFieldStart() hoặc khi đang ghi phần tử, JSON vẫn còn cấu trúc chưa đóng.

Ví dụ phần dữ liệu chưa hoàn chỉnh có thể trông như sau:

~~~json
{
  "orderId": "ORD-100",
  "items": [
    "BOOK-01",
    "PEN-02"
~~~

Parser phía nhận sẽ gặp EOF khi vẫn đang chờ kết thúc array và object.

Một root value có thể là object, array hoặc scalar. Quy tắc chung vẫn giống nhau: phải ghi xong toàn bộ root value theo cấu trúc JSON trước khi xem tài liệu là hoàn chỉnh.

## 2. Phân biệt writeEnd, flush và close

Ba thao tác này có trách nhiệm khác nhau:

| Thao tác | Trách nhiệm | Có chứng minh tài liệu hoàn chỉnh không? |
|---|---|---|
| writeEndObject() / writeEndArray() | Ghi token đóng cấu trúc hiện tại. | Chỉ hoàn tất cấu trúc tương ứng; cần kết thúc toàn bộ root và các bước ghi còn lại. |
| flush() | Đẩy dữ liệu đang được buffer xuống đích bên dưới. | Không. Có thể flush một tài liệu vẫn còn dang dở. |
| close() | Kết thúc generator và giải phóng tài nguyên liên quan. | Không tự chứng minh nghiệp vụ đã ghi đủ dữ liệu. |

Ví dụ:

~~~java
generator.writeStartObject();
generator.writeStringField("status", "created");
generator.flush();
~~~

Sau flush(), các byte hiện có có thể đã được đẩy ra OutputStream, nhưng object vẫn chưa có dấu ngoặc đóng. Nếu consumer đọc ngay, họ có thể nhận JSON chưa hoàn chỉnh.

Thứ tự hợp lý cho một document đơn là:

1. Ghi toàn bộ field và node con.
2. Ghi token kết thúc array/object ở mọi cấp.
3. Xác nhận root đã kết thúc.
4. Flush và đóng generator thành công.
5. Chỉ sau đó mới công bố dữ liệu cho consumer.

Flush phục vụ việc chuyển dữ liệu qua buffer. Nó không phải thao tác commit. Close giải phóng generator và stream theo cấu hình, nhưng cũng không thay thế việc kiểm tra rằng ứng dụng đã ghi đủ các trường cần thiết.

## 3. Lưu ý AUTO_CLOSE_JSON_CONTENT khi đóng generator

Jackson JsonGenerator có feature AUTO_CLOSE_JSON_CONTENT. Khi feature này bật, việc đóng generator có thể tự ghi các token đóng cho object hoặc array còn mở.

Ví dụ, chương trình bắt đầu ghi:

~~~java
generator.writeStartObject();
generator.writeStringField("orderId", "ORD-100");

// Một lỗi xảy ra trước khi ghi các field còn lại.
generator.close();
~~~

Nếu AUTO_CLOSE_JSON_CONTENT được bật, generator có thể tự đóng object đang mở. File kết quả có thể trở thành:

~~~json
{
  "orderId": "ORD-100"
}
~~~

JSON này hợp lệ về cú pháp, nhưng có thể thiếu customer, items, total hoặc các field mà nghiệp vụ yêu cầu. Đây là lý do không thể chỉ parse lại file thành công rồi kết luận báo cáo đã được tạo đầy đủ.

Với quy trình ghi staging cần phát hiện rõ trường hợp ghi dở, có thể tắt feature:

~~~java
generator.disable(JsonGenerator.Feature.AUTO_CLOSE_JSON_CONTENT);
~~~

Khi đó, close() không tự đóng các array/object còn mở. Tuy nhiên, ứng dụng vẫn phải xử lý lỗi và xóa file tạm nếu quá trình tạo thất bại. Việc tắt feature không tự biến output thành một giao dịch nguyên tử.

Nếu vẫn để feature mặc định, hãy bảo đảm output chưa được công bố và chỉ publish khi luồng tạo tài liệu hoàn tất thành công. Không dùng việc close() tự sửa cấu trúc làm tín hiệu thành công.

## 4. Không ghi trực tiếp lên file cuối cùng khi cần bảo đảm nguyên tử

Nếu ứng dụng ghi thẳng vào file đích, consumer khác có thể đọc file trong lúc nó đang được tạo. Khi đó, họ có thể nhìn thấy file rỗng, file mới ghi một phần hoặc file cũ đã bị ghi đè dở.

Một cách phổ biến là ghi vào file tạm trong cùng thư mục, đóng thành công rồi mới đổi tên sang file cuối:

~~~text
Tạo file tạm
    |
    v
Ghi JSON bằng JsonGenerator
    |
    v
Kết thúc root + flush + close thành công
    |
    v
Di chuyển/đổi tên nguyên tử sang file đích
    |
    v
Consumer nhìn thấy tài liệu hoàn chỉnh
~~~

Ví dụ:

~~~java
import com.fasterxml.jackson.core.JsonEncoding;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public void writeOrderAtomically(
        ObjectMapper mapper,
        Order order,
        Path target) throws IOException {

    Path absoluteTarget = target.toAbsolutePath();
    Path directory = absoluteTarget.getParent();

    Path temporary = Files.createTempFile(
        directory,
        absoluteTarget.getFileName().toString(),
        ".tmp"
    );

    boolean published = false;

    try {
        try (OutputStream output = Files.newOutputStream(temporary);
             JsonGenerator generator = mapper.getFactory()
                 .createGenerator(output, JsonEncoding.UTF8)) {

            generator.disable(JsonGenerator.Feature.AUTO_CLOSE_JSON_CONTENT);

            generator.writeStartObject();
            generator.writeStringField("orderId", order.id());
            generator.writeNumberField("quantity", order.quantity());
            generator.writeEndObject();

            generator.flush();
        }

        Files.move(
            temporary,
            absoluteTarget,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING
        );

        published = true;
    } finally {
        if (!published) {
            Files.deleteIfExists(temporary);
        }
    }
}
~~~

Ví dụ giả định thư mục đích đã tồn tại và lớp Order có các accessor id() và quantity(). Cần import IOException và các kiểu Jackson tương ứng.

Điểm quan trọng của quy trình:

- File tạm nằm cùng thư mục hoặc cùng filesystem với file đích để có cơ hội hỗ trợ atomic move.
- Nếu ghi token, flush hoặc close ném exception, chương trình không chạy đến bước move.
- Nếu move thất bại, file đích cũ vẫn được giữ theo hành vi của filesystem và file tạm được dọn trong finally.
- Chỉ sau khi move thành công, tên file cuối mới trỏ đến nội dung đã ghi xong.

ATOMIC_MOVE yêu cầu filesystem hỗ trợ thao tác nguyên tử. Nếu filesystem không hỗ trợ, Files.move có thể ném AtomicMoveNotSupportedException. Khi tính nguyên tử là yêu cầu bắt buộc, hãy coi đó là lỗi publish và giữ file đích hiện tại; không âm thầm chuyển sang cách copy/ghi đè có thể để lộ file dở. Hành vi thay thế file đích đã tồn tại cùng ATOMIC_MOVE cũng có thể phụ thuộc filesystem, nên cần kiểm tra môi trường triển khai.

Đổi tên nguyên tử giúp consumer không nhìn thấy trạng thái ghi dở ở file đích. Nó không tự bảo đảm dữ liệu đã được ghi bền vững qua mất điện; nếu yêu cầu durability ở mức filesystem, cần thêm chiến lược đồng bộ dữ liệu và metadata phù hợp với nền tảng.

## 5. Tách trạng thái tạo dữ liệu khỏi trạng thái công bố

Một file có thể đã tồn tại nhưng chưa sẵn sàng cho consumer. Vì vậy, hệ thống nên có trạng thái rõ ràng:

| Trạng thái | Ý nghĩa |
|---|---|
| WRITING | Producer đang tạo nội dung. |
| COMPLETE | Root JSON đã ghi xong, generator/stream đóng thành công. |
| PUBLISHED | Consumer có thể truy cập qua tên hoặc địa chỉ chính thức. |
| FAILED | Quá trình tạo hoặc công bố thất bại. |

Có thể biểu diễn trạng thái bằng metadata riêng hoặc quy ước tên file:

~~~text
orders/ORD-100.json.tmp
orders/ORD-100.json
~~~

Producer ghi vào .tmp. Sau khi hoàn tất, producer đổi tên sang .json. Consumer chỉ quét file có đuôi .json.

Không nên để consumer quét mọi file rồi đoán file nào đã hoàn tất dựa trên thời gian sửa đổi hoặc kích thước đang ổn định. Một file có thể tạm ngừng ghi trong thời gian dài mà vẫn chưa hoàn chỉnh.

Nếu dùng manifest, chỉ cập nhật manifest sau khi file dữ liệu đã hoàn tất và được publish. Manifest có thể chứa tên file, kích thước, checksum, số bản ghi và thời điểm tạo để consumer kiểm tra tính toàn vẹn.

## 6. Kiểm tra nội dung trước khi công bố

Kết thúc root JSON mới chỉ bảo đảm cấu trúc cú pháp. Ứng dụng còn cần xác nhận các điều kiện nghiệp vụ đã được đáp ứng.

Ví dụ, báo cáo đơn hàng có thể cần:

- Có orderId.
- Có danh sách items đã xử lý hết.
- Có tổng tiền đã tính.
- Có trạng thái báo cáo hoàn tất.
- Có số lượng bản ghi bằng số dự kiến.
- Có checksum hoặc metadata tương ứng nếu quy trình yêu cầu.

Một object có thể hoàn toàn hợp lệ về JSON nhưng vẫn thiếu một phần dữ liệu cần thiết. Do đó, trước khi publish, nên có bước kiểm tra điều kiện hoàn thành ở tầng ứng dụng.

Có thể kiểm tra lại file tạm bằng Jackson sau khi generator đã đóng:

~~~java
try (InputStream input = Files.newInputStream(temporary)) {
    ObjectReader strictReader = mapper.reader()
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    JsonNode document = strictReader.readTree(input);

    if (!document.isObject()
            || !document.hasNonNull("orderId")
            || !document.path("items").isArray()) {
        throw new IOException("Generated document is incomplete");
    }
}
~~~

Đoạn code này minh họa kiểm tra cấu trúc cơ bản. Trong dự án, cần kiểm tra đúng các field và ràng buộc của tài liệu thực tế.

FAIL_ON_TRAILING_TOKENS giúp từ chối token dư sau root. Nó không xác nhận rằng mọi field nghiệp vụ bắt buộc đều có mặt. Hãy kết hợp parse, validation và metadata hoàn tất theo yêu cầu.

## 7. Ghi JSON ra HTTP response

HTTP response là trường hợp khó hơn file tạm. Khi byte đã được gửi đến client hoặc response đã commit, server không thể thu hồi phần nội dung đã gửi.

Nếu serialize trực tiếp vào response stream:

~~~java
mapper.writeValue(response.getOutputStream(), report);
~~~

Jackson có thể ghi dữ liệu dần. Nếu serializer, getter, custom serializer hoặc tầng I/O ném lỗi giữa chừng, client có thể nhận một phần JSON. Khi response đã commit, server thường không thể đổi status code hoặc thay body bằng lỗi JSON khác.

Với response có kích thước vừa phải, có thể serialize hoàn chỉnh vào byte array trước, sau đó mới ghi response:

~~~java
byte[] body = mapper.writeValueAsBytes(report);

response.setStatus(HttpServletResponse.SC_OK);
response.setContentType("application/json");
response.setCharacterEncoding(StandardCharsets.UTF_8.name());
response.setContentLength(body.length);

response.getOutputStream().write(body);
~~~

Nếu serialize thất bại, ứng dụng chưa ghi body vào response và vẫn có cơ hội xử lý lỗi ở tầng HTTP. Khi serialize thành công, body đã hoàn chỉnh trong bộ nhớ trước khi bắt đầu gửi.

Cách này tiêu tốn bộ nhớ tỷ lệ với kích thước output. Với báo cáo lớn, có thể ghi ra file tạm hoặc spool storage, xác nhận hoàn tất rồi mới stream file đó đến response. Dù vậy, lỗi mạng trong lúc gửi vẫn có thể khiến client nhận thiếu byte; client phải kiểm tra kết thúc response và parse đầy đủ document.

Không flush response trước khi quá trình tạo body hoàn tất nếu endpoint hứa trả một JSON document đơn. Flush có thể commit response sớm và khiến ứng dụng mất khả năng thay thế body khi gặp lỗi.

## 8. Khi nào streaming trực tiếp là phù hợp?

Streaming trực tiếp hữu ích khi output rất lớn và không thể giữ toàn bộ trong bộ nhớ. Tuy nhiên, nó thay đổi hợp đồng về khả năng phục hồi.

Nếu server gửi một JSON array rất lớn theo thời gian thực:

~~~json
[
  {"id": 1},
  {"id": 2},
  {"id": 3}
~~~

client có thể đã nhận một số phần tử trước khi server gặp lỗi. Phần array chưa có END_ARRAY, nên toàn bộ document chưa hoàn chỉnh.

Có hai hướng thiết kế:

**Một document nguyên tử.** Chỉ công bố sau khi đã tạo xong toàn bộ nội dung, thường bằng file tạm, spool storage hoặc buffer. Phù hợp khi client chỉ chấp nhận toàn bộ báo cáo.

**Một stream bản ghi độc lập.** Giao thức cho phép consumer xử lý từng record đã hoàn tất và nhận biết stream có kết thúc bình thường hay không. Khi đó, record trước có thể được giữ lại dù record sau lỗi, nhưng giao thức phải quy định cách phát hiện kết thúc bất thường.

Không nên dùng streaming trực tiếp rồi mô tả kết quả như một file JSON hoàn chỉnh nếu hệ thống không có cơ chế xác nhận stream kết thúc.

## 9. Công bố NDJSON theo từng bản ghi hoàn chỉnh

NDJSON (JSON Lines) cho phép mỗi dòng là một JSON document độc lập. Nó phù hợp với export lớn, log hoặc message stream khi consumer có thể xử lý từng record.

Ví dụ:

~~~text
{"id":1,"event":"created"}
{"id":2,"event":"updated"}
{"id":3,"event":"deleted"}
~~~

Mỗi record nên được serialize hoàn chỉnh trước khi đưa vào stream. Có thể dùng byte array làm buffer cho một record:

~~~java
byte[] record = mapper.writeValueAsBytes(event);

output.write(record);
output.write('\n');
output.flush();
~~~

Việc serialize vào byte array trước giúp phát hiện lỗi mapping trước khi ghi record đó ra stream. Dấu newline được ghi sau JSON, đóng vai trò ranh giới record theo quy ước của ứng dụng.

Tuy nhiên, ghi byte array và newline xuống socket không tạo ra một giao dịch mạng nguyên tử. Nếu kết nối đứt giữa chừng, consumer có thể nhận record thiếu byte hoặc thiếu delimiter. Consumer cần chỉ chấp nhận một dòng sau khi đã nhận đủ delimiter theo framing đã thống nhất và parse thành công.

Với yêu cầu toàn vẹn cao hơn, có thể dùng frame có độ dài và checksum:

~~~text
[length][JSON bytes][checksum]
[length][JSON bytes][checksum]
...
~~~

Consumer đọc đủ số byte theo length, kiểm tra checksum rồi mới xử lý record. Cách này giúp phát hiện frame bị cắt hoặc hỏng rõ ràng hơn chỉ dựa vào newline.

Nếu giao thức cho phép stream bị kết thúc bất thường, cần có end marker, số record dự kiến hoặc manifest để phân biệt stream hoàn tất với stream dừng giữa chừng.

## 10. Xử lý lỗi trong khi serialize

Lỗi có thể xảy ra ở nhiều thời điểm:

- Trước khi bắt đầu ghi root.
- Sau khi đã ghi một số field.
- Trong custom serializer.
- Khi đọc getter của object nguồn.
- Khi ghi xuống file hoặc socket.
- Khi flush buffer.
- Khi close generator hoặc stream.

Không nên bắt exception rồi tiếp tục publish phần output đã tạo dở.

Ví dụ quy trình an toàn:

~~~java
Path temporary = createTemporaryFile();
boolean complete = false;

try {
    writeWholeDocument(temporary);
    validateGeneratedDocument(temporary);
    complete = true;
} finally {
    if (!complete) {
        Files.deleteIfExists(temporary);
    }
}

if (complete) {
    publishTemporaryFile(temporary);
}
~~~

Trong code thực tế, nên đặt việc publish và dọn file trong cùng một khối try/finally để tránh rò rỉ file tạm nếu move thất bại. Biến complete chỉ nên chuyển thành true sau khi mọi thao tác tạo và xác nhận hoàn tất đã thành công.

Nếu close() ném exception, không publish. Đóng stream là một phần của quá trình ghi; lỗi khi flush/close có thể cho thấy byte chưa được chuyển xuống đích thành công.

Với HTTP, lỗi sau khi response đã commit không thể được khắc phục bằng cách ghi thêm một JSON error object vào cuối body. Client có thể nhìn thấy hai root value hoặc một document sai cú pháp. Hãy để kết nối kết thúc và client xử lý response không hoàn chỉnh theo giao thức; log lỗi bằng correlation id để điều tra.

## 11. Không dùng AUTO_CLOSE_JSON_CONTENT như cơ chế hoàn thiện nghiệp vụ

AUTO_CLOSE_JSON_CONTENT giúp generator đóng các cấu trúc JSON còn mở khi close. Nó có ích khi việc đóng cấu trúc là điều mong muốn, nhưng không biết ứng dụng đã ghi đủ dữ liệu nghiệp vụ hay chưa.

Ví dụ một báo cáo cần 1000 bản ghi, nhưng lỗi xảy ra sau bản ghi thứ 400. Generator có thể đóng array và object để tạo một JSON document parse được với 400 bản ghi. Nếu ứng dụng công bố file đó, consumer không biết 600 bản ghi còn thiếu.

Vì vậy, hãy lưu thêm điều kiện hoàn tất ở tầng ứng dụng:

- Số bản ghi đã ghi bằng số bản ghi dự kiến.
- Mọi bước truy vấn và chuyển đổi đã thành công.
- Các field tổng hợp đã được tính.
- Root đã được đóng tường minh.
- Generator và stream đã flush/close thành công.
- Bước publish đã hoàn thành.

Nếu không biết trước số bản ghi, có thể dùng trạng thái hoàn tất hoặc manifest được ghi sau cùng. Một file JSON hợp lệ về cú pháp không thay thế metadata hoàn tất của quy trình.

## 12. Kiểm tra root value và dữ liệu dư

Khi tạo một JSON document đơn, ứng dụng nên ghi đúng một root value. Nếu dùng JsonGenerator thủ công, hãy tổ chức code sao cho chỉ có một nhánh tạo root và nhánh đó kết thúc rõ ràng.

Khi đọc lại hoặc consumer deserialize, có thể bật FAIL_ON_TRAILING_TOKENS:

~~~java
ObjectReader reader = mapper.readerFor(Report.class)
    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

Report report = reader.readValue(inputStream);
~~~

Feature này phát hiện token thứ hai sau root. Nó không phát hiện việc một root object có ít record hơn dự kiến nếu object vẫn hoàn chỉnh.

Nếu định dạng là NDJSON hoặc root-value sequence, nhiều root value là chủ đích. Không áp dụng chính sách một root cho toàn bộ stream; hãy đọc theo từng frame hoặc từng record.

## 13. Kiểm thử trường hợp ghi thành công và ghi dở

Một test nên kiểm tra:

- Output hoàn chỉnh parse được.
- Output có đúng một root value.
- Lỗi trong khi tạo không thay thế file đích.
- File tạm được dọn khi publish thất bại.
- Số record và metadata hoàn tất khớp với dữ liệu nguồn.
- Consumer không coi record thiếu delimiter hoặc thiếu frame là hoàn chỉnh.

Ví dụ kiểm tra generator tạo một document hoàn chỉnh:

~~~java
@Test
void writesACompleteJsonDocument() throws Exception {
    ByteArrayOutputStream output = new ByteArrayOutputStream();

    try (JsonGenerator generator = mapper.getFactory().createGenerator(output)) {
        generator.writeStartObject();
        generator.writeStringField("orderId", "ORD-100");
        generator.writeEndObject();
    }

    ObjectReader reader = mapper.reader()
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    JsonNode document = reader.readTree(output.toByteArray());

    assertTrue(document.isObject());
    assertEquals("ORD-100", document.path("orderId").asText());
}
~~~

Có thể kiểm tra không công bố file khi serializer thất bại bằng một serializer cố ý ném exception sau khi ghi một phần dữ liệu. Test cần xác nhận file đích cũ vẫn giữ nguyên và file tạm không còn sau khi phương thức kết thúc.

Đối với HTTP, integration test có thể kiểm tra status và body khi serialize thành công, cũng như phản hồi lỗi nếu tạo body thất bại trước khi response commit. Không nên giả định server có thể đổi status sau khi đã gửi một phần body.

## 14. Chọn chiến lược công bố theo loại đầu ra

| Đầu ra | Chiến lược phù hợp |
|---|---|
| File JSON đơn | Ghi file tạm, đóng thành công, rồi atomic move sang tên chính thức. |
| HTTP response nhỏ/vừa | Serialize vào byte array trước, sau đó mới ghi response. |
| HTTP response rất lớn | Spool vào file/object storage rồi stream sau khi hoàn tất, hoặc dùng giao thức streaming có trạng thái kết thúc rõ ràng. |
| NDJSON | Serialize từng record vào buffer, ghi record và delimiter, consumer xác nhận frame hoàn chỉnh. |
| Message queue | Gửi một message hoàn chỉnh; dùng broker acknowledgement sau khi publish thành công. |
| Batch export | Ghi các file dữ liệu tạm, kiểm tra số lượng/checksum, rồi công bố manifest hoặc đổi tên batch. |

Không có một chiến lược phù hợp cho mọi đích. File và object storage có thể hỗ trợ staging/rename hoặc multipart completion; HTTP response có thể commit không thể đảo ngược; message queue có cơ chế acknowledgement riêng. Hãy thiết kế ranh giới hoàn tất theo khả năng thật của transport.

## 15. Quy trình thực hành để tránh công bố JSON dở dang

Khi triển khai một chức năng export hoặc streaming, hãy đi theo trình tự:

1. Xác định output là một JSON document đơn hay một stream gồm nhiều record.
2. Xác định ai có thể nhìn thấy dữ liệu trong lúc producer đang ghi.
3. Chọn buffer, file tạm hoặc framing để giữ dữ liệu chưa hoàn tất ở trạng thái riêng.
4. Ghi đầy đủ token và kết thúc root value tường minh.
5. Flush và close; xem mọi lỗi ở các bước này là lỗi tạo tài liệu.
6. Kiểm tra điều kiện nghiệp vụ như số record, field bắt buộc và checksum.
7. Publish bằng thao tác phù hợp với đích: atomic move, ghi response sau khi buffer hoàn tất hoặc publish message.
8. Nếu có lỗi, dọn dữ liệu tạm và giữ trạng thái chưa công bố.
9. Ở consumer, parse đến hết document/frame và từ chối dữ liệu bị cắt hoặc không có dấu hiệu hoàn tất.

## Kết luận

Một JSON document chưa được công bố cho đến khi root value đã được kết thúc tường minh, dữ liệu đã flush/close thành công và các điều kiện hoàn tất của ứng dụng đã được xác nhận. writeEndObject() hoặc writeEndArray() đóng cấu trúc; flush() đẩy buffer; close() giải phóng tài nguyên và có thể tự đóng cấu trúc nếu AUTO_CLOSE_JSON_CONTENT được bật. Không thao tác nào trong số đó tự xác nhận dữ liệu nghiệp vụ đã đầy đủ.

Với file, hãy ghi staging rồi atomic move khi có hỗ trợ. Với HTTP, buffer hoặc spool trước khi commit response nếu cần một document nguyên tử. Với NDJSON hoặc message stream, định nghĩa delimiter/frame và tín hiệu kết thúc để consumer nhận diện record hoàn chỉnh. Khi có lỗi, không publish output dở dang và không dùng một JSON parse được như bằng chứng duy nhất rằng toàn bộ dữ liệu mong đợi đã được tạo.

