# Phân biệt định dạng ổn định và chuẩn hóa JSON dùng để ký hoặc băm

Khi serialize cùng một dữ liệu Java nhiều lần, ứng dụng đôi khi muốn nhận được cùng một chuỗi JSON hoặc cùng một dãy byte. Yêu cầu này thường xuất hiện khi tạo snapshot test, cache key, checksum, hash hoặc chữ ký số. Tuy nhiên, **serialize ổn định** và **canonicalize JSON** là hai khái niệm khác nhau.

Jackson có thể được cấu hình để tạo output có tính xác định trong một môi trường cụ thể: sắp xếp property, sắp xếp map key, cố định định dạng ngày giờ, quy định null, encoding và cách ghi số. Cách làm đó giúp giảm khác biệt không cần thiết giữa các lần serialize. Nhưng nó không tự động bảo đảm output tuân thủ một chuẩn canonical JSON dùng chung giữa các ngôn ngữ và thư viện.

Nếu byte JSON được dùng làm đầu vào cho chữ ký số hoặc hash theo ý nghĩa dữ liệu, cần một thuật toán canonicalization được đặc tả rõ, chẳng hạn **JSON Canonicalization Scheme (JCS), RFC 8785**. Không nên xem việc bật sort property trên `ObjectMapper` là đã có JCS.

## 1. Vì sao cùng dữ liệu có thể tạo ra nhiều chuỗi JSON?

JSON cho phép nhiều cách viết khác nhau cho cùng một cấu trúc dữ liệu. Ví dụ:

```json
{"id":101,"name":"An","active":true}
```

```json
{
  "active": true,
  "name" : "An",
  "id": 101
}
```

Hai tài liệu trên có cùng các field và giá trị, nhưng khác thứ tự property, khoảng trắng và xuống dòng. Nếu tính SHA-256 trực tiếp trên byte của từng chuỗi, kết quả hash sẽ khác nhau.

Một số khác biệt khác cũng có thể làm thay đổi byte:

- Object property được ghi theo thứ tự khác nhau.
- `Map` sử dụng thứ tự duyệt không ổn định, ví dụ `HashMap` sau khi thay đổi nội dung hoặc runtime.
- `Set` được serialize thành array nhưng thứ tự phần tử không được xác định.
- Một lần ghi dùng pretty printing, lần khác dùng compact JSON.
- Giá trị ngày giờ phụ thuộc timezone, locale hoặc cấu hình timestamp.
- Giá trị `null` được đưa vào một lần nhưng bị bỏ qua ở lần khác.
- Số thập phân được ghi thành `1.0`, `1.00` hoặc dạng exponent khác.
- Serializer tùy chỉnh phụ thuộc thời gian hiện tại, cấu hình máy hoặc thứ tự iteration.
- Encoding và chính sách escape ký tự khác nhau.

Vì vậy, muốn hash hoặc ký dữ liệu có ý nghĩa ổn định, trước tiên phải xác định byte nào thực sự thuộc về hợp đồng.

## 2. Serialize ổn định là gì?

Serialize ổn định (deterministic serialization) là việc thiết lập một bộ quy tắc để cùng một object và cùng cấu hình tạo ra cùng một output trong phạm vi môi trường đã xác định.

Ví dụ, một ứng dụng có thể quy định:

- Property của POJO được ghi theo thứ tự cố định.
- Entry trong map được sắp xếp theo key.
- Collection có thứ tự được giữ nguyên; `Set` phải được sắp xếp trước khi ghi.
- JSON luôn compact, không có khoảng trắng định dạng.
- Ngày giờ dùng một định dạng ISO-8601 và timezone được quy định rõ.
- Chính sách ghi `null` nhất quán.
- Số và kiểu dữ liệu được serialize bằng cùng serializer/version.
- Byte đầu ra luôn dùng UTF-8.

Khi các yếu tố trên được kiểm soát, output Jackson có thể ổn định trong cùng một phiên bản ứng dụng, JDK, Jackson và cấu hình. Đây là điều hữu ích cho snapshot test, cache key nội bộ hoặc checksum của output đã được định nghĩa.

Tuy nhiên, ổn định trong một ứng dụng không đồng nghĩa với canonical theo một chuẩn độc lập. Hai hệ thống dùng Jackson và một thư viện JSON khác vẫn có thể tạo byte khác nhau cho cùng JSON data model.

## 3. Cấu hình Jackson để tạo output có tính xác định

