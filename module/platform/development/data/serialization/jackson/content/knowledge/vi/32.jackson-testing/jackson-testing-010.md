# Kiểm thử dữ liệu dư, tên trường trùng và cú pháp mở rộng

JSON có cú pháp tương đối chặt chẽ: tên property và string phải dùng dấu nháy kép, object không được có dấu phẩy thừa ở cuối, và một JSON document chỉ có một root value. Tuy nhiên, dữ liệu thực tế đôi khi chứa nhiều nội dung sau root, tên field bị lặp hoặc cú pháp mở rộng do một thư viện khác sinh ra.

Khi kiểm thử Jackson, cần phân biệt ba nhóm vấn đề:

- **Dữ liệu dư sau root (trailing tokens):** sau một JSON value hoàn chỉnh còn một value hoặc token khác trong cùng input.
- **Tên trường trùng (duplicate object keys):** cùng một object chứa một property name nhiều lần.
- **Cú pháp mở rộng (non-standard JSON syntax):** ví dụ single quotes, unquoted field names, comment hoặc trailing comma.

Ngoài ra còn có **unknown properties**: JSON object có một key mà DTO Java không khai báo. Đây là một vấn đề khác với trailing tokens và duplicate keys. Jackson có các feature riêng cho từng trường hợp; bật một feature không tự giải quyết các trường hợp còn lại.

Trong API nhận JSON từ client hoặc hệ thống bên ngoài, nên giữ parser strict theo chuẩn JSON và chủ động bật các kiểm tra cần thiết. Nếu phải đọc dữ liệu legacy có cú pháp mở rộng, hãy cô lập chế độ lenient ở đúng boundary thay vì nới lỏng mọi mapper trong ứng dụng.

## 1. Phân biệt bốn loại dữ liệu không mong đợi

Giả sử DTO:

```java
public class UserRequest {
    private String name;
    private int age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
```

Các input sau không cùng một loại lỗi:

| Loại | Ví dụ | Cơ chế Jackson liên quan |
|---|---|---|
| Unknown property | `{"name":"An","age":20,"role":"ADMIN"}` | `FAIL_ON_UNKNOWN_PROPERTIES`, `@JsonIgnoreProperties`, `@JsonAnySetter` |
| Duplicate property | `{"name":"An","name":"Binh"}` | `StreamReadFeature.STRICT_DUPLICATE_DETECTION` |
| Trailing root value | `{"name":"An","age":20} {"name":"Binh","age":21}` | `FAIL_ON_TRAILING_TOKENS` |
| Non-standard syntax | `{'name':'An','age':20}` | `JsonReadFeature` và parser configuration |

Một request có thể đồng thời chứa nhiều vấn đề, ví dụ một object có duplicate key và sau đó còn một root value khác. Khi kiểm thử, nên tạo test riêng cho từng điều kiện để biết feature nào đang chịu trách nhiệm.

## 2. Strict JSON là điểm bắt đầu

JSON chuẩn yêu cầu tên property và string được đặt trong dấu nháy kép. Ví dụ hợp lệ:

```json
{
  "name": "An",
  "age": 20
}
```

Các dạng sau không thuộc cú pháp JSON chuẩn:

```text
{'name': 'An'}       // single quotes
{name: "An"}         // unquoted field name
{"age": 020}         // leading zero
{"age": 20,}         // trailing comma
{/* comment */ "age": 20}
```

Jackson mặc định đọc JSON theo cú pháp strict. Những cú pháp mở rộng chỉ được chấp nhận khi ứng dụng bật parser feature tương ứng. Đây là một lựa chọn có chủ đích: nếu mọi parser đều tự động chấp nhận extension, dữ liệu không chuẩn có thể lan rộng và tạo khác biệt giữa các parser trong hệ thống.

Một cấu hình strict có thể được tạo rõ ràng:

```java
JsonFactory factory = JsonFactory.builder().build();
ObjectMapper mapper = new ObjectMapper(factory)
    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Factory giữ parser strict theo mặc định; `FAIL_ON_TRAILING_TOKENS` bổ sung kiểm tra rằng input chỉ chứa một root value. Duplicate detection là một feature riêng và có thể bật thêm khi contract yêu cầu.

## 3. Kiểm tra dữ liệu dư sau root bằng FAIL_ON_TRAILING_TOKENS

Một JSON document có một root value. Nhưng một input stream có thể chứa thêm dữ liệu sau root:

```json
{"name":"An","age":20} {"name":"Binh","age":21}
```

Nếu ứng dụng mong đợi đúng một `UserRequest`, object đầu tiên có thể được bind thành công trong khi phần còn lại không được xử lý theo ý định của API. Tình huống tương tự xảy ra với garbage sau JSON:

```text
{"name":"An","age":20} unexpected-data
```

Để yêu cầu không còn token sau root value, bật:

```java
ObjectMapper mapper = new ObjectMapper()
    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Khi bật feature, Jackson kiểm tra phần còn lại của input sau khi deserialize root value. Nếu có token khác, thao tác đọc thất bại bằng lỗi mapping/parsing.

