# Tạo Stream mới từ nguồn hoặc Supplier để xử lý nhiều lần

Trong Java, **một đối tượng `Stream` chỉ được tiêu thụ một lần**. Sau khi gọi một terminal operation như `count()`, `toList()`, `collect()`, `findFirst()` hay `forEach()`, không được đem chính đối tượng stream đó dùng cho một pipeline khác. Nếu muốn chạy nhiều phép truy vấn trên cùng nguồn dữ liệu, cách đúng là **tạo Stream mới cho mỗi lần xử lý**, trực tiếp từ nguồn có thể duyệt lại hoặc qua một **`Supplier<Stream<T>>`** đóng vai trò factory.

Ví dụ ý tưởng:

~~~java
// source là một List<String> có thể duyệt lại:
long count = source.stream().count();       // Stream thứ nhất
List<String> names = source.stream().toList(); // Stream thứ hai
~~~

Không phải `List` bị tiêu thụ; **đối tượng Stream do `source.stream()` trả về mới bị tiêu thụ**. Nguồn còn tồn tại và có thể tạo những stream khác nếu bản thân nguồn cho phép duyệt lại.

**Cảnh báo cốt lõi:** Supplier chỉ hữu ích nếu mỗi lời gọi `get()` thực sự trả về **một pipeline Stream mới trên nguồn có thể đọc lại**. Nếu Supplier luôn trả cùng Stream đã tạo từ trước, hoặc trả Stream mới nhưng vẫn cùng đọc một `Iterator`/cổng dữ liệu một lần, nó **không làm dữ liệu có thể phát lại**.

## 1. Phân biệt nguồn, pipeline và lần tiêu thụ

Có ba đối tượng/khái niệm nên tách riêng:

1. **Nguồn** (*source*): `List`, `Set`, mảng, dãy số, tệp tin, generator, cursor... Nguồn có thể hỗ trợ đọc lặp hoặc chỉ một lượt tùy loại.
2. **Stream/pipeline**: đối tượng mô tả phép xử lý từ nguồn, gồm các intermediate operation như `filter`, `map`, `sorted`. Các thao tác này thường lazy.
3. **Terminal operation**: kích hoạt tiêu thụ stream và trả kết quả hoặc thực hiện hành động, ví dụ `count()`, `sum()`, `toList()`, `collect()`.

Mô hình đúng cho collection có thể duyệt lại:

~~~text
                 ┌─ stream() → filter(...) → count()
List<String> ────┤
                 ├─ stream() → map(...)    → toList()
                 └─ stream() → sorted()    → findFirst()
~~~

Mỗi nhánh bắt đầu bằng **một lời gọi `stream()` khác nhau**, vì mỗi terminal operation kết thúc riêng một pipeline.

Mô hình sai:

~~~text
List<String> → stream() ── count()
                     └── toList()   ✗ dùng lại Stream đã tiêu thụ
~~~

Một stream có thể báo `IllegalStateException` khi bị tái sử dụng (với thông báo tương tự “stream has already been operated upon or closed”). **Không nên dựa vào thông báo ngoại lệ cụ thể**, và không suy rằng mọi lần sử dụng sai đều được phát hiện tại cùng một điểm; hợp đồng API đã cấm tái sử dụng.

## 2. Ví dụ thực thi: dùng lại cùng Stream là sai

Tạo file `StreamReuseFailureDemo.java`:

~~~java
import java.util.stream.Stream;

