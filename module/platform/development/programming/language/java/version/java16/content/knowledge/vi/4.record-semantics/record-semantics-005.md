# `toString` được sinh tự động và nguy cơ lộ dữ liệu nhạy cảm

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record trở thành tính năng chính thức từ Java 16. Khi không tự khai báo `toString()`, record được compiler cung cấp một phương thức biểu diễn đối tượng dựa trên tên record, tên các component và biểu diễn chuỗi của giá trị component. Cơ chế này rất tiện khi gỡ lỗi, nhưng cũng tạo ra một rủi ro bảo mật: **mọi component có thể xuất hiện trong chuỗi được ghi vào log hoặc thông báo lỗi**, kể cả mật khẩu, token, số tài khoản hay dữ liệu cá nhân.

`toString()` chỉ là biểu diễn phục vụ con người đọc. Không nên xem chuỗi mặc định là dữ liệu đã được lọc, định dạng trao đổi ổn định hay ranh giới bảo vệ bí mật.

## 1. `toString()` mặc định của record hoạt động như thế nào?

Ví dụ:

```java
record UserProfile(String username, int age) {}

UserProfile user = new UserProfile("minh", 28);
System.out.println(user);
```

Một biểu diễn thường thấy có dạng:

```text
UserProfile[username=minh, age=28]
```

Đây là ví dụ minh họa định dạng quen thuộc. Đặc tả bảo đảm chuỗi biểu diễn chứa tên lớp record, tên các component và biểu diễn chuỗi của các component, nhưng **không quy định chính xác định dạng văn bản**. Không dựa vào dấu ngoặc, dấu phẩy, khoảng trắng hoặc thứ tự trình bày cụ thể để phân tích chuỗi.

Nếu record có nhiều component, phương thức mặc định đưa thông tin của các component vào biểu diễn:

```java
record PaymentRequest(
    String requestId,
    String customerId,
    long amountInCents,
    String currency
) {}

PaymentRequest request =
    new PaymentRequest("req-42", "customer-7", 12500, "VND");

System.out.println(request);
```

Chuỗi thường có dạng tương tự:

```text
PaymentRequest[requestId=req-42, customerId=customer-7, amountInCents=12500, currency=VND]
```

Ngay cả khi chương trình chỉ muốn in một thông tin ngắn để chẩn đoán, `toString()` mặc định vẫn có thể đưa tất cả component vào chuỗi.

## 2. Vì sao việc in toàn bộ component có thể gây rò rỉ dữ liệu?

Xét một record đại diện cho yêu cầu đăng nhập:

```java
record LoginRequest(
    String username,
    String password,
    String accessToken
) {}

LoginRequest request =
    new LoginRequest("minh", "example-password", "example-access-token");

System.out.println(request);
```

Với `toString()` mặc định, biểu diễn có thể chứa cả `username`, `password` và `accessToken`. Trong ví dụ thực tế, hai component cuối có thể là thông tin xác thực còn hiệu lực. Nếu chuỗi này được ghi vào log, người có quyền đọc log có thể tiếp cận dữ liệu mà họ không được phép sử dụng.

Những nhóm dữ liệu cần đặc biệt chú ý gồm:

| Nhóm dữ liệu | Ví dụ component | Rủi ro khi xuất hiện trong log |
| --- | --- | --- |
| Thông tin xác thực | `password`, `accessToken`, `refreshToken`, API key | Có thể cho phép đăng nhập hoặc gọi API dưới danh nghĩa người dùng/hệ thống. |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ, ngày sinh | Làm lộ thông tin riêng tư và tăng phạm vi dữ liệu phải bảo vệ. |
| Dữ liệu tài chính | Số tài khoản, mã thẻ, mã xác minh | Có thể bị lạm dụng nếu log bị truy cập hoặc lưu trữ sai cách. |
| Dữ liệu nội bộ | Secret cấu hình, khóa mã hóa, chuỗi kết nối | Có thể tiết lộ cách triển khai và quyền truy cập hạ tầng. |
| Dữ liệu nghiệp vụ nhạy cảm | Hồ sơ khách hàng, nội dung giao dịch, dữ liệu nhân sự | Có thể vượt quá mục đích chẩn đoán của log. |

