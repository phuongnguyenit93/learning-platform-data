# Tìm cực trị từng nhóm bằng minBy và maxBy

Khi xử lý dữ liệu theo nhóm, câu hỏi thường không chỉ là “mỗi nhóm có bao nhiêu phần tử?” mà còn là **“bản ghi nào nhỏ nhất/lớn nhất trong mỗi nhóm?”**. Ví dụ: nhân viên nhận lương cao nhất từng phòng ban, đơn hàng giá trị lớn nhất từng khách hàng, sản phẩm giá rẻ nhất từng danh mục hoặc giao dịch sớm nhất của mỗi tài khoản.

Trong module **JAVA_STREAM_API**, bài học thuộc chương **Collector nhiều tầng và tổng hợp**. Chúng ta xây dựng pipeline khai báo bằng `filter`, `map`, `collect`, rồi sử dụng **downstream collector** bên trong `Collectors.groupingBy`. Trọng tâm là `Collectors.minBy(comparator)` và `Collectors.maxBy(comparator)`: hai bộ thu thập tìm **phần tử cực trị của từng nhóm** mà không phải tạo một `List` của mọi phần tử trong mỗi nhóm.

Các điểm cần nắm: cách xây `Comparator`, xử lý `Optional`, trường hợp bằng nhau (*tie*), khác biệt giữa lọc trước và sau khi nhóm, ảnh hưởng của `parallelStream()`, và khi nào nên dùng `summarizingInt` hoặc `toMap` thay thế.

## 1. Từ cực trị toàn Stream đến cực trị từng nhóm

Với một Stream duy nhất, ta có terminal operation:

```java
Optional<Integer> smallest = Stream.of(8, 3, 9, 3)
    .min(Integer::compare);

Optional<Integer> largest = Stream.of(8, 3, 9, 3)
    .max(Integer::compare);

System.out.println(smallest.orElse(-1)); // 3
System.out.println(largest.orElse(-1));  // 9
```

Nhưng với yêu cầu “**mỗi phòng ban** có một nhân viên lương cao nhất”, `stream.max(...)` chỉ trả về **một người trên toàn bộ Stream**, không trả về một kết quả cho từng phòng ban.

Ta cần hai lớp xử lý:

1. **Phân loại theo khóa nhóm** bằng `groupingBy(keyMapper, downstream)`.
2. **Tìm cực trị riêng trong từng nhóm** bằng `minBy(comparator)` hoặc `maxBy(comparator)`.

Hình dung:

```text
Stream<Employee>
       |
       v
groupingBy(Employee::getDepartment, downstream)
       |
       +-- Engineering --> maxBy(bySalary) --> Optional<Employee>
       |
       +-- Sales       --> maxBy(bySalary) --> Optional<Employee>
       |
       +-- Support     --> maxBy(bySalary) --> Optional<Employee>
       |
       v
Map<String, Optional<Employee>>
```

Một `Map` là kết quả của `groupingBy`, còn `Optional<Employee>` là kết quả downstream của từng nhóm. `collect(...)` ở cuối là **terminal operation** kích hoạt pipeline lười.

## 2. Chữ ký và ý nghĩa các Collector

Về khái niệm, hai phương thức có dạng:

```java
Collector<T, ?, Optional<T>> minBy(Comparator<? super T> comparator);
Collector<T, ?, Optional<T>> maxBy(Comparator<? super T> comparator);
```

Đặt vào `groupingBy`:

```java
Map<K, Optional<T>> minPerGroup = stream.collect(
    Collectors.groupingBy(
        item -> keyOf(item),
        Collectors.minBy(comparator)
    )
);

Map<K, Optional<T>> maxPerGroup = stream.collect(
    Collectors.groupingBy(
        item -> keyOf(item),
        Collectors.maxBy(comparator)
    )
);
```

Trong đó `K` là kiểu khóa nhóm, `T` là kiểu phần tử Stream. `Comparator<? super T>` quyết định **nhỏ nhất** hay **lớn nhất** theo quy tắc nào. `Collectors.minBy/maxBy` là **collector**, không phải terminal operation; chúng chỉ thực thi khi được truyền vào `collect` (hoặc được bao bọc bởi collector khác).

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `groupingBy(Employee::getDepartment, ...)` | Xác định khóa của từng nhóm | `"Engineering"`, `"Sales"` |
| `Collectors.minBy(bySalary)` | Lấy phần tử nhỏ nhất theo comparator trong từng nhóm | Người lương thấp nhất |
| `Collectors.maxBy(bySalary)` | Lấy phần tử lớn nhất theo comparator trong từng nhóm | Người lương cao nhất |
| `Optional<Employee>` | Biểu diễn một người hoặc không có người | `Optional.empty()` trong trường hợp downstream không nhận phần tử |

