# Wildcard ? super và ? extends trong API nhận hàm của Java

## 1. Mục tiêu

Trong Java, các phương thức nhận một lambda, method reference hoặc đối tượng functional interface thường dùng những kiểu như:

~~~java
Function<? super T, ? extends R>
Consumer<? super T>
Predicate<? super T>
Comparator<? super T>
Supplier<? extends T>
~~~

Những wildcard ở đây **không trang trí cho cú pháp**. Chúng mô tả quan hệ kiểu hợp lệ giữa **dữ liệu mà API đưa vào hàm** và **kết quả mà API nhận từ hàm**.

Sau bài này, bạn có thể:

- Giải thích vì sao generic Java mặc định **invariant**, dù các kiểu thành phần có quan hệ kế thừa.
- Đọc đúng `? super` và `? extends` theo quy tắc **PECS** (Producer Extends, Consumer Super).
- Chọn wildcard ở **đầu vào và đầu ra** của `Function<T,R>`, `BiFunction<T,U,R>`, `Consumer<T>`, `Predicate<T>`, `Comparator<T>` và `Supplier<T>`.
- Hiểu các chữ ký trong `Stream.map`, `Stream.filter`, `Iterable.forEach`, `Function.andThen` và `Function.compose`.
- Giải thích cách **target typing**, generic method inference và explicit type witness giúp biên dịch những lời gọi có wildcard.
- Tránh dùng raw type, cast không an toàn và các wildcard ngược chiều.

## 2. Từ quan hệ kế thừa đến generic invariance

Giả sử có lớp `Animal` và lớp `Dog extends Animal`. Một Dog có thể dùng ở nơi yêu cầu Animal:

~~~java
Dog dog = new Dog("Milo");
Animal animal = dog;
~~~

Đoạn này giả định lớp Animal và Dog có constructor phù hợp; chương trình đầy đủ sẽ xuất hiện ở phần 8.

Nhưng với kiểu generic, quan hệ đó **không tự được nâng lên**:

~~~java
List<Dog> dogs = new ArrayList<>();
// List<Animal> animals = dogs; // Không biên dịch.
~~~

Nếu phép gán trên được phép, caller có thể thêm Cat vào biến `animals`, trong khi danh sách thật vốn là List<Dog>. Java tránh lỗi này bằng **invariance**: `List<Dog>` không phải subtype của `List<Animal>`.

Tương tự:

~~~java
Function<Animal, String> label = animal -> "pet";
// Function<Dog, CharSequence> f = label; // Không biên dịch.
~~~

Về khả năng xử lý, một hàm chấp nhận **Animal** đương nhiên chấp nhận Dog, và String là một **CharSequence**. Tuy nhiên, hai kiểu generic cụ thể `Function<Animal,String>` và `Function<Dog,CharSequence>` không có quan hệ subtype trực tiếp.

**Wildcard** cho phép định nghĩa một kiểu đích mô tả **họ các kiểu generic tương thích**, thay vì ép phép gán invariant phải thành công.

## 3. Producer Extends và Consumer Super (PECS)

Quy tắc PECS định hướng từ góc nhìn nơi **sử dụng giá trị**:

- Nếu cấu trúc **sản xuất** giá trị kiểu T để bạn lấy ra, thường dùng **`? extends T`**.
- Nếu cấu trúc **tiêu thụ** những giá trị T mà bạn truyền vào, thường dùng **`? super T`**.

Hãy xét `List` trước khi chuyển sang hàm.

### 3.1. ? extends: đọc ra như một kiểu cha

~~~java
List<Integer> integers = List.of(2, 4, 6);
List<? extends Number> numbers = integers;
Number first = numbers.get(0); // 2

// numbers.add(7); // Không biên dịch.
~~~

