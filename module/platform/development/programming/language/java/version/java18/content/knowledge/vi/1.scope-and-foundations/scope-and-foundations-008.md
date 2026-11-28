# Tổ chức ví dụ tối thiểu với đầu vào, kết quả mong đợi, ngoại lệ và thông tin môi trường

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Trình bày một ví dụ Java có thể tái hiện và kiểm chứng: đầu vào, thư mục chạy, lệnh thực thi, stdout, stderr, exit code, ngoại lệ dự kiến và thông tin môi trường. Áp dụng cách tổ chức này cho UTF-8 mặc định, Simple Web Server, Javadoc snippet, resolver SPI, reflection và MethodHandle trên JDK hiện đại.

## 1. Một ví dụ kỹ thuật cần đủ dữ liệu để tái hiện

Một đoạn code ngắn chưa chắc là một ví dụ có thể kiểm chứng. Người đọc còn cần biết:

- Dùng JDK/compiler/runtime nào?
- Lệnh chạy được gọi từ thư mục nào?
- Đầu vào cụ thể là gì, encoding nào, có phụ thuộc mạng hoặc filesystem không?
- Kết quả nào phải xuất hiện ở stdout?
- Có thông báo nào dự kiến đi ra stderr?
- Chương trình phải kết thúc với exit code nào?
- Nếu lỗi xảy ra, ngoại lệ nào được mong đợi và ngoại lệ đó xuất hiện trực tiếp hay được bọc?
- Kết quả nào ổn định theo hợp đồng, kết quả nào phụ thuộc OS, locale, DNS, vendor hoặc phiên bản JDK?

Một ví dụ tối thiểu tốt cần trả lời được các câu hỏi này mà không bắt người đọc đoán môi trường.

### 1.1. Phân biệt code sample, smoke test và regression test

| Loại | Mục đích | Nội dung cần có |
|---|---|---|
| Code sample | Minh họa API hoặc khái niệm | Mã ngắn, đầu vào mẫu, kết quả minh họa, điều kiện |
| Smoke test | Xác nhận môi trường và tính năng cơ bản đang hoạt động | Lệnh chạy, điều kiện môi trường, kết quả thành công/lỗi, exit code |
| Regression test | Ngăn lỗi đã biết quay lại | Fixture cố định, assertion tự động, expected behavior, cách chạy CI |
| Diagnostic example | Thu thập thông tin để phân loại vấn đề | Version, vendor, OS, locale, charset, module, cấu hình |

Một code sample có thể trở thành smoke test nếu thêm lệnh và kết quả mong đợi. Một smoke test có thể trở thành regression test khi đầu vào và assertion được cố định, tự động chạy và duy trì cùng dự án.

Không cần biến mọi đoạn minh họa nhỏ thành dự án kiểm thử phức tạp. Hãy ghi đủ dữ kiện để người khác hiểu **điều kiện nào tạo ra kết quả**.

### 1.2. Cấu trúc tối thiểu nên có

Một ví dụ kỹ thuật có thể tổ chức theo thứ tự sau:

1. **Mục đích:** Đang kiểm tra điều gì?
2. **Điều kiện:** JDK tối thiểu, module, quyền truy cập, OS hoặc kết nối cần thiết.
3. **Tệp và cấu trúc:** Tên file, nội dung fixture, thư mục làm việc.
4. **Đầu vào:** Argument, stdin, file, HTTP request, DNS name hoặc dữ liệu cấu hình.
5. **Lệnh:** Lệnh compile và run chính xác, có ghi `--release` nếu cần.
6. **Kết quả mong đợi:** stdout, stderr, exit code và trạng thái tài nguyên.
7. **Ngoại lệ:** Loại ngoại lệ, nguyên nhân, lớp bọc và thời điểm phát sinh.
8. **Môi trường:** Compiler/runtime version, vendor, OS/architecture, locale, charset và module.
9. **Giới hạn:** Phần nào có thể biến thiên và không được dùng làm assertion cố định.

Cấu trúc này phù hợp cho cả ví dụ vài dòng lẫn bài kiểm chứng một thay đổi của JDK.

## 2. Tách đầu vào, đầu ra và điều kiện môi trường

### 2.1. Đầu vào phải cụ thể và có thể tái tạo

Không ghi chung chung “nhập một chuỗi bất kỳ” nếu ví dụ cần kiểm tra Unicode. Hãy cung cấp chuỗi, encoding, file hoặc request chính xác.

| Loại đầu vào | Cần ghi |
|---|---|
| Argument dòng lệnh | Giá trị, thứ tự, cách quote nếu có khoảng trắng |
| stdin | Nội dung, encoding, ký tự kết thúc dòng nếu có ý nghĩa |
| File | Đường dẫn tương đối, nội dung, encoding, newline/BOM nếu liên quan |
| HTTP | Method, URL, headers cần thiết, body và server address |
| DNS | Hostname, resolver/network context và việc kết quả có thể thay đổi |
| Reflection/MethodHandle | Class, method, signature, lookup context và quyền truy cập |
| Module | Module path, module name, requires, service provider cần thiết |

Đối với đầu vào nhạy cảm, dùng fixture giả lập. Không đưa password, token, dữ liệu khách hàng hoặc hostname nội bộ vào ví dụ công khai.

### 2.2. Thư mục làm việc là một phần của ví dụ

Các đường dẫn tương đối được tính từ current working directory. Ví dụ:

~~~text
example/
├── src/
│   └── NormalizeInput.java
├── input/
│   └── sample.txt
└── out/
~~~

Nếu lệnh là:

~~~shell
java -cp out NormalizeInput "  Java 18  "
~~~

thì người đọc cần biết chạy lệnh từ thư mục `example/` và thư mục `out/` đã có class file. Nếu chạy từ thư mục cha, đường dẫn tương đối sẽ khác.

Nên ghi:

~~~text
Working directory: example/
Compile output: out/
Input file: input/sample.txt
~~~

Không dùng đường dẫn tuyệt đối từ máy tác giả như `C:\Users\...` hoặc `/home/alice/...` làm điều kiện bắt buộc. Đường dẫn tuyệt đối chỉ cần khi đang chẩn đoán một môi trường cụ thể.

### 2.3. Tách kết quả ổn định và kết quả phụ thuộc môi trường

| Kết quả | Có nên so khớp chính xác? | Lý do |
|---|---|---|
| Chuỗi do chương trình tự in từ input cố định | Có | Đầu vào và logic đã xác định |
| `Charset.defaultCharset()` trên JDK 18+ cấu hình mặc định | Có thể kiểm tra `UTF-8`, nhưng phải ghi override nếu có | JEP 400 thay đổi default charset; runtime option vẫn có thể ảnh hưởng |
| Địa chỉ IP do DNS trả về | Thường không | DNS, cache, IPv4/IPv6 và mạng thay đổi |
| Stack trace đầy đủ | Không nên | Đường dẫn, dòng code và cách trình bày thay đổi |
| Loại ngoại lệ và cause theo hợp đồng API | Có | Đây thường là hành vi cần xác minh |
| Header HTTP như `Date` | Không | Giá trị thay đổi theo thời điểm |
| HTTP status và body của fixture cố định | Có | Có thể xác định chính xác nếu server và file đã được kiểm soát |
| Thời gian thực thi | Không dùng làm assertion chức năng | Phụ thuộc máy, tải, JIT và môi trường |

Một ví dụ tốt không nhất thiết có output giống từng ký tự trên mọi OS. Nó phải nói rõ phần nào cần giống và phần nào chỉ để quan sát.

## 3. Ghi lại môi trường trước khi chạy

Các thay đổi Java 18 được học trên JDK hiện đại có thể phụ thuộc runtime và module. Ít nhất hãy ghi nhận:

| Thuộc tính | Vì sao cần |
|---|---|
| `java --version` | Xác định JVM launcher và build |
| `javac --version` | Xác định compiler |
| `javadoc --version` | Xác định standard doclet/tool tạo tài liệu |
| `jwebserver --version` | Xác định công cụ Simple Web Server |
| `java.vendor` | Phân biệt nhà phân phối |
| `java.runtime.version` | Ghi patch/build runtime |
| `java.home` | Xác định runtime home thực tế |
| `os.name`, `os.version`, `os.arch` | Chẩn đoán khác biệt hệ điều hành/kiến trúc |
| Locale mặc định | Có thể ảnh hưởng định dạng và dữ liệu văn bản |
| `Charset.defaultCharset()` | Xác minh default charset thực tế |
| Module liên quan | Phát hiện runtime image thiếu module |

### 3.1. Lệnh thu thập thông tin cơ bản

Trên Linux/macOS:

~~~shell
java --version
javac --version
javadoc --version
jwebserver --version
java -XshowSettings:properties -version
java --list-modules
~~~

Trên Windows PowerShell:

~~~powershell
java --version
javac --version
javadoc --version
jwebserver --version
java -XshowSettings:properties -version
java --list-modules
~~~

Nếu môi trường không có `jwebserver`, ghi nhận lỗi đó cùng loại runtime đang dùng; không tự kết luận JDK hỏng. Một custom runtime image có thể chủ động bỏ `jdk.httpserver`.

### 3.2. Chương trình ghi nhận môi trường từ chính JVM

Có thể dùng một class nhỏ trong ví dụ:

~~~java
import java.nio.charset.Charset;
import java.util.Locale;

public final class EnvironmentInfo {
    public static void main(String[] args) {
        print("java.version");
        print("java.runtime.version");
        print("java.vendor");
        print("java.home");
        print("os.name");
        print("os.version");
        print("os.arch");
        print("file.encoding");
        print("native.encoding");

        System.out.println("defaultCharset="
                + Charset.defaultCharset().name());
        System.out.println("locale=" + Locale.getDefault());
    }

    private static void print(String key) {
        System.out.println(key + "="
                + System.getProperty(key, "<not available>"));
    }
}
~~~

Compile và chạy bằng JDK được chọn:

~~~shell
javac -encoding UTF-8 --release 18 -d out src/EnvironmentInfo.java
java -cp out EnvironmentInfo
~~~

`file.encoding` và `native.encoding` hữu ích như dữ liệu chẩn đoán, nhưng `Charset.defaultCharset()` là API nên dùng khi muốn hỏi default charset của JVM. Không dùng giá trị property nội bộ làm hợp đồng thay cho API được đặc tả.

Đầu ra chứa đường dẫn và thông tin máy. Khi chia sẻ log ra ngoài, loại bỏ username, thư mục riêng, tên máy và dữ liệu nhạy cảm nếu chúng không cần cho việc chẩn đoán.

### 3.3. Ghi compiler và runtime riêng

Một ví dụ có thể được compile bằng JDK 27 với `--release 18`, rồi chạy trên JDK 25. Hãy ghi cả ba giá trị:

~~~text
Compiler: javac 27.x
Compile target/API baseline: --release 18
Runtime: OpenJDK 25.x
Vendor: ...
OS/architecture: ...
~~~

`--release 18` giới hạn source, class file và API platform ở compile time; nó không mô phỏng JVM 18. Những phép thử default charset, resolver, reflection và module phải ghi runtime thực tế.

## 4. Ví dụ tối thiểu: đầu vào, kết quả và exit code

Một chương trình nhỏ có thể quy định rõ cả đường chạy thành công và thất bại. Ví dụ sau nhận đúng một argument, loại bỏ khoảng trắng đầu/cuối và từ chối chuỗi rỗng.

Tệp `src/NormalizeInput.java`:

~~~java
public final class NormalizeInput {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("ERROR: expected exactly one argument");
            System.exit(2);
            return;
        }

        String value = args[0].strip();
        if (value.isEmpty()) {
            System.err.println("ERROR: input must not be blank");
            System.exit(3);
            return;
        }

        System.out.println(value);
    }
}
~~~

Compile:

~~~shell
javac --release 18 -encoding UTF-8 -d out src/NormalizeInput.java
~~~

### 4.1. Ca thành công

Đầu vào:

~~~shell
java -cp out NormalizeInput "  Java 18  "
~~~

Kết quả mong đợi:

~~~text
stdout:
Java 18

stderr:
(empty)

exit code:
0
~~~

### 4.2. Ca thiếu argument

~~~shell
java -cp out NormalizeInput
~~~

Kết quả mong đợi:

~~~text
stdout:
(empty)

stderr:
ERROR: expected exactly one argument

exit code:
2
~~~

### 4.3. Ca đầu vào chỉ có khoảng trắng

~~~shell
java -cp out NormalizeInput "   "
~~~

Kết quả mong đợi:

~~~text
stdout:
(empty)

stderr:
ERROR: input must not be blank

exit code:
3
~~~

Mã thoát `2` và `3` ở đây là quy ước do chính ứng dụng định nghĩa. Khi ví dụ bắt đầu dùng `System.exit`, cần ghi rõ mã thoát để script/CI kiểm tra được. Với một ngoại lệ không được bắt, nên kiểm tra rằng tiến trình kết thúc khác 0 và ghi loại ngoại lệ; tránh phụ thuộc toàn bộ stack trace vì đường dẫn và số dòng có thể đổi.

Trên PowerShell, sau khi chạy chương trình Java, xem mã thoát bằng `$LASTEXITCODE`. Trên Bash/Zsh, xem bằng `$?`.

## 5. Kiểm chứng UTF-8 mặc định mà không nhầm encoding của file và terminal

JEP 400 đặt UTF-8 làm default charset của Java từ JDK 18 trên cấu hình mặc định. Khi viết ví dụ, phải phân biệt:

1. Encoding của source file khi compiler đọc mã nguồn.
2. Encoding của file dữ liệu được đọc/ghi.
3. Default charset của JVM.
4. Encoding của console/terminal khi hiển thị stdout/stderr.

Bốn giá trị này có thể liên quan nhưng không phải một.

### 5.1. Ví dụ ghi nhận default charset

Tệp `src/DefaultCharsetCheck.java`:

~~~java
import java.nio.charset.Charset;

public final class DefaultCharsetCheck {
    public static void main(String[] args) {
        System.out.println(Charset.defaultCharset().name());
    }
}
~~~

Compile và chạy:

~~~shell
javac --release 18 -encoding UTF-8 -d out src/DefaultCharsetCheck.java
java -cp out DefaultCharsetCheck
~~~

Kết quả mong đợi trên JDK 18+ với cấu hình mặc định:

~~~text
UTF-8
~~~

Nếu kết quả khác, ghi lại runtime version và JVM options. Có thể có tùy chọn tương thích hoặc cấu hình riêng. Không chỉ dựa vào phiên bản compiler để kết luận charset runtime.

### 5.2. Ví dụ file UTF-8 với encoding được chỉ định tường minh

Tệp `src/Utf8FileCheck.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public final class Utf8FileCheck {
    public static void main(String[] args) throws Exception {
        Path file = Path.of("sample.txt");
        String value = "é";

        Files.writeString(file, value, StandardCharsets.UTF_8);
        String loaded = Files.readString(file, StandardCharsets.UTF_8);

        if (!value.equals(loaded)) {
            throw new AssertionError("UTF-8 round-trip failed");
        }

        byte[] bytes = Files.readAllBytes(file);
        System.out.println(HexFormat.of().formatHex(bytes));
    }
}
~~~

Compile và chạy từ thư mục ví dụ:

~~~shell
javac --release 18 -encoding UTF-8 -d out src/Utf8FileCheck.java
java -cp out Utf8FileCheck
~~~

Kết quả mong đợi:

~~~text
c3a9
~~~

`c3a9` là byte UTF-8 của ký tự `é`. Ví dụ này kiểm tra encoding được chỉ định rõ trong API file; nó **không** chứng minh mọi API dùng default charset hoặc console đều dùng cùng encoding.

### 5.3. Ghi nhận khác biệt giữa default charset và console

Nếu `Charset.defaultCharset()` in `UTF-8` nhưng tiếng Việt bị lỗi trên terminal, hãy kiểm tra console, font, encoding của shell và cách output được redirect. Không thay assertion của file round-trip chỉ vì terminal hiển thị không đúng.

Với dữ liệu trao đổi qua file, HTTP, database hoặc message queue, ưu tiên chỉ định charset/giao thức tường minh. Default charset là thông tin môi trường hữu ích, không phải lý do để bỏ encoding khỏi hợp đồng dữ liệu.

## 6. Kiểm chứng ngoại lệ: reflection và MethodHandle

JEP 416 thay đổi cách triển khai core reflection trong JDK 18 bằng method handles. Khi viết ví dụ, cần tách hợp đồng public của `Method.invoke` khỏi cách runtime thực thi bên trong.

### 6.1. Reflection: ngoại lệ của method đích được bọc

Tệp `src/ReflectionExceptionCheck.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class ReflectionExceptionCheck {
    public static void fail() {
        throw new IllegalStateException("target failed");
    }

    public static void main(String[] args) throws Exception {
        Method method = ReflectionExceptionCheck.class
                .getMethod("fail");

        try {
            method.invoke(null);
        } catch (InvocationTargetException exception) {
            Throwable cause = exception.getCause();
            System.out.println(cause.getClass().getSimpleName());
            System.out.println(cause.getMessage());
        }
    }
}
~~~

