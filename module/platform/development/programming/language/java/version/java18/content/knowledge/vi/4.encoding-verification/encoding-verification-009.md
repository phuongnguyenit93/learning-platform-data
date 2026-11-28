# Chạy tiến trình JVM riêng để so sánh cấu hình charset khởi động một cách độc lập

## 1. Vì sao phải so sánh trong các JVM riêng?

Trong module **JAVA_VERSION_JAVA18**, [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400) đưa UTF-8 thành charset mặc định của nhiều API Java từ JDK 18. Một chương trình có thể cần xác minh hành vi khi JVM khởi động theo cấu hình mặc định, khi yêu cầu tương thích với charset native, và khi chỉ định UTF-8 rõ ràng.

Charset mặc định được thiết lập trong quá trình khởi động JVM. Thay đổi `System.setProperty("file.encoding", ...)` sau khi chương trình đã chạy không phải cách được hỗ trợ để khởi tạo lại `Charset.defaultCharset()` hay cấu hình lại các API đã tạo. Muốn so sánh các cấu hình khởi động, hãy chạy **mỗi cấu hình trong một tiến trình JVM mới**.

Bài thuộc chương **Kiểm chứng mã hóa**. Ta sẽ dùng `ProcessBuilder` để chạy nhiều tiến trình con từ cùng một chương trình:

- JVM mặc định của JDK 18+: không truyền `file.encoding`, để kiểm tra giá trị mặc định UTF-8.
- JVM có `-Dfile.encoding=UTF-8`: chỉ định rõ UTF-8 ngay khi khởi động.
- JVM có `-Dfile.encoding=COMPAT`: yêu cầu charset mặc định tương thích với charset native của môi trường chạy.

Mỗi tiến trình sẽ tự in `file.encoding`, `native.encoding`, `Charset.defaultCharset()` và kết quả đọc/ghi mẫu. Chương trình cha thu stdout dưới dạng byte và giải mã phần báo cáo ASCII bằng charset tường minh, để chính phép thử không phụ thuộc vào cách terminal hiển thị tiếng Việt.

## 2. Điều gì được thiết lập khi JVM khởi động?

Trên JDK 18+:

- Nếu không chỉ định chế độ khác, charset mặc định là `UTF-8`.
- `-Dfile.encoding=COMPAT` yêu cầu JDK dùng hành vi charset mặc định tương thích với charset native của nền tảng.
- `-Dfile.encoding=UTF-8` chỉ định rõ UTF-8.
- `native.encoding` cung cấp tên charset native mà runtime nhận diện. Đây là thông tin môi trường; nó không mô tả charset của từng file hoặc giao thức.
- Với mục đích cấu hình của JEP 400, `UTF-8` và `COMPAT` là hai giá trị được hỗ trợ. Đặt tên charset tùy ý như `-Dfile.encoding=windows-1252` không phải cách cấu hình được hỗ trợ trên JDK 18+.

Giá trị thực tế của `COMPAT` phụ thuộc nền tảng và cấu hình môi trường. Trên máy có charset native UTF-8, chế độ `COMPAT` có thể cho kết quả giống chế độ mặc định UTF-8. Phép thử phải in `native.encoding` và `Charset.defaultCharset()` để giải thích kết quả thay vì giả định hai chế độ luôn khác nhau.

### 2.1. Vì sao không thể đổi default charset giữa chương trình?

Ví dụ sau không phải phép thử hợp lệ:

```java
System.setProperty("file.encoding", "COMPAT");

// Không được bảo đảm sẽ làm Charset.defaultCharset() đổi theo.
System.out.println(Charset.defaultCharset());
```

Các API và runtime có thể đã khởi tạo hoặc lưu charset mặc định trước khi thuộc tính bị thay đổi. Nếu cần kiểm tra `UTF-8` và `COMPAT`, hãy khởi chạy hai JVM độc lập với tùy chọn tương ứng.

### 2.2. System property của tiến trình cha không tự truyền sang tiến trình con

`ProcessBuilder` kế thừa môi trường của tiến trình cha, nhưng không tự sao chép toàn bộ system properties của JVM cha sang JVM con. Muốn đặt `file.encoding` cho tiến trình con, truyền tùy chọn `-Dfile.encoding=...` trong danh sách lệnh, trước tên lớp chính.

