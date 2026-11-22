# Che khuất tên kiểu và vì sao nên tránh dùng lại tên T trong Java Generics

Trong Java Generics, `T` là **tên của một biến kiểu (type parameter)**, không phải một kiểu cố định hay một biến chứa dữ liệu. Tên ấy có **phạm vi (scope)** giống những tên khác trong chương trình. Một generic class có thể khai báo `T`, rồi một generic method hoặc inner class bên trong lại khai báo **một `T` mới**. Tại phạm vi bên trong, `T` mới *che khuất* (*shadow*) `T` bên ngoài.

Cú pháp này có thể hợp lệ, nhưng rất dễ khiến người đọc tưởng hai ký hiệu `T` là một kiểu duy nhất. Kết quả là sai hợp đồng API, phép gán bị compiler từ chối hoặc những dòng cast không cần thiết được thêm vào để “chữa” lỗi. Bài học tập trung vào **cơ chế shadowing của type parameter**, cách nhận biết phạm vi, phân biệt các `T` cùng tên, giới hạn kiểu và cách đặt tên giúp thiết kế generic code dễ hiểu, an toàn.

Các ví dụ chạy độc lập dùng Java 17 trở lên. Các dòng cố ý gây lỗi biên dịch sẽ được comment và giải thích riêng.

## 1. Nhắc lại: tên T xuất hiện ở đâu?

Một generic class đơn giản:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` được khai báo ngay sau tên class ở `Box<T>`. Mỗi lần `T` xuất hiện trong các thành viên instance nêu trên đều trỏ tới **chính type parameter của class**. Với `Box<String>`, compiler xem `Box.get()` trả `String`, còn `Box<Integer>` cho kết quả kiểu `Integer`.

So sánh:

```java
class Utilities {
    static <T> T identity(T value) {
        return value;
    }
}
```

Ở đây `<T>` nằm trước kiểu trả về của method. `T` là **type parameter của method**; class `Utilities` không khai báo `T` nào cả. Không có shadowing vì không có tên type parameter cùng tên ở một phạm vi bao quanh đang được truy cập.

Còn ví dụ sau:

```java
class Box<T> {
    <T> T echo(T input) {
        return input;
    }
}
```

Hai dấu `<T>` là **hai khai báo khác nhau**:

- `Box<T>` khai báo một `T` thuộc class.
- `<T> T echo(T input)` khai báo một `T` mới thuộc method, làm cho những lần dùng tên đơn `T` trong phạm vi method biểu thị **T của method**.
- `T` của method được suy luận theo mỗi lần gọi `echo`, độc lập với type argument của một `Box<T>` instance.
- Không có cơ chế “compiler tự nhận ra hai T giống nhau” chỉ nhờ tên trùng.

Việc hiểu chính xác **nơi khai báo** quan trọng hơn việc nhớ tên `T`.

## 2. Shadowing là gì, khác gì reuse tên ở phạm vi rời nhau?

Shadowing xảy ra khi một khai báo tên ở phạm vi bên trong che một khai báo cùng tên ở phạm vi bao quanh. Với generic type parameters, cấu trúc rất dễ nhầm:

```java
class Holder<T> {
    <T> T echo(T input) {
        return input;
    }
}
```

Tên `T` ở khai báo method che tên `T` của class trong vùng mà type parameter của method có hiệu lực. Lúc compiler phân giải `T input` hoặc `T` là kiểu trả về của `echo`, nó tìm `T` tại phạm vi method trước.

Không phải cứ thấy hai chữ `T` trong dự án là có shadowing. Hai generic methods độc lập trong cùng một class, chẳng hạn `<T> T first(T x)` và `<T> T last(T x)`, có các type-parameter scopes riêng biệt, **không lồng nhau**. Việc mỗi method dùng tên thông dụng `T` là hoàn toàn bình thường. Vấn đề nằm ở việc có **hai khai báo cùng tên với các phạm vi chồng lên nhau**, khiến người đọc dễ hiểu sai một `T` là của cấp nào.

Một type argument cũng không phải khai báo mới:

```java
class Holder<T> {
    java.util.List<T> asList(T item) {
        return java.util.List.of(item);
    }
}
```

`List<T>` ở đây đang **sử dụng** `T` của `Holder<T>`; `List<T>` không khai báo thêm `T` để che tên. Dấu `<...>` trong Java vừa có thể dùng để *khai báo type parameter* (sau class/method), vừa để *truyền type argument* (sau tên type generic), nên phải nhìn **vị trí cú pháp** trước khi kết luận.

## 3. Ví dụ chạy được: hai T cùng tên nhưng độc lập

Tạo `ShadowingDemo.java`:

```java
public class ShadowingDemo {
    static final class Holder<T> {
        private final T stored;

