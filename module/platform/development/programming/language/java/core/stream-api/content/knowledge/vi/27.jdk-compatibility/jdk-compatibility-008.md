# Rà soát ngữ nghĩa kết quả khi nâng JDK hoặc thay phép toán

Nâng phiên bản JDK hoặc viết lại một pipeline Java Stream API có thể khiến chương trình **biên dịch thành công, chạy không báo lỗi, nhưng kết quả không còn đúng với hợp đồng nghiệp vụ**. Một thay đổi tưởng như vô hại, chẳng hạn thay `collect(Collectors.toList())` bằng `toList()`, chuyển `findFirst()` sang `findAny()`, thay `filter` bằng `takeWhile` hoặc thu thập Map bằng collector đồng thời, có thể thay đổi **khả năng sửa kết quả, xử lý null, lựa chọn phần tử, thứ tự hoặc dữ liệu bị giữ/bỏ**.

Ở chiều ngược lại, không phải mọi khác biệt quan sát được giữa hai lần chạy là lỗi tương thích: thứ tự in từ `HashMap`, tên lớp implementation của `List` hoặc thời điểm một lambda có side effect được gọi có thể **không được API bảo đảm từ đầu**. Điều cần bảo vệ là **ngữ nghĩa có hợp đồng rõ ràng**, không phải tình cờ của một bản JDK.

Bài thuộc chương **Khả năng tương thích JDK** của module **JAVA_STREAM_API**. Ta sẽ rà soát các thay đổi liên quan đến pipeline lazy, `filter`, `map`, `reduce`, `collect`, grouping, collector tùy chỉnh, xử lý song song, `Spliterator`, quản lý tài nguyên và các API mới như Stream Gatherers. Mục tiêu cuối là có một quy trình kiểm tra **trước và sau khi nâng JDK hoặc refactor**, với ví dụ và bài tập tự thực hành.

## 1. Phân biệt bốn loại tương thích

Khi nói “nâng JDK mà không làm hỏng Stream”, trước tiên cần xác định đang kiểm tra vấn đề nào:

| Loại tương thích | Câu hỏi phải trả lời | Ví dụ |
|---|---|---|
| **Nguồn (source)** | Mã có biên dịch với mức Java đích không? | `Stream.toList()` không có trong Java 8 |
| **Binary/runtime** | File `.class` và thư viện có chạy với JRE đích không? | Bytecode biên dịch cho JDK mới không chạy được trên JRE quá cũ |
| **Ngữ nghĩa (behavioral)** | Giá trị, ngoại lệ, thứ tự và trạng thái trả về có còn đúng không? | `findFirst` đổi thành `findAny` có thể chọn khác phần tử |
| **Phi chức năng** | Hiệu năng, bộ nhớ, tài nguyên, song song có còn chấp nhận được không? | `parallel()` làm tăng tranh chấp hoặc chi phí |

Bài này tập trung vào **tương thích ngữ nghĩa**, nhưng ba loại còn lại cũng cần có bước kiểm tra riêng. Mã biên dịch thành công **không chứng minh** kết quả đúng; một bài kiểm thử đúng giá trị trên vài phần tử cũng **không chứng minh** hiệu năng hay an toàn tài nguyên.

### 1.1. Ngữ nghĩa nào cần được giữ?

Với mỗi pipeline, hãy ghi rõ:

1. **Tập phần tử đầu vào nào được tính?** Bao gồm cả phần tử null hay chỉ dữ liệu hợp lệ?
2. **Có cần thứ tự không?** Nếu cần, là thứ tự nguồn, thứ tự sắp xếp hay thứ tự thời gian nghiệp vụ?
3. **Kết quả rỗng biểu diễn thế nào?** Số 0, `Optional.empty()`, Map rỗng hay không có khóa nhóm?
4. **Có chấp nhận trùng lặp không?** Một SKU có thể xuất hiện nhiều đơn; phải cộng hay giữ bản ghi nào?
5. **Kết quả có được phép sửa không?** Caller có dùng `list.add(...)` hoặc cập nhật Map không?
6. **Sai số và tràn số được xử lý ra sao?** `int`, `long`, `double` hay `BigDecimal`?
7. **Ai chịu trách nhiệm đóng nguồn I/O?** Terminal operation có làm thay việc đóng file không?

Nếu chưa trả lời, một phép thay thế “trông gọn hơn” có thể vô tình thay đổi hợp đồng.

## 2. Bảng mốc API quan trọng khi rà soát phiên bản JDK

Các mốc dưới đây giúp nhận diện phương thức có sẵn theo phiên bản. Đây là **mốc giới thiệu API**, không phải kết luận rằng các phương thức có cùng chức năng có thể thay thế cho nhau.

| Phiên bản Java/JDK | API hoặc thay đổi đáng chú ý | Điểm cần rà soát |
|---|---|---|
| **Java 8** | `Stream`, `map`, `flatMap`, `filter`, `reduce`, `collect`, `Collectors.toList`/`toMap`/`groupingBy`, primitive streams | Nền tảng cho mã tương thích Java 8 |
| **Java 9** | `takeWhile`, `dropWhile`, `Stream.ofNullable`, `Stream.iterate(seed, hasNext, next)`, `Optional.stream`, `Collectors.flatMapping`/`filtering` | Điều kiện dừng, null, cách giữ nhóm và thay đổi tập phần tử |
| **Java 10** | `Collectors.toUnmodifiableList`/`toUnmodifiableSet`/`toUnmodifiableMap`; `List.copyOf` | Khả năng sửa kết quả, null và khóa trùng |
| **Java 12** | `Collectors.teeing` | Kết hợp hai phép thu thập, cách xử lý nguồn rỗng và finisher |
| **Java 16** | `Stream.toList()`, `Stream.mapMulti(...)` | Danh sách không sửa được; chuyển một phần tử thành 0..n kết quả |
| **Java 24** | Stream Gatherers (`Stream.gather`, `Gatherer`) được hoàn thiện thành tính năng chính thức | API không có ở các bản JDK cũ; kiểm tra cách đóng khung, trạng thái và thực thi |

Ở Java 22 và 23, Stream Gatherers từng ở giai đoạn preview; mã dùng chúng tại các phiên bản ấy có yêu cầu riêng về bật tính năng preview. Với mã cần chạy trên Java 8, 11, 17 hoặc 21, không sử dụng trực tiếp `Stream.gather` của Java 24.

**Quan trọng:** Không tự suy rằng một phương thức mới “sửa lỗi” tất cả phiên bản cũ. Việc thay API mới phải được đánh giá theo **hợp đồng kết quả**, **mức `--release`**, và dữ liệu thực tế.

