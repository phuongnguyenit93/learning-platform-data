# Mapping trước khi thu thập theo nhóm với Java Stream (Java 8+)

## 1. Bài toán và mục tiêu

Khi phân nhóm dữ liệu bằng **Collectors.groupingBy(...)**, không phải lúc nào dữ liệu nguồn cũng ở đúng dạng cần đưa vào nhóm. Trước khi thu thập, ta có thể phải chuẩn hóa mã, chuyển đối tượng thành một giá trị mới, hoặc chỉ giữ các trường cần thiết.

Có hai cách liên quan nhưng **không cùng ý nghĩa**:

1. **stream.map(mapper).collect(groupingBy(classifier, ...))**: biến đổi từng phần tử của Stream **trước** khi hàm phân nhóm nhận phần tử đó; classifier làm việc trên **giá trị sau mapping**.
2. **stream.collect(groupingBy(classifier, mapping(mapper, downstream)))**: classifier phân nhóm **phần tử đầu vào**, còn **Collectors.mapping** biến đổi những phần tử được chuyển cho collector của **từng nhóm**.

Cả **Stream.map**, **Collectors.groupingBy** và **Collectors.mapping** đều có từ Java 8; đây vẫn là những API được dùng trong Java hiện đại.

Sau bài này, bạn có thể chọn vị trí mapping theo đúng ý nghĩa khóa nhóm, xác định kiểu kết quả Map, tránh mất thông tin nguồn, kết hợp mapping với counting/toList/toSet/summingInt, và xử lý đúng dữ liệu trùng, rỗng, thiếu, thứ tự và parallel stream.

### Ví dụ tình huống

Đầu vào gồm các nhân viên với nhóm **Dev**, **DEV**, **dev**, **Ops**, **ops**. Theo quy tắc nghiệp vụ, các biến thể chữ hoa/chữ thường của cùng tên nhóm phải được gộp chung.

Nếu tạo khóa nhóm trực tiếp từ chuỗi gốc, sẽ có **năm khóa**. Nếu chuẩn hóa **trim() + toUpperCase(Locale.ROOT)** trước khi phân nhóm, ta chỉ còn hai khóa:

~~~text
Dev, DEV, Ops, ops, dev
      |
      v
DEV, DEV, OPS, OPS, DEV
      |
      v
{DEV=3, OPS=2}
~~~

Mapping được đặt đúng vị trí là chìa khóa để giải quyết bài toán này.

## 2. Pipeline hoạt động như thế nào?

Xét một chuỗi các bước:

~~~java
Map<String, Long> counts = employees.stream()
        .map(e -> normalize(e.department()))
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()));
~~~

Đây là mô tả luồng dữ liệu, với **Employee** là kiểu đầu vào:

~~~text
Stream<Employee>
      |
      | map(Employee -> String)
      v
Stream<String>  -- giá trị đã chuẩn hóa
      |
      | collect(groupingBy(String -> String, counting()))
      v
Map<String, Long>
~~~

**map** là *intermediate operation*: mỗi phần tử được chuyển đổi sang một giá trị khác, có thể đổi cả kiểu (**Stream<T> -> Stream<R>**). **collect** là *terminal operation*: nó kích hoạt pipeline và tích lũy kết quả.

Cụm từ "mapping trước khi thu thập" nói về **thứ tự logic** trong pipeline, không có nghĩa Java bắt buộc chạy một lượt để tạo sẵn toàn bộ danh sách đã map rồi mới chạy lượt thứ hai để group. Stream thường xử lý các thao tác trung gian một cách lazy trong quá trình terminal operation thực thi.

Nếu mapper chỉ là ánh xạ **một phần tử thành một phần tử** và không có bước lọc, số phần tử đầu vào cho collect vẫn bằng số phần tử nguồn. Tuy vậy, nhiều phần tử có thể tạo ra **cùng một khóa** sau khi chuẩn hóa, dẫn đến số nhóm nhỏ đi. Nếu sau đó dùng **toSet()**, số giá trị *phân biệt* trong từng nhóm có thể tiếp tục giảm.

## 3. Cách 1 — Stream.map trước Collectors.groupingBy

### 3.1. Chuẩn hóa trước, phân nhóm theo giá trị đã chuẩn hóa

~~~java
List<String> departments =
        Arrays.asList("Dev", "DEV", "Ops", "ops", "dev");

Map<String, Long> counts = departments.stream()
        .map(name -> name.trim().toUpperCase(Locale.ROOT))
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()));

// Nội dung kết quả: DEV=3, OPS=2.
// Thứ tự duyệt các khóa của Map mặc định không được bảo đảm.
~~~

Phân tích:

- **map** biến **"Dev"**, **"DEV"**, **"dev"** thành **"DEV"**.
- **Function.identity()** dùng chính String đã chuẩn hóa làm khóa của nhóm.
- **counting()** đếm số giá trị thuộc từng khóa và trả **Long**, nên kiểu kết quả là **Map<String, Long>**.
- Phân nhóm dựa trên giá trị sau mapping, vì vậy các biến thể của cùng một mã được gộp thành một nhóm.

