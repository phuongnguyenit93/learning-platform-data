# Giải phóng ngữ cảnh bằng dispose và xử lý lỗi xác thực

## 1. Ngữ cảnh SASL sống trong bao lâu?

SASL là khuôn khổ để giao thức ứng dụng sử dụng các cơ chế xác thực. Trong Java, `SaslClient` và `SaslServer` giữ trạng thái của một cuộc trao đổi xác thực. Khi cuộc trao đổi kết thúc, đối tượng có thể vẫn cần thiết cho lớp bảo vệ dữ liệu của phiên.

Vì vậy, hãy phân biệt hai mốc:

- **Xác thực kết thúc:** không còn bước thương lượng xác thực cần thực hiện.
- **Ngữ cảnh hết được sử dụng:** không còn thao tác nào của phiên cần đối tượng SASL nữa.

Nếu phiên dùng lớp bảo vệ SASL để bảo đảm toàn vẹn hoặc bí mật, việc xử lý dữ liệu tiếp tục phụ thuộc vào ngữ cảnh sau xác thực. Đây là lý do không đặt `dispose()` ngay sau một lần `evaluateChallenge()` hoặc ngay khi thấy `isComplete() == true`. Xem hợp đồng của [SaslClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html) và [SaslServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html).

Bài này dùng các API còn áp dụng trên Java hiện đại. Ví dụ chạy trên Java 17 trở lên, không cần máy chủ xác thực và không cấu hình cơ chế mật mã cũ.

## 2. dispose thực hiện điều gì?

Cả hai giao diện đều có phương thức:

```java
void dispose() throws SaslException;
```

Lệnh này yêu cầu giải phóng tài nguyên hệ thống hoặc thông tin nhạy cảm mà ngữ cảnh đang sử dụng. Sau khi gọi, coi đối tượng là **đã vô hiệu hóa**, không đưa trở lại kho dùng chung và không tiếp tục đánh giá dữ liệu xác thực hay bảo vệ dữ liệu bằng nó.