Rủi ro không chỉ xuất hiện khi lập trình viên chủ động gọi `System.out.println`. Một chuỗi do `toString()` tạo ra có thể đi vào:

- Log ứng dụng khi truyền cả đối tượng vào logger.
- Nội dung exception khi nối đối tượng vào thông báo lỗi.
- Log của collection khi in danh sách hoặc map chứa record.
- Công cụ giám sát, hệ thống thu thập log, báo cáo lỗi hoặc trace nếu ứng dụng đưa đối tượng vào các trường hiển thị.
- Giao diện gỡ lỗi hoặc công cụ phát triển khi chúng chọn hiển thị đối tượng qua `toString()`.

Ví dụ với logger:

```java
logger.debug("Received login request: {}", request);
```

Thông điệp có placeholder vẫn có thể gọi `request.toString()` khi logger cần tạo thông điệp. Cách viết tham số hóa giúp tránh nối chuỗi sớm khi cấp log bị tắt, nhưng **không tự động che dữ liệu nhạy cảm**.

Tương tự:

```java
throw new IllegalArgumentException("Invalid request: " + request);
```

Thông báo exception có thể được ghi vào log hoặc trả về hệ thống theo dõi lỗi. Vì vậy, cần kiểm soát biểu diễn của đối tượng ngay từ thiết kế.

## 3. Ghi đè `toString()` để tạo biểu diễn an toàn

Record cho phép khai báo tường minh `toString()`. Khi phương thức này đã được khai báo, compiler không sinh phiên bản mặc định thay thế nó. Hãy chủ động chọn những thông tin có ích cho việc chẩn đoán và loại bỏ hoặc che các giá trị bí mật.

```java
record LoginRequest(
    String requestId,
    String username,
    String password,
    String accessToken
) {
    @Override
    public String toString() {
        return "LoginRequest[requestId=" + requestId
            + ", username=<redacted>"
            + ", password=<redacted>"
            + ", accessToken=<redacted>]";
    }
}

LoginRequest request = new LoginRequest(
    "req-42",
    "minh",
    "example-password",
    "example-access-token"
);

System.out.println(request);
```

Biểu diễn giờ chỉ chứa mã yêu cầu và các dấu `<redacted>`. Trong hệ thống thực tế, cần đánh giá cả `requestId`: chỉ giữ nó nếu đây là mã tương quan an toàn, không phải token hoặc thông tin có thể dùng để truy cập dữ liệu.

Có thể bỏ hẳn component nhạy cảm khỏi chuỗi:

```java
record PaymentCommand(
    String operationId,
    String cardNumber,
    String verificationCode,
    long amountInCents
) {
    @Override
    public String toString() {
        return "PaymentCommand[operationId=" + operationId
            + ", amountInCents=" + amountInCents
            + ", paymentDetails=<omitted>]";
    }
}
```

Việc ghi đè này chỉ thay đổi biểu diễn của `toString()`. Nó không xóa component khỏi đối tượng, không ngăn truy cập qua accessor và không mã hóa dữ liệu trong bộ nhớ. Nếu một record công khai có component `password`, accessor `password()` vẫn là một phương thức công khai. **Không xem `toString()` đã che dữ liệu là đủ để bảo vệ bí mật được lưu trong record.**

## 4. Tránh đưa lại đối tượng hiện tại vào `toString()` đã ghi đè

Một lỗi dễ gặp là ghi đè `toString()` nhưng vẫn nối chính đối tượng hiện tại vào chuỗi. Không có một phiên bản `toString()` mặc định riêng để gọi lại sau khi bạn đã thay thế nó.

Ví dụ không an toàn:

```java
record Credentials(String username, String password) {
    @Override
    public String toString() {
        // Không làm như vậy: gọi lại biểu diễn có thể chứa password.
        return "Credentials[details=" + this + "]";
    }
}
```

Đoạn mã trên gây đệ quy vì `this` khi nối chuỗi lại gọi `toString()` của chính record. Một biến thể khác là tự ghép tất cả component rồi chỉ che một phần, dễ bỏ sót khi record được bổ sung component mới hoặc khi một component lồng nhau tự hiển thị dữ liệu nhạy cảm.

