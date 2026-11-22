# Networking properties: phạm vi toàn tiến trình và thời điểm thuộc tính được đọc

## Mục tiêu học tập

Một chương trình Java mạng có thể bị ảnh hưởng bởi các cấu hình như `java.net.preferIPv4Stack`, `http.proxyHost`, `java.net.useSystemProxies`, `http.keepAlive` hay `networkaddress.cache.ttl`. Tuy nhiên, **không phải mọi thuộc tính đều có cùng phạm vi, cách đặt hoặc thời điểm có hiệu lực**.

Có ba câu hỏi cần trả lời *trước khi sửa cấu hình*:

1. **Ai sở hữu giá trị?** Một **JVM process** thông qua system properties, một cấu hình **security properties**, một file cấu hình của JDK, một đối tượng `HttpClient`/`ProxySelector`, hay chính hệ điều hành?
2. **Giá trị được đọc lúc nào?** Một lần lúc **JVM startup/initialization**, mỗi lần một hoạt động mạng được thực hiện, khi **class/component lần đầu khởi tạo**, hoặc khi **một đối tượng client được xây dựng**?
3. **Đổi giá trị ảnh hưởng tới ai?** Toàn bộ thread và các thư viện **trong cùng JVM**, chỉ một HTTP client/connection nếu cấu hình theo instance, hay chỉ những **JVM process được khởi động về sau** khi thay `-D`?

Sai lầm phổ biến là thấy `System.getProperty("java.net.preferIPv4Stack")` thay từ `false` sang `true` sau khi ứng dụng chạy, rồi cho rằng các socket đã tồn tại hoặc những socket tiếp theo chắc chắn đổi IPv4/IPv6 policy ngay. Tài liệu JDK 17 xác định đây là **thuộc tính được đọc một lần lúc JVM khởi động**; việc thay **chuỗi trong properties map** không tương đương reinitialize networking stack.

Bài này có bốn chương trình Java 17+ được biên dịch/chạy kiểm chứng:

- **`StartupPropertyVisibilityDemo`:** khởi động **hai JVM riêng** với `-Djava.net.preferIPv4Stack=false` và `true`; quan sát IPv6 loopback socket và chứng minh thay `System.setProperty` lúc runtime không đổi kết quả thử nghiệm.
- **`ProxyPropertyScopeDemo`:** hai thread cùng nhìn một system property toàn process; `ProxySelector` mặc định tra cứu `http.proxyHost`/`http.nonProxyHosts` theo yêu cầu mới.
- **`LegacyAgentTimingDemo`:** `http.agent` của HTTP URL protocol handler giữ giá trị đã đọc ban đầu, dù `System.setProperty` thay đổi sau request đầu.
- **`SecurityPropertyScopeDemo`:** so sánh `System.setProperty` với `Security.setProperty` cho DNS negative-cache TTL, hoàn toàn không cần tra cứu DNS thật.

Tất cả ví dụ chỉ dùng loopback hoặc tạo đối tượng cấu hình; không kết nối dịch vụ công cộng, không thay file JDK hay cấu hình mạng của máy. Mỗi ví dụ là **một chương trình độc lập**, khác với các code snippets ghi rõ chỉ minh họa trong phần lý thuyết.

## 1. Phân biệt process, thread, object, OS và JDK installation

Java process điển hình có một JVM với nhiều thread và nhiều thư viện:

```text
Hệ điều hành / container / VM
  │
  ├── JVM Process A   (java -Dhttp.proxyHost=proxy-a ...)
  │     │
  │     ├── JVM System Properties (một kho dùng chung trong process)
  │     │     ├── http.proxyHost
  │     │     ├── java.net.useSystemProxies
  │     │     └── java.net.preferIPv4Stack
  │     │
  │     ├── Java Security Properties (kho KHÁC)
  │     │     ├── networkaddress.cache.ttl
  │     │     └── networkaddress.cache.negative.ttl
  │     │
  │     ├── Thread 1: URLConnection / HttpClient / Socket
  │     ├── Thread 2: URLConnection / HttpClient / Socket
  │     └── Shared defaults: ProxySelector, Authenticator, SSL settings...
  │
  └── JVM Process B   (java -Dhttp.proxyHost=proxy-b ...)
        └── Có kho properties riêng, không tự nhận setProperty từ A
```

**`System.getProperties()` dùng chung giữa các thread trong cùng JVM.** Không phải “mỗi request giữ một bộ global properties độc lập”. Khi thread A gọi `System.setProperty("http.proxyHost","...")`, thread B có thể đọc giá trị mới. Đây là nguồn **coupling, race condition và thay đổi hành vi của thư viện không liên quan**.

Ngược lại, hai tiến trình Java chạy trên cùng máy không tự chia sẻ mutation của `System.setProperty`. Nếu process A thay `http.proxyHost`, process B không tự thay. Để áp dụng một cấu hình startup mới cho process B, phải truyền `-D` khi launch B hoặc dùng cơ chế cấu hình mà process B đọc.

### Mô hình phạm vi

| Nguồn/cơ chế | Phạm vi thông thường | Ví dụ | Tác động khi thay |
|---|---|---|---|
| JVM system property | **Process-wide** | `System.setProperty("http.proxyHost",...)` | Các thread/chức năng đọc lại property có thể thấy giá trị mới |
| JVM launch flag | Chỉ **JVM process** vừa launch | `java -Djava.net.preferIPv4Stack=true ...` | Có hiệu lực khi thành phần đọc lúc startup, không đổi JVM khác |
| JDK security property | JVM-wide nhưng **kho security riêng** | `Security.getProperty("networkaddress.cache.ttl")` | Có thể bị component cache; không phải map của `System` |
| JDK install configuration | File ở cài đặt JDK, áp cho các process dùng installation đó tùy cơ chế | `conf/net.properties`, `conf/security/java.security` | Có thể chỉ tác động tới lần launch mới; không sửa trực tiếp vào running JVM |
| Network object property | Một đối tượng/instance | `HttpURLConnection.setConnectTimeout`, `HttpClient.Builder.proxy(...)` | Không chủ động sửa global system properties |
| OS network configuration | Máy, namespace, container hoặc user theo OS | DNS resolver, route, system proxy | Java có thể đọc/snapshot/cache, không mặc định cập nhật mọi object ngay |
| Environment variable | Môi trường process do launcher cấp | `System.getenv("HTTPS_PROXY")` | **Không đồng nhất** với `System.getProperty("https.proxyHost")` |

Một cấu hình gọi là “global” thường chỉ global **trong một JVM**, không có nghĩa global của mọi chương trình trên máy. Đừng hiểu `System.setProperty` là lệnh thay proxy Windows/Linux/macOS hoặc thay giá trị trong `$JAVA_HOME/conf/net.properties` trên đĩa.

## 2. Thời điểm đọc giá trị: static, dynamic, initialized hay cached?

Tài liệu **Networking Properties của Java 17** nêu quy tắc nền:

- Một số properties **chỉ được kiểm tra một lần lúc JVM startup** và nên dùng `-D` của lệnh `java`.
- Một số properties có tính **dynamic** và có thể được thay bằng `System.setProperty(...)`.
- **Nếu mô tả một property không có chú thích riêng về thời điểm đọc**, tài liệu trang đó nói giá trị được kiểm tra mỗi lần sử dụng. **Quy tắc này áp dụng trong phạm vi danh sách và contract của tài liệu**, không phải lời hứa cho mọi property nội bộ `jdk.*` hay mọi thư viện.

### Ba loại hành vi cần nhận biết

| Kiểu | Khi nào component đọc? | Tác động của `System.setProperty` lúc runtime | Chiến lược ổn định |
|---|---|---|---|
| **Startup-only** | Một lần trong giai đoạn khởi động JVM | Chuỗi map có thể đổi nhưng network mechanism không nhất thiết cập nhật | Đặt `-D` trước khi process start, rồi restart |
| **Dynamic lookup** | Mỗi lần component tra cứu, nếu contract nói vậy | Những lần tra cứu sau có thể thấy giá trị mới | Cẩn thận process-wide; tránh toggle nhiều thread |
| **Component initialization/cached** | Khi class/object/subsystem lần đầu init hoặc snapshot | Thay map sau init có thể **không** ảnh hưởng component đã tồn tại | Đặt sớm, xem Javadoc/chính sách component, thử trên đúng JDK |