Nếu muốn nhóm theo **chữ cái đầu** của tên sau khi chuẩn hóa:

~~~java
Map<String, List<String>> byInitial = names.stream()
        .map(name -> name.trim().toUpperCase(Locale.ROOT))
        .collect(Collectors.groupingBy(
                name -> name.substring(0, 1)));
// name trong classifier là String đã biến đổi.
~~~

Trong ví dụ ngắn này, giả định **names** là List<String> chứa các chuỗi không null, không rỗng sau khi trim; nếu không, phải lọc/kiểm tra trước khi gọi substring(0, 1).

### 3.2. Mapping đổi kiểu, nên classifier cũng đổi kiểu đầu vào

~~~java
List<Employee> employees = ...; // Danh sách Employee đã có.

Map<Integer, List<Integer>> salaryBuckets = employees.stream()
        .map(Employee::salary)
        .collect(Collectors.groupingBy(
                salary -> salary / 100));
~~~

Đây là đoạn minh họa giả định Employee có phương thức **salary()**, không phải một chương trình độc lập.

Sau **map(Employee::salary)**, phần tử của pipeline là **Integer**. Hàm classifier **salary -> salary / 100** phân nhóm *các giá trị lương*, không còn nhận một Employee. Kết quả là **Map<Integer, List<Integer>>**.

Nếu ngay sau **map(Employee::salary)** lại viết **groupingBy(Employee::department)**, mã **không biên dịch**, vì classifier cần nhận Employee nhưng phần tử hiện tại đã là Integer. Một khi mapping chỉ giữ lương, thông tin phòng ban ban đầu không còn trong phần tử Stream.

**Quy tắc:** Chỉ map toàn bộ phần tử trước grouping khi khóa nhóm **có thể được tính từ giá trị mới** hoặc bạn chủ động giữ đủ thông tin trong một đối tượng trung gian.

### 3.3. Mapping cả đối tượng trước khi nhóm

Khi phải dùng nhiều trường sau mapping, bạn có thể tạo một đối tượng đã chuẩn hóa rồi phân nhóm theo đối tượng mới:

~~~java
// Ví dụ rút gọn, giả sử Employee có constructor tương ứng.
Map<String, List<Employee>> normalized = employees.stream()
        .map(e -> new Employee(
                normalize(e.department()),
                normalize(e.name()),
                e.salary()))
        .collect(Collectors.groupingBy(Employee::department));
~~~

Điểm cần cân nhắc: mỗi phần tử được tạo một Employee mới, có thêm chi phí cấp phát. Không cần làm vậy nếu mục tiêu chỉ là dùng khóa chuẩn hóa và trích xuất một trường; khi đó **classifier chuẩn hóa + downstream mapping** thường diễn đạt ý định gọn hơn.

## 4. Cách 2 — Mapping ở downstream collector của groupingBy

Dạng tổng quát:

~~~java
Collectors.groupingBy(
        classifier,
        Collectors.mapping(mapper, downstreamCollector)
)
~~~

Đây là *cascaded reduction*: trước tiên mỗi phần tử được **phân loại vào nhóm theo classifier**, sau đó **mapper** chuyển đổi giá trị gửi cho **downstreamCollector** của nhóm đó.

Ví dụ: nhóm nhân viên theo phòng ban gốc, nhưng trong từng nhóm chỉ giữ **tên viết hoa**:

~~~java
Map<String, List<String>> namesByRawDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        e -> normalize(e.name()),
                        Collectors.toList())));
~~~

Ở đây:

- **classifier** nhìn thấy **Employee**, nên khóa là **e.department()** ban đầu.
- **mapper** trong **Collectors.mapping** cũng nhận **Employee** và tạo **String** là tên đã chuẩn hóa.
- **toList()** thu String vào danh sách của từng khóa.
- Kiểu Map cuối là **Map<String, List<String>>**, không phải **Map<String, List<Employee>>**.

**Điểm quan trọng:** **Collectors.mapping** chỉ thay đổi giá trị chuyển vào downstream collector; nó **không tự chuẩn hóa khóa nhóm**. Nếu classifier là **Employee::department**, thì **"Dev"**, **"DEV"** và **"dev"** vẫn là các khóa khác nhau.

### 4.1. Cần chuẩn hóa cả khóa lẫn giá trị?

Chỉ cần chuẩn hóa trong **classifier** và **downstream mapping**:

~~~java
Map<String, List<String>> namesByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                e -> normalize(e.department()),
                Collectors.mapping(
                        e -> normalize(e.name()),
                        Collectors.toList())));
~~~

Lần này classifier tạo khóa **DEV** hoặc **OPS**; downstream tạo danh sách tên đã chuẩn hóa. Dữ liệu Employee vẫn có sẵn ở cả hai hàm, không cần dựng đối tượng mới.

