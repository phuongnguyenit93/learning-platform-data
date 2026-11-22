# Phân biệt Stream, Collection, Iterator và luồng nhập xuất trong Java

Trong Java, cùng một từ *stream* có thể chỉ **hai nhóm API hoàn toàn khác nhau**: **java.util.stream.Stream<T>**, dùng để xây dựng một pipeline xử lý phần tử, và **java.io.InputStream/OutputStream**, dùng để đọc, ghi byte qua nguồn và đích I/O. Ngoài ra, **Collection<E>** quản lý một nhóm phần tử, trong khi **Iterator<E>** giúp duyệt lần lượt các phần tử.

Bốn khái niệm này có thể phối hợp trong cùng một ứng dụng nhưng không thay thế trực tiếp cho nhau. Một tệp được đọc bằng API I/O; các dòng của nó có thể trở thành Stream<String> để lọc và biến đổi; kết quả có thể được thu về List<String> để dùng lại. Bài viết giải thích hợp đồng, vòng đời, lỗi phổ biến và cách lựa chọn trong Java 17+.

## 1. So sánh nhanh

| Abstraction | Đại diện | Nhiệm vụ | Hành vi đặc trưng |
| --- | --- | --- | --- |
| **Collection<E>** | java.util.Collection, List, Set | Mô hình nhóm dữ liệu | size, contains, add/remove nếu hỗ trợ, iterator |
| **Iterator<E>** | java.util.Iterator | Duyệt phần tử tuần tự | hasNext, next, remove tùy chọn |
| **Stream<T>** | java.util.stream.Stream | Mô tả phép xử lý phần tử | filter, map, sorted, collect; chỉ dùng một lượt |
| **I/O byte stream** | java.io.InputStream/OutputStream | Truyền byte | read, write, close; có thể blocking/IOException |
| **I/O character stream** | java.io.Reader/Writer | Đọc/ghi ký tự | read ký tự, write ký tự, giải mã/mã hóa qua adapter |

**Ghi nhớ:** Collection lưu/đại diện dữ liệu; Iterator dẫn qua một lượt duyệt; Stream API mô tả cách xử lý phần tử; luồng I/O vận chuyển byte/ký tự giữa chương trình và nguồn/đích.

## 2. Collection<E>: dữ liệu được tổ chức thành tập hợp

Collection là một interface của Java Collections Framework. Ví dụ List lưu các phần tử có thứ tự theo vị trí, Set duy trì tính duy nhất của phần tử theo hợp đồng equality.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(
    List.of("An", "Binh", "Mai")
);
System.out.println(names.size());      // 3
System.out.println(names.get(0));      // An
names.add("Lan");
System.out.println(names.contains("Lan")); // true
~~~

Đoạn trên là mã minh họa đặt trong phương thức; chương trình chạy độc lập có ở phần 9.

Một Collection thường có các thao tác truy vấn như **size, isEmpty, contains, toArray**, có thể cung cấp **iterator()**, **stream()** và **parallelStream()**. Nhưng không được mặc định rằng mọi Collection đều mutable:

~~~java
List<String> fixed = List.of("An", "Mai");

// Ném UnsupportedOperationException:
fixed.add("Lan");
~~~

List.of trả List không thể chỉnh sửa; ArrayList trong ví dụ trước hỗ trợ add/remove. Một số Collection cũng chỉ là **view** trên cấu trúc khác, không nhất thiết là một bản sao độc lập hoàn toàn.

Map<K,V> **không kế thừa Collection**. Các phương thức keySet(), values() và entrySet() trả các collection view thích hợp để duyệt hoặc chuyển thành stream.

### 2.1. Collection có thể được duyệt nhiều lần

~~~java
List<String> names = List.of("An", "Binh", "Mai");

for (String name : names) {
    System.out.println(name);
}
for (String name : names) {
    System.out.println(name);
}
~~~

Duyệt hai lần là hợp lệ với List thông thường. Khả năng tạo lượt duyệt mới là khác biệt quan trọng với **cùng một instance Stream** sau khi đã tiêu thụ.

