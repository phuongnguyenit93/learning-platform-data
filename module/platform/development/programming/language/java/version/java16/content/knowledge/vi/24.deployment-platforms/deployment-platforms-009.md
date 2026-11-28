# Kiểm thử Unix-domain socket và installer trên từng nền tảng đích

Khi ứng dụng Java sử dụng Unix-domain socket hoặc được phân phối bằng installer native, cần kiểm thử trên đúng hệ điều hành, kiến trúc và runtime sẽ triển khai. Unix-domain socket (AF_UNIX) cung cấp giao tiếp liên tiến trình trên cùng máy thông qua đường dẫn socket; installer như MSI, DEB, RPM, PKG hoặc DMG lại phụ thuộc nền tảng đóng gói và cơ chế cài đặt của hệ điều hành.

Java 16 bổ sung Unix-domain socket channels qua JEP 380 và đưa `jpackage` thành công cụ đóng gói chính thức. Các API này vẫn có trong JDK hiện đại. Tuy nhiên, Java 16 là feature release đã hết thời gian hỗ trợ thông thường; dự án production nên dùng JDK LTS còn được nhà cung cấp duy trì, đồng thời kiểm tra khả năng hỗ trợ của chính JDK, OS và kiến trúc mục tiêu.

## 1. Xác định phạm vi kiểm thử

Trước khi xây dựng test matrix, cần ghi rõ các target mà sản phẩm cam kết hỗ trợ:

- Hệ điều hành và phiên bản tối thiểu: Linux distribution, Windows build, macOS release.
- Kiến trúc tiến trình: x64/AMD64 hoặc ARM64/AArch64.
- JDK vendor, major version, patch release và kiến trúc runtime.
- Có dùng Unix-domain socket hay không; socket được tạo ở đường dẫn nào và process nào kết nối.
- Loại gói: `app-image`, EXE/MSI, DEB/RPM, PKG/DMG.
- Chế độ cài đặt: theo user hay toàn máy, quyền cần thiết và tài khoản chạy ứng dụng.
- Các native dependency, Java agent, service, shortcut, file association hoặc cấu hình hệ điều hành liên quan.

Ví dụ ma trận:

| Target | UDS cần xác minh | Artifact cài đặt cần test |
|---|---|---|
| Linux x64, glibc | Socket path, quyền Unix, cleanup và IPC | DEB hoặc RPM tùy distro được hỗ trợ |
| Linux ARM64, glibc/musl | JDK và native dependency đúng kiến trúc/libc; socket path | DEB/RPM hoặc image ứng dụng phù hợp |
| Windows x64 | Hỗ trợ AF_UNIX của OS/JDK, ACL và socket path | EXE hoặc MSI x64 |
| Windows ARM64 | JVM process ARM64 hoặc x64 emulation; đúng native dependencies | EXE hoặc MSI cho kiến trúc được hỗ trợ |
| macOS ARM64 | Unix-domain socket, quyền thư mục và đường dẫn | PKG hoặc ứng dụng trong DMG |

Không cần kiểm thử mọi định dạng trên mọi hệ điều hành. Chỉ đưa vào ma trận những tổ hợp sản phẩm thực sự phát hành và có môi trường xác minh.

## 2. Unix-domain socket trong Java là gì?

Unix-domain socket là cơ chế IPC để hai tiến trình trên cùng host trao đổi dữ liệu qua một socket address gắn với filesystem path. Nó không dùng IP address hoặc TCP port. Trên các nền tảng hỗ trợ, cơ chế này có thể giảm overhead so với loopback TCP và cho phép dùng quyền filesystem để giới hạn tiến trình nào có thể truy cập socket.

Từ Java 16, API NIO hỗ trợ AF_UNIX qua:

- `StandardProtocolFamily.UNIX` để chọn protocol family.
- `UnixDomainSocketAddress` để biểu diễn địa chỉ bằng `Path`.
- `ServerSocketChannel` để bind và accept kết nối.
- `SocketChannel` để connect, đọc và ghi dữ liệu.

Ví dụ mở server channel:

```java
ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX);
server.bind(UnixDomainSocketAddress.of(socketPath));
```

Ví dụ mở client channel:

```java
SocketChannel client = SocketChannel.open(StandardProtocolFamily.UNIX);
client.connect(UnixDomainSocketAddress.of(socketPath));
```

