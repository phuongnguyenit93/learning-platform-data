# Nhận biết EOF, đóng kết nối và xử lý peer ngắt giữa chừng

Với Unix-domain stream socket trong Java, ứng dụng cần đọc cho đến khi nhận được EOF, đóng channel đúng lúc và phân biệt một kết nối kết thúc bình thường với một thông điệp bị cắt giữa chừng. API `SocketChannel` và `ServerSocketChannel` dùng `StandardProtocolFamily.UNIX` cung cấp cách giao tiếp hai chiều giữa các tiến trình trên cùng máy, không cần địa chỉ IP hay TCP port.

Điểm quan trọng là Unix-domain stream socket truyền một luồng byte liên tục. Một lần `read()` không tương ứng với một thông điệp hoàn chỉnh; dữ liệu có thể đến thành nhiều phần. Nếu peer đóng kết nối khi ứng dụng mới nhận được một phần header hoặc payload, `read()` cuối cùng trả về `-1`, nhưng ứng dụng phải nhận ra frame hiện tại đã bị cắt và xử lý như lỗi giao thức.

Bài học thuộc chương **Unix-domain socket** của module **JAVA_VERSION_JAVA16**. Unix-domain socket channels được đưa vào Java chính thức từ Java 16 và vẫn dùng được trong Java hiện đại. Nội dung tập trung vào stream channel, EOF, half-close, vòng lặp đọc/ghi và cleanup kết nối; không dùng API thử nghiệm hoặc kỹ thuật đã lỗi thời.

## 1. EOF có nghĩa gì trong stream socket?

Khi đọc từ một `SocketChannel`:

| Giá trị trả về | Ý nghĩa |
| --- | --- |
| Số dương | Đã đọc được số byte tương ứng vào `ByteBuffer` |
| `0` | Hiện chưa đọc được byte nào; thường gặp với channel non-blocking, hoặc buffer không còn chỗ |
| `-1` | Đã tới end-of-stream ở chiều nhận; peer đã kết thúc chiều gửi hoặc đóng socket sau khi dữ liệu còn lại được đọc hết |

EOF không phải một byte đặc biệt trong dữ liệu. Đây là tín hiệu từ channel cho biết không còn byte nào nữa ở chiều nhận. Nếu peer đã gửi dữ liệu rồi đóng output, bên nhận vẫn có thể đọc hết các byte đã gửi trước đó; chỉ sau khi dữ liệu đó được tiêu thụ, `read()` mới trả về `-1`.

EOF cũng không nhất thiết có nghĩa peer đã đóng hoàn toàn cả hai chiều. Peer có thể gọi `shutdownOutput()` để báo rằng nó không gửi thêm dữ liệu nhưng vẫn tiếp tục đọc phản hồi. Vì vậy, hãy hiểu `-1` là kết thúc luồng dữ liệu đi vào channel hiện tại, không phải một phép kiểm tra tổng quát xem tiến trình peer còn sống hay không.

## 2. Nhận biết EOF trong vòng lặp đọc

Với channel ở blocking mode, một vòng lặp đọc cơ bản có thể viết như sau:

```java
ByteBuffer buffer = ByteBuffer.allocate(4096);

try (SocketChannel peer = server.accept()) {
    while (true) {
        buffer.clear();
        int count = peer.read(buffer);

        if (count == -1) {
            System.out.println("Peer đã gửi EOF");
            break;
        }

        if (count == 0) {
            continue;
        }

        buffer.flip();
        while (buffer.hasRemaining()) {
            byte value = buffer.get();
            // Chuyển byte vào bộ phân tích giao thức.
        }
    }
}
```

Trong ví dụ này:

- `server.accept()` trả về channel đại diện cho một kết nối đã được chấp nhận.
- `peer.read(buffer)` đọc byte từ peer vào buffer.
- `count == -1` là dấu hiệu kết thúc luồng nhận.
- `count > 0` cho biết có dữ liệu cần xử lý.
- `try-with-resources` đóng channel khi rời khỏi khối, kể cả khi xảy ra exception.

