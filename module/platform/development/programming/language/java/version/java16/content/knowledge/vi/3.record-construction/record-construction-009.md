# Constructor bổ sung và yêu cầu ủy quyền bằng this

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá các cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này giải thích constructor bổ sung (non-canonical constructor), yêu cầu ủy quyền đến canonical constructor và thay đổi quan trọng của Java 25 về vị trí câu lệnh `this(...)`.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt canonical constructor với constructor bổ sung của record.
- Giải thích vì sao mọi constructor không phải canonical phải ủy quyền bằng `this(...)` đến một constructor khác của cùng record.
- Tổ chức chuỗi overload sao cho cuối cùng đi đến canonical constructor.
- Dùng constructor bổ sung để cung cấp giá trị mặc định hoặc chuyển đổi dạng đầu vào.
- Nhận diện chu trình ủy quyền và các trường hợp gọi `super(...)` không hợp lệ.
- Áp dụng đúng quy tắc theo phiên bản Java: từ Java 25, các câu lệnh hợp lệ có thể xuất hiện trước `this(...)`.
- Tránh truy cập đối tượng đang được tạo trong phần mã chạy trước lời gọi constructor.

## 1. Canonical constructor và constructor bổ sung

Record mô tả dữ liệu bằng các component trong record header:

```java
public record UserProfile(String username, int age) {}
```

Với khai báo này, canonical constructor (constructor chuẩn) có chữ ký tương ứng với `UserProfile(String username, int age)`. Nếu không khai báo constructor tường minh, compiler tự sinh canonical constructor để khởi tạo tất cả component field.

Bạn có thể tự khai báo canonical constructor dạng đầy đủ:

```java
public record UserProfile(String username, int age) {
    public UserProfile(String username, int age) {
        this.username = username;
        this.age = age;
    }
}
```

Hoặc dạng compact:

```java
public record UserProfile(String username, int age) {
    public UserProfile {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username is required");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

Ngoài canonical constructor, record có thể khai báo constructor với danh sách tham số khác. Những constructor đó được gọi là **non-canonical constructor** hoặc constructor bổ sung.

Ví dụ:

```java
public record UserProfile(String username, int age) {
    public UserProfile(String username) {
        this(username, 0);
    }
}
```

Constructor `UserProfile(String username)` là constructor bổ sung vì nó không có danh sách tham số tương ứng toàn bộ component trong header. Nó cung cấp cách khởi tạo tiện lợi khi người gọi chỉ có username.

## 2. Yêu cầu bắt buộc: constructor bổ sung phải ủy quyền bằng this(...)

Mọi constructor không phải canonical trong record đều phải chứa một **alternate constructor invocation** bằng `this(...)`. Lời gọi này chuyển quá trình khởi tạo sang một constructor khác của chính record.

Mỗi thân constructor chỉ có tối đa một constructor invocation. Vì vậy, không thể đặt nhiều lời gọi `this(...)` trong các nhánh `if` để chọn đường khởi tạo; hãy tính toán đối số trong phần prologue rồi thực hiện một lời gọi ủy quyền.

Ví dụ hợp lệ:

```java
public record UserProfile(String username, int age) {

    public UserProfile(String username) {
        this(username, 0);
    }
}
```

Lệnh `this(username, 0)` gọi canonical constructor `UserProfile(String username, int age)`. Canonical constructor chịu trách nhiệm khởi tạo component field và thực hiện các quy tắc xác thực dữ liệu.

Constructor bổ sung không được tự gán component field để thay thế việc ủy quyền:

```java
// SAI: constructor bổ sung không thể tự khởi tạo component field.
public record UserProfile(String username, int age) {
    public UserProfile(String username) {
        this.username = username;
        this.age = 0;
    }
}
```

Đoạn mã sai vì constructor bổ sung không gọi constructor khác bằng `this(...)`. Component field của record là `private final` và được khởi tạo qua canonical constructor.

Quy tắc này giúp mọi đường tạo đối tượng đều đi qua cùng một cơ chế khởi tạo chuẩn. Nhờ đó, các bất biến đặt trong canonical constructor được áp dụng nhất quán.

## 3. Chuỗi ủy quyền phải kết thúc ở canonical constructor

Một record có thể có nhiều overload. Một constructor bổ sung có thể gọi canonical constructor trực tiếp hoặc gọi một constructor bổ sung khác. Dù tổ chức theo cách nào, chuỗi gọi phải kết thúc ở canonical constructor.

Ví dụ:

```java
public record ConnectionConfig(
        String host,
        int port,
        boolean secure
) {
    public ConnectionConfig {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host is required");
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
        host = host.strip();
    }

    public ConnectionConfig(String host, int port) {
        this(host, port, true);
    }

    public ConnectionConfig(String host) {
        this(host, 443);
    }

    public ConnectionConfig() {
        this("localhost");
    }
}
```

Chuỗi ủy quyền:

```text
new ConnectionConfig()
        |
        v
