# Supplier<T>, Consumer<T>, Predicate<T> và Function<T,R> trong Java Generics

## 1. Tại sao Java cần bốn functional interfaces này?

Trong `java.util.function`, Java cung cấp các **functional interfaces** để đưa một hành vi thành giá trị: có thể lưu trong biến, truyền vào method, trả về từ method và kết hợp với lambda hoặc method reference.

Bốn interface quan trọng nhất có các vai trò khác nhau:

- **`Supplier<T>`**: cung cấp một giá trị T **không cần đối số**.
- **`Consumer<T>`**: nhận T và thực hiện hành động, **không trả kết quả**.
- **`Predicate<T>`**: nhận T rồi trả lời **đúng/sai** bằng primitive boolean.
- **`Function<T,R>`**: nhận T rồi **biến đổi thành R**.

Sơ đồ trực quan:

~~~text
Supplier<T>         () ───────→ T
Consumer<T>          T ───────→ void
Predicate<T>         T ───────→ boolean
Function<T,R>        T ───────→ R
~~~

Generic parameters cho phép compiler kiểm tra tính tương thích giữa dữ liệu và hành vi. Chẳng hạn, `Function<String,Integer>` nhận String và trả Integer; `Predicate<User>` kiểm tra User, chứ không phải một kiểu bất kỳ bị bỏ qua bằng raw type.

Ví dụ nhanh:

~~~java
Supplier<String> supplier = () -> "Java";
Consumer<String> consumer = System.out::println;
Predicate<String> predicate = s -> !s.isBlank();
Function<String, Integer> mapper = String::length;

String s = supplier.get();          // "Java"
boolean ok = predicate.test(s);    // true
int size = mapper.apply(s);        // 4
consumer.accept(s);                // In Java
~~~

Mảnh mã trên giả định import `java.util.function.*` và đặt trong method. Chương trình Java 17+ đầy đủ, lệnh biên dịch và stdout chính xác có ở phần 9.

## 2. Functional interface, SAM và target typing

**Functional interface** là interface có đúng một abstract method thích hợp theo quy tắc Java; nó có thể có nhiều default/static methods. Một lambda được chuyển thành implementation theo *target type* của functional interface.

Ví dụ tự định nghĩa:

~~~java
@FunctionalInterface
interface TextRule<T> {
    boolean matches(T value);
}
~~~

Cách dùng:

~~~java
TextRule<String> longText = value -> value.length() >= 5;
boolean result = longText.matches("Java"); // false
~~~

`@FunctionalInterface` giúp compiler kiểm tra declaration vẫn đáp ứng quy tắc SAM; annotation không bắt buộc để interface được dùng với lambda.

Các interface `Supplier`, `Consumer`, `Predicate`, `Function` có SAM khác nhau. Compiler suy ra kiểu tham số lambda từ phép gán hoặc tham số method:

~~~java
Predicate<String> a = s -> s.length() > 2;
Function<String, Boolean> b = s -> s.length() > 2;
~~~

Cùng một biểu thức lambda có thể được gán cho hai target types khác nhau, nhưng **Predicate không thay thế trực tiếp Function**: method contract và các phép kết hợp sẵn có khác nhau. `Predicate.test` trả primitive boolean; `Function.apply` ở ví dụ thứ hai trả boxed Boolean.

## 3. Bảng API nền tảng

| Interface | Abstract method | Hướng dữ liệu | Phép kết hợp tiêu biểu |
| --- | --- | --- | --- |
| `Supplier<T>` | `T get()` | Không có đầu vào → T | Không có `andThen` được định nghĩa sẵn. |
| `Consumer<T>` | `void accept(T t)` | T → hành động | `andThen` |
| `Predicate<T>` | `boolean test(T t)` | T → boolean | `and`, `or`, `negate`, `isEqual`, `not` |
| `Function<T,R>` | `R apply(T t)` | T → R | `compose`, `andThen`, `identity` |

Từ mục tiêu nghiệp vụ, hãy chọn:
- Tạo đối tượng/default value theo yêu cầu: Supplier.
- Ghi log, in, gửi notification, thao tác mang side effect: Consumer.
- Lọc hoặc xác thực điều kiện: Predicate.
- Trích xuất trường, chuẩn hóa và chuyển đổi object: Function.

