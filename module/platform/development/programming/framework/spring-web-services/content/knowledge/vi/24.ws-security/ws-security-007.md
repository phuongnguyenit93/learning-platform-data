# Timestamp, độ lệch đồng hồ, nonce và phát hiện phát lại

## 1. Một SOAP request hợp lệ vẫn có thể là request bị phát lại

Giả sử một ứng dụng **Spring Web Services (Spring-WS)** nhận yêu cầu thanh toán `SubmitPaymentRequest`. Bên gửi đã xác thực, XML hợp XSD, SOAP Body có chữ ký số đúng và kết nối sử dụng HTTPS. Một kẻ tấn công hoặc một thành phần trung gian bị xâm nhập ghi lại thông điệp hợp lệ rồi gửi lại nguyên vẹn trong thời gian ngắn.

Nếu server chỉ xác minh chữ ký và payload, nó có thể thực hiện **cùng một lệnh thanh toán hai lần**. Chữ ký số chứng minh dữ liệu chưa bị thay đổi và thuộc về khóa ký được chấp nhận; **nó không tự chứng minh đây là lần đầu tiên thông điệp được xử lý**.

WS-Security giải quyết một phần vấn đề này bằng các thành phần:

- **`wsu:Timestamp`**: xác định khoảng thời gian thông điệp được coi là còn mới.
- **`wsse:Nonce`**: giá trị ngẫu nhiên dùng một lần, thường nằm trong `wsse:UsernameToken`.
- **`wsu:Created` của UsernameToken**: gắn thông tin thời gian với token và, khi dùng `PasswordDigest`, tham gia tính digest.
- **Replay cache**: ghi nhận định danh của những token/message đã thấy và từ chối lần lặp lại trong cửa sổ được bảo vệ.
- **Chính sách thời gian và đồng bộ đồng hồ**: giới hạn độ lệch giữa client, server và các node của cụm dịch vụ.

Những cơ chế đó **không thay thế** xác thực danh tính, phân quyền, bảo vệ chữ ký, TLS/mTLS, cũng không thay thế **idempotency ở tầng nghiệp vụ**.

Trong chương **WS-Security** của module `SPRING_WEB_SERVICES`, bài học này tập trung vào cách vận dụng timestamp, clock skew, nonce và replay detection khi xây dựng SOAP service và client theo hướng **contract-first** với XSD/WSDL, JAXB, endpoint, interceptor, SOAP Fault, chứng chỉ và kiểm thử tương thích doanh nghiệp.

### 1.1. Mục tiêu học tập

Sau bài học, bạn cần:

1. Đọc đúng `wsu:Timestamp` với `Created`, `Expires` trong SOAP Security Header.
2. Phân biệt **thời hạn hợp lệ**, **độ lệch đồng hồ** và **cửa sổ lưu replay cache**.
3. Hiểu nonce và `PasswordDigest` trong `UsernameToken`; không nhầm nonce với password, signature hay business transaction ID.
4. Cấu hình kiểm tra WS-Security qua `Wss4jSecurityInterceptor`, nhận diện giới hạn API/version.
5. Thiết kế replay cache có **atomic insert-if-absent** và hoạt động được với nhiều instance.
6. Chẩn đoán SOAP Fault khi timestamp hết hạn, nonce trùng hoặc đồng hồ sai.
7. Kiểm thử các cạnh thời gian, concurrency, retry, failover và khả năng tương thích giữa hai SOAP stack.

**Thông điệp trọng tâm:** kiểm tra “message còn mới” và kiểm tra “message chưa từng xuất hiện” là **hai bài toán khác nhau**; muốn chống phát lại phải giải quyết cả hai.

## 2. Threat model: kẻ tấn công có thể phát lại ở đâu?

~~~mermaid
sequenceDiagram
    participant C as SOAP Client
    participant G as Gateway
    participant S as Spring-WS Server
    participant A as Attacker / compromised component
    C->>G: Request R (Timestamp, Nonce, Signature)
    G->>S: R
    S-->>C: Response thành công
    A->>S: Phát lại nguyên request R
    Note over S: Chữ ký có thể vẫn hợp lệ
    S-->>A: Phải từ chối nếu token/message đã dùng
~~~

Một thông điệp hợp lệ có thể bị phát lại bởi thành phần nhìn thấy thông điệp, hệ thống log không được bảo vệ, một client bị xâm nhập, hoặc ngay chính client retry sau timeout. Vì thế **replay** không nhất thiết có nghĩa attacker biết mật khẩu hay khóa riêng.

| Mối đe dọa | Chữ ký giúp gì? | Timestamp giúp gì? | Replay cache giúp gì? |
| --- | --- | --- | --- |
| Sửa `amount` trong SOAP Body | Phát hiện thay đổi **nếu Body được ký** | Không trực tiếp | Không trực tiếp |
| Gửi lại nguyên request trong 20 giây | Chữ ký vẫn có thể hợp lệ | Request vẫn còn mới | **Phát hiện lặp** nếu khóa được lưu |
| Phát lại message sau nhiều giờ | Chữ ký vẫn có thể hợp lệ | **Từ chối quá hạn** | Có thể đã hết hạn lưu khóa |
| Đặt `Created` ở tương lai xa | Không giúp nếu timestamp không được ký/bảo vệ | **Giới hạn future skew** | Không thay kiểm tra thời gian |
| Chặn response rồi khiến client retry | Chữ ký không xác định đã commit hay chưa | Cả hai lần có thể còn mới | Có thể từ chối request lặp; nghiệp vụ vẫn cần đối soát |
| Client tạo nonce mới để gửi lại cùng lệnh | Chữ ký có thể vẫn đúng | Thời gian đều hợp lệ | **Nonce cache không nhận ra lệnh nghiệp vụ trùng** |

### 2.1. Hai lớp chống trùng cần tồn tại song song

~~~text
Lớp bảo mật thông điệp:
  username + nonce / signature value / message ID theo profile
  -> Phát hiện token/message đã được dùng trong cửa sổ thời gian

Lớp nghiệp vụ:
  tenant + paymentRequestId (idempotency key)
  -> Ngăn cùng một nghiệp vụ được commit hai lần
~~~

**Replay cache** bảo vệ security exchange. **Idempotency key** bảo vệ ý nghĩa nghiệp vụ. Nếu client gửi lại cùng thao tác với nonce hợp lệ **mới**, replay cache vẫn có thể cho qua, nhưng service thanh toán phải nhận ra `paymentRequestId` đã được xử lý.

## 3. WS-Security Header: đặt Timestamp và UsernameToken ở đâu?

WS-Security đặt các thành phần bảo mật trong **SOAP Header**, không đặt trực tiếp vào XSD payload nghiệp vụ. Ví dụ dưới đây dùng SOAP 1.1 và WS-Security UsernameToken Profile:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    xmlns:p="urn:example:payments:v1">

    <soap:Header>
        <wsse:Security soap:mustUnderstand="1">
            <wsu:Timestamp wsu:Id="TS-1001">
                <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
                <wsu:Expires>2026-11-27T02:05:00Z</wsu:Expires>
            </wsu:Timestamp>

            <wsse:UsernameToken wsu:Id="UT-1001">
                <wsse:Username>integration-client</wsse:Username>
                <wsse:Password
                    Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">BASE64_DIGEST_EXAMPLE</wsse:Password>
                <wsse:Nonce
                    EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">BASE64_NONCE_EXAMPLE</wsse:Nonce>
                <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
            </wsse:UsernameToken>
        </wsse:Security>
    </soap:Header>

    <soap:Body>
        <p:SubmitPaymentRequest>
            <p:paymentRequestId>PAY-1001</p:paymentRequestId>
            <p:amount>250000</p:amount>
            <p:currency>VND</p:currency>
        </p:SubmitPaymentRequest>
    </soap:Body>
</soap:Envelope>
~~~

**Cảnh báo:** `BASE64_DIGEST_EXAMPLE` và `BASE64_NONCE_EXAMPLE` là placeholder **không phải Base64 thực**; XML này minh họa vị trí cấu trúc, **không phải request bảo mật có thể gửi ngay**. Ví dụ cũng cố ý chưa có `ds:Signature`; nếu chính sách yêu cầu bảo vệ Body/Timestamp, client phải ký các phần tương ứng.

### 3.1. Hai `Created` có thể cùng xuất hiện

Ví dụ có:

- `wsu:Timestamp/wsu:Created`: thời điểm bắt đầu tính tuổi của **message timestamp**.
- `wsse:UsernameToken/wsu:Created`: thời điểm tạo **UsernameToken**; tham gia `PasswordDigest` nếu profile dùng digest.

Chúng có thể cùng giá trị nhưng **không phải cùng một phần tử**. Cấu hình validator cần quyết định kiểm tra cả timestamp độc lập và UsernameToken theo chính sách. Đừng xóa một `Created` chỉ vì “đã có Created trong Header”.

### 3.2. Namespace quyết định ý nghĩa

WS-Security sử dụng namespace OASIS chuẩn:

| Prefix ví dụ | Namespace | Vai trò |
| --- | --- | --- |
| `soap` | `http://schemas.xmlsoap.org/soap/envelope/` | SOAP 1.1 Envelope |
| `wsse` | `.../oasis-200401-wss-wssecurity-secext-1.0.xsd` | Security, UsernameToken, Nonce |
| `wsu` | `.../oasis-200401-wss-wssecurity-utility-1.0.xsd` | Timestamp, Created, Expires và ID |
| `p` | `urn:example:payments:v1` | Payload nghiệp vụ từ XSD |

Prefix `wsse`/`wsu` chỉ là bí danh XML. Khi kiểm thử, so sánh **namespace URI + local name** thay vì yêu cầu cùng prefix.

## 4. `wsu:Timestamp`: định nghĩa và vai trò

Thông điệp có thể mang:

~~~xml
<wsu:Timestamp
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    wsu:Id="TS-1001">
    <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
    <wsu:Expires>2026-11-27T02:05:00Z</wsu:Expires>
</wsu:Timestamp>
~~~

Ý nghĩa:

- **`Created`**: thời điểm message được tạo theo đồng hồ phía gửi.
- **`Expires`**: thời điểm message hết hiệu lực theo thông tin thời gian được công bố.
- **`wsu:Id`**: định danh XML để tham chiếu đến Timestamp, thường quan trọng khi ký phần tử này.

Khi nhận message lúc `2026-11-27T02:01:30Z`, một policy với thời hạn phù hợp có thể cho phép bước kiểm tra freshness, **nếu timestamp đã được xác thực theo yêu cầu và các điều kiện khác đều đạt**.

### 4.1. Timestamp không phải chữ ký

