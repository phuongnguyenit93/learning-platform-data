# `Comparator.comparing()` và các biến thể `comparingInt()`, `comparingLong()`, `comparingDouble()`

Khi cần sắp xếp danh sách đối tượng Java theo một thuộc tính, ta thường không cần tự viết đầy đủ `compare(a, b)`. Interface `java.util.Comparator<T>` cung cấp các **phương thức factory tĩnh** tạo comparator từ một hàm lấy khóa (*key extractor*):

- `Comparator.comparing(...)`: lấy khóa kiểu đối tượng, so sánh khóa theo thứ tự tự nhiên hoặc bằng một comparator khác.
- `Comparator.comparingInt(...)`: lấy khóa nguyên thủy `int`.
- `Comparator.comparingLong(...)`: lấy khóa nguyên thủy `long`.
- `Comparator.comparingDouble(...)`: lấy khóa nguyên thủy `double`.

Cả bốn đều tạo một `Comparator<T>` để truyền vào `List.sort(...)`, `Collections.sort(...)`, `Stream.sorted(...)`, `Arrays.sort(...)`, hoặc các API cần một thứ tự sắp xếp. Khác biệt chủ yếu nằm ở **kiểu khóa** và **cách so sánh khóa**.

## 1. `Comparator<T>` quyết định thứ tự như thế nào?

Các factory trong bài tạo một `Comparator<T>` bằng cách **lấy khóa** từ mỗi đối tượng và so sánh các khóa đó. Ví dụ:

~~~java
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);
~~~

Đây là mảnh mã giả định `Employee.age()` trả `int`. `Employee::age` tương đương `e -> e.age()` khi làm key extractor.

Kết quả `compare(a,b)` mang dấu âm nếu a đứng trước b, bằng 0 nếu ngang hàng theo khóa đã chọn, dương nếu a đứng sau b. Các quy tắc đối dấu, bắc cầu và nhóm so sánh bằng 0 vẫn áp dụng; phương thức factory không miễn trách nhiệm bảo đảm khóa hợp lệ và ổn định. Trọng tâm ở đây là **chọn overload đúng kiểu khóa**, bao gồm primitive, nullable và `double` có giá trị đặc biệt.
## 2. So sánh nhanh bốn phương thức factory

| Factory | Kiểu hàm lấy khóa | So sánh khóa | Trường hợp điển hình |
| --- | --- | --- | --- |
| `comparing(keyExtractor)` | `Function<? super T, ? extends U>`, với `U` có thứ tự tự nhiên | `U.compareTo(...)` qua `Comparable` | `String`, `LocalDate`, `BigDecimal`, enum… |
| `comparing(keyExtractor, keyComparator)` | `Function<? super T, ? extends U>` | Comparator riêng của khóa | Không phân biệt hoa thường, khóa nullable, thứ tự nghiệp vụ |
| `comparingInt(keyExtractor)` | `ToIntFunction<? super T>` | `Integer.compare(...)` | Tuổi, số lượng, mức ưu tiên `int` |
| `comparingLong(keyExtractor)` | `ToLongFunction<? super T>` | `Long.compare(...)` | Timestamp dạng `long`, số lượng lớn, sequence |
| `comparingDouble(keyExtractor)` | `ToDoubleFunction<? super T>` | `Double.compare(...)` | Điểm số, tỷ lệ, số đo `double` |

Ba hàm nguyên thủy cho phép extractor trả trực tiếp `int`, `long` hoặc `double`, tránh đóng hộp khóa đó thành `Integer`, `Long` hoặc `Double` để gọi `compareTo`. Điều này giúp biểu đạt rõ ý định và có thể giảm chi phí boxing khi sắp xếp nhiều phần tử. Không có nghĩa mọi phần của quá trình sort sẽ hoàn toàn không cấp phát bộ nhớ.

Lưu ý: `comparingInt`/`Long`/`Double` **không** có overload nhận thêm `Comparator` cho khóa nguyên thủy. Muốn quy tắc so khác tự nhiên, hãy cân nhắc biến đổi khóa có kiểm soát, `reversed()`, hoặc một comparator tự viết phù hợp. Riêng `comparing(...)` có overload nhận comparator thứ hai cho khóa kiểu đối tượng.

