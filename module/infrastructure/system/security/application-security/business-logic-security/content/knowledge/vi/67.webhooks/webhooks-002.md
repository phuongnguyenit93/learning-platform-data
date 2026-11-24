# Xác minh chữ ký webhook (Webhook signature validation)

Trong chương **Webhooks** của module **Bảo mật logic nghiệp vụ**, bài học này giải thích cách kiểm tra chữ ký webhook và gắn kết quả xác minh với quyết định nghiệp vụ. Mục tiêu là ngăn việc giả mạo sự kiện, sửa giá trị giao dịch, gửi lại yêu cầu đã xử lý hoặc mượn một thông báo hợp lệ để tác động sai đối tượng.

Webhook là yêu cầu HTTP do một hệ thống gửi tới hệ thống khác khi có sự kiện. Ví dụ, nhà cung cấp thanh toán thông báo đã thu tiền, hoàn tiền hoặc hủy giao dịch. Một endpoint nhận webhook có thể dẫn tới cập nhật trạng thái đơn hàng, ghi nhận tiền hoặc cấp quyền sử dụng dịch vụ, nên dữ liệu đầu vào cần được kiểm chứng trước khi tạo tác động.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích chữ ký webhook chứng minh điều gì và cần thêm điều kiện nào để thực thi nghiệp vụ.
- Xác minh đúng bytes của nội dung theo hợp đồng ký, tránh lỗi do phân tích hoặc tái tạo JSON.
- Thiết kế việc chọn khóa, so sánh mã xác thực, kiểm tra thời gian và xử lý quay vòng khóa.
- Kết hợp cửa sổ thời gian, định danh sự kiện, idempotency và transaction để chống phát lại.
- Ràng buộc nguồn đã xác minh với đơn vị, giao dịch, số tiền, loại tiền và chuyển trạng thái.
- Kiểm thử thông điệp bị sửa, chữ ký sai, khóa sai, giao lại đồng thời và sự kiện đến muộn.

## 2. Chữ ký đứng ở đâu trong luồng bảo vệ?

Một luồng nhận webhook có thể gồm:

```text
HTTP request
  -> kiểm tra giới hạn và hình thức yêu cầu
  -> lấy đúng nội dung cần xác minh
  -> xác minh chữ ký và điều kiện thời gian
  -> phân tích, kiểm tra schema
  -> ràng buộc nguồn với đối tượng nghiệp vụ
  -> chống trùng và kiểm tra chuyển trạng thái
  -> commit tác động cùng bằng chứng cần thiết
  -> phản hồi theo hợp đồng giao nhận
```

Với HMAC và một bí mật dùng chung, mã xác thực hợp lệ cho thấy nội dung khớp với bên có khả năng sử dụng bí mật đó, trong các giả định bảo mật của cơ chế. Bên nhận cũng giữ bí mật và có thể tạo HMAC, nên không dùng HMAC làm bằng chứng không thể chối bỏ giữa hai bên.

Với chữ ký bất đối xứng, bên ký dùng khóa riêng và bên nhận xác minh bằng khóa công khai tin cậy. Cách xây dữ liệu ký, quản lý khóa và thuật toán phải theo hợp đồng cụ thể.

Một chữ ký hợp lệ cần được gắn với những điều kiện tiếp theo:

| Điều cần chứng minh | Kiểm soát phù hợp |
| --- | --- |
| Nội dung thuộc nguồn tin cậy và không bị sửa ngoài giao thức | Xác minh chữ ký hoặc MAC với khóa được cấu hình đúng |
| Yêu cầu không quá cũ hoặc quá xa trong tương lai | Thời gian được bảo vệ bởi chữ ký và chính sách độ lệch |
| Cùng sự kiện không tạo tác động lặp | Inbox, ràng buộc duy nhất và khóa nghĩa vụ nghiệp vụ |
| Nguồn được phép tác động đối tượng này | Ánh xạ tài khoản nguồn, đơn vị và đối tượng |
| Trạng thái, số tiền và phê duyệt vẫn hợp lệ | Kiểm tra nghiệp vụ tại điểm áp dụng |

TLS bảo vệ kết nối và vẫn cần được dùng. Địa chỉ IP, một đường dẫn khó đoán hoặc chuỗi `User-Agent` không thay thế việc xác minh thông điệp theo hợp đồng.

## 3. Xác định chính xác dữ liệu được ký

Đây là bước dễ sai nhất. Hai hệ thống chỉ xác minh được cùng một mã nếu cùng tính toán trên đúng dữ liệu và cùng quy tắc.

Hợp đồng phải xác định:

- Thuật toán, cách biểu diễn chữ ký và phiên bản giao thức.
- Các thành phần tham gia dữ liệu ký: body, timestamp, định danh sự kiện, đích nhận hoặc thành phần khác.
- Thứ tự ghép, dấu phân cách, bảng mã và cách xử lý giá trị không hợp lệ.
- Cách xử lý nhiều chữ ký hoặc nhiều khóa trong giai đoạn quay vòng.
- Chính xác bytes nào của nội dung HTTP được dùng.

Không tự suy đoán công thức ký từ tên header. Khi tích hợp một nhà cung cấp cụ thể, phải dùng đặc tả và bộ kiểm chứng tương ứng của nhà cung cấp đó.

