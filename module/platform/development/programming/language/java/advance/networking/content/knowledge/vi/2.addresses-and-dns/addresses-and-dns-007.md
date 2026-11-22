# InetSocketAddress: địa chỉ đã phân giải, chưa phân giải và cổng tự cấp

## 1. InetSocketAddress mô tả điều gì?

Trong lập trình mạng Java, một điểm cuối (endpoint) thường cần **địa chỉ IP hoặc tên máy chủ** và **số cổng (port)**. Lớp `java.net.InetSocketAddress` biểu diễn cặp thông tin đó để truyền vào các thao tác như `Socket.connect(...)`, `ServerSocket.bind(...)` hoặc `DatagramSocket.bind(...)`.

Cần tách ba câu hỏi khác nhau:

1. **Đang chỉ đến máy nào?** Một `InetAddress` đã biết IP, hay chỉ có tên miền (hostname) chưa phân giải?
2. **Đang dùng cổng nào?** Số cổng được khai báo trong `InetSocketAddress` là bao nhiêu?
3. **Socket thật đã được hệ điều hành gắn vào địa chỉ/cổng chưa?** Chỉ thao tác `bind` (hoặc kết nối khiến socket được tự gắn cổng) mới cấp tài nguyên mạng thực.

`InetSocketAddress` là đối tượng **bất biến**: tạo xong không thể sửa hostname, IP hay port của nó. Tạo một đối tượng này **không tự mở kết nối TCP, không lắng nghe và không giữ cổng**. Riêng hàm khởi tạo nhận hostname có thể thực hiện tra cứu tên miền khi tạo đối tượng.

Ví dụ một server thử nghiệm có thể yêu cầu `127.0.0.1:0`. Số `0` là yêu cầu hệ điều hành chọn cổng khi `bind`, chứ chưa phải cổng thật. Sau khi bind thành công, socket có thể đang lắng nghe ở `127.0.0.1:53124` (con số chỉ minh họa); muốn biết số thật phải hỏi **socket đã bind**.

## 2. Bốn cách tạo địa chỉ và ý nghĩa của chúng

| Cách tạo | Việc phân giải địa chỉ | Trạng thái/ứng dụng |
| --- | --- | --- |
| `new InetSocketAddress(port)` | Tạo địa chỉ IP đại diện cho **mọi giao diện cục bộ** (wildcard); không tra cứu DNS | `isUnresolved() == false`; thường dùng cho `bind` server |
| `new InetSocketAddress(inetAddress, port)` | Nhận `InetAddress` đã có sẵn; không cần tra cứu hostname ở bước này | `isUnresolved() == false`; chọn IP cụ thể, ví dụ loopback |
| `new InetSocketAddress(hostname, port)` | **Cố gắng phân giải** hostname ngay khi tạo; nếu không thành công vẫn tạo đối tượng | Có thể resolved hoặc unresolved, tùy kết quả phân giải |
| `InetSocketAddress.createUnresolved(hostname, port)` | **Không phân giải** hostname khi tạo | Luôn unresolved; dùng khi muốn trì hoãn việc phân giải hoặc để proxy xử lý |

Các port được chấp nhận từ **0 đến 65535**; giá trị ngoài khoảng gây `IllegalArgumentException`. Port `0` được thiết kế để hệ thống chọn cổng cho một thao tác **bind cục bộ**. Đối với đích dịch vụ từ xa, ứng dụng thường phải biết cổng thật, chẳng hạn `443`; không được hiểu port `0` là “tự tìm cổng của máy chủ bên kia”.

Ở dạng nhận `InetAddress`, truyền `null` cho tham số địa chỉ cũng có nghĩa là wildcard. Địa chỉ wildcard có thể được biểu diễn dưới dạng IPv4 hoặc IPv6 tùy hệ thống. Nó có nghĩa là **mọi địa chỉ cục bộ thích hợp khi bind**, không phải địa chỉ máy chủ từ xa có thể kết nối tới.

### Những phương thức cần nhớ

| Phương thức | Ý nghĩa |
| --- | --- |
| `isUnresolved()` | `true` khi đối tượng còn hostname mà chưa có `InetAddress` |
| `getAddress()` | Trả `InetAddress`, hoặc `null` nếu unresolved |
| `getHostString()` | Lấy hostname đã giữ hoặc chuỗi biểu diễn IP **mà không kích hoạt tra cứu ngược DNS** |
| `getHostName()` | Lấy hostname; trong một số trường hợp có thể kích hoạt tra cứu ngược DNS |
| `getPort()` | Trả số port ghi trong đối tượng, **không phản ánh cổng được cấp cho socket sau này** |

