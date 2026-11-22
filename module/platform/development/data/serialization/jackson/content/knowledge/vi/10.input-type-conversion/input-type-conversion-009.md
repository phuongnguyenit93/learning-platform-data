# Phân biệt cấu hình nghiêm ngặt và các tính năng cú pháp mở rộng

Jackson có thể đọc JSON theo quy tắc cú pháp chuẩn hoặc chấp nhận thêm một số dạng viết mở rộng để tương thích với dữ liệu cũ và các nguồn không tạo JSON chuẩn. Ngoài cú pháp, Jackson Databind còn có những tùy chọn quyết định có chấp nhận chuyển đổi kiểu đầu vào hay không, ví dụ chuỗi số thành số nguyên, một giá trị đơn thành danh sách một phần tử hoặc số thành ordinal của enum.

Hai nhóm cấu hình giải quyết hai vấn đề khác nhau:

- **Cấu hình parser** quyết định văn bản đầu vào có phải cú pháp JSON được chấp nhận hay không.
- **Cấu hình databind** quyết định token JSON hợp lệ được ánh xạ vào kiểu Java đích theo quy tắc nào.

Hiểu rõ hai lớp này giúp thiết kế ranh giới dữ liệu có thể dự đoán: dữ liệu không hợp lệ được từ chối ở đúng bước, còn ngoại lệ tương thích được bật có chủ đích và có phạm vi rõ ràng.

## 1. JSON chuẩn và cú pháp mở rộng

JSON chuẩn yêu cầu tên property và string dùng dấu ngoặc kép, không có comment, không có dấu phẩy thừa, không có dấu cộng hoặc số 0 thừa ở đầu number. Các literal chuẩn là true, false và null. Một JSON document biểu diễn một giá trị gốc.

Ví dụ JSON chuẩn:

```json
{
  "username": "an",
  "age": 21,
  "active": true,
  "roles": ["READER", "EDITOR"]
}
```

Một số nguồn dữ liệu lại tạo dạng viết tiện dụng nhưng không tuân theo cú pháp JSON chuẩn:

```text
{
  // User information
  username: 'an',
  age: 021,
  active: true,
}
```

Đoạn trên có comment, tên property không có dấu ngoặc kép, string dùng dấu nháy đơn, số có số 0 ở đầu và dấu phẩy thừa. Parser JSON chuẩn sẽ từ chối.

Jackson có các tính năng mở rộng để đọc một số dạng như vậy. Chúng không biến dữ liệu đó thành JSON chuẩn; chúng chỉ làm parser chấp nhận thêm cú pháp ngoài chuẩn.

## 2. Hai lớp cấu hình cần phân biệt

Luồng xử lý có thể hình dung:

```text
Văn bản đầu vào
      │
      ▼
Jackson Core: tokenizer/parser
      │
      │  Cú pháp có hợp lệ theo cấu hình parser?
      ▼
Các JSON token
      │
      ▼
Jackson Databind
      │
      │  Token có khớp kiểu Java?
      │  Có được phép coercion không?
      ▼
DTO / record / Map / List / scalar
      │
      ▼
Validation nghiệp vụ
```

Ví dụ:

- JSON có tên field không quote hoặc string dùng dấu nháy đơn có thể bị từ chối ở parser.
- JSON có property age là string "21" là JSON hợp lệ, nhưng Databind phải quyết định có cho phép chuyển nó thành Java int hay không.
- JSON có age bằng -5 có thể parse và bind thành công nhưng vẫn không hợp lệ về nghiệp vụ nếu tuổi phải không âm.

Không nên dùng một tùy chọn parser để giải quyết lỗi chuyển kiểu, hoặc dùng coercion để hợp thức hóa JSON sai cú pháp.

## 3. Cấu hình parser nghiêm ngặt

Jackson không bật các cú pháp mở rộng phổ biến theo mặc định. Có thể tạo JsonFactory nghiêm ngặt và truyền vào ObjectMapper:

```java
JsonFactory strictFactory = JsonFactory.builder()
    .build();

ObjectMapper strictMapper = new ObjectMapper(strictFactory);
```

Trong cấu hình hiện đại, các tính năng đọc mở rộng được biểu diễn bằng JsonReadFeature thuộc package com.fasterxml.jackson.core.json.

Mặc định, các feature mở rộng này bị tắt. Có thể tạo mapper nghiêm ngặt một cách tường minh để thể hiện chính sách của ứng dụng:

```java
JsonFactory strictFactory = JsonFactory.builder()
    .disable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
    .disable(JsonReadFeature.ALLOW_YAML_COMMENTS)
    .disable(JsonReadFeature.ALLOW_SINGLE_QUOTES)
    .disable(JsonReadFeature.ALLOW_UNQUOTED_FIELD_NAMES)
    .disable(JsonReadFeature.ALLOW_TRAILING_COMMA)
    .disable(JsonReadFeature.ALLOW_MISSING_VALUES)
    .build();

ObjectMapper strictMapper = new ObjectMapper(strictFactory);
```

Các lệnh disable ở đây làm rõ chính sách trong code review. Với mapper mới, đây cũng là trạng thái mặc định của các feature đọc mở rộng tương ứng.

### 3.1. Khi parser từ chối cú pháp không chuẩn

Ví dụ:

```java
String json = "{ username: 'an' }";

UserInput input = strictMapper.readValue(json, UserInput.class);
```

Parser sẽ ném lỗi vì username không phải tên property được đặt trong dấu ngoặc kép theo JSON chuẩn. Việc DTO có property username không làm cú pháp trên trở thành hợp lệ.

Một số lỗi parser thường thuộc nhóm JsonParseException hoặc lớp con của JsonProcessingException. Thông tin exception thường có vị trí dòng/cột hoặc vị trí byte/character giúp tìm đoạn văn bản gây lỗi.

### 3.2. Bật phát hiện key trùng lặp

JSON object không nên chứa nhiều property trùng tên. Ví dụ:

```json
{
  "role": "USER",
  "role": "ADMIN"
}
```

Nếu không bật kiểm tra, một số cách biểu diễn dữ liệu có thể giữ giá trị cuối cùng, khiến ý nghĩa payload không rõ ràng. Có thể bật phát hiện key trùng ở tầng parser:

```java
JsonFactory strictFactory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper strictMapper = new ObjectMapper(strictFactory);
```

Khi phát hiện tên property lặp trong cùng object, parser báo lỗi thay vì để ứng dụng tiếp tục với một giá trị không rõ ràng.

Phát hiện trùng lặp có thêm chi phí theo dõi tên field khi parse. Với payload từ bên ngoài, cấu hình này hữu ích khi tính rõ ràng và tính nhất quán quan trọng. Hãy đo hiệu năng nếu xử lý khối lượng dữ liệu rất lớn.

FAIL_ON_READING_DUP_TREE_KEY là một tùy chọn Databind riêng dành cho duplicate key khi đọc tree model. Nếu cần phát hiện trùng lặp ở cấp parser cho nhiều kiểu đọc khác nhau, STRICT_DUPLICATE_DETECTION thể hiện chính sách ở tầng phù hợp hơn.

## 4. Các tính năng cú pháp mở rộng của JsonReadFeature

Các feature sau cho phép parser chấp nhận những dạng viết tiện dụng ngoài JSON chuẩn. Chỉ bật feature mà nguồn dữ liệu thực sự cần.

| Feature | Dạng đầu vào được chấp nhận | Lưu ý |
| --- | --- | --- |
| ALLOW_JAVA_COMMENTS | Comment // và /* ... */ | Comment không thuộc JSON chuẩn |
| ALLOW_YAML_COMMENTS | Comment bắt đầu bằng # | Cú pháp này thường gặp trong file cấu hình |
| ALLOW_SINGLE_QUOTES | String dùng dấu nháy đơn | JSON chuẩn yêu cầu dấu nháy kép |
| ALLOW_UNQUOTED_FIELD_NAMES | Tên property không có dấu ngoặc kép | Không phải tên field JSON chuẩn |
| ALLOW_TRAILING_COMMA | Dấu phẩy trước dấu đóng object hoặc array | JSON chuẩn không cho phép |
| ALLOW_MISSING_VALUES | Phần tử array bị bỏ trống giữa hai dấu phẩy | Parser có thể biểu diễn phần tử thiếu như null |
| ALLOW_LEADING_ZEROS_FOR_NUMBERS | Number như 0012 | JSON chuẩn không cho phép số 0 thừa ở đầu |
| ALLOW_LEADING_PLUS_SIGN_FOR_NUMBERS | Number như +12 | JSON chuẩn không dùng dấu cộng đầu số |
| ALLOW_LEADING_DECIMAL_POINT_FOR_NUMBERS | Number như .5 | JSON chuẩn yêu cầu chữ số trước dấu thập phân |
| ALLOW_TRAILING_DECIMAL_POINT_FOR_NUMBERS | Number như 5. | JSON chuẩn yêu cầu chữ số sau dấu thập phân |
| ALLOW_NON_NUMERIC_NUMBERS | Giá trị như NaN, Infinity | Không phải JSON number chuẩn |
| ALLOW_BACKSLASH_ESCAPING_ANY_CHARACTER | Escape ký tự không nằm trong tập escape chuẩn | Có thể che giấu dữ liệu được tạo sai |
| ALLOW_UNESCAPED_CONTROL_CHARS | Control character trực tiếp trong string | JSON chuẩn yêu cầu escape các ký tự điều khiển |