**Một thuộc tính “dynamic” không tự cập nhật request đang gửi**: nếu proxy cho một request đã được chọn, thay property giữa lúc socket hoạt động không làm socket nhảy sang proxy khác. Dynamic thường có nghĩa **lần chọn proxy/operation tiếp theo** có thể quan sát giá trị mới, tùy implementation.

### “Lúc startup” không đồng nghĩa “lúc main bắt đầu”

`main(String[] args)` là điểm người lập trình thấy sau khi Java launcher đã khởi động runtime. Các socket classes, network preferences hoặc system service có thể đã được khởi tạo trước hoặc trong giai đoạn startup. Do đó **đặt `System.setProperty` ở dòng đầu `main` không phải cách tương đương tuyệt đối với `-D`** cho property startup-only. Nếu Java doc yêu cầu startup, đặt ở **lệnh launch JVM**, không đánh cược vào thứ tự class loading.

### Cách đọc đúng câu “System.getProperty() đã thay”

`System.getProperty("java.net.preferIPv4Stack")` chỉ trả một **String đang nằm trong system properties map** (hoặc `null`). Nó **không** hỏi native networking stack đang chạy ở IPv4 hay IPv6 mode. Đổi map không chứng minh thay native state; phải kiểm tra hành vi socket riêng và đối chiếu contract.

## 3. Bảng networking properties quan trọng theo Java 17

Bảng dưới đây phân nhóm **đúng theo tài liệu Java SE 17**, không tự trộn chúng thành một cơ chế cập nhật thống nhất.

| Property | Giá trị mặc định theo tài liệu JDK 17 | Phạm vi/nhóm | Khi nào đọc? |
|---|---|---|---|
| `java.net.preferIPv4Stack` | `false` | java.net IPv4/IPv6 | **Startup-only** |
| `java.net.preferIPv6Addresses` | `false` | java.net DNS address ordering preference | **Startup-only** |
| `java.net.useSystemProxies` | `false` | Default OS proxy integration | **Startup-only** |
| `http.proxyHost` | Không đặt | Legacy HTTP/default proxy selection | **Lookup khi dùng** theo nhóm proxy |
| `http.proxyPort` | `80` | HTTP proxy | **Lookup khi dùng** theo nhóm proxy |
| `http.nonProxyHosts` | `localhost\|127.*\|[::1]` | HTTP/HTTPS proxy exclusions | **Lookup khi dùng** theo nhóm proxy |
| `https.proxyHost` | Không đặt | HTTPS proxy | **Lookup khi dùng** theo nhóm proxy |
| `https.proxyPort` | `443` | HTTPS proxy | **Lookup khi dùng** theo nhóm proxy |
| `socksProxyHost` | Không đặt | SOCKS proxy | **Lookup khi dùng** theo nhóm proxy |
| `socksProxyPort` | `1080` | SOCKS proxy | **Lookup khi dùng** theo nhóm proxy |
| `http.agent` | User-Agent `Java/<version>` | Legacy HTTP URL protocol handler | **Startup-only** |
| `http.keepAlive` | `true` | Legacy URL handler persistent connections | **Startup-only** |
| `http.maxConnections` | `5` | Legacy URL handler: số idle keep-alive connections tối đa mỗi destination | **Startup-only** |
| `http.maxRedirects` | `20` | Legacy URL handler redirect limit | **Startup-only** |
| `jdk.http.maxHeaderSize` | `393216` bytes | Giới hạn header mà client chuẩn bị nhận | **Startup-only** trong danh mục URL handler |
| `networkaddress.cache.ttl` | Phụ thuộc JDK/security config | **Security property**, DNS positive cache | Không phải cấu hình `-D` thông thường; xem `Security.getProperty` |
| `networkaddress.cache.negative.ttl` | `10` giây trong trang JDK 17 | **Security property**, DNS negative cache | Không phải cấu hình `-D` thông thường; có thể được cache bởi resolver |
| `jdk.httpclient.connectionPoolSize` | `0` trong hướng dẫn JDK 17 | **JDK-specific java.net.http client** | Xem tài liệu module/phiên bản; không đồng nhất với `http.maxConnections` |

**Lưu ý khi nâng cấp JDK:** danh mục và mặc định của properties JDK-specific có thể thay đổi giữa Java 17, 21 và các update releases. Khi vận hành production, kiểm tra tài liệu **đúng JDK runtime đang dùng**. Bảng này có mục đích huấn luyện Java 17, không cấp phép giả định mọi property tồn tại/hợp lệ vĩnh viễn.

### Tại sao không kết luận `http.maxConnections=5` nghĩa HTTP client có tối đa năm sockets?

`http.maxConnections` là giới hạn **idle keep-alive connections per destination** của **HTTP URL protocol handler** theo JDK 17, không phải “max 5 connections đang hoạt động” toàn JVM. `java.net.http.HttpClient` hiện đại có properties/configuration khác, ví dụ `jdk.httpclient.connectionPoolSize`. Không dùng cùng một key cho hai HTTP implementations khi không có contract tương ứng.

### Vì sao `http.keepAlive` không bằng TCP `SO_KEEPALIVE`?

`http.keepAlive` điều chỉnh khả năng **tái sử dụng HTTP persistent connections** của legacy HTTP handler. `Socket.setKeepAlive(true)` là socket option của TCP để bật keepalive probes ở tầng OS. Hai hành vi khác nhau: một bên liên quan số lần gửi HTTP requests trên connection, bên kia giám sát transport idle.

## 4. IPv4/IPv6: hai properties được đọc đúng một lần

Theo Java 17:

- `java.net.preferIPv4Stack=false` là default. Khi IPv6 có sẵn, Java thường dùng IPv6-capable sockets có thể phục vụ IPv4/IPv6 theo OS behavior.
- `java.net.preferIPv4Stack=true` yêu cầu IPv4-only stack, do đó những socket do stack này tạo **không thể giao tiếp tới IPv6-only hosts**.
- `java.net.preferIPv6Addresses=false` mặc định ưu tiên địa chỉ IPv4 khi host có cả A/AAAA để giữ tương thích lịch sử. `true` ưu tiên IPv6 khi có thể; `system` bảo toàn thứ tự địa chỉ do OS trả về.
- **Cả hai được kiểm tra một lần lúc JVM startup**. Không dùng chúng như công tắc đổi addressing giữa hai requests đang chạy.

### Hai thuộc tính này không hoàn toàn trùng nhau

`preferIPv4Stack` là **loại socket/stack**. `preferIPv6Addresses` là **thứ tự ưu tiên** trong lựa chọn địa chỉ khi resolution trả nhiều addresses. Ví dụ đặt `preferIPv6Addresses=true` nhưng vẫn dùng IPv4-only stack là cấu hình xung đột về kỳ vọng; không tự đảm bảo có thể kết nối IPv6-only host.

Một host `localhost` có thể resolve thành `127.0.0.1` và/hoặc `::1` theo OS/JDK. **Không lấy thứ tự của `InetAddress.getAllByName("localhost")` ở máy này làm bảo đảm chung**. Trên môi trường không có IPv6, test IPv6 có thể fail hợp lệ.

### Cách vận hành đúng

```bash
# Dùng dấu -D trước tên class; khởi chạy một JVM mới.
java -Djava.net.preferIPv4Stack=true MyNetworkingApp

# Một JVM khác, ở thời điểm launch khác, có chính sách khác:
java -Djava.net.preferIPv6Addresses=system MyNetworkingApp
```

`MyNetworkingApp` là tên minh họa, không phải class có sẵn trong bài. Cần cấu hình launcher của container/systemd/IDE/Java service wrapper để các flags này có mặt **ngay lúc Java process được tạo**. Không dựa vào việc “sau khi application đã started thì setProperty(...) là đủ”.

## 5. Java 17+: so sánh hai JVM và việc đổi thuộc tính lúc chạy

Ví dụ thứ nhất được chạy **hai lần trong hai Java processes riêng**. Nó thử bind một socket server trên IPv6 loopback `::1`, sau đó thay `java.net.preferIPv4Stack` bằng `System.setProperty(...,"true")`, thử lại và in kết quả.

Để tránh phụ thuộc vào DNS, chương trình dùng **IPv6 literal `::1`**; không truy cập Internet. Trong hệ điều hành không có IPv6, cả hai lần bind có thể fail; chương trình cố tình ghi nhận dưới dạng boolean thay vì đổ lỗi cho mạng.

