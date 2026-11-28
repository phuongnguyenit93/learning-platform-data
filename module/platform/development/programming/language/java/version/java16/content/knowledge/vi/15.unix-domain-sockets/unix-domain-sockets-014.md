# Socket option theo supportedOptions và giới hạn adapter socket truyền thống

Unix-domain socket trong Java 16 được sử dụng thông qua NIO channel như `SocketChannel` và `ServerSocketChannel`, kết hợp với `StandardProtocolFamily.UNIX` và `UnixDomainSocketAddress`. Khi cần cấu hình socket option, hãy hỏi chính channel đang dùng thông qua `supportedOptions()` rồi mới gọi `setOption()` hoặc `getOption()`.

Đây là điểm quan trọng vì một socket option chuẩn không nhất thiết được hỗ trợ trên mọi loại socket, hệ điều hành hoặc channel provider. Unix-domain socket là giao tiếp cục bộ, không phải TCP connection; các option gắn với TCP không tự nhiên áp dụng cho nó. Ngoài ra, adapter truyền thống `java.net.Socket` và `java.net.ServerSocket` không đại diện được cho Unix-domain socket. Hãy làm việc trực tiếp với NIO channel.

Java 16 bổ sung Unix-domain socket cho NIO; `NetworkChannel.supportedOptions()`, `getOption()` và `setOption()` là các API NIO đã có từ trước. Bài học này tập trung cách áp dụng chúng một cách portable cho channel Unix-domain.

## 1. Bối cảnh Unix-domain socket trong Java

Java 16 bổ sung hỗ trợ Unix-domain socket cho NIO:

- `UnixDomainSocketAddress` biểu diễn địa chỉ socket cục bộ.
- `StandardProtocolFamily.UNIX` chọn họ giao thức Unix-domain.
- `SocketChannel` tạo kết nối phía client.
- `ServerSocketChannel` bind địa chỉ và chấp nhận kết nối.

Ví dụ tạo địa chỉ và mở channel:

```java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(Path.of("/tmp/orders.sock"));

try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    server.bind(address);
    try (var accepted = server.accept()) {
        // Đọc và ghi qua SocketChannel được accept.
    }
}
```

Client kết nối từ một luồng hoặc tiến trình riêng:

```java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(Path.of("/tmp/orders.sock"));

try (SocketChannel client =
         SocketChannel.open(StandardProtocolFamily.UNIX)) {
    client.connect(address);
    // Đọc và ghi qua channel.
}
```

Đường dẫn socket phải phù hợp với hệ điều hành, quyền truy cập filesystem và vòng đời của server.

Dù tên interface là `NetworkChannel`, các API cấu hình option của NIO vẫn được dùng cho những channel này. Tên interface không có nghĩa Unix-domain socket trở thành TCP/IP socket.

## 2. Socket option là gì?

Socket option là một tham số cấu hình hoặc truy vấn thuộc tính của socket. Ví dụ trong Java có các option chuẩn như:

- `SO_RCVBUF`: kích thước bộ đệm nhận.
- `SO_SNDBUF`: kích thước bộ đệm gửi.
- `SO_KEEPALIVE`: cơ chế keep-alive của kết nối dạng TCP.
- `TCP_NODELAY`: điều khiển thuật toán Nagle của TCP.
- `SO_LINGER`: hành vi đóng socket khi còn dữ liệu chưa gửi, theo semantics của loại socket hỗ trợ option đó.
- `SO_REUSEADDR`: quy tắc sử dụng lại địa chỉ trong những trường hợp được hệ điều hành hỗ trợ.

Các hằng số chuẩn nằm trong `StandardSocketOptions`. Chúng là các định danh option dùng chung cho API Java; sự tồn tại của hằng số không đồng nghĩa mọi channel đều hỗ trợ option đó.

Đối với Unix-domain socket, hãy đặc biệt cẩn thận với các option mang ý nghĩa TCP/IP. Chẳng hạn, `TCP_NODELAY` chỉ có ý nghĩa với TCP. Không nên cố đặt option này lên Unix-domain channel chỉ vì nó có trong `StandardSocketOptions`.

## 3. supportedOptions() cho biết channel hiện tại hỗ trợ gì

`NetworkChannel` định nghĩa phương thức:

```java
Set<SocketOption<?>> supportedOptions()
```

Phương thức trả về tập các option được channel hỗ trợ. `SocketChannel` và `ServerSocketChannel` đều có thể sử dụng phương thức này.

Ví dụ liệt kê các option mà một Unix-domain server channel công bố:

```java
import java.net.StandardProtocolFamily;
import java.net.SocketOption;
import java.nio.channels.ServerSocketChannel;
import java.util.Set;

try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    Set<SocketOption<?>> options = server.supportedOptions();

    options.stream()
        .map(SocketOption::name)
        .sorted()
        .forEach(System.out::println);
}
```

Kết quả phụ thuộc JDK, hệ điều hành và channel provider đang chạy. Không nên viết chương trình giả định tập option luôn giống hệt nhau trên mọi máy.

Một số nguyên tắc:

- Gọi `supportedOptions()` trên chính channel sẽ được cấu hình.
- Client channel và server channel có thể công bố các tập option khác nhau.
- Chỉ gọi `getOption` hoặc `setOption` sau khi xác nhận option có trong tập hỗ trợ.
- Không dùng một danh sách option cố định suy ra từ một hệ điều hành để áp dụng cho tất cả môi trường.

## 4. supportedOptions không phải danh sách option của peer

Tập option được trả về mô tả khả năng của channel cục bộ do JDK/provider tạo ra. Nó không phải một giao thức thương lượng với tiến trình ở đầu kia.

Ví dụ, nếu client channel hỗ trợ `SO_RCVBUF`, điều đó cho biết client có thể truy vấn hoặc cấu hình bộ đệm nhận cục bộ. Nó không chứng minh server hỗ trợ cùng option hoặc đang dùng cùng kích thước buffer.

Với Unix-domain socket, hai đầu thường nằm trên cùng máy, nhưng mỗi channel vẫn có trạng thái và cấu hình riêng. Nếu ứng dụng cần một điều kiện ở cả hai phía, mỗi tiến trình phải tự cấu hình và xác thực phía của mình.

Không suy luận các thuộc tính sau từ `supportedOptions()`:

- Peer có hỗ trợ một option cụ thể hay không.
- Quyền truy cập filesystem đối với đường dẫn socket.
- Danh tính hoặc quyền của peer.
- Kích thước buffer thực tế mà hệ điều hành cuối cùng áp dụng.
- Thông lượng hoặc độ trễ của kết nối.

Đây là các vấn đề khác nhau và cần API hoặc cơ chế hệ điều hành phù hợp.

## 5. Kiểm tra trước khi setOption

`NetworkChannel.setOption(option, value)` đặt giá trị cho option trên channel. Cách an toàn là kiểm tra option trước:

```java
import java.io.IOException;
import java.net.SocketOption;
import java.nio.channels.NetworkChannel;

static <T> boolean setIfSupported(
        NetworkChannel channel,
        SocketOption<T> option,
        T value) throws IOException {

    if (!channel.supportedOptions().contains(option)) {
        return false;
    }

    channel.setOption(option, value);
    return true;
}
```

Hàm trả về `true` khi option được công bố là hỗ trợ và lệnh đặt giá trị đã được gọi thành công. Nó trả về `false` nếu channel không hỗ trợ option đó.

Cách này phù hợp khi option là tùy chọn và ứng dụng có phương án mặc định. Nếu option là yêu cầu bắt buộc của ứng dụng, hãy báo lỗi rõ ràng thay vì âm thầm bỏ qua:

```java
import java.io.IOException;
import java.net.SocketOption;
import java.nio.channels.NetworkChannel;

static <T> void requireAndSet(
        NetworkChannel channel,
        SocketOption<T> option,
        T value) throws IOException {

    if (!channel.supportedOptions().contains(option)) {
        throw new UnsupportedOperationException(
            "Socket option is required but unsupported: " + option.name()
        );
    }

    channel.setOption(option, value);
}
```

Không nên bắt `UnsupportedOperationException` rồi bỏ qua mọi trường hợp. Hãy quyết định từ đầu option nào là tùy chọn, option nào là điều kiện bắt buộc để ứng dụng hoạt động đúng.

## 6. Ví dụ cấu hình SO_RCVBUF khi được hỗ trợ

