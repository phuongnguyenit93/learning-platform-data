# Phân biệt `Stream.toList` với `Collectors.toList` trong Java 17

## 1. Vì sao có hai cách chuyển Stream thành List?

Stream API cung cấp hai cách quen thuộc để thu các phần tử thành một danh sách:

~~~java
List<String> a = names.stream()
        .filter(name -> !name.isBlank())
        .toList();

List<String> b = names.stream()
        .filter(name -> !name.isBlank())
        .collect(Collectors.toList());
~~~

Cả hai đều trả về một đối tượng có kiểu khai báo `List<String>`, nhưng **hợp đồng của hai API khác nhau**:

- `Stream.toList()` có từ Java 16 và trả về một `List` **không sửa đổi được** (*unmodifiable*).
- `Collectors.toList()` có từ Java 8 và là một `Collector` được truyền cho `collect`. Tài liệu API **không cam kết** kiểu triển khai, tính sửa đổi được, khả năng tuần tự hóa hay tính an toàn luồng của danh sách kết quả.

Vì vậy, không nên chọn chỉ theo thói quen hoặc dựa vào việc một phiên bản JDK hiện tại có vẻ trả về `ArrayList`. Hãy chọn theo điều mà chương trình cần bảo đảm: danh sách không sửa đổi được, danh sách có thể thay đổi, hay một kiểu collection cụ thể.

Sau bài học, người học cần:

1. Phân biệt phương thức `Stream.toList()` với collector `Collectors.toList()`.
2. Nêu chính xác khác biệt về khả năng sửa đổi và bảo đảm của API.
3. Biết dùng `Collectors.toCollection(ArrayList::new)` khi cần một `ArrayList` có thể sửa đổi.
4. Biết dùng `Collectors.toUnmodifiableList()` khi muốn collector tạo danh sách không sửa đổi được.
5. Hiểu thứ tự phần tử, xử lý phần tử null, tính bất biến nông và vòng đời một lần sử dụng của Stream.
6. Chọn API phù hợp với Java 17 và mức tương thích JDK của dự án.

## 2. Hai API khác nhau về vai trò

### 2.1. `Stream.toList()`

`toList()` là **terminal operation** được khai báo trực tiếp trên interface `Stream<T>`. Nó tiêu thụ stream và trả về một danh sách:

~~~java
List<Integer> numbers = Stream.of(3, 1, 4, 1, 5)
        .filter(n -> n % 2 == 1)
        .toList();

System.out.println(numbers); // [3, 1, 1, 5]
~~~

Kiểu trả về là `List<T>`. Danh sách kết quả không sửa đổi được: gọi các phương thức thay đổi nội dung như `add`, `remove`, `set`, `clear` hoặc các phương thức mutator tương ứng sẽ ném `UnsupportedOperationException`.

~~~java
List<String> names = Stream.of("An", "Binh").toList();

// names.add("Chi"); // UnsupportedOperationException
// names.set(0, "Anh"); // UnsupportedOperationException
~~~

Phương thức này phù hợp khi muốn thu kết quả của pipeline và công bố một danh sách mà người nhận không thể thêm, xóa hoặc thay thế phần tử qua API List.

Javadoc cũng lưu ý danh sách trả về có thể là một **value-based object**. Không nên dựa vào identity của instance, so sánh nó bằng `==`, dùng `System.identityHashCode` hoặc đồng bộ hóa (`synchronized`) trên chính instance đó. Hãy so sánh nội dung bằng `equals` và dùng một đối tượng khóa riêng nếu cần synchronization.

### 2.2. `Collectors.toList()`

`Collectors.toList()` là một **factory method** của lớp tiện ích `java.util.stream.Collectors`. Nó trả về một `Collector`; collector này được đưa vào terminal operation `Stream.collect(...)`:

~~~java
List<Integer> numbers = Stream.of(3, 1, 4, 1, 5)
        .filter(n -> n % 2 == 1)
        .collect(Collectors.toList());
