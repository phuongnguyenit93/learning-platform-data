# Hiểu mô hình chia nguồn, xử lý và ghép kết quả

## 1. Mục tiêu bài học

Trong module **`JAVA_STREAM_API`**, Stream API cho phép mô tả pipeline khai báo: tạo nguồn, ghép các bước trung gian lazy như `filter`, `map`, `flatMap` và kết thúc bằng `reduce`, `collect` hoặc phép tổng hợp. Với dữ liệu đủ lớn và các thao tác thích hợp, có thể yêu cầu Java xử lý pipeline theo chế độ **song song**.

Tuy nhiên, `parallel()` **không có nghĩa một phần tử được giao cho một thread riêng**, và `parallelStream()` cũng **không bảo đảm nhanh hơn** stream tuần tự. Muốn hiểu ngữ nghĩa và hiệu năng, cần nắm ba giai đoạn khái niệm:

1. **Chia nguồn (split):** phân nguồn thành các phần công việc có thể được xử lý độc lập.
2. **Xử lý (process):** cho mỗi phần tử đi qua những thao tác trong pipeline.
3. **Ghép kết quả (combine):** kết hợp các kết quả cục bộ để hoàn thành terminal operation.

Sau bài này, bạn có thể:

- Giải thích vai trò của `Spliterator.trySplit()` trong quá trình chia dữ liệu.
- Phân biệt phần công việc, thread thực thi và thứ tự gặp (*encounter order*).
- Đọc cơ chế giảm dữ liệu bằng `reduce`, tích lũy bằng `collect` và ghép kết quả.
- Hiểu tại sao `identity`, tính kết hợp (*associativity*) và `combiner` quyết định tính đúng khi chạy song song.
- Nhận diện lỗi do tác dụng phụ, trạng thái chia sẻ hoặc giả định sai về thứ tự.
- Kiểm tra kết quả trước, sau đó mới cân nhắc đo hiệu năng.

Bài thuộc chương **Ngữ nghĩa xử lý song song**, làm nền tảng cho nội dung về `Spliterator`, collector tùy chỉnh, grouping, tính trạng thái và giới hạn tài nguyên.

## 2. Hình dung ba giai đoạn trên một pipeline

Xét phép tính tổng bình phương của tám số:

```java
import java.util.stream.LongStream;

public class ViDuTongBinhPhuong {
    public static void main(String[] args) {
        long tong = LongStream.rangeClosed(1, 8)
            .parallel()
            .map(n -> n * n)
            .sum();

        System.out.println(tong); // 204
    }
}
```

Về mặt toán học:

```text
1² + 2² + 3² + 4² + 5² + 6² + 7² + 8² = 204
```

Một cách phân chia **có thể hình dung**:

```text
                Nguồn: 1 2 3 4 5 6 7 8
                           |
                        SPLIT
                ___________|___________
               /                       \
           1 2 3 4                   5 6 7 8
          /       \                 /       \
         1 2      3 4             5 6      7 8
          |        |               |        |
       map, sum  map, sum        map, sum  map, sum
          |        |               |        |
          5       25              61      113
           \      /                \       /
              30                      174
                \                    /
                 COMBINE (phép cộng)
                         |
                        204
```

**Sơ đồ không cam kết** JVM luôn chia đúng bốn nhánh, theo ranh giới đó hoặc chỉ dùng bốn thread. Nguồn và runtime quyết định khả năng chia, kích thước công việc, lịch xử lý và cách ghép. Ngữ nghĩa của phép tính vẫn phải đúng khi các hàm trong pipeline thỏa hợp đồng Stream.

Không phải mọi phần tử đều có một tác vụ riêng. Việc tạo quá nhiều tác vụ nhỏ có thể tốn chi phí hơn tính toán thực tế, nên parallel stream thường xử lý **lô phần tử** trong từng phần công việc.

## 3. Bật chế độ song song và khi nào pipeline thực sự chạy

Có hai cách thường gặp:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

List<Integer> so = Arrays.asList(1, 2, 3, 4, 5);

Stream<Integer> a = so.parallelStream();
Stream<Integer> b = so.stream().parallel();

System.out.println(a.isParallel()); // true
System.out.println(b.isParallel()); // true
```

`parallel()` là một thao tác **trung gian** cấu hình chế độ chạy. Nó không tự tiêu thụ dữ liệu: quá trình xử lý chỉ bắt đầu khi terminal operation như `sum`, `reduce`, `count`, `collect` hay `forEach` cần kết quả.

```java
long tong = so.stream()
    .mapToLong(Integer::longValue)
    .parallel()
    .sum();

System.out.println(tong); // 15
```

`sequential()` đưa pipeline trở lại chế độ tuần tự:

```java
long tongTuanTu = so.stream()
    .parallel()
    .mapToLong(Integer::longValue)
    .sequential()
    .sum();

System.out.println(tongTuanTu); // 15
```

Không nên hiểu đoạn trên như "phần trước `sequential()` chạy song song, phần sau chạy tuần tự". Với pipeline Stream thông thường, chế độ tuần tự/song song được thiết lập cho **toàn pipeline khi terminal operation thực thi**, không phải cho từng stage độc lập.

Một stream **chỉ được tiêu thụ một lần**. Muốn so sánh kết quả tuần tự và song song, tạo hai stream mới từ cùng nguồn; không gọi terminal operation lần thứ hai trên stream đã được sử dụng.

## 4. Giai đoạn chia nguồn: `Spliterator`

### 4.1. Vai trò của `Spliterator`

`Spliterator<T>` cung cấp cơ chế tiêu thụ và **thử chia** nguồn. Những phương thức quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `tryAdvance(Consumer<? super T>)` | Cấp một phần tử tiếp theo cho consumer nếu còn. |
| `forEachRemaining(Consumer<? super T>)` | Tiêu thụ toàn bộ phần còn lại. |
| `trySplit()` | Thử tách một phần dữ liệu ra spliterator khác; có thể trả `null`. |
| `estimateSize()` | Cho biết số phần tử ước tính còn lại. |
| `characteristics()` | Mô tả các thuộc tính như `ORDERED`, `SIZED`, `SUBSIZED`. |

Ví dụ mô hình:

```text
Spliterator ban đầu: [A, B, C, D, E, F]
                      trySplit()
                      /        \
   Spliterator mới [A,B,C]    Phần còn lại [D,E,F]