### 4.2. Chỉ cần khóa chuẩn hóa, vẫn giữ toàn bộ Employee?

Nếu muốn Map nhóm theo mã chuẩn hóa nhưng giữ **toàn bộ đối tượng** trong từng List, không cần **Collectors.mapping**:

~~~java
Map<String, List<Employee>> employeesByDepartment =
        employees.stream().collect(Collectors.groupingBy(
                e -> normalize(e.department())));
~~~

Đây là một trường hợp quan trọng: **không phải mọi bài toán phân nhóm đều cần mapping**. Chọn cấu trúc đơn giản nhất thỏa hợp đồng dữ liệu.

## 5. So sánh vị trí mapping bằng cùng một bộ dữ liệu

Giả sử năm nhân viên có các phòng ban như sau:

| Nhân viên | Phòng ban thô | Tên đã chuẩn hóa |
| --- | --- | --- |
| An | Dev | AN |
| Binh | DEV | BINH |
| Chi | Ops | CHI |
| Dung | ops | DUNG |
| An | dev | AN |

| Pipeline | Khóa nhóm dựa trên | Giá trị trong nhóm | Kiểu kết quả |
| --- | --- | --- | --- |
| map(department chuẩn hóa) -> groupingBy(identity, counting) | String sau map | Số lượng | Map<String, Long> |
| groupingBy(Employee::department, mapping(name, toList)) | Employee ban đầu | Tên đã map | Map<String, List<String>> |
| groupingBy(department chuẩn hóa, mapping(name, toList)) | Employee ban đầu qua classifier chuẩn hóa | Tên đã map | Map<String, List<String>> |
| groupingBy(department chuẩn hóa) | Employee ban đầu qua classifier chuẩn hóa | Employee gốc | Map<String, List<Employee>> |
| map(name chuẩn hóa) -> groupingBy(chữ đầu tên) | String sau map | Tên đã map | Map<String, List<String>> |

Chọn **Stream.map trước groupingBy** khi bản thân **đơn vị dữ liệu cần nhóm** đã đổi từ T sang R và toàn bộ công đoạn phân nhóm chỉ cần R. Chọn **groupingBy(..., mapping(...))** khi khóa cần được tính từ T nhưng giá trị cuối ở từng nhóm chỉ cần dạng rút gọn R.

Hai cách đôi khi có thể cho dữ liệu nhìn tương tự, nhưng **không thể hoán đổi máy móc** vì khác kiểu đầu vào của classifier và thông tin còn giữ lại.

## 6. Ví dụ chạy được: chuẩn hóa, nhóm, đếm, khử trùng và tổng hợp

Ví dụ sau chỉ dùng các API đã có trong Java 8, đồng thời biên dịch và chạy được trên Java 17+ hiện hành. Tạo tệp **MappingGroupingDemo.java**:

~~~java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class MappingGroupingDemo {
    static final class Employee {
        final String department;
        final String name;
        final int salary;

        Employee(String department, String name, int salary) {
            this.department = department;
            this.name = name;
            this.salary = salary;
        }

        String department() { return department; }
        String name() { return name; }
        int salary() { return salary; }
    }

    static String normalize(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<Employee> people = Arrays.asList(
                new Employee("Dev", " An ", 100),
                new Employee("DEV", "Binh", 150),
                new Employee("Ops", "Chi", 90),
                new Employee("ops", "Dung", 120),
                new Employee("dev", "An", 110));

        Map<String, Long> counts = people.stream()
                .map(e -> normalize(e.department()))
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        LinkedHashMap::new,
                        Collectors.counting()));

        Map<String, List<String>> rawKeys = people.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                e -> normalize(e.name()),
                                Collectors.toList())));

        Map<String, List<String>> groupedNames = people.stream()
                .collect(Collectors.groupingBy(
                        e -> normalize(e.department()),
                        LinkedHashMap::new,
                        Collectors.mapping(
                                e -> normalize(e.name()),
                                Collectors.toList())));

        Map<String, Set<String>> distinctNames = people.stream()
                .collect(Collectors.groupingBy(
                        e -> normalize(e.department()),
                        LinkedHashMap::new,
                        Collectors.mapping(
                                e -> normalize(e.name()),
                                Collectors.toCollection(LinkedHashSet::new))));

        Map<String, Integer> salaries = people.stream()
                .collect(Collectors.groupingBy(
                        e -> normalize(e.department()),
                        LinkedHashMap::new,
                        Collectors.summingInt(Employee::salary)));

        Map<String, List<String>> initials = people.stream()
                .map(e -> normalize(e.name()))
                .collect(Collectors.groupingBy(
                        name -> name.substring(0, 1),
                        LinkedHashMap::new,
                        Collectors.toList()));

        System.out.println("counts: " + counts);
        System.out.println("raw keys: " + rawKeys);
        System.out.println("grouped names: " + groupedNames);
        System.out.println("distinct names: " + distinctNames);
        System.out.println("salaries: " + salaries);
        System.out.println("initials: " + initials);
    }
}
~~~

