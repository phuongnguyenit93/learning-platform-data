# Thiết kế chính sách dừng tài liệu hoặc tách bản ghi lỗi

## 1. Vì sao cần chính sách lỗi cho pipeline JSON?

Một chương trình nhập dữ liệu thường xử lý nhiều bản ghi trong cùng một tài liệu hoặc một luồng. Với Jackson, dữ liệu có thể được đọc bằng Streaming API, chuyển thành POJO hoặc JsonNode, kiểm tra nghiệp vụ rồi ghi kết quả ra file hay dịch vụ khác.

Trong quá trình này, một bản ghi có thể gặp lỗi vì nhiều nguyên nhân:

- JSON sai cú pháp hoặc bị cắt giữa chừng.
- Cấu trúc JSON hợp lệ nhưng không khớp kiểu Java đích.
- Giá trị ánh xạ được nhưng vi phạm quy tắc nghiệp vụ.
- Bản ghi tham chiếu đến dữ liệu không tồn tại.
- Nguồn hoặc đích gặp lỗi I/O.

Ứng dụng cần quyết định rõ khi một lỗi xuất hiện thì:

1. Dừng toàn bộ tài liệu và báo thất bại.
2. Bỏ qua bản ghi lỗi, lưu lại để điều tra và tiếp tục bản ghi sau.
3. Ghi kết quả hợp lệ một phần kèm báo cáo lỗi, nhưng đánh dấu lần chạy là hoàn tất có lỗi.
4. Tạm dừng để retry nếu lỗi có thể phục hồi, chẳng hạn dịch vụ downstream tạm thời không khả dụng.

Không có một chính sách đúng cho mọi hệ thống. Dữ liệu tài chính, đơn hàng hoặc lệnh điều khiển thường cần tính toàn vẹn cao và có thể phải dừng toàn bộ batch. Một luồng telemetry hoặc import danh mục có thể chấp nhận một số bản ghi lỗi nếu chúng được cách ly và báo cáo đầy đủ.

Chính sách phải được xác định cùng với ranh giới bản ghi, khả năng phục hồi parser, cách ghi kết quả và yêu cầu về tính toàn vẹn. Chỉ bắt exception rồi tiếp tục vòng lặp không đủ để bảo đảm dữ liệu còn đúng.

## 2. Phân loại lỗi trước khi quyết định dừng hay tiếp tục

Các lỗi khác nhau có khả năng phục hồi khác nhau. Nên phân loại chúng trước khi thiết kế catch block:

| Nhóm lỗi | Ví dụ | Khả năng tiếp tục |
|---|---|---|
| Lỗi cú pháp JSON | Thiếu dấu ngoặc, dấu phẩy sai, chuỗi chưa đóng | Thường phải dừng tài liệu JSON đơn vì không còn ranh giới đáng tin cậy |
| Lỗi ánh xạ | String gửi vào field số, enum không hợp lệ, thiếu creator property bắt buộc | Có thể cách ly bản ghi nếu toàn bộ bản ghi đã được parse thành công |
| Lỗi validation nghiệp vụ | Số lượng âm, mã khách hàng không tồn tại | Thường có thể cách ly riêng bản ghi |
| Lỗi tham chiếu | Object identity chưa được giải quyết | Phụ thuộc phạm vi đồ thị; thường ảnh hưởng cả tài liệu hoặc đồ thị |
| Lỗi nguồn I/O | File không đọc được, socket bị ngắt | Dừng hoặc retry theo khả năng của nguồn |
| Lỗi đích I/O | Disk đầy, output stream đóng, dịch vụ đích không nhận dữ liệu | Dừng ghi; không tiếp tục đọc nếu không có nơi lưu backlog an toàn |
| Lỗi cấu hình/chương trình | Module thiếu, serializer sai, bug xử lý | Thường dừng vì retry cùng cấu hình không khắc phục được |

Jackson có thể phát ra các loại exception như:

- JsonParseException hoặc StreamReadException cho lỗi cú pháp và đọc token.
- JsonMappingException và các lớp con như MismatchedInputException hoặc InvalidFormatException cho lỗi ánh xạ.
- UnrecognizedPropertyException cho property không được nhận diện khi strict mode được bật.
- UnresolvedForwardReference cho object identity reference không tìm được đích.
- IOException cho lỗi đọc hoặc ghi luồng.

