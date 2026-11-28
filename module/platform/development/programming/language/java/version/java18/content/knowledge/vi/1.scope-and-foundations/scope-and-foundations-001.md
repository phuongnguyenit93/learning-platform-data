# Các thay đổi bền vững từ Java 18: UTF-8, Simple Web Server, Javadoc snippet, resolver SPI và reflection

> **Chương:** Phạm vi và nền tảng  
> **Phạm vi:** Những thay đổi được đưa vào JDK 18 và vẫn có giá trị trên JDK hiện đại; kiểm chứng hành vi bằng hợp đồng API thay vì dựa vào chi tiết triển khai của một bản JDK.

## 1. Bối cảnh và kết quả học tập

Java 18 là bản phát hành không thuộc chu kỳ hỗ trợ dài hạn (non-LTS), nhưng một số thay đổi của nó đã trở thành một phần ổn định của hệ sinh thái Java. Khi học trên JDK hiện đại, cần phân biệt **phiên bản giới thiệu tính năng** với **phiên bản đang dùng**. Bài này tập trung vào năm thay đổi có ích dài hạn:

| JEP trong Java 18 | Chủ đề | Điều tiếp tục có ích |
|---|---|---|
| [JEP 400](https://openjdk.org/jeps/400) | UTF-8 by Default | Hành vi mặc định của nhiều API chuyển đổi ký tự và cách kiểm soát charset khi trao đổi dữ liệu |
| [JEP 408](https://openjdk.org/jeps/408) | Simple Web Server | Dựng máy chủ HTTP tĩnh phục vụ phát triển, kiểm thử và tài liệu cục bộ |
| [JEP 413](https://openjdk.org/jeps/413) | Code Snippets in Java API Documentation | Viết ví dụ trong Javadoc dễ đọc, có thể gắn với mã nguồn kiểm thử |
| [JEP 418](https://openjdk.org/jeps/418) | Internet-Address Resolution SPI | Thay thế hoặc bọc bộ phân giải tên của `InetAddress` qua provider |
| [JEP 416](https://openjdk.org/jeps/416) | Reimplement Core Reflection with Method Handles | Hiểu hợp đồng reflection khi JDK dùng MethodHandle bên trong và chọn đúng API cho nhu cầu |

Đây là các thay đổi **đã được phát hành chính thức** trong Java 18, không phải cú pháp preview cần bật cờ. Nội dung dưới đây cố ý không đi sâu vào các thử nghiệm hoặc cơ chế đã hết giá trị thực tế. Những ví dụ đặt mục tiêu chạy trên JDK 18 trở lên, trừ khi ghi rõ điều kiện khác.

Sau bài này, người học có thể:

1. Dự đoán và kiểm chứng charset mặc định, đồng thời đọc/ghi dữ liệu với charset rõ ràng.
2. Khởi chạy `jwebserver` để phục vụ thư mục tĩnh trên loopback và biết giới hạn sử dụng.
3. Viết `{@snippet}` nội tuyến hoặc lấy từ tệp ngoài trong Javadoc.
4. Giải thích luồng hoạt động của `InetAddressResolverProvider`, bao gồm fallback và phạm vi tác động.
5. Phân biệt `Method.invoke` với `MethodHandle.invokeExact` về kiểu tham số, quyền truy cập và lỗi.

## 2. UTF-8 mặc định: JEP 400

### 2.1. Tại sao thay đổi này cần thiết?

Trước Java 18, charset mặc định của JVM thường phụ thuộc hệ điều hành và cấu hình vùng. Cùng đoạn mã `new String(bytes)` có thể cho kết quả khác nhau khi chạy trên hai máy nếu không chỉ rõ charset. Từ JDK 18, **charset mặc định của các API Java SE sử dụng default charset thông thường là UTF-8**, trừ khi cấu hình JVM yêu cầu hành vi tương thích được hỗ trợ.

Ví dụ kiểm tra trực tiếp:

~~~java
import java.nio.charset.Charset;

public class CharsetCheck {
    public static void main(String[] args) {
        System.out.println("default = " + Charset.defaultCharset());
        System.out.println("file.encoding = " + System.getProperty("file.encoding"));
        System.out.println("native.encoding = " + System.getProperty("native.encoding"));
    }
}
~~~

Trong cấu hình JDK 18+ mặc định, `Charset.defaultCharset()` trả về `UTF-8`. `native.encoding` mô tả charset của môi trường bản địa mà JDK phát hiện; nó **có thể khác** UTF-8. Thuộc tính này dùng để quan sát môi trường, không phải nút chuyển đổi charset có hiệu lực khi gọi `System.setProperty`.

Một số API chịu tác động vì **không truyền charset**:

- `new String(byte[])`, `String.getBytes()`.
- `new InputStreamReader(input)`, `new OutputStreamWriter(output)`.
- `FileReader` và `FileWriter` khi dùng overload không chỉ định charset.
- Các API đọc/ghi văn bản khác có hợp đồng sử dụng default charset.

Đọc hợp đồng của từng API trước khi suy luận: ví dụ `Files.readString(path)` và `Files.newBufferedReader(path)` đã quy định UTF-8 cho overload không truyền charset; JEP 400 không làm thay đổi quy định vốn có đó.

### 2.2. Quy tắc bền vững: mã hóa phải là một phần của hợp đồng dữ liệu

Một tệp CSV gửi cho hệ thống khác, một payload HTTP hoặc dữ liệu xuất nhập phải ghi rõ encoding. Không nên dựa vào việc máy chạy hiện đang dùng UTF-8, vì dữ liệu đầu vào có thể được tạo ở thời điểm hoặc hệ thống khác.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8File {
    public static void main(String[] args) throws Exception {
        Path file = Path.of("greeting.txt");
        String original = "Xin chào, Hà Nội 👋";

        Files.writeString(file, original, StandardCharsets.UTF_8);
        String restored = Files.readString(file, StandardCharsets.UTF_8);

        if (!original.equals(restored)) {
            throw new AssertionError("Dữ liệu bị thay đổi");
        }
        System.out.println(restored);
    }
}
~~~

Trong ví dụ này, encoding là một phần nhìn thấy được của giao diện đọc/ghi. Nếu bắt buộc đọc dữ liệu cũ theo charset khác, hãy dùng đúng charset ấy, ví dụ `Charset.forName("windows-1258")` **chỉ khi biết chắc định dạng đầu vào thực sự sử dụng encoding đó**; không tự đoán từ ngôn ngữ của nội dung.

Cần phân biệt:

| Trường hợp | Điều cần hiểu |
|---|---|
| `Charset.defaultCharset()` | Bình thường là UTF-8 trên JDK 18+ |
| `StandardCharsets.UTF_8` | Giá trị UTF-8 cố định, độc lập với default charset |
| `System.out`, `System.err` và console | Encoding của thiết bị đầu cuối có thể có quy tắc riêng; không suy ra chắc chắn chỉ từ `Charset.defaultCharset()` |
| `Properties.load(InputStream)` | Có hợp đồng ISO-8859-1 riêng; không đổi thành UTF-8 theo JEP 400 |
| Dữ liệu từ mạng hoặc thư viện bên ngoài | Tuân theo giao thức hoặc hợp đồng của từng API, không tự động được “chuyển sang UTF-8” |
| Đường dẫn tệp và tên tệp | Là chủ đề riêng của hệ điều hành/file system, không đồng nhất với charset mặc định để đọc nội dung tệp |

### 2.3. Kiểm chứng khi nâng cấp ứng dụng cũ

Trên JDK 18+, hai giá trị được tài liệu JDK hỗ trợ cho cờ khởi động `file.encoding` là `UTF-8` và `COMPAT`:

~~~shell
java -Dfile.encoding=UTF-8 CharsetCheck
java -Dfile.encoding=COMPAT CharsetCheck
~~~

`COMPAT` nhằm tái hiện cách chọn default charset theo môi trường như ở JDK 17 trở về trước. Dùng nó để **điều tra và chuyển đổi hệ thống cũ**, không biến nó thành phụ thuộc mới trong ứng dụng. Thiết lập property lúc khởi động JVM; đừng kỳ vọng thay đổi `System.setProperty("file.encoding", ...)` khi chương trình đang chạy sẽ thay đổi nhất quán hành vi các API.

Với mã nguồn Java được lưu bằng UTF-8, có thể khai báo encoding rõ ràng cho trình biên dịch:

~~~shell
javac -encoding UTF-8 CharsetCheck.java
java CharsetCheck
~~~

**Ví dụ thực tế:** Một hệ thống nhập CSV cũ do công cụ Windows tạo ra. Sau nâng JDK, ký tự có dấu bị lỗi. Hãy xác định charset của tệp nguồn từ hệ thống xuất, viết phép thử với bộ dữ liệu có tiếng Việt, sau đó chọn charset rõ ràng tại điểm đọc. Không giải quyết bằng cách thay default charset toàn bộ JVM vì có thể ảnh hưởng các luồng dữ liệu khác.

## 3. Simple Web Server: JEP 408

### 3.1. Dựng máy chủ tĩnh trong vài giây

`jwebserver` là công cụ đi kèm JDK để phục vụ **tệp tĩnh** trong một thư mục. Công cụ thích hợp khi muốn mở nhanh bộ tài liệu HTML, kiểm tra tài nguyên CSS/JavaScript, hoặc tạo endpoint tĩnh cho thao tác thử nghiệm.

Giả sử thư mục `public/` đã tồn tại và chứa `index.html`:

~~~text
project/
└── public/
    ├── index.html
    └── style.css
~~~

Tại thư mục `project/`, chạy:

~~~shell
jwebserver -d public -p 8000 -b 127.0.0.1
~~~

Sau đó truy cập `http://127.0.0.1:8000/` hoặc kiểm tra:

~~~shell
curl -i http://127.0.0.1:8000/index.html
~~~

Mặc định, khi không chỉ định cờ, máy chủ phục vụ thư mục hiện hành, dùng cổng `8000` và bind trên loopback (`127.0.0.1` hoặc `::1` tùy môi trường). Dừng bằng `Ctrl+C`. Các cờ thông dụng:

| Cờ | Tác dụng |
|---|---|
| `-d` / `--directory` | Chọn thư mục gốc để phục vụ |
| `-p` / `--port` | Chọn cổng HTTP |
| `-b` / `--bind-address` | Chọn địa chỉ lắng nghe |
| `-o none\|info\|verbose` | Chọn mức ghi log |
| `--help` | Hiển thị hướng dẫn của JDK đang dùng |

### 3.2. Phạm vi đúng của máy chủ

`jwebserver` chỉ phục vụ HTTP/1.1 (không hỗ trợ HTTPS hay HTTP/2 trong công cụ này), tập trung vào `GET` và `HEAD`. Nó trả nội dung tệp, ưu tiên tệp index cho thư mục nếu có, hoặc có thể hiển thị danh sách thư mục. Tệp ẩn và symlink không được liệt kê/phục vụ theo hợp đồng công cụ.

Điều này dẫn tới một số quyết định thực tế:

- Để demo giao diện tĩnh hoặc kiểm tra tài liệu API tại máy cá nhân: **phù hợp**.
- Để triển khai ứng dụng web có xác thực, TLS, routing nghiệp vụ, giới hạn tải và vận hành production: **không phù hợp**; cần máy chủ và kiến trúc được thiết kế cho mục đích đó.
- Khi truyền `-b 0.0.0.0`, máy chủ có thể nhận truy cập từ mạng ngoài máy: cần biết chính xác nội dung thư mục được chia sẻ. Với thử nghiệm cục bộ, dùng loopback.

Không nên đặt khóa bí mật, tệp cấu hình nhạy cảm hoặc dữ liệu khách hàng trong thư mục được phục vụ.

### 3.3. Dùng API Java để tạo máy chủ

Trong module `jdk.httpserver` có lớp `com.sun.net.httpserver.SimpleFileServer`. Đây là API dùng được trên JDK hiện đại khi cần điều khiển máy chủ từ chương trình:

~~~java
import com.sun.net.httpserver.SimpleFileServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Path;

public class StaticPreview {
    public static void main(String[] args) {
        var address = new InetSocketAddress(
                InetAddress.getLoopbackAddress(), 8000);
        var root = Path.of("public").toAbsolutePath();

        var server = SimpleFileServer.createFileServer(
                address, root, SimpleFileServer.OutputLevel.INFO);
        server.start();
        System.out.println("Preview: http://127.0.0.1:8000/");
    }
}
~~~

Thư mục `public` phải tồn tại, đọc được, và đường dẫn truyền cho API phải là **đường dẫn tuyệt đối**. Nếu chạy trong dự án Java có `module-info.java`, thêm `requires jdk.httpserver;`. Trong ví dụ này, tiến trình giữ máy chủ hoạt động cho đến khi dừng; khi tích hợp trong ứng dụng có vòng đời riêng, cần quản lý `server.stop(delay)` phù hợp.

`SimpleFileServer` cũng có các factory cho `HttpHandler` và `Filter`; khi muốn xây HTTP endpoint thực sự, có thể dùng các thành phần `com.sun.net.httpserver` phù hợp với yêu cầu. Không suy ra rằng `jwebserver` tự trở thành framework web chỉ vì có thể mở rộng ở cấp API.

## 4. Code snippet trong Javadoc: JEP 413

### 4.1. Viết ví dụ dễ bảo trì bằng `{@snippet}`

Trước đây ví dụ nhiều dòng trong Javadoc thường phải kết hợp `<pre>` và `{@code}`. Từ Java 18, standard doclet hiểu tag `{@snippet}`, cho phép trình bày mã có định dạng và tùy chọn nhấn mạnh, liên kết hoặc tái sử dụng mã ở tệp ngoài.

Ví dụ snippet nội tuyến:

~~~java
/**
 * Chuẩn hóa nhãn hiển thị.
 *
 * Ví dụ:
 * {@snippet lang="java" :
 *     String label = "  Java 18  ".strip();
 *     System.out.println(label); // Java 18
 * }
 */
public final class Labels {
    private Labels() {}

    public static String normalize(String value) {
        return value.strip();
    }
}
~~~

Khi chạy `javadoc` bằng JDK 18+, standard doclet trình bày ví dụ như một đoạn mã. Phần sau dấu `:` là thân snippet; chú ý cách viết thụt lề để kết quả rõ ràng.

**Quan trọng:** `javadoc` hiển thị và phân tích cấu trúc snippet, nhưng **không tự biên dịch hoặc chạy kiểm thử đoạn mã**. Một ví dụ hiển thị đẹp vẫn có thể sai về kiểu, import hoặc đầu ra nếu người viết không kiểm thử.

### 4.2. Dùng mã từ tệp ngoài

Với ví dụ dài hoặc cần biên dịch trong bộ test, đặt mã trong thư mục `snippet-files` của package hoặc trỏ đến thư mục ngoài bằng `--snippet-path`.

Ví dụ cấu trúc:

~~~text
src/
└── demo/
    ├── Labels.java
    └── snippet-files/
        └── LabelExamples.java
~~~

Trong Javadoc của `Labels.java`:

~~~java
/**
 * Ví dụ rút gọn từ mã nguồn:
 * {@snippet class="LabelExamples" region="strip-label"}
 */
~~~

Trong `snippet-files/LabelExamples.java`:

~~~java
public class LabelExamples {
    public static void main(String[] args) {
        // @start region="strip-label"
        String label = "  Java 18  ".strip();
        System.out.println(label);
        // @end region="strip-label"
    }
}
~~~

Vùng `strip-label` là phần xuất hiện trong Javadoc. Mã nguồn ngoài có thể được biên dịch và kiểm thử riêng để giảm tình trạng tài liệu mô tả khác hành vi thực tế. Với tệp ngoài không phải Java, dùng `file="name.ext"` thay vì `class="..."`. `--snippet-path` chỉ đường dẫn cho công cụ Javadoc tìm các snippet ngoài khi chúng không ở `snippet-files` cùng package.

Ngoài việc chọn `region`, markup comment hỗ trợ `@highlight`, `@replace`, `@link` để làm rõ ý định minh họa. Chỉ dùng khi giúp người đọc hiểu API, và nên xem lại HTML Javadoc sau khi tạo.

### 4.3. Hợp đồng tài liệu và kiểm chứng

Một ví dụ Javadoc tốt nên có:

1. Đầu vào đủ cụ thể, nhất là trường hợp Unicode, `null` hoặc ngoại lệ.
2. Đầu ra đúng với phiên bản JDK mục tiêu.
3. Import, điều kiện khởi tạo và quyền truy cập rõ ràng.
4. Kiểm thử riêng nếu snippet thể hiện quy tắc nghiệp vụ hoặc xử lý dữ liệu quan trọng.

**Ví dụ thực tế:** Thư viện cung cấp hàm chuẩn hóa chuỗi. Snippet nên lấy từ ví dụ có test so sánh kết quả, để một lần sửa API không làm tài liệu lỗi thời.

## 5. SPI phân giải tên Internet: JEP 418

### 5.1. Resolver là gì?

`InetAddress` hỗ trợ tra cứu tên máy thành địa chỉ IP và tra cứu ngược. Với JEP 418, Java cung cấp `java.net.spi.InetAddressResolver` và `InetAddressResolverProvider` để chương trình có thể đăng ký bộ phân giải tùy biến.

Luồng ý tưởng:

~~~text
Ứng dụng gọi InetAddress.getByName("demo.test")
             |
             v
       Resolver chung của JVM
             |
      +------+------+
      |             |
  Có provider?      Không
      |             |
 Resolver do        Resolver
 provider tạo       mặc định
      |
  IP hoặc UnknownHostException
~~~

Một tiến trình JVM dùng **một resolver cấp hệ thống** do cơ chế provider chọn. Provider được tìm qua `ServiceLoader` dùng system class loader khi lần phân giải đầu tiên xảy ra sau khi VM khởi tạo đầy đủ. Nếu có nhiều provider, **thứ tự tìm thấy là chi tiết triển khai**; không dựa vào “provider A luôn thắng”. Nếu không có provider, Java dùng resolver tích hợp của JDK. Nếu khởi tạo provider thất bại, lỗi có thể được truyền tới lời gọi phân giải đã kích hoạt việc khởi tạo.

Đây là SPI cho **hành vi tra cứu thông qua `InetAddress` trong JVM**, không phải cơ chế cấu hình lại DNS trên toàn hệ điều hành.

### 5.2. Một provider tối thiểu để minh họa

Provider sau trả loopback cho tên `demo.test` và ủy quyền các tên khác cho resolver tích hợp. Nó chỉ nhằm làm rõ hợp đồng SPI trong kiểm thử.

~~~java
package example.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.stream.Stream;

public final class DemoResolverProvider extends InetAddressResolverProvider {
    @Override
    public String name() {
        return "demo-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver builtIn = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy) throws UnknownHostException {
                if ("demo.test".equalsIgnoreCase(host)) {
                    return Stream.of(InetAddress.getByAddress(
                            host, new byte[] {127, 0, 0, 1}));
                }
                return builtIn.lookupByName(host, policy);
            }

            @Override
            public String lookupByAddress(byte[] address)
                    throws UnknownHostException {
                return builtIn.lookupByAddress(address);
            }
        };
    }
}
~~~

Để công bố provider trong **module có tên**, `module-info.java` có thể khai báo:

~~~java
module example.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with example.resolver.DemoResolverProvider;
}
~~~

Nếu đóng gói theo **classpath**, đăng ký với tệp `META-INF/services/java.net.spi.InetAddressResolverProvider`, nội dung là tên đầy đủ của lớp provider, ví dụ `example.resolver.DemoResolverProvider`. Chỉ khai báo cách đăng ký tương ứng với cách đóng gói ứng dụng; không cần đồng thời cả hai.

Mã phía ứng dụng không cần biết tên provider:

~~~java
import java.net.InetAddress;

public class ResolverDemo {
    public static void main(String[] args) throws Exception {
        InetAddress address = InetAddress.getByName("demo.test");
        System.out.println(address.getHostAddress()); // 127.0.0.1
    }
}
~~~

Kết quả như chú thích chỉ đúng **khi provider đã được đóng gói và tìm thấy**, và khi tên chưa bị chi phối bởi trạng thái cache/khởi tạo trước đó. Nếu chạy ví dụ đơn độc không cài provider, `demo.test` có thể dẫn tới `UnknownHostException`. Cần chạy kiểm thử trong một JVM mới để kiểm soát lần khởi tạo resolver và tránh cache từ phép thử trước.

### 5.3. Những giới hạn phải hiểu trước khi dùng trong hệ thống thật

- `lookupByName` nhận `LookupPolicy` mô tả yêu cầu IPv4/IPv6 và thứ tự ưu tiên; resolver tùy biến nghiêm túc phải tôn trọng policy đó. Ví dụ loopback ở trên cố ý giản lược cho một địa chỉ IPv4.
- `lookupByAddress` dùng cho tra cứu ngược; không thể chỉ triển khai chiều tên → IP rồi bỏ quên chiều IP → tên.
- `InetAddress` có cơ chế cache kết quả thành công và thất bại; sửa mapping không bảo đảm mọi lần gọi sau sẽ thấy kết quả mới ngay lập tức.
- Khi cần fallback, nên dùng `configuration.builtinResolver()`. Không gọi ngược `InetAddress.getByName` trong `lookupByName` để fallback, vì có thể gọi lại chính resolver tùy biến và gây đệ quy.
- Provider ảnh hưởng chung trong JVM, vì vậy phải cân nhắc kiểm thử, giới hạn trách nhiệm và việc quản lý cấu hình trước khi dùng.

**Ví dụ thực tế:** Một môi trường kiểm thử tích hợp muốn ánh xạ `test.internal` đến IP cố định mà không phụ thuộc DNS bên ngoài. SPI có thể thực hiện việc ánh xạ đó; nhưng nếu mục tiêu chỉ là thay một vài hostname trong môi trường test, hãy đánh giá phương án cấu hình resolver/hosts file của JDK hoặc tầng mạng hiện có để tránh tác động toàn JVM.

## 6. Core reflection dùng MethodHandle bên trong: JEP 416

### 6.1. Thay đổi ở lớp thực thi, không phải cú pháp reflection mới

JEP 416 tái triển khai cơ chế **core reflection** (`java.lang.reflect.Method`, `Constructor` và `Field`) dựa trên hạ tầng method handles của `java.lang.invoke`. Mục tiêu chính là giảm việc phải duy trì nhiều con đường thực thi và tăng tính nhất quán trong nội bộ JDK.

Từ góc nhìn ứng dụng, các API reflection quen thuộc vẫn được dùng:

~~~java
import java.lang.reflect.Method;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class InvokeComparison {
    public static String greet(String name) {
        return "Xin chào, " + name;
    }

    public static void main(String[] args) throws Throwable {
        Method method = InvokeComparison.class.getMethod(
                "greet", String.class);
        String viaReflection = (String) method.invoke(null, "An");

        MethodHandle handle = MethodHandles.lookup().findStatic(
                InvokeComparison.class,
                "greet",
                MethodType.methodType(String.class, String.class));
        String viaHandle = (String) handle.invokeExact("An");

        System.out.println(viaReflection);
        System.out.println(viaHandle);
    }
}
~~~

Cả hai đường gọi trong ví dụ đều in ra `Xin chào, An`, nhưng hợp đồng lập trình không giống hệt nhau:

| Tiêu chí | Core reflection | MethodHandle |
|---|---|---|
| Tạo đối tượng gọi | `Class.getMethod`, `getDeclaredMethod` và các API phản chiếu | `MethodHandles.Lookup.findStatic`, `findVirtual`, `unreflect` ... |
| Kiểu đối số khi gọi | `Method.invoke(Object, Object...)`, truyền mảng đối tượng, xử lý chuyển đổi hợp lệ | `MethodHandle` có `MethodType`; `invokeExact` yêu cầu signature trùng khớp |
| Kiểm tra quyền | Core reflection áp dụng kiểm tra truy cập khi sử dụng member (trừ trường hợp được cho phép bỏ qua) | `Lookup` thực hiện kiểm tra quyền khi tạo handle |
| Lỗi điển hình | Ngoại lệ từ phương thức đích được bọc trong `InvocationTargetException` | Lời gọi handle có thể truyền trực tiếp ngoại lệ từ đích; lỗi chữ ký có thể thành `WrongMethodTypeException` |
| Trường hợp dùng | Framework cần khám phá annotation/member, gọi linh hoạt | Bộ gọi có cấu trúc kiểu xác định, liên kết hoặc biến đổi hành vi gọi động |

### 6.2. Quy tắc truy cập vẫn tuân theo module và Java language access

Việc JDK đổi phần lõi reflection **không biến mọi trường private thành truy cập được**. Ví dụ, trong hệ thống sử dụng Java Platform Module System (JPMS):

- `getDeclaredMethod` có thể tìm thấy phương thức khai báo, nhưng việc gọi vẫn chịu kiểm tra quyền.
- `setAccessible(true)` hoặc `trySetAccessible()` chỉ có thể mở quyền trong điều kiện API và cấu hình module cho phép.
- Muốn deep reflection từ module khác, package mục tiêu thường cần được `opens` phù hợp; `exports` đơn thuần không có nghĩa là mở quyền truy cập private.
- `MethodHandles.privateLookupIn` cũng kiểm tra điều kiện module và quyền của `Lookup` đầu vào.

Khi nhận `IllegalAccessException` hoặc `InaccessibleObjectException`, kiểm tra quyền thực tế của class/package/module. Không kết luận rằng JEP 416 phá vỡ logic hoặc rằng MethodHandle tự động bỏ qua cơ chế đóng gói.

### 6.3. Tránh suy luận hiệu năng bằng tên API

Không có bảo đảm hợp đồng rằng “reflection sau Java 18 luôn nhanh hơn MethodHandle” hay ngược lại. Hiệu năng chịu ảnh hưởng của loại member, cách lưu đối tượng `Method`/`Field`, mức độ ổn định của call site và tối ưu hóa JIT. Kết quả microbenchmark không thay thế được đo đạc trên tải thực tế.

Chọn API theo nhu cầu:

- Cần liệt kê phương thức, đọc annotation, xử lý kiểu động trong framework: `java.lang.reflect` vẫn phù hợp.
- Cần thiết lập một thao tác gọi được kiểm tra kiểu và tái sử dụng nhiều lần, nhất là khi phải thích nghi chữ ký: xem xét `MethodHandle` cùng `MethodType` và các phép biến đổi handle.
- Khi dùng `invokeExact`, xem cả **kiểu trả về tại call site**. Trong ví dụ, phép ép kiểu `(String)` là một phần giúp JVM xác định descriptor chính xác.
- Không dùng `setAccessible(true)` như cách mặc định để vượt giới hạn module.

**Ví dụ thực tế:** Một thư viện ánh xạ DTO cần đọc metadata và gọi getter. Nó có thể tiếp tục dùng reflection để khám phá member, sau đó cân nhắc cache `MethodHandle` đã được kiểm tra quyền nếu số lần gọi cao và benchmark cho thấy phù hợp. JEP 416 không bắt buộc thư viện phải viết lại.

## 7. Kết hợp các thay đổi trong một tình huống thực tế

Giả sử đội phát triển một thư viện xử lý dữ liệu, có website tài liệu và bộ kiểm thử tích hợp:

| Nhu cầu | Công cụ / hợp đồng áp dụng | Cách kiểm chứng |
|---|---|---|
| Đọc/ghi dữ liệu khách hàng có dấu tiếng Việt | `StandardCharsets.UTF_8`, JEP 400 | Test round-trip và dữ liệu có ký tự đa byte |
| Xem nhanh HTML Javadoc hoặc một trang ví dụ | `jwebserver`, JEP 408 | Truy cập trên `127.0.0.1`, kiểm tra `GET`/`HEAD` |
| Trình bày cách gọi API trong tài liệu | `{@snippet}`, JEP 413 | Biên dịch/test ví dụ ngoài, chạy `javadoc` và xem HTML |
| Kiểm thử tên miền nội bộ giả lập | Resolver SPI, JEP 418 | Đăng ký provider, chạy JVM mới, xác nhận tra cứu hai chiều và fallback |
| Tạo cơ chế gọi getter động | Reflection / MethodHandle, JEP 416 | Test quyền truy cập, chữ ký, ngoại lệ; benchmark nếu tối ưu hiệu năng |

Các công cụ giải quyết **những vấn đề khác nhau**. Một thư viện ổn định thường dùng UTF-8 minh bạch khi lưu dữ liệu, Javadoc có ví dụ kiểm thử được, `jwebserver` phục vụ quá trình phát triển, và chỉ dùng resolver SPI hoặc MethodHandle trực tiếp khi yêu cầu kiến trúc thực sự đòi hỏi.

## 8. Thực hành tự kiểm chứng

### Bài 1 — Charset ở ranh giới dữ liệu

Tạo `CharsetCheck` trên JDK đang dùng. So sánh `Charset.defaultCharset()`, `file.encoding` và `native.encoding`. Sau đó đọc/ghi một chuỗi gồm “Tiếng Việt”, “日本語” và emoji bằng `StandardCharsets.UTF_8`. Giải thích vì sao kết quả vẫn đúng ngay cả khi `native.encoding` khác UTF-8.

**Tiêu chí đạt:** Nêu được rằng default charset là quy tắc cho API có sử dụng mặc định, còn charset tường minh là hợp đồng độc lập với máy chạy.

### Bài 2 — Preview tệp tĩnh

Tạo `public/index.html`, chạy `jwebserver -d public -b 127.0.0.1 -p 8000`. So sánh `curl -I` (HEAD) với `curl -i` (GET), rồi thử một yêu cầu POST.

**Tiêu chí đạt:** Phân biệt yêu cầu được hỗ trợ và yêu cầu không được hỗ trợ; giải thích tại sao thử nghiệm trên loopback là lựa chọn thích hợp.

### Bài 3 — Javadoc có ví dụ

Viết một API nhỏ với `{@snippet}` inline. Chuyển ví dụ sang `snippet-files`, tách vùng bằng `@start region` / `@end region`, biên dịch mã ví dụ và tạo lại Javadoc.

**Tiêu chí đạt:** Javadoc hiển thị đúng đoạn mong muốn, còn mã ví dụ được kiểm chứng độc lập.

### Bài 4 — Resolver và quyền truy cập

Giải thích tại sao provider từ ví dụ có thể trả `127.0.0.1` cho `demo.test` nhưng các tên khác vẫn có thể phân giải thông thường. Sau đó sửa một lời gọi `invokeExact` với sai kiểu tham số và dự đoán lỗi. Thử tìm một member private của module khác, xác định quyền `opens` cần thiết.

**Tiêu chí đạt:** Phân biệt provider selection/cache với DNS hệ điều hành; phân biệt lỗi kiểu MethodHandle và lỗi truy cập do JPMS.

## 9. Các hiểu lầm thường gặp

| Hiểu lầm | Hiểu đúng |
|---|---|
| “Java 18 mặc định UTF-8 nên mọi file cũ đều đọc đúng.” | Tệp cũ có thể theo charset khác; phải xác định encoding thực. |
| “Đổi `file.encoding` lúc runtime là đủ.” | Hành vi charset mặc định được xác lập theo triển khai/JVM; dùng cấu hình khởi động hoặc truyền charset trực tiếp. |
| “`jwebserver` là HTTP server cho production.” | Công cụ được thiết kế cho thử nghiệm, phát triển và debug tệp tĩnh. |
| “Snippet trong Javadoc tự được chạy test.” | Standard doclet không tự biên dịch/chạy snippet; cần kiểm chứng bên ngoài. |
| “Resolver SPI chỉ ảnh hưởng một lời gọi `getByName`.” | Provider đã chọn có phạm vi system-wide của JVM, chịu ảnh hưởng của cache và vòng đời khởi tạo. |
| “JEP 416 cho phép reflection truy cập mọi trường private.” | Kiểm tra quyền theo Java và JPMS vẫn có hiệu lực. |
| “MethodHandle luôn nhanh hơn reflection.” | Hợp đồng API không cam kết điều đó; chỉ số đo trong ngữ cảnh ứng dụng mới có ý nghĩa. |

## 10. Tài liệu chuẩn để tra cứu trên JDK đang dùng

Ưu tiên đọc API specification của **đúng phiên bản JDK đang chạy** khi một chi tiết hành vi quan trọng với sản phẩm. Các tài liệu sau minh họa rằng những cơ chế của Java 18 vẫn hiện diện trên JDK hiện đại:

1. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400) và [Charset (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html).
2. [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408), [hướng dẫn lệnh jwebserver (JDK 27)](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html), [SimpleFileServer API (JDK 27)](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html).
3. [JEP 413 — Code Snippets](https://openjdk.org/jeps/413), [Javadoc Snippets Guide (JDK 26)](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
4. [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418), [InetAddressResolverProvider (JDK 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html), [InetAddressResolver (JDK 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolver.html).
5. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416), [MethodHandles.Lookup (JDK 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html), [AccessibleObject (JDK 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html).

Bài học tập trung vào **hợp đồng công khai và cách kiểm thử** vì đây là phần bền vững khi nâng cấp JDK. Với những quy tắc phụ thuộc phiên bản hoặc nhà cung cấp, hãy kiểm tra lại đặc tả API và thử nghiệm có kiểm soát trên môi trường thực tế.