`SO_RCVBUF` là option kích thước bộ đệm nhận. Có thể thử đặt kích thước mong muốn nếu channel công bố hỗ trợ:

```java
import java.io.IOException;
import java.net.StandardSocketOptions;
import java.nio.channels.NetworkChannel;

static void configureReceiveBuffer(NetworkChannel channel)
        throws IOException {

    if (channel.supportedOptions()
            .contains(StandardSocketOptions.SO_RCVBUF)) {

        channel.setOption(
            StandardSocketOptions.SO_RCVBUF,
            64 * 1024
        );

        Integer effectiveSize =
            channel.getOption(StandardSocketOptions.SO_RCVBUF);

        System.out.println("Receive buffer: " + effectiveSize);
    } else {
        System.out.println("SO_RCVBUF is not supported by this channel");
    }
}
```

Giá trị yêu cầu là 64 KiB trong ví dụ. Giá trị truy vấn lại có thể khác vì hệ điều hành hoặc provider có quyền áp dụng giới hạn và quy tắc riêng.

Vì vậy, nếu kích thước buffer là một yêu cầu hiệu năng, hãy đọc lại giá trị sau khi cấu hình và đo workload thực tế. Không giả định `setOption` luôn khiến hệ điều hành áp dụng chính xác con số được truyền vào.

Có thể dùng cùng helper cho `SO_SNDBUF` nếu channel hỗ trợ:

```java
if (channel.supportedOptions()
        .contains(StandardSocketOptions.SO_SNDBUF)) {
    channel.setOption(StandardSocketOptions.SO_SNDBUF, 64 * 1024);
}
```

Không áp dụng ví dụ này như một cam kết rằng mọi Unix-domain socket provider đều phải hỗ trợ hai option buffer.

## 7. Cấu hình option cho SocketChannel và ServerSocketChannel

Nên kiểm tra option trên đúng loại channel cần cấu hình. Ví dụ:

```java
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(Path.of("/tmp/orders.sock"));

try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    if (server.supportedOptions()
            .contains(StandardSocketOptions.SO_RCVBUF)) {
        server.setOption(StandardSocketOptions.SO_RCVBUF, 32 * 1024);
    }

    server.bind(address);
    try (SocketChannel accepted = server.accept()) {
        // Xử lý kết nối đã được chấp nhận.
    }
}
```

Ở phía client, chạy riêng đoạn sau trong tiến trình hoặc luồng khác:

```java
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(Path.of("/tmp/orders.sock"));

try (SocketChannel client =
         SocketChannel.open(StandardProtocolFamily.UNIX)) {

    if (client.supportedOptions()
            .contains(StandardSocketOptions.SO_RCVBUF)) {
        client.setOption(StandardSocketOptions.SO_RCVBUF, 32 * 1024);
    }

    client.connect(address);
    // Giao tiếp qua client channel.
}
```

Hai phía kiểm tra option độc lập. Không lấy tập option của server rồi dùng thay cho client.

Trong ứng dụng thật, server cần bind và accept trong khi client connect tới địa chỉ đang được server lắng nghe. Phần cấu hình option độc lập với logic xử lý dữ liệu sau khi kết nối.

## 8. Không giả định mọi StandardSocketOptions đều áp dụng cho Unix-domain socket

`StandardSocketOptions` chứa các option phục vụ nhiều loại socket. Một số option gắn với TCP/IP, một số có thể có ý nghĩa rộng hơn tùy loại socket và provider.

Ví dụ:

| Option | Ý nghĩa chung | Lưu ý với Unix-domain socket |
|---|---|---|
| `SO_RCVBUF` | Bộ đệm nhận | Chỉ dùng nếu channel công bố hỗ trợ |
| `SO_SNDBUF` | Bộ đệm gửi | Chỉ dùng nếu channel công bố hỗ trợ |
| `SO_KEEPALIVE` | TCP keep-alive | Không mặc định áp dụng cho Unix-domain |
| `TCP_NODELAY` | Tắt Nagle cho TCP | Không có ngữ nghĩa TCP trên Unix-domain |
| `SO_REUSEADDR` | Quy tắc sử dụng lại địa chỉ | Không suy ra semantics của địa chỉ filesystem |
| `SO_LINGER` | Hành vi close với dữ liệu đang gửi | Chỉ dùng theo hỗ trợ và semantics của provider |

