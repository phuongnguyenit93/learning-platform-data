# Chạy ma trận kiểm chứng trên các JDK hiện đại đã chọn và ghi rõ hành vi phụ thuộc phiên bản

## 1. Mục tiêu của bài thực hành

Một chương trình chạy thành công trên một JDK chưa chứng minh rằng nó sẽ có cùng hành vi trên mọi JDK hiện đại. Có những đặc điểm được **hợp đồng API bảo đảm**, nhưng cũng có những giá trị phụ thuộc vào phiên bản, nhà cung cấp JDK, hệ điều hành, cấu hình module, class loader, mạng hoặc tham số khởi động.

Trong chương **Thực hành tổng hợp** của module Java 18, ta sẽ dựng một **ma trận kiểm chứng có thể tái lập** cho các chủ đề vẫn còn hữu ích: UTF-8 mặc định, Simple Web Server, snippet trong Javadoc, resolver SPI của `InetAddress`, reflection và `MethodHandle`. Trọng tâm của bài là **thực thi trên các JDK đã chọn, lưu chứng cứ và viết kết luận đúng mức**.

Sau bài này, bạn có thể:

1. Chọn ít nhất hai JDK hiện đại, ghi đúng phiên bản, vendor và cách khởi động của từng JDK.
2. Phân biệt **kỳ vọng theo hợp đồng** với **kết quả đã đo thực tế**.
3. Chạy các phép thử giống nhau trong JVM mới cho từng phiên bản, đồng thời kiểm soát biến môi trường.
4. Chẩn đoán sự khác nhau do API, module, hệ điều hành, class loader, cache hoặc chính sách của JDK.
5. Lập bảng báo cáo có trạng thái `PASS`, `FAIL`, `SKIP` và ghi rõ hành vi nào **phụ thuộc phiên bản/cấu hình**.

**Lưu ý về chứng cứ:** Các đầu ra trong bài chỉ là ví dụ hoặc kết quả kỳ vọng để người học đối chiếu. Bài viết không khẳng định đã thực sự chạy các lệnh trên máy của người học. Chỉ ghi `PASS` sau khi có kết quả thực tế từ JDK tương ứng.

## 2. Chọn ma trận JDK và cố định điều kiện thử nghiệm

Một lựa chọn dễ quản lý là **JDK 21** và **JDK 25**; có thể thêm bản JDK mới hơn đã cài trong môi trường của bạn. Hai JDK này cho phép kiểm chứng các API liên quan từ Java 18 trên những runtime hiện đại khác nhau.

| Trục so sánh | Cấu hình A | Cấu hình B | Cấu hình C (nếu có) |
| --- | --- | --- | --- |
| Runtime | JDK 21 | JDK 25 | Một JDK hiện đại khác đã cài |
| Nhà cung cấp | Ghi từ `java -version` | Ghi từ `java -version` | Ghi từ `java -version` |
| Hệ điều hành | Cố gắng giữ giống nhau | Cố gắng giữ giống nhau | Ghi chênh lệch nếu khác |
| `JAVA_HOME` / đường dẫn `java` | Đường dẫn tuyệt đối A | Đường dẫn tuyệt đối B | Đường dẫn tuyệt đối C |
| `javadoc` / `jwebserver` | Công cụ của A | Công cụ của B | Công cụ của C |
| Flags JVM | Ghi nguyên văn | Giữ tương đương hoặc ghi khác biệt | Ghi nguyên văn |
| Module/class path | Cùng fixture | Cùng fixture | Cùng fixture |

JDK 21 và JDK 25 là **ví dụ để lựa chọn**, không phải yêu cầu cứng. Nếu chỉ có một JDK, vẫn có thể chạy các phép thử, nhưng chưa thể kết luận điều gì về sự thay đổi giữa các phiên bản. Hãy ghi kết quả còn lại là `SKIP: JDK_NOT_INSTALLED`.

Để so sánh đúng, hãy cố định:

- **Cùng mã nguồn và dữ liệu đầu vào**, kể cả encoding của tệp thử nghiệm.
- **Cùng thư viện và cách đóng gói**; tránh vô tình đưa provider vào class path của một lượt chạy mà không có trong lượt khác.
- **Cùng chế độ chạy**: class path hoặc module path, loại HTTP, có hay không có proxy.
- **JVM mới** cho phép thử cần quan sát khởi tạo resolver hoặc cache; không giả định thay đổi cấu hình giữa chừng sẽ được áp dụng.
- **Phiên bản thực tế**: không chỉ ghi “Java 21”, mà còn ghi vendor, build và flags nếu các dữ kiện này có thể ảnh hưởng kết quả.

Với phép thử nhạy môi trường, việc hai JDK cho ra kết quả khác nhau **chưa đủ** để khẳng định nguyên nhân là thay đổi API. Cần kiểm tra những biến còn lại.

### Thu thập metadata trước khi chạy

Ví dụ trên Linux/macOS, thay các đường dẫn minh họa bằng đường dẫn JDK bạn thực sự có:

~~~bash
/opt/jdks/jdk-21/bin/java -version
/opt/jdks/jdk-25/bin/java -version

/opt/jdks/jdk-21/bin/java -XshowSettings:properties -version
/opt/jdks/jdk-25/bin/java -XshowSettings:properties -version
~~~

Trên Windows PowerShell:

~~~powershell
& 'C:\jdks\jdk-21\bin\java.exe' -version
& 'C:\jdks\jdk-25\bin\java.exe' -version

& 'C:\jdks\jdk-21\bin\java.exe' -XshowSettings:properties -version
& 'C:\jdks\jdk-25\bin\java.exe' -XshowSettings:properties -version
~~~

Từ output, ghi tối thiểu `java.version`, `java.vendor`, `java.vm.name`, `os.name`, `file.encoding`. Lệnh `-XshowSettings:properties` phục vụ kiểm tra cấu hình JVM; không cần đưa toàn bộ danh sách system properties vào báo cáo công khai vì một số property có thể chứa đường dẫn nội bộ.

**Kiểm tra đồng bộ công cụ:** Khi thử `javadoc` hoặc `jwebserver`, gọi tệp thực thi từ **cùng thư mục JDK** với `java` của hàng ma trận. Nếu dùng `java` của JDK 25 nhưng `javadoc` trên `PATH` lại thuộc JDK 21, phép so sánh không còn đáng tin.

## 3. Thiết kế ma trận: hợp đồng ổn định và biến phụ thuộc môi trường

Trước khi chạy, hãy phân loại kỳ vọng:

| Mã kiểm chứng | Chủ đề | Kỳ vọng theo hợp đồng còn áp dụng | Điều có thể thay đổi cần ghi |
| --- | --- | --- | --- |
| E01 | UTF-8 mặc định | Trên JDK từ 18, mặc định là UTF-8 trong cấu hình chuẩn | Flags mã hóa, cấu hình tương thích, môi trường và source encoding |
| E02 | Đọc Unicode | Đọc/ghi **tường minh** với `StandardCharsets.UTF_8` ổn định | File đầu vào, default charset nếu chọn decoder mặc định |
| E03 | Simple Web Server | Công cụ `jwebserver` có thể phục vụ tệp tĩnh cục bộ | Port bận, module/công cụ trong bản phân phối, chính sách mạng |
| E04 | Javadoc snippet | `{@snippet}` được hỗ trợ bởi doclet hiện đại | Cách trình bày HTML, tùy chọn Javadoc, cảnh báo theo build |
| E05 | `InetAddress` | API tra cứu tên còn tồn tại | IPv4/IPv6, DNS, hosts file, cache, mạng |
| E06 | Resolver SPI | Phát hiện `InetAddressResolverProvider` theo cơ chế service của JDK | Class path, module resolution, system loader, thời điểm khởi tạo |
| E07 | Reflection: field không sửa được | `static final` và `final` field trong record không được cấp quyền ghi bằng deep reflection | Quyền truy cập/module có thể thay đổi giai đoạn báo lỗi |
| E08 | Reflection: instance `final` thông thường | Kiểm chứng thực tế theo hợp đồng JDK đang dùng | Chính sách final-field mutation, flags, warnings, module |
| E09 | MethodHandle `asCollector` | Kiểu collector có số phần tử cố định | Sai `MethodType` hoặc kiểu call site dẫn đến lỗi |
| E10 | Ngoại lệ của method đích | `Method.invoke` bọc target exception; `invokeExact` truyền trực tiếp | Có thể có adapter/handler do ứng dụng tự thêm |

Các hàng có cột “thay đổi” không có nghĩa sẽ khác nhau giữa hai JDK. Chúng là **biến cần quan sát** trước khi kết luận. Nếu kết quả giống nhau, hãy ghi “không quan sát thấy khác biệt trong cấu hình thử nghiệm”, không khái quát thành “mọi JDK đều giống nhau”.

## 4. Tạo một chương trình thăm dò Java tự chứa

