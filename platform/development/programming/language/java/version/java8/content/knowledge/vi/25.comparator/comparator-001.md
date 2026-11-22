# Comparator.comparing và trích xuất khóa sắp xếp trong Java

> **Phạm vi:** Java 8 — Comparator. Trọng tâm là chuyển một quy tắc sắp xếp đối tượng thành việc **trích xuất khóa** rồi **so sánh khóa**, bằng các overload `Comparator.comparing` cùng các hàm phối hợp. Những API Java 8 được giải thích ở đây vẫn hoạt động trong các JDK hiện hành; ví dụ runnable giữ tương thích Java 8.

## 1. Bài toán: sắp xếp object theo một thuộc tính

Giả sử ứng dụng có danh sách nhân viên:

~~~java
final class Employee {
    private final int id;
    private final String name;
    private final int age;

    Employee(int id, String name, int age) {
        this.id = id;
        this.name = name;
        this.age = age;
    }

    int getId() { return id; }
    String getName() { return name; }
    int getAge() { return age; }
}
~~~

Đây là **lớp minh họa**; mục 11 có chương trình Java chạy độc lập.

Nhân viên không có một thứ tự “đúng” duy nhất. Tùy nghiệp vụ, ta có thể muốn:

- Sắp xếp theo **tên** tăng dần.
- Sắp xếp theo **tuổi** tăng dần.
- Sắp xếp theo **phòng ban** tăng dần, rồi **lương** giảm dần.
- Sắp xếp theo tên nhưng **không phân biệt hoa/thường**, và dùng ID để phá hòa.
- Sắp xếp theo khóa tính được, ví dụ tên đã chuẩn hóa hoặc độ dài tên.

Một cách viết thủ công cho tuổi là:

~~~java
Comparator<Employee> byAge = (left, right) ->
        Integer.compare(left.getAge(), right.getAge());
~~~

Nhưng Java 8 cho phép diễn đạt trực tiếp ý định:

~~~java
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::getAge);
~~~

Cách thứ hai nói rõ: **lấy tuổi từ mỗi Employee, rồi so sánh như số nguyên**. Nó thường dễ đọc, an toàn trước lỗi trừ số bị overflow và tránh boxing của dạng so sánh qua `Integer`.

Với tên:

~~~java
Comparator<Employee> byName =
        Comparator.comparing(Employee::getName);
~~~

Đây là hai **đoạn minh họa** với import `java.util.Comparator`. `Employee::getName` không so sánh hai Employee trực tiếp; nó là một **key extractor** trích xuất `String` từ từng Employee. Sau đó `Comparator.comparing` dùng thứ tự tự nhiên của `String` để so sánh.

## 2. Comparator, Comparable và key extractor khác nhau ra sao?

### 2.1. Comparator<T>: so sánh hai đối tượng kiểu T

`Comparator<T>` là functional interface mà phương thức trừu tượng cốt lõi là:

~~~java
int compare(T left, T right);
~~~

Quy ước dấu:

| Giá trị `compare(a, b)` | Ý nghĩa |
| --- | --- |
| Số âm | `a` đứng trước `b` theo quy tắc sắp xếp |
| `0` | `a` và `b` tương đương **theo comparator** |
| Số dương | `a` đứng sau `b` theo quy tắc sắp xếp |

Comparator không bắt buộc trả đúng `-1` hoặc `1`; chỉ **dấu** của kết quả mới quan trọng. Comparator phải bảo đảm tính đối xứng về dấu, tính bắc cầu và tính nhất quán của quan hệ “so sánh bằng 0” đối với phần tử thứ ba.

### 2.2. Comparable<U>: khóa biết tự so sánh

Nhiều kiểu như `String`, `Integer`, `Long`, `LocalDate` và `BigDecimal` triển khai `Comparable` nên có **natural ordering**.

- `String` có thứ tự tự nhiên theo thứ tự từ điển dựa trên đơn vị mã Unicode/UTF-16; **không tự động** là quy tắc sắp xếp tên tiếng Việt.
- `Integer`/`Long` so sánh theo giá trị số.
- `LocalDate` so sánh theo ngày.
- `BigDecimal.compareTo` so sánh theo giá trị số, trong khi `BigDecimal.equals` còn xét scale; điều này quan trọng khi dùng comparator trong sorted Set/Map.

`Comparator.comparing(keyExtractor)` dùng natural ordering của khóa. Nó **không đòi Employee triển khai Comparable** nếu key được trích xuất đã Comparable.

### 2.3. Function<T,U>: lấy khóa ra từ object

Trích xuất khóa là một ánh xạ:

~~~text
Employee  -- getName -->  String
Employee  -- getAge  -->  int
Order     -- getDate -->  LocalDate
Product   -- getCode -->  String
~~~

Với `Comparator.comparing` dạng nhận `Function`, kiểu khóa `U` phải đáp ứng `Comparable`, hoặc caller phải cung cấp comparator riêng cho `U`.

Với `comparingInt`, `comparingLong` và `comparingDouble`, Java nhận các functional interface chuyên biệt:

- `ToIntFunction<T>`: `int applyAsInt(T value)`.
- `ToLongFunction<T>`: `long applyAsLong(T value)`.
- `ToDoubleFunction<T>`: `double applyAsDouble(T value)`.

Điểm phân biệt: **key extractor không phải comparator**. Một extractor nhận *một* object và trả khóa; comparator nhận *hai* object rồi trả kết quả so sánh.

## 3. Comparator.comparing(Function): khóa có natural order

Chữ ký rút gọn của Java 8:

~~~java
static <T, U extends Comparable<? super U>>
Comparator<T> comparing(
        Function<? super T, ? extends U> keyExtractor);
~~~

Trong đó:

- `T` là kiểu phần tử muốn sắp xếp (ví dụ `Employee`).
- `U` là kiểu khóa được lấy ra (ví dụ `String` hoặc `LocalDate`).
- `Function<? super T, ? extends U>` có thể dùng getter, lambda hoặc một hàm biến đổi tương thích.
- Điều kiện `U extends Comparable<? super U>` yêu cầu khóa có **thứ tự tự nhiên** tương thích.
- Kết quả là một `Comparator<T>`, **không phải** `Comparator<U>`.

Ví dụ:

~~~java
Comparator<Employee> byName =
        Comparator.comparing(Employee::getName);

Comparator<Employee> byNameLength =
        Comparator.comparing(e -> e.getName().length());

Comparator<Employee> byNormalizedName =
        Comparator.comparing(e -> e.getName().trim().toLowerCase(Locale.ROOT));
