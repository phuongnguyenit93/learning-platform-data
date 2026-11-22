# Phân giải thuận, phân giải ngược và chi phí của việc lấy tên máy trong Java

Trong lập trình mạng, một địa chỉ IP trả lời câu hỏi **gói tin phải đi đến đâu**, còn tên máy (hostname) giúp con người và ứng dụng gọi một đích bằng tên. Hai chiều chuyển đổi giữa tên và IP có mục đích, điều kiện thành công và chi phí khác nhau. Đặc biệt, thao tác tưởng như chỉ để hiển thị tên máy có thể kích hoạt truy vấn tên qua mạng và làm chậm một luồng xử lý.

## 1. Phân giải thuận (forward resolution): tên máy → địa chỉ IP

Phân giải thuận tìm một hoặc nhiều địa chỉ IP ứng với một tên, chẳng hạn `api.example.com`. Trong DNS:

- Bản ghi **A** ánh xạ tên sang địa chỉ IPv4.
- Bản ghi **AAAA** ánh xạ tên sang địa chỉ IPv6.
- **CNAME** khai báo bí danh tới tên khác; resolver có thể phải theo chuỗi bí danh để tìm A/AAAA.
- Một tên có thể trả về **nhiều IP**, các bản ghi có TTL và tập địa chỉ/thứ tự có thể thay đổi theo thời gian, vị trí hoặc chính sách cân bằng tải.

Mô hình khái niệm:

```text
Tên: api.example.com
       |
       | tra cứu thuận (A/AAAA, có thể qua CNAME)
       v
IP: 192.0.2.10 / 2001:db8::10 / ... (ví dụ minh họa)
```

**Không đồng nhất name resolution với đúng một truy vấn DNS.** JVM có thể lấy kết quả qua cache địa chỉ, cấu hình tên của máy, tệp hosts, hệ thống resolver hoặc dịch vụ tên khác; DNS là trường hợp phổ biến nhưng không phải đường đi duy nhất. Ngay cả hai lần gọi cùng API cũng có thể khác thời gian và kết quả.

Trong Java 17+, `InetAddress.getByName(host)` trả về **một** địa chỉ được phân giải; `InetAddress.getAllByName(host)` trả về mảng các địa chỉ theo dịch vụ phân giải mà máy đang sử dụng. Không giả định địa chỉ đầu tiên luôn là IPv4, cùng thứ tự hoặc ổn định giữa các lần chạy. Nếu không tìm được địa chỉ, các phương thức này có thể ném `UnknownHostException`.

Với một chuỗi IP literal hợp lệ, ví dụ `"192.0.2.10"`, `getByName` chỉ cần diễn giải địa chỉ, không phải tra tên miền. Đây là điểm khác biệt quan trọng khi đo chi phí.

## 2. Phân giải ngược (reverse resolution): địa chỉ IP → tên máy

Phân giải ngược tìm tên tương ứng với IP. Trong DNS, cơ chế thường dùng bản ghi **PTR**:

- IPv4: đảo thứ tự octet và thêm `in-addr.arpa`. Ví dụ địa chỉ tài liệu `203.0.113.7` được tra dưới tên `7.113.0.203.in-addr.arpa`.
- IPv6: đảo từng ký tự hệ 16 của địa chỉ đã khai triển, dùng miền `ip6.arpa`.
- Trả lời PTR, nếu tồn tại, là một tên do bên quản lý vùng reverse công bố; nó không mặc nhiên là tên mà ứng dụng từng dùng để kết nối.

```text
Forward: api.example.com --A/AAAA--> 203.0.113.7
Reverse: 203.0.113.7 ----PTR-----> edge.example.net (nếu có)
```

Hai chiều **không phải hai hàm nghịch đảo**. Một tên có nhiều IP; nhiều tên có thể trỏ về một IP; một IP có thể không có PTR, có nhiều PTR hoặc trả về tên khác với tên truy cập ban đầu. Trường hợp CDN, NAT, máy chủ dùng chung hoặc địa chỉ động càng khiến mối quan hệ này không đối xứng.

Một số hệ thống còn kiểm tra **forward-confirmed reverse DNS (FCrDNS)**: lấy PTR để được tên, phân giải thuận tên ấy và xem IP ban đầu có nằm trong kết quả hay không. Cách kiểm tra này cải thiện tính nhất quán cấu hình, **không chứng minh danh tính hay quyền truy cập**. Không tự suy diễn rằng mọi API Java đều thực hiện FCrDNS theo cùng một cách: Java công bố `getCanonicalHostName()` là thao tác cố gắng tìm tên đầy đủ, và kết quả thực tế phụ thuộc resolver/hệ điều hành.

