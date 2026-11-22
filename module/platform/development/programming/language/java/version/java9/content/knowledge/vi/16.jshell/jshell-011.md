# Nhúng JShell API, đọc SnippetEvent và diagnostics

JShell không chỉ là chương trình REPL chạy trong terminal. Từ Java 9, JDK cung cấp API trong module `jdk.jshell` để một ứng dụng Java có thể tạo phiên JShell, gửi mã nguồn vào đánh giá và nhận lại kết quả, trạng thái snippet, ngoại lệ cùng chẩn đoán biên dịch. Cách nhúng này hữu ích khi xây dựng công cụ học Java, console tương tác, trình thử API hoặc tính năng chạy thử mã trong IDE.

API này thuộc JDK module `jdk.jshell`, không phải module nền tảng `java.base`. Môi trường chạy phải có module đó; một runtime tùy biến được tạo bằng `jlink` cần đưa `jdk.jshell` vào nếu ứng dụng sử dụng API.

## 1. Chuẩn bị module và chương trình

Với dự án dùng classpath, biên dịch và chạy bằng JDK có JShell:

```bash
javac --add-modules jdk.jshell JshellApiDemo.java
java --add-modules jdk.jshell JshellApiDemo
```

Với dự án modular, khai báo phụ thuộc trong `module-info.java`:

```java
module demo {
    requires jdk.jshell;
}
```

Nếu compiler báo không tìm thấy `jdk.jshell`, hãy kiểm tra đang dùng JDK thay vì một runtime rút gọn và module có được resolve hay chưa.

Các kiểu chính cần biết:

- `JShell`: quản lý một phiên đánh giá mã và trạng thái của các snippet.
- `Snippet`: đại diện cho một đơn vị mã đã gửi vào phiên, chẳng hạn khai báo biến, phương thức, lớp hoặc biểu thức.
- `SnippetEvent`: thông báo về kết quả hoặc thay đổi trạng thái của một snippet.
- `Diag`: mô tả một cảnh báo hoặc lỗi do quá trình phân tích/biên dịch phát hiện.

## 2. Tạo và quản lý một phiên JShell

Cách ngắn nhất để tạo phiên là `JShell.create()`. Mỗi đối tượng JShell giữ trạng thái riêng: biến, import, phương thức và kiểu đã khai báo trong phiên đó.

```java
import jdk.jshell.JShell;

public class SimpleSession {
    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            shell.eval("int price = 120;");
            shell.eval("price * 2").forEach(event ->
                    System.out.println(event.value()));
        }
    }
}
```

Kết quả:

```text
240
```

`JShell` triển khai `AutoCloseable`, vì vậy nên dùng try-with-resources để đóng phiên và giải phóng tài nguyên thực thi khi hoàn tất.

Khi cần điều khiển các luồng vào/ra của snippet, có thể tạo phiên bằng builder:

```java
JShell shell = JShell.builder()
        .in(inputStream)
        .out(outputStream)
        .err(errorStream)
        .build();
```

Các luồng này hữu ích khi tích hợp JShell vào giao diện ứng dụng thay vì để mã được đánh giá ghi trực tiếp vào các luồng mặc định. Builder cũng cung cấp các tùy chọn cấu hình compiler và execution engine; chỉ cấu hình chúng khi ứng dụng có yêu cầu cụ thể.

Nếu snippet cần dùng thư viện bên ngoài, thêm JAR vào classpath của phiên bằng `shell.addToClasspath(path)` trước khi đánh giá mã sử dụng thư viện đó. Đường dẫn phải trỏ tới thư viện có thể đọc được trong môi trường thực thi JShell.

## 3. Đánh giá mã và nhận SnippetEvent

Phương thức trung tâm là:

```java
List<SnippetEvent> events = shell.eval("int total = 10;");
```

