# JSON fixture, charset và tính ổn định khi so sánh

Trong kiểm thử Spring Boot, một response JSON có thể **đúng về dữ liệu nhưng khác về biểu diễn văn bản**. Hai JSON object chứa cùng các cặp key–value có thể khác thứ tự key, khoảng trắng, indent hoặc cách escape ký tự Unicode. Ngược lại, hai chuỗi trông giống nhau trên màn hình có thể chứa các code point Unicode khác nhau, bị chuyển mã sai, thiếu field hoặc đổi thứ tự phần tử array. Nếu test so sánh sai cấp độ, nó sẽ **đỏ giả khi format thay đổi** hoặc **xanh giả khi hợp đồng dữ liệu bị phá**.

**JSON fixture** là dữ liệu JSON mẫu đã được kiểm soát, thường lưu ở `src/test/resources`, dùng làm input hoặc expected output của bài test. **Charset** xác định cách chuyển các byte thành ký tự; đối với JSON trao đổi giữa những hệ thống khác nhau, chuẩn RFC 8259 yêu cầu **UTF-8**. **Tính ổn định khi so sánh** đòi hỏi chọn đúng độ chặt: kiểm nội dung JSON ở mức cấu trúc khi contract mang ý nghĩa dữ liệu, nhưng kiểm raw bytes khi thực sự có giao thức ký số, hash, canonicalization hoặc byte-for-byte payload.

Bài học dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5, Jackson, MockMvc và JSONassert**. Các ví dụ phân biệt test controller slice với HTTP integration test có server thật. Chúng không dùng database hoặc API production. Nếu project dùng Spring Boot 4.x, một số package dependency và test API đã đổi; kiểm tài liệu đúng version trước khi copy code.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Thiết kế fixture JSON độc lập, có tên rõ, nhỏ, dễ review và đúng contract.
- Phân biệt **byte equality**, **string equality**, **JSON structural equality** và **schema/contract assertions**.
- Hiểu `application/json`, charset UTF-8, UTF-8 BOM, newline và escaping `\n`, `\"`, `\\`, `\uXXXX`.
- Tránh lỗi tiếng Việt bị biến thành chuỗi kiểu `CÃ  phÃª` hoặc ký tự thay thế `�`.
- So sánh `JsonNode` của Jackson, `content().json(...)` với `JsonCompareMode.STRICT/LENIENT` và JSONPath theo đúng ranh giới.
- Phân biệt object key order với array element order; kiểm dữ liệu `null`, missing, empty string và empty array.
- Kiểm số, timestamp, timezone, UUID và dữ liệu không xác định mà không tạo flaky tests.
- Viết bài `@WebMvcTest` đọc file fixture từ classpath ở dạng byte[], parse bằng Jackson và xác minh HTTP response.
- Viết HTTP integration test `@SpringBootTest(RANDOM_PORT)` để kiểm dữ liệu UTF-8 được gửi qua server thật.
- Chẩn đoán sự khác nhau giữa lỗi fixture, lỗi encoding, lỗi serializer và lỗi nghiệp vụ.

## 2. Một JSON có thể có nhiều biểu diễn tương đương

Hai chuỗi sau khác nhau về từng ký tự:

```json
{"id":7,"title":"Cà phê Việt","tags":["cà phê","sách"]}
```

```json
{
  "tags": ["cà phê", "sách"],
  "title": "Cà phê Việt",
  "id": 7
}
```

Nhưng xét theo cấu trúc JSON, hai **object** có cùng field và giá trị. Thứ tự các member trong JSON object **không được xem là thứ tự nghiệp vụ**. So sánh hai chuỗi bằng `assertEquals(json1, json2)` sẽ thất bại chỉ vì indent hoặc key order.

Ngược lại, hai mảng:

```json
["BOOK", "PEN"]
```

và:

```json
["PEN", "BOOK"]
```

khác thứ tự phần tử. **JSON array là một dãy có thứ tự.** Nếu API quy định “mới nhất trước”, thay thứ tự là bug cần phát hiện. Nếu API chỉ trả một tập hợp mà không quy định thứ tự, assertion nên cho phép đổi thứ tự, chẳng hạn JSONPath kết hợp Hamcrest `containsInAnyOrder`.

Đừng nhầm “JSON tương đương về mặt object” với “mọi khác biệt trong JSON có thể bỏ qua”. Những khác biệt sau vẫn có thể quan trọng:

- Field bị xóa, thêm trái phép hoặc đổi tên.
- Giá trị `true` thành `"true"` (boolean thành string).
- Số `7` thành chuỗi `"7"`.
- `null` thành field không tồn tại.
- `["A","B"]` đổi thành `["B","A"]` khi order là contract.
- Giá tiền `216000` thành `21600`.
- Chuỗi Unicode nhìn tương tự nhưng có normalization form khác mà consumer xử lý theo byte/string equality.

## 3. Bốn cấp độ so sánh: chọn dựa trên hợp đồng

| Cấp | So sánh điều gì? | Công cụ ví dụ | Dùng khi | Rủi ro |
|---|---|---|---|---|
| **Raw bytes** | Từng byte chính xác | `assertArrayEquals(byte[], byte[])` | Chữ ký số, hash, canonical JSON, wire protocol đặc biệt | Quá giòn nếu chỉ kiểm response JSON thường |
| **Raw text** | Từng ký tự sau decoding | `assertEquals(String, String)` | Dữ liệu là text có format được quy định | Vỡ vì whitespace, indent và key order |
| **JSON structure** | Object/array/value sau khi parse | `ObjectMapper.readTree`, `JsonNode.equals`, JSONassert | Phần lớn HTTP JSON contract | Cần rõ chiến lược đối với array và số |
| **Focused contract** | Một số field/type/absence quan trọng | `jsonPath`, Jackson predicates, schema validation | Response có metadata mở rộng hoặc API evolving | Quá lỏng nếu bỏ sót field nhạy cảm |

**Nguyên tắc mặc định:** Với API JSON thông thường, hãy bắt đầu từ **structured comparison** hoặc **focused contract assertions**, không bắt đầu bằng `content().string(expectedJson)`.

**Ngoại lệ thật sự:** Nếu server gửi JSON đã ký theo **byte sequence cụ thể**, một khoảng trắng thay đổi có thể làm signature sai; lúc đó byte equality/canonicalization là hợp đồng. Đừng tùy tiện chuẩn hóa lại payload rồi verify chữ ký trên dữ liệu đã bị thay đổi.

## 4. JSON fixture nên được lưu ở đâu?

Với dự án Java Gradle/Maven theo convention:

```text
src/
  main/
    java/
      com/example/fixturejson/
        FixtureJsonApplication.java
        ArticleView.java
        ArticleCatalog.java
        DemoArticleCatalog.java
        ArticleController.java
  test/
    java/
      com/example/fixturejson/
        ArticleControllerFixtureTest.java
        ArticleHttpUtf8IntegrationTest.java
        UnicodeNormalizationTest.java
    resources/
      fixtures/
        article-7.json
```

`src/test/resources/fixtures/article-7.json` sẽ nằm trên **test runtime classpath** trong cấu hình build thông thường. Test đọc bằng `ClassPathResource`; không giả định current working directory của CI hay IDE.

**Nên làm:**

- Dùng path cụ thể: `fixtures/article-7.json`.
- Lưu file dưới UTF-8, không thêm BOM.
- Chọn tên fixture phản ánh **scenario và version** khi thật sự có nhiều biến thể, ví dụ `article-paid-v1.json`, `article-with-null-note.json` hoặc `search-page-2.json`.
- Giữ fixture đủ nhỏ để review khác biệt; tách fixture quá lớn theo scenario.
- Kiểm fixture được parse trước khi dùng; JSON syntax sai phải fail sớm.
- Giữ expected data **độc lập với serializer code đang được kiểm**; không viết lại fixture từ response hiện tại rồi coi đó là ground truth.