**Tệp `StartupPropertyVisibilityDemo.java`:**

```java
import java.net.*;

public class StartupPropertyVisibilityDemo {
    public static void main(String[] args) throws Exception {
        String initial = System.getProperty("java.net.preferIPv4Stack", "false");
        boolean initialSocketIPv6Support;
        try (ServerSocket v6 = new ServerSocket()) {
            v6.bind(new InetSocketAddress(InetAddress.getByName("::1"), 0));
            initialSocketIPv6Support = true;
        } catch (Exception noIpv6) {
            initialSocketIPv6Support = false;
        }
        System.setProperty("java.net.preferIPv4Stack", "true");
        boolean afterSocketIPv6Support;
        try (ServerSocket v6 = new ServerSocket()) {
            v6.bind(new InetSocketAddress(InetAddress.getByName("::1"), 0));
            afterSocketIPv6Support = true;
        } catch (Exception noIpv6) {
            afterSocketIPv6Support = false;
        }
        System.out.println("Initial property: " + initial);
        System.out.println("System property after mutation: " +
                System.getProperty("java.net.preferIPv4Stack"));
        System.out.println("IPv6 loopback socket supported before: "
                + initialSocketIPv6Support);
        System.out.println("IPv6 loopback socket supported after: "
                + afterSocketIPv6Support);
        System.out.println("Socket capability changed: "
                + (initialSocketIPv6Support != afterSocketIPv6Support));
    }
}
```

Biên dịch:

```bash
javac --release 17 -encoding UTF-8 StartupPropertyVisibilityDemo.java
```

Chạy lần 1, tạo JVM với `preferIPv4Stack=false`:

```bash
java -Djava.net.preferIPv4Stack=false StartupPropertyVisibilityDemo
```

**Stdout đã quan sát trên một máy Windows hỗ trợ IPv6:**

```text
Initial property: false
System property after mutation: true
IPv6 loopback socket supported before: true
IPv6 loopback socket supported after: true
Socket capability changed: false
```

Chạy lần 2, tạo **JVM mới**, với `preferIPv4Stack=true`:

```bash
java -Djava.net.preferIPv4Stack=true StartupPropertyVisibilityDemo
```

**Stdout đã quan sát trên cùng máy:**

```text
Initial property: true
System property after mutation: true
IPv6 loopback socket supported before: false
IPv6 loopback socket supported after: false
Socket capability changed: false
```

### Đọc kết quả đúng

1. `System.setProperty(...)` đã thay được **chuỗi property map** thành `true` ở cả hai tiến trình; điều này được in ở dòng 2.
2. Process khởi động với `preferIPv4Stack=false` có thể bind `::1`; đổi map thành true giữa chương trình không làm thử nghiệm socket kế tiếp mất khả năng bind IPv6.
3. Process khởi động với `preferIPv4Stack=true` không bind được socket IPv6 trong môi trường thử nghiệm, dù cũng đã có property string true sau mutation.
4. `Socket capability changed: false` chứng minh **trong phép thử này** thay `System.setProperty` lúc runtime không làm thay đổi khả năng bind IPv6.
5. Dữ liệu là **quan sát trên runtime/OS cụ thể**; máy thiếu IPv6 có thể in false trước và sau bất kể `-D`. Quy tắc startup-only là **contract tài liệu JDK 17**, không suy ra bằng cách chỉ nhìn một dòng output.
6. Chương trình cố tình bắt rộng `Exception` ở phép thử socket capability để không phụ thuộc OS; production không nên nuốt exception như vậy khi chẩn đoán thật. Ở hệ thống thật, log class/message và callsite để biết bind fail vì gì.
7. Không khuyến nghị thay `java.net.preferIPv4Stack` trong một JVM production đang có nhiều sockets; thay string không làm “reset” sockets đã được tạo.

**Bài học:** chọn network stack ngay khi launch JVM, đo hành vi thay vì nhìn riêng `System.getProperty`.

## 6. Proxy properties: phạm vi toàn tiến trình, tra cứu theo request

Proxy là ví dụ hữu ích vì `http.proxyHost`, `http.proxyPort` và `http.nonProxyHosts` thuộc nhóm có thể được **default proxy selector** tra cứu lại khi tạo các requests mới.

Theo danh mục Java 17:

- `http.proxyHost` và `http.proxyPort` cấu hình HTTP proxy; default port 80 nếu không cung cấp.
- `https.proxyHost` và `https.proxyPort` cấu hình HTTPS proxy; default port 443. HTTPS protocol handler dùng **`http.nonProxyHosts`** như exclusions.
- `http.nonProxyHosts` dùng các mẫu phân cách bằng ký tự pipe `|`; wildcard `*` có thể match domain/host theo mô tả. Default ngoại lệ loopback `localhost|127.*|[::1]`.
- `socksProxyHost`/`socksProxyPort` cấu hình SOCKS proxy khi được hỗ trợ, nhưng ứng dụng còn có thể dùng proxy riêng hoặc `ProxySelector` custom.
- `java.net.useSystemProxies=true` cho phép java.net dùng system proxy settings trên một số OS. **Chính property này được đọc một lần ở startup**, không nên bật/tắt giữa request rồi kỳ vọng OS proxy integration tự thay tức thì.
- Các proxy properties được chỉ định trực tiếp (như `http.proxyHost`) **có ưu tiên so với OS proxy settings** theo tài liệu JDK 17 khi cùng cấu hình.

### Mẫu khởi động

```bash
java -Djava.net.useSystemProxies=false \
     -Dhttp.proxyHost=proxy.example.test \
     -Dhttp.proxyPort=8080 \
     -Dhttp.nonProxyHosts="localhost|127.*|*.internal" \
     MyApp
```

Lệnh trên minh họa kiểu shell Unix; `MyApp` và `proxy.example.test` **không phải endpoint đã được kiểm chứng**. Nếu dùng PowerShell, đặt flags trên **một dòng** hoặc dùng ký hiệu nối dòng đúng PowerShell (backtick); backslash cuối dòng kiểu POSIX không nối command trong PowerShell.

### Property “dynamic” không tự đổi một HttpURLConnection đã kết nối

Khi `URL.openConnection()` rồi kết nối, proxy route đã được chọn ở một thời điểm. Thay `http.proxyHost` sau đó **không** di chuyển TCP connection đang tồn tại sang proxy khác. Request tiếp theo trong default selector có thể thấy giá trị mới, nếu không bị proxy selector tùy chỉnh, per-connection proxy hoặc client snapshot policy ghi đè.

### Proxy exceptions là vấn đề bảo mật

Một cấu hình `http.nonProxyHosts="*"` có thể khiến **mọi host đi trực tiếp**, bỏ qua corporate proxy, làm sai egress/audit policy. Ngược lại, thiếu ngoại lệ nội bộ có thể chuyển lưu lượng tới proxy ngoài ý muốn. Đừng dùng wildcard quá rộng; hãy xác minh DNS, vùng mạng nội bộ và quy định tổ chức.

## 7. Java 17+: hai thread thấy cùng proxy property, selector cập nhật

Ví dụ này **không mở một TCP connection tới proxy nào**. Nó dùng `ProxySelector.getDefault().select(uri)` để xem proxy mà default selector định dùng; proxy IP `192.0.2.10` thuộc block TEST-NET-1 chỉ dành cho tài liệu, nên không có nguy cơ vô tình gọi service thật từ demo.

Chúng ta chạy với `-Djava.net.useSystemProxies=false` để không lấy proxy policy từ UI của hệ điều hành; trong process tạo lần lượt các system properties `http.proxyHost`, `http.proxyPort`, `http.nonProxyHosts`.

**Tệp `ProxyPropertyScopeDemo.java`:**

