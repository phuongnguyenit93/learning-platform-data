# Giới hạn độ dài chuỗi, tên thuộc tính và số

JSON đầu vào có thể chứa một chuỗi rất dài, một tên thuộc tính bất thường, một số có hàng triệu chữ số hoặc cấu trúc lồng nhau quá sâu. Dù JSON đúng cú pháp, những giá trị này vẫn có thể tiêu tốn nhiều bộ nhớ và CPU trong lúc parser giải mã token hoặc Databind tạo object Java.

Jackson Core cung cấp **`StreamReadConstraints`** để giới hạn một số đặc điểm của dữ liệu ngay trong quá trình đọc token. Các giới hạn quan trọng gồm độ dài string value, độ dài property name, độ dài numeric token và độ sâu lồng nhau. Ứng dụng có thể cấu hình chúng trên `JsonFactory` được dùng bởi `ObjectMapper`.

Các giới hạn parser là một lớp bảo vệ đầu vào. Chúng không thay thế giới hạn kích thước HTTP request, validation nghiệp vụ hay JSON Schema. Mỗi lớp kiểm soát một loại rủi ro khác nhau: parser giới hạn các cấu trúc tốn tài nguyên trong lúc đọc; transport giới hạn tổng dữ liệu nhận; schema và Bean Validation kiểm tra dữ liệu có ý nghĩa gì đối với ứng dụng.

## 1. Vì sao phải giới hạn đầu vào JSON?

Một request có thể nhỏ về số lượng property nhưng chứa một giá trị cực lớn:

```json
{
  "comment": "...một chuỗi có hàng chục triệu ký tự..."
}
```

Hoặc chứa tên property dài bất thường:

```json
{
  "a-very-long-property-name-that-is-not-part-of-the-contract": "value"
}
```

Hoặc một numeric token rất dài:

```json
{
  "accountNumber": 12345678901234567890123456789012345678901234567890
}
```

Những đầu vào này có thể làm parser cần buffer lớn, tăng chi phí giải mã và chuyển đổi kiểu, hoặc làm ứng dụng giữ nhiều dữ liệu hơn dự kiến. Kẻ gửi không cần tạo một JSON document sai cú pháp; chỉ cần một document hợp lệ nhưng chứa các token quá lớn cũng có thể gây áp lực tài nguyên.

Các rủi ro chính:

- **Chuỗi dài:** parser cần buffer để giải mã nội dung; Databind có thể tạo thêm `String` và object phụ thuộc.
- **Tên property dài:** tên field được giữ và so khớp với property metadata hoặc map key; tên quá lớn có thể làm tăng chi phí bộ nhớ và xử lý.
- **Số dài:** parser phải nhận diện token số; `BigInteger`/`BigDecimal` có thể cần thêm tài nguyên để chuyển đổi giá trị.
- **Cấu trúc lồng sâu:** parser và code xử lý có thể tiêu tốn stack/bộ nhớ khi đi qua nhiều object/array lồng nhau.
- **Quá nhiều token:** document có thể chứa rất nhiều property hoặc phần tử nhỏ, dù mỗi token riêng lẻ đều ngắn.

Giới hạn hợp lý giúp parser từ chối input bất thường sớm hơn, trước khi toàn bộ dữ liệu được bind vào domain object.

## 2. StreamReadConstraints là gì?

`StreamReadConstraints` thuộc Jackson Core. Đây là cấu hình giới hạn được gắn với `JsonFactory` (hoặc token stream factory tương ứng). Parser do factory tạo ra sử dụng các giới hạn này khi đọc dữ liệu.

Các giới hạn liên quan trực tiếp đến bài học:

| API | Đối tượng được giới hạn | Ý nghĩa |
|---|---|---|
| `maxStringLength(int)` | String value | Giới hạn độ dài của giá trị JSON dạng string |
| `maxNameLength(int)` | Object property name | Giới hạn độ dài tên thuộc tính trong JSON object |
| `maxNumberLength(int)` | Numeric token | Giới hạn độ dài biểu diễn của số nguyên/số thập phân trong JSON |
| `maxNestingDepth(int)` | Object/array lồng nhau | Giới hạn độ sâu cấu trúc JSON |
| `maxDocumentLength(long)` | Toàn bộ document | Giới hạn độ dài đầu vào cho một document, nếu phiên bản hỗ trợ |
| `maxTokenCount(long)` | Tổng số token | Giới hạn số token được đọc, nếu phiên bản hỗ trợ |