~~~

Điểm quan trọng là `Collectors.toList()` **không trực tiếp trả về List**. Nó trả về đối tượng mô tả cách thu thập phần tử của stream thành một list. `collect` mới là thao tác tiêu thụ stream và trả danh sách.

Javadoc của `Collectors.toList()` nêu rõ rằng không có bảo đảm về:

- Kiểu triển khai cụ thể của danh sách.
- Danh sách có sửa đổi được hay không.
- Khả năng tuần tự hóa.
- Tính an toàn khi nhiều luồng cùng truy cập.

Nếu cần kiểm soát rõ hơn kiểu danh sách đầu ra, tài liệu API hướng tới `Collectors.toCollection(Supplier)`.

### 2.3. Bảng so sánh trực tiếp

| Tiêu chí | `Stream.toList()` | `Collectors.toList()` |
|---|---|---|
| Có từ phiên bản | Java 16 | Java 8 |
| Cách gọi | `stream.toList()` | `stream.collect(Collectors.toList())` |
| Vai trò | Terminal operation của Stream | Factory tạo Collector |
| Kiểu trả về của lời gọi chính | `List<T>` | `Collector<T, ?, List<T>>` |
| Khả năng sửa đổi của List kết quả | **Không sửa đổi được** | **Không được API bảo đảm** |
| Kiểu triển khai cụ thể | Không được cam kết | Không được cam kết |
| Encounter order | Giữ thứ tự nếu stream có encounter order | Giữ thứ tự nếu stream có encounter order |
| Có thể dùng với parallel stream | Có | Có |
| Cần Java 17 | Có | Có |
| Dùng khi | Muốn một List không sửa đổi được, cách gọi ngắn | Đang dùng collector hoặc cần kết hợp với collector khác; không dựa vào mutability |

**Quy tắc lựa chọn:** nếu cần List không sửa đổi được, `Stream.toList()` diễn đạt trực tiếp ý định. Nếu cần một List mutable, đừng mặc định `Collectors.toList()` luôn tạo `ArrayList`; hãy yêu cầu collection cụ thể bằng `toCollection`.

## 3. Ví dụ chứng minh khác biệt về khả năng sửa đổi

### 3.1. Danh sách từ `Stream.toList()`

~~~java
import java.util.List;
import java.util.stream.Stream;

public class Main {
    public static void main(String[] args) {
        List<String> result = Stream.of("red", "green", "blue")
                .toList();

        System.out.println(result); // [red, green, blue]

        // result.add("black"); // UnsupportedOperationException
    }
}
~~~

Danh sách vẫn đọc được, duyệt được, lấy kích thước và truyền cho các phương thức nhận `List`. Điều bị chặn là các thao tác sửa đổi cấu trúc hoặc thay thế phần tử.

### 3.2. Danh sách từ `Collectors.toList()`

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Main {
    public static void main(String[] args) {
        List<String> result = Stream.of("red", "green", "blue")
                .collect(Collectors.toList());

        System.out.println(result);
    }
}
~~~

Không nên viết logic phụ thuộc vào việc đoạn mã này có thể gọi `result.add(...)` thành công. JDK hiện tại có thể trả về một implementation mutable, nhưng hợp đồng của `Collectors.toList()` không cam kết điều đó. Một implementation khác hoàn toàn có thể trả về List không sửa đổi được mà vẫn phù hợp với API.

### 3.3. Khi thật sự cần một `ArrayList` mutable

Hãy chỉ định implementation bằng `Collectors.toCollection`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Binh")
        .collect(Collectors.toCollection(ArrayList::new));

names.add("Chi");
names.set(0, "Anh");

System.out.println(names); // [Anh, Binh, Chi]
~~~

Ở đây, supplier `ArrayList::new` yêu cầu tạo `ArrayList` để thu thập. Ý định về kiểu và khả năng sửa đổi đã được thể hiện tường minh.

