# Duyệt kết quả bằng forEach và forEachOrdered

Trong **Java Stream API**, cả `forEach` và `forEachOrdered` đều là thao tác kết thúc (*terminal operation*) dùng để thực hiện một hành động với các phần tử được pipeline tạo ra. Khác biệt cốt lõi là **thứ tự thực thi hành động**: `forEach` không cam kết giữ *encounter order*, còn `forEachOrdered` bảo đảm thực hiện theo encounter order **nếu Stream có thứ tự gặp phần tử được xác định**.

Bài thuộc chương **Duyệt, tìm kiếm và đối sánh** của module **JAVA_STREAM_API**. Khi đã biết tổ chức pipeline lazy bằng `filter`, `map`, `reduce` và `collect`, bạn cần chọn đúng cách tiêu thụ kết quả, đặc biệt với Stream song song. Kiến thức này còn liên quan đến `Spliterator`, grouping, collector tùy chỉnh, Stream Gatherers và các giới hạn về trạng thái, tài nguyên, hiệu năng.

## 1. Cú pháp: cả hai đều nhận Consumer và trả về void

Trong `java.util.stream.Stream<T>`:

```java
void forEach(Consumer<? super T> action);
void forEachOrdered(Consumer<? super T> action);
```

`Consumer<T>` là functional interface trong `java.util.function`, có phương thức trừu tượng `void accept(T value)`. Nó mô tả một hành động nhận phần tử nhưng không trực tiếp trả giá trị biến đổi.

Ví dụ với nguồn có thứ tự:

```java
import java.util.Arrays;
import java.util.List;

List<String> names = Arrays.asList("An", "Bình", "Chi");

names.stream()
        .map(String::toUpperCase)
        .forEachOrdered(System.out::println);
// AN
// BÌNH
// CHI
```

Trong pipeline trên, `map` là thao tác trung gian (*intermediate operation*) khai báo phép biến đổi, còn `forEachOrdered` là thao tác kết thúc thực sự kích hoạt việc duyệt.

> `forEach`/`forEachOrdered` là công cụ **tiêu thụ phần tử để thực hiện hành động**. Khi muốn tạo một danh sách, tập hợp, bản đồ hay một giá trị tính toán, thường nên dùng `collect`, `reduce` hoặc terminal operation phù hợp hơn.

## 2. Encounter order khác thứ tự thread hoàn thành

**Encounter order** là thứ tự các phần tử được nguồn và pipeline xác định. Một `List` có thứ tự theo vị trí phần tử; `IntStream.range(1, 6)` có thứ tự số tăng; `Stream` từ `HashSet` thường không có thứ tự gặp phần tử được bảo đảm. Các phép biến đổi như `map`, `filter` trên một nguồn có thứ tự thường giữ lại encounter order của những phần tử còn lại.

```text
Nguồn List:       [1, 2, 3, 4, 5]
       |
      filter(n -> n % 2 != 0)
       |
Kết quả có thứ tự: [1, 3, 5]
       |
    terminal operation
       +-- forEach:        thứ tự hành động không được cam kết
       +-- forEachOrdered: hành động với 1, rồi 3, rồi 5
```

Với Stream song song, các worker có thể xử lý nhiều phần tử cùng lúc. **Thứ tự xử lý nội bộ** không nhất thiết trùng encounter order. `forEachOrdered` chỉ cam kết **thứ tự hành động của terminal operation** theo encounter order; điều đó không có nghĩa mọi bước `map`/`filter` bên trên đã được thực thi tuần tự hay cùng một thread.

### 2.1. Bảng so sánh

| Tiêu chí | `forEach(action)` | `forEachOrdered(action)` |
|---|---|---|
| Loại thao tác | Kết thúc (*terminal*) | Kết thúc (*terminal*) |
| Kiểu tham số | `Consumer<? super T>` | `Consumer<? super T>` |
| Giá trị trả về | `void` | `void` |
| Với Stream có encounter order | Không cam kết thứ tự hành động | Cam kết thực hiện hành động theo encounter order |
| Với Stream không có encounter order | Không có thứ tự gặp phần tử cần giữ | Không tạo ra một thứ tự nghiệp vụ mới |
| Khi thực thi song song | Các lời gọi action có thể chạy trên nhiều worker, theo thứ tự không dự đoán | Hành động được sắp theo encounter order; không cam kết chạy trên một thread duy nhất |
| Chi phí | Thường dễ khai thác song song hơn khi hành động độc lập | Có thể cần chờ, điều phối, đồng bộ để giữ thứ tự |
| Dùng điển hình | Gửi sự kiện độc lập, xử lý không phụ thuộc thứ tự | Xuất báo cáo hoặc ghi kết quả bắt buộc theo thứ tự |