`StreamReadConstraints` được giới thiệu trong Jackson Core 2.15. `maxNameLength` và các giới hạn document length có từ dòng 2.16. `maxTokenCount` được bổ sung ở dòng 2.18. Khi dùng phiên bản cũ hơn, hãy kiểm tra API của đúng phiên bản thay vì sao chép toàn bộ builder options từ bản mới.

### 2.1. Cấu hình trên JsonFactory

Ví dụ với Jackson 2.16 trở lên:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(100)
    .maxStringLength(1_000_000)
    .maxNameLength(256)
    .maxNumberLength(128)
    .maxDocumentLength(5_000_000L)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Các con số trên chỉ là ví dụ để minh họa cách cấu hình. Giá trị phù hợp phụ thuộc kích thước request hợp lệ, kiểu dữ liệu, giới hạn hạ tầng và workload thực tế. Không nên sao chép chúng vào production mà không đo payload hợp lệ của ứng dụng.

`ObjectMapper` sử dụng factory đã cấu hình, do đó parser được tạo thông qua mapper sẽ nhận các giới hạn tương ứng. Nếu một phần khác của ứng dụng tạo `JsonFactory` độc lập hoặc dùng mapper khác, phần đó có thể có chính sách khác.

### 2.2. Tạo mapper bằng JsonMapper builder

Có thể dùng builder:

```java
JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = JsonMapper.builder(factory).build();
```

Hoặc với cấu hình đơn giản, `new ObjectMapper(factory)` là đủ. Điểm quan trọng là `StreamReadConstraints` phải được gắn vào factory thực sự dùng để tạo parser.

## 3. Giới hạn độ dài string value

`maxStringLength()` giới hạn độ dài của giá trị JSON dạng string. Ví dụ:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxStringLength(64 * 1024)
    .build();
```

Với cấu hình này, parser sẽ từ chối string value quá lớn theo giới hạn đã đặt. Ví dụ JSON:

```json
{
  "description": "một nội dung văn bản rất dài..."
}
```

Nếu nội dung vượt ngưỡng, lỗi phát sinh trong quá trình parse token, trước khi Jackson hoàn tất việc bind DTO.

### 3.1. Giới hạn này áp dụng cho từng string value

`maxStringLength` giới hạn một string token. Nó không phải tổng dung lượng của tất cả string trong document và không phải giới hạn tổng request body.

Ví dụ, document có 10.000 string, mỗi string dài 100 ký tự, vẫn có thể vượt tổng dung lượng mong muốn dù không string nào vượt `maxStringLength`. Muốn giới hạn tổng dữ liệu, cần giới hạn document/request ở lớp phù hợp và cân nhắc giới hạn token count.

### 3.2. String value khác property name

Trong JSON:

```json
{
  "description": "nội dung mô tả"
}
```

- `description` là property name.
- `nội dung mô tả` là string value.

`maxStringLength` áp dụng cho string value. Tên property có giới hạn riêng bằng `maxNameLength()` ở các phiên bản hỗ trợ.

Không nên giả định giảm `maxStringLength` sẽ tự động giới hạn tên field. Cần cấu hình cả hai khi ứng dụng cần kiểm soát riêng.

### 3.3. Đơn vị và tính chính xác của giới hạn

Jackson mô tả các giới hạn độ dài theo input unit của nguồn đọc, có thể là byte hoặc ký tự tùy parser/source. Với `InputStream`, parser đọc byte; với `Reader` hoặc `String`, parser đọc ký tự.

Các giới hạn string/name được áp dụng khi parser cần mở rộng buffer nội bộ, vì vậy chúng là giới hạn bảo vệ thực tế chứ không phải phép đo chính xác tuyệt đối tại từng ký tự. Một giá trị hơi vượt ngưỡng có thể vẫn được chấp nhận tùy thời điểm buffer tăng; giá trị lớn hơn đáng kể sẽ bị từ chối. Không dùng chúng thay cho một bộ đếm byte chính xác ở tầng HTTP.

### 3.4. Đừng đặt giới hạn string quá thấp

Giới hạn phải phù hợp với dữ liệu hợp lệ. Ví dụ, nếu ứng dụng nhận mô tả sản phẩm, nội dung rich text hoặc một trường base64, giới hạn 1 KB có thể làm hỏng request hợp lệ.

Hãy phân loại field:

- Tên, mã định danh, trạng thái: thường cần giới hạn ngắn.
- Comment, mô tả, ghi chú: có thể cần giới hạn lớn hơn.
- Nội dung nhúng/base64: có thể cần giới hạn riêng hoặc truyền qua endpoint/file flow chuyên biệt.

Parser constraint áp dụng ở mức token và không biết field nào là `description` hay `avatar`. Nếu các field có giới hạn khác nhau, dùng JSON Schema hoặc Bean Validation bổ sung sau parser; nếu cần từ chối trước khi materialize một field cụ thể, cân nhắc custom streaming parser/endpoint chuyên biệt.

## 4. Giới hạn tên thuộc tính bằng maxNameLength

Tên property cũng là dữ liệu đầu vào. Một object JSON có thể chứa key rất dài:

```json
{
  "customer_metadata_extension_name_with_unexpected_length": "value"
}
```

`maxNameLength()` giới hạn độ dài tên property mà parser đọc:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNameLength(256)
    .build();
```

