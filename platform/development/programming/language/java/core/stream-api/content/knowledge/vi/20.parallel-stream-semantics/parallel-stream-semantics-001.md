# Kích hoạt song song bằng parallelStream và parallel

Java Stream API cho phép xử lý một dãy phần tử theo pipeline khai báo: tạo nguồn, nối các thao tác trung gian như `filter`, `map`, rồi thực hiện thao tác kết thúc như `sum`, `reduce` hoặc `collect`. Mặc định nhiều nguồn tạo ra **Stream tuần tự** (*sequential stream*). Khi công việc đủ lớn và có thể phân chia độc lập, ta có thể yêu cầu **chế độ song song** (*parallel stream*) bằng `Collection.parallelStream()` hoặc `BaseStream.parallel()`. Tuy nhiên, việc bật chế độ song song **không bảo đảm chương trình nhanh hơn, không biến một thuật toán có side effect thành thread-safe và không bảo đảm mỗi phần tử chạy trên một thread riêng**.

Bài thuộc chương **Ngữ nghĩa xử lý song song** của module **JAVA_STREAM_API**. Trọng tâm là cách kích hoạt chế độ song song, cách kiểm tra và thay đổi chế độ, ảnh hưởng đến encounter order, reduction, collector, trạng thái dùng chung và hiệu năng. Kiến thức này hỗ trợ các phần nâng cao về `Spliterator`, grouping, collector tùy chỉnh và Stream Gatherers, nhưng cần bắt đầu bằng hợp đồng ngữ nghĩa của Stream chứ không chỉ bằng lời gọi `parallel()`.

## 1. Hai cách phổ biến để tạo Stream song song

### 1.1. Gọi parallelStream() trực tiếp trên Collection

Từ Java 8, giao diện `java.util.Collection<E>` có phương thức:

```java
default Stream<E> parallelStream();
```

Ví dụ:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);

int sum = numbers.parallelStream()
        .filter(n -> n % 2 != 0)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 9 = 1 + 3 + 5
```

`parallelStream()` tạo một Stream có chế độ song song từ collection. Nó có thể được gọi trên `List`, `Set` và các collection khác; nếu nguồn là một `Map`, thường chọn `map.entrySet().parallelStream()` hoặc `map.values().parallelStream()` tùy dữ liệu cần duyệt.

### 1.2. Gọi parallel() trên một Stream đã có

`parallel()` là phương thức của `BaseStream` và có trên `Stream` cũng như các primitive stream `IntStream`, `LongStream`, `DoubleStream`:

```java
import java.util.stream.IntStream;

long sum = IntStream.rangeClosed(1, 100_000)
        .parallel()
        .mapToLong(n -> n)
        .sum();

System.out.println(sum); // 5000050000
```

Ở ví dụ này, `rangeClosed(1, 100_000)` tạo dãy số nguyên có thứ tự; `parallel()` yêu cầu xử lý song song, `mapToLong` chuyển sang `long` để tổng không tràn `int`, còn `sum()` thực hiện phép tổng hợp.

Có thể bắt đầu từ `stream()` rồi gọi `parallel()`:

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);

int sum = numbers.stream()
        .parallel()
        .mapToInt(Integer::intValue)
        .sum(); // 15
```

Trong phần lớn bài toán với `Collection` thông thường, `collection.parallelStream()` và `collection.stream().parallel()` là **hai cách diễn đạt cùng ý định**: thu được pipeline ở chế độ song song. Tuy nhiên, đừng coi chúng là cam kết về cùng chiến lược chia việc hoặc tốc độ, vì nguồn `Spliterator` và implementation collection có thể ảnh hưởng đến khả năng phân tách.

### 1.3. Bảng chọn nhanh

| Nguồn hiện có | Cách kích hoạt | Ghi chú |
|---|---|---|
| `List<Product> products` | `products.parallelStream()` | Ngắn gọn khi đã có collection |
| `Set<String> tags` | `tags.parallelStream()` | Không tự thêm encounter order cho set không có thứ tự |
| `Stream<Order> orders` | `orders.parallel()` | Đổi chế độ của pipeline |
| `IntStream.range(0, n)` | `IntStream.range(0, n).parallel()` | Nguồn số nguyên thủy dễ chia khoảng |
| `Arrays.stream(array)` | `Arrays.stream(array).parallel()` | Xử lý phần tử từ mảng |
| `Map<K,V> map` | `map.entrySet().parallelStream()` | Xử lý từng entry của Map |
| `Spliterator<T> spliterator` | `StreamSupport.stream(spliterator, true)` | Cách nâng cao khi tự kiểm soát nguồn |

**Lưu ý:** `parallelStream` không có trên chính kiểu `Stream`; đối tượng đã là Stream thì gọi `parallel()`.

