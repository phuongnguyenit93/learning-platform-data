# Comparator.thenComparing và sắp xếp theo nhiều tiêu chí trong Java

## 1. Bài toán: khi một tiêu chí không đủ

Trong ứng dụng, sắp xếp theo một trường thường chưa đáp ứng yêu cầu: nhân viên cần xếp theo **phòng ban tăng dần**, trong cùng phòng ban theo **đánh giá giảm dần**, tiếp đến **lương giảm dần**, **ngày vào làm tăng dần**, rồi **tên**; nếu vẫn bằng nhau cần một mã ID để kết quả dự đoán được.

`Comparator<T>` định nghĩa cách so sánh hai đối tượng kiểu `T` mà không bắt buộc `T` phải tự triển khai `Comparable<T>`. Kể từ Java 8, các phương thức `Comparator.comparing(...)` và `thenComparing(...)` giúp ghép các điều kiện theo **thứ tự ưu tiên từ trái sang phải**. Đây là API vẫn được sử dụng trong Java hiện đại.

Ý tưởng:

```text
So sánh a và b:
  1. Ưu tiên tiêu chí 1.
  2. Chỉ khi tiêu chí 1 bằng nhau, xét tiêu chí 2.
  3. Chỉ khi hai tiêu chí đầu đều bằng nhau, xét tiêu chí 3.
  ...
  n. Nếu mọi tiêu chí bằng nhau, Comparator trả 0.
```

Với các tiêu chí `team ASC`, `rating DESC`, `salary DESC`, `joined ASC`:

- Phòng A luôn trước phòng B, bất kể rating hoặc salary.
- Trong phòng A, rating 9 trước rating 8, dù người rating 8 có lương cao hơn.
- Hai người cùng phòng và cùng rating mới được so salary.
- Khi team/rating/salary bằng nhau mới xét ngày, tên, ID.

**Đây là phép sắp xếp theo thứ tự từ điển (lexicographic ordering)**. `thenComparing` không lấy trung bình các tiêu chí, không cộng điểm và không cho tiêu chí sau vượt qua tiêu chí trước.

Bài này dùng **Java 17+** cho chương trình ví dụ hoàn chỉnh (`record`, `Stream.toList()`). Bản thân `Comparator.thenComparing` và các overload `comparingInt/comparingLong/comparingDouble` đã có từ Java 8 và vẫn là API hiện hành.

## 2. Hợp đồng của Comparator và giá trị trả về

`Comparator<T>` là functional interface, có phương thức cốt lõi:

```java
int compare(T first, T second);
```

Giá trị trả về được hiểu theo **dấu**:

| Kết quả | Ý nghĩa |
| --- | --- |
| Số âm | `first` đứng **trước** `second` |
| `0` | Hai đối tượng **ngang nhau theo comparator này** |
| Số dương | `first` đứng **sau** `second` |

Không yêu cầu trả đúng `-1`, `0` hoặc `1`; chỉ dấu của số nguyên mới mang ý nghĩa. Cách gọi `compare(a,b)==0` không đồng nghĩa bắt buộc `a.equals(b)` bằng true — đây là sự khác nhau quan trọng, nhất là với `TreeSet` và `TreeMap`.

### 2.1. Ba tính chất cần tôn trọng

Một comparator hợp lệ cần có thứ tự nhất quán:

1. **Đối xứng theo dấu:** dấu của `compare(a,b)` là dấu đối của `compare(b,a)`.
2. **Bắc cầu:** nếu `a > b` và `b > c` theo comparator, thì `a > c`; tương tự cho quan hệ nhỏ hơn.
3. **Nhất quán khi một cặp so bằng 0:** nếu `compare(a,b)==0`, thì khi đem `a` và `b` so với một `c`, dấu kết quả phải tương ứng giống nhau.

`thenComparing` ghép các comparator thành thứ tự hợp lệ **nếu các comparator thành phần đúng luật**. Nó không thể sửa một comparator ban đầu có vòng lặp thứ tự, phụ thuộc biến toàn cục hoặc ngẫu nhiên.

### 2.2. Không so sánh số nguyên bằng phép trừ

**Dễ sai:**

```java
Comparator<Employee> byAge = (a, b) -> a.age() - b.age();
```

Đây là đoạn *anti-pattern* minh họa; `Employee` phải được định nghĩa trước. Nếu các giá trị `int` cách xa nhau, phép trừ có thể **overflow** và đổi dấu kết quả, vi phạm hợp đồng comparator.

**Nên dùng:**

```java
Comparator<Employee> byAge = Comparator.comparingInt(Employee::age);
```

Hoặc `Integer.compare(a.age(), b.age())`. Với `long` dùng `Long.compare(...)` hoặc `comparingLong(...)`. Không ép hiệu `long` sang `int`.

## 3. `comparing` tạo tiêu chí đầu tiên

Có các factory thường dùng:

| API | Dữ liệu khóa được rút ra | Lưu ý |
| --- | --- | --- |
| `Comparator.comparing(keyExtractor)` | Kiểu object `U` triển khai `Comparable` | Ví dụ `String`, `LocalDate` |
| `Comparator.comparing(keyExtractor, keyComparator)` | Object `U` với Comparator riêng | Ví dụ tên không phân biệt hoa/thường, khóa có thể null |
| `Comparator.comparingInt(toIntFunction)` | Primitive `int` | Tránh boxing khi so trường int |
| `Comparator.comparingLong(toLongFunction)` | Primitive `long` | Tránh boxing khi so trường long |
| `Comparator.comparingDouble(toDoubleFunction)` | Primitive `double` | Dùng ngữ nghĩa `Double.compare` |

Ví dụ trong lớp có `record Employee(int id, String name, int age, long salary) {}`:

```java
Comparator<Employee> byName = Comparator.comparing(Employee::name);
Comparator<Employee> byAge = Comparator.comparingInt(Employee::age);
Comparator<Employee> bySalary = Comparator.comparingLong(Employee::salary);
```

Đây là **đoạn trích minh họa**, cần định nghĩa `Employee` và import `java.util.Comparator`. Mặc định những comparator này sắp tăng dần theo natural order của khóa.

