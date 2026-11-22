# 18.1 SASL giải quyết xác thực trong giao thức ứng dụng như thế nào

## 1. Bài toán SASL giải quyết

Một giao thức ứng dụng như SMTP, IMAP, LDAP hoặc XMPP cần trả lời câu hỏi: **đầu kết nối này đang chứng minh danh tính nào, bằng cách nào, và sau khi xác thực thành công sẽ được phép hành động với danh tính nào?**

Nếu mỗi giao thức tự thiết kế lại phần kiểm tra mật khẩu, vé Kerberos, chứng chỉ hoặc token, chúng phải tự xử lý trao đổi thông điệp, thay đổi thuật toán, lỗi xác thực và chính sách bảo mật. **SASL (Simple Authentication and Security Layer)** giải quyết bài toán tái sử dụng: giao thức ứng dụng cung cấp *chỗ để xác thực*, còn một **SASL mechanism** cung cấp cách chứng minh danh tính. Có thể thay cơ chế xác thực mà không phải thiết kế lại toàn bộ giao thức.

SASL được chuẩn hóa ở **RFC 4422** và áp dụng chủ yếu cho các giao thức có kết nối. Bản thân SASL **không phải** một phương thức mã hóa duy nhất, một dịch vụ quản lý người dùng, cũng không tự biến một kết nối không an toàn thành kết nối an toàn. Mức bảo vệ thực tế phụ thuộc vào mechanism, cấu hình máy chủ, giao thức mang nó và lớp bảo mật như TLS.

**Mục tiêu sau bài:** phân biệt giao thức ứng dụng với SASL mechanism; mô tả được các bước thương lượng và xác thực; hiểu sự khác nhau giữa authentication identity và authorization identity; chọn được cơ chế phù hợp và nhận ra các lỗi triển khai hay gặp trong Java.

## 2. Kiến trúc: giao thức “chở” thông điệp, mechanism “hiểu” chứng thực

~~~text
Ứng dụng và giao thức: SMTP / IMAP / LDAP / XMPP / ...
    │ Lệnh AUTH / bind, quảng bá capabilities, báo SUCCESS/FAILURE
    ▼
Lớp tích hợp SASL
    │ Chọn mechanism, chuyển các challenge/response dạng byte
    ▼
SASL mechanism (ví dụ PLAIN, SCRAM-SHA-256, GSSAPI, EXTERNAL)
    │ Kiểm tra mật khẩu/proof, Kerberos ticket, identity ngoài kết nối...
    ▼
Máy chủ xác thực + ánh xạ danh tính + chính sách ủy quyền
    │
    └── Nếu xác thực VÀ ủy quyền thành công → phiên ứng dụng được dùng
~~~

Một giao thức tích hợp SASL phải định nghĩa **cách quảng bá hoặc chọn mechanism**, **cách bắt đầu phiên xác thực**, **cách truyền từng thông điệp challenge/response**, **cách hủy hoặc xử lý lỗi**, và **cách báo kết quả thành công/thất bại**. Ví dụ, SMTP dùng lệnh `AUTH`; LDAP dùng SASL bind. Cú pháp khung lệnh và cách mã hóa giá trị trên dây là việc của từng giao thức. SASL mechanism làm việc với các thông điệp byte logic ở bên trong khung đó.

Mechanism có thể nhận một thông điệp đầu tiên từ client (*client-first*), chờ câu đố từ server (*server-first*), hoặc trao đổi nhiều vòng. Vì vậy không có “một gói SASL chung” dùng nguyên xi cho mọi giao thức. **Tên mechanism** và ý nghĩa của nó là phần có thể tái sử dụng; **cách đóng khung, thứ tự lệnh và trạng thái phiên** do giao thức ứng dụng quy định.

Lợi ích kiến trúc là khi hai phía cùng hỗ trợ một mechanism mới và chính sách cho phép, ứng dụng có thể nâng cấp từ cơ chế cũ sang cơ chế mạnh hơn mà vẫn giữ luồng nghiệp vụ và cách chuyển thông điệp SASL của giao thức.

## 3. Luồng xác thực từ kết nối đến phiên đã đăng nhập