Tuy nhiên, một Collection không nhất thiết bất biến hoặc bảo đảm an toàn cho nhiều thread. Khi cấu trúc nguồn bị sửa trong lúc duyệt, cần tuân thủ hợp đồng của implementation.

## 3. Iterator<E>: con trỏ của một lượt duyệt

Iterator không phải nơi chứa phần tử; nó cung cấp cơ chế đi từ phần tử hiện tại sang phần tử kế tiếp:

~~~java
boolean hasNext();
E next();
void remove(); // Optional operation
~~~

- **hasNext():** kiểm tra có phần tử tiếp theo không.
- **next():** lấy phần tử tiếp theo và tiến trạng thái duyệt; hết phần tử gây NoSuchElementException.
- **remove():** nếu iterator hỗ trợ, xóa phần tử vừa được next trả về khỏi cấu trúc nền. Không phải iterator nào cũng hỗ trợ.

Ví dụ xóa tên ngắn trong ArrayList:

~~~java
List<String> names = new ArrayList<>(
    List.of("An", "Binh", "Bo")
);

Iterator<String> iterator = names.iterator();
while (iterator.hasNext()) {
    String name = iterator.next();
    if (name.length() <= 2) {
        iterator.remove();
    }
}

System.out.println(names); // [Binh]
~~~

Ở đây **Iterator.remove() thay đổi ArrayList thật sự**. Trái lại, phép Stream.filter trong phần tiếp theo chỉ chọn phần tử cho kết quả mà không xóa nguồn.

Không nên đồng thời xóa trực tiếp bằng names.remove(name) trong vòng lặp đang dùng iterator của ArrayList. Thay đổi cấu trúc ngoài iterator có thể khiến iterator phát hiện ConcurrentModificationException. Đây không phải cơ chế bảo đảm thread-safety; tính fail-fast là **best effort**, không dùng làm phương thức đồng bộ.

### 3.1. Iterator thường không có khả năng reset

Sau khi hết, một iterator bình thường không tự quay về đầu. Với Collection có thể duyệt lại, hãy gọi **collection.iterator()** để lấy iterator mới. Interface Iterator không quy định reset hay rewind. Nếu cần duyệt hai chiều đối với List, có thể xem xét ListIterator với các phương thức previous/hasPrevious phù hợp.

Iterator cũng có thể được viết để đọc phần tử từ nguồn sinh dữ liệu, không nhất thiết phải bắt nguồn từ Collection. Vì vậy không thể suy luận một Iterator luôn có size cố định hoặc giữ toàn bộ dữ liệu trong RAM.

### 3.2. For-each liên quan đến Iterable

Enhanced for:

~~~java
for (String name : names) {
    System.out.println(name);
}
~~~

làm việc với array hoặc đối tượng **Iterable**. Collection<E> kế thừa Iterable<E>, nên thường dùng được for-each. Stream<T> không kế thừa Iterable<T> nên không thể trực tiếp viết for (String name : stream). Muốn duyệt Stream, dùng terminal operation, ví dụ forEach, hoặc lấy iterator từ Stream và tuân thủ một lượt tiêu thụ.

## 4. Stream<T>: pipeline, không phải container

java.util.stream.Stream<T> là chuỗi phần tử hỗ trợ các phép xử lý tổng hợp tuần tự hoặc song song, thường được tạo từ Collection, array, generator hoặc nguồn I/O.

~~~java
List<String> names = List.of("An", "Binh", "Mai");

List<String> upperLongNames = names.stream()
    .filter(name -> name.length() > 2)
    .map(String::toUpperCase)
    .toList();

System.out.println(upperLongNames); // [BINH, MAI]
~~~

Stream ở đây không phải ArrayList thứ hai tự động sinh ra lúc gọi stream(). Nó mô tả một **pipeline**:

~~~text
List<String> nguồn
    |
    v
stream() -> filter() -> map() -> toList()
                          |
                          v
                  List<String> kết quả
~~~

### 4.1. Intermediate operations và terminal operations

