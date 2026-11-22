# Vì sao thường cần `Comparable<? super T>` trong giới hạn đệ quy?

Khi viết thuật toán tìm phần tử lớn nhất, sắp xếp hoặc xử lý các đối tượng theo **thứ tự tự nhiên** (natural ordering), ta thường gặp chữ ký generic:

```java
<T extends Comparable<? super T>>
```

Câu hỏi cốt lõi: vì sao không viết ngắn hơn thành `<T extends Comparable<T>>`? Lý do là **một lớp con có thể kế thừa cách so sánh do lớp cha định nghĩa**, và thuật toán vẫn phải dùng được với lớp con đó mà giữ nguyên kiểu kết quả.

## 1. Hai phần của giới hạn có ý nghĩa khác nhau

Trong Java, `Comparable<X>` biểu thị một kiểu có phương thức:

```java
int compareTo(X other);
```

Đây là chữ ký rút gọn để giải thích kiểu tham số, không phải khai báo lại thư viện chuẩn. Theo hợp đồng của `Comparable`, `compareTo` trả về số âm, số 0 hoặc số dương khi đối tượng hiện tại lần lượt nhỏ hơn, bằng thứ tự hoặc lớn hơn đối tượng được truyền vào.

Xét giới hạn:

```java
<T extends Comparable<? super T>>
```

- `T extends ...`: **giới hạn trên của tham số kiểu** `T`; đối tượng kiểu `T` phải có khả năng so sánh theo `Comparable` phù hợp.
- `Comparable<? super T>`: đối tượng kiểu `T` có thể triển khai `Comparable<T>`, hoặc `Comparable<S>` với một **kiểu cha `S` của `T`**.
- Vị trí `T` bên trong điều kiện của chính `T` tạo thành dạng **giới hạn đệ quy** (recursive bound, thường gọi là F-bounded polymorphism). Wildcard `? super T` mở rộng các cách triển khai được chấp nhận.

Đặc biệt, `extends` và `super` ở đây không mâu thuẫn: `extends` giới hạn *kiểu của phần tử*, còn `super` nới *kiểu đối số mà compareTo nhận vào*.

## 2. Tình huống thực tế: lớp con dùng cách so sánh của lớp cha

Giả sử `Person` biết so sánh tuổi với một `Person` khác:

```java
class Person implements Comparable<Person> {
    @Override
    public int compareTo(Person other) {
        // So sánh theo tuổi
        return 0; // Minh họa chữ ký; xem bản chạy đầy đủ bên dưới
    }
}

class Student extends Person {
}
```

Đoạn trên chỉ minh họa quan hệ kiểu, không phải chương trình hoàn chỉnh. Quan hệ quan trọng là:

```text
Student extends Person
Person implements Comparable<Person>
=> Student kế thừa Comparable<Person>
```

Một `Student` có thể gọi `compareTo` với một `Student` khác, bởi `Student` **là một** `Person`. Nhưng điều đó **không** làm `Student` tự động trở thành `Comparable<Student>`.

Lý do: generic trong Java **bất biến** (invariant). `Comparable<Person>` không phải là kiểu con của `Comparable<Student>`, dù `Student` là kiểu con của `Person`.

Vì vậy:

| Ràng buộc cần thỏa | `Student` có thỏa không? | Giải thích |
| --- | --- | --- |
| `T extends Comparable<T>` với `T = Student` | Không | `Student` kế thừa `Comparable<Person>`, không phải `Comparable<Student>` |
| `T extends Comparable<? super T>` với `T = Student` | Có | `Person` là kiểu cha của `Student`, nên `Comparable<Person>` khớp `Comparable<? super Student>` |
| `T extends Comparable<? super T>` với `T = Person` | Có | `Comparable<Person>` khớp trực tiếp |

Đó là lý do phiên bản có `? super T` chấp nhận được nhiều mô hình kế thừa hợp lệ hơn.

## 3. Chương trình Java 17+ chạy được

Lưu mã sau trong tệp `ComparableSuperDemo.java`:

```java
import java.util.Collections;
import java.util.List;

public class ComparableSuperDemo {
    static class Person implements Comparable<Person> {
        private final String name;
        private final int age;

        Person(String name, int age) {
            this.name = name;
            this.age = age;
        }

        @Override
        public int compareTo(Person other) {
            return Integer.compare(this.age, other.age);
        }

        @Override
        public String toString() {
            return name + " (" + age + ")";
        }
    }

    static final class Student extends Person {
        Student(String name, int age) {
            super(name, age);
        }
    }

    static <T extends Comparable<? super T>> T maxOf(List<? extends T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("Danh sách phải có phần tử");
        }

        T best = values.get(0);
        for (T candidate : values) {
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        List<Student> students = List.of(
                new Student("An", 20),
                new Student("Binh", 22),
                new Student("Chi", 21)
        );

        Student customResult = maxOf(students);
        Student libraryResult = Collections.max(students);

        System.out.println("maxOf: " + customResult);
        System.out.println("Collections.max: " + libraryResult);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ComparableSuperDemo.java
java ComparableSuperDemo
```

