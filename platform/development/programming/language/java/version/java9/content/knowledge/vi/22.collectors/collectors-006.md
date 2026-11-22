# Giữ nhóm có kết quả rỗng khi yêu cầu nghiệp vụ cần

Khi tổng hợp dữ liệu theo nhóm, có trường hợp một nhóm vẫn phải xuất hiện trong báo cáo dù không có phần tử nào của nhóm đó thỏa điều kiện. Từ Java 9, `Collectors.filtering` cho phép đặt điều kiện lọc bên trong downstream collector của `groupingBy`. Nhờ vậy, nhóm đã xuất hiện trong dữ liệu nguồn vẫn được tạo và có kết quả rỗng nếu mọi phần tử của nhóm bị loại bởi điều kiện.

Điểm khác biệt quan trọng là vị trí đặt bộ lọc. Nếu gọi `Stream.filter` trước `groupingBy`, một nhóm không còn phần tử sau khi lọc sẽ biến mất khỏi Map. Nếu lọc trong downstream collector, `groupingBy` vẫn nhìn thấy phần tử gốc và tạo key cho nhóm đó.

## 1. Vấn đề khi lọc trước khi phân nhóm

Giả sử báo cáo nhân viên chỉ giữ người có lương từ 100.000 trở lên. Phòng HR có nhân viên trong dữ liệu nguồn nhưng không ai đạt ngưỡng.

~~~java
Map<Department, List<Employee>> result = employees.stream()
        .filter(employee -> employee.salary() >= 100_000)
        .collect(Collectors.groupingBy(Employee::department));
~~~

Sau bước `filter`, không còn nhân viên HR trong Stream. Vì `groupingBy` chỉ phân nhóm những phần tử nó nhận được, key HR không được tạo. Khi đọc Map, ứng dụng khó phân biệt "nhóm có dữ liệu nhưng không có kết quả phù hợp" với "nhóm hoàn toàn không xuất hiện trong dữ liệu".

Nếu yêu cầu báo cáo cần giữ nhóm đã có dữ liệu nguồn với kết quả rỗng, hãy đặt điều kiện lọc ở downstream collector.

## 2. Collectors.filtering

Java 9 bổ sung factory method:

~~~java
Collectors.filtering(
        Predicate<? super T> predicate,
        Collector<? super T, A, R> downstream
)
~~~

Collector này nhận predicate và một downstream collector. Mỗi phần tử được chuyển đến nó sẽ được kiểm tra; nếu predicate trả về `true`, phần tử được chuyển tiếp cho downstream collector. Nếu predicate trả về `false`, phần tử bị bỏ qua ở bước thu thập đó.

Kết hợp với `groupingBy`:

~~~java
Map<Department, List<Employee>> result = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        employee -> employee.salary() >= 100_000,
                        Collectors.toList()
                )
        ));
~~~

Luồng xử lý:

1. `groupingBy` nhận từng nhân viên và xác định phòng ban.
2. Nhóm tương ứng được tạo khi phần tử đầu tiên của phòng ban đó đến.
3. Downstream `filtering` kiểm tra nhân viên.
4. Chỉ nhân viên đạt điều kiện được chuyển vào List.

Nếu HR có nhân viên trong nguồn nhưng tất cả đều không đạt ngưỡng, key HR vẫn tồn tại và giá trị là List rỗng.

## 3. So sánh kết quả

Giả sử dữ liệu có các nhóm sau:

| Phòng ban | Số nhân viên nguồn | Số nhân viên đạt điều kiện |
|---|---:|---:|
| ENGINEERING | 2 | 1 |
| HR | 1 | 0 |
| SALES | 2 | 1 |
| SUPPORT | 0 | 0 |

Kết quả:

| Cách viết | ENGINEERING | HR | SALES | SUPPORT |
|---|---|---|---|---|
| `filter(...).groupingBy(...)` | Có 1 phần tử | Key không tồn tại | Có 1 phần tử | Key không tồn tại |
| `groupingBy(..., filtering(...))` | Có 1 phần tử | Key có List rỗng | Có 1 phần tử | Key không tồn tại |

