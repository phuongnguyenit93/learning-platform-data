# Tham chiếu constructor (`Type::new`) trong Java 8

## 1. Khái niệm và mục tiêu

**Constructor reference** (*tham chiếu constructor*) là một dạng **method reference** của Java, có cú pháp phổ biến `ClassName::new` hoặc `ArrayType::new`. Nó cho phép biểu diễn **hành động tạo đối tượng/mảng** như một hàm và truyền hành động đó tới API đang nhận **functional interface**. Tính năng này có từ Java 8 và vẫn là cách viết phổ biến, hợp lệ trong Java hiện đại.

Thay vì viết lambda trực tiếp gọi constructor:

```java
java.util.function.Supplier<Order> factory = () -> new Order();
```

khi đã có kiểu đích phù hợp, bạn có thể viết:

```java
java.util.function.Supplier<Order> factory = Order::new;
```

Hai dòng trên là ví dụ **giả sử class `Order` có constructor không tham số có thể truy cập**; không phải chương trình chạy độc lập. Với cả hai biểu thức, việc khai báo `factory` **không tạo `Order` ngay**. Mỗi lần gọi `factory.get()` sẽ thực hiện hành vi xây dựng đối tượng, theo contract của constructor.

Bài học giúp bạn:

- Nhận ra cú pháp `ClassName::new`, `GenericClass<T>::new` và `ArrayType::new`.
- Hiểu vì sao constructor reference **phụ thuộc kiểu đích (target typing)** và cách compiler chọn constructor overload.
- Dùng `Supplier<T>`, `Function<A,T>`, `BiFunction<A,B,T>` và `IntFunction<T[]>` đúng chữ ký.
- Đưa constructor reference vào Stream, collection, helper factory và generic API.
- Phân biệt constructor reference với **method reference tới static factory** và với **lambda có logic bổ sung**.
- Xử lý đúng những giới hạn về access modifier, exception, generics, overloaded constructors, array allocation và side effects.

**Phạm vi phiên bản:** bài tập trung vào ngữ nghĩa Java 8 vẫn tiếp tục áp dụng; ví dụ chạy được với JDK 17+ và không yêu cầu API lỗi thời.

## 2. Cú pháp và mô hình thực thi

Một constructor reference có cấu trúc:

```java
TypeName::new
```

Khi `TypeName` là một class phù hợp, tham chiếu này biểu diễn một hành vi gọi **constructor của class đó**. Dạng mảng `TypeName[]::new` biểu diễn hành vi tạo mảng.

So sánh ba cách:

| Cách viết | Ý nghĩa |
| --- | --- |
| `new Account()` | Gọi constructor **ngay**, trả về object mới tại biểu thức đó. |
| `() -> new Account()` | Tạo một lambda có hành vi gọi constructor khi được thực thi. |
| `Account::new` | Tạo method reference biểu diễn hành vi gọi constructor khi được thực thi. |

Bảng trên giả định `Account()` tồn tại và có thể truy cập; lambda và reference phải được đặt trong **ngữ cảnh có functional-interface target type**, chẳng hạn `Supplier<Account>`.

**Điểm cốt lõi:** `Account::new` **không có dấu ngoặc gọi constructor**. Nó không phải `Account::new()`, `new Account::new` hoặc `Account.new`. Reference mô tả hành vi; target functional interface quy định số lượng, kiểu tham số và kết quả cần trả.

Ví dụ:

```java
Supplier<Account> create = Account::new;
Account first = create.get();
Account second = create.get();
```

Đây là đoạn minh họa trong method có import `Supplier` và class `Account`. `first` và `second` được tạo thông qua **hai lần thực thi constructor**, không phải việc tham chiếu constructor tự động khởi tạo singleton. Trong trường hợp thông thường, mỗi lần chạy một constructor class để tạo object tạo ra object mới. Không đánh đồng danh tính của **functional interface object** (reference có thể được runtime tối ưu/tái sử dụng) với danh tính của **object được constructor tạo ra**.

## 3. Constructor reference cần functional interface đích

Trong Java, lambda và constructor reference là **poly expressions**: compiler cần **target type** để xác định chữ ký cần thỏa mãn. Target type phổ biến là một functional interface có một abstract method.

### Constructor không tham số: `Supplier<T>`

```java
Supplier<Profile> factory = Profile::new;
Profile value = factory.get();
```

Khi `Profile` có constructor không tham số, `Supplier<Profile>.get()` không nhận argument và trả `Profile`. Compiler chọn constructor có thể dùng mà không truyền tham số.

