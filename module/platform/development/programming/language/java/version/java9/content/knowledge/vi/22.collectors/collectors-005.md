# Kết hợp với groupingBy, partitioningBy và bộ thu lồng nhau trong Java Streams

Java Stream API cung cấp các collector để tổng hợp dữ liệu theo nhóm. `Collectors.groupingBy` gom phần tử theo một khóa, `Collectors.partitioningBy` chia phần tử theo một điều kiện boolean, còn downstream collector cho phép tiếp tục đếm, tính toán, ánh xạ hoặc gom nhóm ngay bên trong từng nhóm.

Khi kết hợp các collector, một pipeline có thể tạo ra kết quả như số nhân viên theo phòng ban, số người đang hoạt động trong từng phòng ban, danh sách kỹ năng duy nhất theo nhóm, hoặc cấu trúc Map nhiều tầng. Việc chọn đúng collector giúp biểu diễn trực tiếp cấu trúc dữ liệu cần có và tránh các vòng lặp lồng nhau phải tự quản lý trạng thái.

## 1. Collector và vai trò của collect()

Một `Collector<T, A, R>` mô tả cách tích lũy các phần tử kiểu `T` vào vùng tích lũy kiểu `A`, rồi hoàn tất thành kết quả kiểu `R`. Stream dùng collector thông qua terminal operation `collect()`:

~~~java
R result = stream.collect(collector);
~~~

Các collector chuẩn được cung cấp trong `java.util.stream.Collectors`. Những phương thức thường dùng:

- `toList()`, `toSet()`, `toCollection(...)`: gom phần tử thành collection.
- `counting()`: đếm số phần tử.
- `summingInt(...)`, `averagingInt(...)`, `summarizingInt(...)`: tổng hợp số nguyên.
- `minBy(...)`, `maxBy(...)`: tìm phần tử nhỏ nhất hoặc lớn nhất theo Comparator.
- `mapping(...)`: biến đổi phần tử trước khi chuyển cho downstream collector.
- `filtering(...)`: chỉ chuyển phần tử thỏa predicate cho downstream collector.
- `flatMapping(...)`: ánh xạ mỗi phần tử thành một Stream rồi làm phẳng trước khi thu thập.
- `collectingAndThen(...)`: áp dụng một bước hoàn tất sau downstream collector.
- `groupingBy(...)` và `partitioningBy(...)`: phân nhóm và phân hoạch phần tử.

Một collector có thể nhận collector khác làm đối số downstream. Cách kết hợp này thường được gọi là downstream hoặc nested collector.

## 2. groupingBy: gom nhóm theo khóa

Dạng đơn giản:

~~~java
Map<K, List<T>> result = stream.collect(
    Collectors.groupingBy(classifier)
);
~~~

Classifier là hàm lấy khóa nhóm từ mỗi phần tử. Mọi phần tử có cùng khóa được đưa vào cùng một danh sách.

Ví dụ:

~~~java
Map<String, List<Employee>> byDepartment = employees.stream()
    .collect(Collectors.groupingBy(Employee::department));
~~~

Nếu dữ liệu có phòng ban Engineering, Sales và Support, kết quả là một Map có mỗi phòng ban làm khóa và danh sách nhân viên tương ứng làm giá trị.

### Chọn downstream collector và kiểu Map

Có ba dạng overload chính:

~~~java
groupingBy(classifier)
groupingBy(classifier, downstream)
groupingBy(classifier, mapFactory, downstream)
~~~

- Dạng một đối số mặc định thu thập mỗi nhóm thành `List<T>`.
- Dạng hai đối số cho phép chọn cách tổng hợp bên trong mỗi nhóm.
- Dạng ba đối số cho phép chọn cả kiểu Map chứa các nhóm.

Ví dụ đếm số nhân viên mỗi phòng ban:

~~~java
Map<String, Long> countByDepartment = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

Ví dụ dùng `TreeMap` để sắp xếp khóa phòng ban:

~~~java
Map<String, Long> countByDepartment = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        TreeMap::new,
        Collectors.counting()
    ));
~~~

Map được tạo bởi overload mặc định không có cam kết về kiểu cụ thể hoặc thứ tự duyệt khóa. Khi cần thứ tự khóa ổn định theo thứ tự tự nhiên, dùng `TreeMap::new`. Nếu cần một loại Map cụ thể cho hợp đồng API, hãy cung cấp map factory phù hợp.

Classifier không được trả về null: `groupingBy` hiện hành từ chối khóa null và ném `NullPointerException`. Nếu trường phân nhóm có thể null, hãy chuẩn hóa khóa trước khi grouping, ví dụ dùng chuỗi đại diện rõ ràng như `"UNKNOWN"`, hoặc lọc và xử lý các bản ghi thiếu dữ liệu theo quy tắc nghiệp vụ.

## 3. partitioningBy: chia thành hai nhóm true và false

`partitioningBy` dùng predicate để chia tất cả phần tử thành hai nhóm:

~~~java
Map<Boolean, List<Employee>> byActiveStatus = employees.stream()
    .collect(Collectors.partitioningBy(Employee::active));
~~~

Khác với groupingBy, khóa chỉ có hai giá trị boolean: `true` và `false`. Kết quả partitioningBy luôn chứa cả hai khóa, kể cả khi một phía không có phần tử.

Có thể kết hợp downstream collector:

~~~java
Map<Boolean, Long> countByActiveStatus = employees.stream()
    .collect(Collectors.partitioningBy(
        Employee::active,
        Collectors.counting()
    ));
~~~

Kết quả là số phần tử thỏa điều kiện và số phần tử không thỏa điều kiện. Dùng `partitioningBy` khi câu hỏi thực sự là một phép chia đôi. Nếu cần phân loại thành nhiều giá trị như phòng ban, loại đơn hàng hoặc trạng thái, dùng `groupingBy`.

## 4. Downstream collector: tổng hợp ngay trong từng nhóm

Downstream collector được chạy riêng trên các phần tử của mỗi nhóm. Điều này cho phép tạo Map có giá trị là số đếm, tổng, trung bình, tập hợp hoặc một kết quả đã biến đổi.

### Đếm phần tử: counting()

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

Kiểu kết quả là `Map<String, Long>`. `counting()` trả về `Long`, không phải `Integer`.

### Tính tổng, trung bình và thống kê

~~~java
import java.util.IntSummaryStatistics;

Map<String, Integer> salaryTotals = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.summingInt(Employee::salary)
    ));

Map<String, Double> salaryAverages = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.averagingInt(Employee::salary)
    ));

Map<String, IntSummaryStatistics> salaryStats = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.summarizingInt(Employee::salary)
    ));
~~~

`IntSummaryStatistics` cung cấp count, sum, min, average và max. Dùng summarizing khi cần nhiều thống kê trong một lượt tổng hợp.

### Chuyển đổi trước khi thu thập: mapping()

`mapping(mapper, downstream)` biến đổi mỗi phần tử rồi đưa kết quả vào downstream collector:

~~~java
Map<String, Set<String>> namesByDepartment = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.mapping(
            Employee::name,
            Collectors.toSet()
        )
    ));
~~~

Ở đây, nhóm vẫn được xác định bằng phòng ban, nhưng nội dung thu thập là tên thay vì toàn bộ Employee.

Nếu cần thứ tự phần tử ổn định, dùng `toCollection(TreeSet::new)` thay cho `toSet()`. API `toSet()` không bảo đảm kiểu Set cụ thể hoặc thứ tự duyệt.

### Lọc trong từng nhóm: filtering()

`Collectors.filtering(predicate, downstream)` được bổ sung từ Java 9. Nó chỉ chuyển các phần tử thỏa điều kiện đến downstream collector.

~~~java
Map<String, Long> activeCountByDepartment = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.filtering(
            Employee::active,
            Collectors.counting()
        )
    ));
