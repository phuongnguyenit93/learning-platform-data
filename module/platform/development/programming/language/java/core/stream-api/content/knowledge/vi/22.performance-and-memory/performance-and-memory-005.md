# Xử lý dữ liệu lớn theo dòng và giới hạn kích thước kết quả

Khi xử lý tệp nhật ký, giao dịch, bảng dữ liệu xuất từ hệ thống hay luồng sự kiện có hàng triệu dòng, thiết kế `Files.readAllLines(path)` rồi giữ toàn bộ dữ liệu trong `List` thường tốn nhiều heap không cần thiết. Java Stream API cho phép **đọc và xử lý từng dòng theo nhu cầu** bằng `Files.lines`, lọc và biến đổi qua pipeline lazy, rồi tính tổng, đếm, ghi ra tệp hoặc thu thập một **kết quả đã giới hạn**. Tuy nhiên, **đọc đầu vào theo dòng không tự động bảo đảm bộ nhớ nhỏ**: một lệnh `collect(toList())`, `sorted()`, `distinct()` hoặc `groupingBy(..., toList())` đặt phía sau vẫn có thể giữ lượng dữ liệu tỷ lệ với toàn bộ nguồn.

Bài thuộc chương **Hiệu năng và bộ nhớ** của module **JAVA_STREAM_API**. Ta sẽ kết hợp pipeline lazy, `filter`, `map`, `reduce` và `collect` để xử lý tập dữ liệu lớn mà không vật chất hóa (*materialize*) mọi bản ghi. Các khái niệm grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và giới hạn tài nguyên cũng được phân tích. Trọng tâm không phải một mẹo “bật Stream sẽ tiết kiệm RAM”, mà là **thiết kế mức giới hạn cho từng loại trạng thái và từng kết quả**.

## 1. Ba giới hạn phải đặt ra trước khi chạy

Giả sử đầu vào có `n` dòng, trong đó `m` dòng hợp lệ, `k` khóa nhóm phân biệt và ứng dụng chỉ cần `K` kết quả ưu tiên.

| Giới hạn | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Đầu vào của một bản ghi** | Một dòng có thể dài bao nhiêu? Mỗi dòng tạo bao nhiêu đối tượng? | Từ chối dòng quá dài; giới hạn kích thước trường văn bản |
| **Trạng thái trung gian** | Phép toán có giữ danh sách, Set, Map hoặc buffer sort tăng theo nguồn không? | Một bộ tổng hợp theo khu vực; một heap top-K |
| **Kết quả đầu ra** | Có giữ toàn bộ kết quả trong bộ nhớ hay chỉ ghi dần/giữ K bản ghi? | `limit(100)`, top-10, ghi qua `BufferedWriter` |

Một thiết kế có `limit(100)` ở cuối vẫn có thể vượt bộ nhớ nếu trước đó `sorted` phải giữ hàng triệu bản ghi. Ngược lại, một pipeline xử lý **tất cả `n` dòng** và chỉ tính `count`/`sum` có thể giữ trạng thái gần như hằng số.

### 1.1. Phân biệt thời gian chạy và bộ nhớ

- **Đọc `n` dòng** cần tối thiểu công sức tỷ lệ với lượng dữ liệu thực sự phải đọc, trừ khi bài toán cho phép dừng sớm hoặc nguồn có chỉ mục.
- **Bộ nhớ không nhất thiết tỷ lệ với `n`**. Một phép cộng có thể duyệt từng dòng và chỉ giữ một biến tổng.
- **Giới hạn số kết quả không đồng nghĩa giới hạn số dòng phải đọc**. Tìm 10 giao dịch lớn nhất toàn tệp vẫn thường phải xét tất cả giao dịch.
- **Nguồn có thể lớn vô hạn** thì các thao tác cần biết toàn bộ nguồn như sắp xếp tổng thể không có điều kiện kết thúc thích hợp.

Ký hiệu `O(1)`, `O(K)`, `O(k)` hay `O(n)` trong bài nói về **bậc bộ nhớ phụ thêm**, không phải một cam kết byte chính xác; JVM còn có object header, buffer, boxing, capacity và chi phí garbage collection.

## 2. Đọc dữ liệu theo dòng bằng Files.lines

Từ Java 8, `java.nio.file.Files.lines(Path, Charset)` tạo `Stream<String>` đọc các dòng từ tệp theo nhu cầu:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = /* đường dẫn tệp đã xác định */;

try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long nonBlank = lines
            .filter(line -> !line.trim().isEmpty())
            .count();

    System.out.println(nonBlank);
}
```

Đoạn minh họa cần đặt trong một phương thức có xử lý/khai báo `IOException`. `Files.lines` không đọc toàn bộ tệp thành một `List<String>` trước khi tạo Stream. Trình đọc có thể cấp phát buffer và từng `String` khi duyệt, còn các bước `filter` và `map` thường không cần giữ mọi dòng trước đó.

### 2.1. So sánh với readAllLines

```java
// Không phù hợp nếu tệp quá lớn so với heap:
List<String> allLines =
        Files.readAllLines(path, StandardCharsets.UTF_8);

// Phương án duyệt theo dòng:
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
}
```

`readAllLines` trả `List` chứa mọi dòng và có bộ nhớ tăng theo số dòng cùng tổng chiều dài văn bản. `Files.lines` cho phép duyệt theo nhu cầu, nhưng **pipeline phía sau quyết định có giữ lại tất cả dòng hay không**.

### 2.2. Files.lines giữ tài nguyên I/O

Stream được tạo bởi `Files.lines` gắn với một tài nguyên mở. Vì thế:

1. Dùng `try-with-resources` để **đóng Stream nguồn**.
2. Đóng vẫn cần thiết khi terminal operation `count`, `findFirst`, `limit` hay `collect` đã chạy xong.
3. Dừng sớm **không tự động đóng tệp**.
4. Đừng trả về một Stream được tạo trong khối `try-with-resources` đã kết thúc: caller sẽ nhận Stream đã đóng.
5. Nếu cố trả Stream còn mở, phải định nghĩa rõ **caller sở hữu trách nhiệm đóng**; với API công khai, một callback/consumer xử lý bên trong phạm vi tài nguyên đôi khi an toàn hơn.

Các lỗi I/O phát sinh **trong lúc duyệt** có thể xuất hiện dưới dạng `UncheckedIOException`, không chỉ `IOException` khi mở tệp. `try-with-resources` vẫn bảo đảm gọi `close` khi rời khối do lỗi hoặc hoàn thành bình thường.

## 3. BufferedReader.lines và các nguồn tương tự

Nếu đã có `BufferedReader`, có thể tạo Stream từ reader:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    Stream<String> lines = reader.lines();
    long count = lines.filter(s -> !s.isEmpty()).count();
}
```

Ở đây, **reader** do chương trình mở được đóng qua `try-with-resources`; không chỉ dựa vào terminal operation trên `reader.lines()`. Tránh tiếp tục đọc `reader` bằng phương thức khác trong khi Stream từ `reader.lines()` đang được tiêu thụ: hai cách duyệt có thể tác động cùng trạng thái nguồn.