## 2. parallel() đặt chế độ, không lập tức thực hiện công việc

`parallel()` **không phải terminal operation**. Nó không tự duyệt dữ liệu và không tự tạo kết quả. Pipeline vẫn có tính *lazy*: phép `filter` hay `map` được thực hiện khi có thao tác kết thúc thực sự yêu cầu dữ liệu.

```java
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.of(1, 2, 3, 4)
        .parallel()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);

System.out.println(pipeline.isParallel()); // true

List<Integer> result = pipeline.collect(
        java.util.stream.Collectors.toList());
System.out.println(result); // [20, 40]
```

Thao tác kết thúc `collect` mới kích hoạt quá trình xử lý. `isParallel()` là phép hỏi **chế độ cấu hình** của Stream, không phải một lệnh thực thi. Không có bảo đảm rằng cả bốn phần tử trong ví dụ đều được xử lý trên các thread khác nhau: kích thước quá nhỏ có thể khiến việc chia việc không mang lại lợi ích.

### 2.1. sequential() chuyển lại chế độ tuần tự

`BaseStream.sequential()` đưa Stream về chế độ tuần tự:

```java
Stream<Integer> selected = Stream.of(1, 2, 3)
        .parallel()
        .sequential();

System.out.println(selected.isParallel()); // false
System.out.println(selected.count());      // 3
```

Nếu pipeline gọi cả `parallel()` và `sequential()`, **chế độ cuối cùng của pipeline khi terminal operation chạy** là điều cần quan tâm; không có nghĩa mỗi đoạn pipeline giữ một chế độ riêng:

```java
Stream<Integer> source = Stream.of(1, 2, 3)
        .parallel()
        .map(n -> n * 2)
        .sequential();

System.out.println(source.isParallel()); // false
System.out.println(source.reduce(0, Integer::sum)); // 12
```

Ngược lại, `Stream.of(1, 2, 3).sequential().parallel()` ở chế độ song song. Không nên dùng các lệnh chuyển qua lại liên tục như một cơ chế “đặt phần này chạy song song, phần kia chạy tuần tự” bên trong **một** pipeline; nếu cần các giai đoạn có vòng đời khác nhau, phải hoàn tất một giai đoạn rồi tạo pipeline mới từ kết quả thích hợp.

### 2.2. Stream vẫn chỉ dùng được một lần

`parallel()` **không nhân bản** dữ liệu hay tạo một pipeline có thể dùng lại nhiều lần:

```java
Stream<Integer> numbers = Stream.of(1, 2, 3).parallel();
long count = numbers.count(); // 3

// numbers.reduce(0, Integer::sum);
// SAI: Stream đã được tiêu thụ.
```

Nếu cần cả tổng và số lượng, có thể tạo hai Stream mới từ nguồn có thể duyệt lại hoặc dùng một collector tổng hợp nhiều đại lượng trong một lần duyệt.

## 3. Parallel stream hoạt động như thế nào?

Ở mức khái niệm, Java có thể **chia nguồn thành các phần**, xử lý từng phần rồi **gộp kết quả**:

```text
              Nguồn [1, 2, 3, 4, 5, 6, 7, 8]
                              |
                      Spliterator chia
                        /            \
                 [1,2,3,4]        [5,6,7,8]
                  /      \         /      \
               [1,2]   [3,4]   [5,6]   [7,8]
                  \      /         \      /
                 kết quả cục bộ   kết quả cục bộ
                        \           /
                          kết hợp
                              |
                       kết quả cuối
```

**Sơ đồ chỉ minh họa**; thư viện có thể chia nguồn theo chiến lược khác. Điểm quan trọng là có những việc có thể thực hiện độc lập, nhưng bước kết hợp vẫn phải cho kết quả đúng dù nguồn được chia thành bao nhiêu phần.

### 3.1. Vai trò của Spliterator

`Spliterator` là cơ chế Stream dùng để duyệt và có thể phân chia nguồn. Các khả năng như `trySplit()`, ước lượng kích thước (`estimateSize()`) và các đặc tính `ORDERED`, `SIZED`, `SUBSIZED` có thể ảnh hưởng cách framework chia việc.

Thông thường, một mảng hoặc `ArrayList` dễ chia thành các đoạn hơn một nguồn phụ thuộc trạng thái trước để tạo phần tử kế tiếp. Chẳng hạn:

```java
// Nguồn có khoảng số nguyên rõ ràng.
long sumRange = java.util.stream.LongStream
        .rangeClosed(1, 100_000)
        .parallel()
        .sum();

// Nguồn được sinh từng bước từ phần tử trước.
long sumIterate = java.util.stream.Stream
        .iterate(1L, n -> n + 1)
        .limit(100_000)
        .parallel()
        .mapToLong(Long::longValue)
        .sum();
```

