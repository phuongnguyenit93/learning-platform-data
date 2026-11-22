# Ánh xạ mô hình builder và cấu hình bước tạo đối tượng

Khi một lớp Java dùng Builder Pattern, đối tượng thường được tạo qua một chuỗi lời gọi như `builder().name(...).active(...).build()`. Jackson có thể sử dụng chính mô hình này để tạo object khi đọc JSON. Cách làm đặc biệt phù hợp với lớp bất biến (immutable), lớp có nhiều thuộc tính tùy chọn hoặc lớp cần kiểm tra dữ liệu trước khi được tạo hoàn chỉnh.

Để Jackson hiểu builder, cần chỉ rõ builder class trên kiểu đích bằng `@JsonDeserialize(builder = ...)`, sau đó mô tả quy ước tên phương thức và phương thức kết thúc bằng `@JsonPOJOBuilder`.

## 1. Vì sao cần ánh xạ builder?

Với JavaBean truyền thống, Jackson thường tạo object bằng constructor không tham số rồi gán từng thuộc tính qua setter hoặc field:

```java
User user = new User();
user.setId(42L);
user.setName("An");
```

Cách này đơn giản, nhưng lớp phải cho phép trạng thái được thiết lập từng phần. Trong một số mô hình, ta muốn:

- Các thuộc tính là `final`, không có setter công khai.
- Object chỉ được tạo khi đã thu thập đủ dữ liệu cần thiết.
- Kiểm tra các bất biến nghiệp vụ tại một điểm duy nhất.
- Có nhiều thuộc tính tùy chọn mà constructor nhiều tham số sẽ khó sử dụng.
- Tách bước thu thập dữ liệu khỏi bước tạo object cuối cùng.

Builder Pattern đáp ứng các nhu cầu đó:

```java
User user = User.builder()
    .id(42L)
    .name("An")
    .active(true)
    .build();
```

Tuy nhiên, Jackson không tự động suy ra mọi builder chỉ từ tên phương thức `builder()`. Ta cần cấu hình để Jackson biết lớp builder nào sẽ nhận các thuộc tính JSON và phương thức nào sẽ tạo object đích.

## 2. Hai annotation chính

Hai annotation thường được dùng cùng nhau:

| Annotation | Package trong Jackson 2.x | Vai trò |
|---|---|---|
| `@JsonDeserialize(builder = ...)` | `com.fasterxml.jackson.databind.annotation` | Chỉ định builder class được dùng để deserialize kiểu đích |
| `@JsonPOJOBuilder` | `com.fasterxml.jackson.databind.annotation` | Cấu hình quy ước tên mutator và tên phương thức hoàn tất builder |

Cấu trúc tổng quát:

```java
@JsonDeserialize(builder = User.Builder.class)
public class User {
    // Trạng thái và hành vi của object đích

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder {
        // Các phương thức nhận giá trị từ JSON
        public User build() {
            // Tạo object đích
        }
    }
}
```

Jackson thực hiện luồng sau:

```text
JSON input
    |
    v
Deserialize User
    |
    v
Tạo User.Builder
    |
    +--> Ánh xạ từng JSON property vào builder mutator
    |
    v
Gọi phương thức build()
    |
    v
Tạo User hoàn chỉnh
```

Jackson làm việc với builder trong quá trình đọc JSON. Object đích chỉ được tạo khi phương thức build được gọi.

## 3. Ví dụ đầy đủ với immutable class

Xét lớp `User` có ba thuộc tính: `id`, `name` và `active`. Các thuộc tính là `final`, constructor của lớp được giữ private và không có setter.

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonPOJOBuilder;

@JsonDeserialize(builder = User.Builder.class)
public final class User {
    private final long id;
    private final String name;
    private final boolean active;

    private User(Builder builder) {
        this.id = builder.id;
        this.name = builder.name;
        this.active = builder.active;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public static Builder builder() {
        return new Builder();
    }

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder {
        private long id;
        private String name;
        private boolean active = true;

        public Builder id(long id) {
            this.id = id;
            return this;
        }

        public Builder name(String name) {
            this.name = name;
            return this;
        }

        public Builder active(boolean active) {
            this.active = active;
            return this;
        }

        public User build() {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "name must not be blank"
                );
            }

            return new User(this);
        }
    }
}
```

Đọc JSON bằng `ObjectMapper`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "id": 42,
      "name": "An",
      "active": true
    }
    """;

User user = mapper.readValue(json, User.class);

System.out.println(user.getId());
System.out.println(user.getName());
System.out.println(user.isActive());
```

