# `Comparator<T>`: định nghĩa thứ tự bên ngoài lớp

## 1. Vì sao cần một thứ tự từ bên ngoài?

Trong Java, có những lớp mà đối tượng có thể được sắp xếp theo **nhiều tiêu chí hợp lệ**. Ví dụ, một nhân viên có mã định danh, tên và tuổi. Danh sách nhân viên có thể cần hiển thị theo tuổi tăng dần, theo tên theo bảng chữ cái hoặc theo mã nhân viên. Không có lý do nào buộc một trong các tiêu chí phải được mã hóa cố định vào chính lớp `Employee`.

`java.util.Comparator<T>` giải quyết nhu cầu đó: nó mô tả **một chiến lược so sánh hai đối tượng kiểu `T` ở bên ngoài lớp dữ liệu**. Ta có thể tạo nhiều comparator, chọn comparator tại nơi cần sử dụng và không phải thay đổi mã nguồn của `Employee`.

```java
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);

Comparator<Employee> byName =
        Comparator.comparing(Employee::name);
```

Hai câu lệnh là **fragment minh họa**, cần import `java.util.Comparator` và một kiểu `Employee` có accessor `age()`/`name()`. Trong phần chương trình hoàn chỉnh bên dưới sẽ có lớp dữ liệu cụ thể và ví dụ chạy được.

Với một comparator hợp lệ, phép `compare(a, b)` trả:

| Kết quả | Ý nghĩa |
| --- | --- |
| Số âm | `a` đứng **trước** `b` |
| `0` | `a` và `b` **tương đương về thứ tự** theo comparator |
| Số dương | `a` đứng **sau** `b` |

Giá trị `-1` hay `1` chỉ là các trường hợp có thể có. **Hợp đồng yêu cầu dấu**, không yêu cầu luôn trả đúng `-1, 0, 1`.

## 2. Phân biệt `Comparator`, `Comparable` và `equals()`

| API | Người định nghĩa thứ tự | Nghiệp vụ phù hợp |
| --- | --- | --- |
| `Comparable<T>` với `compareTo(T)` | **Bên trong lớp** triển khai `Comparable` | Một thứ tự tự nhiên, mặc định và ổn định cho kiểu |
| `Comparator<T>` với `compare(T, T)` | **Bên ngoài lớp**, qua object/lambda/method reference | Nhiều thứ tự, hoặc kiểu dữ liệu không thể/chưa muốn sửa |
| `Object.equals(Object)` | Bên trong lớp (hoặc kế thừa) | Xác định hai đối tượng **bằng nhau về bản sắc logic** |

`Comparable` là lựa chọn thích hợp khi có một thứ tự tự nhiên rõ ràng, ví dụ `String` so theo thứ tự từ điển, `Integer` so theo giá trị số. Ngược lại, `Comparator` phù hợp khi cần sắp xếp `Employee` theo tuổi hôm nay và theo tên ngày mai, hoặc khi thư viện cung cấp lớp `final` không thể chỉnh sửa.

**`compare(a, b) == 0` không tự động đồng nghĩa `a.equals(b)`.** Comparator có thể coi hai nhân viên cùng tuổi là tương đương **về thứ tự tuổi** mặc dù họ có mã định danh khác nhau. Việc này thường chấp nhận được khi chỉ sắp xếp một danh sách; nhưng cần chú ý với các cấu trúc sử dụng comparator để nhận diện khóa như `TreeSet` và `TreeMap`.

Một comparator không thay đổi `equals()` hoặc `hashCode()` của đối tượng. Nó chỉ cung cấp một quan hệ thứ tự được chọn trong lúc thao tác.

## 3. Cách tạo comparator không phải viết lớp riêng

Từ Java 8, `Comparator` là **functional interface**: phương thức trừu tượng chính là `int compare(T o1, T o2)`. Vì vậy có thể dùng lambda hoặc method reference.

### Viết bằng lambda

```java
Comparator<Employee> byAge =
        (left, right) -> Integer.compare(left.age(), right.age());
```