Các biến môi trường `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS` có thể bổ sung tùy chọn cho JVM mới. Để phép thử có thể lặp lại, ví dụ dưới đây loại bỏ hai biến đó khỏi **môi trường bản sao của tiến trình con**. Môi trường của tiến trình cha không bị sửa đổi.

## 3. Thiết kế phép thử: cùng mã nguồn, ba lần khởi động

Ta sẽ tạo một lớp duy nhất có hai chế độ:

- Chạy bình thường: đóng vai trò tiến trình cha, khởi chạy ba JVM con.
- Chạy với tham số `--probe`: đóng vai trò tiến trình con, đọc charset mặc định của chính nó và in kết quả.

Cả ba JVM con dùng cùng executable trong `java.home`, cùng classpath và cùng lớp chính. Điểm khác nhau duy nhất trong lệnh khởi chạy là tùy chọn `file.encoding`.

```text
Tiến trình cha
    |
    +-- java CharsetForkLab --probe
    |       Không truyền file.encoding
    |       -> JDK mặc định
    |
    +-- java -Dfile.encoding=UTF-8 CharsetForkLab --probe
    |       -> UTF-8 tường minh
    |
    +-- java -Dfile.encoding=COMPAT CharsetForkLab --probe
            -> charset native tương thích
```

Để tránh nhầm kết quả do terminal, tiến trình con chỉ gửi báo cáo ASCII: tên charset, code point dạng `U+XXXX`, byte dạng hex và giá trị boolean. Tiến trình cha nhận byte stdout bằng `InputStream.readAllBytes()` rồi chuyển thành nội dung ASCII bằng `StandardCharsets.US_ASCII`.

## 4. Chương trình Java chạy các JVM con

Lưu mã dưới đây thành **CharsetForkLab.java** bằng UTF-8. Mã dùng `ProcessBuilder`, `Charset.defaultCharset()`, `System.getProperty`, `System.out.charset()` và `StandardCharsets`; các API này đều có trên JDK hiện đại.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;

