# Những nền tảng từ Java 7 vẫn được sử dụng trong Java hiện đại

> **Định hướng:** Nhìn Java 7 như một cột mốc hình thành nhiều cách viết Java hiện đại: quản lý tài nguyên an toàn, thao tác file theo `Path`, xử lý ngoại lệ rõ ràng, suy luận kiểu generic và một số API tiện ích/đồng thời. Bài tập trung **chỉ vào những nền tảng còn có giá trị trong code Java hiện nay**, với ví dụ chạy trên **JDK 17+**. Những cú pháp hoặc API được bổ sung sau Java 7 sẽ được ghi rõ để tránh nhầm nguồn gốc.

## 1. Java 7 để lại những gì cho Java hiện đại?

| Nền tảng có từ Java 7 | Vì sao vẫn quan trọng? | Cách dùng trong dự án hiện nay |
| --- | --- | --- |
| `try-with-resources` và `AutoCloseable` | Đóng tài nguyên tự động, kể cả khi phát sinh lỗi | File, stream, kết nối JDBC, tài nguyên tự quản lý |
| NIO.2: `Path`, `Files`, `FileSystem` | API thao tác đường dẫn/file rõ nghĩa, hỗ trợ nhiều filesystem | Đọc/ghi/copy/move file, duyệt thư mục, xử lý file tạm |
| Multi-catch, precise rethrow | Tránh lặp logic xử lý và giữ kiểu ngoại lệ chính xác | Xử lý những lỗi có cùng phương án phục hồi |
| Diamond operator `<>` | Giảm lặp khai báo kiểu generic | Collections, repositories, DTO mappings |
| `switch` với `String` | Phân nhánh trực tiếp theo chuỗi | Chọn định dạng file, trạng thái, lệnh; dùng cú pháp `switch` mới khi phù hợp |
| Binary literal và dấu `_` trong số | Biểu diễn bitmask và hằng số dễ đọc | Quyền bit, giao thức nhị phân, số lớn |
| `Objects`, `StandardCharsets` | Kiểm tra null có chủ đích, mã hóa ký tự tường minh | Biên API, dữ liệu văn bản, UTF-8 |
| `ForkJoinPool`, `RecursiveTask`, `ThreadLocalRandom` | Công cụ chia việc CPU và tạo số ngẫu nhiên theo luồng | Tính toán song song phù hợp, thuật toán và kiểm thử |
| `MethodHandle` và `invokedynamic` | Nền tảng liên kết lời gọi động của JVM | Hiểu cơ chế JVM/framework; phần lớn ứng dụng không cần gọi trực tiếp |

**Điểm mấu chốt:** “Có từ Java 7” không đồng nghĩa “phải viết code theo phong cách năm 2011”. Ta giữ lại mô hình, cú pháp và API còn hữu ích, đồng thời tận dụng cải tiến của JDK mới.

## 2. Quản lý tài nguyên bằng try-with-resources

### 2.1. Cơ chế cần hiểu

`try-with-resources` tự gọi `close()` trên tài nguyên implements `AutoCloseable` sau khi rời khối `try`, dù hoàn tất bình thường, `return` hay có ngoại lệ. Nếu khai báo nhiều tài nguyên, chúng được khởi tạo từ trái sang phải và đóng theo **thứ tự ngược lại**. Không cần viết `finally` chỉ để đóng từng stream.

`AutoCloseable.close()` có thể ném `Exception`; `java.io.Closeable` là trường hợp chuyên biệt dùng `IOException`. Không phải mọi tài nguyên đều có thể sử dụng lại sau khi đóng. Chỉ đưa những đối tượng có vòng đời cần kết thúc vào phần khai báo tài nguyên.

Từ **Java 9**, một biến tài nguyên đã khai báo bên ngoài và là `final` hoặc *effectively final* cũng có thể được đặt trực tiếp trong `try (...)`. Khi viết code hiện đại, cách này hợp lệ, nhưng không phải cú pháp của Java 7 gốc.

### 2.2. Lỗi chính và suppressed exception

Nếu phần xử lý ném ngoại lệ và `close()` cũng thất bại, ngoại lệ **trong phần xử lý vẫn là lỗi chính**; lỗi khi đóng được lưu qua `getSuppressed()`. Điều này giúp không mất nguyên nhân gốc.

Lưu thành `ResourceDemo.java`:

```java
import java.io.IOException;

public class ResourceDemo {
    static final class FaultyResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("đóng thất bại");
        }
    }

    public static void main(String[] args) {
        try (FaultyResource resource = new FaultyResource()) {
            throw new IllegalStateException("thao tác thất bại");
        } catch (Exception error) {
            System.out.println("Lỗi chính: " + error.getMessage());
            for (Throwable suppressed : error.getSuppressed()) {
                System.out.println("Lỗi khi đóng: " + suppressed.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ResourceDemo.java
java ResourceDemo
```

Kết quả:

```text
Lỗi chính: thao tác thất bại
Lỗi khi đóng: đóng thất bại
```

**Áp dụng:** dùng `try-with-resources` với `InputStream`, `Reader`, `Writer`, `java.sql.Connection`, `PreparedStatement`, `ResultSet` hoặc bất kỳ tài nguyên nào thực sự sở hữu. Đối với `Stream` trả về từ `Files.list` / `Files.walk`, phải đóng stream sau khi duyệt vì chúng nắm tài nguyên thư mục bên dưới.

**Lỗi phổ biến:** bỏ qua lỗi đóng hoặc chỉ đọc `getCause()` rồi quên `getSuppressed()` khi điều tra thất bại I/O; tạo stream trong một method rồi trả ra ngoài mà không xác định rõ bên nào có trách nhiệm đóng.

## 3. NIO.2: Path và Files vẫn là nền tảng xử lý file

### 3.1. Phân biệt đường dẫn và thao tác I/O

- `Path` biểu diễn vị trí trong một filesystem, hỗ trợ `resolve`, `getFileName`, `normalize`, `startsWith`...; tạo `Path` không đồng nghĩa file đã tồn tại.
- `Files` thực hiện I/O như `copy`, `move`, `deleteIfExists`, `createDirectories`, `newBufferedReader`, `readAttributes`. Các thao tác có thể ném `IOException` và phải xử lý thật.
- `FileSystem` / `FileSystems` cho phép làm việc với filesystem không chỉ là đĩa mặc định (ví dụ ZIP filesystem khi provider phù hợp).
- `WatchService` quan sát sự kiện thư mục khi có nhu cầu; sự kiện có thể bị gộp hoặc mất trong tình huống tràn hàng đợi, và hành vi khác nhau giữa hệ điều hành. Đừng coi nó là cam kết nhận đầy đủ mọi thay đổi.

Java 7 giới thiệu `Path` / `Files` và `Paths.get(...)`. **Java 11** bổ sung `Path.of(...)`, `Files.readString(...)` và `Files.writeString(...)`; dùng các cách tiện lợi này trên JDK 17+ là hợp lý, nhưng đừng ghi nhầm chúng là tính năng Java 7.

### 3.2. Ví dụ file tạm, copy và đóng luồng duyệt thư mục

Lưu thành `FilesDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("java7-foundations-");
        Path source = directory.resolve("data.txt");
        Path copy = directory.resolve("copy.txt");

        try {
            Files.writeString(source, "Xin chào Java\n", StandardCharsets.UTF_8);
            Files.copy(source, copy);

            System.out.println(Files.readString(copy, StandardCharsets.UTF_8).trim());

            try (Stream<Path> entries = Files.list(directory)) {
                System.out.println(
                    entries.map(path -> path.getFileName().toString())
                           .sorted()
                           .toList()
                );
            }
        } finally {
            Files.deleteIfExists(copy);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FilesDemo.java
java FilesDemo
```

Kết quả:

```text
Xin chào Java
[copy.txt, data.txt]
```

Trong ví dụ này, **`Path` và `Files` là nền tảng từ Java 7**; `Files.list` thuộc Java 8, `readString`/`writeString` thuộc Java 11 và `Stream.toList` thuộc Java 16. Khối `finally` vẫn cần thiết để **xóa** các file tạm sau khi thao tác; `try-with-resources` dùng để **đóng** stream duyệt thư mục.

### 3.3. Quy tắc an toàn và tính đúng đắn

