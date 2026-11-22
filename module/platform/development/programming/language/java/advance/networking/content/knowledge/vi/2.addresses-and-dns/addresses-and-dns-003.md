# getByName, getAllByName và một tên máy có nhiều địa chỉ

## Mục tiêu

Sau bài này, bạn có thể:
- Phân biệt việc lấy **một** địa chỉ với việc lấy **danh sách** địa chỉ từ cùng một tên máy bằng `InetAddress`.
- Giải thích vì sao một hostname có thể dẫn đến nhiều IPv4/IPv6 và vì sao kết quả phân giải có thể thay đổi.
- Viết chương trình Java 17+ kiểm tra kết quả phân giải, xử lý lỗi, và tránh giả định sai về thứ tự hay khả năng kết nối.

## 1. Từ tên máy đến địa chỉ IP

Tên máy (hostname) như `api.example.com` là tên dùng ở tầng ứng dụng. Trước khi thực hiện kết nối TCP/UDP thông thường tới một tên, hệ thống cần ánh xạ tên ấy thành một hoặc nhiều địa chỉ IP. Với DNS, bản ghi **A** biểu diễn địa chỉ IPv4; bản ghi **AAAA** biểu diễn địa chỉ IPv6. Ngoài DNS, bộ phân giải tên của hệ thống còn có thể chịu ảnh hưởng của tệp hosts, cấu hình hệ điều hành, bộ nhớ đệm và chính sách mạng. Bởi vậy, kết quả quan sát từ Java không nhất thiết giống hệt một lần truy vấn DNS thô.

Một hostname có thể liên kết với nhiều IP vì:
- **Nhiều máy phục vụ cùng tên:** phân phối lưu lượng, tăng sẵn sàng hoặc đặt máy chủ ở nhiều vùng.
- **Một máy/nền tảng có nhiều giao diện hoặc địa chỉ:** nhiều IP không nhất thiết đồng nghĩa nhiều máy vật lý.
- **Dual stack:** cùng tên có bản ghi A và AAAA để hỗ trợ IPv4 lẫn IPv6.
- **DNS theo vị trí, chính sách hoặc thời điểm:** các máy khách khác nhau, hoặc cùng máy ở thời điểm khác, có thể nhận tập địa chỉ khác nhau.

Ví dụ **giả định** (các IP tài liệu `192.0.2.0/24` và `2001:db8::/32` không đại diện dịch vụ thật):

~~~text
service.example
  ├─ A     → 192.0.2.10
  ├─ A     → 192.0.2.11
  └─ AAAA  → 2001:db8::10
~~~

Từ dữ liệu giả định đó, một lần phân giải có thể cho một IPv4, hoặc một tập IPv4/IPv6, tùy bộ phân giải và môi trường. **Tên máy không có quan hệ một-một bắt buộc với IP.**

## 2. Hai phương thức của `java.net.InetAddress`

| API | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `InetAddress.getByName(String host)` | `InetAddress` | Lấy **một địa chỉ** cho hostname hoặc IP literal. |
| `InetAddress.getAllByName(String host)` | `InetAddress[]` | Lấy **mảng địa chỉ** mà bộ phân giải cấu hình cho hệ thống trả về cho tên đó. |
| `address.getHostAddress()` | `String` | Lấy biểu diễn IP dạng văn bản từ `InetAddress` đã có. |
| `address.getAddress()` | `byte[]` | Lấy byte của IP (4 byte với IPv4, 16 byte với IPv6). |

Cả `getByName` và `getAllByName` đều là API phân giải đồng bộ: lời gọi có thể chờ bộ phân giải, và có thể ném `UnknownHostException` khi không tìm được địa chỉ. Chúng **không tạo socket, không mở kết nối, không thử cổng, không kiểm tra máy chủ còn sống**.

**`getByName(host)`:** thích hợp khi phần mềm chỉ cần một đối tượng địa chỉ. Với hostname nhiều IP, API chọn ra một địa chỉ theo kết quả/chính sách bộ phân giải; không có hợp đồng rằng đó là IP nhanh nhất, khỏe nhất, gần nhất hoặc luôn là IPv4. Cũng không nên lấy IP đó rồi suy ra rằng hostname chỉ có một địa chỉ.

**`getAllByName(host)`:** thích hợp khi cần quan sát hoặc xử lý tập ứng viên. Kết quả là mảng gồm một hoặc nhiều `InetAddress` nếu phân giải thành công; mảng không nhất thiết chứa mọi bản ghi công bố trên DNS toàn cầu vì dữ liệu có thể bị ảnh hưởng bởi resolver, lựa chọn họ địa chỉ, cấu hình và cache. Không được coi thứ tự phần tử là ưu tiên cố định hay thuật toán cân bằng tải.

