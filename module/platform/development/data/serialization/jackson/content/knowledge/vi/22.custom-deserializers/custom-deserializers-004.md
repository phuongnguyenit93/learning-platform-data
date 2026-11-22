# Thiết kế deserializer cho kiểu giá trị có nhiều cách biểu diễn

Một API đôi khi nhận cùng một ý nghĩa dữ liệu dưới nhiều hình thức JSON. Một tọa độ có thể được gửi dưới dạng object có tên field, array gồm hai số hoặc một chuỗi gọn như `"10.7626,106.6602"`. Một mã định danh có thể xuất hiện dưới dạng string hoặc number; một khoảng thời gian có thể được biểu diễn bằng số giây hoặc object có đơn vị. Nếu kiểu Java đích cần chuẩn hóa các hình thức đó thành một value object duy nhất, deserializer tùy biến là nơi thích hợp để định nghĩa quy tắc chuyển đổi.

Jackson có sẵn nhiều coercion và annotation cho các trường hợp chuyển đổi đơn giản. Tuy nhiên, khi đầu vào có nhiều **hình dạng token** khác nhau, có quy tắc bắt buộc/tuỳ chọn riêng và cần kiểm tra ngữ nghĩa, một lớp `JsonDeserializer<T>` giúp kiểm soát rõ ràng cách đọc.

Trong chương **Deserializer tùy biến** của Data Serialization Jackson, trọng tâm là thiết kế một deserializer có hợp đồng đầu vào rõ ràng: xác định những dạng JSON được chấp nhận, đọc đúng token hiện tại, kiểm tra dữ liệu, báo lỗi có ngữ cảnh và tạo ra một kiểu Java thống nhất. Deserializer nên chấp nhận đúng những dạng đã công bố, không cố đoán mọi chuỗi hoặc cấu trúc mà client gửi.

## 1. Một giá trị, nhiều hình dạng JSON

Giả sử ứng dụng cần một kiểu `GeoPoint` đại diện cho tọa độ địa lý. Có thể quy định ba cách biểu diễn đầu vào:

**Dạng object:**

```json
{
  "latitude": 10.7626,
  "longitude": 106.6602
}
```

**Dạng array:**

```json
[10.7626, 106.6602]
```

**Dạng string gọn:**

```json
"10.7626,106.6602"
```

