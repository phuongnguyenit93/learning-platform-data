# Wildcard giới hạn dưới với ? super T

## 1. Khái niệm: nhận một nơi có thể chứa giá trị T

Giả sử một phương thức cần đưa các số nguyên vào danh sách. Nếu tham số bắt buộc là `List<Integer>`, phương thức không nhận trực tiếp được một `List<Number>` hoặc `List<Object>`, dù hai danh sách đó có thể chứa `Integer` an toàn.

Wildcard giới hạn dưới giải quyết yêu cầu này:

```java
// Phương thức minh họa; cần import java.util.List.
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Đọc `List<? super Integer>` là:

> Một danh sách có kiểu phần tử cụ thể chưa biết, nhưng kiểu ấy là Integer hoặc một kiểu cha phù hợp của Integer.

Vì mọi `Integer` đều dùng được ở vị trí của kiểu cha, phương thức có thể thêm `Integer` mà không cần biết danh sách thật sự được khai báo là `List<Integer>`, `List<Number>` hay `List<Object>`.

`super` đặt **giới hạn dưới** cho kiểu chưa biết. Nó không có nghĩa là “có thể tùy ý thêm mọi đối tượng thuộc các kiểu cha”.

Các nguyên tắc trong bài vẫn áp dụng trong Java hiện đại; chương trình thực hành dùng Java 17 trở lên.

## 2. Vì sao List<Number> không tự là List<Integer>?

Java không coi `List<Integer>` là kiểu con của `List<Number>`, và cũng không coi `List<Number>` là kiểu con của `List<Integer>`.

Nếu một biến `List<Number>` có thể bị nhìn như `List<Integer>`, đoạn mã đọc qua cách nhìn `List<Integer>` sẽ đòi hỏi mọi phần tử là số nguyên. Nhưng danh sách gốc vẫn có thể chứa `Double`, nên quan hệ đó không an toàn.

`List<? super Integer>` cung cấp một hợp đồng khác:

- Không hứa rằng mọi phần tử đọc ra đều là `Integer`.
- Có đủ thông tin để đưa một `Integer` vào qua các phương thức nhận phần tử.
- Giữ nguyên đối tượng danh sách, không chuyển đổi hay sao chép từng phần tử.

Ví dụ:

```java
// Minh họa trong một phương thức; cần import ArrayList và List.
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;
destination.add(7);
```

`destination` là một cách nhìn có giới hạn đối với cùng danh sách `numbers`, không phải một danh sách mới.

## 3. Các kiểu đối số nào phù hợp?

Những ví dụ thường gặp:

| Kiểu danh sách truyền vào | Phù hợp với List<? super Integer>? | Lý do |
| --- | --- | --- |
| `List<Integer>` | Có | Kiểu phần tử chính là `Integer` |
| `List<Number>` | Có | `Number` là kiểu cha của `Integer` |
| `List<Object>` | Có | `Object` là kiểu cha của `Integer` |
| `List<Double>` | Không | `Double` không phải kiểu cha của `Integer` |
| `List<String>` | Không | `String` không phải kiểu cha của `Integer` |

Đây không phải danh sách đầy đủ mọi kiểu phù hợp. Quan hệ kiểu cha còn có thể đi qua interface mà `Integer` thực hiện; điều cần kiểm tra là một `Integer` có thể dùng an toàn ở vị trí kiểu phần tử đó hay không.

Với một tham số tổng quát `T`, `? super T` giữ cùng ý nghĩa: kiểu chưa biết có thể là `T` hoặc một kiểu cha phù hợp của `T`.

Không suy luận từ tên `Number` rằng mọi danh sách của các lớp con `Number` đều dùng được. `List<Double>` không thể nhận tùy ý một `Integer`.

## 4. Có thể thêm gì qua List<? super Integer>?

```java
// Minh họa trong một phương thức; cần import ArrayList và List.
List<? super Integer> destination = new ArrayList<Number>();
destination.add(1);
destination.add(Integer.valueOf(2));
```

Hai lời gọi hợp lệ về kiểu. Literal `1` được boxing thành `Integer`.

Các lời gọi sau không hợp lệ:

```java
// Minh họa lỗi, với destination như trên.
destination.add(2.5);
destination.add(new Object());
```

Dù biến được khởi tạo từ `ArrayList<Number>` trong ví dụ, kiểu của biểu thức `destination` vẫn là `List<? super Integer>`. Qua hợp đồng đó, trình biên dịch phải tính tới khả năng danh sách là `List<Integer>`. Một `Double` hoặc một `Object` bất kỳ không an toàn trong trường hợp ấy.

Với một kiểu có lớp con thực sự, có thể thêm cả đối tượng lớp con của `T`. Ví dụ, qua `List<? super Dog>` có thể đưa một `Dog` hoặc một `Poodle extends Dog` vào; không thể đưa một `Animal` bất kỳ vào chỉ vì `Animal` là lớp cha của `Dog`.

`Integer` là lớp `final`, nên ví dụ số nguyên không có lớp con riêng để minh họa điều này.

## 5. Khi đọc ra, chỉ chắc chắn có Object

```java
// Minh họa trong một phương thức.
List<Object> mixed = new ArrayList<>();
mixed.add("existing");