public class StreamReuseFailureDemo {
    public static void main(String[] args) {
        Stream<Integer> numbers = Stream.of(2, 4, 6);

        System.out.println("first count=" + numbers.count());

        try {
            System.out.println("second count=" + numbers.count());
        } catch (IllegalStateException ex) {
            System.out.println("second=IllegalStateException");
        }
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac --release 17 StreamReuseFailureDemo.java
java StreamReuseFailureDemo
~~~

Kết quả:

~~~text
first count=3
second=IllegalStateException
~~~

Sau lần `count()` đầu tiên, stream đã được tiêu thụ. Lần thứ hai không thể biến `Stream<Integer>` cũ thành đối tượng “mới” chỉ bằng cách gọi lại `count()`.

Điều này **vẫn đúng với Stream rỗng**: `Stream.empty().count()` trả 0 nhưng stream ấy cũng đã được dùng. Đừng dùng `count() == 0` làm dấu hiệu một stream vẫn có thể tái sử dụng.

Không chỉ terminal operation mới có liên quan: **thao tác liên kết pipeline với stream đã bị liên kết/đóng cũng có thể bị từ chối**. Vì vậy, nguyên tắc an toàn nhất là coi stream là một pipeline dùng một lần, không cất nó vào field để dùng lại tùy ý.

## 3. Tạo trực tiếp Stream mới từ `Collection`

Với `List<T>`, `Set<T>` và các collection có thể duyệt lại, có thể gọi `stream()` nhiều lần để tạo các pipeline riêng.

Tạo file `FreshStreamFromListDemo.java`:

~~~java
import java.util.List;

public class FreshStreamFromListDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");

        long longNames = names.stream()
                .filter(name -> name.length() >= 3)
                .count();

        List<String> uppercase = names.stream()
                .map(String::toUpperCase)
                .toList();

        String first = names.stream()
                .sorted()
                .findFirst()
                .orElse("Không có");

        System.out.println("longNames=" + longNames);
        System.out.println("uppercase=" + uppercase);
        System.out.println("first=" + first);
    }
}
~~~

~~~bash
javac --release 17 FreshStreamFromListDemo.java
java FreshStreamFromListDemo
~~~

Kết quả:

~~~text
longNames=2
uppercase=[AN, BÌNH, CHI]
first=An
~~~

Giải thích: `"Bình"` có 4 ký tự UTF-16, `"Chi"` có 3, `"An"` có 2, nên `longNames == 2`. `String::toUpperCase` chuyển từng chuỗi; danh sách gốc không bị tiêu thụ. `sorted()` chọn `"An"` là chuỗi đầu theo thứ tự tự nhiên trong dữ liệu này.

Với `Set` không có encounter order xác định (như `HashSet`), mỗi stream mới vẫn có thể dùng được nhưng **thứ tự xử lý/kết quả có thể không được bảo đảm**. Tạo mới một pipeline không đồng nghĩa làm nguồn trở thành ordered hoặc biến dữ liệu không ổn định thành snapshot.

## 4. `Supplier<Stream<T>>`: đóng gói cách tạo pipeline mới

`java.util.function.Supplier<R>` là interface có phương thức `R get()`. Với `R = Stream<T>`, ta có một **stream factory**:

~~~java
Supplier<Stream<String>> factory = () -> names.stream();
~~~

Đây là đoạn minh họa trong phương thức có `names: List<String>`. Mỗi `factory.get()` gọi lại `names.stream()` và tạo pipeline mới.

Có thể viết ngắn bằng method reference:

~~~java
Supplier<Stream<String>> factory = names::stream;
~~~

Hai cách trên tương đương về mục đích. Supplier **không chứa sẵn kết quả của stream**; `get()` chỉ tạo một stream mới, còn kết quả được tính khi pipeline mới có terminal operation.

Tạo file `StreamSupplierDemo.java`:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class StreamSupplierDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 4, 6);

        Supplier<Stream<Integer>> factory = values::stream;

        long count = factory.get()
                .filter(n -> n >= 4)
                .count();

        int sum = factory.get()
                .mapToInt(Integer::intValue)
                .sum();

        List<Integer> descending = factory.get()
                .sorted(Comparator.reverseOrder())
                .toList();

        System.out.println("count=" + count);
        System.out.println("sum=" + sum);
        System.out.println("descending=" + descending);
    }
}
~~~

~~~bash
javac --release 17 StreamSupplierDemo.java
java StreamSupplierDemo
~~~

Kết quả:

~~~text
count=2
sum=12
descending=[6, 4, 2]
~~~

**Ba lần gọi `factory.get()`** tạo ba stream khác nhau. Nếu viết `Stream<Integer> s = factory.get()` một lần rồi dùng `s` ba lần, vấn đề tái sử dụng vẫn xảy ra. Nhớ đặt `get()` **bên trong từng lần xử lý**.

## 5. Factory có thể tạo cả pipeline trung gian, không chỉ nguồn

Một Supplier có thể đóng gói các phép xử lý chung, để nhiều terminal operation tái sử dụng **định nghĩa pipeline**, chứ không tái sử dụng đối tượng stream.