1. **Thiết lập kênh và xác thực máy chủ.** Với mechanism gửi bí mật có thể khôi phục như `PLAIN` hoặc bearer token, phải có TLS bảo vệ và kiểm tra đúng danh tính máy chủ trước khi gửi chứng thực. Nếu giao thức nâng cấp bằng STARTTLS, sau nâng cấp cần thực hiện lại phần khám phá capabilities theo đặc tả giao thức, không dùng danh sách cũ một cách mù quáng.
2. **Máy chủ công bố các mechanism hợp lệ.** Ví dụ server hỗ trợ `SCRAM-SHA-256` và `PLAIN` trên kênh TLS. Danh sách được công bố có thể phụ thuộc kênh, cấu hình và chính sách.
3. **Client chọn một mechanism có hỗ trợ ở cả hai đầu và đạt yêu cầu bảo mật.** Không nên “thấy cái nào server đưa trước thì dùng”. Nếu chính sách yêu cầu SCRAM có channel binding mà chỉ còn PLAIN, client phải từ chối hoặc báo lỗi, thay vì tự hạ cấp.
4. **Bắt đầu SASL exchange.** Client gửi tên mechanism cùng initial response nếu mechanism và giao thức cho phép. Nếu không, server có thể gửi challenge trước. Các vòng tiếp theo đưa challenge của server vào mechanism phía client để tạo response, và ngược lại.
5. **Máy chủ kiểm tra bằng chứng và danh tính.** Mechanism xác thực credential/proof; server xác định *authentication identity* (ai thực sự chứng minh được danh tính). Sau đó server kiểm tra *authorization identity* (danh tính mà phiên muốn hoạt động dưới quyền), kể cả trường hợp hai danh tính khác nhau.
6. **Máy chủ báo kết quả cuối cùng bằng thông điệp của giao thức.** Chỉ **server báo thành công** và các điều kiện bảo mật/ủy quyền được đáp ứng thì ứng dụng mới coi kết nối là đã xác thực. Client xử lý dữ liệu cuối của mechanism nếu đặc tả yêu cầu; việc một đối tượng thư viện báo hoàn thành một vòng nội bộ không thể thay thế phản hồi thành công từ server.
7. **Bắt đầu thao tác ứng dụng với quyền đã xác định.** Nếu mechanism thương lượng *SASL security layer* (không phải cơ chế nào cũng có), hai phía lắp lớp đó đúng thời điểm do giao thức quy định. Nếu không, kết nối tiếp tục dựa vào TLS hoặc lớp bảo vệ bên ngoài.

~~~text
Client                     Protocol server             SASL mechanism / verifier
  |--- TLS + capabilities ------->|                                |
  |<-- các mechanism -----------|                                |
  |--- chọn mechanism + data --->|------ validate/init --------->|
  |<-- challenge ---------------|<----- challenge ---------------|
  |--- response ---------------->|------ verify response ------->|
  |<-- SUCCESS/FAILURE ----------|<----- outcome -----------------|
  |--- lệnh ứng dụng ------------>|  (chỉ khi SUCCESS)             |
~~~

Số vòng và nội dung thông điệp thay đổi theo mechanism. Các khung `challenge`/`response` có thể được mã hóa Base64 khi đặt vào cú pháp văn bản của giao thức; **Base64 chỉ là biểu diễn dữ liệu, hoàn toàn không phải mã hóa bảo mật**.

## 4. Ví dụ dễ thấy: SMTP dùng SASL PLAIN qua TLS

Giả sử client đã thiết lập TLS an toàn tới máy chủ SMTP và kiểm tra tên máy chủ/chứng chỉ. Đoạn đối thoại dưới đây là **minh họa rút gọn**, dùng tài khoản giả `alice` và mật khẩu giả `secret`:

~~~text
S: 220 mail.example.test ESMTP ready
C: EHLO client.example.test
S: 250-mail.example.test
S: 250-AUTH PLAIN
S: 250 OK
C: AUTH PLAIN AGFsaWNlAHNlY3JldA==
S: 235 2.7.0 Authentication successful
~~~