**Lưu ý:** `forEach` vẫn hoạt động trên những Stream có encounter order; đơn giản là phương thức **không có nghĩa vụ tôn trọng thứ tự đó**. Với Stream tuần tự thông thường, bạn thường quan sát các hành động diễn ra lần lượt theo thứ tự nguồn, nhưng không nên biến quan sát ấy thành một giả định áp dụng được khi thay nguồn, chế độ thực thi hoặc tối ưu pipeline.

## 3. Quan sát sự khác nhau khi chạy tuần tự và song song

### 3.1. Stream tuần tự

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 5)
        .forEach(System.out::print);
// Trên pipeline tuần tự thông thường: 12345

System.out.println();

IntStream.rangeClosed(1, 5)
        .forEachOrdered(System.out::print);
// 12345 (đúng thứ tự gặp phần tử)
```

Cả hai đều có thể cho ra cùng thứ tự trong ví dụ đơn giản. Khác biệt nằm ở **hợp đồng API**, thể hiện rõ hơn khi bật song song.

### 3.2. Stream song song: forEach không bảo đảm thứ tự

```java
IntStream.rangeClosed(1, 10)
        .parallel()
        .forEach(n -> System.out.print(n + " "));
// Có thể: 7 6 9 10 8 3 5 4 2 1
// Thứ tự cụ thể thay đổi tùy runtime và mỗi lần chạy.
```

Hành động in từng phần tử vẫn được gọi, nhưng **thứ tự các phần tử xuất hiện không được cam kết**. Ví dụ kết quả chỉ minh họa một khả năng; không dùng giá trị in thực tế để suy luận worker nào chắc chắn chạy trước.

### 3.3. Stream song song: forEachOrdered giữ thứ tự hành động

```java
IntStream.rangeClosed(1, 10)
        .parallel()
        .forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5 6 7 8 9 10
```

Nguồn `rangeClosed` có encounter order từ nhỏ đến lớn, vì vậy `forEachOrdered` duy trì thứ tự các hành động in. Pipeline vẫn được cấu hình `parallel()`; đây **không phải** lời yêu cầu chuyển toàn bộ xử lý thành tuần tự.

### 3.4. Tính thử trên một pipeline có filter và map

```java
import java.util.Arrays;
import java.util.List;

List<Integer> data = Arrays.asList(8, 3, 10, 7, 2, 5);

data.parallelStream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * 10)
        .forEachOrdered(System.out::println);
