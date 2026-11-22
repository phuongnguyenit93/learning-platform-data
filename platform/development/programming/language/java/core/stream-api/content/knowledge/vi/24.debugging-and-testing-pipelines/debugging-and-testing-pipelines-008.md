# Kiểm thử đóng tài nguyên khi dừng sớm hoặc có ngoại lệ

> **Chương:** Gỡ lỗi và kiểm thử pipeline  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện giới hạn về trạng thái, tài nguyên và hiệu năng.

Một pipeline Java Stream có thể trả đúng kết quả nhưng vẫn **rò rỉ tài nguyên**. Ví dụ, chương trình đọc một vài dòng đầu từ file bằng `Files.lines(...).limit(5)`, hoặc tìm được phần tử phù hợp bằng `findFirst()`, rồi quên đóng Stream. Việc xử lý đã kết thúc về mặt dữ liệu **không đồng nghĩa** handle file, thư mục hay nguồn I/O đã được giải phóng.

Tình huống khó hơn xuất hiện khi lambda trong `map`, `filter` hoặc terminal operation ném ngoại lệ. Lúc đó, mã dọn dẹp đặt sau terminal operation có thể không bao giờ chạy. Bài này hướng dẫn đặt **quyền sở hữu tài nguyên** đúng chỗ bằng `try-with-resources`, viết kiểm thử quan sát `onClose`, kiểm tra ngoại lệ trong xử lý và ngoại lệ khi đóng, đồng thời tránh nhầm hành vi dừng sớm của Stream với hành vi đóng tài nguyên.

Các ví dụ chạy trên **Java 17+**, không cần thư viện ngoài JDK. Các phép kiểm tra dùng `AssertionError` để có thể chạy mà không cần bật `-ea`.

## 1. Ba sự kiện khác nhau: tiêu thụ, dừng và đóng

Trong Java Stream API cần phân biệt:

| Sự kiện | Ví dụ | Có tự gọi `close()` không? |
| --- | --- | --- |
| **Terminal operation kết thúc bình thường** | `toList()`, `count()`, `sum()` | **Không**. |
| **Terminal operation dừng sớm** | `findFirst()`, `anyMatch(...)`, `limit(3).toList()` | **Không**. |
| **Terminal operation ném ngoại lệ** | `map(...)` ném `IllegalArgumentException` lúc `toList()` | **Không bảo đảm đóng**; cần cơ chế quản lý tài nguyên. |
| **`close()` được gọi tường minh** | `stream.close()` | **Có**, gọi các close handler đã đăng ký. |
| **Rời khối `try-with-resources`** | `try (Stream<T> s = ...) { ... }` | **Có**, kể cả khi `return` hoặc ngoại lệ. |

`Stream` kế thừa `BaseStream`, mà `BaseStream` triển khai `AutoCloseable`. Vì vậy, Stream có thể được khai báo trong `try-with-resources`. Tuy nhiên, **gọi terminal operation không tự động đóng Stream**. Một Stream sau terminal operation thường đã bị tiêu thụ và không được dùng lại, nhưng trạng thái *consumed* không phải trạng thái *closed*.

Một sơ đồ vòng đời:

```text
Tạo Stream từ nguồn I/O
        |
        v
Tạo các intermediate stages (filter/map/limit...)
        |
        v
Terminal operation
        |
        +---- hoàn tất toàn bộ nguồn -----------+
        |                                       |
        +---- dừng sớm (findFirst/limit...) ----+----> Chưa chắc đã close
        |                                       |
        +---- ném ngoại lệ ---------------------+
                                                |
                              Rời try-with-resources / gọi close()
                                                |
                                                v
                                     Đóng pipeline và close handlers
```

Hầu hết Stream từ collection/mảng không giữ tài nguyên I/O cần giải phóng nên thường không phải đóng. Ngược lại, các Stream gắn với file, bộ duyệt thư mục hoặc nguồn do ứng dụng tự mở phải tuân thủ **hợp đồng đóng tài nguyên** của nguồn đó. Không thể suy rằng mọi Stream từ API bất kỳ đều tự quản lý handle.

## 2. Mẫu an toàn với `Files.lines` và `Files.walk`

