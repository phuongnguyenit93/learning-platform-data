# `Collectors.filtering` trong phép thu theo nhóm

Từ Java 9, `Collectors.filtering` cho phép đặt một điều kiện lọc **bên trong một collector khác**. Nó là downstream collector: mỗi phần tử được chuyển đến collector bọc bên ngoài, được kiểm tra bằng `Predicate`, rồi chỉ phần tử thỏa mãn mới được chuyển tiếp cho collector downstream cuối cùng.

Điểm quan trọng nhất xuất hiện khi kết hợp với `Collectors.groupingBy`. Nếu lọc stream trước khi nhóm, một nhóm mà tất cả phần tử bị loại sẽ biến mất khỏi kết quả. Nếu đặt `Collectors.filtering` bên trong `groupingBy`, nhóm vẫn tồn tại khi nó có phần tử nguồn, nhưng tất cả phần tử của nhóm không thỏa điều kiện sẽ tạo ra kết quả thu rỗng, chẳng hạn danh sách rỗng hoặc số đếm bằng 0.

## 1. Cú pháp và vai trò

```java
Collectors.filtering(predicate, downstream)
```

- `predicate`: điều kiện quyết định phần tử có được chuyển tiếp hay không.
- `downstream`: collector tiếp tục tích lũy các phần tử đã vượt qua điều kiện, ví dụ `toList()`, `toSet()`, `counting()`, `mapping(...)` hoặc một collector khác.
- Kết quả: một `Collector` có thể lồng bên trong `groupingBy`, `partitioningBy` hoặc collector có hỗ trợ downstream khác.

`Collectors.filtering` không phải terminal operation và không tự tạo một collection. Nó định nghĩa cách một collector bên ngoài chuyển từng phần tử đến collector downstream. Việc thực thi diễn ra khi pipeline được kết thúc bằng `collect(...)`.

## 2. Vì sao cần filtering ở downstream?

Giả sử có danh sách nhân viên thuộc nhiều phòng ban. Ta muốn nhóm theo phòng ban và chỉ giữ nhân viên có lương từ 60.000 trở lên.

Dữ liệu đầu vào:

| Nhân viên | Phòng ban | Lương | Đạt điều kiện? |
| --- | --- | ---: | --- |
| An | Engineering | 90.000 | Có |
| Binh | Engineering | 50.000 | Không |
| Chi | Sales | 55.000 | Không |
| Dung | Sales | 48.000 | Không |
| Ha | Support | 65.000 | Có |

Phòng ban `Sales` có dữ liệu đầu vào, nhưng không có nhân viên nào đạt điều kiện. Có hai cách viết và chúng tạo ra kết quả khác nhau.

### Lọc stream trước khi nhóm

```java
Map<String, List<String>> result = employees.stream()
    .filter(employee -> employee.getSalary() >= 60000)
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        TreeMap::new,
        Collectors.mapping(Employee::getName, Collectors.toList())
    ));
```

Ở đây `filter` loại Binh, Chi và Dung khỏi stream trước khi `groupingBy` nhìn thấy chúng. Vì không còn nhân viên Sales nào đi vào collector nhóm, key `Sales` không được tạo ra.

Kết quả:

```text
{Engineering=[An], Support=[Ha]}
```

### Đặt filtering bên trong groupingBy

```java
Map<String, List<String>> result = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        TreeMap::new,
        Collectors.filtering(
            employee -> employee.getSalary() >= 60000,
            Collectors.mapping(Employee::getName, Collectors.toList())
        )
    ));
```

`groupingBy` phân loại từng nhân viên theo phòng ban trước. Sau khi một nhóm được tạo, downstream `filtering` chỉ chuyển nhân viên đạt điều kiện đến `mapping` và `toList`. Nhóm Sales vẫn được tạo vì stream ban đầu có nhân viên thuộc Sales; sau lọc, danh sách của nhóm đó rỗng.

Kết quả:

```text
{Engineering=[An], Sales=[], Support=[Ha]}
```

Đây là khác biệt cốt lõi: downstream filtering giữ được thông tin rằng một nhóm đã xuất hiện trong dữ liệu nguồn, ngay cả khi không phần tử nào của nhóm được chấp nhận.

## 3. Phần tử nào tạo ra một nhóm?

Với `groupingBy(classifier, downstream)`, classifier được áp dụng lên các phần tử đầu vào để xác định nhóm. Downstream collector xử lý các phần tử của từng nhóm sau đó.

Khi dùng `filtering` làm downstream:

1. Một phần tử nguồn được phân loại vào nhóm dựa trên classifier.
2. Nhóm tương ứng được tạo hoặc tìm thấy.
3. Predicate của `filtering` được kiểm tra cho phần tử đó.
4. Nếu predicate trả về `true`, phần tử được chuyển cho downstream collector bên trong.
5. Nếu predicate trả về `false`, phần tử không được tích lũy, nhưng nhóm đã được tạo vẫn được giữ.

