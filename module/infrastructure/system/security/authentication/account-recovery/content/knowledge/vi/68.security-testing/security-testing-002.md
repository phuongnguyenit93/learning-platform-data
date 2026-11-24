# Token guessing security test

## 1. Kiểm thử này cần chứng minh điều gì?

Trong khôi phục tài khoản, người gọi có thể chưa đăng nhập và đã mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Token khôi phục trở thành một phần bằng chứng để hệ thống quyết định có cho phép bước tiếp theo hay không. Nếu đoán được token hoặc vượt qua giới hạn thử, kẻ khác có thể giành quyền đăng ký yếu tố xác thực mới.

**Token guessing security test** kiểm tra khả năng chống đoán token tại bề mặt xác minh thực tế. Đối tượng kiểm tra gồm cách sinh token, tập giá trị có thể được chấp nhận, ngân sách thử, phản hồi có thể hỗ trợ việc đoán và tác động sau khi xác minh.

Một kết quả cần được diễn đạt cụ thể, chẳng hạn: “Ba token sai nhưng đúng định dạng đều bị từ chối; không xuất hiện recovery grant hoặc thay đổi credential; token đúng vẫn hoạt động trong ngân sách của fixture”. Câu “đã gửi nhiều request và không thấy thành công” không đủ chứng minh thiết kế an toàn.

OWASP khuyến nghị token reset được sinh bằng thuật toán ngẫu nhiên mật mã, có độ dài phù hợp, hết hạn và dùng một lần. Đây là cơ sở để đặt câu hỏi kiểm thử; các ngưỡng và fixture bên dưới là ví dụ thiết kế của bài học. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Trong khôi phục MFA hoặc passkey, xác minh token không mặc nhiên cho phép bỏ mọi yếu tố bảo vệ còn lại. Hệ thống có thể chỉ cấp một capability giới hạn cho bước xác minh tiếp theo. Khi mất passkey, luồng thường cho phép đăng ký credential mới theo chính sách; nó không khôi phục private key đã mất từ một mã OTP.

## 2. Xác định mô hình đe dọa trước khi chọn test

Cần mô tả người thử có thông tin gì và đang tấn công ranh giới nào. Một mã bí mật có thể mạnh trong mô hình này nhưng yếu trong mô hình khác.

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Kiến thức ban đầu | Người gọi biết email, recovery ID, tenant hay chỉ biết endpoint? |
| Bí mật cần đoán | Token ngẫu nhiên dài, OTP ngắn hay phần xác thực của token có chữ ký? |
| Phạm vi chấp nhận | Token chỉ hợp lệ cho một hồ sơ hay được tra cứu trên toàn bộ kho? |
| Số bí mật đang hợp lệ | Một token, nhiều token do gửi lại hay nhiều mã dự phòng? |
| Cửa sổ thử | Bao lâu token còn hiệu lực và ngân sách được khôi phục khi nào? |
| Bề mặt truy cập | Web, mobile, API cũ và các node có cùng quy tắc không? |
| Thành công thực sự | Được cấp capability nào, cho tài khoản nào và cho hành động gì? |

Bài học tập trung vào đoán trực tuyến qua verifier do hệ thống cung cấp. Tấn công ngoại tuyến sau khi lộ kho dữ liệu là mô hình khác: bộ đếm HTTP không hạn chế được số lần tính toán của người đang giữ dữ liệu đó.

Kiểm thử sử dụng tài khoản tổng hợp, kênh thông báo giả lập và endpoint của môi trường được giao. Fixture phải giới hạn số request, có thời hạn chạy và được dọn sau test. Không cần dò hết không gian token để phát hiện lỗi bộ đếm hoặc lỗi cấp quyền.

## 3. Định lượng khả năng đoán đúng

### 3.1. Không gian bí mật và số lần thử

Giả sử có đúng một token hợp lệ, được chọn đều từ không gian có `N` giá trị. Với `q` dự đoán khác nhau, xác suất trúng là:

```text
P = min(q / N, 1)
```

Nếu mỗi lần chọn độc lập và có thể lặp lại giá trị đã thử:

```text
P = 1 - (1 - 1/N)^q
```

Khi `q` nhỏ hơn rất nhiều so với `N`, biểu thức sau gần bằng `q/N`. Hai công thức sử dụng giả định khác nhau; không nên áp dụng chúng cho token có phân phối lệch hoặc có phần đã bị lộ.

Nếu verifier chấp nhận tối đa `m` token còn hiệu lực trong cùng phạm vi tìm kiếm, một chặn trên đơn giản là:

```text
P <= min(q * m / N, 1)
```

Phạm vi tìm kiếm rất quan trọng. Nếu token được kiểm tra trong một hồ sơ cụ thể, `m` là số token được chấp nhận của hồ sơ đó. Nếu endpoint nhận riêng token và tra trên toàn kho, phải xét toàn bộ tập token mà một dự đoán có thể khớp.

