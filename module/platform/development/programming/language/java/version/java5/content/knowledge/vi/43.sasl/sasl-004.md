# CallbackHandler và việc cung cấp thông tin xác thực trong SASL

## 1. Vì sao cơ chế SASL không tự đọc mật khẩu?

Một cơ chế SASL biết cách tạo và kiểm tra dữ liệu trao đổi của cơ chế đó. Nó không nên phải biết ứng dụng dùng cửa sổ nhập liệu, dòng lệnh, cấu hình dịch vụ hay kho bí mật để lấy thông tin xác thực.

`CallbackHandler` là điểm kết nối giữa hai phần:

- **Cơ chế xác thực** phát yêu cầu bằng các đối tượng callback.
- **Ứng dụng** xử lý yêu cầu, lấy dữ liệu từ nguồn phù hợp rồi điền vào callback.
- **Cơ chế** đọc dữ liệu đã được cung cấp để tiếp tục trao đổi.

Đây là cách đảo chiều yêu cầu: không phải ứng dụng tự đoán lúc nào cơ chế cần mật khẩu, mà cơ chế thông báo nhu cầu qua hợp đồng callback.

Theo [CallbackHandler API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/security/auth/callback/CallbackHandler.html), handler có thể tương tác với người dùng hoặc lấy dữ liệu từ nguồn khác. `handle(Callback[])` có thể báo `IOException` hoặc `UnsupportedCallbackException`.

API này vẫn được sử dụng trên Java hiện đại. Bài học không phụ thuộc một cơ chế SASL cũ và không hướng dẫn bỏ qua chính sách bảo mật để đăng nhập được.

## 2. Luồng dữ liệu và ranh giới trách nhiệm

```text
Thư viện giao thức điều khiển trao đổi SASL
                    |
          Cơ chế cần thông tin
                    |
        handle(Callback[] callbacks)
                    |
   Handler của ứng dụng chọn nguồn dữ liệu
                    |
        Điền dữ liệu vào callback
                    |
    Cơ chế đọc dữ liệu và tiếp tục xử lý
```

Phân chia này giúp thay nguồn bí mật mà không viết lại thuật toán cơ chế. Ví dụ, môi trường phát triển có thể dùng một nguồn thử nghiệm, còn dịch vụ triển khai dùng kho bí mật được cấu hình theo tài khoản dịch vụ.

Handler không tự:

- Mở kết nối mạng cho giao thức ứng dụng.
- Thương lượng TLS hoặc xác minh tên máy chủ.
- Quyết định mật khẩu đã được máy chủ chấp nhận.
- Cấp mọi quyền nghiệp vụ cho danh tính đã đăng nhập.
- Biến một cơ chế không được cài đặt thành cơ chế có sẵn.

Nếu handler điền xong mật khẩu, điều vừa hoàn tất là **cung cấp đầu vào**, không phải **đăng nhập thành công**.

## 3. Nhận diện callback theo kiểu, không theo vị trí hoặc lời nhắc

Một lần gọi `handle()` nhận một mảng callback. Không giả định phần tử đầu luôn là tên và phần tử thứ hai luôn là mật khẩu. Cơ chế có thể yêu cầu một nhóm thông tin hoặc gọi handler nhiều lần.

Cách phân nhánh phù hợp là kiểm tra kiểu đối tượng:

```java
// Đoạn minh họa, không phải chương trình độc lập.
if (callback instanceof NameCallback name) {
    name.setName(configuredUsername);
} else if (callback instanceof PasswordCallback password) {
    // Lấy bí mật và điền password theo vòng đời đã thiết kế.
} else {
    throw new UnsupportedCallbackException(callback);
}
```

Không dùng `getPrompt().contains("password")` để quyết định trường nào chứa bí mật. Lời nhắc dành cho trình bày, có thể khác theo ngôn ngữ hoặc nhà cung cấp, và không phải giao diện máy ổn định.

### 3.1. NameCallback

`NameCallback` yêu cầu thông tin tên. Handler trả lời bằng `setName(...)`; `getDefaultName()` là giá trị gợi ý nếu có, khác với tên đã được handler cung cấp qua `getName()`.