Các overload mặc định `SocketChannel.open()` và `ServerSocketChannel.open()` vẫn tạo socket Internet; phải chọn `StandardProtocolFamily.UNIX` hoặc dùng overload nhận `UnixDomainSocketAddress` cho client. UDS của JEP 380 là stream socket thông qua NIO channels. API `java.net.Socket`/`ServerSocket` truyền thống không được mở rộng thành UDS; datagram UDS và một số tính năng đặc thù của Unix cũng không nằm trong phạm vi API này.

## 3. Khả năng hỗ trợ phụ thuộc OS và JDK

Không nên suy luận rằng mọi hệ điều hành có tên Unix đều hỗ trợ UDS theo cùng một cách. JDK cần có implementation cho OS đó, OS cần cung cấp AF_UNIX tương ứng và runtime phải đáp ứng các giới hạn nền tảng.

Một số nguyên tắc:

- Linux và macOS hiện đại thường hỗ trợ Unix-domain socket.
- Windows hỗ trợ AF_UNIX trên các bản Windows phù hợp; cần kiểm tra build Windows và JDK vendor/version đang triển khai.
- Nếu protocol family không được hỗ trợ, việc mở channel có thể ném `UnsupportedOperationException`.
- Lỗi `IOException` khi bind/connect có thể là lỗi đường dẫn, quyền, socket đã tồn tại hoặc môi trường; không nên tự động coi mọi `IOException` là nền tảng không hỗ trợ.
- Chạy test trên đúng kiến trúc tiến trình. Windows ARM64 chạy JDK x64 qua emulation vẫn là process x64.

Nếu UDS là yêu cầu bắt buộc của sản phẩm trên một target, test không được âm thầm skip khi môi trường đó không hỗ trợ. Nếu UDS chỉ là tính năng tùy chọn và ứng dụng có transport dự phòng, có thể dùng JUnit assumption để bỏ qua test UDS trên target không hỗ trợ, đồng thời kiểm thử đường fallback riêng.

## 4. Những khác biệt cần kiểm thử với UDS

### Socket address và giới hạn độ dài

Địa chỉ UDS thường là đường dẫn filesystem. Giới hạn độ dài phụ thuộc OS và implementation, thường ngắn hơn đáng kể so với đường dẫn file thông thường. Trên nhiều nền tảng, giới hạn có thể xấp xỉ khoảng 100 byte; không dùng con số này làm hợp đồng chung cho mọi OS.

Hãy dùng socket path ngắn, tuyệt đối và ổn định. Đặc biệt, thư mục temp hoặc user profile trên Windows có thể khiến đường dẫn tổng dài hơn dự kiến. Nếu dùng thư mục tạm, kiểm tra đường dẫn đầy đủ sau khi ghép tên socket. JDK có cấu hình riêng cho thư mục tạm của socket được tự động bind; với socket path do ứng dụng tự chọn, hãy quản lý trực tiếp đường dẫn và giới hạn của OS.

### Socket file còn tồn tại sau khi đóng channel

Trên hệ thống dùng filesystem socket node, khi server channel đóng, file socket có thể vẫn còn trên filesystem. Lần bind sau vào cùng tên sẽ thất bại nếu socket file cũ vẫn tồn tại. Ứng dụng cần dọn socket path khi shutdown và xử lý file tồn dư sau crash.

Chỉ xóa một socket path đã biết trong thư mục riêng do ứng dụng kiểm soát. Không xóa tùy tiện một đường dẫn cấu hình từ bên ngoài vì nó có thể trỏ đến file thường hoặc dữ liệu của tiến trình khác.

### Quyền truy cập

Trên Unix, quyền của thư mục chứa socket và quyền của socket node ảnh hưởng tiến trình nào có thể kết nối. Trên Windows, kiểm tra ACL và tài khoản chạy service. Không đặt socket trong thư mục cài đặt ứng dụng nếu thư mục đó chỉ đọc hoặc dùng chung cho nhiều user.

### IPC chỉ trong cùng host

UDS phục vụ giao tiếp giữa các tiến trình trên cùng máy. Hai container có thể dùng chung UDS nếu chúng chạy trên cùng host và mount cùng một volume chứa socket path. UDS không thay thế kết nối giữa các host khác nhau hoặc giữa các node trong cluster.

## 5. Ví dụ server/client trao đổi dữ liệu qua UDS