List<? super Integer> destination = mixed;
destination.add(10);

Object first = destination.get(0);
```

Danh sách gốc là `List<Object>` và đã chứa một chuỗi. Việc thêm `Integer` qua wildcard không làm phần tử cũ biến thành số nguyên.

Vì thế, các phép gán sau không hợp lệ qua kiểu wildcard này:

```java
// Minh họa lỗi.
Integer first = destination.get(0);
Number another = destination.get(0);
```

Kiểu an toàn chung để đọc là `Object`. Không nên ép kiểu sang `Integer` chỉ vì mới gọi `add(10)`: danh sách có thể chứa các phần tử khác hoặc bị sử dụng qua một tham chiếu khác.

Câu nói “`super` chỉ ghi, không đọc” chỉ là mẹo nhớ và không chính xác nếu hiểu theo nghĩa tuyệt đối. Ta vẫn có thể:

- Gọi `get` và nhận kết quả qua `Object`.
- Xem `size`, kiểm tra rỗng, duyệt qua các phần tử dưới cách nhìn `Object`.
- Dùng các thao tác khác mà hợp đồng kiểu và bản triển khai cho phép.

Điều bị giới hạn là thông tin kiểu đọc ra, không phải toàn bộ khả năng đọc danh sách.

## 6. Kết hợp tham số kiểu có tên với wildcard

Wildcard không tự giới thiệu một tên `T`. Muốn nối kiểu của giá trị đầu vào với nơi nhận dữ liệu, phương thức cần khai báo `T`:

```java
// Phương thức minh họa; cần import java.util.List.
static <T> void addOne(List<? super T> destination, T value) {
    destination.add(value);
}
```

Các lời gọi hợp lệ:

```java
// Minh họa trong một phương thức.
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

addOne(numbers, Integer.valueOf(7));
addOne(objects, "Java");
```

`T` kết nối kiểu giá trị với giới hạn dưới của danh sách. Khi suy luận kiểu, trình biên dịch kiểm tra các đối số cùng nhau; nó không bỏ qua kiểu thực tế của danh sách để cho phép đưa một đối tượng không tương thích vào.

Không có cú pháp khai báo tham số kiểu dạng `<T super Number>`. Với tham số kiểu có tên, Java dùng giới hạn trên `extends`; `super` trong chủ đề này nằm ở wildcard như `? super T`.

Cũng không viết `? super int`; giới hạn phải dùng kiểu tham chiếu, chẳng hạn `Integer`.

## 7. Nguồn cung cấp extends, đích tiếp nhận super

Một phương thức thêm nhiều phần tử có thể cần đọc nguồn và ghi đích:

```java
// Phương thức minh họa; cần import java.util.List.
static <T> void appendAll(
        List<? super T> destination,
        List<? extends T> source) {
    for (T value : source) {
        destination.add(value);
    }
}
```

Trong hợp đồng này:

- `source` cung cấp các giá trị có thể đọc qua kiểu `T`.
- `destination` tiếp nhận các giá trị `T`.
- Vòng lặp giữ được kiểu an toàn mà không ép kiểu.

Đây là ý nghĩa của mẹo **PECS — Producer Extends, Consumer Super**: một phía cung cấp giá trị `T` thường dùng `extends`; một phía tiếp nhận giá trị `T` thường dùng `super`.

```java
// Minh họa trong một phương thức.
List<Integer> source = List.of(1, 2, 3);
List<Number> destination = new ArrayList<>();

