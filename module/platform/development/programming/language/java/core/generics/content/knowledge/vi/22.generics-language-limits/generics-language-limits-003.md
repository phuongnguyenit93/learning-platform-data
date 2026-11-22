# Không dùng tham số kiểu của lớp trong ngữ cảnh `static` — Java Generics

Khi một lớp Java được khai báo `class Box<T>`, tham số kiểu `T` thuộc về **khai báo lớp generic và cách sử dụng lớp dưới kiểu tham số hóa**, ví dụ `Box<String>` hoặc `Box<Integer>`. Nhưng thành viên `static` gắn với **lớp**, không gắn riêng với từng cách chọn đối số kiểu. Vì vậy, Java **không cho phép sử dụng trực tiếp tham số kiểu `T` của lớp trong các khai báo và ngữ cảnh static**.

```java
// Mã CỐ Ý KHÔNG BIÊN DỊCH: minh họa lỗi cần hiểu.
class Box<T> {
    T value;                   // Hợp lệ: instance field
    void set(T value) { }      // Hợp lệ: instance method

    // static T cached;                   // Lỗi
    // static T getCached() { return null; } // Lỗi
    // static void save(T value) { }       // Lỗi
}
```

Tuy nhiên, điều này **không có nghĩa phương thức static bị cấm dùng generics**. Phương thức static có thể **tự khai báo type parameter riêng**:

```java
class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    static <U> Box<U> of(U value) { // Hợp lệ: U thuộc phương thức of
        return new Box<>(value);
    }
}
```

Sự phân biệt giữa **`T` của lớp** và **`U` của phương thức static** là trọng tâm của bài. Tính đúng/sai không phụ thuộc việc tên biến kiểu là chữ `T` hay `U`, mà phụ thuộc **scope của nơi khai báo type parameter**.

## 1. Tách biệt tham số kiểu của lớp và biến/thành viên static

Hãy xét cùng một generic class:

```java
class Holder<T> {
    private T value;             // Mỗi instance có field value của nó
    static int created;          // Field chung của runtime class Holder

    Holder(T value) {
        this.value = value;
        created++;
    }

    T get() {
        return value;
    }
}
```

Sử dụng:

```java
Holder<String> a = new Holder<>("An");
Holder<Integer> b = new Holder<>(42);
System.out.println(Holder.created); // 2
```

Hai kiểu tĩnh `Holder<String>` và `Holder<Integer>` **khác nhau về cách compiler kiểm tra generic**, nhưng thường dùng **cùng một runtime class `Holder`** do type erasure. Vì vậy, biến `static int created` chỉ có **một bản cho runtime class được nạp bởi class loader tương ứng**, không được sao chép riêng thành `created` cho `String` và `Integer`.

Nếu Java cho viết `static T lastValue`, hãy thử hỏi:

- Khi gán `Holder<String>.lastValue = "Java"`, trường đó phải nhận `String`?
- Khi gán `Holder<Integer>.lastValue = 7`, cùng trường đó phải nhận `Integer`?
- Nếu chỉ có một static field chung, kiểu nào là hợp đồng an toàn cho cả hai?

Không có câu trả lời nhất quán nếu coi `T` của lớp là một kiểu riêng biệt cho mỗi phiên bản static field trong mô hình Java Generics thông thường. Java giải quyết từ **hệ thống kiểu ở compile time** bằng cách cấm tham chiếu trực tiếp `T` của lớp trong static context.

**Chú ý:** `static` không đồng nghĩa “chỉ tạo một instance object của lớp”. Mỗi `new Holder<...>()` vẫn tạo đối tượng riêng với instance field riêng; chỉ **thành viên static** không được nhân theo từng đối số kiểu.

## 2. Những ngữ cảnh static không được dùng `T` của lớp

Với:

```java
class Cache<T> {
    // Các ví dụ khác nhau bên dưới được xét độc lập.
}
```

Những vị trí sau đều sai nếu sử dụng chính `T` của `Cache<T>`:

| Vị trí | Mã minh họa bị cấm | Lý do |
| --- | --- | --- |
| Kiểu của static field | `static T item;` | Field static không có đối số kiểu của lớp riêng để chọn `T` |
| Tham số static method | `static void put(T item)` | Method static không nằm trong ngữ cảnh dùng type parameter của lớp |
| Kiểu trả về static method | `static T get()` | Không có `T` lớp nào được method static dùng |
| Kiểu local trong static method | `static void run() { T t; }` | Thân static method không được tham chiếu `T` của lớp |
| Static initialization block | `static { T x = null; }` | Static initializer là static context |
| Kiểu trong static member class | `static class Entry { T value; }` | Static nested class không mang type parameter của enclosing class |
| Dùng `T` như đối số generic trong static field | `static List<T> list;` | Dù `List` hợp lệ, `T` của lớp vẫn không nằm trong scope này |

Một số snippet ở bảng bỏ qua dấu ngoặc đóng và được viết để biểu thị **vị trí sai**, không phải chương trình hoàn chỉnh.

### Lỗi `non-static type variable T cannot be referenced from a static context`

Tùy trình biên dịch, khi viết:

```java
class Wrong<T> {
    static T data;
}
```

bạn có thể gặp thông báo dạng:

```text
non-static type variable T cannot be referenced from a static context
```

Chẩn đoán nói rằng biến kiểu `T` được khai báo tại lớp generic không được tham chiếu ở static context. Đừng nhầm với thông báo `non-static variable ... cannot be referenced from a static context` khi cố gọi **instance field** từ static method: hai lỗi có liên quan ý tưởng tách biệt static/instance nhưng là những quy tắc khác nhau.

### Static method không có implicit `this`

Một static method không có đối tượng `this` gắn với lời gọi. Nó không thể viết `this.value` hoặc tham chiếu trực tiếp instance field không qua một object. Tương tự, nó không thể sử dụng trực tiếp type parameter `T` của class để tuyên bố tham số/trả về vì static method không được gắn với một cách tham số hóa lớp cụ thể.

Tuy nhiên, static method hoàn toàn có thể **nhận một đối tượng `Holder<U>` làm tham số**, nhờ type parameter tự khai báo `U`; điều này sẽ được trình bày ở phần factory và generic static method.

## 3. Instance field, instance method và constructor dùng `T` thế nào?

Ở **ngữ cảnh instance**, type parameter của lớp có thể được sử dụng:

```java
class Parcel<T> {
    private T content;

    Parcel(T content) {      // Constructor nhận T của lớp
        this.content = content;
    }

    T get() {                // Instance method trả T
        return content;
    }

    void replace(T next) {   // Instance method nhận T
        content = next;
    }
}
```

Khi gọi:

```java
Parcel<String> label = new Parcel<>("A");
label.replace("B");
String text = label.get();

// label.replace(42); // Không biên dịch: Integer không phù hợp String
```

Compiler xem `content` và phương thức `replace` qua kiểu `Parcel<String>`. Với `Parcel<Integer>`, compiler kiểm tra một bộ quy tắc tương ứng với `Integer` cho instance API. Không có static field nào phải đồng thời đóng vai trò `String` và `Integer`.

Constructor của generic class có thể tham chiếu type parameter lớp vì nó **xây dựng instance** có cách tham số hóa cụ thể ở mã nguồn. Đừng suy ra mọi constructor đều là static chỉ vì cú pháp `new` tạo object.

### Một instance method cũng có thể khai báo type parameter riêng

```java
class PairBox<T> {
    T first;

    <U> U takeSecond(U other) {
        return other;
    }
}
```

Trong `PairBox<T>`, `T` thuộc class, còn `U` thuộc method `takeSecond`. Đây là hai scope độc lập, tương tự nguyên tắc áp dụng cho static generic method.

## 4. Cú pháp đúng của static generic method: `static <U> ...`

Định nghĩa một static factory:

```java
class Box<T> {
    private final T item;

    private Box(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }

    static <U> Box<U> of(U item) {
        return new Box<>(item);
    }
}
```

Dòng quan trọng:

```java
static <U> Box<U> of(U item)
```

