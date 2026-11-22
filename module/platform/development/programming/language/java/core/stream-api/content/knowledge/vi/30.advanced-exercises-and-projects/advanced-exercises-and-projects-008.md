# Rà soát dự án theo hợp đồng API, khả năng bảo trì và tài nguyên

Một dự án dùng **Java Stream API** có thể tạo ra kết quả đúng trên bộ dữ liệu mẫu nhưng vẫn tồn tại lỗi nghiêm trọng: dùng lại Stream đã kết thúc, không đóng nguồn tệp, cập nhật một `ArrayList` chung khi chạy song song, xử lý sai trường hợp dữ liệu rỗng, hoặc thay đổi thứ tự phần tử ngoài ý muốn. Những lỗi này thường chỉ xuất hiện khi dữ liệu lớn, có ngoại lệ, chạy trong môi trường nhiều luồng hoặc được bảo trì bởi người khác.

Vì vậy, hoàn thành dự án Stream không chỉ là viết được pipeline `filter → map → collect`. Cần một quy trình **rà soát có bằng chứng** theo ba trục:

1. **Hợp đồng API:** mỗi phương thức có yêu cầu, bảo đảm và giới hạn nào?
2. **Khả năng bảo trì:** người đọc có hiểu đúng ý định nghiệp vụ, kiểu dữ liệu và ranh giới trách nhiệm không?
3. **Tài nguyên và vận hành:** Stream, file, bộ nhớ, CPU và tác vụ song song có được quản lý đúng cách không?

Bài thực hành nâng cao này thuộc chương **Bài tập nâng cao và dự án** của module **JAVA_STREAM_API**. Ta sẽ sử dụng một dự án báo cáo thanh toán làm ví dụ xuyên suốt, từ yêu cầu nghiệp vụ, mã cần review, bản cải tiến đến kế hoạch kiểm thử. Những vấn đề được kiểm tra liên hệ trực tiếp với pipeline lazy, `filter`, `map`, `reduce`, `collect`, grouping, collector tùy chỉnh, `Spliterator`, parallel Stream và các phép biến đổi nâng cao như Stream Gatherers.

**Mục tiêu đầu ra:** sau bài này, bạn có thể tự tổ chức một vòng code review, tìm vấn đề theo mức độ rủi ro, đề xuất bản sửa có thể kiểm chứng và thiết lập tiêu chí chấp nhận trước khi đưa một tính năng Stream vào sử dụng.

## 1. Review dự án khác gì đọc lại code?

Một vòng review không chỉ hỏi “code có chạy không?”, mà phải trả lời ít nhất bốn câu hỏi:

- **Đúng nghiệp vụ:** ví dụ số tiền báo cáo có được tính từ những giao dịch đủ điều kiện không?
- **Đúng hợp đồng Java:** code có giả định sai về encounter order, `Optional`, nguồn rỗng, tác dụng phụ hay tính kết hợp của reduction không?
- **An toàn khi dữ liệu và môi trường thay đổi:** một tệp lỗi, một nguồn rất lớn, một yêu cầu dừng sớm hoặc nhiều thread có làm hỏng kết quả không?
- **Dễ thay đổi về sau:** chính sách parse, tổng hợp, xử lý lỗi, sở hữu tài nguyên và cách hiển thị có bị trộn trong một biểu thức khó kiểm tra không?

Nên phân biệt **phát hiện** với **cảm nhận**. Một nhận xét review có giá trị nên mô tả:

~~~text
Hiện tượng / rủi ro
    ↓
Đoạn mã hoặc hợp đồng API liên quan
    ↓
Dữ liệu đầu vào tối thiểu để tái hiện
    ↓
Hướng sửa
    ↓
Kiểm thử xác nhận
~~~

Ví dụ tốt:

> Pipeline gọi `count()` rồi `collect()` trên cùng biến Stream. Stream chỉ được tiêu thụ một lần; lượt thứ hai có thể ném `IllegalStateException`. Hãy tạo nguồn mới nếu dữ liệu có thể duyệt lại, hoặc dùng một collector kết hợp trong một terminal operation. Thêm kiểm thử tính cả số lượng và tổng tiền trên nguồn đọc một lần.

Ví dụ chưa đủ:

> “Đoạn này nhìn hơi khó hiểu, có lẽ nên tối ưu.”

Review nên ưu tiên **tính đúng** và **an toàn** trước tranh luận về sở thích định dạng.

## 2. Bài toán dự án: báo cáo thanh toán từ tệp văn bản

Giả sử ứng dụng phải đọc từng dòng của một tệp văn bản UTF-8. Để tập trung vào Stream API, ta chọn định dạng minh họa đơn giản, dùng dấu `|` làm dấu phân cách:

~~~text
id|region|category|amountVnd|status
~~~

**Lưu ý:** dòng trên là **mô tả lược đồ**, không phải header thực sự trong tệp mà chương trình ở phần sau xử lý. Mỗi dòng dữ liệu phải có đúng năm trường; các giá trị trường không được chứa dấu `|`. Đây **không phải bộ phân tích CSV tổng quát** có hỗ trợ quoting và escape.

Ví dụ dữ liệu:

~~~text
TX01|North|Books|120000|PAID
TX02|South|Pens|50000|PENDING
TX03|North|Books|80000|PAID
TX04|South|Books|200000|PAID
TX05|North|Pens|35000|PAID
TX06|South|Books|25000|PENDING
~~~

Các yêu cầu nghiệp vụ:

1. Chỉ giao dịch có `status = PAID` được tính vào doanh thu.
2. `amountVnd` là số nguyên `long` không âm; dòng không hợp lệ phải gây lỗi có thông tin, không tự biến thành số 0.
3. Báo cáo gồm **số giao dịch đã thanh toán**, **tổng tiền đã thanh toán** và **tổng tiền theo khu vực**.
4. Không dựa vào thứ tự duyệt các khóa trong `Map`.
5. Phải đóng luồng đọc tệp khi hoàn thành hoặc gặp lỗi.
6. Kết quả báo cáo không cho bên gọi tự ý sửa Map tổng hợp.
7. Chưa mặc định chạy song song: cần kiểm tra tính đúng và đo hiệu năng trước.

Kết quả mong đợi:

| Chỉ số | Giá trị |
|---|---:|
| Số giao dịch `PAID` | 4 |
| Tổng doanh thu | 435.000 VND |
| Doanh thu `North` | 235.000 VND |
| Doanh thu `South` | 200.000 VND |
| Giao dịch `PENDING` được tính | 0 |

Yêu cầu này là **hợp đồng đầu ra** để đánh giá code. Nếu dữ liệu nguồn thay đổi, kiểm thử phải có khả năng chỉ ra chính xác giả định nào không còn đúng.

## 3. Bảng kiểm theo hợp đồng Java Stream API

Trước khi sửa code, hãy dùng một bảng kiểm ngắn để tìm các rủi ro có khả năng ảnh hưởng đến tính đúng.

