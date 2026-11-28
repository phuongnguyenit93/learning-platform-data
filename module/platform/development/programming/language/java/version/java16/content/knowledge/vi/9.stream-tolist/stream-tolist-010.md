# Giới hạn suy luận generic khi gán kết quả vào `List` của supertype

Khi một `Stream<Dog>` gọi `toList()`, kiểu kết quả là `List<Dog>`. Java không tự đổi nó thành `List<Animal>` chỉ vì biến nhận có kiểu `List<Animal>`, dù `Dog` kế thừa `Animal`. Nguyên nhân là generic `List<T>` có tính bất biến về tham số kiểu (*invariant*), còn `Stream.toList()` trả về `List<T>` theo đúng kiểu phần tử `T` của stream. Ở đây *invariant* mô tả quan hệ subtype của kiểu generic, không có nghĩa collection là immutable hoặc unmodifiable.

Để nhận `List<Animal>`, hãy chuyển kiểu phần tử của stream sang `Animal` trước khi gọi `toList()`, hoặc dùng wildcard `List<? extends Animal>` nếu chỉ cần đọc các phần tử. `collect(Collectors.toList())` có thể suy luận kiểu đích khác trong một số phép gán vì `collect` là generic method nhận `Collector<? super T, A, R>`; điều này liên quan đến target type inference, không phải quy tắc chung rằng mọi `List<Dog>` đều có thể gán cho `List<Animal>`.

## 1. Vì sao phép gán `List<Dog>` sang `List<Animal>` không hợp lệ?

Giả sử có hệ thống kiểu đơn giản:

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}
```

Các ví dụ tiếp theo dùng lại ba class này.

Một `Dog` là một `Animal`, vì vậy có thể gán biến kiểu `Dog` cho biến kiểu `Animal`:

```java
Dog dog = new Dog();
Animal animal = dog; // Hợp lệ
```

Nhưng quan hệ kế thừa giữa các kiểu phần tử không tự mở rộng sang generic type:

```java
List<Dog> dogs = List.of(new Dog(), new Dog());
List<Animal> animals = dogs; // Lỗi biên dịch
```

`List<Dog>` không phải subtype của `List<Animal>`. Nếu phép gán trên được cho phép, đoạn mã sau sẽ có thể đưa một `Cat` vào danh sách vốn chỉ được thiết kế để chứa `Dog`:

```java
import java.util.ArrayList;
import java.util.List;

List<Dog> dogs = new ArrayList<>();
// Nếu List<Dog> được xem là List<Animal>, dòng sau sẽ làm hỏng bảo đảm kiểu:
// List<Animal> animals = dogs;
// animals.add(new Cat());
```

Vì vậy, Java giữ tính bất biến cho các kiểu generic như `List<T>`, `Collection<T>` và `Optional<T>`. Việc `Dog` kế thừa `Animal` không có nghĩa `List<Dog>` kế thừa `List<Animal>`.

## 2. `Stream.toList()` trả về đúng kiểu phần tử của stream

Chữ ký của `Stream.toList()` là:

```java
default List<T> toList()
```

`T` là tham số kiểu của `Stream<T>`. Phương thức `toList()` không khai báo một tham số kiểu mới để compiler có thể chọn một supertype dựa trên biến nhận.

```java
import java.util.List;

List<Dog> dogs = List.of(new Dog(), new Dog());
List<Dog> dogResult = dogs.stream().toList(); // Hợp lệ

List<Animal> animalResult = dogs.stream().toList();
// Lỗi biên dịch: List<Dog> không chuyển được thành List<Animal>
```

Kiểu của receiver đã là `Stream<Dog>`, nên kiểu trả về là `List<Dog>`. Kiểu đích `List<Animal>` không làm thay đổi tham số `T` của stream.

`var` cũng không tự mở rộng kiểu phần tử:

```java
var result = dogs.stream().toList();
// Kiểu được suy luận là List<Dog>

var collected = dogs.stream().collect(java.util.stream.Collectors.toList());
// Cũng suy luận List<Dog> vì không có target type List<Animal> ở đây.
```

`var` lấy kiểu tĩnh của biểu thức khởi tạo. Nó không yêu cầu compiler suy luận một supertype từ một khai báo biến có kiểu đích.

## 3. Chuyển stream sang supertype trước khi gọi `toList()`

Cách rõ ràng nhất là dùng `map()` để tạo một stream có kiểu phần tử là supertype mong muốn:

```java
import java.util.List;

List<Dog> dogs = List.of(new Dog(), new Dog());

List<Animal> animals = dogs.stream()
    .<Animal>map(dog -> dog)
    .toList();
