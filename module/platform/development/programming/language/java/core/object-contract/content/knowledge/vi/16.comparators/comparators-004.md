# `Comparator.thenComparing()`: tạo thứ tự theo nhiều khóa trong Java

## 1. Bài toán và nguyên tắc thứ tự ưu tiên

Khi sắp xếp danh sách đối tượng, một trường thường không đủ để quyết định vị trí. Ví dụ, yêu cầu của hệ thống nhân sự có thể là:

1. Sắp xếp **phòng ban tăng dần**.
2. Trong cùng phòng ban, sắp xếp **cấp bậc giảm dần**.
3. Nếu cấp bậc bằng nhau, sắp xếp **tên tăng dần**.
4. Nếu vẫn bằng nhau, sắp xếp **mã nhân viên tăng dần** để có kết quả xác định.

Đây là thứ tự **nhiều khóa** (*multi-key sorting*), hay so sánh kiểu từ điển (*lexicographic ordering*): xét khóa đầu tiên trước; chỉ khi hai giá trị bằng nhau theo comparator đang dùng mới chuyển sang khóa kế tiếp.

Trong Java, `Comparator<T>` diễn tả quy tắc thứ tự của hai đối tượng `T`. Kết quả của `compare(a, b)` là:

- Số âm: `a` đứng trước `b`.
- Số không: `a` và `b` được xem là **tương đương theo thứ tự sắp xếp**.
- Số dương: `a` đứng sau `b`.

Giá trị trả về **không** bắt buộc là `-1`, `0` hoặc `1`; chỉ dấu âm/không/dương có ý nghĩa. Quan hệ “`compare(a, b) == 0`” không tự động có nghĩa “`a.equals(b)`”.

Phương thức `thenComparing()` ghép các comparator theo quy tắc đó, giúp code giữ nguyên **thứ tự ưu tiên khóa** mà không cần nhiều khối `if`.

## 2. Cơ chế của `thenComparing()`

`Comparator.comparing(keyExtractor)` tạo comparator dựa trên một khóa có thể so sánh tự nhiên (*natural order*) như `String` hoặc `LocalDate`. `thenComparing(nextComparator)` thêm một bộ so sánh dự phòng khi comparator trước trả về `0`.

Ví dụ:

```java
Comparator<Person> byLastThenFirst =
    Comparator.comparing(Person::lastName)
              .thenComparing(Person::firstName);
```

Đây là mảnh code minh họa; giả sử có lớp `Person` với hai getter `lastName()` và `firstName()` trả giá trị `String` khác `null`, cùng `import java.util.Comparator;`.

Khi so hai người:

1. `lastName` khác nhau → dùng ngay kết quả khóa họ, **không cần xét** tên.
2. `lastName` được comparator coi bằng nhau → xét `firstName`.
3. Cả hai khóa đều tương đương → kết quả so sánh là `0`.

Diễn đạt gần với thuật toán (chỉ để hiểu cơ chế):

```java
// Logic tương đương về ý nghĩa, không phải mã bắt buộc viết tay.
int primary = byLastName.compare(a, b);
if (primary != 0) {
    return primary;
}
return byFirstName.compare(a, b);
```

Việc nối nhiều khóa tạo một comparator **mới**. `thenComparing()` không thay đổi comparator đã có, vì thế phải dùng giá trị được trả về khi xây chuỗi so sánh.

### 2.1. Các overload hay dùng

| Cách gọi | Dùng khi nào | Ví dụ ý nghĩa |
| --- | --- | --- |
| `thenComparing(Comparator<? super T>)` | Đã có comparator cho toàn đối tượng | Sau khóa chính, dùng comparator cấp bậc giảm dần |
| `thenComparing(Function<? super T, ? extends U>)` | Khóa phụ có kiểu hỗ trợ natural order | Sau họ, so tên |
| `thenComparing(Function, Comparator<? super U>)` | Khóa phụ cần quy tắc riêng: `null`, không phân biệt hoa/thường, đảo chiều | Sau đội, so tên theo `String.CASE_INSENSITIVE_ORDER` |
| `thenComparingInt(ToIntFunction<? super T>)` | Khóa số nguyên `int` | Sau tên, so ID dạng `int` |
| `thenComparingLong(ToLongFunction<? super T>)` | Khóa `long` | Sau trạng thái, so thời điểm dạng epoch |
| `thenComparingDouble(ToDoubleFunction<? super T>)` | Khóa `double` | Sau nhóm, so điểm số |