1. **Không đoán separator:** dùng `resolve` và `Path` thay vì nối chuỗi với `"/"` hoặc `"\\"` cho các thành phần đường dẫn.
2. **Không xem `exists` + thao tác kế tiếp là giao dịch nguyên tử:** file có thể thay đổi giữa lúc kiểm tra và sử dụng (TOCTOU). Hãy thực hiện thao tác thật và xử lý `IOException`.
3. **Không mặc định mọi phép move đều atomic:** `Files.move(..., StandardCopyOption.ATOMIC_MOVE)` có thể không được hỗ trợ giữa các filesystem; phải xử lý `AtomicMoveNotSupportedException` khi cần.
4. **Không giả định `normalize()` ngăn được path traversal:** đây là chuẩn hóa cú pháp; symbolic link và race vẫn có thể thoát khỏi thư mục dự kiến. Với input không tin cậy, phải kiểm soát phạm vi truy cập thực tế, symlink và quyền file; cân nhắc `toRealPath`/`SecureDirectoryStream` theo ngữ cảnh.
5. **Đọc nhiều file lớn nên dùng stream/buffer thích hợp:** `readString` và `readAllBytes` tải dữ liệu vào bộ nhớ. Khi kích thước không kiểm soát được, ưu tiên `newBufferedReader`, `newInputStream` hoặc kênh thích hợp và đóng đúng vòng đời.
6. **File I/O không đồng nhất giữa các máy:** quyền truy cập, case sensitivity, symlink, encoding tên file và độ hỗ trợ metadata phụ thuộc filesystem/provider. Không áp đặt một quy tắc của riêng Windows hoặc Linux cho mọi nơi.

## 4. Xử lý ngoại lệ bằng multi-catch và precise rethrow

Java 7 thêm cú pháp `catch (A | B e)` để gom những ngoại lệ **không có quan hệ cha–con với nhau** khi cần cùng một chính sách xử lý. Biến `e` trong multi-catch không thể gán lại. Nếu lỗi cần retry, log hoặc chuyển thành lỗi domain theo cách khác nhau, hãy tách catch cho rõ.

Ví dụ Java 17+, method xử lý cả lỗi đọc file và dữ liệu số không hợp lệ:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ParseConfig {
    static int loadPort(Path file) {
        try {
            return Integer.parseInt(
                Files.readString(file, StandardCharsets.UTF_8).trim()
            );
        } catch (IOException | NumberFormatException error) {
            System.err.println("Không đọc được cổng: " + error.getClass().getSimpleName());
            return -1;
        }
    }
}
```

Đây là **method minh họa, không có `main`**. `Files.readString` được thêm từ Java 11, còn multi-catch là tính năng Java 7. Trong ứng dụng thật, trả `-1` chỉ hợp lệ nếu đã định nghĩa rõ đó là sentinel; nhiều hệ thống nên ném exception riêng hoặc trả một kết quả biểu thị lỗi để không che giấu nguyên nhân.

**Precise rethrow:** khi bắt một ngoại lệ chung rồi `throw` lại chính biến bắt mà không gán lại, trình biên dịch có thể suy ra tập ngoại lệ checked cụ thể từ khối `try` thay vì bắt caller phải khai báo `throws Exception` chung chung. Đây là cơ chế kiểm tra kiểu compile-time, không thay đổi đối tượng ngoại lệ tại runtime.

**Tránh:** `catch (Exception e)` rộng và bỏ qua lỗi; multi-catch nhóm những lỗi đòi hỏi xử lý khác nhau; khai báo `IOException | FileNotFoundException` (không hợp lệ vì `FileNotFoundException` kế thừa `IOException`).

## 5. Diamond operator, generic và cú pháp số dễ đọc

### 5.1. Diamond operator

`<>` cho phép compiler suy ra đối số kiểu generic ở biểu thức khởi tạo từ ngữ cảnh, giúp code bớt lặp mà vẫn có kiểm tra kiểu lúc biên dịch.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CollectionsDemo {
    public static void main(String[] args) {
        Map<String, List<Integer>> scores = new HashMap<>();
        scores.computeIfAbsent("java", key -> new ArrayList<>()).add(7);

        System.out.println(scores.get("java"));
    }
}
```

```bash
javac -encoding UTF-8 CollectionsDemo.java
java CollectionsDemo
```

```text
[7]
```

**Nguồn gốc:** diamond `new HashMap<>()` / `new ArrayList<>()` là Java 7; `computeIfAbsent` và lambda `key -> ...` là Java 8. Generic **không tự làm collection type-safe ở runtime**; type erasure vẫn tồn tại, và dùng raw type/cast sai vẫn có thể tạo lỗi.

### 5.2. Binary literal và dấu gạch dưới

`0b`/`0B` biểu diễn số nguyên nhị phân; `_` có thể phân tách chữ số để dễ đọc. Đều là cú pháp Java 7, vẫn thích hợp cho bitmask, giao thức và hằng số:

```java
int permissionMask = 0b1100_0000;  // 192
long maxRecords = 1_000_000L;
boolean highestBitSet = (permissionMask & 0b1000_0000) != 0;
```

