# Ảnh hưởng của `null` khi ánh xạ vào kiểu nguyên thủy và kiểu bao

## 1. Vì sao cùng một JSON `null` lại cho kết quả khác nhau?

Java có hai nhóm kiểu dữ liệu thường dùng để biểu diễn số, boolean và ký tự:

- **Kiểu nguyên thủy (primitive):** `int`, `long`, `double`, `boolean`, `char` và các kiểu primitive còn lại. Một biến primitive luôn có một giá trị thuộc miền giá trị của kiểu đó; nó không thể chứa tham chiếu Java `null`.
- **Kiểu bao (wrapper):** `Integer`, `Long`, `Double`, `Boolean`, `Character` và các lớp bao tương ứng. Đây là kiểu tham chiếu, vì vậy biến có thể chứa một đối tượng hoặc tham chiếu Java `null`.

Khi Jackson giải tuần tự hóa JSON, sự khác biệt này ảnh hưởng trực tiếp đến cách xử lý giá trị `null`. Với wrapper, JSON `null` có thể được ánh xạ thành Java null. Với primitive, Jackson không thể gán Java null, nên mặc định thường chuyển giá trị JSON null thành giá trị mặc định của primitive. Nếu muốn từ chối trường hợp đó, có thể bật `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES`.

Ngoài giá trị `null` tường minh, còn phải phân biệt thuộc tính **không xuất hiện** trong JSON. Khi thuộc tính bị thiếu, Jackson không có giá trị để gán cho property đó. Kết quả cuối cùng còn phụ thuộc cách đối tượng được tạo, giá trị khởi tạo của field, setter, constructor và cấu hình creator-property.

## 2. Giá trị mặc định của primitive và wrapper trong Java

Các field của một đối tượng Java được khởi tạo giá trị mặc định nếu không có initializer riêng:

| Kiểu | Giá trị mặc định của field |
|---|---|
| `byte`, `short`, `int`, `long` | `0` |
| `float`, `double` | `0.0` |
| `char` | Ký tự null `\u0000` |
| `boolean` | `false` |
| `Byte`, `Short`, `Integer`, `Long` | `null` |
| `Float`, `Double` | `null` |
| `Character` | `null` |
| `Boolean` | `null` |

Ví dụ:

```java
public class Defaults {
    int primitiveCount;
    Integer wrapperCount;
    boolean primitiveEnabled;
    Boolean wrapperEnabled;
}
```

Một đối tượng `new Defaults()` có `primitiveCount == 0`, `wrapperCount == null`, `primitiveEnabled == false` và `wrapperEnabled == null`.

Đây là quy tắc khởi tạo của Java. Jackson có thể giữ các giá trị đó nếu thuộc tính không được cung cấp trong JSON, hoặc cập nhật chúng khi property xuất hiện. Nếu field có initializer hoặc constructor đặt giá trị riêng, trạng thái khi thuộc tính bị thiếu có thể khác giá trị mặc định của Java.

## 3. JSON `null` ánh xạ vào primitive

Xét lớp có một thuộc tính `int`:

```java
public class PrimitiveRequest {
    private int quantity;

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
```

Với cấu hình mặc định thông thường của Jackson Databind, JSON sau:

```json
{"quantity": null}
```

có thể được giải tuần tự hóa thành đối tượng có `quantity == 0`. Jackson cần cung cấp một giá trị primitive vì setter nhận `int`, không thể nhận Java null. Giá trị mặc định cho các primitive số là 0, boolean là `false`, còn `char` là ký tự null.

Điều này tiện trong một số mô hình dữ liệu nhưng có thể làm mất ý nghĩa đầu vào. Nếu `quantity` là số lượng do client gửi, `0` có thể là một giá trị hợp lệ và khác với việc client gửi `null`. Nếu ứng dụng coi null là dữ liệu không hợp lệ, nên bật kiểm tra thay vì âm thầm chuyển null thành 0.

### Từ chối JSON null cho primitive

Có thể bật `FAIL_ON_NULL_FOR_PRIMITIVES`:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper strictMapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);