Các phương thức tiện ích cho primitive tránh boxing không cần thiết. Ở khóa đầu tiên cũng có `Comparator.comparingInt`, `comparingLong` và `comparingDouble`.

**Chú ý:** `Comparator.comparing(Person::name)` giả định khóa có `Comparable` và có chính sách cho `null` phù hợp. Nếu khóa có thể `null`, dùng comparator xử lý null cụ thể; không tự mặc định phép so sánh tự nhiên chấp nhận `null`.

## 3. Ví dụ Java 17 hoàn chỉnh: bốn khóa, hai hướng sắp xếp

Định nghĩa dữ liệu:

- `department`: String, A → Z.
- `level`: int, lớn hơn đứng trước.
- `name`: String, A → Z.
- `employeeId`: int, nhỏ hơn đứng trước.
- `salary`: long, thông tin phụ **không tham gia** thứ tự đang chọn.

Một kỹ thuật rõ nghĩa khi có khóa phụ giảm dần là truyền **comparator phụ đã đảo chiều** vào `thenComparing`, thay vì gọi `reversed()` lên toàn bộ chuỗi.

Lưu vào tệp **`MultiKeyComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class MultiKeyComparatorDemo {
    record Employee(String department, String name,
                    int level, long salary, int employeeId) {}

    public static void main(String[] args) {
        List<Employee> employees = new ArrayList<>(List.of(
            new Employee("Core", "An",   3, 100, 102),
            new Employee("Core", "Binh", 5, 125, 103),
            new Employee("Core", "An",   5, 130, 101),
            new Employee("Web",  "An",   4, 120, 104),
            new Employee("Core", "An",   5, 140, 105)
        ));

        Comparator<Employee> byDepartmentLevelNameId =
            Comparator.comparing(Employee::department)
                .thenComparing(
                    Comparator.comparingInt(Employee::level).reversed()
                )
                .thenComparing(Employee::name)
                .thenComparingInt(Employee::employeeId);

        employees.sort(byDepartmentLevelNameId);

        for (Employee employee : employees) {
            System.out.printf("%s | %d | %s | %d%n",
                employee.department(),
                employee.level(),
                employee.name(),
                employee.employeeId());
        }

        Employee original =
            new Employee("Core", "An", 5, 130, 101);
        Employee otherSalary =
            new Employee("Core", "An", 5, 999, 101);

        System.out.println("Comparator sees tie: "
            + (byDepartmentLevelNameId.compare(original, otherSalary) == 0));
        System.out.println("Record equals: " + original.equals(otherSalary));

        TreeSet<Employee> sortedSet =
            new TreeSet<>(byDepartmentLevelNameId);
        sortedSet.add(original);
        sortedSet.add(otherSalary);
        System.out.println("TreeSet size: " + sortedSet.size());
    }
}
```

Biên dịch và chạy bằng **JDK 17+** trong thư mục chứa tệp:

```bash
javac MultiKeyComparatorDemo.java
java MultiKeyComparatorDemo
```

Kết quả chuẩn:

```text
Core | 5 | An | 101
Core | 5 | An | 105
Core | 5 | Binh | 103
Core | 3 | An | 102
Web | 4 | An | 104
Comparator sees tie: true
Record equals: false
TreeSet size: 1
```

**Giải thích thứ tự:**

