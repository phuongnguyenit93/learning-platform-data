# Tránh tiếp tục sử dụng parser sau lỗi khi không xác định được ranh giới

Jackson streaming parser đọc JSON tuần tự và duy trì trạng thái về token, object, array cùng vị trí hiện tại. Khi gặp lỗi cú pháp hoặc lỗi I/O, trạng thái parser có thể không còn ở một ranh giới mà ứng dụng hiểu chắc chắn. Nếu tiếp tục gọi `nextToken()` hoặc cố bỏ qua phần còn lại, ứng dụng có thể đọc nhầm dữ liệu, bỏ sót lỗi hoặc xử lý một phần payload như thể đó là một record hợp lệ.

Nguyên tắc an toàn là: **chỉ tiếp tục sau lỗi khi định dạng nguồn có ranh giới record độc lập và code đã khôi phục được đúng ranh giới đó**. Với một JSON document liên tục bị sai cú pháp, Jackson không cung cấp cơ chế tổng quát để tự tìm điểm bắt đầu của JSON hợp lệ tiếp theo. Hãy dừng lần parse đó, đóng parser và xử lý lỗi ở cấp document. Nếu cần tiếp tục xử lý record sau một record lỗi, hãy thiết kế framing ở bên ngoài JSON, chẳng hạn NDJSON hoặc JSON Text Sequences.

## 1. Parser là một máy trạng thái

Một `JsonParser` không phải bộ tìm kiếm chuỗi JSON độc lập cho từng lần gọi. Nó giữ trạng thái đọc:

- Token hiện tại như `START_OBJECT`, `FIELD_NAME`, `VALUE_STRING` hoặc `END_ARRAY`.
- Parsing context hiện tại và các context cha.
- Vị trí trong nguồn dữ liệu.
- Trạng thái bộ đệm và nguồn InputStream/Reader.

Với JSON hợp lệ:

~~~json
{
  "users": [
    {"id": 1},
    {"id": 2}
  ]
}
~~~

Parser đi qua một chuỗi token có cấu trúc. Mỗi token chỉ có ý nghĩa trong quan hệ với token trước đó và context hiện tại.

Nếu nguồn bị hỏng giữa chừng:

~~~json
{
  "users": [
    {"id": 1},
    {"id": }
  ]
}
~~~

parser có thể ném `JsonParseException` khi đang đọc giá trị của `id`. Tại thời điểm đó, tài liệu không còn tuân theo grammar JSON. Parser không thể biết phần byte tiếp theo là phần còn lại của record hiện tại, một dấu ngoặc bị thiếu hay dữ liệu của một record mới được nối vào.

## 2. Phân biệt lỗi cú pháp, lỗi ánh xạ và lỗi nghiệp vụ

Không phải lỗi nào trong pipeline cũng có cùng khả năng tiếp tục.

| Loại lỗi | Ví dụ | Có thể tiếp tục không? |
|---|---|---|
| Lỗi cú pháp JSON | Thiếu dấu ngoặc, dấu phẩy sai, string không đóng | Thường phải dừng document nếu không có framing độc lập |
| Lỗi I/O | Stream bị ngắt, socket timeout, file không đọc được | Thường phải dừng nguồn hiện tại; không biết byte tiếp theo có đầy đủ hay không |
| Lỗi ánh xạ | Chuỗi không chuyển được sang enum, number vượt miền kiểu đích | Chỉ tiếp tục nếu ranh giới value/record đã được tiêu thụ và xác định chắc chắn |
| Lỗi validation nghiệp vụ | Email sai định dạng, trạng thái không được phép | Có thể bỏ record và tiếp tục nếu record JSON đã được parse trọn vẹn |
| Lỗi xử lý downstream | Database hoặc service từ chối một record | Có thể tiếp tục theo chính sách batch nếu ranh giới record vẫn rõ |

Ví dụ:

- `{"id": }` là lỗi cú pháp. Parser không thể hoàn tất cấu trúc object.
- `{"id": "abc"}` đọc được thành JSON hợp lệ, nhưng có thể gây lỗi ánh xạ nếu DTO yêu cầu số nguyên.
- `{"id": 10, "email": "not-an-email"}` có thể ánh xạ thành DTO thành công nhưng thất bại ở validation nghiệp vụ.