### 3.1. Không phân tích rồi tạo lại JSON trước khi xác minh

Hai nội dung sau có thể biểu diễn dữ liệu giống nhau nhưng có bytes khác nhau:

```json
{"amount":1000,"currency":"VND"}
```

```json
{ "currency": "VND", "amount": 1000 }
```

Khác biệt còn có thể đến từ thứ tự trường, ký tự Unicode, dấu xuống dòng, khoảng trắng, cách biểu diễn số hoặc ký tự escape.

Nếu giao thức ký raw body, phải giữ raw body theo đúng hợp đồng và xác minh trước khi chuyển thành đối tượng nghiệp vụ. Không dùng `toString()` của một object, không tự sắp xếp trường và không đổi bảng mã rồi hy vọng chữ ký vẫn đúng.

Có giao thức sử dụng biểu diễn chuẩn hóa riêng. Khi đó, cả hai phía phải thực hiện đúng quy tắc chuẩn hóa đó; không tự thay nó bằng việc serialize JSON theo mặc định của framework.

### 3.2. Phân biệt body với đóng gói truyền tải

Raw body không bao gồm các dòng đóng gói chunk của HTTP. Cần xác định ảnh hưởng của proxy, middleware, giải nén và bộ lọc đọc request.

Ví dụ, nếu bên gửi ký bytes trước nén nhưng framework cung cấp dữ liệu sau một cách biến đổi khác, phải làm rõ tại đâu lấy đúng dữ liệu. Không để middleware tự chuẩn hóa văn bản trước khi bộ xác minh chạy.

Trong giao thức minh họa của bài này, endpoint chỉ chấp nhận body không dùng content encoding, định dạng JSON UTF-8 và giới hạn kích thước trước khi giữ nội dung trong bộ nhớ. Đây là lựa chọn của ví dụ, không phải quy tắc chung của mọi webhook.

## 4. Một giao thức HMAC minh họa có hợp đồng rõ

Phần này tự định nghĩa giao thức phục vụ học tập; các header và công thức dưới đây không đại diện cho một nhà cung cấp cụ thể.

Bên gửi và bên nhận thống nhất:

- Thuật toán: HMAC-SHA-256.
- Body: bytes JSON UTF-8 đúng như gửi, không thêm hoặc bớt ký tự.
- Chữ ký: 32 bytes biểu diễn bằng 64 ký tự hex chữ thường, có tiền tố `v1=`.
- Mỗi header được liệt kê chỉ xuất hiện đúng một lần.
- ID sử dụng tập ký tự ASCII giới hạn, không chứa dấu xuống dòng.
- Timestamp là số giây Unix dạng thập phân chuẩn, được đưa vào dữ liệu ký.
- Định danh tích hợp lấy từ cấu hình endpoint tin cậy và giống nhau ở hai phía.

Các header ví dụ:

```text
X-Hook-Key-Id: key-2026-a
X-Hook-Timestamp: <unix-seconds>
X-Hook-Event-Id: evt-731
X-Hook-Signature: v1=<64-lowercase-hex-characters>
```

Dữ liệu ký:

```text
prefix = ASCII(
    "v1\n"
    + integrationId + "\n"
    + keyId + "\n"
    + timestampText + "\n"
    + eventId + "\n"
)

signedBytes = prefix || rawBodyBytes
signature = HMAC-SHA-256(secret, signedBytes)
```

Ở đây, `\n` trong công thức biểu diễn một byte xuống dòng LF. Body bắt đầu ngay sau dấu xuống dòng kết thúc prefix; không tự thêm một dấu xuống dòng ở cuối body.

Định danh tích hợp giúp ràng buộc nội dung với đích logic đã thống nhất. Khi cần bảo vệ thêm phương thức hoặc đường dẫn, hợp đồng phải đưa chúng vào dữ liệu ký theo cách chuẩn hóa rõ. Không tự đưa `Host` hoặc header chuyển tiếp chưa đáng tin vào công thức rồi coi đó là đích đã xác thực.

Giới hạn ký tự của ID và hình thức timestamp giúp dữ liệu ghép không mơ hồ. Phiên bản `v1` cũng phân tách cách diễn giải hiện tại với một giao thức khác trong tương lai.

## 5. Chọn khóa từ nguồn tin cậy

Một `keyId` trong header là dữ liệu chưa được xác minh. Nó có thể được dùng để tra một tập khóa cho phép, nhưng không được dùng để mở một đường dẫn tùy ý, tải khóa từ URL do người gọi chọn hoặc tự quyết định thuật toán.

Một mô hình tra khóa phù hợp:

```text
trusted endpoint configuration
  -> integrationId
  -> allowlisted keyId
  -> key material và trạng thái cho phép xác minh
```

Những nguyên tắc cần giữ:

- Khóa được giới hạn theo tích hợp hoặc tài khoản nguồn phù hợp.
- Không thử mọi bí mật của mọi khách hàng khi một khóa không khớp.
- Không suy ra đơn vị được tác động chỉ từ `tenantId` trong payload.
- Không để giá trị `alg` do request tự chọn thay thuật toán đã cấu hình.
- Bảo vệ khóa khỏi log, thông báo lỗi, mã nguồn và giao diện không cần truy cập.