Downstream `filtering` giữ được nhóm đã có ít nhất một phần tử nguồn, kể cả khi không phần tử nào vượt qua predicate. Nó không thể tự tạo key cho nhóm hoàn toàn vắng mặt trong nguồn, như SUPPORT.

## 4. Ví dụ chạy được với Java 17+

Tạo file **GroupingWithEmptyGroupsDemo.java**:

~~~java
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;

import static java.util.stream.Collectors.filtering;
import static java.util.stream.Collectors.groupingBy;

public class GroupingWithEmptyGroupsDemo {
    enum Department {
        ENGINEERING, HR, SALES, SUPPORT
    }

    record Employee(String name, Department department, int salary) {
    }

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("An", Department.ENGINEERING, 120_000),
                new Employee("Binh", Department.ENGINEERING, 90_000),
                new Employee("Chi", Department.HR, 70_000),
                new Employee("Dung", Department.SALES, 110_000),
                new Employee("Em", Department.SALES, 80_000)
        );

        Predicate<Employee> eligible =
                employee -> employee.salary() >= 100_000;

        Map<Department, List<Employee>> grouped = employees.stream()
                .collect(groupingBy(
                        Employee::department,
                        filtering(eligible, Collectors.toList())
                ));

        for (Department department : Department.values()) {
            if (grouped.containsKey(department)) {
                System.out.println(department + ": " + grouped.get(department));
            }
        }

        System.out.println("SUPPORT present: "
                + grouped.containsKey(Department.SUPPORT));

        Map<Department, Long> eligibleCounts = employees.stream()
                .collect(groupingBy(
                        Employee::department,
                        filtering(eligible, Collectors.counting())
                ));

        System.out.println("HR eligible count: " + eligibleCounts.get(Department.HR));

        Map<Department, List<Employee>> filteredBeforeGrouping = employees.stream()
                .filter(eligible)
                .collect(groupingBy(Employee::department));

        System.out.println("HR present after upstream filter: "
                + filteredBeforeGrouping.containsKey(Department.HR));

        Map<Department, List<Employee>> completeReport =
                new EnumMap<>(Department.class);

        for (Department department : Department.values()) {
            completeReport.put(
                    department,
                    grouped.getOrDefault(department, List.of())
            );
        }

        System.out.println("complete SUPPORT: "
                + completeReport.get(Department.SUPPORT));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac GroupingWithEmptyGroupsDemo.java
java GroupingWithEmptyGroupsDemo
~~~

Kết quả stdout:

~~~text
ENGINEERING: [Employee[name=An, department=ENGINEERING, salary=120000]]
HR: []
SALES: [Employee[name=Dung, department=SALES, salary=110000]]
SUPPORT present: false
HR eligible count: 0
HR present after upstream filter: false
complete SUPPORT: []
~~~

HR có trong nguồn nên downstream filtering giữ key HR với List rỗng. SUPPORT không có nhân viên trong nguồn nên `groupingBy` không tạo key. Đoạn cuối tạo một `EnumMap` mới từ danh mục enum để bổ sung mọi phòng ban còn thiếu bằng List rỗng. Đây là bước riêng dựa trên danh mục nghiệp vụ.

## 5. Các downstream collector khác

`Collectors.filtering` có thể bọc nhiều collector, không chỉ `toList()`.

**Đếm số phần tử đạt điều kiện:**

~~~java
Map<Department, Long> counts = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        employee -> employee.salary() >= 100_000,
                        Collectors.counting()
                )
        ));
~~~

Nhóm HR vẫn tồn tại với giá trị `0L`.

**Chuyển phần tử thành tên trước khi thu thập:**

~~~java
Map<Department, List<String>> names = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        employee -> employee.salary() >= 100_000,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                )
        ));
~~~

