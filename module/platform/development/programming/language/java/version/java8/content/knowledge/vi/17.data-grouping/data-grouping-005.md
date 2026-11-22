# Collectors.partitioningBy và hai nhánh boolean trong Java Stream

## 1. Bài toán: phân dữ liệu theo một điều kiện đúng/sai

Trong một pipeline Stream, nhiều bài toán yêu cầu **chia toàn bộ phần tử thành hai nhóm**: đạt/không đạt, hợp lệ/không hợp lệ, đang hoạt động/không hoạt động, số chẵn/số lẻ. Từ Java 8 đến các JDK hiện hành, `Collectors.partitioningBy` là collector tiêu chuẩn cho trường hợp này.

Ví dụ, với các điểm số `[8, 5, 9, 4, 6]` và điều kiện `score >= 6`, ta cần:

- Nhánh **`true`**: `[8, 9, 6]` — các phần tử thỏa điều kiện.
- Nhánh **`false`**: `[5, 4]` — các phần tử không thỏa điều kiện.

`partitioningBy` dùng một **`Predicate<T>`**, tức hàm nhận một phần tử `T` và trả về `boolean`. Khi gọi `stream.collect(...)`, Stream duyệt dữ liệu, đánh giá điều kiện và gom phần tử vào nhánh tương ứng.

~~~java
Map<Boolean, List<Integer>> parts = scores.stream()
        .collect(Collectors.partitioningBy(score -> score >= 6));

List<Integer> passed = parts.get(true);
List<Integer> failed = parts.get(false);
~~~

Đoạn trên là **mã minh họa**, giả định `scores` là `List<Integer>` và đã import `Map`, `List`, `Collectors`. Cả hai danh sách được tạo ra trong **một lần collect**. Với nguồn có encounter order như `List.stream()`, thứ tự các phần tử bên trong mỗi `List` được giữ theo thứ tự xuất hiện của nguồn.

**Không được hiểu nhầm:** `true`/`false` là kết quả của predicate, không phải nhãn có sẵn của dữ liệu. Nếu predicate là `score < 6` thì ý nghĩa hai nhánh sẽ **đảo ngược**.

## 2. Hai overload và kiểu trả về

Trong `java.util.stream.Collectors` có hai overload áp dụng cho chủ đề này:

~~~java
// 1. Không truyền downstream:
static <T> Collector<T, ?, Map<Boolean, List<T>>>
    partitioningBy(Predicate<? super T> predicate)

// 2. Có downstream để giảm/gom riêng từng nhánh:
static <T, D, A> Collector<T, ?, Map<Boolean, D>>
    partitioningBy(
        Predicate<? super T> predicate,
        Collector<? super T, A, D> downstream)
~~~

Đây là **khai báo API minh họa**, không phải hai phương thức độc lập có thể dán vào một lớp để chạy. Hai overload đều có từ Java 8 và tiếp tục được hỗ trợ trong Java hiện đại.

| Thành phần | Vai trò |
| --- | --- |
| `Predicate<? super T>` | Phân loại mỗi phần tử vào nhánh `true` hoặc `false`. |
| `Map<Boolean, List<T>>` | Kết quả của overload một tham số: mỗi nhánh chứa một danh sách phần tử gốc. |
| `Collector<? super T, A, D> downstream` | Phép tích lũy riêng trên các phần tử của từng nhánh: đếm, tính tổng, lấy tên, tìm max, v.v. |
| `Map<Boolean, D>` | Kết quả của overload hai tham số: mỗi nhánh mang giá trị `D` do downstream tạo, không nhất thiết là `List`. |
| `collect(...)` | Terminal operation kích hoạt việc duyệt nguồn và thực hiện phép phân nhóm. |

Giả sử `Stream<Student>` với điều kiện `Student::isPassed`:

~~~java
// Lấy các Student thuộc từng nhánh.
Map<Boolean, List<Student>> byStatus = students.stream()
        .collect(Collectors.partitioningBy(Student::isPassed));

// Đếm số Student của từng nhánh.
Map<Boolean, Long> countByStatus = students.stream()
        .collect(Collectors.partitioningBy(
                Student::isPassed,
                Collectors.counting()));
~~~

Hai phép `collect` ở đây dùng **hai stream mới** được tạo riêng từ collection `students`. Không được tái sử dụng cùng một đối tượng `Stream` sau khi đã có terminal operation.

