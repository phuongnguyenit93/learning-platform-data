# Quan sát hành vi tra cứu với `Socket` hoặc `HttpClient` trên đúng JDK và cấu hình đang chạy

## 1. Mục tiêu và phạm vi

Bài học thuộc chương **Kiểm chứng resolver** của module **JAVA_VERSION_JAVA18**. Java 18 giới thiệu `java.net.spi.InetAddressResolverProvider` (JEP 418) để tùy biến việc phân giải tên máy chủ. SPI này vẫn được hỗ trợ trên các JDK hiện đại. Điều cần kiểm chứng không chỉ là provider đã được đăng ký, mà còn là **truy vấn phân giải nào thực sự đi qua resolver khi ứng dụng dùng `Socket` hoặc `HttpClient`**.

Sau bài này, bạn có thể:

- Xác nhận phiên bản JDK, module provider và các thiết lập liên quan ngay trong tiến trình kiểm thử.
- Phân biệt ba sự kiện: provider được chọn, resolver nhận yêu cầu tra cứu và kết nối TCP/HTTP thành công hoặc thất bại.
- Dùng một `InetAddressResolverProvider` có log để quan sát yêu cầu do `InetSocketAddress` và `Socket` tạo ra mà vẫn giữ hành vi phân giải của JDK.
- Giải thích vì sao một lần gọi `Socket.connect(...)` hoặc `HttpClient.send(...)` **không nhất thiết** tạo một truy vấn DNS mới, cũng như vì sao lỗi kết nối không đồng nghĩa lỗi phân giải tên.

**Giới hạn học thuật:** Chỉ dùng API còn được hỗ trợ trên JDK hiện đại: `InetAddress`, `InetSocketAddress`, `Socket`, `InetAddressResolver`, `InetAddressResolverProvider`, JPMS và (nếu chọn) `java.net.http.HttpClient`. Không phụ thuộc vào API nội bộ hoặc cơ chế cấu hình đã lỗi thời.

## 2. Hiểu đúng các lớp bằng chứng

Một lần gọi networking có thể đi qua các bước sau:

```text
Khởi chạy JVM trên JDK + cấu hình thực tế
          |
          v
Module provider có được resolve?
          |
          v
JDK có chọn provider và gọi get(Configuration)?
          |
          v
Ứng dụng yêu cầu phân giải hostname?
          |
          v
lookupByName(host, policy) có được gọi?  <-- cache / địa chỉ IP literal có thể ảnh hưởng
          |
          v
Có địa chỉ IP được trả về?
          |
          v
Ứng dụng kết nối TCP / gửi HTTP
          |
          v
Kết quả: thành công, từ chối, timeout, lỗi mạng, lỗi HTTP...
```

Các bằng chứng không thay thế cho nhau:

| Bằng chứng | Khẳng định được | Không khẳng định được |
| --- | --- | --- |
| `ModuleLayer.boot().findModule(...)` trả `true` | Module provider thuộc boot layer đã được resolve. | Provider đã được chọn hoặc `lookupByName` đã chạy. |
| Log từ `InetAddressResolverProvider.get(...)` | JDK đã yêu cầu provider cung cấp resolver. | Mỗi thao tác socket đều cần tra cứu tên. |
| Log từ `lookupByName(host, policy)` | Có yêu cầu tra cứu tên đi qua resolver đang quan sát. | Có truy vấn DNS qua mạng; resolver tích hợp có thể dùng hosts file, cache hoặc nguồn khác. |
| `InetSocketAddress.isUnresolved() == false` | Đã có một địa chỉ IP cho endpoint đó. | Cổng đích có dịch vụ đang lắng nghe. |
| `Socket.connect(...)` thành công | Kết nối TCP được thiết lập tới endpoint. | Đã có tra cứu tên mới trong chính lời gọi `connect`. |
| `HttpClient.send(...)` trả response | Có phản hồi HTTP cho yêu cầu. | Bắt buộc có DNS mới; có thể tái sử dụng kết nối hoặc đi qua proxy. |

Với `Socket`, thao tác `new InetSocketAddress(hostname, port)` thường thực hiện phân giải tên **ngay tại lúc xây dựng endpoint**, trước `socket.connect(endpoint, timeout)`. Ngược lại, `InetSocketAddress.createUnresolved(hostname, port)` cố ý không phân giải ở bước tạo đối tượng; không được xem nó là phép thử DNS đã chạy.