Lệnh chạy:

~~~bash
javac MappingGroupingDemo.java
java MappingGroupingDemo
~~~

Đầu ra chính xác:

~~~text
counts: {DEV=3, OPS=2}
raw keys: {Dev=[AN], DEV=[BINH], Ops=[CHI], ops=[DUNG], dev=[AN]}
grouped names: {DEV=[AN, BINH, AN], OPS=[CHI, DUNG]}
distinct names: {DEV=[AN, BINH], OPS=[CHI, DUNG]}
salaries: {DEV=360, OPS=210}
initials: {A=[AN, AN], B=[BINH], C=[CHI], D=[DUNG]}
~~~

Giải thích từng kết quả:

1. **counts** dùng **Stream.map(...) trước collect**: chuẩn hóa phòng ban thành **DEV/OPS** rồi **groupingBy(identity, counting)**. Ba người thuộc DEV, hai người thuộc OPS.
2. **rawKeys** dùng **downstream mapping** cho tên, nhưng classifier vẫn là **Employee::department**. Vì thế các khóa **Dev**, **DEV**, **dev**, **Ops**, **ops** không gộp lại.
3. **groupedNames** chuẩn hóa tại classifier và downstream mapping, nên cả khóa lẫn tên trong danh sách đều thống nhất.
4. **distinctNames** giống groupedNames, nhưng dùng **toCollection(LinkedHashSet::new)** nên hai giá trị **AN** trong DEV chỉ còn một. Set duy trì thứ tự chèn trong lần chạy tuần tự này.
5. **salaries** là phép tổng hợp theo nhóm: DEV = **100 + 150 + 110 = 360**, OPS = **90 + 120 = 210**. **summingInt** phù hợp hơn việc tạo danh sách lương rồi tự tính tổng.
6. **initials** minh họa sau **map(Employee -> String)**, classifier thấy **tên đã chuẩn hóa**, nên nhóm theo chữ đầu của tên; thông tin phòng ban không còn trong phần tử Stream.

Trong chương trình này, **LinkedHashMap::new** được cung cấp rõ để việc in thứ tự khóa của Stream tuần tự có thứ tự dễ kiểm chứng: khóa được gặp lần đầu theo thứ tự DEV rồi OPS. **LinkedHashSet::new** giữ thứ tự giá trị phân biệt; đây là chủ đích của ví dụ, không phải đặc tính tự động của **groupingBy** mặc định.

## 7. Kết hợp mapping với các downstream collector khác

**Collectors.mapping(mapper, downstream)** không chỉ dùng với **toList()**. Nó nhận một collector bất kỳ phù hợp với kiểu dữ liệu sau mapping.

| Mục tiêu | Downstream thích hợp | Kết quả mỗi nhóm |
| --- | --- | --- |
| Giữ các tên đã biến đổi, kể cả trùng | mapping(nameMapper, toList()) | List<String> |
| Giữ tên không trùng, không cần thứ tự | mapping(nameMapper, toSet()) | Set<String> |
| Giữ tên không trùng và thứ tự chèn | mapping(nameMapper, toCollection(LinkedHashSet::new)) | Set<String> có thứ tự chèn |
| Số phần tử trong nhóm | counting() | Long |
| Tổng giá trị số | summingInt(Employee::salary) | Integer |
| Tổng hợp min/max/avg/count | summarizingInt(Employee::salary) | IntSummaryStatistics |

Hai trường hợp **counting()** và **summingInt(...)** không cần lồng thêm **mapping()** nếu mục tiêu chỉ là đếm hoặc tổng số nguyên. **summingInt** nhận trực tiếp hàm chuyển Employee thành int. Điều này tránh tạo đối tượng trung gian không cần thiết.

Nếu muốn giữ điểm số đã làm tròn/phân loại thành nhãn trước khi nhóm, downstream mapping có thể kết hợp với **toList** hoặc **toSet** để thu thập nhãn, miễn mapper biểu diễn rõ quy tắc nghiệp vụ.

### 7.1. Trùng lặp: phân biệt count với distinct count

Dữ liệu tên đã chuẩn hóa của DEV là **[AN, BINH, AN]**.

- **mapping(nameMapper, toList())** trả ba mục, giữ hai lần **AN**.
- **mapping(nameMapper, toSet())** trả hai giá trị phân biệt nhưng không bảo đảm thứ tự duyệt Set.
- **mapping(nameMapper, toCollection(LinkedHashSet::new))** trả hai giá trị phân biệt theo thứ tự chèn của Stream tuần tự có thứ tự.
- **counting()** trả **3**, vì đếm nhân viên; nó không tự chuyển thành số lượng tên phân biệt.