        Holder(T stored) {
            this.stored = stored;
        }

        T get() {
            return stored;
        }

        <T> T echo(T input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("Java");

        String stored = holder.get();
        Integer echoedNumber = holder.echo(42);
        Boolean echoedBoolean = holder.echo(true);

        System.out.println(stored);
        System.out.println(echoedNumber);
        System.out.println(echoedBoolean);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac ShadowingDemo.java
java ShadowingDemo
```

`stdout`:

```text
Java
42
true
```

Phân tích theo hai phạm vi:

| Ký hiệu trong source | Được khai báo tại | Kiểu ở invocation đang xét |
| --- | --- | --- |
| `T` trong `Holder<T>` | Class `Holder` | `String` vì receiver là `Holder<String>` |
| `T stored` | Dùng `T` của class | `String` |
| `T get()` | Dùng `T` của class | Trả `String` |
| `<T>` trên `echo` | Khai báo `T` mới thuộc method | Suy luận lại trên từng lời gọi |
| `T input` trong `echo` | Dùng `T` của method | `Integer` với `echo(42)`, `Boolean` với `echo(true)` |
| `T` trả về từ `echo` | Dùng `T` của method | Tương ứng `Integer`, `Boolean` |

Hai lời gọi `echo` không hề thay type argument của `Holder<String>`. Đối tượng vẫn lưu `String` trong `stored`. Method `echo` đơn thuần nhận và trả lại một giá trị thuộc **kiểu riêng do method suy luận**.

Nếu người đọc thấy `Holder<String>` và nghĩ `echo` “chỉ nhận String” thì họ đã nhầm `T` của class với `T` của method. Đây là một lý do nên tránh khai báo lại tên `T` ở phạm vi bên trong khi hai loại dữ liệu độc lập.

## 4. Lỗi nguy hiểm hơn: tưởng T trong method là T của field

Xét class minh họa:

```java
class ConfusingStore<T> {
    private T stored;

    ConfusingStore(T stored) {
        this.stored = stored;
    }

    <T> void replace(T incoming) {
        // this.stored = incoming; // Lỗi biên dịch.
    }
}
```

Người viết có thể nghĩ `replace` nhận cùng kiểu với `stored`. Nhưng:

1. `stored` được khai báo theo type parameter `T` của **class**.
2. `<T>` ngay trước `void replace` khai báo type parameter **khác**.
3. `incoming` mang `T` của **method**, vì tên đó che khuất `T` của class ở đây.
4. Từ góc nhìn compiler, không có ràng buộc bảo đảm một giá trị kiểu method `T` có thể gán cho field kiểu class `T`.
5. Compiler từ chối `this.stored = incoming` dù cả hai chữ trong source đều viết là `T`.

Điểm này không phụ thuộc vào việc runtime có tình cờ truyền cùng loại đối tượng hay không. Thân method phải đúng với mọi type arguments được cho phép bởi khai báo của nó.

### Cách sửa đúng khi method phải nhận cùng kiểu với field

Bỏ khai báo `<T>` thừa:

```java
class Store<T> {
    private T stored;

    Store(T stored) {
        this.stored = stored;
    }

    void replace(T incoming) {
        this.stored = incoming;
    }

    T get() {
        return stored;
    }
}
```

Lúc này `T incoming` tham chiếu trực tiếp tới `T` của class. Với `Store<String>`, compiler chỉ cho `replace` nhận giá trị phù hợp với `String`.

Cần nhớ thêm: `this.` chọn **field/member của object**, nhưng **không biến tên kiểu T trong method thành T của class**. Trong ví dụ gây lỗi, `this.stored` vẫn có kiểu của class, `incoming` vẫn có kiểu của method. Viết thêm `this.` không giải quyết quan hệ kiểu đã bị tách ra.

## 5. Cách sửa khi method thực sự có kiểu độc lập

Đôi khi method cố ý nhận kiểu khác với dữ liệu mà class đang giữ. Khi đó giữ generic method là đúng, nhưng **đổi tên type parameter** cho dễ hiểu.

Tạo `ClearNamesDemo.java`:

```java
import java.util.function.Function;

public class ClearNamesDemo {
    static final class Holder<T> {
        private final T stored;

        Holder(T stored) {
            this.stored = stored;
        }

        T get() {
            return stored;
        }

        <R> R map(Function<? super T, ? extends R> mapper) {
            return mapper.apply(stored);
        }

        <U> U echo(U input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("Java");

        Integer length = holder.map(String::length);
        Boolean yes = holder.echo(true);

        System.out.println(holder.get());
        System.out.println(length);
        System.out.println(yes);
    }
}
```

Chạy:

```bash
javac ClearNamesDemo.java
java ClearNamesDemo
```

`stdout`:

```text
Java
4
true
```

Bây giờ vai trò từng biến kiểu sáng rõ:

- `T` của `Holder<T>` là **kiểu giá trị đang lưu**, ví dụ `String`.
- `R` của `<R> R map(...)` là **kiểu kết quả của phép biến đổi**. `Function<? super T, ? extends R>` nối đầu vào `T` của class với đầu ra `R` của method.
- `U` của `<U> U echo(U input)` là kiểu đầu vào/đầu ra riêng của method `echo`, hoàn toàn độc lập với `T`.
- Không có tên bị che khuất. Người đọc dễ thấy `map` phụ thuộc dữ liệu trong object còn `echo` thì không.

Trong nhiều API, tên có ý nghĩa hơn `T`/`U` cũng rất hữu ích: `<ID, ENTITY>`, `<INPUT, OUTPUT>` hoặc `<SOURCE, RESULT>`. Tuy nhiên, tên ngắn theo quy ước `T`, `E`, `K`, `V`, `R`, `U` vẫn phù hợp khi chữ ký đơn giản. Vấn đề cần tránh là **tái khai báo cùng tên ở phạm vi lồng nhau**, không phải cấm hoàn toàn ký tự `T`.

## 6. Bound của hai T không trở thành một bound chung

Khi type parameter có giới hạn `extends`, việc dùng lại tên càng dễ gây hiểu nhầm.

```java
class NumberHolder<T extends Number> {
    private final T number;

    NumberHolder(T number) {
        this.number = number;
    }

    <T extends CharSequence> int lengthOf(T text) {
        return text.length();
    }

    Number asNumber() {
        return number;
    }
}
```

Ở đây hai `T` khác nhau:

- `T extends Number` của class ràng buộc giá trị lưu trong `number`; compiler cho phép xem nó là `Number`.
- `T extends CharSequence` của method ràng buộc tham số `text`; compiler cho phép gọi `text.length()`.
- Bound `Number` không “chảy” vào method `T`; bound `CharSequence` cũng không áp dụng ngược cho field.
- Nếu method cố gán `text` vào `number`, compiler không có lý do để cho phép.

Chương trình thực thi `BoundShadowingDemo.java`:

```java
public class BoundShadowingDemo {
    static final class NumberHolder<T extends Number> {
        private final T number;

        NumberHolder(T number) {
            this.number = number;
        }

        <T extends CharSequence> int lengthOf(T text) {
            return text.length();
        }

        double doubleValue() {
            return number.doubleValue();
        }
    }

    public static void main(String[] args) {
        NumberHolder<Integer> holder = new NumberHolder<>(12);

        System.out.println(holder.doubleValue());
        System.out.println(holder.lengthOf("Java"));
    }
}
```

Chạy:

```bash
javac BoundShadowingDemo.java
java BoundShadowingDemo
```

`stdout`:

```text
12.0
4
```

Mã này có thể biên dịch, nhưng về khả năng đọc hiểu thì kém hơn cách đặt `<S extends CharSequence>` ở method. Hai cận rất khác nhau cùng mang tên `T` không giúp thể hiện ý nghĩa; nó tạo một sự trùng tên vô ích.

**Phiên bản rõ nghĩa hơn:**

```java
class NumberHolder<N extends Number> {
    private final N number;

    NumberHolder(N number) {
        this.number = number;
    }

    <S extends CharSequence> int lengthOf(S text) {
        return text.length();
    }
}
```

Dùng `N` cho number type, `S` cho sequence type giúp không cần suy đoán scope.

## 7. Inner class cũng có thể che khuất type parameter của outer class

Scope lồng nhau không chỉ có class–method. Một **non-static inner class** có thể khai báo một type parameter trùng tên với outer class. Đây là dạng shadowing đặc biệt dễ lẫn khi viết nhiều tầng generic.

Tạo `NestedShadowingDemo.java`:

```java
public class NestedShadowingDemo {
    static class Outer<T> {
        private final T outerValue;

        Outer(T outerValue) {
            this.outerValue = outerValue;
        }

        class Inner<T> {
            private final T innerValue;

            Inner(T innerValue) {
                this.innerValue = innerValue;
            }

            String describe() {
                return outerValue + " / " + innerValue;
            }

            T inner() {
                return innerValue;
            }
        }
    }

    public static void main(String[] args) {
        Outer<String> outer = new Outer<>("outer");
        Outer<String>.Inner<Integer> inner = outer.new Inner<>(7);

        System.out.println(inner.describe());
        System.out.println(inner.inner());
    }
}
```

Chạy:

```bash
javac NestedShadowingDemo.java
java NestedShadowingDemo
```

`stdout`:

```text
outer / 7
7
```

Theo dõi hai `T`:

1. `Outer<T>` khai báo một type parameter của outer class.
2. `Inner<T>` khai báo **type parameter riêng** cho inner class; trong phạm vi khai báo `Inner`, tên `T` của inner che tên `T` của outer.
3. Trường `outerValue` đã được khai báo với `T` của outer; nó không tự đổi kiểu chỉ vì method của inner đang tham chiếu tới nó.
4. Trường `innerValue` thuộc `Inner<T>`, vì vậy dùng `T` của inner.
5. Với `Outer<String>.Inner<Integer>`, outer value có kiểu `String` và inner value có kiểu `Integer`.

Dạng tên `Outer<String>.Inner<Integer>` đặc biệt hữu ích: nó bộc lộ rằng outer và inner có **hai lựa chọn type argument độc lập**.

### Sửa để tránh shadowing

```java
class Outer<T> {
    class Inner<U> {
        private U innerValue;
    }
}
```

Đây là khai báo minh họa. `T` thuộc outer, `U` thuộc inner; mọi lần dùng sau đó đều rõ. Khi cần tương tác với outer, inner có thể sử dụng trường hoặc phương thức outer theo quan hệ kiểu vốn đã khai báo.

### Static nested class không phải trường hợp giống hệt

Một `static class Nested<U>` đặt trong generic outer class **không** mang ngữ cảnh type argument của outer instance. Vì vậy không nên gọi việc khai báo type parameter của static nested class là một ví dụ tương đương hoàn toàn với shadowing của non-static inner class. Nếu cần static nested class chứa dữ liệu khác loại, khai báo type parameters của chính nó và truyền những dữ liệu cần thiết vào constructor.

## 8. Phương thức static và tên T của generic class

Type parameter của class gắn với việc tham số hóa các object, còn thành viên `static` thuộc lớp, không thuộc riêng `Box<String>` hay `Box<Integer>`. Vì vậy static method không thể trực tiếp dùng class-level `T` như thể nó đã có một type argument cụ thể.

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    // static T wrong(T input) { return input; } // Không hợp lệ.

    static <U> Box<U> of(U input) {
        return new Box<>(input);
    }
}
```

Trong `static <U> Box<U> of(U input)`, `U` là type parameter **của static method**. Nó không trỏ về type parameter `T` của một object `Box<T>` bất kỳ. Việc chọn tên `U` giúp người đọc thấy rõ nguồn gốc.

Bạn cũng có thể viết `static <T> Box<T> of(T input)`, đây là generic method hợp lệ với `T` thuộc method, nhưng dùng `U` sẽ tránh gây cảm giác vô tình dùng lại `T` của class. Khi đọc mã cần tách hai tầng này, đặc biệt trong factory methods.

## 9. Shadowing khác type inference và type erasure

Ba khái niệm đôi khi bị trộn lẫn:

| Khái niệm | Xảy ra ở đâu | Tác động |
| --- | --- | --- |
| **Shadowing** | Cú pháp và scope của khai báo | Tên `T` ở phạm vi trong trỏ tới type parameter mới thay vì type parameter ngoài |
| **Type inference** | Kiểm tra lời gọi lúc biên dịch | Tìm type arguments thỏa ràng buộc của generic method/class |
| **Type erasure** | Cách biên dịch generics sang bytecode | Phần lớn type arguments không hiện diện như runtime specialization; compiler chèn cast/bridge khi cần |

Một method `<T> T echo(T)` có thể che `T` của outer class ngay trong code nguồn, sau đó tại invocation `echo(123)` compiler suy luận `T` của **method** phù hợp `Integer`. Erasure của method `T` không có bound thường là `Object`. Mỗi khái niệm trả lời một câu hỏi khác nhau:

- Shadowing: **tên T này được khai báo ở đâu?**
- Inference: **T của lời gọi cụ thể được suy luận thành kiểu gì?**
- Erasure: **kiểu generic được biểu diễn thế nào ở runtime?**

Dùng lại tên `T` không khiến JVM tạo hai class runtime mới, cũng không buộc hai type parameters cùng type argument.

## 10. Các dấu hiệu trong IDE và lỗi compiler

### 10.1. Gán method T vào class T thất bại

```java
class Store<T> {
    private T stored;

    <T> void set(T incoming) {
        // stored = incoming; // Incompatible types.
    }
}
```

Compiler không thể bảo đảm phép gán: method-level `T` và class-level `T` là hai khai báo độc lập. Một lời gọi method cụ thể có thể suy luận cùng kiểu, nhưng implementation phải đúng với mọi cách gọi hợp lệ. Sửa bằng `void set(T incoming)` nếu thật sự cần cùng class T.

### 10.2. Return type trông giống T nhưng không trùng kiểu của object

```java
class Holder<T> {
    T saved;

    <T> T echo(T input) {
        return input;
    }
}
```

Với `Holder<String> holder`, `holder.echo(1)` có thể tạo kết quả `Integer`. Nếu người viết API hứa “echo trả cùng kiểu với dữ liệu đã lưu” thì chữ ký là sai ý định, dù vẫn biên dịch.

### 10.3. Một method được khai báo với tên type variable gây hiểu nhầm

```java
class Cache<K, V> {
    <V> V convert(V input) {
        return input;
    }
}
```

`<V>` ở method che `V` của `Cache<K,V>`. `convert` không nhất thiết liên quan tới giá trị kiểu `V` trong cache. Đổi thành `<R> R convert(R input)` nếu hoàn toàn độc lập, hoặc bỏ type parameter mới nếu method phải dùng cache value type.

### 10.4. Lỗi được “chữa” bằng cast không bảo đảm

Khi gặp incompatible types do shadowing, không nên thêm unchecked cast như `(T) incoming` để làm im compiler. Type erasure có thể khiến cast không xác minh được type argument mong muốn, đẩy lỗi tới lúc đọc dữ liệu. Cần sửa **khai báo phạm vi** và API contract trước.

### 10.5. Tooling hiện gợi ý cùng tên T hai lần

Trong IDE, dùng chức năng “go to declaration” trên từng `T`. Nếu nó nhảy tới `<T>` của method thay vì `class Box<T>`, bạn đã xác định được shadowing. Hiển thị type tại từng expression, xem generic signature và bật compiler warning có thể giúp phát hiện vấn đề từ sớm. Một linter có thể cảnh báo về hidden type parameter tùy cấu hình, nhưng không nên coi cảnh báo ấy là bắt buộc trong mọi build Java.

## 11. Vì sao tránh che khuất tên type parameter?

### 11.1. Ngăn hiểu sai hợp đồng của API

Người đọc `class Service<T> { <T> T transform(T x) ... }` thường có khuynh hướng nghĩ `transform` phụ thuộc kiểu của `Service<T>`. Thực tế method `<T>` đã tách quan hệ đó. Nếu tên khác `<R>`, người đọc nhận ra mối quan hệ (hoặc sự độc lập) nhanh hơn.

### 11.2. Dễ theo dõi ràng buộc khi mở rộng method

Một method nhỏ có thể chỉ chứa `return input`, nhưng khi thêm field, mapper hay collection, cần phân biệt kiểu lưu trong class với kiểu đầu vào mới. Tên trùng khiến việc thêm code dễ dẫn tới incompatible types và cast không an toàn.

### 11.3. Refactor ít nhầm phạm vi

Một lần sửa từ `<T> T echo(T)` sang “lưu giá trị vào field T” có thể bị ảnh hưởng bởi method-level T mới. Nếu ban đầu tên rõ nghĩa `<U> U echo(U)`, khi thêm code dễ nhận thấy rằng `U` không thể gán thẳng cho field `T`.

### 11.4. Code review nhận diện đúng generic bounds

Khi class có `<T extends Number>` còn method có `<T extends CharSequence>`, việc cùng dùng `T` che giấu hai khả năng hoàn toàn khác nhau. Dùng `N` và `S` hoặc `NUMBER` và `TEXT` làm lộ các hợp đồng thực.

### 11.5. Dễ kiểm tra sự liên kết giữa input và output

Trong API chuyển đổi, `<R> R convert(Function<? super T,? extends R> f)` cho thấy dữ liệu `T` của class được biến thành `R`. Với hai biến đều viết `T`, tính độc lập này bị che mờ.

Điều cần tránh là **sự mơ hồ do trùng tên trong scope lồng nhau**. Không cần đặt những cái tên dài, phức tạp hoặc thay mọi `T` của dự án bằng một kiểu đặt tên duy nhất.

## 12. Khi nào tái sử dụng tên T vẫn ổn?

`T` là quy ước rất phổ biến cho “một kiểu chưa biết”. Việc dùng `T` trong những scope độc lập là tự nhiên:

```java
class Utilities {
    static <T> T first(java.util.List<T> values) {
        return values.get(0);
    }

    static <T> T last(java.util.List<T> values) {
        return values.get(values.size() - 1);
    }
}
```

Hai method khai báo `<T>` riêng, không lồng nhau; mỗi method chỉ có một type variable và mọi vị trí của `T` trong method ấy đều liên kết với nhau đúng như mong muốn. Tên `T` có giá trị vì đơn giản.

Tương tự, `class Box<T>` và `class Queue<T>` trong hai top-level class khác nhau dùng `T` độc lập; không có xung đột. Shadowing đáng tránh khi **một khai báo T ở scope trong che T của scope ngoài** và người đọc dễ nhầm chúng có cùng ý nghĩa.

Quy tắc thực hành:

- Một type variable duy nhất trong một scope ngắn: `T` thường đủ rõ.
- Hai type variables độc lập trong cùng chữ ký: `T,R` hoặc tên theo vai trò.
- Class generic và method generic nằm trong class: dùng tên khác nhau nếu method khai báo type variable mới.
- Nested non-static generic class: không tái dùng tên của generic outer class.
- Khi một method cần chính `T` của class: **không** khai báo thêm `<T>`.
- Khi method không liên quan tới class T: đặt `<U>`, `<R>` hoặc tên có ý nghĩa.

## 13. Phân biệt shadowing với các khái niệm dễ nhầm

### 13.1. Shadowing type parameter và shadowing local variable

```java
class Example<T> {
    private int size = 5;

    void print(int size) {
        System.out.println(size);
        System.out.println(this.size);
    }
}
```

Đoạn minh họa trên có **parameter tên size** che **field tên size**. Có thể dùng `this.size` để chỉ field. Nhưng khi method khai báo `<T>` che class `T`, `this.T` **không phải cú pháp Java hợp lệ** để chỉ biến kiểu của class. Cách sửa thông thường là không dùng lại tên type parameter hoặc thiết kế lại quan hệ kiểu; `this` không mở ra một đường truy cập “T kiểu của class” bằng một tên trực tiếp khác.

### 13.2. Shadowing khác method overriding

Overriding là việc subtype cung cấp implementation của phương thức được kế thừa theo quy tắc chữ ký/kiểu trả về. Shadowing `T` là **phân giải tên trong source code**, không phải override, không phải overload và không ảnh hưởng trực tiếp đến dynamic dispatch.

### 13.3. Shadowing khác đặt tên lớp con trùng kiểu tham số

```java
class Parent<T> {
    T value;
}

class Child<T> extends Parent<T> {
}
```

Đây là ví dụ chuyển tiếp type argument: `Child<T>` khai báo type parameter **của Child**, rồi dùng chính tham số đó làm type argument của `Parent<T>`. Hai khai báo type parameter của `Parent` và `Child` là độc lập, nhưng subclass **ràng buộc chúng tại mệnh đề `extends Parent<T>`**. Không nên chỉ nhìn hai tên `T` rồi coi đây là lỗi shadowing cùng cấu trúc như method nằm trong class.

Nếu viết `class Child<U> extends Parent<U>`, ý nghĩa không đổi mà sự phân biệt khai báo có thể rõ hơn. Chọn cách đặt tên phù hợp ngữ cảnh; đừng kết luận chỉ từ tên.

### 13.4. Overload khác tên type parameter không tạo overload khác

Hai generic methods:

```java
// Không được cùng khai báo trong một class:
static <T> void log(T value) {}
static <U> void log(U value) {}
```

sẽ xung đột vì sau type erasure chúng có cùng chữ ký runtime tương ứng `log(Object)`. Đổi tên `T` thành `U` không tạo overload mới, cũng không liên quan tới shadowing giữa class và method.

### 13.5. Type parameter và type argument

Trong `class Box<T>`, `<T>` khai báo. Trong `Box<String>`, `<String>` truyền type argument. Trong `List<T>` bên trong `Box<T>`, `T` chỉ được **sử dụng**, không khai báo mới. Những cú pháp trông giống nhau này đóng vai trò khác nhau nên phải xác định vị trí trước khi nói tới shadowing.

## 14. Type parameter shadowing và generic interface

Một generic class có thể dùng type parameter của mình để triển khai interface:

```java
interface Container<E> {
    E read();
}

class ValueContainer<T> implements Container<T> {
    private final T stored;

    ValueContainer(T stored) {
        this.stored = stored;
    }

    @Override
    public T read() {
        return stored;
    }
}
```

`T` của `ValueContainer<T>` là type argument truyền cho `Container<E>`. Phần `implements Container<T>` **không tạo biến kiểu mới**. Trong class này, `read()` trả `T` của ValueContainer đúng hợp đồng của Container.

Nếu thêm một generic method:

```java
class ValueContainer<T> implements Container<T> {
    private final T stored;

    ValueContainer(T stored) {
        this.stored = stored;
    }

    @Override
    public T read() {
        return stored;
    }

    <R> R convert(java.util.function.Function<? super T, ? extends R> f) {
        return f.apply(stored);
    }
}
```

Lúc này `T` của class liên hệ với interface và input của mapper; `R` của method mang kiểu kết quả. Không có shadowing; quan hệ kiểu trong chữ ký được biểu diễn chính xác và dễ duy trì.

## 15. Reflection có thể phân biệt hai TypeVariable tên T

Phần này dành cho người đã biết reflection; nó làm rõ rằng hai type variables cùng tên **không đồng nhất về khai báo**. Java reflection cung cấp `TypeVariable<?>` với tên và `GenericDeclaration` tương ứng.

Tạo `TypeVariableIdentityDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;

public class TypeVariableIdentityDemo {
    static class Holder<T> {
        <T> T echo(T value) {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        TypeVariable<?> classT = Holder.class.getTypeParameters()[0];
        Method method = Holder.class.getDeclaredMethod("echo", Object.class);
        TypeVariable<?> methodT = method.getTypeParameters()[0];

        System.out.println(classT.getName());
        System.out.println(methodT.getName());
        System.out.println(
                classT.getGenericDeclaration().equals(
                        methodT.getGenericDeclaration()));
    }
}
```

Chạy:

```bash
javac TypeVariableIdentityDemo.java
java TypeVariableIdentityDemo
```

`stdout`:

```text
T
T
false
```

Cả hai biến kiểu đều có `getName()` là `"T"`. Nhưng khai báo gốc khác nhau: `classT` thuộc `Holder.class`, `methodT` thuộc method `echo`. Giá trị `false` ở phép so sánh cho thấy chúng không phải cùng một generic declaration. Method `echo(T)` có type parameter không bound nên tham số runtime bị erasure thành `Object`, vì vậy `getDeclaredMethod("echo", Object.class)` tìm đúng method.

Reflection không biến type arguments generic thành runtime types riêng của từng object. Nó chỉ cho phép khảo sát metadata của các **khai báo** vẫn có trong class file. Bạn không cần reflection để sử dụng generic thông thường; ví dụ này chỉ củng cố lý do không được coi hai type variables cùng tên là một.

## 16. Bài tập: nhận diện và sửa shadowing

### Bài 1 — Dự đoán kiểu

Cho:

```java
class Container<T> {
    T get() { return null; }

    <T> T identity(T x) {
        return x;
    }
}
```

Đối với biến `Container<String> c`:

- `c.get()` có kiểu biểu thức gì?
- `c.identity(123)` có thể trả gì?
- Hai chữ `T` trong class và method có cùng khai báo không?

**Đáp án:** `get()` có kiểu tĩnh `String`; `identity(123)` có thể suy luận method T là `Integer`; hai `T` thuộc hai khai báo khác nhau. `get()` trong mẫu đang trả null, vì vậy không tự xem nó là một store có dữ liệu thật.

### Bài 2 — Tìm lỗi trong setter

```java
class Store<T> {
    private T value;

    <T> void set(T v) {
        // value = v; // Vì sao không biên dịch?
    }
}
```

**Đáp án:** `v` mang type variable T thuộc method còn `value` thuộc class. Muốn setter nhận cùng kiểu với field, xóa `<T>` ở method và dùng `void set(T v) { value = v; }`.

### Bài 3 — Method có kiểu kết quả mới

Thay vì:

```java
class Box<T> {
    T value;

    <T> T transform(java.util.function.Function<T, T> mapper) {
        return null;
    }
}
```

hãy viết method chuyển kiểu của giá trị field từ `T` thành `R`, không làm thay đổi field.

**Đáp án mẫu:**

```java
<R> R transform(java.util.function.Function<? super T, ? extends R> mapper) {
    return mapper.apply(value);
}
```

`T` lấy từ generic class, `R` do method khai báo. Nếu muốn trả một `Box<R>` thay vì `R`, có thể tạo `new Box<R>(...)` với constructor phù hợp. Đây là đoạn method minh họa cần đặt trong class có `T value`.

### Bài 4 — Hai bounds cùng tên

Một class khai báo `<T extends Number>`, method trong class khai báo `<T extends CharSequence>`. Phương thức có thể gọi `length()` hay `doubleValue()` trên parameter mang type variable T của method?

**Đáp án:** được gọi `length()` vì method T có bound `CharSequence`, không được compiler bảo đảm `doubleValue()`. Bound `Number` thuộc T của class không truyền vào T của method.

### Bài 5 — Outer và Inner

Với `Outer<String>.Inner<Integer>` trong ví dụ trước, hãy xác định kiểu của `outerValue` và `innerValue`. Nếu đổi declaration inner thành `class Inner<U>` thì annotation kiểu nên viết gì?

**Đáp án:** lần lượt `String` và `Integer`. Với khai báo `Inner<U>`, vị trí dùng vẫn có dạng `Outer<String>.Inner<Integer>`; trong source của inner, dùng `U` thay cho `T` để chỉ kiểu component của inner.

### Bài 6 — Hai generic methods độc lập

```java
static <T> T left(T a, T b) { return a; }
static <T> T right(T a, T b) { return b; }
```

Đây có phải trường hợp nên cấm tái dùng tên `T` không?

**Đáp án:** không. Hai method-level `T` có phạm vi riêng, không lồng nhau và không che một `T` outer class; cùng dùng tên theo quy ước là dễ đọc.

### Bài 7 — Review một API trước và sau

**Trước:**

```java
class Holder<T> {
    T stored;
    <T> T echo(T input) { return input; }
}
```

**Sau:**

```java
class Holder<T> {
    T stored;
    <U> U echo(U input) { return input; }
}
```

Hãy trả lời: method `echo` trong hai phiên bản có quan hệ kiểu với field `stored` không? Việc đổi tên có thay đổi hành vi runtime không?

**Đáp án:** cả hai đều không liên kết kiểu method argument với `stored`. Đổi tên từ method T sang U làm rõ hợp đồng source nhưng không thay logic, không tạo specialized class và không thay đổi cách Java Generics được xóa kiểu. Kết quả dùng method vẫn được compiler suy luận từ lời gọi như cũ.

## 17. Checklist khi đọc hoặc review tên type parameter

Khi một đoạn code generic có nhiều cấp khai báo, lần lượt hỏi:

1. **T đang xét được khai báo ở đâu?** Class, interface, record, method hay constructor?
2. Có một `<T>` **mới** nằm bên trong phạm vi class/interface đã có `T` không?
3. Method này muốn dùng kiểu lưu trong object hay muốn khai báo kiểu đầu vào/kết quả độc lập?
4. Có cùng tên `T` ở hai cấp nhưng bounds khác nhau không?
5. Những field, parameter và return type nào phải được ràng buộc với **T của class**?
6. Những vị trí nào là kiểu kết quả mới nên đặt `R` hoặc `U`?
7. Có ai dùng unchecked cast để “sửa” một lỗi vốn do khai báo lại type parameter không?
8. Trong nested class, dấu `<T>` là khai báo mới hay chỉ là type argument của một generic type khác?
9. Các type arguments ở caller có được suy luận đúng không nếu không xem tên `T` như một kiểu runtime cụ thể?
10. Tên kiểu đang giúp người đọc nhận ra quan hệ dữ liệu, hay đang che mất sự độc lập giữa các kiểu?

Nếu cùng một `T` ở hai cấp khai báo có thể khiến người đọc trả lời nhầm những câu này, hãy đổi tên type parameter ở cấp trong hoặc bỏ khai báo type parameter thừa. Giữ tên `T` khi chỉ có một nghĩa rõ ràng trong phạm vi đang đọc.

## 18. Kết luận

**Shadowing của type parameter là quy tắc về phạm vi tên lúc biên dịch.** Trong `class Box<T> { <T> T echo(T value) ... }`, `T` của method là một khai báo mới và che khuất `T` của class. Việc viết cùng chữ `T` không làm hai kiểu liên quan với nhau, cũng không khiến JVM lưu hai kiểu runtime khác nhau theo tên.

Khi method cần thao tác trên dữ liệu đã lưu, hãy **dùng trực tiếp `T` của class** mà không khai báo lại. Khi method cần một kiểu riêng, hãy đặt `<R>`, `<U>` hoặc tên theo vai trò để làm lộ quan hệ: `T` cho đầu vào hiện có, `R` cho kết quả mới, `U` cho kiểu độc lập. Phân biệt được scope, inference và erasure giúp bạn đọc generic signature chính xác, tránh cast không cần thiết và duy trì những API dễ hiểu khi chương trình phát triển.