Nếu khóa là `String`, natural order dựa trên `String.compareTo` chứ không tự là quy tắc sắp theo ngôn ngữ Việt. Nếu cần sắp xếp có ngữ nghĩa locale, phải chọn comparator theo locale (ví dụ `Collator` thích hợp) và xác định rõ chính sách so chữ hoa, dấu và các phiên bản dữ liệu locale.

## 4. `thenComparing`: bộ phân giải khi các tiêu chí trước bằng nhau

Các overload quan trọng của `Comparator<T>`:

```java
Comparator<T> thenComparing(Comparator<? super T> other);

<U extends Comparable<? super U>>
Comparator<T> thenComparing(Function<? super T, ? extends U> keyExtractor);

<U>
Comparator<T> thenComparing(
    Function<? super T, ? extends U> keyExtractor,
    Comparator<? super U> keyComparator);

Comparator<T> thenComparingInt(ToIntFunction<? super T> keyExtractor);
Comparator<T> thenComparingLong(ToLongFunction<? super T> keyExtractor);
Comparator<T> thenComparingDouble(ToDoubleFunction<? super T> keyExtractor);
```

Đây là **các chữ ký rút gọn để đọc API**, không phải mã Java độc lập có thể khai báo ở top-level.

Những overload này cho phép dùng cả comparator sẵn có và hàm rút trích khóa:

```java
Comparator<Employee> order = Comparator.comparing(Employee::name)
        .thenComparingInt(Employee::age)
        .thenComparingLong(Employee::salary);
```

Nếu `name` bằng nhau thì mới so `age`; nếu `name` và `age` đều bằng nhau mới so `salary`. Mọi tiêu chí trong đoạn này đều tăng dần.

### 4.1. Ví dụ hai tiêu chí đơn giản

Có các bản ghi:

| Tên | Tuổi | ID |
| --- | ---: | ---: |
| An | 30 | 1 |
| Bình | 24 | 2 |
| An | 22 | 3 |

Với `comparing(name).thenComparingInt(age)`, thứ tự là:

```text
An, 22, id 3
An, 30, id 1
Bình, 24, id 2
```

**Vì sao Bình, 24 không đứng đầu?** Tiêu chí đầu tiên là tên. Tuổi chỉ được xét khi tên bằng nhau, không được ưu tiên hơn tên.

### 4.2. Nguyên tắc đánh giá lười theo từng tiêu chí

Trong chuỗi comparator, tiêu chí sau chỉ cần được xét nếu các tiêu chí trước đã so bằng `0`. Đó là logic ưu tiên từ điển. Nhưng đừng dựa vào số lần cụ thể hàm extractor được gọi để thực hiện side effect: sorting có thể so cùng một cặp nhiều lần, thứ tự so phụ thuộc thuật toán, và không được sửa dữ liệu đang sắp xếp.

**Sai về ý tưởng:**

```java
Comparator<Employee> order = Comparator.comparingInt(e -> {
    auditLog("compare " + e.id()); // side effect trong key extraction
    return e.age();
});
```

Đây là anti-pattern với `Employee` và `auditLog` giả định đã tồn tại. Extractor nên thuần (pure) và nhất quán. Để đo/log một sự kiện nghiệp vụ, làm trước hoặc sau sort, không lồng vào chức năng so sánh.

## 5. Nhiều tiêu chí tăng/giảm: đặt `reversed()` đúng vị trí

Đây là điểm dễ sai nhất khi học `thenComparing`.

Giả sử cần:

1. `team` tăng dần (A trước B).
2. `rating` giảm dần (9 trước 8).
3. `salary` giảm dần (7000 trước 5000).
4. `joined` tăng dần (ngày cũ trước).
5. `name` tăng dần.
6. `id` tăng dần để phân định các bản ghi nếu mọi trường trước trùng.

**Đúng:** đảo chiều **riêng comparator của tiêu chí cần giảm**, rồi thêm vào chuỗi:

```java
Comparator<Staff> ratingDesc =
        Comparator.comparingInt(Staff::rating).reversed();
Comparator<Staff> salaryDesc =
        Comparator.comparingLong(Staff::salary).reversed();

Comparator<Staff> order = Comparator.comparing(Staff::team)
        .thenComparing(ratingDesc)
        .thenComparing(salaryDesc)
        .thenComparing(Staff::joined)
        .thenComparing(Staff::name)
        .thenComparingInt(Staff::id);
```

Đoạn này dựa vào `record Staff(...)` được khai báo trong chương trình hoàn chỉnh ở mục 10. Có thể chọn cách viết tương đương `.thenComparing(Comparator.comparingInt(...).reversed())`, nhưng khai báo comparator giảm dần riêng làm thứ tự ưu tiên dễ đọc và tránh vấn đề suy luận kiểu trong một số ngữ cảnh.

### 5.1. Bẫy đảo chiều toàn bộ chuỗi

**Sai yêu cầu** nếu chỉ muốn đảo rating:

```java
Comparator<Staff> wrong = Comparator.comparing(Staff::team)
        .thenComparingInt(Staff::rating)
        .reversed();
```

Dấu `.reversed()` cuối cùng đảo **cả team lẫn rating**, làm phòng B đứng trước phòng A. Nó không chỉ đảo tiêu chí cuối.

Có thể tưởng tượng:

```text
A tăng, rating tăng:
    Comparator.comparing(team).thenComparingInt(rating)

A tăng, rating giảm:
    Comparator.comparing(team)
        .thenComparing(Comparator.comparingInt(rating).reversed())

A giảm, rating giảm:
    Comparator.comparing(team).thenComparingInt(rating).reversed()
```

Các dòng là **sơ đồ mô tả**, không phải code Java độc lập.

### 5.2. Sắp giảm bằng `reverseOrder` hoặc phương thức `reversed`

Với object key triển khai `Comparable`, có thể dùng key comparator:

```java
Comparator<Staff> byTeamDescending =
        Comparator.comparing(Staff::team, Comparator.reverseOrder());
```

Với trường primitive, `Comparator.comparingInt(Staff::rating).reversed()` hoặc `comparingLong(...).reversed()` thường rõ ràng và tránh boxing. Không dùng `(a,b) -> b.rating() - a.rating()`: phép trừ có thể tràn `int`.