### 3.2. Độ dài biểu diễn không đồng nghĩa với entropy

| Ví dụ giả định phân phối đều | Số giá trị | Nhận xét |
|---|---:|---|
| OTP sáu chữ số, cho phép số 0 ở đầu | `10^6` | Khoảng 19,93 bit; cần kiểm soát thử trực tuyến chặt |
| OTP tám chữ số, cho phép số 0 ở đầu | `10^8` | Khoảng 26,58 bit; vẫn phải xét ngân sách thử |
| 16 byte ngẫu nhiên | `2^128` | Chuỗi hex dài 32 ký tự không làm tăng số bit |
| 32 byte ngẫu nhiên | `2^256` | Base64url không padding dài 43 ký tự |
| Timestamp, counter hoặc email được encode | Phụ thuộc dữ liệu gốc | Chuỗi có vẻ dài vẫn có thể dự đoán |

Base64url của 32 byte có 256 bit đầu vào, không phải 258 bit chỉ vì có 43 vị trí ký tự. Các bit đệm ở ký tự cuối làm tập biểu diễn hợp lệ nhỏ hơn tập mọi chuỗi 43 ký tự.

Ví dụ với OTP sáu chữ số và năm dự đoán khác nhau trong một lần cấp mã: `P = 5/1.000.000`. Đây không phải xác suất chiếm tài khoản của toàn hệ thống. Gửi lại mã nhiều lần, nhiều hồ sơ, nhiều tài khoản và nhiều cửa sổ ngân sách có thể làm tăng tổng số cơ hội.

OWASP WSTG nhấn mạnh rằng mã số ngắn cần được kiểm tra về khả năng chống thử tự động và việc khóa recovery có thể ảnh hưởng người dùng hợp lệ. Vì vậy, bài kiểm thử phải đánh giá cả giới hạn đoán và tác động gây từ chối dịch vụ. [OWASP WSTG: Weak Password Change or Reset Functionalities](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/04-Authentication/09-Weak_Password_Change_or_Reset_Functionalities/).

### 3.3. Những thứ phép tính không bao phủ

Các công thức trên không còn phản ánh đúng rủi ro nếu token bị lộ qua log, bị sinh từ seed đoán được hoặc verifier chỉ so khớp một tiền tố. Tương tự, một token có chữ ký cần được đánh giá theo cơ chế xác thực mật mã và quản lý khóa; không tính entropy bằng độ dài toàn bộ JSON payload.

Không có collision trong một mẫu nhỏ cũng không chứng minh nguồn sinh là ngẫu nhiên mật mã. Người kiểm tra phải xem thiết kế nguồn sinh, cấu hình thực tế và hành vi khi khởi động lại bên cạnh kết quả chạy test.

## 4. Viết chính sách có thể kiểm thử

Trước khi viết assertion, cần thống nhất các cam kết quan sát được. Ví dụ sau dùng hai profile độc lập:

| Thuộc tính | Profile A: link ngẫu nhiên | Profile B: mã nhập tay |
|---|---|---|
| Bí mật minh họa | 32 byte ngẫu nhiên | Sáu chữ số ngẫu nhiên |
| Binding | Tenant, hồ sơ, tài khoản, mục đích | Tenant, hồ sơ, tài khoản, mục đích |
| Hạn dùng minh họa | 10 phút | 5 phút |
| Kiểm soát lưu lượng | Theo nguồn gọi và phạm vi nghiệp vụ | Theo nguồn gọi, hồ sơ và ngân sách tích lũy phù hợp |
| Kết quả xác minh | Capability cho bước được phép | Capability cho bước được phép |
| Giới hạn test | Một tập nhỏ token sai | Ngân sách verifier nhỏ, kiểm tra đúng biên |

Các con số là dữ liệu của ví dụ, không phải ngưỡng bắt buộc cho mọi sản phẩm. Cửa sổ gửi thông báo, thời gian người dùng nhận mã, mức rủi ro và khả năng khôi phục thay thế đều ảnh hưởng chính sách thực.

Đối với test ngân sách ở phần Java, đặt quy tắc riêng: **verifier được đánh giá tối đa năm candidate trong một cửa sổ của fixture**. Năm candidate đầu đều sai thì candidate thứ sáu bị chặn trước bước so khớp, kể cả khi nó đúng. Đây là quy tắc admission cụ thể; nó khác một chính sách chỉ tăng bộ đếm sau khi xác minh thất bại.

Không áp dụng máy móc ngân sách nhỏ của OTP cho mọi link dài. Nếu bất kỳ người lạ nào có thể nhập recovery ID công khai rồi làm vô hiệu khả năng khôi phục của nạn nhân chỉ bằng vài request, hệ thống đã tạo ra đường gây từ chối dịch vụ. Test phải mô tả phạm vi bị hạn chế, thời gian phục hồi và các đường khôi phục khác.