| Nhóm | Ví dụ | Vai trò |
| --- | --- | --- |
| Intermediate | filter, map, flatMap | Biến đổi luồng phần tử |
| Intermediate có trạng thái | sorted, distinct | Có thể cần nhớ nhiều phần tử |
| Intermediate giới hạn | limit, skip, takeWhile | Hạn chế hoặc bỏ phần tử |
| Terminal thu kết quả | toList, collect, count | Trả kết quả/tổng hợp |
| Terminal tìm kiếm | findFirst, anyMatch, allMatch | Có thể short-circuit |
| Terminal thao tác | forEach, reduce | Thực thi/tổng hợp theo hợp đồng |

**Intermediate operations thường lazy:** tạo pipeline không nhất thiết thực hiện thao tác trên dữ liệu cho đến khi một terminal operation yêu cầu kết quả. Một số pipeline có thể short-circuit; compiler/runtime có thể tối ưu để không gọi mọi callback đúng số lần người viết tưởng tượng.

~~~java
Stream<String> pipeline = names.stream()
    .filter(name -> name.length() > 2);

System.out.println("before terminal");
System.out.println(pipeline.count());
~~~

Các câu lệnh in xảy ra theo thứ tự, nhưng không nên dùng filter/map làm nơi bắt buộc phải ghi log, ghi database hoặc tăng bộ đếm. Việc callback có được gọi bao nhiêu lần phụ thuộc vào pipeline và terminal operation.

### 4.2. Stream chỉ tiêu thụ một lần

~~~java
Stream<String> stream = names.stream();
List<String> result = stream.toList();

// KHÔNG HỢP LỆ: stream này đã được tiêu thụ.
long count = stream.count();
~~~

Cố sử dụng lại có thể ném IllegalStateException; một số trường hợp reuse có thể không được phát hiện, nên quy tắc đúng là **không tái sử dụng cùng một Stream instance**. Tạo stream mới từ Collection nếu cần xử lý lần nữa:

~~~java
List<String> result = names.stream().toList();
long count = names.stream().count();
~~~

Đừng viết Supplier<Stream<T>> mà mỗi lần get() đều trả **cùng một Stream đã cache**. Một supplier thích hợp phải tạo Stream mới khi được gọi, nếu mục tiêu là xử lý lại.

### 4.3. Stream không thay đổi Collection nguồn theo mặc định

~~~java
List<String> source = new ArrayList<>(
    List.of("An", "Mai")
);
List<String> filtered = source.stream()
    .filter(name -> name.length() > 2)
    .toList();

// source vẫn chứa [An, Mai]; filtered là [Mai].
~~~

Muốn thay đổi source, có thể dùng **source.removeIf(predicate)** trên collection mutable hoặc thao tác cập nhật có hợp đồng riêng. Nhưng đừng sửa source từ lambda filter/map hoặc thread khác khi pipeline đang duyệt; Stream API thường đòi hỏi các behavioral parameters **không can thiệp nguồn (non-interference)** và không có trạng thái chia sẻ không an toàn.

Stream.toList() trên Java 17 trả List **không thể chỉnh sửa**; kết quả không tự thừa hưởng khả năng sửa của ArrayList nguồn. Nếu cần ArrayList mutable, thu kết quả bằng Collectors.toCollection(ArrayList::new).

### 4.4. Stream tuần tự và song song

Một Stream có thể là sequential hoặc parallel. Ví dụ:

~~~java
long total = numbers.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

Đoạn trên cần một Collection<Integer> tên numbers. Parallel stream không tự động nhanh hơn: còn chi phí chia việc, hợp đồng thứ tự, kích thước nguồn và mức độ tính toán. Các callback chứa mutation, log hoặc biến dùng chung không được tự động bảo đảm an toàn bởi parallelStream.

**Stream.forEach** trong pipeline parallel không bảo đảm thứ tự thực hiện; **forEachOrdered** được dùng khi cần tôn trọng encounter order thích hợp. Một vòng for-each trên List tuần tự và một parallelStream.forEach không thể được xem như hai biểu thức có hành vi thứ tự giống nhau.

## 5. I/O stream: InputStream và OutputStream

