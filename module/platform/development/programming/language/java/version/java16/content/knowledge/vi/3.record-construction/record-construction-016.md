# Kiểm chứng mọi đường tạo đối tượng đều bảo toàn invariant của record

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá những cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record` và cách áp dụng ổn định trong thiết kế API. Bài này tập trung kiểm chứng rằng mọi đường tạo record được hỗ trợ đều đi qua canonical constructor và tuân thủ cùng một bộ invariant.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích invariant của record và vai trò của canonical constructor.
- Phân biệt canonical constructor tường minh, compact constructor và constructor do compiler sinh.
- Kiểm tra constructor bổ sung luôn ủy quyền đến constructor khác của cùng record bằng `this(...)`.
- Thiết kế static factory để chuyển đổi đầu vào mà vẫn giữ validation chung.
- Hiểu cách reflection và Java Serialization tạo record.
- Viết test xác nhận các đường tạo hợp lệ và không hợp lệ cùng tuân thủ invariant.
- Phân biệt invariant tại thời điểm khởi tạo với trạng thái có thể thay đổi sau đó do component mutable.

## 1. Invariant của record là gì?

**Invariant** là tập hợp điều kiện mà một đối tượng phải thỏa mãn để được xem là hợp lệ. Với record, invariant thường liên quan đến:

- Miền giá trị của từng component.
- Component tham chiếu bắt buộc khác null.
- Quan hệ giữa nhiều component.
- Quy tắc chuẩn hóa dữ liệu trước khi lưu.
- Cấu trúc collection hoặc dữ liệu được sao chép phòng vệ.

Ví dụ, một record biểu diễn phần trăm có thể yêu cầu giá trị nằm trong khoảng từ 0 đến 100:

```java
public record Percentage(int value) {

    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "value must be between 0 and 100"
            );
        }
    }
}
```

Sau khi tạo thành công, mọi đối tượng `Percentage` phải có `value` nằm trong miền hợp lệ. Điều kiện này là invariant của record.

Nếu validation chỉ nằm trong một static factory nhưng canonical constructor không kiểm tra, người gọi vẫn có thể tạo dữ liệu sai bằng `new Percentage(...)`. Vì vậy, cần xác định một điểm bảo vệ chung cho mọi đường khởi tạo.

## 2. Canonical constructor là điểm bảo vệ invariant chung

Canonical constructor có danh sách tham số tương ứng với toàn bộ component trong record header. Mọi component được khởi tạo thông qua constructor này.

Có hai cách khai báo canonical constructor:

- **Compact constructor:** viết phần kiểm tra hoặc chuẩn hóa mà không khai báo lại danh sách tham số và không gán trực tiếp vào field.
- **Canonical constructor tường minh:** khai báo đầy đủ tham số và gán giá trị cho từng component field.

Ví dụ compact constructor:

```java
import java.util.Objects;

public record UserName(String value) {

    public UserName {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                    "value must not be blank"
            );
        }
    }
}
```

Compiler gán các tham số sau khi compact constructor kết thúc bình thường vào component field. Nếu validation ném ngoại lệ, đối tượng không được tạo thành công.

Cùng hợp đồng có thể được viết bằng canonical constructor tường minh:

```java
import java.util.Objects;

public record UserName(String value) {

    public UserName(String value) {
        String normalized = Objects.requireNonNull(
                value, "value"
        ).strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    "value must not be blank"
            );
        }

        this.value = normalized;
    }
}
```

Cả hai cách đều bảo vệ cùng một invariant. Hãy chọn cách dễ đọc và tránh duy trì hai bộ validation khác nhau cho cùng một record.

### Canonical constructor do compiler sinh

Nếu không khai báo constructor nào, compiler sinh canonical constructor với hành vi gán component tương ứng. Nó không tự thêm quy tắc nghiệp vụ.

Ví dụ:

```java
public record Percentage(int value) {}
```

Đoạn mã này cho phép tạo `new Percentage(-1)` vì không có validation miền giá trị. Nếu record có invariant, hãy khai báo compact hoặc canonical constructor tường minh để thực thi nó.

## 3. Đường tạo trực tiếp bằng new

Đường tạo cơ bản là gọi canonical constructor trực tiếp:

```java
Percentage valid = new Percentage(75);
Percentage invalid = new Percentage(150);
```

Dòng đầu tạo record thành công; dòng thứ hai ném `IllegalArgumentException`.

Test cần xác nhận cả hai hành vi:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PercentageTest {

    @Test
    void acceptsValueInsideRange() {
        Percentage percentage = new Percentage(75);

        assertEquals(75, percentage.value());
    }

    @Test
    void rejectsValueOutsideRange() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Percentage(150)
        );
    }
}
```