| Chủ đề | Điều phải xác minh | Lỗi thường gặp |
|---|---|---|
| Vòng đời Stream | Một Stream chỉ được dùng cho một pipeline terminal; nguồn I/O được đóng | Gọi `count()` và `collect()` trên cùng Stream |
| Lazy evaluation | Các callback trung gian chỉ chạy khi pipeline thực sự yêu cầu | Dựa vào `peek` để ghi dữ liệu bắt buộc |
| Non-interference | Callback không làm thay đổi cấu trúc nguồn đang duyệt | `filter` hoặc `map` đồng thời xóa phần tử khỏi List |
| Stateless behavior | Callback không phụ thuộc vào biến dùng chung thay đổi giữa các phần tử | Dùng biến đếm ngoài để gán mã khi `parallel()` |
| Thứ tự | Chỉ yêu cầu encounter order khi nghiệp vụ cần | Nghĩ `findAny` luôn trả phần tử đầu hoặc `toSet` có thứ tự |
| Dữ liệu rỗng | `Optional`, identity và collector có quy tắc rõ | Gọi `get()` trên Optional rỗng |
| Equality | `distinct` dựa vào `equals`/`hashCode`; `TreeSet` dựa vào comparator | Mất bản ghi khi comparator chỉ so sánh giá |
| Reduction | Identity, associativity, compatibility của phép gộp | Dùng phép trừ hoặc bộ chứa mutable trong `reduce` |
| Collector | Supplier tạo bộ chứa đúng; combiner không làm mất dữ liệu | Dùng một `ArrayList` chia sẻ trong parallel |
| Tài nguyên | Stream lấy từ `Files.lines` được đóng bằng `try-with-resources` | Terminal operation chạy xong nhưng file còn mở |
| Kiểu số | Kiểm soát tràn số và độ chính xác | Cộng `long` vượt miền biểu diễn |
| Song song | Nguồn chia được; pipeline và collector đúng hợp đồng | Bật `parallel()` vì nghĩ luôn nhanh hơn |

Bảng kiểm chỉ phát huy tác dụng khi từng mục có **bằng chứng kiểm thử, lập luận từ API hoặc ví dụ tái hiện**, không phải chỉ có dấu tích.

## 4. Trục thứ nhất: vòng đời Stream và quyền sở hữu nguồn

`Stream` là một mô tả pipeline tiêu thụ **một lần**. Terminal operation như `sum()`, `count()`, `findFirst()`, `reduce()` hoặc `collect()` kết thúc pipeline. Không được chạy tiếp terminal operation khác trên cùng đối tượng Stream.

~~~java
java.util.stream.Stream<String> names =
    java.util.stream.Stream.of("An", "Bình", "Chi");

long count = names.count(); // 3

// Không hợp lệ: Stream đã được tiêu thụ.
// java.util.List<String> list = names.toList();
~~~

**Cách sửa phụ thuộc nguồn:**

- Với `List` có thể duyệt lại, tạo hai Stream độc lập nếu mục tiêu và chi phí cho phép.
- Nếu muốn nhiều chỉ số trong một lần duyệt, dùng `Collectors.teeing` (Java 12+) hoặc collector thích hợp.
- Với nguồn đọc từ file, không dùng lại cùng một Stream sau khi đã terminal; cần xem xét ai chịu trách nhiệm đóng.

### 4.1. Terminal operation không tự đóng Stream I/O

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("payments.txt");

try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
    System.out.println(count);
}
~~~

`try-with-resources` bảo đảm gọi `close()` khi rời khối `try`, kể cả trường hợp xảy ra ngoại lệ. `count()` chỉ thực hiện terminal operation; nó **không phải cam kết đóng file**.

Ở một phương thức **trả Stream cho người gọi**, phải làm rõ **quyền sở hữu việc đóng**. Nếu tạo nguồn I/O bên trong một phương thức rồi trả Stream đã đóng, người gọi không thể xử lý tiếp. Nếu trả Stream chưa đóng, người gọi cần biết phải đóng nó:

~~~java
static Stream<String> openLines(Path path)
        throws java.io.IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

// Người gọi sở hữu trách nhiệm đóng:
try (Stream<String> lines = openLines(path)) {
    // Xử lý trong phạm vi này.
}
~~~

Một thiết kế thay thế là **không trả Stream** mà cung cấp một hàm nghiệp vụ nhận `Path` và tự thực hiện toàn bộ xử lý trong `try-with-resources`. Cách này thường giúp giới hạn phạm vi mở tệp và tránh rò rỉ tài nguyên.

### 4.2. onClose không thay thế close

`onClose(Runnable)` chỉ **đăng ký handler**. Handler chạy khi Stream được đóng, **không** khi terminal operation hoàn tất.

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)
        .onClose(() -> System.out.println("Đã đóng nguồn"))) {
    System.out.println(lines.findFirst().orElse("Rỗng"));
}
~~~

Không cần thêm `onClose` chỉ để gọi `close` lần nữa trên chính Stream; nó hữu ích khi cần công việc dọn dẹp bổ sung. Nếu nhiều close handler ném ngoại lệ, các ngoại lệ còn lại có thể được lưu dưới dạng *suppressed exceptions*; khi chẩn đoán, xem cả `Throwable.getSuppressed()`.

## 5. Trục thứ nhất: tính lazy và tác dụng phụ

Các thao tác trung gian như `filter` và `map` thường *lazy*. Chúng tạo kế hoạch tính toán, không tự duyệt dữ liệu ngay khi được khai báo.

~~~java
java.util.stream.Stream<Integer> pipeline =
    java.util.stream.Stream.of(1, 2, 3)
        .filter(n -> n > 1)
        .map(n -> n * 10);

// Chưa có phép terminal nào.
// Lúc gọi toList() mới yêu cầu kết quả.
java.util.List<Integer> result = pipeline.toList();
System.out.println(result); // [20, 30]
~~~

Vì Java có thể tối ưu đường thực thi dựa trên nguồn và terminal operation, **không được xem số lần gọi callback trung gian là một sự kiện nghiệp vụ bắt buộc**.

### 5.1. Lỗi: đưa hành động bắt buộc vào peek

~~~java
// Không đặt logic cập nhật trạng thái bắt buộc vào peek.
long count = java.util.stream.IntStream.range(0, 100)
    .peek(n -> auditLog(n))
    .count();
~~~

Đoạn này giả định có hàm `auditLog(int)`. Với nguồn `SIZED` và pipeline phù hợp, `count()` có thể dùng kích thước nguồn mà không cần duyệt từng phần tử, nên `auditLog` không được bảo đảm chạy 100 lần.

**Cách sửa:** tách việc ghi log nghiệp vụ thành một bước có hợp đồng rõ ràng, không phụ thuộc vào `peek`. Nếu việc cập nhật dữ liệu là phần cốt lõi, cần thiết kế xử lý giao dịch, lỗi, retry và thứ tự phù hợp thay vì giấu nó trong một pipeline thuần tính toán.

### 5.2. Non-interference và stateless

Ví dụ rủi ro:

~~~java
java.util.List<Integer> source =
    new java.util.ArrayList<>(java.util.List.of(1, 2, 3, 4));

// Sai: thay đổi cấu trúc nguồn trong lúc Stream đang duyệt.
// source.stream()
//     .filter(n -> {
//         if (n == 2) source.remove(Integer.valueOf(3));
//         return n % 2 == 0;
//     })
//     .toList();
~~~

Việc thay đổi nguồn ngay trong callback có thể gây `ConcurrentModificationException` hoặc kết quả không xác định theo ý định. Với parallel Stream, biến ngoài mutable còn tạo nguy cơ race condition.

Nên viết callback dựa trên **đối số** và không sửa nguồn:

~~~java
java.util.List<Integer> even = source.stream()
    .filter(n -> n % 2 == 0)
    .toList();

System.out.println(even); // [2, 4]
~~~

## 6. Trục thứ nhất: thứ tự và tiêu chí chọn phần tử

Nguồn như `List` thường có **encounter order**. Một số terminal operation bảo đảm tôn trọng thứ tự đó khi có, số khác thì không.

| Phép toán | Điều cần nhớ |
|---|---|
| `findFirst()` | Trả phần tử đầu theo encounter order nếu Stream có thứ tự |
| `findAny()` | Trả một phần tử bất kỳ; không dựa vào nó để chọn đại diện đầu |
| `forEach()` trên parallel Stream | Không bảo đảm thứ tự thực thi action |
| `forEachOrdered()` | Giữ encounter order nhưng có thể tăng chi phí phối hợp |
| `sorted()` | Sắp xếp theo comparator, giữ phần tử trùng |
| `distinct()` | Loại trùng theo `equals`/`hashCode`; với Stream ordered giữ đại diện đầu |
| `Collectors.toSet()` | Không bảo đảm kiểu Set hoặc thứ tự duyệt kết quả |
| `Collectors.groupingBy(...)` | Không bảo đảm thứ tự khóa Map mặc định |