Chúng là **hợp đồng của hành vi**, không phải lớp tự động đảm bảo purity, caching, concurrency hoặc tính hợp lệ của dữ liệu.

## 4. Supplier<T>: cung cấp giá trị đúng lúc get() được gọi

Phương thức:

~~~java
T get();
~~~

Ví dụ:

~~~java
Supplier<String> greeting = () -> "Xin chào";
String text = greeting.get();
~~~

Lambda `() -> ...` không có tham số. Việc tạo supplier **không thực thi ngay** thân lambda; computation xảy ra khi caller gọi `get()`.

### 4.1. Lazy evaluation không phải memoization

~~~java
AtomicInteger calls = new AtomicInteger();
Supplier<Integer> next = calls::incrementAndGet;

System.out.println(calls.get()); // 0
System.out.println(next.get());  // 1
System.out.println(next.get());  // 2
~~~

Mảnh mã cần `java.util.concurrent.atomic.AtomicInteger`. Hai lần `get()` tạo hai kết quả khác nhau. Supplier **không tự cache** kết quả hay chỉ chạy đúng một lần.

Nếu muốn lazy initialization có cache, phải tự thiết kế lưu kết quả và đồng bộ phù hợp nếu dùng nhiều thread. Supplier cũng không tự chạy trên thread riêng: mặc định `get()` là lời gọi đồng bộ.

### 4.2. Supplier giúp tránh phép tính không cần thiết

~~~java
static String choose(boolean fallbackNeeded,
                     Supplier<String> fallback) {
    return fallbackNeeded ? fallback.get() : "primary";
}
~~~

Nếu fallbackNeeded false, supplier không được gọi. Ngược lại, truyền sẵn một giá trị đã được tính thì phép tính đó xảy ra trước lời gọi:

~~~java
// Giả sử expensiveOperation() là method do ứng dụng định nghĩa.
Supplier<String> deferred = () -> expensiveOperation();
// String immediate = expensiveOperation();
~~~

Sự khác biệt nằm ở **thời điểm gọi** chứ không phải ở tốc độ tự nhiên của lambda.

### 4.3. Những API chuẩn dùng Supplier

`Optional.orElseGet(Supplier<? extends T>)` chỉ gọi supplier tạo fallback khi Optional không có giá trị:

~~~java
Optional<String> language = Optional.of("Java");
String name = language.orElseGet(() -> "fallback"); // "Java"
~~~

`Stream.generate(Supplier<T>)` dùng supplier để cung cấp các phần tử stream; thường nên dùng `limit` khi muốn lượng hữu hạn:

~~~java
List<String> values = Stream.generate(() -> "A")
        .limit(3)
        .toList(); // [A, A, A]
~~~

Các ví dụ cần import `java.util.Optional`, `java.util.stream.Stream` và `java.util.List` tương ứng. Stream có cơ chế lazy pipeline của riêng nó; không nên nhầm với thời điểm thực thi `Supplier.get()`.

## 5. Consumer<T>: hành động nhận đầu vào nhưng không trả giá trị

SAM:

~~~java
void accept(T value);
~~~

Ví dụ:

~~~java
Consumer<String> print = System.out::println;
print.accept("Java");
~~~

`Consumer` phù hợp với ghi log, gửi sự kiện, cập nhật trạng thái và terminal operation của collection. Lời gọi `accept` trả `void`, do đó:

~~~java
// String result = print.accept("Java"); // Không biên dịch.
~~~

Nếu cần kết quả String được tạo ra, hãy dùng `Function<T,R>`.

### 5.1. Consumer.andThen chạy theo thứ tự

~~~java
Consumer<String> audit =
        s -> System.out.println("audit=" + s);
Consumer<String> send =
        s -> System.out.println("send=" + s);

audit.andThen(send).accept("done");
~~~

Đầu ra:

~~~text
audit=done
send=done
~~~

`andThen` chuyển **cùng đầu vào** qua cả hai consumer. Consumer thứ hai chỉ được gọi khi consumer đầu hoàn thành bình thường; nếu consumer đầu ném exception, bước sau không được thực hiện. API yêu cầu `after` không null.

