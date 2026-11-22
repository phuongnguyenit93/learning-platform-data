# Xử lý getter boolean và tên thuộc tính dễ gây nhập nhằng

Jackson thường xác định thuộc tính JSON từ getter, setter, field và constructor của một lớp Java. Với thuộc tính boolean, quy ước đặt tên getter có một điểm dễ gây nhầm lẫn: phương thức `isActive()` thường đại diện cho thuộc tính JSON `active`, còn `getIsActive()` thường đại diện cho thuộc tính `isActive`. Khi field, getter và setter dùng các tên không nhất quán, JSON có thể xuất hiện tên ngoài dự kiến, bị lặp thuộc tính hoặc không deserialize được như mong muốn.

Để kiểm soát kết quả, cần hiểu quy tắc nhận diện getter của Jackson, phân biệt `boolean` nguyên thủy với `Boolean` wrapper, và dùng annotation để khai báo tên JSON rõ ràng khi quy ước Java không đủ diễn đạt hợp đồng dữ liệu.

## 1. Jackson nhận diện thuộc tính Java như thế nào?

Trong data binding, Jackson xây dựng các thuộc tính logic từ những thành phần mà nó nhận diện trên lớp Java. Một thuộc tính có thể được tạo từ:

- Getter dùng để đọc giá trị khi serialize.
- Setter dùng để gán giá trị khi deserialize.
- Field được Jackson cho phép truy cập.
- Constructor hoặc factory method được dùng để tạo object.
- Annotation như `@JsonProperty`, `@JsonIgnore` và `@JsonCreator`.

Những thành phần cùng đại diện cho một tên thuộc tính có thể được hợp nhất thành một logical property. Ví dụ, field `active`, getter `isActive()` và setter `setActive(boolean)` cùng mô tả thuộc tính `active`.

```java
public class User {
    private boolean active;

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Với quy ước JavaBeans thông thường, thuộc tính này có tên logic là `active`. JSON mặc định sẽ dùng tên đó:

```json
{
  "active": true
}
```

Điều quan trọng là Jackson không đơn giản lấy nguyên tên field rồi đưa vào JSON. Tên property có thể được suy ra từ getter hoặc setter, rồi được điều chỉnh bởi annotation, visibility và naming strategy.

## 2. Quy tắc đặt tên getter boolean

JavaBeans có hai dạng getter phổ biến:

- Getter thông thường: `getX()`.
- Getter boolean: `isX()`.

Với kiểu `boolean` nguyên thủy, Jackson nhận diện dạng `isX()` theo quy ước bean. Phần `X` được chuyển thành tên thuộc tính theo quy tắc viết hoa/thường của JavaBeans.

| Phương thức | Tên property thường được suy ra |
|---|---|
| `getName()` | `name` |
| `isActive()` trả về `boolean` | `active` |
| `getActive()` | `active` |
| `getIsActive()` | `isActive` |
| `isReady()` trả về `boolean` | `ready` |
| `getURL()` | `URL` |

Ví dụ:

```java
public class Device {
    public boolean isReady() {
        return true;
    }

    public boolean isOnline() {
        return false;
    }

    public boolean getIsArchived() {
        return false;
    }
}
```

Các tên property được suy ra là `ready`, `online` và `isArchived`. Tiền tố `is` trong `isReady()` là dấu hiệu của getter boolean và bị loại khỏi tên property. Trong `getIsArchived()`, tiền tố getter là `get`, vì vậy phần tên còn lại là `IsArchived`, được chuyển thành `isArchived`.

### 2.1. `isActive()` không có nghĩa JSON phải có key `isActive`

Đây là nhầm lẫn phổ biến nhất. Tên phương thức:

```java
public boolean isActive() {
    return active;
}
```

thường tạo property `active`, chứ không phải `isActive`. Nếu hợp đồng JSON yêu cầu key đúng là `isActive`, hãy khai báo tên tường minh:

```java
public class User {
    private boolean active;

    @JsonProperty("isActive")
    public boolean isActive() {
        return active;
    }

