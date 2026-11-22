# Thay thế tham số kiểu khi ghi đè phương thức trong Java Generics

## 1. Mục tiêu và tình huống

Khi một lớp con kế thừa lớp hoặc triển khai interface có tham số kiểu, Java cần xác định **phương thức sau khi thay thế tham số kiểu** có thực sự ghi đè (*override*) phương thức của lớp cha hay không.

Ví dụ:

```java
class Box<T> {
    T get() {
        return null;
    }

    void put(T value) {
    }
}

class StringBox extends Box<String> {
    @Override
    String get() {
        return "Java";
    }

    @Override
    void put(String value) {
        System.out.println(value);
    }
}
```

Trong `Box<T>`, `get()` trả `T` và `put(...)` nhận `T`. Với kiểu cha trực tiếp `Box<String>`, trình biên dịch xem các kiểu trong **hợp đồng thừa kế** như đã được thay `T` bằng `String`:

```text
Box<T> khai báo              Khi nhìn từ Box<String>
--------------------------  ---------------------------
T get()                     String get()
void put(T value)           void put(String value)
```

Vì vậy `StringBox.get()` và `StringBox.put(String)` là các phương thức ghi đè hợp lệ. `@Override` giúp compiler xác nhận điều đó.

Tuy nhiên, sau **type erasure**, bytecode của `Box<T>` vẫn có thể mang chữ ký `Object get()` và `put(Object)`. Để bảo toàn đa hình, compiler có thể sinh **bridge method** trong lớp con. Cần phân biệt ba bước:

1. **Thay thế tham số kiểu khi kiểm tra source:** từ `Box<T>` đến `Box<String>`, các chỗ dùng `T` trong hợp đồng được chuyên biệt hóa thành `String`.
2. **Xác định quan hệ override:** tên, tham số, phạm vi truy cập, kiểu trả về và giới hạn generic phải tuân thủ quy tắc ngôn ngữ.
3. **Phát sinh bytecode:** Java xóa nhiều thông tin generic khỏi descriptor và thêm bridge khi cần duy trì dispatch.

Đây là bài về **thay thế tham số kiểu trong override**. Giới hạn đệ quy, wildcard và erasure được nhắc tới ở mức cần thiết để đọc đúng hợp đồng ghi đè.

## 2. Hai loại tham số kiểu cần phân biệt

### 2.1. Type parameter thuộc lớp hoặc interface

```java
class Repository<T> {
    T save(T value) {
        return value;
    }
}

class StringRepository extends Repository<String> {
    @Override
    String save(String value) {
        return value.strip();
    }
}
```

Ở lớp cha, `T` được khai báo ngay tại `Repository<T>`. Lớp con chọn `String` qua `extends Repository<String>`, nên tham số và kết quả `save` trong hợp đồng kế thừa đều được thay tương ứng.

Điều này **không tạo một bản sao `Repository<String>` có bytecode riêng**. Đây là chuyên biệt hóa ở mức kiểu source, còn `Repository` vẫn là một lớp generic được biên dịch theo mô hình erasure.

### 2.2. Type parameter thuộc chính phương thức

```java
class Repository<T> {
    <N extends Number> N number(N value) {
        return value;
    }
}
```

`N` được khai báo tại **phương thức** `number`; nó độc lập với `T` của lớp. Nếu kế thừa `Repository<String>`, ta chỉ thay các lần xuất hiện của `T` thuộc lớp. Không được tự ý suy diễn rằng `N` cũng trở thành `String`.

Lớp con có thể ghi đè bằng tham số kiểu phương thức **đổi tên**:

```java
class StringRepository extends Repository<String> {
    @Override
    <X extends Number> X number(X value) {
        return value;
    }
}
```

`X` và `N` là tên khác nhau của cùng vị trí tham số kiểu phương thức và có giới hạn tương ứng. Sự đổi tên này tương tự đổi tên biến ràng buộc trong một biểu thức generic; nó không thay đổi hợp đồng.

Ngược lại:

```java
// Minh họa lỗi khi dùng @Override:
class Base {
    <N> void accept(N value) {
    }
}

class Child extends Base {
    @Override
    void accept(String value) {
    }
}
```