**Không nên làm:**

- Hard-code đường dẫn tuyệt đối trên laptop.
- Ghi expected output vào thư mục source production.
- Copy credential, token, email thực hay dữ liệu riêng tư vào fixtures.
- Tạo expected bằng chính `ObjectMapper` đã serialize object thực trong đường test rồi assert hai kết quả giống nhau — phép kiểm sẽ dễ thành tautology.
- Dùng một JSON fixture “tổng hợp” hàng nghìn field cho mọi bài kiểm thử, khiến thay đổi nhỏ làm cả suite gãy.

## 5. UTF-8 là hợp đồng byte của JSON trao đổi

Theo **RFC 8259, mục 8.1**, JSON text trao đổi giữa các hệ thống không phải một hệ sinh thái khép kín phải dùng **UTF-8**. `application/json` không yêu cầu một tham số `charset` để client hiểu rằng body JSON được encode UTF-8. JSON generators trên network **không được thêm UTF-8 BOM** ở đầu JSON; parsers có thể chấp nhận BOM để tăng tương thích, nhưng không nên dựa vào điều đó.

Một response hợp lệ có thể có:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"title":"Cà phê Việt"}
```

Không nhất thiết phải có:

```http
Content-Type: application/json;charset=UTF-8
```

Vì vậy:

- **Kiểm media type** bằng `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` là hợp lý khi contract không cố định charset parameter.
- **Kiểm UTF-8 payload** bằng cách lấy `byte[]` và decode với một `CharsetDecoder` cấu hình **REPORT** cho malformed/unmappable data, hoặc parse trực tiếp bytes bằng Jackson.
- Không kiểm `getCharacterEncoding()` bằng chuỗi `"UTF-8"` như điều kiện bắt buộc cho mọi response `application/json` khi controller/converter không set explicit charset.
- Không nhầm `ISO-8859-1` fallback của **mock servlet response** khi gọi `getContentAsString()` với encoding thật mà Jackson đã dùng cho JSON bytes.

### 5.1. Một byte sequence khác nhau có thể mang cùng Unicode string

Chữ `à` trong UTF-8 có các byte khác với encoding một byte kiểu Latin-1. Nếu UTF-8 bytes bị decode bằng ISO-8859-1, người đọc có thể thấy `CÃ `. Đây là hiện tượng **mojibake**, không phải Jackson đã đổi nội dung nghiệp vụ.

Đường đi đúng:

```text
Java String (Unicode)
    |
    | Jackson JSON serialization (UTF-8 bytes)
    v
HTTP response byte[]
    |
    | Client reads as UTF-8, parses JSON escapes
    v
Java String (Unicode) mang cùng nội dung
```

Đường đi sai:

```text
UTF-8 byte[] --> decode giả định ISO-8859-1 --> CÃ  phÃª
```

Chính vì thế, khi phân tích lỗi tiếng Việt, hãy bắt đầu từ **byte[] và media type**, không kết luận quá sớm từ một chuỗi hiển thị trong log/test report.

## 6. UTF-8 BOM và fixture ngoài repository

UTF-8 BOM là ba byte `EF BB BF` ở đầu file. Nó có thể do editor/exporter thêm. RFC 8259 nói generator **không được** thêm BOM vào JSON gửi qua network. Với fixture local, cách an toàn là **lưu UTF-8 không BOM** để tooling nhất quán.

**Triệu chứng có thể gặp:** một parser xử lý BOM, parser khác từ chối; snapshot nhìn bình thường nhưng parser báo ký tự bất thường ở vị trí đầu. Đừng tự động loại BOM bằng cách xóa ba byte từ mọi request rồi giả định đã giải quyết vấn đề: bạn có thể che lỗi nguồn dữ liệu hoặc xử lý sai các tệp khác encoding.

Khi thực sự cần phát hiện BOM:

```java
// Snippet đặt trong test có biến byte[] bytes:
boolean utf8Bom = bytes.length >= 3
        && (bytes[0] & 0xFF) == 0xEF
        && (bytes[1] & 0xFF) == 0xBB
        && (bytes[2] & 0xFF) == 0xBF;