Kết quả:

```text
42
An
true
```

Điều cần chú ý:

1. `@JsonDeserialize(builder = User.Builder.class)` đặt trên lớp đích `User`. Jackson biết phải dùng `Builder` khi đọc JSON thành `User`.
2. `Builder` là lớp lồng nhau `static`, có constructor không tham số mặc định để Jackson tạo instance.
3. Các phương thức `id(...)`, `name(...)`, `active(...)` nhận giá trị và trả lại chính builder để hỗ trợ fluent API.
4. `@JsonPOJOBuilder(withPrefix = "")` cho Jackson biết các phương thức không có tiền tố như `name(...)` cũng là mutator của property.
5. `build()` trả về object `User` hoàn chỉnh. Việc kiểm tra `name` trong `build()` bảo đảm object được tạo ra thỏa mãn quy tắc mà lớp yêu cầu.

Không cần constructor không tham số hoặc setter trên `User`. Jackson tạo builder, điền dữ liệu vào builder, rồi gọi `build()`.

## 4. Cấu hình tiền tố phương thức bằng withPrefix

`@JsonPOJOBuilder` có thuộc tính `withPrefix` để xác định tiền tố của các phương thức nhận dữ liệu.

Mặc định, `withPrefix` là `"with"`. Do đó, builder theo kiểu:

```java
public static class Builder {
    public Builder withId(long id) {
        this.id = id;
        return this;
    }

    public Builder withName(String name) {
        this.name = name;
        return this;
    }

    public User build() {
        return new User(this);
    }
}
```

có thể dùng annotation mặc định:

```java
@JsonPOJOBuilder
public static class Builder {
    // ...
}
```

Nếu builder dùng tiền tố `set`, khai báo:

```java
@JsonPOJOBuilder(withPrefix = "set")
public static class Builder {
    public Builder setId(long id) {
        this.id = id;
        return this;
    }

    public Builder setName(String name) {
        this.name = name;
        return this;
    }

    public User build() {
        return new User(this);
    }
}
```

Nếu phương thức không có tiền tố, như `id(...)` hoặc `name(...)`, dùng:

```java
@JsonPOJOBuilder(withPrefix = "")
```

Giá trị `withPrefix` phải khớp với quy ước thực tế của builder. Nếu Jackson đang tìm `withName(...)` nhưng lớp chỉ có `name(...)`, property có thể không được nhận diện như mong muốn.

## 5. Cấu hình tên phương thức hoàn tất bằng buildMethodName

Mặc định, Jackson gọi phương thức có tên `build` để lấy object đích. Nếu builder dùng tên khác như `create`, cần khai báo `buildMethodName`:

```java
@JsonPOJOBuilder(
    withPrefix = "set",
    buildMethodName = "create"
)
public static class Builder {
    public Builder setName(String name) {
        this.name = name;
        return this;
    }

    public User create() {
        return new User(this);
    }
}
```

Có thể tổng hợp các cấu hình:

| Builder convention | Cấu hình |
|---|---|
| `withName(...)` và `build()` | `@JsonPOJOBuilder` |
| `name(...)` và `build()` | `@JsonPOJOBuilder(withPrefix = "")` |
| `setName(...)` và `build()` | `@JsonPOJOBuilder(withPrefix = "set")` |
| `setName(...)` và `create()` | `@JsonPOJOBuilder(withPrefix = "set", buildMethodName = "create")` |

Phương thức hoàn tất phải trả về đúng kiểu object mà builder chịu trách nhiệm tạo. Nếu tên hoặc kiểu trả về không khớp, quá trình deserialize có thể thất bại khi Jackson tìm hoặc gọi build method.

## 6. Ánh xạ tên JSON vào builder mutator

Tên phương thức builder không nhất thiết giống tên key trong JSON. Có thể dùng `@JsonProperty` trên mutator để xác định tên JSON chuẩn:

```java
@JsonPOJOBuilder(withPrefix = "")
public static class Builder {
    private String displayName;

    @JsonProperty("display_name")
    public Builder displayName(String value) {
        this.displayName = value;
        return this;
    }

    public User build() {
        return new User(displayName);
    }
}
```

Nếu cần chấp nhận tên cũ, có thể dùng `@JsonAlias` ngay trên builder mutator:

```java
@JsonPOJOBuilder(withPrefix = "")
public static class Builder {
    private String displayName;

    @JsonProperty("display_name")
    @JsonAlias({"name", "full_name"})
    public Builder displayName(String value) {
        this.displayName = value;
        return this;
    }

    public User build() {
        return new User(displayName);
    }
}
```

Như vậy, các key `display_name`, `name` và `full_name` đều có thể cập nhật cùng một giá trị builder. Khi serialize object đích, Jackson sử dụng property của lớp đích theo metadata serialization của lớp đó; cấu hình alias ở builder không làm cho JSON đầu ra phát ra nhiều tên.

Có thể kết hợp quy tắc đặt tên toàn lớp với builder, nhưng cần kiểm tra mapper và annotation thực tế. Khi hợp đồng có tên đặc biệt, khai báo `@JsonProperty` trên mutator thường giúp ý định ánh xạ rõ ràng hơn.

## 7. Xử lý thuộc tính JSON không biết trong builder

Nếu JSON chứa key mà builder không có mutator tương ứng, hành vi mặc định thường chịu ảnh hưởng của `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES`. Với cấu hình mặc định phổ biến, Jackson báo lỗi thay vì âm thầm bỏ qua key không biết.

Nếu hợp đồng cho phép bỏ qua các trường mở rộng, có thể đặt `@JsonIgnoreProperties(ignoreUnknown = true)` trên builder:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.annotation.JsonPOJOBuilder;

@JsonPOJOBuilder(withPrefix = "")
@JsonIgnoreProperties(ignoreUnknown = true)
public static class Builder {
    // Builder properties và build()
}
```

Ví dụ payload có thêm trường `trace_id` mà lớp không cần dùng:

```json
{
  "id": 42,
  "name": "An",
  "trace_id": "req-123"
}
```

Nếu builder được cấu hình bỏ qua unknown property, Jackson vẫn có thể tạo object từ các thuộc tính đã biết. Chỉ bật hành vi này khi API thực sự muốn cho phép trường mở rộng; nếu cần phát hiện client gửi sai tên property, nên giữ chế độ báo lỗi để lỗi hợp đồng không bị che giấu.

## 8. Giá trị mặc định và kiểm tra dữ liệu trong build()

Builder thường có thể đặt giá trị mặc định cho thuộc tính tùy chọn:

```java
@JsonPOJOBuilder(withPrefix = "")
public static class Builder {
    private String name;
    private boolean active = true;
    private int retryCount = 3;

    public Builder name(String name) {
        this.name = name;
        return this;
    }

    public Builder active(boolean active) {
        this.active = active;
        return this;
    }

    public Builder retryCount(int retryCount) {
        this.retryCount = retryCount;
        return this;
    }