Luồng nhập xuất byte nằm trong **java.io**, có trách nhiệm lấy và ghi **byte**, không cung cấp filter/map/toList như Stream<T>.

~~~java
int value = input.read(); // 0..255 hoặc -1 khi EOF

if (value != -1) {
    output.write(value);
}
~~~

Đây là **đoạn minh họa**, với input/output là đối tượng InputStream/OutputStream phù hợp. Giá trị -1 của read() là dấu hiệu cuối nguồn, không phải dữ liệu cần ghi. Các thao tác có thể blocking và có thể ném IOException.

Nguồn I/O có thể là file, socket, mảng byte, pipe hoặc thiết bị. Ví dụ byte stream hoạt động trong bộ nhớ:

~~~java
byte[] bytes = "Hi".getBytes(
    java.nio.charset.StandardCharsets.UTF_8);

try (java.io.ByteArrayInputStream input =
         new java.io.ByteArrayInputStream(bytes)) {
    String text = new String(
        input.readAllBytes(),
        java.nio.charset.StandardCharsets.UTF_8
    );
    System.out.println(text); // Hi
}
~~~

Đoạn trên là minh họa trong phương thức có xử lý hoặc khai báo IOException, khi dùng trong lớp đầy đủ. Với FileInputStream, socket và stream giữ tài nguyên hệ điều hành, close là phần quan trọng của quản lý vòng đời.

### 5.1. Reader và Writer là I/O ký tự

Reader/Writer là abstraction cho **ký tự**, không phải abstraction stream pipeline. Để chuyển byte thành văn bản đúng, dùng charset thích hợp qua InputStreamReader hoặc phương thức của Files.

~~~java
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(
             path,
             java.nio.charset.StandardCharsets.UTF_8)) {
    String firstLine = reader.readLine();
}
~~~

Đây là mã minh họa cần Path hợp lệ và xử lý IOException. Byte stream không tự biết chuỗi là UTF-8, UTF-16 hay một encoding khác; việc giải mã/mã hóa là một phần hợp đồng xử lý dữ liệu.

### 5.2. Vòng đời của I/O khác pipeline Stream

- Nguồn I/O thường cần **close()** để giải phóng file descriptor/socket/handle.
- Việc đọc/ghi có thể chặn, gặp EOF hoặc ném IOException.
- InputStream có thể hỗ trợ mark/reset tùy implementation; **không** thể mặc định mọi InputStream đều rewind.
- readAllBytes/readAllLines có thể giữ toàn bộ nội dung trong bộ nhớ; cần thận trọng với dữ liệu lớn.
- Các stream byte/reader khác nhau có thể được bọc bởi buffer hoặc adapter, và quyền sở hữu close cần thống nhất.

Không dùng Stream<T>.close thay cho việc đóng tài nguyên I/O bị giữ bởi thành phần khác nếu API không tự quản lý chúng.

## 6. Vì sao Files.lines vừa là I/O vừa trả Stream<String>?

**Files.lines(Path, Charset)** đọc các dòng văn bản của tệp và trả về **java.util.stream.Stream<String>**. Nó không trả InputStream, nhưng bên dưới có nguồn I/O:

~~~text
Tệp (bytes)
    |
    v
Đọc và giải mã theo Charset
    |
    v
Các dòng String
    |
    v
java.util.stream.Stream<String>
    |
    v
filter / map / limit / count / toList
~~~

Ví dụ:

~~~java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> nonBlank = lines
        .filter(s -> !s.isBlank())
        .toList();
}
~~~

Các đoạn ở mục này dùng tên lớp Files, Path, Stream, List, StandardCharsets theo import tương ứng; xem chương trình độc lập ở phần 9.

**Cần dùng try-with-resources** cho các Stream có nguồn I/O như **Files.lines, Files.list, Files.walk, Files.find**. Các terminal operation như count hoặc toList không tự bảo đảm đóng tất cả tài nguyên nguồn nếu có lỗi. Stream<T> kế thừa BaseStream, thuộc AutoCloseable, nhưng với stream thuần từ một List thường không có tài nguyên cần đóng.

### 6.1. Files.readAllLines khác Files.lines