Jackson có một số feature giúp kiểm soát thứ tự và định dạng output. Ví dụ sau tạo mapper với property ordering, map ordering và JSON compact:

```java
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper stableMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
        .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
        .disable(SerializationFeature.INDENT_OUTPUT)
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();
```

Các cấu hình chính:

- `MapperFeature.SORT_PROPERTIES_ALPHABETICALLY`: sắp xếp property của POJO theo tên alphabet khi Jackson xây dựng thứ tự property.
- `SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS`: yêu cầu serializer sắp xếp entry của map theo key.
- `SerializationFeature.INDENT_OUTPUT`: tắt pretty printing để không thêm khoảng trắng định dạng.
- `SerializationFeature.WRITE_DATES_AS_TIMESTAMPS`: tắt dạng timestamp số/mảng để dùng chuỗi ngày giờ của serializer Java Time.
- `JavaTimeModule`: cung cấp hỗ trợ cho các kiểu `java.time` như `Instant`, `LocalDateTime` và `OffsetDateTime`.

Các feature này phải được cấu hình trước khi mapper được đưa vào sử dụng và giữ nhất quán giữa các nơi serialize.

### 3.1. Sắp xếp property của POJO

Có thể dùng `@JsonPropertyOrder` để khai báo thứ tự tường minh cho một DTO:

```java
@JsonPropertyOrder({"id", "name", "createdAt"})
public record UserSnapshot(
        long id,
        String name,
        Instant createdAt
) {
}
```

Đây là lựa chọn phù hợp khi thứ tự output là một phần của format nội bộ hoặc fixture. Nếu dùng `SORT_PROPERTIES_ALPHABETICALLY`, thứ tự được xác định theo tên property. Nếu dùng `@JsonPropertyOrder`, thứ tự được khai báo theo contract của kiểu đó. Tránh để nhiều chính sách thứ tự mâu thuẫn mà không có lý do.

### 3.2. Sắp xếp map key

`HashMap` không phải lựa chọn tốt nếu output cần thứ tự ổn định. Có thể bật `ORDER_MAP_ENTRIES_BY_KEYS` hoặc dùng một map đã được sắp xếp:

```java
Map<String, Integer> counts = new TreeMap<>();
counts.put("pending", 3);
counts.put("active", 10);
counts.put("closed", 2);

String json = stableMapper.writeValueAsString(counts);
```

Với key là `String`, thứ tự tự nhiên của `TreeMap` ổn định và dễ hiểu. Nếu map dùng key tùy chỉnh hoặc custom key serializer, cần định nghĩa thứ tự theo biểu diễn key của hợp đồng; đừng giả định mọi kiểu key đều có thể so sánh tự nhiên hoặc được sort theo đúng quy tắc canonical JSON.

### 3.3. Sắp xếp collection không có thứ tự

JSON array luôn có thứ tự. Nếu serialize một `Set`, thứ tự iteration của Set có thể không ổn định. Hãy chuyển thành list và sắp xếp theo quy tắc nghiệp vụ trước khi serialize:

```java
List<String> sortedRoles = roles.stream()
        .sorted()
        .toList();

String json = stableMapper.writeValueAsString(sortedRoles);
```

Không tự sắp xếp một list vốn mang thứ tự nghiệp vụ, vì việc đó có thể làm thay đổi ý nghĩa dữ liệu. Chỉ chuẩn hóa thứ tự khi contract xác định các phần tử là một tập hợp không có thứ tự.

### 3.4. Cố định null, ngày giờ, số và serializer tùy chỉnh

Thứ tự property chưa đủ để bảo đảm output ổn định. Ứng dụng cần quyết định rõ:

- Có ghi field null hay bỏ field null.
- Ngày giờ dùng UTC, offset nguồn hay ZoneId khu vực.
- Timestamp dùng giây, mili giây hay chuỗi ISO-8601.
- `BigDecimal` giữ scale hay được chuẩn hóa theo một quy tắc riêng.
- Custom serializer có phụ thuộc locale, timezone, đồng hồ hệ thống, environment variable hoặc iteration order không.
- String có dùng cùng encoding và chính sách escape hay không.

Ví dụ, nếu contract yêu cầu mọi field null đều xuất hiện, có thể cấu hình inclusion phù hợp trước khi mapper được sử dụng:

```java
stableMapper.setSerializationInclusion(JsonInclude.Include.ALWAYS);
```

