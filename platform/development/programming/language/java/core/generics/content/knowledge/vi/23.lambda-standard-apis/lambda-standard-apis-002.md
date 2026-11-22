# Phương thức của API nhận `? super T` hoặc `? extends R`: Lambda và Java Generics

## Mục tiêu bài học

Khi đọc Java Standard API, bạn thường gặp các chữ ký dạng:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

Đây không phải cách viết rườm rà ngẫu nhiên. Hai wildcard **`? super T`** và **`? extends R`** khiến phương thức chấp nhận nhiều callback hợp lệ hơn nhưng vẫn giữ tính an toàn kiểu.

Sau bài học, bạn có thể:

- Đọc một cách chính xác `Function<? super T, ? extends R>` theo **hướng tiêu thụ đầu vào** và **hướng tạo đầu ra**.
- Giải thích vì sao `Function<Animal, StringBuilder>` có thể truyền vào một hàm đang biến đổi `Dog` thành `CharSequence`.
- Hiểu **contravariance** ở đầu vào, **covariance** ở đầu ra và phân biệt với **invariance** của `Function<A,B>`/generics Java thông thường.
- Đọc các chữ ký phổ biến của `Stream.map`, `Stream.flatMap`, `Stream.filter`, `Iterable.forEach`, `List.sort`, `Function.compose`, `Function.andThen`, `Consumer.andThen` và `Predicate.and/or`.
- Biết khi nào wildcard thuộc tham số callback, khi nào thuộc collection, và tại sao không nên thay chúng bằng raw types.
- Viết một generic API riêng kết hợp `List<? extends T>` và `Function<? super T, ? extends R>`.
- Đọc lỗi compiler, khắc phục vấn đề type inference, chọn lambda hoặc method reference phù hợp.
- Nhận biết giới hạn: wildcard **mở rộng loại callback được nhận**, không tự đổi `Consumer<T>` thành một loại generic khác, cũng không thêm runtime subtype checks mới.

Các ví dụ hoàn chỉnh ở đây sử dụng **Java 17 trở lên**, đã được biên dịch bằng `javac -Xlint:all` và chạy để kiểm chứng stdout. Các đoạn mã được ghi là “minh họa” cần đặt trong lớp/method phù hợp, không phải chương trình độc lập.

## 1. Đầu tiên, hiểu `Function<T,R>`

`Function<T,R>` biểu diễn một phép biến đổi với **một đầu vào `T` và một kết quả `R`**; abstract method là `R apply(T value)`. Ví dụ:

```java
Function<String, Integer> length = String::length;
Integer count = length.apply("Java"); // 4
```

Điều cần cho **chữ ký API callback** là phân biệt hướng dùng: caller đưa vào một `T`, còn callback có thể chấp nhận kiểu **cha của `T`**; caller lấy ra một `R`, còn callback có thể tạo kiểu **con của `R`**. Vì thế mẫu rộng hơn là:

```java
Function<? super T, ? extends R>
```

Tình huống `Dog extends Animal` và `StringBuilder implements CharSequence` ở phần tiếp theo chứng minh cả hai phía đồng thời; không chỉ nhắc lại bảng bốn interfaces của bài mở đầu.

## 2. Vì sao `Function<Animal, StringBuilder>` dùng được cho `Dog -> CharSequence`?

Giả sử có quan hệ kế thừa:

```text
    Object                  CharSequence
      |                          ^
    Animal                        |
      ^                      StringBuilder
      |
     Dog
```

`Dog extends Animal`, và `StringBuilder implements CharSequence`.

Bây giờ callback:

```java
Function<Animal, StringBuilder> label =
        animal -> new StringBuilder(animal.name());
```

Hàm này nhận **mọi `Animal`**, nên chắc chắn nhận được `Dog`. Nó trả `StringBuilder`, và một `StringBuilder` có thể dùng như `CharSequence`. Vì vậy, trong ngữ cảnh `T = Dog`, `R = CharSequence`, callback ấy thỏa:

```java
Function<? super Dog, ? extends CharSequence>
```

Không cần viết lại thành một `Function<Dog, CharSequence>` chỉ để chiều kiểu “vừa khít”.

Bảng:

| Thành phần của callback | Loại thực tế | Kiểu API yêu cầu | Vì sao hợp lệ? |
| --- | --- | --- | --- |
| Đầu vào | `Animal` | `? super Dog` | `Animal` là supertype của `Dog` |
| Đầu ra | `StringBuilder` | `? extends CharSequence` | `StringBuilder` triển khai `CharSequence` |
| Callback đầy đủ | `Function<Animal,StringBuilder>` | `Function<? super Dog,? extends CharSequence>` | Cả hai hướng an toàn |

**Không được đảo hướng:**

- Callback chỉ nhận `Dog` **không** dùng được để xử lý tất cả `Animal`, vì có thể gặp `Cat`.
- Callback chỉ cam kết trả `Object` **không** tự dùng được ở nơi cần `String`, vì `Object` có thể không phải `String`.

Wildcard không “ép” một đối tượng thành subtype thích hợp. Nó mô tả các **quan hệ kiểu an toàn** đã được compiler chứng minh.

## 3. Nguyên tắc PECS cho một functional interface hai tham số kiểu

Quy tắc học nhanh **PECS — Producer Extends, Consumer Super**:

- **`? super T`**: một thành phần **tiêu thụ** các giá trị `T` (consumer) được phép nhận một supertype của `T`.
- **`? extends R`**: một thành phần **cung cấp** các giá trị dùng như `R` (producer) có thể trả một subtype của `R`.

Với `Function<A,B>`, `A` ở vị trí tham số của `apply` nên nó là đầu vào, còn `B` là kết quả của `apply` nên là đầu ra.