Timestamp tự nó chỉ là **dữ liệu khai báo về thời gian**. Nếu bất kỳ ai cũng có thể sửa `Created` hoặc `Expires` mà server vẫn tin, kẻ phát lại có thể đơn giản **đẩy thời gian về phía trước**.

Với trao đổi cần tính toàn vẹn message, hãy cấu hình chữ ký WS-Security bao phủ `wsu:Timestamp` và những phần SOAP cần bảo vệ, hoặc sử dụng cơ chế bảo vệ/tin cậy phù hợp profile đã thống nhất. **Không chỉ kiểm tra chuỗi timestamp rồi xem như đủ bảo mật.**

TLS cung cấp tính bảo mật của kênh và kiểm tra peer trong phạm vi kết nối, nhưng không tự thay thế chữ ký end-to-end khi message đi qua nhiều trung gian hoặc được lưu/chuyển tiếp.

### 4.2. Vì sao `Expires` không được tin vô điều kiện?

Client không được tự quyết định mình có thể hợp lệ đến ngày mai chỉ bằng:

~~~xml
<wsu:Expires>2026-11-28T02:00:00Z</wsu:Expires>
~~~

Server còn phải áp dụng **giới hạn tuổi do chính server cấu hình**. Giá trị `Expires` có thể cần nằm trong giới hạn hợp đồng và phải được kiểm tra thứ tự thời gian so với `Created`; một số profile còn yêu cầu khoảng sống tối đa. Không chỉ viết `now.isBefore(expires)` rồi chấp nhận.

### 4.3. Freshness khác replay detection

Hai request giống hệt có thể đều mang:

~~~text
Created = 02:00:00
Expires = 02:05:00
Now     = 02:01:00
~~~

**Cả hai đều còn mới** theo timestamp, nhưng nếu lần thứ hai là phát lại thì phải bị phát hiện bằng cache/ID/signature-replay policy độc lập. Đây là lý do timestamp không thể tự xử lý replay trong cửa sổ cho phép.

## 5. Độ lệch đồng hồ: `clock skew` và giới hạn thời gian tương lai

Các máy chủ không bao giờ hoàn toàn đồng bộ. Ví dụ:

~~~text
Client clock:  02:00:45 UTC
Server clock:  02:00:10 UTC
Difference:   client nhanh hơn server 35 giây
~~~

Nếu server từ chối mọi `Created > now`, client hợp lệ có thể bị chặn vì lệch đồng hồ nhỏ. Vì thế WS-Security validator thường có **future tolerance** cho Created timestamp.

Định nghĩa:

- `t_server`: đồng hồ UTC tại nơi nhận.
- `t_created`: Created trong message.
- `t_expires`: Expires nếu có.
- `TTL`: tuổi tối đa server cho phép kể từ Created.
- `FUTURE_SKEW`: khoảng Created được phép nằm trước đồng hồ server.

Một **mô hình kiểm tra minh họa**:

~~~text
created <= server_now + FUTURE_SKEW
server_now - created <= TTL
expires > server_now                 (khi Expires được yêu cầu)
expires > created                    (khi cả hai hiện diện)
thời hạn từ Created đến Expires không vượt policy server
~~~

**Đây là pseudocode chính sách**, không phải copy nguyên thuật toán WSS4J. WSS4J có các tùy chọn kiểm tra `Timestamp` và `UsernameToken` theo phiên bản; chi tiết inclusive/exclusive, kiểm tra Expires và điều kiện timestamp bắt buộc phải được xác nhận bằng test.

### 5.1. Ví dụ chọn cửa sổ thời gian

Giả sử một hệ thống chọn:

~~~text
TTL                   = 300 giây
FUTURE_SKEW           = 60 giây
Timestamp Created     = 2026-11-27T02:00:00Z
Timestamp Expires     = 2026-11-27T02:05:00Z
Thời điểm nhận        = 2026-11-27T02:01:30Z
~~~

Lúc này tuổi message là 90 giây: **còn trong giới hạn 300 giây**. Với `Expires` lớn hơn thời điểm nhận, kiểm tra về thời gian có thể đạt nếu những điều kiện policy khác đều đúng.

Các giá trị **300 và 60 giây chỉ để minh họa**, không phải cấu hình bắt buộc của Spring-WS hay khuyến nghị mặc định cho mọi hệ thống.

### 5.2. Bốn tình huống phân biệt

| Thời điểm nhận server | `Created` | `Expires` | Phân loại minh họa |
| --- | --- | --- | --- |
| 02:01:30 | 02:00:00 | 02:05:00 | Freshness có thể hợp lệ |
| 02:06:00 | 02:00:00 | 02:05:00 | Đã hết hạn |
| 02:08:00 | 02:00:00 | 02:30:00 | Quá `TTL=300s` dù Expires còn xa |
| 02:00:00 | 02:01:30 | 02:06:30 | Created ở tương lai 90s, vượt `FUTURE_SKEW=60s` |

Trong bảng, giả định tất cả thời gian cùng ngày, theo UTC, và không xét chữ ký/nonce. Policy cụ thể có thể còn giới hạn khoảng `Expires - Created` và các điều kiện riêng.

### 5.3. Vì sao không tăng clock skew thật lớn?

Nếu cho phép Created ở tương lai 30 phút chỉ để “hết lỗi staging”, hệ thống làm rộng khoảng thời gian có thể chấp nhận message bất thường. Điều đó có thể kéo dài thời gian cần giữ replay identifiers và làm tăng vùng rủi ro.

Cách xử lý tốt hơn:

1. Đồng bộ đồng hồ các node bằng dịch vụ thời gian được quản trị (ví dụ NTP được bảo vệ).
2. Theo dõi độ lệch thời gian và cảnh báo khi vượt ngưỡng.
3. Chọn skew dựa trên **độ lệch thực tế và độ trễ có kiểm soát**, không dùng một hằng số cực lớn.
4. Thống nhất xử lý UTC/time zone cho các timestamp XML.
5. Kiểm thử đúng thời điểm sát ngưỡng, không chỉ happy path.

Một lỗi clock skew liên tục không nên được che bằng cách **vô hiệu hóa timestamp validation**.

## 6. `UsernameToken`, nonce và `PasswordDigest`

`UsernameToken` thường chứa:

~~~xml
<wsse:UsernameToken
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
    <wsse:Username>integration-client</wsse:Username>
    <wsse:Password
        Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">DIGEST_BASE64</wsse:Password>
    <wsse:Nonce
        EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">NONCE_BASE64</wsse:Nonce>
    <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
</wsse:UsernameToken>
~~~

`Username` định danh account, `Nonce` là chuỗi bytes ngẫu nhiên được mã hóa Base64, `Created` xác định thời điểm token được tạo; `PasswordDigest` dùng nonce và thời gian nhằm giảm rủi ro từ việc truyền mật khẩu ở dạng có thể đọc.

### 6.1. Nonce là giá trị dùng một lần

Nonce nên được:

- Sinh bằng bộ sinh số ngẫu nhiên mật mã (**CSPRNG**).
- Có độ bất định đủ cao, chẳng hạn **16 hoặc 32 bytes** ngẫu nhiên theo profile bảo mật.
- Không tái sử dụng trong một cửa sổ replay được bảo vệ.
- Được so sánh như **bytes hoặc giá trị mã hóa được chuẩn hóa đúng**, tránh đồng nhất hai biểu diễn Base64 khác nhau.
- Không lưu/ghi log tùy tiện cùng UsernameToken, password digest hay thông điệp nhạy cảm.

**Nonce không cần bí mật để có ích**, nhưng nó cần khó dự đoán và phải được server kiểm tra **chưa từng xuất hiện**. Một nonce ngẫu nhiên nhưng không có replay cache chỉ làm message đa dạng, không tự chặn việc gửi lại message nguyên vẹn.

### 6.2. Công thức `PasswordDigest` trong UsernameToken Profile

Với UsernameToken Profile dùng `PasswordDigest`, biểu thức khái niệm:

\[
\text{PasswordDigest} =
\operatorname{Base64}\left(
\operatorname{SHA1}(
\text{NonceBytes}\,\|\,\text{CreatedUTF8}\,\|\,\text{PasswordBytes}
)\right)
\]

Trong đó `NonceBytes` là **bytes sau Base64 decoding**, `CreatedUTF8` là bytes của chuỗi ngày giờ đúng cách biểu diễn được gửi, và `PasswordBytes` lấy theo quy tắc profile/implementation. Ký hiệu `||` nghĩa là nối bytes, không phải phép OR.

**Lưu ý bảo mật:** SHA-1 xuất hiện vì **quy định tương thích lịch sử của UsernameToken PasswordDigest**, không phải khuyến nghị dùng SHA-1 để băm mật khẩu lưu trong database hoặc tạo chữ ký số mới. Việc chấp nhận UsernameToken cần đánh giá yêu cầu interoperable, TLS, bí mật chia sẻ và chính sách authentication hiện hành.

### 6.3. `PasswordDigest` không ký SOAP Body

Attacker không biết password có thể khó tạo token digest hợp lệ mới; tuy nhiên việc có digest **không ràng buộc nội dung SOAP Body**. Nếu threat model yêu cầu bảo vệ `amount`, `accountId`, `paymentRequestId`, cần chữ ký số WS-Security cho đúng signed parts hoặc cơ chế bảo vệ tương ứng theo policy.

Một số hệ thống dùng chứng chỉ X.509 và chữ ký XML thay vì hoặc cùng UsernameToken. Trong trường hợp đó replay detection vẫn quan trọng: **một chữ ký hợp lệ trên request cũ có thể được phát lại**.

### 6.4. Nonce và `wsu:Id` không giống nhau

| Giá trị | Vai trò |
| --- | --- |
| `wsse:Nonce` | Bytes ngẫu nhiên của token, có thể dùng làm replay key |
| `wsu:Id` của `UsernameToken` hoặc `Timestamp` | XML ID để tham chiếu phần tử, thường dùng khi ký |
| `wsa:MessageID` | Correlation/relationship của WS-Addressing |
| `paymentRequestId` | Khóa định danh nghiệp vụ để chống xử lý trùng |

Không dùng `wsu:Id="UT-1"` để thay cho nonce ngẫu nhiên. `wsa:MessageID` cũng chỉ trở thành một phần chống replay nếu **được xác thực, được lưu/truy vấn và có chính sách rõ**; chỉ có header MessageID chưa đủ.

## 7. Sinh nonce đúng cách ở phía client

Nếu ứng dụng dùng thư viện WS-Security như WSS4J, ưu tiên để **security library tạo UsernameToken/Nonce**, đặt Created và PasswordDigest theo profile. Đừng tự tính digest hoặc thao tác với XML Header nếu không cần thiết.