Điểm rất quan trọng: `maxBy` trên `Employee` **trả về `Optional<Employee>`**, không tự chuyển thành số lương. Nếu chỉ cần mức lương cao nhất, xem phần **mapping** và **summarizingInt** ở các mục sau.

## 3. Ví dụ Java 8 đầy đủ: nhân viên cực trị theo phòng ban

Ví dụ dưới đây có thể biên dịch với Java 8. Để kết quả **không phụ thuộc vào việc hai người có cùng lương**, comparator dùng lương trước, rồi dùng mã nhân viên duy nhất để phá hòa.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public class ExtremumByGroupDemo {
    static final class Employee {
        private final String id;
        private final String department;
        private final String level;
        private final int salary;

        Employee(String id, String department, String level, int salary) {
            this.id = id;
            this.department = department;
            this.level = level;
            this.salary = salary;
        }

        String getId() {
            return id;
        }

        String getDepartment() {
            return department;
        }

        String getLevel() {
            return level;
        }

        int getSalary() {
            return salary;
        }
    }

    public static void main(String[] args) {
        List<Employee> staff = Arrays.asList(
            new Employee("E01", "Engineering", "Senior", 4200),
            new Employee("E02", "Engineering", "Senior", 5000),
            new Employee("E03", "Engineering", "Mid",    5000),
            new Employee("S01", "Sales",       "Mid",    3200),
            new Employee("S02", "Sales",       "Junior", 2800),
            new Employee("P01", "Support",     "Junior", 3000)
        );

        Comparator<Employee> bySalaryThenId =
            Comparator.comparingInt(Employee::getSalary)
                      .thenComparing(Employee::getId);

        Map<String, Optional<Employee>> highestByDepartment = staff.stream()
            .collect(Collectors.groupingBy(
                Employee::getDepartment,
                Collectors.maxBy(bySalaryThenId)
            ));

        Map<String, Optional<Employee>> lowestByDepartment = staff.stream()
            .collect(Collectors.groupingBy(
                Employee::getDepartment,
                Collectors.minBy(bySalaryThenId)
            ));

        System.out.println(
            highestByDepartment.get("Engineering")
                .map(Employee::getId).orElse("none")
        ); // E03

        System.out.println(
            lowestByDepartment.get("Sales")
                .map(Employee::getId).orElse("none")
        ); // S02

        System.out.println(
            highestByDepartment.get("Support")
                .map(Employee::getSalary).orElse(-1)
        ); // 3000
    }
}
```

Giải thích kết quả:

1. Nhóm Engineering có ba người. `E02` và `E03` đều có lương `5000`, lớn hơn `E01`. Với `thenComparing(Employee::getId)`, `E03` được chọn vì mã `E03` lớn hơn `E02` theo thứ tự chuỗi.
2. Nhóm Sales có mức lương `3200` và `2800`, nên `minBy` chọn `S02`.
3. Nhóm Support có duy nhất `P01`, do đó cả `minBy` và `maxBy` đều chọn `P01`.

**Đừng phụ thuộc vào thứ tự duyệt các khóa Map:** `groupingBy` mặc định không cam kết loại Map cụ thể hoặc thứ tự duyệt khóa. Ở ví dụ này ta lấy theo khóa bằng `get(...)` nên không có vấn đề.

Việc thu thập cực trị **không tạo một List các nhân viên riêng cho từng phòng**. Collector của mỗi nhóm chỉ cần giữ ứng viên cực trị, thay vì mọi phần tử đã đi qua.

## 4. Comparator quyết định cực trị theo tiêu chí nào

`minBy` và `maxBy` **không tự biết** trường nào là “nhỏ” hay “lớn”. Chúng tin vào kết quả từ `Comparator`:

```java
Comparator<Employee> bySalary =
    Comparator.comparingInt(Employee::getSalary);

Comparator<Employee> byId =
    Comparator.comparing(Employee::getId);

Comparator<Employee> bySalaryThenId =
    Comparator.comparingInt(Employee::getSalary)
              .thenComparing(Employee::getId);
