# Xử lý khóa Map không phải String

Trong Java, `Map<K, V>` cho phép kiểu khóa `K` là nhiều loại dữ liệu: `Integer`, `Long`, enum, `UUID` hoặc một class do ứng dụng tự định nghĩa. Tuy nhiên, JSON object chỉ cho phép tên thuộc tính là chuỗi. Vì vậy, khi Jackson chuyển một `Map` thành JSON object, khóa Java phải được chuyển thành tên field JSON; khi đọc lại, Jackson phải chuyển tên field đó về kiểu khóa mà ứng dụng yêu cầu.

Jackson xử lý việc này bằng **key serializer** và **key deserializer**. Chúng có vai trò riêng với serializer/deserializer của giá trị trong map:

- Key serializer chuyển khóa Java thành tên field JSON dạng `String`.
- Key deserializer chuyển tên field JSON dạng `String` thành khóa Java.
- Value serializer/deserializer xử lý giá trị `V` của từng entry.

Với kiểu khóa phổ biến, Jackson thường đã có cách chuyển đổi mặc định. Với khóa là object nghiệp vụ hoặc có định dạng đặc biệt, ứng dụng cần định nghĩa cách mã hóa và giải mã rõ ràng.

## 1. Vì sao khóa Map phải được chuyển thành String?

JSON object có dạng:

```json
{
  "name": "An",
  "active": true,
  "age": 25
}
```

Tên của mỗi thành viên object (`name`, `active`, `age`) đều là chuỗi. JSON không có cú pháp object member name mang trực tiếp kiểu number, enum hay object Java.

Do đó, một map Java như sau:

```java
Map<Integer, String> labels = new LinkedHashMap<>();
labels.put(10, "Ten");
labels.put(20, "Twenty");
```

có thể được Jackson ghi thành JSON object:

```json
{
  "10": "Ten",
  "20": "Twenty"
}
```

Các khóa `10` và `20` đã trở thành tên field JSON là `"10"` và `"20"`. Giá trị vẫn là string như ban đầu. Khi đọc JSON, nếu kiểu đích là `Map<Integer, String>`, Jackson có thể dùng key deserializer dành cho `Integer` để chuyển các tên field trở lại thành khóa số nguyên.

Điều quan trọng là phải phân biệt khóa và giá trị. Key serializer không ghi một JSON number token cho khóa; nó ghi **field name**. Value serializer mới ghi token tương ứng với kiểu giá trị như string, number, object hoặc array.

## 2. Sử dụng kiểu khóa phổ biến có sẵn

Jackson cung cấp xử lý khóa mặc định cho nhiều kiểu phổ biến. Ví dụ thường gặp gồm chuỗi, các kiểu số, boolean, enum và một số kiểu JDK như UUID. Các module mở rộng cũng có thể bổ sung key serializer/deserializer cho kiểu dữ liệu riêng của chúng.

### 2.1. Khóa Integer

```java
ObjectMapper mapper = new ObjectMapper();

Map<Integer, String> source = new LinkedHashMap<>();
source.put(10, "Ten");
source.put(20, "Twenty");

String json = mapper.writeValueAsString(source);
// {"10":"Ten","20":"Twenty"}

Map<Integer, String> restored = mapper.readValue(
        json,
        new TypeReference<Map<Integer, String>>() { }
);
```

Khi deserialize, kiểu đích `Map<Integer, String>` cung cấp thông tin để Jackson chọn key deserializer cho `Integer`. Nếu đọc thành raw `Map.class`, Jackson không có thông tin kiểu khóa mong muốn và các tên field thường được giữ dưới dạng `String`.

### 2.2. Khóa enum

```java
enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}

Map<OrderStatus, Integer> counts = new EnumMap<>(OrderStatus.class);
counts.put(OrderStatus.NEW, 5);
counts.put(OrderStatus.PAID, 12);

String json = mapper.writeValueAsString(counts);

Map<OrderStatus, Integer> restored = mapper.readValue(
        json,
        new TypeReference<Map<OrderStatus, Integer>>() { }
);
```