Hãy tạo chuỗi an toàn từ danh sách cho phép (*allowlist*) các trường cần hiển thị:

```java
record Credentials(String username, String password) {
    @Override
    public String toString() {
        return "Credentials[username=<redacted>, password=<redacted>]";
    }
}
```

Khi cần hiển thị một phần username, hãy dùng hàm che dữ liệu có quy tắc rõ ràng và kiểm thử với giá trị ngắn, `null`, Unicode cũng như các định dạng khác nhau. Đừng tự viết thao tác cắt chuỗi đơn giản rồi giả định nó phù hợp với mọi loại định danh.

## 5. Component lồng nhau và collection cũng có thể làm lộ dữ liệu

Việc record không chứa trực tiếp một component tên `password` không có nghĩa chuỗi được tạo ra an toàn. Component có thể là một object khác, collection hoặc record lồng nhau. Biểu diễn của đối tượng bên trong có thể tiếp tục đưa thông tin nhạy cảm ra ngoài.

```java
record Credentials(String username, String password) {}
record LoginEnvelope(String requestId, Credentials credentials) {}

LoginEnvelope envelope = new LoginEnvelope(
    "req-42",
    new Credentials("minh", "example-password")
);

System.out.println(envelope);
```

Biểu diễn của `LoginEnvelope` có thể gọi `toString()` trên `Credentials`. Nếu `Credentials` dùng phiên bản mặc định, mật khẩu có thể xuất hiện trong chuỗi của record bên ngoài.

Collection cũng có hành vi tương tự:

```java
record BatchRequest(java.util.List<Credentials> entries) {}

BatchRequest batch = new BatchRequest(java.util.List.of(
    new Credentials("minh", "example-password")
));

System.out.println(batch);
```

`List.toString()` trình bày các phần tử của danh sách; nếu phần tử là record, biểu diễn của phần tử có thể tiếp tục hiển thị component của nó. Vì vậy cần xem xét toàn bộ đường đi của `toString()`, không chỉ tên component ở record ngoài cùng.

Có thể giảm rủi ro ở nhiều lớp:

- Record giữ dữ liệu nhạy cảm nên có `toString()` an toàn.
- Record bao ngoài không in component nhạy cảm hoặc object chứa bí mật.
- Log chỉ chọn các trường cần thiết thay vì truyền toàn bộ object/collection.
- Những class tham gia biểu diễn lồng nhau cũng phải có chính sách hiển thị phù hợp.

## 6. Thiết kế logging theo allowlist

Thay vì ghi toàn bộ request:

```java
logger.info("Login request: {}", request);
```

Hãy chỉ ghi các thuộc tính cần cho mục đích vận hành:

```java
logger.info(
    "Login attempt requestId={}, outcome={}",
    request.requestId(),
    "REJECTED"
);
```

Ngay cả các trường được chọn cũng cần đánh giá mức độ nhạy cảm. Username hoặc request ID có thể liên kết tới một cá nhân hay phiên làm việc; trong một số hệ thống, cần dùng ID giả danh, mã tương quan ngẫu nhiên hoặc che bớt giá trị.

Với structured logging, hãy tạo các trường log riêng theo allowlist thay vì đưa nguyên record vào một trường object. Cần kiểm soát nơi lưu log, quyền truy cập, thời gian lưu giữ và việc truyền log sang hệ thống bên ngoài theo chính sách của ứng dụng.

## 7. Nên tách dữ liệu bí mật khỏi dữ liệu dùng để hiển thị

Nếu một record được dùng làm dữ liệu trao đổi giữa nhiều lớp, hãy cân nhắc xem nó có thực sự cần mang theo bí mật hay không. Có thể tách phần thông tin phục vụ log/quan sát thành một kiểu riêng chỉ chứa dữ liệu đã được phê duyệt:

```java
record LoginRequest(
    String requestId,
    String username,
    String password,
    String accessToken
) {}

record LoginRequestLogView(String requestId, String outcome) {}

class LoginLogging {
    static LoginRequestLogView toLogView(
        LoginRequest request,
        String outcome
    ) {
        return new LoginRequestLogView(request.requestId(), outcome);
    }
}
```

