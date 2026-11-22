# Tùy biến cách đọc khóa Map

Trong JSON, object được biểu diễn bằng các cặp tên thuộc tính và giá trị. Tên thuộc tính luôn là chuỗi, kể cả khi ứng dụng Java muốn dùng một kiểu khác làm khóa Map như `LocalDate`, `UUID`, enum hoặc một kiểu định danh tự tạo.

Jackson có cơ chế riêng để chuyển tên field JSON thành khóa Java: `KeyDeserializer`. Cơ chế này khác với deserializer dùng để đọc value của Map. Khi cần hỗ trợ round-trip, tức đọc và ghi cùng một định dạng khóa, cần cấu hình thêm key serializer ở chiều xuất JSON.

Bài học này trình bày cách viết `KeyDeserializer`, gắn nó vào một Map bằng annotation hoặc module, xử lý khóa sai định dạng và phối hợp với key serializer.

## 1. Vì sao Map key cần deserializer riêng?

Giả sử Java có Map dùng ngày làm khóa:

```java
Map<LocalDate, BigDecimal> balances;
```

Một JSON object không thể dùng trực tiếp một JSON number hoặc JSON object làm tên field. Các key của nó luôn là string:

```json
{
  "12-11-2026": 1250.00,
  "13-11-2026": 980.50
}
```

Ứng dụng muốn chuyển các chuỗi `"12-11-2026"` và `"13-11-2026"` thành `LocalDate` để sử dụng làm khóa Map.

Jackson xử lý hai phần độc lập:

- **Key:** tên field JSON được chuyển thành kiểu khóa Java bằng key deserializer.
- **Value:** giá trị JSON được chuyển thành kiểu value Java bằng value deserializer thông thường.

Sơ đồ:

```text
JSON object
{
  "12-11-2026": 1250.00
}
       |
       +---- field name "12-11-2026"
       |             |
       |             v
       |       KeyDeserializer
       |             |
       |             v
       |       LocalDate(2026-11-12)
       |
       +---- field value 1250.00
                     |
                     v
              BigDecimal deserializer
                     |
                     v
                 BigDecimal
       |
       v
Map<LocalDate, BigDecimal>
```

Nếu không có custom key deserializer, Jackson dùng key deserializer mặc định tương ứng với kiểu khóa. Với `LocalDate`, module Java Time thường hỗ trợ định dạng ISO mặc định như `2026-11-12`; định dạng khác như `12-11-2026` cần quy tắc tùy biến.

## 2. KeyDeserializer là gì?

Trong Jackson Databind 2.x, `KeyDeserializer` nằm trong package:

```java
com.fasterxml.jackson.databind.KeyDeserializer
```

Đây là abstract class có method chính:

```java
public abstract Object deserializeKey(
    String key,
    DeserializationContext ctxt
) throws IOException;
```

Jackson gọi method này với tên field JSON dưới dạng String. Method trả về object sẽ được dùng làm key trong Map.

Một key deserializer cần:

1. Nhận chuỗi tên field.
2. Kiểm tra định dạng.
3. Chuyển chuỗi thành kiểu key Java.
4. Báo lỗi mapping rõ ràng nếu chuỗi không hợp lệ.

Ví dụ tổng quát:

```java
public class CustomKeyDeserializer extends KeyDeserializer {
    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext ctxt) throws IOException {

        // Parse key thành kiểu Java cần dùng.
        return parseKey(key);
    }
}
```

Khác với `JsonDeserializer<T>`, method này không nhận `JsonParser` làm tham số. Jackson đã đọc tên field JSON và truyền chuỗi key vào `deserializeKey()`. Vì vậy, không gọi `nextToken()` trong key deserializer để đọc value kế tiếp.

## 3. Ví dụ: đọc khóa LocalDate theo định dạng dd-MM-yyyy

Giả sử API dùng ngày theo định dạng `dd-MM-yyyy`, trong khi Java sử dụng `LocalDate`.

JSON đầu vào:

```json
{
  "12-11-2026": 1250.00,
  "13-11-2026": 980.50
}
```

Kiểu đích:

```java
Map<LocalDate, BigDecimal> balances;
```

Viết key deserializer:

```java
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.KeyDeserializer;

import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public final class LocalDateKeyDeserializer extends KeyDeserializer {
    private static final DateTimeFormatter FORMATTER =
        DateTimeFormatter.ofPattern("dd-MM-uuuu", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext ctxt) throws IOException {

        try {
            return LocalDate.parse(key, FORMATTER);
        } catch (DateTimeParseException ex) {
            throw ctxt.weirdKey(
                LocalDate.class,
                key,
                "Expected date in dd-MM-yyyy format"
            );
        }
    }
}
```