Cách xử lý phụ thuộc vào việc parser đã đọc xong một record hay chưa. Lỗi validation sau khi đã có object hoàn chỉnh thường có thể cô lập theo record. Lỗi cú pháp giữa một JSON document liên tục thì không.

## 3. Không tiếp tục gọi nextToken() sau JsonParseException

Một mẫu nguy hiểm là bắt lỗi rồi tiếp tục vòng lặp:

~~~java
try (JsonParser parser = factory.createParser(input)) {
    while (parser.nextToken() != null) {
        try {
            processCurrentToken(parser);
        } catch (JsonProcessingException ex) {
            log.warn("Bad token", ex);
            // Tiếp tục đọc token kế tiếp
        }
    }
}
~~~

Mẫu này không an toàn nếu lỗi phát sinh từ parser hoặc quá trình đọc cấu trúc. Parser có thể đã dừng ở vị trí giữa token hoặc trong một cấu trúc chưa đóng. Gọi `nextToken()` tiếp không có nghĩa là parser đã đồng bộ lại.

Ngay cả khi lần gọi tiếp theo trả về một token, điều đó cũng không chứng minh phần tài liệu trước đó đã hợp lệ hoặc token mới thuộc một record độc lập.

Đối với lỗi cú pháp hoặc I/O, hãy để exception thoát ra khỏi vòng lặp, đóng parser và đánh dấu document/batch theo chính sách thất bại.

## 4. Không dùng skipChildren() như một cơ chế phục hồi cú pháp

`skipChildren()` hữu ích khi parser đang ở một token mở container hợp lệ:

~~~java
if (parser.currentToken() == JsonToken.START_OBJECT
        || parser.currentToken() == JsonToken.START_ARRAY) {
    parser.skipChildren();
}
~~~

Nó bỏ qua các token con cho đến token đóng tương ứng. Phương thức này giả định parser đang ở trong một cấu trúc JSON có thể đọc và duyệt được.

Nếu parser vừa ném lỗi cú pháp do container thiếu dấu đóng hoặc value sai định dạng, `skipChildren()` không thể tự suy ra dấu đóng đúng. Nó cũng không phải thao tác "bỏ đến object tiếp theo".

Chỉ gọi `skipChildren()` khi:

- Parser không ở trạng thái lỗi.
- Token hiện tại là `START_OBJECT` hoặc `START_ARRAY`.
- Ứng dụng chủ động bỏ qua một nhánh hợp lệ, không phải đang cố cứu một document sai cú pháp.

## 5. Ranh giới JSON document không thể suy ra bằng cách tìm dấu ngoặc

Một số cách phục hồi tự viết thường tìm ký tự `{` hoặc `[` tiếp theo trong input rồi tạo parser mới từ vị trí đó. Cách này không đáng tin cậy.

Ví dụ:

~~~json
{
  "message": "text có ký tự } và { trong string",
  "payload": {"id": 1}
}
~~~

Dấu ngoặc trong string không phải delimiter cấu trúc. Ngoài ra:

- Object có thể lồng nhiều cấp.
- String có thể chứa escape cho dấu ngoặc kép hoặc cho chính ký tự gạch chéo ngược.
- JSON có thể có whitespace và line break ở nhiều vị trí.
- Một dấu ngoặc mở sau lỗi có thể thuộc payload hỏng hiện tại, không phải record mới.
- Nếu lỗi xảy ra do encoding hoặc stream bị cắt, phần byte tiếp theo cũng có thể không hoàn chỉnh.

Vì vậy, không thể khôi phục ranh giới JSON tổng quát chỉ bằng cách tìm dấu ngoặc tiếp theo. Muốn phục hồi, định dạng truyền tải phải cung cấp framing độc lập.

## 6. Xử lý một JSON document đơn: lỗi thì dừng và đóng parser

Với một JSON document thông thường, hãy để lỗi parse kết thúc lần đọc. Dùng try-with-resources để parser và tài nguyên thuộc quyền sở hữu của method được đóng.

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.JsonProcessingException;

import java.io.IOException;
import java.io.InputStream;

public Document readDocument(
        JsonFactory factory,
        InputStream input) throws IOException {

    try (JsonParser parser = factory.createParser(input)) {
        if (parser.nextToken() != JsonToken.START_OBJECT) {
            throw new IOException("Expected a JSON object");
        }

        return readDocumentBody(parser);
    } catch (JsonProcessingException ex) {
        // Ghi nhận document lỗi rồi truyền lỗi lên tầng gọi.
        throw ex;
    }
}
~~~