Nếu một endpoint phục vụ nhiều tài khoản, việc chọn cấu hình xác minh phải có ánh xạ được kiểm soát. Một định danh định tuyến có thể giúp tìm cấu hình ứng viên, nhưng quyền của nguồn với đơn vị và đối tượng vẫn phải được xác minh trước tác động.

## 6. Minh họa xác minh bằng Java

Mã sau minh họa phần mật mã và kiểm tra thời gian của giao thức vừa định nghĩa, dùng các API có trong Java 17 trở lên. Adapter HTTP, kho khóa và kiểu lỗi ứng dụng được lược bỏ.

Trước khi gọi hàm, adapter phải bảo đảm mỗi header bắt buộc xuất hiện đúng một lần, body được đọc có giới hạn, định dạng nội dung được phép và không có phép biến đổi ngoài hợp đồng.

```java
record HookHeaders(
    String keyId,
    String timestampText,
    String eventId,
    String signature
) {}

record VerifiedWebhook(
    String integrationId,
    String eventId,
    String keyId,
    Instant signedAt,
    Instant receivedAt,
    byte[] verifiedBody
) {
    VerifiedWebhook {
        verifiedBody = verifiedBody.clone();
    }

    @Override
    public byte[] verifiedBody() {
        return verifiedBody.clone();
    }
}

VerifiedWebhook verify(
    HookHeaders headers,
    byte[] rawBody,
    WebhookConfig config,
    VerificationKeyStore keys,
    Clock clock
) throws GeneralSecurityException {
    requirePattern(headers.keyId(), "[A-Za-z0-9_-]{1,96}");
    requirePattern(headers.eventId(), "[A-Za-z0-9_-]{1,96}");
    requirePattern(headers.timestampText(), "0|[1-9][0-9]{0,11}");
    requirePattern(headers.signature(), "v1=[0-9a-f]{64}");

    // integrationId được kiểm tra hình thức khi nạp cấu hình.
    Instant receivedAt = clock.instant();
    VerificationKey key = keys.requireVerifyingKey(
        config.integrationId(), headers.keyId(), receivedAt
    );

    byte[] supplied = HexFormat.of().parseHex(
        headers.signature().substring(3)
    );

    String prefix = "v1\n"
        + config.integrationId() + "\n"
        + headers.keyId() + "\n"
        + headers.timestampText() + "\n"
        + headers.eventId() + "\n";

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(key.secretKey());
    mac.update(prefix.getBytes(StandardCharsets.US_ASCII));
    byte[] expected = mac.doFinal(rawBody);

    if (!MessageDigest.isEqual(expected, supplied)) {
        throw new WebhookVerificationException("INVALID_SIGNATURE");
    }

    Instant signedAt = Instant.ofEpochSecond(
        Long.parseLong(headers.timestampText())
    );

    if (signedAt.isBefore(receivedAt.minus(config.maxAge()))
        || signedAt.isAfter(receivedAt.plus(config.maxFutureSkew()))) {
        throw new WebhookVerificationException("OUTSIDE_TIME_WINDOW");
    }

    return new VerifiedWebhook(
        config.integrationId(), headers.eventId(), headers.keyId(),
        signedAt, receivedAt, rawBody
    );
}
```

Cần import các lớp tương ứng trong `java.time`, `java.security`, `javax.crypto`, `java.nio.charset` và `java.util`.

Các hợp đồng của thành phần được lược bỏ:

- `requirePattern` từ chối giá trị thiếu, null, quá dài hoặc không khớp toàn bộ mẫu; không tự trim hay đổi cách biểu diễn.
- `WebhookConfig` chỉ chứa cấu hình tin cậy; thời lượng là giá trị không âm có giới hạn và `integrationId` thuộc tập ASCII đã quy định.
- `requireVerifyingKey` chỉ trả khóa được phép xác minh cho đúng tích hợp tại thời điểm nhận, theo chính sách quay vòng và thu hồi.
- `secretKey()` cung cấp khóa cho HMAC-SHA-256 từ kho được bảo vệ.
- `WebhookVerificationException` là lỗi quyết định xác minh; không đưa khóa hoặc dữ liệu nhạy cảm vào thông báo.

Chữ ký được giải mã thành bytes và được yêu cầu có đúng độ dài trước khi so sánh. `MessageDigest.isEqual` phù hợp cho so sánh mã xác thực có độ dài đã kiểm soát, tránh tự viết vòng lặp trả về ngay ở byte đầu tiên khác nhau.

Hàm xác minh phải làm việc trên buffer body mà request sở hữu ổn định trong suốt lần gọi. Dữ liệu trả về được sao chép để phần xử lý sau sử dụng đúng nội dung đã xác minh, không phải đọc lại request hoặc nhận một mảng đã bị thay đổi.

Lỗi cấu hình hoặc lỗi hạ tầng mật mã cần được xử lý và quan sát riêng với chữ ký không hợp lệ. Không biến lỗi nội bộ thành kết quả “xác minh thành công” để tiếp tục nghiệp vụ.

## 7. Timestamp và cửa sổ chấp nhận