| Nguồn | Đặc điểm | Tài nguyên |
|---|---|---|
| `Files.lines(path, UTF_8)` | Đọc các dòng tệp qua Stream | Đóng Stream |
| `BufferedReader.lines()` | Stream từ reader đã mở | Đóng reader sở hữu |
| `Files.list(dir)` | Stream các entry của thư mục | Đóng Stream |
| `Files.walk(dir)` | Duyệt cây thư mục | Đóng Stream |
| `Stream.of(...)` | Phần tử trong bộ nhớ | Thường không giữ tài nguyên I/O |
| `Collection.stream()` | Duyệt collection đã tồn tại | Nguồn dữ liệu vẫn ở bộ nhớ |

`Files.walk` là nguồn đường dẫn, không đọc nội dung mọi tệp ngay lập tức. Nếu dùng `flatMap` để mở từng tệp con, phải làm rõ chính sách đóng nguồn bên trong và xử lý lỗi; không tạo hàng nghìn file reader được giữ mở đồng thời một cách không kiểm soát.

## 4. Lazy pipeline chỉ tiết kiệm RAM khi terminal operation cho phép

Xét pipeline:

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines
            .filter(s -> s.startsWith("ERROR"))
            .count();
}
```

Về ý nghĩa, pipeline có thể duyệt và đếm liên tiếp, không cần List chứa tất cả dòng `ERROR`. Nếu thay terminal operation:

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> errors = lines
            .filter(s -> s.startsWith("ERROR"))
            .collect(java.util.stream.Collectors.toList());
}
```

Danh sách `errors` cần giữ **mọi dòng lỗi**, nên bộ nhớ tăng theo số dòng lỗi và chiều dài của chúng. Việc nguồn là `Files.lines` **không xóa chi phí của `toList`**.

### 4.1. Phân tích theo số bản ghi giữ lại

| Pipeline | Trạng thái/đầu ra cần giữ thông thường |
|---|---|
| `lines.count()` | Nhỏ, gần `O(1)` |
| `lines.map(...).reduce(...)` | Tùy reduction, nhiều phép số học `O(1)` |
| `lines.filter(...).findFirst()` | Nhỏ; có thể dừng sớm |
| `lines.filter(...).limit(K).toList()` | Khoảng `O(K)` cộng kích thước `K` phần tử được giữ |
| `lines.sorted().limit(K).toList()` | Có thể phải giữ `O(n)` trước `limit` |
| `lines.distinct().limit(K).toList()` | Thường có trạng thái “đã gặp”; số mục giữ phụ thuộc đường thực thi và phần nguồn đã tiêu thụ |
| `lines.collect(groupingBy(key, counting()))` | `O(k)` trạng thái nhóm |
| `lines.collect(groupingBy(key, toList()))` | `O(k+n)` tham chiếu cho nhóm và phần tử |

Đây là mô hình thường gặp cho **nguồn tổng quát**. JVM và Stream implementation có thể tối ưu trong các trường hợp đặc biệt; không nên coi ký hiệu O ở bảng là đặc tả về mọi runtime.

### 4.2. Đặc biệt thận trọng với phần tử văn bản rất dài

`Files.lines` cho đọc theo **dòng**, nhưng một dòng có thể rất dài. Do đó không được suy ra “mỗi thời điểm chỉ có một dòng” thì bộ nhớ luôn có giới hạn nhỏ. Một dòng vài trăm MB có thể làm ứng dụng thiếu heap trước cả khi predicate của `filter` kiểm tra được nó.

Đoạn kiểm tra:

```java
.map(line -> {
    if (line.length() > 1024) {
        throw new IllegalArgumentException("Dòng quá dài");
    }
    return line;
})
```

chỉ **từ chối sau khi String dòng đã được tạo**. Nó hữu ích cho chính sách dữ liệu, nhưng **không phải giới hạn cứng về bộ nhớ khi đọc**. Nếu phải bảo đảm không bao giờ materialize một dòng quá ngưỡng, cần reader/parser đọc từng khối ký tự và **đếm giới hạn trước khi tích lũy toàn dòng**, hoặc áp dụng giới hạn ở tầng nguồn.

## 5. Đặt limit đúng chỗ và hiểu ý nghĩa kết quả

`limit(K)` là thao tác **short-circuiting stateful intermediate operation**: với Stream có encounter order, nó giữ tối đa **K phần tử đầu theo thứ tự nguồn**.

```java
List<String> firstTenErrors;
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    firstTenErrors = lines
            .filter(s -> s.startsWith("ERROR"))
            .limit(10)
            .collect(Collectors.toList());
}
```

Kết quả có nhiều nhất 10 dòng lỗi. `filter` được đặt **trước `limit`**, nên chương trình đang tìm **10 dòng lỗi đầu tiên** chứ không phải “lấy 10 dòng đầu tệp rồi tìm lỗi”.

### 5.1. Thứ tự filter và limit làm thay đổi ngữ nghĩa

```java
// Lấy tối đa 10 dòng lỗi xuất hiện đầu tiên trong toàn nguồn.
lines.filter(isError).limit(10);

// Chỉ kiểm tra 10 dòng đầu nguồn; có thể trả ít hơn 10 lỗi.
lines.limit(10).filter(isError);
```

Đây là các **mẫu pipeline riêng**, không dùng lại cùng đối tượng `lines` sau một terminal operation. `isError` là predicate đã định nghĩa trong ứng dụng.

Nếu có triệu dòng và lỗi thứ mười xuất hiện gần cuối, phiên bản đầu vẫn có thể phải đọc gần cả triệu dòng. Vì thế `limit(10)` giới hạn **số phần tử đầu ra**, không giới hạn số phần tử đầu vào phải xét.

### 5.2. sorted trước limit không có giới hạn bộ nhớ K

```java
List<Event> top = events.stream()
        .sorted(Comparator.comparingLong(Event::getAmountCents)
                .reversed())
        .limit(10)
        .collect(Collectors.toList());
```

Pipeline có thể giữ tới toàn bộ `n` phần tử để sắp xếp trước khi trả top-10. Nếu cần **10 giao dịch lớn nhất trên toàn tệp**, việc dùng `limit(10)` không đủ để bảo đảm bộ nhớ tăng thêm chỉ `O(10)`. Phần 8 sẽ dùng **heap kích thước K** để giải quyết bài toán chính xác hơn.

### 5.3. skip/limit không tạo phân trang ngẫu nhiên giá rẻ

`lines.skip(offset).limit(pageSize)` có thể giới hạn **kích thước trang kết quả**, nhưng muốn đến dòng thứ một triệu của tệp thì chương trình thường vẫn phải duyệt/bỏ qua các dòng phía trước. Đây **không phải truy cập ngẫu nhiên O(1)**. Nếu dữ liệu có chỉ mục ở database hoặc storage, cân nhắc truy vấn có chỉ mục/keyset pagination thay vì liên tục quét từ đầu file.

