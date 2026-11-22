# SASL và cơ chế xác thực độc lập giao thức ứng dụng

## 1. Bài toán: nhiều giao thức cùng cần xác thực

Một máy khách truy cập hộp thư, một ứng dụng truy vấn thư mục và một dịch vụ kết nối hệ thống nhắn tin có định dạng lệnh khác nhau. Tuy vậy, chúng đều cần trả lời câu hỏi: **đối tác đang kết nối là ai và có được dùng danh tính yêu cầu hay không?**

Nếu mỗi giao thức tự thiết kế toàn bộ cách trao đổi thông tin xác thực, khi thêm phương thức đăng nhập mới sẽ phải sửa nhiều tầng cùng lúc. SASL giải quyết phần phân chia này.

**SASL (Simple Authentication and Security Layer)** là một khung để tích hợp các cơ chế xác thực có thể thay thế vào giao thức ứng dụng hướng kết nối. Một số cơ chế còn thương lượng lớp bảo vệ cho dữ liệu sau xác thực.

SASL không phải tên của một thuật toán mật khẩu, một cơ sở dữ liệu người dùng hay một giao thức mã hóa vận chuyển. Nói “hệ thống dùng SASL” vẫn chưa đủ để biết nó dùng chứng thư, mật khẩu, vé Kerberos hay token.

