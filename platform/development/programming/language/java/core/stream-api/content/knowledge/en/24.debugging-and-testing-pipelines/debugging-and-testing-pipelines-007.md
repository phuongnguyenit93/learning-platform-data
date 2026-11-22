# Đối chiếu kết quả tuần tự và song song

Java Stream API cho phép đổi cách thực thi của nhiều pipeline chỉ bằng `parallel()` hoặc `parallelStream()`. Tuy nhiên, **chạy được** không có nghĩa **cho kết quả đúng**. Một pipeline tuần tự có thể trông hoàn toàn hợp lý nhưng khi thực thi song song lại mất phần tử, đếm sai, phát sinh ngoại lệ không ổn định hoặc trả các giá trị khác nhau giữa các lượt chạy. Muốn gỡ lỗi, trước tiên phải xác định **kết quả nào cần giống nhau về ngữ nghĩa**, sau đó mới viết phép so sánh tương ứng.

Bài thuộc chương **Gỡ lỗi và kiểm thử pipeline** của module `JAVA_STREAM_API`. Ta sẽ xây cách đối chiếu kết quả tuần tự và song song với `filter`, `map`, `reduce`, `collect`, `groupingBy`, các phép toán có thứ tự và các thao tác dừng sớm. Đồng thời, bài phân tích vì sao kết quả có thể khác do side effect, accumulator chia sẻ, phép gộp sai, sai số dấu phẩy động, thứ tự không được bảo đảm hoặc nguồn dữ liệu thay đổi; cuối cùng là bộ kiểm thử có thể tái lập và quy trình chẩn đoán khi sự cố chỉ xuất hiện với parallel stream.

Các ví dụ chính dùng **Java 8 trở lên**, trừ những đoạn kiểm thử minh họa JUnit Jupiter có phụ thuộc thư viện kiểm thử. Những lệnh Java đặt ở mức cao nhất trong các ví dụ cần được đưa vào phương thức (chẳng hạn `main`) hoặc chạy trong JShell; các lớp/helper có thể lưu riêng. `Stream` là API xử lý dữ liệu khai báo và lazy; việc bật parallel không làm mất những yêu cầu về an toàn trạng thái, vòng đời nguồn I/O hoặc giới hạn hiệu năng.

## 1. Mục tiêu không phải lúc nào cũng là so sánh hai chuỗi in ra

Xét pipeline sau:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> source = Arrays.asList(5, 2, 3, 4, 1);

List<Integer> sequential = source.stream()
        .filter(n -> n % 2 == 1)
        .map(n -> n * n)
        .collect(Collectors.toList());

List<Integer> parallel = source.parallelStream()
        .filter(n -> n % 2 == 1)
        .map(n -> n * n)
        .collect(Collectors.toList());

System.out.println(sequential); // [25, 9, 1]
System.out.println(parallel);   // [25, 9, 1]
```

Nguồn là `List` có **encounter order** theo vị trí. Cả `filter` và `map` ở đây không thay đổi encounter order; `Collectors.toList()` thu thập theo thứ tự gặp phần tử. Do đó, với dữ liệu cố định và các hàm thuần, hai danh sách **phải có nội dung và thứ tự như nhau**.

Nhưng xem ví dụ khác:

```java
import java.util.Set;
import java.util.stream.Collectors;

Set<Integer> a = source.stream()
        .map(n -> n % 3)
        .collect(Collectors.toSet());

Set<Integer> b = source.parallelStream()
        .map(n -> n % 3)
        .collect(Collectors.toSet());

System.out.println(a.equals(b)); // true
```

`Set` không có yêu cầu thứ tự duyệt ở ví dụ này. Nếu in hai tập hợp ra và thấy thứ tự khác, đó **không nhất thiết là lỗi**: điều cần so là **các phần tử thuộc tập hợp**, không phải thứ tự hiển thị.

**Nguyên tắc đầu tiên:** định nghĩa **hợp đồng đầu ra** rồi chọn cách so sánh. Không dùng `toString()` hoặc log luồng làm tiêu chí đúng/sai cho mọi pipeline.

## 2. Các hợp đồng kết quả thường gặp cần phân biệt

| Dạng kết quả | Điều cần so sánh | Không được giả định |
| --- | --- | --- |
| `List<T>` từ nguồn ordered, collector giữ order | Cùng số phần tử, cùng giá trị tại cùng vị trí | Luồng chạy cùng thứ tự thời gian |
| `Set<T>` | Cùng phần tử theo `equals/hashCode` | Thứ tự lặp, thứ tự in giống nhau |
| `Map<K,V>` đếm/tổng theo khóa | Cùng khóa và giá trị theo từng khóa | Thứ tự duyệt Map giống nhau |
| Kết quả `double` của phép tổng hợp | Đúng trong sai số đã định nghĩa; xử lý `NaN`/vô cực riêng | Luôn bằng nhau từng bit |
| Phép chọn `findFirst` trên nguồn ordered | Cùng phần tử đầu theo encounter order | Số lần predicate được gọi giống nhau |
| Phép chọn `findAny` | Một phần tử **bất kỳ** thỏa điều kiện, hoặc rỗng đúng hợp đồng | Cùng phần tử được chọn mỗi lần |
| `forEach` có side effect | Không nên coi side effect là kết quả chuẩn | Thứ tự callback hoặc thread cố định |
| `groupingByConcurrent(..., toList())` | Nhóm và đa tập phần tử trong từng nhóm nếu không yêu cầu order | Thứ tự phần tử trong mỗi nhóm |

Một **đa tập** (*multiset*) là tập hợp có tính cả số lần lặp. Ví dụ `[A,A,B]` và `[A,B,B]` có cùng Set `{A,B}` nhưng **không cùng đa tập**. Khi thứ tự không quan trọng nhưng số lần xuất hiện quan trọng, chỉ chuyển về `Set` sẽ làm mất thông tin kiểm thử.

Nếu nghiệp vụ cần “bản ghi mới nhất”, hãy định nghĩa một khóa sắp xếp/tie-breaker rõ ràng, chứ không để quá trình song song tự quyết định bản ghi nào là cuối cùng.

## 3. Vì sao một pipeline có thể đúng khi tuần tự nhưng sai khi song song?

Có bốn nhóm nguyên nhân thường gặp:

1. **Chia sẻ trạng thái mutable ngoài pipeline**: nhiều luồng cùng sửa `ArrayList`, `HashMap`, biến đếm hoặc đối tượng không thread-safe.
2. **Phép rút gọn không hợp lệ**: thiếu identity đúng, accumulator/combiner không tương thích, phép toán không kết hợp (*associative*).
3. **Giả định encounter order không được cam kết**: `findAny`, `forEach`, `unordered` hoặc collector concurrent/unordered.
4. **Khác biệt số học và nguồn**: floating point, tràn số, dữ liệu nguồn bị sửa trong khi duyệt hoặc hàm phụ thuộc đồng hồ, random, I/O ngoài.

`parallel()` chỉ thay đổi **chế độ thực thi**; nó không tự cấp mutex cho biến mutable bên ngoài, không sửa một combiner sai, và không tạo bản sao bất biến của nguồn.

### Minh họa hai con đường thu thập

```text
TUẦN TỰ
  source -> map/filter -> accumulator A -> result

