# Chia sẻ socket qua volume và ranh giới namespace của container

## 1. Bài toán chia sẻ Unix-domain socket giữa các container

Unix-domain socket cho phép các tiến trình trên cùng host giao tiếp qua một địa chỉ cục bộ. Trong môi trường container, server và client thường chạy ở hai container riêng, mỗi container có filesystem view và namespace riêng.

Ví dụ một ứng dụng có hai service:

- `socket-server` mở Unix-domain socket tại `/run/app/orders.sock`.
- `socket-client` kết nối đến socket đó để gửi request và nhận response.

Nếu hai container có filesystem độc lập, đường dẫn `/run/app/orders.sock` trong container client không tự động trỏ đến socket do server tạo. Cách phổ biến trên Linux là đặt socket pathname trong một thư mục được chia sẻ qua named volume hoặc bind mount để cả hai container nhìn thấy cùng socket file.

Sơ đồ:

~~~text
                    Docker host
        +--------------------------------------+
        |          Shared volume               |
        |          /run/app/                   |
        |          orders.sock                 |
        +------------------+-------------------+
                           |
              +------------+------------+
              |                         |
      +-------v--------+        +-------v--------+
      | socket-server  |        | socket-client  |
      | mount /run/app |        | mount /run/app |
      | bind()         |        | connect()      |
      +----------------+        +----------------+
~~~

Hai tiến trình không cần chia sẻ toàn bộ filesystem hoặc toàn bộ network namespace. Điều kiện cốt lõi với pathname socket là cả hai phải truy cập được cùng socket entry qua filesystem được mount vào từng container, đồng thời quyền truy cập phải cho phép kết nối.

Bài học tập trung vào Unix-domain socket pathname trên Linux container, Java NIO từ Java 16 và các nguyên tắc vận hành vẫn áp dụng trong Java hiện đại.

Mục tiêu:

- Phân biệt mount namespace với network namespace khi dùng Unix-domain socket.
- Chia sẻ socket pathname qua Docker volume.
- Hiểu vì sao nên mount thư mục chứa socket.
- Tạo server và client Java dùng chung socket path.
- Xử lý UID/GID, quyền thư mục và quyền socket.
- Quản lý vòng đời socket khi container khởi động lại.
- Tránh nhầm volume sharing với xác thực hoặc cấp quyền an toàn.

## 2. Pathname socket và abstract socket khác nhau thế nào?

Trên Linux, Unix-domain socket có thể dùng địa chỉ gắn với pathname trong filesystem hoặc địa chỉ thuộc abstract namespace.

| Loại địa chỉ | Được đặt tên bằng | Cơ chế chia sẻ giữa container |
| --- | --- | --- |
| Pathname socket | Đường dẫn như `/run/app/orders.sock` | Chia sẻ filesystem entry bằng volume hoặc bind mount. |
| Abstract socket | Tên trừu tượng, không phải file trong filesystem | Không thể chia sẻ bằng volume; namespace mạng quyết định phạm vi nhìn thấy. |

Java NIO dùng `UnixDomainSocketAddress` với `Path`, vì vậy ví dụ trong bài dùng pathname socket:

~~~java
UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(Path.of("/run/app/orders.sock"));
~~~

Địa chỉ này cần được phân giải trong filesystem view của tiến trình đang gọi. Nếu container client không mount thư mục chứa socket, cùng chuỗi `/run/app/orders.sock` có thể không tồn tại trong container đó.

Abstract socket không có file pathname để mount. Trên Linux, abstract Unix-domain socket được cô lập theo network namespace; bind mount một thư mục không làm abstract name xuất hiện trong container khác. Vì vậy, khi cần chia sẻ socket bằng volume, hãy dùng pathname socket.

## 3. Mount namespace quyết định pathname có nhìn thấy được hay không

Container thường có mount namespace riêng. Namespace này cung cấp một góc nhìn riêng về các mount point và filesystem. Một thư mục có trong container server không tự động xuất hiện trong container client.