Cả ba dạng đều biểu diễn cùng một giá trị: vĩ độ `10.7626`, kinh độ `106.6602`. Java domain model không cần giữ ba kiểu khác nhau. Nó chỉ cần một `GeoPoint`:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record GeoPoint(BigDecimal latitude, BigDecimal longitude) {
    private static final BigDecimal MIN_LATITUDE = new BigDecimal("-90");
    private static final BigDecimal MAX_LATITUDE = new BigDecimal("90");
    private static final BigDecimal MIN_LONGITUDE = new BigDecimal("-180");
    private static final BigDecimal MAX_LONGITUDE = new BigDecimal("180");

    public GeoPoint {
        Objects.requireNonNull(latitude, "latitude is required");
        Objects.requireNonNull(longitude, "longitude is required");

        if (latitude.compareTo(MIN_LATITUDE) < 0
                || latitude.compareTo(MAX_LATITUDE) > 0) {
            throw new IllegalArgumentException("latitude must be between -90 and 90");
        }
        if (longitude.compareTo(MIN_LONGITUDE) < 0
                || longitude.compareTo(MAX_LONGITUDE) > 0) {
            throw new IllegalArgumentException("longitude must be between -180 and 180");
        }
    }
}
```

`BigDecimal` được dùng để giữ giá trị thập phân theo dữ liệu đầu vào, tránh chuyển qua `double` rồi mang theo sai số nhị phân. Constructor của value object tự bảo vệ invariant, vì vậy đối tượng tạo từ code Java cũng phải tuân thủ cùng giới hạn tọa độ.

## 2. Khi nào nên viết custom deserializer?

Trước khi viết code, cần xác định liệu các dạng đầu vào có thể xử lý bằng cấu hình Jackson sẵn có hay không.

| Nhu cầu | Cách tiếp cận nên cân nhắc |
|---|---|
| Chỉ đổi tên JSON property | `@JsonProperty` hoặc naming strategy |
| Một property có format ngày giờ riêng | `@JsonFormat` nếu format được hỗ trợ |
| Chuyển scalar đơn giản giữa string và number | Coercion hoặc deserializer mặc định |
| Một giá trị có nhiều token shape, ví dụ object/array/string | Custom `JsonDeserializer<T>` |
| Cần xác thực nhiều field kết hợp với nhau | Custom deserializer hoặc bind DTO rồi validate ở tầng phù hợp |
| Quy tắc chuyển đổi phụ thuộc annotation/config của từng property | Cân nhắc `ContextualDeserializer` |
| JSON động cần duyệt/chỉnh sửa trước khi tạo kiểu đích | Tree Model hoặc Streaming API ở tầng gọi |

Custom deserializer phù hợp khi quy tắc là một phần ổn định của kiểu giá trị. Nếu mỗi endpoint cần một cách diễn giải khác nhau, hãy cân nhắc tạo các DTO/value type riêng hoặc dùng contextual configuration. Không nên nhồi mọi chính sách của API vào một deserializer toàn cục.

## 3. Hiểu token hiện tại trước khi đọc

`JsonDeserializer<T>` nhận một `JsonParser` đang đứng tại token bắt đầu của giá trị cần chuyển đổi. Deserializer cần kiểm tra `p.currentToken()` để biết JSON đang cung cấp object, array, string hay scalar.

Với ba dạng `GeoPoint`, token đầu tiên sẽ là:

| JSON | Token đầu tiên của giá trị |
|---|---|
| `{"latitude":10.7,"longitude":106.6}` | `START_OBJECT` |
| `[10.7,106.6]` | `START_ARRAY` |
| `"10.7,106.6"` | `VALUE_STRING` |
| `null` | `VALUE_NULL` (thường được xử lý riêng bởi Jackson trước `deserialize()`) |
| `10.7` | `VALUE_NUMBER_FLOAT` |

Deserializer cần tiêu thụ đúng phạm vi value của nó. Nếu giá trị là object, nó đọc tới `END_OBJECT`; nếu là array, nó đọc tới `END_ARRAY`; nếu là scalar, nó đọc giá trị hiện tại. Sau khi hoàn tất, parser phải ở đúng vị trí để Jackson tiếp tục đọc property hoặc phần tử kế tiếp.

## 4. Cài đặt deserializer cho object, array và string

Ví dụ dưới đây mở rộng `StdDeserializer<GeoPoint>`. Quy tắc đầu vào được định nghĩa rõ:

- Object phải có cả `latitude` và `longitude`.
- Mỗi tọa độ trong object có thể là JSON number hoặc chuỗi thập phân.
- Array phải có đúng hai phần tử theo thứ tự `[latitude, longitude]`.
- String phải có đúng hai số thập phân phân tách bằng một dấu phẩy.
- Field lạ, field trùng, thiếu tọa độ, giá trị rỗng hoặc token khác đều bị từ chối.
- Tọa độ được kiểm tra giới hạn bởi constructor của `GeoPoint`.

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;

public final class GeoPointDeserializer extends StdDeserializer<GeoPoint> {
    public GeoPointDeserializer() {
        super(GeoPoint.class);
    }

    @Override
    public GeoPoint deserialize(JsonParser p, DeserializationContext ctxt)
            throws IOException {
        JsonToken token = p.currentToken();

        if (token == JsonToken.START_OBJECT) {
            return readObject(p);
        }
        if (token == JsonToken.START_ARRAY) {
            return readArray(p);
        }
        if (token == JsonToken.VALUE_STRING) {
            return readCompactString(p);
        }

        throw JsonMappingException.from(
                p,
                "GeoPoint must be an object, a two-element array, or a comma-separated string"
        );
    }

    private GeoPoint readObject(JsonParser p) throws IOException {
        BigDecimal latitude = null;
        BigDecimal longitude = null;
        Set<String> seen = new HashSet<>();

        JsonToken token;
        while ((token = p.nextToken()) != JsonToken.END_OBJECT) {
            if (token == null) {
                throw JsonMappingException.from(p, "Unexpected end of GeoPoint object");
            }
            if (token != JsonToken.FIELD_NAME) {
                throw JsonMappingException.from(p, "Expected a GeoPoint property name");
            }

            String fieldName = p.currentName();
            if (!seen.add(fieldName)) {
                throw JsonMappingException.from(
                        p,
                        "Duplicate GeoPoint property: " + fieldName
                );
            }

            JsonToken valueToken = p.nextToken();
            if (valueToken == null) {
                throw JsonMappingException.from(
                        p,
                        "Missing value for GeoPoint property: " + fieldName
                );
            }

            switch (fieldName) {
                case "latitude" -> latitude = readDecimal(p, "latitude");
                case "longitude" -> longitude = readDecimal(p, "longitude");
                default -> throw JsonMappingException.from(
                        p,
                        "Unknown GeoPoint property: " + fieldName
                );
            }
        }

        return createPoint(latitude, longitude, p);
    }

    private GeoPoint readArray(JsonParser p) throws IOException {
        JsonToken token = p.nextToken();
        if (token == null || token == JsonToken.END_ARRAY) {
            throw JsonMappingException.from(p, "GeoPoint array must contain latitude and longitude");
        }
        BigDecimal latitude = readDecimal(p, "latitude");

        token = p.nextToken();
        if (token == null || token == JsonToken.END_ARRAY) {
            throw JsonMappingException.from(p, "GeoPoint array is missing longitude");
        }
        BigDecimal longitude = readDecimal(p, "longitude");

        token = p.nextToken();
        if (token != JsonToken.END_ARRAY) {
            throw JsonMappingException.from(p, "GeoPoint array must contain exactly two values");
        }

        return createPoint(latitude, longitude, p);
    }

    private GeoPoint readCompactString(JsonParser p) throws IOException {
        String text = p.getText().trim();
        String[] parts = text.split(",", -1);
        if (parts.length != 2) {
            throw JsonMappingException.from(
                    p,
                    "GeoPoint string must have the form 'latitude,longitude'"
            );
        }

        BigDecimal latitude = parseDecimal(parts[0].trim(), "latitude", p);
        BigDecimal longitude = parseDecimal(parts[1].trim(), "longitude", p);
        return createPoint(latitude, longitude, p);
    }

    private BigDecimal readDecimal(JsonParser p, String coordinateName)
            throws IOException {
        JsonToken token = p.currentToken();

        if (token == JsonToken.VALUE_NUMBER_INT || token == JsonToken.VALUE_NUMBER_FLOAT) {
            return p.getDecimalValue();
        }
        if (token == JsonToken.VALUE_STRING) {
            return parseDecimal(p.getText().trim(), coordinateName, p);
        }

        throw JsonMappingException.from(
                p,
                coordinateName + " must be a JSON number or a decimal string"
        );
    }

    private BigDecimal parseDecimal(
            String text,
            String coordinateName,
            JsonParser p
    ) throws JsonMappingException {
        if (text.isEmpty()) {
            throw JsonMappingException.from(p, coordinateName + " must not be empty");
        }

        try {
            return new BigDecimal(text);
        } catch (NumberFormatException ex) {
            throw JsonMappingException.from(
                    p,
                    coordinateName + " is not a valid decimal number: " + text
            );
        }
    }

    private GeoPoint createPoint(
            BigDecimal latitude,
            BigDecimal longitude,
            JsonParser p
    ) throws JsonMappingException {
        if (latitude == null) {
            throw JsonMappingException.from(p, "GeoPoint is missing required property 'latitude'");
        }
        if (longitude == null) {
            throw JsonMappingException.from(p, "GeoPoint is missing required property 'longitude'");
        }

        try {
            return new GeoPoint(latitude, longitude);
        } catch (IllegalArgumentException ex) {
            throw JsonMappingException.from(p, ex.getMessage());
        }
    }
}
```