`Integer.compare` được ưu tiên so với `left.age() - right.age()`: phép trừ hai số nguyên có thể **tràn số**, gây kết quả thứ tự sai. Ví dụ `Integer.MAX_VALUE - (-1)` vượt phạm vi `int`.

### Viết bằng factory method

```java
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);

Comparator<Employee> byId =
        Comparator.comparingInt(Employee::id);

Comparator<Employee> byName =
        Comparator.comparing(Employee::name);
```

Các comparator này cùng có kiểu `Comparator<Employee>`, nhưng mỗi cái dùng **một khóa sắp xếp khác nhau**. `comparingInt` tránh boxing khóa `int` thành `Integer` để so sánh. Các phương thức tương tự gồm `comparingLong`, `comparingDouble`; dùng `comparing` cho khóa đối tượng như `String`.

Nếu khóa không phải kiểu có thứ tự tự nhiên phù hợp, truyền thêm comparator của khóa:

```java
Comparator<Employee> byNameIgnoringCase =
        Comparator.comparing(
                Employee::name,
                String.CASE_INSENSITIVE_ORDER);
```

Đoạn này giả định tên không null. Nếu tên có thể null, cần chỉ rõ quy tắc đặt null trước/sau hoặc bỏ qua bản ghi không hợp lệ.

### Kết hợp nhiều khóa bằng `thenComparing`

Sắp xếp theo tuổi tăng dần, **nếu bằng tuổi thì theo mã tăng dần**:

```java
Comparator<Employee> byAgeThenId =
        Comparator.comparingInt(Employee::age)
                  .thenComparingInt(Employee::id);
```

Khi hai người cùng tuổi, comparator không trả ngay `0` mà dùng mã để quyết định. Nếu mã là **duy nhất** và định nghĩa bản sắc logic của `Employee`, so sánh cuối theo mã giúp tránh coi hai người khác nhau là cùng phần tử trong `TreeSet`.

Tuy nhiên, thêm tie-breaker chỉ đúng nếu khóa cuối nhất quán với chính sách bằng nhau của lớp. Nếu một lớp có `equals()` dựa trên nhiều trường, hãy hiểu rõ các trường đó trước khi kỳ vọng `compare(a,b)==0` tương đương `equals()`.

### Đảo thứ tự bằng `reversed()`

```java
Comparator<Employee> descendingAgeThenId =
        byAgeThenId.reversed();
```

`reversed()` đảo **toàn bộ** thứ tự, bao gồm cả khóa phụ: tuổi giảm dần, nếu cùng tuổi thì mã cũng giảm dần. Nếu muốn *tuổi giảm dần nhưng mã tăng dần*, hãy đảo comparator tuổi **trước** khi thêm khóa phụ:

```java
Comparator<Employee> ageDescendingIdAscending =
        Comparator.comparingInt(Employee::age)
                  .reversed()
                  .thenComparingInt(Employee::id);
```

Hai chiến lược khác nhau về kết quả khi có người cùng tuổi.

## 4. Chương trình Java 17 chạy được