## 3. Trường hợp dễ lỗi nhất: toList(), Collectors.toList() và toUnmodifiableList()

Ba cách thu thập thành danh sách có thể nhìn giống nhau:

```java
// Java 8+
List<String> a = stream.collect(Collectors.toList());

// Java 10+
List<String> b = stream.collect(Collectors.toUnmodifiableList());

// Java 16+
List<String> c = stream.toList();
```

Các dòng là **ba ví dụ riêng**; cần tạo Stream mới cho từng lệnh vì Stream chỉ tiêu thụ một lần.

### 3.1. So sánh hợp đồng

| API | Mức Java tối thiểu | Có bảo đảm sửa được List không? | Chính sách null | Thứ tự |
|---|---:|---|---|---|
| `collect(Collectors.toList())` | 8 | **Không cam kết** khả năng sửa hoặc kiểu List | Không nên thiết kế dựa vào một implementation cụ thể | Giữ encounter order nếu nguồn có thứ tự |
| `collect(Collectors.toUnmodifiableList())` | 10 | **Không sửa được** | **Không chấp nhận phần tử null** | Giữ encounter order nếu có |
| `Stream.toList()` | 16 | **Không sửa được** | **Cho phép phần tử null** trong List kết quả | Giữ encounter order nếu có |

Sự khác biệt quan trọng nhất khi refactor:

- Thay `collect(toList())` bằng `toList()` có thể làm **code ở phía sau ném `UnsupportedOperationException`** nếu trước đó caller dựa vào việc `add` hoặc `remove` hoạt động.
- Thay bằng `toUnmodifiableList()` có thể làm **code ném `NullPointerException`** khi nguồn có phần tử null.
- Chỉ đổi tên phương thức mà không chạy lại các kiểm thử về null, thứ tự và khả năng sửa có thể bỏ sót lỗi.

### 3.2. Ví dụ chạy được từ Java 16

```java
import java.util.List;
import java.util.stream.Stream;

public class ToListSemanticDemo {
    public static void main(String[] args) {
        List<String> values = Stream.of("A", null, "B").toList();

        System.out.println(values); // [A, null, B]
        System.out.println(values.size()); // 3

        try {
            values.add("C");
            throw new AssertionError("Không được sửa List");
        } catch (UnsupportedOperationException expected) {
            System.out.println("List không sửa được");
        }
    }
}
```

Nếu cần **danh sách có thể sửa được**, hãy tạo kiểu cụ thể một cách rõ ràng:

```java
// Java 8+: kết quả là một ArrayList do ta yêu cầu.
List<String> mutable = stream.collect(
        Collectors.toCollection(ArrayList::new));
```

Hoặc, ở Java 16+, có thể sao chép:

```java
List<String> mutable = new ArrayList<>(stream.toList());
```

Lời hứa “List có thể sửa” đến từ `ArrayList` được chọn, **không** đến từ hành vi tình cờ của `Collectors.toList()` trên một bản JDK cụ thể.

### 3.3. Không phụ thuộc vào lớp implementation

Không kiểm thử kiểu:

```java
// Không nên:
// assert result.getClass() == ArrayList.class;
```

`Collectors.toList()` không cam kết loại List cụ thể; `Stream.toList()` cũng không cam kết một tên lớp implementation nhất định và kết quả có thể có tính chất *value-based*. Hãy kiểm tra giá trị, thứ tự và tính không sửa được **nếu chúng là hợp đồng**, thay vì phụ thuộc tên class, địa chỉ đối tượng hoặc đồng bộ trên List trả về.

## 4. Phân biệt giá trị null với Stream rỗng

Java 9 thêm `Stream.ofNullable(value)`:

```java
// Java 9+
Stream<String> none = Stream.ofNullable(null); // 0 phần tử
Stream<String> one = Stream.ofNullable("A");   // 1 phần tử
```

Nhưng `Stream.of((String) null)` chứa **một phần tử null**, không phải Stream rỗng:

```java
// Java 8+
long withNull = Stream.of((String) null).count(); // 1

// Java 9+
long withoutValue = Stream.<String>ofNullable(null).count(); // 0
```

Đây là khác biệt ngữ nghĩa rõ ràng. Nếu refactor `Stream.of(value)` thành `Stream.ofNullable(value)`, khi `value == null`, **số phần tử thay đổi từ 1 thành 0**. Điều đó có thể ảnh hưởng `count`, `collect`, số bản ghi bị loại và báo cáo chất lượng dữ liệu.

### 4.1. Optional không thay thế số liệu rỗng bằng 0

Một vài kết quả:

| Phép toán | Stream rỗng | Stream có một phần tử 0 |
|---|---|---|
| `IntStream.sum()` | `0` | `0` |
| `IntStream.average()` | `OptionalDouble.empty()` | `OptionalDouble[0.0]` |
| `IntStream.reduce(Integer::sum)` | `OptionalInt.empty()` | `OptionalInt[0]` |
| `IntStream.reduce(0, Integer::sum)` | `0` | `0` |
| `IntStream.count()` | `0L` | `1L` |

Việc thay `reduce(Integer::sum)` bằng `sum()` **làm mất trạng thái “không có phần tử”** nếu phía gọi quan tâm tới `OptionalInt.empty()`. Ngược lại, nếu nghiệp vụ định nghĩa tổng của nguồn rỗng bằng 0, `sum()` là lựa chọn dễ đọc.

### 4.2. findFirst() và giá trị null

`findFirst()` trả `Optional<T>`. Nếu phần tử được chọn là `null`, thao tác này có thể ném `NullPointerException`; không nên dùng nó như cách “trả Optional rỗng cho phần tử null”:

```java
// SAI nếu phần tử đầu là null:
// Stream.of((String) null, "A").findFirst();

Optional<String> safe = Stream.of((String) null, "A")
        .filter(Objects::nonNull)
        .findFirst();
System.out.println(safe.orElse("(trống)")); // A
```

Ở Java 9+, `Optional.stream()` có thể làm phẳng các Optional:

```java
// Java 9+
List<String> present = Stream.of(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("B"))
        .flatMap(Optional::stream)
        .collect(Collectors.toList());
// [A, B]
```

Ở Java 8, có thể dùng `filter(Optional::isPresent).map(Optional::get)` khi chính đối tượng Optional không null. Dù chọn cách nào, cần xác định rõ **có giữ thông tin phần tử vắng mặt trong thống kê hay không**.

## 5. filter khác takeWhile và dropWhile

Java 9 có `takeWhile` và `dropWhile`, nhưng chúng **không thay thế tương đương** cho `filter`.