Theo RFC 4616, phần dữ liệu logic của `PLAIN` có dạng:

~~~text
UTF-8(authzid)  0x00  UTF-8(authcid)  0x00  UTF-8(password)
~~~

Với `authzid` rỗng, `authcid=alice`, `password=secret`, chuỗi byte là `\0alice\0secret`. Chuỗi `AGFsaWNlAHNlY3JldA==` là Base64 của chính các byte ấy. Người nghe lén có thể giải mã Base64 rất dễ dàng; **PLAIN không bí mật hóa credential và không tự bảo vệ tính toàn vẹn**, vì vậy phải đặt trong kênh TLS phù hợp. Dữ liệu ví dụ chỉ để học, tuyệt đối không dùng tài khoản thật và không ghi credential/response vào log.

Điểm đáng chú ý: `EHLO` và `AUTH` thuộc **SMTP**, trong khi định nghĩa bố cục các byte `authzid/authcid/password` thuộc **SASL PLAIN**. Một giao thức khác có thể chở cùng mechanism nhưng dùng cú pháp lệnh hoàn toàn khác. Trong một phiên STARTTLS, việc chào ban đầu và đàm phán TLS có các bước riêng; phía client phải khám phá lại capabilities sau khi STARTTLS hoàn tất.

Nếu mật khẩu sai, server trả lỗi; nếu đúng mật khẩu nhưng yêu cầu hoạt động dưới danh tính không được phép, server vẫn phải từ chối. Hai tình huống này không đồng nghĩa.

## 5. Authentication identity khác authorization identity

- **Authentication identity (authcid):** danh tính gắn với bằng chứng xác thực, ví dụ `alice` chứng minh biết mật khẩu hoặc sở hữu vé Kerberos.
- **Authorization identity (authzid):** danh tính mà client đề nghị sử dụng quyền trong phiên, ví dụ `billing-agent`. Có thể bỏ trống để server chọn danh tính mặc định theo mechanism/chính sách.
- **Quyết định ủy quyền:** server phải kiểm tra liệu `alice` có được hoạt động như `billing-agent` hay không. Việc client tự khai `authzid=billing-agent` **không cấp quyền** cho client.

Ví dụ: một tác vụ tích hợp được xác thực là tài khoản dịch vụ `job-runner` và yêu cầu truy cập hộp thư với `authzid=alice`. Server cần chính sách delegation rõ ràng; nếu không có, trả thất bại cho yêu cầu đó. Sau khi SASL thành công, kiểm soát truy cập cụ thể (đọc thư nào, thao tác nào, giới hạn tài nguyên nào) vẫn là trách nhiệm của ứng dụng.

Đừng nhập nhằng ba khái niệm: **authentication** xác minh bằng chứng danh tính; **authorization identity mapping** xác định phiên hoạt động dưới danh tính nào; **authorization/permission checks** quyết định từng thao tác có được phép hay không.

## 6. Các mechanism phổ biến và ý nghĩa khi lựa chọn

| Mechanism | Bằng chứng/luồng chính | Lưu ý bảo mật và ứng dụng |
| --- | --- | --- |
| `PLAIN` | Gửi `authzid, authcid, password` (dạng byte) | Đơn giản, tương thích rộng; không có security layer. Dùng **chỉ qua kênh bảo vệ phù hợp**, thường TLS đã kiểm tra máy chủ. |
| `SCRAM-SHA-256` | Challenge/response dựa trên nonce, salt, phép dẫn xuất khóa và proof; có xác nhận máy chủ | Không gửi mật khẩu thô trên dây; vẫn cần thiết kế TLS/chính sách chống MITM và chống dò mật khẩu, quản lý verifier an toàn. RFC 5802/7677. |
| `SCRAM-SHA-256-PLUS` | SCRAM-SHA-256 cộng *channel binding* với kênh bảo mật bên ngoài | Ràng buộc chứng minh xác thực với kênh TLS đã dùng, nhằm giảm một số kiểu chuyển tiếp/MITM; hai bên phải hỗ trợ loại channel binding tương thích. |
| `GSSAPI` | Trao đổi token của GSS-API, thường dựa trên Kerberos | Phù hợp môi trường Kerberos/SSO; cần cấu hình principal, service name và credential đúng; có thể thương lượng mức bảo vệ sau xác thực. |
| `EXTERNAL` | Sử dụng danh tính đã xác thực bởi lớp hoặc ngữ cảnh bên ngoài, ví dụ TLS client certificate | Server phải ánh xạ và xác nhận danh tính bên ngoài đáng tin; SASL không tự thay thế bước xác minh chứng chỉ. |
| `OAUTHBEARER` | Đưa OAuth 2.0 bearer token vào trao đổi SASL | Phụ thuộc TLS, hạn token và kiểm tra issuer/audience/expiry/scope phù hợp; token bị lộ có thể bị sử dụng bởi bên khác. RFC 7628. |