**Nếu không có bản ghi hoặc không lấy được tên**, Java có thể trả về chuỗi IP dạng số. Một IP tồn tại và kết nối được không có nghĩa là có reverse DNS hợp lệ.

## 3. Phân biệt các API Java: có thể tra cứu tên hay không?

| API | Ý nghĩa | Khả năng đụng dịch vụ tên |
| --- | --- | --- |
| `InetAddress.getByName("example.com")` | Lấy một IP từ hostname | Có thể phân giải thuận; bị ảnh hưởng cache/resolver |
| `InetAddress.getAllByName("example.com")` | Lấy các IP được công bố/tra cứu | Có thể phân giải thuận |
| `InetAddress.getByAddress(byte[])` | Tạo đối tượng từ 4 byte IPv4 hoặc 16 byte IPv6 | **Không** tra cứu ngược tại lúc tạo |
| `address.getHostAddress()` | Đổi địa chỉ đã có sang chuỗi IP | **Không** tra cứu tên |
| `address.getHostName()` | Lấy tên gắn với địa chỉ | Nếu đối tượng được tạo từ hostname, thường trả lại tên đã nhớ; nếu chỉ có IP, **có thể tra ngược** |
| `address.getCanonicalHostName()` | Cố tìm tên miền đầy đủ (FQDN) của IP | **Có thể tra ngược**; không bảo đảm trả về FQDN |
| `InetAddress.getLocalHost()` | Lấy địa chỉ của máy hiện tại thông qua tên máy cục bộ | Có thể cần phân giải tên máy; có thể thất bại |
| `inetSocketAddress.getHostName()` | Lấy phần hostname của địa chỉ socket | **Có thể** tra ngược khi đối tượng hình thành từ IP literal |
| `inetSocketAddress.getHostString()` | Lấy tên đã lưu hoặc IP dạng chuỗi | Được thiết kế để **tránh** reverse lookup |

Điểm dễ nhầm nhất:

```java
InetAddress resolved = InetAddress.getByName("example.com");
resolved.getHostName();              // Có thể trả ngay tên "example.com" đã nhớ.
resolved.getCanonicalHostName();     // Có thể thực hiện tra cứu tên thực sự.

InetAddress fromBytes =
        InetAddress.getByAddress(resolved.getAddress());
fromBytes.getHostAddress();          // Chỉ đổi IP sang chuỗi; không cần DNS.
fromBytes.getHostName();             // Giờ có thể phải tra ngược từ IP.
```

Đoạn trên minh họa hành vi API, **không phải chương trình Java độc lập**. Lời gọi đầu cần môi trường có thể phân giải `example.com`. Việc một lời gọi `getHostName()` nhanh không chứng tỏ lời gọi đó luôn rẻ: đối tượng có thể đã giữ hostname từ bước phân giải thuận hoặc kết quả đã nằm trong cache.

`getCanonicalHostName()` không phải phép “chuẩn hóa hostname” thuần túy trên chuỗi. Nếu mục đích chỉ là in IP của client vào log, dùng `getHostAddress()`; nếu muốn lưu tên đích do người dùng cấu hình, giữ nguyên chuỗi hostname ban đầu.

## 4. Ví dụ Java 17+ không phụ thuộc DNS: tạo địa chỉ và đọc thông tin an toàn

Tệp **`NameLookupBasics.java`**:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;

public class NameLookupBasics {
    public static void main(String[] args) throws Exception {
        // 203.0.113.0/24 dành cho tài liệu; không gọi DNS khi tạo từ byte.
        byte[] rawIpv4 = {(byte) 203, 0, 113, 7};
        InetAddress address = InetAddress.getByAddress(rawIpv4);

        System.out.println("IP: " + address.getHostAddress());

        // Chỉ lưu hostname + port; không phân giải hostname lúc tạo.
        InetSocketAddress endpoint =
                InetSocketAddress.createUnresolved("example.com", 443);
        System.out.println("Host: " + endpoint.getHostString());
        System.out.println("Unresolved: " + endpoint.isUnresolved());
    }
}
```

Chạy:

```sh
javac NameLookupBasics.java
java NameLookupBasics
```

Kết quả chính xác của chương trình:

```text
IP: 203.0.113.7
Host: example.com
Unresolved: true
```

Giải thích: `getByAddress` chỉ tạo địa chỉ từ 4 byte, `getHostAddress` chỉ định dạng IP; `createUnresolved` giữ hostname mà chưa phân giải. **Unresolved không có nghĩa là đã kết nối được**: `endpoint.getAddress()` sẽ là `null`, và API dùng địa chỉ này để kết nối phải xử lý quy trình phân giải phù hợp. Mã cố tình không gọi `getHostName()` hoặc `getCanonicalHostName()` của `address` để tránh phát sinh reverse lookup.

## 5. Ví dụ đo chi phí forward và reverse thực tế

Tệp **`LookupCost.java`** (độc lập, biên dịch trên Java 17+):

```java
import java.net.InetAddress;
import java.util.concurrent.Callable;

