# Trạng thái dùng chung, thread confinement và an toàn luồng

Khi đổi một pipeline Java Stream API từ `stream()` sang `parallelStream()`, Java có thể xử lý các phần tử trong nhiều tác vụ đồng thời. Nếu lambda chỉ đọc dữ liệu bất biến và trả về giá trị mới, chương trình thường vẫn dễ hiểu. Nhưng nếu lambda **ghi vào một `ArrayList`, `HashMap`, bộ đếm hoặc đối tượng dùng chung**, kết quả có thể thiếu, trùng, sai thứ tự hoặc phụ thuộc lịch chạy của các luồng.

Bài học thuộc chương **Ngữ nghĩa xử lý song song** của mô-đun **JAVA_STREAM_API**. Mục tiêu là hiểu ba ý tưởng liên quan nhưng không đồng nhất: **shared mutable state** (trạng thái có thể thay đổi được chia sẻ), **thread confinement** (giới hạn quyền truy cập trạng thái trong một phạm vi thực thi) và **thread safety** (tính đúng khi có truy cập đồng thời). Chúng ta sẽ vận dụng các quy tắc này vào `filter`, `map`, `reduce`, `collect`, `groupingBy`, collector tùy chỉnh, `Spliterator`, nguồn I/O, xử lý song song và đánh giá hiệu năng.

## 1. Vì sao pipeline tuần tự có vẻ đúng nhưng song song lại sai?

Xét một danh sách số nguyên, cần lấy các số chẵn rồi trả về một danh sách mới.

Cách viết nguy hiểm:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> result = new ArrayList<>();

IntStream.range(0, 10_000)
    .parallel()
    .filter(n -> n % 2 == 0)
    .forEach(result::add); // Không an toàn!

System.out.println(result.size());
```

Về toán học, có **5.000** số chẵn trong khoảng `[0, 10_000)`. Nhưng `ArrayList.add` không được thiết kế để nhiều luồng cập nhật đồng thời trên cùng một danh sách. Việc ghi vào mảng nội bộ và cập nhật số lượng phần tử có thể tranh chấp, khiến kết quả không đáng tin cậy; lỗi cũng có thể không xuất hiện ở mọi lần chạy.

Cách sửa bằng cơ chế thu thập của Stream:

```java
List<Integer> evenNumbers = IntStream.range(0, 10_000)
    .parallel()
    .filter(n -> n % 2 == 0)
    .boxed()
    .toList();

System.out.println(evenNumbers.size()); // 5000
```

Pipeline này giao việc quản lý kết quả cho `toList()`. Với nguồn có thứ tự như `IntStream.range`, kết quả `toList()` giữ thứ tự gặp; danh sách kết quả không thể chỉnh sửa bằng `add`/`remove`. Ta không cần tự điều phối nhiều lời gọi `add` vào một `ArrayList` toàn cục.

**Nguyên tắc đầu tiên:** Hãy mô tả **kết quả cần nhận** bằng `reduce` hoặc `collect`, thay vì biến các lambda thành một vòng lặp cập nhật trạng thái bên ngoài.

## 2. Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Shared mutable state** | Có từ hai tác vụ trở lên có thể truy cập cùng một đối tượng/trường và ít nhất một tác vụ có thể ghi | Nhiều lambda gọi `sharedList.add(...)` |
| **Thread confinement** | Trạng thái chỉ được một luồng hoặc một phạm vi tác vụ sở hữu tại một thời điểm, không bị nhiều tác vụ sửa đồng thời | Container tích lũy riêng của một nhánh `collect` |
| **Thread safety** | Các thao tác trên trạng thái duy trì hợp đồng đúng khi nhiều luồng có thể truy cập đồng thời | `ConcurrentHashMap` với các phương thức cập nhật phù hợp |

**Thread-safe không có nghĩa toàn bộ thuật toán đúng.** Ví dụ, `AtomicInteger.incrementAndGet()` bảo đảm một phép tăng đơn lẻ là nguyên tử, nhưng không bảo đảm lambda sẽ được gọi đúng một lần cho mỗi phần tử đầu vào; các thao tác Stream có thể dừng sớm hoặc bỏ qua công việc không cần thiết.

**Thread confinement cũng không đồng nghĩa một đối tượng phải gắn mãi với cùng một Java thread.** Với collector không concurrent, trạng thái tích lũy được quản lý sao cho không phải chịu các lời gọi accumulator đồng thời trên cùng container. Khi kết hợp, container có thể được chuyển qua các tác vụ theo cách do framework quản lý. Điều cần giữ là **không có quyền sở hữu ghi đồng thời không được bảo vệ**, chứ không phải ghi nhớ thread ID.

### Sơ đồ trực quan

```text
Sai: trạng thái dùng chung không đồng bộ

 task A ---- add ----\
 task B ---- add -----+----> ArrayList dùng chung (race)
 task C ---- add ----/

Đúng: trạng thái tích lũy thuộc các phần xử lý

 task A --> container A --\
                           +--> combiner --> kết quả
 task B --> container B --/
