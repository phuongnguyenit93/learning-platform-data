# Không đưa mật khẩu, token hoặc dữ liệu nhạy cảm vào biểu diễn `toString()`

## 1. Vì sao `toString()` là điểm dễ rò rỉ thông tin?

`Object.toString()` trả về một chuỗi biểu diễn đối tượng. Các lớp thường ghi đè `toString()` để giúp lập trình viên đọc log, thông báo lỗi hoặc kết quả gỡ lỗi nhanh hơn. Tuy nhiên **chuỗi biểu diễn có thể rời khỏi phạm vi đang kiểm soát**: nó có thể được ghi vào log, chuyển tới dịch vụ quan sát hệ thống, lưu trong báo cáo lỗi, xuất hiện trong màn hình hỗ trợ hoặc được chia sẻ khi xử lý sự cố.

Ví dụ, đối tượng đăng nhập có thể có các trường `accountId`, `password` và `accessToken`. Một `toString()` liệt kê mọi trường sẽ vô tình tiết lộ thông tin xác thực khi ai đó chỉ định in đối tượng để theo dõi luồng xử lý. Mật khẩu và token có thể cho phép truy cập tài khoản hoặc hệ thống khi bị lộ; ngay cả log có giới hạn quyền cũng có thể bị sao chép, lưu lâu hoặc truy cập bởi nhiều thành phần hơn phạm vi xử lý bí mật ban đầu.

**Nguyên tắc mặc định:** `toString()` phục vụ **chẩn đoán** chứ không phải xuất toàn bộ trạng thái. Chỉ đưa vào những thuộc tính **đã được xác định là an toàn để ghi log**. Không bao giờ đưa mật khẩu, secret, khóa riêng hoặc giá trị token truy cập vào chuỗi biểu diễn.

Cách định nghĩa một biểu diễn tốt:

- Người đọc nhận ra **loại đối tượng** và **ngữ cảnh đủ để chẩn đoán**.
- Chuỗi không chứa thông tin xác thực hoặc dữ liệu cá nhân vượt quá mục đích được phép.
- Nếu lớp được bổ sung trường nhạy cảm về sau, biểu diễn không tự động lộ trường mới.
- Biểu diễn có định dạng ổn định, gọn, dễ hiểu và không chứa dữ liệu đầu vào chưa kiểm soát có thể phá cấu trúc log.

## 2. Những loại dữ liệu không nên in trong `toString()`

Tùy ứng dụng và phân loại dữ liệu, các nhóm sau thường cần được loại khỏi biểu diễn:

| Nhóm dữ liệu | Ví dụ | Rủi ro khi xuất vào biểu diễn |
| --- | --- | --- |
| Mật khẩu, PIN, OTP và mã khôi phục | `password`, `pin`, `oneTimeCode` | Có thể dùng để xác thực hoặc chiếm quyền truy cập |
| Token xác thực và phiên | Access token, refresh token, session cookie, bearer token | Có thể bị tái sử dụng để truy cập phiên hoặc API |
| Khóa và bí mật kỹ thuật | API key, client secret, private key, connection-string chứa mật khẩu | Cho phép truy cập dịch vụ, ký/giải mã hoặc kết nối trái phép |
| Header/query nhạy cảm | `Authorization`, `Cookie`, URL có token trong query string | Giá trị bí mật có thể lọt qua log HTTP hoặc exception |
| Thông tin cá nhân | Email, điện thoại, địa chỉ, giấy tờ, dữ liệu tài chính hoặc sức khỏe | Có thể xâm phạm riêng tư hoặc vượt quyền sử dụng dữ liệu |
| Nội dung yêu cầu/phản hồi | JSON chứa thông tin tài khoản, hồ sơ, thông tin thanh toán | Có thể vô tình kéo theo hàng loạt trường nhạy cảm |

Không phải mọi `id`, email hay số tham chiếu đều được phép xuất. Một mã định danh có thể là thông tin cá nhân hoặc bí mật trong ngữ cảnh cụ thể. Nếu cần kết nối các sự kiện, ưu tiên **correlation ID được thiết kế riêng cho việc quan sát hệ thống**, không mang khả năng truy cập và đã được duyệt để ghi log.