Ở máy khách, tên có thể đến từ tài khoản đã cấu hình. Không mặc định dùng tên người dùng hệ điều hành thay cho tài khoản dịch vụ. Ở máy chủ, ý nghĩa giá trị tên được cơ chế đưa vào cần được hiểu theo hợp đồng cơ chế; không tái sử dụng handler máy khách vốn luôn ghi một tên cố định.

Xem [NameCallback API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/security/auth/callback/NameCallback.html).

### 3.2. PasswordCallback

`PasswordCallback` cho phép điền mật khẩu bằng `char[]`. Hai chi tiết quan trọng:

- `setPassword(char[])` lưu một **bản sao** của mảng đầu vào.
- `getPassword()` trả một **bản sao** của dữ liệu đã lưu.

Vì vậy, xóa mảng tạm sau `setPassword()` không xóa ngay dữ liệu mà callback cần cung cấp cho cơ chế. Nhưng sau đó vẫn còn bản sao trong callback và có thể có các bản sao khác do bên tiêu thụ tạo.

Hợp đồng sao chép và `clearPassword()` nằm trong [PasswordCallback API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html).

Tham số `echoOn` mô tả việc có hiển thị ký tự khi nhập hay không. Nó không tự mã hóa bộ nhớ, không bảo vệ log và không tự tạo một hộp nhập liệu.

## 4. Chọn nguồn thông tin xác thực đúng ngữ cảnh

Một handler cho chương trình tương tác có thể đọc từ console hoặc giao diện. Handler của dịch vụ chạy nền thường phải dùng nguồn cấu hình/kho bí mật, vì không có người ngồi nhập mật khẩu khi một kết nối được tạo lại.

Thiết kế nguồn dữ liệu nên trả lời rõ các câu hỏi:

| Câu hỏi | Lý do cần xác định |
| --- | --- |
| Bí mật thuộc tài khoản và môi trường nào? | Tránh dùng nhầm tài khoản giữa các kết nối |
| Mỗi lần đọc có tạo mảng riêng không? | Quyết định ai được xóa mảng sau sử dụng |
| Cơ chế có thể gọi handler nhiều lần không? | Nguồn dữ liệu phải còn hợp lệ trong cả trao đổi |
| Bí mật thay đổi giữa một lần xác thực thì xử lý thế nào? | Tránh kết hợp dữ liệu không nhất quán |
| Đọc kho bí mật thất bại hoặc hết thời gian chờ thì sao? | Không tự thay bằng bí mật rỗng hoặc bí mật mặc định |
| Handler có bị dùng đồng thời không? | Không chia sẻ bộ đệm nhạy cảm thiếu đồng bộ |

Trong một luồng xử lý sự kiện, việc handler truy cập kho bí mật chậm hoặc chờ người dùng có thể giữ luồng gọi. Cần thiết kế nơi thực thi trao đổi SASL phù hợp; không giả định callback là lời gọi bất đồng bộ chỉ vì có chữ “callback”.

Không đọc token/mật khẩu từ một trường tùy ý do phía bên kia chọn rồi trả lại bí mật cho đối tác khác. Nguồn thông tin xác thực phải gắn với tài khoản, cơ chế và dịch vụ đích đã được ứng dụng cho phép.

## 5. Quản lý vòng đời mật khẩu: ai xóa bản nào?

Một mô hình rõ ràng:

```text
Nguồn bí mật cấp char[] mới
            |
Handler gọi setPassword()
            |         \
            |          Bản sao trong PasswordCallback
            |
Handler xóa mảng tạm của mình
                      |
        Cơ chế đọc/tiêu thụ thông tin
                      |
      Bên sở hữu xóa các bản sao hết hạn
```

Các nguyên tắc triển khai:

1. Nguồn bí mật chuyển quyền sở hữu một mảng mới cho handler thì handler có thể xóa nó sau `setPassword()`.
2. Nếu nguồn chỉ cho mượn một bộ đệm dùng chung, không tự xóa bộ đệm đó; cần hợp đồng sở hữu khác hoặc tạo bản sao phù hợp.
3. Không gọi `clearPassword()` ngay sau `setPassword()` bên trong handler trước khi cơ chế đọc được dữ liệu.
4. Bên nhận bản sao từ `getPassword()` phải xóa bản sao đó khi dùng xong.
5. Dọn tài nguyên và dữ liệu nhạy cảm của đối tượng SASL khi trao đổi kết thúc theo API, kể cả đường lỗi.