Khi cùng một volume được mount vào hai container, cả hai cùng nhìn thấy nội dung của volume đó tại mount point tương ứng.

~~~text
Host volume:      app-runtime

Container server: /run/app  ----+
                                +---- cùng volume
Container client: /run/app  ----+
~~~

Với pathname AF_UNIX trên Linux:

- Socket là filesystem object được tạo tại pathname khi server bind.
- Mount namespace quyết định tiến trình có nhìn thấy pathname đó hay không.
- Bind mount hoặc named volume có thể cung cấp cùng filesystem entry cho nhiều container.
- Network namespace không phải cơ chế làm pathname socket xuất hiện trong filesystem view.

Cần phân biệt thêm:

- Network namespace cô lập tài nguyên mạng như interface, route, port và abstract Unix-domain socket namespace.
- Mount namespace cô lập góc nhìn filesystem, gồm pathname Unix-domain socket.
- IPC namespace chủ yếu cô lập System V IPC và POSIX message queue; không phải cơ chế chia sẻ pathname Unix-domain socket.

Do đó, chỉ bật `--network host` hoặc chia sẻ network namespace không thay thế việc mount thư mục socket. Ngược lại, pathname socket được chia sẻ qua volume có thể dùng giữa các container có network namespace riêng, miễn là filesystem entry và quyền truy cập phù hợp.

## 4. Chia sẻ named volume bằng Docker Compose

Named volume là cách thuận tiện để hai service cùng dùng một thư mục runtime:

~~~yaml
services:
  socket-server:
    image: example/java-socket-server:1.0
    volumes:
      - uds-data:/run/app

  socket-client:
    image: example/java-socket-client:1.0
    volumes:
      - uds-data:/run/app

volumes:
  uds-data:
~~~

Cả hai container mount cùng volume `uds-data` tại `/run/app`. Server bind socket tại `/run/app/orders.sock`; client connect đến cùng pathname trong filesystem view của nó.

Một số lưu ý:

- Named volume được Docker quản lý và tồn tại độc lập với vòng đời của một container.
- Việc tạo hoặc xóa container không đồng nghĩa volume bị xóa.
- `docker compose down -v` có thể xóa named volume được Compose quản lý; không dùng tùy chọn này nếu cần giữ dữ liệu runtime hoặc dữ liệu khác trong volume.
- Cả hai service phải mount đúng cùng volume. Hai volume khác nhau nhưng có cùng mount path không chia sẻ nội dung.
- Có thể mount volume tại hai đường dẫn khác nhau, nhưng dùng cùng mount path trong các container giúp giảm nhầm lẫn.
- `depends_on` chỉ điều khiển thứ tự khởi động theo cấu hình; nó không tự bảo đảm server đã bind socket và sẵn sàng nhận kết nối.

Nếu dùng bind mount từ host, hai service phải tham chiếu cùng một thư mục host:

~~~yaml
services:
  socket-server:
    image: example/java-socket-server:1.0
    volumes:
      - type: bind
        source: /srv/orders/runtime
        target: /run/app

  socket-client:
    image: example/java-socket-client:1.0
    volumes:
      - type: bind
        source: /srv/orders/runtime
        target: /run/app
~~~

Bind mount hữu ích khi host hoặc một tiến trình bên ngoài container cũng cần truy cập socket. Named volume thường dễ quản lý hơn khi socket chỉ phục vụ giao tiếp nội bộ giữa các container.

## 5. Vì sao nên mount thư mục chứa socket?

Nên chia sẻ thư mục cha, chẳng hạn `/run/app`, thay vì bind mount riêng file `/run/app/orders.sock`.

Socket pathname là một filesystem entry. Khi server dừng và tạo lại socket, entry cũ có thể bị xóa rồi một socket object mới được bind tại cùng pathname. Nếu client chỉ mount riêng file socket cũ, mount có thể tiếp tục tham chiếu object cũ thay vì entry mới xuất hiện trong thư mục.

Chia sẻ thư mục cha giúp client tra cứu pathname hiện tại sau khi server tạo lại socket:

~~~text
Khuyến nghị:

shared-volume/
    orders.sock       <- server có thể unlink và bind lại entry này

Không nên chỉ mount file socket riêng:
    orders.sock       <- có thể giữ tham chiếu tới socket object cũ
~~~

Quy tắc vận hành:

1. Tạo hoặc mount thư mục runtime trước khi server khởi động.
2. Server bind socket bên trong thư mục đó.
3. Client kết nối bằng pathname bên trong mount point của nó.
4. Khi server dừng, đóng channel và dọn socket pathname theo vòng đời đã định.
5. Khi server khởi động lại, client tra cứu entry mới trong thư mục được chia sẻ.

Không xóa socket pathname đang được server hoạt động sử dụng. Unlink entry đang hoạt động có thể khiến client mới không còn tìm thấy listener tại đường dẫn đó, dù các kết nối đã được thiết lập có thể vẫn tồn tại.

## 6. Server Java tạo socket trong thư mục volume

Java 16 cung cấp `UnixDomainSocketAddress` và khả năng mở `ServerSocketChannel` với `StandardProtocolFamily.UNIX`.

Ví dụ server dùng `/run/app/orders.sock`:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;

public class OrderSocketServer {
    public static void main(String[] args) throws IOException {
        Path socketDirectory = Path.of("/run/app");
        Path socketPath = socketDirectory.resolve("orders.sock");

        Files.createDirectories(socketDirectory);

        boolean bound = false;

        try (ServerSocketChannel server =
                 ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

            server.bind(UnixDomainSocketAddress.of(socketPath));
            bound = true;

            System.out.println("Listening on " + socketPath);

            try (SocketChannel client = server.accept()) {
                // Thực hiện protocol đọc/ghi với client.
            }
        } finally {
            // Chỉ xóa pathname do lần chạy này bind thành công.
            if (bound) {
                Files.deleteIfExists(socketPath);
            }
        }
    }
}
~~~

Giải thích:

- `Files.createDirectories` bảo đảm thư mục mount point tồn tại.
- `socketPath` là pathname nằm trong shared volume.
- `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` mở server channel cho Unix-domain socket.
- `bind` tạo socket entry tại pathname.
- `accept` chờ client kết nối.
- Khi server channel đóng, phần `finally` xóa pathname do lần chạy này tạo.

Ví dụ này giả định một server instance có quyền sở hữu độc quyền pathname. Nếu `bind` thất bại vì pathname đã tồn tại, `bound` vẫn là `false` nên đoạn `finally` không xóa entry mà server khác có thể đang sử dụng.

Nếu server chết đột ngột, pathname có thể còn lại. Quy trình khởi động cần xử lý stale socket riêng sau khi xác nhận chắc chắn không còn listener cũ. Không dùng `Files.deleteIfExists` một cách mù quáng trên pathname đang hoạt động.

## 7. Client Java kết nối qua cùng volume

Client dùng cùng pathname bên trong container của nó:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

public class OrderSocketClient {
    public static void main(String[] args) throws IOException {
        Path socketPath = Path.of("/run/app/orders.sock");

        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(socketPath);

        try (SocketChannel channel =
                 SocketChannel.open(StandardProtocolFamily.UNIX)) {
            channel.connect(address);

            System.out.println("Connected to " + socketPath);

            // Gửi request và nhận response theo protocol ứng dụng.
        }
    }
}
~~~

Hai chương trình không cần chạy trong cùng container. Điều kiện để kết nối thành công:

- Server đã bind socket.
- Client nhìn thấy cùng socket entry thông qua shared volume.
- Đường dẫn client dùng trỏ đến entry đó.
- UID/GID và quyền truy cập cho phép client kết nối.
- Runtime và hệ điều hành hỗ trợ Unix-domain socket.

Nếu client khởi động trước khi server bind, `connect` có thể thất bại vì pathname chưa tồn tại hoặc chưa có listener. Client nên retry có giới hạn và backoff, hoặc chờ readiness signal do ứng dụng cung cấp. Không nên lặp connect liên tục không có delay.