appendAll(destination, source);
destination.add(2.5);
```

Thêm `2.5` ở câu lệnh cuối hợp lệ vì biểu thức `destination` tại nơi gọi có kiểu `List<Number>`. Điều đó khác với việc gọi `add(2.5)` qua một biến chỉ có kiểu `List<? super Integer>`.

Phương thức minh họa giả định nguồn và đích khác nhau và đích hỗ trợ thêm phần tử. Nó không xử lý trường hợp nguồn/đích là cùng danh sách hoặc cùng chia sẻ một vùng dữ liệu; các yêu cầu đó cần hợp đồng riêng trong một hàm thư viện hoàn chỉnh.

### Phân biệt với Collections.copy

Thư viện chuẩn có `Collections.copy` với nguồn dùng `extends` và đích dùng `super`. Tuy nhiên, phương thức đó **thay thế các phần tử ở những vị trí đã có**, không tự nối thêm như `appendAll`.

Danh sách đích phải có `size()` đủ lớn và hỗ trợ thay thế phần tử. `new ArrayList<>(3)` chỉ cấp sức chứa ban đầu, không tạo ba phần tử; nó vẫn có kích thước `0`. Đúng chữ ký wildcard chưa đủ để bảo đảm các điều kiện runtime ấy.

## 8. Super không tự làm collection thay đổi được

Xét:

```java
// Minh họa lỗi khi chạy, không phải lỗi kiểu.
List<? super Integer> fixed = List.<Number>of(1, 2);
fixed.add(3);
```

Lời gọi `add(3)` hợp lệ về kiểu, nhưng danh sách từ `List.of` không cho phép thêm phần tử và sẽ ném `UnsupportedOperationException`.

Tương tự, kiểu wildcard không bảo đảm rằng `null` được chấp nhận. `null` tương thích về kiểu ở vị trí thêm phần tử tham chiếu, nhưng bản triển khai collection có thể từ chối nó.

Cần phân biệt:

- **Kiểm tra kiểu:** giá trị có phù hợp với hợp đồng generic không?
- **Khả năng sửa đổi:** danh sách có cho phép `add`, `set` hoặc `remove` không?
- **Ràng buộc dữ liệu:** có cho phép `null`, phần tử trùng hay các điều kiện khác không?

`? super T` trả lời câu hỏi về quan hệ kiểu, không tự trả lời hai câu hỏi còn lại.

## 9. Quan hệ giữa các wildcard giới hạn dưới

So sánh:

```java
// Minh họa trong một phương thức.
List<? super Number> allNumbers = new ArrayList<Number>();
List<? super Integer> integersOnlyView = allNumbers;
```

Phép gán hợp lệ. Một danh sách được bảo đảm nhận `Number` cũng có thể nhận `Integer`.

Chiều ngược lại không hợp lệ một cách tổng quát: một `List<? super Integer>` có thể thực sự là `List<Integer>`, nên không bảo đảm nhận được mọi `Number`.

Tên `integersOnlyView` chỉ mô tả những giá trị không-null mà cách nhìn này bảo đảm có thể đưa vào trong ví dụ. Nó không hứa danh sách chỉ chứa `Integer`, cũng không thay đổi đối tượng danh sách bên dưới.

| Cách nhìn | Có thể đưa T vào? | Kiểu an toàn khi đọc |
| --- | --- | --- |
| `List<T>` | Có, nếu thao tác được hỗ trợ | `T` |
| `List<? extends T>` | Không bảo đảm với một giá trị `T` bất kỳ | `T` |
| `List<? super T>` | Có, nếu thao tác được hỗ trợ | `Object` |
| `List<?>` | Không bảo đảm với một giá trị không-null bất kỳ | `Object` |

Bảng nói về cách dùng tổng quát qua kiểu biến đã ghi, không phủ nhận những thao tác như xóa phần tử hoặc việc `null` có thể hợp lệ về kiểu.

## 10. Chương trình đầy đủ

Lưu vào `LowerBoundWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Consumer;