`eval(String)` nhận mã nguồn của snippet và trả về một danh sách `SnippetEvent`. Danh sách có thể chứa nhiều sự kiện: ngoài snippet vừa gửi, JShell còn có thể thông báo những snippet liên quan bị thay đổi trạng thái do định nghĩa mới.

Vì vậy, hãy duyệt toàn bộ danh sách thay vì giả định lần gọi nào cũng chỉ có một event:

```java
for (SnippetEvent event : shell.eval("total * 2")) {
    System.out.println(event.value());
}
```

Các thuộc tính quan trọng của `SnippetEvent`:

| Thành phần | Ý nghĩa |
|---|---|
| `snippet()` | Snippet được tạo hoặc bị ảnh hưởng; có thể đọc `id()`, `source()`, `kind()`, `subKind()`. |
| `previousStatus()` | Trạng thái của snippet trước sự kiện. |
| `status()` | Trạng thái mới sau khi xử lý. |
| `value()` | Giá trị kết quả nếu lần đánh giá tạo ra giá trị; có thể là `null`. |
| `exception()` | Ngoại lệ phát sinh trong quá trình thực thi, nếu có. |
| `causeSnippet()` | Snippet gây ra thay đổi trạng thái của snippet này; thường là `null` với event trực tiếp. |
| `isSignatureChange()` | Cho biết chữ ký của snippet có thay đổi hay không. |

### Các trạng thái cần nhận biết

Trạng thái được biểu diễn bởi `Snippet.Status`, không phải một cờ boolean duy nhất:

- `VALID`: snippet hợp lệ.
- `RECOVERABLE_DEFINED` và `RECOVERABLE_NOT_DEFINED`: các trạng thái có thể phục hồi khi những phụ thuộc chưa được giải quyết được bổ sung.
- `REJECTED`: snippet bị từ chối, thường do lỗi biên dịch.
- `OVERWRITTEN`: định nghĩa cũ bị thay thế bởi một định nghĩa mới.
- `DROPPED`: snippet đã bị loại khỏi phiên.
- `NONEXISTENT`: snippet chưa tồn tại trong phiên.

Khi cần phân loại tổng quát, `Snippet.Status` còn có `isActive()` và `isDefined()`. Hai phương thức này hữu ích hơn việc tự suy luận trạng thái từ chuỗi hiển thị.

## 4. Đọc diagnostics từ một snippet

`SnippetEvent.status()` cho biết trạng thái tổng thể. Để biết vì sao compiler từ chối một snippet, dùng:

```java
shell.diagnostics(event.snippet())
```

Phương thức trả về `Stream<Diag>`. Mỗi `Diag` cung cấp thông tin về một lỗi hoặc cảnh báo:

- `isError()`: phân biệt lỗi với cảnh báo.
- `getCode()`: mã định danh của chẩn đoán từ compiler.
- `getMessage(Locale.ROOT)`: nội dung thông báo theo locale được chọn.
- `getStartPosition()`, `getEndPosition()` và `getPosition()`: vị trí chẩn đoán trong nguồn snippet.
- `Diag.NOPOS`: giá trị cho biết vị trí không có sẵn.

Ví dụ:

```java
shell.diagnostics(event.snippet()).forEach(diag -> {
    String severity = diag.isError() ? "ERROR" : "WARNING";
    System.out.println(severity + ": "
            + diag.getMessage(Locale.ROOT));
    System.out.println("code=" + diag.getCode());
    System.out.println("range="
            + diag.getStartPosition() + ".."
            + diag.getEndPosition());
});
```

Không nên dùng nội dung thông báo hoặc mã compiler làm khóa nghiệp vụ cố định. Câu chữ có thể thay đổi theo phiên bản JDK và locale; hãy dựa vào trạng thái, `isError()` và vị trí để xây dựng phản hồi cho người dùng.

## 5. Phân biệt lỗi biên dịch và ngoại lệ lúc chạy

Hai trường hợp này đi qua hai nhánh thông tin khác nhau:

**Lỗi biên dịch:** ví dụ dùng một biến chưa được khai báo. Snippet thường có trạng thái `REJECTED`; `shell.diagnostics(snippet)` cung cấp lỗi và vị trí tương ứng.

**Ngoại lệ lúc chạy:** ví dụ phép chia cho 0. Mã vẫn biên dịch được, vì vậy snippet có thể ở trạng thái `VALID`, nhưng `event.exception()` chứa ngoại lệ phát sinh khi thực thi. Với `EvalException`, có thể lấy tên lớp ngoại lệ gốc bằng `getExceptionClassName()`.

Ngoài ra, `UnresolvedReferenceException` biểu diễn trường hợp một khai báo phụ thuộc vào tham chiếu chưa được giải quyết; `getSnippet()` cho biết khai báo liên quan. Đừng kết luận rằng diagnostics rỗng có nghĩa là snippet chắc chắn chạy thành công: hãy kiểm tra cả `exception()`.

## 6. Ví dụ hoàn chỉnh: đánh giá snippet, đọc event và diagnostics

Tạo tệp `JshellApiDemo.java`:

```java
import java.util.Locale;
import jdk.jshell.Diag;
import jdk.jshell.EvalException;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;

public class JshellApiDemo {
    private static void evaluate(JShell shell, String source) {
        System.out.println(">>> " + source);

        for (SnippetEvent event : shell.eval(source)) {
            Snippet snippet = event.snippet();

            System.out.printf(
                    "id=%s kind=%s previous=%s status=%s%n",
                    snippet.id(),
                    snippet.kind(),
                    event.previousStatus(),
                    event.status());

            if (event.value() != null) {
                System.out.println("value=" + event.value());
            }

            if (event.causeSnippet() != null) {
                System.out.println(
                        "cause=" + event.causeSnippet().source());
            }

            if (event.exception() != null) {
                System.out.println(
                        "exception="
                                + event.exception().getClass()
                                        .getSimpleName());

                if (event.exception() instanceof EvalException evalException) {
                    System.out.println(
                            "exceptionType="
                                    + evalException.getExceptionClassName());
                }
            }

            shell.diagnostics(snippet).forEach(diag -> {
                String severity = diag.isError() ? "ERROR" : "WARNING";
                String position = diag.getStartPosition() == Diag.NOPOS
                        ? "position unavailable"
                        : diag.getStartPosition()
                                + ".." + diag.getEndPosition();

                System.out.printf(
                        "diagnostic %s [%s] %s: %s%n",
                        severity,
                        diag.getCode(),
                        position,
                        diag.getMessage(Locale.ROOT));
            });
        }
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            evaluate(shell, "int count = 3;");
            evaluate(shell, "count * 2");
            evaluate(shell, "int invalid = missingName + 1;");
            evaluate(shell, "int crash = 10 / 0;");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --add-modules jdk.jshell JshellApiDemo.java
java --add-modules jdk.jshell JshellApiDemo
```

Một phần kết quả trên JDK 24.0.2:

```text
>>> int count = 3;
id=1 kind=VAR previous=NONEXISTENT status=VALID
value=3
>>> count * 2
id=2 kind=VAR previous=NONEXISTENT status=VALID
value=6
>>> int invalid = missingName + 1;
id=3 kind=VAR previous=NONEXISTENT status=REJECTED
diagnostic ERROR [...] 14..25: cannot find symbol
>>> int crash = 10 / 0;
id=4 kind=VAR previous=NONEXISTENT status=VALID
exception=EvalException
exceptionType=java.lang.ArithmeticException
```

Thông báo compiler đầy đủ có thể khác giữa các phiên bản JDK. Điểm cần chú ý là lỗi tên biến chưa tồn tại tạo diagnostics và trạng thái `REJECTED`, trong khi phép chia cho 0 vẫn qua bước biên dịch nhưng tạo `EvalException` khi chạy.

