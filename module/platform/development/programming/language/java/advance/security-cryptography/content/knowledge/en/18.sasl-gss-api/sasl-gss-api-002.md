# 18.2 SaslClient, SaslServer và vòng trao đổi challenge–response

## 1. Bức tranh tổng thể

**SASL (Simple Authentication and Security Layer)** là khung xác thực cho các giao thức ứng dụng, mô tả cách chọn *cơ chế* (mechanism) và trao đổi các thông điệp xác thực. SASL không tự định nghĩa TCP, HTTP, LDAP hay định dạng gói mạng: giao thức sử dụng SASL phải quy định lệnh bắt đầu xác thực, nơi mang token, trạng thái tiếp tục/thành công/thất bại và cách đóng kết nối. RFC 4422 là tài liệu nền tảng.

Trong Java, gói `javax.security.sasl` (module `java.security.sasl`) đưa cơ chế xác thực vào hai đối tượng có trạng thái:

| Thành phần | Phía sử dụng | Vai trò |
| --- | --- | --- |
| `SaslClient` | Client | Nhận challenge từ server, sinh response, theo dõi trạng thái phía client. |
| `SaslServer` | Server | Nhận response từ client, kiểm tra thông tin xác thực, có thể sinh challenge mới và xác định danh tính được ủy quyền. |
| `Sasl` | Cả hai | Tìm `SaslClientFactory`/`SaslServerFactory` qua các security provider đã đăng ký, tạo đối tượng phù hợp với mechanism và cấu hình. |
| `CallbackHandler` | Cả hai | Cung cấp dữ liệu mà mechanism yêu cầu (tên đăng nhập, mật khẩu, realm, quyết định ủy quyền...). |

**Phân biệt ba lớp:** (1) giao thức ứng dụng chuyên chở dữ liệu, (2) SASL điều phối xác thực, (3) mechanism thực hiện thuật toán cụ thể. Ví dụ, LDAP có thể mang token của cơ chế `GSSAPI`; SMTP có thể dùng cơ chế SASL khác. Việc chọn mechanism phải thuộc chính sách bảo mật và khả năng của cả hai đầu.

## 2. Hai giao diện Java và trạng thái của chúng

### 2.1. `SaslClient`

Tạo client bằng:

```java
SaslClient client = Sasl.createSaslClient(
    new String[] {"GSSAPI"},  // danh sách cơ chế chấp nhận, theo thứ tự ưu tiên
    null,                     // authorizationId mong muốn, nếu mechanism hỗ trợ
    "ldap",                   // tên giao thức/dịch vụ
    "ldap.example.com",       // tên server đích
    props,                    // thuộc tính SASL
    clientCallbackHandler
);
if (client == null) {
    throw new IllegalStateException("Không có SASL client mechanism phù hợp");
}
```

Đây là **đoạn minh họa API**, chỉ hoạt động khi `props`, `clientCallbackHandler`, provider và thông tin dịch vụ/Kerberos thích hợp đã được chuẩn bị; không phải chương trình hoàn chỉnh. Các phương thức quan trọng:

- `getMechanismName()`: trả tên mechanism thực sự được chọn. Khi truyền nhiều lựa chọn, phải gửi **đúng tên đã chọn** cho server; không giả định phần tử đầu tiên luôn có provider hỗ trợ.
- `hasInitialResponse()`: cho biết mechanism có dữ liệu client gửi ngay khi bắt đầu hay không. Nếu `true` và giao thức hỗ trợ initial response, gọi `evaluateChallenge(new byte[0])` để lấy token đầu tiên.
- `evaluateChallenge(byte[] challenge)`: nhận token của server, cập nhật state nội bộ và trả token response. Kết quả có thể là `null` trong trường hợp đặc biệt của dữ liệu cuối đi kèm trạng thái thành công, nghĩa là **không cần gửi response**; `new byte[0]` lại là **một response rỗng có thật**.
- `isComplete()`: cho biết state machine của client hoàn tất. Điều này **chưa đủ** để coi đăng nhập thành công: còn phải nhận trạng thái `SUCCESS` của giao thức/server.
- `getNegotiatedProperty(...)`, `wrap(...)`, `unwrap(...)`: dùng sau khi hoàn tất, nếu mechanism thương lượng được các thuộc tính hoặc lớp bảo vệ dữ liệu phù hợp.
- `dispose()`: giải phóng state và dữ liệu nhạy cảm do mechanism giữ.

### 2.2. `SaslServer`

Tạo server bằng:

```java
SaslServer server = Sasl.createSaslServer(
    selectedMechanism, "ldap", "ldap.example.com", props, serverCallbackHandler
);
if (server == null) {
    throw new IllegalStateException("Không có SASL server mechanism phù hợp");
}
```

Đây cũng là **đoạn minh họa API**: `selectedMechanism`, `props` và handler do ứng dụng cung cấp. Phương thức quan trọng:

- `evaluateResponse(byte[] response)`: xử lý token client và trả challenge tiếp theo; một số mechanism cần nhiều vòng. Giá trị trả về có thể là `null` nếu không còn challenge.
- `isComplete()`: state machine phía server đã kết thúc xác thực; với cơ chế/provider cụ thể, lỗi xác thực có thể được thông báo bằng `SaslException`.
- `getAuthorizationID()`: chỉ gọi **sau khi** `isComplete() == true`; trả danh tính mà client được phép sử dụng (authorization identity), không nhất thiết đồng nhất tên đăng nhập xác thực.
- `getNegotiatedProperty(...)`, `wrap(...)`, `unwrap(...)` và `dispose()` có vai trò tương ứng phía server.

Cả `SaslClient` lẫn `SaslServer` đều **có trạng thái, gắn với một phiên trao đổi**. Không chia sẻ một instance giữa các kết nối, không dùng lại instance đã `dispose()`, không giả định có thể gọi `evaluateChallenge`/`evaluateResponse` từ nhiều luồng đồng thời.

### 2.3. Callback và identity

Các mechanism hỏi thông tin qua `CallbackHandler.handle(Callback[])`. Những callback phổ biến gồm:

- `NameCallback`: tên xác thực (authentication identity, ví dụ `alice`).
- `PasswordCallback`: bí mật được dùng để chứng minh danh tính; phải quản lý vòng đời và không ghi log.
- `RealmCallback`/`RealmChoiceCallback`: realm, khi mechanism yêu cầu.
- `AuthorizeCallback`: phía server quyết định danh tính đã xác thực có được **hành động dưới authorization ID** được yêu cầu hay không.

**Authentication** trả lời “đây là ai?”; **authorization** trả lời “người này được phép hành động dưới danh tính/quyền nào?”. Cùng một tên ở hai bước trong demo đơn giản không có nghĩa ứng dụng thật được bỏ qua kiểm tra quyền. Các loại callback thực tế phụ thuộc mechanism/provider; handler phải từ chối callback không hỗ trợ bằng `UnsupportedCallbackException`.

## 3. Vòng trao đổi challenge–response

Một vòng tổng quát diễn ra như sau:

```text
Client (SaslClient)                     Server (SaslServer)
       |                                          |
       |-- AUTH <mechanism> [+ initial token] --->|  [giao thức ứng dụng]
       |<--------------- CHALLENGE ---------------|  evaluateResponse(...)
       |-- RESPONSE ----------------------------->|  evaluateChallenge(...)
       |<----------- CHALLENGE tiếp (nếu có) -----|
       |-- RESPONSE tiếp ------------------------>|
       |<----- SUCCESS / FAILURE [+ final data] --|  [giao thức ứng dụng]
       |                                          |
```

1. **Chọn và chấp nhận cơ chế.** Client chỉ chọn trong danh sách server công bố và chính sách cục bộ cho phép. Server xác nhận mechanism được phép rồi tạo `SaslServer`. Thông điệp chọn mechanism là một phần của giao thức ứng dụng, **không** do `SaslClient` tự gửi qua mạng.
2. **Khởi tạo đúng chiều.** Nếu `client.hasInitialResponse()` là `true`, client có thể tạo token đầu bằng `evaluateChallenge(new byte[0])`; nếu `false`, client chờ challenge đầu của server. Một giao thức không cho gửi initial response có thể yêu cầu một challenge rỗng đầu tiên với mechanism client-first.
3. **Trao đổi token.** Server chuyển response nhận được vào `server.evaluateResponse(...)`; client chuyển challenge nhận được vào `client.evaluateChallenge(...)`. Mỗi lần gọi có thể làm thay đổi state và sinh token để chuyển sang phía đối diện.
4. **Lặp khi cần.** Không giả định “một challenge, một response” cho mọi mechanism: một số có nhiều lượt, mutual authentication hoặc thông tin đàm phán bổ sung.
5. **Xác nhận kết thúc ở hai cấp.** Server phải báo `SUCCESS`/`FAILURE` theo giao thức. Client chỉ chấp nhận thành công khi trạng thái giao thức và trạng thái của `SaslClient` nhất quán; server phải kiểm tra xác thực và ủy quyền theo chính sách. Dữ liệu cuối kèm thông báo thành công, nếu có, vẫn có thể cần được client xử lý.
6. **Chỉ sau thành công** mới dùng authorization ID và các thuộc tính/lớp bảo vệ đã thương lượng để chuyển sang trao đổi dữ liệu ứng dụng.