## 8. Quyền thư mục và quyền socket trên Linux

Chia sẻ volume chỉ làm filesystem entry có thể nhìn thấy. Nó không tự cấp quyền kết nối.

Trên Linux, cần xem xét ít nhất:

- Quyền `x` trên từng thư mục cha để tiến trình đi qua pathname.
- Server cần quyền ghi và tìm kiếm trên thư mục để tạo socket entry.
- Client cần quyền truy cập thư mục và quyền phù hợp trên socket file.
- UID, GID và supplementary groups của hai tiến trình.
- `umask` khi server tạo socket.
- Các chính sách bảo mật bổ sung như SELinux hoặc AppArmor.

Linux có quy tắc riêng về quyền pathname socket: kết nối tới stream socket pathname yêu cầu quyền ghi trên socket object; việc tạo socket cũng cần quyền ghi và tìm kiếm trên thư mục chứa nó. Chi tiết permission của Unix-domain socket có khác biệt giữa các hệ điều hành, nên cần kiểm tra trên nền tảng triển khai.

Ví dụ thiết kế quyền theo group:

~~~text
/run/app
owner: socket-user
group: app-socket
directory mode: 2770

orders.sock
owner: socket-user
group: app-socket
socket mode: cho phép group app-socket kết nối
~~~

Bit setgid trên thư mục giúp entry mới kế thừa group của thư mục trong môi trường POSIX hỗ trợ hành vi đó. `umask` của server ảnh hưởng mode ban đầu của socket. Cấu hình thực tế cần xác nhận mode sau khi bind.

Tránh dùng `chmod 777` cho thư mục socket. Mọi tiến trình có quyền ghi vào thư mục có thể xóa hoặc thay thế socket entry, gây gián đoạn hoặc giả mạo endpoint.

## 9. UID/GID, user namespace và quyền volume

Container có thể chạy bằng UID/GID khác nhau. Khi dùng user namespace hoặc user-namespace remapping, UID/GID bên trong container có thể được ánh xạ sang ID khác trên host.

Vì vậy, hai container cùng hiển thị user `app` không nhất thiết có cùng numeric UID/GID trên filesystem volume. Tên user chỉ là nhãn trong `/etc/passwd`; kernel kiểm tra credential số và group membership.

Cần kiểm tra:

1. UID/GID thực của tiến trình server trong container.
2. UID/GID thực của tiến trình client.
3. Owner/group hiển thị trên shared volume.
4. Mapping của user namespace nếu runtime bật remapping.
5. Supplementary group mà tiến trình client được cấp.
6. Quyền thư mục và socket sau khi server bind.

Một cấu hình Compose có thể khai báo user và group bổ sung:

~~~yaml
services:
  socket-server:
    image: example/java-socket-server:1.0
    user: "10001:20000"
    volumes:
      - uds-data:/run/app

  socket-client:
    image: example/java-socket-client:1.0
    user: "10002:20000"
    group_add:
      - "20000"
    volumes:
      - uds-data:/run/app

volumes:
  uds-data:
~~~

Đây là ví dụ minh họa. Volume phải được khởi tạo với owner/group phù hợp; chỉ đặt `user` trong Compose không tự sửa quyền của volume hiện có. Với user namespace remapping, phải đối chiếu ID bên trong container với ID được ánh xạ trên host.

## 10. SELinux, AppArmor và chính sách mount

Ngay cả khi Unix permission cho phép, chính sách bảo mật của host có thể chặn truy cập socket.

Với SELinux:

- Bind mount từ host có thể cần label phù hợp cho container.
- Docker hỗ trợ các tùy chọn relabel như `:z` và `:Z` trong những môi trường SELinux được hỗ trợ.
- `:z` dùng cho nội dung được chia sẻ bởi nhiều container.
- `:Z` áp dụng label riêng cho một container; không dùng tùy tiện cho cùng một thư mục cần chia sẻ giữa nhiều container vì label có thể không phù hợp với container còn lại.

Với AppArmor hoặc các policy runtime khác, kiểm tra log audit và profile nếu kết nối bị từ chối dù pathname và mode có vẻ đúng.

