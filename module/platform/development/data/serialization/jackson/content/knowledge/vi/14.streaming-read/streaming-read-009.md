# Nhận diện tài liệu bị cắt dở và kết thúc nguồn không hợp lệ

Khi đọc JSON từ file, HTTP request, message queue hoặc InputStream, Jackson phải biết dữ liệu đã kết thúc đúng lúc hay bị dừng giữa chừng. Một luồng byte kết thúc không tự động có nghĩa tài liệu JSON hợp lệ. Kết quả phụ thuộc vào vị trí parser đang đọc khi gặp EOF (end of file/end of input).

Có một khác biệt quan trọng:

- EOF sau khi một JSON root value đã hoàn chỉnh và chỉ còn khoảng trắng là kết thúc hợp lệ của một JSON document.
- EOF khi parser vẫn đang chờ dấu ngoặc đóng, dấu nháy, chữ số còn thiếu hoặc phần kết thúc của một token là dấu hiệu tài liệu chưa hoàn chỉnh.
- EOF ở cấp transport có thể là lỗi truyền dữ liệu, ngay cả khi phần byte đã nhận tình cờ tạo thành một JSON document hợp lệ. Jackson chỉ phân tích cú pháp những byte được cung cấp; nó không tự biết số byte mà hệ thống gửi dự kiến phải có.

Jackson Core cung cấp exception và vị trí lỗi để ứng dụng nhận diện nhiều trường hợp kết thúc không hợp lệ. Khi đọc theo luồng, cần tiêu thụ parser đúng cách, phân biệt lỗi cú pháp với lỗi I/O và xác định ranh giới bản ghi của giao thức.

## 1. EOF hợp lệ và EOF bất thường

Một JSON document cần có đủ token để hoàn thành cấu trúc của nó.

Ví dụ object hoàn chỉnh:

~~~json
{
  "orderId": "ORD-100",
  "items": [1, 2, 3]
}
~~~

Sau dấu ngoặc nhọn đóng, parser có thể đọc đến EOF. Nếu phần còn lại chỉ là khoảng trắng, document hợp lệ.

Ngược lại, object sau chưa hoàn chỉnh:

~~~json
{
  "orderId": "ORD-100",
  "items": [1, 2, 3]
~~~

Parser đã thấy object bắt đầu nhưng chưa thấy dấu ngoặc nhọn đóng. EOF xảy ra khi cấu trúc vẫn còn mở, nên Jackson phải báo lỗi.

Một số ví dụ khác:

| Input | Tình trạng tại EOF |
|---|---|
| {"id": 1} | Root object hoàn chỉnh. |
| {"id": 1} và sau đó là khoảng trắng | Root hoàn chỉnh; whitespace được phép. |
| {"id": 1 | Thiếu dấu đóng object. |
| {"items": [1, 2 | Thiếu phần đóng array và object. |
| {"name": "Linh | Chuỗi chưa có dấu nháy kết thúc. |
| {"active": tru | Literal boolean chưa hoàn chỉnh. |
| {"amount": 12. | Number chưa hoàn chỉnh. |
| {"amount": 1e | Phần exponent chưa hoàn chỉnh. |

Không nên chỉ kiểm tra stream đã trả về -1 hay chưa rồi kết luận dữ liệu hợp lệ. EOF là tín hiệu kết thúc nguồn; parser mới xác định liệu cú pháp JSON đã hoàn thành tại vị trí đó hay chưa.

## 2. Parser hoạt động như thế nào khi đọc theo luồng?

Jackson Core cung cấp JsonParser để đọc JSON theo token. Parser không cần tạo toàn bộ cây JSON trong bộ nhớ.

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        System.out.println(token);
    }
}
~~~

Với một document hợp lệ, nextToken() trả về từng token, chẳng hạn START_OBJECT, FIELD_NAME, VALUE_STRING, START_ARRAY, VALUE_NUMBER_INT, END_ARRAY và END_OBJECT. Khi parser đã tiêu thụ hết document hợp lệ và nguồn kết thúc, nextToken() trả về null.

Nếu nguồn kết thúc khi parser vẫn đang ở trong object, array, string hoặc token chưa hoàn chỉnh, nextToken() có thể ném JsonEOFException hoặc một JsonParseException phù hợp với vị trí lỗi.

Điều quan trọng là vòng lặp phải tiếp tục đọc đến hết document. Nếu code dừng ngay sau khi lấy được field cần thiết mà không kiểm tra phần còn lại, nó có thể bỏ sót lỗi cú pháp nằm ở cuối input.

Ví dụ, đoạn code chỉ đọc một trường rồi dừng:

~~~java
try (JsonParser parser = factory.createParser(inputStream)) {
    parser.nextToken(); // START_OBJECT
    parser.nextToken(); // FIELD_NAME
    parser.nextToken(); // VALUE_STRING

    String orderId = parser.getText();

    // Dừng tại đây: chưa xác nhận phần còn lại của document.
}
~~~

Đoạn code này chưa chứng minh toàn bộ JSON hợp lệ. Nếu phần sau bị cắt dở, lỗi chỉ xuất hiện khi parser tiếp tục được tiêu thụ.

## 3. Nhận diện JsonEOFException

Jackson Core có JsonEOFException trong package com.fasterxml.jackson.core.io. Đây là một dạng JsonParseException dùng để mô tả trường hợp parser gặp kết thúc nguồn ngoài dự kiến khi vẫn cần thêm nội dung để hoàn thành cú pháp.

Ví dụ, input:

~~~json
{"orderId":"ORD-100","items":[1,2
~~~

có thể gây JsonEOFException khi parser cần đọc tiếp để tìm dấu đóng array hoặc object.

Có thể bắt exception cụ thể:

~~~java
import com.fasterxml.jackson.core.JsonParseException;
import com.fasterxml.jackson.core.io.JsonEOFException;

try {
    OrderRequest request = mapper.readValue(inputStream, OrderRequest.class);
} catch (JsonEOFException e) {
    // Nguồn kết thúc khi JSON vẫn chưa hoàn chỉnh.
    log.warn("JSON input ended unexpectedly", e);
} catch (JsonParseException e) {
    // JSON sai cú pháp theo một cách khác.
    log.warn("Malformed JSON", e);
}
~~~

JsonEOFException là một trường hợp cụ thể của lỗi parse. Đặt catch cụ thể trước catch tổng quát hơn để xử lý đúng nhánh.

Trong nhiều ứng dụng, không nhất thiết phải bắt JsonEOFException ở mọi nơi. Có thể để lỗi đi lên một tầng xử lý chung, nơi ứng dụng phân loại lỗi request hoặc lỗi message. Điều quan trọng là không nuốt exception rồi coi phần object đã đọc được là dữ liệu hoàn chỉnh.

Một lỗi EOF bất thường không đồng nghĩa parser luôn có thể phục hồi để tiếp tục đọc phần còn lại. Với một JSON document đơn, khi cú pháp đã bị cắt giữa chừng, thông thường phải xem toàn bộ document là không hợp lệ và yêu cầu producer gửi lại.

## 4. Phân biệt EOF với JSON sai cú pháp

EOF bất thường là một trường hợp của lỗi parse, nhưng không phải mọi lỗi parse đều do EOF.

Ví dụ JSON sai dấu phẩy:

~~~json
{
  "id": 1
  "name": "Linh"
}
~~~

Parser có đủ byte nhưng cú pháp không hợp lệ vì thiếu dấu phẩy giữa các thuộc tính.

Ví dụ token không hợp lệ:

~~~text
{"active": truX}
~~~

Đây là lỗi cú pháp tại token, không phải nguồn kết thúc quá sớm.

Có thể phân loại ở mức exception:

| Exception / nhóm lỗi | Ý nghĩa thường gặp |
|---|---|
| JsonEOFException | Parser cần thêm dữ liệu nhưng nguồn đã kết thúc. |
| JsonParseException | JSON sai cú pháp, bao gồm nhiều lỗi không phải EOF. |
| JsonMappingException | JSON có thể parse được nhưng không ánh xạ được sang kiểu Java đích hoặc vi phạm quy tắc mapping. |
| IOException | Lỗi đọc nguồn, file, socket hoặc stream; có thể không phải lỗi cú pháp JSON. |

JsonProcessingException là nhóm exception cấp cao thường được dùng cho lỗi xử lý JSON trong Jackson Databind. JsonParseException và JsonMappingException là các nhánh cụ thể của nhóm lỗi này. IOException còn bao gồm lỗi I/O của nguồn dữ liệu.

Không nên phân loại mọi IOException thành JSON bị cắt. Ví dụ, socket có thể ném SocketTimeoutException hoặc một lỗi kết nối khác trước khi parser nhận được EOF. Hãy xem exception gốc và nguyên nhân lồng bên trong.

## 5. Vị trí lỗi giúp tìm nơi tài liệu bị cắt

Jackson thường gắn JsonLocation vào lỗi parse. Vị trí có thể chứa:

- Byte offset trong nguồn.
- Character offset nếu parser làm việc trên nguồn ký tự.
- Số dòng.
- Số cột.

Ví dụ ghi log vị trí:

~~~java
catch (JsonParseException e) {
    JsonLocation location = e.getLocation();

    if (location != null) {
        log.warn(
            "JSON error at line {}, column {}, byte offset {}",
            location.getLineNr(),
            location.getColumnNr(),
            location.getByteOffset()
        );
    }

    throw e;
}
~~~

Tên và độ sẵn có của offset phụ thuộc loại parser và nguồn đầu vào. Khi đọc từ Reader, byte offset có thể không có giá trị hữu ích; line và column thường phù hợp hơn. Khi đọc từ InputStream, byte offset có thể giúp xác định vị trí trong payload.

Thông tin vị trí hữu ích để:

- Xác định parser dừng ở đâu.
- Đối chiếu với log transport hoặc file nguồn.
- Tìm bản ghi bị cắt trong batch import.
- Trả lỗi có vị trí cho công cụ nội bộ.

Không nên đưa nguyên payload nhạy cảm vào log chỉ để chẩn đoán EOF. Hãy ghi loại lỗi, vị trí, mã correlation và thông tin nguồn phù hợp; nếu cần lưu payload để điều tra, áp dụng chính sách bảo vệ dữ liệu của hệ thống.

## 6. Đọc một JSON object và xác nhận toàn bộ nguồn đã được tiêu thụ

Ở tầng Databind, readValue() có thể deserialize root value đầu tiên. Nếu hợp đồng yêu cầu đúng một JSON document, ứng dụng cần xác nhận không còn token khác sau root.

Có thể bật FAIL_ON_TRAILING_TOKENS:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
    .build();

OrderRequest request =
    strictMapper.readValue(inputStream, OrderRequest.class);
~~~

Feature này kiểm tra token còn lại sau khi root value đã được deserialize. Nó giúp phát hiện một JSON value thứ hai đứng sau object đầu tiên.

Ví dụ:

~~~text
{"orderId":"ORD-100"} {"orderId":"ORD-101"}
~~~

Nếu chỉ đọc root đầu tiên mà không kiểm tra trailing tokens, ứng dụng có thể bỏ qua object thứ hai. Khi feature được bật, dữ liệu dư sẽ làm quá trình đọc thất bại.

Cần phân biệt hai loại vấn đề:

- JSON bị cắt giữa cấu trúc: parser gặp EOF bất thường và báo lỗi parse.
- JSON root hoàn chỉnh nhưng có thêm root value: document đầu tiên đã hợp lệ, nhưng input vi phạm hợp đồng chỉ cho phép một root value; FAIL_ON_TRAILING_TOKENS phát hiện token dư.

Whitespace sau root là hợp lệ và không bị xem là trailing token.

## 7. Đọc thủ công bằng JsonParser và kiểm tra token cuối

Khi dùng Streaming API trực tiếp, ứng dụng có thể kiểm tra cấu trúc theo token. Nếu cần đúng một root value, sau khi xử lý xong root, hãy yêu cầu parser đọc tiếp và xác nhận EOF hợp lệ.

Ví dụ minh họa cho một object:

~~~java
try (JsonParser parser = factory.createParser(inputStream)) {
    JsonToken first = parser.nextToken();

    if (first != JsonToken.START_OBJECT) {
        throw new IllegalArgumentException("Expected one JSON object");
    }

    // Đọc và xử lý toàn bộ object.
    while (parser.nextToken() != JsonToken.END_OBJECT) {
        // Xử lý field/value theo schema.
    }

    // Đọc tiếp để kiểm tra token ngoài root.
    JsonToken trailing = parser.nextToken();

    if (trailing != null) {
        throw new IllegalArgumentException("Unexpected data after root object");
    }
}
~~~

Ví dụ trên giả định parser đã đọc được một object và vòng lặp xử lý đầy đủ mọi cấu trúc lồng nhau theo cách đúng. Trong code thực tế, không nên dùng vòng lặp đơn giản này để bỏ qua object lồng hoặc array; cần quản lý depth hoặc dùng API đọc subtree phù hợp.

Cách ít lỗi hơn khi ánh xạ object vào DTO là dùng ObjectReader cùng FAIL_ON_TRAILING_TOKENS. Khi cần streaming thủ công, phải bảo đảm parser đã tiêu thụ hết cấu trúc root trước khi kiểm tra token tiếp theo.

Nếu parser ném JsonEOFException trong vòng lặp, document chưa hoàn chỉnh. Nếu parser trả null sau root hoàn chỉnh, nguồn đã kết thúc đúng cú pháp. Nếu trả token khác null, có thêm nội dung sau root.

## 8. Phân biệt tài liệu bị cắt với nguồn kết thúc ngay sau một root hợp lệ

Đây là giới hạn quan trọng của parser: Jackson chỉ có thể xác định cú pháp của byte đã nhận. Nó không thể biết producer dự định gửi thêm dữ liệu gì nếu document đã hoàn chỉnh.

Ví dụ nguồn kết thúc sau:

~~~json
{"orderId":"ORD-100"}
~~~

Đây là một JSON document hợp lệ. Nếu producer dự định gửi thêm một field nhưng kết nối bị đóng sau dấu ngoặc nhọn, parser không thể biết ý định đó. Đối với JSON, object đã hoàn chỉnh.

Nếu giao thức cần bảo đảm payload đã được truyền đầy đủ theo kích thước hoặc nội dung dự kiến, cần framing hoặc metadata ở tầng transport:

- Content-Length hoặc độ dài frame do giao thức quy định.
- Chunked transfer framing và việc kết thúc message hợp lệ.
- Message envelope có trường cuối hoặc trạng thái hoàn tất.
- Checksum hoặc chữ ký trên toàn payload.
- Sequence number và acknowledgement của message queue.
- Độ dài bản ghi trong giao thức binary hoặc length-prefixed stream.

Không dùng việc “Jackson parse thành công” như bằng chứng duy nhất rằng quá trình truyền tải không bị cắt. Nó chỉ chứng minh phần dữ liệu đã nhận tạo thành một JSON document hợp lệ.

Ngược lại, nếu parser ném lỗi vì thiếu dấu đóng object hoặc token chưa hoàn tất, đây là bằng chứng trực tiếp rằng nội dung nhận được không tạo thành một document JSON hoàn chỉnh.

## 9. Kiểm tra Content-Length và lỗi đọc nguồn

Trong HTTP, tầng transport hoặc framework thường quản lý việc đọc body và kiểm tra framing. Nếu request khai báo Content-Length lớn hơn số byte thực tế nhận được, tầng HTTP có thể phát hiện lỗi trước hoặc trong khi Jackson parse.

Tuy nhiên, cách lỗi được biểu diễn phụ thuộc server, HTTP client, proxy và cách body được cung cấp cho ứng dụng. Có thể gặp:

- IOException từ stream.
- Client disconnect hoặc connection reset.
- Lỗi framing của HTTP server.
- JsonEOFException nếu Jackson nhận một stream kết thúc khi JSON còn dang dở.

Nếu dùng InputStream từ file, hãy kiểm tra thêm kích thước file hoặc metadata nếu quy trình nhập dữ liệu có độ dài mong đợi. Với stream không có độ dài khai báo, ứng dụng cần dựa vào framing của giao thức hoặc cấu trúc JSON để quyết định hoàn tất.

Ví dụ kiểm tra kích thước file trước khi parse:

~~~java
long actualSize = Files.size(path);

if (expectedSize >= 0 && actualSize != expectedSize) {
    throw new IOException("Input file size does not match expected size");
}

try (InputStream input = Files.newInputStream(path)) {
    OrderRequest request = mapper.readValue(input, OrderRequest.class);
}
~~~

expectedSize phải đến từ metadata đáng tin cậy của quy trình tạo file. Nếu metadata và file cùng được ghi bởi một tiến trình có lỗi, cần thêm checksum hoặc giao thức commit để xác nhận tính toàn vẹn.

Không nên tự đếm byte từ một InputStream rồi đọc lại cùng stream nếu không có buffering hoặc cơ chế rewind. Mọi phép đo kích thước phải được thực hiện trên nguồn có thể kiểm tra độc lập hoặc trong wrapper đếm byte ngay từ đầu.

## 10. Đọc nhiều bản ghi trong một luồng

Một số hệ thống cố ý truyền nhiều JSON value nối tiếp nhau thay vì một root array. Khi đó, EOF hợp lệ phải được đánh giá theo ranh giới bản ghi.

Có ba dạng framing thường gặp:

| Dạng dữ liệu | Cấu trúc |
|---|---|
| JSON array | Một root array chứa nhiều phần tử. |
| NDJSON / JSON Lines | Mỗi dòng là một JSON document độc lập. |
| Root-value sequence | Nhiều JSON root value được đọc nối tiếp theo giao thức đã thống nhất. |

Với JSON array, parser chỉ xem document hoàn chỉnh khi gặp END_ARRAY và các cấu trúc bên ngoài đã đóng.

Với NDJSON, mỗi dòng có ranh giới riêng. Một dòng cuối bị cắt dở phải được xem là bản ghi lỗi; không nên coi việc file kết thúc là lý do tự động chấp nhận dòng đó.

Với root-value sequence, Jackson có thể đọc từng value bằng MappingIterator:

~~~java
ObjectReader reader = mapper.readerFor(Event.class);

try (MappingIterator<Event> events = reader.readValues(inputStream)) {
    while (events.hasNextValue()) {
        Event event = events.nextValue();
        process(event);
    }
}
~~~

Nếu một record trong sequence bị cắt giữa chừng, việc đọc record đó sẽ ném lỗi parse/EOF. Ứng dụng cần quyết định dừng toàn bộ stream, quarantine record hoặc yêu cầu producer gửi lại. Không nên tiếp tục parse từ vị trí không xác định nếu parser không thể phục hồi một ranh giới đáng tin cậy.

Đối với hệ thống yêu cầu phục hồi từng bản ghi, NDJSON hoặc framing có độ dài thường dễ cô lập lỗi hơn một chuỗi root value không có ranh giới ngoài JSON.

## 11. Đọc NDJSON theo từng dòng và xử lý dòng cuối

Một cách triển khai đơn giản là đọc từng dòng, rồi parse mỗi dòng như một JSON document riêng:

~~~java
try (BufferedReader input = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    long lineNumber = 0;

    while ((line = input.readLine()) != null) {
        lineNumber++;

        if (line.isBlank()) {
            continue;
        }

        try {
            Event event = mapper.readValue(line, Event.class);
            process(event);
        } catch (JsonProcessingException e) {
            log.warn("Invalid JSON record at line {}", lineNumber, e);
            throw e;
        }
    }
}
~~~

Nếu dòng cuối chứa object chưa đóng, Jackson sẽ báo lỗi cho dòng đó. Nếu dòng cuối là object hoàn chỉnh, nó là một bản ghi hợp lệ theo cú pháp NDJSON, dù file kết thúc ngay sau dòng đó.

Nếu ứng dụng cần phát hiện dòng cuối bị thiếu do file ghi chưa hoàn tất, cần thêm giao thức ở ngoài JSON: file tạm rồi atomic rename, marker hoàn tất, số bản ghi dự kiến, checksum hoặc manifest. Không thể suy ra việc thiếu record chỉ từ một dòng JSON cuối hoàn chỉnh.

NDJSON cho phép một JSON document trên mỗi dòng; không nên tự động cho phép một dòng chứa nhiều root value nếu hợp đồng không quy định như vậy. Có thể bật FAIL_ON_TRAILING_TOKENS cho mapper/reader dùng để parse từng dòng.

## 12. Xử lý exception ở ranh giới phù hợp

Không nên bắt JsonEOFException ở mọi tầng rồi chuyển thành null hoặc object mặc định. Điều đó có thể khiến payload lỗi tiếp tục đi vào nghiệp vụ như thể hợp lệ.

Một cách tổ chức là phân loại lỗi ở tầng adapter:

~~~java
public OrderRequest parseRequest(InputStream input) throws IOException {
    try {
        return strictReader.readValue(input);
    } catch (JsonEOFException e) {
        throw new InvalidPayloadException(
            "JSON document ended before its structure was complete",
            e
        );
    } catch (JsonParseException e) {
        throw new InvalidPayloadException(
            "JSON syntax is invalid",
            e
        );
    }
}
~~~

InvalidPayloadException là exception của ứng dụng, cần được định nghĩa riêng. Trong ứng dụng HTTP, adapter có thể ánh xạ nó sang phản hồi 400 Bad Request. Trong consumer message queue, adapter có thể đánh dấu message lỗi, đưa vào dead-letter queue hoặc yêu cầu retry tùy loại lỗi và chính sách hệ thống.

Cần phân biệt lỗi có thể retry và lỗi không thể retry:

- JSON sai cú pháp do producer gửi thường không tự hết khi retry cùng payload.
- Connection reset hoặc timeout có thể là lỗi tạm thời; producer có thể gửi lại toàn message.
- File đang được ghi dở có thể hợp lệ sau khi producer hoàn tất; consumer nên đợi tín hiệu hoàn tất thay vì parse file chưa commit.
- Schema mismatch hoặc mapping lỗi có thể cần sửa producer hoặc phiên bản consumer.

Không tự retry vô hạn một payload đã biết là JSON sai cú pháp. Hãy lưu mã lỗi, nguồn message và correlation id để hỗ trợ điều tra.

## 13. Không dùng dữ liệu đã parse một phần như một document hợp lệ

Khi parser đã đọc được một số field trước lúc gặp EOF, các giá trị đó không có nghĩa toàn bộ request hợp lệ.

Ví dụ:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "id": "CUS-17"
  },
  "items": [
    {"sku": "BOOK-01", "quantity": 2},
~~~

Ứng dụng có thể đã nhìn thấy orderId và customer trước khi lỗi xảy ra ở array items. Không nên tạo hoặc lưu một đơn hàng chỉ từ các field đã đọc nếu hợp đồng yêu cầu toàn bộ document.

Với databinding, readValue() thông thường không trả về một DTO hoàn chỉnh khi parser ném lỗi trong quá trình bind. Với streaming thủ công, code có thể đã thực hiện side effect cho các token trước đó; do đó cần thiết kế transaction hoặc staging:

1. Parse và kiểm tra toàn bộ document.
2. Lưu dữ liệu tạm trong bộ nhớ hoặc vùng staging.
3. Chỉ commit side effect sau khi root hoàn chỉnh và các validation cần thiết đã thành công.

Nếu xử lý từng record độc lập trong một stream lớn, có thể commit sau mỗi record đã hoàn chỉnh và hợp lệ, nhưng phải có ranh giới record rõ ràng.

## 14. Kiểm thử EOF và kết thúc nguồn không hợp lệ

Test nên bao gồm ít nhất các tình huống:

- Object hoàn chỉnh.
- Array hoàn chỉnh.
- Object thiếu dấu đóng.
- Array thiếu dấu đóng.
- String thiếu dấu nháy cuối.
- Number có phần thập phân hoặc exponent chưa hoàn chỉnh.
- Root hoàn chỉnh nhưng có token thứ hai.
- Root hoàn chỉnh theo sau bởi whitespace.
- Lỗi I/O từ nguồn.

Ví dụ JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.io.JsonEOFException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

class TruncatedJsonTest {

    record OrderRequest(String orderId) {}

    private final ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
        .build();

    @Test
    void acceptsCompleteDocument() {
        assertDoesNotThrow(() ->
            mapper.readValue("{\"orderId\":\"ORD-100\"}", OrderRequest.class)
        );
    }

    @Test
    void acceptsWhitespaceAfterCompleteDocument() {
        assertDoesNotThrow(() ->
            mapper.readValue("{\"orderId\":\"ORD-100\"} \n\t", OrderRequest.class)
        );
    }

    @Test
    void rejectsObjectMissingClosingBrace() {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue("{\"orderId\":\"ORD-100\"", OrderRequest.class)
        );
    }

    @Test
    void rejectsUnterminatedString() {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue("{\"orderId\":\"ORD-100}", OrderRequest.class)
        );
    }

    @Test
    void rejectsSecondRootValue() {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                "{\"orderId\":\"ORD-100\"} true",
                OrderRequest.class
            )
        );
    }
}
~~~

Có thể dùng JsonEOFException.class trong assertThrows nếu test gắn với phiên bản Jackson và input cụ thể đã được xác nhận tạo exception đó. Dùng JsonProcessingException.class phù hợp hơn khi chỉ muốn khẳng định dữ liệu không hợp lệ mà không phụ thuộc vào subclass chi tiết.

Test cần chạy trên phiên bản Jackson thực tế của dự án. Exception cụ thể và thông báo lỗi có thể thay đổi theo phiên bản parser, loại nguồn và vị trí EOF.

## 15. Các lưu ý khi đọc từ nguồn không đồng bộ hoặc không chặn

Trong ứng dụng có non-blocking parser, việc chưa có thêm byte tại một thời điểm không đồng nghĩa nguồn đã kết thúc. Parser có thể cần chờ dữ liệu tiếp theo thay vì báo EOF.

Với non-blocking parsing, cần phân biệt trạng thái:

- Parser cần thêm input (NOT_AVAILABLE trong API tương ứng).
- Nguồn đã thực sự kết thúc.
- JSON document đã hoàn chỉnh.
- JSON document bị cắt khi nguồn xác nhận kết thúc.

Không được gọi endOfInput() chỉ vì buffer hiện tại đã hết dữ liệu. Chỉ gọi khi transport hoặc producer xác nhận không còn byte nào nữa. Nếu báo end-of-input quá sớm, parser sẽ hiểu phần JSON còn thiếu là tài liệu bị cắt.

Ngược lại, nếu không báo end-of-input khi nguồn đã kết thúc, parser có thể chờ thêm dữ liệu và ứng dụng không phát hiện document chưa hoàn chỉnh.

Với asynchronous/non-blocking parser, hãy theo đúng vòng đời feeder và parser của phiên bản Jackson đang dùng. Phần logic xác nhận hoàn tất phải nằm ở tầng quản lý transport, nơi biết chắc nguồn còn dữ liệu hay đã kết thúc.

## 16. Quy trình xử lý một JSON stream đáng tin cậy

Một pipeline đọc dữ liệu có thể tổ chức như sau:

~~~text
Nguồn dữ liệu
  |
  v
Transport / framing
  |  - xác định message bắt đầu/kết thúc
  |  - kiểm tra độ dài hoặc trạng thái hoàn tất nếu có
  v
Jackson JsonParser / ObjectReader
  |  - parse token
  |  - phát hiện EOF bất thường
  |  - kiểm tra trailing tokens nếu chỉ cho phép một root
  v
Mapping / validation
  |  - kiểm tra kiểu và miền giá trị
  |  - không dùng object parse dở
  v
Commit nghiệp vụ
~~~

Các bước quan trọng:

1. Xác định giao thức là một JSON document, một array, NDJSON hay sequence nhiều root.
2. Đảm bảo transport đã cung cấp toàn bộ message theo framing của nó.
3. Đọc hết document bằng parser hoặc ObjectReader.
4. Xử lý JsonEOFException như một document chưa hoàn chỉnh.
5. Phân biệt lỗi parse với IOException của nguồn.
6. Kiểm tra token dư nếu hợp đồng chỉ cho phép một root value.
7. Chỉ thực hiện side effect sau khi record/document đã hoàn chỉnh và hợp lệ.

## Kết luận

EOF chỉ hợp lệ khi parser đã đọc xong một JSON root value và phần còn lại là khoảng trắng. Nếu nguồn kết thúc khi object, array, string, number hoặc literal vẫn chưa hoàn chỉnh, Jackson báo lỗi parse, thường có thể nhận diện bằng JsonEOFException. JsonParseException còn bao gồm những lỗi cú pháp khác, trong khi IOException có thể bắt nguồn từ transport hoặc file.

Hãy đọc parser đến hết document, kiểm tra trailing tokens khi hợp đồng chỉ cho phép một root, ghi nhận JsonLocation để chẩn đoán và phân biệt lỗi cú pháp với lỗi I/O. Với stream nhiều bản ghi, phải xác định framing rõ ràng; với nguồn không đồng bộ, chỉ báo end-of-input khi transport xác nhận thực sự đã hết dữ liệu. Không sử dụng object hoặc side effect được tạo từ dữ liệu parse dở như một document hợp lệ.

