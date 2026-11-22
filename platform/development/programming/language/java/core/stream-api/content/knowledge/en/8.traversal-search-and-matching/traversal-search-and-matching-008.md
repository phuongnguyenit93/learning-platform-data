# Quan sát pipeline bằng `peek` và các giới hạn của tác dụng phụ

Một pipeline Java Stream API thường được diễn đạt bằng các bước khai báo như `filter`, `map`, `sorted`, `distinct` và một terminal operation. Khi kết quả không đúng như mong đợi, người học dễ muốn xem phần tử đi qua từng bước. `peek` là công cụ thuận tiện để **quan sát** giá trị trong quá trình tiêu thụ stream, nhưng việc quan sát đó có những giới hạn quan trọng: pipeline thực thi lazy, có thể dừng sớm, có thể bỏ qua bước không cần thiết và có thể xử lý phần tử trên nhiều thread.

Bài này thuộc chương **Duyệt, tìm kiếm và đối sánh** của module **JAVA_STREAM_API**. Mục tiêu là hiểu chính xác `peek` làm gì, lúc nào hành động trong `peek` có thể chạy, cách dùng để chẩn đoán pipeline, và vì sao không nên dựa vào tác dụng phụ của `peek` để cập nhật trạng thái nghiệp vụ. Các ví dụ dùng Java 17 trở lên, có liên hệ đến `filter`, `map`, `collect`, xử lý song song, vòng đời stream và hiệu năng.

## 1. `peek` là gì?

`Stream.peek` là **intermediate operation** nhận một `Consumer`:

```java
Stream<T> peek(Consumer<? super T> action);
```

`Consumer<T>` có phương thức `void accept(T value)`: nhận một phần tử và thực hiện hành động nhưng không trả về phần tử mới. Khi một phần tử thật sự được pipeline xử lý qua `peek`, action có thể quan sát phần tử đó. `peek` chuyển tiếp **chính phần tử đầu vào**, không thay đổi số lượng và không thay đổi giá trị tham chiếu bằng cơ chế ánh xạ như `map`.

```java
import java.util.List;

List<Integer> result = List.of(5, 2, 8, 3).stream()
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("Sau filter: " + n))
        .map(n -> n * 10)
        .toList();

System.out.println(result); // [20, 80]
```

Trong đường thực thi tuần tự thông thường, đoạn `peek` in `2` và `8`, sau đó `map` biến chúng thành `20` và `80`. **Kết quả được bảo đảm** là danh sách `[20, 80]`; việc log có chạy hay không và chạy mấy lần không phải hợp đồng để dựa vào trong nghiệp vụ.

### So sánh với những thao tác thường bị nhầm

| Thao tác | Vai trò | Phần tử đầu ra |
|---|---|---|
| `filter(predicate)` | Quyết định giữ hay bỏ phần tử | Giữ nguyên phần tử thỏa điều kiện |
| `map(function)` | Chuyển đổi giá trị/kiểu | Giá trị do `function` trả về |
| `peek(consumer)` | Quan sát hoặc thực hiện action phụ khi phần tử được tiêu thụ | Chuyển tiếp cùng phần tử |
| `forEach(consumer)` | Terminal operation thực hiện action cho các phần tử được duyệt | Không tạo stream kết quả |
| `forEachOrdered(consumer)` | Terminal operation thực hiện action theo encounter order nếu có | Không tạo stream kết quả |
| `collect(collector)` / `toList()` | Terminal operation tích lũy kết quả | Một kết quả tổng hợp, ví dụ danh sách |

**Quy tắc:** dùng `map` để tạo giá trị mới, `filter` để loại giá trị không phù hợp, `peek` để hỗ trợ quan sát và terminal operation để hoàn tất pipeline.

## 2. Tính lazy: khai báo `peek` không làm action chạy ngay

Vì `peek` là intermediate operation, việc gọi nó chỉ xây dựng pipeline:

```java
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of("Lan", "An", "Minh")
        .peek(name -> System.out.println("Nhìn thấy: " + name))
        .map(String::toUpperCase);

System.out.println("Đã khai báo xong pipeline");
// Chưa cần đọc phần tử hay gọi action trong peek.

List<String> names = pipeline.toList();
System.out.println(names); // [LAN, AN, MINH]
```

Phương thức `toList()` là terminal operation yêu cầu các giá trị kết quả. Với pipeline này, `peek` giúp quan sát những phần tử mà quá trình tiêu thụ thật sự đi qua.

Tính lazy giúp tránh công việc không cần thiết, đặc biệt khi có thao tác ngắn mạch, nhưng cũng có nghĩa **không được dùng `peek` như một bộ đếm số phần tử bắt buộc phải chạy**.

### 2.1. Dòng dữ liệu đi qua từng điểm quan sát

```java
List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> result = values.stream()
        .peek(n -> System.out.println("Nguồn: " + n))
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("Qua filter: " + n))
        .map(n -> n * n)
        .peek(n -> System.out.println("Qua map: " + n))
        .toList();

System.out.println(result); // [4, 16]
```

Khi debug một pipeline tuần tự mà terminal cần toàn bộ kết quả, các điểm `peek` giúp phân biệt ba tập giá trị: đầu vào `1, 2, 3, 4, 5`, phần tử chẵn `2, 4` và kết quả bình phương `4, 16`.

Đừng suy từ đoạn mã này rằng JVM phải thực thi theo ba **vòng lặp tách biệt**. Một số thao tác có thể được kết hợp trong quá trình duyệt, và thứ tự, số lần gọi action không nên trở thành kết quả được kiểm thử.

## 3. Vì sao `peek` có thể không chạy như ta mong đợi?

Theo hợp đồng của Stream API, trình thực thi có thể **bỏ qua một số thao tác hoặc một số lần gọi lambda** khi vẫn tính được kết quả cuối đúng. Đây là lý do chính `peek` được mô tả là công cụ phục vụ debug.

### 3.1. Không có terminal operation thì không tiêu thụ

```java
Stream.of("A", "B", "C")
        .peek(System.out::println);
// Không có terminal operation; không yêu cầu in phần tử.
```

Mã trên chỉ xây dựng stream rồi bỏ tham chiếu; không có yêu cầu tiêu thụ phần tử.

### 3.2. `count()` có thể tính kết quả từ kích thước nguồn

```java
long size = Stream.of("A", "B", "C")
        .peek(s -> System.out.println("Đang xử lý: " + s))
        .count();

System.out.println(size); // 3
```

Với nguồn có kích thước xác định như `Stream.of("A", "B", "C")`, implementation **có thể suy ra `count() = 3` mà không duyệt từng phần tử**. Do đó các dòng `Đang xử lý` có thể không xuất hiện. Đây là hành vi tối ưu hóa hợp lệ, được tài liệu API nhấn mạnh từ Java 9.

Không thể dùng `peek` làm nơi lưu log kiểm toán hoặc tăng biến `processedCount` rồi giả định giá trị đó luôn đúng với `count()`.

### 3.3. Thao tác ngắn mạch chỉ cần một phần dữ liệu

```java
import java.util.Optional;

Optional<Integer> firstEven = List.of(3, 7, 8, 10, 12).stream()
        .peek(n -> System.out.println("Đang xét: " + n))
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(firstEven); // Optional[8]
```

`findFirst()` có thể dừng khi đã tìm được phần tử đầu tiên theo encounter order. Trong một pipeline tuần tự thông thường, action ở `peek` có thể được gọi với `3`, `7` và `8`; các phần tử `10`, `12` không cần được xét. Không nên viết kiểm thử khẳng định action nhất thiết phải được gọi **đúng** ba lần.

Các thao tác như `findAny`, `anyMatch`, `allMatch`, `noneMatch`, `limit`, `takeWhile` có thể ảnh hưởng số phần tử thực sự được yêu cầu. Với stream song song, một số tác vụ có thể xử lý thêm phần tử quanh thời điểm phát hiện kết quả; vì vậy lượng log cũng không là con số ổn định.

