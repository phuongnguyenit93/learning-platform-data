# Tùy biến cách ghi khóa Map

Trong JSON, một object được biểu diễn bằng các cặp **tên property** và **giá trị**. Tên property luôn là chuỗi, kể cả khi ứng dụng Java dùng kiểu key khác như Long, enum hoặc một value object riêng. Khi serialize một Map<K, V>, Jackson phải chuyển mỗi key Java thành tên property JSON.

Với các kiểu phổ biến như String, Integer, Long hoặc enum, Jackson đã có cách biểu diễn mặc định. Nhưng trong domain model, key có thể là một kiểu riêng như mã tiền tệ, mã tenant, cặp vùng/phiên bản hoặc định danh tổng hợp. Khi đó, cách ghi mặc định có thể không đúng hợp đồng JSON.

Jackson cho phép tùy biến việc này bằng **key serializer**. Key serializer quyết định chuỗi nào sẽ được ghi làm tên property cho mỗi entry của Map. Nếu ứng dụng cũng cần đọc JSON trở lại kiểu key đó, hãy định nghĩa thêm **key deserializer** để chuyển tên property thành đối tượng Java tương ứng.

Bài học tập trung vào cách ghi khóa Map bằng Jackson Databind: hình dạng JSON, API key serializer, đăng ký toàn cục và theo property, quy tắc mã hóa ổn định, xử lý va chạm và kiểm thử round-trip.

## 1. Vì sao khóa Map cần serializer riêng?

Xét Map trong Java:

```java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("SKU-1001", 25);
stock.put("SKU-1002", 80);
```

Jackson có thể ghi trực tiếp thành JSON object:

```json
{
  "SKU-1001": 25,
  "SKU-1002": 80
}
```

Ở đây, key Java trở thành tên property JSON; value Java trở thành giá trị của property.

Với key là kiểu số:

```java
Map<Long, String> names = Map.of(
    1001L, "Keyboard",
    1002L, "Mouse"
);
```

JSON object vẫn phải dùng tên property dạng chuỗi:

```json
{
  "1001": "Keyboard",
  "1002": "Mouse"
}
```

Nếu domain model dùng một kiểu riêng:

```java
public record CurrencyCode(String value) {}
```

và Map:

```java
Map<CurrencyCode, BigDecimal> rates;
```

Jackson cần quy tắc để chuyển CurrencyCode thành field name. Đây là nhiệm vụ của key serializer. Serializer thông thường dành cho value không giải quyết đúng vị trí này, vì JSON object yêu cầu key được ghi như tên property chứ không phải một JSON value độc lập.

## 2. Phân biệt key serializer và value serializer

Một entry trong Map có hai phần độc lập:

```text
Map entry
  ├── key   ──> tên property JSON
  └── value ──> giá trị JSON
```

Ví dụ Java:

```java
Map<CurrencyCode, BigDecimal> rates = ...;
```

JSON:

```json
{
  "USD": 1.0,
  "EUR": 0.92
}
```

| Thành phần | Java | Vị trí trong JSON | Cơ chế Jackson |
| --- | --- | --- | --- |
| Key | CurrencyCode | Tên property, ví dụ "USD" | Key serializer |
| Value | BigDecimal | Giá trị number, ví dụ 1.0 | Value serializer |

Key serializer phải ghi tên property bằng API tương ứng của JsonGenerator. Value serializer ghi nội dung value theo kiểu JSON phù hợp.

Ví dụ, với một Map có key là CurrencyCode và value là BigDecimal, custom key serializer không quyết định BigDecimal được ghi thành number hay string. Hai nhiệm vụ này độc lập.

## 3. JSON object chỉ có tên property dạng chuỗi

JSON không hỗ trợ trực tiếp object key là một object Java tùy ý. Những dạng sau không phải cách biểu diễn JSON object hợp lệ:

```text
{
  CurrencyCode("USD"): 1.0
}
```

hoặc:

```text
{
  {"region": "VN", "tenant": "A"}: 1.0
}
```

Tên property JSON phải là string được quote theo cú pháp JSON. Vì vậy, custom key serializer phải chuyển key Java thành một chuỗi field name duy nhất.

Ví dụ hợp lệ:

```json
{
  "VN": 0.10,
  "SG": 0.09
}
```

