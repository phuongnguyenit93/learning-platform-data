# Xử lý checked exception trong lambda của Stream

## 1. Vấn đề: mã hợp lệ trong vòng lặp có thể không biên dịch trong Stream

Trong **JAVA_STREAM_API**, ta dùng các pipeline lazy với `filter`, `map`, `reduce`, `collect` để xử lý dữ liệu khai báo. Tuy nhiên, nhiều thao tác thực tế như đọc file, gọi API dùng thư viện Java cũ, truy vấn JDBC hoặc phân tích dữ liệu với API có kiểm tra ngoại lệ có thể ném **checked exception**. Khi chuyển một vòng lặp sang Stream, câu lệnh `throws IOException` trong một phương thức **không tự làm cho lambda bên trong `map` chấp nhận IOException**.

Xét ví dụ:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class CheckedExceptionProblem {

    static List<String> loadFiles(List<Path> paths)
        throws IOException {

        // KHÔNG BIÊN DỊCH:
        // return paths.stream()
        //     .map(Files::readString)
        //     .toList();

        throw new UnsupportedOperationException(
            "Ví dụ trên minh họa lỗi compile"
        );
    }
}
~~~

`Files.readString(Path)` khai báo `throws IOException`. Trong khi đó, `Stream.map` yêu cầu một `Function<? super T, ? extends R>`, mà `Function.apply` **không khai báo checked exception**. Java từ chối gán phương thức có checked exception chưa được xử lý vào vị trí này.

Bài thuộc chương **Ngoại lệ và tính an toàn**, tập trung vào cách xử lý chính xác và minh bạch các lỗi phát sinh trong lambda của Stream. Sau khi học, bạn sẽ:

- Phân biệt **checked**, **unchecked exception** và thông báo lỗi biên dịch.
- Chọn giữa **xử lý tại chỗ**, **bọc thành unchecked exception**, **đưa lỗi thành dữ liệu** và **quay lại vòng lặp**.
- Viết adapter `IOFunction`/`IOPredicate` có chính sách rõ ràng, không nuốt lỗi.
- Giữ nguyên `cause` và bối cảnh bản ghi gây lỗi khi chuyển exception.
- Hiểu thời điểm exception xuất hiện do **lazy evaluation** và ảnh hưởng của short-circuit.
- Đóng tài nguyên đúng với `Files.lines` và phân biệt lỗi khi mở nguồn với lỗi trong lúc tiêu thụ.
- Xử lý trường hợp parallel stream, số lỗi không được quan sát, side effect đã thực hiện và interruption.
- Thiết kế ví dụ kiểm thử bằng Java 17+ để xác nhận lỗi thành công, lỗi thất bại và dữ liệu không bị âm thầm biến mất.

**Phạm vi:** Các ví dụ dùng Java 17+, có thể áp dụng những ý tưởng chính cho Java 8 bằng cách đổi cú pháp tương thích. Đây là bài về Java Stream API; không giả định có cơ chế `onErrorContinue` hay toán tử xử lý lỗi của thư viện reactive bên ngoài.

## 2. Tại sao Function, Predicate và Consumer không khai báo throws?

Các functional interface tiêu chuẩn trong `java.util.function` có dạng khái niệm:

~~~java
@FunctionalInterface
interface Function<T, R> {
    R apply(T value);
}

@FunctionalInterface
interface Predicate<T> {
    boolean test(T value);
}

@FunctionalInterface
interface Consumer<T> {
    void accept(T value);
}
~~~

Đây là **các phiên bản rút gọn để giải thích**; API thực tế còn có các default/static method. Điểm quan trọng là các abstract method trên **không có `throws IOException` hoặc `throws SQLException`**.

| Vị trí trong pipeline | Functional interface điển hình | Phần thân có thể ném checked exception trực tiếp? |
| --- | --- | --- |
| `map(mapper)` | `Function<T,R>` | Không, nếu exception chưa được xử lý |
| `filter(predicate)` | `Predicate<T>` | Không |
| `forEach(action)` | `Consumer<T>` | Không |
| `flatMap(mapper)` | `Function<T,Stream<R>>` | Không |
| `sorted(comparator)` | `Comparator<T>` | Không |
| `collect(collector)` | Các callback accumulator/combiner/finisher | Không tự cho phép checked exception |
| `reduce(accumulator)` | `BinaryOperator<T>` | Không |
| Phương thức vòng lặp bình thường có `throws IOException` | Không có functional interface chặn | Có, nếu phương thức khai báo hoặc xử lý đúng |

### Checked và unchecked exception

- **Checked exception:** phần lớn subclass của `Exception` không phải `RuntimeException`, ví dụ `IOException`, `SQLException`, `ParseException`. Trình biên dịch yêu cầu bắt hoặc khai báo `throws` tại nơi có thể ném.
- **Unchecked exception:** `RuntimeException` và các subclass như `IllegalArgumentException`, `NumberFormatException`, `UncheckedIOException`; cũng như `Error`. Java không bắt buộc khai báo `throws`.
- **Error:** ví dụ `OutOfMemoryError`; không nên đưa vào một adapter tổng quát rồi coi là lỗi dữ liệu thông thường.

Ngay cả khi một phương thức bao ngoài khai báo `throws IOException`, lambda dùng làm `Function.apply` vẫn không thể để IOException thoát trực tiếp theo hợp đồng của target type:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

// SAI: khai báo throws ở phương thức bao ngoài không đủ.
static List<String> invalid(List<Path> paths) throws IOException {
    // return paths.stream().map(Files::readString).toList();
    throw new UnsupportedOperationException("Minh họa");
}
~~~

**Nguyên tắc:** Java kiểm tra checked exception theo **kiểu đích của lambda/method reference**, không chỉ theo khai báo của phương thức bao ngoài.

## 3. Trước khi viết try/catch: xác định chính sách khi gặp lỗi

Không có một “mẹo lambda” đúng cho mọi nghiệp vụ. Hãy chọn chính sách thất bại trước:

| Chính sách | Ý nghĩa | Tình huống phù hợp | Rủi ro nếu dùng sai |
| --- | --- | --- | --- |
| **Fail-fast** | Ngừng xử lý và báo lỗi | Mọi file bắt buộc phải đọc được; dữ liệu tài chính | Kết quả từng phần/side effect có thể đã xảy ra |
| **Fallback** | Dùng giá trị dự phòng | Thiếu cấu hình tùy chọn, nội dung cache có thể thay thế | Dễ che sự cố nếu fallback không có nghĩa hợp lệ |
| **Skip + ghi nhận** | Bỏ bản ghi lỗi, vẫn báo cáo đầy đủ | Import best-effort, xử lý dữ liệu bẩn | Nếu chỉ skip mà không ghi lỗi sẽ mất dữ liệu im lặng |
| **Error as data** | Trả `Success/Failure` cho từng bản ghi | Cần tổng hợp nhiều lỗi và hiển thị cho người dùng | Cần thêm kiểu kết quả và bước phân loại |
| **Xử lý ngoài Stream** | Dùng vòng lặp hoặc API chuyên dụng | Kiểm soát transaction, retry, cleanup, break | Dài hơn nhưng đôi khi đúng và dễ đọc hơn |