Hai pipeline cùng có thể tạo tổng `5000050000`, nhưng nguồn `iterate` có đặc điểm sinh nối tiếp nên không mặc định có khả năng chia việc tốt bằng `rangeClosed`. Đừng xem việc thêm `parallel()` là đủ để xóa bỏ đặc tính tuần tự vốn có của nguồn.

### 3.2. Thread và ForkJoinPool

Các parallel stream Java phổ biến thường được triển khai bằng cơ chế **fork/join** và sử dụng `ForkJoinPool.commonPool()` trong bối cảnh thông thường. Nhưng API Stream **không cam kết mỗi phần tử chạy trên một thread cụ thể, không cam kết số thread chính xác**, và không biến `parallel()` thành một lời gọi lập lịch công việc bất đồng bộ cho caller.

```java
java.util.stream.IntStream.rangeClosed(1, 8)
        .parallel()
        .forEach(n -> System.out.println(
                n + " handled by " + Thread.currentThread().getName()));
```

Khi chạy, bạn có thể thấy các tên thread khác nhau và các số in không theo thứ tự. **Tên thread và thứ tự cụ thể chỉ dùng để quan sát**, không phải dữ liệu để viết phép kiểm thử tính đúng đắn.

Vì common pool là tài nguyên chia sẻ trong nhiều cấu hình runtime, tác vụ blocking I/O lâu dài, đợi lock hoặc chờ mạng có thể làm giảm thông lượng của những tác vụ khác. Parallel stream thích hợp nhất khi phần việc đủ lớn, tính toán chủ yếu trên CPU, độc lập và có thể gộp kết quả hiệu quả. Nếu muốn kiểm soát sâu lịch thực thi và giới hạn mức đồng thời, cân nhắc thiết kế thực thi riêng thay vì phụ thuộc ngầm vào việc gọi `parallel()`.

## 4. Ví dụ Java 8 hoàn chỉnh: tổng hợp hóa đơn

Ví dụ sau minh họa **hai cách bật song song**, so sánh kết quả với chế độ tuần tự, rồi thu thập theo khu vực. Không có side effect dùng chung trong pipeline; dữ liệu hóa đơn được xem là bất biến khi duyệt.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ParallelStreamActivationDemo {
    static final class Invoice {
        private final String id;
        private final String region;
        private final long amountCents;
        private final boolean paid;

        Invoice(String id, String region, long amountCents, boolean paid) {
            this.id = id;
            this.region = region;
            this.amountCents = amountCents;
            this.paid = paid;
        }

        String getId() {
            return id;
        }

        String getRegion() {
            return region;
        }

        long getAmountCents() {
            return amountCents;
        }

        boolean isPaid() {
            return paid;
        }
    }

    public static void main(String[] args) {
        List<Invoice> invoices = Arrays.asList(
                new Invoice("HD-01", "BAC", 1_000L, true),
                new Invoice("HD-02", "NAM", 2_000L, true),
                new Invoice("HD-03", "BAC", 3_000L, false),
                new Invoice("HD-04", "BAC", 4_000L, true),
                new Invoice("HD-05", "NAM", 5_000L, true)
        );

        // 1) Stream tuần tự mặc định.
        long sequentialTotal = invoices.stream()
                .filter(Invoice::isPaid)
                .mapToLong(Invoice::getAmountCents)
                .sum();

        // 2) Collection.parallelStream().
        long parallelTotal = invoices.parallelStream()
                .filter(Invoice::isPaid)
                .mapToLong(Invoice::getAmountCents)
                .sum();

        // 3) Stream.parallel() trên nguồn tuần tự.
        long parallelViaFlag = invoices.stream()
                .parallel()
                .filter(Invoice::isPaid)
                .mapToLong(Invoice::getAmountCents)
                .sum();

        System.out.println(sequentialTotal); // 12000
        System.out.println(parallelTotal);   // 12000
        System.out.println(parallelViaFlag); // 12000

        // 4) Thu thập song song bằng collector có sẵn.
        Map<String, Long> paidByRegion = invoices.parallelStream()
                .filter(Invoice::isPaid)
                .collect(Collectors.groupingBy(
                        Invoice::getRegion,
                        Collectors.summingLong(Invoice::getAmountCents)));

        System.out.println(paidByRegion.get("BAC")); // 5000
        System.out.println(paidByRegion.get("NAM")); // 7000

        // 5) collect(toList()) giữ encounter order từ nguồn List.
        List<String> paidIds = invoices.parallelStream()
                .filter(Invoice::isPaid)
                .map(Invoice::getId)
                .collect(Collectors.toList());
        System.out.println(paidIds);
        // [HD-01, HD-02, HD-04, HD-05]

        // 6) Kiểm tra và đổi chế độ.
        System.out.println(invoices.parallelStream().isParallel()); // true
        Stream<Invoice> switched = invoices.stream()
                .parallel()
                .sequential();
        System.out.println(switched.isParallel()); // false
        System.out.println(switched.count());      // 5

        // 7) In có thứ tự dù pipeline được cấu hình song song.
        invoices.parallelStream()
                .filter(Invoice::isPaid)
                .map(Invoice::getId)
                .forEachOrdered(System.out::println);
        // HD-01
        // HD-02
        // HD-04
        // HD-05
    }
}
```

**Diễn giải:** ba cách tính tổng đầu đều cho `12000` vì chỉ có bốn hóa đơn đã thanh toán. Collector `groupingBy` với `summingLong` để framework quản lý việc tích lũy và gộp từng nhóm; không cần một `HashMap` chung bị sửa từ nhiều thread. `collect(toList())` bảo toàn encounter order từ nguồn `List` có thứ tự, nhưng Map từ `groupingBy` không cam kết thứ tự duyệt các khóa. Với năm phần tử, việc bật song song **không phải** khuyến nghị tối ưu hiệu năng; chương trình chỉ minh họa ngữ nghĩa API.

## 5. Encounter order vẫn là một khái niệm riêng

**Encounter order** là thứ tự các phần tử được nguồn và pipeline xác lập. Ví dụ `List` có thứ tự theo vị trí; `IntStream.range` có thứ tự số tăng; một `HashSet` không bảo đảm encounter order. Bật `parallel()` **không tự xóa** encounter order, nhưng cách **thực thi hành động** có thể khác thứ tự đó.

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 8)
        .parallel()
        .forEach(n -> System.out.print(n + " "));
// Có thể không in theo thứ tự 1, 2, 3, ..., 8.

System.out.println();

IntStream.rangeClosed(1, 8)
        .parallel()
        .forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5 6 7 8
```

