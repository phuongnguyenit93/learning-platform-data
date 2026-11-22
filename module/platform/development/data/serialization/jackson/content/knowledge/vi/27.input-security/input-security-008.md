# Từ chối cấu trúc lặp bất thường và tài liệu gây tiêu tốn tài nguyên

JSON là định dạng văn bản linh hoạt, nhưng một request JSON hợp lệ về cú pháp vẫn có thể gây hại cho ứng dụng nếu nó quá lớn, lồng quá sâu hoặc chứa quá nhiều phần tử lặp lại. Một payload có thể buộc server cấp phát bộ nhớ lớn, tạo object graph khổng lồ, tiêu tốn CPU khi parse/validate hoặc làm cạn thread và tài nguyên I/O.

Trong Jackson, có thể giảm rủi ro bằng cách kết hợp các lớp bảo vệ:

- Bật kiểm tra duplicate field nếu hợp đồng không cho phép tên property lặp.
- Đặt giới hạn parser cho độ sâu nesting, độ dài string và number bằng `StreamReadConstraints`.
- Giới hạn kích thước request ở gateway/server và đếm byte thực nhận, kể cả khi body được truyền theo chunk.
- Giới hạn số phần tử array, số property và tổng lượng dữ liệu ở tầng ứng dụng khi parser constraint không bao phủ trực tiếp.
- Dùng Streaming API để xử lý dữ liệu lớn theo từng phần tử thay vì materialize toàn bộ document thành cây hoặc collection.
- Đặt timeout, giới hạn tốc độ và giới hạn sau giải nén để chống request chậm hoặc payload nén phình lớn.

Không có một feature đơn lẻ nào biến mọi JSON đầu vào thành an toàn. Cần xác định giới hạn theo hợp đồng API, cấu hình parser trước khi dùng mapper và kiểm soát tài nguyên ở cả tầng HTTP lẫn tầng xử lý nghiệp vụ.

## 1. JSON hợp lệ vẫn có thể là input nguy hiểm

Jackson kiểm tra cú pháp JSON và chuyển đổi dữ liệu. Nhưng cú pháp hợp lệ không đồng nghĩa với payload có kích thước hoặc cấu trúc phù hợp để xử lý.

Ví dụ một object lồng sâu:

```json
{"a":{"a":{"a":{"a":{"a":{"a":{}}}}}}}
```

Một cấu trúc như vậy có thể tiếp tục lồng hàng nghìn tầng. Nếu ứng dụng dùng recursive deserializer, validation đệ quy hoặc tạo object graph tương ứng, stack và CPU có thể bị tiêu tốn đáng kể.

Một array rất lớn cũng có thể gây áp lực bộ nhớ:

```json
{
  "items": [
    {"id": 1},
    {"id": 2},
    {"id": 3}
  ]
}
```

Đoạn ví dụ chỉ có ba phần tử, nhưng một request có thể chứa hàng triệu phần tử tương tự. Nếu DTO khai báo `List<Item>` hoặc ứng dụng đọc toàn bộ thành `JsonNode`, Jackson sẽ tạo và giữ nhiều object/node cho đến khi xử lý xong.

Các dạng payload cần giới hạn gồm:

| Dạng input | Rủi ro |
| --- | --- |
| Object/array lồng rất sâu | Stack overflow, chi phí traversal và validation cao |
| Array có quá nhiều phần tử | Tạo collection lớn, tăng heap và thời gian xử lý |
| Object có quá nhiều property | Tăng số token, map entry và chi phí binding |
| String hoặc tên field rất dài | Cấp phát buffer lớn, tăng CPU và bộ nhớ |
| Number token cực dài | Tốn thời gian parse và tạo số lớn |
| Duplicate field | Các consumer có thể hiểu giá trị khác nhau; có thể bị khai thác để vượt kiểm tra |
| Document tổng thể quá lớn | Tốn băng thông, bộ nhớ, thời gian parse và log |
| Body nén phình rất lớn sau giải nén | Vượt giới hạn bộ nhớ dù kích thước truyền tải nhỏ |
| Request gửi rất chậm | Giữ kết nối và tài nguyên server trong thời gian dài |

JSON chuẩn biểu diễn dữ liệu dạng cây, không có tham chiếu object hay vòng lặp như Java object graph. “Cấu trúc lặp bất thường” trong JSON thường thể hiện qua duplicate property names, nhiều container lồng nhau hoặc rất nhiều phần tử giống nhau; không phải một reference cycle được mã hóa trực tiếp trong JSON.