```

Với một nguồn có thứ tự, phần tách ra của `trySplit` phải tương ứng một **tiền tố** của những phần tử chưa duyệt, nhưng cách chia và kích thước từng phần phụ thuộc nguồn. Không phải mọi nguồn đều chia đều; có nguồn trả `null` vì không thể chia hoặc chia không có lợi.

Đặc tính thường gặp:

- **`ORDERED`:** nguồn có encounter order xác định.
- **`SIZED`:** biết chính xác kích thước phần dữ liệu còn lại theo hợp đồng.
- **`SUBSIZED`:** những spliterator con tạo khi tách cũng có kích thước chính xác.
- **`SORTED` / `DISTINCT`:** nguồn đã thỏa các tính chất có thể giúp tối ưu một số bước.

Những đặc tính này là **hợp đồng**, không phải gợi ý tùy tiện. Khi viết spliterator riêng, khai báo sai `SIZED`, `SUBSIZED` hoặc `ORDERED` có thể dẫn đến lỗi nghiêm trọng khi pipeline dùng tối ưu hóa.

### 4.2. Quan sát một lần gọi `trySplit`

Ví dụ Java 8+ tự chứa:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;

public class ThuTrySplit {
    public static void main(String[] args) {
        List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8);

        Spliterator<Integer> conLai = nguon.spliterator();
        Spliterator<Integer> tachRa = conLai.trySplit();

        List<Integer> a = new ArrayList<>();
        List<Integer> b = new ArrayList<>();

        if (tachRa != null) {
            tachRa.forEachRemaining(a::add);
        }
        conLai.forEachRemaining(b::add);

        List<Integer> ghep = new ArrayList<>(a);
        ghep.addAll(b);

        System.out.println("Tách ra: " + a);
        System.out.println("Còn lại: " + b);
        System.out.println(ghep.equals(nguon)); // true
    }
}
```

Với nguồn `List` có thứ tự như trên, phần tách ra là tiền tố và phần còn lại là hậu tố. Chương trình không bắt buộc giả định kích thước `a` và `b` bằng nhau. **Gọi trực tiếp `trySplit` không tạo thread**: nó chỉ chia đối tượng đại diện dữ liệu.

### 4.3. Không phải nguồn nào cũng chia hiệu quả

| Nguồn | Đặc điểm chia nguồn | Hệ quả |
| --- | --- | --- |
| Mảng, `ArrayList`, `IntStream.range` | Thường chia thành các đoạn nhanh, cân bằng | Thường thuận lợi nếu xử lý CPU-bound đủ lớn. |
| `LinkedList` | Không có truy cập chỉ số nhanh như mảng | Việc chia có thể đòi hỏi gom theo lô; cần đo. |
| `Stream.iterate` | Phần tử kế tiếp có thể phụ thuộc phần tử trước | Khó tận dụng chia độc lập trong một số trường hợp. |
| `BufferedReader.lines()` | Nguồn I/O đọc tuần tự | Song song không tự làm việc đọc tệp hiệu quả. |
| `Files.walk` / `Files.find` | Duyệt cây và truy cập I/O, có trạng thái | Giới hạn tài nguyên và cách chia khác nguồn trong bộ nhớ. |
| Spliterator tùy chỉnh | Phụ thuộc trực tiếp vào `trySplit` | Phải bảo đảm không mất hoặc lặp phần tử. |

Nguồn có thể chia thành hai vùng có số phần tử gần bằng nhau nhưng **chi phí mỗi phần tử khác nhau**. Do đó "chia đều số lượng" chưa đủ để bảo đảm cân bằng tải.

## 5. Giai đoạn xử lý: tác vụ, thread và fork/join

Parallel stream trong những triển khai JDK thông dụng thường dùng cơ chế **fork/join**, với nhiều tác vụ có thể chạy trong `ForkJoinPool.commonPool()`. Đây là mô tả triển khai thường gặp, **không phải lời hứa API** rằng mỗi pipeline luôn dùng một pool, một số thread hoặc tên thread cố định.

Trong fork/join, một tác vụ có thể tiếp tục chia công việc thành các tác vụ con; những worker khác có thể lấy việc còn lại (*work stealing*). Không có bảo đảm mỗi phần tử hoặc mỗi nhánh sơ đồ được xử lý bởi một thread riêng.

### 5.1. `map` và `filter` giữ ngữ nghĩa dữ liệu

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> ketQua = nguon.parallelStream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * n)
    .collect(Collectors.toList());

System.out.println(ketQua); // [4, 16, 36]
```

Trên một `List` có thứ tự, `filter` giữ thứ tự tương đối các phần tử còn lại, `map` biến đổi từng giá trị và collector `toList` thu theo encounter order. **Các callback có thể chạy ở thứ tự thời gian khác**, nhưng list kết quả vẫn có thứ tự logic như trên.

Một hàm xử lý phù hợp:

```java
List<Integer> binhPhuong = nguon.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

