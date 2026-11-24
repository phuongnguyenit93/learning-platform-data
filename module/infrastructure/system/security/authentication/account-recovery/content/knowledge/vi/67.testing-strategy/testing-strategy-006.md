# Recovery regression suite — Bộ kiểm thử hồi quy cho khôi phục tài khoản

## 1. Mục tiêu của bộ hồi quy

Một bản sửa giao diện thông báo có thể vô tình làm lộ tài khoản tồn tại. Một lần tối ưu truy vấn có thể bỏ mất điều kiện token chưa được sử dụng. Một thay đổi trong cổng hỗ trợ có thể cho phép nhân viên đặt lại MFA khi hồ sơ mới chỉ được mở. Các lỗi này thường không xuất hiện trong kịch bản “nhận email, bấm liên kết, đặt mật khẩu mới”.

Recovery regression suite là bộ kiểm thử được chạy lặp lại để phát hiện việc một hành vi từng an toàn bị thay đổi ngoài ý muốn. Trong phạm vi SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, suite phải theo dõi cả khôi phục mật khẩu, mất MFA, mất passkey, mất thiết bị xác thực và những tác động tiếp theo lên session. Mục tiêu là giữ khả năng lấy lại quyền truy cập cho chủ tài khoản đồng thời ngăn người khác dùng đường khôi phục để chiếm tài khoản.

Bài học tập trung vào cách thiết kế, tổ chức và duy trì suite. Những ví dụ dưới đây là thiết kế tham khảo cho một hệ thống giả định; endpoint, thời hạn, mã trạng thái và tên bảng phải được điều chỉnh theo hợp đồng thực tế của sản phẩm.

Sau bài học, người học cần làm được:

- Chuyển chính sách recovery thành các bất biến có thể kiểm tra.
- Xây dựng danh mục test theo rủi ro thay vì chỉ theo màn hình.
- Kiểm tra đồng thời kết quả API, dữ liệu bền vững, quyền truy cập và side effect.
- Tái hiện lỗi thời gian, replay, cạnh tranh và lỗi phụ thuộc một cách có kiểm soát.
- Phân chia suite để phản hồi nhanh mà vẫn giữ các gate an toàn quan trọng.
- Bổ sung regression test từ sự cố mà không làm suite phụ thuộc dữ liệu hoặc thời gian ngẫu nhiên.

Một lần chạy xanh không chứng minh hệ thống không thể bị tấn công. Nó cung cấp bằng chứng rằng các tình huống và bất biến đã mô hình hóa vẫn giữ được tại cấu hình được kiểm tra.

## 2. Đặt hợp đồng trước khi viết assertion

Test cần một oracle: quy tắc độc lập để xác định kết quả đúng. Nếu oracle chỉ là “hàm hiện tại trả về gì thì lưu lại làm expected”, suite có thể đóng băng chính lỗi đang tồn tại.

Ví dụ, sản phẩm giả định công bố chính sách sau:

| Quyết định | Chính sách minh họa | Điều suite phải chứng minh |
|---|---|---|
| Khởi tạo reset mật khẩu | Phản hồi công khai đồng nhất cho tài khoản có và không có | Không lộ sự tồn tại qua body, header hoặc cấu trúc phản hồi |
| Thời hạn token | Có hiệu lực khi thời điểm xét nhỏ hơn expiresAt | Ngay tại expiresAt phải từ chối |
| Phạm vi token | Gắn với account, tenant, purpose và recovery transaction | Không đổi ngữ cảnh để dùng cho tác vụ khác |
| Hoàn tất reset | Thay credential và tiêu thụ quyền reset trong một giao dịch nhất quán | Không có credential mới trong khi token vẫn tái sử dụng được |
| Sau reset mật khẩu | Người dùng đăng nhập lại qua luồng thông thường | Không cấp ngầm session đầy đủ quyền từ token reset |
| Khôi phục MFA | Cần bằng chứng phù hợp chính sách bảo đảm của tài khoản | Email reset mật khẩu không tự cấp quyền tháo MFA |
| Hủy recovery | Chặn các bước chưa hoàn tất của giao dịch bị hủy | Worker chậm hoặc callback cũ không khôi phục lại giao dịch |
| Thu hồi session | Có thời hạn hiệu lực được quy định và cơ chế thực thi tương ứng | Session cũ mất quyền trên tài nguyên được bảo vệ trong giới hạn đó |

Đây là chính sách minh họa, không phải một tập giá trị bắt buộc cho mọi hệ thống. Chẳng hạn, sản phẩm có thể vô hiệu tất cả token cũ khi gửi lại, hoặc cho phép nhiều token cùng tồn tại trong một thời gian. Suite phải kiểm tra lựa chọn đã được phê duyệt, đặc biệt là tác động của lựa chọn đó khi có hai request đồng thời.

Các khuyến nghị nền tảng như thông báo công khai đồng nhất, token có hạn và dùng một lần được trình bày trong [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html). Các ma trận, mã case và cách tổ chức suite trong bài là đề xuất thiết kế từ những mục tiêu bảo mật của hệ thống giả định, không phải danh mục test do OWASP quy định.

### 2.1. Những bất biến cốt lõi

Có thể bắt đầu bằng sáu bất biến:

1. Chưa đủ bằng chứng thì chưa được thay credential hoặc tăng quyền.
2. Một bằng chứng không được sử dụng ngoài account, tenant, mục đích và giao dịch đã ràng buộc.
3. Một quyền dùng một lần không tạo ra hai thay đổi credential thành công.
4. Khi hoàn tất hoặc hủy, những tác vụ đến muộn không được mở lại quyền đã kết thúc.
5. Recovery không tự làm giảm yêu cầu xác thực của tài khoản.
6. Một thay đổi đã được công bố thành công phải có dữ liệu và tác động bảo mật phù hợp hợp đồng.

Bất biến thứ ba nói về số lần chuyển trạng thái có hiệu lực, không đơn thuần là số response HTTP 200. Cơ chế idempotency có thể trả lại kết quả thành công cũ khi client gửi lại cùng request; điều đó hợp lệ nếu chỉ có một thay đổi nghiệp vụ.

### 2.2. Ghi rõ các mốc thời gian

Đừng gộp mọi thứ thành “timeout”. Hệ thống có thể có:

- Thời hạn của token hoặc challenge.
- Thời hạn của hồ sơ xác minh danh tính.
- Thời gian chờ trước khi được thay factor.
- Cửa sổ giới hạn tốc độ.
- Độ trễ cho phép của session revocation.
- Thời hạn chờ thông báo trong kiểm thử bất đồng bộ.