Bảng này mô tả mục đích chung, không phải danh sách hỗ trợ bắt buộc. Tập trả về từ `supportedOptions()` mới là cơ sở để quyết định channel cụ thể có chấp nhận option hay không.

Đặc biệt, `SO_REUSEADDR` không thay thế quy tắc quản lý pathname của Unix-domain socket. Đường dẫn socket là tài nguyên filesystem; việc tạo, xóa và quyền truy cập pathname cần được quản lý riêng.

## 9. getOption cũng cần kiểm tra hỗ trợ

`getOption(option)` truy vấn giá trị hiện tại. Nếu option không được hỗ trợ, việc gọi có thể ném `UnsupportedOperationException`. Vì vậy, hãy kiểm tra trước:

```java
import java.io.IOException;
import java.net.StandardSocketOptions;
import java.nio.channels.NetworkChannel;

static void printReceiveBuffer(NetworkChannel channel)
        throws IOException {

    if (channel.supportedOptions()
            .contains(StandardSocketOptions.SO_RCVBUF)) {

        int receiveBuffer =
            channel.getOption(StandardSocketOptions.SO_RCVBUF);

        System.out.println(receiveBuffer);
    } else {
        System.out.println("Receive buffer option unavailable");
    }
}
```

`getOption` trả về kiểu dữ liệu tương ứng với option. `SO_RCVBUF` và `SO_SNDBUF` dùng `Integer`; các option khác có thể dùng `Boolean` hoặc kiểu khác theo định nghĩa của `SocketOption<T>`.

Không chuyển tất cả giá trị option thành chuỗi rồi parse lại để cấu hình. Hãy giữ kiểu generic của option để trình biên dịch kiểm tra kiểu giá trị.

## 10. Phân biệt option không được hỗ trợ với giá trị không hợp lệ

Hai lỗi này biểu thị hai vấn đề khác nhau:

- Option không được channel hỗ trợ: `UnsupportedOperationException`.
- Option được hỗ trợ nhưng giá trị không hợp lệ: thường là `IllegalArgumentException`.

Ngoài ra, thao tác có thể gặp `IOException` nếu hệ điều hành không thực hiện được yêu cầu. Nếu channel đã đóng, các thao tác có thể ném `ClosedChannelException`, một lớp con của `IOException`.

Ví dụ một helper chỉ xử lý trường hợp option không được hỗ trợ:

```java
if (channel.supportedOptions().contains(option)) {
    channel.setOption(option, value);
} else {
    // Áp dụng mặc định hoặc báo lỗi theo chính sách ứng dụng.
}
```

Không nên dùng một khối catch rộng để coi mọi lỗi cấu hình là "option không hỗ trợ". Giá trị ngoài phạm vi, channel đã đóng và lỗi I/O cần được xử lý theo nguyên nhân riêng.

## 11. Giới hạn của adapter Socket truyền thống

NIO channel có các phương thức adapter như `SocketChannel.socket()` và `ServerSocketChannel.socket()` để truy cập API `java.net.Socket` hoặc `java.net.ServerSocket` đối với Internet socket tương ứng.

Unix-domain socket không phải Internet protocol socket. Vì vậy, với channel thuộc họ `StandardProtocolFamily.UNIX`, không thể dùng adapter truyền thống này để lấy một đối tượng `Socket` hoặc `ServerSocket` tương đương. Lời gọi `socket()` sẽ ném `UnsupportedOperationException`.

Ví dụ không phù hợp:

```java
import java.net.StandardProtocolFamily;
import java.nio.channels.SocketChannel;

try (SocketChannel channel =
         SocketChannel.open(StandardProtocolFamily.UNIX)) {

    channel.socket().setKeepAlive(true);
    // UnsupportedOperationException:
    // Unix-domain channel không có Internet Socket adapter.
}
```

Tương tự, không dùng `server.socket()` để lấy `ServerSocket` cho Unix-domain server channel.

Đây là giới hạn về mô hình API: `java.net.Socket` và `java.net.ServerSocket` truyền thống được thiết kế cho Internet socket, trong khi Unix-domain socket sử dụng địa chỉ cục bộ kiểu `UnixDomainSocketAddress`.

