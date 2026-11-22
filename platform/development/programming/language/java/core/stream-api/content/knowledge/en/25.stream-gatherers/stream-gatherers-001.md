# Vai trò của gather và Gatherer trong JDK hỗ trợ

Java Stream API cung cấp các thao tác quen thuộc như `filter`, `map`, `flatMap`, `distinct`, `sorted`, `reduce` và `collect`. Chúng giải quyết rất nhiều bài toán xử lý dữ liệu khai báo. Tuy nhiên, một số bài toán cần **nhìn nhiều phần tử liên tiếp**, **duy trì trạng thái qua các phần tử** hoặc **phát số lượng kết quả khác với số lượng đầu vào**: tính trung bình trượt, gom sự kiện theo lô, kiểm tra mẫu sự kiện hay phát nhiều kết quả từ một bản ghi. Đây là những tình huống mà **Stream Gatherers** mở rộng khả năng biểu đạt của pipeline.

Từ **Java 24**, `Stream.gather(...)` và các giao diện trong `java.util.stream.Gatherer` trở thành API chính thức. Một `Gatherer` mô tả *cách một giai đoạn trung gian nhận, xử lý và phát phần tử*, còn `gather(...)` là thao tác trên `Stream` dùng để **gắn Gatherer vào pipeline**.

Bài thuộc chương **Stream Gatherer** của mô-đun **JAVA_STREAM_API**. Mục tiêu là hiểu vai trò của `gather` và `Gatherer`, biết chọn chúng so với `filter`, `map`, `flatMap`, `reduce` và `collect`, nắm các Gatherer dựng sẵn, cách viết Gatherer đơn giản, yêu cầu JDK và những giới hạn về tính lazy, dừng sớm, thứ tự, xử lý song song, tài nguyên và hiệu năng. Các ví dụ chính sử dụng **JDK 24+**.

## 1. Bài toán mở đầu: trung bình ba phép đo gần nhất

Giả sử hệ thống nhận chuỗi nhiệt độ theo thứ tự thời gian:

```text
20, 22, 21, 25, 27
```

Trung bình toàn bộ chuỗi là:

```java
import java.util.List;

List<Integer> temperatures = List.of(20, 22, 21, 25, 27);

double overallAverage = temperatures.stream()
    .mapToInt(Integer::intValue)
    .average()
    .orElseThrow();

System.out.println(overallAverage); // 23.0
```

Nhưng người dùng muốn **trung bình của từng nhóm ba phép đo liên tiếp**:

```text
[20, 22, 21] -> 21.0
[22, 21, 25] -> 22.666...
[21, 25, 27] -> 24.333...
```

Từ Java 24 có thể viết trực tiếp:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Double> movingAverages = temperatures.stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> window.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow())
    .toList();

System.out.println(movingAverages);
// [21.0, 22.666666666666668, 24.333333333333332]
```

Ở đây `windowSliding(3)` tạo **một cửa sổ gồm ba phần tử liên tiếp** cho mỗi vị trí đủ mẫu; `map` tính trung bình của **mỗi cửa sổ**. Thao tác `gather` cho phép pipeline chuyển từ:

```text
Stream<Integer>
      |
      | gather(Gatherers.windowSliding(3))
      v
Stream<List<Integer>>
      |
      | map(tính trung bình)
      v
Stream<Double>
      |
      | toList()
      v
List<Double>
```

Đây là vai trò tổng quát của Gatherer: **biến đổi cả cách các phần tử chảy qua pipeline**, thay vì chỉ tính toán trên từng phần tử riêng lẻ.

## 2. Phân biệt `gather` với `Gatherer` và `Gatherers`

Ba tên gần giống nhau nhưng thuộc những vai trò khác nhau:

| Thành phần | Loại | Vai trò |
| --- | --- | --- |
| `Stream.gather(...)` | Phương thức trên `Stream<T>` | Gắn một Gatherer để tạo **giai đoạn trung gian mới** |
| `Gatherer<T, A, R>` | Giao diện mô tả quy tắc xử lý | Nhận `T`, có thể giữ trạng thái `A`, phát `R` |
| `Gatherers` | Lớp tiện ích chứa các factory | Cung cấp các Gatherer dựng sẵn như `windowFixed`, `windowSliding`, `scan`, `fold`, `mapConcurrent` |

Ví dụ:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<String, ?, List<String>> batchByTwo =
    Gatherers.windowFixed(2);

List<List<String>> batches = Stream.of("A", "B", "C")
    .gather(batchByTwo)
    .toList();

System.out.println(batches); // [[A, B], [C]]
```

Phương thức `Gatherers.windowFixed(2)` **tạo một đối tượng Gatherer**; phương thức `Stream.gather(batchByTwo)` **sử dụng đối tượng đó** trong pipeline.

**Cách nhớ:** `Gatherer` là *quy tắc*, `Gatherers` là *bộ quy tắc dựng sẵn*, còn `gather` là *điểm áp dụng quy tắc lên Stream*.

### 2.1. `gather` là thao tác trung gian

`gather` trả về một Stream mới, do đó có thể tiếp tục:

```java
List<Integer> sums = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(2))
    .map(window -> window.stream().mapToInt(Integer::intValue).sum())
    .filter(sum -> sum >= 5)
    .toList();

System.out.println(sums); // [7, 5]
```

Các cửa sổ là `[1,2]`, `[3,4]`, `[5]` với tổng `3`, `7` và `5`. Bộ lọc sau `gather` kiểm tra **tổng của từng cửa sổ**, không kiểm tra từng số đầu vào.

`gather` **không phải terminal operation**. Chỉ khi có terminal operation như `toList`, `collect`, `reduce` hoặc `findFirst`, pipeline mới được tiêu thụ.

## 3. Mốc JDK: khi nào dùng được Stream Gatherers?

Stream Gatherers đi qua ba giai đoạn:

| Phiên bản JDK | Trạng thái | JEP | Yêu cầu |
| --- | --- | --- | --- |
| Java 8–21 | Không có Stream Gatherers chuẩn | — | Không gọi trực tiếp `Stream.gather` |
| **Java 22** | Preview lần đầu | [JEP 461](https://openjdk.org/jeps/461) | Bật preview khi biên dịch và chạy |
| **Java 23** | Second preview | [JEP 473](https://openjdk.org/jeps/473) | Vẫn phải bật preview |
| **Java 24** | API chính thức | [JEP 485](https://openjdk.org/jeps/485) | Không cần preview chỉ để dùng Gatherer |
| Java 25 trở lên có API này | API đã được chuẩn hóa | Bắt đầu từ JEP 485 | Dùng toolchain/runtime phù hợp phiên bản mục tiêu |

Chương trình sử dụng Gatherer chuẩn trên JDK 24:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererAvailabilityDemo {
    public static void main(String[] args) {
        List<List<Integer>> result = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowFixed(2))
            .toList();

        System.out.println(result); // [[1, 2], [3, 4], [5]]
    }
}
```

Biên dịch và chạy bằng **JDK 24**:

```bash
javac --release 24 GathererAvailabilityDemo.java
java GathererAvailabilityDemo
```

Nếu đang thử nghiệm cùng một bài cơ bản trên **JDK 22**:

```bash
javac --enable-preview --release 22 GathererAvailabilityDemo.java
java --enable-preview GathererAvailabilityDemo
```

Trên **JDK 23**:

```bash
javac --enable-preview --release 23 GathererAvailabilityDemo.java
java --enable-preview GathererAvailabilityDemo
```

Không dùng JDK 21 cùng `--enable-preview` rồi mong có `Gatherers`: Java 21 chưa cung cấp API này. `--release 21` trên compiler mới cũng không cho phép sử dụng API Java 24 khi tuyên bố target Java 21.

### 3.1. Lưu ý về tính tương thích

- Ví dụ trong bài viết theo **API chính thức của Java 24**, không có nghĩa mã tùy chỉnh viết cho bản preview 22/23 sẽ chuyển lên mà không chỉnh sửa.
- Preview feature gắn với phiên bản JDK đang dùng; nên biên dịch lại trên JDK mục tiêu.
- Nếu ứng dụng cần chạy trên Java 17/21, phải chọn giải pháp khác hoặc tách phần yêu cầu JDK mới.
- Java 24 là bản có API Gatherer chính thức, nhưng **phiên bản Java tối thiểu của sản phẩm** do yêu cầu triển khai và chính sách hỗ trợ quyết định.

## 4. Tại sao cần Gatherer khi đã có `map` và `flatMap`?

Nhiều yêu cầu nên tiếp tục dùng thao tác Stream truyền thống. Gatherer không có mục tiêu thay thế chúng.

| Bài toán | API nên ưu tiên | Vì sao |
| --- | --- | --- |
| Chỉ giữ giao dịch đã thanh toán | `filter(Order::paid)` | Mỗi phần tử được xét độc lập |
| Đổi tên thành chữ hoa | `map(String::toUpperCase)` | Một đầu vào cho một đầu ra |
| Tách từng danh sách con thành phần tử | `flatMap(List::stream)` | Ghép nhiều Stream con |
| Tính một tổng cuối cùng | `mapToLong(...).sum()` hoặc `reduce` | Không cần phát chuỗi kết quả trung gian |
| Gom nhóm theo khóa ở cuối pipeline | `collect(groupingBy(...))` | Kết quả cuối là Map/báo cáo |
| Gom mỗi 100 phần tử liên tiếp thành một lô | `gather(windowFixed(100))` | Cần giai đoạn có trạng thái để hình thành lô |
| Trung bình trượt của ba phần tử gần nhất | `gather(windowSliding(3))` rồi `map` | Cần cửa sổ chồng lấn |
| Phát tổng tích lũy sau **mỗi** phần tử | `gather(scan(...))` | Cần nhiều kết quả tích lũy, không chỉ một tổng cuối |
| Biến đổi trung gian có trạng thái tùy chỉnh | Custom `Gatherer` | Cần điều khiển dữ liệu và trạng thái vượt các thao tác có sẵn |

Phép `flatMap` cũng có thể phát nhiều đầu ra từ một phần tử, nên **số lượng đầu ra khác số lượng đầu vào** một mình chưa đủ để bắt buộc dùng Gatherer. Điểm mạnh của Gatherer là **mô hình lập trình cho thao tác trung gian có trạng thái và quy tắc phát/dừng linh hoạt**.

### 4.1. Gatherer không thay thế `Collector`

`Collectors.groupingBy` gom các phần tử theo khóa và tạo **một Map kết quả cuối**:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String region, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("Bắc", 100L),
    new Sale("Nam", 200L),
    new Sale("Bắc", 300L)
);

Map<String, Long> totals = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(totals.get("Bắc")); // 400
```

Gatherer tạo các **giá trị trung gian** mà sau đó có thể tiếp tục lọc, biến đổi hoặc thu thập. Ví dụ nhận các nhóm giao dịch liên tiếp, rồi mới tính tổng mỗi lô:

```java
List<Long> batchTotals = sales.stream()
    .gather(Gatherers.windowFixed(2))
    .map(batch -> batch.stream()
        .mapToLong(Sale::amountVnd)
        .sum())
    .toList();

System.out.println(batchTotals); // [300, 300]
```

Hai bài toán có ý nghĩa khác nhau:

- `groupingBy`: tất cả giao dịch cùng `region` được gom về một khóa, dù xuất hiện cách xa nhau.
- `windowFixed`: các giao dịch **liền nhau** theo encounter order được gom theo số lượng, không theo khóa.

## 5. Các thành phần của một Gatherer

Hình thức tổng quát:

```java
Gatherer<T, A, R>
```

Trong đó:

- **`T`**: kiểu phần tử đầu vào của giai đoạn.
- **`A`**: kiểu trạng thái nội bộ (*intermediate state*); có thể là một đối tượng, mảng hoặc `Void` nếu không cần trạng thái.
- **`R`**: kiểu phần tử được phát về phía downstream.

Bốn thành phần tạo nên vòng đời xử lý:

| Thành phần | Nhiệm vụ | Câu hỏi lập trình viên cần trả lời |
| --- | --- | --- |
| `initializer` | Tạo trạng thái `A` | Ban đầu lưu thông tin gì? |
| `integrator` | Nhận một `T`, cập nhật `A`, có thể phát các `R` | Mỗi phần tử ảnh hưởng kết quả thế nào? |
| `combiner` | Kết hợp các trạng thái khi có phân chia công việc | Hai nhánh có thể được gộp đúng không? |
| `finisher` | Hoàn tất khi kết thúc xử lý, có thể phát đầu ra còn lại | Có phần kết quả cần đẩy ở cuối nguồn không? |

Mô hình:

```text
        Stream<T>
            |
            v
   +---------------------+
   | initializer()       | -> state A
   +---------------------+
            |
            v
   +---------------------+
   | integrator(state,   | -> push R, push R, ...
   |            T, out)  |
   +---------------------+
            |
            | khi kết thúc nguồn hoặc xử lý
            v
   +---------------------+
   | finisher(state,out) | -> có thể push thêm R
   +---------------------+
            |
            v
        Stream<R>

   combiner(left,right): dành cho thiết kế có thể gộp trạng thái
```

**Không phải mọi Gatherer đều cần bốn thành phần tự viết.** Các factory trong `Gatherers` đã chuẩn bị logic hoàn chỉnh cho nhiều mẫu thông dụng. Các factory `Gatherer.of(...)` và `Gatherer.ofSequential(...)` còn cung cấp overload cho các trường hợp không cần state hoặc finisher tùy chỉnh.

### 5.1. Gatherer có thể nhận một phần tử nhưng phát 0, 1 hoặc nhiều phần tử

Khác với `map` luôn ánh xạ một phần tử thành một đầu ra, Integrator có thể:

- Nhận một phần tử mà **chưa phát gì**, vì cần đủ dữ liệu.
- Phát **một** kết quả mới sau mỗi phần tử, như running sum.
- Phát **nhiều** kết quả do một phần tử chứa nhiều dữ liệu con.
- Chấm dứt nhận thêm dữ liệu theo một điều kiện hợp lệ.

Đây là điểm quan trọng khi xây các xử lý theo cửa sổ, giao thức hoặc phân tích luồng sự kiện.

## 6. `Gatherers.windowFixed`: chia nguồn thành những lô cố định

`windowFixed(k)` tạo các cửa sổ **không chồng lấn**, mỗi cửa sổ tối đa `k` phần tử. Cửa sổ cuối có thể ít hơn `k` phần tử.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [4, 5, 6], [7]]
```

Đây là lựa chọn hợp lý để:

- Tính số tiền của từng lô giao dịch liên tiếp.
- Xử lý dữ liệu theo batch có giới hạn `k` phần tử.
- Phát các khối đầu vào cho một bước biến đổi tiếp theo.
- Tạo thống kê theo mỗi nhóm quan sát liền kề có độ dài tối đa cố định.

### 6.1. Nhóm cuối thiếu phần tử vẫn xuất hiện

```java
List<List<String>> batches = Stream.of("A", "B", "C", "D", "E")
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(batches); // [[A, B], [C, D], [E]]
```

Nếu nghiệp vụ chỉ xử lý lô **đủ hai phần tử**:

```java
List<List<String>> fullBatches = Stream.of("A", "B", "C", "D", "E")
    .gather(Gatherers.windowFixed(2))
    .filter(batch -> batch.size() == 2)
    .toList();

System.out.println(fullBatches); // [[A, B], [C, D]]
```

Không nên tự giả định nhóm cuối bị bỏ. Đây là **chính sách nghiệp vụ** cần viết thành điều kiện cụ thể nếu có yêu cầu.

## 7. `Gatherers.windowSliding`: những cửa sổ chồng lấn

`windowSliding(k)` tạo các cửa sổ gồm `k` phần tử liên tiếp và dịch điểm bắt đầu lên **một phần tử** sau mỗi cửa sổ đầy đủ.

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Khác với `windowFixed(3)` trên cùng nguồn:

```java
System.out.println(Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(3))
    .toList());