`forEach` **không bảo đảm** thứ tự thực thi action, kể cả trên nguồn có encounter order. `forEachOrdered` **bảo đảm** action được thực hiện theo encounter order nếu Stream có thứ tự; nhưng có thể đòi hỏi điều phối, chờ đợi và làm giảm lợi ích song song. Nó **không** cam kết mọi `map` hoặc `filter` bên trên cũng chạy theo thứ tự hoặc cùng một thread.

### 5.1. findFirst và findAny

`findFirst()` tôn trọng phần tử đầu tiên theo encounter order của một Stream có thứ tự. `findAny()` được phép chọn phần tử phù hợp bất kỳ và thường trao nhiều tự do hơn cho xử lý song song:

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt first = IntStream.rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 7 == 0)
        .findFirst();

OptionalInt any = IntStream.rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 7 == 0)
        .findAny();

System.out.println(first.orElse(-1)); // 7
System.out.println(any.isPresent());  // true
// Không giả định any.getAsInt() luôn là 7.
```

Nếu ứng dụng chỉ cần biết có phần tử phù hợp, dùng `anyMatch` thay vì duyệt toàn bộ bằng `forEach`. Nếu ứng dụng cần vị trí đầu tiên, phải giữ yêu cầu encounter order; đừng chọn `findAny` chỉ vì muốn nhanh mà làm thay đổi nghiệp vụ.

### 5.2. limit, distinct và sorted có thể có chi phí giữ thứ tự

`limit(n)` trên Stream có thứ tự phải chọn **n phần tử đầu theo encounter order**. `distinct()` trên Stream có thứ tự phải xác định phần tử nào là lần xuất hiện đầu được giữ. `sorted()` cần nắm đủ dữ liệu liên quan để sắp xếp. Những ràng buộc này có thể làm pipeline song song tốn thêm bộ nhớ, đồng bộ hoặc thời gian.

```java
List<Integer> firstFourEven = java.util.stream.IntStream
        .rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 2 == 0)
        .limit(4)
        .boxed()
        .collect(java.util.stream.Collectors.toList());

System.out.println(firstFourEven); // [2, 4, 6, 8]
```

Đừng gọi `unordered()` chỉ để tăng tốc nếu nghiệp vụ đang cần “bốn phần tử đầu tiên” theo nguồn; thao tác đó có thể thay đổi tập phần tử được chọn.

## 6. Side effect và trạng thái dùng chung: nguồn lỗi chính

Đổi `stream()` thành `parallelStream()` làm nhiều lời gọi lambda **có thể diễn ra đồng thời**. Bất kỳ biến hay đối tượng mutable nào được nhiều lời gọi cùng sửa đều cần xem xét về tính an toàn luồng. Nhưng biện pháp tốt nhất thường là **tránh đưa trạng thái dùng chung vào lambda**, không phải thêm lock tùy tiện.

### 6.1. Sai: nhiều thread cùng sửa ArrayList

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> unsafe = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(unsafe::add); // SAI: ArrayList không thread-safe.

// Không thể coi unsafe.size() hoặc nội dung là đáng tin.
```