Việc gửi yêu cầu khôi phục chưa xác minh không được tự thay mật khẩu, xóa MFA hoặc thu hồi toàn bộ session. Những thay đổi có tác động như vậy cần điều kiện nghiệp vụ riêng, không phải một hệ quả ngầm của rate limit.

## 5. Chuẩn bị fixture và bằng chứng đáng tin cậy

Fixture nên tạo hai tài khoản tổng hợp trong hai tenant, một hồ sơ khôi phục đang hoạt động và token hợp lệ dành cho hồ sơ đó. Nếu test không cần nhiều token cùng tồn tại, giữ đúng một token để diễn giải kết quả rõ ràng.

Những điều kiện cần kiểm tra trước khi gửi request:

1. Token đúng còn hạn và chưa sử dụng.
2. Mục đích của token trùng hành động đang kiểm thử.
3. Các bộ đếm liên quan có trạng thái ban đầu xác định.
4. Request đi qua parser, xác thực ngữ cảnh và verifier thật.
5. Kênh email/SMS được thay bằng bộ thu nhận của môi trường test.
6. Có thể quan sát recovery grant và phiên bản credential từ nguồn có thẩm quyền.

Mock chỉ trả `REJECTED` cho mọi candidate sẽ khiến test đoán token luôn xanh. Dùng fake cho dịch vụ chuyển phát có thể hợp lý; thay verifier hoặc kho ngân sách bằng mock thì không kiểm tra được đúng ranh giới đang quan tâm.

### Snapshot nên bao gồm gì?

Một snapshot phục vụ kiểm thử có thể chứa:

- Số grant khôi phục đã được cấp cho tài khoản tổng hợp.
- Phiên bản credential mật khẩu.
- Phiên bản tập MFA và tập passkey.
- Phiên bản registry session hoặc dấu mốc thu hồi session có thẩm quyền.

Không đưa token, mật khẩu, private key hoặc session bearer vào snapshot. Sự kiện audit và bộ đếm thử sai được phép tăng theo chính sách, nên không so sánh toàn bộ DB theo kiểu “không một dòng nào được thay đổi”.

Nếu snapshot dựa trên cache trễ, một lỗi cấp quyền có thể chưa xuất hiện khi test đọc. Hãy đọc nguồn ghi chính hoặc đợi điều kiện đồng bộ đã định với timeout hữu hạn. Việc không thấy log thành công không thay thế được kiểm tra grant và credential.

## 6. Xây bộ candidate sai nhưng có ý nghĩa

Tập candidate phải kiểm tra nhiều ranh giới, thay vì chỉ gửi chuỗi ngẫu nhiên quá ngắn và dừng ở parser.

| Nhóm candidate | Cách chuẩn bị trong fixture | Mục đích |
|---|---|---|
| Đúng định dạng, sai toàn bộ giá trị | Token tổng hợp cùng độ dài và alphabet | Đi vào verifier thực |
| Khác đúng một phần token | Đổi một byte rồi encode lại hợp lệ | Phát hiện so tiền tố hoặc cắt ngắn |
| Đúng token, sai recovery ID | Hai hồ sơ tổng hợp có binding khác nhau | Kiểm tra phạm vi chấp nhận |
| Đúng token, sai tenant hoặc mục đích | Fixture có đủ ngữ cảnh tương ứng | Kiểm tra binding |
| Token đã hết hạn hoặc bị thay thế | Điều khiển clock và trạng thái issuance | Chặn bí mật không còn hợp lệ |
| Rỗng, quá dài, ký tự không hợp lệ | Bộ dữ liệu có giới hạn kích thước | Kiểm tra parser và chi phí xử lý |
| Biểu diễn thay thế của cùng dữ liệu | Theo policy encoding đã công bố | Kiểm tra chuẩn hóa và bộ đếm |

Với token ngẫu nhiên encode từ byte, sửa byte rồi encode lại thường giúp tạo candidate hợp lệ về cấu trúc. Sửa tùy ý ký tự cuối của Base64url có thể tạo dạng không canonical và chỉ kiểm tra parser.

Fixture phải bảo đảm candidate sai không trùng bất kỳ token đang hợp lệ nào trong phạm vi verifier. Không đưa toàn bộ candidate vào assertion message; khi test thất bại, tên case hoặc số thứ tự đã đủ để tìm dữ liệu trong bộ dựng fixture được kiểm soát.

Một token của tài khoản khác có thể hợp lệ khi được dùng trong chính ngữ cảnh của nó. Test cần giữ recovery ID hoặc tenant đích cố định rồi thay token, để chứng minh không thể dùng token nguồn cho hồ sơ đích. Trộn cả token và ngữ cảnh sang hồ sơ nguồn sẽ tạo một positive control, không phải kiểm tra binding thất bại.

## 7. Phân biệt từ chối HTTP với từ chối quyền

