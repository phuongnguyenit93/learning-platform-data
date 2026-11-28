# Khai báo canonical constructor tường minh và gán đủ field final

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá các cải tiến từ Java 16 còn hữu ích trong Java hiện đại. Bài tập trung vào cách tự khai báo constructor chuẩn của `record` và bảo đảm mọi component field `final` được khởi tạo hợp lệ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích mối quan hệ giữa record component và component field được Java tạo ra.
- Viết canonical constructor tường minh với danh sách tham số khớp record header.
- Phân biệt tham số constructor với field bằng `this` và gán từng field `final` đúng cách.
- Bảo đảm mọi field được gán trên mọi luồng thực thi kết thúc bình thường.
- Thực hiện kiểm tra đầu vào, chuẩn hóa dữ liệu và sao chép phòng vệ trong constructor.
- Nhận diện lỗi biên dịch do thiếu gán, gán lặp hoặc khai báo sai canonical constructor.

## 1. Record component và field được tạo ra

Một record mô tả dữ liệu qua danh sách component trong record header:

```java
public record Customer(String name, int age) {}
```

Với khai báo trên, Java tự cung cấp các thành phần tương ứng:

- Một field `private final String name`.
- Một field `private final int age`.
- Các accessor `name()` và `age()`.
- Các phương thức `equals()`, `hashCode()` và `toString()` dựa trên component.
- Một **canonical constructor** có tham số tương ứng với `name` và `age`.

Các field component là `private final`. Chúng được khai báo ngầm từ record header; bạn không viết lại chúng trong thân record. Record cũng không cho phép khai báo thêm instance field tùy ý như một class thông thường.

Khi không khai báo constructor chuẩn, trình biên dịch tạo canonical constructor và tự gán các tham số cho component field. Ví dụ:

```java
Customer customer = new Customer("An", 28);

System.out.println(customer.name()); // An
System.out.println(customer.age());  // 28
```

Cơ chế tự sinh này phù hợp khi chỉ cần lưu các giá trị đầu vào. Khi cần xác thực, chuẩn hóa hoặc sao chép dữ liệu trước khi lưu, bạn có thể khai báo canonical constructor tường minh.

## 2. Canonical constructor tường minh là gì?

Canonical constructor là constructor có danh sách tham số đại diện chính xác cho các component của record. Khi khai báo dạng đầy đủ, danh sách tham số phải khớp record header về:

- **Số lượng:** mỗi component có một tham số tương ứng.
- **Thứ tự:** tham số ở vị trí nào phải ứng với component ở vị trí đó.
- **Kiểu:** kiểu của từng tham số phải tương ứng với kiểu component.
- **Tên:** tên tham số phải giống chính xác tên component tương ứng.

Ví dụ record:

```java
public record Customer(String name, int age) {
    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

Constructor `Customer(String name, int age)` là canonical constructor vì nó khớp với danh sách component trong header `(String name, int age)`.

Một lời gọi:

```java
Customer customer = new Customer("An", 28);
```

sẽ truyền `"An"` vào tham số `name` và `28` vào tham số `age`. Java xác định tương ứng theo vị trí trong chữ ký constructor.

**Không được thay tên tham số tùy ý để tạo một canonical constructor khác.** Ví dụ sau không hợp lệ:

```java
// SAI: tên tham số không khớp tên component.
public record Customer(String name, int age) {
    public Customer(String customerName, int age) {
        this.name = customerName;
        this.age = age;
    }
}
```

Dù kiểu và thứ tự tham số vẫn đúng, `customerName` không trùng với tên component `name`. Đây vẫn là chữ ký canonical, nên việc đổi tên tham số không biến nó thành constructor nạp chồng.

## 3. Gán đầy đủ component field final

Vì các component field là `final`, canonical constructor tường minh phải bảo đảm **mỗi field được gán đúng một lần trên mọi luồng thực thi kết thúc bình thường**.

```java
public record Customer(String name, int age) {

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

Hai lệnh gán có ý nghĩa:

- `this.name = name;` gán tham số `name` vào field `name` của đối tượng hiện tại.
- `this.age = age;` gán tham số `age` vào field `age` của đối tượng hiện tại.

Từ khóa `this` giúp phân biệt field với tham số có cùng tên. Trong constructor này, `name` ở vế phải là tham số, còn `this.name` ở vế trái là field.

Nếu chỉ viết:

```java
public record Customer(String name, int age) {
    public Customer(String name, int age) {
        name = name.strip();
        // SAI: field name và field age chưa được gán.
    }
}
```

thì câu lệnh `name = name.strip()` chỉ thay đổi giá trị tham số. Nó không gán field `this.name`. Constructor kết thúc bình thường trong khi các field component chưa được khởi tạo, nên chương trình không biên dịch.

### Vì sao phải gán đủ field?

Mọi đối tượng record phải có giá trị hợp lệ cho tất cả component ngay khi được tạo. Trình biên dịch áp dụng quy tắc definite assignment đối với các field `final` để ngăn đối tượng hoàn tất khởi tạo khi còn component chưa được gán.

Ví dụ lỗi thiếu một field:

```java
// SAI: age chưa được gán.
public record Customer(String name, int age) {
    public Customer(String name, int age) {
        this.name = name;
    }
}
```

Ví dụ gán một field hai lần:

```java
// SAI: field final name bị gán nhiều lần.
public record Customer(String name, int age) {
    public Customer(String name, int age) {
        this.name = name;
        this.name = name.strip();
        this.age = age;
    }
}
```

Cách đúng là chuẩn hóa giá trị trước, sau đó gán field một lần:

```java
public record Customer(String name, int age) {
    public Customer(String name, int age) {
        String normalizedName = name.strip();

        this.name = normalizedName;
        this.age = age;
    }
}
```

Ví dụ cuối vẫn cần chính sách xử lý `name == null` trong ứng dụng thực tế; phần tiếp theo sẽ hoàn thiện kiểm tra đó.

## 4. Kiểm tra và chuẩn hóa trước khi gán

Một constructor tốt nên xác định dữ liệu hợp lệ trước khi lưu vào các field. Ví dụ:

```java
import java.util.Objects;

public record Customer(String name, int age) {

    public Customer(String name, int age) {
        String normalizedName =
                Objects.requireNonNull(name, "name").strip();

        if (normalizedName.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }

        this.name = normalizedName;
        this.age = age;
    }
}
```

Cách sử dụng:

```java
Customer customer = new Customer("  An  ", 28);

System.out.println(customer.name()); // An
System.out.println(customer.age());  // 28

// new Customer("   ", 28); // IllegalArgumentException
// new Customer("An", -1);   // IllegalArgumentException
// new Customer(null, 28);   // NullPointerException
```

Thứ tự thực hiện là:

1. Kiểm tra `name` không phải `null`.
2. Chuẩn hóa chuỗi bằng `strip()`.
3. Từ chối tên rỗng hoặc chỉ chứa khoảng trắng.
4. Kiểm tra `age` không âm.
5. Gán các giá trị hợp lệ vào hai field `final`.

Nếu một kiểm tra thất bại và constructor ném ngoại lệ, đối tượng không được tạo thành công. Những đường thực thi kết thúc bình thường đều đi qua cả hai lệnh gán field.

### Gán field theo thứ tự nào?

Thứ tự câu lệnh gán không bắt buộc trùng thứ tự component trong header. Điều bắt buộc là mỗi field nhận đúng giá trị tương ứng và được gán đầy đủ.

```java
public record Coordinate(int x, int y) {
    public Coordinate(int x, int y) {
        this.y = y;
        this.x = x;
    }
}
```

Đoạn trên hợp lệ dù gán `y` trước `x`. Tuy nhiên, nên giữ thứ tự gán dễ đọc, thường trùng với thứ tự component trong header, để giảm nhầm lẫn khi record có nhiều thành phần.

## 5. Quy tắc definite assignment trên các nhánh điều kiện

Mỗi component field phải được gán trên **mọi đường thực thi có thể kết thúc bình thường**. Không nhất thiết mỗi field chỉ xuất hiện trong đúng một câu lệnh gán về mặt cú pháp, nhưng trình biên dịch phải chứng minh được field được gán đúng một lần trên từng đường chạy hợp lệ.

Ví dụ gán theo nhánh:

```java
public record DisplayName(String value, boolean abbreviated) {

    public DisplayName(String value, boolean abbreviated) {
        String result;

        if (abbreviated) {
            result = value.substring(0, 1);
        } else {
            result = value;
        }

        this.value = result;
        this.abbreviated = abbreviated;
    }
}
```

Biến cục bộ `result` nhận giá trị ở cả hai nhánh trước khi được dùng để gán field `this.value`. Cả hai field component đều được gán khi constructor hoàn tất.

Ngược lại, ví dụ sau không hợp lệ:

```java
// SAI: result chưa chắc có giá trị nếu điều kiện false.
public record DisplayName(String value, boolean abbreviated) {

    public DisplayName(String value, boolean abbreviated) {
        String result;

        if (abbreviated) {
            result = value.substring(0, 1);
        }

        this.value = result;
        this.abbreviated = abbreviated;
    }
}
```

Nếu `abbreviated` là `false`, `result` chưa được khởi tạo nhưng vẫn được đọc. Đây là lỗi definite assignment của biến cục bộ.

Một đường chạy ném ngoại lệ trước khi gán field không cần hoàn tất khởi tạo, vì constructor đó không kết thúc bình thường. Tuy vậy, mọi đường chạy có thể tạo ra đối tượng thành công phải gán đủ tất cả component field.

## 6. Tham số và field là hai vị trí lưu trữ khác nhau

Trong canonical constructor dạng đầy đủ, tham số có tên giống component nhưng vẫn là biến tham số. Muốn thay đổi giá trị sẽ lưu vào record, hãy gán field tương ứng.

| Câu lệnh | Tác động |
| --- | --- |
| `name = name.strip();` | Gán lại biến tham số `name`. |
| `this.name = name;` | Gán field `name` bằng giá trị hiện tại của tham số. |
| `this.name = name.strip();` | Gán trực tiếp giá trị đã chuẩn hóa vào field. |
| `this.age = age;` | Gán field `age` từ tham số `age`. |

Có thể chuẩn hóa ngay trong câu lệnh gán:

```java
public record Slug(String value) {
    public Slug(String value) {
        this.value = value == null ? null : value.strip().toLowerCase();
    }
}
```

Tuy nhiên, ví dụ trên chủ động cho phép `null`. Nếu hợp đồng dữ liệu yêu cầu giá trị bắt buộc, hãy kiểm tra và từ chối `null` rõ ràng:

```java
import java.util.Objects;
import java.util.Locale;

public record Slug(String value) {
    public Slug(String value) {
        String normalized = Objects.requireNonNull(value, "value")
                .strip()
                .toLowerCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }

        this.value = normalized;
    }
}
```

Dùng `Locale.ROOT` cho phép chuyển chữ thường theo quy tắc ổn định, không phụ thuộc locale mặc định của máy đang chạy. Quy tắc chuẩn hóa cụ thể vẫn phải phù hợp với ý nghĩa dữ liệu của ứng dụng.

## 7. Bảo vệ dữ liệu có thể thay đổi

Field component là `final` chỉ có nghĩa là **không thể gán lại tham chiếu** sau khi khởi tạo. Nếu component tham chiếu đến một đối tượng có thể thay đổi, nội dung đối tượng đó vẫn có thể bị sửa.

Ví dụ với danh sách:

```java
import java.util.List;

public record Team(String name, List<String> members) {
    public Team(String name, List<String> members) {
        this.name = name;
        this.members = List.copyOf(members);
    }
}
```

`List.copyOf` tạo bản sao danh sách không thể thay đổi qua các thao tác sửa danh sách thông thường. Điều này giúp record không bị ảnh hưởng khi bên gọi sửa danh sách ban đầu và không cho bên nhận accessor thêm hoặc xóa phần tử.

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("An", "Bình"));
Team team = new Team("Platform", source);