`LoginRequestLogView` chỉ mang những trường được chọn để ghi log. Vì record này cũng có `toString()` mặc định, hãy tiếp tục bảo đảm mọi component của nó đều an toàn để hiển thị.

Đối với thông tin xác thực, thường tốt hơn là giới hạn nơi lưu trữ, phạm vi truy cập và thời gian tồn tại; không sao chép bí mật sang các DTO, event hoặc log chỉ để tiện chẩn đoán. Nếu một record cần giữ dữ liệu bí mật trong thời gian ngắn, hãy cân nhắc một kiểu chuyên biệt có chính sách hiển thị an toàn và quyền truy cập được kiểm soát.

## 8. `toString()` không phải định dạng tuần tự hóa

Không dùng chuỗi do `toString()` sinh ra để:

- Lưu dữ liệu lâu dài rồi đọc lại như một định dạng file.
- Gửi qua HTTP, message broker hoặc giao thức giữa các dịch vụ.
- Tạo chữ ký số, hash nghiệp vụ hoặc khóa cache ổn định.
- Phân tích bằng cách tách chuỗi theo dấu phẩy, dấu ngoặc hoặc dấu bằng.
- So sánh phiên bản dữ liệu giữa các lần chạy hoặc các phiên bản JDK.

Định dạng `toString()` mặc định không được đặc tả cố định; nó phục vụ biểu diễn dễ đọc. Khi cần trao đổi dữ liệu, hãy dùng định dạng có schema và hợp đồng rõ ràng như JSON/Protocol Buffers hoặc một định dạng được hệ thống quy định. Khi cần log, hãy tạo thông điệp có cấu trúc và danh sách trường cho phép.

## 9. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| `toString()` mặc định của record chỉ in tên lớp. | **Sai** | Biểu diễn bao gồm tên lớp, tên component và biểu diễn chuỗi của component. |
| Định dạng mặc định luôn giống nhau giữa các phiên bản JDK. | **Sai** | Đặc tả không cố định định dạng văn bản chính xác. |
| Record có `toString()` nên có thể ghi log toàn bộ object an toàn. | **Sai** | Component nhạy cảm có thể xuất hiện trong chuỗi. |
| Logger dùng placeholder `{}` sẽ tự che password. | **Sai** | Placeholder không phải cơ chế redaction. |
| Ghi đè `toString()` làm component bí mật không thể truy cập. | **Sai** | Accessor của record vẫn cung cấp giá trị component. |
| Record lồng nhau hoặc collection có thể kéo dữ liệu nhạy cảm vào chuỗi ngoài. | **Đúng** | `toString()` của component/element có thể được gọi tiếp. |
| Có thể dùng `toString()` mặc định làm JSON hoặc giao thức ổn định. | **Sai** | Đây không phải định dạng tuần tự hóa có schema. |

## 10. Checklist trước khi ghi log một record

1. Record có component nào là password, token, API key, khóa, dữ liệu tài chính hoặc thông tin cá nhân không?
2. `toString()` mặc định có thể đưa những component nào vào log?
3. Component lồng nhau hoặc collection có `toString()` hiển thị dữ liệu nhạy cảm không?
4. Có thể thay việc log cả object bằng một allowlist trường an toàn không?
5. Nếu ghi đè `toString()`, mọi component mới được thêm sau này có được mặc định loại khỏi biểu diễn an toàn không?
6. Có đang nhầm `toString()` với serialization hoặc một định dạng log ổn định không?
7. Các accessor và nơi lưu trữ khác của record đã được bảo vệ phù hợp chưa?

**Ghi nhớ:** `toString()` mặc định giúp record dễ đọc khi gỡ lỗi, nhưng nó có thể làm lộ giá trị của các component trong log và thông báo lỗi. Hãy ghi đè bằng biểu diễn allowlist/redacted khi cần, kiểm soát log ở nơi sử dụng, và nhớ rằng redaction trong `toString()` không bảo vệ dữ liệu khỏi accessor hoặc các đường truy cập khác.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, hợp đồng của `toString()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java Language Specification, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