Nếu contract yêu cầu bỏ null, dùng `NON_NULL` nhất quán thay vì để từng service tự chọn. Annotation `@JsonInclude` trên class/property có thể tạo override, nên cần bảo đảm các override đó là một phần của contract.

Với ngày giờ, nên chọn kiểu biểu diễn phù hợp và cấu hình rõ timezone. Ví dụ `Instant` có thể được ghi dưới dạng UTC ISO string; `OffsetDateTime` có thể giữ offset; `ZonedDateTime` cần chính sách giữ hoặc bỏ ZoneId. Không dựa vào timezone mặc định của máy chạy.

Với custom serializer, tránh lấy `LocalDateTime.now()`, `Locale.getDefault()`, `ZoneId.systemDefault()` hoặc duyệt `HashSet` trực tiếp nếu những giá trị đó ảnh hưởng output. Nếu chúng là dữ liệu nghiệp vụ, hãy truyền chúng vào object và định dạng theo contract rõ ràng.

## 4. Lấy byte output ổn định từ Jackson

Hash và chữ ký số làm việc trên byte, không làm việc trực tiếp trên khái niệm object Java. Sau khi cấu hình mapper, hãy lấy byte output với encoding xác định:

```java
byte[] stableBytes = stableMapper.writeValueAsBytes(snapshot);
```

`writeValueAsBytes(...)` tạo byte JSON UTF-8. Nếu dùng `writeValueAsString(...)`, cần encode chuỗi thành UTF-8 một cách tường minh trước khi hash:

```java
byte[] stableBytes = stableMapper.writeValueAsString(snapshot)
        .getBytes(StandardCharsets.UTF_8);
```

Không lấy `String.length()` làm số byte để hash hoặc ký. `String.length()` đếm UTF-16 code unit; số byte UTF-8 có thể khác, đặc biệt với ký tự ngoài ASCII.

Có thể kiểm tra tính lặp lại trong cùng môi trường bằng test:

```java
byte[] first = stableMapper.writeValueAsBytes(snapshot);
byte[] second = stableMapper.writeValueAsBytes(snapshot);

assertArrayEquals(first, second);
```

Test này xác nhận cùng object/configuration tạo cùng byte trong lần chạy đang kiểm tra. Nó không chứng minh output tuân thủ JCS hoặc giống byte do một ngôn ngữ khác tạo ra.

## 5. Chuẩn hóa JSON (canonicalization) là gì?

Canonicalization là quá trình biến một JSON value thành một biểu diễn byte duy nhất theo một bộ quy tắc công khai. Mục tiêu là để các tài liệu có cùng JSON data model tạo ra cùng byte canonical, dù input ban đầu khác khoảng trắng hoặc thứ tự object property.

Một chuẩn canonical JSON cần xác định ít nhất:

- Cách xử lý whitespace.
- Thứ tự property trong object.
- Cách escape string và mã hóa Unicode.
- Cách biểu diễn number.
- Cách xử lý duplicate property name và các dữ liệu không hợp lệ.
- Encoding byte đầu ra.

Nếu hai hệ thống tuân thủ cùng một chuẩn canonicalization, chúng có thể independently tạo ra cùng byte cho cùng JSON data model và dùng byte đó cho hash hoặc chữ ký số.

## 6. JSON Canonicalization Scheme (JCS), RFC 8785

JCS được đặc tả trong RFC 8785. Đây là một chuẩn canonicalization JSON phổ biến, xác định cách tạo biểu diễn JSON ổn định dựa trên các ràng buộc I-JSON và quy tắc serialize tương thích ECMAScript.

Các đặc điểm chính của JCS:

1. Output không chứa whitespace định dạng không cần thiết.
2. Tên property trong object được sắp xếp theo thứ tự từ điển dựa trên UTF-16 code units; đây không phải sort theo locale.
3. String được escape theo quy tắc JSON/ECMAScript mà chuẩn quy định.
4. Number được serialize theo quy tắc ECMAScript cho số IEEE-754 binary64.
5. Array giữ nguyên thứ tự phần tử.
6. JSON object không được có duplicate property names.
7. Output là byte UTF-8.

JCS không tự chuẩn hóa Unicode về NFC/NFD. Hai string nhìn giống nhau nhưng có chuỗi code point khác nhau vẫn có thể tạo byte canonical khác nhau. Nếu nghiệp vụ yêu cầu chuẩn hóa Unicode, phải định nghĩa và thực hiện bước đó như một phần của hợp đồng trước canonicalization; không tự ý normalize vì có thể thay đổi dữ liệu.

