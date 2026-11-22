# Phân biệt khóa nghiệp vụ và tên trường động

Khi thiết kế JSON, một object có thể chứa các property đã biết trước hoặc một tập khóa thay đổi theo dữ liệu. Hai khái niệm dễ bị nhầm là **khóa nghiệp vụ** và **tên trường động**.

- **Khóa nghiệp vụ** là định danh có ý nghĩa trong miền nghiệp vụ, ví dụ mã sản phẩm, mã vùng, mã tiền tệ hoặc mã chỉ số. Nó có quy tắc hợp lệ, cách chuẩn hóa và ý nghĩa ổn định.
- **Tên trường động** là tên property trong JSON không được khai báo cố định trong DTO. Tên đó có thể thay đổi theo đối tác, cấu hình hoặc phần mở rộng của schema.

Một khóa nghiệp vụ đôi khi được đặt ở vị trí tên property của JSON object, ví dụ mã vùng trong một Map. Khi đó nó vừa là tên property ở cấp cú pháp JSON, vừa mang ý nghĩa khóa nghiệp vụ. Jackson chuyển tên property thành key của Map; domain model vẫn cần xác thực ý nghĩa của key.

Bài học này giải thích cách phân biệt các trường hợp đó và lựa chọn giữa DTO, Map, @JsonAnySetter, @JsonAnyGetter, key serializer/deserializer và cấu trúc array các entry.

## 1. Hai khái niệm nằm ở hai lớp khác nhau

JSON object được tạo bởi các cặp tên property và giá trị:

```json
{
  "sku": "SKU-1001",
  "name": "Keyboard",
  "stock": 25
}
```

Trong ví dụ trên, sku, name và stock là tên property. SKU-1001 là giá trị của property sku, đồng thời là khóa nghiệp vụ vì nó định danh sản phẩm theo quy tắc của hệ thống. Tên property sku thường cố định trong schema; giá trị SKU thay đổi theo từng sản phẩm nhưng không làm schema có thêm property mới.

Một JSON object khác có thể dùng chính mã SKU làm tên property:

```json
{
  "SKU-1001": {
    "name": "Keyboard",
    "stock": 25
  },
  "SKU-1002": {
    "name": "Mouse",
    "stock": 80
  }
}
```

Ở đây, SKU-1001 và SKU-1002 là các tên property động theo cú pháp JSON. Về ý nghĩa nghiệp vụ, chúng cũng là mã sản phẩm. Mỗi key có thể được ánh xạ thành một phần tử trong Map<BusinessKey, ProductStock>.

Một trường hợp khác:

```json
{
  "eventId": "evt-100",
  "eventType": "USER_CREATED",
  "x-partner-trace": "trace-abc",
  "customColor": "blue",
  "vendorFlag": true
}
```

Các tên x-partner-trace, customColor và vendorFlag là property mở rộng mà DTO hiện tại chưa biết. Chúng là tên trường động. Chúng không nhất thiết là khóa nghiệp vụ; có thể chỉ là metadata do nguồn dữ liệu bổ sung.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Tên property cố định | Schema quy định trường nào? | sku, eventId, createdAt |
| Giá trị khóa nghiệp vụ | Giá trị nào định danh một thực thể/nhóm? | SKU-1001, VN, USD |
| Tên trường động | Payload có thể thêm tên property nào chưa biết? | x-partner-trace, customColor |
| Key của Map | Mỗi entry trong dictionary được định danh bằng gì? | Map<BusinessKey, BigDecimal> |

Không nên coi mọi tên property thay đổi là khóa nghiệp vụ. Cũng không nên coi mọi khóa nghiệp vụ là một property động. Ý nghĩa phụ thuộc vào hợp đồng dữ liệu và vị trí của giá trị trong JSON.

## 2. Nhận diện đúng hình dạng JSON trước khi chọn kiểu Java

Ba payload dưới đây có thể trông gần nhau nhưng biểu diễn ba hợp đồng khác nhau.

### 2.1. Khóa nghiệp vụ là giá trị của property cố định

```json
{
  "sku": "SKU-1001",
  "quantity": 25
}
```

Đây là object có schema cố định. Mã SKU nằm trong value của property sku. DTO/record là lựa chọn tự nhiên:

```java
public record StockItem(
    String sku,
    int quantity
) {}
```

Jackson không cần Map key serializer hoặc @JsonAnySetter cho trường hợp này.

### 2.2. Khóa nghiệp vụ được dùng làm key của dictionary

```json
{
  "SKU-1001": 25,
  "SKU-1002": 80
}
```

Đây là một JSON object dùng các mã SKU làm tên property. Nếu tất cả value có cùng ý nghĩa và kiểu, mô hình Map phù hợp:

```java
Map<String, Integer> stockBySku = mapper.readValue(
    json,
    new TypeReference<Map<String, Integer>>() {}
);
```

Nếu muốn domain model kiểm soát định dạng SKU, có thể dùng key type riêng và đăng ký key deserializer.

### 2.3. Payload có property mở rộng chưa biết trước

```json
{
  "eventId": "evt-100",
  "eventType": "USER_CREATED",
  "x-partner-trace": "trace-abc",
  "customColor": "blue"
}
```

Đây là object có một phần schema cố định và một phần property mở rộng. @JsonAnySetter có thể nhận các property chưa được khai báo vào Map; @JsonAnyGetter có thể xuất Map đó trở lại thành property ở cấp object.

Không nên đưa tất cả trường hợp vào một Map<String, Object> chỉ vì chúng đều xuất hiện dưới dạng tên property trong JSON. Hãy chọn kiểu Java theo ý nghĩa và quy tắc của dữ liệu.

## 3. Khi nào dùng DTO và property cố định?

Nếu tên trường là một phần ổn định của hợp đồng, khai báo nó trong DTO/record:

```java
public record ProductDto(
    String sku,
    String name,
    BigDecimal price,
    int stock
) {}
```

Ưu điểm:

- Compiler kiểm tra kiểu dữ liệu.
- IDE hỗ trợ điều hướng và đổi tên.
- Có thể áp dụng validation cho từng property.
- Hợp đồng JSON dễ đọc và dễ tạo tài liệu.
- Lỗi thiếu hoặc sai kiểu có thể được phát hiện khi deserialize hoặc validate.

Dùng @JsonProperty khi tên JSON khác tên component/field Java:

```java
public record ProductDto(
    @JsonProperty("product_code") String sku,
    String name
) {}
```

Ở đây product_code vẫn là tên property cố định. sku là tên component Java. Annotation không biến property thành trường động.

@JsonAlias có thể nhận nhiều tên đầu vào tương thích:

```java
public record ProductDto(
    @JsonProperty("product_code")
    @JsonAlias({"sku", "legacyCode"})
    String sku
) {}
```

Alias là các tên thay thế đã biết trước cho cùng một property. Nó không có nghĩa DTO có thể nhận mọi tên property mới.

Nếu một tên trường được định nghĩa bởi hợp đồng API, hãy khai báo tường minh bằng DTO, @JsonProperty hoặc naming strategy. Không dùng cơ chế dynamic field để che giấu một schema thực ra đã cố định.

## 4. Khóa nghiệp vụ trong Map

Một JSON object có thể được dùng như dictionary khi mọi entry cùng tuân theo một quy tắc:

```json
{
  "USD": 1.0,
  "EUR": 0.92,
  "JPY": 150.25
}
```

Các key có thể là mã tiền tệ. Value là tỷ giá theo một quy ước đã định nghĩa.

Mô hình Java:

```java
Map<String, BigDecimal> rates = mapper.readValue(
    json,
    new TypeReference<Map<String, BigDecimal>>() {}
);
```

Tên property trong JSON luôn là string. Vì vậy, Map<String, ...> là cách ánh xạ trực tiếp nhất.

Nếu key có kiểu domain riêng, ví dụ CurrencyCode, nên thể hiện kiểu đó trong Java để xác thực và tránh truyền nhầm chuỗi tùy ý:

```java
public record CurrencyCode(String value) {
    public CurrencyCode {
        Objects.requireNonNull(value, "value");

        if (!value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must contain three uppercase letters"
            );
        }
    }
}
```

Sau đó có thể khai báo:

```java
Map<CurrencyCode, BigDecimal> rates;
```

Nhưng Jackson cần biết cách chuyển tên property dạng String thành CurrencyCode. Đây là nhiệm vụ của key deserializer.

### 4.1. Không nhầm key của Map với value của Map

Với JSON:

```json
{
  "USD": 1.0,
  "EUR": 0.92
}
```

USD và EUR là key; 1.0 và 0.92 là value. Key không phải một object JSON độc lập và không thể chứa nhiều property. Nếu một khóa cần thêm metadata, ví dụ mã, tên hiển thị, nguồn và thời điểm hiệu lực, object JSON keyed by code có thể không còn là cấu trúc phù hợp.

Khi key có metadata riêng, cân nhắc array các entry:

```json
{
  "rates": [
    {
      "currency": "USD",
      "rate": 1.0,
      "source": "provider-a"
    },
    {
      "currency": "EUR",
      "rate": 0.92,
      "source": "provider-b"
    }
  ]
}
```

Lúc này currency là một property có kiểu rõ ràng trong mỗi phần tử. Cấu trúc array linh hoạt hơn khi mỗi entry cần nhiều thông tin ngoài key và value.