Nó không sửa nguồn, không cập nhật biến bên ngoài và không dựa vào lần gọi trước. Những hàm **stateless** và **non-interfering** như vậy dễ lý luận khi chia các phần tử cho nhiều tác vụ.

### 5.2. Tải mỗi phần tử có thể khác nhau

Giả sử 100 phần tử đầu rất nhẹ còn 100 phần tử sau cần tính toán nặng. Nếu nguồn chia thành hai nửa bằng số lượng, **thời gian hai nhánh vẫn không cân bằng**. Runtime có thể chia thêm các phần, nhưng không có bảo đảm tự động xóa hết mất cân bằng.

Vì vậy khi đánh giá một nguồn, cần hỏi:

- `trySplit` có tạo phần công việc đủ cân bằng và không quá tốn chi phí không?
- Các phần tử có chi phí xử lý gần nhau không?
- Có lock hoặc tài nguyên chia sẻ làm các tác vụ phải chờ nhau không?
- Công việc chủ yếu giới hạn bởi CPU, bộ nhớ hay I/O?

## 6. Giai đoạn ghép: `reduce`

Song song hóa đúng nghĩa là kết quả từ nhiều nhánh có thể **ghép lại mà không phụ thuộc cách chia**. Ví dụ phép cộng trên những số trong miền an toàn:

```java
import java.util.stream.LongStream;

long tong = LongStream.rangeClosed(1, 1000)
    .parallel()
    .reduce(0L, Long::sum);

System.out.println(tong); // 500500
```

`0L` là **identity** của phép cộng, `Long::sum` là phép kết hợp. Một phép toán `op` với identity `e` cần thỏa:

```text
op(e, x) == x
op(x, e) == x
op(op(a, b), c) == op(a, op(b, c))
```

Tính chất thứ ba gọi là **associativity** (tính kết hợp). Nó cho phép đổi cách đặt ngoặc khi ghép tổng cục bộ.

### 6.1. Vì sao phép trừ không phù hợp?

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Phép trừ không kết hợp, nên ví dụ sau không bảo đảm cùng kết quả logic giữa tuần tự và song song:

```java
List<Integer> so = Arrays.asList(1, 2, 3, 4);

int tuanTu = so.stream()
    .reduce(0, (a, b) -> a - b);

int songSong = so.parallelStream()
    .reduce(0, (a, b) -> a - b);

System.out.println(tuanTu);  // -10
System.out.println(songSong); // Không bảo đảm bằng -10
```

Một lần chạy tình cờ cho giá trị mong muốn không chứng minh phép toán hợp lệ. Lỗi nằm ở **quy tắc đại số**, không nằm ở số lõi CPU.

### 6.2. Identity sai có thể bị áp dụng nhiều lần

```java
// SAI: 10 không phải identity của phép cộng.
int sai = so.parallelStream().reduce(10, Integer::sum);

// ĐÚNG:
int dung = so.parallelStream().reduce(0, Integer::sum);

System.out.println(dung); // 10
```

Trong chế độ tuần tự, thêm identity `10` khiến tổng sai một lần. Trong chế độ song song, giá trị khởi đầu có thể được đưa vào **nhiều phần cục bộ**, nên sai số không có một lượng cố định mà chương trình được phép dựa vào.

### 6.3. Overload ba tham số có accumulator và combiner

Chữ ký:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Ví dụ tính tổng độ dài các chuỗi:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int tong = ten.parallelStream()
    .reduce(0,
        (soKyTu, s) -> soKyTu + s.length(),
        Integer::sum);

System.out.println(tong); // 12
```

Ngoài identity đúng và combiner có tính kết hợp, còn có yêu cầu **tương thích** giữa accumulator và combiner:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

Trong ví dụ: `u + (0 + s.length()) == u + s.length()`. Nếu combiner bị thay thành phép trừ, kết quả ở chế độ song song có thể sai dù phiên bản tuần tự dường như hoạt động.

Chỉ để tính tổng độ dài chuỗi, API chuyên biệt thường gọn hơn:

```java
int tong = ten.parallelStream()
    .mapToInt(String::length)
    .sum();
```

### 6.4. Số thực và tràn số

`double` có sai số dấu phẩy động: `(a + b) + c` có thể khác `a + (b + c)` về bit. Vì vậy, các kết quả `DoubleStream.reduce` có thể khác những chữ số cuối khi thay đổi cách nhóm; khi kiểm thử dữ liệu số thực, hãy xác định dung sai phù hợp. `DoubleStream.sum()` có thể áp dụng thuật toán cộng bù để giảm sai số, nên không nhất thiết có cách đánh giá giống `reduce(0.0, Double::sum)`.

Tổng kiểu `int` hoặc `long` cũng có giới hạn. Dùng kiểu phù hợp và ca kiểm tra chống tràn khi nghiệp vụ yêu cầu chính xác lớn; không dùng kết quả song song "giống tuần tự" làm bằng chứng rằng phép tính không tràn.

## 7. `collect`: vùng tích lũy cục bộ và combiner

`reduce` thường kết hợp **giá trị mới**; `collect` hỗ trợ **mutable reduction** như list, set, map và thống kê theo nhóm.

Ví dụ:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

List<String> ketQua = ten.parallelStream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());

System.out.println(ketQua); // [JAVA, GO, KOTLIN]
```

Một collector có các thành phần khái niệm:

1. **Supplier:** tạo đối tượng tích lũy ban đầu.
2. **Accumulator:** ghi một phần tử vào đối tượng tích lũy.
3. **Combiner:** ghép các đối tượng tích lũy từ nhiều phần việc.
4. **Finisher:** biến đối tượng tích lũy thành kết quả cuối, khi cần.