// [[1, 2, 3], [4, 5]]
```

### 7.1. So sánh tình huống biên

Với kích thước cửa sổ `k = 3`:

| Đầu vào | `windowFixed(3)` | `windowSliding(3)` |
| --- | --- | --- |
| `[]` | `[]` | `[]` |
| `[1]` | `[[1]]` | `[[1]]` |
| `[1,2]` | `[[1,2]]` | `[[1,2]]` |
| `[1,2,3]` | `[[1,2,3]]` | `[[1,2,3]]` |
| `[1,2,3,4]` | `[[1,2,3],[4]]` | `[[1,2,3],[2,3,4]]` |

Đối với `windowSliding(k)`, nếu nguồn **không rỗng nhưng có ít hơn `k` phần tử**, nó phát **một cửa sổ ngắn** chứa toàn bộ nguồn. Nếu nguồn có ít nhất `k` phần tử, các cửa sổ trượt được phát ra đều đủ `k` phần tử.

Với `N >= k`, số cửa sổ trượt bằng `N-k+1`. Với cửa sổ cố định trên nguồn hữu hạn, số cửa sổ bằng `ceil(N/k)` khi `N > 0`.

### 7.2. Cửa sổ phần tử không đồng nghĩa cửa sổ thời gian

`windowSliding(3)` nghĩa là **ba phần tử liên tiếp**, không có nghĩa ba giây hoặc ba phút. Nếu các sự kiện có timestamp cách nhau không đều, muốn cửa sổ theo thời gian thực tế cần có một thiết kế khác xác định rõ:

- Thời gian sự kiện hay thời gian xử lý.
- Ranh giới đầu/cuối của khoảng thời gian.
- Các sự kiện đến muộn và thứ tự timestamp.
- Chính sách cho những khoảng thời gian không có bản ghi.

Gatherer chuẩn chỉ nhận **thứ tự phần tử** và kích thước `k`, không suy ra các quy tắc thời gian nghiệp vụ.

## 8. `Gatherers.scan` và `Gatherers.fold`: trạng thái tích lũy và kết quả cuối

Hai Gatherer dựng sẵn này làm rõ **sự khác nhau giữa phát kết quả qua từng bước và chỉ phát kết quả sau cùng**.

### 8.1. `scan` phát tổng chạy sau mỗi phần tử

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Long> runningTotals = List.of(10L, 20L, 30L, 40L)
    .stream()
    .gather(Gatherers.scan(
        () -> 0L,
        Long::sum
    ))
    .toList();

System.out.println(runningTotals); // [10, 30, 60, 100]
```

Đầu ra chứa giá trị tích lũy **sau mỗi lần nhận phần tử**. Tổng chạy không phải tổng cửa sổ trượt: với running sum, phần tử cũ **không bị loại khỏi tổng**.

### 8.2. `fold` phát một giá trị sau khi tổng hợp

```java
String text = Stream.of("Java", " ", "Stream")
    .gather(Gatherers.fold(
        () -> "",
        String::concat
    ))
    .findFirst()
    .orElseThrow();

System.out.println(text); // Java Stream
```

`fold` dùng trạng thái tích lũy để tạo **một kết quả ở cuối**, khác với `scan` có thể phát nhiều giá trị trung gian.

Khi chỉ cần một tổng số học cuối, `reduce` hoặc `sum` thường đơn giản hơn `gather(fold(...))`:

```java
long total = List.of(10L, 20L, 30L, 40L)
    .stream()
    .mapToLong(Long::longValue)
    .sum();

System.out.println(total); // 100
```

**Quy tắc chọn:** `scan` khi cần các trạng thái tích lũy theo từng bước; `fold` khi muốn một giá trị sau khi duyệt nguồn; `reduce`/`sum` khi phép tổng hợp cuối đơn giản và đã có terminal operation phù hợp.

## 9. `Gatherers.mapConcurrent`: ánh xạ đồng thời có giới hạn

`Gatherers.mapConcurrent(maxConcurrency, mapper)` cho phép một giai đoạn ánh xạ **thực hiện nhiều công việc đồng thời** bằng virtual threads, trong phạm vi tối đa do `maxConcurrency` chỉ định. Gatherer này **giữ thứ tự kết quả** theo encounter order của Stream.

Ví dụ có thể chạy trên JDK 24+:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Integer> sizes = List.of("A", "Java", "Gatherers")
    .stream()
    .gather(Gatherers.mapConcurrent(
        3,
        String::length
    ))
    .toList();

System.out.println(sizes); // [1, 4, 9]
```

Các phép `String::length` rất rẻ, nên ví dụ chỉ minh họa cú pháp. `mapConcurrent` thường đáng cân nhắc hơn cho những tác vụ độc lập có thời gian chờ, chẳng hạn gọi các dịch vụ có hợp đồng cho phép đồng thời, **nếu** giới hạn concurrency và quản lý I/O được thiết kế phù hợp.

### 9.1. `mapConcurrent` khác `parallelStream`

| Tiêu chí | `Gatherers.mapConcurrent` | `parallelStream().map(...)` |
| --- | --- | --- |
| Mục tiêu | Giới hạn số phép mapper đang thực hiện đồng thời | Chia xử lý Stream trên các tác vụ song song |
| Mô hình nổi bật | Virtual threads cho công việc mapper | Cơ chế xử lý song song của Stream |
| Cấu hình giới hạn đồng thời tại API | `maxConcurrency` | Không có tham số tương đương ngay trên `parallel()` |
| Thứ tự đầu ra | Giữ encounter order khi có | `toList` cũng giữ encounter order khi Stream có thứ tự |
| Bảo đảm chạy nhanh hơn | **Không** | **Không** |

Cả hai đều không tự biến một mapper dùng trạng thái mutable chia sẻ thành thread-safe. Việc giữ **thứ tự kết quả** không có nghĩa các phép tính bên trong được thực hiện tuần tự.

Đừng đặt `maxConcurrency` quá cao chỉ để tăng throughput. Nguồn I/O, giới hạn kết nối, mức CPU, bộ nhớ và yêu cầu upstream/downstream đều ảnh hưởng hiệu quả.

## 10. Tự viết Gatherer tối giản: một đầu vào thành một đầu ra

Để hiểu vai trò của `Gatherer`, ta bắt đầu bằng một ví dụ không cần trạng thái: bình phương số nguyên.

```java
import java.util.List;
import java.util.stream.Gatherer;

public class SquareGathererDemo {

    static Gatherer<Integer, Void, Integer> squares() {
        Gatherer.Integrator.Greedy<Void, Integer, Integer> integrator =
            Gatherer.Integrator.ofGreedy(
                (unused, number, downstream) ->
                    downstream.push(Math.multiplyExact(number, number))
            );

        return Gatherer.of(integrator);
    }