### 5.4. limit trên Stream không có thứ tự

Với nguồn không có encounter order hoặc pipeline gọi `unordered()`, `limit(K)` được phép chọn một tập con phù hợp theo hợp đồng, không có ý nghĩa “K bản ghi xuất hiện sớm nhất”. Nếu nghiệp vụ cần **đúng K dòng đầu theo thứ tự file**, giữ nguồn và pipeline có thứ tự, tránh các thay đổi thứ tự không cần thiết.

## 6. Ba cách giới hạn bộ nhớ khi tổng hợp

### 6.1. Thu hẹp phần tử rồi đếm/tổng hợp bằng số

Nếu yêu cầu là **tổng số dòng giao dịch và tổng tiền**, chỉ giữ bộ đếm:

```java
long totalCents;
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    totalCents = lines
            .skip(1) // Bỏ header theo đúng định dạng tệp.
            .map(BoundedStreamingReportDemo::parse)
            .mapToLong(Event::getAmountCents)
            .reduce(0L, Math::addExact);
}
```

Đoạn minh họa dùng `parse` và `Event` từ chương trình đầy đủ ở phần 9. `Math.addExact` giúp phát hiện tràn `long`; nó không làm phát sinh một danh sách các sự kiện đã đọc.

### 6.2. Grouping bằng số liệu, không giữ danh sách dòng

```java
Map<String, Long> countByRegion;
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    countByRegion = lines
            .skip(1)
            .map(BoundedStreamingReportDemo::parse)
            .collect(Collectors.groupingBy(
                    Event::getRegion,
                    Collectors.counting()));
}
```

Bộ nhớ phụ thuộc vào **số khu vực phân biệt `k`** thay vì số giao dịch `n`, với điều kiện giá trị Map chỉ là số đếm. Nhưng **`k` có thể gần bằng `n`** nếu khóa không được kiểm soát. Muốn có giới hạn RAM đáng tin, phải xác định hoặc giới hạn số khóa nhóm, không chỉ giả định `groupingBy` “nhỏ”.

### 6.3. Dùng collector có trạng thái giới hạn

Để lấy **K giao dịch có giá trị lớn nhất**, giữ **min-heap tối đa K phần tử**. Để báo cáo theo khu vực, giữ Map tối đa một số khóa được phép `maxGroups`. Hai giới hạn có thể kết hợp thành một collector tùy chỉnh để **duyệt nguồn một lần**.

Mô hình trạng thái:

```text
Stream<Event> (đọc từ tệp)
         |
         v
  BoundedAccumulator
   - totalCount: long                 O(1)
   - totalCents: long                 O(1)
   - byRegion: Map<String, Stats>     O(maxGroups)
   - bestEvents: PriorityQueue<Event> O(K)
         |
         v
Report: số liệu + Map nhóm + danh sách K giao dịch lớn nhất
```

Với độ dài ID/khu vực được kiểm soát, bộ nhớ **trạng thái và kết quả** tăng chủ yếu theo `O(maxGroups + K)`. Nguồn vẫn phải đọc mọi dòng cần thiết, nhưng không lưu cả `n` sự kiện.

## 7. Lựa chọn giữa kết quả giới hạn và xuất dữ liệu liên tục

Có hai loại bài toán dễ bị nhầm:

1. **Giới hạn số bản ghi kết quả**: chỉ cần 100 sự kiện đầu hoặc 10 sự kiện lớn nhất. Giữ K phần tử trong bộ nhớ là hợp lý.
2. **Cần xuất toàn bộ kết quả nhưng không giữ trong heap**: ví dụ chuyển đổi một tệp 50 GB thành tệp đã chuẩn hóa. Khi đó không thể giảm **số dòng cần ghi**, nhưng có thể ghi từng dòng trực tiếp vào `BufferedWriter` thay vì tạo một List khổng lồ.

### 7.1. Ghi kết quả từng dòng

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static void exportNormalized(Path input, Path output)
        throws IOException {
    try (Stream<String> lines =
                 Files.lines(input, StandardCharsets.UTF_8);
         BufferedWriter writer =
                 Files.newBufferedWriter(output,
                         StandardCharsets.UTF_8)) {
        lines.map(String::trim)
                .filter(s -> !s.isEmpty())
                .forEachOrdered(line -> {
                    try {
                        writer.write(line);
                        writer.newLine();
                    } catch (IOException cause) {
                        throw new UncheckedIOException(cause);
                    }
                });
    } catch (UncheckedIOException failure) {
        throw failure.getCause();
    }
}
```

Ở đây, **output phải khác input**: không mở cùng một tệp để vừa đọc vừa ghi đè. Ví dụ áp dụng chính sách đơn giản “trim rồi bỏ dòng trống”, không giải quyết quoting/CSV. `forEachOrdered` bảo toàn thứ tự hành động khi nguồn có encounter order; quá trình ghi file là **side effect có chủ đích tại terminal operation**, không dùng shared mutable List.

**Hệ quả quan trọng:** nếu ghi giữa chừng rồi lỗi, tệp output có thể chỉ chứa một phần kết quả. Với ứng dụng đòi hỏi tính nguyên tử, hãy ghi vào **tệp tạm cùng filesystem**, đóng thành công, rồi chuyển/đổi tên theo chiến lược phù hợp với hệ điều hành. Chương trình cần quyết định xóa tệp tạm và cách phục hồi sau lỗi; `Stream` không tự cung cấp transaction cho file.

### 7.2. Không dùng parallel forEach để ghi một writer chung

`parallel().forEach(...)` có thể gọi các action đồng thời và không giữ thứ tự, trong khi `BufferedWriter` không tự động trở thành một cơ chế xuất dữ liệu đồng thời an toàn. Nếu mục tiêu chỉ là truyền dữ liệu vào một tệp theo thứ tự, xử lý tuần tự hoặc thiết kế một pipeline có điều phối rõ ràng thường dễ hiểu và an toàn hơn.

## 8. Top-K toàn tệp bằng heap giới hạn

Giả sử có `n` giao dịch và chỉ cần **K giao dịch lớn nhất** theo số tiền. Với K nhỏ hơn rất nhiều n:

- `sorted(desc).limit(K)` thường cần bộ nhớ trung gian `O(n)`.
- Một **min-heap giữ tối đa K ứng viên tốt nhất** cần trạng thái `O(K)`.
- Mỗi giao dịch mới được so với ứng viên nhỏ nhất trong top-K hiện tại.

Thuật toán:

```text
heap rỗng (min-heap), capacity K

với mỗi giao dịch e:
    nếu heap.size < K:
        thêm e
    ngược lại nếu e có hạng cao hơn heap.peek:
        bỏ heap.peek
        thêm e
    ngược lại:
        không giữ e

sau khi đọc hết:
    lấy tối đa K giao dịch từ heap
    sắp xếp K kết quả theo thứ tự mong muốn