Không tắt toàn bộ cơ chế bảo vệ host để khắc phục lỗi socket. Hãy điều chỉnh label hoặc policy ở phạm vi nhỏ nhất cần thiết.

Một mount read-only không đồng nghĩa với quyền kết nối được bảo đảm trên mọi runtime và filesystem. Server cần mount có thể ghi để tạo socket; phía client cần quyền truy cập socket theo quy tắc hệ điều hành và chính sách container. Kiểm thử cấu hình mount thực tế thay vì suy luận chỉ từ cờ read-only.

## 11. Vòng đời socket và xử lý stale pathname

Socket pathname có vòng đời riêng với process và container:

- Server bind tạo filesystem entry.
- Client kết nối qua entry đó.
- Đóng `ServerSocketChannel` giải phóng listener.
- Trên Linux, pathname có thể vẫn còn sau khi channel đóng nếu ứng dụng không unlink.
- Nếu server chết bất thường, entry cũ có thể còn trong shared volume.
- Server mới có thể không bind được khi pathname cũ vẫn tồn tại.

Một quy trình vận hành nên có các bước:

1. Dùng một instance server làm chủ pathname trong mỗi shared directory.
2. Khi dừng bình thường, đóng channel rồi xóa pathname do server sở hữu.
3. Khi khởi động, nếu pathname đã tồn tại, xác minh server cũ không còn hoạt động trước khi dọn.
4. Không xóa socket path chỉ vì `connect` của client thất bại một lần.
5. Không cho nhiều server instance cùng bind một pathname nếu giao thức và thiết kế không hỗ trợ cơ chế chia sẻ listener tương ứng.
6. Dùng volume riêng cho từng ứng dụng hoặc từng instance để tránh xung đột tên.

Không coi việc file socket tồn tại là bằng chứng server còn sống. Cũng không coi việc file socket không tồn tại là bằng chứng server không sắp khởi động. Readiness cần được xác định bằng kết nối thực tế hoặc health check phù hợp.

## 12. Readiness, retry và khởi động theo thứ tự

Container server có thể đã chạy nhưng chưa tạo socket. Container client có thể được khởi động ngay sau server mà vẫn gặp lỗi kết nối.

`depends_on` trong Compose có thể sắp xếp thứ tự khởi động, nhưng không tự xác nhận ứng dụng server đã bind và nhận kết nối. Nên chọn một trong các cách:

- Client retry `connect` với backoff và deadline.
- Server cung cấp health check kiểm tra listener thực sự sẵn sàng.
- Một tiến trình điều phối chỉ khởi động client sau khi kiểm tra kết nối thành công.
- Ứng dụng dùng một readiness protocol riêng nếu cần xác nhận phiên bản hoặc khả năng phục vụ.

Retry cần có giới hạn, delay tăng dần và xử lý shutdown. Không retry vô hạn khi lỗi là permission denied hoặc cấu hình path sai; các lỗi đó cần được báo rõ để người vận hành sửa cấu hình.

## 13. Namespace nào cần chia sẻ?

Bảng này áp dụng cho Linux:

| Namespace/cơ chế | Ảnh hưởng đến pathname AF_UNIX | Ảnh hưởng đến abstract AF_UNIX |
| --- | --- | --- |
| Mount namespace | Quyết định filesystem pathname có nhìn thấy được hay không. | Không cung cấp cơ chế chia sẻ abstract name. |
| Network namespace | Không phải cơ chế chính để chia sẻ pathname socket. | Cô lập abstract socket namespace. |
| IPC namespace | Không cô lập pathname AF_UNIX. | Không phải cơ chế quản lý abstract socket. |
| User namespace | Ảnh hưởng UID/GID và credential, có thể làm thay đổi quyền truy cập. | Credential vẫn liên quan đến kiểm soát truy cập; tên abstract không được chia sẻ bằng volume. |

