# Canonical constructor được suy ra từ header của record

## Mục tiêu và phạm vi

Trong một `record`, **record header** là nguồn xác định các thành phần dữ liệu (*record components*) và chữ ký của **canonical constructor**. Sau bài này, bạn sẽ biết cách suy ra constructor từ header, giải thích lúc nào Java tự sinh constructor, phân biệt constructor chuẩn viết đầy đủ với **compact canonical constructor**, kiểm tra/chuẩn hóa dữ liệu đúng chỗ và nhận diện các lỗi biên dịch thường gặp.

Các quy tắc dưới đây là ngữ nghĩa **đang được Java hỗ trợ chính thức**. Record đã là tính năng chuẩn từ Java 16; các chương trình trong bài dùng **JDK 17+**, không cần bật preview. Ví dụ phục vụ kiến thức đang áp dụng, không sử dụng cú pháp thử nghiệm hoặc cách chạy preview cũ.

## 1. Header xác định cấu trúc của record

```java
record Point(int x, int y) {}
```

Phần `(int x, int y)` là header, mô tả hai component theo thứ tự: `x` kiểu `int` và `y` kiểu `int`. Với mỗi component, Java cung cấp một field `private final` tương ứng, một accessor `public` như `x()`/`y()` (nếu chưa khai báo tường minh hợp lệ) và một tham số tương ứng trong canonical constructor. Record cũng có các triển khai `equals`, `hashCode`, `toString` được sinh ngầm khi thích hợp.

Vì vậy, dù thân record trống, bạn vẫn có thể viết trong một phương thức:

```java
Point p = new Point(3, 4);
System.out.println(p.x()); // 3
System.out.println(p.y()); // 4
```

Lời gọi `new Point(3, 4)` sử dụng canonical constructor do Java sinh ngầm. Record **không có setter được sinh tự động**, và các field là `final`; tuy nhiên, tính bất biến này chỉ ở mức các field/tham chiếu, không bảo đảm bất biến sâu với component kiểu đối tượng có thể thay đổi.

## 2. Canonical constructor được suy ra như thế nào?

Giả sử header của record `R` gồm các component `(T1 c1, T2 c2, ..., Tn cn)`. Java suy ra danh sách tham số constructor chuẩn **theo đúng thứ tự, kiểu và tên component**; về mặt khái niệm có dạng `R(T1 c1, T2 c2, ..., Tn cn)`.

| Header | Dạng canonical constructor tương ứng | Điều cần chú ý |
| --- | --- | --- |
| `record Point(int x, int y)` | `Point(int x, int y)` | Hai tham số theo thứ tự trong header |
| `record User(String name, int age)` | `User(String name, int age)` | `name` đứng trước `age` |
| `record Box<T>(T value)` | `Box(T value)` | Kiểu generic `T` thuộc phạm vi record |
| `record Empty()` | `Empty()` | Header rỗng tạo canonical constructor không tham số |
| `record Labels(String... tags)` | `Labels(String... tags)` | Component varargs dẫn tới tham số varargs tương ứng |

Một constructor do lập trình viên khai báo có **chữ ký tương đương chữ ký chuẩn suy ra từ header** sẽ được phân loại là canonical constructor. Đối với dạng canonical constructor **viết đầy đủ**, Java yêu cầu từng tham số có tên và kiểu đúng như component tương ứng. Tên tham số tuy không là thành phần nhận diện overload trong chữ ký Java nói chung, nhưng vẫn phải trùng header khi khai báo normal canonical constructor.

Nếu bạn thay đổi tên, kiểu, thứ tự hoặc số lượng component trong header, đường khởi tạo và các mã gọi constructor có thể cần cập nhật. Hãy xem header là một **hợp đồng cấu trúc** của record.

## 3. Constructor ngầm định: không viết vẫn có

Xét khai báo:

```java
public record Coordinate(int latitude, int longitude) {}
```

Do bạn **không khai báo canonical constructor**, Java tự sinh constructor với hai tham số cùng tên, kiểu và thứ tự như header. Về tác dụng gán field, có thể hình dung tương đương khai báo thay thế sau:

```java
public record Coordinate(int latitude, int longitude) {
    public Coordinate(int latitude, int longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }
}
```

