# Collectors.flatMapping và trải phẳng dữ liệu của từng phần tử

## Mục tiêu

Khi mỗi phần tử đầu vào chứa một tập hợp con, ta thường cần gom tất cả phần tử con vào một kết quả chung hoặc gom chúng theo một nhóm. Ví dụ, mỗi nhân viên có nhiều kỹ năng, mỗi đơn hàng có nhiều sản phẩm, hoặc mỗi phòng ban có nhiều nhân viên và mỗi nhân viên lại có nhiều chứng chỉ.

Java 9 bổ sung **Collectors.flatMapping** để giải quyết trường hợp này ngay trong một Collector. Nó nhận một phần tử đầu vào, chuyển phần tử đó thành một Stream gồm không, một hoặc nhiều phần tử con, rồi đưa các phần tử con vào Collector downstream.

Điểm hữu ích nhất là có thể kết hợp flatMapping với groupingBy hoặc partitioningBy để trải phẳng dữ liệu riêng bên trong từng nhóm, thay vì phải tự tạo các cấu trúc trung gian.

## 1. Collectors.flatMapping là gì?

Collectors.flatMapping là một factory method trong lớp java.util.stream.Collectors. Phương thức này tạo ra một Collector trung gian có nhiệm vụ:

1. Nhận một phần tử kiểu T từ Stream nguồn.
2. Dùng mapper để chuyển phần tử đó thành một Stream chứa các phần tử kiểu U.
3. Lấy lần lượt từng phần tử U trong Stream con và chuyển cho Collector downstream.
4. Lặp lại quá trình với các phần tử đầu vào tiếp theo.

Chữ “flat” thể hiện việc trải phẳng nhiều Stream con thành một luồng giá trị được thu thập bởi downstream.

Dạng khai báo tổng quát:

~~~java
public static <T, U, A, R> Collector<T, ?, R> flatMapping(
        Function<? super T, ? extends Stream<? extends U>> mapper,
        Collector<? super U, A, R> downstream)
~~~

Trong đó:

- T: kiểu của phần tử trong Stream nguồn.
- U: kiểu của từng phần tử được tạo ra từ Stream con.
- mapper: hàm chuyển một phần tử T thành Stream các phần tử U.
- downstream: Collector nhận từng phần tử U để tích lũy kết quả.
- R: kiểu kết quả cuối cùng do downstream tạo ra.

Một phần tử T có thể tạo ra:

- Stream rỗng: không đóng góp phần tử nào.
- Stream có một phần tử: đóng góp đúng một giá trị.
- Stream có nhiều phần tử: đóng góp toàn bộ các giá trị đó.

Vì vậy flatMapping biểu diễn quan hệ một-nhiều hoặc một-không giữa dữ liệu nguồn và dữ liệu đích.

## 2. Phân biệt Stream.flatMap và Collectors.flatMapping

Hai API có ý tưởng trải phẳng giống nhau nhưng hoạt động ở hai vị trí khác nhau.

### Stream.flatMap

flatMap là thao tác trung gian trên Stream. Nó chuyển từng phần tử nguồn thành một Stream con rồi tạo ra một Stream phẳng để các thao tác tiếp theo xử lý:

~~~java
List<String> allSkills = employees.stream()
        .flatMap(employee -> employee.skills().stream())
        .collect(Collectors.toList());
~~~

Sau flatMap, Stream chỉ còn các kỹ năng. Thông tin nhóm của nhân viên không còn được giữ tự động trong kết quả.

### Collectors.flatMapping

flatMapping là một Collector downstream. Nó trải phẳng các giá trị con ngay trong quá trình tích lũy kết quả của một Collector khác:

~~~java
Map<String, Set<String>> skillsByDepartment =
        employees.stream().collect(
                Collectors.groupingBy(
                        Employee::department,
                        Collectors.flatMapping(
                                employee -> employee.skills().stream(),
                                Collectors.toSet()
                        )
                )
        );
~~~

Ở đây groupingBy vẫn phân nhóm theo phòng ban. flatMapping chỉ trải phẳng danh sách kỹ năng của các nhân viên thuộc từng phòng ban, sau đó downstream thu thập kỹ năng vào Set tương ứng.

| Tiêu chí | Stream.flatMap | Collectors.flatMapping |
|---|---|---|
| Loại API | Thao tác trung gian của Stream | Factory method tạo Collector |
| Vị trí sử dụng | Trong pipeline trước terminal operation | Bên trong collect hoặc downstream collector |
| Kết quả trực tiếp | Một Stream phẳng | Kết quả do downstream Collector tạo ra |
| Dùng với groupingBy | Có thể, nhưng cần giữ thông tin khóa trong phần tử trung gian | Trải phẳng trực tiếp bên trong từng nhóm |
| Mục đích điển hình | Biến Stream nhiều tầng thành một Stream | Gom các phần tử con trong một cấu trúc Collector |

