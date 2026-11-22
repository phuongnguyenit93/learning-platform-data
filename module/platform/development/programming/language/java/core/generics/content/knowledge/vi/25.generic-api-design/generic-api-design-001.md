# Chọn tham số kiểu ở cấp lớp hay cấp phương thức trong Java Generics

## Mục tiêu

Trong Java, hai chữ ký sau đều sử dụng generics:

```java
class Box<T> {
    private T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}

static <T> T identity(T value) {
    return value;
}
```

Tuy nhiên, ý nghĩa của hai biến kiểu T là khác nhau. Trong `Box<T>`, T là một phần **hợp đồng kiểu của object**: constructor, field và những method instance có thể cùng duy trì một invariant. Trong `identity`, T chỉ cần gắn đầu vào với kết quả của **một lần gọi**. Những lần gọi sau có thể suy luận một T hoàn toàn khác.

Nguyên tắc hữu ích nhất là **đặt tham số kiểu ở phạm vi nhỏ nhất vẫn bao quát mọi quan hệ kiểu mà API phải bảo đảm**. Nếu một object giữ kiểu đó xuyên suốt nhiều thao tác, dùng generic class/interface. Nếu kiểu chỉ thuộc một thuật toán, dùng generic method. Nếu không cần một tên T để liên hệ đầu vào với đầu ra, cân nhắc wildcard.

Sau bài, bạn có thể:

- Phân biệt type parameters của class, interface, method và constructor.
- Chọn đúng scope cho trạng thái `Box<T>`, `Repository<E>` và các utility methods.
- Kết hợp class-level E với method-level K/R/U.
- Viết static generic factory và tránh tham chiếu T của class trong static context.
- Nhận diện type parameter shadowing, generic method giả an toàn, raw type và erasure name clash.
- Dùng wildcard, PECS, target typing và type inference để tối ưu public API.
- Chạy chương trình Java 17 hợp lệ và kiểm chứng các ví dụ cố ý bị compiler từ chối.

## 1. T thuộc đối tượng hay thuộc lời gọi?

| Nội dung | Type parameter cấp lớp | Type parameter cấp method |
| --- | --- | --- |
| Cú pháp | `class Box<T>`, `interface Store<E>` | `static <T> T identity(T)` |
| Phạm vi | Các thành viên thích hợp của class, đặc biệt instance fields/methods | Chỉ method khai báo T |
| Kiểu được xác định tại | Việc dùng class/interface như `Box<String>` | Từng lời gọi method |
| Quan hệ thường diễn đạt | `set(T)` và `get():T` phải thống nhất | `convert(T):R` của một thao tác |
| Ví dụ | `Repository<User>`, `Cache<K,V>` | `<T,R> map(...)`, `<T> copy(...)` |
| Có thể dùng class T trong static? | Không | Static method tự khai báo `<T>` mới |
| Có cần lưu giá trị T? | Không bắt buộc nhưng thường gắn với contract lâu dài | Không tự tạo generic state cho class |

T cấp lớp không có nghĩa JVM tạo một class riêng cho từng T. Sau *type erasure*, `Box<String>` và `Box<Integer>` thường có cùng runtime class Box. Compiler mới là nơi bảo vệ các quan hệ kiểu tương ứng ở mã nguồn.

Câu hỏi đầu tiên khi review: **T có đại diện cho thứ object này chứa hoặc cung cấp nhất quán trong nhiều thao tác, hay chỉ là biến dùng một lần trong một phép toán?**

## 2. Class-level T: giữ invariant qua nhiều method

Một hộp có thể được khai báo:

```java
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T next) {
        value = next;
    }
}
```

Caller:

```java
Box<String> title = new Box<>("Java");
String current = title.get();
title.set("Generics");

// title.set(42); // Lỗi biên dịch.
```

Cùng một T liên kết field, constructor, getter và setter. Khi một tham chiếu mang kiểu `Box<String>`, `get()` trả String và `set` đòi String. Đó là lý do phù hợp để khai báo T ở cấp lớp.

Một instance khác có thể có kiểu khác:

```java
Box<Integer> counter = new Box<>(7);
counter.set(9);
```

T không bị cố định cho mọi Box trong toàn ứng dụng; từng cách tham số hóa class có contract riêng ở compile time.

### Trường hợp thực tế nên dùng class-level type parameter