`null` khác với mảng byte rỗng: `null` thường mang ý nghĩa “không có token để gửi”, còn `byte[0]` là token độ dài 0 mà giao thức vẫn có thể phải chuyển đi. Phải phân biệt thêm trạng thái `CONTINUE` và `SUCCESS`; chỉ nhìn thấy mảng rỗng không chứng minh xác thực hoàn tất.

Ở mức vận chuyển, SASL token là `byte[]` **nhị phân tùy ý**. Nếu giao thức dùng dòng văn bản, nó có thể quy định Base64; nếu dùng giao thức nhị phân, nó có thể truyền payload có length-prefix. Không tùy tiện chuyển token qua `new String(bytes)`/encoding mặc định, không tự thêm newline và không làm mất byte `0x00`.

## 4. Ví dụ Java 17+ chạy được: vòng CRAM-MD5 trong một JVM

Ví dụ chọn `CRAM-MD5` vì JDK thường có provider cho cả client và server và có thể mô phỏng một vòng challenge–response **mà không cần Kerberos hay server mạng**. CRAM-MD5 là cơ chế cũ, có hạn chế bảo mật; **chỉ dùng để học API/state machine, không đề xuất cho hệ thống mới**. Để mô phỏng, hai đầu được gọi trực tiếp trong cùng tiến trình; ứng dụng thực phải truyền token qua giao thức được thiết kế rõ ràng.

Lưu tệp `SaslRoundTripDemo.java`:

```java
import java.io.IOException;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.callback.*;
import javax.security.sasl.*;

public class SaslRoundTripDemo {
    // Bí mật cố định và dùng chung chỉ nhằm mô phỏng, KHÔNG làm vậy ở production.
    private static final char[] SECRET = "demo-only-secret".toCharArray();

    public static void main(String[] args) throws Exception {
        CallbackHandler clientHandler = callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(SECRET);
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        CallbackHandler serverHandler = callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    if (!"alice".equals(name.getDefaultName())) {
                        throw new IOException("Unknown user");
                    }
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(SECRET);
                } else if (callback instanceof AuthorizeCallback authz) {
                    authz.setAuthorized(
                        authz.getAuthenticationID().equals(authz.getAuthorizationID()));
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        SaslClient client = Sasl.createSaslClient(
            new String[] {"CRAM-MD5"}, null, "demo", "localhost",
            Map.of(), clientHandler);
        SaslServer server = Sasl.createSaslServer(
            "CRAM-MD5", "demo", "localhost", Map.of(), serverHandler);
        if (client == null || server == null) {
            throw new IllegalStateException("Mechanism not available");
        }

        try {
            // CRAM-MD5 là server-first. Phản hồi rỗng mô phỏng điểm khởi động.
            byte[] challenge = server.evaluateResponse(new byte[0]);
            int rounds = 0;

            while (!server.isComplete()) {
                if (challenge == null || rounds >= 10) {
                    throw new SaslException("Unexpected protocol state");
                }
                byte[] response = client.evaluateChallenge(challenge);
                if (response == null) {
                    throw new SaslException("Missing client response");
                }
                challenge = server.evaluateResponse(response);
                rounds++;
            }

            if (!client.isComplete()) {
                throw new SaslException("Client/server state mismatch");
            }

            System.out.println("Mechanism: " + client.getMechanismName());
            System.out.println("Authenticated: " + server.isComplete());
            System.out.println("Authorized ID: " + server.getAuthorizationID());
            System.out.println("Rounds: " + rounds);
        } finally {
            client.dispose();
            server.dispose();
            Arrays.fill(SECRET, '\0');
        }
    }
}
```

Biên dịch và chạy (JDK 17 trở lên có provider hỗ trợ `CRAM-MD5`):

```bash
javac --release 17 SaslRoundTripDemo.java
java SaslRoundTripDemo
```

Kết quả đã kiểm tra khi chạy với JDK có provider `CRAM-MD5`:

```text
Mechanism: CRAM-MD5
Authenticated: true
Authorized ID: alice
Rounds: 1
```