Không phân tích chuỗi từ `toString()` để tách hostname/port: cách biểu diễn có thể chứa dấu ngoặc vuông IPv6, dấu `/` hoặc phần `<unresolved>`. Hãy dùng các getter tương ứng.

## 3. Resolved và unresolved: đã có IP hay chưa?

**Resolved** nghĩa là `InetSocketAddress` có một `InetAddress`. IP có thể đã được truyền trực tiếp, ví dụ `InetAddress.getLoopbackAddress()`, hoặc đã được xác định qua phân giải hostname. Khi đó:

- `isUnresolved()` là `false`.
- `getAddress()` khác `null`.
- Điều này **không chứng minh** máy đích đang hoạt động, cổng đang mở hay kết nối sẽ thành công.

**Unresolved** nghĩa là vẫn giữ hostname và port nhưng chưa có IP:

- `isUnresolved()` là `true`.
- `getAddress()` là `null`; gọi phương thức của kết quả này mà không kiểm tra sẽ gây `NullPointerException`.
- `getHostString()` vẫn trả hostname để ghi log, chuyển cho lớp khác hoặc proxy.

Có **hai đường dẫn tới unresolved**: phân giải tên thất bại khi dùng constructor nhận `String`, hoặc chủ động không phân giải bằng `createUnresolved`. Vì vậy “unresolved” không đồng nghĩa “hostname chắc chắn sai”. Một SOCKS proxy, chẳng hạn, có thể được giao hostname để phân giải ở phía proxy; khả năng xử lý unresolved phụ thuộc API và cách thiết lập kết nối. Khi dùng kết nối trực tiếp, hãy kiểm tra yêu cầu của API thay vì giả định mọi loại socket đều chấp nhận unresolved.

Một `InetSocketAddress` đã tạo **không tự chuyển trạng thái từ unresolved sang resolved**. Nếu cần phân giải sau, có thể gọi `InetAddress.getByName(hostname)` (cần xử lý `UnknownHostException`), rồi **tạo đối tượng `InetSocketAddress` mới** từ IP và port cũ. `getHostString()` chỉ lấy chuỗi, không thực hiện bước phân giải đó.

Ngược lại, địa chỉ wildcard dùng cho `bind` có một `InetAddress` đặc biệt và **không** bị coi là unresolved. Đây là sự khác biệt giữa “IP biểu thị mọi giao diện cục bộ” với “chỉ biết hostname nhưng chưa có IP”.

### Ví dụ 1: phân biệt ba trạng thái bằng Java 17+

Tạo tệp `AddressStatesDemo.java`:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;

public class AddressStatesDemo {
    public static void main(String[] args) {
        InetSocketAddress resolved =
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 8080);
        InetSocketAddress unresolved =
                InetSocketAddress.createUnresolved("example.com", 443);
        InetSocketAddress wildcard = new InetSocketAddress(0);

        System.out.println("resolved: " + !resolved.isUnresolved());
        System.out.println("unresolved: " + unresolved.isUnresolved());
        System.out.println("unresolved IP null: " + (unresolved.getAddress() == null));
        System.out.println("unresolved host: " + unresolved.getHostString());
        System.out.println("wildcard: " + wildcard.getAddress().isAnyLocalAddress());
        System.out.println("requested port: " + wildcard.getPort());
    }
}
~~~

Chạy:

~~~bash
javac AddressStatesDemo.java
java AddressStatesDemo
~~~

Kết quả xác định, không phụ thuộc DNS hay một máy chủ bên ngoài:

~~~text
resolved: true
unresolved: true
unresolved IP null: true
unresolved host: example.com
wildcard: true
requested port: 0
~~~

Giải thích: `getLoopbackAddress()` cung cấp một IP loopback đã biết; `createUnresolved` cố ý chỉ giữ hostname; `new InetSocketAddress(0)` có IP wildcard và port yêu cầu là `0`. Chưa có lệnh `bind` nên chưa có cổng tự cấp thực tế. Không dùng `new InetSocketAddress("example.com", 443)` trong phép thử trạng thái cố định này vì kết quả phụ thuộc việc DNS có phân giải được tại thời điểm chạy hay không.