Dấu `_` **không hợp lệ** ở đầu/cuối literal, sát dấu chấm thập phân hoặc ngay sau tiền tố `0b`/`0x`. Đừng dùng bitmask khi mô hình dữ liệu rõ ràng hơn bằng enum hoặc kiểu domain.

## 6. switch với String và cách viết switch hiện đại

Java 7 cho phép `switch` trên `String` (so sánh theo nội dung chuỗi). Tính năng này còn hiệu lực, nhưng **switch expression** và nhãn `case ... ->` là cải tiến từ các phiên bản sau; switch expression được chuẩn hóa từ **Java 14**.

Ví dụ chạy trên Java 17+:

```java
public class StringSwitchDemo {
    static String category(String extension) {
        return switch (extension) {
            case "json", "yaml" -> "Cấu hình";
            case "csv" -> "Dữ liệu bảng";
            case "txt" -> "Văn bản";
            default -> "Khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(category("json"));
        System.out.println(category("txt"));
        System.out.println(category("exe"));
    }
}
```

```bash
javac -encoding UTF-8 StringSwitchDemo.java
java StringSwitchDemo
```

```text
Cấu hình
Văn bản
Khác
```

**Lưu ý:** nhánh `String` phân biệt hoa/thường; dữ liệu `null` phải được xử lý có chủ đích theo phiên bản Java và cú pháp switch đang dùng. Đừng mặc định mọi switch đều nhận `null`. Cú pháp arrow `->` giúp tránh lỗi fall-through vô tình của switch statement cổ điển.

## 7. Objects và StandardCharsets: nền tảng nhỏ, tác động lớn

### 7.1. Kiểm tra null rõ ràng

`java.util.Objects` có từ Java 7, với các tiện ích như `requireNonNull`, `equals`, `hash`, `toString`. Ví dụ:

```java
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class EncodingUtil {
    public static byte[] utf8(String text) {
        return Objects.requireNonNull(text, "text")
                      .getBytes(StandardCharsets.UTF_8);
    }
}
```

Đây là **class thư viện**, không có `main`. `requireNonNull` giúp báo lỗi sớm tại ranh giới API khi null là không hợp lệ; không thay thế validation về định dạng, độ dài, quyền truy cập hay các ràng buộc nghiệp vụ. `Objects.equals(a, b)` hữu ích khi một trong hai tham chiếu có thể null.

### 7.2. Mã hóa ký tự nhất quán

`StandardCharsets.UTF_8`, `US_ASCII`, `ISO_8859_1`, `UTF_16`... là hằng `Charset` chuẩn có từ Java 7. Chỉ định charset rõ trong file, giao thức, serialization và integration để kết quả dễ dự đoán giữa môi trường chạy. UTF-8 là lựa chọn phổ biến cho văn bản hiện đại, nhưng **đừng thay đổi encoding của dữ liệu/protocol đã có hợp đồng khác**.

Java 18 chuẩn hóa mặc định UTF-8 trên nhiều API trong JDK, nhưng code xử lý dữ liệu có hợp đồng encoding vẫn nên ghi charset tường minh khi có thể. Khi thao tác dữ liệu nhị phân, dùng byte stream thay vì tự ép sang chuỗi.

## 8. Đồng thời: Fork/Join và ThreadLocalRandom vẫn hữu ích

### 8.1. ForkJoinPool cho bài toán CPU có thể chia nhỏ

`ForkJoinPool`, `RecursiveTask` / `RecursiveAction` xuất hiện từ Java 7. Mô hình *fork/join* tách bài toán thành phần nhỏ, cho các worker xử lý song song rồi kết hợp kết quả. Work-stealing cho phép worker rảnh lấy bớt việc của worker khác.

Lưu thành `ForkJoinDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinDemo {
    static final class SumTask extends RecursiveTask<Long> {
        private final long fromInclusive;
        private final long toExclusive;

        SumTask(long fromInclusive, long toExclusive) {
            this.fromInclusive = fromInclusive;
            this.toExclusive = toExclusive;
        }

        @Override
        protected Long compute() {
            if (toExclusive - fromInclusive <= 1_000) {
                long total = 0;
                for (long n = fromInclusive; n < toExclusive; n++) {
                    total += n;
                }
                return total;
            }

            long middle = fromInclusive + (toExclusive - fromInclusive) / 2;
            SumTask left = new SumTask(fromInclusive, middle);
            left.fork();
            long rightResult = new SumTask(middle, toExclusive).compute();
            return left.join() + rightResult;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool();
        try {
            System.out.println(pool.invoke(new SumTask(1, 101)));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 ForkJoinDemo.java
java ForkJoinDemo
```