Tạo file `ReusablePipelineFactoryDemo.java`:

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class ReusablePipelineFactoryDemo {
    public static void main(String[] args) {
        List<String> raw = List.of(" Ana ", "Bo", "Chi", " An ");

        Supplier<Stream<String>> validNames = () -> raw.stream()
                .map(String::trim)
                .filter(s -> s.length() >= 3);

        long count = validNames.get().count();
        List<String> names = validNames.get().sorted().toList();

        System.out.println("count=" + count);
        System.out.println("names=" + names);
    }
}
~~~

~~~bash
javac --release 17 ReusablePipelineFactoryDemo.java
java ReusablePipelineFactoryDemo
~~~

Kết quả:

~~~text
count=2
names=[Ana, Chi]
~~~

Khi gọi `validNames.get()`, lambda tạo một **pipeline mới** từ `raw.stream()`, rồi gắn `map` và `filter`. Pipeline chỉ thực sự xử lý dữ liệu khi `count()` hoặc `toList()` được gọi.

Cách này hữu ích khi nhiều phép truy vấn có chung bước lọc/chuyển đổi, nhưng cần lưu ý:

- Các bước trung gian phải **stateless/non-interfering**, đặc biệt nếu factory được gọi nhiều lần hoặc dùng song song.
- Nếu danh sách nguồn thay đổi giữa hai lần gọi, hai pipeline **có thể cho kết quả khác nhau**. Factory không tự bảo đảm snapshot bất biến.
- Không đặt một đối tượng `Stream` đã khởi tạo ngoài supplier rồi nối tiếp từ nó ở mỗi lần `get()`; cách đó vẫn gắn lại pipeline cũ.

## 6. Hai kiểu Supplier nhìn giống nhau nhưng một kiểu sai

**Đúng — tạo Stream bên trong `get()`:**

~~~java
// Đúng: mỗi lần gọi get() sẽ chạy numbers.stream().
Supplier<Stream<Integer>> correct = numbers::stream;
~~~

**Sai — tạo Stream trước rồi luôn trả lại đối tượng cũ:**

~~~java
// Sai: sourceStream chỉ được tạo MỘT lần.
Stream<Integer> sourceStream = numbers.stream();
Supplier<Stream<Integer>> broken = () -> sourceStream;
~~~

Ví dụ chương trình `BrokenStreamSupplierDemo.java`:

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class BrokenStreamSupplierDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3);
        Stream<Integer> original = numbers.stream();

        Supplier<Stream<Integer>> broken = () -> original;

        System.out.println("first=" + broken.get().count());

        try {
            System.out.println("second=" + broken.get().count());
        } catch (IllegalStateException ex) {
            System.out.println("second=IllegalStateException");
        }
    }
}
~~~

~~~bash
javac --release 17 BrokenStreamSupplierDemo.java
java BrokenStreamSupplierDemo
~~~

Kết quả:

~~~text
first=3
second=IllegalStateException
~~~

Một lambda `() -> original` chỉ trả về **tham chiếu đang giữ**; lambda không tự biến đối tượng đó thành mới. Trong code review, hãy kiểm tra biểu thức chạy mỗi lần `get()`: có thực sự tạo lại stream từ một nguồn cho phép duyệt lại hay không?

Tương tự, không dùng:

~~~java
// Sai nếu getter trả cùng instance stream cũ:
Supplier<Stream<String>> factory = () -> cachedStream;
~~~

Nếu cần cache để xử lý nhiều lần, thường nên **cache dữ liệu đã materialize** vào `List`/collection (nếu kích thước và quy tắc cập nhật cho phép), rồi tạo `list.stream()` ở mỗi lần.

## 7. Stream mới không đồng nghĩa nguồn được đọc lại từ đầu

Một bẫy tinh vi: Supplier có thể tạo **đối tượng Stream mới** nhưng dùng lại **cùng một `Iterator` đã tiến lên phía trước**.

Tạo file `OneShotIteratorDemo.java`:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class OneShotIteratorDemo {
    public static void main(String[] args) {
        Iterator<Integer> sharedIterator =
                List.of(1, 2, 3).iterator();

        Supplier<Stream<Integer>> wrong = () -> StreamSupport.stream(
                Spliterators.spliteratorUnknownSize(
                        sharedIterator, Spliterator.ORDERED),
                false);

        System.out.println("first=" + wrong.get().toList());
        System.out.println("second=" + wrong.get().toList());
    }
}
~~~