```text
             [Java, Go]        [Kotlin]
                 |                 |
              supplier          supplier
                 |                 |
              listA=[]          listB=[]
                 |                 |
             accumulate        accumulate
                 |                 |
            [Java, Go]          [Kotlin]
                 \                 /
                    combiner
                       |
               [Java, Go, Kotlin]
```

Sơ đồ minh họa, không khẳng định collector luôn tạo đúng hai list. Runtime có thể phân chia và ghép theo nhiều cách phù hợp hợp đồng.

### 7.1. Đừng tự sửa một `ArrayList` dùng chung

```java
List<Integer> nguon = Arrays.asList(1, 2, 3, 4);
List<Integer> ketQua = new ArrayList<>();

// KHÔNG AN TOÀN: nhiều thread có thể cùng thêm vào ArrayList.
nguon.parallelStream().forEach(ketQua::add);
```

Thay bằng:

```java
List<Integer> ketQua = nguon.parallelStream()
    .collect(Collectors.toList());
```

Collector có thể tổ chức các vùng tích lũy độc lập và ghép chúng. `Collectors.toList()` không cam kết loại list hay khả năng sửa cụ thể. Nếu cần `ArrayList` rõ ràng:

```java
ArrayList<Integer> ketQua = nguon.parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));
```

### 7.2. Nhìn cách hoạt động qua overload của `collect`

```java
long[] tongTrongMang = Arrays.asList(1, 2, 3, 4)
    .parallelStream()
    .collect(
        () -> new long[1],
        (box, n) -> box[0] += n,
        (left, right) -> left[0] += right[0]
    );

System.out.println(tongTrongMang[0]); // 10
```

Supplier tạo một mảng `long[1]` riêng mỗi lần được gọi; accumulator cập nhật mảng của phần việc; combiner ghép tổng từ mảng khác. **Không được** dùng một mảng toàn cục làm supplier cho mọi phần việc. Đây là ví dụ để hiểu cơ chế; khi chỉ cần tính tổng, `mapToLong(Integer::longValue).sum()` đơn giản hơn.

## 8. Ghép nhóm với `groupingBy`

`groupingBy` có thể tạo các bản đồ nhóm cục bộ rồi ghép theo khóa. Khi có nhiều nhóm, chi phí ghép các map và danh sách có thể đáng kể.

```java
List<String> tu = Arrays.asList(
    "Java", "Go", "Kotlin", "Ruby", "C", "Python"
);

Map<Integer, List<String>> theoDoDai = tu.parallelStream()
    .collect(Collectors.groupingBy(String::length));

System.out.println(theoDoDai.get(4)); // [Java, Ruby]
```

Nếu chỉ cần đếm:

```java
Map<Integer, Long> dem = tu.parallelStream()
    .collect(Collectors.groupingBy(
        String::length, Collectors.counting()));

System.out.println(dem.get(4)); // 2
```

`groupingByConcurrent` có thể cho phép các tác vụ tích lũy vào một `ConcurrentMap` phù hợp trong những điều kiện nhất định. Collector này có đặc tính **concurrent** và **unordered**, nên không được kỳ vọng giữ encounter order của các phần tử trong mỗi nhóm:

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<Integer, Long> demConcurrent = tu.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        String::length, Collectors.counting()));
```

Không chọn `groupingByConcurrent` chỉ vì tên có chữ "Concurrent". Cần xét yêu cầu thứ tự, độ lệch phân phối nhóm, chi phí tranh chấp, bộ nhớ và đo hiệu năng thật.

## 9. Encounter order không phải thứ tự thực thi

| Loại thứ tự | Nghĩa | Điều được bảo đảm |
| --- | --- | --- |
| **Encounter order** | Thứ tự logic do nguồn và pipeline xác định | Có với ordered stream như `List.stream()`, `IntStream.range` nếu chưa bỏ ràng buộc. |
| **Execution order** | Khi nào, trên thread nào callback được gọi | Không cam kết trên parallel stream. |
| **Result order** | Thứ tự do terminal operation/collector trả ra | Phụ thuộc nguồn và ngữ nghĩa phép kết thúc. |

Ví dụ:

```java
List<Integer> so = Arrays.asList(1, 2, 3, 4, 5);

List<Integer> ketQua = so.parallelStream()
    .map(n -> n * 10)
    .collect(Collectors.toList());

System.out.println(ketQua); // [10, 20, 30, 40, 50]
```

List kết quả theo encounter order, nhưng các lệnh `map` không nhất thiết được gọi đúng 1, 2, 3, 4, 5 theo thời gian.

### `forEach` khác `forEachOrdered`

```java
so.parallelStream().forEach(System.out::println);
```

Không bảo đảm in 1 đến 5 theo thứ tự. Khi thật sự cần thực hiện hành động cuối theo thứ tự gặp:

```java
so.parallelStream().forEachOrdered(System.out::println);
```

Trên nguồn `List`, `forEachOrdered` in 1, 2, 3, 4, 5; yêu cầu này có thể hạn chế lợi ích song song. Khi mục tiêu là thu danh sách, `collect` rõ hơn việc tự ghi vào list bên ngoài.

### `findFirst` khác `findAny`

```java
int first = so.parallelStream()
    .filter(n -> n > 2)
    .findFirst()
    .orElse(-1); // 3

int any = so.parallelStream()
    .filter(n -> n > 2)
    .findAny()
    .orElse(-1); // Có thể là 3, 4 hoặc 5
