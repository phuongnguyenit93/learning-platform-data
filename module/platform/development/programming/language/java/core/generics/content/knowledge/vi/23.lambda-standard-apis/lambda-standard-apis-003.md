# Generic với `Comparator<T>` và phép nối tiêu chí trong Java

## 1. Mục tiêu: sắp xếp đối tượng theo nhiều tiêu chí có kiểm tra kiểu

Trong ứng dụng Java, ta thường cần sắp xếp danh sách các đối tượng theo nhiều thuộc tính: nhân viên theo phòng ban rồi tên; sinh viên theo điểm giảm dần rồi họ tên; sản phẩm theo giá, ngày cập nhật rồi mã định danh. Việc chỉ viết một phép so sánh đơn giản thường chưa đủ.

Java cung cấp interface generic **`Comparator<T>`** và các factory/chaining methods để xây dựng thứ tự một cách rõ ràng:

```java
Comparator<Student> order =
        Comparator.<Student>comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name)
                .thenComparingInt(Student::age);
```

Đoạn trên là một mảnh code minh họa; giả định có record hoặc class `Student` với các accessor `score()`, `name()`, `age()`, và import `java.util.Comparator`.

Nó biểu diễn đúng một hợp đồng sắp xếp:

1. **Điểm giảm dần**: sinh viên có điểm cao đứng trước.
2. Nếu **điểm bằng nhau**, so sánh **tên tăng dần**.
3. Nếu **cả điểm và tên bằng nhau**, so sánh **tuổi tăng dần**.

Dấu `.reversed()` đặt **ngay sau comparator điểm** rất quan trọng: nó đảo chiều điểm, không tự đảo hai tiêu chí nối tiếp.

**Nội dung trọng tâm của bài:** Hiểu `Comparator<T>` là một *hợp đồng so sánh có kiểu*, biết sử dụng lambda/method reference với `Comparator.comparing`, `comparingInt` và `thenComparing`, đặt `reversed()` chính xác, xử lý `null`, và giữ tính đúng đắn của thứ tự trong `List.sort`, `Stream.sorted` và các sorted collections.

## 2. `Comparator<T>` là gì?

`java.util.Comparator<T>` là một **functional interface**, trong đó thao tác chính là:

```java
int compare(T left, T right);
```

Ý nghĩa dấu của giá trị trả về:

| Kết quả của `compare(a, b)` | Ý nghĩa |
|---|---|
| Nhỏ hơn 0 | `a` đứng trước `b` theo comparator này |
| Bằng 0 | `a` và `b` bằng nhau **về thứ tự so sánh** |
| Lớn hơn 0 | `a` đứng sau `b` |

Không có yêu cầu phải trả đúng `-1`, `0` hoặc `1`; Java chỉ dựa vào **dấu** của kết quả.

Ví dụ với số nguyên:

```java
Comparator<Integer> ascending = (a, b) ->
        Integer.compare(a, b);
```

Đây là một lambda hợp lệ khi có import `java.util.Comparator`. Nếu `a = 2`, `b = 8`, `compare(a,b)` có giá trị âm; nếu đảo vị trí thì dương.

Generic type argument `Integer` trong `Comparator<Integer>` khiến compiler xác nhận lambda làm việc với hai `Integer`. Việc viết `(a, b)` không khai báo kiểu tường minh vẫn an toàn vì **target type** cung cấp thông tin cho lambda.

### Hợp đồng so sánh phải nhất quán

Comparator không chỉ là một phép tính trả số tùy ý. Nó cần thỏa các thuộc tính quan trọng:

- **Phản xứng về dấu**: dấu của `compare(a,b)` phải ngược dấu của `compare(b,a)` với những giá trị mà phép so sánh xác định.
- **Bắc cầu**: nếu `a > b` và `b > c` theo comparator, phải có `a > c`.
- **Nhất quán khi bằng 0**: nếu `compare(a,b) == 0`, việc so `a` hay `b` với một `z` khác phải cho cùng dấu.
- Comparator nên cho kết quả ổn định khi trạng thái liên quan tới thứ tự không thay đổi.

Vi phạm hợp đồng có thể làm thuật toán sort hoạt động sai, kết quả bất ngờ hoặc trong một số tình huống gây ngoại lệ về vi phạm general contract.

## 3. `Comparator<T>` và `Comparable<T>` khác nhau thế nào?

`Comparable<T>` mô tả một **thứ tự tự nhiên** do chính kiểu dữ liệu định nghĩa:

```java
class Version implements Comparable<Version> {
    private final int number;

    Version(int number) {
        this.number = number;
    }

    @Override
    public int compareTo(Version other) {
        return Integer.compare(number, other.number);
    }
}
```

Đoạn class trên hợp lệ nhưng không có `main`.

`Comparator<T>` là **quy tắc so sánh ở bên ngoài kiểu**, có thể thay đổi tùy ngữ cảnh:

```java
Comparator<Version> descending = (a, b) ->
        b.compareTo(a);
```

Những khác biệt chính:

| `Comparable<T>` | `Comparator<T>` |
|---|---|
| Kiểu thường tự triển khai `compareTo` | Có thể đặt ngoài class |
| Một thứ tự tự nhiên do class lựa chọn | Có thể có nhiều thứ tự khác nhau |
| `Collections.sort(list)`/`sorted()` không comparator dựa vào nó | `sort(comparator)`/`sorted(comparator)` dùng comparator được truyền |
| Hữu ích khi bản thân kiểu có natural order rõ ràng | Hữu ích khi yêu cầu nghiệp vụ thay đổi hoặc có nhiều tiêu chí |

Khi một bản ghi có nhiều cách sắp xếp hợp lý (theo điểm, tên, tuổi…), một hoặc nhiều `Comparator<Student>` thường rõ ràng hơn việc cố nhồi tất cả vào `compareTo`.

## 4. Lambda và method reference đi vào `Comparator<T>`

Vì `Comparator<T>` là functional interface, ta có thể tạo comparator từ lambda:

```java
Comparator<String> byLength = (left, right) ->
        Integer.compare(left.length(), right.length());
```

Hoặc dùng một static factory method với **method reference**:

```java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);
```

`String::length` đại diện cho một hàm nhận `String` và trả `int`; nó phù hợp với `ToIntFunction<? super String>` mà `comparingInt` yêu cầu.

Về ý nghĩa, hai comparator đều so chuỗi theo độ dài tăng dần. Chúng **không tự thêm tiêu chí theo thứ tự từ điển**; hai chuỗi có cùng độ dài sẽ cho kết quả `0`.

Để có thứ tự phụ:

```java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());
```

Đây là ví dụ dùng lambda/method reference **và nối tiêu chí**; compiler suy luận các generic types liên quan từ target type `Comparator<String>`.

Khi compiler khó suy luận từ một method chain dài, ta có thể nêu rõ type ở biến, hoặc dùng **explicit type witness** như `Comparator.<Student>comparingInt(Student::score)`.