## 3. Chuẩn bị ví dụ quan sát trên JDK đang sử dụng

Ví dụ gồm hai **named module**:

```text
src/
├── demo.resolver/
│   ├── module-info.java
│   └── demo/resolver/LoggingResolverProvider.java
└── demo.socket/
    ├── module-info.java
    └── demo/socketclient/Main.java
```

### 3.1. Đăng ký provider và ghi log cả lượt tra cứu

File `src/demo.resolver/module-info.java`:

```java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
            with demo.resolver.LoggingResolverProvider;
}
```

File `src/demo.resolver/demo/resolver/LoggingResolverProvider.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.stream.Stream;

public final class LoggingResolverProvider
        extends InetAddressResolverProvider {

    public LoggingResolverProvider() {
    }

    @Override
    public String name() {
        return "logging-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        System.err.println("[resolver] get(): provider duoc chon");

        // Sử dụng resolver tích hợp của chính JDK đang chạy.
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                System.err.println("[resolver] lookupByName: " + host);
                return builtin.lookupByName(host, policy);
            }

            @Override
            public String lookupByAddress(byte[] address)
                    throws UnknownHostException {
                System.err.println(
                        "[resolver] lookupByAddress: " + address.length
                        + " bytes");
                return builtin.lookupByAddress(address);
            }
        };
    }
}
```

Ở đây, `get(Configuration)` ghi nhận thời điểm provider được chọn. Hai phương thức của `InetAddressResolver` ghi nhận yêu cầu **phân giải thuận** (hostname → địa chỉ) và **phân giải ngược** (địa chỉ → hostname). Việc gọi `configuration.builtinResolver()` giúp giữ nguyên cách JDK/OS giải quyết tên, thay vì tạo một resolver giả khiến kết quả của bài kiểm thử bị bóp méo.

**Lưu ý:** Log `lookupByName` cho biết JDK gọi SPI; nó không chứng minh có gói tin DNS gửi đến máy chủ DNS. Resolver tích hợp có thể dùng hosts file và các cơ chế sẵn có khác. Trong các bài kiểm thử có nhiều provider, lựa chọn provider không nên được giả định theo thứ tự module path.

### 3.2. Ứng dụng thử tra cứu bằng `Socket`

File `src/demo.socket/module-info.java`:

```java
module demo.socket {
}
```

Ứng dụng chỉ dùng API của `java.base`, nên không cần `requires` bổ sung. File `src/demo.socket/demo/socketclient/Main.java`:

```java
package demo.socketclient;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

public final class Main {
    public static void main(String[] args) {
        String host = args.length > 0 ? args[0] : "localhost";
        int port = args.length > 1 ? Integer.parseInt(args[1]) : 9;

        System.out.println("JDK version: " + Runtime.version());
        System.out.println("java.home: " + System.getProperty("java.home"));
        System.out.println("Provider module resolved: "
                + ModuleLayer.boot()
                        .findModule("demo.resolver")
                        .isPresent());

        System.out.println("preferIPv4Stack: "
                + System.getProperty("java.net.preferIPv4Stack"));
        System.out.println("preferIPv6Addresses: "
                + System.getProperty("java.net.preferIPv6Addresses"));

        System.out.println("Creating InetSocketAddress: " + host);
        InetSocketAddress endpoint = new InetSocketAddress(host, port);

        System.out.println("Endpoint unresolved: "
                + endpoint.isUnresolved());
        if (!endpoint.isUnresolved()) {
            System.out.println("Endpoint IP: "
                    + endpoint.getAddress().getHostAddress());
        }

        try (Socket socket = new Socket()) {
            // Kết nối TCP dùng endpoint đã tạo ở trên.
            socket.connect(endpoint, 1500);
            System.out.println("TCP connection: SUCCESS");
        } catch (IOException ex) {
            System.out.println("TCP connection: "
                    + ex.getClass().getSimpleName());
            System.out.println("Reason: " + ex.getMessage());
        }
    }
}
```