Nếu yêu cầu **đếm tên khác nhau trong mỗi phòng**, đừng dùng counting() trực tiếp trên nhân viên. Có thể thu thập một Set tên đã chuẩn hóa ở mỗi nhóm, rồi lấy **size()** của Set, hoặc dùng một collector có finisher phù hợp với bài toán. Cân nhắc chi phí lưu Set cho mỗi nhóm nếu dữ liệu rất lớn.

### 7.2. Tách biệt xác định khóa và biến đổi giá trị

Ví dụ muốn gộp các phòng ban bằng mã chuẩn hóa, nhưng danh sách cuối phải chứa **tên như dữ liệu gốc**:

~~~java
Map<String, List<String>> originalNames = people.stream()
        .collect(Collectors.groupingBy(
                e -> normalize(e.department()),
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList())));
~~~

Kết quả DEV có thể chứa **" An "**, **"Binh"**, **"An"** theo đúng dữ liệu nguồn. Đây không phải lỗi; mapper chỉ **Employee::name**, không gọi normalize. Điều này minh họa nguyên tắc: **hàm tạo khóa và hàm biến đổi giá trị là hai quyết định độc lập**.

## 8. Cẩn thận thứ tự và loại Map kết quả

**Collectors.groupingBy(classifier)** không bảo đảm kiểu Map cụ thể, thứ tự duyệt khóa, khả năng sửa đổi, thread safety hay tính tuần tự hóa của Map/List trả về. Nếu cần một đặc tính cụ thể, hãy yêu cầu nó bằng **mapFactory** và downstream collector tương ứng.

### Muốn khóa theo thứ tự chữ cái

~~~java
Map<String, List<String>> alphabetical = people.stream()
        .collect(Collectors.groupingBy(
                e -> normalize(e.department()),
                TreeMap::new,
                Collectors.mapping(
                        e -> normalize(e.name()),
                        Collectors.toList())));
~~~

**TreeMap** sắp xếp khóa theo thứ tự tự nhiên của String. Khác với **LinkedHashMap**, nó không giữ "gặp khóa nào trước thì in khóa đó trước".

### Muốn giữ thứ tự xuất hiện của khóa trong luồng tuần tự

~~~java
Map<String, List<String>> insertionOrder = people.stream()
        .collect(Collectors.groupingBy(
                e -> normalize(e.department()),
                LinkedHashMap::new,
                Collectors.mapping(
                        e -> normalize(e.name()),
                        Collectors.toList())));
~~~

Với **people.stream()** từ List có thứ tự và cách thực thi tuần tự trong ví dụ, khóa đầu tiên xuất hiện là DEV, tiếp theo là OPS; LinkedHashMap duyệt theo thứ tự chèn. Nếu chuyển sang một nguồn không có encounter order, không được tự suy ra thứ tự nhóm ổn định.

Lưu ý thêm: **Map là ánh xạ từ một khóa sang một kết quả nhóm**. Hai giá trị khóa **equals** nhau sẽ rơi vào cùng một nhóm. Với String, **"Dev"** và **"DEV"** khác nhau trừ khi bạn chủ động normalize; nếu dùng khóa là object tự tạo, cần triển khai **equals/hashCode** ổn định, nhất quán và tránh sửa object khóa sau khi đưa vào Map.

## 9. Sai lầm thường gặp: mất dữ liệu, nhầm kiểu và null

### 9.1. Map quá sớm làm mất trường để phân nhóm

~~~java
// Sau map chỉ còn String. Không thể lấy department từ String.
employees.stream()
        .map(Employee::name)
        // .collect(Collectors.groupingBy(Employee::department)); // Không biên dịch
        .collect(Collectors.toList());
~~~

Sửa bằng cách **groupingBy(Employee::department, mapping(Employee::name, toList()))**, hoặc ánh xạ sang đối tượng mới vẫn giữ đủ trường khóa và giá trị.

### 9.2. Nhầm downstream mapping với chuẩn hóa khóa

~~~java
// Khóa vẫn là giá trị department gốc, không tự thành DEV/OPS.
Map<String, List<String>> incorrectForNormalizedKeys =
        employees.stream().collect(
                Collectors.groupingBy(
                        Employee::department,
                        Collectors.mapping(
                                e -> normalize(e.name()),
                                Collectors.toList())));
~~~

Đoạn này hoàn toàn hợp lệ về kỹ thuật; nó chỉ **sai yêu cầu nghiệp vụ nếu cần nhóm theo khóa đã chuẩn hóa**. Cách sửa là chuẩn hóa **classifier**.

### 9.3. Dữ liệu null hoặc chuỗi rỗng

~~~java
// Bước tiền xử lý khi nguồn có thể chứa record thiếu department:
List<Employee> valid = employees.stream()
        .filter(e -> e != null
                && e.department() != null
                && !e.department().trim().isEmpty())
        .collect(Collectors.toList());
~~~

