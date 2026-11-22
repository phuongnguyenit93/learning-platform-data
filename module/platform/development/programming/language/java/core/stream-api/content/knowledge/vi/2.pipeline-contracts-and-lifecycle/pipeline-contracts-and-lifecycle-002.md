# Tính sử dụng một lần và lỗi tái sử dụng Stream

Trong chương **Hợp đồng và vòng đời pipeline**, một quy tắc nền tảng của **Java Stream API** là: **mỗi đối tượng `Stream` chỉ được sử dụng để thiết lập và thực thi một pipeline duy nhất**. Quy tắc này áp dụng dù pipeline dùng `filter`, `map`, `reduce`, `collect`, nhóm dữ liệu bằng collector, xử lý song song hay các thao tác nâng cao như Stream Gatherers. Hiểu đúng quy tắc giúp viết chương trình xử lý dữ liệu khai báo mà không gặp lỗi vòng đời, đồng thời chọn cách tính toán phù hợp với nguồn dữ liệu và chi phí xử lý.

## 1. Phân biệt Stream với nguồn dữ liệu

`Stream<T>` biểu diễn một luồng tính toán trên các phần tử từ **nguồn dữ liệu** (collection, mảng, tệp, bộ sinh, ...). Bản thân `Stream` không phải một collection để duyệt lại tùy ý.

- **Nguồn dữ liệu**: ví dụ một `List<String>`. Với nguồn có thể duyệt lại như danh sách, ta thường có thể tạo nhiều Stream mới bằng cách gọi `list.stream()` nhiều lần.
- **Pipeline**: chuỗi các thao tác trung gian như `filter` và `map`, kết thúc bằng một thao tác đầu cuối (terminal operation) như `count`, `findFirst`, `reduce`, `collect` hoặc `forEach`.
- **Đối tượng Stream cụ thể**: chỉ thuộc về **một** pipeline. Gọi một thao tác trên Stream đã được liên kết với pipeline khác hoặc đã kết thúc là vi phạm hợp đồng sử dụng.

Ví dụ, hai lời gọi `names.stream()` sau đây tạo **hai Stream khác nhau** trên cùng danh sách. Danh sách không bị “tiêu thụ” chỉ vì ta đã duyệt nó bằng Stream.

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Linh", "Minh");

long total = names.stream().count();               // 3
long startsWithL = names.stream()
        .filter(name -> name.startsWith("L"))
        .count();                                   // 2
~~~

Ví dụ dùng `List.of` (Java 9+); nguyên tắc sử dụng một lần đã có từ khi Stream API xuất hiện trong Java 8.

## 2. Vòng đời pipeline và thời điểm “đã sử dụng”

| Giai đoạn | Ví dụ | Ý nghĩa với vòng đời |
| --- | --- | --- |
| Tạo Stream | `names.stream()`, `Stream.of(...)` | Nhận một Stream mới, chưa gắn thao tác. |
| Ghép thao tác trung gian | `filter`, `map`, `sorted`, `distinct` | Tạo pipeline **lazy**: thông thường chưa duyệt phần tử, nhưng Stream đầu vào đã được **liên kết** với pipeline vừa tạo và không còn dành cho một nhánh thứ hai. |
| Chạy thao tác đầu cuối | `count`, `findFirst`, `anyMatch`, `reduce`, `collect`, `forEach` | Kết thúc pipeline. Stream của pipeline không được sử dụng lại, kể cả khi thao tác chỉ đọc một phần dữ liệu hoặc không cần duyệt tất cả phần tử. |
| Đóng Stream | `close()` | Đóng Stream và chạy các handler đã đăng ký qua `onClose`; Stream đã đóng không được tiếp tục sử dụng. Đây là khái niệm khác với việc chạy terminal operation. |

Một thao tác trung gian có tính **lazy** không có nghĩa là Stream đầu vào còn có thể dùng để ghép nhánh khác. “Chưa xử lý phần tử” và “chưa liên kết vào pipeline” là hai trạng thái khác nhau.

### Ví dụ A: Dùng lại sau thao tác đầu cuối

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> names = List.of("Lan", "Linh", "Minh");

Stream<String> selected = names.stream()
        .filter(name -> name.startsWith("L"));

long count = selected.count(); // Hợp lệ: terminal operation đầu tiên
List<String> items = selected.toList(); // Sai: tái sử dụng Stream
~~~

Trên các JDK thông dụng, dòng cuối thường ném:

~~~text
java.lang.IllegalStateException: stream has already been operated upon or closed
~~~