**Đọc mã theo đúng chiều:** server nhận lời bắt đầu giả lập và sinh challenge → client xử lý bằng `evaluateChallenge` để tạo response → server kiểm tra response → cả hai báo hoàn tất → ứng dụng mới lấy `getAuthorizationID()`. `rounds = 1` chỉ đúng với luồng CRAM-MD5 của ví dụ, không phải số vòng mặc định của SASL. Callback phía server tra cứu mật khẩu theo tên do mechanism cung cấp; chương trình dùng một user và một bí mật cố định cho dễ quan sát, còn hệ thống thật cần nguồn credential an toàn và kiểm tra quyền độc lập.

Nếu thay bí mật của một phía, trao đổi phải thất bại (`SaslException` hoặc lỗi xác thực tương ứng), tuyệt đối không chuyển sang trạng thái ứng dụng đã đăng nhập. Nếu provider bị vô hiệu hóa hoặc không có implementation, `createSaslClient`/`createSaslServer` có thể trả `null`; không được mặc định là thành công.

## 5. Phân biệt state machine với giao thức mạng thật

Đoạn Java trên gọi trực tiếp hai đối tượng nên **không** phải một server LDAP/SMTP hoàn chỉnh. Khi tích hợp vào giao thức thực, cần viết lớp điều phối riêng:

- Định nghĩa frame/lệnh chứa tên mechanism, initial response, challenge, response, trạng thái `CONTINUE`, `SUCCESS`, `FAILURE` và (nếu có) dữ liệu cuối.
- Bảo toàn **từng byte token**, ranh giới từng message và thứ tự lượt. Khi message dài hoặc bị chia khung, phải ghép đủ token trước khi đưa vào `evaluateChallenge`/`evaluateResponse`.
- Điều khiển vòng lặp theo cả trạng thái message **lẫn** `isComplete()`; giới hạn số vòng, kích cỡ token và thời gian; lỗi giao thức hoặc state lệch nhau thì hủy phiên.
- Nếu client có initial response, truyền nó ở phần được giao thức cho phép; nếu server-first, không tự gửi token client trước khi có challenge. Nếu server trả final data cùng `SUCCESS`, client xử lý đúng như đặc tả mechanism/giao thức mà không gửi response bổ sung sau khi đã kết thúc.
- Chỉ báo ứng dụng “đã xác thực” sau khi server thực sự công nhận thành công và client nhận được kết quả tương ứng. Trên thất bại, đóng/hủy phiên và dọn state bảo mật.

Một sơ đồ trạng thái giản lược:

```text
NEW
  -> MECHANISM_SELECTED
  -> EXCHANGING (challenge <-> response, lặp 0..n lần)
  -> AUTHENTICATED + AUTHORIZED  [server SUCCESS và state nhất quán]
  -> APPLICATION_TRAFFIC
                  \-> DISPOSED
  -> FAILED / ABORTED -> DISPOSED
```

Đây là mô hình để tư duy, **không phải** tập giá trị enum có sẵn trong Java SASL API.

## 6. QOP, authorization và mối liên hệ GSS-API

SASL có thể thương lượng **quality of protection** qua thuộc tính `Sasl.QOP`:

| QOP | Ý nghĩa |
| --- | --- |
| `auth` | Chỉ xác thực; **không tự cung cấp** tính toàn vẹn/bí mật cho dữ liệu ứng dụng. |
| `auth-int` | Xác thực cộng kiểm tra tính toàn vẹn của message. |
| `auth-conf` | Xác thực cộng bảo vệ tính bí mật (và toàn vẹn) của message. |

Sau khi cả hai phía hoàn tất, ứng dụng có thể kiểm tra `getNegotiatedProperty(Sasl.QOP)`. Chỉ dùng `wrap`/`unwrap` nếu mechanism và QOP thực sự hỗ trợ lớp bảo vệ (`auth-int`/`auth-conf`); các hàm này không phải thao tác luôn hợp lệ cho mọi cơ chế. Giao thức ứng dụng còn phải đóng khung các bản ghi được bảo vệ theo đúng quy định.

**GSSAPI** là một SASL mechanism sử dụng GSS-API, thường gắn với Kerberos trong JDK. Cấu hình GSSAPI cần các thông tin như principal/service name, ticket và môi trường Kerberos hợp lệ; không thể thay chuỗi `"CRAM-MD5"` bằng `"GSSAPI"` trong demo rồi mặc nhiên chạy được. Cơ chế có thể cung cấp mutual authentication và đàm phán QOP, nhưng kết quả phụ thuộc provider, cấu hình và chính sách của ứng dụng.

`AuthorizeCallback` và `getAuthorizationID()` xử lý **ủy quyền danh tính**, còn quyền đọc/sửa tài nguyên nghiệp vụ vẫn phải do application kiểm tra sau đó. Một phiên SASL thành công không có nghĩa người dùng được truy cập mọi tài nguyên.