SONG SONG, collector KHÔNG concurrent
  source
    |---- phần 1 -> A1 --\
    |---- phần 2 -> A2 ---+--> combiner --> result
    |---- phần 3 -> A3 --/

SONG SONG, collector concurrent phù hợp
  source -> nhiều tác vụ -> cùng accumulator A an toàn -> result
```

Phần lớn Collector chuẩn không yêu cầu bạn chia sẻ một container giữa các nhánh. Việc `Collectors.toList()` có thể hoạt động đúng với parallel stream **không đồng nghĩa** `ArrayList` là thread-safe để bạn tự gọi `add` từ `parallel().forEach(...)`.

## 4. Xây một phép đối chiếu tái sử dụng

Để kiểm tra cùng một pipeline ở hai chế độ, cần **hai Stream mới từ cùng một dữ liệu ổn định**. Một Stream đã chạy terminal operation không thể chạy lại.

Dưới đây là helper dùng với nguồn có thể tạo lại trong bộ nhớ:

```java
import java.util.Objects;
import java.util.function.BiPredicate;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.stream.Stream;

public final class StreamComparison {
    private StreamComparison() {}

    public static <T, R> void assertEquivalent(
            Supplier<Stream<T>> freshSource,
            Function<Stream<T>, R> pipeline,
            BiPredicate<? super R, ? super R> equivalent) {

        Objects.requireNonNull(freshSource, "freshSource");
        Objects.requireNonNull(pipeline, "pipeline");
        Objects.requireNonNull(equivalent, "equivalent");

        R sequential;
        R parallel;

        try (Stream<T> stream = freshSource.get()) {
            sequential = pipeline.apply(stream.sequential());
        }

        try (Stream<T> stream = freshSource.get()) {
            parallel = pipeline.apply(stream.parallel());
        }

        if (!equivalent.test(sequential, parallel)) {
            throw new AssertionError(
                    "Sequential=" + sequential
                    + ", parallel=" + parallel
            );
        }
    }
}
```

Cách dùng cho List có thứ tự:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<Integer> values = Arrays.asList(1, 2, 3, 4, 5, 6);

StreamComparison.assertEquivalent(
        values::stream,
        s -> s.filter(n -> n % 2 == 0)
              .map(n -> n * 10)
              .collect(Collectors.toList()),
        Objects::equals
);
```

Các điểm cần lưu ý:

- `freshSource.get()` phải trả **Stream mới mỗi lần**, không trả cùng một Stream đã tiêu thụ.
- Dữ liệu ở hai lần thử phải **ổn định và có ý nghĩa như nhau**; nếu nguồn thay đổi, phép so sánh có thể không hợp lệ.
- `pipeline` phải không dựa vào biến mutable bên ngoài, thời gian hiện tại hoặc random chưa được cố định; nó phải thực hiện **terminal operation** và trả kết quả đã hoàn tất, không trả một Stream lazy phụ thuộc nguồn đã đóng.
- `try-with-resources` giúp đóng Stream trong helper. Với `List`, `close()` thường không có tài nguyên cần giải phóng; với nguồn I/O, việc đóng có ý nghĩa thực.
- `BiPredicate` cho phép so sánh theo **ngữ nghĩa** thay vì luôn dùng `equals`.

Nếu factory nguồn ném `IOException` đã kiểm tra (*checked exception*), `Supplier<Stream<T>>` không có `throws IOException` phù hợp; nên dùng helper khác với giao diện nguồn có thể ném ngoại lệ, hoặc mở tệp riêng trong hai khối `try` như phần sau.

**Không** đưa một `Iterator` một lần, `BufferedReader` đã bị đóng hoặc một đối tượng Stream dùng lại vào factory này rồi kỳ vọng hai lần chạy đọc được cùng dữ liệu.

## 5. Kiểm thử pipeline giữ encounter order

Với nguồn ordered và phép biến đổi stateless, thứ tự kết quả phải được giữ khi terminal operation có hợp đồng giữ thứ tự.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> normalize(Stream<String> stream) {
    return stream
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(String::toUpperCase)
            .collect(Collectors.toList());
}

List<String> input = Arrays.asList(
        "  apple ", "", "banana ", " apple", "cherry "
);

List<String> a = normalize(input.stream());
List<String> b = normalize(input.parallelStream());

System.out.println(a);         // [APPLE, BANANA, APPLE, CHERRY]
System.out.println(a.equals(b)); // true
```

Đây là phép so sánh bằng `List.equals`: vừa kiểm tra số phần tử, vừa kiểm tra từng vị trí. Không cần tự sắp xếp hai danh sách, vì thao tác sắp xếp **có thể che giấu lỗi mất thứ tự** mà nghiệp vụ muốn phát hiện.

### sorted và quy tắc hòa điểm

Khi sắp xếp đối tượng, comparator nên xác định thứ tự đầy đủ nếu muốn đầu ra ổn định ở những điểm có cùng khóa chính.

```java
import java.util.Comparator;

// Ví dụ định nghĩa comparator cho một kiểu Employee có id và score.
Comparator<Employee> order = Comparator
        .comparingInt(Employee::score)
        .reversed()
        .thenComparing(Employee::id);
```

Đây là mẫu minh họa giả định `Employee` có `score()` và `id()`. Nếu chỉ so sánh `score`, nhiều nhân viên có cùng điểm có thể hòa điểm. Với nguồn ordered, `sorted` có yêu cầu ổn định thích hợp, nhưng với nguồn unordered hoặc các thao tác khác không giữ order, muốn kết quả độc lập với encounter order thì nên bổ sung khóa phụ `id`.

Không sửa các trường dùng trong comparator hoặc `hashCode` của phần tử trong lúc Stream đang duyệt.

## 6. Đối chiếu Set, Map và thống kê nhóm

### Set: so theo phần tử, không so theo chuỗi in ra

```java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

Set<String> seq = Arrays.asList(
        "A", "B", "A", "C"
).stream().collect(Collectors.toSet());

Set<String> par = Arrays.asList(
        "A", "B", "A", "C"
).parallelStream().collect(Collectors.toSet());