~~~bash
javac --release 17 OneShotIteratorDemo.java
java OneShotIteratorDemo
~~~

Kết quả:

~~~text
first=[1, 2, 3]
second=[]
~~~

**Vì sao?** Hai lời gọi `wrong.get()` đúng là tạo hai `Stream` khác nhau, nhưng cả hai dùng một `Iterator` đã bị tiêu thụ trong lượt đầu. `Iterator` không có API tự động quay về đầu.

Cách đúng khi nguồn là collection:

~~~java
// Minh họa: values là List<Integer> có thể duyệt lại.
Supplier<Stream<Integer>> correct = values::stream;
~~~

Nếu dữ liệu thực sự đi từ network socket, cursor hoặc nguồn chỉ đọc một lần, phải **mở lại nguồn theo hợp đồng của nó**, **materialize/cache dữ liệu** khi hợp lý, hoặc **thiết kế một phép xử lý duy nhất**. Supplier chỉ là cách đóng gói hành vi tạo stream, **không tạo ra khả năng replay khi nguồn không hỗ trợ**.

## 8. Nguồn tệp: mỗi lượt cần mở mới và đóng đúng cách

`Files.lines(Path, Charset)` trả `Stream<String>` đọc các dòng của tệp. Khác với `List.stream()`, stream này nắm giữ tài nguyên I/O; cần **đóng** sau khi xử lý. Một Supplier có thể mở một stream tệp mới cho từng lượt, nhưng vì `Supplier.get()` không khai báo checked exception, phải quy định cách xử lý `IOException`.