## 3. Hợp đồng cốt lõi: luôn có cả hai khóa boolean

Đây là điểm khác biệt quan trọng nhất khi dùng `partitioningBy`:

**Map kết quả luôn có ánh xạ cho cả `Boolean.TRUE` và `Boolean.FALSE`**, kể cả khi nguồn trống hoặc khi mọi phần tử chỉ vào một nhánh. Hợp đồng này được ghi rõ trong Javadoc Java hiện hành.

| Nguồn/điều kiện | `result.get(true)` khi dùng overload mặc định | `result.get(false)` |
| --- | --- | --- |
| `[2, 3, 4]`, predicate `n % 2 == 0` | `[2, 4]` | `[3]` |
| `[2, 4]`, predicate `n % 2 == 0` | `[2, 4]` | `[]` |
| `[1, 3]`, predicate `n % 2 == 0` | `[]` | `[1, 3]` |
| Stream rỗng | `[]` | `[]` |

Bảng mô tả **giá trị danh sách**, không mô tả thứ tự duyệt các entry của `Map`. Để biết nhánh nào là nhánh nào, hãy truy cập bằng `get(true)` hoặc `get(false)`.

~~~java
Map<Boolean, List<Integer>> emptyParts =
        Stream.<Integer>empty()
                .collect(Collectors.partitioningBy(n -> n % 2 == 0));

System.out.println(emptyParts.containsKey(true));  // true
System.out.println(emptyParts.containsKey(false)); // true
System.out.println(emptyParts.get(true).isEmpty()); // true
System.out.println(emptyParts.get(false).isEmpty());// true
~~~

Đoạn này chỉ minh họa; đầy đủ import nằm ở chương trình chạy được trong mục 5.

**Hệ quả thực dụng:** Với collector mặc định, ta có thể truy cập `result.get(true)` và `result.get(false)` rồi duyệt hai danh sách mà **không cần tự bổ sung khóa bị thiếu**. Tuy nhiên, chỉ nên phụ thuộc vào hợp đồng hai khóa và kiểu `List`, không phụ thuộc lớp triển khai cụ thể của `Map`/`List`.

### 3.1. Nhánh trống khi có downstream

Với overload `partitioningBy(predicate, downstream)`, Map vẫn luôn có hai khóa, nhưng giá trị cho một nhánh trống **phụ thuộc downstream**. Javadoc hiện hành giải thích: đối với nhánh không có phần tử, giá trị được tạo bằng **supplier** của downstream, sau đó áp dụng **finisher** của downstream.

| Downstream | Giá trị khi nhánh không có phần tử |
| --- | --- |
| `Collectors.toList()` | Danh sách rỗng `[]` |
| `Collectors.toSet()` | Set rỗng; không được suy ra thứ tự in |
| `Collectors.counting()` | `0L` |
| `Collectors.summingInt(mapper)` | `0` |
| `Collectors.averagingInt(mapper)` | `0.0` |
| `Collectors.maxBy(comparator)` | `Optional.empty()` |
| `Collectors.mapping(mapper, toList())` | Danh sách rỗng |

Không nên khẳng định rằng **mọi** downstream đều có giá trị rỗng “hợp lệ” theo nghiệp vụ. Một custom downstream hoặc finisher như `Optional::get` có thể **ném exception khi nhánh trống**. Thiết kế downstream để xử lý trường hợp rỗng ngay từ đầu.

## 4. Vì sao hai nhánh phù hợp với predicate hơn việc lọc hai lần?

Có thể viết hai lần `filter` trên một collection:

~~~java
List<Integer> passed = scores.stream()
        .filter(n -> n >= 6)
        .collect(Collectors.toList());

List<Integer> failed = scores.stream()
        .filter(n -> n < 6)
        .collect(Collectors.toList());
~~~

Đây là **mã minh họa**. Cách trên tạo **hai pipeline**, mỗi pipeline duyệt dữ liệu từ đầu. Với nguồn lớn, phép kiểm tra tốn chi phí hoặc nguồn chỉ được duyệt một lần, sử dụng `partitioningBy` giúp diễn đạt rõ ý định **chia cùng một tập đầu vào thành hai nhánh bổ sung cho nhau trong một lần collect**:

~~~java
Map<Boolean, List<Integer>> parts = scores.stream()
        .collect(Collectors.partitioningBy(n -> n >= 6));
