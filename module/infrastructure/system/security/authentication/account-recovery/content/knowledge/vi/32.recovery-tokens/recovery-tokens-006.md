# Recovery token comparison — So khớp token khôi phục an toàn

## 1. So khớp token là một bước xác minh bí mật

Khi người dùng mở liên kết hoặc nộp mã khôi phục, máy chủ cần xác định giá trị họ gửi có tương ứng với token đã cấp hay không. Bước này thường trông đơn giản như một phép so sánh chuỗi, nhưng sai sót có thể làm lộ thông tin qua thời gian xử lý, chấp nhận sai dạng dữ liệu hoặc cho phép dùng lại token.

Trong bài này, **recovery token comparison** là việc so khớp phần bí mật của token với giá trị kiểm chứng ở máy chủ. Trọng tâm là cách biểu diễn, phép biến đổi trước khi so sánh và cách dùng kết quả. Bài không dùng từ “comparison” theo nghĩa lựa chọn giữa các sản phẩm cung cấp dịch vụ khôi phục.

Một phép so sánh đúng cần trả lời: “người gửi đã đưa ra đúng bí mật tương ứng với bản ghi này chưa?”. Nó chưa trả lời đầy đủ: “token còn được phép sử dụng cho hành động khôi phục hiện tại không?”.

OWASP khuyến nghị token đặt lại mật khẩu được tạo bằng nguồn ngẫu nhiên mật mã, đủ mạnh trước việc đoán, lưu an toàn, có thời hạn và dùng một lần. Việc so khớp phải nằm trong thiết kế đáp ứng các thuộc tính đó. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Sau bài học, người học có thể:

- Phân biệt token gốc, phần định vị và giá trị kiểm chứng được lưu.
- Xử lý định dạng mà không vô tình thay đổi bí mật.
- Dùng phép so sánh phù hợp thay vì so sánh chuỗi hoặc tiền tố.
- Giải thích cách áp dụng `MessageDigest.isEqual` với digest có độ dài cố định trong Java.
- Gắn kết quả so khớp với phạm vi, thời hạn, thu hồi và tiêu thụ nguyên tử.

## 2. Token gốc và giá trị kiểm chứng là hai dữ liệu khác nhau

Giả sử dịch vụ tạo phần bí mật `S` gồm 32 byte ngẫu nhiên bằng nguồn ngẫu nhiên mật mã. Khi phát hành, dịch vụ gửi biểu diễn Base64URL của `S` cho người nhận qua kênh phù hợp. Máy chủ có thể lưu:

```text
storedVerifier = SHA-256(S)
```

Khi nhận phần bí mật `C` từ client, máy chủ tính:

```text
candidateVerifier = SHA-256(C)
matches = secureCompare(storedVerifier, candidateVerifier)
```

Trong thiết kế này, giá trị gửi cho người dùng là `S`, không phải `storedVerifier`. Client không được phép gửi một hash do họ tự khai rồi yêu cầu máy chủ tin rằng hash đó chứng minh họ biết token gốc.

Đặc biệt, nếu máy chủ chấp nhận trực tiếp `storedVerifier` làm bằng chứng, giá trị lưu trong cơ sở dữ liệu đã trở thành một bearer token khác. Điều đó làm mất lợi ích của việc chỉ lưu giá trị kiểm chứng.

SHA-256 ở ví dụ phù hợp với giả định phần bí mật thật sự ngẫu nhiên và có entropy cao. Không suy rộng rằng băm nhanh một mã sáu chữ số hoặc câu trả lời dễ đoán cũng bảo vệ được trước dò tìm offline. Không gian bí mật ban đầu vẫn là yếu tố quyết định.