Timestamp chỉ hỗ trợ chống phát lại khi nó thuộc dữ liệu được xác minh. Nếu người gọi có thể thay timestamp mà không làm chữ ký sai, cửa sổ thời gian không giới hạn được tuổi của yêu cầu.

Cần phân biệt:

- `signedAt`: thời gian bên gửi gắn với lần ký hoặc giao theo hợp đồng.
- `receivedAt`: thời gian có thẩm quyền của bên nhận tại điểm kiểm tra.
- `occurredAt`: thời gian sự kiện nghiệp vụ xảy ra, nếu payload có trường này.
- Thời điểm xử lý và hoàn tất nghiệp vụ ở bên nhận.

Một sự kiện xảy ra hôm trước có thể được giao lại hôm nay với timestamp giao mới hợp lệ, nếu giao thức cho phép. Không dùng tuổi của sự kiện thay cho tuổi của lần ký mà chưa hiểu hợp đồng.

Cửa sổ chấp nhận cần cân bằng thời gian giao, retry và độ lệch đồng hồ phù hợp. Ví dụ một cửa sổ vài phút chỉ là lựa chọn triển khai, không phải chuẩn dùng chung.

Trong mã minh họa, hai biên được chấp nhận: `signedAt` không cũ hơn `receivedAt - maxAge` và không muộn hơn `receivedAt + maxFutureSkew`. Một hệ thống chọn quy tắc khác phải ghi rõ để kiểm thử đúng đầu mút.

Timestamp trong cửa sổ vẫn cho phép cùng một yêu cầu bị gửi lại nhiều lần trong cửa sổ đó. Cần chống trùng bền vững riêng, đồng thời bảo vệ các điều kiện nghiệp vụ tại thời điểm thực thi.

## 8. Chống phát lại bằng trạng thái bền vững

Chống phát lại có hai lớp bổ sung cho nhau:

1. Cửa sổ thời gian giới hạn tuổi của lần ký hoặc giao theo hợp đồng.
2. Bản ghi sự kiện và bất biến nghiệp vụ ngăn cùng tác động xảy ra nhiều lần.

Trong giao thức minh họa, khi retry, bên gửi giữ nguyên `eventId` và body, còn timestamp và chữ ký có thể được tạo lại. Quay vòng khóa cũng có thể làm `keyId` thay đổi. Vì vậy, khóa chống trùng không được dựa riêng vào chữ ký, timestamp hoặc khóa ký.

Một lựa chọn cho giao thức này là:

```text
event identity = (trustedIntegrationId, verifiedEventId)
delivery evidence = keyId + signedAt + receivedAt + bodyDigest
```

Nếu một nguồn có định danh sự kiện chỉ duy nhất trong từng tài khoản, khóa phải bổ sung tài khoản nguồn đã được xác minh và ràng buộc đúng. Không giả định mọi nhà cung cấp có cùng phạm vi duy nhất.

Những điều cần tránh:

- Chỉ giữ tập ID trong bộ nhớ của một instance.
- Ghi ID vào kho chống trùng trước khi xác minh, khiến người không có khóa chiếm trước ID của sự kiện thật.
- Đánh dấu đã hoàn tất trước khi tác động nghiệp vụ được commit.
- Coi cùng ID nhưng nội dung khác là một bản sao bình thường.
- Xóa dấu vết sớm rồi cho rằng chữ ký hợp lệ làm phát sinh quyền thực hiện lại.

Trong giao thức minh họa, cùng sự kiện phải có body bất biến, nên cùng ID nhưng body khác cần bị xử lý như xung đột. Với giao thức cho phép một số trường giao nhận thay đổi, cần tách bằng chứng bytes từng lần giao khỏi dấu vân tay các trường nghiệp vụ bất biến theo hợp đồng. Không tùy tiện bỏ các trường số tiền, người nhận hoặc đối tượng khỏi phép so sánh.

Ngoài chống trùng theo sự kiện, cần khóa nghĩa vụ nghiệp vụ. Hai sự kiện khác ID vẫn có thể cùng nói về một giao dịch hoặc cùng yêu cầu ghi nhận một lần thanh toán. Inbox không tự bảo đảm sổ cái hoặc đơn hàng không được cập nhật hai lần.

## 9. Transaction, inbox và phản hồi HTTP

Với xử lý đồng bộ trong một cơ sở dữ liệu, có thể tổ chức:

```text
1. Xác minh request và phân tích đúng body đã xác minh.
2. Xác định nguồn, tài khoản và phạm vi đối tượng hợp lệ.
3. Bắt đầu transaction.
4. Tạo hoặc khóa inbox theo định danh sự kiện đã xác minh.
5. Kiểm tra nội dung sự kiện có khớp bản ghi trước hay không.
6. Nếu đã hoàn tất nguyên vẹn, không tạo tác động mới.
7. Khóa đối tượng và kiểm tra nghĩa vụ, tham số, trạng thái.
8. Áp dụng tác động, lưu biên nhận, audit và outbox cần thiết.
9. Đánh dấu sự kiện đã xử lý và commit.
10. Phản hồi thành công theo hợp đồng của bên gửi.
```

Inbox cần ràng buộc duy nhất thực sự trong cơ sở dữ liệu. Hai request đến đồng thời không được đều thấy “chưa có” rồi cùng thực hiện.

