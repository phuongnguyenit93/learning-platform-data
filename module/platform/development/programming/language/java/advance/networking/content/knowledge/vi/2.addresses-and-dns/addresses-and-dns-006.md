# Bộ nhớ đệm kết quả DNS thành công, thất bại và dữ liệu hết hạn trong Java

Khi ứng dụng Java kết nối đến `api.example.com`, tên máy cần được phân giải thành địa chỉ IP. Tra cứu lặp lại có thể tốn thời gian; nhưng giữ kết quả quá lâu cũng có thể khiến ứng dụng tiếp tục gọi IP đã thay đổi. `java.net.InetAddress` cung cấp bộ nhớ đệm cho cả **kết quả phân giải thành công (positive cache)** và **kết quả phân giải thất bại (negative cache)**. Trên JDK hỗ trợ, chính sách **stale cache** còn cho phép dùng tạm địa chỉ thành công cũ khi việc làm mới không thành công.

**Phạm vi phiên bản:** các khái niệm positive/negative và hai thuộc tính `networkaddress.cache.ttl`, `networkaddress.cache.negative.ttl` áp dụng cho Java 17+. Thuộc tính `networkaddress.cache.stale.ttl` được tài liệu Java 21 mô tả, nhưng **không được tài liệu Java 17 liệt kê**; chỉ cấu hình stale sau khi xác minh JDK/runtime thực tế có hỗ trợ. Bài học xét việc phân giải tên qua `InetAddress`, không mặc định áp dụng cho mọi thư viện DNS của bên thứ ba.

## 1. Kết quả nào được lưu và lưu ở đâu?

`InetAddress.getByName(host)` trả một địa chỉ; `InetAddress.getAllByName(host)` trả các địa chỉ mà bộ phân giải cung cấp. Với bộ phân giải mặc định, dữ liệu có thể đến từ cấu hình máy (ví dụ hosts file), bộ phân giải của hệ điều hành và dịch vụ đặt tên như DNS. Do đó, **một lần gọi `InetAddress` không đồng nghĩa một gói truy vấn DNS đã ra mạng**.

~~~text
Ứng dụng Java gọi InetAddress.getAllByName(host)
          |
          v
  Cache tên/địa chỉ của InetAddress trong JVM
          |
       Cache hit? ---- có ----> trả IP đã lưu hoặc ném lỗi đã lưu
          |
         không
          v
 Bộ phân giải được cấu hình (hosts/OS/DNS/...)
          |
          +---- phân giải thành công ----> positive cache ----> danh sách IP
          |
          +---- phân giải thất bại -----> negative cache ----> UnknownHostException
~~~

Ba lớp thường bị nhầm lẫn:

| Lớp | Nội dung | Điểm cần nhớ |
| --- | --- | --- |
| Cache của `InetAddress` trong JVM | Kết quả thành công/thất bại khi ứng dụng phân giải tên qua API này | Chịu chính sách Java security properties; thường phải quan sát theo từng tiến trình JVM |
| Resolver/cache của hệ điều hành hoặc DNS đệ quy | Dữ liệu do hệ thống và hạ tầng DNS lưu | Có chính sách TTL và cách làm mới riêng |
| Connection pool / TCP socket | Kết nối đã mở tới một IP | Đổi cache DNS **không tự động chuyển** socket đang dùng sang IP khác |

TTL trong DNS record do hạ tầng DNS công bố và TTL của **cache `InetAddress`** là hai vấn đề cần phân biệt. Không được suy ra rằng TTL của JVM chắc chắn bằng TTL record DNS. Một số HTTP client, Netty resolver hoặc service-discovery client có cache riêng; cần kiểm tra đường phân giải thực tế trước khi áp dụng chính sách này.

## 2. Positive cache: lưu lần phân giải thành công

Giả sử tại thời điểm `t0`, bộ phân giải trả `service.example -> 192.0.2.10`. Nếu positive TTL là 30 giây, những lượt phân giải qua cùng cache trong khoảng hiệu lực có thể dùng địa chỉ này mà không gọi bộ phân giải phía dưới. Khi mục cache hết hạn, một lượt tra cứu mới có thể phải phân giải lại và nhận `192.0.2.20`.