Nếu chỉ cần một Stream phẳng để xử lý tiếp, dùng Stream.flatMap. Nếu cần trải phẳng dữ liệu bên trong một phép tổng hợp như groupingBy, dùng Collectors.flatMapping.

## 3. Dùng flatMapping với groupingBy

Đây là trường hợp phổ biến nhất: một phần tử nguồn có nhiều phần tử con và kết quả cần được chia nhóm theo thuộc tính của phần tử nguồn.

Giả sử mỗi nhân viên có tên, phòng ban và danh sách kỹ năng:

~~~java
record Employee(
        String name,
        String department,
        List<String> skills
) {
}
~~~

Mục tiêu là tạo Map trong đó:

- Key là tên phòng ban.
- Value là tập hợp các kỹ năng của tất cả nhân viên trong phòng ban đó.
- Kỹ năng trùng lặp chỉ xuất hiện một lần.

Cấu trúc Collector:

~~~java
Map<String, Set<String>> skillsByDepartment =
        employees.stream().collect(
                Collectors.groupingBy(
                        Employee::department,
                        Collectors.flatMapping(
                                employee -> employee.skills().stream(),
                                Collectors.toSet()
                        )
                )
        );
~~~

Có thể đọc cấu trúc từ trong ra ngoài:

1. employee -> employee.skills().stream() tạo Stream kỹ năng của một nhân viên.
2. Collectors.flatMapping trải phẳng các Stream kỹ năng của các nhân viên cùng nhóm.
3. Collectors.toSet() gom kỹ năng vào một Set.
4. Collectors.groupingBy phân nhóm nhân viên theo department và áp dụng Collector downstream cho từng nhóm.

Mỗi nhóm có Collector downstream riêng. Vì vậy các kỹ năng của phòng ban này không bị trộn với phòng ban khác.

### Nhóm vẫn tồn tại khi không có phần tử con

Giả sử phòng ban Support có một nhân viên nhưng danh sách kỹ năng rỗng. Nhân viên đó vẫn được đưa vào groupingBy, vì vậy nhóm Support vẫn được tạo. flatMapping nhận Stream rỗng và downstream tạo một tập hợp rỗng.

Đây là điểm quan trọng khi so sánh với việc filter nhân viên trước khi groupingBy. Nếu loại bỏ nhân viên có danh sách kỹ năng rỗng trước khi phân nhóm, phòng ban chỉ có những nhân viên như vậy có thể biến mất khỏi kết quả.

## 4. Chọn downstream Collector phù hợp

flatMapping không quyết định cách lưu kết quả. Nó chỉ chuyển các phần tử con đến downstream. Collector downstream quyết định cách tích lũy.

| Downstream | Kết quả | Hành vi |
|---|---|---|
| Collectors.toList() | List | Giữ các phần tử được thu thập, kể cả giá trị trùng |
| Collectors.toSet() | Set | Loại bỏ giá trị trùng theo equals/hashCode |
| Collectors.toCollection(TreeSet::new) | TreeSet | Loại bỏ trùng và sắp xếp theo thứ tự tự nhiên |
| Collectors.counting() | Long | Đếm số phần tử con |
| Collectors.summingInt(mapper) | Integer | Tự áp dụng mapper cho từng phần tử U sang int rồi tính tổng; không cần Collectors.mapping bổ sung |
| Collectors.mapping(...) | Kết quả downstream | Chuyển đổi mỗi phần tử con trước khi tích lũy |

Ví dụ thu thập danh sách kỹ năng và giữ phần tử trùng:

~~~java
List<String> allSkills = employees.stream().collect(
        Collectors.flatMapping(
                employee -> employee.skills().stream(),
                Collectors.toList()
        )
);
~~~

Ví dụ thu thập kỹ năng duy nhất theo thứ tự sắp xếp:

~~~java
Set<String> sortedSkills = employees.stream().collect(
        Collectors.flatMapping(
                employee -> employee.skills().stream(),
                Collectors.toCollection(TreeSet::new)
        )
);
~~~

Nếu cần đếm tổng số kỹ năng, có thể dùng downstream counting:

~~~java
long skillCount = employees.stream().collect(
        Collectors.flatMapping(
                employee -> employee.skills().stream(),
                Collectors.counting()
        )
);
~~~

Kết quả của flatMapping phụ thuộc vào downstream. Hãy chọn downstream theo yêu cầu về thứ tự, trùng lặp, kiểu dữ liệu và phép tổng hợp.

## 5. Kết hợp với các Collector khác

flatMapping có thể lồng với các Collector downstream khác để tạo phép tổng hợp nhiều cấp.