```

Hợp đồng comparator:

- Số **âm**: đối số thứ nhất nhỏ hơn đối số thứ hai.
- Số **0**: hai đối tượng được xem như ngang nhau **theo tiêu chí comparator**.
- Số **dương**: đối số thứ nhất lớn hơn đối số thứ hai.

Vì vậy, `maxBy(bySalary)` chọn người có lương cao nhất; `minBy(bySalary)` chọn người có lương thấp nhất. Còn `maxBy(byId)` lại chọn người có ID lớn nhất — một bài toán hoàn toàn khác.

### Trường hợp hòa: định nghĩa chính sách một cách chủ động

Nếu chỉ dùng `bySalary`, `E02` và `E03` được comparator đánh giá ngang nhau, vì cả hai cùng lương `5000`. Khi ấy, kết quả có thể là **một trong các ứng viên cực trị ngang nhau**. Không nên xây nghiệp vụ dựa trên việc phần tử xuất hiện trước sẽ luôn được chọn, đặc biệt khi thay đổi thứ tự nguồn hoặc chạy song song.

Một comparator có tiêu chí phá hòa:

```java
Comparator<Employee> bySalaryThenId =
    Comparator.comparingInt(Employee::getSalary)
              .thenComparing(Employee::getId);
```

giúp chọn cực trị xác định **nếu ID duy nhất trong nhóm**. Nếu muốn ưu tiên **ID nhỏ nhất khi lương bằng nhau** mà vẫn dùng `maxBy` để chọn lương cao nhất, có thể đảo chiều riêng tiêu chí ID:

```java
Comparator<Employee> salaryThenSmallestId =
    Comparator.comparingInt(Employee::getSalary)
        .thenComparing(
            Employee::getId,
            Comparator.reverseOrder()
        );
```

Khi salary cao hơn sẽ thắng; nếu salary bằng nhau thì ID nhỏ hơn được xem là **lớn hơn theo comparator kết hợp**, và do đó được `maxBy` chọn. Hãy đặt tên comparator theo **quy tắc ưu tiên của nghiệp vụ**, không chỉ theo các trường nó đọc.

### Không đảo ngược nhầm minBy và maxBy

`Comparator.reverseOrder()` hoặc `comparator.reversed()` đảo nghĩa nhỏ/lớn:

```java
Comparator<Employee> bySalary =
    Comparator.comparingInt(Employee::getSalary);

// Hai cách này cùng chọn người có lương cao nhất:
Collectors.maxBy(bySalary);
Collectors.minBy(bySalary.reversed());
```

Viết `maxBy(bySalary)` thường trực tiếp hơn cho câu hỏi “ai có lương cao nhất”. Đừng đảo comparator vô tình rồi dùng tiếp `maxBy` vì lúc đó bạn có thể chọn **lương thấp nhất**.

## 5. Vì sao kết quả là Optional?

`Collectors.minBy/maxBy` sử dụng `Optional<T>` vì một quá trình tổng hợp có thể **không nhận phần tử nào**. Trên Stream rỗng:

```java
Optional<Integer> minimum = Stream.<Integer>empty()
    .collect(Collectors.minBy(Integer::compare));

System.out.println(minimum.isPresent()); // false
```

Tuy nhiên, trong `groupingBy(keyMapper, Collectors.maxBy(...))` **không có bước lọc downstream**, mỗi khóa được tạo từ **ít nhất một phần tử nguồn**. Vì vậy, mỗi nhóm xuất hiện thực tế trong Map đều có `Optional` chứa một phần tử (với điều kiện dữ liệu và comparator hợp lệ). Những khóa không có trong nguồn **không được tự tạo ra**.

Ví dụ:

```java
Map<String, Optional<Employee>> top = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.maxBy(bySalaryThenId)
    ));

Optional<Employee> sales = top.get("Sales"); // Có giá trị.
Optional<Employee> absent = top.get("Legal"); // null vì Map không có khóa.
```

Ở đây, `top.get("Legal")` trả về **`null`**, không phải `Optional.empty()`. Đừng gọi `top.get("Legal").orElse(...)` vì sẽ ném `NullPointerException`. Cách dùng an toàn cho một khóa có thể không tồn tại:

```java
Employee legalTop = top.getOrDefault(
    "Legal", Optional.empty()
).orElse(null);
// legalTop == null
```

Nếu muốn từ chối khóa không có kết quả, có thể kiểm tra `containsKey` hoặc dùng `Optional` với `orElseThrow` phù hợp. Không nên dùng `Optional.get()` mà không kiểm tra.

### Nhóm có khóa nhưng kết quả Optional.empty()

Từ Java 9, `Collectors.filtering(predicate, downstream)` cho phép **lọc trong từng nhóm**. Khi một khóa đã tồn tại nhưng **không có phần tử nào qua bộ lọc downstream**, `maxBy` sẽ cho `Optional.empty()` cho khóa ấy:

```java
// Java 9+
Map<String, Optional<Employee>> highEarners = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.filtering(
            employee -> employee.getSalary() >= 6000,
            Collectors.maxBy(bySalaryThenId)
        )
    ));