Đoạn minh họa áp dụng cho Employee có **department()** như ví dụ. **normalize** dùng **trim()**, nên sẽ ném **NullPointerException** nếu đầu vào null. Các triển khai **groupingBy** chuẩn trên JDK cũng không cho classifier tạo **khóa null**; tránh phụ thuộc vào null key.

Nếu null mang ý nghĩa hợp lệ trong miền dữ liệu, hãy định nghĩa quy tắc rõ ràng: bỏ bản ghi thiếu khóa, dùng một khóa thay thế như **"UNKNOWN"**, hoặc báo lỗi xác thực đầu vào. Không âm thầm gộp mọi giá trị lỗi vào một nhóm nếu điều đó làm sai nghiệp vụ.

Với những hệ thống xử lý Unicode, **String.strip()** (có từ Java 11) có khả năng nhận diện khoảng trắng Unicode tốt hơn **trim()** trong một số trường hợp; chọn quy tắc chuẩn hóa theo đặc tả dữ liệu. Dù dùng trim hay strip, nếu mã nhóm có chữ hoa/chữ thường, truyền **Locale.ROOT** vào **toUpperCase(...)** để tránh kết quả phụ thuộc locale mặc định của máy. Không tự giả định chuyển chữ hoa đơn giản giải quyết mọi bài toán chuẩn hóa Unicode.

### 9.4. Biến đổi có side effect

~~~java
// Không nên ghi vào List dùng chung như tác dụng phụ của map:
List<String> globalNames = new ArrayList<>();

List<String> result = employees.parallelStream()
        .map(e -> {
            String name = normalize(e.name());
            globalNames.add(name); // Sai: shared mutable state / data race
            return name;
        })
        .collect(Collectors.toList());
~~~

Lỗi nằm ở **globalNames.add(name)**, không phải ở việc biến đổi String. Mapper dùng trong Stream nên **non-interfering** (không sửa nguồn) và **stateless** (không phụ thuộc trạng thái thay đổi). Hãy trả về giá trị từ mapper và để Collector quản lý việc thu thập.

### 9.5. Nhầm groupingBy với toMap

**groupingBy** được thiết kế cho **nhiều phần tử cùng một khóa** và gom giá trị theo từng nhóm. **toMap(keyMapper, valueMapper)** không có merge function có thể ném **IllegalStateException** khi hai phần tử tạo cùng khóa. Nếu kết quả cần nhiều Employee dưới một phòng ban, hãy chọn groupingBy; nếu cần một giá trị duy nhất mỗi khóa, phải xác định quy tắc gộp xung đột khi dùng toMap.

## 10. Filter nên nằm ở đâu so với mapping và grouping?

Vị trí của **filter** quyết định điều gì được giữ lại. Khi điều kiện lọc yêu cầu giá trị đã chuẩn hóa, có thể **map -> filter -> groupingBy**, miễn việc map đã giữ đủ thông tin cần cho classifier.

~~~java
List<String> tags = Arrays.asList(" api ", "", "API", "web");

Map<String, Long> normalizedCounts = tags.stream()
        .map(tag -> tag.trim().toUpperCase(Locale.ROOT))
        .filter(tag -> !tag.isEmpty())
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()));
// Nội dung: API=2, WEB=1.
~~~

Nếu cần lọc theo một trường của Employee **và** vẫn phân nhóm bằng một trường khác, có thể **filter Employee trước**, rồi **groupingBy** và downstream **mapping**. Đừng map thành String tên rồi mới cố đọc salary hoặc department.

### So sánh với Collectors.filtering (Java 9+)

Đây là kiến thức đang áp dụng trong JDK hiện đại nhưng **Collectors.filtering** được thêm từ Java 9, nên ví dụ sau yêu cầu Java 9+:

~~~java
Map<String, List<String>> highPaidByDepartment =
        people.stream().collect(Collectors.groupingBy(
                e -> normalize(e.department()),
                LinkedHashMap::new,
                Collectors.filtering(
                        e -> e.salary() >= 130,
                        Collectors.mapping(
                                e -> normalize(e.name()),
                                Collectors.toList()))));
~~~

Với dữ liệu demo, kết quả là **{DEV=[BINH], OPS=[]}**. Nhóm OPS vẫn có nhân viên đầu vào, nhưng tất cả bị loại bởi **filtering** downstream nên danh sách của nhóm là rỗng.

Nếu chuyển điều kiện đó thành **people.stream().filter(e -> e.salary() >= 130).collect(groupingBy(...))**, nhóm OPS **không xuất hiện** vì không có phần tử nào đủ điều kiện đi tới classifier.

Đây là khác biệt có ý nghĩa khi báo cáo phải thể hiện một nhóm có **0 kết quả** nhưng **vẫn có bản ghi đầu vào**. Không cần dùng filtering downstream nếu yêu cầu chỉ lấy các nhóm có phần tử đạt điều kiện.

## 11. Mapping khác flatMapping