    @JsonProperty("isActive")
    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Khi đó, tên thuộc tính JSON là `isActive` theo annotation. Một lựa chọn khác là dùng `@JsonProperty` ở field và giữ tên nhất quán cho các accessor. Tránh gắn các annotation với tên khác nhau lên field, getter và setter của cùng một giá trị vì có thể tạo các logical property riêng hoặc xung đột khi Jackson hợp nhất thuộc tính.

### 2.2. Quy tắc chữ hoa đầu tên và acronym

Jackson sử dụng quy tắc suy ra tên property tương tự quy ước JavaBeans. Nếu hai ký tự đầu của phần tên đều viết hoa, chúng thường được giữ nguyên. Vì vậy:

```java
public String getURL() {
    return "https://example.com";
}

public String getName() {
    return "An";
}
```

thường tạo property `URL` và `name`. Nếu API JSON yêu cầu `url` viết thường, có thể dùng `@JsonProperty("url")`:

```java
@JsonProperty("url")
public String getURL() {
    return url;
}
```

Quy tắc acronym cũng có thể làm tên field và tên getter trông không đồng nhất. Với DTO trao đổi dữ liệu, nên xác định tên JSON bằng annotation khi tên có ý nghĩa đặc biệt hoặc phải giữ nguyên hợp đồng của một API bên ngoài.

## 3. Phân biệt boolean và Boolean

Java có hai kiểu thường được dùng để biểu diễn trạng thái:

- `boolean`: kiểu nguyên thủy, chỉ có `true` hoặc `false`.
- `Boolean`: kiểu wrapper, có thể là `true`, `false` hoặc `null`.

Sự khác biệt này ảnh hưởng đến quy ước getter và ý nghĩa của dữ liệu.

### 3.1. Getter `isX()` cho boolean nguyên thủy

Đây là dạng JavaBeans quen thuộc:

```java
public class Feature {
    private boolean enabled;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Jackson nhận diện `isEnabled()` là getter boolean và suy ra property `enabled`.

### 3.2. Getter `getX()` cho Boolean wrapper

Với `Boolean`, dạng rõ ràng và dễ tương thích nhất là `getX()`:

```java
public class Feature {
    private Boolean enabled;

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }
}
```

Property được suy ra là `enabled`, và giá trị `null` có thể biểu diễn trạng thái chưa biết hoặc chưa được cung cấp.

Theo mặc định, Jackson chỉ nhận diện `isX()` như getter boolean khi kiểu trả về là `boolean` nguyên thủy. Ví dụ sau có thể không được nhận diện như getter theo quy tắc mặc định:

```java
public class Feature {
    private Boolean enabled;

    public Boolean isEnabled() {
        return enabled;
    }
}
```

Nếu muốn dùng dạng `isEnabled()` với kiểu trả về không phải primitive boolean, Jackson có `MapperFeature.ALLOW_IS_GETTERS_FOR_NON_BOOLEAN`. Có thể bật feature này trước khi mapper được sử dụng:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.configure(MapperFeature.ALLOW_IS_GETTERS_FOR_NON_BOOLEAN, true);
```

Feature này thay đổi quy tắc nhận diện getter của mapper. Chỉ bật khi dự án thực sự cần quy ước đó và đã thống nhất cách đặt tên; nếu không, dùng `getEnabled()` cho `Boolean` thường rõ ràng hơn.

### 3.3. Chọn kiểu theo ý nghĩa nghiệp vụ

Nếu trạng thái chỉ có hai khả năng, `boolean` thường biểu đạt đúng hơn. Nếu dữ liệu có thể thiếu hoặc trạng thái chưa được xác định, `Boolean` có thể phù hợp.

Ví dụ, trong một request cập nhật một phần:

```json
{
  "emailVerified": null
}
```

`null` có thể mang ý nghĩa khác với `false`, tùy hợp đồng API. Với primitive `boolean`, Jackson không thể lưu trạng thái null vào field; giá trị có thể trở thành giá trị mặc định hoặc phát sinh hành vi phụ thuộc cấu hình và kiểu đích. Vì vậy, hãy chọn kiểu Java theo ngữ nghĩa của dữ liệu, không chỉ theo hình thức getter.

## 4. Những cách đặt tên dễ tạo property ngoài ý muốn

### 4.1. Field bắt đầu bằng `is`, getter lại bỏ `is`

