# Streamable để kết hợp, lọc và chuyển đổi tập kết quả

Trong chương **Luồng và wrapper** của module **SPRING_DATA_COMMONS**, `Streamable<T>` là một abstraction tiện dụng để làm việc với nhiều phần tử do repository trả về. Nó mở rộng cách sử dụng `Iterable<T>` bằng các thao tác nối kết quả, lọc phần tử và chuyển đổi kiểu dữ liệu.

Bài này tập trung vào việc kết hợp các kết quả đã có trong ứng dụng, hiểu đúng thời điểm xử lý và xây dựng một service trả danh sách nhân sự. Các ví dụ repository cần được đặt trong ứng dụng đã cấu hình module Spring Data cho kho dữ liệu cụ thể.

## 1. Streamable nằm ở đâu trong luồng xử lý?

`Streamable<T>` thuộc package `org.springframework.data.util`, đồng thời mở rộng `Iterable<T>` và `Supplier<Stream<T>>`. Có thể duyệt nó bằng `for-each` hoặc lấy một Java stream để dùng thêm các phép toán. Xem [API Streamable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/util/Streamable.html).

Phân biệt ba lớp trong một yêu cầu tìm kiếm:

| Lớp | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Truy vấn của store | Tìm nhân sự theo phòng ban | Chọn dữ liệu tại nguồn |
| Wrapper kết quả | `Streamable<Employee>` | Cung cấp cách duyệt và ghép các phần tử |
| Logic xử lý Java | `filter(Employee::isActive)` | Lọc hoặc chuyển đổi các đối tượng ứng dụng đang duyệt |

Ví dụ tối giản với dữ liệu trong bộ nhớ:

```java
import java.util.List;
import org.springframework.data.util.Streamable;

Streamable<Integer> numbers = Streamable.of(List.of(1, 2, 3, 4));

Streamable<String> labels = numbers
        .filter(number -> number % 2 == 0)
        .map(number -> "N-" + number);

List<String> result = labels.toList();
// ["N-2", "N-4"]
```

Đọc chuỗi xử lý theo thứ tự: nguồn có bốn số; giữ số chẵn; đổi từng số thành nhãn; cuối cùng tạo danh sách. Các biến nguồn vẫn giữ nguyên ý nghĩa, vì `filter` và `map` trả về một `Streamable` mới.

Những phương thức thường dùng:

| Phương thức | Mục đích |
| --- | --- |
| `Streamable.of(iterable)` | Bọc một nguồn có thể duyệt |
| `Streamable.empty()` | Tạo nguồn không có phần tử |
| `and(other)` | Nối thêm các phần tử từ nguồn khác |
| `filter(predicate)` | Giữ phần tử thỏa điều kiện |
| `map(mapper)` | Đổi từng phần tử sang một giá trị mới |
| `flatMap(mapper)` | Trải các stream con thành một chuỗi phần tử |
| `stream()` | Lấy Java stream để thực hiện phép toán bổ sung |
| `toList()` | Thu kết quả thành danh sách không cho sửa cấu trúc |

Bảng trên mô tả các tiện ích của wrapper, không phải danh sách phép toán sẽ được dịch thành truy vấn cơ sở dữ liệu.

## 2. Khai báo repository trả về Streamable

Spring Data cho phép sử dụng `Streamable` làm kiểu trả về cho query method có nhiều kết quả. Cách tạo truy vấn và kiểu trả về được hỗ trợ thực tế vẫn phụ thuộc module store. Xem [Repository query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html).

Giả sử domain type `Employee` đã được ánh xạ và cung cấp các property cùng getter sau:

| Property | Kiểu | Getter |
| --- | --- | --- |
| `id` | `Long` | `getId()` |
| `fullName` | `String` | `getFullName()` |
| `department` | `String` | `getDepartment()` |
| `active` | `boolean` | `isActive()` |

Mọi nhân sự trong ví dụ đã có mã định danh khác null. Repository minh họa:

```java
import org.springframework.data.repository.Repository;
import org.springframework.data.util.Streamable;

public interface EmployeeRepository extends Repository<Employee, Long> {

    Streamable<Employee> findByDepartmentOrderByIdAsc(String department);

    Streamable<Employee> findByFullNameContainingIgnoreCaseOrderByIdAsc(
            String text);
}
```