if (!seq.equals(par)) {
    throw new AssertionError("Distinct values differ");
}
```

Không nên dùng `seq.toString().equals(par.toString())`. Cả hai Set có thể chứa cùng giá trị nhưng duyệt theo thứ tự khác.

### Map: so theo khóa và số lượng

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> levels = Arrays.asList(
        "ERROR", "WARN", "INFO", "ERROR", "WARN", "ERROR"
);

Map<String, Long> seq = levels.stream()
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

ConcurrentMap<String, Long> par = levels.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(seq);            // Không dựa vào thứ tự in Map
System.out.println(seq.equals(par)); // true
```

`groupingByConcurrent` không cam kết encounter order của phần tử trong từng nhóm. Nhưng ở đây chỉ lưu **số lượng** theo khóa, nên so sánh bằng `Map.equals` là phù hợp. Với dữ liệu cố định và phép đếm không tràn, `ERROR=3`, `WARN=2`, `INFO=1`.

### Khi giá trị Map là List và thứ tự không được cam kết

Nếu mỗi nhóm lưu danh sách, phép so sánh trực tiếp `List.equals` có thể thất bại chỉ vì **thứ tự phần tử trong nhóm** khác nhau. Khi nghiệp vụ không quan tâm thứ tự trong nhóm nhưng quan tâm số lần lặp, tạo bản sao rồi sắp xếp để so như **đa tập**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

static Map<String, List<Integer>> canonicalize(
        Map<String, ? extends List<Integer>> input) {

    Map<String, List<Integer>> normalized = new TreeMap<>();

    input.forEach((key, values) -> {
        List<Integer> copy = new ArrayList<>(values);
        Collections.sort(copy);
        normalized.put(key, copy);
    });

    return normalized;
}
```

`canonicalize` giữ nguyên số lần xuất hiện của mỗi giá trị nhờ **không loại trùng**. Nó giả định khóa chuỗi không null và mỗi danh sách chứa số nguyên khác null để `TreeMap`/`Collections.sort` hoạt động theo thứ tự tự nhiên; hãy điều chỉnh nếu mô hình dữ liệu cho phép null.

Quan trọng: **chỉ** chuẩn hóa khi hợp đồng thật sự không yêu cầu thứ tự. Nếu cần giữ thứ tự trong từng nhóm, việc sắp xếp trước khi so có thể che mất bug.

## 7. findFirst, findAny và short-circuit

Hai thao tác này có hợp đồng khác nhau:

- `findFirst()`: trên Stream **có encounter order**, trả phần tử đầu theo thứ tự ấy nếu tồn tại.
- `findAny()`: được phép trả **bất kỳ** phần tử nào, hữu ích khi không cần thứ tự hoặc muốn giảm phối hợp song song.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<Integer> numbers = Arrays.asList(5, 8, 11, 14, 17);

Optional<Integer> firstSequential = numbers.stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

Optional<Integer> firstParallel = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(firstSequential);           // Optional[8]
System.out.println(firstSequential.equals(
        firstParallel));                       // true
```

Nhưng:

```java
Optional<Integer> anyParallel = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .findAny();

if (!anyParallel.isPresent()
        || (anyParallel.get() != 8
            && anyParallel.get() != 14)) {
    throw new AssertionError("findAny returned invalid value");
}
```

Vì danh sách có hai số chẵn, `findAny` có thể chọn 8 hoặc 14; **không nên yêu cầu nó luôn chọn 8**. Trong test tổng quát, hãy xác minh phần tử được trả về **thuộc tập nghiệm**, và việc có/không có kết quả đúng khi tập nghiệm rỗng/không rỗng.

### Kiểm thử anyMatch, allMatch, noneMatch

Với predicate thuần và đầu vào cố định, các kết quả logic này phải giữ nguyên giữa sequential và parallel. Tuy nhiên, **số lần predicate được gọi không nhất thiết giống nhau**, do short-circuit:

```java
boolean seq = numbers.stream().anyMatch(n -> n > 10);
boolean par = numbers.parallelStream().anyMatch(n -> n > 10);

System.out.println(seq == par); // true
```

Không viết test kỳ vọng `peek` hoặc predicate được gọi đúng `k` lần ở parallel pipeline. Một phần tử thỏa điều kiện có thể đã được tìm thấy trong khi các tác vụ khác vẫn xử lý một số phần tử.

### limit, skip và unordered

Với nguồn ordered, `limit(n)` có ý nghĩa lấy **n phần tử đầu theo encounter order**. Nếu dùng `unordered()`, phép chọn phần tử được phép khác:

```java
List<Integer> sample = numbers.parallelStream()
        .unordered()
        .limit(2)
        .collect(java.util.stream.Collectors.toList());
```

Test hợp lý cho ví dụ này là `sample.size() == 2` và mỗi phần tử thuộc nguồn; **không bắt buộc** kết quả là `[5,8]`. `unordered()` không phải phép xáo trộn ngẫu nhiên, nhưng bỏ ràng buộc thứ tự có thể đổi ngữ nghĩa của việc chọn phần tử đầu.

## 8. Side effect là nguồn bug phổ biến nhất

### Ví dụ sai: nhiều luồng cùng thêm vào ArrayList

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

// SAI: ArrayList không an toàn cho nhiều luồng cùng add.
IntStream.range(0, 100_000)
        .parallel()
        .forEach(shared::add);

// Không được khẳng định shared.size() luôn bằng 100_000.
```

Kết quả có thể bị thiếu phần tử, gặp lỗi hoặc đôi khi tình cờ đúng. Thử chạy 100 lần mà không gặp lỗi vẫn **không chứng minh thread-safe**.

Thay bằng collector:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> safe = IntStream.range(0, 100_000)
        .boxed()
        .parallel()
        .collect(Collectors.toList());

System.out.println(safe.size()); // 100000
System.out.println(safe.get(0));  // 0
```

Với nguồn `IntStream.range` ordered và `toList`, List kết quả giữ thứ tự gặp. Trong ví dụ đầu, `forEach` **không cam kết** gọi theo thứ tự nguồn; kể cả nếu dùng cấu trúc dữ liệu đồng bộ để tránh race, thứ tự thêm phần tử cũng không tự nhiên được bảo đảm.

### Không dùng bộ đếm mutable ngoài pipeline

```java
int[] count = {0};

// SAI: cập nhật shared count[0]++ không nguyên tử.
numbers.parallelStream().forEach(n -> count[0]++);
```

Đếm đúng:

```java
long countEven = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .count();

System.out.println(countEven); // 2
```

