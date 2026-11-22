# Record generic và ràng buộc tham số kiểu trong Java

## 1. Record có thể khai báo tham số kiểu như thế nào?

**Generic record** là một record class có một hoặc nhiều **type parameters** khai báo sau tên record, trước danh sách **record components**. Nhờ đó, cùng một cấu trúc dữ liệu có thể dùng với nhiều kiểu tham chiếu khác nhau mà vẫn được kiểm tra kiểu lúc biên dịch.

```java
record Box<T>(T value) {}
record Pair<K, V>(K key, V value) {}
```

- `T`, `K` và `V` là **type variables** (tham số kiểu), không phải kiểu dữ liệu cố định.
- `value` và `key` là **record components**. Với mỗi component, Java cung cấp một trường instance `private final` và một accessor `public` tương ứng.
- `Box<String>` biểu thị một `Box` có component `value` được kiểm tra như `String`; `Box<Integer>` biểu thị component được kiểm tra như `Integer`.
- `Pair<String, Integer>` mô tả cặp gồm khóa `String` và giá trị `Integer`.
- Record có thể dùng type parameter trong component, constructor, accessor, phương thức instance, khai báo `implements` và các kiểu liên quan, miễn tuân theo giới hạn phạm vi sử dụng type variable.

Ví dụ sử dụng trong một phương thức:

```java
Box<String> message = new Box<>("Hello");
Pair<String, Integer> score = new Pair<>("Lan", 95);

System.out.println(message.value()); // Hello
System.out.println(score.key());     // Lan
System.out.println(score.value());   // 95
```

Cú pháp `<>` lúc tạo đối tượng gọi là **diamond operator**: trình biên dịch suy luận tham số kiểu từ ngữ cảnh hoặc đối số. Có thể viết `new Box<String>("Hello")` nếu muốn chỉ rõ.

**Phạm vi phiên bản:** record chính thức từ **Java 16** và generic record vẫn được hỗ trợ trong các bản Java hiện hành. Các ví dụ ở đây dùng **Java 17+**, không cần bật preview và không phụ thuộc cách dùng record thử nghiệm thời Java 14.

## 2. Những thành viên nào mang type parameter?

Với khai báo:

```java
record Box<T>(T value) {}
```

Java cung cấp, về mặt ý nghĩa:

| Thành viên | Với `Box<T>` | Khi biến có kiểu `Box<String>` |
| --- | --- | --- |
| Component | `T value` | `String value` ở góc nhìn kiểm tra kiểu |
| Trường tương ứng | `private final T value` | Kiểu component được chuyên biệt hóa ở cấp source |
| Accessor | `public T value()` | Kết quả của `value()` được kiểm tra là `String` |
| Canonical constructor | `Box(T value)` | Nhận `String` cho `Box<String>` |
| Các method record khác | `equals`, `hashCode`, `toString` | Hoạt động theo component; không cần tự viết chỉ vì dùng generic |

Bảng trên mô tả các thành viên được cung cấp ngầm định; **không chép lại trường instance vào thân record**. Component field vẫn là `private final`, và generic **không thay đổi** tính bất biến nông của record.

Ví dụ trong phương thức:

```java
Box<String> label = new Box<>("ACTIVE");
String upper = label.value().toLowerCase(java.util.Locale.ROOT);
System.out.println(upper); // active
```

Trình biên dịch cho phép gọi method của `String` vì biết `label.value()` có kiểu `String` ở cấp source. Không phải tự ép kiểu `(String) label.value()` khi đã khai báo đúng `Box<String>`.

## 3. Ràng buộc tham số kiểu với `extends`

Một **type bound** đặt yêu cầu cho **kiểu được phép thay vào** tham số kiểu. Cú pháp thông dụng:

```java
record NumberBox<T extends Number>(T value) {}
```

`T extends Number` nghĩa là `T` phải là `Number` hoặc một kiểu con hợp lệ của `Number`. Những kiểu như `Integer`, `Long`, `Double` và `BigDecimal` đáp ứng; `String` thì không.