Ví dụ dùng blocking mode. Với channel non-blocking, `read()` có thể trả về `0` khi chưa có dữ liệu; ứng dụng không được coi `0` là EOF và không nên lặp bận liên tục. Hãy đăng ký `OP_READ` với `Selector` rồi tiếp tục khi channel sẵn sàng.

## 3. EOF sạch và thông điệp bị cắt giữa chừng

Một giao thức ứng dụng cần xác định ranh giới thông điệp. Unix-domain stream socket không bảo toàn ranh giới giữa các lần gửi. Ví dụ, ứng dụng gửi một frame gồm:

```text
+----------------------+---------------------------+
| Header: 4 byte length| Payload: length bytes     |
+----------------------+---------------------------+
```

Giả sử header cho biết payload dài 100 byte. Nếu peer chỉ gửi 40 byte rồi đóng kết nối, bên nhận sẽ đọc được header, đọc 40 byte payload, sau đó nhận EOF. Đây không phải một frame hoàn chỉnh.

Hãy phân biệt:

- **EOF giữa hai frame:** peer đã gửi xong các frame trước đó và đóng chiều gửi. Đây có thể là kết thúc giao thức bình thường.
- **EOF giữa header:** header chưa đủ 4 byte nên không thể biết độ dài frame. Đây là frame bị cắt.
- **EOF giữa payload:** header đã khai báo độ dài nhưng payload nhận được chưa đủ. Đây là frame bị cắt.

Nếu coi mọi EOF là kết thúc bình thường, ứng dụng có thể âm thầm chấp nhận dữ liệu thiếu. Với giao thức có độ dài frame, chỉ chấp nhận EOF sạch khi chưa đọc byte nào của frame kế tiếp.

## 4. Đọc đủ một frame bằng ByteBuffer

Hàm sau đọc đủ số byte mà buffer yêu cầu. Hàm chỉ dùng cho channel ở blocking mode:

```java
static boolean readFully(
        SocketChannel channel,
        ByteBuffer destination,
        boolean allowCleanEof) throws IOException {

    if (!channel.isBlocking()) {
        throw new IllegalStateException(
                "readFully requires a blocking channel");
    }

    int startPosition = destination.position();

    while (destination.hasRemaining()) {
        int count = channel.read(destination);

        if (count == -1) {
            boolean noBytesRead =
                    destination.position() == startPosition;

            if (allowCleanEof && noBytesRead) {
                return false;
            }

            throw new EOFException(
                    "Peer closed before the frame was complete");
        }
    }

    return true;
}
```

Tham số `allowCleanEof` chỉ cho phép EOF nếu chưa đọc byte nào vào buffer hiện tại. Nếu đã đọc được một phần rồi mới EOF, hàm ném `EOFException` để báo frame bị cắt.

Có thể dùng hàm này để đọc giao thức length-prefixed:

```java
private static final int MAX_FRAME_SIZE = 1_048_576;

static void receiveFrames(SocketChannel peer) throws IOException {
    peer.configureBlocking(true);

    while (true) {
        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);

        // EOF trước byte đầu tiên của header: kết thúc sạch giữa hai frame.
        if (!readFully(peer, header, true)) {
            System.out.println("Peer kết thúc luồng gửi");
            return;
        }

        header.flip();
        int length = header.getInt();

        if (length < 0 || length > MAX_FRAME_SIZE) {
            throw new IOException("Invalid frame length: " + length);
        }

        ByteBuffer payload = ByteBuffer.allocate(length);

        // EOF khi payload chưa đủ luôn là frame bị cắt.
        readFully(peer, payload, false);
        payload.flip();
        handleFrame(payload);
    }
}

static void handleFrame(ByteBuffer payload) {
    System.out.println("Received frame with "
            + payload.remaining() + " bytes");
}
```

Giới hạn `MAX_FRAME_SIZE` ngăn peer khai báo một payload quá lớn khiến ứng dụng cấp phát bộ nhớ không kiểm soát. Trong ứng dụng thực tế, hãy chọn giới hạn phù hợp với giao thức và tài nguyên của tiến trình.

## 5. Đọc một lần không có nghĩa là nhận đủ dữ liệu

Không nên viết:

```java
ByteBuffer buffer = ByteBuffer.allocate(1024);
int count = peer.read(buffer);
buffer.flip();
processMessage(buffer);
```