```

`map()` là generic method có thể chọn kiểu kết quả `R`. Type witness `.<Animal>` nói rõ rằng pipeline sau phép ánh xạ là `Stream<Animal>`. Vì vậy, `toList()` trả về `List<Animal>`.

Có thể viết bằng cast trong lambda để biểu đạt cùng ý định:

```java
List<Animal> animals = dogs.stream()
    .map(dog -> (Animal) dog)
    .toList();
```

Cast này là widening reference conversion an toàn vì mọi `Dog` đều là `Animal`. Cách dùng type witness thường dễ đọc hơn khi mục tiêu là điều khiển kiểu generic của `map()`.

Nếu đang tạo stream từ đầu, cũng có thể chỉ định kiểu phần tử ngay tại factory:

```java
Animal first = new Dog();
Animal second = new Cat();

List<Animal> animals = java.util.stream.Stream.<Animal>of(first, second)
    .toList();
```

Ở đây stream được tạo trực tiếp dưới kiểu `Stream<Animal>`, nên kết quả là `List<Animal>`.

## 4. Dùng `List<? extends Animal>` khi chỉ cần đọc

Nếu mục đích là nhận một danh sách chứa các đối tượng thuộc `Animal` hoặc subtype của nó, và phương thức chỉ cần đọc phần tử, upper-bounded wildcard là lựa chọn phù hợp:

```java
import java.util.List;

List<Dog> dogs = List.of(new Dog(), new Dog());
List<? extends Animal> animals = dogs.stream().toList();

Animal first = animals.get(0); // Hợp lệ
```

`List<? extends Animal>` có thể tham chiếu tới `List<Dog>`, `List<Cat>` hoặc `List<Animal>`. Khi đọc phần tử, kiểu an toàn mà compiler biết là `Animal`.

Đổi lại, không thể thêm một `Dog` hay `Cat` tùy ý qua biến wildcard:

```java
import java.util.List;

List<Dog> dogs = List.of(new Dog(), new Dog());
List<? extends Animal> animals = dogs.stream().toList();

animals.add(new Dog()); // Lỗi biên dịch
animals.add(new Cat()); // Lỗi biên dịch
```

Compiler không biết kiểu cụ thể của wildcard là `Dog`, `Cat` hay một subtype khác. Chỉ `null` có thể được truyền vào về mặt kiểu, nhưng danh sách tạo bởi `Stream.toList()` vẫn unmodifiable và sẽ ném `UnsupportedOperationException` khi gọi mutator.

Lưu ý: wildcard chỉ giới hạn những thao tác mà compiler cho phép qua một tham chiếu. Nó không tự biến một collection mutable thành unmodifiable. Khả năng sửa đổi thực tế vẫn phụ thuộc vào object collection và hợp đồng API tạo ra nó.

## 5. Vì sao `collect(Collectors.toList())` có thể gán vào `List<Animal>`?

Đây là điểm khác biệt về chữ ký generic giữa hai terminal operation.

`Stream.collect(Collector)` có chữ ký rút gọn:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

Trong khi `Collectors.toList()` là generic method:

```java
static <T> Collector<T, ?, List<T>> toList()
```

Với `Stream<Dog>`, tham số `? super T` của `collect` cho phép collector nhận `Dog` hoặc một supertype của `Dog`. Kiểu kết quả `R` của `collect` cũng là type parameter của generic method và có thể được suy luận theo target type của phép gán.

Vì vậy, ví dụ sau hợp lệ:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Dog> dogs = List.of(new Dog(), new Dog());
List<Animal> animals = dogs.stream()
    .collect(Collectors.toList());
```

Có thể tách collector ra để thấy kiểu đích rõ hơn:

```java
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Collectors;

List<Dog> dogs = List.of(new Dog(), new Dog());

Collector<Animal, ?, List<Animal>> collector = Collectors.toList();
List<Animal> animals = dogs.stream().collect(collector);
```

Collector có thể nhận các phần tử `Dog` vì `Dog` là `Animal`, rồi tích lũy chúng vào `List<Animal>`. Điểm này không làm thay đổi tính bất biến của `List<T>`; nó là khả năng contravariant ở kiểu đầu vào `? super T` của `Collector` kết hợp với target type inference của generic method `collect`.

Tuy nhiên, không nên chọn `Collectors.toList()` chỉ để có một danh sách mutable. Hợp đồng của collector này không bảo đảm kiểu triển khai hoặc khả năng sửa đổi. Nếu cần `ArrayList` mutable, dùng `Collectors.toCollection(ArrayList::new)` sau khi đã chuyển stream sang kiểu phần tử mong muốn:

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