| Dữ liệu | Vai trò | Cách xử lý |
| --- | --- | --- |
| Token hoặc phần bí mật gốc | Bằng chứng sở hữu quyền hạn chế | Bảo mật khi truyền, tránh lưu và ghi log không cần thiết |
| Selector | Định vị bản ghi token | Không được xem là bằng chứng biết bí mật |
| Digest hoặc MAC đã lưu | Kiểm chứng phần bí mật | Chỉ máy chủ dùng theo thuật toán và định dạng đã xác định |
| Account/request/purpose | Xác định phạm vi | Lấy từ trạng thái tin cậy và đối chiếu khi sử dụng |
| Thời hạn, trạng thái, phiên bản | Xác định điều kiện sử dụng | Kiểm tra lại tại thời điểm chấp nhận hoặc tiêu thụ |

## 3. Tách định vị bản ghi khỏi kiểm chứng bí mật

Một định dạng minh họa là:

```text
rt1.<selector>.<verifier>
```

Trong đó `rt1` là phiên bản định dạng, `selector` là định danh không tuần tự dùng để tìm bản ghi, còn `verifier` là biểu diễn của phần bí mật ngẫu nhiên. Đây là lựa chọn thiết kế minh họa, không phải định dạng chuẩn bắt buộc.

Máy chủ tra bản ghi bằng selector rồi so khớp giá trị kiểm chứng của verifier. Việc tìm thấy selector chưa đủ để chấp nhận token. Selector không nên chứa email, số điện thoại hoặc dữ liệu cá nhân có thể lộ qua URL.

Định dạng này giúp phân biệt hai công việc:

- Tra cứu bản ghi bằng dữ liệu định vị.
- Kiểm chứng bí mật bằng phép so sánh phù hợp.

Truy vấn cơ sở dữ liệu không mặc nhiên có thuộc tính thời gian như phép so sánh mật mã. Do đó, không nên kết luận toàn endpoint có thời gian xử lý an toàn chỉ vì nó dùng `WHERE token_hash = ?`. Cách tra cứu, phản hồi và giới hạn lưu lượng vẫn cần được thiết kế riêng.

Nếu chọn cách băm toàn bộ token để tra cứu thay vì selector, cần đánh giá đặc tính của thiết kế đó. Không có yêu cầu mọi hệ thống đều phải dùng selector, nhưng phải hiểu chỗ nào đang làm định vị và chỗ nào đang kiểm chứng quyền.

## 4. Định dạng đầu vào phải được xác định trước

### 4.1. Không tự chuẩn hóa một bí mật ngẫu nhiên

Đối với token máy sinh, các thao tác sau có thể tạo lỗi:

- Chuyển toàn bộ token sang chữ thường hoặc so sánh không phân biệt hoa thường.
- Cắt token đến độ dài mong muốn thay vì từ chối dữ liệu dư.
- Dùng `trim()` hoặc loại bỏ ký tự bên trong mà giao thức không cho phép.
- Chấp nhận khớp tiền tố, hậu tố hoặc một phần token.
- Diễn giải cùng một trường khi thì là số, khi thì là chuỗi.
- Giải mã URL lặp lại ở nhiều tầng mà không có quy tắc thống nhất.

Một mã ngắn được thiết kế để nhập tay có thể cho phép dấu phân nhóm hoặc khoảng trắng theo quy tắc công bố. Quy tắc đó phải áp dụng thống nhất từ đầu, không được tùy tiện dùng cho token Base64URL hoặc bí mật có phân biệt hoa thường.

Ví dụ, mã dạng chuỗi `004219` không nên bị ép thành số `4219`. Nếu độ dài sáu chữ số là một phần giao thức, việc ép kiểu đã làm mất thông tin.

### 4.2. Giải mã ra byte rồi dùng cùng một biểu diễn kiểm chứng

Nếu token được cấp dưới dạng Base64URL không padding, hãy xác định rõ bảng ký tự, độ dài và việc có chấp nhận biểu diễn thay thế hay không. Không coi việc decoder đọc được là đủ chứng minh đầu vào tuân theo định dạng hẹp của ứng dụng.