Ví dụ:

~~~java
java.util.List<Integer> values = java.util.List.of(9, 3, 9, 5);

System.out.println(values.stream().findFirst().orElse(-1)); // 9
System.out.println(values.stream().min(Integer::compareTo).orElse(-1)); // 3
System.out.println(values.stream().distinct().toList()); // [9, 3, 5]
~~~

**Review phải xác định ý định nghiệp vụ trước:** “đầu tiên” khác với “nhỏ nhất”, “đại diện bất kỳ” khác với “ưu tiên bản ghi được nhập sớm nhất”. Nếu muốn kết quả ổn định khi nhiều giá trị bằng nhau, cần **tie-breaker** rõ ràng.

### 6.1. Đừng suy luận từ một lần in Map

~~~java
java.util.Map<String, Long> amountByRegion = sales.stream()
    .collect(java.util.stream.Collectors.groupingBy(
        Sale::region,
        java.util.stream.Collectors.summingLong(Sale::amountVnd)
    ));
~~~

Đoạn này là biểu thức minh họa cho kiểu `Sale` và `sales` giả định đã khai báo. `groupingBy` không cam kết thứ tự các khóa trong Map trả về. Nếu báo cáo phải hiển thị thứ tự tăng dần, có thể chỉ định `TreeMap::new` bằng overload `groupingBy(classifier, mapFactory, downstream)` hoặc sắp xếp khi hiển thị.

## 7. Trục thứ nhất: kiểu dữ liệu, null và hợp đồng equality

Một collector hoặc terminal operation không thể tự đoán ý nghĩa “bản ghi hợp lệ” hay “bản ghi trùng” của dự án.

### 7.1. Phân biệt phần tử trùng với trùng khóa nghiệp vụ

`Stream.distinct()` dùng `equals`/`hashCode` của phần tử. Nếu kiểu dữ liệu là record:

~~~java
record Payment(String id, String region, long amountVnd) {}

java.util.List<Payment> rows = java.util.List.of(
    new Payment("TX01", "North", 100L),
    new Payment("TX01", "North", 200L)
);
~~~

Hai record trên **khác nhau theo `equals`** vì `amountVnd` khác nhau, dù cùng ID `TX01`. Do đó `rows.stream().distinct()` **không** tự thực thi chính sách “mỗi ID chỉ có một giao dịch”.

Nếu nghiệp vụ yêu cầu ID duy nhất, phải quyết định:

- **Từ chối** dữ liệu có ID trùng?
- **Giữ bản ghi đầu tiên**?
- **Giữ bản ghi mới nhất** theo thời gian?
- **Gộp** các dòng theo quy tắc được xác nhận?

Mỗi lựa chọn cần thuật toán và kiểm thử riêng. Việc gọi `distinct()` không thay thế quyết định nghiệp vụ.

### 7.2. Comparator không nhất thiết tương đương equals

Khi thu vào `TreeSet`, hai phần tử có `compare(a, b) == 0` được xem là trùng theo thứ tự của tập. Nếu comparator chỉ xét số tiền, hai giao dịch khác ID nhưng bằng tiền có thể bị mất một bản ghi.

Với báo cáo cần giữ toàn bộ giao dịch, `sorted(comparator).toList()` phù hợp hơn nếu mục tiêu chỉ là sắp xếp. Nếu cần khóa duy nhất, hãy định nghĩa comparator hoặc cấu trúc Map theo đúng chính sách khóa.

### 7.3. Xử lý null tại ranh giới đầu vào

- `Optional.of(null)` ném `NullPointerException`, còn `Optional.ofNullable(null)` trả Optional rỗng.
- `findFirst` hoặc `findAny` không thể trả Optional chứa null; phần tử null được chọn có thể gây lỗi.
- `Collectors.groupingBy` trong Java chuẩn không chấp nhận kết quả classifier là null.
- `Collectors.toUnmodifiableList()` và `List.copyOf(...)` không chấp nhận phần tử null.

Với pipeline đọc dữ liệu ngoài, hãy **kiểm tra và chuẩn hóa** sớm, thay vì để null đi sâu đến collector rồi chẩn đoán lỗi muộn.

## 8. Trục thứ nhất: reduce và collect cần hợp đồng đúng

Một phép `reduce` phải có identity phù hợp và phép kết hợp **associative**, đặc biệt nếu chạy song song.

~~~java
long sum = java.util.stream.LongStream.of(10L, 20L, 30L)
    .reduce(0L, Long::sum);

System.out.println(sum); // 60
~~~

`0L` là identity của phép cộng. Phép trừ không có tính kết hợp, nên không nên dùng `reduce(0, (a, b) -> a - b)` rồi kỳ vọng kết quả giống nhau khi thực thi song song.

### 8.1. Sai lầm: sửa bộ chứa trong reduce

~~~java
java.util.List<String> names = java.util.List.of("An", "Bình");

// Sai về hợp đồng rút gọn giá trị, đặc biệt khi parallel.
// java.util.List<String> result = names.parallelStream().reduce(
//     new java.util.ArrayList<String>(),
//     (list, name) -> { list.add(name); return list; },
//     (left, right) -> { left.addAll(right); return left; }
// );
~~~

`reduce` không được dùng kiểu này để sửa một identity mutable, có khả năng bị chia sẻ hoặc tái sử dụng giữa các nhánh. Khi cần thu phần tử vào danh sách, dùng `collect`:

~~~java
java.util.List<String> result = names.parallelStream()
    .collect(java.util.stream.Collectors.toList());
~~~

Bộ chứa và combiner do collector tổ chức theo hợp đồng. Điều này khác với tự cập nhật một `ArrayList` dùng chung thông qua `parallelStream().forEach(shared::add)`, vốn không an toàn.

### 8.2. Collector tùy chỉnh phải có supplier, accumulator, combiner phù hợp

Khi review một `Collector.of(...)`, cần đặt câu hỏi:

1. Supplier có tạo một container mới cho mỗi lần được gọi không?
2. Accumulator có cập nhật **đúng container được cung cấp** và không sửa trạng thái ngoài không?
3. Combiner có hợp nhất toàn bộ dữ liệu hai container mà không bỏ sót hoặc đếm trùng không?
4. Finisher có trả đúng kiểu kết quả và không làm rò rỉ container mutable nếu yêu cầu bất biến không?
5. Các đặc tính `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` có thật sự đúng không?

**Không khai báo `CONCURRENT` chỉ vì dùng `parallel()`.** Một collector thông thường vẫn có thể chạy song song bằng nhiều container độc lập và combiner. Nếu cho phép nhiều thread cập nhật **cùng container**, accumulator và cấu trúc dữ liệu phải thực sự hỗ trợ concurrency.

### 8.3. Chú ý số học trong báo cáo

`Collectors.summingLong(...)` và `LongSummaryStatistics` sử dụng số học `long` thông thường, có thể **tràn số**. Việc chuyển từ `int` sang `long` không có nghĩa tổng vô hạn độ chính xác.

Nếu chính sách yêu cầu **báo lỗi khi tràn**:

~~~java
java.util.stream.Collector<Payment, ?, Long> exactTotal =
    java.util.stream.Collectors.reducing(
        0L,
        Payment::amountVnd,
        Math::addExact
    );
~~~

Đoạn này dùng kiểu `Payment` có phương thức `amountVnd()` phù hợp. `Math.addExact` ném `ArithmeticException` nếu phép cộng tràn; kết quả có thể bị dừng thay vì trả một số tiền sai.