Một endpoint có thể trả `200` để hiển thị form, `202` để xác nhận xử lý chung hoặc `400` cho lỗi định dạng. Không thể suy ra xác minh thành công chỉ từ nhóm mã HTTP.

Điều cần kiểm tra là quyết định nghiệp vụ và tác động:

```text
Candidate sai
  -> không có recovery grant hợp lệ cho hành động đích
  -> không có thay đổi credential hoặc yếu tố xác thực
  -> không có session mới có quyền truy cập tài khoản
  -> có ghi nhận thử sai theo policy
```

Nếu API trả một cookie phiên tạm cho màn hình recovery, hãy kiểm tra phạm vi và khả năng sử dụng cookie đó. Cookie phục vụ chống CSRF hoặc duy trì form không được bị nhầm với session đã xác thực hay grant được phép đổi mật khẩu.

Đối với luồng nhiều bước, xác minh token có thể chỉ cấp quyền xem bước tiếp theo. Test cần thử capability tại đúng thao tác nhạy cảm để bảo đảm không có quyền vượt phạm vi. Không cần thực hiện thay đổi credential trong mọi case thử sai; kiểm tra grant và trạng thái bảo mật thường đã đủ.

### Kiểm tra oracle phản hồi

Với các candidate sai đã được parser chấp nhận, quan sát mã kết quả, cấu trúc body, cookie, redirect và sự khác biệt thời gian có thể lặp lại. Phản hồi không nên tiết lộ “đúng ba ký tự đầu” hoặc “token tồn tại nhưng thuộc tài khoản khác” trên bề mặt chưa có quyền biết thông tin đó.

Lỗi định dạng và rate limit có thể có phản hồi riêng nếu hợp đồng cho phép. Không ép mọi request phải có cùng HTTP status. Mục tiêu là tránh phản hồi giúp suy ra bí mật hoặc thông tin tài khoản ngoài quyền của người gọi.

Kiểm thử timing không nên dùng một assertion đơn lẻ như `elapsed < 20 ms`. Nhiễu mạng, warm-up JVM, cache và tải đồng thời có thể lấn át tín hiệu. Đo lặp có kiểm soát, đổi thứ tự mẫu và phân tích phân phối trong một phép kiểm tra chuyên biệt; kết quả âm tính vẫn không chứng minh tuyệt đối không có side channel.

## 8. Ví dụ Java: sinh token có không gian rõ ràng

Đây là ví dụ nguồn sinh cho link ngẫu nhiên. Nó không phải một triển khai đầy đủ của recovery service.

```java
import java.security.SecureRandom;
import java.util.Base64;

final class RecoveryTokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    String newToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
```

Kiểm tra thiết kế cần xác nhận mã production thật sử dụng nguồn này hoặc một nguồn tương đương phù hợp, không chỉ có một class đúng nhưng không được gọi. Tránh seed cố định từ thời gian, account ID hoặc dữ liệu dự đoán được.

Base64url là encoding. Nó không thêm tính bí mật, không thay thế CSPRNG và không tự thực hiện binding. Kho token, thời hạn, thao tác tiêu thụ và quyền được cấp vẫn cần thiết kế riêng.

Một test tạo vài trăm token rồi kiểm tra không trùng chỉ có thể phát hiện một số lỗi thô như trả hằng số. Nó không đánh giá đầy đủ tính không thể dự đoán. Kiểm tra cấu hình sau restart hoặc trong image triển khai cũng cần tập trung vào nguồn sinh thực tế, không suy luận từ vẻ ngoài của chuỗi.

Với OTP, độ dài cố định và cách lấy số cần được xem xét riêng. Chuyển chuỗi số qua kiểu số nguyên có thể làm mất số 0 ở đầu; lấy phần dư từ một nguồn không phù hợp có thể gây lệch phân phối. Những vấn đề này thuộc nguồn sinh và parser, không thể được bù bằng một assertion HTTP đơn lẻ.

## 9. Ví dụ Java: token sai không tạo quyền

Đoạn dưới là một lớp test JUnit trừu tượng. Dự án cần triển khai adapter `Harness` để gọi HTTP hoặc application boundary thật và đọc bằng chứng có thẩm quyền. Ví dụ không cung cấp endpoint production hoặc chương trình dò token hàng loạt.