Nếu key gồm nhiều thành phần, ứng dụng phải định nghĩa cách mã hóa chúng thành một chuỗi. Nếu key phức tạp đến mức không thể biểu diễn rõ ràng bằng một chuỗi ổn định, hãy cân nhắc đổi JSON thành array các entry thay vì cố nhét object phức tạp vào tên property.

## 4. API tạo key serializer

Key serializer thường được viết bằng cách kế thừa JsonSerializer<K>. Trong method serialize, ghi tên property bằng JsonGenerator.writeFieldName(...).

Cấu trúc tổng quát:

```java
public final class CustomKeySerializer
        extends JsonSerializer<CustomKey> {

    @Override
    public void serialize(
            CustomKey value,
            JsonGenerator generator,
            SerializerProvider serializers
    ) throws IOException {
        String fieldName = ...;
        generator.writeFieldName(fieldName);
    }
}
```

Ba tham số:

- value: key Java của entry hiện tại.
- generator: generator đang ghi JSON.
- serializers: ngữ cảnh serializer do Jackson cung cấp; có thể dùng nếu logic cần thông tin từ provider.

Điểm quan trọng là gọi writeFieldName. Nếu gọi writeString, generator sẽ ghi một string value trong vị trí value của object. Nó không tạo tên property cho Map entry.

Không tự thêm dấu ngoặc kép hoặc escape thủ công. JsonGenerator chịu trách nhiệm quote và escape field name theo cú pháp JSON.

## 5. Ví dụ: ghi CurrencyCode thành tên property

Giả sử domain có kiểu mã tiền tệ:

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

Record này dùng constructor để bảo đảm key luôn có ba chữ cái in hoa. Vì record tự sinh equals và hashCode, nó cũng có thể được dùng làm key của Map.

Tạo key serializer:

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

Serializer dùng value.value() làm tên property. Không cần ghi string value riêng, vì chính chuỗi đó là field name.

Tạo Map:

```java
Map<CurrencyCode, BigDecimal> rates = new LinkedHashMap<>();

rates.put(
    new CurrencyCode("USD"),
    new BigDecimal("1.0000")
);

rates.put(
    new CurrencyCode("EUR"),
    new BigDecimal("0.9200")
);
```

Sau khi đăng ký serializer, Jackson có thể ghi:

```json
{
  "USD": 1.0000,
  "EUR": 0.9200
}
```

Giá trị BigDecimal được xử lý bởi value serializer mặc định. Key serializer chỉ biến CurrencyCode thành tên property.

## 6. Đăng ký key serializer bằng SimpleModule

Cách phổ biến để đăng ký custom key serializer cho một kiểu là dùng SimpleModule:

```java
SimpleModule module = new SimpleModule();

module.addKeySerializer(
    CurrencyCode.class,
    new CurrencyCodeKeySerializer()
);

ObjectMapper mapper = new ObjectMapper()
    .registerModule(module);
```

Sau khi đăng ký, mọi Map có key type phù hợp trên mapper này có thể sử dụng serializer đã khai báo:

```java
Map<CurrencyCode, BigDecimal> rates = ...;

String json = mapper.writeValueAsString(rates);
```

Đăng ký bằng module phù hợp khi cách biểu diễn của CurrencyCode là quy ước chung trong ứng dụng. Nếu nhiều DTO và Map cùng dùng kiểu key đó, không cần gắn annotation lặp lại ở từng nơi.

### 6.1. Một module có thể đăng ký cả key serializer và key deserializer

Nếu ứng dụng cũng đọc JSON trở lại, đăng ký cả hai chiều trong cùng module:

```java
SimpleModule module = new SimpleModule("currency-code-module");

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

Key serializer xử lý chiều Java Map → JSON property name. Key deserializer xử lý chiều JSON property name → Java Map key. Chúng cần dùng cùng một quy ước biểu diễn để round-trip giữ nguyên key.

### 6.2. Đăng ký trên đúng ObjectMapper

Module chỉ có tác dụng trên mapper đã đăng ký nó. Nếu ứng dụng có nhiều ObjectMapper, ví dụ mapper cho HTTP API, mapper cho file import và mapper cho message queue, hãy xác định mapper nào thực sự thực hiện serialization.

Trong Spring Boot, ưu tiên cấu hình mapper do framework quản lý thông qua builder/customizer hoặc module bean theo cách dự án đang dùng. Một mapper được tạo bằng new ObjectMapper() trong service không tự động nhận các module đã đăng ký trên mapper của Spring.

Không nên thay đổi mapper sau khi đã đưa vào sử dụng đồng thời. Hoàn tất cấu hình module trước khi chia sẻ mapper cho các service hoặc thread.

## 7. Gắn key serializer ở cấp property

Không phải lúc nào cũng muốn áp dụng quy tắc key cho mọi Map có cùng kiểu key. Nếu chỉ một property cần cách ghi đặc biệt, có thể dùng annotation @JsonSerialize(keyUsing = ...).

Ví dụ:

```java
public record ExchangeRateResponse(
    @JsonSerialize(keyUsing = CurrencyCodeKeySerializer.class)
    Map<CurrencyCode, BigDecimal> rates
) {}
```

Annotation này chỉ định key serializer cho Map property rates.

Nếu cần deserialize property đó bằng key deserializer riêng:

```java
public record ExchangeRateResponse(
    @JsonSerialize(keyUsing = CurrencyCodeKeySerializer.class)
    @JsonDeserialize(keyUsing = CurrencyCodeKeyDeserializer.class)
    Map<CurrencyCode, BigDecimal> rates
) {}
```

Các annotation thuộc package:

```java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
```

Chọn phạm vi cấu hình:

| Phạm vi | Cách đăng ký | Khi phù hợp |
| --- | --- | --- |
| Toàn mapper/module | SimpleModule.addKeySerializer | Một kiểu key có cách biểu diễn chung trong ứng dụng |
| Một property Map | @JsonSerialize(keyUsing = ...) | Một Map cần quy tắc riêng |
| Một property Map ở cả hai chiều | keyUsing kết hợp keyUsing của deserialize | Hợp đồng property có quy tắc đọc/ghi riêng |

Nếu module toàn cục và annotation property cùng chỉ định serializer, cần kiểm tra precedence theo cách cấu hình Jackson của dự án. Tránh đăng ký hai quy tắc cạnh tranh cho cùng một property nếu không có lý do rõ ràng.

## 8. Tạo key deserializer tương ứng

Khi đọc JSON:

```json
{
  "USD": 1.0000,
  "EUR": 0.9200
}
```

Jackson nhận tên property dưới dạng String. Key deserializer chuyển String đó thành CurrencyCode.

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

Method deserializeKey nhận:

- key: tên property JSON.
- context: ngữ cảnh deserialize, dùng để tạo lỗi mapping có thông tin kiểu key và giá trị gây lỗi.

Nếu key không hợp lệ, hãy báo lỗi mapping thay vì trả về null hoặc key mặc định. Một key sai định dạng không nên âm thầm trở thành entry khác trong Map.

Đăng ký:

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

Đọc Map có kiểu đầy đủ:

```java
Map<CurrencyCode, BigDecimal> rates = mapper.readValue(
    json,
    new TypeReference<Map<CurrencyCode, BigDecimal>>() {}
);
```

Nếu chỉ truyền Map.class, Jackson không biết kiểu key/value mong muốn một cách đầy đủ. Dùng TypeReference hoặc JavaType để giữ generic type.

## 9. Quy tắc mã hóa key phải ổn định và không nhập nhằng

Một key serializer tốt cần các thuộc tính:

1. **Ổn định**: cùng một key luôn tạo cùng một field name.
2. **Không nhập nhằng**: hai key khác nhau không được vô tình tạo cùng một field name.
3. **Có thể đảo ngược**: nếu cần deserialize, key deserializer phải khôi phục đúng key ban đầu.
4. **Độc lập locale**: không thay đổi theo ngôn ngữ hoặc cấu hình vùng của máy chạy.
5. **Có quy tắc rõ ràng**: format và giới hạn phải được định nghĩa trong hợp đồng.

Ví dụ không tốt là dùng toString() nếu method đó chỉ được viết để debug; format có thể thay đổi khi refactor. Không nên dùng biểu diễn debug làm hợp đồng JSON.

Nên gọi method có ý nghĩa rõ ràng như code() hoặc toExternalForm():

```java
generator.writeFieldName(value.toExternalForm());
```

Method đó cần được xem là một phần của định dạng trao đổi dữ liệu và được kiểm thử.

### 9.1. Không dùng format phụ thuộc locale

Không nên dùng NumberFormat theo locale mặc định để tạo key số. Cùng một giá trị có thể được ghi thành 1,000 hoặc 1.000 tùy locale. Dùng định dạng chuẩn hóa độc lập locale, như biểu diễn số nguyên thập phân hoặc một format được định nghĩa rõ.

Với ngày giờ, nếu key chứa thời gian, hãy dùng format cố định như ISO-8601 và timezone được quy định rõ. Không dùng format phụ thuộc thiết lập máy.

### 9.2. Tránh hai key khác nhau cùng tạo một field name

Giả sử key serializer bỏ dấu cách và chuyển chữ thường thành chữ hoa:

- CurrencyCode("usd") → "USD".
- CurrencyCode("USD") → "USD".

Nếu hai key khác nhau cùng tồn tại trong Map, JSON output có thể chứa hai property name trùng nhau. Một số consumer sẽ giữ giá trị cuối, một số parser có thể từ chối, còn consumer khác có thể xử lý khác.

Tốt hơn là chuẩn hóa key ngay khi tạo domain object, bảo đảm equals/hashCode phù hợp với biểu diễn chuẩn và từ chối dữ liệu va chạm trước khi serialize.

## 10. Mã hóa key tổng hợp từ nhiều thành phần

Một số Map dùng key gồm nhiều thành phần:

```java
public record TenantRegionKey(
    String tenant,
    String region
) {}
```

Có thể muốn ghi Map:

```java
Map<TenantRegionKey, BigDecimal> taxRates;
```

thành JSON:

```json
{
  "tenant-a|VN": 0.10,
  "tenant-b|SG": 0.09
}
```

Dấu | là delimiter. Cách này chỉ an toàn nếu hợp đồng bảo đảm từng thành phần không chứa |, hoặc có quy tắc escape delimiter.

Ví dụ serializer đơn giản với quy tắc cấm delimiter trong từng thành phần:

```java
public final class TenantRegionKeySerializer
        extends JsonSerializer<TenantRegionKey> {

    @Override
    public void serialize(
            TenantRegionKey value,
            JsonGenerator generator,
            SerializerProvider serializers
    ) throws IOException {
        if (value.tenant().contains("|")
                || value.region().contains("|")) {
            throw new JsonMappingException(
                generator,
                "Tenant and region must not contain '|'."
            );
        }

        generator.writeFieldName(
            value.tenant() + "|" + value.region()
        );
    }
}
```

Key deserializer có thể tách chuỗi theo đúng một delimiter:

```java
public final class TenantRegionKeyDeserializer
        extends KeyDeserializer {

    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext context
    ) throws IOException {
        String[] parts = key.split("\\|", -1);

        if (parts.length != 2
                || parts[0].isBlank()
                || parts[1].isBlank()) {
            throw context.weirdKeyException(
                TenantRegionKey.class,
                key,
                "Expected tenant|region"
            );
        }

        return new TenantRegionKey(parts[0], parts[1]);
    }
}
```

Ví dụ này chỉ đúng với quy tắc delimiter được nêu. Nếu dữ liệu thành phần có thể chứa ký tự phân cách, hãy dùng một encoding không nhập nhằng như length-prefix, escaping có định nghĩa hoặc một định dạng mã hóa khác được kiểm thử đầy đủ.

Nếu key gồm nhiều trường tùy ý, cách biểu diễn array các entry thường dễ hiểu và dễ mở rộng hơn:

```json
{
  "taxRates": [
    {
      "tenant": "tenant-a",
      "region": "VN",
      "rate": 0.10
    },
    {
      "tenant": "tenant-b",
      "region": "SG",
      "rate": 0.09
    }
  ]
}
```

Trong cấu trúc này, tenant và region là property riêng; không cần mã hóa cả hai vào một tên property.

## 11. Key serializer không thay đổi tên field DTO thông thường

Custom key serializer chỉ áp dụng cho key của Map. Nó không đổi tên các property cố định của DTO.

Ví dụ:

```java
public record Report(
    String reportName,
    Map<CurrencyCode, BigDecimal> rates
) {}
```

Nếu dùng key serializer cho CurrencyCode, JSON có dạng:

```json
{
  "reportName": "Daily rates",
  "rates": {
    "USD": 1.0,
    "EUR": 0.92
  }
}
```

reportName vẫn được xử lý theo property naming của DTO. Key serializer chỉ điều khiển "USD" và "EUR" bên trong object rates.

Nếu muốn đổi tên rates thành exchange_rates, hãy dùng @JsonProperty("exchange_rates") trên property đó. Đó là việc đặt tên property DTO, khác với tùy biến key bên trong Map.

## 12. Xử lý key null và value null

Key null và value null là hai trường hợp khác nhau.

```java
Map<CurrencyCode, BigDecimal> rates = new LinkedHashMap<>();
rates.put(new CurrencyCode("USD"), null);
```

Entry trên có key hợp lệ và value null. Việc ghi value null chịu cấu hình serialize Map value, ví dụ chính sách ghi hoặc bỏ qua null map value.

Ngược lại:

```java
rates.put(null, new BigDecimal("1.0"));
```

là Map có key null. JSON object không có một tên property thông thường để biểu diễn key null. Jackson xử lý null Map key qua cơ chế null-key serializer riêng; serializer cho CurrencyCode không nhất thiết được gọi cho null. Cấu hình mặc định thường từ chối null key.

Trong domain model, cách đơn giản và an toàn thường là không cho phép null key. Nếu trạng thái chưa xác định là hợp lệ, hãy biểu diễn nó bằng một key sentinel có ý nghĩa rõ ràng hoặc dùng array entry với property key có thể null theo hợp đồng.

Không nên biến null thành chuỗi "null" nếu consumer không thể phân biệt key null thật với key có nội dung chữ null.

## 13. Thứ tự Map và tính ổn định của output

JSON object về mặt ngữ nghĩa không nên phụ thuộc vào thứ tự property. Tuy nhiên, thứ tự output có thể quan trọng với snapshot test, diff, cache key hoặc hệ thống legacy.

Nếu cần thứ tự ổn định:

- Dùng LinkedHashMap khi muốn giữ thứ tự chèn.
- Dùng TreeMap khi muốn sắp xếp theo comparator.
- Có thể cấu hình thứ tự property khi phù hợp, nhưng cần phân biệt thứ tự Map key với thứ tự property DTO.

Ví dụ:

```java
Map<CurrencyCode, BigDecimal> rates = new TreeMap<>(
    Comparator.comparing(CurrencyCode::value)
);
```

Key serializer vẫn quyết định cách ghi từng key. Comparator chỉ quyết định thứ tự duyệt Map.

Nếu serializer biến key thành chuỗi khác với thứ tự domain, thứ tự Map và thứ tự field name có thể không giống nhau. Nếu thứ tự serialized field name là yêu cầu, hãy sắp xếp theo chính biểu diễn chuẩn trước khi ghi.

Đừng coi thứ tự field JSON là một cơ chế định danh hoặc thay thế validation.

## 14. Kiểm soát duplicate field name

Có thể có hai key Java khác nhau nhưng serializer tạo ra cùng một field name. Ví dụ:

```java
Map<CurrencyCode, BigDecimal> rates = new LinkedHashMap<>();