Ví dụ:

```java
public class Device {
    private boolean isReady;

    public boolean isReady() {
        return isReady;
    }
}
```

Getter `isReady()` được suy ra thành property `ready`. Field có tên `isReady`, nhưng field private thường không được Jackson tự động xem là một property độc lập với cấu hình visibility mặc định. Kết quả thông thường là JSON dùng key `ready`.

Để mã nguồn dễ hiểu hơn, nên đặt field là `ready`:

```java
public class Device {
    private boolean ready;

    public boolean isReady() {
        return ready;
    }

    public void setReady(boolean ready) {
        this.ready = ready;
    }
}
```

Field và accessor giờ cùng biểu diễn một property `ready`.

### 4.2. Getter `isReady()` và getter `getIsReady()` cùng tồn tại

Hai phương thức sau có thể tạo hai tên property khác nhau:

```java
public boolean isReady() {
    return ready;
}

public boolean getIsReady() {
    return ready;
}
```

Getter đầu thường đại diện cho `ready`; getter thứ hai thường đại diện cho `isReady`. Nếu cả hai được Jackson nhận diện, kết quả có thể chứa hai property cùng đọc một giá trị:

```json
{
  "ready": true,
  "isReady": true
}
```

Nếu đây không phải hợp đồng JSON mong muốn, hãy giữ một getter có tên rõ ràng hoặc đánh dấu tường minh bằng annotation. Không nên tạo nhiều accessor chỉ để chiều lòng các cách gọi khác nhau trong Java.

### 4.3. Có cả isX() và getX() cho cùng một property

Một lớp có thể vô tình khai báo cả hai dạng:

```java
public boolean isEnabled() {
    return enabled;
}

public boolean getEnabled() {
    return enabled;
}
```

Cả hai cùng suy ra property `enabled`. Jackson phải chọn getter phù hợp trong quá trình introspection; các getter xung đột có thể tạo kết quả khó hiểu hoặc báo lỗi tùy cấu trúc lớp và quy tắc ưu tiên. Cách thiết kế dễ bảo trì là chỉ cung cấp một getter chuẩn. Nếu bắt buộc phải có cả hai cho API Java, hãy khai báo rõ accessor nào Jackson dùng bằng annotation và kiểm tra kết quả serialize/deserialize.

### 4.4. Field và getter tạo hai tên khác nhau

Khi field được bật visibility bằng cấu hình toàn cục hoặc annotation, field `isEnabled` có thể được nhận diện riêng trong khi getter `isEnabled()` tạo property `enabled`.

Ví dụ:

```java
public class Feature {
    @JsonProperty
    private boolean isEnabled;

    public boolean isEnabled() {
        return isEnabled;
    }
}
```

Field được annotation có thể mang tên JSON `isEnabled`, còn getter suy ra tên `enabled`. Nếu cả hai không được hợp nhất theo cùng tên logic, output có thể có cả hai key hoặc gặp xung đột property.

Để tránh tình huống này, đặt tên field theo property logic và khai báo tên JSON tại một nơi nhất quán:

```java
public class Feature {
    private boolean enabled;

    @JsonProperty("isEnabled")
    public boolean isEnabled() {
        return enabled;
    }

    @JsonProperty("isEnabled")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Ở đây, field Java là `enabled`, còn tên JSON được công bố rõ ràng là `isEnabled`.

## 5. Dùng annotation để xác định hợp đồng JSON

Khi quy ước tên Java không đủ rõ, annotation giúp tách tên API JSON khỏi tên phương thức hoặc field nội bộ.

### 5.1. @JsonProperty

`@JsonProperty` xác định tên thuộc tính JSON:

```java
public class Account {
    private boolean active;

    @JsonProperty("is_active")
    public boolean isActive() {
        return active;
    }

