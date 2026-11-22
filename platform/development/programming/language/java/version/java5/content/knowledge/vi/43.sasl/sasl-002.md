# Vai trò SaslClient và SaslServer

## 1. Hai phía của một cuộc trao đổi xác thực

SASL (Simple Authentication and Security Layer) cung cấp cách ghép cơ chế xác thực vào một giao thức ứng dụng. Thay vì để thư viện giao thức tự viết từng thuật toán xác thực, nó chuyển dữ liệu của cuộc trao đổi cho thành phần thực hiện cơ chế SASL đã chọn.

Trong Java:

- `SaslClient` giữ trạng thái xác thực ở phía đưa thông tin/bằng chứng xác thực và tạo phản hồi.
- `SaslServer` giữ trạng thái ở phía kiểm tra phản hồi, tạo thử thách khi cần và xác định danh tính được phép sử dụng sau khi xác thực.

Đây là **vai trò trong cuộc trao đổi xác thực**, không phải toàn bộ chương trình client/server. `SaslServer` không tự mở cổng lắng nghe; `SaslClient` không tự kết nối mạng. Một dịch vụ có thể đóng vai server khi nhận yêu cầu, đồng thời có một client SASL khác khi gọi sang dịch vụ tiếp theo.

Khung SASL phân biệt cơ chế xác thực với cách giao thức vận chuyển nó; xem [RFC 4422](https://www.rfc-editor.org/rfc/rfc4422.html). Bài học dùng các hợp đồng API vẫn áp dụng trên Java hiện đại, không dùng cơ chế xác thực đã lỗi thời làm mẫu.

## 2. Đặt hai đối tượng vào đúng vị trí

```text
Ứng dụng phía client                          Ứng dụng phía server
        │                                              │
Thư viện giao thức                             Bộ xử lý giao thức
        │                                              │
    SaslClient                                     SaslServer
 evaluateChallenge()                             evaluateResponse()
        │                                              │
        └── phản hồi / thử thách qua giao thức ─────────┘
```

Các byte giữa hai phía có thể được đóng khung hoặc mã hóa biểu diễn theo giao thức ứng dụng. Ví dụ, một giao thức có thể biểu diễn token bằng Base64; việc này không làm token trở thành bí mật và không tự tạo mã hóa đường truyền.

| Khía cạnh | SaslClient | SaslServer |
| --- | --- | --- |
| Đầu vào của bước cơ chế | Thử thách từ server | Phản hồi từ client |
| Phương thức xử lý | `evaluateChallenge(byte[])` | `evaluateResponse(byte[])` |
| Đầu ra của bước cơ chế | Phản hồi gửi về server, hoặc không cần gửi tiếp | Thử thách/dữ liệu cuối gửi về client, hoặc không còn dữ liệu |
| Trạng thái hoàn tất cục bộ | `isComplete()` | `isComplete()` |
| Danh tính dùng sau xác thực | Theo kết quả giao thức và ngữ cảnh ứng dụng | `getAuthorizationID()` sau khi hoàn tất |
| Lớp bảo vệ dữ liệu nếu cơ chế thương lượng được | `wrap()`, `unwrap()` | `wrap()`, `unwrap()` |
| Dọn tài nguyên | `dispose()` | `dispose()` |

Hai đối tượng không phải bản sao dùng chung. Mỗi bên giữ trạng thái riêng và chỉ nhìn thấy dữ liệu mà giao thức chuyển tới nó. Một đối tượng thường gắn với một cuộc trao đổi; không chia sẻ nó cho nhiều phiên xác thực đồng thời.

## 3. SaslClient: xử lý thử thách và tạo bằng chứng

Thư viện phía client tạo `SaslClient` với cơ chế được phép dùng, danh tính được yêu cầu nếu có, tên giao thức, tên server, thuộc tính và `CallbackHandler`.

Client chịu trách nhiệm:

1. Tham gia lựa chọn một cơ chế mà cả hai phía và chính sách cục bộ chấp nhận.
2. Tạo thông điệp đầu nếu cơ chế/giao thức hỗ trợ phản hồi ban đầu.
3. Với mỗi thử thách hợp lệ nhận được, gọi `evaluateChallenge()` để tạo phản hồi tiếp theo.
4. Theo dõi trạng thái cục bộ đồng thời đọc kết quả thành công/thất bại do giao thức báo.
5. Sau xác thực, dùng lớp bảo vệ dữ liệu chỉ khi thực sự đã thương lượng được.

Nếu `hasInitialResponse()` trả `true`, có thể lấy phản hồi ban đầu bằng `evaluateChallenge(new byte[0])` khi quy tắc của giao thức cho phép. Không mặc định mọi cơ chế đều phải đợi server gửi một chuỗi thử thách không rỗng. Ngược lại, giao thức không có chỗ gửi phản hồi ngay trong lệnh khởi đầu có thể cần một bước trao đổi khác.

`evaluateChallenge()` nhận một mảng byte không null, có thể rỗng. Giá trị trả về có thể là `null` khi không cần gửi phản hồi tiếp, hoặc là mảng rỗng khi cần gửi một phản hồi có độ dài bằng 0. Hai trường hợp đó phải được ánh xạ đúng theo giao thức. Xem [SaslClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html).

Thông tin mà callback phía client cung cấp tùy cơ chế: có thể là tên xác thực, mật khẩu, realm hoặc dữ liệu khác. Không phải cơ chế nào cũng yêu cầu mật khẩu; không nên thiết kế wrapper buộc mọi phương thức xác thực phải có cùng bộ username/password.

## 4. SaslServer: đánh giá phản hồi và xác lập danh tính

Phía server tạo một `SaslServer` cho cơ chế client đã yêu cầu và server cho phép. Server chuyển phản hồi nhận được vào `evaluateResponse()`.

Đầu ra có thể là:

- Thử thách tiếp theo vì cuộc trao đổi chưa xong.
- Dữ liệu cuối cần client xử lý dù phía server đã hoàn tất.
- `null` khi không còn dữ liệu thử thách cần gửi sau thành công.

Vì vậy, không được dùng riêng điều kiện `challenge == null` để thay cho toàn bộ logic kết thúc. Phải kiểm tra `isComplete()` sau bước đánh giá và phát kết quả theo giao thức. Xem [SaslServer](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html).

Một trình tự khái niệm:

```text
Nhận tên cơ chế và phản hồi ban đầu nếu có
    ↓
Tạo SaslServer cho đúng cơ chế và chính sách
    ↓
evaluateResponse(response)
    ├── chưa hoàn tất: gửi thử thách và đợi phản hồi
    ├── hoàn tất: gửi kết quả thành công kèm dữ liệu cuối nếu có
    └── lỗi: báo thất bại, không tạo phiên đã xác thực
```

Thành phần SASL thực hiện cơ chế, nhưng ứng dụng/provider vẫn cần nguồn thông tin tin cậy và chính sách cấp quyền. `SaslServer` không tự biến một tên do client khai thành danh tính đã được chứng minh.

Nếu một bước ném `SaslException`, ứng dụng cần hủy cuộc trao đổi hiện tại, dọn tài nguyên và báo lỗi theo giao thức. Không bắt lỗi rồi gán trạng thái “đã đăng nhập” để tiếp tục.

## 5. isComplete() của client chưa thay thế xác nhận từ server

Hai phía có thể hoàn tất phần tính toán cục bộ ở các thời điểm khác nhau. Một cơ chế có thể cho phép client tạo thông điệp cuối rồi tự báo hoàn tất, trong khi server vẫn chưa đánh giá hoặc chưa chấp nhận thông điệp đó.

Do đó:

```text
client.isComplete() == true
không tự suy ra
server đã xác thực thành công và giao thức đã báo SUCCESS
```

Phía client chỉ chuyển sang trạng thái phiên đã xác thực khi kết quả giao thức và trạng thái cơ chế đáp ứng đầy đủ hợp đồng. Nếu kết quả thành công mang dữ liệu cuối để xác minh, phải xử lý dữ liệu đó theo cơ chế và quy tắc giao thức.

Ở chiều ngược lại, server vừa hoàn tất cũng có thể còn dữ liệu cuối phải chuyển cho client. Không bỏ dữ liệu ấy chỉ vì `server.isComplete()` đã là `true`.

Không viết một vòng lặp chung kiểu “client tạo response, server tạo challenge, tới khi một bên complete thì dừng” rồi coi nó đúng cho mọi giao thức. Vòng điều phối phải biết ai được gửi tiếp, cách biểu diễn phản hồi ban đầu, kết quả thành công/thất bại và dữ liệu cuối.

Trong ứng dụng thật, client và server thường không nằm cùng tiến trình. Thư viện giao thức mới là nơi đọc/ghi và gắn trạng thái SASL với trạng thái kết nối.

## 6. Authentication ID và authorization ID khác nhau thế nào?

Hai danh tính cần phân biệt:

- **Danh tính xác thực (authentication ID)**: thực thể đã chứng minh danh tính bằng cơ chế được chọn.
- **Danh tính được phép sử dụng (authorization ID)**: danh tính mà phiên muốn hoạt động dưới tên đó.

Ví dụ tài khoản `alice` đã xác thực nhưng yêu cầu hoạt động dưới danh tính `bob`. Việc biết thông tin xác thực của `alice` không tự cấp quyền làm `bob`.

Với cơ chế/provider dùng `AuthorizeCallback`, callback phía server phải quyết định liệu danh tính đã xác thực có được thay mặt danh tính được yêu cầu hay không. Chỉ chấp nhận khi chính sách cho phép; không gọi `setAuthorized(true)` vô điều kiện. Xem [AuthorizeCallback](https://docs.oracle.com/en/java/javase/26/docs/api/java.security.sasl/javax/security/sasl/AuthorizeCallback.html).

Sau khi `SaslServer.isComplete()` là `true`, server có thể đọc `getAuthorizationID()` để lấy danh tính có hiệu lực của phiên. Không gọi trước khi hoàn tất và không lấy trực tiếp tên do client gửi để thay thế kết quả đó.

Danh tính phiên cũng chưa phải toàn bộ quyền nghiệp vụ. Ví dụ, phiên hoạt động dưới tên `alice` vẫn phải đi qua kiểm tra quyền đọc tài liệu hoặc sửa đơn hàng tại tầng ứng dụng.

### Ví dụ chạy được: chính sách chỉ cho dùng chính danh tính đã xác thực

Chương trình sau kiểm tra một `CallbackHandler` phía server. Nó không thực hiện một cơ chế SASL hay xác thực mật khẩu; hai chuỗi đầu vào là dữ liệu kiểm thử cho **bước quyết định quyền sử dụng danh tính**.

Trong tích hợp thật, phải lấy danh tính xác thực từ quá trình xác thực đáng tin cậy của provider, không từ trường tùy ý do client gửi lên.

Lưu thành `AuthorizationPolicyDemo.java`:

```java
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.sasl.AuthorizeCallback;

public class AuthorizationPolicyDemo {
    static final CallbackHandler POLICY = callbacks -> {
        for (Callback callback : callbacks) {
            if (!(callback instanceof AuthorizeCallback auth)) {
                throw new UnsupportedCallbackException(callback);
            }
            // Chi cho phep dung chinh danh tinh da duoc xac thuc.
            auth.setAuthorized(auth.getAuthenticationID()
                    .equals(auth.getAuthorizationID()));
        }
    };

    static boolean check(String authenticated, String requested)
            throws Exception {
        AuthorizeCallback decision =
                new AuthorizeCallback(authenticated, requested);
        POLICY.handle(new Callback[] { decision });
        return decision.isAuthorized();
    }

    public static void main(String[] args) throws Exception {
        System.out.println("alice -> alice: " + check("alice", "alice"));
        System.out.println("alice -> bob: " + check("alice", "bob"));
    }
}
```

Chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 AuthorizationPolicyDemo.java
java AuthorizationPolicyDemo
```

Hoặc chạy tệp nguồn trực tiếp:

```shell
java AuthorizationPolicyDemo.java
```

Kết quả:

```text
alice -> alice: true
alice -> bob: false
```

Chính sách mẫu cố ý chỉ cho phép cùng một danh tính; hệ thống hỗ trợ ủy quyền cần quy tắc cụ thể hơn. Nếu môi trường cần chuẩn hóa tên/realm, phải xác định quy tắc chuẩn hóa đáng tin cậy trước khi so sánh. Không tự dùng so sánh bỏ qua hoa/thường hoặc cắt phần realm mà không có hợp đồng định danh.

Handler chỉ hỗ trợ `AuthorizeCallback`; callback không hỗ trợ được báo rõ bằng `UnsupportedCallbackException`. Khi ghép với một cơ chế thực, phải xử lý đúng các callback mà cơ chế ấy yêu cầu, không bỏ qua chúng âm thầm.

## 7. Tạo client/server: cùng tên cơ chế chưa đủ

Hai factory có hình dạng khác nhau:

```java
SaslClient client = Sasl.createSaslClient(
        allowedMechanisms, authorizationId,
        protocol, serverName, properties, clientCallbacks);

SaslServer server = Sasl.createSaslServer(
        selectedMechanism,
        protocol, serverName, properties, serverCallbacks);
```

Đây là đoạn tích hợp, không phải chương trình chạy độc lập; các biến phải được lấy từ cấu hình và cuộc trao đổi giao thức đã kiểm tra.

Client nhận một danh sách cơ chế có thể lựa chọn, trong khi server được tạo cho một cơ chế cụ thể. Provider cài trong môi trường quyết định triển khai nào có thể được tạo. Cả hai hàm có thể trả `null` khi không tìm được factory tạo đối tượng phù hợp, hoặc ném `SaslException` khi có lỗi. Phải kiểm tra trước khi gọi phương thức trên đối tượng. Xem [Sasl: factory và thuộc tính](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html).

Những điểm cần kiểm tra ở cả hai phía:

- Cơ chế có được giao thức, server và chính sách client cho phép không?
- Provider có hỗ trợ **đúng vai trò** không? Có client cho một tên cơ chế không bảo đảm có server cùng tên.
- Tham số `protocol` là tên dịch vụ/giao thức theo cơ chế, không phải tự động là chuỗi `"TLS"`.
- `serverName` phải đúng ngữ cảnh dịch vụ mà cơ chế yêu cầu; truyền tên này không tự mở hay xác thực kết nối mạng.
- Callback và thông tin xác thực có phù hợp cơ chế không?
- Thuộc tính chính sách và chất lượng bảo vệ có tương thích không?

Một cơ chế được chuẩn hóa cũng không có nghĩa mọi bản JDK đều cài sẵn nó. Ví dụ, [SCRAM-SHA-256 được định nghĩa trong RFC 7677](https://www.rfc-editor.org/rfc/rfc7677.html), nhưng vẫn cần kiểm tra triển khai/provider thực tế của hệ thống thay vì suy ra từ tên API Java.

Không tự hạ xuống cơ chế yếu hơn khi không tìm được cơ chế được phép. Nhánh “không hỗ trợ” phải trở thành lỗi cấu hình/thương lượng rõ ràng.

## 8. Hai phía có thể tiếp tục bảo vệ dữ liệu sau xác thực

Tên SASL có phần “Security Layer”, nhưng không phải mọi cơ chế hoặc mọi cuộc thương lượng đều tạo lớp bảo vệ dữ liệu.

Sau khi hoàn tất, đọc `getNegotiatedProperty(Sasl.QOP)` theo hợp đồng cơ chế:

| QOP | Ý nghĩa |
| --- | --- |
| `auth` | Xác thực; không tạo lớp toàn vẹn/bí mật dữ liệu SASL |
| `auth-int` | Xác thực và bảo vệ tính toàn vẹn |
| `auth-conf` | Xác thực, bảo vệ toàn vẹn và bí mật |

Chỉ dùng `wrap()`/`unwrap()` của `SaslClient` hoặc `SaslServer` khi đã hoàn tất và đã thương lượng một lớp bảo vệ phù hợp. Không gọi chúng chỉ vì thấy API có phương thức này. Không suy ra SASL luôn mã hóa dữ liệu, cũng không suy ra nó tự thay thế TLS.

Nếu dùng TLS bên ngoài SASL, thư viện kết nối phải thiết lập và xác thực TLS đúng trước khi dựa vào các thuộc tính bảo vệ của nó. Những yêu cầu gắn xác thực với kênh truyền, nếu cơ chế/giao thức có, cũng phải được tích hợp theo tài liệu tương ứng; không tự coi mọi cặp SASL + TLS đều có cùng đặc tính.

Ứng dụng còn chịu trách nhiệm đóng khung các khối dữ liệu được bọc, giới hạn kích thước và giữ thứ tự. `wrap()` không tự ghi socket; `unwrap()` không tự đọc socket.

## 9. Vòng đời và lỗi thường gặp

Một vòng đời điển hình:

```text
Tạo đối tượng cho một cuộc trao đổi
    ↓
Chuyển từng thử thách/phản hồi đúng thứ tự
    ↓
Hoàn tất + kết quả giao thức phù hợp
    ↓
Gắn danh tính được phép với phiên ứng dụng
    ↓
Nếu có security layer: tiếp tục dùng đối tượng cho wrap/unwrap
    ↓
dispose khi không còn cần
```

Nếu chỉ dùng xác thực và không còn cần đối tượng, có thể dọn nó sau khi đã giữ thông tin phiên cần thiết. Nếu dùng lớp bảo vệ SASL, phải giữ đối tượng trong suốt thời gian lớp bảo vệ ấy còn hoạt động rồi mới `dispose()`. `dispose()` giải phóng tài nguyên/dữ liệu nhạy cảm của đối tượng; nó không tự đóng kết nối mạng hay hủy phiên nghiệp vụ bên ngoài.

| Lỗi | Vì sao sai |
| --- | --- |
| Dùng một đối tượng cho nhiều phiên cùng lúc | Trạng thái thử thách/phản hồi bị trộn |
| Gọi evaluateResponse trên client | Nhầm API và vai trò; client xử lý challenge |
| Đánh dấu đăng nhập khi chỉ client.isComplete() | Chưa kiểm tra kết quả xác thực của giao thức |
| Bỏ dữ liệu cuối vì server đã complete | Client có thể còn phải xác minh hoặc cập nhật trạng thái |
| Gộp null và mảng byte rỗng | Mất ý nghĩa “không gửi thông điệp” so với “gửi thông điệp rỗng” |
| Chấp nhận mọi authorization ID | Cho phép mạo danh dù xác thực đúng một tài khoản khác |
| Cho rằng provider hỗ trợ cả hai vai trò | Factory client và server là hai khả năng riêng |
| Log toàn bộ token/callback mật khẩu | Làm lộ dữ liệu xác thực hoặc bằng chứng nhạy cảm |
| Xác thực xong thì wrap vô điều kiện | Chưa chắc có lớp bảo vệ dữ liệu được thương lượng |

Các bài tập kiểm tra vai trò:

1. Một thành phần nhận challenge từ mạng phải gọi phương thức nào? **Client gọi evaluateChallenge; nó không chuyển challenge ấy trực tiếp cho evaluateResponse.**
2. Một server hoàn tất nhưng trả dữ liệu cuối khác null phải làm gì? **Gửi kết quả và dữ liệu cuối đúng hợp đồng giao thức.**
3. Người dùng đã chứng minh là alice nhưng yêu cầu authzid=bob cần bước gì? **Kiểm tra chính sách cho phép thay mặt bob; xác thực alice là chưa đủ.**
4. QOP là auth thì có được xem SASL là lớp mã hóa thông điệp không? **Không; phải dựa vào lớp bảo vệ đã thiết lập thực tế của hệ thống.**