Kết quả chuẩn:

```text
maxOf: Binh (22)
Collections.max: Binh (22)
```

Trong ví dụ này, **thứ tự tự nhiên là theo tuổi**, không phải theo tên. `Integer.compare` tránh lỗi tràn số có thể xảy ra khi lấy hiệu hai số nguyên để so sánh. `Student` không tự định nghĩa `compareTo`; nó kế thừa `Person.compareTo(Person)`. Dù vậy, cả hàm `maxOf` lẫn `Collections.max` đều nhận `List<Student>` và trả kết quả gán được cho biến `Student`.

Hãy chú ý hai wildcard độc lập trong chữ ký `maxOf`:

- `Comparable<? super T>` quy định **đối tượng kiểu `T` có thể so sánh với `T`**.
- `List<? extends T>` quy định **nguồn dữ liệu có các phần tử đọc được dưới dạng `T`**. Nó không thay thế vai trò của `? super T` trong `Comparable`.

Với lời gọi `maxOf(students)`, Java có thể chọn `T = Student`: phần tử đọc ra vẫn là `Student`, và `compareTo` chấp nhận nó dưới dạng `Person`.

## 4. Tại sao lời gọi `compareTo` là an toàn?

Giả sử một đối tượng kiểu `T` triển khai `Comparable<S>`, trong đó `S` là `T` hoặc một kiểu cha của `T`. Ta có:

```text
T là subtype của S
Comparable<S> cung cấp compareTo(S other)
Mọi giá trị T có thể truyền vào tham số S
=> candidate.compareTo(best) hợp lệ khi cả hai có kiểu T
```

Tổng quát hơn, `? super T` đại diện cho một kiểu chưa biết `S` nhưng Java biết `T` có thể chuyển thành `S`. Thuật toán không cần biết `S` cụ thể là `T`, `Person` hay một kiểu cha khác.

Không nên diễn giải `Comparable<? super T>` thành “`compareTo` nhận mọi `Object`”. Phương thức thực tế vẫn có kiểu tham số do lớp triển khai quyết định; trong ví dụ nó nhận `Person`. Wildcard chỉ giúp trình biên dịch chứng minh rằng **truyền một giá trị `T` là hợp lệ**.

## 5. Nếu chỉ dùng `Comparable<T>` thì gặp vấn đề gì?

Xét một phương thức minh họa có điều kiện chặt hơn:

```java
// Chỉ minh họa sự khác biệt về ràng buộc kiểu:
static <T extends Comparable<T>> T strictFirst(List<T> values) {
    return values.get(0);
}
```

Nếu đặt phương thức này vào lớp `ComparableSuperDemo` ở trên, lời gọi cố định tham số kiểu sau **không biên dịch**:

```java
// Dòng kiểm tra âm tính; đừng chèn vào chương trình muốn chạy:
Student s = ComparableSuperDemo.<Student>strictFirst(students);
```

Trình biên dịch yêu cầu `Student extends Comparable<Student>`, nhưng `Student` chỉ kế thừa `Comparable<Person>`. Việc `compareTo(Person)` vẫn so sánh được hai sinh viên không thay đổi tính bất biến của `Comparable<X>`.

Cũng cần phân biệt **giới hạn kiểu** và **suy luận kiểu**. Ở một số chữ ký khác cho phép tham số `List<? extends T>`, trình biên dịch có thể suy luận `T = Person` để một lời gọi với `List<Student>` hợp lệ; khi đó kết quả tĩnh có thể chỉ là `Person`. Còn `Comparable<? super T>` cho phép dùng chính `T = Student` mà vẫn giữ thông tin kiểu cụ thể.

## 6. Vì sao không dùng `Comparable<? extends T>` hoặc `Comparable<?>`?

`Comparable` **nhận một đối tượng đầu vào** trong `compareTo`. Vì vậy, wildcard ở đây phù hợp với quy tắc **PECS**: *Producer Extends, Consumer Super*.

- `Comparable<? super T>`: kiểu so sánh có thể **tiêu thụ** một đối tượng `T`; dùng được `left.compareTo(right)` khi cả hai là `T`.
- `Comparable<? extends T>`: phương thức `compareTo` yêu cầu một *kiểu con chưa biết* của `T`. Ta không có cơ sở để đưa mọi `T` vào đó; điều kiện này không đáp ứng nhu cầu so sánh hai giá trị `T`.
- `Comparable<?>`: biết có khả năng so sánh nhưng chưa biết kiểu đối số, nên cũng không đủ để truyền tùy ý một `T` vào `compareTo`.