### 4.2. Kiểm tra tính duy nhất và chuẩn hóa business key

Một khóa nghiệp vụ cần quy tắc chuẩn hóa rõ ràng. Ví dụ các chuỗi usd, USD và có khoảng trắng xung quanh có thể được xem là cùng một mã sau khi trim/uppercase.

Nếu ứng dụng chuẩn hóa key khi đọc, cần phát hiện va chạm:

- usd và USD cùng chuẩn hóa thành USD.
- Hai entry khác nhau trong JSON có thể ghi đè nhau sau chuẩn hóa.
- Một key rỗng hoặc sai định dạng không nên âm thầm trở thành key hợp lệ.

Không nên dùng Map.put để ghi đè một key đã tồn tại sau chuẩn hóa mà không có chính sách. Hãy từ chối dữ liệu trùng hoặc định nghĩa rõ quy tắc ưu tiên.

Ngoài ra, parser có thể được cấu hình phát hiện duplicate JSON property name ở tầng Core. Việc đó phát hiện cùng một tên key lặp trong văn bản JSON. Nó không thay thế kiểm tra va chạm sau khi ứng dụng chuẩn hóa hai chuỗi key khác nhau thành cùng một business key.

## 5. Key serializer và key deserializer

Jackson Databind dùng serializer/deserializer riêng cho key của Map vì key JSON object luôn được ghi ở vị trí tên property, không phải value thông thường.

- JsonSerializer dùng cho value thông thường.
- Key serializer ghi tên property của Map.
- KeyDeserializer chuyển tên property từ JSON thành kiểu key Java.

Với Map<CurrencyCode, BigDecimal>, cần định nghĩa cách ghi CurrencyCode thành tên property và cách đọc tên property thành CurrencyCode.

### 5.1. Tạo key deserializer

```java
public final class CurrencyCodeKeyDeserializer
        extends KeyDeserializer {

    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext context
    ) throws IOException {
        try {
            return new CurrencyCode(key);
        } catch (IllegalArgumentException ex) {
            throw context.weirdKeyException(
                CurrencyCode.class,
                key,
                ex.getMessage()
            );
        }
    }
}
```

Deserializer nhận key dưới dạng String vì JSON object property name là text. Nó tạo domain key sau khi constructor xác thực định dạng.

Nếu key không hợp lệ, báo lỗi mapping với thông tin key thay vì trả về một giá trị mặc định hoặc bỏ qua entry.

### 5.2. Tạo key serializer

```java
public final class CurrencyCodeKeySerializer
        extends JsonSerializer<CurrencyCode> {

    @Override
    public void serialize(
            CurrencyCode value,
            JsonGenerator generator,
            SerializerProvider serializers
    ) throws IOException {
        generator.writeFieldName(value.value());
    }
}
```

Key serializer phải ghi field name bằng writeFieldName. Không dùng writeString vì nó tạo một JSON string value, không phải tên property của object.

### 5.3. Đăng ký serializer và deserializer bằng SimpleModule

```java
SimpleModule module = new SimpleModule();

module.addKeySerializer(
    CurrencyCode.class,
    new CurrencyCodeKeySerializer()
);

module.addKeyDeserializer(
    CurrencyCode.class,
    new CurrencyCodeKeyDeserializer()
);

ObjectMapper mapper = new ObjectMapper()
    .registerModule(module);
```

Sau khi đăng ký, Jackson có thể đọc:

```java
Map<CurrencyCode, BigDecimal> rates = mapper.readValue(
    json,
    new TypeReference<Map<CurrencyCode, BigDecimal>>() {}
);
```

Và serialize lại Map thành object có tên property là mã tiền tệ:

```java
String output = mapper.writeValueAsString(rates);
```

Kết quả:

```json
{
  "USD": 1.0,
  "EUR": 0.92
}
```

Hãy đăng ký module trên đúng ObjectMapper mà ứng dụng sử dụng. Trong Spring Boot, mapper dùng cho HTTP có thể được cấu hình qua builder/customizer; một mapper mới được tạo riêng trong service không tự động nhận module của mapper framework.

### 5.4. Key serializer/deserializer ở cấp property

Nếu chỉ một Map property cần quy tắc riêng, có thể cấu hình ngay trên property:

```java
public record ExchangeRates(
    @JsonSerialize(keyUsing = CurrencyCodeKeySerializer.class)
    @JsonDeserialize(keyUsing = CurrencyCodeKeyDeserializer.class)
    Map<CurrencyCode, BigDecimal> rates
) {}
```

Cách này giới hạn quy tắc vào một property thay vì áp dụng cho mọi Map có key kiểu CurrencyCode. Chọn module toàn cục khi quy tắc là quy ước chung của kiểu key; chọn annotation khi từng property có hợp đồng riêng.