~~~

Đây là **đoạn minh họa**, cần `java.util.Comparator` và `java.util.Locale`, với tiền đề `getName()` trả chuỗi không null. Dạng `byNameLength` trả `Integer` qua autoboxing từ `int`, nhưng nếu mục tiêu chỉ là số nguyên, phiên bản `comparingInt(e -> e.getName().length())` thường biểu đạt ý định tốt hơn.

**Lưu ý với `toLowerCase(Locale.ROOT)`:** cách chuẩn hóa này phù hợp nếu ứng dụng muốn so sánh chuỗi theo quy tắc không phụ thuộc locale, nhưng nó **không thay thế thuật toán đối chiếu ngôn ngữ tự nhiên**. Sắp xếp tên tiếng Việt theo quy tắc địa phương có thể cần `Collator`. Ngoài ra, so sánh chuỗi không phân biệt hoa/thường có thể xem các chuỗi khác nhau theo `equals` là tương đương; hãy xét tie-breaker nếu cần phân biệt.

### 3.1. Method reference và lambda có cùng vai trò

~~~java
Comparator<Employee> a =
        Comparator.comparing(Employee::getName);

Comparator<Employee> b =
        Comparator.comparing(e -> e.getName());
~~~

Cả hai đều trích xuất cùng khóa từ Employee. Dạng method reference gọn khi đã có method đúng kiểu; lambda hữu ích nếu phải biến đổi hoặc kết hợp điều kiện trước khi lấy khóa.

Không cần tạo method chỉ để cho mọi extractor đều dùng `::`: mục tiêu chính là **đọc rõ quy tắc** và giữ hàm trích xuất ổn định.

### 3.2. Một extractor có thể tính khóa

Không bắt buộc khóa là một field được lưu sẵn:

~~~java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);

Comparator<String> byFinalCharacter =
        Comparator.comparing(
                s -> s.substring(s.length() - 1));
~~~

Đây là **mã minh họa**; `byFinalCharacter` chỉ hợp lệ trên các String không rỗng và không null. Nếu nguồn có chuỗi rỗng, extractor phải định nghĩa cách xử lý phù hợp thay vì để `StringIndexOutOfBoundsException` xảy ra bất ngờ.

**Vấn đề quan trọng:** `comparing` không hứa “tính khóa một lần rồi cache”. Khi thuật toán sắp xếp so sánh nhiều cặp, getter hoặc phép tính khóa **có thể được gọi nhiều lần** cho cùng object. Vì thế extractor nên nhanh, thuần, không side effect và trả cùng kết quả trong suốt lần sắp xếp.

## 4. Comparator.comparing(Function, Comparator): chủ động quy định cách so sánh khóa

Khi khóa không có natural order hoặc nghiệp vụ cần thứ tự riêng, dùng overload hai tham số:

~~~java
static <T, U> Comparator<T> comparing(
        Function<? super T, ? extends U> keyExtractor,
        Comparator<? super U> keyComparator);
~~~

`keyExtractor` lấy giá trị `U` từ mỗi `T`; `keyComparator` quyết định thứ tự giữa hai giá trị `U`. Kiểu `U` **không cần** triển khai `Comparable` vì comparator được cung cấp.

### 4.1. Tên không phân biệt chữ hoa/chữ thường

~~~java
Comparator<Employee> byNameIgnoreCase =
        Comparator.comparing(
                Employee::getName,
                String.CASE_INSENSITIVE_ORDER);
~~~

Hai nhân viên có tên `"an"` và `"An"` có khóa được xem là bằng nhau theo comparator này, mặc dù `"an".equals("An")` là `false`. Khi chỉ cần sắp xếp danh sách thì hợp lệ; khi dùng trong `TreeSet`, điều đó có thể vô tình làm mất một phần tử.

Muốn kết quả có thứ tự xác định khi khóa không phân biệt hoa/thường bằng nhau, thêm tiêu chí:

~~~java
Comparator<Employee> byNameIgnoreCaseThenId =
        Comparator.comparing(
                Employee::getName,
                String.CASE_INSENSITIVE_ORDER)
        .thenComparingInt(Employee::getId);
~~~

Khi tên so sánh bằng 0, ID sẽ quyết định thứ tự. Dùng tiêu chí phụ phù hợp với **ngữ nghĩa của dữ liệu**, không thêm ID một cách tùy tiện nếu yêu cầu chính là giữ thứ tự nhập cho các khóa bằng nhau.

### 4.2. Khóa là đối tượng không Comparable

Giả sử `DeliveryWindow` có trường `getStartEpochSeconds()` nhưng không tự triển khai Comparable. Có thể cung cấp comparator dành riêng cho kiểu này:

~~~java
Comparator<DeliveryWindow> byWindowStart =
        Comparator.comparingLong(DeliveryWindow::getStartEpochSeconds);

Comparator<Shipment> byDeliveryWindow =
        Comparator.comparing(
                Shipment::getWindow,
                byWindowStart);
~~~

Đây là **đoạn minh họa**, giả định có hai lớp `DeliveryWindow` và `Shipment` trong ứng dụng và các getter nêu trên. `comparing(Function, Comparator)` cho phép sắp xếp `Shipment` theo khóa `DeliveryWindow` mà không bắt `DeliveryWindow` trở thành Comparable.

### 4.3. Sắp xếp theo ngôn ngữ/locale

`String.compareTo` và `String.CASE_INSENSITIVE_ORDER` không tự mô phỏng đầy đủ quy tắc thứ tự tên theo từng ngôn ngữ. Có thể xét `java.text.Collator`:

~~~java
Collator vi = Collator.getInstance(new Locale("vi", "VN"));
Comparator<Employee> byVietnameseName =
        Comparator.comparing(Employee::getName, vi);
~~~

Đây là **đoạn minh họa**, có thêm import `java.text.Collator` và `java.util.Locale`. `Collator` có thể cấu hình theo quy tắc ngôn ngữ và có trạng thái cấu hình; không thay đổi cấu hình của cùng comparator giữa lần sắp xếp, và khi dùng nhiều thread cần xem hướng dẫn về thread-safety của implementation. Thứ tự tên cụ thể có thể phụ thuộc dữ liệu locale/provider của runtime; **không suy đoán stdout chính xác từ đoạn này**.

## 5. comparingInt, comparingLong và comparingDouble

Khi khóa là primitive, ưu tiên overload chuyên biệt thay vì boxing sang wrapper:

| Factory | Extractor | Khóa được so sánh |
| --- | --- | --- |
| `Comparator.comparingInt(...)` | `ToIntFunction<? super T>` | `int` |
| `Comparator.comparingLong(...)` | `ToLongFunction<? super T>` | `long` |
| `Comparator.comparingDouble(...)` | `ToDoubleFunction<? super T>` | `double` |

Ví dụ:

~~~java
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::getAge);

Comparator<Employee> bySalary =
        Comparator.comparingLong(Employee::getSalary);

Comparator<Measurement> byReading =
        Comparator.comparingDouble(Measurement::getReading);
~~~

Đây là **các đoạn minh họa**; `Measurement` là lớp giả định có getter trả `double`. Các overload dùng phép so sánh thích hợp cho primitive; về mặt ý nghĩa tương tự trích xuất khóa rồi so sánh.

### 5.1. Tránh lỗi tràn khi trừ hai giá trị

Không cài comparator số nguyên như:

~~~java
// SAI: phép trừ có thể overflow và làm thứ tự bị đảo sai.
Comparator<Employee> risky =
        (a, b) -> a.getAge() - b.getAge();
~~~

Nếu số rất lớn/âm hoặc dùng trường `int` khác có giá trị biên, phép trừ có thể tràn. Dùng:

~~~java
Comparator<Employee> safe =
        Comparator.comparingInt(Employee::getAge);

// Hoặc với lambda thủ công:
Comparator<Employee> safeManual =
        (a, b) -> Integer.compare(a.getAge(), b.getAge());
~~~

Không phải số nguyên tuổi nào cũng đủ lớn để gây lỗi trong thực tế, nhưng xây dựng thói quen `comparingInt`/`Integer.compare` giúp mã đúng với mọi giá trị `int` hợp lệ.

### 5.2. Giá tiền và số thực