`toList()` là terminal operation có từ Java 16. Thay bằng `collect(Collectors.toList())` trên Java 8–15 cũng không làm việc tái sử dụng trở nên hợp lệ. Chuỗi thông báo và thời điểm ném ngoại lệ có thể khác theo triển khai JDK.

### Ví dụ B: Rẽ nhánh khi chưa chạy terminal operation

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> names = List.of("Lan", "Linh", "Minh");

Stream<String> source = names.stream();
Stream<String> uppercase = source.map(String::toUpperCase);

// Sai: source đã được liên kết vào pipeline của uppercase.
Stream<String> shortNames = source.filter(name -> name.length() <= 3);
~~~

Lỗi có thể xuất hiện ngay tại `source.filter(...)`, **trước khi** gọi terminal operation trên `uppercase`. Vì vậy, không nên hiểu quy tắc thành “chỉ sau khi gọi `count` hoặc `collect` mới không được dùng lại”.

### Ví dụ C: Short-circuit vẫn kết thúc pipeline

~~~java
import java.util.stream.Stream;

Stream<Integer> numbers = Stream.of(10, 20, 30, 40);

boolean found = numbers.anyMatch(n -> n == 10); // Dừng sớm khi đã tìm thấy
long total = numbers.count();                   // Sai: Stream đã kết thúc
~~~

`anyMatch`, `allMatch`, `noneMatch`, `findFirst` và `findAny` là các terminal operation. Việc có thể dừng sớm không biến các phần tử còn lại thành một Stream có thể tiếp tục dùng. Tương tự, kết quả rỗng của `findFirst` không cho phép dùng lại Stream.

> **Lưu ý về hợp đồng API:** Không phải mọi trường hợp tái sử dụng đều được phát hiện và ném `IllegalStateException`. Một số thao tác có thể trả về chính đối tượng nhận thao tác, khiến việc phát hiện khó hơn. **Không thấy ngoại lệ không có nghĩa là chương trình được phép tái sử dụng Stream.**

## 3. Ba cách xử lý nhu cầu đọc hoặc tính toán nhiều lần

### Cách 1: Tạo Stream mới từ nguồn có thể duyệt lại

Khi dữ liệu là một collection có thể đọc lại, hãy khởi tạo pipeline mới cho **mỗi** kết quả đầu cuối.

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Linh", "Minh");

long count = names.stream()
        .filter(name -> name.startsWith("L"))
        .count();

List<String> upperNames = names.stream()
        .filter(name -> name.startsWith("L"))
        .map(String::toUpperCase)
        .toList();

System.out.println(count);      // 2
System.out.println(upperNames); // [LAN, LINH]
~~~

Cách này dễ đọc và không phải lưu kết quả trung gian, nhưng phần `filter` sẽ được thực hiện lại khi tạo pipeline mới. Với nguồn dữ liệu hoặc phép biến đổi tốn kém, cần cân nhắc chi phí duyệt lại.

### Cách 2: Dùng factory hoặc `Supplier` tạo **Stream mới**

Khi nhiều nơi cần cùng một chuỗi xử lý, hãy trừu tượng hóa **cách tạo** pipeline, không lưu một đối tượng Stream để chia sẻ.

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

List<String> names = List.of("Lan", "Linh", "Minh");

Supplier<Stream<String>> selected = () -> names.stream()
        .filter(name -> name.startsWith("L"))
        .map(String::toUpperCase);

long count = selected.get().count();       // Stream thứ nhất
List<String> items = selected.get().toList(); // Stream thứ hai
~~~

Mỗi lần gọi `selected.get()` phải trả về **Stream mới**. Mẫu sau **vẫn sai** vì factory chỉ trả lại cùng một đối tượng:

~~~java
Stream<String> oneStream = names.stream();
Supplier<Stream<String>> wrong = () -> oneStream;

long first = wrong.get().count();
long second = wrong.get().count(); // Sai: nhận lại Stream đã dùng
~~~

Trong thiết kế API, một phương thức cần tính toán lặp lại thường nên nhận `Collection<T>` hoặc `Supplier<Stream<T>>` có khả năng tạo Stream mới; một tham số `Stream<T>` biểu đạt tốt hơn một lần duyệt có giới hạn.

### Cách 3: Tính nhiều chỉ số trong **một lần duyệt**

Nếu hai kết quả đều có thể tổng hợp từ cùng phần tử, một terminal operation với collector phù hợp sẽ tiết kiệm việc đọc lại. Chẳng hạn, `summarizingInt` tính cùng lúc số phần tử, tổng, giá trị nhỏ nhất, lớn nhất và trung bình độ dài tên:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("Lan", "Linh", "Minh");

