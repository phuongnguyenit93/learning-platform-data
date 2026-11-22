# Stream API là gì và giải quyết bài toán nào?

Trong ứng dụng Java, dữ liệu thường đi qua một chuỗi thao tác: lấy danh sách đơn hàng, bỏ đơn chưa thanh toán, chọn số tiền, tính tổng hoặc nhóm theo danh mục. **Java Stream API** giúp diễn đạt chuỗi xử lý đó dưới dạng một *pipeline* (đường ống xử lý dữ liệu) với các phép biến đổi và tổng hợp có thể kết hợp với nhau.

Stream API xuất hiện từ **Java 8**, nằm chủ yếu trong gói `java.util.stream`. Nó cung cấp cách viết **khai báo**: mô tả *muốn lấy kết quả gì từ dữ liệu*, thay vì tự điều khiển từng bước duyệt bằng vòng lặp và biến tích lũy. Stream không phải cấu trúc lưu trữ mới, cũng không tự động làm chương trình nhanh hơn.

Sau bài này, bạn có thể nhận diện bài toán phù hợp với Stream API, đọc được pipeline từ nguồn đến kết quả, phân biệt phép toán trung gian và kết thúc, đồng thời biết các giới hạn quan trọng trước khi áp dụng.

## 1. Bài toán thực tế: từ dữ liệu thô đến kết quả

Giả sử một hệ thống bán hàng cần:

- Chỉ lấy các đơn **đã thanh toán**.
- Tính **tổng số tiền** của các đơn đó.
- Đếm số đơn đã thanh toán **theo danh mục sản phẩm**.

Với vòng lặp truyền thống, lập trình viên tự quản lý việc duyệt, điều kiện, biến tổng và bản đồ đếm. Với Stream API, mỗi yêu cầu được biểu diễn bằng một phép toán trong pipeline.

Ví dụ hoàn chỉnh dưới đây chạy trên **JDK 17 trở lên** (sử dụng `record` để biểu diễn dữ liệu mẫu). Các phép toán Stream cốt lõi trong ví dụ đã có từ Java 8.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class StreamOverviewDemo {
    record Order(String id, String category, int amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", "Sách", 120_000, true),
            new Order("DH02", "Sách",  90_000, false),
            new Order("DH03", "Bút",   30_000, true),
            new Order("DH04", "Sách",  50_000, true)
        );

        // Cách viết mệnh lệnh: tự duyệt và cập nhật biến.
        int totalWithLoop = 0;
        for (Order order : orders) {
            if (order.paid()) {
                totalWithLoop += order.amount();
            }
        }

        // Cách viết khai báo: mô tả chuỗi xử lý dữ liệu.
        int totalWithStream = orders.stream()
            .filter(Order::paid)
            .mapToInt(Order::amount)
            .sum();

        // Một bài toán khác trên cùng nguồn: nhóm và đếm.
        Map<String, Long> paidCountByCategory = orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::category,
                Collectors.counting()
            ));

        System.out.println(totalWithLoop);                 // 200000
        System.out.println(totalWithStream);               // 200000
        System.out.println(paidCountByCategory.get("Sách")); // 2
        System.out.println(paidCountByCategory.get("Bút"));  // 1
    }
}
~~~

Điểm đáng chú ý không phải Stream giúp viết ít dòng trong mọi tình huống, mà là **ý nghĩa của từng bước được thể hiện rõ**:

1. `orders.stream()`: tạo Stream từ danh sách đơn hàng.
2. `filter(Order::paid)`: giữ lại đơn đã thanh toán.
3. `mapToInt(Order::amount)`: lấy số tiền ở dạng luồng số nguyên nguyên thủy (`IntStream`).
4. `sum()`: tính tổng và trả về một giá trị `int`.
5. Trong pipeline thứ hai, `collect(groupingBy(..., counting()))` tạo bản đồ số đơn theo danh mục.

Hai pipeline tạo **hai Stream độc lập** từ cùng `List`. Danh sách gốc không bị thay đổi bởi những phép toán này. `Map` kết quả từ `groupingBy` không có bảo đảm về thứ tự duyệt các khóa; ví dụ kiểm tra từng khóa để tránh phụ thuộc thứ tự hiển thị.