```

Trong cách thứ hai, `supplier`, `accumulator` và `combiner` thể hiện ranh giới quản lý trạng thái. Đây là lý do một collector có thể sử dụng container mutable bên trong mà không yêu cầu container đó tự nó là concurrent.

## 3. Vì sao `ArrayList` và `HashMap` chia sẻ dễ tạo data race?

Một **data race** xuất hiện khi các tác vụ truy cập một trạng thái thông thường mà không có cơ chế đồng bộ phù hợp, trong đó có ghi. Hệ quả không chỉ là “mất một lần tăng”:

- Một phần cập nhật có thể ghi đè cập nhật khác.
- Cấu trúc nội bộ có thể ở trạng thái không nhất quán trong lúc một tác vụ khác đang đọc/ghi.
- Thứ tự quan sát và khả năng nhìn thấy giá trị giữa các luồng có thể khác mong đợi.
- Kết quả có thể thay đổi giữa các lần chạy dù đầu vào giống nhau.

Ví dụ đếm theo khu vực bằng `HashMap` ngoài pipeline:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Long> totals = new HashMap<>();

orders.parallelStream().forEach(order ->
    totals.merge(order.region(), order.amountVnd(), Long::sum)
); // Sai: HashMap không an toàn cho các cập nhật đồng thời.
```

Ngay cả khi mỗi phần tử chỉ có một vùng, hai tác vụ vẫn có thể cập nhật cùng khóa hoặc gây tranh chấp cấu trúc Map. Việc `Map.merge` là một phương thức tiện lợi **không biến `HashMap` thành concurrent Map**.

Cách viết theo ý định tổng hợp:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> totalsByRegion = orders.parallelStream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

`groupingBy` kết hợp với `summingLong` để framework quản lý bộ tích lũy và cách hợp nhất các kết quả từng phần.

## 4. Yêu cầu đối với lambda: non-interfering và stateless

Các hàm truyền cho nhiều thao tác Stream như `filter`, `map`, `mapToLong` phải tuân thủ những điều kiện quan trọng:

- **Non-interfering:** không can thiệp vào nguồn đang được Stream duyệt, trừ trường hợp nguồn được thiết kế hỗ trợ can thiệp đồng thời theo hợp đồng.
- **Stateless:** kết quả không phụ thuộc vào trạng thái có thể thay đổi trong quá trình thực thi pipeline.

Lambda phù hợp:

```java
List<String> names = List.of("An", "Bình", "Chi");

List<Integer> lengths = names.parallelStream()
    .filter(name -> !name.isBlank())
    .map(String::length)
    .toList();

System.out.println(lengths); // [2, 4, 3]
```

`String::length` chỉ đọc đối tượng đầu vào và trả về một số; `filter` không sửa nguồn. Do đó, các thao tác có thể được đánh giá mà không cần cập nhật biến chung.

Lambda không phù hợp:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

source.parallelStream()
    .map(n -> {
        source.add(n * 10); // Can thiệp chính collection đang duyệt!
        return n * n;
    })
    .toList();
```

Đoạn trên có thể gây `ConcurrentModificationException` hoặc hành vi không được bảo đảm, kể cả trước khi bàn tới tính đúng của kết quả. Không sửa cấu trúc nguồn được duyệt trong các behavioral functions thông thường.

### 4.1. Đối tượng đầu vào cũng có thể bị chia sẻ

Ngay cả khi `List` nguồn không đổi, từng phần tử trong danh sách có thể là **đối tượng mutable**, và nhiều mục trong nguồn có thể cùng tham chiếu tới một đối tượng. Khi lambda sửa phần tử, các tác vụ có thể ghi vào cùng đối tượng đó.

```java
final class Counter {
    int value;
}

Counter shared = new Counter();
List<Counter> input = List.of(shared, shared);

input.parallelStream().forEach(counter -> counter.value++);
```

Mỗi phần tử ở đây trỏ đến **cùng Counter**. Phép `value++` không nguyên tử; việc nguồn là `List.of(...)` không làm đối tượng `Counter` bất biến. Muốn xử lý song song an toàn, hãy ưu tiên xây **giá trị kết quả mới** hoặc áp dụng cơ chế đồng bộ/giới hạn quyền sở hữu đúng với mô hình dữ liệu.

## 5. Shared mutable accumulator và điều gì làm `reduce` sai

`reduce(identity, accumulator)` được thiết kế cho một phép kết hợp có **identity hợp lệ**, **tính kết hợp** (*associativity*) và không dựa vào side effect bên ngoài.

Ví dụ an toàn:

```java
import java.util.stream.LongStream;

long sum = LongStream.rangeClosed(1, 1_000)
    .parallel()
    .reduce(0L, Long::sum);

System.out.println(sum); // 500500
```

`Long::sum` kết hợp hai giá trị và trả về một giá trị `long`; nó không sửa biến dùng chung. Với miền số trong ví dụ, tổng không tràn. Tuy nhiên, `parallel()` không làm kiểu `long` miễn nhiễm tràn số, và phép cộng `double` có thể khác ở chữ số cuối do làm tròn.

Ví dụ sai về side effect:

```java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong runningTotal = new AtomicLong();