Không nên chọn `CRAM-MD5` hoặc `DIGEST-MD5` cho thiết kế mới chỉ vì một JDK/provider cũ có hỗ trợ; đây là các lựa chọn lịch sử, không phải mặc định bảo mật hiện đại. Một hệ thống phải dựa vào **cơ chế được hỗ trợ thực tế**, khả năng client/server và chính sách bảo mật, không suy ra “SASL tự động hỗ trợ mọi mechanism”.

### SCRAM có gì khác với việc gửi password?

Trong SCRAM, client và server trao đổi nonce, salt, số vòng dẫn xuất và các proof/signature theo cơ chế chuẩn. Server kiểm tra bằng chứng rằng client biết mật khẩu mà client **không truyền mật khẩu thô** trong thông điệp SCRAM; client còn có dữ liệu để xác nhận server. Phần handshake rút gọn:

~~~text
C → S: tên user + client nonce
S → C: nonce kết hợp + salt + iteration count
C → S: client proof (và dữ liệu channel binding nếu có)
S → C: server signature hoặc thông báo thất bại
~~~

Đây là **sơ đồ khái niệm**, không phải chuỗi byte đủ để tự triển khai SCRAM. SCRAM-SHA-256 sử dụng quy tắc chi tiết của RFC 5802 và RFC 7677; biến thể `-PLUS` cần channel binding đúng với phiên bảo mật, kể cả các yêu cầu tương thích TLS hiện hành. Không tự viết thuật toán SCRAM từ bản tóm tắt này. SCRAM **không** tự cung cấp security layer mã hóa cho dữ liệu ứng dụng; dùng TLS hoặc một lớp bảo vệ phù hợp. Salt và phép dẫn xuất khóa giảm một số nguy cơ nhưng không loại bỏ hoàn toàn việc đoán mật khẩu ngoại tuyến khi thông tin verifier bị lộ.

### GSSAPI nằm ở đâu?

`GSSAPI` là **một mechanism SASL**, không phải tên khác của SASL. Khi dùng GSSAPI, giao thức mang các token xác thực GSS-API; GSS-API và cơ chế bên dưới (phổ biến là Kerberos) xử lý thông tin phiên và bằng chứng. SASL chuẩn hóa việc nhúng trao đổi đó vào giao thức ứng dụng. Chi tiết về ticket, service principal, keytab và ngữ nghĩa mutual authentication thuộc phần tìm hiểu GSS-API/Kerberos riêng.

## 7. SASL, TLS và phân quyền bổ sung nhau như thế nào?

| Lớp | Trả lời câu hỏi | Không tự đảm nhận |
| --- | --- | --- |
| **TLS** | Dữ liệu trên kết nối được bảo mật và peer phía máy chủ được xác thực theo chính sách TLS hay chưa? | Không mặc nhiên xác định người dùng ứng dụng; TLS client certificate chỉ là một khả năng nếu được cấu hình. |
| **SASL mechanism** | Client chứng minh danh tính gì, theo phương pháp nào, và mechanism có tạo security layer hay không? | Không định nghĩa nghiệp vụ, cú pháp lệnh của mọi giao thức hoặc quyền tới từng tài nguyên. |
| **Giao thức ứng dụng** | Gọi SASL lúc nào, chuyển challenge/response ra sao, báo kết quả bằng lệnh nào? | Không nên tự chế lại thuật toán xác thực. |
| **Authorization tại server** | Danh tính đã xác thực được phép hành động như ai và làm gì? | Không thể dựa hoàn toàn vào tên `authzid` do client khai. |

