# Quản lý null và phân biệt với serializer giá trị thông thường

Trong Jackson, serialize một giá trị Java thông thường và serialize một giá trị `null` là hai đường xử lý riêng. Khi property có giá trị, Jackson tìm serializer phù hợp với kiểu dữ liệu và gọi `JsonSerializer.serialize(...)`. Khi property là `null`, Jackson thường dùng null value serializer do `SerializerProvider` quản lý; serializer thông thường của kiểu đó không được gọi.

Sự khác biệt này quan trọng khi viết serializer tùy biến. Nếu chỉ override `serialize()` trong một `JsonSerializer<String>`, không có nghĩa method đó sẽ nhận được cả giá trị null. Muốn phát ra JSON null, bỏ hẳn property hoặc thay null bằng một biểu diễn khác, cần chọn đúng cơ chế.

## 1. JSON null và Java null

JSON có giá trị null:

~~~json
{
  "name": "An",
  "nickname": null
}
~~~

Trong Java, giá trị tương ứng thường được biểu diễn bằng `null` của kiểu tham chiếu:

~~~java
public class User {
    private String name;
    private String nickname;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Khi serialize một object có `nickname == null`, Jackson mặc định có thể ghi:

~~~json
{"name":"An","nickname":null}
~~~

Giá trị JSON `null` không phải chuỗi `"null"`:

| JSON | Kiểu JSON | Ý nghĩa |
|---|---|---|
| `null` | Null | Không có giá trị |
| `"null"` | String | Chuỗi gồm bốn ký tự |
| `""` | String | Chuỗi rỗng |
| `0` | Number | Số không |
| `false` | Boolean | Giá trị false |

Nếu hợp đồng API cần null thực sự, phải ghi token null bằng generator, không ghi chuỗi "null".

## 2. Jackson xử lý null khác serializer thông thường

Một custom serializer thường có dạng:

~~~java
public class UppercaseSerializer extends JsonSerializer<String> {
    @Override
    public void serialize(
            String value,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException {

        gen.writeString(value.toUpperCase(Locale.ROOT));
    }
}
~~~

Với property có giá trị như `"An"`, Jackson gọi serializer và ghi `"AN"`.

Nhưng khi property là null, Jackson thường không gọi `UppercaseSerializer.serialize(null, ...)`. Bean property writer kiểm tra null và chuyển sang null serializer riêng. Null serializer mặc định ghi JSON token `null`.

Luồng khái quát:

~~~text
Java property
     |
     v
Giá trị có null không?
     |
     +---- Có ----> Null value serializer
     |                    |
     |                    v
     |                JSON null
     |
     +---- Không --> Serializer của kiểu dữ liệu
                          |
                          v
                     serialize(value)
                          |
                          v
                    JSON value tương ứng
~~~

Do đó, kiểm tra `value == null` bên trong serializer thông thường không phải cách đáng tin cậy để quản lý null property. Muốn thay đổi đường xử lý null, phải cấu hình null serializer hoặc quyết định không phát property.

## 3. Hành vi mặc định: ghi JSON null

Nếu không có cấu hình inclusion hoặc null serializer riêng, Jackson thường giữ property null trong output và ghi token JSON null.

~~~java
ObjectMapper mapper = new ObjectMapper();

User user = new User();
user.setName("An");
user.setNickname(null);

String json = mapper.writeValueAsString(user);
~~~

Kết quả:

~~~json
{"name":"An","nickname":null}
~~~

Đây là hành vi phù hợp khi API muốn thể hiện rõ rằng property tồn tại nhưng hiện không có giá trị.

Với serializer tự viết, có thể chủ động ghi null cho một giá trị mà serializer đang xử lý bằng:

~~~java
gen.writeNull();
~~~

Tuy nhiên, câu lệnh này chỉ có tác dụng khi serializer thực sự được gọi. Đối với một bean property đã là null, Jackson đi qua null serializer riêng như đã giải thích ở trên.

## 4. Bỏ qua property null bằng @JsonInclude

Nhiều API muốn không phát ra field khi giá trị Java là null. Dùng `@JsonInclude(JsonInclude.Include.NON_NULL)`:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

public class User {
    private String name;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String nickname;