`? extends Number` có thể đại diện cho Integer, Double hoặc subtype khác của Number. Ta được bảo đảm đọc ra Number, nhưng **không biết chính xác subtype**, nên không thể thêm một Integer bất kỳ qua tham chiếu đó. Việc thêm null là một ngoại lệ về kiểm tra kiểu, nhưng implementation List cụ thể vẫn có thể từ chối thay đổi.

### 3.2. ? super: truyền một giá trị T vào

~~~java
List<Number> storage = new ArrayList<>();
List<? super Integer> target = storage;

target.add(10);            // Hợp lệ.
target.add(20);            // Hợp lệ.
Object first = target.get(0); // Kiểu được bảo đảm chỉ là Object.
~~~

`? super Integer` có thể là Integer, Number hoặc Object. Đưa Integer vào luôn an toàn; ngược lại kết quả đọc ra qua wildcard chỉ có kiểu được bảo đảm chung là Object. Không được tùy tiện đưa Double vào, vì kiểu thật có thể là List<Integer>.

**PECS nói về hướng sử dụng của dữ liệu tại API**, không có nghĩa mọi biến generic nên chứa wildcard. Khi tạo một cấu trúc cụ thể, thường dùng kiểu chính xác như `List<Dog>`.

## 4. Functional interface có hai chiều dữ liệu

`Function<T,R>` khai báo SAM:

~~~java
R apply(T value);
~~~

Vậy:

- `T` là **đầu vào** do caller cung cấp cho hàm: hàm **tiêu thụ** T.
- `R` là **đầu ra** do hàm tạo ra: hàm **sản xuất** R.

Một API muốn đưa T vào một hàm và nhận lại R có thể khai báo:

~~~java
Function<? super T, ? extends R>
~~~

Đọc thành lời:

> Hãy nhận một hàm chấp nhận T hoặc một kiểu cha của T, và trả về R hoặc một kiểu con của R.

Ví dụ:

~~~java
Function<Animal, String> animalLabel =
        animal -> animal.name();

Function<? super Dog, ? extends CharSequence> dogLabel =
        animalLabel;

CharSequence result = dogLabel.apply(new Dog("An"));
~~~

Hợp lệ vì **Animal** là kiểu cha của Dog ở chiều **đầu vào**, còn **String** triển khai CharSequence ở chiều **đầu ra**.

Không được gán trực tiếp:

~~~java
// String exact = dogLabel.apply(new Dog("An")); // Không biên dịch.
~~~

Tại vị trí này compiler chỉ biết kết quả có thể dùng như CharSequence. Kiểu thực tế có thể là String, StringBuilder hoặc một subtype CharSequence khác, chứ không buộc là String.

**Chú ý:** wildcard không biến `Function<Animal,String>` thành subtype của `Function<Dog,CharSequence>`; nó giúp biểu diễn một kiểu đích chấp nhận các Function có đầu vào/đầu ra phù hợp.

## 5. Thiết kế một API nhận mapper

Một phương thức biến đổi danh sách có thể dùng:

~~~java
static <T, R> List<R> transform(
        List<T> items,
        Function<? super T, ? extends R> mapper) {
    return items.stream()
            .<R>map(mapper)
            .toList();
}
~~~

Đây là **phương thức minh họa**, cần đặt trong lớp và import `List` cùng `Function`.

Tại lời gọi, nếu items là `List<Dog>`, caller có thể truyền `Function<Animal,String>`; nếu cần kết quả dưới dạng `List<CharSequence>`, cũng có thể khai báo:

~~~java
List<Dog> dogs = List.of(new Dog("Milo"));
Function<Animal, String> label = Animal::name;

List<CharSequence> text = transform(dogs, label);
~~~

`Animal` nhận được Dog, còn String là CharSequence. **Type inference** suy ra kiểu T và R từ các đối số và kiểu kết quả được yêu cầu.

### 5.1. Vì sao trong implementation ghi .<R>map(mapper)?