> **Lưu ý về tiền tệ:** `int` chỉ làm ví dụ gọn và dễ đọc. Trong hệ thống thực tế cần xác định rõ đơn vị tiền, khả năng tràn số và quy tắc làm tròn; `BigDecimal` hoặc số nguyên biểu diễn đơn vị tiền nhỏ nhất thường phù hợp hơn tùy yêu cầu.

## 2. Stream thực chất là gì?

`Stream<T>` biểu diễn **một chuỗi phần tử để xử lý** (không nhất thiết là một danh sách đã lưu sẵn). Một Stream liên kết nguồn dữ liệu với các phép toán và thường chỉ duyệt nguồn khi cần kết quả.

Một pipeline điển hình có ba phần:

~~~mermaid
flowchart LR
    A["Nguồn: List<Order>"] --> B["Trung gian: filter(paid)"]
    B --> C["Trung gian: mapToInt(amount)"]
    C --> D["Kết thúc: sum()"]
    D --> E["Kết quả: 200000"]
~~~

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Nguồn (source)** | Cung cấp phần tử cho pipeline | `list.stream()`, `Arrays.stream(array)`, `Stream.of(...)` |
| **Phép toán trung gian (intermediate)** | Trả về một Stream mới để tiếp tục mô tả việc xử lý | `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit` |
| **Phép toán kết thúc (terminal)** | Kích hoạt việc tính toán cần thiết và tạo kết quả hoặc tác động cuối cùng | `sum`, `count`, `collect`, `reduce`, `findFirst`, `forEach` |

Một số điểm cần ghi nhớ:

- Stream **không sở hữu dữ liệu** theo nghĩa của một `List` hay `Set`. Nguồn có thể là collection, mảng, dãy số được sinh ra hoặc dữ liệu đọc dần.
- Những phép toán như `filter` và `map` nói chung **lazy**: tạo pipeline chưa có nghĩa là đã duyệt hết các phần tử.
- Mỗi Stream chỉ được **tiêu thụ một lần**. Sau phép toán kết thúc, muốn chạy một pipeline mới phải tạo Stream mới từ nguồn.
- Stream xử lý phần tử theo hợp đồng của từng phép toán; nó **không mặc nhiên sửa nguồn dữ liệu** và cũng không bảo đảm mọi phép toán đều không cần bộ nhớ trung gian.

### Stream khác Collection ở đâu?

| `Collection` (ví dụ `List`) | `Stream` |
|---|---|
| Quản lý một tập hợp phần tử | Mô tả quá trình xử lý phần tử |
| Có thể đọc hoặc duyệt lại nhiều lần | Thông thường chỉ tiêu thụ một lần |
| Hỗ trợ các thao tác lưu trữ như thêm, xóa | Cung cấp các phép toán biến đổi, lọc, tổng hợp |
| Phần tử đang được chứa trong collection | Phần tử có thể được lấy hoặc sinh ra khi pipeline chạy |

Có thể hiểu: **collection là nơi giữ dữ liệu; stream là cách diễn đạt công việc trên dữ liệu**. Một danh sách có thể tạo nhiều Stream khác nhau, còn kết quả của Stream có thể là một số, `Optional`, `Map`, `List` hoặc một kiểu khác.

## 3. Pipeline hoạt động: khai báo trước, xử lý khi cần

Đây là đặc điểm giúp Stream API khác với việc gọi liên tiếp những hàm luôn tạo danh sách trung gian.

~~~java
import java.util.Optional;
import java.util.stream.Stream;

Stream<Integer> evenNumbers = Stream.of(1, 2, 3, 4)
    .filter(n -> {
        System.out.println("Đang xét: " + n);
        return n % 2 == 0;
    });

System.out.println("Đã khai báo pipeline");

Optional<Integer> firstEven = evenNumbers.findFirst();
System.out.println(firstEven.orElse(-1));
~~~