Đây là *data race*: nhiều worker có thể cùng thay đổi cấu trúc nội bộ của `ArrayList`, dẫn đến mất phần tử, sai thứ tự hoặc lỗi. Việc thấy một vài lần chạy cho `size == 10000` không chứng minh code an toàn.

### 6.2. Đúng: để Collector quản lý bộ tích lũy

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

Với nguồn có thứ tự và collector phù hợp, runtime có thể tạo **nhiều container cục bộ**, tích lũy phần tử rồi gộp chúng theo hợp đồng của collector. Không cần tự quản lý một `ArrayList` mutable bên ngoài pipeline.

### 6.3. AtomicLong tránh race nhưng chưa chắc là thiết kế tối ưu

`AtomicLong.addAndGet` có thể bảo vệ một phép cộng trên trạng thái chia sẻ, nhưng việc nhiều worker tranh chấp cùng một biến có thể gây chi phí:

```java
java.util.concurrent.atomic.AtomicLong total =
        new java.util.concurrent.atomic.AtomicLong();

java.util.stream.LongStream.rangeClosed(1, 100_000)
        .parallel()
        .forEach(total::addAndGet);

System.out.println(total.get()); // 5000050000
```

Để tính tổng, cách gọn và thường hợp lý hơn là:

```java
long sum = java.util.stream.LongStream.rangeClosed(1, 100_000)
        .parallel()
        .sum(); // 5000050000
```

`sum` mô tả một phép reduction thay vì ép tất cả worker cập nhật chung một bộ tích lũy. Đừng diễn giải “thread-safe” là “tự động hiệu quả”.

### 6.4. Đừng sửa nguồn khi đang duyệt

Các lambda nên **non-interfering** (không can thiệp vào nguồn) và thường **stateless** (không dựa trên trạng thái mutable dùng chung). Ví dụ, thêm/xóa phần tử của chính một `ArrayList` nguồn từ `filter` hay `map` trong lúc Stream duyệt có thể gây lỗi hoặc kết quả không dự đoán được. Hãy chuẩn bị một nguồn hợp lệ trước, sau đó xây pipeline chỉ đọc.

Với tác vụ gọi API ngoài, ghi database, ghi file hoặc gửi email trong `forEach`, còn phải xem xét retry, lỗi một phần, giới hạn đồng thời và giao dịch. `parallel()` không tự cung cấp những cơ chế đó.

## 7. Reduction và Collector phải có hợp đồng đúng

Để gộp kết quả từ các nhánh, phép toán reduction cần thỏa **tính kết hợp nhóm** (*associativity*):

\[
(a \mathbin{\mathrm{op}} b) \mathbin{\mathrm{op}} c
= a \mathbin{\mathrm{op}} (b \mathbin{\mathrm{op}} c)
\]

`Integer::sum` và `Long::sum` phù hợp về tính kết hợp trong ngữ nghĩa phép cộng số nguyên của Java (nhưng **có thể tràn số** so với tổng toán học mong muốn). Phép trừ và phép chia nói chung không thỏa tính kết hợp nhóm.

```java
int left = (20 - 5) - 3; // 12
int right = 20 - (5 - 3); // 18
```

Do đó, đây **không phải** một reduction đúng theo hợp đồng khi framework được phép chia việc:

```java
// KHÔNG NÊN: trừ không có tính kết hợp nhóm.
int wrong = java.util.stream.Stream.of(20, 5, 3)
        .parallel()
        .reduce((a, b) -> a - b)
        .orElse(0);
// Kết quả có thể phụ thuộc cách các phần được gộp.
```

### 7.1. Identity phải là phần tử đơn vị thực sự

Khi dùng `reduce(identity, accumulator)`, identity phải không làm thay đổi phần tử:

```java
int correct = java.util.stream.IntStream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum);
System.out.println(correct); // 6

// SAI: 100 không là phần tử đơn vị của phép cộng.
int wrong = java.util.stream.IntStream.of(1, 2, 3)
        .parallel()
        .reduce(100, Integer::sum);
// Không được mong chờ kết quả theo logic "100 chỉ cộng một lần".
```

Trên các nhánh, identity có thể tham gia nhiều kết quả trung gian; một identity không phù hợp khiến kết quả sai hoặc phụ thuộc cách phân hoạch. Với phép cộng, chọn `0`; với phép nhân, chọn `1`. Đừng dùng một số mặc định nghiệp vụ làm identity nếu nó không thực sự là đơn vị của phép toán.

### 7.2. Collector phải kết hợp được các phần tích lũy

