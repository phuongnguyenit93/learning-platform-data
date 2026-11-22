# Kiểm thử khả năng nhập lại và tương tác với công cụ bên ngoài

Một file YAML hoặc CSV được Jackson ghi ra chưa chắc đã dùng được trong hệ thống khác. File có thể đọc lại bằng chính mapper vừa ghi nhưng vẫn gây lỗi với Python, pandas, Excel, LibreOffice, một ETL tool hoặc parser của đối tác. Nguyên nhân thường nằm ở những chi tiết mà phép serialize đơn lẻ không kiểm tra: header CSV, thứ tự cột, kiểu scalar YAML, null và chuỗi rỗng, dấu phân cách, quoting, encoding, định dạng ngày giờ, độ chính xác số và quy tắc xử lý field lạ.

Vì vậy, kiểm thử YAML/CSV cần xem **khả năng nhập lại và tương tác với consumer bên ngoài là một phần của hợp đồng dữ liệu**. Round-trip test giúp phát hiện việc Jackson không đọc lại được output của chính nó; interoperability test xác nhận công cụ khác hiểu file theo cùng ý nghĩa; compatibility test bảo đảm thay đổi model hoặc thư viện không âm thầm làm hỏng file đã phát hành.

Bài này trình bày cách xây dựng các kiểm thử đó với Jackson YAML và CSV, cách kiểm tra giá trị thay vì phụ thuộc vào định dạng văn bản không ổn định, cách tạo fixture thực tế cho công cụ ngoài và các trường hợp biên thường bị bỏ sót.

## 1. Round-trip test kiểm tra điều gì?

Một round-trip cơ bản có hai bước:

1. Serialize object Java thành YAML hoặc CSV.
2. Deserialize nội dung vừa ghi trở lại kiểu Java.

~~~text
Java object
    |
    | Jackson serialize
    v
YAML / CSV bytes
    |
    | Jackson deserialize
    v
Restored Java object
    |
    | Compare semantic values
    v
Assertions
~~~

Ví dụ:

~~~java
String yaml = yamlMapper.writeValueAsString(original);
User restored = yamlMapper.readValue(yaml, User.class);

assertEquals(original.getId(), restored.getId());
assertEquals(original.getName(), restored.getName());
~~~

Round-trip test có thể phát hiện:

- Property bị bỏ khỏi output.
- Tên field ghi ra không khớp với tên reader mong đợi.
- Kiểu số hoặc ngày giờ bị chuyển đổi sai.
- Enum không thể đọc lại.
- Null và empty bị nhập nhằng.
- CSV schema ghi thiếu hoặc đảo cột.
- Collection/map không được biểu diễn theo cách consumer hiểu.
- Cấu hình serialize và deserialize không đồng bộ.

Tuy nhiên, round-trip chỉ chứng minh rằng một mapper có thể đọc output của chính nó trong cùng cấu hình. Nó chưa chứng minh output tuân thủ dialect CSV hoặc semantics YAML mà công cụ khác sử dụng.

## 2. Phân biệt round-trip, interoperability và compatibility

Ba loại test này có mục tiêu khác nhau:

| Loại test | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Round-trip | Jackson có đọc lại được dữ liệu Jackson vừa ghi không? | Object → CSV → Object |
| Interoperability | Công cụ khác có hiểu file theo đúng ý nghĩa không? | Jackson CSV → pandas DataFrame |
| Compatibility | File cũ và model mới có còn tương thích không? | Fixture từ phiên bản trước → DTO hiện tại |

Một bộ kiểm thử tốt nên có cả ba khi YAML/CSV được dùng để trao đổi qua ranh giới hệ thống.

### 2.1. Vì sao round-trip có thể tạo cảm giác an toàn giả?

Giả sử producer và consumer cùng dùng một schema CSV có thứ tự cột sai so với hợp đồng bên ngoài. Jackson ghi theo schema đó và Jackson đọc lại theo đúng schema đó; test vẫn pass. Nhưng đối tác dùng header theo tên hoặc dùng thứ tự cột đã công bố có thể đọc nhầm dữ liệu.

Tương tự, YAML có thể được Jackson đọc lại nhưng một thư viện YAML khác diễn giải scalar như `yes`, `no`, `on`, `off` theo quy tắc khác. Một round-trip nội bộ không phát hiện được sự khác biệt này.

Vì vậy, hãy kiểm tra output với ít nhất một consumer độc lập khi file được trao đổi ra ngoài ứng dụng.

## 3. Xây dựng test fixture ổn định

Fixture là file YAML/CSV mẫu được lưu cùng test để đại diện cho hợp đồng đã phát hành.

Một fixture tốt nên:

- Dùng dữ liệu thực tế nhưng không chứa bí mật hoặc thông tin cá nhân thật.
- Bao gồm giá trị bình thường và các trường hợp biên.
- Có encoding được xác định rõ, thường là UTF-8.
- Ghi nhận quy tắc line ending và header CSV nếu chúng thuộc hợp đồng.
- Có tên thể hiện mục đích, ví dụ `payments-v1.csv` hoặc `user-config-v2.yaml`.
- Được đọc từ classpath hoặc test resources thay vì dựng lại hoàn toàn bằng string trong từng test.
- Có nguồn gốc và version rõ nếu được tạo bởi hệ thống bên ngoài.

Ví dụ cấu trúc thư mục:

~~~text
src/test/resources/
  fixtures/
    yaml/
      user-config-v1.yaml
      user-config-null-values.yaml
    csv/
      payments-v1.csv
      payments-empty-fields.csv
      payments-quoted-fields.csv
~~~

Fixture giúp kiểm tra những file đã tồn tại ngoài production. Khi model hoặc Jackson được nâng cấp, test sẽ phát hiện nếu ứng dụng không còn đọc được định dạng cũ.

### 3.1. Fixture là hợp đồng, không phải snapshot tùy tiện