Tệp `MatrixProbe.java` dưới đây dùng API công khai của JDK, không đòi thư viện bên ngoài. Nó kiểm tra mã hóa, phân giải tên cục bộ, ranh giới ghi field bằng reflection, kiểu collector và sự khác biệt khi ngoại lệ được ném từ method đích.

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.InetAddress;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class MatrixProbe {

    private static final int FIXED = 7;

    private record Snapshot(int value) {}

    private static final class OrdinaryFinal {
        private final int value;
        OrdinaryFinal(int value) {
            this.value = value;
        }
    }

    @FunctionalInterface
    interface CheckedTest {
        void execute() throws Throwable;
    }

    static void test(String id, CheckedTest action) {
        try {
            action.execute();
            System.out.println(id + "=PASS");
        } catch (VirtualMachineError | ThreadDeath fatal) {
            throw fatal;
        } catch (Throwable error) {
            System.out.println(id + "=FAIL "
                    + error.getClass().getName()
                    + ": " + error.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.vendor="
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name="
                + System.getProperty("java.vm.name"));
        System.out.println("os.name="
                + System.getProperty("os.name"));
        System.out.println("file.encoding="
                + System.getProperty("file.encoding"));
        System.out.println("native.encoding="
                + System.getProperty("native.encoding"));
        System.out.println("defaultCharset="
                + Charset.defaultCharset());

        test("E01_E02_ENCODING", MatrixProbe::checkEncoding);
        test("E05_LOCALHOST", MatrixProbe::checkLocalhost);
        test("E07_STATIC_FINAL", MatrixProbe::checkStaticFinal);
        test("E07_RECORD_FINAL", MatrixProbe::checkRecordFinal);
        test("E08_ORDINARY_FINAL", MatrixProbe::observeOrdinaryFinal);
        test("E09_COLLECTOR", MatrixProbe::checkCollector);
        test("E10_EXCEPTION_PATH", MatrixProbe::checkExceptionPath);
    }

    static void checkEncoding() throws Exception {
        String expected = "Tiếng Việt: học Java";
        byte[] utf8 = expected.getBytes(StandardCharsets.UTF_8);

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(utf8))) {
            char[] buffer = new char[expected.length() + 8];
            int count = reader.read(buffer);
            String decoded = new String(buffer, 0, count);
            System.out.println("decodedWithDefault=" + decoded);
            System.out.println("roundTripWithDefault="
                    + expected.equals(decoded));
        }

        String explicit = new String(utf8, StandardCharsets.UTF_8);
        if (!expected.equals(explicit)) {
            throw new AssertionError("Explicit UTF-8 roundtrip failed");
        }
    }

    static void checkLocalhost() throws Exception {
        InetAddress[] addresses = InetAddress.getAllByName("localhost");
        if (addresses.length == 0) {
            throw new AssertionError("localhost returned no addresses");
        }
        System.out.println("localhost=" + Arrays.toString(addresses));
    }

    static void checkStaticFinal() throws Exception {
        Field field = MatrixProbe.class.getDeclaredField("FIXED");
        field.trySetAccessible();
        try {
            field.setInt(null, 8);
            throw new AssertionError("static final unexpectedly writable");
        } catch (IllegalAccessException expected) {
            System.out.println("staticFinal=WRITE_DENIED");
        }
    }

    static void checkRecordFinal() throws Exception {
        Field field = Snapshot.class.getDeclaredField("value");
        field.trySetAccessible();
        try {
            field.setInt(new Snapshot(3), 4);
            throw new AssertionError("record final unexpectedly writable");
        } catch (IllegalAccessException expected) {
            System.out.println("recordFinal=WRITE_DENIED");
        }
    }

    static void observeOrdinaryFinal() throws Exception {
        // Đây là phép quan sát tương thích, KHÔNG phải kỹ thuật cập nhật
        // trạng thái đối tượng dùng trong mã sản phẩm.
        Field field = OrdinaryFinal.class.getDeclaredField("value");
        OrdinaryFinal item = new OrdinaryFinal(1);
        boolean opened = field.trySetAccessible();
        System.out.println("ordinaryFinal.accessOpened=" + opened);

        if (!opened) {
            System.out.println("ordinaryFinal.result=ACCESS_DENIED");
            return;
        }

        try {
            field.setInt(item, 2);
            System.out.println("ordinaryFinal.result=WRITE_ACCEPTED");
        } catch (IllegalAccessException ex) {
            System.out.println("ordinaryFinal.result=WRITE_DENIED");
        }
    }

    static int sum(int[] values) {
        return Arrays.stream(values).sum();
    }

    static void checkCollector() throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                MatrixProbe.class, "sum",
                MethodType.methodType(int.class, int[].class));

        MethodHandle collect3 = target.asCollector(int[].class, 3);
        System.out.println("collector.type=" + collect3.type());

        int result = (int) collect3.invokeExact(1, 2, 3);
        if (result != 6) {
            throw new AssertionError("Wrong collected result: " + result);
        }

        try {
            int unexpected = (int) collect3.invokeExact(1, 2);
            throw new AssertionError("Wrong arity accepted: " + unexpected);
        } catch (WrongMethodTypeException expected) {
            System.out.println("collector.wrongArity=REJECTED");
        }
    }

    public static String fail(String value) throws IOException {
        throw new IOException("target-marker");
    }

    static void checkExceptionPath() throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findStatic(
                MatrixProbe.class, "fail",
                MethodType.methodType(String.class, String.class));

        try {
            String unexpected = (String) handle.invokeExact("x");
            throw new AssertionError("Target did not throw: " + unexpected);
        } catch (IOException expected) {
            System.out.println("handle.exception="
                    + expected.getClass().getSimpleName());
        }

        Method reflection = MatrixProbe.class.getMethod(
                "fail", String.class);
        try {
            reflection.invoke(null, "x");
            throw new AssertionError("Target did not throw");
        } catch (InvocationTargetException wrapper) {
            if (!(wrapper.getCause() instanceof IOException)) {
                throw new AssertionError(
                        "Wrong reflective cause", wrapper);
            }
            System.out.println("reflection.exception="
                    + wrapper.getClass().getSimpleName());
            System.out.println("reflection.cause="
                    + wrapper.getCause().getClass().getSimpleName());
        }
    }
}
~~~