    public Settings build() {
        if (retryCount < 0) {
            throw new IllegalArgumentException(
                "retryCount must be >= 0"
            );
        }

        return new Settings(name, active, retryCount);
    }
}
```

Nếu JSON không chứa `active` hoặc `retryCount`, giá trị khởi tạo trong builder được giữ nguyên. Nếu JSON có chứa các key đó, mutator tương ứng cập nhật giá trị.

Cần phân biệt trường hợp thiếu thuộc tính với trường hợp thuộc tính có giá trị null:

- Thuộc tính bị thiếu: mutator có thể không được gọi, nên giá trị mặc định trong builder còn nguyên.
- Thuộc tính xuất hiện với `null`: mutator có thể được gọi với null đối với kiểu tham chiếu; với kiểu primitive, hành vi phụ thuộc cấu hình coercion/null handling của Jackson.
- Thuộc tính có giá trị cụ thể: builder nhận giá trị đã được Jackson chuyển đổi theo kiểu tham số.

Vì vậy, nếu cần phân biệt "không được gửi" và "được gửi null", builder có thể dùng wrapper hoặc kiểu biểu diễn trạng thái rõ ràng, thay vì chỉ dựa vào một field tham chiếu có giá trị null.

Validation nên đặt tại bước tạo object hoặc trong một lớp domain factory được builder gọi tới. Đừng giả định Jackson tự động chạy Bean Validation chỉ vì nó gọi build method; việc tích hợp validation cần được ứng dụng thực hiện rõ ràng.

## 9. Builder và các cách khởi tạo object khác

Jackson hỗ trợ nhiều cách tạo object. Nên chọn cách đơn giản nhất đáp ứng được mô hình dữ liệu.

| Cách khởi tạo | Cách Jackson sử dụng | Khi phù hợp |
|---|---|---|
| Constructor không tham số + setter/field | Tạo object rồi gán từng property | DTO mutable, cấu trúc đơn giản |
| `@JsonCreator` constructor/factory | Truyền các giá trị JSON vào tham số creator | Lớp bất biến có ít tham số |
| Builder | Tạo builder, gọi mutator, sau đó gọi build method | Lớp có nhiều thuộc tính, giá trị tùy chọn và quy tắc tạo object |
| Record | Dùng canonical constructor của record | DTO bất biến, dữ liệu có cấu trúc cố định |

### 9.1. So với @JsonCreator

Với lớp ít thuộc tính, constructor creator thường gọn hơn builder:

```java
public class Point {
    private final int x;
    private final int y;