- `static`: method thuộc class, không cần instance để gọi.
- `<U>`: **khai báo** type parameter mới của phương thức `of`.
- `Box<U>`: method trả một đối tượng `Box` dùng type argument `U`.
- `U item`: kiểu tham số của chính method là `U`.
- `new Box<>(item)`: compiler suy luận type argument phù hợp để tạo object.

Caller:

```java
Box<String> name = Box.of("An");
Box<Integer> age = Box.of(20);
```

Dù `of` là static, compiler có thể suy luận `U = String` ở lời gọi thứ nhất và `U = Integer` ở lời gọi thứ hai. Điều này **không có nghĩa `of` đã sử dụng `T` của class**. `U` là type variable **được khai báo riêng cho từng lời gọi generic method** ở mức kiểu nguồn, còn runtime vẫn dùng erasure tương ứng.

### Thiếu `<U>` là sai

```java
// KHÔNG BIÊN DỊCH trong Box<T>:
static Box<U> of(U item) {
    return new Box<>(item);
}
```

Tên `U` chưa được khai báo nên không thể dùng làm type variable. Nếu đổi `U` thành `T` của class mà không khai báo type parameter của method, vẫn bị lỗi static context.

### Đặt `<U>` ở đúng vị trí

Với method generic, phần khai báo type parameter nằm **sau các modifier**, **trước return type**:

```java
public static <U> U identity(U value) {
    return value;
}
```

Không đặt `<U>` sau kiểu trả về như cách ghi type argument khi **gọi** generic method.

## 5. Dùng cùng tên `T` cho class và static method: hợp lệ nhưng dễ hiểu nhầm

Java cho phép một static method khai báo type parameter riêng có tên trùng `T` của class:

```java
class Example<T> {
    static <T> T identity(T value) {
        return value;
    }
}
```

Đây là **hai type variables khác nhau** dù cùng có tên `T`. Trong phạm vi method, `T` của `identity` **che khuất (shadows)** tên `T` của class:

```java
Example<String> text = new Example<>();
Integer value = Example.identity(42); // Hợp lệ: T của method là Integer
```

Lệnh này không hề yêu cầu `T` của class là `Integer`; `identity` có type parameter độc lập.

**Khuyến nghị:** trong code dễ gây nhầm, dùng tên `U`, `R`, `V` hoặc tên type parameter có ý nghĩa để phân biệt static method type parameter với class type parameter. Việc dùng `static <T>` không sai, nhưng có thể khiến người mới tưởng method static đang tham chiếu `T` của class.

## 6. Static generic method có thể nhận instance của class generic

Một cách hợp lệ để làm việc với `Box<T>` trong static code là **truyền object đã mang type argument cụ thể ở mã nguồn vào tham số**:

```java
class Holder<T> {
    private final T data;

    Holder(T data) {
        this.data = data;
    }

    T get() {
        return data;
    }

    static <U> U extract(Holder<U> source) {
        return source.get();
    }

    static void printUnknown(Holder<?> source) {
        Object value = source.get();
        System.out.println(value);
    }
}
```

Ở đây:

- `extract` tự khai báo `U`, sau đó ràng buộc kiểu `Holder<U>` của tham số và kiểu trả về `U`.
- `printUnknown` không cần khai báo type parameter: `Holder<?>` thể hiện một `Holder` có kiểu phần tử chưa biết, nên đọc được giá trị như `Object`.
- Không phương thức nào dùng `T` của khai báo `Holder<T>` trong static context.

Với caller:

```java
Holder<String> source = new Holder<>("Java");
String value = Holder.extract(source); // U suy luận là String
Holder.printUnknown(source);           // In Java
```

Đây là cách thông thường để các utility static xử lý generic instance **mà vẫn giữ type safety**, thay vì cố truy cập trực tiếp `T` lớp bên ngoài static method.

### `static` không cấm kiểu tham số hóa trong chữ ký

Hai khai báo sau hoàn toàn có thể hợp lệ:

```java
static void show(Holder<String> value) { /* ... */ }

static <U> void showGeneric(Holder<U> value) { /* ... */ }
```