Trong ví dụ, `JsonProcessingException` được ném lại để caller quyết định trả HTTP 400, đưa file vào vùng quarantine hoặc đánh dấu message thất bại. Vì exception này thuộc hệ thống exception I/O của Jackson, method có thể khai báo `throws IOException`.

Không tiếp tục dùng parser sau khi exception đã thoát khỏi thao tác đọc. Try-with-resources đóng parser ngay cả khi method return hoặc exception được ném ra.

## 7. Ghi lại vị trí và context trước khi parser bị đóng

Vị trí lỗi giúp chẩn đoán payload. Với `JsonProcessingException`, có thể lấy location trực tiếp từ exception. Khi phát hiện lỗi nghiệp vụ trong lúc parser còn hợp lệ, có thể lấy thêm context và path hiện tại.

~~~java
import com.fasterxml.jackson.core.JsonLocation;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonProcessingException;

import java.io.IOException;
import java.io.InputStream;

try (JsonParser parser = factory.createParser(input)) {
    while (parser.nextToken() != null) {
        // Xử lý token
    }
} catch (JsonProcessingException ex) {
    JsonLocation location = ex.getLocation();

    if (location != null) {
        log.error(
            "Invalid JSON at line {}, column {}: {}",
            location.getLineNr(),
            location.getColumnNr(),
            ex.getOriginalMessage()
        );
    } else {
        log.error("Invalid JSON: {}", ex.getOriginalMessage());
    }

    throw ex;
}
~~~

Với lỗi ánh xạ, `JsonMappingException` còn có thể chứa path reference để chỉ ra property hoặc index gây lỗi. Có thể dùng `getPathReference()` khi log.

Không ghi toàn bộ payload nhạy cảm vào log chỉ để chẩn đoán. Nên ghi correlation ID, tên file/message, offset nếu có, line/column và path; nếu cần giữ payload lỗi, dùng vùng lưu trữ được kiểm soát quyền và thời hạn.

## 8. Nếu cần tiếp tục sau một record lỗi, hãy tạo framing độc lập

Một JSON array lớn vẫn chỉ là một JSON document:

~~~json
[
  {"id": 1},
  {"id": 2},
  {"id": 3}
]
~~~

Nếu object thứ hai sai cú pháp, parser có thể không biết nơi object thứ hai kết thúc để tìm object thứ ba. Dấu phẩy và dấu ngoặc chỉ có ý nghĩa khi cấu trúc hiện tại còn hợp lệ.

Nếu nghiệp vụ cần xử lý độc lập từng record và tiếp tục khi một record sai, hãy dùng định dạng có ranh giới record rõ ràng, ví dụ:

- NDJSON: mỗi dòng chứa một JSON document.
- JSON Text Sequences (RFC 7464): mỗi JSON text được phân cách bằng Record Separator (RS).
- Một giao thức message có length prefix hoặc frame riêng.

Ranh giới này phải thuộc hợp đồng producer/consumer. Không thể tự giả định một file JSON array hiện có thực ra là NDJSON.

## 9. NDJSON: cô lập lỗi theo từng dòng

NDJSON (Newline Delimited JSON) lưu mỗi record JSON trên một dòng riêng:

~~~text
{"id":1,"name":"An"}
{"id":2,"name":"Bình"}
{"id":3,"name":"Chi"}
~~~

Ứng dụng đọc từng dòng, tạo một lần deserialize độc lập cho mỗi dòng. Nếu dòng thứ hai sai cú pháp, có thể từ chối dòng đó rồi tiếp tục dòng thứ ba vì newline đã xác định ranh giới record.

Ví dụ:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectReader;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public void processNdjson(
        InputStream input,
        ObjectReader eventReader) throws IOException {

    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(input, StandardCharsets.UTF_8))) {

        String line;
        long lineNumber = 0;

        while ((line = reader.readLine()) != null) {
            lineNumber++;

            if (line.isBlank()) {
                // Chỉ bỏ dòng trắng nếu hợp đồng NDJSON của ứng dụng cho phép.
                continue;
            }

            try {
                Event event = eventReader.readValue(line);
                process(event);
            } catch (JsonProcessingException ex) {
                reportRejectedRecord(lineNumber, ex);
                // Record này đã bị cô lập bởi newline; đọc dòng kế tiếp.
            }
        }
    }
}
~~~