Dùng `AtomicInteger` có thể tránh một loại race khi tăng bộ đếm, nhưng **không tự làm phép biến đổi có side effect trở nên non-interfering, deterministic hoặc đúng thứ tự**. Nếu mục tiêu chỉ là thống kê, hãy dùng `count`, `sum`, `reduce` hoặc `collect`.

### Lỗi khác: thay đổi nguồn trong khi duyệt

```java
// SAI: không sửa cấu trúc source từ một thao tác đang duyệt source.
source.parallelStream()
        .forEach(n -> source.remove(n));
```

Một nguồn như `ArrayList` không chịu được kiểu can thiệp cấu trúc này theo hợp đồng Stream. Tương tự, đọc và sửa cùng một `HashMap` ở các thao tác `map` hoặc `filter` có thể tạo kết quả khó dự đoán.

Hãy biến đổi thành một cấu trúc **mới** rồi thay nguồn sau khi pipeline hoàn tất, thay vì can thiệp vào nguồn đang được tiêu thụ.

## 9. Gỡ lỗi reduce: identity, associativity, compatibility

Phép rút gọn đúng cho parallel stream cần tuân thủ các hợp đồng về phần tử đồng nhất và phép kết hợp.

### Sai: phép trừ không kết hợp

```java
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(1, 2, 3, 4);

int seq = values.stream()
        .reduce(0, (a, b) -> a - b);

int par = values.parallelStream()
        .reduce(0, (a, b) -> a - b);

System.out.println(seq); // -10
System.out.println(par); // Không có bảo đảm phải bằng -10
```

Vì:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Đổi cách gom nhánh làm kết quả thay đổi. `reduce` trên parallel stream có thể kết hợp kết quả từng phần theo cách khác sequential, nên không thể dùng phép trừ như một phép gộp có tính kết hợp.

Sửa khi mục tiêu thật là tính tổng:

```java
int sumSeq = values.stream().reduce(0, Integer::sum);
int sumPar = values.parallelStream().reduce(0, Integer::sum);

System.out.println(sumSeq); // 10
System.out.println(sumSeq == sumPar); // true
```

### Sai: identity không thực sự đồng nhất

```java
// SAI nếu muốn tính tổng của phần tử nguồn.
int seqWithWrongIdentity = values.stream()
        .reduce(10, Integer::sum);

int parWithWrongIdentity = values.parallelStream()
        .reduce(10, Integer::sum);
```

Ở đây `10` **không phải identity** của phép cộng. Sequential cộng thêm 10 một lần, nhưng parallel có thể cộng thêm identity vào nhiều phân hoạch. Nếu yêu cầu là tổng, identity phải là `0`.

Với phép tìm cực đại trên số âm, dùng `reduce(Integer::max)` trả `Optional<Integer>` hoặc chọn identity thật sự phù hợp miền dữ liệu; không mặc định `reduce(0, Integer::max)` sẽ đúng.

### Ba tham số reduce cũng có combiner

```java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("a", "bb", "ccc");

int lengthSeq = words.stream()
        .reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum
        );

int lengthPar = words.parallelStream()
        .reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum
        );

System.out.println(lengthSeq);           // 6
System.out.println(lengthSeq == lengthPar); // true
```

Với `reduce(identity, accumulator, combiner)`, phải kiểm tra:

- Identity là trạng thái khởi đầu thích hợp.
- Combiner có tính kết hợp.
- Combiner tương thích với cách accumulator thêm từng phần tử.
- Cả hai hàm không can thiệp vào dữ liệu nguồn hoặc một đối tượng mutable dùng chung.

Đừng đánh tráo `reduce` immutable với `collect` mutable để chia sẻ `ArrayList` làm identity; cách làm đó dễ vi phạm hợp đồng khi có nhiều nhánh.

## 10. collect: vì sao container mutable vẫn có thể an toàn?

`collect(supplier, accumulator, combiner)` cho phép framework cấp **nhiều container riêng**, rồi gộp chúng bằng combiner. Một container `ArrayList` hoặc class accumulator không thread-safe **vẫn có thể dùng đúng** nếu không chia sẻ nó giữa các nhánh và không khai báo concurrent sai.

Ví dụ tổng hợp số lượng và tổng:

```java
import java.util.Arrays;
import java.util.List;

final class Stats {
    private long count;
    private long sum;

    void add(Integer value) {
        count++;
        sum += value;
    }

    void merge(Stats other) {
        count += other.count;
        sum += other.sum;
    }

    long count() {
        return count;
    }

    long sum() {
        return sum;
    }
}

List<Integer> data = Arrays.asList(1, 2, 3, 4, 5);

Stats sequential = data.stream()
        .collect(Stats::new, Stats::add, Stats::merge);

Stats parallel = data.parallelStream()
        .collect(Stats::new, Stats::add, Stats::merge);

System.out.println(sequential.count()); // 5
System.out.println(parallel.count());   // 5
System.out.println(sequential.sum());   // 15
System.out.println(parallel.sum());     // 15
```

Điểm quan trọng:

- `Stats::new` tạo instance mới mỗi khi Supplier được gọi.
- `add` chỉ cập nhật đúng accumulator đang được giao.
- `merge` cộng đủ trạng thái hai phân hoạch; không bỏ phần tử.
- Kết quả `Stats` được đọc **sau** khi collect hoàn tất, không có tác vụ ngoài đang sửa nó.

Nếu Supplier trả lại cùng `Stats` được tạo ngoài Stream, đó là sai lầm chia sẻ trạng thái. Nếu combiner chỉ trả một phía và không gộp, parallel có thể thiếu số lượng hoặc tổng.

Với Collector tự viết, phải phân biệt `Collector.Characteristics.CONCURRENT` với `Spliterator.CONCURRENT` và việc source chạy parallel. Đừng công bố `CONCURRENT` nếu accumulator không cho phép nhiều luồng cùng gọi trên một container.

## 11. Số thực: đúng về nghiệp vụ không đồng nghĩa bằng từng bit

Phép cộng số dấu phẩy động không có tính kết hợp tuyệt đối do làm tròn:

```text
(1e16 + 1) + (-1e16) có thể thành 0
1e16 + (1 + (-1e16)) cũng có thể thành 0
nhưng cách nhóm và thứ tự khác có thể giữ hoặc mất các số nhỏ
```

Ví dụ so sánh:

```java
import java.util.Arrays;
import java.util.List;

List<Double> amounts = Arrays.asList(
        1.0e16, 1.0, -1.0e16, 1.0
);

double sequential = amounts.stream()
        .reduce(0.0, Double::sum);

double parallel = amounts.parallelStream()
        .reduce(0.0, Double::sum);

System.out.println(sequential); // 1.0 theo thứ tự gộp tuần tự này
System.out.println(parallel);   // Có thể khác do thứ tự gộp
```