## 6. Sắp xếp tên: case-insensitive và tie-break chính xác

Giả sử dữ liệu có `"Lan"` và `"lan"`:

- `String.CASE_INSENSITIVE_ORDER.compare("Lan","lan") == 0`.
- `"Lan".equals("lan") == false`.
- So sánh không phân biệt hoa/thường có thể là **một tiêu chí**, nhưng không bảo đảm phân định được hai chuỗi nguyên gốc.

Có thể ghép các mức:

```java
Comparator<Staff> byName = Comparator
        .comparing(Staff::name, String.CASE_INSENSITIVE_ORDER)
        .thenComparing(Staff::name)
        .thenComparingInt(Staff::id);
```

Ý nghĩa:

1. So `name` không phân biệt hoa/thường.
2. Nếu bước 1 bằng nhau, so `name` theo natural order của `String` để phân biệt viết hoa/thường.
3. Nếu chuỗi hoàn toàn bằng nhau, so `id`.

Trong chương trình mục 10, các tiêu chí này được đặt **sau** team/rating/salary/joined; chỉ có tác dụng khi các trường trước đã hòa.

**Cảnh báo ngôn ngữ:** `String.CASE_INSENSITIVE_ORDER` không cung cấp sắp xếp theo quy tắc từ điển địa phương (collation) cho mọi ngôn ngữ. Với tiếng Việt hay các ngôn ngữ có dấu và quy tắc riêng, xem xét `java.text.Collator` với `Locale` phù hợp và kiểm tra bằng dữ liệu thực. Không tự xóa dấu/đổi chữ thường rồi coi đó là mọi yêu cầu so khớp.

## 7. `nullsFirst`/`nullsLast`: phân biệt đối tượng null và khóa null

Khi dùng `comparing(Employee::name)`, nếu `name` bằng null, natural comparator thường ném `NullPointerException`. Có hai cấp độ xử lý khác nhau.

### 7.1. Khóa bên trong object có thể null

Ví dụ `Row(group, rank)`, trong đó `rank` là `Integer` có thể null. Yêu cầu:

- Group tăng dần.
- Trong cùng group, rank tăng dần.
- Rank **null đứng cuối**.
- Nếu rank giống nhau, ID tăng dần.

```java
Comparator<Row> nullableRank = Comparator.comparing(Row::group)
        .thenComparing(Row::rank,
                Comparator.nullsLast(Comparator.naturalOrder()))
        .thenComparingInt(Row::id);
```

Đây là đoạn trích từ chương trình hoàn chỉnh. `thenComparing(Row::rank, keyComparator)` chọn comparator chuyên biệt cho **giá trị rank**. `Comparator.nullsLast(...)` không có nghĩa tự cho phép `Row` bằng null: nó chỉ áp dụng cho **khóa `rank`**.

Cách tương tự khi trường là `LocalDate` nullable:

```java
Comparator<Staff> byMaybeJoined = Comparator.comparing(
        Staff::joined,
        Comparator.nullsLast(Comparator.naturalOrder()));
```

Đây là đoạn minh họa trong ngữ cảnh `Staff` có `LocalDate joined`.

### 7.2. Chính phần tử trong danh sách có thể null

Nếu toàn bộ object `Row` có thể null, bọc comparator của cả record:

```java
Comparator<Row> safeRows = Comparator.nullsLast(nullableRank);
```

Khi có `null` record, `safeRows` xếp nó cuối mà không gọi extractor trên null. Trong trường hợp cả **object và field** đều nullable, cần xử lý cả hai cấp: một `nullsLast` cho field và một `nullsLast` cho toàn bộ comparator.

### 7.3. Bẫy `reversed()` với null

Nếu viết:

```java
Comparator<Integer> c =
        Comparator.nullsLast(Comparator.naturalOrder()).reversed();
```

Bạn đảo **toàn bộ thứ tự**, nên **null thành đứng đầu**. Nếu yêu cầu số giảm dần nhưng null vẫn đứng cuối, đảo comparator **bên trong**:

```java
Comparator<Integer> descendingNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());
```

Tức là **`nullsLast(naturalOrder()).reversed()` khác `nullsLast(reverseOrder())`**. Hãy test rõ null khi có kết hợp thứ tự tăng/giảm.

**Khuyến nghị:** đừng dùng một giá trị sentinel như `Integer.MAX_VALUE` để thay null trừ khi hợp đồng dữ liệu cho phép; sentinel có thể trùng giá trị hợp lệ hoặc làm sai thứ tự.

## 8. Comparator nhiều tiêu chí và tính ổn định của sort

Sắp xếp **ổn định (stable sort)** nghĩa là nếu `compare(a,b)==0`, thứ tự tương đối ban đầu của `a` và `b` được giữ lại.

- `List.sort(comparator)` trong Java có bảo đảm stable.
- `Stream.sorted(comparator)` có bảo đảm stable **nếu Stream có encounter order**.
- Với Stream **unordered**, `sorted` không bảo đảm ổn định giữa những phần tử comparator cho bằng 0.
- `parallelStream().sorted(comparator)` trên nguồn có encounter order (như `List`) vẫn có bảo đảm stable; điều này không có nghĩa hành động của `parallel().forEach(...)` được gọi theo thứ tự.

Ví dụ với ba bản ghi cùng group và score:

```java
record Entry(int seq, String category, int score) {}

List<Entry> input = List.of(
        new Entry(9, "Q", 7),
        new Entry(3, "Q", 7),
        new Entry(1, "Q", 7)
);

Comparator<Entry> byCategoryThenScore =
        Comparator.comparing(Entry::category)
                .thenComparingInt(Entry::score);

List<Integer> stableIds = input.stream()
        .sorted(byCategoryThenScore)
        .map(Entry::seq)
        .toList(); // [9, 3, 1]
```

Đây là đoạn Java 17+ độc lập trong method khi đã import các lớp cần thiết. Comparator **không xét seq**, nên ba entry được coi là ngang nhau và stable sort giữ thứ tự nguồn.