## 4. Cổng tự cấp (ephemeral port) diễn ra lúc nào?

Khi bind vào **cổng cục bộ 0**, hệ điều hành chọn một cổng khả dụng theo cơ chế của nó (thường từ dải cổng tạm/ephemeral). Quy trình:

1. Tạo địa chỉ yêu cầu, ví dụ `new InetSocketAddress(InetAddress.getLoopbackAddress(), 0)`. Lúc này `getPort() == 0`.
2. Tạo socket chưa bind, ví dụ `new ServerSocket()`.
3. Gọi `server.bind(requested)`. Nếu thành công, hệ điều hành đã chọn và gắn cổng thật cho socket.
4. Đọc `server.getLocalPort()` hoặc `((InetSocketAddress) server.getLocalSocketAddress()).getPort()` để lấy cổng được cấp.
5. Truyền cổng thật cho client/test khác trong khi server còn hoạt động. Đóng socket giải phóng tài nguyên; không giả định lần chạy sau dùng lại hay có số cổng khác.

**Điểm quan trọng:** đối tượng `requested` vẫn có `getPort() == 0` sau bước 3, vì nó bất biến. Cổng thật thuộc **trạng thái của `ServerSocket` đã bind**, không được điền ngược vào đối tượng yêu cầu.

`new ServerSocket(0)` là cách viết ngắn để tạo server socket rồi bind ngay vào một cổng tự cấp trên địa chỉ wildcard. Tuy nhiên khi chỉ muốn nhận kết nối từ máy đang chạy, nên bind rõ vào `InetAddress.getLoopbackAddress()` thay vì wildcard. Bind wildcard có thể khiến dịch vụ nghe trên nhiều giao diện mạng, tùy hệ thống và chính sách tường lửa.

### Ví dụ 2: lấy cổng thật và kết nối cục bộ