- `filter(p)` kiểm tra predicate **trên các phần tử** và giữ mọi phần tử thỏa điều kiện.
- `takeWhile(p)` trên Stream **có thứ tự** giữ **đoạn đầu liên tiếp dài nhất** mà tất cả phần tử đều thỏa predicate; gặp phần tử không thỏa đầu tiên thì dừng lấy.
- `dropWhile(p)` trên Stream **có thứ tự** bỏ **đoạn đầu liên tiếp dài nhất** thỏa predicate, sau đó giữ phần còn lại.

```java
// Java 9+
List<Integer> data = Arrays.asList(1, 2, 0, 3, 4);

List<Integer> filtered = data.stream()
        .filter(n -> n > 0)
        .collect(Collectors.toList());
// [1, 2, 3, 4]

List<Integer> taken = data.stream()
        .takeWhile(n -> n > 0)
        .collect(Collectors.toList());
// [1, 2]

List<Integer> dropped = data.stream()
        .dropWhile(n -> n > 0)
        .collect(Collectors.toList());
// [0, 3, 4]
```

Thay `filter(n -> n > 0)` bằng `takeWhile(n -> n > 0)` sẽ làm mất các số dương phía sau `0`. Phép thay thế chỉ đúng nếu **nguồn đã được sắp xếp hoặc có bất biến bảo đảm mọi phần tử không thỏa nằm sau toàn bộ phần tử thỏa**, và nghiệp vụ thực sự muốn cắt đoạn đầu.

### 5.1. Stream không có thứ tự

Với Stream **unordered**, `takeWhile` không cam kết một đoạn đầu cụ thể theo encounter order và có thể trả một **tập con** các phần tử thỏa predicate theo hợp đồng của thao tác; `dropWhile` cũng có sự tự do khác với nguồn có thứ tự. Không sử dụng chúng để biểu diễn “chọn N bản ghi đầu tiên” hoặc “dừng đúng tại sự kiện đầu” nếu thứ tự đầu vào không được định nghĩa.

### 5.2. iterate ba tham số cũng là một điều kiện dừng

Java 9 cung cấp:

```java
// Java 9+: seed, hasNext, next
Stream<Integer> numbers = Stream.iterate(
        1, n -> n <= 5, n -> n + 1);
// 1, 2, 3, 4, 5
```

Trước đó, Java 8 thường kết hợp `Stream.iterate(seed, next)` với `limit(n)`:

```java
// Java 8+
Stream<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5);
```

Hai ví dụ tình cờ cho cùng dãy, nhưng `limit(5)` đếm số phần tử còn `n -> n <= 5` xét giá trị của phần tử. Với bước nhảy, nguồn hoặc điều kiện khác, chúng có thể không tương đương. Khi nâng JDK, hãy giữ rõ yêu cầu **“lấy đúng N phần tử”** hay **“lấy tới khi điều kiện dừng xảy ra”**.

## 6. Thứ tự, findFirst, findAny và phép thu thập Map/Set

### 6.1. Không nhầm findFirst với findAny

Với nguồn có encounter order:

```java
OptionalInt first = IntStream.rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 7 == 0)
        .findFirst();
// OptionalInt[7]

OptionalInt any = IntStream.rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 7 == 0)
        .findAny();
// Có giá trị, nhưng không bảo đảm là 7.
```

`findAny` có thể mang lại tự do tối ưu lớn hơn, nhưng không phù hợp nếu yêu cầu là **“bản ghi thỏa điều kiện đầu tiên theo thứ tự nguồn”**. Một bài kiểm thử khẳng định `findAny` luôn trả 7 là kiểm thử của hành vi không được bảo đảm, không phải kiểm thử tính đúng.

### 6.2. forEach không bảo đảm thứ tự hành động

`parallel().forEach(action)` không bảo đảm các action chạy theo encounter order. `forEachOrdered(action)` giữ thứ tự hành động theo encounter order nếu nguồn có thứ tự, đổi lại có thể giảm lợi ích song song.

```java
IntStream.rangeClosed(1, 4)
        .parallel()
        .forEachOrdered(System.out::print);
// 1234
```

Đừng thay `forEachOrdered` bằng `forEach` chỉ vì muốn nhanh khi thứ tự ghi log, xuất file hoặc xử lý sự kiện là một yêu cầu nghiệp vụ.

### 6.3. Map và Set không mặc nhiên có thứ tự duyệt

`Collectors.toSet()` không cam kết thứ tự phần tử; `Collectors.toMap(...)` và `groupingBy(...)` không cam kết loại Map hoặc thứ tự duyệt khóa. Đổi phiên bản JDK hoặc chuyển chế độ song song có thể làm thứ tự in **khác nhau mà không vi phạm hợp đồng API**.

```java
Map<String, Long> totals = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.counting()));

// ĐÚNG: so sánh giá trị theo khóa.
long bac = totals.getOrDefault("BAC", 0L);

// KHÔNG NÊN: dựa vào thứ tự in của totals.toString()
// để xác định thứ tự các khu vực.
```

Đoạn minh họa giả định có kiểu `Order` và danh sách `orders`. Nếu nghiệp vụ muốn khóa Map tăng dần, dùng overload cho phép chọn `TreeMap::new`:

```java
Map<String, Long> sorted = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                TreeMap::new,
                Collectors.counting()));
```

Nếu muốn giữ thứ tự chèn các khóa trong một phép thu thập tuần tự, cân nhắc `LinkedHashMap::new` ở overload có map supplier. **Thứ tự của khóa trong Map** và **phần tử thắng cuộc khi hai giá trị có cùng khóa** là hai vấn đề khác nhau.

## 7. toMap, groupingBy và hàm merge khi thay thuật toán

Với dữ liệu có khóa trùng, `Collectors.toMap(keyMapper, valueMapper)` mặc định ném `IllegalStateException`. Một refactor từ `groupingBy(..., toList())` sang `toMap` có thể làm mất khả năng biểu diễn **nhiều giá trị trên cùng khóa**, hoặc làm code ném ngoại lệ.

```java
List<String> data = Arrays.asList("P01:A", "P01:B", "P02:C");

Map<String, List<String>> grouped = data.stream()
        .collect(Collectors.groupingBy(
                item -> item.substring(0, 3)));
// P01 có hai chuỗi, P02 có một chuỗi.

// SAI với P01 trùng khóa:
// data.stream().collect(Collectors.toMap(
//         item -> item.substring(0, 3), item -> item));

Map<String, String> latestByEncounter = data.stream()
        .collect(Collectors.toMap(
                item -> item.substring(0, 3),
                item -> item,
                (oldValue, newValue) -> newValue));
// P01 -> P01:B với List nguồn và phép thu thập có thứ tự ở đây.
```