~~~

Khi phân nhánh, một phần tử đi vào **đúng một trong hai nhánh** dựa trên giá trị predicate tại thời điểm xử lý. Do đó, với dữ liệu đầu vào thông thường, nếu `trueCount` và `falseCount` là số phần tử hai danh sách thì `trueCount + falseCount` bằng tổng số phần tử được collect (kể cả các phần tử có giá trị bằng nhau).

`partitioningBy` **không loại trùng**, **không sắp xếp** và **không tự lọc bỏ** phần tử. Muốn loại trùng hay chuyển đổi dữ liệu, hãy áp dụng các thao tác phù hợp trước khi collect hoặc dùng downstream có chủ đích.

## 5. Chương trình Java hoàn chỉnh: phân nhóm, đếm, ánh xạ và nhánh trống

Lưu mã sau thành **PartitioningByDemo.java**. Chương trình sử dụng API Java 8, chạy được bằng JDK 17+ và không dựa vào thứ tự lặp của `Map`.

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class PartitioningByDemo {
    static final class Student {
        private final String name;
        private final int score;

        Student(String name, int score) {
            this.name = name;
            this.score = score;
        }

        String getName() {
            return name;
        }

        int getScore() {
            return score;
        }

        boolean isPassed() {
            return score >= 6;
        }
    }

    public static void main(String[] args) {
        List<Student> students = Arrays.asList(
                new Student("An", 8),
                new Student("Binh", 5),
                new Student("Chi", 9),
                new Student("Dung", 4),
                new Student("Em", 6));

        // Mặc định: hai danh sách giữ các Student gốc.
        Map<Boolean, List<Student>> byPass = students.stream()
                .collect(Collectors.partitioningBy(Student::isPassed));

        List<String> passing = byPass.get(true).stream()
                .map(Student::getName)
                .collect(Collectors.toList());
        List<String> failing = byPass.get(false).stream()
                .map(Student::getName)
                .collect(Collectors.toList());

        System.out.println("pass names = " + passing);
        System.out.println("fail names = " + failing);

        // Downstream đếm phần tử của từng nhánh.
        Map<Boolean, Long> counts = students.stream()
                .collect(Collectors.partitioningBy(
                        Student::isPassed,
                        Collectors.counting()));
        System.out.println("pass count = " + counts.get(true)
                + ", fail count = " + counts.get(false));

        // Downstream chuyển Student thành tên ở từng nhánh.
        Map<Boolean, List<String>> names = students.stream()
                .collect(Collectors.partitioningBy(
                        Student::isPassed,
                        Collectors.mapping(
                                Student::getName,
                                Collectors.toList())));
        System.out.println("mapped pass = " + names.get(true));
        System.out.println("mapped fail = " + names.get(false));

        // Downstream thống kê trung bình riêng từng nhánh.
        Map<Boolean, Double> averages = students.stream()
                .collect(Collectors.partitioningBy(
                        Student::isPassed,
                        Collectors.averagingInt(Student::getScore)));
        System.out.println("pass average = "
                + String.format(Locale.ROOT, "%.2f", averages.get(true)));
        System.out.println("fail average = "
                + String.format(Locale.ROOT, "%.2f", averages.get(false)));

        // Downstream chọn người có điểm cao nhất trong mỗi nhánh.
        Map<Boolean, Optional<Student>> best = students.stream()
                .collect(Collectors.partitioningBy(
                        Student::isPassed,
                        Collectors.maxBy(
                                Comparator.comparingInt(Student::getScore))));
        System.out.println("best pass = "
                + best.get(true).map(Student::getName).orElse("none"));
        System.out.println("best fail = "
                + best.get(false).map(Student::getName).orElse("none"));

        // Cả hai khóa luôn tồn tại dù nguồn hoàn toàn rỗng.
        Map<Boolean, List<Integer>> empty = Stream.<Integer>empty()
                .collect(Collectors.partitioningBy(n -> n % 2 == 0));
        System.out.println("empty keys = " + empty.keySet().size()
                + "; true = " + empty.get(true).size()
                + "; false = " + empty.get(false).size());

        // Một nhánh rỗng với downstream counting() có giá trị 0L.
        Map<Boolean, Long> allPassed = Arrays.asList(7, 8).stream()
                .collect(Collectors.partitioningBy(
                        n -> n >= 6,
                        Collectors.counting()));
        System.out.println("onlyPassed count = " + allPassed.get(true)
                + ", noPassed count = " + allPassed.get(false));
    }
}
~~~