Mỗi mốc cần một nguồn thời gian, ranh giới chấp nhận và điều kiện quan sát riêng. Nếu ứng dụng dùng thời gian database để tiêu thụ token, việc chỉ thay Clock trong service chưa đủ để kiểm tra ranh giới thật.

## 3. Kiểm thử chuỗi trạng thái, không chỉ từng endpoint

Một luồng recovery tổng quát có thể được mô hình hóa như sau:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PROOF_PENDING
    PROOF_PENDING --> PROOF_ACCEPTED: bang chung dat yeu cau
    PROOF_ACCEPTED --> REBIND_ALLOWED: du dieu kien chinh sach
    REBIND_ALLOWED --> COMPLETED: cap nhat credential
    REQUESTED --> CANCELLED: huy
    PROOF_PENDING --> CANCELLED: huy
    PROOF_ACCEPTED --> CANCELLED: huy
    REBIND_ALLOWED --> CANCELLED: huy
    PROOF_PENDING --> EXPIRED: het han
    PROOF_ACCEPTED --> EXPIRED: het han
    REBIND_ALLOWED --> EXPIRED: het han
    COMPLETED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
~~~

Luồng reset mật khẩu đơn giản có thể gộp một số trạng thái. Luồng hỗ trợ hoặc khôi phục factor có thể bổ sung trạng thái xem xét thủ công và thời gian chờ. Điều cần giữ là quyền thực hiện mỗi bước phải xuất phát từ trạng thái server và bằng chứng còn hiệu lực, không chỉ từ nút đang hiển thị trên giao diện.

Mỗi chuyển trạng thái cần test hợp lệ, test thiếu điều kiện và test lặp lại. Với bước thay MFA, bộ test phải thử gọi thẳng endpoint khi hồ sơ mới ở PROOF_PENDING; với hồ sơ đã hủy, cần thử cả API trực tiếp lẫn callback của bên xác minh đến sau.

Một case thường bị bỏ sót:

~~~text
1. Tạo hồ sơ R cho tài khoản A.
2. Chấp nhận bằng chứng cho R.
3. Người dùng hủy R.
4. Tác vụ nền được tạo trước bước 3 tiếp tục chạy.
5. Tác vụ đó yêu cầu mở quyền đăng ký factor mới.
~~~

Expected là không cấp quyền mới. Suite cần đọc trạng thái bền vững và thử dùng quyền đăng ký factor, bởi một event “cancelled” đã được ghi không bảo đảm bước 5 thực sự bị chặn.

## 4. Danh mục regression theo rủi ro

Một danh mục tốt gắn mỗi case với rủi ro, hợp đồng và tầng thực thi. Các mã dưới đây chỉ có ý nghĩa minh họa để duy trì truy vết.

| ID | Tình huống | Kết quả hoặc bất biến cần kiểm tra | Tầng ưu tiên |
|---|---|---|---|
| REC-001 | Reset mật khẩu hợp lệ | Đổi đúng tài khoản, token được tiêu thụ, đăng nhập lại thành công | Tích hợp + E2E |
| REC-002 | Email không tồn tại | Phản hồi công khai cùng hợp đồng, không tạo hồ sơ cho account khác | API |
| REC-003 | Token hết hạn | Không đổi credential và không cấp session | Domain + database |
| REC-004 | Đúng thời điểm hết hạn | Áp dụng chính xác ranh giới thời gian đã quy định | Domain + database |
| REC-005 | Dùng lại token đã tiêu thụ | Không tạo lần thay credential thứ hai | Database |
| REC-006 | Token tài khoản A với yêu cầu cho B | Từ chối, cả A và B giữ trạng thái phù hợp | API + database |
| REC-007 | Token tenant A dùng ở tenant B | Không đọc hoặc thay dữ liệu xuyên tenant | Tích hợp |
| REC-008 | Token reset mật khẩu dùng để reset MFA | Từ chối vì sai purpose | Domain + API |
| REC-009 | Gửi lại liên kết | Token cũ và mới tuân thủ chính sách supersession | Tích hợp |
| REC-010 | Hai request hoàn tất cùng token | Chỉ một chuyển trạng thái thay credential | Database |
| REC-011 | Client retry sau khi mất response | Không lặp tác động và có kết quả retry rõ ràng | Tích hợp |
| REC-012 | Gửi yêu cầu liên tục | Giới hạn abuse có hiệu lực, không khóa đăng nhập do yêu cầu reset đơn thuần | API |
| REC-013 | Sai code nhiều lần | Ngân sách thử bị trừ đúng và không được reset bằng cách đổi node | Tích hợp |
| REC-014 | Mất MFA nhưng còn mật khẩu | Không coi mật khẩu đơn lẻ là đủ nếu chính sách yêu cầu thêm bằng chứng | API + E2E |
| REC-015 | Recovery code đã dùng | Không cho dùng lại, kể cả đồng thời | Database |
| REC-016 | Mất passkey | Chỉ đăng ký credential mới sau bước recovery được phép | Tích hợp + E2E |
| REC-017 | Session cũ sau recovery | Request tới tài nguyên bị bảo vệ bị từ chối theo hợp đồng revocation | Tích hợp |
| REC-018 | Refresh token cũ | Không tái cấp phiên vượt qua quyết định thu hồi | Tích hợp |
| REC-019 | Hủy trong thời gian chờ | Không thay credential khi tác vụ cũ thức dậy | Tích hợp |
| REC-020 | Bên xác minh timeout | Không tự nâng mức tin cậy hoặc bỏ qua bằng chứng | Contract + tích hợp |
| REC-021 | Mail provider lỗi hoặc gửi chậm | Trạng thái và retry nhất quán; không công bố delivery không có thật | Tích hợp |
| REC-022 | Hỗ trợ viên sai quyền | Không phê duyệt hoặc sửa factor ngoài phạm vi | API |
| REC-023 | Thông báo/audit sau hoàn tất | Có sự kiện đúng định danh, không chứa secret | Tích hợp |
| REC-024 | URL, redirect hoặc host không tin cậy | Không đưa token tới đích do người gọi tùy ý chọn | API + browser |
| REC-025 | GET bởi email scanner | Không thay credential hoặc hoàn tất recovery chỉ do mở link | Browser + API |
| REC-026 | Triển khai phiên bản mới với hồ sơ cũ | Không làm sai ràng buộc hoặc mở lại quyền đã kết thúc | Tích hợp migration |