rates.put(new CurrencyCode("USD"), new BigDecimal("1.0"));
rates.put(new CurrencyCode("usd"), new BigDecimal("0.9"));
```

Nếu serializer uppercase mọi key, cả hai entry có thể trở thành "USD".

Đây là collision ở bước serialize. Nó khác với duplicate key đã có sẵn trong JSON đầu vào.

Có thể xử lý bằng cách:

1. Chuẩn hóa key trong constructor/factory của domain type.
2. Định nghĩa equals và hashCode theo giá trị canonical.
3. Từ chối key trùng sau chuẩn hóa trước khi ghi.
4. Bật cơ chế duplicate field detection của generator nếu phiên bản/cấu hình Jackson hỗ trợ và muốn phát hiện thêm ở tầng ghi.
5. Viết test xác nhận serializer không tạo ra hai tên property giống nhau.

Không nên dựa hoàn toàn vào duplicate detection của generator. Kiểm tra domain trước khi serialize giúp thông báo lỗi có ý nghĩa hơn và ngăn dữ liệu sai đi xa hơn trong pipeline.

## 15. Kiểm thử key serializer

Nên kiểm tra cả output chính xác lẫn round-trip.

### 15.1. Test serialize một Map

```java
@Test
void writesCurrencyCodeAsObjectFieldName() throws Exception {
    Map<CurrencyCode, BigDecimal> rates = new LinkedHashMap<>();
    rates.put(new CurrencyCode("USD"), new BigDecimal("1.0"));

    String json = mapper.writeValueAsString(rates);

    JsonNode root = mapper.readTree(json);

    assertEquals("1.0", root.path("USD").decimalValue().toPlainString());
}
```

Test dùng JsonNode để kiểm tra key xuất hiện đúng vị trí object property. Có thể so sánh JSON tree thay vì so sánh chuỗi nếu whitespace hoặc thứ tự property không thuộc hợp đồng.

### 15.2. Test deserialize với key deserializer

```java
@Test
void readsObjectFieldNameAsCurrencyCode() throws Exception {
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

### 15.3. Test round-trip

```java
@Test
void preservesTypedMapKeysAfterRoundTrip() throws Exception {
    Map<CurrencyCode, BigDecimal> original = new LinkedHashMap<>();
    original.put(new CurrencyCode("USD"), new BigDecimal("1.0"));
    original.put(new CurrencyCode("EUR"), new BigDecimal("0.92"));

    String json = mapper.writeValueAsString(original);

    Map<CurrencyCode, BigDecimal> restored = mapper.readValue(
        json,
        new TypeReference<Map<CurrencyCode, BigDecimal>>() {}
    );

    assertEquals(original, restored);
}
```

Round-trip test chứng minh serializer và deserializer dùng cùng quy ước. Nếu ứng dụng chỉ xuất JSON và không đọc lại, vẫn cần test tên property đầu ra theo hợp đồng consumer.

### 15.4. Test key không hợp lệ

```java
@Test
void rejectsInvalidCurrencyCodeInPropertyName() {
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

### 15.5. Test key collision

Tạo hai key Java khác nhau nhưng sau khi canonicalize lại có cùng external form. Xác nhận tầng domain hoặc tầng chuẩn bị dữ liệu từ chối trước khi output được công bố. Nếu dùng generator duplicate detection, kiểm thử hành vi của đúng phiên bản Jackson đang chạy.

## 16. Lỗi thường gặp khi tùy biến cách ghi khóa Map

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Key xuất hiện như string value thay vì tên property | Key serializer gọi writeString | Dùng writeFieldName |
| Jackson vẫn ghi dạng mặc định | Module chưa đăng ký trên mapper thực tế hoặc annotation không nằm trên property được serialize | Kiểm tra đúng ObjectMapper và vị trí annotation |
| Map key không được đọc về kiểu domain | Chỉ đăng ký key serializer, thiếu key deserializer | Đăng ký cả hai chiều nếu cần deserialize |
| Key bị ghi thành format debug | Dùng toString() không ổn định | Tạo method external form có hợp đồng rõ |
| Hai key khác nhau tạo cùng field name | Encoding mất thông tin hoặc chuẩn hóa không kiểm soát | Dùng encoding injective và kiểm tra collision |
| Key tổng hợp bị tách sai | Delimiter có thể xuất hiện trong thành phần | Escape delimiter hoặc dùng encoding không nhập nhằng |
| Key có dấu quote làm JSON sai | Tự nối chuỗi JSON | Dùng writeFieldName, để generator escape |
| Null key gây lỗi | JSON object không có biểu diễn key null thông thường | Không cho phép null key hoặc định nghĩa biểu diễn riêng |
| Key type generic bị mất | Dùng raw Map hoặc Map.class | Dùng TypeReference hoặc JavaType |
| Chỉ một Map bị ghi sai format | Cấu hình module toàn cục không phù hợp với property đó | Dùng annotation keyUsing ở cấp property |
| Output order không ổn định | Dùng Map không bảo đảm thứ tự duyệt | Chọn LinkedHashMap, TreeMap hoặc sắp xếp trước khi ghi |

Khi debug, xác định vấn đề ở bước chọn serializer, bước tạo field name, bước escape của generator hay bước chuyển ngược khi deserialize. Mỗi bước có trách nhiệm riêng.

## 17. Quy trình thiết kế key serializer

Khi cần tùy biến key Map:

1. Xác định kiểu key Java và hình dạng JSON mà consumer yêu cầu.
2. Định nghĩa một external form duy nhất cho key.
3. Bảo đảm hai key khác nhau không tạo cùng một field name.
4. Viết JsonSerializer<K> và ghi bằng writeFieldName.
5. Đăng ký bằng SimpleModule.addKeySerializer hoặc annotation keyUsing.
6. Nếu cần đọc lại, viết KeyDeserializer dùng cùng quy tắc và đăng ký tương ứng.
7. Quyết định chính sách cho key null, key sai định dạng và collision.
8. Giữ generic type đầy đủ khi đọc Map.
9. Kiểm thử output, deserialize, round-trip và dữ liệu biên.
10. Xác nhận mapper thực tế của ứng dụng có cấu hình serializer.

Nếu key có nhiều thành phần, xác định encoding trước khi viết serializer. Nếu không thể tạo encoding đơn giản, ổn định và đảo ngược, đổi cấu trúc JSON sang array các entry.

## 18. Bài thực hành tổng hợp

Tạo kiểu key tiền tệ:

```java
public record CurrencyCode(String value) {
    public CurrencyCode {
        Objects.requireNonNull(value);

        if (!value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
    }
}
```

Thực hiện:

1. Tạo Map<CurrencyCode, BigDecimal> với USD, EUR và JPY.
2. Viết CurrencyCodeKeySerializer bằng JsonSerializer<CurrencyCode>.
3. Ghi field name bằng JsonGenerator.writeFieldName.
4. Đăng ký key serializer qua SimpleModule.
5. Serialize Map và quan sát JSON object.
6. Viết CurrencyCodeKeyDeserializer.
7. Đăng ký cả hai chiều và đọc JSON trở lại.
8. Gắn @JsonSerialize(keyUsing = ...) và @JsonDeserialize(keyUsing = ...) trên một Map property riêng.
9. Thử key sai định dạng và xác nhận mapping thất bại.
10. Thử một kiểu key tổng hợp gồm tenant và region; định nghĩa delimiter hoặc encoding có thể đảo ngược.
11. Tạo hai key có external form trùng nhau và kiểm tra collision.
12. Kiểm tra key null và xác định chính sách của ứng dụng.
13. So sánh thứ tự output của HashMap, LinkedHashMap và TreeMap.
14. Viết round-trip test và test tên property đầu ra theo hợp đồng.

Bài thực hành hoàn thành khi có thể giải thích chính xác key serializer được gọi ở đâu, tại sao cần writeFieldName, cách đăng ký theo module/property và cách bảo đảm key được ghi ổn định, không nhập nhằng.

## 19. Nguyên tắc ghi nhớ

- JSON object luôn dùng string làm tên property; Map key Java cần được chuyển thành field name.
- Key serializer xử lý key của Map; value serializer xử lý value của entry.
- Kế thừa JsonSerializer<K> và ghi tên key bằng JsonGenerator.writeFieldName.
- Không dùng writeString để ghi tên property và không tự quote/escape thủ công.
- SimpleModule.addKeySerializer đăng ký quy tắc theo kiểu key trên một ObjectMapper.
- @JsonSerialize(keyUsing = ...) giới hạn serializer vào một Map property.
- Nếu cần đọc lại, đăng ký KeyDeserializer hoặc dùng @JsonDeserialize(keyUsing = ...).
- External form phải ổn định, không phụ thuộc locale và có thể đảo ngược nếu cần round-trip.
- Hai key khác nhau không được tạo cùng field name; kiểm tra collision sau chuẩn hóa.
- Key tổng hợp cần delimiter/encoding không nhập nhằng; nếu quá phức tạp, dùng array các entry.
- Key null có xử lý riêng; đừng giả định key serializer thông thường nhận null.
- Giữ generic type bằng TypeReference/JavaType khi deserialize Map.
- Kiểm thử output, key sai định dạng, round-trip, collision và mapper thực tế.

Khi tùy biến cách ghi khóa Map, hãy định nghĩa external form của key trước, triển khai key serializer bằng writeFieldName, đăng ký đúng phạm vi và kiểm thử để mỗi key Java luôn được ghi thành một tên property JSON ổn định, duy nhất và đúng hợp đồng.