## 6. Tên trường động với @JsonAnySetter

Một DTO có thể chứa các property cố định và nhận thêm property chưa biết trước. @JsonAnySetter cho phép Jackson chuyển các property còn lại vào một method hoặc field phù hợp.

Ví dụ payload:

```json
{
  "eventId": "evt-100",
  "eventType": "USER_CREATED",
  "x-partner-trace": "trace-abc",
  "customColor": "blue",
  "vendorFlag": true
}
```

DTO có thể giữ các field chuẩn riêng và lưu phần mở rộng vào Map:

```java
public class PartnerEvent {

    private String eventId;
    private String eventType;

    private final Map<String, JsonNode> extensions =
        new LinkedHashMap<>();

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> extensionProperties() {
        return extensions;
    }
}
```

Khi deserialize:

- eventId được gán vào property cố định.
- eventType được gán vào property cố định.
- Những property chưa được nhận diện như x-partner-trace, customColor và vendorFlag được chuyển vào extensions.

JsonNode giữ hình dạng JSON của từng giá trị động. Một extension có thể là string, number, boolean, null, array hoặc object mà không cần ép tất cả thành String.

Nếu cấu trúc dynamic đã biết chỉ chứa scalar đơn giản, có thể dùng Map<String, Object>. Nếu payload có cấu trúc lồng nhau hoặc cần kiểm tra kiểu chính xác, Map<String, JsonNode> thường thuận tiện hơn.

### 6.1. @JsonAnySetter không phải một property Map thông thường

Nếu khai báo:

```java
public class PartnerEvent {
    private Map<String, JsonNode> extensions;
}
```

Jackson sẽ xem extensions là một property thông thường nếu có accessor và cấu hình visibility phù hợp. JSON có thể phải có wrapper:

```json
{
  "eventId": "evt-100",
  "extensions": {
    "x-partner-trace": "trace-abc",
    "customColor": "blue"
  }
}
```

Còn @JsonAnySetter nhận các property không biết ở cùng cấp với eventId. Nó không cần một property tên extensions trong JSON.

Đây là khác biệt quan trọng giữa Map lồng trong một property và Map chứa các property động của chính object.

## 7. Xuất tên trường động bằng @JsonAnyGetter

@JsonAnyGetter cho phép Jackson ghi các entry của Map thành property ở cấp object hiện tại.

Với class ở phần trước, các extension được serialize thành:

```json
{
  "eventId": "evt-100",
  "eventType": "USER_CREATED",
  "x-partner-trace": "trace-abc",
  "customColor": "blue",
  "vendorFlag": true
}
```

Map không xuất hiện như một property có tên extensions. Các entry của Map được trải phẳng vào object.

Nếu không muốn trải phẳng, hãy bỏ @JsonAnyGetter và khai báo Map như một property bình thường:

```java
public record PartnerEvent(
    String eventId,
    Map<String, JsonNode> extensions
) {}
```

JSON khi đó có wrapper extensions:

```json
{
  "eventId": "evt-100",
  "extensions": {
    "x-partner-trace": "trace-abc"
  }
}
```

Chọn hình dạng dựa trên hợp đồng. Object phẳng phù hợp khi property động thực sự là các property mở rộng của cùng một object. Wrapper rõ ràng phù hợp khi phần mở rộng là một nhóm dữ liệu riêng.

### 7.1. Tránh xung đột với property cố định

Nếu Map dynamic chứa key trùng tên với property cố định như eventId, khi serialize có thể tạo tên property trùng lặp hoặc output khó dự đoán.

Hãy quy định một vùng tên cho dynamic property, ví dụ:

- x-... cho extension do đối tác cung cấp.
- custom... cho thuộc tính cấu hình.
- Một prefix riêng cho metadata do ứng dụng quản lý.

Có thể kiểm tra key trước khi thêm:

```java
private static final Set<String> RESERVED_NAMES =
    Set.of("eventId", "eventType");

@JsonAnySetter
public void addExtension(String name, JsonNode value) {
    if (RESERVED_NAMES.contains(name)) {
        throw new IllegalArgumentException(
            "Extension name is reserved: " + name
        );
    }

    extensions.put(name, value);
}
```

Cũng cần quyết định có phân biệt chữ hoa/chữ thường hay không. Nếu hệ thống chuẩn hóa tên property thành lowercase, hai tên khác nhau có thể va chạm sau chuẩn hóa.

## 8. @JsonAnySetter, ignoreUnknown và Map khác nhau thế nào?

Ba cách có mục tiêu khác nhau:

| Cơ chế | Hành vi khi gặp property chưa biết | Có giữ dữ liệu không? |
| --- | --- | --- |
| @JsonAnySetter | Chuyển property vào method/Map được chỉ định | Có |
| @JsonIgnoreProperties(ignoreUnknown = true) | Bỏ qua property chưa biết | Không |
| Map<String, JsonNode> là property thông thường | Chỉ đọc các entry bên trong property Map có tên đã biết | Có, nhưng cần wrapper trong JSON |

Ví dụ ignoreUnknown:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public record SimpleEvent(
    String eventId,
    String eventType
) {}
```

Payload có thêm x-partner-trace vẫn được đọc, nhưng extension đó bị bỏ đi. Nếu cần forward dữ liệu, ghi lại payload hoặc xử lý extension sau này, hãy dùng @JsonAnySetter thay vì bỏ qua.

FAIL_ON_UNKNOWN_PROPERTIES thường có thể được bật để phát hiện field lạ. Khi class có any-setter, các property chưa biết được chuyển đến any-setter nên không bị xem là lỗi unknown thông thường. Điều này cho phép ứng dụng vừa giữ schema chặt cho field chuẩn vừa mở rộng có kiểm soát cho phần dynamic.

## 9. Phân biệt dynamic field với business key bằng ví dụ thực tế

Xét ba cấu trúc:

### 9.1. Mã vùng là giá trị property cố định

```json
{
  "regionCode": "VN",
  "taxRate": 0.10
}
```

regionCode là property cố định; VN là business key ở dạng value. Dùng DTO:

```java
public record RegionTax(
    String regionCode,
    BigDecimal taxRate
) {}
```

### 9.2. Mã vùng là Map key

```json
{
  "VN": 0.10,
  "SG": 0.09,
  "TH": 0.07
}
```

Mỗi mã vùng là key của một entry. Dùng:

```java
Map<String, BigDecimal> taxRateByRegion;
```

Nếu mã vùng cần xác thực theo danh mục domain, dùng RegionCode cùng key deserializer.

### 9.3. Tên extension do đối tác tự định nghĩa

```json
{
  "eventId": "evt-100",
  "partnerRegionLabel": "South East",
  "x-tenant-context": {
    "tenant": "tenant-a",
    "environment": "staging"
  }
}
```

Các tên partnerRegionLabel và x-tenant-context là property mở rộng. Chúng không tự động là business key. Có thể nhận bằng @JsonAnySetter và giữ value dạng JsonNode.

Bảng quyết định:

| Dữ liệu | Nên mô hình hóa bằng |
| --- | --- |
| Mã định danh nằm trong một field cố định | DTO property có kiểu |
| Tập mã cùng loại dùng để tra cứu value | Map với key type rõ ràng |
| Field bổ sung chưa biết trước trên object | @JsonAnySetter / @JsonAnyGetter |
| Field lạ không cần lưu | ignoreUnknown = true nếu hợp đồng cho phép |
| Key cần nhiều metadata riêng | Array các entry DTO |
| Schema hoàn toàn động | JsonNode hoặc Map có validation |

## 10. Khi nào nên dùng array các entry thay cho tên property động?

JSON object phù hợp khi key là chuỗi đơn giản và mỗi entry có cùng cấu trúc value. Nhưng nếu key có nhiều thuộc tính hoặc cần metadata trên từng entry, array các object thường rõ ràng hơn.

Dạng dictionary:

```json
{
  "VN": 0.10,
  "SG": 0.09
}
```

Dạng entry list:

```json
{
  "taxRates": [
    {
      "regionCode": "VN",
      "rate": 0.10,
      "effectiveFrom": "2026-01-01"
    },
    {
      "regionCode": "SG",
      "rate": 0.09,
      "effectiveFrom": "2026-01-01"
    }
  ]
}
```

Dạng entry list có các lợi thế:

- Có thể khai báo kiểu rõ ràng cho từng field.
- Có thể thêm metadata như ngày hiệu lực, nguồn hoặc trạng thái.
- Có thể validate key như một property bình thường.
- Không phụ thuộc key phải chuyển thành tên property JSON.
- Dễ biểu diễn key phức tạp hoặc nhiều phần.

Đổi lại, truy cập một entry theo key có thể cần duyệt hoặc xây dựng Map ở tầng ứng dụng. Hãy chọn theo cách consumer truy cập dữ liệu và hợp đồng trao đổi.

## 11. Map key không phải lúc nào cũng là String trong Java

JSON object property name luôn là chuỗi, nhưng key trong Java Map có thể là nhiều kiểu:

- String
- Integer, Long
- Enum
- Kiểu value object như CurrencyCode
- Kiểu tùy chỉnh có key serializer/deserializer

Ví dụ Map enum:

```java
public enum Environment {
    DEV,
    TEST,
    PROD
}

