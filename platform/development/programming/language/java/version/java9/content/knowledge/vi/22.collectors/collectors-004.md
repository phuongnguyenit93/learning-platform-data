# Vòng đời luồng con khi flatMapping

Trong Stream API, `flatMap()` biến mỗi phần tử của luồng nguồn thành một luồng con rồi nối các phần tử của những luồng con đó thành một luồng kết quả. Một điểm quan trọng của hợp đồng API là **mỗi luồng con do mapper trả về sẽ được đóng sau khi các phần tử của nó được đưa vào luồng kết quả**.

Quy tắc này đặc biệt hữu ích khi luồng con quản lý tài nguyên như file. Ví dụ, `Files.lines(path)` trả về một `Stream<String>` đọc file theo kiểu lazy và giữ tài nguyên file mở cho đến khi stream được đóng. Khi stream này được trả về từ mapper của `flatMap()`, `flatMap()` tự đóng nó sau khi xử lý xong phần tử nguồn tương ứng. Luồng ngoài như `Files.list(directory)` vẫn thuộc trách nhiệm đóng của đoạn mã đã tạo ra nó.

`flatMap()` có từ Java 8 và vẫn là API hiện hành trong Java 9+. Nội dung dưới đây tập trung vào hợp đồng vòng đời stream đang được áp dụng, không dựa vào chi tiết triển khai nội bộ.

## Mục tiêu

- Hiểu vai trò của luồng nguồn, luồng con và luồng kết quả trong `flatMap()`.
- Biết thời điểm mapper được gọi và thời điểm luồng con được đóng.
- Phân biệt trách nhiệm đóng luồng con với trách nhiệm đóng luồng ngoài.
- Dùng `Files.lines()` và `Files.list()` an toàn trong pipeline.
- Xử lý checked exception trong mapper và hiểu lỗi I/O khi đọc lazy.
- Tránh đóng thủ công, tái sử dụng hoặc giữ tham chiếu đến luồng con sau khi `flatMap()` đã tiêu thụ nó.

## 1. Ba luồng cần phân biệt

Một pipeline có `flatMap()` có thể liên quan đến ba lớp stream:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Luồng nguồn (outer/source stream) | Cung cấp từng phần tử đầu vào cho mapper | `Files.list(directory)` cung cấp các `Path` |
| Luồng con (inner/mapped stream) | Được mapper tạo hoặc trả về cho từng phần tử nguồn | `Files.lines(path)` cung cấp các dòng trong một file |
| Luồng kết quả (flattened stream) | Nối các phần tử từ các luồng con thành một pipeline duy nhất | `paths.flatMap(path -> Files.lines(path))` |

Ví dụ về mặt dữ liệu: nếu luồng nguồn có các phần tử `A` và `B`, mapper tạo luồng con `[a1, a2]` cho `A` và `[b1, b2]` cho `B`, thì kết quả flatten là `[a1, a2, b1, b2]` theo quá trình duyệt của pipeline.

Điểm cần nhớ: luồng kết quả không phải là một collection đã được tạo sẵn. Nó vẫn là một pipeline lazy; các phần tử thường chỉ được xử lý khi có terminal operation như `collect()`, `forEach()`, `count()`, `findFirst()` hoặc `reduce()`.

## 2. Hợp đồng đóng luồng con của `flatMap()`

Javadoc của `Stream.flatMap()` quy định rằng mỗi mapped stream sẽ được đóng sau khi nội dung của nó được đưa vào stream kết quả. Nếu mapper trả về `null`, giá trị đó được xem như một stream rỗng.

Với mỗi phần tử nguồn, quá trình xử lý có thể hình dung như sau:

1. Terminal operation bắt đầu tiêu thụ pipeline; mapper chưa được gọi trước thời điểm này vì pipeline lazy.
2. `flatMap()` nhận một phần tử nguồn và gọi mapper cho phần tử đó.
3. Mapper trả về một stream con.
4. `flatMap()` duyệt các phần tử của stream con và chuyển chúng xuống bước tiếp theo của pipeline.
5. Khi việc duyệt stream con kết thúc, `flatMap()` đóng stream con.
6. Pipeline tiếp tục với phần tử nguồn kế tiếp.

Như vậy, nếu mapper trả về một stream có `onClose()` handler, handler đó sẽ chạy khi stream con được đóng sau lần tiêu thụ tương ứng. Đoạn mã gọi `flatMap()` không cần tự gọi `close()` cho stream con.

### 2.1. Luồng con được đóng ngay sau khi xử lý phần tử nguồn

Luồng con không chờ đến khi toàn bộ luồng ngoài kết thúc mới được đóng. Mỗi luồng con được đóng sau khi nội dung của chính nó được xử lý xong. Vì vậy, một pipeline xử lý hàng nghìn file có thể mở và đóng từng file theo lượt thay vì giữ tất cả các file mở cùng lúc.