### 5.2. Consumer trong collection và stream

~~~java
List.of("A", "B").forEach(System.out::println);

Stream.of("A", "B")
        .forEachOrdered(System.out::println);
~~~

`Iterable.forEach` và `Stream.forEach` nhận Consumer. `forEachOrdered` giúp duy trì encounter order của stream khi điều đó có ý nghĩa; `parallelStream().forEach` có thể không thực hiện các side effects theo thứ tự mong đợi.

Một Consumer **có thể** thay đổi state, nên tránh dùng nó để thêm đồng thời vào một `ArrayList` chia sẻ không đồng bộ trong parallel stream. Nếu muốn thu thập kết quả, ưu tiên `collect` hoặc `toList` thay vì lạm dụng side effects.

## 6. Predicate<T>: điều kiện trả boolean

SAM:

~~~java
boolean test(T value);
~~~

Ví dụ:

~~~java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;

boolean a = positive.test(4); // true
boolean b = even.test(5);     // false
~~~

Predicate có **boolean primitive return** và các default methods giúp kết hợp logic mà không cần tự viết một lambda dài cho mọi điều kiện.

### 6.1. and và or có short-circuit

~~~java
Predicate<String> present = s -> s != null;
Predicate<String> longEnough = s -> s.length() >= 3;

Predicate<String> valid = present.and(longEnough);
boolean result = valid.test(null); // false; không gọi longEnough.
~~~

`and` chỉ gọi predicate thứ hai khi predicate thứ nhất true. Với `or`, bước thứ hai chỉ chạy khi bước đầu false:

~~~java
Predicate<Integer> negative = n -> n < 0;
Predicate<Integer> zero = n -> n == 0;

Predicate<Integer> nonPositive = negative.or(zero);
boolean yes = nonPositive.test(0); // true
~~~

Thứ tự quan trọng nếu điều kiện sau có thể ném exception hoặc có side effects. Khi kiểm tra null, nên đặt điều kiện `s != null` trước `s.length()`.

### 6.2. negate, isEqual và not

~~~java
Predicate<String> blank = String::isBlank;
Predicate<String> notBlank = blank.negate();

boolean a = notBlank.test("Java"); // true

Predicate<String> isJava = Predicate.isEqual("Java");
boolean b = isJava.test("Java");    // true
~~~

`isEqual` sử dụng quy tắc so sánh giá trị thích hợp, bao gồm xử lý null theo hợp đồng.

Java 11+ còn có `Predicate.not`:

~~~java
List<String> nonBlanks = Stream.of("A", "", "B")
        .filter(Predicate.not(String::isBlank))
        .toList(); // [A, B]
~~~

Nếu nguồn chứa null, method reference `String::isBlank` vẫn có thể ném NullPointerException; `Predicate.not` không phải null validator.

### 6.3. Predicate phù hợp với filter và validation

~~~java
List<Integer> adults = List.of(16, 22, 30)
        .stream()
        .filter(age -> age >= 18)
        .toList(); // [22, 30]
~~~

Predicate thường nên biểu diễn một điều kiện, không tạo side effects. Tránh dựa vào số lần predicate được gọi hoặc thứ tự thực thi khi stream implementation có thể tối ưu pipeline.

## 7. Function<T,R>: nhận T và tạo R

SAM:

~~~java
R apply(T value);
~~~

Ví dụ:

~~~java
Function<String, Integer> length = String::length;
Integer size = length.apply("Java"); // 4
~~~

Trong `Function<String,Integer>`, đầu vào là String và đầu ra là Integer. `String.length()` trả int, được boxing thành Integer để đáp ứng generic return type.

Sử dụng Function khi:
- Biến entity thành DTO.
- Trích thuộc tính object.
- Chuẩn hóa chuỗi.
- Chuyển kiểu chuỗi thành số, ngày hay enum.
- Xử lý `Stream.map`.

~~~java
List<Integer> lengths = List.of("Java", "Go")
        .stream()
        .map(String::length)
        .toList(); // [4, 2]
~~~

### 7.1. andThen: phép sau chạy sau

~~~java
Function<String, Integer> length = String::length;
Function<Integer, Integer> square = n -> n * n;