ConnectionConfig(String host)
        |
        v
ConnectionConfig(String host, int port)
        |
        v
ConnectionConfig(String host, int port, boolean secure)
        |
        v
canonical constructor
```

Khi gọi `new ConnectionConfig()`:

1. Constructor không tham số gọi `this("localhost")`.
2. Constructor một tham số gọi `this(host, 443)`.
3. Constructor hai tham số gọi `this(host, port, true)`.
4. Canonical constructor xác thực dữ liệu và khởi tạo component field.
5. Sau khi constructor được ủy quyền hoàn tất, phần thân còn lại của constructor gọi nó (nếu có) mới tiếp tục chạy.

Các constructor bổ sung nên tập trung vào việc cung cấp giá trị mặc định hoặc chuyển đổi đầu vào. Quy tắc bất biến chung nên đặt trong canonical constructor.

## 4. Vị trí của this(...): quy tắc Java 16 và thay đổi Java 25

Đây là điểm cần chú ý khi học record từ Java 16 nhưng viết code cho Java hiện đại.

**Trước Java 25**, nếu constructor có lời gọi `this(...)` thì lời gọi đó phải là câu lệnh đầu tiên trong thân constructor. Vì thế, đoạn mã dưới đây không hợp lệ với quy tắc ngôn ngữ Java 16 đến Java 24 ở chế độ phát hành thông thường:

```java
// Không hợp lệ khi biên dịch theo ngôn ngữ Java 16 đến Java 24.
public record UserId(String value) {
    public UserId(long id) {
        if (id < 0) {
            throw new IllegalArgumentException("id must be non-negative");
        }
        this(Long.toString(id));
    }
}
```

Từ **Java 25**, tính năng *Flexible Constructor Bodies* được hoàn thiện qua JEP 513. Constructor có thể chứa một số câu lệnh hợp lệ trước lời gọi `this(...)` hoặc `super(...)`. Với record, constructor bổ sung vẫn phải ủy quyền bằng `this(...)`; thay đổi nằm ở chỗ phần mã chuẩn bị (prologue) có thể xuất hiện trước lời gọi đó.

Ví dụ hợp lệ từ Java 25:

```java
public record UserId(String value) {

    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        value = value.strip();
    }

    public UserId(long id) {
        if (id < 0) {
            throw new IllegalArgumentException("id must be non-negative");
        }

        this(Long.toString(id));
    }
}
```

Trong constructor `UserId(long id)`:

- Điều kiện kiểm tra `id` chạy trước.
- Nếu `id` âm, constructor ném ngoại lệ và không tiếp tục ủy quyền.
- Nếu hợp lệ, `this(Long.toString(id))` gọi canonical constructor.
- Canonical constructor tiếp tục kiểm tra và chuẩn hóa giá trị `String`.

Đối với dự án cần tương thích Java 16 đến Java 24, hãy đặt `this(...)` ở đầu constructor hoặc dùng helper static bên trong đối số. Nếu dự án biên dịch bằng Java 25 trở lên, có thể sử dụng phần mã chuẩn bị trước lời gọi theo các giới hạn của early construction context. Tính năng này từng ở dạng preview trong một số bản Java trước 25; bài này sử dụng cú pháp đã được hoàn thiện, không yêu cầu bật preview.

## 5. Early construction context: được làm gì trước this(...)?

Các câu lệnh trước `this(...)` trong Java 25+ thuộc **early construction context**. Chúng được phép xử lý dữ liệu đầu vào và chuẩn bị đối số, nhưng không được truy cập instance đang được tạo.

Có thể thực hiện:

- Kiểm tra tham số constructor.
- Ném ngoại lệ nếu đầu vào không hợp lệ.
- Khai báo và gán biến cục bộ.
- Tính toán giá trị từ tham số.
- Gọi phương thức `static` hoặc dùng hằng static.
- Đọc và xử lý một đối tượng khác được truyền vào như tham số.

Không được:

- Dùng `this` để tham chiếu instance đang tạo.
- Đọc hoặc ghi component field của record đang tạo.
- Gọi phương thức instance của record đang tạo.
- Dùng `super` để truy cập trạng thái hoặc hành vi instance trong phần mã chuẩn bị.

Ví dụ hợp lệ:

```java
public record Dimensions(double width, double height) {
    public Dimensions(Pair<Double> pair) {
        java.util.Objects.requireNonNull(pair, "pair");

        double w = java.util.Objects.requireNonNull(
                pair.first(), "pair.first"
        );
        double h = java.util.Objects.requireNonNull(
                pair.second(), "pair.second"
        );

        this(w, h);
    }