## 5. Ví dụ đầy đủ: điểm giảm dần, tên tăng dần, tuổi tăng dần

Tạo tệp **`StudentComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class StudentComparatorDemo {

    record Student(String name, int score, int age) {
    }

    public static void main(String[] args) {
        List<Student> students = new ArrayList<>(List.of(
                new Student("Binh", 90, 22),
                new Student("An", 90, 21),
                new Student("Chi", 80, 20),
                new Student("An", 90, 19)
        ));

        Comparator<Student> byScoreNameAge =
                Comparator.<Student>comparingInt(Student::score)
                        .reversed()
                        .thenComparing(Student::name)
                        .thenComparingInt(Student::age);

        students.sort(byScoreNameAge);

        for (Student s : students) {
            System.out.println(
                    s.name() + "|" + s.score() + "|" + s.age());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac StudentComparatorDemo.java
java StudentComparatorDemo
```

Stdout:

```text
An|90|19
An|90|21
Binh|90|22
Chi|80|20
```

Phân tích:

1. `Comparator.<Student>comparingInt(Student::score)` tạo comparator kiểu `Comparator<Student>` và trích điểm bằng hàm `Student -> int`.
2. `.reversed()` đảo thứ tự của **comparator điểm đã tạo**, đưa `90` trước `80`.
3. `.thenComparing(Student::name)` chỉ so tên khi điểm được coi là bằng nhau. Ở đây `"An"` đứng trước `"Binh"` theo `String` natural order.
4. `.thenComparingInt(Student::age)` chỉ chạy khi điểm **và** tên đều bằng nhau. `"An"` tuổi `19` đứng trước `"An"` tuổi `21`.
5. `students.sort(...)` thay đổi thứ tự phần tử của list có thể chỉnh sửa.

Nếu muốn **tên giảm dần** thay vì tăng dần, cần đặt comparator riêng cho tên ở đoạn `thenComparing`, không nhất thiết đảo toàn bộ comparator.

## 6. Cơ chế short-circuit của `thenComparing`

`thenComparing(other)` tạo một comparator hợp thành. Ý tưởng logic là:

```java
int first = primary.compare(a, b);
if (first != 0) {
    return first;
}
return secondary.compare(a, b);
```

Đây là **mô hình minh họa**, không phải nội dung bytecode hoặc triển khai duy nhất của thư viện JDK.

Điều quan trọng:

- Khi tiêu chí chính đã phân biệt được hai object, tiêu chí phụ **không cần** được gọi.
- Chỉ khi comparator chính trả `0`, comparator phụ mới quyết định.
- Có thể nối nhiều cấp. Mỗi cấp sau chỉ có ý nghĩa khi mọi cấp trước bằng nhau.

Với phép nối ba cấp, có thể hình dung:

```text
So điểm → khác? dùng kết quả đó
       → bằng → so tên → khác? dùng kết quả đó
                     → bằng → so tuổi
```

Điều này thuận lợi cả về cấu trúc logic lẫn việc tránh tính key phụ không cần thiết. Tuy nhiên không nên đưa side effects vào comparator/key extractor: thuật toán sort có thể gọi comparator nhiều lần và theo thứ tự không đơn giản.

## 7. `comparing`, `comparingInt`, `comparingLong`, `comparingDouble`

Java cung cấp nhiều cách tạo comparator từ một **khóa sắp xếp** (*sort key*).

### `Comparator.comparing(Function)`

Khi khóa là một kiểu có thứ tự tự nhiên (*Comparable*), chẳng hạn `String`, `LocalDate`, `BigDecimal`:

```java
Comparator<Student> byName =
        Comparator.comparing(Student::name);
```

Compiler biết `Student::name` trả `String`, và `String` có natural order. Đây là comparator theo tên tăng dần.

### `Comparator.comparingInt(ToIntFunction)`

Khi khóa là `int`:

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
```

`comparingInt` dùng `ToIntFunction<? super T>` và so sánh `int` theo ngữ nghĩa `Integer.compare`, không yêu cầu tạo khóa dạng wrapper trong hợp đồng API.

### Các dạng primitive khác

```java
Comparator<Order> byTimestamp =
        Comparator.comparingLong(Order::timestamp);

Comparator<Order> byAmount =
        Comparator.comparingDouble(Order::amount);
```

Đây là những đoạn **minh họa**, giả sử class `Order` có các accessor `timestamp(): long` và `amount(): double`.

Các bản primitive-specific đặc biệt hữu ích khi khóa vốn là primitive, làm rõ ý định và tránh chuyển khóa sang wrapper chỉ để so sánh.

### Khi nào cần overload `comparing(extractor, keyComparator)`?

Nếu khóa không có natural order, hoặc cần một quy tắc khác, truyền comparator của **kiểu khóa**:

```java
Comparator<Student> byNameIgnoreCase =
        Comparator.comparing(
                Student::name,
                String.CASE_INSENSITIVE_ORDER);
```

Trong trường hợp tên có thể là `null`, comparator cho khóa cũng cần xử lý `null`; phần sau có ví dụ.

## 8. Generic signatures và ý nghĩa của `T`, `U`

Phần lớn sức mạnh của API `Comparator` nằm ở generic type parameters. Các chữ ký tiêu biểu (rút gọn từ Java API) là:

```java
public interface Comparator<T> {

    int compare(T first, T second);

    Comparator<T> thenComparing(
            Comparator<? super T> other);

    <U extends Comparable<? super U>>
    Comparator<T> thenComparing(
            Function<? super T, ? extends U> keyExtractor);

    <U> Comparator<T> thenComparing(
            Function<? super T, ? extends U> keyExtractor,
            Comparator<? super U> keyComparator);
}
```

Đây là **chữ ký rút gọn để học**, không phải một interface có thể copy nguyên và thay thế `java.util.Comparator`.

Phân biệt hai type parameters:

- `T`: kiểu đối tượng **được sắp xếp**, ví dụ `Student`.
- `U`: kiểu **khóa trích xuất**, ví dụ `String`, `LocalDate`, `BigDecimal`.

Vì vậy:

```java
Comparator<Student> byName =
        Comparator.comparing(Student::name);
```

có đối tượng so sánh kiểu `Student`, nhưng khóa `name()` là `String`. Hai kiểu không cần trùng nhau.

Trong bản `comparing` không truyền comparator cho key, khóa `U` cần thực hiện `Comparable<? super U>` để có thứ tự tự nhiên. Khi `U` không có natural order, hãy dùng overload có `Comparator<? super U>`.

### `? super T` bảo vệ tính linh hoạt

Một `Comparator<Object>` có thể so hai giá trị theo quy tắc dùng chung, vì nó nhận được mọi `Student` vốn là `Object`. Do đó các API sắp xếp dùng `Comparator<? super T>` để cho phép so sánh bằng comparator của chính `T` hoặc một **supertype** phù hợp.

Tương tự, `Function<? super T, ? extends U>` chấp nhận một key extractor đọc được `T` hoặc một kiểu cha, và cho ra một giá trị phù hợp với `U`.

Đây là ứng dụng quy tắc thường được gọi là **PECS**: consumer nhận `? super`, producer trả `? extends`. Không phải wildcard tùy ý; chúng mô tả hướng dữ liệu đi qua functional interfaces.

## 9. Vì sao cần explicit type witness ở một số chuỗi gọi?

Với biểu thức:

```java
Comparator.comparingInt(Student::score)
        .reversed()
        .thenComparing(Student::name)