`collect(Collectors.toList())`, `groupingBy` và `summingLong` là các collector có sẵn thực hiện tích lũy và kết hợp theo hợp đồng. Khi tự viết `Collector`, phải bảo đảm:

- `supplier` tạo trạng thái tích lũy mới, độc lập và hợp lệ.
- `accumulator` thêm phần tử vào trạng thái mà không cần sửa nguồn hay trạng thái ngoài.
- `combiner` ghép đủ hai trạng thái và không làm mất phần tử.
- Kết quả cuối tương đương giữa việc tích lũy liên tục và việc chia nguồn rồi kết hợp.
- Không công bố `CONCURRENT` cho một container không chịu được nhiều worker cập nhật đồng thời; không công bố `UNORDERED` khi thứ tự nghiệp vụ quan trọng.

```java
Map<String, Long> totals = invoices.parallelStream()
        .filter(Invoice::isPaid)
        .collect(java.util.stream.Collectors.groupingBy(
                Invoice::getRegion,
                java.util.stream.Collectors.summingLong(
                        Invoice::getAmountCents)));
```

Đoạn này sử dụng `Invoice` và `invoices` trong chương trình ở phần 4. `groupingBy` không bắt buộc phải là collector `CONCURRENT` để được dùng trong parallel stream: framework có thể dùng các Map trung gian rồi gộp.

Nếu thứ tự không quan trọng và dữ liệu có đặc tính phù hợp, có thể cân nhắc `groupingByConcurrent` hoặc `toConcurrentMap`, nhưng không mặc định chúng nhanh hơn hay giữ nguyên quy tắc “phần tử gặp đầu/cuối” trong một Stream đã bỏ encounter order.

### 7.3. Sai số dấu phẩy động

`double` không có tính kết hợp nhóm chính xác theo bit do làm tròn:

```java
double a = (1.0e16 + -1.0e16) + 1.0; // 1.0
double b = 1.0e16 + (-1.0e16 + 1.0); // 0.0
```

Vì vậy, phép tổng hợp dấu phẩy động song song có thể cho những khác biệt nhỏ (hoặc đáng kể ở dữ liệu đặc biệt) so với tuần tự. `DoubleStream.sum()` có thể sử dụng thuật toán cộng bù để cải thiện độ chính xác, nhưng không bảo đảm kết quả giống từng bit trong mọi cách chia việc. Với tiền tệ, cân nhắc `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất và kiểm soát tràn số.

## 8. Khi nào parallelStream có lợi, và khi nào nên tránh?

Tốc độ thực tế phụ thuộc vào **chi phí xử lý mỗi phần tử**, **chi phí chia nguồn**, **chi phí gộp kết quả**, **số phần tử**, ràng buộc thứ tự và tài nguyên máy. Không có ngưỡng số phần tử cố định bảo đảm chế độ song song nhanh hơn.

| Tình huống | Nhận định |
|---|---|
| Mảng hoặc khoảng số lớn, mỗi phần tử tính toán CPU đáng kể, không phụ thuộc nhau | Có thể được lợi từ song song nếu đo thực tế xác nhận |
| Danh sách vài chục phần tử, phép `map` rất nhẹ | Chi phí chia việc/gộp thường làm song song kém hấp dẫn |
| Nguồn `Stream.iterate` phụ thuộc phần tử trước | Khả năng chia nguồn có thể hạn chế lợi ích |
| Pipeline dùng `sorted`, `distinct` hoặc `limit` theo encounter order | Có thể cần phối hợp/tích lũy thêm để giữ thứ tự |
| Nhiều tác vụ I/O blocking hoặc gọi mạng | Nguy cơ chiếm worker và tranh chấp tài nguyên; cần cơ chế giới hạn đồng thời thích hợp |
| Dùng mutable state chung trong `forEach` | Rủi ro data race; nên thiết kế lại thay vì chỉ thêm `parallel()` |
| Yêu cầu giao dịch, gửi thông báo đúng thứ tự | Song song không cung cấp thứ tự hành động hay transaction một cách tự động |
| Tính toán `BigDecimal` với yêu cầu chính xác cao | Có thể dùng song song nếu phép gộp và chính sách làm tròn đúng; đo chi phí |

### 8.1. Chi phí chia nguồn và ghép kết quả

Mỗi phần việc phải đủ lớn để bù **overhead** chia việc, lập lịch và gộp. Chẳng hạn, trên `IntStream.range(0, 10)`, tính bình phương rồi tổng có quá ít việc để suy ra lợi ích từ parallelism. Trái lại, một phép toán thuần CPU tốn kém trên tập dữ liệu lớn có thể hưởng lợi rõ hơn.

### 8.2. Benchmark phải đo đúng

Nếu muốn so tuần tự và song song:

1. Dùng **cùng dữ liệu và cùng logic nghiệp vụ**, kiểm tra kết quả đúng trước khi đo.
2. Khởi động (*warm up*) cả hai đường xử lý để giảm ảnh hưởng biên dịch JIT và khởi tạo.
3. Đo nhiều lần, trên kích thước dữ liệu đại diện; không dựa vào một lần `System.nanoTime()` với tập nhỏ.
4. Tránh `System.out.println`, ghi log, đọc file mạng trong phần tính toán nếu mục đích là đo CPU.
5. Dùng một công cụ benchmark như **JMH** khi cần kết luận hiệu năng đáng tin; quan tâm cả phân bổ bộ nhớ và tải các thread khác.

Không nên thay đổi luồng chạy sản xuất chỉ dựa vào kết quả một ví dụ ngắn hoặc một lần đo trên máy phát triển.

## 9. Parallel stream không phải cơ chế async

Phương thức `parallel()` yêu cầu runtime **có thể xử lý các phần tử bằng nhiều worker trong quá trình terminal operation**. Nó **không** có nghĩa việc gọi `sum()` hay `collect()` ngay lập tức trả về một `Future` để caller tiếp tục công việc khác. Thông thường, terminal operation kết thúc rồi mới trả giá trị cho người gọi.

```java
long total = java.util.stream.LongStream
        .rangeClosed(1, 100_000)
        .parallel()
        .sum();