### 7.1. Phép merge phải có tính kết hợp nhóm

Một phép gộp dùng cho reduction song song phải giữ ý nghĩa khi các nhóm được kết hợp theo các cách khác nhau. Ví dụ:

```text
(10 + 20) + 40 = 70
10 + (20 + 40) = 70

((10 + 20) / 2 + 40) / 2 = 27.5
(10 + (20 + 40) / 2) / 2 = 20
```

Hàm `(a, b) -> (a + b) / 2` **không phải** phép merge hợp lệ để tính trung bình toàn bộ các bản ghi trùng khóa. Muốn trung bình đúng, hãy giữ **tổng và số lượng** trong trạng thái hoặc dùng `Collectors.averagingInt` phù hợp.

### 7.2. toConcurrentMap làm mất ý nghĩa “gặp đầu/cuối”

`Collectors.toConcurrentMap` là collector concurrent và unordered. Khi chuyển từ `toMap` sang `toConcurrentMap`, phép gộp giữ giá trị cũ hoặc mới:

```java
(oldValue, newValue) -> oldValue
(oldValue, newValue) -> newValue
```

không còn là một cách đáng tin để chọn **bản ghi đầu tiên/cuối cùng theo List nguồn**. Nếu cần bản ghi mới nhất, hãy chọn bằng `timestamp`, `version` và tie-breaker rõ ràng; không dựa vào lịch thực thi các worker.

### 7.3. Nhóm rỗng và null key

`groupingBy` không tự tạo khóa cho nhóm **không xuất hiện trong nguồn**. Nếu đang làm phẳng dữ liệu cha–con, `flatMap` trước `groupingBy` có thể làm mất nhóm cha không có phần tử con, trong khi `Collectors.flatMapping` (Java 9+) **bên trong** `groupingBy` có thể giữ nhóm cha đã xuất hiện với downstream rỗng.

Không dựa vào khả năng nhận `null` làm khóa/giá trị của các Map collector. `groupingBy` yêu cầu khóa classifier hợp lệ và thông thường ném `NullPointerException` với khóa null; `toConcurrentMap` không chấp nhận khóa/giá trị null. Chuẩn hóa hoặc từ chối dữ liệu thiếu **trước** khi thu thập.

## 8. Kiểm tra số học: sum, average, overflow và double

Đổi kiểu Stream hoặc thay collector có thể giữ số phần tử nhưng làm thay đổi **ý nghĩa số học**.

### 8.1. Nguồn rỗng: Optional khác giá trị mặc định

```java
OptionalDouble primitiveAverage = IntStream.empty().average();
double collectorAverage = Stream.<Integer>empty()
        .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(primitiveAverage.isPresent()); // false
System.out.println(collectorAverage);              // 0.0
```

Hai API khác nhau **trên nguồn rỗng**. Nếu muốn giữ phân biệt “không có dữ liệu” và “trung bình bằng 0”, đừng chuyển từ `average()` sang `averagingInt(...)` mà chỉ kiểm thử trên nguồn không rỗng.

`IntSummaryStatistics`, `LongSummaryStatistics` có `getAverage() == 0.0` khi `count == 0`. Min/max của statistics rỗng cũng có các giá trị sentinel; kiểm tra `getCount()` trước khi hiển thị.

### 8.2. Tràn số nguyên có thể bị bỏ sót

```java
int wrongForBusiness = IntStream.of(Integer.MAX_VALUE, 1).sum();
// Bị tràn int: giá trị không phải tổng toán học 2147483648.

long widened = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToLong(value -> (long) value)
        .sum();
// 2147483648
```

Với tổng có thể vượt `long`, dùng `BigInteger`/`BigDecimal` hoặc phép cộng kiểm tra tràn như `Math.addExact` tùy chính sách. Chỉ đổi từ `sum` sang `reduce` không tự khắc phục tràn; cần thay kiểu hoặc quy tắc kiểm tra.

### 8.3. Sai số dấu phẩy động và cách gộp song song

`double` không kết hợp nhóm chính xác theo bit:

```java
double a = (1.0e16 + -1.0e16) + 1.0; // 1.0
double b = 1.0e16 + (-1.0e16 + 1.0); // 0.0
```

Do đó, khi đổi cách phân nhánh hoặc implementation thuật toán cộng, kết quả tổng/trung bình số thực **có thể khác nhau về làm tròn**. `DoubleStream.sum()` có thể dùng kỹ thuật cộng bù để cải thiện độ chính xác, nhưng không cam kết một thứ tự gộp hoặc sự đồng nhất bit giữa tất cả cách thực thi.

Với phép thống kê gần đúng, kiểm thử theo **dung sai có ý nghĩa nghiệp vụ** và xử lý riêng `NaN`, vô cực. Với tiền tệ, ưu tiên `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất, xác định rõ quy tắc làm tròn.

## 9. Side effect: vì sao nâng JDK có thể làm log hoặc counter thay đổi?

Các thao tác trung gian như `map`, `filter`, `peek` có tính lazy. Stream implementation được quyền tối ưu khi một thao tác không cần thực thi để xác định kết quả hợp lệ. Đặc biệt, `count()` trên nguồn có kích thước biết trước có thể trả kết quả **mà không duyệt qua tất cả phần tử**, nếu các thao tác trong pipeline không làm thay đổi số phần tử theo cách cần kiểm tra.

```java
List<String> names = Arrays.asList("A", "B", "C");

long count = names.stream()
        .peek(name -> System.out.println("Saw " + name))
        .count();

System.out.println(count); // 3
// KHÔNG bảo đảm cả ba dòng "Saw ..." đều được in.
```

Từ Java 9, tài liệu API nêu rõ ví dụ tối ưu hóa `count` như vậy. Một implementation có thể bỏ qua việc gọi `peek` khi kích thước nguồn đã biết và không cần đi qua phần tử. Điều này **không phải lỗi sai kết quả `count`**; lỗi thiết kế nằm ở việc dựa vào side effect của `peek` để ghi nhận nghiệp vụ.

### 9.1. Không đếm tác dụng phụ từ map/peek

Tránh:

```java
AtomicInteger processed = new AtomicInteger();

long count = names.stream()
        .map(name -> {
            processed.incrementAndGet();
            return name.toUpperCase();
        })
        .count();

// Không lấy processed.get() làm số bản ghi nghiệp vụ đáng tin.
```

Thay bằng phép tổng hợp thể hiện trực tiếp kết quả cần tính:

```java
long numberOfNames = names.stream().count();