Java `Base64.Decoder` chấp nhận một số trường hợp có hoặc không có padding theo quy tắc của nó. Ứng dụng muốn một biểu diễn duy nhất có thể cần kiểm tra thêm ngoài việc gọi decoder. [Java SE 21 — Base64.Decoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.Decoder.html)

Với ví dụ 32 byte bí mật, biểu diễn Base64URL không padding dài 43 ký tự. Pipeline có thể giới hạn độ dài và bảng ký tự, giải mã thành 32 byte, rồi kiểm tra biểu diễn canonical bằng cách mã hóa lại và đối chiếu với chính chuỗi đầu vào.

Phép đối chiếu canonical này là so sánh đầu vào với một biểu diễn suy ra từ chính đầu vào, không phải so sánh với bí mật đã lưu của máy chủ. Không nhầm nó với phép kiểm chứng token.

Giới hạn kích thước cần áp dụng trước các bước tốn tài nguyên. Không giải mã một chuỗi rất lớn chỉ để sau đó phát hiện nó không thể là token hợp lệ.

## 5. Vì sao không dùng so sánh thông thường cho bí mật?

Một cách viết không phù hợp là:

```java
return storedToken.equals(candidateToken);
```

Hoặc:

```text
for each position:
    if expected[position] != candidate[position]:
        return false
return true
```

Vòng lặp thứ hai dừng ngay tại vị trí sai đầu tiên. Trong điều kiện có thể đo và khai thác, khác biệt xử lý có thể làm lộ thông tin về dữ liệu đang được so sánh. Với các hàm bằng nhau thông thường, ứng dụng không nên mặc định có cam kết phù hợp để so sánh bí mật.

Không dùng `==` để so sánh nội dung hai mảng Java vì nó so sánh tham chiếu. Cũng không thay bằng `startsWith`, `contains`, so sánh không phân biệt hoa thường hoặc “chấp nhận nếu phần lớn ký tự đúng”. Token là bằng chứng chính xác, không phải dữ liệu để tìm gần đúng.

OWASP khuyến nghị dùng hàm so sánh bí mật an toàn do nền tảng hoặc framework cung cấp; hướng dẫn cũng lưu ý giới hạn độ dài đầu vào, kiểu dữ liệu rõ ràng và tránh thời gian so sánh phụ thuộc dữ liệu bí mật. Nguyên tắc đó được vận dụng ở đây cho giá trị kiểm chứng token. [OWASP — Authentication Cheat Sheet: Compare Password Hashes Using Safe Functions](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#compare-password-hashes-using-safe-functions)

### Constant-time không có nghĩa toàn API mất đúng một khoảng thời gian

Mục tiêu của phép so sánh phù hợp là tránh để nội dung bí mật, chẳng hạn vị trí byte khác nhau, quyết định mức công việc của phép so sánh. Nó không làm cho truy vấn cơ sở dữ liệu, lập lịch luồng, GC, mạng và mọi nhánh nghiệp vụ có thời gian giống hệt nhau.

Đầu vào sai định dạng có thể được từ chối trước khi kiểm chứng bí mật vì các quy tắc định dạng đã công khai. Điều cần tránh là làm lộ tiền tố đúng hoặc thông tin bí mật thông qua cách kiểm chứng. Sau đó vẫn phải xem xét khả năng phân biệt tài khoản, bản ghi token và trạng thái thông qua phản hồi tổng thể.

## 6. So sánh digest độ dài cố định trong Java

`MessageDigest.isEqual` là API Java dành cho so sánh hai digest. Ghi chú triển khai của Java SE 21 mô tả việc xét các byte của đối số thứ nhất, với thời gian tính toán phụ thuộc vào độ dài đối số đó thay vì nội dung hai digest. Khi dùng cho thiết kế này, hai đầu vào nên là các mảng không null có độ dài cố định đã biết. [Java SE 21 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D))