### 2.2. Terminal operation dừng sớm

Với terminal operation có thể dừng sớm như `findFirst()`, `anyMatch()` hoặc `limit()` trong pipeline, việc duyệt một luồng con có thể kết thúc trước khi đọc hết mọi phần tử của nó. Luồng con đang được `flatMap()` tiêu thụ vẫn được đóng khi quá trình duyệt đó kết thúc.

Không nên dựa vào việc mọi phần tử của luồng con đều đã được đọc. Điều được bảo đảm ở đây là vòng đời đóng của stream con, không phải việc tiêu thụ toàn bộ dữ liệu khi downstream có thể dừng sớm.

### 2.3. Mapper trả về `null`

Nếu mapper trả về `null`, `flatMap()` xử lý nó như một stream rỗng. Tuy vậy, cách viết rõ ràng hơn thường là trả về `Stream.empty()` để thể hiện ý định và tránh một giá trị null khó đọc:

~~~java
Stream<String> names = users.flatMap(user -> {
    List<String> aliases = user.aliases();
    return aliases == null ? Stream.empty() : aliases.stream();
});
~~~

Trong đoạn mã này, `Stream.empty()` làm rõ trường hợp không có phần tử nào được phát ra.

## 3. Luồng con và tài nguyên I/O

`Stream<T>` kế thừa `BaseStream<T, Stream<T>>`, còn `BaseStream` triển khai `AutoCloseable`. Một số API I/O trả về stream gắn với tài nguyên bên ngoài:

- `Files.lines(path)` và `Files.lines(path, charset)` đọc nội dung file theo kiểu lazy; stream cần được đóng để giải phóng file.
- `Files.list(directory)` liệt kê nội dung thư mục và giữ directory stream mở; stream cần được đóng.
- `Files.walk(path)` cũng trả về stream quản lý tài nguyên duyệt cây thư mục; stream cần được đóng.

Khi một stream I/O được trả về làm kết quả mapper của `flatMap()`, nó là luồng con và được `flatMap()` đóng sau khi tiêu thụ. Luồng nguồn I/O không tự trở thành luồng con chỉ vì nó nằm trước `flatMap()`; bên tạo luồng nguồn vẫn phải quản lý việc đóng.

### 3.1. Ví dụ với `Files.lines()`

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    List<String> lines = paths
        .flatMap(path -> {
            try {
                return Files.lines(path, StandardCharsets.UTF_8);
            } catch (IOException exception) {
                throw new UncheckedIOException(exception);
            }
        })
        .collect(Collectors.toList());
}
~~~

Trong ví dụ:

- `paths` là luồng nguồn được tạo bởi `Files.list()`. Khối try-with-resources đóng `paths` khi rời khối.
- Mỗi lần mapper được gọi, `Files.lines()` tạo một luồng con cho một file.
- `flatMap()` tiêu thụ và đóng luồng con đó sau khi xử lý xong file tương ứng.
- `collect()` tiêu thụ pipeline; bản thân terminal operation không tự đóng luồng nguồn.

Không cần bọc `Files.lines()` trong một try-with-resources khác bên trong mapper rồi trả stream ra ngoài. Nếu đóng stream trước khi trả về, `flatMap()` sẽ nhận một stream đã đóng và không thể đọc dữ liệu.

### 3.2. Luồng ngoài không được tự đóng chỉ vì pipeline đã chạy xong

Terminal operation kết thúc việc tiêu thụ dữ liệu, nhưng không mặc nhiên gọi `close()` cho stream. Điều này áp dụng cho stream ngoài có tài nguyên I/O. Hãy đóng stream ngoài bằng try-with-resources hoặc gọi `close()` trong một cấu trúc quản lý vòng đời rõ ràng.

Ví dụ, `Files.list(directory)` phải được đóng bởi đoạn mã đã gọi nó, ngay cả khi mỗi `Files.lines(path)` ở bên trong đã được `flatMap()` đóng tự động.

### 3.3. Tránh tái sử dụng stream con

Một stream chỉ được tiêu thụ một lần. Ngoài ra, stream con trả về từ mapper sẽ được `flatMap()` đóng theo hợp đồng. Không giữ stream con trong biến dùng chung để đọc tiếp sau khi mapper trả về, và không trả đi trả lại cùng một stream instance cho nhiều phần tử nguồn.

Nếu cần đọc lại dữ liệu, hãy tạo stream mới từ nguồn tương ứng hoặc materialize dữ liệu vào collection nếu kích thước và yêu cầu bộ nhớ cho phép.

## 4. Ngoại lệ trong mapper và trong quá trình đọc