```text
T của API  -----(đưa vào)----->  Function<? super T, ? extends R>
                                             |
                                             | apply(T)
                                             v
R của API  <----(nhận về)------  giá trị là R hoặc subtype R
```

Lưu ý: “consumer” và “producer” ở đây mô tả **vai trò của một vị trí kiểu trong lời gọi**, không có nghĩa một `Function` chỉ là `Consumer` hoặc chỉ là `Supplier`. Function vừa nhận đầu vào vừa trả đầu ra, do đó **hai wildcard có thể đi theo hai hướng khác nhau**.

Một lỗi diễn giải thường gặp là chỉ nhìn từ ngữ pháp `extends`/ `super` mà bỏ qua vị trí sử dụng. Hãy nhìn method `R apply(T value)`: đầu vào đi vào hàm, kết quả đi ra khỏi hàm. Hướng dữ liệu quyết định hướng wildcard.

## 4. Vì sao không viết `Function<T,R>` đơn giản?

Chữ ký sau hợp lệ nhưng **quá hạn chế** nếu API muốn nhận callback có đầu vào hoặc đầu ra khác ở mức kế thừa:

```java
static <T, R> R strictApply(T item, Function<T, R> mapper) {
    return mapper.apply(item);
}
```

Đây là đoạn method minh họa và cần import `Function`.

Mặc định Java generics **invariant**. Điều đó có nghĩa dù `Dog extends Animal` thì:

```java
// Function<Animal, StringBuilder> callback = ...;
// Function<Dog, CharSequence> exact = callback; // Không biên dịch.
```

Kiểu `Function<Animal,StringBuilder>` không phải subtype trực tiếp của `Function<Dog,CharSequence>`. Java không khai báo variance ngay trên mọi generic interface theo cách làm `Function` tự đổi hai type arguments trong phép gán đó.

Thay vì dựa vào một phép gán không hợp lệ, API thiết kế tham số:

```java
static <T, R> R flexibleApply(
        T item, Function<? super T, ? extends R> mapper) {
    return mapper.apply(item);
}
```

Ở đây một callback nhận kiểu cha của `T` và trả kiểu con của `R` có thể truyền vào. Quan hệ wildcard này thường xuất hiện trong **method parameters**, nơi compiler biết hàm sẽ đưa `T` vào và nhận `R` ra.

Không nên hiểu `Function<? super T,? extends R>` làm thay đổi định nghĩa interface `Function<T,R>` ở runtime. Đây là ràng buộc compile-time tại vị trí sử dụng một generic type.

## 5. API chuẩn `Stream.map`: mẫu quan trọng nhất

Chữ ký trong `java.util.stream.Stream<T>`:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

Đọc theo ngữ nghĩa:

1. Stream hiện tại cung cấp từng phần tử kiểu `T`.
2. Mapper được gọi với `T`; nếu mapper nhận `Object`, `Animal` hoặc một supertype phù hợp của `T`, nó vẫn làm việc được.
3. Mỗi kết quả mapper được xem là `R`; mapper có thể trả subtype của `R`.
4. API trả `Stream<R>`. Đó là **kiểu kết quả do compiler suy luận hoặc caller yêu cầu**, không nhất thiết trùng chính xác với kiểu biểu thức bên trong lambda.

Với stream `Dog`:

```java
Function<Animal, StringBuilder> label = ...;
List<CharSequence> labels = dogs.stream()
        .<CharSequence>map(label)
        .toList();
```

Dấu `.<CharSequence>map(...)` là **explicit method type argument** để chọn `R = CharSequence`. Nó không bắt buộc trong mọi lời gọi: Java thường suy luận `R` từ callback và ngữ cảnh gán. Trong ví dụ có chủ đích, nó giúp học viên thấy rõ phần `? extends R` ở phía kết quả.

Chú ý: `Stream.toList()` trả `List<CharSequence>` theo `Stream<CharSequence>`, và trong Java 17 danh sách kết quả không hỗ trợ các thao tác sửa đổi thông thường. Dù vậy, wildcard của `map` liên quan đến **quan hệ kiểu callback**, không phải tính bất biến của danh sách.

## 6. Chương trình Java 17 A: Stream, Comparator, Predicate và Consumer

Tạo tệp **`VarianceApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class VarianceApiDemo {
    static class Animal {
        private final String name;

        Animal(String name) { this.name = name; }
        String name() { return name; }
    }

    static final class Dog extends Animal {
        Dog(String name) { super(name); }
    }

    public static void main(String[] args) {
        List<Dog> dogs = new ArrayList<>(
                List.of(new Dog("Luna"), new Dog("Milo")));

        Function<Animal, StringBuilder> label =
                animal -> new StringBuilder(
                        animal.name().toUpperCase(Locale.ROOT));

        List<String> labels = dogs.stream()
                .<CharSequence>map(label)
                .map(CharSequence::toString)
                .toList();
        System.out.println("labels: " + labels);

        Comparator<Animal> byName =
                Comparator.comparing(Animal::name);
        dogs.sort(byName);
        System.out.println("sorted: "
                + dogs.stream().map(Dog::name).toList());

        Predicate<Animal> startsWithM =
                animal -> animal.name().startsWith("M");
        System.out.println("predicate: "
                + dogs.stream()
                        .filter(startsWithM)
                        .map(Dog::name)
                        .toList());

        Consumer<Animal> anyAnimal = animal ->
                System.out.println("consume: " + animal.name());
        Consumer<Dog> dogOnly = d ->
                System.out.println("dog: " + d.name());

        Consumer<Dog> combined = dogOnly.andThen(anyAnimal);
        combined.accept(dogs.get(0));
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all VarianceApiDemo.java
java VarianceApiDemo
```