Tên feature và mức hỗ trợ có thể phụ thuộc phiên bản Jackson Core. Hãy kiểm tra Javadoc của đúng release line mà dự án đang dùng.

### 4.1. Comment và dấu nháy đơn

Ví dụ input:

```text
{
  // Account
  'username': 'an',
  /* state */
  'active': true
}
```

Cấu hình parser:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
    .enable(JsonReadFeature.ALLOW_SINGLE_QUOTES)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Cấu hình này cho phép comment kiểu Java và string dùng dấu nháy đơn. Nó vẫn không tự bật các extension khác như tên field không có dấu ngoặc kép hoặc dấu phẩy thừa.

### 4.2. Tên field không có dấu ngoặc kép

Input:

```text
{
  username: "an",
  active: true
}
```

Bật riêng feature:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_UNQUOTED_FIELD_NAMES)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Chỉ nên dùng khi nguồn dữ liệu cũ thực sự tạo kiểu tên field này. Tên field có dấu cách, dấu gạch hoặc ký tự đặc biệt có thể không phù hợp với quy tắc identifier mà parser cho phép.

### 4.3. Dấu phẩy thừa và phần tử thiếu

Dấu phẩy thừa:

```text
{
  "username": "an",
  "active": true,
}
```

Cho phép bằng:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_TRAILING_COMMA)
    .build();
```

Phần tử array bị bỏ trống:

```text
[1, , 3]
```

Có thể được chấp nhận bằng ALLOW_MISSING_VALUES; vị trí thiếu được xử lý như một giá trị null trong quá trình đọc. Đây là extension dễ làm dữ liệu trở nên mơ hồ, vì vậy thường nên tránh đối với payload API.

### 4.4. Number không chuẩn

Các ví dụ sau không phải JSON number chuẩn:

```text
+12
0012
.5
5.
NaN
Infinity
```

Jackson có feature riêng cho từng dạng. Không nên bật tất cả chỉ vì một nguồn dữ liệu có một kiểu number bất thường. Đặc biệt, NaN và Infinity không thuộc tập giá trị number của JSON chuẩn và nhiều hệ thống JSON khác có thể không đọc được chúng.

### 4.5. Kết hợp một số extension có chủ đích

Nếu một file cấu hình legacy cần comment, dấu nháy đơn và dấu phẩy thừa, có thể cấu hình đúng ba feature:

```java
JsonFactory legacyFactory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
    .enable(JsonReadFeature.ALLOW_SINGLE_QUOTES)
    .enable(JsonReadFeature.ALLOW_TRAILING_COMMA)
    .build();