Tạo tệp `ExternalComparatorDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ExternalComparatorDemo {

    // Record chỉ giữ dữ liệu; không implements Comparable.
    record Employee(int id, String name, int age) {}

    static List<Integer> ids(List<Employee> employees) {
        return employees.stream()
                .map(e -> e == null ? -1 : e.id())
                .toList();
    }

    public static void main(String[] args) {
        Employee alice = new Employee(2, "Alice", 30);
        Employee bao = new Employee(1, "Bao", 25);
        Employee chi = new Employee(3, "Chi", 25);

        List<Employee> original = List.of(alice, bao, chi);

        Comparator<Employee> byAgeThenId =
                Comparator.comparingInt(Employee::age)
                          .thenComparingInt(Employee::id);

        Comparator<Employee> byNameThenId =
                Comparator.comparing(
                        Employee::name,
                        String.CASE_INSENSITIVE_ORDER)
                          .thenComparingInt(Employee::id);

        List<Employee> byAge = new ArrayList<>(original);
        byAge.sort(byAgeThenId);
        System.out.println("original: " + ids(original));
        System.out.println("age then id: " + ids(byAge));

        List<Employee> byName = new ArrayList<>(original);
        byName.sort(byNameThenId);
        System.out.println("name then id: " + ids(byName));

        List<Employee> reversed = new ArrayList<>(original);
        reversed.sort(byAgeThenId.reversed());
        System.out.println("reversed all keys: " + ids(reversed));

        List<Employee> onlyAgeDescending = new ArrayList<>(original);
        onlyAgeDescending.sort(
                Comparator.comparingInt(Employee::age)
                          .reversed()
                          .thenComparingInt(Employee::id));
        System.out.println("age down, id up: "
                + ids(onlyAgeDescending));

        System.out.println("stream sorted: " +
                ids(original.stream().sorted(byAgeThenId).toList()));

        Comparator<Employee> onlyAge =
                Comparator.comparingInt(Employee::age);
        System.out.println("bao equals chi: " + bao.equals(chi));
        System.out.println("age-only compare bao chi: "
                + onlyAge.compare(bao, chi));

        Set<Employee> loose = new TreeSet<>(onlyAge);
        loose.add(bao);
        loose.add(chi);
        loose.add(alice);
        System.out.println("TreeSet age-only size: " + loose.size());
        System.out.println("TreeSet age-only contains chi: "
                + loose.contains(chi));

        Set<Employee> strict = new TreeSet<>(byAgeThenId);
        strict.add(bao);
        strict.add(chi);
        strict.add(alice);
        System.out.println("TreeSet age-id size: " + strict.size());

        List<Employee> nullable =
                new ArrayList<>(Arrays.asList(chi, null, alice, bao));
        nullable.sort(Comparator.nullsLast(byAgeThenId));
        System.out.println("nulls last IDs: " + ids(nullable));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac ExternalComparatorDemo.java
java ExternalComparatorDemo
```

Kết quả stdout chính xác:

```text
original: [2, 1, 3]
age then id: [1, 3, 2]
name then id: [2, 1, 3]
reversed all keys: [2, 3, 1]
age down, id up: [2, 1, 3]
stream sorted: [1, 3, 2]
bao equals chi: false
age-only compare bao chi: 0
TreeSet age-only size: 2
TreeSet age-only contains chi: true
TreeSet age-id size: 3
nulls last IDs: [1, 3, 2, -1]
```

Trong hàm `ids`, giá trị `-1` chỉ là **ký hiệu in ra cho phần tử null**. Người trong ví dụ đều có mã dương, nên có thể phân biệt ký hiệu này. Trong chương trình thật, không nên dùng số `-1` làm dấu hiệu null nếu `-1` là một mã hợp lệ.

### Phân tích kết quả

- Danh sách `original` giữ thứ tự được tạo: Alice (id 2), Bao (id 1), Chi (id 3). `sort` chỉ thay đổi **bản sao `ArrayList`**, không sửa `original`.
- `byAgeThenId` đặt Bao và Chi (25 tuổi) trước Alice (30 tuổi), rồi phân định Bao id 1 trước Chi id 3.
- `byAgeThenId.reversed()` đảo cả khóa tuổi và mã nên Alice trước, rồi Chi, rồi Bao. Đảo chỉ khóa tuổi trước khi ghép mã sẽ cho Alice, Bao, Chi.
- `stream().sorted(byAgeThenId)` trả một danh sách mới theo thứ tự tương ứng. Nó không sửa `original`.
- `bao.equals(chi)` là `false` vì record tự so sánh theo **tất cả thành phần**; comparator chỉ xét tuổi trả `0`.
- `TreeSet` dùng dấu của `compare` để quyết định phần tử trùng nhau. Khi chỉ so tuổi, việc thêm Chi 25 tuổi sau Bao 25 tuổi không thêm phần tử mới; `contains(chi)` vẫn `true` vì comparator coi Chi tương đương Bao.
- `byAgeThenId` phân biệt mã Bao và Chi, nên `TreeSet` thứ hai chứa đủ ba người.
- `Comparator.nullsLast(byAgeThenId)` đặt phần tử null cuối, phần tử không null vẫn theo tuổi và id. Chương trình minh họa vì sao phải chủ động xử lý null khi nguồn dữ liệu cho phép.

