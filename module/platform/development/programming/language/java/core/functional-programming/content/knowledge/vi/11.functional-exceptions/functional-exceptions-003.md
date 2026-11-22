# Bắt và xử lý ngoại lệ bên trong lambda trong Java

## 1. Vì sao xử lý ngoại lệ trong lambda cần chú ý?

Biểu thức lambda (*lambda expression*) là cách cung cấp hành vi cho phương thức trừu tượng duy nhất của một **giao diện hàm** (*functional interface*). Khi phần thân lambda thực hiện I/O, phân tích chuỗi, truy cập dịch vụ hoặc chuyển đổi dữ liệu, thao tác đó có thể ném ngoại lệ (*exception*). Java vẫn áp dụng các quy tắc kiểm tra ngoại lệ thông thường: một lambda **không tự động bỏ qua, bắt hay chuyển đổi ngoại lệ**.

Ví dụ một lambda dùng để chuyển chuỗi thành số:

```java
Function<String, Integer> parse = Integer::parseInt;
```

Dòng này minh họa một lệnh trong phương thức đã import `java.util.function.Function`. `parse.apply("42")` cho `42`; `parse.apply("abc")` ném `NumberFormatException` vì đầu vào sai định dạng. Ngoại lệ có thể được bắt **bên trong lambda** hoặc được cho lan ra để **mã gọi lambda** quyết định xử lý.

Vấn đề trở nên rõ hơn với **checked exception**, ví dụ `IOException`. `Function<T,R>.apply` và `Consumer<T>.accept` trong thư viện chuẩn không khai báo `throws IOException`. Vì vậy, nếu phần thân lambda gọi một phương thức ném `IOException`, nó phải **bắt hoặc xử lý phù hợp**; không thể tự ý khai báo `throws IOException` cho `Function.apply`.

Mục tiêu của bài: hiểu quy tắc checked/unchecked exceptions trong lambda, sử dụng `try/catch`/khối lệnh đúng cú pháp, chọn chính sách fallback/skip/ghi lỗi/rethrow, giữ thông tin nguyên nhân, nhận biết lỗi phổ biến khi dùng `Function`, `Consumer` và `Stream`.

## 2. Phân biệt checked và unchecked exception

| Nhóm | Ví dụ | Trình biên dịch buộc catch/declare? | Khi xử lý trong lambda |
| --- | --- | --- | --- |
| **Checked** | `IOException`, `SQLException` | **Có**, trừ trường hợp ngoại lệ đã được xử lý phù hợp | Nếu SAM không khai báo checked exception tương ứng, phải bắt hoặc chuyển đổi |
| **Unchecked** (`RuntimeException` và lớp con) | `NumberFormatException`, `IllegalArgumentException`, `NullPointerException` | **Không** | Có thể bắt nếu có chính sách hợp lý, hoặc để lan tới mã gọi |
| **Error** (`Error` và lớp con) | `OutOfMemoryError`, `StackOverflowError` | **Không** | Thông thường không bắt để coi là lỗi dữ liệu có thể khôi phục |

`NumberFormatException` là con của `IllegalArgumentException` rồi `RuntimeException`, nên Java cho phép lambda ném nó mà không cần khai báo `throws`. Nhưng “không bị bắt buộc” không có nghĩa “được xử lý an toàn”: nếu không có nơi nào bắt, phép tính có thể dừng và ngoại lệ được truyền lên ngăn xếp lời gọi.

`IOException` là checked exception. Khi dùng một giao diện hàm chuẩn không khai báo nó, phải lựa chọn một trong các chiến lược: bắt tại chỗ và trả giá trị dự phòng, biến lỗi thành dữ liệu trả về, hoặc chuyển nó thành unchecked exception có lưu `cause`. Không có chiến lược nào đúng cho mọi ứng dụng.

## 3. Viết try/catch ngay bên trong thân lambda

Một lambda có thân biểu thức đơn như `x -> x + 1` không cho phép viết trực tiếp các **câu lệnh** `try`, `catch`, `return` bên trong biểu thức ấy. Muốn xử lý ngoại lệ, chuyển sang **thân khối** `{ ... }`:

```java
Consumer<String> printInteger = text -> {
    try {
        int number = Integer.parseInt(text);
        System.out.println("number=" + number);
    } catch (NumberFormatException e) {
        System.out.println("invalid=" + text);
    }
};
```

