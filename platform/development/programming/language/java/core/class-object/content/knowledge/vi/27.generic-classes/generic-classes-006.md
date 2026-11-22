# Phương thức generic và tham số kiểu riêng trong Java 17+

## 1. Vấn đề: kiểu của phương thức không nhất thiết là kiểu của lớp

Một **lớp generic** khai báo tham số kiểu trong phần khai báo lớp:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Ở đây, `T` thuộc **phạm vi kiểu Box**: khi viết `Box<String>`, phương thức `get()` trả String; với `Box<Integer>`, nó trả Integer. Tuy nhiên, đôi khi một phương thức cần xử lý **một kiểu riêng, độc lập với T** của lớp. Ví dụ một Box<String> có thể nhận một Integer, Boolean hoặc object khác để tạo ra một chuỗi mô tả. Khi đó, phương thức có thể khai báo **tham số kiểu của chính nó**, thường đặt tên `U` hoặc `R`.

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    <U> String describeWith(U extra) {
        return value + ":" + extra;
    }
}
~~~

Đây là khai báo lớp hoàn chỉnh hợp lệ. `<U>` đứng **trước kiểu trả về** `String`, chứng tỏ `describeWith` là một **generic method**. `T` vẫn thuộc lớp; `U` chỉ thuộc khai báo phương thức ấy. Khi gọi `new Box<>("java").describeWith(17)`, compiler suy luận `U` là Integer, trong khi `T` của Box vẫn là String.

**Điểm cốt lõi:** một phương thức generic không cần nằm trong một lớp generic. Và một phương thức được khai báo trong lớp generic cũng **không tự nhiên trở thành generic method** nếu nó không có danh sách tham số kiểu riêng.

Bài thuộc **Java core – class-object**, nhóm **Lớp generic**, mục **Phương thức generic và tham số kiểu riêng**. Mọi chương trình độc lập bên dưới dành cho **Java 17+**, không bật preview, có tên tệp, lệnh biên dịch/chạy và stdout xác định. Snippet minh họa hoặc đoạn cố ý không biên dịch sẽ được nói rõ.

## 2. Ba cấp độ cần phân biệt

| Cấp độ | Ví dụ | Ai sở hữu tham số kiểu? |
| --- | --- | --- |
| Lớp generic | `class Box<T> { ... }` | `T` của lớp Box |
| Phương thức dùng T của lớp | `T get() { ... }` | Vẫn là `T` của lớp, **không khai báo T mới** |
| Phương thức generic | `<U> U echo(U value) { ... }` | `U` riêng của phương thức |
| Phương thức static generic | `static <X> X identity(X x) { ... }` | `X` riêng của static method |
| Phương thức với nhiều tham số kiểu | `<A,B> Pair<A,B> pair(A a,B b)` | `A` và `B` riêng của method |

Một method như `String toString()` trong `Box<T>` là method bình thường; `T get()` có thể phụ thuộc vào T nhưng **không phải một generic method theo thuật ngữ JLS**, vì nó không khai báo method type parameters.

Lý do phân biệt: `T` của `Box<T>` được quyết định khi nhìn kiểu của receiver `Box<String>`; còn `U` của `<U> U echo(U x)` được xác định **riêng theo từng lần invocation**, dựa trên arguments, target type và các ràng buộc của compiler.

## 3. Cú pháp chuẩn của generic method

Dạng khai báo:

~~~java
[modifiers] <TypeParameters> ReturnType methodName(parameters) {
    // thân phương thức
}
~~~

Dòng trên là **mẫu cú pháp mô tả**, không phải Java source dùng trực tiếp để biên dịch: dấu ngoặc vuông và placeholders chỉ biểu thị các thành phần.

Một khai báo cụ thể:

~~~java
public static <T> T identity(T value) {
    return value;
}
~~~

Đây là một **method hợp lệ nếu đặt trong class**. Lưu ý thứ tự: modifier `public static`, sau đó `<T>`, rồi đến kiểu trả về `T` và tên `identity`.

- `<T>` **khai báo** một type parameter tên T.
- `T` đầu tiên sau `<T>` là **kiểu trả về**.
- `T value` là tham số giá trị thông thường có kiểu T.
- `return value;` hợp lệ vì value có kiểu T.

So sánh với:

~~~java
public static T identity(T value) {
    return value;
}
~~~

Đoạn thứ hai **cố ý không biên dịch** nếu được đặt trong một class không khai báo T thích hợp: T không được khai báo. Nếu đặt trong `class C<T>`, static method vẫn **không được** dùng class-level T trong static context. Phải khai báo `static <T>` hoặc tham số kiểu khác cho chính static method.

## 4. Chương trình hoàn chỉnh 1 — generic method trong lớp không generic

Tệp **`GenericIdentityDemo.java`**:

~~~java
public class GenericIdentityDemo {
    static <T> T identity(T input) {
        return input;
    }

    public static void main(String[] args) {
        String name = identity("An");
        Integer number = identity(42);
        Boolean flag = identity(true);

        System.out.println("name=" + name);
        System.out.println("number=" + number);
        System.out.println("flag=" + flag);
        System.out.println("name length=" + name.length());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericIdentityDemo.java
java GenericIdentityDemo
~~~

**Stdout:**

~~~text
name=An
number=42
flag=true
name length=2
~~~

Không có `class GenericIdentityDemo<T>`: chỉ method `identity` sở hữu T. Compiler suy luận T lần lượt là String, Integer và Boolean. Việc truyền `42` và `true` dùng **autoboxing** từ primitive sang wrapper types tương ứng; generic type arguments không được là primitive như `int` hay `boolean`.

`identity` không tự chuyển một object thành kiểu bất kỳ theo ý người gọi. Nó trả chính value đã nhận theo quan hệ type mà compiler suy luận được; việc gán vào biến có kiểu cụ thể vẫn phải hợp lệ tại compile time.

## 5. Phạm vi tham số kiểu của phương thức

Một method type parameter có phạm vi trong **khai báo phương thức tương ứng**: nó có thể được dùng làm kiểu trả về, kiểu parameters, generic bounds/throws clause theo quy tắc Java và trong body của method.

~~~java
class TextService {
    <U> U echo(U input) {
        return input;
    }

    String upper(String input) {
        return input.toUpperCase();
    }
}
~~~

Đây là class hợp lệ. `U` của `echo` **không xuất hiện** trong `upper`. Mỗi method có thể chọn một tập type parameters của riêng mình.

**Đoạn cố ý không biên dịch** nếu thêm vào TextService:

~~~java
// U invalid(U value) {
//     return value;
// }
~~~

Không có U đang nằm trong scope của `invalid`. Đừng nhầm một kiểu generic đã được khai ở method A với một type name có thể dùng mọi nơi trong class.

Nếu các methods cần dùng **cùng một type được quyết định bởi instance**, cân nhắc khai type parameter ở **class**. Nếu mỗi lần gọi method cần một type độc lập, khai ở **method**.

## 6. Chương trình hoàn chỉnh 2 — class type `T` và method type `U`

Tệp **`BoxAndMethodTypeDemo.java`**:

~~~java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    <U> String combine(U extra) {
        return value + " / " + extra;
    }

    <U> U echoExtra(U extra) {
        return extra;
    }
}

public class BoxAndMethodTypeDemo {
    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");

        System.out.println("value=" + box.get());
        System.out.println("number=" + box.combine(17));
        System.out.println("boolean=" + box.combine(true));

        Integer extra = box.echoExtra(25);
        System.out.println("extra=" + extra);
        System.out.println("value again=" + box.get());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 BoxAndMethodTypeDemo.java
java BoxAndMethodTypeDemo
~~~

**Stdout:**

~~~text
value=Java
number=Java / 17
boolean=Java / true
extra=25
value again=Java
~~~

`Box<String>` quyết định class-level `T=String`. Hai lần gọi `combine` dùng `U=Integer` rồi `U=Boolean`; không lần nào thay đổi T. `echoExtra` có thể trả U, độc lập với giá trị String đã lưu trong Box.

Method `T get()` **dùng T của lớp**, dù không có tiền tố `<T>`. Đây là khác biệt quan trọng khi đọc generic APIs.

## 7. Khi `T` của lớp và tham số kiểu của method gặp nhau

Một generic class thường cần một method vừa sử dụng **state kiểu T**, vừa nhận **một kiểu U từ caller**.

~~~java
final class Store<T> {
    private final T item;