### 3.4. Nguồn rỗng và thao tác lọc hết phần tử

```java
List<String> none = Stream.<String>empty()
        .peek(System.out::println)
        .toList();
System.out.println(none); // []
```

Không có phần tử để quan sát. Tương tự, `filter` có thể loại hết phần tử trước khi chúng đến một `peek` đặt ở phía sau.

### 3.5. Ngoại lệ cũng có thể cắt ngang đường chạy

Nếu `filter`, `map`, `peek` hoặc terminal operation ném exception, pipeline có thể dừng khi lỗi lan ra. Các action trước thời điểm lỗi có thể đã thực hiện tác dụng phụ; Stream API không cung cấp cơ chế tự động rollback.

```java
// Không phải cách quản lý transaction an toàn.
// values.stream()
//       .peek(value -> updateDatabase(value))
//       .map(this::mayThrow)
//       .toList();
```

Đừng gắn thao tác bắt buộc như ghi database, thanh toán, gửi thông báo vào `peek` chỉ vì muốn nó chạy “khi dữ liệu đi qua”.

## 4. Thứ tự, thread và `parallelStream()`

Một stream có **encounter order** (ví dụ nguồn `List`) không đồng nghĩa action của `peek` chạy đúng thứ tự đó trên một thread. Với pipeline song song, thao tác trên phần tử có thể được thực thi ở thread bất kỳ do triển khai quản lý.

```java
List<Integer> input = List.of(1, 2, 3, 4, 5);

List<Integer> output = input.parallelStream()
        .peek(n -> System.out.printf(
                "value=%d, thread=%s%n",
                n, Thread.currentThread().getName()
        ))
        .map(n -> n * 10)
        .toList();

System.out.println(output); // [10, 20, 30, 40, 50]
```

**Thứ tự log không được bảo đảm**, nhưng `toList()` giữ thứ tự kết quả theo encounter order của input. Vì `peek` là action dùng để quan sát, không được dựa vào thứ tự in để suy ra thứ tự kết quả hay cách các phần tử được giao cho worker thread.

### 4.1. `forEach` và `forEachOrdered` giải quyết bài toán khác

```java
List.of(1, 2, 3, 4, 5).parallelStream()
        .forEach(n -> System.out.print(n + " "));
// Thứ tự in không được cam kết.

System.out.println();

List.of(1, 2, 3, 4, 5).parallelStream()
        .forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5
```

`forEachOrdered` bảo đảm action của terminal operation được thực hiện theo encounter order khi nguồn có thứ tự; action xử lý phần tử trước có quan hệ *happens-before* với action xử lý phần tử sau. Điều này **không buộc mọi action chạy trên cùng một thread** và không làm các `peek` phía trước chạy theo đúng thứ tự.

Khi mục đích là tạo danh sách hoặc bảng kết quả, `toList()`, `collect(...)` thường phù hợp hơn dùng `forEach` để tự thêm phần tử vào một danh sách bên ngoài.

### 4.2. `findAny` và `findFirst`

```java
int first = List.of(4, 1, 3).parallelStream()
        .peek(n -> System.out.println("Quan sát: " + n))
        .findFirst()
        .orElseThrow();

System.out.println(first); // 4
```

`findFirst` phải tôn trọng phần tử đầu tiên theo encounter order của stream có thứ tự; với `findAny`, phần tử được chọn có thể là bất kỳ phần tử nào. Cả hai có thể dừng sớm, và `peek` không phải dấu vết đầy đủ về toàn bộ nguồn đã đi qua.

## 5. Tác dụng phụ và ba yêu cầu với lambda trong pipeline

**Tác dụng phụ (side effect)** là việc hàm làm thay đổi hoặc tác động đến trạng thái ngoài giá trị trả về: ghi biến bên ngoài, sửa `List`, cập nhật cơ sở dữ liệu, in log, phát sự kiện, tăng bộ đếm, thay đổi đối tượng dùng chung, v.v.

Để một pipeline dễ hiểu, dễ chạy song song và ít lỗi, hành vi lambda trong phần lớn thao tác stream nên tuân thủ:

1. **Non-interfering:** không thay đổi nguồn dữ liệu không đồng thời đang được stream duyệt. Ví dụ, không thêm/xóa phần tử của `ArrayList` nguồn khi pipeline đang chạy.
2. **Stateless:** kết quả cho một phần tử không phụ thuộc vào trạng thái thay đổi bởi việc xử lý các phần tử khác. `n -> n * 2` là stateless; `n -> runningTotal += n` phụ thuộc trạng thái ngoài.
3. **Tránh side effect nghiệp vụ:** giá trị đầu ra nên thể hiện qua `map`, `filter`, `reduce`, `collect`, không dựa vào số lần `peek` được gọi.

### 5.1. Tránh cập nhật danh sách bên ngoài qua `peek`

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> seen = new ArrayList<>();

// Không nên làm:
// List<Integer> values = List.of(1, 2, 3, 4).parallelStream()
//         .peek(seen::add)
//         .toList();
```

`ArrayList` không an toàn để nhiều thread cùng `add` mà không đồng bộ, nên đoạn mã có thể gặp race condition hoặc kết quả không đáng tin cậy. Ngay cả khi thay bằng danh sách thread-safe, `peek` vẫn không cam kết được gọi cho mọi phần tử trong mọi pipeline.

Nếu mục tiêu là lấy một danh sách, dùng collector:

```java
List<Integer> values = List.of(1, 2, 3, 4).parallelStream()
        .map(n -> n * 2)
        .toList();

System.out.println(values); // [2, 4, 6, 8]
```

Đối với `collect(Collectors.toList())`, framework quản lý việc tích lũy và kết hợp kết quả trong luồng xử lý song song theo hợp đồng collector. Không cần tự chia sẻ một `ArrayList` qua `peek`.

### 5.2. `AtomicInteger` không biến `peek` thành bộ đếm đáng tin cậy

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger observed = new AtomicInteger();

long count = List.of("a", "b", "c").stream()
        .peek(s -> observed.incrementAndGet())
        .count();

System.out.println(count);          // 3
System.out.println(observed.get()); // Có thể là 0 khi count được tối ưu hóa.
```

`AtomicInteger` giúp phép tăng là nguyên tử khi action **được gọi**, nhưng không bắt buộc runtime phải gọi action. Vì thế, bộ đếm này không phải cách đo chính xác số phần tử được `count()` trả về. Dùng `count` làm kết quả đếm; nếu cần ghi nhận số phần tử đã được thực sự xử lý trong một nghiệp vụ, hãy thiết kế cơ chế ghi nhận ở nơi có hợp đồng thực thi rõ ràng.

### 5.3. Không sửa đối tượng nghiệp vụ qua `peek`

```java
record Order(String id, int amount) {}

List<Order> orders = List.of(
        new Order("A", 100),
        new Order("B", 150)
);

// Hãy tính trạng thái mới bằng map và trả về đối tượng dữ liệu mới.
List<Order> discounted = orders.stream()
        .map(order -> new Order(order.id(), order.amount() - 10))
        .toList();

System.out.println(discounted);
// [Order[id=A, amount=90], Order[id=B, amount=140]]
```

Với đối tượng mutable, `peek(order -> order.setAmount(...))` có thể làm thay đổi cả đối tượng mà nguồn và bên khác đang tham chiếu. Tác dụng phụ này khó kiểm soát khi tái sử dụng dữ liệu, tối ưu hóa pipeline hoặc chạy song song. Dùng `map` để tạo dữ liệu đầu ra mới và xử lý cập nhật trạng thái ở lớp nghiệp vụ phù hợp.

## 6. Cách quan sát pipeline một cách có chủ đích

`peek` hữu ích khi muốn trả lời câu hỏi cụ thể: phần tử nào đi qua bước lọc, ở vị trí nào giá trị bị biến đổi, hoặc vì sao một kết quả biến mất. Có thể thêm điểm quan sát tại các ranh giới trước và sau một phép biến đổi:

```java
List<String> names = List.of(" Lan ", "", " Minh ", "An");

List<String> normalized = names.stream()
        .peek(s -> System.out.println("Đầu vào: [" + s + "]"))
        .map(String::trim)
        .peek(s -> System.out.println("Sau trim: [" + s + "]"))
        .filter(s -> !s.isEmpty())
        .peek(s -> System.out.println("Được giữ: [" + s + "]"))
        .map(String::toUpperCase)
        .toList();

System.out.println(normalized); // [LAN, MINH, AN]
```

Trong lúc debug, `peek` giúp nhìn thấy các giai đoạn của pipeline mà không thay đổi biểu thức chuyển đổi. Khi không còn cần quan sát, có thể bỏ `peek` mà ý nghĩa kết quả của pipeline vẫn giữ nguyên.

### 6.1. Ghi log một kết quả cần bảo đảm

Nếu việc ghi log kết quả hoàn chỉnh là yêu cầu của chương trình, ghi sau terminal operation sẽ rõ ràng hơn đặt trong `peek`:

```java
List<Integer> output = List.of(4, 2, 5, 1).stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();

System.out.println("Kết quả cuối: " + output); // [2, 4]
```

Cách này làm rõ: **pipeline tính dữ liệu**, còn phần mã theo sau quyết định làm gì với dữ liệu đã được tạo. Với hệ thống thực tế, có thể dùng framework logging và thực hiện log tại ranh giới xử lý thích hợp, hạn chế ghi dữ liệu nhạy cảm vào log.

### 6.2. Khi cần hành động trên từng phần tử

Nếu nghiệp vụ thật sự yêu cầu tác động lên **từng phần tử** của một tập hữu hạn, một terminal operation như `forEach` hoặc `forEachOrdered` nêu mục đích rõ hơn `peek`. Nhưng hành động đó vẫn cần xử lý thất bại, trùng lặp, thread safety và transaction ở tầng phù hợp:

```java
List<String> names = List.of("An", "Bình", "Chi");
names.stream().forEachOrdered(System.out::println);
// An
// Bình
// Chi
```

Đừng hiểu rằng `forEachOrdered` tự bảo đảm cập nhật database là nguyên tử hoặc có thể rollback. Nếu cần chính sách retry, exactly-once hay giao dịch, phải thiết kế riêng.

## 7. Tác động của `sorted`, `distinct`, `limit` và stream vô hạn

Vị trí đặt `peek` quyết định **nó quan sát giai đoạn logic nào**, không bảo đảm mỗi phần tử đều tạo một dòng log.

### 7.1. Sau `sorted` sẽ nhìn thấy giá trị đã sắp xếp

```java
List<Integer> result = List.of(5, 1, 4, 2).stream()
        .sorted()
        .peek(n -> System.out.println("Sau sort: " + n))
        .toList();

System.out.println(result); // [1, 2, 4, 5]
```

`sorted` là thao tác stateful, thường cần đọc đủ nguồn hữu hạn trước khi xuất kết quả; dòng log trước `sorted` và sau `sorted` có thể phản ánh các giai đoạn khác nhau. Không dựa vào thứ tự các dòng log khi chuyển pipeline sang `parallel()`.

### 7.2. Sau `distinct` chỉ còn phần tử không trùng

```java
List<Integer> unique = List.of(4, 2, 4, 1, 2).stream()
        .distinct()
        .peek(n -> System.out.println("Không trùng: " + n))
        .toList();

System.out.println(unique); // [4, 2, 1]
```

`distinct` loại trùng theo `equals`. Với nguồn `List` có encounter order, lần xuất hiện đầu tiên được giữ; `peek` đặt sau `distinct` phục vụ quan sát các phần tử còn lại.

### 7.3. `limit` và nguồn không giới hạn

```java
List<Integer> sample = java.util.stream.Stream.generate(() -> 7)
        .limit(3)
        .peek(n -> System.out.println("Mẫu: " + n))
        .toList();

System.out.println(sample); // [7, 7, 7]
```