Đây là đoạn mã minh họa cần đặt trong một phương thức đã import `java.util.function.Consumer`. Với `printInteger.accept("12")`, nó in `number=12`; còn `printInteger.accept("oops")` in `invalid=oops`. `Consumer.accept` trả `void`, vì vậy thân khối không cần `return` giá trị.

Những điểm cú pháp phải nhớ:

1. Dùng `-> { ... }` khi có nhiều câu lệnh hoặc khối `try/catch`.
2. Ngoặc `{ ... }` của thân lambda nằm **ngoài** `try/catch`; dấu `;` sau `};` kết thúc câu lệnh gán biến.
3. Catch nên nhắm vào **kiểu ngoại lệ cụ thể** có thể và cần xử lý.
4. Phần `catch` chạy khi ngoại lệ phù hợp phát sinh trong `try`; nếu bắt xong không ném lại, lambda có thể tiếp tục hoặc hoàn tất theo phần thân.
5. Bắt ngoại lệ để ghi log không đồng nghĩa đã khôi phục thành công. Nếu phép biến đổi cần kết quả, phải quyết định kết quả được trả về như thế nào.

## 4. Function<T,R>: catch xong vẫn cần trả R

Khác `Consumer<T>`, `Function<T,R>` có phương thức `R apply(T value)`; một thân khối muốn hoàn tất bình thường phải trả giá trị tương thích `R`. Ví dụ:

```java
Function<String, Integer> safeParse = text -> {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return -1;
    }
};
```

Đây là một lệnh hợp lệ trong phương thức có import `Function`. Nếu chuỗi là `"18"`, kết quả `18`; nếu không phải số, kết quả `-1`. Nhưng cách dùng sentinel `-1` có **nguy cơ nhập nhằng**: `"-1"` cũng là một số hợp lệ! Nên chỉ chọn giá trị dự phòng nếu ứng dụng có quy ước rõ rằng nó không thể bị hiểu là dữ liệu thật.

Ví dụ sau **cố ý không biên dịch**:

```text
Function<String, Integer> broken = text -> {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        System.err.println("Invalid number");
    }
};
```

Nguyên nhân: nhánh `catch` có thể kết thúc mà không `return Integer`, vi phạm hợp đồng của `Function.apply`. Sửa bằng `return` một giá trị phù hợp, hoặc `throw` một ngoại lệ thích hợp. Nếu kiểu đích trả `void`, quy tắc khác: không thể `return` một giá trị trong `Consumer.accept`.

Nếu thân `catch` gọi `throw new IllegalArgumentException(...)`, đường đi đó **kết thúc đột ngột vì ngoại lệ**, không cần một lệnh `return` phía sau. Java sẽ kiểm tra chính xác từng đường đi của phần thân.

## 5. Ví dụ Java 17 hoàn chỉnh: nhiều chiến lược xử lý

Lưu toàn bộ chương trình sau vào tệp `LambdaExceptionHandlingDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.function.Consumer;
import java.util.function.Function;

public class LambdaExceptionHandlingDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static String checkedUpper(String value) throws IOException {
        if ("FAIL".equals(value)) {
            throw new IOException("unreadable");
        }
        return value.toUpperCase(Locale.ROOT);
    }

    static <T, R> Function<T, R> uncheckedIo(IoFunction<T, R> function) {
        return value -> {
            try {
                return function.apply(value);
            } catch (IOException e) {
                throw new UncheckedIOException("IO operation failed", e);
            }
        };
    }

    public static void main(String[] args) {
        Consumer<String> printInteger = text -> {
            try {
                int number = Integer.parseInt(text);
                System.out.println("number=" + number);
            } catch (NumberFormatException e) {
                System.out.println("invalid=" + text);
            }
        };
        List.of("12", "oops").forEach(printInteger);

        Function<String, String> fallback = text -> {
            try {
                return checkedUpper(text);
            } catch (IOException e) {
                return "N/A";
            }
        };
        System.out.println(fallback.apply("java"));
        System.out.println(fallback.apply("FAIL"));

        Function<String, Optional<String>> safe = text -> {
            try {
                return Optional.of(checkedUpper(text));
            } catch (IOException e) {
                return Optional.empty();
            }
        };
        System.out.println(safe.apply("ok").orElse("missing"));
        System.out.println(safe.apply("FAIL").orElse("missing"));

        List<Integer> parsed = List.of("1", "bad", "3")
                .stream()
                .map(text -> {
                    try {
                        return Integer.parseInt(text);
                    } catch (NumberFormatException e) {
                        return -1;
                    }
                })
                .toList();
        System.out.println(parsed);

        Function<String, String> adapted =
                uncheckedIo(LambdaExceptionHandlingDemo::checkedUpper);
        System.out.println(adapted.apply("hello"));
        try {
            adapted.apply("FAIL");
        } catch (UncheckedIOException e) {
            System.out.println(e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 LambdaExceptionHandlingDemo.java
java LambdaExceptionHandlingDemo
```