ObjectMapper legacyMapper = new ObjectMapper(legacyFactory);
```

Cấu hình này vẫn từ chối những extension chưa bật. Đó là cách kiểm soát tốt hơn việc bật mọi feature cú pháp mở rộng.

## 5. Phân biệt cú pháp mở rộng với coercion của Databind

Một payload có thể là JSON chuẩn nhưng vẫn cần chuyển đổi kiểu khi ánh xạ vào Java.

Ví dụ JSON hợp lệ:

```json
{
  "age": "21",
  "active": "true",
  "score": 9.5
}
```

DTO đích:

```java
public record UserInput(
    int age,
    boolean active,
    int score
) {}
```

Parser đọc được JSON này vì tất cả property đều có cú pháp chuẩn. Databind sau đó phải quyết định:

- Có chuyển string "21" thành int không?
- Có chuyển string "true" thành boolean không?
- Có chuyển số thập phân 9.5 thành int không, và nếu có thì làm tròn, cắt phần thập phân hay từ chối?

Đây là **coercion** — chuyển đổi giữa các hình dạng input JSON và kiểu Java đích. Nó khác với JsonReadFeature.

### 5.1. Các kiểu coercion thường gặp

| Input JSON | Kiểu Java đích | Quyết định cần kiểm soát |
| --- | --- | --- |
| String "21" | int | Cho phép parse chuỗi số hay từ chối? |
| Number 21.5 | int | Có cho phép mất phần thập phân? |
| String "true" | boolean | Có cho phép chuyển chuỗi thành boolean? |
| Scalar 21 | List<Integer> | Có tự bọc thành danh sách một phần tử? |
| Array [21] | int | Có tự mở array một phần tử thành scalar? |
| Number 1 | Enum | Có coi là ordinal của enum? |
| Empty string "" | Object/number | Có chuyển thành null hoặc giá trị rỗng? |

Không nên giả định mọi chuyển đổi đều được bật hoặc tắt giống nhau. Hành vi mặc định có thể phụ thuộc kiểu đích, feature, phiên bản Jackson và cấu hình framework.

## 6. Cấu hình Databind nghiêm ngặt

Có một số feature giúp từ chối input không phù hợp với kiểu Java.

```java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
    .disable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
    .disable(DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS)
    .build();
```

Ý nghĩa:

- FAIL_ON_UNKNOWN_PROPERTIES: từ chối property JSON không có trong kiểu Java đích. Feature này được bật mặc định ở một ObjectMapper Jackson thuần, nhưng cấu hình framework như Spring Boot có thể thay đổi mặc định.
- FAIL_ON_NULL_FOR_PRIMITIVES: từ chối JSON null cho Java primitive thay vì âm thầm dùng giá trị mặc định như 0 hoặc false.
- FAIL_ON_NUMBERS_FOR_ENUMS: từ chối ánh xạ number thành ordinal của enum.
- ACCEPT_SINGLE_VALUE_AS_ARRAY: khi tắt, không tự bọc scalar thành collection một phần tử.
- UNWRAP_SINGLE_VALUE_ARRAYS: khi tắt, không tự lấy phần tử duy nhất trong array để gán cho scalar.

Các feature trên không làm parser chấp nhận hoặc từ chối comment, dấu nháy đơn hay dấu phẩy thừa. Chúng tác động sau khi parser đã tạo token.

### 6.1. Unknown property

DTO:

```java
public record UserInput(
    String username,
    int age
) {}
```

JSON:

```json
{
  "username": "an",
  "age": 21,
  "admin": true
}
```

Nếu bật FAIL_ON_UNKNOWN_PROPERTIES, Jackson báo lỗi vì DTO không có property admin. Điều này giúp phát hiện field sai tên, client gửi thừa hoặc schema không đồng bộ.

Nếu consumer cần tương thích với producer có thể thêm field, có thể dùng JsonIgnoreProperties(ignoreUnknown = true) ở DTO cụ thể hoặc cấu hình phù hợp. Hãy quyết định theo hợp đồng, không nên tắt strictness toàn cục mà không hiểu hệ quả.

### 6.2. Null cho primitive

Với DTO:

```java
public record AccountInput(
    long id,
    boolean active
) {}
```

Payload:

```json
{
  "id": null,
  "active": null
}
```

Primitive Java không thể chứa null. Nếu FAIL_ON_NULL_FOR_PRIMITIVES bị tắt, Jackson có thể dùng giá trị mặc định cho primitive tùy ngữ cảnh. Điều này có thể khiến payload sai bị hiểu thành id = 0 hoặc active = false.

Bật feature giúp từ chối null rõ ràng. Nếu nghiệp vụ cần phân biệt không gửi field, gửi null và gửi giá trị, hãy cân nhắc wrapper type (Long, Boolean), creator configuration hoặc mô hình presence-aware.

### 6.3. Number thành enum

Giả sử:

```java
public enum AccountStatus {
    NEW,
    ACTIVE,
    SUSPENDED
}
```

Nếu nhận JSON:

```json
{"status": 1}
```

Một số cấu hình Jackson có thể ánh xạ số 1 thành enum ở ordinal tương ứng. Ordinal phụ thuộc thứ tự khai báo enum; thêm hoặc sắp xếp lại enum constant có thể làm thay đổi ý nghĩa.

Bật FAIL_ON_NUMBERS_FOR_ENUMS để yêu cầu client gửi tên hoặc dạng biểu diễn được định nghĩa rõ:

```json
{"status": "ACTIVE"}
```

Nếu API dùng code riêng như "A" hoặc "S", hãy định nghĩa mapping tường minh thay vì phụ thuộc ordinal.

## 7. Kiểm soát coercion chi tiết bằng CoercionConfig

Từ Jackson 2.12, Databind cung cấp cấu hình coercion chi tiết hơn thông qua CoercionConfig. Có thể chỉ định hành vi cho một nhóm kiểu Java và một dạng input cụ thể.

Các hành động thường dùng:

| CoercionAction | Ý nghĩa |
| --- | --- |
| Fail | Từ chối chuyển đổi |
| TryConvert | Thử chuyển đổi theo quy tắc của Jackson |
| AsNull | Ánh xạ input thành null |
| AsEmpty | Ánh xạ thành giá trị rỗng/mặc định phù hợp với kiểu |

Các dạng input có thể cấu hình gồm string, integer, float, boolean, array, object và các dạng rỗng tương ứng.

### 7.1. Từ chối string cho kiểu số nguyên

Ví dụ yêu cầu property integer phải là JSON number, không chấp nhận chuỗi "21":

```java
ObjectMapper mapper = new ObjectMapper();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
```

Với cấu hình này:

```json
{"age": 21}
```

được chấp nhận, còn:

```json
{"age": "21"}
```

bị từ chối khi bind vào kiểu integer.

Cần import các kiểu cấu hình:

```java
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.type.LogicalType;
```

### 7.2. Từ chối số thập phân cho integer

Nếu không muốn cắt phần thập phân:

```java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.Float,
        CoercionAction.Fail
    );