// Đến đây total đã được tính, không phải CompletableFuture<Long>.
System.out.println(total); // 5000050000
```

Với nhu cầu điều phối tác vụ bất đồng bộ, hủy tác vụ, timeout, giới hạn đồng thời và xử lý kết quả khi hoàn tất, cần lựa chọn mô hình phù hợp như `ExecutorService` hoặc `CompletableFuture`. Chúng giải quyết bài toán khác với việc song song hóa một pipeline dữ liệu.

### 9.1. Nested parallel stream và blocking

Không tự động đặt `parallel()` ở cả pipeline ngoài và pipeline trong với kỳ vọng tăng tốc theo cấp số nhân. Các tác vụ có thể tranh chấp cùng tài nguyên worker, phát sinh chi phí quản lý, và làm giảm hiệu năng. Với nguồn I/O như `Files.lines`, vẫn cần `try-with-resources` ngay cả khi đọc song song; `parallel()` không thay thế việc đóng tài nguyên. Các hoạt động gọi mạng, đợi khóa hoặc ngủ thread trong mapper cần được đánh giá theo tải thực tế và mức đồng thời được phép.

## 10. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “`parallelStream()` luôn nhanh hơn `stream()`.” | Không; overhead và loại công việc quyết định hiệu năng. |
| “`parallel()` chạy ngay các bước `filter`/`map`.” | Không; pipeline vẫn lazy cho đến terminal operation. |
| “`isParallel() == true` chứng minh đã dùng nhiều thread.” | Không; đó là trạng thái cấu hình, không bảo đảm số worker thực tế. |
| “`parallel()` tạo ra một Future.” | Không; terminal operation thông thường vẫn trả kết quả khi hoàn tất. |
| “`forEach` trên parallel stream luôn giữ thứ tự List.” | Không; nếu cần thứ tự hành động, dùng `forEachOrdered` và chấp nhận chi phí. |
| “`collect(toList())` trên parallel stream làm danh sách bị đảo.” | Với nguồn có encounter order, collector phù hợp vẫn giữ thứ tự phần tử. |
| “Chỉ cần `AtomicLong` là tối ưu nhất để tính tổng.” | Đúng về đồng bộ không đồng nghĩa tối ưu; `sum` hoặc `reduce` thường phù hợp hơn. |
| “`reduce` có thể dùng bất kỳ phép toán hai ngôi.” | Accumulator phải kết hợp nhóm, identity phải hợp lệ. |
| “Bật `parallel()` cho `Files.lines` thì khỏi cần đóng file.” | Không; tài nguyên I/O vẫn cần quản lý rõ ràng. |
| “`parallel()` trước và `sequential()` sau là hai giai đoạn khác nhau.” | Không; chúng điều khiển chế độ của toàn pipeline, không tạo ranh giới pha xử lý. |

## 11. Bài tập thực hành có đáp án

### Bài 1. Hai cách bật chế độ song song

Cho `List<Integer> numbers = Arrays.asList(1, 2, 3, 4)`. Viết hai pipeline tính tổng bằng cách dùng `parallelStream()` và `stream().parallel()`.

```java
int a = numbers.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();

int b = numbers.stream()
        .parallel()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(a); // 10