public class LookupCost {
    private static <T> T measure(String label, Callable<T> operation)
            throws Exception {
        long start = System.nanoTime();
        try {
            return operation.call();
        } finally {
            double elapsedMs = (System.nanoTime() - start) / 1_000_000.0;
            System.out.printf("%s: %.3f ms%n", label, elapsedMs);
        }
    }

    public static void main(String[] args) throws Exception {
        String hostname = args.length > 0 ? args[0] : "example.com";

        InetAddress resolved = measure(
                "Forward", () -> InetAddress.getByName(hostname));
        System.out.println("Resolved IP: " + resolved.getHostAddress());

        // Bỏ hostname đã nhớ để thấy rõ khả năng tra ngược từ IP.
        InetAddress ipOnly = InetAddress.getByAddress(resolved.getAddress());

        String reverseName = measure("Reverse getHostName",
                ipOnly::getHostName);
        System.out.println("Reverse result: " + reverseName);

        String canonicalName = measure("Canonical getCanonicalHostName",
                ipOnly::getCanonicalHostName);
        System.out.println("Canonical result: " + canonicalName);
    }
}
```

Chạy:

```sh
javac LookupCost.java
java LookupCost example.com
```

**Không có một stdout cố định**: IP, hostname ngược và số mili-giây tùy mạng, resolver, cache, JVM và cấu hình DNS; thiếu DNS có thể dẫn tới `UnknownHostException`. Kết quả reverse/canonical có thể chính là IP. Đây là ví dụ quan sát **latency**, không phải benchmark đủ điều kiện kết luận chênh lệch hiệu năng. Lời gọi sau có thể hưởng cache đã được làm nóng bởi lời gọi trước; hãy tách mẫu cold/warm, lặp nhiều lần, ghi nhận cả lỗi và đo percentile (p50/p95/p99) khi đánh giá thực tế.

Phương thức `measure` dùng `System.nanoTime()` để đo thời gian trôi qua, tránh dùng thời gian lịch `currentTimeMillis()` cho phép đo độ trễ ngắn. Nó vẫn đo tổng thời gian đồng bộ của lời gọi (có thể có thời gian chờ dịch vụ tên); con số này **không phải riêng thời gian xử lý tại DNS server**.

## 6. Tại sao “lấy tên máy” có thể đắt?

Giả sử server nhận một kết nối TCP, có sẵn IP của client, sau đó ghi log:

```java
// Trích đoạn minh họa: socket là java.net.Socket đã kết nối.
String clientIp = socket.getInetAddress().getHostAddress(); // Không reverse DNS.
String clientName = socket.getInetAddress().getHostName();  // Có thể reverse DNS.
```

Nếu `InetAddress` chỉ giữ IP, dòng thứ hai có thể phải hỏi resolver: đọc cache → gửi truy vấn PTR → chờ phản hồi → xử lý kết quả (và các bước xác minh của triển khai, nếu có). Một truy vấn lạnh thành công có thể nhanh, nhưng timeout, retry, DNS bị lỗi, tuyến mạng xa hoặc PTR thiếu có thể khiến thời gian chờ tăng rõ rệt. **Không có ngưỡng “luôn mất X ms” cho mọi máy và mọi DNS.**

Các nguồn chi phí cần phân biệt:

1. **I/O và thời gian chờ:** resolver có thể phải gọi dịch vụ tên qua mạng, chờ phản hồi, thử lại hoặc thử máy chủ khác. API đồng bộ có thể giữ luồng gọi trong lúc đợi.
2. **Cache hit/miss:** kết quả trong cache có thể trả về nhanh; cache hết hạn hoặc sai cấu hình khiến truy vấn phát sinh trở lại. Cả tra thuận và tra ngược có thể có đường cache riêng theo triển khai.
3. **Bất cân xứng dữ liệu:** dịch vụ web có thể có bản ghi A/AAAA tốt nhưng IP của client không có PTR, hoặc PTR trỏ về một tên không thể phân giải theo chiều thuận.
4. **Khuếch đại theo lưu lượng:** một thao tác tra ngược đặt trong đường xử lý **mỗi request, mỗi kết nối, mỗi sự kiện log** có thể tăng p99 latency và sử dụng tài nguyên nếu xảy ra đồng thời.
5. **Địa chỉ IPv4/IPv6 và môi trường:** thứ tự lựa chọn IP, chính sách resolver, VPN, container, mạng doanh nghiệp, tệp hosts và hệ điều hành có thể làm thay đổi đường tra cứu.

Hệ quả thiết kế: **đừng biến tính năng hiển thị hostname thành một phụ thuộc đồng bộ của đường xử lý chính** khi chỉ cần nhận diện kết nối hoặc ghi log.

## 7. DNS cache và cách hiểu đúng về TTL trong JVM

`InetAddress` có cơ chế cache cho kết quả phân giải tên **thành công và không thành công**. Với Java 17, các thuộc tính bảo mật thường liên quan gồm:

| Thuộc tính | Mục đích |
| --- | --- |
| `networkaddress.cache.ttl` | Thời gian giữ kết quả tra tên thành công trong cache của JVM, tính bằng giây |
| `networkaddress.cache.negative.ttl` | Thời gian giữ kết quả phân giải thất bại, tính bằng giây |

Theo tài liệu Java 17, giá trị `0` nghĩa là không lưu cache, `-1` nghĩa là lưu vô thời hạn; chính sách mặc định của cache thành công có thể phụ thuộc cấu hình và bản triển khai. Đây là **security properties** (có thể cấu hình trong `java.security` hoặc bằng cơ chế đặt security properties phù hợp), không nên mặc định rằng truyền `-Dnetworkaddress.cache.ttl=...` như một system property thông thường chắc chắn thay đổi chính sách trên mọi JDK.

Lưu ý thực hành:

- **TTL DNS của bản ghi** và **TTL cache thực tế JVM/resolver/hệ điều hành** là các tầng khác nhau; không suy ra một kết quả Java phải đổi ngay khi bản ghi DNS đổi.
- Cache âm giúp giảm số lần tra tên không tồn tại, nhưng cũng có thể khiến một hostname vừa được sửa DNS chưa hoạt động tức thì trong tiến trình.
- Đừng tự thêm cache vô hạn không có giới hạn kích thước và thời hạn; với ứng dụng có yêu cầu cập nhật địa chỉ, phải cân nhắc độ mới, cache eviction, thời gian tồn tại và cơ chế ghi nhận lỗi.
- Một phép đo sau lần đầu thường phản ánh cache; muốn chẩn đoán độ trễ phải ghi nhận trạng thái cache và môi trường thử nghiệm.

Tham khảo: [JDK 17 Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html).

## 8. Quyết định dùng hostname hay IP trong ứng dụng

| Tình huống | Cách làm phù hợp | Lý do |
| --- | --- | --- |
| Ghi log IP của client, metric theo địa chỉ | `getHostAddress()` | Tránh nhu cầu reverse DNS |
| Lưu hostname đích được cấu hình | Lưu chuỗi hostname gốc | Không phụ thuộc kết quả PTR; giữ ý định cấu hình |
| Quan sát reverse DNS để hỗ trợ vận hành | Thực hiện riêng, có timeout ở lớp ứng dụng, giới hạn đồng thời và cache có hạn | Không để lookup làm chậm luồng request |
| Cần kết nối tới dịch vụ theo hostname | Dùng hostname và chính sách kết nối/resolution phù hợp | Dịch vụ có thể đổi IP, có nhiều địa chỉ, cần SNI/TLS hostname |
| Cần toàn bộ các IP hiện được resolver trả về | `getAllByName(host)` | Xử lý mảng địa chỉ, không dựa một IP duy nhất |
| Muốn hiển thị đầu cuối `InetSocketAddress` mà không tra ngược | `getHostString()` | API tránh reverse lookup khi chỉ cần chuỗi hiển thị |
| Muốn biết tên FQDN của IP để chẩn đoán | `getCanonicalHostName()` với cơ chế giới hạn chi phí | Là best effort; kết quả có thể là IP |

Ví dụ xử lý request (đoạn minh họa, cần `socket` đã kết nối):

```java
String peerIp = socket.getInetAddress().getHostAddress();
// Ghi peerIp vào log/metric trong đường xử lý chính.
// Nếu thật sự cần hostname, đưa tác vụ tra ngược sang bước enrichment riêng.
```

Cần phân biệt **thời hạn của tác vụ ứng dụng** với **việc hủy truy vấn đang chạy**: đặt timeout cho một `CompletableFuture`, ví dụ, có thể giúp bên chờ ngừng đợi, nhưng không tự bảo đảm dừng ngay lookup đồng bộ đang thực thi ở luồng khác. Vì vậy phải giới hạn pool và số lookup đang chạy; không tạo luồng vô hạn để “né” độ trễ DNS.

Với HTTPS/TLS, reverse DNS không xác nhận danh tính máy chủ: kiểm tra chứng chỉ phải dựa trên **hostname đích hợp lệ theo kết nối**, không tin vào tên PTR vừa tra được. Không thay hostname cấu hình bằng IP/PTR chỉ để tránh DNS nếu việc đó làm sai định tuyến ảo, SNI hoặc xác minh chứng chỉ.

## 9. Cách kiểm tra và chẩn đoán

Từ máy có `dig`, có thể kiểm tra riêng dữ liệu DNS:

```sh
dig +short example.com A
dig +short example.com AAAA
dig -x 203.0.113.7 +short
```

Hai lệnh đầu hỏi bản ghi tra thuận; lệnh thứ ba hỏi PTR cho IP tài liệu (có thể **không có kết quả**, đó không phải lỗi của chương trình). Trên Windows có thể dùng `nslookup example.com` hoặc công cụ tra DNS tương đương. Kết quả `dig`/`nslookup` có thể **khác Java** vì cách các công cụ sử dụng resolver, tệp hosts và cache không hoàn toàn giống nhau.

Khi gặp “một dòng log làm API chậm”, hãy kiểm tra theo thứ tự:

1. Xác định đường gọi có `getHostName()`, `getCanonicalHostName()` hoặc `InetSocketAddress.getHostName()` trên đối tượng chỉ có IP không.
2. So sánh thời gian lấy số IP bằng `getHostAddress()` với thời gian tra tên, từ cùng máy/chạy cùng JVM; ghi nhận cả trường hợp thất bại.
3. Kiểm tra PTR tương ứng có tồn tại hay không và resolver có timeout/retry bất thường không.
4. Kiểm tra cache JVM và resolver, môi trường container/VPN, cũng như số lookup chạy đồng thời.
5. Nếu chức năng không yêu cầu tên ngược, thay bằng IP/`getHostString()`; nếu có yêu cầu, chuyển sang enrichment được kiểm soát và đo lại độ trễ thực tế.

## 10. Lỗi hiểu thường gặp

- **“Forward trả ra IP nào thì reverse phải trả lại hostname ban đầu.”** Sai: A/AAAA và PTR được quản trị độc lập, quan hệ nhiều–nhiều và có thể thiếu.
- **“Chỉ in ra hostname nên không phát sinh I/O.”** Sai với `getHostName()` khi đối tượng chỉ có IP, hoặc với `getCanonicalHostName()`.
- **“`getByAddress` sẽ tự tra PTR.”** Sai: tạo đối tượng từ byte không tự tra ngược; lookup có thể đến ở phương thức gọi sau.
- **“`getHostAddress()` và `getHostName()` có chi phí tương đương.”** Sai về nguyên tắc: phương thức đầu định dạng IP sẵn có, phương thức sau có thể tra cứu tên.
- **“Có PTR là chứng minh client đáng tin.”** Sai: PTR là metadata tên, không phải căn cứ xác thực hay phân quyền.
- **“Một lần đo nhanh nghĩa là production luôn nhanh.”** Sai: cache, TTL, network, retry và concurrency thay đổi độ trễ.
- **“Cache vô thời hạn luôn là tối ưu.”** Sai: có nguy cơ giữ địa chỉ lỗi thời và làm khó việc chuyển dịch vụ.

## 11. Ghi nhớ khi thiết kế code Java Networking

**Forward** trả lời “hostname hiện phân giải tới IP nào?”; **reverse** trả lời “resolver có tên nào gắn với IP này?” — chúng không buộc đối xứng. Trong Java, `getHostAddress()` phù hợp khi cần địa chỉ để ghi log nhanh; `getHostName()` có thể trả tên đã lưu hoặc phải tra ngược; `getCanonicalHostName()` là best effort có thể tốn thời gian. Luôn đánh giá chi phí của **lookup trong đường xử lý đồng bộ**, khả năng thất bại của PTR và lớp cache trước khi dùng hostname cho mỗi request/kết nối.

Nguồn API chính thức để tự đối chiếu hành vi: [Java 17 `InetAddress`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html), [Java 17 `InetSocketAddress`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html).