Compile và chạy:

~~~shell
javac --release 18 -d out src/ReflectionExceptionCheck.java
java -cp out ReflectionExceptionCheck
~~~

Kết quả mong đợi:

~~~text
IllegalStateException
target failed
~~~

Điểm cần kiểm tra:

- `Method.invoke` ném `InvocationTargetException` khi method đích ném ngoại lệ.
- Nguyên nhân gốc nằm trong `getCause()`.
- `IllegalAccessException` hoặc `IllegalArgumentException` có thể xuất hiện trực tiếp trong các trường hợp tương ứng; chúng không phải ngoại lệ do method đích ném.
- Nếu cần test ngoại lệ của target, kiểm tra cause và loại ngoại lệ cụ thể.

Không viết test chỉ kiểm tra chuỗi stack trace đầy đủ. Hãy kiểm tra loại wrapper, loại cause và thông điệp nếu thông điệp đó là một phần của hợp đồng ứng dụng.

### 6.2. MethodHandle: ngoại lệ của target truyền trực tiếp

Tệp `src/MethodHandleExceptionCheck.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class MethodHandleExceptionCheck {
    public static void fail() {
        throw new IllegalStateException("target failed");
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findStatic(
                MethodHandleExceptionCheck.class,
                "fail",
                MethodType.methodType(void.class));

        try {
            handle.invokeExact();
        } catch (IllegalStateException exception) {
            System.out.println(exception.getClass().getSimpleName());
            System.out.println(exception.getMessage());
        }
    }
}
~~~

Compile và chạy:

~~~shell
javac --release 18 -d out src/MethodHandleExceptionCheck.java
java -cp out MethodHandleExceptionCheck
~~~

Kết quả mong đợi:

~~~text
IllegalStateException
target failed
~~~

Ở ví dụ này, `invokeExact()` gọi method có method type `()void`, nên call site phải khớp chính xác kiểu đã khai báo. Nếu thay signature, kiểu trả về hoặc kiểu argument không khớp, có thể gặp `WrongMethodTypeException`. Đây là lỗi khác với ngoại lệ do method đích ném.

### 6.3. Ghi rõ điều gì đang được kiểm tra

| Câu hỏi | Reflection | MethodHandle |
|---|---|---|
| API nào được gọi? | `Method.invoke` | `MethodHandle.invokeExact` |
| Target ném `IllegalStateException` | Bọc trong `InvocationTargetException` | Truyền trực tiếp `IllegalStateException` |
| Lỗi quyền truy cập | Có thể là `IllegalAccessException` | Phụ thuộc lookup/access check khi tìm handle |
| Signature call site không phù hợp | Quy tắc argument/conversion của reflection | Có thể là `WrongMethodTypeException` với `invokeExact` |
| Có thể suy luận JDK đã tối ưu thế nào? | Không | Không |

Đây là phép kiểm chứng hợp đồng API và ngoại lệ quan sát được. Nó không đo hiệu năng, không chứng minh JDK dùng một chuỗi lời gọi nội bộ cụ thể và không biến MethodHandle thành API mới của Java 18.

## 7. Kiểm chứng phân giải tên: không đóng đinh địa chỉ DNS

JEP 418 đưa vào SPI cho phép thay thế cơ chế phân giải địa chỉ của `InetAddress`. Một ví dụ cơ bản có thể kiểm tra việc phân giải tên đang hoạt động:

Tệp `src/ResolveHost.java`:

~~~java
import java.net.InetAddress;

public final class ResolveHost {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: ResolveHost <hostname>");
            System.exit(2);
            return;
        }

        InetAddress[] addresses = InetAddress.getAllByName(args[0]);
        for (InetAddress address : addresses) {
            System.out.println(address.getHostAddress());
        }
    }
}
~~~

Compile:

~~~shell
javac --release 18 -d out src/ResolveHost.java
~~~

Chạy với hostname công khai phù hợp chính sách mạng của môi trường:

~~~shell
java -cp out ResolveHost example.com
~~~

### 7.1. Đầu ra nào nên kỳ vọng?

Kết quả thành công là một hoặc nhiều địa chỉ IP được in ra. Không nên đưa một địa chỉ cố định vào expected output vì DNS có thể trả nhiều địa chỉ và thay đổi theo thời gian, vị trí, resolver, cache, chính sách IPv4/IPv6 và hạ tầng của tên miền.

Một hồ sơ kiểm thử tốt ghi:

~~~text
Input hostname: example.com
Expected: DNS lookup succeeds in the configured test environment
Observed: one or more resolved addresses
Environment: JDK vendor/version, OS, DNS/network context
Exact IP assertion: not used
~~~

Khi môi trường offline, proxy hoặc DNS nội bộ không cho phép truy cập tên miền, kết quả thất bại không chứng minh API Java bị lỗi. Hãy phân loại đây là lỗi môi trường/kết nối cho tới khi có bằng chứng khác.

### 7.2. Phép thử này không chứng minh provider SPI tùy biến đã được dùng

`InetAddress.getAllByName` kiểm tra đường phân giải tên qua resolver hiện tại. Nó không tự xác minh ứng dụng đã đăng ký một `InetAddressResolverProvider` tùy biến.

Muốn kiểm tra provider của JEP 418:

1. Tạo provider triển khai đúng API `InetAddressResolverProvider`/`InetAddressResolver`.
2. Đăng ký qua cơ chế service phù hợp (module `provides` hoặc service configuration).
3. Đóng gói provider và dependency vào module path/classpath theo thiết kế.
4. Chạy một JVM mới với cấu hình được kiểm soát để việc chọn resolver diễn ra từ đầu.
5. Dùng hostname thử nghiệm do provider quản lý và ghi rõ kết quả mà provider trả về.
6. Kiểm tra log/diagnostic của provider để xác nhận request đi qua implementation mong muốn.

Không dựa vào thứ tự provider không được đặc tả. Nếu nhiều provider cùng hiện diện, thứ tự lựa chọn có thể phụ thuộc implementation; thiết kế test nên kiểm soát provider được đóng gói và môi trường khởi chạy.

## 8. Kiểm chứng Simple Web Server: request, status và body

JEP 408 bổ sung Simple Web Server cho việc phát triển, thử nghiệm và gỡ lỗi. Một ví dụ tối thiểu cần cố định thư mục gốc, bind address, port và file cần phục vụ.

Cấu trúc:

~~~text
web-example/
├── public/
│   └── index.html
└── README.md
~~~

Nội dung `public/index.html`:

~~~html
<!doctype html>
<html lang="vi">
  <meta charset="UTF-8">
  <title>Java 18 example</title>
  <body>Simple Web Server OK</body>
</html>
~~~

Từ thư mục `web-example/`, chạy:

~~~shell
jwebserver -b 127.0.0.1 -p 8000 -d public
~~~

Từ terminal thứ hai:

~~~shell
curl -i http://127.0.0.1:8000/index.html
~~~

Kết quả cần kiểm tra:

- HTTP status là `200`.
- Response body chứa `Simple Web Server OK`.
- Server chỉ bind trên loopback `127.0.0.1` theo lệnh đã chỉ định.
- Kết thúc server bằng `Ctrl+C`.

Có thể kiểm tra HEAD:

~~~shell
curl -I http://127.0.0.1:8000/index.html
~~~

Nếu kiểm tra đường dẫn không tồn tại:

~~~shell
curl -i http://127.0.0.1:8000/missing.html
~~~

Kỳ vọng là phản hồi lỗi HTTP phù hợp cho tài nguyên không có. Không so khớp toàn bộ header như `Date`, vì header thời gian thay đổi. Có thể so khớp status và body/đặc điểm response mà tool specification quy định.

### 8.1. Điều kiện và giới hạn cần ghi

`jwebserver` là công cụ JDK, thuộc module `jdk.httpserver`. Khi chạy trong custom runtime image, module có thể không được đóng gói. Hãy ghi version tool, module presence, command line và thư mục gốc.

Simple Web Server phục vụ tệp tĩnh qua HTTP/1.1, hỗ trợ GET và HEAD. Nó không cung cấp HTTPS/HTTP/2 và không phải web server production. Không dùng một ví dụ loopback để kết luận máy khác trên mạng có thể truy cập server.

## 9. Kiểm chứng Javadoc snippet: phân biệt render và execute

JEP 413 bổ sung hỗ trợ code snippet trong standard doclet của Javadoc. Ví dụ:

Tệp `src/SnippetExample.java`:

~~~java
/**
 * Chuẩn hóa một chuỗi.
 *
 * {@snippet lang="java" :
 *     String value = "  Java 18  ".strip();
 *     System.out.println(value); // Java 18
 * }
 */
public final class SnippetExample {
    private SnippetExample() {}

    public static String normalize(String input) {
        return input.strip();
    }
}
~~~

Tạo Javadoc:

~~~shell
javadoc -encoding UTF-8 -d docs src/SnippetExample.java
~~~

Kiểm tra trang HTML trong `docs/`:

- Snippet được render trong phần mô tả.
- Ngôn ngữ được nhận diện là Java.
- Nội dung code hiển thị đúng.
- Các ký tự Unicode (nếu có) được hiển thị đúng trong HTML.

**Không kết luận rằng snippet đã được compile hoặc chạy.** Javadoc standard doclet xử lý và trình bày tài liệu; nó không thay thế compiler/test suite của dự án. Nếu ví dụ có assertion hoặc output quan trọng, tạo một test source riêng và chạy nó.

Trong hồ sơ, ghi version `javadoc`, standard doclet (nếu dùng doclet khác thì ghi tên/version), command line và đường dẫn output. Không suy luận doclet đang dùng chỉ từ version của `java`.

## 10. Quy định expected output và ngoại lệ theo hợp đồng

### 10.1. Ghi output theo từng stream

Một tiến trình có ít nhất hai luồng output thường cần phân biệt:

- **stdout:** kết quả bình thường mà script hoặc người đọc có thể xử lý.
- **stderr:** chẩn đoán, lỗi đầu vào hoặc thông tin không thuộc kết quả chính.
- **Exit code:** trạng thái thành công/thất bại của tiến trình.

Ví dụ bảng expected:

| Ca | stdout | stderr | Exit code |
|---|---|---|---:|
| Input hợp lệ | Chuỗi đã chuẩn hóa | Rỗng | 0 |
| Thiếu argument | Rỗng | Thông báo usage | 2 |
| Chuỗi rỗng sau strip | Rỗng | Thông báo input blank | 3 |
| DNS thành công | Một hoặc nhiều IP | Rỗng | 0 |
| DNS thất bại | Có thể rỗng | Stack trace hoặc chẩn đoán | Khác 0 |

Với DNS, exception và output cụ thể phụ thuộc môi trường; chỉ kiểm tra chính xác những điều mà ví dụ đã cam kết. Với chương trình tự định nghĩa exit code, có thể kiểm tra chính xác mã đó.

### 10.2. Ngoại lệ cần mô tả theo nguồn phát sinh

Khi ghi một ngoại lệ, trả lời:

1. Ngoại lệ đến từ API được gọi, từ code ứng dụng hay từ launcher/JVM?
2. Là checked exception hay unchecked exception?
3. Có bị bọc trong ngoại lệ khác không?
4. `getCause()` hoặc `getTargetException()` chứa gì?
5. Ngoại lệ phát sinh ngay lúc lookup, lúc gọi method hay lúc runtime liên kết class?
6. Điều kiện môi trường nào có thể làm ngoại lệ xuất hiện?

Ví dụ:

| API/tình huống | Kết quả lỗi cần mô tả |
|---|---|
| `Method.invoke` — target ném lỗi | `InvocationTargetException`, kiểm tra cause |
| `Method.invoke` — quyền truy cập không hợp lệ | `IllegalAccessException` theo điều kiện API |
| `MethodHandle.invokeExact` — call-site type không khớp | `WrongMethodTypeException` |
| DNS không phân giải được | `UnknownHostException`; ghi hostname và network context |
| JVM không hỗ trợ class file | `UnsupportedClassVersionError` khi load class |
| Runtime thiếu module | Lỗi module resolution hoặc class visibility tùy cách khởi chạy |

Không ghi “ném exception” mà bỏ loại cụ thể và nguyên nhân. Không yêu cầu người đọc so khớp toàn bộ stack trace nếu mục tiêu chỉ là xác minh hợp đồng ngoại lệ.

### 10.3. Đừng dùng thông điệp lỗi làm hợp đồng nếu API không bảo đảm

Thông điệp ngoại lệ có thể khác giữa vendor, phiên bản, locale hoặc lớp gọi. Hãy ưu tiên kiểm tra:

- Loại ngoại lệ.
- Cause và loại cause.
- Trạng thái hoặc mã lỗi do ứng dụng định nghĩa.
- Một phần thông điệp chỉ khi tài liệu/ứng dụng cam kết nội dung đó.

Ví dụ, `UnknownHostException` là dấu hiệu phân giải tên thất bại; nội dung message có thể chứa hostname hoặc chi tiết do implementation cung cấp. Nếu test chỉ cần xác nhận lỗi DNS, kiểm tra loại exception và hostname đầu vào thay vì exact message.

## 11. Mẫu hồ sơ ví dụ có thể tái sử dụng

Có thể dùng mẫu sau cho README, tài liệu API hoặc issue:

~~~text
# Example ID:
Title:
Purpose:
Related Java/JDK feature:
Scope (Java SE API / JDK API / tool / runtime behavior):

## Requirements
Minimum JDK:
Compiler version/vendor:
Runtime version/vendor:
Required modules:
OS / architecture:
Locale / charset:
Network / filesystem / permissions:

## Files
Working directory:
Source files:
Input fixtures:
Expected output files:

## Input
Command-line arguments:
stdin:
Files and encoding:
HTTP/DNS input:
Other configuration:

## Commands
Compile command:
Run command:
Tool command:
Working directory:

## Expected result
stdout:
stderr:
Exit code:
Created/modified resources:

## Expected exceptions
Exception type:
Cause / wrapper:
Trigger condition:
When it occurs:

## Environment evidence
java --version:
javac --version:
javadoc --version:
jwebserver --version:
java.vendor:
java.runtime.version:
java.home:
Charset.defaultCharset():
Relevant modules:

## Variability
Stable assertions:
Environment-dependent observations:
What is deliberately not asserted:

## Cleanup
Temporary files:
Server/process to stop:
~~~

Không phải mọi trường đều cần cho mọi ví dụ. Có thể ghi “không áp dụng” hoặc bỏ trường không liên quan; đừng tự tạo giá trị giả. Ví dụ DNS cần network context, còn bài `strip()` đơn giản không cần module HTTP server.

## 12. Cách tổ chức ví dụ trong thư mục dự án

Với nhiều ví dụ liên quan Java 18, giữ mỗi ví dụ độc lập và dùng tên mô tả. Ví dụ:

~~~text
java18-examples/
├── README.md
├── env/
│   └── EnvironmentInfo.java
├── charset/
│   ├── DefaultCharsetCheck.java
│   └── Utf8FileCheck.java
├── reflection/
│   ├── ReflectionExceptionCheck.java
│   └── MethodHandleExceptionCheck.java
├── resolver/
│   └── ResolveHost.java
├── webserver/
│   └── public/
│       └── index.html
└── javadoc/
    └── SnippetExample.java
~~~

Mỗi thư mục có thể có phần README nhỏ mô tả:

- Mục đích ví dụ.
- JDK/tool/module yêu cầu.
- Lệnh compile/run.
- Input và expected output.
- Ngoại lệ hoặc lỗi môi trường dự kiến.
- Giới hạn của kết luận.

Không dùng chung một thư mục output cho nhiều compiler release nếu dễ gây nhầm class file cũ. Xóa hoặc tạo thư mục output riêng trước mỗi lượt build để tránh chạy nhầm `.class` từ lần biên dịch trước.

## 13. Tự động hóa kiểm tra mà vẫn giữ ví dụ dễ đọc

### 13.1. Chạy compile và run trong script

Ví dụ Bash:

~~~shell
set -eu

rm -rf out
mkdir -p out

javac --release 18 -encoding UTF-8 -d out src/NormalizeInput.java

actual="$(java -cp out NormalizeInput "  Java 18  ")"
expected="Java 18"

if [ "$actual" != "$expected" ]; then
  printf 'Expected: <%s>\nActual: <%s>\n' "$expected" "$actual" >&2
  exit 1
fi
~~~

Trong script thật, cân nhắc cách xử lý Windows và shell khác nhau; `rm -rf` chỉ phù hợp môi trường POSIX. Không dùng script này như lệnh PowerShell nguyên trạng.

### 13.2. Kiểm tra stderr và exit code

Một ví dụ có mã thoát tùy chỉnh có thể được kiểm tra bằng shell:

~~~shell
set +e
java -cp out NormalizeInput >stdout.txt 2>stderr.txt
status=$?
set -e

test "$status" -eq 2
test ! -s stdout.txt
grep -F "ERROR: expected exactly one argument" stderr.txt
~~~

Đoạn này cố ý gọi chương trình không có argument. `set +e` chỉ tắt dừng ngay khi lệnh thất bại; sau khi lấy mã thoát thì bật lại `set -e`.

Trên PowerShell:

~~~powershell
java -cp out NormalizeInput 1> stdout.txt 2> stderr.txt
$exitCode = $LASTEXITCODE

if ($exitCode -ne 2) {
    throw "Expected exit code 2, got $exitCode"
}
~~~

Nếu cần so khớp nội dung file, dùng `Get-Content -Raw` và kiểm tra chính xác stdout/stderr theo quy ước newline của test. Đừng giả định output file có cùng line ending trên mọi hệ điều hành.

### 13.3. Ghi lại kết quả test cùng môi trường

Một test thất bại mà không có version/runtime context thường khó tái hiện. CI nên in thông tin JDK trước khi chạy:

~~~shell
java --version
javac --version
java -XshowSettings:properties -version
~~~

Với bài liên quan tool, in thêm `javadoc --version`, `jwebserver --version` và module list cần thiết. Chỉ lưu các property liên quan; tránh đưa toàn bộ biến môi trường có thể chứa secret vào log.

## 14. Quy trình thiết kế ví dụ cho từng chủ đề Java 18

| Chủ đề | Đầu vào cần ghi | Kết quả ổn định nên kiểm tra | Điều kiện cần ghi |
|---|---|---|---|
| JEP 400 — UTF-8 mặc định | Runtime options, file bytes, nội dung Unicode | `Charset.defaultCharset()`; round-trip khi chỉ định UTF-8 | JDK/runtime version, `file.encoding`, locale, terminal |
| JEP 408 — Simple Web Server | Root directory, request path, HTTP method | Status, body của file fixture, bind address | JDK tool version, `jdk.httpserver`, port, cwd |
| JEP 413 — Javadoc snippet | Source comment, doclet và command | Snippet xuất hiện trong HTML | `javadoc` version, standard/custom doclet, encoding |
| JEP 418 — Resolver SPI | Hostname hoặc provider fixture | Lookup thành công/loại lỗi; provider log khi test SPI | DNS/network, module/service config, cache, JVM mới |
| JEP 416 — Core reflection | Method, signature, quyền truy cập và target behavior | Wrapper/cause của `Method.invoke`; kết quả `MethodHandle` | JDK runtime, module access, lookup context |

### 14.1. UTF-8: test default và explicit encoding riêng nhau

Một test hỏi default charset phải in `Charset.defaultCharset()` và ghi JVM options. Một test file/giao thức nên dùng charset tường minh và fixture byte cố định. Không dùng một round-trip explicit UTF-8 để kết luận default charset của JVM.

### 14.2. Simple Web Server: test loopback và fixture cố định

Tạo file HTML có nội dung cố định, bind `127.0.0.1`, chọn port đã biết, gửi GET/HEAD và xác minh status/body. Nếu port bị chiếm, ghi đó là lỗi điều kiện môi trường hoặc chọn port khác theo cơ chế test. Không so sánh header thời gian.

### 14.3. Javadoc snippet: test HTML và test code riêng

Kiểm tra Javadoc có render snippet; compile/run đoạn code bằng một source/test riêng. Hai bước xác minh hai hành vi khác nhau.

### 14.4. Resolver SPI: kiểm soát provider và tránh IP cố định

Test DNS bình thường và test custom provider là hai ca khác nhau. Nếu test provider, dùng JVM mới và cấu hình service được kiểm soát. Không assert thứ tự provider hoặc một địa chỉ Internet cụ thể nếu hợp đồng không bảo đảm.

### 14.5. Reflection: assert wrapper và cause

Với `Method.invoke`, kiểm tra `InvocationTargetException` và cause. Với MethodHandle, kiểm tra ngoại lệ target trực tiếp và call-site type. Không suy ra hiệu năng hay cách tối ưu nội bộ từ kết quả một ví dụ chức năng.

## 15. Checklist review trước khi chia sẻ một ví dụ

- [ ] Mục đích và phạm vi được nêu trong một câu.
- [ ] Tên JDK/compiler/runtime được ghi riêng khi khác nhau.
- [ ] Đã ghi module, quyền truy cập hoặc tool cần thiết.
- [ ] Đầu vào có thể tái tạo và không chứa dữ liệu nhạy cảm.
- [ ] Thư mục làm việc và đường dẫn tương đối được xác định.
- [ ] Lệnh compile/run đầy đủ, bao gồm `--release`/encoding nếu liên quan.
- [ ] stdout, stderr và exit code được mô tả riêng.
- [ ] Ngoại lệ có loại, cause/wrapper và trigger condition.
- [ ] Output biến thiên theo DNS, OS, locale, thời gian hoặc vendor được đánh dấu.
- [ ] Không biến chi tiết triển khai thành hợp đồng API.
- [ ] Không tuyên bố Javadoc snippet tự chạy test.
- [ ] Không dùng JDK 18 hết hỗ trợ làm môi trường mặc định; ví dụ chạy trên JDK hiện đại còn được cập nhật.
- [ ] Cleanup cho file tạm và server/process đã được ghi.

## 16. Bài tập thực hành

### Bài 1 — Viết hồ sơ cho một ví dụ đầu vào đơn giản

Dùng `NormalizeInput.java`. Viết hồ sơ gồm command, cwd, argument, stdout, stderr, exit code cho ba ca: hợp lệ, thiếu argument và chuỗi trắng.

**Tiêu chí đạt:** Người khác có thể chạy lại và xác nhận cả ca thành công lẫn thất bại mà không cần hỏi thêm đầu vào.

### Bài 2 — Tách bốn loại encoding

Tạo file UTF-8 có ký tự `é`, chạy `Utf8FileCheck`, ghi default charset và encoding của terminal riêng.

**Tiêu chí đạt:** Giải thích được vì sao file round-trip đúng UTF-8 không tự chứng minh console cũng hiển thị đúng hoặc mọi API dùng default charset.

### Bài 3 — Ghi ngoại lệ reflection

Chạy `ReflectionExceptionCheck` và `MethodHandleExceptionCheck`. Ghi loại ngoại lệ quan sát được, wrapper/cause, method signature và runtime version.

**Tiêu chí đạt:** Phân biệt `InvocationTargetException` với ngoại lệ target được ném trực tiếp từ MethodHandle.

### Bài 4 — Tạo hồ sơ DNS có giới hạn

Chạy `ResolveHost` với hostname được phép truy cập. Ghi hostname, resolver/network context, một hoặc nhiều kết quả và loại lỗi nếu có.

**Tiêu chí đạt:** Không đóng đinh IP cụ thể; giải thích phép thử chưa chứng minh custom provider SPI đã được đăng ký.

### Bài 5 — Kiểm tra Javadoc và Simple Web Server

Tạo Javadoc từ `SnippetExample.java`, kiểm tra snippet trong HTML; sau đó phục vụ thư mục tài liệu bằng `jwebserver` trên loopback và gửi GET/HEAD.

**Tiêu chí đạt:** Tách kiểm tra render snippet khỏi compile/test code, và chỉ assert HTTP status/body ổn định.

## 17. Tài liệu chính thức

1. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi thay đổi default charset và các lưu ý tương thích.
2. [The Charset API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): hợp đồng `defaultCharset()` và charset chuẩn.
3. [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục tiêu và giới hạn của server tĩnh.
4. [The jwebserver Tool — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): bind address, port, directory và HTTP behavior.
5. [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): khả năng snippet của standard doclet.
6. [Javadoc Documentation Comment Specification — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html): cú pháp và xử lý documentation comment.
7. [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): resolver provider SPI.
8. [The InetAddressResolverProvider API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): hợp đồng lựa chọn provider.
9. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai reflection trong JDK 18.
10. [The Method API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html): hợp đồng `invoke` và `InvocationTargetException`.
11. [The MethodHandle API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invoke`, `invokeExact` và signature-polymorphic call.
12. [The javac Tool — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--release`, encoding và compile options.

**Kết quả cần đạt:** Mỗi ví dụ Java có thể được chạy lại với đầu vào, lệnh, kết quả, ngoại lệ và môi trường đã mô tả. Người đọc biết assertion nào dựa trên hợp đồng API, quan sát nào phụ thuộc runtime hoặc môi trường, và giới hạn nào chưa được kiểm chứng. Cách viết này giúp các ví dụ về Java 18 tiếp tục hữu ích khi chạy trên JDK hiện đại.
