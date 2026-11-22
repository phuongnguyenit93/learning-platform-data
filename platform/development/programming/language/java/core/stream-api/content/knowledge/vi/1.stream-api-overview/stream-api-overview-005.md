# Lựa chọn giữa vòng lặp và Stream theo bài toán

Java Stream API giúp mô tả cách **biến đổi, lọc và tổng hợp dữ liệu** theo một pipeline khai báo. Vòng lặp `for` hoặc `while` cho phép điều khiển trực tiếp từng bước thực thi. Cả hai đều là công cụ phù hợp trong Java; cách chọn tốt nhất phụ thuộc vào **bài toán, mức độ thay đổi trạng thái, yêu cầu về thứ tự và cách đo hiệu năng**.

Trong chủ đề tổng quan Stream API này, mục tiêu là biết khi nào nên viết pipeline `filter → map → reduce/collect`, khi nào nên giữ vòng lặp và cách đánh giá lựa chọn bằng các tiêu chí cụ thể. Các kỹ thuật như `groupingBy`, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers mở rộng khả năng của Stream nhưng không khiến Stream mặc nhiên tốt hơn vòng lặp.

## 1. Hai cách diễn đạt cùng một phép xử lý

Giả sử ứng dụng thương mại điện tử cần lấy mã của các đơn hàng **đã thanh toán** và có giá trị **từ 1.000.000 VND** trở lên, giữ nguyên thứ tự trong danh sách gốc.

Ví dụ hoàn chỉnh dưới đây dùng Java 17 trở lên (vì có `record` và `Stream.toList()`):

```java
import java.util.ArrayList;
import java.util.List;

public class LoopVsStream {
    record Order(String id, String customerId, long totalVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "C-01", 1_500_000, true),
            new Order("O-02", "C-02",   800_000, true),
            new Order("O-03", "C-01", 2_000_000, false),
            new Order("O-04", "C-03", 1_200_000, true)
        );

        // Cách 1: vòng lặp - mô tả từng bước xử lý.
        List<String> idsByLoop = new ArrayList<>();
        for (Order order : orders) {
            if (order.paid() && order.totalVnd() >= 1_000_000) {
                idsByLoop.add(order.id());
            }
        }

        // Cách 2: Stream - mô tả chuỗi phép biến đổi.
        List<String> idsByStream = orders.stream()
            .filter(Order::paid)
            .filter(order -> order.totalVnd() >= 1_000_000)
            .map(Order::id)
            .toList();

        System.out.println(idsByLoop);              // [O-01, O-04]
        System.out.println(idsByStream);            // [O-01, O-04]
        System.out.println(idsByLoop.equals(idsByStream)); // true
    }
}
```

Ở cách dùng vòng lặp, lập trình viên chủ động kiểm tra điều kiện và thêm từng phần tử vào danh sách kết quả. Ở cách dùng Stream, các thao tác diễn đạt ý định: **lọc đơn phù hợp → lấy mã đơn → tạo danh sách**. Với nguồn `List` có thứ tự và pipeline tuần tự như ví dụ, hai cách cho kết quả có cùng thứ tự.

Điểm khác biệt quan trọng nằm ở **mô hình xử lý**, không phải khả năng giải bài toán. Vòng lặp phù hợp với luồng điều khiển phức tạp; Stream thường rõ nghĩa hơn khi công việc là chuỗi thao tác trên dữ liệu.

## 2. Hiểu pipeline trước khi quyết định

Một pipeline Stream gồm ba phần:

1. **Nguồn dữ liệu**: `list.stream()`, `Arrays.stream(array)`, `Files.lines(path)`,…
2. **Thao tác trung gian**: `filter`, `map`, `flatMap`, `distinct`, `sorted`,… trả về một Stream mới; phần lớn được đánh giá *lazy*.
3. **Thao tác kết thúc**: `toList`, `collect`, `count`, `sum` (trên primitive stream), `reduce`, `findFirst`, `anyMatch`, `forEach`,… kích hoạt quá trình xử lý.

```text
Nguồn                 Trung gian (lazy)                   Kết thúc
List<Order>  ──>  filter(paid) ──> mapToLong(totalVnd)  ──>  sum()
                         │                │                  │
                   chọn phần tử      đổi kiểu dữ liệu    tính kết quả
```