System.out.println(highEarners.containsKey("Sales")); // true
System.out.println(highEarners.get("Sales").isPresent()); // false
```

Ngược lại, `stream.filter(predicate).collect(groupingBy(...))` lọc **trước khi tạo nhóm**: phòng ban không có phần tử phù hợp sẽ **không có khóa trong Map**. Hai cách lọc mang ý nghĩa khác nhau.

## 6. Bỏ lớp Optional khi cần Map<K, T>

Khi nghiệp vụ khẳng định mỗi khóa được tạo chắc chắn có ít nhất một phần tử, có thể dùng `Collectors.collectingAndThen` để biến kết quả downstream:

```java
Map<String, Employee> topByDepartment = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.collectingAndThen(
            Collectors.maxBy(bySalaryThenId),
            opt -> opt.orElseThrow(IllegalStateException::new)
        )
    ));

System.out.println(
    topByDepartment.get("Engineering").getId()
); // E03
```

Lời gọi này có hai tầng downstream:

1. `maxBy` tổng hợp trong nhóm, tạo `Optional<Employee>`.
2. `collectingAndThen` gọi **finisher** để chuyển `Optional<Employee>` thành `Employee`.

Với `groupingBy` thông thường, các nhóm được tạo từ phần tử thực tế nên có ít nhất một phần tử. Nếu sau đó thêm `Collectors.filtering(...)` ở downstream (Java 9+), có thể có nhóm rỗng theo bộ lọc và `orElseThrow` sẽ ném ngoại lệ. Vì vậy, chỉ bỏ `Optional` khi **tính không rỗng được đảm bảo bởi thiết kế**.

Không nên lạm dụng `orElse(null)` để “dễ truy cập”; null làm mờ sự khác nhau giữa **khóa không tồn tại** và **khóa có nhưng không có ứng viên hợp lệ**.

## 7. Chỉ cần giá trị cực trị, không cần cả đối tượng?

Nếu chỉ quan tâm **mức lương cao nhất từng phòng**, `Map<String, Optional<Employee>>` có thể chứa nhiều thông tin hơn yêu cầu. Ta có thể dùng `Collectors.mapping` trước `maxBy`:

```java
Map<String, Optional<Integer>> highestSalaryByDepartment =
    staff.stream().collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.mapping(
            Employee::getSalary,
            Collectors.maxBy(Integer::compare)
        )
    ));

System.out.println(
    highestSalaryByDepartment.get("Engineering").orElse(-1)
); // 5000
```

`mapping` biến từng `Employee` của nhóm thành `Integer`, sau đó `maxBy` tìm giá trị nguyên lớn nhất. Cấu trúc:

```text
groupingBy(phòng ban,
    mapping(lương,
        maxBy(so sánh số nguyên)
    )
)
```

Đây là một **collector nhiều tầng** đúng nghĩa: `groupingBy` nhận một downstream `mapping`, và `mapping` lại nhận `maxBy`.

### Muốn cả min, max, count và average?

Nếu chỉ cần **thống kê số lương**, không cần giữ nhân viên ứng viên, `Collectors.summarizingInt` có thể tính nhiều thống kê trong **một lượt duyệt**:

```java
Map<String, IntSummaryStatistics> stats = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.summarizingInt(Employee::getSalary)
    ));