Một số điểm đáng chú ý:

- Formatter được tạo một lần dưới dạng `static final`; `DateTimeFormatter` là immutable và thread-safe.
- Dùng `uuuu` để parse proleptic year với strict resolver. Với pattern strict, `yyyy` là year-of-era và có thể cần era; `uuuu` phù hợp hơn cho ví dụ này.
- `ResolverStyle.STRICT` từ chối ngày không tồn tại như 31-02-2026.
- `ctxt.weirdKey(...)` tạo lỗi mapping gắn với kiểu khóa và giá trị đầu vào.

Nếu muốn thông báo lỗi bằng tiếng Việt, có thể thay nội dung message. Không nên trả về null hoặc một ngày mặc định khi key sai định dạng, vì điều đó có thể làm nhiều entry bị nhập nhằng.

## 4. Gắn key deserializer bằng @JsonDeserialize

Nếu chỉ một property Map cần định dạng khóa riêng, dùng `@JsonDeserialize(keyUsing = ...)`:

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Map;

public class DailyBalances {
    @JsonDeserialize(keyUsing = LocalDateKeyDeserializer.class)
    private Map<LocalDate, BigDecimal> balances;

    public Map<LocalDate, BigDecimal> getBalances() {
        return balances;
    }

    public void setBalances(Map<LocalDate, BigDecimal> balances) {
        this.balances = balances;
    }
}
```

Đọc JSON:

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule());

DailyBalances result = mapper.readValue(
    """
    {
      "balances": {
        "12-11-2026": 1250.00,
        "13-11-2026": 980.50
      }
    }
    """,
    DailyBalances.class
);

LocalDate date = LocalDate.of(2026, 11, 12);
BigDecimal amount = result.getBalances().get(date);
```

Kết quả:

```text
date   = 2026-11-12
amount = 1250.00
```

Annotation `keyUsing` chỉ áp dụng cho key của Map property đó. Nó không thay đổi cách deserialize value `BigDecimal`, cũng không ảnh hưởng đến các Map khác trong ứng dụng.

Nếu property có kiểu generic phức tạp, Jackson vẫn dùng generic type để xác định kiểu value và kiểu key; `keyUsing` chỉ thay thế cơ chế đọc key.

## 5. Đăng ký key deserializer bằng SimpleModule

Khi nhiều Map trong ứng dụng cùng dùng một kiểu key và một quy tắc định dạng, có thể đăng ký deserializer theo kiểu khóa trong module:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;

import java.time.LocalDate;

SimpleModule module = new SimpleModule();
module.addKeyDeserializer(
    LocalDate.class,
    new LocalDateKeyDeserializer()
);

ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule())
    .registerModule(module);