```

Độ phức tạp thông thường: **`O(n log K + K log K)` thời gian** và **`O(K)` bộ nhớ bổ sung** cho heap và danh sách kết quả cuối. Trường hợp K = 0 có thể trả danh sách rỗng mà không cần heap chứa phần tử.

### 8.1. Tie-breaker là một phần của tính đúng

Nếu có hai giao dịch cùng số tiền, ứng dụng phải quyết định giữ giao dịch nào khi chỉ còn một chỗ. Có thể so theo:

1. `amountCents` tăng dần.
2. `id` tăng dần để phá hòa.

Trong một top-K chọn **hạng lớn nhất**, giao dịch có ID lớn hơn sẽ có hạng cao hơn khi số tiền bằng nhau. Đây chỉ là **quy tắc minh họa**; với báo cáo thật, có thể chọn timestamp, id hoặc yêu cầu giữ toàn bộ các trường hợp đồng hạng. Nếu phải giữ **mọi đồng hạng ở biên K**, kích thước đầu ra có thể vượt K và không còn là bài toán top-K giới hạn tuyệt đối.

### 8.2. Vì sao không lấy trung bình K ứng viên làm ngưỡng?

Để biết ứng viên mới có nên vào top-K hay không, chỉ cần so với phần tử **nhỏ nhất trong tập K ứng viên đang giữ**, không cần tính trung bình hoặc sắp xếp lại toàn bộ tập sau mỗi dòng. `PriorityQueue` hỗ trợ `peek/poll/offer` với chi phí phù hợp.

## 9. Chương trình Java 8 hoàn chỉnh: báo cáo giới hạn bộ nhớ trong một lần đọc

Chương trình này chạy trên **JDK 8 trở lên**. Nó tạo một tệp TSV nhỏ để minh họa (hoặc đọc đường dẫn người dùng truyền vào), dùng `Files.lines` và **một collector tùy chỉnh** để:

- Đếm mọi giao dịch hợp lệ sau header.
- Cộng tổng tiền đã đọc bằng `Math.addExact`.
- Đếm và cộng tiền theo khu vực, **giới hạn số khu vực tối đa**.
- Chọn **top-3 giao dịch có số tiền lớn nhất** bằng một `PriorityQueue` không vượt 3 phần tử.
- Trả một báo cáo không lộ Map/List mutable nội bộ.

Định dạng dữ liệu: **TSV** (*tab-separated values*) với đúng ba cột `id`, `region` và `amountCents`. Đây là ví dụ đơn giản, **không phải bộ phân tích CSV có trường được quote**.

### 9.1. Mã nguồn tự chạy

Lưu thành `BoundedStreamingReportDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class BoundedStreamingReportDemo {

    static final class Event {
        private final String id;
        private final String region;
        private final long amountCents;

        Event(String id, String region, long amountCents) {
            this.id = id;
            this.region = region;
            this.amountCents = amountCents;
        }

        String getId() { return id; }
        String getRegion() { return region; }
        long getAmountCents() { return amountCents; }
    }

    // Thứ tự tăng dần theo tiền rồi ID. Heap giữ hạng thấp nhất ở đỉnh.
    private static final Comparator<Event> RANK =
            Comparator.comparingLong(Event::getAmountCents)
                    .thenComparing(Event::getId);

    static Event parse(String rawLine) {
        // Từ chối dòng dài sau khi String đã được tạo.
        // Đây KHÔNG phải hard limit cho bộ nhớ đọc một dòng.
        if (rawLine.length() > 1024) {
            throw new IllegalArgumentException("Dòng quá dài");
        }

        String[] fields = rawLine.split("\t", -1);
        if (fields.length != 3) {
            throw new IllegalArgumentException(
                    "Phải có 3 trường TSV: " + rawLine);
        }

        String id = fields[0].trim();
        String region = fields[1].trim();
        if (id.isEmpty() || region.isEmpty()
                || id.length() > 32 || region.length() > 24) {
            throw new IllegalArgumentException(
                    "ID hoặc khu vực không hợp lệ");
        }

        long cents = Long.parseLong(fields[2].trim());
        if (cents < 0) {
            throw new IllegalArgumentException(
                    "Số tiền không được âm");
        }
        return new Event(id, region, cents);
    }

    // Số liệu của một khu vực.
    static final class RegionTotals {
        long count;
        long sumCents;

        void add(long cents) {
            count = Math.addExact(count, 1L);
            sumCents = Math.addExact(sumCents, cents);
        }

        void combine(RegionTotals right) {
            count = Math.addExact(count, right.count);
            sumCents = Math.addExact(sumCents, right.sumCents);
        }
    }

    // Value DTO không còn được thay đổi sau khi tạo.
    static final class RegionView {
        final long count;
        final long sumCents;

        RegionView(long count, long sumCents) {
            this.count = count;
            this.sumCents = sumCents;
        }
    }

    // A: trạng thái mutable của một Collector.
    static final class BoundedState {
        final int topK;
        final int maxRegions;
        long count;
        long totalCents;
        final Map<String, RegionTotals> byRegion = new HashMap<>();
        final PriorityQueue<Event> best = new PriorityQueue<>(RANK);

        BoundedState(int topK, int maxRegions) {
            if (topK < 0 || maxRegions <= 0) {
                throw new IllegalArgumentException(
                        "topK phải >= 0 và maxRegions phải > 0");
            }
            this.topK = topK;
            this.maxRegions = maxRegions;
        }

        void keepCandidate(Event event) {
            if (topK == 0) {
                return;
            }
            if (best.size() < topK) {
                best.offer(event);
            } else if (RANK.compare(event, best.peek()) > 0) {
                best.poll();
                best.offer(event);
            }
        }

        RegionTotals getOrCreate(String region) {
            RegionTotals state = byRegion.get(region);
            if (state == null) {
                if (byRegion.size() >= maxRegions) {
                    throw new IllegalStateException(
                            "Vượt giới hạn số khu vực");
                }
                state = new RegionTotals();
                byRegion.put(region, state);
            }
            return state;
        }

        // Accumulator: cập nhật mọi chỉ số cho đúng một Event.
        void add(Event event) {
            count = Math.addExact(count, 1L);
            totalCents = Math.addExact(
                    totalCents, event.getAmountCents());
            getOrCreate(event.getRegion())
                    .add(event.getAmountCents());
            keepCandidate(event);
        }

        // Combiner đúng hợp đồng cho trường hợp framework chia nguồn.
        BoundedState combine(BoundedState right) {
            if (topK != right.topK || maxRegions != right.maxRegions) {
                throw new IllegalArgumentException(
                        "Cấu hình accumulator không khớp");
            }

            count = Math.addExact(count, right.count);
            totalCents = Math.addExact(
                    totalCents, right.totalCents);

            right.byRegion.forEach((region, totals) -> {
                getOrCreate(region).combine(totals);
            });

            // Top-K của hợp hai tập nằm trong hợp hai top-K cục bộ.
            for (Event event : right.best) {
                keepCandidate(event);
            }
            return this;
        }

        Report finish() {
            Map<String, RegionView> regions = new TreeMap<>();
            byRegion.forEach((region, totals) -> regions.put(
                    region, new RegionView(
                            totals.count, totals.sumCents)));

            List<Event> sortedBest = new ArrayList<>(best);
            sortedBest.sort(RANK.reversed());

            return new Report(
                    count,
                    totalCents,
                    Collections.unmodifiableMap(regions),
                    Collections.unmodifiableList(sortedBest));
        }
    }

    // R: kết quả không lộ trạng thái mutable của Collector.
    static final class Report {
        final long count;
        final long totalCents;
        final Map<String, RegionView> byRegion;
        final List<Event> bestEvents;

        Report(long count, long totalCents,
                Map<String, RegionView> byRegion,
                List<Event> bestEvents) {
            this.count = count;
            this.totalCents = totalCents;
            this.byRegion = byRegion;
            this.bestEvents = bestEvents;
        }
    }

    static Collector<Event, BoundedState, Report> boundedCollector(
            int topK, int maxRegions) {
        return Collector.of(
                () -> new BoundedState(topK, maxRegions),
                BoundedState::add,
                BoundedState::combine,
                BoundedState::finish);
    }

    static void reportFrom(Path input) throws IOException {
        Report report;
        try (Stream<String> lines =
                     Files.lines(input, StandardCharsets.UTF_8)) {
            report = lines
                    .skip(1) // Một header trong định dạng TSV mẫu.
                    .filter(line -> !line.trim().isEmpty())
                    .map(BoundedStreamingReportDemo::parse)
                    .collect(boundedCollector(3, 1000));
        }

        System.out.println("Giao dịch: " + report.count);
        System.out.println("Tổng cents: " + report.totalCents);
        report.byRegion.forEach((region, totals) ->
                System.out.println(region
                        + ": count=" + totals.count
                        + ", cents=" + totals.sumCents));

        System.out.println("Top giao dịch:");
        report.bestEvents.forEach(event ->
                System.out.println(event.getId()
                        + ": " + event.getAmountCents()));
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 1) {
            reportFrom(Paths.get(args[0]));
            return;
        }
        if (args.length != 0) {
            throw new IllegalArgumentException(
                    "Cách dùng: java BoundedStreamingReportDemo [file.tsv]");
        }

        // Tự tạo dữ liệu mẫu để chạy mà không cần chuẩn bị file.
        Path sample = Files.createTempFile("bounded-stream-", ".tsv");
        try {
            Files.write(sample, Arrays.asList(
                    "id\tregion\tamountCents",
                    "E01\tBAC\t120",
                    "E02\tNAM\t990",
                    "E03\tBAC\t500",
                    "E04\tTRUNG\t1500",
                    "E05\tNAM\t250",
                    "E06\tBAC\t1500",
                    "E07\tNAM\t0"
            ), StandardCharsets.UTF_8);
            reportFrom(sample);
        } finally {
            Files.deleteIfExists(sample);
        }
    }
}
```

### 9.2. Chạy và diễn giải đầu ra

Trên JDK 8 trở lên:

```text
javac BoundedStreamingReportDemo.java
java BoundedStreamingReportDemo
```

Nội dung kỳ vọng:

```text
Giao dịch: 7
Tổng cents: 4860
BAC: count=3, cents=2120
NAM: count=3, cents=1240
TRUNG: count=1, cents=1500
Top giao dịch:
E06: 1500
E04: 1500
E02: 990
```

Tổng nhóm: `2120 + 1240 + 1500 = 4860`. Heap chỉ giữ tối đa **3 ứng viên**. Khu vực có tối đa **1000 khóa**; nếu dữ liệu xuất hiện khu vực thứ 1001, collector **thất bại rõ ràng** thay vì tự ý chiếm thêm bộ nhớ cho khóa nhóm.

Trong chế độ thực tế, chạy:

```text
java BoundedStreamingReportDemo data.tsv
```

với đúng định dạng TSV và chính sách đầu vào đã công bố. Demo không tự đọc toàn bộ tệp thành List; tệp chỉ được tạo trong nhánh mẫu để có dữ liệu chạy thử.

### 9.3. Vì sao một collector đủ cho nhiều chỉ số?

Trong `BoundedState.add`, một `Event` cập nhật số đếm chung, tổng chung, thống kê khu vực và heap. **Không cần** mở lại tệp bốn lần để tính bốn đại lượng. Bộ tích lũy cuối tạo `Report` chứa một bản sao kết quả cần lưu.

`BoundedState.combine` cũng được viết đủ để hợp nhất hai nhánh nếu framework chọn cách tích lũy phân nhánh. Phép cộng số, phép gộp theo khóa và top-K theo comparator có thứ tự toàn phần phải được thiết kế đúng; **không công bố `CONCURRENT`** vì `HashMap` và `PriorityQueue` không an toàn cho nhiều worker cùng sửa một instance.

Tuy vậy, **nguồn tệp trong ví dụ mặc định chạy tuần tự**. Không nên thêm `parallel()` vào `Files.lines` chỉ vì đã có combiner: việc đọc tệp, parse và gộp có thể mất lợi ích do I/O, phân chia nguồn hoặc tranh chấp tài nguyên. Cần đo cụ thể trước khi bật.

### 9.4. Top-K có thể gộp từ các nhánh

Với comparator xác định hạng cho các Event, nếu một Event **không nằm trong top-K của chính nhánh**, có ít nhất K Event trong nhánh đó xếp cao hơn nó; vì thế nó không thể nằm trong top-K của toàn bộ dữ liệu khi gộp thêm các nhánh khác. Do đó, việc xét ứng viên từ **top-K của mỗi nhánh** đủ để tạo top-K chung.

Ví dụ yêu cầu ID giao dịch là **duy nhất** để phá hòa một cách xác định. Nếu khóa xếp hạng không xác định thứ tự đầy đủ, hoặc nghiệp vụ muốn giữ tất cả giao dịch bằng hạng tại biên K, phải điều chỉnh thuật toán và quy tắc giới hạn.

### 9.5. Những giới hạn mà demo chưa giải quyết

Demo dùng cách kiểm tra dòng dài **sau khi đã đọc cả dòng thành String**; nếu cần chống dòng cực dài ở tầng input, phải sử dụng reader/parser có giới hạn **trước khi materialize dòng**. Giới hạn số khóa cũng chưa đủ nếu mỗi khóa được phép dài vô hạn, nên code giới hạn `region.length()` và `id.length()`.

Ngoài ra, `split("\t", -1)` là cách phân tách TSV đơn giản, không hiểu escaping, dấu tab nằm trong giá trị hoặc trường quoted. Định dạng CSV/JSON Lines thực tế cần parser phù hợp. Code ví dụ dừng khi dữ liệu sai thay vì âm thầm bỏ dòng; một hệ thống sản xuất có thể cần chính sách *dead-letter*, đếm dòng lỗi và ghi nhật ký an toàn.

## 10. Lưu ý về phân trang và tải dữ liệu theo đợt

Khi nguồn là database/API, **giới hạn kết quả phải bắt đầu từ tầng có khả năng áp dụng nó hiệu quả**:

- Với truy vấn có sắp xếp theo khóa có chỉ mục, truy vấn theo khóa tiếp theo (*keyset/cursor pagination*) có thể tránh phải quét/bỏ qua quá nhiều bản ghi của trang trước.
- Với tệp văn bản thuần không có chỉ mục, `skip(offset)` thường vẫn phải đọc/duyệt những phần tử trước offset.
- Với nguồn sự kiện không hữu hạn, cần có quy tắc ngừng theo số bản ghi, thời gian, kích thước hoặc dừng theo tín hiệu nghiệp vụ; không gọi `sorted().collect(toList())` trên một luồng không kết thúc.
- Một đợt (*batch*) nên có giới hạn kích thước rõ ràng. Khi ghi mỗi batch ra nơi lưu trữ, giải phóng tham chiếu tới batch cũ trước khi tạo batch mới.

### 10.1. Ví dụ xử lý từng batch tuần tự

```java
final int BATCH_SIZE = 500;
List<Event> batch = new ArrayList<>(BATCH_SIZE);

