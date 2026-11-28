# Dùng type witness và `map()` để biểu đạt đúng kiểu đầu ra

`Stream.toList()` trả về `List<T>` theo kiểu phần tử `T` của stream đang gọi phương thức. Bản thân `toList()` không có tham số kiểu generic để yêu cầu compiler đổi `T` thành một supertype hoặc một kiểu kết quả khác. Khi muốn danh sách đầu ra mang kiểu cụ thể, hãy định hình kiểu của stream trước terminal operation.

`map()` là generic intermediate operation có thể tạo `Stream<R>`. Cú pháp type witness như `.<Animal>map(...)` cho phép chỉ rõ `R` ngay tại lời gọi. Cách này hữu ích khi muốn mở rộng kiểu phần tử từ subtype sang supertype, hoặc khi muốn biểu đạt rõ kiểu DTO/interface mà mapper tạo ra.

## 1. `map()` có thể thay đổi kiểu phần tử của stream

Chữ ký tổng quát của `map()`:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

Trong đó:

- `T` là kiểu phần tử của stream nguồn.
- `R` là kiểu phần tử của stream sau khi ánh xạ.
- `Function` nhận một giá trị tương thích với `T` và trả về một giá trị tương thích với `R`.

Ví dụ, stream nguồn là `Stream<String>` nhưng kết quả ánh xạ là `Stream<Integer>`:

```java
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

List<Integer> lengths = words.stream()
    .map(String::length)
    .toList();

System.out.println(lengths); // [4, 6, 3]
```

Ở đây compiler suy luận `R` là `Integer` từ giá trị mapper trả về. `toList()` nhận `Stream<Integer>`, vì vậy kết quả là `List<Integer>`.

## 2. Cú pháp type witness trên lời gọi `map()`

Type witness là cách viết tường minh tham số kiểu của một generic method. Với `map()`, đặt tham số kiểu sau dấu chấm và trước tên phương thức:

```java
stream.<Animal>map(mapper)
```

Không viết tham số kiểu sau tên phương thức như `stream.map<Animal>(...)`. Cũng không viết `stream.<Animal>toList()`, vì `toList()` không phải generic method độc lập; nó trả `List<T>` theo `T` đã có của stream.

Các ví dụ sau dùng lại mô hình kiểu:

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}
```

Khi stream có kiểu `Stream<Dog>`, ta có thể chỉ định `R` của `map()` là `Animal`:

```java
import java.util.List;

List<Dog> dogs = List.of(new Dog(), new Dog());

List<Animal> animals = dogs.stream()
    .<Animal>map(dog -> dog)
    .toList();
```

Phân tích kiểu qua từng bước:

1. `dogs.stream()` tạo `Stream<Dog>`, nên `T` của `map()` là `Dog`.
2. `.<Animal>map(...)` chỉ định `R` là `Animal`.
3. Lambda nhận `Dog` và trả lại chính object đó. `Dog` có thể gán cho `Animal`, nên mapper đáp ứng kiểu kết quả `R`.
4. Pipeline sau `map()` có kiểu `Stream<Animal>`.
5. `toList()` trả `List<Animal>`.

## 3. Type witness không phải cast và không tạo object mới

Hai cách dưới đây đều có thể biểu đạt stream `Stream<Animal>` từ nguồn `Stream<Dog>`:

```java
import java.util.List;

List<Dog> dogs = List.of(new Dog(), new Dog());

List<Animal> byTypeWitness = dogs.stream()
    .<Animal>map(dog -> dog)
    .toList();

List<Animal> byWideningCast = dogs.stream()
    .map(dog -> (Animal) dog)
    .toList();
```

Khác biệt nằm ở cách biểu đạt ý định:

- `.<Animal>map(...)` chỉ định tham số kiểu kết quả `R` của generic method `map()`.
- `(Animal) dog` là cast tham chiếu tường minh trong lambda. Đây là widening conversion an toàn vì `Dog` luôn là `Animal`.

Type witness không chuyển object `Dog` thành một object `Animal` khác, không gọi constructor và không thực hiện kiểm tra kiểu lúc chạy. Nó yêu cầu compiler kiểm tra mapper theo kiểu kết quả đã chọn. Khi lambda trả lại `dog`, phần tử trong stream vẫn là chính object `Dog` ban đầu; chỉ kiểu tĩnh mà pipeline công bố là `Animal`.

Nếu cần tạo object mới, hãy viết logic tạo object trong mapper. Type witness chỉ xác định kiểu `R`, còn việc tạo hay giữ object do lambda quyết định.

## 4. Kiểu kết quả có thể là interface hoặc supertype

Type witness không chỉ dùng với class cha. Nó cũng hữu ích khi muốn công bố kết quả thông qua một interface mà các phần tử nguồn đã triển khai:

```java
import java.util.List;