**Có cần thêm tiêu chí ID?** Nếu yêu cầu **tổng thứ tự dự đoán được bất kể thứ tự nguồn**, thêm `thenComparingInt(Entry::seq)`. Nếu yêu cầu giữ thứ tự ban đầu của các mục có cùng key, **không** thêm tie-breaker đó, mà dùng một nguồn ordered và stable sort.

### 8.1. Ổn định không phải là “không có giá trị trùng”

Comparator trả 0 chỉ nói rằng hai đối tượng bằng nhau **theo các tiêu chí được chọn**. Nó không xóa bản ghi trùng. `sorted` không thực hiện dedup. Khi cần dedup, có các yêu cầu riêng và không được tự đồng nhất `compare==0` với `equals`.

### 8.2. Vì sao thứ tự ban đầu quan trọng?

Nguồn `List` thường có encounter order xác định. Nguồn `HashSet` hoặc một stream đã gọi `unordered()` có thể không có bảo đảm tương tự. Nếu dùng comparator thiếu tiêu chí cuối mà cần kết quả nhất quán giữa các nguồn và lần chạy, thêm khóa phân định cuối như một ID ổn định có thể phù hợp hơn dựa vào stable sort.

Đừng coi `Stream.toList()` là thao tác “khôi phục thứ tự nguồn”: nó chỉ thu các phần tử theo encounter order của pipeline sau khi `sorted` hoàn tất.

## 9. `Stream.sorted` và `List.sort` dùng cùng Comparator

Hai cách đều nhận một comparator hợp lệ nhưng tác động lên nguồn khác nhau.

### 9.1. Không sửa danh sách ban đầu

```java
List<Staff> sorted = staff.stream()
        .sorted(order)
        .toList();
```

Đây là đoạn trích giả định `staff` và `order` đã có. `Stream.sorted` là **intermediate operation**; việc sắp xếp thực sự xảy ra khi có terminal operation như `toList()`. Trong Java 17+, `Stream.toList()` cho danh sách kết quả **không hỗ trợ sửa đổi**; nguồn `staff` không bị sắp xếp trực tiếp.

Nếu cần giữ list mutable, tạo `new ArrayList<>(staff.stream().sorted(order).toList())` hoặc sắp một bản sao như dưới.

### 9.2. Sắp danh sách có thể sửa đổi

```java
List<Staff> mutableCopy = new ArrayList<>(staff);
mutableCopy.sort(order);
```

`List.sort` thay đổi **thứ tự của chính mutableCopy**. Không gọi `sort` trên `List.of(...)` hoặc danh sách trả bởi `Stream.toList()` nếu danh sách không hỗ trợ cập nhật; các lời gọi đó có thể ném `UnsupportedOperationException`.

Khi muốn sắp đối tượng trong collection ngay tại chỗ, kiểm tra khả năng sửa đổi. Với ứng dụng nhiều luồng, không tự cập nhật list đang bị luồng khác đọc/sửa mà không có đồng bộ thích hợp.

### 9.3. Dữ liệu null trong phần tử của nguồn

Với danh sách có null object, phải truyền comparator đã bọc `Comparator.nullsFirst(...)`/`nullsLast(...)` nếu muốn sort mà không lỗi. `Stream.sorted` không tự bỏ qua phần tử null.

### 9.4. Hiệu năng khi có nhiều tiêu chí

Một comparator nhiều tiêu chí thường có thể dùng trực tiếp cho dữ liệu nhỏ/vừa. Với nguồn lớn:

- So sánh thường gọi extractor **nhiều lần**, không phải đúng một lần mỗi phần tử.
- Nếu khóa rút trích đắt (parse ngày, gọi API, chuẩn hóa Unicode phức tạp), cân nhắc **tính trước sort key** rồi so dữ liệu đã chuẩn bị.
- Các `comparingInt/Long/Double` thường tránh boxing trong quá trình so giá trị primitive.
- Sort object thường ở lớp độ phức tạp **O(n log n)** về số phép so trong tình huống thông thường, nhưng thời gian thực còn phụ thuộc chi phí comparator, đặc điểm dữ liệu, bộ nhớ, thuật toán và JVM.
- `parallelStream().sorted` có overhead phân phối/ghép; không mặc định nhanh hơn trên danh sách nhỏ.
- Benchmark bằng workload thực tế nếu hiệu năng là yêu cầu; tránh “tối ưu” bằng bỏ mất tie-breaker nghiệp vụ.

## 10. Chương trình Java 17+ chạy được: nhiều tiêu chí, null, stability, parallel

Chương trình hoàn chỉnh dưới đây kiểm thử một comparator sáu tiêu chí chính và tiêu chí ID cuối, kiểm tra `reversed()` đặt sai vị trí, xử lý hai cấp độ null, stable sort và ảnh hưởng của comparator không nhất quán với `equals`.

Tạo tệp **`MultiCriteriaComparatorDemo.java`**:

```java
import java.util.*;
import java.time.*;
import java.util.stream.*;

public class MultiCriteriaComparatorDemo {
    record Staff(int id, String team, String name, int rating,
                 long salary, LocalDate joined) {}

    record Row(int id, String group, Integer rank) {}

    record Entry(int seq, String category, int score) {}

    static void check(boolean ok, String what) {
        if (!ok) {
            throw new AssertionError(what);
        }
    }

    static List<Integer> ids(List<Staff> list) {
        return list.stream().map(Staff::id).toList();
    }

    public static void main(String[] args) {
        List<Staff> staff = List.of(
            new Staff(104, "A", "Minh", 8, 7000,
                      LocalDate.parse("2021-02-02")),
            new Staff(107, "A", "lan", 9, 5000,
                      LocalDate.parse("2023-01-10")),
            new Staff(103, "B", "Binh", 10, 6200,
                      LocalDate.parse("2022-06-01")),
            new Staff(101, "A", "Lan", 9, 5000,
                      LocalDate.parse("2023-01-10")),
            new Staff(102, "A", "An", 9, 5000,
                      LocalDate.parse("2024-04-01")),
            new Staff(105, "A", "Binh", 9, 6500,
                      LocalDate.parse("2023-03-05")),
            new Staff(106, "B", "An", 10, 6200,
                      LocalDate.parse("2022-01-01")),
            new Staff(108, "A", "Lan", 9, 5000,
                      LocalDate.parse("2023-01-10"))
        );

        Comparator<Staff> ratingDesc =
                Comparator.comparingInt(Staff::rating).reversed();
        Comparator<Staff> salaryDesc =
                Comparator.comparingLong(Staff::salary).reversed();

        Comparator<Staff> order = Comparator.comparing(Staff::team)
                .thenComparing(ratingDesc)
                .thenComparing(salaryDesc)
                .thenComparing(Staff::joined)
                .thenComparing(Staff::name, String.CASE_INSENSITIVE_ORDER)
                .thenComparing(Staff::name)
                .thenComparingInt(Staff::id);

        List<Integer> expected =
                List.of(105, 101, 108, 107, 102, 104, 106, 103);

        List<Integer> ordered = staff.stream()
                .sorted(order).map(Staff::id).toList();
        check(ordered.equals(expected), "full ordering");
        System.out.println("sortedIds=" + ordered);

        List<Integer> parallel = staff.parallelStream()
                .sorted(order).map(Staff::id).toList();
        check(parallel.equals(expected), "parallel ordered source");
        System.out.println("parallelEqual=" + ordered.equals(parallel));

        List<Staff> mutable = new ArrayList<>(staff);
        mutable.sort(order);
        check(ids(mutable).equals(expected), "mutable list sort");
        System.out.println("mutableListSame=" +
                ids(mutable).equals(expected));

        // .reversed() sau cùng đảo TOÀN BỘ tiêu chí trong chuỗi.
        Comparator<Staff> wholeReverse =
                Comparator.comparing(Staff::team)
                    .thenComparingInt(Staff::rating).reversed();
        System.out.println("wholeReverseTeams=" + staff.stream()
                .sorted(wholeReverse).map(Staff::team)
                .distinct().toList());

        // Null trong một trường Integer (rank) phải đặt chính sách rõ.
        Comparator<Row> nullableRank = Comparator.comparing(Row::group)
                .thenComparing(Row::rank,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparingInt(Row::id);

        List<Row> rows = List.of(
                new Row(3, "Y", null),
                new Row(1, "X", 2),
                new Row(2, "X", null),
                new Row(4, "X", 1),
                new Row(5, "X", 2));
        List<Integer> rowIds = rows.stream().sorted(nullableRank)
                .map(Row::id).toList();
        check(rowIds.equals(List.of(4, 1, 5, 2, 3)), "null ranks");
        System.out.println("nullRankIds=" + rowIds);

        // Null cho TOÀN BỘ phần tử Row cần wrapper nullsLast bên ngoài.
        List<Row> withNull = Arrays.asList(
                new Row(2, "X", null),
                null,
                new Row(1, "X", 2));
        List<String> safeRows = withNull.stream()
                .sorted(Comparator.nullsLast(nullableRank))
                .map(x -> x == null ? "null" : "" + x.id())
                .toList();
        check(safeRows.equals(List.of("1", "2", "null")),
                "null records");
        System.out.println("nullObjectIds=" + safeRows);

        // Stable sort: 3 entry có cùng mọi khóa comparator.
        List<Entry> input = List.of(
                new Entry(9, "Q", 7),
                new Entry(3, "Q", 7),
                new Entry(1, "Q", 7));
        Comparator<Entry> byCategoryThenScore =
                Comparator.comparing(Entry::category)
                        .thenComparingInt(Entry::score);
        List<Integer> stableIds = input.stream()
                .sorted(byCategoryThenScore)
                .map(Entry::seq).toList();
        check(stableIds.equals(List.of(9, 3, 1)),
                "stable ordered stream");
        System.out.println("stableTieIds=" + stableIds);

        // TreeSet dùng compare==0 để xác định trùng theo ordering.
        TreeSet<String> insensitive =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        insensitive.add("Lan");
        insensitive.add("lan");
        System.out.println("treeSetCaseInsensitiveSize=" +
                insensitive.size());

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac MultiCriteriaComparatorDemo.java
java MultiCriteriaComparatorDemo
```

**Stdout chuẩn:**

```text
sortedIds=[105, 101, 108, 107, 102, 104, 106, 103]
parallelEqual=true
mutableListSame=true
wholeReverseTeams=[B, A]
nullRankIds=[4, 1, 5, 2, 3]
nullObjectIds=[1, 2, null]
stableTieIds=[9, 3, 1]
treeSetCaseInsensitiveSize=1
ALL CHECKS PASSED
```

### 10.1. Giải thích thứ tự kết quả

- **105 đầu tiên:** nhóm A, rating 9, salary 6500 — cao hơn các nhân viên cùng nhóm/cùng rating có salary 5000.
- **101, 108, 107:** cùng A, rating 9, salary 5000, ngày 2023-01-10. `"Lan"` trước `"lan"` theo tie-break natural order sau bước case-insensitive; hai bản ghi `"Lan"` dùng ID 101 trước 108.
- **102:** cũng A/rating 9/salary 5000 nhưng vào làm ngày 2024-04-01, sau nhóm cùng lương đã vào ngày 2023-01-10.
- **104:** rating 8, nên xuống sau mọi rating 9 trong phòng A, dù salary 7000.
- **106, 103:** thuộc phòng B, luôn sau phòng A. Cả hai rating 10 và salary 6200; `joined` của 106 sớm hơn 103.
- `parallelEqual=true` và `mutableListSame=true`: cùng comparator cho kết quả giống nhau trên nguồn List đã xác định thứ tự và dữ liệu không đổi.
- `wholeReverseTeams=[B,A]`: chứng minh `reversed()` đặt **sau toàn bộ chuỗi** đảo cả team.
- `nullRankIds=[4,1,5,2,3]`: nhóm X trước Y; trong X, rank 1 trước rank 2, rank null cuối nhóm; ID 1 trước 5 khi cùng rank 2.
- `nullObjectIds=[1,2,null]`: rank null sau rank 2, còn chính record null xếp cuối toàn bộ.
- `stableTieIds=[9,3,1]`: comparator không xét `seq`, nên stable sort giữ thứ tự ban đầu của các phần tử ngang nhau.
- `treeSetCaseInsensitiveSize=1`: `TreeSet` dùng comparator để xác định tính tương đương theo thứ tự; `"Lan"` và `"lan"` không bằng nhau theo `String.equals` nhưng so bằng 0 theo comparator được chọn.