## 7. Sự kiện của snippet phụ thuộc

Một lần đánh giá có thể làm thay đổi trạng thái của snippet đã tồn tại. Ví dụ, định nghĩa lại biến mà một phương thức đang tham chiếu:

```java
try (JShell shell = JShell.create()) {
    shell.eval("int base = 1;");
    shell.eval("int twice() { return base * 2; }");

    for (SnippetEvent event : shell.eval("int base = 4;")) {
        String cause = event.causeSnippet() == null
                ? "-"
                : event.causeSnippet().source();

        System.out.printf(
                "snippet=%s | %s -> %s | cause=%s%n",
                event.snippet().source(),
                event.previousStatus(),
                event.status(),
                cause);
    }
}
```

Danh sách event có thể chứa snippet mới vừa nhập và snippet cũ bị thay thế. Với event phát sinh do tác động phụ thuộc, `causeSnippet()` giúp xác định snippet nào gây ra thay đổi. Đây là lý do ứng dụng tích hợp nên xử lý mọi event và không chỉ đọc phần tử đầu tiên.

## 8. Quy trình xử lý trong ứng dụng

Một luồng tích hợp thường có các bước:

1. Tạo một `JShell` cho phiên tương tác và cấu hình các luồng vào/ra nếu giao diện cần thu kết quả riêng.
2. Gửi một snippet qua `eval(source)`.
3. Duyệt tất cả `SnippetEvent` trả về; ghi nhận snippet, trạng thái trước/sau, giá trị và snippet gây thay đổi nếu có.
4. Đọc `diagnostics(snippet)` để hiển thị lỗi hoặc cảnh báo biên dịch.
5. Kiểm tra `exception()` để xử lý ngoại lệ lúc chạy.
6. Đóng phiên bằng `close()` khi người dùng kết thúc.

Nếu cần hiển thị trạng thái phiên, JShell còn cung cấp các stream như `snippets()`, `variables()`, `methods()`, `types()` và `imports()`. Chúng cho phép ứng dụng lấy danh sách snippet theo loại mà không cần tự phân tích lại toàn bộ lịch sử nguồn.

## 9. Lưu ý khi triển khai

- **Không coi JShell là sandbox bảo mật.** Mã được đánh giá có thể thực hiện thao tác với quyền của môi trường chạy. Không đưa mã không đáng tin cậy vào cùng tiến trình có quyền truy cập bí mật hoặc tài nguyên quan trọng; nếu cần chạy mã người dùng, phải cô lập bằng cơ chế hệ điều hành hoặc container và giới hạn tài nguyên.
- **Không bỏ qua các event phụ thuộc.** Việc định nghĩa lại một biến, phương thức hoặc kiểu có thể ảnh hưởng đến snippet khác trong cùng phiên.
- **Không nhầm diagnostics với exception.** Diagnostics mô tả vấn đề phân tích/biên dịch; exception phản ánh lỗi trong lúc thực thi.
- **Không giữ JShell mãi sau khi phiên kết thúc.** Đóng phiên để giải phóng tài nguyên và tránh vô tình dùng lại trạng thái cũ.
- **Kiểm tra module ở môi trường triển khai.** Một runtime tùy biến có thể không chứa `jdk.jshell`, dù ứng dụng biên dịch thành công trên JDK đầy đủ.
- **Không phụ thuộc vào câu chữ lỗi.** Dùng trạng thái, loại lỗi, mã chẩn đoán và vị trí để xây dựng logic; nội dung thông báo nên được hiển thị như thông tin hỗ trợ người dùng.

JShell API biến bộ đánh giá snippet thành một thành phần có thể tích hợp vào ứng dụng Java. Khi đọc đồng thời `SnippetEvent`, `Diag` và `exception()`, chương trình có thể phân biệt mã hợp lệ, lỗi compiler, lỗi lúc chạy và những thay đổi lan truyền tới snippet phụ thuộc.