interface Named {
    String name();
}

record User(String name) implements Named {}

List<User> users = List.of(new User("An"), new User("Bình"));

List<Named> namedUsers = users.stream()
    .<Named>map(user -> user)
    .toList();
```

Các object trong danh sách vẫn là `User`, nhưng người sử dụng kết quả chỉ phụ thuộc vào hợp đồng `Named`. Điều này giúp giảm phụ thuộc vào implementation cụ thể và làm API linh hoạt hơn.

## 5. Dùng type witness khi mapper tạo DTO hoặc kiểu kết quả khác

Kiểu `R` không bắt buộc phải là supertype của `T`. `map()` có thể chuyển phần tử nguồn thành một kiểu không liên quan trong hệ kế thừa, miễn mapper trả về giá trị tương thích với `R`.

```java
import java.util.List;

record DogProfile(String name, int age) {}
record DogSummary(String label) {}

List<DogProfile> dogs = List.of(
    new DogProfile("Milo", 3),
    new DogProfile("Luna", 5)
);

List<DogSummary> summaries = dogs.stream()
    .<DogSummary>map(dog -> new DogSummary(
        dog.name() + " (" + dog.age() + " tuổi)"
    ))
    .toList();

System.out.println(summaries);
// [DogSummary[label=Milo (3 tuổi)], DogSummary[label=Luna (5 tuổi)]]
```

Trong ví dụ này, `T` là `DogProfile`, `R` là `DogSummary`. Lambda tạo một `DogSummary` mới cho mỗi phần tử. Type witness giúp thể hiện rõ kiểu stream sau ánh xạ và kiểu danh sách mà `toList()` sẽ trả về.

Nếu kiểu trả về của mapper đã đủ rõ để compiler suy luận chính xác, không bắt buộc phải thêm type witness. Hãy dùng nó khi muốn cố định hoặc làm rõ `R`, đặc biệt trong pipeline generic dài hoặc khi kiểu kết quả cần khớp với hợp đồng API.

## 6. Có thể chỉ định kiểu ngay khi tạo stream

Nếu đang tạo stream từ các phần tử thuộc nhiều subtype, có thể chỉ định kiểu tham số ngay ở factory method:

```java
import java.util.List;
import java.util.stream.Stream;

Animal dog = new Dog();
Animal cat = new Cat();

List<Animal> animals = Stream.<Animal>of(dog, cat).toList();
```

Type witness `.<Animal>` ở đây áp dụng cho `Stream.of(...)`, làm cho stream ngay từ đầu có kiểu `Stream<Animal>`. Đây là lựa chọn phù hợp khi các phần tử được tập hợp trực tiếp vào một stream có kiểu chung. Nếu stream đã tồn tại dưới kiểu `Stream<Dog>`, dùng `.<Animal>map(...)` để mở rộng kiểu phần tử trước khi thu thập.

## 7. `map()` phải trả về giá trị tương thích với kiểu đã chỉ định

Type witness không bỏ qua kiểm tra kiểu. Nếu chỉ định `R` quá hẹp so với kiểu mapper trả về, chương trình vẫn không biên dịch.

```java
import java.util.List;

List<Dog> dogs = List.of(new Dog());

List<Dog> sameType = dogs.stream()
    .<Dog>map(dog -> dog)
    .toList(); // Hợp lệ

List<Dog> invalid = dogs.stream()
    .<Dog>map(dog -> new Animal())
    .toList(); // Lỗi biên dịch: Animal không phải Dog