Deserializer xử lý ba token shape bằng ba phương thức riêng. Mỗi phương thức trả về cùng một `GeoPoint`, vì vậy các tầng sau không cần biết client đã gửi object, array hay string.

### 4.1. Vì sao object cần kiểm tra thứ tự field và field trùng?

JSON object không quy định thứ tự property. `longitude` có thể xuất hiện trước `latitude`; code dùng biến tạm nên không phụ thuộc thứ tự. `Set<String>` ghi nhận tên đã gặp để từ chối key trùng. Đây là chính sách rõ ràng cho value object; nếu parser đã bật strict duplicate detection ở `JsonFactory`, parser cũng có thể phát hiện duplicate property trước đó.

Việc kiểm tra field trùng hữu ích vì nhiều parser hoặc hệ thống trung gian có thể chọn giá trị đầu tiên, giá trị cuối cùng hoặc báo lỗi. Với dữ liệu điều khiển hành vi, không nên để kết quả phụ thuộc vào cách từng bên xử lý key trùng.

### 4.2. Vì sao array phải có đúng hai phần tử?

Array có thứ tự, nên hợp đồng cần nói rõ phần tử đầu là latitude và phần tử thứ hai là longitude. Nếu array có một phần tử, thiếu dữ liệu; nếu có ba phần tử, không rõ phần tử thứ ba mang ý nghĩa gì. Từ chối shape không đúng giúp phát hiện client gửi nhầm format.

