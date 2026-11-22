# Nguồn dữ liệu, phép biến đổi trung gian và thao tác kết thúc trong Java Stream

Java Stream API cho phép mô tả quá trình xử lý một dãy phần tử như một **pipeline**: lấy phần tử từ nguồn, áp dụng các phép biến đổi hoặc lọc, rồi dùng một thao tác kết thúc để tạo ra kết quả hoặc tác động mong muốn. Đây là mô hình quan trọng trong lập trình hàm với Java: ta truyền các **hành vi** như `Predicate`, `Function`, `Comparator` và `Consumer` vào API, thay vì tự viết vòng lặp cho từng công đoạn.

Một pipeline Stream thông thường có dạng:

~~~text
Nguồn dữ liệu
   |
   v
Intermediate operations: filter → map → sorted → ...
   |
   v
Terminal operation: toList / collect / count / reduce / forEach / ...
   |
   v
Kết quả hoặc tác động
~~~

Ví dụ:

~~~java
List<String> names = List.of("An", "Binh", "Chi", "Anh");
List<String> selected = names.stream()
        .filter(name -> name.startsWith("A"))
        .map(String::toUpperCase)
        .toList();
// selected == [AN, ANH]
~~~

Đoạn mã cần `import java.util.List;` và nằm trong phương thức. `names.stream()` tạo Stream từ nguồn; `filter` và `map` là phép trung gian; `toList()` là thao tác kết thúc. Từng khái niệm này có hợp đồng riêng, và sự khác biệt quyết định cách pipeline được thực thi.

## 1. Nguồn dữ liệu (source): Stream lấy phần tử từ đâu?

**Source** là nơi pipeline lấy các phần tử ban đầu. Stream không nhất thiết chứa sẵn một bản sao toàn bộ phần tử; nó thường mô tả cách **duyệt nguồn khi pipeline được thực thi**.

Những nguồn thường gặp trong Java 17+:

| Nguồn | Ví dụ | Ghi chú |
| --- | --- | --- |
| Collection | `list.stream()` | Duyệt các phần tử trong collection |
| Collection song song | `list.parallelStream()` | Có khả năng xử lý song song; cần cân nhắc hiệu quả |
| Mảng đối tượng | `Arrays.stream(array)` | Tạo stream trên phần tử mảng |
| Mảng nguyên thủy | `Arrays.stream(intArray)` | Trả `IntStream` thay vì `Stream<Integer>` |
| Giá trị tường minh | `Stream.of("A", "B")` | Tạo stream từ danh sách đối số |
| Giá trị có thể null | `Stream.ofNullable(value)` | Stream 0 hoặc 1 phần tử |
| Khoảng số | `IntStream.range(1, 4)` | Các số 1, 2, 3; điểm cuối loại trừ |
| Sinh phần tử | `Stream.generate(supplier)` | Thường vô hạn, nên có điểm dừng |
| Lặp có quy tắc | `Stream.iterate(seed, next)` | Thường vô hạn ở overload hai đối số |
| Tệp văn bản | `Files.lines(path)` | Stream gắn với tài nguyên I/O; phải đóng |

Cần import các lớp tương ứng từ `java.util`, `java.util.stream`, `java.nio.file`. Các ví dụ trong bảng là biểu thức độc lập, không phải chương trình hoàn chỉnh.

### Stream không phải Collection

- **Collection** lưu trữ và tổ chức phần tử; nó có thể cho phép thêm/xóa, duyệt lại nhiều lần.
- **Stream** diễn đạt một quá trình tính toán trên nguồn và chỉ được **tiêu thụ một lần**. Nó không cung cấp thao tác lưu trữ, thêm hay xóa phần tử.
- Xử lý Stream thường **không sửa collection nguồn**. Tuy nhiên, đây không phải cam kết rằng tác dụng phụ bị cấm bằng hệ thống kiểu; một lambda gây mutation vẫn có thể làm hỏng tính đúng đắn. `List.sort(...)` là API Collection thay đổi list, còn `stream.sorted(...)` mô tả thứ tự kết quả của Stream.
- Stream có thể tạo kết quả collection mới bằng `toList()` hoặc `collect(...)`. Kết quả đó là đối tượng riêng; không biến Stream thành container có thể duyệt lại.