Không nên cập nhật fixture chỉ để làm test pass sau khi thay đổi serializer. Trước khi thay fixture, xác định thay đổi đó là:

- Sửa lỗi implementation nhưng giữ nguyên contract.
- Thay đổi contract có chủ đích.
- Thay đổi formatting nhưng không thay đổi semantic value.
- Thay đổi làm mất tương thích với consumer cũ.

Nếu contract thay đổi, cần versioning và kế hoạch migration thay vì chỉ ghi đè file fixture cũ.

## 4. Kiểm thử YAML round-trip với Jackson

Jackson YAML nằm trong module `jackson-dataformat-yaml`. Có thể tạo mapper bằng YAMLFactory:

~~~java
ObjectMapper yamlMapper = new ObjectMapper(new YAMLFactory());
~~~

Nếu model dùng các kiểu `java.time`, đăng ký JavaTimeModule như với Jackson Databind:

~~~java
ObjectMapper yamlMapper = JsonMapper.builder(new YAMLFactory())
        .addModule(new JavaTimeModule())
        .build();
~~~

Tùy phiên bản Jackson, builder overload có thể khác; có thể dùng `new ObjectMapper(new YAMLFactory())` rồi đăng ký module trước khi dùng mapper.

DTO:

~~~java
public class UserConfig {
    private String id;
    private String displayName;
    private boolean enabled;
    private List<String> roles;

    public UserConfig() {
    }

    public UserConfig(
            String id,
            String displayName,
            boolean enabled,
            List<String> roles
    ) {
        this.id = id;
        this.displayName = displayName;
        this.enabled = enabled;
        this.roles = roles;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public List<String> getRoles() {
        return roles;
    }

    public void setRoles(List<String> roles) {
        this.roles = roles;
    }
}
~~~

Test:

~~~java
@Test
void shouldRoundTripYaml() throws Exception {
    ObjectMapper mapper = new ObjectMapper(new YAMLFactory());

    UserConfig original = new UserConfig(
            "U-100",
            "An",
            true,
            List.of("reader", "operator")
    );

    String yaml = mapper.writeValueAsString(original);
    UserConfig restored = mapper.readValue(yaml, UserConfig.class);

    assertEquals(original.getId(), restored.getId());
    assertEquals(original.getDisplayName(), restored.getDisplayName());
    assertEquals(original.isEnabled(), restored.isEnabled());
    assertEquals(original.getRoles(), restored.getRoles());
}
~~~

Test so sánh giá trị sau khi parse. Nó không yêu cầu YAML output phải có đúng indentation, quote style hoặc thứ tự trình bày như một chuỗi snapshot cố định, trừ khi các chi tiết đó là một phần contract đã công bố.

## 5. Kiểm thử YAML bằng fixture bên ngoài

Một fixture YAML có thể được tạo bởi Python, một công cụ cấu hình hoặc người vận hành. Đọc fixture bằng mapper hiện tại:

~~~java
@Test
void shouldReadExternalYamlFixture() throws Exception {
    ObjectMapper mapper = new ObjectMapper(new YAMLFactory());

    try (InputStream input = getClass()
            .getResourceAsStream("/fixtures/yaml/user-config-v1.yaml")) {

        assertNotNull(input);

        UserConfig config = mapper.readValue(input, UserConfig.class);

        assertEquals("U-100", config.getId());
        assertEquals("An", config.getDisplayName());
        assertTrue(config.isEnabled());
    }
}
~~~

Đây là kiểm thử consumer: Jackson phải đọc file đã được tạo ở nơi khác, không phải file do cùng test serialize trước đó.

Nếu fixture được xuất từ hệ thống bên ngoài, nên lưu một bản nguyên gốc trong test resources. Tránh tự tạo lại fixture bằng Jackson trong bước setup, vì như vậy test sẽ không còn kiểm tra khác biệt giữa các producer.

## 6. YAML scalar có thể được diễn giải khác nhau

YAML là định dạng có kiểu scalar, nhưng quy tắc nhận diện scalar có thể khác theo phiên bản specification và thư viện parser.

Những giá trị dễ gây nhầm:

~~~yaml
enabled: yes
disabled: no
mode: on
version: 0012
date: 2025-01-02
code: 000123
empty: ""
nothing: null
~~~

Một công cụ có thể hiểu `yes/no/on/off` là boolean theo quy tắc YAML cũ, trong khi công cụ khác coi đó là string. Giá trị bắt đầu bằng số 0 có thể bị diễn giải thành kiểu số hoặc mất số 0 đầu. Date-like scalar có thể được parse thành date object thay vì string.

Nếu field là mã định danh, mã bưu chính, số tài khoản hoặc code có số 0 đầu, hãy quote rõ ràng:

~~~yaml
postalCode: "00123"
accountCode: "00004567"
enabledText: "yes"
releaseLabel: "2025-01-02"
~~~

Nếu field thực sự là boolean hoặc number, dùng scalar đúng kiểu:

~~~yaml
enabled: true
retryCount: 3
~~~

### 6.1. Kiểm thử kiểu dữ liệu sau khi đọc

Không chỉ assert chuỗi output có chứa giá trị. Hãy kiểm tra kiểu Java và giá trị thực:

~~~java
@Test
void shouldPreserveIdentifierWithLeadingZeros() throws Exception {
    String yaml = """
            accountCode: "00004567"
            """;

    AccountConfig config = mapper.readValue(yaml, AccountConfig.class);

    assertEquals("00004567", config.getAccountCode());
}
~~~

Nếu field được khai báo String, test này bảo đảm số 0 đầu không bị mất do một producer ghi scalar không quote hoặc một consumer suy diễn thành số.

### 6.2. Null và empty trong YAML

YAML có thể biểu diễn null bằng `null`, `~` hoặc một số dạng scalar rỗng tùy context. Chuỗi rỗng được quote là giá trị khác:

~~~yaml
nickname: null
description: ""
~~~

Trong DTO, null và empty string có thể mang ý nghĩa nghiệp vụ khác nhau. Hãy có fixture cho cả hai và assert riêng:

~~~java
assertNull(config.getNickname());
assertEquals("", config.getDescription());
~~~

Không nên giả định mọi công cụ YAML sẽ giữ nguyên semantics nếu field không được quote hoặc nếu schema của công cụ ngoài áp dụng default value.

## 7. YAML aliases, anchors và tags

YAML hỗ trợ anchors và aliases để tái sử dụng node:

~~~yaml
defaults: &defaults
  retries: 3
  timeoutSeconds: 10

serviceA:
  <<: *defaults
  name: alpha
~~~

Không phải mọi parser hoặc công cụ xử lý YAML đều hỗ trợ merge key theo cùng cách. Jackson YAML, SnakeYAML và các công cụ khác có thể khác nhau theo version và cấu hình. Nếu file là hợp đồng trao đổi rộng, nên cân nhắc tránh các tính năng phụ thuộc parser như merge key hoặc anchors phức tạp.

YAML còn có explicit tags. Tag có thể biểu diễn kiểu đặc biệt và một số thư viện cho phép custom constructor. Không nên chấp nhận arbitrary tags hoặc object construction từ YAML không tin cậy. Dùng model rõ ràng, giới hạn tag cần thiết và kiểm tra cấu hình parser của phiên bản SnakeYAML mà Jackson YAML sử dụng.

Interoperability test nên bao gồm fixture có anchor/alias nếu contract cho phép, hoặc xác nhận ứng dụng từ chối chúng nếu không hỗ trợ.

## 8. YAML và thay đổi field theo thời gian

Một file cấu hình cũ có thể không chứa property mới. Khi đọc, Jackson sẽ để giá trị Java mặc định hoặc giá trị initializer tùy cách tạo object và binding.

Ví dụ:

~~~java
public class ServiceConfig {
    private String name;
    private int retries = 3;