### 3.1. Vì sao nên bật cho API nhận một document?

Nếu endpoint nhận một JSON object duy nhất, phần dữ liệu dư thường biểu thị:

- Client gửi nhầm hai document vào một body.
- Producer nối nhầm payload.
- Một thành phần chỉ đọc phần đầu của stream.
- Input bị chèn thêm dữ liệu ngoài contract.
- Một lớp validation kiểm tra khác phần body mà lớp binding xử lý.

Fail sớm giúp tránh tình trạng tầng gateway, tầng signature validation và tầng application diễn giải cùng body theo các cách khác nhau.

### 3.2. Test trailing token

```java
class TrailingTokenTest {
    private final ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    @Test
    void rejectsSecondRootValue() {
        String input = """
            {"name":"An","age":20}
            {"name":"Binh","age":21}
            """;

        assertThrows(JsonProcessingException.class,
            () -> mapper.readValue(input, UserRequest.class));
    }

    @Test
    void rejectsGarbageAfterRootValue() {
        String input = "{\"name\":\"An\",\"age\":20} trailing";

        assertThrows(JsonProcessingException.class,
            () -> mapper.readValue(input, UserRequest.class));
    }
}
```

Nên test cả root value thứ hai hợp lệ lẫn ký tự không hợp lệ sau root. Chúng chứng minh hai dạng dữ liệu dư đều bị từ chối.

### 3.3. Khi nào không bật FAIL_ON_TRAILING_TOKENS?

Một số giao thức cố ý truyền nhiều root values nối tiếp nhau trong cùng stream. Ví dụ một file có thể là sequence của nhiều JSON object chứ không phải một JSON array. Khi đó, mỗi root value là một record hợp lệ theo framing của giao thức.

Không dùng `readValue()` một lần rồi bỏ qua phần còn lại. Dùng API đọc sequence như `MappingIterator`/`ObjectReader.readValues()` hoặc đọc parser theo vòng lặp để xử lý từng root value:

```java
try (MappingIterator<UserRequest> iterator = mapper
        .readerFor(UserRequest.class)
        .readValues(inputStream)) {
    while (iterator.hasNextValue()) {
        UserRequest request = iterator.nextValue();
        process(request);
    }
}
```

Ở chế độ sequence, cần định nghĩa ranh giới record và xử lý record lỗi. Không nên bật `FAIL_ON_TRAILING_TOKENS` trên một reader chuyên đọc nhiều root values vì chính feature đó sẽ từ chối value thứ hai.

## 4. Unknown property không phải trailing token

Unknown property là key nằm bên trong object nhưng không được DTO nhận diện:

```json
{
  "name": "An",
  "age": 20,
  "department": "Engineering"
}
```

Nếu `UserRequest` không có property `department`, Jackson xử lý theo `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` (được bật mặc định trong cấu hình Databind thông thường, trừ khi annotation/handler xử lý khác).

Tắt feature:

```java
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

sẽ cho phép bỏ qua unknown properties. Cấu hình này không kiểm tra dữ liệu sau root và không phát hiện duplicate keys.

Nếu cần giữ dữ liệu mở, dùng `@JsonAnySetter`; nếu cần bỏ qua unknown key ở một DTO, có thể dùng `@JsonIgnoreProperties(ignoreUnknown = true)`. Với API strict, giữ hành vi fail để phát hiện field gõ sai hoặc schema drift.

## 5. Tên trường trùng trong cùng một object

JSON object không nên có các member name trùng nhau. RFC 8259 nói tên nên là duy nhất; khi tên bị lặp, behavior của receiver có thể khác nhau. Một số implementation giữ giá trị đầu, một số giữ giá trị cuối, và một số từ chối.

Ví dụ:

```json
{
  "role": "USER",
  "role": "ADMIN"
}
```

Nếu producer, gateway, signature verifier và consumer chọn cách xử lý khác nhau, cùng một message có thể mang ý nghĩa khác nhau ở mỗi tầng. Đây là lý do duplicate detection quan trọng với request có quyền hạn, cấu hình hoặc dữ liệu tài chính.

### 5.1. Hành vi khi không bật duplicate detection

Nếu parser không kiểm tra duplicate key, Jackson thường tiếp tục đọc cả hai field. Trong data binding thông thường, property có thể được gán nhiều lần và giá trị đọc sau cùng thường ghi đè giá trị trước. Với `Map` hoặc tree, entry trùng tên cũng có thể bị ghi đè.

Không nên dựa vào last-wins behavior như một phần của contract. Consumer khác có thể chọn first-wins hoặc reject. Nếu key phải duy nhất, hãy yêu cầu parser phát hiện duplicate.

### 5.2. Bật STRICT_DUPLICATE_DETECTION

Trong Jackson Core hiện đại, dùng `StreamReadFeature.STRICT_DUPLICATE_DETECTION` khi tạo `JsonFactory`:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Khi parser gặp cùng một property name lần thứ hai trong cùng object, nó ném lỗi thay vì tiếp tục âm thầm.

Feature này kiểm tra duplicate ở parser level, nên có tác dụng với nhiều kiểu đích như POJO, Map và tree model. Parser giữ trạng thái tên field của object đang đọc; vì vậy có thêm chi phí bộ nhớ và CPU. Bật khi tính đúng đắn/security của contract quan trọng hơn phần overhead đó, rồi benchmark trên workload thực tế.

Ở API cũ, có thể gặp cách cấu hình tương đương qua `JsonParser.Feature.STRICT_DUPLICATE_DETECTION`. Đây là API cũ/alias; với code mới, ưu tiên `StreamReadFeature` và kiểm tra Javadoc của Jackson version dự án.

### 5.3. Duplicate key ở object lồng nhau

Duplicate detection áp dụng theo từng object, bao gồm object lồng nhau:

```json
{
  "user": {
    "name": "An",
    "name": "Binh"
  }
}
```

Trong ví dụ, duplicate nằm bên trong object `user`. Parser strict sẽ từ chối khi đọc lần xuất hiện thứ hai của `name` trong object đó.

Hai object khác nhau có thể có cùng key hợp lệ:

```json
{
  "billing": {"city": "Hanoi"},
  "shipping": {"city": "HCMC"}
}
```

Tên `city` xuất hiện ở hai object khác nhau nên không phải duplicate trong cùng một object.

## 6. Duplicate detection khi đọc JsonNode

Jackson có thêm `DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY`, dành riêng cho việc đọc tree model:

```java
ObjectMapper treeMapper = new ObjectMapper()
    .enable(DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY);

JsonNode node = treeMapper.readTree(
    "{\"role\":\"USER\",\"role\":\"ADMIN\"}"
);
```

Feature này yêu cầu tree deserializer báo lỗi khi gặp duplicate key trong một tree object. Nó không thay thế parser-level `STRICT_DUPLICATE_DETECTION` cho mọi kiểu data binding.

Phân biệt:

| Feature | Phạm vi |
|---|---|
| `StreamReadFeature.STRICT_DUPLICATE_DETECTION` | Parser-level; phát hiện duplicate khi đọc token cho POJO, Map, tree và các target khác |
| `DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY` | Tree model; phát hiện duplicate trong quá trình tạo `JsonNode` |

Nếu ứng dụng chỉ đọc JSON thành POJO, bật `FAIL_ON_READING_DUP_TREE_KEY` không phải cách tổng quát để bảo vệ duplicate keys. Dùng parser-level strict duplicate detection.

### 6.1. Test duplicate key với POJO

```java
class DuplicateKeyTest {
    private final ObjectMapper mapper = new ObjectMapper(
        JsonFactory.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .build()
    );