    // Getter/setter
}
~~~

Khi `nickname == null`, output chỉ còn:

~~~json
{"name":"An"}
~~~

Có thể áp dụng cho cả lớp:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class User {
    private String name;
    private String nickname;

    // Getter/setter
}
~~~

Hoặc cấu hình ở mapper:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
~~~

Cấu hình mapper áp dụng rộng đến các kiểu được serialize bằng mapper đó. Nếu chỉ một DTO hoặc property có chính sách khác, annotation ở phạm vi hẹp thường dễ hiểu hơn.

### 4.1. ALWAYS, NON_NULL và NON_EMPTY

Một số chế độ inclusion thường dùng:

| Chế độ | Ý nghĩa khái quát |
|---|---|
| `ALWAYS` | Luôn đưa property vào output, kể cả null |
| `NON_NULL` | Bỏ property có giá trị null |
| `NON_ABSENT` | Bỏ null và các giá trị absent như Optional.empty() |
| `NON_EMPTY` | Bỏ null và các giá trị được xem là rỗng như chuỗi rỗng, collection rỗng |
| `NON_DEFAULT` | Bỏ các giá trị bằng giá trị mặc định theo quy tắc Jackson |

Ví dụ:

~~~java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
private List<String> tags;
~~~

Nếu `tags` là null hoặc danh sách rỗng, property có thể bị loại khỏi output. Nếu danh sách có phần tử, Jackson serialize như bình thường.

Không nên dùng `NON_EMPTY` chỉ vì muốn bỏ null nếu chuỗi rỗng hoặc collection rỗng vẫn có ý nghĩa nghiệp vụ. Chọn inclusion theo hợp đồng JSON.

### 4.2. Null, empty và absent không giống nhau

| Trạng thái Java | Output khi dùng ALWAYS | Output khi dùng NON_NULL |
|---|---|---|
| `null` | `"nickname": null` | Bỏ property |
| `""` | `"nickname": ""` | `"nickname": ""` |
| `"An"` | `"nickname": "An"` | `"nickname": "An"` |

Với `NON_EMPTY`, chuỗi rỗng thường cũng bị bỏ. Với một property không được Jackson nhận diện hoặc bị `@JsonIgnore`, nó không tham gia serialization ngay từ đầu. Đó là trường hợp khác với property được nhận diện nhưng có giá trị null.

## 5. Viết null serializer tùy biến cho một property

Nếu hợp đồng yêu cầu null được biểu diễn bằng một giá trị khác, có thể gắn null serializer vào property writer thông qua `BeanSerializerModifier`.

Ví dụ property `nickname` là null thì ghi chuỗi `"(unknown)"`, còn property có giá trị thì dùng serializer thông thường.

Null serializer:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;

public class UnknownNullSerializer extends JsonSerializer<Object> {
    @Override
    public void serialize(
            Object value,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException {

        gen.writeString("(unknown)");
    }
}
~~~

Modifier gắn serializer vào đúng property:

~~~java
import com.fasterxml.jackson.databind.BeanDescription;
import com.fasterxml.jackson.databind.SerializationConfig;
import com.fasterxml.jackson.databind.ser.BeanPropertyWriter;
import com.fasterxml.jackson.databind.ser.BeanSerializerModifier;

import java.util.List;

public class UserNullSerializerModifier extends BeanSerializerModifier {
    @Override
    public List<BeanPropertyWriter> changeProperties(
            SerializationConfig config,
            BeanDescription beanDesc,
            List<BeanPropertyWriter> beanProperties) {

        if (beanDesc.getBeanClass() == User.class) {
            for (BeanPropertyWriter writer : beanProperties) {
                if ("nickname".equals(writer.getName())) {
                    writer.assignNullSerializer(
                        new UnknownNullSerializer()
                    );
                }
            }
        }

        return beanProperties;
    }
}
~~~

Đăng ký modifier qua module:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule module = new SimpleModule();
module.setSerializerModifier(new UserNullSerializerModifier());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
~~~

Khi `nickname == null`, output có dạng:

~~~json
{"name":"An","nickname":"(unknown)"}
~~~

Ở đây, null serializer được gọi bởi đường xử lý null của property writer. Nó không thay thế serializer cho các giá trị String thông thường.

Ví dụ này minh họa một quy tắc property-level. Trong ứng dụng lớn, nên giới hạn modifier theo bean class và tên property cụ thể để không vô tình thay đổi null handling của những DTO khác.

### 5.1. Vì sao null serializer nhận Object?

Null không có kiểu runtime cụ thể. Một null serializer thường khai báo kiểu tổng quát `JsonSerializer<Object>` để có thể được dùng cho property null theo cấu hình. Method serialize của nó được gọi với giá trị null trong vai trò null serializer.

Đừng viết logic phụ thuộc vào kiểu cụ thể của value trong null serializer; mục đích của nó là định nghĩa cách phát ra null.

### 5.2. Không thay null bằng chuỗi nếu schema yêu cầu null

Ví dụ trên biến null thành JSON string:

~~~json
{"nickname":"(unknown)"}
~~~

Đây không còn là JSON null. Consumer nhận được một String và có thể xử lý khác.

Nếu hợp đồng yêu cầu token null, null serializer nên ghi:

~~~java
gen.writeNull();
~~~

Nếu hợp đồng yêu cầu bỏ hẳn property, dùng `@JsonInclude(NON_NULL)`. Nếu hợp đồng yêu cầu placeholder, ghi rõ kiểu và giá trị placeholder trong schema API.

## 6. Null serializer toàn cục và phạm vi cấu hình

Có trường hợp ứng dụng muốn mọi null value trong một mapper đều được serialize theo cùng chính sách. Jackson cho phép tùy biến null value serializer ở cấp `SerializerProvider` hoặc thông qua cơ chế cấu hình serializer/module phù hợp với phiên bản.

Tuy nhiên, cấu hình toàn cục có phạm vi rất rộng:

- Có thể tác động đến null của nhiều DTO không liên quan.
- Có thể thay đổi kiểu JSON mà consumer mong đợi.
- Có thể khiến một field số hoặc boolean phát ra placeholder string không đúng schema.
- Có thể ảnh hưởng dữ liệu null trong container.

Vì vậy, ưu tiên cấu hình null serializer ở property hoặc DTO cần nó. Chỉ dùng chính sách toàn cục khi toàn bộ hợp đồng output của mapper thống nhất cùng một biểu diễn null.

Dù cấu hình toàn cục hay cục bộ, serializer null vẫn là một thành phần riêng với serializer giá trị thông thường.

## 7. Null trong collection và Map

Cần phân biệt null của chính property container với null của phần tử bên trong.

Ví dụ:

~~~java
public class Batch {
    private List<String> names;
    private Map<String, String> labels;