~~~

Điểm khác biệt quan trọng giữa downstream filtering và `stream.filter(...)` trước grouping:

- `stream.filter(Employee::active).collect(groupingBy(...))`: nhóm chỉ xuất hiện nếu có ít nhất một nhân viên active.
- `groupingBy(..., filtering(Employee::active, counting()))`: nhóm vẫn xuất hiện nếu phòng ban có nhân viên đầu vào, kể cả khi tất cả đều inactive; số đếm của nhóm đó bằng 0.

Chọn cách nào phụ thuộc vào việc kết quả cần giữ những nhóm không có phần tử thỏa điều kiện hay không.

### Làm phẳng dữ liệu con: flatMapping()

`flatMapping(mapper, downstream)` được bổ sung từ Java 9. Mapper trả về một Stream cho mỗi phần tử; các Stream con được làm phẳng rồi chuyển phần tử của chúng đến downstream collector.

~~~java
Map<String, Set<String>> skillsByDepartment = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.flatMapping(
            employee -> employee.skills().stream(),
            Collectors.toCollection(TreeSet::new)
        )
    ));
~~~

Ví dụ mỗi nhân viên có một danh sách kỹ năng. Kết quả gom các kỹ năng của mọi nhân viên trong phòng ban thành một tập hợp không trùng lặp và có thứ tự.

### Hoàn tất kết quả: collectingAndThen()

`collectingAndThen(downstream, finisher)` chạy downstream trước rồi áp dụng hàm finisher lên kết quả của downstream:

~~~java
Map<String, List<Employee>> immutableGroups = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.collectingAndThen(
            Collectors.toList(),
            List::copyOf
        )
    ));
~~~

Ví dụ trên tạo bản sao danh sách không sửa đổi được cho mỗi nhóm. Lưu ý đây là tính bất biến của danh sách; nếu phần tử bên trong là đối tượng mutable thì chúng vẫn có thể thay đổi. Muốn bất biến sâu, cần thiết kế cả phần tử và các đối tượng lồng nhau theo hướng bất biến.

### Tìm phần tử lớn nhất hoặc nhỏ nhất trong mỗi nhóm

~~~java
Map<String, Optional<Employee>> highestPaidByDepartment =
    employees.stream().collect(Collectors.groupingBy(
        Employee::department,
        Collectors.maxBy(
            Comparator.comparingInt(Employee::salary)
        )
    ));
~~~

Downstream `maxBy` trả về `Optional<Employee>`, vì hợp đồng collector thể hiện trường hợp không có phần tử. Trong groupingBy thông thường, mỗi nhóm được tạo từ ít nhất một phần tử, nhưng Optional vẫn là kiểu kết quả được định nghĩa bởi maxBy.

## 5. Kết hợp nhiều tầng: nested groupingBy

Có thể lồng groupingBy để tạo Map nhiều tầng. Ví dụ nhóm nhân viên theo phòng ban, sau đó theo trạng thái active:

~~~java
Map<String, Map<Boolean, Long>> countsByDepartmentAndStatus =
    employees.stream().collect(Collectors.groupingBy(
        Employee::department,
        TreeMap::new,
        Collectors.groupingBy(
            Employee::active,
            TreeMap::new,
            Collectors.counting()
        )
    ));
~~~

Cấu trúc kết quả:

- Map ngoài: khóa là phòng ban.
- Map bên trong: khóa là trạng thái boolean.
- Giá trị cuối: số nhân viên trong tổ hợp phòng ban và trạng thái.

Có thể lồng groupingBy với partitioningBy khi một tầng phân loại có đúng hai nhánh:

~~~java
Map<String, Map<Boolean, Long>> byDepartmentAndActive =
    employees.stream().collect(Collectors.groupingBy(
        Employee::department,
        Collectors.partitioningBy(
            Employee::active,
            Collectors.counting()
        )
    ));
~~~