Giới hạn này hữu ích cho DTO thông thường lẫn cấu trúc động như `Map<String, Object>` hoặc `@JsonAnySetter`, nơi tên key có thể không được giới hạn bởi danh sách property cố định.

### 4.1. Phiên bản hỗ trợ

`StreamReadConstraints` xuất hiện từ Jackson Core 2.15, nhưng `maxNameLength()` được bổ sung trong 2.16. Nếu project dùng Jackson 2.15, có thể cấu hình giới hạn string, number và nesting depth nhưng không có builder method `maxNameLength()`.

Với 2.15, nếu cần giới hạn key cụ thể, cân nhắc nâng Jackson Core lên phiên bản tương thích có hỗ trợ `maxNameLength`, hoặc kiểm tra tên sau khi parser đọc field bằng một streaming layer riêng. Không nên gọi một API không tồn tại rồi giả định dependency management sẽ tự chọn version mới.

### 4.2. maxNameLength không giới hạn số lượng property

Giới hạn tên property chỉ kiểm soát độ dài từng key. Nó không đặt giới hạn số key trong object.

Ví dụ một document có thể có hàng trăm nghìn key ngắn:

```json
{
  "k1": 1,
  "k2": 2,
  "k3": 3
}
```

Mỗi key đều ngắn nhưng tổng số token và tổng kích thước document vẫn lớn. Để kiểm soát số lượng phần tử/property, cân nhắc:

- `maxTokenCount()` trong Jackson Core 2.18 trở lên.
- `maxProperties` trong JSON Schema.
- Giới hạn kích thước request/document ở transport hoặc parser.
- Logic streaming đếm số field nếu cần chính sách riêng cho một object.

### 4.3. Giới hạn tên không thay thế allowlist property

Một key dài 20 ký tự vẫn có thể là key không được phép như `adminOverride`. `maxNameLength` chỉ giới hạn kích thước, không xác định tên nào hợp lệ.

Để kiểm soát tập field:

- Giữ `FAIL_ON_UNKNOWN_PROPERTIES` nếu DTO phải từ chối field lạ.
- Dùng JSON Schema `additionalProperties: false` cho contract JSON.
- Dùng allowlist trong custom `@JsonAnySetter` nếu chấp nhận một số key động.
- Không bind trực tiếp request Map vào entity nhạy cảm mà thiếu kiểm soát field.

## 5. Giới hạn độ dài numeric token

`maxNumberLength()` giới hạn độ dài biểu diễn của một numeric token JSON:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNumberLength(128)
    .build();