1. Các nhân viên `Core` đứng trước `Web` vì `department` tăng dần; cấp bậc của `Web` không được dùng để vượt lên trên khác phòng ban.
2. Trong `Core`, cấp `5` đứng trước cấp `3` do comparator `comparingInt(Employee::level).reversed()`.
3. Trong nhóm `Core` cấp `5`, tên `An` đứng trước `Binh`.
4. Hai nhân viên `An` ở cùng `Core`, cấp `5` được phân biệt bằng `employeeId`: `101` trước `105`.
5. `salary` không được đưa vào comparator. Hai record `original` và `otherSalary` chỉ khác salary nên comparator trả `0`, nhưng `record.equals` so **tất cả component** và cho `false`.
6. `TreeSet` xem hai phần tử tương đương theo comparator, vì vậy chỉ giữ một phần tử. Kết quả `TreeSet size: 1` là lời nhắc rằng **comparator còn quyết định tính trùng trong các tập hợp có thứ tự**, không chỉ thứ tự hiển thị.

Trong yêu cầu chỉ sắp xếp danh sách, salary có thể không thuộc quy tắc thứ tự. Nhưng nếu comparator được dùng làm định nghĩa khóa trong `TreeSet` hoặc `TreeMap`, bỏ qua trường quan trọng có thể vô tình gộp những đối tượng mà `equals()` coi khác nhau.

## 4. Viết khóa tăng dần và giảm dần cho đúng vị trí

### 4.1. Đảo chiều đúng **khóa phụ**

Để khóa `department` tăng dần nhưng `level` giảm dần:

```java
Comparator<Employee> order =
    Comparator.comparing(Employee::department)
        .thenComparing(
            Comparator.comparingInt(Employee::level).reversed()
        );
```

Đây là mảnh code minh họa dùng `Employee` từ chương trình hoàn chỉnh. Comparator phụ `comparingInt(...).reversed()` chỉ đảo thứ tự `level` trong nhóm có department bằng nhau.

### 4.2. `reversed()` ở cuối đảo **toàn bộ comparator**

Cần phân biệt:

```java
Comparator<Employee> allReversed =
    Comparator.comparing(Employee::department)
        .thenComparingInt(Employee::level)
        .reversed();
```

Ở đây `reversed()` được gọi trên kết quả **cả chuỗi** `department` rồi `level`, nên **cả department và level** cùng bị đảo. Nó không chỉ đảo trường gần nhất.

Nếu yêu cầu là “department tăng, level giảm”, cách viết ở 4.1 mới diễn tả đúng. Nếu yêu cầu là “cả hai khóa giảm”, `allReversed` là phù hợp.

### 4.3. Thay đổi thứ tự chuỗi sẽ đổi ưu tiên

Hai biểu thức này không tương đương:

```java
Comparator<Employee> byDepartmentThenLevel =
    Comparator.comparing(Employee::department)
        .thenComparingInt(Employee::level);

Comparator<Employee> byLevelThenDepartment =
    Comparator.comparingInt(Employee::level)
        .thenComparing(Employee::department);
```

Khóa **nằm trước** luôn có quyền ưu tiên cao hơn. Chuyển vị trí `thenComparing` không phải tái cấu trúc code vô hại mà là thay đổi luật nghiệp vụ.

### 4.4. Thêm khóa cuối để có kết quả quyết định

Nếu chỉ dùng `department`, `level` và `name`, các đối tượng có cùng ba khóa sẽ có `compare == 0`. `List.sort` và `Collections.sort` được Java quy định **sắp xếp ổn định** (*stable*): phần tử được xem bằng nhau theo comparator giữ thứ tự tương đối ban đầu. Tuy nhiên, nếu thứ tự đầu vào đến từ API, database hoặc HashSet không có thứ tự ổn định, kết quả có thể khác giữa các lần lấy dữ liệu.

Thêm một khóa ổn định, duy nhất theo miền như `employeeId` (nếu đúng là duy nhất trong phạm vi đang sắp xếp) giúp thứ tự có tính quyết định. Không tự thêm tiêu chí mà nghiệp vụ không chấp nhận, và đừng dùng `hashCode` hay `identityHashCode` làm khóa cuối để kỳ vọng duy nhất hoặc ổn định xuyên JVM.