Ở đây, điều kiện theo phòng ban và tên thuộc derived query. Các thao tác gọi trên kết quả sau đó thuộc phần xử lý trong Java. Cơ chế trả về `Streamable` và nối các kết quả được mô tả trong [Using Streamable as Query Method Return Type](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.collections-and-iterables.streamable).

Để quan sát rõ hành vi, dùng bộ dữ liệu nhỏ sau:

| id | fullName | department | active |
| ---: | --- | --- | --- |
| 10 | An | DEV | true |
| 20 | Binh | OPS | true |
| 30 | Chi | DEV | false |
| 40 | Dang | SALES | true |

Với quy tắc tìm tên chứa chuỗi, không phân biệt chữ hoa chữ thường:

- Tìm phòng `DEV` trả về mã `[10, 30]`.
- Tìm tên chứa `an` trả về mã `[10, 40]`.
- Nhân sự mã 10 có mặt trong cả hai kết quả.

Đây là dữ liệu giả định để giải thích thuật toán. Khi áp dụng, cần dùng toán tử so khớp chuỗi mà store và phiên bản dự án hỗ trợ.

## 3. and nối kết quả, giữ lại phần tử trùng

Kết hợp hai kết quả:

```java
Streamable<Employee> byDepartment =
        repository.findByDepartmentOrderByIdAsc("DEV");

Streamable<Employee> byName =
        repository.findByFullNameContainingIgnoreCaseOrderByIdAsc("an");

Streamable<Employee> combined = byDepartment.and(byName);
```

Với dữ liệu trên, thứ tự mã sau khi nối là:

```text
byDepartment: [10, 30]
byName:       [10, 40]
combined:     [10, 30, 10, 40]
```

`and` thực hiện phép nối: đi qua nguồn thứ nhất rồi đến nguồn thứ hai. Nó không tự loại trùng hoặc sắp xếp lại toàn cục. Cách triển khai phép nối có thể xem trong [mã nguồn Streamable của Spring Data Commons](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/util/Streamable.java).

Điều này dẫn đến ba quyết định thiết kế riêng:

1. **Có giữ trùng không?** Với danh sách gợi ý nhân sự, thường chỉ muốn một mục cho mỗi mã nhân sự.
2. **Ưu tiên nguồn nào?** Nếu cùng mã nhưng dữ liệu khác nhau, ứng dụng cần một quy tắc chọn rõ ràng.
3. **Sắp xếp đầu ra thế nào?** Hai nguồn được sắp theo mã riêng không tạo thành một nguồn đã sắp theo mã toàn cục.

Trong ví dụ, `[10, 30, 10, 40]` không tăng dần toàn cục. Nếu đầu ra yêu cầu sắp xếp theo tên, cần một bước sắp xếp riêng sau khi chọn các nhân sự sẽ xuất hiện.

### Hai lời gọi repository vẫn là hai lời gọi

Biểu thức ngắn sau không biến thành một truy vấn dùng điều kiện `OR` tại store:

```java
Streamable<Employee> combined =
        repository.findByDepartmentOrderByIdAsc("DEV")
                .and(repository
                        .findByFullNameContainingIgnoreCaseOrderByIdAsc("an"));
```

Java phải gọi các phương thức repository để lấy đối số và đối tượng nhận trước khi gọi `and`. Wrapper không có thông tin để gộp ngược hai thao tác đó thành một truy vấn mới.

Nếu yêu cầu thực tế là một điều kiện tìm kiếm duy nhất tại nguồn, hãy thiết kế query method, Query by Example hoặc repository fragment phù hợp với store. Chọn cách nối ở service khi yêu cầu nghiệp vụ cần kết hợp hai nguồn kết quả riêng.

## 4. filter và map: lọc đối tượng, đổi cách biểu diễn

Tiếp tục với `combined` ở trên:

```java
Streamable<Employee> activeEmployees =
        combined.filter(Employee::isActive);

Streamable<String> employeeNames =
        activeEmployees.map(Employee::getFullName);

List<String> names = employeeNames.toList();
// ["An", "An", "Dang"]
```