Map<Integer, Long> countsByLength = names.stream()
        .collect(Collectors.groupingBy(
                String::length, Collectors.counting()));
```

Nếu yêu cầu là **thực hiện hành động trên mọi phần tử**, hãy dùng thao tác kết thúc phù hợp như `forEach` với cân nhắc về thứ tự và an toàn luồng; nếu yêu cầu là **tổng hợp số liệu**, hãy dùng collector/reduction. Không thiết kế tính đúng dựa vào việc `peek` có luôn được gọi.

## 10. flatMap, mapMulti và Gatherers: cùng hình dạng chưa chắc cùng hợp đồng

### 10.1. flatMap so với mapMulti

`Stream.flatMap` có từ Java 8. Nó yêu cầu mapper trả `Stream` con:

```java
// Java 8+
List<String> words = sentences.stream()
        .flatMap(sentence -> Arrays.stream(sentence.split(" ")))
        .collect(Collectors.toList());
```

`Stream.mapMulti` từ Java 16 cho mapper **phát 0..n phần tử trực tiếp** qua một consumer:

```java
// Java 16+
List<String> words = sentences.stream()
        .<String>mapMulti((sentence, emit) -> {
            for (String word : sentence.split(" ")) {
                emit.accept(word);
            }
        })
        .toList();
```

Đoạn này giả định `sentences` là `List<String>` không có phần tử null. Nếu chỉ xét **dãy từ được phát ra**, hai cách có thể tương đương. Nhưng ví dụ còn thay `collect(toList())` bằng `toList()`, làm thay đổi **khả năng sửa danh sách**. Vì vậy, khi refactor, hãy kiểm thử **cả phép biến đổi và bước kết thúc**, không chỉ output được in.

`mapMulti` không cần tạo Stream con cho từng phần tử nguồn, nên **có thể** hữu ích về chi phí khi một phần tử phát ít giá trị; không mặc định nhanh hơn cho mọi trường hợp. Với `flatMap` trả Stream con từ nguồn I/O, còn phải hiểu hợp đồng đóng các Stream con sau khi nội dung của chúng được đưa vào pipeline. Không thay cách quản lý tài nguyên chỉ dựa trên hình dạng kết quả.

### 10.2. Gatherers thuộc mức JDK khác

Stream Gatherers cho phép những phép biến đổi trung gian có trạng thái, cửa sổ dữ liệu (*windowing*) và nhiều hình dạng điều phối phức tạp hơn `map` hay `flatMap`. API `Stream.gather` và `Gatherer` được chuẩn hóa trong Java 24. Điều đó có hai hệ quả cần rà soát:

1. **Mức JDK:** mã dùng `gather` không thể tự chạy trên JRE Java 8/11/17/21.
2. **Hợp đồng pipeline:** khi thay `limit`, `map`, `flatMap` hay collector tùy chỉnh bằng gatherer, phải kiểm tra trạng thái, thứ tự, điều kiện kết thúc và sự tương đương kết quả, nhất là ở nguồn rỗng, xử lý song song và Stream không có thứ tự.

Không cần chuyển mọi pipeline sang Gatherers chỉ vì nâng JDK. Ưu tiên phép toán đơn giản nhất diễn đạt đúng yêu cầu và có mức tương thích phù hợp với hệ thống.

## 11. Tài nguyên I/O: nâng JDK không làm terminal operation tự đóng Stream

Các nguồn như `Files.lines`, `Files.list`, `Files.walk` và `Files.find` có thể nắm giữ file hoặc directory handle. Dù gọi `count()`, `findFirst()` hay `collect()`, vẫn cần **đóng Stream gắn tài nguyên** bằng `try-with-resources`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public static Optional<String> firstError(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.startsWith("ERROR"))
                .findFirst();
    }
}
```

`findFirst` có thể dừng sớm, nhưng **nguồn vẫn phải được đóng**. Không đổi hàm trả một `List` đã tính thành hàm trả một `Stream` còn mở mà không xác định **ai sẽ đóng**. Ngược lại, đừng trả pipeline được tạo trong một `try-with-resources` đã kết thúc; caller sẽ nhận Stream đã đóng.

Với `Stream.concat(first, second)`, đóng Stream kết hợp sẽ đóng các input Stream theo hợp đồng, nhưng nếu việc mở nguồn thứ hai thất bại **trước khi concat được tạo**, nguồn thứ nhất vẫn cần có `try-with-resources` bảo vệ. Bản nâng cấp JDK không xóa bỏ các yêu cầu sở hữu và vòng đời tài nguyên này.

## 12. Ví dụ Java 8 hoàn chỉnh: bộ kiểm tra ngữ nghĩa nền tảng

Bộ kiểm tra sau **không dùng API sau Java 8**, nên có thể biên dịch trên JDK 8. Nó không kiểm tra tốc độ hoặc tên lớp implementation. Thay vào đó, nó kiểm tra những điều mà bài toán thực sự yêu cầu: kết quả sau lọc, thứ tự có cam kết, số liệu rỗng, Optional, phép gộp trùng khóa và tương đương giữa xử lý tuần tự/song song.