Với SHA-256, ứng dụng giữ giá trị kiểm chứng dưới dạng 32 byte. Không đưa một bên là chuỗi hex 64 ký tự, bên còn lại là digest nhị phân 32 byte rồi mong chúng so khớp.

Ví dụ dưới đây minh họa hai việc hẹp: giải mã một verifier canonical và so khớp SHA-256 của phần bí mật 32 byte. Nó chưa thực hiện tra cứu, giới hạn lượt thử, kiểm tra phạm vi hoặc tiêu thụ token.

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.regex.Pattern;

public final class RecoveryTokenComparison {
    private static final int SECRET_BYTES = 32;
    private static final int DIGEST_BYTES = 32;
    private static final Pattern ENCODED_SECRET =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private RecoveryTokenComparison() {
    }

    public static byte[] decodeVerifier(String encoded) {
        if (encoded == null || !ENCODED_SECRET.matcher(encoded).matches()) {
            throw new IllegalArgumentException("Invalid token format");
        }

        byte[] decoded = Base64.getUrlDecoder().decode(encoded);
        if (decoded.length != SECRET_BYTES) {
            throw new IllegalArgumentException("Invalid token format");
        }

        String canonical = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(decoded);
        if (!canonical.equals(encoded)) {
            throw new IllegalArgumentException("Invalid token format");
        }

        return decoded;
    }