```java
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

abstract class RecoveryGuessingSecurityTest {

    protected abstract Harness isolatedFixture(int verificationBudget);

    @Test
    void invalidCandidatesDoNotGrantRecoveryAuthority() {
        try (Harness fx = isolatedFixture(8)) {
            SecuritySnapshot before = fx.snapshot();
            List<String> wrong = fx.validFormatWrongCandidates(3);

            assertEquals(3, wrong.size());

            for (int i = 0; i < wrong.size(); i++) {
                AttemptOutcome outcome = fx.verify(wrong.get(i));

                assertEquals(Decision.REJECTED, outcome.decision(),
                        "Wrong candidate must be rejected");
                assertTrue(outcome.verifierReached(),
                        "Case must reach the real verifier");
                assertEquals(before, fx.snapshot(),
                        "Wrong candidate changed security state");
            }

            // Positive control: three failures remain below budget eight.
            AttemptOutcome valid = fx.verify(fx.validToken());
            assertEquals(Decision.GRANT_ISSUED, valid.decision());
            assertTrue(valid.verifierReached());

            SecuritySnapshot after = fx.snapshot();
            assertEquals(before.recoveryGrantCount() + 1,
                    after.recoveryGrantCount());
            assertEquals(before.passwordVersion(), after.passwordVersion());
            assertEquals(before.mfaVersion(), after.mfaVersion());
            assertEquals(before.passkeyVersion(), after.passkeyVersion());
            assertEquals(before.sessionRegistryVersion(),
                    after.sessionRegistryVersion());
        }
    }

    @Test
    void exhaustedBudgetStopsEvenACorrectCandidate() {
        try (Harness fx = isolatedFixture(5)) {
            SecuritySnapshot before = fx.snapshot();
            List<String> wrong = fx.validFormatWrongCandidates(5);

            assertEquals(5, wrong.size());

            for (String candidate : wrong) {
                AttemptOutcome outcome = fx.verify(candidate);
                assertEquals(Decision.REJECTED, outcome.decision());
                assertTrue(outcome.verifierReached());
            }

            assertEquals(5L, fx.verifierInvocationCount());

            AttemptOutcome overBudget = fx.verify(fx.validToken());
            assertEquals(Decision.THROTTLED, overBudget.decision());
            assertFalse(overBudget.verifierReached());
            assertEquals(5L, fx.verifierInvocationCount());
            assertEquals(before, fx.snapshot());
        }
    }

    enum Decision {
        REJECTED,
        THROTTLED,
        GRANT_ISSUED
    }

    record AttemptOutcome(
            Decision decision,
            boolean verifierReached) {}

    record SecuritySnapshot(
            long recoveryGrantCount,
            long passwordVersion,
            long mfaVersion,
            long passkeyVersion,
            long sessionRegistryVersion) {}

    interface Harness extends AutoCloseable {
        List<String> validFormatWrongCandidates(int count);
        String validToken();
        AttemptOutcome verify(String candidate);
        SecuritySnapshot snapshot();
        long verifierInvocationCount();

        @Override
        void close();
    }
}
```

### Điều kiện để test có giá trị

- `isolatedFixture(...)` tạo namespace và dữ liệu riêng; cấu hình ngân sách test không đi vào endpoint quản trị công khai.
- Tất cả candidate sai đều có cấu trúc hợp lệ và được xác nhận không phải token hợp lệ của fixture.
- `verify(...)` đi qua admission control, verifier và cơ chế cấp grant thật.
- `verifierReached` và `verifierInvocationCount` lấy từ instrumentation của môi trường test gắn với request; không suy ra từ HTTP status.
- Snapshot đọc dữ liệu có thẩm quyền sau khi tác động của request đã hoàn tất.
- `validToken()` chỉ được dùng trong bộ nhớ test và không xuất hiện trong message, URL log hoặc output CI.
- `close()` dọn dữ liệu và đợi các tác vụ liên quan của fixture kết thúc theo thiết kế môi trường.

Positive control ngăn một lỗi cấu hình phổ biến: verifier hỏng hoàn toàn hoặc endpoint không truy cập được nhưng mọi candidate sai vẫn được tính là “bị chặn an toàn”. Adapter phải phân biệt lỗi hạ tầng với quyết định `REJECTED`, không chuyển mọi exception thành kết quả từ chối.

Ví dụ kỳ vọng token đúng chỉ cấp grant, chưa đổi credential hoặc session. Nếu hợp đồng sản phẩm cấp một phiên recovery giới hạn hoặc thực hiện tác động khác, phải sửa snapshot và assertion theo hợp đồng đó, đồng thời xác minh phạm vi quyền.

Test thứ hai chỉ phù hợp với policy “tối đa năm lần đi vào verifier”. Nó không mô tả tất cả thiết kế rate limit. Một implementation đếm thất bại ở thời điểm khác cần case biên tương ứng, có giải thích rõ candidate nào vẫn được đánh giá.

## 10. Kiểm tra bộ đếm không bị chia nhỏ ngoài ý muốn

Một bộ đếm theo IP có thể hạn chế nguồn gửi đơn lẻ nhưng không giới hạn tổng số dự đoán vào cùng OTP khi nguồn gửi thay đổi. Ngược lại, bộ đếm chỉ theo account ID công khai có thể bị sử dụng để gây gián đoạn recovery cho người khác.

Test cần theo policy đã chọn, bao gồm nhiều chiều và chi phí xử lý trước khi xác định được tài khoản.