```java
NumberBox<Integer> first = new NumberBox<>(42);
NumberBox<Double> second = new NumberBox<>(3.5);

// SAI nếu bỏ chú thích:
// NumberBox<String> invalid = new NumberBox<>("42");
// String không phải subtype của Number.
```

Tại sao dùng bound? Bên trong record, trình biên dịch cho phép gọi các phương thức mà bound bảo đảm có, chẳng hạn `doubleValue()` của `Number`:

```java
record NumberBox<T extends Number>(T value) {
    double asDouble() {
        return value.doubleValue();
    }
}
```

Tuy nhiên, bound **chỉ mô tả kiểu**, không tự kiểm tra nghiệp vụ. `T extends Number` không bảo đảm số dương, hữu hạn, hoặc khác `null`. Nếu ứng dụng cần các ràng buộc đó, phải xác thực ở constructor/phương thức.

### 3.1. Ràng buộc bằng interface

Để record có thể **so sánh thứ tự** hai component cùng kiểu, dùng interface `Comparable`:

```java
record Ordered<T extends Comparable<? super T>>(T start, T end) {
    Ordered {
        java.util.Objects.requireNonNull(start, "start");
        java.util.Objects.requireNonNull(end, "end");

        if (start.compareTo(end) > 0) {
            throw new IllegalArgumentException("start > end");
        }
    }

    boolean includes(T item) {
        java.util.Objects.requireNonNull(item, "item");
        return start.compareTo(item) <= 0
                && item.compareTo(end) <= 0;
    }
}
```

`Comparable<? super T>` cho phép so sánh `T` với một đối tượng thuộc `T` hoặc một **supertype của `T`** mà kiểu đó triển khai `Comparable`. Đây là kiểu bound linh hoạt thường hữu ích cho các API đọc/so sánh; `Comparable<T>` cũng có thể dùng nếu bài toán chỉ yêu cầu trường hợp đúng chính xác `T`.

Ví dụ hợp lệ trong một phương thức:

```java
Ordered<Integer> numbers = new Ordered<>(10, 20);
System.out.println(numbers.includes(15)); // true

Ordered<String> words = new Ordered<>("apple", "pear");
System.out.println(words.includes("mango")); // true
```

`Integer` và `String` đáp ứng yêu cầu `Comparable<? super T>`. Lời gọi `new Ordered<>(20, 10)` là **đúng kiểu** nhưng constructor sẽ ném `IllegalArgumentException`: bound kiểm tra **khả năng so sánh** tại lúc biên dịch, còn điều kiện `start <= end` là kiểm tra dữ liệu lúc chạy.

### 3.2. Nhiều bound: lớp phải đứng trước interface

Một type variable có thể có nhiều bound được nối bằng ký hiệu `&`:

```java
record Amount<T extends Number & Comparable<T>>(T value) {
    boolean atLeast(T other) {
        return value.compareTo(other) >= 0;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

Kiểu `T` ở đây phải đồng thời là subtype của `Number` **và** triển khai `Comparable<T>`. Vì vậy bên trong record có thể gọi cả `doubleValue()` lẫn `compareTo()`.

```java
Amount<java.math.BigDecimal> amount =
        new Amount<>(new java.math.BigDecimal("12.5"));