Kết quả quan sát trong trường hợp này:

~~~text
Đã khai báo pipeline
Đang xét: 1
Đang xét: 2
2
~~~

Khi khai báo `filter`, chưa có phần tử nào được kiểm tra. `findFirst()` là phép toán kết thúc; nó yêu cầu phần tử chẵn đầu tiên nên việc duyệt **dừng ngay khi tìm thấy số 2**. Đây là cơ chế *short-circuit* (dừng sớm) của một số phép toán, bao gồm `findFirst`, `anyMatch` và `limit` khi điều kiện áp dụng cho phép.

Đoạn in log bên trong `filter` chỉ nhằm minh họa. Trong code nghiệp vụ, nên giữ hàm lọc và biến đổi **không có tác dụng phụ** để kết quả dễ hiểu, dễ kiểm thử và an toàn hơn khi thay đổi cách thực thi.

### Vì sao không thể tái sử dụng cùng Stream?

~~~java
Stream<Integer> numbers = Stream.of(1, 2, 3);
long quantity = numbers.count(); // 3

// numbers.filter(n -> n > 1).count();
// Không hợp lệ: Stream đã được tiêu thụ; thường ném IllegalStateException.

// Cách đúng: tạo Stream khác từ nguồn có thể dùng lại.
List<Integer> source = List.of(1, 2, 3);
long all = source.stream().count();
long greaterThanOne = source.stream().filter(n -> n > 1).count();
~~~

Thực tế còn có những phép toán kết thúc cho kết quả rỗng một cách hợp lệ. Ví dụ, `findFirst()` trả về `Optional<T>` vì nguồn có thể không chứa phần tử phù hợp. Hãy dùng `orElse`, `orElseGet`, `ifPresent` hoặc xử lý trường hợp rỗng thay vì gọi `get()` một cách mặc định.

## 4. Stream API giải quyết những dạng bài toán nào?

| Dạng nhu cầu | Câu hỏi nghiệp vụ | Phép toán thường gặp |
|---|---|---|
| **Lọc** | Đơn nào đã thanh toán? | `filter` |
| **Chiếu/biến đổi** | Lấy email từ danh sách khách hàng? | `map` |
| **Làm phẳng** | Gom các mặt hàng từ nhiều đơn thành một luồng? | `flatMap` |
| **Tìm kiếm/kiểm tra** | Có đơn nào quá hạn không? | `findFirst`, `anyMatch`, `allMatch` |
| **Giới hạn/sắp xếp/khử trùng** | Lấy 10 mã sản phẩm khác nhau theo thứ tự? | `distinct`, `sorted`, `limit` |
| **Tổng hợp** | Tổng doanh thu hoặc số lượng đơn là bao nhiêu? | `mapToInt`, `sum`, `count`, `reduce` |
| **Gom nhóm** | Mỗi danh mục có bao nhiêu đơn? | `collect`, `Collectors.groupingBy` |
| **Tạo kết quả** | Thu được `List`, `Set` hoặc `Map` nào? | `toList`, `collect` |

Một pipeline thường kết hợp nhiều thao tác để trả lời một câu hỏi hoàn chỉnh. Ví dụ: “Lấy tên duy nhất của những khách đã thanh toán, sắp xếp theo bảng chữ cái” có thể được diễn đạt thành `filter → map → distinct → sorted → toList`.

### Các nguồn dữ liệu phổ biến

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

List<String> names = List.of("An", "Bình", "Chi");
Stream<String> fromList = names.stream();

Stream<String> fromArray = Arrays.stream(new String[] {"An", "Bình"});
Stream<String> fromValues = Stream.of("An", "Bình");

// Không phải tất cả Stream đều chứa object:
IntStream numbers = IntStream.rangeClosed(1, 5); // 1, 2, 3, 4, 5

System.out.println(fromList.count());           // 3
System.out.println(fromArray.count());          // 2
System.out.println(fromValues.count());         // 2
System.out.println(numbers.sum());              // 15
~~~