long reduced = LongStream.rangeClosed(1, 1_000)
    .parallel()
    .reduce(0L, (left, right) -> {
        runningTotal.addAndGet(right); // Side effect bên ngoài reduce!
        return left + right;
    });
```

`runningTotal` là thread-safe ở mức cập nhật đơn, nhưng chương trình đang duy trì **hai kết quả** với ngữ nghĩa khác nhau. Trong giảm song song, accumulator có thể nhận kết quả từng phần chứ không chỉ nhận từng phần tử nguồn, nên `runningTotal` không có hợp đồng tương đương với phép tổng. Cách đúng là **dùng chính giá trị `reduced` trả về** và loại side effect.

### 5.1. Tính kết hợp quan trọng hơn thứ tự tác vụ

Phép trừ không kết hợp:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Vì vậy không nên coi `reduce(0, (a, b) -> a - b)` là một phép tổng hợp song song hợp lệ. Thay đổi cách chia và gộp có thể làm kết quả khác nhau. Các thuật toán phụ thuộc trạng thái trước đó hoặc thứ tự từng bước có thể phù hợp hơn với vòng lặp tuần tự hoặc một cấu trúc xử lý trạng thái chuyên dụng.

## 6. Thread confinement qua `collect`: mutable bên trong, kết quả đúng

Collector không concurrent có thể sử dụng một `ArrayList` mutable làm trạng thái tích lũy vì framework quản lý việc tạo container và kết hợp. Đây là ví dụ cụ thể cho **confinement theo phạm vi tích lũy**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

record Product(String sku, long priceVnd) {}

Collector<Product, ArrayList<String>, List<String>> skuCollector =
    Collector.of(
        ArrayList::new,                      // supplier: container riêng
        (list, product) -> list.add(product.sku()),
        (left, right) -> {                   // combiner: gộp hai container
            left.addAll(right);
            return left;
        },
        List::copyOf                         // finisher: kết quả không sửa được
    );

List<Product> products = List.of(
    new Product("P-01", 100_000L),
    new Product("P-02",  60_000L),
    new Product("P-03",  80_000L)
);

List<String> skus = products.parallelStream()
    .collect(skuCollector);

System.out.println(skus); // [P-01, P-02, P-03]
```

Mặc dù `ArrayList` không thread-safe để nhiều luồng gọi `add` đồng thời, collector trên **không khai báo `CONCURRENT`** và dựa vào hợp đồng collector để các container tạm thời không bị tích lũy đồng thời theo cách nguy hiểm. Combiner gộp các container và finisher tạo bản sao kết quả.

Với ví dụ chỉ lấy SKU, có thể viết ngắn và rõ hơn bằng collector có sẵn:

```java
List<String> skus = products.parallelStream()
    .map(Product::sku)
    .toList();
```

**Điều cần học:** Không phải mọi trạng thái mutable đều sai. Trạng thái mutable **do framework sở hữu, có ranh giới rõ, kết hợp được đúng cách** là một mô hình hợp lệ. Trạng thái mutable **bên ngoài pipeline được nhiều tác vụ sửa trực tiếp** mới là nguồn lỗi thường gặp.

### 6.1. Vai trò của bốn thành phần Collector

| Thành phần | Ý nghĩa trong song song | Rủi ro khi viết sai |
| --- | --- | --- |
| `supplier` | Tạo container khởi đầu; nhiều container có thể được tạo | Trả về một singleton mutable dùng chung |
| `accumulator` | Thêm một phần tử vào container được giao | Ghi đồng thời vào container khác hoặc biến ngoài |
| `combiner` | Hợp nhất các kết quả từng phần | Bỏ sót phần tử, gộp hai lần hoặc sai thứ tự |
| `finisher` | Chuyển container thành kiểu kết quả cuối | Làm lộ tham chiếu mutable khi kết quả cần bất biến |

Không đặt phụ phí cố định, giá trị đếm khởi đầu khác 0 hoặc dữ liệu ngoại lai vào supplier một cách tùy tiện: trong pipeline song song, container có thể được tạo nhiều lần, khiến giá trị khởi đầu bị tính lặp lại.

## 7. `groupingBy` và `groupingByConcurrent`: cùng mục tiêu, hợp đồng khác nhau

Đếm và tính tổng theo vùng là ví dụ thường gặp của trạng thái tích lũy theo nhóm.