```

Sau khi đăng ký, các Map có key kiểu `LocalDate` có thể dùng key deserializer đã đăng ký.

Khác biệt giữa hai cách:

| Cách | Phạm vi | Khi phù hợp |
|---|---|---|
| `@JsonDeserialize(keyUsing = ...)` | Một property Map | Chỉ một field có định dạng đặc biệt |
| `SimpleModule.addKeyDeserializer(...)` | Các Map có kiểu key tương ứng dùng mapper/module | Quy tắc dùng chung trong ứng dụng |

Nếu một kiểu key có nhiều định dạng theo từng API, annotation tại property giúp giới hạn ảnh hưởng. Nếu đăng ký global cho `LocalDate`, hãy cân nhắc các nơi khác đang kỳ vọng ISO mặc định. Với module Java Time và module tùy biến cùng đăng ký key handler cho một kiểu, thứ tự/ưu tiên module có thể ảnh hưởng kết quả; hãy xác nhận bằng test trên mapper thực tế.

## 6. Key deserializer và value deserializer không giống nhau

Annotation `@JsonDeserialize` có nhiều thuộc tính cho các vị trí khác nhau:

| Thuộc tính | Áp dụng cho | Ví dụ |
|---|---|---|
| `using` | Toàn bộ property | Custom deserializer cho cả Map |
| `keyUsing` | Key của Map | Chuỗi field name thành LocalDate |
| `contentUsing` | Value/phần tử bên trong container | JSON value thành kiểu tùy biến |

Ví dụ Map có key là LocalDate và value là một kiểu Money tùy chỉnh:

```java
@JsonDeserialize(
    keyUsing = LocalDateKeyDeserializer.class,
    contentUsing = MoneyDeserializer.class
)
private Map<LocalDate, Money> balances;
```

Trong trường hợp này:

- `LocalDateKeyDeserializer` đọc tên field như `12-11-2026`.
- `MoneyDeserializer` đọc JSON value tương ứng.
- Jackson kết hợp hai kết quả để tạo entry trong Map.

Nếu gắn custom deserializer vào `contentUsing` mà mục tiêu là chuyển tên field, Jackson sẽ không gọi nó cho key. Ngược lại, `keyUsing` không xử lý object/number nằm ở phía value.

## 7. Khóa Map là kiểu định danh, không phải JSON value tùy ý

JSON object chỉ có field name dạng string. Do đó, custom key deserializer luôn nhận chuỗi, kể cả khi kiểu Java cuối cùng là:

- `UUID`
- `LocalDate`
- `YearMonth`
- Enum
- Một value object như `AccountKey`
- Một mã nghiệp vụ hoặc composite key

Ví dụ Map dùng UUID:

```json
{
  "550e8400-e29b-41d4-a716-446655440000": {
    "status": "ACTIVE"
  }
}
```

Có thể chuyển key bằng:

```java
UUID id = UUID.fromString(key);
```

Jackson đã có hỗ trợ key deserializer cho nhiều kiểu phổ biến. Chỉ cần custom khi định dạng đầu vào khác quy ước mặc định, có alias, cần chuẩn hóa hoặc cần validation đặc thù.

Với custom key type, nên thiết kế class bất biến và triển khai `equals()`/`hashCode()` ổn định. Map dựa vào hai method này để nhận diện key; nếu key thay đổi sau khi được đưa vào Map, việc tìm entry có thể không còn hoạt động đúng.

## 8. Ví dụ: khóa composite AccountKey

Một khóa Map có thể gồm nhiều thành phần, chẳng hạn tenant và account:

```text
tenant-a:account-17
```

Định nghĩa value object:

```java
public record AccountKey(String tenant, String account) {
    public AccountKey {
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalArgumentException("tenant is required");
        }
        if (account == null || account.isBlank()) {
            throw new IllegalArgumentException("account is required");
        }
    }

    public static AccountKey parse(String raw) {
        int separator = raw.indexOf(':');

        if (separator <= 0 || separator == raw.length() - 1) {
            throw new IllegalArgumentException(
                "Expected tenant:account"
            );
        }

        if (raw.indexOf(':', separator + 1) >= 0) {
            throw new IllegalArgumentException(
                "Key must contain exactly one separator"
            );
        }

        return new AccountKey(
            raw.substring(0, separator),
            raw.substring(separator + 1)
        );
    }

    public String toWireKey() {
        return tenant + ":" + account;
    }
}
```

Key deserializer:

```java
public final class AccountKeyDeserializer extends KeyDeserializer {
    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext ctxt) throws IOException {

        try {
            return AccountKey.parse(key);
        } catch (IllegalArgumentException ex) {
            throw ctxt.weirdKey(
                AccountKey.class,
                key,
                ex.getMessage()
            );
        }
    }
}
```

DTO:

```java
public class AccountBalances {
    @JsonDeserialize(keyUsing = AccountKeyDeserializer.class)
    private Map<AccountKey, BigDecimal> balances;

    public Map<AccountKey, BigDecimal> getBalances() {
        return balances;
    }

    public void setBalances(Map<AccountKey, BigDecimal> balances) {
        this.balances = balances;
    }
}
```

JSON:

```json
{
  "balances": {
    "tenant-a:account-17": 250.00,
    "tenant-b:account-22": 900.00
  }
}
```

Sau khi deserialize, key có cấu trúc riêng trong Java:

```java
AccountKey key = new AccountKey("tenant-a", "account-17");
BigDecimal balance = result.getBalances().get(key);
```

Record tự sinh `equals()` và `hashCode()` dựa trên các component, nên hai AccountKey có cùng tenant/account có thể tra cứu cùng entry trong Map.

## 9. Cấu hình key serializer để round-trip

Key deserializer chỉ điều khiển chiều đọc JSON vào Java. Khi serialize Map, Jackson cần chuyển Java key trở lại tên field JSON.

Nếu chỉ custom deserializer, key serializer mặc định có thể phát ra định dạng khác với đầu vào. Ví dụ đọc `12-11-2026` thành LocalDate rồi ghi lại, key mặc định có thể thành `2026-11-12`.

Để giữ cùng wire format, viết key serializer:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class LocalDateKeySerializer extends JsonSerializer<LocalDate> {
    private static final DateTimeFormatter FORMATTER =
        DateTimeFormatter.ofPattern("dd-MM-uuuu", Locale.ROOT);

    @Override
    public void serialize(
            LocalDate value,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException {

        gen.writeFieldName(FORMATTER.format(value));
    }
}
```