    Store(T item) {
        this.item = item;
    }

    <U> String describe(U note) {
        return "item=" + item + ", note=" + note;
    }
}
~~~

Đây là class hợp lệ. `describe` sử dụng T thông qua `item` và dùng U qua `note`.

**Ví dụ thiết kế:** một repository lưu `Entity` có thể có method nhận `<R> R map(Function<? super Entity,? extends R>)`: Entity là data type do repository instance quản lý; R là output type riêng của **mỗi phép biến đổi**. Hai cấp tham số kiểu tồn tại vì chúng giải quyết hai vấn đề độc lập.

Nếu bạn đặt cả T và R ở class chỉ vì một method trả về R, mọi caller có thể phải mang theo R một cách không cần thiết trên toàn bộ kiểu class. Hãy đặt type parameter ở **phạm vi hẹp nhất có ý nghĩa**.

## 8. Chương trình hoàn chỉnh 3 — mapping từ `T` của lớp sang `R` của method

Tệp **`GenericMapMethodDemo.java`**:

~~~java
import java.util.function.Function;

final class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    <R> R map(Function<? super T, ? extends R> mapper) {
        return mapper.apply(value);
    }
}

public class GenericMapMethodDemo {
    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("hello");

        Integer length = holder.map(String::length);
        String upper = holder.map(String::toUpperCase);
        Boolean longText = holder.map(s -> s.length() > 3);

        System.out.println("length=" + length);
        System.out.println("upper=" + upper);
        System.out.println("long=" + longText);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericMapMethodDemo.java
java GenericMapMethodDemo
~~~

**Stdout:**

~~~text
length=5
upper=HELLO
long=true
~~~

`Holder<String>` giữ T là String; mỗi `map` có R khác nhau: Integer, String, Boolean. `Function<? super T, ? extends R>` thể hiện quan hệ variance hữu ích: mapper **tiêu thụ một T** và **sinh một R**.

`map` chỉ *trả* một giá trị R, không chuyển Holder<String> thành Holder<R>. Đó là lý do R thuộc method, không phải toàn class.

## 9. Phương thức `static` không dùng được tham số kiểu của instance

Xét:

~~~java
class Container<T> {
    private final T item;

    Container(T item) {
        this.item = item;
    }
}
~~~

Trong một class generic, type parameter `T` thuộc **instance-level generic type context**; các static members không thể trực tiếp phụ thuộc vào `T` của một instance cụ thể.

**Cố ý không biên dịch** nếu viết trong Container:

~~~java
// static T invalid(T value) {
//     return value;
// }
~~~

Sửa bằng một method tự khai báo type parameter:

~~~java
static <U> Container<U> of(U item) {
    return new Container<>(item);
}
~~~

Đây là **snippet method** hợp lệ khi đặt trong Container. `U` thuộc static method, và compiler có thể suy luận U ở mỗi call site.

Không có mâu thuẫn: `Container<String>` và `Container<Integer>` có thể dùng cùng một static generic factory vì type U được chọn khi gọi method, không được “đọc” từ một class-level T bị static member dùng sai ngữ cảnh.

## 10. Chương trình hoàn chỉnh 4 — static generic factory method

Tệp **`StaticGenericFactoryDemo.java`**:

~~~java
final class Container<T> {
    private final T item;

    private Container(T item) {
        this.item = item;
    }

    static <U> Container<U> of(U value) {
        return new Container<>(value);
    }