| Thay đổi giữa hai request | Điều cần xác minh |
|---|---|
| Đổi cookie hoặc user-agent | Không được tạo ngân sách mới nếu policy ràng buộc cùng hồ sơ |
| Đổi node xử lý | Ngân sách chung vẫn được thực thi |
| Đổi endpoint web sang mobile | Không có verifier yếu hơn hoặc bộ đếm độc lập trái thiết kế |
| Đổi cách biểu diễn identifier | Việc chuẩn hóa theo contract không tách cùng đối tượng thành nhiều ngân sách |
| Gửi lại mã hoặc mở hồ sơ mới | Không tạo vô hạn lượt thử đối với cùng mục tiêu |
| Đổi tenant | Không sử dụng nhầm token hoặc dữ liệu bộ đếm của tenant khác |
| Gửi idempotency key lặp lại | Không bỏ qua xác minh cho một payload mới |
| Gửi dữ liệu không parse được | Có giới hạn chi phí và lưu lượng thích hợp trước verifier |

Không nhất thiết mọi request lỗi đều tiêu tốn một slot OTP. Ví dụ, payload vượt giới hạn có thể bị proxy từ chối trước khi xác định được hồ sơ. Tuy nhiên, những nhánh này vẫn cần kiểm soát tài nguyên để tránh trở thành đường gây tải không giới hạn.

Canonicalization phải dựa trên quy tắc identifier của hệ thống. Không tự coi mọi email viết khác dấu chấm, dấu cộng hoặc chữ hoa là một người dùng nếu sản phẩm không có quy tắc tương ứng.

Header `X-Forwarded-For` chỉ có giá trị khi được xử lý theo chuỗi proxy tin cậy. Một test nên chứng minh client không thể tự khai nguồn mới qua header rồi nhận ngân sách mới. Dùng cấu hình proxy của môi trường thử, không giả định mọi header đều đã được hạ tầng xác thực.

### Gửi lại token không được che mất tổng ngân sách

Một case hữu ích với mã ngắn:

1. Cấp mã cho hồ sơ tổng hợp.
2. Dùng một phần ngân sách bằng candidate sai.
3. Thực hiện gửi lại theo đúng điều kiện được phép.
4. Kiểm tra trạng thái mã cũ theo policy thay thế hoặc cùng tồn tại.
5. Kiểm tra ngân sách tích lũy và giới hạn issuance vẫn còn tác dụng.

Không áp đặt mọi sản phẩm phải giữ nguyên bộ đếm của từng mã. Điều cần chứng minh là cơ chế gửi lại không làm mô hình rủi ro giả định năm lần thử biến thành số lần thử không bị chặn.

## 11. Kiểm tra cạnh tranh và nhiều node

Lỗi thường gặp là hai request cùng đọc `remaining = 1`, cùng được đưa vào verifier rồi mới cập nhật bộ đếm. Kết quả là giới hạn đúng khi chạy tuần tự nhưng sai khi có cạnh tranh.

Một thử nghiệm nhỏ có thể sử dụng ngân sách năm slot, tám candidate sai và hai node:

```text
Chuẩn bị:
  - Một hồ sơ, một ngân sách chung, dữ liệu hoàn toàn tổng hợp.
  - Tám candidate sai nhưng hợp lệ về định dạng.
  - Hai adapter gửi vào hai node dùng chung kho giới hạn.

Thực thi:
  - Đồng bộ điểm bắt đầu của tám request trong môi trường test.
  - Đợi tất cả request kết thúc với timeout hữu hạn.

Quan sát:
  - Số lần verifier thực sự được vào không vượt quá năm.
  - Không có grant hoặc thay đổi credential.
  - Kết quả và audit có thể đối chiếu với từng request.
  - Request tiếp theo vẫn bị chặn trong cửa sổ hiện hành.
```

Chỉ đếm số phản hồi `429` có thể bỏ sót lỗi. Một implementation có thể đã chạy verifier, tạo quyền rồi mới trả phản hồi rate limit do xử lý sai thứ tự.

Để bảo vệ chính sách admission trong ví dụ, việc giữ slot phải diễn ra nguyên tử trước khi đánh giá candidate. Cơ chế cụ thể có thể là cập nhật có điều kiện trong DB hoặc thao tác nguyên tử của kho giới hạn. Test cần sử dụng cơ chế thật của implementation.

Không gộp assertion ngân sách với assertion “token chỉ được tiêu thụ một lần”. Hai request cùng mang token đúng kiểm tra tiêu thụ nguyên tử; nhiều request mang token sai kiểm tra admission budget. Cả hai đều quan trọng nhưng có điều kiện thất bại khác nhau.

### Khi kho giới hạn lỗi

Với OTP ngắn đang dựa vào giới hạn trực tuyến, lỗi kho ngân sách không được tự biến thành khả năng xác minh không hạn chế. Chính sách có thể từ chối tạm, trì hoãn hoặc sử dụng phương án suy giảm đã được đánh giá.