Nhân sự mã 30 bị loại vì không hoạt động. Hai lần xuất hiện của mã 10 vẫn được giữ; `filter` chỉ áp dụng điều kiện, còn `map` chỉ chuyển giá trị. Cả hai bước đều không tự bổ sung quy tắc duy nhất theo mã.

### map sang DTO không đồng nghĩa projection tại store

Định nghĩa DTO bằng Java record, dùng Java 17 trở lên cho các ví dụ có record:

```java
public record EmployeeCard(
        Long id,
        String fullName,
        String department) {

    public static EmployeeCard from(Employee employee) {
        return new EmployeeCard(
                employee.getId(),
                employee.getFullName(),
                employee.getDepartment());
    }
}
```

Chuyển đổi trong ứng dụng:

```java
Streamable<EmployeeCard> cards = activeEmployees.map(EmployeeCard::from);
```

Thao tác này tạo `EmployeeCard` từ các đối tượng `Employee` đang được duyệt. Nó không yêu cầu store chỉ đọc ba cột tương ứng. Nếu mục tiêu là giảm dữ liệu truy xuất, cần thiết kế projection ngay trong hợp đồng query theo khả năng của store.

Tương tự, `filter(Employee::isActive)` không thêm `active = true` vào truy vấn đã khai báo. Nếu việc chỉ lấy nhân sự hoạt động là yêu cầu phổ biến và nguồn lớn, nên cân nhắc đưa điều kiện đó vào query.

### Dùng flatMap khi một phần tử sinh ra nhiều giá trị

Ví dụ độc lập với hai nhóm phòng ban:

```java
Streamable<List<String>> groups = Streamable.of(
        List.of("DEV", "OPS"),
        List.of("DEV", "SALES"));

Streamable<String> departments = groups.flatMap(List::stream);

List<String> result = departments.stream()
        .distinct()
        .sorted()
        .toList();
// ["DEV", "OPS", "SALES"]
```

`map` phù hợp khi mỗi phần tử được biến thành một giá trị đầu ra; `flatMap` phù hợp khi mỗi phần tử được biến thành một stream con cần trải phẳng. Trong ví dụ này, `distinct` và `sorted` là phép toán của Java `Stream`, được gọi sau `stream()`.

## 5. Loại trùng theo đúng định danh nghiệp vụ