Jackson có thể biểu diễn khóa enum bằng tên dạng chuỗi và khôi phục khóa khi biết kiểu đích là `OrderStatus`. Nếu hợp đồng dữ liệu dùng một mã enum tùy chỉnh thay cho tên hằng, hãy cấu hình key serializer/deserializer rõ ràng và kiểm tra cả hai chiều. Không nên mặc định rằng mọi annotation hoặc feature dành cho enum value sẽ tác động hoàn toàn giống nhau lên enum map key.

### 2.3. Khóa UUID

UUID thường được biểu diễn bằng chuỗi chuẩn, ví dụ `"550e8400-e29b-41d4-a716-446655440000"`. Với kiểu đích `Map<UUID, V>`, Jackson có thể sử dụng hỗ trợ key conversion tương ứng:

```java
Map<UUID, String> sessions = new LinkedHashMap<>();
UUID sessionId = UUID.fromString(
        "550e8400-e29b-41d4-a716-446655440000"
);
sessions.put(sessionId, "ACTIVE");

String json = mapper.writeValueAsString(sessions);

Map<UUID, String> restored = mapper.readValue(
        json,
        new TypeReference<Map<UUID, String>>() { }
);
```

Khi dùng kiểu từ module bên ngoài hoặc một phiên bản Jackson khác, hãy xác nhận module tương ứng đã được đăng ký và key codec cần thiết có sẵn. Nếu không có hỗ trợ mặc định, hãy đăng ký key deserializer/serializer riêng.

## 3. Kiểu đích generic vẫn rất quan trọng

Khóa và giá trị của map đều có thể là kiểu generic. Khi đọc JSON, Jackson cần biết cả `K` và `V` để chọn đúng key deserializer và value deserializer.

Ví dụ:

```java
ObjectReader reader = mapper.readerFor(
        new TypeReference<Map<Integer, User>>() { }
);

Map<Integer, User> users = reader.readValue(json);
```

Trong trường hợp này:

- Tên field JSON được chuyển thành `Integer`.
- Giá trị object JSON của mỗi field được deserialize thành `User`.

Nếu cấu trúc kiểu được xây dựng ở runtime, có thể dùng `JavaType`:

```java
JavaType mapType = mapper.getTypeFactory().constructMapType(
        Map.class,
        Integer.class,
        User.class
);

ObjectReader reader = mapper.readerFor(mapType);
Map<Integer, User> users = reader.readValue(json);
```

Không dùng `Map.class` khi ứng dụng cần giữ kiểu khóa hoặc giá trị cụ thể. Java type erasure làm mất thông tin generic nếu chỉ truyền raw class.

## 4. Cơ chế key serializer và key deserializer

Jackson xử lý map key bằng API riêng vì khóa JSON nằm ở vị trí field name, không phải value token.

| Thành phần | API | Nhiệm vụ |
|---|---|---|
| Key serializer | `JsonSerializer<K>` đăng ký như key serializer | Ghi khóa thành tên field bằng `JsonGenerator.writeFieldName(...)` |
| Key deserializer | `KeyDeserializer` | Nhận tên field JSON dạng `String` và tạo khóa Java |
| Value serializer | `JsonSerializer<V>` | Ghi giá trị map thành JSON token/object/array |
| Value deserializer | `JsonDeserializer<V>` hoặc cơ chế mặc định | Đọc giá trị map thành kiểu `V` |

Một custom key serializer vẫn kế thừa `JsonSerializer`, nhưng được đăng ký ở vị trí key. Trong phương thức `serialize`, nó phải ghi field name phù hợp. Không gọi `writeStartObject()` hoặc ghi một object JSON độc lập cho khóa, vì vị trí đó trong JSON object chỉ chấp nhận tên field.

## 5. Tạo key serializer cho kiểu khóa nghiệp vụ

Giả sử hệ thống quản lý số lượng sản phẩm theo mã SKU và mã kho. Một khóa Java có hai thành phần:

```java
public record ProductKey(String sku, int warehouseId) {
}
```

Nếu dùng `ProductKey` làm khóa map, JSON object không thể chứa trực tiếp một object Java làm tên field. Ứng dụng cần một chuỗi đại diện duy nhất cho cặp `sku` và `warehouseId`.