Nếu tổng thực tế có thể vượt `long` theo thiết kế, cần biểu diễn như `BigInteger` hoặc `BigDecimal` và chính sách số học được xác định rõ.

## 9. Trục thứ hai: chia trách nhiệm để code dễ bảo trì

Một biểu thức Stream dài không tự động là “code đẹp”. Nếu trộn **parse đầu vào**, **quy tắc nghiệp vụ**, **tổng hợp**, **định dạng hiển thị** và **logging** trong một chuỗi lambda, người bảo trì rất khó biết thay đổi nào ảnh hưởng kết quả.

Thiết kế dễ review thường tách ba lớp:

~~~mermaid
flowchart LR
    A["Nguồn: Files.lines / List"] --> B["parseLine: text → Payment"]
    B --> C["Chọn dữ liệu hợp lệ và PAID"]
    C --> D["summarize: collect → Report"]
    D --> E["Hiển thị / API response"]
~~~

Trong dự án nhỏ, không nhất thiết cần nhiều tầng class hoặc framework. Mục đích là tách các **chính sách có thể thay đổi độc lập** thành các hàm có tên rõ nghĩa.

### 9.1. Chọn tên thể hiện nghiệp vụ

So sánh:

~~~java
// Khó đọc khi xem riêng trong review:
.filter(x -> x.paid())
.map(x -> x.amountVnd())

// Rõ ý định hơn:
.filter(Payment::paid)
.mapToLong(Payment::amountVnd)
~~~

Tên `paid` và `amountVnd` giúp reviewer nhận ra điều kiện và đơn vị đo. Với logic nhiều nhánh, nên tạo phương thức như `parseLine`, `isBillable` hoặc `summarizePayments` thay vì nhồi tất cả vào một lambda.

### 9.2. Tách tính toán khỏi I/O

Một phương thức nhận `Stream<String>` có thể chỉ lo **biến dữ liệu thành báo cáo**, còn caller sở hữu Stream và tài nguyên:

~~~java
static Report summarize(Stream<String> lines) {
    // Phân tích và tổng hợp; không tự đóng nguồn của caller.
}
~~~

Điều này giúp kiểm thử bằng `List.of(...).stream()` mà không cần tạo file thật. Phương thức `main` hoặc service ở lớp ngoài sử dụng `try-with-resources` khi mở `Files.lines`.

**Hợp đồng sở hữu phải rõ:** ai tạo Stream I/O thì người đó phải bảo đảm đóng, hoặc chuyển giao trách nhiệm đóng cho caller được tài liệu hóa. Không để một Stream “trôi” qua nhiều tầng mà không có người chịu trách nhiệm.

## 10. Trục thứ hai: chọn API theo nhu cầu, không theo độ ngắn

| Nhu cầu | Cách diễn đạt đáng cân nhắc | Điều reviewer kiểm tra |
|---|---|---|
| Tổng một trường nguyên thủy | `mapToLong(...).sum()` | Tràn số và đơn vị đo |
| Tìm phần tử đầu | `findFirst()` | Encounter order có tồn tại không? |
| Tìm phần tử bất kỳ | `findAny()` | Có thật không cần ưu tiên thứ tự? |
| Min/max | `min(comparator)`, `max(comparator)` | Tie-breaker, Optional rỗng |
| Tạo danh sách | `collect(toList())` hoặc `toList()` | Có yêu cầu sửa kết quả không? Phiên bản Java? |
| Tổng hợp số lượng, tổng, min, max | `summarizingLong(...)` | Có đủ chính sách nguồn rỗng/tràn số không? |
| Nhóm theo khóa | `groupingBy(...)` | Null key, thứ tự Map, cardinality nhóm |
| Nhóm theo nhiều khóa | `groupingBy(..., groupingBy(...))` | Độ sâu Map có gây khó bảo trì không? |
| Kết hợp hai kết quả | `teeing(...)` (Java 12+) | Merger nhận kết quả cuối, không phải từng phần tử |
| Tập sắp xếp duy nhất | `toCollection(TreeSet::new)` | Comparator có làm mất bản ghi không? |
| Thu dữ liệu không đột biến | `Collectors.toUnmodifiableList()` hoặc `Stream.toList()` | Khác biệt về null và API |
| Nguồn tùy chỉnh | `Spliterator` và `StreamSupport` | Phân chia, thứ tự, kích thước và vòng đời |

Viết ít dòng không bảo đảm dễ sửa hơn. Ví dụ `groupingBy` lồng bốn cấp có thể ngắn hơn một lớp báo cáo có tên rõ ràng, nhưng chi phí hiểu và truy xuất null có thể cao hơn. Hãy đo **độ rõ nghĩa và khả năng kiểm thử** bên cạnh độ dài code.

### 10.1. Phân biệt mutability và identity

- `Stream.toList()` (Java 16+) trả danh sách không thể sửa.
- `Collectors.toList()` **không cam kết** lớp triển khai, mutability hoặc thread-safety của danh sách trả về.
- `Collectors.toCollection(ArrayList::new)` tạo loại collection được yêu cầu, có thể sửa.
- `List.copyOf(...)` tạo danh sách không thể sửa nhưng từ chối phần tử null.

Nếu kết quả phải bất biến, nói rõ điều đó trong API hoặc kiểu trả về; đừng giả định record chứa một `List` thì bản thân List cũng không thể sửa.

## 11. Trục thứ ba: tài nguyên, lỗi và giới hạn dữ liệu

### 11.1. Bộ nhớ và loại terminal operation

Một Stream có thể đọc từng phần tử lazily, nhưng terminal operation vẫn có thể **thu toàn bộ dữ liệu vào bộ nhớ**.

~~~java
// Có thể giữ toàn bộ dữ liệu của tệp trong bộ nhớ.
java.util.List<String> allLines;
try (java.util.stream.Stream<String> lines =
         java.nio.file.Files.lines(path)) {
    allLines = lines.toList();
}
~~~

Nếu chỉ cần số lượng hoặc tổng theo một số nhóm ít khóa, `counting`/`summingLong`/`groupingBy` với downstream thống kê có thể tránh lưu mọi dòng vào List. Tuy vậy, `groupingBy` vẫn giữ trạng thái cho mỗi khóa; nếu số khóa gần bằng số bản ghi, kết quả Map cũng có thể rất lớn.

### 11.2. Nguồn không giới hạn và short-circuit

`Stream.generate(...)` hoặc `Stream.iterate(...)` có thể tạo nguồn vô hạn. `collect(toList())` hay `sorted()` trên nguồn không giới hạn không thể tự hoàn thành nếu không có điều kiện dừng phù hợp.

~~~java
java.util.List<Integer> firstFive = java.util.stream.Stream
    .iterate(1, n -> n + 1)
    .limit(5)
    .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
~~~

Thứ tự các bước quan trọng: `sorted().limit(5)` có thể cần sắp xếp toàn bộ nguồn trước khi trả kết quả, không thích hợp với nguồn vô hạn.

### 11.3. Hạn chế I/O blocking và lỗi giữa pipeline

Khi dùng `Files.lines`, lỗi mở file có thể là `IOException`; lỗi đọc trong lúc duyệt có thể xuất hiện dưới dạng `UncheckedIOException`. Không nên bắt `RuntimeException` rộng rồi biến mọi lỗi thành báo cáo rỗng. Làm vậy khiến dữ liệu mất nhưng dashboard vẫn trông bình thường.

Trong một báo cáo tài chính, **fail fast có ngữ cảnh** thường tốt hơn âm thầm bỏ qua những dòng không hợp lệ, trừ khi yêu cầu sản phẩm đã xác định rõ cơ chế báo cáo cả dữ liệu hợp lệ và dữ liệu bị loại.

