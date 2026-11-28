# Tùy biến toString để che dữ liệu và tránh coi kết quả là định dạng lưu trữ

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record tự sinh phương thức `toString()` để tạo biểu diễn dạng văn bản từ tên record, tên component và giá trị của chúng. Điều này tiện cho debug, nhưng cũng có thể vô tình đưa mật khẩu, access token, thông tin thanh toán hoặc dữ liệu riêng tư vào log.

Record cho phép ghi đè `toString()` để kiểm soát thông tin hiển thị, ví dụ che component nhạy cảm. Tuy nhiên, chuỗi trả về chỉ nên được xem là **biểu diễn phục vụ con người đọc**. Không dùng nó làm định dạng lưu trữ, giao thức trao đổi, JSON, khóa cache hoặc chuỗi để parse ngược thành object. Nếu cần dữ liệu có cấu trúc và hợp đồng ổn định, hãy dùng serializer hoặc DTO/schema được thiết kế riêng.

## 1. toString mặc định của record hiển thị component

Xét record:

```java
record LoginRequest(String username, String password) {}

LoginRequest request =
    new LoginRequest("linh", "correct-horse-battery-staple");

System.out.println(request);
```

Biểu diễn mặc định của record được tạo từ tên record cùng tên và biểu diễn văn bản của các component. Vì vậy output có thể chứa cả password. Nếu object được ghi vào log khi xử lý lỗi, debug hoặc theo dõi request, dữ liệu nhạy cảm có thể xuất hiện ở nơi nhiều người hoặc hệ thống khác có quyền truy cập.

Đây không phải lỗi của compiler: record đang thể hiện các component của nó như thiết kế. Trách nhiệm của ứng dụng là xác định component nào được phép xuất hiện trong biểu diễn dành cho log hoặc debug.

Những component cần xem xét kỹ gồm:

- Password, access token, refresh token, API key, secret.
- Cookie phiên, authorization header, mã xác thực dùng một lần.
- Số thẻ, thông tin tài khoản hoặc dữ liệu thanh toán.
- Thông tin cá nhân, địa chỉ, email hoặc dữ liệu định danh mà log không cần giữ.
- Nội dung request/response có thể chứa bí mật hoặc dữ liệu do người dùng cung cấp.

Không giả định component lồng nhau đã tự che dữ liệu. Khi biểu diễn record gọi `toString()` của một component khác, component đó có thể in toàn bộ trạng thái nếu không có quy tắc redaction riêng.

## 2. Ghi đè toString để che component nhạy cảm

Có thể ghi đè `toString()` trong thân record và chỉ đưa các trường được phép hiển thị vào chuỗi:

```java
record LoginRequest(String username, String password) {
    @Override
    public String toString() {
        return "LoginRequest[username=" + username
            + ", password=<redacted>]";
    }
}

LoginRequest request =
    new LoginRequest("linh", "secret-value");

System.out.println(request);
// LoginRequest[username=linh, password=<redacted>]
```

Phương thức này chỉ thay đổi biểu diễn văn bản. Component `password` vẫn lưu giá trị ban đầu; accessor `password()` vẫn trả về giá trị đó; `equals` và `hashCode` mặc định vẫn dựa trên component gốc.

Vì thế:

```java
LoginRequest first = new LoginRequest("linh", "secret-A");
LoginRequest second = new LoginRequest("linh", "secret-B");

System.out.println(first); // Cả hai đều có thể hiển thị password=<redacted>
System.out.println(first.equals(second)); // false
```

Hai record có biểu diễn đã che giống phần password nhưng vẫn khác nhau theo giá trị vì password thực tế khác nhau. Đây là điều mong muốn: che dữ liệu khi hiển thị không được làm thay đổi ngữ nghĩa của object.

## 3. Che toàn bộ bí mật hoặc chỉ hiển thị một phần đã được cho phép

Đối với token, password và secret, lựa chọn an toàn thường là không hiển thị bất kỳ phần nào:

```java
record ApiCredential(
    String clientId,
    String accessToken,
    String refreshToken
) {
    @Override
    public String toString() {
        return "ApiCredential[clientId=" + clientId
            + ", accessToken=<redacted>"
            + ", refreshToken=<redacted>]";
    }
}
```

Với một mã định danh cần hỗ trợ đối chiếu, chỉ hiển thị một phần cuối khi chính sách bảo mật cho phép:

```java
record PaymentReference(String merchant, String accountNumber) {
    @Override
    public String toString() {
        String suffix = accountNumber == null
            || accountNumber.length() < 4
                ? "****"
                : "****" + accountNumber.substring(accountNumber.length() - 4);

        return "PaymentReference[merchant=" + merchant
            + ", accountNumber=" + suffix + "]";
    }
}
```

Không tự suy đoán rằng bốn ký tự cuối luôn an toàn. Chính sách có thể yêu cầu che toàn bộ giá trị, hoặc chỉ cho phép hiển thị phần cuối trong một số ngữ cảnh. Hãy kiểm tra cả nguy cơ nhận dạng lại khi kết hợp nhiều trường.