`Stream.map` tự có type parameter `<R>` độc lập với method `transform`. Khi mapper có kiểu `Function<? super T,? extends R>`, một số tổ hợp suy luận khiến compiler giữ kiểu kết quả của `map` dưới một **capture** cụ thể của `? extends R`; lời gọi `.toList()` có thể không được xem là `List<R>` nếu để toàn bộ tự suy luận.

Viết:

~~~java
items.stream().<R>map(mapper).toList()
~~~

là **explicit type witness**, yêu cầu `map` dùng chính kiểu `R` của `transform`. Nó vẫn type-safe vì mapper hứa trả một giá trị có thể dùng như R; không cần cast hay raw type. Đây là ví dụ một chỗ **suy luận kiểu của Java** có thể cần hỗ trợ từ người viết.

Ngược lại, ở những lời gọi đơn giản như:

~~~java
List<String> labels = dogs.stream()
        .map(label)
        .toList();
~~~

nếu mapper có kiểu `Function<Animal,String>`, compiler thường suy ra R = String trực tiếp và không cần ghi type witness.

### 5.2. Vì sao không viết Function<T,R>?

Nếu API ghi `Function<T,R>` thì `Function<Animal,String>` không nhất thiết khớp chính xác với T=Dog và R=CharSequence. Khi thực tế cần **hàm nhận một supertype và trả một subtype**, wildcard trong **chữ ký tham số** diễn đạt hợp đồng tốt hơn.

Đừng thêm wildcard vào mọi khai báo biến thông thường. Một implementation cụ thể thường nên có kiểu rõ:

~~~java
Function<Animal, String> label = Animal::name;
~~~

Chỉ mở rộng ở vị trí API cần **chấp nhận một họ hàm**.

## 6. Những API tiêu chuẩn dùng ? super

### 6.1. Stream.filter: Predicate nhận phần tử

Chữ ký chính:

~~~java
Stream<T> filter(Predicate<? super T> predicate)
~~~

Nếu stream chứa Dog, một Predicate<Animal> có thể xử lý từng Dog:

~~~java
Predicate<Animal> hasName = animal -> animal.name() != null;
List<Dog> namedDogs = dogs.stream()
        .filter(hasName)
        .toList();
~~~

Predicate **tiêu thụ T**, rồi trả primitive boolean, nên input `? super T` phù hợp. Nó không **sản xuất một T**.

### 6.2. Iterable.forEach: Consumer nhận phần tử

~~~java
void forEach(Consumer<? super T> action)
~~~

Với `List<Dog>`:

~~~java
Consumer<Animal> logAnimal =
        animal -> System.out.println(animal.name());

dogs.forEach(logAnimal);
~~~

Bất kỳ hành động nào xử lý Animal đều xử lý được Dog. **forEach có thể tạo side effect** và cách callback chạy phụ thuộc API thực thi; wildcard chỉ nói về kiểu, không bảo đảm thứ tự/concurrency.

### 6.3. Comparator<T>: nhận hai giá trị T

Các API như `Stream<T>.sorted` hoặc `List<T>.sort` nhận `Comparator<? super T>`.

~~~java
Comparator<Animal> byName =
        Comparator.comparing(Animal::name);

List<Dog> sorted = dogs.stream()
        .sorted(byName)
        .toList();
~~~

Comparator<Animal> so sánh được hai Dog. Comparator phải bảo đảm hợp đồng về dấu, tính bắc cầu và sự nhất quán; wildcard không sửa comparator sai hoặc giải quyết dữ liệu bị thay đổi khi sắp xếp.

### 6.4. Stream.map: nhận vào và trả ra

`Stream<T>.map` khai báo:

~~~java
<R> Stream<R> map(
        Function<? super T, ? extends R> mapper)
~~~

Hàm **nhận phần tử T** và **trả kết quả thuộc R**: đúng mẫu super ở đầu vào, extends ở đầu ra. Với `Function<Animal,String>` trên Stream<Dog>, cách viết `.map(label)` thường đủ để suy ra Stream<String>. Khi muốn ấn định R là CharSequence:

~~~java
List<CharSequence> result = dogs.stream()
        .<CharSequence>map(label)
        .toList();
~~~

`Stream.toList()` từ Java 16 trả danh sách không hỗ trợ mutation; nó không làm các phần tử mutable trở thành bất biến sâu.

## 7. Các nguồn tạo kết quả dùng ? extends

`Supplier<T>` có SAM `T get()`: nó **chỉ tạo ra giá trị**, không nhận đối số từ caller tại lời gọi get.

Một API muốn tạo Animal có thể chấp nhận:

~~~java
static Animal create(
        Supplier<? extends Animal> source) {
    return source.get();
}
~~~

Một `Supplier<Dog>` có thể truyền vào vì Dog là Animal. Với vị trí **đầu ra của hàm**, dùng `? extends Animal` mở rộng khả năng tái sử dụng.

Ngược lại, `Supplier<? super Dog>` chỉ bảo đảm kết quả là một kiểu cha chưa biết của Dog; không thể kết luận kết quả luôn là Animal nếu kiểu thực tế có thể là Object.

Chú ý: wildcard **không bảo đảm non-null**. Một Supplier hợp lệ về kiểu có thể trả null nếu hợp đồng cho phép.

## 8. Java 17 hoàn chỉnh: tổng hợp các wildcard

Ví dụ minh họa một API biến đổi `List<T>`, sử dụng comparator và consumer nhận supertype, supplier trả subtype, cùng `BiFunction` có hai đầu vào.

Tạo tệp **WildcardFunctionDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