`IntStream`, `LongStream` và `DoubleStream` tránh chi phí boxing trong nhiều phép tính số học, đồng thời có các phép toán như `sum`, `average`, `max`. Với Stream đối tượng, `mapToInt` hoặc `mapToLong` thường là bước chuyển hợp lý trước khi tổng hợp số.

Nguồn không nhất thiết hữu hạn: `Stream.generate(...)` hoặc `Stream.iterate(...)` có thể tạo dãy dài không giới hạn. Phải thiết kế phép toán kết thúc và điều kiện dừng phù hợp; ví dụ dùng `limit` khi muốn lấy một số lượng hữu hạn.

## 5. Vì sao cách viết khai báo hữu ích?

### Diễn đạt sát yêu cầu

`filter` đọc như “giữ các phần tử thỏa điều kiện”, `map` đọc như “chuyển từng phần tử”, còn `collect` đọc như “gom kết quả”. Khi chuỗi thao tác nhỏ, tách bạch và có tên tốt, người đọc có thể đi theo luồng dữ liệu mà ít phải theo dõi biến đếm hoặc trạng thái tạm.

### Dễ kết hợp và thay đổi quy tắc

Cùng nguồn đơn hàng có thể sinh các kết quả khác nhau:

~~~java
long paidOrders = orders.stream()
    .filter(Order::paid)
    .count();

boolean hasUnpaidOrders = orders.stream()
    .anyMatch(order -> !order.paid());

List<String> paidCategories = orders.stream()
    .filter(Order::paid)
    .map(Order::category)
    .distinct()
    .sorted()
    .toList(); // JDK 16+: List kết quả không cho phép sửa.
~~~

Các đoạn trên được đặt trong ngữ cảnh lớp và biến `orders` của ví dụ đầu bài. Mỗi đoạn gọi `orders.stream()` riêng để bảo đảm vòng đời Stream hợp lệ.

### Thể hiện rõ phép tổng hợp

Thay vì duy trì một cấu trúc dữ liệu tạm bằng tay, `Collectors` có thể diễn đạt cách nhóm, đếm, nối chuỗi hoặc kết hợp nhiều kết quả. Đây là lý do Stream đặc biệt hữu ích trong xử lý báo cáo, danh sách, dữ liệu trả về từ API và các bước chuẩn hóa dữ liệu.

Tuy vậy, **cú pháp ngắn không tự động đồng nghĩa với mã dễ hiểu**. Một pipeline quá dài, lồng nhiều lambda hoặc che giấu tác dụng phụ có thể khó đọc hơn vòng lặp rõ ràng.

## 6. Các quy tắc và giới hạn phải biết từ đầu

### 6.1. Không nên thay đổi nguồn khi đang duyệt

Hàm truyền vào `filter`, `map` hay `reduce` thường cần **không can thiệp nguồn** (*non-interfering*) và, ở các thao tác thông thường, nên **không phụ thuộc trạng thái biến đổi bên ngoài** (*stateless*).

Không nên làm như sau:

~~~java
List<Integer> values = new java.util.ArrayList<>(List.of(1, 2, 3));

// Sai về thiết kế: sửa chính nguồn khi Stream đang duyệt.
values.stream().forEach(values::remove);
~~~

Cách này có thể tạo hành vi không xác định theo cách ta mong đợi, bỏ sót phần tử hoặc ném lỗi tùy nguồn và cách duyệt. Khi muốn lọc bỏ phần tử, hãy **tạo kết quả mới** hoặc dùng một thao tác cập nhật collection được thiết kế riêng như `removeIf` khi thực sự muốn thay đổi collection.

Cũng tránh gộp kết quả bằng cách gọi `forEach(result::add)` lên một `ArrayList` bên ngoài, đặc biệt khi chạy song song; hãy ưu tiên `collect` hoặc `toList`.

### 6.2. Thứ tự không phải lúc nào cũng được bảo đảm

Nguồn như `List` thường có *encounter order* (thứ tự phần tử khi duyệt); một số nguồn như `HashSet` không cam kết thứ tự. `sorted` thiết lập thứ tự theo comparator, trong khi `findAny` có thể trả về một phần tử bất kỳ, nhất là khi chạy song song.

