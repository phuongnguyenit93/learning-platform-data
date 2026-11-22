# Checked exception trong lambda theo hợp đồng của kiểu hàm trong Java

Trong Java, một biểu thức lambda không có danh sách `throws` của riêng nó. Việc lambda có được phép để **checked exception** thoát ra hay không phụ thuộc vào **functional interface** mà biểu thức lambda đang được gán hoặc chuyển vào. Chính xác hơn, trình biên dịch kiểm tra những exception mà phần thân lambda có thể ném so với **mệnh đề `throws` của function type/functional descriptor** thuộc kiểu đích (*target type*).

Điều này giải thích vì sao **cùng một thao tác có thể biên dịch khi viết dưới dạng `Callable` nhưng không biên dịch khi viết dưới dạng `Supplier`**, và vì sao phương thức được tham chiếu bằng `::` có `throws IOException` đôi khi không thể dùng trực tiếp trong `Stream.map`.

Ý chính cần nhớ:

1. `Runnable.run()`, `Supplier.get()`, `Function.apply()` và `Consumer.accept()` trong thư viện Java chuẩn **không khai báo checked exception**.
2. `Callable.call() throws Exception` cho phép phần thân lambda ném những checked exception thuộc `Exception`.
3. Bạn có thể định nghĩa một functional interface riêng với `throws IOException` hoặc tham số generic `E extends Exception` nếu caller cần nhận và xử lý lỗi checked.
4. Nếu kiểu hàm đích không cho phép một checked exception, lambda phải **xử lý nó trong thân** hoặc **chuyển sang một loại lỗi được hợp đồng cho phép**, chứ không thể tự thêm `throws` sau dấu `->`.
5. Gán một lambda sang kiểu khác không làm đổi bản chất của nguồn lỗi; **kiểu đích quyết định hợp đồng kiểm tra tại thời điểm biên dịch**.

## 1. Phân biệt checked exception và unchecked exception

Java dùng `Throwable` làm gốc của hệ thống ngoại lệ. Đối với kiểm tra tại compile time:

| Nhóm | Ví dụ | Có phải bắt hoặc khai báo theo quy tắc checked exception? |
| --- | --- | --- |
| **Checked exception** | `IOException`, `SQLException`, `ParseException`, custom `Exception` không thuộc `RuntimeException` | Có |
| **Unchecked exception** | `RuntimeException` và các lớp con như `IllegalArgumentException`, `NumberFormatException` | Không |
| **Unchecked `Error`** | `Error` và các lớp con | Không; thường biểu diễn lỗi nghiêm trọng, không dùng cho validation nghiệp vụ |

Ví dụ phương thức nguồn:

```java
static String load(String key) throws java.io.IOException {
    if ("missing".equals(key)) {
        throw new java.io.IOException("source unavailable");
    }
    return "value:" + key;
}
```

Đây là một **phương thức minh họa**. Khi gọi `load(key)`, mã sử dụng phải thỏa hợp đồng checked `IOException`: hoặc đặt lời gọi trong `try-catch` phù hợp, hoặc nằm trong phương thức/lambda được phép truyền checked exception đó ra ngoài.

Với lambda, điểm khác là **lambda không tự công bố `throws IOException` bằng cú pháp của chính nó**. Nó phải dựa vào functional interface của ngữ cảnh.

## 2. Lambda cần một functional interface làm kiểu đích

Một **functional interface** là interface có đúng **một phương thức abstract theo quy tắc xác định function type**, dù vẫn có thể có phương thức `default`, `static` hoặc phương thức tương ứng với các phương thức `public` của `Object`.

Ví dụ:

```java
@FunctionalInterface
interface CheckedReader {
    String read(String key) throws java.io.IOException;
}
```

Lambda phù hợp:

```java
CheckedReader reader = key -> {
    if (key.isBlank()) {
        throw new java.io.IOException("blank key");
    }
    return "value:" + key;
};
```

Đây là **các khai báo minh họa**, đặt trong lớp/phạm vi Java hợp lệ. Tham số `key` và giá trị trả về của lambda được ràng buộc bởi `CheckedReader.read(String)`. Vì phương thức abstract khai báo `throws IOException`, phần thân có thể ném checked `IOException`.

Nếu đổi kiểu đích:

```java
java.util.function.Function<String, String> reader = key -> {
    if (key.isBlank()) {
        throw new java.io.IOException("blank key"); // Không biên dịch.
    }
    return "value:" + key;
};
```

Mã trên **cố ý không biên dịch**. `Function.apply(T)` không có `throws IOException`. Lambda không thể đưa ra loại checked exception mới ngoài hợp đồng của kiểu hàm đích.

### Lambda không có cú pháp `throws` riêng

Không có cú pháp Java hợp lệ như sau:

```java
// Cố ý SAI CÚ PHÁP.
Function<String, String> reader =
        (String key) throws IOException -> load(key);
```

Lời khai báo `throws` thuộc về **phương thức** hoặc **phương thức abstract của functional interface**, không nằm giữa danh sách tham số và dấu `->` của lambda.

Bạn có thể viết `throws` trên phương thức chứa lambda nếu phương thức đó thực sự phát sinh checked exception trong đường thực thi **của chính nó**, nhưng **không** vì thế mà lambda gán vào `Function` được quyền ném `IOException`. Hai hợp đồng kiểm tra khác nhau.

## 3. “Function type” hay “functional descriptor” chứa những gì?

Khi compiler kiểm tra lambda, nó xét kiểu hàm mục tiêu với các thông tin thiết yếu:

- **Số lượng và kiểu tham số**.
- **Kiểu trả về**.
- **Các kiểu trong `throws`** được function type cho phép.
- Các ràng buộc do generic type, method type parameter hoặc kiểu đích suy ra.

Ví dụ:

```java
@FunctionalInterface
interface Parser {
    int parse(String text) throws java.text.ParseException;
}
```

Biểu thức:

```java
Parser parser = text -> {
    if (text.isBlank()) {
        throw new java.text.ParseException(
                "empty input", 0);
    }
    return text.length();
};
```

hợp lệ vì `Parser.parse(String)` khai báo `throws ParseException`. Nhưng cùng một phần thân, nếu gán vào `ToIntFunction<String>`, sẽ không hợp lệ nếu `ParseException` thoát ra mà không được xử lý, vì `ToIntFunction.applyAsInt` không khai báo checked exception.