```text
5050
```

`RecursiveTask<Long>` trả giá trị; `RecursiveAction` dùng khi không cần kết quả. Ví dụ rất nhỏ nên **không có lợi thế hiệu năng** so với vòng lặp tuần tự: chỉ phân việc khi kích thước bài toán, overhead và cách kết hợp kết quả cho phép. Giám sát contention và lựa chọn ngưỡng tách hợp lý.

**Giới hạn:** Fork/Join phù hợp nhất với tính toán CPU chia nhỏ; không lấy nó làm mặc định cho mọi yêu cầu chờ mạng/database. Các lựa chọn hiện đại như `ExecutorService`, `CompletableFuture` (Java 8) hoặc virtual threads (Java 21) phục vụ các bài toán khác nhau; chọn theo đặc tính tác vụ thay vì theo “mới nhất”.

### 8.2. ThreadLocalRandom

`ThreadLocalRandom` (Java 7) tạo số ngẫu nhiên tiện dụng trong môi trường nhiều luồng, giảm cạnh tranh trên nguồn sinh số dùng chung:

```java
import java.util.concurrent.ThreadLocalRandom;

int dice = ThreadLocalRandom.current().nextInt(1, 7); // 1..6
```

Đây là **snippet minh họa đặt bên trong method**; kết quả mỗi lần chạy khác nhau. Không dùng `ThreadLocalRandom` để tạo token, mật khẩu, mã OTP hay khóa bí mật: các mục đích bảo mật phải dùng nguồn ngẫu nhiên mật mã phù hợp, như `SecureRandom`.

### 8.3. MethodHandle và invokedynamic: biết để đọc tài liệu JVM

Java 7 đưa vào `java.lang.invoke.MethodHandle` và bytecode `invokedynamic`, mở đường cho cơ chế liên kết lời gọi linh hoạt của JVM. Từ Java 8, nhiều biểu thức lambda được triển khai thông qua hạ tầng `invokedynamic`. Đây là **kiến thức nền cho người tìm hiểu JVM, thư viện và framework**, không phải yêu cầu phải tự viết `MethodHandle` để thay lời gọi method thông thường.

## 9. Phân biệt phần Java 7 và các lớp tiện ích được bổ sung sau

| Thành phần / cách viết | Từ phiên bản | Ý nghĩa khi đọc source code hôm nay |
| --- | --- | --- |
| `try (Resource r = ...)`, `AutoCloseable` | 7 | Cơ chế gốc quản lý tài nguyên |
| `Path` / `Files` / `StandardCharsets` / `Objects` | 7 | API nền tảng còn dùng |
| `new HashMap<>()`, `catch (A \| B e)`, `switch` trên String | 7 | Cú pháp vẫn hợp lệ |
| `ForkJoinPool`, `ThreadLocalRandom` | 7 | Công cụ concurrency phù hợp tình huống |
| Lambda, Stream, `Map.computeIfAbsent`, `Files.list` | 8 | Có thể kết hợp trên nền Java 7 |
| Dùng biến effectively final trực tiếp trong `try (resource)` | 9 | Cú pháp TWR mở rộng |
| `Path.of`, `Files.readString` / `writeString` | 11 | Convenience API trên nền NIO.2 |
| Switch expression `return switch (...)` | 14 | Cách viết rõ ràng cho switch có kết quả |
| `Stream.toList` | 16 | Thu thập stream thành danh sách không sửa được |
| Virtual threads | 21 | Giải pháp khác cho nhiều tác vụ chờ I/O |

Cột phiên bản chỉ nói **lúc tính năng/API được đưa vào**; việc chọn API cần xét phiên bản JDK của project, hợp đồng dữ liệu, hiệu năng và khả năng bảo trì. Không nên sao chép nguyên một ví dụ JDK 17 rồi kỳ vọng chạy trên `--release 7`.

## 10. Tình huống thực tế và nguyên tắc chọn giải pháp

**Tình huống A — nhập file cấu hình:** Biểu diễn vị trí bằng `Path`, đọc với `Files` và UTF-8 chỉ định rõ, dùng `try-with-resources` nếu mở reader/stream, xử lý `IOException` riêng với lỗi cú pháp. Với file lớn, xử lý tuần tự thay vì đọc hết vào RAM.