    public Dimensions {
        if (!Double.isFinite(width) || width <= 0) {
            throw new IllegalArgumentException("width must be positive and finite");
        }
        if (!Double.isFinite(height) || height <= 0) {
            throw new IllegalArgumentException("height must be positive and finite");
        }
    }
}

record Pair<T>(T first, T second) {}
```

Phần trước `this(w, h)` chỉ làm việc với tham số `pair` và biến cục bộ `w`, `h`. Nó không truy cập instance `Dimensions` đang được tạo. Sau lời gọi, canonical constructor xác thực miền giá trị và khởi tạo field.

Ví dụ không hợp lệ:

```java
// SAI trong early construction context.
public record UserId(String value) {
    public UserId(long id) {
        System.out.println(this);
        this(Long.toString(id));
    }
}
```

Lệnh `System.out.println(this)` truy cập đối tượng đang được tạo trước khi ủy quyền. Java không cho phép thao tác này trong phần mã trước `this(...)`.

## 6. Có thể dùng biến cục bộ để chuẩn bị đối số

Java 25+ cho phép khai báo biến cục bộ trước lời gọi constructor. Điều này hữu ích khi đầu vào cần chuyển đổi qua nhiều bước.

Ví dụ chuyển chuỗi thành số tiền:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal amount, String currency) {

    public Money {
        amount = Objects.requireNonNull(amount, "amount");

        currency = Objects.requireNonNull(currency, "currency")
                .strip()
                .toUpperCase(java.util.Locale.ROOT);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
        if (currency.isEmpty()) {
            throw new IllegalArgumentException("currency is required");
        }
    }

    public Money(String amountText, String currency) {
        Objects.requireNonNull(amountText, "amountText");

        BigDecimal parsed;
        try {
            parsed = new BigDecimal(amountText.strip());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("invalid amount", ex);
        }

        this(parsed, currency);
    }
}
```

Constructor `Money(String amountText, String currency)` thực hiện các bước:

1. Kiểm tra `amountText` không null.
2. Phân tích chuỗi thành `BigDecimal` và xử lý lỗi định dạng.
3. Lưu kết quả vào biến cục bộ `parsed`.
4. Gọi `this(parsed, currency)` để ủy quyền đến canonical constructor.
5. Canonical constructor kiểm tra và chuẩn hóa các component.

Ví dụ này sử dụng cú pháp prologue của Java 25+. Nếu cần tương thích Java 16 đến Java 24, hãy chuyển phần phân tích sang helper static được gọi trực tiếp trong đối số `this(...)`.

## 7. Cách viết tương thích Java 16: dùng helper static

Trước Java 25, bạn vẫn có thể kiểm tra hoặc chuyển đổi dữ liệu trước khi ủy quyền bằng cách đặt lời gọi helper static trong đối số của `this(...)`.

Ví dụ:

```java
public record UserId(String value) {

    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        value = value.strip();
    }

    public UserId(long id) {
        this(toValue(id));
    }

    private static String toValue(long id) {
        if (id < 0) {
            throw new IllegalArgumentException("id must be non-negative");
        }
        return Long.toString(id);
    }
}
```

Lời gọi `this(toValue(id))` vẫn là câu lệnh đầu tiên. Phương thức static xử lý dữ liệu trước khi constructor canonical được gọi.

Cách này vẫn hợp lệ trong Java hiện đại và phù hợp khi code cần chạy trên nhiều phiên bản Java. Khi dùng Java 25+, bạn có thêm lựa chọn viết phần kiểm tra hoặc chuyển đổi trực tiếp trong prologue.

## 8. Constructor bổ sung có thể cung cấp giá trị mặc định

Một mục đích phổ biến của overload là cho phép người gọi bỏ qua component có giá trị mặc định.