Ví dụ, chỉ muốn đọc tối đa năm dòng đầu tiên của một file:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path path = Path.of("orders.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> firstFive = lines.limit(5).toList();
    System.out.println(firstFive);
} catch (IOException openFailure) {
    System.err.println("Không mở được file: " + openFailure.getMessage());
}
```

`Files.lines` trả một Stream được hỗ trợ bởi tài nguyên file và **phải được đóng** sau khi sử dụng. `limit(5)` giúp terminal operation chỉ yêu cầu một tiền tố của nguồn nhưng **không thay thế** việc đóng Stream. `try-with-resources` gọi `close()` khi rời khối, dù nguồn có nhiều hơn năm dòng.

`Files.lines` có thể ném `IOException` khi mở file; lỗi I/O xảy ra **trong lúc duyệt** cũng có thể được bọc thành `UncheckedIOException`. Đoạn bắt `IOException` ở trên minh họa lỗi mở file, không phải chính sách xử lý mọi lỗi runtime khi đọc. Ứng dụng cần xác định cách báo lỗi cả hai trường hợp và không nuốt ngoại lệ.

Một ví dụ khác là duyệt thư mục và lấy tối đa ba đường dẫn file:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path root = Path.of("data");

try (Stream<Path> paths = Files.walk(root)) {
    List<Path> firstFiles = paths
            .filter(Files::isRegularFile)
            .limit(3)
            .toList();
    System.out.println(firstFiles);
} catch (IOException openFailure) {
    System.err.println("Không thể bắt đầu duyệt: " + openFailure);
}
```

`Files.walk` cũng dùng tài nguyên mở trong quá trình duyệt; việc dừng bằng `limit` không tự giải phóng những tài nguyên đó. Cũng như `Files.lines`, lỗi phát sinh khi duyệt có thể là `UncheckedIOException`.

**Lưu ý:** Nếu sử dụng `BufferedReader.lines()`, hãy xem `BufferedReader` là tài nguyên cần quản lý và đóng reader bằng `try-with-resources`. Không nên suy từ tên phương thức `lines()` rằng mọi nguồn đều có chính sách đóng giống nhau.

## 3. `onClose`: công cụ kiểm thử đường đóng

Đối với một Stream trong bộ nhớ, ta có thể đăng ký callback `onClose` để quan sát liệu `close()` có thực sự được gọi hay không:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger closeCount = new AtomicInteger();

try (Stream<Integer> numbers = Stream.of(1, 2, 3)
        .onClose(closeCount::incrementAndGet)) {
    int first = numbers.findFirst().orElseThrow();
    System.out.println(first);         // 1
    System.out.println(closeCount.get()); // 0: đang ở trong try
}

System.out.println(closeCount.get());  // 1: close đã được gọi
```

Đây là **kiểm thử cơ chế gọi close handler**, không phải phép đo trực tiếp rằng hệ điều hành đã đóng một file descriptor nào đó. `onClose` được dùng rất tốt để xác nhận ownership và control flow. Muốn kiểm chứng giải phóng tài nguyên cụ thể, cần test tích hợp với loại tài nguyên đó.

### Vì sao dùng `AtomicInteger`?

Trong test tuần tự, một biến đếm đơn giản có thể đủ, nhưng `AtomicInteger` an toàn hơn khi bài tập được mở rộng sang các tình huống có nhiều thread. Tuy vậy, **thread-safe counter không quyết định thời điểm đóng**; chính `try-with-resources` hoặc `close()` mới là hành động cần kiểm tra.

`onClose` đăng ký một handler chạy **khi đóng pipeline**, không đăng ký callback sau mỗi phần tử, và cũng không phải `peek`. Không dùng nó để tăng bộ đếm số dòng đã xử lý.

## 4. Kiểm thử dừng sớm: `findFirst`, `anyMatch`, `limit`

Ba ví dụ đều cần đóng Stream nếu nguồn giữ tài nguyên:

```java
try (Stream<String> lines = Files.lines(path)) {
    String firstError = lines
            .filter(line -> line.startsWith("ERROR:"))
            .findFirst()
            .orElse("(không có lỗi)");
    System.out.println(firstError);
}
```

```java
try (Stream<String> lines = Files.lines(path)) {
    boolean hasError = lines.anyMatch(line -> line.startsWith("ERROR:"));
    System.out.println(hasError);
}
```

```java
try (Stream<String> lines = Files.lines(path)) {
    List<String> preview = lines.limit(10).toList();
    System.out.println(preview);
}
```

Trong ba ví dụ, `path` là `Path` trỏ tới file thực tế. `findFirst` và `anyMatch` có thể dừng khi đã đạt điều kiện; `limit` có thể dừng sau khi thu đủ phần tử. **Không có thao tác nào tự gọi `close()` để thay cho `try-with-resources`.**

Không nên viết test giả định lambda trong `filter` hoặc `peek` được gọi đúng N lần trong **mọi** pipeline, đặc biệt khi có short-circuit hoặc xử lý song song. Điều ổn định để kiểm tra ở đây là: **kết quả nghiệp vụ đúng và handler đóng chạy khi rời scope**.

### Dùng nguồn vô hạn một cách kiểm soát

```java
AtomicInteger closed = new AtomicInteger();