`accept(String)` **không ghi đè** phương thức generic `<N> accept(N)`: phương thức cha phải chấp nhận mọi kiểu `N` hợp lệ, còn phương thức con chỉ chấp nhận `String`. Khi có `@Override`, compiler báo phương thức không override một phương thức của supertype. Nếu bỏ `@Override`, đây là một overload với tham số cụ thể, còn phương thức generic được kế thừa vẫn tồn tại.

**Quy tắc:** tham số kiểu **của lớp** được thay theo phép kế thừa; tham số kiểu **của phương thức** vẫn được khai báo độc lập tại từng phương thức generic. Không thể biến phương thức generic của cha thành một bản chỉ xử lý `String` chỉ bằng cách ghi đè có tham số `String`.

## 3. Trình tự suy ra chữ ký override

Xét:

```java
import java.util.List;

class Repository<T> {
    T save(T value) {
        return value;
    }

    List<T> items(T value) {
        return List.of(value);
    }

    <N extends Number> N number(N value) {
        return value;
    }
}

class StringRepository extends Repository<String> {
    @Override
    String save(String value) {
        return value.strip();
    }

    @Override
    List<String> items(String value) {
        return List.of(save(value));
    }

    @Override
    <X extends Number> X number(X value) {
        return value;
    }
}
```

Hãy đọc theo trình tự:

1. **Tìm khai báo generic của lớp cha**: `Repository<T>`.
2. **Tìm phép kế thừa cụ thể**: `extends Repository<String>`, tức phép thay `T := String`.
3. **Áp dụng thay thế vào các lần dùng `T` thuộc lớp**: `save(T)` thành `save(String)`, `List<T> items(T)` thành `List<String> items(String)`.
4. **Giữ riêng type parameter của phương thức**: `<N extends Number> N number(N)` vẫn là một phương thức generic. Có thể dùng tên mới `<X extends Number> X number(X)` với bound phù hợp.
5. **Kiểm tra `@Override`** và các quy tắc Java: kiểu tham số, return-type substitutability, access, `final`, `static`, checked exceptions…
6. Sau khi override hợp lệ, **xem erasure** để hiểu vì sao compiler có thể phát sinh phương thức bridge.

Bảng đối chiếu:

| Phương thức khai báo ở `Repository<T>` | Hợp đồng nhìn từ `Repository<String>` | Khai báo ở lớp con |
| --- | --- | --- |
| `T save(T)` | `String save(String)` | `String save(String)` |
| `List<T> items(T)` | `List<String> items(String)` | `List<String> items(String)` |
| `<N extends Number> N number(N)` | Vẫn generic với `N extends Number` | `<X extends Number> X number(X)` |

Điểm quyết định ở đây là **cùng một `T` thuộc lớp** xuất hiện trong nhiều vị trí đều được thay nhất quán. Không được chỉ thay kiểu tham số mà giữ nhầm kiểu trả về, hoặc thay type variable thuộc một phạm vi khai báo khác.

## 4. Kiểu tham số phải khớp theo hợp đồng kế thừa

### 4.1. `put(Object)` không tự ghi đè `put(String)`

```java
class Base<T> {
    void put(T value) {
    }
}

class Wrong extends Base<String> {
    // Không hợp lệ; javac có thể báo "name clash":
    void put(Object value) {
    }
}
```

Sau khi thay `T := String`, phương thức cha được nhìn theo hợp đồng source là `put(String)`. `put(Object)` của lớp con không trở thành `put(String)` chỉ vì `String` là subtype của `Object`.

Ví dụ trên đặc biệt nguy hiểm: `put(Object)` và phương thức cha có **cùng erasure** là `put(Object)` nhưng không hình thành một override hợp lệ. `javac` từ chối với lỗi dạng:

```text
name clash: put(Object) in Wrong and put(String) in Base
have the same erasure, yet neither overrides the other
```

Đây là lỗi khác với một overload thông thường. Khi thấy “same erasure, yet neither overrides the other”, hãy đối chiếu **chữ ký kế thừa sau substitution** và **chữ ký JVM sau erasure**, thay vì thử thêm cast vào body.

Sửa đúng:

```java
class Correct extends Base<String> {
    @Override
    void put(String value) {
        System.out.println(value);
    }
}
```