Nếu đầu ra cần thứ tự xác định, hãy lựa chọn nguồn và phép toán thích hợp. Không suy ra thứ tự của `Map` tạo bởi `groupingBy` chỉ từ thứ tự của các phần tử đầu vào.

### 6.3. Lazy không có nghĩa là luôn dùng ít bộ nhớ

Một số phép toán có trạng thái như `sorted` hoặc `distinct` có thể cần lưu thông tin về các phần tử đã gặp, trong khi các phép toán như `filter` và `map` thường xử lý theo từng phần tử. Vì vậy không thể kết luận mọi Stream đều hoạt động trong bộ nhớ hằng số.

Về thời gian, một pipeline đơn giản qua `n` phần tử thường vẫn có độ phức tạp tuyến tính tương tự vòng lặp. Stream có thể có chi phí tạo pipeline, gọi lambda hoặc boxing. Hãy đo trên dữ liệu và cấu hình thật nếu hiệu năng là yêu cầu trọng yếu.

### 6.4. Parallel Stream chỉ phù hợp trong một số điều kiện

`parallelStream()` hoặc `stream().parallel()` cho phép framework phân phối việc xử lý qua nhiều luồng, nhưng **không bảo đảm nhanh hơn**. Việc phân chia dữ liệu, kết hợp kết quả, cạnh tranh tài nguyên, thứ tự và tác dụng phụ đều ảnh hưởng đến hiệu năng và tính đúng đắn.

Chỉ cân nhắc xử lý song song khi tác vụ đủ lớn, phép toán độc lập, nguồn dễ chia và phép tổng hợp tuân thủ hợp đồng. Không mặc định bật song song cho thao tác I/O chặn, pipeline rất nhỏ hoặc code dùng trạng thái chia sẻ có thể thay đổi.

### 6.5. Một số Stream cần được đóng

Phần lớn Stream tạo từ collection không giữ tài nguyên ngoài. Ngược lại, một Stream do `Files.lines(...)` mở có thể sở hữu tài nguyên I/O; nên dùng `try-with-resources`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("data.txt");
try (Stream<String> lines = Files.lines(path)) {
    long nonBlankLines = lines
        .filter(line -> !line.isBlank())
        .count();
    System.out.println(nonBlankLines);
}
~~~

Ví dụ dùng `Path.of` và `String.isBlank` (JDK 11+), giả định file `data.txt` tồn tại. Phép toán kết thúc **không tự thay thế** việc đóng nguồn I/O; khối `try` bảo đảm giải phóng tài nguyên.

### 6.6. Stream API không phải mọi loại “stream” trong Java

- `java.util.stream.Stream`: mô hình xử lý các phần tử qua pipeline.
- `java.io.InputStream` và `OutputStream`: luồng byte cho I/O.
- Các mô hình reactive/`Flow.Publisher`: quan tâm đến việc phát dữ liệu bất đồng bộ và điều phối nhu cầu tiêu thụ (*backpressure*).

Tên gọi giống nhau nhưng mục đích và hợp đồng lập trình khác nhau. Đừng dùng Stream API như một hệ thống truyền sự kiện bất đồng bộ chỉ vì nó có tên “Stream”.

## 7. Liên hệ với các chủ đề Stream nâng cao

Khi đã hiểu pipeline cơ bản, bạn sẽ thấy các chủ đề nâng cao xuất phát từ những nhu cầu rất cụ thể:

| Nhu cầu phát triển | Chủ đề tiếp theo |
|---|---|
| Gộp nhiều phần tử thành một giá trị | `reduce`, quy tắc identity và associativity |
| Thu thập dữ liệu thành cấu trúc tùy ý | `collect`, `Collector`, `groupingBy`, `partitioningBy` |
| Kiểm soát cách chia và duyệt nguồn | `Spliterator` |
| Tận dụng nhiều lõi CPU đúng cách | Parallel Stream, collector đồng thời, đo hiệu năng |
| Biến đổi luồng phức tạp có trạng thái hoặc thay đổi số phần tử | **Stream Gatherers** (API chuẩn hóa ở JDK 24) |