Validation nghiệp vụ thường dùng exception riêng của ứng dụng, ví dụ InvalidRecordException. Nên giữ loại lỗi và vị trí field để báo cáo có ích.

Không nên bắt mọi Exception rồi tiếp tục. Một lỗi ghi output hoặc lỗi parser có thể làm hỏng toàn bộ phần còn lại của tài liệu. Nếu xem chúng như lỗi riêng của một bản ghi, ứng dụng có thể phát ra JSON không hoàn chỉnh hoặc mất dữ liệu mà vẫn báo thành công.

## 3. Chọn phạm vi thất bại: bản ghi hay toàn tài liệu?

Trước khi chọn chiến lược, cần xác định cấu trúc đầu vào:

### Một JSON document chứa array

~~~json
[
  {"id": 1, "name": "Lan"},
  {"id": 2, "name": "Minh"},
  {"id": 3, "name": "An"}
]
~~~

Toàn bộ array là một JSON document. Parser phải hiểu cấu trúc ngoặc và dấu phân cách để biết vị trí phần tử. Nếu một object có JSON sai cú pháp, parser có thể không biết chính xác nơi phần tử đó kết thúc. Không nên giả định có thể bỏ qua vài byte rồi tiếp tục parse phần tử sau một cách an toàn.

Tuy nhiên, nếu cấu trúc JSON của phần tử đã được parse hoàn chỉnh thành JsonNode, lỗi xảy ra ở bước chuyển JsonNode sang POJO hoặc validation nghiệp vụ có thể được cách ly riêng. Parser đã tiêu thụ trọn phần tử hợp lệ về cú pháp nên có thể tiếp tục phần tử kế tiếp.

### NDJSON: một JSON document trên mỗi dòng

~~~text
{"id":1,"name":"Lan"}
{"id":2,"name":"Minh"}
{"id":3,"name":"An"}
~~~

NDJSON (Newline Delimited JSON) đặt một JSON value trên mỗi dòng. Ranh giới dòng cho phép ứng dụng tạo parser riêng cho từng bản ghi. Nếu một dòng sai cú pháp, có thể ghi dòng đó vào vùng cách ly rồi chuyển sang dòng kế tiếp mà không cần khôi phục parser của tài liệu lớn.

Điều kiện là producer tuân theo định dạng NDJSON: mỗi JSON value phải nằm trên một dòng vật lý, newline bên trong string phải được escape, và một object nhiều dòng được pretty-print không phải một record NDJSON hợp lệ.

### Các JSON value nối tiếp

Một luồng có thể chứa nhiều JSON value liên tiếp được phân tách bằng khoảng trắng:

~~~text
{"id":1} {"id":2} {"id":3}
~~~

Jackson có thể đọc các root value nối tiếp bằng parser, nhưng nếu một value bị lỗi cú pháp thì việc tìm ranh giới value tiếp theo vẫn không tự động an toàn. Cần một framing protocol rõ ràng nếu muốn phục hồi sau lỗi.

## 4. Chính sách fail-fast: dừng toàn bộ tài liệu

Fail-fast phù hợp khi mọi bản ghi trong tài liệu tạo thành một đơn vị nghiệp vụ nguyên tử hoặc khi không thể tin cậy ranh giới sau một lỗi.

Ví dụ:

- Một batch thanh toán phải được xử lý đầy đủ hoặc bị từ chối toàn bộ.
- Một file cấu hình phải hợp lệ hoàn toàn trước khi được áp dụng.
- Các bản ghi phụ thuộc lẫn nhau và thứ tự xử lý có ý nghĩa.
- JSON sai cú pháp khiến parser không thể xác định vị trí tiếp tục.
- Lỗi output có thể làm kết quả không đầy đủ.

Luồng xử lý:

~~~text
Bắt đầu tài liệu
      |
      v
Đọc và xử lý bản ghi
      |
      v
Có lỗi?
  /       \
Không      Có
 |          |
 v          v
Tiếp tục   Dừng pipeline
 |          |
 v          v
Hoàn tất   Đánh dấu thất bại
~~~

Với fail-fast, nên:

1. Dừng đọc ngay khi gặp lỗi không thể phục hồi.
2. Đóng parser, generator và stream bằng try-with-resources.
3. Không công bố output chưa hoàn chỉnh như một kết quả thành công.
4. Ghi loại lỗi, vị trí, nguồn dữ liệu và batch ID.
5. Nếu cần retry, xác định lại nguồn dữ liệu và bảo đảm thao tác có thể chạy lặp an toàn.

Fail-fast không nhất thiết có nghĩa xóa mọi kết quả đã tạo. Nếu đầu ra được ghi vào file tạm, có thể loại bỏ file tạm khi thất bại. Nếu output đã được gửi ra dịch vụ bên ngoài, cần cơ chế transaction, idempotency hoặc bù trừ vì byte hoặc side effect đã phát ra không thể tự thu hồi.

## 5. Chính sách record-level: tách bản ghi lỗi và tiếp tục

Record-level isolation phù hợp khi mỗi bản ghi độc lập và ranh giới bản ghi được xác định rõ. Ví dụ:

- Import danh sách khách hàng độc lập.
- Nạp sự kiện telemetry.
- Chuyển đổi danh mục sản phẩm.
- Đồng bộ nhiều message không phụ thuộc lẫn nhau.

Luồng xử lý:

~~~text
Đọc một record
      |
      v
Parse cấu trúc JSON
      |
      v
Map và validate
   /       \
 Hợp lệ    Lỗi record
   |          |
   v          v
Ghi output  Ghi quarantine/DLQ
   |          |
   +----+-----+
        |
        v
    Record kế tiếp
~~~

Nên phân biệt hai giai đoạn:

1. Parse cú pháp và lấy trọn một record.
2. Ánh xạ, kiểm tra và xử lý record đã parse.

Nếu giai đoạn thứ nhất thất bại trong một JSON array thông thường, parser có thể mất trạng thái cấu trúc. Nếu giai đoạn thứ hai thất bại sau khi đã có JsonNode hoàn chỉnh, ứng dụng có thể lưu node đó vào quarantine rồi tiếp tục.

Một record bị cách ly phải có thông tin đủ để điều tra hoặc chạy lại. Chỉ log thông báo lỗi mà bỏ payload có thể khiến không thể khôi phục dữ liệu.

## 6. Ví dụ: tách lỗi ánh xạ trong một JSON array

Ví dụ đầu vào là một array các object. Chương trình parse mỗi phần tử thành JsonNode trước; sau đó mới chuyển thành POJO và validation. Nhờ vậy, lỗi mapping hoặc nghiệp vụ của một node đã parse hoàn chỉnh có thể được ghi nhận riêng.

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class ArrayImport {
    public static void main(String[] args) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        Path inputPath = Path.of("records.json");
        Path outputPath = Path.of("accepted.json");

        try (InputStream input = Files.newInputStream(inputPath);
             OutputStream output = Files.newOutputStream(outputPath);
             JsonParser parser = mapper.getFactory().createParser(input);
             JsonGenerator generator = mapper.getFactory().createGenerator(output)) {

            if (parser.nextToken() != JsonToken.START_ARRAY) {
                throw new IOException("Expected a top-level JSON array");
            }

            generator.writeStartArray();
            int accepted = 0;
            int rejected = 0;

            JsonToken token;
            while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
                if (token == null) {
                    throw new IOException("Unexpected end of JSON array");
                }

                // Đọc trọn phần tử. Lỗi cú pháp ở đây làm dừng toàn tài liệu.
                JsonNode rawRecord = mapper.readTree(parser);

                try {
                    if (rawRecord == null || !rawRecord.isObject()) {
                        throw new InvalidRecordException(
                                "Each array item must be a JSON object"
                        );
                    }

                    ImportRecord record =
                            mapper.treeToValue(rawRecord, ImportRecord.class);
                    validate(record);

                    ImportRecord transformed = transform(record);
                    mapper.writeValue(generator, transformed);
                    accepted++;
                } catch (JsonProcessingException | InvalidRecordException error) {
                    rejected++;
                    writeDeadLetter(rawRecord, error);
                }
            }

            // Từ chối token ngoài array nếu hợp đồng yêu cầu đúng một document.
            if (parser.nextToken() != null) {
                throw new IOException("Unexpected content after top-level array");
            }

            generator.writeEndArray();
            System.out.printf(
                    "Accepted=%d, rejected=%d%n",
                    accepted,
                    rejected
            );
        }
    }

    private static void validate(ImportRecord record) {
        if (record.getQuantity() == null || record.getQuantity() <= 0) {
            throw new InvalidRecordException("quantity must be positive");
        }
    }

    private static ImportRecord transform(ImportRecord record) {
        // Thay bằng phép chuyển đổi nghiệp vụ.
        return record;
    }

    private static void writeDeadLetter(
            JsonNode rawRecord,
            Exception error
    ) throws IOException {
        // Ví dụ minh họa: lưu payload và thông tin lỗi vào file riêng.
        // Trong production, dùng writer/queue có giới hạn và bảo vệ dữ liệu.
        String payload = rawRecord.toString();
        String reason = error.getMessage();
        System.err.println("Rejected record: " + reason);
        System.err.println(payload);
    }
}
~~~