Tạo file `FileStreamFactoryDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class FileStreamFactoryDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("stream-factory-", ".txt");
        try {
            Files.write(path, List.of("An", "Bình", "Chi"),
                    StandardCharsets.UTF_8);

            Supplier<Stream<String>> lines = () -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            };

            try (Stream<String> first = lines.get()) {
                long count = first.filter(s -> s.length() >= 3).count();
                System.out.println("count=" + count);
            }

            try (Stream<String> second = lines.get()) {
                System.out.println("lines=" + second.toList());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

~~~bash
javac --release 17 FileStreamFactoryDemo.java
java FileStreamFactoryDemo
~~~

Kết quả:

~~~text
count=2
lines=[An, Bình, Chi]
~~~

Giải thích:

1. `Files.write(...)` tạo nội dung xác định, không cần tệp ngoài do người học chuẩn bị.
2. Mỗi `lines.get()` gọi lại `Files.lines` và mở **một luồng đọc mới**.
3. `try (Stream<String> first = ...)` bảo đảm gọi `close()` kể cả khi terminal operation ném lỗi.
4. `UncheckedIOException` bọc lỗi checked `IOException` xảy ra tại bước mở, vì `Supplier.get()` không khai báo `throws IOException`.
5. `finally` xóa tệp tạm sau khi hai stream đã đóng; bản chạy thành công in đúng hai dòng trên.

**Lưu ý:** lỗi đọc tệp trong quá trình tiêu thụ cũng có thể xuất hiện dưới dạng `UncheckedIOException`. Đường dẫn/tệp có thể thay đổi hoặc bị xóa giữa các lần `get()`, nên kết quả không đương nhiên giống nhau. Việc mở nhiều lần có chi phí I/O; không nên làm như vậy tùy tiện với tệp cực lớn.

**Không** viết `Stream<String> s = Files.lines(path)` một lần và dùng lại `s` sau `close()`: stream đã đóng không còn được dùng. Không mặc định rằng đóng terminal operation như `count()` tự đóng resource stream; chính `try-with-resources` hoặc trách nhiệm đóng rõ ràng mới xử lý phần tài nguyên cần đóng.

## 9. Nguồn chỉ đọc một lần: các phương án thay thế

Một số nguồn có bản chất *one-shot* hoặc tốn chi phí để tái mở:

- `Iterator` đã tiến đến cuối;
- `BufferedReader.lines()` gắn với cùng reader;
- dữ liệu từ socket hoặc một API streaming một lượt;
- một database cursor hoặc `ResultSet` đang mở;
- nguồn đọc tệp từ vị trí/offset đã dịch chuyển mà không hỗ trợ reset.

Một factory `Supplier<Stream<T>>` chỉ đúng nếu nó **tạo lại được nguồn thích hợp** ở mỗi lần `get()`, hoặc làm rõ rằng mỗi lần có **dữ liệu mới** chứ không phải cùng snapshot.

| Nhu cầu | Lựa chọn thường phù hợp | Đánh đổi |
| --- | --- | --- |
| Nguồn là collection nhỏ, có thể duyệt lại | Gọi `collection.stream()` mỗi lượt | Đơn giản, không phải cache thêm; dữ liệu có thể đổi nếu collection mutable. |
| Muốn dùng lại logic `filter/map` | `Supplier<Stream<T>>` tạo pipeline mới | Cần bảo đảm mỗi `get()` thực sự tạo stream từ nguồn hợp lệ. |
| Nguồn I/O có thể mở lại | Supplier mở lại và caller đóng từng stream | Có chi phí mở/đọc nhiều lần; lỗi I/O và snapshot phải được xử lý. |
| Nguồn one-shot, dữ liệu vừa bộ nhớ | Thu thành collection một lần rồi lấy `list.stream()` | Tốn bộ nhớ; cần xét tính cập nhật và dữ liệu nhạy cảm. |
| Nguồn one-shot, không thể cache | Tổng hợp nhiều kết quả trong **một lượt** | Có thể dùng custom collector, `teeing` hoặc pipeline xử lý tổng hợp. |
| Muốn kết quả giữa các lượt giống hệt | Tạo snapshot bất biến hoặc dữ liệu versioned | Phải quy định thời điểm snapshot và mức chi phí. |

**Không nhầm `supplier.get()` với “restart” của nguồn I/O**. Tạo một `Stream` mới trên cùng cursor đã tiêu thụ có thể trả rỗng hoặc sai nội dung. Mở lại một database query có thể trả dữ liệu **mới** nếu database thay đổi; nếu yêu cầu cùng snapshot thì cần chiến lược nhất quán dữ liệu phù hợp.

## 10. Cache dữ liệu khi phù hợp: `toList()` và stream mới

Nếu nguồn có thể đọc một lần và tập dữ liệu đủ nhỏ để đưa vào bộ nhớ, có thể materialize thành danh sách:

~~~java
// Minh họa: original là Stream<String> one-shot, không chứa null
List<String> snapshot = original.toList();

long count = snapshot.stream().count();
List<String> sorted = snapshot.stream().sorted().toList();
~~~

`Stream.toList()` trả danh sách không hỗ trợ sửa qua `add/remove`, nhưng **không deep-copy các đối tượng mutable** chứa bên trong. Để có snapshot nội dung thực sự bất biến, cần thiết kế dữ liệu phần tử bất biến hoặc copy phù hợp.

Nếu nguồn chứa đối tượng mutable và bị sửa giữa hai lần đọc, hai pipeline trên cùng `List` vẫn có thể quan sát dữ liệu khác. Nếu nguồn lớn hoặc vô hạn, không nên dùng `toList()` vô điều kiện vì có thể tiêu tốn bộ nhớ hoặc không kết thúc.

Tạo file `SnapshotAndStreamsDemo.java`:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class SnapshotAndStreamsDemo {
    public static void main(String[] args) {
        Stream<Integer> once = Stream.of(9, 2, 7);

        List<Integer> snapshot = once.toList();

        System.out.println("count=" + snapshot.stream().count());
        System.out.println("ascending="
                + snapshot.stream().sorted().toList());
        System.out.println("maximum="
                + snapshot.stream()
                        .max(Comparator.naturalOrder())
                        .orElseThrow());
    }
}
~~~

~~~bash
javac --release 17 SnapshotAndStreamsDemo.java
java SnapshotAndStreamsDemo
~~~

Kết quả:

~~~text
count=3
ascending=[2, 7, 9]
maximum=9
~~~

Stream `once` đã được tiêu thụ **một lần** để tạo `snapshot`; ba lần xử lý tiếp theo tạo stream mới từ danh sách, không “hồi sinh” `once`.

## 11. Tránh đọc nguồn nhiều lần khi một lượt đã đủ

Đôi khi bạn không cần `Supplier` vì các kết quả có thể được tính trong **một lần collect**.

Ví dụ: thay vì `stream.count()` rồi chạy lại stream để tính tổng độ dài chuỗi, với Java 12+ có thể dùng `Collectors.teeing`:

Tạo file `OnePassTeeingDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class OnePassTeeingDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");

        String report = names.stream().collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(s -> s.length()),
                (count, total) ->
                        "count=" + count + ", totalLength=" + total));

        System.out.println(report);
    }
}
~~~