### 4.2. Khác type argument trong tham số không đồng nghĩa override

```java
import java.util.List;

class Base {
    void publish(List<String> values) {
    }
}

// Không phải bản override hợp lệ:
class Wrong extends Base {
    // void publish(List<Integer> values) {} // Name clash
}
```

`List<String>` và `List<Integer>` bị xóa về cùng kiểu `List`. Java không cho tạo một phương thức mới cùng tên/cùng erased parameter list nhưng khác type argument như vậy trong quan hệ kế thừa không tương thích. Nếu ý định là xử lý khác loại dữ liệu, hãy chọn chữ ký hoặc tên API khác phù hợp.

**Overload** chọn phương thức dựa trên danh sách tham số và luật overload; **override** thay implementation của một phương thức đã được kế thừa. Java không cho phép “overload bằng generic type argument” theo cách chỉ thay `List<String>` thành `List<Integer>`.

### 4.3. Đổi tên type parameter của phương thức thì khác

Đây là trường hợp hợp lệ:

```java
class Base {
    <T extends Number> T echo(T input) {
        return input;
    }
}

class Child extends Base {
    @Override
    <U extends Number> U echo(U input) {
        return input;
    }
}
```

Tên `T` và `U` khác nhau nhưng cấu trúc generic tương ứng. Sửa thành `<U extends CharSequence>` không còn cùng hợp đồng; không thể đổi tùy ý bound của phương thức đang override.

Đừng nhầm việc **đổi tên biến kiểu** (`T` → `U`) với việc **chuyên biệt hóa biến kiểu** (`T` → `String`). Việc đầu thường hợp lệ khi bound khớp; việc sau phụ thuộc biến đó được khai báo tại lớp hay tại phương thức.

## 5. Kiểu trả về: covariant, invariant và return-type substitutability

Một phương thức override phải có kiểu trả về hợp lệ theo quy tắc *return-type substitutability*. Trong các trường hợp tham chiếu thông dụng, kiểu trả về có thể là subtype thích hợp của kiểu cha sau khi thay type parameter.

Ví dụ hợp lệ:

```java
class Base<T> {
    T load() {
        return null;
    }
}

class Child extends Base<Number> {
    @Override
    Integer load() {
        return 10;
    }
}
```

Sau phép thay `T := Number`, `Base<Number>.load()` có hợp đồng trả `Number`; `Integer` là subtype của `Number`, nên việc thu hẹp kiểu trả về được cho phép. Đây là **covariant return**.

Một trường hợp dễ nhầm với generic parameterized return:

```java
import java.util.List;

class Base {
    List<Number> values() {
        return List.of(1);
    }
}

class Wrong extends Base {
    // @Override List<Integer> values() { return List.of(1); } // Sai
}
```

Dù `Integer extends Number`, `List<Integer>` **không phải subtype** của `List<Number>`: generic Java bất biến. Compiler không cho override bằng kiểu trả về này.

Nếu API thực sự chỉ hứa trả các phần tử kiểu số bất kỳ, một hợp đồng linh hoạt hơn có thể là:

```java
import java.util.List;

class Base {
    List<? extends Number> values() {
        return List.of(1, 2);
    }
}

class Child extends Base {
    @Override
    List<Integer> values() {
        return List.of(4, 5);
    }
}
```

`List<Integer>` tương thích với `List<? extends Number>` ở vai trò **kết quả để đọc các giá trị Number**. Nhưng đó là một **quyết định thiết kế của API cha**, không phải mẹo có thể tự áp dụng từ lớp con khi chữ ký của cha đã cố định.

### 5.1. Kiểu trả về `void` và primitive

Bạn không thể tùy ý đổi `void` thành một kiểu khác khi override. Với kiểu primitive, việc widening như `int` thành `long` không tạo ra covariant return như đối với subtype tham chiếu:

```java
class Base {
    int size() { return 0; }
}

class Wrong extends Base {
    // @Override long size() { return 0L; } // Sai
}
```

Khi debug lỗi override, đừng chỉ nhìn danh sách tham số; kiểu trả về vẫn phải hợp lệ dù nó không tham gia cách lập overload bằng source code.

## 6. Sau substitution vẫn có type erasure và bridge