~~~java
List<String> all = Files.readAllLines(
    path, StandardCharsets.UTF_8);
~~~

readAllLines trả một **List<String> đã được tạo**, thích hợp khi có thể chứa toàn bộ dữ liệu và muốn duyệt lại nhiều lần.

~~~java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
}
~~~

Files.lines có thể xử lý dòng theo nhu cầu của pipeline, tránh việc bắt buộc dựng List chứa mọi dòng trước khi bắt đầu. Nhưng **lazy không có nghĩa bộ nhớ luôn hằng số**: sorted, distinct, groupingBy, toList có thể tích lũy phần lớn dữ liệu.

Khi xử lý Stream từ tệp, lỗi khi mở có thể là IOException; lỗi I/O phát sinh trong quá trình duyệt còn có thể xuất hiện dưới dạng **UncheckedIOException**. API Stream không khiến hoạt động I/O trở thành phép tính thuần.

### 6.2. BufferedReader.lines

BufferedReader có phương thức lines() trả Stream<String> từ reader:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    List<String> firstThree =
        reader.lines().limit(3).toList();
}
~~~

**Reader** trong đoạn trên là tài nguyên được try-with-resources quản lý. Không suy ra rằng bất kỳ terminal operation nào trên reader.lines() đều tự đóng reader.

## 7. Khi nào chọn Iterator, khi nào chọn Stream?

Iterator hợp lý khi cần **kiểm soát từng bước**, có vòng điều kiện phức tạp, cần break, hoặc cần dùng remove() trên implementation hỗ trợ.

~~~java
Iterator<String> it = names.iterator();
while (it.hasNext()) {
    String value = it.next();
    if (value.isEmpty()) {
        it.remove();
    }
}
~~~

Stream hợp lý khi cần một pipeline dễ đọc để lọc, biến đổi hoặc tổng hợp:

~~~java
List<String> cleaned = names.stream()
    .filter(s -> !s.isBlank())
    .map(String::trim)
    .toList();
~~~

Hai đoạn **không tương đương**: đoạn Iterator thay đổi names, đoạn Stream tạo kết quả và giữ names nguyên nếu callback không can thiệp nguồn.

Một vòng for có if/break có thể rõ hơn một pipeline lạm dụng filter/peek để mô phỏng điều khiển luồng. Mục tiêu là chọn abstraction khớp hợp đồng, không ép mọi xử lý thành lambda.

### 7.1. Chuyển qua lại có kiểm soát

Collection → Stream:

~~~java
Stream<String> stream = names.stream();
~~~

Stream → List không thể chỉnh sửa:

~~~java
List<String> collected = names.stream()
    .map(String::toUpperCase)
    .toList();
~~~

Stream → ArrayList mutable:

~~~java
ArrayList<String> collected = names.stream()
    .map(String::toUpperCase)
    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
~~~

Iterator → Stream khi chỉ có iterator:

~~~java
Iterator<String> iterator = names.iterator();
java.util.Spliterator<String> spliterator =
    java.util.Spliterators.spliteratorUnknownSize(
        iterator, java.util.Spliterator.ORDERED);
Stream<String> stream =
    java.util.stream.StreamSupport.stream(spliterator, false);
~~~

Dùng ORDERED chỉ khi nguồn thực sự có encounter order; không khai báo đặc tính không đúng để “tối ưu” tùy tiện. Stream mới vẫn tiêu thụ cùng iterator nguồn, không tự sao chép mọi phần tử; không đồng thời duyệt bằng iterator và stream.

Stream → Iterator:

~~~java
Iterator<String> iterator = names.stream().iterator();
~~~

Đây là iterator được tạo từ Stream và tiêu thụ Stream tương ứng. Không dùng lại instance Stream sau khi đã bắt đầu một lượt duyệt theo cách không hợp lệ.

## 8. Quản lý tài nguyên và các lỗi thường gặp

### 8.1. Cần đóng cái gì?