```

Trong ví dụ lỗi, mapper được yêu cầu trả về `Dog`, nhưng lại tạo `Animal` bất kỳ. Compiler từ chối vì một `Animal` có thể là `Cat`, không bảo đảm là `Dog`.

Ngược lại, nếu chọn `R` là `Animal`, mapper có thể trả về `Dog`, `Cat` hoặc một object thuộc subtype khác:

```java
List<Animal> animals = dogs.stream()
    .<Animal>map(dog -> dog)
    .toList();
```

## 8. Phân biệt kiểu phần tử, kiểu collection và khả năng sửa đổi

Type witness điều khiển kiểu phần tử của stream sau `map()`. Nó không thay đổi các thuộc tính khác của collection:

- `Stream<Dog>` sau `.<Animal>map(...)` trở thành `Stream<Animal>` về mặt kiểu tĩnh.
- `toList()` trên stream đó trả `List<Animal>`.
- Danh sách vẫn unmodifiable theo hợp đồng của `Stream.toList()`.
- Type witness không làm danh sách mutable và cũng không làm các object phần tử immutable.

Nếu bên nhận cần danh sách mutable, có thể thu thập sau khi đã định hình kiểu đầu ra:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<Dog> dogs = List.of(new Dog(), new Dog());

List<Animal> animals = dogs.stream()
    .<Animal>map(dog -> dog)
    .collect(Collectors.toCollection(ArrayList::new));

animals.add(new Cat()); // Hợp lệ
```

Ở đây `map()` quyết định kiểu phần tử `Animal`; `toCollection(ArrayList::new)` quyết định loại collection mutable.

## 9. Khi nào nên dùng type witness?

| Tình huống | Cách viết | Lý do |
| --- | --- | --- |
| Muốn giữ nguyên kiểu phần tử | `stream.map(mapper).toList()` | Để compiler tự suy luận từ mapper. |
| Muốn công bố subtype qua supertype | `dogStream.<Animal>map(dog -> dog).toList()` | Chỉ định rõ kiểu phần tử đầu ra. |
| Muốn công bố qua interface | `userStream.<Named>map(user -> user).toList()` | Giảm phụ thuộc vào implementation cụ thể. |
| Muốn chuyển entity thành DTO | `dogStream.<DogSummary>map(this::toSummary).toList()` | Nêu rõ kiểu dữ liệu sau ánh xạ. |
| Tạo stream từ nhiều subtype | `Stream.<Animal>of(dog, cat).toList()` | Xác định kiểu chung ngay tại nguồn. |
| Cần mutable collection | Widen bằng `map()`, rồi `collect(toCollection(ArrayList::new))` | Tách quyết định kiểu phần tử khỏi quyết định loại collection. |

Không thêm type witness chỉ để làm code dài hơn. Khi compiler đã suy luận đúng kiểu và kiểu đó diễn đạt đủ ý định, để compiler suy luận là cách viết gọn. Type witness có giá trị khi nó làm rõ hợp đồng kiểu mà pipeline phải tạo ra.

## 10. Những điểm cần nhớ

- `Stream.toList()` trả `List<T>` theo kiểu phần tử của stream receiver; không thể truyền type argument trực tiếp cho `toList()`.
- `map()` có tham số kiểu kết quả `R`, nên có thể tạo `Stream<R>` từ `Stream<T>`.
- Viết explicit type witness trước tên phương thức: `stream.<Animal>map(...)`.
- Mapper phải trả về giá trị tương thích với `R`; type witness không bỏ qua kiểm tra kiểu.
- Dùng `.<Supertype>map(value -> value)` để biểu đạt widening mà không cần cast.
- Type witness không tạo object mới và không thay đổi object lúc chạy.
- Kiểu phần tử, khả năng sửa đổi của danh sách và tính bất biến của object là các thuộc tính riêng biệt.

Hãy dùng `map()` để định hình kiểu dữ liệu mà pipeline cần xuất ra, và dùng type witness khi muốn nói rõ kiểu kết quả generic cho compiler cũng như người đọc. Sau đó, chọn `toList()` hoặc collector khác theo hợp đồng collection mà bên nhận cần.

## Tài liệu tham khảo

- [Stream.map() và Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html)
- [Stream.map() và Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Function – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Function.html)
- [Java Language Specification, §15.12 – Method Invocation Expressions](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.12)
- [Java Language Specification, §18 – Type Inference](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-18.html)