Cách lồng này hữu ích khi muốn giữ cấu trúc hai tầng để truy cập như `result.get("Engineering").get(true)`. Tuy nhiên, đừng lồng quá nhiều tầng nếu cấu trúc kết quả trở nên khó đọc. Có thể dùng một khóa record tổng hợp hoặc một lớp kết quả riêng khi điều đó làm mô hình rõ ràng hơn.

## 6. Kết hợp partitioningBy với groupingBy

Có thể phân hoạch toàn bộ dữ liệu trước, rồi trong từng nhánh tiếp tục phân nhóm:

~~~java
Map<Boolean, Map<String, Long>> byActiveThenDepartment =
    employees.stream().collect(Collectors.partitioningBy(
        Employee::active,
        Collectors.groupingBy(
            Employee::department,
            TreeMap::new,
            Collectors.counting()
        )
    ));
~~~

Cấu trúc ngoài là `true/false`, bên trong là phòng ban. So với groupingBy rồi partitioningBy, thứ tự lồng nhau thay đổi cấu trúc truy cập và cách đọc kết quả. Hãy chọn thứ tự theo câu hỏi chính mà chương trình cần trả lời.

## 7. Ví dụ Java chạy được

Ví dụ sau dùng dữ liệu nhân viên để minh họa groupingBy, partitioningBy, downstream filtering, flatMapping, nested groupingBy và collectingAndThen.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class NestedCollectorsExample {
    record Employee(
        String name,
        String department,
        boolean active,
        int salary,
        List<String> skills
    ) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
            new Employee("Alice", "Engineering", true, 120,
                List.of("Java", "SQL")),
            new Employee("Bao", "Engineering", false, 90,
                List.of("Java", "Docker")),
            new Employee("Em", "Engineering", true, 130,
                List.of("Java", "Cloud")),
            new Employee("Chi", "Sales", true, 100,
                List.of("CRM", "SQL")),
            new Employee("Dung", "Sales", true, 110,
                List.of("CRM", "Java")),
            new Employee("Fai", "Support", false, 80,
                List.of("Helpdesk"))
        );

        Map<String, Long> departmentCounts = employees.stream()
            .collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.counting()
            ));
        System.out.println("counts=" + departmentCounts);

        Map<Boolean, Long> activeCounts = employees.stream()
            .collect(Collectors.partitioningBy(
                Employee::active,
                Collectors.counting()
            ));
        System.out.println("active=" + activeCounts.get(true));
        System.out.println("inactive=" + activeCounts.get(false));

        Map<String, Long> activeByDepartment = employees.stream()
            .collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.filtering(
                    Employee::active,
                    Collectors.counting()
                )
            ));
        System.out.println("active by department=" + activeByDepartment);

        Map<String, Set<String>> skillsByDepartment = employees.stream()
            .collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.flatMapping(
                    employee -> employee.skills().stream(),
                    Collectors.toCollection(TreeSet::new)
                )
            ));
        System.out.println("skills=" + skillsByDepartment);

        Map<String, Map<Boolean, Long>> nestedCounts = employees.stream()
            .collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.groupingBy(
                    Employee::active,
                    TreeMap::new,
                    Collectors.counting()
                )
            ));
        System.out.println("nested=" + nestedCounts);

        Map<String, List<Employee>> immutableGroups = employees.stream()
            .collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.collectingAndThen(
                    Collectors.toList(),
                    List::copyOf
                )
            ));
        System.out.println("engineering size="
            + immutableGroups.get("Engineering").size());
        try {
            immutableGroups.get("Engineering").add(employees.get(0));
        } catch (UnsupportedOperationException ex) {
            System.out.println("immutable list="
                + ex.getClass().getSimpleName());
        }
    }
}
~~~

Lưu mã trong tệp `NestedCollectorsExample.java`, sau đó biên dịch và chạy bằng Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all NestedCollectorsExample.java
java NestedCollectorsExample
~~~