    @Test
    void rejectsDuplicatePropertyDuringPojoBinding() {
        String input = """
            {
              "name": "An",
              "name": "Binh",
              "age": 20
            }
            """;

        assertThrows(JsonProcessingException.class,
            () -> mapper.readValue(input, UserRequest.class));
    }
}
```

### 6.2. Test duplicate key với tree

```java
@Test
void rejectsDuplicateKeyWhenReadingTree() {
    ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY);

    String input = "{\"role\":\"USER\",\"role\":\"ADMIN\"}";

    assertThrows(JsonProcessingException.class,
        () -> mapper.readTree(input));
}
```

Hai test xác nhận hai cơ chế khác nhau. Trong ứng dụng yêu cầu duplicate bị từ chối ở mọi target, nên cấu hình parser-level feature trên factory dùng chung.

## 7. Cú pháp mở rộng: single quotes

Một số file cấu hình hoặc payload do công cụ nội bộ tạo ra dùng dấu nháy đơn:

```text
{'name': 'An', 'age': 20}
```

Đây không phải JSON chuẩn. Jackson có thể chấp nhận nếu bật `JsonReadFeature.ALLOW_SINGLE_QUOTES`:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_SINGLE_QUOTES)
    .build();

ObjectMapper lenientMapper = new ObjectMapper(factory);
```

Chỉ bật khi input contract thực sự cho phép extension này. Nếu endpoint công khai tuyên bố nhận JSON chuẩn, hãy giữ strict mode và yêu cầu producer gửi double quotes.

## 8. Cú pháp mở rộng: tên field không có dấu nháy

Một số cấu hình viết key không quote:

```text
{name: "An", age: 20}
```

Bật `JsonReadFeature.ALLOW_UNQUOTED_FIELD_NAMES` để chấp nhận:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_UNQUOTED_FIELD_NAMES)
    .build();
```

Tên field không quote không thuộc JSON chuẩn. Cú pháp này có thể gây khác biệt khi chuyển dữ liệu sang parser khác hoặc qua API gateway. Chỉ bật cho nguồn dữ liệu legacy có kiểm soát.

## 9. Cú pháp mở rộng: comments

JSON chuẩn không cho phép comment. Jackson có thể bật Java-style comments:

```text
{
  // User profile
  "name": "An",
  /* age supplied by client */
  "age": 20
}
```

Bật:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
    .build();
```

Jackson cũng có `ALLOW_YAML_COMMENTS` cho comment bắt đầu bằng `#` trong một số dạng input:

```text
{
  "name": "An" # imported from legacy config
}
```

Không nhầm parser chấp nhận comment với JSON contract chuẩn. Nếu dữ liệu được gửi qua nhiều công cụ, comment có thể bị từ chối ở tầng khác.

## 10. Cú pháp mở rộng: trailing comma

JSON chuẩn không cho dấu phẩy sau phần tử cuối:

```text
{
  "name": "An",
  "age": 20,
}
```

Jackson có thể cho phép bằng `JsonReadFeature.ALLOW_TRAILING_COMMA`:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_TRAILING_COMMA)
    .build();