Đây là test nền tảng cho invariant. Các đường tạo khác cần được kiểm tra để chắc chắn chúng không bỏ qua hoặc thay đổi quy tắc này.

## 4. Constructor bổ sung phải ủy quyền về cùng record

Record có thể khai báo constructor bổ sung để cung cấp giá trị mặc định hoặc nhận dạng đầu vào khác.

Một constructor không phải canonical phải có lời gọi constructor khác của chính record bằng `this(...)`. Chuỗi ủy quyền cuối cùng phải đi đến canonical constructor.

Trong Java 16 đến Java 24, lời gọi `this(...)` phải đứng đầu thân constructor. Từ Java 25, Flexible Constructor Bodies (JEP 513) cho phép một phần prologue bị giới hạn xuất hiện trước lời gọi này. Quy tắc ủy quyền của constructor bổ sung trong record vẫn còn nguyên: nó phải gọi constructor khác của cùng record và chuỗi đó phải kết thúc ở canonical constructor. Ví dụ trong bài giữ `this(...)` ở đầu để tương thích từ Java 16 và dễ nhìn thấy đường ủy quyền.

Ví dụ:

```java
import java.util.Objects;

public record RetryPolicy(int maxAttempts, String name) {

    public RetryPolicy {
        name = Objects.requireNonNull(name, "name").strip();

        if (maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException(
                    "maxAttempts must be between 1 and 10"
            );
        }

        if (name.isEmpty()) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }
    }

    public RetryPolicy(int maxAttempts) {
        this(maxAttempts, "default");
    }

    public RetryPolicy() {
        this(3);
    }
}
```

Luồng khởi tạo:

1. `new RetryPolicy()` gọi constructor không tham số.
2. Constructor không tham số gọi `this(3)`.
3. Constructor một tham số gọi `this(maxAttempts, "default")`.
4. Canonical constructor kiểm tra cả hai component và hoàn tất việc khởi tạo.

Không constructor bổ sung nào tự gán field hoặc bỏ qua validation chung.

### Chuỗi ủy quyền phải kết thúc ở canonical constructor

Hai constructor bổ sung không được gọi vòng lặp. Ví dụ dưới đây không biên dịch vì hai constructor gọi lẫn nhau và không có đường đến canonical constructor:

```java
public record RetryPolicy(int maxAttempts, String name) {

    public RetryPolicy(int maxAttempts) {
        this("default");
    }

    public RetryPolicy(String name) {
        this(3);
    }
}
```

Hãy thiết kế mọi đường ủy quyền sao cho cuối cùng đi đến canonical constructor, không tạo chu trình.

## 5. Chuyển đổi đầu vào trong constructor bổ sung

Một constructor bổ sung có thể nhận kiểu đầu vào khác với component và chuyển đổi trước khi ủy quyền. Với cú pháp tương thích Java 16, lời gọi `this(...)` đứng đầu thân constructor.

Ví dụ:

```java
import java.util.Locale;
import java.util.Objects;

public record UserId(String value) {

    public UserId {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("U-[1-9][0-9]*")) {
            throw new IllegalArgumentException(
                    "value must match U-<positive-number>"
            );
        }
    }

    public UserId(long numericId) {
        this(fromNumericId(numericId));
    }

    private static String fromNumericId(long numericId) {
        if (numericId <= 0) {
            throw new IllegalArgumentException(
                    "numericId must be positive"
            );
        }

        return "U-" + numericId;
    }
}
```