## 6. Chọn cách khai báo theo cách sử dụng kết quả

| Nhu cầu | Kiểu khai báo hoặc cách chuyển đổi | Ý nghĩa |
| --- | --- | --- |
| Giữ đúng kiểu phần tử của stream | `List<Dog> dogs = dogStream.toList()` | Kết quả là `List<Dog>`. |
| Chỉ đọc các phần tử như supertype | `List<? extends Animal> animals = dogStream.toList()` | Có thể đọc từng phần tử như `Animal`; không thể thêm subtype tùy ý. |
| Cần chính xác `List<Animal>` và không cần sửa đổi | `dogStream.<Animal>map(dog -> dog).toList()` | Đổi kiểu phần tử của stream trước khi thu thập. |
| Cần `List<Animal>` mutable | Widen bằng `map()` rồi `collect(toCollection(ArrayList::new))` | Tạo `ArrayList<Animal>` rõ ràng. |
| Dùng collector và muốn target type inference | `dogStream.collect(Collectors.toList())` trong ngữ cảnh gán `List<Animal>` | Hợp lệ nhờ chữ ký generic của `collect`; không bảo đảm mutability. |

Không ép kiểu không kiểm tra để né lỗi generic:

```java
// Không dùng cast raw/unchecked để biến List<Dog> thành List<Animal>:
// List<Animal> animals = (List<Animal>) (List<?>) dogStream.toList();
```

Cast này bỏ qua kiểm tra an toàn kiểu của compiler. Nó không chuyển đổi các phần tử hoặc tạo một collection có kiểu thực sự phù hợp; về sau, thao tác thêm và đọc có thể gây lỗi hoặc vi phạm hợp đồng của danh sách.

## 7. Thiết kế phương thức nhận danh sách từ nhiều subtype

Nếu phương thức chỉ đọc các đối tượng thuộc một hệ phân cấp, khai báo tham số với `? extends` để nhận được nhiều kiểu danh sách:

```java
import java.util.List;

class AnimalPrinter {
    static void printNames(List<? extends Animal> animals) {
        for (Animal animal : animals) {
            System.out.println(animal);
        }
    }
}
```

Phương thức có thể nhận `List<Dog>`, `List<Cat>` hoặc `List<Animal>`. Nếu phương thức phải thêm một `Animal` bất kỳ vào danh sách, tham số `List<Animal>` là hợp đồng khác và caller cần cung cấp đúng kiểu đó.

Quy tắc thực hành thường dùng là PECS: *Producer Extends, Consumer Super*. Khi chỉ đọc giá trị do collection cung cấp, `? extends Animal` phù hợp. Khi ghi các giá trị `Animal` vào một cấu trúc generic đầu vào, `? super Animal` thường phù hợp hơn. Đây là quy tắc thiết kế wildcard tổng quát; nó không thay đổi kiểu trả về cố định `List<T>` của `Stream.toList()`.

## 8. Những điểm cần nhớ

- `Dog` là subtype của `Animal`, nhưng `List<Dog>` không phải subtype của `List<Animal>`.
- `Stream<Dog>.toList()` trả về `List<Dog>` vì `toList()` trả `List<T>` theo kiểu phần tử của receiver.
- Target type của biến nhận không thể tự thay đổi `T` đã xác định trong `Stream<T>`.
- Dùng `.<Animal>map(...)` hoặc ánh xạ từng phần tử sang `Animal` trước `toList()` khi cần `List<Animal>`.
- Dùng `List<? extends Animal>` nếu chỉ cần đọc nhiều kiểu subtype qua một API chung.
- `collect(Collectors.toList())` có thể suy luận kiểu kết quả theo target type nhờ chữ ký generic của `collect`; điều đó không bảo đảm collection mutable.
- Không dùng raw type hoặc unchecked cast để vượt qua kiểm tra generic.

Hãy phân biệt kiểu của phần tử trong stream, kiểu generic của collection và target type của phép gán. Khi cần một danh sách chứa supertype, cách rõ ràng và ổn định nhất là chuyển kiểu phần tử của stream trước khi thu thập; dùng wildcard khi API chỉ cần đọc các subtype.

## Tài liệu tham khảo

- [Stream – Java SE 26 API (`toList()` và `collect()`)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Stream – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html)
- [Collectors.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toList())
- [Java Language Specification, §4.10 – Subtyping](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.10)
- [Java Language Specification, §18.5 – Type Inference](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-18.html#jls-18.5)
- [Type Inference – Dev.java](https://dev.java/learn/language/fp/generics/type-inference/)