Deserializer cũng phải bảo đảm parser tiêu thụ tới `END_ARRAY` của value hợp lệ. Với trường hợp có phần tử thứ ba, code phát sinh lỗi thay vì âm thầm bỏ phần dư.

### 4.3. Vì sao không dùng `double` trung gian?

`JsonParser.getDecimalValue()` đọc numeric token thành `BigDecimal`. Với string, constructor `new BigDecimal(text)` phân tích trực tiếp nội dung thập phân. Không chuyển qua `getDoubleValue()` rồi `BigDecimal.valueOf()` vì như vậy có thể mất thông tin chính xác đã có trong JSON.

## 5. Gắn deserializer với kiểu Java

Có hai cách phổ biến để Jackson sử dụng custom deserializer.

### 5.1. Gắn bằng `@JsonDeserialize`

Đặt annotation trên kiểu giá trị:

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import java.math.BigDecimal;

@JsonDeserialize(using = GeoPointDeserializer.class)
public record GeoPoint(BigDecimal latitude, BigDecimal longitude) {
    // Constructor compact có kiểm tra invariant như ví dụ phía trên.
}
```

Khi đó, mọi property có kiểu `GeoPoint` được xử lý bằng deserializer này, trừ khi cấu hình ở vị trí cụ thể ghi đè theo quy tắc Jackson. Cách này phù hợp khi nhiều cách biểu diễn là một đặc tính chung của kiểu `GeoPoint`.

Có thể gắn annotation ở một property nếu chỉ property đó cần quy tắc đặc biệt:

```java
public record DeliveryRequest(
        @JsonDeserialize(using = GeoPointDeserializer.class)
        GeoPoint destination
) {
}
```

### 5.2. Đăng ký bằng `SimpleModule`

Nếu không muốn đặt annotation trong domain class hoặc không thể sửa lớp nguồn, đăng ký deserializer qua module:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule geoModule = new SimpleModule();
geoModule.addDeserializer(GeoPoint.class, new GeoPointDeserializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(geoModule);
```

Module phù hợp khi muốn tập trung cấu hình Jackson tại composition root, hoặc khi cùng một kiểu Java cần cách đọc khác nhau trong những mapper dành cho các integration khác nhau.

Không cần vừa đăng ký module vừa gắn annotation cho cùng một kiểu nếu không có lý do cụ thể. Hãy chọn một nơi chịu trách nhiệm rõ ràng để tránh khó hiểu khi thứ tự ưu tiên annotation/module thay đổi theo cấu hình.

## 6. Sử dụng trong DTO, collection và wrapper generic

Sau khi đăng ký, có thể dùng `GeoPoint` như một kiểu Java bình thường:

```java
public record DeliveryRequest(
        String orderId,
        GeoPoint destination
) {
}
```

Ba JSON sau đều có thể ánh xạ vào property `destination`:

```json
{"orderId":"ORD-1","destination":{"latitude":10.7626,"longitude":106.6602}}
```

```json
{"orderId":"ORD-1","destination":[10.7626,106.6602]}
```

```json
{"orderId":"ORD-1","destination":"10.7626,106.6602"}
```

Deserializer cũng được dùng cho phần tử collection:

```java
List<GeoPoint> points = mapper.readValue(
        json,
        new TypeReference<List<GeoPoint>>() {}
);
```

Hoặc value của map:

```java
Map<String, GeoPoint> locations = mapper.readValue(
        json,
        new TypeReference<Map<String, GeoPoint>>() {}
);
```

Với wrapper generic:

```java
ApiEnvelope<List<GeoPoint>> response = mapper.readValue(
        json,
        new TypeReference<ApiEnvelope<List<GeoPoint>>>() {}
);
```

`TypeReference` giữ kiểu generic của container; custom deserializer được gọi cho từng giá trị `GeoPoint`. Hai cơ chế giải quyết hai vấn đề riêng: generic type xác định vị trí có kiểu `GeoPoint`, còn deserializer quyết định cách chuyển token tại vị trí đó thành object.

