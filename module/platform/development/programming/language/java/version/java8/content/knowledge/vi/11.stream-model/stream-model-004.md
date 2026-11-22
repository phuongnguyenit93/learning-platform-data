# Stream dùng một lần và tạo lại từ nguồn trong Java

## Mục tiêu học tập

**Java Stream** là một pipeline mô tả cách xử lý các phần tử từ một nguồn dữ liệu. Một đối tượng **Stream** được thiết kế để **sử dụng một lần**: sau khi pipeline đã được tiêu thụ bằng terminal operation, hoặc đã bị đóng, bạn không thể coi chính đối tượng Stream đó như một danh sách để duyệt lại. Nếu cần xử lý nhiều lần, hãy **tạo Stream mới từ nguồn có thể duyệt lại**, hoặc tạo một **factory** cung cấp Stream mới cho từng lượt.

Sau bài học, bạn có thể:

- Giải thích **source**, **intermediate operation** và **terminal operation** trong pipeline.
- Phân biệt **tạo một Stream mới** với **gọi lại một Stream đã tiêu thụ**.
- Hiểu tại sao **IllegalStateException** có thể xuất hiện khi dùng lại Stream, nhưng không dựa vào việc exception luôn phát hiện mọi sai phạm.
- Tạo nhiều pipeline độc lập từ **Collection**, mảng, giá trị cố định hoặc một factory **Supplier<Stream<T>>**.
- Phân biệt **nguồn có thể duyệt lại** và **nguồn một lượt** như iterator, một reader đã đọc hết hoặc một resource stream.
- Dùng **try-with-resources** cho Stream giữ tài nguyên, đặc biệt với **Files.lines(...)**.
- Tránh chia nhánh một Stream thành nhiều pipeline, tránh các side effect không an toàn và hiểu tác động của việc thay đổi nguồn.
- Chọn khi nào nên chạy nhiều lượt, khi nào nên thu thập kết quả một lượt để tái sử dụng.

Kiến thức này đã có từ Java 8 và vẫn còn áp dụng trong Java hiện đại (bao gồm JDK 17+). Các chương trình hoàn chỉnh sử dụng API Java 8-compatible để bạn có thể biên dịch và chạy trên JDK 8 trở lên.

## 1. Stream không phải một bộ sưu tập lưu dữ liệu

Một **List** chứa các phần tử có thể được duyệt nhiều lần. Một **Stream** thì khác: nó đại diện cho **chuỗi thao tác xử lý dữ liệu từ một nguồn**, không nhất thiết lưu sẵn tất cả phần tử.

Ví dụ:

~~~java
List<String> names = Arrays.asList("An", "Binh", "Chi");

long count = names.stream()
    .filter(name -> name.length() >= 3)
    .count();
~~~

Đây là đoạn minh họa cần import **java.util.List**, **java.util.Arrays** và đặt trong một phương thức. **names** là List; **names.stream()** tạo một đối tượng Stream mới. **filter(...)** là intermediate operation, còn **count()** là terminal operation. Kết quả count là **2**, tương ứng "Binh" và "Chi".

Nếu muốn xử lý lại chính List, hãy gọi **names.stream()** lần nữa:

~~~java
long countAgain = names.stream()
    .filter(name -> name.length() >= 3)
    .count();
~~~

Hai lượt này không dùng lại cùng một Stream. Chúng sử dụng **hai đối tượng Stream khác nhau**, mỗi đối tượng nhận dữ liệu từ **cùng List nguồn**.

**Điểm cốt lõi:** một nguồn có thể được dùng để tạo nhiều Stream, nhưng điều đó không có nghĩa **một Stream** được tiêu thụ nhiều lần.

## 2. Source – intermediate – terminal: nơi một lượt xử lý diễn ra

Một pipeline điển hình:

~~~text
List<String> names
       |
       | names.stream()        <-- tạo Stream mới
       v
filter(name -> name.length() >= 3)
       |
       |                        <-- intermediate: tạo pipeline mới, thường lazy
       v
map(String::toUpperCase)
       |
       v
collect(toList())             <-- terminal: tiêu thụ pipeline
       |
       v
[BINH, CHI]                  <-- kết quả được lưu trong List mới
~~~

Ba phần đóng vai trò khác nhau:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Source** | List, mảng, generator, tệp | Cung cấp dữ liệu để pipeline xử lý |
| **Intermediate operation** | filter, map, sorted, limit | Xây dựng/biến đổi pipeline; thường lazy |
| **Terminal operation** | count, collect, forEach, reduce, findFirst | Khởi chạy việc xử lý để sinh kết quả hoặc side effect |

**Intermediate operation thường không duyệt dữ liệu ngay.** Khi viết **stream.filter(...)**, bạn đang tạo một giai đoạn của pipeline; phần xử lý thực sự thường diễn ra khi terminal operation được gọi.

**Terminal operation kết thúc lượt sử dụng của pipeline.** Sau **collect(...)**, **count()**, **findFirst()**, v.v., đối tượng Stream đã tham gia pipeline không còn là thứ được phép dùng để khởi chạy một lượt duyệt mới.

Một số terminal operation **short-circuit**: **findFirst()**, **anyMatch()**, **noneMatch()** có thể không duyệt mọi phần tử. Điều này không làm Stream trở nên “chưa dùng hết nên tái sử dụng được”. Nó đã được tiêu thụ theo hợp đồng của stream API.

## 3. Ví dụ sai: gọi terminal operation hai lần trên cùng Stream

Xem đoạn mã sau:

~~~java
Stream<String> stream = names.stream();
long count = stream.count();
long secondCount = stream.count();  // Sai: dùng lại Stream.
~~~

Đây là đoạn minh họa; cần khai báo names và import Stream. Sau lời gọi **count()** đầu tiên, **stream** không còn được sử dụng cho một terminal operation khác.

Trên những Stream implementation thông dụng trong JDK, lần gọi thứ hai thường ném:

~~~text
java.lang.IllegalStateException: stream has already been operated upon or closed
~~~