Điều này có một giới hạn quan trọng: `filtering` không tự tạo key cho một nhóm **hoàn toàn không có phần tử nào trong nguồn**. Ví dụ nếu danh sách không chứa nhân viên thuộc `Marketing`, `groupingBy` không thể tự suy ra rằng cần thêm key `Marketing`. Nếu cần đầy đủ danh mục kể cả nhóm không có dữ liệu nguồn, phải bổ sung danh mục đó từ một nguồn cấu hình riêng hoặc khởi tạo/ghép kết quả theo quy tắc nghiệp vụ.

## 4. Chọn downstream collector phù hợp

`Collectors.filtering` có thể kết hợp với nhiều collector khác nhau. Predicate quyết định phần tử được chấp nhận; downstream quyết định cách tổng hợp các phần tử đã được chấp nhận.

### Thu thập thành danh sách

```java
Map<String, List<Employee>> eligibleByDepartment = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.filtering(
            employee -> employee.getSalary() >= 60000,
            Collectors.toList()
        )
    ));
```

Mỗi key ánh xạ đến danh sách các nhân viên đạt điều kiện. Nhóm có dữ liệu nguồn nhưng không có nhân viên đạt điều kiện sẽ có danh sách rỗng.

### Đếm số phần tử đạt điều kiện

```java
Map<String, Long> eligibleCountByDepartment = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.filtering(
            employee -> employee.getSalary() >= 60000,
            Collectors.counting()
        )
    ));
```

Với dữ liệu ví dụ, kết quả có số đếm Engineering là `1`, Sales là `0` và Support là `1`. Cách này hữu ích khi cần báo cáo số lượng theo nhóm mà vẫn giữ nhóm có số lượng đạt điều kiện bằng 0.

### Chuyển đổi phần tử trước khi thu

Có thể lồng `mapping` bên trong `filtering` để chỉ thu một thuộc tính của những phần tử đạt điều kiện:

```java
Collectors.filtering(
    employee -> employee.getSalary() >= 60000,
    Collectors.mapping(Employee::getName, Collectors.toSet())
)
```

Collector này lọc nhân viên theo lương, chuyển nhân viên được chấp nhận thành tên, rồi thu tên vào một `Set`. Có thể thay `toSet()` bằng `toList()`, `joining(...)`, `summarizingInt(...)` hoặc collector downstream thích hợp khác.

### Kết hợp với partitioningBy

`filtering` cũng có thể được dùng làm downstream của `partitioningBy`:

```java
Map<Boolean, List<Employee>> result = employees.stream()
    .collect(Collectors.partitioningBy(
        employee -> employee.getDepartment().equals("Engineering"),
        Collectors.filtering(
            employee -> employee.getSalary() >= 60000,
            Collectors.toList()
        )
    ));
```

Ở ví dụ này, `partitioningBy` chia nguồn thành hai nhóm theo điều kiện phòng ban; downstream `filtering` tiếp tục lọc từng nhóm theo mức lương. Collector `partitioningBy` trả về cả hai key Boolean `true` và `false`, kể cả khi một phía không có phần tử đạt điều kiện downstream.

## 5. Ví dụ hoàn chỉnh chạy với Java 9 trở lên

Ví dụ dưới đây dùng `TreeMap` để kết quả hiển thị theo thứ tự key ổn định, đồng thời so sánh lọc trước khi nhóm với lọc ở downstream.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class Main {
    static final class Employee {
        private final String name;
        private final String department;
        private final int salary;

        Employee(String name, String department, int salary) {
            this.name = name;
            this.department = department;
            this.salary = salary;
        }

        String getName() {
            return name;
        }

        String getDepartment() {
            return department;
        }

        int getSalary() {
            return salary;
        }
    }

    public static void main(String[] args) {
        List<Employee> employees = Arrays.asList(
            new Employee("An", "Engineering", 90000),
            new Employee("Binh", "Engineering", 50000),
            new Employee("Chi", "Sales", 55000),
            new Employee("Dung", "Sales", 48000),
            new Employee("Ha", "Support", 65000)
        );

        Map<String, List<String>> groupedWithFiltering = employees.stream()
            .collect(Collectors.groupingBy(
                Employee::getDepartment,
                TreeMap::new,
                Collectors.filtering(
                    employee -> employee.getSalary() >= 60000,
                    Collectors.mapping(Employee::getName, Collectors.toList())
                )
            ));

        Map<String, List<String>> groupedAfterStreamFilter = employees.stream()
            .filter(employee -> employee.getSalary() >= 60000)
            .collect(Collectors.groupingBy(
                Employee::getDepartment,
                TreeMap::new,
                Collectors.mapping(Employee::getName, Collectors.toList())
            ));

        System.out.println(groupedWithFiltering);
        System.out.println(groupedAfterStreamFilter);
        System.out.println(groupedWithFiltering.get("Sales").size());
    }
}
```

Lưu vào `Main.java`, biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 Main.java
java Main
```