### 4.1. Checked exception khi mở luồng con

Mapper của `flatMap()` nhận một `Function`, mà phương thức `apply()` không khai báo checked exception. Trong khi đó, `Files.lines()` khai báo `IOException`. Vì vậy, khi mở stream trong mapper, cần xử lý checked exception tại đó hoặc chuyển thành unchecked exception.

~~~java
paths.flatMap(path -> {
    try {
        return Files.lines(path, StandardCharsets.UTF_8);
    } catch (IOException exception) {
        throw new UncheckedIOException(exception);
    }
});
~~~

`UncheckedIOException` giữ lại nguyên nhân gốc trong `getCause()`. Lớp gọi có thể bắt `UncheckedIOException` quanh terminal operation để xử lý lỗi I/O.

### 4.2. Lỗi xảy ra trong lúc đọc lazy

`Files.lines()` mở file và trả về stream để đọc lười. Một số lỗi I/O có thể chỉ xuất hiện khi terminal operation thực sự duyệt các dòng. Các lỗi đó được báo dưới dạng `UncheckedIOException` trong quá trình xử lý stream.

Do đó, chỉ bắt `IOException` trong mapper là chưa đủ để xử lý mọi lỗi đọc. Nếu cần chuyển lỗi thành thông báo nghiệp vụ hoặc ghi log, hãy cân nhắc bắt `UncheckedIOException` quanh thao tác terminal và kiểm tra cause.

### 4.3. Stream con vẫn được đóng khi xử lý gặp lỗi

Việc đóng stream con là một phần của hợp đồng `flatMap()`. Khi việc duyệt stream con kết thúc do lỗi, luồng con đang được quản lý cũng được đóng. Nếu thao tác đóng có lỗi, quy tắc ngoại lệ bị suppressed của try-with-resources có thể áp dụng cho lỗi chính và lỗi đóng.

Không tự bắt rồi bỏ qua lỗi đóng tài nguyên. Nếu `close()` có thể báo lỗi quan trọng đối với tính đúng đắn của ứng dụng, hãy để lỗi được truyền ra hoặc xử lý theo chính sách lỗi rõ ràng.

## 5. Ví dụ hoàn chỉnh: hai tầng tài nguyên

Ví dụ này tạo một thư mục tạm với hai file. `Files.list()` cung cấp stream ngoài gồm các đường dẫn. Mapper dùng `Files.lines()` để mở stream con cho từng file. Mỗi stream con có `onClose()` handler để quan sát thời điểm `flatMap()` đóng nó; stream ngoài có handler riêng và chỉ đóng khi khối try-with-resources kết thúc.