```

Feature này cho phép dấu phẩy cuối trong object hoặc array. Nó khác `ALLOW_MISSING_VALUES`: dấu phẩy thừa ở cuối không đồng nghĩa với một phần tử array bị thiếu ở giữa.

## 11. Cú pháp mở rộng: số có leading zero hoặc dạng không chuẩn

JSON number chuẩn không cho leading zero tùy ý:

```text
{"age": 020}
```

Có thể bật `JsonReadFeature.ALLOW_LEADING_ZEROS_FOR_NUMBERS` nếu phải đọc dữ liệu legacy. Nhưng việc cho phép leading zero có thể tạo khác biệt với parser khác và gây nhầm lẫn giữa số thập phân, mã định danh hoặc số có padding.

Một số extension khác có thể được bật riêng theo Jackson version:

| Feature | Ví dụ | Lưu ý |
|---|---|---|
| `ALLOW_NON_NUMERIC_NUMBERS` | `NaN`, `Infinity`, `-Infinity` | Không thuộc JSON number chuẩn; không phải mọi ngôn ngữ hỗ trợ cùng semantics |
| `ALLOW_LEADING_PLUS_SIGN_FOR_NUMBERS` | `+12` | Dấu cộng đầu không thuộc JSON number grammar |
| `ALLOW_LEADING_DECIMAL_POINT_FOR_NUMBERS` | `.5` | Thiếu phần nguyên |
| `ALLOW_TRAILING_DECIMAL_POINT_FOR_NUMBERS` | `12.` | Thiếu chữ số sau dấu chấm |
| `ALLOW_MISSING_VALUES` | `[1,,3]` | Parser có thể biểu diễn vị trí thiếu như null trong array |

Các feature mở rộng số được thêm theo từng release. Kiểm tra `JsonReadFeature` của Jackson Core version đang dùng trước khi cấu hình. Không bật tất cả chỉ để “dễ parse”; mỗi extension làm contract rộng hơn và có thể tạo kết quả khác giữa các ngôn ngữ.

### 11.1. Leading zero không phải numeric precision

`020` có thể được một hệ thống xem là số 20, hệ thống khác xem là chuỗi mã `020`, hoặc bị từ chối. Nếu giá trị là identifier có padding, nên khai báo field dạng string thay vì dựa vào permissive numeric parsing.

### 11.2. NaN và Infinity

`NaN` và `Infinity` không thuộc JSON number grammar. Nếu bật `ALLOW_NON_NUMERIC_NUMBERS`, hãy xác định kiểu Java đích và cách consumer khác biểu diễn chúng. Một số ngôn ngữ có float NaN/Infinity nhưng JSON serializer của chúng có thể từ chối hoặc thay bằng null.

Với API trao đổi đa ngôn ngữ, thường nên dùng null hoặc một trạng thái/representation tường minh thay vì đưa NaN/Infinity vào JSON mở rộng.

## 12. Cú pháp mở rộng: unescaped control characters và escape permissive

JSON string phải escape các control characters theo quy tắc JSON. Ví dụ newline bên trong string phải được ghi thành `\\n`, không phải ký tự xuống dòng thô:

```json
{"comment":"first line\nsecond line"}
```

Jackson có các feature permissive như `ALLOW_UNESCAPED_CONTROL_CHARS` hoặc `ALLOW_BACKSLASH_ESCAPING_ANY_CHARACTER` trong những version hỗ trợ. Chúng có thể giúp đọc file legacy nhưng làm parser chấp nhận input mà consumer strict khác từ chối.

Nếu phải bật, hãy giới hạn cho file import hoặc cấu hình migration. Không nên bật trên public API nếu không có yêu cầu tương thích cụ thể.

## 13. Gom các extension vào một mapper lenient riêng

Nếu phải đọc một nguồn legacy dùng nhiều extension, có thể tạo mapper riêng:

```java
JsonFactory legacyFactory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_SINGLE_QUOTES)
    .enable(JsonReadFeature.ALLOW_UNQUOTED_FIELD_NAMES)
    .enable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
    .enable(JsonReadFeature.ALLOW_TRAILING_COMMA)
    .build();

ObjectMapper legacyMapper = new ObjectMapper(legacyFactory)
    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Mapper này chấp nhận một số extension cú pháp nhưng vẫn yêu cầu chỉ có một root value. Đây là điểm quan trọng: **lenient syntax không đồng nghĩa với chấp nhận dữ liệu dư**.

Giữ mapper strict cho API và mapper lenient cho file legacy/import. Không thay đổi cấu hình của một mapper singleton theo từng request.

### 13.1. Strict và lenient có thể chia sẻ DTO

Hai mapper có thể bind cùng DTO:

```java
UserRequest strictValue = strictMapper.readValue(strictJson, UserRequest.class);
UserRequest legacyValue = legacyMapper.readValue(legacyJson, UserRequest.class);
```

DTO không cần biết input dùng single quotes hay comments. Cú pháp là trách nhiệm của parser; validation object là bước tiếp theo.

### 13.2. Không ghi output theo cú pháp mở rộng

Các `JsonReadFeature` điều khiển parser đọc input. Serializer Jackson vẫn tạo JSON theo representation chuẩn thông thường. Không nên coi việc reader chấp nhận extension là lý do để producer xuất extension đó ra ngoài.

## 14. Cấu hình strict để kiểm thử contract API

Một mapper strict cho endpoint nhận một JSON document có thể bật cả trailing token check và duplicate detection:

```java
JsonFactory strictFactory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper strictMapper = new ObjectMapper(strictFactory)
    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Ở đây:

- Parser mặc định từ chối cú pháp JSON mở rộng.
- `STRICT_DUPLICATE_DETECTION` từ chối tên key lặp trong một object.
- `FAIL_ON_TRAILING_TOKENS` từ chối root value hoặc token dư sau document.
- `FAIL_ON_UNKNOWN_PROPERTIES` từ chối property không có trong DTO.

Ba feature Databind/parser này giải quyết ba nhóm vấn đề riêng. Nếu DTO có `@JsonIgnoreProperties(ignoreUnknown = true)` hoặc `@JsonAnySetter`, chính sách unknown property có thể khác cho kiểu đó.

## 15. Kiểm thử cú pháp mở rộng bị từ chối ở strict mapper

Nên có test xác nhận strict mapper từ chối các extension mà contract không cho phép:

```java
class StrictJsonSyntaxTest {
    private final ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    @Test
    void rejectsSingleQuotedStrings() {
        assertThrows(JsonProcessingException.class,
            () -> mapper.readValue("{'name':'An','age':20}", UserRequest.class));
    }

