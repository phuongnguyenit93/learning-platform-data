# Hiểu pipeline fusion, tính lười và chi phí tạo đối tượng

## 1. Vì sao cùng một phép xử lý lại có chi phí khác nhau?

Java Stream API cho phép mô tả cách xử lý dữ liệu bằng một **pipeline**: nguồn dữ liệu (*source*), các thao tác trung gian (*intermediate operations*) và một thao tác kết thúc (*terminal operation*). Cú pháp khai báo như `filter`, `map`, `reduce` và `collect` giúp tập trung vào kết quả cần tính. Tuy nhiên, muốn đánh giá hiệu năng và bộ nhớ, cần hiểu **pipeline thực sự chạy khi nào, duyệt phần tử ra sao và tạo ra những đối tượng nào**.

Ví dụ, với danh sách đơn hàng, yêu cầu “tính tổng giá trị đơn đã thanh toán” có thể viết bằng `filter(...).mapToLong(...).sum()`. Pipeline này thường chỉ cần một lượt đi qua các phần tử, không phải tạo một danh sách kết quả sau mỗi thao tác. Ngược lại, `sorted()` có thể phải giữ nhiều phần tử trong bộ nhớ trước khi chuyển kết quả sang bước tiếp theo. Cùng một bài toán, việc dùng `Stream<Long>` hay `LongStream` cũng ảnh hưởng đến khả năng phát sinh boxing.

Sau bài này, bạn sẽ phân biệt được:

- **Pipeline fusion**: các bước trung gian không giữ trạng thái thường được phối hợp trong một lượt duyệt.
- **Lazy evaluation (tính lười)**: việc xử lý phần tử được hoãn cho đến khi có thao tác kết thúc, và có thể dừng sớm.
- **Chi phí đối tượng**: chi phí dựng pipeline, boxing/unboxing, tạo đối tượng ứng dụng và lưu kết quả là những nguồn chi phí khác nhau.

> Phạm vi: các ví dụ dùng Java 17 trở lên để có `record`, `List.of()` và `Stream.toList()`. Các nguyên tắc chính về pipeline của Stream API cũng áp dụng cho nhiều phiên bản JDK trước đó; API cụ thể cần kiểm tra theo phiên bản đang sử dụng.

## 2. Pipeline fusion: một lượt duyệt, nhiều bước xử lý

Xét pipeline tuần tự:

```java
List<Integer> result = List.of(1, 2, 3, 4, 5, 6).stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10)
    .toList();

System.out.println(result); // [20, 40, 60]
```

Cách hình dung dễ gây hiểu nhầm là `filter()` tạo một danh sách `[2, 4, 6]`, sau đó `map()` lại duyệt danh sách đó để tạo `[20, 40, 60]`. Với pipeline tuần tự gồm các thao tác trung gian **không giữ trạng thái** (*stateless*), Stream thường đưa từng phần tử qua các bước nối tiếp nhau trong cùng lượt duyệt nguồn:

```text
Nguồn:  1 ─→ filter (loại)
        2 ─→ filter (giữ) ─→ map (20) ─→ kết quả
        3 ─→ filter (loại)
        4 ─→ filter (giữ) ─→ map (40) ─→ kết quả
        5 ─→ filter (loại)
        6 ─→ filter (giữ) ─→ map (60) ─→ kết quả
```

Đây là cách hiểu thực tế của **pipeline fusion**: Stream phối hợp các bước để không phải tạo một collection trung gian cho từng `filter()` hoặc `map()`. Trong một pipeline tuần tự đơn giản, một phần tử có thể đi qua `filter`, `map` rồi được terminal operation tiêu thụ trước khi phần tử tiếp theo được xử lý.

**Fusion không đồng nghĩa với “không tốn chi phí”.** Bản thân đối tượng Stream, các stage, lambda, cơ chế gọi hàm và kết quả cuối vẫn có chi phí tiềm năng. Đặc biệt, `map(x -> new Dto(...))` vẫn có thể tạo một DTO cho mỗi phần tử đi qua `map`, dù không tạo danh sách trung gian. JVM/JIT có thể tối ưu một số cấp phát trong điều kiện phù hợp, nhưng không nên mặc định chúng sẽ biến mất.