// 30
// 70
// 50
```

`filter` giữ các số lẻ theo encounter order của `List` (3, 7, 5), rồi `map` biến thành 30, 70, 50. `forEachOrdered` bảo đảm việc in những kết quả này theo đúng thứ tự đó.

## 4. Ví dụ hoàn chỉnh: ghi các mã đơn hàng theo thứ tự ưu tiên

Giả sử cần lọc các đơn hàng đã thanh toán và xuất mã **theo ngày tạo tăng dần, rồi mã tăng dần**. Vì đây là yêu cầu thứ tự nghiệp vụ, phải mô tả thứ tự bằng `sorted` trước khi tiêu thụ. `forEachOrdered` chỉ **giữ** encounter order hiện có; nó không tự sắp xếp theo thuộc tính ngày hay mã.

Ví dụ Java 8 chạy độc lập:

```java
import java.time.LocalDate;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class OrderTraversalDemo {
    static final class Order {
        private final String id;
        private final LocalDate createdOn;
        private final boolean paid;

        Order(String id, LocalDate createdOn, boolean paid) {
            this.id = id;
            this.createdOn = createdOn;
            this.paid = paid;
        }

        String getId() {
            return id;
        }

        LocalDate getCreatedOn() {
            return createdOn;
        }

        boolean isPaid() {
            return paid;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("DH-03", LocalDate.of(2026, 11, 18), true),
                new Order("DH-02", LocalDate.of(2026, 11, 17), false),
                new Order("DH-04", LocalDate.of(2026, 11, 18), true),
                new Order("DH-01", LocalDate.of(2026, 11, 16), true)
        );

        Comparator<Order> byDateThenId =
                Comparator.comparing(Order::getCreatedOn)
                        .thenComparing(Order::getId);

        System.out.println("Các đơn đã thanh toán theo thứ tự:");

        orders.parallelStream()
                .filter(Order::isPaid)
                .sorted(byDateThenId)
                .map(Order::getId)
                .forEachOrdered(System.out::println);
        // DH-01
        // DH-03
        // DH-04

        // Nếu nghiệp vụ cần trả về dữ liệu thay vì in ra,
        // collect tạo kết quả để phía gọi tự quyết định cách hiển thị.
        List<String> orderedIds = orders.parallelStream()
                .filter(Order::isPaid)
                .sorted(byDateThenId)
                .map(Order::getId)
                .collect(Collectors.toList());

        System.out.println(orderedIds);
        // [DH-01, DH-03, DH-04]
    }
}
```

Pipeline có hai trách nhiệm rõ ràng: `sorted(byDateThenId)` xác lập thứ tự nghiệp vụ; `forEachOrdered` duy trì thứ tự đó trong lúc xuất. Nếu thay bằng `forEach` trên pipeline song song, việc in mã **có thể bị đảo thứ tự** dù trước đó đã gọi `sorted`.

Nếu chỉ muốn trả danh sách mã đã sắp xếp cho một lớp khác sử dụng, `collect(Collectors.toList())` thường thích hợp hơn việc in hoặc thêm phần tử vào một danh sách có thể thay đổi từ bên ngoài.

## 5. forEachOrdered có đảm bảo chạy trên một thread không?

**Không.** Với Stream song song, JDK không cam kết mọi lời gọi action của `forEachOrdered` chạy trên cùng một thread. Điều được bảo đảm là đối với các phần tử theo encounter order, **việc thực hiện action cho một phần tử happens-before việc thực hiện action cho phần tử kế tiếp**. Quan hệ *happens-before* hỗ trợ khả năng nhìn thấy hiệu ứng bộ nhớ và thứ tự giữa những hành động đó.

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(n -> System.out.println(
                n + " : " + Thread.currentThread().getName()));
```

Số 1 đến 5 sẽ xuất hiện theo encounter order, còn tên thread có thể khác nhau. Không được kiểm tra một tên thread cố định để xác nhận tính đúng đắn.

Ngược lại, `forEach` được đặc tả rõ là hành động cho một phần tử có thể được thực hiện ở bất kỳ thread nào mà thư viện chọn; nếu cần **đồng bộ** khi truy cập trạng thái dùng chung, lập trình viên phải đảm trách. Việc các phần tử cùng thuộc một Stream không tạo ra quy tắc tự động bảo vệ biến mutable được các action sửa đổi.

### 5.1. Quan hệ happens-before chỉ áp dụng đúng phạm vi được bảo đảm

`forEachOrdered` bảo đảm thứ tự **các hành động `Consumer`** trên Stream có thứ tự; đừng suy rộng thành lời hứa rằng mọi hàm ở mọi bước trung gian sẽ được thực hiện tuần tự theo đúng encounter order. Ví dụ, một phép `map` tính toán tốn thời gian vẫn có thể thực hiện trên worker khác, nhưng việc gọi action sau cùng phải chờ để giữ thứ tự quan sát.

Điều này giải thích vì sao một pipeline có thể tính toán trung gian theo kiểu song song mà vẫn xuất kết quả theo đúng thứ tự.

## 6. Side effect và trạng thái chia sẻ: lỗi phổ biến với forEach

`forEach` được dùng cho hành động có tác dụng bên ngoài như in log, phát thông báo hay cập nhật hệ thống khác. Nhưng việc tác động lên **cùng một cấu trúc mutable không thread-safe** từ nhiều action song song là nguy hiểm.

### 6.1. Sai: cùng sửa ArrayList từ nhiều worker

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> unsafe = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(unsafe::add); // SAI: ArrayList không thread-safe.

// Không thể dựa vào unsafe.size() hay nội dung kết quả.
```

Ví dụ có data race. Danh sách có thể thiếu phần tử, nội dung sai, hoặc xảy ra lỗi trong quá trình cập nhật nội bộ.

**Đúng: để collector điều phối việc tạo kết quả**

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> safe = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.toList());

System.out.println(safe.size()); // 10000
System.out.println(safe.get(0));  // 0
```

Với nguồn `IntStream.range` có thứ tự, `Collectors.toList()` giữ encounter order trong danh sách kết quả. Mã không cần chia sẻ một `ArrayList` bên ngoài cho nhiều action.

