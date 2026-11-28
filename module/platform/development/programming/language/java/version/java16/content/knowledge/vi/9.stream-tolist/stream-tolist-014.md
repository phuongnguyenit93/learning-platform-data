# Chi phí vật chất hóa toàn bộ Stream và giới hạn kích thước dữ liệu

`Stream.toList()` là terminal operation: khi được gọi, pipeline bắt đầu xử lý dữ liệu và phương thức chỉ trả về sau khi đã thu thập các phần tử kết quả vào một `List`. Vì vậy, đây là thao tác **vật chất hóa toàn bộ kết quả** (*materialization*), không phải một view lazy đọc dữ liệu khi caller truy cập.

Với `n` phần tử đầu ra, danh sách phải giữ tham chiếu tới `n` phần tử, nên bộ nhớ dành cho kết quả tăng theo `O(n)`, chưa tính các object do pipeline tạo ra và bộ nhớ tạm của một số operation. Nếu nguồn rất lớn hoặc không giới hạn, `toList()` có thể tiêu thụ nhiều heap, làm tăng áp lực garbage collector hoặc khiến ứng dụng hết bộ nhớ. Chỉ dùng nó khi kích thước kết quả có giới hạn phù hợp và chương trình thực sự cần giữ toàn bộ kết quả.

## 1. `toList()` tiêu thụ stream và giữ toàn bộ kết quả

Các intermediate operation như `filter`, `map` và `peek` thường mô tả pipeline; chúng không tự chạy toàn bộ dữ liệu ngay tại dòng khai báo. Terminal operation như `toList()` kích hoạt quá trình duyệt nguồn:

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .filter(name -> !name.isBlank())
    .map(String::trim)
    .toList();
```

Khi `toList()` hoàn tất:

- Nguồn đã được tiêu thụ theo pipeline.
- Các phần tử đầu ra được giữ trong danh sách kết quả.
- Caller nhận được danh sách để có thể duyệt nhiều lần.
- Stream nguồn đã dùng không thể tiếp tục gọi một terminal operation khác.

Danh sách kết quả là unmodifiable theo hợp đồng API. Tuy nhiên, tính unmodifiable không làm giảm yêu cầu phải giữ các phần tử trong bộ nhớ. Nếu pipeline tạo ra một triệu phần tử, danh sách vẫn phải giữ một triệu phần tử đó để caller có thể truy cập sau khi phương thức trả về.

## 2. Chi phí bộ nhớ tăng theo số phần tử

Với một kết quả gồm `n` phần tử, có thể hình dung chi phí bộ nhớ gồm:

- Cấu trúc lưu trữ danh sách và các tham chiếu tới phần tử.
- Object phần tử nếu pipeline tạo object mới, chẳng hạn qua `map()` tạo DTO.
- Trạng thái hoặc bộ đệm của intermediate operation có trạng thái như `sorted()` và `distinct()`.
- Bộ nhớ tạm phục vụ xử lý song song và kết hợp kết quả, tùy implementation và pipeline.

Ví dụ sau tạo một object mới cho mỗi dòng và giữ tất cả object đó trong kết quả:

```java
import java.util.List;

record UserSummary(String displayName) {}

List<String> source = List.of("An", "Bình", "Chi");

List<UserSummary> summaries = source.stream()
    .map(name -> new UserSummary(name.trim()))
    .toList();
```

Ngoài cấu trúc danh sách, pipeline còn tạo các `UserSummary`. Nếu caller chỉ cần đếm số dòng hợp lệ hoặc tính tổng, tạo và giữ toàn bộ DTO là công việc không cần thiết.

Không có một con số byte cố định cho mỗi phần tử mà chương trình có thể dựa vào. Dung lượng phụ thuộc loại phần tử, kích thước object, implementation JDK, trạng thái pipeline và cách heap được quản lý. Hãy đo bằng dữ liệu gần với tải thực tế nếu cần lập ngân sách bộ nhớ.

## 3. Nguồn vô hạn có thể khiến `toList()` không bao giờ trả về

Một số stream được thiết kế để sinh dữ liệu không giới hạn, chẳng hạn `Stream.iterate()` hoặc `Stream.generate()` không có điều kiện dừng. Nếu gọi `toList()` trực tiếp trên nguồn như vậy, pipeline không có điểm kết thúc tự nhiên:

```java
import java.util.stream.Stream;

var numbers = Stream.iterate(1, number -> number + 1)
    .toList(); // Không hoàn tất với nguồn vô hạn
```

Terminal operation phải chờ stream kết thúc để trả danh sách. Với nguồn vô hạn, nó tiếp tục yêu cầu phần tử và giữ kết quả ngày càng lớn, cuối cùng có thể làm cạn heap hoặc không bao giờ trả về.

Nếu chỉ cần một số lượng phần tử xác định, hãy giới hạn trước khi thu thập:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> firstHundred = Stream.iterate(1, number -> number + 1)
    .limit(100)
    .toList();

System.out.println(firstHundred.size()); // 100
```