Constructor nhận `long` chuyển đầu vào thành chuỗi bằng helper `static` rồi ủy quyền đến canonical constructor. Canonical constructor tiếp tục chuẩn hóa và xác thực định dạng cuối cùng.

Helper có thể kiểm tra điều kiện đặc thù của kiểu nguồn, nhưng invariant của component vẫn nên được bảo vệ ở canonical constructor. Nhờ vậy, lời gọi `new UserId("invalid")` cũng bị từ chối như lời gọi `new UserId(0L)`.

Không truy cập trạng thái instance trước khi constructor được ủy quyền. Trong constructor bổ sung, hãy thực hiện chuyển đổi trước `this(...)` bằng biểu thức hoặc lời gọi helper tĩnh phù hợp.

## 6. Static factory cũng phải đi qua canonical constructor

Static factory giúp đặt tên có ý nghĩa cho từng cách tạo, ví dụ `of`, `parse`, `from` hoặc tên nghiệp vụ. Khi cần tạo instance mới, factory gọi constructor của record; nếu factory trả về instance đã tồn tại, instance đó cũng phải được tạo từ một đường khởi tạo bảo vệ invariant.

Ví dụ mở rộng `UserId`:

```java
import java.util.Locale;
import java.util.Objects;

public record UserId(String value) {

    public UserId {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("U-[1-9][0-9]*")) {
            throw new IllegalArgumentException(
                    "value must match U-<positive-number>"
            );
        }
    }

    public UserId(long numericId) {
        this(fromNumericId(numericId));
    }

    private static String fromNumericId(long numericId) {
        if (numericId <= 0) {
            throw new IllegalArgumentException(
                    "numericId must be positive"
            );
        }
        return "U-" + numericId;
    }

    public static UserId of(String value) {
        return new UserId(value);
    }

    public static UserId parse(String text) {
        text = Objects.requireNonNull(text, "text").strip();

        String prefix = "user:";
        if (!text.startsWith(prefix)) {
            throw new IllegalArgumentException(
                    "text must start with user:"
            );
        }

        return new UserId(text.substring(prefix.length()));
    }
}
```

Các đường tạo:

```java
UserId direct = new UserId("u-42");
UserId converted = new UserId(42L);
UserId named = UserId.of("U-42");
UserId parsed = UserId.parse("user:u-42");
```

Cả bốn đường đều kết thúc ở canonical constructor. Kết quả được chuẩn hóa thành `U-42` và phải thỏa cùng một biểu thức định dạng.

Factory không nên lặp toàn bộ validation chung rồi bỏ qua constructor. Nếu factory tạo record bằng `new UserId(...)`, canonical constructor vẫn là nơi bảo vệ trạng thái cuối cùng.

## 7. Kiểm thử mọi đường tạo hợp lệ và không hợp lệ

Một bộ test nên liệt kê các đường tạo được API công khai hỗ trợ và xác nhận chúng cùng tuân thủ invariant.

Ví dụ JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class UserIdTest {

    @Test
    void allCreationPathsProduceNormalizedValue() {
        assertEquals("U-42", new UserId("u-42").value());
        assertEquals("U-42", new UserId(42L).value());
        assertEquals("U-42", UserId.of(" U-42 ").value());
        assertEquals("U-42", UserId.parse("user:u-42").value());
    }

    @Test
    void allCreationPathsRejectInvalidValues() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new UserId("invalid")
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new UserId(0L)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> UserId.of("invalid")
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> UserId.parse("user:invalid")
        );
    }

    @Test
    void rejectsNullAtRequiredReferenceBoundaries() {
        assertThrows(
                NullPointerException.class,
                () -> new UserId((String) null)
        );

        assertThrows(
                NullPointerException.class,
                () -> UserId.parse(null)
        );
    }
}
```

Các test kiểm tra kết quả qua accessor công khai. Chúng không phụ thuộc cách compiler lưu component hoặc tên biến nội bộ.

Nếu một factory có quy tắc riêng về cú pháp, hãy test riêng quy tắc đó. Ví dụ `parse` phải từ chối văn bản không có tiền tố `user:`, trong khi `of` nhận trực tiếp dạng component. Các quy tắc nguồn riêng không thay thế validation cuối cùng của canonical constructor.

## 8. Reflection vẫn gọi constructor của record

Reflection có thể lấy constructor và gọi `newInstance(...)`. Đây vẫn là lời gọi constructor Java, nên canonical constructor thực thi validation như khi gọi `new` trực tiếp.

Ví dụ:

```java
import java.lang.reflect.Constructor;