    @Test
    void rejectsUnquotedFieldNames() {
        assertThrows(JsonProcessingException.class,
            () -> mapper.readValue("{name:'An'}", UserRequest.class));
    }

    @Test
    void rejectsTrailingComma() {
        assertThrows(JsonProcessingException.class,
            () -> mapper.readValue("{\"name\":\"An\",}", UserRequest.class));
    }

    @Test
    void rejectsComments() {
        assertThrows(JsonProcessingException.class,
            () -> mapper.readValue("{/*comment*/\"name\":\"An\"}", UserRequest.class));
    }
}
```

Các test chỉ xác nhận parser strict. Nếu project có một mapper khác do framework tạo, cần test chính mapper được inject trong controller hoặc integration test, không chỉ test một `new ObjectMapper()` độc lập.

## 16. Kiểm thử mapper lenient nhưng vẫn kiểm soát được dữ liệu dư

```java
class LegacyJsonSyntaxTest {
    private final ObjectMapper mapper = new ObjectMapper(
        JsonFactory.builder()
            .enable(JsonReadFeature.ALLOW_SINGLE_QUOTES)
            .enable(JsonReadFeature.ALLOW_UNQUOTED_FIELD_NAMES)
            .enable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
            .enable(JsonReadFeature.ALLOW_TRAILING_COMMA)
            .build()
    ).enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    @Test
    void acceptsConfiguredExtensions() throws Exception {
        UserRequest user = mapper.readValue(
            "{name:'An', age:20, /* old export */}",
            UserRequest.class
        );

        assertEquals("An", user.getName());
        assertEquals(20, user.getAge());
    }

    @Test
    void stillRejectsSecondRootValue() {
        String input = "{name:'An'} {name:'Binh'}";

        assertThrows(JsonProcessingException.class,
            () -> mapper.readValue(input, UserRequest.class));
    }
}
```

Mapper lenient chỉ chấp nhận các extension đã bật. Nó vẫn từ chối duplicate keys nếu parser-level duplicate detection được bật và vẫn từ chối trailing root value nếu `FAIL_ON_TRAILING_TOKENS` được bật.

## 17. Kiểm thử theo matrix thay vì chỉ một ví dụ

Một bộ test nên xác nhận từng điều kiện độc lập:

| Input case | Strict mapper | Mapper legacy có bật feature tương ứng |
|---|---|---|
| JSON chuẩn | Chấp nhận | Chấp nhận |
| Single quotes | Từ chối | Chấp nhận nếu bật `ALLOW_SINGLE_QUOTES` |
| Unquoted field name | Từ chối | Chấp nhận nếu bật `ALLOW_UNQUOTED_FIELD_NAMES` |
| Java comment | Từ chối | Chấp nhận nếu bật `ALLOW_JAVA_COMMENTS` |
| Trailing comma | Từ chối | Chấp nhận nếu bật `ALLOW_TRAILING_COMMA` |
| Duplicate key | Từ chối khi bật strict duplicate detection | Vẫn từ chối nếu feature được bật |
| Second root value | Từ chối khi bật `FAIL_ON_TRAILING_TOKENS` | Vẫn từ chối nếu feature được bật |
| Unknown property | Theo `FAIL_ON_UNKNOWN_PROPERTIES`/annotation | Theo cấu hình Databind riêng |
| Leading zero | Từ chối mặc định | Chấp nhận nếu bật feature tương ứng |

Không cần bật mọi extension trong một test. Test riêng giúp khi một cấu hình thay đổi, biết chính xác behavior nào đã thay đổi.

## 18. Rủi ro khi chấp nhận cú pháp mở rộng

Permissive parsing có thể hữu ích cho dữ liệu legacy, nhưng nó tạo ra một số rủi ro:

- **Khác biệt giữa parser:** gateway có thể parse strict trong khi backend parse lenient, hoặc ngược lại.
- **Signature/canonicalization mismatch:** các tầng có thể chuẩn hóa duplicate keys, whitespace hoặc number representation khác nhau trước khi ký/xác minh.
- **Schema drift:** producer dần phụ thuộc vào extension mà consumer khác không hỗ trợ.
- **Input ambiguity:** duplicate keys khiến first-wins/last-wins không thống nhất.
- **Khó debug:** payload không còn là JSON chuẩn nên nhiều công cụ format/validate không đọc được.
- **Tăng bề mặt input:** parser phải hỗ trợ nhiều cách viết hơn, làm hợp đồng và test phức tạp hơn.

Với payload liên quan authentication, authorization, payment hoặc signed request, nên ưu tiên strict syntax và duplicate detection. Nếu một hệ thống bắt buộc phải nhận legacy syntax, normalize ở một boundary được kiểm soát rồi chuyển sang representation chuẩn trước khi các tầng tiếp theo xử lý.

## 19. Normalization cho dữ liệu legacy

Một pipeline có thể chấp nhận input legacy ở bước đầu, sau đó chuyển thành object hoặc canonical JSON chuẩn:

```text
Legacy input
    |
    v