```

Ví dụ một số có hàng nghìn chữ số hoặc phần exponent rất dài có thể bị từ chối khi parser đọc token.

JSON number có thể dùng dạng nguyên hoặc thập phân/exponent:

```json
{
  "integerValue": 123456789,
  "decimalValue": 125.50,
  "scientificValue": 1.25e6
}
```

`maxNumberLength` giới hạn độ dài biểu diễn token, không phải giá trị số lớn nhất theo nghiệp vụ.

### 5.1. Độ dài token khác numeric range

Hai kiểm tra cần được tách riêng:

- **Token length:** số ký tự/byte tạo nên literal số trong JSON; parser constraint kiểm soát.
- **Numeric range/precision:** giá trị sau khi parse có nằm trong giới hạn nghiệp vụ và kiểu đích hay không; schema, Bean Validation hoặc logic domain kiểm soát.

Ví dụ `999999999999999999999999` có token tương đối ngắn nhưng có thể vượt giới hạn của một field `int`. Ngược lại, `1e100000` có biểu diễn ngắn nhưng magnitude rất lớn. Chỉ đặt `maxNumberLength` không bảo đảm số nằm trong khoảng nghiệp vụ.

### 5.2. Kiểm tra range sau khi deserialize

Với kiểu Java số nguyên:

```java
public class TransferRequest {
    @NotNull
    @Positive
    @Max(1_000_000)
    private Long amount;
}
```

Với số thập phân:

```java
public class PriceRequest {
    @NotNull
    @DecimalMin("0.00")
    @DecimalMax("1000000.00")
    @Digits(integer = 10, fraction = 2)
    private BigDecimal price;
}
```

Các constraint này kiểm tra giá trị Java sau khi deserialize. JSON Schema cũng có `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf` và các keyword tương ứng để kiểm tra document.

### 5.3. Cẩn thận với BigInteger và BigDecimal

`BigInteger` và `BigDecimal` hỗ trợ giá trị lớn hơn các kiểu primitive, nhưng không nên xem khả năng biểu diễn lớn là lý do để chấp nhận mọi số đầu vào.

- Giới hạn token length để tránh literal quá dài.
- Giới hạn range/precision theo domain.
- Xác định có chấp nhận exponent notation hay không.
- Tránh chuyển sang `double` nếu cần độ chính xác thập phân tài chính.
- Không dùng ordinal hoặc numeric coercion tùy tiện cho các field có contract chặt.

Nếu field chỉ nhận số nguyên nhỏ, dùng kiểu đích phù hợp và constraint range. Nếu field là tiền, thường dùng `BigDecimal` cùng precision/scale rõ ràng.

## 6. Giới hạn độ sâu lồng nhau

JSON có thể lồng object/array rất sâu:

```json
{
  "a": {
    "b": {
      "c": {
        "d": {
          "value": 1
        }
      }
    }
  }
}
```

`maxNestingDepth()` giới hạn số cấp cấu trúc lồng nhau:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(100)
    .build();
```

Giới hạn này bảo vệ parser và các bước xử lý downstream khỏi document có nesting bất thường. Giá trị phù hợp tùy schema thực tế; API request thông thường thường không cần hàng trăm hoặc hàng nghìn cấp lồng nhau.

Nesting depth không phải số lượng phần tử. Một array phẳng có thể chứa rất nhiều phần tử mà depth thấp; một object lồng sâu có thể có ít token nhưng depth lớn. Cần kiểm soát cả hai dạng nếu rủi ro yêu cầu.

## 7. Giới hạn toàn document và token count

Các phiên bản Jackson Core mới hơn cung cấp thêm giới hạn toàn document và tổng số token.

### 7.1. maxDocumentLength

Trong các phiên bản có API này (từ dòng 2.16), có thể giới hạn độ dài document:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxDocumentLength(5_000_000L)
    .build();
```

Giới hạn document giúp ngăn một tài liệu có quá nhiều nội dung dù từng string, name và number đều nằm trong giới hạn riêng. Đơn vị phụ thuộc input source (byte hoặc ký tự). Kiểm tra tài liệu phiên bản Jackson đang dùng để hiểu chính xác semantics.

### 7.2. maxTokenCount

Từ Jackson Core 2.18, builder hỗ trợ giới hạn tổng số token:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxTokenCount(100_000L)
    .build();
```

Token là một đơn vị parser như object start/end, array start/end, field name, string, number, boolean hoặc null. Giới hạn token count có thể giúp kiểm soát document có quá nhiều property/phần tử nhỏ.

Giá trị `0` hoặc số âm có nghĩa không giới hạn đối với API token count trong các phiên bản hỗ trợ. Chỉ dùng giới hạn này khi version của Jackson Core cung cấp method tương ứng.

### 7.3. Không nhầm các giới hạn

| Giới hạn | Bảo vệ trước | Không bảo vệ trực tiếp trước |
|---|---|---|
| `maxStringLength` | Một string value quá dài | Tổng body quá lớn hoặc quá nhiều string ngắn |
| `maxNameLength` | Một property name quá dài | Quá nhiều property hoặc key không được phép |
| `maxNumberLength` | Một numeric literal quá dài | Giá trị số vượt range dù token ngắn |
| `maxNestingDepth` | Object/array lồng quá sâu | Array phẳng có quá nhiều phần tử |
| `maxDocumentLength` | Document quá dài | Quy tắc nghiệp vụ của từng field |
| `maxTokenCount` | Quá nhiều token nhỏ | Range/format của giá trị riêng lẻ |

Kết hợp nhiều giới hạn sẽ tạo lớp phòng vệ tốt hơn một giới hạn đơn lẻ.

## 8. Chọn giới hạn phù hợp với contract

Không có một bộ số dùng được cho mọi API. Cần chọn theo kích thước dữ liệu hợp lệ và cách client sử dụng endpoint.