IntSummaryStatistics stats = names.stream()
        .collect(Collectors.summarizingInt(String::length));

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 11
System.out.println(stats.getAverage()); // 3.6666666666666665
~~~

`collect` là **một** terminal operation; collector có thể tích lũy nhiều loại thông tin trong lần xử lý đó. Cùng ý tưởng áp dụng với `groupingBy`, collector tùy chỉnh và các phép tổng hợp cần chạy trên Stream song song, miễn tuân thủ hợp đồng của collector tương ứng.

Nếu các bước xử lý sau cần đọc lại **chính các phần tử đầu ra**, có thể materialize dữ liệu:

~~~java
List<String> selectedNames = names.stream()
        .filter(name -> name.startsWith("L"))
        .toList();

long count = selectedNames.size();
List<Integer> lengths = selectedNames.stream()
        .map(String::length)
        .toList();
~~~

Đây là lưu một **kết quả dạng collection** để dùng lại, không phải tái sử dụng Stream cũ. Đổi lại, ứng dụng phải giữ các phần tử trong bộ nhớ; cần cân nhắc với dữ liệu rất lớn hoặc vô hạn.

## 4. Nguồn chỉ đọc được một lần và quản lý tài nguyên

Không phải nguồn nào cũng giống `List`. Dòng dữ liệu từ kết nối, bộ đọc tệp, iterator một chiều hoặc nguồn phát sự kiện có thể không khôi phục được trạng thái ban đầu. **Tạo Stream mới** chỉ là lời giải khi chính nguồn dữ liệu có thể mở lại hoặc duyệt lại.

Ví dụ đọc tệp bằng `Files.lines`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path path = Path.of("users.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> nonBlank = lines
            .filter(line -> !line.isBlank())
            .toList();
    System.out.println(nonBlank.size());
} // Tự gọi close() ngay cả khi xử lý gặp ngoại lệ
~~~

`Files.lines` tạo Stream gắn với tài nguyên I/O nên cần `try-with-resources`. Một terminal operation **không tự động đóng** tất cả Stream có tài nguyên. Nếu cần đọc tệp lần thứ hai, hãy mở một `Files.lines(path, ...)` mới trong một khối `try-with-resources` mới, khi tệp vẫn còn sẵn và có thể đọc lại.

Cũng cần tách bạch:

- **Đã thực hiện terminal operation**: pipeline đã hết quyền sử dụng, dù Stream chưa được gọi `close()`.
- **Đã gọi `close()`**: Stream không thể tiếp tục vận hành, dù trước đó chưa có terminal operation.
- **Đã đóng một Stream I/O**: không đồng nghĩa nguồn bên ngoài có thể tự quay về đầu; khả năng đọc lại phụ thuộc vào cách tạo nguồn mới.

Nếu nguồn một chiều không mở lại được, có hai hướng: thiết kế collector để lấy đủ kết quả trong một lượt, hoặc lưu dữ liệu cần dùng lại vào collection/bộ nhớ đệm phù hợp. Không thể “reset” một `Stream` đã dùng bằng cách gọi `sequential()`, `parallel()` hoặc `unordered()`.

## 5. Nhận diện và sửa lỗi trong mã thực tế

| Tình huống | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Gọi `count()` rồi `collect()` trên cùng biến Stream | Hai terminal operation trên một pipeline | Tạo hai Stream từ nguồn có thể duyệt lại hoặc gộp kết quả vào một collector. |
| Dùng một biến Stream để tạo hai nhánh `map` và `filter` | Stream nguồn đã liên kết với nhánh đầu | Tạo Stream mới cho mỗi nhánh hoặc xây một pipeline thống nhất. |
| Lưu `Stream` làm field và dùng qua nhiều request/phương thức | Đối tượng Stream có vòng đời một lần | Lưu nguồn dữ liệu hoặc một factory tạo Stream mới mỗi lần. |
| Dùng lại sau `findFirst()` / `anyMatch()` | Short-circuit vẫn là terminal operation | Tạo pipeline mới; nếu nguồn một chiều, thiết kế xử lý trong một lượt. |
| Truy cập Stream sau `close()` hoặc ngoài khối `try-with-resources` | Stream đã đóng | Xử lý khi Stream còn mở; mở nguồn mới nếu cần lượt đọc khác. |
| Chạy lại pipeline trên dữ liệu đã bị nguồn thay đổi | Hai Stream mới có thể quan sát hai trạng thái khác nhau | Tạo snapshot nếu cần kết quả nhất quán, đồng thời chấp nhận chi phí lưu trữ. |