Test cần mô phỏng timeout, mất kết nối và khôi phục kho trong phạm vi fixture, rồi xác minh không cấp quyền ngoài chính sách. Không chỉ kiểm tra service “vẫn trả được HTTP”. Một fallback theo bộ đếm RAM từng node phải được đánh giá theo tổng ngân sách thực tế mà nó tạo ra.

## 12. Hạn dùng, retry và thời điểm phục hồi ngân sách

Giới hạn thử chỉ có ý nghĩa khi cửa sổ thời gian được định nghĩa rõ. Dùng clock điều khiển được hoặc cơ chế thời gian kiểm thử của hệ thống để tránh sleep dài và test thất thường.

Các case cần tách riêng:

| Case | Kỳ vọng cần ghi trong contract |
|---|---|
| Candidate đúng ngay trước hạn | Được xử lý theo quy tắc kiểm tra thời điểm đã định |
| Candidate đúng đúng mốc hết hạn | Ví dụ `now >= expiresAt` bị từ chối |
| Ngân sách phục hồi nhưng token hết hạn | Token không trở lại hợp lệ |
| Token còn hạn nhưng ngân sách cạn | Áp dụng chính sách chặn đã chọn |
| Response bị mất sau khi server giữ slot | Retry không tạo quyền vượt ngân sách |
| Gửi lại request với cùng idempotency key | Ràng buộc key với nội dung và phạm vi theo thiết kế |
| Node lệch thời gian trong biên được hỗ trợ | Không tạo cửa sổ chấp nhận ngoài policy |

Không cần mọi hệ thống hoàn trả slot cho request thất bại vì hạ tầng. Việc hoàn trả phải được thiết kế cẩn thận để không mở ra số lượt xác minh vô hạn qua lỗi lặp lại. Test cần quan sát slot đã được giữ, verifier đã chạy chưa và kết quả cuối cùng có được ghi nhận nguyên tử hay không.

Nếu dùng idempotency, cùng một key với candidate khác không được lấy lại kết quả “đã xác minh” của request trước. Phạm vi key, fingerprint payload và thời hạn lưu kết quả đều thuộc contract cần kiểm tra.

Hạn dùng của token, thời hạn grant sau xác minh và cửa sổ rate limit là ba khái niệm riêng. Một grant cũ không được kéo dài chỉ vì người gọi bắt đầu một cửa sổ thử mới.

## 13. Chuẩn hóa và lỗi so khớp làm giảm không gian bí mật

Verifier có thể vô tình chấp nhận nhiều giá trị hơn issuer dự định. Những lỗi này làm tăng khả năng đoán trúng dù nguồn sinh ban đầu đủ mạnh.

Ví dụ cần xem xét:

- Chỉ so một số ký tự đầu của token.
- Cắt token theo giới hạn cột hoặc buffer rồi mới so.
- Chuyển token phân biệt hoa thường thành chữ thường.
- Xử lý ký tự null như điểm kết thúc ngoài ý muốn.
- Parse OTP thành số làm mất độ dài và quy tắc số 0 ở đầu.
- Chấp nhận một token mặc định khi trường token rỗng.
- Bỏ qua kiểm tra chữ ký hoặc mục đích ở một nhánh lỗi.
- Tách cache key và verifier theo hai cách chuẩn hóa khác nhau.

Một chiến lược test hiệu quả là giữ token đúng trong fixture, thay đổi một thành phần có ý nghĩa rồi quan sát rằng candidate đó không được xác minh. Cần biết phép thay đổi có tạo dữ liệu khác thực sự sau decode hay không.

Một số decoder cho phép nhiều biểu diễn của cùng byte. Nếu sản phẩm chủ động hỗ trợ điều đó, không nhất thiết mọi biểu diễn thay thế đều phải bị từ chối. Khi ấy, cùng bí mật không được nhận thêm ngân sách hoặc vượt quy tắc dùng một lần do biểu diễn khác nhau.

Không cần ép thông báo công khai nói chính xác “sai chữ ký”, “sai tenant” hoặc “hết hạn”. Những phân loại đó có thể ở telemetry nội bộ, trong khi phản hồi công khai chỉ cung cấp mức chi tiết phù hợp với quyền hiện tại.

## 14. Observability hỗ trợ test mà không làm lộ token

Một bản ghi kiểm thử hữu ích có thể chứa `runId`, tên scenario, định danh hồ sơ tổng hợp, node xử lý, loại quyết định, số slot đã dùng và mã lý do nội bộ đã được kiểm soát truy cập.

Tránh lưu candidate, token đúng, URL có token, mã OTP, địa chỉ nhận thật hoặc toàn bộ body lỗi. Đặc biệt chú ý access log của proxy, log debug của HTTP client và hệ thống đính kèm request khi test thất bại.