System.out.println(b); // 10
```

**Đáp án:** Hai pipeline đều cấu hình xử lý song song và trả tổng `10`. Với bốn số, không khẳng định song song nhanh hơn.

### Bài 2. Chế độ cuối cùng

```java
Stream<Integer> s = Stream.of(1, 2, 3)
        .parallel()
        .sequential()
        .parallel();
```

**Đáp án:** `s.isParallel()` là `true`. Nếu gọi thêm `s.sequential()` trước terminal operation, chế độ sẽ là tuần tự. Việc đổi trạng thái không tạo nhiều pha thực thi độc lập.

### Bài 3. Nhận diện data race

```java
List<Integer> result = new java.util.ArrayList<>();
java.util.stream.IntStream.range(0, 1000)
        .parallel()
        .forEach(result::add);
```

**Đáp án:** Sai vì `ArrayList` bị cập nhật đồng thời mà không an toàn luồng. Sửa bằng `boxed().collect(Collectors.toList())` để framework quản lý kết quả.

### Bài 4. Thứ tự có được giữ không?

```java
java.util.stream.IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(System.out::print);
```

**Đáp án:** In `12345`. Với `forEach(System.out::print)`, thứ tự in không được bảo đảm dù nguồn là dãy có encounter order.

### Bài 5. Phép reduce nào sai?

```java
int result = java.util.stream.IntStream.of(10, 5, 2)
        .parallel()
        .reduce((a, b) -> a - b)
        .orElse(0);
```

**Đáp án:** Phép trừ không có tính kết hợp nhóm: `(10 - 5) - 2 = 3` khác `10 - (5 - 2) = 7`. Không dùng làm reduction khi cách phân hoạch có thể thay đổi.

### Bài 6. Chọn nguồn có khả năng chia

Muốn tính tổng các số từ 1 đến 1.000.000, nên bắt đầu với `LongStream.rangeClosed(1, 1_000_000)` hay `Stream.iterate(1L, n -> n + 1).limit(1_000_000)` nếu đánh giá xử lý song song?

**Đáp án:** `LongStream.rangeClosed` diễn đạt khoảng số trực tiếp, tránh boxing và thường dễ chia cho các worker. Sau đó vẫn cần đo để quyết định có nên gọi `parallel()`.

### Bài 7. Chọn terminal operation phù hợp

Một danh sách có thứ tự chứa các yêu cầu. Bạn chỉ cần biết **có yêu cầu quá hạn hay không**, không cần duyệt mọi yêu cầu để in thông tin. Nên dùng `forEach` kết hợp biến boolean ngoài hay `anyMatch`?

**Đáp án:** Dùng `requests.parallelStream().anyMatch(Request::isOverdue)` nếu predicate thuần và việc kiểm tra độc lập. `anyMatch` có thể kết thúc sớm, không cần biến mutable ngoài. Đo hiệu năng và cân nhắc chi phí đồng thời trước khi giữ `parallelStream()`.

## 12. Checklist trước khi bật parallel()

Trước khi thay `stream()` bằng `parallelStream()` hoặc thêm `parallel()`, hãy kiểm tra:

1. **Đúng bài toán?** Mỗi phần tử có thể xử lý độc lập không, hay cần trạng thái của phần tử trước?
2. **Nguồn chia tốt không?** Mảng, danh sách, range, hay một nguồn tuần tự khó tách hoặc I/O?
3. **Lambda có thuần không?** Có sửa collection nguồn, biến chung, log nghiệp vụ hay gọi API cần tuần tự không?
4. **Phép kết hợp có đúng không?** Accumulator kết hợp nhóm, identity hợp lệ, collector có combiner và characteristics đúng?
5. **Cần encounter order không?** Có `findFirst`, `limit`, `sorted`, `distinct` hoặc `forEachOrdered` làm tăng chi phí?
6. **Có giới hạn tài nguyên không?** Số worker, I/O, memory, file handles, blocking và tác vụ khác trong ứng dụng?
7. **Đã kiểm tra độ chính xác chưa?** Tràn `int`/`long`, sai số `double` hay yêu cầu tiền tệ?
8. **Đã benchmark đúng chưa?** Kết quả tuần tự và song song có tương đương, hiệu năng có cải thiện đáng kể với dữ liệu thật?

**Ghi nhớ:** `Collection.parallelStream()` và `BaseStream.parallel()` là hai cách đưa pipeline vào **chế độ song song**, chứ không phải lệnh tự động tăng tốc hoặc một cơ chế xử lý bất đồng bộ. Chương trình vẫn phải tuân thủ hợp đồng Stream về encounter order, tính độc lập của lambda, tính kết hợp của reduction và vòng đời tài nguyên. Hãy chọn nguồn chia được, dùng phép tổng hợp phù hợp, tránh trạng thái chia sẻ và chỉ giữ chế độ song song khi phép đo thực tế chứng minh lợi ích.