Constructor<UserId> constructor =
        UserId.class.getDeclaredConstructor(String.class);

UserId id = constructor.newInstance("u-42");
```

Nếu canonical constructor ném ngoại lệ khi được gọi bằng reflection, reflection bọc ngoại lệ do constructor ném trong `InvocationTargetException`. Caller cần xem `getCause()` để biết nguyên nhân gốc.

Ví dụ test:

```java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

import org.junit.jupiter.api.Test;

class UserIdReflectionTest {

    @Test
    void reflectiveConstructionStillRunsCanonicalValidation()
            throws NoSuchMethodException {

        Constructor<UserId> constructor =
                UserId.class.getDeclaredConstructor(String.class);

        InvocationTargetException exception = assertThrows(
                InvocationTargetException.class,
                () -> constructor.newInstance("invalid")
        );

        assertInstanceOf(
                IllegalArgumentException.class,
                exception.getCause()
        );
    }
}
```

Reflection không phải đường tắt để bỏ qua canonical constructor. Quyền truy cập constructor vẫn tuân theo quy tắc access control và đóng gói module của Java.

## 9. Java Serialization của record cũng gọi canonical constructor

Record có thể triển khai `Serializable`. Khi một record được khôi phục từ object stream, Java Serialization sử dụng canonical constructor để tạo đối tượng và truyền các giá trị component đã giải tuần tự vào constructor đó.

Điều này giúp invariant được kiểm tra trong quá trình deserialization, cùng điểm bảo vệ với khởi tạo thông thường.

Ví dụ:

```java
import java.io.Serializable;
import java.util.Objects;

public record CustomerCode(String value) implements Serializable {

    public CustomerCode {
        value = Objects.requireNonNull(value, "value").strip();

        if (!value.matches("CUS-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "value must match CUS- followed by four digits"
            );
        }
    }
}
```

Test round-trip:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

import org.junit.jupiter.api.Test;

class CustomerCodeSerializationTest {

    @Test
    void restoresRecordThroughSerialization() throws Exception {
        CustomerCode original = new CustomerCode(" CUS-0042 ");

        byte[] serialized;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(original);
            serialized = bytes.toByteArray();
        }

        CustomerCode restored;
        try (ByteArrayInputStream bytes =
                     new ByteArrayInputStream(serialized);
             ObjectInputStream input = new ObjectInputStream(bytes)) {
            restored = (CustomerCode) input.readObject();
        }

        assertEquals("CUS-0042", restored.value());
        assertEquals(original, restored);
    }
}
```

Ví dụ xác nhận record hợp lệ được khôi phục và giữ giá trị component đã chuẩn hóa. Khi dữ liệu được giải tuần tự không thỏa invariant, canonical constructor có thể từ chối quá trình tạo đối tượng.

Không nên coi object stream là cách khởi tạo để bỏ qua validation. Nếu ứng dụng dùng serialization, invariant của canonical constructor là một phần quan trọng của hợp đồng khôi phục record.

## 10. Phân biệt invariant tại thời điểm tạo với trạng thái trong suốt vòng đời

Canonical constructor đảm bảo dữ liệu hợp lệ **khi đối tượng được tạo**. Điều đó chưa đủ nếu component tham chiếu đến object mutable mà bên ngoài còn có thể thay đổi.

Ví dụ:

```java
import java.util.List;

public record PositiveNumbers(List<Integer> values) {

    public PositiveNumbers {
        if (values.stream().anyMatch(value -> value <= 0)) {
            throw new IllegalArgumentException(
                    "all values must be positive"
            );
        }
    }
}
```