try (Stream<Integer> values = Stream.iterate(1, n -> n + 1)
        .onClose(closed::incrementAndGet)
        .limit(4)) {
    System.out.println(values.toList()); // [1, 2, 3, 4]
}

System.out.println(closed.get()); // 1
```

`Stream.iterate` ở ví dụ này có thể vô hạn, nhưng `limit(4)` bảo đảm terminal operation chỉ cần bốn giá trị đầu. Nếu vô tình bỏ `limit` và gọi `toList()`, phép xử lý có thể không kết thúc, nên câu lệnh `close` ở cuối khối cũng chưa được thực hiện vì chương trình chưa ra khỏi khối. Trong test tự động về short-circuit, nên áp dụng **timeout của test runner** để tránh treo suite khi có lỗi logic.

## 5. Ngoại lệ giữa pipeline: dọn dẹp vẫn phải xảy ra

Đoạn sau **không an toàn** khi Stream gắn với file hoặc nguồn cần đóng:

```java
Stream<String> lines = Files.lines(path);
List<Integer> numbers = lines
        .map(Integer::parseInt)
        .toList();
lines.close(); // Không chạy nếu parseInt ném ngoại lệ!
```

Một dòng `abc` sẽ khiến `Integer.parseInt` ném `NumberFormatException`; khi đó câu lệnh `lines.close()` phía sau không được thực thi.

Sửa bằng `try-with-resources`:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<Integer> numbers = lines
            .map(Integer::parseInt)
            .toList();
    System.out.println(numbers);
}
```

Nếu việc phân tích dữ liệu ném ngoại lệ và thoát khỏi khối, Java vẫn gọi `close()` của `lines`. Ngoại lệ từ `parseInt` tiếp tục được truyền ra ngoài, trừ khi chương trình chủ động bắt nó ở tầng phù hợp.

Đừng dùng `finally` một cách thủ công khi `try-with-resources` đã diễn đạt rõ ownership. Với nhiều tài nguyên và ngoại lệ từ `close`, cú pháp `try-with-resources` còn xử lý **suppressed exceptions** đúng quy tắc của Java.

## 6. Khi đóng cũng ném ngoại lệ: suppressed exceptions

Có hai nơi độc lập có thể hỏng:

1. **Thân xử lý:** `map`/terminal operation ném `IllegalArgumentException`, `UncheckedIOException`, ...
2. **Đóng tài nguyên:** một close handler hoặc phương thức `close()` ném `RuntimeException`.

Trong `try-with-resources`, nếu **thân khối đã ném ngoại lệ**, ngoại lệ đó thường là **primary exception**; ngoại lệ phát sinh khi đóng được gắn vào `primary.getSuppressed()`, thay vì thay thế lỗi xử lý ban đầu.

```java
import java.util.stream.Stream;

try (Stream<Integer> values = Stream.of(1, 2)
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {
    values.map(n -> {
        if (n == 2) {
            throw new IllegalArgumentException("bad input");
        }
        return n;
    }).toList();
} catch (IllegalArgumentException processingFailure) {
    System.out.println(processingFailure.getMessage()); // bad input
    System.out.println(processingFailure.getSuppressed().length); // 1
    System.out.println(processingFailure.getSuppressed()[0].getMessage());
    // close failed
}
```

Ở đây `close()` không bị bỏ qua: nó đã chạy và ném lỗi; Java giữ lỗi xử lý làm **nguyên nhân chính** và giữ lỗi đóng để chẩn đoán thêm. Khi làm hệ thống thực, log và giám sát nên xem cả `getSuppressed()`, đặc biệt khi hai loại lỗi cùng xuất hiện.

### Nhiều `onClose` handler

`BaseStream.onClose(...)` cho phép đăng ký nhiều handler. Các handler được chạy **theo thứ tự đăng ký**; nếu một handler ném ngoại lệ, những handler còn lại vẫn được gọi. Ngoại lệ đầu tiên sẽ là ngoại lệ được ném từ `close()`, các ngoại lệ tiếp theo được gắn dưới dạng suppressed.