Function<String, Integer> f = length.andThen(square);
int result = f.apply("java"); // 16
~~~

Thứ tự là:

~~~text
"java" → length → 4 → square → 16
~~~

### 7.2. compose: phép trước chạy trước

~~~java
Function<String, Integer> length = String::length;
Function<Integer, Integer> square = n -> n * n;

Function<String, Integer> f = square.compose(length);
int result = f.apply("abc"); // 9
~~~

Thứ tự:

~~~text
"abc" → length → 3 → square → 9
~~~

Đọc `A.andThen(B)` là A rồi B, còn `B.compose(A)` cũng là A rồi B. Khi các kiểu khác nhau, compiler giúp ngăn ghép sai; khi các function cùng kiểu, một lỗi đảo thứ tự đôi khi vẫn biên dịch được nhưng cho kết quả khác.

### 7.3. identity

~~~java
Function<String, String> same = Function.identity();
String value = same.apply("ok"); // "ok"
~~~

`identity()` trả lại đầu vào mà không biến đổi; có ích trong API cần Function nhưng không có bước chuyển đổi thực tế.

### 7.4. Function không tự bảo đảm purity

Một Function có thể đọc/chỉnh sửa state hoặc ném unchecked exception. Interface chỉ xác định hình dạng `T→R`, không hứa kết quả bất biến, không cache hay tự xử lý lỗi. Trong streams, ưu tiên lambda dễ hiểu và không phụ thuộc mutable shared state.

## 8. Ghép bốn interface thành pipeline Java

Một luồng xử lý có thể là:

~~~text
Supplier<List<User>>
        │ get()
        ▼
List<User> → stream()
                  │ filter(Predicate<User>)
                  ▼
                 User
                  │ map(Function<User,String>)
                  ▼
                String
                  │ accept(Consumer<String>)
                  ▼
             Tác vụ cuối
~~~

Ví dụ: Supplier tạo danh sách User; Predicate giữ người trưởng thành; Function chuẩn hóa tên; Consumer in từng tên.

Trong Java 17, có thể định nghĩa:

~~~java
record User(String name, int age) {}
~~~

Compiler kiểm tra từng bước của pipeline. `filter` phải nhận Predicate dùng được với User; `map` phải chấp nhận User và có kết quả String; `forEachOrdered` truyền String tới Consumer<String>.

Đây là lợi ích của generics: **ràng buộc kiểu đầu vào/đầu ra giữa các hành vi được ghép** mà không cần cast thủ công.

## 9. Chương trình Java 17+ hoàn chỉnh và kiểm tra output