```

Khi đó JSON number 21.5 không được chuyển thành integer một cách âm thầm. Nếu hợp đồng cần số nguyên, client phải gửi 21.

### 7.3. Từ chối string cho boolean

```java
mapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
```

Cấu hình này yêu cầu boolean phải được gửi bằng literal JSON true hoặc false, không phải string "true" hoặc "false".

### 7.4. Cấu hình theo kiểu cụ thể hoặc logical type

coercionConfigFor(LogicalType) áp dụng cho nhóm kiểu logic, ví dụ integer, float, boolean, enum hoặc textual. Khi cần chính sách cho một class cụ thể, Jackson cũng có API cấu hình theo kiểu Java cụ thể ở các phiên bản hỗ trợ.

Không nên đặt một quy tắc coercion quá rộng nếu chỉ một field cần xử lý đặc biệt. Hãy cân nhắc DTO riêng, kiểu wrapper hoặc cấu hình ở phạm vi hẹp để tránh ảnh hưởng tới các property không liên quan.

## 8. Tính năng chấp nhận scalar/array

Hai feature dễ bị nhầm lẫn:

- ACCEPT_SINGLE_VALUE_AS_ARRAY: cho phép một scalar trở thành collection có một phần tử.
- UNWRAP_SINGLE_VALUE_ARRAYS: cho phép array có đúng một phần tử trở thành scalar.

Ví dụ DTO:

```java
public record SearchRequest(List<String> tags) {}
```

JSON array chuẩn:

```json
{"tags": ["java", "jackson"]}
```

Input scalar:

```json
{"tags": "java"}
```

Nếu bật ACCEPT_SINGLE_VALUE_AS_ARRAY, Jackson có thể ánh xạ "java" thành List.of("java"). Nếu tắt, kiểu input không khớp collection sẽ bị từ chối.

Chiều ngược lại, với property Java là String:

```java
public record LabelRequest(String label) {}
```

Payload:

```json
{"label": ["primary"]}
```

UNWRAP_SINGLE_VALUE_ARRAYS cho phép lấy "primary" từ array một phần tử. Nếu array có nhiều phần tử, mapping vẫn không phù hợp với scalar đích.

Đây là tiện ích tương thích cho nguồn dữ liệu không nhất quán. Với API mới, nên yêu cầu client gửi một hình dạng duy nhất để giảm mơ hồ.

## 9. Cấu hình mở rộng cú pháp và coercion không nên trộn lẫn

Có thể tạo một mapper chấp nhận cú pháp legacy nhưng vẫn giữ coercion nghiêm ngặt:

```java
JsonFactory legacyFactory = JsonFactory.builder()
    .enable(JsonReadFeature.ALLOW_JAVA_COMMENTS)
    .enable(JsonReadFeature.ALLOW_SINGLE_QUOTES)
    .enable(JsonReadFeature.ALLOW_TRAILING_COMMA)
    .build();