Tạo reader với kiểm tra trailing token:

~~~java
ObjectReader eventReader = mapper
    .readerFor(Event.class)
    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
~~~

Cấu hình này giúp bảo đảm mỗi dòng chỉ chứa một JSON value hoàn chỉnh. Nếu một dòng chứa JSON hợp lệ rồi có thêm token khác, record bị từ chối thay vì âm thầm bỏ phần đuôi.

### 9.1. Giới hạn của phục hồi theo dòng

NDJSON chỉ cho phép tiếp tục khi framing vẫn còn đáng tin cậy:

- Một record phải nằm trên một dòng vật lý.
- JSON string không được chứa raw newline; newline bên trong string phải được escape.
- Encoding phải được xác định, thường là UTF-8.
- Nếu InputStream gặp lỗi I/O, không thể giả định rằng dòng tiếp theo sẽ đầy đủ.
- Dòng quá dài cần giới hạn kích thước để tránh tiêu thụ bộ nhớ không kiểm soát.

Trong ví dụ, lỗi JSON của một dòng được cô lập; lỗi I/O của BufferedReader thoát khỏi method và dừng batch. Đây là khác biệt quan trọng: newline giúp cô lập record, nhưng không thể sửa một stream bị mất byte hoặc bị ngắt giữa quá trình đọc.

## 10. JSON Text Sequences: delimiter RS rõ ràng

RFC 7464 định nghĩa JSON Text Sequences. Mỗi JSON text được bắt đầu bằng ký tự Record Separator (RS, byte `0x1E`), thường theo sau là JSON text và line feed.

Hình dạng khái quát:

~~~text
<RS>{"id":1,"name":"An"}<LF>
<RS>{"id":2,"name":"Bình"}<LF>
<RS>{"id":3,"name":"Chi"}<LF>
~~~

Vì RS là framing marker riêng, consumer có thể tìm record tiếp theo sau khi đã kết thúc hoặc loại bỏ record hiện tại theo quy tắc của RFC. Ký tự điều khiển RS không được xuất hiện thô trong JSON string hợp lệ; nếu cần biểu diễn nó trong string, JSON dùng escape.

Khi dùng JSON Text Sequences:

- Dùng parser/decoder hiểu RFC 7464 hoặc tự triển khai framing đúng chuẩn ở tầng byte.
- Chỉ tạo parser JSON cho phần text thuộc một sequence element.
- Áp dụng giới hạn kích thước cho từng record.
- Xác định rõ cách xử lý record rỗng, JSON text không hợp lệ và record cuối bị cắt.
- Không coi một JSON array thông thường là JSON Text Sequence.

Jackson Core cung cấp parser JSON, nhưng việc tách RS framing là trách nhiệm của tầng protocol/decoder hoặc thư viện chuyên dụng. Chỉ đưa một stream nhiều JSON text liên tiếp vào parser không tự biến nó thành RFC 7464.

## 11. Trong một JSON array, phân biệt lỗi parse với lỗi validation record

Nếu toàn bộ array hợp lệ về cú pháp nhưng một record không đạt quy tắc nghiệp vụ, có thể tiếp tục sau record đó vì parser đã đọc hết record.

Một cách làm là đọc mỗi phần tử thành một `JsonNode`, sau đó bind và validate:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;

public void processArray(
        ObjectMapper mapper,
        InputStream input) throws IOException {

    try (JsonParser parser = mapper.getFactory().createParser(input)) {
        if (parser.nextToken() != JsonToken.START_ARRAY) {
            throw new IOException("Expected a JSON array");
        }

        JsonToken token;
        while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
            if (token == null) {
                throw new IOException("Unexpected end of JSON array");
            }

            // readTree tiêu thụ trọn một JSON value hiện tại.
            JsonNode recordTree = mapper.readTree(parser);

            try {
                Event event = mapper.treeToValue(recordTree, Event.class);
                validate(event);
                process(event);
            } catch (JsonProcessingException ex) {
                reportRejectedRecord(recordTree, ex);
                // Parser đã ở sau record tree hợp lệ; có thể đọc phần tử tiếp.
            } catch (ValidationException ex) {
                reportRejectedRecord(recordTree, ex);
                // Parser đã ở sau record tree hợp lệ; có thể đọc phần tử tiếp.
            }
        }
    }
}
~~~