Nếu chỉ cần một List mutable nhưng không quan trọng implementation, có thể dùng một collection mutable phù hợp khác. Điều quan trọng là **đừng dùng một bảo đảm mà API không cung cấp**.

### 3.4. Tạo bản sao mutable từ danh sách không sửa đổi được

Nếu đã có kết quả từ `Stream.toList()` nhưng sau đó cần sửa đổi:

~~~java
List<String> immutableResult = Stream.of("An", "Binh").toList();
List<String> editable = new ArrayList<>(immutableResult);

editable.add("Chi");
~~~

`new ArrayList<>(...)` tạo một list mới có thể sửa đổi. Đây là bản sao **nông**: các phần tử bên trong vẫn là những object được tham chiếu từ danh sách ban đầu.

## 4. Không nhầm “không sửa đổi được” với bất biến sâu

`Stream.toList()` trả về List không sửa đổi được. Điều này nói về **cấu trúc của danh sách**, không có nghĩa mọi object nằm trong danh sách cũng bất biến.

Ví dụ:

~~~java
import java.util.List;

class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String newName) {
        this.name = newName;
    }

    String name() {
        return name;
    }
}

Person person = new Person("An");
List<Person> people = List.of(person);

person.rename("Anh");
System.out.println(people.get(0).name()); // Anh
~~~

Danh sách không cho phép thay phần tử hoặc thêm phần tử, nhưng object `Person` bên trong vẫn có thể thay đổi trạng thái. Cả `Stream.toList()` lẫn `Collectors.toUnmodifiableList()` đều không tự tạo bản sao sâu của các phần tử.

Nếu muốn dữ liệu không thay đổi xuyên suốt, cần thiết kế các phần tử theo hướng immutable, tạo bản sao phòng vệ hoặc chuyển sang kiểu dữ liệu có hợp đồng bất biến phù hợp.

## 5. `Collectors.toUnmodifiableList()`: lựa chọn thứ ba

Java 17 có thêm lựa chọn `Collectors.toUnmodifiableList()`, được bổ sung từ Java 10. Nó tạo một collector cho danh sách không sửa đổi được:

~~~java
List<String> names = Stream.of("An", "Binh", "Chi")
        .collect(Collectors.toUnmodifiableList());

// names.add("Dung"); // UnsupportedOperationException
~~~

Vì vậy, nếu so sánh ba lựa chọn:

| API | Hợp đồng về mutability | Ghi chú |
|---|---|---|
| `Stream.toList()` | Unmodifiable | Terminal operation ngắn gọn từ Java 16 |
| `Collectors.toList()` | Không có bảo đảm | Không phụ thuộc vào việc có thể sửa đổi |
| `Collectors.toUnmodifiableList()` | Unmodifiable | Collector tường minh cho kết quả không sửa đổi được |

`Collectors.toUnmodifiableList()` không chấp nhận phần tử `null`; nếu quá trình thu thập gặp null, nó ném `NullPointerException`. Với `Stream.toList()` và `Collectors.toList()`, không nên tự suy ra một chính sách null chung từ implementation đang chạy; nếu null là một phần của hợp đồng dữ liệu, hãy xác thực và quy định rõ hành vi.

### 5.1. Khi nào dùng lựa chọn nào?

- Dùng `stream.toList()` khi cần thu kết quả và muốn List không sửa đổi được.
- Dùng `collect(Collectors.toUnmodifiableList())` khi đang xây dựng pipeline collector và muốn nêu rõ chính sách kết quả unmodifiable; nhớ rằng collector này từ chối null.
- Dùng `collect(Collectors.toCollection(ArrayList::new))` khi cần một ArrayList mutable.
- Dùng `collect(Collectors.toList())` khi cần một collector list tổng quát và không phụ thuộc vào kiểu cụ thể hay mutability.