```java
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

Map<String, Long> grouped = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));

ConcurrentMap<String, Long> concurrentGrouped = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

| Collector | Cách nhìn về trạng thái | Thứ tự |
| --- | --- | --- |
| `groupingBy` | Có thể tạo nhiều Map/container từng phần rồi ghép | Không mặc định bảo đảm thứ tự duyệt khóa Map; downstream có thể cần giữ thứ tự giá trị |
| `groupingByConcurrent` | Là collector `CONCURRENT` và `UNORDERED`; hỗ trợ tích lũy đồng thời vào `ConcurrentMap` khi phù hợp | Không duy trì encounter order như một yêu cầu kết quả |

Một điểm dễ nhầm: `Collectors.summingLong(...)` hoặc `Collectors.toList()` **không phải concurrent collector độc lập**. Nhưng khi làm downstream của `groupingByConcurrent`, implementation phải phối hợp các lần tích lũy cần thiết để bảo đảm hợp đồng của collector kết hợp; không được tự suy rằng downstream sẽ bị gọi đồng thời không bảo vệ trên cùng một `ArrayList`.

Tuy nhiên, không vì thế mà thay toàn bộ `groupingBy` bằng `groupingByConcurrent`. Nếu dữ liệu tập trung vào rất ít khóa, contention có thể cao; nếu thứ tự phần tử trong từng nhóm có ý nghĩa, collector unordered có thể không phù hợp.

### 7.1. `Spliterator.CONCURRENT` khác `Collector.Characteristics.CONCURRENT`

- `Spliterator.CONCURRENT` nói rằng **nguồn** hỗ trợ sửa đổi đồng thời trong khi duyệt theo một hợp đồng nhất định.
- `Collector.Characteristics.CONCURRENT` nói rằng **bộ tích lũy** có thể được gọi đồng thời trên **cùng container kết quả** theo hợp đồng của collector.

Hai cờ thuộc hai lớp trách nhiệm khác nhau. Một nguồn concurrent không làm `ArrayList` dùng chung trong `forEach` trở nên an toàn; một collector concurrent cũng không tự bảo đảm mọi nguồn tùy chỉnh có thể bị sửa trong lúc duyệt.

## 8. Có nên dùng `AtomicInteger`, `LongAdder` hoặc khóa?

Các primitive đồng bộ hữu ích khi bài toán **thực sự cần trạng thái dùng chung**. Nhưng trong pipeline Stream, chúng thường không phải lựa chọn đầu tiên cho phép đếm/tổng.

### 8.1. `AtomicInteger` và `AtomicLong`

`AtomicInteger.incrementAndGet()` là phép tăng nguyên tử. Ví dụ sau không có data race ở phép tăng:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger counter = new AtomicInteger();

IntStream.range(0, 1_000)
    .parallel()
    .forEach(n -> counter.incrementAndGet());

System.out.println(counter.get()); // 1000
```

Trong ví dụ đơn giản, terminal `forEach` xử lý từng phần tử và cập nhật đồng bộ. Nhưng nếu mục tiêu **chỉ là đếm**, code gọn hơn:

```java
long count = IntStream.range(0, 1_000)
    .parallel()
    .count();

System.out.println(count); // 1000
```

`AtomicInteger` giải quyết **atomicity của một thao tác**, không tự bảo đảm toàn bộ nghiệp vụ. Đặc biệt, khi đồng thời cập nhật nhiều trường (ví dụ `count` và `total`), hai `AtomicLong` riêng lẻ không tạo ra một **snapshot nhất quán** của cả hai trường nếu người đọc quan sát trong lúc cập nhật.

### 8.2. `LongAdder`: giảm contention không đồng nghĩa thay thế Collector

`LongAdder` hữu ích cho bộ đếm chịu nhiều cập nhật đồng thời. Ví dụ:

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder processed = new LongAdder();

orders.parallelStream().forEach(order -> {
    // Giả sử có tác vụ xử lý thực sự cần bộ đếm telemetry:
    processed.increment();
});

System.out.println(processed.sum());
```

`LongAdder.sum()` không phải snapshot nguyên tử trong khi các luồng vẫn đang cập nhật. Sau khi một terminal operation đồng bộ hoàn tất, có thể đọc kết quả cho mục đích quan sát; nhưng với các thống kê nghiệp vụ trực tiếp từ Stream, `count()` hoặc collector tương ứng dễ kiểm chứng hơn.

Một bộ đếm telemetry là khác biệt về mục đích so với **sản phẩm đầu ra của pipeline**. Đừng dựa vào bộ đếm dùng chung để quyết định logic phê duyệt khi kết quả có thể mô tả thuần bằng Stream.

### 8.3. `Collections.synchronizedList`

Một danh sách có đồng bộ có thể khiến lời gọi `add` riêng lẻ an toàn hơn:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<Integer> synchronizedResult =
    Collections.synchronizedList(new ArrayList<>());

IntStream.range(0, 1_000)
    .parallel()
    .forEach(synchronizedResult::add);

System.out.println(synchronizedResult.size()); // 1000
```

Nhưng **thứ tự phần tử trong danh sách không còn đồng nghĩa encounter order**: những tác vụ xử lý các chỉ số nhỏ hơn có thể gọi `add` sau các tác vụ khác. Ngoài ra, các thao tác phối hợp như vừa kiểm tra vừa thêm có thể cần đồng bộ bổ sung, và mọi luồng cạnh tranh cùng khóa sẽ tăng chi phí.

