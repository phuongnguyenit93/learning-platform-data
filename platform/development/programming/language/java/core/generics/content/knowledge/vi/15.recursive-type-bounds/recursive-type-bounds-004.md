# `Enum<E extends Enum<E>>` và quan hệ với kiểu enum cụ thể trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể đọc đúng giới hạn kiểu `E extends Enum<E>`, giải thích vì sao `enum Status` tương ứng với `Enum<Status>`, viết phương thức generic dùng được cho nhiều enum nhưng vẫn kiểm tra kiểu lúc biên dịch, và chọn đúng giữa `Enum<E>`, `Enum<?>`, `Class<E>`, `EnumSet<E>` và `EnumMap<E, V>`.

## 1. Giới hạn đệ quy trong khai báo `Enum`

Khai báo của lớp nền tảng Java có dạng:

```java
public abstract class Enum<E extends Enum<E>>
        implements Comparable<E>, java.io.Serializable {
    // Đây chỉ là phần khai báo minh họa chữ ký kiểu,
    // không phải mã nguồn đầy đủ của java.lang.Enum.
}
```

Ở đây:

- `E` là **tham số kiểu**.
- `E extends Enum<E>` ràng buộc `E` phải là một kiểu con của `Enum` được tham số hóa bằng **chính E**.
- `Enum<E>` là kiểu cha generic cung cấp hành vi chung cho các enum, trong đó có `name()`, `ordinal()`, `compareTo(E)` và `getDeclaringClass()`.
- Cách một tham số kiểu xuất hiện lại trong giới hạn của chính nó được gọi là **F-bounded polymorphism** (*giới hạn kiểu đệ quy*, hay *self-referential type bound*).

Chữ “đệ quy” ở đây nói về **quan hệ giữa các kiểu tại thời điểm biên dịch**. Nó không có nghĩa là phương thức gọi chính nó, đối tượng chứa chính nó vô hạn, hay Java phải tạo một chuỗi kế thừa vô tận.

Có thể đọc biểu thức `E extends Enum<E>` như sau: “Phương thức này chấp nhận một kiểu enum cụ thể E, mà lớp nền của kiểu đó là `Enum<E>`.”

## 2. Từ một khai báo `enum` đến `Enum<KiểuĐó>`

Xét hai enum độc lập:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

enum State {
    NEW, RUNNING, DONE
}
```

Về quan hệ kiểu, trình biên dịch xử lý chúng **tương đương về mặt kế thừa** với:

```java
// Sơ đồ khái niệm, KHÔNG phải Java được phép tự khai báo:
final class Priority extends Enum<Priority> { /* ... */ }
final class State extends Enum<State> { /* ... */ }
```

Đây là sơ đồ giải thích, **không phải hai lớp cần hoặc có thể tự viết**: Java cấm lớp thông thường kế thừa trực tiếp `java.lang.Enum`. Khi viết `enum Priority`, trình biên dịch tự tạo lớp enum, các hằng `LOW`, `MEDIUM`, `HIGH`, cùng cơ chế khởi tạo cần thiết. Một enum không thể `extends` một lớp khác và không thể kế thừa từ một enum khác, nhưng có thể `implements` interface.

Quan hệ quan trọng là:

| Kiểu cụ thể | Kiểu cha liên quan | Kiểu đối số của `Comparable` được kế thừa |
| --- | --- | --- |
| `Priority` | `Enum<Priority>` | `Comparable<Priority>` |
| `State` | `Enum<State>` | `Comparable<State>` |

Vì vậy, `Priority.LOW.compareTo(Priority.HIGH)` là hợp lệ. Việc so sánh với `State.NEW` không hợp lệ ở thời điểm biên dịch. Hai enum có thể chứa các tên hằng giống nhau, nhưng vẫn là **hai kiểu khác nhau**.

`Enum` tự triển khai `Comparable<E>`, nên chữ ký `compareTo(E other)` gắn tham số so sánh với đúng loại enum. Kết quả sắp xếp dựa trên thứ tự khai báo các hằng, không phải tên theo thứ tự chữ cái.

## 3. Viết thuật toán dùng chung mà vẫn giữ đúng kiểu

Cách dùng thường gặp là viết phương thức:

```java
static <E extends Enum<E>> E someOperation(E value) {
    // ...
}
```

Cấu trúc `<E extends Enum<E>>` **khai báo** tham số kiểu của phương thức; `E` đứng trước tên phương thức là **kiểu trả về**; `E value` là tham số của phương thức. Với mỗi lần gọi, trình biên dịch suy luận `E` từ enum thực tế: `Priority`, `State` hoặc một enum khác.

Ví dụ sau là chương trình Java 17+ hoàn chỉnh.

**Tệp `EnumBoundDemo.java`:**

```java
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Objects;