Hai đoạn trên là **hai cách khai báo thay thế nhau**, không đặt đồng thời trong một tệp. Đoạn thứ hai chỉ minh họa hành vi gán dữ liệu, không mô tả chính xác mọi chi tiết bytecode do compiler sinh.

Quy tắc quan trọng:

- Canonical constructor ngầm xuất hiện **khi record không tự khai báo canonical constructor** theo dạng đầy đủ hoặc compact. Một overload không chuẩn vẫn có thể cùng tồn tại với canonical constructor được sinh ngầm.
- Mức truy cập constructor ngầm tương ứng mức truy cập của record: record `public` có canonical constructor `public`; record có quyền truy cập package có canonical constructor package.
- `record Point(int x, int y)` không tự có constructor `Point()`; `new Point()` không hợp lệ nếu không viết một overload phù hợp. Ngược lại, `record Empty()` có canonical constructor rỗng vì **header vốn rỗng**.
- Constructor ngầm chỉ nhận và lưu tham số. Nó **không tự kiểm tra** chuỗi trắng, `null`, số âm hay quan hệ giữa các component. Quy tắc đó phải được đặt trong contract của ứng dụng.
- Mỗi lần gọi `new` thường tạo đối tượng mới; canonical constructor không hàm ý cache hoặc singleton.

## 4. Ba hình thức canonical constructor

| Hình thức | Cách khai báo | Trách nhiệm gán component fields | Phù hợp |
| --- | --- | --- | --- |
| **Ngầm định** | Chỉ có header, không khai báo canonical constructor | Compiler gán từng tham số vào field tương ứng | Dữ liệu không cần xử lý riêng |
| **Normal canonical tường minh** | Viết đủ `R(T1 c1, T2 c2, ...) { ... }` | **Bạn** phải gán đủ các component fields | Muốn kiểm soát rõ việc khởi tạo |
| **Compact canonical** | Viết `R { ... }`, không lặp tham số | Compiler gán các field sau khi thân kết thúc bình thường | Kiểm tra, chuẩn hóa, sao chép phòng vệ |

### 4.1. Normal canonical constructor viết đầy đủ

```java
record Range(int start, int end) {
    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
        this.start = start;
        this.end = end;
    }
}
```

Constructor viết đầy đủ có **đúng tham số** `(int start, int end)`. Bạn tự khởi tạo `this.start` và `this.end`. Nếu bỏ một phép gán, compiler không tự bù như ở dạng compact. Vì các field là `final`, chúng phải được khởi tạo đúng theo quy tắc definite assignment của Java.

Ví dụ `new Range(2, 5)` thành công, còn `new Range(5, 2)` ném ngoại lệ do **điều kiện bạn tự viết**. Record không mặc định biết quy tắc `start <= end`.

### 4.2. Compact canonical constructor: tham số đã có từ header

```java
record UserName(String value) {
    UserName {
        java.util.Objects.requireNonNull(value, "value");
        value = value.strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("username is blank");
        }
    }
}
```

Dù không lặp `(String value)`, `UserName { ... }` **vẫn là canonical constructor**. Tham số `value` được compiler suy ra từ header và có thể dùng trong thân constructor.

- `value = value.strip();` thay đổi **tham số cục bộ**, không trực tiếp gán vào field.
- Khi thân compact constructor **kết thúc bình thường**, Java tự thực hiện phép gán component field từ giá trị cuối cùng của tham số, tương đương `this.value = value`.
- `new UserName("  Lan  ").value()` trả `"Lan"`; `new UserName("  ")` ném `IllegalArgumentException`; `new UserName(null)` ném `NullPointerException` từ `requireNonNull`.
- **Không** viết `this.value = value;` trong thân compact constructor: Java không cho gán trực tiếp vào component field ở đây.
- Thân compact constructor cũng không được chứa `return` statement. Nếu phải thực hiện xử lý nhiều bước, bạn cứ viết các lệnh hợp lệ rồi để Java gán ở cuối.

### 4.3. Không thể khai báo cả hai dạng canonical tường minh

Một normal canonical constructor và một compact constructor trên cùng record đều xác định **cùng một canonical constructor**. Viết cả hai gây lỗi biên dịch. Hãy chọn một trong hai; không có cơ chế định nghĩa hai bản canonical để Java tự chọn.

## 5. Chương trình đầy đủ: ngầm định, compact, normal và overload