Ví dụ sau dùng thông điệp cố định bốn byte để minh họa round-trip `PING`/`PONG`. Trong giao thức thực tế, cần thiết kế message framing rõ ràng, vì một lần `read` hoặc `write` trên stream channel không đảm bảo xử lý trọn một message.

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnixSocketRoundTrip {
    static void writeFully(SocketChannel channel, byte[] bytes)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    static byte[] readExactly(SocketChannel channel, int size)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(size);
        while (buffer.hasRemaining()) {
            if (channel.read(buffer) < 0) {
                throw new EOFException("Peer closed before message completed");
            }
        }
        return buffer.array();
    }

    public static void main(String[] args) throws IOException {
        Path socketPath = Path.of(args[0]).toAbsolutePath();
        Files.createDirectories(socketPath.getParent());

        // Chỉ xóa socket tồn dư trong thư mục riêng do ứng dụng kiểm soát.
        Files.deleteIfExists(socketPath);

        try (ServerSocketChannel server =
                     ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            server.bind(UnixDomainSocketAddress.of(socketPath));

            try (SocketChannel peer = server.accept()) {
                byte[] request = readExactly(peer, 4);
                String text = new String(request, StandardCharsets.UTF_8);
                if (!text.equals("PING")) {
                    throw new IOException("Unexpected request: " + text);
                }
                writeFully(peer, "PONG".getBytes(StandardCharsets.UTF_8));
            }
        } finally {
            Files.deleteIfExists(socketPath);
        }
    }
}
```

Client tương ứng:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class UnixSocketClient {
    public static void main(String[] args) throws IOException {
        Path socketPath = Path.of(args[0]).toAbsolutePath();

        try (SocketChannel client =
                     SocketChannel.open(StandardProtocolFamily.UNIX)) {
            client.connect(UnixDomainSocketAddress.of(socketPath));

            ByteBuffer request = ByteBuffer.wrap(
                    "PING".getBytes(StandardCharsets.UTF_8));
            while (request.hasRemaining()) {
                client.write(request);
            }

            ByteBuffer response = ByteBuffer.allocate(4);
            while (response.hasRemaining()) {
                if (client.read(response) < 0) {
                    throw new IOException("Server closed before response completed");
                }
            }
            response.flip();
            System.out.println(StandardCharsets.UTF_8.decode(response));
        }
    }
}
```

Chạy server trước rồi chạy client với cùng socket path. Kết quả client mong đợi là `PONG`. Khi đưa vào production, nên bổ sung timeout, xác thực client theo mô hình bảo mật của ứng dụng, giới hạn kích thước message, xử lý nhiều client và shutdown có kiểm soát.

## 6. Kiểm thử UDS bằng JUnit Jupiter