Điểm quan trọng là `readTree(parser)` phải đọc thành công toàn bộ một JSON value trước khi code bắt lỗi mapping/validation. Sau đó, `treeToValue(recordTree, Event.class)` và `validate(event)` làm việc trên tree trong bộ nhớ, không còn điều khiển vị trí parser của array.

Nếu `readTree(parser)` gặp lỗi cú pháp giữa record, exception thoát ra ngoài vòng lặp và toàn bộ document bị dừng. Không bắt lỗi đó rồi tiếp tục `nextToken()`.

Cách này giữ bộ nhớ theo kích thước của một record tree, không phải toàn bộ array. Nếu một record có thể rất lớn, cần giới hạn kích thước/depth hoặc dùng một mô hình xử lý khác. Nếu cần ánh xạ streaming trực tiếp vào DTO mà không tạo tree, chỉ nên tiếp tục sau lỗi mapping khi đã chứng minh parser đã tiêu thụ trọn record và vị trí hiện tại vẫn ở ranh giới an toàn; nếu không, hãy dừng document.

## 12. Vì sao không nên catch mọi exception bên trong vòng lặp record?

Ví dụ không nên dùng:

~~~java
while (parser.nextToken() == JsonToken.START_OBJECT) {
    try {
        Event event = mapper.readValue(parser, Event.class);
        process(event);
    } catch (Exception ex) {
        log.warn("Skipping bad event", ex);
        parser.skipChildren();
    }
}
~~~

Có nhiều vấn đề:

- `readValue` có thể thất bại khi đang đọc một nested field, trước khi object kết thúc.
- Parser có thể đang ở scalar token, token mở container hoặc vị trí không thể suy ra bằng logic chung.
- `skipChildren()` chỉ có ý nghĩa nếu parser đang ở token mở container hợp lệ.
- Catch `Exception` còn che cả lỗi lập trình, lỗi I/O và lỗi downstream.
- Vòng lặp có thể tiếp tục từ một token nằm sâu bên trong record trước, rồi xử lý nhầm như record cấp ngoài.

Nếu cần cô lập lỗi mapping theo record trong một array hợp lệ, hãy parse trọn record thành tree trước rồi bind/validate sau. Nếu không thể parse trọn record, không có ranh giới đáng tin cậy để tiếp tục.

## 13. Lỗi I/O không giống lỗi một record JSON

Ngay cả khi định dạng có newline hoặc RS, lỗi I/O có thể xảy ra giữa delimiter và record. Ví dụ socket bị đóng khi consumer mới đọc được một phần dòng.

Khi InputStream ném IOException:

- Không thể giả định parser hoặc reader đã nhận đủ byte.
- Không thể tiếp tục chỉ bằng cách gọi lại `nextToken()`.
- Nếu nguồn là HTTP body hoặc socket, cần kết thúc request/connection theo API sở hữu nó.
- Nếu nguồn là file có thể đọc lại, có thể khởi động lại từ checkpoint đã xác nhận, nhưng checkpoint phải nằm ở ranh giới record đã hoàn tất.

Với stream mạng, timeout, retry và reconnect thuộc tầng transport. Jackson parser không tự khôi phục kết nối hoặc xác định record bị thiếu byte.

## 14. Đầu ra cũng cần xử lý khi parse bị lỗi

Một pipeline có thể đọc JSON rồi ghi JSON mới bằng `JsonGenerator`. Nếu lỗi xảy ra sau khi đã ghi một phần output, file đích có thể chứa document dở dang.

Không nên để consumer khác đọc file tạm như một tài liệu hoàn chỉnh. Với file, có thể:

1. Ghi vào file tạm.
2. Chỉ đóng và commit file khi parse/transform hoàn tất.
3. Nếu parse lỗi hoặc I/O lỗi, xóa file tạm hoặc chuyển vào vùng quarantine.
4. Dùng atomic move nếu filesystem hỗ trợ.

Với HTTP response đã gửi một phần body, server không thể thu hồi các byte đã gửi. Hãy xác định lỗi trước khi bắt đầu response nếu có thể, hoặc dùng giao thức streaming có record framing và trạng thái kết thúc rõ ràng.

## 15. Giới hạn tài nguyên và chống payload gây quá tải

Một parser có thể đọc được cú pháp nhưng payload vẫn có thể tiêu tốn quá nhiều tài nguyên:

- Object/array lồng quá sâu.
- String hoặc number token rất dài.
- Một NDJSON record có kích thước bất thường.
- Quá nhiều field hoặc record.
- Một stream không bao giờ kết thúc.

Với Jackson 2.x, có thể cấu hình `StreamReadConstraints` trên `JsonFactory` để giới hạn độ sâu nesting, độ dài string/number và một số giới hạn đọc khác, tùy phiên bản:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(
        StreamReadConstraints.builder()
            .maxNestingDepth(100)
            .maxStringLength(1_000_000)
            .maxNumberLength(1_000)
            .build()
    )
    .build();
~~~

Các con số trong ví dụ chỉ minh họa; chọn giới hạn theo kích thước payload hợp lệ của hệ thống. Giới hạn parser không thay thế giới hạn tổng request, timeout, số record và giới hạn ở tầng HTTP/message broker.

## 16. Chiến lược phục hồi theo từng loại nguồn

| Nguồn | Ranh giới đáng tin cậy | Khi một record sai cú pháp |
|---|---|---|
| Một JSON document | Chỉ có root document | Dừng document, đóng parser |
| Một JSON array lớn | Các phần tử chỉ phân biệt được khi grammar còn hợp lệ | Nếu lỗi cú pháp giữa phần tử, dừng document |
| NDJSON | Newline giữa các JSON text | Từ chối dòng lỗi, đọc dòng tiếp nếu I/O còn tốt |
| JSON Text Sequences | Record Separator (RS) | Khôi phục tại sequence marker theo RFC/decoder |
| Message broker, mỗi message là một JSON document | Message boundary do broker cung cấp | Từ chối/quarantine message, tiếp tục message kế |
| HTTP body chứa một JSON document | Body của request/response | Dừng xử lý body; không tự tìm JSON tiếp theo |

Ranh giới do message broker hoặc protocol cung cấp thường là cách cô lập lỗi tốt nhất: mỗi message được parse bằng một parser riêng. Một message hỏng không làm parser của message tiếp theo mất trạng thái.

## 17. Checklist khi parser phát sinh lỗi

Khi có exception, hãy xác định theo thứ tự:

1. Lỗi đến từ parser syntax, databinding, validation hay I/O?
2. Parser đã đọc trọn JSON value/record hiện tại chưa?
3. Định dạng nguồn có delimiter hoặc message boundary độc lập không?
4. Ranh giới tiếp theo có thể xác định mà không đoán cấu trúc JSON không?
5. Nếu không xác định được ranh giới, đã dừng lần parse và đóng parser chưa?
6. Nếu có thể tiếp tục, mỗi record tiếp theo có được parse bằng parser mới không?
7. Record lỗi có được log/quarantine mà không lộ dữ liệu nhạy cảm không?
8. Output dở dang có bị ngăn commit không?
9. Có giới hạn kích thước, nesting depth, timeout và số record không?

Nếu câu trả lời cho câu 2 hoặc 4 là không, hãy dừng parser hiện tại. Không cố đồng bộ lại bằng cách tìm token tùy ý.

## 18. Ghi nhớ

- `JsonParser` là stateful; sau lỗi cú pháp hoặc I/O, không giả định parser vẫn ở ranh giới JSON hợp lệ.
- Không tiếp tục `nextToken()` sau `JsonParseException` nếu không có framing và quy tắc phục hồi được xác định rõ.
- `skipChildren()` bỏ qua một container hợp lệ; nó không sửa JSON sai cú pháp.
- Không tìm dấu `{` hoặc `[` tiếp theo để phục hồi, vì dấu ngoặc có thể nằm trong string hoặc nested structure.
- Với một JSON document hoặc array bị lỗi cú pháp giữa chừng, dừng lần parse và đóng parser.
- Có thể bỏ record lỗi trong NDJSON hoặc JSON Text Sequences vì protocol cung cấp ranh giới độc lập.
- Trong một array hợp lệ, có thể đọc trọn từng record thành `JsonNode`, rồi bind/validate riêng; lỗi parse khi đọc tree vẫn phải dừng document.
- Phân biệt lỗi syntax, mapping, validation và I/O để chỉ tiếp tục ở nơi ranh giới còn chắc chắn.
- Ghi location/path để chẩn đoán, nhưng không log payload nhạy cảm không cần thiết.
- Commit output sau khi toàn bộ thao tác hoàn tất; giới hạn độ sâu, kích thước token, record và thời gian xử lý.