System.out.println(
        amount.atLeast(new java.math.BigDecimal("10"))
); // true
```

**Thứ tự bound có ý nghĩa:** nếu có một class bound như `Number`, nó **phải xuất hiện đầu tiên**. Sau đó mới là các interface bound. Ví dụ `<T extends Comparable<T> & Number>` là **sai** vì đặt class `Number` sau interface. Một type variable chỉ có thể có tối đa một class bound, nhưng có thể có nhiều interface bound tương thích.

Bound cũng ảnh hưởng đến **type erasure**: type variable được xóa về bound bên trái cùng. Phần 7 giải thích rõ hơn.

## 4. Suy luận kiểu, diamond và generic static factory

Một generic record cho phép tạo object theo cả hai cách:

```java
Box<String> explicit = new Box<String>("Hi");
Box<String> inferred = new Box<>("Hi");
```

Nếu record tự khai báo **static factory method**, method đó phải khai báo type parameter riêng của chính nó, vì static context không sử dụng trực tiếp tham số kiểu thuộc instance của `Box<T>`:

```java
record Box<T>(T value) {
    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
```

Cách gọi:

```java
Box<String> word = Box.of("Java");
Box<Integer> count = Box.of(7);
System.out.println(word.value());  // Java
System.out.println(count.value()); // 7
```

`<U>` đứng trước kiểu trả về trong chữ ký `static <U> Box<U> of(U value)` là **type parameter của phương thức static**. Nó độc lập với `T` được khai báo ở đầu record. Không được viết `static T fallback;` bên trong `Box<T>`: Java sẽ báo **`non-static type variable T cannot be referenced from a static context`**.

### 4.1. Constructor của generic record

Có thể dùng **compact canonical constructor** để kiểm tra dữ liệu:

```java
record Box<T>(T value) {
    Box {
        java.util.Objects.requireNonNull(value, "value");
    }
}
```

Tên `value` trong thân compact constructor là **tham số constructor** ngầm định có kiểu `T`. Khi thân kết thúc bình thường, Java tự gán tham số vào component field. Không tự gán `this.value = value;` bên trong compact constructor.

Hoặc dùng normal canonical constructor:

```java
record Box<T>(T value) {
    Box(T value) {
        this.value = java.util.Objects.requireNonNull(value, "value");
    }
}
```

Đây là **hai cách thay thế**, không khai báo đồng thời trên cùng record. Canonical constructor dùng type variable `T` của record; **không khai báo một danh sách type parameters riêng** cho canonical constructor kiểu `<U> Box(T value)`.

Ngoài canonical constructor, record có thể có constructor phụ với danh sách tham số khác; constructor phụ phải ủy quyền hợp lệ đến constructor khác của cùng record.

## 5. Giới hạn quan trọng: invariant và wildcard

Generic trong Java mặc định là **invariant**: dù `Integer` kế thừa `Number`, `Box<Integer>` **không** là subtype của `Box<Number>`.

```java
Box<Integer> integers = new Box<>(5);

// SAI: không thể gán Box<Integer> vào Box<Number>.
// Box<Number> numbers = integers;
```

Nếu API chỉ cần **đọc** một giá trị có kiểu con của `Number`, dùng wildcard:

```java
static void printNumber(Box<? extends Number> box) {
    Number number = box.value();
    System.out.println(number);
}
```

Đoạn trên là **phương thức minh họa cần đặt trong một class**. `printNumber(new Box<>(5));` và `printNumber(new Box<>(3.14));` đều hợp lệ. Với `Box<? extends Number>`, giá trị lấy ra có thể xem là `Number`.

Nếu không cần thông tin về loại component, `Box<?>` biểu thị box với type argument chưa biết:

```java
static void printAny(Box<?> box) {
    Object value = box.value();
    System.out.println(value);
}
```

Wildcard không làm thay đổi thực thể record được tạo; nó diễn đạt **điều người gọi được phép giả định về kiểu**. Không nên chuyển sang **raw type** `Box` (bỏ `<...>`) để lách ràng buộc, vì làm mất kiểm tra kiểu và có thể gây unchecked warnings hoặc lỗi ép kiểu khi chạy.

## 6. Type argument phải là kiểu tham chiếu

Cũng như generic class, generic record không nhận kiểu nguyên thủy làm type argument:

```java
Box<Integer> good = new Box<>(123);

// SAI: generic type argument không được là primitive int.
// Box<int> bad = new Box<int>(123);
```

Thay `int` bằng wrapper `Integer`, `long` bằng `Long`, v.v. Trong nhiều trường hợp, **autoboxing** cho phép viết `new Box<>(123)` khi type argument được suy luận là `Integer`.

**Không nhầm** với component nguyên thủy của record **không generic**:

```java
record Counter(int value) {} // HỢP LỆ
```

Giới hạn chỉ áp dụng cho **type arguments** của Java generics, không cấm record dùng component có kiểu primitive.

## 7. Type erasure và giới hạn khi chạy

Java generics sử dụng **type erasure**. Tham số kiểu tạo sự an toàn lúc biên dịch, nhưng Java không tạo một class runtime khác nhau cho mỗi kiểu sử dụng generic record.

Ví dụ trong một phương thức:

```java
Box<String> text = new Box<>("hello");
Box<Integer> number = new Box<>(123);

System.out.println(text.getClass().equals(number.getClass())); // true
```

Cả hai instance có cùng runtime class `Box`. Khi biên dịch, type variable `T` được erasure theo bound trái nhất:

- `record Box<T>(T value) {}`: `T` mặc định bound là `Object`; erasure của `T` là `Object`.
- `record NumberBox<T extends Number>(T value) {}`: erasure của `T` là `Number`.
- `record Amount<T extends Number & Comparable<T>>(T value) {}`: erasure của `T` là `Number`, vì `Number` là bound trái nhất.

Điều này **không xóa bỏ** kiểm tra kiểu tại nguồn: `Box<String>.value()` vẫn được Java compiler kiểm tra như kết quả `String`. Nhưng không thể dùng kiểm tra kiểu đã mất tại runtime như:

```java
// CỐ Ý SAI: type argument String không thể kiểm tra bằng instanceof.
// if (someObject instanceof Box<String>) { ... }
```

Có thể kiểm tra kiểu chưa biết bằng `instanceof Box<?>`, rồi làm việc với component ở mức `Object` hoặc kiểm tra kiểu thực tế của chính giá trị trả về. Reflection có thể xem **khai báo** type parameter của class, nhưng không tự cho biết kiểu `T` cụ thể được dùng để khai báo một biến tham chiếu trong source.

**Khi làm việc với JSON, database hoặc reflection:** nếu một framework cần biết type argument cụ thể tại runtime, cần cung cấp thông tin kiểu một cách tường minh theo cơ chế framework (ví dụ một type token hay type reference), thay vì trông đợi `record` tự lưu `T = String` vào mỗi object.

## 8. Tính bất biến nông của generic record và sao chép phòng vệ

Một generic record có component kiểu tham chiếu thường được kỳ vọng biểu diễn dữ liệu giá trị, nhưng `private final` chỉ ngăn thay đổi **tham chiếu của field**, không tự ngăn sửa object mà nó trỏ tới.

Ví dụ:

```java
record Snapshot<E>(java.util.List<E> elements) {
    Snapshot {
        elements = java.util.List.copyOf(elements);
    }
}
```

Khi nhận `ArrayList` có thể sửa, compact constructor thay tham số `elements` bằng một danh sách không cho sửa. Đây là thiết kế phù hợp nếu dữ liệu record cần giữ ổn định:

```java
java.util.ArrayList<String> input =
        new java.util.ArrayList<>(java.util.List.of("java"));

Snapshot<String> snapshot = new Snapshot<>(input);
input.add("changed");

System.out.println(snapshot.elements()); // [java]
```

Tuy vậy, `List.copyOf` thực hiện **sao chép nông**. Nếu `E` là kiểu mutable, chính đối tượng phần tử có thể vẫn thay đổi. Generic bound như `E extends SomeInterface` không tự bảo đảm tính bất biến sâu hoặc kiểm soát `null`. Quyết định defensive copy cần dựa trên bản chất dữ liệu và hợp đồng API.

### 8.1. Record có thể triển khai generic interface

Generic record không dùng `extends SomeClass` để kế thừa một class do người dùng chọn, vì record kế thừa `java.lang.Record` theo định nghĩa ngôn ngữ. Tuy nhiên, record **có thể `implements` một hay nhiều interface**, kể cả generic interface:

```java
interface Identified<T> {
    T id();
}

record Entry<T>(T id) implements Identified<T> {}
```

Accessor `id()` của `Entry<T>` đáp ứng hợp đồng interface `Identified<T>`. Khi interface method phù hợp, compiler có thể dùng accessor được sinh ngầm định làm triển khai; không cần viết lại phương thức `id()` thủ công.

### 8.2. Record lồng nhau là `static` về mặt ngữ nghĩa

Một record khai báo bên trong class là **implicitly static**. Nó không bắt giữ instance hay type variables của class bao ngoài:

```java
class Outer<T> {
    record Slot<U>(U value) {} // HỢP LỆ: tự khai báo U
    // record Bad(T value) {} // SAI: T của Outer không ở static context này
}
```

Điều này không cấm generic record; nó chỉ yêu cầu record lồng nhau khai báo và sử dụng **tham số kiểu của chính record**, hoặc một kiểu cụ thể. Generic record có thể khai báo ở top-level, làm member type hoặc làm local record trong phương thức, tuân theo những quy tắc phạm vi tương ứng.

## 9. Chương trình Java 17+ hoàn chỉnh, có thể biên dịch và chạy

Lưu đúng tên tệp **`GenericRecordDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class GenericRecordDemo {
    record Box<T>(T value) {
        Box { Objects.requireNonNull(value, "value"); }
        static <U> Box<U> of(U value) { return new Box<>(value); }
    }

    record Pair<A, B>(A left, B right) {}

    record Ordered<T extends Comparable<? super T>>(T start, T end) {
        Ordered {
            Objects.requireNonNull(start, "start");
            Objects.requireNonNull(end, "end");
            if (start.compareTo(end) > 0) {
                throw new IllegalArgumentException("start > end");
            }
        }

        boolean includes(T item) {
            Objects.requireNonNull(item, "item");
            return start.compareTo(item) <= 0
                    && item.compareTo(end) <= 0;
        }
    }

    record Amount<T extends Number & Comparable<T>>(T value) {
        boolean atLeast(T other) {
            return value.compareTo(other) >= 0;
        }
    }

    record Snapshot<E>(List<E> elements) {
        Snapshot { elements = List.copyOf(elements); }
    }

    interface Identified<T> { T id(); }
    record Entry<T>(T id) implements Identified<T> {}

    static void showValue(Box<? extends Number> number) {
        Number value = number.value();
        System.out.println("number=" + value);
    }

    public static void main(String[] args) {
        Box<String> message = Box.of("java");
        System.out.println(message.value().toUpperCase(Locale.ROOT));

        Pair<String, Integer> pair = new Pair<>("age", 21);
        System.out.println(pair.left() + "=" + pair.right());

        Ordered<Integer> range = new Ordered<>(10, 20);
        System.out.println("includes15=" + range.includes(15));

        Amount<BigDecimal> amount = new Amount<>(new BigDecimal("12.5"));
        System.out.println("atLeast10="
                + amount.atLeast(new BigDecimal("10")));

        Entry<String> entry = new Entry<>("R-7");
        System.out.println("id=" + entry.id());

        ArrayList<String> mutable = new ArrayList<>(List.of("java"));
        Snapshot<String> snapshot = new Snapshot<>(mutable);
        mutable.add("changed");
        System.out.println("snapshot=" + snapshot.elements());
        try {
            snapshot.elements().add("another");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }

        Box<Integer> integerBox = Box.of(42);
        showValue(integerBox);
        System.out.println("sameClass="
                + message.getClass().equals(integerBox.getClass()));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 GenericRecordDemo.java
java GenericRecordDemo
```

Kết quả chính xác:

```text
JAVA
age=21
includes15=true
atLeast10=true
id=R-7
snapshot=[java]
unmodifiable
number=42
sameClass=true
```

### Tại sao chương trình in đúng các dòng này?

1. `JAVA`: `Box.of("java")` suy luận `U = String`; accessor trả `String`, cho phép gọi `toUpperCase`.
2. `age=21`: `Pair<String, Integer>` có hai component với hai kiểu độc lập.
3. `includes15=true`: `Integer` triển khai `Comparable<Integer>`; số 15 nằm trong khoảng 10..20.
4. `atLeast10=true`: `BigDecimal` thỏa cả `Number` và `Comparable<BigDecimal>`; 12.5 lớn hơn 10.
5. `id=R-7`: accessor `id()` của record đồng thời đáp ứng method trong generic interface.
6. `snapshot=[java]`: compact constructor đã copy danh sách trước khi caller thêm `"changed"` vào list gốc.
7. `unmodifiable`: danh sách giữ trong record là `List.copyOf` nên không hỗ trợ `add`.
8. `number=42`: `Box<Integer>` được chấp nhận ở tham số `Box<? extends Number>`.
9. `sameClass=true`: các phiên bản tham số kiểu khác nhau sử dụng cùng runtime class do type erasure.

Các record trong ví dụ là member records của class `GenericRecordDemo`, vì vậy mặc định có ngữ nghĩa `static`; việc chạy không cần tạo instance của class bao ngoài.

## 10. Lỗi biên dịch thường gặp

### 10.1. Truyền type argument nằm ngoài bound

```java
// CỐ Ý SAI: biên dịch thất bại.
record WrongBound<T extends Number>(T value) {}

class InvalidUsage {
    WrongBound<String> wrong = new WrongBound<>("oops");
}
```

`String` không thỏa `T extends Number`, nên compiler báo đại ý `type argument String is not within bounds of type-variable T` và có thể thêm lỗi không suy luận được type argument. Sửa bằng loại component phù hợp (chẳng hạn `WrongBound<Integer>`), hoặc sửa lại bound **chỉ khi** yêu cầu dữ liệu thực sự khác.

### 10.2. Viết thứ tự nhiều bound sai

```java
// CỐ Ý SAI:
record WrongOrder<T extends Comparable<T> & Number>(T value) {}
```

`Number` là class, nên phải đứng **trước** interface:

```java
record RightOrder<T extends Number & Comparable<T>>(T value) {}
```

Không phải mọi kiểu con của `Number` đều chắc chắn triển khai `Comparable<T>`. Chỉ những kiểu **đáp ứng cả hai yêu cầu** mới dùng được.

### 10.3. Tham chiếu type variable của record từ static context

```java
// CỐ Ý SAI:
record InvalidStatic<T>(T value) {
    static T fallback;
}
```

`T` gắn với tham số kiểu của instance, không thể dùng làm kiểu của một field `static`. Nếu cần static factory tổng quát, khai báo type parameter **riêng** cho method:

```java
record Factory<T>(T value) {
    static <U> Factory<U> of(U value) {
        return new Factory<>(value);
    }
}
```

### 10.4. Thêm type parameter riêng vào canonical constructor

```java
// CỐ Ý SAI:
record InvalidGeneric<T>(T value) {
    <U> InvalidGeneric(T value) {
        this.value = value;
    }
}
```

Canonical constructor **không được khai báo type variables riêng**. Compiler báo `canonical constructor must not declare type variables`. Sửa bằng `InvalidGeneric(T value) { this.value = value; }` hoặc compact form `InvalidGeneric { ... }`.

### 10.5. Nhầm generic bound với kiểm tra giá trị

`record Amount<T extends Number>(T value) {}` cho phép `new Amount<Integer>(-1)` và `new Amount<Integer>(null)` về mặt kiểu nếu không có kiểm tra bổ sung. Bound không tự chặn `null`, không kiểm tra số âm và không biến dữ liệu mutable thành bất biến. Hãy kiểm tra hợp đồng nghiệp vụ trong constructor.

### 10.6. Cố kiểm tra `instanceof Box<String>`

```java
// CỐ Ý SAI:
// if (obj instanceof Box<String>) { ... }
```

Type argument `String` không reifiable ở runtime. Dùng `obj instanceof Box<?>` để nhận biết kiểu record tổng quát, rồi kiểm tra component theo nhu cầu, hoặc chuyển thông tin kiểu một cách tường minh qua API.

## 11. Bài tập kiểm tra hiểu biết

**Câu 1.** `Box<Integer>` có thể gán trực tiếp vào biến `Box<Number>` không? Vì sao?

**Đáp án:** Không. Generic invariant. Nếu chỉ muốn đọc kiểu số, cân nhắc `Box<? extends Number>`.

**Câu 2.** Trong `record Choice<T extends CharSequence>(T text) {}`, `Choice<String>` có hợp lệ không, và có được gọi `text.length()` bên trong record?

**Đáp án:** Có. `String` triển khai `CharSequence`, nên bound cho phép gọi `length()`. Tuy nhiên, `Choice<Integer>` không thỏa bound.

**Câu 3.** `record Pair<K, V>(K key, V value) {}` với `Pair<String, Integer>` có tạo một runtime class khác với `Pair<Long, String>`?

**Đáp án:** Không. Generic record được compiler kiểm tra kiểu khác nhau ở source, nhưng runtime dùng chung class `Pair` do type erasure.

**Câu 4.** Vì sao dùng `T extends Number & Comparable<T>` thay vì chỉ `T extends Number` khi cần `compareTo`?

**Đáp án:** `Number` không bảo đảm mọi subtype của nó có `compareTo`; thêm `Comparable<T>` mới đảm bảo method so sánh phù hợp ở cấp type.

**Câu 5.** `record Snapshot<E>(List<E> elements) { Snapshot { elements = List.copyOf(elements); } }` có làm mọi phần tử kiểu `E` bất biến sâu không?

**Đáp án:** Không. `List.copyOf` tạo danh sách không cho sửa và sao chép nông; phần tử `E` có thể vẫn mutable.

**Câu 6.** Vì sao `record Box<T>(T value) { static <U> Box<U> of(U x) { return new Box<>(x); } }` hợp lệ dù `static T defaultValue;` không hợp lệ?

**Đáp án:** `<U>` được khai báo riêng ngay trên method static nên nó tồn tại trong phạm vi method; `T` là type variable của generic record và không dùng trực tiếp trong static context.

## 12. Checklist thiết kế generic record

- [ ] Đặt các tham số kiểu `<T>`, `<K, V>` ở **sau tên record** và **trước header**.
- [ ] Chọn bound thấp nhất nhưng đủ đáp ứng các thao tác cần dùng; không thêm `Number`/`Comparable` chỉ để “giới hạn” khi không có nhu cầu.
- [ ] Với nhiều bound, class (nếu có) phải đứng trước interface; kiểm tra các bound tương thích.
- [ ] Dùng diamond `<>` hoặc static factory generic riêng để compiler suy luận kiểu hợp lệ.
- [ ] Tránh raw types và unchecked casts. Dùng wildcard khi API cần nhận nhiều tham số kiểu liên quan.
- [ ] Nhớ generics không chấp nhận primitive type arguments; sử dụng wrapper khi cần.
- [ ] Không giả định type argument của object có sẵn ở runtime; cân nhắc type erasure khi làm việc với reflection/serialization.
- [ ] Kiểm tra dữ liệu runtime riêng: `null`, thứ tự, giá trị hợp lệ, mutable references và defensive copy.
- [ ] Không dùng type variable của record trực tiếp trong static context; khai báo `<U>` trên static method nếu cần.
- [ ] Constructor/field/accessor vẫn phải tuân thủ các quy tắc chung của record, kể cả khi record là generic.

## Tài liệu chuẩn đang áp dụng

- [Java Language Specification, Java SE 27 — Chương 8, `8.10 Record Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10): cú pháp record với `TypeParameters`, component fields, accessor và constructor.
- [Java Language Specification, Java SE 27 — Chương 4, `4.4 Type Variables](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.4): ràng buộc kiểu với `extends`, nhiều bound và thứ tự.
- [Java Language Specification, Java SE 27 — Chương 4, `4.5–`4.8](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.5): parameterized types, wildcard, type erasure và raw types.
- [Oracle — Record Classes (Java 17)](https://docs.oracle.com/en/java/javase/17/language/records.html): hướng dẫn record khi đã là tính năng chính thức, với constructor và các thành viên sinh ngầm định.