## 7. Những lỗi phổ biến và lưu ý an toàn

| Sai lầm | Hậu quả và cách sửa |
| --- | --- |
| Gọi `evaluateChallenge` trước khi biết ai gửi token đầu | Sai thứ tự handshake; kiểm tra `hasInitialResponse()` và đặc tả mechanism/giao thức. |
| Dựa riêng vào `client.isComplete()` hoặc response không rỗng để kết luận đăng nhập thành công | Có thể chấp nhận state lệch/protocol failure; bắt buộc xử lý kết quả `SUCCESS`/`FAILURE` và kiểm tra phía server. |
| Coi `null` và `byte[0]` như nhau | Làm mất hoặc tạo thừa message; bảo toàn ý nghĩa token rỗng. |
| Chuyển token SASL thành chuỗi bằng charset mặc định | Hỏng dữ liệu nhị phân; dùng `byte[]` và encoding do giao thức quy định. |
| Giả định mọi JDK/provider có mọi cơ chế | Có thể nhận `null` từ `Sasl.createSaslClient/Server`; phải kiểm tra và fail closed. |
| Nhầm authentication ID với authorization ID | Có thể cấp nhầm quyền; áp dụng `AuthorizeCallback` và kiểm tra quyền ứng dụng. |
| Gọi `wrap`/`unwrap` lúc chưa hoàn tất hoặc với `QOP=auth` | Không có lớp bảo vệ phù hợp; kiểm tra negotiated QOP trước. |
| Ghi log password, token hoặc dùng lại state của kết nối khác | Rò rỉ bí mật/lỗi trạng thái; xóa bí mật tạm, `dispose()` và mỗi phiên một instance. |

Trong hệ thống thật:

1. **Cho phép có chọn lọc mechanism** theo chính sách hiện tại; CRAM-MD5/DIGEST-MD5 là cơ chế cũ, không nên lấy ví dụ giáo dục làm cấu hình production. Những mechanism như SCRAM có thể cần provider thư viện riêng; không mặc định JDK nào cũng hỗ trợ.
2. **Bảo vệ kênh và danh sách cơ chế** bằng TLS được xác thực hoặc lớp bảo vệ tương đương khi mô hình đe dọa yêu cầu. SASL không tự mã hóa lưu lượng và việc công bố/chọn mechanism có thể bị hạ cấp nếu không được bảo vệ. Không dùng `PLAIN` trên kênh chưa bảo vệ.
3. **Không hardcode credential**, không phản hồi lỗi tiết lộ user có tồn tại hay không, không lưu token nhạy cảm trong log. Handler phía server phải lấy bí mật đúng user từ nguồn được bảo vệ và kiểm tra authorization.
4. **Fail closed** trước lỗi token, timeout, response sai, QOP không đạt yêu cầu, mechanism không hỗ trợ hoặc hai bên báo trạng thái không nhất quán.
5. **Dọn phiên** bằng `dispose()`, đóng/loại bỏ kết nối thất bại; đặt giới hạn kích thước payload, số vòng và thời gian để tránh tiêu thụ tài nguyên vô hạn.

## 8. Tự kiểm tra hiểu bài

- Vì sao `Sasl.createSaslClient(...)` trả `null` không tương đương “mật khẩu sai”? (Vì chưa tạo được implementation cho cơ chế và chính sách đã yêu cầu.)
- Vì sao CRAM-MD5 demo gọi `server.evaluateResponse(new byte[0])` trước? (Mechanism server-first cần tạo challenge; chương trình mô phỏng phần khởi động của giao thức.)
- Sau khi `client.isComplete() == true` có được cấp quyền ngay không? (Chưa; cần server báo thành công, xác minh state phù hợp và kiểm tra quyền nghiệp vụ.)
- Khi negotiated QOP là `auth`, nên gọi `wrap` để “mã hóa” bản tin không? (Không; không có lớp bảo vệ thông điệp được thương lượng.)
- Hai luồng dùng chung một `SaslClient` cho hai kết nối liệu có an toàn? (Không; đối tượng giữ state theo một phiên.)

## 9. Tài liệu tham khảo

- [RFC 4422 — Simple Authentication and Security Layer](https://www.rfc-editor.org/rfc/rfc4422)
- [Java SE 21 — `Sasl` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html)
- [Java SE 21 — `SaslClient` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html)
- [Java SE 21 — `SaslServer` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html)
- [Java SE 21 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/21/security/)