Nếu cần `List<Integer>` theo encounter order, dùng `boxed().toList()` hoặc collector có sẵn; chỉ dùng danh sách đồng bộ ngoài pipeline khi có yêu cầu cụ thể không biểu diễn tốt bằng phép thu thập.

## 9. `ThreadLocal`: không phải phép tổng hợp dữ liệu

`ThreadLocal<T>` cung cấp một giá trị riêng theo **luồng thực thi**. Nó có ích trong một số ngữ cảnh quản lý trạng thái gắn với từng thread, nhưng rất dễ bị hiểu sai khi áp dụng vào parallel Stream.

Ví dụ tư duy sai:

```java
import java.util.concurrent.atomic.AtomicInteger;

ThreadLocal<Integer> localCount = ThreadLocal.withInitial(() -> 0);

orders.parallelStream().forEach(order ->
    localCount.set(localCount.get() + 1)
);

// localCount.get() ở thread gọi phía ngoài KHÔNG phải tổng mọi thread.
System.out.println(localCount.get());
```

Mỗi worker thread có một giá trị riêng. `ThreadLocal` **không có cơ chế tự ghép các giá trị** thành tổng cuối; thậm chí các tác vụ khác nhau có thể được lập lịch lên cùng một thread theo cách không do ứng dụng kiểm soát.

Còn một rủi ro vòng đời: các luồng thuộc pool có thể được **tái sử dụng cho công việc khác**. Nếu trạng thái `ThreadLocal` bị giữ lại không đúng cách, nó có thể rò rỉ dữ liệu hoặc ảnh hưởng tác vụ tiếp theo. Khi thật sự phải dùng `ThreadLocal`, hãy xác định điểm thiết lập và xóa bằng `remove()` trong `finally`, song tránh lạm dụng như phương tiện truyền dữ liệu giữa các giai đoạn của Stream.

Một phương án phù hợp hơn để tổng hợp dữ liệu là **collector có trạng thái tách biệt theo phạm vi tích lũy**, không phải đếm theo mã thread. Collector biết cách tạo container, kết hợp và hoàn tất kết quả; `ThreadLocal` không thay thế các hợp đồng đó.

## 10. `forEach`, `forEachOrdered` và các bảo đảm về thứ tự

Nguồn có encounter order không có nghĩa mọi side effect đều chạy theo thứ tự đó khi song song.

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 5)
    .parallel()
    .forEach(System.out::print);

// Có thể in các chữ số theo thứ tự khác 12345.
```

`forEach` cố ý không bảo đảm thứ tự xử lý phần tử. Nếu cần thực thi action theo encounter order:

```java
IntStream.rangeClosed(1, 5)
    .parallel()
    .forEachOrdered(System.out::print);

// In 12345 đối với nguồn có thứ tự.
```

`forEachOrdered` bảo đảm các action được thực hiện theo encounter order của Stream có thứ tự, và action xử lý một phần tử xảy ra trước action phần tử kế tiếp theo ngữ nghĩa phương thức. Nhưng **không bảo đảm mọi action chạy trên cùng một thread**; nó cũng không làm nguồn mutable hoặc các side effect nằm trước action trở nên thread-safe.

Điều quan trọng hơn: nếu mục tiêu là **tạo danh sách có thứ tự**, đừng dùng `forEachOrdered` để thêm phần tử vào container ngoài khi `toList()` đã giải quyết trực tiếp bài toán. `forEachOrdered` có thể cần thêm điều phối và giảm lợi ích song song khi thực thi side effect bắt buộc tuần tự.

### 10.1. `findAny` khác `findFirst`

`findAny()` có thể trả một phần tử bất kỳ; điều này đặc biệt hữu ích khi không cần thứ tự và muốn cho phép tối ưu song song. `findFirst()` phải tuân thủ encounter order nếu nguồn có thứ tự, nên có thể có thêm chi phí phối hợp.

Không được dùng kết quả `findAny()` để khẳng định “bản ghi đầu tiên” của tập dữ liệu có thứ tự.

## 11. Short-circuit và tối ưu Stream làm side effect khó dự đoán

Một số thao tác không cần duyệt hết nguồn:

- `anyMatch` dừng khi tìm được một phần tử thỏa predicate.
- `allMatch` dừng khi có phần tử không thỏa.
- `findFirst` hoặc `findAny` dừng khi đã có phần tử đáp ứng điều kiện.
- `limit(n)` có thể chỉ chuyển tối đa `n` phần tử cho downstream.

Ngoài ra, implementation được phép tối ưu các giai đoạn trung gian khi kết quả terminal operation vẫn đúng. Ví dụ `count()` trên một nguồn đã biết kích thước có thể **không cần gọi `peek`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger visits = new AtomicInteger();

long size = IntStream.range(0, 1_000)
    .parallel()
    .peek(n -> visits.incrementAndGet())
    .count();

System.out.println(size); // 1000

// Không bảo đảm visits == 1000; peek có thể không được gọi.
```

`AtomicInteger` làm bộ đếm an toàn khi `peek` được gọi, nhưng **không buộc Stream phải gọi peek**. `peek` thích hợp để quan sát/debug trong giới hạn phù hợp, không phải để thực hiện bước nghiệp vụ bắt buộc.