## 12. Dùng NIO channel API thay cho adapter

Với Unix-domain socket, thực hiện các thao tác trên channel:

| Nhu cầu | API phù hợp |
|---|---|
| Mở client | `SocketChannel.open(StandardProtocolFamily.UNIX)` |
| Mở server | `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` |
| Kết nối | `SocketChannel.connect(UnixDomainSocketAddress)` |
| Bind server | `ServerSocketChannel.bind(UnixDomainSocketAddress)` |
| Chấp nhận kết nối | `ServerSocketChannel.accept()` |
| Liệt kê option | `NetworkChannel.supportedOptions()` |
| Đọc option | `NetworkChannel.getOption(option)` |
| Đặt option | `NetworkChannel.setOption(option, value)` |
| Đọc dữ liệu | `SocketChannel.read(ByteBuffer)` |
| Ghi dữ liệu | `SocketChannel.write(ByteBuffer)` |

Không gọi adapter `socket()` để sử dụng các phương thức như `setSoTimeout`, `setKeepAlive` hoặc `setTcpNoDelay`. Hãy xác định option nào thực sự có ý nghĩa với loại channel, kiểm tra hỗ trợ và dùng API NIO tương ứng.

Nếu một thư viện chỉ nhận `Socket` hoặc `ServerSocket` mà không hỗ trợ NIO channel hay Unix-domain socket, không thể tự động chuyển Unix-domain channel thành adapter tương thích. Cần chọn tích hợp có hỗ trợ Unix-domain socket hoặc thay đổi ranh giới API của ứng dụng.

## 13. Socket option không thay thế quyền filesystem

Unix-domain socket thường được gắn với một pathname trong filesystem. Khả năng bind hoặc connect có thể phụ thuộc:

- Thư mục chứa socket có tồn tại hay không.
- Quyền tạo file trong thư mục.
- Quyền truy cập pathname của tiến trình client.
- Socket cũ còn sót lại từ lần chạy trước.
- Quyền sở hữu và chính sách bảo mật của hệ điều hành.

`supportedOptions()` không kiểm tra các điều kiện này. Một channel có thể hỗ trợ đầy đủ option nhưng vẫn không bind hoặc connect được vì quyền filesystem hoặc pathname.

Tương tự, `SO_RCVBUF` và `SO_SNDBUF` không quyết định ai được phép kết nối tới socket. Hãy quản lý quyền filesystem và vòng đời socket path như một phần riêng của cấu hình triển khai.

## 14. Viết code có tính portable

Một chương trình portable không giả định tất cả hệ điều hành có cùng tập option. Nên chia option thành hai nhóm:

- **Bắt buộc:** nếu không hỗ trợ thì ứng dụng không thể đáp ứng yêu cầu; fail-fast với thông báo rõ ràng.
- **Tùy chọn:** nếu không hỗ trợ thì dùng mặc định hoặc bỏ qua có chủ đích.

Ví dụ:

```java
import java.io.IOException;
import java.net.StandardSocketOptions;
import java.nio.channels.NetworkChannel;

static void configureChannel(NetworkChannel channel)
        throws IOException {

    if (!channel.supportedOptions()
            .contains(StandardSocketOptions.SO_RCVBUF)) {
        // Đây là option tối ưu tùy chọn, dùng mặc định của hệ điều hành.
        return;
    }

    channel.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);

    int actual = channel.getOption(StandardSocketOptions.SO_RCVBUF);
    System.out.println("Effective receive buffer = " + actual);
}
```

Không viết test yêu cầu tập option phải bằng chính xác một danh sách cứng trên mọi nền tảng. Thay vào đó, kiểm tra rằng ứng dụng xử lý đúng cả hai trường hợp: option có hỗ trợ và option không được hỗ trợ.

Nếu ứng dụng có yêu cầu triển khai cụ thể, hãy kiểm thử trên hệ điều hành và JDK thực tế sẽ chạy production.

## 15. Các lỗi thường gặp

**Gọi setOption mà không kiểm tra supportedOptions.** Option chuẩn có thể không được hỗ trợ trên Unix-domain channel. Hãy kiểm tra trên đúng channel trước khi đặt.