IntSummaryStatistics engineering = stats.get("Engineering");
System.out.println(engineering.getCount());   // 3
System.out.println(engineering.getMin());     // 4200
System.out.println(engineering.getMax());     // 5000
System.out.println(engineering.getSum());     // 14200
System.out.println(engineering.getAverage()); // 4733.333...
```

`summarizingInt` không xác định nhân viên nào có lương cao nhất; nó chỉ tổng hợp các **giá trị số**. Ngoài ra, với `int` và dữ liệu lớn, cần quan tâm miền số và tràn khi tổng hợp. Chọn Collector dựa trên **kiểu kết quả cần trả về**, không chỉ dựa vào tên phương thức.

| Câu hỏi | Cách thu thập gợi ý | Kiểu giá trị của mỗi khóa |
| --- | --- | --- |
| Nhân viên lương cao nhất? | `maxBy(bySalaryThenId)` | `Optional<Employee>` |
| Nhân viên lương thấp nhất? | `minBy(bySalaryThenId)` | `Optional<Employee>` |
| Con số lương cao nhất? | `mapping(getSalary, maxBy(Integer::compare))` | `Optional<Integer>` |
| Min, max, count, sum, average? | `summarizingInt(getSalary)` | `IntSummaryStatistics` |
| Toàn bộ nhân viên từng phòng? | `groupingBy(getDepartment)` (downstream mặc định `toList`) | `List<Employee>` |

## 8. Phân nhóm nhiều cấp trước khi tìm cực trị

Một doanh nghiệp có thể cần tìm người lương cao nhất **trong mỗi cấp bậc của từng phòng ban**. Khi đó, lồng `groupingBy`:

```java
Map<String, Map<String, Optional<Employee>>> topByDepartmentAndLevel =
    staff.stream().collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.groupingBy(
            Employee::getLevel,
            Collectors.maxBy(bySalaryThenId)
        )
    ));

Employee topSeniorEngineer = topByDepartmentAndLevel
    .get("Engineering")
    .get("Senior")
    .orElseThrow(IllegalStateException::new);

System.out.println(topSeniorEngineer.getId()); // E02
```

Phân tích kiểu:

- `groupingBy(Employee::getDepartment, ...)` tạo khóa cấp một `String`.
- `groupingBy(Employee::getLevel, ...)` tạo khóa cấp hai `String` bên trong từng phòng.
- `maxBy(bySalaryThenId)` chọn `Employee` cực trị của từng tổ hợp **(phòng, cấp bậc)**.
- Kiểu kết quả là `Map<String, Map<String, Optional<Employee>>>`.

Các nhóm không có dữ liệu không tự xuất hiện. Khi truy cập một phòng hoặc cấp bậc **không tồn tại**, `Map.get(...)` có thể trả `null` trước khi tới `Optional`. Trong ứng dụng thật, nên kiểm tra sự tồn tại của từng khóa hoặc tạo hàm truy cập an toàn.

Nếu cần sắp các khóa nhóm theo thứ tự chữ cái, có thể dùng overload ba tham số của `groupingBy` với `TreeMap::new`:

```java
Map<String, Optional<Employee>> sortedDepartments = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        TreeMap::new,
        Collectors.maxBy(bySalaryThenId)
    ));
```

Nhà cung cấp Map quyết định cách lưu/trình bày **khóa nhóm**, không thay đổi tiêu chí so sánh lương để tìm người cực trị.

## 9. Khác biệt với groupingBy(toList) rồi tìm max

Một cách viết dễ nghĩ tới là **thu toàn bộ nhân viên vào List từng nhóm**, sau đó lại duyệt mỗi List để tìm cực trị:

```java
Map<String, List<Employee>> grouped = staff.stream()
    .collect(Collectors.groupingBy(Employee::getDepartment));

Map<String, Optional<Employee>> top = new HashMap<>();
for (Map.Entry<String, List<Employee>> entry : grouped.entrySet()) {
    top.put(
        entry.getKey(),
        entry.getValue().stream().max(bySalaryThenId)
    );
}
```

Cách này có thể đúng về kết quả, nhưng phải **giữ tất cả phần tử trong các List trung gian** rồi thực hiện lượt duyệt tiếp theo cho từng nhóm. Nếu chỉ cần một người cực trị mỗi nhóm, viết trực tiếp:

```java
Map<String, Optional<Employee>> top = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.maxBy(bySalaryThenId)
    ));
```

Phương án trực tiếp thường phù hợp hơn về ý nghĩa, bộ nhớ và số lượt xử lý:

| Phương án | Chi phí duyệt | Dữ liệu trung gian |
| --- | --- | --- |
| `groupingBy(toList)` rồi `list.stream().max(...)` | Gom nhóm, sau đó duyệt lại thành viên từng nhóm | Lưu toàn bộ phần tử trong các List |
| `groupingBy(maxBy(comparator))` | Tích lũy ứng viên cực trị ngay khi duyệt | Chủ yếu một ứng viên cho mỗi nhóm cùng cấu trúc Map |

Tổng số lần so sánh để tìm cực trị thường tăng tuyến tính theo số phần tử. `maxBy` không bắt buộc phải sắp xếp cả nhóm; **sắp xếp để lấy phần tử cuối** thường tốn công hơn khi chỉ cần giá trị lớn nhất.

## 10. So sánh với toMap có merge function

Cùng bài toán lương cao nhất từng phòng có thể biểu diễn bằng `Collectors.toMap`:

```java
Map<String, Employee> top = staff.stream()
    .collect(Collectors.toMap(
        Employee::getDepartment,
        employee -> employee,
        BinaryOperator.maxBy(bySalaryThenId)
    ));
