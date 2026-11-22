# Kết nối đến tên máy nhiều địa chỉ và phân biệt lỗi DNS với lỗi kết nối

## 1. Vấn đề: tên máy không đồng nghĩa với một địa chỉ IP

Trong Java, lập trình viên thường bắt đầu bằng tên và cổng như `api.example.org:443`. Để thiết lập kết nối TCP, hệ điều hành cần biết **địa chỉ IP đích** và **cổng TCP**. Nhưng một hostname có thể được phân giải thành **nhiều địa chỉ** IPv4 và/hoặc IPv6. Một số địa chỉ có thể kết nối được, số khác bị chặn, không có listener hoặc đi qua tuyến mạng không hoạt động.

Có hai giai đoạn logic khác nhau:

1. **Name resolution:** biến tên máy thành các địa chỉ IP ứng viên; thường thông qua cơ chế name service của máy, có thể sử dụng DNS, file hosts hoặc cache.
2. **TCP connection:** với từng IP và cổng, thử thiết lập kết nối TCP đến một endpoint cụ thể.

Điểm phân biệt quan trọng: **phân giải tên thành công chưa chứng minh cổng TCP mở**, và **một IP kết nối thất bại chưa chứng minh tất cả IP của tên đó đều thất bại**. Lỗi ở bước 1 không phải cùng loại với lỗi ở bước 2.

Mục tiêu bài học:

- Giải thích vì sao hostname có thể cho nhiều IPv4/IPv6 và thứ tự địa chỉ có thể thay đổi.
- Biết khi nào dùng `InetAddress.getAllByName` thay vì chỉ dùng `getByName`.
- Phân biệt `UnknownHostException` ở bước resolve với `ConnectException`, `SocketTimeoutException` và các lỗi khác khi `Socket.connect`.
- Tự viết và chạy một ví dụ Java 17 thử nhiều địa chỉ, đóng socket lỗi, giữ nguyên nhân và dừng ở địa chỉ kết nối thành công.
- Nhận biết giới hạn của cách thử tuần tự, thời gian chờ, bảo mật TLS và retry sau khi đã gửi dữ liệu.

## 2. Tên máy có nhiều địa chỉ: A, AAAA và resolver

DNS có **A record** cho địa chỉ IPv4 và **AAAA record** cho địa chỉ IPv6. Một hostname có thể nhận nhiều bản ghi cùng loại hoặc cả hai loại. Ví dụ minh họa:

| Hostname | Địa chỉ ứng viên | Family |
|---|---|---|
| `api.example.org` | `192.0.2.10` | IPv4 |
| `api.example.org` | `192.0.2.11` | IPv4 |
| `api.example.org` | `2001:db8::10` | IPv6 |

Các IP trên thuộc dải dành cho tài liệu (TEST-NET và IPv6 documentation prefix); không được dùng như địa chỉ một dịch vụ đang chạy.

Những lý do có nhiều địa chỉ gồm: nhiều máy backend, triển khai đa vùng, cân bằng tải dựa trên DNS, dự phòng và đồng thời hỗ trợ IPv4/IPv6. Tuy nhiên, kết quả nhận được phụ thuộc resolver và môi trường mạng; chương trình **không nên giả định** DNS luôn trả ba IP trên, tất cả IP từ zone file đều xuất hiện, hoặc IPv4/IPv6 luôn theo một thứ tự cố định.

Trong thực tế, “phân giải tên” rộng hơn “gửi DNS query”: Java có thể nhận kết quả từ file hosts, cache JVM, cache hệ điều hành hoặc name service được cấu hình. Các lần gọi liên tiếp đôi khi không thấy thay đổi DNS ngay do caching/TTL. Mặt khác, một IP literal như `127.0.0.1` hay `::1` không cần DNS để được biểu diễn thành `InetAddress`.

**Hostname không chứa thông tin rằng port 443 có listener.** DNS A/AAAA phân giải địa chỉ; trạng thái cổng và khả năng kết nối chỉ được kiểm tra ở bước TCP (hoặc qua phép kiểm tra chuyên biệt khác).

### Lưu đồ tổng quát