## 5. Khóa `null`: đặt trước hay sau phải rõ ràng

Các extractor của `Comparator.comparing` có thể trả về `null`. Nếu comparator khóa không xử lý null, so sánh thường phát sinh `NullPointerException` khi gặp giá trị null.

Để giá trị `name == null` đứng **sau** tên không null:

```java
Comparator<Employee> byNameNullsLast =
    Comparator.comparing(
        Employee::name,
        Comparator.nullsLast(Comparator.naturalOrder())
    );
```

Để `department` tăng dần và `name` null đứng cuối **trong mỗi department**:

```java
Comparator<Employee> byDepartmentThenName =
    Comparator.comparing(Employee::department)
        .thenComparing(
            Employee::name,
            Comparator.nullsLast(Comparator.naturalOrder())
        );
```

Đây là mảnh code minh họa dùng `Employee` có `name()` trả String. Nếu bản thân `Employee` có thể `null` (không chỉ field bên trong null), có thể bọc **comparator toàn đối tượng** bằng `Comparator.nullsFirst(...)` hoặc `nullsLast(...)`. Cần phân biệt hai chính sách:

- `Comparator.comparing(Employee::name, nullsLast(...))` xử lý **khóa name null**.
- `Comparator.nullsLast(byDepartmentThenName)` xử lý **cả phần tử Employee null**.

Đặt `nullsLast` ở vị trí nào sẽ quyết định phạm vi áp dụng. Nếu đảo chiều một comparator đã `nullsLast` bằng `reversed()`, quy tắc null cũng bị đảo theo: `nullsLast(...).reversed()` đưa null lên đầu. Nếu mong muốn tên giảm dần nhưng null vẫn cuối, hãy viết:

```java
Comparator<String> descendingWithNullLast =
    Comparator.nullsLast(Comparator.reverseOrder());
```

Dùng comparator này cho **khóa String** phù hợp bằng overload `thenComparing(Employee::name, descendingWithNullLast)`.

Lưu ý: `Comparator.nullsFirst(null)` và `nullsLast(null)` vẫn chấp nhận comparator khóa `null` theo API Java và coi các giá trị không null là tương đương; trường hợp này chỉ hữu ích khi thật sự muốn bỏ qua thứ tự giữa các giá trị không null.

## 6. So chuỗi theo chính sách phù hợp

### 6.1. Phân biệt hay không phân biệt chữ hoa/thường?

`String` sắp xếp tự nhiên theo thứ tự từ điển dựa trên mã ký tự Unicode (UTF-16 code units), không tự động phù hợp thứ tự chữ cái tiếng Việt hay yêu cầu không phân biệt hoa/thường.

Với mã kỹ thuật hoặc tên cần so không phân biệt hoa/thường, bạn có thể dùng:

```java
Comparator<Employee> byDepartmentThenNameIgnoreCase =
    Comparator.comparing(Employee::department)
        .thenComparing(
            Employee::name,
            String.CASE_INSENSITIVE_ORDER
        );
```

Nhưng `CASE_INSENSITIVE_ORDER` không cam kết trùng với bộ quy tắc sắp xếp ngôn ngữ tự nhiên ở mọi locale. Nó cũng có thể trả `0` cho hai chuỗi khác nhau theo `String.equals`. Khi sắp xếp hiển thị, thêm một khóa phụ phân biệt chữ hoa/thường hoặc ID ổn định nếu cần tổng thứ tự cụ thể.

### 6.2. Tên tiếng Việt và `Collator`

Nếu giao diện cần thứ tự phù hợp với quy tắc ngôn ngữ, cân nhắc `java.text.Collator` và `Locale` thích hợp. Một ví dụ minh họa:

```java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

// Ví dụ minh họa, biến Employee từ chương trình mẫu.
Collator vietnamese = Collator.getInstance(
    Locale.forLanguageTag("vi-VN")
);
Comparator<Employee> byVietnameseName =
    Comparator.comparing(Employee::name, vietnamese);
```