Trở lại:

```java
class Repository<T> {
    T save(T value) {
        return value;
    }
}

class StringRepository extends Repository<String> {
    @Override
    String save(String value) {
        return value.strip();
    }
}
```

Compiler biết `StringRepository.save(String)` là một override hợp lệ. Nhưng descriptor của `Repository.save` sau xóa `T` không có bound là:

```text
(Ljava/lang/Object;)Ljava/lang/Object;
```

Trong khi phương thức được viết ở lớp con có descriptor:

```text
(Ljava/lang/String;)Ljava/lang/String;
```

Để đảm bảo lời gọi `save` đi qua một tham chiếu kiểu `Repository<String>` vẫn dispatch đến phương thức override của lớp con, compiler có thể sinh **bridge** trong `StringRepository`, có dạng mô tả:

```java
// MÃ KHÁI NIỆM DO COMPILER SINH, KHÔNG THÊM VÀO SOURCE:
Object save(Object input) {
    return save((String) input);
}
```

Với `@Override List<String> items(String)`, erasure của kiểu trả về `List<String>` thành `List`, và vì kiểu tham số `T` thành `Object` trong lớp cha, compiler cũng có thể sinh:

```text
items(Object) -> List
```

Bridge thông thường được đánh dấu `ACC_BRIDGE` và `ACC_SYNTHETIC` trong class file. Nó là phần hỗ trợ đa hình sau erasure; **không phải** một overload mà lập trình viên tự viết.

Không phải phương thức nào sau substitution cũng cần bridge. Trong ví dụ:

```java
<N extends Number> N number(N value)
```

phương thức lớp cha và phương thức lớp con (đổi tên type variable thành `X`) đều có descriptor sau erasure:

```text
(Ljava/lang/Number;)Ljava/lang/Number;
```

Nếu không có khác biệt descriptor cần nối, compiler không cần tạo bridge riêng cho phương thức đó.

### 6.1. Bridge có thể gây `ClassCastException` nếu phá hợp đồng qua raw type

Nếu code legacy dùng raw type:

```java
// Không khuyến nghị:
Repository raw = new StringRepository();
raw.save(123);
```

Lời gọi compile được với raw type (thường có cảnh báo unchecked). Bridge `save(Object)` của lớp con cố chuyển `123` thành `String`, nên phát sinh `ClassCastException` tại runtime. Đây không chứng minh generics “chỉ là kiểm tra giả”: lỗi xuất hiện vì code raw/unchecked đã bỏ qua hợp đồng `Repository<String>` mà compiler cần bảo vệ.

Trong code mới, dùng tham chiếu tham số hóa:

```java
Repository<String> safe = new StringRepository();
safe.save("Java");
```

Lời gọi `safe.save(123)` sẽ bị từ chối ở compile time.

## 7. Ví dụ Java 17 hoàn chỉnh

Tạo file **`OverrideSubstitutionDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class OverrideSubstitutionDemo {
    static class Repository<T> {
        public T save(T value) {
            return value;
        }

        public List<T> items(T value) {
            return List.of(value);
        }

        public <N extends Number> N number(N value) {
            return value;
        }
    }

    static final class StringRepository extends Repository<String> {
        @Override
        public String save(String value) {
            return value.strip();
        }

        @Override
        public List<String> items(String value) {
            return List.of(save(value));
        }

        @Override
        public <X extends Number> X number(X value) {
            return value;
        }
    }

    static class NumberSource {
        public List<? extends Number> values() {
            return List.of(1, 2);
        }
    }

    static final class IntegerSource extends NumberSource {
        @Override
        public List<Integer> values() {
            return List.of(4, 5);
        }
    }

    public static void main(String[] args) {
        Repository<String> repository = new StringRepository();

        System.out.println(repository.save("  Java  "));
        System.out.println(repository.items("  Generics "));
        System.out.println(repository.number(42));
        System.out.println(new IntegerSource().values());

        Arrays.stream(StringRepository.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .map(m -> m.getName() + "("
                        + Arrays.stream(m.getParameterTypes())
                                .map(Class::getSimpleName)
                                .collect(Collectors.joining(", "))
                        + ") -> " + m.getReturnType().getSimpleName())
                .sorted()
                .forEach(System.out::println);
    }
}
```