## 2. Từ chối tên property trùng lặp

Một JSON object có thể xuất hiện cùng tên property nhiều lần:

```json
{
  "role": "user",
  "role": "admin"
}
```

Đây là input nguy hiểm vì các parser hoặc hệ thống trung gian có thể xử lý khác nhau. Một consumer có thể giữ giá trị đầu, consumer khác giữ giá trị cuối, hoặc một hệ thống có thể từ chối. Nếu gateway kiểm tra `role` theo giá trị đầu nhưng service phía sau dùng giá trị cuối, hai tầng có thể đưa ra quyết định khác nhau.

Khi hợp đồng API yêu cầu mỗi object chỉ có một property cho mỗi tên, hãy bật strict duplicate detection ở parser:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;

JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();
```

Tạo mapper dùng factory đó:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper(factory);
```

Khi parser gặp một tên field đã xuất hiện trong cùng object, nó báo lỗi thay vì tiếp tục âm thầm. Kiểm tra được thực hiện riêng trong từng object; cùng tên `id` ở hai object khác nhau là bình thường:

```json
{
  "customer": {"id": "C-1"},
  "order": {"id": "O-1"}
}
```

### 2.1. Strict duplicate detection và Tree Model

Nếu ứng dụng đọc JSON thành `JsonNode`, Jackson còn có feature:

```java
mapper.enable(DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY);
```

Feature này dành cho việc phát hiện duplicate key khi xây dựng tree model. `StreamReadFeature.STRICT_DUPLICATE_DETECTION` là kiểm tra ở tầng parser và có thể áp dụng rộng hơn cho các đường đọc JSON sử dụng factory đó.

Nếu yêu cầu là từ chối duplicate field ở mọi endpoint, ưu tiên cấu hình parser/factory chung thay vì chỉ bật feature dành riêng cho tree. Có thể dùng cả hai khi ứng dụng có nhiều đường xử lý khác nhau, nhưng hãy hiểu phạm vi của từng feature.

### 2.2. Chi phí của duplicate detection

Để phát hiện tên lặp, parser phải theo dõi các tên đã gặp trong object hiện tại. Điều này sử dụng thêm bộ nhớ và CPU, đặc biệt với object có rất nhiều property. Với API nhận input không tin cậy, chi phí này thường đáng cân nhắc để tránh cách diễn giải mơ hồ. Tuy nhiên, vẫn cần giới hạn tổng số property và kích thước document.

Duplicate detection chỉ phát hiện tên JSON giống nhau trong cùng object. Nó không tự phát hiện hai tên alias khác nhau cùng ánh xạ vào một property Java. Ví dụ `email` và `email_address` có thể là hai tên JSON khác nhau nhưng cùng được khai báo qua `@JsonAlias`; nếu cả hai xuất hiện, ứng dụng cần có quy tắc riêng hoặc kiểm tra ở tầng mapping/validation.

## 3. Dùng StreamReadConstraints để giới hạn cấu trúc và token

Jackson Core cung cấp `StreamReadConstraints` để đặt giới hạn cho parser. Các giới hạn quan trọng trong nhiều phiên bản Jackson 2.x gồm:

- `maxNestingDepth`: độ sâu tối đa của object/array lồng nhau.
- `maxStringLength`: độ dài tối đa của string value.
- `maxNumberLength`: độ dài tối đa của token number.

Ví dụ cấu hình:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;

StreamReadConstraints constraints = StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxStringLength(1_000_000)
        .maxNumberLength(256)
        .build();

JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(constraints)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Các con số chỉ là ví dụ minh họa. API nhận metadata nhỏ có thể cần giới hạn thấp hơn; API upload nội dung văn bản lớn có thể cần chính sách khác. Hãy chọn giới hạn theo kích thước request, kiểu dữ liệu và mục đích endpoint.

Khi parser vượt giới hạn, Jackson ném lỗi đọc/constraint thay vì tiếp tục xử lý không giới hạn. Tùy phiên bản, loại exception cụ thể và thông điệp có thể khác nhau; ứng dụng nên phân loại đây là lỗi input vượt giới hạn, không phải lỗi nghiệp vụ.

### 3.1. Độ sâu nesting

`maxNestingDepth` hạn chế số tầng object/array lồng nhau. Giới hạn này hữu ích với payload có cấu trúc đệ quy hoặc JSON được tạo tự động.

Ví dụ một cấu trúc có độ sâu tăng dần:

```json
{"node":{"node":{"node":{"node":{"value":"x"}}}}}
```