`Stream.generate` có thể sinh phần tử mãi mãi; `limit(3)` khiến kết quả hữu hạn. Tránh dùng `peek` để đếm số lần gọi supplier của nguồn vô hạn, vì tối ưu hóa và short circuit có thể làm hành vi quan sát khác dự đoán. Không chạy `Stream.generate(...).peek(...).toList()` không giới hạn: terminal yêu cầu toàn bộ nguồn nên không hoàn tất và có nguy cơ cạn bộ nhớ.

## 8. Tài nguyên và ngoại lệ trong pipeline

`peek` không thay thế cơ chế quản lý tài nguyên. Với nguồn mở file như `Files.lines(path)`, dùng `try-with-resources` để đóng stream dù việc duyệt hoàn tất hay gặp exception:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<String> readNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .peek(s -> System.out.println("Đang đọc: " + s))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .toList();
    }
}
```

Trong môi trường thật, tránh log trực tiếp toàn bộ nội dung file khi có thông tin riêng tư; quan sát số lượng hoặc mã định danh phù hợp có thể hữu ích hơn. Cần nhớ `Files.lines` giữ tài nguyên được giải phóng bằng `close()`; `peek` và `toList()` tự chúng không đóng stream.

Nếu action trong `peek` ném unchecked exception, exception được lan ra khi pipeline tiêu thụ. Các tác dụng phụ đã thực hiện trước lỗi không được tự động hoàn tác. Với stream song song, không suy rằng tất cả action khác đã dừng tức thì ngay khi một action ném lỗi.

## 9. Một chương trình tổng hợp có thể chạy (Java 17+)

Ví dụ dưới đây đối chiếu việc quan sát bằng `peek`, kết quả được tính qua `toList`, tối ưu hóa `count` và cách dùng `forEachOrdered` khi muốn in theo thứ tự:

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class PeekAndSideEffectsDemo {
    public static void main(String[] args) {
        // (1) Quan sát các giai đoạn của pipeline tuần tự.
        List<Integer> result = List.of(5, 2, 4, 1).stream()
                .peek(n -> System.out.println("Input: " + n))
                .filter(n -> n % 2 == 0)
                .peek(n -> System.out.println("Even: " + n))
                .map(n -> n * 10)
                .toList();
        System.out.println("Result: " + result); // [20, 40]

        // (2) count() có thể tính được từ kích thước nguồn.
        AtomicInteger observed = new AtomicInteger();
        long count = Stream.of("A", "B", "C")
                .peek(s -> observed.incrementAndGet())
                .count();
        System.out.println("Count: " + count); // 3
        System.out.println("Peek calls: " + observed.get());
        // Không được yêu cầu Peek calls == 3; có thể bằng 0.

        // (3) Terminal operation ngắn mạch có thể dừng sớm.
        int firstEven = List.of(3, 5, 8, 10).stream()
                .peek(n -> System.out.println("Find: " + n))
                .filter(n -> n % 2 == 0)
                .findFirst()
                .orElseThrow();
        System.out.println("First even: " + firstEven); // 8

        // (4) Kết quả song song giữ encounter order của List.
        List<Integer> parallelResult = List.of(3, 1, 2)
                .parallelStream()
                .peek(n -> System.out.println(
                        Thread.currentThread().getName() + ": " + n))
                .sorted()
                .toList();
        System.out.println(parallelResult); // [1, 2, 3]

        // (5) Action terminal được yêu cầu theo encounter order.
        List.of("An", "Bình", "Chi").parallelStream()
                .forEachOrdered(System.out::println);
    }
}
```

Tại phần (2), kết quả nghiệp vụ là `Count: 3`; giá trị `Peek calls` chỉ dùng để minh họa tính không bảo đảm của side effect. Tại phần (4), thứ tự của các dòng chứa tên thread có thể khác nhau, nhưng danh sách kết quả cuối được sắp xếp tăng dần.

## 10. Sai lầm thường gặp