    T get() {
        return item;
    }
}

public class StaticGenericFactoryDemo {
    public static void main(String[] args) {
        Container<String> title = Container.of("Java");
        Container<Integer> count = Container.of(3);

        System.out.println("title=" + title.get());
        System.out.println("count=" + count.get());
        System.out.println("same raw class="
                + (title.getClass() == count.getClass()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StaticGenericFactoryDemo.java
java StaticGenericFactoryDemo
~~~

**Stdout:**

~~~text
title=Java
count=3
same raw class=true
~~~

Factory `of` khai U riêng. Kiểu `Container<U>` trong return type phù hợp với đối số đã nhận. Vì **type erasure**, `Container<String>` và `Container<Integer>` không tạo hai runtime classes độc lập; phép `getClass()==` trả true.

Nội dung `same raw class` không nói hai Container objects là một: chỉ nói cùng runtime class sau erasure.

## 11. Suy luận kiểu khi gọi generic method

Với:

~~~java
static <T> T choose(T first, T second) {
    return first;
}
~~~

được đặt trong một class, compiler cần quyết định **T là gì cho invocation cụ thể**. Nó dùng constraints từ arguments và đôi khi **target type** (kiểu của biến gán, parameter đích hoặc return context).

~~~java
String first = choose("A", "B");
Number second = choose(10, 2.5);
~~~

Đây là snippet hợp lệ khi method ở scope phù hợp. Với hai Strings, T có thể là String; với Integer và Double, một kiểu chung phù hợp như Number/những superinterfaces có thể tham gia suy luận. Tránh dựa vào suy luận phức tạp như thể nó “chọn một class cha duy nhất” theo ý người đọc; compiler áp dụng các quy tắc inference của JLS.

**Không suy từ tên T rằng chỉ một T tồn tại cho toàn bộ chương trình.** Type variable T trong declaration là một ký hiệu, được **thế theo ràng buộc** riêng cho mỗi invocation.

Nếu inference khó đọc, bạn có thể khai local variable với type rõ hoặc cung cấp type arguments tường minh.

## 12. Type witness: truyền type arguments tường minh

Thông thường gọi:

~~~java
String text = GenericIdentityDemo.identity("A");
~~~

Là một statement hợp lệ nếu dùng class GenericIdentityDemo ở chương trình trước. Compiler suy luận T = String.

Bạn cũng có thể dùng **explicit type witness**:

~~~java
String text = GenericIdentityDemo.<String>identity("A");
~~~

`<String>` đứng **sau dấu chấm trước tên method**, không phải sau method name và không phải tham số runtime.

Với static method trong cùng class, có thể gọi dạng `ClassName.<Type>method(args)`; với instance method, `receiver.<Type>method(args)` cũng hợp lệ. Đừng nhầm với khai báo method `<T> T identity(...)`: khai báo đặt trước return type, còn invocation có type witness ở vị trí sau qualifier.

Type witness hữu ích khi compiler không suy được kiểu mong muốn hoặc để biểu diễn intent; **không dùng nó chỉ vì quen viết generic types trong dấu `<>`**, nếu inference đã rõ.

## 13. Chương trình hoàn chỉnh 5 — suy luận và type witness

Tệp **`GenericTypeInferenceDemo.java`**:

~~~java
public class GenericTypeInferenceDemo {
    static <T> T first(T a, T b) {
        return a;
    }

    static <T> T defaultValue(T fallback) {
        return fallback;
    }

    public static void main(String[] args) {
        String inferred = first("An", "Binh");
        String explicit =
                GenericTypeInferenceDemo.<String>first("A", "B");
        Number number =
                GenericTypeInferenceDemo.<Number>first(7, 2.5);

        System.out.println("inferred=" + inferred);
        System.out.println("explicit=" + explicit);
        System.out.println("number=" + number);

        String defaultName =
                GenericTypeInferenceDemo.<String>
                        defaultValue("guest");
        System.out.println("default=" + defaultName);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericTypeInferenceDemo.java
java GenericTypeInferenceDemo
~~~

**Stdout:**

~~~text
inferred=An
explicit=A
number=7
default=guest
~~~

`<Number>` chỉ định T là Number và cho phép các Integer/Double objects truyền vào nhờ quan hệ subtype. Method `first` trả tham số thứ nhất; `System.out.println` in số Integer 7 bằng ký tự `7`.

Gọi tường minh giúp đọc ý định nhưng **không tạo phép cast runtime tùy tiện**. Nếu viết `<String>first(7,8)`, compiler sẽ không chấp nhận Integer arguments làm String.

## 14. Một generic method có nhiều type parameters

Khi input và output không nhất thiết cùng kiểu, method có thể khai `<A, B>`, `<K, V>`, `<T, R>`:

~~~java
static <A, B> Entry<A, B> entry(A first, B second) {
    return new Entry<>(first, second);
}
~~~

Đoạn này là snippet method, giả sử có `record Entry<A,B>(A first,B second) {}` cùng phạm vi.

`A` và `B` là **hai type variables riêng**. Một lời gọi `entry("id", 10)` có thể có kiểu `Entry<String,Integer>`. Điều này khác method `<T> Pair<T,T>` vốn ràng buộc cả hai trường về cùng một type variable, dù compiler có thể suy luận một supertype chung cho arguments khác kiểu.

Tuy nhiên không phải cứ thấy hai parameters trong method là phải dùng hai type variables. Nếu chúng thực sự phải cùng kiểu domain, dùng một `T` để diễn đạt ràng buộc.

## 15. Chương trình hoàn chỉnh 6 — generic method trả record có hai tham số kiểu

Tệp **`TwoMethodTypesDemo.java`**:

~~~java
record Entry<A, B>(A key, B value) {
}

public class TwoMethodTypesDemo {
    static <K, V> Entry<K, V> pair(K key, V value) {
        return new Entry<>(key, value);
    }

    public static void main(String[] args) {
        Entry<String, Integer> score = pair("An", 90);
        Entry<Integer, Boolean> flag = pair(1, true);

        System.out.println("score=" + score);
        System.out.println("flag=" + flag);
        System.out.println("key uppercase="
                + score.key().toUpperCase());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TwoMethodTypesDemo.java
java TwoMethodTypesDemo
~~~

**Stdout:**

~~~text
score=Entry[key=An, value=90]
flag=Entry[key=1, value=true]
key uppercase=AN
~~~

Type inference quyết định K/V cho từng lần gọi. Record type và method type parameters là **hai cấp khai báo độc lập**: record Entry<A,B> định nghĩa cấu trúc container; method pair<K,V> định nghĩa generic factory có thể tạo các instantiations khác nhau.

## 16. Đặt tên type parameters sao cho dễ hiểu

Theo quy ước Java phổ biến:

| Tên | Ý nghĩa thường gặp |
| --- | --- |
| `T` | Type chung |
| `E` | Element |
| `K` | Key |
| `V` | Value |
| `R` | Result/return |
| `U` | Type bổ sung, độc lập với T |
| `N` | Number subtype |
| `S` | Source |

Tên một chữ phù hợp cho generic algorithms ngắn. Với API phức tạp, đôi khi một cái tên dài hơn vẫn hợp lệ và đọc dễ hơn, nhưng tránh đặt tên gây nhầm như dùng `T` vừa là class parameter vừa là method parameter.

**Không có phép ràng buộc thần kỳ dựa trên tên.** `<N>` tự nó **không có nghĩa N extends Number**. Muốn giới hạn phải khai `<N extends Number>`.

## 17. Bounded generic methods: `<T extends SomeType>`

Phương thức generic không có bound tường minh về cơ bản có upper bound `Object`. Nếu cần gọi API của Number hoặc Comparable, khai một **upper bound**.

~~~java
static <N extends Number> double doubleValue(N number) {
    return number.doubleValue();
}
~~~

Snippet method trên hợp lệ trong class. Nó chấp nhận Integer, Long, Double, BigDecimal và các subclasses phù hợp của Number; không chấp nhận String như một argument hợp lệ.

Bên trong method, compiler biết N **là subtype của Number**, nên cho phép `number.doubleValue()`.

**Những điều bound không làm:** `<N extends Number>` không cho phép cộng `N + N` như primitive arithmetic tổng quát; không buộc mọi Number subtype được diễn đạt chính xác bằng double mà không mất precision. `doubleValue()` chỉ là một cách chuyển đổi có thể mất thông tin đối với các số lớn/BigDecimal.

Vì Java generics không nhận primitive type arguments, `<Integer>` là dạng wrapper khi truyền `int`.

## 18. Chương trình hoàn chỉnh 7 — method có bound Number

Tệp **`BoundedGenericNumberDemo.java`**:

~~~java
public class BoundedGenericNumberDemo {
    static <N extends Number> double twice(N number) {
        return number.doubleValue() * 2;
    }

    static <N extends Number> String typeAndValue(N number) {
        return number.getClass().getSimpleName()
                + ":" + number.doubleValue();
    }

    public static void main(String[] args) {
        System.out.println("int twice=" + twice(4));
        System.out.println("double twice=" + twice(1.5));
        System.out.println("long=" + typeAndValue(7L));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BoundedGenericNumberDemo.java
java BoundedGenericNumberDemo
~~~

**Stdout:**

~~~text
int twice=8.0
double twice=3.0
long=Long:7.0
~~~

`twice(4)` nhận Integer nhờ boxing, `twice(1.5)` nhận Double. Cả hai phù hợp `N extends Number`. Đây là một ví dụ về generic algorithm dùng Number API, không phải cách thực hiện số học chính xác cho mọi numeric domain.

## 19. Một method có nhiều upper bounds

Java cho phép intersection bounds:

~~~java
static <T extends Number & Comparable<T>> boolean atLeast(
        T value, T minimum) {
    return value.compareTo(minimum) >= 0;
}
~~~

Method snippet này hợp lệ trong class. `Number` là **class bound** đứng đầu; `Comparable<T>` là interface bound phía sau. Type argument phải đáp ứng **cả hai**.

Quy tắc chung:
- Một class bound (nếu có) phải đứng trước interface bounds.
- Có thể dùng nhiều interface bounds ngăn bằng `&`.
- Không thể liệt kê hai class bounds độc lập vì Java không có multiple class inheritance.
- Bound quyết định operations được phép gọi trong method; nó không biến T thành primitive.

Ví dụ Integer vừa extends Number vừa implements Comparable<Integer>, nên có thể dùng. Nhưng không có nghĩa mọi subclass Number đều Comparable với chính kiểu của nó.

## 20. Chương trình hoàn chỉnh 8 — intersection bounds

Tệp **`IntersectionBoundDemo.java`**:

~~~java
public class IntersectionBoundDemo {
    static <T extends Number & Comparable<T>>
            T larger(T first, T second) {
        return first.compareTo(second) >= 0
                ? first : second;
    }

    public static void main(String[] args) {
        Integer a = larger(3, 7);
        Long b = larger(10L, 4L);
        Double c = larger(2.5, 2.5);

        System.out.println("integers=" + a);
        System.out.println("longs=" + b);
        System.out.println("doubles=" + c);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 IntersectionBoundDemo.java
java IntersectionBoundDemo
~~~

**Stdout:**

~~~text
integers=7
longs=10
doubles=2.5
~~~

Khi hai values bằng nhau theo `compareTo`, method trả first; kết quả `2.5` xác định. `Number` cung cấp numeric operations nếu cần, còn `Comparable<T>` cho phép so thứ tự với cùng T.

Nếu bài toán chỉ cần Comparable mà không cần Number, bound Number là **không cần thiết**; hãy giới hạn API vừa đủ.

## 21. Generic methods và wildcards: cùng liên quan kiểu, khác vai trò

Hai phương thức:

~~~java
static void printAll(java.util.List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
~~~

~~~java
static <T> void printTyped(java.util.List<T> values) {
    for (T value : values) {
        System.out.println(value);
    }
}
~~~

Đây là hai method snippets riêng hợp lệ khi nằm trong class.

`List<?>` dùng **wildcard**: caller có thể truyền List<String> hay List<Integer>, nhưng method không khai báo một type parameter T có tên để liên kết với return type hoặc tham số khác.

`<T> void printTyped(List<T>)` có một **named type variable T** cho toàn method. Trong trường hợp chỉ cần đọc từng value rồi in, generic T **không mang thêm quan hệ kiểu có ích**; `List<?>` thường đơn giản hơn.

Quy tắc chọn:
- Dùng wildcard khi chỉ cần **chấp nhận một vùng kiểu** và không cần liên kết nhiều vị trí.
- Dùng method type parameter khi muốn biểu diễn **quan hệ** giữa input–input, input–output hoặc giữa nhiều generic parameters.

Đừng cho rằng thêm `<T>` luôn làm API “an toàn hơn” một wildcard: mỗi cách giải quyết một vấn đề khác nhau.

## 22. Liên hệ nhiều tham số bằng cùng một type variable

Xét:

~~~java
static <T> void copy(
        java.util.List<? super T> destination,
        java.util.List<? extends T> source) {
    for (T value : source) {
        destination.add(value);
    }
}
~~~

Đây là một generic method snippet hợp lệ trong class. Method type T **liên kết** hai Lists: source sản xuất các values tương thích T; destination nhận các values T.

`? extends T` diễn đạt **producer**, `? super T` diễn đạt **consumer** — quy tắc thường nhớ bằng **PECS** (*Producer Extends, Consumer Super*).

Ví dụ, List<Integer> có thể làm source và List<Number> làm destination, dù `List<Integer>` **không** là subtype của `List<Number>`. Không có lệnh cast thiếu an toàn nào ở đây.

Các bounds trong generic method giúp compiler kiểm tra quan hệ kiểu mà một cặp `List<?>` độc lập không diễn đạt được.

## 23. Chương trình hoàn chỉnh 9 — PECS cùng tham số kiểu riêng

Tệp **`GenericCopyMethodDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericCopyMethodDemo {
    static <T> void copy(
            List<? super T> target,
            List<? extends T> source) {
        for (T element : source) {
            target.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4, 6);
        List<Number> destination = new ArrayList<>();

        copy(destination, source);

        System.out.println("destination=" + destination);
        System.out.println("size=" + destination.size());
        System.out.println("sum="
                + (destination.get(0).intValue()
                   + destination.get(1).intValue()
                   + destination.get(2).intValue()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericCopyMethodDemo.java
java GenericCopyMethodDemo
~~~

**Stdout:**

~~~text
destination=[2, 4, 6]
size=3
sum=12
~~~

Số nguyên được boxing vào List<Integer>. Khi copy, generic constraints bảo đảm các Integer values có thể được thêm vào List<Number>. Đây không phải một “cast List<Integer> thành List<Number>” (cast như vậy là sai semantics).

**Lưu ý thực tế:** method đơn giản này không cố giải quyết các tình huống `source == destination`, collections bị sửa đồng thời hoặc rollback khi add thất bại. Generic type safety không tự cung cấp transaction hay concurrency guarantees.

## 24. Invariance và lỗi kiểu phổ biến

Java generic classes như `List<E>` là **invariant** theo E: dù Integer extends Number, `List<Integer>` không phải subtype của `List<Number>`.

**Cố ý không biên dịch:**

~~~java
// List<Number> values = new ArrayList<Integer>();
~~~

Nếu kiểu này được phép, caller có thể thêm Double vào một ArrayList<Integer>, phá hợp đồng element type.

Dùng wildcard nếu muốn nhận một nhóm list:

~~~java
List<? extends Number> readable =
        new ArrayList<Integer>();
~~~

Đây là snippet hợp lệ với imports. Có thể đọc phần tử dưới dạng Number, nhưng không được tùy ý `readable.add(3)` vì kiểu thực tế của list có thể là một subtype Number khác.

Nếu cần cả đọc từ List<Integer> và ghi vào List<Number>, method có thể khai type relationship như ở ví dụ copy với `<T>`, `? extends T`, `? super T`.

## 25. Generic type parameter shadowing trong lớp generic

Java cho phép một **method type parameter có cùng tên** với class type parameter; type name bên trong method sẽ **che khuất** type name của lớp. Tuy biên dịch được trong các tình huống thích hợp, đây là nguồn gây hiểu nhầm.

~~~java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    <T> T echo(T input) {
        return input;
    }
}
~~~

Đây là một **class hợp lệ**. `T` trong khai báo `<T> T echo(T input)` là **T của method**, không phải T của Outer. Còn field `value` giữ T của class.

Ví dụ với `Outer<String> outer`, có thể gọi `Integer n = outer.echo(5)`, vì T của echo được suy luận là Integer.

**Khuyến nghị:** nếu method sử dụng kiểu khác class-level T, đặt `<U>` hoặc `<R>` thay vì khai lại `<T>`. Nhờ đó `T` luôn có nghĩa nhất quán trong code review, và phần khác biệt cấp độ không bị che giấu.

## 26. Chương trình hoàn chỉnh 10 — cùng tên T nhưng hai scopes

Tệp **`TypeParameterShadowDemo.java`**:

~~~java
final class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    T stored() {
        return value;
    }

    <T> T echo(T input) {
        return input;
    }
}

public class TypeParameterShadowDemo {
    public static void main(String[] args) {
        Outer<String> outer = new Outer<>("text");
        Integer result = outer.echo(99);

        System.out.println("stored=" + outer.stored());
        System.out.println("echo=" + result);
        System.out.println("stored class="
                + outer.stored().getClass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TypeParameterShadowDemo.java
java TypeParameterShadowDemo
~~~

**Stdout:**

~~~text
stored=text
echo=99
stored class=String
~~~

Đoạn chạy chứng minh `T` của `echo` không bị ràng buộc thành String bởi `Outer<String>`. Nhưng dù Java cho phép, kiểu viết `<U> U echo(U input)` thường là một lựa chọn dễ đọc hơn.

## 27. Type erasure ảnh hưởng gì tới generic methods?

Java generics chủ yếu được kiểm tra ở **compile time**. Trong quá trình biên dịch, type parameters chịu cơ chế **type erasure**:

- Unbounded T thường có erasure là Object.
- `T extends Number` có erasure là Number.
- Parameterized types được biểu diễn bằng raw runtime class tương ứng; có thể có casts do compiler chèn tại call sites.
- Type arguments như `String` và `Integer` không trở thành một bản runtime method/class riêng cho từng trường hợp.

Ví dụ `static <T> T identity(T input)` có dạng erasure gần với `Object identity(Object input)`. Đây là mô hình tư duy về bytecode signature, không phải yêu cầu người học tự viết raw Object API thay thế.

Các trường hợp biên dịch lỗi do erasure:
- Hai generic overloads có **cùng erasure**.
- Cố kiểm tra `instanceof T` với method type variable thông thường.
- Cố tạo `new T()` chỉ từ type parameter.
- Cố tạo `new T[10]` khi T không reifiable.

Vì Java kiểm tra ở compile time rồi erase, generic method không cho phép khám phá đầy đủ T trực tiếp ở runtime.

## 28. Chương trình hoàn chỉnh 11 — nhìn vào runtime class sau erasure

Tệp **`MethodErasureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MethodErasureDemo {
    static <T> String inspect(T value) {
        return value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();

        System.out.println("name type=" + inspect("Java"));
        System.out.println("number type=" + inspect(12));
        System.out.println("same list class="
                + (names.getClass() == numbers.getClass()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MethodErasureDemo.java
java MethodErasureDemo
~~~

**Stdout:**

~~~text
name type=String
number type=Integer
same list class=true
~~~

Method `inspect` không biết “generic T=String” qua một runtime token T nào: nó chỉ gọi `getClass()` trên object thực sự được đưa vào. Hai ArrayList instantiations có cùng runtime class dù compile-time element types khác nhau.

**Hạn chế của demo:** `inspect(null)` sẽ ném NPE do `value.getClass()`, không phải vì generics cấm null. Khi dùng generic methods với values có thể null, phải xác định null policy riêng.

## 29. Hạn chế `new T()` và cách truyền factory

Method type parameter **không đủ** để tạo một instance của kiểu T:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
// static <T> T create() {
//     return new T();
// }
~~~

Java không biết constructor nào của T hợp lệ tại runtime chỉ từ type variable đã bị erase.

Nếu caller có khả năng cung cấp đối tượng, bạn có thể truyền **factory function** như `Supplier<T>`:

~~~java
static <T> T create(java.util.function.Supplier<? extends T> factory) {
    return factory.get();
}
~~~

Đây là method snippet hợp lệ. Caller chỉ rõ cách tạo:

~~~java
StringBuilder buffer = create(StringBuilder::new);
~~~

Đây là snippet hợp lệ nếu create ở scope; `StringBuilder::new` là một constructor reference. Generic method T được suy luận là StringBuilder dựa trên supplier và target type.

Nếu cần runtime reflection theo `Class<T>`, hãy nhận class token tường minh và xử lý constructor accessibility/checked exceptions theo policy của API; **đừng giả định mọi class có constructor công khai không tham số**.

## 30. Chương trình hoàn chỉnh 12 — tạo T qua `Supplier`

Tệp **`GenericSupplierDemo.java`**:

~~~java
import java.util.function.Supplier;

public class GenericSupplierDemo {
    static <T> T create(Supplier<? extends T> factory) {
        return factory.get();
    }

    static <T> T build(
            Supplier<? extends T> factory,
            java.util.function.Consumer<? super T> setup) {
        T object = factory.get();
        setup.accept(object);
        return object;
    }

    public static void main(String[] args) {
        StringBuilder empty = create(StringBuilder::new);
        StringBuilder configured = build(
                StringBuilder::new,
                builder -> builder.append("Java"));

        System.out.println("empty length=" + empty.length());
        System.out.println("configured=" + configured);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 GenericSupplierDemo.java
java GenericSupplierDemo
~~~

**Stdout:**

~~~text
empty length=0
configured=Java
~~~

`Supplier<? extends T>` tạo ra object tương thích T. `Consumer<? super T>` nhận T để cấu hình. Việc dùng method type parameter này không yêu cầu class chứa method phải khai T.

**Không coi hàm create là construction an toàn trong mọi trường hợp:** factory có thể ném exception, trả null hoặc tạo mutable object; generic constraints chỉ kiểm tra quan hệ kiểu.

## 31. `Class<T>` token giúp liên kết type ở compile time và runtime

Khi cần kiểm tra/cast một object theo class caller cung cấp, nhận `Class<T>`:

~~~java
static <T> T checkedCast(Class<T> type, Object value) {
    return type.cast(value);
}
~~~

Đây là method snippet hợp lệ. `type.cast(value)` kiểm tra runtime object tương thích với Class token; nếu không, nó ném ClassCastException.

So với `(T) value`, `Class<T>.cast` có runtime check gắn với một token rõ và tránh một unchecked cast tùy ý. Nhưng `Class<List<String>>` theo nghĩa một class literal mang đầy đủ generic arguments **không tồn tại**. Class token thường biết raw runtime class, không biết element type sâu của List<T> sau erasure.

**Cố ý không biên dịch:**

~~~java
// Class<java.util.List<String>> type =
//         java.util.List<String>.class;
~~~

Đừng kỳ vọng `Class<T>` giải quyết mọi validation của nested generic values.

## 32. Chương trình hoàn chỉnh 13 — checked cast bằng Class token

Tệp **`GenericClassTokenDemo.java`**:

~~~java
public class GenericClassTokenDemo {
    static <T> T checkedCast(Class<T> type, Object value) {
        return type.cast(value);
    }

    public static void main(String[] args) {
        Object source = "hello";

        String text = checkedCast(String.class, source);
        System.out.println("text=" + text);

        try {
            Integer number =
                    checkedCast(Integer.class, source);
            System.out.println("number=" + number);
        } catch (ClassCastException ex) {
            System.out.println("mismatch="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericClassTokenDemo.java
java GenericClassTokenDemo
~~~

**Stdout:**

~~~text
text=hello
mismatch=ClassCastException
~~~

String.class và Integer.class là hai class tokens khác nhau. Nếu object không thuộc kiểu được yêu cầu, `Class.cast` báo lỗi runtime; compiler vẫn suy ra return T tương ứng từ Class<T>.

## 33. Generic method overloads và type erasure

Overloading dựa trên **method signatures**, không chỉ trên tên. Một generic method và một method thường có thể overload hợp lệ khi tham số sau erasure khác:

~~~java
static String describe(String text) {
    return "string:" + text;
}

static <T> String describe(T value) {
    return "generic:" + value;
}
~~~

Đây là hai method snippets hợp lệ trong một class. String overload cụ thể hơn cho String argument; generic overload có thể được gọi với Integer hoặc Boolean.

Nhưng các khai báo sau **cố ý không biên dịch nếu cùng xuất hiện**:

~~~java
// static <T> void consume(T value) {}
// static void consume(Object value) {}
~~~

Method generic đầu có erasure nhận Object; method thứ hai cũng nhận Object, gây name clash.

Một cặp khác **cố ý không biên dịch**:

~~~java
// static void use(java.util.List<String> x) {}
// static void use(java.util.List<Integer> x) {}
~~~

Sau erasure cả hai cùng nhận List. Không thể overload chỉ bằng generic type arguments.

## 34. Chương trình hoàn chỉnh 14 — overload cụ thể và generic

Tệp **`GenericOverloadDemo.java`**:

~~~java
public class GenericOverloadDemo {
    static String describe(String text) {
        return "string:" + text;
    }

    static <T> String describe(T value) {
        return "generic:" + value;
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(10));
        System.out.println(describe(true));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericOverloadDemo.java
java GenericOverloadDemo
~~~

**Stdout:**

~~~text
string:Java
generic:10
generic:true
~~~

Dòng với String chọn overload nhận String do nó cụ thể hơn. Dòng với Integer và Boolean dùng generic overload.

**Đừng nghĩ generic overload luôn được chọn vì “linh hoạt hơn”.** Java có những quy tắc overload resolution dựa trên các applicable methods, phases của invocation và specificity; khi API có nhiều overloads cùng generic inference, hãy viết test compile-time cho call sites quan trọng.

## 35. Generics và primitive values

Java không cho dùng primitive types trực tiếp làm generic type arguments:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
// List<int> values = new ArrayList<int>();
// GenericIdentityDemo.<int>identity(5);
~~~

Bạn cần wrapper types:

~~~java
java.util.List<Integer> values =
        java.util.List.of(1, 2, 3);
~~~

Đây là snippet hợp lệ; int literals được boxing thành Integer. Với generic method `<T> T identity(T input)`, caller truyền primitive `5` vẫn được vì **autoboxing** tạo Integer.

Nhưng boxing/unboxing có chi phí và có thể ném NullPointerException khi unbox một wrapper null. Trong code xử lý hàng triệu primitive elements, chuyên biệt hóa bằng `int[]`, primitive streams hoặc API primitive chuyên dụng có thể phù hợp hơn generic containers.

Generic method type parameter không “hỗ trợ primitive” chỉ vì compiler chấp nhận expression dạng số nguyên.

## 36. Generic varargs và heap pollution

Một generic method có thể nhận varargs:

~~~java
@SafeVarargs
static <T> java.util.List<T> immutable(T... elements) {
    return java.util.List.of(elements);
}
~~~

Đây là snippet method **hợp lệ nếu đặt trong class**. `T...` được biểu diễn bằng array parameter. Generic varargs có thể tạo **compiler warnings** vì arrays có runtime component types trong khi phần lớn parameterized generic types không reifiable.

`@SafeVarargs` là một cam kết của tác giả rằng implementation **không thực hiện các thao tác không an toàn** lên generic varargs array, chẳng hạn ghi object sai kiểu qua alias Object[]. Annotation không tự làm một method trở nên an toàn nếu body thực sự vi phạm contract. Trong Java 17, annotation này được phép cho static, final, và những instance methods private phù hợp; không dùng tùy tiện với overridable instance method.

Tại call site, `immutable("A","B")` suy luận T=String và tạo một List không hỗ trợ mutation. Nếu method nhận các elements null, `List.of` ném NullPointerException theo contract.

## 37. Chương trình hoàn chỉnh 15 — generic varargs an toàn

Tệp **`GenericVarargsDemo.java`**:

~~~java
import java.util.List;

public class GenericVarargsDemo {
    @SafeVarargs
    static <T> List<T> immutable(T... elements) {
        return List.of(elements);
    }

    public static void main(String[] args) {
        List<String> names = immutable("An", "Binh");
        List<Integer> numbers = immutable(1, 2, 3);

        System.out.println("names=" + names);
        System.out.println("numbers=" + numbers);
        System.out.println("count=" + numbers.size());

        try {
            names.add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("mutation blocked=true");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericVarargsDemo.java
java GenericVarargsDemo
~~~

**Stdout:**

~~~text
names=[An, Binh]
numbers=[1, 2, 3]
count=3
mutation blocked=true
~~~

`List.of` giữ thứ tự elements của input. Ở method này chúng ta không gán phần tử khác kiểu vào varargs array và không làm lộ array mutable; annotation phù hợp với implementation đơn giản đó.

`@SafeVarargs` **không** phải cách tắt warnings bất kể mức độ nguy hiểm. Nếu body chuyển `T[]` thành `Object[]` rồi ghi sai runtime type, có thể dẫn tới ArrayStoreException hoặc heap pollution dù method đã được annotation.

## 38. Generic method trong `record`

Record có thể là generic hoặc không generic. Nó vẫn có thể khai báo methods với type parameters riêng:

~~~java
record Pair<A, B>(A first, B second) {
    <R> R combine(
            java.util.function.BiFunction<
                    ? super A, ? super B, ? extends R> mapper) {
        return mapper.apply(first, second);
    }
}
~~~

Đây là record hợp lệ. A/B thuộc **Pair record**, còn R thuộc **method combine**. Caller có thể kết hợp cùng một Pair<String,Integer> theo nhiều cách trả String, Boolean hoặc một DTO khác.

Với một record không generic `record Point(int x,int y)`, bạn vẫn có thể khai `<R> R map(BiFunction<Integer,Integer,R> mapper)`, vì method generic không đòi class generic.

**Đừng nhầm generic method với generic constructor:** constructor của record có canonical signature theo record components, với các ràng buộc riêng của JLS. Nếu vấn đề học tập chỉ là xử lý/biến đổi values, method type parameter là giải pháp thẳng hơn.

## 39. Chương trình hoàn chỉnh 16 — generic method của generic record

Tệp **`GenericRecordMethodDemo.java`**:

~~~java
import java.util.function.BiFunction;

record Pair<A, B>(A first, B second) {
    <R> R combine(
            BiFunction<? super A, ? super B, ? extends R> mapper) {
        return mapper.apply(first, second);
    }
}

public class GenericRecordMethodDemo {
    public static void main(String[] args) {
        Pair<String, Integer> score = new Pair<>("An", 90);

        String label =
                score.combine((name, points) ->
                        name + "=" + points);
        Boolean passed =
                score.combine((name, points) -> points >= 50);
        Integer doubled =
                score.combine((name, points) -> points * 2);

        System.out.println("label=" + label);
        System.out.println("passed=" + passed);
        System.out.println("doubled=" + doubled);
        System.out.println("pair=" + score);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericRecordMethodDemo.java
java GenericRecordMethodDemo
~~~

**Stdout:**

~~~text
label=An=90
passed=true
doubled=180
pair=Pair[first=An, second=90]
~~~

A=String và B=Integer được xác định từ Pair instance. R của `combine` lần lượt là String, Boolean và Integer; không lần nào thay đổi các components của score.

## 40. Method tham số kiểu riêng và generic constructor là hai cơ chế khác

Một class generic có thể có constructor sử dụng class-level T:

~~~java
final class Wrapper<T> {
    private final T value;

    Wrapper(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Đây là class hợp lệ. Constructor nhận T của **class**; nó không tự khai một type parameter mới.

Một **generic constructor** cũng có thể tồn tại trong class thường, bằng cách khai type parameter trước tên constructor:

~~~java
final class TaggedValue<T> {
    private final T value;
    private final String tag;

    <U> TaggedValue(T value, U tag) {
        this.value = value;
        this.tag = String.valueOf(tag);
    }

    T get() {
        return value;
    }

    String tag() {
        return tag;
    }
}
~~~

Đây là class hợp lệ. T thuộc class, U thuộc constructor. Mỗi lời gọi constructor có thể suy luận U riêng, tương tự generic method, nhưng constructor không khai kiểu trả về. Nhận biết được generic constructor giúp tránh hiểu nhầm `<U>` trước tên constructor là một method mang kiểu trả về bị thiếu.

## 41. Chương trình hoàn chỉnh 17 — class type và constructor type riêng

Tệp **`GenericConstructorScopeDemo.java`**:

~~~java
final class TaggedValue<T> {
    private final T value;
    private final String tag;

    <U> TaggedValue(T value, U tag) {
        this.value = value;
        this.tag = String.valueOf(tag);
    }

    T value() {
        return value;
    }

    String tag() {
        return tag;
    }
}

public class GenericConstructorScopeDemo {
    public static void main(String[] args) {
        TaggedValue<String> first =
                new TaggedValue<>("Java", 17);
        TaggedValue<Integer> second =
                new TaggedValue<>(5, true);

        System.out.println("first="
                + first.value() + ":" + first.tag());
        System.out.println("second="
                + second.value() + ":" + second.tag());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericConstructorScopeDemo.java
java GenericConstructorScopeDemo
~~~

**Stdout:**

~~~text
first=Java:17
second=5:true
~~~

T của TaggedValue được quyết định theo declared type/diamond inference của mỗi instance; U của constructor được suy luận từ argument `17` hoặc `true`. Constructor generic có thể dùng type parameter riêng ngay cả khi enclosing class cũng generic.

**Trọng tâm phân biệt:** generic method khai `<U>` trước **return type**; generic constructor khai `<U>` trước **constructor name** và không có return type.

## 42. Wildcard capture và helper method dùng `<T>`

Có những API nhận `List<?>` nhưng cần thao tác theo **một kiểu element cụ thể bên trong cùng list**. Một private generic helper có thể **capture wildcard** thành một type variable T có tên để nối quan hệ giữa các operations.

Ví dụ:

~~~java
static void swapFirstTwo(java.util.List<?> list) {
    swapFirstTwoCaptured(list);
}

private static <T> void swapFirstTwoCaptured(
        java.util.List<T> list) {
    T first = list.get(0);
    list.set(0, list.get(1));
    list.set(1, first);
}
~~~

Hai methods snippets hợp lệ trong class; giả định list có ít nhất hai phần tử và hỗ trợ `set`. Nếu list là `List.of(...)`, `set` sẽ ném UnsupportedOperationException; nếu list có dưới hai phần tử, `get` sẽ ném IndexOutOfBoundsException.

Generic helper cho phép biết `get(0)` và `set(1,...)` đều sử dụng **cùng captured element type T**. Đây là trường hợp method type parameter hữu ích ngay cả khi public API chỉ biểu lộ `List<?>`.

**Không dùng raw List và cast Object bừa bãi** để “giải quyết” việc wildcard không cho add/set dễ dàng: raw types bỏ kiểm tra kiểu mà compiler đang bảo vệ.

## 43. Chương trình hoàn chỉnh 18 — wildcard capture với helper

Tệp **`WildcardCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapFirstTwo(List<?> items) {
        if (items.size() < 2) {
            throw new IllegalArgumentException(
                    "need at least two");
        }
        swapCaptured(items);
    }

    private static <T> void swapCaptured(List<T> items) {
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }

    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(List.of("An", "Binh"));
        List<Integer> numbers =
                new ArrayList<>(List.of(1, 2));

        swapFirstTwo(names);
        swapFirstTwo(numbers);

        System.out.println("names=" + names);
        System.out.println("numbers=" + numbers);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 WildcardCaptureDemo.java
java WildcardCaptureDemo
~~~

**Stdout:**

~~~text
names=[Binh, An]
numbers=[2, 1]
~~~

Public method dùng wildcard để nhận bất kỳ List element type nào; private helper dùng generic T để compiler biết hai lệnh `set` không đưa nhầm kiểu mới vào list.

## 44. Method tham số kiểu riêng và kế thừa/overriding

Một generic method có thể được khai ở superclass hoặc interface. Khi một subclass override, phải tuân **method signature và type parameter bounds** phù hợp; không được tự ý thay generic method thành overload chỉ khác type name mà tưởng là override.

Ví dụ:

~~~java
interface Converter {
    <T> T same(T value);
}

final class SimpleConverter implements Converter {
    @Override
    public <U> U same(U value) {
        return value;
    }
}
~~~

Đây là khai báo hợp lệ. Tên type parameter T/U **không phải phần quyết định identity của method**; các signatures tương thích sau việc đổi tên biến kiểu theo quy tắc Java.

Một method `String same(String s)` riêng không tự thay thế `<T> T same(T)`: method generic phải chấp nhận nhiều kiểu T, không phải chỉ String.

Đặt `@Override` để compiler kiểm tra chính xác mình đang override; đừng dùng raw types để ép compiler bỏ qua generic contract.

## 45. Chương trình hoàn chỉnh 19 — override generic method

Tệp **`GenericOverrideDemo.java`**:

~~~java
interface Converter {
    <T> T same(T value);
}

final class SimpleConverter implements Converter {
    @Override
    public <U> U same(U value) {
        return value;
    }
}

public class GenericOverrideDemo {
    public static void main(String[] args) {
        Converter converter = new SimpleConverter();

        String text = converter.same("Java");
        Integer number = converter.same(17);

        System.out.println("text=" + text);
        System.out.println("number=" + number);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericOverrideDemo.java
java GenericOverrideDemo
~~~

**Stdout:**

~~~text
text=Java
number=17
~~~

Compiler coi generic method `<U> U same(U)` là implementation phù hợp cho `<T> T same(T)`, dù tên ký hiệu khác nhau. Interface type Converter vẫn giữ hợp đồng generic cho mỗi invocation.

## 46. Những anti-patterns cần tránh

| Lỗi thường gặp | Vì sao sai hoặc khó bảo trì | Cách sửa |
| --- | --- | --- |
| Viết `T method(...)` nhưng chưa khai T trong scope | Compiler không tìm thấy type variable | Khai `<T>` đúng chỗ hoặc dùng T của lớp |
| Dùng class T trong static method | Static context không có class-level T | Dùng `static <U>` |
| Khai `<T>` trong method khi T của class đã đủ | T mới có thể shadow T cũ | Bỏ `<T>` nếu chỉ dùng type của lớp |
| Dùng cùng tên T cho class và method độc lập | Dễ đọc nhầm hai scopes | Đặt U/R cho method |
| Khai generic method chỉ để in `List<?>` | Không liên kết kiểu nào khác | Dùng wildcard đơn giản |
| Viết `new T()` | Không có constructor token runtime T | Truyền `Supplier<T>` hoặc factory |
| Viết `new T[n]` | Array creation với non-reifiable T không hợp lệ | Nhận array factory hoặc API an toàn khác |
| `instanceof T` | T bị erasure, không có runtime T class test trực tiếp | Dùng `Class<T>.isInstance` |
| Overload `List<String>` và `List<Integer>` | Erasure gây name clash | Tên method khác hoặc một generic method |
| `List<Integer>` gán vào `List<Number>` | Generic invariance | Dùng PECS/wildcards khi thích hợp |
| `<T extends Number>` nhưng viết `T + T` | T là reference type, không có numeric operator tổng quát | Dùng numeric API/định nghĩa operation |
| Trông chờ generic T là primitive | Java generics nhận reference types | Boxing/wrapper hoặc primitive API |
| `@SafeVarargs` để che implementation nguy hiểm | Annotation là cam kết chứ không phải sửa lỗi | Chỉ dùng khi body thực sự an toàn |
| Ép unchecked casts vì inference khó | Có nguy cơ ClassCastException khi dùng kết quả | Thiết kế API rõ hơn hoặc truyền Class token |
| Đọc generic signature như runtime reified type | Erasure làm mất type arguments thông thường | Rõ compile-time vs runtime |
| Dùng nhiều method type params không có quan hệ | API dài, khó suy luận | Dùng wildcards hoặc type cụ thể |
| Dùng raw List để “giải quyết” wildcard | Bỏ type checking | Generic helper capture wildcard |
| Tin generic method bảo đảm input không null | Generics không cấm null | Validate theo domain |
| Tin generic method tự làm object immutable/thread-safe | Không liên quan | Ownership/concurrency riêng |

## 47. Cách đọc một chữ ký phương thức generic

Khi gặp chữ ký:

~~~java
public static <T, R> java.util.List<R> transform(
        java.util.List<? extends T> source,
        java.util.function.Function<? super T, ? extends R> mapper)
~~~

Đây là **chữ ký minh họa**, không phải chương trình độc lập (chưa có body).

Hãy phân tích theo thứ tự:

1. `public static`: modifiers.
2. `<T, R>`: **khai báo method type parameters** T và R; chúng không phải type arguments được truyền từ `class`.
3. `List<R>`: kiểu trả về, list elements loại R.
4. `source`: một List có elements thuộc subtype nào đó của T.
5. `mapper`: một Function có thể nhận T hoặc supertype của T và trả R hoặc subtype của R.
6. `transform`: tên method.
7. Compiler suy luận T/R ở từng invocation, từ source, mapper và target type.
8. T/R được kiểm tra compile time; không trở thành hai Class objects runtime riêng chỉ vì dùng generics.

Cách đọc này hữu ích với API Java Collections, Streams, Optional, Comparators và các phương thức biến đổi collections.

## 48. Chương trình hoàn chỉnh 20 — generic transform với source/output độc lập

Tệp **`GenericTransformDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class GenericTransformDemo {
    static <T, R> List<R> transform(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> words = List.of("java", "code");
        List<Integer> lengths =
                transform(words, String::length);
        List<String> upper =
                transform(words, String::toUpperCase);

        System.out.println("words=" + words);
        System.out.println("lengths=" + lengths);
        System.out.println("upper=" + upper);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericTransformDemo.java
java GenericTransformDemo
~~~

**Stdout:**

~~~text
words=[java, code]
lengths=[4, 4]
upper=[JAVA, CODE]
~~~

T là String ở hai lần gọi; R lần lượt là Integer và String. Method có thể tái sử dụng cho nhiều kiểu nguồn và kết quả mà không sửa body.

Kết quả là một ArrayList mutable, vì implementation chọn `new ArrayList<>()`. Generics **không quyết định** mutability của collection.

## 49. Những ràng buộc về API, null, lỗi và concurrency

Generic methods chủ yếu diễn đạt **ràng buộc kiểu**, không thay các hợp đồng vận hành khác:

- **Null:** `<T> T identity(T x)` vẫn nhận null trong những ngữ cảnh suy luận hợp lệ; gọi method trên x có thể ném NPE.
- **Exceptions:** generic bounds không tự chuyển checked exception thành unchecked. API vẫn phải khai/handle theo Java rules.
- **Mutability:** một method trả `List<T>` có thể trả mutable ArrayList hoặc unmodifiable List; phải tài liệu hóa.
- **Thread safety:** `<T> void add(List<T>, T)` không làm ArrayList thread-safe.
- **Side effects:** mapper trong `transform` có thể mutate external state hoặc ném exception; generic contract không rollback.
- **Numeric precision:** bound Number không tự làm kết quả double chính xác cho mọi BigDecimal/BigInteger.
- **Ownership:** trả lại reference T có thể cho caller mutate object ban đầu; generic identity không clone.
- **Unchecked casts:** tránh nếu không có cơ sở runtime chính đáng, ngay cả khi test case đơn giản chạy.

Khi thiết kế generic API, nên ghi rõ ai sở hữu collections, khả năng null, exception behavior và target mutability bên cạnh generic type signature.

## 50. Một bộ bài tập thực hành theo cấp độ

### Cấp 1 — đọc ký hiệu

**1.** Trong `class Box<T> { T get() { ... } }`, `get` có tự khai method type parameter không?

**2.** Trong `<U> U echo(U x)`, U thuộc class hay method?

**3.** Có thể khai `static T get()` trong `class Box<T>` rồi dùng T của lớp không?

**4.** Thứ tự đúng là `public <T> T identity(T x)` hay `public T <T> identity(T x)`?

**5.** `<T> String describe(T x)` có phải generic method dù return type không dùng T?

**6.** `static <T> void print(List<T>)` và `static void print(List<?>)` khác nhau ở khả năng đặt tên T thế nào?

**7.** Type witness `<String>` được đặt ở đâu khi gọi `Util.identity(...)`?

**8.** `<N>` có tự bảo đảm N extends Number không?

### Cấp 2 — dự đoán type inference

**9.** Với `static <T> T identity(T x)`, `Integer x = identity(3)` có hợp lệ không?

**10.** `String x = identity(3)` có hợp lệ không nếu không có overload khác và identity chỉ trả tham số?

**11.** `Box<String>` có thể gọi `<U> U echo(U x)` với Integer argument không?

**12.** Khi `Holder<String>.map(String::length)` trả Integer, class-level T có đổi thành Integer không?

**13.** `<K,V> Entry<K,V> pair(K,V)` có thể tạo Entry<String,Boolean> không?

**14.** `List<Integer>` có gán trực tiếp vào `List<Number>` không?

**15.** `List<Integer>` có phù hợp với `List<? extends Number>` không?

### Cấp 3 — bounds, erasure, API

**16.** Vì sao `<N extends Number>` cho phép `n.doubleValue()`?

**17.** Vì sao `<N extends Number>` không cho cộng `n + n` như phép toán cho mọi N?

**18.** `<T extends Number & Comparable<T>>` đặt Number sau Comparable có luôn hợp lệ không?

**19.** Vì sao overload `use(List<String>)` và `use(List<Integer>)` bị lỗi?

**20.** Vì sao `new T()` không hợp lệ trong generic method?

**21.** `Class<T>.cast` có kiểm tra được List<String> elements đúng String nhờ class token không?

**22.** Generic method khai `<T> T method(T x)` có nghĩa T được reify thành runtime type argument object không?

**23.** Một `@SafeVarargs` method có tự trở nên an toàn nếu body gán sai kiểu vào varargs array không?

**24.** Khi nào `Supplier<T>` hợp lý hơn `new T()`?

### Cấp 4 — thiết kế

**25.** Nếu class giữ `T value` và mỗi method call cần trả một kiểu R khác, nên khai R ở cấp nào?

**26.** Nếu API chỉ đọc List<?> rồi in, có nhất thiết cần `<T>` không?

**27.** Nếu API copy List<Integer> sang List<Number>, tham số nguồn/đích nên dùng quan hệ wildcard nào?

**28.** Vì sao nên tránh khai `<T>` trong method khi class cũng đã có T nhưng hai T độc lập?

**29.** Khi nào một private generic helper có thể giải quyết vấn đề wildcard capture?

**30.** Một record generic Pair<A,B> có được khai method `<R> R combine(...)` không?

**31.** Generic constructor `<U> TaggedValue(T value,U tag)` khác method generic thế nào?

**32.** Khi đưa generic code vào concurrency hoặc mutable collections, ràng buộc kiểu có thay thế synchronization/defensive copying không?

### Đáp án và giải thích

1. Không; get dùng T của lớp, không có danh sách type parameters riêng.
2. Thuộc method; khác với type variable cùng tên ở nơi khác.
3. Không; static context không dùng class-level T. Cần `static <U>` hoặc kiểu cụ thể.
4. `public <T> T identity(T x)` đúng thứ tự.
5. Có; phương thức sở hữu type parameter T dù trả String.
6. Bản có `<T>` đặt tên type liên kết các vị trí; wildcard không có tên T.
7. Sau qualifier và trước method name: `Util.<String>identity(x)`.
8. Không; phải viết `<N extends Number>`.
9. Có; int boxing thành Integer.
10. Không; int/Integer argument không làm identity trả String tùy ý.
11. Có; U thuộc method độc lập với T=String của Box.
12. Không; Holder vẫn giữ T=String; R riêng của map là Integer.
13. Có; K=String, V=Boolean theo inference.
14. Không; List generic invariant.
15. Có; Integer là subtype Number nên wildcard extends nhận list đó.
16. Compiler biết N có các methods của Number.
17. Generics không có numeric operator chung trên reference types.
18. Không nếu Number là class bound; class bound phải đứng đầu các interface bounds.
19. Erasure biến cả hai danh sách parameter thành List.
20. T không cho biết constructor runtime và bị type erasure.
21. Không; Class token của raw List không chứa element type String ở runtime.
22. Không; erasure không tạo một instantiated method class riêng cho mỗi T.
23. Không; annotation chỉ là cam kết của tác giả.
24. Khi caller biết cách khởi tạo T qua constructor reference/factory function.
25. Ở method: `<R> R map(...)`.
26. Không nhất thiết; `List<?>` thường đủ.
27. `List<? extends T>` cho source, `List<? super T>` cho destination, với method `<T>`.
28. T của method shadow T của class, gây nhầm nghĩa.
29. Khi method cần đọc/ghi nhất quán cùng captured element type của `List<?>`.
30. Có. A/B thuộc record, R thuộc method.
31. Constructor không có return type và dùng tên class; method có return type/name riêng.
32. Không; generic type safety không thay ownership, mutability hoặc thread safety.

## 51. Checklist khi viết hoặc review generic method

- [ ] Đã xác định mỗi type variable thuộc class hay method?
- [ ] Phương thức có cần một type parameter riêng, hay chỉ dùng T của class?
- [ ] Nếu method không generic, có vô tình khai `<T>` rồi shadow T lớp không?
- [ ] `<T>` được đặt **trước return type**, sau modifiers?
- [ ] Với static method, không tham chiếu class-level T sai ngữ cảnh?
- [ ] Mọi type parameters được khai và nằm trong scope?
- [ ] Nếu cần nhiều type variables, tên K/V/T/R có diễn đạt đúng quan hệ?
- [ ] Dùng `extends` cho upper bound phù hợp, không nhầm với primitive types?
- [ ] Nếu có class bound và interface bounds, class bound đứng đầu?
- [ ] Method có thực sự cần named T, hay wildcard là đủ?
- [ ] Với producers/consumers, đã chọn `? extends T`/`? super T` theo PECS?
- [ ] Đã tránh raw types và unchecked casts không cần thiết?
- [ ] Có tránh overloads trùng nhau sau type erasure?
- [ ] Có hiểu type inference ở các call sites quan trọng?
- [ ] Type witness chỉ dùng nơi làm rõ hoặc giải quyết inference?
- [ ] Có tránh `new T()`, `new T[]`, `instanceof T` khi không được hỗ trợ?
- [ ] Nếu cần runtime type check, có Class<T> token phù hợp và hiểu giới hạn erasure?
- [ ] Với generic varargs, implementation có thật sự an toàn trước khi thêm @SafeVarargs?
- [ ] Có phân biệt generic method với generic constructor?
- [ ] Với override, `@Override` và generic signature có hợp đồng phù hợp?
- [ ] Ví dụ runnable đã có import, đúng file/class, đúng stdout?
- [ ] Các vấn đề null, exception, mutability, concurrency được mô tả riêng?
- [ ] Method type parameter phản ánh một quan hệ kiểu có ích, không chỉ thêm ký hiệu?

## 52. Tài liệu chính thức Java 17

- [JLS 17 §8.4.4 — Generic Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.4): cú pháp và ngữ nghĩa generic method declarations.
- [JLS 17 §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): method signature, subsignature và method type parameters.
- [JLS 17 §8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): overriding generic methods.
- [JLS 17 §8.8.4 — Generic Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.4): constructor type parameters.
- [JLS 17 §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): type variables và upper bounds.
- [JLS 17 §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erasure của type variables và parameterized types.
- [JLS 17 §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): invariance và generic types.
- [JLS 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): wildcard capture.
- [JLS 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): method invocation/overloading.
- [JLS 17 §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): generic method inference.
- [Java SE 17 API — Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): Function<? super T,? extends R>.
- [Java SE 17 API — Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): factory callback trả T.
- [Java SE 17 API — Class.cast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)): runtime cast có token.
- [Java SE 17 API — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): collection generic và factory.
- [Java SE 17 API — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): các operations trên arrays.
- [Java SE 17 API — SafeVarargs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): hợp đồng cho generic/reifiable varargs.
- [Oracle Java Tutorials — Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html): giải thích cú pháp method type parameter.
- [Oracle Java Tutorials — Bounded Type Parameters](https://docs.oracle.com/javase/tutorial/java/generics/bounded.html): upper bounds và multiple bounds.
- [Oracle Java Tutorials — Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html): ví dụ giải quyết wildcard capture.

## 53. Tổng kết

**Phương thức generic khai báo bộ type parameters riêng bằng `<T>`, `<U>`, `<R>`, ... đặt trước kiểu trả về**, và chúng được suy luận hoặc chỉ định theo **từng lần gọi**. Một lớp generic `Box<T>` có thể dùng T cho state của nó, đồng thời một method `<U> U echo(U)` hoặc `<R> R map(...)` dùng kiểu riêng hoàn toàn độc lập. Một static method không được sử dụng class-level T trực tiếp; nó phải khai các type parameters của chính mình khi muốn generic.

Những ưu điểm nổi bật là **tái sử dụng thuật toán**, **compile-time type safety**, và khả năng biểu diễn quan hệ giữa các vị trí kiểu: `<K,V>` cho cặp key/value, `<T,R>` cho transformation, `<T>` cùng PECS cho copy lists. Hãy chọn wildcard nếu không cần một named type variable liên kết các vị trí.

Cuối cùng, **generics không reify đầy đủ type arguments ở runtime**. Type erasure giải thích vì sao không được overload chỉ khác `List<String>`/`List<Integer>`, không có `new T()` mặc định, và cần factory/Class token khi runtime operations yêu cầu kiểu cụ thể. Phương thức generic tốt không phải phương thức có nhiều chữ T, mà là phương thức khai các ràng buộc **đúng, tối thiểu và rõ nghĩa**.