Phép toán Java `Stream.distinct()` dựa vào `equals` của phần tử. Vì vậy, dùng `distinct()` trực tiếp trên entity đòi hỏi cách định nghĩa `equals`/`hashCode` phù hợp. Xem [Java Stream — distinct](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#distinct()).

Với danh sách nhân sự, yêu cầu của bài là duy nhất theo `id`. Một lựa chọn rõ ràng là gom vào `LinkedHashMap<Long, Employee>`, dùng mã nhân sự làm khóa và giữ đối tượng gặp trước.

```java
Map<Long, Employee> uniqueById = combined
        .filter(Employee::isActive)
        .stream()
        .collect(Collectors.toMap(
                Employee::getId,
                Function.identity(),
                (first, later) -> first,
                LinkedHashMap::new));
```

`Collectors.toMap` cho phép chỉ định cách lấy khóa, giá trị, xử lý khóa trùng và loại map đích. Xem [API Collectors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html).

Trong trường hợp này:

- Khóa là `id`, nên hai đối tượng có cùng mã được gộp dù không cùng tham chiếu.
- Hàm `(first, later) -> first` giữ đối tượng gặp trước.
- `LinkedHashMap` duy trì thứ tự chèn khóa.
- Sau khi lọc và gộp, thứ tự mã còn lại là `[10, 40]`.

Quy tắc giữ bản đầu tiên phù hợp với ví dụ ưu tiên nguồn phòng ban. Nó không chứng minh bản đầu là dữ liệu mới nhất. Nếu hai truy vấn đọc ở hai thời điểm khác nhau, ứng dụng cần quyết định có chấp nhận khác biệt đó hay cần một yêu cầu nhất quán mạnh hơn.

Đừng loại trùng bằng tên khi mục tiêu là duy nhất theo nhân sự. Hai người có thể cùng tên; ngược lại, một mã nhân sự có thể xuất hiện với hai cách viết tên khác nhau trong dữ liệu từ các nguồn khác nhau.

## 6. Service hoàn chỉnh cho danh sách nhân sự

Service sau dùng `EmployeeRepository` và `EmployeeCard` đã giới thiệu. Nó thực hiện đúng một quy trình: lấy hai nhóm, giữ nhân sự hoạt động, gộp theo mã và trả DTO.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.data.util.Streamable;

public final class EmployeeDirectoryService {

    private final EmployeeRepository repository;

    public EmployeeDirectoryService(EmployeeRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public List<EmployeeCard> search(
            String department,
            String namePart) {

        Objects.requireNonNull(department, "department");
        Objects.requireNonNull(namePart, "namePart");

        Streamable<Employee> byDepartment =
                repository.findByDepartmentOrderByIdAsc(department);

        Streamable<Employee> byName =
                repository.findByFullNameContainingIgnoreCaseOrderByIdAsc(
                        namePart);

        Map<Long, Employee> uniqueById = byDepartment
                .and(byName)
                .filter(Employee::isActive)
                .stream()
                .collect(Collectors.toMap(
                        Employee::getId,
                        Function.identity(),
                        (first, later) -> first,
                        LinkedHashMap::new));

        return Streamable.of(uniqueById.values())
                .map(EmployeeCard::from)
                .toList();
    }
}
```

Với lời gọi `search("DEV", "an")`, diễn tiến của dữ liệu giả định là:

| Bước | Chuỗi mã nhân sự |
| --- | --- |
| Kết quả theo phòng ban | `[10, 30]` |
| Kết quả theo tên | `[10, 40]` |
| Nối bằng `and` | `[10, 30, 10, 40]` |
| Lọc nhân sự hoạt động | `[10, 10, 40]` |
| Gộp theo mã, giữ lần đầu | `[10, 40]` |
| Đổi thành DTO | Hai `EmployeeCard` cho An và Dang |

Thứ tự lọc trước khi gộp là một lựa chọn nghiệp vụ. Nếu một bản ghi cũ không hoạt động xuất hiện trước một bản ghi đang hoạt động có cùng mã, quy trình trên bỏ bản không hoạt động trước rồi mới chọn bản giữ lại. Đảo hai bước có thể tạo kết quả khác. Cần thống nhất quy tắc khi dữ liệu từ các nguồn không đồng nhất.

Nếu cần thứ tự cuối cùng theo tên rồi mã, bổ sung bước sắp xếp sau khi tạo danh sách:

```java
List<EmployeeCard> sorted = cards.stream()
        .sorted(Comparator
                .comparing(EmployeeCard::fullName)
                .thenComparing(EmployeeCard::id))
        .toList();
```

Ở đoạn bổ sung này, `cards` là danh sách service đã trả về; cần import `java.util.Comparator`. Ví dụ giả định tên và mã đều khác null. Việc sắp xếp đầu ra là quyết định độc lập với thứ tự ưu tiên khi loại trùng.

## 7. Hiểu đúng tính trì hoãn và khả năng duyệt lại

Các phép `map`, `filter` của `Streamable` tạo wrapper dựa trên hàm cấp stream. Phần biến đổi được áp dụng lúc duyệt, không được lưu sẵn thành một danh sách kết quả chỉ nhờ khai báo chuỗi thao tác. Cách triển khai này thể hiện trong [mã nguồn Streamable](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/util/Streamable.java).

Tuy nhiên, trì hoãn phần biến đổi trong Java không có nghĩa truy vấn repository chưa chạy. Với kết quả repository thông thường, `Streamable` là wrapper tiện ích cho toàn bộ kết quả; bản thân nó không cam kết đọc cơ sở dữ liệu từng đợt hay giảm lượng dữ liệu vào bộ nhớ. Xem [bảng Consuming Large Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-methods).

### Mỗi lượt duyệt cần một nguồn hợp lệ

Ví dụ dùng list ổn định:

```java
List<Integer> source = List.of(1, 2, 3);

Streamable<Integer> transformed = Streamable.of(source)
        .map(number -> number * 10);

List<Integer> firstPass = transformed.toList();
List<Integer> secondPass = transformed.toList();

// Cả hai danh sách đều chứa [10, 20, 30].
```

Hai lần gọi trên duyệt nguồn và áp dụng phép biến đổi hai lần. Nó không phải cơ chế tự cache kết quả của `map`. Vì thế, nên để predicate và mapper chỉ tính toán giá trị, không gửi thông báo, ghi dữ liệu hay thực hiện hành động mà ứng dụng chỉ muốn chạy một lần.

Đối với nguồn dùng `Supplier<Stream<T>>`, mỗi lượt duyệt cần được cấp một stream sử dụng được. Lớp triển khai lấy stream từ supplier khi được yêu cầu; xem [mã nguồn LazyStreamable](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/util/LazyStreamable.java).

Cách phù hợp với một list trong bộ nhớ:

```java
Streamable<Integer> repeatable = Streamable.of(source::stream);

List<Integer> firstPass = repeatable.toList();
List<Integer> secondPass = repeatable.toList();
```

Cách cần tránh:

```java
Stream<Integer> once = source.stream();

// Supplier luôn trả lại đúng stream đã tạo một lần.
Streamable<Integer> broken = Streamable.of(() -> once);

List<Integer> firstPass = broken.toList();
List<Integer> secondPass = broken.toList(); // Tái sử dụng stream đã tiêu thụ.
```

Java stream chỉ được sử dụng một lần; tái sử dụng có thể gây `IllegalStateException`. Xem [quy tắc sử dụng Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html). Các đoạn dùng `Stream` cần import `java.util.stream.Stream`.

### Bọc một collection không đồng nghĩa chụp ảnh dữ liệu

```java
List<Integer> mutableSource = new ArrayList<>(List.of(1, 2));

Streamable<Integer> view = Streamable.of(mutableSource);

mutableSource.add(3);

List<Integer> result = view.toList();
// [1, 2, 3]
```

Nguồn vẫn là list được truyền vào. Trong ví dụ này, thay đổi xảy ra trước khi duyệt nên phần tử mới được thấy ở lượt duyệt sau. Không sửa collection trong lúc đang duyệt.

Nếu cần cố định tập phần tử tại thời điểm tạo wrapper, có thể sao chép trước:

```java
Streamable<Integer> snapshot =
        Streamable.of(List.copyOf(mutableSource));
```

Đây là bản sao của các tham chiếu phần tử. Nếu phần tử là entity có thể thay đổi, sao chép list không làm entity trở nên bất biến. Các đoạn trên cần import `java.util.ArrayList`.

### Thu kết quả khi cần dùng lại đầu ra đã tính

Khi một pipeline tốn công và cùng kết quả được sử dụng nhiều lần, thu nó thành một danh sách ở ranh giới phù hợp:

```java
List<EmployeeCard> computed = employees
        .filter(Employee::isActive)
        .map(EmployeeCard::from)
        .toList();

Streamable<EmployeeCard> reusable = Streamable.of(computed);
```

Trong đoạn này, `employees` là một `Streamable<Employee>` đã có. Các lần duyệt `reusable` sử dụng các DTO đã tạo; không chạy lại phần lọc và chuyển đổi ở trên.

`Streamable.toList()` và `toSet()` trả collection không cho sửa cấu trúc. Nếu cần danh sách có thể thêm hoặc xóa phần tử, tạo `new ArrayList<>(computed)`. Điều này không làm thay đổi tính có thể sửa của chính các đối tượng nằm trong danh sách.

## 8. Streamable, Stream và tài nguyên của store

Cần lựa chọn kiểu trả về theo yêu cầu đọc dữ liệu, không dựa riêng vào tên có chữ “stream”:

| Kiểu | Nhu cầu phù hợp |
| --- | --- |
| `List<T>` | Cần collection kết quả rõ ràng để trả về hoặc truy cập |
| `Streamable<T>` | Cần API tiện dụng để duyệt, nối, lọc và chuyển đổi tập kết quả |
| `Stream<T>` từ query | Cần streaming theo cơ chế mà store hỗ trợ |
| `Slice<T>` hoặc `Window<T>` | Cần điều khiển việc lấy kết quả theo từng phần trong phạm vi hỗ trợ |

Một query trả `Stream<T>` có thể gắn với tài nguyên của store và cần được đóng theo hợp đồng sử dụng. Không bọc một stream tài nguyên vào `Streamable.of(() -> stream)` rồi coi như đã giải quyết vòng đời của nó. Hướng dẫn đóng stream kết quả nằm trong [Streaming Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-streaming).

`Streamable` cũng không mang sẵn các bảo đảm của một pipeline reactive. Ví dụ service ở trên không thiết kế backpressure, tự lấy trang tiếp theo hoặc duyệt toàn bộ dữ liệu lớn bằng cursor.

Với ứng dụng JPA, truy cập quan hệ lazy bên trong mapper còn phụ thuộc ngữ cảnh persistence của ứng dụng. Cách tạo wrapper không tự bảo đảm rằng quan hệ đã được tải hoặc có thể truy cập ngoài giao dịch. Khi DTO cần dữ liệu quan hệ, hãy thiết kế truy vấn và ranh giới chuyển đổi phù hợp thay vì chỉ thay `List` thành `Streamable`.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả trong ví dụ | Cách xử lý |
| --- | --- | --- |
| `and` tự loại trùng | Nhân sự mã 10 xuất hiện hai lần | Chọn quy tắc gộp theo `id` |
| Hai nguồn đã sort thì kết quả nối cũng đã sort | Chuỗi `[10, 30, 10, 40]` không tăng dần | Sắp xếp kết quả cuối nếu cần |
| `filter` sẽ bổ sung điều kiện tại store | Có thể đã đọc cả nhân sự không hoạt động | Đưa điều kiện phổ biến vào query khi phù hợp |
| `map` sang DTO sẽ giảm dữ liệu đã truy xuất | Entity vẫn là nguồn để tạo DTO | Dùng projection ở query nếu cần giảm dữ liệu đọc |
| Duyệt lại là nhận kết quả đã cache | Mapper có thể được chạy lại | Thu thành collection khi cần dùng lại đầu ra |
| Supplier có thể trả cùng một stream mãi mãi | Lượt sau tái sử dụng stream đã tiêu thụ | Cấp stream mới từ nguồn hợp lệ |
| Bọc collection là tạo snapshot | Thay đổi nguồn có thể xuất hiện ở lượt sau | Sao chép tập phần tử nếu cần |
| Wrapper thay thế việc đóng stream tài nguyên | Vòng đời tài nguyên không được kiểm soát | Quản lý tài nguyên tại nơi mở và tiêu thụ |

Các lỗi này đều xuất phát từ việc gán thêm trách nhiệm cho wrapper. Trong service danh bạ, truy vấn quyết định dữ liệu đầu vào; phép nối quyết định thứ tự nguồn; logic gộp quyết định tính duy nhất; mapper quyết định dạng DTO.

## 10. Bài thực hành tự kiểm tra

Dùng bộ dữ liệu nhân sự ở mục 2 để thực hiện lần lượt:

1. Lấy hai kết quả theo phòng `DEV` và tên chứa `an`; ghi lại thứ tự mã của từng nguồn.
2. Nối bằng `and` rồi thu danh sách mã để quan sát phần tử trùng.
3. Lọc `active` và chuyển sang `EmployeeCard`; giải thích vì sao mã 10 vẫn xuất hiện hai lần.
4. Gộp theo `id` với quy tắc giữ lần đầu; đối chiếu kết quả với hai DTO cho mã 10 và 40.
5. Đổi một nhân sự thành cùng tên với người khác; xác định vì sao tên không phù hợp làm khóa loại trùng.
6. Tạo một nguồn không có kết quả bằng `Streamable.empty()`; nối với nguồn còn lại và quan sát kết quả.
7. Duyệt lại một pipeline từ list, rồi so sánh với trường hợp supplier trả cùng một stream.
8. Mô tả cách chuyển điều kiện `active` và việc chọn trường DTO xuống query nếu dự án cần giảm dữ liệu đọc.

Các kết quả nêu trong bài là diễn giải từ dữ liệu giả định, không phải báo cáo chạy kiểm thử. Khi tích hợp với store thực tế, xác nhận kiểu trả về, toán tử truy vấn và yêu cầu giao dịch theo đúng module cùng phiên bản mà dự án sử dụng.