source.add("Chi");

System.out.println(team.members()); // [An, Bình]

// team.members().add("Dũng");
// UnsupportedOperationException
```

Nếu component là mảng, việc gán trực tiếp chỉ lưu cùng một tham chiếu. Muốn bảo vệ mảng, constructor có thể clone dữ liệu đầu vào:

```java
import java.util.Arrays;

public record DataBlock(byte[] bytes) {

    public DataBlock(byte[] bytes) {
        this.bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Constructor sao chép mảng khi nhận dữ liệu; accessor cũng trả về bản sao để người gọi không sửa trực tiếp mảng bên trong record. Đây là ví dụ cho thấy bảo vệ dữ liệu có thể cần cả lúc khởi tạo lẫn lúc truy cập.

`List.copyOf` và `clone()` trong các ví dụ trên chỉ sao chép cấu trúc chứa phần tử. Nếu phần tử là đối tượng có thể thay đổi, trạng thái bên trong các phần tử đó vẫn có thể thay đổi. Vì vậy, đây là bất biến nông; muốn bất biến sâu cần thiết kế thêm cho các kiểu phần tử.

## 8. Phân biệt canonical constructor với constructor nạp chồng

Canonical constructor tường minh có danh sách tham số khớp toàn bộ record header. Constructor nạp chồng có chữ ký khác và không thay thế canonical constructor.

```java
public record Money(long amount, String currency) {

    // Canonical constructor: (long, String)
    public Money(long amount, String currency) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }

        this.amount = amount;
        this.currency = currency;
    }

    // Constructor nạp chồng: (long)
    public Money(long amount) {
        this(amount, "VND");
    }
}
```

Constructor nạp chồng `Money(long amount)` phải ủy quyền qua `this(...)`. Nó không tự gán component field. Nhờ vậy, việc khởi tạo vẫn đi qua canonical constructor, nơi kiểm tra và gán dữ liệu tập trung.

```java
Money a = new Money(100_000, "VND");
Money b = new Money(100_000);

System.out.println(a.currency()); // VND
System.out.println(b.currency()); // VND
```

Không thể khai báo một constructor có danh sách tham số trùng với canonical constructor rồi xem nó như overload. Một record chỉ có một canonical constructor.

## 9. So sánh canonical đầy đủ và compact constructor

Java hỗ trợ hai cách khai báo canonical constructor tường minh:

| Tiêu chí | Canonical dạng đầy đủ | Compact canonical |
| --- | --- | --- |
| Danh sách tham số | Viết rõ toàn bộ tham số | Không viết danh sách tham số |
| Tên và thứ tự tham số | Phải khớp record header | Tham số được suy ra từ header |
| Kiểm tra đầu vào | Được phép | Được phép |
| Chuẩn hóa tham số | Được phép | Được phép |
| Gán component field | Tự gán tường minh bằng `this.field = ...` | Trình biên dịch tự gán sau thân constructor |
| Dùng khi | Cần điều khiển rõ cách gán từng field | Chủ yếu kiểm tra hoặc chuẩn hóa dữ liệu |

Ví dụ compact canonical:

```java
public record Customer(String name, int age) {
    public Customer {
        name = name.strip();

        if (name.isEmpty()) {
            throw new IllegalArgumentException("name is required");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

Trong compact constructor, `name` và `age` là các tham số ngầm. Có thể gán lại tham số để chuẩn hóa; sau khi thân constructor hoàn tất bình thường, trình biên dịch tự gán các field component. Không viết `this.name = name` trong thân compact constructor.

Bài này tập trung vào dạng đầy đủ, nơi người viết phải tự gán tất cả field `final`. Hãy chọn dạng phù hợp với độ phức tạp của việc khởi tạo và giữ cách triển khai nhất quán.

## 10. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Bỏ quên `this.age = age` | Field `age` chưa được gán khi constructor kết thúc bình thường. | Gán mọi component field trên mọi đường chạy hợp lệ. |
| Chỉ viết `name = name.strip()` | Chỉ thay đổi tham số, không gán field `this.name`. | Gán `this.name = name` sau khi chuẩn hóa. |
| Gán `this.name` hai lần | Field component là `final` và chỉ được gán một lần. | Chuẩn hóa vào biến cục bộ rồi gán field một lần. |
| Đổi tên tham số `name` thành `customerName` | Danh sách tham số không còn khớp tên component. | Dùng đúng tên component trong canonical constructor. |
| Đảo thứ tự tham số | Chữ ký không khớp thứ tự component. | Giữ thứ tự như record header. |
| Gán field chỉ ở một nhánh điều kiện | Có đường chạy kết thúc bình thường mà field chưa được gán. | Bảo đảm mọi nhánh đều đi đến lệnh gán hoặc kết thúc bất thường bằng ngoại lệ. |
| Nghĩ `final List` đồng nghĩa danh sách bất biến | `final` chỉ khóa tham chiếu, không khóa nội dung danh sách. | Sao chép phòng vệ, ví dụ `List.copyOf`. |
| Viết constructor nạp chồng rồi tự gán field | Constructor không phải canonical phải ủy quyền theo quy tắc constructor của record. | Dùng `this(...)` để gọi canonical constructor. |

## 11. Bài tập tự luyện

### Bài 1: Hoàn thiện canonical constructor

Hoàn thiện record sau để tên không được `null` hoặc rỗng, đồng thời tuổi không âm:

```java
import java.util.Objects;

public record Person(String name, int age) {
    public Person(String name, int age) {
        // TODO: kiểm tra và chuẩn hóa name
        // TODO: kiểm tra age
        // TODO: gán đủ hai field final
    }
}
```

**Đáp án tham khảo:**

```java
import java.util.Objects;

public record Person(String name, int age) {
    public Person(String name, int age) {
        String normalized = Objects.requireNonNull(name, "name").strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }

        this.name = normalized;
        this.age = age;
    }
}
```

### Bài 2: Vì sao đoạn mã không biên dịch?

```java
public record Rectangle(int width, int height) {
    public Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException();
        }