- `Repository<E>` lưu nhiều E, nhận E ở `add` và trả E ở `get`.
- `Cache<K,V>` luôn dùng K làm khóa và V làm giá trị.
- `Queue<T>` hỗ trợ `offer(T)` và `poll():T`.
- `Result<T>` mô tả một kết quả typed.
- `ConfiguredMapper<T,R>` lưu callback T→R để áp dụng nhiều lần.
- `Comparable<T>` diễn đạt loại đối tượng mà một implementation biết cách so sánh.

Không phải cứ class không có field T thì không được generic: một interface có thể khai báo một **hợp đồng liên kết nhiều phương thức** dù nó không sở hữu state. Tiêu chí chính là phạm vi cần giữ một T thống nhất.

## 3. Method-level T: thuật toán dùng trong từng lần gọi

Ví dụ:

```java
static <T> T identity(T value) {
    return value;
}
```

Lời gọi:

```java
String name = identity("An");
Integer count = identity(3);
```

Compiler suy luận T độc lập cho mỗi lời gọi. Method không cần biết hoặc giữ giá trị kiểu T giữa các lần gọi.

Cú pháp tổng quát:

```text
[modifiers] <TypeParameters> ReturnType methodName(parameters)
```

`<T>` nằm **trước kiểu trả về**. Không viết `static T <T> identity(...)`.

### Nhiều type parameters trong một method

```java
static <T, R> R convert(
        T input, Function<? super T, ? extends R> mapper) {
    return mapper.apply(input);
}
```

T liên hệ với kiểu input; R liên hệ với kiểu output. Một lần gọi có thể String→Integer, lần khác Integer→String. Nếu không có cấu hình hay state giữ lâu dài quan hệ T/R, đặt hai biến ở method là tự nhiên.

Java suy luận generic method type arguments từ đối số, target types, lambda/method reference và bounds. Trong trường hợp cần rõ ràng:

```java
List<Integer> lengths =
        Operations.<String, Integer>mapAll(
                List.of("A", "Java"), String::length);
```

Nhưng lời gọi ngắn hơn thường đủ:

```java
List<Integer> lengths =
        Operations.mapAll(List.of("A", "Java"), String::length);
```

`Operations` là utility class trong chương trình phần 8. Explicit type arguments nên dùng khi cần giúp inference hoặc làm rõ ý định; không nên viết mọi nơi nếu chúng chỉ lặp lại điều compiler đã biết.

### Generic method không bắt buộc static

Cả hai đều hợp lệ:

```java
class Worker {
    <T> T apply(T input) {
        return input;
    }

    static <T> T echo(T input) {
        return input;
    }
}
```

Phân loại cấp method nói về vị trí khai báo biến kiểu, không phải từ khóa static. Static có thêm giới hạn riêng với class-level type variables ở phần 6.

## 4. Repository cấp lớp và phép nhóm cấp method

Một thiết kế phổ biến:

```java
final class Repository<E> {
    private final List<E> items = new ArrayList<>();

    void add(E element) {
        items.add(element);
    }

    List<E> snapshot() {
        return List.copyOf(items);
    }

    <K> Map<K, List<E>> groupBy(
            Function<? super E, ? extends K> classifier) {
        return items.stream().collect(Collectors.groupingBy(
                classifier,
                LinkedHashMap::new,
                Collectors.toList()));
    }
}
```

Đoạn cần các imports `List`, `ArrayList`, `Map`, `LinkedHashMap`, `Function`, `Collectors`. Ví dụ đầy đủ ở phần 8.

Giả sử:

```java
Repository<String> names = new Repository<>();
names.add("An");
names.add("Binh");
names.add("Anh");

Map<Integer, List<String>> byLength =
        names.groupBy(String::length);

Map<Character, List<String>> byFirstLetter =
        names.groupBy(text -> text.charAt(0));
```

E=String được giữ xuyên suốt trạng thái repository. Nhưng K được suy luận theo **từng lần nhóm**, có thể Integer hoặc Character. Không nên thêm K vào `Repository<E,K>` nếu repository không có một loại khóa cố định trong cả đời object.

### Vì sao callback có wildcard?

`Function<? super E, ? extends K>` mô tả một mapper:

- Nó **tiêu thụ** E, nên có thể nhận loại cha của E (super).
- Nó **sản xuất** kết quả tương thích K, nên có thể trả một subtype của K (extends).