Nếu hợp đồng chỉ cho phép vài tầng, không có lý do để chấp nhận hàng trăm hoặc hàng nghìn tầng. Đặt giới hạn thấp hơn giúp giảm rủi ro cho parser, custom deserializer và các bước xử lý sau đó.

Độ sâu parser không phải giới hạn độ sâu của mọi object graph Java sau khi deserialize. Custom deserializer có thể tạo thêm object hoặc đệ quy theo cách riêng; vẫn cần giới hạn ở tầng ứng dụng nếu code có traversal đệ quy.

### 3.2. Độ dài string và tên field

String value có thể chứa dữ liệu lớn như mô tả, nội dung văn bản hoặc Base64. Tên field cũng có thể bị gửi với độ dài bất thường. `maxStringLength` giới hạn string value; hỗ trợ giới hạn tên field riêng phụ thuộc phiên bản Jackson Core đang dùng.

Nếu phiên bản dự án có API giới hạn độ dài property name, có thể cấu hình thêm theo tài liệu của phiên bản đó. Nếu chưa có, vẫn phải giới hạn kích thước document/request tổng thể và tránh chấp nhận object có hàng nghìn tên field dài.

Đừng đặt `maxStringLength` chỉ dựa vào độ dài ký tự nhìn thấy trong JSON mà quên encoding. Với parser đọc UTF-8, một ký tự có thể chiếm nhiều byte; giới hạn parser và giới hạn byte HTTP là hai lớp khác nhau.

### 3.3. Độ dài number

Number token có thể chứa rất nhiều chữ số hoặc exponent dài:

```json
{"amount": 999999999999999999999999999999999999999999999999999999999999999999}
```

Một number rất dài có thể làm tăng thời gian parse và chi phí tạo `BigInteger`/`BigDecimal`. `maxNumberLength` giới hạn số ký tự trong token number trước khi Jackson xử lý sâu hơn.

Ngoài giới hạn parser, domain vẫn cần giới hạn giá trị thực tế. Ví dụ, một số tiền có thể có token ngắn nhưng giá trị vượt giới hạn kinh doanh; đây là vấn đề validation/domain chứ không chỉ parser constraint.

## 4. Cấu hình giới hạn cho toàn ứng dụng

`JsonFactory` giữ cấu hình parser và được `ObjectMapper` sử dụng khi tạo parser. Hãy tạo factory với constraint cần thiết rồi tạo mapper từ factory đó:

```java
JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
                StreamReadConstraints.builder()
                        .maxNestingDepth(80)
                        .maxStringLength(512_000)
                        .maxNumberLength(128)
                        .build()
        )
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Các endpoint dùng mapper này sẽ nhận parser từ factory đã cấu hình. Trong Spring Boot, hãy cấu hình đúng `ObjectMapper` được HTTP message converter sử dụng; tạo một mapper riêng trong controller sẽ không giúp bảo vệ mapper của converter.

### 4.1. Phiên bản Jackson

`StreamReadConstraints` được bổ sung trong các phiên bản Jackson 2.x mới hơn (từ dòng 2.15). Các method và giới hạn có thể được mở rộng qua từng bản phát hành. Hãy:

- Kiểm tra phiên bản `jackson-core` thực tế trong dependency tree.
- Dùng Jackson BOM hoặc dependency management để các module Jackson đồng bộ phiên bản.
- Chỉ gọi method có trong phiên bản đang dùng.
- Đọc tài liệu của đúng minor version thay vì sao chép cấu hình từ một bản mới hơn.
- Kiểm thử rằng mapper production thực sự dùng factory có constraint.

Không nên chỉ nâng riêng `jackson-core` trong khi `jackson-databind` và các module Jackson khác lệch phiên bản. Hãy nâng theo một bộ phiên bản tương thích.

## 5. Parser constraints không thay thế giới hạn kích thước request

`StreamReadConstraints` giới hạn một số đặc điểm của cú pháp/token. Nó không phải giới hạn tổng byte HTTP cho mọi trường hợp và không thay thế giới hạn request body ở server hoặc API gateway.

Ví dụ, một JSON array có thể chứa hàng triệu object nhỏ. Mỗi string và number đều nằm trong giới hạn, nesting depth thấp, nhưng tổng document vẫn rất lớn. Parser constraints không tự đặt giới hạn số phần tử array hoặc tổng số property cho mọi kiểu binding.

Vì vậy cần giới hạn body ở tầng nhận dữ liệu:

- Đặt maximum request size ở reverse proxy/API gateway.
- Đặt giới hạn ở HTTP server hoặc framework.
- Kiểm tra `Content-Length` nếu có, nhưng không chỉ dựa vào header này.
- Đếm byte thực tế khi đọc body, đặc biệt với chunked transfer hoặc request không có content length đáng tin cậy.
- Dừng đọc và trả lỗi phù hợp khi vượt giới hạn.

Header `Content-Length` do client gửi không phải bằng chứng duy nhất về kích thước thực tế. Server phải áp dụng giới hạn cho byte thực nhận để tránh bypass bằng transfer encoding hoặc request framing khác.

## 6. Giới hạn array và số property ở tầng ứng dụng

Một payload có thể có nesting nông nhưng chứa rất nhiều phần tử:

```json
{
  "ids": [1, 2, 3, 4, 5]
}
```

Nếu hợp đồng cho phép tối đa 500 id, cần từ chối array có phần tử thứ 501. `StreamReadConstraints` không thay thế quy tắc nghiệp vụ này; hãy kiểm tra số phần tử trong DTO validation hoặc khi streaming.

### 6.1. Giới hạn collection sau khi deserialize

Với collection nhỏ và DTO rõ ràng, có thể dùng Bean Validation:

```java
public class BatchRequest {
    @NotEmpty
    @Size(max = 500)
    private List<@NotNull @Valid ItemRequest> items;
}
```

Ràng buộc `@Size(max = 500)` kiểm tra collection sau khi Jackson đã tạo danh sách. Nó giúp bảo đảm dữ liệu nghiệp vụ không vượt số phần tử, nhưng không ngăn Jackson phải deserialize toàn bộ danh sách trước khi validation chạy.

Nếu mục tiêu là bảo vệ tài nguyên ngay trong quá trình parse, hãy dùng streaming hoặc custom deserializer đếm phần tử trước khi tạo collection lớn.

### 6.2. Đếm phần tử khi đọc array bằng Streaming API

Ví dụ đọc array ở root và bind từng item:

```java
private static final int MAX_ITEMS = 500;