`Collator` có cấu hình mức độ so sánh và hành vi phụ thuộc dữ liệu locale của môi trường Java. Nếu cần kết quả hoàn toàn cố định qua môi trường, phải xác định chính sách collation và phiên bản nguồn dữ liệu; đừng dự đoán một danh sách tên có dấu sẽ ra cùng thứ tự trong mọi cấu hình.

Các đối tượng `Collator` là mutable và không đảm bảo an toàn luồng khi cùng một instance bị dùng đồng thời mà có thay đổi. Khi cần chia sẻ giữa threads, hãy dùng phương án phù hợp như mỗi luồng có bản riêng hoặc kiểm soát truy cập, đồng thời không thay đổi quy tắc trong quá trình sắp xếp.

### 6.3. Giá trị khóa được chuẩn hóa

Nếu code dùng `String.toLowerCase()` làm khóa phụ, cần xác định locale và null policy. Với mã định danh kỹ thuật có quy tắc case-insensitive, dùng `Locale.ROOT` khi phù hợp sẽ rõ hơn việc dựa vào locale mặc định máy chạy. Tránh tạo nhiều biểu diễn chuẩn hóa khác nhau giữa sorting, `equals`, hash và tra cứu nghiệp vụ.

## 7. Khóa số, ngày giờ và các comparator chuyên biệt

Với số nguyên, sử dụng `comparingInt` / `thenComparingInt`; với `long`, sử dụng `comparingLong` / `thenComparingLong`; với `double`, sử dụng `comparingDouble` / `thenComparingDouble`. Các overload primitive tiết kiệm boxing và tránh tự trừ số để so sánh.

Ví dụ mã minh họa cho class `Event` có `LocalDateTime createdAt()` và `long sequence()`:

```java
Comparator<Event> newestFirstThenSequence =
    Comparator.comparing(Event::createdAt, Comparator.reverseOrder())
        .thenComparingLong(Event::sequence);
```

Đoạn này cần `java.util.Comparator` và class `Event` tương ứng; không phải chương trình biên dịch độc lập. Với ngày giờ, cần chọn đúng kiểu biểu diễn: `LocalDateTime` không mang múi giờ; `Instant` phù hợp hơn khi mục tiêu là thứ tự thời điểm tuyệt đối.

**Tránh cách viết dễ lỗi này:**

```java
// KHÔNG nên dùng cho int lớn: có thể tràn số.
Comparator<Employee> risky =
    (left, right) -> left.employeeId() - right.employeeId();
```

Nếu `left.employeeId() == Integer.MIN_VALUE` và `right.employeeId() == 1`, phép trừ tràn `int` có thể cho dấu sai, làm comparator vi phạm thứ tự. Dùng `Integer.compare(left.employeeId(), right.employeeId())` hoặc `Comparator.comparingInt(Employee::employeeId)`.

Với `double`, `Double.compare` và `comparingDouble` có quy tắc tổng thứ tự cho NaN và số 0 có dấu phù hợp API Java; nếu miền nghiệp vụ muốn xử lý NaN hoặc `-0.0` khác đi, phải nêu rõ chính sách và kiểm thử. Comparator nhiều khóa không tự xác định quy tắc đó.

## 8. `thenComparing()` và hợp đồng của `Comparator`

Ghép nhiều khóa có ý nghĩa như so từ điển: khóa chính quyết định trước, khóa phụ chỉ được dùng khi khóa chính trả `0`. Các comparator thành phần phải có quan hệ thứ tự hợp lệ, ổn định; việc nối chúng không khắc phục một comparator có chu kỳ, phụ thuộc random hoặc dữ liệu đang bị sửa.

Hai khái niệm cần tách trong ứng dụng:

- **Khóa sắp xếp:** chuỗi khóa `department → level → name → employeeId` có thể cho `compare(a,b)==0` khi hai đối tượng ngang nhau trên tất cả các khóa ấy.
- **Định danh dữ liệu:** `equals(a,b)` của một record còn có thể xét trường khác như `salary`. Trong ví dụ ở mục 3, hai record khác salary vẫn so bằng 0.