Ví dụ:

```java
public record PageRequest(int page, int size, String sort) {

    public PageRequest {
        if (page < 1) {
            throw new IllegalArgumentException("page must be >= 1");
        }
        if (size < 1 || size > 200) {
            throw new IllegalArgumentException("size must be between 1 and 200");
        }
        if (sort == null || sort.isBlank()) {
            throw new IllegalArgumentException("sort is required");
        }
        sort = sort.strip();
    }

    public PageRequest(int page, int size) {
        this(page, size, "createdAt");
    }

    public PageRequest(int page) {
        this(page, 20);
    }

    public PageRequest() {
        this(1);
    }
}
```

Sử dụng:

```java
PageRequest firstPage = new PageRequest();
PageRequest customSize = new PageRequest(2, 50);
PageRequest customSort = new PageRequest(3, 25, "name");

System.out.println(firstPage);
// PageRequest[page=1, size=20, sort=createdAt]
```

Các constructor bổ sung tạo giá trị mặc định rồi ủy quyền đến canonical constructor. Vì vậy, các kiểm tra `page`, `size` và `sort` vẫn được áp dụng cho tất cả cách khởi tạo.

Một record có component vẫn có canonical constructor, không tự động có constructor không tham số như một class thông thường. Nếu muốn `new PageRequest()`, bạn phải tự khai báo overload không tham số và ủy quyền như ví dụ trên.

## 9. Constructor bổ sung có thể chuyển đổi kiểu đầu vào

Overload cũng hữu ích khi API muốn nhận kiểu dữ liệu khác với kiểu component, sau đó chuyển đổi về dạng record chuẩn.

Ví dụ:

```java
import java.util.Objects;

public record UserName(String value) {

    public UserName {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value is required");
        }
    }

    public UserName(CharSequence input) {
        this(input == null ? null : input.toString());
    }
}
```

Constructor `UserName(CharSequence input)` chuyển đầu vào thành `String` rồi ủy quyền đến canonical constructor. Nếu đầu vào null, canonical constructor từ chối theo chính sách dữ liệu của record.

Một ví dụ khác nhận số:

```java
public record UserId(String value) {
    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        value = value.strip();
    }

    public UserId(long numericId) {
        this(Long.toString(numericId));
    }
}
```

Hai constructor nhận hai dạng đầu vào khác nhau. Constructor số chuyển đổi thành chuỗi rồi gọi canonical constructor, nơi quy tắc dữ liệu được áp dụng tập trung.

## 10. Không tạo chuỗi ủy quyền vòng lặp

Constructor bổ sung có thể gọi constructor bổ sung khác, nhưng chuỗi phải kết thúc ở canonical constructor. Nếu các constructor gọi lẫn nhau tạo thành chu trình, compiler báo lỗi.

Ví dụ sai:

```java
// SAI: hai constructor bổ sung gọi vòng lặp lẫn nhau.
public record Token(String value, int version, boolean active) {

    public Token(String value) {
        this(value, 1);
    }

    public Token(String value, int version) {
        this(value);
    }
}
```

Ở đây:

- `Token(String value)` gọi `Token(String value, int version)`.
- `Token(String value, int version)` gọi ngược lại `Token(String value)`.
- Không constructor nào đi đến canonical constructor `Token(String value, int version, boolean active)`.

Cách sửa:

```java
public record Token(String value, int version, boolean active) {

    public Token {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        if (version < 1) {
            throw new IllegalArgumentException("version must be positive");
        }
    }

    public Token(String value) {
        this(value, 1, true);
    }

    public Token(String value, int version) {
        this(value, version, true);
    }
}
```

Cả hai constructor bổ sung đều gọi thẳng canonical constructor, do đó không có chu trình.

## 11. Constructor record không được gọi super(...)

Record có superclass trực tiếp là `java.lang.Record`. Tuy nhiên, constructor của record không được khai báo lời gọi `super(...)`. Với constructor bổ sung, quy tắc yêu cầu dùng `this(...)` để chuyển đến constructor khác của cùng record.

Ví dụ sai:

```java
// SAI: constructor bổ sung của record không được gọi super(...).
public record Tag(String value) {
    public Tag() {
        super();
    }
}
```

Cách đúng:

```java
public record Tag(String value) {
    public Tag() {
        this("default");
    }
}
```

