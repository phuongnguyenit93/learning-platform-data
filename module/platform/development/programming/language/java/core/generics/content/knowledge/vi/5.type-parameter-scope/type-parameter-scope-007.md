# Thành viên `static` dùng chung giữa các kiểu tham số hóa trong Java Generics

Khi một lớp Java khai báo `class Box<T>`, người dùng có thể tạo `Box<String>`, `Box<Integer>` hoặc `Box<Customer>`. Những cách sử dụng này có **hợp đồng kiểu khác nhau ở thời điểm biên dịch**, nhưng chúng không tạo ra các bản sao độc lập của lớp `Box` tại JVM. Vì vậy, **trường `static` khai báo trên `Box` là trạng thái chung** cho các đối tượng của cùng một lớp runtime, bất kể chúng được tham số hóa bằng đối số kiểu nào.

Điều này rất quan trọng nếu đặt bộ đếm đối tượng, cache, bộ đăng ký hoặc cấu hình dùng chung vào lớp generic. Nếu hiểu nhầm rằng mỗi `Box<String>` và `Box<Integer>` sở hữu một bản sao riêng của trường `static`, chương trình có thể thống kê sai dữ liệu, trộn trạng thái giữa các kiểu hoặc gặp lỗi đồng thời. Bài học làm rõ quy tắc của trường và phương thức `static`, cơ chế *type erasure*, khởi tạo lớp, phạm vi của `T`, và cách thiết kế thành viên `static` an toàn.

## 1. Trường instance và trường `static` khác nhau thế nào?

Ví dụ:

```java
class Box<T> {
    private final T value;
    private static int created;

    Box(T value) {
        this.value = value;
        created++;
    }

    T get() {
        return value;
    }

    static int createdCount() {
        return created;
    }
}
```

Đây là **khai báo lớp Java minh họa**, chưa có `main`. Hai trường có thời gian tồn tại và chủ sở hữu khác nhau:

- `value` là **trường instance**. Mỗi đối tượng `Box` có một trường `value` riêng. Với tham chiếu `Box<String>`, compiler kiểm tra `value` theo đối số kiểu `String` thông qua constructor/getter; với `Box<Integer>`, kiểu tương ứng là `Integer`.
- `created` là **trường `static` của lớp `Box`**. Các đối tượng `Box<String>` và `Box<Integer>` cùng truy cập một trường `created` thuộc định nghĩa lớp được JVM nạp. Cứ gọi constructor là bộ đếm tăng, dù đối tượng mới chứa kiểu gì.
- `createdCount()` là **phương thức `static`**. Nó đọc bộ đếm chung và được gọi thông qua tên lớp: `Box.createdCount()`.

Cần phân biệt **tham số kiểu `T`** với **đối số kiểu tại nơi sử dụng**. `T` mô tả quan hệ kiểu đối với những thành viên instance phù hợp; nó không tạo ra một không gian bộ nhớ `static` riêng cho mỗi `T`.

| Cách khai báo | Thuộc về | Có tách riêng cho mỗi `Box<String>` và `Box<Integer>`? |
|---|---|---|
| `private T value;` | Từng đối tượng `Box` | Mỗi đối tượng có trường riêng; compiler kiểm tra theo kiểu được tham số hóa. |
| `private static int created;` | Lớp runtime `Box` | **Không**; cùng trường chung cho mọi cách tham số hóa của cùng lớp được nạp. |
| `T get()` | Phương thức instance | Gọi trên từng đối tượng và dùng hợp đồng kiểu `T` tương ứng. |
| `static int createdCount()` | Lớp runtime `Box` | **Không**; một định nghĩa phương thức chung. |
| `static <U> Box<U> of(U value)` | Phương thức của lớp, có tham số kiểu riêng `U` | Một phương thức chung; `U` được suy luận riêng cho mỗi lời gọi. |

## 2. Ví dụ chạy được: một bộ đếm chung cho nhiều đối số kiểu