Không chuyển mật khẩu thành `String` chỉ để tiện log, nối chuỗi hoặc so sánh. `String` không có thao tác xóa nội dung chủ động như một mảng ký tự do ứng dụng sở hữu.

Dùng `char[]` và xóa bản sao giúp giảm thời gian giữ bí mật ở mức ứng dụng; nó không phải bảo đảm tuyệt đối rằng JVM, hệ điều hành hoặc thư viện không có bản sao nào khác. Cũng không giả định `clearPassword()` phải làm `getPassword()` trả `null`: mục tiêu là xóa dữ liệu, không kiểm tra một giá trị trả về không được hợp đồng cam kết.

## 6. Ví dụ Java 17+: handler máy khách và nguồn bí mật có quyền sở hữu rõ ràng

Chương trình dưới đây chỉ minh họa cơ chế callback. Nó không tạo kết nối SASL thật và không chứng minh mật khẩu được một máy chủ chấp nhận.

Nguồn bí mật trong `main()` tạo dữ liệu thử nghiệm cố định để kiểm tra vòng đời mảng; không dùng cách viết dữ liệu thử nghiệm này làm nguồn mật khẩu triển khai. Biến `issued` giữ tham chiếu chỉ để phép kiểm tra quan sát mảng đã được xóa.

Lưu thành `CredentialCallbackDemo.java`:

```java
import java.io.IOException;
import java.util.Arrays;
import java.util.Objects;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.TextInputCallback;
import javax.security.auth.callback.UnsupportedCallbackException;

public class CredentialCallbackDemo {
    @FunctionalInterface
    interface SecretSource {
        // Transfers ownership of a fresh char[] to the caller.
        char[] read() throws IOException;
    }

    static final class ClientCredentials implements CallbackHandler {
        private final String username;
        private final SecretSource source;

        ClientCredentials(String username, SecretSource source) {
            this.username = Objects.requireNonNull(username);
            this.source = Objects.requireNonNull(source);
        }

        @Override
        public void handle(Callback[] callbacks)
                throws IOException, UnsupportedCallbackException {
            // Reject an unsupported batch before reading any secret.
            for (Callback callback : callbacks) {
                if (!(callback instanceof NameCallback)
                        && !(callback instanceof PasswordCallback)) {
                    throw new UnsupportedCallbackException(callback);
                }
            }

            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName(username);
                } else if (callback instanceof PasswordCallback password) {
                    char[] secret = source.read();
                    if (secret == null) {
                        throw new IOException("Credential unavailable");
                    }
                    try {
                        password.setPassword(secret);
                    } finally {
                        Arrays.fill(secret, '\0');
                    }
                }
            }
        }
    }

    private static boolean isZeroed(char[] value) {
        for (char c : value) {
            if (c != '\0') {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) throws Exception {
        // Synthetic test data only; no real account or connection.
        char[][] issued = new char[1][];
        SecretSource source = () -> {
            issued[0] = new char[] {'t', 'e', 's', 't'};
            return issued[0];
        };
        CallbackHandler handler = new ClientCredentials("learner", source);
        NameCallback name = new NameCallback("Account:");
        PasswordCallback password = new PasswordCallback("Secret:", false);

        char[] received = null;
        try {
            handler.handle(new Callback[] {password, name});
            received = password.getPassword();
            System.out.println("name=" + name.getName());
            System.out.println("passwordLength=" + received.length);
            System.out.println("sourceWiped=" + isZeroed(issued[0]));
        } finally {
            if (received != null) {
                Arrays.fill(received, '\0');
            }
            password.clearPassword();
        }

        try {
            handler.handle(new Callback[] {new TextInputCallback("Other:")});
        } catch (UnsupportedCallbackException expected) {
            System.out.println("unknown=UnsupportedCallbackException");
        }
    }
}
```

Chạy bằng JDK 17+:

```shell
javac CredentialCallbackDemo.java
java CredentialCallbackDemo
```

Stdout:

```text
name=learner
passwordLength=4
sourceWiped=true
unknown=UnsupportedCallbackException
```

Các hành vi đã được minh họa:

- Mảng callback cố ý đặt mật khẩu trước tên; handler vẫn điền đúng theo kiểu.
- Handler kiểm tra toàn bộ nhóm callback trước khi đọc bí mật, để callback chưa hỗ trợ không gây một lần đọc bí mật vô ích.
- Mảng do nguồn chuyển cho handler đã bị xóa, còn callback vẫn giữ được bản sao để bên tiêu thụ lấy.
- Bản sao nhận trong `main()` và dữ liệu trong callback được dọn sau khi dùng.
- Callback ngoài phạm vi hỗ trợ bị từ chối rõ ràng.

Handler này hỗ trợ **chỉ NameCallback và PasswordCallback**. Nó không tự trở thành handler đầy đủ cho mọi cơ chế SASL. Vòng kiểm tra kiểu trước không biến toàn bộ `handle()` thành giao dịch nguyên tử: nếu một lần đọc bí mật sau đó thất bại, các callback đã điền trước đó có thể đã có dữ liệu. Phần sở hữu trao đổi phải có đường dọn dữ liệu trên lỗi.

Trong triển khai thật, không ghi độ dài mật khẩu vào log chỉ vì ví dụ học tập có in nó. Thông tin chẩn đoán cần được giới hạn theo chính sách dữ liệu nhạy cảm.

## 7. Truyền handler cho SASL và giữ nó sống đủ lâu

Đoạn tích hợp khái niệm:

```java
// Minh họa; danh sách cơ chế, ngữ cảnh và handler do ứng dụng cấu hình.
SaslClient client = Sasl.createSaslClient(
        allowedMechanisms,
        authorizationId,
        protocol,
        serverName,
        properties,
        credentialsHandler);

if (client == null) {
    throw new IllegalStateException("No suitable SASL client");
}

// Thư viện giao thức điều khiển các lượt evaluateChallenge(),
// xử lý kết quả máy chủ, rồi dispose() khi không còn dùng client.
```

Không giả định factory đã đọc hết thông tin xác thực ngay khi trả về. Tùy cơ chế, callback có thể xuất hiện khi khởi tạo hoặc ở một bước xử lý trao đổi sau đó. Nguồn bí mật cần còn khả dụng trong thời gian trao đổi có thể yêu cầu nó.

Factory có thể trả `null` nếu không tạo được cơ chế phù hợp, theo [Sasl API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html). Thiếu cơ chế hoặc thiếu callback không phải lý do tự hạ chính sách xác thực.

Một số cơ chế cần thông tin xác thực qua API khác hoặc callback riêng của nhà cung cấp. Không đưa mọi token, khóa hoặc chứng thư vào `PasswordCallback` theo suy đoán; phải theo đúng tài liệu cơ chế và phần tích hợp đang dùng.

## 8. Realm và callback chuyên biệt

Một số cơ chế cần ngữ cảnh miền xác thực (realm):

| Callback | Cách trả lời |
| --- | --- |
| `RealmCallback` | Điền realm bằng `setText(...)` |
| `RealmChoiceCallback` | Chọn chỉ số hợp lệ trong danh sách được cung cấp |

`RealmCallback` có thể có giá trị mặc định; `RealmChoiceCallback` có danh sách lựa chọn và quy định chọn một/nhiều. Không gán một chỉ số cố định mà không kiểm tra danh sách.

Realm không tự đồng nghĩa tên DNS, tổ chức, tenant hay quyền truy cập. Ý nghĩa phụ thuộc cơ chế. Handler nên có quy tắc chọn realm đã được ứng dụng phê duyệt; không chọn bất kỳ realm được gợi ý chỉ để cơ chế tiếp tục.

Các hợp đồng nằm trong [RealmCallback API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/RealmCallback.html) và [RealmChoiceCallback API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/RealmChoiceCallback.html).

Ví dụ chính của bài cố ý từ chối cả hai kiểu này vì chưa triển khai chính sách realm. Muốn hỗ trợ một cơ chế cần realm, phải mở rộng có chủ đích và kiểm thử lựa chọn đúng/sai; không lặng lẽ bỏ qua callback.