Tổng chính xác trong toán học là `2.0`. Một số cách cộng số thực làm tròn mất số `1.0` và có thể cho kết quả khác. Không nên viết test luôn yêu cầu hai `double` **bằng nhau từng bit** cho mọi dạng reduction song song.

### So sánh có dung sai

```java
static boolean approximatelyEqual(
        double a, double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (Double.doubleToLongBits(a)
            == Double.doubleToLongBits(b)) {
        return true;
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double scale = Math.max(Math.abs(a), Math.abs(b));
    double allowed = Math.max(
            absoluteTolerance,
            relativeTolerance * scale
    );

    return Math.abs(a - b) <= allowed;
}
```

Hàm này:

- So sánh từng bit khi hai số bằng nhau đúng theo `doubleToLongBits`.
- Loại các trường hợp `NaN`/vô cực không khớp; với `NaN` ở cả hai vế, quy tắc bit chuẩn hóa của phương thức có thể coi chúng tương đương. Nếu ứng dụng cần coi mọi `NaN` là lỗi dữ liệu, hãy kiểm tra riêng trước.
- Dùng kết hợp ngưỡng tuyệt đối và tương đối; **ngưỡng phải được xác định từ yêu cầu nghiệp vụ**, không chọn tùy tiện để che bug.
- Không giải quyết được tràn số nguyên, sai đơn vị hoặc lỗi công thức. Dung sai chỉ dành cho sai số số học được chấp nhận.

Nếu tiền tệ yêu cầu kết quả **chính xác**, hãy dùng `BigDecimal` (với chính sách scale/rounding rõ ràng) hoặc số nguyên đơn vị nhỏ nhất thay vì `double`:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