String json = "{\"quantity\":null}";
PrimitiveRequest request = strictMapper.readValue(
        json,
        PrimitiveRequest.class
);
```

Với cấu hình này, việc ánh xạ explicit JSON null vào primitive sẽ thất bại bằng ngoại lệ mapping của Jackson, thay vì gán giá trị mặc định. Trong ứng dụng, có thể bắt ngoại lệ Jackson ở ranh giới API và chuyển thành phản hồi validation phù hợp.

Feature này áp dụng cho null tường minh được gửi vào primitive. Nó không có nghĩa mọi thuộc tính primitive bị thiếu đều tự động gây lỗi. Trường hợp thiếu thuộc tính cần được xem xét riêng, đặc biệt khi Jackson tạo đối tượng thông qua constructor hoặc creator.

## 4. JSON `null` ánh xạ vào wrapper

Đổi thuộc tính thành `Integer`:

```java
public class WrapperRequest {
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

Khi đọc:

```json
{"quantity": null}
```

Jackson có thể gán Java null cho `quantity`, vì `Integer` là kiểu tham chiếu. Điều này giữ được trạng thái “không có giá trị” trong đối tượng.

So sánh hai kiểu:

| JSON đầu vào | Thuộc tính `int` (mặc định) | Thuộc tính `Integer` |
|---|---:|---|
| `{"quantity": 7}` | `7` | `7` |
| `{"quantity": 0}` | `0` | `0` |
| `{"quantity": null}` | `0` theo mặc định, hoặc lỗi nếu bật `FAIL_ON_NULL_FOR_PRIMITIVES` | Java `null` |
| `{}` và field không có initializer | `0` do field primitive được khởi tạo mặc định | Java `null` do field tham chiếu được khởi tạo mặc định |

Wrapper phù hợp khi ứng dụng cần biểu diễn thêm trạng thái chưa có giá trị. Tuy nhiên, chỉ đổi từ `int` sang `Integer` chưa chắc giữ được sự khác biệt giữa thuộc tính bị lược bỏ và thuộc tính được gửi rõ ràng với null; hai trường hợp đó thường cùng cho kết quả Java null nếu không có cơ chế theo dõi sự hiện diện.

## 5. Phân biệt thuộc tính bị thiếu với thuộc tính có giá trị null

Hãy xem hai JSON sau:

```json
{}
```

```json
{"quantity": null}
```

JSON thứ nhất không có thuộc tính `quantity`. JSON thứ hai có thuộc tính `quantity`, và giá trị của nó là null. Ở cấp cú pháp JSON, hai tài liệu này khác nhau.

Với một bean mutable có constructor không tham số:

- Nếu Jackson không gặp thuộc tính `quantity`, nó thường không gọi setter cho property đó. Field giữ giá trị đã có sau khi constructor và initializer chạy.
- Nếu Jackson gặp `"quantity": null`, nó xử lý giá trị null theo kiểu đích và null policy. Với wrapper, setter có thể được gọi với Java null. Với primitive, null mặc định được chuyển thành giá trị primitive mặc định hoặc bị từ chối nếu bật feature tương ứng.

Ví dụ dùng initializer để làm rõ sự khác biệt giữa thiếu và null:

```java
public class MutableSettings {
    private int primitiveLimit = 5;
    private Integer wrapperLimit = 5;

    public int getPrimitiveLimit() {
        return primitiveLimit;
    }

    public void setPrimitiveLimit(int primitiveLimit) {
        this.primitiveLimit = primitiveLimit;
    }

    public Integer getWrapperLimit() {
        return wrapperLimit;
    }

    public void setWrapperLimit(Integer wrapperLimit) {
        this.wrapperLimit = wrapperLimit;
    }
}
```

Nếu đọc `{}`, các setter không được gọi và cả hai field giữ giá trị khởi tạo `5`. Nếu đọc `{"primitiveLimit":null,"wrapperLimit":null}`, primitive mặc định được gán `0`, còn wrapper được gán Java null. Ví dụ này cho thấy kết quả không chỉ phụ thuộc kiểu khai báo mà còn phụ thuộc property có xuất hiện hay không.

### Giữ được thông tin “đã gửi” hay chưa

Nếu nghiệp vụ cần phân biệt “không gửi trường” với “gửi trường null”, có thể theo dõi sự hiện diện riêng:

```java
import com.fasterxml.jackson.annotation.JsonSetter;

public class PatchRequest {
    private Integer quantity;
    private boolean quantityProvided;

    public Integer getQuantity() {
        return quantity;
    }

    public boolean isQuantityProvided() {
        return quantityProvided;
    }

    @JsonSetter("quantity")
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
        this.quantityProvided = true;
    }
}
```

Với bean có setter như trên:

```java
PatchRequest absent = mapper.readValue("{}", PatchRequest.class);
PatchRequest explicitNull = mapper.readValue(
        "{\"quantity\":null}",
        PatchRequest.class
);

System.out.println(absent.isQuantityProvided());       // false
System.out.println(explicitNull.isQuantityProvided()); // true
System.out.println(explicitNull.getQuantity() == null);// true
```

Setter chỉ được gọi khi property xuất hiện theo cấu hình thông thường. Nếu ứng dụng bật null policy như `Nulls.SKIP`, setter có thể không được gọi cho giá trị null; khi đó cờ presence không còn phản ánh ý định đầu vào như ví dụ. Hãy chọn null policy phù hợp với cách theo dõi sự hiện diện.

Một lựa chọn khác là đọc thành `JsonNode` trước, dùng `has(...)` và `hasNonNull(...)` để nhận diện trạng thái, rồi mới ánh xạ hoặc cập nhật mô hình. Với request PATCH, cách giữ riêng presence và value thường quan trọng hơn việc chỉ dùng một wrapper.

## 6. Xử lý null bằng `@JsonSetter` và `Nulls`

Jackson cho phép định nghĩa cách xử lý giá trị null tường minh tại từng property bằng `@JsonSetter` và enum `Nulls`.

| Chính sách | Ý nghĩa khi property nhận JSON null |
|---|---|
| `Nulls.SET` | Gán null theo cách thông thường; đây là hành vi mặc định phổ biến cho property tham chiếu |
| `Nulls.SKIP` | Bỏ qua việc gán property; giá trị hiện có của đối tượng được giữ lại |
| `Nulls.FAIL` | Ném lỗi khi gặp null |
| `Nulls.AS_EMPTY` | Dùng giá trị rỗng theo cách định nghĩa bởi deserializer của kiểu đích |
| `Nulls.DEFAULT` | Dùng chính sách null mặc định của mapper/property |

Ví dụ từ chối null cho một thuộc tính bắt buộc:

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

public class CreateOrderRequest {
    @JsonSetter(nulls = Nulls.FAIL)
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

Khi JSON có `"quantity": null`, Jackson từ chối giá trị đó. Tuy nhiên, `Nulls.FAIL` không tự biến thuộc tính bị thiếu thành lỗi; nếu JSON là `{}`, null handler không được gọi vì không có giá trị null nào được cung cấp. Kiểm tra sự hiện diện của property là một yêu cầu riêng.

Ví dụ bỏ qua null để giữ giá trị đã có:

```java
public class UpdatePreferences {
    @JsonSetter(nulls = Nulls.SKIP)
    private Integer pageSize = 20;

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
```

Khi đọc `{"pageSize":null}`, Jackson bỏ qua thao tác gán và `pageSize` giữ giá trị `20`. Khi đọc `{"pageSize":50}`, giá trị trở thành `50`. Khi đọc `{}`, property cũng không được gán nên giá trị khởi tạo vẫn là `20`.

`Nulls.AS_EMPTY` phụ thuộc định nghĩa “empty” của deserializer. Với collection, nó thường tạo collection rỗng; với kiểu khác, kết quả phụ thuộc kiểu và deserializer. Không nên giả định nó luôn tương đương số 0 hoặc chuỗi rỗng cho mọi kiểu.

## 7. Phân biệt null của property với null của phần tử collection

Một thuộc tính collection có thể có hai vị trí nhận null khác nhau:

1. Chính thuộc tính collection là null: `"tags": null`.
2. Collection tồn tại nhưng một phần tử bên trong là null: `"tags": ["java", null]`.

`@JsonSetter` cung cấp cả `nulls` và `contentNulls` để điều khiển hai cấp đó:

```java
public class TagRequest {
    @JsonSetter(nulls = Nulls.AS_EMPTY, contentNulls = Nulls.FAIL)
    private List<String> tags;

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

Với cấu hình này, `"tags": null` được xử lý theo null policy của property và yêu cầu giá trị rỗng của deserializer list. Còn `"tags": ["java", null]` bị từ chối vì phần tử null vi phạm `contentNulls = Nulls.FAIL`.

Khi thiết kế schema, hãy xác định riêng collection có được phép không tồn tại, có được phép null, có thể rỗng hay có phần tử null. Đây là bốn trạng thái khác nhau về mặt dữ liệu.

## 8. Null trong constructor và Java record

Với record hoặc một lớp dùng constructor-based creator, Jackson truyền giá trị các property vào constructor thay vì tạo object rỗng rồi gọi setter. Do đó, các feature dành cho creator properties đặc biệt hữu ích:

- `FAIL_ON_MISSING_CREATOR_PROPERTIES`: từ chối nếu một tham số creator không được cung cấp.
- `FAIL_ON_NULL_CREATOR_PROPERTIES`: từ chối nếu tham số creator nhận giá trị null.
- `FAIL_ON_NULL_FOR_PRIMITIVES`: từ chối JSON null khi giá trị đích là primitive.

Ví dụ:

```java
public record Shipment(String trackingCode, Integer packageCount) {
}

ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
```

Với cấu hình này, mọi creator property cần được cung cấp và không được null. Điều này có thể phù hợp với record dùng làm lệnh nghiệp vụ bắt buộc đủ dữ liệu. Nếu một component được phép tùy chọn, không nên bật chính sách bắt buộc toàn cục một cách thiếu cân nhắc; hãy chọn cấu hình phù hợp hoặc dùng DTO khác cho loại request đó.

Với record có component primitive, component không thể giữ Java null sau khi tạo. Nếu cần trạng thái chưa biết hoặc chưa được cung cấp, hãy cân nhắc dùng wrapper như `Integer` hoặc `Boolean`, đồng thời quyết định riêng cách xử lý property bị thiếu.

## 9. Serialization: null có được ghi ra JSON không?

Ở chiều serialization, primitive không thể null nên luôn có một giá trị để ghi, ví dụ `0` hoặc `false`. Wrapper có thể null. Mặc định, Jackson thường ghi property wrapper có giá trị null thành JSON null:

```java
public class Profile {
    private Integer age;
    private Boolean active;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
```

Nếu cả hai wrapper đang null, JSON thường có dạng:

```json
{"age":null,"active":null}
```

Nếu muốn bỏ các property null khỏi output, có thể dùng `@JsonInclude`:

```java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class Profile {
    private Integer age;
    private Boolean active;
    // getters/setters
}
```

Hoặc cấu hình ở mapper:

```java
ObjectMapper mapper = JsonMapper.builder()
        .serializationInclusion(JsonInclude.Include.NON_NULL)
        .build();
```

`NON_NULL` chỉ ảnh hưởng serialization: property có giá trị Java null sẽ không được ghi ra JSON. Nó không thay đổi cách Jackson nhận JSON null khi deserialization. Vì vậy, đừng dùng `NON_NULL` như một cách validation đầu vào.

Đối với primitive, `NON_NULL` không loại bỏ giá trị mặc định như 0 hoặc false vì primitive không thể null. Nếu mục tiêu là bỏ giá trị mặc định, cần xem xét inclusion policy khác như `NON_DEFAULT`, nhưng chính sách đó có thể loại bỏ cả giá trị hợp lệ trùng với default. Hãy chọn theo hợp đồng response.

## 10. Primitive hay wrapper: chọn theo ý nghĩa dữ liệu

Không có quy tắc rằng wrapper luôn tốt hơn primitive hoặc ngược lại. Hãy chọn kiểu dựa trên miền giá trị và ý nghĩa của trạng thái thiếu:

| Nhu cầu | Kiểu thường phù hợp | Lý do |
|---|---|---|
| Giá trị luôn tồn tại và không có trạng thái chưa biết | `int`, `long`, `boolean` | Gọn, không thể null và thể hiện rõ luôn có giá trị |
| Giá trị có thể không được cung cấp | `Integer`, `Long`, `Boolean` | Có thể biểu diễn Java null |
| Cần phân biệt thiếu với null tường minh | Wrapper cộng cờ presence, setter tracking hoặc `JsonNode` | Wrapper đơn lẻ thường không giữ được sự khác biệt này |
| Component bắt buộc trong constructor/record | Primitive hoặc wrapper cùng strict creator features/validation | Có thể từ chối thiếu/null theo hợp đồng |
| Trường PATCH có quy tắc “không gửi = giữ nguyên” | Wrapper cùng presence tracking hoặc mô hình patch chuyên biệt | Cần biết property có xuất hiện trong request hay không |

Với dữ liệu số, `0` có thể là giá trị hợp lệ. Nếu dùng primitive và để Jackson chuyển JSON null thành 0, ứng dụng không thể biết 0 là giá trị người dùng gửi hay là kết quả thay thế null. Wrapper giữ được null, nhưng để phân biệt “không gửi” với “gửi null” vẫn cần thêm thông tin presence.

## 11. Một ví dụ xử lý PATCH có phân biệt thiếu và null

Giả sử API cho phép client cập nhật `displayName` và `age`:

- Không gửi `displayName`: giữ tên hiện tại.
- Gửi `displayName: null`: yêu cầu xóa tên nếu nghiệp vụ cho phép.
- Gửi một chuỗi: cập nhật tên.
- Không gửi `age`: giữ tuổi hiện tại.
- Gửi `age: null`: yêu cầu xóa tuổi hoặc báo lỗi theo hợp đồng.
- Gửi một số: cập nhật tuổi.

Một DTO đơn giản có thể giữ trạng thái presence như sau:

```java
public class ProfilePatch {
    private String displayName;
    private boolean displayNameProvided;
    private Integer age;
    private boolean ageProvided;