**Lưu ý:** Java không bắt người viết lambda phải **thực sự** ném một checked exception được khai báo ở kiểu đích. Lambda không ném lỗi checked nào vẫn có thể triển khai interface có `throws IOException`.

## 4. So sánh các functional interface quen thuộc

| Functional interface | Phương thức hàm | Checked `throws` của phương thức hàm |
| --- | --- | --- |
| `Runnable` | `void run()` | Không |
| `Supplier<T>` | `T get()` | Không |
| `Consumer<T>` | `void accept(T t)` | Không |
| `Function<T,R>` | `R apply(T t)` | Không |
| `Predicate<T>` | `boolean test(T t)` | Không |
| `BiFunction<T,U,R>` | `R apply(T t, U u)` | Không |
| `Callable<V>` | `V call() throws Exception` | `Exception` |
| Custom `CheckedReader` | `String read(String) throws IOException` | `IOException` |
| Custom `ThrowingFunction<T,R,E>` | `R apply(T) throws E` | Tham số kiểu `E` theo ràng buộc |

Các tên kiểu trong bảng là của `java.lang.Runnable`, `java.util.concurrent.Callable`, `java.util.function` hoặc interface custom. Không nên ghi nhớ đơn giản “lambda không ném được checked exception”: lambda **ném được** khi hợp đồng functional interface cho phép.

### `Runnable` và `Callable` khác nhau ở checked exception

Một lambda dùng `Runnable`:

```java
Runnable action = () -> {
    throw new java.io.IOException("I/O failed"); // Không biên dịch.
};
```

Phương thức `run()` không khai báo checked `IOException`.

Cùng ý tưởng với `Callable`:

```java
java.util.concurrent.Callable<String> action = () -> {
    throw new java.io.IOException("I/O failed");
};
```

Đoạn `Callable` **hợp lệ**: `call() throws Exception` cho phép `IOException`.

Tuy nhiên, khi caller dùng `action.call()` thông qua **kiểu `Callable<String>`**, compiler thấy `throws Exception`, nên caller phải bắt hoặc khai báo loại **`Exception`** tương ứng, không tự suy ra rằng lambda này chỉ ném `IOException`.

## 5. Ví dụ Java 17+ hoàn chỉnh: cùng thao tác, ba hợp đồng xử lý

Chương trình không cần đọc tệp thật; một hàm giả lập ném checked `IOException` để đầu ra hoàn toàn xác định.

Lưu toàn bộ nội dung vào **`CheckedLambdaContractDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.concurrent.Callable;
import java.util.function.Function;

public class CheckedLambdaContractDemo {

    @FunctionalInterface
    interface CheckedReader {
        String read(String key) throws IOException;
    }

    static String load(String key) throws IOException {
        if ("missing".equals(key)) {
            throw new IOException("source unavailable");
        }
        return "value:" + key;
    }

    static void inspect(String key) {
        CheckedReader checked =
                CheckedLambdaContractDemo::load;

        try {
            System.out.println(
                    "checked=" + checked.read(key));
        } catch (IOException ex) {
            System.out.println(
                    "checked error=" + ex.getMessage());
        }

        Function<String, String> converted = value -> {
            try {
                return load(value);
            } catch (IOException cause) {
                throw new UncheckedIOException(
                        "cannot resolve " + value, cause);
            }
        };

        try {
            System.out.println(
                    "function=" + converted.apply(key));
        } catch (UncheckedIOException ex) {
            System.out.println(
                    "function error=" + ex.getMessage());
            System.out.println(
                    "function cause="
                    + ex.getCause().getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        inspect("ok");
        inspect("missing");

        Callable<String> task = () -> load("ok");
        try {
            System.out.println("callable=" + task.call());
        } catch (Exception ex) {
            System.out.println(
                    "callable error=" + ex.getClass().getSimpleName());
        }

        Runnable action = () -> {
            try {
                load("missing");
            } catch (IOException ex) {
                System.out.println(
                        "runnable handled=" + ex.getMessage());
            }
        };
        action.run();
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 CheckedLambdaContractDemo.java
java CheckedLambdaContractDemo
```

**Stdout chính xác:**

```text
checked=value:ok
function=value:ok
checked error=source unavailable
function error=cannot resolve missing
function cause=IOException
callable=value:ok
runnable handled=source unavailable
```

### Đọc ba kiểu hợp đồng

**`CheckedReader`:** phương thức abstract `read(String) throws IOException` cho phép lambda hoặc method reference truyền checked `IOException` ra ngoài. Người gọi qua `CheckedReader` bắt `IOException` trực tiếp.

**`Function<String,String>`:** `apply` không cho phép checked `IOException`. Lambda phải bắt lỗi ngay trong thân; ví dụ chuyển lỗi I/O sang `UncheckedIOException` và **giữ `cause`**. Người gọi `Function` không bắt buộc phải có `catch`, nhưng vẫn có thể gặp unchecked exception ở runtime.

**`Callable<String>`:** `call() throws Exception` cho phép method body gọi `load` mà không cần bắt `IOException` bên trong. Tuy nhiên caller qua `Callable` phải xử lý `Exception` theo khai báo của `call`.

**`Runnable`:** `run()` không có checked `throws`, nên lambda phải tự bắt `IOException`. Ở ví dụ, hành động chỉ in một dòng báo lỗi, không ném lại, giúp chứng minh cú pháp. Trong hệ thống thật, quyết định phục hồi/báo lỗi không nên chỉ là `println` rồi lặng lẽ coi tác vụ thành công.

**Quan trọng:** `UncheckedIOException` phù hợp khi chuyển một lỗi I/O checked sang unchecked, bởi nó yêu cầu một `IOException` làm cause. Với checked exception không phải I/O, cần chọn wrapper hợp đồng khác; đừng cố ép mọi loại checked exception thành `UncheckedIOException`.

## 6. Kiểu đích quyết định checked exception ở thời điểm gán lambda

Một lambda biểu diễn việc gọi hàm:

```java
() -> load("missing")
```

**chưa có kiểu độc lập giống một biểu thức `String` thông thường**. Lambda được kiểm tra trong ngữ cảnh kiểu đích khi gán biến, truyền đối số hoặc ép kiểu sang functional interface.

Ví dụ cùng biểu thức:

```java
java.util.concurrent.Callable<String> c =
        () -> load("missing"); // Hợp lệ.

java.util.function.Supplier<String> s =
        () -> load("missing"); // Không biên dịch.
```

Đây là đoạn minh họa, giả định `load` là phương thức ném `IOException`. `Callable.call` cho phép `Exception`; `Supplier.get` không cho phép checked `IOException`.

### Có thể thêm `throws IOException` cho phương thức chứa lambda để sửa không?

Không, nếu lỗi nằm trong phần thân lambda được gán vào `Supplier`:

```java
// Cố ý KHÔNG BIÊN DỊCH.
static java.util.function.Supplier<String> build()
        throws java.io.IOException {
    return () -> load("missing");
}
```

`build()` chỉ **tạo và trả một lambda**, chưa thực thi lời gọi `load`. Hợp đồng `throws IOException` của `build` không làm thay đổi hợp đồng `Supplier.get()` khi lambda được gọi sau này.

Muốn giữ checked exception để caller xử lý, hãy đổi **kiểu đích** sang functional interface có `throws IOException`. Muốn giữ `Supplier`, hãy xử lý/chuyển lỗi ở trong lambda.

## 7. Method reference `::` tuân theo cùng quy tắc

Không chỉ lambda dạng `x -> method(x)`; **method reference** cũng được kiểm tra với functional interface đích.

Ví dụ:

```java
static String loadFile(String key) throws java.io.IOException {
    if (key.isEmpty()) {
        throw new java.io.IOException("empty key");
    }
    return key;
}
```

Với interface tùy chỉnh cho phép `IOException`:

```java
@FunctionalInterface
interface CheckedLoader {
    String load(String key) throws java.io.IOException;
}

CheckedLoader good = Example::loadFile;
```

Đây là những khai báo minh họa, `Example` là lớp chứa phương thức `loadFile`.

Nhưng:

```java
java.util.function.Function<String, String> bad =
        Example::loadFile; // Không biên dịch vì IOException checked.
```

Thông điệp compiler có thể nhắc `incompatible thrown types` hoặc `unreported exception` tùy ngữ cảnh. Bản chất giống hệt lambda: **function descriptor của kiểu đích không cho phép loại checked exception mà lời gọi được tham chiếu có thể ném**.

### Không thể “sửa” method reference bằng ép kiểu tùy tiện

Ép sang `Function<String,String>` không xóa `IOException` khỏi phương thức nguồn. Cần chọn kiểu hàm phù hợp hoặc viết một lambda adapter có `try-catch` đúng nghĩa.

Đổi sang `Callable` cũng không giải quyết mọi trường hợp: `Callable` không có tham số và trả về một giá trị; method reference với chữ ký nhận đối số chỉ phù hợp nếu danh sách tham số theo kiểu đích có thể ánh xạ đúng.

## 8. Định nghĩa functional interface generic với `E extends Exception`