Đừng cho rằng chỉ mật khẩu thô mới là bí mật. Hash mật khẩu, mã xác minh, token đã hết hạn, khóa thử nghiệm, các giá trị “một phần” hoặc tài liệu nhận dạng có thể vẫn nhạy cảm. Quyết định chính sách phải dựa trên mục đích sử dụng và mức độ rủi ro, không dựa đơn thuần vào tên trường.

## 3. `toString()` có thể bị gọi gián tiếp

Một lập trình viên có thể không viết `object.toString()` nhưng vẫn làm biểu diễn được sử dụng:

~~~java
System.out.println(object);              // Gọi biểu diễn chuỗi đối tượng.
String message = "Request: " + object;    // Nối chuỗi sẽ dùng biểu diễn.
String text = String.format("%s", object);
String display = String.valueOf(object);
~~~

Đây là những **đoạn minh họa**, giả định biến `object` đã được khai báo. Với một số API logging có tham số, ví dụ lời gọi kiểu `logger.info("request={}", request)` của các thư viện phổ biến, formatter có thể chuyển đối số thành chuỗi khi ghi log. Việc trì hoãn định dạng hoặc kiểm tra mức log có thể ảnh hưởng thời điểm đánh giá, nhưng **không biến `request.toString()` thành an toàn** khi thông điệp thực sự được ghi.

Các luồng khác cũng có thể gián tiếp gọi biểu diễn: tạo chuỗi của exception, ghi giá trị vào thông báo assert, xuất một đối tượng trong trang quản trị hoặc thu thập snapshot phục vụ điều tra sự cố.

**Điều cần tránh là đưa cả đối tượng chứa bí mật vào thông điệp**, nhất là khi không kiểm soát được cách nó được chuyển sang chuỗi. Thay vì ghi `request`, hãy ghi các trường cho phép như loại hành động, kết quả xử lý và correlation ID đã được phân loại.

## 4. Bẫy của `record`: `toString()` được sinh sẵn và chứa mọi component

Từ Java 16, `record` có các phương thức tổng hợp `equals()`, `hashCode()` và `toString()` nếu bạn không tự khai báo. Phương thức `toString()` được sinh biểu diễn tên record cùng các **component** và giá trị tương ứng. Vì thế dùng record cho dữ liệu chứa bí mật vẫn có nguy cơ rò rỉ, dù bạn không viết một dòng `toString()` thủ công nào.

### Ví dụ chạy được: phát hiện nguy cơ nhưng không in giá trị bí mật

Tạo tệp `UnsafeRecordToStringDemo.java`:

~~~java
public class UnsafeRecordToStringDemo {
    record LoginData(String accountId, String password, String accessToken) {}