## 3. `comparing()` với khóa có `Comparable`

Giả sử `Product` có tên `String`:

~~~java
Comparator<Product> byName =
    Comparator.comparing(Product::name);
~~~

Đây là một mảnh mã giả định `Product.name()` trả `String`. Vì `String` triển khai `Comparable<String>`, comparator mới dùng thứ tự tự nhiên của chuỗi, dựa trên thứ tự so từ điển theo giá trị UTF-16; không mặc nhiên giống quy tắc sắp xếp tên tiếng Việt theo locale.

Một số ví dụ thông dụng:

~~~java
Comparator<Order> byDate =
    Comparator.comparing(Order::createdOn); // LocalDate

Comparator<Invoice> byAmount =
    Comparator.comparing(Invoice::total);   // BigDecimal
~~~

Các dòng này **chỉ minh họa cú pháp** nếu lớp `Order` và `Invoice` có phương thức tương ứng. `LocalDate` và `BigDecimal` cung cấp `compareTo()`, nên thích hợp cho overload một tham số.

Nếu kiểu khóa không triển khai `Comparable` phù hợp, overload `comparing(keyExtractor)` không thể dựa vào thứ tự tự nhiên; hãy truyền một `Comparator<U>` xác định quy tắc so khóa:

~~~java
Comparator<Product> byNameIgnoringCase =
    Comparator.comparing(
        Product::name,
        String.CASE_INSENSITIVE_ORDER
    );
~~~

Điều này cũng nhấn mạnh rằng comparator mô tả **thứ tự**, không nhất thiết định nghĩa bằng nhau giống `equals()`: hai chuỗi khác chữ hoa/thường có thể cho `compare(...) == 0` với `CASE_INSENSITIVE_ORDER` nhưng `String.equals()` vẫn trả `false`.

## 4. `comparingInt()`, `comparingLong()` và `comparingDouble()`

### `comparingInt(ToIntFunction)`

~~~java
Comparator<Employee> byAge =
    Comparator.comparingInt(Employee::age);
~~~

Nếu hai tuổi lần lượt là `22` và `30`, `byAge.compare(e22, e30)` là số âm. Không cần viết phép trừ `e22.age() - e30.age()`.

**Tránh so số nguyên bằng phép trừ:**

~~~java
// SAI: tràn số có thể đảo dấu kết quả.
Comparator<Employee> risky =
    (a, b) -> a.age() - b.age();

// ĐÚNG: Comparator.comparingInt dùng cách so sánh không tràn số.
Comparator<Employee> safe =
    Comparator.comparingInt(Employee::age);
~~~

Với `int`, phép trừ `Integer.MIN_VALUE - Integer.MAX_VALUE` có thể tràn và trả dấu sai; `Integer.compare` không mắc lỗi đó. Đoạn trên là mảnh mã minh họa trong phạm vi lớp `Employee`.

### `comparingLong(ToLongFunction)`

~~~java
Comparator<Event> byTimestamp =
    Comparator.comparingLong(Event::timestamp);
~~~

Dùng khi khóa là `long`, chẳng hạn epoch milliseconds, số bản ghi hoặc mã thứ tự lớn. Đặc biệt không ép hiệu hai `long` sang `int`:

~~~java
// SAI: vừa có nguy cơ tràn phép trừ long vừa có nguy cơ mất bit.
Comparator<Event> risky =
    (a, b) -> (int) (a.timestamp() - b.timestamp());
~~~

Cách viết `comparingLong` dùng `Long.compare` và bảo toàn thứ tự trên toàn miền `long`. Nếu dữ liệu là thời điểm, phải biết kiểu số đang lưu có cùng đơn vị và cùng quy ước thời gian; comparator không tự chuyển đổi giây sang mili giây.

### `comparingDouble(ToDoubleFunction)`

~~~java
Comparator<Measurement> byValue =
    Comparator.comparingDouble(Measurement::value);
~~~