Ví dụ chỉ tạo pipeline mà **chưa chạy phép lọc**:

```java
var pipeline = orders.stream()
    .filter(Order::paid)
    .map(Order::id);

// Chưa có terminal operation nên các phần tử chưa được xử lý bởi filter/map.
List<String> paidIds = pipeline.toList(); // Bây giờ pipeline được tiêu thụ.
```

Mỗi Stream chỉ được sử dụng cho một lần tiêu thụ; muốn chạy một phép xử lý khác, hãy tạo Stream mới từ nguồn. Với các thao tác như `sorted` hoặc `distinct`, Stream có thể cần lưu trạng thái/buffer nội bộ. “Lazy” không có nghĩa là luôn dùng bộ nhớ hằng số hoặc lúc nào cũng xử lý một phần tử trọn vẹn rồi mới đến phần tử kế tiếp.

## 3. Ma trận lựa chọn theo bài toán

| Dấu hiệu của bài toán | Thường ưu tiên | Lý do |
| --- | --- | --- |
| Lọc, ánh xạ, chuyển đổi một tập phần tử thành kết quả mới | **Stream** | Pipeline thể hiện rõ `filter`, `map`, `collect` hoặc `toList`. |
| Đếm, tìm giá trị phù hợp, tổng hợp theo một phép toán có sẵn | **Stream hoặc vòng lặp** | `count`, `anyMatch`, `mapToLong().sum()` và `reduce` diễn đạt ngắn gọn; vòng lặp cũng rất rõ với phép tính đơn giản. |
| Nhóm dữ liệu, thống kê theo khóa | **Stream** khi `groupingBy` rõ nghĩa | Collector gói phép gom nhóm; nếu chính sách cập nhật trạng thái phức tạp, vòng lặp có thể dễ hiểu hơn. |
| Cần chỉ số phần tử, chỉnh sửa trực tiếp mảng/danh sách, hoặc phối hợp nhiều phép gán | **Vòng lặp** | Điều khiển chỉ số và các bước thay đổi trạng thái là phần chính của bài toán. |
| Cần `break` / `continue` / `return` ở nhiều nhánh hoặc dừng sau nhiều hành động | **Vòng lặp** | Luồng điều khiển tường minh; nếu chỉ “có tồn tại?” hay “lấy phần tử đầu tiên?”, `anyMatch`/`findFirst` cũng phù hợp. |
| Tính toán phụ thuộc vào kết quả của phần tử trước (số dư chạy, máy trạng thái) | **Vòng lặp** trong trường hợp cơ bản | Trạng thái tuần tự có thể rõ ràng hơn vòng lặp; các cách xử lý Stream nâng cao cần được cân nhắc riêng. |
| Xử lý nguồn có tài nguyên cần đóng, như `Files.lines` | **Cả hai**, quản lý tài nguyên đúng cách | Khi dùng Stream gắn với tệp, phải đóng bằng `try-with-resources`. |
| Đường chạy rất nóng, dữ liệu cực lớn, nhạy với cấp phát/boxing | **Đo đạc trước khi quyết định** | Overhead Stream có thể đáng kể, nhưng tối ưu thực tế còn tùy JVM, nguồn dữ liệu, phép tính và cách viết. |
| Tính toán CPU độc lập trên lượng dữ liệu đủ lớn | **Cân nhắc parallel Stream** sau đo đạc | Parallelism có overhead và ràng buộc về trạng thái, thứ tự, môi trường thực thi. |

Ma trận là điểm khởi đầu, không phải quy tắc bắt buộc. Nếu một pipeline Stream phải dùng nhiều thủ thuật để mô phỏng `break` hoặc cập nhật biến ngoài, vòng lặp thường diễn đạt ý định tốt hơn.

## 4. Các tình huống điển hình

### 4.1. Lọc, biến đổi và trả về một tập kết quả: Stream thường dễ đọc

Từ danh sách `orders` ở ví dụ đầu, tính tổng tiền của các đơn đã thanh toán:

```java
long totalPaidVnd = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::totalVnd)
    .sum();
```