Không cần tạo mọi tổ hợp của mọi chiều. Hãy giữ test trực tiếp cho các bất biến nghiêm trọng, sau đó chọn thêm tổ hợp dựa trên đường đi chung của code, thay đổi gần đây và lịch sử sự cố.

Ví dụ, tổ hợp “tenant khác + token đã dùng + ngôn ngữ khác” thường kém giá trị hơn “hai tenant có cùng email + token của tenant thứ nhất + endpoint suy tenant từ host”. Tổ hợp sau đánh vào cách xác định account thực tế.

## 5. Fixture và dữ liệu kiểm thử có thể tái hiện

### 5.1. Xây dựng vài persona rõ mục đích

Bộ dữ liệu nên có tài khoản chỉ mật khẩu, tài khoản bật MFA, tài khoản chỉ passkey, tài khoản nhiều factor và tài khoản có phiên đang hoạt động trên nhiều thiết bị. Bổ sung hai tenant có email trùng nhau để phát hiện truy vấn thiếu tenant.

Một fixture minh họa:

~~~yaml
caseId: REC-017
policyVersion: recovery-policy-v3
account:
  reference: account-a
  tenant: tenant-a
  assurance: mfa-required
  factors:
    - password
    - totp
sessions:
  - reference: browser-before-recovery
  - reference: mobile-before-recovery
recovery:
  purpose: PASSWORD_RESET
  issuedAt: 2030-01-01T00:00:00Z
  expiresAt: 2030-01-01T00:15:00Z
expected:
  passwordChanges: 1
  mfaStillRequired: true
  oldSessionsUsableAfterDeadline: false
~~~

Ngày và thời hạn trong fixture chỉ là giá trị cố định để tái hiện test. Không nên hiểu 15 phút là thời hạn phù hợp cho mọi hình thức recovery.

Dữ liệu fixture không chứa tài khoản thật, email cá nhân thật, seed TOTP production hoặc khóa passkey thật. Email test có thể dùng miền dành cho ví dụ như example.test và được chặn tại mail sink của môi trường kiểm thử.

### 5.2. Tạo dữ liệu qua đúng lớp

Test tích hợp về token nên cấp token bằng API hoặc service thật để kiểm tra đúng đường tạo và lưu token. Test parser có thể dùng chuỗi giả. Test token hết hạn có thể điều khiển đồng hồ thay vì chờ thời gian thực.

Khi cần đặt một hồ sơ vào trạng thái hiếm để kiểm thử migration, có thể seed trực tiếp database bằng fixture được kiểm soát. Cần ghi rõ test đang bỏ qua bước nào; không dùng fixture đó làm bằng chứng cho toàn bộ luồng phát hành token.

Mỗi test nên có account, transaction, namespace cache và định danh idempotency riêng. Chỉ rollback database chưa chắc dọn được message queue, cache hoặc request đã được gửi cho provider stub.

### 5.3. Phân biệt kiểm soát ngẫu nhiên và kiểm tra mật mã

Dùng token generator có thể điều khiển trong unit test để tạo case dễ đọc. Nhưng việc đó không kiểm chứng token production được tạo bằng nguồn ngẫu nhiên thích hợp.

Suite cần một kiểm tra riêng đối với wiring production: đường phát hành dùng thành phần sinh token dự kiến, secret không đi vào log, và dữ liệu lưu trữ tuân thủ thiết kế. Không viết assertion “mọi token trong 100 mẫu đều khác nhau nên đủ an toàn”; số mẫu nhỏ không chứng minh entropy hay chất lượng mật mã.

## 6. Cấu trúc suite theo tầng

| Tầng | Kiểm tra chính | Phụ thuộc thật cần giữ |
|---|---|---|
| Domain/unit | Purpose, state machine, ranh giới thời gian, điều kiện policy | Logic nghiệp vụ |
| Component/API | Mapping request, xác định tenant, quyền gọi, response công khai | Routing và middleware cần kiểm tra |
| Database integration | Tiêu thụ nguyên tử, transaction, unique constraint, migration | Engine và hành vi giao dịch mục tiêu |
| Provider contract | Timeout, mã lỗi, schema callback, xác thực callback | Adapter và hợp đồng provider |
| End-to-end | Hành trình người dùng, link, cookie, đăng nhập lại | Các thành phần triển khai trong môi trường test |
| Hệ thống phân tán | Revocation nhiều node, redelivery, retry, cache consistency | Thành phần chia sẻ trạng thái thực tế |

Unit test xanh không thay thế được test race với database. Provider stub xanh không chứng minh credential cấu hình cho provider sandbox còn hoạt động. E2E xanh cũng có thể bỏ sót việc token được lưu sai nếu không kiểm tra storage.

Trong một E2E reset mật khẩu, hành trình hữu ích là:

1. Tạo tài khoản và đăng nhập để có session cũ.
2. Khởi tạo recovery qua giao diện hoặc API công khai.
3. Lấy email từ mail sink test, không từ bảng database chứa token hash.
4. Mở link và hoàn tất biểu mẫu.
5. Đăng nhập bằng credential mới qua cơ chế thông thường.
6. Thử credential cũ, token recovery cũ và session cũ theo chính sách.
7. Quan sát thông báo và audit đã được tạo.

Mail sink phải có bộ lọc theo transaction hoặc định danh test. Nếu luôn lấy “email mới nhất”, hai test chạy song song có thể nhận nhầm token và tạo lỗi khó tái hiện.

## 7. Ví dụ Java: kiểm tra ranh giới hết hạn

Ví dụ sau dùng JUnit Jupiter và Java 17 trở lên. Nó tự chứa logic mô hình cho một quy tắc thời gian; đây là minh họa cách xây test ranh giới, chưa phải integration test của dịch vụ recovery.

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RecoveryExpiryBoundaryTest {

    private static final Instant EXPIRES_AT =
            Instant.parse("2030-01-01T00:15:00Z");

    private static boolean isTimeValid(
            Instant expiresAt, Clock clock) {
        return clock.instant().isBefore(expiresAt);
    }

    @ParameterizedTest(name = "offsetMillis={0}, valid={1}")
    @CsvSource({
            "-1, true",
            "0, false",
            "1, false"
    })
    void expiryUsesExclusiveUpperBound(
            long offsetMillis, boolean expected) {
        Clock clock = Clock.fixed(
                EXPIRES_AT.plusMillis(offsetMillis),
                ZoneOffset.UTC);

        assertEquals(
                expected,
                isTimeValid(EXPIRES_AT, clock));
    }
}
~~~