public class WildcardFunctionDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }
    }

    static <T, R> List<R> transform(
            List<T> items,
            Function<? super T, ? extends R> mapper) {
        return items.stream().<R>map(mapper).toList();
    }

    static void observeDogs(
            List<Dog> dogs,
            Consumer<? super Dog> observer) {
        dogs.forEach(observer);
    }

    static Animal createAnimal(
            Supplier<? extends Animal> source) {
        return source.get();
    }

    public static void main(String[] args) {
        List<Dog> dogs = List.of(
                new Dog("Milo"),
                new Dog("An")
        );

        Function<Animal, String> label =
                animal -> "pet:" + animal.name();
        Comparator<Animal> byName =
                Comparator.comparing(Animal::name);
        Consumer<Animal> observer =
                animal -> System.out.println("seen " + animal.name());

        List<String> labels = transform(
                dogs.stream().sorted(byName).toList(),
                label
        );
        System.out.println("labels: " + labels);

        List<CharSequence> asText = transform(dogs, label);
        System.out.println("first text: " + asText.get(0));

        observeDogs(dogs, observer);

        Supplier<Dog> dogFactory = () -> new Dog("Zoe");
        Animal created = createAnimal(dogFactory);
        System.out.println("created: " + created.name());

        BiFunction<Animal, Integer, String> indexed =
                (animal, index) -> animal.name() + "#" + index;
        BiFunction<? super Dog, ? super Integer,
                ? extends CharSequence> adapter = indexed;
        CharSequence code = adapter.apply(dogs.get(0), 3);
        System.out.println("code: " + code);

        Function<CharSequence, Integer> length =
                CharSequence::length;
        Function<Animal, Integer> labelLength =
                label.andThen(length);
        System.out.println("length: " + labelLength.apply(dogs.get(1)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac WildcardFunctionDemo.java
java WildcardFunctionDemo
~~~

**Đầu ra chính xác:**

~~~text
labels: [pet:An, pet:Milo]
first text: pet:Milo
seen Milo
seen An
created: Zoe
code: Milo#3
length: 6
~~~

**Giải thích:**

1. `Comparator<Animal>` dùng trong Stream<Dog> vì `sorted` nhận `Comparator<? super Dog>`. Kết quả labels theo tên tăng dần: An trước Milo.
2. `Function<Animal,String>` dùng như mapper cho Dog nhờ `? super Dog`; đầu ra String có thể sử dụng dưới kiểu CharSequence nhờ `? extends CharSequence`.
3. `List<CharSequence> asText` được suy ra hợp lệ khi `transform` có type witness cho `map`. `asText.get(0)` là chuỗi tạo từ Milo: pet:Milo.
4. `Consumer<Animal>` được đưa vào `observeDogs`, nơi đòi `Consumer<? super Dog>`. Nó duyệt danh sách gốc theo Milo rồi An, không dùng danh sách đã sắp của labels.
5. `Supplier<Dog>` được đưa vào `createAnimal` vì phương thức chỉ cần đọc một Animal từ nguồn. Kết quả có tên Zoe.
6. `BiFunction<Animal,Integer,String>` phù hợp với `BiFunction<? super Dog,? super Integer,? extends CharSequence>`, nên kết quả là Milo#3.
7. `label.andThen(length)` hợp lệ vì label trả String, còn length nhận CharSequence. Chuỗi pet:An dài 6 đơn vị UTF-16.

Chương trình không cần cast hay raw type. Phần in console là side effect có chủ đích; chính wildcard không bảo đảm hàm thuần, an toàn đa luồng hoặc không ném ngoại lệ.

## 9. andThen và compose của Function

Với `Function<T,R>`, các chữ ký rút gọn:

~~~java
<V> Function<T,V> andThen(
        Function<? super R, ? extends V> after)

<V> Function<V,R> compose(
        Function<? super V, ? extends T> before)
~~~

Đối với **andThen**, hàm hiện tại sản xuất R; hàm `after` phải **tiêu thụ được R** nên dùng `? super R`, và sản xuất được V nên dùng `? extends V`.

Đối với **compose**, `before` chạy trước, nó phải sản xuất thứ có thể dùng như T, nên dùng `? extends T`. Hàm kết hợp mới nhận V, nên `before` phải tiêu thụ V hoặc supertype, tức `? super V`.

Ví dụ:

~~~java
Function<Animal, String> name = Animal::name;
Function<CharSequence, Integer> length = CharSequence::length;

Function<Animal, Integer> count = name.andThen(length);
~~~

Hợp lệ vì String triển khai CharSequence. Đừng nhầm **compose** với **andThen** về thứ tự: `f.andThen(g)` là **f rồi g**; `f.compose(g)` là **g rồi f**.

## 10. BiFunction có hai đầu vào

`BiFunction<T,U,R>` có chữ ký `R apply(T t,U u)`. Cả **T và U đều được tiêu thụ**, còn R được sản xuất. Vì vậy mẫu tham số linh hoạt là:

~~~java
BiFunction<? super T, ? super U, ? extends R>
~~~

Ví dụ:

~~~java
BiFunction<Animal, Number, String> display =
        (animal, number) -> animal.name() + number;

BiFunction<? super Dog, ? super Integer,
        ? extends CharSequence> compatible = display;
~~~

Animal nhận Dog; Number nhận Integer; String là CharSequence. Đây là ba quan hệ an toàn cùng lúc.

Nếu API cần kiểu số nguyên thủy không boxing, hãy kiểm tra những specialization có sẵn trong `java.util.function` như `ToIntFunction<T>`; không thể đặt primitive `int` làm type argument generic. Chọn loại interface theo hợp đồng, sau đó mới đo hiệu năng nếu cần.

## 11. Khi nào không nên dùng wildcard?

Một API cần các hàm chính xác theo kiểu có thể chọn `Function<T,R>`. Wildcard hữu ích khi thực sự muốn chấp nhận **đầu vào rộng hơn** hoặc **đầu ra hẹp hơn**. Dùng nó ở mọi nơi có thể làm code khó đọc và khiến phép suy luận kiểu khó hơn.

Ví dụ nên khai báo implementation cụ thể:

~~~java
Function<Animal, String> name = Animal::name;
~~~

Sau đó API tự mở rộng tham số của nó:

~~~java
static <T,R> R applyOne(
        T item,
        Function<? super T, ? extends R> mapper) {
    return mapper.apply(item);
}
~~~

Không cần cast. Nếu bạn khai báo biến mapper là `Function<? super Dog, ? extends CharSequence>` từ đầu, giá trị trả về chỉ được bảo đảm CharSequence; bạn có thể mất thông tin cụ thể String mà caller muốn dùng.

## 12. Những hiểu nhầm thường gặp

| Nhầm lẫn | Giải thích chính xác |
| --- | --- |
| `Function<Animal,String>` là subtype của `Function<Dog,CharSequence>` | Generic invariant; có thể gán qua kiểu đích wildcard tương thích |
| `? super Dog` có nghĩa đầu ra là Animal | `super` ở đầu vào cho phép truyền Dog; không nói gì về đầu ra |
| `? extends Animal` nghĩa có thể thêm Dog | Với List<? extends Animal>, không thể thêm Dog tùy ý |
| Dùng `? extends T` ở đầu vào của mapper luôn tốt hơn | Không bảo đảm hàm nhận được một T bất kỳ |
| Dùng `? super R` ở đầu ra của mapper | Chỉ có thể chắc chắn kết quả là Object, không phải R |
| Type inference sẽ luôn tự hiểu mọi wildcard | Một số tình huống cần kiểu tường minh hoặc `.<R>map(...)` |
| Wildcard tự kiểm tra null, side effect, concurrency | Nó chỉ là quy tắc tương thích kiểu khi biên dịch |
| Dùng raw `Function` sẽ giải quyết lỗi | Bỏ bảo đảm kiểu, dễ phát sinh unchecked warning và lỗi runtime |

### 12.1. Đảo wildcard ở đầu vào

Giả sử:

~~~java
Function<? extends Dog, ? extends CharSequence> wrong;
~~~

Kiểu đầu vào thực tế có thể là một subtype riêng rất hẹp của Dog. Vì vậy compiler không thể cho phép bạn gọi `wrong.apply(new Dog("An"))` một cách tổng quát. Khi API cần **đưa Dog cho mapper**, phải là `Function<? super Dog, ? extends CharSequence>`.

### 12.2. Đảo wildcard ở đầu ra

~~~java
Function<? super Dog, ? super CharSequence> wrongOutput;
~~~

Về đầu ra, `? super CharSequence` có thể là CharSequence hoặc Object, nên caller chỉ có thể dựa vào Object. Nếu muốn đảm bảo đọc như CharSequence, dùng `? extends CharSequence`.

### 12.3. Wildcard capture

Mỗi `?` tương ứng với một kiểu **chưa biết** mà compiler có thể biểu diễn bằng **capture conversion**. Ví dụ `List<?>` đọc ra Object, nhưng không được tự thêm Object vì kiểu phần tử thực tế chưa biết.

Nếu gặp lỗi capture, hãy tìm quan hệ cần ràng buộc, đặt tên kiểu qua một **generic helper**, hoặc sử dụng type witness và biến trung gian có kiểu cụ thể. Không nên sửa bằng raw type hoặc unchecked cast chỉ để hết lỗi.

## 13. Kiểm thử API nhận hàm

Nên kiểm tra các hợp đồng có ý nghĩa:

1. Mapper nhận **supertype**: Function<Animal,String> xử lý List<Dog>.
2. Mapper trả **subtype**: String được đọc qua CharSequence.
3. Consumer/Predicate nhận supertype và xử lý Dog.
4. Comparator<Animal> sắp xếp Dog đúng tiêu chí, gồm trường hợp cùng khóa.
5. Supplier<Dog> tạo giá trị dùng như Animal.
6. Hàm ném exception hoặc trả null: wildcard không xử lý tự động.
7. Type inference hoạt động với kiểu đích mong muốn; helper có explicit type witness khi cần.

Ví dụ kiểm tra thủ công sau được đặt trong ngữ cảnh có `applyOne`, Animal và Dog:

~~~java
Function<Animal, String> name = Animal::name;
Dog dog = new Dog("An");
CharSequence result = applyOne(dog, name);

if (!result.toString().equals("An")) {
    throw new AssertionError("Unexpected result");
}
~~~

Kiểm thử runtime chỉ xác nhận vài dữ liệu cụ thể; các quan hệ type-safe chủ yếu được compiler xác minh khi biên dịch mã nguồn.

## 14. Bài tập

**Bài 1 — Chọn kiểu tham số.** Một API xử lý `Student` cần callback ghi log, không trả kết quả. Nên khai báo `Consumer<Student>`, `Consumer<? super Student>` hay `Consumer<? extends Student>`?

**Đáp án:** `Consumer<? super Student>` linh hoạt nhất trong phạm vi hợp đồng này. Nó cho phép Consumer<Student>, Consumer<Person> hoặc Consumer<Object> khi tương thích. `Consumer<Student>` hợp lệ nhưng hẹp hơn.

**Bài 2 — Truyền đối số và đọc kết quả.** Với `Function<? super Dog,? extends Animal>`, có thể truyền Dog, truyền Animal, hay đọc kết quả như Animal?

**Đáp án:** có thể truyền Dog, có thể đọc kết quả như Animal. Không bảo đảm có thể truyền một Animal bất kỳ, vì input thực tế có thể chính là Dog.

**Bài 3 — Supplier hay Consumer?** Một API yêu cầu nguồn tạo động vật; API khác đưa Dog cho callback in dữ liệu. Chọn dạng tham số nào?

**Đáp án:** nguồn tạo `Supplier<? extends Animal>`, hành động nhận Dog `Consumer<? super Dog>`.

**Bài 4 — Sửa chữ ký generic:**

~~~java
static <T,R> List<R> mapAll(
        List<T> source,
        Function<T,R> mapper) {
    return source.stream().map(mapper).toList();
}
~~~

Hãy viết phiên bản chấp nhận Function<Animal,String> để xử lý List<Dog>, có thể dùng đầu ra như List<CharSequence>.

**Đáp án:**

~~~java
static <T,R> List<R> mapAll(
        List<T> source,
        Function<? super T, ? extends R> mapper) {
    return source.stream().<R>map(mapper).toList();
}
~~~

**Bài 5 — Giải thích type witness.** Vì sao `.<R>map(mapper)` hữu ích trong implementation của `mapAll` dù mapper đã có kiểu `? extends R`?

**Đáp án:** type witness buộc phương thức generic `Stream.map` dùng đúng kiểu kết quả R của `mapAll`; nó tránh một số trường hợp suy luận thành một capture subtype chưa biết của R khiến `toList()` không được xem là List<R>. Việc chỉ rõ R vẫn an toàn theo hợp đồng `? extends R`.

## 15. Ghi nhớ

**Function<? super T, ? extends R>** là mẫu quan trọng nhất khi Java API **nhận một hàm**: caller đưa T vào, hàm có thể chấp nhận kiểu cha của T, và kết quả có thể dùng như R.

**Consumer / Predicate / Comparator<? super T>** có đầu vào tiêu thụ T; **Supplier<? extends T>** tạo ra giá trị T hoặc subtype; **BiFunction<? super T, ? super U, ? extends R>** có hai đầu vào tiêu thụ và một đầu ra sản xuất.

Hãy quyết định wildcard bằng hướng di chuyển của giá trị, không bằng tên lớp hoặc thói quen cú pháp. Kiểu generic cụ thể vẫn invariant; wildcard mở rộng **hợp đồng nhận hàm** mà không mất type safety. Nếu compiler gặp khó với capture và inference, hãy dùng generic helper, kiểu tường minh hoặc explicit type witness thích hợp thay vì raw type/cast không an toàn.