```java
import java.net.*;
import java.util.List;
import java.util.concurrent.*;

public class ProxyPropertyScopeDemo {
    private static String decide(String url) {
        List<Proxy> proxies = ProxySelector.getDefault().select(URI.create(url));
        if (proxies.isEmpty()) return "EMPTY";
        Proxy proxy = proxies.get(0);
        if (proxy.type() == Proxy.Type.DIRECT) return "DIRECT";
        InetSocketAddress address = (InetSocketAddress) proxy.address();
        return proxy.type() + ":" + address.getHostString()
                + ":" + address.getPort();
    }
    public static void main(String[] args) throws Exception {
        if (!"false".equals(System.getProperty("java.net.useSystemProxies")))
            throw new IllegalArgumentException("Use -Djava.net.useSystemProxies=false");
        String oldHost = System.getProperty("http.proxyHost");
        String oldPort = System.getProperty("http.proxyPort");
        String oldExceptions = System.getProperty("http.nonProxyHosts");
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            System.setProperty("http.proxyHost", "192.0.2.10");
            System.setProperty("http.proxyPort", "8181");
            System.setProperty("http.nonProxyHosts", "*.internal|localhost|127.*");
            System.out.println("Main thread property: " +
                    System.getProperty("http.proxyHost"));
            System.out.println("Worker thread property: " + worker.submit(
                    () -> System.getProperty("http.proxyHost")).get());
            System.out.println("External URI selection: " +
                    decide("http://public.example.test/resource"));
            System.out.println("Internal URI selection: " +
                    decide("http://database.internal/resource"));
            System.out.println("Loopback URI selection: " +
                    decide("http://127.0.0.1/resource"));
        } finally {
            worker.shutdownNow();
            restore("http.proxyHost", oldHost);
            restore("http.proxyPort", oldPort);
            restore("http.nonProxyHosts", oldExceptions);
        }
    }
    private static void restore(String key, String original) {
        if (original == null) System.clearProperty(key);
        else System.setProperty(key, original);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ProxyPropertyScopeDemo.java
java -Djava.net.useSystemProxies=false ProxyPropertyScopeDemo
```

**Stdout đã kiểm chứng:**

```text
Main thread property: 192.0.2.10
Worker thread property: 192.0.2.10
External URI selection: HTTP:192.0.2.10:8181
Internal URI selection: DIRECT
Loopback URI selection: DIRECT
```

### Tại sao demo này đáng chú ý?

1. Main thread và thread của `ExecutorService` nhìn thấy cùng `http.proxyHost`, vì đây là **system property toàn tiến trình**, không phải thread-local property.
2. `ProxySelector.getDefault().select` trả HTTP proxy cho một URI ngoài danh sách exclusions, dựa trên giá trị mới được đặt ở runtime.
3. `*.internal` và `127.*` khiến internal/loopback URIs được chọn `DIRECT`. Đối tượng `ProxySelector` đã có sẵn vẫn có thể lookup system properties khi chọn proxy mới.
4. Đây là **default proxy selector của Java 17**. Nếu ứng dụng đã gọi `ProxySelector.setDefault(customSelector)` hoặc `HttpClient.Builder.proxy(custom)`, kết quả phải xét implementation/policy riêng, không tự khẳng định mọi client nhìn thấy toàn cục giống nhau.
5. Việc chọn proxy chỉ trả một **quyết định routing dự định**, không xác nhận proxy `192.0.2.10:8181` đang chạy. Demo **không thực hiện HTTP request hoặc TCP connect**.
6. `finally` khôi phục ba system property cũ. Tuy nhiên đó chỉ làm demo an toàn hơn trong process thử nghiệm: khi có requests đồng thời ở thời điểm đang đổi property, chúng **vẫn có thể quan sát giá trị tạm thời**. Trong production multi-threaded, tránh kiểu save–set–restore của global properties để cấu hình một request.

### Một lỗi khó tìm: test chạy song song

Trong suite JUnit chạy nhiều tests đồng thời, test A đổi `http.proxyHost`; test B gửi HTTP request; cả hai thuộc **cùng JVM**. Test B có thể bất ngờ dùng proxy giả của A. Dù A restore property trong finally, race vẫn có thể đã xảy ra. Chạy tests có mutable global properties trong **JVM riêng**, hoặc dùng explicit per-client/per-request proxy config mà không đổi global.

## 8. `java.net.useSystemProxies`: cái nào cần set từ startup?

Một hiểu lầm rất thường gặp:

```java
// ANTI-PATTERN nếu mong bật hệ thống proxy ngay lập tức:
System.setProperty("java.net.useSystemProxies", "true");
```

JDK 17 ghi rõ `java.net.useSystemProxies` **được đọc một lần lúc startup**. Mệnh lệnh trên chỉ thay property string, không phải API “làm lại” mọi cấu hình OS proxy trong JVM đang chạy. Nếu muốn dùng OS proxy default, đặt từ lúc launcher:

```bash
java -Djava.net.useSystemProxies=true MyApp
```

**Còn `http.proxyHost` thường tra cứu lại được**, như demo phần 7. Hai thuộc tính nằm trong một chủ đề “proxy” nhưng **có thời điểm đọc khác nhau**. Vì vậy không đủ chỉ nhớ rằng “cấu hình proxy có thể đổi runtime”; phải nhìn **chính xác key**.

### Hành vi khi OS proxy thay đổi

Mặc dù bật `useSystemProxies=true` lúc startup, không mặc định mọi thay đổi setting của OS được phản ánh tức thì cho mọi JVM/connection. OS notification, native integration, JVM proxy selector, proxy PAC và caching đều có thể ảnh hưởng. Kiểm tra trên đúng JDK/OS và tạo **request mới** sau thay đổi; giữ kết nối cũ không có nghĩa proxy route đã thay.

## 9. HTTP URL protocol handler: properties được lấy một lần

Trong tài liệu Networking Properties Java 17, nhóm `Misc HTTP URL stream protocol handler properties` bao gồm:

- `http.agent`: cung cấp User-Agent, giá trị `Java/<version>` được append theo contract.
- `http.keepAlive`: default `true`; điều khiển khả năng dùng persistent HTTP/1.1 connections.
- `http.maxConnections`: default `5`; số **idle connections mỗi destination** có thể giữ trong cache khi keep-alive bật.
- `http.keepAlive.time.server` và `http.keepAlive.time.proxy`: điều khiển idle timeout fallback trong trường hợp server/proxy chưa cung cấp timeout; đơn vị giây.
- `http.maxRedirects`: default `20`; số redirects tự follow cho một request của protocol handler.
- `http.auth.digest.validateServer`, `http.auth.digest.validateProxy`, `http.auth.digest.cnonceRepeat`: tham số của Digest authentication.
- `http.auth.ntlm.domain`: cấu hình domain cho NTLM.
- `jdk.http.maxHeaderSize`: hạn mức response header section; default 393216 bytes trong JDK 17.

**Tài liệu JDK 17 đánh dấu nhóm này được kiểm tra một lần lúc startup**. Nếu định thay `http.keepAlive` để debug connection reuse, đặt bằng `-D` trước launch và chạy lại một JVM mới. Đừng đổi sau khi HTTP handler đã chạy rồi kết luận pool phải xóa ngay.

### Điều gì xảy ra khi chỉ thay Java String?

Ví dụ:

```java
System.setProperty("http.keepAlive", "false");
```

Sau đó `System.getProperty("http.keepAlive")` có thể trả `false`, nhưng **điều đó không chứng minh handler đã bỏ persistent connections** theo runtime. Giá trị cho networking behavior được quyết định bởi hợp đồng **startup-only**, không chỉ bởi map. Ngoài ra, connection đã đang được sử dụng không thể bị “quay ngược thời gian” vì một mutable string.

### `http.agent` là ví dụ dễ đo nhất

Ta có thể quan sát `User-Agent` do Java legacy HTTP URL handler gửi trên **loopback server**. Cấu hình `-Dhttp.agent=START` từ lúc launch; sau request đầu, gọi `System.setProperty("http.agent","CHANGED")`; request thứ hai vẫn gửi **cùng User-Agent đã được xác định trước** trong môi trường kiểm thử. Không cần dựa vào TLS/network firewall hoặc DNS.

## 10. Java 17+: chứng minh `http.agent` không đổi theo mutation runtime

Chương trình mở server HTTP loopback, nhận hai GET requests, ghi lại header User-Agent. Sau request đầu, client thay system property `http.agent` từ START sang CHANGED, rồi gửi request thứ hai trong **cùng JVM**.