Map<Environment, String> endpoints;
```

Jackson có hỗ trợ key enum theo tên enum trong nhiều trường hợp. Nếu hệ thống dùng code khác tên enum, ví dụ P cho production, cần mapping tường minh thay vì dựa vào tên hoặc ordinal mặc định.

Không nên dùng ordinal số làm key nghiệp vụ vì thứ tự enum có thể thay đổi. Hãy dùng code ổn định được quy định rõ.

Với key số:

```json
{
  "1001": "Keyboard",
  "1002": "Mouse"
}
```

Có thể đọc thành:

```java
Map<Long, String> names = mapper.readValue(
    json,
    new TypeReference<Map<Long, String>>() {}
);
```

Jackson dùng key deserializer để chuyển text "1001" thành Long. Nếu tên property không parse được thành Long, thao tác mapping sẽ thất bại.

## 12. Tên property động và các ký tự đặc biệt

Tên property JSON có thể chứa khoảng trắng, dấu chấm, dấu gạch ngang hoặc ký tự Unicode nếu được quote đúng quy tắc JSON:

```json
{
  "x-vendor-id": "v-100",
  "display.name": "Keyboard",
  "thuộc_tính_mở_rộng": true
}
```

Jackson xử lý escaping tên property khi serialize. Không tự nối chuỗi JSON bằng cách chèn tên dynamic vào giữa dấu ngoặc kép:

```java
// Không nên tự ghép tên field và value thành JSON.
String json = "{\"" + dynamicName + "\":\"" + dynamicValue + "\"}";
```

Nếu dynamicName chứa dấu ngoặc kép, dấu gạch chéo ngược hoặc ký tự điều khiển, chuỗi có thể sai cú pháp hoặc thay đổi ý nghĩa. Hãy dùng Map, @JsonAnyGetter, JsonGenerator.writeFieldName(...) hoặc API Databind để Jackson escape đúng cách.

Tên property động cũng cần giới hạn về độ dài, ký tự, namespace và số lượng. Một nguồn bên ngoài có thể gửi hàng nghìn tên field ngẫu nhiên làm tăng bộ nhớ, kích thước payload hoặc độ phức tạp xử lý.

## 13. Kiểm soát schema mở và bảo vệ hợp đồng dữ liệu

Mở rộng schema không có nghĩa là chấp nhận mọi property không giới hạn.

Với dynamic field, cần xác định:

- Prefix hoặc namespace nào được phép?
- Tên field tối đa dài bao nhiêu?
- Có giới hạn số lượng extension không?
- Value có thể là object/array lồng sâu đến mức nào?
- Có cấm các tên trùng với property chuẩn không?
- Có giữ lại extension khi serialize lại hay chỉ dùng trong thời gian xử lý?
- Có cần forward extension đến hệ thống khác không?
- Có cần loại bỏ field nhạy cảm hoặc field không được phép?

Ví dụ kiểm tra tên extension:

```java
private static final Pattern ALLOWED_EXTENSION =
    Pattern.compile("x-[a-z0-9-]{1,60}");