```text
hostname + port
      |
      v
Name resolution: hosts/cache/DNS
      |
      +-- thất bại --> lỗi phân giải tên (chưa thử TCP)
      |
      +-- thành công --> [IPv6 A, IPv4 B, IPv4 C, ...]
                              |
                              v
                       thử IP A : port
                              |
                   thất bại?  +-- không --> TCP connected
                      |
                      v
                       thử IP B : port
                              |
                   thất bại?  +-- không --> TCP connected
                      |
                      v
                       thử IP C : port
                              |
                tất cả thất bại --> lỗi kết nối tổng hợp
```

Sơ đồ mô tả **fallback tuần tự** cho mục đích học; client production có thể sắp xếp và thực hiện các nỗ lực chồng lấp để giảm độ trễ.

## 3. Các API Java cần phân biệt

### 3.1. `InetAddress.getAllByName`: lấy các ứng viên

```java
// Đoạn minh họa nằm trong phương thức có thể throws UnknownHostException.
InetAddress[] addresses = InetAddress.getAllByName("api.example.org");
for (InetAddress address : addresses) {
    System.out.println(address.getHostAddress());
}
```

`getAllByName` trả về mảng các `InetAddress` ứng viên của hostname theo name service đang dùng; nếu không thể phân giải thành địa chỉ dùng được thì ném `UnknownHostException`. Nó không tự kiểm tra port, thực hiện bắt tay TCP hay gửi dữ liệu HTTP. `InetAddress.getByName(host)` chỉ trả **một** địa chỉ và vì vậy không phù hợp nếu mục tiêu là tự kiểm soát quá trình thử **toàn bộ các ứng viên**.

Mỗi phần tử có thể là `Inet4Address` hoặc `Inet6Address`. `getHostAddress()` cho biết địa chỉ dạng số. Danh sách/thứ tự phụ thuộc hệ điều hành và chính sách địa chỉ của môi trường, không phải hợp đồng “ưu tiên IPv6 trước” hoặc “IP đầu luôn nhanh nhất”.

### 3.2. `Socket.connect`: thử IP:port đã biết

```java
// address là InetAddress đã được resolve; port và timeoutMillis hợp lệ.
try (Socket socket = new Socket()) {
    socket.connect(
            new InetSocketAddress(address, port), timeoutMillis);
    // Kết nối TCP chỉ được xem là thành lập nếu connect trả về thành công.
}
```

Các chi tiết dễ nhầm:

- `new Socket()` tạo một socket chưa kết nối. Mỗi nỗ lực nên dùng socket mới; sau khi connect lỗi, đóng socket cũ.
- `new InetSocketAddress(address, port)` nhận **InetAddress đã phân giải**, nên có thể xác định exception xảy ra trong chính giai đoạn TCP connect.
- `connect(endpoint, timeoutMillis)` đặt **timeout cho nỗ lực kết nối đó**. Nó không đặt timeout DNS và cũng không bảo đảm tổng thời gian thử 5 IP nhỏ hơn cùng một timeout.
- `socket.setSoTimeout(ms)` kiểm soát thời gian chờ **blocking read** trên socket; không đặt timeout cho DNS hoặc connect.
- `Socket` cơ bản là TCP. Để giao tiếp HTTPS cần thêm TLS với xác thực chứng chỉ và hostname; đừng coi “TCP connect OK” là “HTTPS OK”.

Khi dùng constructor nhận hostname trực tiếp, resolution có thể bị giấu bên trong quá trình tạo/kết nối. Nếu cần phân biệt lỗi DNS với lỗi TCP trong log và chẩn đoán, chủ động tách hai bước.

## 4. Phân loại lỗi theo đúng giai đoạn

| Lúc xảy ra | Dấu hiệu Java thường thấy | Cách đọc đúng |
|---|---|---|
| Resolve hostname bằng `getAllByName` | `UnknownHostException` | Không nhận được địa chỉ dùng được từ cơ chế phân giải tên, hoặc quá trình resolve gặp vấn đề |
| `connect` đến IP và cổng | `ConnectException`, thường có “Connection refused” | Đích không chấp nhận kết nối, có thể không có listener hoặc có thiết bị từ chối chủ động |
| `connect(endpoint, timeout)` | `SocketTimeoutException` | Không thiết lập được TCP trong thời hạn đã đặt |
| Tìm tuyến đến IP | `NoRouteToHostException`, `SocketException` như “Network is unreachable” | Đường đi/khả năng tiếp cận mạng có vấn đề |
| Đọc từ socket đã connect | `SocketTimeoutException` khi dùng `setSoTimeout` | Chờ dữ liệu ứng dụng quá lâu; đây là read timeout, không phải DNS timeout |
| Bắt tay HTTPS/TLS | `SSLHandshakeException` hoặc lỗi chứng chỉ | TCP có thể đã thành công, nhưng handshake/xác thực TLS không thành công |
| Sau giao thức ứng dụng | HTTP status `401`, `404`, `503` | Đã nhận phản hồi HTTP; đó là trạng thái ở tầng ứng dụng |