### Kết hợp với partitioningBy

partitioningBy chia dữ liệu thành hai nhóm theo điều kiện boolean. Mỗi nhóm có thể dùng flatMapping để trải phẳng các giá trị con:

~~~java
Map<Boolean, Set<String>> skillsByActive =
        employees.stream().collect(
                Collectors.partitioningBy(
                        Employee::active,
                        Collectors.flatMapping(
                                employee -> employee.skills().stream(),
                                Collectors.toSet()
                        )
                )
        );
~~~

Ví dụ này giả định Employee có phương thức active() trả về boolean. Kết quả có hai khóa true và false; mỗi giá trị là tập kỹ năng của nhân viên tương ứng.

### Kết hợp với filtering

Có thể lọc từng phần tử con trước khi chuyển vào downstream:

~~~java
Map<String, Set<String>> nonBlankSkillsByDepartment =
        employees.stream().collect(
                Collectors.groupingBy(
                        Employee::department,
                        Collectors.flatMapping(
                                employee -> employee.skills().stream(),
                                Collectors.filtering(
                                        skill -> !skill.isBlank(),
                                        Collectors.toSet()
                                )
                        )
                )
        );
~~~

Ở đây filtering lọc các kỹ năng sau khi flatMapping đã trải phẳng chúng. Nhờ vậy có thể loại bỏ chuỗi rỗng hoặc chỉ chứa khoảng trắng mà vẫn giữ cấu trúc nhóm.

### Kết hợp với mapping

mapping chuyển đổi từng phần tử mà không làm thay đổi số lượng phần tử. Có thể dùng mapping làm downstream của flatMapping khi cần biến đổi các phần tử con trước khi lưu:

~~~java
Collectors.flatMapping(
        employee -> employee.skills().stream(),
        Collectors.mapping(
                String::toUpperCase,
                Collectors.toSet()
        )
)
~~~

Với mỗi nhân viên, các kỹ năng được trải phẳng, chuyển thành chữ hoa rồi gom vào Set.

## 6. Xử lý Stream rỗng, null và đóng tài nguyên

### Stream rỗng

Nếu mapper trả về Stream.empty(), phần tử nguồn đó không đóng góp giá trị nào cho downstream:

~~~java
Collectors.flatMapping(
        employee -> employee.skills().isEmpty()
                ? Stream.empty()
                : employee.skills().stream(),
        Collectors.toSet()
)
~~~

Kết quả của nhóm vẫn được tạo nếu phần tử nguồn đã đi vào groupingBy; chỉ có tập giá trị downstream là rỗng nếu mọi Stream con đều rỗng.

### Mapper trả về null

Theo hợp đồng API, nếu mapper trả về null thay vì một Stream, flatMapping xem đó như Stream rỗng. Tuy nhiên, trong mã ứng dụng, nên trả về Stream.empty() để thể hiện rõ ý định và tránh dùng null như một giá trị điều khiển.

Lưu ý rằng nếu employee.skills() là null, biểu thức employee.skills().stream() sẽ phát sinh NullPointerException trước khi mapper trả về Stream. Nếu dữ liệu có thể chứa danh sách null, hãy xử lý ngay trong mapper:

~~~java
employee -> employee.skills() == null
        ? Stream.empty()
        : employee.skills().stream()
~~~

### Stream con được đóng tự động

Mỗi Stream được mapper tạo ra sẽ được đóng sau khi các phần tử của nó đã được chuyển đến downstream. Vì vậy, nếu Stream con có close handler, handler đó được thực thi sau khi xử lý xong Stream con tương ứng.

Không nên tái sử dụng cùng một Stream con cho nhiều phần tử nguồn. Stream chỉ được tiêu thụ một lần; hãy tạo một Stream mới trong mapper cho mỗi phần tử.

## 7. Parallel Stream và tính đúng đắn

flatMapping có thể được dùng trong pipeline parallel:

~~~java
Map<String, Set<String>> skillsByDepartment =
        employees.parallelStream().collect(
                Collectors.groupingBy(
                        Employee::department,
                        Collectors.flatMapping(
                                employee -> employee.skills().stream(),
                                Collectors.toSet()
                        )
                )
        );
~~~

Collector downstream xử lý các phần tử con được tạo ra từ từng phần tử nguồn. Khi dùng parallel Stream, việc tích lũy có thể diễn ra trên nhiều nhánh rồi được kết hợp theo cơ chế của Collector.

Để giữ tính đúng đắn:

- Mapper nên không có side effect và không sửa đổi dữ liệu nguồn.
- Không dùng một Collection mutable dùng chung để tự thêm phần tử từ mapper.
- Chọn downstream Collector có hành vi phù hợp với yêu cầu.
- Không giả định thứ tự phần tử nếu downstream hoặc nguồn không bảo đảm thứ tự.
- Chỉ dùng parallel khi khối lượng công việc đủ lớn để bù chi phí chia việc và kết hợp kết quả.