SASL có khái niệm **security layer tùy chọn**: tùy mechanism và thương lượng, lớp này có thể bảo vệ tính toàn vẹn hoặc cả bí mật của những thông điệp *sau xác thực*. Ví dụ các mức `auth`, `auth-int`, `auth-conf` thường được nhắc khi một mechanism có hỗ trợ QOP. **Không phải mọi mechanism có đủ ba mức**: `PLAIN` và `SCRAM-SHA-256` không cung cấp SASL security layer, trong khi một số cấu hình `GSSAPI` có thể hỗ trợ. Nếu không thương lượng lớp đó, kết nối vẫn có thể được TLS bảo vệ bình thường.

Vì TLS và SASL nằm ở các tầng khác nhau, việc “đã đăng nhập bằng SASL” **không chứng minh rằng đường truyền an toàn**, và việc “đã kết nối TLS” **không chứng minh rằng client đã đăng nhập tài khoản ứng dụng**.

## 8. Java 17+: dùng API `javax.security.sasl`

Java cung cấp các giao diện trong module `java.security.sasl`:

- `Sasl.createSaslClient(...)` / `Sasl.createSaslServer(...)` tìm factory theo mechanism đã đăng ký với security provider; có thể trả `null` nếu không tìm được implementation phù hợp.
- `SaslClient` cung cấp `hasInitialResponse()`, `evaluateChallenge(byte[])`, `isComplete()`, `getNegotiatedProperty(...)`, `wrap(...)`, `unwrap(...)` và `dispose()`.
- `SaslServer` nhận response bằng `evaluateResponse(byte[])`, đưa kết quả về phía giao thức và cho phép lấy danh tính ủy quyền sau khi hoàn tất theo hợp đồng API.
- `CallbackHandler` cung cấp thông tin mà mechanism yêu cầu, chẳng hạn `NameCallback` và `PasswordCallback`. Callback được yêu cầu khác nhau giữa các mechanism; không phải cái nào cũng dùng mật khẩu.

### Ví dụ chạy độc lập: tạo initial response cho PLAIN

Ví dụ này **không mở kết nối mạng và không đăng nhập SMTP thật**. Nó chỉ cho thấy một ứng dụng Java giao dữ liệu credential cho SASL client để mechanism tạo *initial response*. Trong sản phẩm thật, chỉ kích hoạt PLAIN **sau khi TLS của phiên đã được xác thực**, không in credential hay payload ra log. Mật khẩu ở đây là chuỗi giả phục vụ học tập.

~~~java
// File: SaslPlainDemo.java
import java.util.Base64;
import java.util.Map;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.sasl.Sasl;
import javax.security.sasl.SaslClient;

