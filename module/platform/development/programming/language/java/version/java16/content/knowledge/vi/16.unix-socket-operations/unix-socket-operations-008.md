# Kiểm tra khác biệt hỗ trợ và socket option giữa Windows và Linux

Java 16 đưa Unix-domain socket (AF_UNIX) vào các API NIO chuẩn thông qua JEP 380. Tính năng này có mặt trên Linux, macOS và Windows hiện đại. Tuy nhiên, khả năng sử dụng thực tế còn phụ thuộc vào build của hệ điều hành, bản JDK và các socket option mà channel cụ thể hỗ trợ.

Khi triển khai cùng một ứng dụng trên Windows và Linux, cần kiểm tra ba lớp: hệ điều hành có AF_UNIX hay không; bản JDK có triển khai tính năng đó trên hệ điều hành này hay không; và channel đang dùng hỗ trợ những option nào. Bài học này so sánh các điểm khác biệt quan trọng và hướng dẫn kiểm tra capability ngay trên runtime triển khai.

## 1. Phạm vi hỗ trợ trên Windows và Linux

| Môi trường | Hỗ trợ AF_UNIX | Điểm cần chú ý |
| --- | --- | --- |
| Linux hiện đại | Có | Hỗ trợ pathname socket và quyền filesystem của Linux |
| macOS | Có | Có Unix-domain socket; option mở rộng có thể khác Linux |
| Windows 10 build 18362 trở lên | Có theo ghi chú JDK 16 | Build 18362 tương ứng Windows 10 version 1903 |
| Windows Server 2019 với JDK 16 GA | Bị tắt trong bản JDK 16 ban đầu | Release Notes ghi nhận lỗi implementation trên nền tảng này |
| Windows Server 2019 với JDK 17 trở lên | Vấn đề JDK 16 nêu trên được ghi nhận là đã xử lý trong JDK 17 | Vẫn cần kiểm tra bản phân phối JDK và môi trường thực tế |

JDK 16 Release Notes nêu hỗ trợ trên Linux, macOS và Windows có build number từ 18362 trở lên. Tài liệu cũng cảnh báo một số bản Windows mới hơn có thể gặp vấn đề khiến công cụ native như Cygwin khó truy cập hoặc xóa socket file. Lỗi trên Windows Server 2019 khiến tính năng bị vô hiệu hóa trong bản JDK 16 ban đầu; ghi chú phát hành cho biết vấn đề được xử lý trong JDK 17 và một bản cập nhật JDK 16 tương lai.

Nếu ứng dụng vẫn phải chạy trên JDK 16, hãy xác nhận đúng build Windows và đúng bản cập nhật JDK. Với runtime mới hơn, vẫn nên chạy smoke test trên môi trường đích trước khi bật Unix-domain socket trong production.

## 2. Java API giống nhau, nhưng pathname khác nhau

Java dùng **UnixDomainSocketAddress** để biểu diễn endpoint. Địa chỉ được tạo từ **Path** hoặc chuỗi pathname, nhưng cách viết path phụ thuộc filesystem mặc định.

Ví dụ Linux:

~~~java
Path socketPath = Path.of("/run/order-service/orders.sock");
UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(socketPath);
~~~

Ví dụ Windows:

~~~java
Path socketPath = Path.of("C:/ProgramData/OrderService/orders.sock");
UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(socketPath);
~~~

Không nên dùng một chuỗi pathname cố định cho mọi hệ điều hành. Hãy lấy thư mục từ cấu hình và ghép các thành phần bằng **Path.resolve()**:

~~~java
Path socketDirectory = Path.of(configuredSocketDirectory);
Path socketPath = socketDirectory.resolve("orders.sock")
    .toAbsolutePath()
    .normalize();

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(socketPath);
~~~

Cách này để filesystem mặc định xử lý separator. Cấu hình thư mục socket vẫn cần khác nhau theo môi trường, ví dụ **/run/...** trên Linux và một thư mục dành riêng trong **ProgramData** trên Windows.

Path tương đối có thể được diễn giải khác nếu service chạy với working directory khác nhau. Với ứng dụng production, nên cấu hình thư mục rõ ràng và chuyển thành path tuyệt đối trước khi bind.

## 3. Quyền truy cập socket file