Lời gọi `this("default")` chuyển việc khởi tạo về canonical constructor `Tag(String value)`. Quan hệ với superclass `java.lang.Record` được Java xử lý theo quy tắc riêng của record.

## 12. Không lặp validation trong mọi overload

Một thiết kế không tốt là sao chép cùng một quy tắc xác thực vào từng constructor bổ sung. Khi yêu cầu thay đổi, các bản sao có thể không còn đồng nhất.

Hãy đặt bất biến chung ở canonical constructor:

```java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        value = value.strip();
    }

    public EmailAddress(CharSequence input) {
        this(input == null ? null : input.toString());
    }

    public EmailAddress() {
        this("guest@example.com");
    }
}
```

Các overload chỉ chuyển đổi kiểu hoặc cung cấp giá trị mặc định. Canonical constructor là nơi xác thực và chuẩn hóa component, vì vậy mọi đường khởi tạo đều có cùng chính sách.

Có thể dùng prologue Java 25+ cho những điều kiện đặc thù của một dạng đầu vào. Tuy nhiên, các bất biến áp dụng cho mọi cách tạo record vẫn nên được kiểm tra trong canonical constructor.

## 13. Khi nào nên dùng overload, khi nào nên dùng static factory?

Không nên tạo overload chỉ để tăng số lượng cách khởi tạo. Mỗi constructor bổ sung nên giải quyết một nhu cầu API cụ thể.

| Nhu cầu | Cách thiết kế |
| --- | --- |
| Cung cấp giá trị mặc định đơn giản | Overload gọi `this(...)` với giá trị mặc định. |
| Nhận kiểu đầu vào khác | Chuyển đổi rồi ủy quyền đến canonical constructor. |
| Rút gọn lời gọi thường gặp | Thêm overload có chữ ký rõ ràng. |
| Chọn một cấu hình theo ý nghĩa nghiệp vụ | Cân nhắc static factory có tên mô tả. |
| Giữ validation nhất quán | Tập trung bất biến trong canonical constructor. |

Nếu nhiều cách khởi tạo có ý nghĩa riêng, factory method có tên như `of(...)`, `from(...)` hoặc `defaultConfig()` có thể dễ đọc hơn overload.

Ví dụ:

```java
public record ServerPort(int value) {

    public ServerPort {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
    }

    public static ServerPort http() {
        return new ServerPort(80);
    }

    public static ServerPort https() {
        return new ServerPort(443);
    }
}
```

Factory method không thay thế constructor chuẩn; chúng gọi constructor để tạo record đã được xác thực. Ưu điểm là tên phương thức mô tả mục đích sử dụng rõ ràng.

## 14. Kiểm thử constructor bổ sung

Hãy kiểm thử giá trị mà từng overload tạo ra và xác nhận canonical validation vẫn được áp dụng.

Ví dụ với JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PageRequestTest {

    @Test
    void noArgConstructorUsesDefaults() {
        PageRequest request = new PageRequest();

        assertEquals(1, request.page());
        assertEquals(20, request.size());
        assertEquals("createdAt", request.sort());
    }

    @Test
    void overloadStillUsesCanonicalValidation() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new PageRequest(0)
        );
    }
}
```

Các trường hợp nên kiểm tra:

- Mỗi overload tạo đúng component value mong đợi.
- Giá trị mặc định được truyền đúng.
- Đầu vào được chuyển đổi chính xác.
- Dữ liệu không hợp lệ vẫn bị canonical constructor từ chối.
- Prologue trước `this(...)` chỉ sử dụng tham số, biến cục bộ và thành phần static.
- Chuỗi ủy quyền không tạo vòng lặp.
- Không có constructor bổ sung nào tự khởi tạo component field.

## 15. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Constructor bổ sung không chứa `this(...)` | Không đáp ứng quy tắc non-canonical constructor của record. | Ủy quyền đến constructor khác cùng record. |
| Gọi `super(...)` trong record constructor | Record constructor không được gọi superclass constructor tường minh. | Dùng `this(...)` trong constructor bổ sung. |
| Gán trực tiếp component field trong overload | Constructor bổ sung phải ủy quyền; field được canonical constructor khởi tạo. | Chuyển giá trị qua `this(...)`. |
| Tạo chuỗi `this(...)` gọi vòng lặp | Compiler không tìm được đường khởi tạo kết thúc. | Thiết kế chuỗi kết thúc ở canonical constructor. |
| Dùng `this` hoặc instance field trước `this(...)` trong Java 25+ | Vi phạm giới hạn early construction context. | Chỉ xử lý tham số và dữ liệu độc lập với instance. |
| Cho rằng `this(...)` luôn phải là câu lệnh đầu tiên | Quy tắc này đã thay đổi trong Java 25. | Dùng quy tắc tương ứng với source level của dự án. |
| Lặp validation ở từng overload | Các đường khởi tạo có thể áp dụng chính sách khác nhau. | Đặt bất biến chung trong canonical constructor. |
| Dùng overload cho nhiều lựa chọn có tên nghiệp vụ | Chữ ký constructor có thể khó hiểu. | Cân nhắc static factory có tên rõ nghĩa. |

## 16. Bài tập tự luyện

### Bài 1: Hoàn thiện constructor mặc định

Cho record:

```java
public record RetryPolicy(int maxAttempts, long delayMillis) {}
```

Viết constructor không tham số dùng `maxAttempts = 3` và `delayMillis = 500`.

**Đáp án:**

```java
public record RetryPolicy(int maxAttempts, long delayMillis) {
    public RetryPolicy() {
        this(3, 500);
    }
}
```

Lời gọi `this(3, 500)` ủy quyền đến canonical constructor.

### Bài 2: Sửa constructor bổ sung

Đoạn mã sau không hợp lệ theo quy tắc Java 16 đến Java 24:

```java
public record UserId(String value) {
    public UserId(long id) {
        if (id < 0) {
            throw new IllegalArgumentException("id must be non-negative");
        }
        this(Long.toString(id));
    }
}
```

**Đáp án cho Java 16 đến Java 24:**

```java
public record UserId(String value) {
    public UserId(long id) {
        this(toValue(id));
    }