Ví dụ một endpoint tạo hồ sơ có thể dùng:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(64)
    .maxStringLength(128 * 1024)
    .maxNameLength(128)
    .maxNumberLength(64)
    .maxDocumentLength(2 * 1024 * 1024L)
    .build();
```

Đây chỉ là bộ giá trị minh họa. Một endpoint upload metadata có thể cần giới hạn khác với endpoint nhận comment dài hoặc batch records.

Quy trình lựa chọn:

1. Thu thập payload hợp lệ điển hình và payload lớn nhất được contract cho phép.
2. Phân loại endpoint theo loại dữ liệu, chẳng hạn metadata, form, batch, rich text hoặc file metadata.
3. Đặt ngưỡng có khoảng đệm hợp lý trên giá trị hợp lệ tối đa.
4. Cấu hình giới hạn parser trên factory dùng cho endpoint.
5. Bổ sung giới hạn tổng request và validation theo từng field.
6. Theo dõi lỗi constraint và điều chỉnh dựa trên dữ liệu thực tế.

Không đặt giới hạn sát đúng kích thước trung bình. Client có thể có Unicode, escape sequence, tên field mở rộng hoặc dữ liệu hợp lệ ở sát biên contract.

## 9. Kết hợp parser constraints với JSON Schema và Bean Validation

Ba lớp thường phối hợp như sau:

| Lớp | Ví dụ | Thời điểm |
|---|---|---|
| Transport/request limit | Giới hạn body 2 MB sau khi xử lý transfer/content encoding theo chính sách server | Khi nhận request |
| Jackson `StreamReadConstraints` | String tối đa, property name tối đa, number token tối đa, nesting depth | Trong lúc parse token |
| JSON Schema | `maxLength`, `maxProperties`, `maximum`, `maxItems`, `additionalProperties` | Sau khi tạo JSON representation cần validate |
| Bean Validation | `@Size`, `@Digits`, `@DecimalMax`, custom constraint | Sau khi deserialize thành Java object |
| Domain/service | Giá trị có hợp lệ theo tài khoản/trạng thái hay không | Trong xử lý nghiệp vụ |

Ví dụ DTO:

```java
public class ProfileRequest {
    @NotBlank
    @Size(max = 80)
    private String displayName;

    @Size(max = 500)
    private String biography;

    @NotNull
    @DecimalMin("0.00")
    @DecimalMax("1000000.00")
    @Digits(integer = 7, fraction = 2)
    private BigDecimal monthlyBudget;
}
```

Parser constraint giới hạn string token lớn nhất và numeric token dài bất thường ở cấp toàn mapper/factory. Bean Validation giới hạn riêng `displayName`, `biography` và `monthlyBudget` theo contract của DTO.

### 9.1. Vì sao @Size không thay thế maxStringLength?

`@Size(max = 500)` chỉ chạy sau khi Jackson đã đọc string và tạo giá trị Java. Nếu request gửi một string cực lớn, parser vẫn phải đọc và giải mã nó trước khi Bean Validation có cơ hội từ chối.

Vì vậy:

- `maxStringLength` bảo vệ parser trước string token quá lớn.
- `@Size` bảo vệ contract của một property cụ thể sau binding.

Hai giới hạn có thể khác nhau. Ví dụ parser cho phép string tối đa 128 KB vì một field upload metadata có thể dài, nhưng `biography` chỉ được phép 500 ký tự.

### 9.2. Vì sao JSON Schema maxLength không thay thế parser constraint?

JSON Schema validator thường cần một `JsonNode` hoặc representation đã parse. Nếu string đã quá lớn, bộ nhớ đã được dùng để tạo node trước khi schema có thể áp dụng `maxLength`.

Schema rất hữu ích để kiểm tra giới hạn riêng của field và contract dùng chung, nhưng không nên xem nó là lớp bảo vệ duy nhất trước token quá lớn. Dùng parser constraints và transport limit để kiểm soát tài nguyên sớm hơn.

## 10. Giới hạn tổng request ở tầng HTTP

`StreamReadConstraints` giới hạn token/document theo khả năng của parser. Nó không thay thế giới hạn body của HTTP server, reverse proxy, API gateway hoặc framework.

Một request có thể chứa nhiều JSON document hoặc dữ liệu ngoài JSON tùy giao thức. Ngoài ra, `Content-Length` có thể không có trong request streaming/chunked. Vì vậy, cần giới hạn dữ liệu thực sự được đọc, không chỉ tin vào header.

Các điểm cần cấu hình:

- Reverse proxy/API gateway: giới hạn request body theo route.
- HTTP server/framework: giới hạn số byte đọc từ request stream.
- Nếu có gzip hoặc content encoding: cân nhắc giới hạn cả compressed bytes lẫn decompressed bytes để tránh decompression bomb.
- Jackson: giới hạn document/token/string/name/number/depth.
- Application: giới hạn số record, số field động và kích thước nội dung theo nghiệp vụ.

Không nên đọc toàn bộ body vào `byte[]` hoặc `String` trước rồi mới kiểm tra kích thước nếu mục tiêu là bảo vệ bộ nhớ. Dùng stream có giới hạn byte hoặc cơ chế giới hạn body của framework.

## 11. Áp dụng constraints cho tất cả parser của ứng dụng

`StreamReadConstraints` gắn với `JsonFactory`. Nếu ứng dụng có nhiều mapper/factory, cần đảm bảo từng đường đọc đều dùng factory được cấu hình:

```java
JsonFactory apiFactory = JsonFactory.builder()
    .streamReadConstraints(apiConstraints)
    .build();