Điểm quan trọng: key serializer phải ghi **field name** bằng `gen.writeFieldName(...)`. Không dùng `gen.writeString(...)`, vì Map key nằm ở vị trí tên thuộc tính của JSON object chứ không phải một JSON value độc lập.

Gắn cả hai chiều:

```java
@JsonDeserialize(keyUsing = LocalDateKeyDeserializer.class)
@JsonSerialize(keyUsing = LocalDateKeySerializer.class)
private Map<LocalDate, BigDecimal> balances;
```

Hoặc đăng ký cả hai trong module:

```java
SimpleModule module = new SimpleModule();

module.addKeyDeserializer(
    LocalDate.class,
    new LocalDateKeyDeserializer()
);

module.addKeySerializer(
    LocalDate.class,
    new LocalDateKeySerializer()
);
```

Sau đó, round-trip có thể giữ định dạng:

```json
{
  "balances": {
    "12-11-2026": 1250.00
  }
}
```

Key serializer và key deserializer là hai thành phần độc lập. Nếu API chỉ cần đọc dữ liệu legacy nhưng luôn muốn phát ra định dạng chuẩn mới, có thể custom deserializer mà giữ serializer mặc định. Hãy quyết định theo hợp đồng output.

## 10. Lỗi định dạng và thông báo mapping

Key không hợp lệ nên bị từ chối với thông báo có ngữ cảnh. Ví dụ:

```json
{
  "balances": {
    "31-02-2026": 1250.00
  }
}
```

Ngày này không tồn tại. Deserializer nên ném lỗi mapping thay vì tự điều chỉnh thành một ngày khác.

Mẫu xử lý:

```java
try {
    return LocalDate.parse(key, FORMATTER);
} catch (DateTimeParseException ex) {
    throw ctxt.weirdKey(
        LocalDate.class,
        key,
        "Expected a real calendar date in dd-MM-yyyy format"
    );
}
```

Jackson có thể bọc lỗi trong exception thuộc nhóm `JsonMappingException` và bổ sung path tới property Map. Ở tầng API, nên chuyển lỗi thành phản hồi validation phù hợp; không trả stack trace hoặc thông tin nội bộ cho client.

Không nên:

- Trả null cho key sai định dạng.
- Dùng ngày mặc định thay cho key không hợp lệ.
- Bỏ qua entry lỗi nhưng vẫn báo request thành công nếu hợp đồng yêu cầu toàn bộ Map hợp lệ.
- Catch mọi exception rồi ném một lỗi chung làm mất ngữ cảnh.

## 11. Chuẩn hóa key và nguy cơ trùng khóa

Hai chuỗi key khác nhau có thể trở thành cùng một Java key sau khi parse hoặc chuẩn hóa.

Ví dụ, nếu deserializer chấp nhận cả chữ hoa và chữ thường cho một mã không phân biệt hoa thường:

```json
{
  "acct-a": 100,
  "ACCT-A": 200
}
```

Cả hai có thể được chuẩn hóa thành cùng một key `AccountKey("acct-a")`. Map chỉ có một entry cho key đó; giá trị ghi sau có thể thay thế giá trị trước.

Tương tự, nếu date deserializer chấp nhận nhiều định dạng, hai tên field khác nhau có thể cùng biểu diễn một ngày.

Cần quyết định chính sách:

- Chỉ chấp nhận một dạng canonical duy nhất.
- Từ chối key không canonical.
- Phát hiện collision sau khi parse và báo lỗi nếu hai key cùng ánh xạ đến một Java key.

Duplicate field detection của parser có thể phát hiện tên JSON trùng nguyên văn, nhưng không tự phát hiện hai chuỗi khác nhau được custom deserializer chuẩn hóa thành cùng một key Java. Nếu collision phải bị từ chối, có thể cần custom Map deserializer hoặc một bước kiểm tra riêng trước khi ghi entry vào Map.

## 12. Key deserializer không xử lý null Map key

Trong JSON object, field name luôn là string. JSON không có một tên field kiểu null. Do đó, `KeyDeserializer.deserializeKey(...)` không phải cơ chế để đọc một JSON null thành Map key.

Cần phân biệt:

- JSON value của một entry có thể là `null`.
- Tên field/key của object vẫn là string.
- Java Map có thể cho phép null key tùy implementation, nhưng JSON object không có cách biểu diễn null key trực tiếp theo cú pháp thông thường.