### 6.1. Ví dụ về thứ tự property và whitespace

Hai input:

```json
{"b":2,"a":1}
```

```json
{
  "a": 1,
  "b": 2
}
```

được canonicalize theo JCS thành cùng một dạng:

```json
{"a":1,"b":2}
```

Whitespace bị loại bỏ và property được sắp xếp theo quy tắc của chuẩn. Nếu tính hash trên byte canonical, hai input này tạo cùng digest.

### 6.2. Quy tắc number có ý nghĩa quan trọng

JCS dùng quy tắc biểu diễn số tương thích ECMAScript/IEEE-754 binary64. Điều đó có nghĩa canonicalization không phải là một cơ chế giữ nguyên mọi dạng số thập phân tùy ý của Java.

Ví dụ, `BigDecimal` có thể giữ scale và độ chính xác thập phân mà `double` không thể biểu diễn chính xác. Một số nguyên lớn hơn phạm vi biểu diễn chính xác của IEEE-754 binary64 cũng có thể bị làm tròn nếu chuyển qua kiểu số đó. Với mã định danh dài, số tài khoản hoặc decimal cần độ chính xác tuyệt đối, hãy cân nhắc biểu diễn theo string trong JSON contract nếu chuẩn/consumer yêu cầu JCS.

Không nên chuyển `BigDecimal` thành `double` chỉ để “cho giống JCS” mà không xem xét mất chính xác. Cần xác định rõ kiểu dữ liệu JSON mà contract cho phép và giới hạn numeric trước khi canonicalize.

### 6.3. Duplicate property name phải bị từ chối

JSON text có thể chứa duplicate field name về mặt parser permissive, ví dụ:

```json
{"role":"user","role":"admin"}
```

Các consumer khác nhau có thể giữ giá trị đầu, giữ giá trị cuối hoặc từ chối. Một canonicalizer không thể đưa ra kết quả liên hệ thống đáng tin cậy nếu đầu vào có ý nghĩa mơ hồ như vậy. JCS dựa trên ràng buộc không có duplicate property name; ứng dụng nên phát hiện và từ chối duplicate trước canonicalization.

## 7. Vì sao sort property bằng Jackson chưa phải JCS?

Jackson có thể sắp xếp property và map key, nhưng JCS quy định nhiều điều hơn thứ tự field:

| Khía cạnh | Jackson deterministic config | JCS (RFC 8785) |
|---|---|---|
| POJO property order | Có thể sắp xếp alphabet hoặc dùng `@JsonPropertyOrder` | Bắt buộc sort theo quy tắc UTF-16 code units |
| Map key | Có thể sort bằng `ORDER_MAP_ENTRIES_BY_KEYS` | Sort tên property theo quy tắc chuẩn |
| Whitespace | Có thể tắt pretty printing | Quy định bỏ whitespace không cần thiết |
| Number | Theo serializer và kiểu Java/Jackson | Theo ECMAScript number serialization, IEEE-754 binary64 |
| String escaping | Theo Jackson generator/configuration | Theo quy tắc JCS/ECMAScript |
| Duplicate property | Phụ thuộc parser/cấu hình và cách tạo object | Input canonicalization phải không có duplicate names |
| Unicode normalization | Không phải mục tiêu tự động của mapper | JCS không thực hiện Unicode normalization |
| Tính tương thích liên ngôn ngữ | Phụ thuộc implementation/version | Có quy tắc chuẩn độc lập implementation |

Ngay cả khi một payload đơn giản tạo cùng output bằng Jackson và JCS, điều đó không chứng minh hai cách tương đương với mọi dữ liệu. Chênh lệch có thể xuất hiện ở số lớn, decimal, ký tự Unicode, custom serializer, key order hoặc date/time.

Vì vậy, nếu contract yêu cầu RFC 8785, hãy dùng implementation JCS đã được kiểm chứng. Có thể dùng Jackson để parse và xử lý DTO, nhưng bước tạo byte canonical phải tuân thủ chính xác RFC 8785.

## 8. Quy trình chuẩn để hash JSON theo ý nghĩa dữ liệu

Nếu mục tiêu là coi hai JSON có cùng data model là cùng một nội dung, quy trình thường là:

```text
JSON input bytes
       |
       v
Parse và kiểm tra đầu vào
       |
       +--> Từ chối duplicate property names
       +--> Kiểm tra Unicode và giới hạn number
       +--> Kiểm tra schema/contract nếu cần
       |
       v
JCS canonicalization (RFC 8785)
       |
       v
Canonical UTF-8 bytes
       |
       v
Cryptographic hash (ví dụ SHA-256)
       |
       v
Digest bytes / hex
```

Ví dụ dưới đây dùng tên `jcsCanonicalizer` như một placeholder mô tả thư viện canonicalization. Đây **không phải API của Jackson**; cần thay bằng implementation RFC 8785 được project lựa chọn:

```java
byte[] canonicalBytes = jcsCanonicalizer.canonicalize(inputJsonBytes);

byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(canonicalBytes);

String hexDigest = HexFormat.of().formatHex(digest);
```

Không tính SHA-256 trực tiếp trên chuỗi JSON ban đầu nếu muốn bỏ qua khác biệt whitespace/property order. Hash phải được tính trên byte canonical do cùng một chuẩn tạo ra.

## 9. Quy trình ký số JSON

Ký số cũng cần một dãy byte đầu vào chính xác. Nếu bên gửi và bên nhận có thể nhận cùng JSON với whitespace hoặc property order khác nhau, hai bên phải canonicalize theo cùng chuẩn trước khi ký và xác minh.

Luồng tổng quát:

```text
Bên gửi                               Bên nhận
---------                              ---------
JSON data                              JSON data nhận được
   |                                           |
   v                                           v
JCS canonicalize                       JCS canonicalize
   |                                           |
   v                                           v
Canonical bytes                         Canonical bytes
   |                                           |
   v                                           v
Sign bằng private key                Verify bằng public key
   |                                           ^
   v                                           |
Signature -------------------------------+    |
```

Ví dụ với Ed25519:

```java
byte[] canonicalBytes = jcsCanonicalizer.canonicalize(inputJsonBytes);

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(canonicalBytes);
byte[] signatureBytes = signer.sign();
```

Ở bên xác minh, parse và canonicalize JSON nhận được bằng cùng quy tắc, sau đó:

```java
byte[] receivedCanonicalBytes =
        jcsCanonicalizer.canonicalize(receivedJsonBytes);

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
verifier.update(receivedCanonicalBytes);

boolean valid = verifier.verify(signatureBytes);
```

Nếu một bên dùng Jackson compact JSON còn bên kia dùng JCS, chữ ký sẽ không khớp. Cả hai bên phải dùng cùng thuật toán canonicalization, cùng quy tắc xử lý input và cùng byte encoding.

Chữ ký số còn cần quản lý private key, thuật toán, key rotation, danh tính người ký và metadata thuật toán. Canonicalization chỉ xác định byte được ký; nó không thay thế các yêu cầu bảo mật đó.

## 10. Một lựa chọn khác: ký chính xác byte JSON đã nhận

Không phải mọi hệ thống đều cần ký theo ý nghĩa data model. Một số hợp đồng muốn xác nhận **đúng byte đã được gửi**, bao gồm whitespace, thứ tự property và cách escape.

Trong trường hợp đó, có thể ký trực tiếp byte payload nhận được:

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(originalPayloadBytes);
byte[] signatureBytes = signer.sign();
```

Khi xác minh, phải dùng chính xác byte tương ứng. Nếu gateway parse JSON rồi serialize lại, byte thay đổi và chữ ký sẽ không còn hợp lệ dù data model có thể giống nhau.

Hai mô hình khác nhau:

| Mô hình | Byte được ký | Hành vi khi chỉ đổi whitespace/order |
|---|---|---|
| Ký byte nguyên bản | Byte payload ban đầu | Chữ ký thay đổi/không xác minh được |
| Ký JSON canonical | Byte canonical theo chuẩn | Chữ ký vẫn xác minh nếu data model canonical không đổi |

Hãy chọn một mô hình trong contract và truyền đạt rõ cho mọi bên tham gia. Không trộn hai mô hình trong cùng một luồng.

## 11. Kiểm tra đầu vào trước canonicalization

Canonicalization không phải validation nghiệp vụ. Trước khi tạo byte canonical, ứng dụng cần quyết định input nào được chấp nhận.

Các điểm thường cần kiểm tra:

- JSON có cú pháp hợp lệ và đúng một root value.
- Không có duplicate property name.
- Tên field và string có Unicode hợp lệ theo yêu cầu của chuẩn.
- Number nằm trong miền mà canonicalizer/contract hỗ trợ.
- Schema có đúng kiểu và field cần thiết.
- Field nhạy cảm hoặc field chỉ server được phép đặt không bị người dùng tự cung cấp.
- Các giá trị ngày giờ, tiền và identifier có biểu diễn được quy định rõ.

Jackson có thể bật strict duplicate detection khi parse:

```java
JsonFactory strictFactory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