### Constructor một tham số: `Function<A,R>`

```java
Function<String, Profile> byName = Profile::new;
Profile value = byName.apply("An");
```

Target type là `String -> Profile`. Compiler tìm constructor phù hợp với một `String` và kết quả có thể gán cho `Profile`.

### Constructor hai tham số: `BiFunction<A,B,R>`

```java
BiFunction<String, Integer, Profile> full = Profile::new;
Profile value = full.apply("Binh", 21);
```

Target type yêu cầu hai input: `String` và `Integer`. Constructor có thể khai báo `(String, int)`, và compiler dùng unboxing từ `Integer` sang `int` theo quy tắc overload/method invocation tương ứng.

Các đoạn code trên là **minh họa** với class `Profile` có các constructor phù hợp; ví dụ hoàn chỉnh ở mục 6 sẽ chứng minh kết quả thực tế.

### Nếu constructor cần ba hoặc nhiều tham số

JDK cung cấp `Supplier` (0), `Function` (1), `BiFunction` (2), cùng các interface đặc thù khác. Không có một interface chuẩn dạng `TriFunction` trong `java.util.function`. Khi cần constructor ba đối số, có thể định nghĩa interface có một abstract method:

```java
@FunctionalInterface
interface TriFactory<A, B, C, R> {
    R create(A a, B b, C c);
}
```

Sau đó, nếu class có constructor ba đối số tương thích, dùng `TriFactory<String, Integer, Boolean, RecordItem> factory = RecordItem::new;`. Đây là **minh họa**, với class `RecordItem` do ứng dụng tự định nghĩa và có constructor tương ứng.

**Không cố ép** một constructor ba tham số vào `BiFunction` nếu contract đích không có đủ input. Chọn chữ ký callback rõ ràng hoặc một named factory API phù hợp.

## 4. Overloaded constructor và target typing

Một class có thể định nghĩa nhiều constructor trùng tên nhưng khác số lượng hoặc loại tham số:

```java
class Profile {
    Profile() { /* default */ }
    Profile(String name) { /* name */ }
    Profile(String name, int age) { /* name + age */ }
}
```

Đây là **ví dụ minh họa**, không phải class hoàn chỉnh có method in dữ liệu. Cả ba constructor đều được tham chiếu bằng **cùng cú pháp** `Profile::new`; target type quyết định overload:

| Target type | Constructor phù hợp |
| --- | --- |
| `Supplier<Profile>` | `Profile()` |
| `Function<String,Profile>` | `Profile(String)` |
| `BiFunction<String,Integer,Profile>` | `Profile(String,int)` (có thể unbox). |

Nếu target không đủ thông tin hoặc có nhiều overload cùng phù hợp mà không có overload tối ưu duy nhất theo quy tắc Java, compiler sẽ báo lỗi **ambiguous**. Constructor reference không tự hiểu bạn định dùng overload nào theo tên biến.

Có thể giải quyết bằng cách **khai báo target type rõ ràng** hoặc viết lambda với kiểu parameter và lời gọi constructor tường minh khi cần điều khiển chuyển đổi:

```java
Function<String, Profile> explicit = name -> new Profile(name);
```

Một số biểu thức lambda/method reference ở vị trí gọi overload của method nhận nhiều functional interface cũng có thể mơ hồ. Hãy tách biến có kiểu cụ thể hoặc dùng type witness hợp lệ, thay vì cast unchecked.

**Cẩn trọng với `var`:** không thể viết `var maker = Profile::new;` rồi mong compiler tự chọn overload vì thiếu target functional interface. Có thể dùng `var maker = (Supplier<Profile>) Profile::new;` nhưng khai báo `Supplier<Profile>` trực tiếp thường dễ đọc hơn. `var` là cú pháp Java 10+, không phải phần cần thiết của Java 8.

## 5. Sự khác biệt giữa constructor reference và lambda

Khi lambda chỉ gọi constructor đúng với tham số được truyền vào, constructor reference thường ngắn gọn hơn:

```java
Function<String, Profile> a = s -> new Profile(s);
Function<String, Profile> b = Profile::new;
```

Hai dòng trên có cùng mục tiêu tạo `Profile` từ `String`. Nhưng constructor reference **không thay thế được tất cả lambda**.

Nếu cần chuẩn hóa input trước khi tạo object:

```java
Function<String, Profile> normalized =
        s -> new Profile(s.trim());
```