Đây là nguyên tắc **PECS — Producer Extends, Consumer Super**. Type variable K ở method liên kết kiểu kết quả của mapper với kiểu khóa của `Map<K,List<E>>`.

### Snapshot và mutability là hợp đồng khác

`List.copyOf(items)` tạo list không sửa được về mặt cấu trúc, không chấp nhận phần tử null và không deep-copy các object E mutable. Các tính chất đó không làm thay đổi quyết định E đặt cấp lớp hay K đặt cấp method.

## 5. Class generic vẫn có thể chứa method generic riêng

Một Box với giá trị T cố định có thể hỗ trợ phép map ra loại R bất kỳ:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    <R> R map(Function<? super T, ? extends R> mapper) {
        return mapper.apply(value);
    }
}
```

Lời gọi:

```java
Box<String> title = new Box<>("Java");
Integer length = title.map(String::length);
String upper = title.map(String::toUpperCase);
```

Trong cả hai lời gọi, Box vẫn chứa String. Nhưng R của method lần đầu là Integer, lần sau là String. Nếu R bị đặt lên class (`Box<T,R>`), một caller có thể phải xác định R ngay lúc tạo Box dù chưa biết mình sẽ map thành gì.

Ngược lại, nếu class được tạo để **giữ chính mapper T→R lâu dài**:

```java
final class ConfiguredMapper<T, R> {
    private final Function<? super T, ? extends R> mapper;

    ConfiguredMapper(Function<? super T, ? extends R> mapper) {
        this.mapper = mapper;
    }

    R apply(T value) {
        return mapper.apply(value);
    }
}
```

lúc này class-level T/R hoàn toàn hợp lý. Không có quy tắc “mọi hàm map đều đặt R ở method”; scope do thời gian tồn tại của contract quyết định.

## 6. Static không được dùng T của class như type variable

**Tệp BadStaticScope.java, cố ý không biên dịch:**

```java
class BadStaticScope<T> {
    static T cache;
    static T create() { return null; }
}
```

`javac --release 17` từ chối hai chỗ dùng T:

```text
non-static type variable T cannot be referenced from a static context
```

Static member thuộc về class chứ không thuộc một instance `BadStaticScope<String>` hoặc `BadStaticScope<Integer>` cụ thể. T của instance không thể tự động trở thành một loại cho static field.

### Static generic factory đúng cách

```java
final class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    static <X> Box<X> of(X value) {
        return new Box<>(value);
    }
}
```

Lời gọi:

```java
Box<String> text = Box.of("hello");
Box<Integer> number = Box.of(10);
```

X là **biến kiểu riêng của static method**, được suy luận tại từng lời gọi. Static factory không tham chiếu T của một Box đang tồn tại.

Java cho phép dùng cùng tên T cho type parameter của class và của method static, nhưng chúng là **hai declarations khác nhau**. Chọn tên X trong ví dụ để làm rõ phạm vi.

**Không có generic field với cú pháp `static <T> T cache`**: method/constructor có type parameter khai báo riêng, field không có cơ chế đó.

## 7. Shadowing type parameter

**Tệp BadShadowing.java, cố ý không biên dịch:**

```java
class BadShadowing<T> {
    private T value;

    <T> void replace(T next) {
        value = next;
    }
}
```

Compiler thông báo:

```text
incompatible types: T#1 cannot be converted to T#2
```

T trong `<T> void replace(...)` là một type variable mới và **che** T của class. Hai T được viết giống hệt nhưng là hai khai báo khác nhau.

Nếu mục tiêu là cập nhật field kiểu T của Box, sửa thành:

```java
class GoodBox<T> {
    private T value;