PECS là mẹo nhớ vị trí wildcard, còn cơ sở chính xác vẫn là **hướng gán được của đối số phương thức**. Dấu `?` không làm Java tự biến một phép so sánh không tương thích thành tương thích.

## 7. Thư viện chuẩn Java áp dụng cách này

Hai API quen thuộc có giới hạn cùng tinh thần:

```java
// Chữ ký rút gọn để tập trung vào giới hạn kiểu:
static <T extends Comparable<? super T>> void sort(List<T> list);

static <T extends Comparable<? super T>> T max(Collection<? extends T> items);
```

Đây là **chữ ký giải thích**, không phải đoạn mã để khai báo thay thế `Collections`. Trong JDK, `Collections.sort` dùng giới hạn `Comparable<? super T>`; chữ ký thực tế của `Collections.max` còn chứa giới hạn giao `Object & Comparable<? super T>` vì yêu cầu tương thích nhị phân lịch sử.

Điểm mấu chốt: API tìm cực trị và sắp xếp theo natural ordering nên hoạt động với cả kiểu tự triển khai `Comparable<T>` lẫn kiểu con thừa kế `Comparable<Parent>` hợp lệ. `? super T` giúp thuật toán linh hoạt mà vẫn được kiểm tra kiểu khi biên dịch.

## 8. Khi nào nên dùng `Comparator<? super T>` thay thế?

`Comparable` dành cho **thứ tự tự nhiên được định nghĩa ngay trong lớp**. Nếu cần nhiều quy tắc sắp xếp, không thể sửa lớp, hoặc một lớp không có thứ tự tự nhiên, hãy truyền một `Comparator` riêng:

```java
// Đoạn minh họa: giả sử có List<Student> students
students.sort(java.util.Comparator.comparing(Object::toString));
```

Đoạn này minh họa việc chọn **một tiêu chí sắp xếp khác** mà không sửa `compareTo`; nó chỉ là snippet bổ sung cho chương trình ở mục 3 (với danh sách tạo từ `List.of` là bất biến thì cần dùng bản sao có thể sửa, ví dụ `new java.util.ArrayList<>(students)`, trước khi gọi `sort`).

Về kiểu, một thuật toán nhận comparator thường khai báo `Comparator<? super T>` vì comparator cũng **nhận đối tượng `T` để so sánh**. Nhưng `Comparable<? super T>` trong giới hạn đệ quy vẫn là lựa chọn tự nhiên khi API muốn dùng chính cách so sánh mà kiểu phần tử cung cấp.

## 9. Lưu ý khi áp dụng

1. **Không phải lớp nào cũng hợp lệ**: một kiểu không triển khai `Comparable` tương thích vẫn bị trình biên dịch loại bỏ. `Comparable<String>` cũng không giúp một kiểu không liên quan tới `String` thỏa `Comparable<? super T>`.
2. **Không tự sinh thứ tự cho lớp con**: `? super T` chỉ thừa nhận cách so sánh đã tồn tại hoặc kế thừa; logic trong `compareTo` của lớp cha vẫn quyết định ý nghĩa thứ tự.
3. **Tuân thủ hợp đồng `compareTo`**: quan hệ thứ tự nên có tính nhất quán, bắc cầu và phản đối xứng về dấu. Tính nhất quán giữa `compareTo(...) == 0` và `equals` rất nên được duy trì, đặc biệt với `TreeSet`/`TreeMap`; nếu không, cần hiểu rõ hệ quả.
4. **Chú ý `null` và danh sách rỗng**: giới hạn generic không tự xử lý các trường hợp này. Ví dụ `maxOf` chủ động báo lỗi với danh sách rỗng; `List.of` không chứa `null`.
5. **Đừng viết raw type** `Comparable` để né điều kiện generic: raw type làm giảm kiểm tra kiểu và có thể đẩy lỗi sang lúc chạy.

## 10. Ghi nhớ bằng một câu hỏi

Khi xây dựng hàm `max`, hãy tự hỏi: “Nếu một `Student` đã biết so sánh với `Person`, nó có thể so sánh với một `Student` khác không?” **Có**, vì `Student` là `Person`. Giới hạn `<T extends Comparable<? super T>>` cho phép diễn đạt chính xác điều đó và giữ kết quả ở kiểu `T`.

**Quy tắc thực hành:** với thuật toán tổng quát dựa vào natural ordering của các phần tử `T`, ưu tiên `T extends Comparable<? super T>`; chỉ đòi `Comparable<T>` khi chính hợp đồng API thực sự yêu cầu một triển khai so sánh đúng kiểu `T`.