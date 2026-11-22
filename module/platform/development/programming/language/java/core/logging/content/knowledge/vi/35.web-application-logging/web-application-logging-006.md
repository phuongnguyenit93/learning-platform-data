# Client address trong logging của ứng dụng web Java

## 1. Client address là gì?

Trong logging ứng dụng web, **client address** thường chỉ địa chỉ mạng của phía gửi request, chủ yếu là **địa chỉ IP** và đôi khi là **cổng nguồn**. Thông tin này hữu ích để điều tra sự cố kết nối, thống kê lỗi theo nguồn, truy dấu yêu cầu hoặc nhận biết các hành vi bất thường.

Ví dụ một event truy cập được ghi có cấu trúc:

~~~text
event=http_request_finished method=GET route=/orders/{id}
status=200 durationMs=18 requestId=req-001
peerIp=10.0.0.10 clientIp=203.0.113.9 clientIpSource=TRUSTED_EDGE
~~~

Địa chỉ trong ví dụ thuộc các dải IP dành cho minh họa và mạng nội bộ. Trường `peerIp` và `clientIp` **không nhất thiết cùng một giá trị** khi có reverse proxy. `requestId` dùng để tương quan các log thuộc cùng request; không được dùng access token hay cookie thay cho request ID.

Ba khái niệm cần phân biệt:

- **Socket peer / remote peer:** IP của đầu bên kia kết nối TCP mà máy chủ Java đang nhìn thấy. Nếu kết nối đi qua proxy, đó thường là IP **của proxy**.
- **Logical/original client IP:** IP của phía khởi tạo yêu cầu trước các proxy, nếu có một chuỗi chuyển tiếp đáng tin và chính sách xác định nguồn hợp lệ.
- **User identity:** người dùng, tài khoản hoặc service đã được xác thực. **Không thể kết luận danh tính hay quyền truy cập chỉ từ địa chỉ IP**: nhiều người có thể dùng chung NAT/VPN/proxy, IP có thể thay đổi và dữ liệu proxy có thể bị giả mạo.

**Client address không phải địa chỉ mà HTTP `Host` hoặc `:authority` yêu cầu truy cập.** `Host` mô tả đích HTTP, không chứng minh nguồn kết nối. Cũng không nên gọi việc lấy địa chỉ từ header là “lấy IP thật” nếu chưa nêu rõ mô hình tin cậy.

## 2. Vì sao địa chỉ client có thể thay đổi qua từng lớp?

Một kiến trúc web có thể là:

~~~text
Browser (203.0.113.9)
      |
      v
CDN / Edge proxy
      |
      v
Load balancer (10.0.0.5)
      |
      v
Reverse proxy (10.0.0.10)
      |
      v
Java application
~~~

Ứng dụng Java thường chỉ nhìn thấy **peer của kết nối trực tiếp**: chẳng hạn `10.0.0.10`. Thông tin địa chỉ client gốc có thể được proxy chuyển tiếp qua metadata HTTP hoặc qua cơ chế ở lớp transport, nếu hạ tầng được cấu hình hỗ trợ.

Các lý do phổ biến khiến client address khác peer address:

1. **Reverse proxy/load balancer:** TLS có thể được kết thúc ở ingress, rồi proxy tạo kết nối mới tới Java.
2. **CDN/WAF:** nhiều request vào hệ thống đi qua một nhóm địa chỉ của nhà cung cấp.
3. **Service mesh/gateway:** request chuyển qua sidecar hoặc proxy nội bộ.
4. **NAT/CGNAT:** nhiều thiết bị chia sẻ một địa chỉ IP công cộng; phía server không biết IP riêng của thiết bị nếu không có thông tin bổ sung đáng tin.
5. **VPN/corporate proxy:** IP công khai là điểm thoát của mạng trung gian.
6. **IPv4 và IPv6:** một người dùng có thể đi qua nhiều giao thức/địa chỉ theo thời gian.