**Tệp `LegacyAgentTimingDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class LegacyAgentTimingDemo {
    private static void get(URL url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setConnectTimeout(2000);
        c.setReadTimeout(2000);
        try (InputStream body = c.getInputStream()) {
            body.readAllBytes();
        } finally {
            c.disconnect();
        }
    }
    public static void main(String[] args) throws Exception {
        if (!"START".equals(System.getProperty("http.agent")))
            throw new IllegalArgumentException("Run with -Dhttp.agent=START");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        List<String> seen = new ArrayList<>();
        server.createContext("/agent", exchange -> {
            try (exchange) {
                synchronized (seen) {
                    seen.add(exchange.getRequestHeaders().getFirst("User-Agent"));
                }
                byte[] bytes = "OK".getBytes(StandardCharsets.US_ASCII);
                exchange.sendResponseHeaders(200, bytes.length);
                try (var out = exchange.getResponseBody()) { out.write(bytes); }
            }
        });
        try {
            server.start();
            URL url = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/agent").toURL();
            get(url);
            System.setProperty("http.agent", "CHANGED");
            get(url);
            System.out.println("Property now: " + System.getProperty("http.agent"));
            System.out.println("First agent starts START: "
                    + seen.get(0).startsWith("START "));
            System.out.println("Second agent same as first: "
                    + seen.get(1).equals(seen.get(0)));
            System.out.println("Requests received: " + seen.size());
        } finally {
            server.stop(0);
        }
    }
}
```

Chạy trong thư mục chứa file với **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 LegacyAgentTimingDemo.java
java -Dhttp.agent=START LegacyAgentTimingDemo
```

**Stdout đã được biên dịch/chạy kiểm chứng:**

```text
Property now: CHANGED
First agent starts START: true
Second agent same as first: true
Requests received: 2
```

**Giải thích:**

1. Lệnh `-Dhttp.agent=START` làm property hiện diện **ngay khi JVM khởi động**.
2. Java HTTP URL handler tạo User-Agent từ property đã đọc lúc initialization. JDK có thể append `Java/<version>`, nên demo kiểm tra prefix START thay vì phụ thuộc version đang chạy.
3. `System.setProperty` thay property map thành CHANGED, được xác nhận ở dòng đầu output.
4. Request thứ hai vẫn mang User-Agent giống request đầu trong môi trường kiểm thử. Điều đó minh họa **giá trị startup/cached khác với chuỗi trả từ System.getProperty**.
5. Demo dùng `HttpURLConnection`, **không phải** `java.net.http.HttpClient` hiện đại. Đừng lấy phép thử này làm contract User-Agent cho mọi HTTP library (OkHttp, Apache HttpClient, Netty) hoặc cho Java HTTP client module.
6. Việc header được ghi ra server không có nghĩa một connection TCP mới được tạo mỗi request. HTTP keep-alive có thể tái sử dụng socket, nhưng điều đó không làm thay đổi kết luận về User-Agent.
7. Chương trình dùng `127.0.0.1` và port động; không kết nối tới Internet. `seen` chỉ được handler thêm một entry cho mỗi request, và main đọc sau khi nhận đủ responses.

**Kết luận:** thay property string ở runtime không phải bằng chứng rằng property startup-only đã có hiệu lực với handler đang chạy.

## 11. DNS cache TTL là **security property**, không phải `-D` networking thông thường

Hai keys quan trọng:

- `networkaddress.cache.ttl`: thời gian (giây) lưu kết quả name resolution **thành công**. Java 17 mô tả 0 = không cache, số âm = cache vô hạn, mặc định phụ thuộc security manager/JDK implementation.
- `networkaddress.cache.negative.ttl`: thời gian lưu kết quả name resolution **thất bại**. Tài liệu Java 17 nêu mặc định 10 giây; 0 = không cache, số âm = giữ vô hạn.

**Lưu ý:** đây là **Java Security properties** của cơ chế cache trong `java.net.InetAddress`, **không phải system properties chuẩn**. Tài liệu JDK 17 nói rõ chúng **không được cấu hình bằng `-D` hoặc `System.setProperty`** theo cách dùng chuẩn, mà qua Java security property mechanism.

### Cấu hình đúng cho JDK 17

Trong một môi trường JDK được kiểm soát, cấu hình security property bằng file `$JAVA_HOME/conf/security/java.security` hoặc qua cơ chế bảo mật được JDK hỗ trợ. Nếu ứng dụng cần thay `Security.setProperty` khi chạy, phải xem **thời điểm cache/resolver đã khởi tạo** và tài liệu của implementation; thay được chuỗi security property không tự chứng minh cơ chế DNS cache đang dùng TTL mới.

```java
// Trích đoạn minh họa; dùng trong chương trình cấu hình sớm, có kiểm soát.
String current = java.security.Security.getProperty(
        "networkaddress.cache.negative.ttl");

// Khác với System.setProperty:
java.security.Security.setProperty(
        "networkaddress.cache.negative.ttl", "7");
```

**Không khuyến khích hot-change DNS TTL trong một Java server đang phục vụ traffic.** Một thay đổi có thể tác động DNS lookups ở toàn JVM, và kết quả cache cũ có thể vẫn còn, gây lệch giữa instances/threads. Nếu muốn một trạng thái ổn định, cấu hình **trước khi resolver được sử dụng** và kiểm thử theo đúng JDK, rồi restart khi cần.

### Không lẫn JVM DNS cache với DNS/OS resolver cache

Một tên có thể bị cache ở nhiều tầng: JVM `InetAddress`, OS resolver, DNS daemon, DNS server, proxy hoặc sidecar. `networkaddress.cache.ttl=0` ở JVM **không xóa** các cache bên ngoài. Ngược lại, OS DNS record đã đổi không làm mọi Java connection đang mở chuyển IP mới tức thời.

### Sai lầm: “Tôi đã set -Dnetworkaddress.cache.ttl=0 mà vẫn cache”

Phương thức cấu hình sai. `System.getProperty("networkaddress.cache.ttl")` có thể trả `0` nhưng `Security.getProperty(...)` vẫn giữ giá trị khác. Đây là tình huống đáng kiểm thử đầu tiên trước khi đổ lỗi cho DNS.

## 12. Java 17+: phân biệt System property và Security property

Ví dụ thứ ba không lookup hostname nên kết quả độc lập với DNS, cache và Internet. Nó đọc security property ban đầu, ghi một **system property cùng tên** bằng `System.setProperty(...,"123")`, kiểm tra `Security.getProperty` có bị ảnh hưởng không, rồi ghi **security property** bằng `Security.setProperty(...,"7")` và đọc hai kho.

**Tệp `SecurityPropertyScopeDemo.java`:**

```java
import java.security.Security;