Tương tự, một `Predicate` có tác dụng phụ có thể được gọi với số lần và thứ tự khác nhau trên Stream song song. Nếu cần đếm thực sự có bao nhiêu bản ghi thỏa điều kiện, hãy dùng `filter(predicate).count()` với predicate thuần.

## 12. Ví dụ Java 17 hoàn chỉnh: báo cáo đơn hàng an toàn khi song song

Ví dụ dưới đây sử dụng `record` và các API Java 17+. Nó minh họa ba kết quả độc lập được tạo **không sửa trạng thái ngoài pipeline**:

1. Tổng doanh thu đã thanh toán bằng `mapToLong(...).sum()`.
2. Tổng doanh thu theo khu vực bằng `groupingBy(..., summingLong(...))`.
3. Danh sách mã đơn đã thanh toán theo encounter order bằng `map(...).toList()`.

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ParallelStreamStateDemo {

    record Order(String id, String region, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "Bắc", 120_000L, true),
            new Order("O-02", "Nam",  60_000L, false),
            new Order("O-03", "Bắc",  80_000L, true),
            new Order("O-04", "Nam", 200_000L, true),
            new Order("O-05", "Trung", 50_000L, true)
        );

        long revenue = orders.parallelStream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .sum();

        Map<String, Long> byRegion = orders.parallelStream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.summingLong(Order::amountVnd)
            ));

        ConcurrentMap<String, Long> concurrentByRegion =
            orders.parallelStream()
                .filter(Order::paid)
                .collect(Collectors.groupingByConcurrent(
                    Order::region,
                    Collectors.summingLong(Order::amountVnd)
                ));

        List<String> paidIds = orders.parallelStream()
            .filter(Order::paid)
            .map(Order::id)
            .toList();

        long paidCount = orders.parallelStream()
            .filter(Order::paid)
            .count();

        System.out.println(revenue);              // 450000
        System.out.println(byRegion.get("Bắc"));   // 200000
        System.out.println(byRegion.get("Nam"));   // 200000
        System.out.println(byRegion.get("Trung")); // 50000
        System.out.println(concurrentByRegion.get("Bắc")); // 200000
        System.out.println(paidIds);              // [O-01, O-03, O-04, O-05]
        System.out.println(paidCount);            // 4
    }
}
```

Mỗi lời gọi `orders.parallelStream()` tạo **một Stream mới**. Không thể dùng lại Stream sau terminal operation. Trong ví dụ, `Order` có các trường bất biến theo cấu trúc record; các lambda chỉ đọc dữ liệu và tổng hợp. Không có `ArrayList` hoặc `HashMap` ngoài pipeline bị nhiều tác vụ sửa đồng thời.

Hai kết quả Map có cùng số tiền theo nhóm, nhưng **không có bảo đảm giống nhau về kiểu Map và thứ tự duyệt khóa**. Không dựa vào `Map.toString()` hay `keySet()` mặc định để kiểm tra thứ tự. `paidIds` giữ encounter order của nguồn `List`, vì `Stream.toList()` trả các phần tử theo thứ tự gặp nếu Stream có thứ tự.

**Giới hạn số học:** `summingLong` và `sum()` vẫn có thể tràn kiểu `long` nếu tổng vượt miền 64 bit. Khi cần tổng nguyên chính xác không bị giới hạn bởi `long`, chuyển sang `BigInteger` và giảm với `BigInteger::add`; xử lý song song không tự mở rộng miền giá trị.

## 13. Hiệu năng: tránh biến đồng bộ thành điểm nghẽn

Một pipeline có thể thread-safe nhưng chậm hơn xử lý tuần tự vì:

- Tạo tác vụ và chia nguồn qua `Spliterator` tốn chi phí.
- Nhiều tác vụ cập nhật cùng `AtomicLong`, `synchronizedList` hoặc cùng một khóa trong `ConcurrentHashMap` gây tranh chấp.
- `forEachOrdered` cần duy trì encounter order.
- `groupingBy` cần combiner để gộp các Map; `groupingByConcurrent` có thể tranh chấp các khóa nóng.
- Boxing từ `int` sang `Integer` có thể tăng chi phí khi không cần thiết.
- Nguồn I/O hoặc dữ liệu nhỏ không đủ công việc tính toán để bù overhead của song song.

Có thể dùng `IntStream`, `LongStream` và `DoubleStream` để tránh boxing khi bài toán thuần số học. Với nguồn tùy chỉnh, chất lượng `trySplit()` và các characteristic `SIZED`, `SUBSIZED`, `ORDERED` quyết định nhiều đến khả năng chia hiệu quả. Nhưng không vì thế mà tự viết Spliterator phức tạp khi nguồn chuẩn đã đủ.

### Cách đánh giá hiệu năng hợp lý

1. Trước hết kiểm chứng kết quả tuần tự và song song **bằng cùng dữ liệu và cùng quy tắc nghiệp vụ**.
2. Dùng dữ liệu đại diện, nhiều lần chạy và công cụ benchmark phù hợp như JMH.
3. Xem phân bố khóa nhóm, số phần tử, chi phí mapper/accumulator và tỷ lệ tác vụ chờ đồng bộ.
4. Đo cả thời gian, throughput, CPU, bộ nhớ và mức cấp phát khi cần.
5. Chỉ chọn song song nếu cải thiện đủ lớn và không làm phức tạp tính đúng hoặc việc vận hành.

**Thread safety là điều kiện cần, không phải bảo đảm về tốc độ.**

## 14. Trường hợp đặc biệt: nguồn concurrent, I/O và tài nguyên

Một số nguồn hỗ trợ đọc đồng thời hoặc cập nhật trong lúc duyệt theo hợp đồng riêng, chẳng hạn các cấu trúc concurrent collection. Nhưng đặc tính đó không chuyển thành giấy phép sửa nguồn tùy ý trong `map` hoặc `filter`.

Đối với nguồn từ `Files.lines(path)`, `Files.walk(path)` hoặc API giữ tài nguyên ngoài, trách nhiệm đóng vẫn thuộc bên sở hữu Stream/tài nguyên, **dù chạy tuần tự hay song song**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countErrors(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.parallel()
            .filter(line -> line.contains("ERROR"))
            .count();
    }
}
```