`List.sort` giữ cả hai bản ghi ngang hàng. `TreeSet` và `TreeMap` dùng kết quả bằng 0 làm quan hệ trùng khóa, vì vậy phải quyết định **khóa cuối cùng có cần phân biệt các bản ghi theo `equals` hay không**. Nếu entity định danh chỉ bằng ID nhưng comparator dùng trường hiển thị thay đổi trước ID, thêm ID ở cuối vẫn chưa chắc nhất quán với `equals`. Bài về quan hệ bằng nhau đi sâu vào hai chiều sai lệch này.
## 9. Hiệu năng và thời điểm trích xuất khóa

Comparator dạng chuỗi có thể đọc nhiều trường qua getter. `thenComparing` chỉ xét khóa phụ **khi khóa trước hòa** nên thứ tự trường cũng có thể ảnh hưởng số lần gọi extractor, nhưng hãy ưu tiên đúng yêu cầu nghiệp vụ trước.

Với extractor tốn kém, ví dụ chuẩn hóa tên, chuyển định dạng ngày, truy vấn nguồn ngoài hoặc tính toán dài, bộ sắp xếp có thể gọi chúng **nhiều lần**. Hướng thiết kế đáng cân nhắc là tiền tính khóa vào một đối tượng bất biến/record, sau đó sort theo các khóa đã tính. Tránh gọi API bên ngoài, thay đổi trạng thái hay phát sinh hiệu ứng phụ trong comparator.

`List.sort` và `Collections.sort` không chỉ gọi comparator đúng một lần trên mỗi phần tử. Comparator cần là **pure** theo nghĩa kết quả cho một cặp không đổi trong suốt lượt sort. Sửa các field được dùng làm khóa đồng thời với sort có thể gây lỗi, thậm chí vi phạm hợp đồng comparator.

`thenComparingInt`, `thenComparingLong`, `thenComparingDouble` phù hợp cho primitive keys; không phải mọi lambda đều cần tối ưu thủ công. Nếu bộ dữ liệu nhỏ, biểu thức comparator rõ ràng thường quan trọng hơn vài cấp phát nhỏ.

## 10. Những lỗi phổ biến

| Lỗi | Kết quả có thể xảy ra | Cách sửa |
| --- | --- | --- |
| Đặt `reversed()` ở cuối chuỗi, trong khi chỉ muốn đảo khóa cuối | Đảo toàn bộ khóa đã ghép | Đảo comparator của riêng khóa tương ứng rồi truyền vào `thenComparing` |
| Đổi thứ tự các lời gọi `thenComparing` | Đổi độ ưu tiên nghiệp vụ | Viết thứ tự khóa theo yêu cầu bằng lời trước |
| Bỏ khóa phân biệt cuối | Nhiều đối tượng có `compare == 0`; TreeSet gộp dữ liệu | Cân nhắc ID ổn định phù hợp miền |
| Dùng `String.CASE_INSENSITIVE_ORDER` rồi coi `compare == 0` tương đương `String.equals` | Hai chuỗi khác viết hoa/thường bị xem là một trong sorted set | Tách semantics hiển thị khỏi semantics nhận diện |
| Quên chính sách `null` | Ném `NullPointerException` trong sort | Sử dụng `nullsFirst/nullsLast` đúng phạm vi |
| Dùng subtraction `a.id() - b.id()` | Tràn số làm đảo dấu hoặc phá hợp đồng | Dùng `comparingInt` hay `Integer.compare` |
| Dùng comparator phụ trên mutable state | Kết quả không nhất quán giữa các lượt so | Dùng khóa ổn định trong quá trình sort và lưu collection có thứ tự |
| Dùng comparator có hiệu ứng phụ/random | Vi phạm bắc cầu hoặc tính nhất quán | Biến comparator thành phép so sánh xác định |
| Mặc định thứ tự tự nhiên của String là thứ tự ngôn ngữ Việt | Kết quả hiển thị không phù hợp | Chọn collation theo locale hoặc quy tắc ứng dụng |
| Giả định `thenComparing()` sửa comparator gốc tại chỗ | Bỏ quên comparator phụ vì không giữ giá trị trả về | Gán kết quả chuỗi vào một biến comparator mới |