`limit(100)` làm pipeline chỉ phát ra tối đa 100 phần tử, nên danh sách kết quả có giới hạn kích thước. Cách này phù hợp khi nghiệp vụ thực sự chỉ cần một prefix hoặc một trang dữ liệu có số phần tử xác định.

## 4. `limit()` giới hạn số phần tử, không biến danh sách thành lazy

`limit(n)` giúp giới hạn số phần tử đầu ra của pipeline. Nhưng sau khi gọi `toList()`, toàn bộ tối đa `n` phần tử đó vẫn được giữ trong danh sách:

```java
import java.util.List;
import java.util.stream.Stream;

record Event(String name) {}

Stream<Event> eventStream = Stream.of(
    new Event("login"), new Event("purchase"), new Event("logout")
);

List<Event> recentEvents = eventStream
    .limit(500)
    .toList();
```

Đây vẫn là materialization, chỉ là materialization có giới hạn 500 phần tử. Nếu `n` rất lớn, bộ nhớ vẫn tăng theo số phần tử được giữ.

Các operation khác không thay thế giới hạn số lượng:

| Operation | Tác động khi kết hợp với `toList()` |
| --- | --- |
| `filter(predicate)` | Bỏ phần tử không đạt điều kiện, nhưng không bảo đảm số phần tử còn lại có giới hạn. |
| `skip(n)` | Bỏ qua `n` phần tử đầu, sau đó vẫn thu thập toàn bộ phần còn lại. |
| `distinct()` | Loại trùng lặp, nhưng phải theo dõi phần tử đã gặp; số giá trị duy nhất vẫn có thể rất lớn. |
| `sorted()` | Sắp xếp kết quả; thường cần giữ dữ liệu để xác định thứ tự trước khi phát ra. |
| `limit(n)` | Giới hạn tối đa số phần tử đầu ra còn `n`. |
| `takeWhile(predicate)` | Với stream có encounter order, lấy prefix liên tiếp cho tới phần tử đầu tiên không đạt điều kiện. |

Đừng cho rằng `filter()` hoặc `distinct()` tự làm dữ liệu nhỏ. Chúng có thể giảm kích thước kết quả trong một số trường hợp, nhưng không đặt ra một giới hạn trên cố định.

## 5. Phân biệt terminal operation có short-circuit với `toList()`

Một số terminal operation có thể dừng sớm khi đã biết kết quả. Chúng hữu ích khi không cần giữ toàn bộ phần tử:

```java
import java.util.List;

record DataRecord(String value, boolean valid) {
    boolean isValid() { return valid; }
}

List<DataRecord> records = List.of(
    new DataRecord("A", false),
    new DataRecord("B", true),
    new DataRecord("C", false)
);

boolean hasInvalidRecord = records.stream()
    .anyMatch(record -> !record.isValid());

var firstInvalidRecord = records.stream()
    .filter(record -> !record.isValid())
    .findFirst();
```

`anyMatch()` có thể dừng khi tìm thấy phần tử thỏa điều kiện. `findFirst()` có thể dừng khi tìm được phần tử đầu tiên theo encounter order. Trái lại, `toList()` cần thu thập tất cả phần tử mà pipeline phát ra trước khi trả về.

Một số operation hữu ích khác khi không cần danh sách:

| Nhu cầu | Operation phù hợp | Kết quả |
| --- | --- | --- |
| Kiểm tra có phần tử nào thỏa điều kiện | `anyMatch()` | `boolean` |
| Kiểm tra mọi phần tử đều thỏa điều kiện | `allMatch()` | `boolean` |
| Kiểm tra không có phần tử nào thỏa điều kiện | `noneMatch()` | `boolean` |
| Lấy một phần tử đầu tiên | `findFirst()` | `Optional<T>` |
| Lấy một phần tử bất kỳ | `findAny()` | `Optional<T>` |
| Tính số lượng | `count()` | `long` |
| Tính tổng số nguyên | `sum()` trên primitive stream | Giá trị số nguyên |
| Tính thống kê số | `summaryStatistics()` | Đối tượng thống kê |

Các operation như `count()`, `min()` hoặc `max()` thường vẫn cần xét toàn bộ phần tử về mặt logic; chúng tránh tạo danh sách nhưng không nhất thiết dừng sớm. Một số pipeline có nguồn đã biết kích thước cho phép implementation tối ưu `count()` mà không duyệt từng phần tử, nên không nên dựa vào side effect trong intermediate operation để buộc chúng chạy. Short-circuiting là đặc tính riêng của từng operation, không phải terminal operation nào trả một giá trị nhỏ cũng tự động dừng sớm.