Lưu nội dung sau thành tệp **FunctionalInterfacesDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class FunctionalInterfacesDemo {
    record User(String name, int age) {}

    public static void main(String[] args) {
        Supplier<List<User>> source = () -> List.of(
                new User(" Lan ", 22),
                new User("Minh", 16),
                new User("An", 30)
        );

        Predicate<User> adult = user -> user.age() >= 18;
        Predicate<User> named = user -> !user.name().isBlank();

        Function<User, String> cleanName =
                user -> user.name().trim();
        Function<String, String> upper = String::toUpperCase;

        Consumer<String> print =
                name -> System.out.println("user=" + name);

        source.get().stream()
                .filter(adult.and(named))
                .map(cleanName.andThen(upper))
                .forEachOrdered(print);

        System.out.println(
                "minor=" +
                adult.negate().test(new User("Minh", 16))
        );

        Function<String, Integer> length = String::length;
        Function<Integer, Integer> square = n -> n * n;

        System.out.println(
                "compose=" +
                square.compose(length).apply("abc")
        );
        System.out.println(
                "andThen=" +
                length.andThen(square).apply("java")
        );
        System.out.println(
                "identity=" +
                Function.<String>identity().apply("ok")
        );
        System.out.println(
                "isEqual=" +
                Predicate.isEqual("An").test("An")
        );

        Consumer<String> audit =
                s -> System.out.println("audit=" + s);
        Consumer<String> send =
                s -> System.out.println("send=" + s);

        audit.andThen(send).accept("done");

        AtomicInteger calls = new AtomicInteger();
        Supplier<Integer> next = calls::incrementAndGet;

        System.out.println("before=" + calls.get());
        System.out.println("next=" + next.get());
        System.out.println("next=" + next.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -Xlint:all FunctionalInterfacesDemo.java
java FunctionalInterfacesDemo
~~~

Stdout **chính xác**:

~~~text
user=LAN
user=AN
minor=true
compose=9
andThen=16
identity=ok
isEqual=true
audit=done
send=done
before=0
next=1
next=2
~~~

### Giải thích output

1. `source.get()` đưa ba User. `adult.and(named)` giữ Lan và An vì họ từ 18 tuổi trở lên; Minh 16 tuổi bị lọc.
2. `cleanName.andThen(upper)` bỏ khoảng trắng rồi viết hoa; `forEachOrdered` in LAN trước AN theo encounter order.
3. `adult.negate()` cho biết Minh là người chưa trưởng thành: true.
4. `square.compose(length)` tính 3 rồi bình phương thành 9; `length.andThen(square)` tính 4 rồi bình phương thành 16.
5. `Function.identity()` giữ nguyên "ok"; `Predicate.isEqual("An")` nhận diện chuỗi "An".
6. `audit.andThen(send)` thực hiện hai hành động theo thứ tự.
7. `before=0` chứng minh tạo Supplier chưa tăng counter; hai lần `get()` tiếp theo lần lượt trả 1 và 2.

Chương trình dùng tên không dấu để ví dụ viết hoa đơn giản và kết quả ổn định trong bối cảnh chạy thông thường. Trong hệ thống quốc tế hóa, nên xét rõ `Locale` cho các phép chuyển chữ hoa/thường.

## 10. Method references và suy luận kiểu

Các cách viết:

~~~java
Function<String, Integer> a = s -> s.length();
Function<String, Integer> b = String::length;

Consumer<String> printer = System.out::println;
Predicate<String> blank = String::isBlank;
Supplier<List<String>> listFactory = ArrayList::new;
~~~

đều hợp lệ nếu import những class cần thiết. Target functional interface quyết định kiểu phù hợp của method reference.

Các nhóm method references thường gặp:

| Dạng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Class::staticMethod` | `Integer::parseInt` | Gọi static method. |
| `object::instanceMethod` | `System.out::println` | Gọi trên object cụ thể. |
| `Class::instanceMethod` | `String::length` | Tham số đầu là receiver. |
| `Class::new` | `ArrayList::new` | Tạo object bằng constructor. |

Lambda thường dễ đọc hơn khi logic cần nhiều bước, biến trung gian hoặc kiểm tra lỗi. Method reference thường gọn hơn khi chỉ chuyển tiếp đến một method rõ nghĩa.

### Truyền một Function vào generic method

~~~java
static <T, R> R transform(
        T value, Function<? super T, ? extends R> function) {
    return function.apply(value);
}
~~~

Sử dụng:

~~~java
Integer result = transform("Java", String::length); // 4
~~~

Compiler suy luận kiểu T/R từ value, target và method reference. `? super T` giúp chấp nhận function tiêu thụ supertype của T; `? extends R` giúp chấp nhận function trả subtype của R.

## 11. Wildcards, variance và quy tắc PECS

Các functional interfaces chuẩn cũng cần **đúng chiều của dữ liệu**. Java generic invariance khiến `Consumer<Number>` không tự là `Consumer<Integer>`, nhưng wildcard trong API có thể biểu đạt quan hệ sử dụng an toàn:

~~~java
Consumer<Number> printNumber = System.out::println;
Consumer<? super Integer> acceptInteger = printNumber;
acceptInteger.accept(42);

Supplier<Integer> integerSource = () -> 7;
Supplier<? extends Number> numberSource = integerSource;
Number value = numberSource.get();
~~~

- `Consumer` nhận **đầu vào**: `? super T` cho phép callback nhận cả supertype của `T`.
- `Supplier` tạo **đầu ra**: `? extends R` cho phép callback sản xuất subtype của `R`.
- `Function` vừa nhận `T` vừa trả `R`, vì vậy những API biến đổi có thể nhận `Function<? super T, ? extends R>`.

Đây là PECS (*Producer Extends, Consumer Super*), một gợi ý về hướng dữ liệu chứ không biến generic types thành covariant. Bài kế tiếp phân tích **chữ ký thực** của `Stream.map`, `Comparator`, `Predicate` và việc dùng callback với kiểu cha/con; ở đây chỉ cần nhận diện chiều consumer/producer của bốn interface.

## 12. Những biến thể dành cho primitive

Generics dùng reference types, nên `Function<String,Integer>` và `Predicate<Integer>` có thể phát sinh boxing/unboxing. Java có các functional interfaces chuyên biệt:

| Mục tiêu | Interface | Method |
| --- | --- | --- |
| Cung cấp int | `IntSupplier` | `getAsInt()` |
| Xử lý int | `IntConsumer` | `accept(int)` |
| Kiểm tra int | `IntPredicate` | `test(int)` |
| int → int | `IntUnaryOperator` | `applyAsInt(int)` |
| int → long | `IntToLongFunction` | `applyAsLong(int)` |
| T → int | `ToIntFunction<T>` | `applyAsInt(T)` |
| int → R | `IntFunction<R>` | `apply(int)` |

Ví dụ:

~~~java
IntSupplier answer = () -> 21;
IntUnaryOperator doubleIt = n -> n * 2;
IntPredicate even = n -> n % 2 == 0;

int value = doubleIt.applyAsInt(answer.getAsInt()); // 42
boolean yes = even.test(value); // true
~~~

Các class ở `java.util.function` và thích hợp khi làm việc với `IntStream`, `LongStream`, `DoubleStream`. Điều đó không có nghĩa boxing luôn là vấn đề hiệu năng nghiêm trọng: nên đo đạc trước khi tối ưu đường xử lý thực tế.

Cú pháp `Supplier<int>` hay `Function<int,int>` không hợp lệ: type arguments của generics thông thường phải là reference types.

## 13. Các lỗi thường gặp

### 13.1. Dùng Supplier khi cần nhận tham số

~~~java
// Supplier<String> wrong = name -> "Hello " + name;
Function<String, String> correct = name -> "Hello " + name;
~~~

Supplier không có tham số; Function có một đầu vào.

### 13.2. Dùng Consumer rồi mong lấy kết quả

~~~java
Consumer<String> print = System.out::println;
// String result = print.accept("Java"); // Không biên dịch.
~~~

`accept` trả void. Dùng Function nếu cần giá trị mới.

### 13.3. Lẫn Predicate với Function<T,Boolean>

~~~java
Predicate<String> nonBlank = s -> !s.isBlank();
Function<String, Boolean> sameCondition = s -> !s.isBlank();
~~~

Chúng biểu diễn điều kiện tương tự nhưng API khác: Predicate có `and/or/negate` và trả primitive boolean; Function có `compose/andThen` và trả boxed Boolean.

### 13.4. Đảo chiều compose và andThen

Nên viết hướng dữ liệu:

~~~text
"A" -> normalize -> parse -> calculate
~~~

rồi ghép từ đầu ra của bước trước vào đầu vào của bước sau. Với các Function đồng kiểu, thứ tự sai đôi khi vẫn compile nhưng cho sai kết quả.

### 13.5. Predicate truy cập giá trị null

~~~java
Predicate<String> longer = s -> s.length() >= 3;
// longer.test(null); // NullPointerException.
~~~

Một cách an toàn:

~~~java
Predicate<String> present = s -> s != null;
Predicate<String> safe = present.and(s -> s.length() >= 3);
~~~

Bước thứ hai không được gọi nếu bước đầu false.

### 13.6. Cho rằng Supplier tự cache hoặc chạy async

Supplier chỉ cung cấp `get`. Implementation có thể tính lại, lưu cache hoặc gọi một hệ thống ngoài, nhưng không có hành vi nào trong số đó được interface tự cung cấp.

### 13.7. Side effects trong parallel streams

~~~java
List<String> output = new ArrayList<>();
// source.parallelStream().forEach(output::add);
~~~

Đây là ý tưởng không an toàn nếu output là ArrayList chia sẻ không đồng bộ. Dùng collectors hoặc một thiết kế concurrency phù hợp. Predicate/Function/Consumer không tự làm mutable state trở thành thread-safe.

### 13.8. Checked exception trong lambda

SAM của bốn interface chuẩn không khai báo checked exceptions. Một lambda ném IOException chưa xử lý thường không thể gán trực tiếp cho `Function<T,R>` hoặc `Consumer<T>` tương ứng. Có thể catch/wrap phù hợp hoặc định nghĩa functional interface riêng với `throws E` nếu hợp đồng cần giữ checked exceptions.

### 13.9. Tái sử dụng stream đã kết thúc

Stream không phải collection có thể thực hiện terminal operations lặp đi lặp lại. Sau `forEach`, `toList` hoặc terminal operation khác, không nên sử dụng lại cùng stream. Nếu cần tạo stream mới mỗi lần, một `Supplier<Stream<T>>` có thể phù hợp:

~~~java
Supplier<Stream<String>> fresh =
        () -> Stream.of("Java", "Go");

long first = fresh.get().count();   // 2
long second = fresh.get().count();  // 2
~~~

Ở đây supplier tạo **stream mới cho mỗi lần get**, tránh tái sử dụng stream đã tiêu thụ.

## 14. Thiết kế API nhỏ sử dụng cả bốn interface

Một method generic có thể nhận bốn hành vi tách biệt:

~~~java
static <T, R> void process(
        Supplier<? extends T> loader,
        Predicate<? super T> accepted,
        Function<? super T, ? extends R> mapper,
        Consumer<? super R> sink) {

    T value = loader.get();

    if (accepted.test(value)) {
        sink.accept(mapper.apply(value));
    }
}
~~~

Ví dụ:

~~~java
process(
        () -> " Java ",
        text -> !text.isBlank(),
        String::trim,
        System.out::println
);
~~~

Đầu ra là `Java`. Mỗi bước có trách nhiệm rõ ràng: cung cấp, kiểm tra, biến đổi, xử lý cuối. Có thể thay từng lambda bằng implementation thử nghiệm để kiểm tra nhánh đúng/sai hoặc số lần gọi mà không cần thay body của `process`.

### Kiểm thử nhánh bị từ chối

~~~java
AtomicInteger sent = new AtomicInteger();

process(
        () -> "A",
        text -> false,
        String::trim,
        text -> sent.incrementAndGet()
);

System.out.println(sent.get()); // 0
~~~

Predicate trả false nên mapper/sink không chạy. Method này đồng bộ và chỉ gọi Supplier một lần; nó không tự có retry, async execution hoặc transaction semantics.

## 15. Khi nào không nên dùng bốn interface này?

Chúng đủ cho nhiều API nhỏ, nhưng có trường hợp cần loại khác:

- Hai đầu vào, một kết quả: `BiFunction<T,U,R>`.
- Hai đầu vào, không kết quả: `BiConsumer<T,U>`.
- Hai đầu vào, trả boolean: `BiPredicate<T,U>`.
- T → T: `UnaryOperator<T>`.
- Hai T → T: `BinaryOperator<T>`.
- Callback ném checked exception cụ thể: functional interface tự định nghĩa với `throws E`.
- Hợp đồng miền nghiệp vụ có tên rõ như `AuthorizationRule` hoặc `PricePolicy`, đặc biệt khi một tên có ý nghĩa giúp API dễ đọc hơn `Function` tổng quát.

Không cần tự viết interface thay thế `Supplier<T>` nếu nó không mang thêm hợp đồng. Ngược lại, cũng đừng ép logic miền nghiệp vụ quan trọng thành lambda vô danh khó kiểm thử và khó tìm khi debug.

## 16. Checklist áp dụng trong Java thực tế

1. **Xác định số đầu vào và loại đầu ra** trước khi chọn interface.
2. **Giữ generic type arguments** thay vì dùng raw `Function` hay raw `Predicate`.
3. **Dùng method reference hợp lý** để làm rõ ý định, nhưng lambda nhiều bước vẫn thích hợp khi cần logic cụ thể.
4. **Kiểm tra hướng compose/andThen** bằng sơ đồ T→R.
5. **Lưu ý short-circuit** của Predicate.and/or; điều kiện thứ hai có thể không chạy.
6. **Quy định null policy** của từng bước, đặc biệt khi dùng method reference trên object.
7. **Không giả định purity**; mặc dù nên giảm side effects ở Predicate/Function, interface không bắt buộc làm vậy.
8. **Không giả định laziness/caching/async** ngoài những gì Supplier và stream API thực sự cam kết.
9. **Xét wildcard variance** khi thiết kế method generic nhận function của supertype hoặc supplier trả subtype.
10. **Không dùng shared mutable state thiếu đồng bộ** trong consumer của parallel stream.
11. **Chọn primitive specializations** trong đường xử lý primitive khi API và performance yêu cầu.
12. **Dùng compiler với source release mục tiêu**, ví dụ `javac --release 17`, và kiểm tra stdout xác định thay vì dựa vào thứ tự không được API hứa.

## 17. Câu hỏi tự kiểm tra

**1.** Nếu một lambda không có tham số, trả String, chọn interface nào?

**Đáp án:** `Supplier<String>` với `String get()`.

**2.** Muốn log một String mà không tạo kết quả, dùng gì?

**Đáp án:** `Consumer<String>` với `void accept(String)`.

**3.** Muốn giữ User có tuổi từ 18 trở lên bằng `Stream.filter`, dùng gì?

**Đáp án:** `Predicate<User>`, ví dụ `u -> u.age() >= 18`.

**4.** Muốn đổi một User thành String, dùng gì?

**Đáp án:** `Function<User,String>`.

**5.** `Predicate.and` có luôn thực hiện cả hai điều kiện không?

**Đáp án:** Không. Nó short-circuit khi điều kiện đầu false.

**6.** `Consumer.andThen` thực hiện gì khi consumer đầu ném exception?

**Đáp án:** Exception được chuyển tiếp; consumer sau không được thực hiện trên lời gọi đó.

**7.** `length.andThen(square)` và `square.compose(length)` có cùng chiều xử lý không?

**Đáp án:** Có. Cả hai thực hiện length trước rồi square.

**8.** Supplier có tự memoize không?

**Đáp án:** Không. `get()` có thể trả kết quả mới ở mỗi lần gọi.

**9.** `Function.identity()` có ý nghĩa gì?

**Đáp án:** Trả lại giá trị đầu vào, không chuyển đổi.

**10.** Vì sao `Supplier<Integer>` và `IntSupplier` không hoàn toàn giống nhau?

**Đáp án:** Supplier<Integer> trả boxed Integer qua get; IntSupplier trả primitive int qua getAsInt.

**11.** Vì sao một `Consumer<Number>` có thể dùng ở vị trí `Consumer<? super Integer>`?

**Đáp án:** Consumer<Number> xử lý được Integer vì Integer là subtype của Number; `? super Integer` biểu diễn đúng hướng nhận đầu vào.

**12.** Vì sao không nên gọi `parallelStream().forEach(list::add)` nếu list là ArrayList dùng chung?

**Đáp án:** Consumer không cung cấp thread safety và ArrayList không an toàn cho nhiều lần thêm đồng thời không đồng bộ.

## 18. Tổng kết

Bốn interface chuẩn có thể ghi nhớ theo **chiều dữ liệu**:

~~~text
Supplier<T>   = lấy T             → get()
Consumer<T>   = làm việc với T    → accept(T)
Predicate<T>  = hỏi T đúng không  → test(T)
Function<T,R> = chuyển T thành R  → apply(T)
~~~

Chúng cung cấp hợp đồng hành vi có kiểm tra kiểu, làm nền cho lambda, method reference, collection, stream, Optional và nhiều APIs hiện đại.

Điều quan trọng là hiểu **SAM và type inference**, **sự khác nhau giữa hành động và kết quả**, **short-circuit**, **thứ tự compose/andThen**, **hướng wildcards**, và giới hạn thực tế: Supplier không tự cache; Consumer có side effects cần kiểm soát; Predicate/Function không bắt buộc pure; không interface nào tự cung cấp thread safety hoặc xử lý checked exceptions.

Chọn đúng interface giúp code Java dễ đọc, dễ test, linh hoạt khi ghép chức năng và an toàn kiểu hơn.