List<BigDecimal> money = Arrays.asList(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal seq = money.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal par = money.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(seq.compareTo(par) == 0); // true
```

Ví dụ này dùng `BigDecimal.add` không có `MathContext` nên phép cộng thập phân là chính xác; nếu sử dụng làm tròn ở các bước trung gian, cần đánh giá lại tính kết hợp của phép toán.

## 12. Tràn số nguyên: hai kết quả giống nhau vẫn có thể cùng sai

Giả sử có các số lớn và kết quả vượt miền của `int`:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(
        Integer.MAX_VALUE, 1
);

int seq = values.stream().mapToInt(Integer::intValue).sum();
int par = values.parallelStream().mapToInt(Integer::intValue).sum();

System.out.println(seq);          // -2147483648 do overflow int
System.out.println(seq == par);  // true, nhưng tổng nghiệp vụ sai
```

Phép cộng số nguyên `int` có hành vi overflow theo ngữ nghĩa Java; hai pipeline có thể cùng trả kết quả không mong muốn trong miền nghiệp vụ. Vì vậy **đối chiếu sequential/parallel là điều kiện cần, không phải bằng chứng đầy đủ về đúng đắn**.

Nếu tổng không vượt miền `long`, có thể nâng kiểu trước khi cộng:

```java
long safeSum = values.stream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(safeSum); // 2147483648
```

Khi tổng có thể vượt `Long.MAX_VALUE`, cần số học lớn hơn hoặc cơ chế phát hiện tràn. Cũng không mặc định `Math.addExact` có cùng hành vi ngoại lệ ở mọi thứ tự gộp nếu các tổng trung gian có thể vượt giới hạn dù kết quả cuối cùng nằm trong miền.

Một bộ test tốt cần kiểm tra **giá trị kỳ vọng độc lập** bằng mô hình số học đúng, không chỉ so `seq.equals(par)`.

## 13. Debug pipeline bằng bước trung gian có kiểm soát

Khi thấy kết quả khác nhau, đừng lập tức thêm `println` vào mọi `map` rồi suy luận từ thứ tự log. Trong parallel stream, log từ nhiều thread thường xen kẽ và có thể làm thay đổi timing.

### Đoạn pipeline mẫu

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> pipeline(Stream<String> lines) {
    return lines
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .filter(s -> s.startsWith("ERR"))
            .map(String::toLowerCase)
            .distinct()
            .sorted()
            .collect(Collectors.toList());
}
```

Các bước kiểm tra có hệ thống:

1. **Nguồn:** số lượng phần tử, tính bất biến, encounter order và các giá trị null.
2. **Bộ lọc:** xác nhận phần tử nào đáng được giữ bằng ví dụ nhỏ có kết quả kỳ vọng.
3. **Biến đổi:** làm rõ hàm có thuần, stateless và không sửa nguồn không.
4. **Thao tác stateful:** `distinct`/`sorted`/`limit` có yêu cầu thứ tự hoặc bộ nhớ nào?
5. **Terminal:** kiểu kết quả có cam kết thứ tự không? Collector có combiner đúng không?
6. **So sánh:** dùng phương thức so đúng hợp đồng (`List.equals`, `Map.equals`, đa tập, dung sai...).

### peek hữu ích để quan sát, không phải oracle kiểm thử

```java
long result = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .peek(n -> System.out.println(
                Thread.currentThread().getName() + ": " + n))
        .count();
```

Lệnh này không bảo đảm `peek` được gọi đúng bốn lần. Một số pipeline có nguồn `SIZED` và terminal `count()` có thể được tối ưu mà không cần duyệt từng phần tử; vì vậy `peek` có thể không chạy. Ngay cả khi chạy, thứ tự log song song không phải thứ tự dữ liệu.

Dùng `peek` để **chẩn đoán tạm thời**, không làm phần logic nghiệp vụ và không đặt assertion dựa trên số dòng log hoặc tên thread.

## 14. Test bằng JUnit: kiểm tra kết quả thay vì lịch luồng

Ví dụ sau dùng **JUnit Jupiter** và cần thêm dependency tương ứng vào dự án kiểm thử; phần Java Stream không phụ thuộc JUnit.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ParallelPipelineTest {

    private static List<Integer> squaresOfEven(
            Stream<Integer> stream) {

        return stream.filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .collect(Collectors.toList());
    }

    @Test
    void parallelMatchesSequentialForOrderedResult() {
        List<Integer> input = IntStream.range(0, 10000)
                .boxed()
                .collect(Collectors.toList());

        List<Integer> seq = squaresOfEven(input.stream());
        List<Integer> par = squaresOfEven(input.parallelStream());

        assertEquals(seq, par);
        assertEquals(5000, seq.size());
        assertEquals(Integer.valueOf(0), seq.get(0));
        assertEquals(Integer.valueOf(9998 * 9998), seq.get(4999));
    }
}
```

**Lưu ý kiểm tra giá trị kỳ vọng:** `9998 * 9998` vẫn nằm trong miền `int`, nên biểu thức không bị tràn ở ví dụ này. Khi tăng miền lên giá trị lớn hơn, chuyển phép nhân sang `long` và chọn kiểu List phù hợp.

JUnit `assertEquals` so bằng `List.equals` nên kiểm tra cả thứ tự. Nếu yêu cầu không quan tâm thứ tự, hãy dùng phép chuẩn hóa hoặc so theo đa tập, không áp đặt thứ tự chỉ vì framework trả List.

### Test nhiều bộ dữ liệu có seed cố định

```java
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GroupingPropertyTest {

    private static Map<Integer, Long> histogram(
            java.util.stream.Stream<Integer> stream) {

        return stream.collect(Collectors.groupingBy(
                value -> Math.floorDiv(value, 10),
                Collectors.counting()
        ));
    }

    @Test
    void groupedCountsMatchAcrossGeneratedInputs() {
        for (int seed = 0; seed < 40; seed++) {
            Random random = new Random(seed);

            List<Integer> values = random
                    .ints(2000, -100, 101)
                    .boxed()
                    .collect(Collectors.toList());

            Map<Integer, Long> seq =
                    histogram(values.stream());

            Map<Integer, Long> par =
                    histogram(values.parallelStream());

            assertEquals(seq, par, "seed=" + seed);
            assertEquals(2000L,
                    seq.values().stream()
                            .mapToLong(Long::longValue)
                            .sum());
        }
    }
}
```

Việc dùng seed cố định giúp tái hiện ca lỗi. `Random.ints` ở đoạn này được tiêu thụ **tuần tự trước khi** chạy hai phiên bản pipeline trên cùng List đã tạo. Không chia sẻ một Random mutable trong `parallel().map(...)` rồi hy vọng từng phần tử có cùng số random ở cả hai chế độ.

40 bộ dữ liệu có thể tìm thấy lỗi phụ thuộc dữ liệu, nhưng **không thể chứng minh** mọi interleaving an toàn. Nếu xuất hiện race hiếm, cần phân tích trạng thái chia sẻ và công cụ kiểm thử concurrency phù hợp, không chỉ tăng số vòng lặp.

## 15. Kiểm tra nhiều kích thước và cách phân hoạch

Một combiner sai có thể không lộ ở bộ dữ liệu quá nhỏ, do framework không chia nhánh như mong đợi. Hãy thử:

| Dữ liệu | Lỗi có thể phát hiện |
| --- | --- |
| Nguồn rỗng | Identity, Optional, collector không có phần tử |
| Một phần tử | Khởi tạo, finisher, trường hợp không cần combiner |
| Hai phần tử | Đầu tiên/cuối cùng, gộp hai trạng thái |
| Số lượng lẻ | Bỏ sót phần tử cuối hoặc nhóm không đủ |
| Nhiều giá trị trùng | `distinct`, đếm theo nhóm, merge khi trùng khóa |
| Giá trị âm, 0 và số cực lớn | Identity sai, overflow, floorDiv |
| Dữ liệu có null nếu được phép | Null handling trong mapper/classifier |
| Danh sách ordered và nguồn unordered | Các yêu cầu encounter order khác nhau |
| 10, 100, 1000, 100000 phần tử | Nhiều cách chia nhánh và chi phí bộ nhớ |
| Nhiều lần chạy parallel | Tái hiện race không ổn định |

Đối với một phép tổng hợp đúng, nên kiểm tra thêm **tính độc lập với cách phân nhóm**. Ví dụ cộng số:

```text
((a + b) + c) == (a + (b + c))
```

Với số nguyên không tràn, phép cộng đáp ứng tính kết hợp. Với phép nối chuỗi, thứ tự toán hạng thường quan trọng nhưng phép ghép có thể kết hợp nếu giữ đúng thứ tự; với trừ hoặc chia, phép toán nói chung không kết hợp.

### Thay đổi số luồng không phải oracle

Đừng viết test phụ thuộc vào `ForkJoinPool.commonPool().getParallelism()` hoặc yêu cầu các thread cụ thể xuất hiện. Số luồng, cách tách `Spliterator` và lịch thực thi thuộc môi trường và implementation; chúng có thể thay đổi theo JDK hoặc máy chạy.

Một test đúng nên khẳng định **ngữ nghĩa kết quả** và hợp đồng an toàn, không ràng buộc vào sơ đồ luồng nội bộ.

## 16. Đối chiếu với nguồn I/O: mở hai lượt riêng

Với `Files.lines`, mỗi lần tạo Stream thường giữ tài nguyên cần đóng. Không được tiêu thụ một Stream hai lần.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> countLogLevels(
        Path path, boolean parallel) throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        Stream<String> mode =
                parallel ? lines.parallel() : lines.sequential();

        return mode
                .filter(line -> line.contains(":"))
                .map(line -> line.substring(
                        0, line.indexOf(':')))
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        Collectors.counting()
                ));
    }
}
```

Đối chiếu:

```java
Map<String, Long> sequential = countLogLevels(path, false);
Map<String, Long> parallel = countLogLevels(path, true);