try (JsonParser parser = factory.createParser(input)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw JsonMappingException.from(parser, "Root phải là array");
    }

    int count = 0;
    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (parser.currentToken() == null) {
            throw JsonMappingException.from(parser, "Array kết thúc bất thường");
        }

        if (++count > MAX_ITEMS) {
            throw JsonMappingException.from(
                    parser,
                    "Array vượt quá " + MAX_ITEMS + " phần tử"
            );
        }

        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw JsonMappingException.from(parser, "Mỗi item phải là object");
        }

        ItemRequest item = mapper.readValue(parser, ItemRequest.class);
        process(item);
    }
}
```

`mapper.readValue(parser, ItemRequest.class)` tiêu thụ object hiện tại. Vòng lặp tiếp tục ở phần tử kế tiếp. Ứng dụng không cần giữ toàn bộ array trong một `List`; có thể xử lý từng item rồi giải phóng tham chiếu.

Nếu array nằm trong một property lồng nhau, áp dụng cùng nguyên tắc trong custom deserializer của property hoặc một parser chuyên trách. Cần quy định rõ ai gọi `nextToken()` và ai tiêu thụ token đóng array.

### 6.3. Giới hạn số field trong object

Với object có schema động, có thể cần giới hạn số property. Khi tự đọc object bằng Streaming API, đếm mỗi `FIELD_NAME`:

```java
private static final int MAX_FIELDS = 200;

if (parser.nextToken() != JsonToken.START_OBJECT) {
    throw JsonMappingException.from(parser, "Expected object");
}