**Không suy luận quá mức từ exception.** `UnknownHostException` không tự cho biết DNS trả NXDOMAIN, resolver tạm mất liên lạc, file hosts sai hay một tên không được cấu hình. `ConnectException` không chứng minh máy chủ hoàn toàn tắt; có thể cổng không lắng nghe hoặc firewall trả lời từ chối. `SocketTimeoutException` từ connect không chứng minh server chết; gói có thể bị drop hoặc đường mạng chậm.

**Một hostname có thể vừa resolve thành công vừa kết nối thất bại.** Ví dụ `api.example.org` trả về ba IP; `192.0.2.10:443` từ chối, `2001:db8::10:443` timeout nhưng `192.0.2.11:443` thành công. Tại đây DNS đã cung cấp danh sách; vấn đề nằm ở từng đường TCP, và client có thể tiếp tục với địa chỉ hoạt động.

### Ba ví dụ chẩn đoán nhanh

1. `getAllByName("unknown.invalid")` ném `UnknownHostException`: đây là **lỗi resolve** trong lời gọi này; chưa có nỗ lực TCP tới IP được phân giải. `.invalid` là hậu tố dành cho tên không hợp lệ trong DNS công cộng, nhưng test có thể bị tác động bởi chính sách resolver môi trường.
2. Hostname ra `127.0.0.1`, port không có dịch vụ lắng nghe: DNS/resolve thành công, `connect` thường ném `ConnectException`.
3. `connect` cổng 443 thành công, sau đó HTTPS báo certificate mismatch: lỗi ở **TLS và hostname verification**, không phải DNS/TCP connect.

## 5. Chính sách thử nhiều địa chỉ

Một triển khai TCP đơn giản có thể làm theo các bước sau:

1. Nhận hostname và port; xác định timeout cho mỗi nỗ lực cùng giới hạn tổng thời gian phù hợp.
2. Gọi `InetAddress.getAllByName(host)` để lấy các địa chỉ. Nếu thất bại ở đây, báo lỗi phân giải tên riêng.
3. Với mỗi `InetAddress`, tạo **một `Socket` mới** rồi gọi `connect(new InetSocketAddress(address, port), timeoutMillis)`.
4. Nếu connect thất bại, **đóng socket đó**, ghi nhận IP và exception rồi thử ứng viên kế.
5. Nếu connect thành công, **dừng vòng lặp**, chuyển socket đang mở cho mã ứng dụng và trách nhiệm đóng socket.
6. Nếu tất cả connect thất bại, tạo một lỗi kết nối tổng hợp và giữ lại các lỗi thành phần để chẩn đoán. Không gọi đây là “DNS failed”.

Một điều kiện thiết kế rất quan trọng: **chỉ fallback giữa các IP ở giai đoạn chưa kết nối thành công**. Khi đã gửi thông điệp ứng dụng, timeout lúc đọc phản hồi **không bảo đảm server chưa xử lý yêu cầu**. Thử gửi lại một lệnh tạo đơn hàng hoặc chuyển tiền có thể thực thi trùng nếu thiếu idempotency.

Ví dụ này dùng fallback tuần tự, dễ hiểu và dễ kiểm chứng; với mạng dual-stack bị lỗi một family, cách tuần tự có thể chậm vì phải đợi timeout rồi mới thử family khác. Phần tối ưu sẽ được trình bày sau ví dụ.

## 6. Ví dụ Java 17+: một IP lỗi, IP còn lại hoạt động