**Ý nghĩa:** giảm độ trễ và tải truy vấn, nhưng nếu TTL quá dài thì ứng dụng có thể tiếp tục dùng IP cũ sau khi dịch vụ thay địa chỉ (deploy, failover, cân bằng tải). TTL bằng `-1` là lưu vô hạn theo chính sách; `0` là không cache; số dương là số giây. Mặc định positive TTL được tài liệu Java mô tả là **phụ thuộc cách triển khai** khi không có Security Manager; không lấy một con số mặc định từ môi trường này áp lên mọi JVM.

Địa chỉ trả về có thể là IPv4, IPv6 hoặc nhiều địa chỉ. Kết quả `getAllByName` và thứ tự địa chỉ có thể khác tùy máy. Không dùng một IP cố định hay thời gian truy vấn cố định làm kết quả kỳ vọng cho các ví dụ mạng.

## 3. Negative cache: lưu lần phân giải thất bại

Nếu bộ phân giải không tìm được địa chỉ hợp lệ cho hostname, lời gọi `InetAddress.getByName`/`getAllByName` có thể ném `UnknownHostException`. JVM có thể ghi nhớ kết quả thất bại này trong **negative TTL**. Các lần gọi tiếp theo trong khoảng đó có thể thất bại ngay từ cache, dù nguyên nhân bên ngoài đã được khắc phục.

Ví dụ:

1. `t0`: ứng dụng tra `new-service.example` khi tên dịch vụ chưa được tạo hoặc hệ thống DNS đang lỗi; tra cứu thất bại.
2. Negative TTL = 10 giây: trong khoảng hiệu lực, các tra cứu lặp lại có thể tiếp tục nhận lỗi từ cache.
3. Khi negative entry hết hạn, lần tra cứu mới có thể thử lại. Nếu tên đã hợp lệ, ứng dụng có thể nhận IP và tạo positive entry.

**Không đồng nhất mọi `UnknownHostException` với “DNS trả NXDOMAIN”.** Lỗi có thể chịu ảnh hưởng từ cấu hình resolver, mạng hay dịch vụ đặt tên. API này không cung cấp cơ sở để quy tất cả lỗi tra cứu thành một DNS response cụ thể. Negative cache hữu ích để chống truy vấn lặp vô ích, nhưng TTL quá lớn có thể kéo dài sự cố sau khi DNS hồi phục. Theo tài liệu Java, negative TTL mặc định là **10 giây**; cấu hình triển khai cụ thể vẫn cần được kiểm tra.

## 4. Dữ liệu hết hạn khác với dữ liệu stale

**Expired** nghĩa là thời gian dùng kết quả positive theo TTL thông thường đã hết; một lần phân giải tiếp theo cần xét làm mới. **Stale** nghĩa là một kết quả positive cũ đã hết hạn nhưng có thể còn được giữ lại theo chính sách riêng để dùng làm phương án dự phòng **khi tra cứu làm mới thất bại**.

~~~text
Trước đó từng phân giải thành công?
   |
   +-- Không --> không có IP cũ để dùng làm stale
   |
   +-- Có --> positive entry còn trong TTL? -- Có --> dùng entry hiện hành
                         |
                        Không
                         |
                     thử làm mới
                         |
         +---------------+----------------+
         |                                |
       thành công                       thất bại
         |                                |
   cập nhật IP/TTL           stale được bật, còn hợp lệ?
                                          |
                                 +--------+--------+
                                 |                 |
                                Có                Không
                                 |                 |
                           dùng IP cũ         báo lỗi phân giải
~~~

Trên **Java 21**, `networkaddress.cache.stale.ttl` cho phép giữ và dùng tên cũ khi positive TTL đã hết và việc làm mới không thành công. Nếu stale TTL lớn hơn positive TTL, tài liệu `InetAddress` mô tả positive TTL là **khoảng làm mới**: ví dụ positive TTL = 30 giây, stale TTL = 1 ngày, JVM có thể thử refresh theo chu kỳ 30 giây trong khi vẫn có cửa sổ sử dụng dữ liệu cũ. Giá trị stale `0` hoặc không đặt nghĩa là **không sử dụng stale**; giá trị âm bị bỏ qua.