~~~bash
javac --release 17 OnePassTeeingDemo.java
java OnePassTeeingDemo
~~~

Kết quả:

~~~text
count=3, totalLength=9
~~~

`teeing` nhận hai collector và một hàm ghép kết quả, vì vậy không cần tạo nhiều stream độc lập chỉ để thu hai chỉ số. Tương tự, `IntStream.summaryStatistics()` hoặc `Collectors.summarizingInt(...)` có thể tính count, sum, min, max và average trên một lượt.

Cần phân biệt:

- **Hai truy vấn độc lập ở hai thời điểm**: factory stream mới là lựa chọn tự nhiên nếu nguồn replayable.
- **Hai số liệu trên cùng lần duyệt nguồn**: collector tổng hợp là lựa chọn tốt khi nguồn one-shot hoặc chi phí đọc lại cao.
- **Các truy vấn cần cùng snapshot**: materialize hoặc đảm bảo phiên bản dữ liệu nhất quán, không mặc định hai lần mở stream tương đương.

## 12. `Supplier<Stream<T>>` không phải `Stream.generate(Supplier<T>)`

Hai API đều có chữ `Supplier` nhưng **vai trò hoàn toàn khác**:

~~~java
// Stream factory: mỗi get tạo một Stream mới.
Supplier<Stream<Integer>> factory =
        () -> Stream.of(1, 2, 3);

// Supplier tạo từng PHẦN TỬ:
Stream<Integer> generated =
        Stream.generate(() -> 7);
~~~

Trong trường hợp đầu, `factory.get()` trả `Stream<Integer>` để bạn tiêu thụ độc lập; có thể gọi `get()` nhiều lần.

Trong trường hợp sau, `Stream.generate(() -> 7)` trả **một Stream có thể không hữu hạn**, phát ra các phần tử số 7 khi terminal operation yêu cầu. Bản thân `generated` vẫn là **một stream dùng một lần**.

Nếu truyền nhầm một `Supplier<Stream<Integer>>` cho `Stream.generate`, kết quả sẽ có kiểu `Stream<Stream<Integer>>`, chứ không tự động trở thành cơ chế chạy lại pipeline hay trải phẳng dữ liệu.

`Supplier` dùng trong `Collector.supplier()` lại có vai trò khác nữa: tạo **container tích lũy** như `ArrayList`, không phải tạo lại stream nguồn. Đọc kiểu generic đầy đủ để tránh nhầm các thuật ngữ giống nhau.

## 13. Source mutable: mỗi Stream mới có thể thấy phiên bản dữ liệu khác

`Supplier<Stream<T>>` thường **capture tham chiếu tới collection**, không tạo snapshot. Hai lần gọi `get()` có thể cho kết quả khác nhau nếu collection thay đổi giữa hai lượt.

