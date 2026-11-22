# SASL: Phối hợp bảo vệ đường truyền và bảo vệ thông tin bí mật

## 1. Hiểu đúng hai lớp bảo vệ

Một ứng dụng Java kết nối đến máy chủ thư, LDAP hoặc dịch vụ có SASL phải trả lời hai câu hỏi: **đường truyền có an toàn không** và **đang xác thực bằng danh tính nào**. Mật khẩu hay token còn phải được giữ kín trước và sau khi truyền.

TLS bảo vệ tính bí mật, tính toàn vẹn của kết nối và giúp xác minh máy chủ. SASL là khung gắn cơ chế xác thực vào giao thức ứng dụng; khả năng bảo vệ dữ liệu sau xác thực tùy cơ chế. Vì vậy, “SASL thành công” không đồng nghĩa với “mọi dữ liệu đã được mã hóa”. [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html), [RFC 4422](https://www.rfc-editor.org/rfc/rfc4422.html).

| Thành phần | Trách nhiệm cần kiểm tra |
| --- | --- |
| TLS | Mã hóa và chống sửa dữ liệu trên chặng kết nối; xác minh đúng máy chủ |
| Cơ chế SASL | Chứng minh danh tính theo cơ chế được lựa chọn |
| Quản lý bí mật | Cấp phát, lưu giữ, hạn chế truy cập, thay thế và thu hồi mật khẩu/token |
| Phân quyền ứng dụng | Quyết định danh tính đã xác thực được làm gì |

Ba lớp đầu bổ sung cho nhau. TLS không làm một mật khẩu trong Git trở nên an toàn; giữ mật khẩu trong kho bí mật cũng không bảo vệ được khi gửi nó qua kết nối thiếu bảo vệ.

## 2. TLS phải hoàn tất trước khi gửi thông tin xác thực

Với cấu hình yêu cầu TLS, thứ tự xử lý là:

```text
Kết nối tới địa chỉ dự kiến
    -> thiết lập TLS
    -> kiểm tra chứng chỉ và danh tính máy chủ
    -> đọc/thương lượng khả năng SASL trên kênh đã bảo vệ
    -> chọn cơ chế thuộc chính sách cho phép
    -> lấy thông tin xác thực khi cần
    -> trao đổi SASL
    -> kiểm tra kết quả và áp dụng phân quyền
```

Chỉ bật mã hóa là chưa đủ: nếu chấp nhận chứng chỉ của bất kỳ ai hoặc bỏ kiểm tra tên máy chủ, ứng dụng có thể đưa bí mật cho kẻ đứng giữa. Với Java, kho tin cậy và kiểm tra danh tính điểm cuối là hai phần cần cấu hình đúng; không dùng cách “tin tất cả chứng chỉ” để chữa lỗi kết nối. [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html).

Ưu tiên TLS 1.3; dùng TLS 1.2 khi cần tương thích và cấu hình mật mã phù hợp. Không tự mở lại các phiên bản TLS đã bị loại bỏ chỉ để đăng nhập thành công. JDK và thư viện TLS cần được cập nhật cùng cấu hình triển khai. [OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html), [RFC 8996](https://www.rfc-editor.org/rfc/rfc8996.html).

### TLS ngay từ đầu và STARTTLS

TLS ngay từ đầu bắt tay trước dữ liệu ứng dụng. STARTTLS bắt đầu bằng kết nối thường rồi nâng cấp theo giao thức. Nếu chọn STARTTLS nhưng chính sách bắt buộc mã hóa, không được tiếp tục gửi mật khẩu khi nâng cấp bị từ chối, không được quảng bá hoặc bắt tay thất bại.

Sau nâng cấp, bỏ thông tin khả năng chưa được bảo vệ và lấy lại khả năng theo quy định của giao thức. Không tự viết một lệnh STARTTLS chung cho mọi dịch vụ: trình tự của SMTP, IMAP và LDAP khác nhau. Với thư điện tử, lựa chọn cổng và chế độ TLS phải khớp cấu hình máy chủ; RFC 8314 mô tả TLS ngay từ đầu cho truy cập và gửi thư. [RFC 4422, yêu cầu khi thay đổi lớp bảo vệ](https://www.rfc-editor.org/rfc/rfc4422.html), [RFC 8314](https://www.rfc-editor.org/rfc/rfc8314.html).

## 3. Chọn cơ chế SASL cùng chính sách bảo vệ bí mật

### SCRAM-SHA-256 và SCRAM-SHA-256-PLUS

SCRAM-SHA-256 dùng trao đổi chứng minh dựa trên mật khẩu thay vì gửi trực tiếp mật khẩu. Biến thể SCRAM-SHA-256-PLUS hỗ trợ gắn xác thực với kênh bên dưới (channel binding).

Điều này không thay thế TLS cho nội dung ứng dụng. Không suy ra rằng mọi đoạn dữ liệu sau SCRAM đều được mã hóa. Hỗ trợ cơ chế phụ thuộc cả máy khách, máy chủ và nhà cung cấp triển khai. [RFC 7677](https://www.rfc-editor.org/rfc/rfc7677.html).

Khi dùng channel binding, hai phía phải hỗ trợ cùng loại và xử lý dữ liệu gắn kênh đúng quy định. Với TLS 1.3, RFC 9266 định nghĩa loại `tls-exporter`; không tự ghép tên máy chủ hay chuỗi chứng chỉ rồi gọi đó là channel binding. Nếu chính sách bắt buộc biến thể PLUS, không tự hạ xuống biến thể không gắn kênh khi thương lượng thất bại. [RFC 9266](https://www.rfc-editor.org/rfc/rfc9266.html).

### OAUTHBEARER

Token thay cho việc đưa mật khẩu dài hạn của người dùng vào từng ứng dụng. Token có thể bị đánh cắp và sử dụng trong phạm vi hiệu lực của nó, nên vẫn cần TLS, giới hạn quyền, thời hạn và khả năng thu hồi. Không ghi token vào log hay dùng refresh token tùy tiện làm thông tin SASL.

Máy chủ cần xác minh token theo mô hình triển khai, bao gồm tài nguyên đích, quyền và hạn sử dụng. Token không hợp lệ phải dẫn đến từ chối; không âm thầm chuyển sang dùng mật khẩu. [RFC 7628](https://www.rfc-editor.org/rfc/rfc7628.html).

### PLAIN cần được hiểu theo đúng ranh giới

PLAIN tự nó không tạo lớp mã hóa hay bảo vệ toàn vẹn. Nếu hệ thống còn chủ động cho phép cơ chế này, chỉ gửi thông tin xác thực khi đã có lớp bảo vệ đủ mạnh và xác minh máy chủ đúng. Base64 dùng trong giao thức chỉ là biểu diễn dữ liệu, không phải mã hóa bí mật.

Tên cơ chế “PLAIN” không nói rằng cả kết nối đang không mã hóa; ngược lại, việc có TLS cũng không loại bỏ rủi ro bí mật tại máy nhận. Chọn cơ chế theo chính sách hệ thống và khả năng hỗ trợ thực tế, không theo một tên được máy chủ quảng bá. [RFC 4616](https://www.rfc-editor.org/rfc/rfc4616.html).

## 4. Phân biệt lớp SASL với lớp TLS trong Java

`Sasl.QOP` có các giá trị:

| Giá trị | Bảo vệ do lớp SASL thương lượng |
| --- | --- |
| `auth` | Xác thực |
| `auth-int` | Xác thực và toàn vẹn |
| `auth-conf` | Xác thực, toàn vẹn và bí mật |

Không phải cơ chế nào cũng hỗ trợ mọi mức. Đặt `auth-conf` không tự biến cơ chế chỉ xác thực thành cơ chế mã hóa. `auth` vẫn có thể nằm bên trong TLS và dữ liệu vẫn được TLS bảo vệ. [Java Sasl.QOP](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html#QOP).

Nếu cơ chế thương lượng lớp bảo vệ, thư viện giao thức phải thực sự sử dụng `wrap()`/`unwrap()` cho dữ liệu tiếp theo. Kiểm tra hoàn tất phía Java phải đi cùng kết quả thành công của giao thức máy chủ; gọi `isComplete()` riêng lẻ chưa đủ kết luận đăng nhập thành công. Sau sử dụng, gọi `dispose()` để giải phóng tài nguyên nhạy cảm. [Java SaslClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html).

`Sasl.POLICY_NOPLAINTEXT` là bộ lọc cơ chế; nó không thiết lập hoặc kiểm chứng TLS. Giá trị `serverName` truyền cho `createSaslClient()` cũng không tự cấu hình kiểm tra chứng chỉ cho socket. Cần xử lý trường hợp không tìm được triển khai phù hợp; không có cơ chế phù hợp thì dừng. [Java Sasl](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html).

## 5. Ví dụ Java: cổng kiểm tra trước khi bắt đầu SASL

Chương trình sau chạy độc lập bằng Java 17+. Nó **mô phỏng chính sách**, không mở kết nối, không thực hiện TLS hay xác thực SASL và không sử dụng bí mật thật. Danh sách cơ chế là lựa chọn minh họa của ứng dụng này.

```java
import java.util.Set;

public class SaslTransportPolicyDemo {
    record Channel(boolean handshakeSucceeded,
                   boolean peerVerified,
                   String tlsVersion) {}

    private static final Set<String> TLS_VERSIONS =
            Set.of("TLSv1.3", "TLSv1.2");
    private static final Set<String> MECHANISMS =
            Set.of("SCRAM-SHA-256", "SCRAM-SHA-256-PLUS",
                   "OAUTHBEARER");

    static String check(Channel channel, String mechanism) {
        if (!channel.handshakeSucceeded()) {
            return "DENY: TLS handshake required";
        }
        if (!channel.peerVerified()) {
            return "DENY: server identity not verified";
        }
        if (!TLS_VERSIONS.contains(channel.tlsVersion())) {
            return "DENY: TLS version not allowed";
        }
        if (!MECHANISMS.contains(mechanism)) {
            return "DENY: mechanism not allowed";
        }
        return "ALLOW: may start SASL";
    }

    public static void main(String[] args) {
        System.out.println(check(
                new Channel(false, false, ""), "OAUTHBEARER"));
        System.out.println(check(
                new Channel(true, false, "TLSv1.3"), "OAUTHBEARER"));
        System.out.println(check(
                new Channel(true, true, "TLSv1.3"), "UNKNOWN"));
        System.out.println(check(
                new Channel(true, true, "TLSv1.3"), "SCRAM-SHA-256"));
    }
}
```

Lưu đúng tên `SaslTransportPolicyDemo.java`, rồi chạy:

```shell
javac SaslTransportPolicyDemo.java
java SaslTransportPolicyDemo
```

Stdout:

```text
DENY: TLS handshake required
DENY: server identity not verified
DENY: mechanism not allowed
ALLOW: may start SASL
```

Hai trường hợp đầu cho thấy “có kết nối” hoặc “có mã hóa” chưa đủ cho phép xác thực. Trường hợp thứ ba chặn cơ chế ngoài danh sách. Dòng cuối chỉ cho phép **bắt đầu** SASL, chưa cấp quyền truy cập.

Trong hệ thống thật, không nhận `peerVerified=true` từ tham số người dùng hoặc cờ cấu hình. Trạng thái phải xuất phát từ kết quả bắt tay đã xác minh trên **chính kết nối sẽ gửi SASL**; nếu đổi hoặc nối lại kết nối thì kiểm tra lại. Mã mô phỏng không thay việc xác minh mật mã hay triển khai giao thức.

### Điểm nối với JSSE

Đoạn sau chỉ minh họa phần thiết lập một socket TLS ngay từ đầu; nó chưa phải máy khách SASL hoàn chỉnh. `socket` là `SSLSocket` phía máy khách, được tạo với tên máy chủ dự kiến và cấu hình tin cậy hợp lệ:

```java
SSLParameters parameters = socket.getSSLParameters();
parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
// Chỉ sau khi bắt tay thành công mới bắt đầu trao đổi SASL.
```

`HTTPS` ở đây là tên thuật toán kiểm tra danh tính điểm cuối của JSSE, không chuyển giao thức ứng dụng thành HTTP. Khi dùng thư viện LDAP, thư hoặc dịch vụ khác, ưu tiên tùy chọn xác minh máy chủ của chính thư viện theo giao thức đó. Không áp dụng đoạn socket này nguyên xi cho quá trình STARTTLS. [SSLParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html).

## 6. Giữ bí mật trong suốt vòng đời

Trước khi kết nối, lấy bí mật qua cơ chế được quản lý: kho bí mật hoặc thông tin xác thực ngắn hạn gắn với danh tính ứng dụng. Không đặt mật khẩu/token trong mã nguồn, tệp cấu hình được commit hay đối số dòng lệnh. Biến môi trường chỉ là phương tiện cấp cấu hình; nó không mặc nhiên trở thành kho bí mật an toàn.

Cấp quyền tối thiểu, tách danh tính theo ứng dụng/môi trường, quy định hết hạn và thu hồi. Khi thay bí mật, các kết nối mới phải dùng phiên bản mới; kiểm tra chính sách máy chủ đối với phiên đã xác thực, vì thay mật khẩu không nhất thiết đóng mọi phiên đang sống. Nếu phát hiện lộ bí mật, thu hồi và điều tra thay vì chỉ xóa chuỗi khỏi mã nguồn. [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).

Trong Java, ưu tiên `char[]` cho mật khẩu khi API hỗ trợ để có thể ghi đè sau sử dụng. `PasswordCallback.setPassword()` và `getPassword()` tạo bản sao; xóa mảng nguồn không xóa các bản sao đó. Dọn từng mảng ứng dụng sở hữu trong `finally` và gọi `clearPassword()` khi không còn cần callback. Không xóa callback trước khi bên tiêu thụ kịp đọc. Việc dọn mảng giảm thời gian tồn tại, không bảo đảm xóa mọi bản sao trong JVM. [PasswordCallback](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html).

Ghi log trạng thái TLS, cơ chế được chọn, mã lỗi và mã tương quan đủ để vận hành. Loại mật khẩu, token, chuỗi AUTH và nội dung callback khỏi log; bản mã Base64 vẫn có thể chứa bí mật. Kiểm tra cả log mức debug của thư viện trước khi bật trong môi trường thật. Giới hạn truy cập và thời gian lưu log. [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

## 7. Các tình huống dễ bỏ sót

| Tình huống | Cách xử lý |
| --- | --- |
| TLS bắt tay lỗi nhưng ứng dụng thử đăng nhập thường | Đóng kết nối; không gửi bí mật và không tự hạ bảo vệ |
| Chứng chỉ hợp lệ về chuỗi tin cậy nhưng sai tên máy chủ | Từ chối kết nối và sửa cấu hình danh tính |
| SASL thành công nhưng ứng dụng ghi token vào log | Sửa đường ghi log, xử lý lộ token và thu hồi khi cần |
| Kết nối mới sau mất mạng | Thiết lập lại TLS và SASL; không tái dùng cờ xác minh của socket cũ |
| TLS kết thúc ở bộ cân bằng tải | Xem nó là một điểm được phép thấy dữ liệu; bảo vệ cả chặng đến máy chủ phía sau |
| Chọn cơ chế không được hỗ trợ | Báo lỗi cấu hình rõ ràng; không tự thêm cơ chế yếu vào danh sách |

TLS bảo vệ giữa các điểm kết thúc của nó. Khi có proxy giải mã, cần xác định ai được đọc bí mật và cách bảo vệ chặng sau; không gọi đó là mã hóa xuyên suốt tới máy chủ cuối nếu thực tế TLS đã kết thúc ở proxy. [OWASP TLS](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

## 8. Tự kiểm tra cách phối hợp

1. **Một kênh TLS có chứng chỉ sai tên, nhưng mật khẩu đúng: có tiếp tục SASL không?** Không. Phải xác minh đúng điểm nhận trước khi gửi thông tin xác thực.
2. **Thương lượng QOP là `auth` nhưng kết nối dùng TLS đã xác minh: nội dung có thể được mã hóa không?** Có, bởi TLS; cần phân biệt lớp cung cấp bảo vệ.
3. **Token chỉ sống ngắn hạn thì có được ghi vào log không?** Không. Trong thời gian còn hiệu lực, token vẫn là bí mật có thể bị lợi dụng.
4. **Đổi mật khẩu trong kho bí mật có chắc đóng mọi phiên SASL đang hoạt động không?** Không được giả định; cần kiểm tra cơ chế phiên và thu hồi của máy chủ.

Một kết nối chỉ đạt mục tiêu khi bảo vệ đường truyền, xác thực danh tính và quản lý bí mật cùng đáp ứng chính sách. Hãy kiểm tra cả đường thành công lẫn trường hợp phải từ chối trước khi đưa bí mật thật vào luồng xử lý.