Ví dụ: với danh sách đường dẫn tài liệu bắt buộc, đọc thất bại một file có thể phải làm hỏng cả batch. Nhưng với import 1.000 dòng, yêu cầu có thể là **thu đủ các dòng lỗi**, vẫn tạo báo cáo những dòng hợp lệ và **chỉ commit khi bộ phận nghiệp vụ chấp thuận**.

Mọi giải pháp trong bài đều phải trả lời được ba câu hỏi:

1. **Lỗi có bị mất không?**
2. **Dữ liệu thành công có còn được dùng đúng không?**
3. **Chính sách dừng hoặc tiếp tục có đúng với giao dịch và nghiệp vụ không?**

## 4. Cách 1 — try/catch ngay trong lambda

Cách trực tiếp nhất là bắt checked exception tại nơi phát sinh và biến nó thành **kết quả hợp lệ có ý nghĩa** hoặc thành **unchecked exception**.

### 4.1. Fail-fast: bọc IOException thành UncheckedIOException

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class LocalCatchDemo {

    static List<String> readAll(List<Path> paths) {
        return paths.stream()
            .map(path -> {
                try {
                    return Files.readString(path);
                } catch (IOException ex) {
                    throw new UncheckedIOException(
                        "Không đọc được file: " + path, ex
                    );
                }
            })
            .toList();
    }
}
~~~

Ở đây:

- `try/catch` giải quyết checked exception tại lambda.
- `UncheckedIOException` là subclass của `RuntimeException` dành riêng cho `IOException`.
- Thông điệp thêm **đường dẫn file**, giúp truy vết bản ghi thất bại.
- Ngoại lệ gốc được giữ trong `ex.getCause()`, không bị thay bằng một chuỗi thông báo đơn thuần.
- Khi một `IOException` xuất hiện trong quá trình đánh giá pipeline, terminal operation có thể kết thúc bằng unchecked exception.

### 4.2. Fallback tường minh: chỉ khi được phép

Nếu thiếu một file cấu hình tùy chọn có thể chấp nhận giá trị mặc định, có thể trả fallback:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String readOptionalConfiguration(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        // Chỉ hợp lệ nếu mọi IOException đều được
        // nghiệp vụ cho phép xử lý bằng fallback.
        return "mode=DEFAULT";
    }
}
~~~

**Thận trọng:** `IOException` không chỉ có nghĩa “file không tồn tại”. Nó còn có thể là lỗi quyền truy cập, đĩa hỏng hoặc dữ liệu đọc thất bại. Nếu chỉ muốn fallback khi file **không tồn tại**, hãy bắt ngoại lệ cụ thể hơn:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

static String readConfigOrDefault(Path path) throws IOException {
    try {
        return Files.readString(path);
    } catch (NoSuchFileException missing) {
        return "mode=DEFAULT";
    }
}
~~~

Phương thức này vẫn khai báo `throws IOException` cho những lỗi I/O khác. Nếu đưa nó vào `map`, ta **vẫn cần** adapter hoặc catch tương ứng cho các IOException có thể còn lại.

### 4.3. Vì sao không nên `catch (Exception) { return null; }`?

Mẫu này có thể biến lỗi đọc file thành phần tử `null` mà downstream không biết lý do; sau đó `filter(Objects::nonNull)` xóa dấu vết lỗi. Nó còn có thể nuốt những `RuntimeException` không mong đợi như lỗi lập trình.

Nếu muốn bỏ dòng lỗi, hãy biểu diễn lỗi một cách **quan sát được**: trả kiểu `Failure`, ghi nhận vào danh sách kết quả hoặc báo cáo lỗi ở tầng gọi. Không dùng `null`/chuỗi rỗng như thay thế mặc định cho mọi lỗi.

## 5. Cách 2 — Viết IOFunction adapter để tái sử dụng

Khi nhiều pipeline cùng làm I/O, việc lặp `try/catch` trong từng `map` làm code khó đọc. Có thể định nghĩa một functional interface **cho phép ném IOException**, rồi chuyển nó sang `Function` chuẩn.

