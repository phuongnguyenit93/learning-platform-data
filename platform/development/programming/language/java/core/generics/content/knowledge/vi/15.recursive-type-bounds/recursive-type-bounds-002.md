# `<T extends Comparable<T>>` trong thuật toán so sánh

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Đọc đúng ràng buộc generic đệ quy `<T extends Comparable<T>>` và giải thích vì sao trình biên dịch cho phép gọi `compareTo` trên giá trị kiểu `T`.
- Viết thuật toán tìm giá trị nhỏ hơn và sắp xếp danh sách theo **thứ tự tự nhiên** (natural ordering) mà không cần ép kiểu hoặc dùng kiểu thô (`raw type`).
- Tự xây dựng một kiểu dữ liệu cài đặt `Comparable<T>`, xác định quy tắc so sánh và dự đoán kết quả chạy.
- Nhận ra giới hạn của ràng buộc chính xác `Comparable<T>`, biết khi nào cần `Comparable<? super T>` hoặc `Comparator<? super T>`.
- Tránh các lỗi thường gặp với `compareTo`, `null`, danh sách không thể sửa và quy tắc nhất quán khi sắp xếp.

## 1. Bài toán: thuật toán cần biết hai giá trị so sánh với nhau thế nào

Giả sử muốn viết một hàm chọn giá trị nhỏ hơn cho nhiều kiểu dữ liệu:

- Hai số nguyên `Integer`: `2` nhỏ hơn `7`.
- Hai chuỗi `String`: so sánh theo thứ tự từ điển do `String.compareTo` định nghĩa.
- Hai đối tượng `Student`: có thể tự định nghĩa so sánh theo điểm, sau đó theo tên.

Viết `static <T> T min(T a, T b)` **chưa đủ**. `T` không bị ràng buộc có phương thức `compareTo`, nên biểu thức `a.compareTo(b)` không biên dịch. Generic chỉ cho trình biên dịch biết hai tham số liên quan đến cùng một kiểu suy luận; nó không tự tạo quy tắc thứ tự.

Java cung cấp giao diện:

```java
public interface Comparable<T> {
    int compareTo(T other);
}
```

Đây là trích yếu chữ ký để giải thích, không phải mã cần tự định nghĩa lại giao diện trong `java.lang`.

Một đối tượng cài đặt `Comparable<X>` có thể so sánh với đối tượng kiểu `X` thông qua `compareTo(X)`. Kết quả mang **dấu**, không nhất thiết chỉ nhận `-1`, `0`, `1`:

| Giá trị trả về của `a.compareTo(b)` | Ý nghĩa |
| --- | --- |
| Nhỏ hơn `0` | `a` đứng trước `b` |
| Bằng `0` | `a` và `b` ngang nhau **theo thứ tự so sánh** |
| Lớn hơn `0` | `a` đứng sau `b` |

`compareTo(...) == 0` không mặc nhiên đồng nghĩa với `equals(...)` trả về `true`.

## 2. Đọc chính xác ràng buộc đệ quy

```java
public static <T extends Comparable<T>> T min(T a, T b) {
    return a.compareTo(b) <= 0 ? a : b;
}
```

Tách cú pháp thành ba phần:

1. `<T ...>`: khai báo tham số kiểu `T` của **phương thức**.
2. `T extends Comparable<T>`: `T` phải là kiểu thỏa ràng buộc có thể so sánh với các giá trị `T`. Trong ràng buộc kiểu Java, từ khóa `extends` cũng dùng khi giới hạn bởi một **interface**, không yêu cầu interface là class cha.
3. `T min(T a, T b)`: kiểu giá trị trả về và kiểu tham số sử dụng `T`, giúp kết quả giữ được thông tin kiểu ở thời điểm biên dịch.

Điểm **đệ quy** nằm ở chỗ `T` xuất hiện bên trong chính giới hạn của nó: `T extends Comparable<T>`. Mẫu này thường được gọi là *F-bounded polymorphism* hoặc *self-referential type bound*. Nó biểu đạt quan hệ kiểu trong hệ thống type, không có nghĩa phương thức `min` hay `compareTo` tự gọi lại chính mình lúc chạy.