Nếu cần liên kết các lần dùng cùng token, không mặc định một hash công khai của OTP ngắn là an toàn: người có log có thể thử toàn bộ không gian OTP ngoại tuyến. Có thể dùng định danh bản ghi hoặc cơ chế liên kết có khóa phù hợp, tùy mô hình đe dọa và quản lý khóa của hệ thống.

Thiết kế telemetry không nên tạo một endpoint công khai để hỏi “verifier có được chạy không?”. Instrumentation phục vụ assertion cần nằm trong môi trường test hoặc công cụ nội bộ có quyền kiểm soát.

Một assertion tốt cho case đoán sai có thể báo:

```text
scenario=wrong-valid-format
requestIndex=2
expectedDecision=REJECTED
actualDecision=GRANT_ISSUED
credentialChanged=false
recoveryGrantDelta=1
```

Thông tin này đã đủ chỉ ra lỗi cấp quyền. Không cần in candidate gây lỗi vào output CI.

## 15. Diễn giải kết quả và giới hạn của bằng chứng

| Quan sát | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Ba candidate sai bị từ chối, positive control thành công | Fixture kiểm tra đúng verifier và các case này không tạo quyền | Mọi token tương lai đều không dự đoán được |
| Ngân sách năm slot giữ được khi gửi tám request qua hai node | Cấu hình và đường đi đã thử giữ được giới hạn trong thử nghiệm | Mọi topology và tình huống failover đều đúng |
| Token đúng hết hạn bị từ chối | Case thời gian và trạng thái đã chuẩn bị hoạt động đúng | Không có endpoint khác bỏ qua hạn dùng |
| Không thấy dữ liệu nhạy cảm trong output test | Các bề mặt log đã quan sát không lộ dữ liệu trong lần chạy | Tất cả log, trace và hệ thống bên thứ ba đều sạch |
| Nguồn sinh dùng CSPRNG với không gian rõ ràng | Thiết kế nguồn sinh có cơ sở mật mã phù hợp | Token không bị rò rỉ hoặc cấp sai quyền |

Phân biệt kết quả thiết kế và kết quả chạy. Có source code minh họa trong tài liệu không có nghĩa test đã được triển khai hoặc thực thi trong module.

Một báo cáo thực thi nên ghi phiên bản build, profile policy, endpoint hoặc nhóm node thử nghiệm, số request thực gửi, số lần verifier chạy, snapshot trước/sau và các case chưa thực hiện. Nếu không đọc được nguồn grant có thẩm quyền thì ghi thiếu bằng chứng, không suy ra “không có tác động” từ việc HTTP trả lỗi.

Khi phát hiện lỗi, mô tả chuỗi nguyên nhân cụ thể. Ví dụ: “Bộ đếm lưu theo node, tám request được đưa vào verifier dù ngân sách hồ sơ là năm”. Cách mô tả này dẫn trực tiếp đến kiểm tra kho chung và thao tác admission nguyên tử.

## 16. Tình huống thực hành: OTP recovery cho MFA bị chia ngân sách

Một dịch vụ cho phép người mất thiết bị MFA nhận OTP qua kênh khôi phục đã đăng ký. Mỗi node có bộ đếm RAM cho phép năm lần xác minh. Khi chỉ kiểm tra tuần tự trên một node, test luôn đạt.

Môi trường triển khai có hai node. Cùng một recovery ID được gửi qua cả hai node và mỗi nơi cấp năm lượt riêng. Tổng ngân sách thực tế đã vượt giả định của thiết kế dù từng node đều báo “đã giới hạn”.

Một kế hoạch sửa và kiểm chứng có thể gồm:

1. Xác định khóa ngân sách theo tenant và hồ sơ, cùng giới hạn tích lũy cần thiết cho issuance.
2. Đặt admission vào kho dùng chung với thao tác nguyên tử.
3. Kiểm tra đổi cookie, endpoint và node không tạo thêm ngân sách cho cùng phạm vi.
4. Kiểm tra kho giới hạn bị lỗi không dẫn tới xác minh OTP không hạn chế.
5. Kiểm tra token đúng trong ngân sách chỉ cấp capability recovery đã định.
6. Kiểm tra capability đó không cho phép xóa MFA, đăng ký passkey hoặc cấp session vượt bước đã xác minh.
7. Kiểm tra cơ chế hạn chế không khóa đăng nhập bình thường hoặc gây đình trệ recovery vô thời hạn.

Case này không cần thử hết một triệu OTP. Tám candidate sai được kiểm soát đã đủ tái hiện việc vượt ngân sách năm slot. Phép tính xác suất sau đó phải sử dụng ngân sách và số lần issuance thực tế, thay vì con số cấu hình trên một node.

Sau khi sửa, giữ lại cả positive control và negative control. Một hệ thống từ chối mọi người dùng có thể chặn được thử đoán nhưng không đáp ứng mục tiêu khôi phục tài khoản an toàn và sử dụng được.