Trong ví dụ này, ta mã hóa SKU bằng Base64 URL-safe rồi nối với mã kho bằng dấu chấm. Alphabet Base64 URL-safe không chứa dấu chấm, nên dấu phân cách không bị nhầm với dữ liệu SKU.

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class ProductKeyKeySerializer
        extends JsonSerializer<ProductKey> {

    @Override
    public void serialize(
            ProductKey value,
            JsonGenerator gen,
            SerializerProvider serializers
    ) throws IOException {
        String encodedSku = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value.sku().getBytes(StandardCharsets.UTF_8));

        String fieldName = encodedSku + "." + value.warehouseId();
        gen.writeFieldName(fieldName);
    }
}
```

Ví dụ, `ProductKey("SKU/RED|2026", 7)` được chuyển thành một tên field dạng `U0tVL1JF RHwyMDI2.7` theo phép mã hóa Base64 URL-safe (giá trị thực tế không có dấu cách). Phần SKU có thể chứa dấu phân cách thông thường mà không làm hỏng cấu trúc chuỗi khóa.

Key serializer không quyết định cách serialize giá trị map. Nếu map là `Map<ProductKey, Integer>`, serializer cho khóa tạo field name còn serializer cho `Integer` ghi số lượng thành JSON number.

## 6. Tạo key deserializer để khôi phục kiểu khóa

Khi đọc JSON object, parser cung cấp tên field dưới dạng chuỗi. Key deserializer nhận chuỗi đó và chuyển thành `ProductKey`:

```java
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.KeyDeserializer;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class ProductKeyKeyDeserializer extends KeyDeserializer {

    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext ctxt
    ) throws IOException {
        int separator = key.lastIndexOf('.');
        if (separator <= 0 || separator == key.length() - 1) {
            throw ctxt.weirdKeyException(
                    ProductKey.class,
                    key,
                    "Expected Base64URL(SKU).<warehouseId>"
            );
        }

        try {
            String encodedSku = key.substring(0, separator);
            String sku = new String(
                    Base64.getUrlDecoder().decode(encodedSku),
                    StandardCharsets.UTF_8
            );
            int warehouseId = Integer.parseInt(
                    key.substring(separator + 1)
            );

            return new ProductKey(sku, warehouseId);
        } catch (IllegalArgumentException exception) {
            throw ctxt.weirdKeyException(
                    ProductKey.class,
                    key,
                    "SKU must be Base64 URL-safe and warehouseId must be an integer"
            );
        }
    }
}
```

Deserializer kiểm tra dấu phân cách, giải mã SKU và chuyển phần cuối thành số nguyên. Nếu chuỗi không đúng định dạng, nó ném lỗi ánh xạ khóa có ngữ cảnh thay vì trả về một object khóa không hợp lệ.

Định dạng khóa là một phần của JSON contract. Nếu ứng dụng thay đổi cách mã hóa từ `Base64URL(SKU).warehouseId` sang một định dạng khác, các JSON đã lưu hoặc đang được hệ thống khác gửi đến cũng cần được xử lý tương thích. Với dữ liệu lâu dài, hãy cân nhắc version hóa định dạng hoặc duy trì khả năng đọc định dạng cũ trong giai đoạn chuyển đổi.

## 7. Đăng ký key codec bằng SimpleModule

Có thể đăng ký key serializer và key deserializer ở cấp module để nhiều map cùng kiểu khóa sử dụng một quy tắc thống nhất:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule productKeyModule = new SimpleModule("product-key-module");
productKeyModule.addKeySerializer(
        ProductKey.class,
        new ProductKeyKeySerializer()
);
productKeyModule.addKeyDeserializer(
        ProductKey.class,
        new ProductKeyKeyDeserializer()
);

ObjectMapper mapper = new ObjectMapper()
        .registerModule(productKeyModule);
```

Sau khi đăng ký module, có thể serialize và deserialize map:

```java
Map<ProductKey, Integer> stock = new LinkedHashMap<>();
stock.put(new ProductKey("SKU/RED|2026", 7), 15);
stock.put(new ProductKey("SKU-BLUE", 8), 4);

String json = mapper.writeValueAsString(stock);

Map<ProductKey, Integer> restored = mapper.readValue(
        json,
        new TypeReference<Map<ProductKey, Integer>>() { }
);
```

Luồng xử lý:

```text
Serialize
Map<ProductKey, Integer>
        |
        +--> ProductKeyKeySerializer
        |       ProductKey -> JSON field name (String)
        |
        +--> Integer value serializer
                Integer -> JSON number
        |
        v
      JSON object

Deserialize
      JSON object
        |
        +--> field name (String)
        |       ProductKeyKeyDeserializer
        |       String -> ProductKey
        |
        +--> JSON number
                Integer value deserializer
        |
        v
Map<ProductKey, Integer>
```

Để round-trip thành công, kiểu đích khi deserialize phải chứa `ProductKey`. Nếu đọc cùng JSON thành `Map<String, Integer>`, Jackson sẽ giữ tên field dưới dạng `String` và không gọi key deserializer cho `ProductKey`.

## 8. Đăng ký codec ngay trên thuộc tính Map

Nếu một kiểu khóa chỉ được sử dụng trong một property, có thể cấu hình trực tiếp trên property bằng annotation:

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

public class InventorySnapshot {
    @JsonSerialize(keyUsing = ProductKeyKeySerializer.class)
    @JsonDeserialize(keyUsing = ProductKeyKeyDeserializer.class)
    private Map<ProductKey, Integer> quantities;

    public Map<ProductKey, Integer> getQuantities() {
        return quantities;
    }

    public void setQuantities(Map<ProductKey, Integer> quantities) {
        this.quantities = quantities;
    }
}
```

`keyUsing` chỉ định codec dành cho khóa map. Nó khác `using`, vốn chỉ định serializer/deserializer cho giá trị của property. Nếu map có kiểu `Map<ProductKey, Integer>`, `keyUsing` xử lý `ProductKey`, còn Jackson vẫn dùng serializer/deserializer thông thường cho `Integer`.

Chọn một nơi quản lý codec phù hợp:

- Đăng ký bằng `SimpleModule` khi quy tắc khóa là chính sách chung cho kiểu `ProductKey` trong ứng dụng.
- Dùng `keyUsing` trên property khi một map cụ thể cần quy tắc riêng.

Khi dùng cả module registration và property annotation, cần hiểu annotation có thể cung cấp cấu hình riêng cho property. Tránh cấu hình trùng lặp nếu không có lý do rõ ràng, vì người đọc sẽ khó biết codec nào đang điều khiển kết quả.

## 9. Khóa không phải String có thể bị mất thông tin hoặc va chạm

Việc chuyển khóa Java thành tên field JSON là một phép mã hóa. Muốn round-trip, phép mã hóa phải có khả năng phân biệt và giải mã.

### 9.1. Không dựa vào toString() nếu không có hợp đồng rõ ràng

Một class có thể kế thừa `Object.toString()`, trả về chuỗi chứa tên class và hash code. Chuỗi đó không phải định dạng ổn định để lưu trữ, trao đổi hoặc khôi phục object. Ngay cả khi đã override `toString()`, nó vẫn có thể chỉ phục vụ log và không bảo đảm duy nhất hoặc parse ngược được.

Ví dụ hai khóa khác nhau có thể cùng được chuyển thành chuỗi `"unknown"` nếu serializer tùy tiện dùng `toString()`. Khi đó, JSON object có thể chứa hai field cùng tên; parser hoặc consumer có thể giữ giá trị sau cùng và làm mất entry trước.

### 9.2. Kiểm tra va chạm sau khi mã hóa

Với `Map<Object, String>`, Java có thể phân biệt `Integer.valueOf(1)` và `"1"` vì chúng không bằng nhau. Nhưng nếu cả hai đều được chuyển thành tên field JSON `"1"`, kết quả JSON có hai member cùng tên:

```json
{
  "1": "numeric key",
  "1": "string key"
}
```

JSON object không nên dựa vào duplicate member name. Các parser có thể xử lý khác nhau; nhiều cấu hình sẽ giữ một giá trị và làm mất giá trị còn lại. Vì vậy, key serializer cần bảo đảm các khóa khác nhau trong map được mã hóa thành field name khác nhau.

### 9.3. Định dạng phải ổn định

Nếu khóa có ngày, số thập phân hoặc chuỗi phụ thuộc locale, không dùng format theo locale mặc định của máy. Ví dụ, cùng một ngày có thể được biểu diễn khác nhau theo `dd/MM/yyyy` hoặc `MM/dd/yyyy`; dấu thập phân cũng có thể khác theo locale.

Hãy chọn định dạng cố định, quy tắc escape rõ ràng và cách parse đối xứng. Với khóa ghép nhiều thành phần, cần một dấu phân cách không thể xuất hiện trong dữ liệu hoặc phải có cơ chế escape/encoding để không gây nhập nhằng.

## 10. Khi nào không nên dùng Map key làm JSON object field?

Custom key serializer phù hợp khi khóa có thể được biểu diễn thành một chuỗi ngắn, ổn định và có thể khôi phục. Nhưng nếu khóa là một object phức tạp có nhiều trường, việc nén object đó thành tên field thường làm JSON khó đọc và khó mở rộng.

Ví dụ khóa có cấu trúc:

```java
public record ProductKey(String sku, int warehouseId) {
}
```

Nếu cần thể hiện rõ cấu trúc khóa trong JSON, có thể đổi hợp đồng dữ liệu thành danh sách entry:

```java
public record InventoryEntry(ProductKey key, int quantity) {
}