**map** biến một phần tử thành **một giá trị kết quả**; nếu giá trị đó là **List<String>**, thì mỗi phần tử Stream mới là cả List, không tự dàn phẳng các phần tử trong List.

**flatMap** biến một phần tử thành một Stream các phần tử con, sau đó trải các Stream con thành một Stream chung. Nếu một Employee có nhiều tag, flatMap cho phép nhóm từng tag khi đơn vị cần nhóm là tag, nhưng có thể làm mất thông tin Employee nếu chỉ giữ tag.

Đối với downstream collector, Java 9+ có **Collectors.flatMapping(...)** cho phép duy trì classifier dựa trên Employee ban đầu rồi đưa **nhiều giá trị con** vào nhóm. Đây là công cụ hiện đại hữu ích khi đầu ra cần toàn bộ kỹ năng/tag/sản phẩm gắn với mỗi phần tử.

Hãy chọn:

- **map trước groupingBy** khi cần thay đổi bản thân phần tử được phân nhóm.
- **mapping downstream** khi mỗi phần tử thuộc một nhóm tạo ra một giá trị downstream.
- **flatMap trước groupingBy** khi đơn vị cần nhóm là từng phần tử con đã được trải phẳng.
- **flatMapping downstream** khi khóa nhóm dựa trên phần tử cha, nhưng mỗi phần tử cha đóng góp nhiều giá trị con.

Đừng dùng flatMap nếu bài toán chỉ cần **một giá trị cho mỗi Employee**; nó khiến kiểu dữ liệu và lượng phần tử khó theo dõi hơn.

## 12. Parallel stream và hiệu suất

Có thể kết hợp các toán tử đã học với **parallelStream()**, nhưng phải bảo đảm mapper, classifier và downstream collector thực hiện đúng hợp đồng.

- **map**, **mapping** và **classifier** nên là hàm thuần: cùng đầu vào cho cùng kết quả, không ghi biến dùng chung và không sửa dữ liệu nguồn.
- **groupingBy(...)** mặc định không phải concurrent collector; khi chạy song song, quá trình kết hợp các Map cục bộ có thể tốn chi phí.
- **groupingByConcurrent(...)** có thể hữu ích khi không cần bảo toàn thứ tự của các phần tử thuộc mỗi nhóm; bản thân nó là **concurrent, unordered collector**. Đừng chọn nó nếu thứ tự danh sách trong nhóm là yêu cầu nghiệp vụ.
- Việc thêm một **map** để dựng đối tượng trung gian có thể tạo áp lực cấp phát; khi chỉ cần chuẩn hóa classifier và trích một thuộc tính, downstream mapping có thể giảm khối lượng đối tượng mới.
- **parallel()** không mặc nhiên nhanh: hiệu quả phụ thuộc số lượng phần tử, chi phí chuẩn hóa, phân bố khóa, chi phí gộp và hạ tầng thực thi. Hãy benchmark với dữ liệu đại diện trước khi quyết định.

Ví dụ demo dùng **stream() tuần tự** và mapFactory **LinkedHashMap::new** để kết quả in có thứ tự dễ đọc. Nếu chuyển sang song song, không lấy thứ tự gọi lambda hoặc thứ tự tạo/ghép Map cục bộ làm giả định nghiệp vụ.

## 13. Quy trình chọn giải pháp trong dự án

**Bước 1 — Xác định khóa nhóm.** Đầu vào cần nhóm theo department thô, department đã chuẩn hóa, ký tự đầu của name hay một thuộc tính khác? Khóa phải ổn định và có quy tắc equals/hashCode phù hợp.

**Bước 2 — Xác định phần tử giữ trong từng nhóm.** Cần Employee gốc, chỉ name, Set tên không trùng, số lượng, tổng lương, hay số liệu thống kê? Trả lời rõ để chọn downstream collector.

**Bước 3 — Xác định thông tin được phép mất.** Nếu map Employee thành String name trước, bạn có còn cần department hay salary nữa không? Nếu còn, giữ Employee qua classifier hoặc tạo đối tượng trung gian có đủ trường.

**Bước 4 — Xác định cách chuẩn hóa và dữ liệu thiếu.** Định nghĩa chính xác trim/strip, viết hoa, mã mặc định, cách xử lý null/rỗng, và trường hợp các khóa khác nhau trở thành cùng một khóa.

**Bước 5 — Xác định yêu cầu thứ tự và khử trùng.** Nếu cần thứ tự khóa, dùng TreeMap/LinkedHashMap theo ý nghĩa. Nếu cần thứ tự giá trị phân biệt, dùng toCollection(LinkedHashSet::new) với nguồn ordered và xử lý tuần tự khi thứ tự đó quan trọng.