Các kiểu ImportRecord và InvalidRecordException là kiểu của ứng dụng. Ví dụ tập trung vào ranh giới xử lý: readTree(parser) phải hoàn tất trước khi lỗi mapping/validation được coi là lỗi riêng record.

Lỗi cú pháp trong mapper.readTree(parser), lỗi đọc nguồn hoặc lỗi ghi generator không được bắt trong catch record-level. Chúng phải làm dừng toàn pipeline. Không nên bắt IOException tổng quát trong khối xử lý record vì IOException cũng có thể là lỗi nguồn/đích.

Trong mã production, không ghi payload nhạy cảm trực tiếp ra stderr. Thay writeDeadLetter bằng một kho quarantine có kiểm soát, có giới hạn dung lượng và chính sách retention.

## 7. Ví dụ: cách ly từng dòng NDJSON

Với NDJSON, mỗi dòng được parse bằng một parser riêng thông qua readTree(String). Một dòng sai cú pháp không làm hỏng trạng thái parser của dòng kế tiếp:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class NdjsonImport {
    public static void main(String[] args) throws IOException {
        ObjectMapper mapper = new ObjectMapper();

        Path input = Path.of("events.ndjson");
        Path accepted = Path.of("accepted.ndjson");
        Path rejected = Path.of("rejected.ndjson");

        try (BufferedReader reader = Files.newBufferedReader(input);
             BufferedWriter acceptedWriter = Files.newBufferedWriter(accepted);
             BufferedWriter rejectedWriter = Files.newBufferedWriter(rejected)) {

            String line;
            long lineNumber = 0;

            while ((line = reader.readLine()) != null) {
                lineNumber++;
                if (line.isBlank()) {
                    continue; // Hoặc cách ly dòng trống theo hợp đồng.
                }

                try {
                    JsonNode raw = mapper.readTree(line);
                    if (raw == null || !raw.isObject()) {
                        throw new InvalidRecordException(
                                "Each line must contain a JSON object"
                        );
                    }

                    Event event = mapper.treeToValue(raw, Event.class);
                    validate(event);
                    Event result = transform(event);

                    acceptedWriter.write(mapper.writeValueAsString(result));
                    acceptedWriter.newLine();
                } catch (JsonProcessingException | InvalidRecordException error) {
                    // Lưu cả số dòng và nguyên văn dòng đầu vào để điều tra.
                    rejectedWriter.write(lineNumber + "\t" + error.getMessage());
                    rejectedWriter.write("\t");
                    rejectedWriter.write(line);
                    rejectedWriter.newLine();
                }
            }
        }
    }

    private static void validate(Event event) {
        if (event.getEventId() == null || event.getEventId().isBlank()) {
            throw new InvalidRecordException("eventId is required");
        }
    }

    private static Event transform(Event event) {
        return event;
    }
}
~~~

Mỗi dòng có một parser riêng do ObjectMapper tạo trong readTree(String). Khi một dòng không hợp lệ, lần đọc tiếp theo bắt đầu từ chuỗi dòng mới nên không cần khôi phục parser của record trước.