Ví dụ, tạo stream không đồng nghĩa với tạo bản sao list:

~~~java
List<String> data = new ArrayList<>(List.of("a", "b"));
Stream<String> stream = data.stream(); // Xây dựng nguồn
// Đừng thay đổi cấu trúc data trong lúc pipeline được duyệt.
List<String> copy = stream.toList();
~~~

Đoạn mã cần import `List`, `ArrayList`, `Stream`. Việc can thiệp vào nguồn khi pipeline đang chạy vi phạm nguyên tắc *non-interference* (trừ những trường hợp nguồn hỗ trợ đồng thời theo hợp đồng). Nếu cần ảnh chụp dữ liệu cố định, hãy chủ động tạo bản sao đầu vào trước khi dùng.

### Nguồn hữu hạn và vô hạn

`IntStream.range(0, 10)` là hữu hạn; `Stream.generate(Math::random)` thường vô hạn. Pipeline trên nguồn vô hạn cần một thao tác có thể dừng, ví dụ `limit(n)` (trong điều kiện phù hợp) hoặc terminal short-circuit như `findFirst()`. Kết thúc bằng `count()` trên một pipeline sinh vô hạn không có ràng buộc dừng sẽ không hoàn tất.

~~~java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .toList();
// [1, 2, 3, 4, 5]
~~~

Không nên dùng nguồn vô hạn tùy tiện với `sorted()`, vì sắp xếp toàn bộ dữ liệu đòi hỏi thấy hết phần tử trước khi trả kết quả.

## 2. Phép biến đổi trung gian (intermediate operations)

Các phương thức trung gian trả về **một Stream mới**, nên có thể nối nhiều bước thành chuỗi. Việc gọi chúng để xây dựng pipeline thường **chưa duyệt nguồn và chưa chạy lambda**. Hoạt động thực tế được dồn tới khi một terminal operation đòi hỏi kết quả.

Các phép trung gian phổ biến:

| Phép toán | Vai trò | Ví dụ |
| --- | --- | --- |
| `filter(predicate)` | Chỉ giữ phần tử thỏa điều kiện | `filter(n -> n > 0)` |
| `map(mapper)` | Đổi mỗi phần tử thành một phần tử khác | `map(String::length)` |
| `mapToInt / mapToLong / mapToDouble` | Biến thành stream nguyên thủy | `mapToInt(String::length)` |
| `flatMap(mapper)` | Ghép các stream con được tạo từ từng phần tử | `flatMap(List::stream)` |
| `distinct()` | Loại trùng theo `equals` | `distinct()` |
| `sorted()` / `sorted(comparator)` | Sắp xếp theo thứ tự | `sorted(Comparator.reverseOrder())` |
| `peek(action)` | Quan sát phần tử được xử lý; chủ yếu dùng để chẩn đoán | `peek(System.out::println)` |
| `limit(n)` | Giữ tối đa `n` phần tử đầu tiên theo thứ tự có thể xác định | `limit(10)` |
| `skip(n)` | Bỏ `n` phần tử đầu | `skip(5)` |
| `takeWhile(predicate)` | Lấy đoạn tiền tố còn thỏa điều kiện trên stream có thứ tự | `takeWhile(n -> n < 10)` |
| `dropWhile(predicate)` | Bỏ đoạn tiền tố còn thỏa điều kiện trên stream có thứ tự | `dropWhile(n -> n < 10)` |

Mỗi phép toán trung gian nhận và trả một dạng stream thích hợp: `Stream<T>`, `IntStream`, `LongStream` hoặc `DoubleStream`. Ví dụ:

~~~java
IntStream numbers = Stream.of("10", "20", "30")
        .mapToInt(Integer::parseInt);
int total = numbers.sum(); // 60
~~~

`sum()` là terminal operation của `IntStream`. Với `map` thông thường, pipeline vẫn là `Stream<Integer>` và muốn cộng tổng có thể dùng `mapToInt(Integer::intValue).sum()` hoặc `reduce(...)`.

### Phép trung gian stateless và stateful

**Stateless**: `map`, `filter` thường xử lý từng phần tử mà không cần giữ nhiều phần tử khác; phù hợp để kết hợp, xử lý theo từng phần tử khi terminal được gọi.