`count()` không tự thay `close()`; `try-with-resources` bảo đảm đóng tài nguyên khi rời khối, kể cả khi pipeline gặp lỗi. Không dùng xử lý song song chỉ vì tệp có nhiều dòng: I/O, chia nguồn, giải mã và tranh chấp có thể khiến nó chậm hơn.

Nếu nguồn là một `Spliterator` tự định nghĩa, cần xác định rõ nó có được chia an toàn không, các phần sau `trySplit()` có cùng tham chiếu mutable nào không và đặc tính `CONCURRENT`/`IMMUTABLE` có được khai báo chính xác không.

## 15. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| `parallelStream().forEach(sharedArrayList::add)` | Data race, thiếu/sai phần tử | `map(...).toList()` hoặc `collect(...)` |
| `parallelStream().forEach(n -> hashMap.merge(...))` | `HashMap` không an toàn khi cập nhật đồng thời | `groupingBy` hoặc `groupingByConcurrent` |
| Cho rằng `AtomicInteger` làm mọi lambda có side effect hợp lệ | Chỉ an toàn cho thao tác nguyên tử, không bảo đảm số lần lambda chạy | Dùng `count()`/`sum()`/collector đúng mục đích |
| Dùng `peek` để tăng bộ đếm bắt buộc | Stage có thể bị bỏ qua khi terminal operation được tối ưu | Không đặt logic nghiệp vụ vào `peek` |
| Dùng `ThreadLocal` để tính tổng từ các worker | Các giá trị không tự được hợp nhất; thread có thể tái sử dụng | Dùng collector với supplier/combiner |
| Dùng một `ArrayList` singleton trong supplier của collector | Nhiều nhánh chia sẻ cùng trạng thái, mất an toàn | Supplier trả container mới mỗi lần |
| Dùng `reduce` sửa một container mutable là identity chung | Vi phạm hợp đồng giảm và có thể chia sẻ giữa các tác vụ | Dùng phép kết hợp bất biến hoặc `collect` |
| Dùng phép trừ làm accumulator cho parallel reduce | Không kết hợp, phụ thuộc cách gom | Dùng phép kết hợp có tính kết hợp hoặc thuật toán khác |
| Giả định `forEach` giữ encounter order | Side effect có thứ tự bất định | Dùng `forEachOrdered` nếu bắt buộc làm action có thứ tự; ưu tiên `toList` |
| Giả định `forEachOrdered` buộc mọi action chạy cùng thread | Nhầm bảo đảm về thứ tự với thread affinity | Không gắn trạng thái với thread ID |
| Cho rằng `groupingByConcurrent` giữ thứ tự phần tử từng nhóm | Collector unordered | Chọn phương án giữ thứ tự nếu nghiệp vụ yêu cầu |
| Cho rằng nguồn có `Spliterator.CONCURRENT` làm collector tự an toàn | Nhầm hợp đồng nguồn và hợp đồng bộ tích lũy | Xem xét mỗi hợp đồng riêng |
| Cho rằng `parallel()` tăng tốc và sửa tràn số | Overhead có thể lớn; miền số không đổi | Đo hiệu năng, chọn kiểu số hợp lệ |
| Quên đóng nguồn I/O sau terminal operation | Rò rỉ tài nguyên | `try-with-resources` ở chủ sở hữu nguồn |
| Sửa đối tượng mutable được nhiều phần tử cùng tham chiếu | Data race dù collection nguồn bất biến | Biến đổi thành giá trị mới hoặc bảo vệ quyền sở hữu |

## 16. Bài tập thực hành

### Bài 1: Sửa shared mutable list