Đầu ra chính xác:

```text
number=12
invalid=oops
JAVA
N/A
OK
missing
[1, -1, 3]
HELLO
IOException
```

Các trường hợp trong chương trình:

- `printInteger` bắt `NumberFormatException` trực tiếp trong thân `Consumer`, hiển thị dòng thông báo cho dữ liệu sai thay vì làm dừng lời gọi.
- `fallback` gọi phương thức có `throws IOException`, bắt ngoại lệ và trả `"N/A"` như một quy tắc nghiệp vụ minh họa.
- `safe` biến **thành công/thất bại** thành `Optional<String>`: `Optional.of(...)` khi thành công và `Optional.empty()` khi gặp `IOException`.
- Pipeline stream dùng `.map(text -> { try ... catch ... })` để chuyển từng chuỗi sang số; phần tử `"bad"` được thay bằng `-1`, tạo danh sách `[1, -1, 3]`.
- `uncheckedIo` là hàm adapter nhận giao diện hàm do ta định nghĩa có thể ném `IOException`, rồi tạo `Function<T,R>` chuẩn bằng cách **bọc ngoại lệ vào `UncheckedIOException`**. Tình huống `"FAIL"` được mã gọi `adapted.apply` bắt bên ngoài.
- `e.getCause().getClass().getSimpleName()` cho `IOException`: nguyên nhân gốc được lưu trong wrapper, không bị mất như khi chỉ ném một ngoại lệ chung không có `cause`.

Phương thức `checkedUpper` cố ý ném `IOException` khi đầu vào bằng `"FAIL"` để ví dụ **độc lập và tất định**, không cần tạo file thật. Trong mã sản xuất, checked exception thường đến từ đọc file, I/O mạng hoặc truy cập tài nguyên.

## 6. Tại sao checked exception không thể tự xuyên qua Function.apply?

Giao diện chuẩn có hợp đồng (dạng rút gọn để học):

```java
@FunctionalInterface
interface Function<T, R> {
    R apply(T value);
}
```

`apply` không có `throws IOException`. Trong khi đó:

```java
static String checkedUpper(String value) throws IOException {
    if ("FAIL".equals(value)) throw new IOException("unreadable");
    return value;
}
```

Hai mẩu là **mã minh họa chữ ký**, không phải hai khai báo bạn nên ghép nguyên khối vào cùng tên `Function` của thư viện.

Lời gán sau **cố ý không biên dịch** (giả sử đã có `checkedUpper`):

```text
Function<String, String> broken = text -> checkedUpper(text);
```

Lỗi là `unreported exception IOException; must be caught or declared to be thrown`. Lambda triển khai `Function.apply` không thể mở rộng `throws` bằng một checked exception mà SAM không cho phép. Ngay cả khi **phương thức chứa lambda** khai báo `throws IOException`, điều đó không tự thay đổi hợp đồng của `Function.apply`, vì lambda có thể được gọi ở một nơi khác.

Cách sửa: dùng thân khối và xử lý tại chỗ, hoặc thiết kế functional interface riêng có `throws IOException` khi muốn bên gọi tự quyết định. Với ngoại lệ không kiểm tra như `NumberFormatException`, Java không buộc phải bắt khi truyền lambda cho `Function`.

## 7. Chiến lược 1: fallback có chủ ý

Khi hệ thống có giá trị thay thế được định nghĩa rõ, bạn có thể trả giá trị mặc định trong `catch`:

```java
Function<String, String> fallback = text -> {
    try {
        return checkedUpper(text);
    } catch (IOException e) {
        return "N/A";
    }
};
```

Đây là đoạn trích nằm trong chương trình đầy đủ ở mục 5.