### Tại sao mã thăm dò được viết theo cách này?

- `checkEncoding()` phân biệt bộ giải mã **mặc định** với việc dùng tường minh `StandardCharsets.UTF_8`.
- `checkLocalhost()` ghi nhận địa chỉ thực tế; **không ép** thứ tự IPv4/IPv6 phải giống nhau giữa các máy.
- Hai phép thử `E07` kiểm tra ràng buộc ghi **`static final`** và **field component của record** bằng `Field.setInt`.
- `E08` chỉ **quan sát** việc thay đổi instance field `final` của class thông thường; kết quả có thể phụ thuộc chính sách JDK. Không kiểm tra bằng cách đọc accessor/JIT sau khi sửa vì phép sửa field `final` sau khởi tạo không phải nền tảng cho logic ổn định.
- `E09` kiểm tra `asCollector` gom chính xác ba phần tử thành `int[]`, đồng thời thử call site thiếu đối số.
- `E10` chứng minh exception target được truyền trực tiếp qua `MethodHandle.invokeExact` và được bọc bởi `Method.invoke`.

`PASS` mà chương trình in ra chỉ có nghĩa **phép thử con hoàn tất mà không có exception ngoài dự kiến**. Ví dụ, hàng `E08_ORDINARY_FINAL=PASS` vẫn phải đọc thêm dòng `ordinaryFinal.result=...` để biết chính sách quan sát được. Tương tự, `roundTripWithDefault=false` là một quan sát cần phân tích flags và charset chứ không tự động làm hàm `checkEncoding` thất bại.

Không sử dụng mã này để viết lại field `final` trong sản phẩm; đây là fixture chẩn đoán chạy trên một đối tượng thử nghiệm mới.

## 5. Chạy cùng nguồn trên từng JDK

Có thể dùng **source-file mode** của trình chạy Java để mỗi JDK tự biên dịch nguồn cho lượt chạy của chính nó, tránh dùng nhầm class file biên dịch bằng JDK cao hơn.

Ví dụ Linux/macOS:

~~~bash
/opt/jdks/jdk-21/bin/java MatrixProbe.java
/opt/jdks/jdk-25/bin/java MatrixProbe.java
~~~

Ví dụ Windows PowerShell:

~~~powershell
& 'C:\jdks\jdk-21\bin\java.exe' .\MatrixProbe.java
& 'C:\jdks\jdk-25\bin\java.exe' .\MatrixProbe.java
~~~

Các đường dẫn là **minh họa**. Thay bằng đường dẫn có thật và chạy các lệnh trong thư mục chứa `MatrixProbe.java`. Không chọn một JDK bằng `JAVA_HOME` rồi dùng một `java` khác trên `PATH` mà không kiểm tra.

Lưu riêng cả **stdout** và **stderr** của từng lượt chạy. Stderr có thể chứa cảnh báo quan trọng, đặc biệt với các phép thử liên quan chính sách reflection ở JDK mới. Nếu một JDK chưa cài hoặc một phép thử không thể chạy do môi trường, ghi `SKIP` cùng lý do, không tự điền `PASS` theo dự đoán.

### Đọc kết quả có trách nhiệm

Một số dòng **kỳ vọng dạng cấu trúc**, không phải transcript đã được đo:

~~~text
defaultCharset=...
decodedWithDefault=...
roundTripWithDefault=...
E01_E02_ENCODING=PASS
localhost=[...]
E05_LOCALHOST=PASS
staticFinal=WRITE_DENIED
E07_STATIC_FINAL=PASS
recordFinal=WRITE_DENIED
E07_RECORD_FINAL=PASS
ordinaryFinal.accessOpened=...
ordinaryFinal.result=WRITE_ACCEPTED hoặc WRITE_DENIED
E08_ORDINARY_FINAL=PASS
collector.type=(int,int,int)int
collector.wrongArity=REJECTED
E09_COLLECTOR=PASS
handle.exception=IOException
reflection.exception=InvocationTargetException
reflection.cause=IOException
E10_EXCEPTION_PATH=PASS
~~~

Với một JDK có cấu hình mã hóa mặc định chuẩn từ Java 18 trở lên, `Charset.defaultCharset()` được kỳ vọng là UTF-8. Nếu quan sát khác, trước hết kiểm tra tham số khởi động, môi trường và cấu hình tương thích của bản JDK; đừng vội kết luận JDK không hỗ trợ JEP 400.

## 6. Kiểm chứng riêng công cụ Simple Web Server

`jwebserver` là công cụ dùng để phục vụ **tệp tĩnh** trong phạm vi phát triển và thử nghiệm. Để so sánh giữa JDK, hãy tạo cùng một thư mục `public` với nội dung đơn giản:

~~~text
public/
└── index.html
~~~

Nội dung `public/index.html`:

~~~html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Matrix probe</title></head>
<body>jdk-web-test</body>
</html>
~~~

Dùng executable `jwebserver` của một JDK, mở server trong **một terminal riêng**:

~~~bash
/opt/jdks/jdk-21/bin/jwebserver -b 127.0.0.1 -p 18080 -d public
~~~

Trong terminal khác, gửi GET:

~~~bash
curl -i http://127.0.0.1:18080/index.html
~~~

Sau khi thu thập kết quả, dừng server bằng `Ctrl+C` rồi **mới** chạy cùng phép thử bằng `jwebserver` của JDK còn lại, với cùng thư mục và port:

~~~bash
/opt/jdks/jdk-25/bin/jwebserver -b 127.0.0.1 -p 18080 -d public
~~~

Trên Windows, thay executable bằng đường dẫn tương ứng như `C:\jdks\jdk-21\bin\jwebserver.exe`; các tùy chọn `-b`, `-p`, `-d` có cùng vai trò. Nếu không chạy được vì port đã bận hoặc công cụ không có trong bản JDK cụ thể, ghi **`SKIP/ENVIRONMENT_BLOCKED`**, kiểm tra `jwebserver --help` của đúng JDK rồi chọn phương án thích hợp.

Mỗi lượt cần quan sát:

1. Công cụ có khởi động thành công và bind được `127.0.0.1:18080` không?
2. GET tới `/index.html` có trả thành công nội dung chứa `jdk-web-test` không?
3. Header và Content-Type thực tế là gì? Ghi lại để chẩn đoán, **không viết test cứng** dựa trên toàn bộ chuỗi header, thứ tự header hoặc thông điệp log.
4. Có khác biệt giữa các JDK không? Nếu có, tách biệt thay đổi thực thi và khác biệt cấu hình.

Không dùng Simple Web Server như một reverse proxy hay server ứng dụng HTTPS sản phẩm; phạm vi kiểm chứng ở đây là phục vụ tệp tĩnh cục bộ. Để tránh mở dịch vụ thử nghiệm ra mạng, bind vào loopback `127.0.0.1`.

## 7. Kiểm chứng riêng Javadoc snippet

`{@snippet}` từ Java 18 cho phép viết đoạn mã có cấu trúc trong Javadoc. Hãy tạo tệp `SnippetProbe.java`:

~~~java
/**
 * Ví dụ phép tính minh họa:
 *
 * {@snippet :
 * int answer = Math.addExact(20, 22);
 * System.out.println(answer);
 * }
 */
public class SnippetProbe {
    public int answer() {
        return 42;
    }
}
~~~

Chạy **`javadoc` của từng JDK** vào các thư mục output khác nhau:

~~~bash
/opt/jdks/jdk-21/bin/javadoc -d docs-21 SnippetProbe.java
/opt/jdks/jdk-25/bin/javadoc -d docs-25 SnippetProbe.java
~~~

Đối chiếu trang `SnippetProbe.html` sinh ra theo từng JDK. Mục tiêu ổn định là đoạn code được hiển thị như snippet hợp lệ, có các dòng `int answer = ...` và `System.out.println(answer);`.

**Không lấy toàn bộ HTML sinh ra làm golden file tuyệt đối** giữa hai JDK: cấu trúc DOM, class CSS, định dạng hoặc asset của doclet có thể thay đổi theo phiên bản. Nếu cần kiểm tra bằng công cụ tự động, hãy kiểm tra snippet có mặt về mặt ngữ nghĩa và không có lỗi doclet, đồng thời lưu riêng warnings.

Các snippet là nội dung tài liệu; trình `javadoc` không tự chứng minh đoạn code trong snippet đã chạy thành công. Nếu một snippet cần đồng bộ với mã thực thi, hãy có bài test mã Java độc lập; đừng đánh dấu `PASS` chỉ vì Javadoc render thành công rồi suy ra logic trong snippet đúng.

## 8. Kiểm chứng riêng cơ chế resolver SPI trong JVM mới

Phép thử `InetAddress.getAllByName("localhost")` kiểm tra được một luồng phân giải tên, nhưng **không chứng minh một provider tùy chỉnh đã được chọn**. Muốn kiểm chứng `InetAddressResolverProvider`, hãy triển khai một provider có dấu hiệu quan sát được rồi đóng gói đúng cơ chế service.

Ví dụ fixture `src/demo/MatrixResolverProvider.java`:

~~~java
package demo;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.stream.Stream;