Đoạn mã kiểm tra các số dương nhưng lưu trực tiếp danh sách đầu vào. Sau khi record được tạo, bên gọi có thể thêm số âm vào danh sách nguồn. Khi đó trạng thái quan sát qua `values()` không còn thỏa invariant ban đầu.

Nên tạo defensive copy trước khi xác thực:

```java
import java.util.List;
import java.util.Objects;

public record PositiveNumbers(List<Integer> values) {

    public PositiveNumbers {
        values = List.copyOf(
                Objects.requireNonNull(values, "values")
        );

        if (values.stream().anyMatch(value -> value <= 0)) {
            throw new IllegalArgumentException(
                    "all values must be positive"
            );
        }
    }
}
```

`List.copyOf` tạo collection không thể sửa đổi và không chấp nhận null collection hoặc null element. Với `Integer` là kiểu bất biến, snapshot cấu trúc này đủ để bảo vệ invariant ví dụ.

Nếu collection chứa object mutable, sao chép cấu trúc thôi chưa đủ. Cần sao chép phần tử theo chính sách dữ liệu hoặc dùng kiểu phần tử bất biến. Với array, cần defensive copy ở constructor và accessor.

Vì vậy, hãy phân biệt hai câu hỏi:

- Constructor có từ chối mọi đầu vào không hợp lệ tại thời điểm tạo không?
- Sau khi tạo, bên ngoài có thể thay đổi dữ liệu được record biểu diễn và phá invariant không?

Một thiết kế record tốt cần trả lời cả hai.

## 11. Không lặp validation chung trong factory và overload

Việc kiểm tra đầu vào riêng của từng đường tạo là hợp lý, nhưng lặp toàn bộ invariant ở nhiều nơi dễ tạo sai lệch.

Ví dụ không nên duy trì nhiều phiên bản điều kiện:

```java
public record PageSize(int value) {

    public PageSize {
        if (value < 1 || value > 200) {
            throw new IllegalArgumentException("invalid page size");
        }
    }

    public PageSize(String text) {
        this(Integer.parseInt(text));

        if (text.isBlank()) {
            throw new IllegalArgumentException("text is blank");
        }
    }

    public static PageSize of(int value) {
        if (value < 1 || value > 100) {
            throw new IllegalArgumentException("invalid page size");
        }
        return new PageSize(value);
    }
}
```

Factory `of` ở đây áp dụng giới hạn 100 trong khi canonical constructor cho phép đến 200. Hai đường tạo có hợp đồng khác nhau dù cùng tạo một record. Constructor nhận chuỗi cũng kiểm tra rỗng sau khi đã gọi `Integer.parseInt`, khiến lỗi định dạng có thể xuất hiện trước thông báo mong muốn.

Nên phân chia trách nhiệm:

- Canonical constructor bảo vệ invariant của component.
- Constructor bổ sung chuyển đổi đầu vào khác dạng rồi ủy quyền.
- Static factory kiểm tra cú pháp hoặc ngữ nghĩa riêng của nguồn dữ liệu rồi gọi constructor.
- Test xác nhận tất cả đường tạo đều tạo cùng trạng thái hợp lệ và từ chối cùng miền dữ liệu không hợp lệ.

Ví dụ sửa:

```java
public record PageSize(int value) {

    public PageSize {
        if (value < 1 || value > 200) {
            throw new IllegalArgumentException(
                    "value must be between 1 and 200"
            );
        }
    }

    public PageSize(String text) {
        this(parseValue(text));
    }

    private static int parseValue(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                    "text must not be null or blank"
            );
        }
        return Integer.parseInt(text);
    }

    public static PageSize of(int value) {
        return new PageSize(value);
    }
}
```

Trong ví dụ này, `of` không lặp validation miền số. Constructor nhận chuỗi chỉ xử lý cú pháp đầu vào trước khi ủy quyền. Canonical constructor vẫn kiểm tra giới hạn cuối cùng.

Nếu hợp đồng yêu cầu null phải được phân biệt với chuỗi rỗng, hãy dùng `Objects.requireNonNull` trước khi gọi `isBlank` và ghi rõ loại ngoại lệ tương ứng.

## 12. Kiểm thử theo ma trận các đường tạo