### Chứng minh thứ tự xử lý bằng log

Đoạn mã sau dùng log **chỉ để quan sát** thứ tự thực thi của pipeline tuần tự:

```java
OptionalInt first = IntStream.rangeClosed(1, 6)
    .filter(n -> {
        System.out.println("filter " + n);
        return n % 2 == 0;
    })
    .map(n -> {
        System.out.println("map " + n);
        return n * 10;
    })
    .findFirst();

System.out.println(first); // OptionalInt[20]
```

Thứ tự log trong ví dụ tuần tự là:

```text
filter 1
filter 2
map 2
OptionalInt[20]
```

Không có `map 4` hay `map 6`: `findFirst()` đã tìm được kết quả đầu tiên và có thể kết thúc pipeline sớm. Nếu Stream chạy song song, cách chia việc và thứ tự quan sát có thể khác; không dùng ví dụ log tuần tự này để suy luận thứ tự thực thi của `parallelStream()`.

## 3. Tính lười: mô tả trước, thực thi sau

`filter`, `map`, `flatMap`, `distinct`, `sorted` và nhiều thao tác trung gian trả về một Stream mới để nối pipeline. Chúng **không thực hiện việc duyệt và xử lý các phần tử ngay khi được khai báo**. Việc duyệt thường bắt đầu khi gọi terminal operation như `sum`, `count`, `findFirst`, `forEach`, `reduce`, `collect` hoặc `toList`.

```java
Stream<Integer> pipeline = Stream.of(1, 2, 3, 4)
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10);

System.out.println("Đã tạo pipeline");

List<Integer> numbers = pipeline.toList(); // Bắt đầu xử lý phần tử
System.out.println(numbers);                // [20, 40]
```

Khi tạo `pipeline`, chương trình vẫn cần tạo các cấu trúc biểu diễn pipeline và lấy nguồn dữ liệu. “Lười” ở đây nói đến **thời điểm xử lý phần tử**, không phải việc mọi thao tác đều miễn phí cho đến terminal operation.

Một Stream chỉ được dùng cho **một lần tiêu thụ**. Sau `toList()`, không gọi tiếp `sum()`, `count()` hoặc terminal operation khác trên cùng `pipeline`; hãy tạo pipeline mới từ nguồn nếu cần tính kết quả khác.

### Dừng sớm nhờ short-circuit

Một số terminal operation chỉ cần xử lý một phần dữ liệu:

| Thao tác | Điều kiện có thể dừng |
| --- | --- |
| `findFirst()` | Đã tìm thấy phần tử đầu tiên theo encounter order, nếu có thứ tự. |
| `findAny()` | Đã tìm thấy một phần tử; đặc biệt hữu ích khi không cần bảo toàn thứ tự. |
| `anyMatch(...)` | Đã gặp một phần tử thỏa điều kiện. |
| `allMatch(...)` | Đã gặp một phần tử không thỏa điều kiện. |
| `noneMatch(...)` | Đã gặp một phần tử thỏa điều kiện. |
| `limit(n)` | Đây là thao tác trung gian có thể chặn việc lấy thêm phần tử sau khi đủ `n` phần tử ở downstream, tùy pipeline. |

Ví dụ:

```java
boolean hasNegative = IntStream.of(5, 8, -3, 12, 20)
    .anyMatch(n -> n < 0);

System.out.println(hasNegative); // true
```

Với pipeline tuần tự và nguồn trên, `anyMatch()` có thể kết thúc khi gặp `-3`, không cần xét `12` và `20`. Trong pipeline song song, các phần việc đã được khởi chạy có thể xử lý thêm phần tử trước khi việc hủy lan tới chúng.

### Đừng dựa vào side effect của intermediate operation

Stream cho phép triển khai tối ưu mà **không nhất thiết phải gọi mọi hành vi được gắn vào thao tác trung gian**, nếu kết quả terminal operation vẫn được bảo toàn. Ví dụ với một nguồn đã biết kích thước:

```java
long count = List.of("a", "b", "c").stream()
    .map(s -> {
        System.out.println("map: " + s);
        return s.toUpperCase();
    })
    .count();

System.out.println(count); // 3
```

JDK có thể tính `count()` trực tiếp từ kích thước nguồn, bỏ qua việc thực thi `map()` vì phép biến đổi này không làm thay đổi số phần tử. Do đó, **không dùng `map`, `filter` hoặc `peek` để thực hiện nghiệp vụ bắt buộc có side effect** (ghi cơ sở dữ liệu, cập nhật biến dùng chung, gửi thông báo…). `peek` thích hợp để quan sát khi gỡ lỗi, nhưng cũng không đảm bảo được gọi với mọi phần tử.

## 4. Khi nào fusion bị giới hạn?

Không phải thao tác trung gian nào cũng có thể truyền ngay từng phần tử cho bước sau. Đặc biệt, các thao tác **giữ trạng thái** (*stateful*) có thể cần nhìn nhiều phần tử hoặc lưu trạng thái trước khi phát kết quả.

| Thao tác | Đặc tính khi thực thi | Hệ quả tiềm năng |
| --- | --- | --- |
| `filter`, `map`, `mapToInt`, `mapToLong` | Stateless; thường xử lý từng phần tử. | Thường không cần collection trung gian; lambda hoặc đối tượng tạo trong `map` vẫn có chi phí. |
| `flatMap` | Phát phần tử từ nhiều stream con. | Có chi phí tạo/đóng stream con hoặc cấu trúc liên quan. |
| `sorted()` | Phải biết thứ tự sắp xếp của các phần tử cần sắp. | Thường cần giữ toàn bộ đầu vào hữu hạn trước khi phát kết quả có thứ tự. |
| `distinct()` | Phải nhận diện phần tử đã gặp. | Có thể cần cấu trúc như tập hợp để ghi nhớ giá trị, tùy đặc tính nguồn và cách thực thi. |
| `limit(n)`, `skip(n)` | Có trạng thái về số phần tử; `limit` có thể dừng sớm. | Chi phí phụ thuộc encounter order, vị trí trong pipeline và việc chạy song song. |
| `collect(toList())`, `toList()` | Terminal operation tích lũy đầu ra. | Cần bộ nhớ cho collection kết quả; không làm xuất hiện collection sau *mỗi* bước trung gian. |
| `sum()`, `count()`, `reduce(...)` | Terminal operation tổng hợp. | Có thể không cần lưu mọi phần tử; chi phí phụ thuộc accumulator và cách thực thi. |

### Vị trí của `sorted()` và `limit()` thay đổi ý nghĩa

```java
List<Integer> smallestTwo = Stream.of(9, 2, 7, 1, 5)
    .sorted()
    .limit(2)
    .toList();
// [1, 2]: lấy 2 số nhỏ nhất trong toàn bộ nguồn

List<Integer> firstTwoSorted = Stream.of(9, 2, 7, 1, 5)
    .limit(2)
    .sorted()
    .toList();
// [2, 9]: chỉ sắp xếp 2 phần tử đầu nguồn
```

Đẩy `limit()` lên trước `sorted()` có thể giảm số phần tử cần giữ, **nhưng làm thay đổi kết quả**. Chỉ đổi thứ tự khi ngữ nghĩa nghiệp vụ cho phép. Tương tự, lọc dữ liệu trước `sorted()` thường giảm lượng cần sắp xếp nếu `filter()` không làm thay đổi điều kiện chọn kết quả.

Với nguồn vô hạn, `Stream.generate(...).sorted().findFirst()` có thể không kết thúc vì `sorted()` cần thu nhận toàn bộ dữ liệu trước khi chọn phần tử đầu tiên. Một giới hạn hữu hạn đặt **trước** `sorted()` có thể giúp pipeline kết thúc, miễn là phù hợp bài toán.

## 5. Các nguồn chi phí bộ nhớ và tạo đối tượng

Để tránh kết luận sai kiểu “Stream luôn tạo nhiều đối tượng” hoặc “fusion không tạo đối tượng”, hãy tách các nhóm chi phí:

1. **Thiết lập pipeline:** nguồn Stream, các stage, cơ chế xử lý và lambda/capture có thể cần cấp phát. Với tập dữ liệu nhỏ và thao tác rất đơn giản, chi phí này có thể đáng kể so với phần công việc thực tế.
2. **Tạo đối tượng cho từng phần tử:** `map(order -> new Summary(...))`, nối chuỗi, tạo `Optional`/collection con hoặc chuyển đổi dữ liệu có thể phát sinh đối tượng theo số phần tử đã được xử lý.
3. **Boxing/unboxing:** Stream tham chiếu `Stream<Integer>` hoặc `Stream<Long>` có thể tạo wrapper và tăng chi phí truy cập bộ nhớ so với `IntStream`, `LongStream`, `DoubleStream`.
4. **Lưu trạng thái và kết quả:** `sorted`, `distinct`, `groupingBy`, `toList` và một số collector có thể cần bộ nhớ tỷ lệ với số phần tử hoặc số nhóm.
5. **Áp lực GC và bộ nhớ tạm thời:** đối tượng tồn tại ngắn vẫn có thể gây áp lực thu gom rác; mức độ ảnh hưởng phụ thuộc workload và tối ưu của JVM.

### Tránh boxing khi làm việc chủ yếu với số

Giả sử có một loại đơn hàng:

```java
record Order(String code, boolean paid, long amount) {}

List<Order> orders = List.of(
    new Order("A01", true, 1_200_000L),
    new Order("A02", false, 400_000L),
    new Order("A03", true, 500_000L)
);

long revenue = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amount)
    .sum();

System.out.println(revenue); // 1700000
```

`mapToLong()` chuyển sang `LongStream`, nên các giá trị tiền ở giai đoạn tính tổng được biểu diễn bằng `long` nguyên thủy. So sánh với cách viết có thể phát sinh boxing:

```java
Long revenueBoxed = orders.stream()
    .filter(Order::paid)
    .map(Order::amount)        // Stream<Long>
    .reduce(0L, Long::sum);   // Có các bước boxing/unboxing
```

Hai cách cho cùng giá trị trong ví dụ, nhưng kiểu Stream tham chiếu tạo thêm cơ hội phát sinh wrapper. Thực tế JIT có thể loại bỏ một số cấp phát; **không suy ra chính xác số đối tượng chỉ bằng cách đếm lời gọi `map`**. Nếu dữ liệu đầu vào đã là `List<Long>`, các wrapper có sẵn trong danh sách vẫn tồn tại dù dùng `mapToLong(Long::longValue)`.

### Phân biệt kết quả vô hướng và danh sách DTO

```java
record Summary(String code, long amount) {}

List<Summary> summaries = orders.stream()
    .filter(Order::paid)
    .map(order -> new Summary(order.code(), order.amount()))
    .toList();
```

Ở đây fusion giúp tránh một danh sách trung gian chỉ gồm đơn đã thanh toán, nhưng `new Summary(...)` tạo các đối tượng kết quả và `toList()` lưu chúng để dùng về sau. Đó là **chi phí hợp lý nếu ứng dụng thật sự cần danh sách Summary**. Nếu chỉ cần tổng, `mapToLong(...).sum()` thường phù hợp hơn vì không cần giữ một DTO cho mỗi đơn.

`Stream.toList()` (có từ Java 16) trả về danh sách không cho sửa đổi bằng các thao tác như `add`/`remove`. Không nhầm với `Collectors.toList()`, vốn không cam kết cụ thể kiểu triển khai, tính thay đổi được hay các đặc tính khác của danh sách trả về.

### Ước lượng độ phức tạp, không đồng nhất với benchmark

Với `n` phần tử đầu vào, `k` phần tử sau lọc và `u` giá trị khác nhau, có thể dùng các ước lượng sau để thiết kế:

| Pipeline điển hình | Thời gian thường gặp | Bộ nhớ bổ sung đáng chú ý |
| --- | --- | --- |
| `filter(...).mapToLong(...).sum()` | `O(n)` | Thường `O(1)` cho phần tổng hợp trong thực thi tuần tự, ngoài hạ tầng pipeline. |
| `filter(...).map(...).toList()` | `O(n)` | `O(k)` cho kết quả, cộng các đối tượng do phép `map` tạo. |
| `sorted().toList()` | `O(n log n)` khi cần sắp xếp tổng quát | Thường `O(n)` để giữ dữ liệu sắp xếp và kết quả. |
| `distinct().toList()` | Thường gần `O(n)` khi có hash hiệu quả | Thường phụ thuộc `u`, đồng thời cần chỗ cho kết quả. |

Các con số này mô tả khuynh hướng, **không phải cam kết về số lần duyệt, bộ nhớ cực đại hoặc hiệu năng tuyệt đối**. Đặc tính của nguồn (`SIZED`, `DISTINCT`, `SORTED`...), phép toán, encounter order, phiên bản JDK và chạy song song đều có thể thay đổi chiến lược thực thi.

## 6. So sánh Stream và vòng lặp trong bài toán thực tế

Pipeline tính doanh thu ở trên có một phiên bản vòng lặp tương đương:

```java
long revenue = 0L;
for (Order order : orders) {
    if (order.paid()) {
        revenue += order.amount();
    }
}
```

Cả hai đều biểu diễn một lượt duyệt `O(n)` và không cần danh sách trung gian. Vòng lặp có thể tránh một phần chi phí dựng pipeline, đặc biệt trong đoạn mã cực ngắn được gọi rất nhiều lần. Stream có lợi thế diễn đạt rõ phép biến đổi, dễ phối hợp với các collector và thao tác tổng hợp.

Không có quy tắc chung rằng vòng lặp luôn nhanh hơn Stream hoặc Stream luôn được JVM tối ưu thành cùng mã máy với vòng lặp. Quyết định phải dựa trên **khả năng đọc hiểu, ngữ nghĩa và phép đo trong môi trường thực tế**.

### Lưu ý khi chuyển sang parallel stream

`parallelStream()` có thể chia nguồn thành nhiều phần để xử lý song song, rồi hợp nhất kết quả. Nó không tự động cải thiện hiệu năng: chia việc, đồng bộ, hợp nhất, bảo toàn thứ tự và các thao tác trạng thái như `sorted` hoặc `distinct` có chi phí riêng. `findFirst()` trên nguồn có thứ tự có thể tốn công phối hợp hơn `findAny()` khi không cần kết quả đầu tiên. Các side effect dùng chung giữa nhiều phần việc còn có nguy cơ tranh chấp và lỗi dữ liệu.

Với nguồn nhỏ, công việc nhẹ trên mỗi phần tử hoặc yêu cầu thứ tự nghiêm ngặt, pipeline tuần tự thường là điểm bắt đầu hợp lý. Chỉ đánh giá chạy song song khi công việc đủ lớn, tách được và phép đo chứng minh có lợi.

## 7. Đo đúng chi phí thay vì đoán

Một benchmark kiểu `System.nanoTime()` gọi một lần dễ bị ảnh hưởng bởi khởi động JVM, JIT, GC và độ nhiễu của máy. Để so sánh có căn cứ:

1. **Xác định workload:** kích thước đầu vào, tỷ lệ phần tử qua `filter`, kích thước DTO, độ phức tạp của lambda, mức trùng lặp và nhu cầu bảo toàn thứ tự.
2. **So sánh thuật toán tương đương:** cùng dữ liệu, cùng đầu ra và cùng semantics; đừng so `sorted().limit(10)` với `limit(10).sorted()` nếu yêu cầu là “10 giá trị nhỏ nhất toàn tập”.
3. **Benchmark có warmup:** sử dụng JMH để giảm sai lệch do JIT, chạy nhiều lượt và đảm bảo kết quả không bị tối ưu bỏ vì không sử dụng.
4. **Đo cấp phát và GC:** kết hợp JFR/JDK Mission Control, profiler hoặc thống kê cấp phát để biết chi phí đến từ pipeline setup, boxing, DTO hay collector.
5. **Kiểm tra dưới điều kiện thực:** dữ liệu lớn và nhỏ, heap phù hợp, JDK đang triển khai, và cả tải đồng thời nếu ứng dụng chạy nhiều request.