## 11. Comparator có ảnh hưởng tới `TreeSet` và `TreeMap` khác sort như thế nào?

Một comparator không chỉ dùng để sắp xếp List. Khi truyền vào `TreeSet` hoặc `TreeMap`, nó quyết định **thứ tự và sự tương đương của phần tử/khóa**.

Với `List.sort` hoặc `Stream.sorted`:

- Hai object comparator trả 0 vẫn **đều tồn tại** trong kết quả; stable sort giữ thứ tự tương đối nếu nguồn có thứ tự.
- Không có bước tự xóa duplicates chỉ vì `compare==0`.

Với `TreeSet` hoặc `TreeMap`:

- Nếu `compare(a,b)==0`, cấu trúc coi chúng là cùng vị trí/key theo ordering; thêm bản ghi thứ hai có thể không tạo phần tử/key mới.
- Nếu comparator không nhất quán với `equals`, hành vi từ góc nhìn hợp đồng `Set`/`Map` có thể gây ngạc nhiên. Hãy chủ động xác định yêu cầu “trùng nhau” khi dùng sorted collections.

Ví dụ `new TreeSet<>(String.CASE_INSENSITIVE_ORDER)` sau khi thêm `"Lan"` và `"lan"` chỉ giữ một phần tử, dù `String.equals` phân biệt hoa/thường. Trong một danh sách dùng `sorted(String.CASE_INSENSITIVE_ORDER)`, **cả hai chuỗi vẫn còn**.

**Chọn tie-breaker phù hợp:** Nếu cần bảo toàn cả hai khóa trong TreeSet/TreeMap, phải chọn comparator phân biệt chúng, ví dụ sau case-insensitive thêm natural-order. Với object phức tạp, thêm ID ổn định nếu đó là quy tắc nghiệp vụ, nhưng không thêm ID chỉ vì mục tiêu “vượt qua” hợp đồng tương đương của map/set.

## 12. Dùng `thenComparingDouble` và những trường hợp số thực

`thenComparingDouble` giúp tránh boxing `double`:

```java
record Measurement(String sensor, double value, long timestamp) {}

Comparator<Measurement> measurementOrder =
        Comparator.comparing(Measurement::sensor)
                .thenComparingDouble(Measurement::value)
                .thenComparingLong(Measurement::timestamp);
```

Đây là đoạn Java 17+ minh họa độc lập trong một method. Các tiêu chí là sensor tăng, value tăng, timestamp tăng.

Đối với `double`, comparator dùng ngữ nghĩa tương ứng `Double.compare`:

- `NaN` có trật tự so sánh được định nghĩa; không tự tương đương “không có dữ liệu”.
- `-0.0` và `+0.0` có thể được phân biệt bởi `Double.compare` dù toán tử `==` coi chúng bằng nhau.
- Dữ liệu `Infinity` cần chính sách rõ nếu ứng dụng không cho giá trị vô cực.
- Không dùng `double` cho tiền nếu bắt buộc tính chính xác thập phân; dùng `BigDecimal` và comparator tương ứng khi đó là kiểu dữ liệu thực.

Với `BigDecimal`, `BigDecimal.compareTo` theo giá trị số và có thể coi `1.0` bằng `1.00`, trong khi `BigDecimal.equals` còn xét scale. Đừng bỏ qua sự không nhất quán đó nếu dùng làm khóa trong `TreeMap`/`TreeSet`.

## 13. Chuyên sâu: khi nào thêm tiêu chí quyết định cuối cùng?

Có ba cách thiết kế phổ biến:

### A. Giữ nguyên thứ tự đầu vào khi các khóa hòa

Chỉ xét những tiêu chí nghiệp vụ thật cần. Phù hợp với màn hình sắp xếp theo nhóm mà các mục cùng giá trị giữ nguyên thứ tự hiển thị. Khi đó cần nguồn có encounter order và phép sắp xếp ổn định.

### B. Muốn kết quả nhất quán không phụ thuộc thứ tự nguồn

Thêm một **tie-breaker duy nhất và ổn định** như ID:

```java
Comparator<Staff> deterministic = Comparator.comparing(Staff::team)
        .thenComparingInt(Staff::id);
```

Đoạn minh họa: team tăng, sau đó ID tăng. Với mỗi ID khác nhau, kết quả phân định được các bản ghi dù nguồn không có thứ tự ổn định.

### C. Một số tiêu chí chỉ là khóa phụ mang tính trình bày

Ví dụ sắp theo điểm giảm rồi tên hiển thị, nhưng dữ liệu có thể đổi tên. Nếu comparator được dùng cho `TreeSet`/`TreeMap`, việc thay đổi khóa phụ khi phần tử đang nằm trong cấu trúc là nguy hiểm: thứ tự nội bộ có thể không còn phù hợp, dẫn đến lookup sai. Hãy dùng key ổn định hoặc remove–update–add theo quy trình an toàn.

**Nguyên tắc:** “Quyết định cuối cùng” không phải luôn bắt buộc. Nó cần phù hợp với nơi comparator được dùng: sort một lần để hiển thị, hay sắp xếp/định danh lâu dài trong một ordered collection.

## 14. Những lỗi thực tế và cách khắc phục