    public static void main(String[] args) {
        List<Integer> result = List.of(1, 2, 3, 4)
            .stream()
            .gather(squares())
            .toList();

        System.out.println(result); // [1, 4, 9, 16]
    }
}
```

Đây là custom Gatherer có `T = Integer`, `A = Void` và `R = Integer`. Không có bộ trạng thái riêng. Integrator nhận số, tính bình phương rồi gọi `downstream.push`.

`Integrator.ofGreedy` được dùng vì Integrator **không tự yêu cầu dừng sớm**: nó chỉ phản ánh quyết định của downstream qua giá trị trả về từ `push`.

Với bài toán đơn giản này, vẫn nên dùng:

```java
List<Integer> result = List.of(1, 2, 3, 4)
    .stream()
    .map(n -> Math.multiplyExact(n, n))
    .toList();
```

Mục đích của ví dụ là làm quen với API, **không** đề xuất thay mọi `map` bằng Gatherer. Khi code không cần giữ trạng thái hoặc phát nhiều kết quả theo quy tắc riêng, thao tác chuẩn thường rõ ràng hơn.

## 11. Custom Gatherer có trạng thái: phát tổng chạy

Với `scan` đã có sẵn, ta có thể học cách một Gatherer tự viết lưu trạng thái qua các lần nhận phần tử.

Ví dụ sau dùng một mảng `long[]` để giữ tổng. Mảng được tạo mới cho phạm vi tích lũy và không được chia sẻ như biến toàn cục.

```java
import java.util.List;
import java.util.stream.Gatherer;

public class RunningSumGathererDemo {

    static Gatherer<Integer, long[], Long> runningSum() {
        return Gatherer.ofSequential(
            () -> new long[] {0L},
            (state, number, downstream) -> {
                state[0] = Math.addExact(state[0], number.longValue());
                return downstream.push(state[0]);
            }
        );
    }

    public static void main(String[] args) {
        List<Long> result = List.of(3, 5, -2, 9)
            .stream()
            .gather(runningSum())
            .toList();

        System.out.println(result); // [3, 8, 6, 15]
    }
}
```

Thành phần của Gatherer:

1. **Initializer:** `() -> new long[] {0L}` tạo trạng thái khởi đầu.
2. **Integrator:** nhận từng số, cộng vào tổng và phát tổng mới.
3. **Combiner:** không khai báo; `ofSequential` dùng khi chưa có cách gộp trạng thái song song đúng.
4. **Finisher:** không có công việc đặc biệt nên không cần tự định nghĩa.

`Math.addExact` làm phát sinh `ArithmeticException` nếu tổng `long` tràn. Nó **không** chuyển phép cộng thành phép số nguyên vô hạn; nếu yêu cầu tổng lớn hơn 64 bit, cần kiểu như `BigInteger`.

### 11.1. Vì sao chọn `ofSequential`?

Kết quả tổng chạy có phụ thuộc thứ tự: để phát đúng trạng thái ở phần tử thứ ba, Gatherer cần biết tổng của các phần tử trước đó. Không thể tự ý gộp các trạng thái của hai nhánh bằng `Long::sum` rồi cho rằng **toàn bộ chuỗi prefix sum** vẫn đúng.

`ofSequential` là lựa chọn rõ ràng khi không có combiner hợp lệ. Nó không có nghĩa mọi giai đoạn trong pipeline chỉ chạy trên một Java thread duy nhất, cũng không loại bỏ yêu cầu kiểm tra trạng thái dùng chung ở nơi khác.

### 11.2. Một Stream chỉ được tiêu thụ một lần

```java
var pending = List.of(3, 5, -2, 9)
    .stream()
    .gather(runningSum());

System.out.println(pending.toList()); // [3, 8, 6, 15]

// pending.count(); // Không hợp lệ: Stream đã được tiêu thụ.
```

Một Gatherer có thể được sử dụng cho các **pipeline mới** theo đúng hợp đồng, nhưng nó không biến cùng một Stream đã tiêu thụ thành nguồn có thể tái sử dụng.

## 12. Custom Gatherer và dừng sớm

Bên cạnh trạng thái và đầu ra, Gatherer có thể **tự dừng nhận upstream** khi gặp một dấu mốc nghiệp vụ.

Ví dụ giữ tất cả chuỗi cho đến khi gặp `"END"`, **bao gồm marker**:

```java
import java.util.List;
import java.util.stream.Gatherer;

public class UntilEndGathererDemo {

    static Gatherer<String, Void, String> untilEnd() {
        Gatherer.Integrator<Void, String, String> integrator =
            Gatherer.Integrator.of(
                (unused, value, downstream) -> {
                    boolean wantsMore = downstream.push(value);
                    return wantsMore && !"END".equals(value);
                }
            );

        return Gatherer.ofSequential(integrator);
    }

    public static void main(String[] args) {
        List<String> result = List.of(
                "START", "RUN", "END", "AFTER"
            ).stream()
            .gather(untilEnd())
            .toList();

        System.out.println(result); // [START, RUN, END]
    }
}
```

Đối với Integrator thông thường:

- Trả `true`: sẵn sàng nhận thêm phần tử.
- Trả `false`: đề nghị dừng nhận upstream.
- Có thể tự trả `false` vì gặp marker, ngay cả khi downstream vẫn còn muốn nhận thêm.

### 12.1. `ofGreedy` không có nghĩa luôn phải phát phần tử

`Gatherer.Integrator.ofGreedy` tạo một Integrator **không tự khởi phát dừng sớm**. Nó có thể bỏ qua phần tử hoặc phát nhiều kết quả, nhưng **không** được tự trả `false` vì điều kiện nghiệp vụ khi downstream còn nhận.

Ví dụ lọc số chẵn mà vẫn tiếp tục sau số lẻ:

```java
Gatherer.Integrator.Greedy<Void, Integer, Integer> even =
    Gatherer.Integrator.ofGreedy(
        (unused, n, downstream) ->
            n % 2 == 0 ? downstream.push(n) : true
    );
```

Ví dụ **sai hợp đồng** nếu gắn nhãn Greedy:

```java
Gatherer.Integrator.Greedy<Void, String, String> bad =
    Gatherer.Integrator.ofGreedy(
        (unused, value, downstream) ->
            downstream.push(value) && !"END".equals(value)
    );
```

Vì `false` có thể xuất hiện do marker, một triển khai Stream hợp lệ có thể **bỏ qua giá trị trả về của Greedy Integrator** và không dừng ở chỗ code mong muốn.

**Nguyên tắc:** dùng Integrator thông thường khi **chính Gatherer quyết định dừng**; chỉ dùng `ofGreedy` khi không có đường tự dừng nào.

## 13. Cơ chế phát đầu ra: `Downstream.push` và `isRejecting`

Integrator giao tiếp với giai đoạn tiếp theo thông qua `Gatherer.Downstream<R>`.

```java
boolean accepted = downstream.push(result);
boolean rejecting = downstream.isRejecting();
```

`push(result)` trả `false` nếu downstream không muốn nhận thêm đầu ra. Một terminal operation như `limit(3).toList()` có thể làm downstream từ chối sau khi đủ ba phần tử. `isRejecting()` là phép kiểm tra *best-effort* về tình trạng từ chối, không bảo đảm `push` tương lai chắc chắn được chấp nhận nếu trả `false` ở thời điểm kiểm tra.

Với Gatherer có thể phát nhiều kết quả cho một đầu vào, nên phản hồi tín hiệu:

```java
import java.util.List;
import java.util.stream.Gatherer;

Gatherer.Integrator.Greedy<Void, List<String>, String> flatten =
    Gatherer.Integrator.ofGreedy(
        (unused, batch, downstream) -> {
            for (String item : batch) {
                if (!downstream.push(item)) {
                    return false; // Chỉ truyền downstream rejection.
                }
            }
            return true;
        }
    );