Bạn không thể thay bằng `Profile::new` mà vẫn giữ bước `trim()`; làm vậy đổi hành vi. Tương tự, khi có `if`, kiểm tra null, bắt exception, log thời gian hoặc tạo giá trị default theo điều kiện, lambda hay named factory method thường rõ hơn.

### Tham chiếu constructor không đồng nghĩa với static factory

`Profile::new` chọn **constructor**; `Profile::fromName` (nếu tồn tại) là **method reference** tới một static method. Hai thứ có thể cùng trả `Profile`, nhưng contract khác:

- Constructor reference gọi constructor có thể truy cập.
- Static factory có thể đặt tên nghiệp vụ rõ hơn, validate, cache, trả subtype hoặc ẩn lớp triển khai.
- Constructor reference không tự hỗ trợ singleton hoặc cache; nếu muốn policy tạo object khác, chuyển sang method reference của factory phù hợp.

Dùng constructor reference khi API thực sự cần **cấp phát/khởi tạo đối tượng theo constructor**, không ép mọi logic tạo object phải đi qua `::new`.

## 6. Chương trình chạy độc lập: overloaded, generic, array và Stream

Tạo tệp **`ConstructorReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ConstructorReferenceDemo {
    static final class Profile {
        private final String name;
        private final int age;

        Profile() {
            this("Guest", 0);
        }

        Profile(String name) {
            this(name, 0);
        }

        Profile(String name, int age) {
            this.name = Objects.requireNonNull(name);
            if (age < 0) {
                throw new IllegalArgumentException("age");
            }
            this.age = age;
        }

        @Override
        public String toString() {
            return name + ":" + age;
        }
    }

    static final class Box<T> {
        private final T item;
        Box(T item) { this.item = item; }
        T value() { return item; }
    }

    static <T> List<T> copy(List<? extends T> input,
                            Supplier<? extends List<T>> factory) {
        List<T> result = factory.get();
        result.addAll(input);
        return result;
    }

    public static void main(String[] args) {
        Supplier<Profile> guest = Profile::new;
        Function<String, Profile> named = Profile::new;
        BiFunction<String, Integer, Profile> full = Profile::new;
        System.out.println("guest=" + guest.get());
        System.out.println("named=" + named.apply("An"));
        System.out.println("full=" + full.apply("Binh", 21));

        Function<String, Box<String>> wrap = Box<String>::new;
        System.out.println("box=" + wrap.apply("OK").value());

        IntFunction<String[]> arrayFactory = String[]::new;
        String[] cells = arrayFactory.apply(3);
        cells[0] = "A";
        System.out.println("array=" + Arrays.toString(cells));

        List<Profile> profiles = Stream.of("Mai", "Lan")
                .map(Profile::new).collect(Collectors.toList());
        System.out.println("stream=" + profiles);

        List<String> names = copy(Arrays.asList("x", "y"), ArrayList::new);
        System.out.println("copy=" + names);

        IntFunction<ArrayList<String>> capacity = ArrayList::new;
        System.out.println("capacitySize=" + capacity.apply(5).size());
    }
}
```

Biên dịch và chạy với JDK 17+ (đoạn code trên chỉ sử dụng tính năng/API đã có trong Java 8):

```bash
javac ConstructorReferenceDemo.java
java ConstructorReferenceDemo
```

**Kết quả chuẩn:**

```text
guest=Guest:0
named=An:0
full=Binh:21
box=OK
array=[A, null, null]
stream=[Mai:0, Lan:0]
copy=[x, y]
capacitySize=0
```

Giải thích:

1. `guest`, `named` và `full` đều viết `Profile::new` nhưng ánh xạ tới các constructor **0, 1 và 2 tham số** theo target type khác nhau.
2. `Objects.requireNonNull(name)` và kiểm tra `age < 0` vẫn chạy trong constructor khi factory được gọi. Constructor reference **không bỏ qua validation**.
3. `Box<String>::new` thể hiện cách tham chiếu constructor của **generic class đã chỉ rõ type argument**. `wrap.apply("OK")` tạo một `Box<String>` và chứa `"OK"`.
4. `String[]::new` tạo mảng có chiều dài đúng theo đối số `int`; mảng reference khởi tạo các phần tử là `null`. Sau khi gán ô đầu thành `"A"`, kết quả là `[A, null, null]`.
5. `Stream.of(...).map(Profile::new)` áp dụng constructor cho từng tên khi **terminal operation** `collect` kích hoạt pipeline. Nó tạo hai `Profile` theo thứ tự dữ liệu của stream tuần tự này.
6. `copy(..., ArrayList::new)` dùng constructor không tham số để tạo danh sách đầu ra qua `Supplier`. Helper có `<T>` để liên kết kiểu phần tử nguồn, kết quả và collection.
7. `IntFunction<ArrayList<String>> capacity = ArrayList::new` chọn **constructor nhận `int initialCapacity`**. `capacity.apply(5).size()` bằng **0**, vì capacity ban đầu **không phải số phần tử**. Đây là nhầm lẫn quan trọng cần tránh.