if (!sequential.equals(parallel)) {
    throw new AssertionError("Log counts differ");
}
```

Hai lời gọi **mở hai Stream riêng** và đóng chúng bằng `try-with-resources`. Đây là phép so có ý nghĩa chỉ khi tệp **không bị thay đổi** giữa hai lượt. Trong test tự động, nên tạo fixture cố định; trong hệ thống đang ghi log, hãy dùng snapshot hoặc dữ liệu bất biến trước khi so sánh.

`Files.lines` có thể ném `IOException` lúc mở và `UncheckedIOException` lúc tiêu thụ dữ liệu lazy. Đừng bắt mọi ngoại lệ rồi thay bằng Map rỗng: như vậy có thể làm hai nhánh “bằng nhau” dù cả hai đều thất bại khi đọc.

Khi dùng `BufferedReader.lines()`, phải đóng Reader ở nơi sở hữu nó. `collect`/`count`/`findFirst` không tự đóng nguồn I/O. Bật parallel không miễn trừ trách nhiệm vòng đời này.

## 17. Performance test khác correctness test

So sánh thời gian chạy không trả lời câu hỏi “hai kết quả có cùng nghĩa không”. Để đánh giá parallel:

1. **Chứng minh đúng:** so với oracle/kết quả kỳ vọng và so ngữ nghĩa sequential–parallel.
2. **Cố định dữ liệu:** cùng kích thước, phân bố giá trị, nguồn và điều kiện.
3. **Tách hiệu ứng I/O:** benchmark đọc tệp khác với benchmark xử lý dữ liệu trong bộ nhớ.
4. **Warm-up và lặp lại:** JIT, GC và scheduling làm một lần đo không đại diện.
5. **Đo memory/throughput/latency:** song song có thể tăng throughput nhưng làm tăng bộ đệm, cấp phát và phối hợp.
6. **Không dùng `System.out.println` trong pipeline đang đo:** log đồng bộ có thể chi phối toàn bộ thời gian.
7. **Đánh giá theo môi trường:** CPU, JDK, cấu trúc nguồn, số nhóm và tính chất Collector ảnh hưởng kết quả.

Ví dụ `parallel().sorted().collect(toList())` có thể tốn nhiều bộ nhớ và chi phí phối hợp; một phép `map` rẻ trên vài trăm phần tử thường không có lợi khi chia nhánh.

Đối với Java, có thể dùng framework benchmark chuyên dụng như JMH trong giai đoạn đo hiệu năng. Nhưng **không cần benchmark** mới có thể kiểm tra tính đúng đắn của một pipeline; hai hoạt động có mục tiêu riêng.

## 18. Quy trình chẩn đoán khi phát hiện sai khác

```text
Phát hiện sequential != parallel
               |
               v
  Hai lượt có thật sự cùng dữ liệu?
       | Không -> cố định snapshot / input
       v Có
  Hợp đồng có cho phép khác thứ tự?
       | Có -> so Set/Map/đa tập/điều kiện nghiệm
       v Không hoặc vẫn sai
  Có state mutable dùng chung/side effect?
       | Có -> bỏ side effect, dùng collector đúng
       v Không
  Reduce/combiner có identity và associative?
       | Không -> sửa phép tổng hợp
       v Có
  Có double/NaN/overflow/parse lỗi?
       | Có -> kiểm tra oracle số học & tolerance
       v Không
  Có unordered/short-circuit/source lifecycle?
       | Có -> sửa test theo hợp đồng
       v Không
  Thu nhỏ input + seed cố định + nhiều lần parallel
               |
               v
  Báo lỗi có fixture, kỳ vọng, kết quả, JDK