Với pathname socket, chia sẻ volume là cơ chế cần thiết để cung cấp filesystem entry. Không cần chia sẻ network namespace chỉ vì muốn client kết nối pathname socket. Nếu dùng abstract socket, volume không giúp; các tiến trình cần ở network namespace phù hợp để nhìn thấy cùng abstract namespace.

Không nhầm `--ipc=host` với việc chia sẻ pathname socket. Trên Linux, AF_UNIX pathname chịu ảnh hưởng của mount namespace; abstract socket chịu ảnh hưởng của network namespace.

## 14. Bảo mật khi chia sẻ socket giữa container

Một Unix-domain socket thường là cổng truy cập vào chức năng của server. Bất kỳ tiến trình nào có thể kết nối và được server chấp nhận đều có thể gọi giao thức mà server công bố.

Các nguyên tắc:

- Chỉ mount volume vào những container thực sự cần kết nối.
- Dùng group riêng và quyền thư mục/socket tối thiểu.
- Không chia sẻ thư mục runtime với container không tin cậy.
- Xác thực và phân quyền request ở tầng ứng dụng khi chức năng yêu cầu.
- Giới hạn kích thước message, timeout và số lượng kết nối.
- Ghi log lỗi kết nối và request theo cách không làm lộ dữ liệu nhạy cảm.
- Tránh đặt dữ liệu không liên quan vào cùng volume.
- Không mount Docker daemon socket vào container ứng dụng thông thường.

Đặc biệt, `/var/run/docker.sock` thường cho phép client điều khiển Docker daemon. Container có quyền truy cập socket này có thể tạo container đặc quyền hoặc truy cập tài nguyên host tùy cấu hình daemon. Chia sẻ Docker socket tương đương trao một quyền quản trị rất lớn; không xem đây là ví dụ volume chia sẻ vô hại.

Volume sharing không phải cơ chế xác thực client. Nó chỉ làm pathname có thể nhìn thấy và cho phép filesystem permission được áp dụng. Server vẫn cần kiểm tra request và quyền của caller theo mô hình bảo mật của ứng dụng.

## 15. Kiểm tra và chẩn đoán khi client không kết nối được

Khi client không kết nối được, kiểm tra theo thứ tự:

1. Server đã khởi động và `bind` thành công chưa?
2. Server và client có mount cùng named volume hoặc cùng host directory không?
3. Pathname trong client có trỏ đến đúng mount point không?
4. Socket entry có tồn tại trong cả hai filesystem view không?
5. Quyền execute của các thư mục cha có cho phép traversal không?
6. UID/GID và group của hai tiến trình có phù hợp không?
7. SELinux/AppArmor có từ chối thao tác không?
8. Socket path có stale hoặc đang thuộc một server instance khác không?
9. Ứng dụng client có kết nối quá sớm trước readiness không?
10. Hai phía có dùng cùng loại địa chỉ pathname, không nhầm abstract namespace không?

Trên Linux, các lệnh kiểm tra hữu ích gồm:

~~~bash
# Xem socket pathname và quyền của nó.
ls -l /srv/orders/runtime
stat /srv/orders/runtime/orders.sock

# Xem mount và filesystem view trong từng container.
findmnt /run/app
mount | grep /run/app

# Xem process nào đang lắng nghe socket (nếu công cụ có sẵn).
ss -xl
~~~

Thực hiện lệnh trong đúng host hoặc container cần kiểm tra. Một pathname tồn tại trên host không chứng minh client container nhìn thấy cùng entry; hãy kiểm tra từ bên trong từng container.

Nếu cần xác nhận mount có trỏ đến cùng volume, đối chiếu mount configuration của runtime và quan sát file socket trong hai container. Tránh xóa socket hoặc restart đồng thời nhiều service trước khi thu thập thông tin, vì hành động đó có thể làm mất dấu nguyên nhân ban đầu.

## 16. Lỗi thường gặp và cách khắc phục