Ưu điểm: caller vẫn nhận `String` đúng kiểu; có thể áp dụng `map` trong stream mà không phải đổi cấu trúc dữ liệu. Nhược điểm: thông tin lỗi bị **ẩn khỏi kết quả** và `"N/A"` có thể bị hiểu là dữ liệu có ý nghĩa. Phù hợp cho một số giao diện hiển thị hoặc quy tắc dự phòng rõ ràng; không phù hợp nếu lỗi đòi hỏi retry, cảnh báo hay dừng giao dịch.

Nếu fallback có thể gây nhầm, hãy cân nhắc kiểu kết quả thể hiện lỗi, hoặc truyền ngoại lệ lên tầng xử lý. Trong mã thật, nếu cần ghi log thì log ở ranh giới phù hợp; tránh lặp một ngoại lệ ở quá nhiều tầng.

## 8. Chiến lược 2: dùng Optional để tránh giá trị giả

Khi muốn biểu thị **có hoặc không có** giá trị hợp lệ:

```java
Function<String, Optional<String>> safe = text -> {
    try {
        return Optional.of(checkedUpper(text));
    } catch (IOException e) {
        return Optional.empty();
    }
};
```

Đoạn này nằm trong chương trình đầy đủ và cần `import java.util.Optional;`, `import java.util.function.Function;`. Caller có thể dùng `safe.apply("FAIL").orElse("missing")` và nhận `"missing"`.

Lưu ý quan trọng:

- `Optional.empty()` **không cho biết nguyên nhân** thất bại; mất thông tin về loại ngoại lệ và thông điệp.
- `Optional.of(result)` yêu cầu `result` không `null`; nếu kết quả có thể null, dùng `Optional.ofNullable(result)`.
- Không nên dùng `Optional.empty()` để che giấu mọi lỗi I/O nghiêm trọng hoặc lỗi lập trình. Hãy giới hạn catch vào lỗi đã xác định là có thể xử lý.
- Nếu nghiệp vụ cần biết lỗi cụ thể, có thể dùng một kiểu kết quả riêng như `Success<T>`/`Failure<E>` trong một `sealed interface`, thay vì cố nén mọi lỗi vào giá trị vắng mặt.

`Optional` mô tả **sự hiện diện của giá trị**, không phải một cơ chế tổng quát lưu lỗi và stack trace.

## 9. Chiến lược 3: chuyển checked exception thành unchecked exception

Khi cần truyền một thao tác ném `IOException` vào API chỉ nhận `Function<T,R>`, có thể định nghĩa giao diện riêng và adapter:

```java
@FunctionalInterface
interface IoFunction<T, R> {
    R apply(T value) throws IOException;
}

static <T, R> Function<T, R> uncheckedIo(IoFunction<T, R> function) {
    return value -> {
        try {
            return function.apply(value);
        } catch (IOException e) {
            throw new UncheckedIOException("IO operation failed", e);
        }
    };
}
```

Đây là trích đoạn từ lớp đầy đủ; import `IOException`, `UncheckedIOException` từ `java.io` và `Function` từ `java.util.function`. Khi dùng `uncheckedIo(LambdaExceptionHandlingDemo::checkedUpper)`, adapter nhận phương thức có checked exception, nhưng hàm kết quả phù hợp với `Function<String,String>`.

Ưu điểm: **giữ được nguyên nhân gốc** trong `getCause()`; caller có thể bắt `UncheckedIOException` ở ranh giới phù hợp; code stream không bị lặp nhiều `try/catch`.

Nhược điểm: lỗi không còn được trình biên dịch ép xử lý ở điểm gọi `apply`. Vì thế cần tài liệu API ghi rõ ngoại lệ unchecked có thể lan ra. **Không** bắt `Exception` rồi bọc tất cả vào `RuntimeException` một cách bừa bãi: làm vậy có thể che mất lỗi lập trình và mất ý nghĩa phân loại lỗi. Adapter trong ví dụ chủ động chỉ bắt `IOException`.

Nếu một phương thức chỉ có thể ném một checked exception loại khác, hãy thiết kế wrapper tương ứng hoặc để interface tùy chỉnh truyền loại đó. Không mặc định mọi checked exception đều nên chuyển thành `UncheckedIOException`.

## 10. Chiến lược 4: để caller bắt ngoại lệ

Không phải mọi lỗi đều cần biến thành dữ liệu thay thế. Khi một bước chuyển đổi thất bại là **bất thường** và phải dừng quy trình, bạn có thể để unchecked exception lan ra:

```java
Function<String, Integer> parse = Integer::parseInt;

try {
    System.out.println(parse.apply("not-a-number"));
} catch (NumberFormatException e) {
    System.out.println("Invalid input");
}
```

Đây là các lệnh minh họa trong phương thức có import `Function`. Phần thân lambda không bắt gì; ngoại lệ phát sinh khi gọi `apply` và được caller bắt. Điều này giúp logic xử lý lỗi tập trung ở ranh giới nghiệp vụ, thay vì phân tán fallback không nhất quán trong các phép biến đổi.

Với adapter `uncheckedIo`, caller bắt `UncheckedIOException` để đọc `getCause()` là `IOException`. Như vậy “xử lý ngoại lệ liên quan tới lambda” **không bắt buộc** mọi `catch` phải nằm trong lambda: vị trí bắt phải phản ánh nơi có đủ thông tin để quyết định nên làm gì khi lỗi xuất hiện.

## 11. Xử lý trong Stream và khác biệt giữa map và forEach

Lambda thường được truyền vào `stream().map(...)`, `filter(...)`, `forEach(...)`. Các API đó dùng `Function`, `Predicate` hoặc `Consumer` chuẩn; vì vậy các quy tắc checked exceptions ở trên vẫn áp dụng.

Ví dụ trong mục 5:

```java
List<Integer> parsed = List.of("1", "bad", "3")
        .stream()
        .map(text -> {
            try {
                return Integer.parseInt(text);
            } catch (NumberFormatException e) {
                return -1;
            }
        })
        .toList();
```

Đây là đoạn trích chạy được trong chương trình đã import `java.util.List`. Kết quả `[1, -1, 3]`, mỗi phần tử nguồn tương ứng một phần tử đích. Nhưng giá trị `-1` **có thể che lỗi dữ liệu**, vì chuỗi `"-1"` cũng chuyển thành số hợp lệ.

Có ba hướng thiết kế tùy mục tiêu:

1. **Giữ mỗi phần tử và đặt fallback:** có thể dùng một giá trị đặc biệt nếu quy ước an toàn; cần tính đến khả năng dữ liệu hợp lệ trùng fallback.
2. **Trả `Optional<T>` và lọc phần thất bại:** `map(s -> safeParse(s))` rồi `flatMap(Optional::stream)`; cách này thay đổi số lượng phần tử và có thể làm mất thông tin vị trí lỗi.
3. **Dừng và để lỗi lan ra:** phù hợp khi toàn bộ danh sách phải hợp lệ, chẳng hạn dữ liệu cho giao dịch tài chính. Một `NumberFormatException` không bị bắt có thể làm terminal operation thất bại.

**Stream là lazy** với phần lớn thao tác trung gian. Định nghĩa `stream.map(lambda)` chưa nhất thiết thực thi lambda; terminal operation như `toList()`, `collect(...)`, `forEach(...)` kích hoạt xử lý theo ngữ nghĩa stream. Nếu lambda ném unchecked exception mà không xử lý, hoạt động có thể kết thúc đột ngột; không nên suy đoán các phần tử sau vẫn được xử lý.

Với `parallelStream()`, không nên dựa vào thứ tự log của các lambda hoặc chia sẻ `ArrayList`/`StringBuilder` không đồng bộ chỉ để tập hợp lỗi. Nếu muốn thống kê lỗi theo từng phần tử, hãy trả **kết quả có cấu trúc** rồi tổng hợp, tránh side effect không an toàn.

## 12. finally, tài nguyên và đóng kết nối

`try/catch/finally` có thể xuất hiện bên trong **thân khối lambda** như trong một phương thức Java bình thường:

```java
Consumer<String> action = text -> {
    try {
        System.out.println("start:" + text);
    } catch (RuntimeException e) {
        System.err.println(e.getMessage());
    } finally {
        System.out.println("finished");
    }
};
```

Đây là ví dụ minh họa trong phương thức có import `Consumer`. `finally` thường chạy khi thoát khỏi `try`/`catch`, kể cả khi có `return` hoặc một exception khác được ném; có các ngoại lệ ở cấp JVM/quá trình nên không được khẳng định nó **luôn luôn** chạy trong mọi hoàn cảnh.

Với tài nguyên cần đóng (`InputStream`, `BufferedReader`, kết nối...), ưu tiên **try-with-resources** để đóng khi rời khối:

```java
Function<java.nio.file.Path, String> readText = path -> {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    } catch (IOException e) {
        throw new UncheckedIOException(e);
    }
};
```

Đây là **đoạn minh họa đặt trong một phương thức**, không phải chương trình độc lập và chưa có ví dụ đầu ra do phụ thuộc tệp. Phương thức `newBufferedReader` và `readLine` có thể ném `IOException`; `reader` được đóng theo cơ chế `AutoCloseable` khi ra khỏi khối. `readLine()` có thể trả `null` nếu file rỗng, nên API ứng dụng cần xử lý trường hợp ấy.

Không nên mở rồi bỏ mặc tài nguyên trong lambda được gọi nhiều lần. Thân lambda có thể chạy nhiều lần và ở những thời điểm khác nhau; việc đóng kết nối đúng chỗ là trách nhiệm của code trong lambda hoặc tầng bao quanh.

## 13. Phân biệt InterruptedException và tác dụng phụ

Một số API chặn như `Thread.sleep` có thể ném `InterruptedException` (checked). Khi viết `Runnable` hoặc `Consumer`, nếu quyết định không truyền checked exception qua kiểu đích, phải bắt nó. Trong nhiều tình huống, cách xử lý đúng là **khôi phục cờ ngắt** rồi kết thúc công việc thích hợp:

```java
Runnable task = () -> {
    try {
        Thread.sleep(10);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
};
```

Đây là một lệnh minh họa đặt trong phương thức. Không nên bắt `InterruptedException` rồi âm thầm tiếp tục làm việc, vì điều đó có thể phá giao thức hủy tác vụ. Với các API cho phép truyền ngoại lệ, cân nhắc lan truyền theo đúng hợp đồng thay vì luôn chuyển sang `RuntimeException`.

Tương tự, khi lambda cập nhật shared state hoặc ghi log trong `catch`, cần quan tâm **an toàn luồng**, **lặp lại thao tác** và **khả năng kiểm thử**. Một hàm chuyển đổi thuần có thể dễ ghép, tái sử dụng và kiểm thử hơn; việc ghi log/phản hồi lỗi nên được thiết kế có chủ đích.

## 14. Những lỗi phổ biến và cách sửa

| Vấn đề | Vì sao sai/nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Gọi phương thức `throws IOException` trực tiếp trong `Function.apply` | `Function.apply` không khai báo checked exception | `try/catch` trong lambda hoặc adapter phù hợp |
| Viết `x -> try { ... }` | `try` là câu lệnh, không phải expression body | Dùng `x -> { try { ... } catch (...) { ... } }` |
| `Function` có `catch` chỉ ghi log, không trả kết quả | Một đường đi có thể không trả `R` | `return` giá trị hợp lệ hoặc `throw` |
| `Consumer` dùng `return x;` | SAM có kiểu `void` | Dùng `return;` khi cần kết thúc sớm |
| `catch(Exception e) { return null; }` cho mọi lỗi | Che nhiều lỗi khác nhau, có thể làm phát sinh NPE muộn | Bắt cụ thể, định nghĩa fallback rõ hoặc trả kết quả lỗi có cấu trúc |
| Dùng `-1` làm mọi kết quả lỗi parse | `-1` có thể là đầu vào hợp lệ | Dùng `Optional` hay kiểu kết quả `Success/Failure` |
| `throw new RuntimeException()` không giữ nguyên nhân | Mất `cause`, khó gỡ lỗi | Dùng wrapper với `cause` như `new UncheckedIOException(e)` |
| Bắt `InterruptedException` rồi bỏ qua | Làm mất tín hiệu hủy tác vụ | Khôi phục trạng thái ngắt hoặc xử lý theo hợp đồng |
| Cho rằng lỗi trong `map` xảy ra ngay khi khai báo stream | Stream trung gian thường lazy | Xem xét terminal operation và vị trí catch |
| Dùng side effect thu thập lỗi trong parallel stream | Có thể race hoặc sai thứ tự | Dùng kết quả bất biến/cấu trúc rồi tổng hợp |
| Mặc định mọi ngoại lệ nên được nuốt để tiếp tục | Có lỗi phải dừng luồng xử lý | Chọn chính sách dựa vào nghiệp vụ, không theo tiện lợi cú pháp |

Ba lỗi biên dịch thường thấy đã được kiểm chứng bằng `javac --release 17`: unchecked checked exception không được catch/declare đúng hợp đồng; một `Function` thiếu `return` ở `catch`; và một `Consumer` cố `return` giá trị.