```

compiler đôi khi không có đủ thông tin target type sớm để suy luận đúng `Student` trong một chuỗi phương thức, đặc biệt khi một method trung gian như `.reversed()` buộc kiểm tra kiểu kết quả trước khi toàn chuỗi hoàn tất.

Một cách chắc chắn là đặt rõ generic argument cho **factory method**:

```java
Comparator<Student> order =
        Comparator.<Student>comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name);
```

`<Student>` ngay sau `Comparator.` là **explicit method type argument** cho `comparingInt`, không phải cast và không tạo thêm class runtime.

Một cách khác là tách comparator ban đầu:

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);

Comparator<Student> order =
        byScore.reversed().thenComparing(Student::name);
```

Khi đọc code, **kiểu được đặt ở biến trung gian** cũng giúp compiler và người bảo trì thấy rõ khóa áp dụng cho `Student`, chứ không phải một `Object` chưa biết.

### Với `Comparator.comparing`, có hai type parameters

Chữ ký `comparing` tổng quát có hai kiểu: đối tượng `T` và khóa `U`. Nếu cần type witness đầy đủ:

```java
Comparator<Student> byName =
        Comparator.<Student, String>comparing(Student::name);
```

Trong code đơn giản, target typing thông thường đã đủ; không cần lạm dụng việc viết explicit type arguments ở mọi nơi.

## 10. `reversed()` đảo đúng phạm vi nào?

`reversed()` trả một comparator có thứ tự ngược với comparator nhận lời gọi.

Điểm bẫy: khi gọi `.reversed()` **sau khi** đã nối nhiều tiêu chí, nó đảo **toàn bộ chuỗi**, không chỉ tiêu chí gần nhất.

Xét:

```java
Comparator<Student> bothAsc =
        Comparator.comparingInt(Student::score)
                .thenComparing(Student::name);

Comparator<Student> bothDesc = bothAsc.reversed();
```

`bothDesc` ưu tiên **điểm giảm dần**, và nếu điểm bằng nhau thì **tên giảm dần**.

Ngược lại, nếu muốn điểm giảm dần **nhưng tên tăng dần**:

```java
Comparator<Student> scoreDescNameAsc =
        Comparator.<Student>comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name);
```

Đặt `reversed()` **trước** `thenComparing(...)`.

### Ví dụ so ba kết quả

Tạo tệp **`ReversedScopeDemo.java`**:

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class ReversedScopeDemo {

    record Item(String label, int quantity) {
    }

    static String render(List<Item> items, Comparator<Item> order) {
        return items.stream()
                .sorted(order)
                .map(i -> i.label() + ":" + i.quantity())
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("B", 2),
                new Item("A", 2),
                new Item("C", 1));

        Comparator<Item> ascending =
                Comparator.<Item>comparingInt(Item::quantity)
                        .thenComparing(Item::label);

        Comparator<Item> reversedAll = ascending.reversed();

        Comparator<Item> quantityDescLabelAsc =
                Comparator.<Item>comparingInt(Item::quantity)
                        .reversed()
                        .thenComparing(Item::label);

        System.out.println(render(items, ascending));
        System.out.println(render(items, reversedAll));
        System.out.println(render(items, quantityDescLabelAsc));
    }
}
```

Chạy:

```bash
javac ReversedScopeDemo.java
java ReversedScopeDemo
```

Stdout:

```text
C:1, A:2, B:2
B:2, A:2, C:1
A:2, B:2, C:1
```

Dòng cuối là yêu cầu thường gặp: **số lượng giảm dần**, **nhãn tăng dần**. Dòng giữa chứng minh việc `.reversed()` đặt ở cuối đảo cả tiêu chí phụ.

## 11. Đảo riêng một tiêu chí phụ

Nếu muốn **điểm tăng dần, tên giảm dần**, ta không đảo comparator sau khi đã nối toàn bộ. Thay vào đó, xây một comparator tên đảo chiều rồi truyền cho `thenComparing`:

```java
Comparator<Student> scoreAscNameDesc =
        Comparator.<Student>comparingInt(Student::score)
                .thenComparing(
                        Comparator.comparing(
                                Student::name,
                                Comparator.reverseOrder()));
```

Trong ví dụ, `Comparator.reverseOrder()` cung cấp comparator cho khóa `String` theo natural order đảo chiều. Đây là đoạn minh họa với `Student` như đã định nghĩa.

Một cách thể hiện trực tiếp hơn:

```java
Comparator<Student> byNameDescending =
        Comparator.comparing(
                Student::name,
                Comparator.reverseOrder());

Comparator<Student> scoreAscNameDesc =
        Comparator.comparingInt(Student::score)
                .thenComparing(byNameDescending);
```

Khi có nhiều chiều tăng/giảm đan xen, **tạo comparator riêng cho từng khóa** hoặc tách thành biến có tên thường dễ đọc hơn một chain dài với nhiều lần `.reversed()`.

## 12. `thenComparing` và các bản chuyên primitive

API có nhiều overload để nối tiêu chí:

```java
primary.thenComparing(secondaryComparator);
primary.thenComparing(keyExtractor);
primary.thenComparing(keyExtractor, keyComparator);
primary.thenComparingInt(intKeyExtractor);
primary.thenComparingLong(longKeyExtractor);
primary.thenComparingDouble(doubleKeyExtractor);
```

- `thenComparing(Comparator<? super T>)`: nhận comparator hoàn chỉnh của cùng kiểu đối tượng `T`.
- `thenComparing(Function...)`: trích một khóa có natural order rồi so khóa đó.
- `thenComparing(Function..., Comparator...)`: trích khóa và dùng comparator riêng cho khóa.
- `thenComparingInt/Long/Double`: trích primitive keys và so theo cách tương ứng.

Ví dụ:

```java
Comparator<Student> byNameThenScore =
        Comparator.comparing(Student::name)
                .thenComparingInt(Student::score);
```

Nếu `Student::score` trả `int`, `thenComparingInt` biểu đạt đúng kiểu khóa. Nếu dữ liệu có `double` và giá trị `NaN`, comparator dùng `Double.compare` với quy tắc nhất quán của Java; không nên tự so bằng phép trừ rồi ép sang `int`.

## 13. Null: cần phân biệt null **đối tượng** và null **khóa**

Một trong các lỗi phổ biến là:

```java
Comparator<Student> byName =
        Comparator.comparing(Student::name);