```

Ở đây, mỗi `Employee` đóng góp cặp `department → employee`; khi khóa trùng, `BinaryOperator.maxBy` gộp hai ứng viên.

Sự khác nhau:

| Cách viết | Kiểu kết quả | Điểm nổi bật |
| --- | --- | --- |
| `groupingBy(key, Collectors.maxBy(cmp))` | `Map<K, Optional<T>>` | Diễn đạt rõ “tổng hợp trong từng nhóm”; thuận tiện ghép thêm downstream |
| `toMap(key, identityValue, BinaryOperator.maxBy(cmp))` | `Map<K, T>` | Nhận trực tiếp bản ghi, không có lớp `Optional` khi có khóa |
| `groupingBy(key, collectingAndThen(maxBy(cmp), ...))` | `Map<K, T>` | Vẫn theo mô hình downstream nhưng chuyển kết quả ở cuối mỗi nhóm |

Không nên lẫn lộn `Collectors.maxBy(cmp)` và `BinaryOperator.maxBy(cmp)`:

- `Collectors.maxBy` trả về **`Collector<T, ?, Optional<T>>`**, dùng bên trong `collect` và `groupingBy`.
- `BinaryOperator.maxBy` trả về **`BinaryOperator<T>`**, dùng làm hàm gộp khi khóa trùng trong `toMap` hoặc làm phép tích lũy khi phù hợp.

Chúng đều dùng comparator nhưng **không thay thế trực tiếp cho nhau** vì kiểu và vai trò trong API khác nhau.

## 11. Những ranh giới về dữ liệu và hiệu năng

### 11.1. Dữ liệu null và khóa null

Với `groupingBy`, khóa do classifier trả về **không được là null**. Nếu `Employee::getDepartment` có thể trả về null, cần xác thực, lọc hoặc gán một khóa thay thế có ý nghĩa, chẳng hạn `"UNASSIGNED"`:

```java
Map<String, Optional<Employee>> top = staff.stream()
    .filter(Objects::nonNull)
    .collect(Collectors.groupingBy(
        employee -> employee.getDepartment() == null
            ? "UNASSIGNED" : employee.getDepartment(),
        Collectors.maxBy(bySalaryThenId)
    ));
```

`minBy/maxBy` dùng comparator trên các phần tử nhóm. Comparator ví dụ đọc `getSalary()`, `getId()` và không được thiết kế cho phần tử `null`. Vì vậy, nếu nguồn có thể chứa null, cần lọc `Objects::nonNull` hoặc định nghĩa chính sách so sánh null rõ ràng trước khi thu thập.

### 11.2. Trường dữ liệu dùng để so sánh không nên thay đổi

Đừng sửa `salary` hoặc `id` của các đối tượng trong quá trình pipeline xử lý; các hàm `groupingBy` và `maxBy` cần hoạt động **không can thiệp vào nguồn** và **không phụ thuộc trạng thái bên ngoài đang thay đổi**. Trong ví dụ, đối tượng `Employee` là immutable về các trường được dùng, giúp kết quả dễ suy luận.

Nếu lương được lưu dưới dạng `double`, cần tính đến `NaN`, vô cực và `-0.0`. Dùng `Comparator.comparingDouble(...)` và xác định chính sách giá trị không hữu hạn trước khi chọn cực trị. Với tiền tệ, `BigDecimal` hoặc số nguyên biểu diễn đơn vị nhỏ nhất thường phù hợp hơn khi cần độ chính xác thập phân.

### 11.3. Chạy song song không tự bảo đảm nhanh hơn

`groupingBy` có thể chạy trong parallel stream:

```java
Map<String, Optional<Employee>> parallelTop = staff.parallelStream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.maxBy(bySalaryThenId)
    ));
