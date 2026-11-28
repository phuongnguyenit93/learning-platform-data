# Quản lý tài nguyên bên trong mapper và khác biệt với substream của flatMap

Khi dùng Stream để đọc file, duyệt thư mục hoặc truy vấn nguồn dữ liệu có thể đóng, cần quản lý vòng đời resource một cách tường minh. Điểm khác biệt quan trọng giữa **mapMulti** và **flatMap** là: mapper của mapMulti nhận một Consumer để phát ra phần tử, còn mapper của flatMap trả về một Stream con. Stream API tự đóng từng Stream con do flatMap trả về sau khi xử lý; với mapMulti, resource được mở bên trong mapper phải được đóng bởi chính mapper, thường bằng try-with-resources.

mapMulti được bổ sung trong Java 16 và vẫn là API Stream hiện hành. Bài học tập trung vào các cách sử dụng còn phù hợp trên JDK hiện đại, đặc biệt khi mapper cần đọc dữ liệu từ resource, phát ra không hoặc nhiều phần tử và xử lý lỗi trong quá trình duyệt.

## 1. mapMulti và flatMap khác nhau ở hợp đồng mapper

Cả hai đều biểu diễn phép biến đổi một-phần-tử-thành-không-hoặc-nhiều-phần-tử. Cách mapper tạo ra các phần tử khác nhau:

| Đặc điểm | mapMulti | flatMap |
|---|---|---|
| Kết quả mapper | Gọi Consumer từ 0 đến nhiều lần | Trả về một Stream con |
| Cách phát phần tử | Imperative: gọi accept khi có phần tử | Declarative: trả về Stream mô tả phần tử |
| Đóng Stream con | Không có Stream con do mapper trả về để Stream API tự đóng | Stream API đóng từng Stream con sau khi xử lý |
| Resource mở trong mapper | Mapper phải tự đóng | Nếu resource được biểu diễn bằng Stream trả về, flatMap quản lý việc đóng Stream con |
| Phù hợp khi | Sinh một số phần tử trực tiếp bằng vòng lặp, điều kiện hoặc API callback | Có sẵn một Stream con, nhất là Stream gắn với resource |
| Short-circuit | Mapper không nhận tín hiệu cancellation để chủ động dừng vòng lặp sinh phần tử | Pipeline có thể truyền cancellation vào quá trình duyệt Stream con |

Ví dụ về chữ ký tổng quát:

~~~java
stream.<R>mapMulti((element, downstream) -> {
    // downstream.accept(value);
});
~~~

Trong khi đó:

~~~java
stream.flatMap(element -> {
    return anotherStream;
});
~~~

Không nên chọn mapMulti chỉ vì nó có thể tránh tạo nhiều Stream nhỏ. Nếu dữ liệu đã được biểu diễn tự nhiên bằng Stream, flatMap thường dễ đọc và có quy tắc đóng Stream con rõ ràng hơn. mapMulti hữu ích khi mapper phát phần tử trực tiếp bằng logic imperative.

## 2. Stream không tự đóng chỉ vì terminal operation đã chạy

Một Stream có thể triển khai AutoCloseable và đăng ký hành động đóng qua onClose. Tuy nhiên, việc gọi terminal operation như forEach, count, toList hoặc collect không tự động gọi close trên Stream nguồn.

Ví dụ, Files.lines trả về Stream gắn với file handle:

~~~java
Stream<String> lines = Files.lines(path);
lines.forEach(System.out::println);
~~~

Đoạn code trên duyệt các dòng nhưng không đóng Stream. File handle có thể tiếp tục mở sau terminal operation. Cần dùng try-with-resources:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(System.out::println);
}
~~~

Quy tắc này áp dụng cho cả Stream được tạo từ Files.lines, Files.list, Files.walk và các API trả về Stream có resource gắn với nó. Với Stream thuần từ collection hoặc range, thường không có resource hệ điều hành cần đóng.

## 3. Resource mở bên trong mapMulti phải được đóng ngay trong mapper