Lệnh biên dịch và chạy bằng JDK 17+ (kiểm tra khả năng tương thích với Java 8):

~~~bash
javac --release 8 PartitioningByDemo.java
java PartitioningByDemo
~~~

**Stdout chính xác:**

~~~text
pass names = [An, Chi, Em]
fail names = [Binh, Dung]
pass count = 3, fail count = 2
mapped pass = [An, Chi, Em]
mapped fail = [Binh, Dung]
pass average = 7.67
fail average = 4.50
best pass = Chi
best fail = Binh
empty keys = 2; true = 0; false = 0
onlyPassed count = 2, noPassed count = 0
~~~

Khi đọc kết quả, chú ý:

1. Nguồn là `List` có encounter order, nên thứ tự tên trong mỗi danh sách phản ánh thứ tự đầu vào. Đoạn code **không in `Map` nguyên khối**, vì thứ tự duyệt khóa của `Map` không được hứa.
2. `passing` và `failing` là hai danh sách được tạo từ kết quả phân nhóm; chúng chỉ chứa tên để in, trong khi `byPass` giữ chính các đối tượng `Student`.
3. `counting()` tạo `Long`; đếm `3L` và `2L`, in thành `3` và `2`.
4. `mapping(Student::getName, toList())` tạo trực tiếp `Map<Boolean, List<String>>`. Khi chỉ cần tên, có thể tránh bước duyệt lại các danh sách `Student`.
5. `averagingInt` cho kết quả `Double` và `String.format(Locale.ROOT, "%.2f", ...)` cố định dấu thập phân là dấu chấm trong output.
6. `maxBy` trả `Optional<Student>` cho cả hai nhánh; nếu một nhánh rỗng, `Optional.empty()` là trường hợp cần xử lý, ví dụ bằng `orElse`.
7. Nguồn rỗng vẫn tạo Map với đúng hai khóa và hai danh sách rỗng. Trường hợp chỉ có dữ liệu đạt, nhánh không đạt có giá trị `0L` khi dùng `counting()`.

## 6. So sánh partitioningBy với groupingBy

Cả hai đều phân nhóm dữ liệu nhưng có mục đích và **hợp đồng về khóa** khác nhau.

| Tiêu chí | `partitioningBy(predicate)` | `groupingBy(classifier)` |
| --- | --- | --- |
| Hàm nhận | `Predicate<T>` → `boolean` | `Function<T, K>` → khóa `K` |
| Loại nhánh | **Chính xác hai nhánh logic:** `true`/`false` | Một hoặc nhiều nhóm tùy kết quả classifier |
| Khi một nhánh không có phần tử | **Vẫn có khóa** với danh sách rỗng | **Không tạo khóa** nếu không phần tử nào được phân vào khóa đó |
| Khi toàn bộ nguồn rỗng | Map có cả hai khóa boolean | Map không có nhóm nào |
| Kiểu thường gặp | `Map<Boolean, List<T>>` | `Map<K, List<T>>` |
| Khi nên dùng | Một điều kiện đúng/sai, cần đọc rõ cả hai nhánh | Phân theo nhiều giá trị như phòng ban, trạng thái hoặc loại sản phẩm |

Ví dụ khác biệt chính xác về nhánh rỗng:

~~~java
// Đoạn minh họa: chỉ có số chẵn.
List<Integer> values = Arrays.asList(2, 4);

Map<Boolean, List<Integer>> partitioned = values.stream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));

Map<Boolean, List<Integer>> grouped = values.stream()
        .collect(Collectors.groupingBy(n -> n % 2 == 0));

// partitioned.get(false) là danh sách rỗng.
// grouped.containsKey(false) là false; grouped.get(false) là null.
~~~

Vì `groupingBy` tạo khóa khi classifier thực sự trả về khóa đó, không nên coi `groupingBy(n -> predicate)` là thay thế hoàn toàn tương đương với `partitioningBy(predicate)`. Nếu nghiệp vụ có **ba trạng thái** như `PENDING`, `APPROVED`, `REJECTED`, dùng `groupingBy` theo status sẽ đúng mô hình hơn; ép ba trạng thái vào boolean có thể làm mất ý nghĩa.

### 6.1. Thứ tự phần tử và thứ tự khóa không phải một