**Tệp:** `FlatMapResourceLifecycleDemo.java`

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FlatMapResourceLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("flatmap-lifecycle-");
        Path first = directory.resolve("01.txt");
        Path second = directory.resolve("02.txt");

        try {
            Files.write(first, Arrays.asList("alpha", "beta"), StandardCharsets.UTF_8);
            Files.write(second, Arrays.asList("gamma", "delta"), StandardCharsets.UTF_8);

            try (Stream<Path> paths = Files.list(directory).onClose(
                    () -> System.out.println("outer stream closed"))) {
                List<String> lines = paths
                    .sorted()
                    .flatMap(path -> {
                        try {
                            return Files.lines(path, StandardCharsets.UTF_8).onClose(
                                () -> System.out.println(
                                    "inner stream closed: " + path.getFileName()
                                )
                            );
                        } catch (IOException exception) {
                            throw new UncheckedIOException(exception);
                        }
                    })
                    .collect(Collectors.toList());

                System.out.println(lines);
            }
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~text
javac --release 9 FlatMapResourceLifecycleDemo.java
java FlatMapResourceLifecycleDemo
~~~

Output:

~~~text
inner stream closed: 01.txt
inner stream closed: 02.txt
[alpha, beta, gamma, delta]
outer stream closed
~~~

Giải thích thứ tự:

1. `paths.sorted()` sắp xếp tên file để ví dụ có kết quả xác định, không dựa vào thứ tự liệt kê thư mục của hệ thống file.
2. Khi `flatMap()` đọc xong `01.txt`, stream con tương ứng được đóng và handler in `inner stream closed: 01.txt`.
3. Sau đó stream con của `02.txt` được đóng tương tự.
4. `collect()` tạo list kết quả và chương trình in list.
5. Khi rời khối try-with-resources, stream ngoài từ `Files.list()` được đóng và handler in `outer stream closed`.

Ví dụ cho thấy việc đóng hai loại stream diễn ra ở hai thời điểm khác nhau và do hai bên chịu trách nhiệm khác nhau.

## 6. Các biến thể flattening

Stream API có các biến thể primitive:

- `flatMapToInt()` ánh xạ mỗi phần tử thành `IntStream` rồi nối các giá trị `int`.
- `flatMapToLong()` ánh xạ thành `LongStream`.
- `flatMapToDouble()` ánh xạ thành `DoubleStream`.

Chúng có cùng mục tiêu flatten các luồng con primitive. Khi mapper trả về một stream con có close handler, hãy áp dụng nguyên tắc quản lý vòng đời của mapped stream và kiểm tra hợp đồng API tương ứng.

## 7. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Quên đóng `Files.list()` | Nghĩ rằng `flatMap()` đóng cả stream nguồn | Quản lý stream ngoài bằng try-with-resources |
| Tự đóng stream con trước khi return | Mapper trả về stream đã đóng | Trả stream đang mở; để `flatMap()` đóng sau khi tiêu thụ |
| Giữ stream con để dùng lại | Stream chỉ được tiêu thụ một lần và `flatMap()` đóng mapped stream | Tạo stream mới hoặc thu thập dữ liệu cần giữ |
| Dùng một stream con cho nhiều phần tử nguồn | Nhiều lần mapper trả cùng instance đã tiêu thụ/đóng | Tạo một stream mới cho mỗi phần tử nguồn |
| Chỉ bắt `IOException` lúc mở file | Lỗi đọc lazy có thể xuất hiện trong terminal operation dưới dạng `UncheckedIOException` | Xử lý cả lỗi lúc mở và lỗi khi tiêu thụ |
| Cho rằng `collect()` tự đóng stream ngoài | Terminal operation chỉ tiêu thụ pipeline | Đóng stream có tài nguyên bằng try-with-resources |
| Trả về `null` từ mapper | Kết quả khó đọc và che giấu trường hợp không có dữ liệu | Trả `Stream.empty()` để thể hiện ý định rõ ràng |
| Dùng `peek()` để gọi `close()` thủ công | Trộn logic quản lý tài nguyên vào xử lý phần tử và có thể đóng sai thời điểm | Dùng hợp đồng tự đóng của `flatMap()` cho stream con |

## 8. Quy tắc thực hành

1. Xác định rõ stream nào là nguồn và stream nào được mapper tạo ra.
2. Khi mapper trả về một stream, coi stream đó sẽ được `flatMap()` tiêu thụ và đóng.
3. Mỗi phần tử nguồn nên tạo một stream con mới; không chia sẻ lại một stream đã dùng.
4. Đóng stream ngoài có tài nguyên bằng try-with-resources, kể cả khi terminal operation đã hoàn tất.
5. Không tự đóng stream con trước khi trả về từ mapper.
6. Với `Files.lines()`, xử lý `IOException` khi mở và cân nhắc `UncheckedIOException` khi đọc lazy.
7. Dùng `Stream.empty()` khi một phần tử nguồn không tạo ra dữ liệu con.
8. Khi cần quan sát lifecycle, dùng `onClose()` trong ví dụ kiểm thử hoặc chẩn đoán; không phụ thuộc vào chi tiết triển khai nội bộ.

## 9. Tự kiểm tra

- `flatMap()` có đóng từng stream con do mapper trả về không? Có, sau khi nội dung của mapped stream được đưa vào stream kết quả.
- Nếu mapper trả về `null`, `flatMap()` xử lý thế nào? Xem như một stream rỗng.
- `flatMap()` có tự đóng stream ngoài được tạo bởi `Files.list()` không? Không. Đoạn mã tạo stream ngoài vẫn phải đóng nó.
- Terminal operation `collect()` có tự gọi `close()` cho stream không? Không. Terminal operation tiêu thụ dữ liệu; việc đóng phải được quản lý riêng.
- Vì sao không nên trả về cùng một stream instance cho nhiều phần tử nguồn? Vì stream chỉ được tiêu thụ một lần và mapped stream sẽ được đóng sau khi sử dụng.
- Vì sao `Files.lines()` trong mapper cần chuyển `IOException` thành unchecked exception? Vì hàm mapper không khai báo checked exception.
- Lỗi đọc file có thể xuất hiện ở thời điểm nào? Có thể xuất hiện khi terminal operation tiêu thụ stream, vì `Files.lines()` đọc dữ liệu lazy.
- Trong ví dụ, vì sao inner stream đóng trước outer stream? `flatMap()` đóng từng mapped stream sau khi xử lý file; try-with-resources đóng stream ngoài khi rời khối.

Điểm cốt lõi: **`flatMap()` chịu trách nhiệm đóng từng stream con mà mapper trả về; đoạn mã tạo stream nguồn chịu trách nhiệm đóng stream ngoài.** Tách bạch hai vòng đời này giúp giải phóng file và directory stream đúng lúc, kể cả khi pipeline dừng sớm hoặc phát sinh lỗi.