ObjectMapper parserMapper = new ObjectMapper(strictFactory)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

JsonNode tree = parserMapper.readTree(inputJsonBytes);
```

Đây là bước parse/kiểm tra đầu vào hữu ích. Nó không tự thực hiện JCS. Sau khi parse, vẫn cần canonicalizer tuân thủ RFC 8785 để tạo byte chuẩn.

Nếu canonicalizer có parser/validator riêng và đã bảo đảm các ràng buộc cần thiết, hãy tuân theo API và giới hạn của implementation đó. Không parse permissive thành `JsonNode` rồi giả định duplicate key đã được phát hiện: với cấu hình mặc định, thông tin về duplicate có thể đã mất khi các field được đưa vào tree.

## 12. Các vấn đề dữ liệu cần đặc biệt chú ý

### 12.1. BigDecimal và số có độ chính xác cao

Java `BigDecimal` có thể giữ số chữ số thập phân và scale. JCS lại sử dụng mô hình số IEEE-754 binary64 và cách biểu diễn ECMAScript. Nếu dữ liệu cần độ chính xác decimal tuyệt đối, ví dụ số tiền, phải thống nhất cách biểu diễn trong schema. Có thể dùng chuỗi decimal với grammar được quy định nếu contract cần bảo toàn chính xác chữ số.

### 12.2. Số nguyên lớn và identifier

Các ID dài thường không nên được xem là đại lượng số cần tính toán. Nếu giá trị vượt miền số nguyên có thể biểu diễn chính xác theo binary64, hãy biểu diễn identifier thành JSON string trong contract. Điều này tránh việc canonicalizer hoặc consumer chuyển đổi số làm mất chữ số.

### 12.3. Unicode và chuỗi nhìn giống nhau

Ký tự có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc một chuỗi base character cộng combining mark. Chúng có thể hiển thị giống nhau nhưng byte khác nhau. JCS không tự normalize chúng về cùng một dạng. Nếu hệ thống cần coi hai cách viết là tương đương, hãy quy định Unicode normalization ở tầng nghiệp vụ và áp dụng nhất quán trước khi canonicalize.

### 12.4. Ngày giờ và múi giờ

JCS chỉ thấy ngày giờ là JSON string. Nó không hiểu `2026-11-12T09:30:00Z` và `2026-11-12T16:30:00+07:00` là cùng một instant. Nếu ứng dụng muốn hai giá trị đó được xem là tương đương khi hash, phải chuẩn hóa chúng về cùng biểu diễn theo schema trước canonicalization, ví dụ UTC ISO string. Nếu offset nguồn là dữ liệu cần giữ, không được tự ý chuẩn hóa.

### 12.5. Field bị bỏ qua hoặc giá trị mặc định

Canonicalization không tự quyết định `null`, field vắng mặt và field có giá trị mặc định có ý nghĩa như nhau hay không. `{"enabled":false}`, `{"enabled":null}` và `{}` là ba cấu trúc JSON khác nhau. Hãy xác định contract trước khi hash hoặc ký.

## 13. Vì sao không nên tự viết canonicalizer bằng vài feature Jackson?

Một canonicalizer phải xử lý chính xác nhiều chi tiết nhỏ có thể ảnh hưởng chữ ký:

- Thứ tự property theo đúng quy tắc chuẩn, không phụ thuộc locale.
- Sắp xếp tên có ký tự ngoài ASCII theo UTF-16 code units.
- Escape string và control character đúng quy tắc.
- Number serialization nhất quán với IEEE-754/ECMAScript.
- Xử lý `-0`, exponent và ranh giới số đúng chuẩn.
- Từ chối duplicate property name và dữ liệu Unicode không hợp lệ.
- Xuất UTF-8 chính xác.

Chỉ bật `SORT_PROPERTIES_ALPHABETICALLY`, `ORDER_MAP_ENTRIES_BY_KEYS` và tắt `INDENT_OUTPUT` chưa giải quyết đầy đủ các quy tắc trên. Tự triển khai một phần có thể tạo output trông hợp lý nhưng không tương thích với implementation khác, khiến chữ ký hợp lệ ở bên gửi nhưng thất bại ở bên nhận.

Nếu contract yêu cầu RFC 8785, hãy chọn thư viện JCS có kiểm thử tương thích với RFC, pin version và dùng test vector của chuẩn. Jackson có thể tiếp tục đảm nhiệm Databind, DTO và validation; canonicalizer đảm nhiệm bước tạo byte chuẩn.

## 14. Test tính ổn định và canonicalization

Nên tách test cho hai mục tiêu.

### 14.1. Test deterministic Jackson output

Test này xác nhận cùng object và mapper tạo byte giống nhau:

```java
byte[] first = stableMapper.writeValueAsBytes(snapshot);
byte[] second = stableMapper.writeValueAsBytes(snapshot);