Chương trình sau hoàn toàn **offline**, dùng địa chỉ loopback và một cổng tạm do hệ điều hành chọn. Để có kết quả ổn định trên máy có file hosts/DNS khác nhau, ví dụ chuẩn bị hai `InetAddress` theo thứ tự: IPv6 `::1` rồi IPv4 `127.0.0.1`. Server cố ý **bind riêng `127.0.0.1`**. Vì vậy TCP connect đến `::1` không đến được listener đó, còn connect IPv4 sẽ thành công.

Đây là **danh sách ứng viên mô phỏng** để kiểm tra thuật toán fallback; nó không khẳng định DNS thật của `localhost` lúc nào cũng trả đủ cả hai IP hay trả IPv6 trước. Trong cùng chương trình có `connectHost`, minh họa cách thay danh sách mô phỏng bằng kết quả **`getAllByName(host)` của tên máy thật**.

Lưu file **`MultiAddressConnectDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MultiAddressConnectDemo {

    // Mẫu dùng hostname thật: resolve trước, rồi thử các IP.
    static Socket connectHost(String host, int port, int timeoutMillis)
            throws IOException {
        InetAddress[] candidates = InetAddress.getAllByName(host);
        return connectCandidates(candidates, port, timeoutMillis);
    }

    // Chỉ retry khi TCP connect chưa thành công.
    static Socket connectCandidates(
            InetAddress[] addresses, int port, int timeoutMillis)
            throws IOException {

        IOException summary =
                new IOException("All TCP connection attempts failed");

        for (InetAddress address : addresses) {
            Socket candidate = new Socket();
            try {
                candidate.connect(
                        new InetSocketAddress(address, port), timeoutMillis);
                return candidate; // caller chịu trách nhiệm đóng socket
            } catch (IOException failure) {
                summary.addSuppressed(failure);
                try {
                    candidate.close();
                } catch (IOException closeFailure) {
                    summary.addSuppressed(closeFailure);
                }

                String family = address instanceof Inet6Address
                        ? "IPv6" : "IPv4";
                System.out.println(family + " connect failed");
            }
        }

        throw summary;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();

        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {

            Future<String> received = workers.submit(() -> {
                try (Socket peer = server.accept()) {
                    peer.setSoTimeout(2_000);

                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(
                                    peer.getInputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedWriter out = new BufferedWriter(
                            new OutputStreamWriter(
                                    peer.getOutputStream(),
                                    StandardCharsets.UTF_8));

                    String request = in.readLine();
                    out.write("PONG\n");
                    out.flush();
                    return request;
                }
            });

            InetAddress[] demoAddresses = {
                    InetAddress.getByName("::1"),
                    InetAddress.getByName("127.0.0.1")
            };

            try (Socket client = connectCandidates(
                    demoAddresses, server.getLocalPort(), 1_000)) {
                client.setSoTimeout(2_000);

                BufferedReader in = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.UTF_8));
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(
                                client.getOutputStream(),
                                StandardCharsets.UTF_8));

                String family = client.getInetAddress()
                        instanceof Inet6Address ? "IPv6" : "IPv4";
                System.out.println("Connected via " + family);

                out.write("PING\n");
                out.flush();
                System.out.println("Client received: " + in.readLine());
            }

            System.out.println("Server received: "
                    + received.get(3, TimeUnit.SECONDS));
        } finally {
            workers.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn, trong thư mục chứa file:

```bash
javac -encoding UTF-8 MultiAddressConnectDemo.java
java MultiAddressConnectDemo
```

Kết quả trên hệ thống có TCP loopback bình thường:

```text
IPv6 connect failed
Connected via IPv4
Client received: PONG
Server received: PING
```

**Giải thích luồng chạy:**

1. `ServerSocket(0, 1, 127.0.0.1)` bind vào IPv4 loopback; tham số port `0` yêu cầu hệ điều hành tự chọn cổng. `getLocalPort()` trả về cổng đó.
2. Một task server chờ `accept()`, đọc một dòng và gửi `PONG\n` khi nhận kết nối.
3. `connectCandidates` thử `::1:port` bằng một socket mới; IP này không khớp địa chỉ listener IPv4, vì vậy connect thất bại. Chương trình bắt `IOException`, lưu vào danh sách suppressed của lỗi tổng hợp rồi đóng socket.
4. Vòng lặp tạo socket khác và thử `127.0.0.1:port`; connect thành công. Hàm trả socket đang mở và **không thử thêm địa chỉ**.
5. Client gửi `PING\n`, nhận `PONG`; `Future.get` xác nhận server đã nhận đúng `PING`. `try-with-resources` đóng socket; executor được shutdown trong `finally`.
6. Nếu sử dụng `connectHost("service.example.org", port, timeout)` ở mã nghiệp vụ, tên máy được resolve trước. Lỗi `UnknownHostException` từ `getAllByName` xuất hiện **trước vòng thử TCP**. Nếu resolve được nhưng tất cả IP thất bại, phương thức ném `IOException` tổng hợp và có thể xem các nguyên nhân bằng `getSuppressed()`.

**Giới hạn của ví dụ:** chỉ phục vụ một kết nối, không dùng TLS, không có connection pool, deadline tổng, kiểm soát số lượng ứng viên hay luồng retry concurrent. Chạy với cổng loopback có thể bị cấm bởi chính sách máy. Không biến demo này thành dịch vụ Internet trực tiếp; khi xây HTTP client, thường nên dùng `java.net.http.HttpClient` hoặc thư viện có chính sách timeout, DNS, proxy, TLS và pool thích hợp.

## 7. Giới hạn của thử tuần tự và Happy Eyeballs

Nếu một hostname có IPv6 và IPv4 nhưng đường IPv6 không hoạt động, một client thử IPv6 tuần tự với timeout 3 giây có thể trì hoãn việc dùng IPv4 dù IPv4 hoàn toàn khỏe. Điều này ảnh hưởng trải nghiệm khi gặp mạng dual-stack cấu hình không đầy đủ.

**Happy Eyeballs** (RFC 8305) là hướng tiếp cận kết nối IPv6/IPv4 với sắp xếp ứng viên và những nỗ lực có thể **chồng lấp có kiểm soát** để tránh chờ quá lâu ở một địa chỉ/family không hoạt động. Đây là thuật toán phức tạp hơn vòng `for`; cần quản lý các socket thua cuộc, cancellation, concurrency và chính sách lựa chọn đích.

Đối với production, cần xem xét:

- **Per-address timeout** và **overall deadline** là hai giới hạn khác nhau. Nếu có 8 IP và mỗi IP chờ 2 giây tuần tự, thời gian trước khi báo thất bại có thể lớn hơn 16 giây, chưa tính resolve.
- **Name-resolution timeout/caching** có chính sách riêng; tham số connect timeout của `Socket` không giới hạn thời gian lấy địa chỉ.
- **Connect success** chỉ xác nhận TCP; TLS handshake, request timeout và đọc response cũng có giới hạn thời gian riêng.
- **Cancellation:** khi một ứng viên đã thắng, không để các kết nối song song khác tồn tại vô ích.
- **Không giả định** vòng lặp `Socket` do bạn viết tự có Happy Eyeballs. API thư viện HTTP, proxy hoặc runtime có thể có chính sách khác; cần kiểm tra thực tế.
- **Connection reuse:** dùng kết nối sẵn có có thể tránh cả DNS lookup và TCP/TLS handshake cho mỗi request; thông tin pool phải được quản lý đúng vòng đời.

Trong Java, `Socket.setSoTimeout` dành cho chờ đọc; nó **không** là deadline chung của DNS, TCP, TLS và toàn bộ request. Đừng dùng một loại timeout để mô tả mọi giai đoạn.

## 8. TLS/HTTPS, DNS thay đổi và bảo mật

**Giữ hostname để xác thực TLS:** nếu ứng dụng cần HTTPS cho `api.example.org`, việc bạn chọn một IP từ `getAllByName` chỉ xác định địa chỉ TCP. Chứng chỉ và kiểm tra hostname vẫn phải gắn với **`api.example.org`**, không được tùy ý bỏ xác thực hoặc chỉ tin vào IP. Với TLS tự dựng trên `Socket` cần cấu hình đúng peer host, SNI và hostname verification; tốt hơn là dùng HTTP/TLS client phù hợp.

**Đừng đánh đồng IP đã resolve với đích vĩnh viễn:** DNS record có thể thay đổi vì failover hoặc load balancing. JVM và các tầng hệ thống có thể cache kết quả, nên không giả định hai lần resolve luôn trả giống nhau hay luôn gửi truy vấn DNS mới.

**Khi hostname do người dùng cung cấp**, cần ngăn truy cập địa chỉ nội bộ hoặc endpoint không được phép (SSRF). Validate mỗi đích mạng, chú ý DNS rebinding và redirect, và thực thi kiểm soát trên **đích thực tế được kết nối**. Chỉ kiểm tra tiền tố chuỗi hostname hoặc validate một IP ban đầu rồi bỏ qua IP khác không đủ.

**Retry có side effect:** nếu connect TCP chưa thành công thì ứng dụng chưa gửi request trên socket đó. Nhưng nếu request đã gửi và client timeout khi chờ response, server có thể đã xử lý. Ví dụ retry lệnh chuyển tiền hoặc `POST /orders` cần hợp đồng idempotency để tránh xử lý trùng.

## 9. Quy trình chẩn đoán theo lớp

Khi Java báo “không kết nối được tới tên máy”:

1. **Xác minh input:** hostname, port, scheme, dấu cách, typo; một chuỗi `https://...` không phải hostname trực tiếp truyền nguyên vào `getAllByName`.
2. **Kiểm tra phân giải tên:** gọi `getAllByName`; ghi nhận số IP, IPv4/IPv6 và exception. Đừng cho rằng `nslookup`/`dig` luôn dùng cùng cache hoặc cùng cơ chế của JVM.
3. **Kiểm tra từng TCP endpoint:** với mỗi IP và cổng, thử `connect` với timeout và ghi loại exception; một IP lỗi không có nghĩa IP khác lỗi.
4. **Kiểm tra listener và route:** server có bind đúng giao diện/cổng không? Binding vào `127.0.0.1` không làm server nghe trên địa chỉ IP public; binding IPv4 cũng không tự đảm bảo listener IPv6 `::1`.
5. **Sau khi TCP thành công:** kiểm tra TLS/SNI/chứng chỉ, quyền truy cập, giao thức ứng dụng, HTTP status và read timeout.
6. **Kiểm tra biến thiên theo thời gian:** ghi thời điểm, client network/VPN, DNS cache, các IP đã dùng, latency và IPv4/IPv6; phân tích riêng sự cố intermittent.