Biên dịch bằng Java 17, hoặc JDK mới hơn có hỗ trợ `--release 17`:

```bash
javac --release 17 OverrideSubstitutionDemo.java
java OverrideSubstitutionDemo
```

Stdout:

```text
Java
[Generics]
42
[4, 5]
items(Object) -> List
save(Object) -> Object
```

Phần đầu xác nhận các giá trị trả về giữ hợp đồng generic của `Repository<String>`. Hai dòng cuối được tạo bằng reflection, lọc `Method.isBridge()`, format tên/tham số/kiểu trả về và sắp xếp tên: compiler đã sinh bridge cho `items` và `save`. Phương thức generic `number` chỉ đổi tên biến kiểu mà không cần bridge vì descriptor cơ bản không thay đổi.

### 7.1. Xem signature bytecode

Sau `javac`, chạy:

```bash
javap -p -s 'OverrideSubstitutionDemo$StringRepository'
```

Dấu nháy đơn giữ nguyên ký tự `$` trong các shell có khai triển biến. Trong phần kết quả tương ứng, bạn có thể nhìn thấy:

```text
public java.lang.String save(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

public java.util.List<java.lang.String> items(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/util/List;

public <X extends java.lang.Number> X number(X);
  descriptor: (Ljava/lang/Number;)Ljava/lang/Number;

public java.util.List items(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/util/List;

public java.lang.Object save(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
```

Để nhìn cờ của bridge:

```bash
javap -p -v 'OverrideSubstitutionDemo$StringRepository'
```

Tìm `ACC_BRIDGE` và `ACC_SYNTHETIC` ở hai phương thức chuyển tiếp. `javap -s` hiển thị descriptor; `javap -v` cho phép kiểm tra flags, Signature attribute và hướng gọi trong bytecode.

### 7.2. Kiểu tĩnh và kiểu runtime của cùng một đối tượng

```java
Repository<String> repository = new StringRepository();
String name = repository.save("  Java  ");
```

- Compiler nhìn `repository` theo `Repository<String>`; `save` nhận và trả `String`.
- Đối tượng thực là `StringRepository`.
- Khi cần, bridge của lớp con đảm bảo lời gọi tới descriptor đã xóa được chuyển tiếp đến `save(String)`.
- Giá trị kết quả là `"Java"` nhờ `.strip()`.
- Sự thay `T := String` **không tạo** một instance chuyên biệt có trường runtime để chứa tham số kiểu `String`.

Các cấp này phối hợp để code vẫn có type safety ở source và đa hình ở runtime.

## 8. Interface generic: thay tham số kiểu qua `implements`

Cơ chế tương tự diễn ra với interface:

```java
interface Transformer<I, O> {
    O transform(I input);
}

final class LengthTransformer implements Transformer<String, Integer> {
    @Override
    public Integer transform(String input) {
        return input.length();
    }
}
```

Với phép thay `I := String`, `O := Integer`, hợp đồng kế thừa là `Integer transform(String)`. Nếu khai báo `Object transform(Object)` ở lớp triển khai, nó không trở thành override đúng ý định chỉ vì các kiểu sau erasure của interface gốc cũng là `Object`. Kiểm tra source vẫn dựa trên **hợp đồng đã thay tham số kiểu**.

Một lớp có thể kế thừa tham số kiểu qua nhiều tầng:

```java
interface Sink<T> {
    void accept(T value);
}

abstract class BaseSink<U> implements Sink<U> {
}

final class StringSink extends BaseSink<String> {
    @Override
    public void accept(String value) {
        System.out.println(value);
    }
}
```

Lần theo `StringSink -> BaseSink<String> -> Sink<String>` là có thể xác định được `accept(String)`. Phép thay có thể diễn ra liên tiếp qua nhiều lớp mà không cần `StringSink` trực tiếp khai báo `implements Sink<String>`.

Khi phải debug một hierarchy phức tạp, hãy vẽ đường kế thừa và **ghi lại type argument tại mỗi cạnh**, trước khi đọc body hoặc thử ép kiểu.

### 8.1. Không thể triển khai cùng generic interface với hai type argument khác nhau