    public static boolean matchesSha256(
            byte[] candidateSecret,
            byte[] storedDigest
    ) throws NoSuchAlgorithmException {
        if (storedDigest == null || storedDigest.length != DIGEST_BYTES) {
            throw new IllegalArgumentException("Invalid verifier record");
        }
        if (candidateSecret == null || candidateSecret.length != SECRET_BYTES) {
            return false;
        }

        byte[] candidateDigest = MessageDigest.getInstance("SHA-256")
                .digest(candidateSecret);

        return MessageDigest.isEqual(storedDigest, candidateDigest);
    }
}
```

Trong ví dụ, `canonical.equals(encoded)` chỉ kiểm tra tính canonical từ chính đầu vào. Phép so sánh liên quan đến bí mật lưu ở máy chủ là `MessageDigest.isEqual(storedDigest, candidateDigest)`.

`storedDigest` phải được đọc từ bản ghi tin cậy của máy chủ. Không cho client cung cấp cả `candidateSecret` lẫn `storedDigest`, vì khi đó họ đang tự đưa ra giá trị kỳ vọng cho phép kiểm chứng của mình.

Ngoại lệ về bản ghi kiểm chứng hỏng cần được xử lý như lỗi nội bộ và không cấp quyền. Tầng HTTP không nên trả nguyên nội dung lỗi làm lộ cấu trúc lưu trữ. Lỗi khởi tạo thuật toán hoặc kho khóa cũng không được đổi thành kết quả so khớp thành công.

Không cần tự viết lại một vòng XOR rồi khẳng định nó an toàn trên mọi JVM, JIT hoặc nền tảng. Dùng API phù hợp và hiểu phạm vi cam kết của runtime đang triển khai.

## 7. Khi dùng MAC hoặc dạng lưu trữ khác

### 7.1. MAC có khóa

Một lựa chọn khác là:

```text
storedVerifier = HMAC(K, encode(context, secret))
```

Trong đó `K` được bảo vệ ngoài bản ghi token, còn `context` có thể gồm phiên bản giao thức, tenant, yêu cầu khôi phục, mục đích và selector. Các trường cần được đóng khung không nhập nhằng, chẳng hạn dùng cấu trúc mã hóa xác định hoặc tiền tố độ dài; không nối chuỗi tùy tiện.

Khi kiểm chứng, máy chủ dựng lại context từ dữ liệu tin cậy, tính MAC cho phần bí mật đã nhận và so sánh các giá trị MAC có cùng độ dài bằng cơ chế phù hợp. Không nhận context kỳ vọng hoàn toàn từ client rồi bỏ qua việc đối chiếu với bản ghi.

MAC có thể tăng bảo vệ khi chỉ cơ sở dữ liệu bị đọc mà khóa vẫn an toàn, đặc biệt khi bí mật có không gian nhỏ. Nó không làm mã ngắn có entropy cao hơn và không thay thế giới hạn đoán online. Nếu cả khóa lẫn dữ liệu bị lộ, giả định bảo vệ cũng thay đổi.

Phiên bản khóa phải do chính sách và bản ghi máy chủ xác định. Khi xoay khóa, không cho client chọn tùy ý thuật toán yếu hơn hoặc kích hoạt thử mọi khóa không giới hạn. Không tìm được khóa phù hợp là chưa kiểm chứng được token, không phải lý do cho qua.

### 7.2. Mã ngắn và giá trị do người dùng chọn

Với mã số ngắn, băm nhanh không đủ ngăn người có bản sao cơ sở dữ liệu thử toàn bộ không gian mã. Cần chọn chiến lược lưu trữ phù hợp với đe dọa, bảo vệ khóa khi dùng MAC, thời hạn và giới hạn thử ở phía máy chủ.

Nếu giá trị là một bí mật do người dùng chọn có đặc tính giống mật khẩu, sử dụng cơ chế hash và hàm verify dành cho trường hợp đó. Không tự thay bằng SHA-256 chỉ vì token ngẫu nhiên ở ví dụ trước dùng SHA-256.

Khi dùng hash có salt và tham số chi phí, gọi hàm verify đúng định dạng của thư viện. Không tính một hash với salt mới rồi so với bản đã lưu; không bỏ qua tham số chi phí hoặc chỉ so sánh một đoạn chuỗi kết quả.

### 7.3. Token tự chứa có chữ ký

Với JWT hoặc định dạng ký tương tự, bước kiểm chứng không phải chỉ giải mã payload hoặc so sánh toàn bộ chuỗi với một giá trị đã lưu. Cần dùng bộ xác minh đúng giao thức để kiểm chữ ký, thuật toán được phép và các claim liên quan như issuer, audience, mục đích, thời hạn và định danh token.

Sau đó vẫn phải xét trạng thái sử dụng một lần, thu hồi và phiên bản yêu cầu nếu luồng đòi hỏi. Một chữ ký hợp lệ không chứng minh token chưa từng được dùng.

## 8. Bản ghi không tồn tại và phản hồi tổng thể

Khi selector không tồn tại, máy chủ không có digest thực để so sánh. Một thiết kế có thể dùng digest giả có cùng kích thước và thực hiện phần công việc kiểm chứng tương tự trước khi từ chối. Tuy nhiên, nó phải có điều kiện riêng bảo đảm bản ghi không tồn tại không bao giờ được chấp nhận.

```text
recordUsable = record exists and verifierSchemaIsValid(record)
expected = recordUsable ? record.storedDigest : fixedSizeDummyDigest

matched = compareComputedDigest(candidateSecret, expected)

if not recordUsable or not matched:
    rejectWithoutGrantingRecovery()