```

`return false` ở đây **không** vi phạm Greedy vì chỉ xảy ra khi downstream `push` trả `false`. Không tiếp tục duyệt các phần tử còn lại trong một batch nếu downstream đã từ chối.

Nếu chỉ cần làm phẳng danh sách, `flatMap(List::stream)` là lựa chọn gọn hơn. Ví dụ minh họa **cơ chế điều phối đầu ra** của Gatherer.

## 14. `finisher` dùng để phát phần kết quả còn lại

Không phải mọi Gatherer phát dữ liệu ngay trong Integrator. Có trường hợp cần **giữ trạng thái rồi phát một kết quả vào cuối nguồn**.

Ví dụ đếm các phần tử nhận được, rồi phát số lượng khi kết thúc:

```java
import java.util.List;
import java.util.stream.Gatherer;

public class FinishCountGathererDemo {
    static final class State {
        long count;
    }

    static Gatherer<String, State, Long> countAtEnd() {
        return Gatherer.ofSequential(
            State::new,
            (state, value, downstream) -> {
                state.count = Math.addExact(state.count, 1L);
                return true; // Chưa phát gì, vẫn muốn nhận tiếp.
            },
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(state.count);
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Long> output = List.of("A", "B", "C")
            .stream()
            .gather(countAtEnd())
            .toList();

        System.out.println(output); // [3]
    }
}
```

Ví dụ này cho thấy:

- Integrator có thể **không phát kết quả** trong suốt quá trình nhận input.
- `finisher` có thể phát một phần tử cuối cùng.
- Khi downstream từ chối, không nên tiếp tục phát thêm dữ liệu không cần thiết.

Trong sản phẩm thực, đếm đơn giản nên dùng `Stream.count()`. Custom Gatherer thích hợp hơn khi có quy tắc xử lý trạng thái nhiều bước hoặc dữ liệu cuối cần được phát như một giai đoạn trung gian.

## 15. Tính lazy: `gather` không chạy ngay khi tạo pipeline

Một Stream pipeline được xây dựng trước, xử lý khi terminal operation bắt đầu.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Stream<List<Integer>> pending = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3));

// Chưa gọi toList(), findFirst() hoặc terminal operation nào khác.

List<Integer> firstWindow = pending.findFirst().orElseThrow();

System.out.println(firstWindow); // [1, 2, 3]
```

`findFirst` có thể dừng sau khi giai đoạn Gatherer phát đủ dữ liệu cho nó. Một Gatherer có khả năng phát kết quả trước khi nguồn kết thúc thường phù hợp với nhu cầu xử lý **incremental**, nhưng điều đó **không** có nghĩa mọi Gatherer đều có thể tạo đầu ra tức thì.

Ví dụ `fold` cần tích lũy đến hết nguồn mới tạo kết quả cuối.

### 15.1. Tránh side effect phụ thuộc số lần gọi callback

`map`, `filter`, `peek` và integrator là các hàm trong pipeline. Không nên dựa vào side effect để đếm chính xác “framework đã gọi lambda mấy lần” trong mọi hoàn cảnh:

- Terminal operation có thể short-circuit.
- Stream có thể tối ưu các bước khi ngữ nghĩa kết quả được giữ nguyên.
- Xử lý song song có thể thay đổi thứ tự và cách chia công việc.
- Gatherer có thể phát 0, 1 hoặc nhiều đầu ra cho mỗi đầu vào.

Hãy biểu diễn thống kê bằng kết quả của `count`, `sum`, `reduce`, `collect` hoặc Gatherer đúng hợp đồng, thay vì biến `peek` thành nơi ghi dữ liệu nghiệp vụ bắt buộc.

## 16. Stream vô hạn và dừng sớm

Một nguồn vô hạn vẫn có thể dùng được nếu phía sau có điều kiện kết thúc rõ ràng.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> firstThreeWindows = Stream
    .iterate(1, n -> n + 1)
    .gather(Gatherers.windowSliding(3))
    .limit(3)
    .toList();

System.out.println(firstThreeWindows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

`limit(3)` giới hạn **ba cửa sổ đầu ra**, không giới hạn ba phần tử nguồn. Để có ba cửa sổ đầy đủ rộng ba, pipeline cần ít nhất năm phần tử đầu vào.

Với nguồn vô hạn, tránh các terminal operation hoặc Gatherer **đòi kết thúc toàn bộ nguồn trước khi phát kết quả**, chẳng hạn một phép fold trên nguồn không bao giờ kết thúc.

### 16.1. Dừng sớm và tài nguyên là hai vấn đề khác nhau

Nếu nguồn là Stream gắn tệp hoặc kết nối, một `limit` hoặc Gatherer tự dừng **không tự giải phóng tài nguyên**. Phải đóng đúng nguồn theo hợp đồng API, thường bằng `try-with-resources`.

## 17. Encounter order: cửa sổ phụ thuộc vào thứ tự phần tử

`windowFixed` và `windowSliding` dựa vào **thứ tự phần tử được gặp**. Với nguồn có encounter order như `List.stream()` hoặc `IntStream.range(...).boxed()`, người học có thể dự đoán chính xác các cửa sổ theo thứ tự đó.

```java
import java.util.List;
import java.util.stream.Gatherers;

List<List<String>> windows = List.of("A", "B", "C", "D")
    .stream()
    .gather(Gatherers.windowSliding(2))
    .toList();

System.out.println(windows);
// [[A, B], [B, C], [C, D]]
```

Nếu nguồn là `HashSet` hoặc pipeline bị chuyển sang `unordered()`, không nên suy một thứ tự nghiệp vụ cố định. Dù tất cả giá trị đều xuất hiện, **cách chúng được ghép thành cửa sổ** có thể không biểu diễn “hai bản ghi gần nhất theo thời gian”.

Đối với dữ liệu có timestamp, phải xác định rõ:

- Nguồn đã được sắp theo thời gian sự kiện chưa?
- Nếu timestamp trùng nhau, tiêu chí phụ là gì?
- Việc gọi `sorted` trước `gather` có làm thay đổi ý nghĩa ban đầu không?
- Có cần cửa sổ theo thời gian thay vì theo số bản ghi?

Một đối tượng có trường timestamp **không khiến Stream tự trở thành Stream có thứ tự theo timestamp**.

## 18. Xử lý song song: Gatherer không tự bảo đảm tăng tốc

Một số Gatherer mang trạng thái phụ thuộc thứ tự. Khi chạy song song, hệ thống phải biết liệu có thể:

1. Chia phần tử thành các nhánh.
2. Xử lý trạng thái của từng nhánh.
3. Hợp nhất kết quả mà **không mất, trùng hoặc đổi sai thứ tự phần tử**.

`combiner` là một phần của hợp đồng hỗ trợ việc gộp trạng thái khi có thể phân chia. Nhưng không phải bài toán nào cũng có combiner đơn giản.

Ví dụ tổng chạy ở mục 11 cần biết **tổng của toàn bộ phần trước** khi phát các giá trị ở phần sau. Ghép hai tổng cục bộ bằng phép cộng chưa đủ để hiệu chỉnh tất cả giá trị trung gian của nhánh sau. Vì vậy ví dụ sử dụng `ofSequential`.

```java
List<Long> output = List.of(1, 2, 3, 4, 5)
    .parallelStream()
    .gather(RunningSumGathererDemo.runningSum())
    .toList();

System.out.println(output); // [1, 3, 6, 10, 15]
```

Dù nguồn là parallel Stream, Gatherer tuần tự có thể hạn chế khả năng chạy song song tại giai đoạn đó. Không nên kết luận việc gọi `parallelStream()` luôn tăng tốc.

### 18.1. Dùng trạng thái mutable đúng phạm vi

Mô hình không nên dùng:

```java
import java.util.ArrayList;
import java.util.List;

List<Long> shared = new ArrayList<>();

List.of(1, 2, 3, 4).parallelStream()
    .map(Integer::longValue)
    .forEach(shared::add); // Không an toàn khi nhiều task ghi ArrayList.
```

Mô hình nên dùng:

```java
List<Long> result = List.of(1, 2, 3, 4)
    .parallelStream()
    .map(Integer::longValue)
    .toList();
```

Một custom Gatherer stateful cần lưu trạng thái trong bộ tích lũy được framework quản lý, tránh biến mutable static dùng chung giữa nhiều Stream. Gatherer được thiết kế đúng có thể dùng trạng thái mutable nội bộ nhưng vẫn không cho phép tự ý ghi vào dữ liệu nguồn.

### 18.2. `Integrator.ofGreedy` không đồng nghĩa `Gatherer.ofSequential`

Hai lựa chọn giải quyết hai câu hỏi:

| Câu hỏi | API liên quan |
| --- | --- |
| Integrator có **tự khởi phát dừng sớm** không? | `Integrator.of` và `Integrator.ofGreedy` |
| Gatherer có **combiner đúng** để chia/gộp trạng thái không? | `Gatherer.of`, `ofSequential` và các overload có combiner |

Một Integrator **Greedy nhưng có trạng thái tuần tự** là hoàn toàn hợp lệ. Đánh dấu Greedy không tự biến thuật toán thành song song an toàn.

## 19. Primitive Stream và Gatherer

`gather(...)` là phương thức của **`Stream<T>`** đối tượng. Các primitive specialization như `IntStream`, `LongStream` và `DoubleStream` **không có phương thức `gather` tương đương trực tiếp** trong API Java 24.

Khi cần áp dụng Gatherer với dữ liệu `int`:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 5)
    .boxed()
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
```

`boxed()` tạo `Stream<Integer>`, từ đó có thể dùng `gather`. Khi xử lý hàng triệu số nguyên, boxing và các cửa sổ `List<Integer>` có thể tạo thêm áp lực cấp phát bộ nhớ. Nếu chỉ cần tổng toàn bộ số nguyên, hãy cân nhắc `IntStream.sum`, `LongStream.sum` hoặc `summaryStatistics` trước khi dùng Gatherer.

## 20. I/O và trách nhiệm đóng Stream

`gather` là một giai đoạn trung gian; việc áp dụng nó **không tự đóng** `Files.lines`, `Files.walk` hoặc các nguồn I/O khác.

Ví dụ đếm số dòng lỗi theo từng batch 100 dòng **không trống**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class LogBatchDemo {
    public static List<Long> countErrorsPerBatch(Path path)
            throws IOException {
        try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> !line.isBlank())
                .gather(Gatherers.windowFixed(100))
                .map(batch -> batch.stream()
                    .filter(line -> line.contains("ERROR"))
                    .count())
                .toList();
        }
    }
}
```

Ở đây:

- `Files.lines` giữ tài nguyên đọc tệp trong vòng đời Stream.
- `try-with-resources` đóng nguồn, kể cả khi xảy ra lỗi.
- `filter` **trước** `gather` nghĩa là batch có 100 dòng không trống, **không** nhất thiết 100 dòng gốc.
- `windowFixed(100)` phát batch cuối thiếu 100 dòng nếu còn phần tử.
- `toList()` vật hóa danh sách số lượng lỗi của tất cả batch.

Nếu muốn batch theo **100 dòng gốc rồi mới đếm dòng lỗi**, cần đảo thứ tự:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<Long> counts = lines
        .gather(Gatherers.windowFixed(100))
        .map(batch -> batch.stream()
            .filter(line -> line.contains("ERROR"))
            .count())
        .toList();