```java
List<String> events = new ArrayList<>();

try (Stream<Integer> values = Stream.of(1)
        .onClose(() -> {
            events.add("first");
            throw new IllegalStateException("first close failed");
        })
        .onClose(() -> {
            events.add("second");
            throw new IllegalArgumentException("second close failed");
        })) {
    values.findFirst();
} catch (IllegalStateException closeFailure) {
    System.out.println(events); // [first, second]
    System.out.println(closeFailure.getSuppressed().length); // 1
}
```

Trong chương trình hoàn chỉnh ở mục 8, các tình huống này được kiểm tra bằng điều kiện, không chỉ in log.

## 7. Đóng pipeline và quản lý quyền sở hữu tài nguyên

Khi tạo các stage từ một Stream:

```java
Stream<String> source = Files.lines(path);
Stream<Integer> lengths = source
        .filter(line -> !line.isBlank())
        .map(String::length);
```

`source` và `lengths` thuộc **cùng một pipeline**. Khi đóng một Stream trong pipeline, các close handler của pipeline được gọi. Vì thế, có thể đặt `try-with-resources` quanh Stream sau cùng mà mình sẽ tiêu thụ:

```java
try (Stream<Integer> lengths = Files.lines(path)
        .filter(line -> !line.isBlank())
        .map(String::length)) {
    System.out.println(lengths.limit(3).toList());
}
```

Quyền sở hữu phải rõ ràng: ai tạo Stream I/O, ai có trách nhiệm đóng, có trả Stream ra khỏi phương thức hay chỉ trả danh sách đã vật hóa? Một phương thức trả `List<T>` sau khi đóng Stream thường đơn giản hơn để sử dụng an toàn. Nếu phương thức **trả Stream còn mở**, phải công bố rõ caller có trách nhiệm đóng và không được đóng nó trước khi caller tiêu thụ.

### Tự tạo Stream từ nguồn cần đóng

Nếu ứng dụng tự xây Stream qua `StreamSupport.stream(spliterator, ...)` trên một nguồn tài nguyên, Stream đó **không tự biết cách đóng** tài nguyên riêng của bạn. Cần gắn `onClose` hoặc bảo đảm đối tượng nguồn được đóng bằng một scope `try-with-resources` riêng.

```java
// Ví dụ mô hình, không phải code chạy độc lập:
// Stream<Record> records = StreamSupport.stream(source.spliterator(), false)
//         .onClose(source::close);
// try (records) {
//     return records.limit(100).toList();
// }
```

Ở ví dụ này, `source` được hiểu là một đối tượng có `spliterator()` và `close()` phù hợp. Các `Stream` thông thường từ `List` hoặc mảng không cần đăng ký close handler giả chỉ để tính toán số.

### `close()` được gọi hai lần thì sao?

`BaseStream.close()` là **idempotent**: khi Stream đã đóng, lời gọi tiếp theo không gây tác dụng mới. Điều này hữu ích để tránh dọn dẹp trùng, nhưng không phải lý do để phân tán nhiều chỗ đóng trong chương trình.

```java
AtomicInteger closeCount = new AtomicInteger();
Stream<Integer> values = Stream.of(1)
        .onClose(closeCount::incrementAndGet);

values.close();
values.close();
System.out.println(closeCount.get()); // 1
```

Vẫn nên chọn **một owner** và một scope quản lý cụ thể thay vì để nhiều tầng tùy ý đóng cùng Stream.

## 8. Chương trình Java 17+ tự chứa: kiểm thử đóng trong mọi nhánh