Ở đây `mapToLong` tạo `LongStream` để tính tổng trực tiếp với kiểu nguyên thủy `long`, tránh tạo nhiều đối tượng `Long` như khi đưa dữ liệu qua `Stream<Long>`. Vòng lặp vẫn là lựa chọn tốt nếu phép tổng hợp chỉ có một điều kiện ngắn:

```java
long totalPaidVnd = 0L;
for (Order order : orders) {
    if (order.paid()) {
        totalPaidVnd += order.totalVnd();
    }
}
```

Hai đoạn cùng mô tả một phép cộng các giá trị thỏa điều kiện. Hãy chọn cách mà nhóm phát triển đọc nhanh và sửa ít sai sót hơn. Nếu dữ liệu tiền tệ yêu cầu phần thập phân hoặc giá trị có thể vượt giới hạn `long`, cần chọn mô hình số phù hợp (ví dụ `BigDecimal`) thay vì phụ thuộc vào cú pháp Stream.

### 4.2. Tìm kiếm và dừng sớm: xét rõ điều kiện dừng

Nếu chỉ cần biết **có đơn chưa thanh toán hay không**, `anyMatch` vừa ngắn vừa có thể dừng ngay khi gặp phần tử phù hợp:

```java
boolean hasUnpaidOrder = orders.stream()
    .anyMatch(order -> !order.paid());
```

Nếu cần lấy **đơn chưa thanh toán đầu tiên theo thứ tự danh sách**:

```java
var firstUnpaid = orders.stream()
    .filter(order -> !order.paid())
    .findFirst(); // Optional<Order>; có thể rỗng.
```

Vòng lặp cũng hỗ trợ dừng sớm:

```java
Order firstUnpaid = null;
for (Order order : orders) {
    if (!order.paid()) {
        firstUnpaid = order;
        break;
    }
}
```

Khi việc dừng sớm còn phải cập nhật nhiều biến, gọi nhiều thao tác có điều kiện hoặc báo lỗi tùy vị trí, vòng lặp thường dễ kiểm tra hơn. Đừng thay `break` bằng `forEach` rồi dựa vào cờ thay đổi bên ngoài lambda; `forEach` không cung cấp cơ chế `break` như vòng lặp.

Với nguồn Stream **có thứ tự**, `findFirst` tôn trọng phần tử đầu tiên theo thứ tự gặp. `findAny` không cam kết chọn phần tử đầu tiên, đặc biệt khi chạy song song.

### 4.3. Gom nhóm và thống kê: Stream giúp tập trung vào kết quả

Ví dụ đếm số đơn hàng theo khách hàng:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> numberOfOrdersByCustomer = orders.stream()
    .collect(Collectors.groupingBy(
        Order::customerId,
        Collectors.counting()
    ));
```

Nếu chỉ cần nhóm phần tử, `groupingBy(Order::customerId)` tạo map từ mã khách hàng đến danh sách đơn. Nếu cần cách gom đặc biệt, có thể cân nhắc các collector tích hợp khác hoặc **collector tùy chỉnh**. Tuy nhiên, một vòng lặp với `Map.merge` đôi khi ngắn và rõ hơn khi chỉ đếm:

```java
Map<String, Long> counts = new java.util.HashMap<>();
for (Order order : orders) {
    counts.merge(order.customerId(), 1L, Long::sum);
}
```

Thứ tự duyệt các khóa của `HashMap` và map do `groupingBy` mặc định trả về **không được bảo đảm**. Nếu kết quả có ràng buộc thứ tự, phải thể hiện ràng buộc đó một cách tường minh.

### 4.4. Trạng thái phụ thuộc phần tử trước: vòng lặp thường tự nhiên hơn

Hệ thống ví điện tử nhận các biến động số dư `[+100, -25, +40]` và cần trả về **số dư sau từng giao dịch**, lần lượt là `[100, 75, 115]`.

```java
List<Integer> changes = List.of(100, -25, 40);
List<Integer> runningBalances = new ArrayList<>();

int balance = 0;
for (int change : changes) {
    balance += change;
    runningBalances.add(balance);
}