int fieldCount = 0;
while (parser.nextToken() != JsonToken.END_OBJECT) {
    if (parser.currentToken() != JsonToken.FIELD_NAME) {
        throw JsonMappingException.from(parser, "Expected field name");
    }

    if (++fieldCount > MAX_FIELDS) {
        throw JsonMappingException.from(parser, "Object có quá nhiều property");
    }

    String name = parser.currentName();
    JsonToken valueToken = parser.nextToken();
    if (valueToken == null) {
        throw JsonMappingException.from(parser, "Thiếu value cho " + name);
    }

    // Xử lý value hoặc bỏ qua subtree nếu không cần.
    parser.skipChildren();
}
```

Đoạn code minh họa cách đếm property trong một object hiện tại. Với object lồng nhau, nếu cần giới hạn tổng số field trên toàn document, phải duy trì bộ đếm dùng chung qua các cấp hoặc dùng một parser delegate/validation layer có trạng thái toàn cục cho document.

Đừng dùng `@Size` trên một map như biện pháp duy nhất nếu mục tiêu là chặn trước khi map khổng lồ được tạo; validation sau binding có thể đến quá muộn để bảo vệ heap.

## 7. Giới hạn tổng số token và tổng công việc

Ngay cả khi mỗi string ngắn và mỗi array không quá lớn riêng lẻ, document có thể có nhiều nhánh lồng nhau tạo ra tổng số token rất cao. Trong trường hợp đó, cần giới hạn tổng lượng công việc.

Các lựa chọn:

- Giới hạn byte request ở tầng HTTP.
- Đếm tổng token trong custom streaming pipeline.
- Giới hạn số phần tử và số field ở từng container.
- Giới hạn số object được tạo trong một batch.
- Dùng deadline hoặc timeout cho toàn bộ request.
- Hủy xử lý nếu request đã vượt ngân sách tài nguyên.

Một giới hạn token tổng quát có thể được thực hiện bằng wrapper `JsonParserDelegate` hoặc parser layer riêng đếm mỗi lần `nextToken()` trả token dữ liệu. Khi vượt ngưỡng, wrapper ném `JsonParseException`/mapping exception phù hợp. Đây là cơ chế nâng cao; phải bảo đảm wrapper vẫn chuyển tiếp đúng các API khác của parser và không đếm `NOT_AVAILABLE` như token dữ liệu trong non-blocking flow.

Không nên chỉ dựa vào giới hạn số byte: một document nhỏ nhưng lồng sâu có thể gây chi phí traversal lớn; ngược lại một document lớn gồm chuỗi dài có thể tiêu tốn bộ nhớ ngay cả khi số token thấp.

## 8. Dùng Streaming API thay vì tạo toàn bộ cây cho document lớn

`ObjectMapper.readTree()` tạo cây node cho toàn bộ document. `readValue()` vào DTO có collection lớn cũng thường tạo toàn bộ object graph. Với batch lớn, streaming giúp xử lý từng phần tử:

```text
JSON array lớn
      │
      ▼
JsonParser
      │ đọc START_ARRAY
      ▼
đọc một item
      │
      ▼
bind một DTO
      │
      ▼
validate + process + persist
      │
      ▼