Trong pipeline có **encounter order** và downstream `toList()`, các phần tử trong **mỗi danh sách** giữ thứ tự xuất hiện tương đối của nhánh. Ví dụ đầu vào `[8, 5, 9, 4, 6]` cho danh sách `[8, 9, 6]` ở nhánh đúng và `[5, 4]` ở nhánh sai.

Điều này **không** có nghĩa Map sẽ duyệt `false` trước `true` hoặc ngược lại. Không viết logic kiểu “entry đầu tiên là nhóm đạt”. Nếu cần thứ tự hiển thị ổn định, hãy đặt nhãn và truy cập hai khóa rõ ràng:

~~~java
System.out.println("Đạt: " + parts.get(true));
System.out.println("Chưa đạt: " + parts.get(false));
~~~

Đoạn trên minh họa giả định biến `parts` đã được tạo. Nếu nguồn Stream **unordered**, việc dựa vào thứ tự phần tử trong List cũng không có cơ sở.

## 7. Các downstream hữu ích và nguyên tắc chọn

Downstream chạy **riêng cho mỗi nhánh**. Chọn nó theo kiểu dữ liệu đầu ra mà bài toán thật sự cần, thay vì luôn giữ toàn bộ phần tử trong `List` rồi mới xử lý lại.

| Nhu cầu | Collector | Kết quả |
| --- | --- | --- |
| Lấy toàn bộ đối tượng từng nhánh | `partitioningBy(p)` | `Map<Boolean, List<T>>` |
| Đếm từng nhánh | `partitioningBy(p, counting())` | `Map<Boolean, Long>` |
| Tổng doanh số mỗi nhánh | `partitioningBy(p, summingLong(Order::getAmount))` | `Map<Boolean, Long>` |
| Trung bình mỗi nhánh | `partitioningBy(p, averagingInt(Item::getScore))` | `Map<Boolean, Double>` |
| Chỉ lấy trường tên | `partitioningBy(p, mapping(User::getName, toList()))` | `Map<Boolean, List<String>>` |
| Loại giá trị trùng trong mỗi nhánh | `partitioningBy(p, mapping(User::getRole, toSet()))` | `Map<Boolean, Set<Role>>` |
| Lấy phần tử lớn nhất | `partitioningBy(p, maxBy(comparator))` | `Map<Boolean, Optional<T>>` |
| Thống kê min/max/sum/count/average của `int` | `partitioningBy(p, summarizingInt(mapper))` | `Map<Boolean, IntSummaryStatistics>` |

Các biểu thức ở bảng là **mẫu rút gọn**, giả định đã có kiểu miền `Order`/`Item`/`User`, biến `p` là predicate hợp lệ, `comparator` phù hợp và đã `import static java.util.stream.Collectors.*;`. Đây không phải những chương trình độc lập.

### 7.1. Cách đọc nhánh trống khi downstream không trả List

Không viết:

~~~java
Map<Boolean, Long> counts = numbers.stream()
        .collect(Collectors.partitioningBy(
                n -> n > 0, Collectors.counting()));

// Sai kiểu: counts.get(true).size()
~~~

`counts.get(true)` có kiểu `Long`, không có `size()`. Khi dùng `counting()`, kiểm tra bằng `counts.get(true)` hoặc so sánh với `0L`.

Tương tự, khi downstream là `maxBy`, dữ liệu mỗi nhánh là một `Optional<T>`; gọi `get()` trên `Optional.empty()` sẽ gây `NoSuchElementException`. Dùng `ifPresent`, `map`, `orElse` hoặc xử lý vắng mặt có chủ đích.

### 7.2. Downstream cũng có giới hạn hợp đồng

`Collectors.toList()` không hứa kết quả là `ArrayList` hay luôn sửa được; `Collectors.toSet()` không hứa thứ tự duyệt, lớp triển khai hay khả năng chỉnh sửa. Khi có downstream `toList()/toSet()` trong `partitioningBy`, các giới hạn này **vẫn còn nguyên**.

Nếu cần danh sách cụ thể có thể thêm/xóa, có thể yêu cầu collector rõ ràng:

~~~java
Map<Boolean, java.util.ArrayList<Integer>> parts = numbers.stream()
        .collect(Collectors.partitioningBy(
                n -> n % 2 == 0,
                Collectors.toCollection(java.util.ArrayList::new)));