Hợp đồng quy định `dispose()` có tính lũy đẳng: gọi lại không tạo thêm một lần chuyển trạng thái có ý nghĩa. Điều đó không phải lời hứa rằng thao tác dọn dẹp không thể ném lỗi; chữ ký vẫn khai báo `SaslException`. Thiết kế một nơi chịu trách nhiệm đóng ngữ cảnh sẽ dễ kiểm soát hơn việc rải lệnh đóng ở nhiều lớp. Các chi tiết này có trong mục `dispose()` của [SaslClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html#dispose()) và [SaslServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html#dispose()).

Đừng suy rộng trách nhiệm của phương thức:

| Tài nguyên | Ai cần quản lý vòng đời? |
| --- | --- |
| Trạng thái nội bộ của đối tượng SASL | Bên sở hữu ngữ cảnh, thông qua `dispose()` |
| Kết nối và luồng mạng | Tầng giao thức/kết nối của ứng dụng |
| Thông tin đăng nhập do ứng dụng giữ riêng | Thành phần đã tạo hoặc đang sở hữu dữ liệu đó |
| Nhiệm vụ bất đồng bộ đang sử dụng ngữ cảnh | Thành phần điều phối phiên |

Không có cơ sở để cho rằng gọi `dispose()` sẽ tự đóng mọi kết nối của ứng dụng, đăng xuất mọi hệ thống bên ngoài hoặc xóa mọi bản sao bí mật trong bộ nhớ. Hãy quy định riêng trách nhiệm cho từng tài nguyên.

## 3. Đặt điểm giải phóng theo vòng đời phiên

Một thiết kế thực tế có thể dùng quy tắc sau:

```text
Tạo ngữ cảnh
    |
    +-- Tạo thất bại / không có ngữ cảnh -> xử lý lỗi khởi tạo
    |
    +-- Trao đổi xác thực
            |
            +-- Lỗi / hủy / hết hạn -> kết thúc lần thử -> dọn dẹp
            |
            +-- Thành công
                    |
                    +-- Còn dùng lớp bảo vệ SASL -> giữ đến khi phiên kết thúc
                    |
                    +-- Không còn cần ngữ cảnh -> dọn dẹp
```

Với chất lượng bảo vệ `auth-int` hoặc `auth-conf`, các thao tác `wrap()`/`unwrap()` cần ngữ cảnh đã thương lượng xong. Không giải phóng khi còn dữ liệu cần xử lý. Với phiên không cần ngữ cảnh sau xác thực, có thể kết thúc phạm vi sở hữu sớm hơn, sau khi đã xử lý kết quả cuối cùng cần thiết. Việc gắn SASL vào giao thức và lớp bảo vệ được mô tả trong [RFC 4422](https://www.rfc-editor.org/rfc/rfc4422.html#section-3.7).

Ở phía máy khách, `isComplete()` không thay thế thông báo kết quả của giao thức. Một số cơ chế còn cần xử lý dữ liệu cuối từ phía máy chủ. Không cấp quyền cho phiên chỉ vì phía máy khách đã ngừng tạo phản hồi; tầng giao thức phải xác nhận cuộc trao đổi thành công.

Khi hủy phiên có nhiều tác vụ, trước hết ngăn tác vụ mới sử dụng ngữ cảnh và kết thúc các thao tác đang chạy theo thiết kế của ứng dụng, rồi mới giải phóng. Không để một luồng gọi `dispose()` trong lúc luồng khác vẫn đang sử dụng ngữ cảnh.

## 4. Không để lỗi dọn dẹp che mất lỗi gốc

Đoạn minh họa sau có lỗi thiết kế:

```java
// Minh họa vấn đề, không phải chương trình độc lập.
try {
    authenticate();
} finally {
    client.dispose();
}
```

Nếu `authenticate()` ném lỗi và `dispose()` cũng ném lỗi, ngoại lệ từ khối `finally` có thể trở thành lỗi được truyền ra, che lỗi xảy ra trước đó.

Trong Java hiện đại, có thể dùng `try-with-resources` thông qua một bộ chuyển tiếp. `SaslClient` và `SaslServer` không tự triển khai `AutoCloseable`; không viết trực tiếp `try (SaslClient client = ...)`. Tạo đối tượng có `close()` gọi `dispose()` của ngữ cảnh đã được tạo thành công.

Theo cơ chế của [AutoCloseable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html), khi thân khối ném lỗi, lỗi đóng tài nguyên được giữ như ngoại lệ bị kìm lại (suppressed exception). Dùng [Throwable.getSuppressed()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Throwable.html#getSuppressed()) để kiểm tra; nó khác `getCause()`, vốn mô tả nguyên nhân của một ngoại lệ.

## 5. Ví dụ chạy được: giữ lỗi xác thực và lỗi dispose

Lưu thành **SaslDisposeDemo.java**:

```java
import java.util.Objects;
import javax.security.sasl.AuthenticationException;
import javax.security.sasl.SaslClient;
import javax.security.sasl.SaslException;
import javax.security.sasl.SaslServer;

public class SaslDisposeDemo {
    @FunctionalInterface
    interface Disposer {
        void dispose() throws SaslException;
    }

    static final class SaslResource implements AutoCloseable {
        private final Disposer disposer;
        private boolean closed;

        SaslResource(Disposer disposer) {
            this.disposer = Objects.requireNonNull(disposer);
        }

        static SaslResource ofClient(SaslClient client) {
            Objects.requireNonNull(client);
            return new SaslResource(client::dispose);
        }

        static SaslResource ofServer(SaslServer server) {
            Objects.requireNonNull(server);
            return new SaslResource(server::dispose);
        }

        @Override
        public void close() throws SaslException {
            if (!closed) {
                closed = true;
                disposer.dispose();
            }
        }
    }

    public static void main(String[] args) {
        authenticationAndCleanupFail();
        onlyCleanupFails();
    }

    private static void authenticationAndCleanupFail() {
        try (SaslResource resource = new SaslResource(() -> {
            System.out.println("dispose: attempted");
            throw new SaslException("cleanup failed");
        })) {
            throw new AuthenticationException("authentication failed");
        } catch (AuthenticationException e) {
            System.out.println("primary: " + e.getClass().getSimpleName());
            System.out.println("suppressed: " + e.getSuppressed().length);
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("cleanup: "
                        + suppressed.getClass().getSimpleName());
            }
        } catch (SaslException e) {
            System.out.println("other SASL failure");
        }
    }

    private static void onlyCleanupFails() {
        try (SaslResource resource = new SaslResource(() -> {
            throw new SaslException("cleanup failed");
        })) {
            System.out.println("body: completed");
        } catch (SaslException e) {
            System.out.println("primary: " + e.getClass().getSimpleName());
            System.out.println("suppressed: " + e.getSuppressed().length);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac SaslDisposeDemo.java
java SaslDisposeDemo
```

Stdout chính xác:

```text
dispose: attempted
primary: AuthenticationException
suppressed: 1
cleanup: SaslException
body: completed
primary: SaslException
suppressed: 0
```

Ở tình huống đầu, lỗi xác thực vẫn là lỗi chính; lỗi dọn dẹp nằm trong `getSuppressed()`. Ở tình huống sau, thân khối không ném lỗi nên lỗi dọn dẹp được truyền ra như lỗi chính.

Đây là phép thử **cơ chế quản lý vòng đời và ngoại lệ**, không thực hiện xác thực mạng, không giả vờ kiểm chứng một cơ chế SASL thực. Hai phương thức `ofClient()` và `ofServer()` là điểm gắn với ngữ cảnh thật. Chẳng hạn, sau khi đã tạo được một `SaslClient` khác `null`:

```java
// Đoạn tích hợp; client đã được tạo và thuộc quyền sở hữu của phạm vi này.
try (var resource = SaslDisposeDemo.SaslResource.ofClient(client)) {
    // Toàn bộ thao tác cần client nằm trong phạm vi này:
    // trao đổi xác thực, kiểm tra kết quả giao thức,
    // rồi xử lý dữ liệu nếu phiên còn cần lớp bảo vệ SASL.
}
```

Chỉ bọc ngữ cảnh khi tầng hiện tại nhận trách nhiệm giải phóng. Nếu một thư viện đang sở hữu phiên và đã quản lý ngữ cảnh, hãy sử dụng hợp đồng đóng phiên của thư viện đó.

Cờ `closed` trong ví dụ khiến bộ chuyển tiếp chỉ gọi thao tác giải phóng một lần, kể cả khi thao tác đó ném lỗi. Nó không chứng minh dọn dẹp đã thành công và không làm bộ chuyển tiếp an toàn cho sử dụng đồng thời. Ví dụ dành cho một chủ sở hữu tuần tự; chính sách khôi phục lỗi giải phóng thuộc về ứng dụng.

## 6. Phân loại lỗi xác thực đúng mức

`javax.security.sasl.AuthenticationException` là lớp con của `SaslException`. Nó biểu thị lỗi liên quan đến xác thực, chẳng hạn danh tính hoặc thông tin chứng minh danh tính không hợp lệ. Vì vậy, nếu cần xử lý riêng, đặt `catch (AuthenticationException ...)` trước `catch (SaslException ...)`.

Tuy nhiên, **không nhận được AuthenticationException không đồng nghĩa lỗi không liên quan đến xác thực**. Nhà cung cấp có thể chỉ ném `SaslException`, kể cả khi không muốn công bố nguyên nhân cụ thể. Không phân loại bằng cách tìm chuỗi “wrong password” trong thông báo lỗi. Đây là giới hạn được nêu trong [hợp đồng AuthenticationException](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/AuthenticationException.html).

Các hướng xử lý sau là chính sách ứng dụng gợi ý, không phải cam kết mọi nhà cung cấp trả cùng loại ngoại lệ:

| Nhóm tình huống | Hướng xử lý |
| --- | --- |
| Thông tin xác thực bị từ chối | Kết thúc lần thử, không gửi yêu cầu nghiệp vụ như đã xác thực |
| Lỗi SASL chưa phân loại được | Giữ nguyên nguyên nhân khi có; xem xét cấu hình, cơ chế và tầng giao thức |
| Lỗi mạng, hết hạn, hủy yêu cầu | Kết thúc lần thử có kiểm soát và giải phóng theo quyền sở hữu |
| Lỗi dọn dẹp sau lỗi chính | Giữ lỗi chính, ghi nhận lỗi dọn dẹp riêng |
| Lỗi dọn dẹp sau thân khối hoàn tất | Báo lỗi quản lý tài nguyên; không tự diễn giải thành “sai mật khẩu” |

Một `SaslException` có thể bọc lỗi của thành phần cung cấp thông tin cho quá trình xác thực qua callback. Khi điều tra nội bộ, xem chuỗi `getCause()`; không chỉ đọc thông báo ở lớp ngoài. [SaslException](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslException.html) mô tả trường hợp bọc lỗi này.

## 7. Thử lại và ghi nhận lỗi

Sau một lần xác thực lỗi, không tái sử dụng ngữ cảnh đã hỏng hoặc đã giải phóng. Nếu chính sách cho phép thử lại, bắt đầu một lần thử mới với ngữ cảnh mới; khả năng dùng lại kết nối mạng phụ thuộc giao thức và thư viện.

Thiết kế chính sách thử lại có giới hạn. Liên tục gửi lại cùng thông tin đăng nhập bị từ chối thường không giải quyết nguyên nhân và có thể làm tăng tải hoặc kích hoạt khóa tài khoản. Không tự động hạ yêu cầu bảo vệ chỉ để lần thử sau “thành công”.

Đối với nhật ký vận hành, ưu tiên mã sự kiện, mã tương quan, giai đoạn xảy ra lỗi, loại ngoại lệ và kết quả dọn dẹp. Không ghi mật khẩu, mã thông báo, dữ liệu challenge/response thô hoặc toàn bộ dữ liệu truyền qua lớp bảo vệ. Thông báo ngoại lệ và nguyên nhân cũng cần được xem xét trước khi đưa vào nhật ký; đừng mặc định mọi thông báo của nhà cung cấp đều không chứa dữ liệu nhạy cảm.

Phản hồi ra ngoài nên đủ để người dùng biết lần xác thực không thành công mà không tiết lộ danh tính nào tồn tại hoặc bí mật nào bị từ chối. Ví dụ mã minh họa chỉ in **tên lớp ngoại lệ và số lượng lỗi phụ**, không in dữ liệu xác thực.

## 8. Tự kiểm tra cách áp dụng

1. Nếu xác thực thành công nhưng phiên vẫn gọi `wrap()`, có được `dispose()` ngay không? **Không.** Ngữ cảnh vẫn còn phục vụ lớp bảo vệ.
2. Nếu xác thực và dọn dẹp cùng lỗi, lỗi nào cần giữ làm lỗi chính? **Lỗi phát sinh trong thân khối**; lỗi đóng được giữ trong danh sách suppressed khi dùng `try-with-resources`.
3. Nếu `dispose()` lỗi sau khi thao tác chính đã hoàn tất, có thể kết luận mật khẩu sai không? **Không.** Đó là lỗi ở giai đoạn dọn dẹp.
4. Nếu chỉ nhận `SaslException`, có loại trừ lỗi xác thực không? **Không.** Hợp đồng cho phép nhà cung cấp dùng ngoại lệ tổng quát.
5. Ai đóng ngữ cảnh do thư viện giao thức quản lý? **Thành phần sở hữu theo hợp đồng của thư viện**; tránh hai tầng cùng tự nhận trách nhiệm.

Khi đưa vào ứng dụng, kiểm tra riêng các đường đi: thành công, bị từ chối, lỗi mạng, hủy yêu cầu và lỗi giải phóng. Ở mỗi đường đi, xác nhận phiên không tiếp tục dùng ngữ cảnh đã vô hiệu hóa và lỗi gốc vẫn còn được giữ.