Ví dụ dùng BufferedReader nên giữ toàn bộ một dòng trong bộ nhớ. Nếu record có thể rất lớn, cần giới hạn chiều dài dòng hoặc dùng một framing/streaming strategy phù hợp. Không dùng NDJSON với JSON pretty-printed nhiều dòng vì newline là ranh giới record.

Đối với production, nên dùng một định dạng quarantine có cấu trúc riêng thay vì nối tab nếu payload hoặc error message có thể chứa tab/newline. Có thể ghi JSON object gồm lineNumber, rawPayload, errorCode và message đã làm sạch.

## 8. Khi nào parser có thể tiếp tục sau lỗi?

Khả năng phục hồi phụ thuộc parser đã tiêu thụ được bao nhiêu dữ liệu và ranh giới record có rõ ràng hay không:

| Tình huống | Có thể tiếp tục an toàn? | Lý do |
|---|---|---|
| JsonNode của một phần tử đã parse xong, treeToValue thất bại | Thường có | Parser đã đọc hết phần tử; token kế tiếp thuộc phần tử sau |
| Validation nghiệp vụ thất bại sau khi đã có POJO | Có | Không ảnh hưởng trạng thái cú pháp parser |
| Một dòng NDJSON sai cú pháp | Có thể tiếp tục dòng sau | Mỗi dòng được parse độc lập |
| JSON array có dấu ngoặc hoặc dấu phẩy sai | Không nên giả định | Ranh giới phần tử tiếp theo có thể không xác định |
| Parser bị EOF giữa object/string | Không | Tài liệu chưa hoàn chỉnh |
| OutputStream ghi thất bại | Không thể tiếp tục cùng output một cách tin cậy | Kết quả có thể đã bị ghi một phần |
| Unresolved object identity trong toàn đồ thị | Thường không thể tách một node độc lập | ID có thể được định nghĩa ở vị trí khác trong tài liệu |

Jackson Streaming API không cung cấp một cơ chế chung để tự đồng bộ lại sau mọi lỗi cú pháp JSON. Nếu cần skip record lỗi bất kể record có sai cú pháp, hãy chọn định dạng framing cho phép tìm ranh giới tiếp theo, chẳng hạn NDJSON hoặc một message broker với mỗi message là một payload độc lập.

Không nên tìm dấu ngoặc đóng bằng cách quét chuỗi thô sau lỗi parse. Dấu ngoặc có thể xuất hiện bên trong string đã escape; parser phải hiểu trạng thái string, escape và nesting để xác định ranh giới đúng.

## 9. Tách lỗi thành dead-letter queue hoặc quarantine

Một bản ghi lỗi cần được lưu ở nơi có thể điều tra và xử lý lại. Hai khái niệm thường gặp:

- **Quarantine:** vùng lưu cách ly dữ liệu không hợp lệ, thường phục vụ kiểm tra và sửa dữ liệu.
- **Dead-letter queue (DLQ):** nơi chuyển message không thể xử lý sau một hoặc nhiều lần thử, thường có metadata để replay hoặc phân tích.

Một dead-letter record nên chứa tối thiểu:

| Trường | Mục đích |
|---|---|
| batchId hoặc messageId | Nhận diện lần nhập hoặc message gốc |
| source | File, topic, partition hoặc nguồn dữ liệu |
| offset/lineNumber/index | Vị trí record trong nguồn |
| rawPayload | Dữ liệu gốc để sửa và replay |
| errorCategory | Syntax, mapping, validation, dependency hoặc I/O |
| errorCode | Mã lỗi ổn định để phân loại |
| errorPath | Đường dẫn property nếu Jackson cung cấp |
| occurredAt | Thời điểm lỗi |
| attemptCount | Số lần đã thử |
| schemaVersion | Phiên bản schema nếu biết |

Không phải lúc nào cũng nên lưu raw payload ở dạng không mã hóa. Payload có thể chứa dữ liệu cá nhân, token hoặc thông tin bí mật. Quarantine cần kiểm soát quyền truy cập, encryption, retention và audit. Log ứng dụng thường chỉ nên ghi message ID, error code, path và thông tin đủ để tra cứu bản ghi trong kho an toàn.

DLQ cũng phải có giới hạn dung lượng và cảnh báo khi tăng nhanh. Nếu DLQ đầy hoặc không ghi được, chính sách record-level không còn bảo đảm lưu được lỗi; pipeline nên dừng hoặc áp dụng một backpressure rõ ràng thay vì âm thầm bỏ record.

