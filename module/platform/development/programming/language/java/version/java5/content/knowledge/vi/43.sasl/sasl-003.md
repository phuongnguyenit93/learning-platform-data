# Trao đổi challenge, response và trạng thái hoàn tất trong SASL

## 1. SASL tổ chức cuộc trao đổi như thế nào?

SASL là khung xác thực cho giao thức có kết nối. Cơ chế SASL quyết định cách tạo và kiểm tra dữ liệu xác thực; giao thức ứng dụng quyết định cách đóng gói, gửi và biểu diễn kết quả. Hai phía không gọi phương thức Java của nhau qua mạng: mỗi phía xử lý dữ liệu cục bộ rồi gửi thông điệp tương ứng.

Trong Java:

| Thành phần | Trách nhiệm chính |
| --- | --- |
| `SaslClient` | Nhận dữ liệu thách thức của máy chủ và tạo dữ liệu phản hồi của máy khách |
| `SaslServer` | Kiểm tra phản hồi của máy khách và tạo dữ liệu trả về cho bước tiếp theo |
| Lớp giao thức, chẳng hạn LDAP | Chọn cơ chế, đóng khung thông điệp, vận chuyển byte, báo tiếp tục/thành công/thất bại |

Một thách thức (challenge) không nhất thiết chỉ là một số ngẫu nhiên. Nó có thể chứa tham số, bằng chứng, thông tin thương lượng hoặc dữ liệu khác do cơ chế quy định. Phản hồi (response) cũng không mặc định là mật khẩu. Hãy coi chúng là các chuỗi byte có nghĩa riêng đối với cơ chế. [RFC 4422, mục 3](https://www.rfc-editor.org/rfc/rfc4422.html#section-3).

Bài này trình bày mô hình và API còn áp dụng trên JDK hiện đại. Không cần chọn cơ chế cũ để học luồng challenge–response.

## 2. Luồng tổng quát có thể có nhiều lượt

Sơ đồ sau biểu diễn một khả năng, không phải số lượt bắt buộc:

```text
Máy khách                              Máy chủ
Yêu cầu xác thực + tên cơ chế --------->
                         <------------- Thách thức bước 1
Phản hồi bước 1 ----------------------->
                         <------------- Thách thức bước 2
Phản hồi bước 2 ----------------------->
                         <------------- Kết quả cuối, có thể kèm dữ liệu cuối
Kiểm tra dữ liệu cuối nếu cơ chế yêu cầu
Chỉ chuyển sang trạng thái đã xác thực khi đủ điều kiện
```

Nếu cơ chế cho phép máy khách gửi trước, phản hồi ban đầu có thể được gộp vào yêu cầu xác thực, tùy giao thức. Nếu giao thức không cho gộp, nó có thể tổ chức một lượt đầu với thách thức rỗng để kích hoạt phản hồi ban đầu. Không gắn cứng “luôn bắt đầu bằng một challenge có dữ liệu từ máy chủ”.

Một kết nối đang xác thực chưa được xử lý yêu cầu nghiệp vụ dưới danh tính mới. Bộ điều khiển nên có trạng thái riêng, chẳng hạn `NEW`, `EXCHANGING`, `WAITING_OUTCOME`, `AUTHENTICATED`, `FAILED`, `DISPOSED`; đây là tên do ứng dụng thiết kế, không phải enum có sẵn của SASL.

## 3. Phía máy khách: hasInitialResponse và evaluateChallenge

`hasInitialResponse()` cho biết cơ chế có phản hồi ban đầu. Nếu giao thức cho phép gửi kèm và giá trị là `true`, gọi `evaluateChallenge(new byte[0])` để tạo dữ liệu đó. Sau các thách thức từ máy chủ, gọi `evaluateChallenge(challenge)` để có phản hồi kế tiếp. Đầu vào không được là `null`; mảng rỗng là đầu vào hợp lệ. [API SaslClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html).

Đoạn sau minh họa bước chuẩn bị, không thực hiện I/O:

```java
byte[] initialResponse = null;
if (protocolSupportsInitialResponse && client.hasInitialResponse()) {
    initialResponse = client.evaluateChallenge(new byte[0]);
}
// Lớp giao thức phải bảo toàn sự khác nhau giữa không có phản hồi
// và một phản hồi có độ dài bằng 0 khi đóng gói yêu cầu.
```

`client` là `SaslClient` đã tạo; `protocolSupportsInitialResponse` là khả năng của giao thức tích hợp. Không tự đặt biến này thành `true` chỉ vì provider hỗ trợ phản hồi ban đầu.

Sau mỗi lần đánh giá, kiểm tra trạng thái nội bộ của client. Tuy nhiên, chưa được kết luận phía máy chủ đã chấp nhận danh tính. Một số cơ chế có thể hoàn thành công việc cục bộ rất sớm, trong khi máy khách vẫn đang đợi kết quả cuối từ máy chủ.

### Khi nhận dữ liệu từ máy chủ

Lớp giao thức cần giải mã thông điệp thành ít nhất hai phần khác nhau:

1. Trạng thái giao thức: đang tiếp tục, thành công, thất bại hoặc bị hủy.
2. Dữ liệu SASL kèm theo: có thể có, rỗng hoặc vắng mặt theo quy tắc của giao thức.

Chỉ chuyển phần dữ liệu SASL đã được bóc đúng lớp cho cơ chế. Không đưa nguyên dòng phản hồi LDAP/SMTP hay mã trạng thái văn bản vào `evaluateChallenge()`.

## 4. Phía máy chủ: evaluateResponse và dữ liệu cuối

Máy chủ chuyển phần phản hồi SASL đã giải mã vào `server.evaluateResponse(response)`, sau đó kiểm tra `server.isComplete()`. Phương thức có thể trả dữ liệu cần gửi cho máy khách ngay cả khi trạng thái máy chủ đã hoàn tất. Do đó, không bỏ giá trị trả về chỉ vì `isComplete()` chuyển thành `true`. [API SaslServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html).

Một đoạn định hướng cho lớp giao thức:

```java
byte[] outgoingData = server.evaluateResponse(response);
boolean completed = server.isComplete();

if (completed) {
    // Gửi kết quả thành công, bảo toàn outgoingData nếu có,
    // theo cách giao thức quy định cho dữ liệu cuối.
} else {
    // Gửi thông điệp tiếp tục mang outgoingData.
    // Đợi phản hồi tiếp theo của đúng cuộc trao đổi này.
}
```

Đây là đoạn minh họa, không phải máy chủ chạy độc lập. Nó giả định phía tích hợp đã lựa chọn cơ chế hợp lệ, có thông tin xác thực/chính sách phân quyền phù hợp và đã bóc được `response`. Khi `evaluateResponse()` ném `SaslException`, xử lý theo nhánh thất bại của giao thức, không chuyển lỗi thành một mảng thách thức rỗng rồi tiếp tục.

Máy chủ còn phải kiểm tra quyền sử dụng danh tính được yêu cầu. Được xác thực bằng một thông tin định danh không tự cho phép hoạt động dưới mọi danh tính khác mà máy khách gửi lên.

## 5. null, mảng rỗng và dữ liệu nhị phân là ba điều khác nhau

Không dùng `if (token == null || token.length == 0)` để coi mọi tình huống giống nhau.

| Giá trị | Cách hiểu cần bảo toàn |
| --- | --- |
| `null` trả về từ bước đánh giá | Không có dữ liệu phản hồi/thách thức cần gửi ở tình huống mà API/cơ chế cho phép |
| `new byte[0]` | Có một thông điệp SASL nhưng phần dữ liệu có độ dài bằng 0 |
| Mảng có độ dài lớn hơn 0 | Dữ liệu SASL phải được vận chuyển nguyên vẹn |

Ở máy khách, kết quả `null` có thể xuất hiện khi dữ liệu cuối đi cùng thành công chỉ dùng để cập nhật/kiểm tra trạng thái và không cần gửi phản hồi nữa. Ở máy chủ, `null` có thể biểu diễn thành công không còn dữ liệu cần gửi. Muốn biết hoàn tất, vẫn đọc `isComplete()` và trạng thái giao thức tương ứng; không dùng riêng `null` làm tín hiệu chung. [SaslClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html), [SaslServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html).

Quy tắc đóng gói thông điệp thuộc giao thức tích hợp. Một giao thức văn bản có thể dùng Base64 để mang byte, nhưng đó là mã hóa biểu diễn, không phải mã hóa bảo mật. Luồng xử lý thường là:

```text
Phía gửi: byte SASL -> biểu diễn/đóng khung của giao thức -> mạng
Phía nhận: mạng -> tách khung/giải mã biểu diễn -> đúng byte SASL ban đầu
```

Không gọi `new String(token)` bằng bảng mã mặc định rồi `.getBytes()` để vận chuyển. Token có thể chứa mọi giá trị byte, bao gồm byte 0; chuyển đổi văn bản không đúng có thể thay đổi dữ liệu. Cũng không tự mã hóa Base64 lần nữa nếu thư viện giao thức đã làm việc đó.

## 6. Hoàn tất cục bộ khác với thành công của toàn cuộc trao đổi

Một bộ điều khiển máy khách chỉ nên coi xác thực thành công khi đủ các điều kiện phù hợp với cơ chế/giao thức:

- Nhận kết quả thành công cuối của máy chủ.
- Cơ chế máy khách đã hoàn tất và kiểm tra dữ liệu cuối bắt buộc thành công.
- Kết quả thương lượng đáp ứng chính sách của ứng dụng.
- Không có lỗi giao thức, hủy hoặc mất kết nối làm cuộc trao đổi không còn hợp lệ.

Không bỏ qua dữ liệu cuối chỉ vì thông điệp có nhãn thành công. Dữ liệu ấy có thể là phần cần để máy khách kiểm tra máy chủ hoặc hoàn tất trạng thái cơ chế. Ngược lại, không tiếp tục tự phát thêm phản hồi sau một kết quả cuối nếu giao thức không cho phép. [RFC 4422, mục 3.6](https://www.rfc-editor.org/rfc/rfc4422.html#section-3.6).

Ví dụ suy luận:

```text
Client: đã tạo phản hồi cuối, isComplete = true
Mạng:   phản hồi đã được gửi
Server: trả FAILURE vì không cho phép danh tính hoạt động được yêu cầu
Kết luận: thất bại, dù isComplete của client là true
```

Một tình huống khác:

```text
Server: trả SUCCESS kèm dữ liệu cuối
Client: còn phải đánh giá/kiểm tra dữ liệu cuối của cơ chế
Client: kiểm tra thất bại
Kết luận: không chấp nhận kết nối là đã xác thực
```

Nếu client đã hoàn tất mà vẫn nhận một bước tiếp tục không phù hợp, đừng gọi đánh giá lặp vô điều kiện. Kiểm tra quy tắc cơ chế và giao thức, kể cả trường hợp xác nhận rỗng được quy định riêng; nếu không hợp lệ, kết thúc với lỗi giao thức.

## 7. Chương trình Java 17+: nhìn thấy isComplete sớm

Ví dụ dùng cơ chế `EXTERNAL` của provider có trong môi trường SunSASL. `EXTERNAL` dựa vào thông tin xác thực được thiết lập ngoài SASL, chẳng hạn danh tính từ TLS máy khách đã được máy chủ kiểm tra. Nó không tự chứng minh danh tính chỉ bằng cách tạo một phản hồi rỗng.

Chương trình chạy cục bộ, không mở mạng, không có TLS và không đăng nhập vào máy chủ. Mục tiêu duy nhất là quan sát API máy khách hoàn tất trong khi chưa nhận kết quả từ máy chủ. Trường hợp `authorizationId` là `null` ở đây tạo phản hồi ban đầu rỗng với provider được kiểm chứng. [RFC 4422, cơ chế EXTERNAL](https://www.rfc-editor.org/rfc/rfc4422.html#appendix-A).

Lưu thành `SaslCompletionDemo.java`:

```java
import java.util.Map;
import javax.security.sasl.Sasl;
import javax.security.sasl.SaslClient;

public class SaslCompletionDemo {
    public static void main(String[] args) throws Exception {
        SaslClient client = Sasl.createSaslClient(
                new String[] {"EXTERNAL"}, null,
                "ldap", "directory.example", Map.of(), null);
        if (client == null) {
            throw new IllegalStateException("EXTERNAL client provider unavailable");
        }
        try {
            System.out.println("mechanism=" + client.getMechanismName());
            System.out.println("initialResponse=" + client.hasInitialResponse());
            byte[] response = client.evaluateChallenge(new byte[0]);
            System.out.println("responseLength=" + response.length);
            System.out.println("clientComplete=" + client.isComplete());
            boolean serverReportedSuccess = false;
            System.out.println("acceptedBeforeOutcome="
                    + (client.isComplete() && serverReportedSuccess));
        } finally {
            client.dispose();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 SaslCompletionDemo.java
java SaslCompletionDemo
```

Stdout quan sát với SunSASL trên JDK 21:

```text
mechanism=EXTERNAL
initialResponse=true
responseLength=0
clientComplete=true
acceptedBeforeOutcome=false
```

`responseLength=0` biểu diễn một phản hồi rỗng, không phải không có phản hồi. `clientComplete=true` chỉ là trạng thái cơ chế cục bộ; `acceptedBeforeOutcome=false` cho thấy bộ điều khiển không được tự nhận đã đăng nhập trước kết quả của máy chủ.

Trên provider khác, `createSaslClient()` có thể trả `null` nếu không tạo được cơ chế theo yêu cầu. Chương trình báo lỗi rõ ràng; không tự chuyển sang cơ chế ngoài chính sách. Việc truyền `"ldap"` và tên máy chủ ở đây chỉ cung cấp tham số cơ chế, không tạo kết nối LDAP. [API Sasl.createSaslClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html).

Ví dụ này không minh họa một cuộc xác thực EXTERNAL hoàn chỉnh. Trong hệ thống thật, máy chủ phải có danh tính ngoài SASL đã được kiểm tra, ánh xạ nó và chấp nhận quyền hoạt động được yêu cầu. Không coi phản hồi rỗng là bằng chứng xác thực hoặc đăng nhập ẩn danh thành công.

## 8. Một ví dụ nhiều lượt mà không tự triển khai thuật toán

Với cơ chế SCRAM-SHA-256, có thể hình dung các vai trò thông điệp như sau:

```text
client-first-message ->
                     <- server-first-message
client-final-message ->
                     <- server-final-message
```

Các thông điệp bao gồm tham số và bằng chứng của cơ chế; phần cuối của máy chủ cần được máy khách kiểm tra. Sơ đồ chỉ mô tả vai trò, không phải chuỗi byte có thể sao chép để xác thực. [RFC 7677](https://www.rfc-editor.org/rfc/rfc7677.html).

Ứng dụng nên giao việc tạo và kiểm tra thông điệp cho provider/thư viện cơ chế đã được đánh giá. Không tự nối tên người dùng, số ngẫu nhiên và mật khẩu thành một thuật toán “challenge–response” mới. Việc một cơ chế là chuẩn SASL cũng không bảo đảm mọi JDK/provider đã cài sẵn nó; kiểm tra khả năng triển khai và chính sách trước khi chọn.

Ví dụ nhiều lượt không làm thay đổi mô hình điều khiển: byte đến đúng lượt được đánh giá đúng một lần, byte đi được đóng khung đúng một lần, sau đó chờ thông điệp kế tiếp. Số lần gọi đánh giá không phải số lần thử mật khẩu độc lập và không được tái khởi tạo đối tượng cơ chế sau từng lượt.

## 9. Quản lý trạng thái, lỗi và tài nguyên

Mỗi cuộc trao đổi có một `SaslClient`/`SaslServer` giữ trạng thái riêng. Nếu tạo mới đối tượng ở mỗi lượt, thông tin của lượt trước có thể mất, khiến bằng chứng hoặc thứ tự thông điệp không còn hợp lệ. Không chia sẻ cùng đối tượng cho nhiều người dùng hoặc nhiều cuộc xác thực đồng thời.

Một lớp tích hợp nên xử lý rõ:

| Sự kiện | Hành động định hướng |
| --- | --- |
| Có challenge/response hợp lệ của lượt hiện tại | Đánh giá, kiểm tra trạng thái, gửi dữ liệu cần thiết |
| `SaslException` | Đánh dấu thất bại, báo/hủy theo giao thức, dọn trạng thái |
| Máy chủ trả thất bại | Không cho phép dùng kết nối dưới danh tính mới |
| Hết thời gian hoặc EOF trước kết quả cuối | Cuộc trao đổi chưa hoàn tất; trả lỗi thích hợp |
| Thông điệp quá lớn hoặc quá nhiều lượt | Dừng theo giới hạn đã đặt; không cấp phát hoặc lặp vô hạn |
| Kết nối bị hủy khi công việc bất đồng bộ còn chạy | Ngăn callback muộn khôi phục trạng thái xác thực |

Giới hạn số lượt, kích thước token và thời gian là chính sách tài nguyên của lớp tích hợp; chọn theo cơ chế và giao thức, không dùng một số cố định thiếu cơ sở cho mọi hệ thống. Mất mạng ở giữa cuộc trao đổi không được suy ra thành công chỉ từ việc đã gửi xong phản hồi cuối.

Khi không còn dùng, gọi `dispose()` để giải phóng tài nguyên nhạy cảm của đối tượng. Nếu cơ chế đã thương lượng lớp bảo vệ cho dữ liệu sau xác thực, cần giữ đối tượng trong suốt thời gian dùng lớp đó; không `dispose()` ngay rồi tiếp tục gọi `wrap()`/`unwrap()`. Chỉ sử dụng các phương thức bảo vệ dữ liệu khi đã hoàn tất và thực sự thương lượng chất lượng bảo vệ phù hợp. [SaslClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html).

Không mặc định SASL nào cũng mã hóa toàn bộ dữ liệu nghiệp vụ. Cơ chế, lớp bảo vệ được thương lượng và TLS bên ngoài là các phần cần đánh giá riêng. Việc hoàn thành SASL cũng không thay thế phân quyền ở từng thao tác nghiệp vụ.

## 10. Các lỗi tích hợp thường gặp

| Sai sót | Hậu quả |
| --- | --- |
| Dùng `isComplete()` ở client làm bằng chứng máy chủ đã chấp nhận | Mở quyền truy cập trước kết quả xác thực cuối |
| Bỏ dữ liệu máy chủ trả vì `server.isComplete()` đã đúng | Máy khách không có dữ liệu cuối để kiểm tra/hoàn tất |
| Đồng nhất `null` với mảng rỗng | Sai cấu trúc thông điệp hoặc thiếu một phản hồi bắt buộc |
| Gắn cứng một challenge và một response | Không hỗ trợ các cơ chế nhiều lượt hoặc phản hồi ban đầu |
| Chuyển token tùy tiện qua `String` | Thay đổi byte, làm bằng chứng không hợp lệ |
| Gọi đánh giá hai lần cho cùng thông điệp | Đẩy máy trạng thái sang lượt sai |
| Tạo lại cơ chế sau mỗi lượt | Mất ngữ cảnh của cuộc xác thực |
| Ghi toàn bộ challenge/response để gỡ lỗi | Có thể lộ token, thông tin định danh hoặc dữ liệu xác thực nhạy cảm |

Khi gỡ lỗi, ưu tiên ghi tên cơ chế, số lượt, kích thước thông điệp, trạng thái giao thức, cờ hoàn tất và loại lỗi. Giữ nội dung token ra khỏi nhật ký thông thường.

Tự kiểm tra: máy chủ `evaluateResponse()` trả mảng có dữ liệu đồng thời `isComplete()` là `true`. Lớp giao thức phải vận chuyển dữ liệu cuối theo quy tắc thành công của giao thức, còn máy khách phải xử lý dữ liệu ấy khi cơ chế yêu cầu. Không tiếp tục chờ một phản hồi mới chỉ vì mảng không rỗng, và không bỏ dữ liệu chỉ vì máy chủ đã hoàn tất.