Lưu thành `StreamBehaviorAudit.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.Set;
import java.util.HashSet;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamBehaviorAudit {
    private static int checks;

    static void check(boolean condition, String name) {
        checks++;
        if (!condition) {
            throw new AssertionError("FAILED: " + name);
        }
    }

    static final class Sale {
        final String region;
        final String sku;
        final long cents;

        Sale(String region, String sku, long cents) {
            this.region = region;
            this.sku = sku;
            this.cents = cents;
        }
    }

    public static void main(String[] args) {
        List<Integer> data = Arrays.asList(3, 1, 3, 2);

        // 1) Giữ thứ tự với nguồn List có encounter order.
        List<Integer> unique = data.parallelStream()
                .distinct()
                .collect(Collectors.toList());
        check(unique.equals(Arrays.asList(3, 1, 2)),
                "distinct giữ encounter order");

        // 2) Không đòi hỏi iteration order ở Set.
        Set<Integer> asSet = data.stream()
                .collect(Collectors.toSet());
        check(asSet.equals(new HashSet<>(Arrays.asList(1, 2, 3))),
                "tập phần tử thay vì thứ tự in");

        // 3) Phân biệt rỗng với tổng thực sự bằng 0.
        check(IntStream.empty().sum() == 0,
                "sum trên nguồn rỗng");
        OptionalDouble average = IntStream.empty().average();
        check(!average.isPresent(),
                "average trên nguồn rỗng");
        OptionalInt reduced = IntStream.of(-5, 5)
                .reduce(Integer::sum);
        check(reduced.isPresent() && reduced.getAsInt() == 0,
                "có dữ liệu nhưng reduce ra 0");
        check(!IntStream.empty().reduce(Integer::sum).isPresent(),
                "reduce không identity trên nguồn rỗng");

        // 4) Số lượng thật khác số phần tử sau làm phẳng.
        List<List<Integer>> nested = Arrays.asList(
                Arrays.asList(1, 2),
                Collections.<Integer>emptyList(),
                Arrays.asList(3));
        List<Integer> flattened = nested.stream()
                .flatMap(List::stream)
                .collect(Collectors.toList());
        check(flattened.equals(Arrays.asList(1, 2, 3)),
                "flatMap bỏ danh sách con rỗng");

        // 5) Map: chỉ kiểm tra nội dung theo khóa.
        List<Sale> sales = Arrays.asList(
                new Sale("BAC", "P01", 100L),
                new Sale("NAM", "P02", 200L),
                new Sale("BAC", "P01", 300L));

        Map<String, Long> seqTotals = sales.stream()
                .collect(Collectors.toMap(
                        sale -> sale.sku,
                        sale -> sale.cents,
                        Long::sum));

        Map<String, Long> parallelTotals = sales.parallelStream()
                .collect(Collectors.toMap(
                        sale -> sale.sku,
                        sale -> sale.cents,
                        Long::sum));

        check(seqTotals.equals(parallelTotals),
                "toMap tuần tự và song song tương đương");
        check(seqTotals.get("P01") == 400L,
                "merge cộng đủ khóa trùng");

        Map<String, Long> byRegion = sales.parallelStream()
                .collect(Collectors.groupingBy(
                        sale -> sale.region,
                        Collectors.counting()));
        check(byRegion.get("BAC") == 2L
                && byRegion.get("NAM") == 1L,
                "groupingBy đếm đúng từng nhóm");

        // 6) toMap không merge phải từ chối khóa trùng.
        boolean duplicateRejected = false;
        try {
            Stream.of("P01:A", "P01:B").collect(Collectors.toMap(
                    item -> item.substring(0, 3),
                    item -> item));
        } catch (IllegalStateException expected) {
            duplicateRejected = true;
        }
        check(duplicateRejected, "toMap từ chối khóa trùng");

        // 7) Tự yêu cầu ArrayList nếu cần kết quả có thể sửa.
        List<Integer> mutable = data.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add(99);
        check(mutable.size() == 5 && mutable.get(4) == 99,
                "toCollection(ArrayList::new) có thể sửa");

        // 8) findFirst khác findAny về cam kết chọn phần tử.
        OptionalInt first = IntStream.rangeClosed(1, 100)
                .parallel()
                .filter(n -> n % 7 == 0)
                .findFirst();
        check(first.isPresent() && first.getAsInt() == 7,
                "findFirst tôn trọng encounter order");

        System.out.println("PASS " + checks + " semantic checks");
    }
}
```

**Kết quả kỳ vọng:** chương trình in `PASS 13 semantic checks` và không ném `AssertionError`. Điều quan trọng không phải một chuỗi log tùy ý, mà là **các bất biến được kiểm tra bằng `check`**. Nếu một kiểm tra thất bại sau khi nâng JDK hoặc refactor, cần tìm hiểu xem ta đã thay đổi nghiệp vụ hay đã vô tình đặt kỳ vọng lên hành vi không được API bảo đảm.

### 12.1. Cách dùng bộ kiểm tra khi di chuyển phiên bản

Trên **JDK 9 trở lên**, có thể biên dịch chương trình bằng:

```bash
javac --release 8 StreamBehaviorAudit.java
java StreamBehaviorAudit
```

`--release 8` yêu cầu trình biên dịch chỉ cho phép các API sẵn có ở mức Java 8 và tạo bytecode tương thích mục tiêu. Trên **chính JDK 8**, dùng `javac StreamBehaviorAudit.java` vì tùy chọn `--release` xuất hiện từ JDK 9.

Khi triển khai nâng cấp, chạy bộ kiểm tra trên **runtime cũ và runtime mới** bằng môi trường riêng, đồng thời đo hiệu năng và thử các phiên bản thư viện thực tế. `--release` giúp kiểm tra tương thích nguồn/API mục tiêu nhưng **không thay thế việc chạy mã trên runtime mục tiêu**.

## 13. Xây dựng ma trận kiểm thử trước và sau nâng cấp

Một bộ test “happy path” với vài số dương là chưa đủ. Nên xây ma trận những biên và thuộc tính ngữ nghĩa sau:

| Nhóm kiểm thử | Bộ dữ liệu/điều kiện | Kỳ vọng cần ghi rõ |
|---|---|---|
| **Nguồn rỗng** | `[]`; mọi phần tử bị `filter` loại | Tổng, average, Optional, Map/list rỗng |
| **Null** | Null đầu nguồn, trong danh sách con, mapper trả null | Lọc, chấp nhận, từ chối hoặc báo lỗi? |
| **Trùng khóa** | Nhiều bản ghi cùng SKU | Cộng, giữ đầu/cuối, chọn max hay ném ngoại lệ? |
| **Thứ tự** | List có thứ tự; Set không có thứ tự; pipeline `unordered()` | Khi nào phải bảo toàn encounter order? |
| **Song song** | `parallelStream()`; nhiều cách chia `Spliterator` | Giá trị tương đương, không phụ thuộc side effect |
| **Sai số** | Tổng rất lớn, `Double.NaN`, vô cực, số thập phân | Chấp nhận dung sai, phát hiện tràn, xử lý dữ liệu đặc biệt |
| **Khả năng sửa** | Caller gọi `add`/`remove` trên kết quả | Có phải yêu cầu của API không? |
| **Nguồn một lần** | Stream đã tiêu thụ; đọc từ tệp | Có sử dụng lại Stream sai hay quên đóng không? |
| **Điều kiện dừng** | Predicate thay đổi đúng/sai nhiều lần | `filter` khác `takeWhile`, `dropWhile` và `limit` |
| **API theo phiên bản** | Java 8/11/17/21/24 tùy hệ thống | Có dùng tính năng mới vượt mức hỗ trợ không? |

### 13.1. Golden tests và kiểm thử bất biến

Nên kết hợp hai cách:

- **Golden tests:** với dữ liệu nhỏ đã biết, ghi lại kết quả chính xác mang ý nghĩa nghiệp vụ, ví dụ `P01 -> 400`, `count -> 3`, `[A,B]` khi thứ tự được yêu cầu.
- **Property/invariant tests:** kiểm tra đặc tính trên nhiều bộ dữ liệu, ví dụ tổng số đếm theo nhóm bằng tổng số bản ghi hợp lệ, kết quả `sum` tuần tự/song song tương đương khi phép cộng không tràn, hoặc `distinct` không làm xuất hiện phần tử mới.

Đừng lưu `Map.toString()` hay thứ tự duyệt `HashSet` làm golden output nếu hợp đồng không yêu cầu thứ tự ấy. Khi so Map và Set, so theo **nội dung**, không so thứ tự in ra console.

### 13.2. Chạy cả mức nguồn lẫn runtime

Với một dự án hỗ trợ Java 8 nhưng phát triển trên JDK mới, nên:

1. Biên dịch với mức API/bytecode tối thiểu được hỗ trợ (ví dụ `javac --release 8` trên JDK đủ mới).
2. Chạy trên JRE tối thiểu thực sự cần hỗ trợ.
3. Chạy cùng bộ test trên JRE dự kiến nâng cấp.
4. Thử tổ hợp thư viện và dữ liệu thật, kiểm tra ngoại lệ, tài nguyên, bộ nhớ và hiệu năng.
5. Chỉ thay các phép toán sau khi đã xác định rõ hợp đồng ngữ nghĩa và các test biên.

Đừng bỏ qua bước 2 chỉ vì chương trình đã chạy trên JDK mới. Mục tiêu của `--release` là kiểm soát phiên bản API/bytecode, không chứng minh mọi hành vi ở runtime cũ.

## 14. Quy trình rà soát một pull request thay Stream

Trước khi chấp nhận thay đổi “rút gọn code”, hãy đối chiếu hai pipeline ở những mặt sau:

| Thay đổi đề xuất | Câu hỏi bắt buộc |
|---|---|
| `collect(toList())` → `toList()` | Caller có sửa List không? JDK tối thiểu ≥ 16 không? |
| `collect(toList())` → `toUnmodifiableList()` | Nguồn có thể chứa null không? JDK tối thiểu ≥ 10 không? |
| `Stream.of(value)` → `ofNullable(value)` | Có cần giữ phần tử null như một bản ghi không? |
| `filter(p)` → `takeWhile(p)` | Predicate có thể từ đúng thành sai rồi đúng lại không? |
| `limit(n)` → `iterate(seed, hasNext, next)` | Giới hạn theo **số phần tử** hay theo **giá trị**? |
| `findFirst()` → `findAny()` | Có cần phần tử đầu theo encounter order không? |
| `reduce(op)` → `sum()` | Có cần phân biệt nguồn rỗng với tổng bằng 0 không? |
| `average()` → `averagingInt(...)` | Có chấp nhận trung bình 0.0 khi nguồn rỗng không? |
| `toMap(...)` → `toConcurrentMap(...)` | Merge có phụ thuộc thứ tự không? |
| `flatMap(...)` → `mapMulti(...)` | Có phát đúng số phần tử, đúng thứ tự và xử lý null/tài nguyên tương đương không? |
| `sequential()` → `parallel()` | Reducer/collector có hợp đồng đúng, không side effect chia sẻ không? |
| `collect(toList())` sau `Files.lines` → một API trả Stream | Ai đóng file? Stream có bị dùng sau khi đóng không? |

### 14.1. Ví dụ review một thay đổi nhỏ

**Mã cũ, hỗ trợ Java 8:**

```java
List<String> selected = names.stream()
        .filter(name -> name.startsWith("A"))
        .collect(Collectors.toList());
```

**Đề xuất mới, yêu cầu Java 16+:**

```java
List<String> selected = names.stream()
        .filter(name -> name.startsWith("A"))
        .toList();
```

Để phê duyệt đúng, cần xác định:

1. Mức JDK tối thiểu của sản phẩm **đã** cho phép Java 16+ chưa?
2. Có nơi nào về sau gọi `selected.add(...)` hay `selected.remove(...)` không? Nếu có, refactor làm thay đổi hợp đồng.
3. Nếu `names` chứa null, biểu thức `name.startsWith("A")` vốn đã ném lỗi; đổi terminal operation **không khắc phục** điều này.
4. Với `names` có encounter order, hai cách có cùng thứ tự nội dung khi pipeline không đổi; **không** cần khóa chặt implementation List.

Nếu caller thực sự cần List mutable, giữ cách tạo `ArrayList` được yêu cầu tường minh, thay vì quyết định theo tên phương thức ngắn hơn.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Biên dịch trên JDK mới thì chạy được trên mọi JDK cũ.” | Phải kiểm tra mức bytecode/API và chạy trên runtime mục tiêu. |
| “`Collectors.toList()` luôn trả `ArrayList` mutable.” | API không cam kết implementation hoặc khả năng sửa. |
| “`Stream.toList()` giống hệt `Collectors.toList()`.” | `toList()` từ Java 16 trả List không sửa được; cần rà soát caller. |
| “`toUnmodifiableList()` giống `toList()` cả về null.” | `toUnmodifiableList()` từ chối null, còn `Stream.toList()` có thể chứa null. |
| “`Stream.ofNullable(null)` chứa một phần tử null.” | Nó tạo Stream rỗng; `Stream.of((T) null)` mới chứa một phần tử null. |
| “`takeWhile` là cách viết khác của `filter`.” | Với Stream có thứ tự, `takeWhile` chỉ lấy đoạn đầu liên tiếp thỏa predicate. |
| “`findAny` sẽ trả phần tử đầu khi dữ liệu nhỏ.” | API không cam kết; dùng `findFirst` nếu yêu cầu phần tử đầu. |
| “Đổi JDK làm `HashMap` in thứ tự khác là regression.” | Nếu không có hợp đồng thứ tự, đây có thể là hành vi được phép. |
| “`peek` được gọi một lần cho mỗi phần tử trước `count`.” | Implementation có thể bỏ qua các thao tác không cần cho kết quả. |
| “`average` và `Collectors.averagingInt` giống nhau trên nguồn rỗng.” | Một bên trả Optional rỗng, bên kia trả số `0.0`. |
| “Chạy parallel thì tự an toàn và nhanh hơn.” | Cần hợp đồng reduction, tránh trạng thái chung và đo hiệu năng. |
| “Terminal operation tự đóng `Files.lines`.” | Phải đóng nguồn I/O bằng `try-with-resources` hoặc hợp đồng sở hữu rõ ràng. |

## 16. Bài tập thực hành có đáp án

### Bài 1. Đổi sang toList