Do đó, logging nên phân biệt **địa chỉ quan sát trực tiếp** với **địa chỉ suy ra từ proxy** và ghi rõ **nguồn xác định** nếu chính sách cho phép lưu các trường này.

## 3. Lấy remote peer trong Java

### 3.1. JDK HttpServer

Với HTTP server đơn giản của JDK:

~~~java
import com.sun.net.httpserver.HttpExchange;
import java.net.InetSocketAddress;

// Doan ma tich hop trong HttpHandler.handle(HttpExchange exchange).
InetSocketAddress peer = exchange.getRemoteAddress();
String peerIp = peer.getAddress().getHostAddress();
int peerPort = peer.getPort();
~~~

`exchange.getRemoteAddress()` trả về remote address của **kết nối mà HttpServer nhận**. Trong một triển khai proxy, giá trị này thường là địa chỉ proxy gần Java nhất. `getAddress()` trả về `InetAddress` khi socket address đã được resolve; đoạn trên giả định trạng thái đó trong request thực của JDK HttpServer. `getHostAddress()` lấy dạng text IP, không phải danh tính người dùng.

Phần port từ `getPort()` là **remote source port của kết nối TCP**, thường tạm thời và thay đổi khi kết nối mới được tạo. Đừng nhầm với port HTTP của server hoặc với mã nhận diện người dùng lâu dài.

### 3.2. Servlet/Jakarta Servlet và Spring

Trong Servlet API, ứng dụng thường có thể đọc:

~~~java
// Doan tich hop, can Servlet/Jakarta Servlet API va request hien huu.
String remoteAddr = request.getRemoteAddr();
int remotePort = request.getRemotePort();
~~~

Ý nghĩa của `getRemoteAddr()` phụ thuộc đường kết nối và **cấu hình container/filter/valve**. Trong một số triển khai, container hoặc cơ chế xử lý forwarded header đã được cấu hình có thể thay đổi địa chỉ mà API cấp cao trả về. Đừng giả định mọi ứng dụng Servlet đều thấy IP gốc hoặc đều thấy IP proxy; hãy kiểm tra chính xác cấu hình runtime.

Trong Spring MVC, `HttpServletRequest` vẫn là một nguồn thường được dùng. Nhưng nếu hệ thống tin các forwarded headers qua container/framework, chính sách tin cậy phải được đặt ở lớp tương ứng; **không tự đọc header không kiểm soát trong controller rồi gọi nó là client IP**.

**Không dùng reverse DNS** (`getHostName()`) chỉ để logging địa chỉ nguồn: DNS lookup có thể tăng độ trễ, kết quả thay đổi và tên miền không phải bằng chứng nhận diện. Với mục đích log IP, thường chọn `getHostAddress()`.

## 4. X-Forwarded-For, Forwarded và X-Real-IP

Một số hạ tầng chuyển thông tin qua HTTP header:

| Header | Dạng thường gặp | Điều cần lưu ý |
| --- | --- | --- |
| `X-Forwarded-For` | `203.0.113.9, 10.0.0.5` | De-facto header, thường là danh sách IP qua các proxy; không phải bảo đảm về nguồn |
| `Forwarded` | `for=203.0.113.9;proto=https` | Header chuẩn hóa theo RFC 7239; có cú pháp phức tạp hơn |
| `X-Real-IP` | `203.0.113.9` | Quy ước của một số proxy; không được bảo đảm tồn tại |
| Header của CDN cụ thể | Tùy nhà cung cấp | Chỉ tin khi request đi qua đúng hạ tầng và hạ tầng chặn/ghi đè dữ liệu giả |

`X-Forwarded-For` (XFF) có thể được bổ sung qua từng proxy:

~~~text
X-Forwarded-For: 203.0.113.9, 10.0.0.5
~~~