    void replace(T next) {
        value = next;
    }
}
```

Nếu method cần một loại khác thật sự, dùng tên U:

```java
<U> Pair<T, U> pairWith(U extra) {
    return new Pair<>(value, extra);
}
```

Đây là một method của Box<T> trong chương trình đầy đủ phần 8, có field `value` và record `Pair<A,B>`.

T/E/K/V/R/U/X chỉ là tên quy ước. Compiler quan tâm tới **nơi khai báo và các ràng buộc**, không suy đoán rằng hai ký tự T ở các scope khác nhau phải tương đương.

## 8. Chương trình Java 17 đầy đủ đã kiểm thử

Chương trình kết hợp `Box<T>`, `Repository<E>`, utility methods với T/R riêng, constructor generic với U riêng và static generic factory.

**Tệp GenericScopeDemo.java:**

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class GenericScopeDemo {
    record Pair<A, B>(A first, B second) {}

    static final class Box<T> {
        private T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
        void set(T next) { value = next; }

        <R> R map(Function<? super T, ? extends R> mapper) {
            return mapper.apply(value);
        }

        <U> Pair<T, U> pairWith(U extra) {
            return new Pair<>(value, extra);
        }

        static <X> Box<X> of(X value) {
            return new Box<>(value);
        }
    }

    static final class Repository<E> {
        private final List<E> items = new ArrayList<>();
        void add(E element) { items.add(element); }
        List<E> snapshot() { return List.copyOf(items); }

        <K> Map<K, List<E>> groupBy(
                Function<? super E, ? extends K> classifier) {
            return items.stream().collect(Collectors.groupingBy(
                    classifier, LinkedHashMap::new, Collectors.toList()));
        }
    }

    static final class Operations {
        private Operations() {}

        static <T> T choose(T a, T b, BinaryOperator<T> chooser) {
            return chooser.apply(a, b);
        }

        static <T, R> List<R> mapAll(
                List<? extends T> source,
                Function<? super T, ? extends R> mapper) {
            List<R> result = new ArrayList<>();
            for (T item : source) {
                result.add(mapper.apply(item));
            }
            return result;
        }

        static <T> void append(
                List<? extends T> source, List<? super T> destination) {
            destination.addAll(source);
        }

        static void printSize(List<?> items) {
            System.out.println("size=" + items.size());
        }
    }

    static final class Envelope<T> {
        final T payload;
        final String audit;

        <U> Envelope(T payload, U auditData) {
            this.payload = payload;
            this.audit = String.valueOf(auditData);
        }
    }

    public static void main(String[] args) {
        Box<String> title = Box.of("Java");
        System.out.println("box=" + title.get());
        title.set("Generics");
        System.out.println("updated=" + title.get());
        System.out.println("mapped=" + title.map(String::length));
        System.out.println("pair=" + title.pairWith(2026));

        Box<Integer> count = Box.of(7);
        System.out.println("otherBox=" + count.get());

        Repository<String> names = new Repository<>();
        names.add("An");
        names.add("Binh");
        names.add("Anh");
        System.out.println("repo=" + names.snapshot());
        System.out.println("groups=" + names.groupBy(String::length));

        int chosen = Operations.choose(4, 9, Integer::max);
        System.out.println("chosen=" + chosen);
        System.out.println("lengths="
                + Operations.mapAll(List.of("A", "Java"), String::length));

        List<Number> destination = new ArrayList<>(List.of(1.5));
        Operations.append(List.of(2, 3), destination);
        System.out.println("append=" + destination);
        Operations.printSize(names.snapshot());

        Envelope<String> e = new Envelope<>("payload", 1001L);
        System.out.println("envelope=" + e.payload + "/" + e.audit);
        System.out.println("classGenericAndMethodGeneric="
                + title.<Integer>map(String::length));
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:all GenericScopeDemo.java
java GenericScopeDemo
```

**Stdout đúng đã kiểm chứng:**

```text
box=Java
updated=Generics
mapped=8
pair=Pair[first=Generics, second=2026]
otherBox=7
repo=[An, Binh, Anh]
groups={2=[An], 4=[Binh], 3=[Anh]}
chosen=9
lengths=[1, 4]
append=[1.5, 2, 3]
size=3
envelope=payload/1001
classGenericAndMethodGeneric=8
```

`javac --release 17 -Xlint:all` không phát warning cho chương trình thử. `LinkedHashMap` trong `groupBy` giúp khóa được in theo thứ tự gặp trong dữ liệu: 2, 4, 3.

### T của Box và R của map là hai phạm vi

`title` luôn là `Box<String>`: `set/get` dùng String. `map(String::length)` lại trả Integer. Lần gọi khác `map(String::toUpperCase)` trả String. R được suy luận độc lập, Box không biến thành `Box<String,Integer>`.

### U của pairWith không đổi T của Box

`pairWith(2026)` trả `Pair<String,Integer>`. String gắn với Box; Integer gắn với method. Record in ra `Pair[first=Generics, second=2026]`.

### E của Repository và K của groupBy

E=String áp dụng cho repository và snapshot. K=Integer chỉ áp dụng cho một lời gọi nhóm theo độ dài String.