Unix-domain socket gắn với pathname trong filesystem. Khi server bind thành công, hệ điều hành tạo socket file. Quyền truy cập thư mục và socket file có thể giới hạn process nào được kết nối.

### Linux

Linux áp dụng quyền filesystem cho pathname socket. Thư mục cha phải cho phép process đi qua và tạo socket file; quyền trên socket file cũng ảnh hưởng tới khả năng client kết nối. Cách quản lý thường dùng là tạo thư mục riêng cho service với owner/group và mode hạn chế.

Ví dụ chuẩn bị thư mục trên Linux:

~~~bash
install -d -m 0750 -o ordersvc -g ordergrp /run/order-service
~~~

User và group phải được tạo theo chính sách của hệ thống. Không nên mở quyền rộng chỉ để tránh lỗi kết nối.

### Windows

Windows sử dụng ACL của filesystem thay cho POSIX mode bits. JEP 380 nêu rõ filesystem access control chuẩn của Windows có thể được áp dụng để giới hạn truy cập Unix-domain socket theo user hoặc group.

Không dùng **Files.setPosixFilePermissions()** như giải pháp chung cho cả hai hệ điều hành. POSIX attribute view có thể không được hỗ trợ trên Windows. Với Windows, hãy cấu hình ACL cho thư mục chứa socket bằng công cụ quản trị hoặc API phù hợp.

Quyền filesystem giúp giới hạn ai có thể tiếp cận endpoint, nhưng bản thân Unix-domain socket không tự cung cấp xác thực ứng dụng hoặc mã hóa payload. Nếu cần xác minh danh tính peer, hãy dùng cơ chế nền tảng hỗ trợ và vẫn kiểm tra quyền nghiệp vụ ở tầng ứng dụng.

## 4. Linux abstract namespace và Java pathname API

Linux hỗ trợ abstract namespace cho AF_UNIX. Địa chỉ thuộc namespace này không phải socket file thông thường trong filesystem.

API Java chuẩn biểu diễn Unix-domain address bằng **Path** thông qua **UnixDomainSocketAddress**. Vì vậy, code Java đa nền tảng nên dùng pathname socket. Không thiết kế ứng dụng phụ thuộc vào abstract namespace của Linux nếu cần chạy cùng code trên Windows.

## 5. Giới hạn độ dài pathname

Linux và Windows đều có giới hạn riêng cho địa chỉ AF_UNIX. Tài liệu Java mô tả giới hạn thường xấp xỉ 100 byte và phụ thuộc nền tảng; giới hạn được kiểm tra khi channel bind.

Không nên dùng số ký tự làm đại diện chính xác cho số byte, nhất là khi path chứa ký tự ngoài ASCII. Hãy chọn đường dẫn ngắn, tránh nhiều cấp thư mục và kiểm thử bind trên OS thật.

Việc tạo **UnixDomainSocketAddress** thành công không chứng minh pathname có thể bind được. Một số lỗi chỉ xuất hiện ở bước **bind()**.

## 6. Thư mục tạm khi bind với địa chỉ null

Server có thể gọi **bind(null)** để yêu cầu runtime tự chọn pathname socket duy nhất. Java chọn thư mục tạm theo cấu hình hệ thống; thứ tự tra cứu khác nhau giữa Windows và Linux/macOS.

| Thứ tự | Linux và macOS | Windows |
| --- | --- | --- |
| 1 | System property **jdk.net.unixdomain.tmpdir** | System property **jdk.net.unixdomain.tmpdir** |
| 2 | **$JAVA_HOME/conf/net.properties** | **%JAVA_HOME%/conf/net.properties** |
| 3 | System property **java.io.tmpdir** | Environment variable **TEMP** |
| 4 | — | System property **java.io.tmpdir** |

Tên socket được tự sinh nhưng vẫn phải nằm trong giới hạn độ dài pathname. Nếu thư mục tạm mặc định quá dài, có thể cấu hình **jdk.net.unixdomain.tmpdir** tới một thư mục ngắn hơn và có quyền phù hợp.

Đừng mặc định **java.io.tmpdir** là nguồn duy nhất trên Windows. Nếu dùng **bind(null)**, hãy kiểm tra địa chỉ local thực tế bằng **getLocalAddress()** và xác minh quyền truy cập thư mục được chọn.