    // Getter/setter
}
~~~

Fixture cũ:

~~~yaml
name: worker
~~~

Nếu property `retries` không xuất hiện, test nên xác nhận default mong muốn:

~~~java
assertEquals(3, config.getRetries());
~~~

Ngược lại, nếu property mới bắt buộc phải có, cần validation rõ ràng sau binding hoặc dùng creator/required property phù hợp. Đừng để thiếu field quan trọng âm thầm trở thành `0`, `false` hoặc null.

### 8.1. Unknown YAML properties

Nếu YAML chứa field mới mà DTO cũ không biết, behavior phụ thuộc `FAIL_ON_UNKNOWN_PROPERTIES` và annotation/configuration tương ứng.

Có ba chiến lược:

- Strict: từ chối field lạ để phát hiện file sai version.
- Tolerant: bỏ qua field lạ để consumer cũ có thể đọc subset.
- Preserve: lưu field lạ trong Map/JsonNode-like structure để round-trip hoặc chuyển tiếp.

Test cần xác nhận chính sách đã chọn. Nếu tắt unknown-property failure, hãy có test để chứng minh field lạ không làm hỏng phần dữ liệu đã biết.

## 9. CSV cần schema tường minh

CSV không mang type metadata phong phú như YAML. Một file thường chỉ là hàng và cột văn bản, vì vậy consumer cần biết:

- Tên cột.
- Thứ tự cột.
- Dấu phân cách.
- Quote character và escaping.
- Có header hay không.
- Quy tắc encoding và line ending.
- Cách biểu diễn null/empty.
- Kiểu dữ liệu của từng cột.

Jackson CSV cung cấp CsvMapper và CsvSchema để mô tả cấu trúc.

Ví dụ model phẳng:

~~~java
public class PaymentRow {
    private String id;
    private BigDecimal amount;
    private String currency;
    private String status;

    public PaymentRow() {
    }