## 6. Chỉ xử lý từng phần tử khi không cần giữ toàn bộ kết quả

Nếu mục tiêu là ghi log, gửi dữ liệu, cập nhật một hệ thống khác hoặc thực hiện một hành động cho từng phần tử, có thể xử lý trực tiếp trong terminal operation:

```java
import java.util.List;

record DataRecord(String value, boolean valid) {
    boolean isValid() { return valid; }
}

List<DataRecord> records = List.of(
    new DataRecord("A", true),
    new DataRecord("B", false),
    new DataRecord("C", true)
);

records.stream()
    .filter(DataRecord::isValid)
    .forEach(System.out::println);
```

Ví dụ này không tạo một `List` chứa mọi record hợp lệ. Pipeline xử lý từng phần tử theo thứ tự của stream tuần tự và không giữ toàn bộ kết quả chỉ để duyệt sau đó.

Nếu action cần chạy theo encounter order, đặc biệt với parallel stream, dùng `forEachOrdered()`:

```java
import java.util.List;

record DataRecord(String value, boolean valid) {
    boolean isValid() { return valid; }
}

List<DataRecord> records = List.of(
    new DataRecord("A", true),
    new DataRecord("B", false),
    new DataRecord("C", true)
);

records.parallelStream()
    .filter(DataRecord::isValid)
    .forEachOrdered(System.out::println);
```

`forEach()` trên parallel stream không bảo đảm thứ tự action. `forEachOrdered()` bảo đảm thứ tự encounter nhưng có thể hạn chế khả năng song song. Cả hai đều không tự tích lũy kết quả thành một danh sách; tuy nhiên, action của bạn không nên tự giữ toàn bộ phần tử ở một collection khác nếu mục tiêu là giới hạn bộ nhớ.

Không dùng side effect để thay thế một pipeline thuần túy nếu có thể biểu đạt bằng `map`, `filter` hoặc `reduce`. Hãy dùng `forEach` khi mục tiêu thực sự là thực hiện một hành động cho từng phần tử.

## 7. Xử lý dữ liệu lớn theo từng batch

Khi cần ghi dữ liệu theo lô, hãy giới hạn số phần tử giữ trong bộ nhớ cùng lúc. Ví dụ sau đọc file theo stream và gom tối đa 500 dòng vào một batch:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.stream.Stream;

class BatchFileImporter {
    private static final int BATCH_SIZE = 500;

    static void importFile(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            Iterator<String> iterator = lines.iterator();
            List<String> batch = new ArrayList<>(BATCH_SIZE);

            while (iterator.hasNext()) {
                batch.add(iterator.next());

                if (batch.size() == BATCH_SIZE) {
                    processBatch(batch);
                    batch.clear();
                }
            }

            if (!batch.isEmpty()) {
                processBatch(batch);
            }
        }
    }

    private static void processBatch(List<String> batch) {
        // Ghi batch vào database hoặc xử lý đồng bộ tại đây.
    }
}
```

Ở đây, chương trình chỉ giữ tối đa 500 dòng trong `batch` tại một thời điểm, cộng với bộ đệm đọc file và dữ liệu đang được `processBatch()` xử lý. Sau khi xử lý xong, `clear()` giải phóng các tham chiếu trong batch để chúng có thể được garbage collector thu hồi nếu không còn nơi nào giữ chúng.

Nếu `processBatch()` chuyển batch sang xử lý bất đồng bộ hoặc giữ lại tham chiếu, không được xóa rồi tái sử dụng list ngay. Khi đó hãy chuyển quyền sở hữu rõ ràng, hoặc truyền một bản sao cho tác vụ bất đồng bộ. Giới hạn batch chỉ có tác dụng khi consumer xử lý và giải phóng dữ liệu theo đúng vòng đời.

## 8. Đóng stream gắn với tài nguyên bên ngoài

Một số stream được tạo từ tài nguyên cần đóng, ví dụ `Files.lines()` và `Files.walk()`. Hãy dùng try-with-resources để bảo đảm tài nguyên được đóng khi pipeline kết thúc hoặc khi có exception:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

class FileLineProcessor {
    static void process(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            lines.forEach(FileLineProcessor::processLine);
        }
    }

    private static void processLine(String line) {
        System.out.println(line);
    }
}
```

Nếu dùng `toList()` trên file lớn:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