~~~

Đây là **đoạn minh họa** với `numbers` kiểu `Collection<Integer>`. Nó cam kết mỗi nhánh là `ArrayList` theo loại downstream đã yêu cầu. Đừng dùng phép ép kiểu `(ArrayList<T>) result.get(true)` chỉ vì implementation quan sát được tại một bản JDK cụ thể.

## 8. Predicate chính xác, ổn định và xử lý null

### 8.1. Viết predicate theo đúng ý nghĩa nghiệp vụ

Xác định điều kiện một lần, có tên rõ ràng khi logic phức tạp:

~~~java
java.util.function.Predicate<Order> isOverdue =
        order -> !order.isPaid() && order.getDueDate().isBefore(today);

Map<Boolean, List<Order>> byOverdue = orders.stream()
        .collect(Collectors.partitioningBy(isOverdue));
~~~

Đoạn trên là **minh họa trong hệ thống có kiểu `Order`, `today` và `orders` phù hợp**. Nhánh `true` là các đơn vừa chưa thanh toán vừa quá hạn; nhánh `false` bao gồm **mọi trường hợp còn lại**, kể cả đơn đã thanh toán hoặc đơn chưa đến hạn. Nhánh `false` không nhất thiết chỉ gồm đơn “đang còn hạn”.

Nếu muốn ba trạng thái “đã trả / chưa trả và quá hạn / chưa trả và còn hạn”, hãy biểu diễn bằng enum và dùng `groupingBy`; một predicate boolean không thể giữ đủ ba trạng thái độc lập.

### 8.2. Null trong nguồn

`partitioningBy` không tự động loại phần tử `null`. Nếu Stream có `null` và predicate dereference phần tử, chẳng hạn `s -> s.length() > 3`, phép thu thập sẽ ném `NullPointerException`. Cần định nghĩa rõ ý nghĩa nghiệp vụ của null:

~~~java
// Cách 1: bỏ null trước khi phân nhóm.
Map<Boolean, List<String>> nonNullParts = values.stream()
        .filter(java.util.Objects::nonNull)
        .collect(Collectors.partitioningBy(s -> s.length() > 3));

// Cách 2: coi null là trường hợp không đạt điều kiện.
// Nhánh false sẽ chứa cả null.
Map<Boolean, List<String>> includingNull = values.stream()
        .collect(Collectors.partitioningBy(
                s -> s != null && s.length() > 3));
~~~

Hai ví dụ trên **không tương đương**: cách đầu giảm số phần tử cần phân, cách sau vẫn phân mọi phần tử vào một trong hai nhánh. Với nghiệp vụ cần phân biệt `null` như trạng thái thứ ba, một Map khóa boolean không đủ biểu diễn.

### 8.3. Predicate nên không có tác dụng phụ

Không dùng predicate để ghi log nghiệp vụ bắt buộc, tăng biến đếm ngoài, sửa nguồn hoặc phụ thuộc thứ tự thực thi. Khi chạy `parallelStream()`, việc đánh giá có thể xảy ra trên nhiều thread và không theo thứ tự quan sát mong đợi.

Một predicate thuần như `student -> student.getScore() >= 6` giúp kết quả có ý nghĩa và dễ kiểm thử. Nếu điểm số thay đổi trong khi Stream đang chạy, việc phân loại có thể trở nên không xác định hoặc vi phạm yêu cầu không can thiệp vào nguồn.

## 9. Đặc tính hiệu năng và hợp đồng collection trả về

### 9.1. Collect tiêu thụ dữ liệu

`partitioningBy` **không phải phép short-circuit**: để tạo ra hai nhóm đầy đủ, terminal `collect` thường phải đi qua toàn bộ phần tử còn lại của pipeline. Với stream vô hạn mà không có bước giới hạn hợp lý, collect sẽ không hoàn thành. Nếu chỉ cần biết “có phần tử nào đạt không”, dùng `anyMatch(predicate)` phù hợp hơn vì có thể dừng sớm.

Khi dùng overload mặc định, toàn bộ phần tử đầu ra được giữ trong hai danh sách, do đó bộ nhớ cần thiết tăng theo kích thước dữ liệu. Khi chỉ cần số lượng, `partitioningBy(predicate, counting())` tránh phải giữ danh sách đầy đủ; phép collect vẫn duyệt nguồn nhưng bộ nhớ tích lũy nhỏ hơn đáng kể.