### 11.4. Độ lớn dữ liệu và giới hạn vận hành

Review cần xét:

- Một tệp cực lớn có làm đầy heap không?
- Parser có thể tạo quá nhiều chuỗi hoặc đối tượng tạm không?
- Số khóa nhóm có thể tăng không giới hạn không?
- Có cần giới hạn kích thước tệp, số dòng hoặc số lỗi đầu vào không?
- Lỗi giữa pipeline có đóng tài nguyên và để lại hệ thống ở trạng thái rõ ràng không?
- Có ghi ra log toàn bộ dữ liệu người dùng hoặc thông tin nhạy cảm không?

Không có một đáp án chung: giới hạn tài nguyên phải phù hợp môi trường chạy và yêu cầu sản phẩm.

## 12. Chương trình tham chiếu: đọc, xác thực và tổng hợp trong một pipeline

Đây là bản triển khai nhỏ nhưng **tự chứa**, ưu tiên đúng hợp đồng và khả năng bảo trì. Ví dụ dùng **Java 17+** vì có `record`, `switch` expression và `List.of`; `Collectors.teeing` có từ Java 12.

Đặt mã trong file `ProjectStreamReviewDemo.java`. Không truyền đối số để chạy bộ dữ liệu mẫu; truyền một đường dẫn tệp khi muốn đọc dữ liệu UTF-8 thực tế.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ProjectStreamReviewDemo {

    record Payment(
        String id,
        String region,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    record Report(
        long paidCount,
        long paidTotalVnd,
        Map<String, Long> paidRevenueByRegion
    ) {}

    private static List<String> sampleRows() {
        return List.of(
            "TX01|North|Books|120000|PAID",
            "TX02|South|Pens|50000|PENDING",
            "TX03|North|Books|80000|PAID",
            "TX04|South|Books|200000|PAID",
            "TX05|North|Pens|35000|PAID",
            "TX06|South|Books|25000|PENDING"
        );
    }

    static Payment parseLine(String line) {
        if (line == null) {
            throw new IllegalArgumentException("Dòng dữ liệu là null");
        }

        String[] fields = line.split("\\|", -1);
        if (fields.length != 5) {
            throw new IllegalArgumentException(
                "Cần đúng 5 trường: " + line
            );
        }

        String id = fields[0].trim();
        String region = fields[1].trim();
        String category = fields[2].trim();
        String amountText = fields[3].trim();
        String status = fields[4].trim();

        if (id.isEmpty() || region.isEmpty() || category.isEmpty()) {
            throw new IllegalArgumentException(
                "Thiếu id, region hoặc category: " + line
            );
        }

        long amount;
        try {
            amount = Long.parseLong(amountText);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "Số tiền không hợp lệ trong dòng: " + line, ex
            );
        }

        if (amount < 0L) {
            throw new IllegalArgumentException(
                "Số tiền không được âm: " + line
            );
        }

        boolean paid = switch (status) {
            case "PAID" -> true;
            case "PENDING" -> false;
            default -> throw new IllegalArgumentException(
                "Trạng thái không hợp lệ: " + status
            );
        };

        return new Payment(id, region, category, amount, paid);
    }

    // Không tự đóng Stream: caller chịu trách nhiệm quản lý nguồn.
    static Report summarize(Stream<String> lines) {
        return lines
            .map(ProjectStreamReviewDemo::parseLine)
            .filter(Payment::paid)
            .collect(Collectors.teeing(
                Collectors.summarizingLong(Payment::amountVnd),
                Collectors.groupingBy(
                    Payment::region,
                    Collectors.summingLong(Payment::amountVnd)
                ),
                (stats, byRegion) -> new Report(
                    stats.getCount(),
                    stats.getSum(),
                    Map.copyOf(byRegion)
                )
            ));
    }

    public static void main(String[] args) throws IOException {
        if (args.length > 1) {
            throw new IllegalArgumentException(
                "Dùng: java ProjectStreamReviewDemo [file]"
            );
        }

        Stream<String> source = args.length == 0
            ? sampleRows().stream()
            : Files.lines(Path.of(args[0]), StandardCharsets.UTF_8);

        Report report;

        // Với Files.lines, đây là nơi đóng nguồn kể cả khi parse lỗi.
        try (Stream<String> lines = source) {
            report = summarize(lines);
        }

        System.out.println("paidCount=" + report.paidCount());
        System.out.println("paidTotalVnd=" + report.paidTotalVnd());
        System.out.println(
            "North=" + report.paidRevenueByRegion().get("North")
        );
        System.out.println(
            "South=" + report.paidRevenueByRegion().get("South")
        );
    }
}
~~~

Kết quả khi chạy không có đối số:

~~~text
paidCount=4
paidTotalVnd=435000
North=235000
South=200000
~~~

### 12.1. Vì sao thiết kế này dễ review hơn?

**Một nguồn, một terminal operation.** Phương thức `summarize` nhận Stream và dùng `teeing` để tạo đồng thời thống kê toàn bộ và doanh thu theo khu vực. Không gọi hai terminal operation trên cùng đối tượng Stream.

**Parser độc lập.** `parseLine` thực hiện kiểm tra cú pháp và giá trị đầu vào. Có thể viết unit test trực tiếp cho những trường hợp sai mà không cần đọc file.

**Chính sách nghiệp vụ rõ ràng.** `filter(Payment::paid)` thể hiện quy tắc chỉ ghi nhận khoản đã thanh toán.

**Báo cáo không cho sửa Map.** `Map.copyOf(byRegion)` tạo Map không thể sửa; các khóa `String` và giá trị `Long` đều không phải container mutable. Nó không hứa thứ tự khóa, và đoạn code không dựa vào thứ tự đó.

**Sở hữu file ở tầng ngoài.** Phương thức `main` dùng `try-with-resources`; `summarize` không tự ý đóng Stream của caller. Lúc parse hoặc collect thất bại, khối `try` vẫn đóng nguồn.

**Không chia sẻ mutable state.** `teeing` và `groupingBy` quản lý các bộ chứa theo hợp đồng collector; không có `ArrayList`/`HashMap` được các lambda ghi trực tiếp từ bên ngoài.

### 12.2. Giới hạn đã được nhận diện, chưa được che giấu

Bản ví dụ **không tự nhận là một hệ thống tài chính hoàn chỉnh**:

- Định dạng dấu `|` không hỗ trợ escape hoặc trường chứa dấu phân cách. Nếu định dạng thực là CSV, phải dùng parser phù hợp.
- Không có kiểm tra **ID giao dịch trùng**. Nếu ID là duy nhất theo nghiệp vụ, cần quy tắc phát hiện và xử lý riêng.
- `summingLong` và `LongSummaryStatistics` có thể **tràn `long`** khi tổng cực lớn.
- Các tên khu vực mới đều trở thành khóa, nên một nguồn có cardinality rất lớn có thể khiến Map tiêu thụ nhiều bộ nhớ.
- Lỗi parse hiện chứa toàn dòng dữ liệu trong thông báo; với dữ liệu cá nhân/nhạy cảm, phải thay bằng thông tin chẩn đoán được phép ghi log.
- Ví dụ cố ý **không bật parallel** vì nguồn I/O và tính đúng đắn chưa được benchmark/đánh giá cho song song.

Nhận diện ranh giới là một phần quan trọng của review: tránh đưa những giả định chưa được chứng minh thành cam kết của API.

## 13. Kiểm thử: từ ví dụ “đúng” đến kiểm tra hợp đồng

Kiểm thử nên bao gồm **kết quả mẫu, nguồn rỗng, đầu vào không hợp lệ, dữ liệu biên và vòng đời tài nguyên**.

### 13.1. Bộ kiểm thử tối thiểu không cần thư viện ngoài