Nếu server chết sau commit nhưng trước khi trả phản hồi, bên gửi có thể retry. Lần giao lại phải đọc được biên nhận và tránh tác động thứ hai.

Nếu lỗi xảy ra trước commit, bản ghi không được mang trạng thái đã hoàn tất. Chỉ lưu một dòng “đã nhìn thấy ID” rồi bỏ qua mọi lần tiếp theo có thể làm mất vĩnh viễn nghiệp vụ chưa xử lý.

### 9.1. Khi tiếp nhận rồi xử lý bất đồng bộ

Endpoint có thể phản hồi sau khi đã lưu bền vững sự kiện cùng ý định xử lý. Khi đó, cần phân biệt:

- **Đã tiếp nhận:** hệ thống đã chịu trách nhiệm giữ và tiếp tục xử lý.
- **Đã áp dụng:** tác động nghiệp vụ đã hoàn tất theo điều kiện.

Không phản hồi thành công chỉ vì đã đưa dữ liệu vào một hàng đợi trong bộ nhớ. Nếu dùng kho tiếp nhận và outbox, việc lưu bằng chứng cùng ý định phát nội bộ cần nhất quán. Sau khi đã xác nhận tiếp nhận, cơ chế nội bộ phải có retry, đối soát và chuyển xử lý phù hợp.

Consumer nội bộ cần biết sự kiện đã được xác minh tại thời điểm nhận thông qua bản ghi hoặc kênh tin cậy. Một trường `verified=true` do payload tự khai không phải bằng chứng.

Cửa sổ chữ ký dùng cho thời điểm tiếp nhận theo hợp đồng. Không mặc nhiên xác minh lại với đồng hồ nhiều giờ sau rồi loại bỏ một sự kiện đã được nhận hợp lệ chỉ vì nó chờ trong hàng đợi. Những điều kiện nghiệp vụ như thời hạn phê duyệt hoặc trạng thái đối tượng vẫn phải được xét tại điểm áp dụng tương ứng.

### 9.2. Khi tạo tác động ở hệ thống khác

Transaction cơ sở dữ liệu không làm một lệnh HTTP bên ngoài trở thành commit nguyên tử. Cần ý định bền vững, khóa idempotency ở nơi nhận nếu có, xác nhận kết quả và đối soát khi chưa rõ.

Webhook hợp lệ không miễn trừ rủi ro “đã gửi lệnh nhưng mất phản hồi”. Không tạo lệnh nghiệp vụ mới với ID mới chỉ vì lần gọi trước timeout.

## 10. Ràng buộc chữ ký với tài khoản và đối tượng nghiệp vụ

Giả sử một webhook đã được xác minh thông báo thanh toán thành công. Trước khi đánh dấu đơn hàng đã thanh toán, hệ thống còn cần kiểm tra:

- Nguồn và môi trường đã xác minh đúng với cấu hình tích hợp, chẳng hạn môi trường thử nghiệm hay thực tế.
- Tài khoản người bán trong sự kiện khớp tài khoản được cấu hình cho đơn vị.
- Giao dịch ngoài hệ thống khớp lần thanh toán đã được tạo và lưu trước đó.
- Đơn hàng thuộc đúng đơn vị và đúng quan hệ với lần thanh toán.
- Số tiền, loại tiền và các thành phần liên quan đáp ứng hợp đồng nghiệp vụ.
- Loại sự kiện cho phép chuyển trạng thái đang xét.
- Chưa có biên nhận ghi nhận cùng tác động hoặc nghĩa vụ đã hoàn tất.

Không chỉ tìm đơn hàng theo `orderId` trong body rồi đặt `paid = true`. Một giá trị metadata do khách hàng từng nhập vẫn có thể xuất hiện trong một webhook được ký đúng.

Ví dụ, khách hàng được phép ghi một mã tham chiếu tùy ý khi khởi tạo thanh toán. Việc nhà cung cấp ký lại mã tham chiếu đó chỉ chứng minh nội dung thông báo được bảo vệ theo giao thức; nó không biến mã tham chiếu thành bằng chứng rằng khách hàng sở hữu đơn hàng mang mã đó.

Vì vậy, cần đối chiếu với các liên kết máy chủ đã lưu: nguồn, tài khoản, mã thanh toán, đơn vị, đơn hàng và giá trị được phê duyệt. Kiểu số và đơn vị tiền cũng phải theo hợp đồng; không so sánh một số tính theo đơn vị nhỏ nhất với một số được hiểu theo đơn vị tiền chính.

Nếu cần lấy thêm dữ liệu để xác nhận, chỉ gọi API của nguồn từ cấu hình tin cậy và dùng đúng danh tính tích hợp. Không tải một URL do payload tự chỉ định rồi coi phản hồi đó là bằng chứng.

## 11. Chữ ký hợp lệ và máy trạng thái nghiệp vụ

Sự kiện có thể hợp lệ về nguồn nhưng đến muộn hoặc sai thứ tự. Việc xác minh chữ ký không giải quyết thứ tự nghiệp vụ.

Ví dụ:

```text
PENDING -> PAID
PENDING -> PAYMENT_FAILED
PAID -> REFUNDED
```