```

Thư viện có thể tạo các Map từng phần, tính ứng viên cực trị ở mỗi phần rồi **gộp** các kết quả. Comparator nên thuần túy và nhất quán; phép chọn cực trị theo một thứ tự so sánh nhất quán có khả năng kết hợp các ứng viên. Khi có **hòa** mà comparator không phân định được, nguồn hoặc cách gộp khác nhau có thể khiến ứng viên được chọn khác; dùng khóa phá hòa nếu nghiệp vụ cần kết quả xác định.

`Collectors.groupingBy` không phải **concurrent collector**. Khi xử lý song song, việc gộp Map từng phần có thể tốn tài nguyên; số nhóm, mức phân bố phần tử, khả năng chia nguồn (`Spliterator`) và chi phí comparator đều ảnh hưởng hiệu năng. Có `Collectors.groupingByConcurrent` cho nhu cầu khác, nhưng nó có đặc tính unordered/concurrent; không nên thay vào một cách máy móc khi đang cần thứ tự đầu ra hoặc quy tắc hòa theo encounter order.

Để tối ưu thực tế, hãy đo với dữ liệu đại diện. Với danh sách nhỏ, `stream()` tuần tự thường đơn giản và có thể nhanh hơn `parallelStream()`.

### 11.4. Nguồn vô hạn và chi phí bộ nhớ

`groupingBy(..., maxBy(...))` thường chỉ giữ ứng viên của mỗi nhóm thay vì giữ toàn bộ nhóm, nhưng `collect` vẫn cần **tiêu thụ hết đầu ra của Stream** mới trả về Map hoàn chỉnh. Với Stream vô hạn không được giới hạn, terminal có thể không kết thúc.

Giải pháp phụ thuộc bài toán:

```java
Map<Integer, Optional<Integer>> topByRemainder =
    IntStream.iterate(1, n -> n + 1)
        .limit(100)
        .boxed()
        .collect(Collectors.groupingBy(
            n -> n % 3,
            Collectors.maxBy(Integer::compare)
        ));
```

Ở đây, `limit(100)` khiến nguồn đầu ra hữu hạn; cực trị được tìm **trong 100 số đầu tiên**, không phải trên dãy vô hạn nói chung. `limit` không thay thế timeout và cũng không cứu được pipeline khi bước trước nó không bao giờ cho đủ phần tử.

## 12. Các nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `stream.max(...)` để trả cực trị từng nhóm | Chỉ nhận một phần tử trên toàn Stream | `groupingBy(key, Collectors.maxBy(...))` |
| Nghĩ `maxBy` lấy lương lớn nhất nhưng trả `Integer` | Kiểu thực tế là `Optional<Employee>` nếu đầu vào là `Employee` | Dùng `mapping(getSalary, maxBy(...))` khi chỉ cần con số |
| Gọi `map.get("Legal").orElse(...)` khi nhóm không có khóa | `Map.get` trả `null` gây `NullPointerException` | Kiểm tra khóa hoặc `getOrDefault("Legal", Optional.empty())` |
| Giả định mọi `Optional` trong nhóm luôn có dữ liệu kể cả khi lọc downstream | `Collectors.filtering` có thể để lại nhóm với `Optional.empty()` | Xử lý trường hợp rỗng trước khi `get()` |
| Chỉ so sánh lương khi nhiều người bằng nhau và cần một kết quả xác định | Ứng viên được chọn có thể không đúng chính sách | Thêm tiêu chí phá hòa duy nhất |
| Dùng `sorted().findFirst()` bên trong từng nhóm chỉ để lấy cực trị | Có thể làm nhiều việc hơn mức cần thiết | Dùng `minBy/maxBy` với comparator phù hợp |
| Thu toàn bộ nhóm vào List rồi mới duyệt tìm max | Tăng bộ nhớ và lượt duyệt | Thu trực tiếp bằng downstream `maxBy` |
| Coi thứ tự Map mặc định là thứ tự nguồn | Báo cáo có thể xuất khóa không ổn định | Dùng `TreeMap` hoặc sắp xếp khi trình bày |
| Đồng nhất `Collectors.maxBy` với `BinaryOperator.maxBy` | Sai kiểu hoặc sai vị trí API | Phân biệt Collector và BinaryOperator |
| Cho rằng `parallelStream()` luôn nhanh hơn | Có thể tốn chi phí chia và gộp nhóm | Đo đạc; ưu tiên comparator thuần túy |

## 13. Bài tập tự kiểm tra có đáp án

### Bài 1 — Ai có lương lớn nhất từng nhóm?

Cho dữ liệu nhân viên của ví dụ đầy đủ, viết pipeline lấy **người lương cao nhất theo phòng ban**, phân xử bằng ID khi lương bằng nhau.

```java
Comparator<Employee> cmp =
    Comparator.comparingInt(Employee::getSalary)
              .thenComparing(Employee::getId);