```

Một báo cáo bug hữu ích nên kèm: input tối giản, quy tắc kết quả kỳ vọng, code pipeline, chế độ sequential/parallel, seed nếu có, kiểu Collector, môi trường JDK, và chính xác lỗi là **giá trị sai**, **thiếu phần tử**, **sai thứ tự**, **exception** hay **không hoàn tất**.

Đừng gắn nhãn “bug của Java parallel stream” trước khi xác minh hợp đồng của accumulator, comparator, source và các lambda đã được tuân thủ.

## 19. Bài tập thực hành

### Bài tập A: đối chiếu ordered List

Tạo các số từ 0 tới 999, lấy số chẵn, bình phương trên `long`, thu về List. So kết quả tuần tự và song song theo thứ tự, sau đó cố ý thay `collect(toList())` bằng `forEach` ghi vào List dùng chung và giải thích vì sao phiên bản sau không hợp lệ.

**Tiêu chí:** List so bằng `equals`; số phần tử chính xác; không có shared mutable state trong pipeline đúng.

### Bài tập B: kiểm tra grouping có khóa trùng

Từ các chuỗi:

```text
ERROR WARN INFO ERROR ERROR WARN
```

Tạo `Map<String,Long>` bằng `groupingBy(..., counting())` và so với `groupingByConcurrent(..., counting())`. Xác minh `ERROR=3`, `WARN=2`, `INFO=1`; không so theo thứ tự in Map.

### Bài tập C: tạo một test thất bại có chủ đích

Dùng:

```java
Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, (a, b) -> a - b);
```

So với phiên bản tuần tự. Giải thích bằng tính không kết hợp của phép trừ. Sau đó đổi sang `Integer::sum` với identity 0 và kiểm tra bằng tổng kỳ vọng 10.

### Bài tập D: kiểm tra hàm chọn phần tử

Dùng nguồn `[5,8,11,14,17]` và predicate số chẵn. Test `findFirst` phải trả 8 trong cả hai chế độ; test `findAny` chỉ đòi kết quả thuộc `{8,14}`. Thử nguồn không có số chẵn và xác minh `Optional.empty()`.

### Bài tập E: dữ liệu phát sinh có seed cố định

Tạo 50 bộ dữ liệu số nguyên gồm giá trị âm, 0, dương và phần tử trùng. Kiểm tra histogram `value -> Math.floorDiv(value, 10)` bằng `groupingBy(counting())` trong hai chế độ. Thêm một phép kiểm tra độc lập rằng tổng số phần tử trong các bucket bằng độ dài nguồn.

### Bài tập F: thống kê nguồn I/O

Tạo tệp log nhỏ có các dòng `INFO:...`, `WARN:...`, `ERROR:...`. Chạy `countLogLevels(path,false)` và `countLogLevels(path,true)` trên cùng snapshot bất biến. Kiểm tra Map đúng, file được đóng và dữ liệu lỗi được báo rõ.

## 20. Những sai lầm thường gặp

| Sai lầm | Vì sao dẫn đến kết luận sai | Cách sửa |
| --- | --- | --- |
| So `Map.toString()` hoặc `Set.toString()` | Thứ tự lặp không phải hợp đồng kết quả | So `Map.equals`/`Set.equals` |
| Sắp xếp List đầu ra dù nghiệp vụ cần order | Có thể che lỗi mất thứ tự | So `List.equals` trực tiếp |
| Đổi sang Set khi có phần tử lặp | Mất tần suất từng giá trị | So đa tập hoặc danh sách chuẩn hóa có giữ lặp |
| Đòi `findAny` luôn trả cùng giá trị | `findAny` được phép chọn phần tử khác | So điều kiện nghiệm/membership |
| Kiểm tra số lời gọi predicate trong `anyMatch` | Short-circuit không có lịch cố định | Kiểm tra boolean kết quả |
| Thấy log `peek` khác thứ tự rồi báo lỗi | Log xen kẽ, `peek` có thể bị bỏ qua | Kiểm tra output, không kiểm tra log |
| Dùng `parallel().forEach(sharedList::add)` | `ArrayList` không thread-safe | `collect(toList())` |
| Dùng `reduce` với phép trừ | Không associative | Phép gộp hợp lệ hoặc thiết kế khác |
| Identity của `reduce` không phù hợp | Có thể cộng identity nhiều lần khi chia nhánh | Dùng identity đúng |
| Combiner bỏ qua một nhánh | Mất dữ liệu khi parallel | Gộp đủ các accumulator |
| Supplier trả cùng container mutable | Race/đếm trùng khi có nhiều nhánh | Mỗi lần Supplier tạo container mới |
| So `double` bằng từng bit trong mọi trường hợp | Thứ tự làm tròn khác | Tolerance có cơ sở hoặc số học chính xác |
| Hai nhánh trả cùng số nguyên tràn rồi coi là đúng | Cùng lỗi overflow | So với oracle miền số phù hợp |
| Chạy tuần tự rồi song song trên cùng Stream | Stream đã bị tiêu thụ | Tạo nguồn Stream mới |
| Đọc cùng tệp log đang bị ghi cho hai lượt so | Hai nguồn dữ liệu không giống nhau | Snapshot/fixture bất biến |
| Bật `unordered()` để “tăng tốc” rồi vẫn yêu cầu limit đầu | Hợp đồng thứ tự đã bị bỏ | Giữ order nếu nghiệp vụ cần |
| Dùng một lần chạy parallel làm bằng chứng thread-safe | Race có thể hiếm | Phân tích hợp đồng, test nhiều cách phân hoạch |
| So benchmark trước khi xác minh correctness | Nhanh nhưng có thể sai | Kiểm tra kết quả trước, đo hiệu năng sau |
| Quên đóng `Files.lines` | Rò rỉ tài nguyên I/O | `try-with-resources` |

## 21. Checklist trước khi chấp nhận một parallel pipeline

1. Nguồn dữ liệu của hai lần đối chiếu có **giống nhau** và không bị sửa trong lúc duyệt không?
2. Các hàm `filter`, `map`, classifier và comparator có **stateless, non-interfering** không?
3. Có dùng một `ArrayList`/`HashMap`/counter mutable bên ngoài được nhiều luồng sửa không?
4. `reduce` có identity, accumulator, combiner và associativity đúng không?
5. `collect` có Supplier trả container mới, combiner gộp đủ dữ liệu và characteristics đúng không?
6. Output là ordered List, Set, Map, đa tập, một cực trị hay số thực? **Phép so sánh đã đúng kiểu ngữ nghĩa chưa?**
7. Với `findAny`, `limit`, `unordered()`, ta có đang áp đặt yêu cầu thứ tự không được cam kết không?
8. Có xử lý nguồn rỗng, một phần tử, khóa trùng, null, giá trị âm, overflow, `NaN`/vô cực khi cần không?
9. Test có một **oracle kỳ vọng độc lập**, hay chỉ so hai kết quả có thể cùng sai?
10. Đã thử các kích thước và seed tái lập khác nhau, không phụ thuộc tên thread hay lịch thực thi chưa?
11. Nếu nguồn là I/O, đã tạo hai lượt nguồn hợp lệ và đóng tài nguyên đúng chưa?
12. Sau khi correctness đạt, có số đo thực nghiệm chứng minh parallel giúp bài toán thực tế không?

## 22. Câu hỏi tự kiểm tra

1. Hai Stream có thể dùng lại cùng một instance sau terminal operation không? **Không**, phải tạo Stream mới.
2. Với `List` ordered và `Collectors.toList()`, ta nên so gì? **Số phần tử, giá trị và thứ tự**, ví dụ bằng `List.equals`.
3. Với `Set`, hai lần in khác thứ tự có phải bug không? **Không**, hãy so phần tử theo `Set.equals`.
4. Khi Map chỉ chứa `Long` đếm theo khóa, so Map thế nào? **`Map.equals`**, không dựa vào thứ tự in.
5. Nếu Map chứa danh sách unordered có phần tử lặp, dùng `Set` để chuẩn hóa có đúng không? **Không**, sẽ làm mất tần suất; dùng đa tập hoặc bản sao được sắp xếp.
6. `findFirst` trên nguồn ordered có giữ ý nghĩa phần tử đầu khi parallel không? **Có**, theo encounter order.
7. `findAny` có buộc trả giống `findFirst` không? **Không**.
8. Vì sao không nên assert số lần predicate được gọi ở `anyMatch`? **Do short-circuit và chia nhánh có thể khác nhau**.
9. Tại sao `parallel().forEach(arrayList::add)` nguy hiểm? **Nhiều luồng sửa một List không thread-safe**.
10. `Collectors.toList()` có thể dùng trên parallel stream dù `ArrayList` không thread-safe không? **Có**, collector xử lý bộ chứa theo hợp đồng.
11. Phép trừ có thích hợp làm combiner của reduction song song không? **Không**, vì không associative.
12. Identity của phép cộng phải là gì? **0**, không phải giá trị tùy ý như 10.
13. Combiner chỉ trả nhánh trái có gì sai? **Có thể làm mất dữ liệu nhánh phải**.
14. Tại sao hai tổng `double` có thể khác một chút? **Do thay thứ tự gom và sai số làm tròn**.
15. Tại sao `seq == parallel` chưa đủ chứng minh kết quả số nguyên đúng? **Cả hai có thể cùng overflow**.
16. Khi nào nên dùng `BigDecimal` thay `double`? **Khi yêu cầu kết quả thập phân chính xác theo quy tắc nghiệp vụ**.
17. `peek` có phải phép kiểm tra số lần xử lý phần tử đáng tin cậy không? **Không**, pipeline có thể tối ưu bỏ lời gọi.
18. Test dựa vào thread name hoặc số luồng có ổn định qua JDK không? **Không**.
19. Với nguồn `Files.lines`, phải làm gì khi chạy hai cách xử lý? **Mở hai Stream riêng, đọc cùng snapshot và đóng từng nguồn**.
20. Correctness test và performance test có cùng mục tiêu không? **Không**; kiểm tra đúng đắn trước khi đo tốc độ.
21. Nên làm gì với bug chỉ xuất hiện khi parallel? **Cố định input/seed, thu nhỏ ví dụ, kiểm tra state/combiner/order và lưu fixture tái hiện**.
22. Bằng chứng quan trọng nhất khi so kết quả là gì? **Hợp đồng ngữ nghĩa đầu ra cộng với một oracle kỳ vọng độc lập**.

**Nguyên tắc áp dụng:** Đối chiếu tuần tự và song song không phải là so hai dòng log hay hai chuỗi `toString()`. Hãy **cố định dữ liệu**, dùng **hai Stream mới**, xác định **ngữ nghĩa kết quả**, và kiểm tra từng yếu tố quyết định tính đúng: lambda thuần, trạng thái không chia sẻ, identity/associativity/combiner hợp lệ, yêu cầu thứ tự, floating point, overflow và vòng đời nguồn I/O. Khi sequential và parallel có kết quả tương đương **theo đúng hợp đồng**, vẫn cần oracle độc lập để tránh trường hợp cả hai cùng sai. Chỉ sau đó mới đánh giá lợi ích hiệu năng của parallel stream.