Quy tắc “lấy **IP đầu tiên** bên trái” là **không an toàn nếu giá trị có thể bị client cung cấp tùy ý**. Một attacker có thể tự gửi:

~~~text
X-Forwarded-For: 1.2.3.4
~~~

Nếu server nhận trực tiếp request này và tin vào header, log có thể ghi sai `clientIp=1.2.3.4` dù peer thực sự khác. Header HTTP là **dữ liệu do bên gửi có thể kiểm soát**, trừ khi có một chuỗi proxy tin cậy đứng trước ứng dụng và thiết lập/chuẩn hóa header theo chính sách.

**Cú pháp `Forwarded` còn phức tạp hơn XFF:** có tham số `for`, `by`, `host`, `proto`, giá trị có dấu nháy, địa chỉ IPv6 trong dấu ngoặc vuông, cổng, giá trị `unknown` hoặc obfuscated identifier. Không phân tích header này bằng cách chỉ cắt chuỗi theo dấu phẩy, dấu hai chấm hay lấy substring đầu tiên.

Đối với IPv6, `2001:db8::1` chứa nhiều dấu `:`; thao tác `split(":")` để lấy IP từ một giá trị kiểu `[2001:db8::1]:12345` rất dễ sai. Nếu cần phân tích `Forwarded` đầy đủ, ưu tiên bộ xử lý được kiểm thử của web server/framework hoặc thư viện hỗ trợ đúng ngữ pháp.

## 5. Mô hình tin cậy: bước quan trọng nhất

Để lấy một địa chỉ logical client từ metadata proxy, trước hết phải có câu trả lời cho câu hỏi: **request này có thực sự đến từ một proxy mà hệ thống tin cậy không?**

Thiết kế an toàn thường có các lớp:

1. **Giới hạn đường vào Java:** backend không cho client ngoài Internet kết nối trực tiếp, trừ khi có chủ đích. Dùng cấu hình mạng, firewall, service mesh, mTLS hoặc giới hạn nguồn phù hợp.
2. **Cấu hình danh sách proxy tin cậy:** IP/CIDR hoặc identity theo hạ tầng được quản lý; không tin mọi địa chỉ private hay mọi `X-Forwarded-For`.
3. **Chuẩn hóa tại edge:** proxy đầu tiên được phép nhận traffic công khai nên **xóa/ghi đè** các header forward không đáng tin, hoặc áp đúng thuật toán nối chuỗi và chính sách trusted hops.
4. **Xác minh immediate peer:** ứng dụng chỉ diễn giải metadata forward khi kết nối thực sự đi từ proxy tin cậy.
5. **Chọn địa chỉ theo chain tin cậy:** với cấu hình nhiều hop, duyệt các hop theo quy tắc hạ tầng (thường từ phải sang trái để tìm hop không tin cậy đầu tiên), không “lấy trái nhất” vô điều kiện.
6. **Xử lý thiếu/sai header:** có chính sách fallback hoặc đánh dấu `unknown`, không silently gán một giá trị sai rồi dùng cho security decision.

**Ví dụ:**

~~~text
Peer ngay truoc Java: 10.0.0.10 (proxy duoc quan ly)
XFF: 203.0.113.9, 10.0.0.5
Trusted chain: 10.0.0.10 va 10.0.0.5
=> Client hop khong tin cay gan nhat: 203.0.113.9
~~~

Nếu chỉ tin `10.0.0.10` mà không tin `10.0.0.5`, không thể tự suy ra địa chỉ `203.0.113.9` là nguồn đã được chứng thực; cần xem `10.0.0.5` là ranh giới không tin cậy trong policy đã xác định. Hệ thống có một hoặc nhiều proxy cần mô hình phù hợp với cấu hình mạng thực, **không hard-code thuật toán chung cho mọi deployment**.

Trong nhiều ứng dụng, cách tốt nhất là **để ingress/container xử lý đúng forwarded headers**, rồi cung cấp một API `clientAddress` nhất quán cùng metadata nguồn, thay vì để từng controller tự parse XFF.