    // Getter và setter
}
~~~

Schema:

~~~java
CsvMapper csvMapper = new CsvMapper();

CsvSchema schema = CsvSchema.builder()
        .addColumn("id")
        .addColumn("amount")
        .addColumn("currency")
        .addColumn("status")
        .setUseHeader(true)
        .build();
~~~

Ghi nhiều record:

~~~java
StringWriter output = new StringWriter();
try (SequenceWriter sequence = csvMapper.writer(schema)
        .writeValues(output)) {
    sequence.writeAll(rows);
}

String csv = output.toString();
~~~

Đọc theo header:

~~~java
CsvSchema readSchema = CsvSchema.emptySchema().withHeader();

try (MappingIterator<PaymentRow> iterator =
        csvMapper.readerFor(PaymentRow.class)
                .with(readSchema)
                .readValues(csv)) {

    List<PaymentRow> restored = iterator.readAll();
}
~~~

Với schema có header, tên cột trong file được dùng để ánh xạ property. Nếu contract yêu cầu thứ tự cột cố định, test cả header lẫn thứ tự output.

## 10. Kiểm thử CSV round-trip

Ví dụ test:

~~~java
@Test
void shouldRoundTripCsvWithHeader() throws Exception {
    CsvMapper mapper = new CsvMapper();

    CsvSchema schema = CsvSchema.builder()
            .addColumn("id")
            .addColumn("amount")
            .addColumn("currency")
            .addColumn("status")
            .setUseHeader(true)
            .build();

    PaymentRow first = payment(
            "P-001",
            new BigDecimal("125.50"),
            "VND",
            "PAID"
    );

    PaymentRow second = payment(
            "P-002",
            new BigDecimal("80.00"),
            "USD",
            "PENDING"
    );

    StringWriter output = new StringWriter();
    try (SequenceWriter sequence = mapper.writer(schema)
            .writeValues(output)) {
        sequence.writeAll(List.of(first, second));
    }
    String csv = output.toString();

    CsvSchema readSchema = CsvSchema.emptySchema().withHeader();

    List<PaymentRow> restored;
    try (MappingIterator<PaymentRow> iterator =
            mapper.readerFor(PaymentRow.class)
                    .with(readSchema)
                    .readValues(csv)) {
        restored = iterator.readAll();
    }

    assertEquals(2, restored.size());
    assertEquals("P-001", restored.get(0).getId());
    assertEquals(0, new BigDecimal("125.50")
            .compareTo(restored.get(0).getAmount()));
    assertEquals("VND", restored.get(0).getCurrency());
    assertEquals("PAID", restored.get(0).getStatus());
}
~~~

Với `BigDecimal`, dùng compareTo nếu scale không phải một phần contract. Nếu scale có ý nghĩa, ví dụ số tiền luôn phải có hai chữ số thập phân, hãy assert scale riêng hoặc kiểm tra representation output.

### 10.1. Header là một phần của contract

Một header như:

~~~csv
id,amount,currency,status
~~~

khác với:

~~~csv
amount,id,status,currency
~~~

Nếu consumer ánh xạ theo header, thứ tự có thể không ảnh hưởng đến binding nhưng vẫn có thể quan trọng với công cụ chỉ đọc theo vị trí. Nếu file không có header, thứ tự cột trở thành yêu cầu bắt buộc.

Test nên xác nhận chính xác header được ghi ra:

~~~java
String firstLine = csv.lines().findFirst().orElseThrow();

assertEquals("id,amount,currency,status", firstLine);
~~~

Chỉ dùng assertion chính xác như trên khi delimiter, line ending và header order đã được chốt trong contract.

## 11. CSV quoting và escaping

CSV cần xử lý đúng các giá trị có:

- Dấu phân cách, ví dụ dấu phẩy.
- Dấu quote.
- Ký tự xuống dòng.
- Dấu cách ở đầu/cuối.
- Unicode.
- Chuỗi rỗng.

Ví dụ dữ liệu:

~~~text
id=P-003
description=Transfer, urgent
note=Customer said "send today"
comment=Line one
Line two
~~~

CSV cần quote field chứa delimiter, quote hoặc newline. Dấu quote bên trong field thường được escape bằng cách lặp đôi:

~~~csv
id,description,note
P-003,"Transfer, urgent","Customer said ""send today"""
~~~

Không nên tự nối string bằng dấu phẩy:

~~~java
String line = id + "," + description + "," + note;
~~~

Cách đó sẽ làm hỏng record nếu description chứa dấu phẩy hoặc newline. Dùng CsvMapper/CsvSchema để serializer xử lý quoting theo dialect đã chọn.

### 11.1. Kiểm thử ký tự đặc biệt

~~~java
@Test
void shouldRoundTripQuotedCsvFields() throws Exception {
    PaymentRow row = payment(
            "P-003",
            new BigDecimal("10.00"),
            "USD",
            "Transfer, urgent; note: \"send today\""
    );

    StringWriter output = new StringWriter();
    try (SequenceWriter sequence = csvMapper.writer(schema)
            .writeValues(output)) {
        sequence.write(row);
    }
    String csv = output.toString();

    List<PaymentRow> restored = readPayments(csv);

    assertEquals(
            "Transfer, urgent; note: \"send today\"",
            restored.get(0).getStatus()
    );
}
~~~

Ví dụ này dùng field status để minh họa text có dấu phẩy và quote; trong model thực tế, hãy đặt vào cột mô tả phù hợp. Quan trọng là test round-trip chính giá trị có ký tự đặc biệt, không chỉ assert output có dấu quote.

### 11.2. Newline bên trong một CSV field

CSV cho phép field có newline nếu field được quote đúng. Vì thế, số dòng vật lý trong file không nhất thiết bằng số record. Không nên đếm record bằng cách gọi split("\\n") hoặc đọc từng dòng text rồi coi mỗi dòng là một row CSV.

Dùng CSV parser hiểu quoting để đọc record. Nếu ứng dụng cần streaming, dùng MappingIterator hoặc parser tương ứng thay vì tự chia chuỗi theo newline.

## 12. Null và empty trong CSV

CSV không có một kiểu null tiêu chuẩn phổ quát. Một ô rỗng có thể có nghĩa:

- Giá trị null.
- Chuỗi rỗng.
- Không có dữ liệu.
- Giá trị chưa được cung cấp.
- Giá trị cần giữ nguyên mặc định.

Hai biểu diễn:

~~~csv
id,note
P-001,
P-002,""
~~~

có thể bị các công cụ diễn giải khác nhau. Một số parser coi cả hai là empty string; một số pipeline có thể coi ô không quote là null hoặc missing.

Nếu cần phân biệt null với empty, hãy định nghĩa convention rõ ràng, ví dụ:

- Dùng một sentinel được escape và bảo đảm không đụng giá trị hợp lệ.
- Thêm cột trạng thái null riêng.
- Dùng một định dạng có null semantics rõ hơn như YAML/JSON khi contract cần giữ khác biệt.
- Quy định empty luôn tương đương null hoặc luôn tương đương empty string, rồi test điều đó.

Không dựa vào hành vi mặc định của một spreadsheet hoặc ETL tool để suy ra null semantics cho toàn hệ thống.

## 13. CSV và kiểu dữ liệu

CSV thường đọc mọi cell như text trước khi ứng dụng chuyển sang kiểu đích. Điều này tạo ra các điểm cần kiểm thử.

### 13.1. Số nguyên lớn

Một số công cụ spreadsheet có thể tự chuyển chuỗi số dài thành dạng scientific notation hoặc làm tròn độ chính xác. Nếu cột là mã định danh, hãy coi nó là string, không phải số.

Ví dụ:

~~~csv
accountCode
000012345678901234
~~~

Nếu consumer tự suy diễn thành numeric, số 0 đầu có thể mất và số chữ số có thể bị thay đổi. Với ID, mã bưu chính, số tài khoản và mã sản phẩm, khai báo cột là text trong quy trình import của công cụ ngoài.

### 13.2. Decimal và dấu thập phân

Một số môi trường dùng dấu chấm làm decimal separator, môi trường khác dùng dấu phẩy. CSV có delimiter dấu phẩy có thể xung đột với locale dùng dấu phẩy cho decimal.

Hãy xác định:

- Decimal separator luôn là dấu chấm hay theo locale?
- Grouping separator có xuất hiện không?
- Số âm được biểu diễn ra sao?
- Có giữ trailing zero không?
- Consumer có tự parse theo locale máy không?

Đối với file trao đổi máy-máy, dùng biểu diễn canonical và không thêm grouping separator thường dễ tương thích hơn. Kiểm tra decimal bằng BigDecimal thay vì double để tránh sai số nhị phân.

### 13.3. Ngày và giờ

CSV không có kiểu date/time. Một cột thời gian cần format đã thống nhất, thường là ISO-8601:

~~~csv
id,createdAt
P-001,2025-01-02T10:15:30Z
~~~

Nếu chỉ có local date/time mà không có timezone, cần quy định timezone hoặc semantics rõ. Không để consumer tự đoán timezone theo máy đang mở file.

Với các kiểu java.time, đăng ký JavaTimeModule khi cần và cấu hình format thống nhất. Interoperability test nên đọc fixture do công cụ ngoài xuất để xác nhận format thực tế được chấp nhận.

## 14. CSV column order và header evolution

Nếu thêm property mới vào DTO, schema CSV không nhất thiết tự thay đổi theo cách mong muốn. Khi dùng CsvSchema tường minh, chỉ các cột được khai báo mới được ghi.

Điều này có thể là lợi thế vì wire format không tự thay đổi khi thêm field Java. Nhưng nó cũng có nghĩa field mới sẽ không xuất hiện nếu schema chưa được cập nhật.

Nên quản lý schema như một contract có version:

~~~text
payments-v1.csv
id,amount,currency,status

payments-v2.csv
id,amount,currency,status,channel
~~~

Khi consumer cũ đọc file mới:

- Nếu có header và bỏ qua cột lạ, có thể tiếp tục đọc subset.
- Nếu strict unknown column, cần từ chối và yêu cầu version phù hợp.
- Nếu không có header, thêm cột giữa file có thể làm lệch mọi cột phía sau.

Không nên thay đổi thứ tự cột trong file không header mà không tăng version.

## 15. CSV có nested object hoặc collection

CSV là bảng hai chiều, không biểu diễn trực tiếp object graph như YAML/JSON. Khi DTO có nested object:

~~~java
public class Customer {
    private String id;
    private String name;
}

public class Order {
    private String id;
    private Customer customer;
    private List<OrderLine> lines;
}
~~~

cần chọn một quy ước:

1. Flatten thành cột như `customerId`, `customerName`.
2. Một order nhiều line thì xuất mỗi line thành một row, lặp các cột order-level.
3. Tách thành nhiều file CSV có khóa liên kết.
4. Đóng gói nested value thành JSON string trong một cột nếu consumer hỗ trợ và contract cho phép.

Không nên giả định CsvMapper tự biến nested graph thành một schema relational phù hợp với mọi công cụ. Hãy thiết kế export DTO riêng cho CSV thay vì serialize trực tiếp persistence entity phức tạp.

### 15.1. Một dòng cho mỗi record hay một dòng cho mỗi child?

Ví dụ order có nhiều line. Có thể dùng bảng:

~~~csv
orderId,customerId,lineSku,quantity
ORD-1,CUS-1,SKU-1,2
ORD-1,CUS-1,SKU-2,1
~~~

Consumer hiểu mỗi row là một order line, còn order/customer được lặp theo từng row. Cần ghi rõ grain của bảng: một row đại diện cho order, order line, customer hay một event.

Nếu không định nghĩa grain, consumer có thể đếm order trùng hoặc cộng tổng tiền nhiều lần.

## 16. Tương tác với Python và pandas

pandas là một consumer phổ biến của CSV. Ví dụ đọc file:

~~~python
import pandas as pd

df = pd.read_csv(
    "payments.csv",
    dtype={
        "id": "string",
        "currency": "string",
        "status": "string"
    }
)
~~~

Dùng dtype rõ ràng giúp giữ mã định danh dưới dạng string. Nếu để pandas tự suy luận, các cột có thể bị chuyển thành số hoặc kiểu khác dựa trên dữ liệu mẫu.

Khi ghi lại:

~~~python
df.to_csv(
    "payments-export.csv",
    index=False,
    encoding="utf-8"
)
~~~

`index=False` tránh thêm một cột index không thuộc schema ban đầu. Encoding cần được chốt với consumer. Nếu pandas ghi thêm index mặc định, Jackson có thể thấy một cột ngoài hợp đồng.

### 16.1. Test hai chiều giữa Jackson và pandas

Một quy trình interoperability test có thể là:

~~~text
Java fixture objects
       |
       v
Jackson CsvMapper writes payments.csv
       |
       v
Python pandas reads payments.csv
       |
       v
Assertions on columns, dtypes and values
       |
       v
pandas writes payments-export.csv
       |
       v
Jackson CsvMapper reads payments-export.csv
       |
       v
Assertions on restored DTOs
~~~

Test Python nên kiểm tra:

- Tên và thứ tự cột.
- Số lượng row.
- Dtype của ID và decimal.
- Null/empty behavior.
- Giá trị có dấu phẩy, quote và Unicode.
- Không có cột index thừa.

Test Java nên đọc file pandas xuất ra bằng cùng schema contract. Nếu môi trường build không cài Python/pandas, có thể chạy interoperability test ở pipeline riêng hoặc dùng file fixture đã được tạo bởi phiên bản pandas đã chốt.

### 16.2. CSV không phải spreadsheet workbook

Một file .csv không lưu kiểu cell, format number, formula, width hoặc style như .xlsx. Excel có thể tự suy luận kiểu khi mở CSV, nhưng việc hiển thị đúng trên một máy không chứng minh bytes trong file đã giữ nguyên giá trị.

Nếu consumer cần kiểu cột, công thức hoặc format hiển thị, cân nhắc XLSX thay vì CSV.

## 17. Tương tác với Excel và LibreOffice

Spreadsheet thường có các hành vi tự động:

- Nhận diện ngày theo locale.
- Chuyển mã có số 0 đầu thành number.
- Làm tròn số dài.
- Diễn giải decimal theo dấu phân cách của locale.
- Tự nhận diện delimiter khác nhau.
- Thêm hoặc thay đổi quote/line ending khi lưu lại.
- Tự động tạo hyperlink hoặc formula từ nội dung.

Nếu người dùng mở rồi Save As CSV, file có thể thay đổi encoding, delimiter hoặc kiểu dữ liệu so với file ban đầu.

Đối với file trao đổi với người dùng spreadsheet:

- Cung cấp hướng dẫn import chọn encoding, delimiter và dtype.
- Không dựa vào double-click để tự nhận diện.
- Giữ ID và code dưới dạng text.
- Xác định rõ locale và decimal format.
- Kiểm thử file được lưu lại từ phiên bản spreadsheet được hỗ trợ.

### 17.1. CSV formula injection

Nếu dữ liệu không tin cậy được xuất vào CSV rồi mở bằng spreadsheet, cell bắt đầu bằng các ký tự như `=`, `+`, `-` hoặc `@` có thể bị diễn giải như formula tùy công cụ và cấu hình.

Ví dụ một giá trị do người dùng gửi:

~~~csv
name
=HYPERLINK("https://example.invalid","open")
~~~

Khi mở trong spreadsheet, cell có thể được xem là công thức thay vì text. Đây là rủi ro CSV formula injection.

Nếu CSV được dùng để mở trong spreadsheet, cần chính sách export an toàn cho text không tin cậy. Một số hệ thống thêm apostrophe ở đầu hoặc biến đổi giá trị theo quy tắc riêng, nhưng cách xử lý phụ thuộc spreadsheet và có thể làm thay đổi dữ liệu khi import lại. Hãy phân biệt:

- CSV dành cho máy-máy cần giữ nguyên dữ liệu.
- CSV dành cho người dùng mở trong spreadsheet cần giảm rủi ro formula execution.

Có thể cung cấp hai export profile khác nhau thay vì âm thầm biến đổi mọi CSV.

## 18. Encoding, BOM và line ending

Một file có nội dung đúng vẫn có thể bị công cụ ngoài đọc sai vì encoding hoặc line ending.

### 18.1. UTF-8

Nên chốt UTF-8 trong contract và đọc/ghi file bằng charset tường minh:

~~~java
try (Writer writer = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8
); SequenceWriter sequence = csvMapper.writer(schema).writeValues(writer)) {
    sequence.writeAll(rows);
}
~~~