```

`findFirst` tôn trọng vị trí đầu tiên trong encounter order. `findAny` chấp nhận bất kỳ phần tử phù hợp, nên không viết test cứng rằng nó luôn trả 3.

`unordered()` không bắt buộc xáo trộn; nó chỉ **bỏ yêu cầu bảo toàn thứ tự** cho những bước có thể tận dụng điều đó. Khi cần đúng N phần tử đầu hoặc phần tử đầu tiên, không tự ý thêm `unordered()`.


## 10. Stateful operations và short-circuit trong song song

Không phải mọi bước trung gian đều độc lập từng phần tử:

| Phép toán | Đặc điểm | Ảnh hưởng có thể gặp khi chạy song song |
| --- | --- | --- |
| `map` | Thường stateless nếu mapper thuần | Dễ xử lý riêng từng phần. |
| `filter` | Thường stateless nếu predicate thuần | Dễ xử lý riêng, nhưng số lượng kết quả chưa chắc biết trước. |
| `sorted` | Stateful, cần thông tin của nhiều phần tử | Có thể phải giữ dữ liệu và phối hợp để sắp xếp. |
| `distinct` | Stateful vì cần loại trùng | Giữ phần tử xuất hiện đầu trên ordered stream có thể tốn phối hợp. |
| `limit(n)` / `skip(n)` | Phụ thuộc vị trí phần tử nếu nguồn ordered | Có thể cần phối hợp để xác định đoạn đầu/bỏ qua. |
| `takeWhile` / `dropWhile` (Java 9+) | Phụ thuộc đoạn đầu liên tục thỏa điều kiện | Ràng buộc thứ tự có thể giảm hiệu quả song song. |
| `findFirst` | Short-circuit và tôn trọng phần tử đầu nếu ordered | Có thể phải đồng bộ thông tin giữa các nhánh. |
| `findAny` / `anyMatch` | Short-circuit | Có thể dừng sớm mà không cần xét toàn bộ nguồn. |

### 10.1. `limit` trên nguồn ordered

```java
import java.util.stream.IntStream;

List<Integer> dauTien = IntStream.range(0, 1000)
    .parallel()
    .limit(5)
    .boxed()
    .collect(Collectors.toList());

System.out.println(dauTien); // [0, 1, 2, 3, 4]
```

Với nguồn `IntStream.range` có thứ tự, `limit(5)` phải chọn năm phần tử **đầu tiên theo thứ tự logic**, không phải năm phần tử mà thread nào đó hoàn thành sớm. Việc duy trì yêu cầu này có thể phát sinh chi phí phối hợp.

`sorted().limit(5)` và `limit(5).sorted()` cũng có ngữ nghĩa khác nhau: cách thứ nhất tìm năm giá trị nhỏ nhất của toàn nguồn; cách thứ hai chỉ sắp xếp năm phần tử gặp đầu.

### 10.2. Short-circuit không hứa số lần gọi lambda

```java
boolean coSoChan = IntStream.range(1, 1000)
    .parallel()
    .anyMatch(n -> n % 2 == 0);

System.out.println(coSoChan); // true
```

`anyMatch` có thể xác định kết quả trước khi duyệt toàn bộ nguồn. Nhưng một số phần việc khác có thể đã bắt đầu, đang chạy hoặc đang ngừng; **không thể suy ra predicate được gọi đúng hai lần** chỉ vì phần tử chẵn đầu tiên theo encounter order là 2.

Do đó không dùng lambda kiểm tra để kích hoạt các hành động nghiệp vụ cần chạy đủ một lần cho từng phần tử.

## 11. Tác dụng phụ và trạng thái dùng chung

Các hàm hành vi trong pipeline nên **non-interfering** (không sửa nguồn đang xử lý) và trong phần lớn trường hợp **stateless** (kết quả không phụ thuộc một biến đang thay đổi qua các lần gọi).

Ví dụ **không an toàn**:

```java
List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5);
List<Integer> dich = new ArrayList<>();

// KHÔNG NÊN: nhiều thread có thể cùng sửa dich.
nguon.parallelStream()
    .map(n -> {
        dich.add(n);
        return n * n;
    })
    .count();
```

Có hai vấn đề:

1. `ArrayList` dùng chung không an toàn trước các thao tác ghi đồng thời.
2. `count()` có thể trả ngay kích thước nguồn mà **không đánh giá `map`**, vì `map` không làm thay đổi số lượng phần tử. Vì vậy `dich.add(n)` thậm chí có thể **không chạy**.

Cách đúng nếu muốn danh sách bình phương:

```java
List<Integer> binhPhuong = nguon.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());

System.out.println(binhPhuong); // [1, 4, 9, 16, 25]
```

### 11.1. `AtomicInteger` không tự bảo đảm đúng ngữ nghĩa

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

List<Integer> ketQua = nguon.parallelStream()
    .map(n -> n + counter.incrementAndGet())
    .collect(Collectors.toList());
```

`AtomicInteger` giúp cập nhật bộ đếm một cách nguyên tử. Nhưng số thứ tự được gán cho từng phần tử vẫn phụ thuộc **lịch thực thi của các thread**, không còn là hàm thuần của `n`. Khi yêu cầu là xử lý theo **vị trí trong List**, có thể dùng chỉ số rõ ràng:

```java
List<Integer> theoViTri = IntStream.range(0, nguon.size())
    .parallel()
    .mapToObj(i -> nguon.get(i) + i)
    .collect(Collectors.toList());
```

Mẫu này giả định nguồn `List` không bị sửa và truy cập chỉ số phù hợp, ví dụ `ArrayList`. Với `LinkedList`, truy cập theo chỉ số nhiều lần có thể tốn kém.

### 11.2. Không dùng một mutable identity trong `reduce`