## 4. toString không thay đổi accessor, equals hoặc hashCode

Ghi đè `toString()` chỉ kiểm soát biểu diễn văn bản. Nó không phải cách thay đổi dữ liệu được lưu và cũng không thay đổi hợp đồng equality của record.

```java
record ApiCredential(String clientId, String accessToken) {
    @Override
    public String toString() {
        return "ApiCredential[clientId=" + clientId
            + ", accessToken=<redacted>]";
    }
}

ApiCredential credential =
    new ApiCredential("client-7", "token-secret");

System.out.println(credential.accessToken()); // token-secret
System.out.println(credential);               // accessToken đã che
```

Các điểm cần phân biệt:

| Thành phần | Vai trò | Ghi đè toString có thay đổi không? |
| --- | --- | --- |
| Record component | Giá trị được lưu trong instance | Không |
| Accessor | Đọc giá trị component | Không |
| `equals()` | So sánh giá trị theo hợp đồng equality | Không |
| `hashCode()` | Tạo mã băm nhất quán với equality | Không |
| `toString()` | Biểu diễn văn bản để đọc/debug | Có |

Không ghi đè accessor để che password hoặc token. Accessor là cách đọc component theo hợp đồng của record; trả về giá trị đã che có thể phá copy invariant và làm mã nghiệp vụ không đọc được giá trị cần dùng. Redaction thuộc về biểu diễn hiển thị hoặc logging.

## 5. Không dùng kết quả toString làm định dạng lưu trữ

Một lỗi thiết kế thường gặp là lưu trực tiếp kết quả `toString()` rồi cố parse lại:

```java
record UserProfile(String name, int age) {}

UserProfile user = new UserProfile("Linh", 25);
String stored = user.toString();

// Không nên parse stored bằng cách tách chuỗi theo dấu phẩy,
// dấu ngoặc hoặc dấu bằng để tái tạo UserProfile.
```

Biểu diễn này được thiết kế để đọc/debug, không phải một định dạng tuần tự hóa có schema. Không có cam kết rằng cú pháp văn bản sẽ giữ nguyên qua các thay đổi của record, component hoặc implementation. Ngay cả khi output hiện tại trông giống cấu trúc có thể parse, đó không phải hợp đồng dữ liệu.

Các vấn đề khi dùng `toString()` làm format:

- Đổi tên record hoặc component có thể đổi output.
- Thêm, bỏ hoặc đổi thứ tự component có thể làm thay đổi biểu diễn.
- Giá trị component có thể chứa dấu phẩy, dấu bằng, ngoặc, dấu xuống dòng hoặc ký tự điều khiển.
- Component lồng nhau có biểu diễn riêng và có thể thay đổi độc lập.
- Chuỗi đã redaction không còn chứa đủ dữ liệu để khôi phục object.
- Format không nhất thiết có version, escaping, kiểu dữ liệu hoặc quy tắc tương thích ngược.

Không dùng `toString()` làm khóa database, cache key, chữ ký số, payload API hoặc định danh bền vững. Nếu cần một khóa, hãy tạo khóa rõ ràng từ các trường nghiệp vụ đã chuẩn hóa. Nếu cần lưu hoặc truyền dữ liệu, dùng định dạng có cấu trúc và schema rõ ràng.

## 6. Dùng JSON hoặc serialization có hợp đồng riêng

Nếu cần ghi record thành JSON, hãy dùng thư viện JSON hoặc serializer phù hợp và cấu hình rõ:

- Tên field và kiểu dữ liệu.
- Field nào được phép xuất hiện.
- Quy tắc che hoặc loại bỏ secret.
- Cách biểu diễn ngày giờ, số thập phân và giá trị null.
- Version schema và cách xử lý thay đổi tương thích.

Ví dụ minh họa một DTO dành riêng cho log:

```java
record LoginRequest(String username, String password) {}
record LoginLogView(String username, String passwordStatus) {}

LoginLogView toLogView(LoginRequest request) {
    return new LoginLogView(request.username(), "REDACTED");
}
```

Serializer có thể chuyển `LoginLogView` thành JSON theo schema được ứng dụng quản lý. DTO log chỉ chứa dữ liệu được phép ghi, nên quy tắc redaction được thể hiện rõ ở ranh giới logging.

Nếu cần lưu trữ để đọc lại, hãy serialize một DTO dữ liệu phù hợp với yêu cầu lưu trữ, không serialize chuỗi debug. Việc lưu dữ liệu nhạy cảm còn cần cơ chế bảo vệ phù hợp như kiểm soát quyền truy cập, mã hóa và chính sách retention; việc che `toString()` không thay thế các biện pháp đó.

## 7. Cẩn thận khi ghi log record

Ghi log bằng placeholder giúp tách thông điệp và giá trị, nhưng nếu truyền cả record thì logger thường vẫn gọi `toString()`:

```java
logger.debug("Received request: {}", request);
```

Nếu record chưa override `toString()`, dòng log có thể chứa tất cả component. Sau khi override, chuỗi có thể được che, nhưng cần xem đây là một lớp bảo vệ bổ sung.

Thực hành tốt hơn là chỉ ghi các trường được phép và có ích cho chẩn đoán:

```java
logger.info(
    "Login requested for username={}",
    request.username()
);
```

Nếu username cũng là dữ liệu cần hạn chế, hãy dùng một mã định danh nội bộ hoặc giá trị đã được xử lý theo chính sách log. Không ghi token, password, cookie hoặc header xác thực chỉ vì chúng có sẵn trong record.

Ngoài ra, cần cân nhắc dữ liệu do người dùng kiểm soát có thể chứa ký tự xuống dòng hoặc ký tự điều khiển. Dùng logging framework có hỗ trợ structured logging và encoding phù hợp; tránh tự ghép chuỗi log không kiểm soát nội dung.

## 8. toString của component lồng nhau không bảo đảm được che

Một record có thể chứa một record khác hoặc class tùy chỉnh:

```java
record DatabaseConfig(String host, String username, String password) {}
record ApplicationConfig(String name, DatabaseConfig database) {}
```

Nếu `ApplicationConfig` dùng `toString()` mặc định, biểu diễn của component `database` có thể gọi `DatabaseConfig.toString()`. Nếu record lồng nhau chưa che password, thông tin đó vẫn có thể xuất hiện trong output bên ngoài.

Vì vậy, hãy rà soát toàn bộ object graph được đưa vào log. Không chỉ kiểm tra record ngoài cùng. Có thể tạo log view phẳng chỉ chứa allowlist field:

```java
record DatabaseLogView(String host, String username) {}
record ApplicationLogView(String name, DatabaseLogView database) {}

ApplicationLogView toLogView(
    String appName,
    DatabaseConfig database
) {
    return new ApplicationLogView(
        appName,
        new DatabaseLogView(database.host(), database.username())
    );
}
```

Log view không chứa password, nên logger không cần dựa vào việc mọi class lồng nhau đều có implementation redaction đúng.

## 9. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| toString mặc định của record có thể hiển thị component nhạy cảm. | **Đúng** | Biểu diễn được tạo từ tên và giá trị component. |
| Ghi đè toString sẽ xóa hoặc thay đổi secret đang lưu. | **Sai** | Nó chỉ thay đổi chuỗi biểu diễn. |
| Ghi đè toString làm thay đổi equals và hashCode. | **Sai** | Ba phương thức có vai trò riêng. |
| Accessor nên trả giá trị đã che để bảo vệ secret. | **Sai** | Accessor cần giữ hợp đồng đọc component và copy invariant. |
| Chuỗi toString phù hợp làm định dạng database hoặc API. | **Sai** | Nó không phải schema serialization ổn định. |
| Placeholder logger luôn che dữ liệu trong object. | **Sai** | Logger vẫn có thể gọi toString của object được truyền vào. |
| Che record ngoài cùng đảm bảo mọi component lồng nhau đã an toàn. | **Sai** | toString của component lồng nhau có thể làm lộ dữ liệu. |
| DTO log riêng giúp giới hạn field được ghi. | **Đúng** | Chỉ đưa vào view những dữ liệu được phép xuất hiện. |

## 10. Checklist trước khi dùng toString trong ứng dụng

1. Record có component nhạy cảm như password, token, cookie hoặc dữ liệu thanh toán không?
2. toString mặc định có thể làm lộ component nào?
3. Các component lồng nhau có tự in dữ liệu nhạy cảm không?
4. Có cần override toString để che toàn bộ hoặc một phần theo chính sách không?
5. Accessor vẫn trả component thật và copy invariant có được giữ không?
6. Log có đang truyền cả record thay vì chỉ các field allowlist không?
7. Dữ liệu người dùng có thể chứa ký tự điều khiển hoặc xuống dòng không?
8. Có đang dùng kết quả toString làm dữ liệu lưu trữ, cache key, chữ ký hoặc payload không?
9. Nếu cần JSON hoặc lưu trữ, đã dùng serializer/schema riêng chưa?
10. Log view có tránh được secret và chỉ giữ dữ liệu cần thiết cho chẩn đoán không?

**Ghi nhớ:** Override `toString()` để kiểm soát biểu diễn và che component nhạy cảm, nhưng đừng coi đó là cơ chế xóa secret hoặc định dạng serialization. Giữ accessor, `equals` và `hashCode` đúng ngữ nghĩa component; dùng DTO/log view và serializer có schema riêng cho log, JSON, lưu trữ và trao đổi dữ liệu.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, record component và biểu diễn chuỗi](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.lang.Object.toString`, mục đích biểu diễn văn bản](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#toString()).
- [Java Language Specification, Section 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