    @JsonCreator
    public Point(
            @JsonProperty("x") int x,
            @JsonProperty("y") int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() {
        return x;
    }

    public int getY() {
        return y;
    }
}
```

Builder hữu ích hơn khi constructor có nhiều tham số hoặc có nhiều thuộc tính tùy chọn. Nó cũng tạo một điểm rõ ràng để kiểm tra các điều kiện liên thuộc tính trước khi trả về object hoàn chỉnh.

### 9.2. Builder không thay thế cơ chế serialize

`@JsonDeserialize(builder = ...)` điều khiển cách Jackson đọc JSON để tạo object. Khi ghi object ra JSON, Jackson vẫn introspect lớp đích theo getter, field, annotation và cấu hình serialization thông thường.

Do đó, một lớp có builder nhưng không có getter/field mà Jackson nhận diện được có thể deserialize thành công nhưng serialize ra thiếu thuộc tính hoặc không có thuộc tính nào. Nếu cần hỗ trợ cả hai chiều, hãy thiết kế metadata serialization trên lớp đích và kiểm thử riêng.

## 10. Dùng Lombok Builder với Jackson

Nếu dự án dùng Lombok để sinh builder, chỉ có `@Builder` thường chưa đủ để Jackson biết builder đó là cơ chế deserialize. Lombok cung cấp `@Jacksonized` để kết nối builder sinh tự động với Jackson.

Ví dụ:

```java
import lombok.Builder;
import lombok.Value;
import lombok.extern.jackson.Jacksonized;

@Value
@Builder
@Jacksonized
public class Customer {
    long id;
    String name;
    boolean active;
}
```

- `@Builder` sinh builder API.
- `@Value` tạo lớp theo hướng immutable với field final và getter.
- `@Jacksonized` bổ sung metadata Jackson cần để deserialize thông qua builder được Lombok sinh ra, bao gồm cấu hình builder prefix tương ứng.

Cần dùng phiên bản Lombok có hỗ trợ `@Jacksonized` và kiểm tra annotation được sinh ra nếu dự án có cấu hình builder tùy chỉnh. Khi builder dùng tên phương thức hoặc prefix riêng, hãy bảo đảm metadata Jackson do Lombok sinh ra phản ánh đúng convention đó.

Nếu không dùng Lombok, cấu hình `@JsonDeserialize` và `@JsonPOJOBuilder` thủ công như các ví dụ trước vẫn là cách trực tiếp và dễ kiểm soát.

## 11. Kiểm thử builder deserialization

Nên kiểm tra cả trường hợp JSON đầy đủ, thuộc tính tùy chọn bị thiếu, dữ liệu không hợp lệ và chiều serialize của object đã tạo.

Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class UserBuilderTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void createsImmutableObjectFromJson() throws Exception {
        User user = mapper.readValue(
            """
            {
              "id": 42,
              "name": "An",
              "active": false
            }
            """,
            User.class
        );

        assertEquals(42L, user.getId());
        assertEquals("An", user.getName());
        assertEquals(false, user.isActive());
    }

    @Test
    void keepsBuilderDefaultWhenOptionalPropertyIsMissing()
            throws Exception {
        User user = mapper.readValue(
            """
            {
              "id": 42,
              "name": "An"
            }
            """,
            User.class
        );

        assertEquals(true, user.isActive());
    }

    @Test
    void rejectsInvalidStateAtBuildTime() {
        assertThrows(
            Exception.class,
            () -> mapper.readValue(
                """
                {"id": 42, "name": ""}
                """,
                User.class
            )
        );
    }
}
```

Test thứ ba chỉ minh họa rằng lỗi từ bước tạo object được truyền ra ngoài quá trình deserialize; trong test thực tế, có thể kiểm tra chính xác exception Jackson bọc quanh lỗi validation theo phiên bản và cấu hình đang dùng.

Nên có thêm test serialize để xác nhận các getter của lớp đích tạo ra JSON đúng hợp đồng. Không nên chỉ kiểm tra rằng `readValue` không ném exception; cần xác nhận giá trị từng thuộc tính và trạng thái mặc định.

## 12. Lỗi thường gặp khi cấu hình builder

**Quên `@JsonDeserialize(builder = ...)`.** Jackson vẫn dùng cơ chế tạo object mặc định và có thể thất bại nếu lớp đích không có constructor/setter phù hợp.

**Quên `@JsonPOJOBuilder`.** Jackson áp dụng quy ước builder mặc định. Nếu method prefix hoặc tên build method khác mặc định, các method có thể không được nhận diện.

**Sai `withPrefix`.** Builder dùng `name(...)` nhưng annotation để mặc định `with`; Jackson không ánh xạ đúng mutator. Hãy dùng `withPrefix = ""` hoặc đổi tên method theo convention.

**Sai `buildMethodName`.** Builder có `create()` nhưng Jackson vẫn tìm `build()`. Khai báo đúng `buildMethodName = "create"`.

**Builder không thể được Jackson tạo.** Hãy bảo đảm builder class và constructor của nó có mức truy cập phù hợp. Một nested builder thường nên là `public static` và có constructor không tham số có thể truy cập.

**Mutator không trả về builder.** Fluent builder thường trả về `this`; nếu method trả về kiểu không phù hợp với mô hình builder hoặc không đúng signature mà Jackson nhận diện, hãy kiểm tra lại API mutator.

**Thiếu giá trị nhưng không có default hoặc validation.** Field primitive nhận giá trị mặc định như 0/false; field tham chiếu nhận null. Nếu đó không phải trạng thái hợp lệ, hãy kiểm tra trong build method và phát sinh lỗi có ngữ cảnh.

**Chỉ kiểm thử deserialize.** Builder annotation không tự bảo đảm serialization có cùng tên hoặc đủ property. Hãy kiểm tra riêng JSON đầu ra từ object đã tạo.

## 13. Ghi nhớ

- Dùng `@JsonDeserialize(builder = MyType.Builder.class)` trên lớp đích để Jackson tạo object thông qua builder.
- Dùng `@JsonPOJOBuilder` để cấu hình tiền tố mutator và tên phương thức hoàn tất.
- Mặc định builder dùng prefix `with` và build method `build`; fluent method không tiền tố cần `withPrefix = ""`.
- Builder có thể giữ trạng thái tạm, giá trị mặc định và validation trước khi tạo immutable object.
- `@JsonProperty` và `@JsonAlias` có thể đặt trên mutator để ánh xạ tên JSON chuẩn hoặc tên cũ.
- `@JsonDeserialize(builder = ...)` điều khiển chiều đọc; serialization vẫn dựa trên metadata của lớp đích.
- Với Lombok, kết hợp `@Builder` và `@Jacksonized` để sinh cấu hình tích hợp Jackson.