```java
// KHÔNG NÊN: identity là đối tượng ArrayList có thể sửa tại chỗ.
List<Integer> sai = nguon.parallelStream()
    .reduce(
        new ArrayList<Integer>(),
        (list, n) -> {
            list.add(n);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

`reduce` đòi hỏi identity và phép gộp thỏa các luật đại số; việc thay đổi tại chỗ một đối tượng identity có thể khiến nhiều phần việc chia sẻ tham chiếu, nhân đôi kết quả hoặc tạo race condition. Nếu mục tiêu là tạo một collection, dùng `collect` với supplier thích hợp.

### 11.3. Không sửa nguồn khi đang duyệt

```java
List<Integer> so = new ArrayList<>(
    Arrays.asList(1, 2, 3, 4));

// KHÔNG NÊN:
// so.parallelStream().forEach(so::remove);
```

Duyệt và thay đổi nguồn cùng lúc vi phạm giả định không can thiệp (*non-interference*), có thể gây lỗi hoặc kết quả sai. Thay vào đó, tạo collection mới:

```java
List<Integer> soLe = so.parallelStream()
    .filter(n -> n % 2 != 0)
    .collect(Collectors.toList());

System.out.println(soLe); // [1, 3]
```

## 12. Chi phí và giới hạn của parallel stream

Parallel stream phải trả chi phí cho:

1. Chia nguồn và tổ chức các phần công việc.
2. Lập lịch, chuyển việc và phối hợp các worker.
3. Thu hoặc ghép kết quả từ các phần.
4. Duy trì encounter order nếu phép toán yêu cầu.
5. Cấp phát bộ nhớ trung gian và sử dụng cache/băng thông bộ nhớ.

Song song đáng cân nhắc khi:

- **Nguồn đủ lớn**, có khả năng chia tốt như mảng, `ArrayList` hoặc `IntStream.range`.
- **Mỗi phần tử cần lượng tính toán CPU tương đối đáng kể**.
- Các hàm xử lý độc lập, stateless và không tranh chấp trạng thái dùng chung.
- Terminal operation có `combiner` hợp lệ, chi phí ghép không quá lớn.
- CPU có tài nguyên khả dụng, không bận xử lý tác vụ khác.

Song song có thể **chậm hơn** khi:

- Dữ liệu chỉ vài chục hoặc vài trăm phần tử đơn giản.
- Nguồn khó chia hoặc các phần việc chênh lệch đáng kể.
- Nhiều bước có trạng thái như `sorted` hoặc `distinct`.
- Các tác vụ tranh chấp một lock, map hoặc vùng nhớ.
- Công việc chặn I/O như đọc đĩa, gọi HTTP hay chờ cơ sở dữ liệu.
- Giới hạn chính là băng thông bộ nhớ chứ không phải sức tính CPU.

### 12.1. So sánh kết quả không phải benchmark

```java
long tuanTu = java.util.stream.LongStream.rangeClosed(1, 100000)
    .map(n -> n * n)
    .sum();

long songSong = java.util.stream.LongStream.rangeClosed(1, 100000)
    .parallel()
    .map(n -> n * n)
    .sum();