Tạo tệp `DynamicPortDemo.java`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class DynamicPortDemo {
    public static void main(String[] args) throws IOException {
        InetSocketAddress requested =
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0);
        System.out.println("before bind: " + requested.getPort());

        try (ServerSocket server = new ServerSocket()) {
            server.bind(requested);
            InetSocketAddress actual =
                    (InetSocketAddress) server.getLocalSocketAddress();

            System.out.println("selected port valid: " + (server.getLocalPort() > 0));
            System.out.println("same port: " + (server.getLocalPort() == actual.getPort()));

            try (Socket client = new Socket()) {
                client.connect(actual, 3_000);
                try (Socket accepted = server.accept()) {
                    System.out.println("connected: " + client.isConnected());
                }
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac DynamicPortDemo.java
java DynamicPortDemo
~~~

Kết quả khi máy cho phép tạo TCP socket cục bộ:

~~~text
before bind: 0
selected port valid: true
same port: true
connected: true
~~~

Số cổng được hệ điều hành chọn thay đổi theo môi trường nên chương trình **kiểm tra điều kiện**, không in một số cổng cố định. Client dùng chính `actual` lấy từ server đã bind, vì thế không cần đoán cổng. Hai khối `try-with-resources` bảo đảm các socket được đóng khi kết thúc; lỗi `bind` hoặc `connect` có thể gây `IOException`. Tham số `3_000` của `connect` là thời hạn chờ kết nối tính bằng mili giây, không phải port.

Tương tự, socket phía client cũng thường được hệ điều hành tự chọn **cổng cục bộ** khi kết nối nếu ứng dụng chưa bind nó. Hãy phân biệt cổng cục bộ của client với cổng **đích** mà client kết nối tới.

## 5. Chọn cách tạo đúng theo mục đích

| Tình huống | Cách làm phù hợp | Lý do |
| --- | --- | --- |
| Server nghe trên mọi giao diện ở cổng 8080 | `server.bind(new InetSocketAddress(8080))` | Wildcard dùng cho địa chỉ **cục bộ** |
| Server thử nghiệm chỉ nghe nội bộ và muốn cổng tự cấp | `server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))` | Giới hạn ở loopback, lấy cổng qua `getLocalPort()` |
| Client kết nối hostname và chấp nhận phân giải ngay | `new InetSocketAddress("service.example", 443)` | Có thể phân giải hostname tại thời điểm tạo |
| Muốn giữ tên máy chủ để phân giải về sau/qua proxy | `InetSocketAddress.createUnresolved("service.example", 443)` | Không bắt DNS chạy tại thời điểm tạo |
| Đã có IP từ trước | `new InetSocketAddress(ip, 443)` | Không cần tra cứu hostname thêm trong constructor |

Tên `service.example` trong bảng chỉ có tính minh họa, không giả định tồn tại trong DNS. Với mã kết nối thật, xác định host, port, cơ chế phân giải và timeout theo hệ thống đích.

Trong giao tiếp TCP, `ServerSocket.bind` là **gắn điểm nghe cục bộ**, còn `Socket.connect` là **kết nối đến điểm cuối từ xa**. Cùng dùng `InetSocketAddress` nhưng hướng thao tác khác nhau. Ví dụ `0.0.0.0:8080`/wildcard thích hợp khi **bind**; client không nên coi `0.0.0.0` là IP dịch vụ từ xa.

## 6. Những lỗi và nhầm lẫn thường gặp

1. **Nghĩ `new InetSocketAddress(0)` đã giữ một cổng.** Sai: đối tượng chưa bind; `getPort()` vẫn bằng 0. Phải bind thành công rồi hỏi socket.
2. **Nghĩ resolved đồng nghĩa kết nối được.** Sai: biết IP không xác nhận máy chủ chạy, port mở, tuyến mạng hoạt động hay tường lửa cho phép.
3. **Nghĩ unresolved luôn là lỗi.** Có thể chủ động trì hoãn DNS bằng `createUnresolved`; một số đường kết nối qua proxy cần hostname gốc. Ngược lại, đừng đưa unresolved cho API chỉ chấp nhận IP đã phân giải.
4. **Gọi `getAddress().getHostAddress()` mà không kiểm tra.** Với unresolved, `getAddress()` bằng `null`; hãy kiểm tra `isUnresolved()` trước.
5. **Dùng `getHostName()` để log mà không cân nhắc DNS.** Nó có thể tra cứu ngược trong vài trường hợp. `getHostString()` không thực hiện tra cứu ngược.
6. **Dùng port 0 cho địa chỉ đích với hy vọng Java tự tìm dịch vụ.** Cơ chế chọn cổng tự động áp dụng cho **bind cục bộ**, không phải khám phá port của server từ xa.
7. **Bind wildcard khi chỉ muốn chạy test nội bộ.** Hãy chủ động dùng loopback để tránh mở điểm nghe trên các giao diện không cần thiết.
8. **Dựa vào chuỗi `toString()` hoặc so sánh hostname đơn giản.** Dùng getter; `equals()` so sánh cả port và địa chỉ IP đối với resolved, hoặc hostname (không phân biệt hoa/thường) đối với cặp unresolved. Hai trạng thái khác nhau không mặc nhiên tương đương.
9. **Giả định DNS luôn ổn định và duy nhất.** Một hostname có thể có nhiều bản ghi IPv4/IPv6; kết quả phân giải, thứ tự IP và khả năng kết nối có thể thay đổi theo máy, mạng và thời gian.

## 7. Tự kiểm tra

**Câu 1.** `InetSocketAddress.createUnresolved("localhost", 9000)` có `getAddress()` là gì, dù `localhost` thường phân giải được?

Đáp án: `null`. Lệnh `createUnresolved` cố ý bỏ qua phân giải, nên `isUnresolved() == true`.

**Câu 2.** Tạo `InetSocketAddress requested = new InetSocketAddress(0)` rồi bind thành công. `requested.getPort()` có đổi sang cổng được cấp không?

Đáp án: không. Nó vẫn là `0`. Lấy port thật từ `ServerSocket.getLocalPort()` hoặc socket tương ứng.

**Câu 3.** Vì sao `new InetSocketAddress(0)` không bị coi là unresolved?

Đáp án: constructor này đã có một `InetAddress` wildcard đại diện cho địa chỉ cục bộ; unresolved là trạng thái **chưa có IP cho hostname**, không phải trạng thái “chưa bind cổng”.

**Bài tập ngắn:** Sửa `DynamicPortDemo` để in `server.getLocalPort()`, chạy nhiều lần và quan sát kết quả. Giải thích tại sao **không được** viết assertion yêu cầu hai lần chạy phải chọn hai cổng khác nhau. Sau đó thay loopback bằng wildcard và nêu sự khác nhau về phạm vi giao diện mà server có thể lắng nghe.

## Tài liệu API

- [`InetSocketAddress` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetSocketAddress.html)
- [`ServerSocket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html)
- [`Socket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