public final class MatrixResolverProvider
        extends InetAddressResolverProvider {

    public MatrixResolverProvider() {}

    @Override
    public String name() {
        return "matrix-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host,
                    InetAddressResolver.LookupPolicy policy)
                    throws UnknownHostException {

                if (host.equalsIgnoreCase("matrix.test")) {
                    System.err.println("[matrix-resolver] " + host);
                    return Stream.of(InetAddress.getByAddress(
                            "matrix.test",
                            new byte[] {127, 0, 0, 1}));
                }
                return builtin.lookupByName(host, policy);
            }

            @Override
            public String lookupByAddress(byte[] address)
                    throws UnknownHostException {
                return builtin.lookupByAddress(address);
            }
        };
    }
}
~~~

Đây là fixture **chỉ dành cho một phép thử IPv4 cục bộ có kiểm soát**. Một resolver tổng quát phải tôn trọng đầy đủ `LookupPolicy`, lựa chọn IPv4/IPv6, chiều tra cứu ngược, đồng thời bảo đảm an toàn khi được gọi đồng thời. Khi không xử lý hostname đặc biệt, ví dụ ủy quyền cho resolver tích hợp qua `configuration.builtinResolver()`.

Đặt service descriptor tại:

~~~text
resources/META-INF/services/java.net.spi.InetAddressResolverProvider
~~~

Nội dung:

~~~text
demo.MatrixResolverProvider
~~~

Tạo ứng dụng thăm dò `DnsProbe.java`:

~~~java
import java.net.InetAddress;
import java.util.Arrays;

public class DnsProbe {
    public static void main(String[] args) throws Exception {
        System.out.println(Arrays.toString(
                InetAddress.getAllByName("matrix.test")));
    }
}
~~~

Với một JDK đã chọn, biên dịch, tạo JAR chứa cả class và service descriptor, rồi chạy trong **JVM mới**. Ví dụ kiểu lệnh trên Linux/macOS (tạo trước các thư mục `src` và `resources` như trên):

~~~bash
mkdir -p build/classes

/opt/jdks/jdk-21/bin/javac \
    -d build/classes src/demo/MatrixResolverProvider.java

/opt/jdks/jdk-21/bin/jar --create \
    --file build/matrix-resolver.jar \
    -C build/classes . \
    -C resources META-INF/services/java.net.spi.InetAddressResolverProvider

/opt/jdks/jdk-21/bin/java \
    -cp build/matrix-resolver.jar DnsProbe.java
~~~

Lặp lại bằng bộ `javac`, `jar` và `java` của JDK còn lại, tốt nhất trong thư mục build riêng hoặc sau khi dọn **chỉ artifact của fixture thử nghiệm** để không dùng nhầm JAR của lượt trước. Nếu chạy trên Windows, dấu phân cách class path cho nhiều mục là `;` thay vì `:`; ví dụ này chỉ có một JAR nên không phụ thuộc dấu phân cách.

Kỳ vọng khi provider được phát hiện và sử dụng:

~~~text
[matrix-resolver] matrix.test
[matrix.test/127.0.0.1]     # Dạng hiển thị tham khảo
~~~

Dòng output địa chỉ là **minh họa**; không cố định chuỗi `toString()` khi kiểm thử. Hãy so sánh bytes địa chỉ loopback và xác minh log provider có xuất hiện. Nếu không thấy log, xem lại JAR service descriptor, class path, lớp provider, thời điểm khởi tạo resolver và có provider khác được phát hiện trước hay không.

`InetAddress` sử dụng cơ chế `ServiceLoader` trong phạm vi **system class loader** để phát hiện provider. Việc một plugin nhìn thấy class provider qua custom class loader hoặc TCCL chưa chứng minh `InetAddress` sẽ sử dụng provider đó. Đặc biệt, chạy một `ServiceLoader.load(...)` riêng và in ra class provider chỉ kiểm tra **discovery** ở lời gọi ấy; cần có một lượt tra cứu bằng `InetAddress` để kiểm chứng end-to-end.

Không đổi provider bằng cách thêm JAR vào một loader riêng sau khi JVM đã thiết lập resolver rồi coi đó là phép thử tương đương. Hãy khởi động JVM mới cho từng cấu hình để kiểm soát vòng đời và cache.

## 9. Phân loại hành vi phụ thuộc phiên bản/cấu hình

Sau khi có kết quả, viết mỗi phát hiện theo một trong ba mức:

**Mức A — Hợp đồng API ổn định.** Ví dụ: `MethodHandle.asCollector(int[].class, 3)` tạo adapter nhận ba giá trị `int` thành phần; `Method.invoke` bọc exception từ method đích trong `InvocationTargetException`. Nếu phép thử không đúng kỳ vọng, kiểm tra mã và cấu hình trước khi gắn nhãn thay đổi phiên bản.

**Mức B — Hành vi có điều kiện đã biết.** Ví dụ: UTF-8 là mặc định từ Java 18 theo cấu hình chuẩn, nhưng có thể có chế độ/flag tương thích ảnh hưởng default charset; `InetAddress` có kết quả phụ thuộc DNS/hosts/cache; Javadoc HTML có thể thay đổi theo doclet. Kết luận phải ghi điều kiện.