### 9.2. Sequential, parallel và thread safety

`partitioningBy` dùng được với `stream().collect(...)` lẫn `parallelStream().collect(...)`. Stream framework có thể dùng bộ tích lũy cục bộ rồi kết hợp kết quả. Điều này **không có nghĩa** Map và List sau khi trả về an toàn cho nhiều thread cùng chỉnh sửa.

Theo Javadoc, **không có bảo đảm về**:

- Lớp `Map` hay `List` cụ thể được dùng làm kết quả.
- Khả năng sửa đổi các collection sau khi collect.
- Khả năng serialization.
- Thread safety của Map/List kết quả.

Nếu cần thay đổi hoặc chia sẻ kết quả, quyết định dựa trên hợp đồng cụ thể của collection hoặc tạo bản sao/biện pháp đồng bộ phù hợp. Không nên ép kết quả vào `HashMap`/`ArrayList` rồi coi đó là bảo đảm API.

### 9.3. Không phụ thuộc thứ tự duyệt của Map

Chương trình có thể thấy `{false=[...], true=[...]}` trên một JDK và nghĩ đó là thứ tự cố định. Hợp đồng chỉ hứa **có hai khóa**, không hứa thứ tự `entrySet()`, `keySet()` hay `toString()`. Khi xuất báo cáo, hiển thị hai nhóm bằng cách truy cập `get(false)` và `get(true)` theo thứ tự mong muốn.

### 9.4. Không coi boolean là mô hình cho mọi bài toán

Hai nhánh boolean phù hợp khi hai điều kiện bù nhau hoàn toàn. Nếu logic cần nhiều nhãn, thứ tự mức độ ưu tiên, trạng thái “không biết”, hoặc lý do không đạt, nên dùng kiểu dữ liệu mô tả trạng thái rồi `groupingBy`, thay vì chồng nhiều phân nhánh boolean gây mất thông tin.

## 10. Lỗi phổ biến và cách sửa

**Lỗi 1 — Tưởng một nhánh không có dữ liệu sẽ không xuất hiện.** Với `partitioningBy`, `containsKey(true)` và `containsKey(false)` luôn đúng. Với overload mặc định, nhánh không có phần tử là danh sách rỗng. Đừng dùng `null` để kiểm tra nhánh rỗng; dùng `isEmpty()`.

**Lỗi 2 — Nhầm `true` là “nhóm đạt” bất kể predicate.** Khóa `true` chỉ nghĩa là predicate trả `true`. Đặt tên rõ predicate và kiểm tra đầu vào biên; đảo dấu so sánh có thể đổi ý nghĩa hai nhánh.

**Lỗi 3 — Dùng `groupingBy` rồi phụ thuộc đủ hai khóa.** `groupingBy` chỉ tạo khóa có dữ liệu; khác biệt thể hiện rõ trên nguồn rỗng và nguồn chỉ có một loại. Chọn `partitioningBy` khi cần hợp đồng hai khóa.

**Lỗi 4 — Giả định thứ tự lặp của Map.** Không dựa vào `Map.toString()` hoặc vị trí entry; truy cập trực tiếp bằng Boolean key.

**Lỗi 5 — Tưởng `partitioningBy` tự loại trùng hoặc sắp xếp.** Nó chỉ chia theo predicate. Nếu cần loại trùng hoặc sort, thiết kế thao tác riêng và xét encounter order.

**Lỗi 6 — Quên kiểu của downstream.** Với `counting()` nhánh có kiểu `Long`, không phải `List`; với `maxBy` là `Optional<T>` và có thể rỗng; với `mapping(..., toSet())` là `Set` chứ không có index.

**Lỗi 7 — Không xử lý nhánh rỗng khi dùng finisher.** Downstream phải tạo được kết quả từ một nhánh không chứa phần tử. Các phép như `Optional::get` trên `Optional.empty()` sẽ ném lỗi; hãy xử lý thiếu dữ liệu bằng một kết quả có ý nghĩa.

**Lỗi 8 — Dùng boolean để che giấu trạng thái thứ ba.** Nhánh `false` gom mọi trường hợp không thỏa predicate. Khi có `UNKNOWN`/`PENDING` cần phân biệt, dùng một kiểu trạng thái nhiều giá trị.