- **Collection trong bộ nhớ:** không có close chuẩn.
- **Iterator thông thường:** không có close trong interface.
- **Stream từ Collection:** có close nhưng thường không có tài nguyên I/O để giải phóng.
- **Stream trả bởi Files.lines/list/walk/find:** có thể giữ tài nguyên; dùng try-with-resources.
- **InputStream, OutputStream, Reader, Writer:** thường cần đóng khi nắm quyền sở hữu tài nguyên.

Một phương thức đọc tệp tốt có thể bao toàn bộ luồng I/O trong try-with-resources rồi trả về **kết quả dữ liệu đã thu**, thay vì trả Stream còn mở mà không nói rõ caller phải close. Nếu API trả Stream I/O-backed, phải làm rõ nghĩa vụ close của caller.

### 8.2. Collection và Iterator không tự bảo đảm thread safety

Sửa ArrayList từ thread khác khi iterator hoặc stream đang duyệt có thể làm hỏng kết quả hoặc ném ngoại lệ; fail-fast không phải cơ chế synchronization. Với concurrency, cần chọn concurrent collections, xử lý snapshot hoặc bảo vệ trạng thái đúng cách.

### 8.3. Tránh tác dụng phụ trong filter/map

Không nên dựa vào số lần callback trong Stream làm cơ sở ghi audit, vì lazy/short-circuit/tối ưu/parallel làm thay đổi cách thực thi. Với Iterator, người viết điều khiển từng lần next rõ hơn, nhưng việc đọc source bên ngoài vẫn có thể ném lỗi hoặc gây side effect theo hợp đồng API.

### 8.4. Phân biệt nội dung, encoding và buffering

InputStream trả byte; Reader giải mã ký tự. Stream<String> sau Files.lines chứa dòng String; nó không giữ dấu xuống dòng như ký tự riêng ở cuối mỗi phần tử. Muốn bảo toàn chính xác line separator, BOM và encoding khi chuyển đổi, cần quy trình I/O thích hợp. Không tự giả định charset mặc định của hệ thống khớp giao thức dữ liệu.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình sau dùng đủ bốn khái niệm, có kết quả đầu ra xác định và không cần tệp có sẵn. Nó tạo tệp tạm, ghi dữ liệu UTF-8 rồi xóa sau khi sử dụng:

- ArrayList là **Collection** lưu tên.
- Iterator.remove() thực sự sửa ArrayList.
- Stream.filter/map tạo **List kết quả** mà không sửa nguồn.
- Cùng Stream bị gọi terminal lần hai, minh họa lỗi sử dụng lại.
- ByteArrayOutputStream và ByteArrayInputStream ghi/đọc **byte**.
- Files.lines trả **Stream<String>** từ tệp và được đóng bằng try-with-resources.

Tạo tệp **StreamConceptsDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.stream.Stream;