Ví dụ hợp lệ: `Integer` cài đặt `Comparable<Integer>`; `String` cài đặt `Comparable<String>`. Nếu `Student implements Comparable<Student>` thì cũng có thể dùng `Student` trong `min`.

Điều trình biên dịch kiểm tra:

- Có thể gọi `a.compareTo(b)` với `a` và `b` được gắn kiểu `T`.
- Không thể truyền một kiểu bất kỳ không thỏa ràng buộc làm `T`.
- Không cần ép `Object` sang `Comparable` hoặc bỏ kiểm tra kiểu bằng `Comparable` thô.

Điều trình biên dịch **không** đảm bảo: cách cài đặt `compareTo` có đúng, có đối xứng, bắc cầu hay xử lý mọi cặp đối tượng trong miền dữ liệu không. Đó là trách nhiệm của người viết kiểu dữ liệu.

## 3. Ví dụ chạy được: `min` và insertion sort

Tạo tệp `ComparableAlgorithms.java` với toàn bộ mã sau (Java 17 trở lên):

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ComparableAlgorithms {

    public static <T extends Comparable<T>> T min(T left, T right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.compareTo(right) <= 0 ? left : right;
    }

    public static <T extends Comparable<T>> void insertionSort(List<T> values) {
        Objects.requireNonNull(values, "values");
        for (T value : values) {
            Objects.requireNonNull(value, "element");
        }

        for (int i = 1; i < values.size(); i++) {
            T key = values.get(i);
            int j = i - 1;

            while (j >= 0 && values.get(j).compareTo(key) > 0) {
                values.set(j + 1, values.get(j));
                j--;
            }
            values.set(j + 1, key);
        }
    }

    record Student(String name, int grade) implements Comparable<Student> {
        public Student {
            Objects.requireNonNull(name, "name");
        }

        @Override
        public int compareTo(Student other) {
            Objects.requireNonNull(other, "other");
            int byGrade = Integer.compare(grade, other.grade);
            return byGrade != 0 ? byGrade : name.compareTo(other.name);
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(List.of(7, 2, 5, 2));
        insertionSort(numbers);
        System.out.println("Numbers: " + numbers);
        System.out.println("Min: " + min(7, 2));

        List<Student> students = new ArrayList<>(List.of(
                new Student("Lan", 9),
                new Student("Minh", 7),
                new Student("An", 9)));
        insertionSort(students);
        System.out.println("Students: " + students);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ComparableAlgorithms.java
java ComparableAlgorithms
```

Stdout thực tế đã kiểm tra bằng `javac` và `java`:

```text
Numbers: [2, 2, 5, 7]
Min: 2
Students: [Student[name=Minh, grade=7], Student[name=An, grade=9], Student[name=Lan, grade=9]]
```

### Vì sao ví dụ biên dịch?

- `Integer` và `Student` đều thỏa `Comparable<T>` với đúng kiểu tương ứng.
- `min(7, 2)` dùng *autoboxing*: đối số `int` được đưa vào lời gọi generic thông qua `Integer`.
- `Student.compareTo(Student)` so sánh điểm tăng dần bằng `Integer.compare`. Khi hai điểm bằng nhau, tên quyết định thứ tự tiếp theo. Với dữ liệu trên, Minh (7) đứng trước An (9) và Lan (9); An đứng trước Lan theo tên.
- `record Student` tự sinh `toString()`, nên danh sách in ra dạng `Student[name=..., grade=...]`.

Chương trình cố ý tạo `new ArrayList<>(List.of(...))`: `List.of` trả về danh sách không hỗ trợ thay đổi phần tử; thuật toán dùng `List.set`, nên cần danh sách có thể sửa. Phương thức cũng chủ động từ chối phần tử `null`.

### Thuật toán insertion sort vận hành ra sao?

Với `[7, 2, 5, 2]`:

| Lần lặp | Phần tử khóa | Dãy sau khi chèn |
| --- | --- | --- |
| Ban đầu | — | `[7, 2, 5, 2]` |
| `i = 1` | `2` | `[2, 7, 5, 2]` |
| `i = 2` | `5` | `[2, 5, 7, 2]` |
| `i = 3` | `2` | `[2, 2, 5, 7]` |

Ở mỗi vòng, đoạn `[0, i)` đã được sắp xếp. Khi `values.get(j).compareTo(key) > 0`, thuật toán dịch phần tử lớn hơn khóa sang phải để tạo chỗ chèn. Điều kiện **`> 0`**, thay vì `>= 0`, không di chuyển phần tử đứng trước có khóa bằng nhau, vì vậy insertion sort này **ổn định** nếu `compareTo` tuân thủ hợp đồng so sánh.

Độ phức tạp của cách cài đặt: thời gian tốt nhất `O(n)` khi danh sách đã có thứ tự, trung bình/xấu nhất `O(n²)`; bộ nhớ phụ `O(1)` ngoài các biến lặp. Ví dụ dùng thuật toán đơn giản để làm rõ generic, không đại diện cho triển khai sắp xếp tối ưu trong thư viện chuẩn. Trong ứng dụng, thường ưu tiên `List.sort` hoặc `Collections.sort`.

## 4. Tự định nghĩa `Comparable<T>`: hợp đồng phải đúng

Khi tạo thứ tự tự nhiên cho một lớp, hãy chọn rõ **khóa sắp xếp**, chiều tăng/giảm, cách xử lý trường hợp bằng nhau và khả năng gặp `null`.

Một cách an toàn cho các trường số nguyên:

```java
int byGrade = Integer.compare(this.grade, other.grade);
```

Tránh viết:

```java
return this.grade - other.grade;
```

vì phép trừ có thể tràn số nguyên khi dữ liệu gần `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`, dẫn đến dấu kết quả sai. Khi dùng nhiều trường, so sánh trường tiếp theo **chỉ khi** trường trước cho kết quả `0`.

Theo hợp đồng `Comparable`, với các giá trị phù hợp để so sánh:

- **Đổi chiều dấu:** dấu của `a.compareTo(b)` đối nghịch dấu của `b.compareTo(a)`.
- **Bắc cầu:** nếu `a > b` và `b > c` thì `a > c`.
- **Tương đương nhất quán:** nếu `a.compareTo(b) == 0`, hai đối tượng phải có cùng quan hệ thứ tự với mọi `z` hợp lệ.
- **Nhất quán với `equals` là điều nên làm**, nhưng không bắt buộc về mặt giao diện. `BigDecimal("1.0")` và `BigDecimal("1.00")` so sánh theo `compareTo` bằng `0` nhưng `equals` là `false`.

Sự khác biệt giữa `compareTo` và `equals` đặc biệt quan trọng với `TreeSet`/`TreeMap`: chúng xác định khóa trùng theo thứ tự so sánh, nên hai đối tượng mà `compareTo` cho `0` có thể bị xem như một khóa ngay cả khi `equals` là `false`.

Không nhất thiết cho phép so sánh đối tượng `null`: `Comparable.compareTo(null)` thông thường ném `NullPointerException`. Nếu thứ tự cần hỗ trợ `null`, hãy chủ động thiết kế ở tầng `Comparator.nullsFirst` hoặc `Comparator.nullsLast`.

## 5. Khi bound `Comparable<T>` quá chặt

Ví dụ, `Employee implements Comparable<Employee>` và `Manager extends Employee`. `Manager` kế thừa phương thức `compareTo(Employee)`, có thể so sánh với `Manager` khác, nhưng **không tự động** trở thành `Comparable<Manager>` vì generic bất biến.

```java
class Employee implements Comparable<Employee> {
    final int id;
    Employee(int id) { this.id = id; }
    @Override public int compareTo(Employee other) {
        return Integer.compare(id, other.id);
    }
}

class Manager extends Employee {
    Manager(int id) { super(id); }
}
```

Giới hạn ở ví dụ insertion sort là `T extends Comparable<T>`: với `T = Manager`, yêu cầu này không thỏa. Nếu thuật toán chỉ cần `compareTo` nhận một `T`, chữ ký linh hoạt hơn là:

```java
static <T extends Comparable<? super T>> void flexibleSort(List<T> xs) {
    java.util.Collections.sort(xs);
}
```

Khi `T=Manager`, `Comparable<Employee>` đáp ứng `Comparable<? super Manager>`, nên `flexibleSort(List<Manager>)` có thể biên dịch. **Lưu ý về type inference:** với các chữ ký nhận `List<? extends T>`, compiler có lúc có thể chọn `T=Employee`; lúc ấy kiểu trả về có thể kém chuyên biệt. Sự khác nhau cốt lõi nằm ở bound được yêu cầu khi **chốt `T=Manager`**.

Mục này là cầu nối từ thuật toán `Comparable<T>` sang giới hạn linh hoạt. Bài tiếp theo đi sâu chứng minh hướng consumer `? super T`, wildcard containment, thư viện chuẩn `Collections.max` và những lỗi khi dùng `? extends T`/`Comparable<?>` thay thế.

## 6. Khi nào nên dùng `Comparator<? super T>`?

`Comparable<T>` gắn **một thứ tự tự nhiên** vào bản thân kiểu. Thực tế cùng một đối tượng có thể cần nhiều cách sắp xếp: sinh viên theo điểm hoặc tên; sản phẩm theo giá hoặc mã. Khi không thể hoặc không muốn thay đổi lớp dữ liệu, truyền chiến lược so sánh riêng:

```java
public static <T> T min(
        T first, T second, java.util.Comparator<? super T> order) {
    java.util.Objects.requireNonNull(order, "order");
    return order.compare(first, second) <= 0 ? first : second;
}
```

Đây là **overload độc lập về ý tưởng** với phương thức `min` theo `Comparable`; để chạy, đặt nó trong một lớp và có phương thức `main` gọi nó.

Với Java 17, có thể dùng comparator tạo từ record:

```java
record Book(String title, int pages) {}

java.util.Comparator<Book> byPagesThenTitle =
        java.util.Comparator.comparingInt(Book::pages)
                .thenComparing(Book::title);

Book chosen = min(
        new Book("Java", 320),
        new Book("Basics", 180),
        byPagesThenTitle);
// chosen.pages() == 180
```

Đoạn trên minh họa khai báo record và cách gọi trong ngữ cảnh có phương thức `min(..., Comparator)`; riêng nó không chứa `main`.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Kiểu dữ liệu có một thứ tự tự nhiên rõ ràng | Cài `Comparable<T>` |
| Viết thuật toán generic đơn giản theo thứ tự tự nhiên | `<T extends Comparable<T>>` |
| Cần chấp nhận kiểu con thừa kế khả năng so sánh với kiểu cha | `<T extends Comparable<? super T>>` |
| Sắp xếp nhiều tiêu chí hoặc không sửa được lớp dữ liệu | `Comparator<? super T>` |
| Danh sách có phần tử `null` và cần quy tắc rõ | `Comparator.nullsFirst(...)` / `nullsLast(...)` |

`Comparator<? super T>` sử dụng nguyên lý *consumer*: bộ so sánh nhận hai giá trị `T`, nên comparator của kiểu cha cũng có thể so sánh các đối tượng kiểu con. Với `List.sort`, ví dụ `students.sort(Comparator.comparing(Student::name))` tạo thứ tự theo tên, không đổi thứ tự tự nhiên đã cài trong `Student.compareTo`.

## 7. Lỗi thường gặp và cách sửa

**Lỗi 1 — Chưa có ràng buộc:**

```java
static <T> T smaller(T a, T b) {
    return a.compareTo(b) <= 0 ? a : b; // Lỗi biên dịch
}
```

Trình biên dịch không biết `T` có `compareTo`. Sửa bằng `<T extends Comparable<T>>` khi muốn thứ tự tự nhiên, hoặc nhận thêm `Comparator<? super T>`.

**Lỗi 2 — Dùng sai kiểu tham số của Comparable:**

```java
class Ticket implements Comparable<String> {
    @Override
    public int compareTo(String other) {
        return 0;
    }
}
```

`Ticket` không thỏa `T extends Comparable<T>` với `T = Ticket`. Việc viết `Comparable<String>` chỉ nói `Ticket` so sánh với `String`; điều này không đáp ứng yêu cầu so sánh hai `Ticket` với nhau. Để sắp xếp nhiều `Ticket`, cân nhắc `Comparable<Ticket>` hoặc comparator bên ngoài.

**Lỗi 3 — Hiểu `compareTo` chỉ trả `-1, 0, 1`:** chỉ kiểm tra **dấu** với `< 0`, `== 0`, `> 0`; không viết điều kiện như `compareTo(x) == 1`.

**Lỗi 4 — Thứ tự không bắc cầu:** so sánh theo quy tắc mâu thuẫn giữa các cặp có thể gây kết quả sắp xếp sai; thuật toán trong thư viện thậm chí có thể báo vi phạm hợp đồng so sánh ở một số tình huống. Kiểm tra quy tắc đối chiếu và kết hợp nhiều trường trước khi dùng.

**Lỗi 5 — Danh sách không thể sửa:** gọi `insertionSort(List.of(...))` có thể gây `UnsupportedOperationException` khi cần `set`. Dùng `new ArrayList<>(List.of(...))` nếu thuật toán sửa danh sách tại chỗ.

**Lỗi 6 — `null` hoặc kiểu phần tử không so sánh được:** ràng buộc generic là kiểm tra ở thời điểm biên dịch, nhưng không tự ngăn mọi dữ liệu `null` lúc chạy. Với sắp xếp theo thứ tự tự nhiên, kiểu `Object` hoặc `Number` không tự nhiên thỏa `Comparable` cần thiết chỉ vì vài đối tượng cụ thể bên trong là `Integer`. Định kiểu dữ liệu chặt chẽ hoặc cung cấp comparator phù hợp.

**Lỗi 7 — Kiểu thô và cast để lách kiểm tra:** dùng `Comparable` không có tham số kiểu hay cast tùy tiện làm mất bảo đảm kiểu, có thể đẩy lỗi sang `ClassCastException` lúc chạy. Giữ đầy đủ tham số generic và quan hệ so sánh đã khai báo.

## 8. Bài tập tự kiểm tra

1. Viết `max(T a, T b)` với giới hạn `<T extends Comparable<T>>`. Khi `a.compareTo(b) == 0`, trả về `a`; giải thích vì sao toán tử `>= 0` là đủ.
2. Sửa `Student.compareTo` để điểm **giảm dần** nhưng tên vẫn **tăng dần** khi trùng điểm. Gợi ý: dùng `Integer.compare(other.grade, grade)`, giữ `name.compareTo(other.name)` ở bước sau.
3. Cho `class Child extends Parent` và `Parent implements Comparable<Parent>`. Giải thích vì sao `List<Child>` cần chữ ký `Comparable<? super T>` khi đưa vào thuật toán sắp xếp generic.
4. Chỉ ra lỗi trong `return x - y;` khi so sánh hai số nguyên và viết lại bằng `Integer.compare(x, y)`.
5. Với hai `BigDecimal` biểu diễn `1.0` và `1.00`, dự đoán tác động của `compareTo` và `equals` khi đưa vào tập `TreeSet`.

**Tự đối chiếu:** (1) dùng `a.compareTo(b) >= 0 ? a : b`; (2) đảo thứ tự tham số so sánh điểm, không đảo phần tên; (3) kiểu con kế thừa `Comparable<Parent>`, không tự có `Comparable<Child>`; (4) phép trừ có nguy cơ tràn số; (5) `compareTo` trả `0` còn `equals` trả `false`, và `TreeSet` dựa vào kết quả so sánh nên chỉ giữ một phần tử tương đương về thứ tự.

## Ghi nhớ khi áp dụng

Mẫu `<T extends Comparable<T>>` cho phép **thuật toán generic gọi trực tiếp `compareTo(T)` với an toàn kiểu tại thời điểm biên dịch**. Dùng nó để hiểu và tự triển khai thuật toán theo natural ordering; khi xây API dùng lại rộng rãi, cân nhắc `Comparable<? super T>` cho quan hệ kế thừa và `Comparator<? super T>` cho thứ tự tùy biến. Kiểm tra hợp đồng `compareTo`, dữ liệu `null`, khả năng sửa danh sách và ngữ nghĩa bằng nhau trước khi đưa thuật toán vào sử dụng.