public class LowerBoundWildcardDemo {
    static <T> void appendAll(
            List<? super T> destination,
            List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    static <T> void feed(T value, Consumer<? super T> consumer) {
        consumer.accept(value);
    }

    public static void main(String[] args) {
        List<Object> mixed = new ArrayList<>();
        mixed.add("existing");

        List<? super Integer> destination = mixed;
        destination.add(10);
        destination.add(20);
        System.out.println(mixed);

        Object first = destination.get(0);
        System.out.println(first.getClass().getSimpleName());

        List<Integer> source = List.of(1, 2, 3);
        List<Number> numbers = new ArrayList<>();
        appendAll(numbers, source);
        numbers.add(2.5);
        System.out.println(numbers);

        List<Object> objects = new ArrayList<>();
        appendAll(objects, List.of("a", "b"));
        System.out.println(objects);

        List<? super Number> allNumbers = new ArrayList<Number>();
        List<? super Integer> integersView = allNumbers;
        integersView.add(7);
        allNumbers.add(1.5);
        System.out.println(allNumbers);

        List<Number> replacements =
                new ArrayList<>(List.<Number>of(0, 0, 0));
        Collections.copy(replacements, source);
        System.out.println(replacements);

        Consumer<Object> printer =
                value -> System.out.println("accepted=" + value);
        feed(42, printer);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LowerBoundWildcardDemo.java
java LowerBoundWildcardDemo
```

Stdout chính xác:

```text
[existing, 10, 20]
String
[1, 2, 3, 2.5]
[a, b]
[7, 1.5]
[1, 2, 3]
accepted=42
```

Giải thích:

1. Cách nhìn `List<? super Integer>` cho phép đưa các số nguyên vào danh sách `Object` có sẵn.
2. Đọc phần tử đầu trả về một chuỗi dưới cách nhìn `Object`, chứng minh không thể coi mọi phần tử là `Integer`.
3. `appendAll` chuyển các giá trị từ nguồn số nguyên sang đích số tổng quát mà không ép kiểu.
4. Cùng phương thức cũng có thể đưa chuỗi vào danh sách `Object`.
5. Một nơi nhận `Number` được nhìn qua `? super Integer` để thêm số nguyên; cùng danh sách vẫn nhận số thực qua cách nhìn `? super Number`.
6. `Collections.copy` thay thế ba vị trí đã có bằng ba phần tử nguồn.
7. `Consumer<Object>` nhận được một `Integer` qua hợp đồng `Consumer<? super T>`. Wildcard giới hạn dưới không chỉ hữu ích với danh sách; nó còn biểu diễn các thao tác tiếp nhận giá trị.

Các nguồn và đích trong ví dụ `appendAll` là những danh sách khác nhau. Đích đều là `ArrayList` thay đổi được, nên đáp ứng yêu cầu thêm phần tử.

## 11. Những lỗi thường gặp

### Đọc super thành “thêm được kiểu cha”

`List<? super Integer>` bảo đảm thêm `Integer`, không bảo đảm thêm một `Number` bất kỳ. Danh sách thật sự có thể là `List<Integer>`.

### Ép kiểu kết quả get sang T

Giới hạn dưới không bảo đảm các phần tử cũ là `T`. Nếu thuật toán cần vừa nhận vừa trả về chính xác các phần tử cùng kiểu `T`, hãy xem liệu `List<T>` có thể hiện hợp đồng tốt hơn hay không.

### Dùng List<T> ở mọi đích mà không cần thiết

Một đích chỉ nhận dữ liệu có thể linh hoạt hơn với `List<? super T>`; giới hạn quá chặt có thể từ chối những danh sách kiểu cha vốn sử dụng an toàn.

### Cho rằng super làm mất mọi thông tin của biến gốc

Wildcard giới hạn cách sử dụng qua một biểu thức nhất định. Biến gốc `List<Number>` vẫn giữ hợp đồng `Number`; đối tượng không bị đổi kiểu hoặc sao chép khi gán sang biến wildcard.

### Đồng nhất tính hợp lệ của generic với thành công runtime

Một lời gọi có thể biên dịch nhưng thất bại vì collection không cho sửa, thiếu kích thước khi sao chép theo vị trí hoặc từ chối dữ liệu. Kiểm tra cả hợp đồng phương thức và loại collection.

## 12. Tự kiểm tra

1. Vì sao cả `List<Integer>`, `List<Number>` và `List<Object>` đều có thể làm đối số cho `List<? super Integer>`?
2. Vì sao `destination.add(2.5)` bị từ chối dù `destination` từng được gán từ một `ArrayList<Number>`?
3. Tạo một `List<Object>` chứa chuỗi, nhìn nó qua `List<? super Integer>` rồi thêm số nguyên. Vì sao đọc ra vẫn chỉ bảo đảm `Object`?
4. Viết `addOne(List<? super T>, T)` và thử gọi với đích `List<Double>` cùng giá trị `Integer`. Giải thích vì sao lời gọi không phù hợp.
5. Phân biệt `appendAll` trong bài và `Collections.copy`: đích rỗng dùng được với phương thức nào?
6. Giải thích chiều gán từ `List<? super Number>` sang `List<? super Integer>`, và vì sao chiều ngược lại không bảo đảm.
7. Cho một lớp `Dog extends Animal`, thiết kế phương thức đưa `Dog` vào cả danh sách `Dog` và danh sách `Animal` mà không dùng ép kiểu.

## Tài liệu đối chiếu

- [Java Language Specification — Type Arguments and Wildcards (§4.5.1)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1): wildcard và giới hạn.
- [Java API — Collections.copy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)): nguồn `extends`, đích `super` và yêu cầu về kích thước danh sách.
- [Java API — List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): hợp đồng thao tác và những giới hạn do bản triển khai đặt ra.
- [Java API — Consumer<T>](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Consumer.html): thao tác nhận giá trị, dùng trong ví dụ `feed`.