**Tương quan giữa hai lời gọi:** khi được phục vụ từ cùng một tập kết quả nhất quán, địa chỉ do `getByName` chọn thường nằm trong tập địa chỉ mà `getAllByName` trả về. Tuy nhiên, chúng là **hai lần gọi riêng**: dữ liệu, cấu hình hoặc bộ đệm có thể thay đổi. Đừng viết kiểm thử giả định hai lần gọi độc lập phải tạo ra cùng tập và thứ tự mãi mãi.

Đối số có thể là tên như `example.com` hoặc IP literal như `127.0.0.1` / `2001:db8::1`. Với IP literal hợp lệ, Java diễn giải địa chỉ trực tiếp, không cần truy vấn DNS để đổi tên thành IP. Trường hợp `null` hoặc chuỗi rỗng có ngữ nghĩa loopback theo API; trong ứng dụng nên kiểm tra đầu vào và từ chối hostname rỗng khi đó không phải chủ đích.

## 3. Chương trình chạy được: so sánh hai kết quả

Lưu thành **`AddressLookup.java`** (Java 17 trở lên):

~~~java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public final class AddressLookup {
    public static void main(String[] args) {
        String host = args.length > 0 ? args[0] : "example.com";

        try {
            InetAddress first = InetAddress.getByName(host);
            InetAddress[] all = InetAddress.getAllByName(host);

            System.out.println("Host: " + host);
            System.out.println("getByName: " + first.getHostAddress());
            System.out.println("getAllByName: " + all.length + " address(es)");

            for (int i = 0; i < all.length; i++) {
                InetAddress ip = all[i];
                String family = ip instanceof Inet4Address ? "IPv4" : "IPv6";
                System.out.printf("%d. %s (%s)%n",
                        i + 1, ip.getHostAddress(), family);
            }
        } catch (UnknownHostException e) {
            System.err.println("Cannot resolve host: " + host);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AddressLookup.java
java AddressLookup 127.0.0.1
~~~

**Stdout chính xác** cho đầu vào IP literal `127.0.0.1`:

~~~text
Host: 127.0.0.1
getByName: 127.0.0.1
getAllByName: 1 address(es)
1. 127.0.0.1 (IPv4)
~~~

Ví dụ này dùng literal để đầu ra không phụ thuộc DNS. Nó chứng minh kiểu trả về và cách duyệt mảng, **không** chứng minh hostname thực có nhiều IP. Để quan sát bộ phân giải thật, chạy:

~~~bash
java AddressLookup example.com
java AddressLookup localhost
~~~

Ở các lệnh này, **không có stdout cố định**: số lượng, thứ tự và họ địa chỉ có thể khác theo môi trường. `localhost` thường được cấu hình nội bộ và có thể tương ứng IPv4 `127.0.0.1`, IPv6 `::1` hoặc cả hai. Nếu chỉ có một địa chỉ, đó là kết quả hợp lệ; không được tự thêm IP giả để đủ hai dòng.

**Giải thích code:** `first` là một địa chỉ từ lời gọi thứ nhất; `all` là mảng địa chỉ từ lời gọi thứ hai. `getHostAddress()` xuất địa chỉ IP để quan sát; `instanceof Inet4Address` nhận diện IPv4, các địa chỉ còn lại trong trường hợp này là IPv6. `UnknownHostException` được bắt riêng để hiển thị lỗi phân giải rõ ràng. Phần xử lý kết nối mạng, timeout và retry vẫn là trách nhiệm khác.

## 4. Khi một hostname trả về nhiều IP, điều gì cần hiểu?

Giả sử một lần phân giải thực tế cho `service.example` (chỉ là tình huống minh họa) trả về:

~~~text
192.0.2.10
192.0.2.11
2001:db8::10
~~~

- `getByName("service.example")` chỉ cung cấp **một** `InetAddress`, chẳng hạn `192.0.2.10`. Địa chỉ ví dụ này **không phải cam kết** Java luôn lấy phần tử đầu hay luôn chọn IPv4.
- `getAllByName("service.example")` có thể cung cấp **mảng** gồm các ứng viên trên. Ứng dụng có thể ghi log, phân loại IPv4/IPv6 hoặc thử kết nối theo chính sách riêng.
- Dù địa chỉ xuất hiện trong mảng, máy/cổng đích vẫn có thể từ chối kết nối, timeout, không định tuyến được hoặc lỗi TLS. **Phân giải tên thành công khác với kết nối thành công.**
- Nhiều địa chỉ cùng hostname không tự bảo đảm cân bằng tải. Resolver có thể thay đổi thứ tự, ứng dụng có thể chọn một địa chỉ, còn DNS không giám sát toàn bộ trạng thái dịch vụ.

Một sơ đồ luồng điển hình:

~~~text
hostname
  → resolver của Java/hệ thống (có thể dùng cache, hosts, DNS...)
  → InetAddress[] (các địa chỉ được trả về)
  → ứng dụng/HTTP client chọn và thử địa chỉ theo chính sách
  → socket connect(IP, port) → thành công hoặc lỗi
~~~

Nên tách ba câu hỏi: **tên phân giải ra gì?** (`getAllByName`), **địa chỉ nào được chọn?** (quy tắc resolver/client), và **địa chỉ được chọn có kết nối được hay không?** (socket, route, port, TLS, ứng dụng). Nhầm ba lớp này là nguyên nhân của nhiều lỗi khó tái hiện.

## 5. Ứng dụng: duyệt ứng viên khi muốn có đường dự phòng

Nếu bạn tự xây client TCP mức thấp, việc lấy nhiều địa chỉ chỉ là **bước đầu**. Phải đặt timeout, xử lý thất bại từng ứng viên và đóng tài nguyên đúng lúc. Đoạn mã sau là **một phương thức minh họa để đặt trong class Java có import `java.io.IOException` và `java.net.*`**; không phải chương trình `main` độc lập:

~~~java
static Socket connectAny(String host, int port, int timeoutMillis)
        throws IOException {
    IOException lastFailure = null;

    for (InetAddress address : InetAddress.getAllByName(host)) {
        Socket socket = new Socket();
        try {
            socket.connect(new InetSocketAddress(address, port), timeoutMillis);
            return socket; // Người gọi phải đóng Socket khi dùng xong.
        } catch (IOException ex) {
            lastFailure = ex;
            try {
                socket.close();
            } catch (IOException closeFailure) {
                ex.addSuppressed(closeFailure);
            }
        }
    }

    throw new IOException("No reachable address for " + host, lastFailure);
}
~~~

Đây là ví dụ **thử lần lượt**, nên nếu từng địa chỉ timeout, thời gian tổng có thể lớn; cần xác thực `port` và `timeoutMillis` trước khi dùng, và người gọi phải đóng socket trả về (thường bằng `try-with-resources`). Trong ứng dụng HTTP/TLS thực tế, nên ưu tiên client chuẩn có chính sách kết nối, ưu tiên IPv4/IPv6, retry và kiểm tra hostname/TLS phù hợp. **Không tự đổi hostname thành IP cố định rồi bỏ qua xác minh chứng chỉ**; địa chỉ dùng để kết nối không thay thế danh tính máy chủ TLS.

Nếu chỉ cần gọi REST API, thường hãy truyền **URL hostname** cho HTTP client và để thư viện xử lý kết nối. Đừng tự xây cơ chế luân phiên địa chỉ bằng `getAllByName` khi chưa có yêu cầu cụ thể.

## 6. Thứ tự, IPv4/IPv6 và bộ nhớ đệm

**Thứ tự không cố định.** Tập/trật tự ứng viên chịu ảnh hưởng của DNS, cache, bộ phân giải hệ thống, hỗ trợ IPv6 và thuộc tính mạng của JVM. Java không cam kết rằng mảng luôn sắp theo địa chỉ tăng dần, IPv4 trước IPv6 hay luôn giữ một IP ở vị trí 0. Vì vậy:
- Không viết logic nghiệp vụ gắn “server chính” với `all[0]`.
- Không viết unit test đòi kết quả DNS thật có đúng N IP theo một thứ tự cứng.
- Nếu phải bảo đảm thứ tự ứng viên, hãy nêu rõ chính sách của ứng dụng sau khi phân giải; nếu phải kiểm tra tính sẵn sàng, hãy kiểm tra ở bước kết nối.

**Cache tên.** `InetAddress` có cache cho cả phân giải thành công và thất bại. TTL của cache Java có thể được điều chỉnh qua security properties như `networkaddress.cache.ttl` (thành công) và `networkaddress.cache.negative.ttl` (thất bại); một số JDK còn hỗ trợ `networkaddress.cache.stale.ttl`. TTL mặc định của bản ghi thành công phụ thuộc triển khai/cấu hình, nên đừng khẳng định mọi JVM luôn lấy DNS lại ở mỗi lần gọi hoặc luôn lưu vĩnh viễn. Đây là **security properties**, không nên giả định đặt `-Dnetworkaddress.cache.ttl=...` là cách cấu hình chuẩn.

Khi đổi DNS nhưng Java vẫn quan sát địa chỉ cũ, hãy xem xét cache JVM, cache hệ điều hành/resolver, DNS bên ngoài và thời điểm TTL; đừng quy mọi sự khác biệt cho lỗi `getAllByName`.

**IPv4 và IPv6.** Một hostname có thể có cả A và AAAA, nhưng JVM/máy chạy không nhất thiết hỗ trợ hay chọn cả hai. Đừng cắt chuỗi IP bằng dấu `:` để phán đoán IPv6: IPv6 có dạng văn bản khác IPv4 và còn có thể có scope ID. Dùng `instanceof Inet4Address` hoặc `instanceof Inet6Address` khi thực sự phải phân loại; nếu chỉ log thì `getHostAddress()` là đủ.

## 7. Lỗi phổ biến và cách sửa

| Hiểu nhầm hoặc lỗi | Cách hiểu/cách làm đúng |
|---|---|
| “`getByName` trả một IP nên hostname chỉ có một IP.” | Nó chỉ trả **một** phần tử; dùng `getAllByName` nếu cần tập địa chỉ quan sát được. |
| “`getAllByName` luôn trả toàn bộ bản ghi A/AAAA ở DNS authoritative.” | API trả tập mà **resolver cấu hình** cung cấp, có thể chịu cache/chính sách/IPv6. Đây không phải API truy vấn bản ghi DNS thô. |
| “Phần tử đầu là server chính/nhanh nhất.” | Thứ tự không phải thước đo health, latency, weight hay ưu tiên ứng dụng. |
| “Tên phân giải được thì cổng 443 chắc mở.” | Phân giải không thử kết nối; lỗi kết nối phải xử lý ở socket/HTTP client. |
| “`UnknownHostException` chứng tỏ domain chưa được đăng ký.” | Có thể do DNS, mạng, hosts/resolver hoặc chính sách; thông báo chỉ thể hiện lần phân giải thất bại. |
| “Mỗi lần gọi sẽ thấy DNS mới nhất.” | Có nhiều lớp cache và TTL; kết quả có thể lặp lại dù DNS bên ngoài đã đổi. |
| “`getHostName()` hay `getCanonicalHostName()` là cách lấy thêm tất cả IP.” | Đây là các thao tác tên/tra cứu ngược hoặc canonical name (best effort), **không thay thế** `getAllByName`. |
| “Trả về IPv6 tức máy chắc chắn kết nối IPv6 được.” | Có địa chỉ IPv6 không bảo đảm đường mạng, route hoặc dịch vụ IPv6 hoạt động. |

Lưu ý thêm: `InetAddress` biểu diễn **địa chỉ IP**, không mang số cổng. `InetSocketAddress` mới kết hợp địa chỉ (hoặc hostname) với cổng. Đồng thời, kết quả DNS không nên được dùng làm bằng chứng xác thực danh tính của máy chủ; với HTTPS/TLS, việc kiểm tra hostname/chứng chỉ vẫn cần diễn ra.

## 8. Tự kiểm tra và bài tập nhỏ

1. Chạy `java AddressLookup 127.0.0.1` rồi giải thích vì sao kết quả xác định được mà không cần truy vấn DNS.
2. Chạy `java AddressLookup localhost` và `java AddressLookup example.com` trên hai môi trường. Ghi số lượng, thứ tự và họ địa chỉ **đúng như quan sát**, không giả định chúng phải giống nhau.
3. Nếu một hostname trả 2 IPv4 và 1 IPv6, `getByName` cho biết điều gì? `getAllByName` cho biết thêm điều gì? Có thể suy ra cả ba cổng TCP đang mở không?
4. Đặt tình huống DNS đã chuyển từ IP A sang IP B nhưng JVM vẫn thấy A. Nêu các lớp cache cần kiểm tra trước khi kết luận ứng dụng lỗi.
5. Tự sửa chương trình để đếm số IPv4 và IPv6 trong `all`. Khi viết kiểm thử tự động, dùng IP literal/fixture cho phần logic ổn định và tách kiểm thử tích hợp phân giải DNS thật.

**Đáp án cốt lõi:** (1) literal được diễn giải trực tiếp; (3) `getByName` trả một địa chỉ, `getAllByName` trả mảng ứng viên mà resolver nhìn thấy, không kiểm tra cổng; (4) cache JVM, hệ thống/resolver và hạ tầng DNS. Các câu (2), (5) chủ yếu đánh giá cách quan sát thực tế và xử lý mảng, không có một tập IP chuẩn cố định.

## 9. Ghi nhớ

- `getByName(host)` → **một `InetAddress`**; `getAllByName(host)` → **một mảng `InetAddress[]`**.
- Một hostname có thể ánh xạ nhiều IPv4/IPv6; thứ tự và số lượng từ resolver thay đổi theo môi trường.
- **DNS lookup ≠ kết nối thành công**; cần client/socket, timeout, xử lý lỗi và TLS đúng cách.
- Cache và cấu hình hệ thống/JVM có thể làm kết quả khác kỳ vọng; tránh phụ thuộc tập IP “cứng” trong test và nghiệp vụ.

### Tài liệu đối chiếu

- [Oracle Java SE 21 — `InetAddress`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html)
- [Oracle Java SE 21 — Networking Properties (Address Cache)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/doc-files/net-properties.html)