để giả định rằng một lần đọc luôn chứa đúng một thông điệp. Một lần đọc có thể chỉ nhận một phần header, một phần payload, hoặc nhiều byte hơn dự kiến của một thông điệp. Cách xử lý đúng là giữ trạng thái parser giữa các lần đọc và chỉ xử lý frame khi đã nhận đủ byte theo framing protocol.

Các chiến lược framing phổ biến:

| Chiến lược | Cách xác định ranh giới |
| --- | --- |
| Length-prefixed | Header chứa số byte của payload |
| Delimiter-based | Một chuỗi byte phân cách kết thúc thông điệp, ví dụ newline |
| Fixed-size | Mỗi thông điệp có kích thước cố định |

Với delimiter-based, delimiter cũng có thể bị chia giữa nhiều lần đọc. Parser cần giữ lại phần byte cuối chưa đủ để xác định delimiter. Không dùng giả định rằng một lần `write()` từ peer sẽ tương ứng với một lần `read()` ở phía nhận.

## 6. Đóng kết nối bằng close()

`close()` đóng channel cục bộ và giải phóng tài nguyên hệ điều hành gắn với channel. Với kết nối đã chấp nhận, đóng `SocketChannel` khi không còn xử lý dữ liệu của peer. Với server, đóng `ServerSocketChannel` khi không nhận thêm kết nối.

Ưu tiên `try-with-resources`:

```java
try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    server.bind(UnixDomainSocketAddress.of(
            Path.of("/tmp/orders.sock")));

    try (SocketChannel peer = server.accept()) {
        receiveFrames(peer);
    }
}
```

Khi khối kết thúc, channel được đóng kể cả khi `receiveFrames()` ném exception. Trong server phục vụ nhiều client, mỗi channel được accept cần vòng đời và cleanup riêng; không để một kết nối lỗi làm rò rỉ channel hoặc file descriptor.

Nếu một thread khác đóng channel trong lúc thread hiện tại đang block ở thao tác I/O, thao tác đó có thể kết thúc bằng exception liên quan đến việc channel bị đóng bất đồng bộ. Hãy thiết kế luồng shutdown rõ ràng và tránh đóng channel tùy tiện từ nhiều nơi.

## 7. Phân biệt close() với shutdownInput() và shutdownOutput()

`SocketChannel` hỗ trợ đóng một chiều của kết nối:

| Thao tác | Ảnh hưởng |
| --- | --- |
| `close()` | Đóng channel cục bộ, kết thúc cả hai chiều I/O và giải phóng tài nguyên |
| `shutdownOutput()` | Ngừng gửi dữ liệu từ phía cục bộ; peer sẽ đọc hết byte đã gửi rồi nhận EOF |
| `shutdownInput()` | Ngừng nhận dữ liệu ở phía cục bộ; các lần đọc tiếp theo trả EOF |

`shutdownOutput()` hữu ích khi giao thức cần báo “tôi đã gửi xong request” nhưng vẫn chờ response. Ví dụ client gửi xong request rồi half-close chiều gửi:

```java
try (SocketChannel client =
         SocketChannel.open(StandardProtocolFamily.UNIX)) {

    client.connect(UnixDomainSocketAddress.of(
            Path.of("/tmp/orders.sock")));

    writeFully(client, requestBuffer);
    client.shutdownOutput();

    ByteBuffer response = ByteBuffer.allocate(4096);
    while (true) {
        int count = client.read(response);
        if (count == -1) {
            break;
        }
        if (count > 0) {
            response.flip();
            processResponseBytes(response);
            response.compact();
        }
    }
}
```

Sau `shutdownOutput()`, client vẫn có thể đọc response vì chiều nhận chưa bị đóng. Không gọi `close()` ngay sau khi gửi nếu giao thức còn yêu cầu nhận phản hồi.

`shutdownInput()` ít được dùng trong luồng xử lý thông thường. Khi gọi, ứng dụng chủ động từ bỏ dữ liệu chiều nhận; nó không phải cách kiểm tra peer đã đóng kết nối hay chưa.

## 8. Ghi đủ dữ liệu và xử lý peer đóng giữa lúc gửi