Dòng đầu dùng `String` là **một kiểu cụ thể** trong tham số. Dòng sau tự khai báo `U`. Chúng không dùng type variable `T` từ khai báo class. Vì vậy đừng khái quát sai rằng “static method không được viết `Box<...>`”.

## 7. Static field nào hợp lệ trong generic class?

Không được viết `static T item;`, nhưng Java cho phép static field có kiểu **không phụ thuộc `T` của class**:

```java
class Registry<T> {
    static int count;
    static String name = "Shared registry";
    static java.util.List<?> snapshot = java.util.List.of();

    T value;
}
```

Cả `int`, `String` và `List<?>` đều không phụ thuộc type variable `T`. Field `snapshot` dùng wildcard, không cam kết một type argument cụ thể của `Registry<T>`.

Tuy nhiên, cần phân biệt:

```java
// KHÔNG HỢP LỆ trong Registry<T>:
// static java.util.List<T> values;
```

với:

```java
// HỢP LỆ: kiểu phần tử được cố định là String, không phải T của class.
static java.util.List<String> names = new java.util.ArrayList<>();
```

Một static field `List<String>` **không được phân chia riêng theo `Registry<String>` và `Registry<Integer>`**; nó là field chung thuộc runtime class `Registry`. Nếu nó mutable, mọi caller có thể tác động tới một nguồn trạng thái chung. Chỉ sử dụng kiểu cố định khi thiết kế thật sự muốn điều đó.

### Static counter có thể phục vụ thống kê chung

```java
class Counter<T> {
    static int created;

    Counter() {
        created++;
    }
}
```

Hai lệnh `new Counter<String>()` và `new Counter<Integer>()` đều tăng cùng field `Counter.created`. Đây là một đặc tính của thành viên static, **không phải một counter riêng cho mỗi tham số kiểu**. Nếu nhiều thread tăng counter đồng thời, `created++` còn có vấn đề atomicity; muốn đếm thread-safe cần cơ chế đồng bộ hoặc atomic thích hợp, nhưng đó là vấn đề khác với generics.

## 8. Static initializer và static context: không có `T` lớp

Static initializer chạy gắn với việc khởi tạo class, không phụ thuộc một instance `Box<String>` hay `Box<Integer>` nào:

```java
class Settings<T> {
    static java.util.List<String> defaults;

    static {
        defaults = java.util.List.of("A", "B"); // Hợp lệ
        // T initial = null;                    // Không hợp lệ
    }
}
```

Bất kể sau này code dùng `Settings<Integer>` hay `Settings<String>`, khối static initializer không được phép sử dụng chính `T` của class. Việc tồn tại dấu `<T>` trên tên lớp **không làm một static initializer trở thành generic**.

Không có cú pháp khai báo một **static generic initializer block** kiểu `static <U> { ... }`. Nếu cần logic generic, tạo static generic method riêng và gọi method đó với đối số kiểu được suy luận từ các giá trị/tham số thích hợp.

## 9. Static nested class cũng không thấy `T` của enclosing class

Một generic outer class có thể chứa **static nested class**:

```java
class Outer<T> {
    static class Nested<U> {
        U data;

        Nested(U data) {
            this.data = data;
        }
    }
}
```

`Nested<U>` là một type generic **riêng**, khai báo type parameter `U` của chính nó. Nó không tự động “nhận” `T` của `Outer<T>`.

Cách dùng:

```java
Outer.Nested<String> text = new Outer.Nested<>("A");
Outer.Nested<Integer> number = new Outer.Nested<>(7);
```

Để thấy điều không hợp lệ:

```java
class Outer<T> {
    static class Wrong {
        // T item; // Lỗi: không dùng T của Outer trong static nested class
    }
}
```

Do nested class có modifier `static`, nó không mang implicit enclosing instance; cũng không mang type argument `T` của một đối tượng `Outer<T>` nào.

### So với non-static inner class

```java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    class Inner {
        T getOuterValue() {
            return value;
        }
    }
}
```