ObjectMapper apiMapper = new ObjectMapper(apiFactory);

JsonFactory importFactory = JsonFactory.builder()
    .streamReadConstraints(importConstraints)
    .build();

ObjectMapper importMapper = new ObjectMapper(importFactory);
```

Ví dụ này cho phép API và batch import dùng giới hạn khác nhau. API có thể nhận string nhỏ và body ngắn; import nội bộ có thể chấp nhận batch lớn hơn nhưng vẫn có giới hạn rõ.

### 11.1. Không thay đổi cấu hình mapper dùng chung theo từng request

Hãy tạo factory/mapper với constraints cố định ở giai đoạn khởi tạo. Không đổi cấu hình của mapper singleton theo từng request vì nhiều request có thể dùng đồng thời và kết quả trở nên khó dự đoán.

Nếu endpoint cần chính sách riêng, tạo mapper/reader/factory được cấu hình trước và inject theo endpoint hoặc service. Chỉ tạo thêm mapper khi thực sự cần một bộ cấu hình parser khác; mapper nên được tái sử dụng, không tạo cho mỗi request.

### 11.2. Các parser được tạo bên ngoài mapper

Nếu code gọi trực tiếp:

```java
JsonParser parser = anotherFactory.createParser(input);
```

parser sẽ dùng constraints của `anotherFactory`, không tự kế thừa cấu hình từ một `ObjectMapper` khác. Kiểm tra mọi đường đọc JSON: controller, message consumer, file import, scheduled job, test helper và integration adapter.

## 12. Xử lý lỗi khi vượt giới hạn

Khi input vượt `StreamReadConstraints`, Jackson ném lỗi constraint trong quá trình đọc. Trong Jackson 2.x, có thể gặp `StreamConstraintsException` thuộc package `com.fasterxml.jackson.core.exc`.

Ví dụ xử lý ở tầng nhận request:

```java
try {
    CreateRequest request = mapper.readValue(input, CreateRequest.class);
    process(request);
} catch (StreamConstraintsException ex) {
    throw new InvalidRequestException(
        "JSON input exceeds an allowed size or structure limit",
        ex
    );
} catch (JsonProcessingException ex) {
    throw new InvalidRequestException("Invalid JSON request", ex);
}
```

Exception cụ thể và package import có thể thay đổi theo major version. Jackson 3 chuyển Core sang package `tools.jackson.core...`; hãy dùng exception type tương ứng với dependency thực tế.

### 12.1. Không trả chi tiết nội bộ cho client

Thông điệp exception có thể chứa giá trị giới hạn, loại token hoặc vị trí parser. Có thể ghi nhận chi tiết ở log nội bộ có kiểm soát, nhưng response public nên dùng mã lỗi ổn định như `REQUEST_TOO_LARGE` hoặc `JSON_CONSTRAINT_EXCEEDED`.

Không log toàn bộ string hoặc property name đã vượt giới hạn nếu dữ liệu có thể nhạy cảm hoặc quá lớn. Ghi nhận loại constraint, endpoint, kích thước gần đúng và correlation id thường hữu ích hơn.

### 12.2. Phân biệt constraint error và schema validation error

Nếu parser từ chối một string quá lớn, JSON Schema validator chưa được chạy. Nếu parser chấp nhận nhưng `maxLength` của schema không đạt, đó là schema violation. Nếu schema hợp lệ nhưng `@Size` của DTO không đạt, đó là Bean Validation violation.

Phân loại lỗi giúp vận hành biết lớp bảo vệ nào đã kích hoạt và tránh trả mọi lỗi dưới nhãn “JSON syntax error”.

## 13. Kiểm thử các giới hạn parser

Nên tạo factory riêng với giới hạn nhỏ trong test để kiểm tra hành vi mà không cần tạo payload khổng lồ:

```java
class StreamReadConstraintsTest {
    private ObjectMapper mapperWithLimits() {
        StreamReadConstraints constraints = StreamReadConstraints.builder()
            .maxNestingDepth(4)
            .maxStringLength(16)
            .maxNameLength(12)
            .maxNumberLength(8)
            .build();

        JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(constraints)
            .build();

        return new ObjectMapper(factory);
    }