## 7. Socket option được xác định theo loại channel

Sự khác biệt quan trọng không đơn giản là “Windows có option A, Linux có option B”. Java API định nghĩa tập option chuẩn cho từng loại channel; implementation có thể cung cấp thêm option riêng. Các option TCP không tự động áp dụng cho Unix-domain socket.

### ServerSocketChannel

Trong Java 16, **ServerSocketChannel** dùng Unix-domain socket hỗ trợ option chuẩn:

| Option | Ý nghĩa |
| --- | --- |
| **SO_RCVBUF** | Kích thước receive buffer của socket |

Tài liệu Java SE 26 tiếp tục liệt kê **SO_RCVBUF** là option chuẩn cho Unix-domain ServerSocketChannel. Không nên giả định **SO_REUSEADDR** của TCP server cũng áp dụng cho Unix-domain server.

### SocketChannel

Trong Java 16, **SocketChannel** dùng Unix-domain socket hỗ trợ:

| Option | Ý nghĩa |
| --- | --- |
| **SO_SNDBUF** | Kích thước send buffer |
| **SO_RCVBUF** | Kích thước receive buffer |

Tài liệu Java SE 17 và Java SE 26 còn liệt kê **SO_LINGER** cho Unix-domain SocketChannel; option này chỉ có tác dụng theo mô tả API khi channel ở blocking mode. Khi code cần chạy trên JDK 16, hãy dựa trên danh sách option của JDK 16. Khi triển khai trên JDK mới hơn, kiểm tra lại danh sách của runtime đó.

### Những option TCP không nên giả định có trên UDS

| Option | Lý do |
| --- | --- |
| **TCP_NODELAY** | Điều khiển thuật toán Nagle của TCP; Unix-domain socket không chạy trên TCP |
| **SO_KEEPALIVE** | Không nằm trong danh sách chuẩn của Unix-domain SocketChannel |
| **SO_REUSEADDR** | Có trong danh sách Internet ServerSocketChannel, không nằm trong danh sách chuẩn của Unix-domain ServerSocketChannel |

Option ngoài danh sách chuẩn có thể được implementation hỗ trợ, nhưng không được coi là portable. Hãy truy vấn **supportedOptions()** trên channel thật trước khi gọi **setOption()**.

## 8. Kiểm tra supportedOptions() thay vì hard-code theo OS

Hãy hỏi chính channel đang chạy:

~~~java
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.SocketChannel;

try (SocketChannel channel =
         SocketChannel.open(StandardProtocolFamily.UNIX)) {

    var supported = channel.supportedOptions();

    if (supported.contains(StandardSocketOptions.SO_SNDBUF)) {
        channel.setOption(StandardSocketOptions.SO_SNDBUF, 64 * 1024);
    }

    if (supported.contains(StandardSocketOptions.SO_RCVBUF)) {
        channel.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);
    }
}
~~~

Đối với server, hãy mở **ServerSocketChannel** bằng **StandardProtocolFamily.UNIX** và truy vấn **supportedOptions()** trên server channel đó. Không dùng danh sách option của SocketChannel để suy ra danh sách của ServerSocketChannel.

Giá trị buffer hệ điều hành thực sự áp dụng có thể khác giá trị yêu cầu do giới hạn kernel hoặc implementation. Nếu đọc lại bằng **getOption()**, hãy xem đó là giá trị runtime trả về, không phải cam kết mọi hệ điều hành dùng cùng kích thước buffer.

## 9. SO_PEERCRED là option mở rộng, không portable như option chuẩn

JDK 16 bổ sung **ExtendedSocketOptions.SO_PEERCRED** trong module **jdk.net**. Option này trả về **UnixDomainPrincipal**, biểu diễn user và group credentials của peer tại thời điểm kết nối hoặc accept.

Đây là option mở rộng và phụ thuộc nền tảng:

- Trên Unix-like systems, implementation có thể cung cấp thông tin peer credentials.
- Không giả định Windows cung cấp cùng cơ chế hoặc dữ liệu user/group kiểu Unix.
- Option chỉ đọc; không thể dùng **setOption()** để thay đổi credentials.
- Chỉ đọc trên channel đã kết nối hoặc channel đã accept; đọc trên channel chưa kết nối có thể ném SocketException.
- Kiểm tra **supportedOptions()** trước khi gọi **getOption()**.