Một integration test nên tạo thư mục tạm riêng, bind server, kết nối client, kiểm tra dữ liệu hai chiều và xác nhận socket file được dọn sau khi test. Ví dụ sau dùng hai task để server và client chạy đồng thời:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class UnixDomainSocketTest {
    private static void writeFully(SocketChannel channel, String value)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(
                value.getBytes(StandardCharsets.UTF_8));
        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    private static String readExactly(SocketChannel channel, int size)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(size);
        while (buffer.hasRemaining()) {
            if (channel.read(buffer) < 0) {
                throw new EOFException("Unexpected end of stream");
            }
        }
        return new String(buffer.array(), StandardCharsets.UTF_8);
    }

    @Test
    void serverAndClientExchangeMessage() throws Exception {
        Path directory = Files.createTempDirectory("uds-");
        Path socketPath = directory.resolve("s.sock");
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try (ServerSocketChannel server =
                     ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            server.bind(UnixDomainSocketAddress.of(socketPath));

            Future<?> serverTask = pool.submit(() -> {
                try (SocketChannel peer = server.accept()) {
                    assertEquals("PING", readExactly(peer, 4));
                    writeFully(peer, "PONG");
                }
                return null;
            });

            Future<String> clientTask = pool.submit(() -> {
                try (SocketChannel client =
                             SocketChannel.open(StandardProtocolFamily.UNIX)) {
                    client.connect(UnixDomainSocketAddress.of(socketPath));
                    writeFully(client, "PING");
                    return readExactly(client, 4);
                }
            });

            serverTask.get(5, TimeUnit.SECONDS);
            assertEquals("PONG", clientTask.get(5, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
            Files.deleteIfExists(socketPath);
            Files.deleteIfExists(directory);
        }
    }
}
```

Test trên cần chạy trên target mà sản phẩm cam kết hỗ trợ UDS. Nếu CI dùng thư mục tạm có đường dẫn quá dài, hãy cấu hình test temp root ngắn hơn; giới hạn socket path phụ thuộc OS và có thể làm test thất bại dù API đã được hỗ trợ. Khi UDS là yêu cầu bắt buộc, lỗi mở/bind/connect phải làm job thất bại để nhóm phát triển xử lý, không tự động chuyển thành skipped test.

## 7. Các trường hợp UDS cần kiểm thử ngoài round-trip

| Trường hợp | Cách kiểm thử | Kết quả cần xác nhận |
|---|---|---|
| Nền tảng không hỗ trợ | Mở channel với `StandardProtocolFamily.UNIX` trên target được khai báo | Phát hiện rõ unsupported platform; fallback hoạt động nếu được thiết kế |
| Socket path đã tồn tại | Tạo socket, đóng server rồi bind lại cùng path | Ứng dụng cleanup socket tồn dư an toàn |
| Đường dẫn quá dài | Chạy với path sát giới hạn của OS | Ứng dụng báo lỗi rõ hoặc chọn path ngắn hơn |
| Quyền truy cập | Kết nối bằng user/group được phép và user không được phép | ACL/permissions chặn đúng đối tượng |
| Shutdown bình thường | Dừng server qua shutdown hook hoặc lifecycle manager | Channel đóng và socket path được dọn |
| Crash/restart | Kết thúc server bất thường rồi khởi động lại | Stale socket được nhận diện và xử lý an toàn |
| Nhiều client | Mở nhiều client đồng thời | Server xử lý đúng concurrency và giới hạn tài nguyên |
| Non-blocking/Selector | Nếu ứng dụng dùng selector, test register/read/write readiness | Không giả định socket Internet option áp dụng cho UDS |
| Container cùng host | Hai container mount chung volume chứa socket | Client kết nối được và quyền volume đúng |
| Khác host/node | Thử kết nối qua UDS | Xác nhận đây không phải transport liên host; dùng TCP/network transport nếu cần |

UDS là stream, nên protocol phải tự định nghĩa framing như độ dài message, delimiter hoặc fixed-size frame. Một lần `read` không nhất thiết nhận toàn bộ payload; một lần `write` cũng có thể ghi ít hơn số byte yêu cầu. Test nên mô phỏng partial read/write và đóng kết nối giữa chừng.

## 8. Quyền và vị trí socket trong ứng dụng đã cài đặt

Không nên tạo socket trong thư mục cài đặt ứng dụng. Installer có thể đặt application image ở `Program Files`, `/opt` hoặc `/Applications`, nơi user chạy ứng dụng không có quyền ghi. Socket nên nằm trong runtime directory hoặc thư mục tạm/data phù hợp với user/service.

Khi thiết kế vị trí socket:

- Dùng thư mục riêng có owner và quyền truy cập phù hợp.
- Trên Unix, giới hạn quyền thư mục và socket theo user/group; không để thư mục cha có quyền ghi rộng cho user không tin cậy.
- Trên Windows, kiểm tra ACL cho thư mục và socket path.
- Không đưa dữ liệu nhạy cảm vào tên socket path.
- Không tin một socket path chỉ vì file tồn tại; xác định process sở hữu và trạng thái trước khi cleanup.
- Kiểm tra `java.io.tmpdir`, thư mục service và chính sách filesystem read-only.
- Với container, mount volume có quyền ghi phù hợp cho server và client; path trong hai container phải trỏ tới cùng socket file trên shared volume.

Nếu ứng dụng dùng socket tự động bind, cần đọc cấu hình JDK liên quan đến thư mục tạm của UDS và kiểm tra đường dẫn thực tế. Với socket path do ứng dụng quản lý, hãy truyền path rõ ràng qua cấu hình và kiểm tra độ dài trước khi bind.

## 9. jpackage và các loại artifact cần kiểm thử

`jpackage` đóng gói ứng dụng Java thành application image hoặc installer native theo hệ điều hành. Application image là bước phù hợp để kiểm thử launcher và runtime trước khi tạo installer. Installer cần được build trên nền tảng đích; `jpackage` không cung cấp khả năng cross-platform để tạo gói Windows từ Linux hoặc gói macOS từ Windows.

Các định dạng thường dùng:

| Nền tảng | Định dạng jpackage | Điều cần kiểm tra |
|---|---|---|
| Windows | EXE, MSI | Per-user/per-machine install, UAC, shortcuts, registry, file association, signing |
| Linux | DEB, RPM | Package dependencies, install/remove/upgrade qua package manager, desktop entry và quyền file |
| macOS | PKG, ứng dụng trong DMG | Bundle layout, code signing, Gatekeeper, notarization và quyền truy cập |

Các công cụ phụ trợ để tạo installer thay đổi theo JDK và OS. Ví dụ, Windows packaging có thể yêu cầu WiX; Linux cần công cụ tạo DEB/RPM như `fakeroot` hoặc `rpm-build`; macOS cần Xcode command line tools cho một số thao tác ký gói. Kiểm tra tài liệu `jpackage` đúng JDK đang dùng trước khi cấu hình runner.

## 10. Tạo application image trước khi tạo installer

Trước hết, tạo application image:

```sh
jpackage \
  --type app-image \
  --name LocalAgent \
  --input build/input \
  --main-jar local-agent.jar \
  --app-version 2.1.0 \
  --dest build/app-image
```

Chạy launcher trong application image để kiểm tra:

- Ứng dụng khởi động và tìm đúng runtime nhúng.
- Tài nguyên, file cấu hình và native dependencies có mặt.
- Ứng dụng ghi dữ liệu vào vị trí được phép, không ghi vào thư mục cài đặt chỉ đọc.
- Unix-domain socket bind/connect được trên target và socket path được cleanup.
- Logging, shutdown và các chức năng nghiệp vụ hoạt động.

Sau khi application image đạt yêu cầu, tạo installer trên runner của nền tảng tương ứng. Ví dụ lệnh minh họa:

Windows:

```powershell
jpackage --type msi --name LocalAgent `
  --app-image build\app-image\LocalAgent `
  --app-version 2.1.0 --dest dist
```

Linux Debian:

```sh
jpackage --type deb \
  --name local-agent \
  --app-image build/app-image/LocalAgent \
  --app-version 2.1.0 \
  --dest dist
```

macOS:

```sh
jpackage --type dmg \
  --name LocalAgent \
  --app-image build/app-image/LocalAgent.app \
  --app-version 2.1.0 \
  --dest dist
```

Đường dẫn app-image có thể khác theo nền tảng và phiên bản JDK. Hãy dùng đúng thư mục thực tế do `jpackage --type app-image` tạo ra. Để tạo RPM, dùng `--type rpm` trên runner Linux có đủ công cụ packaging tương ứng.

## 11. Kiểm thử cài đặt trên Windows

Với EXE/MSI, kiểm thử trên máy ảo Windows sạch cho từng kiến trúc được hỗ trợ. Nên xác nhận:

- Installer mở và hoàn tất với quyền phù hợp; phân biệt cài theo user và toàn máy.
- Đường dẫn cài đặt, tên ứng dụng, shortcut và menu đúng.
- File association và launcher hoạt động nếu sản phẩm cung cấp.
- Runtime được đóng gói chạy đúng kiến trúc; `java.home` và `os.arch` trong ứng dụng phản ánh runtime mong muốn.
- Native DLL và mọi dependency được nạp thành công.
- Ứng dụng chạy dưới tài khoản chuẩn, không phụ thuộc quyền Administrator sau khi cài.
- UDS path nằm trong thư mục user/service có ACL phù hợp, không nằm trong thư mục cài đặt chỉ đọc.
- Nâng cấp từ phiên bản trước giữ lại dữ liệu người dùng và cập nhật đúng file.
- Gỡ cài đặt xóa thành phần do installer quản lý, giữ dữ liệu người dùng theo chính sách sản phẩm.
- Chữ ký Authenticode hợp lệ và cảnh báo hệ điều hành được xử lý theo kênh phân phối.

Nếu phát hành cả Windows x64 và ARM64, test đúng JDK/runtime và native DLL của từng gói. Máy ARM64 có thể chạy JDK x64 qua emulation; điều đó không thay thế test bằng JDK ARM64 native nếu sản phẩm công bố hỗ trợ ARM64 native.

## 12. Kiểm thử cài đặt trên Linux

DEB và RPM nên được cài trên các distro/version nằm trong ma trận hỗ trợ. Không chỉ kiểm tra `dpkg-deb --info` hoặc `rpm -qpl`; cần cài package bằng package manager và chạy ứng dụng sau cài đặt.

Ví dụ trên hệ Debian/Ubuntu:

```sh
sudo apt install ./local-agent_2.1.0_amd64.deb
```

Ví dụ trên hệ RPM:

```sh
sudo dnf install ./local-agent-2.1.0-1.x86_64.rpm
```

Các trường hợp cần xác nhận:

- Dependency package được khai báo đúng và package manager giải quyết được.
- File cài đặt, launcher, desktop entry, icon và menu đúng.
- Quyền owner/mode của file và thư mục phù hợp.
- Ứng dụng chạy bằng user thường và có thể ghi vào thư mục data/runtime cần thiết.
- Socket file được tạo ở runtime directory phù hợp, không tạo trong `/opt` nếu user không có quyền.
- Gỡ và nâng cấp qua package manager không để lại file socket hoặc dữ liệu không mong muốn.
- DEB/RPM được tạo đúng kiến trúc và đúng hệ package của distro.

Nếu ứng dụng cần systemd service hoặc integration với service manager, kiểm thử unit/service riêng theo distro và chính sách vận hành; không giả định `jpackage` tự tạo mọi tích hợp service mà sản phẩm cần.

## 13. Kiểm thử cài đặt trên macOS

Với macOS, test PKG hoặc ứng dụng trong DMG trên máy sạch cho từng kiến trúc được hỗ trợ. Kiểm tra:

- App bundle có cấu trúc và runtime nhúng đúng.
- Launcher chạy trên macOS version tối thiểu được công bố.
- Quyền thư mục, sandbox/quyền riêng tư và vị trí dữ liệu phù hợp.
- UDS path có độ dài phù hợp và socket được dọn sau khi ứng dụng dừng.
- Native `.dylib` đúng kiến trúc và được ký đúng yêu cầu.
- Code signature hợp lệ; gói phân phối ngoài App Store đáp ứng quy trình notarization/Gatekeeper hiện hành.
- Nâng cấp thay thế đúng app bundle mà không xóa dữ liệu người dùng.
- Gỡ cài đặt xóa đúng bundle và thành phần phụ trợ theo hướng dẫn sản phẩm.

`jpackage` có các tùy chọn ký gói macOS, nhưng quy trình notarization và phát hành tin cậy còn phụ thuộc tài khoản Developer ID, chứng thư và yêu cầu hiện hành của Apple. Cần kiểm tra quy trình phân phối thực tế trên một máy sạch, không chỉ kiểm tra lệnh đóng gói thành công.

## 14. Kiểm thử upgrade, uninstall và dữ liệu người dùng

Installer test không kết thúc ở lần cài đầu tiên. Với mỗi nền tảng, cần có chuỗi kiểm thử:

1. Cài phiên bản mới trên máy sạch.
2. Khởi chạy lần đầu, kiểm tra runtime, cấu hình và quyền.
3. Chạy các chức năng nghiệp vụ, bao gồm UDS nếu được dùng.
4. Tạo dữ liệu người dùng và cấu hình riêng.
5. Cài bản nâng cấp từ phiên bản trước.
6. Xác nhận launcher, runtime, native dependency và dữ liệu vẫn đúng.
7. Gỡ cài đặt theo hướng dẫn.
8. Xác nhận file do installer quản lý đã được xóa; dữ liệu người dùng được giữ hoặc xóa đúng chính sách đã công bố.
9. Cài lại và kiểm tra ứng dụng có xử lý được socket path hoặc thư mục runtime tồn dư.

Không lưu database, log hoặc cấu hình người dùng trong thư mục cài đặt nếu installer có thể thay thế toàn bộ thư mục khi nâng cấp. Tách application files khỏi user data giúp nâng cấp và gỡ cài đặt dễ dự đoán hơn.

## 15. Tích hợp UDS vào installer test

Nếu ứng dụng dùng UDS để giao tiếp giữa launcher, service, helper process hoặc sidecar, phải kiểm tra UDS sau khi cài bằng chính tài khoản và đường dẫn runtime của sản phẩm.

Một số kịch bản quan trọng:

- Ứng dụng được cài ở vị trí mặc định và vị trí tùy chỉnh.
- User thường khởi chạy app; socket được tạo ở nơi user có quyền.
- Service chạy dưới tài khoản riêng; client chỉ có quyền truy cập theo chính sách.
- Ứng dụng bị kill/crash rồi khởi động lại; stale socket được xử lý.
- Nâng cấp trong lúc service đang chạy được chặn hoặc điều phối đúng.
- Gỡ cài đặt khi app đã dừng không để lại socket file do ứng dụng tạo.
- Đường dẫn user profile/temp dài hoặc có ký tự Unicode được kiểm thử.
- Windows ARM64/x64 emulation dùng đúng runtime và native dependency theo process architecture.
- Container deployment dùng shared volume nếu các process ở container khác nhau nhưng cùng host.

Nếu ứng dụng hỗ trợ TCP fallback khi UDS không có, kiểm tra cả hai chế độ và xác nhận cấu hình không vô tình mở TCP listener khi sản phẩm chỉ cho phép local IPC.

## 16. CI matrix và quản lý artifact

`jpackage` phải chạy trên nền tảng tương ứng với loại package cần tạo. Tổ chức CI theo job native cho từng OS; nếu có nhiều kiến trúc, chọn runner và JDK/runtime phù hợp với kiến trúc gói. Có thể build JAR dùng chung ở job riêng, sau đó chuyển JAR sang các job đóng gói.

Ví dụ matrix khái quát:

| CI job | Công việc |
|---|---|
| Linux x64 | UDS integration test, tạo app-image, DEB/RPM nếu distro hỗ trợ |
| Linux ARM64 | UDS test trên ARM64, kiểm tra native dependency và tạo package ARM64 |
| Windows x64 | UDS test, app-image, EXE/MSI x64, signing và install test |
| Windows ARM64 | UDS test, app-image, package đúng kiến trúc và kiểm tra native DLL |
| macOS ARM64 | UDS test, app bundle, PKG/DMG, signing/notarization test |

Với mỗi artifact, lưu metadata gồm JDK vendor/version, OS version, CPU architecture, package type, installer toolchain, checksum và kết quả test. Không dùng artifact app-image của Windows để đóng gói installer Linux hoặc ngược lại.

Installer và runtime cần được kiểm tra lại khi nâng JDK patch, base OS hoặc native dependency. Pin toolchain giúp tái lập build, nhưng phải có lịch cập nhật bảo mật và chạy lại toàn bộ smoke/integration test.

## 17. Ghi nhớ

- UDS Java 16+ dùng `SocketChannel`/`ServerSocketChannel` với `StandardProtocolFamily.UNIX` và `UnixDomainSocketAddress`.
- UDS là stream IPC trên cùng host; không thay thế TCP cho giao tiếp liên host.
- Kiểm tra hỗ trợ theo JDK, OS và build cụ thể; không bỏ qua test trên target mà sản phẩm cam kết hỗ trợ.
- Socket file có thể còn sau khi server channel đóng; phải cleanup trong thư mục do ứng dụng kiểm soát.
- Kiểm tra độ dài path, permissions/ACL, stale socket, shutdown và nhiều client.
- `jpackage --type app-image` là bước test launcher/runtime trước installer.
- Installer native phải được tạo trên nền tảng tương ứng; kiểm thử đúng EXE/MSI, DEB/RPM hoặc PKG/DMG.
- Test cài mới, nâng cấp, gỡ bỏ, quyền user, chữ ký và dữ liệu người dùng.
- Khi app dùng UDS, chạy test sau cài đặt bằng đúng tài khoản và đường dẫn runtime production.
- Dùng JDK LTS còn được duy trì; API UDS và jpackage vẫn áp dụng trên các JDK hiện đại.

## Tài liệu tham khảo

- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380) — phạm vi và mục tiêu UDS trong Java 16.
- [JDK 25 NIO Channels API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/package-summary.html) — các channel API hiện hành.
- [JDK 25 SocketChannel API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SocketChannel.html) — hỗ trợ socket channel và các option của UDS.
- [Unix-domain socket channels: Inside Java](https://inside.java/2021/02/03/jep380-unix-domain-sockets-channels/) — ví dụ client/server, socket file lifecycle và giới hạn.
- [JDK 25 jpackage Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html) — yêu cầu build theo nền tảng, định dạng installer và application image.
- [JDK 25 jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html) — các loại package và tùy chọn đóng gói.