ObjectMapper legacySyntaxStrictBinding = new ObjectMapper(legacyFactory)
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
    .disable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
    .disable(DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS);

legacySyntaxStrictBinding.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Mapper này chấp nhận một số extension cú pháp nhưng vẫn từ chối unknown property, null cho primitive, enum ordinal và string chuyển thành integer theo quy tắc đã cấu hình.

Ngược lại, một mapper có thể đọc JSON chuẩn nhưng cho phép coercion. Hai trục độc lập, vì vậy hãy mô tả chính sách của ứng dụng theo từng trục thay vì gọi chung là strict hoặc lenient.

## 10. Chọn chính sách theo nguồn dữ liệu

| Nguồn dữ liệu | Parser | Databind | Lý do |
| --- | --- | --- | --- |
| Public REST API mới | JSON chuẩn | Nghiêm ngặt với unknown field và coercion quan trọng | Hợp đồng cần rõ ràng, lỗi được phát hiện sớm |
| File cấu hình legacy | Chỉ bật extension thực sự xuất hiện | Bind theo schema và kiểm tra kiểu | Hỗ trợ định dạng cũ trong phạm vi file đó |
| Webhook từ đối tác | Ưu tiên JSON chuẩn | Có thể bỏ qua unknown field nếu hợp đồng cho phép mở rộng | Producer có thể thêm field mới |
| Message nội bộ có schema version | JSON chuẩn | Ràng buộc theo version/schema | Lỗi schema cần được phát hiện, không nên bị che |
| Dữ liệu do người dùng nhập tự do | Parser chuẩn | Coercion có chọn lọc, validation rõ ràng | Tránh tự diễn giải input theo nhiều cách |
| Import dữ liệu cũ | Mapper tương thích riêng | Quy tắc chuyển đổi được ghi nhận | Có thể cần chuyển đổi rồi chuẩn hóa sang schema mới |

Một nguyên tắc hữu ích là **đặt mapper theo ranh giới dữ liệu**. File cấu hình legacy có thể dùng factory riêng; API công khai dùng mapper nghiêm ngặt; message có version schema dùng cấu hình tương ứng. Không nên bật extension trên mapper toàn cục chỉ để đọc một file cũ.

## 11. Kiểm thử cấu hình nghiêm ngặt và mở rộng

Cần kiểm thử cả hai chiều: input hợp lệ phải đọc được, input nằm ngoài chính sách phải bị từ chối.

### 11.1. Test cú pháp chuẩn và cú pháp mở rộng

```java
@Test
void strictParserRejectsSingleQuotedString() {
    ObjectMapper mapper = new ObjectMapper();

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readTree("{'name': 'An'}")
    );
}

@Test
void relaxedParserAcceptsSingleQuotedString() throws Exception {
    JsonFactory factory = JsonFactory.builder()
        .enable(JsonReadFeature.ALLOW_SINGLE_QUOTES)
        .build();

    ObjectMapper mapper = new ObjectMapper(factory);

    JsonNode node = mapper.readTree("{'name': 'An'}");

    assertEquals("An", node.path("name").asText());
}
```

### 11.2. Test unknown property

```java
@Test
void strictBindingRejectsUnknownProperty() {
    ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

    String json = """
        {"username": "an", "unexpected": true}
        """;

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue(json, UserInput.class)
    );
}
```

### 11.3. Test coercion string sang integer

```java
@Test
void rejectsStringForIntegerProperty() {
    ObjectMapper mapper = new ObjectMapper();

    mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(
            CoercionInputShape.String,
            CoercionAction.Fail
        );

    String json = """
        {"age": "21"}
        """;

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue(json, UserInput.class)
    );
}
```

### 11.4. Test duplicate key

```java
@Test
void rejectsDuplicateObjectKeys() {
    JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

    ObjectMapper mapper = new ObjectMapper(factory);

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readTree("""
            {"role": "USER", "role": "ADMIN"}
            """)
    );
}
```

### 11.5. Test theo ma trận input

Với mỗi DTO quan trọng, tạo test cho:

- Property đúng kiểu.
- Property sai kiểu.
- Property không xuất hiện.
- Property có explicit null.
- Property không được nhận diện.
- String số và number thập phân khi đích là integer.
- Scalar khi đích là List.
- Array một phần tử khi đích là scalar.
- JSON có comment, dấu nháy đơn hoặc trailing comma.
- Object có key trùng lặp.

Các test này giúp chính sách được ghi lại bằng hành vi thực tế thay vì phụ thuộc vào mặc định của một phiên bản thư viện.

## 12. Lưu ý khi tích hợp Spring Boot

Spring Boot có thể cấu hình ObjectMapper thông qua auto-configuration, builder customizer, module trên classpath và property riêng. Vì vậy, một mapper tạo bằng new ObjectMapper() trong unit test có thể không giống mapper xử lý HTTP request thực tế.

Khi cấu hình strictness trong Spring Boot:

1. Kiểm tra version Jackson do Spring Boot dependency management chọn.
2. Xác định bean ObjectMapper nào được HTTP message converter sử dụng.
3. Đặt parser feature trên JsonFactory của mapper/builder tương ứng.
4. Đặt Databind feature và coercion policy trên đúng mapper.
5. Kiểm tra cấu hình có ảnh hưởng tới endpoint khác hay không.
6. Viết integration test gửi HTTP body thực tế để xác nhận status code, error response và Content-Type.

Không nên thay bean mapper toàn cục nếu chỉ một endpoint hoặc một nguồn file cần cú pháp mở rộng. Có thể dùng reader/mapper riêng ở service boundary để giới hạn phạm vi tương thích.

Nếu dự án có nhiều ObjectMapper, hãy đặt tên và mục đích rõ ràng, ví dụ mapper cho public API, mapper cho file legacy hoặc mapper cho event version cụ thể.

## 13. Lỗi thường gặp và cách định vị

| Dấu hiệu | Lớp xử lý | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- | --- |
| Parser báo lỗi ở dấu nháy đơn | Jackson Core | ALLOW_SINGLE_QUOTES đang tắt | Kiểm tra JsonFactory và feature đọc |
| Parser không chấp nhận comment | Jackson Core | Comment không thuộc JSON chuẩn | Xác nhận nguồn có thật sự cần comment không |
| Lỗi ở dấu phẩy trước dấu đóng object hoặc array | Jackson Core | Trailing comma không được bật | Kiểm tra ALLOW_TRAILING_COMMA |
| String "21" không bind vào int | Databind | Coercion string sang integer bị từ chối | Kiểm tra CoercionConfig và kiểu đích |
| 21.5 không bind vào int | Databind | Float-to-integer coercion bị từ chối hoặc feature liên quan | Kiểm tra CoercionConfig |
| Unknown property gây lỗi | Databind | FAIL_ON_UNKNOWN_PROPERTIES bật | Kiểm tra schema và chính sách unknown field |
| Null không bind vào primitive | Databind | FAIL_ON_NULL_FOR_PRIMITIVES bật | Dùng wrapper nếu null có ý nghĩa |
| Number không bind vào enum | Databind | FAIL_ON_NUMBERS_FOR_ENUMS bật | Gửi enum name/code theo hợp đồng |
| Scalar không bind vào List | Databind | ACCEPT_SINGLE_VALUE_AS_ARRAY tắt | Gửi array chuẩn hoặc bật riêng nếu cần tương thích |
| Duplicate key gây lỗi | Parser | STRICT_DUPLICATE_DETECTION bật | Xác định producer tạo key trùng |

Khi debug, hãy đọc loại exception và vị trí lỗi. Nếu lỗi xuất hiện trước khi có DTO/property path, thường là parser. Nếu có thông tin kiểu đích và property gây lỗi, thường là Databind. Nếu Jackson mapping thành công nhưng dữ liệu bị từ chối, kiểm tra validation nghiệp vụ.

## 14. Quy trình xây dựng cấu hình phù hợp

Khi tích hợp một nguồn dữ liệu mới:

### Bước 1 — Xác định định dạng nguồn

Kiểm tra payload thực tế. Đó có phải JSON chuẩn không? Có comment, dấu nháy đơn, field không quote, dấu phẩy thừa hoặc number không chuẩn không?

### Bước 2 — Giữ parser chuẩn làm điểm xuất phát