Downstream `mapping` biến Employee thành String rồi đưa vào List. Nhóm không có phần tử phù hợp vẫn có List rỗng.

Có thể dùng downstream `toSet()`, `summarizingInt()` hoặc các collector tổng hợp khác nếu kiểu dữ liệu và yêu cầu báo cáo phù hợp.

## 6. Khi nào cần tự bổ sung nhóm rỗng?

Phân biệt hai trường hợp:

- **Nhóm có phần tử nguồn nhưng không có phần tử đạt điều kiện:** dùng `groupingBy(classifier, filtering(predicate, downstream))`. Nhóm được giữ với List rỗng hoặc giá trị tổng hợp bằng 0.
- **Nhóm hoàn toàn không có trong nguồn nhưng vẫn phải hiển thị:** cần danh mục nhóm đầy đủ từ nghiệp vụ, sau đó bổ sung các key chưa có.

Ví dụ, danh mục phòng ban có thể là enum, bảng cấu hình hoặc dữ liệu danh mục trong database. Duyệt danh mục này để tạo Map đầy đủ:

~~~java
Map<Department, List<Employee>> completeReport =
        new EnumMap<>(Department.class);

for (Department department : Department.values()) {
    completeReport.put(
            department,
            grouped.getOrDefault(department, List.of())
    );
}
~~~

Không giả định `groupingBy` tự tạo key cho mọi enum, phòng ban hoặc loại sản phẩm. Collector chỉ phân nhóm các phần tử thực sự được chuyển đến nó.

Cũng không nên phụ thuộc vào khả năng sửa đổi của Map trả về từ `groupingBy`: hợp đồng API không cam kết loại Map, khả năng mutable, khả năng tuần tự hóa hoặc thread-safety. Tạo Map kết quả riêng giúp thể hiện rõ danh mục nhóm và quyền sở hữu dữ liệu.

## 7. Lỗi thường gặp

**Lọc trước khi groupingBy:** nhóm không còn phần tử sẽ không có key. Chuyển predicate vào downstream `filtering` khi cần giữ nhóm đã xuất hiện trong nguồn.

**Cho rằng filtering tạo mọi nhóm:** nhóm không có phần tử nguồn vẫn vắng mặt. Bổ sung nhóm từ danh mục nghiệp vụ nếu báo cáo cần đầy đủ.

**Nhầm List rỗng với key không tồn tại:** dùng `containsKey` để kiểm tra key. `get(key)` có thể trả `null` khi key vắng mặt, trong khi nhóm có kết quả rỗng thường trả về List rỗng.

**Dùng downstream collector sai kiểu:** predicate nhận kiểu phần tử đang phân nhóm. Nếu downstream cần kiểu khác, dùng `mapping` để chuyển kiểu trước khi thu thập.

**Giả định Map có thứ tự hoặc mutable:** `groupingBy` không cam kết loại Map cụ thể. Chọn overload có mapFactory hoặc tạo Map riêng nếu cần kiểu và thứ tự xác định.

## 8. Checklist áp dụng

- Xác định báo cáo cần giữ nhóm đã xuất hiện trong nguồn dù không có kết quả phù hợp.
- Đặt `Collectors.filtering(predicate, downstream)` bên trong `groupingBy`.
- Chọn downstream phù hợp: `toList()`, `counting()`, `mapping(...)`, `toSet()`.
- Phân biệt nhóm có trong nguồn nhưng không có kết quả với nhóm hoàn toàn vắng mặt.
- Dùng danh mục nhóm nghiệp vụ để bổ sung nhóm vắng mặt nếu báo cáo yêu cầu.
- Không phụ thuộc vào loại Map hoặc thứ tự key mà `groupingBy` không cam kết.

`Collectors.filtering` là API hiện hành từ Java 9. Đây là cách phù hợp để lọc trong từng nhóm khi cần giữ lại nhóm đã xuất hiện trong nguồn ngay cả khi kết quả downstream rỗng.