Khi gặp thông báo kiểu `stream has already been operated upon or closed`:

1. Xác định **đối tượng Stream nào** xuất hiện ở dòng gây lỗi, không chỉ xem collection nguồn.
2. Tìm mọi thao tác trung gian, terminal operation và lời gọi `close` sử dụng cùng đối tượng đó.
3. Kiểm tra Stream có bị lưu trong field, cache, biến dùng chung hoặc factory trả về cùng instance không.
4. Chọn cách sửa dựa trên **khả năng đọc lại của nguồn**: pipeline mới, một collector gộp kết quả, hay lưu snapshot.
5. Chạy lại ca sử dụng nhiều lần hoặc gọi hai nhánh để xác nhận mỗi pipeline chỉ có một terminal operation.

Đừng dùng `try/catch (IllegalStateException)` rồi tiếp tục duyệt Stream như một cơ chế phục hồi; một Stream đã sử dụng không có thao tác reset được API bảo đảm.

## 6. Liên hệ với laziness, song song và hiệu năng

- **Laziness không cho phép tái sử dụng.** `filter`/`map` thường chưa xử lý phần tử lúc khai báo, nhưng Stream đầu vào đã thuộc pipeline mới. Khi một terminal operation khởi chạy, các bước cần thiết sẽ được thực hiện theo chiến lược của pipeline.
- **Terminal operation có thể tối ưu hóa việc duyệt.** Chẳng hạn, một số pipeline có thể trả lời `count()` từ kích thước đã biết mà không chạy mọi hành động quan sát trong `peek`. Dù vậy, Stream vẫn đã kết thúc và không được dùng lại.
- **Parallel stream không tạo bản sao dùng lại.** `parallel()` chỉ cấu hình cách thực thi; nó không biến một Stream thành collection hay cho phép có nhiều terminal operation. Các ràng buộc về trạng thái và tính an toàn của hàm/collector vẫn cần được tôn trọng.
- **Nguồn lặp lại có chi phí.** Hai lời gọi `list.stream()` có thể duyệt lại cùng các phần tử hai lần; với thao tác nặng hoặc I/O, gom vào một lần duyệt hay lưu kết quả trung gian có thể hợp lý hơn.
- **Các thao tác cao cấp không đổi vòng đời.** `Spliterator` mô tả cách phân chia/duyệt nguồn và Stream Gatherers bổ sung khả năng biến đổi pipeline, nhưng chúng không làm một đối tượng Stream trở nên tái sử dụng được.

## 7. Tự kiểm tra

**Câu 1.** Đoạn dưới đây sai ở đâu?

~~~java
Stream<Integer> s = Stream.of(1, 2, 3);
Stream<Integer> even = s.filter(n -> n % 2 == 0);
long a = even.count();
long b = s.count();
~~~

**Đáp án:** `s` đã được liên kết vào pipeline `even` ngay sau lời gọi `filter`. `s.count()` cố vận hành lại Stream đầu vào; việc `even.count()` đã chạy càng khẳng định pipeline đã kết thúc. Hãy tạo Stream mới từ nguồn nếu cần kết quả độc lập.

**Câu 2.** Đoạn này có hợp lệ không?

~~~java
List<Integer> source = List.of(1, 2, 3);
int sum = source.stream().mapToInt(Integer::intValue).sum();
long count = source.stream().count();
~~~

**Đáp án:** Có. Hai lời gọi `source.stream()` tạo hai đối tượng Stream riêng; mỗi đối tượng được dùng trong đúng một pipeline. `source` vẫn là cùng danh sách.

**Câu 3.** Vì sao đoạn sau vẫn sai nếu `findFirst()` chỉ lấy một phần tử?

~~~java
Stream<Integer> s = Stream.of(7, 8, 9);
int first = s.findFirst().orElseThrow();
long count = s.count();
~~~

**Đáp án:** `findFirst` là terminal operation và đã kết thúc pipeline, dù chỉ cần đọc một phần dữ liệu. `s.count()` là lần vận hành thứ hai trên cùng Stream.

**Ghi nhớ:** Tái sử dụng **nguồn dữ liệu có thể duyệt lại** là hợp lệ; tái sử dụng **cùng đối tượng Stream** là vi phạm hợp đồng. Mỗi pipeline có một đường đi qua các thao tác trung gian và một điểm kết thúc bằng terminal operation; tài nguyên I/O cần được đóng đúng vòng đời.