Với tham số mặc định, chương trình kiểm tra `localhost` ở cổng `9`. Đây chỉ là **cổng minh họa**: môi trường của bạn có thể từ chối hoặc chấp nhận kết nối, tùy dịch vụ đang chạy. Không cần mở kết nối thành công mới quan sát được tra cứu tên. Bạn cũng có thể thay `9` bằng cổng của một server thử nghiệm đã có sẵn tại máy.

## 4. Chạy và thu bằng chứng trên đúng JDK

Trước hết, kiểm tra `java` và `javac` mà terminal đang dùng:

```shell
java -version
javac -version
```

Nếu môi trường dùng nhiều JDK, hãy bảo đảm `java` và `javac` đến từ bộ JDK bạn muốn xác minh. Giá trị `java.home` mà ứng dụng in ra là bằng chứng trực tiếp về runtime đang thực thi.

Biên dịch từ thư mục chứa `src`:

```shell
javac --module-source-path src -d mods -m demo.resolver,demo.socket
```

Chạy với provider module được chỉ định rõ:

```shell
java --module-path mods --add-modules demo.resolver --show-module-resolution --module demo.socket/demo.socketclient.Main localhost 9
```

Lệnh trên viết một dòng nên dùng được trong PowerShell cũng như nhiều shell thông dụng. `--add-modules demo.resolver` yêu cầu provider module tham gia quá trình phân giải module, kể cả khi ứng dụng không có `requires demo.resolver`. `--show-module-resolution` in thông tin phân giải module ngay lúc khởi động.

Ví dụ **dấu hiệu đầu ra** cần tìm (thứ tự và địa chỉ có thể khác):

```text
root demo.socket ...
root demo.resolver ...
JDK version: 25.0.x+...
Provider module resolved: true
Creating InetSocketAddress: localhost
[resolver] get(): provider duoc chon
[resolver] lookupByName: localhost
Endpoint unresolved: false
Endpoint IP: 127.0.0.1
TCP connection: ConnectException
```

Đây **không phải output được bảo đảm**. Phiên bản Java, thông tin module, IPv4/IPv6, kết quả kết nối và thứ tự dòng trên `stdout`/`stderr` phụ thuộc máy và cấu hình thực tế. Nếu tên đã được cache hoặc có đường xử lý riêng, số lượt gọi resolver có thể khác mong đợi. Hãy ghi lại log thực tế trước khi rút kết luận.

Tách biệt ba kết quả quan trọng:

1. **`Provider module resolved: true`**: module hiện diện ở boot layer.
2. **`[resolver] get()` và `[resolver] lookupByName`**: provider đã được chọn và có lượt tra cứu thuận đi qua nó.
3. **`TCP connection: ...`**: phản ánh trạng thái kết nối, là chuyện khác với phân giải hostname.

Nếu `lookupByName` trả về địa chỉ nhưng đích không mở cổng, `ConnectException` vẫn là kết quả hoàn toàn phù hợp. Ngược lại, nếu `Endpoint unresolved: true`, tên chưa được phân giải; không nên gọi đó là một lỗi TCP tới địa chỉ IP đã biết.

## 5. Thử các tình huống khác nhau để kiểm chứng giả thuyết

Mỗi dòng lệnh dưới đây nên chạy trong **một tiến trình JVM mới** để tránh trạng thái provider và cache đã có từ những lần thử trước.

| Phép thử | Ví dụ tham số | Quan sát/kết luận dự kiến |
| --- | --- | --- |
| Hostname cục bộ | `localhost 9` | Quan sát tên và IP trả về; kết nối có thể thành công hoặc thất bại độc lập. |
| Địa chỉ IPv4 literal | `127.0.0.1 9` | JDK thường phân tích IP trực tiếp; có thể không xuất hiện `lookupByName`. Đây là ví dụ cho thấy không phải mọi kết nối đều cần phân giải hostname. |
| Host không tồn tại (tên dành riêng cho kiểm thử) | `host-does-not-exist.invalid 9` | Có thể thấy `lookupByName`, `Endpoint unresolved: true`; không có kết nối TCP thành công tới IP chưa xác định. |
| Bỏ `--add-modules demo.resolver` | Giữ `--module-path mods` | So sánh `--show-module-resolution`, `findModule` và log provider. Không tự suy ra rằng module có trên module path thì luôn được resolve. |

Ví dụ với địa chỉ literal:

```shell
java --module-path mods --add-modules demo.resolver --module demo.socket/demo.socketclient.Main 127.0.0.1 9
```