public record InventoryDocument(List<InventoryEntry> entries) {
}
```

JSON khi đó có dạng:

```json
{
  "entries": [
    {
      "key": {
        "sku": "SKU/RED|2026",
        "warehouseId": 7
      },
      "quantity": 15
    },
    {
      "key": {
        "sku": "SKU-BLUE",
        "warehouseId": 8
      },
      "quantity": 4
    }
  ]
}
```

Mô hình này biểu diễn khóa như một object JSON bình thường, không cần biến nó thành tên field. Nó cũng dễ bổ sung thuộc tính cho entry như `unit`, `updatedAt` hoặc `source`.

Sau khi deserialize danh sách entry, ứng dụng có thể tạo lại map ở tầng nghiệp vụ:

```java
Map<ProductKey, Integer> stock = document.entries().stream()
        .collect(Collectors.toMap(
                InventoryEntry::key,
                InventoryEntry::quantity
        ));
```

Nếu dữ liệu có thể chứa nhiều entry cùng `ProductKey`, cần định nghĩa chính sách xử lý trùng trước khi dùng `toMap`, ví dụ từ chối dữ liệu, giữ giá trị đầu tiên, giữ giá trị cuối cùng hoặc cộng số lượng. Không nên để hành vi duplicate key được quyết định ngẫu nhiên bởi cấu trúc collection.

## 11. Xử lý lỗi khi đọc khóa Map

Key deserializer nhận chuỗi field name. Nếu chuỗi không đúng định dạng, quá trình deserialize có thể thất bại với lỗi ánh xạ khóa. Ví dụ JSON:

```json
{
  "U0tVL1JF RHwyMDI2.invalid": 15
}
```

Nếu key deserializer mong đợi phần cuối là số nguyên nhưng nhận `invalid`, nó nên ném lỗi có thông tin về kiểu khóa và giá trị không hợp lệ. Không nên trả về `null` hoặc một khóa mặc định vì điều đó có thể khiến dữ liệu sai được chấp nhận âm thầm.

Ở tầng ứng dụng, có thể bắt `JsonProcessingException` hoặc ngoại lệ Jackson phù hợp để chuyển thành lỗi request/import dễ hiểu. Log nên ghi đủ ngữ cảnh để truy nguyên, nhưng tránh ghi toàn bộ payload nếu payload chứa thông tin nhạy cảm.

## 12. Ghi nhớ

JSON object chỉ có tên field dạng string, vì vậy khóa `Map` không phải `String` cần được Jackson chuyển đổi thông qua key serializer và key deserializer. Jackson hỗ trợ nhiều kiểu khóa phổ biến; kiểu khóa nghiệp vụ cần codec riêng, đăng ký bằng `SimpleModule` hoặc khai báo trên property với `keyUsing`.

Để round-trip chính xác, phải cung cấp kiểu đích generic đầy đủ như `Map<ProductKey, Integer>`, thiết kế định dạng khóa duy nhất và ổn định, đồng thời kiểm tra chuỗi khóa không bị va chạm. Nếu khóa là object có cấu trúc phong phú, biểu diễn map thành danh sách entry thường là hợp đồng JSON dễ hiểu và dễ mở rộng hơn.