```

Digest giả không phải fallback bí mật để tạo quyền cho một tài khoản mặc định. Không được dùng một cặp giá trị rỗng hoặc null rồi coi chúng bằng nhau là thành công.

Công việc giả chỉ xử lý một phần khác biệt. Thời gian truy vấn, cache, giới hạn lưu lượng và cách dựng phản hồi vẫn có thể khác nhau. Không tuyên bố toàn hệ thống chống suy luận thời gian chỉ từ đoạn mã trên.

Thông báo nên tránh phân biệt công khai “selector đúng nhưng bí mật sai”, “tài khoản không tồn tại” hoặc “bạn đoán đúng một phần token”. Giữ mã lý do chi tiết trong hồ sơ nội bộ được kiểm soát truy cập.

Chèn `sleep` hoặc jitter không thay thế phép so sánh an toàn. Nó có thể tạo chi phí tài nguyên và không bảo đảm che được khác biệt khi người tấn công có nhiều mẫu quan sát.

## 9. So khớp đúng chưa đủ điều kiện chấp nhận

Sau khi giá trị kiểm chứng khớp, hệ thống còn cần kiểm tra:

| Điều kiện | Ví dụ bị từ chối dù phần bí mật đúng |
| --- | --- |
| Đúng tenant và tài khoản | Token của tài khoản A gửi tới luồng của B |
| Đúng mục đích | Token đặt lại mật khẩu dùng để bỏ MFA |
| Đúng yêu cầu và phiên bản | Hồ sơ đã bị thay thế hoặc đổi phạm vi |
| Chưa hết hạn | Người dùng gửi lại liên kết cũ |
| Chưa thu hồi hoặc tiêu thụ | Token đã được dùng hoặc vô hiệu hóa |
| Cấu hình an toàn còn phù hợp | Tài khoản đã đổi security epoch theo chính sách |
| Đủ bằng chứng của tuyến khôi phục | Token chỉ chứng minh được một bước trong luồng nhiều bước |

Các điều kiện phải dựa trên thời gian và trạng thái tin cậy ở máy chủ. Không chấp nhận trường `isExpired=false`, `used=false` hoặc tài khoản đích từ client làm nguồn chuẩn.

Tương tự, phiên hạn chế được tạo từ một token không tự có quyền thay mọi cấu hình bảo mật. Quyền đặt lại mật khẩu, thêm passkey và vô hiệu hóa yếu tố MFA là các hành động khác nhau, cần được giới hạn theo quyết định đã phê duyệt.

## 10. Tiêu thụ nguyên tử để ngăn dùng lại

Hai yêu cầu có thể đồng thời đưa ra cùng một token đúng. Cả hai phép so sánh digest đều có thể trả về đúng; hàm so sánh không có trách nhiệm bảo đảm chỉ một yêu cầu thành công.

Một cách tổ chức luồng là:

```text
redeemRecoveryToken(serverContext, submittedToken, requestedAction):
    enforceRequestSizeAndTrafficLimits()
    parsed = parseAccordingToTokenVersion(submittedToken)
    record = lookupTokenInServerScope(serverContext, parsed.selector)

    matched = verifySecretOrPerformDummyComparison(record, parsed.secret)
    if not matched or record does not exist:
        return REJECTED

    return transaction:
        lockCurrentTokenAndRecoveryState(record.id)
        require verifierAndRecordVersionStillMatchCheckedSnapshot()
        require currentScopeAllows(serverContext, requestedAction)
        require requestStillOpenAndPolicyStillSatisfied()
        require tokenUnusedNotRevokedAndNotExpiredNow()

        markTokenConsumed()
        grant = createUniqueRestrictedGrantForApprovedAction()
        return grant