Ví dụ với tên không tồn tại:

```shell
java --module-path mods --add-modules demo.resolver --module demo.socket/demo.socketclient.Main host-does-not-exist.invalid 9
```

Tên `.invalid` được dành riêng cho tình huống thử nghiệm. Mặc dù vậy, thông báo lỗi và thời gian chờ vẫn có thể thay đổi theo resolver, search domain hoặc cấu hình mạng.

Khi đổi cấu hình chọn IPv4/IPv6, hãy khởi động JVM mới và ghi lại giá trị property, hostname, IP thực tế. Chẳng hạn:

```shell
java -Djava.net.preferIPv6Addresses=true --module-path mods --add-modules demo.resolver --module demo.socket/demo.socketclient.Main localhost 9
```

Không kết luận property chắc chắn tạo ra một địa chỉ IPv6: việc hệ thống có IPv6, dữ liệu trả về và chính sách chọn địa chỉ vẫn có vai trò. Các thiết lập lưu cache kết quả phân giải có thể ảnh hưởng tới số lượt gọi provider trong một tiến trình; ví dụ này chủ động sử dụng các JVM mới để dễ diễn giải.

## 6. Nếu muốn quan sát với `HttpClient`

`java.net.http.HttpClient` cũng là API hiện đại; tuy nhiên, quá trình gửi HTTP có nhiều yếu tố hơn `Socket`: kết nối có thể được dùng lại, có thể có proxy và việc phân giải có thể diễn ra bất đồng bộ. Để xây dựng ví dụ riêng, module ứng dụng cần đọc `java.net.http`:

```java
module demo.socket {
    requires java.net.http;
}
```

Một thao tác gửi request minh họa (đưa vào mã ứng dụng có các import thích hợp) như sau:

```java
var client = java.net.http.HttpClient.newBuilder()
        .connectTimeout(java.time.Duration.ofSeconds(2))
        .build();

var request = java.net.http.HttpRequest.newBuilder(
                java.net.URI.create("http://localhost:9/"))
        .timeout(java.time.Duration.ofSeconds(3))
        .GET()
        .build();

try {
    var response = client.send(
            request,
            java.net.http.HttpResponse.BodyHandlers.discarding());
    System.out.println("HTTP status: " + response.statusCode());
} catch (java.io.IOException ex) {
    System.out.println("HTTP I/O: " + ex.getClass().getSimpleName());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    System.out.println("HTTP request interrupted");
}
```

Có thể tái sử dụng `LoggingResolverProvider` để so sánh log khi gửi HTTP. Nếu request trả lỗi kết nối hoặc timeout, hãy kiểm tra riêng có hay không log `lookupByName`. Nếu không có log, không được vội kết luận SPI không hoạt động: trước tiên kiểm tra provider module, proxy, địa chỉ IP literal, cache, tái sử dụng kết nối và phiên bản JDK.

**Chú ý khi so sánh:** `Socket` trong ví dụ tạo `InetSocketAddress` rồi mới kết nối. `HttpClient` có thể quyết định thời điểm phân giải và kết nối ở một bước khác trong quá trình gửi yêu cầu. Vì vậy, các log cần được gắn với hành vi thực tế của từng API thay vì dựa vào giả định một yêu cầu HTTP tương ứng một truy vấn DNS.

## 7. Cách ghi lại bằng chứng và xử lý bất thường

Mẫu biên bản cho mỗi lần chạy:

| Mục cần ghi | Giá trị từ lần chạy |
| --- | --- |
| `java -version`, `javac -version`, `java.home` | JDK và runtime thực tế. |
| Dòng lệnh đầy đủ | `--module-path`, `--add-modules`, `-D...`, tên host và cổng. |
| `Provider module resolved` và `--show-module-resolution` | Provider module có trong đồ thị phân giải hay không. |
| Log `get(Configuration)` | Provider có được chọn không. |
| Log `lookupByName` / `lookupByAddress` | Có yêu cầu nào thực sự đi qua resolver. |
| `Endpoint unresolved`, `Endpoint IP` | Kết quả phân giải. |
| Trạng thái TCP/HTTP | Kết nối hoặc HTTP thành công, thất bại hay timeout. |

Các trường hợp thường gặp:

- **Module chưa resolve:** kiểm tra `--module-path`, tên module và `--add-modules`. Việc có file `.class` trong `mods` chưa đủ chứng minh module đã được resolve.
- **Module đã resolve nhưng thiếu log `get`:** xác minh provider declaration, kiểm tra có provider khác cùng tồn tại và chạy lại trong JVM mới. Đồ thị module không chứng minh provider được chọn.
- **Có log `get` nhưng không có `lookupByName`:** thử hostname mới trong JVM mới; kiểm tra liệu đầu vào có phải IP literal, yêu cầu có sử dụng cache hay quá trình kết nối đã bỏ qua phân giải tên.
- **Có `lookupByName` nhưng kết nối thất bại:** dùng `Endpoint unresolved` và `Endpoint IP` để phân biệt lỗi tên với lỗi TCP. Cổng đóng, firewall, timeout hay proxy không phải là bằng chứng resolver sai.
- **Có `lookupByAddress` dù không chủ động yêu cầu:** tra cứu ngược có thể xảy ra do mã khác gọi phương thức cần tên host. Tránh các lệnh in hoặc logging vô tình gọi `getHostName()` khi chỉ muốn quan sát IP; dùng `getHostAddress()` để in IP.
- **Kết quả khác giữa hai máy:** so sánh đúng phiên bản JDK, hệ điều hành, nội dung hosts file, IPv4/IPv6, cấu hình mạng, proxy, container và cache. Hợp đồng API có thể giống nhau trong khi nguồn dữ liệu tên và kết nối là khác nhau.

## 8. Bài tập thực hành

1. Chạy demo `Socket` bằng JDK hiện dùng với `localhost`, ghi lại dòng lệnh, `java.home`, trạng thái module, log resolver, IP và kết quả TCP.
2. Chạy lại trong JVM mới với `127.0.0.1`. Giải thích vì sao địa chỉ literal có thể không tạo log `lookupByName`.
3. Chạy với `host-does-not-exist.invalid`, so sánh log resolver, `Endpoint unresolved` và lỗi kết nối.
4. Bỏ `--add-modules`, kiểm tra module thực tế được resolve rồi mới rút kết luận về cách module provider tham gia runtime này.
5. Nếu sử dụng `HttpClient`, lập bảng đối chiếu yêu cầu HTTP đầu tiên và yêu cầu tiếp theo trong cùng tiến trình. Kiểm tra xem số lượt gọi `lookupByName` có thay đổi khi kết nối được tái sử dụng hoặc có proxy.

### Câu hỏi tự kiểm tra

**1. Vì sao `ConnectException` không chứng minh tra cứu DNS thất bại?**

Vì tên có thể đã phân giải thành IP thành công, trong khi máy đích từ chối kết nối TCP ở cổng yêu cầu. Cần kiểm tra kết quả phân giải riêng.

**2. `--show-module-resolution` có đủ để chứng minh `lookupByName` đã chạy?**

Không. Lệnh này chỉ quan sát phân giải module. Cần log tại SPI hoặc bằng chứng trực tiếp khác về lượt gọi tra cứu.

**3. Tại sao nên ghi nhận `java.home` thay vì chỉ ghi “đang dùng Java 18/21/25”?**

Vì cùng một máy có thể cài nhiều JDK hoặc dùng JDK khác nhau giữa terminal, IDE và runtime triển khai. `java.home` cho biết runtime của chính tiến trình đang được kiểm tra.

**4. Log `lookupByName` có đồng nghĩa chắc chắn đã phát gói DNS không?**

Không. Nó chứng minh một yêu cầu đến lớp resolver. Resolver tích hợp có thể trả kết quả từ hosts file, cache hoặc cơ chế phân giải khác mà không truy vấn DNS qua mạng.

## Tài liệu tham khảo

- OpenJDK JEP 418 — *Internet-Address Resolution SPI*: https://openjdk.org/jeps/418
- Java SE API — `InetAddressResolverProvider`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html
- Java SE API — `InetSocketAddress`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetSocketAddress.html
- Java SE API — `HttpClient`: https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html

Các liên kết API là ví dụ tài liệu phiên bản JDK hiện đại; khi kiểm chứng hành vi cụ thể, ưu tiên đối chiếu với Java API documentation ứng với **chính phiên bản JDK đang chạy**.