**Cho rằng StandardSocketOptions có nghĩa là mọi socket đều hỗ trợ.** Đây là tập định danh option chuẩn, không phải cam kết hỗ trợ trên mọi transport.

**Dùng TCP_NODELAY cho Unix-domain socket.** Đây là option có ý nghĩa với TCP. Không dùng nó như một cách tối ưu chung cho mọi loại socket.

**Dùng socket().setSoTimeout() trên Unix-domain channel.** Adapter Socket truyền thống không đại diện được cho Unix-domain socket. Hãy dùng NIO channel và cơ chế timeout phù hợp với mô hình I/O đang dùng.

**Dùng tập option của server để cấu hình client.** Mỗi channel có thể công bố khả năng khác nhau. Kiểm tra riêng từng channel.

**Cho rằng option của local channel cho biết peer hỗ trợ gì.** supportedOptions chỉ mô tả channel cục bộ, không phải cơ chế thương lượng với peer.

**Coi setOption thành công là bảo đảm giá trị hiệu lực đúng bằng giá trị yêu cầu.** Hệ điều hành có thể điều chỉnh. Đọc lại bằng getOption khi cần biết giá trị hiện tại.

**Dùng SO_REUSEADDR để xử lý socket pathname còn sót lại.** Option này không thay thế quản lý file socket và quyền filesystem.

**Bắt mọi exception rồi bỏ qua.** Phân biệt option không hỗ trợ, giá trị không hợp lệ, channel đã đóng và lỗi I/O để ứng dụng phản ứng đúng.

**Cố chuyển Unix-domain channel thành java.net.Socket.** Adapter truyền thống chỉ dành cho Internet protocol socket; hãy giữ ở NIO channel API.

## 16. Ghi nhớ

- Unix-domain socket trong Java 16 sử dụng `SocketChannel` và `ServerSocketChannel` với `StandardProtocolFamily.UNIX`.
- Hai channel này cung cấp `supportedOptions()`, `getOption()` và `setOption()` qua API NIO.
- `supportedOptions()` trả về các option mà channel hiện tại hỗ trợ; không giả định danh sách giống nhau trên mọi nền tảng.
- Kiểm tra option trước khi gọi `getOption()` hoặc `setOption()`.
- Phân biệt option tùy chọn và option bắt buộc để quyết định bỏ qua hay fail-fast.
- `StandardSocketOptions` chứa option cho nhiều loại socket; không phải tất cả đều phù hợp với Unix-domain.
- Tập option của channel cục bộ không cho biết cấu hình hoặc khả năng của peer.
- Giá trị set có thể được hệ điều hành điều chỉnh; đọc lại bằng `getOption()` nếu cần.
- `SocketChannel.socket()` và `ServerSocketChannel.socket()` không cung cấp adapter Internet socket cho Unix-domain channel; lời gọi có thể ném `UnsupportedOperationException`.
- Dùng trực tiếp NIO channel cho connect, bind, accept, read, write và cấu hình option.
- Socket option không thay thế quyền filesystem hoặc quản lý pathname của Unix-domain socket.

Khi cấu hình Unix-domain socket, hãy xem `supportedOptions()` là nguồn thông tin cho chính channel đang chạy. Kiểm tra trước khi đặt hoặc đọc option, tách biệt option TCP khỏi option có thể dùng cho Unix-domain, và giữ toàn bộ thao tác ở NIO channel API thay vì dựa vào adapter `Socket` truyền thống.

## Tài liệu tham khảo

- [JEP 380 – Unix-Domain Socket Channels](https://openjdk.org/jeps/380) — hỗ trợ Unix-domain socket được bổ sung trong Java 16.
- [Java SE 16 API – NetworkChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/NetworkChannel.html) — `supportedOptions()`, `getOption()` và `setOption()`.
- [Java SE 16 API – SocketChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html) — client channel và giới hạn của `socket()` adapter.
- [Java SE 16 API – ServerSocketChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ServerSocketChannel.html) — server channel và giới hạn của `socket()` adapter.
- [Java SE 16 API – StandardSocketOptions](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/StandardSocketOptions.html) — các socket option chuẩn và kiểu giá trị.
- [Java SE 16 API – UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/UnixDomainSocketAddress.html) — địa chỉ Unix-domain socket.

