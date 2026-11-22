# Chất lượng bảo vệ được thương lượng trong SASL

## 1. Xác thực xong rồi dữ liệu được bảo vệ thế nào?

Một lần xác thực thành công trả lời câu hỏi về danh tính theo cơ chế đã chọn. Nó không tự bảo đảm mọi dữ liệu ứng dụng gửi sau đó đều được mã hóa hoặc được kiểm tra toàn vẹn bởi SASL.

**Chất lượng bảo vệ (quality of protection, QOP)** mô tả loại dịch vụ bảo vệ mà cơ chế SASL thương lượng cho giai đoạn sau xác thực. Trong Java, các giá trị chuẩn là `auth`, `auth-int` và `auth-conf`.

Ví dụ suy luận: hai kết nối đều xác thực được cùng một tài khoản. Kết nối thứ nhất chỉ dùng SASL để đăng nhập rồi bảo vệ luồng bằng TLS; kết nối thứ hai thương lượng một lớp bảo vệ SASL để xử lý dữ liệu ứng dụng. Không thể phân biệt hai thiết kế đó chỉ bằng thông báo “SASL thành công”.

Cần biết chính sách yêu cầu gì, cơ chế hỗ trợ gì và kết quả thực tế đã chọn gì. Bài học sử dụng hợp đồng API hiện hành trên Java 17+; không cần dùng cơ chế cũ để minh họa QOP.

## 2. Ba giá trị QOP trong Java

| QOP | Loại bảo vệ của SASL | Có lớp bảo vệ dữ liệu SASL để dùng wrap/unwrap? |
| --- | --- | --- |
| `auth` | Chỉ xác thực | Không |
| `auth-int` | Xác thực và bảo vệ toàn vẹn | Có |
| `auth-conf` | Xác thực, toàn vẹn và bí mật | Có |

**Toàn vẹn** giúp phát hiện dữ liệu bị thay đổi theo khả năng của lớp bảo vệ. **Bí mật** nhằm ngăn đọc nội dung mà không có quyền. Bảo vệ cụ thể, thuật toán, quản lý khóa và giới hạn phụ thuộc cơ chế và nhà cung cấp, không chỉ phụ thuộc nhãn QOP.

Không suy ra từ `auth-conf` rằng kết nối có mọi thuộc tính an toàn khác: xác minh đúng danh tính dịch vụ, chống hạ cấp, ràng buộc kênh, bí mật chuyển tiếp hay phân quyền vẫn có hợp đồng và chính sách riêng.