System.out.println(runningBalances); // [100, 75, 115]
```

`reduce(0, Integer::sum)` chỉ cho ra **tổng cuối cùng** (`115`), không tạo ra các số dư trung gian. Cố ép phép quét có trạng thái này vào `map` bằng biến có thể thay đổi bên ngoài lambda dễ gây khó đọc và làm pipeline mất tính an toàn khi song song.

Nếu dự án thực sự cần một pipeline quét trạng thái, có thể tìm hiểu Stream Gatherers (trên các phiên bản JDK hỗ trợ) và đánh giá độ phức tạp so với vòng lặp. Với bài toán nhỏ như trên, vòng lặp có lợi thế rõ rệt.

### 4.5. Làm việc với chỉ số và sửa dữ liệu tại chỗ: ưu tiên vòng lặp

Một ví dụ tính toán tại chỗ trên mảng, trong đó **vị trí** là một phần của yêu cầu:

```java
int[] scores = {10, 20, 30};
for (int i = 0; i < scores.length; i++) {
    scores[i] += i; // [10, 21, 32]
}
```

`IntStream.range(0, scores.length)` cũng có thể biểu diễn chỉ số, nhưng nếu toàn bộ mục tiêu là sửa từng vị trí của cùng mảng thì vòng lặp thường ngắn và trực tiếp hơn. Với dữ liệu cần biến đổi thành **mảng mới**, Stream có thể phù hợp:

```java
int[] doubled = java.util.Arrays.stream(scores)
    .map(score -> score * 2)
    .toArray();
```

### 4.6. Dữ liệu từ tệp: cân nhắc quản lý tài nguyên và bộ nhớ

`Files.lines` cung cấp Stream đọc các dòng tệp. Nó có tài nguyên I/O nên cần được đóng, kể cả khi pipeline ném ngoại lệ:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("logs.txt");
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long nonEmptyLineCount = lines
        .filter(line -> !line.isBlank())
        .count();

    System.out.println(nonEmptyLineCount);
}
// Bối cảnh chứa đoạn mã cần xử lý hoặc khai báo throws IOException.
```

Chỉ nên `toList()` khi thật sự cần giữ các dòng trong bộ nhớ. Nếu cần xử lý từng dòng và ghi kết quả dần ra ngoài, vòng lặp với `BufferedReader` có thể giúp diễn đạt việc đọc, ghi, xử lý lỗi và dừng sớm rõ ràng hơn.

Lưu ý: `Stream.toList()` tạo danh sách **không cho phép sửa** (gọi `add` sẽ ném `UnsupportedOperationException`). Khi cần danh sách có thể thay đổi, hãy thể hiện yêu cầu đó tường minh:

```java
List<String> mutableIds = orders.stream()
    .map(Order::id)
    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
```

## 5. Hiệu năng: đánh giá chi phí thật, không suy đoán từ cú pháp

Không thể kết luận “Stream luôn chậm” hoặc “Stream luôn nhanh”. Cùng một phép toán, kết quả phụ thuộc dữ liệu đầu vào, JDK/JVM, độ nóng của đoạn mã, tối ưu JIT, số lần cấp phát, kiểu phần tử và cấu trúc pipeline.

Khi hiệu năng quan trọng, hãy xem xét:

- **Chi phí tạo pipeline và lời gọi lambda:** có thể đáng kể với phép tính rất nhỏ được lặp đi lặp lại trong đường chạy nóng.
- **Boxing/unboxing:** `Stream<Integer>` có thể tạo chi phí đối tượng; với các phép tính số học, cân nhắc `IntStream`, `LongStream`, `DoubleStream`.
- **Thao tác có trạng thái:** `sorted` hoặc `distinct` có thể cần thêm bộ nhớ; `sorted` thường phải thu thập nhiều phần tử trước khi tạo kết quả.
- **Thu thập dữ liệu:** `toList` lưu kết quả vào bộ nhớ, trong khi vòng lặp hoặc pipeline xử lý từng kết quả có thể giảm bộ nhớ lưu trữ tùy bài toán.
- **Dừng sớm:** `findFirst`, `anyMatch`, `limit` có thể giảm phần tử phải đọc; hiệu quả còn tùy thứ tự thao tác và nguồn.
- **I/O, mạng và cơ sở dữ liệu:** thời gian chờ bên ngoài thường lớn hơn chênh lệch cú pháp giữa vòng lặp và Stream.