### Chương trình Java 17+ hoàn chỉnh

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class IOFunctionAdapter {

    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> uncheckedIO(
        IOFunction<T, R> function
    ) {
        Objects.requireNonNull(function, "function");

        return value -> {
            try {
                return function.apply(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static List<String> readAll(List<Path> paths) {
        return paths.stream()
            .map(uncheckedIO((Path path) -> Files.readString(path)))
            .toList();
    }
}
~~~

Điểm quan trọng:

- `IOFunction.apply` khai báo `throws IOException`, nên cho phép biểu thức `Files.readString(path)` bên trong.
- `uncheckedIO` tạo một `Function<T,R>` hợp lệ cho Stream.
- Adapter giữ `IOException` làm cause, không viết kỹ thuật “sneaky throw” để đánh lừa kiểu ngoại lệ.
- `Objects.requireNonNull(function)` bắt lỗi lập trình ngay lúc tạo adapter.

### Giữ bối cảnh file gây lỗi trong adapter

Adapter tổng quát không biết đường dẫn hoặc tên bản ghi. Nếu thông báo lỗi cần có bối cảnh, hãy bổ sung tại lambda gọi:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

static List<String> load(List<Path> paths) {
    return paths.stream()
        .map(IOFunctionAdapter.uncheckedIO((Path path) -> {
            try {
                return Files.readString(path);
            } catch (IOException ex) {
                throw new IOException(
                    "Đọc thất bại: " + path, ex
                );
            }
        }))
        .toList();
}
~~~

Trong ví dụ này, `IOException` mới có bối cảnh đường dẫn và vẫn giữ cause ban đầu; adapter tiếp tục bọc thành `UncheckedIOException` để phù hợp với `Function`.

**Không nhầm:** Một adapter giúp **chuyển cơ chế báo lỗi**, không tự quyết định liệu lỗi đó nên dẫn tới retry, skip, rollback hay hiển thị cho người dùng. Chính sách ở các tầng ngoài phải còn rõ ràng.

## 6. Cách 3 — Adapter cho Predicate hoặc Consumer có checked exception

`filter` cần `Predicate<T>`; `forEach` cần `Consumer<T>`. Vì các interface này cũng không có checked `throws`, ý tưởng adapter tương tự.

### 6.1. IOPredicate với Files.size

`Files.size(path)` có thể ném `IOException`. Nếu muốn lọc những file có kích thước lớn hơn 0:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.function.Predicate;

public class IOPredicateDemo {

    @FunctionalInterface
    interface IOPredicate<T> {
        boolean test(T value) throws IOException;
    }

    static <T> Predicate<T> uncheckedIO(IOPredicate<T> predicate) {
        return value -> {
            try {
                return predicate.test(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static List<Path> nonEmptyFiles(List<Path> paths) {
        return paths.stream()
            .filter(uncheckedIO(path -> Files.size(path) > 0L))
            .toList();
    }
}
~~~

**Lưu ý nghiệp vụ:** Lọc theo `Files.size` rồi sau đó đọc file có thể gặp tình huống file thay đổi giữa hai bước (*time-of-check to time-of-use*, TOCTOU). Đừng coi kiểm tra size trước như bảo đảm lệnh đọc sau chắc chắn thành công.

### 6.2. IOConsumer cho thao tác có side effect

Một `IOConsumer<T>` cũng có thể được bọc. Tuy nhiên, với các thao tác ghi file hoặc gửi request, dùng `forEach` kèm side effect cần được xem xét kỹ:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Consumer;

@FunctionalInterface
interface IOConsumer<T> {
    void accept(T value) throws IOException;
}

static <T> Consumer<T> uncheckedIOConsumer(IOConsumer<T> action) {
    return value -> {
        try {
            action.accept(value);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    };
}
~~~

Đoạn trên là **snippet** định nghĩa interface và hàm, không phải chương trình độc lập. Nó chuyển ngoại lệ nhưng **không khiến các side effect trở thành nguyên tử**. Nếu `forEach` đã ghi 4 file rồi file thứ 5 lỗi, 4 file đầu có thể đã tồn tại. Với `parallelStream().forEach(...)`, thứ tự thực hiện càng không thể dựa theo encounter order.

Nếu cần **giao dịch toàn bộ hoặc không gì cả**, hãy sử dụng cơ chế transaction/staging/commit phù hợp, hoặc một vòng lặp tuần tự với rollback rõ ràng; không kỳ vọng việc ném exception sẽ tự hoàn tác những side effect đã xảy ra.

## 7. Cách 4 — Chuyển lại checked exception tại ranh giới API

Có khi API công khai phải khai báo `throws IOException` thay vì để lộ `UncheckedIOException`. Ta vẫn có thể dùng Stream bên trong rồi **khôi phục checked exception ở tầng ngoài**.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class CheckedBoundaryDemo {

    static List<String> readAll(List<Path> paths)
        throws IOException {

        try {
            return paths.stream()
                .map(IOFunctionAdapter.uncheckedIO(
                    (Path path) -> Files.readString(path)
                ))
                .toList();

        } catch (UncheckedIOException ex) {
            throw ex.getCause();
        }
    }
}
~~~

`UncheckedIOException.getCause()` trả `IOException` gốc, nên người gọi có thể dùng `catch (IOException e)` theo hợp đồng của phương thức. Nếu cần giữ đường dẫn, hãy dùng adapter có bổ sung bối cảnh như mục 5.

Đây là **chuyển đổi có kiểm soát tại boundary**. Không dùng `throw (IOException) ex.getCause()` cho một `RuntimeException` tổng quát nếu không biết chắc cause có kiểu đó; dùng wrapper có type rõ ràng để tránh `ClassCastException` thứ cấp.

### Khi nào nên chọn ranh giới throws?

- API thư viện của bạn có hợp đồng checked exception và người gọi cần xử lý theo loại lỗi.
- Tầng nghiệp vụ đã có chiến lược retry hoặc fallback cho `IOException`.
- Bạn muốn giữ `IOException` như một phần rõ ràng của public API.

Nếu bên trong pipeline có nhiều loại ngoại lệ như `IOException` và `SQLException`, nên thiết kế một lớp lỗi domain hoặc tách các thao tác, thay vì cố ép mọi lỗi thành một `IOException` sai ngữ nghĩa.

## 8. Cách 5 — Một phương thức thường xử lý I/O, Stream chỉ còn biến đổi thuần

Không phải lúc nào việc bọc checked exception vào lambda cũng là lựa chọn tốt. Đôi khi cách rõ ràng nhất là **thực hiện I/O ở ranh giới ngoài** rồi sử dụng Stream để xử lý dữ liệu đã có trong bộ nhớ.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ReadThenTransform {

    static List<String> cleanedLines(Path path)
        throws IOException {

        // I/O ở API boundary, có thể throws IOException.
        String text = Files.readString(path);

        // Stream xử lý dữ liệu đã được đọc vào bộ nhớ.
        return text.lines()
            .map(String::strip)
            .filter(line -> !line.isEmpty())
            .toList();
    }
}
~~~

Cách này tránh phải viết adapter vì `String.lines()` không thực hiện I/O từ file nữa. Tuy nhiên, nó **đọc toàn bộ file vào bộ nhớ**; không hợp lý với file rất lớn. Khi cần streaming I/O, `Files.lines` và quản lý tài nguyên đúng là lựa chọn khác ở mục sau.

**Bài học thiết kế:** Nên tách “lấy dữ liệu có thể lỗi” khỏi “biến đổi dữ liệu thuần” khi điều đó làm lỗi dễ quan sát, code dễ kiểm thử và chi phí bộ nhớ phù hợp.

## 9. Lazy evaluation: checked exception có thể xuất hiện tại terminal

Phép `map` là intermediate operation **lazy**. Callback đọc file không được chạy chỉ vì ta đã định nghĩa pipeline:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class LazyFailureDemo {

    static Stream<String> buildPipeline(List<Path> paths) {
        return paths.stream().map(path -> {
            try {
                return Files.readString(path);
            } catch (IOException ex) {
                throw new UncheckedIOException(
                    "Lỗi khi đọc " + path, ex
                );
            }
        });
    }

    static List<String> execute(List<Path> paths) {
        Stream<String> pipeline = buildPipeline(paths);
        // Chưa đọc file nào chỉ vì pipeline được tạo.
        return pipeline.toList(); // Lỗi I/O có thể nổi lên tại đây.
    }
}
~~~

### Chỗ đặt try/catch phải bao quanh terminal

~~~java
try {
    List<String> result = LazyFailureDemo.execute(paths);
    // Chỉ dùng result khi terminal hoàn tất thành công.
} catch (UncheckedIOException ex) {
    System.err.println("Lỗi I/O: " + ex.getCause());
}
~~~

Đoạn trên là snippet giả định biến `paths` đã được khai báo; mục đích là chỉ ra vị trí xử lý exception.

Nếu xây pipeline trong một khối `try` nhưng chạy terminal **sau khi rời khỏi khối đó**, ngoại lệ của mapper sẽ xảy ra muộn hơn và không được catch tại chỗ xây dựng pipeline.

### Short-circuit làm thay đổi những phần tử được xét

~~~java
import java.util.List;

List<String> first = names.stream()
    .map(name -> potentiallyFailingTransform(name))
    .limit(1)
    .toList();
~~~

Đây là snippet với `potentiallyFailingTransform` do ứng dụng định nghĩa. `limit(1)` chỉ cần một phần tử đầu ra, nên những phần tử phía sau có thể **chưa từng chạy mapper**. Tương tự, `findFirst`, `findAny`, `anyMatch` và `noneMatch` có thể kết thúc sớm.

**Hệ quả:** Không dùng `map` có side effect để kỳ vọng “kiểm tra hết mọi file và ném mọi lỗi” nếu terminal có khả năng short-circuit. Muốn báo cáo đầy đủ, cần thiết kế bước xử lý hết nguồn và lưu kết quả mỗi bản ghi thành dữ liệu.


## 10. Cách 6 — Biểu diễn lỗi như dữ liệu bằng Success và Failure

Khi yêu cầu là **thu thập tất cả bản ghi lỗi** thay vì chỉ dừng ở lỗi đầu tiên, fail-fast không đủ. Có thể dùng một kiểu kết quả với hai nhánh `Success` và `Failure`; mỗi phần tử của Stream tạo **đúng một kết quả có trạng thái**.

### Ví dụ Java 17+ hoàn chỉnh và không cần file ngoài

~~~java
import java.io.IOException;
import java.util.List;

public class ReadOutcomeDemo {

    sealed interface Outcome permits Success, Failure {}

    record Success(String sourceId, String content)
        implements Outcome {}

    record Failure(String sourceId, IOException error)
        implements Outcome {}

    record Report(
        List<Success> successes,
        List<Failure> failures
    ) {}

    // Mô phỏng nguồn đọc có thể ném IOException.
    static String load(String sourceId) throws IOException {
        if (sourceId.startsWith("bad")) {
            throw new IOException("Không đọc được " + sourceId);
        }
        return "DATA:" + sourceId;
    }

    static Outcome read(String sourceId) {
        try {
            return new Success(sourceId, load(sourceId));
        } catch (IOException ex) {
            return new Failure(sourceId, ex);
        }
    }

    static Report scan(List<String> sourceIds) {
        // Chỉ thực hiện thao tác đọc một lần cho mỗi source.
        List<Outcome> results = sourceIds.stream()
            .map(ReadOutcomeDemo::read)
            .toList();

        List<Success> good = results.stream()
            .filter(Success.class::isInstance)
            .map(Success.class::cast)
            .toList();

        List<Failure> bad = results.stream()
            .filter(Failure.class::isInstance)
            .map(Failure.class::cast)
            .toList();

        return new Report(good, bad);
    }

    public static void main(String[] args) {
        Report report = scan(List.of(
            "doc-1", "bad-2", "doc-3", "bad-4"
        ));

        System.out.println(report.successes().size()); // 2
        System.out.println(report.failures().size());  // 2

        report.failures().forEach(f ->
            System.out.println(
                f.sourceId() + ": " + f.error().getMessage()
            )
        );
    }
}
~~~

**Tại sao cách này hữu ích?**

- Lambda trong `map` không để checked exception thoát ra; `read` đã bắt `IOException` và trả một value object.
- Không cần một `List<Exception>` mutable dùng chung làm side effect.
- Dữ liệu lỗi và dữ liệu thành công được tách **sau khi đã materialize một lần** thành `List<Outcome>`, tránh thực hiện I/O hai lần.
- `Failure` giữ ID nguồn và exception, phù hợp khi cần báo cáo từng dòng.
- Kết quả `toList()` giữ thứ tự đầu vào từ `List` trong ví dụ, nhưng object `IOException` bên trong không trở thành immutable sâu.

Trong ứng dụng thật, thay `load(sourceId)` bằng `Files.readString(path)` hoặc API I/O của dự án. Nếu muốn biểu diễn nhiều loại lỗi, có thể dùng `record Failure(SourceId id, ErrorCode code, String message, Throwable cause)` hoặc một sealed hierarchy chi tiết hơn.

### Không biến mọi bug thành lỗi dữ liệu

Ví dụ chỉ bắt `IOException`. Nếu `sourceId == null` dẫn tới `NullPointerException` trong `startsWith`, đó là vi phạm hợp đồng đầu vào và cần được kiểm tra riêng. Không dùng `catch (Exception)` để coi mọi lỗi, bao gồm lỗi lập trình, là một bản ghi “không đọc được”.

### Fail-fast hay thu thập đủ lỗi?

| Mục tiêu | Phương án |
| --- | --- |
| Một file hỏng thì toàn bộ batch phải thất bại | Bọc lỗi rồi fail-fast hoặc kiểm tra toàn bộ trước commit |
| Cần báo cáo mọi file hỏng để người dùng sửa | `Outcome` cho từng nguồn, không short-circuit |
| Có thể chấp nhận một phần thành công | Trả cả danh sách thành công và lỗi, công bố rõ trạng thái partial |
| Chỉ một loại lỗi cho phép fallback | Catch loại exception cụ thể |
| Cần bảo đảm ghi dữ liệu all-or-nothing | Kết hợp kiểm tra đầu vào với transaction, không chỉ Stream |

**Đặc biệt:** Đọc/kiểm tra thành công một số bản ghi không đồng nghĩa đã có transaction thành công. Việc commit, rollback và idempotency phải được thiết kế riêng.

## 11. Files.lines: phân biệt lỗi mở nguồn và lỗi khi tiêu thụ

`Files.lines(path)` trả một Stream **gắn với tài nguyên file**, không phải collection thuần trong RAM. Có ít nhất ba giai đoạn cần lưu ý:

1. **Mở nguồn:** `Files.lines(path)` có thể ném checked `IOException`.
2. **Đọc lazy:** lỗi I/O khi terminal tiêu thụ các dòng có thể xuất hiện dưới dạng `UncheckedIOException`.
3. **Đóng nguồn:** cần `try-with-resources` để đóng Stream kể cả khi có lỗi.

### Ví dụ đúng về quản lý tài nguyên

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class FilesLinesDemo {

    static List<String> nonBlank(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(
                path, StandardCharsets.UTF_8)) {

            return lines
                .map(String::strip)
                .filter(s -> !s.isEmpty())
                .toList();
        }
    }
}
~~~

`throws IOException` tại phương thức xử lý lỗi checked khi **mở file**. Lỗi đọc trong terminal có thể đi lên dưới dạng `UncheckedIOException`. Nếu cần API chỉ công bố checked `IOException`, có thể chuyển ngược ở boundary:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

// Snippet phương thức sử dụng import phía trên.
static List<String> readLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        try {
            return lines.toList();
        } catch (UncheckedIOException ex) {
            throw ex.getCause();
        }
    }
}
~~~

`try-with-resources` vẫn đóng Stream khi có exception. Một phương thức **trả thẳng Stream của Files.lines** phải công bố rõ người gọi có trách nhiệm đóng; không thể trông chờ GC.

### Sai lầm: tạo Stream trong try-with-resources rồi trả nó ra ngoài

~~~java
// Sai: trả Stream đã bị đóng trước khi caller dùng.
// static Stream<String> broken(Path path) throws IOException {
//     try (Stream<String> lines = Files.lines(path)) {
//         return lines;
//     }
// }
~~~

Stream chỉ hợp lệ trong thời gian sống của tài nguyên. Nếu cần trả Stream cho caller, ownership phải được thiết kế rõ; nếu không, nên thực hiện terminal trong phạm vi `try-with-resources` rồi trả dữ liệu đã thu thập.

## 12. SQLException, ParseException và ngoại lệ nghiệp vụ khác

`UncheckedIOException` được thiết kế cho `IOException`, không nên ép `SQLException` vào lớp này. Với ngoại lệ checked khác, tạo **runtime exception có ý nghĩa theo domain** hoặc mô hình hóa lỗi thành dữ liệu.

~~~java
import java.sql.SQLException;
import java.util.function.Function;

public class SQLAdapter {

    @FunctionalInterface
    interface SQLFunction<T, R> {
        R apply(T value) throws SQLException;
    }

    static class DataAccessFailure extends RuntimeException {
        DataAccessFailure(String message, SQLException cause) {
            super(message, cause);
        }
    }

    static <T, R> Function<T, R> uncheckedSQL(
        SQLFunction<T, R> function
    ) {
        return value -> {
            try {
                return function.apply(value);
            } catch (SQLException ex) {
                throw new DataAccessFailure(
                    "Truy vấn database thất bại", ex
                );
            }
        };
    }
}
~~~

Adapter này chỉ **chuyển cách báo lỗi**, không làm JDBC trở thành thread-safe. Không chạy `parallelStream()` với một `Connection` hoặc `ResultSet` chia sẻ mà không có hợp đồng an toàn đồng thời. Retry, connection pooling, transaction, timeout phải được xử lý ở tầng truy cập dữ liệu.

Với `ParseException` hoặc exception domain riêng, chọn wrapper phù hợp và giữ `cause`. Tránh `throw new RuntimeException("Có lỗi")` mà bỏ mất nguyên nhân và ID bản ghi.

## 13. InterruptedException không được nuốt tùy tiện

Một số API chặn có thể ném `InterruptedException`. Đây thường là tín hiệu hủy/gián đoạn công việc. Nếu bắt nó trong lambda nhưng không thể khai báo checked exception theo `Function`, nên **khôi phục cờ interrupt** trước khi chuyển thành lỗi unchecked phù hợp, trừ khi API của bạn có thể đưa checked exception ra ngoài một cách minh bạch.

~~~java
import java.util.List;
import java.util.Locale;

public class InterruptDemo {

    static String transform(String input) {
        try {
            Thread.sleep(10L);
            return input.toUpperCase(Locale.ROOT);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Công việc bị gián đoạn", ex
            );
        }
    }

    public static void main(String[] args) {
        List<String> values = List.of("a", "b")
            .stream()
            .map(InterruptDemo::transform)
            .toList();

        System.out.println(values); // [A, B] nếu không interrupt.
    }
}
~~~

Khi `InterruptedException` được ném, cờ interrupt của thread thường đã bị xóa. Gọi `Thread.currentThread().interrupt()` giúp tầng điều phối biết có tín hiệu ngắt.

**Không nên:**

~~~java
// Sai: giả vờ xử lý thành công khi bị yêu cầu hủy.
// catch (InterruptedException ignored) { return ""; }
~~~

Với tác vụ bất đồng bộ/cancellation phức tạp, Stream không phải cơ chế thay thế executor/task framework. Đừng catch `Error` hoặc `Throwable` chỉ để giữ pipeline tiếp tục chạy.

## 14. Parallel Stream: lỗi nào xuất hiện không có thứ tự đảm bảo

Với `parallelStream`, nhiều nhánh có thể cùng đọc dữ liệu. Khi một nhánh ném lỗi, terminal có thể thất bại, nhưng **không bảo đảm báo đủ mọi lỗi** hay luôn báo lỗi ở phần tử có vị trí đầu tiên trong List.

~~~java
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

static List<String> readParallel(List<Path> paths) {
    try {
        return paths.parallelStream()
            .map(IOFunctionAdapter.uncheckedIO(
                (Path path) -> Files.readString(path)
            ))
            .toList();

    } catch (UncheckedIOException ex) {
        // Không khẳng định đây là file lỗi đầu tiên theo List.
        throw ex;
    }
}
~~~

Đây là snippet dùng adapter ở mục 5. Không xây logic nghiệp vụ dựa trên assumption về exception đầu tiên, thứ tự các cause, hay danh sách suppressed exception. Một số nhánh có thể đã hoàn thành side effect trước khi lỗi được quan sát.

### Không thu thập lỗi vào ArrayList chung trong parallel

~~~java
// Phản ví dụ: state mutable ngoài pipeline bị nhiều thread sửa.
// List<Exception> errors = new ArrayList<>();
// paths.parallelStream().map(path -> {
//     try { return read(path); }
//     catch (IOException ex) {
//         errors.add(ex); // Không an toàn.
//         return "";
//     }
// }).toList();
~~~

Một collection synchronized không tự giải quyết hợp đồng **đầy đủ, đúng thứ tự, transactional và quan sát lỗi**. Nếu cần mọi kết quả, chọn `Outcome` cho từng input, rồi dùng terminal không short-circuit để thu thập.

### I/O song song không đồng nghĩa nhanh hơn

Parallel Stream không tự cung cấp quota, rate limiting, retry, circuit breaker hay giới hạn connection. Với request bên ngoài, tăng đồng thời có thể gây quá tải hoặc vi phạm giới hạn dịch vụ. Hãy dùng tầng điều phối có kiểm soát nếu cần xử lý số lượng lớn tác vụ I/O.


## 15. Exception không tự rollback những side effect đã xảy ra

Một pipeline có thể đọc/biến đổi nhiều bản ghi rồi thực hiện ghi ra ngoài:

~~~java
// Pseudocode minh họa side effect.
// records.stream()
//     .map(this::validate)
//     .forEach(repository::save);
~~~

Nếu bản ghi thứ năm lỗi, bốn bản ghi trước **có thể đã được lưu**. Exception dừng việc đánh giá tiếp theo nhưng **không hoàn tác** những giao dịch hoặc file đã ghi. Với `parallelStream`, một số bản ghi phía sau lỗi cũng có thể đã được thực hiện.

**Một số lựa chọn an toàn hơn:**

1. **Validate trước, commit sau:** thu thập tất cả giá trị hợp lệ rồi chỉ ghi khi không có lỗi bắt buộc.
2. **Transaction/staging:** lưu vào vùng tạm hoặc transaction, commit khi toàn bộ thành công.
3. **Best-effort có báo cáo:** mỗi input có `Success/Failure`, không giả vờ tất cả đã thành công.
4. **Idempotent retry:** dùng request ID/khóa chống lặp khi nghiệp vụ cho phép retry.
5. **Vòng lặp có điều phối:** dễ xác định thứ tự, breakpoint, dừng và bước bù trừ.

Dù dùng vòng lặp hay Stream, việc rollback và idempotency vẫn phải được thiết kế **ở tầng hệ thống**, không phải đặc tính của `forEach`.

### Không phụ thuộc vào log trong peek để audit

`peek` là intermediate operation dùng quan sát/debug, không phải cơ chế audit chắc chắn. Stream có lazy evaluation, short-circuit và một số tối ưu hóa terminal; các callback không nhất thiết được gọi trên mọi input.

Đặc biệt với một Stream có kích thước biết trước, `count()` **có thể tính kết quả mà không cần thực hiện mapper** nếu mapper không làm thay đổi số phần tử:

~~~java
import java.util.List;

public class CountOptimizationWarning {
    public static void main(String[] args) {
        long count = List.of("A", "B").stream()
            .map(value -> {
                // Không được dùng mapper như bước audit bắt buộc.
                System.out.println("Đã xử lý " + value);
                return value.toLowerCase(java.util.Locale.ROOT);
            })
            .count();

        System.out.println(count); // 2
        // Không có bảo đảm hai dòng "Đã xử lý ..." sẽ được in.
    }
}
~~~

Điều này cũng có nghĩa không dùng `map` có side effect/exception rồi `count()` để “xác minh chắc chắn mọi file đã đọc”. Nếu muốn kiểm tra toàn bộ dữ liệu, hãy dùng một terminal thực sự cần kết quả biến đổi và mô hình hóa lỗi thành giá trị quan sát được.

## 16. Khi nào vòng lặp thường rõ ràng hơn Stream?

Không cần ép mọi I/O có checked exception vào pipeline. Với yêu cầu dừng ngay ở file đầu tiên không đọc được và public API vẫn khai báo `throws IOException`, một vòng lặp có thể là cách dễ đọc nhất.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class PlainLoopAlternative {

    static List<String> readRequiredFiles(List<Path> paths)
        throws IOException {

        List<String> texts = new ArrayList<>();

        for (Path path : paths) {
            texts.add(Files.readString(path));
        }

        return List.copyOf(texts);
    }
}
~~~

Ưu điểm của vòng lặp:

- Checked exception đi trực tiếp qua `throws IOException`.
- Có thể ghi nhận số dòng hoặc path trong exception ngay tại vị trí lỗi.
- Logic retry có giới hạn, `break`, `continue` và cleanup thường dễ theo dõi hơn.
- Không cần adapter nếu chỉ có một luồng xử lý I/O.
- Khi cần trạng thái giao dịch, thứ tự và quyết định rollback, câu lệnh tường minh có thể dễ kiểm toán hơn.

**Không có nghĩa vòng lặp luôn tốt hơn.** Với dữ liệu đã tải và những phép biến đổi thuần, Stream thường ngắn và dễ kết hợp. Hãy chọn cấu trúc làm **chính sách lỗi rõ nhất**, không chọn theo tiêu chí bắt buộc phải dùng phong cách functional.

## 17. Kiểm thử adapter bằng nguồn I/O giả lập

Không cần tạo file thật để kiểm tra một adapter chuyển `IOException` thành `UncheckedIOException`. Dùng hàm giả lập có một đầu vào gây lỗi để xác minh:

- Đường thành công giữ đúng dữ liệu.
- Đường lỗi ném đúng wrapper.
- `IOException` gốc vẫn được giữ dưới dạng cause.
- Test không nuốt lỗi do bắt nhầm ngoại lệ.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;

public class IOAdapterChecks {

    static String fakeRead(String id) throws IOException {
        if ("bad".equals(id)) {
            throw new IOException("cannot read bad");
        }
        return id.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<String> success = List.of("ok", "fine")
            .stream()
            .map(IOFunctionAdapter.uncheckedIO(
                (String id) -> fakeRead(id)
            ))
            .toList();

        if (!success.equals(List.of("OK", "FINE"))) {
            throw new AssertionError("Sai đường thành công");
        }

        try {
            List.of("ok", "bad")
                .stream()
                .map(IOFunctionAdapter.uncheckedIO(
                    (String id) -> fakeRead(id)
                ))
                .toList();

            throw new AssertionError("Đáng lẽ phải ném lỗi");

        } catch (UncheckedIOException ex) {
            IOException cause = ex.getCause();

            if (!"cannot read bad".equals(cause.getMessage())) {
                throw new AssertionError("Mất nguyên nhân", ex);
            }
        }

        System.out.println("PASS");
    }
}
~~~

`IOFunctionAdapter` là lớp đầy đủ ở mục 5. Hai lớp có thể đặt trong cùng package và biên dịch cùng nhau. Test dùng `throw new AssertionError` thay vì Java `assert` vì `assert` thường bị vô hiệu hóa nếu JVM không chạy với `-ea`.

### Kiểm tra đường trả lỗi thành dữ liệu

~~~java
import java.util.List;

public class OutcomeChecks {
    public static void main(String[] args) {
        ReadOutcomeDemo.Report report = ReadOutcomeDemo.scan(
            List.of("ok", "bad-1", "ok-2", "bad-2")
        );

        if (report.successes().size() != 2) {
            throw new AssertionError("Sai số thành công");
        }
        if (report.failures().size() != 2) {
            throw new AssertionError("Thiếu bản ghi lỗi");
        }
        if (!"bad-1".equals(
                report.failures().get(0).sourceId())) {
            throw new AssertionError("Sai thứ tự lỗi");
        }

        System.out.println("PASS");
    }
}
~~~

Bộ kiểm tra này làm rõ hợp đồng: trên `List.stream()` tuần tự, báo cáo giữ encounter order của nguồn. Nó kiểm thử **kết quả có thể quan sát**, không đếm số lần gọi `peek` hoặc log bên trong lambda.

## 18. Quy trình gỡ lỗi và checklist trước khi đưa pipeline vào sản xuất

Khi gặp lỗi trong lambda của Stream, có thể điều tra theo các bước:

1. **Xác định kiểu exception:** checked (`IOException`, `SQLException`) hay unchecked (`NumberFormatException`, `IllegalArgumentException`)?
2. **Xác định target functional interface:** `Function`, `Predicate`, `Consumer`, `BinaryOperator` hoặc callback Collector nào?
3. **Chọn chính sách:** fail-fast, fallback, error as data, partial success hay API vòng lặp.
4. **Kiểm tra chỗ thực sự ném lỗi:** xây pipeline hay chạy terminal?
5. **Giữ ngữ cảnh:** ID nguồn, đường dẫn, vị trí dòng, operation đang thực hiện.
6. **Giữ cause:** không chỉ ném message mất stack/cause của exception gốc.
7. **Kiểm tra tài nguyên:** ai mở và ai đóng? Có `try-with-resources` khi đọc `Files.lines` không?
8. **Kiểm tra side effect:** có dữ liệu nào đã commit trước khi lỗi không?
9. **Kiểm tra short-circuit:** `findFirst`, `limit`, `anyMatch`, `count` có thể khiến một số callback không chạy.
10. **Kiểm tra song song:** có mutable state chia sẻ, lỗi không đủ, thứ tự không xác định hay I/O quá tải không?
11. **Kiểm thử:** nguồn rỗng, toàn thành công, một lỗi, nhiều lỗi, nguyên nhân và transaction boundary.

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `unreported exception IOException` trong `map` | `Function.apply` không có checked throws | Catch/adapter hoặc đổi cấu trúc |
| Lỗi ném tại `toList()` | Lazy mapper chạy ở terminal | Catch quanh terminal |
| Không thấy lỗi ở một số phần tử | Terminal short-circuit hoặc tối ưu hóa | Không dùng side effect làm oracle |
| Hết bộ nhớ khi đọc file | `Files.readString` tải toàn bộ dữ liệu | Streaming/giới hạn kích thước |
| File descriptor không được đóng | Quên quản lý `Files.lines` | Try-with-resources |
| Mất đường dẫn gây lỗi | Wrapper không có context | Đưa path/ID vào message hoặc Result |
| Không quan sát đủ lỗi | Fail-fast dừng sớm | Error as data, terminal cần toàn bộ kết quả |
| Danh sách lỗi bị sai khi parallel | Shared mutable ArrayList | Loại side effect, thu `Outcome` |
| Có bản ghi đã lưu dù pipeline thất bại | Không có transaction/staging | Thiết kế commit/rollback riêng |
| Cancellation không hiệu quả | Nuốt `InterruptedException` | Khôi phục cờ interrupt, báo lỗi |
| Lỗi SQL bị gắn nhãn I/O | Wrapper không đúng loại | Runtime exception domain có cause |

## 19. Những cách làm sai cần tránh

### 19.1. Bắt mọi exception và trả chuỗi rỗng

~~~java
// Không nên:
// catch (Exception ex) { return ""; }
~~~

Giá trị rỗng có thể là dữ liệu **thật**; không phân biệt được file rỗng với file đọc hỏng. Hãy chọn fallback rõ ràng hoặc kiểu `Failure`.

### 19.2. Ném RuntimeException mà bỏ cause

~~~java
// Không nên:
// catch (IOException ex) {
//     throw new RuntimeException("Đọc file lỗi");
// }
~~~

Bỏ cause làm mất chain exception. Nên dùng `new UncheckedIOException("...", ex)` hoặc exception domain chứa `ex`.

### 19.3. Dùng UncheckedIOException cho mọi exception

`UncheckedIOException` dành riêng cho `IOException`. Với `SQLException` và `ParseException`, dùng wrapper đúng domain hoặc mô hình lỗi có cấu trúc.

### 19.4. Ép mọi checked exception thành unchecked rồi quên ranh giới API

Một public API từng khai báo `throws IOException` mà đổi ngầm thành unchecked có thể khiến người gọi không còn xử lý đúng loại lỗi. Nếu cần giữ hợp đồng checked, chuyển ngược ở boundary như mục 7.

### 19.5. Tin rằng try/catch bao quanh việc xây Stream là đủ

Mapper chạy lazy. Nếu terminal chạy ngoài `try`, exception có thể xuất hiện sau khối catch. Kiểm tra vị trí terminal thật.

### 19.6. Giả định parallelStream sẽ báo mọi lỗi

Không có bảo đảm này. Nếu cần thống kê mọi lỗi, sử dụng `Outcome` cho từng input, tránh short-circuit, kiểm soát I/O và kiểm thử đầy đủ.

### 19.7. Dùng shared mutable List để thu thập lỗi

Callback chạy song song có thể cập nhật cùng một List không thread-safe. Ngay cả khi đồng bộ hóa, thiết kế kết quả kiểu `Outcome` thường dễ kiểm soát hơn và ít side effect hơn.

### 19.8. Cho rằng exception sẽ rollback file hoặc database

Không. Side effect đã xảy ra phải được xử lý bằng transaction, staging hoặc compensation tùy domain.

### 19.9. Không đóng nguồn Files.lines

`Files.lines` cần được đóng. Đừng chỉ chạy terminal rồi dựa vào GC hoặc mong Stream tự đóng mọi tài nguyên gắn với nó.

### 19.10. Che tín hiệu interrupt

Không xử lý `InterruptedException` bằng cách trả fallback và tiếp tục như bình thường. Nếu không thể rethrow checked exception, thường cần khôi phục cờ interrupt và báo lỗi có cause.

## 20. Bảng chọn cách xử lý theo yêu cầu

| Nhu cầu | Cách tiếp cận đề xuất |
| --- | --- |
| Đọc tất cả file bắt buộc; lỗi đầu tiên làm thất bại | Catch `IOException` thành `UncheckedIOException` và fail-fast |
| Public method phải `throws IOException` | Chuyển wrapper trở lại `getCause()` ở boundary |
| Nhiều mapper I/O giống nhau | `IOFunction` adapter |
| Lọc dữ liệu dựa trên `Files.size` | `IOPredicate` adapter, tránh TOCTOU assumptions |
| Từng bản ghi phải có trạng thái thành công/thất bại | `Success/Failure` hoặc Result domain |
| Cần phân tích mọi lỗi của một batch | Materialize `Outcome` toàn nguồn rồi phân loại |
| Fallback cho lỗi thiếu file, lỗi khác vẫn phải báo | Catch `NoSuchFileException` cụ thể |
| Đọc file lớn theo dòng | `Files.lines` + try-with-resources |
| Ghi giao dịch có điều kiện all-or-nothing | Transaction/staging ngoài Stream |
| Có `InterruptedException` | Propagate nếu được; nếu wrap thì restore interrupt |
| Gọi I/O đồng thời có quota | Tầng orchestration có giới hạn, không chỉ parallelStream |
| Code adapter phức tạp hơn logic chính | Vòng lặp rõ ràng với `throws` |

## 21. Câu hỏi tự kiểm tra và bài thực hành

1. **Vì sao `Files::readString` không gán trực tiếp vào `Stream.map`?** Vì `Function.apply` không khai báo `throws IOException`.
2. **Thêm `throws IOException` vào method bao ngoài có giải quyết lỗi lambda không?** Không, target type vẫn không cho checked exception thoát ra.
3. **`IOException` khác `UncheckedIOException` thế nào?** Một bên checked, một bên là RuntimeException giữ IOException làm cause.
4. **Vì sao nên thêm Path/ID vào thông điệp lỗi?** Để tìm nguồn gây lỗi khi một pipeline xử lý nhiều bản ghi.
5. **`orElse("")` hoặc trả chuỗi rỗng khi đọc lỗi có luôn an toàn không?** Không, vì có thể xóa khác biệt giữa dữ liệu rỗng và lỗi.
6. **`IOFunction` giải quyết vấn đề gì?** Cho phép callback khai báo `throws IOException` rồi chuyển sang Function hợp lệ.
7. **Có thể dùng `UncheckedIOException` cho SQLException không?** Không; dùng wrapper đúng domain.
8. **Lỗi do mapper lazy xuất hiện ở đâu?** Khi terminal thực sự yêu cầu xử lý mapper.
9. **`limit(1)` có bảo đảm mapper chạy trên mọi input không?** Không.
10. **`count()` có thể bỏ qua mapper không?** Có trong một số pipeline khi kích thước biết trước và mapper không ảnh hưởng số lượng.
11. **Vì sao nên dùng `Outcome` khi cần thu thập mọi lỗi?** Vì mỗi input có một kết quả thành công hoặc thất bại, không dừng ngay ở lỗi đầu.
12. **Vì sao không chạy I/O hai lần để lập hai báo cáo?** Có thể tốn tài nguyên và dữ liệu ngoài thay đổi giữa hai lần.
13. **`Files.lines` cần lưu ý điều gì?** Lỗi checked lúc mở, unchecked khi duyệt và trách nhiệm đóng Stream.
14. **Trả Stream từ try-with-resources có đúng không?** Không nếu Stream đã đóng trước khi caller tiêu thụ.
15. **Vì sao không nuốt `InterruptedException`?** Vì có thể che tín hiệu hủy; cần xử lý cờ interrupt hoặc propagate.
16. **Parallel Stream có báo mọi IOException không?** Không có bảo đảm theo thứ tự hay đầy đủ.
17. **Synchronized List có tự sửa mọi rủi ro thu thập lỗi không?** Không, vẫn còn side effect và hợp đồng tính đầy đủ.
18. **Exception ở record thứ năm có rollback các record trước không?** Không.
19. **Khi nào vòng lặp thích hợp hơn?** Khi checked exception, cleanup, retry, transaction và thứ tự cần thể hiện rõ.
20. **Một adapter unchecked có thay thế retry policy không?** Không, nó chỉ chuyển exception.
21. **Nên thử những ca nào khi test adapter?** Thành công, lỗi, cause và bối cảnh của nguồn, nguồn rỗng.
22. **`NumberFormatException` có cần adapter checked exception không?** Không; nó là unchecked exception, nhưng vẫn cần chính sách xử lý dữ liệu xấu.

### Bài mở rộng A — Báo cáo cả lỗi và dữ liệu đọc thành công

Sửa `ReadOutcomeDemo` để mỗi `Failure` có `sourceId`, loại lỗi và thông điệp. Thêm một bước kiểm tra dữ liệu rỗng, phân biệt “đọc thành công nhưng file không có nội dung” với “đọc thất bại”.

### Bài mở rộng B — Catch lỗi thiếu file nhưng giữ lỗi truy cập

Viết `readConfigOrDefault(Path)` chỉ fallback cho `NoSuchFileException`. Nếu gặp `AccessDeniedException`, giữ lỗi hoặc chuyển thành một `Failure` phù hợp; không dùng cùng fallback cho tất cả IOException.

### Bài mở rộng C — Kiểm thử lazy và short-circuit

Tạo nguồn `["ok","bad"]` với `fakeRead`. So sánh `limit(1).toList()` và `toList()`, rồi giải thích tại sao không thể coi một pipeline short-circuit là bước kiểm tra tất cả bản ghi.

### Bài mở rộng D — Quản lý tài nguyên đọc nhiều file

Thiết kế hàm đọc từng file với `try-with-resources`, trả `Outcome` cho từng path. Kiểm tra các trường hợp không mở được file, lỗi lúc đọc dòng và đảm bảo mọi Stream nguồn được đóng.

### Bài mở rộng E — Xử lý kết quả trước khi commit

Xây một batch import trả `List<Outcome>`, không có side effect ghi cơ sở dữ liệu trong mapper. Chỉ thực hiện commit khi không có `Failure` hoặc theo chính sách partial success đã công bố.

**Ghi nhớ:** Checked exception không tự tương thích với `Function`, `Predicate` hoặc `Consumer` của Stream. Hãy quyết định chính sách lỗi trước: **fail-fast**, **fallback có điều kiện**, **adapter giữ cause**, **error as data** hay **vòng lặp rõ ràng**. Luôn tính tới lazy evaluation, short-circuit, đóng tài nguyên, side effect đã xảy ra và tính không xác định của lỗi trong parallel stream. Viết pipeline đúng không chỉ là làm code biên dịch, mà là bảo đảm mọi lỗi quan trọng có thể được nhận biết và xử lý theo hợp đồng nghiệp vụ.