**Không nên dựa vào chính xác thông báo exception** như một hợp đồng ổn định. Hơn nữa, Java Stream API nêu rõ việc **một Stream chỉ được vận hành một lần**; implementation có thể phát hiện dùng lại và ném IllegalStateException, nhưng **không bảo đảm mọi kiểu dùng sai đều được phát hiện**. Vì vậy:

- Nếu lần dùng lại báo lỗi: sửa thiết kế.
- Nếu một trường hợp dùng lại không báo lỗi: **không kết luận rằng hợp lệ**.
- Không dùng try/catch IllegalStateException làm cách “reset” Stream.
- Không mong Stream có hàm **reset()**, **rewind()** hoặc **restart()**.

Cách đúng:

~~~java
long firstCount = names.stream().count();
long secondCount = names.stream().count();
~~~

Hai lượt count sử dụng **hai Stream độc lập**. Nếu List không thay đổi giữa các lượt, kết quả có thể như nhau.

## 4. Chương trình hoàn chỉnh: minh họa lỗi và cách tạo mới

Tạo tệp **StreamSingleUseDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamSingleUseDemo {

    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi");

        Stream<String> selected = names.stream()
            .filter(name -> name.length() >= 3);

        System.out.println("First count: " + selected.count());

        try {
            selected.count();
        } catch (IllegalStateException ex) {
            System.out.println("Second use: IllegalStateException");
        }

        List<String> upper = names.stream()
            .map(String::toUpperCase)
            .collect(Collectors.toList());

        long freshCount = names.stream()
            .filter(name -> name.length() >= 3)
            .count();

        System.out.println("Upper: " + upper);
        System.out.println("Fresh count: " + freshCount);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamSingleUseDemo.java
java StreamSingleUseDemo
~~~

Đầu ra dự kiến trên các implementation Stream thông dụng của JDK:

~~~text
First count: 2
Second use: IllegalStateException
Upper: [AN, BINH, CHI]
Fresh count: 2
~~~

**Giải thích:**

1. **selected** có pipeline filter; **count()** đầu tiên tiêu thụ pipeline đó.
2. Lần gọi **selected.count()** thứ hai là sai quy tắc dùng Stream. Implementation của JDK phát hiện và ném IllegalStateException, nên chương trình in một thông báo do chính mã catch tạo ra, thay vì phụ thuộc vào text exception của JDK.
3. **names.stream()** ở phần tạo upper là Stream hoàn toàn mới; nó không gọi lại selected.
4. **names.stream()** ở phần freshCount cũng là Stream mới. Danh sách nguồn không thay đổi, nên số phần tử có độ dài từ 3 trở lên vẫn là 2.
5. **upper** là List đã được thu thập bằng collect; khác với Stream, List kết quả có thể được duyệt lại nhiều lần theo hợp đồng Collection.

Đừng hiểu ví dụ exception như một thủ thuật để kiểm tra khả năng tái sử dụng. Cách viết đúng phải được bảo đảm bằng cấu trúc chương trình, không dựa vào việc có exception ở runtime.

## 5. Một Stream không được “chia nhánh” thành hai pipeline độc lập

Một lỗi tinh vi khác:

~~~java
Stream<String> base = names.stream();

Stream<String> longer = base.filter(s -> s.length() >= 3);
Stream<String> upper = base.map(String::toUpperCase); // Sai.
~~~

Đây là đoạn minh họa, cần khai báo names. Lỗi không nhất thiết phải đợi terminal operation. Việc gọi một intermediate operation trên Stream **cũng là một lần vận hành Stream** và có thể liên kết nó vào pipeline. Khi đã tạo nhánh **longer** từ base, việc tiếp tục dùng **base** để tạo nhánh khác không phải mô hình hợp lệ.

Đúng hơn:

~~~java
Stream<String> longer = names.stream()
    .filter(s -> s.length() >= 3);

Stream<String> upper = names.stream()
    .map(String::toUpperCase);
~~~

Mỗi pipeline có **đầu vào Stream mới**. Chỉ cần nhớ phải **tiêu thụ mỗi pipeline tối đa một lần**. Với những Stream giữ tài nguyên, cần thêm chính sách đóng tài nguyên, sẽ bàn ở phần sau.

### Tại sao API không cho fork trực tiếp một Stream?

Một pipeline có thể đọc từ nguồn tiến dần, phát sinh side effect hoặc tiêu thụ I/O. Nếu hai nhánh cùng chia sẻ một cursor/trạng thái nguồn, hành vi có thể khó dự đoán. Stream API không đặt mục tiêu cung cấp cơ chế fork/replay của một luồng dữ liệu.

Nếu cần nhiều phép tính:

- Tạo hai Stream từ **nguồn có thể duyệt lại**.
- Hoặc tính nhiều thống kê **trong một terminal operation**.
- Hoặc **materialize** dữ liệu thành một Collection rồi tạo Stream mới trên Collection ấy.

Chọn cách nào phụ thuộc chi phí duyệt nguồn, bộ nhớ và ràng buộc về tính mới của dữ liệu.

## 6. Nguồn Collection có thể tạo Stream mới nhiều lần

Với Collection, cách đơn giản nhất:

~~~java
List<Integer> values = Arrays.asList(3, 7, 5);

long count = values.stream().count();

int total = values.stream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

Các đoạn này là minh họa. **count = 3**, **total = 15**. Hai lời gọi **values.stream()** tạo hai pipeline mới trên cùng Collection.

Các nguồn có thể dùng lại điển hình:

| Nguồn | Cách tạo Stream mới |
| --- | --- |
| **List<T>** | list.stream() |
| **Set<T>** | set.stream() |
| **Collection<T>** | collection.stream() |
| **T[]** | Arrays.stream(array) |
| **int[]**, **long[]**, **double[]** | Arrays.stream(primitiveArray) |
| Các giá trị cố định | Stream.of(value1, value2, ...) mỗi lần |
| Khoảng số | IntStream.range(start, end) mỗi lần |
| Dãy tính lại được | Stream.iterate(...) hoặc Stream.generate(...) với supplier/state mới khi cần |

**Cảnh báo:** “có thể tạo Stream mới” không đồng nghĩa “kết quả luôn giống nhau”. Nếu nguồn là **List mutable** và đã thay đổi giữa hai lượt, Stream mới có thể nhìn thấy dữ liệu mới. Với Set không có thứ tự duyệt được bảo đảm, thứ tự phần tử có thể khác kỳ vọng. Với dữ liệu ngoài, nguồn có thể thay đổi theo thời gian.

Đồng thời, không được sửa Collection một cách không được hỗ trợ **trong khi pipeline đang duyệt nó**. Điều này có thể gây ConcurrentModificationException hoặc hành vi không được bảo đảm tùy nguồn và thao tác. Hãy phân biệt **sửa giữa hai lượt** với **sửa trong lúc một lượt duyệt đang chạy**.

## 7. Supplier<Stream<T>>: factory tạo pipeline mới

Khi một phương thức cần thực hiện nhiều lượt phân tích, bạn có thể truyền vào một **Supplier<Stream<T>>** thay vì chính một Stream.

Không nên viết:

~~~java
Stream<String> stream = names.stream();
Supplier<Stream<String>> bad = () -> stream;
~~~

Đây là đoạn minh họa. **bad.get()** chỉ trả lại **cùng một đối tượng Stream** lần nào cũng vậy. Supplier không tự làm Stream mới, nên thiết kế này vẫn vi phạm quy tắc dùng một lần.

Cách đúng là đưa **lệnh tạo Stream** vào thân supplier:

~~~java
Supplier<Stream<String>> fresh = () -> names.stream();
~~~

Mỗi lần **fresh.get()** thực thi lambda và gọi **names.stream()** mới. Mỗi đối tượng Stream được nhận về chỉ được tiêu thụ một lần.

Bạn cũng có thể xây pipeline trong factory:

~~~java
Supplier<Stream<String>> selected = () ->
    names.stream().filter(s -> s.length() >= 3);
~~~

Bây giờ **selected.get().count()** và **selected.get().map(...).collect(...)** dùng hai pipeline độc lập.

**Từ khóa quan trọng:** factory phải tạo **mới**. Chỉ việc bọc một reference cũ vào Supplier không đủ.

## 8. Chương trình hoàn chỉnh: factory và nguồn thay đổi giữa các lượt

Tạo tệp **StreamFactoryDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamFactoryDemo {

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(
            Arrays.asList("An", "Binh", "Chi"));

        Supplier<Stream<String>> fresh = () ->
            names.stream().filter(name -> name.length() >= 3);

        System.out.println("Count: " + fresh.get().count());

        List<String> upper = fresh.get()
            .map(String::toUpperCase)
            .collect(Collectors.toList());

        System.out.println("Upper: " + upper);

        names.add("Dung");

        System.out.println(
            "Count after add: " + fresh.get().count());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamFactoryDemo.java
java StreamFactoryDemo
~~~

Kết quả:

~~~text
Count: 2
Upper: [BINH, CHI]
Count after add: 3
~~~

**Phân tích:**

1. Trong **fresh**, biểu thức **names.stream()** được thực thi khi gọi get(), không phải khi tạo Supplier.
2. Lượt thứ nhất lọc và count trên một Stream mới.
3. Lượt thứ hai lại gọi fresh.get(), có Stream mới nên map/collect hợp lệ.
4. Khi thêm "Dung" **giữa các lượt đã kết thúc**, factory tiếp theo nhìn vào List mới và nhận thêm một phần tử đủ điều kiện. Kết quả count tăng từ 2 lên 3.
5. Supplier giữ **reference tới List names**, không tự sao chép nội dung List. Nếu cần mỗi lượt nhìn một snapshot cố định, phải tạo snapshot có chủ đích.

### Thiết kế API nhận Supplier

Có thể định nghĩa một API đơn giản:

~~~java
static long countLongNames(
        java.util.function.Supplier<
            java.util.stream.Stream<String>> factory) {
    return factory.get()
        .filter(name -> name.length() >= 4)
        .count();
}
~~~

Đây là phương thức minh họa cần đặt trong một lớp. Bên gọi có thể viết **countLongNames(() -> names.stream())**. Nhưng nếu nguồn là tệp hoặc tài nguyên cần đóng, cách API này tiêu thụ Stream có thể phải thêm **try-with-resources**, không nên mặc định supplier luôn cho dữ liệu in-memory.

Để tránh lỗi, hãy ghi trong hợp đồng rằng **mỗi lần get() phải trả một Stream mới**, không được trả lại Stream cũ hoặc một Stream đã đóng.

## 9. Đừng nhầm một Stream mới với dữ liệu luôn được reset

Đặc biệt với **Stream.generate(Supplier<T>)**, một factory Stream có thể tạo object Stream mới nhưng lại dùng **cùng trạng thái generator**.

Ví dụ:

~~~java
AtomicInteger counter = new AtomicInteger();

Supplier<Stream<Integer>> streams = () ->
    Stream.generate(counter::incrementAndGet).limit(3);
~~~

Đây là đoạn minh họa, cần import java.util.concurrent.atomic.AtomicInteger, java.util.function.Supplier và java.util.stream.Stream. Mỗi **streams.get()** tạo một Stream mới, nhưng hai Stream cùng tham chiếu tới **counter**.

- Lượt đầu có thể cho **[1, 2, 3]**.
- Lượt thứ hai có thể cho **[4, 5, 6]**.

Cả hai lượt đều hợp lệ về **single-use Stream**, nhưng dữ liệu không reset.

Muốn mỗi lượt có trạng thái độc lập, tạo **AtomicInteger mới bên trong factory**. Ví dụ hoàn chỉnh:

~~~java
Supplier<Stream<Integer>> restarting = () -> {
    AtomicInteger local = new AtomicInteger();
    return Stream.generate(local::incrementAndGet).limit(3);
};
~~~

Bây giờ mỗi lần **restarting.get()** vừa có Stream mới, vừa có generator state mới.

**Phân biệt hai khái niệm:**

- **Fresh stream**: đối tượng Stream mới chưa được tiêu thụ.
- **Fresh data/state**: nguồn hoặc trạng thái tính toán cũng được tạo lại theo ý định.

Chỉ có fresh stream **không bảo đảm** dữ liệu đầu vào không đổi, độc lập hoặc bắt đầu từ đầu.

## 10. Chương trình hoàn chỉnh: supplier chia sẻ state và supplier reset state

Tạo tệp **StatefulSourceDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StatefulSourceDemo {

    static List<Integer> takeThree(Stream<Integer> stream) {
        return stream.collect(Collectors.toList());
    }

    public static void main(String[] args) {
        AtomicInteger shared = new AtomicInteger();

        Supplier<Stream<Integer>> sharing = () ->
            Stream.generate(shared::incrementAndGet).limit(3);

        Supplier<Stream<Integer>> resetting = () -> {
            AtomicInteger local = new AtomicInteger();
            return Stream.generate(local::incrementAndGet).limit(3);
        };

        System.out.println("Shared first: " +
            takeThree(sharing.get()));

        System.out.println("Shared second: " +
            takeThree(sharing.get()));

        System.out.println("Reset first: " +
            takeThree(resetting.get()));

        System.out.println("Reset second: " +
            takeThree(resetting.get()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StatefulSourceDemo.java
java StatefulSourceDemo
~~~

Kết quả trên đường xử lý tuần tự của ví dụ:

~~~text
Shared first: [1, 2, 3]
Shared second: [4, 5, 6]
Reset first: [1, 2, 3]
Reset second: [1, 2, 3]
~~~

Giải thích:

- **sharing.get()** tạo Stream mới mỗi lần nhưng vẫn sử dụng cùng **AtomicInteger shared**.
- **resetting.get()** tạo Stream mới và **AtomicInteger local** mới mỗi lần.
- Cả hai loại Stream chỉ dùng một lần; ở đây không có lỗi reused Stream.
- **limit(3)** chặn một Stream.generate vốn có thể vô hạn; nếu gọi một terminal operation đòi duyệt hết mà không giới hạn, xử lý có thể không kết thúc.
- Ví dụ chạy tuần tự. Khi đổi sang parallel stream hoặc logic generator có side effect, không nên mặc định thứ tự và số lần gọi side-effect giống mô hình này. Tránh stateful side effects nếu không cần thiết.

Bài học sâu hơn: **một factory dùng để tạo pipeline** khác với **một factory tái tạo chính nguồn dữ liệu và trạng thái**. Chọn loại nào tùy yêu cầu nghiệp vụ.

## 11. Stream từ Iterator hoặc Spliterator có thể là nguồn một lượt

Không phải nguồn nào cũng cho phép duyệt lại.

Ví dụ một **Iterator** thông thường tiến dần theo vị trí. Sau khi nó đã duyệt hết phần tử, việc bọc lại **cùng Iterator** vào một Stream mới thường không thể làm dữ liệu xuất hiện lại.

Ví dụ minh họa:

~~~java
Iterator<String> iterator = names.iterator();

Stream<String> once = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(
        iterator, Spliterator.ORDERED),
    false);
~~~

Cần import java.util.Iterator, java.util.Spliterator, java.util.Spliterators và java.util.stream.StreamSupport. **once** là Stream bọc một Iterator đã có.

Muốn duyệt lại List, hãy gọi **names.iterator() mới** hoặc đơn giản hơn **names.stream()**. Không tái sử dụng Iterator cũ và giả định nó reset.

Với một nguồn như message queue, socket, response body hoặc nguồn đọc tuần tự, có thể không có khái niệm “quay về đầu”. Bạn phải quyết định:

- Mở/đăng ký **nguồn mới** theo cơ chế của hệ thống, nếu nguồn hỗ trợ.
- **Lưu dữ liệu đã đọc** (materialize) nếu dung lượng và quyền truy cập cho phép.
- Thiết kế thuật toán **một lượt**, không đòi tái duyệt.

**Không phải mọi Stream factory đều thật sự tạo được dữ liệu mới** khi nguồn nền là một cursor chỉ đi tới. Cần đọc hợp đồng của nguồn, không suy luận từ việc đã tạo được một object Stream mới.

## 12. Stream từ file: tạo lại bằng cách mở lại tài nguyên

API **Files.lines(Path, Charset)** tạo một Stream các dòng văn bản đọc từ tệp. Stream này gắn với **tài nguyên I/O** cần được đóng.

Muốn đếm dòng rồi đọc một lần nữa, cách hợp lệ là **mở Stream mới từ Path** cho mỗi lượt:

~~~java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
}

try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    // Thao tác khác với Stream mới.
}
~~~

Đây là đoạn minh họa; cần import java.nio.file.Files, java.nio.file.Path, java.nio.charset.StandardCharsets và java.util.stream.Stream. Path chỉ là vị trí tệp; mỗi lần **Files.lines(...)** mở một nguồn đọc mới.

**Điểm cực kỳ quan trọng:** terminal operation như **count()** **không tự động đóng Stream**. Với Stream I/O, hãy dùng **try-with-resources** để gọi close ngay cả khi có exception.

Với Stream chỉ duyệt List in-memory, thông thường không cần close. Nhưng với Stream bọc tài nguyên, bỏ qua close có thể giữ file handle hoặc tài nguyên hệ thống lâu hơn mong muốn.

## 13. Chương trình hoàn chỉnh: đọc file hai lượt và đóng tài nguyên

Tạo tệp **FileStreamReplayDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FileStreamReplayDemo {

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile(
            "java-stream-replay-", ".txt");

        try {
            Files.write(path,
                Arrays.asList("alpha", "beta", "gamma"),
                StandardCharsets.UTF_8);

            long lineCount;

            try (Stream<String> lines =
                     Files.lines(path, StandardCharsets.UTF_8)) {
                lineCount = lines.count();
            }

            List<String> startingB;

            try (Stream<String> lines =
                     Files.lines(path, StandardCharsets.UTF_8)) {
                startingB = lines
                    .filter(line -> line.startsWith("b"))
                    .collect(Collectors.toList());
            }

            System.out.println("Lines: " + lineCount);
            System.out.println("Starts with b: " + startingB);
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FileStreamReplayDemo.java
java FileStreamReplayDemo
~~~

Kết quả:

~~~text
Lines: 3
Starts with b: [beta]
~~~

**Phân tích:**

1. Chương trình tạo một tệp tạm chứa đúng ba dòng.
2. Lượt đầu mở **Files.lines(...)** trong try-with-resources, gọi count() và kết thúc khối try. Resource được đóng ở cuối khối.
3. Lượt thứ hai gọi lại **Files.lines(...)**, tạo Stream mới và tài nguyên đọc mới, rồi lọc dòng bắt đầu bằng "b".
4. **finally** xóa tệp tạm ngay cả khi một phép xử lý thất bại, trong giới hạn quy tắc I/O của hệ điều hành.
5. Việc file được mở lại có thể đọc dữ liệu mới nếu file bị sửa giữa các lượt. Trong ví dụ file không bị thay đổi, nên kết quả xác định.

**Lưu ý về lỗi:** Files.lines có thể ném IOException khi mở nguồn; lỗi trong quá trình đọc/duyệt có thể được biểu diễn bằng exception thích hợp như UncheckedIOException theo API. Production code cần chính sách xử lý lỗi và bảo đảm đóng tài nguyên.

### Vì sao không tạo Supplier<Stream<String>> trực tiếp từ Files.lines?

**Supplier.get()** không khai báo checked exception. Trong khi đó **Files.lines(...)** có thể ném **IOException** khi mở tệp. Viết một lambda trực tiếp mà không xử lý ngoại lệ có thể không biên dịch.

Nếu muốn factory file stream, bạn có thể:

- Định nghĩa functional interface chuyên biệt với **throws IOException**.
- Xử lý IOException có chủ đích trong lambda, ví dụ chuyển thành UncheckedIOException khi hợp đồng ứng dụng cho phép.
- Hoặc đơn giản dùng một method mở Stream mới bên trong từng **try-with-resources**, thường rõ ràng hơn trong các thao tác I/O.

Dù chọn cách nào, bên tiêu thụ vẫn phải **đóng từng Stream** đã mở. Supplier không tự thực thi close.

## 14. close() và terminal operation: hai việc khác nhau

Stream có thể ở trạng thái đã được tiêu thụ bởi terminal operation mà chưa được gọi **close()**. Ngược lại, khi Stream đã đóng, nó không còn được sử dụng cho các thao tác pipeline mới.

Ví dụ:

~~~java
Stream<String> stream = Stream.of("A", "B");
long n = stream.count();
~~~

Sau count(), Stream đã được tiêu thụ. Việc gọi close() sau đó không giúp “reset”. Đối với Stream in-memory như Stream.of, việc đóng thường không cần thiết để giải phóng tài nguyên hệ thống.

Với resource stream, dùng:

~~~java
try (Stream<String> stream = openResourceStream()) {
    // Một terminal operation trên stream.
}
~~~

Đây là đoạn minh họa, giả định có phương thức **openResourceStream()** trả Stream và trách nhiệm đóng thuộc về caller.

**BaseStream.close()** giúp đóng một Stream và kích hoạt các close handlers được đăng ký bằng **onClose(...)**, theo các quy tắc API. Nhưng gọi close() không biến Stream thành reusable collection.

### Có thể dùng cùng Stream nhiều lần chỉ vì chưa close không?

Không. Tiêu thụ bằng terminal operation đã là một lượt sử dụng, bất kể bạn có gọi close hay chưa. **Không đóng** không đồng nghĩa **còn duyệt lại được**.

### Có thể chỉ close mà không terminal operation không?

Có thể tạo một Stream rồi đóng mà không thực hiện duyệt. Sau khi đã đóng, nó không được dùng như một Stream mới. Với resource stream, đóng sớm có thể là hành vi đúng nếu bạn quyết định hủy việc xử lý.

## 15. Materialize: thu dữ liệu thành List khi cần tái sử dụng

Nếu nguồn không thể mở lại, đôi khi cách tốt nhất là **đọc một lượt rồi lưu kết quả**:

~~~java
List<String> snapshot;

try (Stream<String> stream = openResourceStream()) {
    snapshot = stream.collect(Collectors.toList());
}
~~~

Đây là đoạn minh họa; cần có openResourceStream phù hợp. Sau khi đã có **snapshot** (List), bạn có thể tạo nhiều Stream từ **snapshot.stream()**, không cần mở lại nguồn gốc.

Ưu điểm:

- Không cần đọc lại nguồn I/O cho mỗi phép tính.
- Có thể dùng lại các phần tử đã được lưu.
- Có dữ liệu snapshot ở một thời điểm xử lý cụ thể (tùy bản chất phần tử).

Đổi lại:

- **Tốn bộ nhớ** tỷ lệ theo lượng dữ liệu thu thập; không phù hợp nếu dữ liệu vô hạn hoặc quá lớn.
- Collection snapshot có thể chỉ là **shallow copy**; phần tử mutable vẫn có thể thay đổi.
- Nếu nguồn dữ liệu thực sự cần cập nhật theo thời gian, snapshot có thể **cũ** so với nguồn hiện tại.
- Nếu nguồn có một lượng lớn dữ liệu, lựa chọn streaming một lượt thường tốt hơn.

**Trong Java 8**, dùng **collect(Collectors.toList())** để thu về List. API **Stream.toList()** được bổ sung trên JDK mới hơn (Java 16); vẫn là API hiện đại, nhưng không thể dùng trong chương trình phải biên dịch bằng JDK 8. Chúng cũng có khác biệt về khả năng sửa kết quả, nên đừng thay thế máy móc mà không kiểm tra hợp đồng.

## 16. Chạy nhiều phép tổng hợp chỉ trong một lượt

Đôi khi người dùng muốn **count, sum, min, max** từ cùng một nguồn số. Không nhất thiết tạo bốn Stream và duyệt bốn lần: có thể dùng **summaryStatistics()**.

Ví dụ:

~~~java
IntSummaryStatistics stats = values.stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();
~~~

Đây là đoạn minh họa, cần import java.util.IntSummaryStatistics và có List<Integer> values. **summaryStatistics()** là một terminal operation thực hiện thống kê trong một pipeline.

Một chương trình đầy đủ:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;

public class SinglePassStatisticsDemo {

    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(3, 7, 5);

        IntSummaryStatistics stats = values.stream()
            .mapToInt(Integer::intValue)
            .summaryStatistics();

        System.out.println("Count: " + stats.getCount());
        System.out.println("Sum: " + stats.getSum());
        System.out.println("Min: " + stats.getMin());
        System.out.println("Max: " + stats.getMax());
    }
}
~~~

Lưu tệp **SinglePassStatisticsDemo.java**, sau đó:

~~~bash
javac -encoding UTF-8 SinglePassStatisticsDemo.java
java SinglePassStatisticsDemo
~~~

Kết quả:

~~~text
Count: 3
Sum: 15
Min: 3
Max: 7
~~~

Một **terminal operation** đã tính nhiều kết quả bằng IntSummaryStatistics. Bạn không cần dùng lại Stream cũ để hỏi từng thống kê. Điều này phù hợp khi muốn giảm số lượt duyệt và có thể chấp nhận tất cả thống kê trên một snapshot xử lý.

Với nguồn số lớn, cách chọn primitive stream **mapToInt** cũng tránh boxing của từng kết quả số trong giai đoạn thống kê. Tuy nhiên, đừng tối ưu theo cảm tính; hãy ưu tiên độ rõ ràng và đo đạc hiệu năng thực tế.

## 17. Thứ tự, tính lazy và side effect khi tạo lại Stream

Mỗi Stream mới có thể thực hiện pipeline một lần, nhưng **thứ tự** và **số lần gọi lambda** không phải luôn là điều bạn được phép dự đoán từ cảm giác.

### Pipeline lazy không chạy khi mới khai báo

~~~java
Stream<String> pipeline = names.stream()
    .filter(name -> name.startsWith("A"));
~~~

Dòng trên chỉ mô tả pipeline. Việc lọc thường diễn ra khi terminal operation gọi tới. Đừng nhầm việc có một Stream chưa dùng với việc List dữ liệu đã được sao chép sẵn.

### Short-circuit và optimization

**findFirst()**, **anyMatch()**, **limit()** có thể ngăn việc xử lý tất cả phần tử. Một số implementation có thể tối ưu terminal operation dựa trên đặc tính nguồn/pipeline. Vì vậy **peek(...)** hoặc những side effects trong intermediate operations không phải cách đáng tin để xác nhận “mỗi phần tử đã được đi qua đúng một lần”.

Không nên dựa vào kiểu logic:

~~~java
// Minh họa lối suy nghĩ dễ sai:
// Stream.of(1, 2, 3).peek(System.out::println).count();
~~~

Dù một Stream chưa được tiêu thụ khi xây pipeline, không nên mặc định mọi biểu thức side-effect sẽ luôn chạy đủ ba lần cho mọi tối ưu và phiên bản JDK.

### Không sửa nguồn trong khi đang duyệt

Nếu source là ArrayList và bạn thêm phần tử trong lúc Stream đang xử lý, đó không phải cách “cập nhật dữ liệu Stream ở giữa lượt”. Nguồn/Stream có những quy tắc về **non-interference**; sửa nguồn không được hỗ trợ trong quá trình duyệt có thể gây lỗi hoặc kết quả khó đoán.

Đúng hơn là:

1. Hoàn thành pipeline thứ nhất.
2. Sửa List qua API được cho phép.
3. Tạo Stream mới.
4. Chạy pipeline thứ hai.

Đối với nguồn concurrent và các collector được thiết kế đặc biệt, quy tắc có thể khác, nhưng không nên mở rộng bài học single-use thành lời khuyên dùng side effect trên Stream tùy tiện.

## 18. Stream tuần tự và parallel đều dùng một lần

**Parallel stream** không phải một ngoại lệ:

~~~java
long count = names.parallelStream()
    .filter(s -> s.length() >= 3)
    .count();
~~~

Đây là đoạn minh họa. Stream parallel vẫn được tiêu thụ một lần và không được dùng lại. Nếu cần lượt parallel tiếp theo, gọi **names.parallelStream()** mới hoặc xây factory mới.

Thay đổi giữa **sequential()** và **parallel()** trên một Stream cũng không phải hành động reset. Đó là cấu hình pipeline, không tạo nguồn dữ liệu để tái chạy vô hạn.

Với Stream song song:

- Tránh stateful side effects trừ khi được đồng bộ và có lý do rõ.
- Không mặc định thứ tự xử lý từng phần tử giống Stream tuần tự.
- Một số terminal operations như forEach không bảo đảm encounter order; dùng đúng API và hợp đồng nếu thứ tự quan trọng.
- Việc tái tạo pipeline không làm code tự nhiên thread-safe khi nguồn hoặc callback có mutable state.

**Single-use** là đặc tính chung của Stream API, độc lập với cách thực thi tuần tự hay song song.

## 19. API nên nhận Stream hay Supplier<Stream<T>>?

Đây là một quyết định thiết kế quan trọng.

| Nhu cầu của API | Kiểu tham số nên cân nhắc | Lý do |
| --- | --- | --- |
| Xử lý dữ liệu một lượt | Stream<T> | Caller chuyển ownership một Stream để method tiêu thụ |
| Xử lý cùng nguồn nhiều lượt | Supplier<Stream<T>> | Mỗi get() tạo pipeline mới |
| Nguồn là Collection duyệt được nhiều lần | Collection<T> hoặc Iterable<T> | Có thể tạo Stream mới tùy nhu cầu, hợp đồng dễ hiểu |
| Nguồn là file/resource có thể mở lại | Path hoặc factory có throws/close rõ | Đóng tài nguyên cho mỗi lượt |
| Muốn snapshot để phân tích nhiều lần | List<T> sau khi thu thập | Materialize một lần rồi tái sử dụng |
| Muốn nhiều thống kê trong một lượt | Stream<T> kết hợp terminal tổng hợp | Không cần đọc nguồn nhiều lần |

### Khi truyền Stream<T> trực tiếp

Một API nhận Stream thường có nghĩa nó được phép **tiêu thụ** Stream. Ghi rõ liệu API có **đóng Stream** hay không. Đặc biệt, khi method nhận Stream từ caller rồi gọi count(), caller không nên dùng Stream ấy tiếp.

Ví dụ:

~~~java
static long countNonBlank(java.util.stream.Stream<String> input) {
    return input.filter(s -> !s.trim().isEmpty()).count();
}
~~~

Đây là method minh họa. Nó tiêu thụ Stream nhận vào. Nếu caller truyền Stream file, cần có hợp đồng rõ về ai chịu trách nhiệm close. Đừng ngầm đóng một Stream do caller sở hữu nếu API không quy định.

### Khi truyền Supplier<Stream<T>>

Mỗi lần get() **phải trả Stream mới**; API có thể tạo hai lượt khác nhau. Nhưng nếu factory có I/O hoặc mutable state, document phải nói rõ cách xử lý lỗi, đóng resource và tính nhất quán dữ liệu.

### Khi nhận Collection<T>

Nếu API thực sự cần duyệt lại một Collection có sẵn, nhận Collection có thể đơn giản và tường minh hơn Supplier. Điều này cũng tránh việc caller vô tình truyền supplier trả một Stream cũ.

Không có một kiểu tham số hoàn hảo cho mọi tình huống; lựa chọn phụ thuộc **quyền sở hữu**, **nguồn có thể duyệt lại**, **đòi hỏi tài nguyên** và **số lần đọc dữ liệu**.

## 20. Những lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai hoặc nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| Gọi **count()** hai lần trên cùng Stream | Stream đã được tiêu thụ | Tạo Stream mới từ nguồn |
| Gọi **collect(...)** rồi muốn dùng Stream tiếp | Terminal operation đã kết thúc lượt sử dụng | Dùng kết quả Collection hoặc tạo Stream mới |
| Dùng **findFirst()** rồi nghĩ phần còn lại chưa duyệt nên được dùng lại | Short-circuit vẫn tiêu thụ pipeline | Stream mới cho lượt mới |
| Tạo hai nhánh từ cùng một Stream base | Forking một Stream không được hỗ trợ | Tạo hai Stream từ nguồn |
| **Supplier<Stream<T>> f = () -> oldStream** | Trả lại cùng Stream cũ | Đặt **source.stream()** trong lambda |
| Nghĩ Stream mới luôn cho cùng dữ liệu | Nguồn hoặc generator state có thể đổi | Kiểm soát snapshot và state |
| Tạo Stream mới từ cùng Iterator đã duyệt hết | Iterator là cursor một lượt | Lấy Iterator mới hoặc materialize |
| Gọi count() trên Files.lines rồi không close | Terminal operation không tự đóng resource | try-with-resources |
| Tin IllegalStateException luôn phát hiện lỗi reused | API không bảo đảm mọi trường hợp được phát hiện | Thiết kế không dùng lại từ đầu |
| Nghĩ close() làm Stream reset | Close kết thúc/giải phóng resource | Mở Stream mới nếu nguồn cho phép |
| Sửa ArrayList trong lúc pipeline duyệt | Có thể vi phạm non-interference | Sửa giữa các lượt đã kết thúc |
| Dùng Stream.generate vô hạn với collect toàn bộ | Có thể không kết thúc hoặc thiếu bộ nhớ | limit/điều kiện kết thúc phù hợp |
| Lấy side effects trong peek để đếm lượt | Optimizations/short-circuit có thể làm sai giả định | Dùng terminal tổng hợp có hợp đồng rõ |
| Dùng parallel stream rồi dự đoán thứ tự side effects | Parallel không bảo đảm cùng thứ tự xử lý | Tránh side effects và chọn API phù hợp |
| Collect tất cả dữ liệu khổng lồ chỉ để “replay” | Tốn bộ nhớ và có thể OOM | Xử lý một lượt, batch hoặc mở lại nguồn |
| Tưởng Stream.toList() luôn có trên JDK 8 | API này xuất hiện từ Java 16 | Dùng Collectors.toList() cho JDK 8 |

## 21. Bài tập thực hành có đáp án

### Bài 1 — Dùng lại một Stream

Cho:

~~~java
Stream<String> s = Stream.of("A", "B");
long a = s.count();
long b = s.count();
~~~

**Câu hỏi:** đoạn này hợp lệ không?

**Đáp án:** không. Sau count đầu tiên, Stream đã được tiêu thụ. Lần count thứ hai vi phạm quy tắc single-use; implementation có thể ném IllegalStateException. Hãy tạo Stream.of(...) mới cho mỗi lượt.

### Bài 2 — Hai lượt từ List

Cho List<String> names = Arrays.asList("A","BB"). Muốn vừa count vừa collect một danh sách chữ hoa, làm thế nào?

**Đáp án:**

~~~java
long count = names.stream().count();
List<String> upper = names.stream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());
~~~

Hai dòng minh họa cần imports. Hai lời gọi **names.stream()** tạo hai Stream độc lập.

### Bài 3 — Supplier đúng hay sai?

~~~java
Stream<Integer> once = Stream.of(1, 2, 3);
Supplier<Stream<Integer>> factory = () -> once;
~~~

**Đáp án:** factory này không đúng nếu bạn muốn nhiều lượt. Mỗi get() trả cùng Stream once. Nên viết **() -> Stream.of(1,2,3)**.

### Bài 4 — Source đã sửa

Bạn đã count List bằng một Stream. Sau đó thêm phần tử vào List, rồi gọi list.stream().count() mới. Kết quả có phải luôn bằng count đầu không?

**Đáp án:** không. Stream mới đọc trạng thái List khi lượt sau thực hiện; nếu List có thêm phần tử, count có thể tăng. Nếu cần snapshot nhất quán, tạo bản sao dữ liệu có chủ đích.

### Bài 5 — Generator dùng chung state

Hai Stream được tạo bằng **Stream.generate(sharedCounter::incrementAndGet)**, mỗi lần limit(3). Vì sao lượt hai không bắt đầu từ 1?

**Đáp án:** đối tượng Stream mới nhưng AtomicInteger/sharedCounter vẫn là một. Nếu cần reset, tạo counter mới trong factory.

### Bài 6 — Iterator một lượt

Bạn đã tạo Stream từ một Iterator và tiêu thụ hết. Tạo Stream mới từ chính Iterator ấy có đủ để đọc lại các phần tử cũ?

**Đáp án:** không. Iterator thường đã ở cuối. Nếu nguồn hỗ trợ, lấy Iterator mới từ Collection; nếu không, materialize khi còn cơ hội hoặc thiết kế thuật toán một lượt.

### Bài 7 — Files.lines

Bạn muốn đếm số dòng và lọc một loại dòng trong cùng file, mỗi bước một lượt. Có thể dùng chung một Stream từ Files.lines không?

**Đáp án:** không. Mở **Files.lines(path)** mới cho mỗi lượt trong các khối **try-with-resources** riêng, hoặc tính cả hai trong một lượt nếu có thuật toán phù hợp.

### Bài 8 — Terminal operation có tự close không?

**Đáp án:** không. count(), collect() hay forEach() là terminal operations, nhưng không tự động gọi close() để giải phóng tài nguyên I/O. Stream giữ tài nguyên phải được đóng theo hợp đồng.

### Bài 9 — Short-circuit

findFirst() chỉ đọc phần tử đầu tiên. Sau đó có thể gọi collect() trên cùng Stream để đọc phần còn lại không?

**Đáp án:** không. findFirst() là terminal operation và đã tiêu thụ Stream theo hợp đồng, dù có thể chưa duyệt hết nguồn.

### Bài 10 — Một lượt thay vì nhiều lượt

Bạn cần count, sum, min, max của một List<Integer>. Có cần tạo bốn Stream không?

**Đáp án:** không nhất thiết. Dùng **values.stream().mapToInt(Integer::intValue).summaryStatistics()** để thu nhiều thống kê trong một terminal operation.

### Bài 11 — Parallel stream

Có thể gọi một terminal operation nữa trên cùng Stream sau khi nó đã chạy parallel count() không?

**Đáp án:** không. Parallel không loại bỏ giới hạn single-use. Tạo parallelStream() mới nếu cần lượt khác.

### Bài 12 — Phân biệt nguồn và pipeline

**List** hay **Stream** mới là nơi mặc định phù hợp để duyệt nhiều lần?

**Đáp án:** List có thể duyệt nhiều lần. Stream là pipeline dùng một lần; tạo Stream mới từ List để xử lý mỗi lượt.

## 22. Checklist trước khi viết code xử lý nhiều lượt

**Xác định nguồn:**

- Nguồn là Collection có thể duyệt lại, một mảng, generator hay resource một lượt?
- Nguồn có thể thay đổi giữa các lần đọc không?
- Có cần snapshot nhất quán không?
- Có giới hạn số lượng phần tử không? Nguồn có thể vô hạn không?

**Xác định pipeline:**

- Mỗi Stream có đúng một hướng xử lý và một terminal operation không?
- Có đang cố tạo hai nhánh từ cùng một Stream base không?
- Có gọi lại Stream đã count/collect/findFirst/forEach/close không?
- Nếu dùng Supplier<Stream<T>>, get() có thực sự tạo Stream mới?

**Xác định tài nguyên:**

- Stream có giữ file descriptor/socket/reader không?
- Ai sở hữu và đóng Stream?
- Terminal operation đã thực hiện nhưng tài nguyên đã close chưa?
- Factory mở resource mới có chính sách checked exception và close rõ chưa?

**Xác định chiến lược nhiều lượt:**

- Có thể tạo Stream mới trực tiếp từ nguồn không?
- Có cần chuyển Stream nguồn thành List snapshot để xử lý lại?
- Có thể gộp thống kê vào một lượt bằng một terminal operation không?
- Có stateful generator hoặc side effect khiến dữ liệu giữa các lượt khác nhau không?

**Kiểm tra kết quả:**

- Viết test cho hai lượt độc lập.
- Test nguồn thay đổi giữa hai lượt nếu được phép.
- Test nguồn có trạng thái như Iterator hoặc generator.
- Test đóng file ở cả đường bình thường và khi có lỗi.
- Không coi việc một lỗi reused Stream chưa được ném là bằng chứng code đúng.

## Tổng kết

**Stream trong Java được thiết kế để vận hành một lần.** Một terminal operation tiêu thụ pipeline; sau đó không được dùng lại chính Stream ấy để thực hiện terminal operation khác. Việc dùng lại có thể gây **IllegalStateException**, nhưng Java không bảo đảm mọi tình huống sai đều được phát hiện bằng exception.

**Cách tái xử lý đúng là tạo Stream mới từ nguồn thích hợp**: gọi **collection.stream()**, **Arrays.stream(...)**, **Stream.of(...)**, hoặc dùng **Supplier<Stream<T>>** thực sự tạo pipeline mới mỗi lần. Nếu nguồn chỉ duyệt một lượt, phải mở lại nguồn theo cách nó hỗ trợ, thu thập dữ liệu thành Collection, hoặc thiết kế tính toán một lượt.

Với **resource streams** như Files.lines, một terminal operation **không thay thế close()**: dùng try-with-resources cho mỗi lượt. Với generator có trạng thái, Stream mới **không tự reset state**; với Collection mutable, Stream mới **không tự bảo đảm snapshot cũ**. Hiểu rõ sự khác biệt giữa **nguồn dữ liệu**, **trạng thái nguồn**, **đối tượng Stream** và **lượt tiêu thụ** sẽ giúp bạn viết pipeline đúng, dễ kiểm thử và an toàn trên Java hiện đại.