```

Nếu `name()` có thể trả `null`, natural order của `String` không xử lý giá trị `null`; lời gọi comparator có thể ném `NullPointerException`.

Có hai tình huống khác nhau:

1. **Student object không null, nhưng `name` null**: đặt `Comparator.nullsFirst` hoặc `nullsLast` lên **comparator của khóa**.
2. **Chính Student object có thể null trong list**: bọc **toàn bộ comparator của Student** bằng `Comparator.nullsFirst` hoặc `nullsLast`.

### Null ở khóa

```java
Comparator<Student> byName =
        Comparator.comparing(
                Student::name,
                Comparator.nullsLast(
                        Comparator.naturalOrder()));
```

Biểu thức này cho `null` **ở giá trị `name`** đứng sau những tên không null. Nó không tự bảo vệ trường hợp bản thân `Student` là `null`, vì key extractor `Student::name` vẫn phải được gọi trên object.

### Null ở object

```java
Comparator<Student> nullStudentsLast =
        Comparator.nullsLast(
                Comparator.comparingInt(Student::score));
```

Lúc này, `null` ở cấp **Student** được xếp sau object khác. Nếu một Student không null lại có khóa nullable, bên trong comparator vẫn cần xử lý khóa riêng.

**Đừng dùng một `nullsLast` ở cấp khóa rồi tin rằng nó tự bao mọi cấp null.**

## 14. Ví dụ chạy được: null trong tên và so sánh không phân biệt hoa thường

Tạo tệp **`NullableKeyComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class NullableKeyComparatorDemo {

    record Person(String name, int id) {
    }

    public static void main(String[] args) {
        List<Person> people = new ArrayList<>(List.of(
                new Person("b", 3),
                new Person(null, 2),
                new Person("A", 2),
                new Person("a", 1)));

        Comparator<Person> byNameThenId =
                Comparator.comparing(
                        Person::name,
                        Comparator.nullsLast(
                                String.CASE_INSENSITIVE_ORDER))
                        .thenComparingInt(Person::id);

        people.sort(byNameThenId);

        for (Person p : people) {
            System.out.println(
                    String.valueOf(p.name()) + "#" + p.id());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac NullableKeyComparatorDemo.java
java NullableKeyComparatorDemo
```

Stdout:

```text
a#1
A#2
b#3
null#2
```

Giải thích:

- `String.CASE_INSENSITIVE_ORDER` xem `"a"` và `"A"` bằng nhau về khóa tên.
- `thenComparingInt(Person::id)` phân biệt hai bản ghi đó, đưa id `1` trước id `2`.
- `Comparator.nullsLast(...)` áp dụng ở **giá trị `name`** nên người có tên `null` đứng cuối.
- Tất cả **Person object** trong ví dụ đều không null. Nếu list chứa một phần tử `null` thật sự, cần bọc comparator ngoài cùng bằng `Comparator.nullsLast(byNameThenId)`.

`String.CASE_INSENSITIVE_ORDER` không đồng nghĩa một thứ tự theo ngôn ngữ tự nhiên cho mọi locale; việc sắp xếp tiếng Việt theo quy tắc ngôn ngữ là câu hỏi khác, xem phần `Collator`.

## 15. Null ở toàn bộ phần tử list

Tạo tệp **`NullElementComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullElementComparatorDemo {

    record Entry(int id) {
    }

    public static void main(String[] args) {
        List<Entry> entries = new ArrayList<>(
                Arrays.asList(new Entry(3), null, new Entry(1)));

        Comparator<Entry> byId =
                Comparator.comparingInt(Entry::id);

        entries.sort(Comparator.nullsLast(byId));

        for (Entry e : entries) {
            System.out.println(e == null ? "null" : e.id());
        }
    }
}
```

Chạy:

```bash
javac NullElementComparatorDemo.java
java NullElementComparatorDemo
```

Stdout:

```text
1
3
null
```

`Arrays.asList` ở đây được dùng để tạo đầu vào **có chứa `null`**, sau đó sao chép sang `ArrayList`. Không dùng `List.of(new Entry(3), null, ...)` vì `List.of` từ chối `null`.

`Comparator.nullsLast(byId)` kiểm tra cấp object trước khi gọi `byId`, nên object `null` được xếp sau object không null mà không truy cập accessor trên `null`.

## 16. `List.sort`, `Collections.sort` và `Stream.sorted`

Có nhiều API dùng chung `Comparator<T>` nhưng **khác cách trả kết quả và tác động lên input**.

### `List.sort(comparator)`

```java
List<Student> mutable = new ArrayList<>(source);
mutable.sort(order);
```

`List.sort` sắp xếp **trên chính list nhận lời gọi**. Nếu list không hỗ trợ thay đổi phần tử, thao tác có thể ném `UnsupportedOperationException`.

### `Collections.sort(list, comparator)`

```java
Collections.sort(mutable, order);
```

Là tiện ích sắp xếp list với comparator; trong Java hiện đại, nó dùng hợp đồng sắp xếp của list tương ứng. Không cần chọn `Collections.sort` chỉ vì comparator generic.

### `Stream.sorted(comparator)`

```java
List<Student> sorted =
        source.stream().sorted(order).toList();
```

Tạo một pipeline rồi thu kết quả thành list mới. `Stream.toList()` trong Java 17 trả một list **unmodifiable**; đây không phải mảng/list có thể tự do thêm phần tử.

Tính ổn định (*stability*) của sorting cũng cần xét:

- `List.sort` được quy định là **stable**: những phần tử có comparator result `0` giữ thứ tự tương đối.
- `Stream.sorted` được bảo đảm stable đối với **ordered streams**; với **unordered streams**, không có bảo đảm giống vậy.
- Trong mọi trường hợp, tính stable không thay thế việc định nghĩa các tie-breakers thực sự quan trọng cho nghiệp vụ.

## 17. Ví dụ chạy được: sort tại chỗ và sorted stream

Tạo tệp **`SortApisDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SortApisDemo {

    record Product(String code, int price) {
    }

    static String codes(List<Product> products) {
        return products.stream()
                .map(Product::code)
                .toList()
                .toString();
    }

    public static void main(String[] args) {
        List<Product> original = List.of(
                new Product("B", 200),
                new Product("A", 100),
                new Product("C", 200));

        Comparator<Product> byPriceThenCode =
                Comparator.<Product>comparingInt(Product::price)
                        .thenComparing(Product::code);

        List<Product> mutable = new ArrayList<>(original);
        mutable.sort(byPriceThenCode);

        List<Product> fromStream = original.stream()
                .sorted(byPriceThenCode)
                .toList();

        System.out.println(codes(original));
        System.out.println(codes(mutable));
        System.out.println(codes(fromStream));
    }
}
```

Lệnh:

```bash
javac SortApisDemo.java
java SortApisDemo
```

Stdout:

```text
[B, A, C]
[A, B, C]
[A, B, C]
```

`original` giữ nguyên thứ tự trong ví dụ vì stream pipeline chỉ **đọc** nguồn và không gọi `sort` trên chính `original`. `mutable` là một bản sao `ArrayList` có thể sửa và được sắp xếp tại chỗ.

`fromStream` là danh sách kết quả theo comparator nhưng không cho thêm phần tử bằng `add` trong Java 17. Nếu cần tiếp tục sửa, tạo `new ArrayList<>(fromStream)`.

## 18. Lỗi dễ gặp: dùng phép trừ để làm comparator số

Nhiều đoạn code viết:

```java
Comparator<Integer> wrong = (a, b) -> a - b;
```

Dù có vẻ ngắn, nó **không an toàn với integer overflow**. Phép trừ có thể tràn vòng theo số nguyên Java, tạo sai dấu và vi phạm hợp đồng comparator.

Hãy dùng:

```java
Comparator<Integer> safe = Integer::compare;
```

Hoặc khi so khóa của object:

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
```

### Ví dụ minh họa overflow

Tạo tệp **`ComparatorOverflowDemo.java`**:

```java
public class ComparatorOverflowDemo {
    public static void main(String[] args) {
        int small = Integer.MIN_VALUE;
        int large = Integer.MAX_VALUE;

        System.out.println(small - large);
        System.out.println(Integer.compare(small, large));
    }
}
```

Biên dịch/chạy:

```bash
javac ComparatorOverflowDemo.java
java ComparatorOverflowDemo
```

Stdout:

```text
1
-1
```

Giá trị `Integer.MIN_VALUE - Integer.MAX_VALUE` tràn số nguyên và cho `1`, trong khi thứ tự đúng là số nhỏ đứng trước số lớn. `Integer.compare` trả một giá trị âm theo hợp đồng.

**Không dùng `a.score() - b.score()` làm comparator** chỉ vì test dữ liệu nhỏ chưa phát hiện tràn. Các factory `comparingInt/Long/Double` giúp tránh loại lỗi này.

## 19. `Comparator` và `TreeSet`/`TreeMap`: so bằng 0 là “cùng khóa thứ tự”

Đối với `List.sort`, hai phần tử có comparator result `0` vẫn có thể cùng xuất hiện trong list. Nhưng các cấu trúc **sorted set/map** dùng comparator để xác định **thứ tự và tính tương đương khóa theo so sánh**.

Ví dụ, một `TreeSet<Person>` chỉ so theo `age` sẽ xem hai người cùng tuổi là **tương đương đối với set** ngay cả khi tên/id khác nhau. Kết quả là một phần tử có thể không được thêm.

Tạo tệp **`TreeSetComparatorDemo.java`**:

```java
import java.util.Comparator;
import java.util.TreeSet;

public class TreeSetComparatorDemo {

    record Person(String name, int age) {
    }

    public static void main(String[] args) {
        TreeSet<Person> byAge = new TreeSet<>(
                Comparator.comparingInt(Person::age));

        byAge.add(new Person("An", 20));
        byAge.add(new Person("Binh", 20));

        System.out.println(byAge.size());

        TreeSet<Person> byAgeThenName = new TreeSet<>(
                Comparator.comparingInt(Person::age)
                        .thenComparing(Person::name));

        byAgeThenName.add(new Person("An", 20));
        byAgeThenName.add(new Person("Binh", 20));

        System.out.println(byAgeThenName.size());
    }
}
```

Chạy:

```bash
javac TreeSetComparatorDemo.java
java TreeSetComparatorDemo
```

Stdout:

```text
1
2
```

Vì sao?

- Comparator chỉ theo tuổi trả `0` cho hai người đều `20`, nên `TreeSet` coi phần tử thứ hai là trùng trong quan hệ thứ tự.
- Comparator nối thêm tên giúp phân biệt `"An"` và `"Binh"`, do đó giữ được hai bản ghi.

### `Comparator` có cần nhất quán với `equals` không?

Một comparator có thể hoạt động dù không nhất quán với `equals`, nhưng dùng nó trong `TreeSet`/`TreeMap` có thể tạo hành vi khác với kỳ vọng của hợp đồng `Set`/`Map` dựa trên `equals`. Với loại dữ liệu có identity nghiệp vụ, hãy cân nhắc thêm **tie-breaker duy nhất** như mã id.

Không nên tự động nối `hashCode()` để phân biệt các object: hash có thể va chạm, không phải khóa định danh bền vững.

## 20. Kết quả so bằng 0 và tie-breakers ổn định

Một comparator sắp xếp theo **điểm**:

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
```

xem mọi sinh viên cùng điểm tương đương về thứ tự. Điều này hoàn toàn hợp lệ nếu yêu cầu chỉ sắp xếp theo điểm. Nhưng nếu kết quả phải có thứ tự hoàn toàn xác định độc lập với thứ tự input, cần xác định thêm tiêu chí.

Ví dụ một bản ghi có id duy nhất:

```java
record Employee(long id, String name, int score) {
}

Comparator<Employee> order =
        Comparator.<Employee>comparingInt(Employee::score)
                .reversed()
                .thenComparing(Employee::name)
                .thenComparingLong(Employee::id);
```

Đây là đoạn minh họa cần đặt trong class/method thích hợp và import `Comparator`.

Nếu hai object có điểm và tên giống nhau nhưng id khác nhau, tiêu chí id sẽ phân biệt. Điều này hữu ích với báo cáo, phân trang hoặc dữ liệu từ nhiều nguồn vì ta không muốn kết quả phụ thuộc vào thứ tự ngẫu nhiên của input.

**Nhưng** nếu id cũng có thể trùng, comparator vẫn có thể trả `0`. Muốn thứ tự toàn phần tương thích nghiệp vụ, cần bảo đảm tập key cuối thật sự phân biệt những object cần phân biệt.

## 21. Key extractor có thể là một phép tính, nhưng nên thuần

`Comparator.comparing` không yêu cầu key extractor chỉ trả một field. Nó có thể là một function tính toán:

```java
record Ticket(String category, int basePrice, int fee) {
}

Comparator<Ticket> byTotal =
        Comparator.comparingInt(
                t -> t.basePrice() + t.fee());
```

Đoạn ví dụ trên giả định giá trị đủ nhỏ để phép cộng `int` không tràn. Nếu tiền có thể lớn, dùng `long`, `BigDecimal` hoặc kiểu tiền tệ theo thiết kế ứng dụng.

Những nguyên tắc tốt:

- Key extractor nên **deterministic** với cùng object khi dữ liệu không đổi.
- Tránh biến trạng thái hay side effects trong extractor/comparator.
- Không gọi mạng, đọc thời gian hiện tại hoặc lấy số ngẫu nhiên trong so sánh.
- Nếu tính key rất tốn kém, có thể **tính trước và lưu key** hoặc dùng dạng decorate-sort-undecorate; thuật toán sort có thể gọi comparator nhiều lần.
- Khi trường dùng để so sánh có thể thay đổi, tránh sửa nó trong lúc cấu trúc sorted set/map đang giữ object như một key. Thứ tự nội bộ có thể không còn phù hợp.

Một phép nối tiêu chí chỉ đúng khi từng comparator con thỏa hợp đồng so sánh.

## 22. `Comparator.naturalOrder`, `reverseOrder` và `reversed`

Ba thao tác dễ bị nhầm:

- `Comparator.naturalOrder()`: tạo comparator theo thứ tự tự nhiên của các giá trị `Comparable`.
- `Comparator.reverseOrder()`: tạo comparator theo thứ tự tự nhiên đảo chiều.
- `someComparator.reversed()`: đảo chiều **một comparator đã có**.

Ví dụ:

```java
Comparator<String> normal = Comparator.naturalOrder();
Comparator<String> reverse = Comparator.reverseOrder();

Comparator<String> lengthDesc =
        Comparator.comparingInt(String::length)
                .reversed();
```

Hai comparator đầu so chuỗi theo `String.compareTo`; comparator cuối so theo **độ dài giảm dần** chứ không theo bảng chữ cái.

Một tiêu chí nâng cao: generic signature của `naturalOrder()` yêu cầu `T` hỗ trợ `Comparable<? super T>`. Không thể dùng `naturalOrder()` trực tiếp cho một class không có natural order, chẳng hạn một record tự viết không implement `Comparable`.

Nếu muốn sắp xếp những object như vậy, truyền comparator riêng qua `sorted(comparator)` hoặc `List.sort(comparator)`.

## 23. Phân biệt `Comparator<? super T>` với `Comparator<T>`

Một helper generic nên nhận comparator có thể so được cả đối tượng kiểu `T`:

```java
static <T> void sortInPlace(
        java.util.List<T> values,
        java.util.Comparator<? super T> comparator) {
    values.sort(comparator);
}
```

Đây là method hợp lệ khi đặt trong class.

`Comparator<? super T>` cho phép:

- `Comparator<T>`: comparator trực tiếp của T.
- `Comparator<Object>`: comparator của supertype dùng được để so T nếu thực sự triển khai hợp đồng phù hợp.
- Các comparator của superclass/interface khác khi generic compatibility cho phép.

Cách khai báo linh hoạt này không có nghĩa Java tự coi `Comparator<Object>` là một thứ tự hợp lý về nghiệp vụ. Một comparator chỉ so `toString()` của mọi object chẳng hạn có thể chưa phải thứ tự bạn thực sự cần.

Đừng cast `Comparator<Object>` sang `Comparator<Student>` để lách compiler nếu API đã chấp nhận `? super T`: kiểu wildcard mô tả đúng quan hệ hướng tiêu thụ đối tượng.

## 24. Utility generic: sorted copy cho Collection bất kỳ

Tạo tệp **`GenericSortedCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;

public class GenericSortedCopyDemo {

    static <T> List<T> sortedCopy(
            Collection<? extends T> source,
            Comparator<? super T> order) {

        List<T> copy = new ArrayList<>(source);
        copy.sort(order);
        return copy;
    }

    public static void main(String[] args) {
        List<String> words = sortedCopy(
                List.of("zzz", "a", "bb"),
                Comparator.comparingInt(String::length));

        List<Integer> numbers = sortedCopy(
                List.of(5, 1, 3),
                Comparator.reverseOrder());

        System.out.println(words);
        System.out.println(numbers);
    }
}
```

Biên dịch/chạy:

```bash
javac GenericSortedCopyDemo.java
java GenericSortedCopyDemo
```

Stdout:

```text
[a, bb, zzz]
[5, 3, 1]
```

Giải thích chữ ký:

- `Collection<? extends T> source`: nguồn có thể cung cấp các phần tử phù hợp với T.
- `Comparator<? super T> order`: comparator có thể **nhận** T để so.
- `new ArrayList<>(source)`: tạo list riêng để không sắp xếp tại chỗ collection gốc.
- Trả `List<T>`: caller tiếp tục có kiểu tĩnh rõ ràng, không dùng raw `List`.

Đây là ví dụ nhỏ về sự kết hợp **Generic + Lambda/Method Reference + Comparator + PECS** trong một API chuẩn.

## 25. Sort tiếng Việt và locale: natural order không luôn đúng nghiệp vụ

`String.compareTo` so theo thứ tự được định nghĩa cho `String` trong Java, không phải trình tự chữ cái tiếng Việt mà người sử dụng mong muốn. Nếu dữ liệu là tên người/địa danh tiếng Việt, yêu cầu sắp xếp theo ngôn ngữ thường cần một **collator** phù hợp locale.

Ví dụ minh họa:

```java
java.text.Collator collator = java.text.Collator.getInstance(
        java.util.Locale.forLanguageTag("vi-VN"));

Comparator<String> vietnameseOrder =
        (a, b) -> collator.compare(a, b);
```

Đặt đoạn trên trong một method và import `java.util.Comparator` nếu biên dịch. `Collator.compare` cung cấp một quy tắc so sánh văn bản dựa vào locale. Có thể nối tiêu chí với một tie-breaker:

```java
Comparator<String> order =
        vietnameseOrder.thenComparing(
                Comparator.naturalOrder());
```

Đây là một ví dụ về **comparator của key tùy chỉnh**. Không nên giả định một kết quả sắp xếp Unicode cụ thể cho mọi JDK/locale provider nếu chưa xác định yêu cầu kiểm thử. Trường hợp hệ thống cần thứ tự nghiệp vụ chính xác phải kiểm tra bộ dữ liệu tiếng Việt đại diện, chính sách dấu/hoa-thường và môi trường runtime.

Đối với code đồng thời, không nên chia sẻ và thay đổi cấu hình một đối tượng `Collator` mutable giữa các thread mà không có chiến lược đồng bộ phù hợp.

## 26. Những lỗi phổ biến khi nối nhiều tiêu chí

**Lỗi 1 — Dùng phép trừ `a.score() - b.score()` làm comparator.** Có nguy cơ overflow và sai dấu. Dùng `comparingInt` hoặc `Integer.compare`.

**Lỗi 2 — Đặt `.reversed()` ở cuối dù chỉ muốn đảo tiêu chí chính.** Nó đảo **toàn bộ chuỗi** đã ghép. Muốn điểm giảm/tên tăng, đảo comparator điểm trước khi `thenComparing`.

**Lỗi 3 — Quên rằng `thenComparing` chỉ chạy khi tiêu chí trước trả 0.** Nếu comparator chính luôn trả số khác 0 cho các object cần buộc hòa, tiêu chí phụ sẽ không được xét.

**Lỗi 4 — Cho rằng `comparing(Student::name)` tự hỗ trợ null.** Không. Thêm `nullsFirst`/`nullsLast` ở đúng cấp khóa hoặc object.

**Lỗi 5 — Nhầm `nullsLast` ở khóa với ở bản thân phần tử.** `Comparator.comparing(Person::name, nullsLast(...))` vẫn không chấp nhận một `Person` null; cần bọc comparator bên ngoài.

**Lỗi 6 — Nghĩ `List.sort` tạo list mới.** Nó sửa list nhận lời gọi. Muốn bản sao, tạo `ArrayList` mới hoặc dùng stream rồi thu kết quả.

**Lỗi 7 — Gọi `sort` trên `List.of(...)`.** Những list này không hỗ trợ thay đổi; hãy copy trước khi sort.

**Lỗi 8 — Cho rằng `Stream.sorted` làm thay đổi nguồn.** Nó tạo một stage của stream; nguồn list không bị sort tại chỗ chỉ vì pipeline dùng `sorted`.

**Lỗi 9 — So theo một key rồi dùng `TreeSet` nhưng vẫn mong giữ mọi object khác nhau.** Trong `TreeSet`, `compare == 0` làm các object tương đương theo thứ tự; thêm tie-breakers nếu cần phân biệt.

**Lỗi 10 — Dùng comparator không nhất quán hoặc phụ thuộc trạng thái thay đổi.** Có thể phá hợp đồng transitivity/ordering. Tránh side effects và key mutable không được quản lý.

**Lỗi 11 — Dùng `Comparator.comparing` trên một key không implement `Comparable` mà không cung cấp key comparator.** Cần overload `comparing(extractor, keyComparator)`.

**Lỗi 12 — Nghĩ `Comparator<T>` phải so các field cũng có kiểu T.** Không. Key extractor có thể trả `U` khác, ví dụ `String` hoặc `LocalDate`.

**Lỗi 13 — Dùng raw `Comparator` để xử lý lỗi suy luận kiểu.** Làm mất kiểm tra generic và có thể phát sinh `ClassCastException`; dùng target type, explicit witness hoặc biến trung gian.

**Lỗi 14 — Cho rằng mọi natural string ordering là thứ tự tiếng Việt.** Nếu có yêu cầu locale, dùng `Collator` hoặc một rule cụ thể được thử nghiệm.

**Lỗi 15 — Dựa vào tính stable sort để không khai báo tie-breakers.** Stable sort bảo toàn thứ tự input giữa các phần tử bằng nhau theo comparator, nhưng không tạo một thứ tự toàn phần độc lập với input.

**Lỗi 16 — Không phân biệt `Comparator.reverseOrder()` và `existingComparator.reversed()`.** Dạng đầu là natural order đảo chiều; dạng sau đảo một comparator bất kỳ, kể cả comparator nhiều cấp.

## 27. Bài tập tự kiểm tra có đáp án

### Câu 1 — Phân biệt dấu của `compare`

`compare(a,b)` trả `-7` có hợp lệ không?

**Đáp án:** Có, nếu phù hợp hợp đồng comparator. Giá trị âm cho biết `a` đứng trước `b`; không cần đúng `-1`.

### Câu 2 — Chỉ đảo tiêu chí điểm

Muốn điểm giảm, tên tăng trong `Comparator<Student>`, đặt `.reversed()` ở đâu?

**Đáp án:** Ngay sau comparator điểm, **trước** `.thenComparing(Student::name)`.

### Câu 3 — Đảo cả chuỗi

Nếu có `byScore.thenComparing(byName).reversed()`, thứ tự của tiêu chí tên có đảo không?

**Đáp án:** Có; `.reversed()` đảo comparator hợp thành, nghĩa là đảo toàn bộ trật tự.

### Câu 4 — Null ở key

Một `Person` không null có `name = null`. Nên xử lý thế nào?

**Đáp án:** Truyền `Comparator.nullsFirst(...)` hoặc `.nullsLast(...)` như comparator **của khóa `name`** trong `Comparator.comparing(Person::name, keyComparator)`.

### Câu 5 — Null ở object

Một list chứa phần tử `Person` thực sự `null`. Nên xử lý thế nào?

**Đáp án:** Bao toàn bộ comparator `Person` bằng `Comparator.nullsFirst(personComparator)` hoặc `nullsLast(...)`.

### Câu 6 — Key extractor

`Comparator.comparingInt(Student::score)` dùng kiểu gì làm key?

**Đáp án:** Primitive `int`; không yêu cầu dùng wrapper `Integer` cho chữ ký extractor.

### Câu 7 — `TreeSet`

Hai `Student` khác id nhưng cùng điểm được thêm vào `TreeSet` dùng comparator **chỉ theo điểm**. Set có bảo đảm giữ cả hai không?

**Đáp án:** Không. Comparator có thể trả `0`, khiến `TreeSet` coi chúng là tương đương theo ordering.

### Câu 8 — `List.of`

`List.of(3,1,2).sort(Comparator.naturalOrder())` có sắp xếp được tại chỗ không?

**Đáp án:** Không theo hợp đồng unmodifiable list; nên tạo `new ArrayList<>(List.of(3,1,2))` rồi gọi `.sort(...)`.

### Câu 9 — `Comparator<? super T>`

Vì sao `List<T>.sort` nhận comparator có `? super T`?

**Đáp án:** Comparator là consumer của các giá trị T; comparator dành cho một supertype phù hợp vẫn so sánh được những đối tượng T.

### Câu 10 — Method reference

`Student::name` có loại chức năng gì trong `Comparator.comparing(Student::name)`?

**Đáp án:** Key extractor: nhận `Student`, trả một `String` để comparator so khóa tên.

### Câu 11 — Overflow

Vì sao không dùng `(a,b) -> a-b` trên toàn miền `int`?

**Đáp án:** Phép trừ có thể overflow và cho dấu sai, vi phạm thứ tự. Dùng `Integer.compare`.

### Câu 12 — Sort và stream

`list.stream().sorted(cmp).toList()` có tự thay đổi `list` không?

**Đáp án:** Không. Nó tạo một list kết quả theo thứ tự; `list.sort(cmp)` mới sửa list nhận lời gọi.

### Câu 13 — So theo ngày rồi id

Có `record Event(LocalDate at, long id)`. Cách nối tiêu chí?

```java
Comparator<Event> byDateThenId =
        Comparator.comparing(Event::at)
                .thenComparingLong(Event::id);
```

**Đáp án:** Hợp lệ khi import `Comparator`/`LocalDate` và `at` không null. `LocalDate` có natural order; id là khóa long dự phòng.

### Câu 14 — Giữ tính ổn định

Một ordered stream có hai phần tử được comparator xem là bằng nhau (`compare == 0`). `sorted(cmp)` có bảo đảm ổn định không?

**Đáp án:** Có đối với **ordered streams**. Với unordered streams, không có cam kết tương tự.

## 28. Thực hành tổng hợp: thiết kế comparator sẵn dùng cho nghiệp vụ

Một ứng dụng quản lý sản phẩm muốn:

1. Sản phẩm còn hàng (`inStock`) đứng trước hết hàng.
2. Trong mỗi nhóm trạng thái, giá tăng dần.
3. Nếu giá bằng nhau, tên tăng dần (không phân biệt hoa thường).
4. Nếu vẫn bằng, so tiếp mã sản phẩm để thứ tự ổn định.

Tạo tệp **`BusinessOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class BusinessOrderDemo {

    record Product(
            String code,
            String name,
            int price,
            boolean inStock) {
    }

    public static void main(String[] args) {
        List<Product> products = new ArrayList<>(List.of(
                new Product("P3", "Beta", 120, true),
                new Product("P2", "Alpha", 100, false),
                new Product("P4", "alpha", 100, true),
                new Product("P1", "Alpha", 100, true)
        ));

        Comparator<Product> order =
                Comparator.<Product, Boolean>comparing(
                                Product::inStock,
                                Comparator.reverseOrder())
                        .thenComparingInt(Product::price)
                        .thenComparing(
                                Product::name,
                                String.CASE_INSENSITIVE_ORDER)
                        .thenComparing(Product::code);

        products.sort(order);

        for (Product p : products) {
            System.out.println(
                    p.code() + "|" + p.inStock()
                    + "|" + p.price() + "|" + p.name());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac BusinessOrderDemo.java
java BusinessOrderDemo
```

Stdout:

```text
P1|true|100|Alpha
P4|true|100|alpha
P3|true|120|Beta
P2|false|100|Alpha
```

Giải thích:

- `Product::inStock` trả primitive `boolean`. Trong overload `comparing` với key type `Boolean`, compiler dùng boxing để so khóa; `Comparator.reverseOrder()` đặt `true` trước `false` vì natural order của `Boolean` là `false < true`.
- `thenComparingInt(Product::price)` xếp giá từ thấp lên cao bên trong từng nhóm trạng thái.
- `thenComparing(Product::name, String.CASE_INSENSITIVE_ORDER)` so tên mà không phân biệt chữ hoa/thường.
- Với `"Alpha"` và `"alpha"` cùng giá và cùng trạng thái, comparator tên trả `0`, nên mã `P1` đứng trước `P4`.
- Không cần raw type, unchecked cast hoặc viết một `compare` dài có nhiều nhánh.

Nếu tên sản phẩm cho phép `null`, phải thay comparator tên bằng `Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)` hoặc chính sách khác trước khi dùng trên dữ liệu thực.

## 29. Quy trình thực tế khi xây chuỗi comparator

Khi nhận một yêu cầu sắp xếp nhiều khóa:

1. **Ghi rõ thứ tự ưu tiên** của từng tiêu chí. Ví dụ: trạng thái → điểm → tên → id.
2. **Ghi chiều tăng/giảm và chính sách null** cho từng tiêu chí.
3. **Chọn key extractor phù hợp:** `comparingInt` cho `int`, `comparingLong` cho `long`, `comparing` cho khóa đối tượng có natural order.
4. **Dùng key comparator riêng** nếu cần thứ tự tùy chỉnh, case-insensitive, locale hoặc null placement.
5. **Đặt `.reversed()` ở phạm vi chính xác**, hoặc xây comparator tiêu chí riêng khi có nhiều chiều sắp xếp.
6. **Nối `thenComparing` theo đúng mức ưu tiên**. Các tiêu chí sau chỉ được xét khi trước đó hòa.
7. **Thêm tie-breaker đủ mạnh** nếu API cần thứ tự kết quả xác định hoặc dùng trong `TreeSet`/`TreeMap`.
8. **Kiểm tra contract** với các giá trị biên: `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `null`, khóa trùng, chữ hoa/thường và các khóa mutable.
9. **Chọn API sử dụng:** `List.sort` khi muốn sửa list, `Stream.sorted` khi muốn kết quả mới, `TreeSet`/`TreeMap` khi ordering là cấu trúc dữ liệu.
10. **Viết test có kết quả cụ thể**, không chỉ thử một danh sách đã có thứ tự sẵn.
11. **Giữ comparator thuần**, tránh side effects; nếu extract key tốn kém, cân nhắc caching/precomputation.
12. **Giữ kiểu generic đầy đủ** và dùng target typing/explicit type witness nếu compiler không suy luận được method chain.

Một chuỗi comparator đúng không chỉ sắp xếp được danh sách demo, mà còn giữ đúng hành vi khi dữ liệu nhiều, khóa trùng và biên giá trị xuất hiện.

## 30. Tổng kết và nguồn tra cứu

**`Comparator<T>` là một functional interface generic định nghĩa cách so hai đối tượng cùng kiểu T.** Nó có thể được viết bằng lambda, method reference hoặc các factory như `comparing`, `comparingInt`, `comparingLong`, `comparingDouble`. Khi cần nhiều tiêu chí, nối chúng bằng `thenComparing` và các overload theo key extractor.

Ba điểm đặc biệt quan trọng:

- **Thứ tự ưu tiên** được xác định bằng thứ tự nối comparator. Một key phụ chỉ dùng khi các key trước trả `0`.
- **Chiều sắp xếp** phụ thuộc vị trí `.reversed()`: gọi ở cuối sẽ đảo toàn bộ comparator, còn gọi ngay sau comparator chính chỉ đảo phần chính trước khi nối.
- **An toàn kiểu và đúng hợp đồng** phụ thuộc generic signatures, null handling, tránh overflow và bảo đảm comparator hợp lệ. Dùng `Comparator<? super T>` trong API generic phù hợp và nhớ `TreeSet`/`TreeMap` dựa vào `compare == 0` để xác định khóa tương đương.

Đối với Java 17+, cách diễn đạt tiêu chí thường rõ ràng hơn khi tách từng khóa, dùng primitive comparators khi phù hợp, đặt tên các comparators phức tạp và viết test có tie-breakers. Không cần lạm dụng raw types hoặc unchecked casts.

Tài liệu chuẩn:

- [Java SE 17 — `java.util.Comparator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): `compare`, `comparing`, `thenComparing`, `reversed`, `nullsFirst/nullsLast`.
- [Java SE 17 — `java.util.List.sort`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)): sắp xếp list tại chỗ và hợp đồng stability.
- [Java SE 17 — `java.util.stream.Stream.sorted`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#sorted(java.util.Comparator)): sắp xếp stream với comparator.
- [Java SE 17 — `java.util.TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html): comparator quyết định ordering và equivalence của phần tử trong sorted set.
- [Java Language Specification §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): target typing của lambda.
- [Java Language Specification §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): method references trong functional interfaces.
- [Java Language Specification §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): suy luận generic type arguments.
- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): kiểu tham số hóa và quan hệ type arguments.