## 5. Cơ chế `List.sort` và `Stream.sorted`

### Sắp xếp trực tiếp trên danh sách

`List.sort(Comparator<? super E> c)` **thay đổi thứ tự phần tử của danh sách đang gọi phương thức** và không tạo danh sách mới. Vì vậy với danh sách không cho phép sửa thứ tự (chẳng hạn `List.of(...)`), gọi `sort` có thể ném `UnsupportedOperationException`.

```java
List<Employee> mutable = new ArrayList<>(employees);
mutable.sort(byAgeThenId);
```

Đoạn này là fragment giả sử có `employees` và `byAgeThenId`. Tạo bản sao có thể sửa giúp giữ nguồn đầu vào nguyên vẹn.

Theo hợp đồng, sắp xếp bằng `List.sort` là **stable**: khi comparator trả `0` cho hai phần tử, thứ tự tương đối ban đầu của chúng được bảo toàn. Tuy vậy stable sort **không thay thế khóa phụ** nếu nghiệp vụ muốn một thứ tự tổng quát có thể lặp lại từ mọi cách nhập dữ liệu. Kết hợp `thenComparing` giúp quy tắc rõ ràng.

### Sắp xếp qua stream

`stream.sorted(comparator)` trả một stream đã sắp thứ tự để thực hiện thao tác tiếp theo; có thể tạo danh sách bằng `toList()` trong Java 17:

```java
List<Employee> sorted = employees.stream()
        .sorted(byAgeThenId)
        .toList();
```

Kết quả `Stream.toList()` là danh sách **không cho phép sửa**, vì vậy muốn sắp xếp tiếp in-place thì nên sao chép ra `ArrayList`. Với các stream có thứ tự encounter order, `Stream.sorted` bảo đảm tính ổn định; với stream không có thứ tự, không có bảo đảm ổn định theo một encounter order vốn không tồn tại.

Ngoài `List` và stream, các phương thức như `Collections.sort(list, comparator)` hoặc `Arrays.sort(array, comparator)` cũng dùng comparator phù hợp với kiểu phần tử. Chọn API theo loại dữ liệu và việc có muốn thay đổi collection gốc hay không.

## 6. Hợp đồng của một `Comparator` đúng

Một comparator phải mô tả quan hệ thứ tự hợp lệ trên toàn bộ miền giá trị mà nó chấp nhận. Với `sgn` là dấu của số nguyên, ba tính chất quan trọng là:

1. **Đối dấu:** `sgn(compare(a,b)) == -sgn(compare(b,a))`.
2. **Bắc cầu:** nếu `a > b` và `b > c` theo comparator thì `a > c`.
3. **Nhóm tương đương nhất quán:** nếu `compare(a,b)==0`, so `a` và `b` với cùng một `z` phải cho kết quả cùng dấu.

Không dùng phép trừ số nguyên làm phương thức so sánh tổng quát, vì phép trừ có thể tràn. Dùng `Integer.compare`, `Long.compare`, `Double.compare` hoặc các factory `comparingInt/Long/Double` theo kiểu khóa. `Double.compare` còn định nghĩa rõ thứ tự cho `NaN`, vô cực và `-0.0`.

Nếu comparator đọc random, đồng hồ, cờ cấu hình thay đổi, hoặc thuộc tính bị sửa trong lúc sort, thứ tự có thể tự mâu thuẫn. Java có thể phát hiện một số lỗi và ném `IllegalArgumentException`, nhưng không bảo đảm phát hiện mọi comparator sai. Bài về *hợp đồng dấu, tính bắc cầu và nhóm 0* sẽ kiểm tra các điều kiện này bằng cặp, bộ ba giá trị và ca biên.
## 7. `compare(a,b) == 0` và `equals()` trong `TreeSet` / `TreeMap`