Trong thư viện tái sử dụng, một interface generic có thể mô tả thao tác biến đổi vừa có kiểu đầu vào/đầu ra vừa có **kiểu checked exception**:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
```

Ba tham số kiểu có ý nghĩa:

- **`T`:** kiểu đầu vào.
- **`R`:** kiểu đầu ra.
- **`E`:** kiểu ngoại lệ được phép ném, bị giới hạn trong các subtype của `Exception`.

Ví dụ một phương thức parse dữ liệu có checked exception tùy chỉnh:

```java
final class ParseFailure extends Exception {
    ParseFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

ThrowingFunction<String, Integer, ParseFailure> parser =
        value -> {
            try {
                return Integer.parseInt(value);
            } catch (NumberFormatException cause) {
                throw new ParseFailure("invalid integer", cause);
            }
        };
```

Đây là đoạn minh họa, cần được đặt trong lớp/phạm vi phù hợp. `ParseFailure` là checked vì extends `Exception` nhưng không extends `RuntimeException`. `throws E` trên phương thức hàm cho phép lambda ném `ParseFailure` khi `E` được xác định là kiểu đó.

### `E` không làm Java tự động bắt ngoại lệ

Caller vẫn phải xử lý:

```java
try {
    int value = parser.apply("12");
    System.out.println(value);
} catch (ParseFailure ex) {
    System.out.println(ex.getMessage());
}
```

Vì kiểu tĩnh của `parser` mang `E=ParseFailure`, trình biên dịch có thể biết loại checked exception cụ thể. Đây là một lợi ích của interface có generic exception parameter so với việc chỉ ghi `throws Exception` cho tất cả thao tác.

### Lưu ý khi một thao tác có nhiều checked exception

Một tham số `E` biểu diễn **một kiểu ngoại lệ tĩnh**. Nếu mã có thể ném hai checked exception độc lập, ví dụ `IOException` và `SQLException`, không phải lúc nào bạn cũng thể hiện chính xác cả hai chỉ bằng một `E` mà không nới lên một supertype chung như `Exception`.

Những lựa chọn thường là:

- Định nghĩa phương thức hàm với `throws IOException, SQLException` nếu đó là chính xác hợp đồng của module.
- Chuyển lỗi sang một custom checked exception theo tầng trừu tượng và giữ `cause`.
- Sử dụng thiết kế kết quả có kiểu nếu lỗi là một phần bình thường của nghiệp vụ.
- Chấp nhận `E=Exception` nếu thư viện thực sự cần độ tổng quát ấy, đồng thời hiểu caller sẽ phải xử lý loại rộng hơn.

Đừng ép một thiết kế generics làm mất ý nghĩa của loại lỗi chỉ để viết API ngắn.

## 9. Adapter từ `ThrowingFunction` sang `Function`: đổi hợp đồng, không tự xóa lỗi

`Stream.map` nhận `Function<? super T, ? extends R>`, tức `Function.apply` **không khai báo checked exception**. Nếu bạn có `ThrowingFunction`, không thể truyền trực tiếp nó vào `map` chỉ vì cùng số lượng tham số.

Có thể viết adapter:

```java
static <T, R, E extends Exception>
java.util.function.Function<T, R> unchecked(
        ThrowingFunction<T, R, E> action) {

    return value -> {
        try {
            return action.apply(value);
        } catch (RuntimeException ex) {
            throw ex;
        } catch (Exception cause) {
            throw new IllegalArgumentException(
                    "conversion rejected", cause);
        }
    };
}
```

Đây là **phương thức minh họa** trong lớp có định nghĩa `ThrowingFunction`. Ý nghĩa:

1. Adapter nhận một hàm **có thể ném checked E**.
2. Lambda bên trong implement `Function.apply`, vốn không có checked `throws`.
3. Nếu nguồn ném một `RuntimeException`, adapter để nguyên lỗi unchecked ấy.
4. Nếu nguồn ném một checked `Exception`, adapter bọc thành `IllegalArgumentException` có `cause`.
5. Caller nhận một `Function` thông thường và có thể truyền vào `Stream.map`.

**Cảnh báo thiết kế:** `IllegalArgumentException` trong ví dụ chỉ là lựa chọn minh họa cho thao tác parse/convert dữ liệu đầu vào. Với lỗi I/O, có thể dùng `UncheckedIOException`; với thao tác bất đồng bộ hoặc lỗi nghiệp vụ, chọn loại wrapper khác đúng hợp đồng.

Adapter **không làm lỗi biến mất**. Nó đổi một đường lỗi checked thành một đường lỗi unchecked; ứng dụng vẫn cần quyết định xử lý ở ranh giới phù hợp.

### Vì sao bắt `RuntimeException` trước `Exception`?

Một `RuntimeException` cũng là lớp con của `Exception`. Nếu chỉ viết `catch (Exception ex)` rồi bọc tất cả, adapter có thể bọc cả lỗi lập trình như `NullPointerException`, làm việc điều tra sai hướng và thay đổi loại runtime mà caller từng mong đợi.

Tách:

```java
catch (RuntimeException ex) {
    throw ex;
} catch (Exception cause) {
    throw new IllegalArgumentException(
            "conversion rejected", cause);
}
```

giữ nguyên lỗi unchecked và chỉ bọc những exception còn lại thuộc nhóm checked. `Error` không bị bắt bởi các nhánh trên; tránh `catch (Throwable)` chung chỉ để “chuyển hết mọi thứ thành thành công”.

## 10. Ví dụ Java 17+ hoàn chỉnh: custom generic function và `Stream.map`

Lưu tệp **`ThrowingStreamAdapterDemo.java`**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class ThrowingStreamAdapterDemo {

    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T value) throws E;
    }

    static final class ParseFailure extends Exception {
        private static final long serialVersionUID = 1L;

        ParseFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static Integer strictPositive(String text)
            throws ParseFailure {

        final int number;
        try {
            number = Integer.parseInt(text);
        } catch (NumberFormatException cause) {
            throw new ParseFailure("not integer", cause);
        }

        if (number <= 0) {
            throw new ParseFailure("not positive", null);
        }
        return number;
    }

    static <T, R, E extends Exception> Function<T, R> unchecked(
            ThrowingFunction<T, R, E> action) {

        return value -> {
            try {
                return action.apply(value);
            } catch (RuntimeException ex) {
                throw ex;
            } catch (Exception cause) {
                throw new IllegalArgumentException(
                        "conversion rejected", cause);
            }
        };
    }

    static void runCase(String first, String second) {
        ThrowingFunction<String, Integer, ParseFailure> parser =
                ThrowingStreamAdapterDemo::strictPositive;

        Function<String, Integer> normal = unchecked(parser);

        try {
            List<Integer> values =
                    Stream.of(first, second)
                            .map(normal)
                            .toList();

            System.out.println("values=" + values);

        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "failed=" + ex.getMessage());
            System.out.println(
                    "cause=" + ex.getCause().getClass().getSimpleName());
            System.out.println(
                    "detail=" + ex.getCause().getMessage());
        }
    }

    public static void main(String[] args) {
        runCase("2", "3");
        runCase("2", "abc");
        runCase("0", "4");
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ThrowingStreamAdapterDemo.java
java ThrowingStreamAdapterDemo
```

**Stdout chính xác:**

```text
values=[2, 3]
failed=conversion rejected
cause=ParseFailure
detail=not integer
failed=conversion rejected
cause=ParseFailure
detail=not positive
```

### Phân tích đường thành công và thất bại

**`runCase("2","3")`:** lambda dưới dạng `ThrowingFunction` gọi `strictPositive` hai lần, mỗi lần trả `Integer` hợp lệ. Adapter `Function` không ném exception; `Stream.toList()` hoàn tất và danh sách in `[2, 3]`.

**`runCase("2","abc")`:** `Integer.parseInt("abc")` ném unchecked `NumberFormatException`. `strictPositive` bắt lỗi và chuyển thành checked `ParseFailure("not integer", cause)`. Adapter bắt `Exception`, bọc thành unchecked `IllegalArgumentException("conversion rejected", cause)`. Handler ngoài in nguyên nhân trực tiếp là `ParseFailure` với message `not integer`. Nếu điều tra sâu, `ParseFailure.getCause()` vẫn là `NumberFormatException`.

**`runCase("0","4")`:** `strictPositive("0")` parse được số `0` nhưng quy tắc yêu cầu dương, nên ném `ParseFailure("not positive", null)`. Stream dừng do ngoại lệ trước khi xử lý phần còn lại theo đường thành công, adapter bọc và caller nhận cùng kiểu wrapper như trên, nhưng có message nguyên nhân khác.

### Vì sao không thể chỉ viết `Stream.of(...).map(parser)`?

`parser` có kiểu `ThrowingFunction<String,Integer,ParseFailure>`. `Stream.map` cần một `Function`. Hai interface là hai **kiểu Java khác nhau**, và kiểu đích `Function.apply` cũng không cho phép checked `ParseFailure`. Việc chúng có cùng hình dạng tham số/giá trị trả về không biến chúng thành cùng kiểu hoặc cùng hợp đồng lỗi.

Adapter là một **chuyển đổi có chủ đích** giữa hai hợp đồng. Nếu pipeline lớn hoặc error handling phức tạp, có thể tốt hơn khi tách công đoạn parse checked ra ngoài stream hoặc dùng kiểu kết quả có cấu trúc.

## 11. Vì sao không được bắt checked exception “ở ngoài stream” nếu lambda không hợp lệ?

Một lỗi thường gặp là viết:

```java
// Cố ý KHÔNG BIÊN DỊCH.
try {
    java.util.stream.Stream.of("a", "b")
            .map(value -> readFile(value))
            .toList();
} catch (java.io.IOException ex) {
    System.out.println("read failed");
}
```

Ở đây `readFile(String)` được giả định khai báo `throws IOException`. `Stream.map` vẫn đòi `Function.apply` không ném checked `IOException`. **Handler ngoài không biến lambda không phù hợp thành hợp lệ.** Compiler cần kiểm tra riêng body lambda theo functional descriptor trước.

Các cách đúng:

1. **Bắt `IOException` bên trong lambda**, trả fallback hợp lệ hoặc chuyển sang unchecked wrapper.
2. **Dùng custom throwing function và adapter** để chọn rõ chính sách.
3. **Đưa thao tác I/O ra ngoài stream** trong một phương thức vòng lặp có `throws IOException`, nếu muốn giữ lỗi checked nguyên dạng cho caller.
4. **Dùng kiểu kết quả** như một record/sealed hierarchy để biểu diễn success/failure như dữ liệu, nếu pipeline cần xử lý nhiều thất bại mà không ngắt giữa chừng.

Đừng dùng `catch (IOException)` bên ngoài với kỳ vọng compiler sẽ nhìn xuyên qua mọi lambda và tự mở rộng hợp đồng `Function.apply`.

### Một handler ngoài có thể bắt loại lỗi nào sau khi adapter?

Nếu adapter chuyển `IOException` sang `UncheckedIOException`, caller có thể bắt `UncheckedIOException`. Nếu adapter chuyển `ParseFailure` sang `IllegalArgumentException`, caller có thể bắt `IllegalArgumentException`.

Handler ngoài **không tự động bắt `ParseFailure`** chỉ vì nó nằm trong `getCause()` của wrapper. Java chọn `catch` theo **đối tượng ngoại lệ đang được ném**, không tự đi xuyên qua cause.

## 12. Xử lý ngay trong lambda: fallback có ý nghĩa thay vì nuốt lỗi

Một cách làm hợp lệ về cú pháp:

```java
java.util.function.Function<String, Integer> parse = value -> {
    try {
        return Integer.parseInt(value);
    } catch (NumberFormatException ex) {
        return 0;
    }
};
```

`NumberFormatException` là unchecked, và lambda trả `0` khi gặp lỗi. Về mặt Java, không vấn đề checked exception; nhưng về **ngữ nghĩa**, chuỗi `"0"` hợp lệ và chuỗi `"abc"` đều có thể trả `0`. Nếu caller cần phân biệt hai trường hợp, fallback này là **mất thông tin**.

Với checked `IOException` cũng vậy:

```java
java.util.function.Supplier<String> supplier = () -> {
    try {
        return readRequiredConfig();
    } catch (java.io.IOException ex) {
        return "";
    }
};
```

Đây là đoạn minh họa, `readRequiredConfig()` giả định có `throws IOException`. Mã có thể biên dịch, nhưng nếu config bắt buộc và chuỗi rỗng vẫn là dữ liệu hợp lệ, caller không biết lỗi đã xảy ra.

**Chỉ chọn fallback khi hợp đồng thực sự cho phép phục hồi.** Trong ví dụ khác, nếu dữ liệu có thể thiếu mà caller được phép dùng default được kiểm chứng, fallback có thể là chính sách hợp lý.

### Dạng kết quả có cấu trúc

Có thể định nghĩa:

```java
sealed interface ReadResult
        permits ReadResult.Success, ReadResult.Failure {

    record Success(String value) implements ReadResult {}

    record Failure(String code, String message)
            implements ReadResult {}
}
```

Đây là **mã minh họa Java 17**, có thể đặt trong file/class phù hợp. Một `Function<String,ReadResult>` có thể bắt `IOException` nội bộ rồi trả `Failure`, giúp pipeline phân biệt dữ liệu với thất bại mà không ném checked exception ra ngoài `Function.apply`.

Thiết kế này có ích khi cần tổng hợp **nhiều kết quả lỗi** thay vì để stream dừng ở lỗi đầu tiên. Nhưng nó cũng làm kiểu dữ liệu phong phú hơn; không ép mọi thao tác đơn giản phải dùng sealed result.

## 13. Đọc kiểu tĩnh của biến hàm khi gọi lại

Đừng nhầm **nội dung lambda** với **chữ ký phương thức mà caller dùng**.

Giả sử:

```java
@FunctionalInterface
interface ReaderAction {
    String read() throws java.io.IOException;
}

ReaderAction action = () -> "cached";
```

Đây là đoạn minh họa. Phần thân lambda không hề ném checked exception. Nhưng:

```java
String value = action.read(); // Cần bắt/khai báo IOException.
```

Trình biên dịch dùng kiểu tĩnh `ReaderAction`, mà `read()` công bố `throws IOException`. Không có cơ chế compile-time suy ngược từ lời khai báo lambda cụ thể để loại bỏ nghĩa vụ checked exception khi caller dùng interface.

Ngược lại, nếu dùng:

```java
java.util.function.Supplier<String> supplier = () -> "cached";
String value = supplier.get(); // Không đòi IOException.
```

thì phương thức hàm không khai báo checked exception, nên caller không bị bắt/khai báo `IOException` do lời gọi `get()` này.

Điều này tương tự quy tắc override trong Java: compiler áp dụng **hợp đồng của kiểu tĩnh được dùng tại vị trí gọi**, không đoán mọi nhánh implementation thực tế.

## 14. Lambda generic không tự “xóa” hợp đồng exception

Khi dùng:

```java
ThrowingFunction<String, Integer, java.io.IOException> f =
        value -> {
            throw new java.io.IOException("read failed");
        };
```

lambda hợp lệ vì `E` là `IOException`. Caller `f.apply("x")` phải xử lý hoặc khai báo `IOException`.

Nếu chuyển thành:

```java
ThrowingFunction<String, Integer, Exception> f =
        value -> {
            throw new java.io.IOException("read failed");
        };
```

lambda cũng hợp lệ, nhưng caller qua biến kiểu này thấy `throws Exception` rộng hơn. **Kiểu exception generic được chọn có ảnh hưởng đến nghĩa vụ tại điểm gọi.**

### Erasure và generic exception parameter

Tại runtime, thông tin generic của kiểu `E` bị ảnh hưởng bởi *type erasure*. Compiler vẫn dùng `E` để kiểm tra nguồn và caller ở compile time, nhưng không nên viết logic runtime kiểu:

```java
// Cố ý KHÔNG HỢP LỆ: không thể catch một type parameter E.
catch (E ex) {
    // ...
}
```

Java không cho dùng biến kiểu generic `E` làm loại trong `catch` như vậy. Đó là lý do nhiều adapter tổng quát bắt `Exception`, phân biệt `RuntimeException` trước, rồi xử lý checked exception còn lại theo hợp đồng adapter.

### Inference không thay thế thiết kế API

Trong phương thức generic dùng `ThrowingFunction<T,R,E>`, trình biên dịch có thể suy ra `E` từ lambda hoặc method reference trong những hoàn cảnh cụ thể. Tuy nhiên, không nên giả định inference sẽ luôn chọn chính xác các loại checked exception trong một biểu thức phức tạp hoặc cho phép tự động truyền một throwing function sang `Function`.

Ở nơi cần minh bạch, khai báo biến có kiểu rõ:

```java
ThrowingFunction<String, Integer, ParseFailure> parser =
        MyParser::parsePositive;
```

Đây là minh họa, với `MyParser.parsePositive` được định nghĩa tương thích. Kiểu rõ giúp caller và người review thấy ngay loại lỗi checked được phép.

## 15. `throws Exception` của `Callable` không có nghĩa mọi tác vụ đều chạy bất đồng bộ

`Callable<V>` là functional interface từ `java.util.concurrent`. Nó cho phép `call() throws Exception`, nhưng **bản thân interface không yêu cầu một thread mới**.

Nếu viết:

```java
java.util.concurrent.Callable<String> task =
        () -> readRequiredConfig();

String result = task.call();
```

đây là minh họa, `readRequiredConfig` là phương thức checked `IOException` giả định. Gọi `task.call()` trực tiếp chạy đồng bộ trên thread hiện tại; caller phải xử lý/khai báo `Exception` theo kiểu `Callable`.

Nếu submit cho `ExecutorService`:

```java
java.util.concurrent.Future<String> future =
        executor.submit(task);

try {
    String result = future.get();
} catch (java.lang.InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable original = ex.getCause();
    // Xử lý/log theo chính sách thực tế.
}
```

Đây là **đoạn minh họa**, biến `executor` và `task` phải được khai báo hợp lệ ở phạm vi tương ứng.

- `submit` đưa tác vụ tới executor.
- `Future.get()` có thể ném checked `InterruptedException` hoặc `ExecutionException`; nó không tự ném trực tiếp mọi `IOException` mà body `Callable` đã ném.
- Khi tác vụ thất bại, `ExecutionException.getCause()` thường trỏ tới ngoại lệ gốc của tác vụ.
- Việc interrupt cần được xử lý theo chính sách; ví dụ khôi phục flag khi không tiếp tục ném `InterruptedException`.

Do đó, có **hai hợp đồng** cần phân biệt: `Callable.call() throws Exception` ở tác vụ, và `Future.get()` khi caller lấy kết quả từ executor.

## 16. `CompletableFuture` và các API async cũng có ranh giới riêng

`CompletableFuture.supplyAsync` nhận `Supplier<U>`, mà `Supplier.get()` **không cho checked exception thoát ra**. Vì thế:

```java
// Cố ý KHÔNG BIÊN DỊCH nếu readRequiredConfig() throws IOException.
java.util.concurrent.CompletableFuture<String> result =
        java.util.concurrent.CompletableFuture.supplyAsync(
                () -> readRequiredConfig());
```

Cần bắt hoặc chuyển lỗi trong lambda:

```java
java.util.concurrent.CompletableFuture<String> result =
        java.util.concurrent.CompletableFuture.supplyAsync(() -> {
            try {
                return readRequiredConfig();
            } catch (java.io.IOException cause) {
                throw new java.io.UncheckedIOException(
                        "config read failed", cause);
            }
        });
```

Đây là khung minh họa. Khi lấy kết quả:

- `result.join()` có thể báo thất bại bằng một `CompletionException` unchecked, với cause liên quan.
- `result.get()` sử dụng hợp đồng `Future` với checked `InterruptedException`/`ExecutionException`.
- Cần phân biệt lỗi wrapper của hạ tầng async và exception nguyên nhân thực tế ở `getCause()`.

Chỉ việc viết `throws IOException` trên phương thức tạo `CompletableFuture` không khiến `Supplier.get()` cho phép checked `IOException`.

### Không suy diễn rằng executor “bắt giúp mọi lỗi”

Framework có thể giữ exception của tác vụ để truy vấn qua `Future`. Việc caller không thấy exception ném ngay tại lệnh `submit` không có nghĩa công việc thành công. Hãy quan sát trạng thái và kết quả bất đồng bộ tại đúng ranh giới.

## 17. Checked exception và `throws` khi functional interface kế thừa nhiều nguồn

Một functional interface có thể có các phương thức abstract tương đương nhau qua quan hệ kế thừa interface. Java xác định function type theo các quy tắc về chữ ký, return type và tập checked exception được phép.

Ví dụ đơn giản:

```java
interface ActionA {
    void run() throws java.io.IOException;
}

interface ActionB {
    void run() throws java.sql.SQLException;
}

@FunctionalInterface
interface CombinedAction extends ActionA, ActionB {
}
```

Đây là **khung minh họa hợp lệ** khi hai phương thức cùng signature có thể được hợp nhất làm một functional method. Nhưng lambda triển khai `CombinedAction` **không được tùy tiện ném `IOException` hoặc `SQLException`** chỉ vì mỗi interface cha cho phép một loại. Để thỏa **cả hai hợp đồng**, tập checked exception mà function type cho phép có thể bị thu hẹp đáng kể; với hai nhánh độc lập như ví dụ, lambda không thể để một trong hai checked exception ấy thoát ra theo cách trái với hợp đồng còn lại.

Một lambda không ném checked exception nào là trường hợp đơn giản:

```java
CombinedAction action = () ->
        System.out.println("combined action");
```

Một lưu ý tinh tế là **kiểu hàm được suy ra** có thể chặt hơn một khai báo cụ thể trong interface cha. Khi bài toán có nhiều interface kết hợp hoặc generics phức tạp, hãy kiểm tra đặc tả kiểu đích bằng compiler thay vì suy đoán rằng danh sách `throws` được cộng dồn.

## 18. Adapter và chính sách giữ nguyên nguyên nhân

Khi chuyển checked exception sang unchecked để thỏa `Function`, lựa chọn wrapper cần được cân nhắc:

| Ngoại lệ checked ban đầu | Một cách chuyển đổi có thể phù hợp | Điều kiện cần chú ý |
| --- | --- | --- |
| `IOException` | `UncheckedIOException(message, cause)` | `cause` phải là `IOException` |
| Checked exception nghiệp vụ | Custom `RuntimeException(message, cause)` | Bảo toàn mã và ý nghĩa nghiệp vụ |
| `SQLException` | Một wrapper phù hợp tầng repository/service | Không tự đưa SQL chi tiết ra client |
| `ParseException` | Một exception validation phù hợp | Không biến mọi lỗi parse thành lỗi hệ thống |
| Đã có một `RuntimeException` | Thường ném lại nếu không cần đổi ngữ cảnh | Không bọc lại vô nghĩa |

**Không dùng `throw new RuntimeException(ex.getMessage())`** nếu bạn muốn giữ loại và stack trace nguyên nhân. Constructor này chỉ nhận chuỗi, không giữ `cause`. Chọn `new RuntimeException("context", ex)` hoặc một subtype chuyên biệt khi cần chuyển lỗi.

Ví dụ:

```java
try {
    return checkedOperation();
} catch (SomeCheckedException cause) {
    throw new DomainOperationException(
            "Cannot complete operation", cause);
}
```

Đây là đoạn minh họa với các kiểu/hàm do ứng dụng định nghĩa. Điều quan trọng là **truyền đối tượng `cause`**, không chỉ message, và chỉ chuyển loại exception tại ranh giới thực sự có ý nghĩa.

### Không dùng “sneaky throw” để né compiler một cách mù quáng

Một số thư viện dùng generic trick hoặc helper đặc biệt để ném checked exception qua API không khai báo `throws`. Dù runtime có thể cho phép ngoại lệ được ném, kỹ thuật này **làm mờ hợp đồng ở compile time**, khiến caller của `Function` không được hướng dẫn bắt loại checked exception thực tế.

Nếu mục đích giáo dục hoặc yêu cầu API là tôn trọng checked exception, hãy ưu tiên **throwing functional interface có khai báo `throws`**, `try-catch` rõ ràng, hoặc **wrapper có cause**. Tránh dùng kỹ thuật né kiểm tra để thay thế thiết kế.

## 19. Trường hợp `finally` và resource trong lambda

Một lambda có thể tự chứa `try-with-resources`:

```java
java.util.concurrent.Callable<String> loader = () -> {
    try (var reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
};
```

Đây là đoạn minh họa với biến `path` hợp lệ kiểu `Path`. Vì `Callable.call() throws Exception`, lambda được phép để checked `IOException` từ mở, đọc hoặc đóng tài nguyên thoát ra. Resource vẫn được đóng trước khi `call` thực sự trả, kể cả khi body `return` sớm hoặc ném lỗi.

Nếu thay `Callable<String>` bằng `Supplier<String>` cho cùng body thì không hợp lệ trừ khi đã xử lý hoặc chuyển checked `IOException`. **`try-with-resources` không tự xóa checked exception** phát sinh trong lúc mở, đọc hoặc đóng.

Đồng thời:

- Nếu thân `try` ném checked exception E1, còn `close()` ném E2, cơ chế `try-with-resources` thường giữ E1 làm lỗi chính và gắn E2 dưới dạng suppressed.
- Nếu thân `try` định trả giá trị nhưng `close()` ném checked `IOException`, đường trả có thể bị thay bằng exception mà hợp đồng functional interface đích phải cho phép hoặc handler phải xử lý.
- Không nên trả một stream/lazy iterator phụ thuộc resource đã đóng từ lambda và giả định caller có thể sử dụng bình thường.

## 20. Lỗi biên dịch và lỗi thiết kế thường gặp

| Hiểu lầm hoặc lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Lambda không bao giờ ném được checked exception” | Tùy `throws` của functional descriptor | Dùng interface có checked `throws` |
| “Lambda tự khai báo `throws IOException` sau `->`” | Cú pháp Java không hỗ trợ | Đặt `throws` ở functional method |
| Gán lambda gọi `Files.readString` trực tiếp vào `Supplier` | `Supplier.get` không khai báo `IOException` | Catch/wrap hoặc dùng custom interface |
| Ghi `throws IOException` trên phương thức tạo `Supplier` | Không sửa được hợp đồng `Supplier.get` | Xử lý lỗi trong lambda hoặc đổi target type |
| Bao `Stream.map` trong `catch(IOException)` rồi mong lambda được phép ném | Vi phạm checked exception ngay trong `Function.apply` | Đổi cách biểu diễn hoặc adapter |
| Dùng `Callable` nhưng caller chỉ bắt `IOException` khi gọi `call()` | `Callable.call` khai báo `throws Exception` | Bắt/khai báo `Exception` hoặc dùng interface hẹp |
| Nghĩ method reference bỏ qua checked `throws` | Cũng phải thỏa target functional descriptor | Dùng kiểu đích/adapter phù hợp |
| Tạo adapter bắt mọi `Exception` rồi luôn bọc | Có thể bọc cả `RuntimeException` không cần thiết | Giữ unchecked nguyên trạng, bọc lỗi checked có chủ đích |
| Bọc bằng message nhưng không truyền `cause` | Mất liên kết lỗi gốc | Truyền `Throwable cause` |
| Dùng `UncheckedIOException` cho mọi checked exception | Constructor/cơ chế dành cho `IOException` | Dùng wrapper phù hợp loại gốc |
| Dùng `catch (Throwable)` trong lambda và nuốt lỗi | Có thể giấu `Error` nghiêm trọng | Bắt những lỗi ứng dụng có thể xử lý |
| Chỉ in stack trace rồi trả giá trị giả | Caller tưởng thao tác thành công | Dùng recovery thật hoặc kết quả thất bại rõ |
| Đồng nhất việc tạo `Callable` với thực thi async | `Callable` chỉ là interface | Phân biệt `call()` trực tiếp và `submit()` |
| Nghĩ `Future.get()` ném trực tiếp mọi exception trong `call()` | `get()` thường dùng `ExecutionException` | Kiểm tra `getCause()` |
| Nghĩ stream có `map` sẽ xử lý mọi phần tử trước khi ném | Exception có thể dừng pipeline | Cân nhắc result type để tổng hợp lỗi |

## 21. Checklist thiết kế lambda có checked exception

Trước khi viết một lambda gọi phương thức `throws`:

1. **Xác định kiểu đích:** là `Runnable`, `Supplier`, `Function`, `Callable` hay interface custom?
2. **Đọc function descriptor:** kiểu tham số, kiểu trả về và danh sách checked `throws` thực sự là gì?
3. **Xác định nguồn checked exception:** lời gọi nào có thể ném `IOException`, `SQLException` hoặc custom checked exception?
4. **Đối chiếu với `throws` của descriptor:** các loại checked thoát khỏi body đã được cho phép chưa?
5. **Nếu không được cho phép**, có chính sách xử lý trong lambda không? Không chỉ nuốt lỗi hoặc trả fallback sai.
6. **Nếu caller cần xử lý checked trực tiếp**, có nên định nghĩa custom functional interface rõ loại `throws` không?
7. **Nếu API cố định dùng `Function`/`Supplier`**, adapter nào diễn đạt ý định chuyển checked sang unchecked tốt nhất?
8. **Nếu wrapper được tạo**, đã giữ `cause` và không vô tình bọc cả các lỗi unchecked cần giữ nguyên chưa?
9. **Nếu dùng generics**, `E` có đủ cụ thể chưa, hay đang vô tình mở thành `Exception` quá rộng?
10. **Nếu dùng method reference**, phương thức nguồn và kiểu đích có tương thích cả tham số, return type và checked `throws` không?
11. **Nếu chạy stream**, có hiểu rằng lỗi sẽ ngắt pipeline, không tự tổng hợp tất cả lỗi không?
12. **Nếu chạy async**, caller quan sát lỗi qua `Future.get()`/`join()` thế nào?
13. **Nếu lambda quản lý resource**, có xét checked exception từ cả khởi tạo, thân `try` và `close()` không?
14. **Đã biên dịch các đường thành công/thất bại chưa?** Kiểm tra cả lỗi compile-time do descriptor và cách lan truyền cause runtime.

## 22. Bài tập tự kiểm tra

**Bài A — Runnable hay Callable?**

```java
Runnable a = () -> {
    throw new java.io.IOException("failed");
};
```

Có biên dịch không?

**Không.** `Runnable.run()` không khai báo checked `IOException`. Với `Callable<Void>`, lambda có thể ném `IOException` nếu các ràng buộc tham số/return phù hợp.

**Bài B — cùng lambda dưới kiểu khác:**

```java
java.util.concurrent.Callable<String> c =
        () -> load("item");

java.util.function.Supplier<String> s =
        () -> load("item");
```

Nếu `load(String) throws IOException`, câu nào hợp lệ?

**`Callable` hợp lệ**, còn `Supplier` không hợp lệ nếu `IOException` chưa được xử lý trong lambda.

**Bài C — thêm throws ở phương thức chứa lambda:**

Có thể chỉ thêm `throws IOException` cho method `createSupplier()` để lambda `() -> load()` được gán vào `Supplier` không?

**Không.** Kiểm tra phần thân lambda vẫn dựa vào `Supplier.get()`, không phải `throws` của `createSupplier()`.

**Bài D — method reference:**

`ReadAction` có `read() throws IOException`. Một method reference tới phương thức `readFile() throws IOException` có thể triển khai interface ấy không?

**Có**, nếu kiểu tham số và kết quả cũng tương thích. Nhưng nó không mặc nhiên triển khai `Supplier` không có checked `throws`.

**Bài E — generic exception:**

`ThrowingFunction<String,Integer,ParseFailure>` có giúp caller bắt riêng `ParseFailure` không?

**Có.** Kiểu `E=ParseFailure` được dùng ở compile time cho phương thức hàm `apply`.

**Bài F — adapter có làm checked exception biến mất ở runtime không?**

**Không.** Adapter có thể bọc lỗi checked thành unchecked wrapper; caller có thể xem lỗi gốc qua `getCause()` nếu adapter giữ nguyên nhân.

**Bài G — Future:**

`Callable.call()` ném `IOException` khi chạy trong executor. `future.get()` có nhất thiết ném trực tiếp `IOException` không?

**Không.** Khi tác vụ thất bại, `get()` thường ném `ExecutionException` và `getCause()` trỏ tới lỗi gốc.

**Bài H — catch bên ngoài stream:**

`try { stream.map(v -> readFile(v)).toList(); } catch (IOException ex) { ... }` có khiến body `Function.apply` được phép ném `IOException` không?

**Không.** Lambda phải phù hợp descriptor của `Function` trước; handler ngoài không sửa được lỗi compile-time đó.

**Bài I — fallback:**

`Supplier` bắt `IOException` rồi trả chuỗi rỗng. Có luôn là xử lý đúng không?

**Không.** Chỉ đúng nếu chuỗi rỗng là fallback hợp đồng cho phép. Nếu không, nó che thất bại và có thể làm caller hiểu sai.

**Bài J — unchecked wrapper:**

Tại sao nên dùng `new UncheckedIOException("context", cause)` hơn `new RuntimeException(cause.getMessage())` cho lỗi `IOException`?

Vì `UncheckedIOException` thể hiện đúng loại nguồn I/O và **giữ đối tượng cause**, còn chỉ copy message làm mất thông tin stack, cause chain và suppressed của lỗi ban đầu.

## Kết luận

**Checked exception trong lambda được quyết định bởi hợp đồng của kiểu hàm đích, không bởi một danh sách `throws` viết trên lambda.** Với `Runnable`, `Supplier`, `Function` và các functional interface chuẩn không có checked `throws`, phần thân phải xử lý hoặc chuyển đổi lỗi checked. `Callable.call() throws Exception` và các functional interface tự định nghĩa có `throws IOException` hay `throws E` có thể cho phép chuyển lỗi checked lên caller.

Hãy phân biệt **kiểu đích tại compile time**, **ngoại lệ thực tế tại runtime**, và **cách hệ thống gọi lambda** (trực tiếp, stream, executor hay `CompletableFuture`). Khi cần adapter, giữ `cause` và diễn đạt chính sách lỗi rõ ràng. Khi cần caller xử lý checked exception theo kiểu hẹp, dùng một **functional interface có `throws` đúng hợp đồng** thay vì giấu lỗi, phân tích message hoặc tìm cách né kiểm tra của compiler.