giải phóng item rồi đọc item kế tiếp
```

Ví dụ:

```java
try (JsonParser parser = factory.createParser(input)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw JsonMappingException.from(parser, "Expected array");
    }

    int count = 0;
    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (++count > MAX_ITEMS) {
            throw JsonMappingException.from(parser, "Too many items");
        }

        ItemRequest item = mapper.readValue(parser, ItemRequest.class);
        Set<ConstraintViolation<ItemRequest>> violations = validator.validate(item);
        if (!violations.isEmpty()) {
            throw new InvalidBatchItemException(count - 1, violations);
        }

        process(item);
    }
}
```

Đây là ví dụ xử lý tuần tự. Nếu cần transaction cho cả batch, hãy cân nhắc transaction boundary, rollback và cách báo lỗi phần tử cụ thể. Streaming giảm nhu cầu giữ toàn bộ danh sách trong heap nhưng không tự giới hạn thời gian xử lý hoặc số lần ghi database.

## 9. Giới hạn dữ liệu nén và payload phình lớn

Một request có thể được gửi ở dạng gzip hoặc encoding nén khác. Kích thước truyền tải có thể nhỏ nhưng dữ liệu sau giải nén lớn hơn nhiều. Nếu chỉ giới hạn số byte nén, server vẫn có thể bị buộc giải nén một payload rất lớn.

Nên có hai giới hạn:

- **Compressed size:** số byte nhận từ mạng trước giải nén.
- **Decompressed size:** số byte thực tế được đưa vào JSON parser sau giải nén.

Giới hạn sau giải nén cần được áp dụng tại lớp giải nén hoặc stream wrapper đếm byte. Parser chỉ nhìn thấy dữ liệu sau giải nén, nên body-size limit ở HTTP server cần hiểu rõ vị trí của compression middleware.

Ngoài ra, đặt timeout giải nén và giới hạn tỷ lệ phình nếu hạ tầng hỗ trợ. Không chấp nhận một request nén chỉ vì header `Content-Encoding` hợp lệ.

## 10. Timeout và tốc độ nhận dữ liệu

Một JSON document nhỏ vẫn có thể giữ kết nối lâu nếu client gửi từng byte với khoảng nghỉ dài. Đây là dạng slow request/slowloris ở tầng vận chuyển, không phải vấn đề parser token.

Các biện pháp ở tầng HTTP/network:

- Read timeout hoặc request deadline.
- Giới hạn thời gian tối đa để nhận toàn bộ body.
- Giới hạn số kết nối đồng thời và số request đang parse.
- Giới hạn tốc độ gửi hoặc dùng cơ chế rate limiting theo client.
- Hủy parser và giải phóng tài nguyên khi client ngắt kết nối hoặc deadline hết hạn.

Non-blocking parser không tự giải quyết slowloris. Nó giúp không giữ thread chờ byte trong lúc parser cần thêm input, nhưng kết nối và trạng thái parser vẫn tiêu tốn tài nguyên. Event loop vẫn cần timeout, backpressure và giới hạn số kết nối.

## 11. Backpressure khi xử lý array lớn

Nếu parser đọc nhanh hơn tầng nghiệp vụ có thể lưu dữ liệu, ứng dụng có thể tạo hàng đợi không giới hạn. Khi đó, dù parser không giữ toàn bộ JSON, queue vẫn có thể làm heap tăng mạnh.

Hãy giữ pipeline có giới hạn:

1. Parse một phần tử.
2. Validate và chuyển phần tử vào worker/database.
3. Chỉ đọc tiếp khi downstream còn khả năng xử lý hoặc queue còn chỗ.
4. Tạm dừng đọc khi downstream bị nghẽn.
5. Hủy request khi vượt deadline hoặc giới hạn tài nguyên.

Với reactive pipeline, dùng cơ chế demand/backpressure của thư viện. Với vòng lặp blocking, xử lý tuần tự hoặc dùng queue bounded thay vì queue vô hạn.

## 12. Giới hạn cho custom deserializer và Tree Model

Custom deserializer có thể tự tạo rủi ro nếu đọc toàn bộ subtree vào `JsonNode`, rồi chuyển thành nhiều DTO hoặc copy nhiều lần.

Ví dụ:

```java
JsonNode root = parser.getCodec().readTree(parser);
JsonNode copy = root.deepCopy();
List<Item> items = mapper.convertValue(copy.get("items"), new TypeReference<>() {});
```

Đoạn code có thể đồng thời giữ:

- Cây `root` ban đầu.
- Bản sao `copy`.
- Collection `items` và object graph tương ứng.

Với subtree lớn, lượng heap có thể tăng nhiều lần so với kích thước JSON đầu vào. Hãy tránh `deepCopy()` nếu không cần bản sao độc lập; tránh serialize node thành string rồi parse lại; dùng `treeToValue()` khi cần chuyển một node; và dùng streaming trực tiếp nếu payload lớn.

Nếu custom deserializer nhận dữ liệu động, hãy giới hạn số field, độ sâu và kích thước payload trước khi tạo các cấu trúc phụ lớn. Parser constraints chỉ bảo vệ các khía cạnh mà nó hỗ trợ; code tùy biến phải tự giữ ngân sách tài nguyên.

## 13. Giới hạn parser không thay thế validation nghiệp vụ

Các giới hạn tài nguyên và validation có mục đích khác nhau:

| Lớp kiểm soát | Ví dụ | Mục tiêu |
| --- | --- | --- |
| HTTP/gateway | Body tối đa 2 MB, timeout 10 giây | Bảo vệ mạng, kết nối và request buffer |
| Jackson parser | Nesting tối đa 80, string tối đa 512 KB | Bảo vệ parser khỏi cấu trúc/token cực đoan |
| Streaming/application | Array tối đa 500 item, object tối đa 200 field | Bảo vệ collection và công việc xử lý |
| Bean Validation | `@Size(max = 80)`, `@Positive` | Kiểm tra dữ liệu Java theo hợp đồng |
| Domain/service | Batch chỉ chứa một tenant, trạng thái cho phép | Bảo đảm quy tắc nghiệp vụ và quyền hạn |

Ví dụ `@Size(max = 500)` trên `List<Item>` kiểm tra số phần tử sau khi list được tạo. Nó không ngăn parser phải tạo 100.000 phần tử trước khi validation báo lỗi. Nếu cần bảo vệ tài nguyên, giới hạn phải được áp dụng sớm hơn ở parser/streaming hoặc tầng HTTP.

## 14. Cấu hình với Spring Boot

Trong Spring Boot, HTTP request body thường được đọc bởi `HttpMessageConverter` sử dụng `ObjectMapper` do ứng dụng/framework cấu hình. Cần bảo đảm mapper được converter dùng đã được tạo với `JsonFactory` có constraints.

Một hướng cấu hình là cung cấp mapper/factory qua cơ chế builder/customizer của phiên bản Spring Boot đang dùng. Ví dụ khái quát:

```java
@Configuration
public class JacksonConfiguration {
    @Bean
    public ObjectMapper objectMapper() {
        StreamReadConstraints constraints = StreamReadConstraints.builder()
                .maxNestingDepth(80)
                .maxStringLength(512_000)
                .maxNumberLength(128)
                .build();

        JsonFactory factory = JsonFactory.builder()
                .streamReadConstraints(constraints)
                .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                .build();

        return new ObjectMapper(factory);
    }
}
```

Đây là ví dụ cấu hình mapper độc lập. Trong ứng dụng Spring Boot thực tế, không nên tạo bean `ObjectMapper` mới mà bỏ mất module Java Time, parameter names, Kotlin, naming strategy hoặc customizer mà framework đã đăng ký. Hãy ưu tiên tùy chỉnh builder/mapper hiện có theo cơ chế của phiên bản Spring Boot, hoặc đăng ký factory/mapper được quản lý thống nhất.

Ngoài parser, cấu hình giới hạn request body ở server/proxy. Một endpoint upload lớn có thể cần giới hạn khác endpoint tạo tài khoản; nếu cần ngân sách khác nhau, cân nhắc converter/mapper riêng được cấu hình trước cho endpoint đó thay vì thay đổi mapper dùng chung trong lúc request đang chạy.

## 15. Bật kiểm tra trailing token khi chỉ chấp nhận một document

Một body có thể chứa một JSON value hợp lệ rồi thêm một JSON value khác:

```text
{"id":"A"} {"id":"B"}
```

Nếu API chỉ chấp nhận một document, hãy bật:

```java
mapper.enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Feature này yêu cầu Databind kiểm tra token còn lại sau root value. Nó giúp từ chối dữ liệu thừa khi hợp đồng chỉ cho phép một JSON document.