**Stateful**: `sorted`, `distinct` hoặc một số phép giới hạn/tiền tố cần quan sát hoặc ghi nhớ trạng thái giữa các phần tử. Ví dụ `sorted` phải có thông tin tổng thể để tạo thứ tự sắp xếp trên nguồn hữu hạn, dù từng lời gọi `sorted()` khi xây dựng pipeline vẫn là lazy.

Khác biệt này ảnh hưởng hiệu năng, bộ nhớ và hành vi short-circuit. `sorted()` trên tập lớn thường tốn thêm bộ nhớ; `distinct()` cần theo dõi giá trị đã gặp; `limit()` và `skip()` trên stream có thứ tự song song có thể tốn chi phí phối hợp.

## 3. Thao tác kết thúc (terminal operations): lúc pipeline được yêu cầu tính toán

Terminal operation là bước **tiêu thụ stream**, thường tạo kết quả cuối cùng, trả `void` hoặc thực thi một tác động. Sau một terminal, stream không được dùng lại.

| Terminal | Kết quả / mục đích | Lưu ý |
| --- | --- | --- |
| `toList()` | `List<T>` kết quả | Java 16+; list không hỗ trợ thao tác thay đổi cấu trúc |
| `collect(collector)` | Gom vào collection/map/thống kê khác | Cấu trúc và khả năng thay đổi phụ thuộc collector |
| `count()` | `long` số phần tử | Có thể được tối ưu hóa mà không chạy mọi bước trung gian |
| `forEach(action)` | Thực thi hành động, trả `void` | Thứ tự không được bảo đảm với stream song song |
| `forEachOrdered(action)` | Thực thi hành động theo encounter order khi có | Song song có thể tốn chi phí giữ thứ tự |
| `reduce(...)` | Gộp phần tử bằng toán tử kết hợp | Cần hàm có tính kết hợp, nhất là khi song song |
| `min(...)` / `max(...)` | `Optional<T>` phần tử cực trị | Stream rỗng trả empty |
| `findFirst()` | `Optional<T>` phần tử đầu theo encounter order | Có thể dừng sớm |
| `findAny()` | `Optional<T>` một phần tử bất kỳ | Hữu ích khi không cần thứ tự, nhất là song song |
| `anyMatch / allMatch / noneMatch` | `boolean` kiểm tra điều kiện | Có thể dừng sớm |

Một số terminal trả dữ liệu mới, một số chỉ in/gửi/lưu kết quả. Điều quan trọng là **nó kích hoạt việc đánh giá pipeline khi cần** và đánh dấu stream là đã tiêu thụ.

Ví dụ:

~~~java
long count = List.of("Java", "Stream", "API").stream()
        .filter(s -> s.length() >= 4)
        .count(); // 2: "Java", "Stream"
~~~

`count()` yêu cầu số lượng phần tử còn lại sau filter, nên filter phải ảnh hưởng kết quả. Nhưng không nên phụ thuộc vào việc một lambda trung gian có chạy bao nhiêu lần nếu công việc của nó chỉ là side effect; Java cho phép tối ưu hóa pipeline khi kết quả vẫn tương đương.

### Trả list bằng hai API

`stream.toList()` (Java 16+) trả một List không hỗ trợ các phương thức làm thay đổi nội dung/cấu trúc. `stream.collect(Collectors.toList())` trả danh sách có kiểu triển khai và tính mutability **không được API bảo đảm**. Nếu cần list có thể sửa, hãy nêu rõ ý định:

~~~java
List<String> mutableCopy = source.stream()
        .collect(Collectors.toCollection(ArrayList::new));
mutableCopy.add("new");
~~~

Đoạn này cần các import `List`, `Collectors`, `ArrayList` và biến `source` có kiểu phù hợp. Không giả định mọi kết quả collector luôn có thể sửa nếu hợp đồng không cam kết.

## 4. Lazy evaluation: trung gian chưa chạy khi chỉ dựng pipeline

Ví dụ sau chỉ thể hiện một phần của chương trình Java hợp lệ:

~~~java
Stream<String> pipeline = List.of("a", "bb", "ccc").stream()
        .filter(s -> {
            System.out.println("checking " + s);
            return s.length() > 1;
        });
System.out.println("built");
List<String> result = pipeline.toList();
~~~

Khi gọi `filter(...)` để tạo pipeline, đoạn `System.out.println("checking ...")` **chưa chạy**. Dòng `built` được in trước; đến `toList()`, nguồn mới được duyệt. `filter` nhận `Predicate<String>`, chạy khi phần tử được cần tới. Chương trình hoàn chỉnh ở mục 6 minh họa rõ điều này cùng với kết quả đầu ra đã kiểm chứng.

**Lazy không có nghĩa là "tự động chạy trong tương lai"**. Một pipeline không có terminal có thể không làm gì ngoài việc tạo cấu trúc mô tả tính toán. Muốn kết quả, cần terminal; muốn giữ kết quả để dùng nhiều lần, hãy materialize bằng `toList()` hoặc collection phù hợp.

### Fusion: xử lý từng phần tử qua nhiều bước

Với pipeline:

~~~java
source.stream()
        .filter(this::eligible)
        .map(this::normalize)
        .forEach(this::save);
~~~

Đây là đoạn mã minh họa trong instance method có `source` và các phương thức tương ứng. Khi terminal chạy, các bước stateless thường được kết hợp trong **một lần duyệt**: phần tử đầu đi qua filter rồi map rồi terminal, sau đó tới phần tử tiếp theo. Không nên hình dung bắt buộc tạo một danh sách trung gian đầy đủ cho mỗi `filter` hoặc `map`.

Các phép stateful như `sorted()` là ranh giới có thể cần gom/buffer dữ liệu trước khi chuyển tiếp. Hơn nữa, Stream có quyền tổ chức và tối ưu việc thực thi theo hợp đồng; không nên xem thứ tự mọi side effect trong lambda là bất biến, đặc biệt trên stream song song.

## 5. Short-circuit: không phải terminal nào cũng cần đọc hết nguồn

Một số thao tác có thể biết kết quả mà không duyệt mọi phần tử:

~~~java
boolean hasEven = IntStream.range(1, 1_000_000)
        .anyMatch(n -> n % 2 == 0); // true
~~~

`anyMatch` có thể dừng ngay khi thấy phần tử phù hợp (`2`). `findFirst` có thể dừng khi tìm phần tử đầu; `findAny` có thể lấy phần tử phù hợp bất kỳ; `limit(5)` là phép trung gian **giới hạn** số phần tử đưa xuống phía dưới. Tuy vậy, một số phép đặt trước `limit` như `sorted()` có thể vẫn cần xem hết nguồn để tìm thứ tự, nên đừng suy luận rằng `limit(5)` luôn chỉ đọc 5 phần tử từ nguồn.

Các terminal kiểu match có quy tắc với Stream rỗng:

- `anyMatch(...)` trả `false`.
- `allMatch(...)` trả `true`.
- `noneMatch(...)` trả `true`.

Đây là quy tắc logic của các lượng từ trên tập rỗng; predicate không được gọi khi không có phần tử.

### Không lẫn `limit` và `filter`

~~~java
List<Integer> firstTwoEvens = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .limit(2)
        .boxed()
        .toList();
// [2, 4]
~~~

`limit(2)` nhận tối đa hai phần tử **sau filter**, không phải lấy hai phần tử nguồn trước rồi mới lọc. Nếu đổi vị trí `limit(2).filter(...)`, chỉ có 1,2 được xem xét nên kết quả là `[2]`. Vị trí các phép toán ảnh hưởng kết quả lẫn hiệu năng.

## 6. Ví dụ Java 17+ hoàn chỉnh: source → intermediate → terminal