`Inner` ở đây là **non-static inner class**. Nó gắn với một đối tượng `Outer<T>`, nên có thể dùng `T` của outer.

```java
Outer<String> outer = new Outer<>("Java");
Outer<String>.Inner inner = outer.new Inner();
String s = inner.getOuterValue();
```

Hai đoạn `Outer` ở trên là **hai phương án khai báo độc lập**, không chép đồng thời hai class cùng tên vào một file. Ví dụ runnable ở mục 11 sử dụng cả nested static và inner non-static với tên khác nhau để bạn kiểm chứng.

## 10. Phân biệt lỗi `static T` với những giới hạn khác của type variable

Không phải mọi chỗ Java từ chối `T` đều do static context. So sánh bốn ví dụ **cố ý không biên dịch** trong một class generic:

```java
class GenericTools<T> {
    // static T shared;       // Sai: T của lớp trong static context.
    void example(Object x) {
        // T item = new T();   // Sai: không có constructor cho T.
        // Class<T> c = T.class; // Sai: type variable không có class literal.
        // T[] arr = new T[2]; // Sai: generic array creation.
        // boolean b = x instanceof T; // Sai: T không reifiable.
    }
}
```

Dù `example` là **instance method**, bốn dòng cuối vẫn không hợp lệ. Chúng liên quan tới type erasure/reifiability, không phải việc chia sẻ static member. Tùy mục đích: dùng `Supplier<? extends T>` để tạo object, `Class<T>` để kiểm tra runtime class, `IntFunction<T[]>` hoặc array factory để tạo mảng, và `List<T>` khi không cần mảng.

**Câu hỏi chẩn đoán:** nếu xóa từ khóa `static` mà code vẫn sai, đó không phải lỗi chỉ do scope static. Phân biệt hai nguyên nhân giúp chọn factory, class token hoặc API instance thích hợp, thay vì dùng một unchecked cast để che lỗi.

## 11. Chương trình Java 17+ chạy được: static và instance cùng tồn tại

Lưu mã vào tệp **`StaticTypeParameterDemo.java`**:

```java
public class StaticTypeParameterDemo {
    static final class Box<T> {
        private final T value;

        private Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static int created;

        // U do phương thức static tự khai báo.
        static <U> Box<U> of(U value) {
            created++;
            return new Box<>(value);
        }

        static <U extends Number> double twice(U number) {
            return number.doubleValue() * 2;
        }

        // T dưới đây thuộc method identity, không phải Box<T>.
        static <T> T identity(T input) {
            return input;
        }

        // Static nested class có type parameter V riêng.
        static final class Tag<V> {
            private final V value;

            Tag(V value) {
                this.value = value;
            }

            V get() {
                return value;
            }
        }

        // Non-static inner class nhìn thấy T của Box<T>.
        final class Inner {
            T outerValue() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Box<String> text = Box.of("Java");
        Box<Integer> number = Box.of(42);

        System.out.println("String box: " + text.get());
        System.out.println("Integer box: " + number.get());
        System.out.println("Shared static count: " + Box.created);
        System.out.println("Static generic identity: "
                + Box.identity("hello"));
        System.out.println("Bounded static method: " + Box.twice(3));

        Box.Tag<Long> tag = new Box.Tag<>(99L);
        System.out.println("Static nested tag: " + tag.get());

        Box<String>.Inner inner = text.new Inner();
        System.out.println("Non-static inner sees T: "
                + inner.outerValue());
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 StaticTypeParameterDemo.java
java StaticTypeParameterDemo
```

Standard output:

```text
String box: Java
Integer box: 42
Shared static count: 2
Static generic identity: hello
Bounded static method: 6.0
Static nested tag: 99
Non-static inner sees T: Java
```

Ý nghĩa từng dòng:

1. `Box<String>` và `Box<Integer>` dùng instance field `value` riêng; compiler kiểm tra `get()` theo `String` hoặc `Integer` ở từng caller.
2. Cả hai lệnh `Box.of(...)` tăng **cùng** static field `Box.created`, nên giá trị là 2.
3. `Box.identity("hello")` hợp lệ dù method dùng tên `T`: tên đó là **type parameter do method tự khai báo**, được suy luận từ đối số `"hello"`.
4. `Box.twice(3)` suy luận `U = Integer`; ràng buộc `U extends Number` cho phép gọi `doubleValue()`.
5. `Box.Tag<Long>` có `V = Long` của static nested class, **không phụ thuộc `T` của `Box<T>`**.
6. `Box<String>.Inner` là inner class không static gắn với đối tượng `text`, nên đọc `value` của outer instance và biết đó là `String` ở mã nguồn.

Đây là chương trình độc lập có thể chạy; các đoạn có nhãn **KHÔNG BIÊN DỊCH** trong các mục khác chỉ dùng để phân tích lỗi, không cần chép vào file này.

## 12. Cách sửa các lỗi static/generic thường gặp

### Lỗi A — Static field dùng `T` lớp

Trước:

```java
// Sai:
class Registry<T> {
    // static T latest;
}
```

Nếu mục tiêu là **lưu dữ liệu theo từng object**, bỏ `static`:

```java
class Registry<T> {
    private T latest;

    void set(T value) {
        latest = value;
    }
}
```

Nếu mục tiêu là **trạng thái static dùng chung**, hãy chọn một kiểu không phụ thuộc `T`, ví dụ `static int count` hoặc một kiểu cụ thể phù hợp. Nếu cần kho dữ liệu đa kiểu, cân nhắc thiết kế registry có token và các bất biến runtime rõ ràng; không phải cứ dùng `static Map<String, Object>` là đã có type safety tự động.

### Lỗi B — Static method trả `T` lớp

Trước:

```java
// Sai trong class Box<T>:
// static T find() { return null; }
```

Nếu xử lý dữ liệu của **một instance cụ thể**, viết instance method:

```java
T get() {
    return value;
}
```

Nếu thao tác là **factory**, khai báo type parameter method:

```java
static <U> Box<U> of(U value) {
    return new Box<>(value);
}
```

Nếu thao tác là utility nhận object generic, khai báo `static <U> U extract(Box<U> box)`.

### Lỗi C — Static nested class muốn dùng `T` của outer

Trước:

```java
// Sai trong Outer<T>:
// static class Entry { T item; }
```

Nếu entry cần độc lập khỏi outer instance, cho nó type parameter riêng:

```java
static class Entry<U> {
    U item;
}
```

Nếu entry phải gắn với outer instance và dùng chính `T`, cân nhắc **non-static inner class** hoặc truyền `T` qua constructor cùng kiểu cụ thể, tùy quan hệ sở hữu và vòng đời.

### Lỗi D — Ghi `static T` và tưởng compiler hiểu `T` từ người gọi

Static method không chọn “`T` của lớp đang được gọi” vì không có bản static riêng cho `Box<String>` và `Box<Integer>`. Nếu method không cần đối số, một generic method `static <U> U empty()` tuy có thể viết `return null` về cú pháp, nhưng **không thể tự suy ra một giá trị `U` hợp lệ bất kỳ** từ không khí. Thiết kế tốt thường nhận dữ liệu, token, supplier hoặc factory thay vì dựa vào một `U` ảo.

## 13. Vấn đề thực hành khi gọi static method qua kiểu tham số hóa

Thông thường, hãy gọi static method bằng **tên class**:

```java
Box<String> box = Box.of("Java");
```

Đối với static factory có type parameter riêng, compiler có thể dùng target typing và type inference để khớp kiểu trả về. Nếu cần, generic method còn cho phép type witness:

```java
Box<String> one = Box.<String>of("Java");
```

Không nên tưởng rằng cú pháp `Box<String>.of(...)` có nghĩa “chọn static method gắn với `T = String` của class”. Java không cung cấp hệ thành viên static riêng cho mỗi `Box<T>` kiểu đó; trong code bình thường hãy viết `Box.of(...)` hoặc `Box.<String>of(...)` cho static generic method.

Khi generic class có phương thức instance `get()`, caller phải có object:

```java
Box<String> value = Box.of("x");
String result = value.get();
```