## 6. Ví dụ Java 17 chạy độc lập: bỏ qua header giả và chỉ tin edge có hợp đồng rõ ràng

Chương trình này mô phỏng hai loại request: truy cập trực tiếp và request đến từ một edge proxy nội bộ do hệ thống quản lý. Để tránh dạy cách tin header tùy tiện, demo sử dụng **giả định hạ tầng rất hẹp**:

- Immediate peer `10.0.0.10` là một edge proxy đã được xác định, và **network policy không cho client ngoài truy cập Java với tư cách peer này**.
- Edge proxy **ghi đè** `X-Forwarded-For` thành **một IPv4 duy nhất** đã được nó xác định; nó không giữ nguyên giá trị không đáng tin từ client.
- Nếu peer khác `10.0.0.10`, bỏ qua hoàn toàn XFF.
- Nếu header thiếu, nhiều hop hoặc sai định dạng, demo không đoán client IP: ghi địa chỉ peer cùng nguồn `PROXY_FALLBACK`.
- Đây là ví dụ để hiểu ranh giới tin cậy, **không phải trình phân tích XFF/Forwarded production**, không xử lý IPv6 và CIDR.

Tạo file `ClientAddressDemo.java`:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ClientAddressDemo {

    record Address(String ip, String source) {}

    private static boolean singleIpv4(String value) {
        if (value == null || !value.matches("[0-9.]{7,15}")) {
            return false;
        }
        String[] parts = value.split("[.]", -1);
        if (parts.length != 4) {
            return false;
        }
        for (String part : parts) {
            if (part.isEmpty() || part.length() > 3
                    || (part.length() > 1 && part.startsWith("0"))) {
                return false;
            }
            if (Integer.parseInt(part) > 255) {
                return false;
            }
        }
        return true;
    }

    private static Address resolve(
            InetSocketAddress peer, String xForwardedFor) {
        String peerIp = peer.getAddress().getHostAddress();

        // Demo policy: chi co edge 10.0.0.10 duoc phep
        // overwrite XFF thanh dung 1 IPv4.
        if (!"10.0.0.10".equals(peerIp)) {
            return new Address(peerIp, "SOCKET_PEER");
        }
        if (!singleIpv4(xForwardedFor)) {
            return new Address(peerIp, "PROXY_FALLBACK");
        }
        return new Address(xForwardedFor, "TRUSTED_EDGE_HEADER");
    }

    private static InetSocketAddress socket(byte[] ip) throws Exception {
        return new InetSocketAddress(InetAddress.getByAddress(ip), 52000);
    }

    private static void logCase(
            Logger logger, String name, Address address) {
        logger.info("case=" + name
                + " client=" + address.ip()
                + " source=" + address.source());
    }

    public static void main(String[] args) throws Exception {
        Logger logger = Logger.getLogger("demo.client.address");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);

        try {
            InetSocketAddress direct = socket(
                    new byte[] {(byte) 198, 51, 100, 23});
            InetSocketAddress edge = socket(
                    new byte[] {10, 0, 0, 10});

            logCase(logger, "direct", resolve(direct, null));

            // Client tu dat XFF gia, nhung peer khong tin cay.
            logCase(logger, "spoof-at-direct",
                    resolve(direct, "1.2.3.4"));

            // Edge duoc quan ly da overwrite header theo policy.
            logCase(logger, "trusted-edge",
                    resolve(edge, "203.0.113.9"));

            // Demo chi ho tro header 1 IPv4, khong parse chain.
            logCase(logger, "multi-hop",
                    resolve(edge, "203.0.113.9, 10.0.0.5"));
        } finally {
            logger.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ClientAddressDemo.java
java ClientAddressDemo
~~~

**Stdout:** không có nội dung.

**Stderr chính xác** trong lần chạy thành công:

~~~text
INFO: case=direct client=198.51.100.23 source=SOCKET_PEER
INFO: case=spoof-at-direct client=198.51.100.23 source=SOCKET_PEER
INFO: case=trusted-edge client=203.0.113.9 source=TRUSTED_EDGE_HEADER
INFO: case=multi-hop client=10.0.0.10 source=PROXY_FALLBACK
~~~

`ConsoleHandler` của JUL ghi vào **stderr**. `Formatter` tùy chỉnh bảo đảm format ngắn và ổn định, không thêm timestamp ngẫu nhiên. Địa chỉ và port được tạo trong code nên không phụ thuộc mạng thực hoặc DNS.

### Phân tích từng tình huống

| Tình huống | Immediate peer | Giá trị XFF | Kết luận |
| --- | --- | --- | --- |
| Truy cập trực tiếp | `198.51.100.23` | Không có | Log peer quan sát trực tiếp |
| Header giả từ client | `198.51.100.23` | `1.2.3.4` | **Bỏ qua XFF**, không nhận địa chỉ giả |
| Edge tin cậy, 1 IPv4 | `10.0.0.10` | `203.0.113.9` | Chỉ chấp nhận theo **hợp đồng hạ tầng đã mô tả** |
| Header nhiều hop | `10.0.0.10` | `203.0.113.9, 10.0.0.5` | Không tự parse; fallback về peer, có nhãn nguồn |

**Điểm giới hạn không được bỏ qua:** ví dụ tin `X-Forwarded-For` chỉ vì peer trùng đúng `10.0.0.10` **và** triển khai được giả định đã bảo vệ backend, đồng thời edge đã overwrite header. Code Java này **không thể tự chứng minh** proxy thực sự đã làm điều đó. Nếu edge chỉ append vào header do attacker gửi, hoặc backend có đường truy cập trực tiếp bỏ qua edge, thiết kế phải được sửa ở **cấu hình mạng và proxy** trước. Không sao chép nguyên hàm `resolve` vào sản phẩm nhiều-hop/IPv6.

## 7. Logging request: trường nào nên ghi?

Một schema request log phổ biến:

~~~text
timestamp=...
requestId=...
method=GET
route=/orders/{id}
status=200
durationMs=18
peerIp=10.0.0.10
clientIp=203.0.113.9
clientIpSource=TRUSTED_EDGE
proxyPolicy=edge-v1
~~~

Giải thích:

- `route` là **mẫu route** khi framework hỗ trợ, ví dụ `/orders/{id}`, không mặc định là URL đầy đủ có query chứa dữ liệu người dùng.
- `clientIpSource` giúp người điều tra biết IP đến từ kết nối trực tiếp hay đã được suy ra theo policy proxy.
- `peerIp` có thể giúp nhận ra lỗi ingress/proxy hoặc request đi sai đường.
- `requestId` thường quan trọng hơn địa chỉ IP để nối các bước xử lý trên nhiều service.
- `durationMs`, status và error category nên tách trường; không cần dump HTTP body.

**Không log nguyên chuỗi header `X-Forwarded-For` từ request không tin cậy** chỉ để debug: nó có thể rất dài, chứa ký tự điều khiển, chuỗi giả mạo hoặc nhiều địa chỉ cá nhân. Nếu cần điều tra sự cố parser/proxy, hãy ghi trạng thái như `FORWARDED_MISSING`, `FORWARDED_INVALID`, `UNTRUSTED_PEER` hoặc một chỉ số số hop đã kiểm tra, không cần in toàn bộ chuỗi raw.

### IP là metadata kỹ thuật nhưng vẫn có thể là dữ liệu cá nhân

Trong nhiều bối cảnh, IP có thể liên kết với thiết bị hoặc người dùng khi kết hợp log thời gian, account và dữ liệu nhà mạng. Do đó:

- Chỉ thu thập IP nếu có **mục đích hợp lệ và rõ ràng**.
- Xác định retention, quyền truy cập và đối tượng được phép tra cứu.
- Cân nhắc **mask/truncate hoặc aggregate** nếu nhu cầu thống kê không đòi IP đầy đủ.
- Không đưa IP/user agent vào tên metric label có cardinality cực lớn.
- Không giả định hash IP là vô danh: IPv4 có thể đoán và đối chiếu, hash cố định cho phép liên kết hoạt động.
- Không tự động đưa nhiều IP qua hệ thống thứ ba nếu không có đánh giá bảo mật/quyền riêng tư.

Một số mục đích như phản ứng sự cố bảo mật cần IP đầy đủ trong thời gian phù hợp; mục đích khác chỉ cần mạng/nhóm địa chỉ hoặc tỷ lệ tổng hợp. Cần tách loại log và chính sách, thay vì “lưu tất cả vĩnh viễn”.

## 8. Các vấn đề thực tế: IPv4, IPv6, NAT, port và địa chỉ bất thường

**IPv4 và IPv6:** nhiều ứng dụng phải hỗ trợ cả hai. Ví dụ `192.0.2.10` là IPv4, `2001:db8::1` là IPv6. Đừng ép IPv6 thành chuỗi 4 octet; cũng đừng dựa vào một độ dài cố định như “IP luôn tối đa 15 ký tự”. Khi cần lưu hay so sánh địa chỉ, ưu tiên cấu trúc IP được kiểm tra qua thư viện phù hợp, không parse bằng split chuỗi tùy tiện.

**NAT/CGNAT/VPN:** IP công cộng không tương đương một người dùng. Cùng một IP có thể có hàng nghìn request hợp lệ từ các tài khoản khác nhau. Không dùng IP làm khóa duy nhất cho identity, audit actor hay các quyết định ủy quyền.

**Source port:** port có thể giúp phân biệt kết nối trong một số log mạng nhưng biến động theo kết nối, NAT và thời điểm; không phải thông tin ổn định về user. Nếu ghi IP:port, dùng biểu diễn không mơ hồ với IPv6 (ví dụ IPv6 cần ngoặc vuông khi ghép port).

**IPv4-mapped IPv6 và chuẩn hóa:** hai chuỗi IP có thể biểu diễn cùng đích theo quy ước khác nhau. Khi cần so sánh một tập IP/CIDR, dùng thuật toán và thư viện mạng phù hợp, tránh so sánh chữ viết rồi suy ra luôn tương đương.

**Địa chỉ thiếu/không parse được:** không điền ngẫu nhiên IP như `0.0.0.0` để ngụy tạo địa chỉ nguồn đã biết. Ghi trạng thái `unknown` hoặc `invalid-forwarded-header` cùng `peerIp` nếu chính sách cho phép, để người đọc phân biệt dữ liệu thiếu với địa chỉ thật.

**Ký tự điều khiển và log injection:** một header attacker kiểm soát có thể chứa newline, dấu phân cách hoặc chuỗi gây hiểu lầm khi parse log. Chỉ ghi trường đã parse và validate; nếu buộc lưu raw cho mục đích điều tra có kiểm soát, cần encoder/escaping và giới hạn kích thước/retention.

## 9. Framework, reverse proxy và cấu hình hạ tầng

Khi triển khai cùng Spring Boot, Tomcat, Jetty, Netty, nginx, Apache HTTP Server, Envoy, CDN hoặc load balancer, phải xác định **thành phần nào chịu trách nhiệm xác nhận trusted proxies**. Có thể có cơ chế chuẩn hóa forwarded headers ở container/framework, nhưng hành vi còn phụ thuộc phiên bản, cấu hình và đường vào.

Một quy trình cấu hình an toàn:

1. Vẽ sơ đồ những hop thực sự nằm trước JVM ở môi trường production.
2. Xác định IP/CIDR hoặc identity của hop tin cậy; tránh cấu hình “tin mọi proxy”.
3. Tại proxy biên, loại header được client tự khai nếu policy yêu cầu và tạo lại header chuẩn.
4. Bảo đảm Java backend không có đường kết nối ngoài mong muốn bỏ qua proxy.
5. Dùng cấu hình container/framework xử lý forwarded metadata **một lần**, tránh tự viết parser lặp trong từng filter/controller.
6. Kiểm tra khi truy cập trực tiếp, qua một proxy, qua nhiều proxy và khi header bị giả.
7. Ghi source/policy/version, quan sát log thay đổi ra sao khi có thay đổi ingress.
8. Đảm bảo hành vi nhất quán giữa dev, staging, production và trong container.

**Đặc biệt:** các header dùng để xác định client IP cho logging không nên được tin riêng rồi đem dùng làm **chính sách bảo mật** như allowlist truy cập hay rate limiting trước khi xác minh trust chain. Địa chỉ IP chỉ là tín hiệu bổ trợ; yêu cầu xác thực/ủy quyền nên dựa vào danh tính và cơ chế phù hợp.

Nếu ứng dụng dùng container hoặc service mesh, log của ingress có thể đã ghi source IP theo chính sách mạng. Khi đó backend Java có thể chỉ cần log `requestId`/trace ID, rồi liên kết với access log tại edge, thay vì nhân bản IP ở mọi service. Đây là quyết định về mục đích, dữ liệu và quyền truy cập.

## 10. Kiểm thử bằng các trường hợp có chủ đích

| Test case | Điều cần xảy ra |
| --- | --- |
| Request trực tiếp, không có forwarded header | Lấy socket peer |
| Request trực tiếp nhưng tự gửi XFF giả | Vẫn lấy socket peer, không tin header |
| Request qua edge tin cậy đã overwrite header | Chọn địa chỉ do policy edge xác nhận |
| Edge thiếu header | Log trạng thái thiếu/fallback, không giả định IP gốc |
| Header nhiều hop | Chạy chính sách chuỗi proxy thực, không lấy trái nhất mù quáng |
| Header IPv6 hoặc RFC `Forwarded` | Parser/framework hỗ trợ ngữ pháp đúng hoặc từ chối có kiểm soát |
| Header cực dài/chứa newline | Giới hạn kích thước, không log raw không kiểm soát |
| Backend có đường vào không qua proxy | Không được tin header chỉ vì nó tồn tại |
| Proxy bị thay đổi IP/CIDR | Cập nhật trust policy; có cảnh báo khi mismatch |
| XFF chứa IP private/public xen kẽ | Chọn theo *trusted hop*, không dùng heuristic “IP public đầu tiên” |
| Đổi từ IPv4 sang IPv6 | Không mất log hoặc hỏng schema vì giới hạn độ dài |
| Client nằm sau NAT/VPN | Không gán IP thành danh tính duy nhất của user |

Trong một bài kiểm thử tích hợp, hãy log **peer IP**, **resolved client IP** và **source/policy** tại hạ tầng test có kiểm soát. Kiểm tra cả response status, request ID và nơi log được ghi. Đừng dùng log đã qua collector làm bằng chứng duy nhất rằng header gốc được parse đúng, vì collector cũng có thể đổi hoặc chuẩn hóa field.

## 11. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Hướng khắc phục |
| --- | --- | --- |
| Dùng `getRemoteAddr()` và tuyên bố luôn là IP trình duyệt | Có thể chỉ là reverse proxy | Phân biệt peer và logical client |
| Tin `X-Forwarded-For` ở mọi request | Client tự gửi header để giả IP | Trust immediate peer và đường proxy |
| Lấy IP bên trái nhất trong XFF bất kỳ | Chuỗi có thể bắt đầu bằng giá trị attacker tạo | Chọn theo trusted-hop policy |
| Dùng `Host` làm client address | `Host` là đích HTTP | Đọc socket peer và metadata proxy tin cậy |
| Parse `Forwarded` bằng `split(":")` | IPv6, quotes, ports, nhiều element làm sai | Dùng parser hỗ trợ ngữ pháp |
| Xem IP là user ID | NAT, VPN, nhiều user dùng chung IP | Correlation ID và auth identity riêng |
| Log raw XFF vô giới hạn | Rủi ro spoofing, injection, PII, dung lượng | Validate, normalize, giới hạn size |
| Cùng lúc container và app tự rewrite remote address | Có thể xử lý lại header không đúng | Chỉ rõ một lớp chịu trách nhiệm |
| Giữ IP mãi mãi | Tăng rủi ro riêng tư và chi phí | Retention theo mục đích và quyền truy cập |
| Dùng hash IP rồi coi là dữ liệu vô danh | Vẫn có thể liên kết hoặc đoán giá trị | Đánh giá khả năng tái nhận diện |

## 12. Checklist áp dụng

- [ ] Phân biệt rõ `peerIp`, `clientIp`, `clientIpSource` và request ID.
- [ ] Xác định app chạy trực tiếp hay sau CDN/load balancer/reverse proxy/mesh.
- [ ] Thiết lập, kiểm thử và ghi nhận danh sách trusted proxies.
- [ ] Edge kiểm soát incoming `X-Forwarded-For`/`Forwarded` theo chính sách.
- [ ] Không tin header khi immediate peer không thuộc trust boundary.
- [ ] Hỗ trợ IPv4/IPv6 đúng cách hoặc từ chối định dạng chưa hỗ trợ có kiểm soát.
- [ ] Không dùng raw XFF làm danh tính hay quy tắc bảo mật.
- [ ] Dùng schema log có nguồn dữ liệu và mức độ tin cậy rõ ràng.
- [ ] Hạn chế ghi PII/IP theo mục đích; đặt retention, phân quyền và masking phù hợp.
- [ ] Kiểm thử spoofed headers, nhiều hop, NAT/VPN, newline và thay đổi hạ tầng.
- [ ] Liên kết log các service qua request ID/trace ID thay vì chỉ dựa vào IP.

### Tự kiểm tra

**Câu 1.** Java server nhận kết nối từ proxy `10.0.0.10`. `getRemoteAddress()` thường thấy IP nào?  
**Đáp:** Địa chỉ immediate peer `10.0.0.10`, không mặc định là IP trình duyệt.

**Câu 2.** Một request trực tiếp có `X-Forwarded-For: 1.2.3.4`. Có thể tin client IP là `1.2.3.4` không?  
**Đáp:** Không. Header có thể do chính client đặt; cần chuỗi proxy tin cậy.

**Câu 3.** Có được dùng IP public đầu tiên bên trái trong mọi chuỗi XFF?  
**Đáp:** Không. Phải xác định trusted hops và chính sách header của hạ tầng.

**Câu 4.** Dùng IP để xác định người dùng đã đăng nhập có đúng không?  
**Đáp:** Không. IP có thể chia sẻ qua NAT/VPN và không thay cho thông tin xác thực.

**Câu 5.** Địa chỉ IP trong log có luôn là dữ liệu vô hại không?  
**Đáp:** Không. Nó có thể liên kết với cá nhân hoặc thiết bị; cần hạn chế thu thập, phân quyền và retention thích hợp.

**Ghi nhớ:** Client address trong logging web là thông tin về **nguồn mạng của request**, nhưng địa chỉ peer, client IP do proxy chuyển và danh tính người dùng là ba khái niệm khác nhau. Đừng tin forwarded headers nếu chưa có trusted proxy policy và hạ tầng bảo vệ phù hợp. Hãy log nguồn xác định địa chỉ, kiểm thử spoofing/IPv6/multi-hop và quản lý IP như dữ liệu có thể nhạy cảm.