### Utility class không có generic state

`Operations.choose`, `mapAll`, `append` dùng những biến T/R khác nhau ở từng method. Không cần `Operations<T,R>` và không phải tạo object để dùng những thuật toán này.

## 9. Constructor generic cũng có scope riêng

`Envelope<T>` của phần 8 có constructor:

```java
<U> Envelope(T payload, U auditData) {
    this.payload = payload;
    this.audit = String.valueOf(auditData);
}
```

T thuộc class và được giữ trong field payload. U chỉ thuộc một lần khởi tạo; constructor nhận auditData kiểu U rồi chuyển sang String. Caller viết:

```java
Envelope<String> e = new Envelope<>("payload", 1001L);
```

T được xác định là String, U tương thích Long. Object vẫn là `Envelope<String>` chứ không phải `Envelope<String,Long>`.

Dấu diamond `<>` tại `new Envelope<>(...)` giúp suy luận **class type arguments**. Constructor type parameter U được suy luận theo chữ ký constructor, độc lập với T.

Generic constructor hữu ích nếu một input tạm thời có quan hệ kiểu cần diễn đạt lúc khởi tạo. Nếu U chỉ xuất hiện một lần và hoàn toàn không cần quan hệ với vị trí khác, một input Object đôi khi cũng có thể đủ; không cần generic chỉ để làm code có nhiều dấu ngoặc nhọn.

## 10. Bounded type parameters ở cả class lẫn method

Bound cấp lớp:

```java
class NumericBox<N extends Number> {
    private final N value;

    NumericBox(N value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

Nếu toàn bộ instance luôn giữ một subtype Number, bound cấp lớp hợp lý.

Bound cấp method:

```java
static <N extends Number> double square(N value) {
    double x = value.doubleValue();
    return x * x;
}
```

Method chỉ xử lý một giá trị Number, không giữ trạng thái N.

Nhiều bounds:

```java
static <T extends Number & Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Nếu có class bound, nó đứng trước các interface bounds; ví dụ Number trước Comparable. **Bound và scope là hai quyết định độc lập**: bound quyết định khả năng của type, scope quyết định nơi quan hệ type phải tồn tại.

## 11. Khi không cần đặt tên T, dùng wildcard

Một method chỉ lấy size:

```java
static <T> int size(List<T> values) {
    return values.size();
}
```

có thể được diễn đạt ngắn hơn:

```java
static int size(List<?> values) {
    return values.size();
}
```

Đây là hai lựa chọn thay thế, **không đặt đồng thời cùng tên trong một class** do cùng erasure.

`List<?>` cho biết kiểu phần tử không quan trọng. Khi type variable không liên kết đầu ra, callback hoặc tham số khác, wildcard có thể rõ nghĩa hơn.

Ngược lại, một method copy cần ràng buộc giữa nguồn và đích:

```java
static <T> void append(
        List<? extends T> source,
        List<? super T> destination) {
    destination.addAll(source);
}
```

T liên kết producer với consumer. `List<Integer>` có thể truyền làm source, `List<Number>` làm destination. Hai `List<?>` độc lập không bảo đảm có chung element type, nên không thể thay chữ ký này mà vẫn hỗ trợ `addAll` an toàn.

Một phép đọc thuần túy từ subtype Number có thể nhận:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

Không cần `<T extends Number>` nếu T không thêm quan hệ hữu ích. Nhưng “T chỉ xuất hiện một lần thì luôn bỏ T” không phải luật tuyệt đối; inference, overload, compatibility và các body implementation vẫn có thể ảnh hưởng lựa chọn.

## 12. Mẫu thiết kế sai: generic return không có bằng chứng

Một phương thức:

```java
// Anti-pattern: không tự chứng minh an toàn kiểu.
@SuppressWarnings("unchecked")
static <T> T pretend(Object value) {
    return (T) value;
}
```

cho phép caller yêu cầu String từ một Integer. `<T>` không làm phép cast trở nên an toàn; `ClassCastException` có thể xuất hiện khi kết quả được dùng dưới dạng String.

Nếu cần kiểm tra class runtime thực:

```java
static <T> T checked(Class<T> token, Object value) {
    return token.cast(value);
}
```

Class token cung cấp loại runtime để kiểm tra. Tuy nhiên `Class<T>` không tự biểu diễn `List<String>` vì type arguments của List không reifiable; dữ liệu generic lồng nhau cần validation riêng.