**Stdout đã kiểm chứng:**

```text
labels: [LUNA, MILO]
sorted: [Luna, Milo]
predicate: [Milo]
dog: Luna
consume: Luna
```

Chương trình đã được kiểm chứng với `-Xlint:all` mà không có compiler warning.

### Đọc đúng phần `map`

`dogs.stream()` có kiểu `Stream<Dog>`. Callback `label` nhận `Animal`, và `Animal` là supertype của `Dog`, nên nó thỏa phần `? super Dog`.

Callback trả `StringBuilder`, là subtype của `CharSequence`, nên nó thỏa `? extends CharSequence`. Dòng `.<CharSequence>map(label)` yêu cầu stream kết quả có phần tử `CharSequence`. Tiếp đó `map(CharSequence::toString)` tạo stream `String`, và `toList()` cho danh sách `String`.

Đây là ví dụ thực tế cho **hai hướng variance trong cùng một callback**, không phải một phép cast nguy hiểm.

### Đọc đúng phần `sort`

`List<E>.sort` nhận:

```java
void sort(Comparator<? super E> c);
```

Danh sách `dogs` có `E = Dog`, còn `byName` có kiểu `Comparator<Animal>`. Một comparator biết so sánh mọi `Animal` chắc chắn so sánh được mọi `Dog`.

`? super E` trong trường hợp này xuất hiện bởi comparator **tiêu thụ** hai giá trị `E` để so sánh. `List<Dog>.sort(Comparator<Animal>)` là hợp lệ; không cần viết lại comparator kiểu `Dog`.

### Đọc đúng phần `filter`

`Stream<T>.filter` nhận:

```java
Stream<T> filter(Predicate<? super T> predicate);
```

Một `Predicate<Animal>` có thể kiểm tra mọi `Dog`, nên dùng được với `Stream<Dog>`. Kết quả vẫn là `Stream<Dog>`: `filter` chỉ chọn phần tử, không tạo một kiểu kết quả mới `R`.

Đây là lý do `filter` chỉ cần `? super T` ở tham số predicate chứ không có `? extends R` trong chữ ký callback.

### Đọc đúng phần `Consumer.andThen`

`Consumer<T>.andThen` nhận `Consumer<? super T>` nhưng **trả `Consumer<T>`**, không tự thu hẹp hoặc mở rộng type parameter của receiver.

Với `dogOnly: Consumer<Dog>`, lời gọi:

```java
Consumer<Dog> combined = dogOnly.andThen(anyAnimal);
```

hợp lệ bởi `anyAnimal: Consumer<Animal>` có thể nhận mọi `Dog`. Hai consumer được gọi theo thứ tự: trước hết `dogOnly`, tiếp đó `anyAnimal`.

Đừng lẫn với:

```java
// KHÔNG HỢP LỆ:
// Consumer<Dog> wrong = anyAnimal.andThen(dogOnly);
```

Receiver `anyAnimal` là `Consumer<Animal>`, nên `andThen` ở đó yêu cầu một `Consumer<? super Animal>`. `Consumer<Dog>` chỉ biết nhận `Dog`, không chắc xử lý được một `Animal` bất kỳ. Compiler bác bỏ. Chữ ký `andThen` **không tự đổi `Consumer<Animal>` thành `Consumer<Dog>`** chỉ vì bạn gán vào biến đó.

## 7. Các chữ ký chuẩn khác cần đọc chính xác

Bảng này dựa trên chữ ký đã đối chiếu bằng `javap` của JDK Java 17:

| API | Chữ ký trọng tâm | Vai trò của wildcard |
| --- | --- | --- |
| `Stream<T>.map` | `<R> Stream<R> map(Function<? super T, ? extends R>)` | Callback nhận T, tạo R |
| `Stream<T>.flatMap` | `<R> Stream<R> flatMap(Function<? super T, ? extends Stream<? extends R>>)` | Callback nhận T, tạo stream phần tử dùng như R |
| `Stream<T>.filter` | `Stream<T> filter(Predicate<? super T>)` | Predicate nhận T |
| `Iterable<T>.forEach` | `void forEach(Consumer<? super T>)` | Consumer nhận T |
| `List<E>.sort` | `void sort(Comparator<? super E>)` | Comparator so sánh các E |
| `Consumer<T>.andThen` | `Consumer<T> andThen(Consumer<? super T>)` | Consumer tiếp theo nhận T |
| `Predicate<T>.and` | `Predicate<T> and(Predicate<? super T>)` | Predicate còn lại nhận T |
| `Predicate<T>.or` | `Predicate<T> or(Predicate<? super T>)` | Predicate còn lại nhận T |
| `Function<T,R>.compose` | `<V> Function<V,R> compose(Function<? super V, ? extends T>)` | Hàm chạy trước nhận V và tạo T |
| `Function<T,R>.andThen` | `<V> Function<T,V> andThen(Function<? super R, ? extends V>)` | Hàm chạy sau nhận R và tạo V |

**Đọc các chữ ký như hợp đồng.** Một `Predicate<? super T>` hoặc `Consumer<? super T>` chỉ tiêu thụ `T`; không có kiểu trả về `R` cần biểu diễn trong generic parameters của `Predicate`/`Consumer`.

Một `Function` vừa nhận vừa trả kết quả nên có cả đầu vào super và đầu ra extends.

Một `Comparator` được truyền vào `sort` cũng tiêu thụ giá trị `E`, nhưng cho ra `int` cố định theo contract `compare`, nên không cần `? extends R`.

## 8. `Function.compose` và `Function.andThen`: quan sát hướng dữ liệu

Lấy `Function<T,R> f`. Về trực giác:

```text
compose(before):
    V ---> before ---> T ---> f ---> R

andThen(after):
    T ---> f ---> R ---> after ---> V
```

Do đó chữ ký của `compose`:

```java
<V> Function<V, R> compose(
        Function<? super V, ? extends T> before)
```

Hàm `before` nhận được `V`, trả về một giá trị hợp lệ làm đầu vào `T` cho hàm hiện tại. Đây là nguyên nhân cặp wildcard gắn với **V** và **T**, không phải với **R**.

Còn `andThen`:

```java
<V> Function<T, V> andThen(
        Function<? super R, ? extends V> after)
```

Hàm `after` tiêu thụ kết quả `R` của hàm hiện tại và tạo giá trị phù hợp với `V`. Cặp wildcard vì thế nằm ở **R** và **V**.

Sự đối xứng này giúp bạn nhớ API mà không cần học thuộc mọi dấu `<` `>`. Hãy vẽ **đường đi của giá trị** theo thứ tự thực thi.

## 9. Chương trình Java 17 B: Compose, andThen và flatMap

Tạo tệp **`FunctionCompositionDemo.java`**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class FunctionCompositionDemo {
    public static void main(String[] args) {
        Function<Number, String> stringify =
                n -> "n=" + n.intValue();
        Function<CharSequence, Integer> length =
                CharSequence::length;

        Function<String, String> compose =
                stringify.compose(length);
        System.out.println("compose: " + compose.apply("Java"));

        Function<CharSequence, Integer> count =
                CharSequence::length;
        Function<Number, Integer> after =
                stringify.andThen(count);
        System.out.println("andThen: " + after.apply(17));

        Function<CharSequence, Stream<String>> split =
                input -> Stream.of(input.toString().split(" "));
        List<CharSequence> tokens =
                List.of("red blue", "green")
                        .stream()
                        .<CharSequence>flatMap(split)
                        .toList();
        System.out.println("flatMap: " + tokens);
    }
}
```

Lệnh:

```bash
javac -Xlint:all FunctionCompositionDemo.java
java FunctionCompositionDemo
```

**Stdout đã kiểm chứng:**

```text
compose: n=4
andThen: 4
flatMap: [red, blue, green]
```

Chương trình đã biên dịch không warning với `-Xlint:all`.

### `compose` từng bước

Receiver `stringify` có kiểu `Function<Number,String>`, tức `T=Number`, `R=String`. Callback `before` là `length: Function<CharSequence,Integer>`.

Ta muốn hàm tổng hợp nhận `String`, nên `V=String`.

- `length` nhận `CharSequence`, một supertype của `String`, vì vậy đáp ứng `? super V`.
- `length` trả `Integer`, một subtype của `Number`, vì vậy đáp ứng `? extends T`.
- Kết quả `Function<String,String>` nhận `"Java"`, tính độ dài `4`, rồi tạo `"n=4"`.

Không hề có cast kiểu `CharSequence -> String` nguy hiểm; callback nhận kiểu rộng hơn nên an toàn.

### `andThen` từng bước

Receiver vẫn là `stringify: Function<Number,String>`. Callback sau là `count: Function<CharSequence,Integer>`. Ta chọn `V=Integer`.

- `count` nhận `CharSequence`, supertype của `String`, nên thỏa `? super R`.
- `count` trả `Integer`, phù hợp với `? extends V`.
- `stringify.apply(17)` cho `"n=17"`, gồm bốn ký tự.
- `count.apply("n=17")` cho `4`.

Kết quả `Function<Number,Integer>` không thay đổi kiểu đầu vào `Number` của receiver `stringify`.

### `flatMap` và lớp wildcard lồng nhau

`Stream<T>.flatMap` nhận:

```java
Function<? super T, ? extends Stream<? extends R>>
```

Đọc từ trong ra ngoài:

1. `Stream<? extends R>`: một stream chứa các giá trị có thể dùng như `R`.
2. `? extends Stream<? extends R>`: callback có thể trả một implementation/subtype thích hợp của stream đó.
3. `? super T`: callback có thể nhận `T` hoặc một supertype.

Trong ví dụ `T=String`, `R=CharSequence`:

- `Function<CharSequence,Stream<String>> split` nhận `CharSequence`, tức supertype của `String`.
- Kết quả là `Stream<String>`, những phần tử `String` dùng được như `CharSequence`.
- Phương thức `.<CharSequence>flatMap(split)` tạo `Stream<CharSequence>`, sau `toList()` là `List<CharSequence>`.

Mức wildcard lồng nhau **không phải phép biên dịch độc lập cho từng lớp thực**; nó là cơ chế kiểu để giữ an toàn khi flatten các stream tạo ra từ callback.

## 10. Phân biệt wildcard ở callback với wildcard ở collection

Hai biểu thức này liên quan nhưng nói về **hai đối tượng khác nhau**:

```java
List<? extends Animal> source;
Function<? super Animal, ? extends CharSequence> mapper;
```

Ở **collection nguồn**, `? extends Animal` nghĩa là các phần tử đọc ra có thể dùng như `Animal`; nhưng không thể tự ý thêm `Animal` vào danh sách vì kiểu phần tử thật có thể là `Dog`.

Ở **callback**, `? super Animal` nghĩa là mapper có thể nhận một `Animal` (hoặc một kiểu cha của `Animal`). Còn `? extends CharSequence` là lời hứa kết quả mapper dùng được như `CharSequence`.

Khi tự thiết kế method, bạn thường cần cả hai:

```java
static <T, R> List<R> mapInto(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T item : source) {
        result.add(mapper.apply(item));
    }
    return result;
}
```

Đây là method minh họa và cần import các kiểu thích hợp. Vì `source` là **producer** của `T`, ta nhận `List<? extends T>`; vì `mapper` là **consumer của T** và **producer của R**, ta dùng `Function<? super T,? extends R>`.

Không phải lúc nào cũng cần mọi wildcard như trên. Một API chỉ nhận `List<T>` cũng có thể hợp lệ và đủ tốt theo nhu cầu. Nhưng việc hiểu vai trò của các kiểu giúp bạn chọn chữ ký linh hoạt mà vẫn không tạo unchecked cast.

## 11. Chương trình Java 17 C: tự viết API có cả `extends` và `super`

Tạo tệp **`OwnFlexibleApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class OwnFlexibleApiDemo {
    static class Base {
        private final String code;

        Base(String code) { this.code = code; }
        String code() { return code; }
    }

    static final class Entry extends Base {
        Entry(String code) { super(code); }
    }

    static <T, R> List<R> mapInto(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        Objects.requireNonNull(source);
        Objects.requireNonNull(mapper);

        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<Entry> entries =
                List.of(new Entry("A"), new Entry("BC"));
        Function<Base, StringBuilder> asLabel =
                b -> new StringBuilder(b.code());

        List<CharSequence> labels = OwnFlexibleApiDemo
                .<Base, CharSequence>mapInto(entries, asLabel);

        System.out.println("labels: " + labels);
        System.out.println("types: "
                + labels.get(0).getClass().getSimpleName());
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all OwnFlexibleApiDemo.java
java OwnFlexibleApiDemo
```

**Stdout đã kiểm chứng:**

```text
labels: [A, BC]
types: StringBuilder
```

### Phân tích đầy đủ ba tham số kiểu

Lời gọi:

```java
OwnFlexibleApiDemo.<Base, CharSequence>mapInto(entries, asLabel)
```

chỉ định `T=Base`, `R=CharSequence`.

**Tham số 1: `List<? extends T> source`.**

`entries` có `List<Entry>`; vì `Entry extends Base`, danh sách này là tham số hợp lệ của `List<? extends Base>`. Method **chỉ duyệt và đọc** ra các `Base`, không tự chèn `Base` vào một list có thể thật ra chỉ chứa `Entry`.

**Tham số 2: `Function<? super T, ? extends R> mapper`.**

`asLabel` có `Function<Base,StringBuilder>`. Phần đầu vào `Base` phù hợp với `? super Base`, phần đầu ra `StringBuilder` là subtype của `CharSequence`, phù hợp `? extends CharSequence`.

**Kiểu trả về: `List<R>`.**

Method thêm các giá trị `StringBuilder` vào `List<CharSequence>`; điều này an toàn do mỗi `StringBuilder` là `CharSequence`. Runtime object vẫn là `StringBuilder` như dòng `types`, không bị chuyển hóa thành một lớp mới.

**Tại sao dùng `.<Base,CharSequence>` tường minh?**

Để thể hiện lựa chọn `T`/`R` rõ ràng trong bài học. Java có type inference cho generic methods nên nhiều ngữ cảnh có thể bỏ type arguments tường minh, nhưng khi compiler suy luận một kiểu hẹp hơn hoặc có overload phức tạp, explicit type witness giúp đọc rõ hợp đồng mong muốn.

Không nên dùng explicit type witness ở mọi lời gọi nếu compiler đã suy luận rõ và code trở nên rườm rà; hãy ưu tiên cách dễ đọc, chỉ thêm khi cần kiểm soát kiểu đích.

## 12. Sự khác nhau giữa `? super` trong `Function` và wildcard trên kiểu trả về

Một câu dễ gây hiểu nhầm: “`map` trả `Stream<? extends R>` bởi mapper có `? extends R`”. **Sai.**

Chữ ký thật của `Stream.map` là:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

Phương thức trả **`Stream<R>`**. Wildcard `? extends R` nằm **ở kiểu của callback được truyền vào**. Nó chỉ cho phép callback trả một subtype của `R` khi method xây stream kết quả kiểu `R`.

Tương tự:

```java
<V> Function<T, V> andThen(Function<? super R, ? extends V> after)
```

Trả `Function<T,V>`, **không** `Function<? super T,? extends V>`.

Khi đọc API Java, hãy phân biệt ba tầng:

1. **Kiểu của tham số method** — ví dụ `Function<? super T,? extends R>`.
2. **Kiểu trả về của method** — ví dụ `Stream<R>`.
3. **Kiểu khai báo của biến nhận kết quả** — ví dụ `List<CharSequence>`.

Wildcard không tự “lan” từ một tham số method sang mọi type argument của giá trị được trả về.

## 13. `? super T` không có nghĩa được đọc một giá trị kiểu `T` tùy ý

Trong `List<? super T>`:

```java
List<? super Dog> sink = new ArrayList<Animal>();
sink.add(new Dog("Milo"));  // Hợp lệ.
Object value = sink.get(0); // Chỉ bảo đảm Object.
```

Đây là đoạn minh họa giả định có lớp `Dog` và `Animal` tương ứng như chương trình A.

Lý do: danh sách thật có thể là `List<Animal>` hoặc `List<Object>`. Khi bạn đọc từ `List<? super Dog>`, compiler chỉ biết phần tử lấy ra là `Object` (ngoài `null`), không thể chắc là `Dog`.

Trong `Function<? super Dog, ? extends CharSequence>` cũng có quy tắc tương tự về **đầu vào của Function**: bạn có thể gọi `apply` với một `Dog`, vì mọi kiểu `? super Dog` đều nhận được `Dog`. Nhưng không thể suy ra loại callback thực sự là `Function<Dog, ...>`; nó có thể là `Function<Animal,...>` hoặc `Function<Object,...>`.

Chính vì giữ đúng giới hạn thông tin như vậy, wildcard vẫn **an toàn kiểu**, khác với raw `Function` hoặc unchecked casts.

## 14. Type inference và lambda: đọc ngữ cảnh trước khi đoán kiểu

Trong `Stream<String>`, method `map` cho compiler một `T` đã biết là `String`, rồi suy luận `R` từ mapper và ngữ cảnh kết quả:

```java
List<String> words = List.of("a", "bb");
List<Integer> lengths = words.stream()
        .map(String::length)
        .toList();
```

Một function nhận **supertype** cũng được:

```java
Function<CharSequence, Integer> count = CharSequence::length;
List<Integer> lengths = words.stream().map(count).toList();
```

Hai đoạn là ví dụ tách biệt và được đặt trong method với imports phù hợp; không khai báo đồng thời hai biến `lengths` trong cùng block. Khi cần cố định output ở một kiểu cha, hãy dùng type witness:

```java
List<CharSequence> names = words.stream()
        .<CharSequence>map(s -> new StringBuilder(s))
        .toList();
```

Đừng cast bừa khi inference khó hiểu. Hãy xác định `T`/`R` từ **chữ ký `Stream.map` và mapper cụ thể**. Bài về inference ở sau phân tích toàn bộ cơ chế target typing, generic method và overload.

## 15. Lambda và method reference: cùng nguyên lý target typing

Callback không tự mang một kiểu functional interface duy nhất nếu tách khỏi ngữ cảnh. Ví dụ `Animal::name` có thể dùng khi target descriptor nhận `Animal` hoặc các trường hợp subtype tương thích.

Trong chương trình `VarianceApiDemo` ở trên:

```java
Comparator<Animal> byName = Comparator.comparing(Animal::name);
dogs.sort(byName);
```

`Comparator.comparing` suy luận kiểu từ method reference; `List<Dog>.sort` chấp nhận `Comparator<? super Dog>` nên một `Comparator<Animal>` là hợp lệ. **Wildcard này nằm ở chữ ký API**, không phải do `Comparator<Animal>` trở thành `Comparator<Dog>`.

Nếu một callback dùng nhiều lần, khai báo `Function<Animal,StringBuilder>` hoặc `Comparator<Animal>` tường minh giúp kiểm tra quan hệ kiểu. Khi có overload/target typing phức tạp, đọc tiếp bài chuyên về inference và overload thay vì coi lambda là một “kiểu đặc biệt” bỏ qua compiler.

## 16. Khi nào `? extends R` là không đủ?

Một callback được yêu cầu trả `String`:

```java
Function<? super Dog, ? extends String> callback
```

**không** nhận tùy ý `Function<Dog,Object>`: một `Object` có thể là `Integer`, `Dog`, `List`, v.v., không bảo đảm là `String`.

Với một method cần `R=String`, compiler có trách nhiệm chặn callback chỉ hứa trả `Object`:

```java
// Minh họa lỗi compile-time:
Function<Dog, Object> tooBroad = dog -> dog.name();
// Stream<String> out = dogs.stream().<String>map(tooBroad); // Lỗi.
```

Mặc dù **lúc chạy** lambda trong ví dụ trả `String` thật, **kiểu khai báo của callback** chỉ là `Function<Dog,Object>`. Method không được dựa vào việc đoán nội dung triển khai để suy ra generic output `String`.

Nếu callback thật sự luôn trả chuỗi, hãy khai báo `Function<Dog,String>` hoặc `Function<Animal,String>` phù hợp. Đừng dùng unchecked cast từ `Function<Dog,Object>` sang `Function<Dog,String>` vì có thể che rủi ro và đẩy lỗi về runtime.

Tương tự, một `Function<Dog,R>` không thể được dùng tại nơi phải xử lý **mọi `Animal`**, vì có thể đầu vào là một loại `Animal` khác. Đây là biểu hiện của hướng **`? super T` ở đầu vào**.

## 17. Một số lỗi phổ biến khi đọc chữ ký API

**Lỗi 1 — Đảo hướng `super`/`extends`.** Đầu vào đi **vào** callback: `? super T`; kết quả đi **ra** callback: `? extends R`. Không dùng `? extends T` cho callback tiêu thụ `T` nếu không có lý do khác.

**Lỗi 2 — Nghĩ `Function<Animal,StringBuilder>` là subtype trực tiếp của `Function<Dog,CharSequence>`.** Generics invariant. Chính **wildcard ở phương thức nhận callback** làm cho lời gọi hợp lệ.

**Lỗi 3 — Tưởng `? super T` “chuyển” kiểu generic của function.** Wildcard cho phép **sử dụng** callback có input rộng hơn, nhưng không thay đổi declared type hoặc runtime class của chính callback.

**Lỗi 4 — Tưởng kết quả mapper buộc phải là đúng `R` theo runtime class.** `StringBuilder` có thể dùng như `CharSequence`; output `? extends R` chấp nhận subtype.

**Lỗi 5 — Nghĩ wildcard của mapper là wildcard của `Stream<R>` kết quả.** `Stream.map` trả `Stream<R>`, không `Stream<? extends R>` như một hiệu ứng tự động.

**Lỗi 6 — Nghĩ `Consumer.andThen` có thể đổi type parameter receiver tùy ý.** Method trả `Consumer<T>`; ví dụ `Consumer<Animal>.andThen(Consumer<Dog>)` không hợp lệ.

**Lỗi 7 — Dùng `List<Object>` khi cần chấp nhận `List<Dog>`.** `List<Dog>` không phải `List<Object>`. Với nguồn chỉ đọc, xem xét `List<? extends Animal>`, `List<?>` hoặc generic method có type variable.

**Lỗi 8 — Dùng raw `Function` hay raw `List` để né lỗi compiler.** Raw types làm mất bảo đảm generic, có thể dẫn đến unchecked warning và lỗi runtime. Wildcard/type inference đúng mới là cách xử lý.

**Lỗi 9 — Viết wildcard trong mọi type argument không cần thiết.** Một API chỉ dùng chính xác `Function<T,R>` trong bối cảnh nội bộ có thể không cần mở rộng. Dùng wildcard khi tăng khả năng tái sử dụng có ý nghĩa và vẫn mô tả đúng vai trò.

**Lỗi 10 — Cho rằng `? super T` luôn trả về `T` khi đọc collection.** Với `List<? super T>`, kết quả đọc chỉ được bảo đảm dưới dạng `Object`; wildcard super thích hợp cho tiêu thụ/ghi `T`, không phải một bảo đảm để đọc `T`.

**Lỗi 11 — Đánh đồng variance ở source với runtime type specialization.** `Function`, `Stream` và `List` vẫn dùng type erasure; wildcard không tạo class mới cho từng tham số hóa.

**Lỗi 12 — Suy luận chỉ từ tên generic parameter.** `T`, `R`, `V` chỉ là tên. Hãy đọc method thực sự **gọi tham số** hay **trả kết quả**, rồi xác định hướng dữ liệu.

## 18. Cách tự xác minh các chữ ký qua JDK

Các lệnh sau giúp bạn đối chiếu API đang dùng từ chính JDK:

```bash
javap -p java.util.stream.Stream
javap -p java.util.function.Function
javap -p java.util.function.Consumer
javap -p java.util.function.Predicate
javap -p java.util.List
javap -p java.lang.Iterable
```

Tìm các tên `map`, `flatMap`, `filter`, `compose`, `andThen`, `sort`, `forEach`. `javap` có thể trình bày generic signatures để bạn xem wildcard cùng type variables.

Đối với chương trình `OwnFlexibleApiDemo.java`, chạy:

```bash
javap -p -s OwnFlexibleApiDemo
```

Trích kết quả đã kiểm chứng:

```text
static <T, R> java.util.List<R> mapInto(
    java.util.List<? extends T>,
    java.util.function.Function<? super T, ? extends R>);
  descriptor: (Ljava/util/List;Ljava/util/function/Function;)Ljava/util/List;
```

Sự khác nhau ở đây quan trọng:

- **Generic signature** mà `javap` hiển thị ở dòng khai báo giữ wildcard `? extends T`, `? super T`, `? extends R` như metadata.
- **JVM descriptor** dùng các lớp bị xóa kiểu `List` và `Function`. Nó không có một runtime class riêng cho `Function<Animal,StringBuilder>` so với `Function<Dog,CharSequence>`.
- Tính hợp lệ của việc truyền callback được compiler kiểm tra dựa trên Java generic type system, không phải nhờ runtime cast tùy ý giữa các dạng `Function`.

Nếu muốn quan sát bytecode cụ thể của lời gọi `apply`, dùng `javap -p -c OwnFlexibleApiDemo`. Nhưng để xác minh câu hỏi trọng tâm về **chữ ký wildcard**, `javap -p` và source JDK đã là bằng chứng trực tiếp và dễ đọc nhất.

## 19. Quy trình chọn wildcard khi tự thiết kế API

Đối với một method nhận callback generic, hãy theo các bước:

1. **Xác định loại dữ liệu mà API chủ động đưa vào callback.** Nếu API gọi `mapper.apply(item)` với `item: T`, callback là **consumer của `T`**, nên có thể nhận `? super T`.
2. **Xác định loại kết quả mà API cần nhận từ callback.** Nếu API muốn một kết quả dùng như `R`, callback là **producer của `R`**, nên có thể trả `? extends R`.
3. **Kiểm tra chữ ký return của method.** Nếu method trả `List<R>` hay `Stream<R>`, đừng tự chuyển thành wildcard output nếu không cần.
4. **Đánh giá nguồn collection.** Nếu chỉ đọc các `T` từ list, `List<? extends T>` có thể phù hợp. Nếu ghi `T` vào destination, `Collection<? super T>` có thể phù hợp.
5. **Kiểm tra bằng các subtype/supertype thực tế.** Tạo một callback nhận supertype và trả subtype; thử với một nguồn list phần tử subtype.
6. **Chạy `javac -Xlint:all` với Java version mục tiêu.** Xử lý lỗi generic bằng quan hệ kiểu đúng, không dùng raw types để “cho biên dịch”.
7. **Đối chiếu `javap` nếu cần:** phân biệt generic metadata với JVM descriptor sau erasure.
8. **Giữ thiết kế dễ đọc.** Wildcard phục vụ tính linh hoạt khi đúng hướng dữ liệu; không cần làm mọi tham số phức tạp nếu lợi ích nhỏ.

Đối với callback, một câu hỏi nhanh rất hiệu quả là: *“Tôi có thể đưa một T cho hàm này mà không cast không? Và kết quả hàm trả có được phép xem như R không?”* Nếu cả hai đều có, chữ ký `Function<? super T,? extends R>` đang làm đúng nhiệm vụ.

## 20. Bài tập có đáp án

### Bài 1 — Chọn callback cho stream

Có `Stream<Dog>`, `Dog extends Animal`, và cần stream kết quả kiểu `CharSequence`. Những callback nào có thể dùng qua `map` với `R=CharSequence`?

```java
Function<Animal, String> a = Animal::name;
Function<Dog, StringBuilder> b = d -> new StringBuilder(d.name());
Function<Object, CharSequence> c = Object::toString;
```

**Đáp án:** cả ba đều thỏa `Function<? super Dog,? extends CharSequence>` (giả định các class `Animal`/`Dog` trong ví dụ). `Animal`, `Dog`, `Object` đều nhận được `Dog` theo quan hệ kiểu; `String`, `StringBuilder`, `CharSequence` đều có thể dùng như `CharSequence`.

### Bài 2 — Vì sao callback này sai?

```java
Function<Animal, Object> broadResult = animal -> animal.name();
// Stream<String> out = dogs.stream().<String>map(broadResult);
```

**Đáp án:** `Object` không phải subtype của `String`. Mặc dù lambda thực tế trả chuỗi, kiểu khai báo callback chỉ cam kết `Object`; `? extends String` không chấp nhận nó.

### Bài 3 — `Consumer.andThen` giữ kiểu nào?

Với `Consumer<Dog> dogOnly` và `Consumer<Animal> allAnimals`, kết quả `dogOnly.andThen(allAnimals)` có kiểu gì?

**Đáp án:** `Consumer<Dog>`. Consumer tiếp theo nhận `Animal`, phù hợp `? super Dog`, còn return type của `andThen` vẫn là `Consumer<T>` với `T=Dog`.

### Bài 4 — Comparator theo supertype

Tại sao `List<Dog>.sort(Comparator<Animal>)` hợp lệ?

**Đáp án:** `List<E>.sort` nhận `Comparator<? super E>`; `Comparator<Animal>` so sánh được hai `Dog` vì mỗi `Dog` là một `Animal`.

### Bài 5 — `compose` chạy theo thứ tự nào?

`Function<Number,String> f` và `Function<CharSequence,Integer> before`; gọi `f.compose(before)` để tạo `Function<String,String>` hợp lệ không?

**Đáp án:** hợp lệ. Hàm `before` nhận `String` vì `CharSequence` là supertype, trả `Integer` vì `Integer` là subtype của `Number`; sau đó `f` nhận kết quả kiểu `Number`.

### Bài 6 — `flatMap` có wildcard nào?

Vì sao `Stream.flatMap` nhận `Function<? super T,? extends Stream<? extends R>>` thay vì chỉ `Function<T,Stream<R>>`?

**Đáp án:** để callback có thể nhận một supertype của `T` và trả stream của những phần tử subtype của `R`, trong khi API vẫn flatten chúng thành `Stream<R>` an toàn.

### Bài 7 — Đọc/ghi wildcard collection

Nếu method chỉ cần duyệt `List<Dog>` để lấy các `Animal`, `List<? extends Animal>` có giúp gì? Nó có cho gọi `list.add(new Animal(...))` không?

**Đáp án:** nhận được nhiều loại list của các subtype `Animal` để **đọc** an toàn. Không được thêm một `Animal` tùy ý, vì list thực có thể chỉ cho phép `Dog` hoặc subtype khác.

### Bài 8 — Generic output type

Với mapper `Function<Animal,StringBuilder>` và source `Stream<Dog>`, nếu để compiler suy luận mặc định, kiểu phần tử kết quả có thể là `StringBuilder`. Làm sao chủ động chọn `R=CharSequence`?

**Đáp án:** dùng `.<CharSequence>map(mapper)` hoặc một ngữ cảnh generic target typing tương ứng khi compiler có thể suy luận. Cách viết tường minh là dễ kiểm chứng nhất ở ví dụ này.

### Bài 9 — Phân biệt generic method với runtime

Chạy `javap -s` thấy descriptor `(List,Function)List` cho `mapInto`, dù generic signature có nhiều wildcard. Có nghĩa compiler bỏ qua kiểm tra kiểu `? super`/`? extends` không?

**Đáp án:** không. Compiler kiểm tra các ràng buộc generic ở source và ghi descriptor erased cho JVM; generic signature metadata và kiểm tra compile-time là hai tầng khác với erased runtime descriptor.

## 21. Checklist trước khi dùng wildcard trong API

- [ ] Xác định **`T` nào được đưa vào** callback và **`R` nào được nhận lại**.
- [ ] Nếu callback nhận `T`, cân nhắc `? super T`.
- [ ] Nếu callback trả một subtype phù hợp với `R`, cân nhắc `? extends R`.
- [ ] Phân biệt variance của **tham số callback** với kiểu **trả về của API**.
- [ ] Đọc đúng chữ ký `Stream.map`, `flatMap`, `filter`, `Consumer.andThen`, `Function.compose/andThen`.
- [ ] Không lẫn generic invariance với khả năng dùng wildcard ở use-site.
- [ ] Không dùng raw type hoặc unchecked cast để né một lỗi về hướng variance.
- [ ] Nếu generic inference phức tạp, thử explicit method type arguments có ý nghĩa.
- [ ] Kiểm tra trường hợp subtype đầu vào và subtype đầu ra bằng một ví dụ runnable.
- [ ] Nhớ `getClass()`/erasure không làm phát sinh những runtime classes riêng cho từng callback generic.

## Kết luận

**`Function<? super T, ? extends R>`** là cách Java Standard API diễn đạt một hợp đồng callback linh hoạt nhưng an toàn: hàm có thể **tiêu thụ T qua một supertype** và **sản xuất R qua một subtype**. Cùng tư duy đó xuất hiện trong `Stream.map`, `flatMap`, `Predicate<? super T>`, `Consumer<? super T>`, `Comparator<? super T>`, `Function.compose` và `Function.andThen`.

Hãy đọc **hướng chảy dữ liệu**, không chỉ học thuộc dấu wildcard. Khi callback nhận giá trị, nghĩ `super`; khi callback trả giá trị dùng như kiểu đích, nghĩ `extends`. Đó là nền tảng để viết lambda, method references và API generic Java dễ tái sử dụng mà không đánh đổi type safety.