Nếu giao thức thực sự cho phép nhiều record nối tiếp, hãy dùng framing rõ ràng như NDJSON hoặc length-prefix và xử lý từng record riêng. Đừng bật hoặc tắt feature này mà không xác định hợp đồng document.

## 16. Không dùng default typing rộng cho input không tin cậy

Polymorphic deserialization có thể làm Jackson tạo subtype theo type metadata trong JSON. Nếu ứng dụng bật default typing rộng hoặc cho phép type id dựa trên tên class mà không có allowlist chặt, input có thể yêu cầu tạo những kiểu Java ngoài dự kiến.

Với API nhận dữ liệu không tin cậy:

- Ưu tiên `JsonTypeInfo.Id.NAME` với danh sách subtype được đăng ký rõ ràng.
- Chỉ cho phép các subtype cần thiết cho hợp đồng.
- Tránh bật default typing toàn cục một cách tùy tiện.
- Không để client cung cấp tên class/package Java tùy ý làm type id.
- Validate dữ liệu sau khi tạo subtype và kiểm tra quyền nghiệp vụ riêng.

Đây là lớp bảo vệ bổ sung bên cạnh giới hạn tài nguyên. Một payload nhỏ vẫn có thể nguy hiểm nếu quá trình deserialize cho phép kiểu không an toàn.

## 17. Log và phản hồi khi từ chối payload

Khi từ chối input do duplicate field hoặc vượt giới hạn, log nên ghi thông tin đủ để chẩn đoán:

- Request/correlation id.
- Endpoint và content type.
- Loại constraint bị vượt, ví dụ nesting depth hoặc string length.
- Vị trí parser nếu có.
- Kích thước body thực nhận nếu hệ thống đo được.
- Client hoặc nguồn gửi theo chính sách log của hệ thống.

Không log toàn bộ raw JSON nếu payload có thông tin cá nhân, token, dữ liệu thanh toán hoặc bí mật. Một document rất lớn còn có thể làm log pipeline bị quá tải nếu ghi nguyên body vào log.

Phản hồi client nên dùng mã lỗi ổn định, ví dụ `REQUEST_TOO_LARGE`, `JSON_LIMIT_EXCEEDED` hoặc `DUPLICATE_PROPERTY`, theo hợp đồng API. Không trả stack trace hoặc thông tin cấu hình nội bộ của Jackson.

## 18. Kiểm thử giới hạn bảo vệ