## 10. Retry lỗi tạm thời và không retry lỗi dữ liệu

Không phải mọi lỗi đều nên retry:

| Loại lỗi | Chính sách thường phù hợp |
|---|---|
| JSON sai cú pháp | Không retry cùng payload; quarantine hoặc từ chối |
| Field sai kiểu | Không retry nếu payload không đổi; cần sửa dữ liệu hoặc schema |
| Validation nghiệp vụ | Không retry tự động trừ khi điều kiện có thể thay đổi |
| HTTP 429 hoặc dịch vụ tạm quá tải | Retry theo Retry-After/backoff nếu thao tác an toàn |
| Timeout mạng | Có thể retry nếu biết thao tác có tính idempotent hoặc có idempotency key |
| Disk full hoặc output permission error | Dừng và sửa hạ tầng; không tiếp tục đọc vào buffer vô hạn |
| Bug serializer hoặc cấu hình | Dừng; retry không khắc phục nguyên nhân |

Retry nên có:

- Số lần thử tối đa.
- Exponential backoff và jitter khi phù hợp.
- Giới hạn tổng thời gian.
- Phân loại lỗi retryable/non-retryable.
- Idempotency key hoặc cơ chế chống xử lý trùng.
- Nơi lưu message đang chờ retry nếu pipeline phải tiếp tục nhận dữ liệu.

Nếu một bản ghi đã tạo side effect nhưng phản hồi bị mất, retry có thể thực hiện side effect lần hai. Ví dụ, gửi thanh toán hoặc tạo đơn hàng cần idempotency key để cùng một message không tạo giao dịch trùng.

## 11. Bảo vệ tính toàn vẹn của output

Khi ghi một JSON array, generator thường ghi từ đầu đến cuối. Nếu pipeline dừng giữa chừng, file có thể chỉ chứa:

~~~json
[
  {"id": 1},
  {"id": 2}
~~~

Đây không phải JSON document hoàn chỉnh vì array chưa được đóng. Nếu ứng dụng công bố file này như kết quả thành công, consumer downstream sẽ không thể đọc toàn bộ.

Một chiến lược thường dùng là ghi vào file tạm:

1. Tạo file tạm trong cùng filesystem với file đích.
2. Ghi toàn bộ array và đóng JsonGenerator thành công.
3. Flush/close stream và thực hiện các bước durability cần thiết theo yêu cầu hệ thống.
4. Chỉ sau khi hoàn tất mới đổi tên file tạm thành file đích.
5. Nếu thất bại, giữ file tạm để điều tra hoặc xóa theo chính sách; không thay thế file đích hợp lệ.

Ví dụ khung:

~~~java
Path target = Path.of("accepted.json");
Path temporary = Files.createTempFile(
        target.getParent(),
        "accepted-",
        ".tmp"
);

boolean completed = false;
try {
    writeCompleteJsonDocument(temporary);

    Files.move(
            temporary,
            target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING
    );
    completed = true;
} finally {
    if (!completed) {
        // Giữ lại hoặc xóa file tạm theo chính sách vận hành.
    }
}
~~~

ATOMIC_MOVE phụ thuộc filesystem và có thể không được hỗ trợ trong mọi môi trường. Nếu hệ thống yêu cầu atomic publication, cần xác nhận filesystem đích hỗ trợ thao tác này; không nên âm thầm coi move thường là atomic.

Với NDJSON, mỗi dòng là một record độc lập nên file có thể chứa một số dòng hoàn chỉnh trước khi pipeline dừng. Dù vậy, cần một manifest hoặc trạng thái batch để downstream biết file là hoàn chỉnh hay chỉ là kết quả một phần.

## 12. Chọn all-or-nothing hay partial success

Hai chính sách thường được dùng:

### All-or-nothing

Chỉ công bố output nếu mọi record đều thành công. Nếu một record lỗi không được phép bỏ qua, batch thất bại và output chưa được commit.

Phù hợp khi:

- Các record tạo thành một transaction nghiệp vụ.
- Batch phải được áp dụng đồng bộ.
- Không chấp nhận kết quả một phần.
- Downstream cần một snapshot nhất quán.

### Partial success

Ghi các record hợp lệ, cách ly record lỗi và trả báo cáo số lượng. Batch có thể hoàn tất với trạng thái PARTIAL_SUCCESS hoặc COMPLETED_WITH_ERRORS.

Phù hợp khi:

- Các record độc lập.
- Hợp đồng cho phép bỏ qua dữ liệu lỗi.
- Có quy trình sửa và replay quarantine.
- Người vận hành có thể theo dõi tỷ lệ lỗi.

Không nên chỉ trả HTTP 200 hoặc exit code 0 khi một phần dữ liệu đã bị loại mà không cung cấp báo cáo. Trạng thái và số lượng phải làm rõ kết quả.

Ví dụ batch report:

~~~json
{
  "batchId": "B-2026-001",
  "status": "COMPLETED_WITH_ERRORS",
  "total": 1000,
  "accepted": 992,
  "rejected": 8,
  "quarantined": 8
}
~~~

## 13. Checkpoint và replay khi xử lý nguồn lớn

Với nguồn rất lớn hoặc liên tục, có thể cần checkpoint để không phải bắt đầu lại từ đầu sau sự cố. Checkpoint có thể lưu:

- File offset hoặc số dòng đã xử lý.
- Message broker partition và offset.
- Batch ID và record sequence.
- Số lượng accepted/rejected.
- Vị trí đã commit trong output.

Checkpoint chỉ nên được cập nhật sau khi kết quả tương ứng đã được ghi bền vững hoặc commit thành công. Nếu đánh dấu nguồn đã xử lý trước khi output được ghi, sự cố có thể làm mất record. Nếu ghi output trước rồi crash trước checkpoint, replay có thể tạo bản ghi trùng.

Để giải quyết cửa sổ lỗi đó, có thể dùng:

- Transaction bao gồm cả output và checkpoint nếu cùng một hệ thống hỗ trợ.
- Idempotent sink, dùng record ID làm khóa duy nhất.
- Outbox/inbox pattern cho tích hợp dịch vụ.
- Commit theo batch với marker và cơ chế nhận biết batch đã được áp dụng.

Không nên chỉ lưu offset hiện tại rồi giả định pipeline có exactly-once. Exactly-once là thuộc tính của toàn luồng side effect và commit, không chỉ của parser.

## 14. Giữ vị trí lỗi và thông tin chẩn đoán

Jackson thường gắn path vào JsonMappingException để cho biết lỗi xảy ra ở property nào. Có thể lấy thông tin:

~~~java
catch (JsonMappingException error) {
    String path = error.getPathReference();
    String message = error.getOriginalMessage();
    // Đưa path và message vào metadata quarantine.
}
~~~

Với Streaming API, có thể ghi nhận vị trí parser:

~~~java
long byteOffset = parser.currentLocation().getByteOffset();
long line = parser.currentLocation().getLineNr();
long column = parser.currentLocation().getColumnNr();
~~~

Vị trí byte có thể không có sẵn hoặc không có ý nghĩa với mọi nguồn parser; line/column thường hữu ích cho JSON văn bản. Với NDJSON, số dòng ngoài cùng là một định danh record rõ ràng hơn.

Khi ghi log:

- Dùng error code ổn định thay vì chỉ dựa vào nội dung message.
- Ghi batch ID, source ID và record index.
- Giữ exception cause để điều tra.
- Không ghi raw payload nhạy cảm vào log công khai.
- Phân biệt lỗi record với lỗi hạ tầng.

## 15. Đặt giới hạn để lỗi không làm cạn tài nguyên

Quarantine và retry cũng có thể trở thành nguồn tiêu thụ tài nguyên:

- Một record lỗi rất lớn có thể chiếm nhiều heap khi lưu raw payload.
- DLQ không giới hạn có thể làm đầy disk.
- Retry không giới hạn có thể tạo vòng lặp vô tận.
- Một batch có quá nhiều lỗi có thể tạo lượng log lớn.
- Một record có nesting hoặc string quá lớn có thể làm parser tốn tài nguyên.

Jackson Core có StreamReadConstraints trong các phiên bản hỗ trợ, cho phép giới hạn độ sâu lồng nhau và độ dài string/number. Ngoài ra, nên giới hạn:

- Tổng kích thước file hoặc request body.
- Kích thước tối đa mỗi record.
- Số lần retry và tổng thời gian retry.
- Dung lượng quarantine/DLQ và retention.
- Tỷ lệ lỗi tối đa trước khi dừng batch.

Một số hệ thống dùng ngưỡng lỗi, ví dụ dừng batch nếu tỷ lệ record lỗi vượt 5%. Ngưỡng này phải được định nghĩa theo yêu cầu nghiệp vụ, không nên chọn tùy tiện. Với dữ liệu tài chính, một lỗi cũng có thể đủ để dừng; với telemetry, tỷ lệ cho phép có thể cao hơn.

## 16. Thiết kế chính sách bằng cấu hình rõ ràng

Thay vì rải các catch block và điều kiện khắp code, có thể mô hình hóa chính sách:

~~~java
public enum FailureMode {
    FAIL_FAST,
    QUARANTINE_AND_CONTINUE
}

public record ImportPolicy(
        FailureMode failureMode,
        int maxRejectedRecords,
        double maxRejectedRatio,
        boolean publishPartialOutput
) {
    public void checkThreshold(long total, long rejected) {
        if (rejected > maxRejectedRecords) {
            throw new IllegalStateException(
                    "Rejected record count exceeded the configured limit"
            );
        }

        if (total > 0
                && ((double) rejected / total) > maxRejectedRatio) {
            throw new IllegalStateException(
                    "Rejected record ratio exceeded the configured limit"
            );
        }
    }
}
~~~

Pipeline có thể dùng policy để quyết định:

- Lỗi cú pháp luôn dừng tài liệu.
- Lỗi mapping/validation được quarantine nếu mode cho phép.
- Vượt ngưỡng rejected thì dừng batch.
- Chỉ publish output một phần nếu publishPartialOutput được bật.

Không nên cho phép cấu hình biến một lỗi I/O thành lỗi record có thể bỏ qua. Chính sách phải giữ phân loại lỗi và ranh giới phục hồi an toàn.

## 17. Checklist thiết kế trước khi triển khai

Trước khi chọn continue-on-error, hãy trả lời:

1. Một record được phân định bằng array element, dòng NDJSON, message broker hay framing khác?
2. Parser đã parse xong record trước khi mapping/validation có thể lỗi chưa?
3. Nếu JSON sai cú pháp, có thể tìm ranh giới record kế tiếp một cách chắc chắn không?
4. Những lỗi nào là record-level và những lỗi nào phải dừng toàn pipeline?
5. Raw payload lỗi được lưu ở đâu, trong bao lâu và ai có quyền truy cập?
6. Output một phần có được công bố không? Trạng thái batch thể hiện điều đó thế nào?
7. Nếu retry, làm sao tránh side effect trùng?
8. Checkpoint được commit cùng output hay theo thứ tự nào?
9. DLQ đầy hoặc không ghi được thì pipeline sẽ làm gì?
10. Có giới hạn record size, retry count, error rate và quarantine capacity không?

Nếu chưa trả lời được câu hỏi về ranh giới record hoặc tính toàn vẹn output, nên bắt đầu bằng fail-fast. Chỉ bật record-level continuation khi có cách chứng minh parser và output vẫn ở trạng thái hợp lệ.

## 18. Kết luận

Chính sách dừng tài liệu hay tách bản ghi lỗi phải dựa trên loại lỗi, ranh giới record và yêu cầu toàn vẹn. Lỗi cú pháp trong một JSON document thường làm mất khả năng xác định vị trí tiếp tục; không nên cố skip tùy tiện. Nếu một phần tử đã được parse hoàn chỉnh thành JsonNode rồi mới lỗi mapping hoặc validation, có thể cách ly riêng phần tử đó. NDJSON giúp cô lập cú pháp theo từng dòng vì mỗi record có parser riêng. Dù chọn fail-fast hay partial success, cần lưu metadata lỗi, bảo vệ raw payload, giới hạn DLQ/retry, ghi output an toàn và công bố rõ trạng thái batch. Một pipeline chỉ nên tiếp tục khi biết chắc ranh giới dữ liệu và khả năng ghi kết quả vẫn còn đáng tin cậy.