**Ghi nhớ:** kết quả stdout phản ánh chính xác code, không nên giả định một constructor chỉ vì tên `::new` trông giống nhau.

## 7. Generic constructor reference và type inference

Generic làm constructor reference hữu ích cho những API nhận một **factory trừu tượng** thay vì phụ thuộc implementation cụ thể.

Trong chương trình chính:

```java
Function<String, Box<String>> wrap = Box<String>::new;
```

Khai báo `Box<T>` có một constructor nhận `T`. Cú pháp `Box<String>::new` gắn type argument `String` cho class và tạo callback có kiểu `String -> Box<String>`.

Ở một API generic:

```java
static <T> List<T> copy(
        List<? extends T> source,
        Supplier<? extends List<T>> factory)
```

`factory` phải tạo ra danh sách phù hợp với phần tử `T`. Một tham chiếu `ArrayList::new` có thể được suy luận thành supplier của `ArrayList<T>` và dùng tại đây mà không cần ép kiểu raw. `List<? extends T>` cho phép nhận nguồn chứa subtype của `T`.

**Không coi raw type và wildcard là tương đương.** `new Box()` hoặc `Box` không gắn type argument có thể mất kiểm tra kiểu và sinh warning. Dùng type parameter rõ ràng hoặc phép suy luận từ target type để giữ compile-time type safety.

Khi viết thư viện, nếu một callback chỉ có vai trò **tạo đối tượng kết quả**, kiểu `Supplier<? extends R>` thường là phù hợp. Nếu cần truyền đầu vào để tạo đối tượng, chọn `Function<? super A, ? extends R>` hoặc `BiFunction<? super A, ? super B, ? extends R>` theo contract. Dùng wildcard dựa vào hướng dữ liệu chứ không thêm tùy ý.

## 8. Constructor reference cho mảng: `T[]::new`

Khác với constructor thông thường của class, một **array constructor reference** có thể diễn đạt hành động cấp phát mảng theo **độ dài**:

```java
IntFunction<String[]> makeArray = String[]::new;
String[] values = makeArray.apply(3);
```

Target interface `IntFunction<String[]>` có SAM `String[] apply(int length)`. Khi gọi, một `String[3]` được tạo ra. Các phần tử của mảng reference được khởi tạo `null`; với mảng primitive như `int[]`, các phần tử được khởi tạo `0`.

Ví dụ mảng primitive:

```java
IntFunction<int[]> makeNumbers = int[]::new;
int[] numbers = makeNumbers.apply(2); // [0, 0]
```

Các đoạn trên là **minh họa trong method** với `import java.util.function.IntFunction;`. Nếu gọi với độ dài âm, việc cấp phát mảng gây `NegativeArraySizeException` tại lúc chạy, không phải tại lúc tạo reference.

Một use case hiện đại là API cần biết kiểu mảng trả về. Ví dụ, từ Java 11 có overload `Collection.toArray(IntFunction<T[]> generator)`, cho phép `collection.toArray(String[]::new)`. Với Java 8, `Stream.toArray(IntFunction<A[]> generator)` đã hỗ trợ cùng cách:

```java
String[] names = java.util.stream.Stream.of("A", "B")
        .toArray(String[]::new);
```

Đây là đoạn code runnable bên trong method (không cần class tự định nghĩa). Array generator nhận độ dài cần thiết và trả mảng đúng runtime component type.

**Không nhầm `String[]::new` với constructor của `String`.** Một bên tạo **mảng String[]**, bên kia `String::new` (khi có target type phù hợp) tạo **đối tượng String** qua constructor. Hai API khác nhau về cả đầu vào lẫn kiểu trả về.

## 9. Constructor reference trong Stream: khi nào thật sự tạo object?

Một Stream pipeline thường **lazy**: các intermediate operation như `map` chỉ mô tả bước xử lý, chưa chạy trước khi có terminal operation.

Ví dụ:

```java
Stream<String> words = Stream.of("Mai", "Lan");
Stream<Profile> pipeline = words.map(Profile::new);
// Chưa gọi terminal operation: constructor chưa được map thực thi.
List<Profile> result = pipeline.collect(Collectors.toList());
```

Đây là đoạn minh họa trong method có import `Stream`, `Collectors`, `List` và class `Profile` phù hợp. Khi `collect` chạy pipeline, constructor được gọi cho các phần tử thực sự được xử lý.

**Lưu ý về side effect và hiệu năng:**

- Tạo object có chi phí; không nên cấp phát vô ích khi một phép biến đổi thuần dữ liệu đã đủ.
- Đừng chèn side effect vào constructor chỉ để biết Stream chạy lúc nào; Stream có thể tối ưu pipeline hoặc có cách xử lý khác tùy terminal operation.
- Với parallel stream, constructor có thể được gọi trên nhiều thread và thứ tự tạo object không nên được dùng làm contract nghiệp vụ. Nếu constructor truy cập shared mutable state, phải thiết kế đồng bộ/kiểm thử phù hợp.
- `map(Profile::new)` chỉ làm việc khi constructor nhận đúng kiểu phần tử và trả kiểu phù hợp với kết quả `map`. Không phải mọi overload có thể được chọn tùy ý.

## 10. Giới hạn: accessibility, class không thể tạo, exception

### Constructor phải tồn tại và có thể truy cập

`Type::new` không vượt qua quy tắc access modifier. Nếu constructor `private` ở một class khác và lexical context không có quyền truy cập, reference sẽ không biên dịch. Constructor package-private, protected hoặc public cũng tuân thủ access rules bình thường.

Một interface hoặc abstract class không có constructor cụ thể để tạo instance theo `InterfaceType::new` hay `AbstractType::new`. Hãy tham chiếu constructor của **implementation class**:

```java
Supplier<List<String>> makeList = ArrayList::new;
```

Đây là minh họa có import `Supplier`, `List`, `ArrayList`. Bạn không thể viết `List::new` vì `List` là interface. Tương tự không tham chiếu constructor enum theo cách bình thường: việc tạo các hằng enum được Java quản lý theo các quy tắc riêng.

### Checked exception trong constructor

Nếu constructor khai báo `throws IOException`, callback được tham chiếu phải có **functional method tương thích với checked exception đó**. `Supplier<T>.get()` không khai báo checked exception, nên một constructor reference gọi constructor throws checked exception không thể gán trực tiếp cho `Supplier<T>` theo cách thông thường.

Một cách thiết kế là tạo functional interface mô tả exception:

```java
@FunctionalInterface
interface ThrowingFactory<T> {
    T create() throws java.io.IOException;
}
```

Đây là một interface riêng hoàn chỉnh; nếu class `Resource` có constructor `Resource() throws IOException` phù hợp và có thể truy cập, có thể viết `ThrowingFactory<Resource> resourceFactory = Resource::new;`.

Đừng dùng unchecked cast để "né" checked exception. Nếu API chỉ chấp nhận `Supplier`, hãy quyết định ở tầng adapter có nên bắt/đổi loại exception, hoặc thay đổi thiết kế để lỗi được truyền đúng contract.

### Runtime exception và validation

Ngay cả khi code biên dịch, constructor có thể ném `IllegalArgumentException`, `NullPointerException` hoặc exception khác khi được thực thi. Ví dụ chính kiểm tra `name` không null và `age` không âm. `Profile::new` **không tự kiểm tra giá trị trước khi gọi** và không biến lỗi thành `Optional` hoặc giá trị mặc định.

Nếu một factory là thành phần quan trọng của xử lý nghiệp vụ, hãy có contract rõ về input validation, exception và ownership/vòng đời của đối tượng được cấp phát.