**Tình huống B — xuất báo cáo tạm:** Tạo file tạm bằng `Files.createTempFile`, dùng stream/writer trong `try-with-resources`, dọn file tạm đúng trách nhiệm trong `finally`. Nếu cần thay file đích, xem xét phương án ghi file tạm và move, đồng thời tính đến khả năng move không atomic.

**Tình huống C — phân nhóm dữ liệu:** Giữ kiểu `Map<String, List<Item>>` cụ thể, khởi tạo bằng diamond. Dùng `computeIfAbsent` khi JDK hỗ trợ; tránh raw type và unchecked cast nếu có cách giữ generic đầy đủ.

**Tình huống D — tính toán nặng:** Đo profile trước; chỉ áp dụng `ForkJoinPool` khi thuật toán thật sự chia nhỏ hiệu quả. Không chọn thread pool cho file/network I/O chỉ vì “xử lý song song” nghe có vẻ nhanh.

## 11. Các nhầm lẫn cần tránh

- **“Java 7 = API lỗi thời”:** sai. Nhiều API từ Java 7 vẫn là nền móng cho ứng dụng Java hiện đại; điều quan trọng là chọn mô hình còn phù hợp.
- **“try-with-resources bắt hết lỗi”:** sai. Nó quản lý đóng tài nguyên; lỗi đọc/ghi vẫn cần được xử lý hoặc truyền đi, và lỗi đóng có thể nằm trong `getSuppressed()`.
- **“Path luôn trỏ tới file có thật”:** sai. `Path` có thể chỉ là một đường dẫn chưa tồn tại.
- **“Files.exists trước rồi write là an toàn”:** sai vì race condition.
- **“Diamond biến generic thành kiểm tra kiểu runtime”:** sai; generic Java vẫn chịu type erasure.
- **“Tất cả switch String an toàn với null”:** sai; cần xác định rõ semantic theo ngôn ngữ và JDK sử dụng.
- **“Mọi API trong ví dụ đều có từ Java 7”:** sai. Ví dụ hiện đại thường kết hợp nền Java 7 với API từ Java 8, 11, 14, 16 trở đi.
- **“ForkJoinPool phù hợp mọi việc bất đồng bộ”:** sai; nó chủ yếu hữu ích cho chia nhỏ công việc tính toán.

## 12. Tự kiểm tra và luyện tập

1. Một lỗi xảy ra trong thân `try`, lỗi khác xảy ra trong `close()`: lỗi nào là chính, tìm lỗi còn lại bằng method nào? **Đáp án:** lỗi trong thân `try` là chính; lỗi đóng ở `getSuppressed()`.
2. `Path.of("logs", "app.log")` có tạo file không? **Đáp án:** không; nó chỉ tạo đối tượng đường dẫn. `Path.of` là API từ Java 11.
3. `new HashMap<>()` và `map.computeIfAbsent(...)` có xuất hiện cùng phiên bản không? **Đáp án:** không; diamond có từ Java 7, `computeIfAbsent` từ Java 8.
4. Khi nào dùng `ThreadLocalRandom`, khi nào dùng `SecureRandom`? **Đáp án:** `ThreadLocalRandom` cho giá trị ngẫu nhiên thông thường trong code nhiều luồng; `SecureRandom` cho yêu cầu ngẫu nhiên mật mã.
5. Tại sao `Files.list(directory)` nên nằm trong `try-with-resources`? **Đáp án:** stream kết quả dùng tài nguyên thư mục cần được đóng.
6. **Bài thực hành:** Viết chương trình nhận tên file từ tham số dòng lệnh, dùng `Path` và UTF-8 để đếm số dòng, in thông báo rõ khi file vắng mặt hoặc không được đọc; dùng API stream/file reader có vòng đời tài nguyên đúng.
7. **Bài thực hành:** Viết chương trình phân loại phần mở rộng `"json"` / `"yaml"` / `"txt"` bằng switch expression; thử input viết hoa và `null`, rồi thiết kế quy tắc normalize/validation có chủ ý.

**Ghi nhớ:** Giá trị lâu dài của Java 7 nằm ở nguyên tắc **đóng tài nguyên đúng vòng đời, thao tác filesystem qua Path/Files, xử lý ngoại lệ có nghĩa, giữ generic rõ ràng và chọn công cụ concurrency đúng bài toán**. Khi dùng JDK hiện đại, tiếp tục kế thừa các nguyên tắc đó với cú pháp/API mới đã được ghi rõ phiên bản.