Ví dụ kiểm tra capability trên accepted channel:

~~~java
import java.net.SocketOption;
import java.nio.channels.SocketChannel;
import jdk.net.ExtendedSocketOptions;
import jdk.net.UnixDomainPrincipal;

SocketOption<UnixDomainPrincipal> peerCred =
    ExtendedSocketOptions.SO_PEERCRED;

if (acceptedChannel.supportedOptions().contains(peerCred)) {
    UnixDomainPrincipal peer = acceptedChannel.getOption(peerCred);
    System.out.println(peer.user().getName());
    System.out.println(peer.group().getName());
}
~~~

Trong dự án dùng module descriptor, cần khai báo phụ thuộc vào module **jdk.net**. Không nên để logic xác thực bắt buộc phụ thuộc vào SO_PEERCRED nếu ứng dụng cần chạy trên Windows. Hãy thiết kế cơ chế xác thực ứng dụng có thể hoạt động trên mọi nền tảng mục tiêu.

## 10. Kiểm tra khả năng hỗ trợ trên runtime đích

Việc biên dịch thành công chỉ xác nhận API có trong compile-time JDK. Nó không chứng minh hệ điều hành và runtime triển khai có thể mở, bind và kết nối Unix-domain socket.

Có thể kiểm tra khả năng mở protocol family:

~~~java
import java.net.StandardProtocolFamily;
import java.nio.channels.ServerSocketChannel;

try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    System.out.println("UNIX family is available");
    System.out.println(server.supportedOptions());
}
~~~

Nếu runtime không hỗ trợ protocol family, thao tác mở có thể ném **UnsupportedOperationException**. Nếu gặp **IOException**, cần xem nguyên nhân hệ điều hành hoặc provider trả về.

Để xác minh end-to-end, hãy chạy smoke test trên chính máy triển khai:

1. Tạo pathname ngắn trong thư mục đã cấu hình.
2. Mở ServerSocketChannel với family UNIX và bind.
3. Mở SocketChannel UNIX từ client và connect.
4. Gửi payload nhỏ, đọc lại ở phía server.
5. Đóng channel và dọn socket file do test tạo.
6. Chạy lại test dưới đúng user/service account của production.

Test phải chạy bằng cùng JDK distribution, OS build, user identity và filesystem mount như service thật. Một test chạy trong terminal với quyền administrator/root không chứng minh service account có cùng quyền.

## 11. Khác biệt khi chạy trong container và WSL

Unix-domain socket có thể dùng để giao tiếp giữa hai container nếu cả hai cùng nhìn thấy pathname thông qua volume được chia sẻ. Chỉ có cùng tên path trong hai container là chưa đủ; chúng phải ánh xạ tới cùng socket file và có quyền truy cập phù hợp.

Trên Linux, cần xem xét mount namespace, user namespace, owner/group và mode của thư mục/socket. Nếu container chạy với UID/GID khác nhau, quyền truy cập có thể khác lúc thử trên host.

Trên Windows, cần kiểm tra volume, ACL và runtime Windows thực tế. Với WSL, phân biệt JVM chạy trong môi trường Linux với JVM chạy native trên Windows. Hai tiến trình có thể dùng filesystem namespace và cơ chế quyền khác nhau; không giả định pathname giống nhau có nghĩa chúng tự động nhìn thấy cùng endpoint.

Nếu cần IPC xuyên môi trường Windows-native và WSL, hãy xác minh khả năng tương thích của đúng bản Windows, WSL và JDK bằng integration test. Khi không có filesystem endpoint chung được hỗ trợ, chọn transport phù hợp khác.

## 12. Quy trình chọn option và cấu hình đa nền tảng