## 11. Những lỗi thường gặp

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| Viết `User::new()` | Cú pháp constructor reference là `User::new`, không có `()` sau `new`. |
| Nghĩ `User::new` tạo đối tượng ngay | Chỉ tạo biểu thức hàm; constructor được thực thi khi SAM tương ứng được gọi. |
| Không khai báo target functional interface | `User::new` cần target type để suy luận chữ ký và chọn overload. |
| Cho rằng mọi `::new` chọn constructor không tham số | Chữ ký `Supplier`, `Function`, `BiFunction`, v.v. quyết định tham số của constructor. |
| Coi `ArrayList::new` với `IntFunction` là tạo sẵn N phần tử | Constructor `ArrayList(int)` cấp phát **initial capacity**, `size()` vẫn là 0. |
| Dùng `Interface::new` hoặc `Abstract::new` | Chỉ tham chiếu được construction expression hợp lệ; dùng constructor của implementation cụ thể. |
| Dùng `Supplier::get` cho constructor throws checked exception không xử lý | SAM phải tương thích với checked exception; dùng interface thích hợp hoặc adapter rõ ràng. |
| Thay lambda có validation/normalization bằng `Type::new` | Reference không tự thực hiện logic phụ của lambda; chỉ thay khi hành vi thực sự tương đương. |
| Nhầm `String[]::new` với `String::new` | Một bên tạo mảng String, một bên gọi constructor String. |
| Dựa vào thứ tự constructor chạy trong parallel Stream | Không nên dựa vào thứ tự đó; xây dựng code không có side effect phụ thuộc thứ tự. |
| Nhầm identity của functional object với object mới tạo | Việc reference được tối ưu/tái sử dụng không làm constructor trở thành singleton. |

## 12. Khi nào nên dùng và khi nào tránh?

**Nên dùng constructor reference** khi hành vi cần truyền đi đúng là *tạo object từ các đối số của SAM*, chữ ký constructor rõ, và bạn muốn dùng nó làm factory cho helper, Stream, dependency provider hoặc collection.

**Dùng lambda hoặc static factory** khi cần thực hiện thêm bước như chuẩn hóa đầu vào, chọn subtype theo điều kiện, cache, validation có nhánh, quản lý vòng đời, dependency lookup hoặc bắt/đổi exception.

**Ưu tiên thiết kế dễ kiểm thử:** thay vì gọi `new` rải rác trong logic khó thay thế, một method nhận `Supplier<T>` hoặc `Function<A,T>` có thể cho phép truyền constructor reference trong production và factory kiểm soát được trong test. Ví dụ `copy(..., ArrayList::new)` ở chương trình chính biểu diễn việc lựa chọn implementation thông qua supplier. Nhưng đừng lạm dụng abstraction factory cho một biểu thức đơn giản chỉ chạy tại chỗ.

## 13. Câu hỏi tự kiểm tra

**Câu 1:** `Person` có `Person()` và `Person(String)`. `Supplier<Person> a = Person::new` chọn cái nào? **Đáp án:** `Person()`, vì `Supplier.get()` không có tham số.

**Câu 2:** `Function<String,Person> a = Person::new` có chạy constructor tại dòng gán không? **Không.** Constructor được gọi khi `a.apply("An")` thực thi.

**Câu 3:** Có `Person(String,int)`. Dùng `BiFunction<String,Integer,Person>` được không? **Được**, nếu constructor có thể truy cập và không có ràng buộc khác khiến reference không tương thích; Java có thể unbox `Integer` sang `int`.

**Câu 4:** `IntFunction<ArrayList<String>> f = ArrayList::new; f.apply(100).size()` bằng bao nhiêu? **0**, vì 100 là *capacity*, không phải số phần tử.

**Câu 5:** Vì sao `Supplier<List<String>> factory = List::new` lỗi? **Vì `List` là interface**. Dùng `ArrayList::new` hoặc implementation phù hợp khác.

**Câu 6:** Với `Stream<String>`, `map(Person::new)` gọi constructor ngay khi viết `map`? **Không**; pipeline trung gian lazy, constructor chạy khi có terminal operation phù hợp.

**Câu 7:** Khi nào không nên đổi `s -> new Person(s.trim())` thành `Person::new`? **Khi muốn giữ bước `trim()`**, vì constructor reference không chứa phép chuẩn hóa đó.

## 14. Kết luận và tài liệu chính thức

**`Type::new` là factory expression có kiểu đích**, không phải lời gọi constructor tức thời. Số/loại tham số của SAM quyết định constructor nào được chọn; kết quả do constructor tạo ra phải tương thích với kiểu trả về của functional interface. Với class generic, cần giữ type argument hợp lệ; với mảng dùng `ArrayType::new` và target thích hợp như `IntFunction<T[]>`.

Khi dùng constructor reference trong hệ thống thực tế, hãy kiểm tra **target typing**, overload, khả năng truy cập constructor, checked exception, side effect và vòng đời object. Dùng lambda khi cần logic bổ sung, dùng static factory khi cần policy tạo object chuyên biệt. Đây đều là các nguyên tắc vẫn áp dụng trên Java hiện đại.

Nguồn tham khảo: [Java Language Specification §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.13), [JLS §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9), [java.util.function — package summary](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html), [Stream API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html).