Một phương thức cũ trả danh sách và caller có dòng `result.add("NEW")`. Có nên đổi ngay `collect(Collectors.toList())` thành `Stream.toList()`?

**Đáp án:** Không nếu hợp đồng caller đòi List mutable. `Stream.toList()` từ Java 16 không sửa được. Dùng `Collectors.toCollection(ArrayList::new)` hoặc `new ArrayList<>(stream.toList())` khi muốn bảo đảm khả năng sửa.

### Bài 2. Null và nguồn rỗng

`Stream.of((String) null).count()` và `Stream.<String>ofNullable(null).count()` có cùng kết quả không?

**Đáp án:** Không. Vế đầu có **1** phần tử null, vế sau có **0** phần tử. `ofNullable` chỉ sẵn có từ Java 9.

### Bài 3. filter so với takeWhile

Cho `[1, 2, 0, 3]`, kết quả `filter(n -> n > 0)` và `takeWhile(n -> n > 0)` lần lượt là gì?

**Đáp án:** `filter` cho `[1, 2, 3]`, `takeWhile` cho `[1, 2]` khi nguồn có thứ tự. Hai phép không thay thế tương đương.

### Bài 4. Kiểm tra Optional trên nguồn rỗng

Một refactor thay `IntStream.empty().average()` bằng `Stream.<Integer>empty().collect(Collectors.averagingInt(Integer::intValue))`. Hợp đồng thiếu dữ liệu có giữ nguyên không?

**Đáp án:** Không. `average()` trả `OptionalDouble.empty()`, collector trả số `0.0`. Nếu nghiệp vụ cần phân biệt thiếu dữ liệu, phải giữ Optional hoặc kèm count.

### Bài 5. Thay toMap bằng toConcurrentMap

Đang dùng hàm merge `(oldValue, newValue) -> newValue` để chọn phần tử cuối của List có thứ tự. Có thể đổi sang `toConcurrentMap` và kỳ vọng luôn chọn phần tử cuối như cũ không?

**Đáp án:** Không. `toConcurrentMap` là unordered; thứ tự cập nhật không nhất thiết là encounter order. Nếu cần bản ghi mới nhất, dùng thuộc tính thời gian hoặc phiên bản và một quy tắc phá hòa.

### Bài 6. count và peek

`List.of("A", "B").stream().peek(System.out::println).count()` có luôn in hai dòng không?

**Đáp án:** Không. `List.of` có từ Java 9; `count` có thể suy ra kích thước và bỏ duyệt nếu không cần. Dùng `peek` để quan sát/debug, không dùng làm bước nghiệp vụ bắt buộc.

### Bài 7. Tràn số nguyên

Vì sao `IntStream.of(Integer.MAX_VALUE, 1).sum()` không trả tổng toán học mong đợi? Sửa thế nào?

**Đáp án:** Phép tổng ở kiểu `int` bị tràn. Có thể `mapToLong(n -> (long) n).sum()` cho ví dụ này; nếu vẫn có thể vượt `long` thì cần chiến lược kiểu số/kiểm soát tràn khác.

### Bài 8. Golden test có thứ tự

Có nên so `Collectors.toSet().toString()` với chuỗi `"[A, B]"` trên các JDK khác nhau không?

**Đáp án:** Không. `toSet` không cam kết thứ tự phần tử. So bằng `Set.equals` hoặc sắp xếp tường minh nếu output nghiệp vụ yêu cầu thứ tự.

### Bài 9. Nâng JDK và đổi API cùng lúc

Một dự án đồng thời chuyển JDK 8 lên JDK 21 và thay `flatMap` bằng `mapMulti`, `collect(toList())` bằng `toList()`. Nếu test thất bại, nên kiểm tra theo thứ tự nào?

**Đáp án định hướng:** Tách hai loại thay đổi: trước tiên chạy bộ kiểm tra nghiệp vụ trên JDK mới **với logic cũ** khi còn tương thích; sau đó thay từng phép toán, xác minh số phần tử và thứ tự sau làm phẳng, null, ngoại lệ, tính không sửa được của kết quả và chi phí bộ nhớ. Làm từng bước giúp định vị nguyên nhân hơn là đổi nhiều hành vi cùng lúc.

## 17. Checklist trước khi chấp nhận nâng JDK hoặc refactor Stream

1. **Xác định JDK tối thiểu và runtime mục tiêu.** API mới có vượt mức hỗ trợ không? Có cần `--release` hoặc chiến lược preview không?
2. **Ghi rõ hợp đồng dữ liệu.** Nguồn rỗng, null, trùng khóa, thứ tự và điều kiện dừng xử lý thế nào?
3. **Kiểm tra đặc tính kết quả.** List/Map có sửa được không? Thứ tự có được bảo đảm không? Có thay `Optional` bằng số mặc định không?
4. **Đối chiếu phép biến đổi.** `map`/`flatMap`/`mapMulti`, `filter`/`takeWhile` và `limit` có giữ tập phần tử mong muốn không?
5. **Đối chiếu phép kết thúc.** `findFirst`/`findAny`, `reduce`/`sum`, `average`/`averaging...` và collector Map có thay ngữ nghĩa không?
6. **Rà soát song song.** Accumulator/combiner có kết hợp đúng, không phụ thuộc thứ tự không được bảo đảm hoặc trạng thái mutable dùng chung không?
7. **Rà soát số học.** Tràn `int`/`long`, sai số `double`, `NaN` và chính sách `BigDecimal` có được kiểm soát không?
8. **Rà soát tài nguyên.** Mọi Stream nguồn I/O cần đóng có `try-with-resources` hoặc quyền sở hữu rõ ràng không?
9. **Chạy kiểm thử trên các runtime cần hỗ trợ.** So kết quả theo bất biến nghiệp vụ, không theo implementation hoặc thứ tự tình cờ.
10. **Đo hiệu năng riêng sau khi xác nhận tính đúng.** Không đổi ngữ nghĩa chỉ để tối ưu mà không có bằng chứng đo lường.

**Kết luận:** Khi nâng JDK hoặc thay phép toán Stream, hãy giữ nguyên **hợp đồng kết quả** thay vì chỉ giữ mã biên dịch hoặc các dòng log trông giống nhau. Những khác biệt quan trọng cần rà soát là **tập phần tử được xử lý, thứ tự, khả năng sửa kết quả, null, nguồn rỗng, khóa trùng, phép gộp, độ chính xác và vòng đời tài nguyên**. Dùng một ma trận test có các trường hợp biên và so sánh theo những gì Java API thật sự bảo đảm, ta có thể tận dụng các tính năng Stream mới mà không đánh đổi tính đúng của ứng dụng.