### 6.2. Synchronized collection tránh race, nhưng không tạo thứ tự nghiệp vụ

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> synchronizedList =
        Collections.synchronizedList(new ArrayList<>());

IntStream.rangeClosed(1, 100)
        .parallel()
        .forEach(synchronizedList::add);
```

Các thao tác `add` được đồng bộ, giúp tránh race trong quá trình sửa danh sách. Tuy nhiên, **thứ tự phần tử thêm vào vẫn có thể khác 1, 2, ..., 100** do `forEach` không giữ thứ tự. Chỉ cần danh sách kết quả theo nguồn thì `collect` rõ ý và thường phù hợp hơn.

### 6.3. Đếm hoặc tổng hợp: dùng terminal operation phù hợp

```java
// Không nên tự tăng biến chia sẻ trong forEach của parallel stream:
// long[] total = {0};
// numbers.parallelStream().forEach(n -> total[0] += n);

long total = java.util.stream.LongStream.rangeClosed(1, 1000)
        .parallel()
        .sum(); // 500500

long count = java.util.stream.LongStream.rangeClosed(1, 1000)
        .filter(n -> n % 2 == 0)
        .count(); // 500
```

Khi bài toán là tính tổng, đếm, tìm cực trị, gom nhóm, xây Map hoặc List, Java Stream API có các terminal operation và collector được thiết kế để xử lý trực tiếp, không yêu cầu biến kết quả mutable ngoài pipeline.

### 6.4. Cẩn thận với action không thể hoàn tác

Nếu `forEach` gửi email, ghi giao dịch hoặc gọi API ngoài, lỗi ở một phần tử không tự hoàn tác các hành động đã diễn ra với phần tử khác. Khi chạy song song, hành động có thể xảy ra cùng lúc và theo thứ tự không xác định. Ngay cả `forEachOrdered` cũng không cung cấp tính nguyên tử, retry hay giao dịch.

Với hệ thống có yêu cầu giao dịch, xử lý lỗi, retry hoặc giới hạn tốc độ, cần thiết kế chúng ở lớp nghiệp vụ phù hợp; không dựa vào thứ tự duyệt như một bảo đảm giao dịch.

## 7. forEachOrdered trên nguồn không có thứ tự

Không phải mọi nguồn đều có encounter order. Ví dụ `HashSet` không bảo đảm thứ tự duyệt:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

Set<String> labels = new HashSet<>(
        Arrays.asList("C", "A", "B"));

labels.parallelStream()
        .forEachOrdered(System.out::println);
// Không có bảo đảm sẽ in A, B, C hay theo thứ tự chèn.
```

`forEachOrdered` **không sắp xếp** dữ liệu và không thêm một quy tắc encounter order mà nguồn không có.

Nếu cần thứ tự alphabet, tự thiết lập:

```java
labels.parallelStream()
        .sorted()
        .forEachOrdered(System.out::println);
// A
// B
// C
```

Ngoài ra, `BaseStream.unordered()` có thể loại bỏ ràng buộc encounter order của một Stream để trao thêm tự do tối ưu khi nghiệp vụ không cần thứ tự. Khi đã gọi `unordered()`, không dùng `forEachOrdered` để trông chờ tự khôi phục thứ tự ban đầu.

**Phân biệt hai loại thứ tự:**

- **Thứ tự dữ liệu theo nghiệp vụ**: do `sorted(comparator)` hoặc bản chất nguồn xác định.
- **Thứ tự hành động quan sát**: do terminal operation quyết định có phải tôn trọng encounter order hay không.

Muốn xuất báo cáo đã sắp xếp trên parallel stream, hai bước này thường cần xuất hiện cùng nhau: `sorted(...)` rồi `forEachOrdered(...)`.

## 8. Tính lazy, tiêu thụ một lần và mối liên hệ với matching

`filter`, `map` hay `sorted` được khai báo trước `forEach`/`forEachOrdered` nhưng thường chưa chạy cho đến khi terminal operation bắt đầu duyệt:

```java
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of("Java", "Stream")
        .map(String::toUpperCase);

// map chưa được tiêu thụ để sinh kết quả ra bên ngoài.
pipeline.forEachOrdered(System.out::println); // JAVA, STREAM

// pipeline.forEach(System.out::println);
// SAI: Stream đã được tiêu thụ, không thể dùng lại.
```

Mỗi pipeline thông thường chỉ được **tiêu thụ một lần**. Nếu cần hai loại kết quả, tạo Stream mới từ nguồn hoặc dùng collector để trả kết quả cho bước xử lý tiếp theo.