Factory dùng `Double.compare`, có các đặc điểm cần nhớ:

- `-0.0` được xếp **trước** `+0.0` dù biểu thức số học `-0.0 == +0.0` là `true`.
- `Double.NaN` được xếp **sau** các giá trị số hữu hạn và các giá trị vô cực theo thứ tự tăng dần của `Double.compare`; các biểu diễn NaN được xem bằng nhau trong phép so này.
- `Double.NEGATIVE_INFINITY` đứng trước các số hữu hạn; `Double.POSITIVE_INFINITY` đứng sau các số hữu hạn nhưng trước NaN.

Vì vậy, không được tùy tiện thay `comparingDouble` bằng `(a, b) -> (int) (a.score() - b.score())`: ép một hiệu `double` sang `int` có thể biến chênh lệch nhỏ thành `0`, làm mất thứ tự mong muốn; NaN và vô cực cũng gây vấn đề.

Nếu nghiệp vụ cần loại `NaN` hoặc áp dụng ngưỡng gần đúng, cần nêu rõ chính sách xử lý. Đặc biệt, **không** coi hai số “chênh nhau dưới epsilon” là tương đương trong một comparator dùng để sắp xếp hay làm khóa `TreeSet` khi quan hệ đó không bắc cầu.

## 5. Ví dụ Java 17 hoàn chỉnh và đầu ra kiểm chứng được