Khi cần quyết định cho đường chạy quan trọng, hãy viết hai phiên bản **cùng ngữ nghĩa**, dùng dữ liệu đại diện và đo bằng công cụ thích hợp như **JMH** sau khi JVM đã warm-up. Không đo bằng một lần gọi `System.nanoTime()` rồi khái quát cho mọi trường hợp. Đặc biệt, xác minh hai phiên bản cùng xử lý dữ liệu, cùng thứ tự nếu thứ tự là yêu cầu, và không bỏ qua công việc để làm benchmark trông nhanh hơn.

### Có nên gọi `parallelStream()`?

Parallel Stream có thể có lợi khi số phần tử đủ lớn, mỗi phép xử lý tương đối nặng, độc lập, không có tác dụng phụ và có khả năng chia việc hiệu quả. Nó **không tự động nhanh hơn** Stream tuần tự hoặc vòng lặp. Chi phí chia/ghép, đồng bộ, tính thứ tự và việc dùng tài nguyên CPU chung có thể khiến kết quả tệ hơn.

Ví dụ sau chỉ minh họa một phép tổng hợp có thể song song hóa về mặt ngữ nghĩa:

```java
long totalPaid = orders.parallelStream()
    .filter(Order::paid)
    .mapToLong(Order::totalVnd)
    .sum();
```

Với vài đơn hàng như ví dụ, không có lý do thực tiễn để dùng song song. Không sử dụng `parallelStream().forEach(...)` để cùng thêm phần tử vào một `ArrayList` được chia sẻ: hành vi cập nhật đồng thời đó không an toàn. Nếu phải xử lý song song, hãy ưu tiên các phép giảm/collector phù hợp và kiểm tra yêu cầu về thứ tự. Khi cần kiểm soát tách dữ liệu, `Spliterator` là một khái niệm liên quan nhưng không phải giải pháp mặc định cho các pipeline thông thường.

## 6. Các lỗi dễ xảy ra khi đổi vòng lặp sang Stream

| Biểu hiện | Vì sao có vấn đề | Cách làm phù hợp |
| --- | --- | --- |
| `stream().filter(...).map(...);` mà không có terminal operation | Pipeline trung gian chưa được tiêu thụ | Thêm `toList`, `collect`, `count`, `forEach` hoặc terminal phù hợp. |
| `stream.forEach(x -> result.add(transform(x)))` | Thay đổi danh sách ngoài lambda che giấu ý định; không an toàn nếu chạy song song | Dùng `map(...).toList()` khi cần tập kết quả mới. |
| Thay mọi vòng lặp bằng Stream dù cần `break` và nhiều bước cập nhật | Luồng điều khiển trở nên vòng vèo | Giữ vòng lặp nếu thao tác điều khiển là yêu cầu chính. |
| Dùng `peek` để thực hiện nghiệp vụ | `peek` thiên về quan sát/debug; một số tối ưu có thể bỏ qua việc gọi ở pipeline nhất định | Đưa biến đổi vào `map`, dùng terminal phù hợp hoặc vòng lặp có tác dụng phụ tường minh. |
| Gọi hai terminal operation trên cùng một Stream | Stream chỉ tiêu thụ một lần | Tạo lại Stream từ nguồn cho phép tính kế tiếp. |
| Giả định `toList()` trả về danh sách sửa được | Kết quả của `Stream.toList()` không thể thêm/xóa phần tử | Dùng `Collectors.toCollection(ArrayList::new)` nếu cần danh sách mutable. |
| Bật song song rồi ghi vào biến/tập hợp dùng chung | Có thể xảy ra race condition hoặc kết quả sai | Tránh trạng thái chia sẻ; dùng phép gom/giảm an toàn và đo hiệu năng. |

Ví dụ về **tác dụng phụ không cần thiết** và cách thay thế:

```java
// Khó mở rộng sang xử lý song song, vì cập nhật list ở ngoài pipeline.
List<String> ids = new ArrayList<>();
orders.stream()
    .filter(Order::paid)
    .forEach(order -> ids.add(order.id()));

// Biểu diễn đúng dữ liệu đầu ra, không cần thay đổi trạng thái ngoài.
List<String> paidIds = orders.stream()
    .filter(Order::paid)
    .map(Order::id)
    .toList();
```

`forEach` không sai khi mục tiêu thực sự là **hành động trên từng phần tử** (chẳng hạn in thông tin); vấn đề là dùng nó để giả lập một phép `map + collect` với trạng thái ngoài. Khi thứ tự hành động là yêu cầu, cần chú ý `forEach` của parallel Stream không bảo đảm thứ tự gặp; `forEachOrdered` có ngữ nghĩa thứ tự khác và có thể làm mất lợi thế song song.

## 7. Quy trình quyết định thực tế

Để chọn nhanh trong một bài toán mới, đi theo trình tự sau:

1. **Viết rõ đầu vào và đầu ra.** Nếu kết quả là “lọc → biến đổi → trả về tập giá trị” hoặc một phép tổng hợp có sẵn, thử Stream trước.
2. **Xác định sự phụ thuộc trạng thái và luồng điều khiển.** Nếu phải quản lý chỉ số, trạng thái từ phần tử trước, nhiều nhánh `break`/`continue` hoặc cập nhật tại chỗ, thử vòng lặp trước.
3. **Kiểm tra ràng buộc thứ tự và tính dừng sớm.** Chọn `findFirst` thay vì `findAny` khi thật sự cần phần tử đầu tiên; dùng `anyMatch` nếu chỉ cần câu trả lời có/không.
4. **Nhận diện tài nguyên và kích thước dữ liệu.** Đóng Stream có nguồn I/O; tránh thu thập mọi phần tử nếu không cần giữ kết quả.
5. **So sánh khả năng đọc, tính đúng và hiệu năng tại chỗ.** Chọn cách có ý nghĩa rõ nhất cho nhóm phát triển; chỉ tối ưu đường nóng sau khi đo.

Một quy tắc kiểm tra hữu ích: hãy thử mô tả bài toán bằng động từ. Nếu câu mô tả tự nhiên là “**lọc** bản ghi, **ánh xạ** trường, **nhóm** theo khóa, **tính tổng**”, Stream là ứng viên tốt. Nếu câu mô tả là “**duyệt đến khi**, **cập nhật trạng thái**, **quay lại vị trí trước**, **dừng ở nhánh này**”, vòng lặp thường phù hợp hơn.

## 8. Bài tập tự kiểm tra

1. Cho danh sách sinh viên, cần lọc sinh viên đạt điểm từ 8 trở lên rồi lấy danh sách email. Hãy viết cả vòng lặp và Stream, giải thích cách nào thể hiện kết quả rõ hơn.
2. Cho mảng các giao dịch đã sắp theo thời gian, cần tìm giao dịch lỗi đầu tiên. Hãy so sánh `for + break` với `filter + findFirst`. Điều gì xảy ra khi không có giao dịch lỗi?
3. Cho dãy thay đổi nhiệt độ, cần tạo dãy **nhiệt độ tích lũy sau mỗi bước**. Vì sao `reduce` không đủ để trả về toàn bộ các giá trị trung gian?
4. Cho 10 triệu số nguyên, cần tính tổng các số chẵn. Hãy thử vòng lặp, `IntStream` tuần tự và song song bằng một benchmark hợp lý; ghi nhận cả độ đúng, bộ nhớ và chi phí chạy.
5. Cho tệp log lớn, cần đếm dòng chứa từ khóa. Hãy viết xử lý đóng tài nguyên đúng cách và giải thích tại sao tạo một `List<String>` cho toàn bộ tệp có thể không cần thiết.

**Ghi nhớ:** Stream mạnh khi bài toán là **chuỗi biến đổi dữ liệu có thể biểu diễn bằng các phép toán khai báo**. Vòng lặp mạnh khi bài toán đòi hỏi **điều khiển và trạng thái tường minh**. Biết cách chuyển đổi giữa hai cách giúp tận dụng Java Stream API mà vẫn giữ mã nguồn rõ ràng, đúng và dễ bảo trì.