    // Getter/setter
}
~~~

Object có thể chứa:

~~~java
Batch batch = new Batch();
batch.setNames(Arrays.asList("An", null, "Bình"));

Map<String, String> labels = new LinkedHashMap<>();
labels.put("primary", "blue");
labels.put("secondary", null);
batch.setLabels(labels);
~~~

Output mặc định có thể giữ null ở vị trí phần tử hoặc value:

~~~json
{
  "names": ["An", null, "Bình"],
  "labels": {
    "primary": "blue",
    "secondary": null
  }
}
~~~

Nếu chỉ đặt `@JsonInclude(NON_NULL)` trên property `names`, điều đó điều khiển việc phát ra cả property khi chính danh sách là null. Nó không nhất thiết loại từng phần tử null bên trong danh sách.

Muốn điều khiển nội dung container, `JsonInclude` có thuộc tính `content`:

~~~java
@JsonInclude(
    value = JsonInclude.Include.ALWAYS,
    content = JsonInclude.Include.NON_NULL
)
private Map<String, String> labels;
~~~

Cấu hình content inclusion áp dụng cho giá trị bên trong container theo loại hỗ trợ. Hãy kiểm thử riêng với List, Map và kiểu container mà ứng dụng dùng; chính sách cho property null và chính sách cho phần tử null là hai phạm vi khác nhau.

### 7.1. Null Map value khác null Map key

JSON object yêu cầu tên property là string. Một Map có key null không thể được biểu diễn như một key JSON null thông thường.

Ví dụ:

~~~java
Map<String, String> values = new HashMap<>();
values.put(null, "value");
~~~

Jackson mặc định thường từ chối serialize null map key vì không có tên field JSON hợp lệ. Cơ chế xử lý null key là null key serializer, khác với null value serializer.

Phân biệt:

- Null Map value: có thể ghi JSON `null` ở value.
- Null Map key: cần một field name; mặc định thường báo lỗi nếu key null.
- Null của cả Map property: được xử lý theo null serializer hoặc inclusion của property.

Không dùng null value serializer để sửa lỗi null map key.

## 8. Null trong serialization khác null trong deserialization

Null serializer chỉ điều khiển chiều Java object thành JSON. Khi đọc JSON vào Java, Jackson có các quy tắc riêng để xử lý property có token null.

Ví dụ `@JsonSetter` và `Nulls`:

~~~java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

public class Preferences {
    private String theme = "light";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setTheme(String theme) {
        this.theme = theme;
    }