    System.out.println(counts);
}
```

Không có một thứ tự pipeline đúng cho mọi nghiệp vụ; chọn thứ tự theo **định nghĩa của một lô dữ liệu**.

## 21. Một ví dụ Java 24 hoàn chỉnh: từ dữ liệu đầu vào tới báo cáo

Chương trình sau kết hợp `filter`, `gather`, `map` và `toList` trên bộ dữ liệu có thứ tự. Nó tạo hai báo cáo: **tổng từng batch hai đơn hàng đã thanh toán** và **tổng trượt ba đơn hàng đã thanh toán liên tiếp**.

```java
import java.util.List;
import java.util.stream.Gatherers;

public class GathererOrderReportDemo {

    record Order(String id, long amountVnd, boolean paid) {}

    record BatchMetric(
        List<String> orderIds,
        int count,
        long totalVnd
    ) {}

    static BatchMetric toMetric(List<Order> window) {
        List<String> ids = window.stream()
            .map(Order::id)
            .toList();

        long total = window.stream()
            .mapToLong(Order::amountVnd)
            .sum();

        return new BatchMetric(ids, window.size(), total);
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", 100_000L, true),
            new Order("O-02",  50_000L, false),
            new Order("O-03", 200_000L, true),
            new Order("O-04",  80_000L, true),
            new Order("O-05", 120_000L, true),
            new Order("O-06",  90_000L, false),
            new Order("O-07", 300_000L, true)
        );

        List<BatchMetric> fixedBatches = orders.stream()
            .filter(Order::paid)
            .gather(Gatherers.windowFixed(2))
            .map(GathererOrderReportDemo::toMetric)
            .toList();

        List<BatchMetric> movingBatches = orders.stream()
            .filter(Order::paid)
            .gather(Gatherers.windowSliding(3))
            .map(GathererOrderReportDemo::toMetric)
            .toList();

        System.out.println("FIXED");
        fixedBatches.forEach(System.out::println);

        System.out.println("SLIDING");
        movingBatches.forEach(System.out::println);
    }
}
```

Kết quả:

```text
FIXED
BatchMetric[orderIds=[O-01, O-03], count=2, totalVnd=300000]
BatchMetric[orderIds=[O-04, O-05], count=2, totalVnd=200000]
BatchMetric[orderIds=[O-07], count=1, totalVnd=300000]

SLIDING
BatchMetric[orderIds=[O-01, O-03, O-04], count=3, totalVnd=380000]
BatchMetric[orderIds=[O-03, O-04, O-05], count=3, totalVnd=400000]
BatchMetric[orderIds=[O-04, O-05, O-07], count=3, totalVnd=500000]
```

### 21.1. Vì sao kết quả có ý nghĩa nghiệp vụ?

- **`filter(Order::paid)`** loại hai đơn chưa thanh toán.
- **`windowFixed(2)`** nhóm các đơn còn lại theo lô hai đơn; lô cuối chỉ có một đơn.
- **`windowSliding(3)`** tính ba cửa sổ chồng lấn theo thứ tự của các đơn đã thanh toán.
- **`map(toMetric)`** chuyển mỗi cửa sổ thành đối tượng domain, có số đơn và tổng tiền.
- **`toList()`** là terminal operation tạo báo cáo cuối cùng.

Nếu cần tính theo **thời điểm thanh toán thực tế**, nguồn `orders` phải có thứ tự tương ứng. Một `List` giữ thứ tự nhập không mặc nhiên là thứ tự thời gian của nghiệp vụ.

### 21.2. Giới hạn số học

`long` vẫn có thể tràn nếu tổng tiền quá lớn. Với tổng số nguyên vượt miền 64 bit, dùng `BigInteger`. Với tiền thập phân, dùng `BigDecimal` theo chính sách làm tròn và đơn vị tiền tệ. Gatherer không thay đổi giới hạn của kiểu số.

## 22. Kiểm thử Gatherer và pipeline đúng cách

Các bài test nhỏ nên kiểm tra **kết quả công khai** và các biên của input, thay vì dựa vào lớp triển khai nội bộ hay số lần gọi callback.

### 22.1. Test cửa sổ dựng sẵn

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererContractDemo {
    public static void main(String[] args) {
        var fixed = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowFixed(3))
            .toList();

        var sliding = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowSliding(3))
            .toList();

        var shortInput = Stream.of(1, 2)
            .gather(Gatherers.windowSliding(3))
            .toList();

        var empty = Stream.<Integer>empty()
            .gather(Gatherers.windowFixed(3))
            .toList();

        if (!fixed.equals(List.of(
                List.of(1, 2, 3),
                List.of(4, 5)))) {
            throw new AssertionError("fixed mismatch");
        }

        if (!sliding.equals(List.of(
                List.of(1, 2, 3),
                List.of(2, 3, 4),
                List.of(3, 4, 5)))) {
            throw new AssertionError("sliding mismatch");
        }

        if (!shortInput.equals(List.of(List.of(1, 2)))) {
            throw new AssertionError("short-input mismatch");
        }

        if (!empty.isEmpty()) {
            throw new AssertionError("empty-input mismatch");
        }

        System.out.println("All checks passed");
    }
}
```