Tạo tệp **`ComparatorFactoriesDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class ComparatorFactoriesDemo {

    record Applicant(String name, int age, long visits, double score) {}

    private static void printSorted(
            String label,
            List<Applicant> source,
            Comparator<Applicant> comparator) {
        String names = source.stream()
                .sorted(comparator)
                .map(Applicant::name)
                .collect(Collectors.joining(", "));
        System.out.println(label + ": " + names);
    }

    public static void main(String[] args) {
        List<Applicant> data = List.of(
                new Applicant("Lan", 22, 5L, 9.5),
                new Applicant("An", 30, 12L, 8.0),
                new Applicant("Binh", 22, 7L, 9.5),
                new Applicant("Mai", 30, 3L, -0.0),
                new Applicant("Hoa", 22, 15L, Double.NaN)
        );

        printSorted("name", data,
                Comparator.comparing(Applicant::name));

        printSorted("age then name", data,
                Comparator.comparingInt(Applicant::age)
                        .thenComparing(Applicant::name));

        printSorted("visits descending", data,
                Comparator.comparingLong(Applicant::visits)
                        .reversed());

        printSorted("score then name", data,
                Comparator.comparingDouble(Applicant::score)
                        .thenComparing(Applicant::name));

        List<Applicant> withNullName = List.of(
                new Applicant(null, 20, 1L, 0.0),
                new Applicant("Zed", 25, 2L, 1.0)
        );
        Comparator<Applicant> nullableName =
                Comparator.comparing(
                        Applicant::name,
                        Comparator.nullsFirst(
                                String.CASE_INSENSITIVE_ORDER));

        String nullableResult = withNullName.stream()
                .sorted(nullableName)
                .map(a -> a.name() == null ? "<null>" : a.name())
                .collect(Collectors.joining(", "));
        System.out.println("nullable names: " + nullableResult);

        Applicant low = new Applicant("MIN", 0, Long.MIN_VALUE, 0.0);
        Applicant high = new Applicant("MAX", 0, Long.MAX_VALUE, 0.0);
        Comparator<Applicant> safeLong =
                Comparator.comparingLong(Applicant::visits);
        System.out.println("long extremes ordered: "
                + (safeLong.compare(low, high) < 0));

        System.out.println("minus zero before plus zero: "
                + (Double.compare(-0.0, +0.0) < 0));
        System.out.println("NaN after positive infinity: "
                + (Double.compare(
                        Double.NaN, Double.POSITIVE_INFINITY) > 0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ComparatorFactoriesDemo.java
java ComparatorFactoriesDemo
~~~

**Đầu ra chuẩn:**

~~~text
name: An, Binh, Hoa, Lan, Mai
age then name: Binh, Hoa, Lan, An, Mai
visits descending: Hoa, An, Binh, Lan, Mai
score then name: Mai, An, Binh, Lan, Hoa
nullable names: <null>, Zed
long extremes ordered: true
minus zero before plus zero: true
NaN after positive infinity: true
~~~

Giải thích:

1. `comparing(Applicant::name)` lấy `String` rồi so theo thứ tự tự nhiên; các tên được sắp tăng dần.
2. `comparingInt(Applicant::age)` đưa nhóm tuổi `22` lên trước nhóm `30`. `thenComparing(Applicant::name)` phá thế hòa theo tên: trong nhóm `22` là `Binh, Hoa, Lan`, trong nhóm `30` là `An, Mai`.
3. `comparingLong(Applicant::visits).reversed()` cho số lượt thăm giảm dần: `15, 12, 7, 5, 3`.
4. `comparingDouble(Applicant::score)` sắp `-0.0, 8.0, 9.5, 9.5, NaN`. `thenComparing(name)` xếp `Binh` trước `Lan` khi điểm bằng nhau.
5. Tên nullable được sắp với `Comparator.nullsFirst(...)` dành cho **khóa String**, nên khóa `null` đứng trước `"Zed"`.
6. Với hai giá trị `long` cực trị, factory dùng `Long.compare` nên nhận diện đúng thứ tự. Hai dòng cuối minh họa quy tắc `Double.compare` cho signed zero và NaN.

`record Applicant` được dùng như mô hình dữ liệu nhỏ để giảm code phụ; các phương thức accessor `name()`, `age()`, `visits()`, `score()` do Java sinh. Java 17 hỗ trợ record chính thức.

## 6. Ghép nhiều tiêu chí với `thenComparing...`

Một khóa đôi khi không phân biệt được hết các phần tử. Ví dụ sắp xếp theo `age` sẽ cho kết quả `0` với hai người cùng tuổi. Trong trường hợp đó, ta ghép tiêu chí phụ:

~~~java
Comparator<Applicant> order =
    Comparator.comparingInt(Applicant::age)
              .thenComparing(Applicant::name)
              .thenComparingLong(Applicant::visits)
              .thenComparingDouble(Applicant::score);
~~~

Đây là mảnh mã sử dụng `Applicant` từ ví dụ hoàn chỉnh. Luồng đánh giá:

1. So `age`. Nếu khác, trả ngay theo tuổi.
2. Nếu bằng tuổi, so `name`.
3. Nếu vẫn bằng tên, so `visits`.
4. Nếu vẫn bằng, so `score`.

Các phương thức `thenComparingInt`, `thenComparingLong`, `thenComparingDouble` phù hợp cho tiêu chí phụ nguyên thủy và hoạt động tương tự các factory tương ứng. Comparator sẽ không cần đến tiêu chí sau nếu tiêu chí trước đã xác định được thứ tự.

### Đảo chiều đúng phạm vi

~~~java
// Đảo toàn bộ comparator: tuổi giảm, rồi tên giảm.
Comparator<Applicant> allDescending =
    Comparator.comparingInt(Applicant::age)
              .thenComparing(Applicant::name)
              .reversed();

// Tuổi giảm nhưng tên vẫn tăng khi cùng tuổi.
Comparator<Applicant> ageDescNameAsc =
    Comparator.comparingInt(Applicant::age)
              .reversed()
              .thenComparing(Applicant::name);

// Tuổi tăng, tên giảm khi cùng tuổi.
Comparator<Applicant> ageAscNameDesc =
    Comparator.comparingInt(Applicant::age)
              .thenComparing(
                  Comparator.comparing(Applicant::name).reversed()
              );
~~~

Các đoạn dùng `Applicant` ở ví dụ trên, không phải tệp hoàn chỉnh riêng. `reversed()` đảo kết quả của **toàn bộ comparator đã ghép tại thời điểm gọi**. Muốn chỉ đảo chiều một khóa, hãy đảo comparator riêng của khóa đó rồi mới ghép. Tránh nhầm rằng `reversed()` luôn chỉ đảo “cột đầu tiên”.

Nếu chỉ cần sắp xếp một danh sách mà không thay đổi danh sách ban đầu, `stream().sorted(comparator).toList()` (Java 16+) tạo danh sách kết quả theo thứ tự; `List.sort(comparator)` thay đổi danh sách đích và không dùng được trên danh sách không cho sửa cấu trúc do `List.of(...)` tạo. Java bảo đảm `List.sort` ổn định; với các phần tử có `compare(a,b)==0`, thứ tự tương đối ban đầu được giữ. Tuy nhiên, khi nghiệp vụ cần một thứ tự hoàn toàn xác định, nên thêm tiêu chí phụ rõ ràng, đặc biệt trước khi phân trang hoặc xuất báo cáo.

## 7. Xử lý `null` cho đúng tầng

Các factory mặc định thường **không tự xử lý khóa null**. Nếu một extractor trả `null` và comparator khóa không hỗ trợ null, phép sắp xếp có thể ném `NullPointerException`.

Có hai tình huống khác nhau:

**A. Chính phần tử cần sắp xếp là `null`:**

~~~java
Comparator<Applicant> byAgeAllowNullApplicant =
    Comparator.nullsLast(
        Comparator.comparingInt(Applicant::age)
    );
~~~

Tầng `nullsLast` bên ngoài giúp phần tử `Applicant` bằng `null` đi cuối. Nếu phần tử không null, comparator bên trong mới truy cập `age()`.

**B. Phần tử không null, nhưng khóa `name()` có thể null:**

~~~java
Comparator<Applicant> byNullableName =
    Comparator.comparing(
        Applicant::name,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    );
~~~

`nullsLast` ở đây xử lý **giá trị String do extractor trả về**, không tự xử lý phần tử `Applicant` null. Nếu cả bản thân phần tử và khóa đều có thể null, có thể bọc hai tầng với các chính sách thích hợp.

Với primitive extractor như `ToIntFunction`, kết quả là `int` nên không thể là `null`. Nhưng nếu code viết `Comparator.comparingInt(e -> e.getNullableAge())` và `getNullableAge()` trả `Integer`, Java phải unbox; giá trị null sẽ gây `NullPointerException`. Hãy xác định chính sách cho trường nullable trước: dùng overload `comparing(...)` với comparator khóa cho null, chuyển về giá trị mặc định có ý nghĩa, hoặc từ chối dữ liệu thiếu.

## 8. Thứ tự của comparator và `equals()` là hai khái niệm khác nhau

`Comparator.compare(a, b) == 0` nghĩa là **tương đương trong thứ tự do comparator xác định**; nó không nhất thiết đồng nghĩa `a.equals(b)`. Chẳng hạn hai `Applicant` bằng tuổi nhưng khác tên có thể cho `0` khi dùng `comparingInt(Applicant::age)`.

Điều này đặc biệt quan trọng nếu sử dụng comparator với `TreeSet` và `TreeMap`:

~~~java
Comparator<Applicant> byAge =
    Comparator.comparingInt(Applicant::age);
~~~

Đoạn trên có thể là tiêu chí sắp xếp rất hữu ích cho `List`. Nhưng nếu đặt vào `TreeSet<Applicant>`, các ứng viên **cùng tuổi** sẽ được cấu trúc cây coi là trùng nhau theo comparator, dù tên và các thuộc tính khác khác nhau. `TreeMap` cũng xác định trùng khóa bằng kết quả `compare==0` của comparator, không dựa vào `equals()` theo cách `HashMap` làm.

Nếu yêu cầu là giữ tất cả ứng viên riêng biệt trong `TreeSet`, hãy thêm tiêu chí phân biệt duy nhất, ổn định, nhất quán với ngữ nghĩa tập hợp mong muốn, ví dụ ID nghiệp vụ:

~~~java
// Giả định kiểu Applicant thực tế có id() là khóa phân biệt ổn định.
Comparator<Applicant> byAgeThenId =
    Comparator.comparingInt(Applicant::age)
              .thenComparing(Applicant::id);
~~~

Đây chỉ là mảnh mã để diễn tả quy tắc; `Applicant` của ví dụ chạy ở mục 5 chưa có trường `id()`. **Không** tạo một comparator trả kết quả khác nhau thất thường chỉ nhằm giữ mọi phần tử: comparator vẫn phải thỏa tính bắc cầu và nhất quán.

Ngoài ra, sắp xếp tăng dần theo `BigDecimal` bằng `Comparator.comparing(Invoice::total)` dùng `BigDecimal.compareTo`. Phương thức này có thể cho `0` giữa `1.0` và `1.00` dù `BigDecimal.equals()` cho `false`. Điều đó được chấp nhận khi chỉ **sort**, nhưng cần cân nhắc kỹ khi dùng comparator này làm quy tắc trùng khóa trong `TreeMap` hoặc `TreeSet`.

## 9. Lưu ý về hiệu năng và tính đúng đắn

- **Ưu tiên method reference rõ nghĩa:** `Comparator.comparingInt(Person::age)` thường dễ đọc hơn một lambda tự trừ hai tuổi.
- **Chọn đúng kiểu khóa:** nếu getter trả `long`, dùng `comparingLong` thay vì ép sang `int`; nếu trả `double`, hiểu chính sách NaN/signed zero của `Double.compare`.
- **Giữ extractor thuần và ổn định:** không sửa trạng thái object, không phát sinh giá trị ngẫu nhiên, và không phụ thuộc dữ liệu thay đổi giữa các lần so sánh trong cùng một thao tác sort. Comparator có thể gọi extractor nhiều lần và với những cặp khác nhau.
- **Không dùng phép gần đúng làm quan hệ so bằng nhau:** so theo sai số `epsilon` thường thiếu tính bắc cầu; nên tách thành phép kiểm tra riêng thay vì gài vào comparator sắp xếp.
- **Không kỳ vọng caching khóa:** factory không hứa gọi extractor đúng một lần trên mỗi phần tử. Nếu tính khóa quá tốn kém, có thể tạo bản ghi mang khóa đã tính (*decorate-sort-undecorate*) hoặc một mô hình khóa ổn định riêng.
- **Không lạm dụng `reversed()`:** ghi rõ chiều từng tiêu chí khi ghép nhiều khóa và kiểm tra bằng ví dụ có giá trị trùng ở khóa chính.

## 10. Checklist khi áp dụng

Trước khi chọn comparator factory, kiểm tra:

1. Khóa đang sắp xếp là đối tượng có `Comparable`, đối tượng cần comparator riêng, hay primitive `int`/`long`/`double`?
2. Nếu dùng `comparing(...)`, khóa có thực sự hỗ trợ so sánh tự nhiên? Nếu không, đã truyền `keyComparator` chưa?
3. Có `null` ở **phần tử** hay ở **khóa**? Đã đặt `nullsFirst`/`nullsLast` đúng tầng chưa?
4. `double` có thể mang NaN, vô cực hoặc `-0.0` không? Thứ tự của `Double.compare` có phù hợp nghiệp vụ không?
5. Có cần ghép tiêu chí phụ bằng `thenComparing(...)` để sắp xếp xác định trong nhóm trùng khóa không?
6. `reversed()` đang đảo toàn bộ comparator hay chỉ tiêu chí muốn đảo?
7. Comparator có được dùng trong `TreeSet`/`TreeMap` không? Nếu có, `compare(a,b)==0` có đúng ý nghĩa “trùng phần tử/khóa” mong muốn không?
8. Các trường lấy khóa có ổn định trong quá trình sort hoặc trong thời gian tồn tại trong cấu trúc cây không?

**Ghi nhớ:** `comparing()` dành cho **khóa đối tượng** (dùng `Comparable` hoặc một comparator khóa riêng). `comparingInt()`, `comparingLong()` và `comparingDouble()` dành cho **khóa primitive**, biểu đạt rõ kiểu và tránh boxing khóa không cần thiết. Dùng `thenComparing...` để ghép tiêu chí, `reversed()` để đảo thứ tự, và luôn xác định chính xác quy tắc null, số thực cũng như ngữ nghĩa `compare==0` trong các collection có sắp xếp.