Tạo file `ChangingSourceDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class ChangingSourceDemo {
    public static void main(String[] args) {
        ArrayList<String> names =
                new ArrayList<>(List.of("An", "Bình"));

        Supplier<Stream<String>> factory = names::stream;

        System.out.println("first=" + factory.get().toList());

        names.add("Chi"); // Thay đổi GIỮA hai lần xử lý.

        System.out.println("second=" + factory.get().toList());
    }
}
~~~

~~~bash
javac --release 17 ChangingSourceDemo.java
java ChangingSourceDemo
~~~

Kết quả:

~~~text
first=[An, Bình]
second=[An, Bình, Chi]
~~~

Trường hợp trên hợp lệ vì thay đổi xảy ra **sau khi stream thứ nhất kết thúc, trước khi tạo/tiêu thụ stream thứ hai**. Ngược lại, không nên sửa một `ArrayList` đang được stream duyệt; điều đó có thể gây kết quả không dự đoán được hoặc `ConcurrentModificationException`.

Đừng hiểu “mỗi `get()` là một Stream mới” thành “mỗi `get()` đọc đúng cùng một dữ liệu”. Nếu cần lặp lại trên dữ liệu bất biến, dùng `List.copyOf`, các kiểu phần tử bất biến và quy tắc snapshot thích hợp (chú ý `List.copyOf` không chấp nhận phần tử null).

## 14. Thread-safety và parallel Stream

Có hai tình huống khác nhau:

1. **Một stream dùng `.parallel()`**: framework chia việc thực thi một pipeline ra nhiều luồng; các hàm intermediate/terminal phải phù hợp quy tắc stateless, non-interfering và an toàn với cơ chế xử lý song song.
2. **Nhiều luồng đồng thời gọi `factory.get()`**: mỗi lời gọi cần tạo một pipeline độc lập, nhưng **nguồn** mà chúng cùng đọc cũng phải có chính sách truy cập đồng thời phù hợp.

Một factory như `() -> sharedList.stream()` tạo pipeline mới, nhưng **không tự làm `ArrayList` thread-safe** khi thread khác đang sửa danh sách. Với nguồn chỉ đọc bất biến, việc tạo các stream độc lập thường dễ kiểm soát hơn; với nguồn mutable, cần chiến lược đồng bộ/snapshot hoặc loại collection phù hợp.

Không dùng side effect ngoài luồng trong `filter`, `map` hoặc terminal operation như thể mỗi stream mới bảo đảm thứ tự hay số lần gọi callback. Stream có tối ưu hóa, short-circuit và nhiều phương pháp thực thi; việc tạo một stream mới không biến side effect thành hợp đồng đáng tin cậy.

Nếu factory gọi tới nguồn bên ngoài có state, dùng chung một cursor/reader giữa nhiều thread còn có thể nguy hiểm hơn: mỗi `get()` phải mở **đúng tài nguyên độc lập** hoặc hệ thống cần quy định rõ điều phối truy cập.

## 15. Khi nào nên dùng method reference, lambda, cache hoặc một lượt?

| Tình huống | Phương án nên cân nhắc |
| --- | --- |
| Một vài truy vấn rõ ràng từ `List<T>` | Viết `list.stream()` trực tiếp ở từng truy vấn để code đơn giản. |
| Cùng một pipeline `filter/map` được gọi nhiều lần | `Supplier<Stream<R>>` trả pipeline mới mỗi lần `get()`. |
| API nhận factory để tùy chọn terminal operation | Truyền `Supplier<Stream<T>>` hoặc một abstraction truy vấn rõ hợp đồng; xác định trách nhiệm đóng resource. |
| Nguồn I/O có thể mở lại | Supplier mở Stream mới, mỗi caller dùng `try-with-resources`. |
| Nguồn one-shot và kết quả nhỏ | Materialize thành `List`, rồi tạo stream mới từ list; cân nhắc bộ nhớ. |
| Nguồn one-shot cần hai chỉ số cùng lượt | Dùng `teeing`, `summarizing...`, custom collector hoặc xử lý tuần tự một lần. |
| Kết quả phải hoàn toàn nhất quán giữa các lượt | Snapshot bất biến, transaction snapshot hoặc cơ chế versioning phù hợp. |

Một **thiết kế API** cần phân biệt `Stream<T>` với `Supplier<Stream<T>>`:

~~~java
// Nhận một Stream: thường chỉ nên tiêu thụ đúng một lần.
static long countMatches(Stream<String> source) {
    return source.filter(s -> s.length() >= 3).count();
}

// Nhận factory: có thể tạo hai pipeline độc lập, nếu factory hợp lệ.
static String analyze(Supplier<Stream<String>> sourceFactory) {
    long count = sourceFactory.get().count();
    String first = sourceFactory.get()
            .sorted()
            .findFirst()
            .orElse("(empty)");
    return "count=" + count + ", first=" + first;
}
~~~

Đoạn này minh họa phương thức tĩnh trong lớp đã import `Stream` và `Supplier`. Nếu `sourceFactory` tạo stream nắm giữ tài nguyên, cách `analyze` trên **chưa quản lý đóng nguồn**; cần thay đổi thiết kế/cài đặt để đóng từng stream bằng `try-with-resources` và ghi rõ ownership. Không áp dụng nguyên xi cho tài nguyên I/O.

## 16. Lỗi thường gặp và cách sửa

1. **Dùng lại cùng Stream sau terminal operation:** tạo stream mới từ nguồn; không gọi lại `count()`, `toList()` trên đối tượng cũ.
2. **Viết supplier trả Stream đã cache:** `() -> stream` không làm Stream mới; dùng `() -> source.stream()` hoặc `source::stream`.
3. **Tạo Stream mới nhưng dùng cùng Iterator/cursor:** vẫn không replay dữ liệu; tạo iterator/nguồn mới hoặc cache dữ liệu.
4. **Gọi `factory.get()` một lần rồi tái sử dụng biến:** phải gọi `get()` cho từng lần xử lý độc lập.
5. **Tưởng `Supplier` bảo đảm kết quả giống nhau:** source mutable/I/O có thể thay đổi giữa các lượt.
6. **Quên đóng `Files.lines`:** dùng `try-with-resources` cho mỗi stream giữ tài nguyên I/O.
7. **Nhầm terminal operation tự đóng Stream:** tiêu thụ không đồng nghĩa giải phóng tài nguyên theo hợp đồng `AutoCloseable`; cần đóng tường minh khi phù hợp.
8. **Dùng Stream rỗng nhiều lần:** Stream rỗng cũng dùng một lần; phải gọi `Stream.empty()` mới khi cần.
9. **Dùng `Stream.generate` thay factory:** `generate` tạo từng phần tử trong một stream, không cấp pipeline để gọi terminal nhiều lần.
10. **Gọi `count()` để kiểm tra dữ liệu rồi dùng lại stream:** `count()` đã tiêu thụ stream; dùng collection `isEmpty()` nếu có, hoặc xử lý một lượt.
11. **Cache bằng `toList()` trên dữ liệu cực lớn/vô hạn:** có thể hết bộ nhớ hoặc không kết thúc.
12. **Trộn logic I/O với `Supplier.get()` mà bỏ qua ngoại lệ:** nguồn tệp có checked `IOException`; quy định cách bọc/xử lý lỗi và đóng stream.
13. **Mặc định stream mới luôn có thứ tự:** nguồn unordered như `HashSet` không có encounter order xác định.
14. **Thay đổi collection nguồn trong lúc terminal operation duyệt:** có thể vi phạm non-interference và gây lỗi/khác kết quả.
15. **Chạy nhiều lần pipeline có side effect và mong hiệu ứng chỉ xảy ra một lần:** mỗi lần dùng factory sẽ có một lần xử lý mới, side effect có thể lặp.
16. **Cho rằng parallel stream giải quyết nguồn one-shot:** parallel chỉ là chiến lược thực thi, không tạo khả năng đọc lại nguồn đã tiêu thụ.

## 17. Checklist trước khi thiết kế xử lý nhiều lần

- Đối tượng tôi đang giữ là **nguồn `Collection`** hay **một `Stream` đã tạo**?
- Terminal operation nào đã dùng Stream hiện tại? Có đang gắn thêm phép xử lý lên Stream cũ không?
- Nếu dùng `Supplier<Stream<T>>`, mỗi `get()` có tạo **Stream mới thực sự**?
- Nguồn phía sau Stream có cho duyệt lại không, hay chỉ là một Iterator/reader/cursor dùng một lần?
- Dữ liệu có thể thay đổi giữa các lượt? Có yêu cầu snapshot hay kết quả giống nhau không?
- Stream có mở tài nguyên không? Ai chịu trách nhiệm đóng từng lần `get()`?
- Có nguy cơ `IOException`, `UncheckedIOException` hoặc tài nguyên bị đóng/xóa giữa các lượt?
- Nếu chỉ cần nhiều số liệu trong một lượt, một collector tổng hợp có rõ ràng/tiết kiệm hơn không?
- Có gọi factory đồng thời từ nhiều thread hoặc chạy parallel trên nguồn mutable không?
- Dữ liệu có lớn hoặc vô hạn khiến việc materialize thành List không hợp lý không?

**Ghi nhớ:** **Stream là pipeline dùng một lần; nguồn có thể là nơi tạo nhiều Stream mới** nếu hỗ trợ đọc lặp. Dùng `source.stream()` cho truy vấn độc lập đơn giản, hoặc `Supplier<Stream<T>>` để đóng gói việc tạo pipeline mới. Supplier không tự reset Iterator, không biến I/O thành replayable, không cache snapshot và không thay thế trách nhiệm đóng tài nguyên.