| Nhận định/cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| Không gọi terminal operation mà chờ `peek` in | Pipeline lazy nên chưa cần tiêu thụ | Thêm terminal operation phù hợp với mục tiêu |
| `peek(...).count()` phải gọi action N lần | `count` có thể suy ra kích thước mà không duyệt | Dùng giá trị `count()` để đếm |
| `peek` được gọi cho mọi phần tử nguồn | `filter`, short circuit và tối ưu hóa có thể bỏ qua | Xem `peek` là công cụ quan sát, không là kết quả nghiệp vụ |
| `parallelStream().peek(...)` chạy đúng thứ tự `List` | Action có thể chạy ở nhiều thread, thứ tự log không ổn định | Dựa vào encounter order của kết quả hoặc `forEachOrdered` |
| `peek(list::add)` để thu thập kết quả | Trạng thái dùng chung có thể bị race và action có thể bị lược | Dùng `toList()`, `collect(...)` |
| `peek(entity::setStatus)` để cập nhật nghiệp vụ | Tạo side effect, có thể sửa nguồn và khó rollback | Dùng `map` để tạo dữ liệu mới; cập nhật tại lớp nghiệp vụ |
| Dùng `AtomicInteger` trong `peek` để có “đúng số lượng” | Atomic chỉ bảo vệ phép tăng nếu action chạy | Đếm bằng terminal operation hoặc cơ chế theo dõi riêng |
| Cho rằng `forEachOrdered` khiến mọi `peek` chạy theo thứ tự | Bảo đảm áp dụng cho action terminal | Không suy ra thứ tự/tần suất của các intermediate action |
| `peek` rồi `toList` trên stream vô hạn | Không có điểm kết thúc, có thể cạn tài nguyên | Chọn giới hạn hữu hạn hoặc nguồn có điều kiện dừng |
| Lạm dụng log `peek` trong pipeline nóng | I/O, định dạng chuỗi và tranh chấp khóa có thể gây chậm | Chỉ bật quan sát khi cần, đo overhead, log ở mức phù hợp |

## 11. Tự kiểm tra

1. **`Stream.of(1, 2).peek(System.out::println)` có chắc chắn in hai số không?** Không. Chưa có terminal operation nên không yêu cầu tiêu thụ dữ liệu.
2. **`Stream.of("A", "B").peek(...).count()` có chắc action chạy hai lần không?** Không. `count()` có thể lấy kích thước trực tiếp từ nguồn.
3. **`peek` có thay thế `map` được không?** Không. `peek` nhận `Consumer` và chuyển tiếp phần tử, còn `map` nhận `Function` để tạo giá trị mới.
4. **`findFirst` có bảo đảm tất cả phần tử trước và sau kết quả đều được `peek` quan sát không?** Không. Short circuit và chiến lược thực thi có thể khiến một số phần tử không được xử lý.
5. **Dùng `AtomicInteger` trong `peek` có bảo đảm số lần action bằng `count()` không?** Không. Atomic chỉ giúp tăng an toàn nếu action được thực hiện.
6. **Sau `parallelStream().peek(...).sorted().toList()`, thứ tự log có phải tăng dần không?** Không. Thứ tự kết quả từ `toList()` theo sắp xếp, còn action log trong `peek` không có cùng bảo đảm.
7. **Nên dùng gì nếu muốn tập hợp tất cả kết quả vào danh sách?** `toList()` hoặc `collect(Collectors.toList())`, thay vì cập nhật một danh sách ngoài qua `peek`.
8. **Có nên đặt việc ghi database trong `peek` không?** Không nên. Hợp đồng xử lý, giao dịch và lỗi cần được thể hiện rõ ở lớp nghiệp vụ hoặc thao tác terminal thích hợp.

**Điểm cốt lõi:** `peek` rất hữu ích để soi một pipeline khi học và debug, nhưng **hành động bên trong nó không có bảo đảm luôn được gọi, được gọi theo thứ tự hay được gọi đúng một lần trên mỗi phần tử nguồn**. Hãy tính dữ liệu bằng các thao tác khai báo, sử dụng terminal operation để lấy kết quả, và quản lý tác dụng phụ nghiệp vụ ở nơi có hợp đồng thực thi rõ ràng.