    public String getTheme() {
        return theme;
    }
}
~~~

Với payload:

~~~json
{"theme": null}
~~~

`Nulls.SKIP` yêu cầu bỏ qua việc gán khi input value là null; giá trị mặc định `"light"` được giữ lại.

Một số lựa chọn của `Nulls`:

| Cấu hình | Ý nghĩa ở chiều đọc |
|---|---|
| `SET` | Gán null vào property theo quy tắc mặc định |
| `SKIP` | Không gọi thao tác gán khi input là null |
| `FAIL` | Từ chối null |
| `AS_EMPTY` | Dùng empty value do deserializer cung cấp |
| `DEFAULT` | Dùng chính sách mặc định của Jackson/property |

Đây là deserialization policy. Nó không quyết định cách serializer phát ra null ở chiều output.

### 8.1. Field bị thiếu khác field có null

Xét hai payload:

~~~json
{}
~~~

~~~json
{"theme": null}
~~~

Payload đầu không có property theme; setter có thể không được gọi và giá trị mặc định của object được giữ nguyên.

Payload thứ hai có property theme với token null; Jackson áp dụng chính sách null của property, chẳng hạn SET, SKIP hoặc FAIL.

Khi serialize, Jackson chỉ nhìn thấy trạng thái Java hiện tại. Nếu theme là null, nó áp dụng null serializer hoặc inclusion. Nó không thể tự biết object đã được tạo từ payload thiếu key hay payload có key null, trừ khi ứng dụng lưu riêng thông tin presence đó.

Nếu nghiệp vụ cần phân biệt "không gửi" với "gửi null", cần một mô hình dữ liệu có trạng thái presence rõ ràng, ví dụ wrapper/patch DTO hoặc kiểu Optional có quy ước cụ thể.

## 9. Primitive và wrapper type

Java primitive không thể chứa null:

~~~java
private boolean active;
private int retryCount;
~~~

Nếu field không được gán, giá trị mặc định lần lượt là false và 0. Wrapper có thể chứa null:

~~~java
private Boolean active;
private Integer retryCount;
~~~

Khi serialize:

- Primitive thường luôn có một giá trị cụ thể, ví dụ false hoặc 0.
- Wrapper có thể là null và đi qua null serializer.
- Nếu dùng NON_NULL, wrapper null có thể bị bỏ khỏi output.

Điều này có ảnh hưởng đến hợp đồng API. Nếu cần phân biệt "chưa cung cấp" với false hoặc 0, wrapper thường biểu đạt được trạng thái null tốt hơn primitive. Tuy nhiên, chỉ dùng wrapper chưa đủ nếu cần phân biệt key thiếu với key có null.

## 10. Custom serializer thông thường không phải null serializer

Giả sử muốn định dạng tiền tệ:

~~~java
public class MoneySerializer extends JsonSerializer<BigDecimal> {
    @Override
    public void serialize(
            BigDecimal value,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException {

        gen.writeString(value.setScale(2, RoundingMode.HALF_UP).toPlainString());
    }
}
~~~

Gắn vào property:

~~~java
@JsonSerialize(using = MoneySerializer.class)
private BigDecimal amount;
~~~

Khi amount có giá trị, MoneySerializer định dạng nó thành JSON string. Khi amount là null, Jackson dùng null serializer riêng hoặc bỏ property theo inclusion. `MoneySerializer.serialize()` không tự động nhận null chỉ vì nó được gắn vào property.

Nếu muốn null của amount được xử lý đặc biệt, cấu hình null serializer riêng qua BeanSerializerModifier như phần 5, hoặc chọn một inclusion policy phù hợp.

### 10.1. isEmpty() không thay thế null serializer

Custom serializer có thể override `isEmpty(...)` để định nghĩa một giá trị không null có được xem là rỗng khi áp dụng `NON_EMPTY` hay không.

Ví dụ một chuỗi chỉ có khoảng trắng có thể được xem là empty theo quy tắc riêng. Nhưng `isEmpty()` không phải API để quyết định cách ghi token null; nó phục vụ inclusion của giá trị và tách biệt với null serialization.

## 11. Kiểm thử null serialization

Nên kiểm tra ba trường hợp riêng: ghi null mặc định, bỏ null và dùng null serializer tùy biến.

Ví dụ kiểm tra output bằng JsonNode thay vì so sánh thứ tự field trong chuỗi:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class NullSerializationTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void writesNullByDefault() throws Exception {
        User user = new User();
        user.setName("An");

        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(user)
        );