1. **Chỉ tạo socket trong container server:** client có filesystem view riêng nên không thấy path; mount chung thư mục chứa socket.
2. **Mount hai volume khác nhau tại cùng path:** cùng tên mount point không có nghĩa cùng dữ liệu; kiểm tra source volume.
3. **Mount riêng file socket:** server unlink/rebind có thể tạo entry mới mà client vẫn nhìn object cũ; mount thư mục cha.
4. **Chia sẻ network namespace nhưng không mount thư mục:** pathname socket vẫn không xuất hiện trong filesystem view của client.
5. **Dùng abstract socket rồi mong volume chia sẻ:** abstract name không phải file; trên Linux nó thuộc network namespace.
6. **Nhầm IPC namespace với AF_UNIX pathname:** `--ipc=host` không làm pathname socket được mount vào container.
7. **UID/GID không khớp:** đối chiếu numeric IDs, group và user namespace mapping.
8. **Thư mục thiếu quyền traversal hoặc tạo file:** kiểm tra quyền `x`, `w` và mode socket trên Linux.
9. **SELinux chặn mount:** cấu hình label chia sẻ phù hợp; không tắt toàn bộ SELinux.
10. **Server restart để lại stale socket:** chỉ dọn pathname sau khi xác nhận listener cũ đã dừng.
11. **Client chạy trước server readiness:** retry có backoff hoặc dùng health check thực sự.
12. **Dùng Docker daemon socket như socket ứng dụng thông thường:** nhận thức rõ quyền quản trị host mà socket đó có thể trao.

## 17. Bài tập thực hành

1. Tạo hai service Compose cùng mount một named volume tại `/run/app`.
2. Viết server Java 16 bind `UnixDomainSocketAddress` tại `/run/app/demo.sock`.
3. Viết client trong container riêng connect đến cùng pathname.
4. Thay named volume bằng bind mount từ host và so sánh filesystem view.
5. Thử mount volume chỉ vào server; quan sát lỗi khi client không nhìn thấy pathname.
6. Tạo một directory riêng cho socket và cấu hình UID/GID dùng chung qua group.
7. Restart server bình thường rồi kiểm tra pathname cũ được dọn và entry mới được tạo.
8. Mô phỏng server dừng bất thường; thiết kế quy trình xác minh và dọn stale socket an toàn.
9. So sánh pathname socket và abstract socket trên Linux; giải thích vì sao volume chỉ chia sẻ loại pathname.
10. Dùng hai network namespace riêng nhưng cùng mount thư mục pathname socket; kiểm tra client có thể kết nối khi quyền phù hợp.
11. Thử thay đổi quyền thư mục và socket; ghi lại lỗi permission.
12. Giải thích vì sao chia sẻ `/var/run/docker.sock` có rủi ro lớn hơn nhiều so với socket của ứng dụng giới hạn chức năng.

## Ghi nhớ

Để chia sẻ Unix-domain pathname socket giữa các container trên Linux, hãy đặt socket trong một thư mục được mount từ cùng named volume hoặc bind mount vào các container cần giao tiếp. Pathname socket thuộc filesystem view nên mount namespace quyết định nó có nhìn thấy được hay không; abstract socket thuộc network namespace và không thể chia sẻ bằng volume. Mount thư mục cha để client thấy socket entry mới khi server restart. Kiểm tra UID/GID, user namespace mapping, quyền thư mục/socket và chính sách SELinux/AppArmor. Quản lý stale pathname sau khi xác nhận server cũ đã dừng, dùng readiness/retry có giới hạn và chỉ cấp volume cho container cần quyền kết nối. Java NIO hỗ trợ pathname Unix-domain socket từ Java 16 qua `UnixDomainSocketAddress`, `ServerSocketChannel` và `SocketChannel`; đây là API ổn định còn áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [JEP 380 – Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [Java API – UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [Java API – ServerSocketChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Java API – SocketChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Linux man-pages – unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html)
- [Linux man-pages – mount_namespaces(7)](https://man7.org/linux/man-pages/man7/mount_namespaces.7.html)
- [Linux man-pages – network_namespaces(7)](https://man7.org/linux/man-pages/man7/network_namespaces.7.html)
- [systemd.exec – AF_UNIX namespace behavior](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