Không gọi `Box.get()` như static method chỉ vì `Box` là generic class. Hãy phân biệt **loại thành viên** với **cách tham số hóa kiểu**.

## 14. Bài tập tự kiểm tra

**Câu 1.** `class Repo<T> { static T data; }` có hợp lệ không?

Không. `T` của lớp không thể được dùng làm kiểu của static field.

**Câu 2.** `class Repo<T> { static int count; }` có hợp lệ không?

Có. `int` không phụ thuộc `T`; field static `count` được dùng chung giữa các cách tham số hóa lớp trong cùng runtime class được nạp.

**Câu 3.** `class Repo<T> { static <U> U identity(U value) { return value; } }` có hợp lệ không?

Có. `U` là type parameter **do static method tự khai báo**, không phải `T` của class.

**Câu 4.** `class Repo<T> { static <T> T identity(T value) { return value; } }` có hợp lệ không?

Có. `T` ở method là type parameter mới, che khuất tên `T` của class trong phạm vi method; không phải một cách truy cập type parameter của class từ static context.

**Câu 5.** Một `static class Nested { T value; }` nằm trong `Outer<T>` có hợp lệ không?

Không. Static nested class không có type parameter `T` của enclosing class trong scope. Để sửa, khai báo `Nested<U>` hoặc dùng non-static inner class nếu quan hệ sở hữu cần outer instance.

**Câu 6.** `class Box<T> { T get() { ... } }` dùng `T` trong instance method có hợp lệ không?

Có. `T` thuộc generic instance API, và compiler áp dụng theo kiểu tĩnh `Box<String>`, `Box<Integer>`, v.v.

**Câu 7.** `static <U> U extract(Box<U> value)` dùng `Box<U>` trong static context có hợp lệ không?

Có. Type parameter `U` được khai báo bởi chính static method và ràng buộc cách dùng `Box<U>` của đối số.

**Câu 8.** Đổi một static method thành instance method có khiến `T.class` và `new T[10]` hợp lệ không?

Không. Đó là những giới hạn khác do type variable `T` non-reifiable và type erasure, không chỉ do static context.

## 15. Checklist trước khi viết generic API có static members

Khi gặp chữ `T` ở một khai báo, hãy tự kiểm tra:

1. **Ai khai báo `T`?** `class Box<T>` hay `static <T> ...`?
2. **Bạn đang ở ngữ cảnh nào?** Field instance, method instance, constructor, static field, static initializer, static method hay static nested class?
3. **Static member có thật sự cần kiểu của một instance không?** Nếu có, có thể nên chuyển logic vào instance method hoặc nhận instance làm tham số.
4. **Có thể khai báo type parameter riêng cho static method không?** Ví dụ `static <U> Box<U> of(U value)`.
5. **Cần trạng thái riêng cho từng đối tượng hay trạng thái chung?** Trường instance và trường static có vòng đời khác nhau.
6. **Nested type có cần enclosing instance không?** Dùng non-static inner nếu cần tham chiếu outer instance và outer `T`; dùng static nested generic class với `<U>` riêng nếu muốn độc lập.
7. **Có đang nhầm lỗi static với type erasure không?** `T.class`, `new T()`, `new T[]` không trở nên hợp lệ chỉ bằng cách bỏ `static`.
8. **Có đang dùng raw type hoặc cast để lách compiler không?** Những cách này có thể phá hợp đồng generic và làm lỗi xuất hiện muộn ở runtime.

**Kết luận:** tham số kiểu `T` của lớp generic chỉ được dùng ở các ngữ cảnh phù hợp với **instance/type của lớp**, không được tham chiếu trực tiếp trong static field, static initializer, static method hoặc static nested class. Nhưng static code **được phép dùng generic theo cách riêng**: khai báo `static <U>`, nhận `Box<U>` làm tham số, tạo `Box<U>` qua factory, hoặc dùng static nested class có type parameter của chính nó. Hiểu đúng **scope và ownership của type variables** là cách chắc chắn nhất để sửa lỗi “non-static type variable cannot be referenced from a static context”.