Kết quả stdout chính xác:

~~~text
counts={Engineering=3, Sales=2, Support=1}
active=4
inactive=2
active by department={Engineering=2, Sales=2, Support=0}
skills={Engineering=[Cloud, Docker, Java, SQL], Sales=[CRM, Java, SQL], Support=[Helpdesk]}
nested={Engineering={false=1, true=2}, Sales={true=2}, Support={false=1}}
engineering size=3
immutable list=UnsupportedOperationException
~~~

Giải thích:

1. `groupingBy(..., counting())` đếm nhân viên theo phòng ban.
2. `partitioningBy(..., counting())` đếm hai nhánh active và inactive.
3. Downstream `filtering` giữ nhóm Support dù không có nhân viên active; giá trị đếm của nhóm là 0.
4. Downstream `flatMapping` lấy các kỹ năng từ danh sách con của từng nhân viên rồi gom vào TreeSet, loại trùng và sắp xếp.
5. Nested groupingBy tạo Map phòng ban → trạng thái active → số lượng. Nhóm chỉ có trạng thái xuất hiện trong dữ liệu của phòng ban đó.
6. `collectingAndThen(..., List::copyOf)` biến danh sách kết quả thành danh sách không sửa đổi được; thao tác add ném UnsupportedOperationException.

## 8. Một số collector hữu ích khác

### teeing(): chạy hai downstream collector trên cùng dữ liệu

Từ Java 12, `Collectors.teeing(downstream1, downstream2, merger)` cho phép thu thập cùng một luồng bằng hai collector rồi kết hợp hai kết quả:

~~~java
record SalarySummary(long count, double average) {}

SalarySummary summary = employees.stream().collect(
    Collectors.teeing(
        Collectors.counting(),
        Collectors.averagingInt(Employee::salary),
        SalarySummary::new
    )
);
~~~

Trong trường hợp cần thống kê theo từng phòng ban, có thể đặt teeing làm downstream của groupingBy. Đây là cách kết hợp nhiều kết quả mà không phải duyệt nguồn Stream hai lần.

### collectingAndThen kết hợp với groupingBy

Dùng khi mỗi nhóm cần một dạng kết quả hoàn tất riêng, chẳng hạn danh sách không sửa đổi, một giá trị đã định dạng hoặc một cấu trúc được chuyển đổi sau khi thu thập. Finisher chạy sau downstream collector cho từng nhóm.

### summarizingInt thay cho nhiều lượt tổng hợp

Nếu cần count, sum, min, average và max của cùng một trường số, `summarizingInt` trả về `IntSummaryStatistics`. Cách này thường rõ ràng hơn việc tạo nhiều pipeline riêng chỉ để tính từng chỉ số.

## 9. Lưu ý về null, thứ tự và hiệu năng

### Khóa nhóm null

`groupingBy` không chấp nhận khóa null. Chuẩn hóa giá trị phân nhóm trước khi gọi collector:

~~~java
import java.util.Objects;
import java.util.function.Function;

Function<Employee, String> safeDepartment = employee ->
    Objects.requireNonNullElse(employee.department(), "UNKNOWN");
~~~

Sau đó dùng `groupingBy(safeDepartment)`. Hãy chọn giá trị thay thế phù hợp với nghiệp vụ và bảo đảm nó không thể nhầm với một phòng ban thực tế.

### Phần tử null và downstream collector

Các collector khác nhau có hợp đồng khác nhau đối với null. Ví dụ, một số collector như `toList()` có thể giữ null, nhưng collector dùng comparator hoặc mapper có thể thất bại tùy cách triển khai. Không nên suy luận rằng groupingBy tự loại bỏ phần tử null. Hãy xác thực nguồn dữ liệu hoặc lọc null trước khi thu thập nếu nghiệp vụ yêu cầu.

### Thứ tự Map và thứ tự phần tử