System.out.println(tuanTu == songSong); // true
```

Trong ví dụ này, tổng bình phương vẫn nằm trong miền `long`. Nhưng phép so sánh chỉ cho biết **kết quả giống nhau**, không chứng minh song song nhanh hơn. Một phép đo thời gian đơn lẻ có thể bị ảnh hưởng bởi JIT, GC, hệ điều hành và nhiệt độ CPU.

Khi đo hiệu năng thực tế, nên thiết lập workload đại diện, warm-up phù hợp, tránh tối ưu hóa loại bỏ tính toán và dùng công cụ benchmark như JMH. Không dùng `System.nanoTime()` quanh một lần chạy đơn để quyết định chuyển cả hệ thống sang parallel stream.

### 12.2. Tác vụ chặn I/O và common pool

Với phép toán CPU-bound độc lập, phân chia trên nhiều lõi có thể hữu ích. Nhưng các lambda chờ mạng, chờ đĩa hoặc database có thể khiến worker trong pool bị giữ lâu và ảnh hưởng các tác vụ khác. Không giả định `Files.walk(...).parallel()` tự động làm đọc I/O nhanh hơn.

Trong ứng dụng dịch vụ, cần cân nhắc giới hạn kết nối, timeout, backpressure, khả năng chia nguồn và cơ chế quản lý luồng riêng khi tác vụ blocking chiếm ưu thế. Mô hình điều phối dùng chung không thay thế thiết kế tài nguyên cụ thể.

## 13. Viết `Spliterator` và `Collector` riêng: hai hợp đồng khác nhau

Khi tự viết **Spliterator**, cần trả lời:

- `trySplit` có tạo hai vùng **không trùng, không bỏ sót** không?
- Với `ORDERED`, phần tách ra có giữ vai trò tiền tố không?
- `estimateSize`, `SIZED` và `SUBSIZED` có phản ánh kích thước đúng không?
- Có trạng thái hoặc I/O nào không thể dùng an toàn ở nhiều phần việc không?

Khi viết **Collector**, cần kiểm tra:

- `supplier` có tạo vùng tích lũy mới khi được gọi không?
- `accumulator` có chấp nhận mỗi phần tử và cập nhật đúng vùng tích lũy không?
- `combiner` có ghép hai vùng mà không mất hoặc nhân đôi dữ liệu không?
- `finisher` có trả đúng kết quả cuối không?
- `characteristics` như `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` có phản ánh chính xác khả năng của collector không?

`CONCURRENT` không có nghĩa "được phép đánh dấu để chạy nhanh". Nó đòi hỏi accumulator đủ an toàn khi có thể được gọi đồng thời trên cùng container tích lũy trong những điều kiện phù hợp. `UNORDERED` cũng chỉ nên khai báo khi thứ tự gặp không ảnh hưởng kết quả.

Với nhu cầu phổ biến, ưu tiên collector đã được Java cung cấp (`toList`, `toSet`, `summingLong`, `groupingBy`) hơn là tự viết, trừ khi hợp đồng nghiệp vụ thực sự đòi hỏi.

## 14. Chương trình kiểm chứng ngữ nghĩa hoàn chỉnh (Java 8+)

Đây là chương trình độc lập kiểm chứng kết quả tuần tự và song song trên dữ liệu rỗng, một phần tử và nhiều phần tử; đồng thời xác minh thứ tự và grouping. Nó **không dựa vào tên thread** hay hình thức chia cụ thể, nên dùng để học tính đúng chứ không phải benchmark.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class KiemChungParallelStream {
    static void yeuCau(boolean hopLe, String thongBao) {
        if (!hopLe) {
            throw new AssertionError(thongBao);
        }
    }

    static long tinhTong(List<Integer> nguon, boolean parallel) {
        LongStream stream = nguon.stream()
            .mapToLong(Integer::longValue);

        if (parallel) {
            stream = stream.parallel();
        }

        return stream.reduce(0L, Long::sum);
    }

    public static void main(String[] args) {
        List<List<Integer>> cacCa = Arrays.asList(
            Collections.<Integer>emptyList(),
            Collections.singletonList(7),
            Arrays.asList(1, 2, 3, 4),
            Arrays.asList(-3, 0, 7, -2)
        );

        for (List<Integer> ca : cacCa) {
            long mongDoi = 0L;
            for (int n : ca) {
                mongDoi += n;
            }

            yeuCau(tinhTong(ca, false) == mongDoi,
                "Sai kết quả tuần tự " + ca);
            yeuCau(tinhTong(ca, true) == mongDoi,
                "Sai kết quả song song " + ca);
        }

        List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5, 6);

        List<Integer> daLoc = nguon.parallelStream()
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());

        yeuCau(daLoc.equals(Arrays.asList(4, 16, 36)),
            "Sai kết quả collect có thứ tự");

        List<Integer> dauTien = IntStream.range(0, 100)
            .parallel()
            .limit(5)
            .boxed()
            .collect(Collectors.toList());

        yeuCau(dauTien.equals(Arrays.asList(0, 1, 2, 3, 4)),
            "Sai encounter order");

        Map<Integer, Long> theoSoDu = IntStream.rangeClosed(1, 1000)
            .parallel()
            .boxed()
            .collect(Collectors.groupingBy(
                n -> n % 3,
                Collectors.counting()
            ));

        yeuCau(theoSoDu.get(0) == 333L, "Sai nhóm dư 0");
        yeuCau(theoSoDu.get(1) == 334L, "Sai nhóm dư 1");
        yeuCau(theoSoDu.get(2) == 333L, "Sai nhóm dư 2");

        List<Integer> banSao = new ArrayList<>(nguon);
        List<Integer> ketQua = banSao.parallelStream()
            .map(n -> n * n)
            .collect(Collectors.toList());

        yeuCau(ketQua.size() == banSao.size(),
            "Sai số phần tử sau map");

        System.out.println("PASS: chia, xử lý, ghép kết quả");
    }
}
```

Khi mọi kiểm tra qua, chương trình in:

```text
PASS: chia, xử lý, ghép kết quả
```

Kiểm thử giúp phát hiện những lỗi phổ biến, **không chứng minh mọi accumulator/combiner tùy chỉnh luôn đúng**. Hãy kiểm tra bằng đại số các thuộc tính identity, associativity và tính tương thích trên miền dữ liệu thực tế.

## 15. Những lỗi và hiểu nhầm thường gặp

| Lỗi / hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ `parallel()` tạo một thread cho mỗi phần tử | Runtime thường chia thành phần việc và dùng cơ chế điều phối | Tách khái niệm phần việc, thread, dữ liệu. |
| Nghĩ chỉ các stage sau `parallel()` chạy song song | Chế độ thực thi áp dụng cho pipeline ở terminal | Dùng `isParallel()` để quan sát chế độ; không tách theo vị trí stage. |
| `forEach` in thứ tự khác list | Execution order không phải encounter order | Dùng `forEachOrdered` nếu phải in theo thứ tự. |
| `findAny` không trả phần tử đầu | Được phép chọn bất kỳ phần tử phù hợp | Dùng `findFirst` nếu yêu cầu phần tử đầu. |
| `reduce(10, Integer::sum)` cho sai kết quả | Identity không trung hòa phép cộng | Dùng `0`. |
| Phép trừ cho kết quả khác giữa tuần tự/song song | Phép trừ không có tính kết hợp | Chọn phép gộp associative. |
| Tự `ArrayList.add` trong `parallel().forEach` mất phần tử | Nhiều thread sửa list không an toàn | Dùng `collect(toList())`. |
| Dùng `AtomicInteger` làm thứ tự gặp | Bộ đếm phụ thuộc lịch thread | Dùng chỉ số từ nguồn có thứ tự. |
| `map` chứa log không chạy khi kết thúc bằng `count` | Runtime có thể bỏ bước không ảnh hưởng số lượng | Không dựa vào tác dụng phụ. |
| `groupingByConcurrent` đảo thứ tự nhóm | Collector unordered | Chọn collector giữ order hoặc sắp xếp đầu ra. |
| Nguồn không chia được nhưng gọi `parallel()` | `trySplit` có thể kém hiệu quả/trả null | Chọn nguồn thích hợp, đo hiệu năng. |
| `sorted` và `limit` trên ordered stream chậm | Phối hợp và trạng thái làm tăng chi phí | Xem lại thứ tự thao tác, nhu cầu order. |
| `parallel()` trên tác vụ I/O chậm hơn | Worker chặn, tranh chấp tài nguyên | Chọn mô hình I/O thích hợp. |
| Chỉ thử một lần rồi kết luận đúng | Chưa kiểm tra rỗng, dữ liệu biên, combiner | Đối chiếu độc lập, kiểm chứng tính chất đại số. |