Có thể đặt phương thức sau **bên trong** lớp `ProjectStreamReviewDemo` rồi gọi từ `main` khi muốn tự kiểm tra. Đây là cách kiểm thử minh họa bằng Java thuần, không thay thế hoàn toàn JUnit hay hệ thống CI.

~~~java
static void verifyContract() {
    Report expected = summarize(Stream.of(
        "TX01|North|Books|120000|PAID",
        "TX02|South|Pens|50000|PENDING",
        "TX03|North|Books|80000|PAID"
    ));

    if (expected.paidCount() != 2L
            || expected.paidTotalVnd() != 200_000L
            || !Long.valueOf(200_000L).equals(
                expected.paidRevenueByRegion().get("North")
            )) {
        throw new AssertionError("Kết quả tổng hợp sai");
    }

    Report empty = summarize(Stream.empty());
    if (empty.paidCount() != 0L
            || empty.paidTotalVnd() != 0L
            || !empty.paidRevenueByRegion().isEmpty()) {
        throw new AssertionError("Xử lý nguồn rỗng sai");
    }

    boolean rejectedNegative = false;
    try {
        parseLine("TX09|North|Books|-1|PAID");
    } catch (IllegalArgumentException ex) {
        rejectedNegative = true;
    }

    if (!rejectedNegative) {
        throw new AssertionError("Chưa từ chối số tiền âm");
    }

    boolean immutableMap = false;
    try {
        empty.paidRevenueByRegion().put("Other", 1L);
    } catch (UnsupportedOperationException ex) {
        immutableMap = true;
    }

    if (!immutableMap) {
        throw new AssertionError("Map kết quả phải không thể sửa");
    }
}
~~~

**Không dùng duy nhất `assert`** nếu không kiểm soát cấu hình chạy: các câu lệnh `assert` của Java bị tắt theo mặc định trừ khi bật `-ea`. Việc ném `AssertionError` trực tiếp trong ví dụ bảo đảm kiểm tra được thực thi.

### 13.2. Ma trận trường hợp kiểm thử

| Trường hợp | Dữ liệu | Kết quả mong đợi |
|---|---|---|
| Luồng rỗng | Không có dòng | Count 0, total 0, Map rỗng |
| Một giao dịch PAID | Một dòng hợp lệ | Count 1, doanh thu bằng số tiền |
| Toàn PENDING | Nhiều dòng hợp lệ chưa thanh toán | Count 0, total 0, Map rỗng |
| Số âm | `-1` | Từ chối với ngoại lệ có ngữ cảnh |
| Số không phải số | `abc` | Từ chối, giữ nguyên nguyên nhân parse |
| Thiếu trường | Chỉ có 4 trường | Từ chối |
| Thừa trường | Có 6 trường | Từ chối |
| Trạng thái không biết | `DONE` | Từ chối |
| Khóa vùng rỗng | `region = ""` | Từ chối |
| Hai khu vực | North và South | Hai khóa trong Map, tổng từng khóa đúng |
| Nhiều giao dịch cùng ID | Hai dòng ID giống nhau | **Chưa định nghĩa** trong ví dụ; cần chính sách nghiệp vụ |
| Tổng vượt `long` | Các số lớn hợp lệ | Xác định yêu cầu: báo lỗi hay kiểu số khác |
| Lỗi I/O giữa chừng | Nguồn đọc tệp lỗi | Báo lỗi và đóng tài nguyên |
| Có nhiều thread | Chạy parallel nếu được cho phép | Kết quả tương đương và không race |

Một reviewer không nên đánh dấu **PASS** cho hai trường hợp “chưa định nghĩa” và “cần chính sách” khi chưa có quyết định nghiệp vụ. Đó là **open question**, không phải lỗi được tự ý giải quyết bằng phỏng đoán.

## 14. Bài tập review code có lỗi

Đọc đoạn code sau và tìm càng nhiều vấn đề càng tốt. Đây là **mã cố ý sai**, không phải khuyến nghị sử dụng:

~~~java
// Ví dụ để code review; không sử dụng trong ứng dụng.
static List<String> broken(Path path) throws IOException {
    Stream<String> lines = Files.lines(path);

    long count = lines.count();

    List<String> result = new ArrayList<>();
    lines.parallel()
        .filter(line -> !line.isEmpty())
        .forEach(result::add);

    System.out.println("rows=" + count);
    return result;
}
~~~

Đoạn ví dụ giả định import `Path`, `Files`, `IOException`, `Stream`, `List` và `ArrayList`.

### 14.1. Các phát hiện cần có

| Vấn đề | Mức ảnh hưởng | Giải thích |
|---|---|---|
| Dùng lại `lines` sau `count()` | Nghiêm trọng | Stream đã terminal; pipeline thứ hai không hợp lệ |
| Không có `try-with-resources` | Nghiêm trọng | Có thể rò rỉ tài nguyên file |
| `parallel().forEach(result::add)` | Nghiêm trọng | `ArrayList` dùng chung không thread-safe |
| `Files.lines(path)` không chỉ rõ charset | Tùy chuẩn dữ liệu | Nên làm rõ charset theo hợp đồng tệp |
| Kiểm tra `!line.isEmpty()` | Cần xem lại | Chuỗi toàn khoảng trắng vẫn được coi là không rỗng |
| In thông tin trực tiếp trong hàm xử lý | Về bảo trì | Trộn logging/hiển thị vào xử lý |
| Trả kết quả mutable không được nêu rõ | Về API | Caller có thể sửa danh sách nếu không có quy định |
| Chạy parallel khi nguồn là I/O | Về hiệu năng | Chưa có bằng chứng nguồn chia tốt hoặc hữu ích |

### 14.2. Một bản sửa tuần tự, đơn giản và có quyền sở hữu rõ

~~~java
static List<String> readNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .filter(line -> !line.trim().isEmpty())
            .toList();
    }
}
~~~

Đoạn này dùng `Stream.toList()` từ Java 16+. Nó trả danh sách **không thể sửa**, giải phóng nguồn tệp bằng `try-with-resources` và không dùng chung trạng thái mutable. Nếu yêu cầu là dữ liệu rất lớn, việc trả toàn bộ List vẫn là vấn đề cần giải quyết bằng thiết kế API khác; bản sửa chỉ giải quyết những lỗi trong phạm vi công việc **đọc tất cả dòng không rỗng vào danh sách**.

Không có lý do tự động thêm `parallel()`: đọc file và thu List phải được đo thực tế và xét yêu cầu thứ tự, tài nguyên trước khi đổi chế độ.

## 15. Rà soát nguồn tự định nghĩa và xử lý song song

Nếu dự án có `Spliterator` tùy chỉnh, cần một bảng kiểm riêng.

### 15.1. Hợp đồng trySplit và estimateSize

| Thành phần | Câu hỏi khi review |
|---|---|
| `tryAdvance(action)` | Phát đúng một phần tử mỗi lần trả `true` không? Khi hết có trả `false` không? |
| `trySplit()` | Hai nhánh có **không giao nhau** và không bỏ sót phần tử không? |
| `ORDERED` | Spliterator được trả về có thực sự là **tiền tố** của phần chưa duyệt không? |
| `estimateSize()` | Có phản ánh phần tử **còn lại** sau duyệt/split không? |
| `SIZED` | Con số có chính xác theo hợp đồng nguồn không? |
| `SUBSIZED` | Mọi Spliterator con tiếp tục có size chính xác không? |
| `IMMUTABLE` | Nguồn có thật sự bảo đảm không bị thay đổi cấu trúc khi duyệt không? |
| `CONCURRENT` | Nguồn có hỗ trợ thay đổi đồng thời đúng hợp đồng không? |
| `SORTED` / `DISTINCT` | Dữ liệu có thật sự đáp ứng các lời hứa này không? |
| Vòng đời | Có tránh dùng cùng Spliterator mutable đồng thời từ nhiều thread không? |