### 22.2. Test với custom Gatherer

Với một Gatherer tự viết, cần kiểm tra:

1. Nguồn rỗng, một phần tử, nhiều phần tử.
2. Trạng thái ban đầu và kết quả qua từng phần tử.
3. Việc phát nhiều đầu ra hoặc không phát đầu ra.
4. Cách ứng xử khi downstream từ chối.
5. Kết quả khi một integrator tự dừng.
6. Trường hợp ngoại lệ trong integrator/finisher.
7. Khả năng chia và gộp trạng thái nếu có combiner.
8. Đầu vào có thứ tự so với không có thứ tự.
9. Mọi ràng buộc về I/O, đóng tài nguyên và kiểu số.

Nếu dùng `Integrator.ofGreedy`, ngoài test phải review rằng **không có đường `return false` do điều kiện nghiệp vụ nội bộ**. Đó là **hợp đồng**, không chỉ là một đặc điểm chạy thử trên một máy.

## 23. Hiệu năng: khi nào Gatherer mang lại lợi ích?

Gatherer có thể giảm nhu cầu viết một vòng lặp nhiều trạng thái khó tái sử dụng, nhưng **không bảo đảm nhanh hơn** code tuần tự, thao tác Stream chuẩn hoặc một vòng lặp được tối ưu tốt.

Những yếu tố chính:

| Yếu tố | Tác động |
| --- | --- |
| Kích thước cửa sổ `k` | Trạng thái và bộ nhớ tăng theo số phần tử phải giữ |
| Số cửa sổ được phát | `windowSliding(k)` có thể phát gần `N` cửa sổ khi `N` lớn |
| Chi phí tính chỉ số | Mỗi lần `window.stream().sum()` duyệt lại phần tử trong cửa sổ |
| Thứ tự encounter order | Ràng buộc thứ tự có thể giới hạn khả năng chia và gộp |
| Combiner của custom Gatherer | Nếu không có cách gộp đúng, dễ phải chạy tuần tự |
| Boxing và cấp phát | `Stream<Integer>` và `List<Integer>` có thể cấp phát nhiều hơn luồng primitive |
| I/O và tác vụ đồng thời | `mapConcurrent` hữu ích cho một số công việc có thời gian chờ nhưng có giới hạn tài nguyên |

Ví dụ, nếu cần duy nhất **tổng trượt với cửa sổ `k` rất lớn**, việc tạo `List<T>` rồi tính lại tổng cho từng cửa sổ có thể đắt hơn một custom Gatherer giữ tổng đang chạy và bỏ phần tử cũ nhất. Tuy nhiên, custom Gatherer phải được kiểm tra kỹ về:

- Tràn số khi cộng và trừ.
- Độ chính xác số thực nếu dùng `double`.
- Cửa sổ thiếu phần tử.
- Nguồn không có encounter order.
- Dừng sớm, ngoại lệ và trạng thái.
- Khả năng chạy song song.

**Tối ưu sau khi tính đúng.** Dùng dữ liệu đại diện và công cụ benchmark như JMH; không rút kết luận từ một lần gọi `System.nanoTime()`.

## 24. Tương thích Java 17/21: phải làm gì khi chưa thể nâng JDK?

Dù Stream Gatherers đã chính thức từ Java 24, nhiều ứng dụng vẫn đặt minimum runtime là Java 17 hoặc 21. Khi đó không thể gọi trực tiếp `Stream.gather` của JDK 24.

Có ba hướng:

- Sử dụng các thao tác Stream đã tồn tại (`filter`, `map`, `flatMap`, `reduce`, `collect`) nếu đủ diễn đạt yêu cầu.
- Dùng vòng lặp, `Iterator` hoặc `Spliterator` tùy chỉnh để tự tổ chức cửa sổ/trạng thái.
- Tách phần yêu cầu Java 24+ vào một module/phiên bản triển khai riêng và xác định rõ runtime bắt buộc.

Ví dụ thay `windowFixed` bằng một vòng lặp trên `List` hữu hạn trong Java 17:

```java
import java.util.ArrayList;
import java.util.List;

public class FixedWindowsLegacy {
    public static <T> List<List<T>> groupBySize(List<T> input, int size) {
        if (size < 1) {
            throw new IllegalArgumentException("size must be positive");
        }

        List<List<T>> result = new ArrayList<>();

        for (int start = 0; start < input.size();) {
            int end = start + Math.min(size, input.size() - start);
            result.add(List.copyOf(input.subList(start, end)));
            start = end;
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(groupBySize(
            List.of(1, 2, 3, 4, 5), 2
        )); // [[1, 2], [3, 4], [5]]
    }
}
```

Đây là một giải pháp **tương đương về kết quả với danh sách hữu hạn không chứa null**, không phải một bản sao đầy đủ của Gatherer. Nó vật hóa các nhóm, không là intermediate operation lazy và không có cùng hợp đồng dừng sớm hoặc song song.

Khi tổ chức dự án nhiều JDK, phải kiểm tra **JDK biên dịch, `--release`, JDK chạy test, môi trường CI và runtime thực tế**. Bật `--enable-preview` ở Java 17/21 không bổ sung API Gatherers của Java 24.

## 25. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Nghĩ `Gatherer` và `Gatherers` là cùng một thứ | Nhầm interface với factory | Phân biệt `Gatherer`, `Gatherers` và `Stream.gather` |
| Gọi `gather` trên JDK 17/21 | API chưa tồn tại | Nâng JDK hoặc chọn giải pháp tương thích |
| Dùng JDK 22/23 nhưng quên preview flags | Biên dịch/chạy không hợp lệ | Bật preview ở compiler và runtime phù hợp JDK |
| Nghĩ `gather` là terminal operation | Hiểu sai thời điểm thực thi | Nhớ `gather` trả một Stream trung gian |
| Dùng Gatherer để thay `map` đơn giản | Tăng độ phức tạp không cần thiết | Ưu tiên `map` hoặc `filter` có sẵn |
| Nhầm `windowSliding(3)` với ba phút gần nhất | Kết quả không đúng theo thời gian | Thiết kế cửa sổ timestamp rõ ràng |
| Nghĩ `windowFixed` bỏ nhóm cuối thiếu mẫu | Mất hoặc tính sai phần cuối | Kiểm tra kích thước nhóm theo yêu cầu |
| Nghĩ `windowSliding(k)` luôn phát nhóm đủ k | Nguồn ngắn vẫn có cửa sổ ngắn | Xử lý trường hợp `0 < N < k` |
| Đặt `filter` trước `gather` rồi tưởng vẫn nhóm trên dữ liệu ban đầu | Thay đổi ranh giới lô | Xác định rõ thứ tự pipeline |
| Dùng `IntStream.gather` trực tiếp | Không có API đó | Chuyển bằng `boxed()` hoặc dùng thuật toán primitive |
| Dùng một `ArrayList` mutable global cho kết quả song song | Data race hoặc thứ tự sai | Dùng `toList`/`collect` |
| Dùng `Integrator.ofGreedy` nhưng tự dừng vì marker | Vi phạm hợp đồng Greedy | Dùng Integrator thông thường |
| Bỏ qua giá trị `downstream.push` khi phát nhiều phần tử | Tiếp tục làm việc sau từ chối | Dừng phát khi `push` trả `false` |
| Dùng `parallel()` và tưởng Gatherer tự chạy nhanh hơn | Chi phí chia/gộp có thể vượt lợi ích | Benchmark và kiểm tra combiner |
| Quên đóng `Files.lines` sau `gather` | Rò rỉ tài nguyên I/O | `try-with-resources` |
| Lưu toàn bộ cửa sổ lớn bằng `toList` | Bộ nhớ tăng mạnh | Chỉ giữ metrics cần thiết hoặc dùng Gatherer incremental |
| Tính tiền bằng `double` và mong chính xác tuyệt đối | Sai số số thực nhị phân | Dùng `BigDecimal` theo quy tắc làm tròn |