Lưu chương trình sau vào `StreamResourceClosureTests.java`. Để bộ test chạy được mà **không tạo file ngoài**, ta dùng `Stream.onClose` và biến đếm `AtomicInteger` làm điểm quan sát. Test này kiểm chứng đường gọi `close()`; sau đó mục 9 đề xuất cách kiểm thử tích hợp trên nguồn I/O thực.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamResourceClosureTests {

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static Stream<Integer> tracked(AtomicInteger closeCount) {
        return Stream.of(1, 2, 3, 4)
                .onClose(closeCount::incrementAndGet);
    }

    static void testFindFirstCloses() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = tracked(closed)) {
            Optional<Integer> first = values
                    .filter(n -> n >= 3)
                    .findFirst();
            check(first.equals(Optional.of(3)), "findFirst sai");
            check(closed.get() == 0,
                    "Terminal operation không tự đóng Stream");
        }

        check(closed.get() == 1, "findFirst không được đóng khi rời try");
    }

    static void testLimitCloses() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = tracked(closed).limit(2)) {
            check(values.toList().equals(List.of(1, 2)),
                    "Sai kết quả limit");
            check(closed.get() == 0,
                    "limit/toList không tự đóng");
        }

        check(closed.get() == 1, "Không đóng sau limit");
    }

    static void testAnyMatchCloses() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = tracked(closed)) {
            check(values.anyMatch(n -> n == 2), "anyMatch sai");
        }

        check(closed.get() == 1, "Không đóng sau anyMatch");
    }

    static void testInfiniteSourceWithLimit() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = Stream
                .iterate(1, n -> n + 1)
                .onClose(closed::incrementAndGet)
                .limit(4)) {
            check(values.toList().equals(List.of(1, 2, 3, 4)),
                    "Nguồn vô hạn không dừng ở 4 phần tử");
        }

        check(closed.get() == 1, "Không đóng nguồn vô hạn có limit");
    }

    static void testTerminalDoesNotAutoClose() {
        AtomicInteger closed = new AtomicInteger();
        Stream<Integer> values = tracked(closed);

        check(values.toList().equals(List.of(1, 2, 3, 4)),
                "toList sai");
        check(closed.get() == 0,
                "toList không được tự gọi onClose");

        values.close();
        check(closed.get() == 1, "close không gọi handler");
        values.close(); // Idempotent.
        check(closed.get() == 1, "Handler chạy hai lần");
    }

    static Optional<Integer> returnEarly(AtomicInteger closed) {
        try (Stream<Integer> values = tracked(closed)) {
            return values.filter(n -> n > 2).findFirst();
        }
    }

    static void testReturnStillCloses() {
        AtomicInteger closed = new AtomicInteger();
        Optional<Integer> found = returnEarly(closed);

        check(found.equals(Optional.of(3)), "Giá trị trả sai");
        check(closed.get() == 1,
                "return không được bỏ qua try-with-resources");
    }

    static void testProcessingExceptionStillCloses() {
        AtomicInteger closed = new AtomicInteger();
        boolean caught = false;

        try (Stream<Integer> values = tracked(closed)
                .map(n -> {
                    if (n == 2) {
                        throw new IllegalArgumentException("invalid row");
                    }
                    return n * 2;
                })) {
            values.toList();
        } catch (IllegalArgumentException expected) {
            caught = "invalid row".equals(expected.getMessage());
        }

        check(caught, "Thiếu ngoại lệ xử lý");
        check(closed.get() == 1,
                "Ngoại lệ trong map làm mất close");
    }

    static void testPrimaryAndSuppressed() {
        AtomicInteger closed = new AtomicInteger();
        boolean caught = false;

        try (Stream<Integer> values = Stream.of(1, 2)
                .onClose(() -> {
                    closed.incrementAndGet();
                    throw new IllegalStateException("cleanup failed");
                })) {
            values.map(n -> {
                if (n == 2) {
                    throw new IllegalArgumentException("bad input");
                }
                return n;
            }).toList();
        } catch (IllegalArgumentException main) {
            caught = "bad input".equals(main.getMessage());
            Throwable[] suppressed = main.getSuppressed();
            check(suppressed.length == 1,
                    "Phải giữ ngoại lệ đóng dưới dạng suppressed");
            check(suppressed[0] instanceof IllegalStateException,
                    "Sai kiểu ngoại lệ đóng");
            check("cleanup failed".equals(suppressed[0].getMessage()),
                    "Sai nguyên nhân đóng");
        }

        check(caught, "Ngoại lệ xử lý không còn là lỗi chính");
        check(closed.get() == 1, "Close handler không chạy");
    }

    static void testMultipleCloseHandlers() {
        List<String> events = new ArrayList<>();
        boolean caught = false;

        try (Stream<Integer> values = Stream.of(1)
                .onClose(() -> {
                    events.add("first");
                    throw new IllegalStateException("close first");
                })
                .onClose(() -> {
                    events.add("second");
                    throw new IllegalArgumentException("close second");
                })) {
            check(values.findFirst().equals(Optional.of(1)),
                    "findFirst sai");
        } catch (IllegalStateException first) {
            caught = "close first".equals(first.getMessage());
            Throwable[] suppressed = first.getSuppressed();
            check(suppressed.length == 1,
                    "Handler lỗi thứ hai phải suppressed");
            check(suppressed[0] instanceof IllegalArgumentException,
                    "Sai ngoại lệ handler thứ hai");
            check("close second".equals(suppressed[0].getMessage()),
                    "Sai thông điệp handler thứ hai");
        }

        check(caught, "Không nhận ngoại lệ close đầu tiên");
        check(events.equals(List.of("first", "second")),
                "Không chạy đủ close handlers theo thứ tự đăng ký");
    }

    static void testParallelEarlyExitCloses() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = IntStream.range(0, 1_000)
                .parallel()
                .boxed()
                .onClose(closed::incrementAndGet)) {
            check(values.anyMatch(n -> n >= 500),
                    "Không tìm thấy phần tử thỏa điều kiện");
        }

        // Không đếm số lần callback của anyMatch: parallel có thể
        // đánh giá thêm phần tử trước khi cơ chế dừng hoàn tất.
        check(closed.get() == 1,
                "Pipeline song song không được đóng khi rời scope");
    }

    public static void main(String[] args) {
        testFindFirstCloses();
        testLimitCloses();
        testAnyMatchCloses();
        testInfiniteSourceWithLimit();
        testTerminalDoesNotAutoClose();
        testReturnStillCloses();
        testProcessingExceptionStillCloses();
        testPrimaryAndSuppressed();
        testMultipleCloseHandlers();
        testParallelEarlyExitCloses();

        System.out.println("ALL STREAM CLOSE TESTS PASS");
    }
}
```

Chạy trên JDK 17+:

```text
javac StreamResourceClosureTests.java
java StreamResourceClosureTests
```

Đầu ra mong đợi nếu mọi ca kiểm tra đều đạt:

```text
ALL STREAM CLOSE TESTS PASS
```

Đây là mã tự kiểm thử cung cấp trong tài liệu. Việc biên soạn bài học **không đồng nghĩa** chương trình đã được biên dịch hoặc thực thi trong môi trường làm việc.

## 9. Kiểm thử tích hợp với tài nguyên thật

Các ca `onClose` ở mục 8 kiểm tra được **đường gọi close**, nhưng chưa chứng minh hệ điều hành giải phóng tài nguyên cụ thể hay thư viện bên ngoài đã đóng đúng hợp đồng. Với `Files.lines` và `Files.walk`, có thể bổ sung test tích hợp riêng:

1. Tạo một file thử trong thư mục tạm được test sở hữu; ghi vài dòng hợp lệ và một dòng gây lỗi parse.
2. Mở Stream bằng `Files.lines` trong `try-with-resources`, lần lượt kiểm `findFirst`, `limit` và ngoại lệ giữa `map`.
3. Sau mỗi scope, xác minh có thể tiếp tục thao tác phù hợp với file theo đặc tính nền tảng đang kiểm thử.
4. Thử cả lỗi phát sinh trong quá trình đọc, nếu có thể mô phỏng một nguồn I/O chủ động ném lỗi.
5. Dọn tài nguyên test trong `finally` hoặc `try-with-resources`, không để test thất bại rồi bỏ lại file tạm.

**Không coi việc xóa được file là một tiêu chí đóng file chung cho mọi hệ điều hành.** Trên một số hệ điều hành, file vẫn có thể bị unlink dù còn handle mở; trên hệ khác, hành vi có thể khác. Để xác minh hợp đồng chính xác, kết hợp fake/mock resource đếm số lần đóng với integration test phù hợp môi trường.

Một mẫu test tích hợp bằng JUnit (phác thảo; **không phải mã chạy độc lập** vì cần test framework và fixture):

```java
// @TempDir Path tempDir; // JUnit 5
// Path sample = tempDir.resolve("sample.txt");
// Files.writeString(sample, "1\n2\ninvalid\n");
//
// try (Stream<String> lines = Files.lines(sample)) {
//     assertEquals(List.of(1, 2),
//             lines.limit(2).map(Integer::parseInt).toList());
// }
//
// assertThrows(NumberFormatException.class, () -> {
//     try (Stream<String> lines = Files.lines(sample)) {
//         lines.map(Integer::parseInt).toList();
//     }
// });
```

Với integration test, có thể quan sát thời điểm tài nguyên được đóng qua wrapper riêng hoặc kiểm tra sự kiện dọn dẹp của thư viện, thay vì đoán dựa trên số thread hay thời điểm file bị hệ điều hành khóa.

## 10. Bảng kiểm thử bắt buộc cho dừng sớm và ngoại lệ

| Ca | Terminal / tình huống | Khi nào `onClose` chạy? | Điều cần xác minh |
| --- | --- | --- | --- |
| Bình thường, đọc hết | `toList()`, `count()` | Khi `close()` được gọi hoặc rời `try`. | Không tự đóng khi terminal kết thúc. |
| Tìm phần tử đầu | `findFirst()` | Khi rời `try`. | Kết quả đúng; đóng đúng một lần. |
| Match ngắn mạch | `anyMatch(...)` | Khi rời `try`. | Không phụ thuộc số phần tử đã được đánh giá. |
| Hạn chế đầu ra | `limit(n).toList()` | Khi rời `try`. | Không đọc vô hạn; vẫn đóng pipeline. |
| Trả sớm khỏi phương thức | `return` trong khối `try` | Trước khi phương thức trả về. | Close handler vẫn chạy. |
| Lambda ném ngoại lệ | `map(...).toList()` ném lỗi | Khi thoát `try` do ngoại lệ. | Vẫn đóng và giữ lỗi xử lý. |
| Lỗi chỉ ở close | Handler ném lỗi | Trong `close()`. | Lỗi close không bị nuốt. |
| Lỗi xử lý **và** close | Hai nơi đều ném lỗi | Trong bước cleanup khi thoát `try`. | Lỗi close là `suppressed` của lỗi chính. |
| Nhiều close handler | Handler đầu ném lỗi | Khi `close()` gọi tất cả handlers. | Thứ tự đăng ký đúng; lỗi sau nằm trong suppressed. |
| Gọi `close()` lặp lại | `close(); close()` | Handler chỉ chạy lần đầu. | Idempotency. |
| Song song, dừng sớm | `parallel().anyMatch(...)` | Khi rời `try`. | Không đếm callback hay giả định thứ tự thread. |

Nếu test chỉ quan sát rằng `findFirst()` trả đúng phần tử mà **không kiểm tra `close()`**, test đó chưa kiểm thử quyền sở hữu tài nguyên. Tương tự, nếu test chỉ kiểm có ngoại lệ ném ra nhưng không kiểm sự kiện đóng, lỗi leak vẫn có thể lọt qua.

## 11. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cho rằng `toList()`/`sum()` tự đóng mọi Stream | Handle I/O có thể tiếp tục mở. | Dùng `try-with-resources` cho nguồn cần đóng. |
| Dừng bằng `findFirst()` rồi bỏ Stream | Terminal kết thúc sớm nhưng tài nguyên chưa được đóng. | Đặt toàn bộ pipeline trong `try`. |
| Gọi `close()` sau `map(...).toList()` | Lỗi trong lambda có thể bỏ qua câu lệnh đóng. | Để `try-with-resources` thực hiện cleanup. |
| Dùng `onClose` như callback cho từng phần tử | Đếm sai và hiểu nhầm lifecycle. | Dùng `onClose` chỉ để quản lý/quan sát lúc đóng. |
| Nuốt mọi ngoại lệ trong `catch (Exception)` | Có thể mất lỗi xử lý và lỗi đóng quan trọng. | Xử lý theo tầng và xem suppressed exceptions. |
| Bắt một ngoại lệ close rồi cho rằng handler sau không chạy | Bỏ qua hợp đồng xử lý nhiều close handler. | Kiểm thứ tự và suppressed theo API. |
| Đếm chính xác số lần `peek` trên `parallel().findAny()` | Test phụ thuộc tối ưu hóa và lịch chạy. | Kiểm kết quả, khả năng kết thúc và sự kiện đóng. |
| Trả một `Stream` còn mở mà không ghi owner | Caller có thể quên đóng hoặc dùng sau khi owner đóng. | Công bố trách nhiệm đóng hoặc trả kết quả đã materialize. |
| Tạo Stream từ `Spliterator` của tài nguyên riêng và quên hook đóng | Stream không tự biết tài nguyên nào cần cleanup. | Dùng `onClose(resource::close)` hoặc quản lý resource riêng. |
| Dùng việc xóa file làm test đóng tuyệt đối trên mọi OS | Kết quả test khác nhau giữa hệ điều hành. | Mock/fake close và integration test theo nền tảng. |
| Dùng nguồn vô hạn mà quên `limit` | Terminal có thể không kết thúc để rời scope. | Định nghĩa short-circuit và đặt timeout cho test. |

## 12. Bài tập tự luyện

**Bài 1 — Terminal có tự đóng không?** Dự đoán `counter` sau `findFirst()` và sau `close()`:

```java
AtomicInteger counter = new AtomicInteger();
Stream<Integer> s = Stream.of(10, 20)
        .onClose(counter::incrementAndGet);