Khi đọc:

~~~java
try (Reader reader = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8
)) {
    List<PaymentRow> rows = readRows(reader);
}
~~~

Không dùng charset mặc định của máy. Cùng file có thể bị giải mã khác nhau giữa Windows, Linux hoặc container.

### 18.2. UTF-8 BOM

Một số công cụ spreadsheet xuất CSV UTF-8 có BOM để giúp nhận diện encoding. Một số parser có thể coi BOM là ký tự đầu của header, khiến cột đầu trở thành tên như `﻿id` thay vì `id`.

Nếu cần tương thích với tool xuất BOM, hãy kiểm thử rõ. Có thể xử lý BOM tại byte/reader boundary trước khi đưa nội dung vào CsvMapper. Đừng xóa ký tự BOM ở giữa file hoặc thay đổi mọi string field một cách vô điều kiện.

### 18.3. LF và CRLF

Các công cụ có thể ghi LF hoặc CRLF. CSV parser nên xử lý line ending theo dialect được hỗ trợ. Nếu contract yêu cầu CRLF, kiểm tra byte output; nếu consumer chấp nhận cả hai, test cả hai fixture.

Không dùng `String.split("\\n")` để đếm record vì field được quote có thể chứa newline hợp lệ.

## 19. Test schema CSV khi có và không có header