        assertTrue(json.has("nickname"));
        assertTrue(json.get("nickname").isNull());
    }

    @Test
    void omitsNullWhenNonNullInclusionIsConfigured() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);

        User user = new User();
        user.setName("An");

        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(user)
        );

        assertFalse(json.has("nickname"));
    }
}
~~~

Nếu kiểm thử null serializer tùy biến, hãy xác nhận output là đúng kiểu JSON mong muốn: token null, string placeholder hay property bị bỏ. Ba kết quả đó không tương đương nhau.

Nên bổ sung test cho:

- Property null ở cấp bean.
- Phần tử null trong List.
- Value null trong Map.
- Map key null.
- Property null với inclusion NON_NULL/NON_EMPTY.
- Custom serializer cho giá trị có thật.
- Custom null serializer cho property.
- Input null và input thiếu property ở chiều deserialize.

## 12. Lựa chọn chính sách null theo hợp đồng API

| Mục tiêu | Cơ chế phù hợp |
|---|---|
| Giữ property và ghi JSON null | Hành vi null serializer mặc định |
| Không phát ra property null | `@JsonInclude(NON_NULL)` |
| Bỏ cả chuỗi rỗng/collection rỗng | `@JsonInclude(NON_EMPTY)` nếu phù hợp nghiệp vụ |
| Ghi placeholder thay null ở một property | Null serializer riêng qua `BeanSerializerModifier` |
| Ghi placeholder cho mọi null | Chính sách null serializer toàn mapper, chỉ khi hợp đồng thống nhất |
| Bỏ qua input null khi deserialize | `@JsonSetter(nulls = Nulls.SKIP)` |
| Từ chối input null | `@JsonSetter(nulls = Nulls.FAIL)` hoặc cấu hình tương ứng |
| Giữ giá trị mặc định khi input null | `Nulls.SKIP` trên property phù hợp |

Không nên biến null thành chuỗi "N/A" trên toàn mapper nếu có property số, boolean hoặc object. Việc đó thay đổi kiểu JSON và có thể phá vỡ consumer.

## 13. Các lỗi thường gặp

**Chỉ override serialize() rồi mong xử lý null.** Jackson thường đi qua null serializer riêng, nên method của serializer giá trị thông thường không được gọi cho property null.

**Nhầm null với chuỗi "null".** JSON null và JSON string có nội dung "null" là hai kiểu khác nhau.

**Dùng NON_EMPTY thay NON_NULL mà không cân nhắc chuỗi rỗng.** NON_EMPTY có thể bỏ cả giá trị rỗng mà nghiệp vụ vẫn cần giữ.

**Dùng @JsonSetter để điều khiển output.** JsonSetter và Nulls điều khiển chiều deserialize; output dùng null serializer và JsonInclude.

**Cho rằng NON_NULL loại null bên trong List.** Inclusion của property container và inclusion của content là hai phạm vi khác nhau.

**Dùng null value serializer cho null Map key.** Key cần được chuyển thành field name; null key serializer là cơ chế riêng.

**Ghi placeholder sai kiểu.** Property số mà null serializer ghi string có thể làm consumer parse thất bại. Hãy thống nhất schema trước.

**Cấu hình global quá rộng.** Null serializer toàn mapper có thể thay đổi nhiều DTO không liên quan; giới hạn ở property cần thiết khi có thể.

## 14. Ghi nhớ

- Jackson xử lý property null qua null value serializer riêng; serializer thông thường của kiểu dữ liệu không tự động nhận null.
- Null serializer mặc định ghi JSON token null.
- Dùng `@JsonInclude(NON_NULL)` để bỏ property null; dùng `NON_EMPTY` khi muốn bỏ thêm các giá trị rỗng.
- Muốn thay null bằng placeholder ở một property, gắn null serializer vào BeanPropertyWriter qua BeanSerializerModifier.
- `gen.writeNull()` ghi JSON null; `gen.writeString("null")` ghi một chuỗi.
- Null của property, null của collection element, null Map value và null Map key là các trường hợp khác nhau.
- `@JsonSetter(nulls = ...)` điều khiển chiều đọc; nó không điều khiển cách serialize.
- Phân biệt field bị thiếu, field có null, empty value và giá trị mặc định của primitive.
- Kiểm thử cả kiểu token và sự hiện diện của property, không chỉ so sánh chuỗi JSON.