Không cần chuyển mọi `Collectors.toList()` cũ sang `Stream.toList()` một cách máy móc. Hãy xem các đoạn code phía sau có đang sửa danh sách, dựa vào implementation, hoặc cần tương thích JDK thấp hơn không.

## 6. Thứ tự phần tử và encounter order

Một stream có thể có **encounter order** (thứ tự gặp phần tử) hoặc không. Với nguồn có thứ tự như `List`, cả hai cách thu thập đều giữ thứ tự nếu pipeline vẫn duy trì encounter order.

~~~java
List<Integer> source = List.of(5, 2, 9, 1);

List<Integer> a = source.stream()
        .filter(n -> n > 1)
        .toList();

List<Integer> b = source.stream()
        .filter(n -> n > 1)
        .collect(Collectors.toList());

System.out.println(a); // [5, 2, 9]
System.out.println(b); // [5, 2, 9]
~~~

Không nên hiểu rằng List đầu ra luôn được sắp xếp tăng dần. Thu thập thành List giữ thứ tự gặp phần tử, không tự gọi `sorted()`.

### 6.1. Stream không có encounter order

Với nguồn không có thứ tự như `HashSet`, hoặc sau khi gọi `unordered()`, không nên dựa vào thứ tự cụ thể của các phần tử trong List:

~~~java
List<String> values = someSet.stream()
        .unordered()
        .toList();
~~~

Kết quả vẫn là List, nhưng không có bảo đảm rằng thứ tự tương ứng với thứ tự chèn hoặc một thứ tự cụ thể nào khác. Nếu thứ tự là yêu cầu nghiệp vụ, hãy dùng nguồn có thứ tự hoặc sắp xếp tường minh:

~~~java
List<String> sorted = someSet.stream()
        .sorted()
        .toList();
~~~

### 6.2. Parallel stream

Cả `toList()` và `collect(Collectors.toList())` đều có thể dùng với parallel stream:

~~~java
List<Integer> values = IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .toList();
~~~

Nếu nguồn có encounter order và pipeline giữ thứ tự, các terminal operation trên bảo toàn thứ tự đó trong kết quả. Với stream unordered, không nên giả định thứ tự cụ thể.

Không tự tạo một `ArrayList` bên ngoài rồi gọi `forEach` song song để thêm phần tử:

~~~java
// Không an toàn khi nhiều thread cùng add vào ArrayList:
// List<Integer> result = new ArrayList<>();
// IntStream.range(0, 1000).parallel().forEach(result::add);
~~~

Hãy để Stream framework thực hiện reduction bằng `toList` hoặc collector phù hợp. `Collectors.toList()` không cần phải là concurrent collector để có thể dùng an toàn trong phép thu thập song song do framework quản lý.

## 7. Stream là một lần sử dụng

`toList()` và `collect(...)` đều là **terminal operation**. Sau khi đã tiêu thụ stream, không thể dùng lại cùng instance để tạo một danh sách khác:

~~~java
Stream<String> stream = Stream.of("A", "B", "C");

List<String> first = stream.toList();

// List<String> second = stream.collect(Collectors.toList());
// IllegalStateException: stream đã được vận hành/đóng.
~~~

Nếu cần hai kết quả độc lập, hãy tạo stream mới từ nguồn có thể duyệt lại:

~~~java
List<String> source = List.of("A", "B", "C");

List<String> first = source.stream().toList();
List<String> second = source.stream().collect(Collectors.toList());
~~~

Không phải mọi nguồn stream đều có thể tạo lại. Ví dụ stream đọc từ một input hoặc nguồn bên ngoài có thể gắn với tài nguyên chỉ mở một lần; khi đó hãy quyết định thu thập một lần rồi tái sử dụng List, hoặc mở lại nguồn theo API của nó.

## 8. Stream pipeline và cách chọn terminal operation

Hai cách thu thập đều ở cuối pipeline, sau các intermediate operation như `filter`, `map`, `distinct`, `sorted`:

~~~java
List<String> result = orders.stream()
        .filter(order -> order.total() > 0)
        .map(Order::code)
        .distinct()
        .sorted()
        .toList();
~~~

Nếu cần một List không sửa đổi được, `toList()` phù hợp. Nếu pipeline cần collector khác như grouping, partitioning hoặc mapping, dùng các collector chuyên biệt:

~~~java
Map<String, List<Order>> byCustomer = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));
~~~

Không phải mọi thao tác thu thập đều nên kết thúc bằng List. Chọn terminal operation phản ánh dạng kết quả cần có:

| Nhu cầu | Terminal operation |
|---|---|
| List không sửa đổi được | `stream.toList()` |
| Collector List tổng quát | `stream.collect(Collectors.toList())` |
| ArrayList mutable | `stream.collect(Collectors.toCollection(ArrayList::new))` |
| List không sửa đổi được qua Collector, không cho null | `stream.collect(Collectors.toUnmodifiableList())` |
| Set | `stream.collect(Collectors.toSet())` hoặc collector cụ thể hơn |
| Map | `stream.collect(Collectors.toMap(...))` |
| Mảng | `stream.toArray(...)` |
| Tổng/đếm/thống kê | `sum()`, `count()`, `summaryStatistics()` với primitive stream phù hợp |

## 9. Tương thích phiên bản Java

`Collectors.toList()` có từ Java 8, còn `Stream.toList()` được bổ sung trong Java 16. Vì vậy:

- Dự án có target Java 17 có thể dùng cả hai.
- Dự án phải chạy trên Java 8 hoặc Java 11 không thể gọi `Stream.toList()`.
- Nếu compile với `javac --release 11`, lời gọi `Stream.toList()` sẽ không được nhận diện trong API mục tiêu.
- `Collectors.toList()` vẫn là lựa chọn tương thích cho code cần hỗ trợ JDK cũ hơn, nhưng không nên dựa vào khả năng sửa đổi của danh sách.

Ví dụ compile với Java 17:

~~~bash
javac --release 17 Main.java
java Main
~~~

Không cần bật preview cho bất kỳ API nào trong bài này.

## 10. Hiệu năng: đừng chọn chỉ dựa vào phỏng đoán

`Stream.toList()` là phương thức trực tiếp trên Stream và implementation có thể tối ưu dựa trên nguồn stream. `Collectors.toList()` đi qua cơ chế collector. Tuy nhiên, API không cam kết một mức hiệu năng cụ thể hoặc một implementation nội bộ nhất định cho mọi JDK.

Khi lựa chọn:

1. Ưu tiên đúng hợp đồng mutability và kiểu kết quả.
2. Giữ pipeline dễ đọc và tránh thu thập dữ liệu nếu chỉ cần một phép tổng hợp.
3. Nếu hiệu năng thực sự quan trọng, benchmark trên JDK và dữ liệu đại diện của ứng dụng; không suy luận chỉ từ số lượng lời gọi API.
4. Tránh gọi `toList()` rồi sao chép sang List khác nếu có thể thu trực tiếp vào collection đích.

Ví dụ, nếu cần mutable `ArrayList` ngay từ đầu:

~~~java
List<String> result = source.stream()
        .filter(this::accepted)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Không cần tạo một List unmodifiable trung gian bằng `toList()` rồi mới copy vào `ArrayList`.

## 11. Ví dụ tổng hợp chạy trên Java 17

Chương trình sau minh họa cả ba cách: `Stream.toList()`, `Collectors.toList()` và `Collectors.toCollection(ArrayList::new)`.