class WholeFileProcessor {
    static void process(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            List<String> allLines = lines.toList();
            processAll(allLines);
        }
    }

    private static void processAll(List<String> lines) {
        System.out.println("Số dòng: " + lines.size());
    }
}
```

Toàn bộ dòng vẫn được giữ trong `allLines` sau khi stream đã đóng. Đóng stream giải phóng tài nguyên file; nó không giải phóng danh sách đang được caller giữ. Nếu không cần xử lý toàn bộ nội dung cùng lúc, hãy xử lý tuần tự hoặc theo batch như phần trước.

## 9. Primitive stream và chi phí boxing

`IntStream`, `LongStream` và `DoubleStream` cung cấp operation chuyên biệt cho dữ liệu số nguyên thủy. Các primitive stream không có phương thức `toList()`; muốn tạo `List<Integer>`, cần chuyển sang `Stream<Integer>` bằng `boxed()`. Nếu chỉ cần tính toán, hãy giữ dữ liệu ở primitive stream thay vì chuyển thành object rồi thu vào `List`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

int total = IntStream.range(0, 1_000_000)
    .sum();

IntSummaryStatistics statistics = IntStream.range(0, 1_000_000)
    .summaryStatistics();
```

Nếu gọi `.boxed().toList()`, các giá trị primitive được boxing thành `Integer` trong `Stream<Integer>` và danh sách phải giữ các phần tử đó:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.range(0, 1_000_000)
    .boxed()
    .toList();
```

Chỉ chuyển sang object collection khi API hoặc nghiệp vụ cần danh sách object. Nếu mục tiêu là tính tổng, trung bình hoặc thống kê, dùng operation của primitive stream để tránh boxing và không cần vật chất hóa danh sách.

## 10. Parallel stream có thể cần thêm bộ nhớ tạm

Parallel stream chia công việc thành nhiều phần. Với terminal operation thu thập kết quả, implementation có thể sử dụng các container trung gian hoặc bộ đệm rồi kết hợp chúng. Vì thế, không nên lập ngân sách bộ nhớ chỉ dựa trên kích thước danh sách cuối cùng.

Các lưu ý thực tế:

- `parallelStream().toList()` vẫn phải giữ toàn bộ kết quả cuối cùng.
- Pipeline có operation trạng thái như `sorted()` có thể cần bộ nhớ để giữ dữ liệu trước khi phát kết quả.
- Kết hợp nhiều phần kết quả có thể làm tăng bộ nhớ tạm trong quá trình thực thi.
- Parallel stream không phải giải pháp để xử lý dữ liệu lớn vượt quá heap.
- Chỉ dùng parallel khi workload và phép đo cho thấy lợi ích; cân nhắc cả chi phí chia nhỏ, kết hợp, cấp phát và đồng bộ.

Nếu dữ liệu vượt quá khả năng giữ trong heap, hãy thay đổi chiến lược xử lý: streaming từng phần tử, batch, ghi kết quả ra file/database hoặc dùng một hệ thống xử lý dữ liệu có khả năng phân trang/phân vùng phù hợp.

## 11. Cách quyết định có nên gọi `toList()`

| Câu hỏi | Nếu câu trả lời là có | Hướng xử lý |
| --- | --- | --- |
| Có cần duyệt kết quả nhiều lần hoặc truy cập theo vị trí sau pipeline không? | Có thể cần giữ danh sách. | Dùng `toList()` nếu số phần tử có giới hạn phù hợp. |
| Nguồn có kích thước không giới hạn hoặc chưa biết? | Không thể giả định materialization an toàn. | Đặt `limit`, phân trang hoặc xử lý từng phần. |
| Chỉ cần kiểm tra điều kiện hoặc lấy một phần tử? | Không cần giữ toàn bộ kết quả. | Dùng `anyMatch`, `findFirst`, `findAny` hoặc operation phù hợp. |
| Chỉ cần tổng, đếm hoặc thống kê? | Không cần danh sách. | Dùng `sum`, `count`, `summaryStatistics` hoặc `reduce`. |
| Cần thực hiện hành động trên từng phần tử? | Không cần giữ danh sách nếu consumer xử lý ngay. | Dùng `forEach`/`forEachOrdered` với side effect được kiểm soát. |
| Cần xử lý theo lô? | Giữ toàn bộ dữ liệu là lãng phí. | Thu thập batch có kích thước cố định rồi giải phóng. |
| Dữ liệu số chỉ dùng để tính toán? | Không cần wrapper object. | Giữ `IntStream`, `LongStream` hoặc `DoubleStream`. |

`toList()` là lựa chọn tốt khi kết quả hữu hạn, có kích thước phù hợp với bộ nhớ và chương trình cần một snapshot danh sách để đọc nhiều lần. Với nguồn lớn hoặc vô hạn, hãy giới hạn, xử lý từng phần hoặc chỉ tính toán giá trị cần thiết. Điều quan trọng là xác định rõ chương trình cần **toàn bộ danh sách** hay chỉ cần **xử lý dữ liệu khi nó đi qua pipeline**.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Stream – Java SE 26 API: lazy evaluation và short-circuiting](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [BaseStream – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html)
- [IntStream – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
- [Files.lines() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset))