Lenient parser (chỉ các extension cần thiết)
    |
    v
JsonNode / DTO
    |
    v
Validation + normalization
    |
    v
Strict JSON output / internal model
```

Ví dụ:

```java
JsonNode tree = legacyMapper.readTree(legacyInput);
validateLegacyTree(tree);

String canonicalJson = strictMapper.writeValueAsString(tree);
```

Đây là normalization theo tree model của Jackson, không phải chuẩn canonical JSON cho chữ ký số. Nếu cần ký payload, cần một canonicalization standard được thống nhất riêng; `writeValueAsString()` không tự bảo đảm thứ tự field hoặc representation byte canonical cho mọi cấu hình.

## 20. Các feature cần nhớ

| Feature | Mục đích | Phạm vi |
|---|---|---|
| `DeserializationFeature.FAIL_ON_TRAILING_TOKENS` | Từ chối token/root value sau root đã bind | Sau khi đọc root value |
| `StreamReadFeature.STRICT_DUPLICATE_DETECTION` | Từ chối key trùng trong cùng object | Parser level, mọi target |
| `DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY` | Từ chối duplicate key khi tạo tree | Tree model |
| `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` | Từ chối key không map được vào DTO | Databind property resolution |
| `JsonReadFeature.ALLOW_SINGLE_QUOTES` | Cho phép single quotes | Parser syntax |
| `JsonReadFeature.ALLOW_UNQUOTED_FIELD_NAMES` | Cho phép tên field không quote | Parser syntax |
| `JsonReadFeature.ALLOW_JAVA_COMMENTS` | Cho phép `//` và `/* ... */` | Parser syntax |
| `JsonReadFeature.ALLOW_YAML_COMMENTS` | Cho phép comment kiểu `#` | Parser syntax |
| `JsonReadFeature.ALLOW_TRAILING_COMMA` | Cho phép dấu phẩy cuối | Parser syntax |
| `JsonReadFeature.ALLOW_LEADING_ZEROS_FOR_NUMBERS` | Cho phép số có leading zero | Parser number grammar |
| `JsonReadFeature.ALLOW_NON_NUMERIC_NUMBERS` | Cho phép NaN/Infinity | Parser number grammar |
| `JsonReadFeature.ALLOW_MISSING_VALUES` | Cho phép vị trí array bị bỏ trống | Parser array syntax |

Các `JsonReadFeature` được thêm qua các phiên bản Jackson Core khác nhau. Kiểm tra Javadoc của đúng version; không giả định mọi constant có mặt trong một dependency cũ. Các feature không được bật mặc định trong parser strict thông thường.

## 21. Lưu ý về phiên bản và API

`JsonReadFeature` là API parser hiện đại cho các extension của JSON. Trong các codebase cũ có thể thấy `JsonParser.Feature.ALLOW_*`; nhiều feature cũ đã được thay thế/đánh dấu deprecated để chuyển sang `JsonReadFeature`.

Với duplicate detection, code mới nên ưu tiên `StreamReadFeature.STRICT_DUPLICATE_DETECTION`. Các API cũ qua `JsonParser.Feature.STRICT_DUPLICATE_DETECTION` có thể vẫn tồn tại như compatibility alias tùy version.

Luôn đồng bộ `jackson-core`, `jackson-databind` và các module dataformat bằng BOM hoặc version tương thích. Nếu compiler không nhận ra một feature constant, hãy kiểm tra version runtime/compile thực tế thay vì tự thay bằng một tên gần giống.

## 22. Những lỗi thường gặp

**Nhầm trailing root value với unknown property.** `FAIL_ON_TRAILING_TOKENS` kiểm tra dữ liệu sau root; `FAIL_ON_UNKNOWN_PROPERTIES` kiểm tra key bên trong object.