    public static void main(String[] args) {
        // Chỉ sử dụng chuỗi giả để kiểm tra hành vi, không đưa secret thật vào mã.
        LoginData login = new LoginData(
                "account-demo",
                "example-password",
                "example-token"
        );

        String rendered = login.toString();

        // Chỉ in kết quả kiểm tra, KHÔNG in rendered hoặc các secret.
        System.out.println("contains account: "
                + rendered.contains(login.accountId()));
        System.out.println("contains password: "
                + rendered.contains(login.password()));
        System.out.println("contains token: "
                + rendered.contains(login.accessToken()));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 UnsafeRecordToStringDemo.java
java UnsafeRecordToStringDemo
~~~

Stdout:

~~~text
contains account: true
contains password: true
contains token: true
~~~

Ví dụ cố ý để record giữ `toString()` mặc định **nhằm phát hiện vấn đề**, nhưng không in ra các giá trị mật khẩu/token. Kết quả `true` cho thấy nếu có mã ghi `System.out.println(login)` hoặc ghép `"login=" + login`, chuỗi biểu diễn sẽ mang các giá trị đó vào đầu ra.

Ngoài `record`, IDE hoặc công cụ sinh mã có thể tạo `toString()` dựa trên toàn bộ field hoặc component. Khi thêm field, chạy lại generator hoặc bật chế độ sinh tự động, cần kiểm tra chính sách loại trừ trường nhạy cảm.

## 5. Chiến lược an toàn hơn: chọn rõ những trường được phép xuất

Cách an toàn khi viết `toString()` cho đối tượng có secret là **allowlist**: chỉ liệt kê thuộc tính được phép hiện ra, thay vì nối tất cả trường rồi cố lọc đi những trường bị cấm.

Ví dụ một phiên xử lý chứa request ID và hai secret. Nếu request ID đã được thiết kế là mã chẩn đoán không nhạy cảm, ta có thể in mã đó và một nhãn cố định mà không sử dụng giá trị secret.

Tạo tệp `SafeSessionToStringDemo.java`:

~~~java
public class SafeSessionToStringDemo {
    record SessionData(String requestId, String password, String accessToken) {
        @Override
        public String toString() {
            return "SessionData[requestId=" + requestId
                    + ", credentials=<redacted>]";
        }
    }

    public static void main(String[] args) {
        SessionData session = new SessionData(
                "req-42",
                "example-password",
                "example-token"
        );

        String representation = session.toString();
        System.out.println(representation);
        System.out.println("contains password: "
                + representation.contains(session.password()));
        System.out.println("contains token: "
                + representation.contains(session.accessToken()));
        System.out.println("same object identity: "
                + (session == session));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeSessionToStringDemo.java
java SafeSessionToStringDemo
~~~

Stdout:

~~~text
SessionData[requestId=req-42, credentials=<redacted>]
contains password: false
contains token: false
same object identity: true
~~~

Đây là ví dụ hoàn chỉnh với dữ liệu giả, dùng nhãn `<redacted>` **cố định** để diễn đạt bí mật đã bị loại khỏi biểu diễn. Không xây dựng nhãn bằng cách nối hoặc lấy một phần thực tế của token rồi hiển thị.

Lợi ích của allowlist:

1. Người đọc biết chính xác những trường nào được đưa ra.
2. Các trường nhạy cảm `password` và `accessToken` không được truy cập trong thân `toString()`.
3. Khi thêm một secret mới vào record, `toString()` tùy chỉnh **không tự động xuất secret đó**.
4. Kết quả ngắn, có nghĩa và thuận tiện cho log, nếu `requestId` thực sự đã được phân loại là an toàn.

Trong môi trường thực tế, hãy kiểm tra rằng giá trị `requestId` cũng không chứa thông tin bí mật hoặc chuỗi do người dùng tự đưa vào. Nếu không chắc, hãy loại luôn trường đó hoặc dùng một correlation ID do hệ thống tạo.

**Lưu ý:** Override `toString()` chỉ thay đổi biểu diễn chuỗi. Nó không xóa password/token khỏi đối tượng, không ngăn accessor truy cập, không bảo vệ việc serialize JSON/XML và không tự giải quyết các quy tắc lưu trữ secret. Record mặc định vẫn sinh `equals/hashCode` dựa trên component, trừ khi các phương thức đó được tự cài đặt; chúng có mục đích khác với chính sách log.

## 6. Vì sao che bằng dấu sao chưa đủ nếu bí mật vẫn đi qua log?

Một số cách xử lý “mask” thông thường có thể vẫn để lộ dữ liệu:

~~~java
// Các đoạn sau là phản ví dụ về thiết kế; không nên dùng để ghi secret.
String partiallyVisible = token.substring(0, 6) + "***";
String suffix = "***" + token.substring(token.length() - 4);
String encoded = java.util.Base64.getEncoder()
        .encodeToString(token.getBytes(java.nio.charset.StandardCharsets.UTF_8));
~~~

Các đoạn là **fragment minh họa**, giả định `token` là chuỗi khác null, đủ dài ở hai cách cắt. Trong chương trình thật, các phép `substring` còn có thể ném lỗi với token quá ngắn; điều đáng chú ý là:

- Đầu/cuối token có thể vẫn nhạy cảm hoặc có thể hỗ trợ khớp một token cụ thể với hoạt động người dùng.
- Base64 là **mã hóa biểu diễn**, không phải mã hóa bảo mật hay xóa thông tin; có thể đảo ngược.
- Việc băm trực tiếp secret rồi đưa hash vào log vẫn tạo một giá trị tương quan cố định, có thể lộ mối liên hệ giữa sự kiện hoặc hỗ trợ suy đoán nếu không có mô hình đe dọa phù hợp.
- Thay thế mẫu chuỗi toàn cục sau khi secret đã bị ghép vào log rất dễ bỏ sót đường đi, định dạng mới hoặc giá trị nhạy cảm nằm sâu trong đối tượng.

Trong `toString()`, tốt nhất **không tham chiếu đến giá trị secret**. Nếu có yêu cầu rất cụ thể về cách hiển thị trạng thái (ví dụ `configured`/`absent`) thì chỉ làm khi đã được đánh giá là an toàn, bởi ngay cả sự có mặt của thông tin xác thực đôi khi cũng là thông tin nhạy cảm.

Không cần in prefix, suffix, chiều dài token hay trạng thái xác thực nếu mục tiêu chỉ là xác định đã xử lý request nào. Dùng mã chẩn đoán độc lập thay thế.

## 7. Rò rỉ qua object lồng nhau, collection và `Map.toString()`

Bỏ trường secret trực tiếp chưa đủ nếu `toString()` của lớp ngoài **gọi `toString()` của đối tượng con** mà đối tượng đó chứa secret.

Ví dụ:

~~~java
record Credential(String token) {}
record Request(String requestId, Credential credential) {}
~~~

Nếu cả hai giữ `toString()` mặc định, biểu diễn của `Request` chứa biểu diễn của `Credential`, và `Credential` chứa giá trị token. Tương tự, cách viết `return "Request{headers=" + headers + "}";` có thể gọi `Map.toString()` và in những entry như `Authorization` hoặc `Cookie`. `List.toString()` cũng có thể dẫn đến `toString()` của từng phần tử.

### Ví dụ chạy được: chứng minh rò rỉ gián tiếp

Tạo tệp `NestedToStringDemo.java`:

~~~java
public class NestedToStringDemo {
    record Credential(String token) {}
    record UnsafeRequest(String requestId, Credential credential) {}

    record SafeRequest(String requestId, Credential credential) {
        @Override
        public String toString() {
            return "SafeRequest[requestId=" + requestId + "]";
        }
    }

    public static void main(String[] args) {
        Credential credential = new Credential("example-token");
        UnsafeRequest unsafe = new UnsafeRequest("req-9", credential);
        SafeRequest safe = new SafeRequest("req-9", credential);

        // Chỉ in boolean kiểm tra, không xuất chuỗi unsafe.
        System.out.println("nested leak: "
                + unsafe.toString().contains(credential.token()));
        System.out.println("safe excludes nested token: "
                + !safe.toString().contains(credential.token()));
        System.out.println("safe representation: " + safe);
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestedToStringDemo.java
java NestedToStringDemo
~~~

Stdout:

~~~text
nested leak: true
safe excludes nested token: true
safe representation: SafeRequest[requestId=req-9]
~~~

Khi thiết kế đối tượng lồng nhau, hãy kiểm tra mọi vị trí mà biểu diễn lớp ngoài **đưa cả object, collection, header map, URL hoặc payload** vào chuỗi. Một `toString()` an toàn không nên phụ thuộc vào việc mọi đối tượng con đều tự biết ẩn secret.

Nếu cần mô tả collection, có thể chỉ xuất số phần tử hoặc một thống kê được phép, chẳng hạn `itemsCount=3`, thay vì nối `items`. Nếu cần mô tả HTTP request, hãy dùng những metadata đã được chọn như phương thức, route chuẩn hóa hoặc correlation ID; tránh xuất nguyên header, query string và body khi chưa phân loại.

## 8. Ví dụ kiểu class thông thường: chỉ xuất metadata có kiểm soát

Record không phải trường hợp duy nhất. Một lớp POJO cũng nên override `toString()` thủ công nếu nó chứa dữ liệu nhạy cảm và có khả năng xuất hiện trong log.

Tạo tệp `SafeAccountToStringDemo.java`:

~~~java
public class SafeAccountToStringDemo {
    static final class Account {
        private final String correlationId;
        private final String passwordHash;
        private final String recoveryCode;

        Account(String correlationId, String passwordHash, String recoveryCode) {
            this.correlationId = correlationId;
            this.passwordHash = passwordHash;
            this.recoveryCode = recoveryCode;
        }

        @Override
        public String toString() {
            return "Account{correlationId='" + correlationId + "'}";
        }

        boolean representationContainsSecret() {
            String text = toString();
            return text.contains(passwordHash) || text.contains(recoveryCode);
        }
    }

    public static void main(String[] args) {
        Account account = new Account(
                "trace-100",
                "example-hash-value",
                "example-recovery-code"
        );

        System.out.println(account);
        System.out.println("contains secret: "
                + account.representationContainsSecret());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeAccountToStringDemo.java
java SafeAccountToStringDemo
~~~

Stdout:

~~~text
Account{correlationId='trace-100'}
contains secret: false
~~~

Lưu ý `passwordHash` vẫn có thể là dữ liệu nhạy cảm và không được xem là an toàn chỉ vì đã được băm. Trong ví dụ này, chuỗi đầu ra chứa **duy nhất** correlation ID giả đã được cho phép. Tên trường bí mật có thể xuất hiện trong mã nguồn để minh họa nhưng **không có mặt trong kết quả `toString()`**.

Cũng không nên dùng tên/ID do người dùng nhập một cách tùy tiện. Nếu dữ liệu đầu vào có thể mang xuống dòng hoặc ký tự điều khiển, hãy chuẩn hóa/escape hoặc thay bằng mã chẩn đoán do hệ thống sinh; xem phần tiếp theo.

## 9. Tránh đưa dữ liệu không tin cậy làm hỏng cấu trúc log

Ngay cả trường không chứa secret cũng có thể là dữ liệu **không tin cậy**. Nếu `toString()` nối thẳng chuỗi có ký tự xuống dòng, ký tự điều khiển hoặc văn bản rất dài, log có thể bị làm nhiễu, giả mạo dòng hoặc tăng chi phí lưu trữ.

Một cách giảm rủi ro khi thực sự cần in giá trị đầu vào đã được cho phép là giới hạn chiều dài và escape các ký tự đặc biệt. Chỉ thực hiện điều này **sau khi** đã xác định trường được phép ghi log; escape không biến secret thành dữ liệu an toàn.

Đoạn minh họa (không phải chương trình độc lập):

~~~java
static String safeShortText(String value) {
    if (value == null) return "null";
    String cleaned = value.replace("\\", "\\\\")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t");
    int max = 80;
    return cleaned.length() <= max
            ? cleaned
            : cleaned.substring(0, max) + "...";
}
~~~

Hàm trên minh họa cách hiển thị chuỗi ngắn với các ký tự CR/LF/tab đã được escape. Nó **không xử lý mọi ký tự điều khiển, Unicode hoặc chính sách giới hạn byte**, nên cần quy tắc phù hợp với định dạng log thực tế khi xây dựng thư viện dùng trong production. Trong trường hợp có thể, **không in giá trị đầu vào** vẫn dễ bảo đảm hơn.

## 10. Khi dùng logging, exception và công cụ sinh mã

### Logging

- Tránh `logger.info("login={}", login)` hoặc `logger.debug("request=" + request)` nếu `login`/`request` có thể chứa secret.
- Ghi sự kiện nghiệp vụ và metadata có mục đích rõ ràng, như tên thao tác, trạng thái, correlation ID được duyệt.
- Kiểm tra cấu hình log và chính sách retention/quyền truy cập, nhưng **đừng dựa vào việc log chỉ dành cho người quản trị để cho phép ghi secret**.
- Dùng logging có cấu trúc và field allowlist khi phù hợp. Cũng cần cấu hình serializer/mapper an toàn: bảo vệ `toString()` không tự động bảo vệ mọi cách serialize đối tượng.

### Exception và debug

Mẫu như `throw new IllegalArgumentException("Bad request: " + request)` có thể kéo theo `request.toString()` vào exception message. Exception sau đó có thể được log hoặc gửi qua API. Nên dùng thông báo mô tả lỗi, mã lỗi, hoặc correlation ID không nhạy cảm thay vì nguyên đối tượng.

Debugger, heap dump và tracing có thể quan sát giá trị theo cách khác `toString()`. Một `toString()` an toàn là **một lớp bảo vệ phạm vi đầu ra chuỗi**, không phải cam kết rằng secret không tồn tại hoặc không thể bị đọc ở nơi khác.

### IDE, record và công cụ sinh mã

- Record tự tạo `toString()` từ các component nếu không override. Rà soát record/DTO chứa dữ liệu xác thực trước khi log.
- IDE có tính năng sinh `toString()` từ các field. Không chấp nhận mặc định “chọn tất cả”.
- Thư viện sinh mã có thể có tùy chọn bỏ qua hoặc chỉ chọn field được phép; kiểm tra cấu hình thực tế và mã được sinh. Một annotation bỏ qua trường khi serialize JSON **không mặc nhiên thay đổi `toString()`**, và ngược lại.
- Với các kiểu mô hình có thể thêm trường mới, ưu tiên allowlist để phần biểu diễn không tự đổi theo cấu trúc nội bộ.

Nếu cần dùng object để hiển thị trong UI hoặc truyền qua mạng, nên có **DTO/response model riêng** đã được thiết kế để loại secret. Không dùng `toString()` làm giao thức trao đổi dữ liệu hoặc định dạng API.

## 11. Tự kiểm tra `toString()` bằng một bài test đơn giản

Không nên chỉ đọc bằng mắt đầu ra một lần. Khi thay đổi lớp hoặc thêm component, hãy kiểm tra rằng biểu diễn vẫn không chứa những dấu hiệu bí mật đã đặt trong đối tượng thử nghiệm.

Tạo tệp `ToStringSafetyCheck.java`:

~~~java
public class ToStringSafetyCheck {
    record SafeCredential(
            String operationId,
            String password,
            String accessToken
    ) {
        @Override
        public String toString() {
            return "SafeCredential[operationId=" + operationId + "]";
        }
    }

    private static void assertNotContained(String text, String secret) {
        if (text.contains(secret)) {
            throw new AssertionError("Sensitive value appears in representation");
        }
    }

    public static void main(String[] args) {
        SafeCredential value = new SafeCredential(
                "op-123",
                "synthetic-password-123",
                "synthetic-access-token-456"
        );

        String output = value.toString();
        assertNotContained(output, value.password());
        assertNotContained(output, value.accessToken());

        if (!output.contains("op-123")) {
            throw new AssertionError("Missing permitted diagnostic field");
        }

        System.out.println("toString safety check: PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ToStringSafetyCheck.java
java ToStringSafetyCheck
~~~

Stdout:

~~~text
toString safety check: PASS
~~~

Các giá trị trên đều là **dữ liệu giả**, tuyệt đối không đặt token thật vào mã thử nghiệm hoặc thông báo thất bại. Đây là kiểm tra tối thiểu, không thể chứng minh rằng tất cả kiểu secret chưa biết hoặc mọi đường serialize đều an toàn. Để mạnh hơn, bổ sung test khi thêm trường, thay đổi kiểu component lồng nhau hoặc thay cơ chế sinh `toString()`.

Khi viết test thất bại, đừng nhét chính secret vào thông báo assert hay log test. Mục đích là phát hiện rò rỉ, không tạo thêm một kênh lộ bí mật.

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Điều đúng |
| --- | --- |
| `toString()` chỉ dùng trong debugger nên có thể in toàn bộ field. | Nó còn có thể xuất hiện trong log, exception, công cụ giám sát và chuỗi nối. |
| Record không có `toString()` tự viết thì an toàn. | Record mặc định sinh biểu diễn gồm các component, có thể chứa mật khẩu/token. |
| Đổi token sang Base64 hoặc chỉ in vài ký tự là đã an toàn. | Không bảo đảm; vẫn có khả năng lộ thông tin và mối liên hệ về token. |
| Chỉ cần sửa `toString()` của lớp ngoài. | Nếu lớp ngoài nối nguyên đối tượng con/Map/List, biểu diễn con có thể chứa secret. |
| Hash mật khẩu luôn được phép xuất log. | Hash cũng có thể là dữ liệu nhạy cảm; nên loại khỏi biểu diễn. |
| Dùng `logger.debug` nghĩa là secret không bao giờ bị ghi. | Khi mức log được bật hoặc thông điệp được thu thập, dữ liệu vẫn có thể xuất hiện. |
| Có `@JsonIgnore` là `toString()` cũng tự bỏ trường. | Chính sách JSON serialization và `toString()` là hai cơ chế khác nhau. |
| Chuỗi `toString()` không lộ bí mật thì cả đối tượng an toàn khi serialize. | JSON/XML, debugger hoặc heap dump có đường lấy dữ liệu riêng. |
| Che hết secret bằng replace sau khi nối chuỗi là đủ. | Dễ bỏ sót trường mới, định dạng khác và object lồng nhau; allowlist vững hơn. |
| Mã định danh nào cũng là dữ liệu công khai. | ID có thể mang ý nghĩa nhạy cảm; cần phân loại trước khi đưa vào log. |

## 13. Checklist thiết kế biểu diễn an toàn

Trước khi hoàn thành `toString()` cho một lớp Java:

1. **Phân loại toàn bộ dữ liệu**: nhận diện mật khẩu, token, khóa, cookie, thông tin cá nhân và dữ liệu quan trọng trong cả field trực tiếp lẫn object lồng.
2. **Xác định mục tiêu chẩn đoán**: thật sự cần biết gì để xử lý sự cố? Thường chỉ cần loại đối tượng, trạng thái và correlation ID được thiết kế an toàn.
3. **Dùng allowlist**: chỉ nối các trường đã được duyệt, thay vì in hết rồi cố gắng xóa.
4. **Không dùng token làm mã tương quan**: không ghi token nguyên văn, prefix/suffix, Base64 hoặc hash token tùy tiện vào log.
5. **Kiểm tra object lồng**: không nối nguyên header map, DTO request, collection hoặc payload chứa dữ liệu chưa phân loại.
6. **Rà soát record và code generator**: `toString()` tự động sinh có thể hiển thị các trường được thêm sau này.
7. **Kiểm soát dữ liệu đầu vào được phép in**: escape ký tự xuống dòng/điều khiển, giới hạn kích thước hoặc chỉ log mã do hệ thống tạo.
8. **Giữ exception và logging nhất quán**: sử dụng những giá trị đã được cho phép, kể cả khi thông điệp chỉ dành cho debug.
9. **Kiểm thử với dữ liệu giả có dấu hiệu nhận diện**: xác nhận chuỗi không chứa bất kỳ secret thử nghiệm nào; không in các giá trị đó trong kết quả kiểm thử.
10. **Đánh giá riêng các kênh khác**: serialize JSON, tracing, event, heap dump và màn hình hỗ trợ phải có chính sách bảo vệ của chính chúng.

**Ghi nhớ:** `toString()` là bề mặt **quan sát** của đối tượng và có thể bị gọi gián tiếp rất nhiều lần. Một biểu diễn tốt cho debug phải **tối thiểu, có chủ đích và không mang thông tin xác thực**. Với lớp chứa mật khẩu, token hoặc dữ liệu nhạy cảm, ưu tiên allowlist và không bao giờ để secret đi vào chuỗi `toString()`, dù thông qua field trực tiếp, record sinh tự động hay object lồng nhau.