## 7. Quyết định chính sách cho JSON null và field thiếu

Null, field thiếu và chuỗi rỗng là ba tình huống khác nhau:

```json
{"destination": null}
```

```json
{}
```

```json
{"destination": ""}
```

Với property reference như `GeoPoint`, Jackson thường xử lý JSON `null` qua `getNullValue()` của deserializer (hoặc giá trị mặc định của context), thay vì gọi `deserialize()` như với object/array/string. Trong ví dụ trên, null được chấp nhận và property nhận Java `null`.

Field thiếu không gọi deserializer cho property đó; kết quả phụ thuộc constructor/creator, giá trị mặc định của field hoặc validation của DTO. Nếu `destination` bắt buộc, hãy thể hiện điều đó bằng Bean Validation hoặc constructor/domain validation, ví dụ `@NotNull`.

Chuỗi rỗng là một `VALUE_STRING` và đi vào `deserialize()`. Deserializer ở trên từ chối vì không có đủ hai tọa độ. Không nên tự động biến chuỗi rỗng thành null trừ khi hợp đồng API định nghĩa rõ điều đó.

Nếu kiểu không được phép null, có thể override `getNullValue()` để ném lỗi mapping thay vì trả null. Cần chọn chính sách theo semantics của value object và áp dụng nhất quán ở mọi property sử dụng kiểu đó.

## 8. Unknown fields: từ chối hay bỏ qua?

Ví dụ object:

```json
{
  "latitude": 10.7626,
  "longitude": 106.6602,
  "altitude": 12
}
```

Deserializer mẫu từ chối `altitude` vì `GeoPoint` chỉ có hai thành phần. Đây là lựa chọn strict: nếu client gửi sai tên hoặc nhầm một schema khác, lỗi xuất hiện ngay.

Nếu hợp đồng cần forward compatibility và cho phép bỏ qua property mở rộng, nhánh `default` có thể dùng:

```java
default -> p.skipChildren();
```

Lúc này parser đang đứng ở token bắt đầu value của field lạ. `skipChildren()` bỏ qua toàn bộ object/array lồng nhau nếu có; với scalar, lời gọi không làm gì. Sau đó vòng lặp tiếp tục đọc field kế tiếp.

Không chọn ignore unknown chỉ để tránh lỗi. Nếu field lạ có thể ảnh hưởng đến ý nghĩa tọa độ, việc bỏ qua nó có thể làm dữ liệu bị diễn giải sai. Chính sách strict hay tolerant phải là một phần của hợp đồng.

## 9. Báo lỗi có ngữ cảnh bằng `JsonMappingException`

Custom deserializer nên báo lỗi theo loại vấn đề cụ thể:

- Root token không thuộc object, array hoặc string được hỗ trợ.
- Object thiếu `latitude` hoặc `longitude`.
- Có property không biết hoặc trùng tên.
- Array không có đúng hai phần tử.
- Tọa độ là boolean, object hoặc null thay vì number/string hợp lệ.
- Chuỗi không phân tích được thành số thập phân.
- Giá trị nằm ngoài phạm vi latitude/longitude.

Trong ví dụ, `JsonMappingException.from(parser, message)` tạo lỗi ánh xạ gắn với vị trí parser. Khi deserializer được gọi cho một property lồng trong DTO, Jackson có thể bổ sung path của property vào exception để thông báo lỗi có ngữ cảnh hơn.

Không nên bắt mọi `Exception` rồi trả về `null`. Cách đó biến dữ liệu sai thành giá trị thiếu, che giấu lỗi đầu vào và khiến tầng nghiệp vụ khó phân biệt. Chỉ bắt exception cụ thể cần chuyển đổi, giữ thông tin nguyên nhân và ném một mapping exception phù hợp.

Ở ranh giới REST API, có thể chuyển lỗi mapping thành `400 Bad Request` cùng mã lỗi/field path phù hợp. Không trả stack trace hoặc chi tiết nội bộ cho client.

## 10. Giữ đầu ra JSON ở một dạng chuẩn

Một deserializer có thể chấp nhận nhiều dạng đầu vào nhưng serializer vẫn nên xuất một dạng canonical duy nhất. Với `GeoPoint` là record, serializer mặc định của Jackson ghi:

```json
{
  "latitude": 10.7626,
  "longitude": 106.6602
}
```

Do đó, cả ba input:

```json
"10.7626,106.6602"
```

```json
[10.7626,106.6602]
```

```json
{"latitude":10.7626,"longitude":106.6602}
```

sau khi đọc thành `GeoPoint` rồi ghi lại đều trở về dạng object chuẩn. Điều này tạo ra một quy tắc hữu ích:

**Đọc linh hoạt theo những alias/shape đã công bố; ghi nhất quán theo một representation chuẩn.**

Canonical output giúp client mới không phải hỗ trợ mọi định dạng legacy, tài liệu schema dễ hiểu hơn và test contract ổn định hơn. Nếu cần serializer tùy biến, chỉ viết khi serializer mặc định của record không tạo đúng dạng canonical đã chọn.

## 11. Khi cần cả custom serializer và deserializer

Custom deserializer chỉ kiểm soát chiều đọc. Nếu đầu ra cần một format khác mặc định, có thể viết thêm `JsonSerializer<GeoPoint>`.

Ví dụ, nếu hợp đồng bắt buộc ghi tọa độ thành array:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;

public final class GeoPointArraySerializer extends JsonSerializer<GeoPoint> {
    @Override
    public void serialize(
            GeoPoint value,
            JsonGenerator generator,
            SerializerProvider serializers
    ) throws IOException {
        generator.writeStartArray();
        generator.writeNumber(value.latitude());
        generator.writeNumber(value.longitude());
        generator.writeEndArray();
    }
}
```

Có thể gắn cả hai annotation:

```java
@JsonDeserialize(using = GeoPointDeserializer.class)
@JsonSerialize(using = GeoPointArraySerializer.class)
public record GeoPoint(BigDecimal latitude, BigDecimal longitude) {
    // Invariant validation.
}
```

Khi đó, input vẫn chấp nhận object/array/string, còn output luôn là array. Tuy nhiên, cần cân nhắc consumer: nếu canonical output là array, thứ tự latitude/longitude phải được tài liệu hóa rõ. Nếu không có lý do về kích thước hoặc hợp đồng cũ, object có tên field thường dễ đọc và ít gây nhầm lẫn hơn.

## 12. Dùng Tree Model thay vì tự quản lý token khi phù hợp

Không phải custom deserializer nào cũng cần tự viết vòng lặp token. Nếu logic dựa nhiều vào việc kiểm tra một cấu trúc nhỏ, có thể đọc value thành `JsonNode` rồi xử lý từng shape:

```java
@Override
public GeoPoint deserialize(JsonParser p, DeserializationContext ctxt)
        throws IOException {
    JsonNode node = p.getCodec().readTree(p);

    if (node.isObject()) {
        JsonNode latitude = node.get("latitude");
        JsonNode longitude = node.get("longitude");
        // Kiểm tra field, kiểu và tạo GeoPoint.
    } else if (node.isArray()) {
        // Kiểm tra đúng hai phần tử.
    } else if (node.isTextual()) {
        // Parse chuỗi gọn.
    }

    throw JsonMappingException.from(p, "Unsupported GeoPoint representation");
}
```

Tree-based deserializer dễ viết khi cần truy cập field không phụ thuộc thứ tự hoặc thực hiện nhiều phép kiểm tra. Đổi lại, nó tạo cây node trung gian cho value đang đọc. Với value nhỏ như `GeoPoint`, chi phí thường không đáng kể; với payload lồng sâu hoặc rất lớn, streaming token có thể tiết kiệm cấp phát hơn.

Nếu dùng Tree Model, vẫn cần phân biệt `node.get("field") == null` (field thiếu), `NullNode` (field có JSON null) và node sai kiểu. Không gọi `asDouble()` rồi chấp nhận mặc định khi node không phải number nếu hợp đồng yêu cầu kiểu chặt chẽ.

## 13. Deserializer theo từng property và `ContextualDeserializer`

Một kiểu Java có thể được dùng trong hai property với quy tắc khác nhau. Ví dụ, `GeoPoint` ở một API yêu cầu string compact được phép, còn API khác chỉ chấp nhận object và array. Nếu behavior thật sự phụ thuộc metadata của property, có thể triển khai `ContextualDeserializer` để tạo biến thể theo `BeanProperty`.

Không nên lưu cờ cấu hình mutable vào một deserializer dùng chung rồi thay đổi nó theo từng request. Deserializer thường được cache và tái sử dụng; trạng thái mutable có thể làm request này ảnh hưởng request khác.

Các lựa chọn đơn giản hơn thường là:

- Tạo hai value type/DTO khác nhau nếu hai hợp đồng khác nhau về semantics.
- Dùng hai `ObjectMapper`/module riêng cho hai integration nếu quy tắc ở cấp mapper.
- Dùng `ContextualDeserializer` khi khác biệt gắn với annotation hoặc metadata của property.

Khi triển khai contextual deserializer, phương thức `createContextual()` nên trả về một instance đã cấu hình bất biến cho property đó. Không thay đổi instance dùng chung.

## 14. Kiểm thử mọi representation được hỗ trợ

Custom deserializer là một hợp đồng parsing. Mỗi dạng JSON được công bố cần có test thành công; mỗi dạng sai cần có test bị từ chối.

```java
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

class GeoPointDeserializerTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsObjectRepresentation() throws Exception {
        GeoPoint point = mapper.readValue(
                "{\"latitude\":10.7626,\"longitude\":106.6602}",
                GeoPoint.class
        );

        assertEquals(0, point.latitude().compareTo(new BigDecimal("10.7626")));
        assertEquals(0, point.longitude().compareTo(new BigDecimal("106.6602")));
    }

    @Test
    void readsArrayRepresentation() throws Exception {
        GeoPoint point = mapper.readValue("[10.7626,106.6602]", GeoPoint.class);

        assertEquals(new BigDecimal("10.7626"), point.latitude());
        assertEquals(new BigDecimal("106.6602"), point.longitude());
    }

    @Test
    void readsCompactStringRepresentation() throws Exception {
        GeoPoint point = mapper.readValue(
                "\"10.7626, 106.6602\"",
                GeoPoint.class
        );

        assertEquals(new BigDecimal("10.7626"), point.latitude());
        assertEquals(new BigDecimal("106.6602"), point.longitude());
    }

    @Test
    void rejectsArrayWithExtraValue() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue("[10.0,20.0,30.0]", GeoPoint.class));
    }

    @Test
    void rejectsOutOfRangeLatitude() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue("[91,20]", GeoPoint.class));
    }

    @Test
    void rejectsUnknownObjectProperty() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue(
                        "{\"latitude\":10,\"longitude\":20,\"altitude\":5}",
                        GeoPoint.class
                ));
    }
}
```

Test dùng `compareTo()` khi so sánh decimal nếu scale có thể khác. `BigDecimal.equals()` xét cả scale, nên `10.0` và `10.00` không bằng nhau theo `equals()` dù có cùng giá trị số.

Ngoài test từng representation, nên kiểm tra:

- Field object xuất hiện theo cả hai thứ tự.
- Thiếu latitude hoặc longitude.
- Field trùng nếu parser policy yêu cầu từ chối.
- Chuỗi có dấu phẩy thiếu/thừa hoặc phần tử rỗng.
- String chứa chữ, `NaN`, `Infinity` hoặc format không được công bố.
- Token root là boolean, number hoặc null theo null policy.
- Tọa độ đúng biên `-90`, `90`, `-180`, `180` và nằm ngoài biên.
- Deserializer hoạt động bên trong DTO, list, map và wrapper generic.
- Serialization luôn tạo canonical output như hợp đồng đã chọn.

## 15. Những lỗi thiết kế thường gặp

### 15.1. Chấp nhận quá nhiều dạng mà không có hợp đồng

Nếu deserializer tự động chấp nhận object, array, string, number, map và mọi dạng scalar khác, client khó biết format nào được hỗ trợ lâu dài. Hãy liệt kê chính xác các shape hợp lệ và từ chối phần còn lại.

### 15.2. Dựa vào thứ tự field trong JSON object

Object property không có thứ tự ngữ nghĩa. Hãy đọc từng field theo tên, lưu vào biến tạm rồi tạo value object sau khi đã đọc xong object.

### 15.3. Không kiểm tra phần tử dư trong array

Nếu hợp đồng là cặp `[latitude, longitude]`, phải từ chối array có một hoặc ba phần tử. Đọc hai phần tử đầu rồi bỏ qua phần còn lại sẽ che giấu lỗi client.

### 15.4. Chuyển number qua `double`

Đối với số thập phân cần giữ chính xác, dùng `getDecimalValue()` hoặc parse string trực tiếp thành `BigDecimal`.

### 15.5. Bắt lỗi rồi trả null

Trả null khi parse thất bại làm dữ liệu sai trở thành dữ liệu thiếu. Hãy ném `JsonMappingException` với thông báo cụ thể và giữ nguyên ngữ cảnh lỗi.

### 15.6. Quên chính sách null

JSON null thường được xử lý qua `getNullValue()` riêng. Nếu kiểu bắt buộc, hãy từ chối null; nếu nullable, ghi rõ semantics. Đừng nhầm null với field thiếu hoặc chuỗi rỗng.

### 15.7. Để custom deserializer thay đổi trạng thái dùng chung

Deserializer có thể được cache và dùng đồng thời. Tránh lưu dữ liệu của request hiện tại trong field mutable. Dùng biến cục bộ và cấu hình bất biến.

### 15.8. Chấp nhận input linh hoạt nhưng output cũng thay đổi ngẫu nhiên

Hỗ trợ nhiều dạng đọc không có nghĩa phải ghi lại đúng hình thức client đã gửi. Chọn một canonical representation để output ổn định, dễ tài liệu hóa và dễ kiểm thử.

## 16. Quy trình thiết kế deserializer cho kiểu nhiều representation

Khi cần tạo một custom deserializer, có thể thực hiện theo trình tự:

1. **Xác định ý nghĩa duy nhất:** các hình dạng JSON phải cùng ánh xạ vào một value object có semantics rõ.
2. **Liệt kê shape được phép:** object, array, string hoặc scalar; mô tả thứ tự và tên field.
3. **Quy định null/missing:** xác định nullable, field bắt buộc và giá trị mặc định nếu có.
4. **Chọn kiểu số và ngày giờ:** giữ precision và timezone theo hợp đồng.
5. **Đọc token có kiểm soát:** kiểm tra `currentToken()`, tiêu thụ đúng value và không lệch parser position.
6. **Kiểm tra cấu trúc:** field thiếu/trùng/lạ, số phần tử, kiểu token và format.
7. **Kiểm tra ngữ nghĩa:** range, invariant và quan hệ giữa các thành phần.
8. **Báo lỗi mapping rõ ràng:** không nuốt exception hoặc biến lỗi thành null.
9. **Chọn cách đăng ký:** annotation, property annotation hoặc `SimpleModule`.
10. **Chuẩn hóa đầu ra:** quyết định representation canonical và serializer tương ứng nếu cần.
11. **Kiểm thử đầy đủ:** mọi shape hợp lệ, shape lỗi, null, generic container và round-trip.

## 17. Chọn kỹ thuật theo tình huống

| Tình huống | Cách xử lý |
|---|---|
| Một kiểu value nhận object, array và string | `JsonDeserializer<T>` kiểm tra `JsonToken` |
| Nhiều property scalar cần chuyển đổi đơn giản | Coercion hoặc deserializer mặc định |
| Cần đọc object theo tên field, không phụ thuộc thứ tự | Vòng lặp token hoặc `JsonNode` |
| Cần xử lý payload nhỏ với logic kiểm tra cấu trúc linh hoạt | Tree-based custom deserializer |
| Cần hiệu quả với payload lớn và parser position rõ ràng | Streaming token trong custom deserializer |
| Quy tắc phụ thuộc property annotation | `ContextualDeserializer` |
| Không thể sửa lớp value object | Đăng ký qua `SimpleModule` |
| Nhiều cách đọc nhưng một output ổn định | Custom deserializer và serializer mặc định/canonical serializer |
| Cần giữ nguyên JSON text/byte gốc | Lưu raw input; deserialize rồi serialize không bảo toàn văn bản gốc |

Một custom deserializer tốt biến nhiều cách biểu diễn JSON thành một kiểu Java thống nhất mà không làm mất ý nghĩa dữ liệu. Hãy xác định trước các shape được phép, đọc token đúng vị trí, kiểm tra field và giới hạn, giữ độ chính xác của số, phân biệt null với thiếu dữ liệu và báo lỗi mapping rõ ràng. Dùng `@JsonDeserialize` hoặc `SimpleModule` để đăng ký theo phạm vi phù hợp. Nếu đầu vào cần linh hoạt vì tương thích, hãy giữ đầu ra ở một representation canonical để hợp đồng JSON vẫn dễ hiểu và ổn định.