## 15. Bài tập thực hành

**Bài 1 — Bắt lỗi parse.** Viết `Function<String,Integer>` chuyển số, nếu sai định dạng thì trả `0`.

Gợi ý đáp án:

```java
Function<String, Integer> parseOrZero = text -> {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return 0;
    }
};
```

Đặt trong phương thức có import `Function`. Đây là giải pháp **theo yêu cầu bài tập**, không phải mặc định nên dùng trong hệ thống thực: số `0` hợp lệ có thể không phân biệt được với lỗi parse.

**Bài 2 — Trả lỗi dưới dạng giá trị.** Vì sao `Function<String, Optional<Integer>>` có thể tốt hơn `Function<String,Integer>` trả `-1` khi lỗi?

Đáp án: `Optional.empty()` biểu thị không có số hợp lệ mà không xung đột trực tiếp với một số nguyên hợp lệ. Tuy nhiên nó không mang nguyên nhân lỗi; khi cần chẩn đoán chi tiết, phải dùng kiểu kết quả khác.

**Bài 3 — Lỗi checked.** `Function<String,String> f = x -> checkedUpper(x);` có hợp lệ nếu `checkedUpper` khai báo `throws IOException` không?

Đáp án: không, vì `Function.apply` không khai báo `IOException`. Dùng `try/catch`, đổi sang functional interface có `throws IOException` hoặc adapter có chính sách chuyển lỗi rõ ràng.

**Bài 4 — Dòng nào được xử lý?** Nếu danh sách `List.of("1", "x", "3")` qua `stream().map(Integer::parseInt).toList()` và không có catch, chuyện gì xảy ra?

Đáp án: terminal operation thực hiện chuyển đổi, đến phần tử `"x"` thì `NumberFormatException` được ném. Không có danh sách kết quả hoàn chỉnh từ lời gọi `toList()` đó; thao tác kết thúc đột ngột. Nếu cần tiếp tục từng phần tử, phải xác định chính sách lỗi trước.

**Bài 5 — Rethrow giữ nguyên nhân.** Có `IOException e` từ thao tác I/O trong `Function`. Vì sao `throw new UncheckedIOException(e);` tốt hơn `throw new RuntimeException("failed");` nếu cần báo lỗi gốc?

Đáp án: wrapper `UncheckedIOException` truyền theo ngữ nghĩa lỗi I/O và giữ `e` làm `cause`. Caller có thể lấy `getCause()` để kiểm tra stack trace, loại và thông điệp gốc.

**Bài 6 — Kiểm tra return.** Với `Function<String,Integer>`, đoạn `x -> { try { return Integer.parseInt(x); } catch(NumberFormatException e) { System.out.println("bad"); } }` sai ở đâu?

Đáp án: catch có thể hoàn tất bình thường mà không trả số. Cần `return` số theo quy ước hoặc `throw` một exception phù hợp.

## 16. Ghi nhớ

- `try/catch` trong lambda được viết ở **thân khối** `-> { ... }`, không phải sau dấu `->` như một biểu thức trần.
- **Checked exception** phải được xử lý phù hợp với `throws` của phương thức SAM; `Function`, `Consumer` và các interface chuẩn thông dụng không tự cho phép `IOException`.
- **Unchecked exception** không bắt buộc catch, nhưng vẫn có thể cần chính sách xử lý ở lambda hoặc caller.
- Với `Function<T,R>`, bắt lỗi xong phải **trả `R` hoặc ném ngoại lệ** trên mỗi đường đi tương ứng; với `Consumer<T>`, không trả giá trị.
- Chọn rõ chính sách: **fallback**, **Optional**, **kết quả mang lỗi**, hoặc **bọc và ném lại**. Tránh nuốt lỗi và tránh giá trị mặc định mơ hồ.
- `UncheckedIOException` là wrapper chuyên biệt hợp lý cho `IOException` khi chọn chuyển thành unchecked, và cần giữ nguyên nhân qua `cause`.
- Trong Stream, lỗi của lambda thường phát sinh khi terminal operation kích hoạt xử lý; tính thứ tự và an toàn luồng quan trọng nếu có side effects.

Tài liệu chuẩn: [Java SE 17 — Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html), [Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html), [UncheckedIOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html), [JLS §11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html), [JLS §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27).