assertFalse(utf8Bom, "Fixture phải là UTF-8 không BOM");
```

Đây là snippet, không phải method/class độc lập; `assertFalse` là JUnit Jupiter. Phần test hoàn chỉnh cũng kiểm BOM. Nếu fixture được cung cấp bởi hệ thống khác và contract cho phép BOM, cần quyết định theo định dạng thực tế thay vì áp một quy tắc tùy tiện.

## 7. Escaping và Unicode: đọc giá trị sau khi parse

Cùng một chuỗi có thể xuất hiện ở dạng Unicode trực tiếp hoặc JSON escape.

```json
{"city":"Đà Nẵng"}
```

và:

```json
{"city":"\u0110\u00e0 N\u1eb5ng"}
```

khi parse JSON đều có thể cho string **`Đà Nẵng`**. Đó là lý do so sánh text thô dễ báo sai khác dù dữ liệu tương đương.

Các escape quan trọng:

| Trong JSON source | Sau khi JSON parser đọc | Khi nào dùng |
|---|---|---|
| `\"` | Dấu nháy kép `"` trong string | String có quote |
| `\\` | Một ký tự backslash | Windows path, regex literal |
| `\n` | Ký tự xuống dòng LF | Multi-line text |
| `\t` | Ký tự tab | Text có tab |
| `\r` | Carriage return | Một số line endings |
| `\u00e0` | Ký tự `à` | Unicode escape hợp lệ |
| `\uD83D\uDE00` | Emoji `😀` | Surrogate pair cho code point ngoài BMP |

**Chú ý số lớp escape:** một đoạn JSON là **file**; một string Java chứa JSON còn có **lớp escape của Java**; một biểu thức regex lại thêm lớp khác. Khi đặt fixture trong `src/test/resources/*.json`, không cần double-escape dấu quote chỉ để chiều ý Java compiler.

Ví dụ **file JSON fixture**, `summary` có dấu quote và xuống dòng:

```json
{
  "summary": "Dòng 1: \"đậm\"\nDòng 2 😀"
}
```

Sau khi parse, Java string có **dấu nháy và newline thực**:

```java
String expected = "Dòng 1: \"đậm\"\nDòng 2 😀";
```

Dòng Java trên có các escape cần thiết **mỗi escape đúng một backslash trong mã nguồn**; `\n` khi Java xử lý sẽ thành LF. **Không viết `\\"` cho một dấu quote bên trong Java string**: hai dấu backslash trước quote có thể khiến quote kết thúc chuỗi theo cách không mong đợi. Với JSON fixture file, mã `\"` và `\n` được JSON parser diễn giải.

## 8. Unicode normalization: nhìn giống chưa chắc bằng nhau

Unicode cho phép một số ký tự có nhiều cách mã hóa tương đương về mặt hiển thị:

- `"é"` có thể là một code point precomposed `U+00E9`.
- `"e"` + combining acute accent `U+0301` có thể trông giống `é`.
- Java `String.equals` thường so **chuỗi code units**, không tự thực hiện Unicode normalization.
- JSON parser không có nghĩa vụ tự normalize mọi string; serialization cũng không tự đảm bảo hai dạng giống nhau sẽ bằng nhau.

Ví dụ:

```java
import java.text.Normalizer;

String composed = "é";
String decomposed = "e\u0301";

boolean before = composed.equals(decomposed); // false
boolean after = Normalizer.normalize(
        composed, Normalizer.Form.NFC).equals(
        Normalizer.normalize(decomposed, Normalizer.Form.NFC)); // true
```

Đoạn trên là snippet trong một Java method; test hoàn chỉnh nằm ở phần 17.

**Quan trọng:** Không âm thầm normalize mọi dữ liệu để cho test xanh. Với username, file path, search term hoặc chữ ký điện tử, normalization có thể là **quy tắc nghiệp vụ** và phải được thống nhất hai phía. Với raw signature/HMAC, normalize trước khi verify có thể làm chữ ký sai và không được tự thay đổi payload.

## 9. Object key order và array order

Trong JSON object, key order **không phải thứ tự dữ liệu**. Jackson `JsonNode` thường so sánh object theo mapping field/value mà không phụ thuộc thứ tự key. Trong JSON array, `ArrayNode` giữ thứ tự phần tử và equality quan tâm thứ tự.

Ví dụ:

```json
{"id":7,"tags":["cà phê","sách"]}
```

so với:

```json
{"tags":["cà phê","sách"],"id":7}
```

là tương đương về mặt cấu trúc.

Nhưng:

```json
{"id":7,"tags":["sách","cà phê"]}
```

có array tags bị đổi thứ tự. Nếu danh sách tags **không quy định thứ tự**, test có thể lấy `$.tags` rồi assert Hamcrest `containsInAnyOrder("cà phê", "sách")`. Nếu API quy định thứ tự ưu tiên, dùng `contains("cà phê", "sách")` hoặc so JSON cấu trúc strict.

**Lưu ý:** `JsonNode.equals` có thể còn quan tâm loại node số cụ thể theo cách Jackson parse/đại diện; không thay thế một numeric comparator có tolerance/semantic riêng. Khi số thực hoặc ID lớn quan trọng, chọn quy tắc so sánh rõ, không giả định mọi biến thể biểu diễn số tương đương.

## 10. `null`, missing, empty: bốn hợp đồng khác nhau

Giả sử API trả:

```json
{
  "note": null,
  "nickname": "",
  "tags": [],
  "active": false
}
```

Hãy phân biệt:

| Biểu diễn | Ý nghĩa | Assertion bằng Jackson |
|---|---|---|
| `"note": null` | Field hiện diện, giá trị null | `root.has("note")` và `root.get("note").isNull()` |
| Không có `note` | Field vắng mặt | `!root.has("note")` |
| `"nickname": ""` | String rỗng | `root.required("nickname").asText().equals("")` |
| `"tags": []` | Array rỗng | `root.required("tags").isArray()` và `size()==0` |
| `"active": false` | Boolean false | `root.required("active").isBoolean()` và `!booleanValue()` |

Spring/Jackson có thể cấu hình `@JsonInclude(Include.NON_NULL)` hoặc global inclusion policy khiến các field null **bị bỏ đi**. Nếu API contract yêu cầu `note: null`, một thay đổi `NON_NULL` là thay đổi contract và test nên đỏ. Nếu contract cho phép field vắng mặt, đừng buộc nó phải luôn xuất hiện.

Trong MockMvc JSONPath:

- `hasJsonPath()` kiểm path hiện diện **kể cả null**.
- `exists()` kiểm có **giá trị non-null**.
- `doesNotExist()` chấp nhận null hoặc path không có giá trị non-null.
- `doesNotHaveJsonPath()` kiểm path **hoàn toàn không có**, kể cả null cũng không chấp nhận.

Với phần tử object, cặp `hasJsonPath()` + `doesNotExist()` phân biệt explicit null với missing trong một definite path. Jackson `JsonNode` giúp biểu diễn quy tắc này rõ hơn.

## 11. So sánh JSON bằng `JsonNode` và JSONAssert

### 11.1. Jackson tree equality

```java
JsonNode expected = mapper.readTree(fixtureBytes);
JsonNode actual = mapper.readTree(responseBytes);
assertEquals(expected, actual);
```

Đây là snippet, không phải Java class đầy đủ. Nó bỏ qua whitespace và object key order, đồng thời nhận biết array ordering, field values và absence/presence của node. Phù hợp khi fixture mô tả **toàn bộ response contract**.

### 11.2. JSONAssert strict vs lenient

Trong Spring Framework 6.2, `content().json(expectedJson, JsonCompareMode.STRICT)` và `LENIENT` dùng JSON comparison thay vì so string raw. Cơ chế được Spring tích hợp từ thư viện JSONassert.

| Chế độ | Extra fields ở object | Array order | Nên dùng khi |
|---|---|---|---|
| `STRICT` | Không chấp nhận | Bắt buộc | Fixed response schema, cần ngăn lộ field mới |
| `LENIENT` | Có thể chấp nhận | Không bắt buộc | API extensible, chỉ kiểm vài trường quan trọng |

**STRICT không đồng nghĩa byte equality.** Indent và object key order vẫn không phải trọng tâm. **LENIENT không đồng nghĩa mọi dữ liệu đều được phép:** những field/value được nêu trong expected vẫn phải phù hợp theo comparator.

Một test strict với expected có `note: null` giúp phát hiện nếu serializer bỗng bỏ field hoặc gửi chuỗi rỗng. Với API cho phép mở rộng metadata, có thể dùng lenient cộng assertion vắng mặt của những field nhạy cảm.

**Điểm có thể gây nhầm:** Một số phương thức JSONAssert so sánh array bằng thuật toán đặc biệt theo mode và không hỗ trợ mọi kiểu biểu diễn của unordered arrays of objects một cách kỳ diệu. Với collection có ID, nên so key/đối tượng theo contract hoặc dùng mapping ID → object trước khi assert. Không coi LENIENT là thuốc chữa mọi khác biệt order.

### 11.3. JSONPath cho một hợp đồng tập trung

```java
mvc.perform(get("/api/articles/{id}", 7L))
        .andExpectAll(
                status().isOk(),
                jsonPath("$.id").value(7),
                jsonPath("$.title").value("Cà phê Việt ☕"),
                jsonPath("$.tags").isArray(),
                jsonPath("$.tags[0]").value("cà phê"));
```

Snippet dùng trong `@Test` có `MockMvc mvc`, imports và collaborator fixture đã sẵn. Khi response có nhiều metadata cho phép thêm, JSONPath có thể giúp test **ít giòn** hơn full strict JSON. Nhưng JSONPath đơn lẻ không phát hiện mọi extra field; thêm assertion cho field nhạy cảm hoặc schema test khi cần.

## 12. Chiến lược fixture: input, output và tình huống biên

Không có một file fixture duy nhất đúng cho mọi phép kiểm.

**Input fixture** thường dùng để gửi request phức tạp:

- Ví dụ `order-create-valid.json`, `order-create-missing-name.json` hoặc `order-create-unknown-currency.json`.
- Input phải phản ánh **request schema** mà client thật gửi, không sao chép entity JPA của server.
- Nếu test gửi byte[] từ fixture, đó là cơ hội kiểm charset, JSON parser và validation qua HTTP boundary.

**Expected output fixture** mô tả response công khai:

- Chỉ chứa field được phép trả và giá trị đã review.
- Không chứa token, timestamp động hoặc random ID nếu chúng không được cố định.
- Có thể có phiên bản theo API, ví dụ `article-response-v1.json`.
- Khi contract cho phép mở rộng field, dùng partial assertions thay vì ép strict full response.

**Negative fixture** cố ý sai:

- JSON malformed, unsupported media type, field sai kiểu, ký tự Unicode đặc biệt.
- Đặt tên thể hiện lỗi dự kiến, ví dụ `invalid-json-trailing-comma.json`.
- Không chia sẻ một file input đã sai format cho cả chục nhánh lỗi vì dễ nhầm lý do fail.

**Fixture chống hồi quy (regression)** có thể tái hiện bug thực tế đã được sanitize: quote escape sai, newline bị mất, emoji thành `?`, null bị bỏ, số tiền sai hoặc field nhạy cảm xuất hiện. Cần gắn scenario rõ để người sau hiểu tại sao fixture tồn tại.

## 13. Khi nào không nên tạo fixture JSON riêng?

Một test có expected ngắn:

```java
assertEquals("PAID", result.status());
assertEquals(216_000L, result.totalVnd());
```

không cần thiết phải tạo một file `expected-42.json` nếu mục tiêu chỉ là domain object. Thậm chí với JSON:

```java
mvc.perform(get("/api/health"))
        .andExpect(jsonPath("$.status").value("UP"));
```

một JSONPath là đủ nếu health contract không có hàng chục field.

Dùng fixture file khi nó thực sự giúp **đọc, tái sử dụng, review hoặc test encoding/schema**. Dùng builder/factory cho Java object khi fixture chủ yếu là dữ liệu đầu vào có nhiều biến thể. Đừng dùng file JSON làm cách né việc viết assertion về business outcome.

## 14. Ví dụ runnable: controller, fixture UTF-8 và test hai cấp

Ta tạo một API bài viết:

- `GET /api/articles/7` trả ArticleView có dấu tiếng Việt, emoji, quote, newline, array, timestamp cố định và `note: null`.
- `GET /api/articles/999` trả 404 với body rỗng.
- `POST /api/articles/echo` chỉ echo lại ArticleView đã deserialize, để kiểm request UTF-8 và JSON converter (đây là endpoint demo, **không phải mẫu production** để mở public).
- `ArticleCatalog` là một port; test MVC slice mock port, còn full HTTP integration test chạy adapter in-memory thật.

### 14.1. Cấu trúc file

```text
src/main/java/com/example/fixturejson/
  FixtureJsonApplication.java
  ArticleView.java
  ArticleCatalog.java
  DemoArticleCatalog.java
  ArticleController.java
src/test/java/com/example/fixturejson/
  ArticleControllerFixtureTest.java
  ArticleHttpUtf8IntegrationTest.java
  UnicodeNormalizationTest.java
src/test/resources/fixtures/
  article-7.json
```

Toàn bộ source dùng `package com.example.fixturejson;`. Fixture có tên `article-7.json` và phải được lưu ở UTF-8 không BOM. Các code block từ mục 14 đến 17 mô tả **đầy đủ các file**, có thể dùng trong một Spring Boot 3.5 project với đúng dependency ở mục 25. Các snippet tách rời ở phần khác chỉ để minh họa.

### 14.2. Application root

**`src/main/java/com/example/fixturejson/FixtureJsonApplication.java`**

```java
package com.example.fixturejson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FixtureJsonApplication {

    public static void main(String[] args) {
        SpringApplication.run(FixtureJsonApplication.class, args);
    }
}
```

### 14.3. Immutable response DTO

**`src/main/java/com/example/fixturejson/ArticleView.java`**

```java
package com.example.fixturejson;

import java.time.Instant;
import java.util.List;

public record ArticleView(
        long id,
        String title,
        String city,
        String summary,
        List<String> tags,
        Instant publishedAt,
        String note) {
}
```

Lý do chọn `record`: DTO có các field rõ ràng, không phụ thuộc JPA lazy loading, và Jackson trong Spring Boot 3.5 có thể serialize/deserialize Java records. `Instant` được biểu diễn thành chuỗi ISO-8601 với cấu hình Boot/Jackson mặc định thường dùng; test cố định giá trị để tránh phụ thuộc thời gian chạy.

### 14.4. Port cho controller

**`src/main/java/com/example/fixturejson/ArticleCatalog.java`**

```java
package com.example.fixturejson;

import java.util.Optional;

public interface ArticleCatalog {
    Optional<ArticleView> findById(long id);
}
```

### 14.5. Adapter in-memory để full application chạy được

**`src/main/java/com/example/fixturejson/DemoArticleCatalog.java`**

```java
package com.example.fixturejson;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DemoArticleCatalog implements ArticleCatalog {

    @Override
    public Optional<ArticleView> findById(long id) {
        if (id != 7L) {
            return Optional.empty();
        }

        return Optional.of(new ArticleView(
                7L,
                "Cà phê Việt ☕",
                "Đà Nẵng",
                "Dòng 1: \"đậm\"\nDòng 2 😀",
                List.of("cà phê", "sách"),
                Instant.parse("2026-11-08T10:15:30Z"),
                null));
    }
}
```

**Rà soát dấu escape trong Java:** literal `"Dòng 1: \"đậm\"\nDòng 2 😀"` chứa một `\"` cho mỗi dấu nháy kép bên trong và `\n` cho xuống dòng. Khi Java chạy, giá trị `summary` có dấu nháy thật, newline thật và emoji. Đây là **cú pháp nguồn Java đúng**, không phải văn bản JSON đã escape hai lần.

Adapter có `@Repository` để Spring full context đăng ký; nó **không truy cập database**. Vì thế full HTTP test chạy implementation thật, nhưng không tuyên bố đã kiểm SQL/JPA. Trong `@WebMvcTest`, collaborator này nằm ngoài web slice và sẽ được thay bằng Mockito mock ở test boundary.

### 14.6. Controller HTTP thật

**`src/main/java/com/example/fixturejson/ArticleController.java`**

```java
package com.example.fixturejson;

import java.util.Optional;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/articles")
public class ArticleController {
    private final ArticleCatalog catalog;

    public ArticleController(ArticleCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ArticleView> get(@PathVariable long id) {
        Optional<ArticleView> view = catalog.findById(id);
        return view.map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ArticleView echo(@RequestBody ArticleView view) {
        return view;
    }
}
```

Controller không can thiệp vào charset bằng cách tự gọi `String.getBytes()`; Spring MVC cùng Jackson HTTP message converter nhận nhiệm vụ JSON serialization. Annotation `produces = application/json` và `consumes = application/json` định nghĩa media-type contract, không buộc phải thêm một tham số charset trong response header.

Endpoint `echo` chỉ dùng để minh họa round-trip input/output; ứng dụng sản phẩm phải có validation/authorization và không nên phản chiếu dữ liệu không tin cậy ngoài phạm vi cần thiết.

## 15. File fixture JSON: dữ liệu độc lập cần review

**`src/test/resources/fixtures/article-7.json`**

```json
{
  "id": 7,
  "title": "Cà phê Việt ☕",
  "city": "Đà Nẵng",
  "summary": "Dòng 1: \"đậm\"\nDòng 2 😀",
  "tags": ["cà phê", "sách"],
  "publishedAt": "2026-11-08T10:15:30Z",
  "note": null
}
```

File này phải **được lưu đúng dưới dạng UTF-8 không BOM**. Mặc dù code fence hiển thị `\n`, JSON source chứa **hai ký tự ASCII backslash và chữ n** trong string; JSON parser sẽ đọc chúng thành **ký tự xuống dòng**. Đừng chèn newline thật vào giữa JSON string chưa escape: JSON không cho phép raw control character U+000A bên trong string.

**Đây là expected độc lập:** file do con người review; không được tạo trong test bằng cách gọi `mapper.writeValueAsString(articleFromProduction)` rồi coi nó là ground truth của serializer đang kiểm.

### 15.1. Nếu file fixture có field lạ

Một test so sánh strict `JsonNode` sẽ phát hiện extra field nếu actual có nhưng fixture không, và ngược lại. Đó là lợi ích khi schema phải cố định. Nếu API cho phép mở rộng metadata, dùng fixture chỉ chứa một tập field quan trọng cùng JSONAssert LENIENT hoặc JSONPath; đừng nới lỏng một contract bảo mật đáng lẽ phải kiểm nghiêm.

## 16. MVC slice test đầy đủ: fixture, charset và so sánh ổn định

**`src/test/java/com/example/fixturejson/ArticleControllerFixtureTest.java`**

```java
package com.example.fixturejson;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.contains;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ArticleController.class)
class ArticleControllerFixtureTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    ArticleCatalog catalog;

    private static ArticleView sample() {
        return new ArticleView(
                7L,
                "Cà phê Việt ☕",
                "Đà Nẵng",
                "Dòng 1: \"đậm\"\nDòng 2 😀",
                List.of("cà phê", "sách"),
                Instant.parse("2026-11-08T10:15:30Z"),
                null);
    }

    private static byte[] fixtureBytes() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("fixtures/article-7.json");
        try (InputStream input = resource.getInputStream()) {
            return input.readAllBytes();
        }
    }

    private static String fixtureText() throws IOException {
        return new String(fixtureBytes(), StandardCharsets.UTF_8);
    }

    private void stubArticle() {
        when(catalog.findById(7L))
                .thenReturn(Optional.of(sample()));
    }

    @Test
    void comparesResponseAsJsonTreeNotRawText()
            throws Exception {
        stubArticle();

        MvcResult result = mvc.perform(get("/api/articles/7")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpectAll(
                        status().isOk(),
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON),
                        jsonPath("$.title").value("Cà phê Việt ☕"),
                        jsonPath("$.tags",
                                contains("cà phê", "sách")))
                .andReturn();

        JsonNode expected = mapper.readTree(fixtureBytes());
        JsonNode actual = mapper.readTree(
                result.getResponse().getContentAsByteArray());

        assertEquals(expected, actual);
        assertEquals("Đà Nẵng", actual.required("city").asText());
        assertTrue(actual.required("id").isIntegralNumber());
        assertTrue(actual.has("note"));
        assertTrue(actual.get("note").isNull());
        assertFalse(actual.has("internalToken"));
    }

    @Test
    void strictStructuralComparisonCatchesUnexpectedFields()
            throws Exception {
        stubArticle();

        mvc.perform(get("/api/articles/7"))
                .andExpect(status().isOk())
                .andExpect(content().json(
                        fixtureText(), JsonCompareMode.STRICT));
    }

    @Test
    void lenientComparisonAllowsAdditionalPublicFields()
            throws Exception {
        stubArticle();

        mvc.perform(get("/api/articles/7"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "id": 7,
                          "title": "Cà phê Việt ☕"
                        }
                        """, JsonCompareMode.LENIENT))
                .andExpect(jsonPath("$.internalToken").doesNotHaveJsonPath());
    }

    @Test
    void decodesActualResponseBytesAsValidUtf8()
            throws Exception {
        stubArticle();

        MvcResult result = mvc.perform(get("/api/articles/7"))
                .andExpect(status().isOk())
                .andReturn();

        byte[] payload = result.getResponse().getContentAsByteArray();

        String decoded = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(payload))
                .toString();

        JsonNode actual = mapper.readTree(decoded);
        assertEquals("Cà phê Việt ☕",
                actual.required("title").asText());
        assertEquals("Dòng 1: \"đậm\"\nDòng 2 😀",
                actual.required("summary").asText());
        assertEquals("Đà Nẵng", actual.required("city").asText());
    }

    @Test
    void acceptsUtf8FixtureRequestAndEchoesSemanticJson()
            throws Exception {
        byte[] requestBytes = fixtureBytes();

        MvcResult result = mvc.perform(post("/api/articles/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(requestBytes))
                .andExpectAll(
                        status().isOk(),
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON))
                .andReturn();

        JsonNode expected = mapper.readTree(requestBytes);
        JsonNode actual = mapper.readTree(
                result.getResponse().getContentAsByteArray());

        assertEquals(expected, actual);
    }

    @Test
    void rejectsMissingArticleWith404AndNoJsonBody()
            throws Exception {
        when(catalog.findById(999L))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/articles/999"))
                .andExpectAll(
                        status().isNotFound(),
                        content().string(""));
    }

    @Test
    void fixtureHasNoBomAndIsParseableJson()
            throws Exception {
        byte[] bytes = fixtureBytes();

        assertTrue(bytes.length > 3);
        boolean bom = (bytes[0] & 0xFF) == 0xEF
                && (bytes[1] & 0xFF) == 0xBB
                && (bytes[2] & 0xFF) == 0xBF;
        assertFalse(bom);

        JsonNode root = mapper.readTree(bytes);
        assertNotNull(root);
        assertEquals("Cà phê Việt ☕",
                root.required("title").asText());
    }

    @Test
    void objectKeyOrderAndWhitespaceDoNotChangeJsonValue()
            throws Exception {
        String compact = """
                {"id":7,"tags":["cà phê","sách"]}
                """;
        String prettyReordered = """
                {
                  "tags": ["cà phê", "sách"],
                  "id": 7
                }
                """;

        assertFalse(compact.equals(prettyReordered));
        assertEquals(mapper.readTree(compact),
                mapper.readTree(prettyReordered));
    }
}
```

### 16.1. Vì sao dùng `getContentAsByteArray()`?

`MockHttpServletResponse.getContentAsString()` dùng charset mà response khai báo; nếu chưa khai báo, mock response có **fallback encoding** (Spring Test đã dùng ISO-8859-1 làm default ở nhiều version), khiến JSON bytes UTF-8 có thể hiển thị sai tiếng Việt. Đọc byte[] rồi parse bằng Jackson **tránh lớp decode string không cần thiết**.

Nếu thật sự cần string để debug:

```java
// Snippet trong test có MvcResult result:
String decodedWithFallback = result.getResponse()
        .getContentAsString(StandardCharsets.UTF_8);
```

Overload `getContentAsString(Charset fallbackCharset)` dùng fallback được chỉ định **khi response không khai báo charset**. Nếu muốn phát hiện invalid UTF-8 thay vì replacement characters, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` như code hoàn chỉnh.

**Không kiểm response raw có chứa emoji dưới dạng ký tự trực tiếp** như một yêu cầu mặc định: serializer có thể chọn JSON escape mà parser vẫn tạo string Unicode tương đương. Bài test nên kiểm **giá trị sau parse** và **byte sequence UTF-8 hợp lệ**; chỉ kiểm cách escape cụ thể khi đó là contract.

### 16.2. Vì sao test strict và lenient cùng tồn tại?

Chúng minh họa hai dạng hợp đồng:

- `strictStructuralComparisonCatchesUnexpectedFields` bảo vệ **đúng toàn bộ JSON fixture**, kể cả `note:null` và danh sách tags có thứ tự.
- `lenientComparisonAllowsAdditionalPublicFields` chỉ quan tâm `id` và `title` nhưng vẫn ngăn field `internalToken`. Nó phù hợp khi endpoint cho phép thêm metadata.
- Trong dự án thật, **đừng viết cả hai test cho mọi endpoint theo thói quen**. Chọn một mức phù hợp hợp đồng, rồi bổ sung focused assertions cho những rủi ro đặc biệt.

### 16.3. Vì sao test echo không đủ chứng minh nghiệp vụ?

`POST /echo` kiểm bytes → Jackson deserialize → DTO → Jackson serialize. Nó có thể xanh dù repository production, policy kiểm duyệt hoặc quyền truy cập sai, vì không có logic ấy trên đường đi. Cần test service/integration riêng cho hợp đồng nghiệp vụ.

### 16.4. Số test và độ độc lập

`ArticleControllerFixtureTest` có **8** test methods. Mockito stubbing xảy ra độc lập cho từng method; dữ liệu fixture được đọc từ classpath nhưng không bị sửa. Các test không cần sắp xếp thứ tự chạy. Nếu thêm fake mutable hoặc database, cần có cleanup/fixture isolation riêng.

## 17. Unicode normalization test thuần Java/JUnit

Để kiểm riêng một vấn đề charset/Unicode mà không cần Spring:

**`src/test/java/com/example/fixturejson/UnicodeNormalizationTest.java`**

```java
package com.example.fixturejson;

import java.text.Normalizer;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class UnicodeNormalizationTest {

    @Test
    void visuallyEqualStringsCanHaveDifferentCodePoints() {
        String composed = "é";
        String decomposed = "e\u0301";

        assertNotEquals(composed, decomposed);

        assertEquals(
                Normalizer.normalize(composed, Normalizer.Form.NFC),
                Normalizer.normalize(decomposed, Normalizer.Form.NFC));
    }
}
```

Test này **không sửa dữ liệu** và không tuyên bố mọi ứng dụng phải normalize về NFC. Nó minh họa rằng **String equality ≠ visual equality**. Nếu contract quy định normalization, nên đặt rule đó tại boundary/service thật và kiểm bằng những input ngoài BMP, combining marks, dấu tiếng Việt, search/case folding phù hợp.

## 18. HTTP integration test: kiểm response bytes qua server thật

`MockMvc` đi qua Spring MVC nhưng **không mở TCP socket**. Khi cần chắc chắn Boot context đầy đủ cùng HTTP server encode response đúng, dùng một test `RANDOM_PORT` có client nhận byte[].

**`src/test/java/com/example/fixturejson/ArticleHttpUtf8IntegrationTest.java`**

```java
package com.example.fixturejson;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = FixtureJsonApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ArticleHttpUtf8IntegrationTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ObjectMapper mapper;

    @Test
    void realHttpResponseMatchesReviewedUtf8Fixture()
            throws Exception {
        ResponseEntity<byte[]> response = rest.getForEntity(
                "/api/articles/7", byte[].class);

        assertEquals(200, response.getStatusCode().value());

        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(MediaType.APPLICATION_JSON
                .isCompatibleWith(contentType));

        byte[] actualBytes = response.getBody();
        assertNotNull(actualBytes);

        JsonNode actual = mapper.readTree(actualBytes);
        JsonNode expected;
        try (InputStream input = new ClassPathResource(
                "fixtures/article-7.json").getInputStream()) {
            expected = mapper.readTree(input);
        }

        assertEquals(expected, actual);
        assertEquals("Đà Nẵng",
                actual.required("city").asText());
    }
}
```

**Ý nghĩa khác MVC slice:**

- Embedded HTTP server thật được khởi động trên random port của Boot.
- Spring full context tạo `DemoArticleCatalog` thật, không có Mockito mock cho port.
- Response được nhận về dưới dạng **raw HTTP body bytes**, không qua `TestRestTemplate` chuyển sang String trước khi Jackson parse.
- Fixture được đọc độc lập bằng Jackson và so với response tree.
- Bài test chứng minh đường Spring Boot → controller → adapter demo → Jackson → HTTP server/client hoạt động trong phạm vi mô hình này.

**Nó không chứng minh SQL, external HTTP hoặc authentication production**, vì ví dụ không dùng chúng. Với ứng dụng có database thật, `RANDOM_PORT` test cần database riêng và cleanup; `@Transactional` trên JUnit method không tự rollback writes do server request thực hiện ở transaction/thread riêng.

## 19. Tính ổn định của số và JSON fixture

Dữ liệu numeric là nơi phát sinh false positives/negatives:

```json
{
  "quantity": 2,
  "priceVnd": 216000,
  "rate": 0.075,
  "bigIdentifier": "9007199254740993"
}
```

- `quantity` là số nguyên, không phải string `"2"`.
- `priceVnd` dùng số nguyên VND; trong hệ thống thật, cần xác định currency, minor units và rounding policy.
- `rate` là số thập phân; nếu dùng `double` để tính tiền hoặc so số thực bằng equality tuyệt đối, lỗi rounding có thể xuất hiện.
- `bigIdentifier` dùng string để không mất precision khi đi qua client JavaScript có giới hạn safe integers; đây là một **quyết định API contract**, không phải mọi ID đều phải string.
- Khi Java dùng `BigDecimal`, phải xác định cách serialize, scale có được bảo toàn không và so sánh theo numeric value hay textual representation.

**Ví dụ:** `BigDecimal("1.0").equals(BigDecimal("1.00"))` là false vì khác scale, dù `compareTo` trả 0. Jackson có thể chọn nhiều numeric node type; `JsonNode` tree equality không thay cho toàn bộ money-domain comparator. Nếu precision quan trọng, assert bằng `BigDecimal`/money type theo quy tắc rõ thay vì chỉ so text hay double.

**Không sinh fixture bằng những phép tính không xác định trong test rồi assert với output cũng dùng cùng phép tính.** Giá trị expected cần độc lập đủ để bắt lỗi domain.

## 20. Timestamp, timezone và dữ liệu động

Một fixture chứa timestamp hard-coded:

```json
{
  "publishedAt": "2026-11-08T10:15:30Z"
}
```

ổn định vì ứng dụng ví dụ dùng `Instant.parse("2026-11-08T10:15:30Z")`. Nếu service production dùng `Instant.now()` thì expected sẽ thay mỗi lần chạy.

**Các rủi ro:**

- System default timezone của laptop và CI khác nhau.
- `LocalDateTime` không có offset, nhưng client hiểu nhầm là UTC.
- Serializer có thể emit epoch milliseconds, ISO text hoặc fractional seconds khác nhau tùy config.
- Timestamp phát sinh bởi DB có precision khác JVM.
- Test đọc thời gian hiện tại trước/sau HTTP request có race hoặc độ lệch millisecond.

**Giải pháp:** inject `Clock` và dùng `Clock.fixed(...)` trong test, hoặc cho domain dùng timestamp fixture xác định. Nếu thời gian là ngữ nghĩa test, assert điều kiện trong khoảng hợp lý hoặc cách xử lý đúng ở boundary, không hard-code `Instant.now()`.

UUID, thứ tự HashMap, random number và auto-increment ID cũng vậy: đặt dữ liệu cố định, dùng seeded generator khi thích hợp hoặc assert dựa trên invariant/schema thay vì snapshot chứa giá trị không ổn định.

## 21. “Expected” phải độc lập khỏi code tạo “actual”

Một anti-pattern:

```java
// PHẢN VÍ DỤ: cùng serializer tạo expected và actual,
// nên lỗi cấu hình serializer có thể bị lặp cả hai phía.
String expected = mapper.writeValueAsString(serviceResult);
String actual = mapper.writeValueAsString(serviceResult);
assertEquals(expected, actual);
```

Bài test này hầu như chỉ kiểm một biểu thức tự so với chính nó. Một anti-pattern khác:

```java
// PHẢN VÍ DỤ: snapshot được update từ response hiện tại
// mà không review thay đổi schema/data.
Files.writeString(snapshotPath, responseBody);
assertEquals(Files.readString(snapshotPath), responseBody);
```

Nó sẽ luôn pass dù response có bug. **Fixture nên do con người review hoặc được tạo bằng một nguồn độc lập và có quy trình approve nghiêm túc**. Có thể dùng tool để tạo bản khởi đầu, nhưng expected phải được kiểm trước khi trở thành baseline.

Trong code runnable, input object được stub trong `@WebMvcTest`, còn fixture JSON ở `src/test/resources` là văn bản riêng. Điều này giúp kiểm serializer và response shape. Tuy nhiên, slice test vẫn chưa kiểm logic `DemoArticleCatalog` thật; đó là lý do có `ArticleHttpUtf8IntegrationTest`.

## 22. Thay đổi serializer có thể phá hợp đồng dù DTO giữ nguyên

Một số thay đổi serialization cần được bảo vệ bằng test:

| Thay đổi | Tác động có thể xảy ra | Test nào sẽ bắt? |
|---|---|---|
| `@JsonProperty("published_at")` | Rename field | Strict fixture, JSONPath |
| `@JsonInclude(NON_NULL)` | Bỏ `note:null` | Strict fixture, `JsonNode.has("note")` |
| Custom naming strategy | `totalVnd` thành `total_vnd` | Contract JSON tests |
| Timezone/date module | ISO timestamp thành số hoặc format khác | Fixture/field assertion |
| ObjectMapper module khác | Enum/record/Java Time value đổi | Serialization/HTTP test |
| Security-sensitive DTO field được thêm | Vô tình expose `internalToken` | Strict fixture hoặc absence assertions |
| Collection order thay đổi | Mảng items khác thứ tự | Strict array contract hoặc sorted assertions |
| Encoder chuyển lỗi UTF-8 | Ký tự tiếng Việt/emoji hỏng | Raw byte UTF-8 decoder + parsed values |
| Auto-configuration khác giữa slice/full context | Mock slice pass, full app sai output | Full HTTP integration test |

**Không phải thay đổi nào cũng là bug.** API có thể cho phép field mở rộng, hoặc JSON serializer có thể thay whitespace vô hại. Điều cần cố định là **hợp đồng công khai**, không phải toàn bộ implementation detail.

## 23. Những lỗi dễ làm test JSON flaky

### 23.1. Dựa vào thứ tự HashMap hoặc DB

Nếu JSON array được xây từ một tập không có thứ tự xác định, test đòi index cố định có thể đỏ lúc này, xanh lúc khác. Giải pháp là **định nghĩa sort trong production** nếu order là contract, hoặc dùng order-insensitive assertion nếu không.

### 23.2. Dựa vào ngôn ngữ/locale máy chạy

Ngày tháng, decimal separator và message lỗi có thể phụ thuộc Locale. Nếu API contract quy định tiếng Việt hoặc tiếng Anh, test phải set locale/`Accept-Language` hoặc dùng formatter cố định, tránh phụ thuộc locale hệ điều hành.

### 23.3. Dựa vào timezone mặc định

`OffsetDateTime`, `ZonedDateTime` và `Instant` có semantics khác nhau. Nếu DTO chỉ cần timestamp UTC, dùng `Instant` hoặc quy tắc format có zone rõ. Không dùng kết quả `LocalDateTime.now()` để so chuỗi với `Z`.

### 23.4. Trộn charset của file và response

Fixture UTF-8 nhưng helper đọc bằng `Files.readString(path)` có charset behavior phụ thuộc API/version, hoặc client ép decode ISO-8859-1. Chọn `Files.readString(path, UTF_8)` khi dùng filesystem và `ClassPathResource`/byte[] trong test classpath; parse JSON trực tiếp bytes khi có thể.

### 23.5. Thay fixture trong test run

Một test cập nhật fixture/snapshot đang dùng làm expected khiến suite không còn độc lập. Expected là **read-only test data**; không rewrite hoặc auto-accept trong CI.

### 23.6. JSON snapshot quá lớn

Một file 5.000 dòng chứa timestamp, environment URL, random ID, exception stack trace sẽ gây false alarms liên tục. Hãy tách một fixture nhỏ theo scenario hoặc so các field đúng contract. Nếu cần full snapshot, phải chuẩn hóa dynamic fields **theo quy tắc rõ ràng và được review**.

### 23.7. Dữ liệu Unicode nhìn giống nhưng không cùng code points

Một fixture copy từ tài liệu có combining marks, trong khi code tạo precomposed characters. So `String.equals` có thể fail dù mắt thường không thấy. Nếu contract yêu cầu normalized form, xử lý tại ứng dụng và assert; nếu contract không quy định, cần xác định chính sách encoding/normalization thay vì thay test tùy tiện.

## 24. Debug theo từng tầng

Khi test so fixture thất bại, đừng ngay lập tức cập nhật fixture cho khớp actual. Làm theo thứ tự:

1. **Status/Content-Type:** response có đúng `200` và `application/json` không? Nếu 404/500/HTML error, đây chưa phải lỗi charset.
2. **Actual byte length + UTF-8 decode:** lấy `byte[]`; thử strict UTF-8 decoder; xem có BOM hay invalid sequence.
3. **Parse JSON:** parse cả fixture và response bằng cùng parser để xác định có phải JSON hợp lệ không.
4. **Kiểm shape:** object/array root, missing/null và kiểu field có thay đổi không?
5. **Kiểm values:** giá trị tiếng Việt, số, boolean, timestamp có thực sự khác không?
6. **Kiểm order:** khác object key order, array order hay formatting? Chỉ array order có thể là business contract.
7. **Kiểm expected:** fixture độc lập có còn đúng theo tài liệu API không?
8. **Kiểm source of nondeterminism:** system clock, random, DB sort, locale, env, profile, timezone, data reuse.
9. **Kiểm độ chặt của matcher:** strict JSON, lenient JSON, JSONPath, byte equality hay raw string?
10. **Kiểm ranh giới test:** service thật có chạy không? Fixture có bị tạo từ actual không? Slice/full context khác nhau không?

### 24.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `CÃ  phÃª` xuất hiện | UTF-8 bytes bị decode như Latin-1 | Lấy byte[], decode UTF-8 đúng |
| `�` xuất hiện | Invalid byte sequence hoặc decoder replacement | Dùng `CharsetDecoder.REPORT` |
| Jackson báo unexpected character ở đầu | BOM/encoding sai/file có ký tự lạ | Kiểm bytes đầu, lưu UTF-8 không BOM |
| JSON string expected khác actual vì newline | `\n` escape khác raw line ending hoặc double-escape | Parse cả hai thành `JsonNode`, xem code points |
| `note` biến mất | `NON_NULL` hoặc naming/filter | Kiểm `has`, strict fixture, serializer config |
| Test fail sau nâng Jackson | Config module/number/time format đổi | Xem tree diff + contract |
| Test fail do thứ tự field | Đang so raw text | Dùng structural JSON comparison |
| Test fail do thứ tự tags | Array order khác | Xác định order có là contract không |
| Fixture có giá đúng nhưng test xanh khi service sai | Collaborator nghiệp vụ bị mock | Thêm test service thật hoặc HTTP integration |
| Timestamp lúc pass lúc fail | Dùng clock thật | Inject fixed clock/fixture ổn định |
| Local pass, CI fail | Locale/timezone/charset/config khác | Cố định config và đọc bytes trước |
| JSONassert LENIENT pass dù field nội bộ lộ | Cho phép extra fields | Dùng STRICT hoặc absence assertion |
| Mọi snapshot pass sau update | Expected tự sinh từ actual | Bắt buộc review expected độc lập |
| JSON parse bị lỗi khi 204/404 body rỗng | Test áp matcher JSON trên empty body | Assert status + empty content |

## 25. Gradle, chạy test và kết quả kỳ vọng

Trong project Gradle đã có Spring Boot plugin/BOM, repositories và Java toolchain phù hợp, dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung**, không phải `build.gradle` độc lập vì thiếu `plugins`, `repositories` và quản lý version. Spring Boot 3.5 starter-web mang Jackson, và starter-test mang JUnit Jupiter, Spring MVC Test, Mockito/JSONassert thường dùng theo BOM phiên bản.

Chạy từ thư mục có Gradle wrapper:

```bash
./gradlew test --tests com.example.fixturejson.ArticleControllerFixtureTest --tests com.example.fixturejson.ArticleHttpUtf8IntegrationTest --tests com.example.fixturejson.UnicodeNormalizationTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.fixturejson.ArticleControllerFixtureTest --tests com.example.fixturejson.ArticleHttpUtf8IntegrationTest --tests com.example.fixturejson.UnicodeNormalizationTest
```

Nếu project nhiều module, dùng task test đúng module. Không copy các snippets rời được đánh dấu “minh họa” thành file Java; các file runnable đã liệt kê ở mục 14–18.

**Kết quả kỳ vọng từ code đã mô tả:**

- `ArticleControllerFixtureTest`: **8** test cho JSON structural equality, STRICT/LENIENT, UTF-8 decoder, request echo, 404, BOM/fixture và key-order.
- `ArticleHttpUtf8IntegrationTest`: **1** test qua HTTP server thật, adapter demo thật, response JSON khớp fixture.
- `UnicodeNormalizationTest`: **1** unit test về Unicode NFC.
- Tổng: **10 JUnit test methods**. Nếu code, fixture và project configuration đúng như ví dụ, Gradle dự kiến báo `BUILD SUCCESSFUL`. Đây là **kết quả dự kiến từ rà soát mã**, không phải tuyên bố đã chạy Gradle trên repository cụ thể.
- Không có stdout nghiệp vụ cố định. Port server, startup logs và thời gian chạy khác nhau theo môi trường.
- Báo cáo thường nằm ở `build/reports/tests/test/index.html`; kết quả XML ở `build/test-results/test/` của module tương ứng.

**Lưu ý khi kiểm code:** toàn bộ Java string có quote/newline dùng đúng **một cấp escape** cho Java source; JSON fixture dùng một cấp escape cho JSON file. Tránh double-escaping khi chuyển giữa Java literal, JSON text và Markdown code fence.

## 26. Bài tập thực hành

### Bài A — JSON giống cấu trúc nhưng khác văn bản

Cho hai JSON object chỉ khác khoảng trắng và thứ tự key. So `assertEquals(String,String)` trả gì? So `JsonNode.equals` trả gì? Giải thích tại sao chỉ một trong hai phản ánh contract JSON thông thường.

**Đáp án định hướng:** Raw text có thể khác; parsed object trees có thể bằng nhau vì field/value tương đương.

### Bài B — UTF-8 và mojibake

Một fixture chứa `"Cà phê"`, nhưng test hiển thị `"CÃ  phÃª"`. Hãy kiểm byte[] và thử decode bằng UTF-8. Có nên đổi expected fixture thành mojibake để test xanh?

**Đáp án:** Không. Xác định lớp decode sai, dùng UTF-8 đúng và kiểm expected data gốc.

### Bài C — null hay missing?

Expected có `"note": null`, actual hoàn toàn không có `note`. `has("note")`, `get("note").isNull()` và `path("note")` phản ứng như thế nào? Viết assertion bắt đúng sự khác biệt theo contract.

### Bài D — array order

Expected tags `["cà phê","sách"]`, actual `["sách","cà phê"]`. Nếu API quy định thứ tự ưu tiên, nên dùng matcher nào? Nếu API không quy định order, nên dùng matcher nào?

**Gợi ý:** `contains` vs `containsInAnyOrder`; structural full equality thường bắt thứ tự array.

### Bài E — chọn STRICT hay LENIENT

API cho phép thêm field `metadata` nhưng không cho phép `internalToken`. Có nên dùng JSONAssert LENIENT với expected chỉ có `id`/`title`? Cần thêm assertion nào?

**Đáp án:** Có thể dùng LENIENT cho contract extensible, nhưng phải assert `$.internalToken` **hoàn toàn không có**, hoặc dùng schema/policy test.

### Bài F — Escape qua hai lớp

Với Java string có quote thật và newline thật, hãy viết source Java:

```java
String summary = "Dòng 1: \"đậm\"\nDòng 2";
```

Sau đó viết JSON fixture tương ứng:

```json
{"summary":"Dòng 1: \"đậm\"\nDòng 2"}
```

Nhìn văn bản nguồn có thể gần giống, nhưng **Java compiler** và **JSON parser** là hai thành phần xử lý escape khác nhau. Hãy giải thích vì sao không dùng newline thô trong JSON string.

### Bài G — fixture từ response có phải test tốt?

Một script lấy response production hiện tại rồi lưu đè fixture trước mỗi lần chạy JUnit. Test pass mọi lúc. Nếu response chứa field bí mật hoặc sai amount, nó có phát hiện không? Hãy đề xuất workflow review snapshot và expected độc lập.

### Bài H — timestamp không xác định

Fixture chứa `"createdAt": "2026-11-08T10:15:30Z"`; service thật dùng `Instant.now()`. Test fail ngẫu nhiên hoặc luôn fail. Hãy sửa bằng fixed Clock hoặc dùng assertion theo invariant phù hợp, và giải thích vì sao default timezone cũng cần cân nhắc.

### Bài I — full HTTP khác gì WebMvcTest?

Nếu `ArticleControllerFixtureTest` pass nhưng `DemoArticleCatalog` production trả sai title thì test MVC có bắt không? Bài nào trong ví dụ chạy adapter thật?

**Đáp án:** Slice dùng `@MockitoBean ArticleCatalog` nên không chạy adapter. `ArticleHttpUtf8IntegrationTest` dùng full context và server thật, sẽ so response adapter với fixture.

## 27. Checklist rà soát fixture và charset

- [ ] Fixture có path/name phản ánh scenario, nằm trong `src/test/resources`.
- [ ] File JSON được lưu **UTF-8 không BOM** và parse được.
- [ ] Expected được review độc lập, không sinh tự động từ chính actual ngay trước assertion.
- [ ] Tôi phân biệt raw bytes, raw text, JSON tree equality và focused field assertions.
- [ ] Tôi không yêu cầu `charset=UTF-8` trong Content-Type khi HTTP JSON contract không quy định nó.
- [ ] Khi cần kiểm byte encoding, tôi lấy `byte[]` và dùng UTF-8 decoder/reporting thích hợp.
- [ ] Tôi không dựa vào `MockHttpServletResponse.getContentAsString()` nếu charset fallback có thể khiến tiếng Việt bị giải mã sai.
- [ ] Tôi hiểu JSON `\"`, `\n` và Java source string `\"`, `\n` là **hai lớp parser khác nhau**.
- [ ] Unicode trực tiếp và `\uXXXX` được so theo giá trị đã parse, không theo raw textual escape khi không cần.
- [ ] Tôi biết Unicode normalization không tự xảy ra theo ý muốn của test.
- [ ] Object key order/whitespace không làm false fail; array order được kiểm theo contract.
- [ ] Tôi kiểm type, value, null, missing và các field nhạy cảm.
- [ ] Tôi chọn JSONAssert `STRICT/LENIENT` có chủ đích.
- [ ] Với số tiền và decimals, tôi có numeric contract rõ, tránh dùng double/tolerance vô tội vạ.
- [ ] Timestamp/timezone/locale/random ID được cố định hoặc assert bằng invariant.
- [ ] Nếu serializer thay naming/date/enum/module, test có thể phát hiện thay đổi contract.
- [ ] Tôi không gọi một MVC slice có mock service là bằng chứng tất cả business rules đã đúng.
- [ ] Tôi có integration/adapter test riêng cho các boundary cần chạy thật.
- [ ] Test độc lập, không phụ thuộc thứ tự chạy hoặc fixture mutable dùng chung.

**Kết luận:** Một JSON fixture tốt là một **bản mô tả hợp đồng đã review**, không phải bản sao mù quáng của response. RFC 8259 hướng JSON trao đổi tới UTF-8; Spring MVC/Jackson cho phép kiểm dữ liệu ở dạng bytes và cây JSON mà không bị đánh lừa bởi hiển thị/charset fallback. Khi so sánh, hãy **chặt ở field, type, value và sự vắng mặt quan trọng**, nhưng **linh hoạt với whitespace, object key order và encoding escape tương đương** khi hợp đồng không yêu cầu raw bytes. Kết hợp slice test, full-context HTTP test và unit tests theo đúng ranh giới để test vừa ổn định vừa phát hiện bug thật.

### Tài liệu tham khảo chính thức

- RFC 8259 — JSON, UTF-8, BOM, Unicode escapes: https://www.rfc-editor.org/rfc/rfc8259
- Spring Framework 6.2 — `MockHttpServletResponse.getContentAsString(Charset)` và `getContentAsByteArray()`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/mock/web/MockHttpServletResponse.html
- Spring Framework 6.2 — `ContentResultMatchers.json(..., JsonCompareMode)`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/test/web/servlet/result/ContentResultMatchers.html
- Spring Boot 3.5 — Testing Spring MVC Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Jackson Databind — `JsonNode` tree model: https://github.com/FasterXML/jackson-databind