Ví dụ lỗi đặc biệt nghiêm trọng:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    return this; // Sai: hai nhánh cùng một đối tượng và cùng con trỏ.
}
~~~

Một `trySplit` đúng trả Spliterator quản lý một phần **khác** của nguồn chưa duyệt, còn Spliterator gốc giữ phần còn lại. Với nguồn `ORDERED`, phần trả về phải là tiền tố. Không thể chỉ kiểm tra `count()` để kết luận nguồn đúng, vì `count()` có thể dùng `SIZED` mà không duyệt thực sự.

### 15.2. Khi nào parallel có lợi?

Đánh giá ba yếu tố:

1. **Kích thước nguồn:** có đủ phần tử hoặc nhiệm vụ để chia không?
2. **Chi phí từng phần tử:** công việc có đủ nặng và độc lập để bù chi phí điều phối không?
3. **Cách chia:** `Spliterator.trySplit()` có tạo các phần đủ cân bằng với chi phí thấp không?

Sau đó xét tiếp chi phí `sorted`, `distinct`, `limit` trên nguồn `ORDERED`; chi phí combiner; mức độ tranh chấp CPU/bộ nhớ; và có I/O blocking hay không.

Nếu một pipeline dùng `parallel()` nhưng có side effect hoặc accumulator dùng trạng thái chung, **đầu tiên phải sửa tính đúng**, không phải benchmark để tìm cấu hình chạy “ít lỗi hơn”.

## 16. Phương pháp đo hiệu năng có ý nghĩa

Không đo hai thuật toán khác nhau rồi kết luận chế độ song song nhanh hơn. Phải so sánh **cùng input, cùng phép toán, cùng kết quả**.

~~~java
import java.util.stream.IntStream;

public class ParallelReviewExample {
    static long work(int n) {
        long x = n + 1L;
        for (int i = 0; i < 100; i++) {
            x = x * 1_664_525L + 1_013_904_223L;
            x ^= x >>> 11;
        }
        return x & 1023L;
    }

    static long calculate(int count, boolean parallel) {
        IntStream source = IntStream.range(0, count);
        if (parallel) {
            source = source.parallel();
        }
        return source.mapToLong(ParallelReviewExample::work).sum();
    }

    public static void main(String[] args) {
        int count = 100_000;

        long sequential = calculate(count, false);
        long parallel = calculate(count, true);

        if (sequential != parallel) {
            throw new AssertionError("Kết quả hai chế độ khác nhau");
        }

        System.out.println("Kết quả nhất quán: " + sequential);
    }
}
~~~

Chương trình trên chỉ kiểm tra **tính tương đương**, chưa đo tốc độ. Để benchmark một cách đáng tin cậy:

- Dùng công cụ như **JMH** với warmup và nhiều lần lặp/fork.
- Bảo đảm kết quả được tiêu thụ, tránh tối ưu loại bỏ phép tính không quan sát được.
- So sánh dữ liệu có kích thước và phân bố chi phí đại diện.
- Kiểm soát JDK, CPU, quota container, tải máy, bộ nhớ và GC.
- Ghi lại cả throughput, latency, allocations và khả năng ảnh hưởng tới tác vụ khác.
- Không xem một lần `System.nanoTime()` là bằng chứng quyết định.

**Không sử dụng thao tác ghi console hoặc gọi HTTP trong callback làm phép đo sức mạnh tính toán CPU.** Những tài nguyên chia sẻ này có đặc tính khác và có thể khiến kết luận sai lệch.

## 17. Chính sách phiên bản Java và khả năng nâng cấp

Một dự án có thể được đọc bằng JDK mới nhưng vẫn phải chạy trên phiên bản được tổ chức hỗ trợ. Review nên ghi lại **phiên bản JDK mục tiêu** và API tối thiểu cần thiết.

| API / cú pháp | Mốc cần lưu ý |
|---|---|
| `Stream`, `Collectors`, `Optional`, `Files.lines`, `Spliterator` | Java 8 |
| `List.of`, `Collectors.filtering`, `Optional.stream` | Java 9 |
| `List.copyOf`, `Collectors.toUnmodifiableList` | Java 10 |
| `Collectors.teeing` | Java 12 |
| `Stream.toList` | Java 16 |
| `record` (không còn preview) | Java 16 |
| Switch expression (không còn preview) | Java 14 |
| Stream Gatherers (API chuẩn) | Java 24 |

Chương trình tham chiếu mục 12 chọn **Java 17+**, nên đáp ứng các cú pháp và API đã sử dụng. Nếu sản phẩm thực tế phải hỗ trợ Java 11, không nên giữ nguyên `teeing`, `record`, `Stream.toList` hay các cú pháp mới mà không có phương án tương đương.

Nếu dự án dùng Stream Gatherers để viết thao tác trung gian có trạng thái hoặc cửa sổ xử lý, vòng review phải xác minh thêm **hợp đồng finisher/integrator, khả năng kết thúc sớm, tính kết hợp** và **mức hỗ trợ của JDK triển khai**. Không nên đưa gatherer vào code chỉ để thay thế một phép `map` hoặc `filter` đơn giản.

## 18. Mức độ ưu tiên của phát hiện và tiêu chí chấp nhận

Không phải mọi góp ý review có cùng mức ưu tiên.

| Mức | Ví dụ | Cách xử lý |
|---|---|---|
| **Blocker** | Mất dữ liệu, tính sai tiền, rò rỉ tài nguyên nghiêm trọng, race condition, dùng lại Stream gây lỗi | Phải sửa và có kiểm thử trước khi chấp nhận |
| **Major** | Thiếu kiểm tra đầu vào quan trọng, null/key chưa rõ, hiệu năng gây quá tải trên dữ liệu dự kiến | Cần giải pháp và xác nhận tác động |
| **Minor** | Tên biến khó hiểu, lặp code nhỏ, format hoặc thông báo lỗi chưa tốt | Sửa theo ưu tiên, không che khuất blocker |
| **Question** | Chưa rõ chính sách ID trùng, tràn tiền, dòng lỗi hoặc giữ thứ tự | Cần quyết định nghiệp vụ, không tự đoán |

Để đánh dấu một phát hiện là đã giải quyết, nên có:

1. **Thay đổi code cụ thể** loại bỏ nguyên nhân.
2. **Kiểm thử trước/sau** chứng minh lỗi được sửa hoặc nghĩa vụ API được đáp ứng.
3. **Tác động tới API** được nêu rõ nếu kiểu trả về, thứ tự, tính mutable hoặc ngoại lệ thay đổi.
4. **Bằng chứng tài nguyên/hiệu năng** nếu tối ưu là mục tiêu của thay đổi.
5. **Không thêm lỗi mới** ở nhánh khác, ví dụ sửa leak nhưng vô tình trả Stream đã đóng.

Nên tách review nội dung học thuật và code review production: một ví dụ Java ngắn có thể hợp lệ để giải thích `reduce` nhưng chưa đầy đủ về observability, giới hạn bộ nhớ, dữ liệu cá nhân hoặc triển khai thực tế. Review phải dựa trên **mục đích của artifact**.

## 19. Checklist sử dụng trước khi hoàn tất dự án