Tạo tệp **`RecordConstructorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RecordConstructorDemo {
    // Implicit canonical constructor: Point(int x, int y).
    record Point(int x, int y) {}

    // Compact canonical constructor: parameter "value" is implicit.
    record UserName(String value) {
        UserName {
            Objects.requireNonNull(value, "value");
            value = value.strip();
            if (value.isEmpty()) {
                throw new IllegalArgumentException("username is blank");
            }
        }
    }

    // Explicit normal canonical constructor.
    record Item(String name, int quantity) {
        Item(String name, int quantity) {
            Objects.requireNonNull(name, "name");
            String normalized = name.strip();
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("item name is blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            this.name = normalized;
            this.quantity = quantity;
        }

        // Non-canonical overload: delegates to canonical constructor.
        Item(String name) {
            this(name, 1);
        }
    }

    // A compact constructor can create a defensive snapshot.
    record Tags(List<String> values) {
        Tags {
            values = List.copyOf(values);
        }
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Point point = new Point(2, 3);
        check(point.x() == 2 && point.y() == 3, "point");
        System.out.println("Point: " + point.x() + "," + point.y());

        UserName userName = new UserName("  Lan  ");
        check("Lan".equals(userName.value()), "userName");
        System.out.println("Username: [" + userName.value() + "]");

        Item item = new Item("  Pencil  ");
        check("Pencil".equals(item.name()) && item.quantity() == 1,
                "item");
        System.out.println("Item: " + item.name() + " x" + item.quantity());

        ArrayList<String> source = new ArrayList<>();
        source.add("java");
        Tags tags = new Tags(source);
        source.add("later");
        check(tags.values().equals(List.of("java")), "snapshot");
        System.out.println("Tags: " + tags.values());

        try {
            tags.values().add("change");
            throw new AssertionError("List should be unmodifiable");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Tags: unmodifiable");
        }

        try {
            new Item("   ", 2);
            throw new AssertionError("Blank item name must fail");
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid Item: " + expected.getMessage());
        }

        try {
            new UserName("   ");
            throw new AssertionError("Blank username must fail");
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid Username: " + expected.getMessage());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng **JDK 17 trở lên**:

```bash
javac --release 17 RecordConstructorDemo.java
java RecordConstructorDemo
```

**Stdout mong đợi:**

```text
Point: 2,3
Username: [Lan]
Item: Pencil x1
Tags: [java]
Tags: unmodifiable
Invalid Item: item name is blank
Invalid Username: username is blank
```

**Phân tích kết quả:**

1. `Point` không khai báo constructor nhưng vẫn tạo được đối tượng với `new Point(2, 3)`; hai accessor trả về giá trị của constructor ngầm.
2. `UserName` chuẩn hóa tham số `value` bằng `strip()` trong compact constructor; Java chỉ gán nó vào component field sau khi thân constructor kết thúc hợp lệ.
3. `Item` viết normal canonical constructor với tham số khớp header và tự gán cả hai field `final`. Overload `Item(String name)` sử dụng `this(name, 1)`, cuối cùng đi qua đường kiểm tra của canonical constructor.
4. `Tags` dùng `List.copyOf` để lưu snapshot không cho sửa cấu trúc, nên thay đổi danh sách `source` sau đó không làm đổi danh sách đã lưu trong record. Thao tác `add` trên bản lưu ném `UnsupportedOperationException`.
5. Hai ca chuỗi chỉ gồm khoảng trắng phải ném đúng `IllegalArgumentException`. Nếu bất ngờ không ném, `AssertionError` làm bài kiểm chứng thất bại rõ ràng.

Các dòng in ra ở trên là **kết quả dự kiến theo mã**, có thể đối chiếu bằng hai lệnh biên dịch/chạy. `--release 17` yêu cầu mức ngôn ngữ và API tương thích Java 17 cho bản biên dịch; nếu cần xác nhận hành vi ở một runtime cụ thể, vẫn phải thực sự chạy trên runtime đó.

## 6. Constructor overload vẫn phải đi qua đường canonical

```java
record Quantity(int value) {
    Quantity() {
        this(1);
    }
}
```

Header `(int value)` dẫn xuất canonical constructor `Quantity(int value)`, được Java sinh ngầm vì record chưa tự khai báo dạng canonical nào. `Quantity()` là overload **non-canonical**, gọi tiếp `this(1)` để đi qua canonical constructor.

Khi đó `new Quantity(5).value()` là `5`; `new Quantity().value()` là `1`. Record có component không tự sinh zero-argument constructor; chính overload mới tạo thêm cách gọi này.

Quy tắc hiện hành là **thân mọi non-canonical constructor trong record phải có alternate constructor invocation** (`this(...)`), để đường khởi tạo cuối cùng tới canonical constructor. Các phiên bản Java mới có quy tắc linh hoạt hơn về vị trí một số câu lệnh trong thân constructor; vì vậy đừng coi diễn đạt “`this(...)` luôn phải là dòng đầu trong mọi JDK” là định nghĩa bất biến. Đối với mã trên JDK 17, đặt `this(...)` đầu tiên là cách đúng và rõ ràng.

Một overload không được tự hình thành đường gán component field tách biệt khỏi canonical constructor. Tập trung kiểm tra hợp lệ tại canonical constructor giúp tránh việc một overload tạo ra record vi phạm contract.

## 7. Các trường hợp cố ý sai khi biên dịch

Các đoạn trong mục này **minh họa lỗi**, không phải mã chạy độc lập; không chép cùng nhau vào tệp ở mục 5.

### 7.1. Tên tham số normal canonical không khớp header

```java
record Point(int x, int y) {
    Point(int a, int b) { // ERROR: names differ from components.
        this.x = a;
        this.y = b;
    }
}
```

Do kiểu tham số tạo thành chữ ký canonical, Java áp dụng quy tắc normal canonical constructor: tên hình thức phải là `x`, `y` như header. Sửa thành `Point(int x, int y)` rồi gán `this.x = x; this.y = y;`.

### 7.2. Normal canonical bỏ sót một phép gán field

```java
record Point(int x, int y) {
    Point(int x, int y) {
        this.x = x;
        // ERROR: final field y has not been assigned.
    }
}
```

Bạn tự viết constructor đầy đủ thì phải khởi tạo đủ component fields. Sửa bằng `this.y = y;` hoặc chuyển sang compact constructor nếu muốn Java thực hiện các phép gán.

### 7.3. Compact constructor tự gán trực tiếp component field

```java
record User(String name) {
    User {
        this.name = name; // ERROR in compact constructor.
    }
}
```

Trong compact constructor, Java tự gán các component fields **sau** thân constructor. Nếu cần chuẩn hóa, thao tác với **tham số** `name` (chẳng hạn `name = name.strip()` sau khi kiểm tra null), rồi để Java gán cuối cùng.

### 7.4. Canonical constructor tường minh quá hạn chế quyền truy cập

```java
public record PublicUser(String name) {
    private PublicUser(String name) { // ERROR: too restrictive.
        this.name = name;
    }
}
```

Canonical constructor tường minh phải có mức truy cập **ít nhất bằng** record. Với `public record`, constructor chuẩn phải là `public`. Ví dụ sửa thành `public PublicUser(String name)`.

### 7.5. Khai báo `throws` trên normal canonical constructor

```java
record Code(String value) {
    Code(String value) throws Exception { // ERROR: throws clause.
        this.value = value;
    }
}
```

Normal canonical constructor không được có `throws` clause theo JLS. Điều này khác việc thân constructor có thể **ném unchecked exception** để báo dữ liệu sai, như `IllegalArgumentException` hoặc `NullPointerException`.

### 7.6. Khai báo hai canonical constructors cùng lúc

```java
record Code(String value) {
    Code {
        java.util.Objects.requireNonNull(value);
    }
    Code(String value) { // ERROR: duplicate canonical constructor.
        this.value = value;
    }
}
```

`Code { ... }` và `Code(String value) { ... }` là hai hình thức của **cùng một** canonical constructor. Chọn một dạng; cũng không thể định nghĩa nhiều compact constructors trong một record.

### 7.7. Nhầm record với class có constructor mặc định

```java
record Person(String name) {}
// new Person(); // ERROR: no zero-argument constructor.
```

Record `Person` có canonical constructor `Person(String name)`. Nếu muốn thêm một cách khởi tạo không có tham số, hãy khai báo overload `Person() { this("Anonymous"); }`, thay vì trông chờ compiler tự sinh no-arg constructor.

## 8. Điểm cần lưu ý trong dự án

**Validation do contract quyết định.** Record mặc định không từ chối `null`, chuỗi rỗng hay số âm. Nếu những đầu vào đó không hợp lệ với miền nghiệp vụ, đặt kiểm tra tại canonical constructor. Khi cần chuẩn hóa chuỗi, compact constructor thường dễ đọc hơn; khi cần gán field trực tiếp với logic rõ ràng, dùng dạng normal.

**Bất biến nông, không phải bất biến sâu.** Một component là `List`, mảng hoặc đối tượng có trạng thái có thể vẫn bị thay đổi ở bên trong. `List.copyOf` tạo danh sách không sửa được cấu trúc và không chứa phần tử null, nhưng không sao chép sâu các phần tử. Với mảng, có thể cần sao chép lúc nhận và lúc trả ra từ accessor để ngăn thay đổi ngoài ý muốn. Đừng hiểu nhầm `final` là toàn bộ đồ thị đối tượng đã bất biến.

**Generic và varargs vẫn tuân thủ header.** Với `record Box<T>(T value) {}`, tham số của canonical constructor có kiểu `T` thuộc record; normal canonical constructor tường minh không được khai báo bộ tham số kiểu riêng. Với `record Labels(String... tags) {}`, canonical constructor tương ứng nhận varargs, component field tương ứng mang kiểu mảng; việc sao chép để bảo vệ bất biến vẫn là trách nhiệm thiết kế.

**Không tự tạo thêm instance fields.** Record không cho khai báo các instance fields mới ngoài các field suy ra từ component; bạn có thể khai báo các thành phần `static` hợp lệ. Mọi trạng thái mang ý nghĩa dữ liệu của record nên được thể hiện đúng qua header.

**Thay header là thay hợp đồng.** Nếu đổi `record Point(int x, int y)` thành `record Point(int y, int x)`, các kiểu tham số đều là `int` nên mã gọi cũ vẫn có thể biên dịch nhưng **ý nghĩa vị trí tham số đã đổi**. Đây là rủi ro logic nghiêm trọng: phải rà soát các vị trí gọi và test hành vi, không chỉ nhìn biên dịch thành công.

## 9. Bài luyện tập và tiêu chí kiểm chứng

Viết `record EmailAddress(String value)` có **compact canonical constructor**, với contract luyện tập: từ chối `null`; bỏ khoảng trắng ở đầu/cuối; từ chối chuỗi trống; và yêu cầu một ký tự `@` nằm giữa ít nhất một ký tự bên trái và một ký tự bên phải. Đây chỉ là quy tắc **tối giản để học constructor**, không phải bộ xác thực địa chỉ email đầy đủ theo tiêu chuẩn Internet.

Dữ liệu thử:

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| `"  user@example.com  "` | Component `value` được lưu là `"user@example.com"` |
| `"user@example.com"` | Giữ nguyên |
| `""` hoặc `"   "` | `IllegalArgumentException` |
| `"invalid"`, `"@domain"`, `"user@"` | `IllegalArgumentException` |
| `null` | `NullPointerException` nếu contract dùng `Objects.requireNonNull` |

Sau đó thêm overload `EmailAddress()` ủy quyền tới canonical constructor với giá trị `"anonymous@example.com"`. Kiểm tra cả cách gọi có và không có tham số; thử cố ý viết `this.value = value;` trong compact constructor để nhận lỗi biên dịch, rồi sửa bằng cách gán cho **tham số** và để compiler xử lý field.

Một lời giải đạt yêu cầu khi bạn giải thích được: (1) chữ ký canonical được xác định thế nào từ header; (2) khi nào compiler tự sinh constructor; (3) dạng đầy đủ khác compact ở trách nhiệm gán field; (4) vì sao overload phải ủy quyền; (5) vì sao phải kiểm tra đầu vào và bảo vệ component mutable theo contract.

## Tham khảo đặc tả hiện hành

- [Java Language Specification — `8.10.4: Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4).
- [Oracle Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html).

**Ghi nhớ:** Header quyết định component và canonical constructor. Khi không viết constructor chuẩn, Java tự sinh và gán fields. Khi tự viết **normal canonical**, bạn phải gán fields. Khi viết **compact canonical**, bạn kiểm tra hoặc chuẩn hóa tham số và Java thực hiện các phép gán sau thân constructor. Tập trung mọi đường khởi tạo vào contract này giúp record nhất quán và dễ kiểm thử.