Một class không thể đồng thời nhận hai specialization không tương thích của cùng một generic interface theo các nhánh thừa kế khác nhau, ví dụ một nhánh `Sink<String>`, nhánh kia `Sink<Integer>`:

```java
interface Sink<T> {
    void accept(T value);
}

interface StringSink extends Sink<String> {
}

interface IntegerSink extends Sink<Integer> {
}

// Không hợp lệ:
// class Both implements StringSink, IntegerSink { ... }
```

Compiler ngăn lớp `Both` vì cùng một generic superinterface không thể được kế thừa với các tham số kiểu khác nhau trong một hierarchy. Đây là ràng buộc cần tính đến khi tổ chức interface dùng đa kế thừa.

## 9. Kiểu trả về generic và wildcard trong override

Wildcard không phải công cụ để tự do thay đổi kiểu tham số ở phương thức override. Nó hữu ích nhất khi **API cha được thiết kế có chủ đích** để cho phép kiểu trả về hẹp hơn:

```java
import java.util.List;

interface NumberProvider {
    List<? extends Number> get();
}

final class IntProvider implements NumberProvider {
    @Override
    public List<Integer> get() {
        return List.of(1, 2);
    }
}
```

Ở đây `List<Integer>` là subtype phù hợp của `List<? extends Number>` theo quan hệ kiểu generic có wildcard. Nhưng với phương thức nhận `List<Number>` làm tham số, lớp con không được ghi đè bằng `List<Integer>`: một `NumberProvider` được phép tiếp nhận danh sách `Number` nếu hợp đồng cha yêu cầu như vậy; thu hẹp khả năng chấp nhận đối số sẽ phá nguyên tắc thay thế.

Vì thế hãy phân biệt **covariant return** (có thể trả kiểu hẹp hơn khi hợp lệ) với việc **narrow parameter** (không tự tạo override chỉ bằng một subtype của tham số cha).

## 10. Quy tắc override khác vẫn có hiệu lực

Thay `T` bằng `String` chưa đủ để hợp đồng override đúng trong mọi tình huống. Các quy tắc Java khác vẫn áp dụng:

- **`static`**: static method không phải instance override; lớp con có thể *hide* static method trong những điều kiện ngôn ngữ cho phép.
- **`final`**: instance method `final` không được override dù chữ ký sau substitution khớp.
- **`private`**: phương thức `private` của lớp cha không được kế thừa để override.
- **Phạm vi truy cập**: không giảm visibility (ví dụ ghi đè `public` thành `protected`).
- **Checked exceptions**: phương thức override không được bổ sung checked exception rộng hơn trái hợp đồng đã kế thừa; việc substitution với generic type variable khai báo `throws` cũng phải thỏa quy tắc này.
- **Kiểu trả về**: phải return-type-substitutable; không được thay tùy tiện `List<Number>` thành `List<Integer>` hoặc đổi primitive return.
- **`@Override`**: giúp phát hiện ngay rằng phương thức dự định ghi đè thực ra chỉ là overload, name clash hoặc sai return type.

Điều kiện kiểm tra override được nêu chính xác trong Java Language Specification, mục **8.4.2 Method Signature**, **8.4.8 Inheritance, Overriding, and Hiding**, **8.4.5 Method Result** và các quy tắc generic tương ứng. Quy tắc đầy đủ còn xét *subsignature* và *override-equivalent*, vì vậy không nên cố đưa ra kết luận từ duy nhất một phép so sánh tên Java viết trong source.

### 10.1. Góc cạnh dành cho mã legacy: erasure của chữ ký phương thức generic

Java cho phép một số trường hợp *subsignature* dùng để giữ tương thích với API được generify, trong đó một chữ ký trùng với **erasure** của chữ ký kia. Điều này không đồng nghĩa mọi phương thức có “cùng erasure” đều ghi đè nhau. Ví dụ `put(Object)` ở `Base<String>` phía trên đã chứng minh ngược lại: cần xét quan hệ subsignature **sau khi thay tham số kiểu trong supertype**, không chỉ so sánh descriptor bytecode.

Nếu gặp code legacy có raw type, hãy làm rõ API gốc và chạy compiler với cảnh báo liên quan:

```bash
javac --release 17 -Xlint:unchecked -Xlint:rawtypes YourFile.java
```

Đây là lệnh minh họa để dùng với tệp thực trong dự án; thay `YourFile.java` bằng đúng tên source. Cảnh báo về raw type/unchecked là dấu hiệu nên kiểm tra hợp đồng generic, không phải lời khuyên mặc định thêm `@SuppressWarnings`.

## 11. Những lỗi biên dịch đặc trưng

### 11.1. `method does not override or implement a method from a supertype`

Nguyên nhân phổ biến:

```java
class Base {
    <T> void accept(T value) {
    }
}

class Child extends Base {
    @Override
    void accept(String value) {
    }
}
```

Phương thức của cha là **method generic**, không có tham số lớp để tự động thay thành `String`. Giải pháp phụ thuộc ý định:

- Muốn override phương thức generic: triển khai phương thức generic tương ứng, như `<U> void accept(U value)`.
- Muốn lớp con chỉ phục vụ chuỗi: chuyển hợp đồng tổng quát lên **type parameter của lớp cha** (`Base<T>`) rồi để con `extends Base<String>`.
- Muốn thêm hành vi riêng cho `String` và giữ API tổng quát: có thể viết overload `accept(String)` khi các chữ ký không clash, đồng thời nhận thức rằng nó **không override** method generic.

### 11.2. `name clash ... same erasure, yet neither overrides the other`

Nguyên nhân điển hình:

```java
class Base<T> {
    void accept(T value) {
    }
}

class Child extends Base<String> {
    void accept(Object value) {
    }
}
```

`accept(Object)` ở con không khớp `accept(String)` sau khi thay `T` trong supertype; nhưng descriptor erased của phương thức cha cũng dùng `Object`, gây clash. Cách sửa thông thường là `accept(String)` hoặc đổi tên/thiết kế API nếu thực sự cần hành vi xử lý mọi `Object`.

### 11.3. `return type ... is not compatible with ...`

Nguyên nhân:

```java
import java.util.List;

class Base {
    List<Number> read() {
        return List.of(1);
    }
}

class Child extends Base {
    @Override
    List<Integer> read() {
        return List.of(2);
    }
}
```

Phương thức con có danh sách tham số phù hợp, nhưng `List<Integer>` không return-type-substitutable cho `List<Number>`. Cách sửa là giữ `List<Number>` ở override; hoặc, nếu sở hữu API cha và thực sự cần tính linh hoạt, cân nhắc kiểu trả về `List<? extends Number>` trong hợp đồng cha.

### 11.4. `ClassCastException` trong bridge sau khi dùng raw type

Hãy tìm luồng dữ liệu đi qua tham chiếu raw hoặc unchecked cast. Nếu một `Repository<String>` thật bị dùng qua `Repository` raw để truyền `Integer`, bridge có thể phải cast đầu vào thành `String` và ném lỗi. Giải pháp là sửa **đầu vào vi phạm hợp đồng**, không xóa bridge.

## 12. Quy trình rà soát khi đọc code dự án

Với một phương thức con bị nghi không override được:

1. **Xác định chính xác supertype đã tham số hóa**: chẳng hạn `extends Repo<String>` hoặc `implements Handler<Long>`.
2. **Lần theo các cấp kế thừa** và lập phép thay cho type parameter **của class/interface** tại từng cấp.
3. **Viết lại chữ ký của phương thức cha theo góc nhìn lớp con**, gồm tham số và return. Phân biệt type parameter của phương thức với type parameter của class.
4. **Kiểm tra method subsignature và return-type substitutability**; đừng chỉ dựa vào quan hệ subtype của một đối số.
5. **Giữ `@Override`** trên implementation dự định ghi đè để compiler báo sớm khi sai.
6. Nếu có lỗi `name clash`, **tính erasure của hai chữ ký** và xác minh chúng có cùng JVM descriptor phần tham số hay không.
7. Nếu việc ghi đè compile được nhưng bytecode có phương thức bất ngờ, **dùng `javap -p -s` và `javap -v`**, hoặc `Method.isBridge()`.
8. Nếu runtime lỗi kiểu, tìm raw types, unchecked casts, heap pollution hoặc dữ liệu vi phạm hợp đồng, thay vì coi bridge tự phát sinh là nguyên nhân gốc.