**Không suy diễn stale thành “cứ hết TTL là trả IP cũ”**: phải có kết quả thành công trước đó, lần làm mới gặp thất bại và chính sách stale còn cho phép sử dụng. Khi làm mới thành công, địa chỉ mới được dùng theo chính sách. Khi không có dữ liệu cũ hợp lệ để dự phòng, ứng dụng vẫn có thể nhận lỗi phân giải.

Stale có ích nếu hạ tầng DNS tạm gián đoạn nhưng IP cũ vẫn phục vụ. Tuy nhiên, IP cũ có thể đã bị thu hồi, chuyển chủ hoặc không còn trỏ đúng hệ thống. **Giữ được IP không bảo đảm kết nối TCP/TLS/HTTP thành công hay an toàn.** Đây là đánh đổi giữa khả năng tiếp tục hoạt động và độ mới/chính xác của đích kết nối.

## 5. Cấu hình chính sách cache của JVM

| Java security property | Vai trò | `0` | Số dương | `-1` |
| --- | --- | --- | --- | --- |
| `networkaddress.cache.ttl` | Positive result | Không cache | Số giây lưu kết quả thành công | Cache vô hạn |
| `networkaddress.cache.negative.ttl` | Negative result | Không cache | Số giây lưu thất bại | Cache vô hạn |
| `networkaddress.cache.stale.ttl` (JDK có hỗ trợ, ví dụ Java 21) | Giữ kết quả thành công cũ để dự phòng khi refresh lỗi | Không dùng stale | Số giây theo chính sách stale | Giá trị âm bị bỏ qua, không mang nghĩa cache vô hạn |

Đây là **security properties**, không phải system properties tương ứng. Vì thế, `-Dnetworkaddress.cache.ttl=30` và `System.setProperty("networkaddress.cache.ttl", "30")` **không phải cách cấu hình chính thức**. Có thể đặt trong `$JAVA_HOME/conf/security/java.security`, hoặc tốt hơn cho một bài thử độc lập, dùng tệp bổ sung qua `-Djava.security.properties=...`. Một dấu `=` nối thêm tệp vào cấu hình chính; không dùng cú pháp hai dấu `==` để vô tình thay thế toàn bộ cấu hình bảo mật nền.

Ví dụ **chính sách thử nghiệm**, không phải giá trị mặc định hoặc khuyến nghị dùng nguyên xi cho production:

~~~properties
# dns-cache.security — Java 17+
networkaddress.cache.ttl=3
networkaddress.cache.negative.ttl=2

# Chỉ bật nếu JDK hỗ trợ stale (ví dụ Java 21+):
networkaddress.cache.stale.ttl=15
~~~

Với Java 17, bỏ hoặc comment dòng stale; Java 17 không liệt kê cơ chế này trong tài liệu `InetAddress`. Với JDK đã xác minh hỗ trợ, có thể bật khi muốn nghiên cứu quá trình refresh thất bại.

Các giá trị được JVM đọc theo cơ chế security configuration. Có thể dùng `Security.setProperty("networkaddress.cache.ttl", "3")` từ Java **rất sớm, trước lần phân giải DNS đầu tiên**, nhưng đặt muộn có thể không ảnh hưởng chính sách đã được khởi tạo/giữ trong cache. Cấu hình ở lúc khởi động, khởi động tiến trình mới cho mỗi kịch bản và kiểm tra hiệu lực là cách dễ lặp lại hơn.

## 6. Chương trình Java 17+ quan sát kết quả tra cứu

Lưu đúng tệp `DnsCacheProbe.java`:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.security.Security;
import java.util.Arrays;
import java.util.stream.Collectors;