assertArrayEquals(first, second);
```

Nên bổ sung fixture có:

- Map được chèn entry theo thứ tự khác nhau.
- Set có thứ tự iteration khác nhau.
- Null và field tùy chọn.
- String có Unicode, dấu ngoặc kép và ký tự điều khiển.
- Số nguyên lớn và decimal.
- Ngày giờ có offset/zone.

### 14.2. Test JCS bằng test vector

Với canonicalizer, hãy kiểm tra input khác whitespace và property order tạo cùng canonical bytes:

```java
byte[] first = jcsCanonicalizer.canonicalize(
        "{\"b\":2,\"a\":1}".getBytes(StandardCharsets.UTF_8)
);

byte[] second = jcsCanonicalizer.canonicalize(
        "{ \"a\" : 1, \"b\" : 2 }".getBytes(StandardCharsets.UTF_8)
);

assertArrayEquals(first, second);
```

Đây là ví dụ minh họa API placeholder của canonicalizer, không phải API Jackson. Trong project, thay bằng API thật của thư viện RFC 8785 và chạy đầy đủ test vector của thư viện/chuẩn.

Ngoài ra, cần test các trường hợp phải bị từ chối: duplicate property, number vượt miền hỗ trợ, Unicode không hợp lệ, trailing token và dữ liệu sai schema.

## 15. Bảng chọn cách tiếp cận

| Mục đích | Cách làm phù hợp |
|---|---|
| Snapshot test trong cùng project | Cấu hình Jackson deterministic và lưu ý version/configuration |
| Cache key nội bộ từ DTO | Xác định contract byte, dùng serialization ổn định hoặc canonicalization nếu cần tương thích đa hệ thống |
| Checksum byte file/payload | Hash trực tiếp byte nguyên bản |
| Hash theo ý nghĩa JSON data model | Canonicalize bằng chuẩn như JCS rồi hash canonical bytes |
| Chữ ký số cần bỏ qua whitespace/property order | Canonicalize theo chuẩn thống nhất rồi ký canonical bytes |
| Chữ ký xác nhận chính xác request bytes | Ký và xác minh đúng byte payload nguyên bản |
| Cần RFC 8785 | Dùng implementation JCS; không thay bằng sort property của Jackson |

## 16. Ghi nhớ

Serialize ổn định là kiểm soát Jackson để cùng object/configuration tạo output nhất quán trong phạm vi runtime và version đã xác định. Có thể dùng property ordering, map ordering, thứ tự collection, compact output, null policy, date/time policy, number formatting và UTF-8 để giảm khác biệt.

Canonicalization là chuẩn hóa JSON thành một biểu diễn byte duy nhất theo quy tắc công khai. Với JCS (RFC 8785), quy tắc bao gồm whitespace, property sorting theo UTF-16 code units, string escaping, number serialization theo ECMAScript/IEEE-754, duplicate-name constraints và UTF-8. Jackson sorting không tự tạo ra JCS.

Nếu hash hoặc ký theo byte nguyên bản, dùng đúng byte đã nhận và bảo đảm byte không bị serialize lại. Nếu hash hoặc ký theo ý nghĩa JSON, canonicalize bằng cùng một chuẩn ở cả bên tạo và bên xác minh, sau đó hash/ký chính canonical UTF-8 bytes. Luôn quy định rõ number precision, Unicode, ngày giờ, null và schema; không tự viết canonicalizer rút gọn cho dữ liệu bảo mật quan trọng.