public final class CharsetForkLab {
    private static final byte[] UTF8_CAFE = {
            0x63, 0x61, 0x66, (byte) 0xC3, (byte) 0xA9
    };

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--probe")) {
            probe();
            return;
        }

        String classPath = System.getProperty("java.class.path");
        if (classPath == null || classPath.isBlank()) {
            throw new IllegalStateException(
                    "Ví dụ này cần chạy từ classpath không rỗng");
        }

        String os = System.getProperty("os.name").toLowerCase(Locale.ROOT);
        String javaName = os.contains("win") ? "java.exe" : "java";
        Path javaExecutable = Path.of(
                System.getProperty("java.home"), "bin", javaName);

        runProbe(javaExecutable, classPath, "JDK_DEFAULT", null);
        runProbe(javaExecutable, classPath, "EXPLICIT_UTF8", "UTF-8");
        runProbe(javaExecutable, classPath, "COMPAT", "COMPAT");
    }

    private static void runProbe(Path javaExecutable, String classPath,
            String label, String fileEncoding) throws Exception {
        List<String> command = new ArrayList<>();
        command.add(javaExecutable.toString());

        // JVM option phải đứng trước tên lớp chính.
        if (fileEncoding != null) {
            command.add("-Dfile.encoding=" + fileEncoding);
        }

        command.add("-cp");
        command.add(classPath);
        command.add(CharsetForkLab.class.getName());
        command.add("--probe");

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.redirectErrorStream(true);

        // Loại bỏ các biến có thể chèn JVM options vào tiến trình con.
        builder.environment().remove("JAVA_TOOL_OPTIONS");
        builder.environment().remove("JDK_JAVA_OPTIONS");

        Process child = builder.start();
        byte[] report;
        try (InputStream input = child.getInputStream()) {
            report = input.readAllBytes();
        }

        int exitCode = child.waitFor();

        writeAsciiLine("===== " + label + " =====");
        // Báo cáo con chỉ chứa ASCII nên có thể chuyển tiếp nguyên byte.
        System.out.write(report);
        System.out.flush();

        if (exitCode != 0) {
            throw new IllegalStateException(
                    label + " kết thúc với exit code " + exitCode);
        }
    }

    private static void probe() throws IOException {
        Charset defaultCharset = Charset.defaultCharset();
        Charset utf8 = StandardCharsets.UTF_8;

        String cafe = "café";
        String decodedWithDefault = new String(UTF8_CAFE);
        String decodedWithUtf8 = new String(UTF8_CAFE, utf8);

        byte[] encodedWithDefault = cafe.getBytes();
        byte[] encodedWithUtf8 = cafe.getBytes(utf8);

        writeAsciiLine("java.version=" + System.getProperty("java.version"));
        writeAsciiLine("file.encoding="
                + System.getProperty("file.encoding"));
        writeAsciiLine("native.encoding="
                + System.getProperty("native.encoding"));
        writeAsciiLine("defaultCharset=" + defaultCharset.name());
        writeAsciiLine("stdoutCharset=" + System.out.charset().name());

        writeAsciiLine("default.decode.utf8.codePoints="
                + codePoints(decodedWithDefault));
        writeAsciiLine("explicit.decode.utf8.codePoints="
                + codePoints(decodedWithUtf8));
        writeAsciiLine("default.decode.matches.explicit="
                + decodedWithDefault.equals(decodedWithUtf8));

        writeAsciiLine("default.encode.cafe.hex="
                + hex(encodedWithDefault));
        writeAsciiLine("explicit.encode.cafe.utf8.hex="
                + hex(encodedWithUtf8));
        writeAsciiLine("default.encode.matches.utf8="
                + Arrays.equals(encodedWithDefault, encodedWithUtf8));
    }

    private static String codePoints(String text) {
        StringBuilder result = new StringBuilder();
        text.codePoints().forEach(cp -> {
            if (result.length() > 0) result.append(' ');
            result.append(String.format(Locale.ROOT, "U+%04X", cp));
        });
        return result.toString();
    }

    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ").withUpperCase().formatHex(bytes);
    }

    private static void writeAsciiLine(String value) throws IOException {
        System.out.write(value.getBytes(StandardCharsets.US_ASCII));
        System.out.write('\n');
        System.out.flush();
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac -encoding UTF-8 CharsetForkLab.java
java CharsetForkLab
```

Ví dụ chạy trên Windows PowerShell:

```powershell
javac -encoding UTF-8 CharsetForkLab.java
java CharsetForkLab
```

Đây là ví dụ chạy từ classpath. Nếu dự án dùng Java module, cần thay cặp tùy chọn `-cp`/tên lớp bằng `--module-path` và `-m module/name` tương ứng; nguyên tắc truyền tùy chọn JVM trước entry point vẫn giữ nguyên.

## 5. Đọc kết quả của từng tiến trình

Mỗi khối báo cáo bắt đầu bằng một nhãn do tiến trình cha in ra:

| Nhãn | Cấu hình JVM con | Mục đích |
| --- | --- | --- |
| `JDK_DEFAULT` | Không truyền `-Dfile.encoding` | Xác nhận mặc định của JDK 18+ trong môi trường chạy. |
| `EXPLICIT_UTF8` | `-Dfile.encoding=UTF-8` | Xác nhận cấu hình UTF-8 tường minh ngay khi khởi động. |
| `COMPAT` | `-Dfile.encoding=COMPAT` | Xác nhận default charset tương thích với charset native. |

Trong từng báo cáo:

- `file.encoding` cho biết giá trị cấu hình mà JVM con nhận lúc khởi động.
- `native.encoding` cho biết charset native mà JDK nhận diện.
- `defaultCharset` là kết quả thực tế của `Charset.defaultCharset()` trong chính tiến trình con.
- `stdoutCharset` là charset của `PrintStream` stdout. Nó được in riêng vì charset của console/stream là một ranh giới khác với charset mặc định dùng cho các API.
- `default.decode.utf8.codePoints` là kết quả khi dùng `new String(bytes)` và do đó phụ thuộc default charset.
- `explicit.decode.utf8.codePoints` là kết quả khi dùng `new String(bytes, UTF_8)`, luôn giải mã byte mẫu theo UTF-8.
- `default.encode.cafe.hex` là byte khi dùng `String.getBytes()` không truyền charset.
- `explicit.encode.cafe.utf8.hex` là byte khi dùng `String.getBytes(UTF_8)`, luôn là `63 61 66 C3 A9`.

Nếu charset native khác UTF-8, chế độ `COMPAT` có thể cho kết quả `default.decode` hoặc `default.encode` khác chế độ mặc định. Nếu charset native cũng là UTF-8, hai chế độ có thể cho kết quả giống nhau. Cả hai đều là kết quả hợp lệ; hãy căn cứ vào `native.encoding` và `defaultCharset` để giải thích.

### 5.1. Vì sao báo cáo dùng code point và hex?

Nếu terminal hiển thị `café` thành mojibake hoặc ký tự thay thế, chỉ nhìn dòng text không đủ để biết chuỗi trong JVM đã sai hay font/terminal hiển thị sai. Mã báo cáo code point như `U+0063 U+0061 U+0066 U+00E9` và byte hex như `63 61 66 C3 A9`, đều chỉ chứa ký tự ASCII.

Tiến trình con gửi báo cáo bằng `System.out.write()` với byte US-ASCII. Tiến trình cha chuyển tiếp nguyên byte nhận được thay vì giải mã bằng default charset của cha. Nhờ đó, việc so sánh cấu hình charset không bị nhiễu bởi một lần chuyển đổi ký tự ở kênh báo cáo.

## 6. Những điều phép thử chứng minh — và không chứng minh

| Kết quả | Kết luận được phép |
| --- | --- |
| `defaultCharset=UTF-8` ở `JDK_DEFAULT` | JVM con dùng UTF-8 mặc định theo JEP 400. |
| `defaultCharset` ở `COMPAT` bằng `native.encoding` | JVM con đã dùng chế độ tương thích với charset native. |
| `explicit.decode.utf8.codePoints` giống nhau ở cả ba tiến trình | API nhận UTF-8 tường minh giữ nguyên cách giải mã bất kể default charset. |
| `explicit.encode.cafe.utf8.hex` giống nhau ở cả ba tiến trình | API `getBytes(UTF_8)` tạo cùng byte UTF-8. |
| `default.encode.cafe.hex` khác giữa các tiến trình | API dùng default charset chịu ảnh hưởng của cấu hình khởi động. |
| Kết quả `COMPAT` giống `JDK_DEFAULT` | Charset native có thể là UTF-8; không có nghĩa `COMPAT` bị bỏ qua. |

Phép thử không chứng minh mọi API đều dùng `Charset.defaultCharset()`. Một số API có charset cố định trong hợp đồng; ví dụ `Files.readString(path)` và `Files.writeString(path, text)` dùng UTF-8 theo đặc tả. Một số API khác có charset riêng cho console. Luôn kiểm tra tài liệu của overload cụ thể.

Phép thử cũng không chứng minh một file có sẵn là UTF-8. Charset của file phải được xác định theo định dạng hoặc bên phát. Nếu dữ liệu được quy định là UTF-8, hãy truyền `StandardCharsets.UTF_8` rõ ràng thay vì trông chờ chế độ mặc định.

## 7. Cách tránh kết quả sai lệch khi chạy tiến trình con

### 7.1. Truyền từng đối số riêng trong ProcessBuilder

Dùng danh sách đối số như ví dụ. Không ghép cả lệnh thành một chuỗi shell rồi tự xử lý dấu cách/escape. `ProcessBuilder` truyền từng phần tử thành đối số riêng, nên đường dẫn Java hoặc classpath có dấu cách vẫn được giữ nguyên.

### 7.2. Đặt JVM option trước lớp chính

Lệnh đúng:

```bash
java -Dfile.encoding=COMPAT -cp . CharsetForkLab --probe
```

Nếu đặt `-Dfile.encoding=COMPAT` sau `CharsetForkLab`, nó trở thành tham số cho `main(String[] args)`, không còn là tùy chọn khởi động JVM.

### 7.3. Dùng đúng Java executable

Ví dụ lấy executable từ `java.home` của JVM cha để các tiến trình con dùng cùng bản JDK. Nếu mục tiêu là so sánh giữa các phiên bản JDK, hãy chủ động truyền đường dẫn executable cho từng bản JDK và in `java.version` trong mỗi tiến trình.

### 7.4. Không giả định system properties được kế thừa

Tiến trình con không tự nhận `System.setProperty` của cha. Các tùy chọn phải xuất hiện trong command line hoặc được cấu hình qua biến môi trường JVM. Ví dụ loại bỏ `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS` nhằm làm rõ ba cấu hình đang kiểm thử; nếu môi trường build bắt buộc các biến này cho agent hoặc công cụ giám sát, cần cân nhắc tác động trước khi loại bỏ chúng.

### 7.5. Kiểm tra exit code và đọc hết output

Đọc stdout/stderr đến EOF trước khi kết luận tiến trình hoàn thành; ví dụ gộp stderr vào stdout và đọc toàn bộ byte báo cáo. Sau đó kiểm tra `waitFor()` và exit code. Một tiến trình con thất bại khi khởi động không được tính là phép thử charset thành công.

## 8. Biến thể: chạy nhiều JVM từ một bộ test

Trong CI hoặc integration test, có thể tách chương trình probe thành một lớp riêng rồi dùng test runner khởi chạy từng JVM với tham số khác nhau. Điều quan trọng là mỗi cấu hình phải có **process boundary** thực sự:

```text
Test case: default
    -> JVM mới, không có file.encoding override

Test case: explicit UTF-8
    -> JVM mới, -Dfile.encoding=UTF-8

Test case: compatibility
    -> JVM mới, -Dfile.encoding=COMPAT
```

Không dùng một test method để gọi `System.setProperty` nhiều lần rồi coi mỗi lần là một lần khởi động mới. Test đó chỉ thay đổi system property, không tái tạo quá trình khởi tạo charset của JVM.

Nếu kiểm thử API có charset tường minh, chạy cùng test ở nhiều tiến trình giúp chứng minh tính ổn định của hợp đồng. Nếu kiểm thử API phụ thuộc default charset, hãy ghi lại cấu hình thực tế và đặt kỳ vọng theo `Charset.defaultCharset()` của từng tiến trình, thay vì hard-code rằng `COMPAT` phải khác UTF-8 trên mọi máy.

## 9. Bài thực hành và tiêu chí hoàn thành

1. Biên dịch `CharsetForkLab` và chạy chương trình cha. Xác nhận có ba khối `JDK_DEFAULT`, `EXPLICIT_UTF8`, `COMPAT`.
2. Ghi lại `file.encoding`, `native.encoding`, `defaultCharset` và `stdoutCharset` của từng JVM con.
3. So sánh `default.decode.utf8.codePoints` với `explicit.decode.utf8.codePoints`; giải thích sự khác nhau nếu native charset không phải UTF-8.
4. So sánh `default.encode.cafe.hex` và `explicit.encode.cafe.utf8.hex`; xác định API nào phụ thuộc default charset.
5. Chạy chương trình cha từ một JVM đã khởi chạy với `-Dfile.encoding=COMPAT`. Xác nhận JVM con `JDK_DEFAULT` vẫn dùng cấu hình khởi động mặc định riêng vì system property của cha không tự truyền sang con.
6. Chạy trên môi trường native UTF-8 và môi trường native khác UTF-8 nếu có. Giải thích vì sao kết quả `COMPAT` có thể trùng hoặc khác mặc định.
7. Thử bỏ phần loại bỏ `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS` trong bản sao môi trường con và quan sát các tùy chọn được chèn có thể ảnh hưởng phép đo ra sao.

**Tiêu chí hoàn thành:** bạn tạo được nhiều JVM độc lập từ một chương trình cha; truyền đúng `-Dfile.encoding` ở thời điểm khởi động; đọc được `file.encoding`, `native.encoding` và `Charset.defaultCharset()` của từng tiến trình; chứng minh API charset tường minh không đổi theo cấu hình mặc định; và giải thích được vì sao `COMPAT` phụ thuộc môi trường native. Đây là cách kiểm chứng còn áp dụng trên JDK hiện đại theo JEP 400.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): UTF-8 mặc định, `COMPAT` và `native.encoding` từ Java 18.
- [Java SE ProcessBuilder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html): tạo tiến trình, truyền đối số và cấu hình môi trường.
- [Java SE Process](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Process.html): đọc stream, chờ tiến trình và kiểm tra exit code.
- [Java SE Charset](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html): `defaultCharset()` và charset mặc định của runtime.
- [Java SE PrintStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintStream.html): `charset()` và encoding của output stream.