Dùng JsonFactory mặc định. Chỉ bật từng JsonReadFeature nếu có ví dụ đầu vào thực tế yêu cầu nó.

### Bước 3 — Xác định schema Java đích

Chọn DTO/record, Map/List hoặc JsonNode. Khai báo generic type đầy đủ để Jackson biết cấu trúc collection lồng nhau.

### Bước 4 — Quyết định chính sách coercion

Với từng property, quyết định có chấp nhận string số, float thành integer, null cho primitive, enum ordinal hoặc scalar thành array không.

### Bước 5 — Quyết định unknown field và duplicate key

Xác định producer có thể mở rộng schema không. Với payload cần chính xác, bật unknown-property failure và duplicate detection. Với webhook mở rộng, có thể bỏ qua unknown field ở DTO cụ thể.

### Bước 6 — Viết test ranh giới

Test các payload đúng, sai cú pháp, sai kiểu, null, missing, unknown field và key trùng. Kiểm thử trên đúng mapper được ứng dụng sử dụng.

### Bước 7 — Cô lập cấu hình tương thích

Nếu một nguồn legacy cần cú pháp mở rộng, dùng mapper/factory riêng cho nguồn đó. Sau khi đọc, có thể chuẩn hóa thành DTO hoặc JSON chuẩn để các lớp còn lại xử lý thống nhất.

## 15. Bài thực hành tổng hợp

Tạo DTO:

```java
public record UserInput(
    String username,
    int age,
    boolean active,
    AccountStatus status
) {}

public enum AccountStatus {
    NEW,
    ACTIVE,
    SUSPENDED
}
```

Thực hiện các trường hợp:

1. Đọc JSON chuẩn với property được quote và string được double quote.
2. Thử JSON có comment và xác nhận mapper chuẩn từ chối.
3. Bật ALLOW_JAVA_COMMENTS và xác nhận parser đọc được.
4. Thử single quote, unquoted field name và trailing comma từng trường hợp riêng.
5. Thử age là string "21" và number 21.5.
6. Cấu hình CoercionConfig để từ chối string/float cho integer.
7. Thử active là string "true" rồi chuyển sang boolean literal.
8. Thử status là number ordinal và bật FAIL_ON_NUMBERS_FOR_ENUMS.
9. Thêm field admin không có trong DTO và kiểm tra unknown-property policy.
10. Thêm duplicate key status và bật strict duplicate detection.
11. So sánh kết quả với mapper dùng cho HTTP trong Spring Boot.
12. Viết bảng chính sách ghi rõ nguồn nào được phép dùng cú pháp mở rộng và những coercion nào được chấp nhận.

Bài thực hành hoàn thành khi có thể chỉ ra lỗi phát sinh ở parser, Databind hay validation, và giải thích được từng feature thay đổi hành vi nào.

## 16. Nguyên tắc ghi nhớ

- JSON chuẩn không có comment, single quote, unquoted field name, trailing comma, leading plus hoặc leading zero tùy tiện.
- JsonReadFeature thuộc Jackson Core và kiểm soát cú pháp đầu vào.
- DeserializationFeature và CoercionConfig thuộc Databind, kiểm soát mapping và chuyển kiểu.
- Một JSON document có thể parse thành công nhưng vẫn không bind được vào kiểu Java đích.
- FAIL_ON_UNKNOWN_PROPERTIES, FAIL_ON_NULL_FOR_PRIMITIVES và FAIL_ON_NUMBERS_FOR_ENUMS giúp ràng buộc input theo schema.
- ACCEPT_SINGLE_VALUE_AS_ARRAY và UNWRAP_SINGLE_VALUE_ARRAYS là các tiện ích coercion, không phải cú pháp JSON mở rộng.
- STRICT_DUPLICATE_DETECTION giúp từ chối object có key trùng.
- Chỉ bật extension mà nguồn dữ liệu thực sự cần; tránh bật toàn bộ trên mapper toàn cục.
- Test trên đúng ObjectMapper/JsonFactory của ứng dụng, nhất là khi Spring Boot có auto-configuration.
- Parser, Databind và validation là ba bước khác nhau; xử lý lỗi ở đúng tầng.

Khi phân biệt cấu hình nghiêm ngặt và cú pháp mở rộng, hãy bắt đầu bằng JSON chuẩn, quyết định riêng parser feature và coercion policy, rồi xác nhận chính sách bằng test trên đúng ranh giới dữ liệu.