**Lỗi 9 — Mong collect dừng sớm trên nguồn vô hạn.** `collect` cần đủ đầu ra của cả hai nhánh; giới hạn nguồn hợp lý hoặc dùng terminal short-circuit nếu chỉ cần một câu trả lời.

**Lỗi 10 — Sửa dữ liệu đầu vào hoặc cập nhật biến chia sẻ trong predicate.** Vi phạm nguyên tắc stateless/non-interfering, dễ phát sinh lỗi khi parallel. Để collector đảm nhiệm tích lũy.

## 11. Câu hỏi kiểm tra

**Câu 1.** `Stream.of(1, 2, 3, 4).collect(partitioningBy(n -> n % 2 == 0))` có những nhánh nào?

**Đáp án:** `true → [2, 4]`, `false → [1, 3]` nếu nguồn ordered như `Stream.of`. Map có cả hai Boolean key; không suy ra thứ tự hiển thị Map.

**Câu 2.** Với `Stream.of(2, 4)`, `partitioningBy(n -> n % 2 == 0)` trả `get(false)` là gì?

**Đáp án:** Danh sách rỗng `[]`, **không phải `null`**.

**Câu 3.** Với Stream rỗng, `partitioningBy(p, counting())` trả `get(true)` và `get(false)` là gì?

**Đáp án:** Cả hai bằng `0L`. Hai khóa đều tồn tại dù predicate không được áp dụng cho phần tử nào.

**Câu 4.** Vì sao `groupingBy(n -> n % 2 == 0)` không thay thế hoàn toàn `partitioningBy(n -> n % 2 == 0)`?

**Đáp án:** `groupingBy` không tạo khóa cho nhánh vắng dữ liệu; `partitioningBy` luôn có đủ hai khóa.

**Câu 5.** Khi cần `Map<Boolean, List<String>>` từ `Stream<Student>`, chọn collector nào?

**Đáp án:** `partitioningBy(Student::isPassed, mapping(Student::getName, toList()))` với các static import tương ứng. Downstream tạo trực tiếp danh sách tên cho mỗi nhánh.

**Câu 6.** Có thể dùng `parallelStream().collect(partitioningBy(p))` không, và kết quả có thread-safe để sửa đồng thời không?

**Đáp án:** Có thể dùng parallel stream. Nhưng Map/List trả về **không có bảo đảm thread-safe** cho việc sửa đồng thời.

**Câu 7.** `partitioningBy(p)` có phải cách nhanh nhất để chỉ biết có phần tử nào thỏa `p` không?

**Đáp án:** Thường không đúng mục đích. `anyMatch(p)` có thể dừng khi phát hiện một phần tử thỏa; `partitioningBy` phải gom đủ hai nhánh.

## 12. Ghi nhớ

- `partitioningBy(predicate)` tạo **`Map<Boolean, List<T>>`**, đưa mỗi phần tử vào nhánh `true` hoặc `false` theo kết quả predicate.
- **Cả hai Boolean key luôn tồn tại**, kể cả nguồn rỗng hoặc một nhánh không có dữ liệu.
- `partitioningBy(predicate, downstream)` tạo **`Map<Boolean, D>`**; nhánh rỗng nhận kết quả do downstream tạo từ trạng thái tích lũy rỗng.
- **`partitioningBy` khác `groupingBy`** chủ yếu ở loại điều kiện và cam kết về hai khóa, đặc biệt trên dữ liệu rỗng.
- Không dựa vào lớp triển khai, khả năng sửa đổi, serialization, thread safety hoặc thứ tự duyệt của Map; hãy truy cập `get(true)`/`get(false)`.
- Chọn downstream cho **dữ liệu thực sự cần giữ**: `counting` nếu chỉ cần đếm; `mapping` nếu chỉ cần trường; `maxBy` nếu chỉ cần phần tử lớn nhất.
- Predicate nên rõ nghĩa, không có tác dụng phụ và xử lý null/trạng thái chưa xác định theo hợp đồng nghiệp vụ.
- Tất cả ví dụ API cốt lõi trong bài đều có từ Java 8 và vẫn còn được sử dụng trong các JDK hiện hành.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Collectors, partitioningBy và downstream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html)
- [Oracle Java SE 26 — Collectors, hợp đồng hai khóa và nhánh rỗng](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java SE 26 — Stream, collect và encounter order](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 8 — Predicate](https://docs.oracle.com/javase/8/docs/api/java/util/function/Predicate.html)