Với header, tên cột giúp ánh xạ property:

~~~csv
id,amount,currency,status
P-001,125.50,VND,PAID
~~~

Dùng:

~~~java
CsvSchema schema = CsvSchema.emptySchema().withHeader();
~~~

Nếu file không có header:

~~~csv
P-001,125.50,VND,PAID
P-002,80.00,USD,PENDING
~~~

consumer phải dùng schema có thứ tự cột cố định:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id")
        .addColumn("amount")
        .addColumn("currency")
        .addColumn("status")
        .build();
~~~

Test cần bảo đảm producer và consumer dùng cùng column order. Với file không header, không có cách đáng tin cậy để suy ra cột chỉ từ dữ liệu nếu các giá trị đều là text hoặc có format giống nhau.

### 19.1. Header trùng hoặc thiếu

Header có thể bị sai do spreadsheet chỉnh sửa, ví dụ:

~~~csv
id,amount,amount,status
~~~

Hoặc thiếu cột:

~~~csv
id,amount,status
~~~

Hãy quyết định consumer strict đến mức nào. Nếu schema yêu cầu currency, test cần xác nhận thiếu cột bị từ chối hoặc được default theo policy đã công bố. Không để giá trị null/default xuất hiện mà không có validation.

## 20. Kiểm thử file thật thay vì chỉ string trong bộ nhớ

Một số lỗi chỉ xuất hiện khi ghi và đọc bytes:

- Encoding không như dự kiến.
- BOM ở đầu file.
- Line ending khác nhau.
- File bị truncate.
- Writer chưa flush/close.
- Path hoặc quyền truy cập sai.
- Consumer đọc file trước khi producer hoàn tất.

Test file:

~~~java
@Test
void shouldWriteAndReadCsvFileAsUtf8() throws Exception {
    Path file = tempDir.resolve("payments.csv");

    CsvMapper mapper = new CsvMapper();

    CsvSchema schema = CsvSchema.builder()
            .addColumn("id")
            .addColumn("amount")
            .addColumn("currency")
            .setUseHeader(true)
            .build();

    List<PaymentRow> payments = List.of(
            payment("P-001", new BigDecimal("125.50"), "VND", "PAID")
    );

    try (Writer writer = Files.newBufferedWriter(
            file,
            StandardCharsets.UTF_8
    ); SequenceWriter sequence = mapper.writer(schema).writeValues(writer)) {
        sequence.writeAll(payments);
    }

    try (Reader reader = Files.newBufferedReader(
            file,
            StandardCharsets.UTF_8
    )) {
        CsvSchema readSchema = CsvSchema.emptySchema().withHeader();

        List<PaymentRow> restored;
        try (MappingIterator<PaymentRow> iterator =
                mapper.readerFor(PaymentRow.class)
                        .with(readSchema)
                        .readValues(reader)) {
            restored = iterator.readAll();
        }

        assertEquals(1, restored.size());
        assertEquals("P-001", restored.get(0).getId());
    }
}
~~~

Test này kiểm tra file đã đóng và đọc lại từ filesystem. Nó vẫn chưa thay thế interoperability test với consumer ngoài.

## 21. Compatibility test khi thay đổi Jackson hoặc DTO

Nâng Jackson, SnakeYAML, Woodstox hoặc CSV module có thể thay đổi chi tiết parse/generate. Thay đổi DTO cũng có thể ảnh hưởng property names, defaults, enum và schema.

Nên duy trì fixture versioned:

~~~text
fixtures/
  yaml/
    config-v1.yaml
    config-v2.yaml
  csv/
    payments-v1.csv
    payments-v2.csv
~~~

Các test nên xác nhận:

- DTO hiện tại đọc được file version cũ theo chính sách tương thích.
- Serializer hiện tại phát đúng format version đang công bố.
- Consumer cũ có thể đọc subset nếu contract yêu cầu backward compatibility.
- Enum mới hoặc unknown value có behavior rõ.
- Field mới có default hợp lệ hoặc được đánh dấu required.
- Cột mới được thêm đúng vị trí và header.
- Không có property vô tình biến mất sau refactor.

Nếu format thay đổi không tương thích, tăng version contract và cung cấp migration/converter. Không dùng test snapshot để che giấu breaking change.

## 22. Kiểm thử property order và textual output

Với YAML, thứ tự property thường không nên là yếu tố semantic trừ khi consumer ngoài có yêu cầu riêng. YAML mapping về bản chất không nên được dùng như một sequence có thứ tự nghiệp vụ. Nếu output order quan trọng cho review hoặc tool legacy, cấu hình và test riêng.

Với CSV, thứ tự cột có ý nghĩa trực tiếp khi file không có header và thường vẫn là một phần giao ước ngay cả khi có header. Test header order và row order nếu consumer phụ thuộc.

Không nên so sánh toàn bộ YAML text theo snapshot nếu indentation, quote style hoặc line ending không phải contract. Thay vào đó:

- Parse YAML output thành DTO hoặc tree rồi so sánh values.
- Assert những textual detail thật sự quan trọng riêng.
- Với CSV, kiểm tra header, delimiter, quoting, record count và giá trị sau parse.
- Giữ fixture bytes khi cần test encoding/BOM/line ending.

## 23. Kiểm thử unknown fields và forward compatibility

Khi producer thêm field mới, consumer cũ có thể:

- Từ chối file.
- Bỏ qua field.
- Giữ field chưa biết.
- Đọc một subset và tiếp tục.

Mỗi hành vi có trade-off.

Ví dụ YAML có field mới:

~~~yaml
id: U-100
name: An
newPreference:
  theme: dark
~~~

Ví dụ CSV có cột mới:

~~~csv
id,name,newPreference
U-100,An,dark
~~~

Đối với CSV có header, consumer có thể ánh xạ các cột đã biết và bỏ qua cột không biết tùy schema/configuration. Với file không header, cột mới có thể làm lệch vị trí của các cột sau. Vì vậy, header giúp mở rộng dễ hơn nhưng không tự giải quyết mọi vấn đề compatibility.

Test phải dùng đúng cấu hình unknown-field của production. Không bật tolerant mode chỉ để test pass nếu hợp đồng yêu cầu strict schema.

## 24. Tách export model khỏi persistence model

Một entity trong database có thể chứa lazy relationship, internal field, audit metadata hoặc object graph phức tạp. Serialize trực tiếp entity thành YAML/CSV có thể tạo output khó ổn định và lộ field ngoài ý muốn.

Nên tạo export DTO rõ ràng:

~~~java
public class PaymentExportRow {
    private String paymentId;
    private String accountCode;
    private BigDecimal amount;
    private String currency;
    private String createdAt;
}
~~~

Export DTO xác định:

- Tên cột và thứ tự cột.
- Format ngày giờ.
- Quy tắc decimal.
- Cách biểu diễn null.
- Field được phép chia sẻ với đối tác.
- Version của file.

Khi schema bên ngoài thay đổi, chỉ cần điều chỉnh export DTO và mapping, không buộc persistence model thay đổi theo.

## 25. Ma trận kiểm thử YAML và CSV

Một ma trận thực tế có thể bao gồm:

| Nhóm | YAML | CSV |
|---|---|---|
| Round-trip | Object → YAML → Object | Rows → CSV → Rows |
| External fixture | File từ Python/config tool | File từ pandas/Excel/ETL |
| Encoding | UTF-8, BOM nếu hỗ trợ | UTF-8, BOM, CRLF/LF |
| Scalar/type | Boolean, number, date-like string | Decimal, integer, ID dạng text |
| Null/empty | null, empty string, missing | Blank cell, quoted empty, sentinel |
| Special characters | Unicode, quote, colon, multiline scalar | Delimiter, quote, newline, Unicode |
| Schema evolution | Field mới/thiếu/unknown | Header mới, thiếu cột, reorder |
| Security | Tags, aliases, parser limits nếu input không tin cậy | Formula injection, oversized field |
| Compatibility | Fixture version cũ | CSV version cũ |
| External consumer | YAML parser độc lập | pandas, spreadsheet hoặc ETL tool |