## 11. Bài tập tự kiểm tra

**Câu 1.** Cho một lớp `Order` có `status()` trả String, `priority()` trả int. Yêu cầu: trạng thái tăng dần, trong cùng trạng thái ưu tiên lớn hơn trước. Viết comparator thế nào?

**Đáp án (mảnh code):**

```java
Comparator<Order> order =
    Comparator.comparing(Order::status)
        .thenComparing(
            Comparator.comparingInt(Order::priority).reversed()
        );
```

### Câu 2. Vì sao `compare(a, b) == 0` không đồng nghĩa `a.equals(b)`?

Vì comparator chỉ dựa vào tập khóa được chọn; `equals` có thể dựa vào tập trường khác. Ví dụ một record có salary khác nhưng comparator chỉ xét department, level, name và employeeId. Trong `TreeSet`, điều này còn ảnh hưởng đến số phần tử được lưu.

### Câu 3. `Comparator.comparing(Employee::department).thenComparingInt(Employee::level).reversed()` đảo khóa nào?

Đảo **cả chuỗi department rồi level**, vì `reversed()` được gọi trên comparator đã ghép. Nếu chỉ muốn level giảm, hãy đảo `Comparator.comparingInt(Employee::level)` bên trong `thenComparing(...)`.

### Câu 4. Nếu tên có thể `null` và cần null cuối nhưng tên còn lại giảm dần, dùng gì?

```java
Comparator<Employee> byName =
    Comparator.comparing(
        Employee::name,
        Comparator.nullsLast(Comparator.reverseOrder())
    );
```

Với comparator cho **khóa tên** như trên, null đứng sau các tên khác; những tên không null được sắp giảm dần.

### Câu 5. Một `TreeSet` dùng comparator chỉ dựa trên `age`. Hai object tuổi `20` nhưng ID khác nhau sẽ thế nào?

Cả hai có `compare == 0`, nên `TreeSet` coi chúng tương đương và chỉ giữ một phần tử. Nếu muốn lưu cả hai, comparator cần thêm khóa phân biệt thích hợp như ID.

### Câu 6. `thenComparingInt` khác `thenComparing(Person::age)` ở điểm thực tiễn nào?

`thenComparingInt` lấy primitive `int`, phù hợp getter trả `int` và tránh boxing sang `Integer` khi so sánh. Với các getter nullable `Integer`, không thể dùng trực tiếp một primitive extractor mà vẫn giữ được ý nghĩa `null`; cần comparator cho wrapper với chính sách null.

### Câu 7. Danh sách đã được sort theo khóa `team` rồi tiếp tục gọi sort theo `name`. Có luôn giống so nhiều khóa bằng `thenComparing` không?

Không. Vì `List.sort` ổn định, nếu trước tiên sort theo **khóa phụ `name`**, sau đó sort theo **khóa chính `team`**, kết quả có thể tương đương với thứ tự `team → name` khi các comparator hợp lệ và dữ liệu không đổi. Nhưng nếu sort theo khóa chính trước rồi sort theo khóa phụ sau, khóa phụ sẽ trở thành ưu tiên chính. Dùng `thenComparing` trực tiếp rõ ràng hơn và tránh phụ thuộc thứ tự nhiều lượt sort.

---

**Ghi nhớ:** `Comparator.comparing(...)` xác định **khóa ưu tiên cao nhất**; mỗi `thenComparing(...)` thêm **khóa dự phòng** chỉ khi các khóa đứng trước hòa. Chọn rõ tăng/giảm ở từng khóa, chính sách `null` và quy tắc so chuỗi. Khi dùng comparator cho `TreeSet`/`TreeMap`, đặc biệt chú ý ý nghĩa của `compare == 0` vì nó quyết định hai khóa có bị coi là trùng hay không.