Định nghĩa QOP và thứ tự ưu tiên cấu hình nằm trong [Sasl.QOP API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html#QOP).

## 3. Yêu cầu cấu hình khác với kết quả thương lượng

### 3.1. Cấu hình là danh sách được chấp nhận

Ứng dụng có thể truyền thuộc tính khi tạo cơ chế:

```java
// Đoạn minh họa: cơ chế cụ thể phải hỗ trợ lớp bảo vệ tương ứng.
Map<String, String> properties = Map.of(
        Sasl.QOP, "auth-conf,auth-int",
        Sasl.POLICY_NOANONYMOUS, "true"
);
```

Danh sách `"auth-conf,auth-int"` thể hiện ưu tiên bí mật trước toàn vẹn và chấp nhận cả hai. Nó **không** có nghĩa bắt buộc phải đạt `auth-conf`.

Nếu chính sách bắt buộc bí mật từ chính lớp SASL, danh sách không nên cho phép `auth-int` hoặc `auth`, và ứng dụng vẫn phải kiểm tra kết quả. Không coi một danh sách có nhiều mức là cách ghi “chọn mức mạnh nhất bắt buộc”.

Theo API, khi không cấu hình `Sasl.QOP`, giá trị QOP mặc định là `auth`. Tuy nhiên, không phải mọi cơ chế đều có cùng khả năng hoặc công bố mọi thuộc tính thương lượng; cần kiểm tra giá trị thực và xử lý thiếu dữ liệu theo chính sách.

### 3.2. Kết quả phải được đọc sau trao đổi

Sau khi cơ chế hoàn tất và giao thức xác nhận thành công, đọc:

```java
// Minh họa phía máy khách; serverAccepted do thư viện giao thức xác định.
if (!client.isComplete() || !serverAccepted) {
    throw new IllegalStateException("SASL exchange not accepted");
}
Object negotiatedQop = client.getNegotiatedProperty(Sasl.QOP);
```

Không đọc lại `properties.get(Sasl.QOP)` rồi coi đó là kết quả. Đó chỉ là dữ liệu ứng dụng đã đề nghị.

Không gọi `getNegotiatedProperty()` trước khi cơ chế hoàn tất; API có thể báo `IllegalStateException`. Giá trị `null` không phải cách viết tắt của `auth-conf`; nó có thể biểu thị thuộc tính không được thương lượng hoặc không áp dụng. Nếu chính sách yêu cầu một lớp SASL, dữ liệu thiếu hoặc không nhận diện phải bị từ chối rõ ràng.

## 4. Cơ chế phải thực sự hỗ trợ lớp bảo vệ

Việc Java định nghĩa ba giá trị QOP không làm mọi cơ chế đều có ba chế độ. Một cơ chế có thể chỉ xác thực, trong khi cơ chế khác thương lượng thêm lớp toàn vẹn hoặc bí mật.

Ví dụ, cơ chế SASL GSSAPI dùng Kerberos V5 có phần thương lượng lớp bảo vệ; triển khai thực tế còn cần danh tính, hạ tầng Kerberos và cấu hình phù hợp. Cấu trúc cơ chế được quy định trong [RFC 4752](https://www.rfc-editor.org/rfc/rfc4752.html). Không tự triển khai mật mã bằng phép XOR hoặc một hàm băm minh họa rồi gọi đó là `auth-conf`.

Với các cơ chế chỉ xác thực hoặc dựa vào một kênh bên ngoài, việc thêm thuộc tính `Sasl.QOP="auth-conf"` không biến cơ chế thành bộ mã hóa dữ liệu. Có thể không tạo được cơ chế, không có mức chung hoặc không nhận được kết quả thỏa chính sách.

Một lỗi cần tránh: nếu yêu cầu lớp bảo vệ thất bại, chương trình tự xóa thuộc tính QOP rồi thử lại ở mức `auth`. Đó là thay đổi chính sách an toàn, không phải một lần thử lại trung tính.

## 5. Bật lớp bảo vệ ở đúng ranh giới

Nếu lớp bảo vệ SASL đã được chọn, hai phía phải bắt đầu dùng nó đúng vị trí trong luồng mà giao thức quy định. Không bọc cả các thông điệp bắt tay từ đầu theo suy đoán, và không gửi dữ liệu ứng dụng trần sau điểm phải chuyển lớp.

Mô hình khái niệm:

```text
Trao đổi xác thực SASL
          |
Kết quả cuối được chuyển/kiểm tra đúng giao thức
          |
Xác nhận QOP và kích thước thương lượng
          |
Cài lớp bảo vệ trước dữ liệu giao thức tiếp theo
          |
Ứng dụng -> wrap -> dữ liệu được bảo vệ -> vận chuyển
Ứng dụng <- unwrap <- dữ liệu được bảo vệ <- vận chuyển
```

[RFC 4422 mục 3.7](https://www.rfc-editor.org/rfc/rfc4422.html#section-3.7) quy định lớp bảo vệ được cài sau chỉ báo kết quả xác thực theo từng phía, trước khi chuyển dữ liệu giao thức tiếp theo; vị trí chính xác thuộc phần tích hợp giao thức.

Điều này có ý nghĩa thực tế khi một lần đọc socket chứa cả phản hồi cuối của xác thực và byte đầu của dữ liệu sau xác thực. Bộ phân tích phải giữ phần dư và chuyển nó cho đúng lớp. Xóa bộ đệm hoặc giải mã phần dư bằng bộ phân tích cũ có thể làm hỏng kết nối.

## 6. Dùng wrap/unwrap và kích thước thương lượng

### 6.1. Điều kiện gọi API

Chỉ dùng `SaslClient.wrap()/unwrap()` sau khi trao đổi hoàn tất và đã thương lượng QOP có toàn vẹn hoặc bí mật. Với `auth`, không dùng hai phương thức này như một hàm sao chép byte tùy ý.

```java
// Minh họa sau khi đã xác nhận QOP và cài lớp bảo vệ.
// plaintextLength không vượt giới hạn RAW_SEND_SIZE của kết nối.
byte[] protectedData =
        client.wrap(plaintext, plaintextOffset, plaintextLength);

// receivedToken là đúng một bộ đệm SASL được bảo vệ,
// đã tách phần độ dài thuộc đóng khung.
byte[] decoded =
        client.unwrap(receivedToken, 0, receivedToken.length);
```

Các điều kiện này được nêu trong [SaslClient API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html). Phía máy chủ dùng cặp phương thức tương ứng trong [SaslServer API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html).

### 6.2. RAW_SEND_SIZE và MAX_BUFFER không phải cùng một thứ

- `Sasl.RAW_SEND_SIZE`: số byte dữ liệu thô tối đa thích hợp cho một lần gửi qua lớp bảo vệ đã thương lượng.
- `Sasl.MAX_BUFFER`: giới hạn bộ đệm nhận của phía đang cấu hình/cơ chế theo hợp đồng thuộc tính.

Dữ liệu sau `wrap()` có thể lớn hơn đầu vào vì phần bảo vệ. Không lấy giới hạn kích thước token nhận rồi dùng trực tiếp làm kích thước plaintext đầu vào.

Nếu giới hạn raw là 1.024 byte, một thông điệp ứng dụng 3.000 byte phải được chia thành các phần phù hợp cho lớp bảo vệ. Việc chia này không thay đổi định dạng hay ranh giới thông điệp của giao thức ứng dụng; bên nhận còn phải ghép luồng đúng quy tắc giao thức.

Không giả định giới hạn gửi của hai chiều bằng nhau. Giữ cấu hình và kết quả theo từng kết nối; kiểm tra dữ liệu thuộc tính thiếu, sai kiểu hoặc ngoài giới hạn mà ứng dụng có thể xử lý.

### 6.3. Đóng khung và giới hạn đầu vào

Trong lớp bảo vệ SASL được RFC 4422 mô tả, mỗi bộ đệm được bảo vệ có trường độ dài bốn octet theo thứ tự byte mạng đứng trước nó. Phần vận chuyển phải đọc đủ bộ đệm, kiểm tra giới hạn rồi mới đưa token phù hợp vào `unwrap()`; không đưa cả trường độ dài vào API nếu API yêu cầu token không có tiền tố đó.

TCP không bảo toàn ranh giới của lần `write()`. Một lần đọc có thể chỉ chứa một phần token hoặc nhiều token. Không dùng “mỗi lần đọc socket = một lần unwrap” làm quy tắc.

Kiểm tra độ dài trước khi cấp phát để tránh phía bên kia yêu cầu bộ nhớ quá lớn. Khi lớp bảo vệ không còn xử lý hoặc kiểm tra được dữ liệu, dừng kết nối theo chính sách lỗi; không thử coi dữ liệu đó là plaintext và tiếp tục.

## 7. Ví dụ Java 17+: cổng chính sách cho kết quả QOP

Ví dụ sau yêu cầu **ít nhất toàn vẹn từ chính lớp SASL**. Nó kiểm tra một ảnh chụp các thuộc tính và trạng thái đã được bên tích hợp cung cấp.

Dữ liệu trong `main()` là **giả lập**, không có trao đổi SASL hoặc mã hóa thật. Chương trình chỉ kiểm tra logic chấp nhận/từ chối; một `Map` có chuỗi `auth-conf` không chứng minh kết nối đã được bảo vệ.

Lưu thành `SaslQopPolicyDemo.java`:

```java
import java.util.Map;
import javax.security.sasl.Sasl;

public class SaslQopPolicyDemo {
    record Plan(String qop, int rawSendSize) {
    }

    static Plan requireSaslLayer(
            boolean complete, boolean serverAccepted,
            Map<String, ?> negotiated) {
        if (!complete || !serverAccepted) {
            throw new IllegalStateException("Exchange not accepted");
        }

        Object qopValue = negotiated.get(Sasl.QOP);
        if (!(qopValue instanceof String qop)
                || (!qop.equals("auth-int")
                && !qop.equals("auth-conf"))) {
            throw new IllegalStateException("SASL layer required");
        }

        Object sizeValue = negotiated.get(Sasl.RAW_SEND_SIZE);
        if (!(sizeValue instanceof String text)) {
            throw new IllegalStateException("Missing raw send size");
        }

        final int size;
        try {
            size = Integer.parseInt(text);
        } catch (NumberFormatException failure) {
            throw new IllegalStateException("Invalid raw send size", failure);
        }
        if (size <= 0) {
            throw new IllegalStateException("Non-positive raw send size");
        }
        return new Plan(qop, size);
    }

    private static void rejected(String label, Runnable check) {
        try {
            check.run();
            throw new AssertionError("Expected rejection");
        } catch (IllegalStateException expected) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        // Simulated snapshots, not a real SASL exchange.
        Map<String, String> protectedResult = Map.of(
                Sasl.QOP, "auth-conf",
                Sasl.RAW_SEND_SIZE, "1024");

        Plan plan = requireSaslLayer(true, true, protectedResult);
        System.out.println("accepted=" + plan.qop()
                + " limit=" + plan.rawSendSize());

        rejected("auth", () -> requireSaslLayer(true, true, Map.of(
                Sasl.QOP, "auth", Sasl.RAW_SEND_SIZE, "1024")));
        rejected("missing", () -> requireSaslLayer(true, true, Map.of()));
        rejected("incomplete", () ->
                requireSaslLayer(false, true, protectedResult));
        rejected("zeroSize", () -> requireSaslLayer(true, true, Map.of(
                Sasl.QOP, "auth-conf", Sasl.RAW_SEND_SIZE, "0")));
    }
}
```

Chạy bằng JDK 17+:

```shell
javac SaslQopPolicyDemo.java
java SaslQopPolicyDemo
```

Stdout:

```text
accepted=auth-conf limit=1024
auth=REJECTED
missing=REJECTED
incomplete=REJECTED
zeroSize=REJECTED
```

Chính sách trong mã chấp nhận `auth-int` hoặc `auth-conf`. Nếu yêu cầu riêng là bí mật từ SASL, phải chỉ chấp nhận `auth-conf`. Con số 1.024 là dữ liệu thử nghiệm, không phải hằng số chuẩn cho mọi cơ chế.

Trong tích hợp thật:

1. Hoàn tất và kiểm tra đầy đủ kết quả cơ chế cùng chỉ báo thành công của giao thức.
2. Đọc các thuộc tính từ `getNegotiatedProperty()` của đúng đối tượng kết nối.
3. Áp dụng chính sách chấp nhận.
4. Cài lớp bảo vệ và giới hạn gửi/nhận trước khi cho phép dữ liệu tiếp theo.

Hàm `requireSaslLayer()` không kiểm tra TLS hoặc danh tính máy chủ. Các giá trị boolean của nó phải được lấy từ trạng thái thật mà thư viện giao thức quản lý, không được đặt thành `true` để vượt kiểm tra.

## 8. QOP của SASL và TLS phải được đánh giá riêng

`auth` không có lớp bảo vệ dữ liệu SASL, nhưng kết nối có thể vẫn được bảo vệ bằng TLS đã xác minh đúng đối tác. Ngược lại, `auth-conf` không tự chứng minh TLS đang hoạt động.

| Thiết kế | Ý nghĩa |
| --- | --- |
| SASL `auth` trên TLS đã xác minh | Xác thực qua SASL, bảo vệ dữ liệu qua TLS |
| SASL `auth-int` | Lớp SASL bảo vệ toàn vẹn; không tự có bí mật từ SASL |
| SASL `auth-conf` | Lớp SASL bảo vệ toàn vẹn và bí mật theo cơ chế |
| Có cả TLS và lớp bảo vệ SASL | Hai lớp có thể cùng tồn tại nếu giao thức và triển khai cho phép |

Chính sách có thể yêu cầu “dữ liệu phải có bí mật trên toàn tuyến” hoặc cụ thể hơn “phải có lớp SASL auth-conf”. Hai yêu cầu đó không đồng nhất. Cần ghi rõ trước khi thiết kế cổng kiểm tra.

Không đổi `auth` thành nhãn `auth-conf` trong log vì bên dưới có TLS. Ghi riêng cơ chế SASL, QOP thực tế, phiên bản/bộ mã TLS và trạng thái kiểm tra danh tính phù hợp. Mô hình kết hợp các API được trình bày trong [hướng dẫn Java SASL](https://docs.oracle.com/en/java/javase/25/security/java-sasl-api-programming-and-deployment-guide1.html).

Nếu có cả hai lớp, thứ tự bọc/mở phải đúng phần tích hợp: byte giao thức đi qua các lớp theo một thứ tự, phía nhận tháo theo chiều ngược lại. Không tráo `SaslClient.wrap()` với `SSLEngine.wrap()`.

## 9. Những lỗi cần đưa vào kiểm thử

| Ca kiểm thử | Điều cần chứng minh |
| --- | --- |
| Hai phía không có QOP chung | Xác thực/thiết lập lớp không được coi là sẵn sàng |
| Yêu cầu bí mật nhưng kết quả chỉ toàn vẹn | Chính sách từ chối |
| Thiếu hoặc không nhận diện QOP | Không đoán thành mức mạnh |
| Gọi wrap trước hoàn tất | Không có đường nghiệp vụ dựa vào trạng thái đó |
| Token bị sửa hoặc cắt ngắn | Không giao dữ liệu chưa kiểm chứng cho ứng dụng |
| Trường độ dài vượt giới hạn | Từ chối trước khi cấp phát lớn |
| Thông điệp lớn hơn RAW_SEND_SIZE | Chia đầu vào hợp lệ và bảo toàn dữ liệu ứng dụng |
| Đọc mạng từng phần hoặc gộp nhiều token | Phân tách đúng bộ đệm bảo vệ |
| Chỉ một chiều có kích thước nhỏ | Mỗi chiều tuân thủ đúng giới hạn riêng |

Khi kiểm thử mật mã thật, dùng cơ chế hiện hành và hạ tầng đúng của môi trường. Ví dụ kiểm tra chính sách bằng dữ liệu giả lập giúp kiểm tra nhánh logic, nhưng không thay thế ca tích hợp phát hiện giả mạo dữ liệu.

## 10. Tự kiểm tra

1. `auth` có làm dữ liệu sau xác thực được mã hóa bằng SASL không? **Không.**
2. `auth-int` khác `auth-conf` ở đâu? **Bí mật; cả hai đều có toàn vẹn theo cơ chế.**
3. Cấu hình `auth-conf,auth-int` có bắt buộc đạt bí mật không? **Không; danh sách cho phép cả hai mức.**
4. Lấy QOP thực tế ở đâu? **Từ thuộc tính đã thương lượng của đối tượng SASL sau hoàn tất.**
5. Vì sao không dùng MAX_BUFFER thay RAW_SEND_SIZE? **Chúng mô tả vai trò kích thước khác nhau và có phần dữ liệu bảo vệ bổ sung.**
6. `auth` trên TLS có được đổi tên thành `auth-conf` không? **Không; phải ghi nhận và kiểm tra hai lớp riêng.**
7. Có chuỗi `auth-conf` trong một Map có chứng minh mật mã đã chạy không? **Không; phải có trao đổi thực và lớp bảo vệ thực được cài đúng.**