Khi record có nhiều cách tạo, có thể lập ma trận để không bỏ sót đường nào:

| Đường tạo | Đầu vào hợp lệ | Đầu vào không hợp lệ | Điểm cần xác nhận |
| --- | --- | --- | --- |
| Canonical constructor trực tiếp | Giá trị component hợp lệ | Null, ngoài miền, quan hệ sai | Invariant được kiểm tra |
| Constructor bổ sung | Dạng đầu vào thay thế hợp lệ | Giá trị nguồn không hợp lệ | Ủy quyền đến canonical constructor |
| Static factory | Nguồn hợp lệ | Sai cú pháp hoặc ngoài miền | Factory không bỏ qua validation chung |
| Reflection | Tham số hợp lệ | Constructor ném lỗi | Cause được bọc trong `InvocationTargetException` |
| Serialization | Record hợp lệ được khôi phục | Dữ liệu khôi phục không thỏa invariant | Canonical constructor được gọi khi deserialize |

Không phải record nào cũng cần mọi đường tạo. Chỉ đưa vào ma trận những đường API thực sự hỗ trợ. Nếu record không triển khai `Serializable`, không cần test serialization; nếu không công bố API reflection, test reflection có thể là kiểm tra bổ sung.

Mỗi đường tạo cần có ít nhất một trường hợp thành công và một trường hợp thất bại phù hợp. Các factory có kiểm tra nguồn riêng cần test cả điều kiện riêng đó.

## 13. Kiểm thử constructor bổ sung và factory bằng test riêng

Nếu nhiều đường tạo cần tạo cùng một giá trị, có thể gom thao tác vào parameterized test hoặc viết test riêng cho từng đường. Test riêng thường dễ đọc và cho biết chính xác đường nào thất bại.

Ví dụ JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PageSizeCreationTest {

    @Test
    void directConstructorUsesCanonicalInvariant() {
        assertEquals(200, new PageSize(200).value());

        assertThrows(
                IllegalArgumentException.class,
                () -> new PageSize(201)
        );
    }

    @Test
    void overloadUsesCanonicalInvariant() {
        assertEquals(20, new PageSize("20").value());

        assertThrows(
                IllegalArgumentException.class,
                () -> new PageSize("201")
        );
    }

    @Test
    void factoryUsesCanonicalInvariant() {
        assertEquals(20, PageSize.of(20).value());

        assertThrows(
                IllegalArgumentException.class,
                () -> PageSize.of(201)
        );
    }
}
```

Test xác nhận ba đường tạo có cùng miền giá trị. Nếu giới hạn thay đổi, canonical constructor vẫn là nơi sửa quy tắc chung; test sẽ phát hiện đường tạo nào không còn tuân thủ.

## 14. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ validation trong static factory | Người gọi có thể gọi canonical constructor trực tiếp và tạo dữ liệu sai. | Đặt invariant chung trong canonical constructor. |
| Không khai báo canonical constructor dù record có invariant | Compiler chỉ sinh constructor gán component, không kiểm tra quy tắc nghiệp vụ. | Viết compact hoặc canonical constructor tường minh. |
| Constructor bổ sung tự gán component | Không tuân thủ cơ chế khởi tạo record. | Ủy quyền bằng `this(...)`. |
| Chuỗi constructor gọi vòng lặp | Không có đường đến canonical constructor và mã không biên dịch. | Thiết kế chuỗi ủy quyền kết thúc ở canonical constructor. |
| Factory lặp lại toàn bộ validation | Quy tắc dễ khác nhau giữa các đường tạo. | Factory xử lý nguồn; canonical constructor bảo vệ invariant cuối. |
| Reflection được xem là đường bỏ qua constructor | Hiểu sai hành vi khởi tạo Java. | Reflective constructor invocation vẫn gọi constructor. |
| Bỏ qua serialization khi record cần Serializable | Không kiểm chứng đường khôi phục đối tượng. | Xác nhận canonical constructor được dùng khi deserialize. |
| Chỉ kiểm tra đầu vào lúc tạo nhưng giữ alias mutable | Bên ngoài có thể phá invariant sau khi tạo. | Defensive copy hoặc dùng component bất biến. |
| Chỉ test đường tạo trực tiếp | Overload hoặc factory có thể có lỗi riêng. | Lập ma trận và test từng đường tạo được hỗ trợ. |
| Test phụ thuộc field hoặc implementation nội bộ | Test dễ hỏng khi refactor. | Kiểm tra qua accessor và hành vi công khai. |

## 15. Bài tập tự luyện

### Bài 1: Tìm đường tạo bỏ qua invariant

Một record `Percentage(int value)` có factory kiểm tra từ 0 đến 100 nhưng không khai báo canonical constructor. Người gọi có thể tạo `new Percentage(150)` không?

**Đáp án:** Có. Canonical constructor mặc định chỉ gán component. Factory không ngăn được lời gọi trực tiếp. Hãy chuyển validation vào compact hoặc canonical constructor.

### Bài 2: Hoàn thiện constructor bổ sung

Record `PageSize(int value)` chấp nhận từ 1 đến 200. Viết constructor nhận `String` và ủy quyền về canonical constructor.

**Đáp án tham khảo:**

```java
public record PageSize(int value) {