Gợi ý phân loại log do ứng dụng tự đặt:

```text
getAllByName failed       -> NAME_RESOLUTION_ERROR
connect IPv6 timed out    -> TCP_CONNECT_TIMEOUT
connect IPv4 refused      -> TCP_CONNECT_REFUSED
another IP connected      -> TCP_CONNECTED
TLS certificate rejected  -> TLS_VERIFICATION_ERROR
HTTP 503 received         -> HTTP_RESPONSE_ERROR
```

Các nhãn ở trên chỉ là ví dụ logging, **không** phải enum hoặc mã lỗi chuẩn của JDK.

Không dùng `ping` để kết luận một port TCP đang hoạt động: ping thường dựa trên ICMP, có thể bị lọc và không kiểm tra listener TCP. Tương tự, một câu trả lời DNS thành công không đo khả năng kết nối tới cổng dịch vụ.

## 10. Các lỗi phổ biến khi viết Java socket

| Cách làm sai | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng `getByName` rồi mặc định hostname chỉ có một IP | Bỏ qua những ứng viên còn hoạt động | Cân nhắc `getAllByName` và chiến lược thử ứng viên |
| Gọi mọi lỗi là “DNS failed” | Chẩn đoán sai và khó sửa đúng lớp | Tách resolve, connect, TLS, request và read |
| Gộp DNS + connect trong một API rồi chỉ log exception cuối | Khó xác định giai đoạn và IP có lỗi | Phân giải trước, connect từng `InetAddress` và giữ nguyên nhân |
| Đặt `setSoTimeout` rồi nghĩ `connect` có timeout | Có thể chờ kết nối quá lâu | Truyền timeout cho `Socket.connect(endpoint, ms)` |
| Tái sử dụng một socket sau connect failure | Socket có trạng thái không còn phù hợp | Mỗi lần thử địa chỉ tạo socket mới; luôn đóng socket lỗi |
| Thử các IP tuần tự mà không có overall deadline | Nhiều IP lỗi có thể kéo dài thời gian chờ | Giới hạn tổng thời gian và chọn thuật toán phù hợp |
| Coi TCP connected là HTTPS thành công | Bỏ sót handshake/certificate/application errors | Giữ hostname gốc, kiểm tra TLS và phản hồi ứng dụng |
| Retry request đã gửi sau timeout mà không có idempotency | Có thể thực thi thao tác trùng | Phân biệt fallback connect với retry nghiệp vụ |
| Chỉ giữ exception cuối, không ghi IP thử | Mất tín hiệu về IPv4/IPv6 và thứ tự fallback | Log theo giai đoạn và bảo tồn các nguyên nhân |
| Giả định cache DNS luôn mới hoặc một IP không đổi | Lỗi sau failover/đổi đích | Thiết kế cache/connection pool và làm mới phù hợp |