    @JsonSetter("displayName")
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
        this.displayNameProvided = true;
    }

    @JsonSetter("age")
    public void setAge(Integer age) {
        this.age = age;
        this.ageProvided = true;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean isDisplayNameProvided() {
        return displayNameProvided;
    }

    public Integer getAge() {
        return age;
    }

    public boolean isAgeProvided() {
        return ageProvided;
    }
}
```

Logic dịch vụ có thể dựa trên hai thông tin value và provided:

```java
if (patch.isDisplayNameProvided()) {
    if (patch.getDisplayName() == null) {
        profile.clearDisplayName();
    } else {
        profile.rename(patch.getDisplayName());
    }
}

if (patch.isAgeProvided()) {
    if (patch.getAge() == null) {
        profile.clearAge();
    } else {
        profile.changeAge(patch.getAge());
    }
}
```

Ví dụ giả định API cho phép xóa hai trường. Nếu nghiệp vụ không cho phép, nhánh null cần trả lỗi validation thay vì gọi phương thức xóa. Điểm cốt lõi là DTO giữ lại ý định “có gửi trường” trước khi logic cập nhật quyết định hành động.

## 12. Các nguyên tắc thực hành

- Dùng primitive khi giá trị luôn tồn tại và default của kiểu có ý nghĩa rõ ràng.
- Dùng wrapper khi cần biểu diễn null hoặc trạng thái chưa có giá trị.
- Bật `FAIL_ON_NULL_FOR_PRIMITIVES` nếu JSON null vào primitive phải bị từ chối.
- Với constructor/record, xem xét `FAIL_ON_MISSING_CREATOR_PROPERTIES` và `FAIL_ON_NULL_CREATOR_PROPERTIES` theo hợp đồng dữ liệu.
- Dùng `@JsonSetter(nulls = ...)` để kiểm soát null ở một property; dùng `contentNulls` cho null bên trong collection.
- Không nhầm null tường minh với thuộc tính không xuất hiện; dùng presence tracking hoặc đọc cây khi nghiệp vụ cần phân biệt.
- Nhớ rằng `@JsonInclude(NON_NULL)` tác động đến chiều ghi JSON, không phải validation chiều đọc.
- Kiểm tra các trường hợp giá trị bình thường, 0/false, null, thiếu property và sai kiểu bằng dữ liệu mẫu có chủ đích.

## 13. Kết luận

Khi Jackson ánh xạ JSON null vào kiểu nguyên thủy, mặc định nó thường dùng giá trị primitive tương ứng như 0 hoặc false; bật `FAIL_ON_NULL_FOR_PRIMITIVES` để từ chối trường hợp này. Với kiểu bao như `Integer` hoặc `Boolean`, JSON null được biểu diễn bằng Java null. Thuộc tính không xuất hiện lại là một trạng thái riêng: bean có thể giữ initializer hoặc giá trị mặc định vì Jackson không gán property đó. Nếu cần phân biệt thiếu với null tường minh, hãy theo dõi presence bằng setter, DTO patch hoặc `JsonNode`. Các chính sách `@JsonSetter`, creator features và `@JsonInclude` cho phép kiểm soát từng chiều ánh xạ, nhưng cần được chọn theo hợp đồng dữ liệu thay vì bật mặc định một cách máy móc.