| Lỗi | Triệu chứng | Cách sửa |
| --- | --- | --- |
| Đặt `.reversed()` ở cuối toàn bộ chuỗi khi chỉ muốn giảm một cột | Đảo cả tiêu chí trước đó | Tách comparator con rồi đảo riêng |
| So `int` bằng `a.score()-b.score()` | Overflow, sai dấu, vi phạm hợp đồng | `comparingInt`/`Integer.compare` |
| So `long` bằng cast hiệu sang `int` | Mất bit, sai thứ tự | `comparingLong`/`Long.compare` |
| Quên null trong khóa `name`/`rank` | `NullPointerException` khi sort | `thenComparing(extractor, nullsFirst/Last(...))` |
| Chỉ bọc null cho field nhưng danh sách chứa object null | NPE khi gọi extractor trên object null | Bọc comparator toàn phần bằng `nullsLast` |
| `nullsLast(naturalOrder()).reversed()` | Null bất ngờ lên đầu | `nullsLast(reverseOrder())` |
| Comparator chỉ xét rating, rồi đưa vào TreeSet | Các bản ghi rating bằng nhau bị coi cùng phần tử | Chọn comparator nhất quán với định danh của set |
| Dùng `String.CASE_INSENSITIVE_ORDER` như thể là thứ tự theo locale tiếng Việt | Thứ tự không như mong muốn | Chọn collation có Locale phù hợp |
| Thay đổi trường tham gia so sánh trong TreeMap/TreeSet | Cấu trúc thứ tự không còn đúng | Dùng khóa ổn định |
| Mutating object trong key extractor | Sort khó đoán hoặc lỗi hợp đồng | Hàm extractor pure, dữ liệu ổn định |
| Gọi `List.of(...).sort(...)` | `UnsupportedOperationException` | Tạo `new ArrayList<>(...)` |
| Cho rằng `HashSet.stream().sorted` luôn stable cho các phần tử so bằng nhau | Thứ tự tie không được bảo đảm | Thêm tie-breaker hoặc dùng nguồn ordered |
| Mong `parallel().forEach` in ra theo thứ tự sorted | Log xuất hiện khác thứ tự | Thu bằng `toList()` hoặc `forEachOrdered` nếu cần thứ tự |

## 15. Kiểm thử comparator nhiều tiêu chí

Đừng chỉ test rằng danh sách đã có vẻ được sắp đúng. Một bộ test đáng tin nên có:

1. **Mỗi tiêu chí một cặp dữ liệu chỉ khác ở tiêu chí đó.** Kiểm tra team quyết định trước rating, rating trước salary, và tiếp tục tới ID.
2. **Nhiều key cùng nhau tạo tie.** Chỉ khi các tiêu chí trước bằng nhau thì tiêu chí sau mới được quyền phân định.
3. **Giá trị ở biên:** `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE`, `Long.MAX_VALUE` để phát hiện overflow do tự trừ.
4. **Null ở cả khóa và object** nếu domain cho phép null, kiểm tra đúng `nullsFirst`/`nullsLast`.
5. **Tên khác nhau về case/dấu** nếu ứng dụng có yêu cầu text locale.
6. **Nguồn ordered, nhiều phần tử comparator bằng 0:** kiểm tra tính stable hoặc thêm ID để xác định thứ tự.
7. **Nguồn không có encounter order:** tránh assert thứ tự tie trừ khi đã thêm khóa phân định.
8. **Kết quả đồng nhất giữa List.sort và Stream.sorted** trên một nguồn không thay đổi và cùng comparator.
9. **Kết quả song song** trên nguồn ordered nếu dùng parallel stream, nhưng không assert thứ tự gọi `forEach`.
10. **Kiểm tra luật comparator bằng thuộc tính** (property-based) trên các bộ ba (`a,b,c`): anti-symmetry, transitivity, consistency of compare-zero.

Một test oracle đơn giản:

```java
List<Integer> expected = List.of(105, 101, 108, 107, 102, 104, 106, 103);
List<Integer> actual = staff.stream().sorted(order)
        .map(Staff::id).toList();
if (!actual.equals(expected)) {
    throw new AssertionError("Unexpected order: " + actual);
}
```

Đoạn này dùng `staff`, `order` từ chương trình mục 10. **Expected được tính từ quy tắc nghiệp vụ trước khi chạy chương trình**, không phải lấy một cách sắp xếp sai làm chuẩn so cho cách thứ hai.

### 15.1. Test luật comparator không phụ thuộc số âm/dương cụ thể

`compare(a,b)` có thể trả bất kỳ số âm/dương, vì vậy nên kiểm tra dấu:

```java
int result = comparator.compare(a, b);
boolean before = result < 0;
```

Đoạn này trong ngữ cảnh đã có `comparator`, `a` và `b`. Không assert `result == -1` vì đó không phải hợp đồng chung.

## 16. Tình huống nào không nên dùng chuỗi `thenComparing` quá dài?

Một chuỗi comparator dài là công cụ tốt khi người đọc hiểu rõ ưu tiên từng trường. Tuy nhiên, không phải bài toán sắp xếp nào cũng là lexicographic order:

- **Xếp hạng có trọng số:** cần tính `weightedScore` một cách đúng miền dữ liệu rồi so theo score. `thenComparing` không phải phép cộng trọng số.
- **Thứ tự theo quy tắc nghiệp vụ phức tạp:** ví dụ trạng thái khẩn cấp đứng đầu dù nhiều trường khác. Có thể rút ra `priorityRank`/`statusRank` ổn định và dùng nó làm tiêu chí đầu.
- **Phụ thuộc dữ liệu bên ngoài tại thời điểm so:** như gọi HTTP để lấy hạng, có thể bất nhất và chậm; hãy lấy snapshot/tính sort keys trước khi sort.
- **Nhu cầu locale tinh vi:** chuẩn hóa dữ liệu văn bản/Collator theo chính sách đã xác nhận, không tự đan nhiều `String.toLowerCase()` khi không hiểu cách xử lý Unicode.
- **Lựa chọn top-N trên nguồn rất lớn:** sorting toàn bộ dữ liệu có thể tốn tài nguyên; cân nhắc thuật toán chọn ứng viên/priority queue nếu nghiệp vụ chỉ cần N mục đầu. Comparator vẫn hữu ích để định nghĩa thứ tự, nhưng không nhất thiết phải sắp toàn bộ.

Ưu tiên làm rõ **thứ tự các tiêu chí và chiều tăng/giảm** bằng bảng hoặc tên biến comparator. Nếu dùng nhiều API, xây comparator một lần và sử dụng lại khi logic phải nhất quán, không viết một biểu thức khác nhau ở mỗi nơi.

## 17. Bài luyện tập và đáp án

**Bài 1.** Muốn sort `Ticket(priority:int, createdAt:LocalDate, id:long)` theo priority **giảm**, createdAt **tăng**, id **tăng**, viết comparator.