Một hướng thử nghiệm có ý nghĩa là benchmark ba cách tính tổng sau trên cùng một tập `Order`: vòng lặp `for`, `stream().filter(...).mapToLong(...).sum()` và `stream().filter(...).map(...).reduce(...)`. Đo **throughput/latency lẫn allocated bytes/op**; kết luận chỉ đúng trong phạm vi cấu hình và dữ liệu được thử.

## 8. Những lỗi tư duy thường gặp

| Nhận định vội vàng | Cách hiểu đúng |
| --- | --- |
| “Có ba lệnh `map`/`filter` thì dữ liệu được duyệt ba lượt.” | Với các stage stateless trong pipeline tuần tự, Stream thường kết hợp chúng trong cùng một lượt duyệt. |
| “Stream lười nên không tạo đối tượng.” | Khởi tạo pipeline, lambda, boxing, DTO và kết quả vẫn có thể cấp phát. |
| “`count()` nhất định gọi mọi `map`/`peek`.” | JDK có thể suy ra kích thước và bỏ qua các stage không ảnh hưởng đến kết quả. |
| “Đưa `limit` lên sớm lúc nào cũng tốt.” | Có thể giảm công việc nhưng đổi ngữ nghĩa, đặc biệt khi đi cùng `sorted`, `skip` hoặc xử lý có thứ tự. |
| “`parallelStream()` luôn nhanh hơn.” | Cần tính đến chi phí chia việc, hợp nhất, trạng thái và thứ tự; phải đo. |
| “`mapToLong` làm biến mất mọi wrapper.” | Nó tránh boxing ở phần pipeline nguyên thủy, nhưng không loại bỏ đối tượng đã tồn tại trong nguồn. |

## 9. Bài tập vận dụng

**Bài tập 1 — Dự đoán số lần gọi lambda.** Với pipeline tuần tự sau, hãy dự đoán thứ tự log và giải thích vì sao:

```java
List<Integer> result = IntStream.rangeClosed(1, 10)
    .filter(n -> {
        System.out.println("F " + n);
        return n % 3 == 0;
    })
    .map(n -> {
        System.out.println("M " + n);
        return n * n;
    })
    .limit(2)
    .boxed()
    .toList();

System.out.println(result);
```

*Gợi ý kiểm tra:* `limit(2)` nhận đủ hai phần tử qua bộ lọc là `3` và `6`; kết quả `[9, 36]`. Hãy so sánh với việc đặt `limit(2)` trước `filter`.

**Bài tập 2 — Thiết kế tiết kiệm bộ nhớ.** Một hệ thống có hàng triệu `Order`, chỉ cần tổng số tiền của đơn đã thanh toán. So sánh việc (a) `filter` rồi `map` thành `List<Summary>` rồi cộng, và (b) `filter` rồi `mapToLong().sum()`. Xác định phần nào trong phương án (a) dùng bộ nhớ tỷ lệ với số đơn hợp lệ và khi nào danh sách Summary vẫn là đầu ra bắt buộc.

**Bài tập 3 — Kiểm tra thứ tự thao tác.** Viết thử `sorted().limit(5)` và `limit(5).sorted()` trên một tập số có thứ tự đầu vào không tăng dần. Mô tả yêu cầu nghiệp vụ mà mỗi pipeline thực hiện, rồi dùng JMH đánh giá hiệu năng khi tăng kích thước nguồn.

Khi tối ưu một pipeline Stream API, hãy lần lượt trả lời: **Có cần xử lý toàn bộ nguồn không? Bước nào phải giữ trạng thái? Đầu ra cần là collection hay chỉ một giá trị? Có phát sinh wrapper hoặc DTO không? Đã đo trên workload thật chưa?** Năm câu hỏi này thường hữu ích hơn việc chỉ đếm số thao tác `map` và `filter` trong mã nguồn.