### 8.1. forEach không phải thao tác tìm kiếm ngắn mạch

`forEach` và `forEachOrdered` được dùng để duyệt, thường cần hành động với mọi phần tử đi tới terminal operation. Nếu mục tiêu chỉ là tìm một bản ghi hoặc kiểm tra có phần tử thỏa điều kiện hay không, hãy dùng các terminal operation có ý nghĩa đúng hơn:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<String> names = Arrays.asList("An", "Bình", "Chi");

boolean hasLongName = names.stream()
        .anyMatch(name -> name.length() >= 4); // true

Optional<String> firstLongName = names.stream()
        .filter(name -> name.length() >= 4)
        .findFirst(); // Optional[Bình]
```

`anyMatch` có thể kết thúc ngay khi tìm thấy một phần tử thỏa điều kiện; `findFirst` trả về phần tử đầu tiên theo encounter order nếu tồn tại; `findAny` có thể chọn một phần tử bất kỳ, đặc biệt hữu ích khi thứ tự không quan trọng trong pipeline song song.

Không nên duyệt bằng `forEach` rồi dùng biến mutable bên ngoài để “tìm được thì dừng”: API này không có cơ chế `break` tương đương vòng lặp, và tạo trạng thái chung khó kiểm soát. Với nhu cầu dừng sớm, dùng `anyMatch`, `allMatch`, `noneMatch`, `findFirst`, `findAny` hoặc các toán tử giới hạn phù hợp.

### 8.2. limit trước forEachOrdered

`limit(n)` là một thao tác trung gian giới hạn số phần tử đưa xuống terminal operation:

```java
java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .limit(4)
        .forEachOrdered(System.out::println);
// 1
// 2
// 3
// 4
```

Với nguồn có thứ tự, `limit(4)` chọn **bốn phần tử đầu theo encounter order**. `forEachOrdered` sau đó xuất đúng thứ tự ấy. Trên parallel stream có thứ tự, việc duy trì ràng buộc của `limit` và `forEachOrdered` có thể làm tăng chi phí so với xử lý không quan tâm thứ tự.

## 9. Hiệu năng: nên chọn cách nào?

`forEachOrdered` có thể làm giảm lợi ích của parallel stream vì các hành động cần được điều phối theo thứ tự. Nhưng không thể kết luận nó luôn chậm hơn: hiệu năng còn phụ thuộc vào nguồn, `Spliterator`, chi phí của từng bước `filter`/`map`, kích thước dữ liệu, số lõi CPU, I/O và tải hệ thống. Cần đo trên dữ liệu thực tế khi hiệu năng là yêu cầu quan trọng.

| Nhu cầu | Gợi ý |
|---|---|
| In hoặc xử lý tuần tự một số ít phần tử | `stream().forEachOrdered(...)` nếu thứ tự phải rõ ràng |
| Duyệt hành động độc lập, không cần thứ tự | `forEach(...)` |
| Xuất dữ liệu theo encounter order dù xử lý trung gian song song | `parallelStream().forEachOrdered(...)` |
| Tạo List kết quả để trả về | `collect(Collectors.toList())` |
| Tính tổng, đếm, tìm min/max | `sum`, `count`, `min`, `max`, `reduce` |
| Gom nhóm, tạo Map | `collect(groupingBy(...))`, `collect(toMap(...))` |
| Chỉ cần biết có phần tử thỏa điều kiện | `anyMatch(...)` |
| Cần phần tử đầu tiên theo thứ tự | `findFirst()` |
| Chỉ cần phần tử phù hợp bất kỳ | `findAny()` |

**Vì sao không dùng `parallelStream().forEachOrdered(...)` cho mọi bài toán?** Nếu nguồn chỉ có vài phần tử hoặc action nhanh, chi phí chia việc và chờ giữ thứ tự có thể vượt lợi ích tính toán song song. Với đầu ra tuần tự như một luồng log hoặc một màn hình console, khả năng tăng tốc cuối pipeline thường bị giới hạn bởi tốc độ đích ghi.

## 10. Những hiểu nhầm thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| “Đã `sorted` rồi thì `forEach` chắc chắn in đúng thứ tự.” | `sorted` thiết lập encounter order; `forEach` không cam kết thứ tự hành động trên Stream song song. |
| “`forEachOrdered` luôn sắp xếp tăng dần.” | Nó chỉ giữ encounter order sẵn có; muốn tăng dần thì dùng nguồn có thứ tự phù hợp hoặc `sorted`. |
| “`forEachOrdered` chạy trên đúng một thread.” | Không được cam kết; action được bảo đảm happens-before theo thứ tự phần tử, có thể dùng thread khác nhau. |
| “`forEach` trên parallel stream chỉ đổi thứ tự, không có rủi ro khác.” | Side effect sửa trạng thái dùng chung có thể gây data race; thư viện không tự bảo vệ đối tượng mutable ngoài pipeline. |
| “Dùng synchronizedList với `forEach` là giữ đúng thứ tự.” | Đồng bộ hóa việc thêm phần tử, nhưng không buộc `forEach` tuân encounter order. |
| “`forEach` có thể trả List.” | Cả hai phương thức trả `void`; muốn kết quả dữ liệu, dùng collector hoặc terminal operation phù hợp. |
| “Một Stream có thể gọi `forEach` xong rồi `forEachOrdered`.” | Stream đã tiêu thụ, phải tạo pipeline mới. |
| “Dùng `forEach` để tìm và dừng ngay khi thấy phần tử đúng.” | Dùng `findFirst`, `findAny` hoặc `anyMatch` cho mục đích tìm kiếm ngắn mạch. |

## 11. Bài tập thực hành

### Bài 1. Đánh giá kết quả song song

```java
java.util.stream.IntStream.range(1, 6)
        .parallel()
        .forEachOrdered(System.out::print);