```

Đoạn mã giả tách phép kiểm chứng và phần chốt quyền, nên cần kiểm tra lại phiên bản bản ghi đã được so khớp. Một thiết kế khác có thể khóa và đọc dữ liệu hiện hành trước khi kiểm chứng. Cả hai đều phải tránh dùng kết quả từ snapshot cũ để tiêu thụ một bản ghi đã thay đổi.

Trong giao dịch, trạng thái token và việc tạo quyền hạn chế cần nhất quán: chỉ một yêu cầu được chuyển từ chưa dùng sang đã dùng và nhận quyền tương ứng. Nếu hệ thống thay đổi mật khẩu ngay trong thao tác đó, cần đặt việc tiêu thụ và thay đổi được bảo vệ trong cùng ranh giới nhất quán phù hợp.

Khi kết nối mất sau khi giao dịch đã commit, retry không được tạo thêm quyền mới. Nếu hỗ trợ idempotency, nó phải gắn với đúng yêu cầu, hành động và ngữ cảnh được phép; nếu không thể trả lại kết quả cũ an toàn, người dùng cần tiếp tục qua cách phục hồi giao dịch đã thiết kế.

Không tiêu thụ token chỉ bằng một lần tải trang `GET` từ liên kết. Việc xem trang và hành động thực sự đổi trạng thái nên được tách để hạn chế tác động từ bộ quét liên kết hoặc trình xem trước.

## 11. Giới hạn đoán và bảo vệ dữ liệu khi vận hành

So sánh không lộ tiền tố không ngăn được việc thử toàn bộ một không gian token nhỏ. Cần giới hạn các phép kiểm chứng được chấp nhận theo phạm vi phù hợp như yêu cầu, mục tiêu và nguồn truy cập. Việc xin token mới không được âm thầm xóa lịch sử lạm dụng theo chính sách.

Nếu kho lưu trạng thái hoặc kho khóa không khả dụng, chưa có cơ sở chấp nhận token. Không fallback sang so sánh thô với dữ liệu client, bỏ kiểm MAC hoặc tạo quyền khôi phục để tránh báo lỗi.

Tránh ghi token nguyên văn, giá trị kiểm chứng hoặc URL đầy đủ có token vào log, trace và thông tin lỗi. Các dữ liệu hữu ích cho vận hành thường là định danh bản ghi không bí mật, mục đích, phiên bản, kết quả theo nhóm và trạng thái tiêu thụ.

Không ghi lại “bao nhiêu byte đầu tiên đã khớp”. Thông tin đó không cần cho quyết định và có thể biến log thành kênh rò rỉ bí mật. Với cùng lý do, giao diện không nên gợi ý người dùng “gần đúng” một token ngẫu nhiên.

Kết quả kiểm chứng cần được dùng trong một luồng có bảo vệ truyền tải và kênh phân phối phù hợp. Nếu token bị đánh cắp nguyên vẹn, phép so sánh đúng sẽ vẫn thấy nó khớp. Khi đó, phạm vi, thời hạn, sử dụng một lần, điều kiện khôi phục và phát hiện rủi ro là các lớp bảo vệ tiếp theo.

## 12. Những tình huống cần phân biệt

| Tình huống | Kết quả và ý nghĩa |
| --- | --- |
| Verifier hợp lệ nhưng khác một byte bí mật | Digest không khớp; từ chối mà không tiết lộ vị trí sai |
| Chuỗi sai bảng ký tự hoặc độ dài | Từ chối định dạng theo giao thức trước khi thực hiện công việc không cần thiết |
| Đầu vào đổi hoa/thường của token phân biệt hoa thường | Không tự sửa để coi là cùng bí mật |
| Client gửi digest lấy từ bản ghi thay vì token gốc | Không chấp nhận digest đó trực tiếp như bằng chứng biết token |
| Selector đúng nhưng verifier sai | Không cấp quyền; selector chỉ định vị bản ghi |
| Bí mật đúng nhưng token hết hạn | So khớp đúng về nội dung, không đủ điều kiện sử dụng |
| Bí mật đúng nhưng mục đích khác | Từ chối hành động ngoài phạm vi |
| Hai node cùng nhận token đúng chưa dùng | Cả hai có thể so khớp đúng, nhưng chỉ một thao tác tiêu thụ được chấp nhận |
| Không đọc được digest hoặc khóa xác minh | Lỗi kiểm chứng; không chuyển thành thành công |
| Token ký có chữ ký đúng nhưng đã tiêu thụ | Không cấp quyền lần nữa chỉ vì chữ ký vẫn hợp lệ |

Giá trị của phép so sánh nằm ở việc xác minh chính xác bí mật mà không tạo thông tin phụ không cần thiết. Giá trị của toàn luồng khôi phục nằm ở việc chỉ dùng kết quả đó trong đúng tài khoản, đúng hành động và đúng thời điểm, với một thao tác tiêu thụ có kiểm soát.