## 11. Câu hỏi tự kiểm tra

**1.** `getAllByName("service.example.org")` trả ba IP; connect IP đầu bị từ chối. DNS thất bại chưa?

**Đáp:** Chưa. Name resolution đã thành công; đây là lỗi TCP tới IP/port đầu. Chính sách có thể tiếp tục thử IP khác.

**2.** Tại sao `UnknownHostException` của `getAllByName` khác `SocketTimeoutException` của `connect`?

**Đáp:** Exception đầu xảy ra trước khi có IP ứng viên dùng được trong bước resolve; exception sau là nỗ lực TCP tới IP:port chưa hoàn thành đúng hạn.

**3.** `setSoTimeout(2_000)` có đảm bảo kết nối hoàn tất trong 2 giây không?

**Đáp:** Không. Nó áp dụng cho blocking read sau khi kết nối. Dùng `connect(endpoint, timeout)` cho từng connect và có deadline riêng nếu cần hạn chế toàn bộ luồng.

**4.** Máy chủ chỉ lắng nghe `127.0.0.1:port`. Vì sao client thử `::1` thất bại rồi thử `127.0.0.1` thành công?

**Đáp:** IPv6 loopback `::1` và IPv4 loopback `127.0.0.1` là những địa chỉ khác nhau. Listener bind chỉ vào IPv4 không tự nhận kết nối tới IPv6 loopback.