    public PageSize {
        if (value < 1 || value > 200) {
            throw new IllegalArgumentException("invalid page size");
        }
    }

    public PageSize(String text) {
        this(parse(text));
    }

    private static int parse(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text is required");
        }
        return Integer.parseInt(text);
    }
}
```

### Bài 3: Factory có cần lặp validation không?

Factory `PageSize.of(int value)` chỉ gọi `new PageSize(value)`. Có cần kiểm tra lại miền 1 đến 200 trong factory không?

**Đáp án:** Không. Canonical constructor đã bảo vệ invariant chung. Factory chỉ cần thêm kiểm tra nếu có quy tắc riêng cho nguồn đầu vào.

### Bài 4: Reflection có bỏ qua canonical constructor không?

Một ứng dụng gọi `getDeclaredConstructor(...).newInstance(...)` trên record. Validation trong canonical constructor có chạy không?

**Đáp án:** Có. Reflection gọi constructor thực tế. Nếu constructor ném ngoại lệ, caller nhận `InvocationTargetException` và có thể xem nguyên nhân qua `getCause()`.

### Bài 5: Vì sao defensive copy liên quan đến invariant?

Record kiểm tra mọi phần tử trong `List<Integer>` đều dương nhưng lưu trực tiếp list đầu vào. Sau khi tạo, bên gọi thêm số âm vào list. Invariant còn được bảo đảm không?

**Đáp án:** Không. Validation chỉ đúng tại thời điểm tạo, nhưng alias mutable cho phép thay đổi trạng thái sau đó. Hãy dùng `List.copyOf` trước khi kiểm tra và lưu, hoặc chọn cấu trúc bất biến phù hợp.

## Ghi nhớ

Canonical constructor là điểm bảo vệ invariant chung của record. Canonical constructor có thể là compact hoặc tường minh; nếu không khai báo, compiler chỉ sinh constructor gán component. Constructor bổ sung phải ủy quyền bằng `this(...)`, còn static factory cần tạo đối tượng thông qua constructor. Reflection và Java Serialization cũng sử dụng canonical constructor của record. Hãy kiểm thử từng đường tạo được hỗ trợ với đầu vào hợp lệ và không hợp lệ. Cuối cùng, bảo đảm invariant không chỉ tại thời điểm tạo: component mutable cần được sao chép phòng vệ hoặc thiết kế theo kiểu bất biến.

## Tài liệu tham khảo

- [Java Language Specification — Java SE 26, `8.10.4` Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10.4).
- [Java Language Specification — Java SE 16, `8.10.4` Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html#jls-8.10.4).
- [JEP 513 — Flexible Constructor Bodies (hoàn thiện trong Java 25)](https://openjdk.org/jeps/513).
- [Java Object Serialization Specification — Serialization of Records](https://docs.oracle.com/en/java/javase/26/docs/specs/serialization/serial-arch.html#serialization-of-records).
- [Java API — Constructor.newInstance](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)).
- [Java API — InvocationTargetException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/InvocationTargetException.html).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