Để hiểu cách nonce được sinh, một ví dụ Java độc lập:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class NonceExample {
    private static final SecureRandom RANDOM =
            new SecureRandom();

    public static String newNonceBase64() {
        byte[] bytes = new byte[16]; // 128 bit
        RANDOM.nextBytes(bytes);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
~~~

**Giới hạn:** hàm này chỉ tạo nonce để minh họa. Nó chưa tạo `UsernameToken`, `PasswordDigest`, Timestamp, chữ ký hoặc replay cache và không phải một SOAP security implementation hoàn chỉnh. Không tự chèn giá trị từ ví dụ vào XML đã ký mà không để WSS4J điều phối thứ tự bảo mật.

### 7.1. Các lỗi khi sinh nonce

| Cách làm | Vì sao không đạt |
| --- | --- |
| `nonce = "123456"` | Dễ đoán, bị tái sử dụng |
| `nonce = System.currentTimeMillis()` | Dễ đoán và trùng khi tạo đồng thời |
| `new Random().nextBytes(...)` | Không được thiết kế cho bảo mật mật mã |
| `nonce = username + date` | Có tính xác định, không có entropy cần thiết |
| Tạo nonce một lần khi ứng dụng startup | Mọi request dùng lại cùng nonce |
| Tạo nonce mới khi **retry cùng nghiệp vụ** | Hợp lệ về security nhưng không thay business idempotency |
| Cho phép nonce bytes dài tùy ý | Có thể gây DoS bộ nhớ/cache và parser |

Nếu một client sinh nonce mới khi gửi lại request sau timeout, server security layer có thể chấp nhận vì đây là UsernameToken mới. **Không dùng cache nonce làm phương pháp duy nhất chống hai lần thanh toán.**

### 7.2. Base64 là encoding, không phải mã hóa

`wsse:Nonce` thường được mã hóa Base64 để biểu diễn bytes trong XML; bất kỳ bên nào đọc Header cũng có thể giải mã nó. Vì vậy:

- Không dùng nonce làm mật khẩu hoặc access token.
- Không gắn thông tin nhạy cảm vào nonce.
- Parse Base64 có giới hạn độ dài và định dạng.
- Cần so sánh **nonce bytes hoặc canonical representation** khi tạo replay key.
- Không chỉ so sánh literal Base64 chưa chuẩn hóa nếu profile cho phép các biểu diễn tương đương.

## 8. Replay cache: phát hiện nonce đã được sử dụng

Replay cache là kho lưu **những token hoặc định danh message đã được xác minh và chấp nhận** trong một khoảng thời gian. Khi request mới chứa một nonce đã xuất hiện trong phạm vi cùng principal/policy, server từ chối như một hành vi phát lại.

~~~mermaid
flowchart TD
    A["SOAP request"] --> B["Kiểm tra XML/WS-Security action"]
    B --> C["Xác thực credentials, signature"]
    C --> D["Kiểm tra Timestamp/Created còn mới"]
    D --> E["Chuẩn hóa principal + nonce"]
    E --> F{"Atomic reserve replay key"}
    F -- "Chưa thấy"| G["Ghi khóa với TTL an toàn"]
    G --> H["Cho phép authorization/endpoint"]
    F -- "Đã thấy"| I["Từ chối request phát lại"]
~~~

Đây là **mô hình bảo mật**, không phải sơ đồ callback cố định của mọi phiên bản WSS4J. Validation thực tế và replay cache có thể nằm bên trong security interceptor. Quan trọng là **chỉ tin principal/nonce sau xác thực** và **không có race condition** giữa kiểm tra và ghi khóa.

### 8.1. Khóa replay nên gồm những gì?

Một policy với UsernameToken có thể dùng khóa khái niệm:

~~~text
replay-key = hash("wsse-username-token" || authenticated-principal || nonce-bytes)
~~~

Điểm thiết kế:

- **Authenticated principal**, không phải chuỗi `Username` chưa xác thực.
- **Nonce bytes** được parse/chuẩn hóa đúng.
- **Namespace của key**, để không va chạm với cache signature hoặc WS-Addressing.
- **Giới hạn dung lượng key** và key cardinality.
- **Không lưu raw UsernameToken/mật khẩu** trong khóa hiển thị/log.

Trong một số profile có thể cần thêm loại token, key identifier, issuer hoặc các thuộc tính khác. Tuy nhiên **không thêm `Created` vào khóa một cách tùy tiện**: nếu cùng nonce được phát lại với `Created` khác, policy vẫn có thể cần coi đó là nonce tái sử dụng và từ chối.

### 8.2. Việc ghi khóa phải atomic

Sai:

~~~java
if (!cache.contains(key)) {
    cache.put(key, expiresAt);
    processPayment();
}
~~~

Hai request song song trên cùng node có thể đều thấy key chưa tồn tại trước khi một request ghi khóa. Với nhiều node, nguy cơ lớn hơn.

Cần thao tác **atomic test-and-insert**:

~~~text
tryReserve(key, expiresAt):
  atomically insert key IF ABSENT
  return true  -> request đầu tiên
  return false -> duplicate, reject
~~~

Với Redis, ý tưởng thường dùng `SET key value NX EX seconds` (hoặc thao tác tương đương bảo đảm atomic và thời hạn). **Không làm GET rồi SET thành hai lệnh**. Bản thân Redis command chỉ giải quyết một phần: phải quản lý replication/failover, phân vùng, bảo mật kết nối và chính sách khi cache không khả dụng.

### 8.3. TTL cache phải bao trùm toàn bộ cửa sổ chấp nhận

Một lỗi tinh vi: message được chấp nhận ngay sát **ranh giới quá sớm theo future skew**, nhưng replay key lại chỉ lưu trong đúng `TTL` tính từ lần nhận đầu tiên.

Giả sử:

~~~text
Created = 02:00:00
FUTURE_SKEW = 60s
TTL = 300s
Lần gửi sớm nhất có thể chấp nhận: 01:59:00
Lần gửi muộn nhất có thể chấp nhận: khoảng 02:05:00
~~~

Cửa sổ hợp lệ có thể dài **360 giây**. Nếu cache lưu khóa 300 giây kể từ 01:59:00, nó hết hạn lúc 02:04:00; request phát lại lúc 02:04:30 **vẫn còn fresh** nhưng cache đã quên.

Vì vậy:

- Nếu thiết kế TTL tương đối từ lần nhận, cần bao phủ **TTL timestamp + future tolerance** và thêm biên an toàn cho chậm trễ/độ lệch giữa các thành phần.
- Tốt hơn, khi profile hỗ trợ, tính **thời điểm hết hiệu lực tuyệt đối** từ policy của token và server, rồi lưu khóa đến hết thời điểm đó.
- Có thể dùng TTL cache **dài hơn cửa sổ hợp lệ** để an toàn; đổi lại tốn tài nguyên.
- Không để key hết hạn **trước** khi request cũ có thể được validator chấp nhận.

**Cảnh báo:** đây là nguyên tắc thiết kế retention, không phải công thức nội bộ của mọi `ReplayCache` WSS4J. Policy cụ thể phải tính cả UsernameToken lifetime, Timestamp lifetime, skew và đường retry.

### 8.4. Tính giới hạn tài nguyên cho replay cache

Giả sử server nhận 2.000 request/giây và cần lưu nonce 7 phút:

\[
N_{\text{keys}} \approx 2000 \times 420 = 840{,}000
\]

Hệ thống phải dự trù metadata/memory/replication overhead; không chỉ lấy 16 bytes nonce nhân số khóa. Cần:

- Giới hạn tốc độ request/token theo principal.
- Giới hạn độ dài nonce và số phần tử header.
- TTL và chính sách eviction không vi phạm security window.
- Metrics về hit/miss, duplicate, eviction, cache errors.
- Phân vùng/replication và thử tải ở peak traffic.

Nếu cache bị eviction sớm do thiếu bộ nhớ, hệ thống có thể **vô tình chấp nhận lại một nonce cũ** đang trong cửa sổ hợp lệ.

## 9. Single instance và cụm nhiều instance

### 9.1. Vì sao cache trong JVM không đủ khi scale?

~~~mermaid
flowchart LR
    C["SOAP client"] --> LB["Load balancer"]
    LB --> A["Node A / nonce cache A"]
    LB --> B["Node B / nonce cache B"]
    A --> X["Payment service"]
    B --> X
~~~

Lần đầu gửi tới node A, nonce được ghi vào cache A. Lần thứ hai bị load balancer chuyển tới node B, cache B chưa thấy nonce. Nếu không có chia sẻ hoặc cơ chế khác, B có thể cho qua cùng một request.

**Sticky session không phải biện pháp bảo mật đủ tin cậy**: failover, autoscaling hoặc retry qua đường khác vẫn có thể đổi node.

### 9.2. Các lựa chọn

| Chiến lược | Ưu điểm | Rủi ro / yêu cầu |
| --- | --- | --- |
| Cache trong JVM | Đơn giản, độ trễ thấp | Không chia sẻ giữa các replica |
| Shared Redis-like atomic cache | Dùng chung key, atomic reserve | Cần HA, TLS/auth, failover và xử lý lỗi |
| Database unique constraint cho replay key | Có thể bền vững và transactional | Chi phí ghi cao, cleanup cần quản lý |
| Central security gateway | Một nơi kiểm tra token/replay | Phải bảo đảm mọi đường vào đều qua gateway; xử lý trust chain |
| Cache signature/token framework hỗ trợ cluster | Gắn với thư viện | Phải kiểm tra tính phân tán thật, không chỉ tên cấu hình |

Không có giải pháp phù hợp mọi quy mô. Nếu nhiều instance cùng phục vụ SOAP, hãy **kiểm thử cùng một nonce qua hai node khác nhau**, không chỉ test hai lần trên cùng một instance.

### 9.3. Cache lỗi thì cho qua hay từ chối?

Khi replay cache không khả dụng:

~~~text
Option A: fail-open  -> xử lý request dù không kiểm tra duplicate
Option B: fail-closed -> từ chối hoặc trả lỗi tạm thời
~~~

Đối với operation nhạy cảm như thanh toán, thay đổi số dư hoặc tạo hồ sơ pháp lý, **fail-open có thể làm mất thuộc tính chống phát lại**. Nên thiết kế fail-closed hoặc một chiến lược dự phòng được đánh giá an toàn, có giới hạn và quan sát được.

Nếu nghiệp vụ có idempotency DB, nó giảm rủi ro commit trùng nhưng **không có nghĩa security layer được phép bỏ qua yêu cầu replay của profile**. Quyết định fail-open/fail-closed phải được ghi trong threat model và hợp đồng vận hành.

## 10. Thời gian trong Java và đồng bộ hệ thống

### 10.1. Dùng UTC và API thời gian phù hợp

Một số API Java hữu ích:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class TimestampWindow {
    private final Clock clock;
    private final Duration ttl;
    private final Duration futureTolerance;

    public TimestampWindow(
            Clock clock, Duration ttl, Duration futureTolerance) {
        if (ttl.isNegative() || ttl.isZero()
                || futureTolerance.isNegative()) {
            throw new IllegalArgumentException("Invalid policy");
        }
        this.clock = clock;
        this.ttl = ttl;
        this.futureTolerance = futureTolerance;
    }

    public boolean isFresh(
            Instant created, Instant expires) {
        Instant now = clock.instant();

        if (created.isAfter(now.plus(futureTolerance))) {
            return false;
        }
        if (created.isBefore(now.minus(ttl))) {
            return false;
        }
        if (expires != null) {
            if (!expires.isAfter(created)
                    || !expires.isAfter(now)) {
                return false;
            }
            if (expires.isAfter(created.plus(ttl))) {
                return false;
            }
        }
        return true;
    }
}
~~~

**Đây là mô hình độc lập để giảng dạy**, **không thay thế Timestamp validator của WSS4J**. Ví dụ chưa xử lý null Created, ngoại lệ parse XML, profile không có Expires, Unicode/duplicate XML elements, XML signature, replay cache, hoặc các điều kiện thời gian khác mà framework yêu cầu. Không nối trực tiếp nó vào production để tự thay cơ chế WS-Security.

Ưu điểm của việc dùng `Clock`: test có thể điều khiển thời gian một cách **xác định**, không dựa vào `Thread.sleep(...)` khiến test chập chờn.

### 10.2. UTC không có nghĩa được phép bỏ qua timezone

XML Schema `xs:dateTime` cho phép nhiều dạng biểu diễn hợp lệ, nhưng WS-Security profile/implementation có quy tắc riêng về thời gian. Khi giao tiếp SOAP:

- Ưu tiên timestamp có timezone rõ, thường là `Z` cho UTC.
- Không parse bằng cách cắt chuỗi hoặc bỏ phần offset.
- Đừng so sánh hai chuỗi date-time theo thứ tự từ điển.
- Đừng dùng `LocalDateTime.now()` và ngầm áp timezone máy chủ cho giá trị UTC.
- Kiểm tra cả timestamp có offset và phần giây lẻ theo policy.
- Đồng bộ đồng hồ tất cả node, kể cả gateway xử lý security.

Một client đặt `Created` bằng giờ địa phương nhưng viết đuôi `Z` sẽ làm server hiểu sai thời điểm thực, gây lỗi có vẻ “ngẫu nhiên” theo timezone.

### 10.3. Phân biệt wall-clock và monotonic clock

- `Instant.now()`/`Clock` đọc **wall-clock**, cần để đối chiếu Timestamp từ xa.
- `System.nanoTime()` đo khoảng thời gian trong cùng process, phù hợp latency metric nhưng không phải giờ UTC.

Không so sánh `System.nanoTime()` với thời gian `wsu:Created`. Đồng thời phải xét clock jump/NTP corrections khi đánh giá edge cases; nên ưu tiên validator/thư viện có chính sách thời gian đã được kiểm thử.

## 11. Spring-WS và WSS4J: đặt logic ở đúng security interceptor

Spring-WS thường tích hợp **Apache WSS4J** qua lớp:

~~~java
org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor
~~~

Nhiệm vụ của interceptor ở phía **SOAP server** có thể gồm:

- Xác minh các security actions yêu cầu (ví dụ `Timestamp`, `UsernameToken`, `Signature`).
- Kiểm tra token/timestamp và gọi callback để tra secret hoặc credentials.
- Làm việc với phần xử lý nonce/signature replay do WSS4J cung cấp/cấu hình.
- Từ chối thông điệp không đáp ứng policy trước khi gọi endpoint.

Ở phía **SOAP client**, cùng họ interceptor có thể bảo vệ outgoing request, thêm timestamp, UsernameToken và chữ ký theo policy.

**Điểm quan trọng:** WSS4J không tự đoán toàn bộ chính sách doanh nghiệp. Bạn phải xác định security actions, credential source, clock skew/freshness, replay cache, chữ ký/keystore và thứ tự interceptor phù hợp với phiên bản được triển khai.

### 11.1. Cấu hình server qua `@EnableWs` và `WsConfigurer`

Ví dụ cấu hình Spring:

~~~java
package example.payments.ws;

import javax.security.auth.callback.CallbackHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
public class WsSecurityBeans {

    @Bean("inboundWsSecurity")
    public Wss4jSecurityInterceptor inboundWsSecurity(
            CallbackHandler credentialLookupCallback) {

        Wss4jSecurityInterceptor security =
                new Wss4jSecurityInterceptor();

        security.setValidationActions(
                "Timestamp UsernameToken");
        security.setValidationCallbackHandler(
                credentialLookupCallback);

        return security;
    }
}
~~~

Và đăng ký vào **chuỗi Spring-WS `EndpointInterceptor`**:

~~~java
package example.payments.ws;

import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
@EnableWs
public class WsSecurityRegistration implements WsConfigurer {

    private final Wss4jSecurityInterceptor security;

    public WsSecurityRegistration(
            @Qualifier("inboundWsSecurity")
            Wss4jSecurityInterceptor security) {
        this.security = security;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(security);
    }
}
~~~

**Điểm cần hiểu đúng:**

1. Bean `Wss4jSecurityInterceptor` phải được đăng ký trong chain đang xử lý SOAP endpoint. Chỉ tạo bean rồi không thêm vào `WsConfigurer` **không chứng minh** validator chạy.
2. `setValidationActions("Timestamp UsernameToken")` đặt các action dự kiến cần xử lý ở mức WSS4J, **không tự cung cấp** authentication DB, chữ ký hoặc replay store phân tán.
3. Nếu contract yêu cầu **SOAP Body/Timestamp được ký**, ví dụ trên **chưa đủ**; cần cấu hình `Signature` validation, keystore/truststore và policy signed parts phù hợp.
4. `@EnableWs` chỉ nên được cấu hình theo một chiến lược hạ tầng rõ; tránh tạo duplicate mappings với XML `<sws:annotation-driven/>`.
5. Header timestamp có thể bị lỗi **trước khi endpoint method chạy**. SOAP Fault từ security interceptor không nhất thiết do `SoapFaultMappingExceptionResolver` dành cho domain exceptions tạo.

### 11.2. Callback xác minh secret có trách nhiệm gì?

WSS4J có thể dùng `CallbackHandler` để lấy secret của user khi xác minh UsernameToken digest. Ý tưởng callback:

~~~java
import java.io.IOException;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.UnsupportedCallbackException;
import org.apache.wss4j.common.ext.WSPasswordCallback;

public final class CredentialLookupCallback
        implements CallbackHandler {

    private final CredentialStore credentials;

    public CredentialLookupCallback(CredentialStore credentials) {
        this.credentials = credentials;
    }

    @Override
    public void handle(Callback[] callbacks)
            throws IOException, UnsupportedCallbackException {
        for (Callback callback : callbacks) {
            if (!(callback instanceof WSPasswordCallback password)) {
                throw new UnsupportedCallbackException(callback);
            }

            String secret = credentials.findSharedSecret(
                    password.getIdentifier());
            if (secret == null) {
                throw new IOException("Credentials unavailable");
            }
            password.setPassword(secret);
        }
    }
}
~~~

`CredentialStore` là **interface/bean ứng dụng tự xây dựng**, không phải class của Spring-WS. Mẫu này giả định profile UsernameToken có shared secret; hãy cung cấp một `CallbackHandler` bean phù hợp trong Spring context, ví dụ:

~~~java
@Bean
CallbackHandler credentialLookupCallback(
        CredentialStore credentialStore) {
    return new CredentialLookupCallback(credentialStore);
}
~~~

Khi dùng password digest, WSS4J cần cách truy cập credential đúng kiểu để xác minh digest. Nếu backend chỉ lưu password hash một chiều không thể khôi phục, **không giả định** có thể dùng hash đó thay cho shared secret theo công thức UsernameToken Profile. Cân nhắc giải pháp authentication/certificate/token phù hợp với yêu cầu bảo mật hiện tại.

Đối với production:

- Không hard-code secret hoặc in secret/digest ra log.
- Dùng secret manager/vault, rotation và access control.
- Giới hạn/throttle xác thực sai để giảm brute force/DoS.
- Không lộ account existence qua Fault quá chi tiết.
- Theo dõi credential validity và đồng bộ cấu hình trên các replica.
- Kiểm tra các giá trị callback usage mà WSS4J yêu cầu theo phiên bản, không tùy tiện xử lý mọi callback như password validation.

### 11.3. Cấu hình freshness và replay cache nằm ở đâu?

Các thế hệ WSS4J có những option liên quan:

| Nhóm cấu hình | Tên khái niệm thường gặp trong WSS4J | Mục đích |
| --- | --- | --- |
| Timestamp lifetime | `timeStampTTL` / validation TTL | Giới hạn độ cũ của Timestamp |
| Future tolerance | `timeStampFutureTTL` | Giới hạn Created ở tương lai |
| Timestamp strictness | `timeStampStrict` | Bật/tắt kiểm tra thời gian nghiêm ngặt |
| Nonce replay protection | `enableNonceCache` và `ReplayCache` tương ứng | Theo dõi nonce đã xử lý |
| Signature replay protection | Signature replay cache/policy | Theo dõi trường hợp phát lại chữ ký |
| UsernameToken controls | Password type, nonce và Created requirements | Chỉ chấp nhận token profile phù hợp |

**Bảng này mô tả khái niệm/option WSS4J, không phải tuyên bố rằng mỗi mục có một setter cùng tên trên `Wss4jSecurityInterceptor` của mọi bản Spring-WS.** API đặt tham số có thể đi qua WSS4J handler properties, `RequestData`, callback/custom validator hoặc extension point khác tùy phiên bản.

Quy trình cấu hình chuẩn:

1. Xác định đúng artifact Spring-WS, WSS4J và SOAP message factory.
2. Đọc API/settings **của version đang chạy**; không chép setter không tồn tại.
3. Chọn TTL, future skew, strictness và token requirements theo contract.
4. Cấu hình replay cache phù hợp với topology (local JVM hoặc shared store).
5. Chạy test **same nonce twice**, **same nonce across replicas** và **timestamp boundaries**.
6. Kiểm tra WSS4J thực sự **từ chối**, không chỉ ghi log cảnh báo.

**Không coi “thư viện có nonce cache mặc định” là bằng chứng replay protection đã bật và phù hợp với cluster.** Phải test behavior thực tế.

## 12. Replay protection còn phụ thuộc chính sách chữ ký

Nhiều SOAP service dùng `Signature` với chứng chỉ X.509:

~~~text
SOAP Body (amount, paymentRequestId)
WS-Security Timestamp
WS-Addressing headers quan trọng (nếu policy yêu cầu)
          ↓
XML Signature theo signed-parts policy
          ↓
Server verify certificate/trust + signature + freshness + replay
~~~

Nếu signature **không bao phủ Timestamp**, attacker có thể sửa Created/Expires mà không làm hỏng chữ ký Body. Nếu signature không bao phủ Body, attacker có thể thay `amount`. Vì vậy không đủ để bật “Signature action” mà không kiểm tra **đúng signed parts**.

### 12.1. Signature replay cache

Một thông điệp có chữ ký số có thể bị gửi lại mà chữ ký vẫn hợp lệ. WSS4J có các cơ chế replay cache liên quan một số token/signature tùy profile và phiên bản. Khi dùng X.509:

- Xác minh chứng chỉ và trust anchors.
- Kiểm tra thời hạn chứng chỉ, mục đích sử dụng khóa và chính sách revocation phù hợp.
- Kiểm tra timestamp được ký và còn hiệu lực.
- Bật/chỉnh replay detection thích hợp cho kiểu message đã ký.
- Bảo đảm replay cache hoạt động xuyên các node nếu service chạy cluster.
- Không coi certificate serial number là nonce; nhiều request hợp lệ dùng cùng chứng chỉ.

### 12.2. TLS/mTLS không giải quyết message replay thay bạn

HTTPS/mTLS có thể bảo vệ request trên một kênh mạng và xác thực endpoint, nhưng khi application hoặc proxy hợp lệ gửi lại **một SOAP Envelope cũ**, tầng SOAP vẫn cần freshness/replay policy. Tùy threat model, TLS có thể giảm khả năng nghe lén nhưng không thay business idempotency.

### 12.3. UsernameToken và chữ ký số không phải cùng cơ chế

| Cơ chế | Chứng minh/kiểm tra chính | Chưa tự giải quyết |
| --- | --- | --- |
| UsernameToken password digest | Kiến thức về shared secret của principal theo profile | Toàn vẹn SOAP Body, business idempotency |
| XML Signature | Toàn vẹn/authenticity của các phần được ký | Message uniqueness |
| `wsu:Timestamp` | Freshness trong cửa sổ | Lặp lại trong cửa sổ |
| Nonce replay cache | Từ chối nonce lặp theo policy | Retry nghiệp vụ bằng nonce mới |
| TLS/mTLS | Bảo mật kênh và peer identity | End-to-end message replay qua các thành phần |
| Business idempotency key | Chống commit trùng theo định danh thao tác | Kiểm tra WS-Security token |

## 13. Hợp đồng SOAP: bảo mật Header và nghiệp vụ Body là hai lớp

Trong cách phát triển **contract-first**, schema XSD thường định nghĩa payload:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:p="urn:example:payments:v1"
    targetNamespace="urn:example:payments:v1"
    elementFormDefault="qualified">

    <xs:element name="SubmitPaymentRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="paymentRequestId">
                    <xs:simpleType>
                        <xs:restriction base="xs:string">
                            <xs:pattern value="PAY-[0-9]{4,12}"/>
                        </xs:restriction>
                    </xs:simpleType>
                </xs:element>
                <xs:element name="amount" type="xs:decimal"/>
                <xs:element name="currency" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="SubmitPaymentResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="receiptId" type="xs:string"/>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

XSD mô tả **nội dung nghiệp vụ**. Nó không tự yêu cầu:

- `wsu:Timestamp` trong SOAP Header.
- `wsse:UsernameToken`, Nonce hoặc PasswordDigest.
- Chữ ký của `Timestamp`/Body.
- Clock skew/replay-cache policy.
- Chứng chỉ tin cậy của đối tác.
- HTTP TLS/mTLS.

Những yêu cầu đó thường nằm trong **WS-SecurityPolicy**, thỏa thuận tích hợp, cấu hình SOAP stack và kiểm thử bảo mật. WSDL có thể mang hoặc tham chiếu policy theo profile được chọn, nhưng **chỉ xuất bản WSDL không tự kích hoạt replay cache** trên server.

### 13.1. `@Endpoint` không nên tự tin Header chưa được xác minh

~~~java
package example.payments.ws;

import javax.xml.transform.Source;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.xml.transform.StringSource;

@Endpoint
public class PaymentEndpoint {
    private static final String NS =
            "urn:example:payments:v1";

    @PayloadRoot(
            namespace = NS,
            localPart = "SubmitPaymentRequest")
    @ResponsePayload
    public Source submit(@RequestPayload Source request) {
        // Ví dụ tối giản, KHÔNG triển khai thanh toán thật.
        // Production: xác thực principal, quyền, idempotency
        // và transaction trước khi ghi nhận thanh toán.
        return new StringSource(
                "<p:SubmitPaymentResponse " +
                "xmlns:p=\"urn:example:payments:v1\">" +
                "<p:receiptId>R-1001</p:receiptId>" +
                "<p:status>ACCEPTED</p:status>" +
                "</p:SubmitPaymentResponse>");
    }
}
~~~

Ví dụ này chỉ cho thấy endpoint được chọn theo root QName. Nó **không thể chạy thanh toán thực an toàn**: chưa có JAXB mapping đầy đủ, XSD runtime validation, credential-derived principal, kiểm tra quyền hay chống xử lý trùng.

Với một request bị replay, **nếu WS-Security interceptor đã từ chối trước endpoint**, method `submit` không được tạo thêm bản ghi. Nhưng điều này còn phụ thuộc việc interceptor đã thực sự được thêm vào đúng chain và request đã được map; test security phải xác minh có chặn đúng.

### 13.2. Nhiều `EndpointMapping` có thể làm lệch kỳ vọng bảo mật

Trong Spring-WS, `EndpointInterceptor` thường được gắn với hạ tầng endpoint mapping. Nếu ứng dụng:

- Có nhiều SOAP servlet hoặc application context.
- Tạo mapping tùy chỉnh không có cùng interceptor list.
- Chỉ bảo vệ một operation nhưng còn endpoint khác có đường vào tương đương.
- Cho phép một HTTP route bypass gateway đã kiểm tra security.

thì request có thể đi qua **đường xử lý thiếu WS-Security enforcement**.

Không chỉ assert Spring bean `Wss4jSecurityInterceptor` tồn tại; cần gửi request **không có UsernameToken/Timestamp** và xác minh **mọi operation được bảo vệ** đều từ chối trên đường HTTP thật.

## 14. Phía SOAP client: tạo Timestamp và UsernameToken nhất quán

Một service Spring-WS có thể vừa làm **server** vừa dùng `WebServiceTemplate` làm **SOAP client** để gọi đối tác. Phía client cần phát sinh thông điệp theo security profile:

~~~text
1. Tạo JAXB request / XML payload đúng XSD.
2. Đặt SOAP/WS-Addressing Header cần thiết.
3. Thêm UsernameToken, nonce, Created và Timestamp.
4. Ký các parts cần thiết bằng WS-Security nếu hợp đồng yêu cầu.
5. Gửi qua HTTPS/mTLS và transport đã có timeout phù hợp.
6. Xác minh response/Fault và WS-Security response khi policy quy định.
~~~

Thứ tự này chỉ **mô tả ý đồ bảo mật**, không yêu cầu ứng dụng tự viết lần lượt các bước XML; để WSS4J/Spring-WS xử lý thứ tự actions, canonicalization và chữ ký theo cấu hình.

### 14.1. Ví dụ cấu hình outgoing security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
public class OutboundSecurityConfig {

    @Bean("outboundWsSecurity")
    public Wss4jSecurityInterceptor outboundWsSecurity() {
        Wss4jSecurityInterceptor security =
                new Wss4jSecurityInterceptor();
        security.setSecurementActions(
                "Timestamp UsernameToken");
        security.setSecurementUsername(
                "integration-client");
        security.setSecurementPassword(
                "REPLACE_WITH_SECRET_FROM_VAULT");
        security.setSecurementPasswordType(
                "PasswordDigest");
        return security;
    }
}
~~~

**Đây là mẫu cấu hình API cho mục đích học**, không phải mẫu quản trị secret production. Chuỗi `REPLACE_WITH_SECRET_FROM_VAULT` là placeholder; **không đưa mật khẩu thật vào source code, properties commit lên Git hoặc log**. Trong thực tế, lấy credential từ secret manager có rotation và hạn chế quyền, cấu hình client lifecycle đúng.

Để interceptor thực sự bảo vệ request, cần thêm nó vào **`WebServiceTemplate`**:

~~~java
WebServiceTemplate template = new WebServiceTemplate();
template.setMarshaller(jaxbMarshaller);
template.setUnmarshaller(jaxbMarshaller);
template.setInterceptors(new ClientInterceptor[] {
        outboundWsSecurity
});
~~~

`jaxbMarshaller` và `outboundWsSecurity` là các bean/biến đã cấu hình; thêm import tương ứng `WebServiceTemplate` và `ClientInterceptor` khi dùng trong project. **`WsConfigurer.addInterceptors(...)` của server không tự áp dụng cho `WebServiceTemplate` phía client.**

### 14.2. Nonce tự động cần được kiểm chứng trên dây

Đối với UsernameToken có `PasswordDigest`, một WSS4J implementation thường tạo nonce/Created theo profile. Tuy nhiên đừng suy rằng bất cứ cấu hình nào có `UsernameToken` cũng luôn tạo nonce và bật replay detection:

1. Gửi hai SOAP request hợp lệ liên tiếp bằng client.
2. Kiểm tra **nonce khác nhau** và timestamp hợp lý.
3. Đảm bảo server từ chối khi **phát lại nguyên XML đã gửi lần đầu**.
4. Đảm bảo một request mới với nonce mới nhưng cùng `paymentRequestId` được xử lý theo **business idempotency**, không tạo giao dịch thứ hai.

Nếu profile đối tác yêu cầu UsernameToken `PasswordText`, nonce/Created có thể có chính sách khác. Không dùng mặc định của profile này để suy cho profile kia.

### 14.3. Khi gửi lại sau timeout

Giả sử client gửi request R, không nhận response và retry:

~~~text
Attempt 1:
  paymentRequestId = PAY-1001
  nonce = N1
  Created = T1

Attempt 2:
  paymentRequestId = PAY-1001
  nonce = N2
  Created = T2
~~~

Điều này **khác phát lại cùng security token** vì N2/T2 mới; bảo mật có thể chấp nhận attempt 2. Server vẫn phải phát hiện cùng business key `PAY-1001` và **trả kết quả idempotent** hoặc thông báo trạng thái đã xử lý, tùy contract.

Không sử dụng retry với cùng UsernameToken đã ký đã hết hạn: đó có thể là một request bị từ chối bởi freshness/replay cache. Cũng không tạo `paymentRequestId` mới chỉ để tránh bị đánh dấu trùng, vì như vậy có thể tạo **hai thanh toán thực**.

## 15. Replay cache và bảo vệ tính nhất quán nghiệp vụ

### 15.1. Hai yêu cầu đồng thời dùng cùng nonce

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant R as Shared Replay Store
    participant P as Business Service
    A->>R: tryReserve(user, nonce)
    B->>R: tryReserve(user, nonce)
    R-->>A: true (first reservation)
    R-->>B: false (duplicate)
    A->>P: Xử lý nghiệp vụ theo authorization/idempotency
    Note over B: Bị từ chối trước nghiệp vụ
~~~

Nếu store không có atomic reservation, A và B có thể cùng qua kiểm tra “chưa thấy”. Vấn đề **không thể sửa** chỉ bằng cách lưu nonce vào `ConcurrentHashMap` ở mỗi node mà không đồng bộ.

### 15.2. Một nonce mới nhưng cùng payment ID

~~~mermaid
sequenceDiagram
    participant C as SOAP Client
    participant S as Security Layer
    participant D as Business Database
    C->>S: PAY-1001, nonce N1
    S->>D: Ghi transaction với unique paymentRequestId
    D-->>S: Commit PAY-1001
    S-->>C: Response bị mất trên mạng
    C->>S: Retry PAY-1001, nonce N2
    Note over S: N2 mới nên WS-Security có thể hợp lệ
    S->>D: Kiểm tra/ghi cùng paymentRequestId
    D-->>S: Đã tồn tại; trả trạng thái idempotent
    S-->>C: Kết quả theo contract
~~~

Với những operation có tác dụng phụ, dùng **unique constraint hoặc transaction/record idempotency** được thực hiện atomically trong DB. Đừng chỉ dùng một check “đã có paymentId chưa?” rồi insert riêng, vì hai request đồng thời vẫn có thể qua check.

### 15.3. “Đã thấy nonce” có đồng nghĩa “đã commit thanh toán”?

**Không.** Security layer có thể reserve nonce trước khi endpoint chạy. Nếu server crash sau reserve nhưng trước transaction, retry **nguyên token** có thể bị từ chối, dù nghiệp vụ chưa hoàn thành. Vì vậy cần có:

- Idempotency record theo business key.
- Trạng thái transaction có thể truy vấn.
- Policy retry với token mới nhưng business key cũ.
- Cơ chế đối soát khi SOAP response mất.

Không xóa replay cache key chỉ vì endpoint throw exception rồi cho phép client phát lại **nguyên token** vô hạn. Policy về thời hạn bảo mật và nghiệp vụ phải độc lập.

## 16. SOAP Fault khi Timestamp hoặc Nonce không hợp lệ

WS-Security có các failure modes như:

~~~text
Timestamp expired
Created too far in the future
UsernameToken missing nonce (khi policy yêu cầu)
Nonce duplicated / replay detected
UsernameToken password digest invalid
XML signature invalid
Certificate not trusted
Required signed part missing
~~~

Spring-WS và WSS4J có thể tạo security exception/Fault khác nhau tùy phiên bản và handler. **Đừng mặc định** rằng mọi lỗi trên sẽ được ánh xạ qua `SoapFaultMappingExceptionResolver` của domain exception; nhiều lỗi xảy ra trong security interceptor **trước khi gọi `@Endpoint`**.

### 16.1. Ví dụ một SOAP Fault bảo mật

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>Security validation failed</faultstring>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Đây là **một ví dụ Fault an toàn ở SOAP 1.1**, không phải output byte-for-byte mặc định của WSS4J. Một số profile WS-Security có mã lỗi/namespace riêng như `wsse:FailedAuthentication` hoặc `wsu:MessageExpired` tùy trường hợp; SOAP 1.2 dùng cấu trúc `Code/Reason/Detail` khác SOAP 1.1.

Điều cần đảm bảo:

- Caller thấy lỗi được phân loại theo contract, không thấy stack trace, password, nonce thô hoặc details cấu hình server.
- Không lộ thông tin giúp attacker suy đoán tên tài khoản hay cửa sổ chính xác ngoài những gì policy công khai.
- Đường HTTP/SOAP status phù hợp binding.
- Lỗi security được ghi metric/correlation ID ở hệ thống nội bộ.
- Client phân biệt security Fault và lỗi HTTP/TLS không có SOAP Envelope.

### 16.2. Không tự map mọi security exception thành lỗi nghiệp vụ

Không làm:

~~~java
catch (Exception ex) {
    throw new InvalidPaymentRequestException("Bad amount");
}
~~~

Nếu nguyên nhân thật là UsernameToken bị phát lại, server không nên báo `amount` sai. Lỗi bảo mật, lỗi XSD và lỗi nghiệp vụ có policy và observability khác nhau. Kết hợp chúng thành một exception làm client sửa sai tầng và che mất dấu hiệu tấn công.

### 16.3. Client nhận SOAP Fault và retry

Client Spring-WS có thể gặp `SoapFaultClientException` khi nhận Fault. Nhưng việc Fault có thể là lỗi replay **không đồng nghĩa** nên retry với nonce mới và lệnh mới:

- **Security Fault:** kiểm tra clock, credential, policy, chữ ký hoặc idempotency.
- **HTTP timeout:** trạng thái nghiệp vụ có thể chưa xác định.
- **HTTP 502 HTML:** lỗi gateway không phải SOAP Fault.
- **XSD validation Fault:** sửa payload theo contract.
- **Business Fault:** xử lý theo mã lỗi nghiệp vụ, không dựa riêng vào `faultstring`.

Retry tự động với thanh toán chỉ được thực hiện khi có cơ chế chống trùng/đối soát và chính sách thời gian, số lần, backoff rõ ràng.

## 17. Bảng kiểm soát security policy cho từng operation

| Operation SOAP | Timestamp | Nonce/replay cache | Signature | Business idempotency |
| --- | --- | --- | --- | --- |
| `GetPaymentStatus` | Theo chính sách chung | Có nếu UsernameToken được dùng và policy yêu cầu | Theo threat model của dữ liệu | Thường ít tác dụng phụ |
| `SubmitPayment` | **Bắt buộc theo policy nhạy cảm** | **Bắt buộc nếu profile chọn nonce** | Bảo vệ amount, account và timestamp | **Bắt buộc** |
| `CancelPayment` | Theo policy | Theo profile | Bảo vệ resource/action | **Bắt buộc** |
| `UploadDocument` | Theo policy | Theo profile | Bao phủ metadata/attachment khi cần | Theo document/request ID |
| `GetOrder` | Theo policy | Theo profile | Nếu thông tin nhạy cảm | Dựa vào contract |

Đây là **bảng ví dụ thiết kế**, không phải tiêu chuẩn buộc mọi operation phải dùng cùng cơ chế. Một tổ chức có thể chọn X.509 signature thay UsernameToken, hoặc mTLS + cơ chế authorization riêng. **Mỗi operation phải có chính sách công bố và được test thực**, không phải suy từ tên method Java.

## 18. Chiến lược kiểm thử Timestamp và clock skew

Kiểm thử bảo mật không thể dừng ở việc “SOAP client gửi thành công một request”. Phải gửi cả message **hợp lệ, cũ, tương lai, trùng nonce, sai chữ ký và thiếu header**. Cần xác minh server **từ chối trước khi nghiệp vụ chạy** ở những trường hợp bị cấm.

### 18.1. Test đơn vị cho mô hình thời gian

Với `TimestampWindow` ở mục 10, dùng `Clock.fixed(...)` để test ranh giới:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class TimestampWindowTest {
    private static final Instant NOW =
            Instant.parse("2026-11-27T02:00:00Z");

    private final TimestampWindow window =
            new TimestampWindow(
                    Clock.fixed(NOW, ZoneOffset.UTC),
                    Duration.ofMinutes(5),
                    Duration.ofSeconds(60));

    @Test
    void acceptsRecentMessage() {
        assertTrue(window.isFresh(
                NOW.minusSeconds(30),
                NOW.plusSeconds(120)));
    }

    @Test
    void rejectsExpiredMessage() {
        assertFalse(window.isFresh(
                NOW.minusSeconds(180),
                NOW.minusSeconds(1)));
    }

    @Test
    void rejectsCreatedTooFarInFuture() {
        assertFalse(window.isFresh(
                NOW.plusSeconds(61),
                NOW.plusSeconds(300)));
    }

    @Test
    void rejectsCreatedTooOldEvenWithLongExpires() {
        assertFalse(window.isFresh(
                NOW.minusSeconds(301),
                NOW.plusSeconds(120)));
    }

    @Test
    void rejectsExpiresBeforeCreated() {
        assertFalse(window.isFresh(
                NOW.minusSeconds(10),
                NOW.minusSeconds(20)));
    }
}
~~~

Đây là **test ví dụ logic thời gian độc lập**, không phải bài test chứng minh WSS4J đã cấu hình đúng. Nó kiểm tra cả việc Expires không thể “gia hạn” một message đã quá TTL.

### 18.2. Những ranh giới cần test thêm

Một bộ test timestamp chuyên sâu nên bao gồm:

- `Created == now - TTL`: có được chấp nhận hay không theo quy tắc ranh giới đã công bố.
- `Created == now + futureSkew`.
- `Expires == now`.
- `Expires == Created` hoặc `Expires < Created`.
- `Expires` vượt giới hạn sống tối đa server cho phép.
- `Created` thiếu, sai format, sai timezone, chứa giá trị bất thường.
- SOAP Header có **hai Timestamp** hoặc XML ID trùng.
- Timestamp không được ký trong policy yêu cầu ký.
- Timestamp đã ký nhưng Body đã bị thay.
- Client/server lệch đồng hồ theo hai chiều: **client nhanh hơn** và **client chậm hơn**.
- Request được tạo trước midnight, qua ngày mới hoặc qua thời điểm thay đổi DST (so sánh UTC phải không đổi).
- Thay đổi tốc độ xử lý hoặc hàng đợi gây delay lâu hơn TTL.

Khi test WSS4J thực, không tùy tiện đổi system clock trên server đang dùng chung. Dùng fixture có timestamp đã ký hợp lệ trong phạm vi môi trường test, test-specific clock/time source nếu version hỗ trợ, hoặc môi trường cô lập được phép điều khiển thời gian.

## 19. Kiểm thử replay nonce và concurrency

### 19.1. Bài test tối thiểu: gửi cùng một request hai lần

Quy trình:

1. Dùng **SOAP client được cấu hình WSS4J** tạo request có UsernameToken, nonce, Created, Timestamp và chữ ký nếu policy yêu cầu.
2. **Giữ nguyên bytes/message đã ký** để có thể gửi lại; không để client tái tạo token mới ở lần thứ hai.
3. Gửi request lần đầu tới server, xác nhận được chấp nhận hoặc đạt nhánh nghiệp vụ dự kiến.
4. Gửi lại **cùng SOAP Envelope** khi Timestamp vẫn còn mới.
5. Xác minh lần hai bị từ chối bởi replay policy, **không** chạy nghiệp vụ thêm lần nữa.
6. Ghi lại Fault category, nhưng không đưa raw password digest/nonce vào log test công khai.

**Phải dùng cùng nonce/digest của request gốc**. Nếu gọi lại `marshalSendAndReceive(...)` và security interceptor sinh nonce mới, bạn đang test hai request mới khác nhau, **không chứng minh replay detection**.

### 19.2. Test giữa hai node

~~~text
Node A: request nonce N1 -> accepted, reserve N1
Node B: replay nonce N1  -> must be rejected
~~~

Chạy qua một shared replay cache hoặc tầng xác minh tập trung. Nếu cache A và B độc lập, test có thể phát hiện lỗ hổng mà single-node test không tìm được.

### 19.3. Test race condition

Cho hai hoặc nhiều client gửi **cùng message hợp lệ** gần như đồng thời. Chỉ một request được phép reserve replay key thành công. Cần kiểm tra:

- Atomic store không có khoảng “GET rồi SET”.
- Không có hai operation thực thi thành công do race.
- Cache unavailable không chuyển sang silently accept.
- Metric duplicate tăng đúng.
- Không có data race trong các interceptor singleton.

Khi thực hiện với business service, còn phải có một test concurrency riêng cho **idempotency key**, vì hai request dùng nonce khác nhau vẫn có thể cùng hướng tới một thanh toán.

### 19.4. Test cache expiration

Đặt cửa sổ chấp nhận trong môi trường test:

~~~text
Timestamp TTL    = 300s
Future tolerance = 60s
Replay retention = 420s (ví dụ)
~~~

Kiểm tra:

1. Nonce đã reserve vẫn bị coi là duplicate ở mọi thời điểm request gốc **còn có thể được chấp nhận**.
2. Khi replay key hết hạn, **timestamp cũ cũng đã bị từ chối**, không có lỗ hổng do cache quên sớm.
3. Replay cache có eviction/cleanup không làm ảnh hưởng chính sách.
4. Thời gian của replay store không lệch đáng kể so với policy mà WSS4J đánh giá.

Không chỉ test “sau 420 giây key không còn” rồi coi như xong. Mục đích an toàn là **không có thời điểm request hợp lệ về thời gian nhưng nonce đã bị quên**.

## 20. Ma trận kiểm thử end-to-end SOAP/WS-Security

| Trường hợp | Kỳ vọng | Lưu ý |
| --- | --- | --- |
| Timestamp hợp lệ, nonce mới, credential đúng | Qua WS-Security | Endpoint còn phải authz/idempotency |
| SOAP Body sai XSD nhưng security hợp lệ | Từ chối ở validation | Đừng quy là nonce replay |
| Không có `wsse:Security` | Từ chối nếu operation yêu cầu security | Đường này phải được bảo vệ thật |
| Có UsernameToken nhưng thiếu Timestamp bắt buộc | Từ chối | Không fallback sang unauthenticated |
| UsernameToken thiếu nonce khi profile bắt buộc | Từ chối | Đúng với nonce requirement đã cấu hình |
| Nonce ngẫu nhiên mới nhưng password sai | Authentication failure | Cache không thay authentication |
| Nonce cũ, timestamp vẫn mới | **Replay rejected** | Không chạy nghiệp vụ lần hai |
| Nonce cũ qua một node khác | **Replay rejected** | Shared cache/central verification |
| Hai request nonce giống nhau đồng thời | Một lần reserve thành công | Atomic store |
| Nonce mới, business `paymentRequestId` cũ | Security có thể qua, business idempotency chặn trùng | Hai lớp tách biệt |
| Timestamp quá TTL | Từ chối | Không chỉ dựa vào Expires |
| `Expires` đã qua | Từ chối | Đường lỗi expiration |
| `Created` ở tương lai ngoài skew | Từ chối | Đồng bộ clocks |
| Client nhanh hơn server trong skew cho phép | Có thể chấp nhận | Còn phụ thuộc policy khác |
| Client chậm hơn, request vượt TTL | Từ chối | Không tăng TTL vô hạn |
| `Expires` xa bất thường | Từ chối theo server lifetime policy | Không tin Expires của client |
| Timestamp đã ký bị sửa | Chữ ký/validation failure | Nếu đã ký đúng part |
| Body bị sửa, Timestamp vẫn hợp lệ | Chữ ký Body phải thất bại | Kiểm tra signed parts |
| SOAP Header có XML ID trùng | Từ chối an toàn | Chống signature wrapping/misreference |
| WSS4J nonce cache bị tắt | Replay test phải phát hiện lỗ hổng | Không suy từ config bean |
| Replay store tạm không kết nối được | Áp fail-closed/policy đã duyệt | Không âm thầm bỏ qua |
| Gateway route bypass security | Request không được xử lý nghiệp vụ | Kiểm tra mọi entrypoint |
| SOAP 1.1 vs SOAP 1.2 | Security/Envelope/Fault đúng binding | Không trộn namespace |
| HTTP 502 HTML | Client nhận transport error, không phải SOAP Fault | Kiểm tra Content-Type |
| TLS/mTLS certificate không hợp lệ | Lỗi TLS trước SOAP | Không quy thành timestamp expiration |
| Read timeout sau khi ghi request | Outcome có thể chưa rõ | Dùng business idempotency |

### 20.1. Mock không thay transport/cluster test

- `MockWebServiceClient` kiểm thử Spring-WS server endpoint, mappings và interceptors trong application context.
- `MockWebServiceServer` kiểm thử SOAP client `WebServiceTemplate`.
- HTTP integration test kiểm tra Servlet mapping, SOAP version/Content-Type và TLS.
- Multi-instance test kiểm tra replay cache phân tán, HA/failover.
- Security adversarial test kiểm tra header tampering, duplicate IDs, replay concurrency và parser hardening.

Không suy rằng mock test thành công đồng nghĩa node B sẽ từ chối nonce đã được node A nhìn thấy. **Phải có bài test liên node**.

## 21. Chẩn đoán lỗi Timestamp, Nonce và replay

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đúng tầng |
| --- | --- | --- |
| Mọi request bị lỗi “expired” | Client giờ sai, TTL quá ngắn hoặc server clock lệch | UTC, NTP, TTL, DateTime parser |
| Chỉ lỗi ở một node | Clock/cache/config của node khác biệt | So sánh NTP, WSS4J profile, replay store |
| Request hợp lệ bị “future created” | Client nhanh hơn server hơn future skew | Chỉnh đồng hồ trước khi tăng skew |
| Request replay vẫn được chấp nhận | Nonce cache không bật/không chia sẻ, timestamp không được enforce | Replay test cùng raw message |
| Duplicate bị chặn ở node A nhưng không ở B | Cache per-JVM | Shared atomic replay store |
| Một request bị xử lý hai lần dù nonce khác | Retry nghiệp vụ dùng token mới | Business idempotency key |
| Lỗi khi cache đầy | Eviction sớm hoặc quota thiếu | Capacity/TTL, failure policy, metrics |
| UsernameToken luôn thất bại | Credential lookup sai, PasswordDigest profile khác | Callback handler, user, nonce/Created format |
| SOAP Body bị sửa nhưng message vẫn được chấp nhận | Chữ ký không bao phủ Body | Signed parts và signature verification |
| Signature lỗi khi timestamp thay đổi | Timestamp đã được ký rồi bị thay | Thứ tự bảo mật trong client |
| SOAP Fault khác mong đợi | Version/profile/resolver khác | Đọc Envelope/Fault wire |
| HTTP 404/415 | Route/Content-Type sai | Servlet/gateway/SOAP binding trước security |
| TLS handshake thất bại | Truststore/cert/hostname | Không liên quan nonce trực tiếp |
| Client retry liên tục vì security Fault | Clock/credential/policy sai | Không retry không giới hạn |

### 21.1. Một quy trình debug từ ngoài vào trong

1. **HTTP/TLS:** request có tới đúng `MessageDispatcherServlet` hay fail ở gateway/certificate?
2. **SOAP version:** Envelope là SOAP 1.1 hay 1.2? `mustUnderstand` Header có được xử lý?
3. **Security Header:** có `Timestamp`, `UsernameToken`/Nonce và Signature đúng namespace/profile?
4. **Time parsing:** Created/Expires có timezone rõ? Độ lệch UTC bao nhiêu?
5. **Validation actions:** WSS4J được cấu hình yêu cầu những action nào?
6. **Credential callback:** lookup shared secret có đúng user và profile?
7. **Signature coverage:** Body, Timestamp và các header quan trọng đã được ký không?
8. **Replay cache:** instance này dùng store nào, atomic reservation có hoạt động, TTL còn bao lâu?
9. **Routing:** có endpoint mapping hoặc đường HTTP khác bỏ qua security chain?
10. **Business idempotency:** paymentRequestId có bị xử lý hai lần dù security token khác nhau không?
11. **Fault:** client nhận SOAP Fault hay lỗi transport/timeout?
12. **Observability:** log nội bộ có correlation ID đủ để đối soát mà không lộ secrets không?

### 21.2. Logging bảo mật nhưng đủ để điều tra

Nên ghi:

~~~text
timestampValidationResult = accepted | expired | future | malformed
replayDecision           = new | duplicate | store_unavailable
principalIdHash          = <non-reversible internal representation>
operationQName           = {urn:example:payments:v1}SubmitPaymentRequest
soapVersion              = SOAP_1_1
securityPolicyId         = ws-policy-v1
nodeId                   = node-b
clockOffsetMs            = <observed/monitored>
correlationId            = REQ-1001
latencyMs                = <duration>
~~~

Không log **password**, UsernameToken digest, private keys, raw Nonce, full SOAP Header hoặc Body nhạy cảm. Cũng không đưa nonce thô/username chưa xác thực trực tiếp vào label của metrics để tránh cardinality explosion và rò rỉ dữ liệu.

### 21.3. Các metrics và cảnh báo

| Metric | Ý nghĩa |
| --- | --- |
| `ws_security_timestamp_expired_total` | Message quá hạn |
| `ws_security_timestamp_future_total` | Created vượt future skew |
| `ws_security_nonce_replay_total` | Nonce đã dùng |
| `ws_security_signature_invalid_total` | Chữ ký không hợp lệ |
| `ws_security_auth_failed_total` | Credential/identity thất bại |
| `replay_store_unavailable_total` | Kho replay không khả dụng |
| `replay_store_memory_usage` | Nguy cơ eviction sớm |
| `system_clock_offset_seconds` | Đồng bộ thời gian có vấn đề |
| `payment_duplicate_rejected_total` | Business idempotency đang chặn trùng |

Tên metric là **gợi ý**, không phải các metric mặc định của Spring-WS hoặc WSS4J. Khi alert tăng, phân tích theo operation/node/policy, nhưng không log các trường có cardinality không giới hạn hoặc giá trị bí mật.

## 22. Tình huống thực hành: cụm thanh toán vẫn chấp nhận phát lại

Một hệ thống thanh toán triển khai Spring-WS trên ba instance sau load balancer. Đội phát triển khai báo:

~~~text
WS-Security:
  validationActions = Timestamp UsernameToken Signature
  timestampTTL       = 300 seconds
  futureSkew         = 60 seconds

Deployment:
  node A, node B, node C
  mỗi node có nonce cache riêng trong JVM
  cache TTL = 120 seconds

Business:
  SubmitPaymentRequest(paymentRequestId, amount)
  chưa có unique constraint/idempotency record
~~~

Client gửi request với:

~~~text
paymentRequestId = PAY-9001
Created = 02:00:00 UTC
Expires = 02:05:00 UTC
Nonce   = N-9001  (ký hiệu minh họa, không phải nonce thực)
Signature = valid
~~~

Request đầu tiên tới node A lúc **02:01:00 UTC** và được xử lý. Sau đó cùng message được gửi nguyên vẹn tới node B lúc **02:01:20 UTC**; node B chưa từng thấy nonce. Cuối cùng, client retry cùng lệnh với nonce mới `N-9002` do mất response.

### 22.1. Câu hỏi

1. Vì sao chữ ký `Signature=valid` không ngăn node B xử lý lần hai?
2. Timestamp còn mới lúc 02:01:20 không?
3. Vì sao cache riêng từng JVM là lỗ hổng?
4. Ngay cả với một node, TTL nonce cache 120 giây có đủ không nếu Timestamp TTL 300 giây và future skew 60 giây?
5. Nếu chuyển sang Redis shared cache, thao tác nào bắt buộc phải atomic?
6. Có nên chọn fail-open khi Redis tạm mất kết nối để “khỏi gián đoạn thanh toán” không?
7. Retry với nonce mới `N-9002` phải được xử lý thế nào khi `paymentRequestId` không đổi?
8. Nếu thấy rất nhiều lỗi `Created in the future` từ một node, có nên đặt future skew thành 30 phút?
9. Làm sao kiểm tra trường `Timestamp` thật sự được bảo vệ bằng chữ ký?
10. Khi một security interceptor từ chối request, có nên kỳ vọng `@Endpoint` tạo `InvalidPaymentException` không?

### 22.2. Đáp án và giải thích

1. Chữ ký chứng minh nội dung được ký không bị thay đổi; **request cũ giữ nguyên chữ ký vẫn có thể verify**.
2. **Có**, 80 giây sau Created vẫn trong TTL 300 giây, Expires chưa qua, xét riêng những điều kiện thời gian ví dụ.
3. Node B không biết lịch sử nonce ở node A. Load balancing/failover có thể chuyển request tới cache khác.
4. **Không đủ**. Ngay khi cùng node, key có thể hết hạn trước khi Timestamp không còn được chấp nhận. Tính retention từ toàn bộ cửa sổ TTL + skew và các biên cần thiết.
5. **Insert-if-absent kèm thời hạn** phải atomic, không kiểm tra tồn tại rồi ghi ở hai bước.
6. Với giao dịch nhạy cảm, fail-open có thể phá thuộc tính chống phát lại. Ưu tiên fail-closed hoặc fallback đã được đánh giá, kiểm thử và giám sát.
7. Nonce N-9002 có thể hợp lệ về security nhưng **business idempotency** phải nhận ra PAY-9001, không commit lần hai; đối soát hoặc trả trạng thái đã lưu.
8. **Không nên mặc định**. Kiểm tra đồng hồ, UTC/timezone và NTP trước; future skew lớn làm tăng rủi ro.
9. Kiểm tra XML Signature references/signed parts thực tế và thử sửa `Created` mà không ký lại; validation phải thất bại theo policy.
10. **Không.** Security validation thường xảy ra trước endpoint và có đường lỗi/Fault riêng; phải kiểm tra Fault của interceptor/framework.

### 22.3. Bài thực hành có hướng dẫn

Tạo một SOAP service mẫu (không thực hiện thanh toán thật):

1. XSD định nghĩa `SubmitPaymentRequest` gồm `paymentRequestId` và `amount`; sinh JAXB classes.
2. `@Endpoint` ghi nhận request vào một repository giả có unique `paymentRequestId`.
3. Spring-WS `Wss4jSecurityInterceptor` yêu cầu Timestamp và UsernameToken, thêm Signature nếu hợp đồng cần.
4. Client `WebServiceTemplate` gửi request bảo mật, lưu một XML fixture để replay byte-for-byte.
5. Chạy server một instance: cùng nonce hai lần trong cửa sổ phải bị từ chối.
6. Chạy hai instance dùng shared replay store: node B phải chặn nonce đã được node A reserve.
7. Gửi cùng paymentRequestId với nonce mới: không tạo business record thứ hai.
8. Dùng timestamp quá hạn, tương lai, Expires không hợp lệ để kiểm tra Fault.
9. Test cache store outage và xác minh chính sách fail-closed.
10. Thử SOAP 1.1/1.2 và client implementation khác khi đối tác yêu cầu.

**Tiêu chí đạt:** kết hợp được **freshness validation + replay detection + business idempotency**, không có đường vào bypass security, không có double-processing khi retry hoặc load balancing.

## 23. Checklist production cho Timestamp, nonce và replay

1. **Contract/security policy:** xác định SOAP version, WS-Security actions và signed parts bắt buộc.
2. **Timestamp required:** xác minh `wsu:Timestamp` có Created/Expires theo profile và được bảo vệ tính toàn vẹn.
3. **TTL:** giới hạn tuổi message từ Created, không chỉ kiểm tra `Expires` của client.
4. **Clock skew:** có future tolerance nhỏ, dựa trên độ lệch thực tế; không mở rộng tùy tiện.
5. **Time synchronization:** NTP/time monitoring, đồng bộ tất cả node, kiểm tra UTC.
6. **UsernameToken:** PasswordText/PasswordDigest được công bố rõ; nonce/Created bắt buộc nếu policy yêu cầu.
7. **Nonce entropy:** dùng CSPRNG, không tái sử dụng hoặc sinh từ timestamp đơn giản.
8. **Credential management:** password/shared secret trong vault hoặc store được bảo vệ, không log.
9. **Replay cache enabled:** được xác minh bằng test phát lại **nguyên message**, không chỉ dựa vào tên property.
10. **Replay key:** principal đã xác thực và nonce/token identifier chuẩn hóa theo profile, có namespace key.
11. **Atomicity:** insert-if-absent atomically, không có race giữa kiểm tra và ghi.
12. **Retention:** TTL cache bao phủ toàn bộ khoảng message còn có thể được chấp nhận, kể cả future skew.
13. **Cluster:** shared replay store hoặc xác minh tập trung cho mọi instance/route.
14. **Failure mode:** cache outage, failover và eviction có policy an toàn, metrics và cảnh báo.
15. **Signed parts:** SOAP Body, Timestamp và header quan trọng được ký theo hợp đồng; kiểm tra chống XML signature wrapping.
16. **TLS/mTLS:** bảo vệ kênh và chứng chỉ đúng; không coi đó là replay cache.
17. **Authorization:** principal được phép thực hiện operation và truy cập tài nguyên đích.
18. **Idempotency:** business key/unique constraint chống commit trùng ngay cả khi nonce mới.
19. **SOAP Fault:** phân biệt security validation, XML schema, domain error và lỗi HTTP/TLS.
20. **Logging:** không phát tán password, digest, nonce raw, private keys hoặc XML payload nhạy cảm.
21. **Tests:** có test các ngưỡng TTL/skew, same nonce, cross-node, concurrency, cache outage và retry.
22. **Interoperability:** test với WSS4J/version của đối tác, XSD/WSDL, SOAP Action và WS-Addressing nếu áp dụng.
23. **Upgrade:** mỗi lần nâng Spring-WS/WSS4J cần kiểm tra lại default replay cache, timestamp validation và signed-part policy.
24. **Operations:** có runbook cho clock drift, credential rotation, replay spikes và cache degradation.

## 24. Ghi nhớ

- **`wsu:Timestamp`** chứa thông tin thời gian `Created`/`Expires`; phải kiểm tra **tuổi message theo server policy**, không tin Expires của client vô điều kiện.
- **Clock skew** là dung sai nhỏ cho chênh lệch đồng hồ, **không phải** lý do bỏ qua kiểm tra thời gian. Đồng bộ UTC và quan sát NTP giúp giảm lỗi giả.
- **`wsse:Nonce`** là giá trị ngẫu nhiên dùng một lần của UsernameToken. Nó cần CSPRNG và replay cache; Base64 chỉ là cách biểu diễn bytes.
- **`PasswordDigest`** trong UsernameToken Profile gắn nonce và Created với shared secret nhưng **không ký SOAP Body**.
- **Chữ ký số hợp lệ không có nghĩa message chưa từng được gửi**; request cũ vẫn có thể được phát lại nguyên vẹn.
- **Replay detection** cần một key phù hợp, **atomic insert-if-absent**, TTL bao phủ toàn bộ freshness window và store chia sẻ giữa các instance nếu chạy cluster.
- **Timestamp validation và replay cache khác nhau**: message còn mới vẫn có thể là duplicate, message cũ phải bị từ chối dù cache đã dọn key.
- **Wss4jSecurityInterceptor** phải được đăng ký đúng vào chain Spring-WS; cấu hình nonce/timestamp/cache/chữ ký phải được kiểm tra theo version và **test bằng request thật**.
- **WS-Security security replay protection không thay thế business idempotency**. Retry cùng thao tác với nonce mới vẫn có thể gây hai giao dịch nếu thiếu unique business key.
- **SOAP Fault bảo mật có thể phát sinh trước `@Endpoint`** và khác lỗi transport; client phải xử lý đúng loại, không retry mù quáng.
- Khi tích hợp doanh nghiệp theo hướng **contract-first**, cần kiểm thử đầy đủ **XSD/WSDL, JAXB, interceptor, SOAP Fault, WS-Security, chứng chỉ TLS/mTLS, clock skew, nonce replay, failover và idempotency**.