**Mức C — Chính sách hoặc kết quả thực tế cần xác minh trên JDK đang chạy.** Ví dụ: phép sửa instance field `final` thông thường bằng deep reflection có thể chịu ràng buộc, cảnh báo hoặc từ chối tùy JDK và flags. Chỉ ghi chính sách cụ thể khi đã quan sát kết quả **và** kiểm tra tài liệu chính thức của JDK mục tiêu.

Để tránh nhầm lẫn, dùng những câu có phạm vi:

> “Với JDK [vendor/build] trên [OS], khởi động bằng [flags], `ordinaryFinal.result` là [giá trị]; stderr có [cảnh báo/không có cảnh báo]. Phép thử này không xác lập quyền ghi instance `final` trên mọi JDK.”

Không viết:

> “Java luôn cho phép sửa `final` bằng reflection”, hoặc “Từ Java X, mọi trường hợp sửa `final` đều bị cấm”, khi chưa đối chiếu đúng chính sách và ngoại lệ của bản JDK đó.

Tương tự, một lần `InetAddress.getAllByName("localhost")` trả về IPv6 trước IPv4 không chứng minh “JDK mới đổi thứ tự DNS” nếu cấu hình mạng, `hosts` hoặc flags chưa được giữ giống nhau.

## 10. Mẫu bảng kết quả để điền sau khi chạy

Bảng sau **cố ý để trống ô kết quả**. Hãy điền đúng dữ liệu đo được, không sao chép các ví dụ output thành kết quả thật.

| Test ID | JDK 21: thực đo | JDK 25: thực đo | JDK khác: thực đo | Mức phụ thuộc cần đánh giá |
| --- | --- | --- | --- | --- |
| E01 Default charset | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | Flags/runtime |
| E02 Unicode roundtrip | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | Charset và dữ liệu |
| E03 `jwebserver` GET | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | Môi trường/CLI |
| E04 `javadoc` snippet | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | Doclet/HTML |
| E05 `localhost` | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | OS/DNS/cache |
| E06 Resolver SPI provider | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | Discovery/config |
| E07 `static final`/record field | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | Hợp đồng reflection/quyền |
| E08 Instance `final` field | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | Chính sách JDK/flags |
| E09 `asCollector` | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | MethodType/call site |
| E10 Exception target | _Chưa chạy_ | _Chưa chạy_ | _Chưa chạy_ | API gọi/adapter |

Đối với một hàng, ghi tối thiểu: `status`, `observedValue` hoặc exception, `stderrWarning` (nếu có), `JDK build` và `evidence`. Nếu chưa thử, để `NOT_RUN`; nếu chưa cài JDK, ghi `SKIP:JDK_NOT_INSTALLED`; nếu test thất bại vì port bận, ghi `BLOCKED:PORT_IN_USE`. Không ép mọi kết quả thành nhị phân pass/fail.

Ví dụ cấu trúc ghi chứng cứ cho một test, các giá trị trong ngoặc vuông sẽ được người thực hành thay sau khi chạy:

~~~yaml
testId: E08
jdk: "[java.version + java.vendor + build]"
os: "[os.name + os.arch]"
command: "[lệnh đã chạy, gồm flags]"
modulePath: "[cấu hình nếu có]"
expectedContract: "Quan sát chính sách ghi final instance"
observedResult: "[WRITE_ACCEPTED | WRITE_DENIED | ACCESS_DENIED]"
stderrWarning: "[nguyên văn cảnh báo liên quan, nếu có]"
status: "[PASS | FAIL | SKIP | BLOCKED]"
evidence: "[đường dẫn log/ghi chú]"
conclusion: "[mô tả điều kiện và phạm vi kết luận]"
~~~

Cấu trúc này chỉ là mẫu trình bày báo cáo; không cần sửa metadata YAML của bài học để lưu kết quả. Trong dự án thực tế, nên lưu evidence của thí nghiệm vào nơi quản lý test thích hợp.

## 11. Điều tra khi hai JDK cho kết quả khác nhau

Dùng quy trình điều tra theo thứ tự:

1. **Xác minh đúng executable** cho cả `java`, `javac`, `javadoc`, `jwebserver`. Ghi build và vendor.
2. **Kiểm tra nguồn/bytecode/fixture** có giống nhau không. Nếu một lượt biên dịch bằng JDK mới rồi chạy bytecode ấy bằng JDK cũ, lỗi `UnsupportedClassVersionError` không chứng minh API nghiệp vụ đã thay đổi.
3. **Kiểm tra flags và môi trường**, nhất là `file.encoding`, module path, class path, proxy, IPv4/IPv6 và chính sách reflection.
4. **Phân biệt lỗi giai đoạn**: biên dịch, startup, lookup, adaptation, method target hay network. Ghi exception và cause chain thay vì chỉ dòng cuối.
5. **Lặp lại trong JVM mới** với cấu hình đã cố định nếu liên quan resolver, cache, class loading hoặc trạng thái tĩnh.
6. **Đối chiếu tài liệu của chính phiên bản JDK** trước khi tuyên bố thay đổi hành vi được đặc tả. Khi chưa đủ chứng cứ, đánh dấu `UNRESOLVED` thay vì đoán.