**5.** Khi TCP đã connected nhưng HTTPS báo mismatch chứng chỉ, nên xem lỗi ở lớp nào?

**Đáp:** TLS và hostname verification. Cần kiểm tra hostname gốc, SNI, certificate, proxy và cấu hình giao thức; không mặc định lỗi DNS.

**6.** Vì sao có thể retry TCP connect tới IP khác nhưng không được tự động retry `POST` sau read timeout?

**Đáp:** Connect chưa thành lập thì chưa có dữ liệu nghiệp vụ gửi trên kết nối đó; sau khi đã gửi request, server có thể đã xử lý dù client chưa nhận phản hồi.

**7.** Vì sao demo không phụ thuộc thứ tự `getAllByName("localhost")`?

**Đáp:** Resolver/hosts/OS có thể trả số lượng hoặc thứ tự IP khác nhau. Demo chủ động tạo danh sách IPv6 rồi IPv4 để kiểm tra chính xác thuật toán fallback; `connectHost` cho thấy cách dùng DNS/name resolution thật.

## 12. Ghi nhớ

- **DNS/name resolution** giúp tìm IP từ hostname; **TCP connect** thử một IP và port.
- Java `InetAddress.getAllByName` có thể trả **nhiều IPv4/IPv6**, không bảo đảm thứ tự/khả năng kết nối.
- Phân giải thất bại thường thể hiện qua `UnknownHostException`; nếu phân giải thành công nhưng một IP lỗi, hãy xem `ConnectException`, connect timeout hoặc route và có thể **thử IP tiếp theo**.
- Mỗi nỗ lực connect nên có timeout và socket riêng; đóng socket thất bại, giữ nguyên nhân, đặt deadline tổng.
- Khi TCP đã thành công, lỗi TLS, HTTP và nghiệp vụ là các giai đoạn khác. **Fallback TCP** không đồng nghĩa retry request ứng dụng an toàn.

Tài liệu tham khảo: JDK 17 API `java.net.InetAddress`, `java.net.Socket`, `java.net.InetSocketAddress`; RFC 8305 (*Happy Eyeballs Version 2*).