@JsonAnySetter
public void addExtension(String name, JsonNode value) {
    if (!ALLOWED_EXTENSION.matcher(name).matches()) {
        throw new IllegalArgumentException(
            "Unsupported extension name: " + name
        );
    }

    if (extensions.size() >= 100) {
        throw new IllegalArgumentException(
            "Too many extension properties"
        );
    }

    extensions.put(name, value);
}
```

Đây là ví dụ chính sách đơn giản. Trong ứng dụng thực tế, lỗi từ any-setter nên được chuyển thành lỗi mapping/API phù hợp; giới hạn kích thước payload và độ sâu lồng nhau cũng cần được kiểm soát ở tầng parser hoặc HTTP server.

Với business key, validation phải dựa trên quy tắc domain: định dạng, tồn tại trong danh mục, trạng thái hoạt động, tenant ownership hoặc quyền truy cập. Một key đúng cú pháp vẫn có thể không hợp lệ về nghiệp vụ.

## 14. Kiểm tra duplicate key và collision

Có hai dạng trùng cần phân biệt:

1. **Trùng tên property trong JSON text**: payload chứa cùng một tên key nhiều lần trong cùng object.
2. **Va chạm sau chuyển đổi/chuẩn hóa**: hai tên khác nhau trở thành cùng một business key sau khi parse hoặc chuẩn hóa.

Ví dụ JSON trùng tên:

```json
{
  "USD": 1.0,
  "USD": 1.1
}
```

Có thể bật phát hiện duplicate key ở parser:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Ví dụ va chạm sau chuẩn hóa:

```json
{
  "usd": 1.0,
  "USD": 1.1
}
```

Parser không xem đây là duplicate vì tên property khác nhau. Nếu CurrencyCode tự chuyển mọi key thành uppercase, hai key có thể trở thành cùng một giá trị. Key deserializer hoặc lớp chuyển đổi cần phát hiện và từ chối trường hợp này.

Với dynamic field, cũng cần phát hiện tên bị trùng sau khi áp dụng chính sách lowercase, Unicode normalization hoặc alias. Đừng âm thầm ghi đè Map entry nếu điều đó có thể làm mất dữ liệu.

## 15. Kiểm thử Map key và dynamic property

Nên kiểm thử riêng hai đường đi:

- JSON property name → Java Map key hoặc extension name.
- Java Map key hoặc extension name → JSON property name.

### 15.1. Test business key trong Map

```java
@Test
void readsBusinessKeysIntoTypedMap() throws Exception {
    String json = """
        {
          "USD": 1.0,
          "EUR": 0.92
        }
        """;

    Map<CurrencyCode, BigDecimal> rates = mapper.readValue(
        json,
        new TypeReference<Map<CurrencyCode, BigDecimal>>() {}
    );

    assertEquals(
        new BigDecimal("1.0"),
        rates.get(new CurrencyCode("USD"))
    );
}
```

### 15.2. Test key sai định dạng

```java
@Test
void rejectsInvalidBusinessKey() {
    String json = """
        {
          "US": 1.0
        }
        """;

    assertThrows(
        JsonMappingException.class,
        () -> mapper.readValue(
            json,
            new TypeReference<Map<CurrencyCode, BigDecimal>>() {}
        )
    );
}
```

### 15.3. Test dynamic fields được giữ lại

```java
@Test
void capturesUnknownFieldsAndWritesThemBack() throws Exception {
    String json = """
        {
          "eventId": "evt-100",
          "customColor": "blue",
          "vendorFlag": true
        }
        """;

    PartnerEvent event = mapper.readValue(json, PartnerEvent.class);

    String output = mapper.writeValueAsString(event);
    JsonNode root = mapper.readTree(output);

    assertEquals("evt-100", root.path("eventId").asText());
    assertEquals("blue", root.path("customColor").asText());
    assertTrue(root.path("vendorFlag").asBoolean());
}
```

### 15.4. Test collision với tên reserved

Tạo test để xác nhận extension không thể dùng tên đã dành cho field cố định. Nếu có cơ chế normalize tên, test thêm các trường hợp khác chữ hoa/chữ thường và Unicode tương đương.

### 15.5. Test round-trip

Với Map có key domain riêng, kiểm tra:

1. Đọc JSON thành Map typed key.
2. Ghi Map trở lại JSON.
3. Đọc JSON lần nữa.
4. So sánh key/value sau round-trip.

Với any-setter/any-getter, kiểm tra extension lồng nhau, null, array, object và thứ tự nếu thứ tự có ý nghĩa với consumer.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Map key vẫn là String dù muốn kiểu domain | Chưa đăng ký key deserializer hoặc generic type chưa rõ | Dùng Map<BusinessKey, V> cùng key deserializer |
| Serialize Map key sai hình dạng | Chỉ tạo value serializer, chưa tạo key serializer | Dùng addKeySerializer hoặc keyUsing |
| Key serializer ghi ra string value trong object | Dùng writeString thay vì writeFieldName | Ghi tên key bằng writeFieldName |
| Unknown property gây lỗi | DTO không có any-setter và unknown-property failure đang bật | Khai báo any-setter hoặc quyết định bỏ qua/từ chối |
| Extension bị mất sau deserialize | Dùng ignoreUnknown = true hoặc không lưu property | Dùng @JsonAnySetter với Map |
| JSON xuất hiện object extensions ngoài ý muốn | Map được khai báo như property thường | Dùng any-getter nếu cần trải phẳng, hoặc giữ wrapper theo hợp đồng |
| JSON có tên property trùng lặp | Dynamic Map chứa key trùng field cố định | Dành reserved names và validate trước khi serialize |
| Hai business key ghi đè nhau | Chuẩn hóa key tạo collision | Phát hiện duplicate sau chuẩn hóa |
| Key có dấu hoặc ký tự đặc biệt làm JSON lỗi | Tự ghép chuỗi JSON | Dùng Jackson serializer/generator |
| Map key không chuyển được sang kiểu số/enum | Text key không hợp lệ theo key deserializer | Xác thực format và báo lỗi rõ ràng |
| Payload có quá nhiều field động | Không giới hạn extension | Quy định namespace, số lượng, độ dài và kích thước value |

Khi debug, xác định lỗi nằm ở tên property của JSON, key conversion của Map, any-setter hay validation nghiệp vụ. Các lớp này có trách nhiệm khác nhau.

## 17. Quy trình chọn mô hình

Khi thiết kế một payload có key thay đổi:

1. Xác định tên property có được định nghĩa cố định trong hợp đồng hay không.
2. Nếu tên cố định, dùng DTO/record và @JsonProperty khi cần.
3. Nếu object là dictionary với các key cùng ý nghĩa và value cùng shape, dùng Map.
4. Nếu key mang ý nghĩa domain, tạo kiểu key riêng và key deserializer/serializer để xác thực.
5. Nếu object có field chuẩn cộng với extension chưa biết, dùng @JsonAnySetter và @JsonAnyGetter.
6. Nếu field lạ không cần lưu, cân nhắc ignoreUnknown = true; nếu cần phát hiện sai schema, giữ strict unknown-property policy.
7. Nếu mỗi key cần metadata riêng hoặc key không thể biểu diễn gọn bằng string, dùng array các entry DTO.
8. Định nghĩa quy tắc duplicate, chuẩn hóa, reserved name và giới hạn số lượng.
9. Kiểm thử serialize, deserialize, round-trip và dữ liệu sai.

Một thiết kế tốt làm rõ phần nào là hợp đồng ổn định, phần nào là dictionary theo khóa nghiệp vụ và phần nào là extension có thể thay đổi.

## 18. Bài thực hành tổng hợp

Xây dựng payload cho hệ thống tồn kho và sự kiện đối tác.

### Phần A — Property cố định và business key dạng value

Tạo record:

```java
public record ProductStock(
    String sku,
    int quantity
) {}
```

Đọc JSON có sku và quantity. Kiểm tra SKU bằng validation hoặc value object. Xác nhận sku là value của property cố định, không phải tên field động.

### Phần B — Dictionary keyed by business key

Tạo BusinessKey hoặc CurrencyCode, sau đó:

1. Viết KeyDeserializer để đọc key từ JSON property name.
2. Viết KeySerializer để ghi key trở lại.
3. Đăng ký bằng SimpleModule.
4. Đọc Map<BusinessKey, Integer>.
5. Từ chối key sai định dạng.
6. Kiểm tra va chạm sau chuẩn hóa.

### Phần C — Extension field

Tạo PartnerEvent với eventId, eventType và Map extension.

1. Dùng @JsonAnySetter để nhận field chưa biết.
2. Lưu value dạng JsonNode.
3. Dùng @JsonAnyGetter để ghi extension ở cùng cấp.
4. Từ chối reserved name.
5. Giới hạn prefix và số lượng extension.
6. Round-trip payload có string, number, boolean, null, array và object.

### Phần D — So sánh cấu trúc

Biểu diễn cùng dữ liệu theo hai dạng:

- JSON object dùng business key làm tên property.
- JSON array chứa các entry có property key, value và metadata.

So sánh khả năng validation, mở rộng schema, truy cập theo key và khả năng tương thích của consumer.

Bài thực hành hoàn thành khi có thể giải thích tại sao một tên JSON có thể là property cố định, Map key mang ý nghĩa nghiệp vụ hoặc extension động, và chọn đúng cơ chế Jackson cho từng trường hợp.

## 19. Nguyên tắc ghi nhớ

- Tên property JSON và khóa nghiệp vụ là hai khái niệm khác nhau; một chuỗi có thể đóng cả hai vai trò tùy vị trí.
- Business key cần quy tắc định dạng, chuẩn hóa, uniqueness và validation domain.
- Property cố định nên được khai báo bằng DTO/record, @JsonProperty hoặc naming strategy.
- Dictionary dùng Map khi các entry có cùng cấu trúc; key type có thể cần KeySerializer và KeyDeserializer.
- @JsonAnySetter nhận property chưa biết vào Map/method; @JsonAnyGetter xuất Map thành property ở cấp object.
- ignoreUnknown = true bỏ dữ liệu lạ; any-setter giữ dữ liệu để xử lý hoặc forward.
- Map lồng như property extensions khác với any-getter trải phẳng extension vào object cha.
- JSON object key luôn là text; key phức tạp hoặc cần nhiều metadata nên được biểu diễn bằng array các entry.
- Không tự ghép tên field/value thành JSON; để Jackson escape tên và serialize value.
- Phát hiện duplicate JSON key và collision sau chuẩn hóa là hai việc riêng.
- Giới hạn namespace, độ dài, số lượng và kích thước dynamic field từ nguồn bên ngoài.
- Kiểm thử round-trip, key sai định dạng, reserved name và collision.

Khi phân biệt khóa nghiệp vụ và tên trường động, hãy bắt đầu từ ý nghĩa domain và hợp đồng JSON: business key định danh dữ liệu theo quy tắc nghiệp vụ; dynamic field mở rộng tên property của schema. Sau đó chọn DTO, Map hoặc any-setter/any-getter và cấu hình key conversion tương ứng để dữ liệu được đọc, xác thực và ghi lại đúng nghĩa.