## 26. Bài tập thực hành

### Bài 1: Nhận diện vai trò ba tên API

Giải thích sự khác nhau giữa `Stream.gather(...)`, `Gatherer<T,A,R>` và `Gatherers`. Trong biểu thức `orders.stream().gather(Gatherers.windowFixed(10))`, thành phần nào tạo Gatherer và thành phần nào áp dụng Gatherer?

### Bài 2: So sánh `filter` và Gatherer

Cho `List.of(1, 2, 3, 4, 5)`. Dùng `filter` lấy mọi số chẵn. Sau đó viết một custom Gatherer có Greedy Integrator chỉ phát số chẵn. Giải thích vì sao `filter` vẫn là lựa chọn khuyến nghị.

### Bài 3: Hai kiểu cửa sổ

Với `[1,2,3,4,5,6,7]` và `k=3`, viết tay kết quả của `windowFixed` và `windowSliding`, rồi chạy bằng Java 24. Đếm số cửa sổ bằng công thức tương ứng.

### Bài 4: Nguồn ngắn hơn cửa sổ

Với `[1,2]` và `k=4`, dự đoán đầu ra của cả hai Gatherer cửa sổ. Hãy viết pipeline chỉ giữ cửa sổ có `size() == 4` và giải thích vì sao kết quả rỗng.

### Bài 5: Scan và reduce

Với `[2,3,5]`, viết một pipeline `scan` cho `[2,5,10]` và một pipeline `reduce`/`sum` cho `10`. Hai kết quả khác nhau về **số lượng đầu ra** và vị trí trong pipeline thế nào?

### Bài 6: Custom Integrator

Viết Gatherer tự nhận từng `String` và phát độ dài chuỗi. Dùng `Integrator.ofGreedy`. Sau đó thêm điều kiện “dừng nếu gặp `STOP`” và giải thích vì sao phải đổi sang Integrator thông thường.

### Bài 7: Custom stateful Gatherer

Tạo Gatherer phát tổng chạy của `[3,5,-2,9]`. Trạng thái phải được tạo ở đâu? Vì sao dùng `ofSequential` và không giữ một mảng static chung?

### Bài 8: Báo cáo log

Đọc một tệp log bằng `Files.lines`, gom mỗi 100 dòng gốc với `windowFixed(100)` rồi đếm số dòng chứa `ERROR` trong mỗi nhóm. So sánh với pipeline lọc dòng trống **trước** khi gom. Cả hai có cùng định nghĩa lô không?

### Bài 9: Primitive Stream

Từ `IntStream.range(0, 100)`, dùng `boxed` rồi `windowFixed(10)`. Phân tích chi phí boxing và bộ nhớ, sau đó đề xuất trường hợp không nên dùng Gatherer.

### Bài 10: Ngữ nghĩa song song

Dùng `parallelStream` với `windowSliding(3)` trên một `List` có thứ tự. So sánh kết quả với tuần tự. Vì sao phải kiểm tra thứ tự và combiner, và tại sao `parallel()` không bảo đảm tốc độ cao hơn?

### Bài 11: Không có JDK 24

Đề xuất cách tạo batch ba phần tử trong ứng dụng buộc chạy Java 17. So sánh vòng lặp trên `List` với cách dùng Gatherer chuẩn trên Java 24 theo khả năng xử lý lazy và tiêu thụ bộ nhớ.

### Bài 12: Quyết định chọn API

Với yêu cầu “trung bình 10 phép đo gần nhất của từng thiết bị theo timestamp”, hãy mô tả pipeline hoặc kiến trúc trước khi viết code. Cần đặt câu hỏi gì về thiết bị, thứ tự timestamp, bản ghi đến muộn và trường hợp ít hơn 10 mẫu?

## 27. Câu hỏi tự kiểm tra

- `Stream.gather` là intermediate hay terminal operation?
- `Gatherer`, `Gatherers` và `gather` có vai trò gì?
- Vì sao `Gatherer<T,A,R>` có ba tham số kiểu?
- `initializer`, `integrator`, `combiner` và `finisher` giải quyết việc gì?
- Một Integrator có được phép phát 0 hoặc nhiều phần tử khi nhận một phần tử không?
- `windowFixed(k)` khác `windowSliding(k)` như thế nào?
- Điều gì xảy ra với `windowSliding(3)` khi nguồn chỉ có hai phần tử?
- `scan` và `fold` khác nhau như thế nào về thời điểm/số lượng đầu ra?
- Khi nào `mapConcurrent` có thể phù hợp hơn `parallelStream`?
- `Integrator.ofGreedy` cam kết điều gì? Khi nào phải dùng Integrator thường?
- Vì sao `ofSequential` liên quan đến khả năng gộp trạng thái nhưng không đồng nghĩa Greedy?
- Vì sao không có `IntStream.gather` trực tiếp trong Java 24?
- Vai trò của encounter order đối với các cửa sổ là gì?
- Khi nào Gatherer chỉ làm code phức tạp hơn `map`/`filter`?
- Vì sao `Files.lines` vẫn cần được đóng sau `gather`?
- Stream Gatherers ở trạng thái preview và final ở những phiên bản nào?

## 28. Tài liệu tham khảo

Các nguồn chuẩn để tra cứu hành vi API và sự thay đổi qua phiên bản:

1. [JEP 461 — Stream Gatherers (Preview)](https://openjdk.org/jeps/461): giai đoạn preview trong Java 22.
2. [JEP 473 — Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473): giai đoạn preview lần hai trong Java 23.
3. [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): chuẩn hóa từ Java 24.
4. [Java SE 24 — `Stream`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html): phương thức `gather` và hợp đồng pipeline.
5. [Java SE 24 — `Gatherer`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): initializer, integrator, combiner và finisher.
6. [Java SE 24 — `Gatherers`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html): `windowFixed`, `windowSliding`, `scan`, `fold` và `mapConcurrent`.
7. [Java SE 24 — `Gatherer.Integrator`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html): hành vi `integrate`, `of` và `ofGreedy`.
8. [Oracle — Stream Gatherers Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): hướng dẫn áp dụng Gatherer trong pipeline.

**Ghi nhớ:** **`Stream.gather(...)` là thao tác trung gian**, **`Gatherer` là hợp đồng mô tả cách xử lý** và **`Gatherers` cung cấp các Gatherer dựng sẵn**. Chúng mở rộng Stream API cho phép xử lý cửa sổ, trạng thái và phát nhiều kết quả trung gian nhưng **không thay thế** `filter`, `map`, `flatMap`, `reduce` hoặc `collect` khi các thao tác ấy đã phù hợp. Gatherers là **preview trên Java 22/23** và **chính thức từ Java 24**. Khi sử dụng, luôn kiểm tra thứ tự nguồn, quy tắc dừng, khả năng song song, kiểu số, vòng đời tài nguyên và chi phí bộ nhớ.