`groupingBy` mặc định không bảo đảm kiểu Map hoặc thứ tự khóa. `toSet()` không bảo đảm thứ tự phần tử. Nếu cần thứ tự rõ ràng, chọn `TreeMap`, `TreeSet` hoặc một collection phù hợp bằng map factory và downstream collector.

### Parallel Stream

`groupingBy` có thể dùng với parallel stream, nhưng việc kết hợp các Map trung gian có thể tốn chi phí khi có nhiều nhóm. Khi thứ tự không quan trọng và bài toán phù hợp với cập nhật đồng thời, cân nhắc `groupingByConcurrent`. Collector concurrent có các ràng buộc về thứ tự và downstream; hãy đo hiệu năng với dữ liệu thực tế trước khi chọn.

Không nên mặc định rằng parallel stream nhanh hơn. Chi phí chia công việc, kết hợp kết quả, kích thước dữ liệu và độ phân bố khóa đều ảnh hưởng hiệu năng.

## 10. Chọn collector theo yêu cầu

| Nhu cầu | Collector phù hợp |
|---|---|
| Gom phần tử thành danh sách theo khóa | `groupingBy(key)` |
| Đếm số phần tử trong từng nhóm | `groupingBy(key, counting())` |
| Chia thành hai nhóm theo điều kiện | `partitioningBy(predicate)` |
| Chia đôi và đếm mỗi phía | `partitioningBy(predicate, counting())` |
| Lấy một trường khác để thu thập | `groupingBy(key, mapping(mapper, downstream))` |
| Lọc trong mỗi nhóm nhưng vẫn giữ nhóm có dữ liệu đầu vào | `groupingBy(key, filtering(predicate, downstream))` |
| Gom các phần tử từ collection/Stream con | `groupingBy(key, flatMapping(mapper, downstream))` |
| Nhóm theo nhiều cấp | `groupingBy(key1, groupingBy(key2, downstream))` |
| Tạo kết quả không sửa đổi sau khi thu thập | `collectingAndThen(downstream, finisher)` |
| Tính hai kết quả rồi kết hợp | `teeing(downstream1, downstream2, merger)` |

## 11. Những lỗi thường gặp

- **Dùng groupingBy khi chỉ cần chia đúng hai nhánh:** partitioningBy diễn đạt ý định rõ hơn và bảo đảm có cả hai khóa true/false.
- **Nhầm mapping với flatMapping:** mapping tạo một kết quả cho mỗi phần tử; flatMapping làm phẳng nhiều phần tử từ một Stream con.
- **Dùng stream.filter trước grouping khi vẫn cần giữ nhóm không có phần tử đạt điều kiện:** dùng downstream filtering để nhóm vẫn được tạo với kết quả rỗng hoặc số đếm bằng 0.
- **Giả định groupingBy mặc định trả về HashMap hoặc TreeMap:** API không cam kết kiểu Map cụ thể; truyền map factory nếu cần.
- **Giả định toSet giữ thứ tự:** dùng TreeSet hoặc collection có thứ tự rõ ràng nếu thứ tự là yêu cầu.
- **Quên kiểu dữ liệu của counting():** kết quả là Long.
- **Lồng collector quá sâu:** cấu trúc Map nhiều tầng có thể khó đọc; cân nhắc record hoặc lớp kết quả riêng.
- **Dùng groupingBy với khóa null:** chuẩn hóa hoặc xử lý dữ liệu thiếu trước khi phân nhóm.
- **Mặc định parallelStream luôn nhanh hơn:** cần đo hiệu năng và cân nhắc chi phí merge các nhóm.

## 12. Tài liệu tham khảo chính thức

- [Collectors — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): hợp đồng của groupingBy, partitioningBy và các downstream collector.
- [Stream — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): collect, parallel stream và các đặc tính pipeline.
- [Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): thông tin về các thay đổi ngôn ngữ và thư viện theo phiên bản.
- [Dev.java — Stream API](https://dev.java/learn/api/streams/): hướng dẫn hiện hành về Stream pipeline và Collectors.