Một generic method an toàn cần thể hiện **quan hệ giữa type parameter và dữ liệu/callback có thể kiểm chứng**, không chỉ có ký hiệu T trong return type.

## 13. Overload và type erasure

**Tệp BadErasureOverloads.java, cố ý không biên dịch:**

```java
import java.util.List;

class BadErasureOverloads {
    void store(List<String> list) {}
    void store(List<Integer> list) {}
}
```

Hai chữ ký cùng bị erasure thành `store(List)`, nên `javac` báo `name clash ... have the same erasure`.

Nếu hai method cùng làm một thuật toán, hãy cân nhắc gộp thành một `<T> void store(List<T>)`. Nếu chúng làm hai nghiệp vụ riêng, đặt tên phản ánh nghiệp vụ. Không nên thêm một tham số giả hoặc cast raw chỉ để tránh compiler mà làm API khó hiểu.

## 14. Type inference không có nghĩa cùng runtime class

Một method:

```java
static <T> void combine(T a, T b) {
    System.out.println(a + " / " + b);
}
```

không bắt buộc hai object có cùng `getClass()`. Compiler có thể chọn T là một **common supertype** hợp lệ cho hai đối số khác runtime class, tùy ngữ cảnh.

Vì vậy T cùng tên diễn đạt quan hệ assignability ở compile time, **không phải phép kiểm tra runtime rằng a và b cùng exact class**. Khi nghiệp vụ có yêu cầu nghiêm ngặt hơn, hãy sử dụng loại domain cụ thể, class token hoặc validation độc lập.

## 15. Đổi scope generic có thể phá API public

So sánh:

```java
interface Store<E> {
    void add(E value);
    E get(int index);
}
```

với:

```java
interface Store {
    <E> void add(E value);
    <E> E get(int index);
}
```

Phiên bản đầu có E thống nhất cho cùng một Store typed. Ở bản sau, E của add và E của get được suy luận độc lập và không còn bằng chứng rằng các giá trị liên hệ với nhau. Caller dùng `Store<String>` cũng không thể tiếp tục khai báo như cũ.

Chuyển type parameter từ class xuống method (hoặc ngược lại) có thể ảnh hưởng source compatibility, overload resolution, override, reflection signatures và trong một số thay đổi còn ảnh hưởng binary compatibility. **Không mặc định đó là refactor chỉ sửa cú pháp.**

Một utility class mang quá nhiều type parameters khiến caller phải viết các type arguments không liên quan tới trạng thái có thể được đơn giản hóa bằng method-level generics, nhưng phải kiểm tra caller và hợp đồng public trước khi sửa.

## 16. Bảng quyết định nhanh

| Nhu cầu | Đặt type parameter ở đâu? | Lý do |
| --- | --- | --- |
| Box giữ T, set/get T | `Box<T>` | State và nhiều method cần T thống nhất. |
| Repository chỉ chứa E | `Repository<E>` | E là invariant của instance. |
| Repository nhóm theo khóa K tùy callback | `Repository<E>` + `<K> groupBy` | K chỉ thuộc một lời gọi. |
| Cache key/value typed | `Cache<K,V>` | Hai type thuộc trạng thái dài hạn. |
| Convert T→R một lần | `static <T,R> R convert(...)` | Không có state generic. |
| Mapper được cấu hình, tái sử dụng | `ConfiguredMapper<T,R>` | Hàm mapping được giữ trong object. |
| Tính size List bất kỳ | `int size(List<?>)` | Không cần đặt tên type. |
| Copy source vào destination | `static <T> append(List<? extends T>,List<? super T>)` | T liên kết hai vị trí. |
| Factory tạo Box<X> bất kỳ | `static <X> Box<X> of(X)` | Static có X độc lập. |
| Constructor có audit U dùng một lần | `Envelope<T>`, constructor `<U>` | T thuộc class, U thuộc construction. |

## 17. Checklist review API