Khái niệm khung và quan hệ với cơ chế được quy định trong [RFC 4422](https://www.rfc-editor.org/rfc/rfc4422.html), đặc tả nền tảng thay thế RFC SASL trước đó.

## 2. Ba phần phải phân biệt

| Phần | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| Giao thức ứng dụng và phần tích hợp SASL | Chào danh sách cơ chế, mở trao đổi xác thực, vận chuyển dữ liệu, báo thành công/thất bại | LDAP Bind, luồng xác thực của IMAP |
| Khung SASL | Giao diện chung giữa giao thức và cơ chế | Cơ chế được chọn theo tên; trao đổi các khối dữ liệu xác thực |
| Cơ chế SASL | Ý nghĩa và cách tạo/kiểm tra dữ liệu xác thực | SCRAM-SHA-256, EXTERNAL, OAUTHBEARER |

Có thể hình dung:

```text
Lệnh và phản hồi của giao thức ứng dụng
                 |
       Phần tích hợp với SASL
                 |
      Cơ chế xác thực được chọn
                 |
   Thông tin xác thực / nguồn danh tính
```

“Độc lập giao thức ứng dụng” nghĩa là cùng một cơ chế có thể được tích hợp vào nhiều giao thức, thay vì bị gắn cứng với cú pháp lệnh của một giao thức.

Điều đó **không** có nghĩa có thể bỏ việc tích hợp. Giao thức vẫn phải định nghĩa cách mang dữ liệu SASL, giới hạn kích thước, cách hủy, cách báo kết quả và thời điểm cho phép gửi lệnh nghiệp vụ.

Ví dụ suy luận: byte phản hồi của một cơ chế không thể tự biến thành LDAP Bind hoặc một dòng lệnh IMAP. Thư viện giao thức phải đóng gói nó đúng quy tắc của giao thức đang dùng. Chép nguyên chuỗi trao đổi ở một giao thức sang giao thức khác thường không tạo thành một phiên đăng nhập hợp lệ.

Trong Java, package `javax.security.sasl` cung cấp các giao diện cho cơ chế; không tự cung cấp một máy khách LDAP hoặc IMAP hoàn chỉnh. Xem [Java SASL API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/package-summary.html).

## 3. Những thuật ngữ cần biết trước khi đọc luồng xác thực

### Cơ chế và tên cơ chế

Mỗi cơ chế có tên xác định. Máy chủ quảng bá những cơ chế cho phép; máy khách chọn một cơ chế mà cả hai phía cùng triển khai và chính sách kết nối chấp nhận.

Không chọn cơ chế chỉ vì tên đó đứng đầu danh sách máy chủ. Chính sách máy khách cần cân nhắc khả năng của thư viện, loại thông tin xác thực và kênh đang sử dụng.

### Challenge, response và initial response

- **Challenge:** khối dữ liệu từ phía máy chủ để máy khách xử lý trong trao đổi.
- **Response:** khối dữ liệu máy khách tạo theo cơ chế.
- **Initial response:** phản hồi đầu tiên mà một số cơ chế cho phép máy khách tạo trước khi nhận dữ liệu thử thách cụ thể.

Các khối này là dữ liệu byte. Giao thức bao ngoài quyết định có dùng Base64 hay định dạng khác để truyền chúng. Base64 chỉ là mã hóa biểu diễn, không bảo mật mật khẩu hoặc token.

Không phải cơ chế nào cũng có cùng số lượt, cùng phía gửi trước hoặc cùng cấu trúc dữ liệu. “Challenge-response” là mô hình giao tiếp chung; không phải cam kết rằng mọi response đều là một hàm băm an toàn của mật khẩu.

### Danh tính xác thực và danh tính được yêu cầu sử dụng

- **Authentication identity (authcid):** danh tính được chứng minh bằng cơ chế xác thực.
- **Authorization identity (authzid):** danh tính mà máy khách yêu cầu được hoạt động dưới danh nghĩa đó.

Thông thường chúng có thể tương ứng cùng một người, nhưng không phải lúc nào cũng giống nhau. Ví dụ, một dịch vụ đã xác thực có thể yêu cầu truy cập thay mặt một tài khoản khác; máy chủ phải kiểm tra quyền đại diện.

Chấp nhận thông tin xác thực không tự cho phép nhận mọi authzid do máy khách gửi. Java có `AuthorizeCallback` để cơ chế phía máy chủ yêu cầu quyết định kiểu này. Xem [AuthorizeCallback API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/AuthorizeCallback.html).

## 4. Một lần xác thực diễn ra như thế nào?

Luồng khái niệm dưới đây không mô tả cú pháp lệnh của một sản phẩm cụ thể:

```text
Máy khách                              Máy chủ
    |                                     |
    |<--- Danh sách cơ chế được công bố ---|
    |                                     |
    |--- Chọn cơ chế + dữ liệu đầu nếu có->|
    |                                     |
    |<---------- Challenge ---------------|
    |----------- Response ---------------->|
    |          ... có thể nhiều lượt ...  |
    |                                     |
    |<------ Kết quả của giao thức --------|
    |                                     |
    |--- Lệnh nghiệp vụ khi được phép ---->|
```

Để phiên xác thực thành công, hai phía phải xử lý đầy đủ các dữ liệu cuối cùng của cơ chế và kết quả do giao thức ứng dụng quy định. Một cơ chế có thể tạo xong dữ liệu cục bộ trước khi máy khách nhận thông báo chấp nhận của máy chủ.

Một trường hợp suy luận: thư viện máy khách vừa tính xong response nên `isComplete()` thành `true`, nhưng response chưa được gửi hoặc máy chủ đã trả lỗi. Bật “đã đăng nhập” tại thời điểm đó là sai. Cần kết hợp trạng thái của cơ chế với kết quả phía máy chủ trên giao thức đang dùng.

Nếu không có cơ chế nào thỏa cả khả năng và chính sách, phiên phải thất bại rõ ràng. Không tự đổi sang một phương thức không được người triển khai cho phép chỉ để tiếp tục kết nối.

## 5. SASL và TLS bổ sung cho nhau

TLS thường cung cấp kênh được bảo vệ, kiểm tra danh tính máy chủ và có thể xác thực máy khách bằng chứng thư. SASL cung cấp cơ chế xác thực được tích hợp vào giao thức ứng dụng.

Ví dụ một thiết kế thông dụng:

```text
Thiết lập TLS và xác minh đúng máy chủ
                    |
     Lấy danh sách cơ chế trên kênh an toàn
                    |
        Chọn cơ chế SASL được cho phép
                    |
        Hoàn tất trao đổi xác thực SASL
                    |
      Kiểm tra quyền cho từng thao tác
```

Các trách nhiệm không thay thế lẫn nhau:

| Khẳng định | Đánh giá |
| --- | --- |
| “Có SASL nên không cần TLS” | Sai; tính bảo mật phụ thuộc cơ chế và cách triển khai |
| “Có TLS nên tài khoản ứng dụng đã được đăng nhập” | Sai; TLS có thể chỉ xác thực máy chủ |
| “Base64 rồi gửi là đã mã hóa bí mật” | Sai |
| “Xác thực thành công nên được làm mọi thao tác” | Sai; còn chính sách phân quyền |
| “EXTERNAL có thể dùng danh tính đã xác thực từ bên ngoài” | Đúng khi phần tích hợp chuyển giao danh tính và kiểm tra quyền đúng |

Nếu giao thức nâng cấp kênh bằng STARTTLS, phải tuân thủ phần tích hợp của giao thức đó, bao gồm việc khám phá lại khả năng khi được yêu cầu sau nâng cấp. Không giữ một danh sách cơ chế nhận trên kênh chưa được bảo vệ rồi coi nó luôn còn hợp lệ.

Thiết kế kết hợp SASL, TLS và thư viện giao thức được trình bày trong [hướng dẫn Java SASL](https://docs.oracle.com/en/java/javase/25/security/java-sasl-api-programming-and-deployment-guide1.html). Các ví dụ lịch sử trong tài liệu API không thay thế chính sách chọn cơ chế hiện hành của hệ thống.

## 6. Một số cơ chế còn có ý nghĩa trong triển khai hiện đại

Mục này giúp nhận diện vai trò, không hướng dẫn tự viết thuật toán xác thực.

### SCRAM-SHA-256

SCRAM-SHA-256 là cơ chế xác thực dựa trên mật khẩu, trao đổi bằng chứng thay vì gửi trực tiếp mật khẩu như dữ liệu đăng nhập. Độ an toàn còn phụ thuộc mật khẩu, chính sách xử lý bí mật, tham số cơ chế, xác minh máy chủ và bảo vệ kênh.

Biến thể `SCRAM-SHA-256-PLUS` dùng ràng buộc kênh (channel binding) để gắn trao đổi với kênh bảo mật bên dưới. Không tự tạo dữ liệu ràng buộc bằng tên máy chủ hoặc một chuỗi tùy ý; phải dùng loại ràng buộc và khả năng mà hai phía thực sự hỗ trợ.

Tên cơ chế và nền tảng SCRAM-SHA-256 được quy định trong [RFC 7677](https://www.rfc-editor.org/rfc/rfc7677.html). Sự có mặt của API SASL trong Java không bảo đảm JDK hoặc thư viện đang dùng đã cài một nhà cung cấp cho cơ chế này.

### OAUTHBEARER

OAUTHBEARER cho phép sử dụng thông tin xác thực OAuth trong luồng SASL của giao thức không nhất thiết là HTTP. Token vẫn là bí mật cần bảo vệ; phải kiểm tra tính hợp lệ và phạm vi sử dụng theo hệ thống cấp token.

Cơ chế SASL này không tự thay người dùng đăng nhập ở máy chủ cấp quyền và không tự biến một token bất kỳ thành token được dịch vụ chấp nhận. Nó định nghĩa cách mang thông tin xác thực OAuth vào trao đổi SASL. Xem [RFC 7628](https://www.rfc-editor.org/rfc/rfc7628.html).

### EXTERNAL

EXTERNAL dựa vào danh tính được xác thực bởi phương tiện bên ngoài trao đổi SASL, chẳng hạn chứng thư máy khách trên TLS. Phần tích hợp phải biết danh tính ngoài đó là gì và đối chiếu quyền sử dụng authzid nếu có.

Một kết nối TLS chỉ xác thực máy chủ không tự mang lại danh tính chứng thư của máy khách cho EXTERNAL. Tạo được một đối tượng EXTERNAL cũng không chứng minh đã có phương tiện xác thực bên ngoài.

Việc chọn cơ chế phải phù hợp hệ sinh thái thật: máy chủ có công bố nó, máy khách có triển khai, dữ liệu xác thực có sẵn, chính sách kênh được đáp ứng. Không chọn theo độ dài tên hoặc theo danh sách ví dụ sao chép từ tài liệu cũ.

## 7. API Java nằm ở đâu trong mô hình?

Các lớp và giao diện chính:

| API | Vai trò |
| --- | --- |
| `Sasl.createSaslClient(...)` | Tạo cơ chế phía máy khách qua nhà cung cấp có sẵn |
| `Sasl.createSaslServer(...)` | Tạo cơ chế phía máy chủ |
| `SaslClient.evaluateChallenge(...)` | Xử lý byte challenge và tạo response |
| `SaslServer.evaluateResponse(...)` | Xử lý byte response và tạo challenge |
| `CallbackHandler` | Cung cấp thông tin hoặc quyết định mà cơ chế cần |
| `isComplete()` | Hỏi cơ chế cục bộ đã hoàn tất trao đổi chưa |
| `dispose()` | Giải phóng tài nguyên và thông tin nhạy cảm do đối tượng giữ |

Factory có thể trả `null` khi không tạo được cơ chế phù hợp; chương trình phải kiểm tra trước khi gọi các phương thức của client/server. Xem [Sasl API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html).

Tham số `protocol` và `serverName` mô tả ngữ cảnh dịch vụ cho cơ chế. Chúng không tự mở socket, không thực hiện phân giải DNS và không thay việc xác minh danh tính máy chủ ở tầng TLS.

Đối tượng cơ chế có trạng thái của một lần trao đổi; không chia sẻ một `SaslClient` đang xác thực giữa nhiều kết nối độc lập. Phần I/O phải giữ đúng trình tự và giới hạn đầu vào, không gọi vô hạn trên một challenge cũ để mong trạng thái tự thay đổi.

Hợp đồng response phân biệt `null` với mảng byte độ dài 0: một bên có thể biểu thị không cần gửi response, còn bên kia là response hợp lệ không có dữ liệu. Phần tích hợp phải giữ ý nghĩa đúng theo [SaslClient API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html), thay vì biến cả hai thành “bỏ qua”.

## 8. Ví dụ Java 17+: cơ chế hoàn tất chưa phải đăng nhập thành công

Ví dụ dùng EXTERNAL để quan sát ranh giới API. Chương trình không tạo TLS, không xuất trình chứng thư và không giao tiếp với máy chủ; vì vậy **không thực hiện xác thực một người dùng thật**.

Với nhà cung cấp EXTERNAL phía máy khách thông thường của JDK, authzid không được chỉ định tạo một phản hồi đầu rỗng. Phản hồi rỗng có ý nghĩa giao thức; không phải bằng chứng ai cũng được đăng nhập.

Lưu thành `SaslBoundaryDemo.java`:

```java
import java.util.Map;
import javax.security.sasl.Sasl;
import javax.security.sasl.SaslClient;
import javax.security.sasl.SaslException;

public class SaslBoundaryDemo {
    public static void main(String[] args) throws SaslException {
        SaslClient client = Sasl.createSaslClient(
                new String[] {"EXTERNAL"},
                null,
                "example",
                "service.example.com",
                Map.of(),
                null);
        if (client == null) {
            throw new IllegalStateException(
                    "No EXTERNAL SaslClient provider");
        }

        try {
            System.out.println("mechanism=" + client.getMechanismName());
            System.out.println("initial=" + client.hasInitialResponse());
            System.out.println("before=" + client.isComplete());

            byte[] response = client.evaluateChallenge(new byte[0]);
            System.out.println("responseBytes=" + response.length);
            System.out.println("after=" + client.isComplete());

            boolean protocolServerAccepted = false;
            System.out.println("ready="
                    + (client.isComplete() && protocolServerAccepted));
        } finally {
            client.dispose();
        }
    }
}
```

Chạy bằng JDK 17+ có nhà cung cấp EXTERNAL phía máy khách:

```shell
javac SaslBoundaryDemo.java
java SaslBoundaryDemo
```

Stdout trên cấu hình JDK đó:

```text
mechanism=EXTERNAL
initial=true
before=false
responseBytes=0
after=true
ready=false
```

Các điểm cần đọc từ ví dụ:

- `"example"` chỉ là nhãn dịch vụ minh họa; chương trình không triển khai một giao thức ứng dụng tên đó.
- `createSaslClient()` chỉ tạo đối tượng cục bộ; nếu nhà cung cấp không có, chương trình báo lỗi rõ ràng.
- `evaluateChallenge(new byte[0])` tạo phản hồi đầu theo cơ chế, không xác minh một máy chủ nào trong ví dụ này.
- `isComplete() == true` sau đó là trạng thái của cơ chế cục bộ.
- `protocolServerAccepted` cố ý bằng `false` vì không có máy chủ; do đó `ready` vẫn là `false`.
- Để dùng EXTERNAL thật, phải có danh tính ngoài được thiết lập và phần tích hợp phía máy chủ chấp nhận nó.

Không lấy ví dụ này làm đường tắt xác thực. Nó chứng minh vì sao bộ điều khiển kết nối phải lưu riêng kết quả cơ chế và kết quả giao thức.

## 9. Lớp bảo vệ SASL là tùy chọn

Một số cơ chế có thể thương lượng chất lượng bảo vệ (quality of protection, QOP) cho dữ liệu sau xác thực:

| QOP trong Java | Ý nghĩa |
| --- | --- |
| `auth` | Chỉ xác thực |
| `auth-int` | Xác thực và bảo vệ toàn vẹn |
| `auth-conf` | Xác thực, toàn vẹn và bí mật |

Không phải cơ chế nào cũng hỗ trợ mọi giá trị. Chỉ gọi `wrap()/unwrap()` của SASL sau khi trao đổi hoàn tất và một lớp bảo vệ tương ứng đã được thương lượng. Cần đọc thuộc tính kết quả và tuân thủ đóng khung dữ liệu của phần tích hợp.

`SaslClient.wrap()` không phải `SSLEngine.wrap()`: chúng thuộc hai API và hai lớp bảo vệ khác nhau. Không tráo byte đầu vào của hai lớp hoặc tự bỏ TLS vì thấy tên phương thức giống nhau.

Đối với EXTERNAL trong ví dụ, chương trình không thương lượng một lớp bảo vệ SASL riêng để dùng `wrap()/unwrap()`. Kênh bên ngoài và danh tính bên ngoài phải được xử lý bởi phần tích hợp thật.

## 10. Lỗi thiết kế dễ gặp và cách kiểm chứng

| Lỗi | Hậu quả có thể xảy ra |
| --- | --- |
| Chọn bất kỳ cơ chế nào máy chủ công bố | Hạ mức bảo vệ ngoài chính sách máy khách |
| Cho rằng mọi cơ chế đều có sẵn trong JDK | Factory trả `null` hoặc triển khai khác môi trường |
| Bật sẵn sàng chỉ dựa vào `isComplete()` | Gửi lệnh nghiệp vụ trước khi máy chủ chấp nhận |
| Nhầm authcid với authzid | Cho phép đại diện danh tính không được ủy quyền |
| Ghi toàn bộ token trao đổi vào log | Lộ bí mật hoặc dữ liệu xác thực |
| Bỏ qua dữ liệu cuối của cơ chế | Không kiểm tra đầy đủ kết quả xác thực |
| Tự thêm Base64 vào mọi byte | Đóng gói sai so với giao thức ứng dụng |

Một bài kiểm thử tích hợp có giá trị cần bao gồm ca thành công và ca bị từ chối: không có cơ chế chung, sai thông tin xác thực, máy chủ từ chối sau khi client hoàn tất cục bộ, yêu cầu authzid không được phép, timeout và mất kết nối giữa trao đổi.

Giữ log ở mức tên cơ chế, mã kết nối, giai đoạn và mã lỗi phù hợp; tránh ghi password, access token hoặc toàn bộ challenge/response khi chưa biết nội dung nhạy cảm của cơ chế.

## 11. Tự kiểm tra

1. SASL có phải một cơ chế cụ thể không? **Không; nó là khung để tích hợp các cơ chế có thể thay thế.**
2. “Độc lập giao thức” có nghĩa bỏ phần tích hợp được không? **Không; giao thức vẫn quyết định cách vận chuyển và báo kết quả.**
3. Vì sao hai giao thức có thể cùng dùng SCRAM? **Thuật toán trao đổi thuộc cơ chế, còn cách đóng gói thuộc từng giao thức.**
4. TLS và SASL có bắt buộc chọn một trong hai không? **Không; chúng thường được kết hợp theo trách nhiệm khác nhau.**
5. Client hoàn tất cục bộ có đủ để coi đã đăng nhập không? **Chưa đủ; còn phải xử lý đầy đủ kết quả máy chủ và giao thức.**
6. Có API SASL trong JDK có đồng nghĩa mọi cơ chế hiện đại đều có sẵn không? **Không; cần kiểm tra nhà cung cấp và khả năng của thư viện triển khai.**