Bảng nhanh:

| Dấu hiệu | Điều cần phân biệt | Hướng xử lý |
| --- | --- | --- |
| `extends Base<String>` và `Base<T>.set(T)` | `T` của class | Override bằng `set(String)`. |
| `Base.<T> set(T)` | `T` của method | Override bằng method generic tương ứng; `set(String)` là overload (khi hợp lệ). |
| `List<Integer>` trả thay `List<Number>` | Generic invariant | Giữ đúng kiểu hợp đồng hoặc thiết kế wildcard ở API cha nếu được phép. |
| `name clash` với `set(Object)` | Source subsignature khác erasure | Chỉnh đúng kiểu tham số sau phép thay hoặc đổi thiết kế API. |
| `javap` cho thấy `save(Object)` trong lớp con | Bridge do compiler tạo | Kiểm tra bridge flag và đường dispatch; không xóa phương thức synthetic. |
| Raw reference gọi subclass qua `Object` | Bỏ qua generic contract | Loại raw/unchecked API và sửa giá trị truyền vào. |

## 13. Bài luyện tập

**Bài 1.** Với:

```java
interface Store<T> {
    T add(T value);
}

class IntStore implements Store<Integer> {
    // Khai báo override nào?
}
```

<details>
<summary>Đáp án</summary>

```java
@Override
public Integer add(Integer value) {
    return value;
}
```

`T` thuộc interface `Store<T>` nên thay thành `Integer` khi `implements Store<Integer>`. Do `Store.add(T)` bị erasure về `add(Object):Object`, compiler có thể cần bridge trong implementation.

</details>

**Bài 2.** Phương thức `<X extends Number> X copy(X x)` của cha có được override bằng `<Y extends Number> Y copy(Y y)` không? Có được đổi thành `String copy(String)` không?

<details>
<summary>Đáp án</summary>

Đổi tên `X` thành `Y` với bound tương ứng là hợp lệ. `String copy(String)` không chuyên biệt hóa method generic này thành override; nếu không gây xung đột với phương thức được kế thừa, nó là overload và vẫn cần implementation generic khi lớp cha/interface yêu cầu.

</details>

**Bài 3.** Vì sao `StringRepository` có thể có `save(String)` và phương thức synthetic `save(Object)` trong class file, trong khi code Java chỉ khai báo một phương thức `save`?

<details>
<summary>Đáp án</summary>

`Repository<T>.save(T):T` sau erasure có descriptor `(Object):Object`, còn override cụ thể của con có `(String):String`. Compiler tạo bridge `(Object):Object` chuyển lời gọi đến `(String):String` để bảo toàn đa hình sau erasure.

</details>

**Bài 4.** Bạn muốn `List<Integer>` là kiểu trả về của override. API cha trả `List<Number>` hiện tại có cho phép không? Nếu đang thiết kế API mới thì lựa chọn nào diễn tả ý “danh sách những phần tử thuộc Number”?

<details>
<summary>Đáp án</summary>

Không thể trực tiếp override `List<Number>` bằng `List<Integer>` vì invariance. Nếu muốn chỉ đọc giá trị Number và chấp nhận nhiều loại phần tử số, API cha có thể công bố `List<? extends Number>`; `List<Integer>` khi đó là return type tương thích.

</details>

## 14. Ghi nhớ

**Thay thế tham số kiểu khi ghi đè** bắt đầu ở quan hệ `extends`/`implements`: `Base<T>` trở thành `Base<String>` thì những phương thức dùng **`T` của class** phải được nhìn theo `String` khi kiểm tra override. **Type parameter của method** được khai báo ở cấp phương thức không bị chuyên biệt hóa theo cách đó; nó phải tiếp tục giữ hợp đồng generic của mình, dù có thể được đổi tên biến kiểu.

Sau khi xác nhận override đúng ở source, **erasure** có thể khiến descriptor JVM của lớp cha và lớp con khác nhau; Java compiler tạo **bridge method** để giữ đa hình. Vì vậy đọc một lỗi về ghi đè generic cần phân biệt rõ **substitution ở source**, **quy tắc override**, và **descriptor/bridge ở bytecode**.