Trong sản phẩm, thay hàm mô hình bằng thành phần policy thật, sau đó có test riêng ở tầng tiêu thụ token. Bộ test này chỉ chứng minh cách biểu diễn “now < expiresAt”, không chứng minh token đã dùng, sai purpose hoặc sai account bị từ chối.

Nếu storage chỉ giữ độ chính xác tới millisecond, không tạo fixture nanosecond rồi mặc định database bảo toàn nó. Kiểm tra thời điểm trước, đúng và sau ranh giới theo độ chính xác thực sự. Với thời gian được database quyết định, dùng cơ chế kiểm soát thời gian phù hợp tầng đó hoặc seed thời điểm tương đối có biên đủ rõ; tránh đánh cược vào vài millisecond của máy CI.

Trong JUnit Jupiter, test tham số hóa cần module junit-jupiter-params tương ứng với phiên bản bộ test đang dùng; xem [JUnit User Guide — Parameterized Tests](https://docs.junit.org/current/writing-tests/parameterized-classes-and-tests.html). Không cần đổi phiên bản JUnit của dự án chỉ để áp dụng ý tưởng này.

## 8. Token dùng một lần: kiểm tra cả trạng thái và hành vi

Một test token dùng một lần tối thiểu phải chứng minh:

- Lần đầu tạo đúng thay đổi được phép.
- Token hoặc grant chuyển sang trạng thái không thể dùng lại.
- Lần thứ hai không thay đổi credential, factor hoặc session thêm lần nữa.
- Các request đồng thời không vượt qua điều kiện chưa sử dụng.
- Lỗi giữa các bước không để lại trạng thái dở dang nguy hiểm.

Một phép tiêu thụ tại database có thể được biểu diễn bằng SQL sau:

~~~sql
UPDATE recovery_grant
SET consumed_at = :now
WHERE id = :grant_id
  AND token_digest = :token_digest
  AND account_id = :account_id
  AND tenant_id = :tenant_id
  AND purpose = :purpose
  AND consumed_at IS NULL
  AND cancelled_at IS NULL
  AND expires_at > :now;
~~~

Số hàng cập nhật bằng 1 là tín hiệu giành được quyền thực hiện bước tiếp theo trong thiết kế này. Đó chưa phải toàn bộ quy trình an toàn: việc thay credential và đóng giao dịch recovery phải nằm trong cùng ranh giới nhất quán được thiết kế. Nếu account và grant nằm cùng database, có thể dùng một transaction; nếu ở hai dịch vụ, cần mô hình trạng thái và cơ chế điều phối riêng.

Trong bài, SQL là ví dụ về phép cập nhật có điều kiện, không phải công thức đầy đủ cho mọi schema. Các kiểm tra policy hoặc evidence version có thể đòi hỏi điều kiện bổ sung.

### 8.1. Assertion phải quan sát tác động thực

Chỉ kiểm tra consumed_at khác null có thể bỏ sót trường hợp credential chưa thay mà token đã mất. Chỉ kiểm tra credential mới dùng được có thể bỏ sót token vẫn hoạt động.

Sau test thành công, cần quan sát cả credential đích, khả năng dùng lại grant, số lần tăng phiên bản credential nếu hệ thống có trường đó, và event nghiệp vụ đã commit. Với password hash có salt ngẫu nhiên, không so sánh hash mới với một chuỗi hash cố định; hãy xác minh credential qua password verifier hoặc luồng đăng nhập.

Đối với kết quả từ chối, kiểm tra credential, factor và quyền session không thay đổi. Audit về lần từ chối hoặc bộ đếm chống abuse vẫn có thể tăng; “không có side effect” ở đây phải được diễn đạt cụ thể, không cấm cả việc ghi nhận an ninh cần thiết.

### 8.2. Idempotency không thay thế single-use

Có hai tình huống khác nhau:

~~~text
A. Cùng idempotency key + cùng request:
   Có thể trả lại kết quả đã lưu, không tạo thay đổi mới.

B. Khác idempotency key + cùng token:
   Không được tạo lần thay credential thứ hai.
~~~

Thử thêm trường hợp cùng key nhưng payload khác. Ví dụ lần đầu đặt mật khẩu P1, lần sau cùng key đặt P2. Hợp đồng nên từ chối xung đột hoặc xử lý theo quy tắc rõ ràng; không âm thầm trả thành công khiến client tưởng P2 đã có hiệu lực.

Không ghi password hoặc raw token vào báo cáo assertion khi payload khác nhau. Có thể dùng nhãn dữ liệu test và so sánh digest dành cho quan sát nội bộ được kiểm soát.

## 9. Tái hiện lỗi cạnh tranh một cách có kiểm soát

Hai request được gửi “gần nhau” không chắc cùng đi qua vùng nguy hiểm. Scheduler, connection pool hoặc database có thể vô tình tuần tự hóa chúng, khiến triển khai lỗi vẫn vượt qua test.

Một test cạnh tranh hữu ích cần tạo được tình huống hai request cùng cố tiêu thụ một grant còn hiệu lực, qua hai transaction và connection độc lập. Điểm đồng bộ phải nằm trước phép tranh quyền nguyên tử hoặc tại ranh giới read-then-write mà ta muốn kiểm tra.

### 9.1. Khung kiểm thử tích hợp

Đoạn Java dưới đây là khung minh họa cho test harness của dự án. RecoveryFixture, ResetResult và các phương thức fixture là API giả định cần được hiện thực; đoạn mã không phải một file test có thể biên dịch độc lập.

~~~java
@Test
void concurrentAttemptsChangeCredentialOnlyOnce() throws Exception {
    RecoveryFixture fixture = fixtures.accountWithIssuedResetGrant();
    long versionBefore = fixture.credentialVersion();
    ExecutorService pool = Executors.newFixedThreadPool(2);

    try {
        // Hook chỉ tồn tại trong test adapter.
        // Hai giao dịch dừng ngay trước phép tiêu thụ grant.
        fixture.armBeforeConsumeBarrier(2);

        Future<ResetResult> first = pool.submit(() ->
                fixture.resetOnIndependentConnection(
                        "request-a", "new-password-a"));
        Future<ResetResult> second = pool.submit(() ->
                fixture.resetOnIndependentConnection(
                        "request-b", "new-password-b"));

        fixture.awaitBothAtBarrier(Duration.ofSeconds(5));
        fixture.releaseConsumeBarrier();

        ResetResult a = first.get(5, TimeUnit.SECONDS);
        ResetResult b = second.get(5, TimeUnit.SECONDS);

        assertEquals(1,
                Stream.of(a, b)
                        .filter(ResetResult::changedCredential)
                        .count());

        assertEquals(versionBefore + 1,
                fixture.readCredentialVersionFromDatabase());
        assertEquals(1, fixture.countCommittedCompletionEvents());
        assertFalse(fixture.canUseGrantForAnotherReset());
    } finally {
        // Giải phóng cả khi một assertion hoặc worker bị lỗi.
        fixture.releaseConsumeBarrier();
        pool.shutdownNow();
        pool.awaitTermination(5, TimeUnit.SECONDS);
    }
}
~~~

Trong test này, hai idempotency key khác nhau cố tạo hai thay đổi credential. Assertion “một kết quả changedCredential” chỉ phù hợp với kiểu kết quả của harness đã định nghĩa, không áp đặt rằng mọi API phải trả một response 200 và một response 409.

Một triển khai có retry nội bộ vì serialization failure vẫn có thể đúng. Harness phải giới hạn retry, quan sát kết quả cuối cùng, và bảo đảm retry không phát sinh thêm completion event. Count event trong ví dụ là event nghiệp vụ đã commit với định danh logic riêng; không phải số lần message broker giao cùng event.

### 9.2. Vị trí barrier rất quan trọng

Không đặt barrier sau khi transaction đầu đã giữ khóa hàng mà transaction thứ hai cần lấy trước khi tới barrier. Khi đó test tự tạo deadlock ở harness: request đầu chờ request sau, request sau chờ khóa của request đầu.

Với cách cập nhật có điều kiện nguyên tử, barrier có thể nằm ngay trước câu UPDATE. Với triển khai nghi ngờ có lỗi “đọc chưa dùng rồi mới cập nhật”, hãy có test adapter điều phối để hai lần đọc đều quan sát trạng thái chưa dùng trước khi thả hai lần cập nhật.

Hook test không được mở qua endpoint vận hành hoặc trở thành quyền bỏ qua policy trong production. Mọi điểm chờ đều cần timeout để lỗi hệ thống tạo ra báo cáo rõ ràng thay vì treo toàn bộ suite.

Test cạnh tranh còn cần các cặp sự kiện:

| Cặp sự kiện | Điều cần bảo toàn |
|---|---|
| Hoàn tất và hủy cùng hồ sơ | Kết quả cuối phù hợp một thứ tự hợp lệ; không vừa hủy có hiệu lực vừa hoàn tất sau đó |
| Dùng token cũ và gửi lại token | Áp dụng đúng quy tắc supersession tại thời điểm quyết định |
| Dùng recovery code ở hai node | Chỉ một lần tiêu thụ code thành công |
| Đổi địa chỉ recovery và callback cũ | Callback không cấp quyền dựa trên phiên bản bằng chứng đã bị thay |
| Thu hồi session và refresh đồng thời | Refresh không tạo đường vượt quyết định revocation |
| Hai hồ sơ recovery cùng account | Không để hồ sơ cũ khôi phục lại quyền đã bị hồ sơ mới thu hồi |

Một lần chạy với barrier chứng minh tình huống điều phối cụ thể. Có thể bổ sung nhiều seed hoặc lịch thực thi khác ở đợt kiểm tra dài hơn, nhưng luôn lưu seed và trace đủ để tái hiện failure.

## 10. MFA, passkey và luồng hỗ trợ

### 10.1. Tách thay mật khẩu khỏi khôi phục factor

Với tài khoản bật MFA, reset mật khẩu thành công không đồng nghĩa người dùng đã chứng minh quyền thay MFA. Suite cần chạy tiếp luồng đăng nhập và xác nhận yêu cầu factor vẫn tồn tại theo chính sách.

Đối với khôi phục MFA, thử cả trường hợp người dùng còn một factor độc lập, còn recovery code và mất toàn bộ factor. Chính sách cho mỗi trường hợp có thể khác nhau. Điều cần kiểm tra là bằng chứng của một nhánh không bị tái sử dụng để bỏ qua điều kiện của nhánh khác.

[OWASP Multifactor Authentication Cheat Sheet — Resetting MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa) nhấn mạnh cơ chế lấy lại quyền truy cập không được tạo đường vượt MFA, và lựa chọn recovery phải tùy bối cảnh ứng dụng. Từ nguyên tắc đó, suite của sản phẩm cần có case trực tiếp cho đường thay factor và đường phê duyệt hỗ trợ.

Ví dụ một case hỗ trợ:

~~~text
Given:
  Hồ sơ R ở tenant A đang chờ xem xét.
  Nhân viên S chỉ có quyền đọc hồ sơ ở tenant A.

When:
  S gọi API phê duyệt recovery và đặt factor mới.

Then:
  Không chuyển trạng thái sang được phép thay factor.
  Không có factor mới.
  Có ghi nhận hành động bị từ chối theo chính sách audit.
~~~

Nếu sản phẩm yêu cầu hai người phê duyệt, kiểm tra cùng một actor không thể đóng hai vai bằng cách dùng hai phiên hoặc hai API khác nhau. Nếu sản phẩm không có quy tắc đó, không tự thêm kỳ vọng vào suite.

### 10.2. Passkey là credential mới, không phải khôi phục private key

Khi mất passkey, một thiết kế recovery thường cấp quyền có giới hạn để đăng ký credential thay thế. Suite cần theo dõi quyền đó từ lúc phát hành đến khi được tiêu thụ hoặc hết hạn.

Các case nên bao gồm:

- Chưa hoàn tất recovery mà đã gọi trực tiếp endpoint đăng ký credential mới.
- Grant của account A dùng trong phiên recovery của account B.
- Grant đúng account nhưng sai tenant hoặc sai purpose.
- Dùng lại challenge đăng ký hoặc gửi callback đã được xử lý.
- Đăng ký thất bại nhưng hệ thống đã vô hiệu factor duy nhất còn hợp lệ.
- Hoàn tất recovery rồi tiếp tục dùng quyền đăng ký tạm để thêm factor ngoài phạm vi.

Việc kiểm tra challenge, origin và RP ID cần đi qua thành phần xác minh WebAuthn thật ở tầng thích hợp; mock luôn trả “valid” chỉ kiểm tra được phần điều phối quanh nó. Với E2E, dùng authenticator ảo do công cụ kiểm thử cung cấp và ghi rõ cấu hình. Nó không thay thế việc kiểm tra tương thích với phần cứng và nền tảng mục tiêu.

Không mặc định mọi passkey cũ đều phải bị xóa sau recovery. Có passkey bị mất thiết bị nhưng chưa được xác định là lộ; có credential đã được kết luận bị chiếm. Suite cần áp dụng chính sách thu hồi theo từng tình huống và không làm mất các phương thức truy cập an toàn ngoài dự kiến.

## 11. Session sau recovery: kiểm tra quyền truy cập thực tế

Một event “revoke sessions” được ghi thành công chưa chứng minh session đã mất quyền. Phép thử cuối cần dùng session cũ gọi một tài nguyên được bảo vệ.

Kịch bản minh họa:

~~~text
1. Đăng nhập trước recovery, lấy session S1 và refresh token F1.
2. Hoàn tất recovery cho cùng account.
3. Gọi tài nguyên bảo vệ bằng S1.
4. Thử refresh bằng F1.
5. Gọi lại qua node khác hoặc sau khi cache được làm ấm.
6. Đăng nhập bằng credential mới và factor còn được yêu cầu.
~~~

Expected tại bước 3–5 phải tuân theo hợp đồng revocation đã chọn. Nếu thu hồi tức thời là yêu cầu, không dùng polling dài để che đi khoảng thời gian phiên cũ còn sử dụng được. Nếu hệ thống cho phép lan truyền trong một giới hạn đã công bố, đo deadline và thất bại khi vượt giới hạn đó.

Với access token tự chứa, vô hiệu refresh token không tự động làm access token hết giá trị. Suite cần thể hiện kiến trúc thực tế: kiểm tra phiên bản session, danh sách thu hồi, introspection, TTL hoặc cơ chế khác mà tài nguyên đang dùng.

Một regression quan trọng là refresh chạy đồng thời với recovery:

1. Refresh đọc trạng thái phiên cũ.
2. Recovery cập nhật phiên bản bảo mật hoặc trạng thái thu hồi.
3. Refresh tiếp tục cấp token mới từ dữ liệu đã đọc ở bước 1.
4. Tài nguyên nhận token mới.

Expected là token vừa cấp không được tạo đường vượt quyết định thu hồi. Tùy thiết kế, refresh phải bị từ chối, phải kiểm tra lại version lúc commit, hoặc token mới sẽ bị resource từ chối. Suite kiểm tra hiệu lực cuối, đồng thời kiểm tra cơ chế được hệ thống cam kết.

Phải giữ cả positive control: sau khi session cũ bị thu hồi, một lần đăng nhập mới với đầy đủ điều kiện vẫn hoạt động. Nếu chỉ assert mọi request đều bị từ chối, lỗi làm toàn hệ thống không đăng nhập được cũng có thể cho kết quả xanh.

## 12. Fault injection và thông báo bất đồng bộ

Recovery liên quan nhiều phụ thuộc, nên suite phải cố ý gây lỗi tại những ranh giới có thể làm dữ liệu không nhất quán.

| Điểm gây lỗi | Trạng thái mong đợi | Kiểm tra tiếp theo |
|---|---|---|
| Trước commit thay credential | Không công bố hoàn tất; thay đổi được rollback theo thiết kế | Token và credential vẫn nhất quán, retry có quy tắc rõ |
| Sau commit nhưng trước khi gửi response | Trạng thái hoàn tất đã bền vững | Retry không tạo thay đổi lần hai |
| Provider gửi mail timeout | Trạng thái gửi là chưa xác định hoặc chờ retry theo adapter | Không phát thêm vô hạn token hoặc bỏ qua rate limit |
| Ghi nhận outbox thất bại trong transaction chung | Không commit nửa thay đổi nếu outbox là phần bắt buộc | Kiểm tra rollback và khả năng thử lại |
| Broker giao lại event | Không lặp tác động nghiệp vụ ngoài hợp đồng | Deduplication gắn với event ID hoặc khóa tương ứng |
| Callback xác minh đến sau khi hủy | Hồ sơ tiếp tục bị hủy | Không mở quyền thay factor |
| Dịch vụ rủi ro không đáp ứng | Không tự coi rủi ro thấp | Nhánh fallback đúng chính sách đã phê duyệt |
| Kho rate limit gặp lỗi | Hành vi fail-open/fail-closed đúng lựa chọn đã xác định | Không biến lỗi hạ tầng thành đường bỏ qua kiểm soát ngoài dự kiến |
| Tiến trình chết giữa hai bước phân tán | Có trạng thái phục hồi được theo thiết kế | Worker tiếp tục hoặc hòa giải mà không cấp thêm quyền |

Fail-closed là lựa chọn thường phù hợp cho quyết định cấp quyền nhạy cảm, nhưng suite không tự đoán fallback. Hợp đồng cần nêu kết quả khi dependency không xác định được bằng chứng. Không nên báo “an toàn” chỉ vì mọi lỗi hạ tầng đều khiến tất cả người dùng bị khóa vĩnh viễn.

### 12.1. Kiểm tra outbox đúng mức bảo đảm

Nếu cập nhật credential và tạo outbox record cùng transaction, test phải kiểm tra cả hai được commit hoặc cả hai được rollback. Sau đó test publisher riêng để xác nhận có retry và xử lý redelivery.

Outbox không bảo đảm email vật lý chỉ được gửi đúng một lần. Provider có thể nhận email nhưng client không nhận ACK; retry có thể gây gửi lặp nếu provider không hỗ trợ idempotency phù hợp. Vì vậy, phân biệt:

- Một sự kiện nghiệp vụ recovery hoàn tất.
- Một hoặc nhiều lần thử chuyển giao thông báo.
- Kết quả provider chấp nhận gửi.
- Việc người dùng thực sự nhận thông báo.

Không dùng số email nhận được làm bằng chứng duy nhất rằng credential chỉ đổi một lần.

### 12.2. Chờ điều kiện thay vì ngủ cố định

Với tác vụ bất đồng bộ, test nên đợi một điều kiện có deadline, chẳng hạn “outbox record của transaction R đã được xử lý”. Mỗi lần thăm dò phải dùng định danh riêng của test.

Ngủ hai giây rồi assert dễ lỗi khi CI chậm và lãng phí khi hệ thống nhanh. Tuy nhiên, thay sleep bằng polling không có nghĩa được nới deadline tùy tiện. Deadline phải có mục đích: kiểm tra thời hạn hiệu lực bảo mật hoặc chỉ giới hạn chờ của harness, và hai loại đó không nên bị lẫn.

## 13. Enumeration, thông báo và rò rỉ dữ liệu

### 13.1. Không dùng một request để kết luận về timing

Với account tồn tại và không tồn tại, kiểm tra hợp đồng phản hồi là bước đầu: mã trạng thái theo thiết kế, body công khai, header, redirect và kích thước các trường có thể quan sát.

Đối với timing, không viết assertion “hai lần gọi chênh dưới 10 ms” trên runner dùng chung rồi xem đó là bằng chứng chống enumeration. Độ trễ mạng, khởi động JVM, GC và cache có thể lớn hơn tín hiệu cần đo.

Một chiến lược hợp lý hơn:

1. Giữ kiểm tra logic nhanh để phát hiện nhánh return sớm khác đường xử lý dự kiến.
2. Có phép đo chuyên biệt trong môi trường ổn định, xen kẽ nhóm account tồn tại và không tồn tại.
3. Warm-up, lưu nhiều mẫu và phân tích phân bố theo tiêu chí đã định trước.
4. Điều tra khác biệt lặp lại được thay vì tăng ngưỡng cho đến khi test xanh.
5. Kiểm tra cả biến thể cache nóng, account bị hạn chế và provider lỗi.

Kiểm thử timing chỉ đánh giá các điều kiện đã đo. Không diễn giải một phép đo không phát hiện khác biệt là chứng minh mọi kênh phụ đều biến mất.

### 13.2. Mở link không được tự hoàn tất recovery

Email scanner, trình xem trước và người dùng mở nhiều tab đều có thể thực hiện GET. Case REC-025 cần mở link nhiều lần và xác nhận chưa thay credential, chưa cấp phiên đầy đủ quyền và chưa hoàn tất giao dịch.

Nếu thiết kế đổi token trong URL sang một restricted session ngay khi mở link, test phải kiểm tra session đó chỉ có quyền cần thiết, có vòng đời đúng và không biến việc scanner đọc link thành hành động không thể phục hồi cho người dùng. Việc tiêu thụ link ở bước nào phải xuất phát từ hợp đồng cụ thể.

Đối với URL và browser, giữ case cho host không tin cậy, redirect không được cho phép, referrer, cache của trang recovery và cookie của phiên giới hạn. Kiểm tra sau reverse proxy nữa nếu proxy là nơi quyết định host hoặc rewrite URL; test trực tiếp controller có thể bỏ qua chính thành phần tạo lỗi.

### 13.3. Thu thập bằng chứng mà không thu thập secret

Nên dùng log test có cấu trúc với case ID, correlation ID, account reference giả, transition và mã lỗi nội bộ. Không ghi raw token, password, recovery code, seed TOTP hoặc toàn bộ URL chứa secret vào artifact CI.

Kiểm tra cả access log, trace span, exception, ảnh chụp màn hình và HTTP dump. Một assertion thất bại có thể in toàn bộ request trong khi log của ứng dụng đã được che đúng.

Test về rò rỉ có thể tìm các secret do chính fixture tạo trong những sink được phép thu thập. Việc không tìm thấy trong một sink không chứng minh các sink còn lại an toàn; danh mục kiểm tra phải khớp pipeline quan sát của môi trường được triển khai.

## 14. Đưa suite vào CI và giữ gate có ý nghĩa

Phân tầng lịch chạy dựa trên rủi ro và thời gian, không đẩy toàn bộ test khó xuống lịch ban đêm rồi bỏ qua khi phát hành.

| Nhóm | Thời điểm gợi ý | Nội dung chính |
|---|---|---|
| Hồi quy nhanh | Mỗi thay đổi liên quan | Policy, state transition, token scope, expiry, authorization |
| Tích hợp bắt buộc | Trước merge thay đổi recovery/auth/session | Consume nguyên tử, transaction, race trọng yếu, revocation |
| Luồng xuyên hệ thống | Trước phát hành cấu hình liên quan | Mật khẩu, MFA/passkey đại diện, mail sink, đăng nhập lại |
| Kiểm tra mở rộng | Theo lịch hoặc trước thay đổi lớn | Nhiều node, fault injection rộng, phân tích timing, migration |

Nếu lỗi nghiêm trọng chỉ phát hiện ở nhóm mở rộng, cần xem có thể tạo một biến thể nhỏ, xác định và nhanh hơn cho gate bắt buộc hay không. Case race một token thường có thể chạy ở tầng tích hợp mà không cần browser hoặc provider thật.

### 14.1. Chọn test theo tác động nhưng giữ lõi cố định

Một thay đổi template email vẫn nên chạy test link, public response và rò rỉ secret. Một thay đổi session middleware phải chạy REC-017/018 ngay cả khi không sửa thư mục recovery.

Duy trì một lõi cố định gồm scope, single-use, expiry, authorization và session theo hợp đồng. Công cụ chọn test theo đường dẫn có thể thêm test, nhưng không nên làm mất lõi chỉ vì dependency gián tiếp chưa được khai báo.

Các cấu hình cần đi qua ít nhất một tổ hợp đại diện: tenant policy khác nhau, tính năng mới bật/tắt, phiên bản schema trước và sau migration. Snapshot cấu hình hoặc policy version phải xuất hiện trong báo cáo để có thể tái hiện.

### 14.2. Xử lý flaky test

Không tự động chạy lại đến khi xanh rồi bỏ qua lần lỗi đầu. Một lần lỗi có thể là bằng chứng hiếm của race hoặc trạng thái dùng chung.

Khi test không ổn định, cần phân loại: lỗi sản phẩm, fixture dùng chung, timeout của harness hay điều kiện môi trường. Lưu log và seed cần thiết trước cleanup. Nếu phải tạm cách ly test, có owner, thời hạn và biện pháp kiểm tra thay thế cho bất biến tương ứng.

Một test single-use quan trọng đang bị cách ly không thể được coi như gate đó đã PASS.

### 14.3. Kiểm tra độ nhạy của suite

Có thể dùng mutation có kiểm soát trong môi trường test để hỏi suite có phát hiện việc bỏ điều kiện purpose, thay dấu “>” thành “>=” ở expiry, bỏ consumed_at hoặc không tăng phiên bản session hay không.

Mutation sống sót có thể cho thấy thiếu test, oracle yếu hoặc đường code chưa được thực thi. Cần điều tra thay vì chỉ theo đuổi tỷ lệ mutation score. Không chạy thay đổi cố ý làm yếu bảo mật lên hệ thống dùng dữ liệu thật.

## 15. Từ sự cố thành một regression test bền vững

Giả sử người dùng báo rằng sau recovery, ứng dụng di động vẫn truy cập được trong khi trình duyệt đã bị đăng xuất. Một cách xử lý suite là:

1. Mô tả bất biến bị phá: session cũ trên mọi loại client phải mất quyền trong thời hạn chính sách.
2. Tái hiện với tài khoản test có cả session browser và refresh token mobile.
3. Quan sát sự khác nhau giữa logout giao diện, trạng thái session store và API resource.
4. Tạo test thất bại trên bản có lỗi, gọi tài nguyên thực bằng token mobile cũ.
5. Sửa nguyên nhân, sau đó xác nhận test chuyển xanh.
6. Bổ sung biến thể refresh đồng thời nếu nguyên nhân liên quan phiên bản credential hoặc cache.
7. Giữ test ở tầng thấp nhất vẫn bắt được lỗi, cùng một E2E đại diện khi cần.

Không gắn regression test vĩnh viễn với account ID, token hoặc timestamp của sự cố thật. Chuyển điều kiện gây lỗi thành fixture tổng quát và chỉ giữ tham chiếu sự cố trong metadata quản lý của nhóm.

Một hồ sơ case có thể ghi như sau:

~~~yaml
id: REC-017-mobile-refresh
invariant: old-session-cannot-regain-access-after-recovery
risk: account-takeover
policyVersion: recovery-policy-v3
level: integration
preconditions:
  - active-mobile-session-before-recovery
  - refresh-route-enabled
actions:
  - complete-authorized-recovery
  - refresh-with-old-token
  - call-protected-resource
expected:
  - no-access-beyond-revocation-deadline
  - no-second-credential-change
  - fresh-login-with-required-factors-still-works
~~~

Đây là tài liệu cho suite, không phải đề xuất thêm trường vào YAML metadata của bài học hoặc sửa schema của module.

## 16. Bài tập vận dụng

### Bài tập 1: Tìm khoảng trống của một suite đang xanh

Một suite chỉ có ba test:

- Reset mật khẩu với token hợp lệ trả thành công.
- Token hết hạn trả lỗi.
- Sau reset, mật khẩu mới đăng nhập được.

Hãy đề xuất năm test ưu tiên bổ sung và giải thích mỗi test bắt được loại lỗi nào.

Gợi ý đáp án: dùng lại token để bắt thiếu consume; hai request đồng thời để bắt read-then-write; sai account/tenant để bắt thiếu scope; reset password không tháo MFA để bắt giảm yêu cầu xác thực; session cũ không còn quyền để bắt thiếu revocation. Nếu chính sách session khác nhau theo loại recovery, phải nêu rõ loại đang kiểm tra.

### Bài tập 2: Thiết kế assertion cho lỗi mất response

Credential đã đổi và transaction đã commit, nhưng kết nối bị ngắt trước khi client nhận response. Client gửi lại cùng idempotency key.

Hãy chỉ ra những gì cần quan sát ngoài mã HTTP.

Gợi ý đáp án: số lần thay credential, trạng thái grant, payload gắn với idempotency key, số completion event logic, khả năng đăng nhập bằng credential đã đặt và hành vi nếu retry mang payload khác. Việc trả kết quả cũ có thể đúng; thay credential thêm lần nữa mới là vi phạm bất biến.

### Bài tập 3: Phân biệt lỗi harness với lỗi sản phẩm

Test race luôn timeout. Trace cho thấy request đầu đã giữ row lock trước barrier; request thứ hai chưa tới barrier vì đang đợi cùng row lock.

Hãy điều chỉnh cách tái hiện mà vẫn kiểm tra được single-use.

Gợi ý đáp án: dời điểm đồng bộ trước thao tác lấy khóa hoặc dùng test adapter đúng ranh giới cần kiểm tra; bảo đảm hai connection độc lập, timeout hữu hạn và cleanup giải phóng điểm chờ. Sau đó assert số chuyển trạng thái thành công trong database và khả năng dùng lại grant.

### Bài tập 4: Kiểm thử một fallback mới

Nhóm đề xuất cho phép tiếp tục recovery bằng email khi dịch vụ chấm điểm rủi ro timeout để giảm số người bị chặn.

Hãy xác định điều kiện cần có trước khi viết expected result.

Gợi ý đáp án: phải làm rõ mức bảo đảm của account, bằng chứng độc lập còn lại, phạm vi quyền được cấp và quyết định policy đã được phê duyệt. Một timeout không tự là bằng chứng rủi ro thấp. Suite cần test cả nhánh fallback được phép lẫn account mà fallback không đáp ứng yêu cầu.

## 17. Tiêu chí một lần chạy có thể dùng làm bằng chứng

Khi sử dụng kết quả regression suite để quyết định phát hành, cần biết phiên bản code, schema, policy, feature flag, môi trường và danh sách case thực sự được chạy. Báo cáo phải phân biệt PASS, FAIL, SKIPPED và case đang cách ly.

Những kiểm tra quan trọng cần có cả negative control lẫn positive control: bằng chứng sai bị từ chối nhưng bằng chứng đúng còn hoạt động; session cũ mất quyền nhưng đăng nhập mới đúng điều kiện vẫn thành công. Điều đó ngăn suite đạt kết quả xanh chỉ vì dịch vụ đang từ chối mọi người.

Giá trị của recovery regression suite nằm ở khả năng giữ các bất biến qua thay đổi: người dùng có thể lấy lại tài khoản bằng bằng chứng phù hợp; token, factor và session được xử lý đúng phạm vi; lỗi phụ thuộc hoặc xử lý đồng thời không tạo thêm quyền. Bộ test cần tiếp tục phát triển theo chính sách, kiến trúc và những sự cố mà hệ thống thực sự gặp.

## Tài liệu tham khảo

- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): nền tảng về phản hồi, token và quy trình reset mật khẩu.
- [OWASP Multifactor Authentication Cheat Sheet — Resetting MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa): các cân nhắc khi lấy lại quyền truy cập sau khi mất factor.
- [JUnit User Guide — Parameterized Classes and Tests](https://docs.junit.org/current/writing-tests/parameterized-classes-and-tests.html): cách khai báo và cấp dữ liệu cho test tham số hóa.