`SocketChannel.write()` cũng có thể ghi ít byte hơn số byte còn lại trong buffer. Với blocking channel, lặp cho tới khi buffer được tiêu thụ:

```java
static void writeFully(
        SocketChannel channel,
        ByteBuffer source) throws IOException {

    if (!channel.isBlocking()) {
        throw new IllegalStateException(
                "writeFully requires a blocking channel");
    }

    while (source.hasRemaining()) {
        channel.write(source);
    }
}
```

Nếu peer đóng đầu nhận hoặc kết nối gặp lỗi khi đang gửi, thao tác ghi có thể ném `IOException`. Không giả định lần ghi tiếp theo sẽ thành công và không lặp vô hạn để thử lại cùng một buffer. Hãy xử lý lỗi ở phạm vi kết nối, đóng channel và ghi log đủ thông tin để chẩn đoán.

Một lần ghi thành công cũng không chứng minh peer đã xử lý dữ liệu. Dữ liệu có thể mới được hệ điều hành nhận vào buffer gửi. Nếu ứng dụng cần xác nhận nghiệp vụ, giao thức phải có response hoặc acknowledgement ở tầng ứng dụng.

## 9. Nhận biết peer ngắt giữa chừng

Peer có thể kết thúc kết nối trong nhiều thời điểm:

| Thời điểm peer ngắt | Dấu hiệu phía ứng dụng |
| --- | --- |
| Trước khi gửi frame mới | EOF ngay đầu header; có thể là kết thúc sạch |
| Khi đang gửi header | EOF sau một phần header; frame không hợp lệ |
| Khi đang gửi payload | EOF trước khi nhận đủ độ dài đã khai báo; frame bị cắt |
| Khi server đang gửi response | Ghi có thể ném IOException; thời điểm phát hiện phụ thuộc trạng thái I/O |
| Sau khi gọi shutdownOutput() | Peer thấy EOF ở chiều nhận request nhưng có thể vẫn đọc response |

Không nên chỉ kiểm tra `isOpen()` hoặc `isConnected()` để xác định peer còn hoạt động. Hai phương thức này phản ánh trạng thái channel cục bộ; chúng không phải heartbeat và không xác nhận tiến trình bên kia đang đọc hoặc còn sống.

Với giao thức cần phát hiện peer không phản hồi trong một khoảng thời gian, hãy bổ sung timeout ở tầng ứng dụng. Có thể dùng non-blocking channel với `Selector` và deadline; khi đó `read()` trả `0` nghĩa là chưa có dữ liệu tại thời điểm kiểm tra, không phải EOF. Không dùng vòng lặp bận để chờ dữ liệu.

## 10. Xử lý exception theo phạm vi một kết nối

Server nên cô lập lỗi của một peer để không làm dừng toàn bộ dịch vụ:

```java
try (SocketChannel peer = server.accept()) {
    try {
        receiveFrames(peer);
    } catch (EOFException e) {
        System.err.println(
                "Peer đóng kết nối giữa một frame: " + e.getMessage());
    } catch (IOException e) {
        System.err.println(
                "I/O error với peer: " + e.getMessage());
    }
}
```

Trong server thực tế, đặt khối xử lý này trong vòng lặp accept hoặc task riêng cho từng client. Khi một peer gửi frame không hợp lệ hoặc ngắt giữa chừng, đóng channel đó, ghi nhận lỗi và tiếp tục phục vụ kết nối khác theo chính sách của ứng dụng.

Không bắt mọi exception rồi bỏ qua. Nếu bỏ qua EOF giữa payload, ứng dụng có thể xử lý dữ liệu chưa đầy đủ như một request hợp lệ. Nếu lỗi là lỗi giao thức, có thể ghi nhận peer hoặc request bị lỗi và kết thúc riêng kết nối đó.

## 11. Cleanup Unix socket file sau khi server đóng

Khi server bind vào một đường dẫn Unix-domain socket trên hệ thống file, đường dẫn socket có thể còn tồn tại sau khi channel đóng. Trên Linux/macOS, ứng dụng server thường xóa socket path do chính nó tạo sau khi đã đóng server channel:

```java
Path socketPath = Path.of("/tmp/orders.sock");
boolean bound = false;

try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    server.bind(UnixDomainSocketAddress.of(socketPath));
    bound = true;

    try (SocketChannel peer = server.accept()) {
        receiveFrames(peer);
    }
} finally {
    if (bound) {
        Files.deleteIfExists(socketPath);
    }
}
```

Chỉ xóa path nếu tiến trình đã bind thành công và sở hữu socket path đó. Không xóa mù một file có sẵn trước khi bind; file có thể thuộc về một server khác hoặc là một file thường quan trọng. Trong triển khai có nhiều instance, cần cơ chế chọn path duy nhất và quản lý vòng đời socket rõ ràng.

Đường dẫn `/tmp/orders.sock` là ví dụ cho Linux/macOS. Chọn vị trí phù hợp với hệ điều hành, quyền truy cập và chính sách triển khai. Bảo vệ quyền trên thư mục socket vì Unix-domain socket dựa trên quyền filesystem để kiểm soát tiến trình có thể kết nối.

## 12. Blocking và non-blocking: không nhầm 0 với EOF

Ở blocking mode, thao tác đọc thường chờ dữ liệu hoặc kết thúc luồng. Ở non-blocking mode, thao tác có thể trả `0` nếu hiện chưa có byte nào. Mẫu xử lý khác nhau:

| Blocking channel | Non-blocking channel |
| --- | --- |
| Có thể dùng vòng lặp `read()` cho tới EOF hoặc đủ frame | Dùng `Selector` để chờ `OP_READ` |
| `read()` chờ dữ liệu khi buffer còn chỗ | `read()` có thể trả `0` ngay |
| Helper `readFully` đơn giản có thể phù hợp | Cần giữ trạng thái buffer/parser qua nhiều lần readiness |
| Không nên block event loop dùng chung | Không spin khi nhận `0`; quay lại selector |

Với non-blocking channel, parser phải lưu lại vị trí header/payload đang đọc dở. Khi selector báo channel sẵn sàng, tiếp tục đọc vào buffer hiện tại; chỉ xử lý frame khi đủ byte. Nếu `read()` trả `-1`, xử lý EOF giống quy tắc giao thức ở trên: EOF giữa frame là dữ liệu bị cắt.

## 13. Checklist xử lý kết nối

- [ ] Dùng `StandardProtocolFamily.UNIX` và `UnixDomainSocketAddress` cho Unix-domain stream channel.
- [ ] Xác định framing protocol thay vì giả định mỗi lần read là một message.
- [ ] Phân biệt EOF ở đầu frame với EOF giữa header/payload.
- [ ] Dùng vòng lặp đọc đủ byte cho blocking channel.
- [ ] Xử lý partial write bằng vòng lặp ghi đủ byte.
- [ ] Phân biệt `close()` với `shutdownOutput()` và `shutdownInput()`.
- [ ] Cô lập lỗi I/O hoặc frame bị cắt trong phạm vi kết nối peer.
- [ ] Dùng `try-with-resources` để đóng channel.
- [ ] Chỉ xóa socket path mà tiến trình đã bind thành công và sở hữu.
- [ ] Với non-blocking channel, xử lý `0` bằng `Selector` thay vì vòng lặp bận.
- [ ] Thêm timeout/acknowledgement ở tầng ứng dụng nếu cần phát hiện peer không phản hồi.

## Ghi nhớ

**Trong Unix-domain stream socket, `read()` trả `-1` khi chiều nhận đã tới EOF; `0` không phải EOF và một lần đọc không bảo đảm nhận đủ một thông điệp.** Hãy xác định framing, chấp nhận EOF sạch chỉ giữa hai frame, coi EOF giữa header hoặc payload là frame bị cắt, và xử lý IOException khi peer ngắt lúc ghi. Dùng `shutdownOutput()` khi cần báo hết dữ liệu gửi mà vẫn chờ response; dùng `close()` để kết thúc channel và giải phóng tài nguyên. Với socket path trên filesystem, chỉ cleanup path do tiến trình sở hữu.

## Tài liệu tham khảo

- [Oracle Java SE 26 — SocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Oracle Java SE 26 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Oracle Java SE 26 — UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [Oracle Java SE 26 — StandardProtocolFamily](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html)
- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