public class DnsCacheProbe {
    private static void lookup(String host) {
        long start = System.nanoTime();
        try {
            InetAddress[] addresses = InetAddress.getAllByName(host);
            String ips = Arrays.stream(addresses)
                    .map(InetAddress::getHostAddress)
                    .collect(Collectors.joining(", "));
            System.out.printf("%s -> OK [%s]%n", host, ips);
        } catch (UnknownHostException ex) {
            System.out.printf("%s -> UNKNOWN_HOST%n", host);
        } finally {
            long millis = (System.nanoTime() - start) / 1_000_000;
            System.out.printf("  elapsed=%d ms%n", millis);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("Java feature version: "
                + Runtime.version().feature());

        for (String key : new String[] {
                "networkaddress.cache.ttl",
                "networkaddress.cache.negative.ttl",
                "networkaddress.cache.stale.ttl"
        }) {
            System.out.printf("%s=%s%n", key, Security.getProperty(key));
        }

        String goodHost = args.length > 0 ? args[0] : "localhost";
        String badHost = args.length > 1
                ? args[1] : "no-such-host.invalid";

        for (int round = 1; round <= 3; round++) {
            System.out.println("round=" + round);
            lookup(goodHost);
            lookup(badHost);
            if (round < 3) {
                Thread.sleep(1_500);
            }
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa hai tệp:

~~~bash
javac DnsCacheProbe.java
java -Djava.security.properties=dns-cache.security DnsCacheProbe
~~~

Có thể thay hai tên máy bằng hostname của môi trường thử nghiệm:

~~~bash
java -Djava.security.properties=dns-cache.security DnsCacheProbe localhost no-such-host.invalid
~~~

**Cách đọc output:** đầu ra có `Java feature version: ...`, các dòng cấu hình và ba vòng `round=1`, `round=2`, `round=3`. Với cấu hình mẫu, các dòng property explicit sẽ hiển thị lần lượt `3`, `2`, `15` nếu tệp được tải; trên JDK không hỗ trợ stale, **giá trị property được in ra cũng không chứng minh runtime thực thi chính sách stale**. `localhost` thường trả `OK [...]` bằng hosts file/loopback; `no-such-host.invalid` thường trả `UNKNOWN_HOST`, nhưng cấu hình nội bộ có thể thay đổi hai kết quả này. IP, số lượng địa chỉ, thời gian `elapsed` và cách xử lý hostname phụ thuộc máy, nên không có một stdout địa chỉ/thời gian cố định cho tất cả môi trường.

**Giới hạn bằng chứng:** nhiều lần `elapsed` nhỏ không chứng minh riêng JVM cache hit: có thể là hosts file, OS cache, DNS recursive cache, đường mạng nhanh hoặc ảnh hưởng warm-up. Chương trình chứng minh cách gọi API, đọc cấu hình và phân biệt thành công/thất bại, nhưng **không đếm được số truy vấn DNS mà JVM thực sự gửi**. Cần kiểm chứng bằng resolver/server quan sát được và một môi trường kiểm thử riêng.

## 7. Thí nghiệm có kiểm soát để xác minh cả ba trạng thái

Để kiểm chứng cache đúng nghĩa, chuẩn bị một hostname thử nghiệm do bạn kiểm soát và resolver có log truy vấn (tránh thay DNS ở production). Mỗi kịch bản khởi động JVM mới để loại trừ trạng thái cache cũ.

| Kịch bản | Thiết lập | Quan sát và giải thích |
| --- | --- | --- |
| **Positive hit / refresh** | Tên thử nghiệm phân giải được; positive TTL ngắn; gọi lặp trước rồi sau TTL; đổi IP trên resolver kiểm soát | Trước khi TTL hết, ứng dụng có thể vẫn nhận địa chỉ trước đó. Sau TTL, một lần resolve mới có thể nhận IP mới; đối chiếu log resolver để tách JVM cache khỏi cache dưới JVM |
| **Negative hit / recovery** | Bắt đầu với tên không phân giải được; negative TTL vài giây; sau đó tạo bản ghi/tình trạng hợp lệ | Có thể vẫn gặp `UnknownHostException` cho đến khi negative entry hết; sau đó thử lại mới có cơ hội thành công |
| **Stale fallback (JDK hỗ trợ)** | Ban đầu tra cứu thành công; positive TTL ngắn, stale TTL dài hơn; sau positive TTL làm cho lần refresh thất bại trong khi IP cũ vẫn dùng được | Nếu stale còn hiệu lực, `InetAddress` có thể trả IP trước đó; khi resolver khôi phục, kiểm tra lần refresh thành công thay thế IP cũ |
| **Stale không có tiền sử** | Tên chưa từng phân giải thành công trước khi resolver gặp lỗi | Không có positive entry để dùng làm stale; không kỳ vọng “stale tự xuất hiện” |
| **Stale hết giới hạn** | Duy trì lỗi làm mới vượt cửa sổ giữ stale | Cuối cùng không thể tiếp tục dựa vào địa chỉ cũ; kết quả phải được đánh giá theo resolver và chính sách hết hạn |

Trong môi trường thử nghiệm, ghi lại timestamp, phiên bản JDK, ba security properties, hostname, địa chỉ resolver trả về, số lượt thực sự đến resolver, thời điểm DNS đổi và lỗi ứng dụng. Khi đo negative cache, đối chiếu thời gian hồi phục với TTL âm; khi đo stale, phải xác nhận đã có **positive lookup thành công trước khi làm DNS thất bại**.

## 8. Chẩn đoán sự cố thực tế

**Tình huống A — DNS đã sửa nhưng Java vẫn gọi IP cũ.** Kiểm tra ứng dụng có dùng `InetAddress` không, positive TTL hiện tại, stale policy, địa chỉ IP trong connection pool, các lớp cache ở OS/resolver và có proxy hay client DNS riêng hay không. Một socket hoặc pool kết nối đang mở có thể tiếp tục trao đổi với IP cũ dù phân giải mới đã đúng.

**Tình huống B — DNS đã tạo nhưng Java tiếp tục báo `UnknownHostException`.** Xem negative TTL, thời điểm lookup thất bại đầu tiên, DNS thật sự đã phục hồi tại resolver mà JVM sử dụng chưa và cache nào khác còn lưu failure. Tránh giải pháp chỉ “tăng retry liên tục”: nếu negative entry vẫn hợp lệ, retry dày có thể không giúp ích.

**Tình huống C — khi DNS đứt, Java vẫn trả IP nhưng request mạng thất bại.** Nếu stale đang bật, IP trả về chỉ là phương án dự phòng để **thử kết nối**; cần kiểm tra IP cũ còn phục vụ, TLS hostname/SNI, routing, health checks và log lỗi TCP/HTTP. Không biến stale thành cơ chế bảo đảm dịch vụ luôn sẵn sàng.

**Tình huống D — cấu hình TTL có vẻ không tác dụng.** Kiểm tra dùng security property thay vì `-Dnetworkaddress.cache.ttl`, tệp security được load lúc JVM khởi động, phiên bản JDK, lần phân giải đã diễn ra trước khi cấu hình chưa, tên có được phân giải qua cache của thư viện khác không. Không có API Java SE công khai, phổ quát để “flush” toàn bộ `InetAddress` cache của một JVM đang chạy; khởi động tiến trình thử mới là cách kiểm tra sạch hơn.

## 9. Quyết định TTL theo mục đích vận hành

- **Positive TTL ngắn hơn** giúp nhận IP thay đổi/failover nhanh hơn, đổi lại tăng lượng truy vấn và sự phụ thuộc vào resolver. **Dài hơn** giảm lookup nhưng kéo dài thời gian sử dụng địa chỉ cũ. Không đặt `-1` theo thói quen với dịch vụ có IP động.
- **Negative TTL ngắn** thích hợp khi tên máy xuất hiện/biến mất thường xuyên (service discovery, môi trường triển khai), nhưng có thể khiến hạ tầng DNS chịu nhiều lookup lỗi. Negative TTL dài làm giảm truy vấn thất bại nhưng kéo dài sự cố giả sau khi DNS hồi phục.
- **Stale TTL** chỉ nên bật khi có yêu cầu khả dụng rõ ràng, có bằng chứng IP cũ vẫn là đích chấp nhận được và đã đánh giá rủi ro gọi nhầm máy chủ. Với endpoint nhạy cảm về bảo mật/tenant, dữ liệu cũ có thể gây hậu quả lớn hơn một lần fail-fast.
- Cần kết hợp **timeout, retry có backoff, health check và xử lý nhiều IP** ở tầng kết nối. TTL DNS không thay thế các cơ chế đó; cũng không thay thế việc tái tạo các kết nối đã hỏng.
- Chọn giá trị dựa trên tuổi thọ DNS của hạ tầng, tốc độ failover mong muốn, lưu lượng truy vấn, khả năng chịu lỗi, kết quả thử nghiệm có log. Không có cấu hình ba số dùng đúng cho mọi dịch vụ.

## 10. Những nhầm lẫn nên tránh

1. **“DNS record TTL = JVM TTL.”** Hai TTL thuộc hai lớp khác nhau; hạ tầng resolver còn có thể cache riêng.
2. **“`UnknownHostException` chắc chắn là NXDOMAIN.”** Java chỉ báo tra cứu tên thất bại; không quy hết nguyên nhân về một mã DNS.
3. **“TTL = 0 khiến toàn bộ mạng không còn cache.”** Nó chỉ kiểm soát cache liên quan của `InetAddress`; OS, recursive resolver và thư viện khác có thể vẫn cache.
4. **“Đã hết positive TTL thì chắc chắn không còn dùng IP cũ.”** Trên JDK hỗ trợ stale và cấu hình cho phép, IP cũ có thể được dùng khi refresh không thành công.
5. **“Bật stale thì mọi hostname sẽ có fallback.”** Phải có lookup thành công trước; thất bại ngay từ lần đầu không có IP cũ.
6. **“Chỉ cần đổi `System.setProperty` giữa lúc chạy.”** Cache/policy có thể đã khởi tạo; hãy cấu hình từ lúc JVM bắt đầu và kiểm chứng.
7. **“Kết quả Java trả IP cũ nghĩa là connection pool đã được cập nhật.”** Thay đổi phân giải không hủy socket đang mở.
8. **“Ba vòng lookup nhanh chứng minh DNS caching.”** Cần quan sát từng lớp, đặc biệt log resolver, để kết luận đó là cache nào.

## 11. Tự kiểm tra kiến thức

**Câu 1:** Một service vừa được tạo DNS record nhưng JVM vẫn gặp `UnknownHostException`. Thuộc tính nào cần xem trước?  
**Trả lời:** `networkaddress.cache.negative.ttl` và thời điểm failure được cache; sau đó xác minh resolver và các cache bên ngoài JVM.

**Câu 2:** Positive TTL đã hết, lần làm mới thất bại. Khi nào Java có thể trả lại IP cũ?  
**Trả lời:** Trên JDK có cơ chế stale được bật, khi đã có positive result trước đó và dữ liệu cũ vẫn nằm trong giới hạn chính sách stale. Nếu không, lookup có thể thất bại.

**Câu 3:** Đổi positive TTL xuống 1 giây có bảo đảm kết nối mới luôn dùng IP DNS mới nhất không?  
**Trả lời:** Không. Còn cache của OS/resolver, client tự quản DNS, load balancing, cách chọn địa chỉ và kết nối được tái sử dụng.

**Câu 4:** Vì sao không dùng `-Dnetworkaddress.cache.ttl=5` như một JVM flag thông thường?  
**Trả lời:** Vì đây là Java security property. Dùng tệp cấu hình security hoặc đặt rất sớm bằng `Security.setProperty` trước khi chính sách cache được khởi tạo.

## Tài liệu chuẩn để đối chiếu theo JDK

- Java 17, `InetAddress` (positive và negative cache): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html
- Java 21, `InetAddress` (bao gồm stale TTL): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html
- Java 21, Networking Properties (Address Cache): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/doc-files/net-properties.html
- Java 21, Security Properties File (cách cấu hình tệp bổ sung): https://docs.oracle.com/en/java/javase/21/security/security-properties-file.html