public class StreamConceptsDemo {
    public static void main(String[] args) throws IOException {
        List<String> names = new ArrayList<>(
            List.of("An", "Binh", "Mai", "Bo"));
        System.out.println("collection=" + names);

        Iterator<String> iterator = names.iterator();
        while (iterator.hasNext()) {
            if (iterator.next().length() <= 2) {
                iterator.remove();
            }
        }
        System.out.println("after-iterator=" + names);

        Stream<String> pipeline = names.stream()
            .filter(name -> name.length() > 3)
            .map(String::toUpperCase);
        System.out.println("before-terminal=" + names);
        System.out.println("stream-result=" + pipeline.toList());
        System.out.println("after-stream=" + names);

        try {
            pipeline.count();
        } catch (IllegalStateException error) {
            System.out.println("stream-reuse=" +
                error.getClass().getSimpleName());
        }

        ByteArrayOutputStream byteOutput = new ByteArrayOutputStream();
        byteOutput.write("Hi".getBytes(StandardCharsets.UTF_8));
        try (ByteArrayInputStream byteInput =
                 new ByteArrayInputStream(byteOutput.toByteArray())) {
            System.out.println("io-bytes=" + new String(
                byteInput.readAllBytes(), StandardCharsets.UTF_8));
        }

        Path file = Files.createTempFile("java-stream-concepts-", ".txt");
        try {
            Files.writeString(file, "one\ntwo\nthree\n",
                StandardCharsets.UTF_8);
            try (Stream<String> lines =
                     Files.lines(file, StandardCharsets.UTF_8)) {
                System.out.println("file-lines=" +
                    lines.map(String::toUpperCase).toList());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Lệnh biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac StreamConceptsDemo.java
java StreamConceptsDemo
~~~

Stdout **chính xác**:

~~~text
collection=[An, Binh, Mai, Bo]
after-iterator=[Binh, Mai]
before-terminal=[Binh, Mai]
stream-result=[BINH]
after-stream=[Binh, Mai]
stream-reuse=IllegalStateException
io-bytes=Hi
file-lines=[ONE, TWO, THREE]
~~~

### 9.1. Giải thích từng nhóm kết quả

**collection:** ArrayList có 4 tên, có thể duyệt và thay đổi theo API của implementation.

**after-iterator:** Iterator.remove bỏ "An" và "Bo" vì mỗi tên dài 2, nên Collection thực sự chỉ còn Binh và Mai.

**before-terminal:** tạo stream chưa biến đổi ArrayList. **stream-result:** filter giữ tên có độ dài trên 3 rồi map chuyển Binh thành BINH. **after-stream:** ArrayList nguồn vẫn [Binh, Mai].

**stream-reuse:** sau toList(), không thể chạy count trên cùng Stream. Mã bắt IllegalStateException và in tên lớp để minh họa.

**io-bytes:** byte stream ghi hai byte UTF-8 cho "Hi", rồi đọc và giải mã thành String. Không có phép filter/map của Stream<T> trong bước này.

**file-lines:** Files.lines lấy các dòng String từ tệp đã được ghi; map chuyển thành các chữ in hoa. Stream I/O-backed được đóng trước khi xóa tệp. Tên tệp tạm không được in ra nên stdout ổn định.

Literal Java "one\ntwo\nthree\n" chứa escape sequence chỉ dấu xuống dòng, nên tệp có ba dòng văn bản. Nếu Files.deleteIfExists gặp lỗi, IOException có thể truyền ra từ main; ví dụ không nuốt lỗi tài nguyên.

## 10. Bảng quyết định

| Cần làm gì? | Abstraction phù hợp | Lưu ý |
| --- | --- | --- |
| Giữ và quản lý phần tử qua nhiều lượt | Collection/List/Set | Xác minh cấu trúc và tính mutable |
| Duyệt từng phần tử theo điều khiển caller | Iterator | next tiến con trỏ, remove tùy chọn |
| Lọc, map, nhóm hoặc tổng hợp | Stream<T> | Một lượt dùng, callback nên non-interfering |
| Tính toán trên int/long/double | IntStream/LongStream/DoubleStream | Hạn chế boxing khi phù hợp |
| Đọc/ghi byte | InputStream/OutputStream | EOF, IOException, close |
| Đọc/ghi ký tự | Reader/Writer | Charset, decoding/encoding |
| Đọc tệp theo dòng và lọc ngay | Files.lines | Trả Stream<String>, phải close |
| Đọc toàn bộ dòng thành dữ liệu | Files.readAllLines | Trả List<String>, có thể tốn RAM |
| Muốn Stream kết quả dùng nhiều lần | Thu thành Collection hoặc tạo Stream mới | Không cache cùng Stream |
| Muốn xóa phần tử khi duyệt ArrayList | Iterator.remove hoặc removeIf | Không sửa nguồn từ callback Stream |

## 11. Những nhầm lẫn thường gặp

**Lỗi 1 — coi Stream<T> là InputStream:** tên tương tự nhưng phương thức hoàn toàn khác. InputStream đọc byte; Stream<T> xử lý phần tử T.

**Lỗi 2 — nghĩ Stream là một danh sách:** Stream không có get(index) và thường không thể chạy terminal operation lần thứ hai. Muốn dữ liệu để dùng lại, thu thành List.

**Lỗi 3 — nghĩ Collection luôn sửa được:** List.of và một số view/collection wrapper không hỗ trợ add/remove.

**Lỗi 4 — nghĩ Stream.filter xóa nguồn:** filter chọn phần tử cho pipeline, còn Collection.removeIf là phép cập nhật nguồn khi được hỗ trợ.

**Lỗi 5 — dùng tên giống nhau để suy luận ngữ nghĩa:** Collection.stream, Files.lines và BufferedReader.lines đều có thể trả Stream<T> nhưng vòng đời nguồn rất khác nhau.

**Lỗi 6 — quên close sau Files.lines:** terminal operation có thể hoàn tất mà tài nguyên I/O vẫn phải đóng; dùng try-with-resources.

**Lỗi 7 — dùng readAllBytes cho nguồn quá lớn:** có thể tiêu thụ bộ nhớ không phù hợp. Cân nhắc đọc theo buffer hoặc xử lý gia tăng.

**Lỗi 8 — nghĩ lazy không cần RAM:** sorted, distinct, toList, collect có thể giữ nhiều phần tử.

**Lỗi 9 — sửa Collection khi Stream đang chạy:** có thể vi phạm non-interference, dẫn đến lỗi hoặc kết quả không đáng tin.

**Lỗi 10 — dùng fail-fast làm cơ chế đồng bộ:** ConcurrentModificationException không phải bảo đảm phát hiện mọi xung đột.

**Lỗi 11 — mong InputStream hỗ trợ reset:** mark/reset là tùy implementation; không phải nguồn nào cũng quay lại được.

**Lỗi 12 — hiểu sai thứ tự với parallelStream:** forEach có thể chạy không theo thứ tự nguồn; cần xem hợp đồng encounter order và cách tổng hợp.

**Lỗi 13 — bỏ qua lỗi I/O:** việc Files.lines trả Stream<String> không loại bỏ IOException/UncheckedIOException của nguồn tệp.

**Lỗi 14 — dùng Stream trong mọi trường hợp:** một for/Iterator có break/continue phức tạp đôi khi sáng rõ và dễ kiểm soát hơn.

## 12. Câu hỏi tự kiểm tra

1. Vì sao cùng một List có thể gọi stream() nhiều lần nhưng cùng Stream sau toList() không được dùng lại?
2. Iterator.remove làm thay đổi điều gì? Stream.filter có làm thay đổi Collection gốc không?
3. InputStream.read trả gì khi hết nguồn và vì sao không được coi -1 là byte dữ liệu?
4. Files.lines trả loại đối tượng nào và nó vẫn phụ thuộc I/O ra sao?
5. Vì sao Files.lines cần try-with-resources dù chỉ gọi count?
6. Khi nào Files.readAllLines thích hợp hơn Files.lines, và ngược lại?
7. Vì sao HashSet, ArrayList và Map có các hợp đồng khác nhau?
8. Một Iterator có chắc chắn quay về đầu hoặc biết trước số lượng phần tử không?
9. Vì sao pipeline có sorted hoặc toList không bảo đảm dùng bộ nhớ hằng số?
10. Tại sao parallelStream không mặc nhiên nhanh hơn?
11. Làm thế nào lấy Stream từ Iterator khi API chỉ cung cấp Iterator?
12. Trong ví dụ đầy đủ, phần nào thay đổi ArrayList, phần nào chỉ biến đổi giá trị và phần nào đọc/ghi byte?
13. Nếu một Stream có nguồn I/O, ai có trách nhiệm đóng khi kết thúc?
14. Trong trường hợp nhiều thread, vì sao fail-fast không thay thế synchronization?
15. Khi phải xử lý dữ liệu văn bản, vì sao cần xác định charset ngay từ ranh giới I/O?

**Kết luận:** **Collection** là abstraction quản lý một nhóm phần tử; **Iterator** biểu diễn một lượt duyệt; **Stream<T>** biểu diễn một pipeline biến đổi và tổng hợp phần tử, thường lazy và chỉ được tiêu thụ một lần; còn **InputStream/OutputStream/Reader/Writer** là công cụ truyền byte và ký tự qua I/O. Chúng có thể phối hợp, nhưng khác nhau về chức năng, vòng đời, chi phí, ngoại lệ và quản lý tài nguyên.