Cho một `ArrayList<Integer>` bên ngoài pipeline, mã dùng `IntStream.range(0, 100_000).parallel().forEach(list::add)`. Hãy viết lại thành `List<Integer>` bằng `boxed().toList()` và giải thích vì sao không cần `synchronizedList`.

### Bài 2: Đếm và tổng hợp theo vùng

Cho danh sách `Order(region, amountVnd, paid)`. Viết hai pipeline tạo `Map<String, Long>` tổng doanh thu đã thanh toán bằng `groupingBy` và `groupingByConcurrent`. So sánh kết quả các khóa, không so sánh thứ tự in Map.

### Bài 3: Khi nào dùng `AtomicInteger`?

Tạo hai chương trình đếm từ 0 đến 1 triệu: một chương trình dùng `AtomicInteger` trong `parallel().forEach`, một chương trình dùng `count()`. Nêu sự khác nhau giữa tính an toàn nguyên tử, ý định nghiệp vụ và chi phí tranh chấp.

### Bài 4: Bắt lỗi `peek`

Dùng `IntStream.range(0, 100).peek(...)` với bộ đếm Atomic và terminal `count()`. Có được giả định `peek` luôn chạy 100 lần không? Giải thích tại sao tối ưu được phép thay đổi số lần thực hiện stage trung gian.

### Bài 5: Collector có trạng thái nhưng an toàn

Viết `Collector<Product, ArrayList<String>, List<String>>` gồm supplier `ArrayList::new`, accumulator thêm SKU, combiner nối danh sách và finisher `List.copyOf`. Chạy tuần tự và song song trên nguồn có thứ tự; giải thích vì sao không cần `ArrayList` tự thread-safe trong thiết kế này.

### Bài 6: `ThreadLocal` không tự gộp

Mô tả một pipeline `parallelStream` sử dụng `ThreadLocal<Integer>` làm bộ đếm. Vì sao đọc `threadLocal.get()` tại thread gọi bên ngoài không cho tổng? Những rủi ro nào phát sinh khi worker thread được pool tái sử dụng?

### Bài 7: Thứ tự và hiệu năng

So sánh `forEach`, `forEachOrdered` và `toList` trên `IntStream.range(0, 100).parallel()`. Với mục tiêu xây một danh sách theo thứ tự tăng dần, cách nào trực tiếp và an toàn nhất? Khi nào `forEachOrdered` là lựa chọn cần thiết?

### Bài 8: Nguồn dữ liệu dùng chung

Cho một `List<Counter>` chứa hai vị trí tham chiếu cùng một đối tượng `Counter` mutable. Nếu mỗi tác vụ thực hiện `counter.value++`, kết quả có đáng tin không? Viết lại thành pipeline chỉ đọc giá trị và tổng hợp bằng `mapToInt(...).sum()`, nêu yêu cầu dữ liệu đầu vào phải ổn định trong lúc đọc.

### Bài 9: Tính đúng trước khi tối ưu

Tạo tập dữ liệu có rất nhiều đơn nhưng chỉ hai khóa nhóm. Dự đoán sự khác nhau giữa `groupingBy` và `groupingByConcurrent` về chi phí gộp Map và contention; thiết kế benchmark JMH thay vì đo một lần rồi kết luận.

## 17. Tự kiểm tra kiến thức

- Vì sao `ArrayList.add` hoặc `HashMap.merge` trên một container bên ngoài pipeline không an toàn với `parallelStream`?
- Khác nhau giữa data race, thread confinement và thread safety là gì?
- Tại sao trạng thái mutable bên trong collector không concurrent vẫn có thể dùng được khi xử lý song song?
- Vì sao Supplier của Collector không được trả lại một singleton mutable dùng chung?
- `AtomicInteger` có làm `peek` trở thành bước nghiệp vụ chắc chắn phải chạy không?
- `ThreadLocal` có tự tổng hợp dữ liệu của nhiều tác vụ thành một kết quả không?
- `forEachOrdered` bảo đảm điều gì và **không** bảo đảm điều gì về thread?
- Vì sao `groupingByConcurrent` không nhất thiết nhanh hơn `groupingBy` khi có ít khóa nhóm?
- `Spliterator.CONCURRENT` khác `Collector.Characteristics.CONCURRENT` ra sao?
- Khi nào một phép `reduce` có side effect có thể sai dù side effect dùng lớp atomic?
- Vì sao phải kiểm tra cả tính đúng, thứ tự, tài nguyên I/O và độ chính xác số học trước khi bật `parallel()`?

**Ghi nhớ:** Với parallel Stream, hãy **giữ các lambda xử lý phần tử stateless và non-interfering**, tránh ghi vào trạng thái mutable dùng chung và để **`reduce`/`collect` quản lý việc tổng hợp**. Thread confinement của các container tạm trong collector và thread safety của cấu trúc concurrent là hai cơ chế khác nhau; cả hai cần được dùng đúng hợp đồng. Các công cụ `AtomicInteger`, `LongAdder`, `ThreadLocal` và `forEachOrdered` không thay thế khả năng diễn đạt kết quả thuần của Stream, và không tự bảo đảm hiệu năng tốt hơn.