Bảng gợi ý xử lý:

| Triệu chứng | Đầu mối cần xem | Kết luận chưa được phép rút ra |
| --- | --- | --- |
| `Charset.defaultCharset()` khác nhau | Flags, vendor, runtime config | “UTF-8 mặc định đã bị loại bỏ” |
| `jwebserver` không bind được | Port, firewall, executable, loopback | “API HTTP đổi giữa hai JDK” |
| Javadoc HTML khác | Phiên bản doclet và style output | “Snippet code bị đổi ý nghĩa” |
| Resolver provider không có log | System loader, service descriptor, module resolution, cache | “JDK bỏ hỗ trợ resolver SPI” |
| `localhost` đổi thứ tự IP | IPv4/IPv6, hosts, network, lookup policy | “Java đổi thuật toán DNS” |
| Reflection `final` cảnh báo hoặc bị từ chối | Quyền module, chính sách final-field mutation | “Mọi `final` đều hành xử giống nhau” |
| `WrongMethodTypeException` | `handle.type()`, kiểu call site | “Method đích đã chạy và ném lỗi” |
| `InvocationTargetException` chỉ xuất hiện ở reflection | Cơ chế `Method.invoke` | “MethodHandle đã nuốt exception” |

## 12. Tiêu chí hoàn thành bài thực hành

Một báo cáo đủ kiểm chứng phải có:

- **Ít nhất hai môi trường JDK có thông tin nhận dạng chính xác**, hoặc ghi rõ điều kiện còn thiếu khiến chưa thể so sánh.
- **Mỗi hàng ma trận có kết quả đo thật** hoặc nhãn `SKIP/BLOCKED/NOT_RUN` có lý do.
- **Tách kỳ vọng hợp đồng khỏi quan sát**; ghi sự khác biệt của lỗi, cảnh báo và giá trị trả về nếu có.
- **Bằng chứng phù hợp từng loại test**: stdout/stderr, HTTP response, Javadoc output, log provider hoặc exception/cause chain.
- **Chú thích phụ thuộc phiên bản/cấu hình** cho hàng mã hóa, resolver, reflection và công cụ.
- **Kết luận với phạm vi giới hạn**: nêu JDK, flags, OS, fixture và phép thử, tránh ngoại suy sang mọi runtime.
- **Không đưa kỹ thuật cũ thiếu bảo đảm vào mã sản phẩm** chỉ để khiến phép thử thành công: không vô hiệu hóa TLS/JPMS, không dựa vào sửa `final` sau khởi tạo, không dùng API nội bộ làm đường vòng.

### Câu hỏi tự đánh giá

1. Vì sao “chạy trên JDK 21 và JDK 25” chưa đủ nếu `javac`, `java` hoặc flags của hai lượt không tương ứng?
2. Khi `E01` cho charset khác UTF-8, cần kiểm tra những điều kiện nào trước khi kết luận?
3. Vì sao việc `localhost` trả về thứ tự IPv4/IPv6 khác nhau không phải bằng chứng độc lập rằng API `InetAddress` đã thay đổi?
4. `trySetAccessible() == true` có đồng nghĩa có thể ghi `static final` hoặc field của record không?
5. Tại sao một phép thử `E08_ORDINARY_FINAL=PASS` vẫn cần ghi `ordinaryFinal.result`?
6. Vì sao `WrongMethodTypeException` của collector không nên được xem là exception của method đích?
7. Khi so sánh Javadoc sinh bởi hai JDK, vì sao nên kiểm tra snippet có mặt về ngữ nghĩa thay vì so toàn bộ HTML?
8. Vì sao resolver SPI phải được thử trong JVM mới và cần quan sát log provider cùng phép gọi `InetAddress`?
9. Khi một lượt không chạy được do thiếu JDK hoặc thiếu công cụ, nên điền trạng thái gì?
10. Thế nào là một kết luận “phụ thuộc phiên bản” có đủ chứng cứ?

## 13. Ghi nhớ

Ma trận kiểm chứng có giá trị khi **mỗi phép thử có hợp đồng rõ ràng, được chạy trên đúng JDK và có chứng cứ thực đo**. Với Java 18 và các JDK hiện đại, hãy tiếp tục dùng những API công khai vẫn được hỗ trợ: UTF-8 mặc định và charset tường minh, `jwebserver` cho nhu cầu tĩnh cục bộ, `{@snippet}` trong Javadoc, resolver SPI, reflection theo ranh giới module và `MethodHandle` với `MethodType` chính xác.

Khi kết quả khác nhau, ghi rõ **phiên bản/vendor JDK, flags, môi trường và điều kiện phép thử**. Chỉ gọi đó là khác biệt hành vi phụ thuộc phiên bản sau khi đã loại trừ nguyên nhân từ cấu hình hoặc fixture, đồng thời đối chiếu hợp đồng JDK tương ứng.