```java
Comparator<Ticket> priorityDesc =
        Comparator.comparingInt(Ticket::priority).reversed();
Comparator<Ticket> order = priorityDesc
        .thenComparing(Ticket::createdAt)
        .thenComparingLong(Ticket::id);
```

Đây là đoạn minh họa yêu cầu đã định nghĩa `Ticket`. Không viết `...thenComparingLong(...).reversed()` nếu chỉ muốn đảo priority, vì nó sẽ đảo cả chuỗi.

**Bài 2.** `Comparator.comparing(User::city).thenComparingInt(User::age)` và danh sách có người ở thành phố B tuổi 20, thành phố A tuổi 40. Ai đứng trước?

**Đáp án:** Người ở thành phố A, vì city là tiêu chí đầu, tuổi chỉ xét trong cùng city.

**Bài 3.** Có hai người cùng tên và cùng tuổi, sort theo tên/tuổi (không thêm ID) có làm mất một bản ghi không?

**Đáp án:** Không. `List.sort` / `Stream.sorted` không xóa bản ghi. Stable sort giữ thứ tự tương đối trong nguồn ordered.

**Bài 4.** `Comparator.nullsLast(Comparator.naturalOrder()).reversed()` đặt null ở đâu?

**Đáp án:** Ở **đầu**, vì `reversed` đảo toàn bộ. Muốn số giảm nhưng null vẫn cuối, dùng `nullsLast(reverseOrder())`.

**Bài 5.** Dùng `String.CASE_INSENSITIVE_ORDER` với TreeSet rồi thêm `"Lan"` và `"lan"`; size là mấy?

**Đáp án:** 1 vì comparator cho chúng bằng 0. Nếu cần giữ cả hai như hai khóa khác nhau, comparator phải có tie-break theo case hoặc điều chỉnh mô hình dữ liệu.

**Bài 6.** Khi `Stream.sorted(comparator)` lấy dữ liệu từ một `HashSet`, có thể dựa vào thứ tự đầu vào để phân biệt các phần tử `compare==0` không?

**Đáp án:** Không; HashSet không có encounter order được bảo đảm. Thêm khóa phân định cuối nếu yêu cầu thứ tự hoàn toàn xác định.

**Bài 7.** Nếu `Comparator.compare(a,b)` trả -50 thay vì -1 thì có sai không?

**Đáp án:** Không. Dấu âm mới là ý nghĩa, giá trị tuyệt đối không được quy định.

**Bài 8.** Nên dùng `thenComparingInt(Item::quantity)` hay `thenComparing(Item::quantity)` với quantity là `int`?

**Đáp án:** Cả hai có thể dẫn tới cách sắp theo số lượng, nhưng `thenComparingInt` cho primitive extractor và tránh boxing trung gian, thể hiện ý định rõ ràng.

**Bài 9.** Khi một record mutable nằm trong TreeMap và bạn sửa trường được dùng cho comparator, có nên tiếp tục tin các phép lookup theo thứ tự cũ không?

**Đáp án:** Không. Thiết kế key không đổi khi đang được lưu, hoặc remove rồi thêm lại một cách hợp lệ.

**Bài 10.** Vì sao comparator nhiều tiêu chí không nên lấy điểm “phụ” trước khi biết tiêu chí chính bằng nhau?

**Đáp án:** Vì `thenComparing` biểu diễn thứ tự ưu tiên; kết quả của tiêu chí chính khác 0 đã quyết định thứ tự. Tiêu chí sau không được thay thế quyết định đó.

## 18. Checklist áp dụng thực tế

- [ ] Đã viết rõ thứ tự ưu tiên: tiêu chí 1, 2, 3... và chiều tăng/giảm của từng tiêu chí.
- [ ] Dùng `Comparator.comparing` với khóa Comparable, hoặc `comparingInt/Long/Double` cho trường primitive phù hợp.
- [ ] Dùng `thenComparing` cho tiêu chí phụ **chỉ khi các tiêu chí trước hòa**.
- [ ] Đảo chiều riêng comparator con khi cần giảm một tiêu chí; không đặt `reversed()` cuối chuỗi nếu không muốn đảo tất cả.
- [ ] Không so `int/long` bằng phép trừ dễ overflow.
- [ ] Nếu khóa null hoặc object null có thể xuất hiện, đặt chính sách `nullsFirst/nullsLast` ở đúng cấp.
- [ ] Nếu dùng `String.CASE_INSENSITIVE_ORDER`, biết rõ nó không thay thế mọi yêu cầu collation theo locale.
- [ ] Nếu cần thứ tự tuyệt đối, bổ sung tie-breaker ổn định như ID; nếu cần stable ties, đừng thêm trường ngoài yêu cầu.
- [ ] Hiểu `List.sort` là inplace trên mutable list, `Stream.sorted` không sửa danh sách nguồn.
- [ ] Không dùng comparator có trạng thái thay đổi hoặc extractor có side effect.
- [ ] Nếu dùng `TreeSet/TreeMap`, cân nhắc quan hệ giữa `compare==0` và `equals`.
- [ ] Kiểm thử từng cấp tie-break, null, dữ liệu biên, stable order và expected độc lập trước khi dùng production.

## Tham khảo chính thức (API hiện hành)

- [Oracle Java SE 25 — Comparator<T>: comparing, thenComparing, thenComparingInt/Long/Double, nullsFirst/nullsLast, reversed](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html)
- [Oracle Java SE 25 — Stream.sorted: bảo đảm stable với ordered stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 25 — List.sort và hợp đồng stable sorting](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html)
- [Oracle Java SE 25 — TreeSet, quan hệ comparator và equals](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html)
- [Oracle Java SE 25 — TreeMap và khóa được so bởi Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html)

**Ghi nhớ:** `thenComparing` giải quyết bài toán **thứ tự ưu tiên nhiều tiêu chí**. Tiêu chí sau chỉ có tác dụng khi mọi tiêu chí trước cho kết quả so sánh bằng 0; hãy cấu hình chiều tăng/giảm, null và quy tắc tie-break thật rõ trước khi tối ưu.