`Comparator` quyết định **thứ tự**, còn `equals()` quyết định **bằng nhau theo hợp đồng của đối tượng**. Với `List.sort`, hai nhân viên cùng tuổi vẫn được giữ trong danh sách. Nhưng `TreeSet` và `TreeMap` dùng `compare(a,b)==0` để nhận diện phần tử/khóa tương đương. Trong ví dụ:

- `bao.equals(chi)` là `false` vì hai record khác mã và tên.
- Comparator chỉ xét tuổi trả `0`, nên `TreeSet` giữ một đại diện của nhóm tuổi 25 và `contains(chi)` vẫn có thể trả `true`.
- `TreeMap` dùng cùng quy tắc có thể thay **giá trị** của mapping hiện có khi `put` một khóa mới nhưng so sánh bằng 0.

Thứ tự **nhất quán với equals** khi `compare(a,b)==0` *khi và chỉ khi* `a.equals(b)` (xét trên miền dữ liệu hợp lệ). Phải kiểm tra **cả hai chiều**. `byAgeThenId` trong ví dụ phân biệt các bản ghi đang có, nhưng chưa chắc nhất quán với `equals` của mọi `Employee`: hai record cùng tuổi và mã nhưng tên khác vẫn so bằng 0. Với `TreeSet/TreeMap`, hãy xác định đúng khóa định danh hoặc dùng cấu trúc khác nếu muốn giữ tất cả phần tử cùng thứ hạng. Bài riêng về Comparator dùng cho hiển thị và quan hệ bằng nhau phân tích sâu hai hướng sai lệch.
## 8. Xử lý `null` và khóa nullable

Mặc định các comparator từ `Comparator.comparingInt(Employee::age)` sẽ gọi getter và không xử lý object `null`, nên so sánh với phần tử null có thể ném `NullPointerException`.

Muốn đặt **toàn bộ nhân viên null** ở cuối:

```java
Comparator<Employee> nullableEmployees =
        Comparator.nullsLast(byAgeThenId);
```

Muốn đặt null ở đầu thì dùng `Comparator.nullsFirst(byAgeThenId)`. Đây là hai phương thức xử lý **đối tượng được so sánh là null**.

Khác với trường hợp **trường khóa bên trong đối tượng null**. Ví dụ `name` có thể null nhưng `Employee` vẫn là object không null. Khi đó cần xử lý comparator của khóa:

```java
Comparator<Employee> nullableNames =
        Comparator.comparing(
                Employee::name,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
```

Đoạn này cho `name == null` xếp cuối so với tên không null, trong phạm vi các object nhân viên không null. Nếu có thể null cả nhân viên và tên, kết hợp **hai lớp chính sách**:

```java
Comparator<Employee> bothNullable =
        Comparator.nullsLast(nullableNames);
```

Những đoạn trên là fragment minh họa, giả sử đã có record `Employee` và các comparator phù hợp. Không nên tự tiện coi chuỗi rỗng `""` là null hoặc thay null bằng một giá trị mặc định nếu điều đó có thể làm mất phân biệt dữ liệu nghiệp vụ.

## 9. Những lỗi thường gặp khi định nghĩa thứ tự ngoài lớp

- **Không dùng tie-breaker khi cần uniqueness.** So theo tuổi đơn thuần có thể khiến `TreeSet` bỏ một nhân viên khác có cùng tuổi.
- **Quên `reversed()` đảo cả khóa phụ.** Nếu muốn chính/phụ trái chiều, đặt `reversed()` đúng vị trí trong chuỗi factory method.
- **Viết `return a.age() - b.age()`.** Phép trừ có thể overflow; dùng `Integer.compare` hoặc `Comparator.comparingInt`.
- **Nhầm `compare() == 0` với `equals()`.** Hai quan hệ không có cùng ý nghĩa mặc định; kiểm tra riêng khi làm khóa collection.
- **Đọc nhầm `sort` là bất biến.** `List.sort` sửa list gọi nó; `stream.sorted(...).toList()` tạo danh sách kết quả.
- **Bỏ qua null.** `nullsFirst/nullsLast` cho object null không tự xử lý khóa `name` null bên trong object.
- **Cố dùng comparator cho dữ liệu biến đổi trong `TreeSet`/`TreeMap`.** Nếu trường tuổi/id dùng khi định vị trong cây thay đổi sau khi chèn, lookup và thứ tự có thể không còn hợp lệ. Ưu tiên khóa bất biến hoặc xóa rồi thêm lại với trạng thái mới.
- **Comparator trả giá trị tùy tiện hoặc phụ thuộc vào thứ tự gọi.** Có thể vi phạm đối dấu/bắc cầu, gây lỗi sắp xếp và hành vi không xác định về ngữ nghĩa nghiệp vụ.