public class SaslPlainDemo {
    public static void main(String[] args) throws Exception {
        CallbackHandler callbacks = requested -> {
            for (Callback callback : requested) {
                if (callback instanceof NameCallback name) {
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword("secret".toCharArray());
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        SaslClient client = Sasl.createSaslClient(
                new String[] {"PLAIN"},
                null,                     // authzid: không yêu cầu danh tính khác
                "smtp",                   // tên dịch vụ/giao thức
                "mail.example.test",      // máy chủ đích của dịch vụ
                Map.of(),
                callbacks);

        if (client == null) {
            throw new IllegalStateException("Không có SASL PLAIN client provider");
        }

        try {
            if (!client.hasInitialResponse()) {
                throw new IllegalStateException("Demo cần initial response");
            }
            byte[] response = client.evaluateChallenge(new byte[0]);
            System.out.println("mechanism=" + client.getMechanismName());
            System.out.println("payloadBase64=" + Base64.getEncoder().encodeToString(response));
            System.out.println("clientComplete=" + client.isComplete());
        } finally {
            client.dispose();
        }
    }
}
~~~

Chạy trên JDK có SASL PLAIN client provider (ví dụ triển khai SunSASL trong OpenJDK/JDK phổ biến):

~~~bash
javac SaslPlainDemo.java
java SaslPlainDemo
~~~

Đầu ra dự kiến của provider PLAIN tương thích RFC 4616:

~~~text
mechanism=PLAIN
payloadBase64=AGFsaWNlAHNlY3JldA==
clientComplete=true
~~~

Ý nghĩa của `clientComplete=true`: SASL client đã tạo xong dữ liệu theo **mechanism PLAIN**; **chưa có server nào xác nhận** trong demo này. Ứng dụng thật phải đưa `response` vào lệnh xác thực của giao thức, đọc kết quả server và chỉ cập nhật trạng thái phiên sau phản hồi thành công. Ví dụ cố ý in payload để quan sát byte format; mã sản xuất phải xóa việc in này, nhận credential từ kho bí mật phù hợp và xử lý vòng đời credential cẩn thận. Cơ chế PLAIN phía server cũng phải thực hiện kiểm tra credential và quyền; gọi `SaslClient` đơn độc không tạo ra hệ thống xác thực đầy đủ.

### Khi tích hợp vào giao thức thật

Phần mềm ứng dụng/driver chịu trách nhiệm:

1. Xác minh TLS, nhận danh sách mechanism server **trên kết nối hiện tại** và lọc theo chính sách bảo mật.
2. Tạo `SaslClient` với mechanism đã chọn; nếu `null`, xử lý thiếu provider, không âm thầm chuyển sang cơ chế yếu.
3. Nếu `hasInitialResponse()`, gọi `evaluateChallenge(new byte[0])` rồi đóng gói vào lệnh mở đầu đúng theo giao thức; nếu không, chờ challenge từ server.
4. Lặp trao đổi challenge/response cho đến khi giao thức báo thành công, thất bại hoặc bị hủy; mỗi message cần được chuyển đổi/framing theo quy định của protocol (ví dụ Base64 nếu protocol yêu cầu).
5. Kiểm tra kết quả cuối, chỉ xác lập phiên đăng nhập khi server xác nhận và các điều kiện về security layer, identity, authorization đều đúng; giải phóng client bằng `dispose()` khi kết thúc.

**Quan trọng:** `SaslClient`/`SaslServer` **không tự mở socket, thực hiện TLS hay gửi SMTP/LDAP command**. Nhiều driver Java đã tích hợp phần giao thức; khi dùng driver đó, nên cấu hình cơ chế mạnh và TLS của driver thay vì tự viết một giao thức mới chỉ để gọi SASL.

## 9. Checklist bảo mật cho một triển khai SASL

- **Không downgrade.** Client phải có policy về mechanism tối thiểu chấp nhận được; đối chiếu capabilities ở đúng thời điểm, chống thay đổi trước/sau nâng cấp TLS và xử lý các trường hợp channel binding bị hạ cấp.
- **Xác thực máy chủ và kênh.** Bật TLS theo cấu hình phù hợp, kiểm tra chứng chỉ/tên máy chủ; không gửi `PLAIN` hoặc `OAUTHBEARER` qua kết nối không được bảo vệ. Với Kerberos, xác định đúng service principal.
- **Phân biệt danh tính và quyền.** Kiểm tra ánh xạ `authcid → authzid` trên server; xác thực thành công không đồng nghĩa mọi thao tác được phép.
- **Bảo vệ bí mật.** Không log password, bearer token, challenge/response nhạy cảm; bảo vệ kho credential/verifier/keytab; làm sạch/giới hạn lưu trữ dữ liệu nhạy cảm khi khả thi.
- **Giới hạn tài nguyên và lỗi.** Chặn brute force/rate-limit theo ngữ cảnh, giới hạn kích thước thông điệp, số vòng, thời gian, và số lần thử; không tiết lộ thông tin giúp liệt kê tài khoản qua nội dung lỗi.
- **Kiểm tra trạng thái.** Nếu exchange thất bại, timeout hoặc kết nối ngắt, không cấp quyền; kiểm tra hành vi khi xác thực lại và khi security layer thay đổi theo đặc tả giao thức.
- **Không tự triển khai mật mã.** Dùng mechanism/provider và thư viện được duy trì; kiểm tra cấu hình và khả năng thực tế của cả client/server. Cần rà soát riêng chính sách với chuẩn, thuật toán và yêu cầu tổ chức.

## 10. Những hiểu nhầm cần tránh

**“Dùng SASL là tự động có mã hóa.”** Sai: SASL có thể chỉ làm authentication. `PLAIN` truyền password dưới dạng có thể khôi phục; `SCRAM-SHA-256` không cung cấp confidentiality cho dữ liệu ứng dụng.

**“Cứ Base64 là password được bảo vệ.”** Sai: Base64 biến đổi biểu diễn để đặt byte vào protocol; bất kỳ ai nhận được byte đều có thể giải mã.

**“Client.isComplete() nghĩa là login thành công.”** Sai: đó là trạng thái hoàn tất của đối tượng SASL client theo mechanism. Thành công của cả kết nối phải dựa vào phản hồi xác thực phía server của giao thức.

**“Có authzid là có quyền mạo danh tài khoản khác.”** Sai: authzid là yêu cầu; server quyết định có ủy quyền hành động dưới danh tính đó hay không.

**“SASL bắt buộc challenge/response nhiều vòng.”** Sai: `PLAIN` có thể dùng một initial response; SCRAM/GSSAPI thường có nhiều thông điệp.

**“SASL và GSS-API là một.”** Sai: SASL là framework nhúng authentication vào giao thức; `GSSAPI` là một mechanism sử dụng dịch vụ GSS-API (thường Kerberos).

## 11. Tình huống tự kiểm tra

1. Server SMTP công bố `PLAIN` và `SCRAM-SHA-256`. Client chưa xác minh TLS. Có nên gửi initial response `PLAIN` ngay không? **Không.** Trước hết bảo vệ/xác minh kênh; chọn mechanism đạt policy. Mặc dù SCRAM không gửi mật khẩu thô, vẫn phải xét TLS và MITM/channel binding.
2. Người dùng `alice` xác thực thành công nhưng yêu cầu `authzid=admin` mà không có quyền delegation. Server nên làm gì? **Từ chối yêu cầu xác thực/ủy quyền đó**, không để session hoạt động như `admin`.
3. Java in `clientComplete=true` nhưng server trả “authentication failed”. Trạng thái phiên là gì? **Chưa xác thực**. Dữ liệu từ `SaslClient` là một phần trao đổi, không thay được kết quả server.
4. Một giao thức chuyển từ `PLAIN` sang `GSSAPI`. Có bắt buộc thay toàn bộ lệnh nghiệp vụ? **Không.** Phần SASL integration vẫn chuyển challenge/response và nhận outcome, nhưng mechanism, số vòng, cấu hình identity và security policy thay đổi.
5. Đã bật TLS, vậy còn cần SASL không? **Có thể vẫn cần**, nếu ứng dụng phải xác định account/authorization identity. TLS phía server thường chứng minh máy chủ, không tự xác thực tài khoản người dùng.

## 12. Tài liệu chuẩn để tra cứu

- **RFC 4422 — Simple Authentication and Security Layer (SASL):** https://www.rfc-editor.org/rfc/rfc4422
- **RFC 4616 — PLAIN SASL Mechanism:** https://www.rfc-editor.org/rfc/rfc4616
- **RFC 5802 — SCRAM SASL and GSS-API Mechanisms:** https://www.rfc-editor.org/rfc/rfc5802
- **RFC 7677 — SCRAM-SHA-256 and SCRAM-SHA-256-PLUS:** https://www.rfc-editor.org/rfc/rfc7677
- **RFC 7628 — SASL Mechanisms for OAuth:** https://www.rfc-editor.org/rfc/rfc7628
- **Java SE 21 API — `Sasl`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html

**Ghi nhớ:** SASL tạo một hợp đồng tích hợp giữa *giao thức ứng dụng* và *cơ chế xác thực có thể thay thế*. Sự an toàn của phiên đến từ cách chọn mechanism, xác minh kênh, kiểm tra credential, ánh xạ danh tính, áp dụng quyền và chỉ chấp nhận kết quả cuối của server.