s.findFirst();
int before = counter.get();
s.close();
int after = counter.get();
```

**Đáp án:** `before == 0`, `after == 1`. Terminal đã dùng Stream nhưng chưa tự gọi handler đóng.

**Bài 2 — Kết thúc sớm.** Nếu `Files.lines(path)` có 10.000 dòng và `limit(1).toList()` trả một dòng, có thể bỏ `try-with-resources` không?

**Đáp án:** Không. `limit` chỉ giới hạn kết quả/tiêu thụ, không thay nghĩa vụ đóng file-backed Stream.

**Bài 3 — Ngoại lệ giữa pipeline.** Viết test đảm bảo `NumberFormatException` từ `Integer.parseInt` không ngăn `onClose` được gọi khi Stream đặt trong `try-with-resources`. Đặt một dòng `"oops"` sau dòng hợp lệ và xác minh cả ngoại lệ lẫn số lần đóng.

**Bài 4 — Hai ngoại lệ.** Cho thân `try` ném `IllegalArgumentException("body")`, `onClose` ném `IllegalStateException("close")`. Ngoại lệ nào là primary? Ngoại lệ nào trong `getSuppressed()`?

**Đáp án:** `IllegalArgumentException("body")` là primary, còn `IllegalStateException("close")` được gắn suppressed.

**Bài 5 — Nhiều handler.** Đăng ký ba `onClose` handler; handler thứ nhất và thứ ba ném ngoại lệ, handler thứ hai tăng bộ đếm. Xác minh cả ba handler được gọi theo thứ tự, và ngoại lệ thứ ba bị suppressed vào ngoại lệ đầu tiên.

**Bài 6 — `return` trong `try`.** Viết phương thức trả kết quả `findFirst()` ngay trong khối `try (Stream<T> s = ...)`. Vì sao lời gọi `return` không làm bỏ qua `close()`?

**Đáp án:** `try-with-resources` tạo phần cleanup được thực hiện khi thoát scope, kể cả thoát bằng `return`. Việc đóng xảy ra trước khi người gọi nhận giá trị trả về.

**Bài 7 — Tài nguyên tự xây.** Một nguồn do ứng dụng tự tạo có `spliterator()` và `close()`. Thiết kế cách kết nối `StreamSupport.stream(...)` với việc đóng nguồn. Phân tích ai là owner nếu phương thức trả Stream còn mở cho caller.

**Bài 8 — Test song song.** Viết ca `parallelStream().anyMatch(...)` trên danh sách lớn và gắn `onClose`. Tại sao chỉ nên yêu cầu `onClose` được gọi đúng khi đóng, không khẳng định `map` luôn chạy đúng số phần tử đã quan sát ở một lần thử?

**Đáp án:** Stream song song có quyền chia công việc, xử lý trước một số phần tử và dừng sau khi một nhánh đã có đáp án. Số lời gọi callback không phải hợp đồng ổn định; `try-with-resources` mới bảo đảm hành động đóng ở cuối scope.

## 13. Ghi nhớ

- **Terminal operation không tự đóng Stream**, kể cả khi đã đọc hết nguồn hoặc dừng sớm bằng `findFirst`, `anyMatch`, `limit`.
- Nguồn gắn với tài nguyên như `Files.lines`/`Files.walk` cần **`try-with-resources`**; `return` và ngoại lệ trong pipeline không bỏ qua cleanup.
- `onClose` dùng để gắn/quan sát hành động đóng pipeline; đóng Stream là idempotent. Kiểm thử `onClose` chứng minh đường gọi close, không tự chứng minh mọi handle của hệ điều hành đã được giải phóng.
- Khi có lỗi cả trong xử lý và khi đóng, `try-with-resources` giữ lỗi xử lý làm **primary** và đưa lỗi đóng vào **suppressed exceptions**; các close handler được gọi theo thứ tự đăng ký.
- Kiểm thử cả **thành công, dừng sớm, nguồn vô hạn được giới hạn, ngoại lệ, nhiều handler và song song**. Đừng buộc số callback hay lịch thread phải cố định nếu API không cam kết.