**Bước 6 — Kiểm tra với bộ dữ liệu đại diện.** Bao gồm ít nhất hai khóa trùng sau normalize, nhiều bản ghi một nhóm, tên trùng, nhóm có một phần tử, đầu vào rỗng và bản ghi thiếu trường nếu có thể xảy ra. So sánh kết quả với yêu cầu nghiệp vụ, không chỉ với kiểu trả về.

**Bước 7 — Đơn giản hóa.** Nếu chỉ cần count, sum hoặc average theo nhóm, dùng counting/summingInt/averagingInt. Không tạo danh sách hoặc đối tượng trung gian không cần thiết chỉ để tính một con số.

## 14. Luyện tập và lời giải

### Câu 1 — Chỗ nào tạo khóa nhóm?

~~~java
Map<String, List<String>> result = employees.stream()
        .map(Employee::name)
        .collect(Collectors.groupingBy(
                name -> name.substring(0, 1)));
~~~

**Lời giải:** Classifier nhận **String name**, không nhận Employee. Khóa là chữ đầu của tên **chưa chuẩn hóa**; các chữ cái hoa/thường có thể trở thành khóa khác nhau. Nếu muốn chuẩn hóa trước, chèn **map(name -> normalize(name))** trước groupingBy.

### Câu 2 — Nhóm theo phòng ban, chỉ giữ tên đã chuẩn hóa

**Lời giải:**

~~~java
Map<String, List<String>> result = employees.stream()
        .collect(Collectors.groupingBy(
                e -> normalize(e.department()),
                Collectors.mapping(
                        e -> normalize(e.name()),
                        Collectors.toList())));
~~~

Classifier và mapping đều nhận Employee. Không phải dựng đối tượng Employee mới, và không làm mất phòng ban trước khi group.

### Câu 3 — Tại sao DEV có ba tên nhưng Set chỉ còn hai?

**Lời giải:** Dữ liệu gốc có hai nhân viên tên An; sau chuẩn hóa đều thành **AN**. **toList** giữ đủ ba giá trị [AN, BINH, AN], còn **toSet** / **LinkedHashSet** giữ các giá trị phân biệt [AN, BINH]. Đây là hành vi khử trùng, không phải mất một bản ghi do map.

### Câu 4 — Sau mapping, vì sao đoạn sau sai kiểu?

~~~java
employees.stream()
        .map(Employee::salary)
        // .collect(Collectors.groupingBy(Employee::department));
        .collect(Collectors.toList());
~~~

**Lời giải:** Kiểu phần tử sau map là Integer. Classifier dùng phương thức của Employee không phù hợp. Nếu muốn nhóm lương theo department:

~~~java
Map<String, List<Integer>> result = employees.stream()
        .collect(Collectors.groupingBy(
                e -> normalize(e.department()),
                Collectors.mapping(
                        Employee::salary,
                        Collectors.toList())));
~~~

### Câu 5 — Cần đếm số nhân viên mỗi phòng; có cần mapping không?

**Lời giải:** Không. Dùng trực tiếp **groupingBy(classifier, counting())**:

~~~java
Map<String, Long> counts = employees.stream()
        .collect(Collectors.groupingBy(
                e -> normalize(e.department()),
                Collectors.counting()));
~~~

Chỉ cần đưa **map** ra trước groupingBy nếu bản thân Stream sẽ được dùng dưới dạng đã biến đổi cho các bước tiếp theo.

## 15. Những điều cần nhớ

1. **Stream.map(...) trước collect** biến đổi phần tử của toàn pipeline; **groupingBy** sẽ nhận giá trị đã map.
2. **Collectors.mapping(...) bên trong groupingBy** chỉ biến đổi giá trị chuyển xuống downstream collector; **khóa nhóm vẫn do classifier quyết định**.
3. Nếu classifier cần thông tin của Employee, đừng map Employee thành String/Integer rồi đánh mất thông tin ấy trước khi group.
4. Chuẩn hóa khóa trong classifier khi cần gộp các biến thể của cùng mã; chuẩn hóa giá trị trong downstream mapper khi cần định dạng khác để lưu vào nhóm.
5. **counting/summingInt/summarizingInt** làm việc trực tiếp trên từng nhóm; **toList/toSet/LinkedHashSet** có quy tắc riêng về giữ trùng và thứ tự.
6. Làm rõ null, chuỗi rỗng, collision giữa khóa sau normalize, hàm có side effect và thứ tự của Map. Dùng **mapFactory** khi kiểu/thứ tự Map cần được xác định.
7. Pipeline cần thiết kế theo **ý nghĩa khóa và giá trị**, không chỉ vì hai đoạn code đều trả về Map; hãy thử dữ liệu có khóa tương đương nhưng khác cách viết.

### Tài liệu Java chính thức còn áp dụng

- **Stream.map** và quy tắc non-interference/stateless: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- **Collectors.groupingBy**, **Collectors.mapping**, **Collectors.counting**, **Collectors.summingInt**, **Collectors.filtering**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
- **Stream package summary** về intermediate operation, parallelism, encounter order, collection: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