Đây chỉ là mô hình minh họa. Một sự kiện thất bại của lần thanh toán cũ không được hạ đơn đã thanh toán bằng một lần khác về chưa thanh toán.

Cần kiểm tra mã lần thanh toán, phiên bản hoặc trình tự do nguồn bảo đảm nếu có, cùng trạng thái miền hiện tại. Không chỉ dùng timestamp trong payload để ghi đè giá trị đang có.

Một đơn hàng đã hủy vẫn có thể nhận thông báo thu tiền thật xảy ra trước đó. Không được xóa hoặc phủ nhận khoản thu chỉ để giữ trạng thái đơn hàng đơn giản. Có thể cần ghi nhận sự thật thanh toán và tạo nghĩa vụ xử lý ngoại lệ hoặc hoàn tiền theo chính sách riêng.

Những chuyển trạng thái có ảnh hưởng tiền, giá hoặc quyền phải giữ bất biến tương ứng:

- Không ghi nhận một khoản thu hai lần.
- Không hoàn vượt số tiền được phép.
- Không cấp quyền cho đối tượng ngoài phạm vi.
- Không biến sự kiện hoàn tất thành phê duyệt cho một hành động khác.
- Không sửa lịch sử để che một sự kiện đã tạo tác động.

## 12. Quay vòng và thu hồi khóa

Một chính sách quay vòng cần phân biệt khóa dùng để ký mới với khóa còn được phép xác minh các lần giao hợp lệ.

Một tiến trình ví dụ:

1. Tạo khóa mới trong kho được bảo vệ và gắn với đúng tích hợp.
2. Cập nhật bên nhận để nhận biết khóa mới theo chính sách đã thống nhất.
3. Chuyển bên gửi sang ký bằng khóa mới.
4. Giữ khóa cũ để xác minh trong khoảng chuyển tiếp được giới hạn.
5. Ngừng chấp nhận khóa cũ theo thời hạn và điều kiện đã định.
6. Theo dõi các lần giao vẫn dùng khóa cũ và xử lý tồn đọng.

Không giữ khóa cũ vô thời hạn vì còn một số retry. Cũng không giả định mọi lần giao cũ dùng timestamp lúc sự kiện xảy ra; cần hiểu quy tắc ký lại của nguồn.

Thu hồi do nghi lộ khóa là tình huống riêng. Một HMAC đúng với khóa đã lộ không còn tạo cùng mức tin cậy. Hệ thống cần chính sách dừng chấp nhận khóa, đối soát sự kiện liên quan và khôi phục quan hệ tin cậy.

Bằng chứng trước đó phải được giữ nguyên để điều tra. Nếu cần đánh giá lại các sự kiện đã nhận, thực hiện theo một quy trình rõ thay vì âm thầm xóa inbox rồi phát lại mọi thứ.

Một số giao thức hỗ trợ nhiều chữ ký trong cùng request khi chuyển khóa. Khi triển khai giao thức đó, phải phân tích đúng danh sách, giới hạn số lượng và chỉ chấp nhận chữ ký hợp lệ thuộc thuật toán, phiên bản và khóa được phép. Ví dụ HMAC trong bài cố ý yêu cầu một header chữ ký duy nhất; không tự mở rộng cú pháp của nó mà bỏ qua kiểm soát.

## 13. Lỗi triển khai thường gặp

### 13.1. Xác minh sau khi đã tạo tác động

Nếu đã cập nhật đơn hoặc gọi cấp quyền rồi mới kiểm tra chữ ký, thao tác từ chối phía sau không làm biến mất tác động trước đó. Mọi quyết định tạo tác động phải dùng kết quả xác minh thành công.

### 13.2. Tin thông tin tự khai để chọn thẩm quyền

Các trường `verified`, `role`, `tenantId`, `isAdmin` hoặc `provider` trong body không tự tạo quyền. Nguồn đã xác minh và dữ liệu máy chủ mới là căn cứ ràng buộc phạm vi.

### 13.3. Cho phép bỏ chữ ký trong môi trường thực

Một cờ kiểu `skipSignature=true`, một header gỡ lỗi hoặc nhánh xử lý khi thiếu bí mật có thể mở đường giả mạo. Cấu hình nhận thực tế phải kiểm tra được yêu cầu xác minh trước khi phục vụ.

Dữ liệu thử và dữ liệu thật cần được tách theo cấu hình, khóa và liên kết đối tượng phù hợp. Một thông điệp được ký đúng bằng khóa thử không được tạo tác động thực.

### 13.4. Lùi về cơ chế yếu hơn khi xác minh thất bại

Không chuyển từ chữ ký sai sang “chấp nhận nếu IP đúng” hoặc “tin vì có mã đơn”. Kiểm soát bổ sung không nên trở thành đường bỏ qua yêu cầu chữ ký đã đặt ra.

Nếu nguồn có cơ chế xác minh dự phòng chính thức, nó phải được cấu hình và triển khai theo hợp đồng riêng có điều kiện rõ.

### 13.5. Header trùng hoặc phép phân tích không nhất quán

Một tầng đọc header đầu tiên, tầng khác đọc header cuối cùng có thể tạo cách hiểu khác nhau. Adapter phải xử lý số lần xuất hiện theo đúng hợp đồng.