Những công cụ này mở rộng cùng một mô hình nguồn → phép toán → kết quả. Không cần sử dụng chúng ngay từ bài đầu tiên; điều quan trọng là hiểu hợp đồng về vòng đời Stream, thứ tự, trạng thái và tài nguyên trước khi đi sâu.

## 8. Bài thực hành ngắn

**Yêu cầu:** Từ danh sách tên ngôn ngữ lập trình có khoảng trắng, chữ hoa/chữ thường và phần tử rỗng, hãy chuẩn hóa, loại trùng, sắp xếp rồi tạo danh sách kết quả. Không sửa danh sách đầu vào.

~~~java
import java.util.List;
import java.util.Locale;

List<String> raw = List.of("Java", " java ", "Kotlin", "", "Go");

List<String> result = raw.stream()
    .map(String::trim)
    .filter(value -> !value.isEmpty())
    .map(value -> value.toUpperCase(Locale.ROOT))
    .distinct()
    .sorted()
    .toList();

System.out.println(result); // [GO, JAVA, KOTLIN]
System.out.println(raw.size()); // 5: nguồn vẫn giữ nguyên
~~~

Hãy tự trả lời trước khi xem gợi ý:

1. **Nguồn** của pipeline là gì? — Danh sách `raw`, được đưa vào pipeline bằng `raw.stream()`.
2. **Phép toán trung gian** nào thay đổi giá trị? — Hai phép `map` lần lượt cắt khoảng trắng và chuyển thành chữ hoa.
3. **Phép toán** nào loại phần tử hoặc loại trùng? — `filter` bỏ chuỗi rỗng; `distinct` bỏ giá trị trùng.
4. **Khi nào pipeline thực sự được tiêu thụ?** — Khi gọi `toList()`, phép toán kết thúc.
5. **Có thể gọi tiếp `count()` trên Stream đã dùng cho `toList()` không?** — Không; phải tạo Stream mới từ `raw`.

`toList()` được giới thiệu ở **Java 16** và trả về `List` không thể sửa. Nếu cần tương thích Java 8, dùng `collect(Collectors.toList())`; tuy nhiên hợp đồng của collector này không bảo đảm tính có thể sửa của danh sách thu được. Chọn cách tạo kết quả theo phiên bản JDK và nhu cầu sử dụng thực tế.

## 9. Khi nào nên chọn Stream API?

**Ưu tiên Stream** khi dữ liệu cần được lọc, chiếu, tìm kiếm, nhóm hoặc tổng hợp; quy trình có thể viết thành các phép toán độc lập; và kết quả cần được xác định từ đầu vào mà ít phụ thuộc trạng thái bên ngoài.

**Cân nhắc vòng lặp hoặc cấu trúc điều khiển khác** khi thuật toán yêu cầu nhiều lần cập nhật trạng thái phức tạp, xử lý lỗi chi tiết cho từng bước, tương tác I/O tuần tự có nhiều tác dụng phụ, hoặc một pipeline sẽ làm ý định nghiệp vụ khó đọc. Tối ưu hiệu năng nên dựa trên phép đo, không dựa vào việc có dùng Stream hay không.

Trước khi viết pipeline, hãy xác định bốn điều: **nguồn dữ liệu**, **quy tắc biến đổi/lọc**, **kiểu kết quả cuối**, và **các ràng buộc về thứ tự, trạng thái, tài nguyên**. Đây là nền tảng để dùng Stream API đúng và mở rộng sang collector tùy chỉnh, xử lý song song hay Stream Gatherers về sau.

**Ghi nhớ:** Stream API diễn đạt cách chuyển dữ liệu từ nguồn sang kết quả bằng pipeline. Sức mạnh chính của nó nằm ở cách tổ chức phép toán rõ nghĩa và khả năng kết hợp; tính lazy, vòng đời một lần sử dụng và các hợp đồng thực thi là những điều bắt buộc phải hiểu để viết code đúng.