1. T đang liên kết những field, tham số và kết quả nào?
2. Có cần cùng T xuyên suốt nhiều lần gọi trên một receiver không?
3. Caller có cần xác định T khi tạo instance không?
4. Kết quả một phép map có thể đổi loại ở mỗi lời gọi không? Nếu có, R nên ở method.
5. Static method có đang cố dùng T cấp lớp không?
6. Một method có khai báo lại `<T>` và che T cấp lớp không?
7. Có thể thay generic variable không cần thiết bằng `?` không?
8. Cần PECS để cho phép đọc subtype hoặc ghi vào supertype không?
9. Generic return có chứng minh được liên hệ giữa kiểu và dữ liệu thực không?
10. Có overload generic nào sau erasure bị trùng chữ ký không?
11. Các type arguments có được suy luận thoải mái mà không cần cast quá mức không?
12. Khi thay scope, có làm đổi public contract, overrides hoặc cách khai báo của caller không?
13. Đã thử các trường hợp String/Integer và kết hợp kiểu khác nhau trong một chương trình biên dịch thật chưa?

## 18. Bài tập và đáp án

**1.** Box có field value, getter và setter. Chọn generic class hay generic method?

**Đáp án:** `Box<T>` vì T là invariant của trạng thái và tất cả thao tác.

**2.** Một method đảo `Pair<A,B>` nhưng không giữ state?

**Đáp án:** Có thể là `static <A,B> Pair<B,A> reverse(Pair<A,B>)`, vì A/B liên hệ trong một lần gọi.

**3.** Vì sao K ở `Repository<E>.<K>groupBy` không phải cấp lớp?

**Đáp án:** Một repository chứa E cố định nhưng có thể nhóm bằng các loại khóa khác nhau ở những calls độc lập.

**4.** `class Box<T> { T x; <T> void set(T v) { x=v; } }` lỗi tại đâu?

**Đáp án:** Method khai báo lại T, che T class. Xóa `<T>` ở method.

**5.** Static factory có thể dùng T của class không?

**Đáp án:** Không trực tiếp; khai báo `static <X> Box<X> of(X)` với X riêng.

**6.** Khi nào dùng `List<?>` thay `<T> List<T>`?

**Đáp án:** Khi loại phần tử không cần liên kết với output/các tham số khác, chẳng hạn chỉ đọc size.

**7.** Vì sao copy List Integer vào List Number cần một T?

**Đáp án:** T liên hệ kiểu phần tử producer với kiểu destination có thể nhận, thường thông qua `? extends T` và `? super T`.

**8.** Generic constructor `<U> Envelope(T,U)` có khiến object mang hai type arguments?

**Đáp án:** Không; object vẫn có class type `Envelope<T>`. U chỉ trong constructor.

**9.** Cùng một T trong `combine(T,T)` có buộc runtime class giống nhau không?

**Đáp án:** Không; compiler có thể chọn một common supertype hợp lệ.

**10.** Khi nào `ConfiguredMapper<T,R>` tốt hơn method `<T,R> convert(...)`?

**Đáp án:** Khi object thật sự giữ mapper T→R để tái sử dụng qua nhiều lần gọi.

**11.** Có nên dùng `<T> T pretend(Object)` để cast dữ liệu không biết kiểu?

**Đáp án:** Không; không có quan hệ an toàn. Dùng Class token hoặc validator tương ứng với contract runtime.

**12.** Có thể chuyển `Store<E>` thành interface không generic với method `<E>` mà không đổi hợp đồng không?

**Đáp án:** Không. Quan hệ kiểu giữa các lần add/get bị mất, và kiểu khai báo caller có thể không còn hợp lệ.

## 19. Tổng kết

- **Cấp lớp/interface:** chọn khi T là một phần hợp đồng của object, gắn với nhiều method hoặc trạng thái lâu dài.
- **Cấp method:** chọn khi T/R/K chỉ diễn đạt quan hệ của một lần gọi; có thể suy luận lại ở những lần gọi sau.
- **Kết hợp cả hai:** `Box<T>` với `<R> map`, `Repository<E>` với `<K> groupBy`.
- **Constructor generic:** có thể nhận type U tạm thời nhưng không làm class có thêm type parameter.
- **Static context:** không dùng trực tiếp class T; static generic factory tự khai báo biến kiểu riêng.
- **Wildcard:** dùng khi không cần đặt tên type parameter chỉ để đọc hoặc quan sát dữ liệu.
- **Tránh các bẫy:** shadowing, unchecked cast, method generic không có invariant, overload trùng erasure và refactor phá public contract.

**Quy tắc cuối:** Đặt type parameter ở phạm vi nhỏ nhất nhưng vẫn bảo toàn đầy đủ invariant và quan hệ kiểu mà API đã hứa với caller.