Lưu tệp **`SharedStaticDemo.java`**:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedStaticDemo {
    static final class Box<T> {
        private static final AtomicInteger CREATED = new AtomicInteger();
        private final T value;

        Box(T value) {
            this.value = Objects.requireNonNull(value, "value");
            CREATED.incrementAndGet();
        }

        T get() {
            return value;
        }

        static int createdCount() {
            return CREATED.get();
        }
    }

    public static void main(String[] args) {
        Box<String> first = new Box<>("Java");
        Box<Integer> second = new Box<>(17);
        Box<Double> third = new Box<>(2.5);

        System.out.println(first.get());
        System.out.println(second.get() + 1);
        System.out.println(third.get());
        System.out.println(Box.createdCount());
        System.out.println(first.getClass() == second.getClass());
        System.out.println(second.getClass() == third.getClass());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 SharedStaticDemo.java
java SharedStaticDemo
```

Kết quả chính xác (`stdout`):

```text
Java
18
2.5
3
true
true
```

**Vì sao in ra `3`?** Constructor `Box(T value)` được gọi ba lần. Cả ba lần đều tăng cùng một `AtomicInteger CREATED`. Không có bộ đếm riêng cho `Box<String>`, `Box<Integer>` hoặc `Box<Double>`.

**Vì sao in ra `true` hai lần?** Khi gọi `getClass()` trên ba đối tượng, JVM trả về cùng một đối tượng `Class` đại diện cho lớp lồng runtime `SharedStaticDemo.Box`. Khác biệt về đối số kiểu là kiểm tra kiểu ở mã nguồn; thông tin này không khiến JVM tạo ba lớp runtime chuyên biệt.

Ví dụ dùng `AtomicInteger` để thao tác tăng bộ đếm an toàn khi các constructor được gọi đồng thời. Với chương trình chỉ chạy tuần tự, `static int created; created++;` cũng cho cùng kết quả, nhưng `created++` không phải thao tác nguyên tử nếu nhiều luồng thực hiện cùng lúc. `AtomicInteger` **chỉ bảo vệ riêng thao tác bộ đếm**, không tự biến mọi thành viên khác của lớp thành thread-safe.

## 3. Vì sao các cách tham số hóa lại chia sẻ thành viên `static`?

Java triển khai phần lớn generics bằng cơ chế **type erasure**. Sau khi biên dịch, một lớp generic thông thường không được nhân bản thành các lớp runtime độc lập cho từng đối số kiểu:

```java
// Đoạn minh họa bên trong một phương thức:
Box<String> strings = new Box<>("hello");
Box<Integer> numbers = new Box<>(42);
```

Cả hai phép tạo đối tượng đều khởi tạo đối tượng của cùng lớp runtime `Box`. Các chữ ký generic được compiler kiểm tra và thông tin generic trong tệp `.class` có thể còn ở metadata để các công cụ đọc, nhưng JVM không duy trì hai bản sao trạng thái `static` cho riêng `String` và `Integer`.

Sơ đồ quan hệ:

```text
                   class Box<T>
                        |
                 JVM: class Box
                        |
             +----------+----------+
             |                     |
       static CREATED          static methods
             |
        một trạng thái chung
             |
      +------+------+ 
      |             |
Box<String>     Box<Integer>
instance A       instance B
value riêng      value riêng
```

Sơ đồ trên diễn đạt **một lớp runtime và các đối tượng riêng**, không phải các tiến trình hay bộ nhớ JVM tách biệt. Lớp `Box` vẫn được biên dịch với metadata generic nhằm hỗ trợ công cụ và kiểm tra kiểu, nhưng không có “bảng `static` theo từng đối số kiểu”.

Một hệ quả là cú pháp `Box<String>.class` không hợp lệ trong Java; class literal dùng tên kiểu có thể biểu diễn ở runtime, chẳng hạn `Box.class`. Tương tự, kiểm tra `instanceof Box<String>` không được phép vì đối số `String` không thể kiểm tra trực tiếp bằng `instanceof` sau erasure; `instanceof Box<?>` có thể dùng nếu chỉ cần xác nhận đối tượng thuộc lớp `Box`.

## 4. Khởi tạo thành viên `static`: một lần cho mỗi lớp được định nghĩa

Xét:

```java
class Sequence<T> {
    private static int nextId = 1;

    static int newId() {
        return nextId++;
    }
}
```

Đây là **khai báo lớp minh họa**. Trình tự hoạt động trong một môi trường thông thường:

1. JVM nạp/định nghĩa lớp `Sequence` và chuẩn bị trạng thái `static` của nó theo quy tắc JVM.
2. Khi có hành động yêu cầu khởi tạo lớp, các giá trị khởi tạo trường `static` và khối khởi tạo `static` được thực hiện theo thứ tự khai báo.
3. `Sequence.newId()` dùng chung `nextId` cho tất cả nơi gọi, bất kể ứng dụng dự định kết quả dùng trong `Sequence<String>` hay `Sequence<Integer>`.
4. Việc tạo thêm đối tượng `Sequence<U>` với một đối số kiểu khác **không** chạy lại phần khởi tạo `static` như một lần “khởi tạo cho `U`” mới.

Không nên hiểu thành “toàn bộ JVM luôn chỉ có đúng một bản sao” trong mọi tình huống. Một lớp có thể được định nghĩa riêng bởi các **class loader** khác nhau, và mỗi định nghĩa lớp như vậy có trạng thái `static` của nó. Trong thực hành, quy tắc nên nhớ là **cùng một lớp được định nghĩa bởi cùng class loader thì chia sẻ thành viên `static`**, không phân biệt đối số kiểu Java Generics.

### Kiểm chứng việc khởi tạo `static`

Lưu tệp **`InitializationDemo.java`**:

```java
public class InitializationDemo {
    static final class Token<T> {
        private static int created;

        static {
            System.out.println("Token initialized");
        }

        Token() {
            created++;
        }

        static int count() {
            return created;
        }
    }

    public static void main(String[] args) {
        Token<String> a = new Token<>();
        Token<Integer> b = new Token<>();
        System.out.println(Token.count());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 InitializationDemo.java
java InitializationDemo
```

`stdout`:

```text
Token initialized
2
```

Khối `static { ... }` được thực thi **một lần** khi lớp `Token` được khởi tạo, trước khi constructor đầu tiên chạy. Hai cách khởi tạo `Token<String>` và `Token<Integer>` không dẫn đến hai lần in `Token initialized`.

Lưu ý: **nạp lớp**, **liên kết lớp** và **khởi tạo lớp** là những bước khác nhau trong JVM. Không phải mọi thao tác nhìn thấy tên lớp ở mã nguồn đều bắt buộc chạy khối `static` ngay; ví dụ việc tham chiếu một hằng compile-time có thể không kích hoạt khởi tạo lớp khai báo hằng. Với ví dụ tạo đối tượng trên, việc khởi tạo lớp diễn ra trước khi constructor đầu tiên chạy.

## 5. Tại sao `static T shared` là lỗi biên dịch?

Nếu `T` là tham số kiểu của lớp:

```java
class InvalidBox<T> {
    // private static T lastValue;       // Sai
    // static T getLastValue() { ... }   // Sai
    // static void print(T value) { ... }// Sai nếu T là của lớp
}
```

Các dòng sai được **chú thích có chủ đích**. Java không cho thành viên `static` dùng trực tiếp biến kiểu không static `T` được khai báo trên lớp `InvalidBox<T>`.

Giải thích bằng một giả định mâu thuẫn: nếu `static T lastValue` được cho phép, sẽ có một trường dùng chung cho cả `InvalidBox<String>` và `InvalidBox<Integer>`. Một bên kỳ vọng trường là `String`, bên kia kỳ vọng `Integer`. JVM không thể bảo đảm cả hai hợp đồng kiểu cùng đúng đối với một trường chung trong mọi thao tác.

Cần phân biệt lỗi này với việc không thể tạo đối tượng bằng `new T()`. Cả hai liên quan đến generic nhưng thuộc hai quy tắc khác nhau: `static T field` dùng sai tham số kiểu trong ngữ cảnh static; `new T()` không hợp lệ do tham số kiểu không có đủ thông tin constructor runtime sau erasure, kể cả trong phương thức instance.

### Cách đúng: chọn kiểu cụ thể hoặc tham số kiểu của riêng phương thức

Một trường `static` có thể có **kiểu xác định độc lập với `T`**:

```java
class SafeBox<T> {
    private static long totalCreated;
    private final T value;

    SafeBox(T value) {
        this.value = value;
        totalCreated++;
    }

    static long totalCreated() {
        return totalCreated;
    }

    T get() {
        return value;
    }
}
```

Trường `totalCreated` thuộc một lớp runtime duy nhất; bản thân nó không cố mô tả giá trị `T` của từng đối tượng.

Nếu cần hàm `static` làm việc với nhiều loại giá trị, **khai báo tham số kiểu riêng của phương thức**:

```java
static <U> U identity(U input) {
    return input;
}
```

Đoạn này phải đặt trong một lớp. `<U>` không thuộc về instance nào, nên `identity("Java")` và `identity(42)` có thể cùng sử dụng định nghĩa phương thức `static` mà compiler vẫn kiểm tra quan hệ kiểu giữa tham số và kết quả ở từng lần gọi.

Chỉ đổi tên `T` thành `U` không phải bản chất của cách sửa; điều quan trọng là đặt **danh sách khai báo tham số kiểu riêng `<U>`** ở chữ ký phương thức.

## 6. Phương thức generic `static` không có trạng thái riêng theo đối số kiểu

Xét hai lời gọi:

```java
String text = Toolbox.<String>identity("Java");
Integer count = Toolbox.<Integer>identity(21);
```

Giả sử `Toolbox` khai báo `static <T> T identity(T input)`. Ở lời gọi đầu, compiler xác định `T = String`; ở lời gọi sau, `T = Integer`. Tuy nhiên, **phương thức `identity` không tự tạo hai vùng biến `static`** tương ứng. Mỗi lần gọi sử dụng các biến cục bộ và tham số của lần gọi đó; các thành viên `static` mà nó truy cập vẫn thuộc lớp khai báo.

### Ví dụ kết hợp factory generic và trạng thái static chung

Lưu thành **`FactoryCounterDemo.java`**:

```java
import java.util.Objects;

public class FactoryCounterDemo {
    static final class Box<T> {
        private static int count;
        private final T value;

        private Box(T value) {
            this.value = Objects.requireNonNull(value, "value");
            count++;
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        T get() {
            return value;
        }

        static int count() {
            return count;
        }
    }

    public static void main(String[] args) {
        Box<String> a = Box.of("spring");
        Box<Integer> b = Box.of(99);
        Box<String> c = Box.of("java");

        System.out.println(a.get().toUpperCase());
        System.out.println(b.get());
        System.out.println(c.get());
        System.out.println(Box.count());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FactoryCounterDemo.java
java FactoryCounterDemo
```

`stdout`:

```text
SPRING
99
java
3
```

Ở đây:

- `Box<T>` là lớp generic, còn `static <U> Box<U> of(U value)` là phương thức generic riêng.
- Compiler suy luận `U` cho từng lần gọi `Box.of(...)`.
- Constructor tăng `count` chung sau khi kiểm tra giá trị khác `null`.
- `Box<String>` và `Box<Integer>` vẫn chia sẻ cùng bộ đếm. Phương thức `of` không tạo bộ đếm riêng cho từng `U`.
- Ví dụ dùng `int count` để đơn giản hóa; nó chỉ phù hợp nếu không có yêu cầu cập nhật đồng thời. Khi đa luồng, thay bằng `AtomicInteger` hoặc cơ chế đồng bộ thích hợp.

## 7. Thành viên `static final` cũng dùng chung

Trường `static final` có thể biểu diễn cấu hình, hằng số hoặc tham chiếu chung:

```java
class CacheBox<T> {
    static final String DEFAULT_NAME = "cache";
    static final int MAX_ENTRIES = 100;
}
```

Những trường đó **không được nhân bản** thành một `DEFAULT_NAME` của `CacheBox<String>` và một `DEFAULT_NAME` khác của `CacheBox<Integer>`. Chúng thuộc lớp `CacheBox`.

Cần phân biệt hai nghĩa của `final`:

- Với `static final int MAX_ENTRIES = 100`, giá trị primitive cố định sau khi gán. Đây còn có thể là hằng tại thời điểm biên dịch.
- Với `static final List<String> ITEMS = new ArrayList<>()`, từ khóa `final` chỉ ngăn gán lại tham chiếu `ITEMS`; **nội dung danh sách vẫn có thể bị thay đổi** nếu đối tượng đó cho phép sửa. Danh sách là trạng thái chung giữa tất cả cách tham số hóa của lớp.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

class SharedMessages<T> {
    static final List<String> MESSAGES = new ArrayList<>();
}
```

Đây là **khai báo lớp minh họa**. Nếu một đối tượng được dùng qua `SharedMessages<String>` thêm phần tử vào `MESSAGES` và một đoạn mã khác dùng `SharedMessages<Integer>` đọc danh sách đó, chúng đang nhìn vào cùng một collection.

Để tránh mã bên ngoài vô tình sửa trạng thái chung, thường nên giữ trường mutable `static` ở quyền `private` và chỉ cung cấp API được kiểm soát. Đừng hiểu `final` là bảo đảm bất biến sâu.

## 8. Khi cần số liệu riêng theo từng kiểu: tự thiết kế cấu trúc phân nhóm

Có những bài toán thật sự cần thống kê riêng số hộp chứa `String`, `Integer` hoặc một loại đối tượng khác. **Java không tự chia trường `static` theo đối số generic**, vì vậy ứng dụng phải chọn khóa phân nhóm rõ ràng.

Một lựa chọn là truyền **`Class<T>`** làm type token ở ranh giới API, rồi dùng một map `static` được khóa bởi `Class<?>`. Trường map vẫn là **một map chung**; các nhóm được tách bằng khóa trong dữ liệu, không phải bằng các bản sao của lớp generic.

### Ví dụ thống kê có khóa theo lớp runtime

Tạo tệp **`PerClassStatsDemo.java`**:

```java
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class PerClassStatsDemo {
    static final class TypedBox<T> {
        private static final Map<Class<?>, AtomicInteger> COUNTS =
                new ConcurrentHashMap<>();

        private final Class<T> type;
        private final T value;

        TypedBox(Class<T> type, T value) {
            this.type = Objects.requireNonNull(type, "type");
            this.value = type.cast(value);
            COUNTS.computeIfAbsent(
                    type, ignored -> new AtomicInteger()).incrementAndGet();
        }

        T get() {
            return value;
        }

        Class<T> type() {
            return type;
        }

        static int countFor(Class<?> type) {
            AtomicInteger count = COUNTS.get(type);
            return count == null ? 0 : count.get();
        }
    }

    public static void main(String[] args) {
        TypedBox<String> a = new TypedBox<>(String.class, "A");
        TypedBox<Integer> b = new TypedBox<>(Integer.class, 1);
        TypedBox<String> c = new TypedBox<>(String.class, "B");

        System.out.println(a.get() + c.get());
        System.out.println(b.type().getSimpleName());
        System.out.println(TypedBox.countFor(String.class));
        System.out.println(TypedBox.countFor(Integer.class));
        System.out.println(TypedBox.countFor(Double.class));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PerClassStatsDemo.java
java PerClassStatsDemo
```

`stdout`:

```text
AB
Integer
2
1
0
```

Điểm cần phân biệt:

1. `COUNTS` vẫn chỉ là **một trường `static` chung** của `TypedBox`.
2. Mỗi khóa `String.class` hoặc `Integer.class` có một bộ đếm riêng **do chương trình tạo ra**.
3. `type.cast(value)` kiểm tra đối tượng theo `Class<T>` được truyền vào. Nếu giá trị không tương thích, phép cast ném `ClassCastException`.
4. `computeIfAbsent` trên `ConcurrentHashMap` cùng `AtomicInteger` giúp cập nhật bộ đếm an toàn cho trường hợp nhiều luồng tạo hộp cùng lúc; phần dữ liệu `value` của từng hộp được gán một lần ở constructor.
5. Trường hợp `null` cần quy định riêng: `Class.cast(null)` trả `null` nên không tự từ chối; nếu cần giá trị khác `null`, thêm `Objects.requireNonNull(value)`.

**Giới hạn của `Class<?>`:** type token như `List.class` chỉ phân biệt lớp runtime `List`, không phân biệt đầy đủ `List<String>` và `List<Integer>`. Nếu cần phân nhóm theo những kiểu tham số hóa lồng nhau, phải dùng một mô hình token giàu thông tin hơn và nêu rõ cách biểu diễn kiểu; không thể chỉ gọi `getClass()` rồi suy ra mọi đối số generic sau erasure.

## 9. Thành viên `static` và đa luồng: chia sẻ đồng nghĩa phải đồng bộ đúng

Nếu nhiều luồng tạo đồng thời các `Box<T>` khác kiểu, mọi constructor vẫn cập nhật cùng bộ đếm `static`. Ví dụ đơn giản:

```java
static int count;

Box(T value) {
    this.value = value;
    count++;
}
```

Đây là **mã minh họa đặt trong một lớp `Box<T>`**, giả sử các khai báo liên quan tồn tại. `count++` gồm đọc giá trị, cộng và ghi lại; thao tác đó **không nguyên tử**. Hai luồng có thể cùng đọc giá trị cũ rồi cùng ghi giá trị mới, dẫn đến bỏ sót lần tăng.

Giải pháp tùy mục tiêu:

| Nhu cầu | Cách làm thường dùng | Lưu ý |
|---|---|---|
| Bộ đếm chính xác dưới cập nhật đồng thời | `AtomicInteger.incrementAndGet()` hoặc `AtomicLong.incrementAndGet()` | Cập nhật nguyên tử, nhưng kiểu số vẫn có giới hạn tràn. |
| Đếm cập nhật rất nhiều luồng, ưu tiên thông lượng | `LongAdder.increment()` | Thích hợp thống kê; `sum()` khi đang cập nhật không phải snapshot tuyến tính hóa. |
| Cần giữ nhiều trường nhất quán theo một giao dịch nhỏ | `synchronized` hoặc khóa phù hợp | Chỉ dùng atomic cho một biến chưa đủ nếu nhiều biến phải thay đổi cùng nhau. |
| Cache map chia sẻ | `ConcurrentHashMap<K,V>` | Tính nguyên tử của các thao tác kết hợp phải được hiểu theo hợp đồng API. |
| Trạng thái không cần chia sẻ | Trường instance hoặc dữ liệu cục bộ phương thức | Giảm chia sẻ không cần thiết, giảm rủi ro đồng thời. |

Không thể giải quyết race condition bằng cách đổi `Box<String>` thành `Box<Integer>`: kiểu đối số generic không chia tách trạng thái `static`.

### Khi nào không nên dùng `static`?

Không nên dùng trường `static` chỉ vì muốn truy cập dữ liệu “từ bất kỳ đâu”. Cân nhắc liệu dữ liệu ấy thực sự có **vòng đời cấp lớp** hay gắn với từng đối tượng, yêu cầu, phiên làm việc hoặc tác vụ riêng. Nếu gắn với từng đối tượng, dùng trường instance `T value`. Nếu cần cấu hình/phụ thuộc chia sẻ nhưng có vòng đời theo ứng dụng, có thể quản lý bằng đối tượng dịch vụ hoặc cơ chế dependency injection thay vì ngầm lưu trạng thái mutable trong trường `static`.

## 10. Thành viên `static` của lớp lồng và của giao diện generic

### 10.1. Lớp lồng `static` không dùng `T` của lớp bao

```java
class Outer<T> {
    static final class Nested<U> {
        private final U value;

        Nested(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }
    }
}
```

`Nested<U>` có tham số kiểu `U` **của chính nó**, không lấy `T` của `Outer<T>`. Khi tạo:

```java
// Đoạn minh họa trong một phương thức:
Outer.Nested<String> first = new Outer.Nested<>("A");
Outer.Nested<Integer> second = new Outer.Nested<>(2);
```

Không cần một đối tượng `Outer<String>` để tạo `Outer.Nested<String>`. Tương tự quy tắc với phương thức `static`, static nested class có vị trí độc lập với cách tham số hóa của lớp bao.

### 10.2. Interface generic cũng có phương thức `static` dùng chung

```java
interface Formatter<T> {
    String format(T value);

    static <U> U identity(U value) {
        return value;
    }
}
```

`Formatter<T>` dùng `T` trong hợp đồng phương thức instance `format(T value)`. Nhưng `identity` là phương thức `static` của interface, nên nó khai báo tham số kiểu riêng `<U>`.

Có thể gọi `Formatter.identity("Java")`; không cần chọn một triển khai `Formatter<String>` và cũng không thể dùng `T` của interface trực tiếp để khai báo phương thức static. Trường khai báo trong interface là `public static final` theo quy tắc ngôn ngữ, không phải trường instance gắn với từng kiểu tham số hóa.

## 11. Phân biệt bộ đếm lớp generic với bộ đếm lớp con

Cùng một trường `static` được khai báo trên lớp cha có thể được lớp con truy cập nếu quyền truy cập cho phép. Việc hai lớp con khác nhau cùng kế thừa một lớp generic **không tự tạo bản sao mới** cho trường `static` của lớp cha.

Ví dụ:

```java
class Base<T> {
    protected static int total;

    Base() {
        total++;
    }
}

final class TextBox extends Base<String> { }
final class NumberBox extends Base<Integer> { }
```

Đây là **nhóm khai báo minh họa**. `TextBox` và `NumberBox` dùng hai cách tham số hóa của `Base<T>`, nhưng constructor của `Base` luôn tăng `Base.total`. Hai lớp con đều có quan hệ kế thừa với **cùng trường được khai báo ở `Base`**.

Nếu lớp con khai báo **một trường `static` mới cùng tên**, đó là *field hiding* (che khuất trường), tạo một trường khác thuộc lớp con. Điều ấy xuất phát từ **khai báo thêm trường**, không phải từ việc chọn đối số kiểu `String` hay `Integer`.

Tương tự, phương thức `static` có thể bị che khuất theo quy tắc static method hiding, không có dispatch đa hình giống phương thức instance được override. Khi cần gọi một tiện ích hoặc bộ đếm, nên ghi rõ tên **lớp khai báo** để tránh nhầm.

## 12. Quy tắc gọi và quan sát thành viên `static`

Hãy ưu tiên cú pháp:

```java
Box.createdCount();
Box.<String>of("Java");
```

Đây là **mẫu lời gọi**, giả sử `Box` định nghĩa hai phương thức `static` tương ứng. Tên lớp ở đầu lời gọi giúp người đọc thấy rõ thành viên thuộc về lớp, không phải một đối tượng `Box<String>` cụ thể.

Không nên diễn giải cú pháp `Box<String>.createdCount()` như cơ chế chọn một bộ đếm riêng theo `String`. Dạng gọi thành viên `static` nên dùng tên lớp generic ở dạng `Box`, không dùng một kiểu tham số hóa làm đối tượng sở hữu trạng thái riêng.

Nếu đã có tham chiếu:

```java
Box<String> item = Box.of("A");
```

một số thành viên `static` có thể được truy cập qua biểu thức trong Java, nhưng cách viết `item.createdCount()` gây hiểu nhầm rằng trạng thái phụ thuộc `item`. Trình biên dịch và công cụ kiểm tra mã thường khuyến nghị truy cập bằng tên lớp: `Box.createdCount()`.

**Một lưu ý về thời điểm chạy:** nếu dùng một biểu thức thay vì tên lớp để tham chiếu thành viên `static`, biểu thức định vị có thể vẫn được đánh giá theo quy tắc Java dù đối tượng không thực sự dùng làm “đích” gọi phương thức `static`. Vì vậy viết tên lớp trực tiếp vừa dễ hiểu vừa tránh các hiệu ứng phụ không cần thiết.

## 13. Các sai lầm thường gặp

| Nhận định hoặc đoạn mã | Vấn đề | Cách hiểu/cách sửa |
|---|---|---|
| “`Box<String>` có một bộ đếm static, `Box<Integer>` có một bộ đếm khác.” | Đối số kiểu không tạo bản sao lớp runtime. | Bộ đếm được khai báo trên `Box` là chung cho cả hai. |
| `static T last;` bên trong `class Box<T>` | `T` của lớp không được dùng trực tiếp ở static context. | Dùng kiểu cụ thể, trường instance `T` hoặc một thiết kế map có khóa kiểu phù hợp. |
| `static T identity(T value)` với `T` chỉ khai báo trên lớp | Phương thức static không thể dùng tham số kiểu của lớp. | `static <U> U identity(U value)`. |
| Đổi từ `static int count` sang `static final List<T> shared` | Vẫn dùng `T` của lớp trong thành viên static, nên không hợp lệ. | Dùng kiểu cố định hoặc quản lý dữ liệu theo khóa với hợp đồng rõ ràng. |
| “`static final List<String>` là bất biến sâu.” | `final` không ngăn sửa đối tượng danh sách. | Dùng dữ liệu bất biến hoặc bảo vệ quyền ghi. |
| `count++` từ nhiều luồng | Mất lần cập nhật do race condition. | Dùng `AtomicInteger`, `LongAdder` hoặc đồng bộ phù hợp. |
| “Mọi class loader trong JVM có cùng một biến static.” | Các class loader khác nhau có thể định nghĩa lớp cùng tên nhưng khác danh tính runtime. | Hiểu phạm vi chia sẻ theo từng định nghĩa lớp. |
| “`Box<String>.class` và `Box<Integer>.class` là hai class object.” | Class literal của kiểu được tham số hóa như vậy không hợp lệ. | Dùng `Box.class`; đối tượng tham số hóa có thể có cùng `getClass()`. |
| “Đổi `T` trong lời gọi generic static sẽ reset cache.” | Type argument chỉ là thông tin kiểu của lời gọi. | Nếu cần reset theo nhóm, thiết kế API với khóa nhóm rõ ràng. |
| “`static final` bảo đảm truy cập dữ liệu mutable an toàn đa luồng.” | `final` không làm mọi thao tác trên đối tượng được trỏ tới trở thành thread-safe. | Chọn kiểu dữ liệu đồng thời hoặc bảo vệ truy cập. |

## 14. Bài tập tự kiểm tra

**Câu 1.** Xét:

```java
class Bucket<T> {
    static int count;
    Bucket() { count++; }
}
```

Nếu tạo hai `Bucket<String>` và một `Bucket<Integer>` trong cùng lớp runtime rồi đọc `Bucket.count`, kết quả là bao nhiêu nếu không có thao tác khác?

**Câu 2.** Vì sao `static T latest;` không hợp lệ bên trong `class Bucket<T>`, dù `T` đã được khai báo?

**Câu 3.** Trong `static <U> Bucket<U> of(U item)`, `U` thuộc về lớp hay phương thức? Việc gọi `of("A")` rồi `of(12)` có tạo hai bản sao bộ đếm không?

**Câu 4.** Khi chương trình in `boxString.getClass() == boxInteger.getClass()` là `true`, điều đó nói gì về generics ở runtime?

**Câu 5.** Nếu muốn đếm riêng các hộp chứa `String` và `Integer`, có thể thiết kế một map `static` như thế nào? Tại sao vẫn nói chỉ có một trường `static`?

**Câu 6.** Tại sao bộ đếm `static int count` với `count++` có thể sai trong chương trình đa luồng? `AtomicInteger.incrementAndGet()` khắc phục điểm nào?

**Đáp án định hướng:** (1) `3` vì mọi lần chạy constructor tăng cùng một trường `static`. (2) Thành phần static không thể dùng trực tiếp tham số kiểu của lớp. (3) `U` thuộc phương thức, các lời gọi dùng chung một định nghĩa phương thức và một bộ đếm của lớp. (4) Các đối số kiểu không tạo lớp runtime chuyên biệt riêng; generics chủ yếu được kiểm tra lúc biên dịch. (5) Một `Map<Class<?>, AtomicInteger>` dùng `String.class`, `Integer.class` làm khóa; map vẫn là một trường chung của lớp. (6) `count++` không nguyên tử; atomic increment ngăn việc mất lần tăng do cập nhật đồng thời trên bộ đếm.

**Ghi nhớ:** Thành viên `static` thuộc về **lớp runtime được định nghĩa**, không thuộc riêng từng đối số kiểu của một lớp generic. `Box<String>`, `Box<Integer>` và `Box<Double>` có thể có dữ liệu instance khác nhau, nhưng chia sẻ các trường `static` của cùng `Box`. Nếu muốn dữ liệu được phân nhóm theo kiểu, hãy tự biểu diễn các nhóm bằng cấu trúc dữ liệu và khóa phù hợp, đồng thời bảo vệ trạng thái chung khi có nhiều luồng.