| Nhóm | Câu hỏi quyết định | Bằng chứng mong đợi |
|---|---|---|
| Yêu cầu | Đã có input/output contract và trường hợp thiếu dữ liệu? | Bộ test mẫu, ví dụ biên |
| Nguồn | Nguồn có thể duyệt lại hay chỉ một lần? | Thiết kế ownership, test single-use |
| Đóng tài nguyên | Nguồn I/O có `try-with-resources`? | Test cả nhánh thành công và ngoại lệ |
| Lambda | Có side effect, non-interference hoặc trạng thái chung? | Code inspection và test parallel khi cần |
| Thứ tự | Có dùng đúng `findFirst`, `findAny`, `sorted`, `forEachOrdered`? | Test kết quả/order |
| Null | Có chính sách null và parse lỗi? | Test null/blank/invalid |
| Khóa nhóm | Có quy tắc equality, duplicate ID, null key? | Test dữ liệu trùng và phân nhóm |
| Reduction | Identity và associativity hợp lệ? | Test nguồn rỗng, sequential/parallel |
| Collector | Supplier/accumulator/combiner/finisher đúng hợp đồng? | Test merge và tính bất biến |
| Số học | Có thể tràn `int/long` hoặc sai số `double`? | Test số lớn, chính sách tính toán |
| Kích thước | Có giới hạn số dòng và cardinality nhóm? | Test dữ liệu lớn, đo heap |
| Parallel | Có đáng bật không và đã đo chưa? | Benchmark, CPU/GC/latency |
| Phiên bản | API/cú pháp dùng có phù hợp JDK target? | Kiểm tra build/CI |
| Bảo trì | Tách parse, business rule, aggregate, I/O? | Hàm rõ trách nhiệm và test riêng |
| Bảo mật | Log lỗi có lộ dữ liệu nhạy cảm không? | Chính sách logging/redaction |
| Triển khai | Có kế hoạch rollback và quan sát sau phát hành? | Giám sát, cảnh báo, tiêu chí dừng |

Có thể dùng bảng này làm **mẫu review cho pull request**. Quan trọng nhất là không đánh dấu “đã kiểm tra” khi chưa có test hoặc lý giải đủ sức chứng minh.

## 20. Bài tập tổng hợp: review và đề xuất bản vá

**Tình huống:** dự án hiện có một chức năng tổng hợp đơn hàng từ Stream đọc file, nhưng team muốn tăng tốc bằng cách gọi `parallel()` và thu Map doanh thu. Reviewer phát hiện bốn vấn đề:

- Nguồn file không được đóng khi parse thất bại.
- `parallel().forEach(...)` cập nhật Map ngoài không đồng bộ.
- Một số dòng trùng ID, nhưng yêu cầu nghiệp vụ chưa xác định có được gộp không.
- Kết quả hiển thị thứ tự vùng dựa vào cách `HashMap` tình cờ duyệt.

**Yêu cầu thực hành:**

1. Phân loại từng vấn đề thành blocker, major hoặc question và giải thích.
2. Phác thảo pipeline **tuần tự** đúng hợp đồng trước khi tối ưu.
3. Viết ít nhất năm kiểm thử bao gồm nguồn rỗng, dữ liệu không hợp lệ, ID trùng, dữ liệu lớn và lỗi I/O.
4. Chọn cấu trúc Map và chính sách thứ tự hiển thị; giải thích vì sao.
5. Chỉ ra điều kiện nào khiến bạn quyết định **không bật parallel**.
6. Mô tả một bằng chứng đủ mạnh để chấp nhận rằng cải tiến hiệu năng không làm sai kết quả.

### Gợi ý hướng giải

**Về mức độ ưu tiên:** rò rỉ tài nguyên và race condition là blocker; trùng ID là **question về chính sách** nhưng có thể trở thành blocker nếu dẫn đến tính sai doanh thu; thứ tự Map là lỗi phải sửa nếu đầu ra đã cam kết thứ tự.

**Về pipeline:** bắt đầu từ `Files.lines` trong `try-with-resources`, tách `parseLine`, `filter(Payment::paid)` và collector `groupingBy(..., summingLong(...))` hoặc `teeing` tùy báo cáo. Không đưa Map mutable dùng chung vào callback.

**Về ID trùng:** chưa tự chọn “giữ bản ghi đầu” hay “gộp số tiền”. Hãy yêu cầu quyết định nghiệp vụ, sau đó thêm test chứng minh đúng chính sách đó. `distinct()` không tự giải quyết khi equality của record khác khóa ID.

**Về thứ tự:** dùng `TreeMap` nếu cần khóa tăng dần theo comparator, hoặc sắp xếp khi xuất kết quả. Nếu thứ tự là một danh sách vùng do nghiệp vụ định nghĩa, cần comparator theo danh sách đó thay vì `String.compareTo` mặc định.

**Về benchmark:** chạy cùng dữ liệu đại diện trên cùng JDK/môi trường, so sánh kết quả trước khi đo; sử dụng nhiều lượt warmup/fork, kiểm soát tải, đo latency/throughput/heap và theo dõi lỗi trên các tình huống biên. Không chấp nhận một ảnh chụp thời gian đơn lẻ làm bằng chứng.

### Câu hỏi tự kiểm tra

1. Vì sao `Files.lines(...).count()` chưa đủ để bảo đảm đóng file? — **Terminal operation không tự gọi close**.
2. Có được gọi hai terminal operation trên cùng một Stream không? — **Không**.
3. `peek` có được bảo đảm chạy cho mọi phần tử khi dùng `count()` không? — **Không**.
4. Khi nào nên dùng `teeing`? — **Khi cần ghép hai collector trên cùng nguồn trong một terminal operation**.
5. Vì sao `parallelStream().forEach(sharedList::add)` nguy hiểm? — **Có trạng thái chia sẻ không thread-safe**.
6. Vì sao `Stream.distinct()` có thể không khử được ID trùng? — **Nó dùng `equals`/`hashCode` của cả phần tử, không tự hiểu khóa nghiệp vụ**.
7. `groupingBy` có bảo đảm thứ tự Map không? — **Không**, trừ khi thiết kế map factory phù hợp hoặc sắp xếp khi xuất.
8. Vì sao `reduce(0, Integer::min)` có thể sai? — **0 không phải identity của min cho mọi dữ liệu**.
9. `Collectors.toList()` có bảo đảm trả một `ArrayList` mutable không? — **Không**.
10. `Spliterator.SUBSIZED` nói gì? — **Các Spliterator con tiếp tục có kích thước chính xác theo hợp đồng**.
11. Một benchmark có thể chứng minh code đúng nghiệp vụ không? — **Không**, phải có kiểm thử tính đúng riêng.
12. Nếu tổng tiền có nguy cơ vượt `long`, nên làm gì? — **Xác định chính sách báo lỗi hoặc dùng biểu diễn số phù hợp**.

## 21. Kết luận: định nghĩa “hoàn thành” bằng bằng chứng

Một dự án Stream được review tốt không phải dự án có biểu thức pipeline ngắn nhất hay nhiều chỗ gọi `parallel()` nhất. Đó là dự án có **hợp đồng đầu vào/đầu ra rõ ràng**, **lựa chọn API có thể giải thích**, **cách xử lý dữ liệu rỗng và lỗi có chủ đích**, **quyền sở hữu tài nguyên xác định**, **không có side effect nguy hiểm** và **khả năng kiểm thử sau khi thay đổi**.

Hãy review theo thứ tự: **đúng nghiệp vụ → đúng hợp đồng API → an toàn tài nguyên → dễ bảo trì → đo hiệu năng**. Khi áp dụng song song hoặc xây custom `Spliterator`/collector, phải giữ nguyên các bất biến về chia nguồn, kích thước, identity, associativity, combiner, thứ tự và trạng thái.

Kỹ năng quan trọng nhất không phải ghi nhớ mọi phương thức Stream, mà là biết **đặt đúng câu hỏi và thu thập bằng chứng** trước khi đưa một pipeline vào dự án lớn. Đây là nền tảng để làm việc với `filter`, `map`, `reduce`, `collect`, grouping, collector tùy chỉnh, `Spliterator`, parallel Stream và Stream Gatherers một cách chính xác, tiết kiệm tài nguyên và có thể bảo trì lâu dài.