## 16. Bài tập thực hành

### Bài 1 — Mô hình chia–xử lý–ghép

Cho `IntStream.rangeClosed(1, 8).parallel().map(n -> n * 2).sum()`. Kết quả là bao nhiêu? Giải thích ba giai đoạn và vì sao không thể khẳng định stream sẽ tạo đúng bốn nhánh, mỗi nhánh hai phần tử.

### Bài 2 — Identity và phép kết hợp

```java
List<Integer> so = Arrays.asList(2, 4, 6, 8);

int a = so.stream().reduce(0, Integer::sum);
int b = so.parallelStream().reduce(0, Integer::sum);
int c = so.parallelStream().reduce(10, Integer::sum);
```

`a` và `b` có giống nhau không? `c` có thể được coi là tổng đúng của nguồn không? Giải thích.

### Bài 3 — Thứ tự kết quả

```java
List<Integer> so = Arrays.asList(5, 2, 4, 1, 3);

List<Integer> kq = so.parallelStream()
    .map(n -> n * 10)
    .collect(Collectors.toList());

so.parallelStream().forEach(System.out::println);
```

Dự đoán `kq`. Có thể dự đoán thứ tự các dòng in bởi `forEach` không? Nếu cần in đúng thứ tự gặp, dùng gì?

### Bài 4 — Trạng thái dùng chung

```java
List<Integer> output = new ArrayList<>();
so.parallelStream().forEach(n -> output.add(n * n));
```

Đoạn trên có an toàn không? Viết lại bằng collector. Vì sao chỉ bọc list bằng `Collections.synchronizedList` chưa đủ để bảo đảm thứ tự kết quả theo encounter order?

### Bài 5 — Khi nào đáng đo hiệu năng?

Hai pipeline cùng xử lý 100.000 bản ghi: (A) tính phép toán CPU-bound độc lập trên mỗi phần tử và (B) đọc metadata/tệp hoặc gọi mạng cho mỗi phần tử. Có nên mặc định gọi `parallel()` cho cả hai không? Những yếu tố nào cần đo?

### Đáp án tham khảo

**Bài 1:** Kết quả là `72`, vì `2 × (1 + 2 + ... + 8) = 72`. Nguồn có thể chia theo nhiều cách; các phần xử lý tạo tổng cục bộ rồi ghép bằng phép cộng. Không có hợp đồng đúng bốn nhánh.

**Bài 2:** `a == 20`, `b == 20`. `c` không phải phép tổng hợp đúng vì `10` không là identity; số lần giá trị 10 xuất hiện ở các nhánh có thể khác tùy cách chia. Identity của phép cộng là 0.

**Bài 3:** `kq = [50, 20, 40, 10, 30]`. Thứ tự các dòng `forEach` không được bảo đảm. `forEachOrdered` thực hiện hành động theo encounter order của ordered stream.

**Bài 4:** Không, `ArrayList` không an toàn khi được nhiều thread sửa. Dùng:

```java
List<Integer> output = so.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

`synchronizedList` có thể tránh một số race khi thêm phần tử nhưng không khiến `forEach` chạy theo encounter order; vì thế thứ tự các lần `add` vẫn có thể khác nguồn.

**Bài 5:** Không mặc định. Pipeline CPU-bound độc lập với nguồn dễ chia có thể đáng thử song song; I/O blocking có thể bị giới hạn bởi số kết nối, ổ đĩa, timeout và tài nguyên worker dùng chung. Cần đo thời gian thực thi, throughput, latency, CPU, bộ nhớ, tranh chấp và áp lực I/O trên workload đại diện.

## 17. Tổng kết

Mô hình của parallel stream có thể ghi nhớ:

```text
Nguồn có Spliterator
          |
      trySplit()
          |
  Các phần việc cục bộ
          |
 map / filter / process
          |
   Kết quả trung gian
          |
  reduce / collect / sum
          |
      Kết quả cuối
```

- **Chia nguồn:** `Spliterator.trySplit` quyết định khả năng chia; `SIZED` / `SUBSIZED` / `ORDERED` giúp runtime hiểu đặc tính nguồn.
- **Xử lý:** hàm hành vi phải non-interfering và thường cần stateless; không phụ thuộc thread hay bộ đếm bên ngoài.
- **Ghép kết quả:** `reduce` đòi hỏi identity, associativity và combiner đúng; `collect` đòi hỏi supplier, accumulator và combiner tuân thủ hợp đồng.
- **Thứ tự:** encounter order khác thứ tự thực thi; `Collectors.toList()` có thể giữ thứ tự đầu ra trong ordered stream ngay cả khi `forEach` song song không giữ thứ tự in.
- **Hiệu năng:** thao tác stateful, yêu cầu order, nguồn khó chia và chi phí ghép có thể khiến song song chậm hơn.
- **Kiểm chứng:** so sánh kết quả trên ca rỗng, một phần tử, nhiều phần tử và dữ liệu biên; chứng minh hợp đồng phép gộp trước khi đo hiệu năng.

Hiểu rõ **chia nguồn – xử lý – ghép kết quả** giúp bạn dùng Stream API song song có cơ sở, tránh những lỗi âm thầm về trạng thái, thứ tự và tính đúng, đồng thời biết khi nào `parallel()` thực sự đáng cân nhắc.