Giả sử mỗi Path trong nguồn đại diện cho một file văn bản. Mapper đọc từng file và phát từng dòng sang downstream:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class ReadFilesWithMapMulti {
    public static List<String> readAllLines(List<Path> paths) {
        return paths.stream()
                .<String>mapMulti((path, emit) -> {
                    try (Stream<String> lines =
                                 Files.lines(path, StandardCharsets.UTF_8)) {
                        lines.forEach(emit);
                    } catch (IOException e) {
                        throw new UncheckedIOException(
                                "Cannot read file: " + path, e);
                    }
                })
                .toList();
    }
}
~~~

Vòng đời trong mỗi lần gọi mapper:

1. Nhận một Path từ Stream nguồn.
2. Mở Stream dòng bằng Files.lines.
3. Dùng forEach để chuyển từng dòng tới Consumer emit.
4. Khi duyệt hoàn tất hoặc có exception, try-with-resources gọi close.
5. Mapper kết thúc và pipeline tiếp tục với phần tử nguồn tiếp theo.

Resource được đóng trước khi mapper trả về. Không có Stream con nào được trả về cho mapMulti, vì vậy không thể trông chờ Stream API tự đóng Stream do Files.lines tạo ra.

try-with-resources cũng bảo đảm close được gọi nếu đọc file hoặc Consumer phát sinh unchecked exception. Nếu cả thân try và thao tác close cùng ném exception, Java giữ exception chính và gắn exception từ close dưới dạng suppressed exception.

## 4. Anti-pattern: mở Stream trong mapMulti nhưng quên close

Đoạn sau bị rò rỉ resource:

~~~java
paths.stream()
        .<String>mapMulti((path, emit) -> {
            try {
                Files.lines(path, StandardCharsets.UTF_8)
                        .forEach(emit);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .toList();
~~~

forEach chỉ tiêu thụ phần tử; nó không đóng Stream. Stream do Files.lines tạo ra không được trả về từ mapper và cũng không được đăng ký như một resource của Stream ngoài. Khi xử lý nhiều file, số file handle còn mở có thể tăng cho đến khi hệ điều hành từ chối mở thêm file.

Cách sửa là đặt Stream vào try-with-resources:

~~~java
paths.stream()
        .<String>mapMulti((path, emit) -> {
            try (Stream<String> lines =
                         Files.lines(path, StandardCharsets.UTF_8)) {
                lines.forEach(emit);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .toList();
~~~

Đừng kỳ vọng việc đóng Stream ngoài sẽ đóng các Stream nội bộ mà mapper đã tạo nhưng không trả về. Nếu mapper sở hữu resource, mapper phải hoàn tất trách nhiệm đóng resource đó.

## 5. Cùng bài toán với flatMap: Stream API đóng substream

Nếu mỗi file đã được biểu diễn tự nhiên bằng một Stream dòng, flatMap thường ngắn gọn hơn:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class ReadFilesWithFlatMap {
    public static List<String> readAllLines(List<Path> paths) {
        return paths.stream()
                .flatMap(path -> {
                    try {
                        return Files.lines(path, StandardCharsets.UTF_8);
                    } catch (IOException e) {
                        throw new UncheckedIOException(
                                "Cannot read file: " + path, e);
                    }
                })
                .toList();
    }
}
~~~

Theo hợp đồng của flatMap, mỗi Stream được mapper trả về sẽ được đóng sau khi các phần tử của nó được đưa vào Stream kết quả. Vì vậy, không cần tự viết try-with-resources quanh Stream con được trả về từ mapper.

Điều này chỉ áp dụng cho Stream con do mapper trả về. Nếu Stream ngoài cũng sở hữu resource, chẳng hạn được tạo bằng Files.list, bên gọi vẫn phải đóng Stream ngoài:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    List<String> lines = paths
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            })
            .toList();
}
~~~

Ở ví dụ này, flatMap đóng từng Stream dòng của file; try-with-resources bên ngoài đóng Stream<Path> được tạo bởi Files.list. Hai cấp resource có chủ sở hữu riêng.

## 6. Chọn mapMulti hay flatMap khi xử lý resource?

Nếu mapper tạo một Stream con từ resource, flatMap thường là lựa chọn tự nhiên:

~~~java
Stream<Path> paths = ...;

Stream<String> lines = paths.flatMap(path -> {
    try {
        return Files.lines(path, StandardCharsets.UTF_8);
    } catch (IOException e) {
        throw new UncheckedIOException(e);
    }
});
~~~

Nếu mapper dùng API imperative và phát ra một số giá trị trực tiếp, mapMulti phù hợp:

~~~java
List<Integer> values = List.of(1, 2, 3, 4).stream()
        .<Integer>mapMulti((number, emit) -> {
            if (number % 2 == 0) {
                emit.accept(number);
                emit.accept(number * 10);
            }
        })
        .toList();
~~~

Ví dụ resource mà không cần tạo Stream con: dùng BufferedReader để đọc và phát các dòng:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ReadWithBufferedReader {
    public static List<String> readSelectedLines(List<Path> paths) {
        return paths.stream()
                .<String>mapMulti((path, emit) -> {
                    try (BufferedReader reader = Files.newBufferedReader(
                            path, StandardCharsets.UTF_8)) {
                        String line;
                        while ((line = reader.readLine()) != null) {
                            if (!line.isBlank()) {
                                emit.accept(line);
                            }
                        }
                    } catch (IOException e) {
                        throw new UncheckedIOException(
                                "Cannot read file: " + path, e);
                    }
                })
                .toList();
    }
}
~~~

Ở đây mapMulti hữu ích vì mapper dùng vòng lặp để lọc và phát giá trị. BufferedReader được đóng trong cùng phạm vi mapper. Nếu không có logic imperative bổ sung, Files.lines kết hợp flatMap thường biểu đạt ý định rõ hơn.

## 7. Ảnh hưởng của short-circuit operation

Các terminal hoặc intermediate operation như findFirst, anyMatch và limit có thể kết thúc việc duyệt sớm. Cần hiểu mapper nào có thể dừng công việc bên trong của nó.

Với flatMap, Stream con tham gia trực tiếp vào pipeline. Khi downstream short-circuit, quá trình duyệt Stream con có thể nhận tín hiệu dừng và Stream con được đóng theo hợp đồng của flatMap.

~~~java
Optional<String> firstLine = paths.stream()
        .flatMap(path -> {
            try {
                return Files.lines(path, StandardCharsets.UTF_8);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .filter(line -> line.contains("ERROR"))
        .findFirst();
~~~

Với mapMulti, mapper chỉ nhận Consumer để phát phần tử; Consumer không cung cấp phương thức kiểm tra downstream đã muốn dừng hay chưa. Nếu mapper tự gọi fileLines.forEach(emit), vòng forEach có thể tiếp tục đọc hết file hiện tại dù downstream không cần thêm phần tử.

~~~java
List<String> firstTen = paths.stream()
        .<String>mapMulti((path, emit) -> {
            try (Stream<String> fileLines =
                         Files.lines(path, StandardCharsets.UTF_8)) {
                fileLines.forEach(emit);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .limit(10)
        .toList();
~~~

Trong trường hợp này, limit giới hạn số phần tử được giữ ở kết quả nhưng không cung cấp tín hiệu cho mapper dừng việc đọc file giữa vòng forEach. Nếu muốn chỉ đọc tối đa một số dòng trong mỗi file, đặt giới hạn ngay trên Stream con trước khi phát:

~~~java
paths.stream()
        .<String>mapMulti((path, emit) -> {
            try (Stream<String> fileLines =
                         Files.lines(path, StandardCharsets.UTF_8)) {
                fileLines.limit(10).forEach(emit);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .toList();
~~~

Nếu mục tiêu là tìm phần tử đầu tiên trên toàn bộ các file và muốn pipeline truyền short-circuit xuống từng Stream con, flatMap thường phù hợp hơn. Với mapMulti, phải tự thiết kế giới hạn công việc ngay trong mapper.

## 8. Exception khi mở, đọc và đóng resource

Các API I/O thường ném checked IOException, trong khi mapper của mapMulti và flatMap không khai báo checked exception. Một cách phổ biến là bọc lỗi thành UncheckedIOException:

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(emit);
} catch (IOException e) {
    throw new UncheckedIOException("Read failed: " + path, e);
}
~~~

Phân biệt các thời điểm lỗi:

| Thời điểm | Ví dụ | Cách xử lý |
|---|---|---|
| Mở resource | File không tồn tại, không có quyền đọc | Bắt IOException và chuyển thành UncheckedIOException hoặc lỗi domain |
| Đọc resource | File lỗi, I/O gián đoạn | Files.lines có thể phát sinh UncheckedIOException trong quá trình traversal; giữ nguyên cause để điều tra |
| Phát phần tử | Consumer/downstream ném RuntimeException | try-with-resources vẫn đóng resource; để lỗi truyền ra nếu không có chính sách phục hồi |
| Đóng resource | Close handler phát sinh lỗi | Try-with-resources xử lý exception chính và suppressed exception theo quy tắc Java |

Không nên bắt Exception chung rồi bỏ qua để pipeline tiếp tục như thể dữ liệu đầy đủ. Nếu bỏ qua một file lỗi, cần ghi nhận rõ file nào bị bỏ và chính sách đó phải là yêu cầu nghiệp vụ.

## 9. Quản lý nhiều loại resource trong mapMulti

mapMulti không chỉ áp dụng cho file. Mapper có thể mở resource khác, miễn là resource được đóng trước khi mapper kết thúc.

| Resource | Cách quản lý trong mapper | Lưu ý |
|---|---|---|
| Files.lines / Files.list / Files.walk | try-with-resources quanh Stream | Terminal operation không tự đóng Stream |
| BufferedReader | try-with-resources quanh reader | Có thể dùng readLine để phát từng giá trị |
| DirectoryStream | try-with-resources quanh DirectoryStream | Iterator được duyệt trong phạm vi resource |
| ZipFile | try-with-resources quanh ZipFile | Đóng ZipFile sau khi đã đọc các entry cần thiết |
| JDBC Connection/Statement/ResultSet | try-with-resources theo thứ tự ownership | Tránh giữ transaction/connection mở khi downstream xử lý lâu |
| HTTP response/body stream | Đóng response hoặc body stream theo API client | Không phát stream ra ngoài rồi đóng response trước khi client đọc xong |

Ví dụ với ZipFile:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.stream.Stream;

public class ZipEntryNames {
    public static Stream<String> entryNames(Stream<Path> archives) {
        return archives.<String>mapMulti((archive, emit) -> {
            try (ZipFile zip = new ZipFile(archive.toFile())) {
                zip.stream()
                        .map(ZipEntry::getName)
                        .forEach(emit);
            } catch (IOException e) {
                throw new UncheckedIOException(
                        "Cannot open archive: " + archive, e);
            }
        });
    }
}
~~~

ZipFile và Stream<ZipEntry> được sử dụng bên trong phạm vi try. Vì zip.stream() phụ thuộc vào ZipFile, phải tiêu thụ Stream entry trước khi đóng ZipFile. Không trả zip.stream() ra khỏi mapper rồi đóng ZipFile ngay sau đó.

## 10. Không để Consumer hoặc resource thoát khỏi phạm vi mapper

Consumer do mapMulti cung cấp chỉ nên được sử dụng đồng bộ trong lần gọi mapper hiện tại. Không lưu Consumer vào field, collection dùng chung hoặc gửi nó sang thread khác để gọi sau khi mapper đã trả về.

Không nên viết:

~~~java
stream.<Result>mapMulti((input, emit) -> {
    executor.submit(() -> emit.accept(loadLater(input)));
});
~~~

Mapper trả về trước khi tác vụ bất đồng bộ gọi Consumer. Việc sử dụng Consumer ngoài phạm vi mapper không thuộc cách dùng hợp lệ của API và có thể dẫn đến kết quả không xác định. Nếu cần xử lý bất đồng bộ, hãy dùng API concurrency phù hợp rồi đưa kết quả về một Stream hoặc collection có vòng đời rõ ràng.

Tương tự, không mở resource trong mapper rồi lưu reference vào biến bên ngoài để đóng sau một terminal operation khác. Resource nên có một chủ sở hữu và phạm vi đóng rõ ràng.

## 11. Parallel stream và resource riêng cho từng mapper invocation

Với parallel stream, mapper có thể được gọi đồng thời cho nhiều phần tử nguồn. Nếu mỗi mapper invocation mở resource riêng, hãy giữ resource cục bộ trong invocation đó và đóng ngay khi hoàn tất.

Không chia sẻ một BufferedReader, ZipFile, JDBC ResultSet hoặc mutable resource giữa các mapper invocation nếu API không hỗ trợ concurrent access. Cũng không dùng chung một Consumer được lưu bên ngoài mapper.

Ví dụ, khi đọc nhiều file song song:

~~~java
List<String> lines = paths.parallelStream()
        .<String>mapMulti((path, emit) -> {
            try (Stream<String> fileLines =
                         Files.lines(path, StandardCharsets.UTF_8)) {
                fileLines.forEach(emit);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .toList();
~~~

Mỗi mapper invocation sở hữu Stream file riêng và đóng nó trước khi kết thúc. Tuy nhiên, đọc song song có thể làm tăng số file descriptor mở cùng lúc, áp lực I/O và mức dùng bộ nhớ. Chỉ chuyển sang parallel sau khi đo tải và giới hạn tài nguyên của môi trường đích.

## 12. Kiểm thử resource đã được đóng

Một test thực tế nên xác nhận kết quả và khả năng xóa file sau khi pipeline hoàn tất. Trên một số hệ điều hành, file đang mở có thể không xóa được; vì vậy kiểm tra xóa file là một tín hiệu hữu ích cho vòng đời handle.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MapMultiResourceTest {
    @TempDir
    Path tempDir;

    @Test
    void closesEachFileStreamAfterMapperFinishes() throws Exception {
        Path file = tempDir.resolve("input.txt");
        Files.writeString(file, "alpha\nbeta\n", StandardCharsets.UTF_8);

        List<String> values = Stream.of(file)
                .<String>mapMulti((path, emit) -> {
                    try (Stream<String> lines =
                                 Files.lines(path, StandardCharsets.UTF_8)) {
                        lines.forEach(emit);
                    } catch (java.io.IOException e) {
                        throw new java.io.UncheckedIOException(e);
                    }
                })
                .toList();

        assertEquals(List.of("alpha", "beta"), values);
        Files.delete(file);
    }
}
~~~

@TempDir tạo thư mục tạm cho test. Test đọc file bằng mapMulti, xác nhận dữ liệu và xóa file sau terminal operation. Với hệ điều hành cho phép xóa file đang mở, việc xóa thành công không tự chứng minh mọi handle đã đóng; nên kết hợp test này với kiểm tra code path và test exception.

Có thể kiểm tra thêm trường hợp Consumer ném exception để xác nhận try-with-resources vẫn đóng file:

~~~java
assertThrows(IllegalStateException.class, () ->
        Stream.of(file)
                .<String>mapMulti((path, emit) -> {
                    try (Stream<String> lines =
                                 Files.lines(path, StandardCharsets.UTF_8)) {
                        lines.forEach(line -> {
                            emit.accept(line);
                            throw new IllegalStateException("stop");
                        });
                    } catch (java.io.IOException e) {
                        throw new java.io.UncheckedIOException(e);
                    }
                })
                .toList());

Files.delete(file);
~~~

Đoạn kiểm thử này minh họa rằng exception phát sinh trong quá trình phát phần tử vẫn đi qua khối try-with-resources. Trong test thực tế, nên tách phần setup và assertion để thông báo lỗi dễ đọc.

## 13. Checklist khi review mapper có resource

- [ ] Resource nào được mở trong mapper?
- [ ] Ai sở hữu resource và ở đâu gọi close?
- [ ] Resource có được đóng nếu đọc thành công, lỗi I/O hoặc Consumer ném exception không?
- [ ] Stream ngoài có phải resource-based stream như Files.list không, và ai đóng nó?
- [ ] Có trả Stream/Iterator/reader phụ thuộc vào resource đã đóng ra ngoài mapper không?
- [ ] Mapper có giữ Consumer sau khi trả về hoặc dùng nó ở thread khác không?
- [ ] Pipeline có short-circuit không; mapper có thể đọc quá nhiều dữ liệu trước khi dừng không?
- [ ] Parallel execution có mở quá nhiều file handle hoặc chia sẻ resource không an toàn không?
- [ ] Checked IOException được chuyển thành lỗi runtime có giữ cause không?
- [ ] Có test cho cleanup khi thành công và khi exception không?

## 14. Chọn cách triển khai theo tình huống

| Tình huống | Cách nên cân nhắc | Lý do |
|---|---|---|
| Mỗi input ánh xạ thành một Stream resource như Files.lines | flatMap | Stream API đóng từng Stream con sau khi xử lý |
| Mỗi input dùng vòng lặp để lọc và phát vài giá trị | mapMulti | Mapper kiểm soát trực tiếp số phần tử được phát |
| Mỗi input mở BufferedReader rồi phát dòng đã lọc | mapMulti + try-with-resources | Không cần tạo Stream con; resource đóng trong mapper |
| Cần short-circuit sâu vào nguồn con | flatMap | Cancellation có thể được truyền qua Stream con |
| Cần mở resource nhưng xử lý bất đồng bộ | Thiết kế pipeline concurrency riêng | Consumer của mapMulti không được giữ để gọi sau mapper |
| Resource ngoài là Files.list hoặc Files.walk | try-with-resources quanh Stream ngoài | Terminal operation không tự đóng nguồn ngoài |

Không có quy tắc rằng mapMulti luôn nhanh hơn flatMap. Nếu mapper phải tạo Stream con từ resource, flatMap thường dễ diễn đạt ownership hơn. Nếu mapper cần imperative expansion, mapMulti có thể tránh việc tạo một Stream nhỏ cho mỗi input. Hãy benchmark bằng dữ liệu và runtime thực tế trước khi tối ưu.

## 15. Ghi nhớ

- mapMulti phát phần tử qua Consumer; nó không trả về Stream con.
- Resource mở bên trong mapper của mapMulti phải được đóng tường minh, thường bằng try-with-resources.
- Terminal operation không tự đóng Stream resource-based.
- flatMap tự đóng từng Stream con do mapper trả về sau khi xử lý.
- Stream ngoài như Files.list vẫn cần được bên gọi đóng.
- Nếu mapper dùng forEach để đọc hết resource, limit bên ngoài không cung cấp tín hiệu cho mapper dừng sớm giữa vòng lặp.
- Consumer của mapMulti chỉ được dùng trong phạm vi mapper; không lưu hoặc gửi sang thread khác.
- Với parallel stream, mỗi invocation cần sở hữu resource riêng và phải cân nhắc giới hạn file handle/I/O.
- Khi mapper trả về Stream resource, flatMap thường là lựa chọn rõ ràng; khi mapper phát giá trị imperative, mapMulti phù hợp hơn.

Quản lý resource đúng cách là trách nhiệm của đoạn code mở resource. Khi dùng mapMulti, hãy đóng resource trước khi mapper trả về; khi dùng flatMap, tận dụng quy tắc đóng substream của Stream API và vẫn đóng Stream nguồn ở cấp ngoài. Cách phân định ownership này giúp tránh rò rỉ file handle và làm hành vi cleanup dễ kiểm thử trên các JDK hiện đại.

## Tài liệu tham khảo

- [Java 25 Stream API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html) — hợp đồng mapMulti, flatMap và các intermediate operation.
- [Java 25 Files API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html) — vòng đời Stream trả về bởi lines, list và walk.
- [Java 25 Stream package summary](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html) — lazy evaluation, pipeline và short-circuit operations.