    @Test
    void rejectsStringAboveConfiguredLimit() {
        ObjectMapper mapper = mapperWithLimits();

        assertThrows(StreamConstraintsException.class,
            () -> mapper.readTree("{\"value\":\"0123456789abcdef0123\"}"));
    }

    @Test
    void rejectsPropertyNameAboveConfiguredLimit() {
        ObjectMapper mapper = mapperWithLimits();

        assertThrows(StreamConstraintsException.class,
            () -> mapper.readTree("{\"propertyNameTooLong\":1}"));
    }

    @Test
    void rejectsNumberAboveConfiguredLimit() {
        ObjectMapper mapper = mapperWithLimits();

        assertThrows(StreamConstraintsException.class,
            () -> mapper.readTree("{\"value\":1234567890123}"));
    }
}
```

Ví dụ trên dùng `maxNameLength()`, vì vậy cần Jackson Core 2.16 trở lên. Với test nesting depth, tạo JSON lồng nhiều hơn mức cho phép và xác nhận parser từ chối.

Giới hạn string/name được áp dụng theo buffer growth nên test nên dùng giá trị vượt ngưỡng một khoảng đủ lớn, không kiểm tra sát đúng một đơn vị. Không viết test giả định mọi trường hợp đúng tại ranh giới sẽ bị từ chối chính xác tuyệt đối.

### 13.1. Test cả đường đi thực tế

Test trực tiếp `ObjectMapper.readTree()` xác nhận factory có constraint. Nhưng ứng dụng production có thể dùng mapper khác trong framework. Hãy có integration test cho controller/message consumer đang dùng mapper được inject thật.

Kiểm tra:

- Request body vượt giới hạn transport.
- String value quá dài.
- Property name quá dài.
- Numeric token quá dài.
- JSON nesting quá sâu.
- Document có quá nhiều property/token nếu có cấu hình tương ứng.
- Request hợp lệ sát giới hạn vẫn được chấp nhận.
- Error handler chuyển constraint exception thành response phù hợp.

## 14. Một số lưu ý về phiên bản Jackson

Các giới hạn được bổ sung theo từng phiên bản:

| Tính năng | Phiên bản Jackson Core |
|---|---|
| `StreamReadConstraints` và `maxStringLength`, `maxNumberLength`, `maxNestingDepth` | 2.15 trở lên |
| `maxNameLength` | 2.16 trở lên |
| `maxDocumentLength` | 2.16 trở lên |
| `maxTokenCount` | 2.18 trở lên |

Giá trị mặc định cũng thay đổi giữa các dòng release. Ví dụ, Jackson 2.15 ban đầu dùng giới hạn string mặc định thấp hơn; các bản 2.16/2.17 phổ biến có các giá trị mặc định như sau:

| Constraint | Default thường gặp trong Jackson Core 2.16/2.17 |
|---|---:|
| Maximum number token length | 1.000 |
| Maximum string value length | 20.000.000 |
| Maximum property name length | 50.000 |
| Maximum nesting depth | 1.000 |

Đây là giá trị mặc định của các version được nêu, không phải khuyến nghị cho mọi ứng dụng. Hãy xem Javadoc đúng version và cấu hình rõ ràng theo contract. Jackson 3.x có thay đổi một số default và package namespace; không sao chép bảng version 2.x sang major version 3.

## 15. Những hiểu lầm thường gặp

**`maxStringLength` giới hạn tổng body.** Không đúng. Nó giới hạn từng string value; tổng body cần giới hạn ở HTTP/parser document layer.

**`maxStringLength` cũng giới hạn property name.** Không đúng. Tên thuộc tính có `maxNameLength()` từ Jackson Core 2.16.

**`maxNameLength` giới hạn số lượng field.** Không đúng. Nó giới hạn độ dài từng tên; số field cần giới hạn bằng token count, JSON Schema `maxProperties` hoặc logic riêng.

**`maxNumberLength` bảo đảm số nằm trong range nghiệp vụ.** Không đúng. Nó giới hạn literal length, còn range/precision cần schema, Bean Validation hoặc domain logic.

**`@Size` bảo vệ parser trước string lớn.** Không đúng. Bean Validation chạy sau khi object đã được tạo. Dùng `maxStringLength` và giới hạn body để bảo vệ sớm.

**JSON Schema `maxLength` là đủ để chống payload string cực lớn.** Validator thường cần parse JSON trước; dùng parser constraint và transport limit làm lớp bảo vệ tài nguyên.

**Một giới hạn duy nhất giải quyết mọi DoS input.** Không đúng. Cần xem cả body size, token size, depth, token count, số record, timeout, decompression và logic xử lý.

**Mặc định Jackson giống nhau ở mọi version.** Không đúng. Các giới hạn được thêm theo release và một số default thay đổi. Kiểm tra đúng `jackson-core` runtime.

**Cấu hình mapper có nghĩa mọi parser đều dùng cùng giới hạn.** Chỉ parser tạo từ factory đã cấu hình mới nhận các giới hạn đó. Kiểm tra mapper/factory độc lập trong ứng dụng.

## 16. Quy trình harden JSON input

1. Xác định kích thước tối đa hợp lệ của request theo endpoint.
2. Đặt giới hạn body ở gateway, HTTP server hoặc framework; kiểm soát cả dữ liệu sau giải nén.
3. Cấu hình `StreamReadConstraints` trên `JsonFactory` dùng bởi mapper thực tế.
4. Đặt `maxStringLength` phù hợp với string value lớn nhất hợp lệ.
5. Đặt `maxNameLength` nếu phiên bản Jackson Core hỗ trợ, đặc biệt với Map hoặc field động.
6. Đặt `maxNumberLength` để từ chối numeric token bất thường.
7. Đặt `maxNestingDepth` để giới hạn cấu trúc lồng sâu.
8. Cân nhắc `maxDocumentLength` và `maxTokenCount` ở version hỗ trợ.
9. Dùng JSON Schema/Bean Validation để kiểm tra giới hạn riêng của field, range số, số property và số phần tử.
10. Kiểm soát unknown property và key động bằng allowlist hoặc `@JsonAnySetter` có giới hạn.
11. Chuyển constraint exception thành response lỗi ổn định, không tiết lộ payload nhạy cảm.
12. Kiểm thử cả payload hợp lệ lớn nhất và payload vượt ngưỡng trên đúng mapper production.
13. Theo dõi lỗi bị từ chối và điều chỉnh ngưỡng khi contract thay đổi.

## Kết luận

`StreamReadConstraints` cho phép Jackson Core giới hạn các token và cấu trúc đầu vào ngay trong lúc parse. `maxStringLength` giới hạn string value, `maxNameLength` giới hạn tên property (từ 2.16), `maxNumberLength` giới hạn độ dài numeric token và `maxNestingDepth` giới hạn cấu trúc lồng nhau. Các bản mới còn có giới hạn document length và token count. Những giới hạn này bảo vệ tài nguyên parser nhưng không thay thế request body limit, JSON Schema hay Bean Validation: parser kiểm soát kích thước token, schema kiểm tra contract JSON, Bean Validation kiểm tra object Java và service/domain layer kiểm tra quy tắc nghiệp vụ. Hãy cấu hình factory thực sự dùng trong ứng dụng, chọn ngưỡng theo dữ liệu hợp lệ và kiểm thử cả trường hợp sát giới hạn.

## Tài liệu tham khảo

- [Jackson Core 2.16 StreamReadConstraints](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-core/2.16.2/com/fasterxml/jackson/core/StreamReadConstraints.html) — các giới hạn và thời điểm hỗ trợ `maxNameLength`.
- [Jackson Core 2.16 StreamReadConstraints.Builder](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-core/2.16.2/com/fasterxml/jackson/core/StreamReadConstraints.Builder.html) — cấu hình `maxStringLength`, `maxNameLength`, `maxNumberLength`, document length.
- [Jackson Core 2.17 StreamReadConstraints](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-core/2.17.3/com/fasterxml/jackson/core/StreamReadConstraints.html) — default constraints của dòng 2.17.
- [Jackson Core processing limits](https://github.com/FasterXML/jackson-core) — mục processing limits, đơn vị input và giới hạn áp dụng theo buffer growth.