public class SecurityPropertyScopeDemo {
    public static void main(String[] args) {
        String key = "networkaddress.cache.negative.ttl";
        String initialSystem = System.getProperty(key);
        String initialSecurity = Security.getProperty(key);
        try {
            System.setProperty(key, "123");
            System.out.println("System property: " + System.getProperty(key));
            System.out.println("Security unchanged by System.setProperty: "
                    + java.util.Objects.equals(initialSecurity,
                        Security.getProperty(key)));
            Security.setProperty(key, "7");
            System.out.println("Security property after Security.setProperty: "
                    + Security.getProperty(key));
            System.out.println("System property still: " + System.getProperty(key));
        } finally {
            if (initialSystem == null) System.clearProperty(key);
            else System.setProperty(key, initialSystem);
            if (initialSecurity != null) Security.setProperty(key, initialSecurity);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SecurityPropertyScopeDemo.java
java SecurityPropertyScopeDemo
```

**Stdout đã kiểm chứng:**

```text
System property: 123
Security unchanged by System.setProperty: true
Security property after Security.setProperty: 7
System property still: 123
```

### Kết luận thực chất

- `System.setProperty` chỉ thay system map; không thay Security map cùng tên.
- `Security.setProperty` thay security map; không tự sửa System map.
- Việc `Security.getProperty` trả 7 **không chứng minh** resolver đã cập nhật TTL đang hoạt động. Một component có thể đã đọc TTL trước đó hoặc giữ các cache entries theo chính sách cũ.
- Demo cố khôi phục giá trị ban đầu trong `finally`. **Không nên chạy code thay security properties trong JVM production shared** vì các thread khác có thể quan sát giá trị mới trong lúc thử nghiệm.
- Nếu `initialSecurity` là `null`, đoạn demo không có API `Security.clearProperty` để xóa entry mới tạo; do đó khôi phục hoàn toàn nghĩa “unset” không được đảm bảo trong chính process demo. Đây là một lý do nữa để **chạy trong JVM riêng**, không nhúng bài test vào app production.
- Demo chỉ chứng minh **hai kho property độc lập**, không kiểm thử caching duration thật vì DNS caches có timing và OS resolver phụ thuộc môi trường.

## 13. File `conf/net.properties`: không phải file chứa mọi system property

Trong Java SE 17, JDK cung cấp file cấu hình mạng mặc định, thường nằm tại:

```text
$JAVA_HOME/conf/net.properties
```

Theo hướng dẫn networking của Java 17, cơ chế này hỗ trợ **proxy-related properties**. Không mặc định có thể đưa mọi key `java.net.*` hay `jdk.httpclient.*` vào đó rồi mong JVM đọc từ file. File `conf/net.properties` là **một nguồn giá trị mặc định** cho những settings được hỗ trợ, không phải một live config service tự đồng bộ tới mọi process.

### Thứ tự ưu tiên cần ghi nhớ

- System properties được chỉ rõ qua `-D` hoặc `System.setProperty` theo contract có thể **ghi đè giá trị mặc định từ `conf/net.properties`** cho những proxy settings hỗ trợ.
- `java.net.useSystemProxies=true` có thể lấy settings từ OS trên platforms hỗ trợ; **proxy properties khai báo trực tiếp thường ưu tiên** hơn OS defaults.
- `ProxySelector` tùy chỉnh hoặc explicit `Proxy` per request/client có thể quyết định routing theo logic khác, không nhất thiết chỉ theo các system properties.
- `conf/security/java.security` là **file cho security properties**, không phải bản sao của `conf/net.properties`.

### Khi sửa file JDK

Một process Java đang chạy thường không tự reload `conf/net.properties` sau khi file bị sửa. Nếu bạn quản lý một installation, thay file có thể ảnh hưởng **các process được launch sau đó**, không tự động thay các JVM đang chạy. Cần cân nhắc JDK upgrades, container images, read-only mounts và configuration drift. Với dịch vụ có nhiều instances, tốt hơn dùng startup flags/managed configuration theo deployment thay vì sửa JDK shared installation thủ công.

**Bài thực hành không chỉnh sửa bất kỳ file `conf/net.properties` hoặc `java.security` nào.** Điều đó giúp tránh ảnh hưởng tới những ứng dụng Java khác trên máy.

## 14. `java.net.http.HttpClient` mới và `HttpURLConnection` cũ không dùng cùng mọi cấu hình

Một sai lầm dễ gặp là đặt:

```bash
java -Dhttp.maxConnections=5 -Dhttp.keepAlive=false MyHttpApp
```

rồi cho rằng `java.net.http.HttpClient` của Java 17 chắc chắn bị giới hạn **5 active connections** và không pool. Theo JDK 17, đây là các keys được mô tả trong **HTTP URL stream protocol handler**, gắn với legacy `HttpURLConnection`. Module `java.net.http` có **nhóm JDK-specific properties riêng** và cấu hình mức client.

Ví dụ, tài liệu Java Networking JDK 17 liệt kê:

- `jdk.httpclient.connectionPoolSize`: giới hạn số connections **trong HTTP/1.1 keep-alive cache** của client mới, mặc định `0` nghĩa là không giới hạn kích thước cache theo property này. Không có nghĩa 0 active connections.
- `jdk.httpclient.keepalive.timeout`: số giây giữ HTTP/1.1 idle connection theo tài liệu JDK 17.
- `jdk.httpclient.HttpClient.log`: có thể bật logging cho Java HTTP client qua Java Logging API; cần cân nhắc header/payload/tokens.
- `jdk.httpclient.disableRetryConnect`, `jdk.httpclient.enableAllMethodRetry`: các switches liên quan retry, cần cẩn trọng với method không idempotent.
- `jdk.httpclient.redirects.retrylimit`: giới hạn attempt cho redirect/retry theo implementation.
- `jdk.httpclient.allowRestrictedHeaders`: chỉ dành cho testing theo cảnh báo JDK; không nên override restricted HTTP headers trong production để “sửa” lỗi giao thức.

**Đừng suy đoán thời điểm đọc từng `jdk.httpclient.*` bằng quy tắc “mọi proxy property dynamic”.** Các JDK-specific knobs có thể được đọc khi class/client/runtime initialization, khác theo phiên bản và không nhất thiết mang contract giống danh sách trong `java.base`. Với cấu hình tối ưu/giới hạn tài nguyên, ưu tiên **đặt lúc khởi động JVM** và xác minh trên JDK release thật.

### Cấu hình theo instance rõ hơn

```java
// Đoạn minh họa: chưa phải class độc lập.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.internal", 8080)))
        .build();
```

Cần imports `java.net.http.HttpClient`, `java.net.ProxySelector`, `java.net.InetSocketAddress` và `java.time.Duration`. Endpoint `proxy.internal` chỉ minh họa. Builder cấu hình **client object cụ thể**; không cần `System.setProperty("http.proxyHost",...)` cho mọi thư viện trong JVM.

Tuy nhiên, **một đối tượng HttpClient có thể dùng bởi nhiều threads**. Cấu hình per-client không đồng nghĩa per-thread; nếu hai yêu cầu cần proxy/tls policy khác nhau, có thể tạo các clients quản lý riêng. Không dùng thay global system properties để thay config network của mọi modules.

### Chọn proxy riêng cho một legacy URLConnection

```java
// Trích đoạn minh họa: 'url' là URL đã xác minh.
HttpURLConnection direct =
        (HttpURLConnection) url.openConnection(Proxy.NO_PROXY);
```

Cách này tạo connection **DIRECT** theo API mà không phải đổi `http.proxyHost` toàn JVM. Tuy nhiên, direct access có thể vi phạm corporate egress policy; cần dùng theo phê duyệt. `Proxy.NO_PROXY` là cách chỉ định object, không bật/bỏ OS proxy cho toàn bộ process.

## 15. System properties, environment variables và Java security settings

Một deployment có thể chứa những kiểu cấu hình:

```text
Docker/Kubernetes env:
  HTTP_PROXY=http://proxy.example.test:8080
  HTTPS_PROXY=http://proxy.example.test:8443

JVM launch flags:
  -Dhttp.proxyHost=proxy.example.test
  -Dhttp.proxyPort=8080
  -Djava.net.useSystemProxies=false

Java security configuration:
  networkaddress.cache.negative.ttl=10
```

Không coi chúng **tương đương**. Java code `System.getenv("HTTP_PROXY")` đọc environment của process; `System.getProperty("http.proxyHost")` đọc system property map; `Security.getProperty("networkaddress.cache.negative.ttl")` đọc security property map. JDK không cam kết mọi thư viện tự dịch `HTTP_PROXY` thành `http.proxyHost`.

Một framework hoặc container entrypoint **có thể** copy env vars thành `-D`, nhưng đó là logic của framework/launcher, không phải mặc định phổ quát của Java Networking. Khi debug, xem **thực tế JVM được start với tham số gì**, chứ không chỉ xem file Docker Compose.

### Cảnh báo với `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`

Một số môi trường triển khai Java dùng environment options để thêm JVM startup flags. Nếu một app nhận unexpected proxy hoặc IPv4-only mode, kiểm tra cả lệnh chạy Java và cách launcher/IDE/container thêm options. **Không in secrets** nằm trong launch flags, file cấu hình hoặc system properties ra log công khai.

### Xem JVM đang chạy

Công cụ Java như `jcmd <pid> VM.system_properties` hoặc `jcmd <pid> VM.command_line` có thể cho thấy properties và launch arguments của process khi bạn có quyền kiểm tra. **Cảnh báo:** output có thể chứa secrets/password/token; chỉ dùng trên môi trường được phép, hạn chế quyền log và redaction. Những giá trị ấy cũng không chứng minh component runtime đã áp dụng thay đổi nếu property chỉ đọc lúc startup.

## 16. Thời điểm thay đổi có tạo race không?

Có. Một `System.setProperty` là thao tác cập nhật một key, nhưng nhiều key phối hợp như `http.proxyHost` + `http.proxyPort` + `http.nonProxyHosts` **không được đổi atomically như một cấu hình duy nhất**. Trong khoảng giữa các lệnh:

```text
Thread A (config updater)                 Thread B (request)
  setProperty(proxyHost="new")                │
        │                                      ├── đọc proxyHost=new
        ├── setProperty(proxyPort="8181")      │
        │                                      └── đọc proxyPort=OLD
        └── setProperty(nonProxyHosts=...)     │

Kết quả: B có thể thấy một cấu hình bị trộn giữa cũ và mới.
```

Thử nghiệm `ProxyPropertyScopeDemo` thể hiện ít nhất việc **cùng property hiển thị ở nhiều thread**. Trong hệ thống nhiều request đồng thời, việc đổi nhiều keys tuần tự có thể làm proxy route không nhất quán; không dựa vào việc **mỗi `setProperty` riêng lẻ thread-safe** để kết luận cả một nhóm properties được cập nhật atomically.

### Per-request configuration và immutable config snapshot

Một mẫu tốt hơn cho ứng dụng:

1. Ở khởi động, parse env/flags/config file thành một **immutable NetworkConfig**.
2. Kiểm tra host, port, timeout, TLS options, allowed proxy và security policy.
3. Tạo client object phù hợp với config; đăng ký object ấy cho các modules/threads dùng chung.
4. Nếu cần hot reload, tạo **client mới** với config snapshot mới, chuyển traffic có kiểm soát, xử lý drain/close client cũ theo API.
5. Không thay `System.setProperty` trong mỗi HTTP request để “chọn proxy tạm thời” hoặc “chuyển IPv6 mode cho thread hiện tại”.

### Thread-local có giúp không?

Không thể dùng `ThreadLocal` để tự biến một system property thành thread-local: `System.getProperty` vẫn đọc shared map của JVM. Muốn cấu hình khác nhau mỗi request, truyền thông số qua arguments/client instance/context, hoặc sử dụng `ProxySelector` per-client biết cách đọc một context phù hợp. Không đổi global default khi thread khác đang hoạt động.

## 17. Debug tình huống: giá trị map đã đổi nhưng traffic vẫn như cũ

Đây là tình huống quan trọng nhất của bài:

```text
Tôi gọi System.setProperty("java.net.preferIPv4Stack","true")
System.getProperty(...) trả "true"
Nhưng connection vẫn có IPv6!
```

**Cách đọc đúng:** Java 17 tài liệu nói property đó **startup-only**, nên không có lý do tin system property string đổi sẽ reinitialize native sockets. Kiểm tra lệnh launch, restart process và đo IPv4/IPv6 behavior thật.

Một số tình huống khác:

| Triệu chứng | Câu hỏi cần hỏi trước | Cách xử lý |
|---|---|---|
| Đổi `java.net.useSystemProxies` lúc runtime nhưng OS proxy không áp dụng | Có phải property startup-only? | Đặt `-D` từ lúc launch, restart và kiểm tra OS support |
| Đổi `http.proxyHost` mà request mới vẫn đi DIRECT | Có `http.nonProxyHosts` match? Có custom selector/client? | Kiểm tra `ProxySelector` và endpoint thực |
| Request cũ vẫn dùng proxy cũ dù đổi property | Connection đã thiết lập hoặc client snapshot chưa? | Theo dõi lifecycle; không chuyển socket bằng map mutation |
| `System.getProperty(networkaddress.cache.ttl)` đổi nhưng DNS vẫn cache | Có đang dùng nhầm system thay security property? | Dùng `Security.getProperty`, config sớm, kiểm tra DNS cache |
| Legacy User-Agent không đổi sau `setProperty("http.agent",...)` | `http.agent` có startup-only? | Đặt trước JVM launch |
| Đặt `http.maxConnections=5` nhưng HttpClient mới có nhiều connections | Property thuộc legacy handler? | Kiểm tra `jdk.httpclient.connectionPoolSize` và actual client module |
| `HTTP_PROXY` đã set nhưng Java không qua proxy | Launcher/framework có map env sang Java properties không? | Cấu hình `-D` hoặc explicit ProxySelector |
| `System.getProperty("http.proxyHost")` bị đổi giữa test | Module/test khác đang mutate global? | Chạy test cô lập hoặc cấu hình per-client |
| `http.nonProxyHosts="*.internal"` không chặn HTTPS khỏi proxy | Đúng property exclusions và hostname được xét? | JDK 17 HTTPS handler dùng chung `http.nonProxyHosts`; xem proxy policy |
| App chạy nhiều pods có proxy behavior khác nhau | Mỗi pod có JVM flags và image JDK giống nhau? | So startup/config/version/OS/proxy và rollout |
| Thay `conf/net.properties` nhưng process cũ không đổi | Process có reload file không? | Thường cần restart JVM; không dựa vào file change |
| Bật HTTP client debug logging làm lộ headers | Logger scope và secrets redaction đã ổn? | Chỉ bật có kiểm soát, giảm chi tiết logging |

### Quy trình điều tra từng bước

1. Xác định **đúng tên key** và nhóm API: `java.net`, legacy `HttpURLConnection`, `java.net.http`, `javax.net.ssl` hay Security.
2. Tìm tài liệu **đúng JDK release**, chú thích **startup-only/dynamic/component-cached**.
3. Ghi **actual startup options** của process đang lỗi, không chỉ giá trị map hiện tại.
4. Kiểm tra `System.getProperty` và khi phù hợp `Security.getProperty`; không coi chúng là cùng nguồn.
5. Xác định object `HttpClient/ProxySelector/Socket` đã được tạo **trước hay sau** khi thay cấu hình.
6. Với proxy, instrument `ProxySelector.select(URI)` hoặc HTTP tracing thích hợp, không dùng route đoán theo hostname.
7. Với IPv4/IPv6, quan sát local/remote socket address và OS capabilities, không chỉ `localhost` DNS order.
8. Với DNS, kiểm tra Java InetAddress cache, OS DNS, DNS TTL và runtime policy; không chỉ DNS server record.
9. Thử **khởi động một JVM mới với `-D`** và chạy phép đo tương ứng trên cùng JDK/OS.
10. Nếu là config runtime shared, loại bỏ race bằng per-client configuration hoặc controlled reload.

## 18. Phân biệt kiểm thử property với thay đổi hệ thống production

Các bài test trong bài được thiết kế **an toàn trong JVM test riêng**:

- Không chỉnh OS proxy registry, DNS resolver hay route.
- Không sửa file `conf/net.properties`/`java.security`.
- Không kết nối tới proxy “giả” vì `ProxySelector.select` chỉ lập kế hoạch routing.
- Không gọi tới tên miền `example.test` hay IP `192.0.2.10` qua mạng; chúng chỉ là input để mô tả routing.
- HTTP server của `LegacyAgentTimingDemo` lắng nghe **127.0.0.1** trên port động.
- DNS security-property test không thực hiện DNS resolution.

**Đừng chép phần `System.setProperty` có tính thử nghiệm vào một application server nhiều tenant**. Những thay đổi này là global đối với các thread trong JVM hiện tại, có thể ảnh hưởng những thư viện không liên quan. Nếu thư viện không hỗ trợ per-instance config và cần property startup-only khác nhau, giải pháp sạch là **tách thành các JVM processes khác nhau**, không thử giả lập thread-local global config.

### Lời khuyên về bảo mật cấu hình

- Không đưa proxy password vào URL, system property hoặc debug log nếu có API credential management tốt hơn.
- `java.net.socks.password`/các cấu hình authentication có thể là secrets; nếu dùng, bảo vệ process arguments và diagnostic dumps.
- Đừng giảm TLS verification chỉ để kiểm thử routing; proxy tunneling có thể có authentication và certificate constraints riêng.
- `jdk.httpclient.allowRestrictedHeaders` được JDK cảnh báo dành cho testing; không bật trong production để tự thêm `Host`, `Content-Length`, `Connection` tùy tiện.
- Khi truy vấn `System.getProperties()` cho observability, chỉ log **allowlist non-sensitive keys**, không dump toàn bộ properties.
- Khi hot-reload proxy, đảm bảo không phá allowlist, egress control, DNS pinning/trust boundaries.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `System.setProperty("java.net.preferIPv4Stack","true")` ngay sau khi start app có chắc chuyển socket mode sang IPv4-only không?  
**Đáp án:** Không. Đây là startup-only theo Java 17. Nên đặt `-D` trước khi JVM launch.

**Câu 2.** Các threads trong cùng JVM có mỗi thread một bản `System.getProperties()` độc lập không?  
**Đáp án:** Không. Chúng truy cập shared system property map, vì vậy mutation có thể ảnh hưởng thread khác.

**Câu 3.** Process A gọi `System.setProperty("http.proxyHost","X")`, process B có tự dùng X không?  
**Đáp án:** Không. Hai JVM có system property maps riêng, trừ khi bên ngoài cấp cấu hình giống nhau khi launch.

**Câu 4.** `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses` có cùng mục đích không?  
**Đáp án:** Không. Một thuộc tính liên quan IPv4-only socket stack, thuộc tính kia là preference/order của địa chỉ IPv4/IPv6 từ name resolution.

**Câu 5.** `java.net.useSystemProxies` có thể bật lên hoàn toàn bằng `System.setProperty` giữa một HTTP request đã gửi không?  
**Đáp án:** Không được dựa vào đó. Java 17 đánh dấu property này startup-only.

**Câu 6.** `http.proxyHost` có thể ảnh hưởng request mới khi thay trong runtime không?  
**Đáp án:** Có thể, với default proxy selector/handler tra cứu lại property, như demo; không di chuyển socket đang mở.

**Câu 7.** `http.nonProxyHosts` dùng dấu phẩy hay dấu pipe để phân cách patterns theo JDK 17?  
**Đáp án:** Dấu `|`; wildcard `*` dùng match hostnames.

**Câu 8.** Một request https có dùng `https.nonProxyHosts` thay `http.nonProxyHosts` theo JDK 17 legacy handler?  
**Đáp án:** Không theo tài liệu này; HTTPS URL handler sử dụng `http.nonProxyHosts`.

**Câu 9.** Vì sao không dùng `http.maxConnections` để cam kết giới hạn tất cả active connections của `HttpClient` mới?  
**Đáp án:** Nó mô tả idle cache per-destination của legacy URL handler, không phải hard limit active connections cho module client mới.

**Câu 10.** `http.agent` đã được đọc lúc startup; thay `System.setProperty` lúc runtime có làm legacy User-Agent chắc chắn đổi ngay không?  
**Đáp án:** Không. Demo thấy header không đổi dù property map thay.

**Câu 11.** `networkaddress.cache.ttl` thuộc `System.getProperties()` hay Security properties?  
**Đáp án:** Theo Java 17 đó là **security property**, đọc bằng `Security.getProperty`.

**Câu 12.** Đặt `-Dnetworkaddress.cache.negative.ttl=0` có phải cách chính thức để tắt DNS negative cache?  
**Đáp án:** Không. JDK 17 hướng dẫn dùng security property mechanism, không phải system `-D`.

**Câu 13.** `Security.setProperty(key,"7")` rồi `Security.getProperty` trả 7; có chắc mọi cache DNS lập tức đổi TTL không?  
**Đáp án:** Không. Cơ chế sử dụng property có thể đã cache/snapshot. Kiểm tra JDK implementation và lifecycle.

**Câu 14.** Sửa `$JAVA_HOME/conf/net.properties` có tự thay JVM đã chạy không?  
**Đáp án:** Không được giả định. Đây là file cấu hình, thường cần restart JVM để nạp trạng thái mới.

**Câu 15.** Có thể đặt mọi property `java.net.*` vào `conf/net.properties` rồi mong Java 17 dùng không?  
**Đáp án:** Không. Hướng dẫn Java 17 giới hạn cơ chế file này cho các proxy-related properties được hỗ trợ.

**Câu 16.** `System.getenv("HTTP_PROXY")` và `System.getProperty("http.proxyHost")` có tương đương không?  
**Đáp án:** Không. Environment variables và JVM system property maps là cơ chế khác nhau; launcher/framework có thể bridge nhưng không phải tự động phổ quát.

**Câu 17.** Java HTTP client logging flag `jdk.httpclient.HttpClient.log` có thể gây rủi ro gì?  
**Đáp án:** Logs có thể chứa metadata/headers nhạy cảm; cần kiểm soát log destination, level và redaction.

**Câu 18.** Nếu service có hai tenants cần hai proxies, nên thay `http.proxyHost` trước mỗi request?  
**Đáp án:** Không. System property là global có race; dùng per-client/per-request proxy config hoặc cách ly processes.

**Câu 19.** Một test thay host và port bằng hai lần `setProperty` có bảo đảm thread khác đọc cả hai giá trị cùng version không?  
**Đáp án:** Không. Cả bộ config không có atomic update, nên có thể thấy host mới/port cũ.

**Câu 20.** Để chứng minh property startup-only, nên test trong một JVM bằng cách đổi `System.setProperty` hay chạy hai JVM khác nhau bằng `-D`?  
**Đáp án:** Chạy **hai JVM riêng** với startup flags khác nhau và quan sát hành vi, như demo IPv4/IPv6.

**Câu 21.** `http.keepAlive` có phải TCP `SO_KEEPALIVE` không?  
**Đáp án:** Không. Một bên điều chỉnh HTTP persistent connection reuse của legacy handler, bên kia là TCP keepalive probes.

**Câu 22.** `ProxySelector.getDefault()` luôn tôn trọng `http.proxyHost` nếu ứng dụng đã `setDefault(custom)`?  
**Đáp án:** Không. Selector custom có thể có logic khác và không đọc system property ấy.

**Câu 23.** Vì sao phải kiểm tra Java version/update release khi so `jdk.httpclient.*` settings?  
**Đáp án:** Vì đây là properties JDK-specific, mặc định/hành vi có thể thay đổi; không mặc định áp dụng quy tắc của nhóm java.net legacy.

**Câu 24.** Nếu đã chọn proxy cho một socket và sau đó property host đổi, socket có tự kết nối tới proxy mới không?  
**Đáp án:** Không. Lựa chọn routing cho connection đã thiết lập không thay tự động; request/connection mới cần chọn lại.

## 20. Checklist áp dụng và nguồn đáng tin cậy

### Checklist trước khi cấu hình

- [ ] Ghi **đúng property name**, API/module, JDK version và **documented default**.
- [ ] Xác định **system property**, **security property**, file `conf/net.properties`, OS proxy hay config per-client.
- [ ] Xác định **JVM process** nào nhận cấu hình; không coi nhiều pods/services là một JVM.
- [ ] Xác định thuộc tính **startup-only** hay **dynamic**; với JDK-specific property đọc tài liệu module/implementation.
- [ ] Với startup-only, thêm `-D` vào launcher trước khi process start, **restart JVM** rồi xác minh.
- [ ] Với proxy động, chỉ kỳ vọng request/selection mới quan sát giá trị; socket đang chạy không tự reroute.
- [ ] Không dùng `System.setProperty` per-request trong JVM nhiều threads.
- [ ] Không trộn `http.maxConnections` của legacy URL handler với `jdk.httpclient.connectionPoolSize` của modern client.
- [ ] Với DNS TTL dùng **Security property** thay vì `-D` thông thường; không đoán OS DNS cache cũng reset.
- [ ] Không tin chỉ `System.getProperty` để kết luận native networking state đã thay.
- [ ] Đo thực tế `ProxySelector.select`, local/remote IP, TCP connections và HTTP handler behavior với telemetry có quyền.
- [ ] Tách startup config, live config reload và mutable global state, tránh race hai property values.
- [ ] Giới hạn logs, không dump toàn bộ system properties hoặc secrets.
- [ ] Dùng **JVM test riêng** cho mọi phép thử thay global security/system properties.
- [ ] Khi production cần hai network policies khác nhau, chọn instance config hoặc process isolation theo contract.

**Kết luận:** trong Java Networking, “property nằm trong `System`” **không** đồng nghĩa “đọc ở mọi lần dùng”; “đã thay `System.setProperty`” **không** đồng nghĩa “network stack đã đổi”; và “toàn cục” thường có nghĩa **toàn JVM process**, chứ không phải mọi Java processes. Hãy biết **property thuộc kho nào, được đọc lúc nào và tác động tới đối tượng nào** rồi mới chỉnh cấu hình.

### Tài liệu chính thức (Java SE 17)

- [Networking Properties — java.net IPv4/IPv6, proxies, HTTP handler, DNS cache](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html).
- [Java Networking — các system/proxy/HTTP Client properties của JDK 17](https://docs.oracle.com/en/java/javase/17/core/java-networking.html).
- [System — `getProperty` / `setProperty` và lưu ý khi đổi system property chuẩn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html).
- [Security — `getProperty` / `setProperty` cho security properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Security.html).
- [InetAddress — DNS cache TTL và negative cache](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html).
- [ProxySelector — `getDefault`/`setDefault`/`select`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html).
- [HttpClient — `newBuilder`/`proxy` và lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [HttpURLConnection — legacy HTTP URL protocol handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html).