public class EnumBoundDemo {
    enum Level {
        LOW, MEDIUM, HIGH
    }

    enum Stage {
        NEW, RUNNING, DONE
    }

    static <E extends Enum<E>> E next(E current) {
        Objects.requireNonNull(current, "current");

        Class<E> enumType = current.getDeclaringClass();
        E[] constants = enumType.getEnumConstants();
        int nextIndex = (current.ordinal() + 1) % constants.length;
        return constants[nextIndex];
    }

    static <E extends Enum<E>> boolean before(E left, E right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.compareTo(right) < 0;
    }

    static <E extends Enum<E>> E byName(Class<E> enumType, String name) {
        return Enum.valueOf(enumType, name);
    }

    public static void main(String[] args) {
        System.out.println(next(Level.LOW));
        System.out.println(next(Stage.DONE));
        System.out.println(next(Level.HIGH));
        System.out.println(before(Level.LOW, Level.HIGH));

        EnumSet<Level> selected = EnumSet.of(Level.LOW, Level.HIGH);
        System.out.println(selected.contains(Level.HIGH));

        EnumMap<Level, String> captions = new EnumMap<>(Level.class);
        captions.put(Level.MEDIUM, "Trung bình");
        System.out.println(captions.get(Level.MEDIUM));

        System.out.println(byName(Level.class, "MEDIUM"));
        System.out.println(Level.LOW.getDeclaringClass().getSimpleName());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac EnumBoundDemo.java
java EnumBoundDemo
```

**Stdout chính xác:**

```text
MEDIUM
NEW
LOW
true
true
Trung bình
MEDIUM
Level
```

Giải thích từng phần:

1. `next` nhận một **giá trị enum cụ thể**, lấy lớp enum khai báo bằng `getDeclaringClass()`, rồi lấy danh sách hằng bằng `Class<E>.getEnumConstants()`. Phép modulo quay về hằng đầu tiên khi giá trị đang ở cuối.
2. `before` gọi `compareTo` với hai giá trị cùng một kiểu E. Ví dụ `before(Level.LOW, Level.HIGH)` trả về `true`.
3. `EnumSet<Level>` tạo tập hợp được ràng buộc với `Level`; `EnumMap<Level, String>` tạo bản đồ có khóa thuộc `Level`.
4. `byName` đưa một `Class<E>` cùng tên hằng cho `Enum.valueOf`, để kiểu trả về vẫn là E. `byName(Level.class, "MEDIUM")` trả về `Level.MEDIUM`.

**Ví dụ cố ý không biên dịch** nếu thêm vào `main` của chương trình:

```java
// before(Level.LOW, Stage.NEW);           // Không có cùng một E phù hợp.
// EnumSet<Stage> wrong = EnumSet.of(Level.LOW); // Sai kiểu phần tử.
// Level wrongValue = byName(Stage.class, "NEW"); // Kiểu trả về là Stage.
```

Những dòng này chỉ dùng để minh họa lỗi biên dịch; hãy giữ chúng ở dạng chú thích khi chạy chương trình.

## 4. Vì sao phải viết `E extends Enum<E>`, thay vì chỉ `E extends Enum`?

`Enum` là một lớp **generic**. Viết `Enum` mà không truyền tham số kiểu là dùng **raw type**, làm mất một phần kiểm tra kiểu của trình biên dịch và có thể dẫn đến cảnh báo unchecked.

So sánh:

```java
// Chữ ký khuyến nghị: giữ quan hệ đúng giữa E và Enum<E>.
static <E extends Enum<E>> E requireTyped(E constant) {
    return constant;
}

// Chữ ký minh họa raw type; tránh dùng cho API mới.
// static <E extends Enum> E requireRaw(E constant) {
//     return constant;
// }
```

Chữ ký đầu khẳng định rõ quan hệ `Enum<E>`, nhờ đó có thể dùng `compareTo(E)`, `Class<E>`, `EnumSet<E>` và `EnumMap<E, V>` đúng với các giới hạn kiểu của thư viện. Chữ ký raw type không biểu đạt được quan hệ này và tạo rủi ro cảnh báo unchecked khi thao tác sâu hơn.

Cũng cần phân biệt:

- `<E extends Enum<E>>`: **khai báo biến kiểu E có tên**, giữ một quan hệ thống nhất giữa nhiều tham số, giá trị trả về và `Class<E>`.
- `Enum<?>`: tham chiếu đến **một giá trị enum bất kỳ**, phù hợp khi chỉ cần đọc `name()`, `ordinal()` hoặc hiển thị. Dấu `?` không đảm bảo hai tham chiếu độc lập là cùng loại enum.
- `Enum` (raw): bỏ thông tin tham số generic; nên tránh trong mã mới.
- `Enum<Level>`: kiểu lớp nền đã gắn với một enum cụ thể; phương thức generic thường dùng `E` thay cho việc cố định `Level`.

Chẳng hạn, đoạn sau có thể hiển thị hai tên nhưng không nên cố so sánh chúng bằng `compareTo`:

```java
Enum<?> first = Level.LOW;
Enum<?> second = Stage.NEW;
System.out.println(first.name());
System.out.println(second.name());
// first.compareTo(second); // Không biên dịch: hai wildcard capture khác nhau.
```

Đoạn này minh họa trong phạm vi lớp `EnumBoundDemo` ở phần trước, nơi `Level` và `Stage` đã được khai báo.

## 5. Liên hệ với `Class<E>`, `Enum.valueOf`, `EnumSet` và `EnumMap`

Các API Java thường xuyên tái sử dụng cùng giới hạn đệ quy:

| API | Chữ ký hoặc cách dùng đại diện | Vai trò của `E` |
| --- | --- | --- |
| `Enum.valueOf` | `<T extends Enum<T>> T valueOf(Class<T>, String)` | Lớp truyền vào xác định chính xác kiểu enum trả về. |
| `Class<E>.getEnumConstants()` | `E[] getEnumConstants()` | Lấy các hằng dưới dạng mảng có đúng kiểu phần tử E. |
| `EnumSet` | `EnumSet<E extends Enum<E>>` | Tập hợp các hằng thuộc cùng một enum. |
| `EnumMap` | `EnumMap<K extends Enum<K>, V>` | Khóa thuộc cùng một enum, còn kiểu giá trị V tùy ý. |
| `Enum.compareTo` | `int compareTo(E other)` | Chỉ so sánh với hằng cùng kiểu enum cụ thể. |

Đặc biệt, `values()` là phương thức `static` được trình biên dịch cung cấp **trên từng enum cụ thể** (ví dụ `Level.values()`). Nó **không** phải phương thức instance hay static dùng chung trên `Enum<E>`; do đó không thể viết `E.values()` bên trong một phương thức generic.

Khi cần các hằng từ kiểu generic, truyền `Class<E>` hoặc lấy `current.getDeclaringClass()`, rồi gọi `getEnumConstants()`. Một mẫu API hữu ích, đặt **bên trong một lớp Java**, là:

```java
static <E extends Enum<E>> EnumSet<E> allOf(Class<E> type) {
    return EnumSet.allOf(type);
}

static <E extends Enum<E>, V> EnumMap<E, V> newMap(Class<E> type) {
    return new EnumMap<>(type);
}
```

`EnumSet` và `EnumMap` chuyên biệt cho khóa hoặc phần tử enum, thường tiết kiệm bộ nhớ và hiệu quả hơn cấu trúc tổng quát trong trường hợp phù hợp. `EnumSet` không chấp nhận phần tử `null`; `EnumMap` không cho khóa `null` nhưng cho phép giá trị `null`.

Lưu ý khi dùng `Enum.valueOf`: tên phải **khớp chính xác** tên hằng khai báo, có phân biệt hoa/thường; tên không tồn tại dẫn đến `IllegalArgumentException`, tham số `null` có thể dẫn đến `NullPointerException`. Nếu đầu vào đến từ người dùng, hãy xác thực hoặc xử lý ngoại lệ tại ranh giới nhập liệu.

## 6. Trường hợp enum có thân lớp riêng cho từng hằng

Một enum có thể khai báo phần thân riêng cho hằng (*constant-specific class body*) để ghi đè phương thức:

**Tệp `EnumClassDemo.java`:**

```java
public class EnumClassDemo {
    enum Operation {
        ADD {
            @Override
            int apply(int a, int b) {
                return a + b;
            }
        },
        SUBTRACT {
            @Override
            int apply(int a, int b) {
                return a - b;
            }
        };

        abstract int apply(int a, int b);
    }

    public static void main(String[] args) {
        System.out.println(Operation.ADD.getClass() == Operation.class);
        System.out.println(Operation.ADD.getDeclaringClass() == Operation.class);
        System.out.println(Operation.ADD.compareTo(Operation.SUBTRACT) < 0);
        System.out.println(Operation.ADD.apply(2, 3));
    }
}
```

Chạy:

```bash
javac EnumClassDemo.java
java EnumClassDemo
```

Stdout:

```text
false
true
true
5
```

Với `ADD`, `getClass()` trả về lớp runtime riêng do trình biên dịch tạo cho thân hằng, nên kết quả so với `Operation.class` là `false`. Trong khi đó, `getDeclaringClass()` vẫn trả về `Operation.class`: đó là **loại enum đang khai báo hằng**. Cả `ADD` và `SUBTRACT` vẫn có quan hệ kiểu `Enum<Operation>` và được `compareTo` với nhau.

Do đó, trong thư viện generic làm việc với enum, **ưu tiên `getDeclaringClass()`** để lấy `Class<E>`. Đừng giả định rằng `constant.getClass() == SomeEnum.class` luôn đúng.

## 7. F-bound giúp gì và không đảm bảo điều gì?

Giới hạn đệ quy cũng xuất hiện bên ngoài enum:

```java
abstract class SelfTyped<T extends SelfTyped<T>> {
    abstract T copy();
}
```

Ý tưởng là diễn đạt các thao tác trả về hoặc nhận một kiểu liên hệ với chính kiểu cài đặt. Tuy nhiên, với các lớp generic tự định nghĩa, F-bound **không tự chứng minh T chính là lớp hiện tại**. Về mặt hệ thống kiểu, một lớp có thể truyền kiểu khác miễn là kiểu đó thỏa mãn giới hạn. Với `enum`, Java có thêm quy tắc ngôn ngữ: việc kế thừa `Enum<E>` được trình biên dịch ấn định theo từng enum, tạo ra quan hệ tự tham chiếu đúng với lớp enum cụ thể.

Cũng vì vậy, F-bound **không** làm xuất hiện một “kiểu E” có thể khởi tạo tùy ý ở runtime. Generic của Java sử dụng **type erasure**; mã generic không thể viết `new E()`, `new E[10]` hoặc `E.values()`. Với enum, cũng không thể tự tạo hằng bằng `new Level()`. Lấy hằng qua `Level.values()`, `Class<E>.getEnumConstants()` hoặc tra cứu bằng `Enum.valueOf`.

## 8. Các lỗi hay gặp và cách khắc phục

| Sai lầm | Vì sao sai hoặc dễ lỗi | Cách làm đúng |
| --- | --- | --- |
| Dùng `<E extends Enum>` trong API mới | Raw type mất mối liên hệ `E` với `Enum<E>`. | Dùng `<E extends Enum<E>>`. |
| Đưa hai enum khác loại vào cùng phép `compareTo` | `Comparable<E>` ràng buộc kiểu so sánh; kiểu enum khác không phù hợp. | Chỉ so sánh cùng E hoặc định nghĩa logic chuyển đổi rõ ràng. |
| Gọi `E.values()` | `values()` sinh trên từng enum cụ thể, không tồn tại trên biến kiểu. | Dùng `Class<E>.getEnumConstants()`. |
| Dùng `getClass()` để xác định enum khai báo | Hằng có thân lớp riêng có thể có subclass runtime. | Dùng `getDeclaringClass()`. |
| Dùng `ordinal()` làm ID lưu database hoặc giao thức | Chèn/đổi thứ tự khai báo làm ordinal thay đổi. | Dùng mã định danh ổn định được định nghĩa riêng; thận trọng cả khi đổi `name()`. |
| Ép kiểu giữa `Enum<?>` hoặc dùng raw `Enum` để né lỗi | Bỏ qua kiểm tra kiểu và có thể gặp lỗi runtime. | Giữ `Class<E>`/tham số E đi cùng dữ liệu từ đầu. |
| So sánh tên hằng để suy ra thứ tự | Thứ tự enum theo **khai báo**, không theo chữ cái. | Dùng `compareTo` khi thực sự muốn thứ tự khai báo, hoặc comparator nghiệp vụ riêng. |

Một lựa chọn đơn giản: khi hàm **chỉ cần in tên**, `Enum<?>` thường đủ. Khi hàm cần **trả về đúng kiểu enum**, so sánh hai hằng, lập tập hợp hoặc bản đồ enum, hãy dùng tham số `<E extends Enum<E>>`.

## 9. Bài tập tự kiểm tra

1. Với `enum Color { RED, GREEN, BLUE }`, hãy dự đoán `next(Color.BLUE)` theo thuật toán phần 3. **Đáp án:** `RED`, vì toán tử modulo quay về vị trí 0.
2. Vì sao `before(Level.LOW, Stage.NEW)` bị từ chối khi biên dịch? **Đáp án:** `Level` và `Stage` có quan hệ lần lượt với `Enum<Level>` và `Enum<Stage>`; không có một E phù hợp cho cả hai đối số.
3. Với enum có constant-specific class body, nên dùng `getClass()` hay `getDeclaringClass()` để truy xuất `Class<E>`? **Đáp án:** `getDeclaringClass()`.
4. Trong phương thức `static <E extends Enum<E>>`, vì sao không thể gọi `E.values()`? **Đáp án:** E là tham số kiểu, còn `values()` là phương thức static được tạo riêng cho từng lớp enum.
5. Khi nào không nên dùng `ordinal()`? **Đáp án:** Khi cần ID bền vững để lưu hoặc trao đổi dữ liệu giữa các phiên bản phần mềm.

**Ghi nhớ:** `Enum<E extends Enum<E>>` kết nối mỗi kiểu enum cụ thể với chính kiểu đó trong hệ thống generic. Nhờ quan hệ này, một thuật toán có thể áp dụng cho nhiều enum mà vẫn bảo toàn kiểu tham số, kiểu trả về và thao tác so sánh ngay từ lúc biên dịch.