1. Xác định OS build, kiến trúc, bản JDK và nhà phân phối JDK.
2. Mở channel UNIX trong startup probe để xác nhận protocol family được hỗ trợ.
3. Chọn pathname ngắn, tuyệt đối và lấy từ cấu hình riêng theo OS.
4. Chuẩn bị thư mục socket với quyền Linux hoặc ACL Windows phù hợp.
5. Truy vấn **supportedOptions()** trên đúng loại channel.
6. Chỉ cấu hình option có trong tập được hỗ trợ.
7. Chỉ dùng **SO_PEERCRED** nếu runtime báo hỗ trợ và ứng dụng có fallback xác thực phù hợp.
8. Thực hiện bind/connect/read/write smoke test dưới service account.
9. Ghi log OS version, JDK version, pathname và capability cần thiết; tránh log thông tin nhạy cảm của peer.
10. Kiểm thử lại khi nâng cấp JDK hoặc đổi Windows build/Linux distribution.

Không nên tạo một bảng cấu hình cứng chỉ dựa trên tên OS rồi giả định mọi máy Windows hoặc mọi bản Linux đều giống nhau. **supportedOptions()** và smoke test cho biết capability thực tế của runtime cụ thể.

## 13. Bảng tóm tắt Windows và Linux

| Chủ đề | Linux | Windows |
| --- | --- | --- |
| AF_UNIX | Hỗ trợ lâu đời trên Linux hiện đại | Hỗ trợ trên Windows hiện đại; JDK 16 có ngưỡng build và ngoại lệ cụ thể |
| Path | Thường là **/run/...** hoặc thư mục cấu hình | Thường là **C:/ProgramData/...** hoặc thư mục cấu hình |
| Quyền filesystem | POSIX owner/group/mode và ACL tùy hệ thống | Windows ACL |
| Abstract namespace | Kernel có hỗ trợ, nhưng không phải địa chỉ pathname portable của Java API | Không có semantics Linux abstract namespace tương đương |
| Peer credentials | Có thể truy vấn qua option mở rộng nếu JDK/provider hỗ trợ | Không giả định có SO_PEERCRED kiểu Unix |
| Socket options chuẩn | Theo loại channel trong Java API; có thể có option mở rộng của provider | Cùng hợp đồng Java theo loại channel; capability thực tế cần kiểm tra |
| Độ dài path | Giới hạn phụ thuộc kernel/platform | Giới hạn phụ thuộc Windows/JDK implementation |
| Temporary directory khi bind(null) | Ưu tiên jdk.net.unixdomain.tmpdir rồi java.io.tmpdir | Có thêm TEMP trước java.io.tmpdir |
| Công cụ vận hành | chmod, chown, ACL và công cụ Linux | ACL, PowerShell và công cụ Windows |

## 14. Kết luận

Java 16 đưa Unix-domain socket vào NIO API trên Linux, macOS và Windows hiện đại. Tuy nhiên, lịch sử hỗ trợ Windows của JDK 16 có ngoại lệ đáng chú ý: Windows Server 2019 bị tắt tính năng trong bản JDK 16 ban đầu; vấn đề được ghi chú là đã xử lý trong JDK 17. Khi triển khai, hãy xác nhận cả OS build và JDK build thay vì chỉ kiểm tra code compile.

Bộ socket option chuẩn được xác định theo loại channel. ServerSocketChannel UDS hỗ trợ SO_RCVBUF; SocketChannel UDS của JDK 16 hỗ trợ SO_SNDBUF và SO_RCVBUF, trong khi tài liệu JDK 17+ còn liệt kê SO_LINGER. SO_PEERCRED là option mở rộng, phụ thuộc nền tảng và không nên dùng làm cơ chế xác thực portable cho Windows.

Hãy dùng pathname ngắn, cấu hình quyền theo POSIX trên Linux hoặc ACL trên Windows, kiểm tra **supportedOptions()** và chạy smoke test bằng đúng runtime cùng service account. Những bước này giúp giữ một codebase Java chung mà vẫn tôn trọng các khác biệt thật của hệ điều hành.

## Tài liệu tham khảo

- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [Inside Java: JEP 380 — Unix domain socket channels](https://inside.java/2021/02/03/jep380-unix-domain-sockets-channels/)
- [JDK 16 Release Notes — Incomplete Support for Unix Domain Sockets in Windows 2019 Server](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [SocketChannel — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ServerSocketChannel — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [SocketChannel — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [SocketChannel — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ExtendedSocketOptions — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html)
- [Networking System Properties — Java SE 16](https://docs.oracle.com/en/java/javase/16/core/networking-properties.html)