try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    lines.skip(1)
            .map(BoundedStreamingReportDemo::parse)
            .forEachOrdered(event -> {
                batch.add(event);
                if (batch.size() == BATCH_SIZE) {
                    processBatch(batch);
                    batch.clear();
                }
            });
}

if (!batch.isEmpty()) {
    processBatch(batch);
    batch.clear();
}
```

`processBatch(batch)` trong ví dụ là **hàm do ứng dụng cung cấp**. Hàm đó phải xử lý **đồng bộ** và không giữ tham chiếu tới `batch` sau khi trả về; nếu nó gửi batch bất đồng bộ rồi ta `clear()`, tác vụ phía sau có thể thấy danh sách đã bị xóa. Với xử lý async, cần chuyển quyền sở hữu của bản sao batch hoặc thiết kế hàng đợi có giới hạn và tín hiệu backpressure.

Giới hạn `BATCH_SIZE` kiểm soát **số phần tử trong buffer**, nhưng nếu mỗi `Event` chứa dữ liệu cực lớn thì ngân sách RAM vẫn không chắc chắn. Ngoài ra, nếu `processBatch` lỗi, cần chính sách retry/idempotency để tránh mất hoặc ghi trùng dữ liệu; Stream không tự cung cấp transaction.

### 10.2. Backpressure và giới hạn hàng đợi

Một producer đọc tệp nhanh hơn consumer ghi database có thể tạo hàng đợi không giới hạn nếu triển khai bằng cách liên tục `submit` tác vụ. Dù mỗi batch chỉ có 500 phần tử, **10.000 batch chờ** vẫn giữ hàng triệu phần tử.

Vì vậy, khi tách producer/consumer, cần ràng buộc **cả kích thước batch lẫn số batch đang chờ**. Các phương án gồm hàng đợi bounded, semaphore hoặc cơ chế backpressure tương ứng với framework đang dùng. `parallelStream()` không tự bảo đảm giới hạn tổng dung lượng hàng đợi nghiệp vụ.

## 11. Thứ tự, tính lặp lại và xử lý song song

### 11.1. Encounter order

`Files.lines` phát các dòng theo thứ tự trong tệp. Nếu kết quả cần **10 dòng lỗi đầu**, nên giữ pipeline có thứ tự và dùng `filter(...).limit(10)`. `forEachOrdered` thích hợp khi thứ tự side effect như ghi tệp là một yêu cầu rõ ràng.

Nếu chuyển thành `parallel()`, không được dùng `forEach` rồi kỳ vọng các dòng được ghi ra theo thứ tự ban đầu. Nếu chỉ tính count hoặc tổng có phép kết hợp đúng, thứ tự có thể không quan trọng; tuy vậy, vẫn cần kiểm tra lợi ích hiệu năng.

### 11.2. findFirst và findAny

`findFirst()` chọn phần tử đầu theo encounter order khi nguồn có thứ tự. `findAny()` có thể chọn một phần tử phù hợp bất kỳ để có thêm tự do song song. Nếu cần tìm **dòng lỗi đầu tiên trong tệp**, không thay `findFirst` thành `findAny` chỉ để “tối ưu” mà làm thay đổi ý nghĩa kết quả.

### 11.3. Giới hạn và distinct

`distinct` thường giữ thông tin về giá trị đã thấy. Với nguồn rất lớn nhưng số phần tử phân biệt gần bằng n, bảng băm có thể lớn. Nếu chỉ cần một số **SKU phân biệt đầu tiên** theo thứ tự, `map(...).distinct().limit(K)` có thể dừng sớm sau K giá trị phân biệt, nhưng lượng dữ liệu phải đọc đến khi thấy đủ K có thể rất lớn. Với dữ liệu cần **tất cả** SKU phân biệt, Set có thể tăng tới O(u); cần xem xét lưu trữ ngoài heap hoặc database khi `u` quá lớn.

## 12. Xử lý dữ liệu lỗi, độ chính xác và tính nhất quán

### 12.1. Tránh mất dòng vì lọc lỗi âm thầm

Một pipeline như:

```java
lines.map(BoundedStreamingReportDemo::parse)
     .filter(event -> event.getAmountCents() > 0)