Ở chiều serialize, null Map key đi qua null key serializer riêng. Đây là cơ chế khác với key serializer thông thường được gắn bằng `@JsonSerialize(keyUsing = ...)`.

Nếu nghiệp vụ thật sự cần key có trạng thái null, hãy thay đổi schema, ví dụ biểu diễn Map thành array các object có trường `key` và `value`, hoặc dùng một cấu trúc dữ liệu khác có thể mô tả trạng thái đó rõ ràng.

## 13. Kiểm thử key deserializer

Nên kiểm tra cả key hợp lệ, key sai định dạng và round-trip nếu ứng dụng cần ghi lại cùng wire format.

Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Map;

class LocalDateMapKeyTest {
    private final ObjectMapper mapper = createMapper();

    private static ObjectMapper createMapper() {
        SimpleModule keyModule = new SimpleModule();
        keyModule.addKeyDeserializer(
            LocalDate.class,
            new LocalDateKeyDeserializer()
        );

        return JsonMapper.builder()
            .addModule(keyModule)
            .build();
    }

    @Test
    void readsCustomDateKeys() throws Exception {
        Map<LocalDate, BigDecimal> balances = mapper.readValue(
            """
            {
              "12-11-2026": 1250.00
            }
            """,
            mapper.getTypeFactory().constructMapType(
                Map.class,
                LocalDate.class,
                BigDecimal.class
            )
        );

        assertEquals(
            new BigDecimal("1250.00"),
            balances.get(LocalDate.of(2026, 11, 12))
        );
    }

    @Test
    void rejectsInvalidDateKey() {
        assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(
                """
                {"31-02-2026": 1250.00}
                """,
                mapper.getTypeFactory().constructMapType(
                    Map.class,
                    LocalDate.class,
                    BigDecimal.class
                )
            )
        );
    }
}
```

Test dùng cùng custom key deserializer đã đăng ký cho `LocalDate`. Nếu cần kiểm tra chính xác message, hãy đối chiếu với phiên bản Jackson của dự án; nội dung message có thể thay đổi giữa các phiên bản.

## 14. Khi nào nên dùng custom key deserializer?

| Tình huống | Cách xử lý |
|---|---|
| Key là String thông thường | Dùng key deserializer mặc định |
| Key là UUID hoặc enum theo định dạng chuẩn | Kiểm tra hỗ trợ mặc định của Jackson trước |
| Key LocalDate dùng format khác ISO | Custom `KeyDeserializer` |
| Key là value object hoặc composite identifier | Custom `KeyDeserializer` |
| Một property có format riêng | `@JsonDeserialize(keyUsing = ...)` |
| Nhiều Map dùng chung quy tắc key | Đăng ký qua `SimpleModule.addKeyDeserializer` |
| Cần phát ra cùng định dạng key khi serialize | Thêm key serializer tương ứng |
| Cần xử lý key sai hoặc collision theo nghiệp vụ | Custom Map deserializer hoặc validation bổ sung |

Không cần viết custom deserializer chỉ để chuyển một String key thành String. Dùng cơ chế mặc định nếu Jackson đã hỗ trợ đúng kiểu và format. Custom code nên được dành cho định dạng hoặc quy tắc thực sự đặc thù.

## 15. Ghi nhớ

- Tên field JSON luôn là string; Jackson dùng `KeyDeserializer` để chuyển nó thành kiểu key Java.
- `deserializeKey(String key, DeserializationContext ctxt)` nhận chuỗi tên field đã được parser giải mã.
- Dùng `@JsonDeserialize(keyUsing = ...)` để cấu hình một property Map hoặc `SimpleModule.addKeyDeserializer` cho kiểu key dùng chung.
- `keyUsing` xử lý Map key; `contentUsing` xử lý Map value/phần tử container; `using` có thể thay deserializer của toàn property.
- Key deserializer không đọc value token và không gọi `nextToken()`.
- Key serializer ở chiều ghi là thành phần riêng; dùng `gen.writeFieldName(...)` để ghi tên key.
- Custom key deserializer không tự bảo đảm round-trip giữ cùng định dạng; cần key serializer nếu hợp đồng output yêu cầu.
- Kiểm tra định dạng và từ chối key không hợp lệ; không thay bằng null hoặc giá trị mặc định.
- Chú ý hai chuỗi key khác nhau có thể chuẩn hóa thành cùng một Java key và gây ghi đè trong Map.
- Null Map key, null Map value và key serializer thông thường là ba tình huống khác nhau.