Với giá tiền cần tính chính xác, thường chọn `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất (ví dụ `long` cents), không dùng `double` chỉ vì có `comparingDouble`.

`comparingDouble` sử dụng thứ tự số thực theo ngữ nghĩa `Double.compare`, có quy tắc cho `NaN` và phân biệt `-0.0` với `+0.0`. Nếu ứng dụng muốn chuẩn hóa hai giá trị zero hoặc quy tắc NaN riêng, phải xác định **khóa/so sánh phù hợp với domain**, không giả định số thực tuân thủ mọi trực giác toán học.

## 6. thenComparing: sắp xếp nhiều tiêu chí, phá hòa có chủ đích

### 6.1. Sắp xếp theo tên, sau đó ID

~~~java
Comparator<Employee> byNameThenId =
        Comparator.comparing(Employee::getName)
                .thenComparingInt(Employee::getId);
~~~

Ý nghĩa:

1. So sánh `name` của hai Employee.
2. **Chỉ nếu** hai tên so sánh bằng `0`, mới so sánh `id`.
3. Trả kết quả từ tiêu chí quyết định đầu tiên.

Nếu hai nhân viên tên `"An"` nhưng ID là `2` và `3` thì ID `2` đứng trước ID `3`. Với các tên khác nhau, ID không làm thay đổi thứ tự đã được quyết định bởi tên.

Các dạng thường dùng:

~~~java
// Key Comparable:
Comparator<Employee> c1 =
        Comparator.comparing(Employee::getTeam)
                .thenComparing(Employee::getName);

// Key thứ hai cần Comparator riêng:
Comparator<Employee> c2 =
        Comparator.comparing(Employee::getTeam)
                .thenComparing(Employee::getName,
                        String.CASE_INSENSITIVE_ORDER);

// Key primitive:
Comparator<Employee> c3 =
        Comparator.comparingInt(Employee::getAge)
                .thenComparingLong(Employee::getSalary);
~~~

Đây là các **đoạn minh họa**, giả định Employee có `getTeam()`, `getName()`, `getAge()` và `getSalary()`; chương trình runnable có các getter tương ứng.

### 6.2. Thứ tự ưu tiên khi chaining

~~~text
comparing(team)
  .thenComparing(name)
  .thenComparingInt(id)

=> team tăng dần
=> nếu cùng team: name tăng dần
=> nếu cùng team + name: id tăng dần
~~~

`thenComparing` không “sắp xếp lại cả danh sách lần thứ hai” theo kiểu hai vòng độc lập. Nó tạo **một Comparator hợp thành**, so sánh các khóa theo thứ tự ưu tiên như so sánh từ điển.

### 6.3. Có nên dùng tiêu chí phá hòa?

- Với **List** và yêu cầu giữ encounter order cho các phần tử có khóa chính bằng nhau, không nhất thiết cần tie-breaker vì `List.sort` và `Stream.sorted` trên ordered stream có bảo đảm ổn định (xem mục 9).
- Với **báo cáo cần thứ tự quyết định giữa mọi ID**, thêm tiêu chí phụ là hợp lý.
- Với **TreeSet/TreeMap**, nếu comparator trả `0` cho hai đối tượng khác nhau theo nghiệp vụ, hai đối tượng/khóa có thể bị coi là một: cần thiết kế comparator tương ứng với quan hệ bằng nhau mong muốn (xem mục 10).

Không thêm khóa phụ chỉ vì “chắc ăn” nếu điều đó làm mất ý nghĩa grouping hoặc chính sách ổn định của ứng dụng.

## 7. reversed(): đảo tiêu chí chính hay đảo toàn bộ chuỗi?

### 7.1. Đảo toàn bộ comparator hợp thành

~~~java
Comparator<Employee> byTeamThenAge =
        Comparator.comparing(Employee::getTeam)
                .thenComparingInt(Employee::getAge);

Comparator<Employee> reversedAll = byTeamThenAge.reversed();
~~~

`reversedAll` sẽ đảo **toàn bộ quan hệ thứ tự**: team giảm dần và, trong từng team, tuổi giảm dần. Đây **không phải** “chỉ cho tuổi giảm dần”.

### 7.2. Team tăng, lương giảm

Cách đúng là đảo **comparator phụ về lương**, rồi mới nối:

~~~java
Comparator<Employee> byTeamSalaryDesc =
        Comparator.comparing(Employee::getTeam)
                .thenComparing(
                        Comparator.comparingLong(Employee::getSalary)
                                .reversed())
                .thenComparingInt(Employee::getId);
~~~

Ý nghĩa: `team` tăng dần; trong cùng team, `salary` giảm dần; khi team và salary bằng nhau, `id` tăng dần.

Sai ý định:

~~~java
Comparator<Employee> notJustSalaryDesc =
        Comparator.comparing(Employee::getTeam)
                .thenComparingLong(Employee::getSalary)
                .reversed();
~~~

Đoạn cuối đảo **cả team lẫn salary**. Khi viết comparator nhiều tiêu chí, hãy kiểm tra `reversed()` được gọi **trước hay sau** `thenComparing(...)`.

### 7.3. Muốn khóa chính giảm dần, khóa phụ tăng dần

~~~java
Comparator<Employee> bySalaryDescThenIdAsc =
        Comparator.comparingLong(Employee::getSalary)
                .reversed()
                .thenComparingInt(Employee::getId);
~~~

Ở đây `reversed()` chỉ được gọi **trước** khi thêm `thenComparingInt`, nên salary giảm, ID vẫn tăng. Cách này khác với `Comparator.comparingLong(...).thenComparingInt(...).reversed()`.

## 8. Xử lý null đúng tầng: null object và null key

### 8.1. Null **phần tử** của danh sách

Nếu List có cả những phần tử `Employee` bằng null, một extractor như `Employee::getName` không thể gọi được trên null. Có thể bọc comparator của object:

~~~java
Comparator<Employee> nullEmployeesLast =
        Comparator.nullsLast(
                Comparator.comparing(Employee::getName));
~~~

Khi so sánh, `null` Employee được xếp cuối; đối tượng không null vẫn so theo tên. Đây là **đoạn minh họa**; tên của Employee không null.

### 8.2. Object không null nhưng **khóa** lấy ra null

Nếu Employee có trường nickname có thể null, bọc comparator **của khóa**:

~~~java
Comparator<Employee> nullNicknamesLast =
        Comparator.comparing(
                Employee::getNickname,
                Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Đây là **đoạn minh họa**, giả định Employee có `getNickname()` trả `String` có thể null. Bọc `Comparator.nullsLast` **ở bên trong** overload `comparing` để xử lý giá trị nickname null.

Hai đoạn khác nhau về vị trí null:

| Đối tượng đầu vào | Khóa trích xuất | Cách xử lý |
| --- | --- | --- |
| `Employee` có thể null | Không gọi được getter | `nullsFirst/Last` **bọc Comparator<Employee>` |
| `Employee` không null | `getNickname()` có thể trả null | `nullsFirst/Last` làm **keyComparator** |
| Cả object và key đều có thể null | Cả hai trường hợp | Bọc **cả keyComparator lẫn Comparator<Employee>` |

Ví dụ kết hợp:

~~~java
Comparator<Employee> byNullableNickname =
        Comparator.nullsLast(
                Comparator.comparing(
                        Employee::getNickname,
                        Comparator.nullsFirst(
                                Comparator.naturalOrder())));
~~~

Đây là đoạn minh họa: **Employee null** đứng cuối, **nickname null** đứng đầu nhóm Employee không null.

### 8.3. Null và reversed

~~~java
Comparator<Employee> descNameNullObjectLast =
        Comparator.nullsLast(
                Comparator.comparing(Employee::getName).reversed());
~~~

Cách này cho tên giảm dần và vẫn giữ **null Employee cuối**. Nếu viết `Comparator.nullsLast(...).reversed()` thì null sẽ bị đưa lên **đầu** vì cả quan hệ thứ tự đã bị đảo.

**Lưu ý:** Các overload `Comparator.comparing` kiểm tra tính hợp lệ của `keyExtractor`/`keyComparator` được truyền khi tạo comparator; truyền null trực tiếp cho tham số bắt buộc là lỗi. Điều này khác với việc extractor hợp lệ đôi khi *trả về* null khi được gọi.

## 9. Sắp xếp danh sách: List.sort, Collections.sort và Stream.sorted

### 9.1. List.sort(Comparator)

~~~java
List<Employee> employees = new ArrayList<>(source);
employees.sort(Comparator.comparing(Employee::getName));
~~~

Đây là **đoạn minh họa** với `source` là collection các Employee và import phù hợp. `List.sort` thay đổi thứ tự **ngay trong List**. List phải hỗ trợ thay thế phần tử hoặc không ném `UnsupportedOperationException` theo hợp đồng của implementation.

Phương thức này ổn định: khi comparator trả `0` cho hai phần tử, **thứ tự tương đối trước khi sắp xếp vẫn được giữ**. Điều này hữu ích nếu muốn sắp theo một tiêu chí mà vẫn tôn trọng thứ tự nhập ở những nhóm bằng nhau.

### 9.2. Stream.sorted(Comparator)

~~~java
List<Employee> sorted = source.stream()
        .sorted(Comparator.comparingInt(Employee::getAge))
        .collect(Collectors.toList());
~~~

Đây là đoạn minh họa. `sorted` là **intermediate operation**; phần tính toán xảy ra khi terminal `collect` chạy. `source` không bị sắp xếp tại chỗ.

Với một Stream **ordered**, `sorted` có tính ổn định: các phần tử có comparator bằng `0` giữ encounter order tương đối. Với Stream **unordered**, `sorted` **không cam kết ổn định**, dù vẫn có thứ tự theo comparator cho các giá trị được so sánh khác 0.

### 9.3. Collections.sort và Arrays.sort

Các API `Collections.sort(list, comparator)` và `Arrays.sort(array, comparator)` tiếp tục được hỗ trợ và hợp lệ. Trong mã hiện đại dùng `List`, `list.sort(comparator)` thường gọn; chọn API theo cấu trúc dữ liệu thật, không coi những API trước Java 8 là “bị loại bỏ”.

### 9.4. Chế độ parallel không thay hợp đồng so sánh

~~~java
List<Employee> result = source.parallelStream()
        .sorted(Comparator.comparingInt(Employee::getAge))
        .collect(Collectors.toList());
~~~

Đây là **đoạn minh họa**. Với nguồn ordered, `sorted` vẫn phải cho kết quả thỏa comparator và tính ổn định; parallel không cho phép comparator vi phạm tính nhất quán.

Tuy nhiên, sắp xếp là thao tác stateful thường cần buffer dữ liệu. Parallel stream có overhead, tiêu thụ bộ nhớ và chi phí hợp nhất; **không tự động nhanh hơn** sắp xếp tuần tự. Đo hiệu năng với dữ liệu/tải thực tế trước khi chọn.

## 10. TreeSet/TreeMap: compare == 0 quyết định tính duy nhất

### 10.1. Comparator cho List khác với comparator dùng để nhận diện phần tử trong SortedSet

Với `List.sort`, hai phần tử `a` và `b` có `compare(a,b)==0` có thể **cùng tồn tại** trong danh sách. Sắp xếp chỉ định thứ tự của chúng.

Với `TreeSet` hoặc `TreeMap`, comparator cũng là cơ chế xác định **khóa/phần tử tương đương trong cấu trúc được sắp xếp**. Nếu `compare(a,b)==0`, hai phần tử sẽ bị coi là cùng một giá trị sắp xếp hoặc hai khóa được coi là cùng một khóa. Việc thêm phần tử thứ hai vào TreeSet không tạo một mục mới.

Ví dụ:

~~~java
Comparator<Employee> byTeam =
        Comparator.comparing(Employee::getTeam);

Set<Employee> byTeamOnly = new TreeSet<>(byTeam);
byTeamOnly.add(new Employee(1, "An", "Sales", 23, 10_000L));
byTeamOnly.add(new Employee(2, "Binh", "Sales", 25, 20_000L));

// byTeamOnly.size() == 1.
~~~

Đây là **mã minh họa** dựa vào constructor Employee ở mục 11 (tham số gồm id, name, team, age, salary). Cả hai có cùng khóa `"Sales"` nên comparator trả 0. Điều này có thể hữu ích nếu nghiệp vụ thực sự muốn **một mục mỗi team**, nhưng dễ là lỗi nếu dự định lưu **mọi nhân viên**.

### 10.2. Comparator và equals phải nhất quán nếu muốn thỏa hợp đồng Set/Map

Hợp đồng tổng quát của `Set`/`Map` nói đến `equals`, còn SortedSet/SortedMap dựa vào thứ tự do comparator tạo. Vì thế để `TreeSet`/`TreeMap` tuân thủ hợp đồng Set/Map, quan hệ:

~~~text
compare(a,b) == 0  <=>  a.equals(b) == true
~~~

nên được giữ đúng trên những giá trị được hỗ trợ.

Nếu equality của `Employee` dựa trên ID, một comparator theo ID là lựa chọn tự nhiên cho TreeSet muốn nhận diện cùng employee theo ID:

~~~java
Comparator<Employee> byId =
        Comparator.comparingInt(Employee::getId);
~~~

Đây là đoạn minh họa. Điều này **chỉ hoàn toàn nhất quán** khi `Employee.equals` thực sự định nghĩa equality bằng ID. Nếu `Employee` vẫn dùng identity mặc định từ `Object`, hai object khác tham chiếu nhưng cùng ID có thể so bằng 0 mà `equals` lại false.

**Không nên thêm ID vào comparator một cách máy móc** để “sửa” mọi TreeSet; trước hết xác định quan hệ bằng nhau hợp lệ của phần tử/khóa.

### 10.3. Ví dụ String không phân biệt hoa/thường

~~~java
Set<String> names = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
names.add("An");
names.add("an"); // Không tạo mục thứ hai.
~~~

`"An".equals("an")` là `false`, nhưng comparator xem hai chuỗi này bằng nhau. Vì vậy cấu trúc TreeSet có thể không phản ánh quan hệ equality của Set mặc định. Khi dùng comparer theo locale, bỏ dấu hoặc case-insensitive, hãy lưu ý ảnh hưởng đến uniqueness.

## 11. Chương trình chạy được: comparing, key extractor và tie-breaker

Lưu thành tệp **ComparatorComparingDemo.java**. Chương trình chỉ sử dụng cú pháp và API Java 8, đồng thời tự làm cho các bản in kết quả **không phụ thuộc thứ tự HashSet/HashMap hoặc chi tiết JVM**.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class ComparatorComparingDemo {

    static final class Employee {
        private final int id;
        private final String name;
        private final String team;
        private final int age;
        private final long salary;

        Employee(int id, String name, String team, int age, long salary) {
            this.id = id;
            this.name = name;
            this.team = team;
            this.age = age;
            this.salary = salary;
        }

        int getId() { return id; }
        String getName() { return name; }
        String getTeam() { return team; }
        int getAge() { return age; }
        long getSalary() { return salary; }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Employee
                        && id == ((Employee) other).id);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }

        @Override
        public String toString() {
            return id + ":" + name;
        }
    }

    public static void main(String[] args) {
        List<Employee> employees = Arrays.asList(
                new Employee(5, "Mai", "Sales", 29, 19_000_000L),
                new Employee(2, "An", "Tech", 31, 23_000_000L),
                new Employee(1, "Binh", "Tech", 27, 21_000_000L),
                new Employee(3, "An", "Sales", 25, 18_000_000L),
                new Employee(4, "Lan", "Sales", 29, 15_000_000L)
        );

        Comparator<Employee> byNameThenId =
                Comparator.comparing(Employee::getName)
                        .thenComparingInt(Employee::getId);

        Comparator<Employee> byAgeOnly =
                Comparator.comparingInt(Employee::getAge);

        Comparator<Employee> byAgeThenId =
                Comparator.comparingInt(Employee::getAge)
                        .thenComparingInt(Employee::getId);

        Comparator<Employee> byTeamSalaryDesc =
                Comparator.comparing(Employee::getTeam)
                        .thenComparing(
                                Comparator.comparingLong(
                                        Employee::getSalary).reversed())
                        .thenComparingInt(Employee::getId);

        System.out.println("source = " + employees);
        System.out.println("by name + id = "
                + employees.stream().sorted(byNameThenId)
                        .collect(Collectors.toList()));
        System.out.println("by age stable = "
                + employees.stream().sorted(byAgeOnly)
                        .collect(Collectors.toList()));
        System.out.println("by age + id = "
                + employees.stream().sorted(byAgeThenId)
                        .collect(Collectors.toList()));
        System.out.println("by team/salary desc = "
                + employees.stream().sorted(byTeamSalaryDesc)
                        .collect(Collectors.toList()));
        System.out.println("reversed name + id = "
                + employees.stream().sorted(byNameThenId.reversed())
                        .collect(Collectors.toList()));

        List<String> nullableNames =
                new ArrayList<>(Arrays.asList(
                        null, "bob", "Alice", "ann"));
        nullableNames.sort(
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
        System.out.println("names null last = " + nullableNames);

        Set<Employee> uniqueTeams = new TreeSet<>(
                Comparator.comparing(Employee::getTeam));
        uniqueTeams.addAll(employees);
        System.out.println("TreeSet by team size = "
                + uniqueTeams.size());

        // equals() của Employee trong demo cũng định nghĩa ID là identity.
        Set<Employee> uniqueIds = new TreeSet<>(
                Comparator.comparingInt(Employee::getId));
        uniqueIds.addAll(employees);
        System.out.println("TreeSet by id size = " + uniqueIds.size());
    }
}
~~~

Biên dịch bằng JDK 17+ với API và cú pháp tương thích Java 8:

~~~bash
javac --release 8 ComparatorComparingDemo.java
java ComparatorComparingDemo
~~~

**Stdout kỳ vọng chính xác:**

~~~text
source = [5:Mai, 2:An, 1:Binh, 3:An, 4:Lan]
by name + id = [2:An, 3:An, 1:Binh, 4:Lan, 5:Mai]
by age stable = [3:An, 1:Binh, 5:Mai, 4:Lan, 2:An]
by age + id = [3:An, 1:Binh, 4:Lan, 5:Mai, 2:An]
by team/salary desc = [5:Mai, 3:An, 4:Lan, 2:An, 1:Binh]
reversed name + id = [5:Mai, 4:Lan, 1:Binh, 3:An, 2:An]
names null last = [Alice, ann, bob, null]
TreeSet by team size = 2
TreeSet by id size = 5
~~~

### 11.1. Giải thích từng dòng quan trọng

1. `source` giữ thứ tự đầu vào vì chương trình không sửa List gốc.
2. `byNameThenId` so tên theo natural order, sau đó ID tăng dần nếu tên trùng. Hai nhân viên `An` được sắp thành ID `2` rồi `3`.
3. `byAgeOnly` chỉ so tuổi. Hai nhân viên tuổi `29` là ID `5` và `4`; `Stream.sorted` trên List ordered là **stable**, nên ID `5` vẫn đứng trước ID `4` theo nguồn.
4. `byAgeThenId` phá hòa ở tuổi `29` bằng ID tăng dần, khiến ID `4` đổi lên trước ID `5`.
5. `byTeamSalaryDesc` đưa `Sales` trước `Tech` theo String natural order. Trong `Sales`, các mức lương 19M, 18M, 15M giảm dần; `Tech` có 23M trước 21M.
6. `byNameThenId.reversed()` đảo **cả hai khóa**; trong nhóm tên `An`, ID `3` đứng trước ID `2`.
7. `nullsLast(String.CASE_INSENSITIVE_ORDER)` sắp theo chữ không phân biệt hoa/thường, để null cuối danh sách.
8. `TreeSet` chỉ theo team có **hai** giá trị khóa `Sales`/`Tech` nên chỉ giữ hai nhân viên, dù đầu vào có năm.
9. `TreeSet` theo ID giữ cả năm vì ID khác nhau; trong ví dụ, `Employee.equals` cũng dựa trên ID nên quan hệ bằng 0 của comparator theo ID nhất quán với equality.

Mọi kết quả được quyết định từ dữ liệu và comparator; chương trình không phụ thuộc locale, thời gian, truy vấn mạng hoặc thứ tự duyệt HashMap.

## 12. Lỗi thường gặp khi trích xuất khóa sắp xếp

### Lỗi 1 — Nhầm comparing nhận Comparator của object

~~~java
Comparator<Employee> byName =
        Comparator.comparing(Employee::getName);
~~~

`Employee::getName` **trả khóa**, không phải hàm so sánh hai Employee. Nếu đã có `Comparator<String>` riêng, dùng overload hai tham số `comparing(Employee::getName, stringComparator)`.

### Lỗi 2 — Khóa không Comparable nhưng dùng overload một tham số

Một kiểu khóa `Money` hoặc `Address` tự định nghĩa không nhất thiết có natural ordering. `comparing(Employee::getAddress)` có thể **không biên dịch** nếu khóa Address không triển khai `Comparable`. Cung cấp keyComparator hoặc chuyển sang khóa có kiểu Comparable phù hợp; đừng ép kiểu không an toàn.

### Lỗi 3 — Viết comparator bằng phép trừ

~~~java
// Không nên: overflow với số nguyên biên.
(a, b) -> a.getId() - b.getId()
~~~

Hãy dùng `Comparator.comparingInt(Employee::getId)` hoặc `Integer.compare(...)`.

### Lỗi 4 — Cho rằng reversed() chỉ đảo trường ngay trước nó

`comparing(team).thenComparingInt(age).reversed()` đảo **toàn bộ chain**. Nếu chỉ muốn tuổi giảm trong team tăng, tạo comparator tuổi đảo bên trong `thenComparing`.

### Lỗi 5 — Lẫn null object với null key

`Comparator.nullsLast(Comparator.comparing(Employee::getName))` xử lý null **Employee**, không tự xử lý `getName()==null`. Nếu khóa có thể null, cần bọc **keyComparator**; nếu cả hai có thể null, phải bọc cả hai tầng.

### Lỗi 6 — Mong TreeSet giữ mọi phần tử dù comparator trả 0

`TreeSet` coi `compare(a,b)==0` là tương đương. Comparator chỉ theo tên hoặc team có thể làm mất phần tử/khóa khác nhau. Thiết kế tie-breaker phù hợp với `equals` và mục tiêu Set.

### Lỗi 7 — Đặt phép tính có side effect vào extractor

~~~java
// SAI về thiết kế: giá trị khóa có thể đổi mỗi lần so sánh.
Comparator<Employee> unstable =
        Comparator.comparingLong(e -> System.nanoTime());
~~~

Đây là **đoạn minh họa phản ví dụ**; nó có thể vi phạm hợp đồng comparator và làm sorting bất thường. Khóa nên ổn định và getter không nên sửa object, gọi network hay phụ thuộc thời điểm.

### Lỗi 8 — Biến đổi trường sort trong lúc đang sort

Nếu nhân viên thay đổi tên/tuổi trong khi `sort` đang so sánh, cùng một object có thể được xếp theo những khóa khác nhau theo thời gian; quan hệ có thể không còn nhất quán. Sắp xếp trên snapshot hoặc dữ liệu bất biến khi tính toán, đặc biệt khi có concurrency.

### Lỗi 9 — Kỳ vọng extractor chỉ chạy đúng một lần

`Comparator.comparing` không hứa cache khóa; thuật toán so sánh nhiều cặp có thể gọi getter nhiều lần. Nếu hàm tính khóa nặng, hãy cân nhắc **tính khóa trước** rồi sort các bản ghi đã chuẩn bị khóa.

### Lỗi 10 — Dùng comparator locale cho dữ liệu chứa null mà không xử lý

`Collator` hoặc `String.CASE_INSENSITIVE_ORDER` không tự xử lý mọi null. Bọc `nullsFirst/Last` đúng tầng và thống nhất chính sách null của input.

### Lỗi 11 — Giả định equals và compare bằng 0 giống nhau

Comparator có thể xem hai object là bằng nhau dù `equals` false. Với List, chúng vẫn cùng tồn tại; với TreeSet/TreeMap, một mục có thể thay thế hoặc che khuất mục còn lại. Khi tạo khóa cho SortedMap/SortedSet, kiểm tra quan hệ này rõ ràng.

### Lỗi 12 — Vi phạm tính bắc cầu hoặc đối xứng

Nếu comparator dùng các trường khác nhau tùy cặp so sánh, hoặc đổi quy tắc do trạng thái ngoài, có thể xảy ra `compare(a,b)<0`, `compare(b,c)<0` nhưng `compare(a,c)>0`. Đây là comparator không hợp lệ. Một số sort implementation có thể ném `IllegalArgumentException` khi phát hiện vi phạm hợp đồng, nhưng **không được dựa vào việc lúc nào cũng sẽ ném**; lỗi dữ liệu/ordering có thể xuất hiện mà không báo.

### Lỗi 13 — Dùng sắp xếp để suy ra quy tắc deduplication

`List.sort` chỉ đổi thứ tự, **không loại trùng**. `Stream.distinct` dựa trên `equals`, không dựa vào `Comparator.comparing` vừa dùng ở `sorted`. Nếu muốn nhóm theo key, cân nhắc `Collectors.groupingBy`; nếu muốn uniqueness theo comparator, xét kỹ hợp đồng `TreeSet` và nguy cơ mất dữ liệu.

### Lỗi 14 — Dùng lexical String order để đại diện một quy tắc domain khác

Ví dụ mã `"A2"` và `"A10"` so theo String tự nhiên có thể không như thứ tự số mong muốn. Cần extractor lấy **thành phần số** hợp lệ hoặc comparator phù hợp; không cố sửa bằng một vài phép `replace` thiếu bao quát. Với tên người, dùng quy tắc locale khi cần, không coi String natural order là sắp xếp ngôn ngữ luôn đúng.

## 13. Tối ưu có cân nhắc: chi phí trích xuất khóa

Giả sử sắp xếp 100.000 record bằng một hàm chuẩn hóa tên tốn CPU. Dạng:

~~~java
employees.sort(Comparator.comparing(
        e -> expensiveNormalize(e.getName())));
~~~

là **đoạn minh họa**: `employees` là List thay đổi được và `expensiveNormalize` là hàm giả định thuần. Getter/hàm chuẩn hóa có thể chạy **nhiều lần mỗi object** vì sorting so sánh nhiều cặp. Bài toán thích hợp để cân nhắc *decorate–sort–undecorate*:

1. Duyệt dữ liệu một lần và tạo cặp `(sortKey, originalObject)`; nếu cần ổn định xuyên nguồn unordered, ghi cả chỉ số đầu vào.
2. Sắp xếp **các cặp bằng sortKey** với Comparator phù hợp và tie-breaker nếu cần.
3. Lấy lại `originalObject` theo thứ tự vừa sắp.

Ví dụ ý tưởng bằng các lớp JDK 8:

~~~java
List<Map.Entry<String, Employee>> decorated = employees.stream()
        .map(e -> new AbstractMap.SimpleImmutableEntry<>(
                expensiveNormalize(e.getName()), e))
        .collect(Collectors.toList());

decorated.sort(Map.Entry.comparingByKey());

List<Employee> sorted = decorated.stream()
        .map(Map.Entry::getValue)
        .collect(Collectors.toList());
~~~

Đây là **đoạn minh họa**, cần import `Map`, `AbstractMap`, `List`, `Collectors`; `expensiveNormalize` là hàm ứng dụng có định nghĩa riêng. Khi source là List ordered, sort ổn định giữ thứ tự tương đối cho các sortKey bằng nhau. Cách này tránh tính lại khóa đắt trong các lượt so sánh, đổi lại cấp phát thêm cặp dữ liệu và bộ nhớ.

**Không phải cứ trích xuất khóa là phải precompute**. Với getter O(1) đơn giản và dữ liệu nhỏ, comparator trực tiếp dễ đọc và đủ tốt. Đo bằng benchmark đáng tin (ví dụ JMH) nếu hiệu năng quan trọng; đừng tối ưu trước khi biết điểm nghẽn.

## 14. Thiết kế quy tắc sort rõ ràng trong ứng dụng

### 14.1. Sắp danh sách cho UI/report

Xác định các yếu tố:

- **Khóa chính:** tên, giá, thời gian, trạng thái hay mức ưu tiên.
- **Chiều tăng/giảm** của từng khóa.
- **Cách xử lý null**: đầu hay cuối, có cấm null hay không.
- **Chuẩn hóa chuỗi**: phân biệt hoa/thường, dấu tiếng Việt, locale.
- **Tiêu chí phá hòa**: giữ thứ tự nhập, theo ID hoặc theo timestamp.
- **Phạm vi đột biến**: tạo List mới bằng Stream hay sort tại chỗ.

Ví dụ ưu tiên giá giảm, rồi mã tăng:

~~~java
Comparator<Product> displayOrder =
        Comparator.comparingLong(Product::getPriceInCents)
                .reversed()
                .thenComparing(Product::getCode);
~~~

Đây là **đoạn minh họa**, `Product` là lớp domain giả định, với giá tiền biểu diễn bằng `long` để tránh sai số `double`. Nếu giá có thể vượt phạm vi `long`, chọn kiểu biểu diễn thích hợp thay vì mặc định dùng kiểu nguyên thủy.

### 14.2. Sắp dữ liệu lớn và API phân trang

Nếu một API phân trang sắp theo timestamp nhưng nhiều bản ghi trùng timestamp, kết quả giữa các trang có thể khó dự đoán nếu không có tie-breaker. Thường cần sắp theo `timestamp` rồi `id` ổn định theo hợp đồng domain.

~~~java
Comparator<Event> byTimeAndId =
        Comparator.comparing(Event::getTime)
                .thenComparingLong(Event::getId);
~~~

Đây là **đoạn minh họa**, `Event` có getter `getTime()` trả `Instant` hoặc một kiểu Comparable phù hợp. Tuy nhiên, sắp xếp trong bộ nhớ **không tự giải quyết** tính nhất quán của phân trang tại database khi dữ liệu thay đổi; cần xác định thứ tự và chính sách snapshot/pagination ở đúng tầng.

### 14.3. Không trộn “sắp xếp” với “khóa nghiệp vụ”

Một đối tượng có thể có **nhiều comparator hợp lệ** cho các màn hình khác nhau (theo tên, tuổi, lương), nhưng chỉ có **một chiến lược equals/hashCode** theo định danh logic nếu dùng làm value key. Đừng thay equality toàn bộ domain chỉ để đáp ứng một màn hình sort.

Nếu cần uniqueness theo tên cho báo cáo, đó là một phép gom theo khóa khác với việc “nhân viên cùng ID là một người”. Phân biệt rõ danh tính và cách trình bày.

## 15. Bài tập tự kiểm tra

**Câu 1.** `Comparator.comparing(Employee::getName)` có đòi `Employee` triển khai `Comparable` không?

**Đáp án:** Không. Nó dùng `String` do getter trả ra làm khóa Comparable; `Employee` chỉ là kiểu phần tử cần so sánh.

**Câu 2.** Khác nhau giữa `Comparator.comparing(Employee::getAge)` và `Comparator.comparingInt(Employee::getAge)`?

**Đáp án:** Dạng đầu dùng `Function`, giá trị `int` được boxing thành `Integer` để làm khóa Comparable; dạng `comparingInt` dùng `ToIntFunction`, tránh boxing không cần thiết và biểu đạt việc so số nguyên trực tiếp.

**Câu 3.** Nếu khóa không triển khai Comparable, dùng overload nào?

**Đáp án:** `Comparator.comparing(extractor, keyComparator)` với comparator phù hợp cho kiểu khóa, hoặc chuyển thành một khóa Comparable hợp lệ.

**Câu 4.** Chuỗi `comparing(team).thenComparing(name).thenComparingInt(id)` ưu tiên thế nào?

**Đáp án:** Team trước, chỉ khi team bằng nhau mới so name, và chỉ khi cả team/name bằng nhau mới so id.

**Câu 5.** Sự khác biệt giữa `comparingInt(age).reversed().thenComparingInt(id)` và `comparingInt(age).thenComparingInt(id).reversed()`?

**Đáp án:** Biểu thức đầu: tuổi giảm, ID tăng khi bằng tuổi. Biểu thức sau: **cả tuổi và ID đều giảm**.

**Câu 6.** `Comparator.nullsLast(Comparator.comparing(Employee::getName))` có xử lý `getName()==null` không?

**Đáp án:** Không, nó xử lý phần tử Employee null. Muốn xử lý khóa name null, dùng `comparing(Employee::getName, Comparator.nullsLast(Comparator.naturalOrder()))`.

**Câu 7.** Tại sao `TreeSet` với comparator chỉ theo team có thể giữ ít phần tử hơn đầu vào?

**Đáp án:** Vì `TreeSet` coi hai phần tử có `compare(a,b)==0` là tương đương. Hai Employee khác nhau cùng team có thể không được thêm thành mục thứ hai.

**Câu 8.** Tại sao không nên dùng `(a,b) -> a.getId() - b.getId()`?

**Đáp án:** Phép trừ trên `int` có thể tràn và vi phạm thứ tự; `Comparator.comparingInt(Employee::getId)` hoặc `Integer.compare` an toàn về so sánh.

**Câu 9.** Với một ordered stream, `sorted(comparingInt(age))` có giữ thứ tự tương đối của hai nhân viên bằng tuổi không?

**Đáp án:** Có, vì `Stream.sorted` trên ordered stream ổn định. Nhưng nếu có thêm `thenComparingInt(id)`, thứ tự có thể đổi khi ID khác.

**Câu 10.** Getter tạo khóa có bắt buộc chỉ chạy một lần mỗi phần tử?

**Đáp án:** Không. Sorting có thể so sánh cùng phần tử nhiều lần, và `comparing` không hứa cache extractor. Nếu khóa đắt, cân nhắc tiền xử lý thành cặp khóa–đối tượng.

**Câu 11.** Sắp xếp một List với comparator không phân biệt hoa/thường có tự loại một trong hai chuỗi `"An"`/`"an"` không?

**Đáp án:** Không, sorting List chỉ đổi thứ tự. Nhưng TreeSet với comparator đó có thể xem chúng tương đương và chỉ giữ một.

**Câu 12.** Dùng `String.compareTo` có bảo đảm thứ tự tên tiếng Việt tự nhiên không?

**Đáp án:** Không. `String.compareTo` dựa trên natural lexicographic order của String, không đảm bảo quy tắc collation của tiếng Việt; khi cần dùng đúng quy tắc ngôn ngữ nên xét `Collator` và dữ liệu locale phù hợp.

## 16. Tổng kết

- **`Comparator.comparing(extractor)`** tạo comparator bằng cách trích xuất khóa `Comparable` từ từng đối tượng.
- **`Comparator.comparing(extractor, keyComparator)`** dùng comparator riêng khi khóa không có natural order hoặc có quy tắc nghiệp vụ khác.
- **`comparingInt/Long/Double`** là các overload dành cho khóa nguyên thủy; tránh boxing và tránh lỗi tự viết phép trừ để so sánh.
- **`thenComparing`** xây comparator nhiều tiêu chí; chỉ dùng tiêu chí sau nếu tiêu chí trước so sánh bằng `0`.
- **`reversed`** đảo toàn bộ comparator hiện tại tại vị trí gọi; đặt trước hoặc sau `thenComparing` làm thay đổi ý nghĩa.
- **`nullsFirst/nullsLast`** phải được đặt đúng tầng: object null hay **key** null.
- **Sắp xếp List không loại trùng**; `TreeSet/TreeMap` dùng `compare == 0` làm quan hệ tương đương, nên phải cân nhắc tính nhất quán với `equals`.
- **Extractor nên thuần, ổn định, không side effect**. Không giả định tính khóa một lần mỗi phần tử; chỉ tiền xử lý khóa khi hiệu năng chứng minh cần.
- Các API chính `comparing`, `thenComparing`, `comparingInt/Long/Double`, `reversed` và `nullsFirst/Last` có từ **Java 8** và vẫn được dùng trong Java hiện hành.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Comparator: comparing, comparingInt và thenComparing](https://docs.oracle.com/javase/8/docs/api/java/util/Comparator.html)
- [Oracle Java SE 26 — Comparator (bộ API hiện hành có các phương thức từ Java 8)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html)
- [Oracle Java SE 8 — List.sort và tính ổn định](https://docs.oracle.com/javase/8/docs/api/java/util/List.html)
- [Oracle Java SE 26 — Stream.sorted](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 26 — TreeSet: ordering consistent with equals](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html)
- [Oracle Java SE 26 — Collator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Collator.html)