```

đang **loại tất cả giao dịch bằng 0**. Nếu số 0 là giao dịch hợp lệ, việc này làm sai số đếm và số liệu theo nhóm. Trước khi “lọc để nhanh hơn”, xác định rõ tập bản ghi nào phải được tính trong báo cáo.

Với dữ liệu hỏng, hai chiến lược thường gặp là:

- **Fail-fast**: dừng khi gặp dòng không hợp lệ, trả lỗi rõ ràng.
- **Tiếp tục và thống kê lỗi**: tách bản ghi hợp lệ/không hợp lệ, đếm loại lỗi và có thể ghi vào một nơi xử lý riêng.

Không nên vừa lặng lẽ bỏ dòng hỏng vừa công bố “đã xử lý đầy đủ n giao dịch” khi n bao gồm các dòng đó.

### 12.2. Tràn số và phép toán giảm

`LongStream.sum()` trả `long`, có thể tràn khi tổng vượt miền giá trị. Demo dùng `Math.addExact` trong cả accumulator lẫn combiner để **báo lỗi** thay vì trả số âm do tràn.

Khi cần dữ liệu tiền tệ vượt phạm vi `long` hoặc phép chia trung bình theo chính sách kế toán, dùng `BigInteger`/`BigDecimal` hay mô hình số thích hợp; không mặc định dùng `double` để biểu diễn tiền chính xác.

### 12.3. Input thay đổi trong lúc đọc

Nếu tệp được ghi thêm, cắt ngắn hoặc thay thế trong khi pipeline đang duyệt, không được mặc định quá trình đọc có **snapshot nhất quán**. Cách vận hành an toàn hơn có thể là nguồn bất biến theo lô, ghi file tạm rồi chuyển tên khi hoàn tất, hoặc truy vấn có snapshot/transaction tại tầng lưu trữ. `Files.lines` là công cụ duyệt dòng, không phải cơ chế snapshot database.

## 13. Đo bộ nhớ và hiệu năng sao cho đúng

Không chỉ đo `Runtime.totalMemory() - Runtime.freeMemory()` sau khi `collect`: buffer trung gian có thể đã được GC, trong khi kết quả có thể đang giữ đối tượng nguồn lâu dài.

| Đặc tính đo | Tác dụng |
|---|---|
| **Allocated bytes** | Nhìn tổng cấp phát do mapper, parser, boxing, container |
| **Peak live heap** | Quan sát đỉnh object còn sống trong quá trình chạy |
| **Retained size** | Xác định Map/List kết quả giữ những đối tượng nào |
| **GC pause / throughput** | Đánh giá chi phí thu gom và độ trễ |
| **Elapsed time / throughput** | Đánh giá tốc độ xử lý n dòng |
| **Số file descriptor/handle** | Bắt nguồn I/O không được đóng |
| **Độ dài dòng cực đại và số khóa nhóm** | Kiểm tra các giả định về giới hạn bộ nhớ |

Các công cụ phù hợp trong hệ sinh thái Java gồm Java Flight Recorder (JFR), Java Mission Control (JMC), VisualVM, heap dump analyzers và JMH cho benchmark vi mô.

### 13.1. Kịch bản benchmark nên có

1. **Giữ cùng dữ liệu và cùng quy tắc nghiệp vụ** giữa các phương án.
2. Thử `n` tăng từ hàng nghìn đến hàng triệu, trong khi `K` được giữ cố định.
3. Thử `k` tăng mạnh để xem Map nhóm có chạm giới hạn hay không.
4. Thử dòng có độ dài khác nhau, kể cả dòng lớn bất thường.
5. So kết quả `Files.readAllLines` với `Files.lines` trên đầu vào hữu hạn đủ nhỏ để chạy an toàn.
6. So `sorted().limit(K)` với top-K heap, kiểm tra **cùng kết quả**, kể cả tie-breaker.
7. Quan sát peak memory và allocation, không chỉ bộ nhớ sau khi chương trình đã xong.
8. Đo riêng trường hợp I/O trên ổ đĩa thực, cache filesystem nóng/lạnh và tải các thread khác.

Không kết luận “Stream nhanh hơn vòng lặp” hoặc “parallel luôn tốt hơn sequential” từ một lần đo trên máy phát triển. Chọn chiến lược xử lý theo dòng và giới hạn trạng thái vì **hợp đồng bộ nhớ**, rồi tối ưu bằng số liệu thực tế.

## 14. Những lỗi thường gặp

| Cách làm hoặc nhận định | Hậu quả | Hướng xử lý |
|---|---|---|
| “Dùng Files.lines nên RAM luôn O(1).” | `collect(toList())`, `sorted` vẫn có thể giữ n phần tử | Phân tích cả pipeline và terminal |
| `filter(...).collect(toList())` trên tệp khổng lồ | List có thể chứa hàng triệu String | Đếm/tổng hợp, `limit` hoặc ghi ra tệp |
| `sorted().limit(10)` để top-10 và gọi đó là O(10) RAM | Sort có thể đệm n phần tử | Dùng min/max hoặc heap giới hạn |
| `limit(10).filter(isError)` khi cần 10 lỗi đầu | Chỉ xét 10 dòng đầu nguồn | `filter(isError).limit(10)` |
| Dùng `skip(1_000_000)` và coi là truy cập trang nhanh | Vẫn phải bỏ qua các dòng trước đó | Chỉ mục hoặc keyset/cursor pagination |
| `groupingBy(key, counting())` mà không kiểm soát số khóa | Map có thể tăng gần n | Giới hạn/kiểm soát cardinality |
| Chỉ kiểm tra độ dài dòng **sau** Files.lines | Dòng rất dài đã materialize trước kiểm tra | Reader có hard limit trước khi cấp phát dòng |
| `Files.lines(...).count()` rồi không đóng Stream | Rò rỉ tài nguyên I/O | `try-with-resources` |
| Trả Stream đã được tạo bên trong try đã kết thúc | Caller nhận Stream đã đóng | Đổi API sở hữu hoặc thu thập trong scope |
| Parallel `forEach` ghi vào writer/List mutable chung | Race hoặc mất thứ tự | Xử lý tuần tự hoặc cơ chế đồng bộ có kiểm soát |
| Chia batch 500 nhưng hàng đợi tác vụ không giới hạn | Tích lũy nhiều batch, hết RAM | Bound cả batch lẫn queue |
| `batch.clear()` sau khi gửi batch bất đồng bộ | Consumer thấy List bị thay đổi | Chuyển quyền sở hữu/bản sao |
| Chỉ giữ count nhưng nghiệp vụ cần xem chi tiết | Mất thông tin bắt buộc | Chọn mức chi tiết theo hợp đồng báo cáo |
| Dùng `sum()` cho tiền mà bỏ qua tràn số | Tổng có thể sai | `Math.addExact` hoặc kiểu số lớn |
| In log từng dòng khi benchmark throughput | I/O log chi phối thời gian | Đo riêng phần tính toán và I/O |

## 15. Bài tập thực hành có lời giải

### Bài 1. Đọc một triệu dòng, chỉ cần tổng tiền

**Đề bài:** Nên dùng `Files.readAllLines` rồi `mapToLong` hay `Files.lines` + `mapToLong` + `reduce`?

**Đáp án:** Chọn `Files.lines` trong `try-with-resources`, parse từng dòng rồi tổng hợp. Không cần List một triệu dòng nếu kết quả chỉ là một số. Với tổng có nguy cơ vượt `long`, cân nhắc `Math.addExact` hoặc kiểu số phù hợp.

### Bài 2. Hai vị trí của limit

**Đề bài:** Tệp có 500 dòng đầu không chứa `ERROR`, sau đó mới có 30 dòng lỗi. Hai pipeline `filter(isError).limit(10)` và `limit(10).filter(isError)` trả cùng kết quả không?

**Đáp án:** Không. Pipeline đầu tìm 10 lỗi đầu tiên (nếu đủ); pipeline sau chỉ xét 10 dòng đầu tệp nên trả rỗng. `limit` giới hạn số phần tử **ở vị trí nó xuất hiện** trong pipeline.

### Bài 3. Top-5 với tệp rất lớn

**Đề bài:** Có 20 triệu giao dịch nhưng chỉ cần năm giao dịch lớn nhất. Nên dùng `sorted(desc).limit(5).toList()` hay heap giới hạn?

**Đáp án:** Cân nhắc heap giữ tối đa 5 ứng viên, có bộ nhớ phụ thêm `O(5)` theo số Event giữ và thời gian xử lý khoảng `O(n log 5)`. `sorted` có thể cần buffer theo toàn bộ n. Phải xác định cách xử lý đồng hạng trước khi chọn thuật toán.

### Bài 4. Báo cáo theo khóa không giới hạn

**Đề bài:** `groupingBy(User::getId, counting())` có luôn bộ nhớ nhỏ hơn `collect(toList())` không?

**Đáp án:** Không có bảo đảm. Nếu gần như mỗi dòng có userId riêng, số nhóm `k` gần `n`, Map có thể rất lớn và mỗi entry có overhead. Nếu chỉ vài nhóm lặp lại, groupingBy(counting()) thường tiết kiệm hơn đáng kể.

### Bài 5. Batch có thật sự bounded?

**Đề bài:** Producer liên tục tạo batch 100 phần tử và đẩy vào một `BlockingQueue` không giới hạn dung lượng. Consumer xử lý rất chậm. Bộ nhớ hệ thống có được giới hạn `O(100)` không?

**Đáp án:** Không. Số batch chờ có thể tăng vô hạn. Phải giới hạn **kích thước batch và số batch có thể chờ**, hoặc dùng cơ chế backpressure tương ứng.

### Bài 6. Dòng dữ liệu dài bất thường

**Đề bài:** Vì sao `Files.lines(path).filter(line -> line.length() <= 4096)` không tạo hard cap 4096 ký tự cho bộ nhớ lúc đọc?

**Đáp án:** Vì `Files.lines` đã phải tạo `String` cho dòng trước khi `filter` đo độ dài. Một dòng rất dài có thể đã làm tăng bộ nhớ đáng kể. Hard cap cần reader/parser kiểm soát độ dài **trong khi đang đọc**, trước khi lưu cả dòng.

### Bài 7. Kết quả rỗng và số 0

**Đề bài:** Một tệp chỉ chứa header. Collector tính count và tổng tiền trả `0`; điều đó có đủ để suy ra “có giao dịch giá trị 0” không?

**Đáp án:** Không. Count = 0 nghĩa là không có bản ghi sau header, còn tổng = 0 có thể xảy ra cả khi có các giao dịch tiền bằng 0. Phải dùng cả số đếm và tổng để phân biệt.

### Bài 8. Xuất mọi dòng nhưng không giữ trong heap

**Đề bài:** Cần chuẩn hóa 10 triệu dòng thành tệp mới, không cần trả List. Cách nào phù hợp?

**Đáp án:** Đọc qua `Files.lines` hoặc `BufferedReader` và ghi từng dòng vào `BufferedWriter` được đóng trong `try-with-resources`, dùng `forEachOrdered` khi cần thứ tự. Thiết kế xử lý tệp kết quả ghi dở nếu có lỗi; không dùng `collect(toList())` chỉ để lặp ghi từng dòng.

### Bài 9. Giải thích đỉnh bộ nhớ của collect

**Đề bài:** Một chương trình trả về `List` chỉ 10 phần tử, nhưng profiler thấy đỉnh heap tăng mạnh ở giai đoạn trước terminal operation. Có thể do đâu?

**Đáp án:** Có thể có `sorted` hoặc một thao tác stateful tạo buffer theo nguồn, hoặc mapper tạo nhiều object tạm. Kích thước List kết quả cuối không bằng **đỉnh bộ nhớ khi xử lý**. Cần xem allocation, live heap và vị trí cấp phát.

### Bài 10. Gộp top-K giữa các nhánh

**Đề bài:** Khi một collector có nhiều accumulator cục bộ, có thể tạo top-K chung chỉ từ top-K của các nhánh không?

**Đáp án:** Có, nếu dùng cùng một thứ tự xếp hạng **xác định** và cùng quy tắc chọn K. Một phần tử không thuộc top-K của một nhánh đã có ít nhất K phần tử trong nhánh xếp cao hơn, nên không thể là ứng viên top-K toàn cục. Cần định nghĩa tie-breaker và không tự áp dụng nếu nghiệp vụ yêu cầu giữ tất cả đồng hạng.

## 16. Checklist trước khi xử lý tệp hoặc luồng lớn

1. **Đã xác định yêu cầu đầu ra chưa?** Chỉ count/sum, top-K, K dòng đầu hay toàn bộ dữ liệu đã chuyển đổi?
2. **Đã phân biệt số dòng cần đọc và số kết quả cần giữ chưa?** `limit` không luôn giảm chi phí duyệt.
3. **Nguồn có được mở và đóng đúng không?** `Files.lines`/`BufferedReader` cần phạm vi sở hữu tài nguyên rõ ràng.
4. **Mỗi dòng có giới hạn kích thước không?** Check sau `Files.lines` không phải hard limit trước cấp phát.
5. **Có thao tác stateful giữ dữ liệu không?** `sorted`, `distinct`, `groupingBy(toList())` hoặc `collect(toList())` có thể phá vỡ ngân sách RAM.
6. **Có thể dùng số đếm/tổng thay cho List chi tiết không?** Chỉ khi nghiệp vụ không cần giữ bản ghi.
7. **Nếu nhóm theo khóa, cardinality k có giới hạn không?** Có chính sách khi vượt giới hạn không?
8. **Nếu lấy top-K, đã có comparator và tie-breaker rõ chưa?** Có trường hợp đồng hạng vượt K không?
9. **Nếu xuất toàn bộ dữ liệu, đã ghi dần thay vì giữ List chưa?** Có chiến lược phục hồi output ghi dở không?
10. **Nếu dùng batch/async, đã giới hạn cả kích thước batch và hàng đợi chưa?**
11. **Các phép tính tiền/số lượng có phát hiện tràn không?** Có kiểm tra count = 0 khi tính trung bình không?
12. **Đã thử dữ liệu rỗng, dòng lỗi, khóa nhiều, dòng cực dài và tệp lớn chưa?** Cần kiểm tra cả ngữ nghĩa lẫn tài nguyên.
13. **Đã đo peak heap, allocation, GC và I/O chưa?** Không chỉ nhìn kích thước List kết quả.
14. **Có thực sự cần song song không?** Đo trước, không dùng shared writer hoặc mutable Map không an toàn.

**Kết luận:** Xử lý dữ liệu lớn theo dòng bằng Java Stream API là cách **không phải vật chất hóa toàn bộ đầu vào**, nhưng để bộ nhớ được kiểm soát, còn phải giới hạn **kích thước từng bản ghi**, **trạng thái tích lũy** và **kết quả giữ lại**. `Files.lines` kết hợp `try-with-resources` giải quyết vòng đời nguồn; `filter`/`limit` giúp chọn một phần kết quả; `reduce`, collector số liệu và heap top-K giúp giữ trạng thái nhỏ; còn `BufferedWriter` hỗ trợ ghi toàn bộ kết quả theo dòng mà không cần List khổng lồ. Khi kết hợp đúng ba loại giới hạn này với kiểm thử dữ liệu biên và profiling, pipeline có thể xử lý nguồn lớn mà vẫn giữ được tính đúng, hiệu năng và khả năng vận hành.