Tương tự, JSON có tên trường trùng hoặc số không đúng kiểu có thể bị các parser diễn giải khác nhau. Sau xác minh, hãy phân tích bằng quy tắc chặt chẽ, từ chối nội dung mơ hồ và dùng đúng đối tượng đã phân tích cho quyết định nghiệp vụ.

### 13.6. Dùng chữ ký hoặc timestamp làm khóa chống trùng

Một sự kiện được ký lại có thể có chữ ký mới nhưng vẫn là cùng nghĩa vụ. Khóa sự kiện và khóa tác động phải dựa trên định danh ổn định theo phạm vi được bảo đảm.

## 14. Phản hồi, log và xử lý lỗi

Phản hồi ra ngoài nên theo hợp đồng tích hợp và đủ ổn định để bên gửi quyết định retry. Không trả bí mật, chữ ký tính lại hoặc thông tin đối tượng nội bộ cho một request chưa xác minh.

Các nhóm lỗi cần được phân biệt trong quan sát nội bộ:

| Nhóm | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Hình thức không hợp lệ | Thiếu header, chữ ký sai độ dài, body quá lớn | Từ chối trước nghiệp vụ |
| Không xác minh được | Khóa không được phép, HMAC không khớp | Từ chối, lưu bằng chứng tối thiểu phù hợp |
| Ngoài cửa sổ | Timestamp cũ hoặc quá xa tương lai | Từ chối lần giao theo chính sách; có đường đối soát nếu cần |
| Hạ tầng tạm thời lỗi | Kho tiếp nhận chưa ghi được | Không xác nhận tiếp nhận bền vững khi chưa lưu được |
| Xung đột sự kiện | Cùng ID nhưng nội dung nghiệp vụ không khớp | Cách ly hoặc chuyển điều tra |
| Nghiệp vụ chưa phù hợp | Sai tài khoản, sai tiền, trạng thái không cho phép | Không tạo tác động; ghi nhận và xử lý theo miền |

Không ghi toàn bộ header xác thực, bí mật hoặc payload nhạy cảm chỉ để kiểm tra lỗi. Log có thể dùng định danh tích hợp tin cậy, định danh sự kiện với nguồn gốc rõ, mã lý do, thời gian nhận và dấu vân tay nội dung phù hợp.

Đối với request chưa xác minh, mọi ID tự khai cần giới hạn độ dài và được xử lý như dữ liệu chưa đáng tin. Không để chúng giả mạo dòng log hoặc tạo vô hạn nhãn theo dõi.

Thông báo “đã nhận” không đồng nghĩa “đã áp dụng thành công”. Trạng thái nội bộ cần thể hiện điều này để vận hành không đóng một sự cố chỉ vì endpoint đã trả phản hồi thành công.

## 15. Tình huống xuyên suốt: xác nhận thanh toán

Giả sử máy chủ đã tạo lần thanh toán `payment-842` cho đơn `order-551` của `tenant-17`, với số tiền và loại tiền được lưu trước đó.

1. Endpoint nhận body có giới hạn và giữ nguyên bytes theo hợp đồng. Các header bắt buộc được kiểm tra không trùng và đúng hình thức.
2. Cấu hình endpoint xác định tích hợp và tập khóa được phép. `keyId` chỉ chọn một khóa trong tập đó.
3. Bộ xác minh tính HMAC trên prefix đã định và body, so sánh bytes, rồi kiểm tra timestamp.
4. Hệ thống phân tích đúng body đã xác minh, kiểm tra schema và ánh xạ tài khoản nguồn với `tenant-17`.
5. Trong transaction, hệ thống lấy hoặc tạo inbox theo sự kiện, đối chiếu nội dung, khóa lần thanh toán và đơn liên quan.
6. Nó kiểm tra mã giao dịch, số tiền, loại tiền, trạng thái và khóa nghĩa vụ trước khi ghi nhận khoản thu.
7. Kết quả, audit, sự kiện phát nội bộ và trạng thái inbox được commit theo mô hình đã chọn.
8. Server mất kết nối trước phản hồi. Bên gửi retry cùng sự kiện với timestamp và chữ ký mới. Hệ thống xác minh lần giao mới, nhận ra nghĩa vụ đã xử lý và không ghi nhận tiền lần nữa.
9. Nếu một sự kiện khác ID vẫn nói về cùng khoản thu, ràng buộc nghiệp vụ tiếp tục ngăn ghi nhận trùng.
10. Nếu sự kiện có chữ ký đúng nhưng số tiền không khớp, hệ thống không tự sửa giá đơn hàng để làm cho nó khớp. Nó giữ bằng chứng và chuyển sang xử lý ngoại lệ hoặc đối soát.

Người không có khóa không thể chỉ sửa `orderId` rồi giữ nguyên chữ ký. Nhưng một chữ ký đúng cũng không cho phép bỏ việc kiểm tra quan hệ đơn hàng, đơn vị và lần thanh toán đã lưu.

## 16. Kiểm thử chữ ký và các tình huống lạm dụng

Kiểm thử nên có bộ mẫu độc lập với hàm xác minh. Nếu bên tạo chữ ký kiểm thử và bên xác minh dùng chung một phép chuẩn hóa sai, cả hai có thể cùng sai mà ca kiểm thử vẫn qua.