Lưu mã nguồn vào tệp **`StreamPipelineDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamPipelineDemo {
    record Order(String id, int total, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 100, true),
                new Order("B", 30, false),
                new Order("C", 150, true),
                new Order("D", 80, true)
        );

        Stream<String> pipeline = orders.stream()
                .filter(o -> {
                    System.out.println("filter: " + o.id());
                    return o.paid();
                })
                .map(o -> o.id() + "=" + o.total())
                .sorted();

        System.out.println("before terminal");
        List<String> result = pipeline.toList();
        System.out.println("result=" + result);

        int paidTotal = orders.stream()
                .filter(Order::paid)
                .mapToInt(Order::total)
                .sum();
        System.out.println("paidTotal=" + paidTotal);

        boolean highPaid = orders.stream()
                .anyMatch(o -> o.paid() && o.total() >= 150);
        System.out.println("highPaid=" + highPaid);

        List<String> top2 = orders.stream()
                .filter(Order::paid)
                .sorted(Comparator.comparingInt(Order::total).reversed())
                .limit(2)
                .map(Order::id)
                .toList();
        System.out.println("top2=" + top2);

        Map<Boolean, Long> counts = orders.stream()
                .collect(Collectors.groupingBy(Order::paid, Collectors.counting()));
        System.out.println("paidCount=" + counts.get(true)
                + ", unpaidCount=" + counts.get(false));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac StreamPipelineDemo.java
java StreamPipelineDemo
~~~

Đầu ra chính xác:

~~~text
before terminal
filter: A
filter: B
filter: C
filter: D
result=[A=100, C=150, D=80]
paidTotal=330
highPaid=true
top2=[C, A]
paidCount=3, unpaidCount=1
~~~

Giải thích theo ba tầng:

1. **Nguồn:** `orders` là `List<Order>` với 4 phần tử; mỗi lời gọi `orders.stream()` tạo một pipeline **mới** trên cùng nguồn.
2. **Trung gian:** pipeline đầu tiên chạy `filter` để chỉ giữ đơn đã thanh toán, `map` thành chuỗi `id=total`, rồi `sorted()` sắp xếp các chuỗi. Vì các chuỗi bắt đầu bằng ID theo bảng chữ cái A, C, D nên kết quả ở thứ tự đó.
3. **Terminal:** Trước `toList()`, chương trình in `before terminal`; chỉ sau đó các dòng `filter: ...` xuất hiện. `toList()` tạo list kết quả. `sum()` cộng 100+150+80=330, `anyMatch` tìm thấy đơn C, `toList()` cho top 2 là C và A, `collect(groupingBy(..., counting()))` đếm 3 đơn đã thanh toán và 1 đơn chưa thanh toán.

Chương trình đặt lệnh in trong filter **để quan sát học tập**, không dùng side effect ấy để tạo kết quả nghiệp vụ. Với stream song song hoặc phép tối ưu, việc dựa vào số lần gọi hay thứ tự in của lambda trung gian không an toàn. Ví dụ dùng nguồn `List` có encounter order và pipeline tuần tự nên stdout minh họa trên là xác định.

`Collectors.groupingBy` trả một `Map` với thứ tự duyệt key không được bảo đảm; ví dụ truy xuất trực tiếp `counts.get(true)` và `counts.get(false)` để hiển thị kết quả ổn định.

## 7. Vòng đời: xây dựng, tiêu thụ một lần, tạo pipeline mới

Sau khi gọi một terminal, stream đã được sử dụng. Không được tái dùng **cùng instance Stream** để chạy thêm terminal:

~~~java
Stream<String> once = Stream.of("a", "b");
long count = once.count(); // 2
// Sai: once đã bị tiêu thụ.
// List<String> all = once.toList();
~~~

Dòng thứ hai nếu bỏ comment sẽ ném `IllegalStateException` (stream has already been operated upon or closed). Trong vài trường hợp sử dụng lại một pipeline có thể bị phát hiện sớm hơn, nên hợp đồng đúng là **mỗi Stream sử dụng một lần**.

Muốn thực hiện hai tính toán độc lập trên cùng nguồn collection:

~~~java
List<String> items = List.of("Java", "Stream", "API");

long count = items.stream().count();
List<String> sorted = items.stream().sorted().toList();
~~~

Mỗi `items.stream()` tạo một Stream mới. Nếu nguồn chỉ đọc được một lần, chẳng hạn một số luồng I/O, cần quyết định tính toán trong cùng traversal, hoặc lưu dữ liệu vào cấu trúc thích hợp trước khi dùng lại. Không cố giữ và tái khởi động một Stream đã tiêu thụ.

Nếu pipeline được đưa vào một biến để tái dùng về mặt logic, có thể dùng `Supplier<Stream<T>>` tạo Stream mới mỗi lần:

~~~java
Supplier<Stream<String>> supplier =
        () -> List.of("Java", "Stream", "API").stream();

long count = supplier.get().count();
List<String> sorted = supplier.get().sorted().toList();
~~~

Đây là đoạn minh họa, cần import `java.util.function.Supplier`, `java.util.stream.Stream` và `java.util.List`.

## 8. Encounter order và thực thi song song

**Encounter order** là thứ tự mà một nguồn có thứ tự cung cấp phần tử: `List` và mảng thường có thứ tự; `HashSet` không cam kết một thứ tự duyệt cố định. Các intermediate như `sorted` có thể tạo thứ tự; `unordered()` có thể bỏ yêu cầu giữ thứ tự để cho phép tối ưu.

Khi pipeline tuần tự có nguồn List, `toList()` giữ encounter order của kết quả sau các phép trung gian. Với `parallelStream()`, Java có thể tính các phần tử ở nhiều thread nhưng những thao tác phải bảo toàn encounter order theo hợp đồng vẫn phải làm như vậy. **`forEach` không bảo đảm thứ tự thực thi**, trong khi `forEachOrdered` thực thi action theo encounter order nếu có.

Ví dụ:

~~~java
List<Integer> values = List.of(1, 2, 3, 4);
List<Integer> doubled = values.parallelStream()
        .map(n -> n * 2)
        .toList();
// doubled == [2, 4, 6, 8]
~~~

Đừng suy ra rằng mọi pipeline song song sẽ nhanh hơn tuần tự: task nhỏ, phép stateful (`sorted`, `distinct`), yêu cầu giữ thứ tự và chi phí phối hợp thread có thể khiến hiệu năng kém hơn. Nếu tính toán dựa vào `reduce`, accumulator cần tương thích với kết hợp song song (associativity), và tránh dựa vào state dùng chung có thể bị race.

Phân biệt:

- **`map` trên Stream** biến từng phần tử và trả Stream mới.
- **`forEach` terminal** nhận `Consumer`, chỉ thực hiện action, không trả Stream để nối tiếp.
- **`collect` terminal** gom dữ liệu vào kết quả; thường thích hợp hơn việc gọi `forEach` rồi thêm vào một `ArrayList` dùng chung khi chạy parallel.

## 9. Side effect, lỗi và vấn đề hiệu năng

### Không dựa vào side effect trong intermediate

Mã sau rất dễ gây hiểu nhầm:

~~~java
List<String> data = List.of("a", "b", "c");
long count = data.stream()
        .peek(System.out::println)
        .count();
~~~

Dù `peek` nhận `Consumer`, Java có thể tối ưu terminal `count()` trên nguồn có kích thước biết trước, nên **không bảo đảm cả ba dòng được in**. Mục đích của `peek` chủ yếu để quan sát/chẩn đoán; đừng coi nó là cơ chế logging/ghi database bắt buộc.

Tương tự, tránh viết `map(x -> {sendMail(x); return x;})` với ý định gửi email chính là hiệu ứng của pipeline. Với nghiệp vụ có side effect, hãy tách phần ra quyết định bằng Stream và phần thực hiện hành động, hoặc sử dụng một terminal thích hợp sau khi xác định yêu cầu thứ tự và lỗi.

### Ngoại lệ không tự biến thành kết quả rỗng

~~~java
List<Integer> parsed = List.of("1", "oops", "3").stream()
        .map(Integer::parseInt)
        .toList();
~~~

Khi terminal chạy, phần tử `"oops"` làm `Integer.parseInt` ném `NumberFormatException`; Stream không tự bỏ qua lỗi. Nếu yêu cầu bỏ giá trị sai, phải thiết kế phép parse an toàn và lọc theo quy tắc rõ ràng. Không lạm dụng `filter(s -> s.matches("\\d+"))` nếu ứng dụng có thêm dấu âm, định dạng locale hoặc quy định đầu vào phức tạp.

### Non-interference và stateless lambdas

Hàm trong `filter`/`map` nên có kết quả phụ thuộc đầu vào, không sửa nguồn đang duyệt và không phụ thuộc vào biến dùng chung biến đổi qua các lần gọi. Với parallel stream, các side effect không đồng bộ có thể gây race condition và kết quả thiếu ổn định. Ngay trên stream tuần tự, mutate nguồn khi đang duyệt có thể gây `ConcurrentModificationException` hoặc hành vi không đáng tin.

### Nguồn lớn, tài nguyên, phép stateful

- `sorted()` cần xử lý thứ tự của nhiều phần tử và thường phải buffer; tránh áp ngay trên stream vô hạn.
- `distinct()` giữ tập các giá trị đã thấy nên tiêu tốn bộ nhớ, nhất là với nguồn rất lớn.
- `limit()`/`findFirst()` có thể dừng sớm, nhưng hiệu quả thực tế phụ thuộc thứ tự thao tác và nguồn.
- `mapToInt(...).sum()` tránh boxing cho phép tính tổng số nguyên.
- Khi dùng `Files.lines(path)`, stream giữ tài nguyên mở và cần đóng bằng *try-with-resources*. Đa số Stream thuần collection không cần gọi `close()`.

Ví dụ đóng stream có tài nguyên:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long nonBlank = lines.filter(s -> !s.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

Đoạn này cần `import java.nio.file.Files;`, `import java.nio.file.Path;`, `import java.util.stream.Stream;`, biến `path` là `Path` hợp lệ và phương thức bao quanh khai báo/xử lý `IOException`. Đây là đoạn minh họa có ngữ cảnh, không phải một chương trình độc lập. `try-with-resources` bảo đảm gọi `close()` ngay cả khi đọc xảy ra lỗi.

## 10. Thiết kế pipeline dễ đọc và đúng hợp đồng

Một cách đọc tốt là hỏi theo thứ tự:

1. **Nguồn nào?** Các phần tử là `T` gì? Nguồn có thứ tự không, hữu hạn hay vô hạn, có cần đóng không?
2. **Chuyển đổi trung gian nào?** `filter` giữ gì, `map` đổi kiểu ra sao, `sorted` cần comparator nào, `flatMap` mở rộng bao nhiêu phần tử? Các phép toán có thay đổi thứ tự hoặc chi phí lưu trữ không?
3. **Terminal nào?** Cần `List`, số đếm, tổng số, `Optional`, bản đồ nhóm, hay tác dụng phụ? Có đòi hỏi phải duyệt hết không?
4. **Cần chạy lại không?** Nếu có, tạo stream mới từ nguồn hay lưu trữ kết quả; không tái dùng instance đã tiêu thụ.
5. **Có side effect hay dữ liệu biến đổi không?** Đảm bảo hàm trong pipeline không phá nguồn, giữ logic ổn định, nhất là khi song song.

Bảng phân biệt nhanh:

| Tình huống | Lựa chọn |
| --- | --- |
| Chọn phần tử phù hợp | `filter(predicate)` — trung gian |
| Biến một phần tử thành một giá trị khác | `map(mapper)` — trung gian |
| Biến một phần tử thành nhiều phần tử | `flatMap(mapper)` — trung gian |
| Đổi thứ tự theo tiêu chí | `sorted(comparator)` — trung gian |
| Lấy tối đa `n` phần tử | `limit(n)` — trung gian |
| Lấy danh sách kết quả | `toList()` — terminal |
| Tính tổng `int` | `mapToInt(...).sum()` — terminal là `sum` |
| Gom vào Map hoặc cấu trúc khác | `collect(collector)` — terminal |
| Kiểm tra có phần tử phù hợp | `anyMatch(predicate)` — terminal, có thể short-circuit |
| Thực thi hành động cho từng kết quả | `forEach(action)` — terminal |
| Sắp xếp tại chỗ một List hiện có | `list.sort(comparator)` — API Collection, không phải Stream |

Khi hiểu rõ ba vai trò **nguồn dữ liệu → phép trung gian → thao tác kết thúc**, ta sẽ thấy Stream là mô hình *mô tả tính toán có thể ghép nối* và được thực thi khi cần kết quả. Các nguyên tắc **lazy, single-use, short-circuit, encounter order và non-interference** là nền tảng để pipeline đúng, dễ bảo trì và có hiệu năng hợp lý.