        this.width = width;
    }
}
```

**Đáp án:** Field `height` chưa được gán trên đường chạy có đầu vào hợp lệ. Bổ sung `this.height = height;` sau phần kiểm tra.

### Bài 3: Chuẩn hóa mà không gán field hai lần

Sửa đoạn sau:

```java
public record Code(String value) {
    public Code(String value) {
        this.value = value;
        this.value = value.strip();
    }
}
```

**Đáp án:** Chuẩn hóa vào biến cục bộ trước khi gán:

```java
public record Code(String value) {
    public Code(String value) {
        String normalized = value.strip();
        this.value = normalized;
    }
}
```

Trong ứng dụng thực tế, bổ sung kiểm tra `null` và chính sách xử lý chuỗi rỗng nếu hợp đồng dữ liệu yêu cầu.

### Bài 4: Phân biệt field với tham số

Với `record Quantity(int value)`, câu lệnh nào gán component field?

- A. `value = value + 1;`
- B. `this.value = value + 1;`

**Đáp án:** B. A chỉ thay đổi tham số. B gán field `value` bằng giá trị mới. Vì field là `final`, constructor phải bảo đảm field chỉ được gán một lần.

## Ghi nhớ

Canonical constructor tường minh dạng đầy đủ cho phép bạn kiểm soát chính xác quá trình khởi tạo record. Danh sách tham số phải khớp record header về số lượng, kiểu, thứ tự và tên. Vì component field là `private final`, bạn phải tự gán mỗi field đúng một lần trên mọi đường thực thi kết thúc bình thường. Hãy kiểm tra và chuẩn hóa dữ liệu trước khi gán, dùng `this.component` để phân biệt field với tham số, và cân nhắc sao chép phòng vệ khi component tham chiếu đến dữ liệu có thể thay đổi.

## Tài liệu tham khảo

- [Java Language Specification — `8.10.4, Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4).
- [Java Language Specification — `4.12.4, final Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4).
- [JEP 395 — Records (được hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