Collectors.toSet() không cam kết thứ tự duyệt. Nếu cần thứ tự sắp xếp, dùng TreeSet. Nếu cần giữ encounter order trong một List, chọn downstream toList() và bảo đảm nguồn Stream có thứ tự.

## 8. Ví dụ hoàn chỉnh có thể chạy

Tệp FlatMappingCollectorDemo.java:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class FlatMappingCollectorDemo {
    record Employee(
            String name,
            String department,
            List<String> skills
    ) {
    }

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("An", "Data", List.of("SQL", "Python")),
                new Employee("Binh", "Platform",
                        List.of("Java", "Kubernetes")),
                new Employee("Chi", "Data", List.of("Python", "SQL")),
                new Employee("Dung", "Support", List.of())
        );

        Map<String, TreeSet<String>> skillsByDepartment =
                employees.stream().collect(
                        Collectors.groupingBy(
                                Employee::department,
                                Collectors.flatMapping(
                                        employee -> employee.skills().stream(),
                                        Collectors.toCollection(TreeSet::new)
                                )
                        )
                );

        System.out.println("Data: " + skillsByDepartment.get("Data"));
        System.out.println("Platform: "
                + skillsByDepartment.get("Platform"));
        System.out.println("Support size: "
                + skillsByDepartment.get("Support").size());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 FlatMappingCollectorDemo.java
java FlatMappingCollectorDemo
~~~

Kết quả chuẩn:

~~~text
Data: [Python, SQL]
Platform: [Java, Kubernetes]
Support size: 0
~~~

Giải thích kết quả:

- Hai nhân viên Data có các kỹ năng SQL và Python. TreeSet gộp giá trị trùng và sắp xếp chúng.
- Nhóm Platform chứa Java và Kubernetes.
- Nhóm Support vẫn tồn tại vì có nhân viên Dung, nhưng danh sách kỹ năng rỗng nên downstream tạo TreeSet rỗng.
- TreeSet giúp kết quả in ra có thứ tự ổn định, thuận tiện cho việc kiểm tra output.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng flatMapping như một thao tác trực tiếp trên Stream | Nhầm với Stream.flatMap | Gọi Collectors.flatMapping bên trong collect hoặc downstream Collector |
| Truyền mapper trả về một Collection | Mapper yêu cầu Stream | Dùng collection.stream() hoặc Stream.of(...) |
| Quên downstream Collector | flatMapping cần biết cách tích lũy phần tử con | Truyền toList(), toSet(), counting() hoặc Collector phù hợp |
| Dùng toSet() nhưng mong muốn thứ tự ổn định | Set không cam kết encounter order | Dùng TreeSet nếu cần sắp xếp hoặc List nếu cần giữ thứ tự |
| Cho rằng nhóm không có phần tử con sẽ biến mất | Nhầm với filter trước groupingBy | flatMapping tạo kết quả rỗng cho downstream; nhóm vẫn tồn tại nếu có phần tử nguồn |
| Truyền Stream con đã sử dụng | Stream không thể tiêu thụ lại | Tạo Stream mới trong mapper cho từng phần tử nguồn |
| Gọi stream() trên Collection null | NullPointerException xảy ra trước khi mapper trả về | Kiểm tra null và trả về Stream.empty() |
| Thêm phần tử vào Collection dùng chung trong mapper | Side effect và nguy cơ race condition | Để downstream Collector quản lý việc tích lũy |

## 10. Checklist khi sử dụng

- Xác định kiểu phần tử nguồn T và kiểu phần tử con U.
- Mapper phải trả về Stream của các phần tử con.
- Chọn downstream Collector theo yêu cầu về List, Set, thứ tự, đếm hoặc tổng hợp.
- Dùng flatMapping bên trong groupingBy hoặc partitioningBy khi cần trải phẳng theo nhóm.
- Xử lý rõ trường hợp danh sách con rỗng hoặc null.
- Không tái sử dụng Stream con đã tiêu thụ.
- Không sửa trạng thái dùng chung trong mapper.
- Kiểm tra thứ tự, phần tử trùng và các nhóm rỗng bằng ví dụ có output xác định.
- Nhớ rằng Collectors.flatMapping có từ Java 9 và vẫn là API hiện hành.

Collectors.flatMapping giúp kết hợp quan hệ một-nhiều với cơ chế tích lũy của Collector. Khi lồng nó vào groupingBy hoặc partitioningBy, chương trình có thể trải phẳng dữ liệu con theo từng nhóm một cách trực tiếp, rõ ràng và dễ kiểm thử.