Không nhất thiết mọi dự án phải kiểm thử tất cả dòng. Hãy chọn theo consumer thực tế và rủi ro của dữ liệu.

## 26. Những lỗi thường gặp

**Chỉ test Jackson đọc lại output của chính nó.** Test này không chứng minh tool ngoài hiểu cùng semantics. Hãy có fixture độc lập hoặc interoperability test.

**So sánh YAML bằng chuỗi tuyệt đối.** Quote style, indentation hoặc property order có thể thay đổi mà dữ liệu vẫn tương đương. Parse rồi so sánh values, trừ khi text format là contract.

**Để spreadsheet tự suy luận ID là số.** Số 0 đầu hoặc chữ số dài có thể bị mất. Đặt dtype text khi import.

**Không cố định CSV header và column order.** Consumer có thể đọc sai field hoặc không biết cột nào tương ứng property nào.

**Tự split CSV theo newline hoặc comma.** Quoted field có thể chứa delimiter và newline. Dùng parser CSV.

**Cho rằng blank cell luôn là null.** CSV không có null semantics phổ quát. Định nghĩa convention và test.

**Không test decimal/locale.** Dấu phẩy/dấu chấm có thể bị hiểu khác nhau giữa các môi trường.

**Không test BOM và line ending.** Header đầu file có thể dính BOM; một số consumer nhạy với CRLF/LF.

**Ghi nested object trực tiếp vào CSV mà không có grain.** Hãy flatten, tách bảng hoặc dùng một cột JSON theo contract.

**Dùng cùng DTO persistence cho mọi file export.** Field nội bộ hoặc quan hệ lazy có thể lọt vào output. Dùng export DTO.

**Cập nhật fixture cũ sau mỗi thay đổi mà không review.** Điều này có thể che giấu breaking change. Giữ fixture versioned và kiểm tra migration.

**Không kiểm tra formula injection.** CSV mở trong spreadsheet có thể diễn giải text không tin cậy thành công thức.

## 27. Quy trình triển khai kiểm thử khả năng nhập lại

Khi xây dựng YAML/CSV exchange:

1. Xác định consumer: Jackson nội bộ, Python/pandas, spreadsheet, ETL hay hệ thống đối tác.
2. Chốt format contract: encoding, line ending, header, column order, null, date, decimal và schema version.
3. Tạo export DTO/schema riêng, không serialize tùy tiện persistence entity.
4. Viết round-trip test cho YAML/CSV.
5. Tạo fixture từ consumer/producer bên ngoài và test đọc vào.
6. Nếu file do Jackson phát ra được công cụ ngoài dùng, test consumer đó đọc fixture thật.
7. Nếu công cụ ngoài ghi lại file, test Jackson đọc file đã được tool xuất.
8. Kiểm tra special characters, null/empty, số 0 đầu, decimal và ngày giờ.
9. Giữ fixture version cũ để test compatibility.
10. Kiểm tra bytes thực tế: UTF-8, BOM, CRLF/LF và file đã đóng hoàn chỉnh.
11. Chạy test trên phiên bản Jackson và external tool được hỗ trợ.
12. Chỉ cập nhật fixture hoặc schema version khi thay đổi contract đã được chấp thuận.

## 28. Kết luận

Kiểm thử YAML/CSV cần vượt ra ngoài việc gọi serialize rồi deserialize bằng cùng một mapper. Round-trip test xác nhận Jackson giữ được giá trị qua hai chiều; fixture test xác nhận ứng dụng đọc được file đã tồn tại; interoperability test xác nhận công cụ ngoài hiểu header, scalar, encoding, null, date, decimal và quoting theo cùng hợp đồng; compatibility test bảo vệ file cũ khi model hoặc thư viện thay đổi.

Với YAML, chú ý cách các parser diễn giải scalar, null, anchors, aliases và tags. Với CSV, chốt schema cột, header, delimiter, quoting, line ending và quy tắc null vì định dạng không mang type metadata đầy đủ. Đặc biệt, ID có số 0 đầu phải được giữ dưới dạng text và file mở trong spreadsheet cần được đánh giá nguy cơ formula injection. Khi có fixture độc lập, export DTO rõ ràng và test với consumer thực tế, các file Jackson tạo ra sẽ đáng tin cậy hơn ở ranh giới giữa các công cụ.

## Tài liệu tham khảo

- [Jackson Dataformat YAML](https://github.com/FasterXML/jackson-dataformats-text/tree/2.x/yaml)
- [Jackson Dataformat CSV](https://github.com/FasterXML/jackson-dataformats-text/tree/2.x/csv)
- [Jackson YAML — YAMLFactory API](https://javadoc.io/doc/com.fasterxml.jackson.dataformat/jackson-dataformat-yaml/latest/com/fasterxml/jackson/dataformat/yaml/YAMLFactory.html)
- [Jackson CSV — CsvMapper API](https://javadoc.io/doc/com.fasterxml.jackson.dataformat/jackson-dataformat-csv/latest/com/fasterxml/jackson/dataformat/csv/CsvMapper.html)
- [Jackson CSV — CsvSchema API](https://javadoc.io/doc/com.fasterxml.jackson.dataformat/jackson-dataformat-csv/latest/com/fasterxml/jackson/dataformat/csv/CsvSchema.html)
- [pandas — read_csv](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html)
- [pandas — DataFrame.to_csv](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_csv.html)
- [OWASP CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection)
- [YAML 1.2.2 Specification](https://yaml.org/spec/1.2.2/)