    @JsonProperty("is_active")
    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Tên JSON là `is_active`, bất kể tên property Java được suy ra từ getter là `active`. Việc dùng cùng một tên trên getter và setter làm ý định hai chiều rõ ràng.

Nếu field, getter và setter đều được annotation, hãy đảm bảo chúng dùng cùng tên JSON. Annotation không nhất quán có thể khiến Jackson xem chúng là các thuộc tính khác nhau.

### 5.2. @JsonIgnore

Nếu một getter phụ chỉ phục vụ nội bộ và không được đưa vào JSON, có thể dùng `@JsonIgnore`:

```java
public class Device {
    private boolean ready;

    public boolean isReady() {
        return ready;
    }

    @JsonIgnore
    public boolean getReadyForDisplay() {
        return ready;
    }
}
```

`getReadyForDisplay()` có thể được nhận diện như getter của property `readyForDisplay`; `@JsonIgnore` loại property đó khỏi ánh xạ theo annotation. Nếu cần đọc/ghi bất đối xứng, có thể xem xét `@JsonProperty(access = ...)` thay vì bỏ qua hoàn toàn.

### 5.3. @JsonProperty.Access

`@JsonProperty.Access` xác định hướng truy cập của một property:

```java
public class Account {
    private String username;
    private String serverGeneratedToken;

    @JsonProperty(access = JsonProperty.Access.READ_WRITE)
    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    public String getServerGeneratedToken() {
        return serverGeneratedToken;
    }

    public void setServerGeneratedToken(String token) {
        this.serverGeneratedToken = token;
    }
}
```

Trong ví dụ, `WRITE_ONLY` nghĩa là property có thể được nhận từ JSON khi deserialize nhưng không được xuất ra JSON khi serialize. `READ_ONLY` có nghĩa là chỉ xuất khi serialize và không nhận giá trị đầu vào theo property đó. Cần chọn đúng hướng theo hợp đồng API và cân nhắc việc đặt annotation trên thành phần đại diện cho property.

### 5.4. @JsonAlias cho tên đầu vào thay thế

Nếu hệ thống cần đọc dữ liệu cũ với nhiều tên field nhưng luôn xuất một tên chuẩn, `@JsonAlias` có thể dùng cho deserialize:

```java
public class Feature {
    private boolean enabled;

    @JsonProperty("enabled")
    @JsonAlias({"isEnabled", "is_enabled"})
    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

`@JsonAlias` cho phép nhận các tên thay thế khi đọc JSON. Khi serialize, Jackson vẫn dùng tên property chuẩn được khai báo. Điều này hữu ích khi chuyển đổi hợp đồng API theo thời gian mà vẫn cần tương thích với payload cũ.

## 6. Naming strategy có thay đổi tên boolean property không?

Sau khi Jackson suy ra tên logic từ getter, naming strategy có thể chuyển tên property sang quy ước JSON khác. Ví dụ `PropertyNamingStrategies.SNAKE_CASE` có thể chuyển `isActive()` thành property `active`, rồi serialize thành `active` (không phải `is_active`, vì phần `is` đã là tiền tố getter và bị loại khi suy ra property).

```java
ObjectMapper mapper = new ObjectMapper();
mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

public class User {
    private boolean active;

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Property logic là `active`; naming strategy chuyển đổi tên logic này theo quy tắc snake case. Với tên đã có acronym hoặc annotation chỉ định tên tường minh, hãy kiểm tra hành vi thực tế thay vì đoán kết quả bằng cách nối tiền tố.

Annotation `@JsonProperty` có thể xác định tên hợp đồng trực tiếp. Khi cần giữ một tên API cố định bất kể naming strategy toàn cục, hãy dùng annotation và kiểm tra cả hai chiều serialize/deserialize.

## 7. Lombok và getter do công cụ sinh ra

Nếu lớp dùng Lombok, getter thực tế có thể được sinh tự động. Quy tắc đặt tên getter của Lombok có thể phụ thuộc tên field, kiểu primitive/wrapper và cấu hình `lombok.config`.

Ví dụ:

```java
@Getter
public class Feature {
    private boolean active;
    private Boolean archived;
}
```

Lombok thường sinh getter theo quy ước boolean cho `active` và getter thông thường cho `archived`. Jackson chỉ nhìn thấy các method/field có trong class đã biên dịch và metadata liên quan, không dựa vào ý định người viết annotation.

Khi output có key ngoài dự kiến, hãy xem mã nguồn đã được Lombok sinh ra (ví dụ dùng Delombok hoặc tính năng xem generated sources của IDE), sau đó đối chiếu tên method với quy tắc Jackson. Không nên suy luận chỉ từ tên field ban đầu.

## 8. Quy trình xử lý property boolean bị nhập nhằng

Khi JSON có key `isX` bất ngờ, thiếu key hoặc xuất hiện hai key cùng mang một giá trị, có thể điều tra theo trình tự:

1. **Xác định kiểu dữ liệu.** Field là `boolean` hay `Boolean`? Getter trả về kiểu nào?
2. **Liệt kê accessor thực tế.** Tìm mọi `isX()`, `getX()`, `getIsX()` và `setX()` trong class, kể cả method được Lombok sinh.
3. **Suy ra logical property.** Áp dụng quy tắc JavaBeans/Jackson: `isActive()` thường là `active`; `getIsActive()` thường là `isActive`.
4. **Kiểm tra field visibility.** Xác định field private có được nhận diện qua annotation hoặc cấu hình visibility hay không.
5. **Kiểm tra annotation.** Tìm `@JsonProperty`, `@JsonIgnore`, `@JsonAlias`, `@JsonGetter` và `@JsonSetter` trên field/accessor.
6. **Kiểm tra naming strategy.** Xác định mapper có dùng snake case hoặc strategy tùy chỉnh hay không.
7. **Kiểm tra chiều đọc và ghi riêng.** Một property có thể được nhận diện khác nhau cho serialize và deserialize nếu accessor/annotation không nhất quán.
8. **Chạy một ví dụ nhỏ với mapper thực tế.** Serialize một object có giá trị dễ nhận biết và deserialize JSON có các tên key dự kiến.

Ví dụ kiểm tra nhanh:

```java
ObjectMapper mapper = new ObjectMapper();

Feature feature = new Feature();
feature.setEnabled(true);

String json = mapper.writeValueAsString(feature);
System.out.println(json);

Feature restored = mapper.readValue(json, Feature.class);
System.out.println(restored.isEnabled());
```

Hãy dùng đúng `ObjectMapper` được ứng dụng cấu hình nếu đang điều tra lỗi trong framework. Một mapper mới với cấu hình mặc định có thể cho kết quả khác mapper production.

## 9. Nguyên tắc thiết kế DTO để tránh nhập nhằng

- Đặt field boolean theo tên trạng thái, chẳng hạn `active`, `ready`, `enabled`, thay vì lặp tiền tố `is` trong field.
- Dùng `isX()` cho getter trả về primitive `boolean`.
- Dùng `getX()` cho getter trả về wrapper `Boolean`, trừ khi dự án chủ động bật quy tắc khác.
- Tránh khai báo đồng thời `isX()` và `getIsX()` nếu chúng cùng biểu diễn một trạng thái nhưng tạo hai tên JSON.
- Dùng `@JsonProperty` khi tên JSON là hợp đồng cố định hoặc khác tên Java.
- Giữ tên annotation nhất quán trên các accessor của cùng một property.
- Dùng `@JsonAlias` khi cần nhận nhiều tên cũ nhưng vẫn xuất một tên chuẩn.
- Chọn `boolean` hay `Boolean` theo ngữ nghĩa của dữ liệu, đặc biệt khi cần phân biệt `false` với `null`.

Với record, builder, Lombok hoặc model có accessor tùy chỉnh, quy tắc introspection có thể khác với POJO JavaBeans đơn giản. Khi dùng những kiểu model này, hãy kiểm tra accessor thực tế và xác nhận JSON bằng mapper/cấu hình của ứng dụng.

## Kết luận

Tên JSON của thuộc tính boolean được suy ra từ accessor và quy tắc introspection, không nhất thiết trùng tên field hoặc tên method. `isActive()` thường tạo property `active`, còn `getIsActive()` thường tạo property `isActive`; getter `isX()` mặc định phù hợp với kiểu trả về primitive `boolean`. Khi hợp đồng JSON yêu cầu tên khác, hãy dùng `@JsonProperty` một cách nhất quán, tránh accessor trùng hoặc field/getter tạo nhiều logical property, và kiểm tra cả serialize lẫn deserialize bằng mapper thực tế của ứng dụng.