Với giao thức minh họa, cần cố định body dưới dạng bytes, header, khóa thử và kết quả mong đợi. Các dữ liệu này chỉ phục vụ kiểm thử, không dùng bí mật thực tế.

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Request hợp lệ với bytes gốc | Xác minh thành công; tiếp tục các kiểm tra nghiệp vụ |
| Sửa một byte trong body | Không xác minh được |
| Đổi khoảng trắng hoặc thứ tự trường sau khi ký raw body | Không xác minh được chữ ký cũ |
| Body chứa Unicode hoặc xuống dòng cuối | Dùng chính xác bytes theo mẫu, không tự chuẩn hóa |
| Thiếu header hoặc có nhiều giá trị theo cách bị cấm | Từ chối trước tác động |
| Chữ ký sai độ dài, sai prefix hoặc sai encoding | Từ chối có kiểm soát |
| Đổi timestamp, event ID hoặc key ID nhưng giữ chữ ký | Không vượt được xác minh theo công thức |
| Dùng khóa của tích hợp khác | Không được chọn khóa ngoài phạm vi |
| Timestamp đúng tại hai biên cửa sổ | Kết quả đúng theo quy tắc đầu mút đã công bố |
| Timestamp quá cũ hoặc quá xa tương lai | Bị từ chối theo chính sách |
| Gửi lại nguyên vẹn trong cửa sổ | Không tạo tác động thứ hai |
| Retry cùng sự kiện với timestamp hoặc khóa mới | Chống trùng vẫn dựa trên định danh sự kiện và nghĩa vụ |
| Hai request cùng sự kiện đến đồng thời | Một tác động, inbox và biên nhận nhất quán |
| Cùng ID nhưng nội dung bất biến khác nhau | Xử lý xung đột thay vì âm thầm ghi đè |
| Hai ID khác nhau cho cùng khoản thu | Không ghi nhận tiền trùng |
| Chữ ký đúng nhưng sai tài khoản, đơn vị, tiền hoặc loại tiền | Không chuyển trạng thái trái bất biến |
| Sự kiện đến muộn hoặc đảo thứ tự | Xử lý theo trạng thái và quan hệ giao dịch đúng |
| Chết sau commit nhưng trước phản hồi | Retry không thực hiện lại tác động |
| Ghi inbox, audit hoặc outbox lỗi trong transaction | Không đánh dấu hoàn tất một tác động chưa commit đúng |
| Khóa cũ trong và ngoài giai đoạn cho phép xác minh | Kết quả tuân chính sách quay vòng |
| Khóa bị thu hồi do nghi lộ | Không tiếp tục chấp nhận chỉ vì HMAC tính đúng |
| Khóa thử được dùng để gửi sự kiện cho đối tượng thật | Không tạo tác động thực |
| Consumer nội bộ xử lý muộn sau khi tiếp nhận hợp lệ | Dùng bằng chứng tiếp nhận tin cậy và kiểm tra nghiệp vụ hiện tại |

Không cần làm một kiểm thử thời gian chạy thiếu ổn định để tự chứng minh tính chống rò rỉ thời gian của mã so sánh. Chọn API mật mã phù hợp, kiểm soát độ dài và tránh viết phép so sánh trả về sớm.

Với transaction và request đồng thời, điều khiển thứ tự bằng điểm đồng bộ hoặc cơ chế kiểm thử phù hợp. Với timestamp, dùng `Clock` có thể điều khiển để kiểm tra chính xác trước biên, tại biên và sau biên.

## 17. Những quyết định cần rõ trước khi triển khai

Một thiết kế xác minh webhook đủ cụ thể cần trả lời được:

1. Giao thức ký bao phủ những bytes và trường nào, theo thuật toán và phiên bản nào?
2. Body đi qua proxy và middleware ra sao trước khi được xác minh?
3. Ai quản lý khóa, endpoint nào được chọn khóa nào và khi nào khóa hết quyền xác minh?
4. Timestamp có được bảo vệ không, mang ý nghĩa gì và cửa sổ chấp nhận là bao nhiêu?
5. Định danh sự kiện có phạm vi duy nhất nào, còn định danh nghĩa vụ nghiệp vụ là gì?
6. Phản hồi thành công xác nhận đã tiếp nhận hay đã áp dụng, và bằng chứng nào đã bền vững lúc đó?
7. Nguồn đã xác minh được phép tác động đơn vị, tài khoản và giao dịch nào?
8. Những kiểm tra số tiền, loại tiền, phê duyệt và trạng thái phải đúng trước tác động?
9. Retry, xử lý đồng thời và sự kiện sai thứ tự được bảo vệ bằng cơ chế nào?
10. Khi có xung đột, khóa lộ hoặc kết quả nghiệp vụ chưa rõ, đường đối soát và chuyển xử lý là gì?

Xác minh chữ ký tạo căn cứ tin cậy cho dữ liệu nhận được theo một hợp đồng cụ thể. Để bảo vệ logic nghiệp vụ, kết quả đó phải đi cùng giới hạn nguồn, kiểm tra đối tượng, máy trạng thái và chống trùng tại nơi tạo tác động.