```

**Đáp án:** In `12345` vì `range(1, 6)` phát 1 đến 5 theo encounter order và `forEachOrdered` bảo đảm thứ tự hành động đó.

### Bài 2. Thay forEach bằng forEachOrdered đã đủ chưa?

Nguồn là một `HashSet<String>` gồm `"B"`, `"A"`, `"C"`. Yêu cầu luôn in `A`, `B`, `C`. Chỉ thay `forEach` bằng `forEachOrdered` có đủ không?

**Đáp án:** Chưa. `HashSet` không có encounter order ổn định theo yêu cầu alphabet. Hãy gọi `sorted()` rồi `forEachOrdered(System.out::println)`.

### Bài 3. Thu thập dữ liệu an toàn khi song song

```java
List<Integer> result = new java.util.ArrayList<>();

java.util.stream.IntStream.range(0, 1000)
        .parallel()
        .forEach(result::add);
```

**Câu hỏi:** Vì sao không nên dùng đoạn trên, và thay bằng gì?

**Đáp án:** `ArrayList` không thread-safe, các worker có thể ghi đồng thời gây race. Dùng:

```java
List<Integer> result = java.util.stream.IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toList());
```

### Bài 4. Duyệt hay tìm kiếm?

Giả sử cần kiểm tra danh sách đơn hàng có ít nhất một đơn chưa thanh toán. Nên dùng `forEach` để cập nhật biến boolean hay `anyMatch`?

**Đáp án:** Dùng `orders.stream().anyMatch(order -> !order.isPaid())`. Nó diễn đạt đúng ý nghĩa kiểm tra tồn tại và có thể dừng sớm.

### Bài 5. Chọn thứ tự nghiệp vụ

Danh sách sản phẩm đã có `getPrice()`. Yêu cầu xuất tên sản phẩm theo giá tăng dần, nếu giá bằng nhau thì tên theo alphabet.

```java
products.stream()
        .sorted(java.util.Comparator
                .comparingInt(Product::getPrice)
                .thenComparing(Product::getName))
        .map(Product::getName)
        .forEachOrdered(System.out::println);
```

Đoạn minh họa giả định tồn tại kiểu `Product` với `getPrice()` trả `int` và `getName()` trả `String` không null. `sorted` tạo thứ tự; `forEachOrdered` dùng thứ tự đó để xuất tên.

## 12. Nguyên tắc ghi nhớ

Khi **duyệt để tạo side effect**, dùng `forEach` nếu các hành động độc lập và thứ tự không quan trọng; dùng `forEachOrdered` khi cần tôn trọng encounter order. Nếu thứ tự nghiệp vụ chưa có, hãy tạo nó bằng nguồn có thứ tự hoặc `sorted`. Khi kết quả phải được giữ lại làm dữ liệu, ưu tiên `collect` và các terminal operation chuyên dụng. Trong Stream song song, tránh trạng thái mutable dùng chung và hiểu rằng **thứ tự hành động**, **thứ tự thực thi các bước trung gian** và **thread được sử dụng** là những khái niệm khác nhau.