**Cho rằng Jackson luôn từ chối duplicate keys.** Mặc định parser có thể chấp nhận và quá trình binding có thể ghi đè giá trị trước. Bật `STRICT_DUPLICATE_DETECTION` nếu key phải duy nhất.

**Chỉ bật `FAIL_ON_READING_DUP_TREE_KEY` rồi nghĩ POJO cũng được bảo vệ.** Feature đó dành cho tree model. Dùng parser-level duplicate detection cho mọi target.

**Bật `FAIL_ON_TRAILING_TOKENS` khi đọc sequence hợp lệ.** Nếu input cố ý chứa nhiều root values, dùng `MappingIterator`/stream reader và định nghĩa framing.

**Cho rằng bật single quotes cũng bật mọi extension khác.** Mỗi `JsonReadFeature` độc lập; bật đúng extension cần thiết.

**Coi JSON có comments hoặc trailing comma là JSON chuẩn.** Đây là extension. Document contract và consumer phải biết rõ.

**Dùng lenient mapper cho mọi endpoint.** Chế độ permissive làm tăng ambiguity. Tạo mapper riêng cho dữ liệu legacy.

**Dựa vào thứ tự first-wins/last-wins của duplicate keys.** Behavior giữa implementation có thể khác. Reject duplicate thay vì chọn một giá trị.

**Tự nối nhiều JSON root values nhưng không định nghĩa framing.** Dùng JSON array hoặc sequence protocol có boundary rõ.

**Cho rằng serialize lại bằng Jackson tạo canonical JSON.** Output thông thường không phải canonicalization standard cho chữ ký/hash. Dùng quy tắc canonical riêng nếu cần byte identity.

## 23. Quy trình kiểm thử input Jackson

1. Xác định endpoint nhận đúng một JSON document hay một sequence nhiều root values.
2. Bật `FAIL_ON_TRAILING_TOKENS` cho nơi chỉ chấp nhận một document.
3. Quyết định duplicate key có bị từ chối; bật `STRICT_DUPLICATE_DETECTION` nếu cần.
4. Nếu đọc `JsonNode`, cân nhắc thêm `FAIL_ON_READING_DUP_TREE_KEY` cho tree-specific protection hoặc dùng parser-level feature chung.
5. Xác định unknown property policy độc lập với trailing token và duplicate key.
6. Giữ parser strict cho JSON contract chuẩn.
7. Nếu phải đọc legacy syntax, bật từng `JsonReadFeature` cần thiết trên một factory/mapper riêng.
8. Không bật extension chỉ để che lỗi producer; ưu tiên sửa producer nếu có thể.
9. Viết test cho JSON chuẩn, trailing root value, garbage sau root, duplicate key ở root/nested object, unknown property và từng extension được phép/từ chối.
10. Chạy test bằng mapper thực tế được inject vào application/framework.
11. Với signed/security-sensitive input, kiểm tra duplicate handling và normalization nhất quán ở mọi tầng.
12. Ghi rõ parser policy trong API contract và giữ test fixture trong CI.

## Kết luận

Kiểm thử dữ liệu dư, duplicate keys và cú pháp mở rộng cần dùng đúng feature cho từng lớp. `FAIL_ON_TRAILING_TOKENS` bảo đảm một lần đọc chỉ nhận một root document; `StreamReadFeature.STRICT_DUPLICATE_DETECTION` từ chối key trùng trong object ở parser level; `FAIL_ON_READING_DUP_TREE_KEY` bổ sung kiểm tra dành cho tree model; còn `FAIL_ON_UNKNOWN_PROPERTIES` xử lý key không có trong DTO. Các cú pháp như single quotes, unquoted names, comments, trailing commas và leading zeros chỉ nên được chấp nhận bằng `JsonReadFeature` khi có yêu cầu legacy cụ thể. Giữ mapper strict cho API chuẩn, cô lập mapper lenient cho nguồn đặc biệt, và kiểm thử riêng từng trường hợp để tránh ambiguity giữa producer, gateway và consumer.

## Tài liệu tham khảo

- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259) — JSON grammar và khuyến nghị tên member trong object nên duy nhất.
- [Jackson Core JsonReadFeature](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/json/JsonReadFeature.html) — các parser feature cho cú pháp mở rộng.
- [Jackson Core StreamReadFeature](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/StreamReadFeature.html) — parser-level strict duplicate detection.
- [Jackson Databind DeserializationFeature](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/DeserializationFeature.html) — trailing token, unknown property và duplicate tree key features.