Stdout chính xác:

```text
{Engineering=[An], Sales=[], Support=[Ha]}
{Engineering=[An], Support=[Ha]}
0
```

Ví dụ cho thấy downstream filtering giữ key Sales và tạo danh sách rỗng, trong khi lọc stream trước khi nhóm làm key Sales biến mất. Dòng cuối xác nhận danh sách của Sales trong kết quả downstream có kích thước `0`.

## 6. Những lưu ý khi sử dụng

- `Collectors.filtering` có từ Java 9. Khi dùng `javac --release 8`, API này không có trong API nền tảng được chọn; mã cần target Java 9 trở lên.
- Predicate chỉ lọc các phần tử được chuyển vào downstream. Nó không thay đổi nguồn stream và không tự tạo key nhóm.
- Nếu muốn nhóm tồn tại khi tất cả phần tử nguồn của nhóm bị loại, đặt `filtering` bên trong collector nhóm. Nếu muốn nhóm biến mất khi không có phần tử đạt điều kiện, có thể lọc stream trước khi nhóm.
- Nếu cần cả những nhóm không có bất kỳ phần tử nguồn nào, phải cung cấp danh mục nhóm đầy đủ và kết hợp với kết quả grouping; downstream filtering không thể tự tạo những key đó.
- Chọn downstream theo kết quả cần có: `toList`/`toSet` để thu phần tử, `counting` để đếm, `mapping` để đổi kiểu dữ liệu trước khi thu, hoặc collector tổng hợp phù hợp.
- Predicate nên không can thiệp vào nguồn và không dựa vào trạng thái thay đổi bên ngoài. Tránh sửa collection đang stream hoặc tạo side effect trong predicate.
- Với parallel stream, dùng predicate stateless và downstream collector phù hợp; không tự cập nhật một `ArrayList` hoặc `HashMap` dùng chung từ predicate.
- Không nhầm `Collectors.filtering` với `Stream.filter`: một cái là downstream collector, cái còn lại là intermediate operation trên stream.

## 7. Lỗi thường gặp

1. **Đặt `filter` trước `groupingBy` nhưng vẫn mong nhóm rỗng xuất hiện.** Khi tất cả phần tử của nhóm bị lọc khỏi nguồn, `groupingBy` không nhận được phần tử nào để tạo key. Dùng downstream `Collectors.filtering` nếu cần giữ nhóm đó.
2. **Nghĩ `filtering` tạo sẵn mọi nhóm có thể có.** Nó chỉ giữ nhóm đã có phần tử đi qua classifier. Danh mục nhóm không xuất hiện trong nguồn cần được bổ sung riêng.
3. **Nhầm thứ tự tham số.** `filtering` nhận predicate trước, downstream collector sau.
4. **Bỏ quên downstream collector.** `filtering` không tự quyết định kết quả là list, set hay số đếm; phải cung cấp collector bên trong.
5. **Dùng sai kiểu dữ liệu khi gán kết quả.** Kiểu giá trị của map phụ thuộc vào downstream. `toList()` trả list, `counting()` trả `Long`, còn `mapping(..., toSet())` trả set.
6. **Giả định nhóm rỗng luôn là null.** Với downstream `toList`, nhóm tồn tại nhưng không có phần tử sẽ có list rỗng; với `counting`, kết quả là `0L`.
7. **Dùng predicate có side effect.** Collector có thể chạy song song; predicate có trạng thái thay đổi có thể cho kết quả không xác định hoặc gây race condition.

## 8. Ghi nhớ

1. `Collectors.filtering` là downstream collector được bổ sung từ Java 9.
2. Cú pháp là `Collectors.filtering(predicate, downstream)`.
3. Khi lồng trong `groupingBy`, nhóm có dữ liệu nguồn vẫn được giữ dù mọi phần tử của nhóm bị predicate loại.
4. Lọc bằng `Stream.filter` trước khi nhóm có thể làm biến mất nhóm không còn phần tử nào.
5. `filtering` không tạo key cho nhóm hoàn toàn không xuất hiện trong nguồn.
6. Downstream quyết định cách thu dữ liệu: list, set, count, mapping hoặc phép tổng hợp khác.
7. Dùng predicate stateless, non-interfering và chọn cách lọc theo yêu cầu giữ hay loại nhóm rỗng.