Tạo tệp `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Main {
    public static void main(String[] args) {
        List<String> source = List.of("An", "Binh", "Chi");

        // List không sửa đổi được theo hợp đồng Stream.toList().
        List<String> unmodifiable = source.stream()
                .filter(name -> !name.isBlank())
                .toList();

        // Collector tổng quát; mutability không được bảo đảm.
        List<String> collected = source.stream()
                .filter(name -> !name.isBlank())
                .collect(Collectors.toList());

        // Yêu cầu rõ một ArrayList mutable.
        ArrayList<String> editable = source.stream()
                .filter(name -> !name.isBlank())
                .collect(Collectors.toCollection(ArrayList::new));

        System.out.println(unmodifiable);
        System.out.println(collected);
        editable.add("Dung");
        System.out.println(editable);

        // Collector unmodifiable, từ chối phần tử null.
        List<String> fixed = Stream.of("Java", "17")
                .collect(Collectors.toUnmodifiableList());
        System.out.println(fixed);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 Main.java
java Main
~~~

Kết quả:

~~~text
[An, Binh, Chi]
[An, Binh, Chi]
[An, Binh, Chi, Dung]
[Java, 17]
~~~

Không có phép thử nào ở đây dựa vào việc `collected` có thể sửa đổi hay không, vì hợp đồng `Collectors.toList()` không bảo đảm điều đó. Chỉ `editable` được tạo với supplier `ArrayList::new` nên mã có thể dựa vào khả năng thêm phần tử.

## 12. Các lỗi thường gặp

### 12.1. Nghĩ rằng `Collectors.toList()` luôn trả về ArrayList

Không có bảo đảm này trong Javadoc. Nếu mã cần `ArrayList`, hãy dùng `Collectors.toCollection(ArrayList::new)`.

### 12.2. Gọi `add` trên kết quả `Stream.toList()`

~~~java
List<Integer> numbers = Stream.of(1, 2, 3).toList();
// numbers.add(4); // UnsupportedOperationException
~~~

Nếu cần sửa đổi, tạo bản sao mutable hoặc thu thập ngay bằng `toCollection`.

### 12.3. Cho rằng unmodifiable đồng nghĩa với deep immutable

Danh sách không cho thay đổi vị trí phần tử, nhưng object bên trong có thể vẫn mutable. Thiết kế bất biến cần xét cả phần tử và các tham chiếu có thể truy cập từ bên ngoài.

### 12.4. Dùng lại cùng stream

Một stream chỉ được tiêu thụ một lần. Hãy tạo pipeline mới từ nguồn có thể duyệt lại hoặc lưu kết quả vào collection rồi sử dụng collection đó.

### 12.5. Giả định thứ tự khi nguồn unordered

List đầu ra không tự tạo ra một thứ tự nghiệp vụ. Nếu cần sắp xếp, dùng `sorted()` hoặc một nguồn có encounter order.

### 12.6. Bỏ qua khác biệt phiên bản

`Stream.toList()` không có trong Java 8/11. Nếu thư viện phải hỗ trợ các runtime đó, cần chọn API tương thích hoặc nâng baseline JDK theo quyết định của dự án.

### 12.7. Dùng `Collectors.toUnmodifiableList()` khi dữ liệu có null

Collector này từ chối null. Nếu dữ liệu có thể chứa null, hãy xác định chính sách: từ chối đầu vào, loại bỏ bằng `filter(Objects::nonNull)` hoặc chọn collection có hợp đồng null phù hợp.

## 13. Bài tập thực hành

### Bài 1 — Chọn API theo yêu cầu

Với mỗi yêu cầu, chọn API phù hợp:

1. Thu một pipeline thành List chỉ để trả về cho caller đọc.
2. Thu thành một `ArrayList` rồi tiếp tục `add` và `remove`.
3. Cần hỗ trợ Java 11.
4. Cần một List unmodifiable qua collector và dữ liệu không có null.

**Gợi ý đáp án:**

1. `stream.toList()`.
2. `collect(Collectors.toCollection(ArrayList::new))`.
3. `collect(Collectors.toList())` hoặc collector phù hợp có từ Java 8.
4. `collect(Collectors.toUnmodifiableList())`.

### Bài 2 — Dự đoán lỗi

~~~java
List<Integer> values = Stream.of(1, 2, 3).toList();
values.remove(Integer.valueOf(2));
~~~

Điều gì xảy ra?

**Đáp án:** thao tác ném `UnsupportedOperationException` vì List trả về từ `Stream.toList()` không sửa đổi được.

### Bài 3 — Viết kết quả mutable rõ ràng

Viết pipeline lọc các số dương từ `List<Integer> source` và thu vào `ArrayList<Integer>` để sau đó thêm số 0.

~~~java
ArrayList<Integer> result = source.stream()
        .filter(n -> n > 0)
        .collect(Collectors.toCollection(ArrayList::new));
result.add(0);
~~~

### Bài 4 — So sánh thứ tự

Cho nguồn `List.of(4, 1, 3, 2)`. Thu thập bằng hai cách rồi giải thích vì sao cả hai đều có thứ tự `[4, 1, 3, 2]` nếu không có thao tác làm thay đổi encounter order. Sau đó thêm `sorted()` và dự đoán kết quả.

**Đáp án:** ban đầu cả hai giữ thứ tự nguồn; sau `sorted()`, kết quả là `[1, 2, 3, 4]`.

### Bài 5 — Phân biệt list unmodifiable và phần tử mutable

Tạo một lớp `Counter` có phương thức tăng giá trị. Đặt một instance trong kết quả `stream.toList()`; thử thêm một phần tử mới và thử tăng giá trị của Counter hiện có. Giải thích tại sao thao tác thứ nhất bị chặn nhưng thao tác thứ hai vẫn có thể thành công.

**Đáp án:** List không cho thay đổi cấu trúc, nhưng tham chiếu đến object `Counter` vẫn trỏ đến cùng object mutable. Unmodifiable List không phải deep immutable.

### Bài 6 — Kiểm tra tương thích Java

Giải thích vì sao `Stream.toList()` biên dịch được với `--release 17` nhưng không có trong API mục tiêu `--release 11`. Viết lại bằng `collect(Collectors.toList())` cho dự án cần Java 11.

## 14. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Nêu đúng phiên bản giới thiệu: `Collectors.toList()` từ Java 8, `Stream.toList()` từ Java 16.
2. Giải thích `Stream.toList()` trả về List unmodifiable.
3. Giải thích `Collectors.toList()` không cam kết kiểu triển khai, mutability, serializability hoặc thread-safety.
4. Viết đúng `stream.collect(Collectors.toList())` và phân biệt nó với `stream.toList()`.
5. Dùng `Collectors.toCollection(ArrayList::new)` khi cần ArrayList mutable.
6. Phân biệt `Collectors.toUnmodifiableList()` và chính sách null của nó.
7. Giải thích encounter order, parallel stream và stream chỉ tiêu thụ một lần.
8. Phân biệt unmodifiable collection với deep immutability của các phần tử.
9. Chọn API phù hợp với yêu cầu tương thích JDK 17 hoặc runtime cũ hơn.

## 15. Tài liệu chính thức

- [Java SE 17 API — `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): hợp đồng List unmodifiable, value-based caveat và thứ tự phần tử.
- [Java SE 17 API — `Collectors.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()): collector List và các giới hạn bảo đảm về kiểu/mutability.
- [Java SE 17 API — `Collectors.toCollection(Supplier)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)): chỉ định collection implementation cần tạo.
- [Java SE 17 API — `Collectors.toUnmodifiableList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector tạo List unmodifiable.

**Ghi nhớ:** `Stream.toList()` bảo đảm một List không sửa đổi được; `Collectors.toList()` chỉ yêu cầu thu thập thành List mà không cam kết implementation hoặc mutability; `Collectors.toCollection(ArrayList::new)` là cách chỉ định rõ ArrayList mutable. Hãy chọn theo hợp đồng cần có và kiểm tra mức Java mục tiêu của dự án.