Map<String, Optional<Employee>> winners = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.maxBy(cmp)
    ));
```

**Đáp án:** Engineering → `E03`, Sales → `S01`, Support → `P01`. Với lương bằng nhau, ID lớn hơn thắng theo comparator đã khai báo.

### Bài 2 — Truy vấn nhóm không tồn tại

Biểu thức `winners.get("Legal").orElse(null)` có an toàn không?

**Đáp án:** Không. Vì nhóm Legal không có trong nguồn, `Map.get("Legal")` trả `null`; gọi `orElse` trên null gây `NullPointerException`. Có thể dùng:

```java
Employee legal = winners.getOrDefault(
    "Legal", Optional.empty()
).orElse(null);
```

### Bài 3 — Chỉ cần số lương lớn nhất

Thu `Map<String, Optional<Integer>>` chứa mức lương cao nhất mỗi phòng:

```java
Map<String, Optional<Integer>> maximumSalary = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.mapping(
            Employee::getSalary,
            Collectors.maxBy(Integer::compare)
        )
    ));
```

**Đáp án:** Engineering → `5000`, Sales → `3200`, Support → `3000`. `mapping` chuyển đối tượng `Employee` thành `Integer` trước khi thu cực trị.

### Bài 4 — Nhóm theo hai cấp

Muốn tìm người lương thấp nhất **cho từng cấp bậc trong từng phòng ban**, cần cấu trúc collector nào?

```java
Map<String, Map<String, Optional<Employee>>> result = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.groupingBy(
            Employee::getLevel,
            Collectors.minBy(bySalaryThenId)
        )
    ));
```

**Đáp án:** Lồng hai `groupingBy`, đặt `minBy` làm downstream trong cùng. Kết quả có khóa hai cấp: phòng ban rồi cấp bậc.

### Bài 5 — Nhóm có thể rỗng sau lọc

Trong Java 9+, nếu dùng `groupingBy(department, filtering(salary >= 6000, maxBy(...)))` trên nguồn ví dụ, kết quả cho nhóm Sales là gì?

**Đáp án:** Map vẫn chứa khóa `"Sales"` nhưng giá trị là `Optional.empty()`, vì các nhân viên Sales đã làm nhóm tồn tại trước khi downstream filtering loại hết. Nếu lọc **trước** `groupingBy`, khóa Sales sẽ không xuất hiện.

### Bài 6 — Khi nào dùng summarizingInt?

Yêu cầu xuất **số lượng nhân viên, lương thấp nhất, cao nhất, trung bình** của mỗi phòng. Có nên gọi `minBy` và `maxBy` rồi tính thêm các số còn lại?

**Đáp án:** Nếu **không cần biết nhân viên cụ thể**, `Collectors.summarizingInt(Employee::getSalary)` trong `groupingBy` diễn đạt đầy đủ và có thể tổng hợp trong một lượt:

```java
Map<String, IntSummaryStatistics> stats = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.summarizingInt(Employee::getSalary)
    ));
```

Khi cần cả **đối tượng nhân viên đại diện**, `minBy/maxBy` mới trực tiếp đáp ứng yêu cầu ấy.

## Ghi nhớ

Để tìm cực trị **từng nhóm** trong **JAVA_STREAM_API**, dùng `Collectors.groupingBy(classifier, Collectors.minBy(comparator))` hoặc `maxBy(comparator)`. Mỗi khóa dẫn tới một `Optional<T>` chứa phần tử cực trị, không phải toàn bộ List thành viên. `Comparator` quyết định giá trị nào thắng; bổ sung **tiêu chí phá hòa** khi cần kết quả ổn định. Có thể kết hợp `mapping` để tìm cực trị của một trường, `collectingAndThen` để chuyển `Optional` sang kiểu khác, hoặc lồng `groupingBy` để tổng hợp nhiều cấp. Hãy phân biệt **khóa không tồn tại** với **Optional rỗng**, chọn giải pháp phù hợp cho dữ liệu null và tránh phụ thuộc vào thứ tự xử lý song song. Nếu chỉ cần số thống kê, `summarizingInt` có thể hợp lý hơn việc tìm các đối tượng cực trị riêng lẻ.