## 9. AuthorizeCallback là quyết định quyền đại diện, không phải ô nhập mật khẩu

Phía máy chủ có thể nhận `AuthorizeCallback` sau khi một danh tính đã được xác thực, để quyết định danh tính đó có được hoạt động dưới authzid yêu cầu hay không.

Ví dụ suy luận: `service-a` đã chứng minh thông tin xác thực nhưng yêu cầu dùng danh tính `administrator`. Việc biết mật khẩu của `service-a` không tự cho quyền đại diện `administrator`.

Handler phía máy chủ phải dùng chính sách ánh xạ/ủy quyền thật rồi gọi `setAuthorized(...)`. Không triển khai nhánh nhận `AuthorizeCallback` bằng `setAuthorized(true)` cho mọi trường hợp.

Ngay cả việc cho phép authcid tương ứng authzid cũng cần quy tắc định danh và chuẩn hóa phù hợp hệ thống. Không suy ra mọi quyền nghiệp vụ từ một phép so sánh chuỗi tên.

Vai trò của callback này được định nghĩa trong [AuthorizeCallback API](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/AuthorizeCallback.html). Handler máy khách trong ví dụ không xử lý nó; hai phía có trách nhiệm và nguồn dữ liệu khác nhau.

## 10. Xử lý lỗi và kiểm thử

Không hỗ trợ một callback thì ném `UnsupportedCallbackException` kèm đối tượng callback tương ứng. Đây là tín hiệu “handler không thực hiện hợp đồng này”, khác với lỗi đọc nguồn dữ liệu. Định nghĩa ngoại lệ nằm trong [UnsupportedCallbackException API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/security/auth/callback/UnsupportedCallbackException.html).

Nếu kho bí mật không truy cập được, dùng lỗi phù hợp và ngừng lần xác thực đó; không trả mật khẩu rỗng, bí mật dự phòng hoặc dữ liệu tài khoản khác. Thông báo lỗi không được chứa mật khẩu hoặc toàn bộ đối tượng chứa bí mật.

Các ca kiểm thử hữu ích:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Thay thứ tự Name/Password callback | Vẫn điền đúng theo kiểu |
| Có callback ngoài danh sách hỗ trợ | Báo lỗi rõ ràng, không bỏ qua |
| Nguồn trả `null` hoặc ném lỗi | Không giả thành công, dọn dữ liệu đã cấp |
| Nguồn trả mảng mới | Mảng tạm được xóa sau khi callback nhận bản sao |
| Cơ chế gọi handler nhiều lần | Dữ liệu vẫn đúng tài khoản và hợp đồng sở hữu |
| Đổi realm hoặc authzid ngoài chính sách | Bị từ chối |
| Hai kết nối dùng tài khoản khác nhau | Không lẫn thông tin xác thực |

Không cần dùng một cơ chế mật mã lỗi thời để kiểm tra handler. Có thể kiểm thử trực tiếp các callback như chương trình minh họa, rồi thêm kiểm thử tích hợp với cơ chế hiện hành mà hệ thống thật sử dụng.

## 11. Tự kiểm tra

1. Ai tạo callback yêu cầu thông tin? **Dịch vụ/cơ chế bảo mật; handler của ứng dụng trả lời yêu cầu.**
2. Handler có phải nơi kết luận mật khẩu đúng không? **Không; cung cấp dữ liệu đầu vào khác với hoàn tất xác thực.**
3. Vì sao phải kiểm tra kiểu thay vì vị trí? **Thứ tự và nhóm callback phụ thuộc cơ chế, không phải quy ước cố định của ứng dụng.**
4. Vì sao xóa mảng nguồn sau `setPassword()` vẫn dùng được? **Callback lưu bản sao theo hợp đồng API.**
5. Vì sao không `clearPassword()` ngay trước khi handler trả về? **Cơ chế có thể chưa đọc dữ liệu callback.**
6. Callback không hỗ trợ có được bỏ qua không? **Không; phải báo lỗi rõ ràng.**
7. Nhận `AuthorizeCallback` có được luôn chấp nhận không? **Không; phải áp dụng chính sách quyền đại diện của máy chủ.**