    private static String toValue(long id) {
        if (id < 0) {
            throw new IllegalArgumentException("id must be non-negative");
        }
        return Long.toString(id);
    }
}
```

**Đáp án cho Java 25 trở lên:** có thể giữ phần kiểm tra tham số trước `this(...)`, vì flexible constructor bodies đã trở thành tính năng chính thức.

### Bài 3: Xác định chuỗi ủy quyền

Với record `Config(String host, int port, boolean tls)`:

- `Config()` gọi `this("localhost")`.
- `Config(String host)` gọi `this(host, 443)`.
- `Config(String host, int port)` gọi `this(host, port, true)`.

Chuỗi ủy quyền kết thúc ở constructor nào?

**Đáp án:** Canonical constructor `Config(String, int, boolean)`. Các constructor bổ sung chỉ chuyển giá trị và không tự gán field.

### Bài 4: Phân biệt prologue hợp lệ

Với Java 25 trở lên, đoạn mã nào hợp lệ trong constructor bổ sung?

**A**

```java
public record Tag(String value) {
    public Tag(String value, boolean trim) {
        if (value == null) {
            throw new IllegalArgumentException("value is required");
        }
        this(trim ? value.strip() : value);
    }
}
```

**B**

```java
public record Tag(String value) {
    public Tag(String value, boolean trim) {
        System.out.println(this);
        this(trim ? value.strip() : value);
    }
}
```

**Đáp án:** A hợp lệ vì phần prologue chỉ đọc tham số và kiểm tra dữ liệu. B không hợp lệ vì truy cập `this` trước lời gọi ủy quyền.

## Ghi nhớ

Mọi constructor bổ sung của record phải ủy quyền đến constructor khác cùng record bằng `this(...)`, và chuỗi gọi phải kết thúc ở canonical constructor. Không được dùng `super(...)` hoặc tự khởi tạo component field trong constructor bổ sung. Từ Java 25, nhờ Flexible Constructor Bodies, bạn có thể đặt phần kiểm tra và chuẩn bị dữ liệu trước `this(...)`, nhưng phần mã này không được truy cập instance đang được tạo. Khi cần tương thích Java 16 đến Java 24, giữ `this(...)` ở đầu constructor hoặc dùng helper static trong đối số.

## Tài liệu tham khảo

- [Java Language Specification — Java SE 26, `8.10.4` Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10.4).
- [Java Language Specification — Java SE 26, `8.8.7` Constructor Body](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.8.7).
- [Oracle Java 26 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/26/language/flexible-constructor-bodies.html).
- [JEP 513 — Flexible Constructor Bodies (hoàn thiện trong Java 25)](https://openjdk.org/jeps/513).
- [Java Language Specification — Java SE 16, `8.10.4` Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html#jls-8.10.4).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