Không chỉ test một JSON hợp lệ. Hãy tạo test xác nhận các giới hạn thực sự được áp dụng trên mapper/factory production:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Object lồng dưới giới hạn | Parse thành công |
| Object lồng vượt `maxNestingDepth` | Bị từ chối bởi parser constraint |
| String nằm trong giới hạn | Parse thành công |
| String vượt giới hạn | Bị từ chối |
| Number token quá dài | Bị từ chối |
| Cùng field xuất hiện hai lần trong object | Bị từ chối nếu strict duplicate detection bật |
| Cùng field ở hai object khác nhau | Được chấp nhận |
| Array vượt số phần tử endpoint cho phép | Bị từ chối ở tầng application/streaming |
| Body vượt maximum request size | Bị từ chối ở gateway/server trước hoặc trong khi đọc |
| Body nén nhỏ nhưng giải nén vượt giới hạn | Bị dừng ở giới hạn decompressed size |
| Request gửi chậm quá deadline | Kết nối/request bị hủy theo chính sách server |
| Có root token thừa | Bị từ chối nếu bật `FAIL_ON_TRAILING_TOKENS` |

Nên test cả mapper được tạo trong unit test lẫn mapper thực sự được framework dùng. Nếu hai mapper khác nhau, test đơn lẻ có thể tạo cảm giác đã bật giới hạn trong khi HTTP converter vẫn dùng cấu hình khác.

## 19. Checklist thiết kế ngân sách tài nguyên

Trước khi mở một endpoint nhận JSON, hãy xác định các ngân sách cụ thể:

1. **Maximum body bytes:** tổng số byte được phép nhận sau khi tính đến compression middleware.
2. **Maximum nesting depth:** số tầng object/array hợp lý với schema.
3. **Maximum string length:** giới hạn cho field văn bản và payload text.
4. **Maximum number length:** giới hạn cho token số.
5. **Maximum array elements:** số phần tử tối đa cho mỗi collection hoặc batch.
6. **Maximum object fields:** số property tối đa cho object mở/dynamic.
7. **Maximum processing time:** deadline cho parse, validation và xử lý nghiệp vụ.
8. **Maximum concurrency:** số request nặng được xử lý đồng thời.
9. **Maximum decompressed bytes:** giới hạn dữ liệu sau giải nén.
10. **Duplicate policy:** từ chối hay chấp nhận tên field trùng; nếu chấp nhận thì consumer nào quyết định giá trị.

Không có một bộ số mặc định phù hợp với mọi API. Một endpoint metadata có thể chỉ cần vài kilobyte và một array nhỏ; endpoint nhập dữ liệu hàng loạt có thể cần body lớn hơn nhưng phải xử lý streaming và giới hạn số record rõ ràng.

## 20. Ghi nhớ

- JSON hợp lệ vẫn có thể tiêu tốn quá nhiều CPU, heap, stack, băng thông hoặc thời gian kết nối.
- `StreamReadFeature.STRICT_DUPLICATE_DETECTION` giúp từ chối tên field trùng trong cùng object; `FAIL_ON_READING_DUP_TREE_KEY` là kiểm tra dành cho Tree Model.
- Duplicate detection không phát hiện hai alias khác tên cùng ánh xạ vào một property Java.
- `StreamReadConstraints` có thể giới hạn `maxNestingDepth`, `maxStringLength` và `maxNumberLength`; method và giới hạn cụ thể phụ thuộc phiên bản Jackson.
- Parser constraints không tự giới hạn tổng byte request, số phần tử array hoặc tổng số property trong mọi trường hợp.
- Đặt body-size limit ở gateway/server và đếm byte thực nhận; không chỉ tin `Content-Length`.
- Với collection lớn, dùng Streaming API để đếm và xử lý từng phần tử; `@Size` sau binding có thể đến quá muộn để bảo vệ heap.
- Giới hạn cả kích thước nén lẫn kích thước sau giải nén.
- Dùng timeout, rate limit, concurrency limit và backpressure để bảo vệ tầng mạng và downstream.
- Tránh tạo nhiều bản sao `JsonNode` hoặc chuyển cây lớn thành chuỗi rồi parse lại.
- Dùng allowlist subtype cho polymorphic deserialization; tránh default typing rộng với input không tin cậy.
- Test các payload vượt giới hạn bằng đúng `ObjectMapper`/`JsonFactory` mà ứng dụng production sử dụng.

Để từ chối JSON bất thường một cách hiệu quả, hãy kết hợp giới hạn parser, giới hạn body, giới hạn cấu trúc ở tầng ứng dụng và cơ chế timeout/backpressure. Jackson bảo vệ cú pháp và token trong phạm vi cấu hình của nó; server và ứng dụng phải bảo vệ tổng tài nguyên mà một request có thể tiêu thụ.