## 10. Checklist và bài tập tự kiểm tra

### Checklist

1. Thứ tự cần thiết là tự nhiên của lớp hay một yêu cầu cụ thể của màn hình/nghiệp vụ? Nếu có nhiều phương án, tạo `Comparator<T>` bên ngoài.
2. Khóa sắp xếp là gì? Có cần nhiều khóa (`thenComparing`) để phân định trường hợp bằng nhau không?
3. Có cần tăng/giảm riêng từng khóa hay đảo toàn bộ comparator?
4. Các đối tượng/trường khóa có thể null không? Định nghĩa vị trí của null rõ ràng.
5. Comparator có thỏa đối dấu, bắc cầu và ổn định khi dữ liệu không đổi không?
6. Comparator chỉ dùng để sắp xếp một list hay còn làm bộ xác định uniqueness cho `TreeSet`/`TreeMap`?
7. Nếu dùng làm khóa sorted collection, `compare(a,b)==0` có phù hợp chính sách `equals()` và bản sắc logic mong muốn không?
8. Có đang so sánh số nguyên bằng phép trừ dễ overflow, hoặc so số thực với các quy tắc không nhất quán không?

### Bài tập

**Bài 1.** Có ba nhân viên: A tuổi 30 id 2, B tuổi 25 id 1, C tuổi 25 id 3. Với `comparingInt(age).thenComparingInt(id)`, thứ tự là gì?

**Đáp án:** B, C, A; tuổi tăng trước, id tăng khi bằng tuổi.

**Bài 2.** Gọi `reversed()` sau khi đã ghép `age` rồi `id` sẽ ra thứ tự gì?

**Đáp án:** A, C, B; cả hai tiêu chí cùng bị đảo. Muốn A, B, C phải đảo comparator tuổi trước khi ghép id tăng.

**Bài 3.** Nếu `a.equals(b)` là false nhưng `compare(a,b)` là `0`, comparator có nhất thiết sai khi dùng `List.sort` không?

**Đáp án:** Không. Nó có thể tạo một nhóm ngang thứ tự hợp lệ, ví dụ người cùng tuổi; list vẫn giữ đủ hai phần tử. Nhưng nếu dùng comparator ấy làm chính sách khóa của `TreeSet`, hai người có thể bị gộp.

**Bài 4.** `Comparator.nullsLast(comparing(Employee::name))` có tự xử lý `employee.name() == null` không?

**Đáp án:** Không. `nullsLast` ở bên ngoài chỉ xử lý object `Employee` null. Muốn xử lý trường `name` null thì áp dụng `nullsLast` cho comparator của **khóa tên** bên trong `comparing`.

## Ghi nhớ

**`Comparator<T>` cho phép đặt quy tắc sắp xếp ở bên ngoài lớp dữ liệu**, nên một kiểu có thể được sắp theo nhiều tiêu chí mà không cần thay đổi chính class. Sử dụng `comparing...`, `thenComparing...` và `reversed()` để mô tả chính sách rõ ràng, tránh phép trừ dễ tràn và định nghĩa null khi cần. Với `TreeSet`/`TreeMap`, `compare(a,b)==0` còn là tiêu chí xem phần tử/khóa trùng nhau; vì thế comparator phải tương thích với bản sắc logic mong muốn và hợp đồng của collection.
